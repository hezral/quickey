import time
import subprocess
import psutil
import os
import signal

def benchmark_launch():
    print("Building flatpak...")
    # Clean and build to ensure fresh start
    subprocess.run(["flatpak-builder", "--force-clean", "--user", "--install", "build-dir", "com.github.hezral.quickey.yml"], check=True)
    
    print("Starting benchmark...")
    
    # Start the application
    start_time = time.time()
    
    # We use a trick: start it in background and poll for it
    process = subprocess.Popen(["flatpak", "run", "com.github.hezral.quickey"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # We need to wait for the window to actually map
    # A good proxy is when the process stabilizes or logs something
    # For now, let's just wait for the process to be available and track stats
    
    launch_time = None
    max_cpu = 0
    max_mem = 0
    
    try:
        p = psutil.Process(process.pid)
        
        # This is a bit tricky with flatpak as the 'flatpak run' is a wrapper
        # We need to find the actual child process
        child = None
        for _ in range(100): # 10 seconds max wait for child
            # Search all processes for our app-id or name
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any("quickey" in arg.lower() for arg in cmdline) and any("python" in arg.lower() for arg in cmdline):
                        child = proc
                        # We found a python process with quickey in it
                        # Let's verify it's not the flatpak-builder or something else
                        if "flatpak-builder" not in " ".join(cmdline):
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if child:
                launch_time = time.time() - start_time
                break
            time.sleep(0.1)
            
        if not child:
             print("Could not find the Quickey python process.")
             # Fallback: look for ANY process with 'quickey' in it that isn't 'flatpak'
             for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and "quickey" in " ".join(cmdline).lower() and "flatpak" not in proc.info['name']:
                         print(f"Fallback found: {proc.info['name']} (PID: {proc.info['pid']})")
                         child = proc
                         launch_time = time.time() - start_time
                         break
                except:
                    continue
        
        if not child:
            print("Failed to find process after 10s.")
            return

        print(f"Detected launch (process start) in {launch_time:.4f} seconds")
        print(f"Monitoring PID: {child.pid} ({child.name()})")
        
        # Phase 1: Launch (first 3 seconds)
        print("Measuring Launch CPU...")
        launch_cpus = []
        for _ in range(30): 
            try:
                launch_cpus.append(child.cpu_percent(interval=0.1))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
        max_launch_cpu = max(launch_cpus) if launch_cpus else 0
        
        # Wait for animations to settle
        print("Waiting for animations to settle...")
        time.sleep(1.0)
        
        # Phase 2: Steady State (next 5 seconds)
        print("Measuring Steady State CPU (Idle) and Memory...")
        idle_cpus = []
        mems = []
        for _ in range(25): # 5 seconds total (0.2s interval)
            try:
                idle_cpus.append(child.cpu_percent(interval=0.2))
                mems.append(child.memory_info().rss / (1024 * 1024))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
        avg_idle_cpu = sum(idle_cpus) / len(idle_cpus) if idle_cpus else 0
        max_idle_cpu = max(idle_cpus) if idle_cpus else 0
        max_mem = max(mems) if mems else 0
        
        # Phase 3: Quit 
        print("Triggering Quit and measuring CPU...")
        try:
            # We use animate_quit if we could, but SIGTERM is our proxy
            child.terminate() 
            quit_cpus = []
            # Monitor for up to 2 seconds of quit activity
            for _ in range(40):
                if not child.is_running():
                    break
                try:
                    cpu = child.cpu_percent(interval=0.05)
                    quit_cpus.append(cpu)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
            max_quit_cpu = max(quit_cpus) if quit_cpus else 0
        except:
            max_quit_cpu = 0

    finally:
        try:
            if process.poll() is None:
                os.kill(process.pid, signal.SIGTERM)
                process.wait()
        except:
            pass
        
    print("\nBenchmark Results:")
    print(f"Launch time: {launch_time:.4f} seconds")
    print(f"Max CPU during Launch: {max_launch_cpu:.2f}%")
    print(f"Avg CPU during Steady State: {avg_idle_cpu:.2f}% (Max: {max_idle_cpu:.2f}%)")
    print(f"Max CPU during Quit: {max_quit_cpu:.2f}%")
    print(f"Max Memory usage (steady state): {max_mem:.2f} MB")

if __name__ == "__main__":
    benchmark_launch()
