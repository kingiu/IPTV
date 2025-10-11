#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频画面静止检测模块
使用ffprobe工具分析视频流，检测画面是否处于静止状态
"""
import subprocess
import json
import re
import time
import logging
from urllib.parse import urlparse
from functools import lru_cache

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('screen_detection')

class ScreenDetection:
    """视频画面静止检测类"""
    
    def __init__(self, timeout=5, sample_duration=3, min_frames=2, cache_size=100):
        """
        初始化画面检测参数
        
        Args:
            timeout: 检测超时时间(秒) - 优化为5秒
            sample_duration: 采样时长(秒) - 优化为3秒
            min_frames: 最小采样帧数 - 优化为2帧
            cache_size: 缓存大小 - 新增缓存机制
        """
        self.timeout = timeout
        self.sample_duration = sample_duration
        self.min_frames = min_frames
        # 为URL检测结果添加缓存，避免重复检测相同URL
        self.detect_frozen_screen = lru_cache(maxsize=cache_size)(self._detect_frozen_screen_impl)
        
    def is_video_url(self, url):
        """判断URL是否可能是视频流 - 优化版本"""
        # 快速过滤：只处理http/https和rtmp协议
        if not (url.startswith('http') or url.startswith('rtmp')):
            return False
        
        # 检查URL中是否包含常见的视频流标识符
        url_lower = url.lower()
        # 使用集合提高查找效率
        video_indicators = {'.m3u8', '.mp4', '.flv', '.ts', 'stream', 'live', 'm3u8'}
        for indicator in video_indicators:
            if indicator in url_lower:
                return True
        
        return False
        
    def _detect_frozen_screen_impl(self, url):
        """
        检测视频流是否为静止画面的实际实现（内部方法，带缓存）
        
        Args:
            url: 视频流URL
        
        Returns:
            tuple: (是否静止画面, 错误信息或None)
        """
        # 快速过滤非视频URL
        if not self.is_video_url(url):
            return False, "不是视频流URL"
        
        try:
            # 合并ffprobe和ffmpeg的功能，减少一次调用
            # 直接使用ffmpeg分析视频流，检测帧数和活动画面
            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', str(self.sample_duration),  # 采样时长 - 优化为3秒
                '-vf', 'select=gt(scene\,0.01)',  # 只选择场景变化明显的帧
                '-vsync', '0',
                '-f', 'null',
                '-loglevel', 'error',
                '-'
            ]
            
            # 执行命令，设置超时
            start_time = time.time()
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                timeout=self.timeout,
                text=True
            )
            
            # 分析输出结果
            output = result.stderr
            # 查找类似 "frame=   25" 的行
            frame_match = re.search(r'frame=\s*(\d+)', output)
            
            # 简单的快速判断：如果命令执行成功且有帧输出
            if result.returncode == 0 and frame_match:
                frames_extracted = int(frame_match.group(1))
                logger.debug(f"URL: {url[:50]}... 提取到的变化帧数: {frames_extracted}")
                
                # 如果检测到的变化帧数过少，认为是静止画面
                if frames_extracted < self.min_frames:
                    return True, f"画面变化帧数过少({frames_extracted}帧)，可能是静止画面"
            else:
                # 如果执行失败，可能是流不可用或者响应太慢
                # 不将这种情况标记为静止画面，避免误判
                logger.warning(f"视频分析失败或无足够数据: {output[:100]}...")
                return False, "视频分析失败"
            
            # 额外的优化：检查处理时间是否异常短
            execution_time = time.time() - start_time
            if execution_time < self.sample_duration * 0.4:
                return True, f"处理时间异常短({execution_time:.2f}秒)，可能是静止画面或无效流"
            
            return False, None
            
        except subprocess.TimeoutExpired:
            # 超时通常意味着流不可用或响应慢，不标记为静止画面
            logger.debug(f"检测超时: {url[:50]}...")
            return False, f"检测超时({self.timeout}秒)"
        except Exception as e:
            logger.debug(f"检测发生错误: {str(e)}")
            return False, f"检测发生错误: {str(e)}"
    
    def clear_cache(self):
        """清除检测结果缓存"""
        self.detect_frozen_screen.cache_clear()

# 创建全局实例供其他模块使用
screen_detector = ScreenDetection()

# 提供简单的函数接口
def is_frozen_screen(url):
    """检测视频流是否为静止画面"""
    return screen_detector.detect_frozen_screen(url)

if __name__ == "__main__":
    # 测试代码
    import sys
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        frozen, message = is_frozen_screen(test_url)
        print(f"URL: {test_url}")
        print(f"是否静止画面: {frozen}")
        if message:
            print(f"原因: {message}")
    else:
        print("请提供测试URL")