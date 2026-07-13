import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Optional
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logging.getLogger('apscheduler').setLevel(logging.WARNING)


class EmbyClient:
    def __init__(self, base_url: str, api_key: str = None, username: str = None, password: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.user_id = None
        self.headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            self.headers['X-Emby-Token'] = self.api_key
            self.user_id = self._get_user_id()
        elif username and password:
            if not self._authenticate(username, password):
                raise Exception("Authentication failed")
        logger.info(f"用户ID: {self.user_id}")

    def _authenticate(self, username: str, password: str) -> bool:
        endpoint = f"{self.base_url}/Users/AuthenticateByName"
        data = {
            'Username': username,
            'Pw': password
        }
        headers = {
            'Content-Type': 'application/json',
            'X-Emby-Authorization': 'MediaBrowser Client="EmbyAutoClean", Device="Docker", DeviceId="emby-autoclean", Version="1.0.0"'
        }
        try:
            response = requests.post(endpoint, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            self.api_key = result.get('AccessToken')
            self.user_id = result.get('User', {}).get('Id')
            self.headers['X-Emby-Token'] = self.api_key
            return True
        except requests.RequestException as e:
            logger.error(f"认证失败: {e}")
            return False

    def _get_user_id(self) -> Optional[str]:
        response = self._request('GET', '/Users/Me')
        if response:
            return response.json().get('Id')
        return None

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"请求失败: {e}")
            return None

    def get_libraries(self) -> List[Dict]:
        response = self._request('GET', '/Library/VirtualFolders')
        return response.json() if response else []

    def get_items(self, parent_id: str, include_item_types: str = "Episode") -> List[Dict]:
        params = {
            'ParentId': parent_id,
            'Recursive': 'true',
            'IncludeItemTypes': include_item_types,
            'Fields': 'UserData,Path,Tags,IndexNumber,ParentIndexNumber'
        }
        if self.user_id:
            params['UserId'] = self.user_id
        response = self._request('GET', '/Items', params=params)
        return response.json().get('Items', []) if response else []

    def delete_item(self, item_id: str) -> bool:
        return self._request('DELETE', f'/Items/{item_id}') is not None

    def get_series_episodes(self, series_id: str) -> List[Dict]:
        items = self.get_items(series_id, 'Episode')
        items.sort(key=lambda x: (x.get('ParentIndexNumber', 0), x.get('IndexNumber', 0)))
        return items


class EpisodeCleaner:
    def __init__(
        self,
        client: EmbyClient,
        days_to_keep: int = 30,
        keep_episodes: int = 2,
        library_filter: List[str] = None,
        tag_filter: List[str] = None,
        whitelist_tags: List[str] = None,
        dry_run: bool = False
    ):
        self.client = client
        self.days_to_keep = days_to_keep
        self.keep_episodes = keep_episodes
        self.library_filter = library_filter or []
        self.tag_filter = tag_filter or []
        self.whitelist_tags = whitelist_tags or []
        self.dry_run = dry_run
        self.stats = {'deleted': 0, 'skipped': 0, 'errors': 0}

    def should_process_library(self, library_name: str) -> bool:
        return not self.library_filter or library_name in self.library_filter

    def has_whitelist_tag(self, item: Dict) -> bool:
        return bool(set(item.get('Tags', []) or []) & set(self.whitelist_tags))

    def has_target_tag(self, item: Dict) -> bool:
        if not self.tag_filter:
            return True
        return bool(set(item.get('Tags', []) or []) & set(self.tag_filter))

    def is_watched(self, item: Dict) -> bool:
        return item.get('UserData', {}).get('Played', False)

    def get_watched_date(self, item: Dict) -> Optional[datetime]:
        last_played = item.get('UserData', {}).get('LastPlayedDate')
        if last_played:
            try:
                return datetime.fromisoformat(last_played.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
        return None

    def should_delete(self, item: Dict) -> bool:
        if not self.is_watched(item):
            return False
        if self.has_whitelist_tag(item) or not self.has_target_tag(item):
            return False

        watched_date = self.get_watched_date(item)
        if not watched_date:
            return self.days_to_keep == 0

        days_since_watched = (datetime.now(watched_date.tzinfo) - watched_date).days
        return days_since_watched >= self.days_to_keep

    def get_series_to_keep(self, series_id: str) -> List[str]:
        episodes = self.client.get_series_episodes(series_id)
        watched = sorted(
            [ep for ep in episodes if self.is_watched(ep)],
            key=lambda x: (x.get('ParentIndexNumber', 0), x.get('IndexNumber', 0)),
            reverse=True
        )
        return [ep['Id'] for ep in watched[:self.keep_episodes]]

    def clean_series(self, series: Dict):
        series_name = series.get('Name', 'Unknown')
        keep_ids = self.get_series_to_keep(series['Id'])
        episodes = self.client.get_series_episodes(series['Id'])
        
        watched_count = sum(1 for ep in episodes if self.is_watched(ep))
        if watched_count == 0:
            return
        
        logger.info(f"  📺 {series_name} (已观看: {watched_count}/{len(episodes)})")

        for episode in episodes:
            if not self.is_watched(episode):
                continue
                
            ep_name = episode.get('Name', f"S{episode.get('ParentIndexNumber', 0):02d}E{episode.get('IndexNumber', 0):02d}")
            
            if episode['Id'] in keep_ids:
                self.stats['skipped'] += 1
                logger.info(f"    ✓ 保留: {ep_name}")
                continue

            watched_date = self.get_watched_date(episode)
            if watched_date:
                days = (datetime.now(watched_date.tzinfo) - watched_date).days
                logger.debug(f"    UserData: {user_data}")
            
            if self.should_delete(episode):
                if self.dry_run:
                    logger.info(f"    ✗ 将删除: {ep_name}")
                    self.stats['deleted'] += 1
                else:
                    if self.client.delete_item(episode['Id']):
                        logger.info(f"    ✗ 已删除: {ep_name}")
                        self.stats['deleted'] += 1
                    else:
                        self.stats['errors'] += 1
            else:
                self.stats['skipped'] += 1
                if watched_date:
                    logger.info(f"    - 跳过: {ep_name} (观看于 {days} 天前)")
                else:
                    logger.info(f"    - 跳过: {ep_name} (无观看记录)")

    def clean_library(self, library: Dict):
        library_name = library.get('Name', 'Unknown')
        if not self.should_process_library(library_name):
            return

        series_list = self.client.get_items(library['Id'], 'Series')
        if not series_list:
            return

        logger.info(f"▶ {library_name} ({len(series_list)} 部剧集)")
        for series in series_list:
            self.clean_series(series)

    def run(self):
        logger.info("=" * 40)
        logger.info("开始清理已观看剧集")
        logger.info(f"保留天数: {self.days_to_keep} | 保留集数: {self.keep_episodes} | 预览模式: {self.dry_run}")
        logger.info("=" * 40)

        libraries = self.client.get_libraries()
        for library in libraries:
            if library.get('CollectionType') == 'tvshows':
                self.clean_library(library)

        logger.info("=" * 40)
        logger.info(f"清理完成: 删除 {self.stats['deleted']} | 跳过 {self.stats['skipped']} | 错误 {self.stats['errors']}")
        logger.info("=" * 40)


def parse_list(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def main():
    from dotenv import load_dotenv
    load_dotenv()

    emby_url = os.getenv('EMBY_URL')
    emby_api_key = os.getenv('EMBY_API_KEY')
    emby_username = os.getenv('EMBY_USERNAME')
    emby_password = os.getenv('EMBY_PASSWORD')

    if not emby_url:
        logger.error("EMBY_URL 必须设置")
        sys.exit(1)

    if not emby_api_key and not (emby_username and emby_password):
        logger.error("必须设置 EMBY_API_KEY 或 EMBY_USERNAME/EMBY_PASSWORD")
        sys.exit(1)

    days_to_keep = int(os.getenv('DAYS_TO_KEEP', '30'))
    keep_episodes = int(os.getenv('KEEP_EPISODES', '2'))
    library_filter = parse_list(os.getenv('LIBRARY_FILTER', ''))
    tag_filter = parse_list(os.getenv('TAG_FILTER', ''))
    whitelist_tags = parse_list(os.getenv('WHITELIST_TAGS', ''))
    dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
    cron_schedule = os.getenv('CRON_SCHEDULE', '0 2 * * *')

    try:
        client = EmbyClient(emby_url, emby_api_key, emby_username, emby_password)
    except Exception as e:
        logger.error(f"连接 Emby 失败: {e}")
        sys.exit(1)

    cleaner = EpisodeCleaner(
        client=client,
        days_to_keep=days_to_keep,
        keep_episodes=keep_episodes,
        library_filter=library_filter,
        tag_filter=tag_filter,
        whitelist_tags=whitelist_tags,
        dry_run=dry_run
    )

    def run_cleanup():
        try:
            cleaner.run()
        except Exception as e:
            logger.error(f"清理失败: {e}")

    if cron_schedule:
        logger.info(f"定时任务: {cron_schedule}")
        parts = cron_schedule.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            scheduler = BlockingScheduler()
            trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
            scheduler.add_job(run_cleanup, trigger)
            scheduler.start()
    else:
        run_cleanup()


if __name__ == '__main__':
    main()
