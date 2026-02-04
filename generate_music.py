#!/usr/bin/env python3
"""
ACE-Step Music Generation CLI

A command-line tool for generating music using the ACE-Step API.
Automatically handles task submission, polling, and file download.

Example usage:
    python generate_music.py --api-url https://your-api.runpod.net \\
        --caption "Upbeat pop song with synths" \\
        --lyrics "[Verse 1]\\nHello world\\n\\n[Chorus]\\nLa la la" \\
        --output my_song.mp3
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path


LYRICS_HELP = """
=== LYRICS STRUCTURE GUIDE ===

Use structure tags to organize your song. The AI understands these sections:

COMMON TAGS:
  [Intro]      - Instrumental opening
  [Verse 1]    - First verse (use [Verse 2], [Verse 3], etc. for more)
  [Pre-Chorus] - Build-up before chorus
  [Chorus]     - Main hook, usually repeated
  [Bridge]     - Contrasting section, often before final chorus
  [Outro]      - Ending section
  [Drop]       - For electronic music - the main beat drop
  [Break]      - Instrumental break
  [Hook]       - Short catchy phrase

EXAMPLE LYRICS:
  [Verse 1]
  Walking down the empty street
  Shadows dancing at my feet
  
  [Chorus]
  We are the dreamers of the night
  Chasing stars until the light
  
  [Verse 2]
  Memories like falling rain
  Washing away all the pain
  
  [Chorus]
  We are the dreamers of the night
  Chasing stars until the light
  
  [Bridge]
  And when the morning comes around
  We'll still be here, we won't back down
  
  [Outro]
  Dreamers of the night...

TIPS:
  - Keep verses 2-4 lines each for best results
  - Repeat the chorus for emphasis
  - Use [Instrumental] or [Solo] for non-vocal sections
  - Leave blank lines between sections
"""

CAPTION_HELP = """
=== CAPTION/STYLE GUIDE ===

The caption describes the musical style. Include:

ELEMENTS TO DESCRIBE:
  - Genre (pop, rock, folk, electronic, jazz, classical, hip-hop, etc.)
  - Instruments (guitar, piano, synths, drums, strings, etc.)
  - Mood (upbeat, melancholic, energetic, peaceful, dark, hopeful)
  - Tempo feel (slow ballad, mid-tempo groove, fast-paced)
  - Vocal style (soft female vocals, raspy male voice, choir, etc.)
  - Production style (lo-fi, polished, raw, atmospheric, reverb-heavy)

EXAMPLE CAPTIONS:
  "Upbeat indie pop with jangly guitars, bright synths, and energetic female vocals"
  
  "Dark atmospheric electronic with deep bass, haunting pads, and whispered vocals"
  
  "Warm acoustic folk ballad with fingerpicked guitar, soft harmonies, and gentle strings"
  
  "High-energy rock anthem with distorted guitars, pounding drums, and powerful male vocals"
  
  "Dreamy lo-fi hip-hop beat with jazzy piano samples and vinyl crackle"
  
  "Epic orchestral cinematic piece with soaring strings, brass, and choir"

TIPS:
  - Be specific about instruments and mood
  - Mention the atmosphere you want (cozy, epic, intimate, etc.)
  - Reference time of day or settings for mood (sunset, midnight, rainy day)
"""


def create_parser():
    """Create argument parser with detailed help."""
    parser = argparse.ArgumentParser(
        prog='generate_music',
        description='Generate music using the ACE-Step API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{CAPTION_HELP}
{LYRICS_HELP}

=== FULL EXAMPLE ===

  python generate_music.py \\
    --api-url https://g8x3vl3i1nw9g9-8000.proxy.runpod.net \\
    --caption "Dreamy indie folk with acoustic guitar and soft female vocals" \\
    --lyrics "[Verse 1]
Midnight whispers through the trees
Carrying secrets on the breeze

[Chorus]
Tonight I finally see
The light was inside of me" \\
    --duration 90 \\
    --output my_song.mp3

=== USING A LYRICS FILE ===

  python generate_music.py \\
    --api-url https://your-api.runpod.net \\
    --caption "Upbeat pop song" \\
    --lyrics-file my_lyrics.txt \\
    --output song.mp3
"""
    )
    
    parser.add_argument(
        '--api-url',
        required=True,
        help='Base URL of the ACE-Step API (e.g., https://xxx-8000.proxy.runpod.net or http://localhost:8000)'
    )
    
    parser.add_argument(
        '--caption', '-c',
        required=True,
        help='Music style description (genre, instruments, mood). See --help for detailed guide.'
    )
    
    lyrics_group = parser.add_mutually_exclusive_group()
    lyrics_group.add_argument(
        '--lyrics', '-l',
        help='Song lyrics with structure tags like [Verse], [Chorus]. Use \\n for newlines.'
    )
    lyrics_group.add_argument(
        '--lyrics-file', '-f',
        type=Path,
        help='Path to a text file containing lyrics'
    )
    
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=90,
        help='Duration in seconds (default: 90). Typical range: 30-300 depending on GPU.'
    )
    
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=1,
        help='Number of variations to generate (default: 1)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('output.mp3'),
        help='Output filename or directory (default: output.mp3). If batch_size > 1, files are numbered.'
    )
    
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=5,
        help='Seconds between status checks (default: 5)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Maximum seconds to wait for generation (default: 600)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress progress output'
    )
    
    parser.add_argument(
        '--show-lyrics-help',
        action='store_true',
        help='Show detailed guide on writing lyrics and exit'
    )
    
    parser.add_argument(
        '--show-caption-help',
        action='store_true',
        help='Show detailed guide on writing captions/styles and exit'
    )
    
    return parser


def api_request(url: str, data: dict = None, method: str = 'GET') -> dict:
    """Make an API request and return JSON response."""
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'ACE-Step-CLI/1.0'
    }
    
    if data is not None:
        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
    else:
        request = urllib.request.Request(url, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        raise RuntimeError(f"API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Request error: {e}")


def download_file(url: str, output_path: Path) -> None:
    """Download a file from URL to local path."""
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'ACE-Step-CLI/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Download error {e.code}: {e.read().decode('utf-8')}")


def check_health(api_url: str) -> bool:
    """Check if the API is healthy."""
    try:
        result = api_request(f"{api_url}/health")
        return result.get('data', {}).get('status') == 'ok'
    except Exception:
        return False


def submit_task(api_url: str, caption: str, lyrics: str, duration: int, batch_size: int) -> str:
    """Submit a music generation task and return the task ID."""
    data = {
        'caption': caption,
        'lyrics': lyrics,
        'duration': duration,
        'batch_size': batch_size
    }
    
    result = api_request(f"{api_url}/release_task", data)
    
    if result.get('code') != 200:
        raise RuntimeError(f"Task submission failed: {result.get('error')}")
    
    return result['data']['task_id']


def poll_task(api_url: str, task_id: str, poll_interval: int, timeout: int, quiet: bool) -> dict:
    """Poll for task completion and return the result."""
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise RuntimeError(f"Timeout after {timeout} seconds")
        
        result = api_request(f"{api_url}/query_result", {'task_id_list': [task_id]})
        
        if not result.get('data'):
            if not quiet:
                print(f"  Waiting for task to start... ({int(elapsed)}s)")
            time.sleep(poll_interval)
            continue
        
        task_result = result['data'][0]
        status = task_result.get('status', 0)
        
        if status == 1:  # Success
            return task_result
        elif status == 2:  # Failed
            raise RuntimeError("Generation failed")
        else:  # In progress
            if not quiet:
                print(f"  Generating... ({int(elapsed)}s)")
            time.sleep(poll_interval)


def main():
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle help flags
    if args.show_lyrics_help:
        print(LYRICS_HELP)
        sys.exit(0)
    
    if args.show_caption_help:
        print(CAPTION_HELP)
        sys.exit(0)
    
    # Get lyrics
    lyrics = ''
    if args.lyrics_file:
        if not args.lyrics_file.exists():
            print(f"Error: Lyrics file not found: {args.lyrics_file}", file=sys.stderr)
            sys.exit(1)
        lyrics = args.lyrics_file.read_text()
    elif args.lyrics:
        # Handle escaped newlines from command line
        lyrics = args.lyrics.replace('\\n', '\n')
    
    api_url = args.api_url.rstrip('/')
    
    # Check API health
    if not args.quiet:
        print(f"Connecting to {api_url}...")
    
    if not check_health(api_url):
        print(f"Error: API is not responding. Check the URL and try again.", file=sys.stderr)
        sys.exit(1)
    
    if not args.quiet:
        print("API is healthy!")
        print(f"\nSubmitting generation task:")
        print(f"  Caption: {args.caption[:60]}{'...' if len(args.caption) > 60 else ''}")
        print(f"  Duration: {args.duration}s")
        print(f"  Batch size: {args.batch_size}")
    
    # Submit task
    try:
        task_id = submit_task(api_url, args.caption, lyrics, args.duration, args.batch_size)
    except Exception as e:
        print(f"Error submitting task: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not args.quiet:
        print(f"  Task ID: {task_id}")
        print(f"\nWaiting for generation (this may take 30-120+ seconds)...")
    
    # Poll for completion
    try:
        task_result = poll_task(api_url, task_id, args.poll_interval, args.timeout, args.quiet)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not args.quiet:
        print("Generation complete!")
    
    # Parse result and download files
    result_data = json.loads(task_result['result'])
    
    if not args.quiet:
        print(f"\nDownloading {len(result_data)} audio file(s)...")
    
    downloaded_files = []
    for i, item in enumerate(result_data):
        file_url = item.get('file', '')
        if not file_url:
            continue
        
        # Determine output filename
        if len(result_data) == 1:
            output_path = args.output
        else:
            stem = args.output.stem
            suffix = args.output.suffix or '.mp3'
            output_path = args.output.parent / f"{stem}_{i+1}{suffix}"
        
        # Ensure .mp3 extension
        if not output_path.suffix:
            output_path = output_path.with_suffix('.mp3')
        
        full_url = f"{api_url}{file_url}"
        
        try:
            download_file(full_url, output_path)
            downloaded_files.append(output_path)
            if not args.quiet:
                print(f"  Saved: {output_path}")
        except Exception as e:
            print(f"  Error downloading {file_url}: {e}", file=sys.stderr)
    
    if not args.quiet:
        print(f"\nDone! Generated {len(downloaded_files)} file(s).")
        
        # Show generation info if available
        if result_data and 'generation_info' in result_data[0]:
            info = result_data[0]['generation_info']
            # Extract key info without markdown formatting
            if 'BPM:' in info:
                for line in info.split('\n'):
                    if 'BPM:' in line or 'Key Scale:' in line or 'Total Time:' in line:
                        clean_line = line.replace('**', '').replace('- ', '  ')
                        print(clean_line)
    
    # Print file paths for scripting
    for f in downloaded_files:
        print(f.resolve())


if __name__ == '__main__':
    main()
