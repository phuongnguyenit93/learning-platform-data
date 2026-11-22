# Chạy ma trận JDK, hệ điều hành, CPU và công cụ biên dịch được hỗ trợ

Khi ứng dụng Java gọi thư viện bản địa bằng **JNI (Java Native Interface)** hoặc **Foreign Function & Memory API (FFM)**, phần Java có thể biên dịch và chạy trên nhiều nền tảng, còn phần C/C++ đã được dịch sang mã máy phụ thuộc **hệ điều hành, CPU, ABI và công cụ biên dịch**. Do đó, một lần `javac` thành công hoặc một bài test chạy trên máy lập trình viên **không chứng minh** thư viện native hoạt động trên toàn bộ môi trường được công bố hỗ trợ.

**Mục tiêu:** xác định các trục của ma trận tương thích; chọn các tổ hợp JDK/OS/CPU/compiler có ý nghĩa; thiết kế kiểm thử build, load, ABI và hành vi; chạy JNI smoke test thực tế trên nhiều nền tảng; tự động hóa CI; diễn giải kết quả và quyết định lúc nào đủ chứng cứ phát hành. Những JDK/OS được liệt kê dưới đây là **ví dụ về chính sách hỗ trợ**, không tự động là danh sách hỗ trợ của một sản phẩm cụ thể.

## 1. Một ô trong ma trận tương thích đại diện cho điều gì?

Một case native tương ứng với tuple:

`(JDK vendor + version + patch, OS + OS version + libc, CPU + native ABI, compiler + version + flags, build type, native artifact version)`.

| Trục | Ví dụ | Rủi ro nếu không kiểm tra |
| --- | --- | --- |
| **JDK** | Temurin 17, 21, 25; patch `17.0.x` | Java classfile/API, JNI/FFM behavior, module policy, runtime native access |
| **OS** | Ubuntu 24.04, Windows Server 2022, macOS 15 | ELF/PE/Mach-O, loader, library dependencies, minimum supported OS |
| **CPU** | AMD64/x86-64, AArch64/arm64 | Instruction set, calling convention, alignment, endianness, native binary architecture |
| **ABI / data model** | LP64, LLP64; glibc, musl | C `long`/`size_t`, struct layout, symbol names, ABI compatibility |
| **Compiler** | GCC, LLVM Clang, Apple Clang, MSVC | Compiler flags, optimizations, standard-library/CRT compatibility |
| **Build mode** | Debug, Release, sanitizer variants | Optimization-dependent undefined behavior, instrumented runtime requirements |
| **Phân phối** | `libfoo.so`, `foo.dll`, `libfoo.dylib` | Packaging, dependency, code signing, search path, installed artifact |

Cần phân biệt bốn bằng chứng:

1. **Compile Java:** `javac` chứng minh source phù hợp một Java release/API nhất định.
2. **Compile/link native:** C/C++ compiler và linker tạo được thư viện cho target OS/CPU/ABI cụ thể.
3. **Load/link lúc chạy:** JVM cùng OS loader tìm được thư viện, các phụ thuộc và symbol JNI/FFM.
4. **Execute + assert:** một JVM thực sự gọi native code và nhận kết quả đúng; kiểm tra thêm layout, memory ownership, lỗi biên, concurrency.

**Cross-compile cho arm64 từ máy x64 mới chỉ chứng minh build**, chưa chứng minh thư viện thực thi được trên CPU arm64. Nếu dùng emulator, ghi rõ đó là **emulation evidence**; với target quan trọng cần xác minh trên hardware/runner phù hợp.

## 2. Chọn tổ hợp được hỗ trợ trước khi nhân ma trận

Chỉ xây dựng những tuple **hợp lệ và có ý nghĩa**: không ghép MSVC để build thư viện ELF trên Linux theo quy trình thông thường; cũng không tuyên bố hỗ trợ Linux/arm64 chỉ vì Linux/x64 đã pass. Giả sử có yêu cầu kiểm thử JNI trên **JDK 17, 21, 25**, các môi trường mẫu có thể là:

| Target | Runner GitHub-hosted mẫu | CPU | Compiler | `sizeof(long)` dự kiến trên target 64-bit |
| --- | --- | --- | --- | --- |
| Linux/glibc | `ubuntu-24.04` | x64 | GCC | 8 (LP64) |
| Linux/glibc | `ubuntu-24.04` | x64 | Clang | 8 (LP64) |
| Linux/glibc | `ubuntu-24.04-arm` | arm64 | GCC | 8 (LP64) |
| Windows | `windows-2022` | x64 | MSVC/Visual Studio 2022 | 4 (LLP64) |
| macOS | `macos-15` | arm64 | Apple Clang | 8 (LP64) |
| macOS | `macos-15-intel` | x64 | Apple Clang | 8 (LP64) |

Có **3 JDK × 6 target = 18 jobs** cho JNI smoke test. Các runner labels là ví dụ dựa trên GitHub-hosted runners và có thể đổi theo thời gian hoặc quyền dùng repository. Đọc thông tin runner và toolchain **thực tế trong job**, tránh suy diễn từ `-latest`.

**JNI và FFM có phạm vi JDK khác nhau:** JNI dùng được trên các JDK 17/21/25 trong ví dụ. API `java.lang.foreign` của FFM trở thành API chính thức từ **JDK 22**; bài kiểm thử sử dụng FFM API chính thức phải chạy trên JDK ≥22 tương thích. Không áp dụng Java FFM source dành cho JDK 22+ vào `javac` của JDK 17/21 rồi xem lỗi compile là lỗi native ABI.

Nếu hỗ trợ **Alpine/musl**, phải có target musl riêng: Linux/glibc x64 không chứng minh tương thích với Linux/musl x64. Nếu hỗ trợ **Windows/arm64**, **macOS/x64**, phiên bản OS tối thiểu hoặc CPU-specific optimizations, tất cả cần có chứng cứ theo target thực sự.

## 3. Tại sao data model và compiler quan trọng?

Java `long` luôn là 64-bit signed integer; C `long` thay đổi theo ABI phổ biến:

| Kiểu | Linux/macOS 64-bit (LP64) | Windows 64-bit (LLP64) |
| --- | --- | --- |
| `int` | 32 bit | 32 bit |
| `long` | 64 bit | 32 bit |
| `long long` | 64 bit | 64 bit |
| `void*`, `size_t` | Thường 64 bit | Thường 64 bit |
| JNI `jint` / `jlong` | 32 / 64 bit | 32 / 64 bit |

Vì vậy không khai báo Java `long` hoặc FFM `ValueLayout.JAVA_LONG` cho một hàm C chỉ dựa vào tên `long`. Với JNI, các kiểu `jint` và `jlong` có độ rộng xác định; với FFM cần mapping theo header, C ABI và `Linker.nativeLinker().canonicalLayouts()` ở những API áp dụng. Với struct-by-value, callback, varargs, alignment, signedness, kiểu trả về và lifetime, sai khác có thể dẫn đến kết quả sai hoặc crash JVM.

Các khác biệt ngoài kích thước kiểu:

- **x64 vs arm64:** calling convention, layout/alignment, vector instructions, architecture-specific intrinsics khác nhau; không chạy binary x64 như native arm64 chỉ bằng cách đổi tên tệp.
- **GCC vs Clang:** khác code generation, tối ưu hóa, warnings, extensions; undefined behavior C/C++ có thể chỉ lộ trên một compiler hoặc ở Release.
- **MSVC vs MinGW:** cùng Windows nhưng có thể khác compiler/CRT/C++ ABI và dependent libraries; không trộn C++ objects hoặc allocator ownership tùy tiện.
- **macOS:** Xcode/Apple Clang, minimum deployment target, Mach-O architecture, universal binary slices và chính sách signing có thể ảnh hưởng việc load.
- **Linux:** phiên bản glibc, musl, `libstdc++`/`libc++`, `RPATH`/`RUNPATH` và dependent `.so` là một phần của compatibility.
- **Distribution JDK:** test bản được support (vendor/build/patch) và ghi `java -version`, vì `--release` kiểm tra Java API/classfile chứ không bảo đảm hành vi của JVM/native loader.

## 4. Ví dụ đầy đủ: Java 17+ gọi JNI qua thư viện C

Để có một điểm kiểm tra **thực sự** trên mỗi OS/CPU/compiler, ta dùng hai hàm native:

- `add(7, 5)` nhận/trả JNI `jlong` và phải trả `12` ở mọi target.
- `cLongBytes()` dùng **chính compiler C trên target** đo `sizeof(long)`. Trên Linux/macOS x64/arm64 LP64 kỳ vọng `8`, Windows/x64 LLP64 kỳ vọng `4`.

Cấu trúc project độc lập:

~~~text
jni-matrix-demo/
├── CMakeLists.txt
├── src/demo/nativebridge/NativeMath.java
├── native/nativemath.c
├── .github/workflows/native-compatibility.yml
├── headers/       # tạo từ javac -h
├── out/           # tạo từ javac -d
└── build/         # tạo từ CMake
~~~

### 4.1. Java source — `src/demo/nativebridge/NativeMath.java`

~~~java
package demo.nativebridge;

import java.util.Locale;

public final class NativeMath {
    private NativeMath() {
    }

    static {
        System.loadLibrary("nativemath");
    }

    private static native long add(long left, long right);
    private static native int cLongBytes();

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: NativeMath <c-long-bytes> <x64|arm64>");
        }

        int expectedBytes = Integer.parseInt(args[0]);
        String expectedCpu = args[1];
        String actualArch = System.getProperty("os.arch", "")
                .toLowerCase(Locale.ROOT);

        boolean cpuMatches = switch (expectedCpu) {
            case "x64" -> actualArch.equals("amd64")
                    || actualArch.equals("x86_64");
            case "arm64" -> actualArch.equals("aarch64")
                    || actualArch.equals("arm64");
            default -> throw new IllegalArgumentException(
                    "Unknown expected CPU: " + expectedCpu);
        };

        if (!cpuMatches) {
            throw new AssertionError("Expected CPU " + expectedCpu
                    + " but JVM reports " + actualArch);
        }

        long result = add(7, 5);
        int actualBytes = cLongBytes();
        if (result != 12 || actualBytes != expectedBytes) {
            throw new AssertionError("JNI/ABI mismatch: result=" + result
                    + ", C long bytes=" + actualBytes
                    + ", expected=" + expectedBytes);
        }

        System.out.println("PASS sum=12; C long=" + actualBytes
                + " bytes; CPU=" + expectedCpu);
    }
}
~~~

`System.loadLibrary("nativemath")` tìm tên thư viện phù hợp target: thông thường `libnativemath.so` (Linux), `nativemath.dll` (Windows), `libnativemath.dylib` (macOS). `System.mapLibraryName("nativemath")` cho biết tên được Java ánh xạ; **loader còn phải tìm được phụ thuộc native**. `os.arch` là thuộc tính kiến trúc JVM, được kiểm tra chủ động với CPU kỳ vọng từ CI matrix.

### 4.2. Sinh header JNI trực tiếp từ Java source

Chạy ở thư mục gốc, với JDK 17+ và shell có `mkdir -p`:

~~~bash
mkdir -p headers out
javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java
~~~

`javac -h` sinh `headers/demo_nativebridge_NativeMath.h`. Mỗi lần đổi `native` declarations phải sinh lại header để tránh sai tên symbol, parameter/calling convention. `--release 17` khóa khả năng sử dụng Java API/classfile ở mức Java 17 trên JDK 17/21/25; nó **không ảnh hưởng ABI nhị phân C của target**.

### 4.3. C source — `native/nativemath.c`

~~~c
#include "demo_nativebridge_NativeMath.h"

JNIEXPORT jlong JNICALL
Java_demo_nativebridge_NativeMath_add(
        JNIEnv *env, jclass cls, jlong left, jlong right) {
    (void) env;
    (void) cls;
    return left + right;
}

JNIEXPORT jint JNICALL
Java_demo_nativebridge_NativeMath_cLongBytes(
        JNIEnv *env, jclass cls) {
    (void) env;
    (void) cls;
    return (jint) sizeof(long);
}
~~~

Vì hai phương thức Java là `static native`, tham số receiver ở C là `jclass`. Các macro `JNIEXPORT` và `JNICALL` do JNI headers cung cấp giúp xuất symbol/calling convention chính xác trên target. `jlong` của JNI khác với C `long`, nên test có thể kiểm tra thực sự sự khác biệt LP64/LLP64. Ví dụ cộng số nhỏ để tránh signed overflow C; với thư viện thật cần quy định behavior tại biên kiểu dữ liệu.

### 4.4. CMake — `CMakeLists.txt`

~~~cmake
cmake_minimum_required(VERSION 3.24)
project(jni_matrix LANGUAGES C)

find_package(JNI REQUIRED COMPONENTS JVM)

add_library(nativemath SHARED native/nativemath.c)
target_include_directories(nativemath PRIVATE
    "${PROJECT_SOURCE_DIR}/headers"
    ${JNI_INCLUDE_DIRS}
)

set_target_properties(nativemath PROPERTIES
    C_STANDARD 11
    C_STANDARD_REQUIRED YES
)
~~~

CMake `FindJNI` tìm các headers như `jni.h` và `jni_md.h`, nhận `JAVA_HOME` làm gợi ý để chọn JDK; ở đây không cần liên kết một JVM thứ hai vào library. `COMPONENTS JVM` tránh phụ thuộc AWT không liên quan. Đảm bảo toolchain thực sự là compiler của target; `add_library(... SHARED ...)` sinh loại thư viện phù hợp với nền tảng.

### 4.5. Lệnh chạy trên Linux/macOS và Windows

Linux/macOS x64, sau khi sinh header:

~~~bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
java -Djava.library.path=build -cp out demo.nativebridge.NativeMath 8 x64
~~~

Kết quả kỳ vọng khi đang chạy **Linux/macOS x64 LP64**:

~~~text
PASS sum=12; C long=8 bytes; CPU=x64
~~~

Với Linux/macOS arm64, thay `8 x64` thành `8 arm64`. Trên **JDK 24+**, dùng `--enable-native-access=ALL-UNNAMED` với JNI classpath để cấp quyền một cách tường minh:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=build -cp out demo.nativebridge.NativeMath 8 arm64
~~~

Lệnh cuối chỉ chạy thành công khi JVM thực sự báo `arm64/aarch64`; trên x64 phải thay `arm64` thành `x64`.

Windows/x64 với **Visual Studio 2022 C++ build tools** và **JDK 25**, chạy PowerShell:

~~~powershell
New-Item -ItemType Directory -Force headers,out | Out-Null
javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
java --enable-native-access=ALL-UNNAMED -Djava.library.path=build/Release -cp out demo.nativebridge.NativeMath 4 x64
~~~

Kết quả kỳ vọng ở Windows/x64:

~~~text
PASS sum=12; C long=4 bytes; CPU=x64
~~~

Với JDK 17/21 trên Windows, có thể chạy lệnh Java tương ứng **không có** `--enable-native-access`. CMake Visual Studio generator thường xuất `nativemath.dll` vào `build/Release`; còn Ninja hoặc single-config generator có thể tạo đường dẫn khác. Hãy kiểm tra output thật thay vì gắn cố định một đường dẫn cho mọi generator.

**Giới hạn của fixture:** hai phép assert chứng minh một phần JNI/ABI load path và native execution. Nó chưa kiểm chứng struct padding, C++ ABI, buffer overflow, callback, ownership, race, dependency đóng gói hay security của thư viện khác.

## 5. Ma trận CI 18 jobs bằng GitHub Actions

Ví dụ workflow dưới đây chạy **3 JDK × 6 platform/compiler target** từ mục 2. Cần repository có quyền dùng runner labels, có CMake và compiler tương ứng trên image, và JDK Temurin cho CPU đã chọn. Các labels phải đối chiếu danh sách runner hiện hành trước khi sử dụng.

Tạo `.github/workflows/native-compatibility.yml`:

~~~yaml
name: Native compatibility

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  jni-smoke:
    name: "${{ matrix.platform.name }} / JDK ${{ matrix.jdk }}"
    runs-on: ${{ matrix.platform.runner }}
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']
        platform:
          - { name: linux-x64-gcc, runner: ubuntu-24.04, cc: gcc, cpu: x64, c_long: 8 }
          - { name: linux-x64-clang, runner: ubuntu-24.04, cc: clang, cpu: x64, c_long: 8 }
          - { name: linux-arm64-gcc, runner: ubuntu-24.04-arm, cc: gcc, cpu: arm64, c_long: 8 }
          - { name: windows-x64-msvc, runner: windows-2022, cc: none, cpu: x64, c_long: 4 }
          - { name: macos-arm64-clang, runner: macos-15, cc: none, cpu: arm64, c_long: 8 }
          - { name: macos-x64-clang, runner: macos-15-intel, cc: none, cpu: x64, c_long: 8 }

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}

      - name: Compile Java and JNI header
        shell: bash
        run: |
          java -version
          javac -version
          cmake --version
          mkdir -p headers out
          javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java

      - name: Compile native library
        shell: bash
        run: |
          if [ "$RUNNER_OS" = "Windows" ]; then
            cmake -S . -B build -G "Visual Studio 17 2022" -A x64
          elif [ "$RUNNER_OS" = "Linux" ]; then
            cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
              -DCMAKE_C_COMPILER=${{ matrix.platform.cc }}
          else
            cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
          fi
          cmake --build build --config Release

      - name: Exercise native library on target
        shell: bash
        run: |
          libdir=build
          if [ "$RUNNER_OS" = "Windows" ]; then
            libdir=build/Release
          fi

          native_access=()
          if [ "${{ matrix.jdk }}" -ge 24 ]; then
            native_access=(--enable-native-access=ALL-UNNAMED)
          fi

          java "${native_access[@]}" \
            -Djava.library.path="$libdir" \
            -cp out demo.nativebridge.NativeMath \
            ${{ matrix.platform.c_long }} ${{ matrix.platform.cpu }}
~~~

Giải nghĩa những phần quan trọng:

- `matrix.jdk` tạo ba JDK; `matrix.platform` chứa sáu **tổ hợp hợp lệ** OS/CPU/compiler (Linux/x64 có hai compiler). Mỗi tổ hợp của hai danh sách tạo một job.
- `runs-on` chọn **runner target**, không chỉ chọn tệp output. `ubuntu-24.04-arm` và `macos-15` ở đây là runner arm64; `macos-15-intel` là runner x64.
- `actions/setup-java` đặt Java trên runner. `javac --release 17` xây Java API dùng chung, còn C được build trong từng target/compiler.
- Windows chọn `Visual Studio 17 2022 -A x64`. Linux GCC/Clang khác nhau qua `CMAKE_C_COMPILER`; Apple Clang được dùng trong macOS runner.
- Bước chạy truyền expected `sizeof(long)` và CPU. Nếu kiến trúc JVM không khớp hoặc C ABI sai, Java ném `AssertionError` khiến job fail.
- JDK 24+ bật quyền native cho classpath để đáp ứng JNI restricted operation policy. Với named module, sản phẩm thật có thể dùng `--enable-native-access=<module>` để cấp hẹp hơn.
- `fail-fast: false` giữ các target độc lập chạy hết để có báo cáo đầy đủ. **Không** dùng `continue-on-error` cho target được cam kết hỗ trợ; một target fail phải làm kiểm thử tổng thể fail.

CI ví dụ chưa pin **compiler patch version** hoặc runner image revision. Để phát hành lặp lại được, lưu `java -version`, CMake compiler identification/version, runner image revision, native dependencies, build flags, commit SHA và binary hash. Label `ubuntu-24.04` không bảo đảm compiler version cố định mãi mãi.

## 6. Phải có ma trận riêng cho FFM và các chính sách JDK mới

JNI là API đã tồn tại lâu; còn FFM ở `java.lang.foreign` được chuẩn hóa ở **JDK 22**. Các test FFM cần bao phủ:

| Nội dung | Vì sao cần chạy riêng |
| --- | --- |
| `Linker.nativeLinker()`/`SymbolLookup` | Tìm symbol và tạo downcall handle theo ABI của target |
| `FunctionDescriptor` | Số lượng, carrier Java và kiểu C phải đúng prototype/ABI |
| `canonicalLayouts()` | Độ rộng C `long`, `size_t`, layout theo ABI hiện hành |
| `MemorySegment`/`Arena` | Lifetime, allocation, alignment, bounds và thread confinement |
| Struct/union/pointer | Padding, signedness, nullability, ownership và return-by-value ABI |
| Callback/upcall | Calling convention, callback reference/lifetime, thread, exceptions |
| Native access | JDK 24+ JNI load/link, restricted FFM operations và module permissions |

Không dùng FFM source chính thức JDK22+ trong job JDK17/21. Nếu sản phẩm hỗ trợ JDK 25 và các JDK mới hơn, chỉ thêm những phiên bản đã được xác nhận API/runtime có thể sử dụng.

**JDK 24** bắt đầu chính sách cảnh báo native access khi JNI nạp/liên kết thư viện mà chưa được cấp quyền; về sau chính sách có thể siết chặt. Với JDK hỗ trợ, kiểm tra `--illegal-native-access=deny` cùng `--enable-native-access` cần thiết để chắc chắn không có module vô tình dựa vào cảnh báo bị bỏ qua. Cờ native access cho phép hành vi native; nó **không** chứng nhận C prototype, native library safety hoặc ABI.

Với C++, các vấn đề `extern "C"` façade, name mangling, C++ exception boundary, compiler runtime và memory ownership giữa runtime cần test riêng. Một fixture C đơn giản PASS **không** chứng nhận khả năng phối hợp binary C++ từ MSVC, GCC, MinGW và Apple Clang.

## 7. Các tầng test thực tế nên gắn với từng target

| Gate | Nội dung cần chạy | Điều kiện PASS |
| --- | --- | --- |
| **Toolchain** | Thu `java -version`, compiler/OS/CPU, build flags | Version và kiến trúc đúng danh sách hỗ trợ |
| **Java build** | `javac --release`, test Java thuần | Classfile và Java APIs đúng baseline |
| **Native build/link** | `javac -h`, compiler warnings, linker, exported symbols | Binary đúng OS/CPU, có export cần thiết |
| **Loader smoke** | `System.loadLibrary` hoặc FFM `SymbolLookup` thực sự | Không lỗi dependency, architecture, naming |
| **ABI/behavior** | Độ rộng kiểu, struct layout, buffer, encoding, null, error codes | Kết quả đúng trên từng ABI |
| **Memory/lifetime** | JNI refs, FFM arenas/segments, malloc/free, callback cleanup | Không use-after-free, double-free, leak |
| **Stress/concurrency** | Nhiều luồng JNI/FFM, reentrant callback, cancellation | Không race, deadlock, crash hoặc sai kết quả |
| **Distribution** | Test artifact đã package trên máy/container sạch | Không phụ thuộc build environment tình cờ |
| **Diagnostics** | Lưu `hs_err_pid`/core khi xảy ra, native symbols và test reports | Tái hiện/điều tra được job lỗi |

Một test passing trên máy developer không thay thế CI. Một test dùng **mã native đã link trong unit-test process** không thay thế kiểm thử **artifact đã package**. Các kiểm thử có nguy cơ crash JVM nên chạy process riêng để một crash không kéo theo toàn bộ bộ test khác.

AddressSanitizer/UndefinedBehaviorSanitizer, compiler warning levels (ví dụ `-Wall -Wextra` trên GCC/Clang và `/W4` với MSVC), Debug/Release, tải lớn, fuzzing và native memory tools rất hữu ích, nhưng tool flags hỗ trợ khác nhau theo compiler/OS. Dùng các jobs bổ sung có điều kiện thay vì áp một cờ lên mọi target.

## 8. Kiểm tra artifact thực sự phát hành

Đây là bước thường bị bỏ sót: build và smoke test thành công ở `build/`, nhưng file đóng gói sai path hoặc thiếu runtime dependency.

1. **Đặt tên và metadata rõ ràng:** `libfoo-linux-x64-glibc.so`, `foo-windows-x64.dll`, `libfoo-macos-arm64.dylib` chỉ là ví dụ naming. Tên không chứng minh file đúng kiến trúc; cần metadata kiểm tra.
2. **Kiểm tra binary/dependency:** Linux dùng `file`, `readelf -h/-d`, `nm -D`; macOS dùng `file`, `otool -L`, `lipo -info` (nếu universal); Windows dùng `dumpbin /HEADERS`/`DEPENDENTS`/`EXPORTS` hoặc công cụ tương đương.
3. **Kiểm tra native runtime:** Windows có thể thiếu VC++ redistributable/DLL phụ thuộc; Linux có thể thiếu glibc version hoặc `libstdc++`; macOS có thể thiếu slice hoặc không hợp lệ với minimum deployment target/signing.
4. **Chạy từ thư mục cài đặt:** test bản JAR/binary cuối cùng trên môi trường sạch, **không** trỏ `java.library.path` sang build directory. Nếu JAR nhúng native resource và trích xuất ra disk, test luôn extraction, quyền file, đồng thời, integrity và cleanup.
5. **Ghi provenance:** build SHA, compiler/build ID, native hash, version, supported target, JDK tested và thư viện phụ thuộc để tái hiện lỗi sau phát hành.

Một bản phát hành chỉ có Linux/x64 binary không thể gắn nhãn Linux/arm64 chỉ vì Java JAR chạy trên cả hai CPU. macOS universal binary có thể bao gồm nhiều slices, nhưng vẫn phải kiểm thử load và gọi trên **từng CPU**.

## 9. Nhận biết lỗi thường gặp theo trục ma trận

| Dấu hiệu | Khả năng cần điều tra | Bằng chứng |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Build classfile bằng JDK cao hơn runtime target | `javac --release` và `java -version` |
| `UnsatisfiedLinkError: no nativemath in java.library.path` | Sai tên/đường dẫn hoặc binary không tìm thấy | `System.mapLibraryName`, output directory, installed artifact |
| `wrong ELF class`, Mach-O incompatible architecture, `not a valid Win32 application` | Sai OS, CPU hoặc bitness của native binary | `file`, `readelf`, `lipo`, `dumpbin`, JVM `os.arch` |
| Unresolved JNI function / symbol | C header không tương ứng Java, export name/mangling sai | `javac -h`, symbol table, C function name |
| Library có mặt nhưng vẫn không load | Thiếu dependency native, compiler runtime, loader/signing policy | `readelf -d`, `otool -L`, `dumpbin /DEPENDENTS`, loader diagnostics |
| Chỉ lỗi trên Windows/x64 | Nhầm C `long` 64-bit, calling convention hoặc MSVC CRT/C++ ABI | `sizeof(long)`, headers, structs, compile flags |
| Chỉ lỗi trên arm64 | CPU instructions/ABI, alignment, build sai architecture | Runner CPU, binary architecture, native tests |
| Java 24+ cảnh báo về native access hoặc `IllegalCallerException` | Chưa cấp đúng module quyền JNI/FFM | `--enable-native-access`, `--illegal-native-access` |
| `SIGSEGV`, `EXCEPTION_ACCESS_VIOLATION` | Pointer/lifetime/ABI sai hoặc native memory corruption | `hs_err_pid`, native frames, core, sanitizers |
| Debug PASS, Release FAIL | Undefined behavior, race, optimizer hoặc uninitialized memory | Repro build flags, native sanitizers |
| CI PASS nhưng khách hàng FAIL | Không kiểm tra package/dependencies/min OS/libc | Clean VM/container test, artifact hashes |

Đừng “sửa” job thất bại bằng cách tắt test, chấp nhận lỗi hay chỉ chạy lại một target dễ pass. Cần biết lỗi liên quan tới JDK, OS, CPU, compiler hay **tổ hợp** các trục; đôi khi không có một thủ phạm đơn lẻ.

## 10. Quản lý chi phí ma trận mà vẫn giữ hợp đồng hỗ trợ

Một ma trận hàng trăm jobs có thể tốn thời gian/chi phí. Có thể chia:

- **PR smoke:** JDK tối thiểu, JDK triển khai chính, JDK mới nhất đã hỗ trợ; tất cả OS/CPU quan trọng và compiler chủ đạo. Thay đổi JNI/FFM/header/ABI cần ma trận đầy đủ hơn.
- **Nightly/weekly:** compiler variants, JDK patch levels, Debug/Release, sanitizer, stress/fuzz, các target ít dùng; giữ kết quả lịch sử để tìm regression.
- **Pre-release:** chạy trên **toàn bộ tuple thực sự được tuyên bố hỗ trợ** và chính candidate artifact được phát hành. Chặn release nếu một tuple bắt buộc FAIL hoặc chưa có kết quả.
- **Nâng cấp toolchain/JDK:** chạy song song bản cũ và mới, đối chiếu compiler flags, runtime loader, ABI layout, crash signatures; chỉ cập nhật support statement khi đã có bằng chứng.

Pairwise/combinatorial reduction hữu ích với **các biến phụ** khi ma trận quá lớn, nhưng không tự động thay thế một target OS/CPU/JDK/compiler đã công bố hỗ trợ. Một tổ hợp chưa chạy phải báo **NOT_VERIFIED**, không được coi là PASS.

Bảng dưới là **dữ liệu giả lập minh họa**, không phải kết quả CI thật:

| JDK | Target | Build | Load | ABI | Package | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| 17 | linux-x64-gcc | PASS | PASS | PASS | PASS | SUPPORTED |
| 21 | windows-x64-msvc | PASS | PASS | PASS | PASS | SUPPORTED |
| 25 | macos-arm64-clang | PASS | PASS | PASS | NOT_RUN | NOT_VERIFIED |
| 25 | linux-arm64-gcc | PASS | FAIL | NOT_RUN | NOT_RUN | FAIL |

CI cần lưu **version thực tế** (JDK vendor/build, compiler identity/version, OS image revision, native artifact checksum), signal/crash logs nếu có và pass/fail cho từng gate. `fail-fast: false` giúp thấy đầy đủ lỗi ở các target; không phải lý do để bỏ qua lỗi.

## 11. Quy trình quyết định “được hỗ trợ”

1. **Chốt support contract:** liệt kê JDK distribution/version, OS tối thiểu và libc, CPU, compiler/toolchain, native library version và các tổ hợp thực tế.
2. **Sinh hợp đồng native:** Java `native` declarations và `javac -h` headers đồng bộ; với FFM đối chiếu C prototype, `FunctionDescriptor`/layout, ownership.
3. **Build đúng target:** xác nhận Java baseline, compiler version/flags, binary architecture, exported symbols và dependencies.
4. **Chạy JVM-native smoke:** load trên chính target, gọi phương thức, assert kết quả/ABI; không chỉ chạy compiler.
5. **Chạy test thực chất:** buffer/struct/callback, lỗi biên, multithread, memory lifetime, JNI references/FFM arenas và negative tests trong process cô lập.
6. **Kiểm tra package:** cài chính artifact sắp phát hành vào môi trường sạch, kiểm tra runtime dependencies và loading paths.
7. **Đánh giá mỗi tuple:** PASS khi đủ gates, FAIL nếu gate lỗi, NOT_VERIFIED nếu thiếu bằng chứng. Không tự suy ra PASS từ OS/CPU/JDK gần giống.
8. **Giữ dấu vết:** version, SHA/build ID, CI job logs và test artifacts để phân biệt regression từ JDK/compiler/OS hay native source khi xảy ra sự cố.

## 12. Tự kiểm tra

**1.** Java build được trên Windows/x64 nhưng `libfoo.so` từ Linux/x64 không load được. Vì sao?  
Vì Java bytecode độc lập hơn về nền tảng, còn native binary ELF của Linux không phải DLL/PE của Windows, mặc dù CPU cùng x64.

**2.** C `long` trên Linux/x64 và Windows/x64 có cùng kích thước không?  
Không. LP64 phổ biến trên Linux/macOS 64-bit có `long` 8 byte, LLP64 Windows 64-bit có `long` 4 byte; Java `long` luôn 8 byte.

**3.** Cross-compile ARM64 thành công có chứng minh runtime ARM64 PASS không?  
Không. Phải kiểm tra loader và chạy thật trên target ARM64 phù hợp, ghi rõ emulation nếu chỉ chạy mô phỏng.

**4.** JNI smoke PASS trên JDK 17/21 có chứng minh FFM trên JDK 25 tương thích không?  
Không. FFM API chính thức ở JDK 22+ và có test riêng về linker, descriptors, layouts, arenas và callbacks.

**5.** Vì sao chạy GCC và Clang trên cùng Linux/x64?  
Compiler optimization, diagnostics, extensions và undefined behavior có thể khác; một compiler pass không bảo đảm compiler còn lại.

**6.** Ma trận compile/load PASS nhưng package thiếu DLL phụ thuộc, được công bố SUPPORTED chưa?  
Chưa. Cần chạy artifact được phân phối trên môi trường sạch và verify dependencies.

**7.** Không có runner macOS/arm64 nhưng tài liệu sản phẩm cam kết hỗ trợ, ghi kết quả gì?  
`NOT_VERIFIED`; bổ sung runner/hardware và test hoặc điều chỉnh support statement, không thay kết quả bằng macOS/x64.

## Nguồn tham khảo

- [Oracle – JNI Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/index.html) — kiểu JNI, native method names/binding.
- [Oracle – `javac` tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — `--release` và `-h`.
- [OpenJDK JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454) — FFM được chuẩn hóa trong JDK 22.
- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472) — JNI native access restrictions từ JDK 24.
- [CMake FindJNI](https://cmake.org/cmake/help/latest/module/FindJNI.html) — tìm JNI headers và libraries.
- [GitHub Actions – Choosing runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) — runner OS/CPU labels.
- [GitHub Actions – Matrix strategy](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs) — cách tạo CI matrix.

**Kết luận kỹ thuật:** một tổ hợp JDK/OS/CPU/compiler chỉ được coi là hỗ trợ khi có bằng chứng **build, load, ABI, thực thi và phân phối** đúng trên target đó. Ma trận tương thích là một hợp đồng QA có thể kiểm chứng, không phải một danh sách tên hệ điều hành.