# Đóng gói thư viện bản địa cùng phụ thuộc và hướng dẫn quyền truy cập lúc chạy

## 1. Vì sao Java native cần một gói phát hành riêng?

Mã Java trong JAR tương đối độc lập với hệ điều hành, còn mã chạy qua **JNI** (Java Native Interface) hoặc **FFM** (Foreign Function & Memory API) phụ thuộc vào binary và dynamic loader của nền tảng. Ngoài `app.jar`, sản phẩm có thể cần `.so` (Linux), `.dll` (Windows), `.dylib` (macOS), thư viện native phụ thuộc, C/C++ runtime, CPU/ABI phù hợp, launcher và cấu hình **native access** của JVM.

Một chương trình chạy được trên máy build vẫn có thể lỗi sau khi phân phối: chỉ copy JNI bridge mà quên một dependency, build cho sai CPU, yêu cầu phiên bản `glibc` mới hơn máy đích, đặt DLL trong thư mục không được loader tìm thấy, trích xuất thư viện lên vùng lưu trữ bị chặn nạp executable, hoặc không cấp quyền native access cho module Java trên JDK mới.

Có **ba tầng khác nhau** phải cấu hình và kiểm chứng:

1. **Phân phối:** phát hành đủ artifact native đúng hệ điều hành, CPU, ABI, phiên bản, giấy phép và checksum.
2. **Nạp library:** JVM tìm *thư viện chính* qua `System.load`/`System.loadLibrary` hoặc FFM; OS loader tìm *thư viện phụ thuộc* theo quy tắc riêng.
3. **Quyền lúc chạy:** JVM cho phép module Java thực hiện native operation; hệ điều hành cho phép đọc/ánh xạ binary, xác thực chữ ký và tuân thủ sandbox nếu có.

Bài này hướng dẫn một gói Linux chạy được trên **Java 17+**, rồi đối chiếu Windows, macOS, JAR chứa resource, `jpackage` và JDK 24+.

## 2. Định nghĩa rõ artifact và ma trận nền tảng

Một bản phát hành Linux có native library có thể đặt như sau:

```text
demo-release/
├── app.jar
├── native/
│   ├── libbridgejni.so
│   └── libhelper.so
├── licenses/
│   └── THIRD_PARTY_NOTICES.txt
└── bin/
    └── run.sh
```

Dùng một gói riêng cho mỗi tổ hợp nền tảng được hỗ trợ, thay vì tự giả định JAR làm cho native binary portable:

```text
artifacts/
├── demo-linux-x86_64-glibc.tar.gz
├── demo-linux-aarch64-glibc.tar.gz
├── demo-linux-x86_64-musl.tar.gz
├── demo-windows-x86_64.zip
├── demo-macos-aarch64.zip
└── demo-macos-x86_64.zip
```

Đây là **ví dụ naming convention**, không ngụ ý dự án phải build đủ mọi biến thể. Với macOS có thể lựa chọn universal binary nếu toàn bộ dependency tương thích. Một bộ release cần ghi:

| Thuộc tính | Cần biết trước khi phát hành |
| --- | --- |
| OS/CPU | Linux, Windows, macOS; `x86_64`, `aarch64`, các tên architecture được chuẩn hóa |
| ABI | `glibc`/`musl`, minimum macOS, MSVC runtime, calling convention và phiên bản thư viện |
| JDK | Java bytecode target, phiên bản JNI/FFM được sử dụng, launcher và runtime thực tế |
| Native dependencies | Các dependency trực tiếp/bắc cầu cần đi kèm hoặc được môi trường đích cung cấp |
| Bảo mật & tuân thủ | Hash/chữ ký, nguồn build, quyền file, giấy phép/notice của dependency |
| Vòng đời | Ai load/unload, đường dẫn cài đặt, liệu class loader/FFM Arena còn sử dụng binary hay không |

Cùng giá trị `os.arch` không đủ để quyết định tương thích: hai Linux `x86_64` khác `glibc`/`musl` hoặc baseline CPU vẫn có thể không chạy chung một binary. Nếu phân phối bằng Maven/Gradle, classifier hoặc variant theo OS/arch/ABI là cách thể hiện rõ ràng các bản khác nhau.

## 3. Phân biệt tìm thư viện chính và tìm thư viện phụ thuộc

Ví dụ có hai thư viện C:

```text
Java class NativeMath
    |
    | System.load("/opt/demo/native/libbridgejni.so")
    v
libbridgejni.so              <- JNI bridge
    |
    | ELF DT_NEEDED: libhelper.so
    v
libhelper.so                 <- dependency
    |
    v
libc / runtime hệ điều hành
```

**Giai đoạn 1 – JVM nạp bridge:** `System.load("/absolute/path/libbridgejni.so")` nạp file được chỉ định; `System.loadLibrary("bridgejni")` dùng tên logic và quy tắc tìm native library của JVM/class loader.

**Giai đoạn 2 – dynamic loader nạp dependency:** hệ điều hành đọc metadata của bridge và tự tìm `libhelper.so`. `java.library.path` phục vụ việc JVM tìm library chính trong nhiều tình huống, nhưng **không thay thế cơ chế tìm dependency của OS**. Việc `System.load` nhận đường dẫn tuyệt đối cũng **không bảo đảm** dependency sẽ được tìm thấy.

| API | Đầu vào đúng | Ý nghĩa |
| --- | --- | --- |
| `System.load` | Đường dẫn **tuyệt đối** đến file native | Chọn chính xác file muốn nạp |
| `System.loadLibrary` | Tên logic như `"bridgejni"` | JVM tìm tên file native tương ứng theo nền tảng |
| `System.mapLibraryName` | `"bridgejni"` | Trả `libbridgejni.so` trên Linux, `bridgejni.dll` trên Windows... |
| `SymbolLookup.libraryLookup` | `Path` hoặc tên library và `Arena` (FFM, JDK 22+) | Nạp và tra symbol theo OS; lifecycle gắn với Arena |

Không truyền `"libbridgejni.so"` hoặc `"/opt/app/native/libbridgejni.so"` cho `System.loadLibrary`. Với JNI, đặc tả quy định một JNI native library gắn với class loader; cùng một JNI library không thể nạp làm thư viện JNI cho **hai class loader khác nhau**. Vì vậy, ứng dụng plugin/hot reload cần thiết kế lớp sở hữu native bridge, không dựa vào việc load lặp cùng library từ mọi plugin.

FFM `SymbolLookup.libraryLookup` có cơ chế lifecycle riêng qua `Arena` và là restricted operation; nó **không** làm biến mất yêu cầu về ABI, dependency và quyền chạy.

## 4. Quy tắc tìm dependency của hệ điều hành

### 4.1. Linux: `DT_NEEDED`, `RUNPATH`, `RPATH` và `$ORIGIN`

Trên hệ thống Linux dùng ELF, dependency trực tiếp thường ghi trong `DT_NEEDED`. Dynamic linker tìm theo các nguồn như `DT_RPATH`/`DT_RUNPATH`, `LD_LIBRARY_PATH`, cache loader và thư mục hệ thống, tùy cấu hình và secure-execution mode.

Một cách bố trí tốt khi bundle helper cạnh JNI bridge là liên kết bridge với:

```bash
-Wl,-rpath,'$ORIGIN'
```

`$ORIGIN` tại runtime đại diện cho **thư mục chứa ELF object đang được xét**, chứ không phải current working directory. Dấu nháy đơn bảo vệ token khỏi shell expansion lúc build. Với GNU linker thông dụng, flag này ghi `DT_RUNPATH=$ORIGIN`, giúp bridge tìm dependency **trực tiếp** ở cùng thư mục.

**Điểm dễ nhầm:** `DT_RUNPATH` chỉ dùng để tìm dependency trực tiếp của object có RUNPATH; nếu `libhelper.so` cần `libthird.so`, phải kiểm tra đường tìm của `libhelper.so` hoặc lựa chọn loader strategy tương ứng. Không mặc định một RUNPATH trên bridge bảo đảm mọi dependency bắc cầu.

Dùng `readelf -d` để xem `NEEDED`, `SONAME`, `RPATH`, `RUNPATH`. Có thể đặt `LD_LIBRARY_PATH` để debug, nhưng hạn chế dùng làm cơ chế triển khai duy nhất: dễ đụng version hệ thống và có thể bị bỏ qua trong secure-execution.

### 4.2. macOS: install name, `@loader_path` và `@rpath`

macOS dùng Mach-O và `dyld`. Binary phụ thuộc có install name hoặc tham chiếu với token:

- `@loader_path`: tương đối với nơi chứa binary đang tham chiếu.
- `@rpath`: tra theo các runpath được khai báo.
- `@executable_path`: tương đối với executable chính ở nơi áp dụng.

Nếu thư viện cần helper nằm cạnh nó, một dependency tương đối dạng `@loader_path/libhelper.dylib` có thể phù hợp. Dùng `otool -L` để đọc dependencies, `otool -l` để đọc load commands; khi release, xét cả **codesign, hardened runtime, notarization và quy tắc loader**. Không trông chờ `DYLD_LIBRARY_PATH` hoạt động trong mọi chế độ bảo vệ.

### 4.3. Windows: DLL search order và native runtime

Windows có KnownDLLs, API sets, SxS, thư mục application/system, search path của tiến trình cùng các chế độ `LoadLibraryEx`. **Đường dẫn tuyệt đối đến DLL chính không bảo đảm mọi DLL phụ thuộc tự được tìm trong cùng thư mục.** Khi có quyền kiểm soát native launcher/loader, xem các cơ chế an toàn như `LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR`, `SetDefaultDllDirectories` và `AddDllDirectory` để xác lập đường tìm.

Không thêm thư mục do người không tin cậy ghi được vào `PATH`/search path toàn tiến trình. Với binary C++ cần Microsoft Visual C++ runtime, phải kiểm tra phiên bản và quy tắc redistributable; `jpackage` không tự giải quyết mọi dependency mà ứng dụng có thêm.

## 5. Demo chạy được: JNI bridge phụ thuộc một shared library khác

Demo sau tạo **app.jar + libbridgejni.so + libhelper.so**, chạy trên Linux với JDK 17+ và GNU-compatible C toolchain.

### 5.1. Tệp `src/NativeMath.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class NativeMath {
    static {
        String nativeDir = System.getProperty("demo.native.dir");
        if (nativeDir == null || nativeDir.isBlank()) {
            throw new IllegalStateException(
                    "Set -Ddemo.native.dir to the native directory");
        }

        Path bridge = Path.of(nativeDir)
                .toAbsolutePath()
                .normalize()
                .resolve(System.mapLibraryName("bridgejni"));

        if (!Files.isRegularFile(bridge)) {
            throw new IllegalStateException(
                    "JNI library is missing: " + bridge);
        }
        System.load(bridge.toString());
    }

    private static native int answer();

    public static void main(String[] args) {
        System.out.println("Native answer = " + answer());
    }
}
```

Code chủ động lấy đường dẫn từ launcher, chuyển thành absolute path và tải đúng library. `Files.isRegularFile` chỉ báo lỗi thiếu file sớm; **không chứng minh file an toàn hay đúng kiến trúc**.

### 5.2. Tệp `native/helper.c`

```c
/* Native dependency, không dùng JNI. */
int helper_answer(void) {
    return 42;
}
```

### 5.3. Tệp `native/bridgejni.c`

```c
#include "NativeMath.h"

/* Được export bởi libhelper.so. */
extern int helper_answer(void);

JNIEXPORT jint JNICALL
Java_NativeMath_answer(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jint)helper_answer();
}
```

Header `NativeMath.h` được sinh bởi `javac -h`, giúp tên JNI đúng với bytecode. Ví dụ dùng Java default package nên JNI symbol ở đây là `Java_NativeMath_answer`; với package/overload phải dùng header tương ứng, không tự đoán symbol name.

### 5.4. Build Java và C trên Linux

Yêu cầu `javac`, `jar`, `cc`/`gcc`, `readelf` và biến `JAVA_HOME` trỏ đến JDK có headers `include`.

```bash
mkdir -p build/classes build/headers dist/native

# Biên dịch class Java 17-compatible và sinh JNI header.
javac --release 17 \
  -h build/headers -d build/classes src/NativeMath.java

# Tạo thư viện phụ thuộc.
cc -fPIC -shared \
  -Wl,-soname,libhelper.so \
  -o dist/native/libhelper.so native/helper.c

# Tạo JNI bridge; link tới helper và đặt RUNPATH cạnh bridge.
cc -fPIC -shared \
  -Ibuild/headers \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/bridgejni.c \
  -Ldist/native -lhelper \
  -Wl,-rpath,'$ORIGIN' \
  -o dist/native/libbridgejni.so

# JAR chứa class, native libraries vẫn là file riêng.
jar --create --file dist/app.jar \
  --main-class NativeMath -C build/classes .

# Kiểm tra ELF dependency và runtime path.
readelf -d dist/native/libbridgejni.so | grep -E 'NEEDED|RUNPATH|RPATH'
```

Với GNU-compatible linker phổ biến, `readelf` phải cho thấy `NEEDED` tham chiếu `libhelper.so` và `RUNPATH` chứa `$ORIGIN`. Output có thể có thêm các thư viện hệ thống tùy toolchain. Nếu thiếu `NEEDED`, kiểm tra symbol linkage, thứ tự object/library và linker option `--as-needed`.

Gói sau build:

```text
dist/
├── app.jar
└── native/
    ├── libbridgejni.so
    └── libhelper.so
```

### 5.5. Chạy và kiểm chứng stdout

Trên **JDK 17–23** với JNI demo:

```bash
java -Ddemo.native.dir=dist/native -jar dist/app.jar
```

Trên **JDK 24+**, khi native access restriction đã áp dụng cho JNI:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.dir=dist/native \
  -jar dist/app.jar
```

**Stdout chính xác của Java khi chạy thành công:**

```text
Native answer = 42
```

Giải thích: Java load bridge từ absolute path; ELF loader đọc `DT_NEEDED: libhelper.so` của bridge; `RUNPATH=$ORIGIN` giúp tìm `libhelper.so` cùng thư mục; hàm `helper_answer()` trả `42`. Không cần thêm dependency này vào `java.library.path` trong demo.

Để thử nghiệm lý do cần dependency, tạo **bản sao** của `dist`, đổi tên `libhelper.so` trong bản sao rồi chạy lại; khi đó bridge tồn tại nhưng bước nạp dependency thất bại. Trả gói thử nghiệm về trạng thái đúng trước khi phát hành. Không sửa file native đang được hệ thống production sử dụng.

**Giới hạn tương thích:** `javac --release 17` chỉ bảo đảm bytecode/API Java mục tiêu; **không** bảo đảm binary C tương thích mọi phiên bản glibc, mọi CPU và mọi OS. Build/test native theo baseline distro và ABI đã công bố.

## 6. Cấp quyền native access trong JVM khi chạy

### 6.1. Quy tắc theo JDK

| Phiên bản | Phạm vi cần chú ý |
| --- | --- |
| JDK 17/21 | JNI truyền thống không có yêu cầu cảnh báo native access giống JDK 24; FFM của các bản này có hình thức incubator/preview khác nhau |
| JDK 22/23 | FFM API chuẩn hóa từ JDK 22 có restricted operations; JNI chưa áp dụng cùng cơ chế như JDK 24 |
| JDK 24+ | **JEP 472** áp dụng native access restriction cho JNI library loading và binding native method, đồng bộ nguyên tắc với FFM |

Với JDK 24+ theo tài liệu OpenJDK/Oracle, `--illegal-native-access` có thể là `allow`, `warn` hoặc `deny`. Các bản JDK hiện hành được tài liệu mô tả dùng `warn` làm mặc định, nhưng định hướng tương lai là `deny`. Hãy cấp quyền ngay khi thiết kế launcher và thử ở chế độ deny, tránh phụ thuộc vào cảnh báo được bỏ qua.

**Ứng dụng chạy trên classpath** (toàn bộ unnamed module, như demo):

```bash
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -Ddemo.native.dir=dist/native \
  -jar dist/app.jar
```

Lệnh trên dành cho **JDK 24+** vì chứa `--illegal-native-access`; không đem nguyên flags này vào bản JDK cũ mà chưa kiểm tra hỗ trợ.

**Ứng dụng modular**: cấp quyền tối thiểu cho module **gọi restricted API hoặc khai báo native method**. Nếu module là `com.example.nativebridge`, có thể khởi chạy theo mô hình:

```bash
java --enable-native-access=com.example.nativebridge \
  --illegal-native-access=deny \
  --module-path mods \
  --module com.example.nativebridge/com.example.nativebridge.Main
```

Đây là **mẫu lệnh** đòi hỏi module, entrypoint và thư mục `mods` thực sự tồn tại, không phải command của demo default-package. Module gọi business API qua module khác không nhất thiết là module cần native access: hãy xác định **module chứa code nạp/link native**.

Có các cách cấu hình hợp lệ khác:

- Đặt flag trong launcher script, `JDK_JAVA_OPTIONS` hoặc Java argument file `@argsfile` được quản lý tại nơi triển khai.
- Với **executable JAR chạy bằng `java -jar`**, manifest có thể chứa `Enable-Native-Access: ALL-UNNAMED`; giá trị là tên module cụ thể **không được hỗ trợ** trong attribute này.
- Với runtime image, có thể cấu hình startup options thích hợp qua công cụ `jlink`/`jpackage` và kiểm chứng launcher đã tạo.

**Không nhầm native access của JVM với quyền của OS.** `--enable-native-access` xác nhận ứng dụng chủ động thực hiện thao tác native có rủi ro cho integrity JVM; nó không cấp quyền filesystem, không bỏ qua `noexec`, Gatekeeper/Code Signing, Windows DLL policy, sandbox hay hạn chế của container.

### 6.2. Nếu dùng FFM thay JNI

Từ **JDK 22**, `java.lang.foreign.SymbolLookup.libraryLookup(Path/String, Arena)` là cách nạp/tra symbol một native library được OS nhận diện. Đây là restricted API; quyền được cấp cho module gọi method. Lifetime của lookup gắn với `Arena`: cần tránh sử dụng function pointer hoặc memory segment sau khi arena hết hiệu lực. Dependency closure, ABI và OS loader **vẫn phải được đóng gói đúng** như trường hợp JNI. Không nhầm API FFM ổn định trên JDK 22+ với API incubator/preview ở JDK 17/21.

## 7. Chiến lược đóng gói khi đưa vào sản phẩm

### 7.1. Ship native files bên cạnh JAR

Giữ thư viện native như file thật trong thư mục cài đặt và cấu hình đường dẫn từ **launcher**, dễ kiểm tra checksum, quyền, ABI và dependency. Ví dụ `bin/run.sh` trong cây thư mục của phần 2:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_HOME="$(cd -- "$(dirname -- "$0")/.." && pwd)"

exec java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.dir="$APP_HOME/native" \
  -jar "$APP_HOME/app.jar" "$@"
```

Script minh họa cho **JDK 24+**, được chạy trực tiếp theo đường dẫn thực của script (không tính trường hợp symlink cần được resolve riêng). `APP_HOME` tính từ vị trí launcher, tránh phụ thuộc current working directory. Với JDK 17–23 và JNI demo có thể bỏ `--enable-native-access`. Thư mục chứa native libraries phải chỉ được sửa bởi quá trình cài đặt tin cậy.

### 7.2. Nhúng native libraries vào JAR rồi trích xuất

Một thư viện phân phối dạng JAR có thể đặt resource theo OS/ABI:

```text
META-INF/native/linux-x86_64-glibc/libbridgejni.so
META-INF/native/linux-x86_64-glibc/libhelper.so
META-INF/native/windows-x86_64/bridgejni.dll
META-INF/native/windows-x86_64/helper.dll
META-INF/native/macos-aarch64/libbridgejni.dylib
META-INF/native/macos-aarch64/libhelper.dylib
```

Đây chỉ là **layout gợi ý**; tên file và artifact thực phải đúng nền tảng. `System.load` không thể trực tiếp mở URL resource `jar:file:...!/libbridgejni.so`. Phải trích xuất **ra file hệ điều hành**, kiểm tra và gọi `System.load(absolutePath)`.

Một extraction flow nên:

1. Chuẩn hóa OS, CPU, libc/ABI; chỉ chọn tuple nằm trong danh sách hỗ trợ, không tin giá trị đường dẫn do người dùng cung cấp.
2. Tạo cache directory riêng, **không thể bị người dùng khác sửa**, có thể map executable. Không mặc định `java.io.tmpdir` hoặc shared `/tmp` luôn phù hợp: mount `noexec` có thể khiến load thất bại.
3. Trích xuất **đủ cả dependency closure** với vị trí mà OS loader tìm được. Kiểm tra checksum/chữ ký nếu áp dụng; đóng stream, tránh path traversal và symlink replacement.
4. Dùng thư mục version/content-hash để bản cũ và mới không ghi đè nhau; ghi vào temp file rồi atomic move khi filesystem hỗ trợ, xử lý race nếu nhiều process cùng khởi động.
5. Duy trì metadata loader: Linux `$ORIGIN`, macOS install name/rpath, Windows DLL search setup. Chỉ sau khi toàn bộ file được cài đặt ổn định mới gọi `System.load`.
6. Không tự xóa/ghi đè native binary đang được tiến trình sử dụng. Cleanup cache theo phiên bản/lifecycle, nhất là trên Windows nơi file đang mở có thể bị khóa.

`System.loadLibrary` có thể tích hợp cùng `ClassLoader.findLibrary` trả absolute path, nhưng vẫn phải có chiến lược phân phối và ownership đối với library trong nhiều class loader.

### 7.3. `jpackage`, `jlink` và installer

`jpackage` tạo application image hoặc native installer phù hợp OS, có thể mang cả Java runtime, JAR và payload. Ví dụ sau **chỉ minh họa đóng gói**, sau đó cần xác minh chỗ đặt native directory và cấu hình đường dẫn của launcher:

```bash
jpackage --type app-image \
  --name NativeMathDemo \
  --input dist \
  --main-jar app.jar \
  --main-class NativeMath \
  --java-options "--enable-native-access=ALL-UNNAMED"
```

Flag `--java-options` phù hợp với **JDK 24+**; phải cấu hình thêm `-Ddemo.native.dir` với đường dẫn native trong **image thực tế**, do layout khác nhau giữa OS và bản tool. Đừng coi lệnh này là bước tạo một bản demo chạy ngay nếu chưa cấu hình đường dẫn đó.

`jpackage` **không tự phát hiện và copy toàn bộ native dependency bắc cầu** từ JAR. Cần đưa files vào payload, kiểm chứng installer thật trên OS target, kiểm tra C/C++ runtime và chữ ký ứng dụng. Các gói như `.deb`/`.rpm`, `.msi`/`.exe`, `.pkg`/`.dmg` phải được tạo và smoke test theo nền tảng được công cụ hỗ trợ. `jlink` hỗ trợ tạo custom runtime, nhưng cũng không thay thế bước giải quyết dependency của ứng dụng C/C++.

## 8. Kiểm thử bản release trên môi trường sạch

### 8.1. Kiểm tra tĩnh và phụ thuộc

Trên Linux:

```bash
file dist/native/libbridgejni.so dist/native/libhelper.so
readelf -d dist/native/libbridgejni.so
readelf -d dist/native/libhelper.so
nm -D dist/native/libbridgejni.so
nm -D dist/native/libhelper.so
sha256sum dist/app.jar dist/native/*.so
```

Tìm `NEEDED` và `RUNPATH` của cả thư viện chính và dependency. `ldd` có thể giúp quan sát thư viện được resolve trên máy test, nhưng chỉ dùng với **binary tin cậy** vì một số kiểu thực hiện `ldd` có thể thực thi mã. Output trên máy build không chứng minh đúng trên máy đích. Công cụ tương đương: `otool -L`/`codesign` trên macOS, `dumpbin /DEPENDENTS` và PE dependency tools trên Windows.

### 8.2. Smoke test động

1. Chạy gói thật và xác nhận stdout `Native answer = 42`, exit code `0`.
2. Chạy từ current working directory khác qua launcher chuẩn để phát hiện phụ thuộc đường dẫn tương đối.
3. Xác minh dependency không vô tình được resolve từ máy dev qua `LD_LIBRARY_PATH`/`PATH`, system-wide install hoặc toolchain cache.
4. Trên JDK 24+, thử `--illegal-native-access=deny` cùng danh sách `--enable-native-access` đã chọn.
5. Chạy trên image/VM sạch của từng OS + CPU + ABI được hỗ trợ, dùng Java runtime thật người dùng sẽ có.
6. Kiểm thử nâng cấp/downgrade và nhiều tiến trình để phát hiện binary/cache cũ bị reuse hoặc file in-use bị ghi đè.

Trên JDK có `jnativescan`, dùng công cụ tĩnh để kiểm tra class/JAR nào dùng JNI/restricted methods:

```bash
jnativescan --class-path dist/app.jar
```

Công cụ này **không** xác nhận `.so`/`.dll` có đủ dependency hay thành công khi OS loader chạy. Khi cần timeline, HotSpot JDK 22+ có các sự kiện JFR `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload`; trên JDK 17/21 có thể dùng snapshot `jdk.NativeLibrary`. Luôn đối chiếu message từ OS dynamic loader.

## 9. Các lỗi thường gặp và cách phân loại

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách khắc phục |
| --- | --- | --- |
| `no ... in java.library.path` | JVM không tìm được tên logic dùng cho `loadLibrary` | Cấu hình thư viện chính/launcher; hoặc dùng `System.load` với absolute path |
| `Can't load library ...`, đường dẫn sai | Cấu trúc phát hành sai, dựa vào working directory | Cấu hình đường dẫn theo nơi cài đặt và test launcher thật |
| `libhelper.so: cannot open shared object file` dù bridge tồn tại | OS loader không tìm được dependency | Kiểm tra `DT_NEEDED`, `RUNPATH=$ORIGIN`, thư viện đi kèm |
| `wrong ELF class`, `bad CPU type` | Sai CPU hoặc 32/64-bit ABI | Chọn đúng binary/target tuple |
| `GLIBC_2.xx not found` | Build trên distro quá mới, thiếu minimum ABI | Dùng build baseline phù hợp, kiểm tra symbol versions |
| `undefined symbol` hoặc `symbol not found` | Sai ABI/JNI name, thiếu symbol, dependency version không khớp | Kiểm tra `nm`, header JNI, `extern "C"` cho C++ exports, liên kết dependency |
| DLL tồn tại nhưng Windows vẫn báo thiếu | Một DLL phụ thuộc/MSVC runtime thiếu, search order không đúng | Kiểm tra PE dependencies, đóng gói redistributable và DLL search policy |
| `Permission denied`, mã ký bị từ chối, `noexec` | Quyền filesystem, mount/sandbox hoặc OS code signing | Sửa theo chính sách của OS; không kỳ vọng JVM flag bỏ qua |
| `IllegalCallerException` ở JDK mới | Module không được cấp native access khi deny | Dùng `--enable-native-access` đúng module, kiểm tra scope |
| `already loaded in another classloader` | Nhiều class loader cùng cố load một JNI library | Quy định class loader sở hữu native bridge và vòng đời |
| Trong IDE chạy được, release lỗi | Local environment ẩn thêm library/path | Test artifact độc lập trên máy sạch với launcher cuối cùng |

## 10. Checklist trước khi phân phối

- [ ] Có matrix OS/CPU/ABI/JDK đầy đủ, chỉ phát hành biến thể thật sự đã build/test.
- [ ] Có tất cả dependency trực tiếp và bắc cầu phải đi kèm, cùng giấy phép/notices.
- [ ] Library chính có đường dẫn load rõ; dependency có metadata tìm kiếm đúng Linux/macOS/Windows.
- [ ] Native files ở location tin cậy, không cho bên không được ủy quyền sửa, kiểm tra checksum/signature khi phù hợp.
- [ ] Không sử dụng file đang load cho bước overwrite/update; xử lý vòng đời JNI class loader/FFM Arena.
- [ ] Với JDK mới, launcher nêu rõ `--enable-native-access` cho module được phép; smoke test chính sách deny trên JDK 24+.
- [ ] Installer/JAR extraction/`jpackage` đều được kiểm tra thực tế, không dựa vào môi trường developer.
- [ ] Có hướng dẫn chẩn đoán riêng cho missing bridge, missing dependency, wrong ABI, OS permission và JVM native access.

## Tài liệu tham khảo

- [JNI Specification — Library and Version Management](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html) về class loader và native library.
- [OpenJDK JEP 472](https://openjdk.org/jeps/472) về JNI/FFM native access và JDK 24.
- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html) về `--enable-native-access`, `--illegal-native-access` và manifest.
- [Java SE SymbolLookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/SymbolLookup.html) về FFM library lookup và `Arena`.
- [Linux ld.so](https://man7.org/linux/man-pages/man8/ld.so.8.html) về `DT_NEEDED`, `RUNPATH` và `$ORIGIN`.
- [Apple Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html) về `@rpath`/`@loader_path`.
- [Microsoft DLL Search Order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order) về tìm dependency và search flags.
- [Oracle jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html) về ứng dụng có runtime image/installer.

Một ứng dụng Java có native code cần được phân phối như **một đơn vị gồm JAR + native libraries + dependency closure + launcher/runtime policy**. Kiểm chứng đủ bốn phần trên môi trường đích là điều kiện thực tế để release hoạt động ổn định.
