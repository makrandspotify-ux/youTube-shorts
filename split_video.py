from moviepy.video.io.VideoFileClip import VideoFileClip
import os

# 1. Load the giant video
source_video = "background_loop.mp4"
clip = VideoFileClip(source_video)

# 2. Define chunk length (e.g., 90 seconds per part ensures they stay under 100MB 
# but are long enough for the agent to pull a 58s clip from).
chunk_duration = 90  
total_duration = clip.duration

print(f"Total duration: {total_duration}s. Splitting into {chunk_duration}s chunks...")

# 3. Slice and export
start_time = 0
part_num = 1

while start_time < total_duration:
    end_time = min(start_time + chunk_duration, total_duration)
    
    # If the last remaining chunk is shorter than 60s, skip it so the agent doesn't crash later
    if (end_time - start_time) < 60:
        break
        
    print(f"Exporting bg_part{part_num}.mp4 (from {start_time}s to {end_time}s)...")
    subclip = clip.subclip(start_time, end_time)
    
    # Write the file. This will take a few minutes locally!
    subclip.write_videofile(f"bg_part{part_num}.mp4", codec="libx264", audio=False)
    
    start_time += chunk_duration
    part_num += 1

clip.close()
print("Splitting complete! You can now delete the original background_loop.mp4")