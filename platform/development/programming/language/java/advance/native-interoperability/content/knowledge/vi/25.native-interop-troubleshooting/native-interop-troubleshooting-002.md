# Chẩn đoán lỗi — Đối chiếu OS, CPU, bitness và phiên bản ABI khi nạp thư viện thất bại

## 1. Mục tiêu: chẩn đoán đúng lớp lỗi trước khi sửa

Khi Java gọi `System.loadLibrary("nativedoctor")`, `System.load("...")` hoặc dùng **FFM `SymbolLookup.libraryLookup(...)`**, Java/JVM phải làm việc với **native binary loader** của hệ điều hành. Một thư viện C/C++ hợp lệ trên máy A không nhất thiết tải được vào JVM trên máy B, dù hai bên cùng phiên bản Java hoặc có cùng tên tệp.

Có bốn câu hỏi độc lập cần kiểm chứng:

1. **OS và binary format:** JVM chạy Windows, Linux hay macOS? Thư viện là PE/COFF `.dll`, ELF `.so` hay Mach-O `.dylib`? Binary do hệ điều hành hiện tại thực sự tải được không?
2. **CPU architecture:** JVM là x86 (32 bit), x86-64/AMD64, ARM64/AArch64 hay loại khác? Native image chứa mã máy cho **kiến trúc của chính JVM process** không?
3. **Bitness / pointer width:** JVM process chạy 32 hay 64 bit? Native thư viện và các dependency có cùng độ rộng và định dạng tương thích không? **64-bit OS không đồng nghĩa JVM đang chạy 64-bit.**
4. **ABI và phiên bản phụ thuộc:** Calling convention, C/JNI symbol, `size_t`, `long`, struct layout, C/C++ runtime, versioned symbols và `JNI_OnLoad` có tương thích với JVM/OS/native dependency đang dùng không?

Đây là một bài **chẩn đoán lỗi native interoperability**, không phải hướng dẫn vô hiệu hóa kiểm tra an toàn. Cách khắc phục là **chọn/biên dịch đúng thư viện theo JVM process và ABI mục tiêu**, kiểm tra dependency và sửa hợp đồng liên kết; không tự ý đổi kiến trúc JVM hoặc chép DLL ngẫu nhiên từ Internet.

### Luồng tìm nguyên nhân

```text
Java gọi loadLibrary / load / FFM libraryLookup
                  │
                  ▼
       Đã tìm thấy tệp đích chưa?
         │ NO                    │ YES
         ▼                       ▼
 java.library.path /       Binary đúng format OS?
 classloader search         │ NO       │ YES
                            ▼          ▼
                         Chọn      CPU/bitness của thư viện
                       đúng binary  khớp JVM process?
                                       │ NO       │ YES
                                       ▼          ▼
                                  Build/download  Dependencies và
                                  đúng arch       runtime ABI đủ?
                                                 │ NO       │ YES
                                                 ▼          ▼
                                           Sửa dep/rpath   JNI_OnLoad,
                                           CRT/glibc       export symbol,
                                                           signature đúng?
                                                        │ NO       │ YES
                                                        ▼          ▼
                                                   Sửa JNI/ABI   Chạy
```

**Cùng một `UnsatisfiedLinkError` có thể có nhiều nguồn gốc.** Hãy giữ **toàn bộ error message, OS diagnostics và native library path thực tế**. Không đoán nguyên nhân chỉ dựa trên tên exception.

## 2. Hiểu 5 giai đoạn khác nhau của việc nạp native library

Một native method thường đi qua:

1. **Java chọn thư viện:** `System.loadLibrary("nativedoctor")` dùng tên logic để tra một thư viện phù hợp với nền tảng. `System.mapLibraryName("nativedoctor")` thường trả `nativedoctor.dll` (Windows), `libnativedoctor.so` (Linux), `libnativedoctor.dylib` (macOS).
2. **JVM tìm tệp:** Java classloader có thể dùng `findLibrary` riêng; nếu không, JVM tra theo cơ chế mặc định và `java.library.path` cho thư viện đích. `System.load(absolutePath)` nhận **đường dẫn tuyệt đối** và bỏ qua bước tra theo tên logic này.
3. **OS loader nạp binary + dependencies:** Windows loader, ELF loader hoặc dyld xác minh format/CPU và tìm những thư viện mà binary phụ thuộc. **`java.library.path` không trực tiếp thay thế đường tìm dependencies của hệ điều hành.**
4. **Khởi tạo native library:** OS chạy một số initializer, JVM có thể gọi `JNI_OnLoad` (nếu thư viện cung cấp); JNI version không được JVM hỗ trợ có thể làm quá trình nạp thất bại.
5. **Liên kết phương thức JNI / tạo FFM downcall:** một Java `native` method cần tên export hoặc `RegisterNatives` đúng; FFM cần symbol/`FunctionDescriptor` đúng. Lỗi này có thể xuất hiện **sau khi library load đã thành công**.

Ví dụ tên thư viện đúng nhưng JNI symbol sai:

```text
System.loadLibrary("nativedoctor")   -> load: OK
NativeLoadDoctor.ping()              -> UnsatisfiedLinkError
```

Trường hợp thứ hai không nhất thiết là "không tìm thấy DLL"; có thể DLL tồn tại và được nạp rồi nhưng thiếu export, tên Java class/package đã đổi, native function không dùng `JNIEXPORT`, C++ name bị mangle, hoặc `RegisterNatives` chưa đăng ký đúng.

**Chú ý classloader:** theo JNI specification, native libraries được quản lý theo classloader. Cố nạp **cùng một JNI library** vào **hai classloaders khác nhau** có thể ném `UnsatisfiedLinkError` dù đường dẫn và CPU đều đúng. Đừng giải quyết trường hợp đó bằng cách sao chép một binary tùy ý.

## 3. OS, CPU và bitness: đối chiếu chính xác những gì?

### 3.1. OS đích và native binary format

| OS JVM đang chạy | Định dạng native phổ biến | Tên ví dụ cho `nativedoctor` | Công cụ nhận dạng |
| --- | --- | --- | --- |
| Windows | PE/COFF, thường là DLL | `nativedoctor.dll` | `dumpbin /headers`, PowerShell đọc PE header, `dumpbin /dependents` |
| Linux | ELF shared object | `libnativedoctor.so` | `file`, `readelf -h`, `readelf -d`, `objdump -p` |
| macOS | Mach-O dynamic library/bundle | `libnativedoctor.dylib` | `file`, `lipo -archs`, `otool -L` |

Tên tệp chỉ là dấu hiệu **bên ngoài**: đổi tên `libnativedoctor.so` thành `nativedoctor.dll` **không biến ELF thành PE**. Kiểm tra **magic number** và header của file thực, không tin extension.

Linux container vẫn phải nạp **ELF Linux** tương thích với container runtime/CPU; không thể dùng Windows DLL chỉ vì host vật lý đang chạy Windows. WSL chạy môi trường Linux, nên bên trong WSL cần Linux ELF. Trên macOS Apple Silicon, một JVM chạy qua Rosetta dưới kiến trúc `x86_64` cần **x86_64 Mach-O slice**, không phải tùy ý lấy `arm64` slice vì CPU vật lý là ARM64.

### 3.2. CPU process khác CPU máy vật lý

`System.getProperty("os.arch")` phản ánh kiến trúc môi trường JVM/implementation, thường là `amd64` hoặc `x86_64` đối với JVM x64, `aarch64` đối với JVM ARM64. Các tên `amd64` và `x86_64` cùng chỉ kiến trúc x86-64; không coi khác chuỗi ký tự là lỗi. `arm64` và `aarch64` thường cùng họ ARM64.

Phân biệt:

- **CPU vật lý** của máy.
- **Kiến trúc JVM process** thực sự chạy, có thể khác CPU vật lý khi dùng Rosetta, Windows-on-ARM emulation hoặc các lớp tương thích.
- **Kiến trúc native binary và các DLL/SO con** phải tương thích với **process đang nạp**, không chỉ với máy vật lý.
- **Instruction-set extensions** như AVX2/AVX-512: một x86-64 library có thể load thành công nhưng crash với `Illegal instruction`/`SIGILL` lúc chạy trên CPU thiếu extension. Đó **không phải** lỗi không tìm thấy library.

**Đừng lấy `uname -m` hoặc `PROCESSOR_ARCHITECTURE` rồi kết luận luôn process Java có cùng ISA.** Đọc cả JVM version/architecture và header của thư viện đang định nạp.

### 3.3. 32/64-bit

**Bitness** là độ rộng của process ABI/pointer, không phải số bit của hệ điều hành. Một OS 64-bit có thể vẫn chạy JVM 32-bit (tùy nền tảng). JVM 32-bit không thể trực tiếp nạp DLL/SO 64-bit; JVM 64-bit cũng không thể trực tiếp nạp thư viện 32-bit.

Ví dụ:

| JVM process | Thư viện | Nạp trực tiếp? | Vấn đề |
| --- | --- | --- | --- |
| Windows x64 Java 64-bit | PE x64 DLL | Có thể, nếu dependencies/ABI đúng | Khớp machine và bitness |
| Windows x64 Java 64-bit | PE x86 32-bit DLL | **Không** | Trái bitness |
| Windows ARM64 Java ARM64 | PE x64 DLL | Không mặc định nạp xuyên kiến trúc vào process ARM64 | Cần library ARM64 hoặc chạy JVM x64 phù hợp |
| Linux x86-64 Java 64-bit | ELF x86-64 64-bit SO | Có thể, nếu dependencies/ABI đúng | Khớp kiến trúc |
| Linux x86-64 Java 64-bit | ELF x86 32-bit SO | **Không** | `wrong ELF class: ELFCLASS32` |
| macOS Apple Silicon Java arm64 | Mach-O universal có arm64 slice | Có thể, nếu ABI và dependencies đúng | OS chọn slice arm64 |
| macOS Apple Silicon Java x86_64 qua Rosetta | Mach-O arm64-only | **Không** | Thiếu x86_64 slice |

**`sun.arch.data.model`** thường trả `32`/`64` trên HotSpot/Azul OpenJDK nhưng là **implementation-specific property**, không phải Java SE portability guarantee. Hãy dùng cùng `java -version`, `os.arch` và binary header để chứng minh bitness.

## 4. Ghi nhận JVM environment trước khi đụng native library

Tại chính môi trường **thất bại** (IDE, Maven Surefire, Gradle Test, container hoặc Java service), chạy:

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Tìm `os.name`, `os.arch`, `java.version`, `java.home`, `java.library.path`; ghi nhận executable Java mà ứng dụng đang chạy, không chỉ `JAVA_HOME` của terminal. `javac` dùng để build source; **`java` của tiến trình chạy mới quyết định native architecture**.

Trên Windows PowerShell:

```powershell
Get-Command java | Select-Object -ExpandProperty Source
Get-Command javac | Select-Object -ExpandProperty Source
[Environment]::Is64BitProcess
[Environment]::Is64BitOperatingSystem
$env:JAVA_HOME
```

Trên Linux/macOS:

```bash
command -v java
command -v javac
uname -s
uname -m
echo "$JAVA_HOME"
```

**Lưu ý:** `command -v java` có thể trỏ tới symlink/launcher wrapper; kiểm tra file đích thực và Java runtime thật. Việc cài nhiều JDK dễ làm IDE build bằng JDK khác với server chạy. Nếu diagnostic in `os.arch=amd64` nhưng artifact release chứa `arm64` binary, đó là dấu hiệu cần chọn lại artifact.

Để tái hiện, lưu bốn trường chính cùng lỗi: **OS name/version, JVM CPU architecture, JVM process bitness, full loader error**, rồi so với header của **chính library file được dùng** và các dependencies.

## 5. Ví dụ Java 17+ có thể chạy: `NativeLoadDoctor.java`

Ví dụ này cho phép:

- In OS/JVM architecture, process bitness theo property HotSpot khi có, Java version, byte order và tên native library được Java map.
- `--bind-only` gọi một `native` method chưa được liên kết để minh họa lỗi **JNI binding**, không cần tạo library.
- `--name <logicalName>` thử `System.loadLibrary`, thể hiện vấn đề tìm kiếm theo tên.
- `--file <path>` thử `System.load` với đường dẫn tuyệt đối (tự chuyển từ path nhận được), thể hiện vấn đề binary/OS loader ngay cả khi đã bỏ qua `java.library.path`.
- Nếu load thành công, gọi native `ping()` để phân biệt **nạp thư viện** và **JNI symbol resolution**.

Source Java không cần JNI C compiler để **kiểm thử các nhánh lỗi**. Đối với chạy thực sự với native library `nativedoctor`, mã C và lệnh build ở mục 6.

### 5.1. File đầy đủ: `NativeLoadDoctor.java`

```java
import java.nio.ByteOrder;
import java.nio.file.Path;

public final class NativeLoadDoctor {
    private static native int ping();

    public static void main(String[] args) {
        System.out.println("os.name: " + System.getProperty("os.name"));
        System.out.println("os.arch: " + System.getProperty("os.arch"));
        System.out.println("VM bitness (vendor-specific): "
                + System.getProperty("sun.arch.data.model", "unknown"));
        System.out.println("java.version: " + System.getProperty("java.version"));
        System.out.println("mapped native name: "
                + System.mapLibraryName("nativedoctor"));
        System.out.println("native byte order: " + ByteOrder.nativeOrder());

        if (args.length == 0) {
            System.out.println("mode: metadata only");
            return;
        }
        if (args[0].equals("--bind-only")) {
            tryPing();
            return;
        }
        if (args.length != 2) {
            System.err.println(
                "Usage: --name logicalName | --file path | --bind-only");
            return;
        }

        try {
            if (args[0].equals("--name")) {
                System.loadLibrary(args[1]);
            } else if (args[0].equals("--file")) {
                String absolute = Path.of(args[1]).toAbsolutePath()
                        .normalize().toString();
                System.load(absolute);
            } else {
                System.err.println("Unknown mode: " + args[0]);
                return;
            }
            System.out.println("library load: OK");
        } catch (UnsatisfiedLinkError error) {
            System.out.println("library load: UnsatisfiedLinkError");
            System.err.println("loader detail: " + error.getMessage());
            return;
        }
        tryPing();
    }

    private static void tryPing() {
        try {
            System.out.println("JNI ping: " + ping());
        } catch (UnsatisfiedLinkError error) {
            System.out.println("JNI bind: UnsatisfiedLinkError");
            System.err.println("symbol detail: " + error.getMessage());
        }
    }
}
```

**Thiết kế diagnostic, không phải error handling sản phẩm:** chương trình **cố ý bắt** `UnsatisfiedLinkError` và in mã trạng thái; vì vậy exit code có thể `0` dù load/bind thất bại. CI phải xem stdout hoặc dùng một process khác có **nonzero exit** khi load fail. Không che lỗi trong ứng dụng thật và coi native functionality đã sẵn sàng.

### 5.2. Compile và sinh JNI header

Với JDK 17+:

```bash
mkdir -p build/classes build/headers
javac -encoding UTF-8 -h build/headers \
  -d build/classes NativeLoadDoctor.java
```

Dùng `javac -h` chứ không dùng công cụ `javah` đã lỗi thời. Trong `build/headers/NativeLoadDoctor.h`, compiler tạo chữ ký:

```c
JNIEXPORT jint JNICALL Java_NativeLoadDoctor_ping
  (JNIEnv *, jclass);
```

Chữ ký này được xác minh bằng `javac -h` trên **OpenJDK 24**. Vì method Java là `private static native int ping()`, C nhận `JNIEnv*` và `jclass` (không phải `jobject`) và trả `jint`.

### 5.3. Lệnh chạy thử không cần DLL/SO

Với **JDK 24+**, vì `System.load`/`System.loadLibrary` là restricted operations, dùng native-access flag khi thử tải:

```bash
# Chỉ in thông tin JVM (không yêu cầu thư viện).
java -cp build/classes NativeLoadDoctor

# Gọi native method không có thư viện liên kết.
java -cp build/classes NativeLoadDoctor --bind-only

# Thử tải một tên cố ý không tồn tại.
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeLoadDoctor \
  --name __nativedoctor_really_missing_w3_2026__
```

Với **JDK 17–23**, không áp đặt `--enable-native-access` theo quy tắc JNI JDK 24; chạy `java -cp build/classes ...` và kiểm tra chính sách của JDK hiện tại. `--illegal-native-access` cũng không có trên mọi JDK cũ.

**Stdout đầy đủ ở chế độ không tham số, đã chạy trên Windows 11/OpenJDK 24.0.2 x64:**

```text
os.name: Windows 11
os.arch: amd64
VM bitness (vendor-specific): 64
java.version: 24.0.2
mapped native name: nativedoctor.dll
native byte order: LITTLE_ENDIAN
mode: metadata only
```

Trên cùng môi trường, `--bind-only` in **sáu dòng fingerprint trên** và dòng cuối:

```text
JNI bind: UnsatisfiedLinkError
```

`stderr` có detail dạng `int NativeLoadDoctor.ping()` — chính xác câu chữ/phần dấu quote có thể khác theo JDK vendor.

Với `--name __nativedoctor_really_missing_w3_2026__`, sáu dòng fingerprint giữ nguyên, dòng cuối là:

```text
library load: UnsatisfiedLinkError
```

`stderr` có dạng `no __nativedoctor_really_missing_w3_2026__ in java.library.path: ...` (đuôi path phụ thuộc máy). **Đừng coi chuỗi này là bằng chứng sai bitness**: ở thử nghiệm này JVM chưa tìm thấy thư viện đích.

Thử đường dẫn tuyệt đối không tồn tại:

```bash
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeLoadDoctor \
  --file missing_native.dll
```

Lệnh `--file` chuyển path thành absolute rồi gọi `System.load`. Nó cũng in `library load: UnsatisfiedLinkError`, nhưng `stderr` báo lỗi `Can't load library: <đường dẫn tuyệt đối>`. Đây là lỗi **tệp đích không tồn tại**, khác với lỗi thiếu native dependency khi tệp đích có thật.

**Lưu ý loại shell:** trên Windows PowerShell, viết toàn bộ lệnh `java` trên một dòng hoặc dùng ký tự nối dòng của PowerShell. Dấu `\` cuối dòng trong ví dụ `bash` chỉ dành cho shell hỗ trợ nối dòng kiểu POSIX. Lệnh một dòng có cùng ý nghĩa.

## 6. Thư viện JNI C mẫu: kiểm tra ABI và symbol một cách xác định

Để có một library “đúng” đối chiếu với trường hợp thất bại, dùng source nhỏ sau. Java source và JNI header đã được compile/test thực tế; mã C dưới đây được rà soát **theo header đã sinh**, nhưng **chưa biên dịch/chạy C trong môi trường Windows kiểm thử do không có C compiler trên PATH**. Chỉ coi output của native call khi tự build là **dự kiến**, không nhận là đã thực thi ở đây.

### 6.1. File `nativedoctor.c`

```c
#include <jni.h>

// Java declaration: private static native int ping();
JNIEXPORT jint JNICALL Java_NativeLoadDoctor_ping
  (JNIEnv *env, jclass clazz) {
    (void) env;
    (void) clazz;
    return 42;
}

// Export này là tùy chọn, nhưng thể hiện JNI API version yêu cầu.
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    return JNI_VERSION_1_8;
}
```

**Ý nghĩa ABI:**

- `#include <jni.h>` lấy đúng typedef JNI `jint`, `JNIEnv`, `jclass` và các macro.
- `JNIEXPORT` đánh dấu symbol export/visibility phù hợp platform.
- `JNICALL` dùng calling convention mà JNI yêu cầu (đặc biệt quan trọng trên Windows x86 32-bit).
- `Java_NativeLoadDoctor_ping` phải khớp **package/class/method** do `javac -h` sinh. Khi đổi Java package/class hoặc overload method, phải sinh header và build lại.
- `JNI_OnLoad` cung cấp phiên bản JNI API tối thiểu. `JNI_VERSION_1_8` được JDK 17+ hỗ trợ; nếu `JNI_OnLoad` trả phiên bản không được JVM nhận diện, quá trình nạp bị từ chối, **dù architecture và đường dẫn đều đúng**.
- Không tự thay `JNI_OnLoad` bằng `JNI_OnLoad_libName` cho **dynamic** library; biến thể có hậu tố dùng cho thư viện liên kết tĩnh vào VM.

**Nếu build bằng compiler C++**, cần đảm bảo exported native functions dùng **C linkage** (`extern "C"`) thay vì C++ name mangling, hoặc triển khai `RegisterNatives` đúng. Hãy dùng prototype của `javac -h` làm nguồn sự thật, không đoán tên JNI thủ công.

### 6.2. Build đúng OS và CPU

**Linux x86-64 / AArch64** với GCC, chạy tại thư mục chứa `nativedoctor.c`:

```bash
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnativedoctor.so nativedoctor.c
```

**macOS** với Clang:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libnativedoctor.dylib nativedoctor.c
```

**Windows** với MSVC trong **Developer Command Prompt** hoặc **Developer PowerShell** chứa toolchain C/C++ phù hợp x64/x86/ARM64:

```bat
cl /LD /W4 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativedoctor.c /link /OUT:nativedoctor.dll
```

Lệnh Windows ở trên dùng cú pháp `cmd.exe/Developer Command Prompt` cho expansion `%JAVA_HOME%`; khi dùng PowerShell, thay bằng đường dẫn `$env:JAVA_HOME` được quote đúng. Chọn **compiler target architecture** khớp JVM process: nếu Java x64 thì dùng MSVC x64 target, nếu Java ARM64 thì dùng toolchain ARM64. Chỉ thêm `-m32` khi thực sự có đủ 32-bit toolchain và JVM 32-bit.

Nếu `JAVA_HOME` chưa được đặt tới JDK có `include/jni.h`, hãy đặt nó đúng trước khi compile. Khi thư viện có dependencies ngoài `jni.h`, cũng phải build/link chúng đúng OS/CPU/ABI.

### 6.3. Chạy bản native đã build

Sau khi đặt library vào thư mục hiện hành:

```bash
# JDK 24+: explicit native access cho code ở classpath.
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. -cp build/classes \
  NativeLoadDoctor --name nativedoctor
```

**Output cuối dự kiến khi source C đã build/nạp đúng:**

```text
library load: OK
JNI ping: 42
```

Đây là **kết quả dự kiến từ source C**, không phải log của một lần chạy C/Java hoàn chỉnh. Nếu `library load: OK` nhưng `JNI bind: UnsatisfiedLinkError`, đừng sửa `java.library.path` nữa: kiểm tra tên symbol/export/ABI và `RegisterNatives`.

## 7. Cách đọc header của thư viện đích trên từng OS

### 7.1. Windows: PE Machine và PE32/PE32+

Mở **Visual Studio Developer Command Prompt** (có `dumpbin`):

```bat
dumpbin /headers nativedoctor.dll
dumpbin /dependents nativedoctor.dll
dumpbin /exports nativedoctor.dll
```

Cách đọc:

- `FILE HEADER VALUES ... machine` cho biết ISA: `14C` thường là **Intel 386/x86 32-bit**, `8664` là **AMD64/x86-64**, `AA64` là **ARM64**.
- `OPTIONAL HEADER VALUES` cho biết magic: `10B` = **PE32**, `20B` = **PE32+** (thường 64-bit).
- `/dependents` cho tên DLL dependencies; **không chứng minh tất cả dependency đó có sẵn đúng bản ở runtime**.
- `/exports` cho biết `Java_NativeLoadDoctor_ping`, `JNI_OnLoad` và các hàm C cần tìm có thực sự được export không.

Nếu không có `dumpbin`, PowerShell có thể đọc **chính PE header**. Script sau **đã chạy trên OpenJDK 24 Windows x64** với `java.exe` và trả `0x8664` / `0x020B`:

```powershell
$path = (Get-Command java).Source
$fs = [System.IO.File]::OpenRead($path)
try {
    $reader = New-Object System.IO.BinaryReader($fs)
    if ($reader.ReadUInt16() -ne 0x5A4D) {
        throw "Not a PE/MZ file"
    }
    [void]$fs.Seek(0x3C, [System.IO.SeekOrigin]::Begin)
    $peOffset = $reader.ReadInt32()
    [void]$fs.Seek($peOffset, [System.IO.SeekOrigin]::Begin)
    if ($reader.ReadUInt32() -ne 0x00004550) {
        throw "Invalid PE signature"
    }
    $machine = $reader.ReadUInt16()
    [void]$fs.Seek($peOffset + 24, [System.IO.SeekOrigin]::Begin)
    $magic = $reader.ReadUInt16()
    "PE Machine: 0x{0:X4}" -f $machine
    "OptionalHeader Magic: 0x{0:X4}" -f $magic
} finally {
    $fs.Dispose()
}
```

**Kết quả máy kiểm thử:**

```text
PE Machine: 0x8664
OptionalHeader Magic: 0x020B
```

Để kiểm tra **DLL thay vì java.exe**, đặt `$path` thành đường dẫn DLL thật. Script này chỉ đọc header, **không nạp hay chạy DLL**; an toàn hơn thử load một binary không đáng tin. `PE32+` cho biết format, còn trường `Machine` là thông tin CPU bắt buộc phải đối chiếu. Thư viện `arm64` có thể có bitness 64 mà vẫn không tương thích với **JVM x86-64**.

### 7.2. Linux: ELF class, machine, NEEDED, symbol versions

```bash
file libnativedoctor.so
readelf -h libnativedoctor.so
readelf -d libnativedoctor.so
readelf --version-info libnativedoctor.so
readelf -Ws libnativedoctor.so | grep Java_NativeLoadDoctor_ping
```

Đọc những trường:

- `Class: ELF64` hoặc `ELF32` — **bitness**, không đồng nghĩa CPU.
- `Machine: Advanced Micro Devices X86-64` / `AArch64` — **CPU architecture**.
- `NEEDED` ở dynamic section — danh sách native libraries mà ELF này cần.
- `RPATH`/`RUNPATH` — đường tìm dependency nhúng trong ELF.
- Version requirements như `GLIBC_2.xx` hay `GLIBCXX_3.4.xx` — mức C/C++ runtime ABI mà binary yêu cầu, có thể không được hệ mục tiêu cung cấp.
- Symbol table xác nhận JNI export tồn tại và có đúng linkage; nếu build với hidden visibility hoặc C++ mangling, export có thể bị thiếu.

`ldd libnativedoctor.so` hữu ích để kiểm tra nơi dependencies được resolve trên một hệ Linux, **nhưng chỉ chạy `ldd` với thư viện đáng tin**, vì một số cơ chế/phiên bản của `ldd` có nguy cơ thực thi code. Khi kiểm tra artifacts chưa tin cậy, ưu tiên static inspection `readelf`/`objdump` và môi trường cô lập.

**glibc vs musl:** cả hai thường dùng tên `.so` và định dạng ELF, nhưng hệ thư viện/runtime ABI khác. Một binary build trong image glibc có thể không chạy trong image Alpine/musl. Dùng đúng base image/toolchain hoặc cung cấp dependency tương thích; đổi tên SO không sửa được libc ABI.

### 7.3. macOS: Mach-O architecture slices và dependencies

```bash
file libnativedoctor.dylib
lipo -archs libnativedoctor.dylib
otool -L libnativedoctor.dylib
nm -gU libnativedoctor.dylib | grep Java_NativeLoadDoctor_ping
```

- `file` cho biết Mach-O format và CPU.
- `lipo -archs` liệt kê slices trong **universal/fat binary**. Cần có slice **trùng process architecture** (arm64 hoặc x86_64).
- `otool -L` liệt kê dependent dylibs và install names.
- `nm -gU` giúp xác nhận exports; C symbol trong Mach-O có thể hiển thị thêm dấu gạch dưới ở đầu theo platform tool.
- Kiểm tra `@rpath`, `@loader_path`, `@executable_path` nếu dynamic loader không tìm được dylib phụ thuộc. macOS còn có các ràng buộc về code signing, quarantine, hardened runtime/SIP tùy tình huống.

Với macOS Apple Silicon, hãy kiểm tra cả JVM đang **arm64** hay **x86_64 qua Rosetta** rồi so với slices trong dylib. Thư viện arm64-only không thể được nạp trực tiếp vào process JVM x86_64 đang chạy qua Rosetta.

## 8. Phân biệt đường tìm thư viện ĐÍCH và thư viện PHỤ THUỘC

Đây là nguyên nhân rất hay bị bỏ sót:

```text
Java
 └── loadLibrary("codec")
       └── JVM tìm libcodec.so / codec.dll
             └── OS loader tìm dependency:
                   ├── libz.so / zlib.dll
                   ├── libstdc++.so.6 / runtime C++
                   └── nativecodechelper.so / helper.dll
```

`java.library.path` giúp JVM tìm **library đích** khi dùng đường tìm theo tên mặc định. Khi OS loader đã mở library đích, **các DLL/SO/dylib phụ thuộc** thường được tìm theo **quy tắc riêng của OS**. Vì vậy sửa `-Djava.library.path` có thể khắc phục `no codec in java.library.path` nhưng **không** khắc phục thiếu `libstdc++.so.6` hoặc `VCRUNTIME140.dll`.

Hướng kiểm tra theo OS:

| OS | Kiểm tra dependencies và đường tìm |
| --- | --- |
| Windows | `dumpbin /dependents`, `where.exe` để khảo sát PATH, OS DLL search order, application directory, hệ thống DLL; lưu ý API load và DLL search flags |
| Linux | `readelf -d` xem `NEEDED/RUNPATH/RPATH`, kiểm tra loader cache `ldconfig -p` khi phù hợp, môi trường `LD_LIBRARY_PATH` và `$ORIGIN`, libc version |
| macOS | `otool -L`, `@rpath/@loader_path`, code signature/quarantine khi liên quan; không phụ thuộc mù quáng vào `DYLD_LIBRARY_PATH` do SIP/hardened runtime |

**Khắc phục bền vững:** package dependencies đúng theo OS/CPU/ABI; dùng app-private library directory hoặc RPATH/RUNPATH hợp lý; kiểm tra version của các runtime dependencies. Không copy DLL có tên gần giống từ nguồn không đáng tin vào `System32`, không tự ý gỡ kiểm tra chữ ký/code signing, và không đổi global PATH khi chỉ một ứng dụng cần cấu hình.

### `System.loadLibrary` so với `System.load`

| Đặc điểm | `System.loadLibrary("nativedoctor")` | `System.load("/abs/path/native.dll")` |
| --- | --- | --- |
| Đầu vào | **Tên logic**, không ghi phần mở rộng/path | **Đường dẫn tuyệt đối** đến binary |
| Quy tắc tìm tệp chính | ClassLoader/Java library search | Đã chỉ ra file chính |
| `System.mapLibraryName` | Có liên quan tới tên native theo OS | Không cần map tên |
| `java.library.path` | Có thể ảnh hưởng việc tìm file chính | Không thay thế đường absolute |
| OS dependent libraries | **Vẫn** theo OS loader | **Vẫn** theo OS loader |
| OS/CPU/bitness/ABI | Phải khớp | Phải khớp |
| JNI/FFM symbol | Vẫn phải có đúng symbols | Vẫn phải có đúng symbols |

Dùng `System.load(absolutePath)` **chỉ để khoanh vùng lỗi tìm file chính**; không coi đó là giải pháp thay thế packaging/ABI/version. Tránh sửa `System.setProperty("java.library.path", ...)` ở runtime rồi giả định classloader sẽ cập nhật search path tức thì: cơ chế có thể đã được cache/khởi tạo trước đó. Ưu tiên cấu hình launcher hoặc loader đúng cách trước khi load.

## 9. ABI và phiên bản: vì sao binary đúng bitness vẫn không tải được?

**ABI (Application Binary Interface)** quy định cách dữ liệu và hàm được trình bày ở mức nhị phân: calling convention, register/stack, layout kiểu và struct, alignment, symbol/linkage, C/C++ runtime compatibility và cơ chế versioned exports. **Đúng 64-bit chưa đủ**.

### 9.1. Windows LLP64 vs Linux LP64

Trên phần lớn Windows x64 (**LLP64**):

- `int` 32-bit, C `long` **32-bit**, pointer và `size_t` **64-bit**.
- JNI `jlong` luôn 64-bit, nhưng **không** map C `long` thành Java `long` một cách mù quáng.

Trên phần lớn Linux x86-64 (**LP64**):

- `int` 32-bit; C `long`, pointer, `size_t` đều **64-bit**.

Một JNI hoặc FFM `FunctionDescriptor` dùng sai return/argument layout có thể **load binary thành công** rồi gây dữ liệu sai/crash **khi gọi**, không nhất thiết ném `UnsatisfiedLinkError` lúc load. `wchar_t`, `long double`, struct padding, C++ vtable/RTTI và calling convention cũng phải đối chiếu C header và compiler/ABI mục tiêu.

### 9.2. JNI symbol name, export và `RegisterNatives`

Với Java:

```java
private static native int ping();
```

Header sinh ra `Java_NativeLoadDoctor_ping(JNIEnv*, jclass)`. Nếu C triển khai `Java_OldClass_ping`, đổi package, đổi JNI signature hoặc để C++ compiler mangle tên, Java có thể load library nhưng thất bại ở **native method binding**.

Cách kiểm tra:

- Dùng `javac -h` để tạo header **từ source Java hiện tại**.
- Dùng `dumpbin /exports`, `nm -D` / `readelf -Ws` hoặc `nm -gU` để xem **export thực tế**.
- Khi dùng `RegisterNatives` thay tên JNI suy diễn, đối chiếu **method name** và **descriptor** chính xác, ví dụ `()I` cho `int ping()`; mã đăng ký phải thực sự chạy thành công.
- Kiểm tra `JNIEXPORT`, `JNICALL`, `extern "C"` (nếu C++), toolchain và compiler options ẩn symbols.
- Với Java module/JDK hiện đại, native method binding có thể còn chịu **native-access restrictions**; phân biệt denial `IllegalCallerException` với loader's `UnsatisfiedLinkError`.

### 9.3. JNI API version và `JNI_OnLoad`

`JNI_OnLoad(JavaVM*,void*)` được JVM gọi khi load JNI library có export này. Nó phải trả một `JNI_VERSION_*` mà JVM hỗ trợ. Ví dụ `JNI_VERSION_1_8` tương thích JDK 17+. Nếu `JNI_OnLoad` trả một version code không được nhận diện, JVM từ chối thư viện và xử lý như load thất bại, **dù OS/CPU/bitness đã khớp**.

**Không nhầm ba loại “version”:**

1. **JNI API version:** `JNI_VERSION_1_8`, `JNI_VERSION_9`, `JNI_VERSION_10` ... là phiên bản **interface** giữa JVM và native library.
2. **Native library/application ABI version:** ví dụ API của `libcodec.so.2` hoặc symbol của `codec.dll` — do thư viện quyết định, có thể phá tương thích nếu đổi hàm/struct.
3. **OS C/C++ runtime ABI version:** ví dụ các versioned symbols `GLIBC_2.xx`, `GLIBCXX_3.4.xx` trên Linux, hoặc yêu cầu MSVC/UCRT runtime trên Windows.

Việc dùng `JNI_VERSION_1_8` **không bảo đảm** binary biên dịch trên Linux glibc mới sẽ chạy trên Alpine/musl, hoặc MSVC DLL mới sẽ có runtime phụ thuộc trên một máy Windows khác.

### 9.4. C++ và versioned symbols

C++ name mangling, compiler ABI, `libstdc++` vs `libc++`, compiler toolset, visibility flags và các C++ exceptions qua FFI boundary đều có thể gây lỗi. Với API exported cho JNI/FFM, nên thiết kế một **C ABI ổn định**, bọc C++ implementation bằng `extern "C"` và tránh truyền trực tiếp STL types/vtables qua boundary.

Nếu Linux báo:

```text
version 'GLIBCXX_3.4.xx' not found
```

Lỗi là **phiên bản libstdc++ runtime**, không phải kiểu dữ liệu Java hay bitness. Hãy kiểm tra `readelf --version-info`, phiên bản runtime thực được OS loader chọn, rồi build trên baseline distro tương thích hoặc đóng gói dependency đúng theo chính sách sản phẩm. Không sửa bằng cách chép bừa `libstdc++.so.6` vào thư mục hệ thống.

**ARM64/x86_64 cùng 64-bit cũng không cùng ABI**. Bitness chỉ là một phần của binary compatibility.

## 10. Ma trận lỗi phổ biến và hướng chẩn đoán

| Triệu chứng (ví dụ) | Giai đoạn | Gợi ý nguyên nhân | Bước tiếp theo |
| --- | --- | --- | --- |
| `no nativedoctor in java.library.path` | JVM tìm file chính | Chưa có file hoặc search path sai | `System.mapLibraryName`, classloader, `-Djava.library.path`, artifact packaging |
| `Can't load library: /abs/path/...` | `System.load` | File chính không tồn tại, path/permissions sai, hoặc loader không mở được | Kiểm tra file thực, quyền và thông báo OS |
| `wrong ELF class: ELFCLASS32` | OS ELF loader | JVM 64-bit thử nạp ELF 32-bit | `readelf -h` + kiến trúc JVM |
| `wrong ELF class: ELFCLASS64` | OS ELF loader | Process 32-bit thử nạp ELF 64-bit | Chọn artifact 32-bit hoặc JVM 64-bit tương ứng |
| `%1 is not a valid Win32 application` / OS error 193 | Windows loader | Có thể sai format/machine/bitness hoặc file không phải DLL hợp lệ | `dumpbin /headers`, machine và PE32/PE32+ |
| `mach-o file, but is an incompatible architecture` | macOS dyld | Dylib thiếu slice trùng JVM | `lipo -archs`, xác định Rosetta/process CPU |
| `The specified module could not be found` dù DLL chính tồn tại | Windows loader | Có thể thiếu một DLL phụ thuộc | `dumpbin /dependents`, OS DLL search path |
| `libcodec.so: cannot open shared object file` | Linux loader | Đường tìm target/dependency chưa đúng | `readelf -d`, `LD_LIBRARY_PATH`, `RUNPATH` |
| `undefined symbol: ...` | Dynamic linker | Thiếu export hoặc ABI/dependency sai | `nm`, `readelf -Ws`, runtime dependency |
| `GLIBC_2.xx not found` / `GLIBCXX_3.4.xx not found` | ELF symbol versions | glibc/libstdc++ runtime thấp hơn yêu cầu | So baseline build và deployed runtime |
| `UnsatisfiedLinkError: ...NativeLoadDoctor.ping()I` | JNI native method binding | DLL đã nạp nhưng thiếu symbol/registration | `javac -h`, `dumpbin /exports`, `RegisterNatives` |
| `JNI_OnLoad returned invalid JNI version` | JNI init | Native yêu cầu JNI version không được VM hỗ trợ | Kiểm tra `JNI_OnLoad` và JDK target |
| `Native Library ... already loaded in another classloader` | JNI classloader | Một JNI lib cố được load trong hai classloaders | Chọn classloader owner duy nhất hoặc thiết kế lại lifecycle |
| `IllegalCallerException` trên JDK 24+ | Native access policy | Module chưa có quyền restricted JNI/FFM | `--enable-native-access=<module>`, rà `--illegal-native-access` |
| Load thành công, gọi native rồi `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION` | Khi chạy native | Sai ABI/calling convention/pointer/lifetime | Header, alignment, native debugger/ASan |
| Load thành công, gọi native rồi `SIGILL` | Khi chạy native | Binary dùng CPU instruction không được CPU thực hỗ trợ | So CPU flags/compile target như AVX2 |

**Thông điệp thực tế khác nhau theo OS/JDK vendor:** bảng trên là dấu hiệu gợi ý, không phải một phép ánh xạ 1–1 chắc chắn. Ví dụ Windows error 193 có thể là binary format hỏng chứ không chỉ “sai 32/64-bit”. Đọc toàn bộ cause chain và loader diagnostics trước khi kết luận.

## 11. Quy trình debug lặp lại được trên máy local và CI

### Bước 1 — Chốt đúng process và lỗi

Ghi nhận lệnh `java` thực tế, `java -version`, `os.name`, `os.arch`, `sun.arch.data.model` nếu có, OS/container image, và **stack trace / exact error message**. Nếu ứng dụng đang chạy qua Gradle, Maven, IDE hay Docker, chạy probe **trong môi trường đó**, không chỉ trên terminal cá nhân.

### Bước 2 — Chỉ ra file native cụ thể đang được nạp

Từ tên `System.loadLibrary("codec")`, dự đoán `System.mapLibraryName("codec")` rồi tìm **file thực**. Nếu ứng dụng dùng file nén trong JAR, kiểm tra code **extract-to-temp** và đường dẫn có được đặt đúng trước khi load không. Nếu dùng `System.load(absolutePath)`, xác minh chính đường dẫn đó. Không chỉnh `java.library.path` khi lỗi thuộc OS dependent loader.

### Bước 3 — Kiểm tra OS/format/CPU/bitness không load binary

Trên Windows dùng `dumpbin /headers` hoặc PowerShell PE header; Linux dùng `readelf -h` và `file`; macOS dùng `file`/`lipo -archs`. Đối chiếu **process ABI** chứ không chỉ host hardware. Nếu mismatch: chọn artifact có variant trùng JVM hoặc build lại bằng đúng toolchain target.

### Bước 4 — Liệt kê các native dependencies và runtime symbol versions

Dùng `dumpbin /dependents`, `readelf -d / --version-info`, `otool -L`. Đối chiếu các DLL/SO/dylib con **tại nơi chạy thật**; kiểm tra libc/libstdc++/UCRT và OS search policy. Đừng sửa lỗi này bằng classpath Java, vì Java classpath chỉ chứa classes/JARs.

### Bước 5 — Chốt JNI symbol và API version

Sinh header lại bằng `javac -h`; so sánh `Java_<class>_<method>`, signatures, `JNIEXPORT`, `JNICALL`, `RegisterNatives` và `JNI_OnLoad`. Nếu `System.loadLibrary` đã thành công nhưng native method call fail, bắt đầu từ **export/binding** thay vì build lại mọi thư viện.

### Bước 6 — Sửa đúng lớp nguyên nhân và xác minh lại

- Sai OS/CPU/bitness: phân phối library variant đúng, không rename.
- Sai dependency hoặc runtime ABI version: thay môi trường chạy/dependency hoặc build trên baseline tương thích.
- Sai JNI symbol: sửa C function prototype/export hoặc registration; build lại.
- Sai FFM ABI: sửa `FunctionDescriptor` theo C header; thêm kiểm thử native call.
- Sai quyền native access: cấp quyền đúng module trên JDK hỗ trợ.
- Cùng một JNI lib bị load trong nhiều classloaders: sửa ownership/classloader lifecycle.

Sau đó chạy lại đúng command trong CI và production-like image. Chỉ coi thành công khi **thư viện tải được, symbol được liên kết và lời gọi smoke-test chạy đúng**.

## 12. Build/release: chọn artifact đúng platform thay vì một file chung

Một bản phát hành Java cross-platform thường cần **nhiều native artifacts**. Ví dụ mô hình đặt thư viện theo variant:

```text
app.jar
native/
  windows-x86_64/nativedoctor.dll
  windows-aarch64/nativedoctor.dll
  linux-x86_64-glibc/libnativedoctor.so
  linux-aarch64-glibc/libnativedoctor.so
  linux-x86_64-musl/libnativedoctor.so
  macos-aarch64/libnativedoctor.dylib
  macos-x86_64/libnativedoctor.dylib
```

**Đây là cấu trúc package minh họa, không có nghĩa mọi project bắt buộc ship tất cả variants.** Chọn các platform được sản phẩm hỗ trợ và kiểm thử. Với macOS có thể dùng universal binary chứa cả arm64/x86_64 slices, nhưng vẫn phải kiểm tra dependent dylibs cho **từng slice**.

Metadata release hữu ích:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `os` | Windows/Linux/macOS |
| `arch` | x86_64/aarch64/x86… |
| `bits` | 32/64 |
| `binaryFormat` | PE/ELF/Mach-O |
| `cAbi` | LLP64/LP64/ILP32 theo platform |
| `libcOrCrt` | glibc/musl/MSVC CRT version policy |
| `jniApi` | Version JNI API tối thiểu nếu thư viện phụ thuộc |
| `nativeAbiVersion` | Version của giao diện C do thư viện công bố |
| `dependencies` | Native libraries và version requirements |
| `checksums` | Phát hiện hỏng binary/nhầm artifact |

Một kiểm thử CI nên bao gồm: Java process OS+CPU+bitness → binary header → native dependencies → `System.loadLibrary`/`System.load` smoke test → native symbol call → ABI/data roundtrip. Test các failure conditions trong **process riêng** vì sai native ABI có thể crash JVM; không chạy intentionally malformed/mismatch binaries trong server production.

### Cross-compile không đồng nghĩa đã test runtime

Một Linux host có thể cross-compile binary Windows ARM64 hoặc Linux AArch64, nhưng bản build chỉ chứng minh compiler đã tạo file. **Vẫn cần runtime tests trên đúng OS/CPU (hoặc môi trường emulation được hỗ trợ và xác nhận)**. Java unit tests không gọi native code không thể phát hiện thiếu DLL con, symbol version mismatch hay sai calling convention.

## 13. Checklist cuối trước khi chốt lỗi

- [ ] Xác định **đúng Java process** bằng `java -version` và application launcher thực.
- [ ] Ghi nhận `os.name`, `os.arch`, process bitness (biết `sun.arch.data.model` không portable).
- [ ] Kiểm tra library **file thực** thay vì dựa trên extension hoặc tên JAR.
- [ ] OS format khớp PE/ELF/Mach-O.
- [ ] CPU ISA và bitness khớp JVM process; không chỉ khớp host OS.
- [ ] Đã kiểm tra case x86_64/AMD64 và AArch64/ARM64 alias, Rosetta/container.
- [ ] Header/loader tools cho biết CPU, PE magic/ELF class/Mach-O slices.
- [ ] Đúng các native dependencies, OS search path và C/C++ runtime versions.
- [ ] Đúng ABI: calling convention, C `long`, `size_t`, struct layout và alignment.
- [ ] `javac -h` tạo header cho Java source hiện tại; C có export/`RegisterNatives` đúng.
- [ ] `JNI_OnLoad` chỉ yêu cầu JNI version JVM hỗ trợ.
- [ ] Không có classloader ownership conflict cho JNI library.
- [ ] Không nhầm `--enable-native-access` với sửa lỗi CPU/ABI/format.
- [ ] Không tải DLL/SO từ nguồn không tin cậy để “thử xem có hết lỗi không”.
- [ ] Đã chạy end-to-end native smoke test trong CI với đúng image/OS/JVM target.

## 14. Bài tập và câu hỏi tự kiểm tra

1. Máy chạy Windows 64-bit nhưng `sun.arch.data.model=32`; bạn cần build DLL bao nhiêu bit cho JVM?
2. Linux Java x86-64 báo `wrong ELF class: ELFCLASS32`. Bạn kiểm tra hai file/header nào trước khi sửa code Java?
3. Mac Apple Silicon đang chạy Java `os.arch=x86_64` qua Rosetta. Dylib arm64-only có phù hợp không?
4. Vì sao `System.load(absolutePath)` giúp loại trừ một phần `java.library.path` nhưng **không loại trừ** lỗi missing dependencies?
5. `dumpbin /headers` báo `Machine: 0xAA64` và `PE32+`. Một JVM `amd64` chạy trên Windows ARM64 có thể nạp DLL này trực tiếp không?
6. `System.loadLibrary` báo load OK, nhưng Java gọi `native int ping()` bị `UnsatisfiedLinkError`. Công cụ và metadata nào cần xem?
7. Vì sao `JNI_OnLoad` trả JNI version sai có thể làm library load fail dù OS/CPU/bitness đều đúng?
8. C `long` trên Windows x64 và Linux x86-64 có cùng width không? Tác động tới FFM descriptor thế nào?
9. Tại sao một chương trình có thể load đúng thư viện nhưng crash `SIGILL` khi gọi native function?
10. Môi trường Alpine/musl không nạp được ELF build trên glibc dù cùng x86-64/ELF64. Bạn kiểm tra gì?
11. `jnativescan` hay `--enable-native-access` có giải quyết `wrong ELF class` không? Vì sao?
12. Một JAR hoạt động trong IDE nhưng không chạy trong Docker: những trường nào cần so sánh trước tiên?
13. Vì sao không nên coi **exit code 0** của demo chuyên bắt `UnsatisfiedLinkError` là bằng chứng load thành công?
14. Khi thấy một lỗi loader, bạn sẽ xác định nó thuộc **search path**, **binary format**, **dependency**, **JNI initialization**, hay **JNI method binding** bằng những dấu hiệu nào?

**Ghi nhớ:** Khi nạp native library thất bại, lần lượt đối chiếu **OS/format → kiến trúc CPU của JVM process → bitness → native dependencies và ABI versions → JNI/FFM exports/signatures**. Giữ nguyên thông báo lỗi để phân biệt *không tìm thấy file*, *file sai kiến trúc*, *dependency thiếu/sai version* và *native method chưa được liên kết*. Một tên thư viện đúng và JVM 64-bit không chứng minh ABI tương thích.

### Tài liệu chính thức và đọc thêm

- [Oracle JDK 24 — JNI Design Overview: native loading, method naming và linkage](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html).
- [Oracle JDK 24 — JNI Invocation API: classloader, JNI_OnLoad, JNI versions](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html).
- [Oracle JDK 24 — ClassLoader.findLibrary và java.library.path](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ClassLoader.html).
- [Oracle JDK 24 — Runtime.load: absolute library path](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Runtime.html).
- [Oracle JDK 24 — javac: -h header generation](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html).
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).
- [Microsoft Learn — /HEADERS (DUMPBIN)](https://learn.microsoft.com/en-us/cpp/build/reference/headers?view=msvc-170).
- [Microsoft Learn — /DEPENDENTS (DUMPBIN)](https://learn.microsoft.com/en-us/cpp/build/reference/dependents?view=msvc-170).
- [Linux man-pages — ld.so(8): ELF loader và dependencies](https://man7.org/linux/man-pages/man8/ld.so.8.html).
- [Apple — Dynamic Library Programming Topics](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/000-Introduction/Introduction.html).
