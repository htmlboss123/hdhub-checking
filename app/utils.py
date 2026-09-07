def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def get_file_quality(width: int, height: int) -> str:
    if max(width, height) >= 3840:
        return "2160p"
    elif max(width, height) >= 1920:
        return "1080p"
    elif max(width, height) >= 1280:
        return "720p"
    elif max(width, height) >= 854:
        return "480p"
    else:
        return f"{height}p"

def extract_metadata(text: str) -> list:
    if not text:
        return []
    tags = []
    for word in ['hindi', 'english', 'tamil', 'telugu', 'malayalam']:
        if word in text.lower():
            tags.append(word)
    return tags
