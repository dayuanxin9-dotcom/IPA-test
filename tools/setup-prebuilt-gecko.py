import urllib.request
import os
import sys
import subprocess
import zipfile
import shutil
import importlib.util

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST_DIR = os.path.join(ROOT, "engine", "firefox", "obj-aarch64-apple-ios", "dist")
BIN_DIR = os.path.join(DIST_DIR, "bin")
INC_DIR = os.path.join(DIST_DIR, "include")
GV_INC_DIR = os.path.join(INC_DIR, "GeckoView")
MOZ_INC_DIR = os.path.join(INC_DIR, "mozilla")

os.makedirs(BIN_DIR, exist_ok=True)
os.makedirs(GV_INC_DIR, exist_ok=True)
os.makedirs(MOZ_INC_DIR, exist_ok=True)

def download(url, dest):
    print(f"Downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)

# 1. 公式リリース Reynard.ipa (v0.22.1) をダウンロードしてビルド済みGecko 160.0一式を抽出
ipa_path = os.path.join(ROOT, "Reynard-0.22.1.ipa")
if not os.path.exists(ipa_path):
    download("https://github.com/minh-ton/reynard-browser/releases/download/0.22.1/Reynard.ipa", ipa_path)

print("Extracting prebuilt Gecko 160.0 binaries and resources...")
with zipfile.ZipFile(ipa_path, "r") as z:
    for info in z.infolist():
        name = info.filename
        if name.startswith("Payload/Reynard.app/Frameworks/") and name.count("/") == 3:
            fname = os.path.basename(name)
            if fname == "XUL" or (fname.endswith(".dylib") and fname != "libswift_Concurrency.dylib"):
                out = os.path.join(BIN_DIR, fname)
                with z.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(out, 0o755)
        elif name.startswith("Payload/Reynard.app/Frameworks/GeckoView.framework/Frameworks/"):
            rel = name[len("Payload/Reynard.app/Frameworks/GeckoView.framework/Frameworks/"):]
            if not rel:
                continue
            out = os.path.join(BIN_DIR, rel)
            if name.endswith("/"):
                os.makedirs(out, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)

print("Extracted Gecko binaries into:", BIN_DIR)

# 2. 必要な Gecko 160.0 ヘッダーを生成・配置
print("Generating Gecko 160.0 headers...")

with open(os.path.join(INC_DIR, "mozilla-config.h"), "w", encoding="utf-8") as f:
    f.write('#ifndef mozilla_config_h\n#define mozilla_config_h\n#define MOZILLA_VERSION "160.0"\n#endif\n')

with open(os.path.join(MOZ_INC_DIR, "Likely.h"), "w", encoding="utf-8") as f:
    f.write('#ifndef mozilla_Likely_h\n#define mozilla_Likely_h\n#define MOZ_LIKELY(x) (__builtin_expect(!!(x), 1))\n#define MOZ_UNLIKELY(x) (__builtin_expect(!!(x), 0))\n#endif\n')

base_raw = "https://raw.githubusercontent.com/mozilla-firefox/firefox/FIREFOX_160_0_RELEASE"
download(f"{base_raw}/xpcom/base/nsError.h", os.path.join(INC_DIR, "nsError.h"))

error_list_py = os.path.join(ROOT, "ErrorList.py")
download(f"{base_raw}/xpcom/base/ErrorList.py", error_list_py)
spec = importlib.util.spec_from_file_location("ErrorList", error_list_py)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
with open(os.path.join(INC_DIR, "ErrorList.h"), "w", encoding="utf-8") as f:
    mod.error_list_h(f)
os.remove(error_list_py)
print("Generated ErrorList.h successfully!")

# GeckoViewRuntimeSupport.h
patch_rt = os.path.join(ROOT, "patches", "widget", "uikit", "GeckoViewRuntimeSupport.h.patch")
with open(patch_rt, "r", encoding="utf-8") as f:
    rt_lines = [line[1:] for line in f.readlines() if line.startswith("+") and not line.startswith("+++")]
with open(os.path.join(GV_INC_DIR, "GeckoViewRuntimeSupport.h"), "w", encoding="utf-8") as f:
    f.writelines(rt_lines)

# IOSBootstrap.h & GeckoViewSwiftSupport.h (git apply で確実にパッチ適用)
tmp_patch_dir = os.path.join(ROOT, "_tmp_headers")
shutil.rmtree(tmp_patch_dir, ignore_errors=True)
os.makedirs(os.path.join(tmp_patch_dir, "toolkit", "xre"), exist_ok=True)
os.makedirs(os.path.join(tmp_patch_dir, "widget", "uikit"), exist_ok=True)

download(f"{base_raw}/toolkit/xre/IOSBootstrap.h", os.path.join(tmp_patch_dir, "toolkit", "xre", "IOSBootstrap.h"))
download(f"{base_raw}/widget/uikit/GeckoViewSwiftSupport.h", os.path.join(tmp_patch_dir, "widget", "uikit", "GeckoViewSwiftSupport.h"))

subprocess.run(["git", "apply", "--directory=_tmp_headers", os.path.join("patches", "toolkit", "xre", "IOSBootstrap.h.patch")], cwd=ROOT, check=True)
subprocess.run(["git", "apply", "--directory=_tmp_headers", os.path.join("patches", "widget", "uikit", "GeckoViewSwiftSupport.h.patch")], cwd=ROOT, check=True)

shutil.copy2(os.path.join(tmp_patch_dir, "toolkit", "xre", "IOSBootstrap.h"), os.path.join(GV_INC_DIR, "IOSBootstrap.h"))
shutil.copy2(os.path.join(tmp_patch_dir, "widget", "uikit", "GeckoViewSwiftSupport.h"), os.path.join(GV_INC_DIR, "GeckoViewSwiftSupport.h"))
shutil.rmtree(tmp_patch_dir, ignore_errors=True)

print("All prebuilt Gecko binaries and headers are ready!")
