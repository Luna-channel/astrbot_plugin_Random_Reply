from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import random
import os
import json
from typing import Tuple, Optional, Dict, Set, List, Any

@register("astrbot_plugin_random_reply", "和泉智宏＆柯尔魔改", "rrbot机器人防尬聊插件", "v0.1", "https://github.com/Luna-channel/random-reply")
class WeakBlacklistPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 初始化保底回复计数器存储路径
        self.data_dir = os.path.join("data", "WeakBlacklist")
        os.makedirs(self.data_dir, exist_ok=True)
        self.user_counters_path = os.path.join(self.data_dir, "user_interception_counters.json")
        self.group_counters_path = os.path.join(self.data_dir, "group_interception_counters.json")
        self.managed_blacklist_path = os.path.join(self.data_dir, "managed_blacklist.json")
        
        # 加载拦截计数器
        self.user_interception_counters: Dict[str, int] = {}
        self.group_interception_counters: Dict[str, int] = {}
        self._load_interception_counters()

        # 动态维护的黑名单
        self.managed_blacklisted_users: Set[str] = set()
        self.managed_blacklisted_groups: Set[str] = set()
        self._load_managed_blacklist()

        # 指令识别码
        self.command_identifier = str(self.config.get("command_identifier", "")).strip()
        if not self.command_identifier:
            logger.warning("未配置 command_identifier，/rrbot 命令已禁用。")
        
        # 命令前缀
        self.command_prefix = "/rrbot"

        # 日志记录插件初始化状态
        blacklisted_users, blacklisted_groups = self._get_combined_blacklists()
        logger.info(f"弱黑名单插件已加载，用户黑名单: {len(blacklisted_users)} 个，群聊黑名单: {len(blacklisted_groups)} 个")

    def _load_interception_counters(self):
        """加载用户和群聊被拦截次数记录"""
        # 加载用户拦截计数器
        try:
            if os.path.exists(self.user_counters_path):
                with open(self.user_counters_path, 'r', encoding='utf-8') as f:
                    self.user_interception_counters = json.load(f)
                    # 确保所有值都是整数类型
                    for key in self.user_interception_counters:
                        self.user_interception_counters[key] = int(self.user_interception_counters[key])
            else:
                self.user_interception_counters = {}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"加载用户拦截计数器失败: {e}")
            self.user_interception_counters = {}

        # 加载群聊拦截计数器
        try:
            if os.path.exists(self.group_counters_path):
                with open(self.group_counters_path, 'r', encoding='utf-8') as f:
                    self.group_interception_counters = json.load(f)
                    # 确保所有值都是整数类型
                    for key in self.group_interception_counters:
                        self.group_interception_counters[key] = int(self.group_interception_counters[key])
            else:
                self.group_interception_counters = {}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"加载群聊拦截计数器失败: {e}")
            self.group_interception_counters = {}

    def _save_interception_counters(self):
        """保存用户和群聊被拦截次数记录"""
        try:
            # 保存用户拦截计数器
            with open(self.user_counters_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_interception_counters, f, ensure_ascii=False, indent=2)
            
            # 保存群聊拦截计数器
            with open(self.group_counters_path, 'w', encoding='utf-8') as f:
                json.dump(self.group_interception_counters, f, ensure_ascii=False, indent=2)
                
            logger.debug("弱黑名单拦截计数器已保存")
        except Exception as e:
            logger.error(f"保存拦截计数器失败: {e}")

    def _load_managed_blacklist(self):
        """加载通过命令动态维护的黑名单"""
        try:
            if os.path.exists(self.managed_blacklist_path):
                with open(self.managed_blacklist_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users = data.get("users", [])
                    groups = data.get("groups", [])
                    self.managed_blacklisted_users = {str(uid) for uid in users}
                    self.managed_blacklisted_groups = {str(gid) for gid in groups}
            else:
                self.managed_blacklisted_users = set()
                self.managed_blacklisted_groups = set()
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"加载动态黑名单失败: {e}")
            self.managed_blacklisted_users = set()
            self.managed_blacklisted_groups = set()

    def _save_managed_blacklist(self):
        """保存通过命令动态维护的黑名单"""
        try:
            payload = {
                "users": sorted(self.managed_blacklisted_users),
                "groups": sorted(self.managed_blacklisted_groups)
            }
            with open(self.managed_blacklist_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存动态黑名单失败: {e}")

    def _get_config_section(self, key: str) -> Dict[str, Any]:
        """安全获取配置中的子对象"""
        value = self.config.get(key, {})
        if isinstance(value, dict):
            return value
        logger.warning(f"配置项 {key} 不是对象类型，已忽略。")
        return {}

    def _get_user_config(self) -> Dict[str, Any]:
        return self._get_config_section("user_settings")

    def _get_group_config(self) -> Dict[str, Any]:
        return self._get_config_section("group_settings")

    def _get_reply_probability(self, blacklist_type: str) -> float:
        if blacklist_type == "group":
            group_cfg = self._get_group_config()
            value = group_cfg.get("reply_probability", self.config.get("group_reply_probability", 0.3))
        else:
            user_cfg = self._get_user_config()
            value = user_cfg.get("reply_probability", self.config.get("reply_probability", 0.3))
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"{blacklist_type} reply_probability 配置值 '{value}' 非法，使用默认值 0.3")
            return 0.3

    def _get_max_interception_count(self, blacklist_type: str) -> Any:
        if blacklist_type == "group":
            group_cfg = self._get_group_config()
            return group_cfg.get("max_interception_count", self.config.get("max_group_interception_count", 8))
        user_cfg = self._get_user_config()
        return user_cfg.get("max_interception_count", self.config.get("max_interception_count", 5))

    def _get_combined_blacklists(self) -> Tuple[Set[str], Set[str]]:
        """合并配置中的黑名单与动态维护的黑名单"""
        user_cfg = self._get_user_config()
        users_enabled = bool(user_cfg.get("enable", True))
        group_cfg = self._get_group_config()
        groups_enabled = bool(group_cfg.get("enable", True))

        config_users: Set[str] = set()
        if users_enabled:
            config_users.update(str(uid) for uid in user_cfg.get("blacklisted_users", []))
            # 向后兼容旧配置
            config_users.update(str(uid) for uid in self.config.get("blacklisted_users", []))
            config_users.update(self.managed_blacklisted_users)

        config_groups: Set[str] = set()
        if groups_enabled:
            config_groups.update(str(gid) for gid in group_cfg.get("blacklisted_groups", []))
            # 向后兼容旧配置
            config_groups.update(str(gid) for gid in self.config.get("blacklisted_groups", []))
            config_groups.update(self.managed_blacklisted_groups)

        return config_users, config_groups

    def _check_blacklist_status(self, event: AstrMessageEvent) -> Tuple[bool, Optional[str], Optional[str]]:
        """直接从配置检查消息是否来自黑名单用户或群聊"""
        sender_id = str(event.get_sender_id())
        group_id = event.get_group_id()

        # 直接从 self.config 获取最新的用户黑名单并检查
        blacklisted_users, blacklisted_groups = self._get_combined_blacklists()
        if sender_id in blacklisted_users:
            return True, "user", sender_id

        # 直接从 self.config 获取最新的群聊黑名单并检查
        if group_id:
            if str(group_id) in blacklisted_groups:
                return True, "group", str(group_id)

        return False, None, None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def check_weak_blacklist(self, event: AstrMessageEvent):
        """检查弱黑名单并进行概率判断，包含保底回复机制"""
        # 检查是否在黑名单中
        is_blacklisted, blacklist_type, target_id = self._check_blacklist_status(event)
        
        if not is_blacklisted:
            # 如果曾经在黑名单中但现在已移除，清除其计数
            sender_id = str(event.get_sender_id())
            group_id = event.get_group_id()
            
            if sender_id in self.user_interception_counters:
                del self.user_interception_counters[sender_id]
                # 注意：不再每次都保存，而是在插件终止时统一保存
            
            if group_id and str(group_id) in self.group_interception_counters:
                del self.group_interception_counters[str(group_id)]
                # 注意：不再每次都保存，而是在插件终止时统一保存
            
            return
        
        # 根据黑名单类型获取相应配置
        if blacklist_type == "user":
            reply_probability = self._get_reply_probability("user")
            max_interception_cfg = self._get_max_interception_count("user")
            current_count = self.user_interception_counters.get(target_id, 0)
            counters_dict = self.user_interception_counters
        else:  # group
            reply_probability = self._get_reply_probability("group")
            max_interception_cfg = self._get_max_interception_count("group")
            current_count = self.group_interception_counters.get(target_id, 0)
            counters_dict = self.group_interception_counters
        
        log_messages = bool(self.config.get("log_blocked_messages", True))
        
        # 确保概率在合理范围内
        reply_probability = max(0.0, min(1.0, reply_probability))
        
        # 解析最大拦截次数，0或负数表示禁用保底机制
        try:
            max_interception_count = int(max_interception_cfg)
            if max_interception_count <= 0:
                max_interception_count = float('inf')  # 禁用保底机制
        except (ValueError, TypeError):
            logger.warning(f"max_interception_count 配置值 '{max_interception_cfg}' 非法，使用默认值")
            max_interception_count = 5 if blacklist_type == "user" else 8
        
        # 决定是否回复
        should_suppress_reply = True
        random_value = random.random()
        sender_name = event.get_sender_name() or "未知用户"
        
        # 生成日志标识
        if blacklist_type == "user":
            log_identifier = f"用户: {sender_name}({target_id})"
        else:
            log_identifier = f"群聊: {target_id} 中的用户: {sender_name}"
        
        # 检查是否触发保底回复
        if current_count + 1 >= max_interception_count:
            # 保底回复，重置计数
            should_suppress_reply = False
            if log_messages:
                logger.info(f"弱黑名单保底回复 - {log_identifier}, "
                           f"已达到最大拦截次数: {current_count}/{max_interception_count}")
            counters_dict[target_id] = 0
        # 如果不是保底回复，进行概率判断
        elif random_value <= reply_probability:
            # 概率允许回复，重置计数
            should_suppress_reply = False
            if log_messages and current_count > 0:
                logger.info(f"弱黑名单概率允许回复 - {log_identifier}, "
                           f"概率: {reply_probability:.2f}, 随机值: {random_value:.3f}, 重置拦截计数")
            counters_dict[target_id] = 0
        else:
            # 拦截回复，增加计数
            should_suppress_reply = True
            counters_dict[target_id] = current_count + 1
            if log_messages:
                message_preview = event.message_str[:50] + ("..." if len(event.message_str) > 50 else "")
                logger.info(f"弱黑名单拦截 - {log_identifier}, "
                           f"消息: {message_preview}, 拦截计数: {counters_dict[target_id]}/{max_interception_count}")
        
        # 注意：不再每次都保存，而是在 terminate 中统一保存
        # self._save_interception_counters() <- 移除此行
        
        # 设置事件标记
        event.set_extra("weak_blacklist_suppress_reply", should_suppress_reply)

    @filter.on_decorating_result(priority=1)
    async def suppress_reply_if_marked(self, event: AstrMessageEvent):
        """
        清空最终要发送的消息链。
        """
        if event.get_extra("weak_blacklist_suppress_reply") is True:
            log_messages = bool(self.config.get("log_blocked_messages", True))
            
            current_result = event.get_result()
            if current_result and hasattr(current_result, 'chain'):
                if log_messages:
                    sender_id = str(event.get_sender_id())
                    group_id = event.get_group_id()
                    identifier = f"群聊 {group_id} 中的用户 {sender_id}" if group_id else f"用户 {sender_id}"
                    original_chain_length = len(current_result.chain)
                    logger.info(f"弱黑名单：替换 {identifier} 的待发送消息链，长度: {original_chain_length}")
                
                # 不完全清空消息链，而是替换为一个空文本消息
                # 这样可以避免其他插件尝试访问chain[0]时出现索引越界错误
                from astrbot.api.message_components import Plain
                current_result.chain.clear()
                current_result.chain.append(Plain(text=""))
            
            # 清除标记，避免对同一事件对象的后续影响
            event.set_extra("weak_blacklist_suppress_reply", False)

    async def terminate(self):
        """插件卸载或关闭时的清理工作"""
        # 在此一次性保存最后的拦截计数，这是最合适的时机
        self._save_interception_counters()
        logger.info("弱黑名单插件已停用，拦截计数已保存。")

    @filter.command("rrbot")
    async def _cmd_rrbot(self, event: AstrMessageEvent):
        """
        处理 /rrbot 命令
        格式: /rrbot <识别码> <子命令> [参数...]
        """
        text = (event.message_str or "").strip()
        
        # 动态处理主命令和参数
        command_parts = text.lstrip('/').split()
        if not command_parts:
            return
        
        # 提取参数（去掉命令本身）
        args_str = " ".join(command_parts[1:]) if len(command_parts) > 1 else ""
        args = args_str.split()
        
        def reply(msg: str):
            return event.plain_result(msg)
        
        # 检查识别码
        if not self.command_identifier:
            yield reply("未配置识别码，/rrbot 命令不可用。")
            return
        
        if len(args) < 1:
            yield reply(f"请使用 {self.command_prefix} <识别码> help")
            return
        
        identifier = args[0]
        if identifier != self.command_identifier:
            # 识别码不匹配，不处理
            return
        
        # 提取子命令
        subcommand = args[1].lower() if len(args) > 1 else ""
        
        # 帮助信息
        if not subcommand or subcommand == "help":
            yield reply(self._get_help_text())
            return
        
        # 列表命令
        if subcommand == "list":
            yield reply(self._get_list_text())
            return
        
        # 添加/移除命令
        if subcommand in {"add", "remove"}:
            target_type, target_id = self._parse_command_target(args[2:])
            if not target_id:
                yield reply(f"格式错误，应为：{self.command_prefix} {self.command_identifier} add/remove [user|group] <QQ号/群号>")
                return
            
            if subcommand == "add":
                success, feedback = self._add_to_managed_blacklist(target_type, target_id)
            else:
                success, feedback = self._remove_from_managed_blacklist(target_type, target_id)
            
            yield reply(feedback)
            if success:
                logger.info(f"弱黑名单命令：{subcommand} {target_type} {target_id} by {event.get_sender_id()}")
            return
        
        # 未知子命令
        yield reply(f"未知子命令：{subcommand}")

    def _get_help_text(self) -> str:
        """返回帮助文本"""
        identifier_hint = self.command_identifier or "<识别码>"
        lines = [
            "随机回复插件命令帮助：",
            f"{self.command_prefix} {identifier_hint} help  - 查看该帮助",
            f"{self.command_prefix} {identifier_hint} list  - 查看当前弱黑名单及拦截计数",
            f"{self.command_prefix} {identifier_hint} add [user|group] <ID>    - 添加用户或群聊到弱黑名单（默认 user）",
            f"{self.command_prefix} {identifier_hint} remove [user|group] <ID> - 从动态弱黑名单移除指定目标"
        ]
        return "\n".join(lines)
    
    def _get_list_text(self) -> str:
        """返回列表文本"""
        users, groups = self._get_combined_blacklists()
        user_cfg = self._get_user_config()
        group_cfg = self._get_group_config()
        users_enabled = bool(user_cfg.get("enable", True))
        groups_enabled = bool(group_cfg.get("enable", True))
        lines = ["弱黑名单当前状态："]

        if not users_enabled:
            lines.append("用户弱黑名单：已禁用。")
        elif users:
            lines.append("用户：")
            for uid in sorted(users):
                count = self.user_interception_counters.get(uid, 0)
                source = "动态" if uid in self.managed_blacklisted_users else "配置"
                lines.append(f"- {uid}（{source}，拦截 {count} 次）")
        else:
            lines.append("用户黑名单为空。")

        if not groups_enabled:
            lines.append("群聊弱黑名单：已禁用。")
        elif groups:
            lines.append("群聊：")
            for gid in sorted(groups):
                count = self.group_interception_counters.get(gid, 0)
                source = "动态" if gid in self.managed_blacklisted_groups else "配置"
                lines.append(f"- {gid}（{source}，拦截 {count} 次）")
        else:
            lines.append("群聊黑名单为空。")

        return "\n".join(lines)

    def _parse_command_target(self, args: List[str]) -> Tuple[str, Optional[str]]:
        """解析命令中的目标类型与ID"""
        if not args:
            return "user", None

        first = args[0].lower()
        if first in {"user", "u", "group", "g"}:
            target_type = "group" if first in {"group", "g"} else "user"
            if len(args) < 2:
                return target_type, None
            target_id = args[1]
        else:
            target_type = "user"
            target_id = args[0]

        target_id = target_id.strip()
        if not target_id:
            return target_type, None

        return target_type, target_id

    def _add_to_managed_blacklist(self, target_type: str, target_id: str) -> Tuple[bool, str]:
        """向动态黑名单中添加目标"""
        target_id = str(target_id)
        user_cfg = self._get_user_config()
        group_cfg = self._get_group_config()
        config_users = set(str(uid) for uid in user_cfg.get("blacklisted_users", []))
        config_users.update(str(uid) for uid in self.config.get("blacklisted_users", []))
        config_groups = set(str(gid) for gid in group_cfg.get("blacklisted_groups", []))
        config_groups.update(str(gid) for gid in self.config.get("blacklisted_groups", []))

        if target_type == "group":
            if target_id in config_groups or target_id in self.managed_blacklisted_groups:
                return False, f"群聊 {target_id} 已存在于黑名单中。"
            self.managed_blacklisted_groups.add(target_id)
        else:
            if target_id in config_users or target_id in self.managed_blacklisted_users:
                return False, f"用户 {target_id} 已存在于黑名单中。"
            self.managed_blacklisted_users.add(target_id)

        self._save_managed_blacklist()
        return True, f"已将 {target_type} {target_id} 添加至弱黑名单。"

    def _remove_from_managed_blacklist(self, target_type: str, target_id: str) -> Tuple[bool, str]:
        """从动态黑名单中移除目标"""
        target_id = str(target_id)

        if target_type == "group":
            if target_id in self.managed_blacklisted_groups:
                self.managed_blacklisted_groups.remove(target_id)
                self.group_interception_counters.pop(target_id, None)
                self._save_managed_blacklist()
                return True, f"已将群聊 {target_id} 从弱黑名单移除。"
            group_cfg = self._get_group_config()
            config_groups = set(str(gid) for gid in group_cfg.get("blacklisted_groups", []))
            config_groups.update(str(gid) for gid in self.config.get("blacklisted_groups", []))
            if target_id in config_groups:
                return False, f"群聊 {target_id} 来自配置文件，如需移除请在后台/配置中操作。"
            return False, f"群聊 {target_id} 不在动态黑名单中。"

        if target_id in self.managed_blacklisted_users:
            self.managed_blacklisted_users.remove(target_id)
            self.user_interception_counters.pop(target_id, None)
            self._save_managed_blacklist()
            return True, f"已将用户 {target_id} 从弱黑名单移除。"

        user_cfg = self._get_user_config()
        config_users = set(str(uid) for uid in user_cfg.get("blacklisted_users", []))
        config_users.update(str(uid) for uid in self.config.get("blacklisted_users", []))
        if target_id in config_users:
            return False, f"用户 {target_id} 来自配置文件，如需移除请在后台/配置中操作。"
        return False, f"用户 {target_id} 不在动态黑名单中。"

