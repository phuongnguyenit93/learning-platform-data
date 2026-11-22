# Native build C++ hoặc Swift và yêu cầu môi trường tương ứng trong Gradle

## 1. Gradle không chỉ xây dựng ứng dụng JVM

Gradle thường được biết đến qua Java, Kotlin, Android và những task như `compileJava`, `test` hoặc `jar`. Nhưng Gradle còn có **native software plugins** để quản lý việc biên dịch, liên kết, kiểm thử và phân phối chương trình C++ hoặc Swift. Những plugin này tích hợp công việc của **compiler/linker thật trên máy** vào Gradle task graph.

Điểm khác biệt nền tảng:

- Java source thường được biên dịch thành **bytecode**; Gradle có thể cấu hình JDK toolchain cho Java compiler và chương trình chạy trên JVM phù hợp.
- C++ source được biên dịch thành **object files** rồi link thành **native executable** hoặc thư viện máy (`.so`, `.dylib`, `.dll`, `.a`, `.lib` tùy hệ điều hành/linkage).
- Swift source được biên dịch bằng **Swift compiler/toolchain** thành mã máy và artifacts phụ thuộc nền tảng, Swift runtime, system frameworks và ABI.
- Native binaries chịu ràng buộc **OS, CPU architecture, toolchain, system SDK, C/C++/Swift runtime và ABI**; không tự mang tính “chạy ở mọi nơi” như một Java JAR được xây cho JVM tương thích.

Ví dụ một lệnh:

```bash
./gradlew assemble
```

có thể dẫn tới `compileDebugCpp → linkDebug` ở một C++ application, hoặc `compileDebugSwift → linkDebug` ở một Swift application. Nó không tự dùng `javac` để compile `.cpp`/`.swift`. Gradle **điều phối**; GCC/Clang/MSVC hoặc Swift compiler mới là công cụ sinh binary.

**Mục tiêu bài học:** phân biệt plugins, chọn hệ điều hành/toolchain hợp lệ, cấu hình build variants, viết hai dự án chạy được, kiểm tra outputs/tests, xử lý các lỗi môi trường phổ biến và thiết kế CI theo đúng target machines.

## 2. Các native plugins trong Gradle hiện đại

| Plugin ID | Loại sản phẩm | Phạm vi / nhiệm vụ |
| --- | --- | --- |
| `cpp-application` | Chương trình C++ | Compile và link executable; debug/release; install |
| `cpp-library` | Thư viện C++ | Shared/static libraries, public/private headers |
| `cpp-unit-test` | Bộ test C++ executable | Tích hợp framework/harness test và lifecycle `check` |
| `swift-application` | Chương trình Swift | Compile và link Swift executable trên macOS/Linux |
| `swift-library` | Thư viện Swift | Shared/static libraries và Swift module/dependencies |
| `xctest` | Swift/XCTest tests | Compile/run XCTest, báo cáo test |
| `visual-studio` | Tích hợp IDE cho C++ | Sinh Visual Studio project/solution phù hợp |
| `xcode` | Tích hợp Xcode | Sinh Xcode project/workspace phù hợp |

**Cú pháp Kotlin DSL** cho core native plugin có dấu gạch nối cần đặt trong backticks:

```kotlin
plugins {
    `cpp-application`
}
```

**Cú pháp Groovy DSL** tương đương:

```groovy
plugins {
    id 'cpp-application'
}
```

Không áp dụng đồng thời `cpp-application` và `swift-application` cho một lab chỉ muốn một entrypoint; bài học dùng **hai builds độc lập** để việc debug/toolchain rõ ràng.

### 2.1. Plugins mới và hệ thống native legacy

Gradle còn có hệ thống native plugins/model rất cũ như `c`, `cpp`, `native-component` và các software-model APIs. Tài liệu Gradle 9.x khuyến nghị dùng `cpp-application`/`cpp-library` và hệ plugin hiện đại; legacy native model đang bị deprecate và được dự kiến loại bỏ ở Gradle 10.

Nếu đang bảo trì repo cũ, không thay các plugins theo tên một cách cơ học. Trước hết phải kiểm dependency model, source sets, variants, toolchains và consumer binaries; sau đó lên kế hoạch di chuyển có tests. Các plugins mới và cũ không phải hai aliases tương đương hoàn toàn.

### 2.2. Các lựa chọn ngoài Gradle

- **CMake**: hệ sinh thái C/C++ lớn, tương thích IDE và nhiều package managers.
- **Ninja/Make**: build executors ở cấp lệnh biên dịch.
- **Swift Package Manager**: workflow native phổ biến của Swift.
- **Xcode build**: hệ sinh thái Apple targets và signing/package workflows.
- **Gradle native plugins**: hữu ích khi dự án cần phối hợp nhiều modules/tasks, metadata/variants, CI/Gradle conventions hoặc quản lý sản phẩm cùng hệ Gradle.

Chọn Gradle không có nghĩa mọi package manager/SDK feature của SwiftPM/Xcode/CMake đều tự được Gradle hỗ trợ. Có thể tích hợp external build tool bằng task thích hợp, nhưng phải khai báo inputs/outputs và tránh build trùng/lặp không kiểm soát.

## 3. Ma trận môi trường: C++ và Swift khác nhau

Đây là phân biệt quan trọng nhất khi một developer chạy cùng Gradle Wrapper trên các máy khác nhau.

| Host OS | C++ compiler/toolchain được Gradle hỗ trợ | Swift compiler được Gradle hỗ trợ | Cần kiểm |
| --- | --- | --- | --- |
| **Linux** | GCC hoặc Clang trong `PATH` | Official Swift toolchain trong `PATH` | Compiler + linker + libc/system headers, SDK |
| **macOS** | Xcode/Apple Clang; một số GCC/Clang từ Homebrew/MacPorts | Official Swift toolchain qua Xcode hoặc cài đặt được hỗ trợ | Xcode/Command Line Tools, SDK, `xcode-select` |
| **Windows** | Visual C++ từ Visual Studio Build Tools; GCC qua MinGW/Cygwin trong các trường hợp hỗ trợ | **Không** là Gradle Swift native host được tài liệu hỗ trợ ở đây | MSVC toolset, Windows SDK, environment |
| **CI container** | Theo OS/container image và compiler đã cài | Theo OS/container image và official Swift tools | Compiler binaries, shared libraries, runner architecture |

Điều kiện trên dựa vào Gradle native documentation; **Swift language nói chung có thể có toolchain trên hệ nền tảng khác**, nhưng không nên suy từ đó rằng Gradle `swift-application` hỗ trợ Windows tương đương macOS/Linux.

### 3.1. Linux — kiểm tra compiler thực tế

```bash
uname -s
uname -m
which gcc
which g++
which clang
which clang++
gcc --version
g++ --version
clang++ --version
```

Máy có thể chỉ cài một trong hai GCC/Clang, khi đó những lệnh kiểm tra compiler **không cài** sẽ fail; không cần cài cả hai chỉ để Gradle dùng một toolchain.

Với Swift:

```bash
which swift
which swiftc
swift --version
swiftc --version
```

Nếu `swiftc` không có trong PATH, Gradle không thể tự sinh Swift compiler từ một Java toolchain. Cài đúng official Swift toolchain cho OS/architecture, rồi cấu hình PATH/required runtime/system dependencies theo Swift install guide.

**Một compiler hiện trong PATH không tự chứng minh linker và SDK đủ dùng.** Hãy compile chương trình tối thiểu rồi mới cấu hình Gradle project lớn.

### 3.2. macOS — Xcode toolchain và SDK

Kiểm:

```bash
xcode-select -p
xcrun --find clang++
xcrun --find swiftc
xcrun clang++ --version
xcrun swiftc --version
```

Nếu chỉ cài Command Line Tools, chức năng build C++ có thể dùng được, nhưng các tác vụ Swift/XCTest/Xcode integration có thể cần các thành phần Xcode phù hợp. Khi nhiều Xcode versions tồn tại, kiểm **Xcode đang active**; thay `xcode-select` trong CI phải có quyền quản trị phù hợp và không nên sửa máy dùng chung tùy tiện.

Một executable macOS x86_64 khác arm64; nếu CI là Apple Silicon, không được tự mặc định hai architectures có cùng ABI và toolchain output. Cần khai báo target và kiểm runner/SDK.

### 3.3. Windows — Visual C++/MSVC

Cài Visual Studio hoặc Visual Studio Build Tools có **Desktop development with C++** cùng MSVC toolset và Windows SDK. Kiểm trong Developer PowerShell/Developer Command Prompt:

```powershell
where.exe cl
where.exe link
cl
```

`cl` có thể trả nonzero nếu gọi không tham số nhưng vẫn in version banner; đây là kiểm tra discovery, không phải chương trình compile đầy đủ.

Nếu không tìm thấy `cl.exe`/`link.exe`, mở Developer Command Prompt hoặc cấu hình môi trường toolset đúng. Gradle C++ plugin có cơ chế phát hiện Visual Studio installations; cấu hình `toolChains` tường minh chỉ khi discovery thất bại và bạn biết install location thật.

Ví dụ tài liệu Gradle cho một installation path Visual Studio là dạng:

```text
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools
```

Path này là **minh họa**, không được coi là tồn tại trên mọi máy. Tìm location thật từ installer/`vswhere` trước khi đặt nó vào build script.

### 3.4. JDK cần để chạy Gradle không phải native compiler

Gradle vẫn chạy trên JVM. Với Gradle 9.x, Gradle Daemon cần Java 17+ phù hợp. Lệnh:

```bash
./gradlew --version
java -version
```

giúp kiểm runtime Gradle/JDK, nhưng **không xác minh GCC/Clang/MSVC/Swift compiler**.

Đoạn cấu hình JVM:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

chỉ có ý nghĩa khi Java/JVM plugins tạo extension `java`. Nó **không phải cách chọn C++ compiler hoặc Swift compiler** trong project chỉ áp dụng `cpp-application` hay `swift-application`. Không thêm `java` block vào native-only build rồi mong Gradle cài C++ toolchain tự động.

## 4. Pipeline native: source → object → linker → executable

Quy trình C++:

```text
src/main/cpp/main.cpp  +  src/main/headers/*.h
              |
              v
       GCC / Clang / MSVC
              |
              v
       Object files (.o/.obj)
              |
              v
     Linker + system/runtime libs
              |
              v
  native executable (.exe/ELF/Mach-O)
              |
              v
          installDebug
```

Quy trình Swift tương ứng:

```text
src/main/swift/main.swift
              |
              v
       Official swiftc toolchain
              |
              v
       Objects + module metadata
              |
              v
       Swift / platform linker
              |
              v
      Native executable
              |
              v
          installDebug
```

### 4.1. Compile và link là hai lỗi khác nhau

- Compile failure: syntax, missing header/module, incompatible source, unsupported compiler flag.
- Link failure: undefined symbols, missing libraries, wrong ABI/architecture, incompatible runtime, library search paths.
- Launch failure: executable không tương thích OS/CPU, thiếu shared libraries, permissions, runtime loader mismatch.

Gradle bọc những lỗi này thành task failure, nhưng **stderr của compiler/linker/process** thường mang nguyên nhân thực tế. Dùng `--info --stacktrace` để biết Gradle đã gọi tool nào và với arguments nào, không chỉ nhìn `BUILD FAILED`.

### 4.2. Build variants

Các native plugins hiện đại xây nhiều variants dựa trên dimensions:

- Build type: `debug` hoặc `release`.
- Target machine: operating system + architecture.
- Linkage (đối với library): `shared` hoặc `static`.

**Debug variant** thường dễ debug, giữ debug symbols và không ưu tiên optimize. **Release variant** tối ưu, nhưng Gradle có thể tách symbols để phục vụ debug. Không coi `release` nghĩa là chương trình đã được ký/notarized và đủ điều kiện distribute.

Ví dụ task names trên một application host:

```text
compileDebugCpp
linkDebug
assembleDebug
installDebug

compileReleaseCpp
linkRelease
assembleRelease
installRelease
```

Với Swift, thay `Cpp` bằng `Swift` cho compile tasks. Khi có nhiều target machines, task names/variants có thể có suffix khác; hãy xem `./gradlew tasks --all` thay vì hardcode theo một bản ví dụ.

### 4.3. Lifecycle tasks

`assemble` chọn **development binary**, mặc định thường là debug host variant. `build` gắn `assemble` với `check`. `clean` xóa Gradle build output directory. `check` **không tự chạy unit tests** trừ khi có test plugin/task được nối vào graph.

Vì vậy một project chỉ áp dụng `cpp-application` mà không cấu hình tests vẫn có thể `build` thành công. CI phải có quality gates riêng nếu cần native unit tests.

## 5. Lab A: C++ application với Gradle Kotlin DSL

Đây là **dự án độc lập**. Có thể chạy trên Linux/macOS với GCC/Clang, hoặc Windows với Visual C++ được Gradle hỗ trợ. Chúng ta sẽ cố định tên executable để biết file cần smoke-test.

### 5.1. Cây thư mục

```text
native-gradle-labs/
└── cpp-native-lab/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── gradlew
    ├── gradlew.bat
    ├── gradle/wrapper/...
    ├── src/main/
    │   ├── cpp/
    │   │   ├── main.cpp
    │   │   └── sum.cpp
    │   └── headers/
    │       └── sum.hpp
    └── src/test/manual/
        └── sum_test.cpp
```

Gradle Wrapper files phải được tạo bằng Gradle được tin cậy và commit; không tạo `gradle-wrapper.jar` giả hoặc bỏ nó rồi vẫn dùng `./gradlew`.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "cpp-native-lab"
```

### 5.3. `build.gradle.kts`

```kotlin
plugins {
    `cpp-application`
}

group = "dev.learning"
version = "1.0.0"

application {
    // Đặt tên binary độc lập với rootProject.name.
    baseName.set("nativeCppLab")
}
```

Không cần `repositories { mavenCentral() }` khi lab chỉ compile local C++ code bằng standard library và không dùng external dependencies. `cpp-application` cung cấp project extension `application` riêng của C++; **không phải** Java Application plugin `mainClass`.

Ta **không chỉ định `targetMachines`**, để Gradle dùng host OS/architecture. Đây là lựa chọn hợp lý nhất cho lab đầu tiên: build trên OS đang dùng, không giả định cross-compiler.

### 5.4. Header `src/main/headers/sum.hpp`

```cpp
#ifndef NATIVE_SUM_HPP
#define NATIVE_SUM_HPP

long long sumUpTo(int n);

#endif
```

Đây là **private header của C++ application** được Gradle lấy từ conventional directory `src/main/headers`. Khi chuyển thành C++ library có API công khai, thư mục headers được cấu trúc khác (mục 10).

### 5.5. Implementation `src/main/cpp/sum.cpp`

```cpp
#include "sum.hpp"

#include <stdexcept>

long long sumUpTo(int n) {
    if (n < 0) {
        throw std::invalid_argument("n must be non-negative");
    }

    long long result = 0;
    for (int i = 1; i <= n; ++i) {
        result += i;
    }
    return result;
}
```

Hàm tính tổng 1..n. Với `n=10`, kết quả bằng 55. API cố tình giới hạn lab input nhỏ; với `n` lớn hơn có thể cần kiểm toán arithmetic overflow và performance trong sản phẩm thực.

### 5.6. Entry point `src/main/cpp/main.cpp`

```cpp
#include "sum.hpp"

#include <iostream>

int main() {
    std::cout
        << "native-cpp=OK; total="
        << sumUpTo(10)
        << '\n';
    return 0;
}
```

**Stdout chính xác của executable C++ khi build/chạy đúng:**

```text
native-cpp=OK; total=55
```

Nó không phụ thuộc network, clock, locale hay environment secrets.

### 5.7. Build bằng Gradle

Linux/macOS:

```bash
./gradlew --version
./gradlew tasks --all
./gradlew clean assembleDebug installDebug --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat tasks --all
.\gradlew.bat clean assembleDebug installDebug --console=plain
```

Các task `compileDebugCpp`, `linkDebug`, `assembleDebug`, `installDebug` là loại nhiệm vụ do C++ Application plugin tạo. `installDebug` còn xử lý runtime dependencies theo native component model.

Với **một host variant mặc định**, output executable theo convention thường ở:

```text
build/exe/main/debug/nativeCppLab          (Linux/macOS)
build/exe/main/debug/nativeCppLab.exe      (Windows)
```

Có thể xem thực tế qua `find build/exe -type f` trên Unix hoặc `Get-ChildItem build\exe -Recurse -File` trên Windows. Đường dẫn có thể khác nếu project thay variant/`buildDirectory`/baseName; luôn **xác định path từ output thật**.

Chạy file đã link (khi layout đúng):

Linux/macOS:

```bash
./build/exe/main/debug/nativeCppLab
```

Windows PowerShell:

```powershell
.\build\exe\main\debug\nativeCppLab.exe
```

Kết quả của chính chương trình:

```text
native-cpp=OK; total=55
```

Nếu binary có shared-library runtime dependencies, ưu tiên chạy **bản installed** do `installDebug` tạo thay vì chép riêng executable, vì Gradle có thể đã sắp xếp libraries tương ứng trong installation directory.

### 5.8. Biên dịch C++ trực tiếp để phân biệt lỗi Gradle và compiler

Linux (GCC):

```bash
mkdir -p build/manual
g++ -std=c++17 -Wall -Wextra -Isrc/main/headers \
  src/main/cpp/sum.cpp src/main/cpp/main.cpp \
  -o build/manual/native-cpp-direct
./build/manual/native-cpp-direct
```

macOS với Clang:

```bash
mkdir -p build/manual
clang++ -std=c++17 -Wall -Wextra -Isrc/main/headers \
  src/main/cpp/sum.cpp src/main/cpp/main.cpp \
  -o build/manual/native-cpp-direct
./build/manual/native-cpp-direct
```

Stdout vẫn là:

```text
native-cpp=OK; total=55
```

Các lệnh trực tiếp này giúp kiểm compiler và source C++ trên host mà không đi qua Gradle. Chúng **không thay thế** Gradle tasks/variant packaging/dependency metadata/CI verification.

Windows với MSVC (Developer PowerShell sau khi MSVC environment được cấu hình):

```powershell
New-Item -ItemType Directory -Force build\manual | Out-Null
cl /EHsc /std:c++17 /Isrc\main\headers src\main\cpp\sum.cpp src\main\cpp\main.cpp /Febuild\manual\native-cpp-direct.exe
.\build\manual\native-cpp-direct.exe
```

Nếu MSVC báo thiếu linker/SDK hoặc `cl` không tìm được, đó là **vấn đề Windows C++ toolchain**, không phải lý do phải nâng JDK.

## 6. Bài kiểm tra C++ không phụ thuộc framework

Trước khi tích hợp Google Test/Catch2, có thể dùng một executable test tối giản với `assert` và exit code. Nó giúp kiểm source logic và compiler riêng.

**File `src/test/manual/sum_test.cpp`:**

```cpp
#include "sum.hpp"

#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    assert(sumUpTo(0) == 0);
    assert(sumUpTo(10) == 55);

    bool rejectsNegative = false;
    try {
        (void)sumUpTo(-1);
    } catch (const std::invalid_argument&) {
        rejectsNegative = true;
    }

    assert(rejectsNegative);
    std::cout << "cpp-unit-smoke=PASS" << '\n';
    return 0;
}
```

GCC:

```bash
mkdir -p build/manual
g++ -std=c++17 -O0 -Isrc/main/headers \
  src/main/cpp/sum.cpp src/test/manual/sum_test.cpp \
  -o build/manual/sum_test
./build/manual/sum_test
```

**Stdout chính xác khi ba điều kiện đạt:**

```text
cpp-unit-smoke=PASS
```

Đây là **manual native smoke test**, không được Gradle `check` tự chạy. Trong test code sử dụng `assert`, cần bảo đảm build không định nghĩa `NDEBUG` vì có thể vô hiệu hóa assertions. Production test framework thường cho reports tốt hơn, được CI gọi và quản lý qua build tool.

### 6.1. Dùng `cpp-unit-test` trong dự án thực

Có thể áp dụng plugin:

```kotlin
plugins {
    `cpp-application`
    `cpp-unit-test`
}
```

Nhưng đừng chỉ dán dòng plugin rồi kết luận `check` đã chạy những assertions ở `src/test/manual`. Plugin có conventional `src/test/cpp` và cần **test harness hợp lệ** với entry point/test runner như framework phù hợp và dependencies/linkage đúng. Khi tích hợp xong, task kiểm thử native được nối vào lifecycle `check`.

Nếu chọn Google Test hoặc framework khác, phải cung cấp dependency/native library, build/link configuration và runner output theo đúng framework. Không tự gọi `cpp-unit-test` là “JUnit cho C++”; nó là mô hình native testing khác.

### 6.2. Khi nào cần `assert` hay framework?

- Lab nhỏ: assert/exit code hữu ích để phân biệt lỗi compiler và logic.
- CI lớn: dùng Google Test/Catch2/CTest hoặc framework được tổ chức chuẩn hóa, reports và test filtering, kiểm test count.
- Với thư viện public: kiểm ABI/API compatibility, consumer compile/link, release/debug variants trên nhiều toolchains.

Native test pass trên Linux GCC không chứng minh Windows MSVC cũng pass; phải chạy matrix.

## 7. Lab B: Swift application với Gradle Kotlin DSL

Đây là build **độc lập** với lab C++. Chỉ thực hiện trên **macOS hoặc Linux** có official Swift toolchain được Gradle hỗ trợ. Không dùng Windows PowerShell làm môi trường Gradle Swift plugin trong bài này.

### 7.1. Cây thư mục

```text
native-gradle-labs/
└── swift-native-lab/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── gradlew
    ├── gradle/wrapper/...
    └── src/main/swift/
        └── main.swift
```

### 7.2. `settings.gradle.kts`

```kotlin
rootProject.name = "swift-native-lab"
```

### 7.3. `build.gradle.kts`

```kotlin
plugins {
    `swift-application`
}

group = "dev.learning"
version = "1.0.0"

application {
    // Ổn định Swift module/executable name thay vì dựa vào root name.
    module.set("NativeSwiftLab")
}
```

`SwiftApplication.module` là một Gradle `Property<String>`. Nó khác `CppApplication.baseName` và khác `application.mainClass` của Java plugin. Không dùng `java { toolchain { ... } }` để chọn Swift compiler.

Không khai báo `targetMachines` ở lab cơ bản, để Gradle build cho host. Swift compiler vẫn phải **được cài và discover** trên macOS/Linux.

### 7.4. Swift source `src/main/swift/main.swift`

```swift
let total = (1...10).reduce(0, +)
print("native-swift=OK; total=\(total)")
```

**Stdout chính xác của chương trình Swift:**

```text
native-swift=OK; total=55
```

Đây là Swift top-level code hợp lệ trong executable module. Không có `static void main(String[] args)` như Java; cũng không dùng C++ `int main()`.

### 7.5. Build Swift bằng Gradle

Linux/macOS:

```bash
swiftc --version
./gradlew --version
./gradlew tasks --all
./gradlew clean assembleDebug installDebug --console=plain
```

Những task quan trọng là `compileDebugSwift`, `linkDebug`, `assembleDebug`, `installDebug`. Khi host/toolchain không phù hợp, Gradle có thể fail ở bước chọn toolchain hoặc compilation/link. Không khắc phục bằng cách tạo JAR hoặc sửa `sourceCompatibility` của Java.

Với một host debug variant và module name trong lab, executable convention có dạng:

```text
build/exe/main/debug/NativeSwiftLab
```

Trước khi chạy nên xác minh file thực sự có tại location tương ứng, vì layout có thể chịu ảnh hưởng của Gradle version/target variant và customization:

```bash
find build/exe -type f
./build/exe/main/debug/NativeSwiftLab
```

Dòng output của executable:

```text
native-swift=OK; total=55
```

`installDebug` tạo một installation layout, có thể quan trọng nếu Swift native program phụ thuộc shared libraries. Khi executable trực tiếp không resolve dependencies, chạy bản installed theo đường dẫn Gradle đã tạo hoặc cấu hình runtime library search path hợp lệ, **không copy ngẫu nhiên system libraries vào source repo**.

### 7.6. Kiểm compiler Swift độc lập

Linux/macOS:

```bash
mkdir -p build/manual
swiftc src/main/swift/main.swift -o build/manual/native-swift-direct
./build/manual/native-swift-direct
```

Stdout:

```text
native-swift=OK; total=55
```

Nếu `swiftc` tự compile/execute được nhưng Gradle không tìm được toolchain, kiểm PATH, Gradle daemon environment và cách Gradle phát hiện official Swift installation. Nếu cả `swiftc` cũng không chạy, tập trung vào OS SDK/toolchain chứ đừng sửa Kotlin DSL đầu tiên.

### 7.7. Tại sao không lấy SwiftPM layout làm Gradle convention mặc định?

Swift Package Manager thường bố trí `Sources/ModuleName/...`, còn Gradle Swift Application plugin theo convention `src/main/swift`. Nếu muốn dùng layout khác, cấu hình extension source tường minh; **đừng đưa source vào `Sources/...` rồi chờ Gradle tự nhận diện**.

Mảnh Kotlin DSL minh họa:

```kotlin
application {
    source.from(file("Sources/NativeSwiftLab"))
}
```

Đây là **cấu hình thay thế** cho directory mặc định. Muốn lab ở mục 7 chạy theo đúng file paths đã tạo, **không** thêm fragment này.

## 8. Groovy DSL tương đương

Một project dùng **Kotlin DSL hoặc Groovy DSL**, không cần viết cả hai build files trong cùng project.

### 8.1. C++: `cpp-native-lab/build.gradle`

```groovy
plugins {
    id 'cpp-application'
}

group = 'dev.learning'
version = '1.0.0'

application {
    baseName = 'nativeCppLab'
}
```

**C++ `settings.gradle`:**

```groovy
rootProject.name = 'cpp-native-lab'
```

C++ source/headers và native tasks không đổi. Trên host hợp lệ, output dự kiến vẫn là `native-cpp=OK; total=55`.

### 8.2. Swift: `swift-native-lab/build.gradle`

```groovy
plugins {
    id 'swift-application'
}

group = 'dev.learning'
version = '1.0.0'

application {
    module = 'NativeSwiftLab'
}
```

**Swift `settings.gradle`:**

```groovy
rootProject.name = 'swift-native-lab'
```

Lưu ý: `application` extension mang loại đối tượng khác nhau tùy plugin; Groovy DSL có dynamic syntax nhưng **không biến thuộc tính từ Swift thành thuộc tính C++**. Đọc đúng Gradle DSL API của plugin được áp dụng.

## 9. Chọn target machines và hiểu cross-compilation

Theo mặc định, native component phát sinh variant cho **host operating system và architecture**. Có thể đặt target machines rõ ràng:

### 9.1. C++ nhiều targets

Mảnh Kotlin DSL cho project C++:

```kotlin
application {
    targetMachines = listOf(
        machines.linux.x86_64,
        machines.windows.x86_64,
        machines.macOS.x86_64
    )
}
```

Groovy DSL:

```groovy
application {
    targetMachines = [
        machines.linux.x86_64,
        machines.windows.x86_64,
        machines.macOS.x86_64
    ]
}
```

### 9.2. Swift targets

Mảnh Kotlin DSL:

```kotlin
application {
    targetMachines = listOf(
        machines.linux.x86_64,
        machines.macOS.x86_64
    )
}
```

Chúng là **mảnh cấu hình minh họa**, không dán vào lab nếu compiler chỉ hỗ trợ một target.

### 9.3. Bẫy lớn: targetMachines không tự cung cấp cross-compiler

`targetMachines` mô tả **những binary variants cần có**; nó không:

- Cài Visual Studio/Windows SDK trên Linux.
- Tạo Apple macOS SDK hợp pháp trên Windows/Linux.
- Bổ sung Swift runtime/SDK cho target khác.
- Chuyển ELF Linux thành Windows PE chỉ bằng đổi tên file thành `.exe`.
- Bảo đảm GCC/Clang cài trên host có cross sysroot và correct linker cho target OS khác.

Với các toolchains Gradle native mặc định, **hỗ trợ thường nhắm build trên cùng hệ điều hành host**. Cross compilation nâng cao cần compiler, target triple, sysroot, linker, runtime libs và plugin support thực sự. Cho bài lab, dùng CI **matrix host** thay vì kỳ vọng một Linux runner xuất được tất cả macOS/Windows binaries.

### 9.4. OS, arch và ABI có những trục riêng

Ví dụ:

| Binary được build | Có thể chạy trực tiếp ở | Không nên tự suy |
| --- | --- | --- |
| Linux x86_64 ELF | Linux x86_64 có runtime/libc compatible | Windows/macOS |
| Windows x86_64 PE/COFF | Windows x86_64 với MSVC runtime phù hợp | Linux chỉ vì CPU x86_64 |
| macOS arm64 Mach-O | macOS arm64 với SDK deployment target phù hợp | Linux ARM64 |
| macOS x86_64 Mach-O | macOS x86_64 hoặc environment tương thích | Linux x86_64 |
| Swift Linux x86_64 | Linux x86_64 có Swift runtime/stdlib tương thích | macOS/Windows |
| C++ shared library | Consumer process dùng ABI + runtime đúng | Consumer bất kỳ chỉ vì cùng tên file |

**ABI** gồm calling convention, name mangling, object layout, compiler standard library, exception handling và binary format. Ngay cả cùng OS/arch, các phiên bản libstdc++/libc++/MSVC runtime hoặc Swift runtime khác nhau cũng có thể làm binary không chạy được.

## 10. Native libraries: shared/static và header/API

Application tạo executable; library tạo binary để **consumer** liên kết.

### 10.1. C++ library Kotlin DSL

**Mảnh độc lập cho một `cpp-library` project:**

```kotlin
import org.gradle.nativeplatform.Linkage

plugins {
    `cpp-library`
}

group = "dev.learning"
version = "1.0.0"

library {
    linkage = listOf(Linkage.STATIC, Linkage.SHARED)
}
```

Cấu trúc thư mục convention:

```text
src/main/
├── cpp/                 # .cpp/.cc/.c++
├── headers/             # private headers
└── public/              # public headers cho consumer
```

Ví dụ public header:

**`src/main/public/arith.hpp`:**

```cpp
#ifndef ARITH_HPP
#define ARITH_HPP

namespace arith {
    long long sumUpTo(int n);
}

#endif
```

**`src/main/cpp/arith.cpp`:**

```cpp
#include "arith.hpp"

namespace arith {
    long long sumUpTo(int n) {
        long long result = 0;
        for (int i = 1; i <= n; ++i) {
            result += i;
        }
        return result;
    }
}
```

Gradle C++ Library plugin dùng `src/main/public` cho headers consumer phải thấy, `src/main/headers` cho private headers. Đừng đưa internal header có secrets/implementation details ra public API chỉ để compiler tìm được file.

### 10.2. Shared/static khác nhau

| Linkage | C++ output phổ biến | Ý nghĩa |
| --- | --- | --- |
| Static | `.a` (Linux/macOS), `.lib` (Windows) | Library code liên kết vào binary consumer khi link |
| Shared | `.so` (Linux), `.dylib` (macOS), `.dll` kèm import `.lib` (Windows) | Binary cần runtime loader tìm library tương thích |

Shared library cần deployment/runtime path hợp lệ (`rpath`, loader search path, application bundle/install layout), không chỉ compile thành công. Static linking có thể tăng binary size và chịu license/ABI constraints; không tự loại bỏ mọi runtime dependency.

### 10.3. Swift library

**Mảnh cho một Swift library project:**

```kotlin
import org.gradle.nativeplatform.Linkage

plugins {
    `swift-library`
}

library {
    linkage = listOf(Linkage.STATIC, Linkage.SHARED)
}
```

Swift library có module/interface và dependencies theo variant. Khi consumer dùng Swift library qua Gradle, version/Swift compiler compatibility và module stability cần được kiểm tra. Không giả định mọi Swift compiled module byte-for-byte portable giữa toolchain versions.

### 10.4. Native dependencies không giống Java JAR dependencies

C++/Swift application extension có model:

```kotlin
application {
    dependencies {
        implementation(project(":common"))
    }
}
```

Đây là **mảnh minh họa một multi-project Gradle build có `:common`**, không hoạt động trong hai single-project labs ở trên khi chưa có project đó. Native variant-aware resolution còn tính build type, architecture, OS và linkage.

Với C++/Swift library:

- `api` dùng cho dependencies lộ ra contract/public headers/module API.
- `implementation` dùng cho chi tiết bên trong không cần consumer compile against trực tiếp.
- Các configurations internal như `cppCompileDebug`, `nativeLinkDebug`, `nativeRuntimeDebug` hoặc `swiftCompileDebug` phục vụ những bước riêng.

Dependency `implementation("group:module:version")` ở native component không đồng nghĩa tự đóng mọi dylib/DLL vào executable. Kiểm Gradle Module Metadata và test consumer ở đúng target machine.

## 11. Kiểm thử native: C++ Unit Test và Swift XCTest

### 11.1. C++ test integration

Gradle `cpp-unit-test` tạo một native executable test suite có task compile/link/install/run thích hợp. Nó **không tự biết business assertions nếu chưa có test sources và framework harness**. Với một project nghiêm túc cần:

1. Tạo test sources trong `src/test/cpp` và headers tương ứng.
2. Chọn framework (Google Test hoặc framework tương thích) và khai báo/native link dependencies.
3. Cung cấp test entrypoint/runner phù hợp.
4. Xác minh Gradle `check` thực sự chạy tests và trả nonzero khi thất bại.
5. Bảo toàn reports/exit codes trong CI.

Đừng nhầm test built-in của Java/JUnit với C++ test task. `tasks.test { useJUnitPlatform() }` trong native-only build không tự xuất hiện.

### 11.2. Swift XCTest

Gradle cung cấp plugin `xctest`, với conventions `src/test/swift` và nhiệm vụ `xcTest`/`test`. Nó chạy XCTest trong process riêng, trên macOS dùng Xcode XCTest, còn Linux dùng core-libraries XCTest tương ứng.

Một **mảnh test source** độc lập minh họa:

**`src/test/swift/ArithmeticTests.swift`:**

```swift
import XCTest

final class ArithmeticTests: XCTestCase {
    func testSumOfTen() {
        XCTAssertEqual((1...10).reduce(0, +), 55)
    }

    func testEmptySum() {
        XCTAssertEqual([Int]().reduce(0, +), 0)
    }
}
```

Cấu hình plugin cho project Swift khi muốn thử XCTest:

```kotlin
plugins {
    `swift-application`
    xctest
}
```

Sau khi đã bảo đảm Swift/XCTest toolchain và test discovery đúng cho host:

```bash
./gradlew tasks --all
./gradlew check --console=plain
```

Test source trên kiểm phép tính mẫu để làm quen test runner; nó **chưa kiểm tra trực tiếp logic của ứng dụng trong `main.swift`**. Trong project thực hãy extract business logic thành module/library có thể import `@testable` và viết tests nhắm đúng public behavior. Các version Swift/XCTest khác nhau có thể yêu cầu cấu hình test discovery hoặc test bundle khác nhau, nên cần xem test reports thay vì giả định plugin có mặt đồng nghĩa tests đã chạy.

### 11.3. Filter và reports

Gradle XCTest hỗ trợ test filtering `--tests` theo các mẫu phù hợp; tên bundle/class trên macOS có thể yêu cầu prefix khác Linux. Xem task `xcTest` và test XML/HTML output thực thay vì đoán pattern.

`ignoreFailures = true` làm CI tiếp tục khi test fail, nên không phù hợp cho mandatory release verification. Với C++ tests cũng phải kiểm exit code/report của test executable; không coi executable chạy nhưng có zero assertions là đạt.

### 11.4. Phân biệt compile smoke và runtime smoke

- `compileDebugCpp`/`compileDebugSwift` pass: compiler chấp nhận source.
- `linkDebug` pass: linker tạo executable.
- Chạy executable trên host tương ứng: kiểm runtime loader và entrypoint.
- Native tests pass: kiểm business assertions.
- Consumer integration tests: kiểm public library API/ABI và deployed runtime dependencies.

Một bước không thay thế các bước còn lại.

## 12. Toolchain selection: để Gradle chọn gì và phải cài gì?

Native plugins dùng host discovery để tìm compiler có thể build target variant.

| Thông tin Gradle có thể quyết định | Nguồn cần tồn tại ngoài Gradle |
| --- | --- |
| Chọn compiler toolchain khả dụng | GCC/Clang/MSVC/Swift installation thật |
| Chọn variant debug/release/architecture | Target toolchain và target runtime/SDK |
| Tạo task compile/link/install | Headers, system libs, linkers và SDK |
| Theo dõi incremental/cacheable compile tasks | Inputs/flags/toolchain phù hợp, filesystem |
| Resolve native project dependencies | Binary artifacts và compatible variants |
| Tạo build outputs | OS permissions, disk space, executable format |

### 12.1. Compiler flags phải phụ thuộc toolchain

Ví dụ, `-Wall` hoặc `-O2` là flags quen thuộc của GCC/Clang, còn MSVC có `/W4`, `/O2`. Không truyền tùy tiện:

```kotlin
// Sai nếu build cả MSVC trên Windows và GCC trên Linux:
tasks.withType<org.gradle.language.cpp.tasks.CppCompile>().configureEach {
    compilerArgs.add("-Wall")
}
```

Đây là **mảnh cố tình thiếu tính portable**. Hãy cấu hình theo toolchain bằng Gradle provider/model hoặc tách CI conventions theo toolchain sau khi đọc task reference. Đừng đánh đồng compiler flags với Java `options.release`.

Ví dụ mảnh an toàn hơn cho **chỉ Linux/macOS với GCC/Clang**:

```kotlin
import org.gradle.language.cpp.tasks.CppCompile

tasks.withType<CppCompile>().configureEach {
    compilerArgs.add("-Wall")
    compilerArgs.add("-Wextra")
}
```

Khi muốn hỗ trợ MSVC, cần loại bỏ hoặc thay thế flags theo toolchain type. Không thêm fragment này cho Windows build mà kỳ vọng `cl.exe` hiểu mọi GNU flags.

### 12.2. Swift flags cũng thuộc Swift compiler

Swift compile options qua `SwiftCompile`:

```kotlin
import org.gradle.language.swift.tasks.SwiftCompile

tasks.withType<SwiftCompile>().configureEach {
    compilerArgs.add("-warnings-as-errors")
}
```

Đây là **mảnh cấu hình bổ sung** để nâng warnings thành errors trong Swift compiler có hỗ trợ flag; kiểm compiler version trước khi đưa vào CI. Không dùng `javac -Xlint` cho Swift source.

### 12.3. C++ Standard version và compiler support

C++17 cần compiler hỗ trợ `-std=c++17` (GCC/Clang) hoặc `/std:c++17` (MSVC). Nếu không định nghĩa compiler args trong Gradle script, compiler sẽ dùng default standard của toolchain, có thể khác nhau giữa máy.

Lab cố tình dùng C++ code tương thích những phiên bản cũ hơn để `cpp-application` sample đơn giản; **manual compile** đặt `-std=c++17` để test explicit standard.

Nếu project thực cần C++20/C++23, pin compiler/SDK support và cấu hình flags theo toolchain; không cố chọn Java 20/23 trong `java.toolchain` để kiểm soát C++ language mode.

## 13. Vì sao một binary đúng trên Linux có thể sai trên Windows/macOS?

### 13.1. Format khác nhau

- ELF là executable/object format phổ biến của Linux.
- Mach-O là executable format của macOS.
- PE/COFF là executable/object format của Windows.

Một file Linux ELF đổi tên thành `app.exe` không trở thành Windows executable.

### 13.2. Libraries và ABI

Dù compiled source giống nhau, C++ tiêu chuẩn không bảo đảm **binary ABI** giữa MSVC và GCC/Clang. Cần kiểm name mangling, standard libraries, compiler flags, exception ABI, struct layout, runtime dependencies và deployment target.

Swift trên Linux và macOS có toolchain/runtime khác nhau. App Swift macOS có thể phụ thuộc Apple SDK; app Swift Linux có thể phụ thuộc Swift runtime/stdlib và system libraries. Không copy executable từ một OS khác sang máy đích chỉ vì `swift --version` in cùng version major.

### 13.3. ARM64 và x86_64

Apple Silicon host có thể xây arm64; Linux CI nhiều khi là x86_64. Target machines nên được ghi rõ trong release artifacts: ví dụ `linux-x86_64-debug` và `macos-arm64-release`. Không upload nhiều binaries khác architecture dưới cùng mutable filename `app` rồi mặc định chọn file đầu tiên trong deploy job.

### 13.4. Link-time và run-time checks

- `ldd ./app` trên Linux giúp xem shared libs trong nhiều trường hợp, nhưng không nên chạy tool untrusted mà không cách ly.
- `otool -L ./app` trên macOS xem dylib dependencies.
- `dumpbin /DEPENDENTS app.exe` hoặc công cụ Visual Studio tương ứng trên Windows xem DLL dependencies.
- Chạy executable trong **runtime environment đại diện** để xác nhận loader, symbols, permissions và output.

Output từ các công cụ trên là **environment-dependent**, không có một stdout cố định.

## 14. Caching, incremental compilation và tính đúng

Tài liệu Gradle cho biết `CppCompile` và `SwiftCompile` tasks có hỗ trợ incremental build và Build Cache. Nhưng điều này không có nghĩa:

- Mọi task link/install/test đều cacheable.
- Binary giữa Linux và Windows có thể dùng chung một cache entry hợp lệ.
- Thay đổi compiler/flags/headers/SDK không làm ảnh hưởng outputs.
- Remote cache an toàn khi untrusted runners có write access.
- Task bị `FROM-CACHE` chứng minh runtime correctness.

### 14.1. Task inputs trong native build

Tùy task/compiler, những inputs có thể ảnh hưởng output:

- Source files và include headers.
- Compiler toolchain và version.
- Compiler args/preprocessor macros.
- Target OS/arch/ABI.
- Linker args và link-time dependencies.
- Swift module/interface dependencies.
- Generated source/headers và tool-generated metadata.
- Environment-sensitive compiler paths/SDK.

Khi viết custom Gradle task để gọi external native tools, cần khai báo inputs/outputs chuẩn; nếu không, Gradle có thể đánh dấu `UP-TO-DATE` sai hoặc cache stale outputs.

### 14.2. Thử correctness với cache tắt

Trong một CI diagnostic job:

```bash
./gradlew clean assembleDebug --no-build-cache --console=plain
```

Lệnh này giúp giảm phụ thuộc vào cached **task outputs**. Nó không tự tạo môi trường sạch hoàn toàn: dependency cache, compiler installations và Gradle daemon vẫn có thể tồn tại. Với release quan trọng, dùng clean runner/Gradle User Home phù hợp và ghi versions.

### 14.3. Remote cache poisoning và sensitive artifacts

Remote cache là nơi chia sẻ outputs; kẻ có quyền push có thể ảnh hưởng consumer builds. Với native binary đặc biệt nguy hiểm vì output có thể được thi hành trực tiếp. Quy định:

- Chỉ trusted CI được quyền PUSH, enforced bởi server ACL.
- Untrusted fork PR không dùng writer token.
- Không cache task outputs chứa signing keys, tokens hoặc dữ liệu nhạy cảm.
- Dùng TLS, artifact provenance và kiểm release digest.
- Không coi `isPush=false` ở client là server-side authorization.

## 15. Native build trong CI/CD

### 15.1. Matrix theo ngôn ngữ và host

Một matrix có kiểm soát:

| CI job | Runner | Toolchain yêu cầu | Build/test |
| --- | --- | --- | --- |
| `cpp-linux` | Linux x86_64 | GCC/Clang + libc/headers | C++ debug/release + test |
| `cpp-windows` | Windows x86_64 | MSVC Build Tools + Windows SDK | C++ debug/release + test |
| `cpp-macos` | macOS x86_64/arm64 | Xcode/Apple Clang + SDK | C++ debug/release + test |
| `swift-linux` | Linux x86_64 | Official Swift + dependencies | Swift debug/release + XCTest |
| `swift-macos` | macOS x86_64/arm64 | Official Swift/Xcode + SDK | Swift debug/release + XCTest |

Không cần ép Swift Gradle build chạy trên Windows chỉ để matrix “đủ ba OS”. Windows Swift work nếu có yêu cầu phải kiểm support của compiler **và** Gradle plugin riêng trước khi tuyên bố.

### 15.2. Các bước runner cần xác minh

Trước Gradle:

```bash
java -version
./gradlew --version
uname -s
uname -m
c++ --version
```

Với Swift runner:

```bash
swiftc --version
./gradlew --version
```

Với MSVC:

```powershell
java -version
.\gradlew.bat --version
where.exe cl
where.exe link
```

Nếu một lệnh kiểm compiler không có sẵn, phải cài đúng toolchain hoặc dùng runner image đã chuẩn hóa. Không chỉ cài Java 17 rồi coi C++/Swift build sẵn sàng.

### 15.3. CI script cho C++ lab trên Linux

Runner đã cài JDK/Gradle Wrapper/GCC:

```bash
set -eu
java -version
g++ --version

./gradlew clean assembleDebug installDebug --no-build-cache --console=plain
./build/exe/main/debug/nativeCppLab

mkdir -p build/manual
g++ -std=c++17 -O0 -Isrc/main/headers \
  src/main/cpp/sum.cpp src/test/manual/sum_test.cpp \
  -o build/manual/sum_test
./build/manual/sum_test
```

Yêu cầu hai dòng output từ hai chương trình tương ứng:

```text
native-cpp=OK; total=55
cpp-unit-smoke=PASS
```

Đây là **một CI script kiểm nội dung lab**, không thay cho C++ unit-test framework/ABI checks trong ứng dụng thật.

### 15.4. CI script cho Swift lab trên Linux/macOS

Runner đã cài JDK/Gradle Wrapper/official Swift:

```bash
set -eu
java -version
swiftc --version

./gradlew clean assembleDebug installDebug --no-build-cache --console=plain
./build/exe/main/debug/NativeSwiftLab
```

Dòng output của executable:

```text
native-swift=OK; total=55
```

Nếu áp dụng thêm `xctest` và có tests được discover, phải chạy `check` và lưu reports; không chỉ build executable rồi ghi “unit test PASS”.

### 15.5. Pin versions và nguồn công cụ

Một runner image thay đổi compiler version có thể tạo binary khác. Lưu:

- Gradle Wrapper version và checksum.
- Java runtime của Gradle.
- Compiler versions (GCC/Clang/MSVC/Swift).
- Xcode/SDK version hoặc Linux distro/glibc.
- CPU architecture/target machines.
- Compiler/linker flags.
- Test results và executable smoke-test outputs.
- Artifact checksums, provenance và CI run ID.

**Build once, verify, promote:** sau khi xác minh binary trên đúng runner/target, đưa binary cùng digest qua staging/production, không âm thầm rebuild trong deploy job có toolchain khác.

## 16. Java 17 dùng kiểm thử native executable như một consumer

Trong một hệ sinh thái Java + native, Gradle có thể xây ứng dụng Java và native binaries riêng. Để quan sát ranh giới, ta tạo **Java 17 helper tùy chọn** chỉ nhận đường dẫn executable và expected stdout, chạy process rồi kiểm exit code/output.

**File độc lập `tools/NativeSmoke.java`** (đặt trong bất kỳ lab nào):

```java
import java.nio.charset.StandardCharsets;

public final class NativeSmoke {
    private NativeSmoke() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: NativeSmoke <executable-path> <expected-output>"
            );
        }

        Process process = new ProcessBuilder(args[0])
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
        ).trim();

        int exit = process.waitFor();

        if (exit != 0 || !output.equals(args[1])) {
            throw new IllegalStateException(
                    "Native smoke failed: exit=" + exit
                    + ", output=" + output
            );
        }

        System.out.println("native-smoke=PASS");
    }
}
```

Biên dịch/chạy trên Linux/macOS **sau C++ Gradle build**:

```bash
mkdir -p build/native-smoke-java
javac -d build/native-smoke-java tools/NativeSmoke.java
java -cp build/native-smoke-java NativeSmoke \
  ./build/exe/main/debug/nativeCppLab \
  'native-cpp=OK; total=55'
```

**Stdout chính xác của Java verifier khi child executable đúng:**

```text
native-smoke=PASS
```

Dùng cho Swift tương tự, đổi executable path và expected string:

```bash
java -cp build/native-smoke-java NativeSmoke \
  ./build/exe/main/debug/NativeSwiftLab \
  'native-swift=OK; total=55'
```

Trước đó phải compile `tools/NativeSmoke.java` trong chính Swift lab hoặc copy **source helper đã review** vào test tooling phù hợp. Code này **không được Gradle native plugin tự gọi**, mà là external verification tool có thể được CI điều phối. Nó không sử dụng JNI và không tự load native library vào JVM.

### 16.1. Vì sao Java helper hữu ích nhưng chưa đủ?

Nó chứng minh native process khởi động, exit code 0 và output đúng trong một happy path. Nhưng:

- Không xác minh các edge cases nếu chương trình không nhận input.
- Không kiểm APIs/ABI của shared library.
- Không chứng minh binary chạy trên OS/architecture khác.
- Không thay security scan, signing, dependency verification hoặc native test framework.
- Không cung cấp cách build C++/Swift; nó chỉ là một consumer smoke test.

## 17. Tích hợp Java với C++/Swift: JNI, JNA và boundaries

Trong dự án Java có chức năng native, có thể dùng JNI/JNA/Panama FFM (tùy Java version) để kết nối JVM và native libraries. Đây là **một bài toán khác** với việc Gradle `cpp-application` sinh executable độc lập.

### 17.1. JNI không chỉ là thêm `cpp-library`

Một tích hợp JNI thực sự cần:

1. Java method `native` và generated JNI headers theo đúng JDK.
2. C/C++ code sử dụng JNI headers/ABI phù hợp.
3. Biên dịch shared library cho từng target OS/arch.
4. Runtime `System.loadLibrary`/library search path hoặc extraction policy đúng.
5. Kiểm Java↔native contract, memory/resource lifetime và exception boundaries.
6. Package native binaries theo classifier/OS/arch phù hợp.

Gradle Java toolchain chọn `javac`, nhưng C++ plugin cần native compiler và JDK JNI headers. Không mặc định `java-library` tự thêm C++ tasks hay load library.

### 17.2. Swift và Java interop

Swift native binaries và Java JVM không dùng chung ABI tự động. Nếu phải gọi Swift từ Java, thường cần C ABI bridge, shared library, JNI/JNA/FFM hoặc IPC theo kiến trúc. Không đặt `.swift` trong `src/main/java` rồi kỳ vọng Gradle Java plugin compile nó.

### 17.3. Tách build theo modules

Một multi-project build có thể có:

```text
root/
├── settings.gradle.kts
├── java-client/     (Java plugin)
├── native-core/     (cpp-library plugin)
└── integration/     (JNI wiring + runtime smoke tests)
```

Mỗi subproject có plugin/toolchain riêng. Việc nối artifacts giữa chúng phải được khai báo bằng variant-aware dependency/task dependencies phù hợp; không copy file binary theo path ngẫu nhiên rồi cho rằng Gradle biết task dependency.

## 18. IDE integration

### 18.1. Visual Studio

Gradle có Visual Studio plugin hỗ trợ tạo project/solution cho C++ builds. Nó **không thay** Visual C++ compiler/Windows SDK và không bảo đảm toolchains trên Linux/macos được cài qua Visual Studio.

Khi IDE và CLI có khác biệt:

- Xem MSVC environment và Windows SDK.
- Kiểm Gradle Wrapper/Java runtime.
- Kiểm selected variant/architecture và preprocessor definitions.
- Đọc compiler/linker diagnostics từ Gradle Build output.
- Đồng bộ generated project files nếu cấu hình source/variant đổi.

### 18.2. Xcode

Gradle Xcode plugin có thể sinh Xcode workspace/project tương ứng C++ hoặc Swift native components và để IDE ủy thác build cho Gradle. Nhưng Xcode vẫn cần Apple SDK và active developer directory phù hợp.

Không coi việc Xcode có thể mở workspace là bằng chứng `./gradlew clean build` pass trên CI. CLI + native tests + runtime smoke mới là gate độc lập.

### 18.3. CLion và những IDE khác

CLion/CMake/Gradle import support phụ thuộc IDE/plugin. Nếu IDE tự chọn compiler khác Gradle, có thể xảy ra “IDE chạy, CLI fail”. Lưu cả hai toolchain versions, task command và build arguments; ưu tiên Wrapper và CI matrix làm chuẩn khi điều tra.

## 19. Chẩn đoán theo thông báo lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cần kiểm |
| --- | --- | --- |
| `No tool chain is available` | Compiler không cài/không được discover/không hỗ trợ target | GCC/Clang/MSVC/Swift path + OS/arch |
| `Compiler executable not found` | PATH, Visual Studio environment hoặc Xcode active path sai | `which`/`where.exe`/`xcrun` |
| `cpp-application` build fail trước tasks | Kotlin/Groovy DSL/plugin/version sai | `plugins` block, Wrapper, `--stacktrace` |
| `No C++ source` | File ở thư mục không đúng | `src/main/cpp` |
| `No Swift source` | File ở `Sources/...` thay vì Gradle convention | `src/main/swift` hoặc `source.from` |
| `fatal error: header not found` | Missing header/include dirs hoặc SDK | `src/main/headers`, public/private headers |
| `cannot find -l...` | Native link library chưa có hoặc `-L` sai | Link dependencies, sysroot |
| `undefined reference` | Thiếu object/library hoặc ABI/link order | `linkDebug` stderr + symbols |
| `LNK2019 unresolved external symbol` | MSVC linker thiếu implementation/import lib | Build/link options, target ABI |
| `unsupported option -Wall` | Gửi GCC flag tới MSVC | Toolchain-aware flags |
| `unsupported source version` | C++/Swift compiler không hỗ trợ language features | Compiler version/flags |
| `wrong architecture` / `bad CPU type` | Host/target architecture mismatch | `uname -m`, targetMachines, binary inspection |
| `Exec format error` | Linux cố chạy binary khác format/arch | `file`, OS/arch |
| `dyld: Library not loaded` | macOS shared library path/rpath sai | `otool -L` và install layout |
| `error while loading shared libraries` | Linux loader thiếu `.so` tương ứng | `ldd`, install layout, library paths |
| `DLL not found` | Windows thiếu runtime DLL/SDK | `dumpbin`, MSVC redistributable |
| `swiftc not found` | Swift chưa cài hoặc PATH sai | Official Swift toolchain |
| Swift Gradle build trên Windows không hoạt động | Native Swift plugin không hỗ trợ host Windows | Chạy macOS/Linux runner |
| `XCTest tests not discovered` | Test source/runner/toolchain configuration | `src/test/swift`, plugin `xctest`, reports |
| C++ `check` xanh nhưng 0 native tests | Chưa tích hợp `cpp-unit-test`/framework | Task graph/test report |
| `FROM-CACHE` nhưng binary sai | Thiếu declared inputs hoặc untrusted cache | Rebuild no-cache, ACL, hashes |
| `gradlew --version` pass nhưng native build fail | JVM Gradle đúng, native SDK/compiler thiếu | Compiler/linker/toolchain availability |
| Native `assemble` pass nhưng runtime fail | ABI/shared libs/permissions | Installed binary smoke test |
| CI khác máy developer | Compiler/SDK/PATH/arch khác | Toolchain matrix và logs |

### 19.1. Cách đọc lỗi đúng thứ tự

1. Dùng `./gradlew --version` kiểm Gradle/JDK runtime.
2. Dùng `./gradlew tasks --all` biết task variant được tạo.
3. Kiểm host OS/arch và compiler binaries/installations.
4. Chạy **compiler trực tiếp** với chương trình tối thiểu để xác minh toolchain.
5. Chạy `./gradlew assembleDebug --info --stacktrace --console=plain`.
6. Nếu `compileDebugCpp/Swift` fail, đọc compiler stderr đầu tiên có nghĩa.
7. Nếu `linkDebug` fail, kiểm symbols, target ABI và libs paths.
8. Nếu `installDebug`/run fail, kiểm native runtime dependencies.
9. Nếu tests fail, xem native test runner/report chứ không chỉ wrapper Gradle.
10. Khi đã sửa, chạy full CI matrix; không chỉ một OS.

### 19.2. Kiểm compiler/language version

GCC/Clang:

```bash
g++ --version
clang++ --version
```

Swift:

```bash
swiftc --version
```

MSVC trong Developer Shell:

```powershell
cl
```

Output có thể khác nhau theo vendor, toolchain và release; không nên hardcode một version trong tài liệu nếu không pin image và không có bằng chứng nó tồn tại.

## 20. Yêu cầu bảo mật và reproducibility

Native compilation là chạy code ngoài JVM. Build scripts, compiler plugins, linkers và test runners có thể truy cập filesystem, CI secrets và network tùy quyền process.

Quy tắc tối thiểu:

- Dùng Gradle Wrapper đã được xác minh; không lấy wrapper JAR từ nguồn không tin.
- Pin OS/arch/compiler/SDK versions cho release CI khi có thể.
- Review native dependencies, thư viện prebuilt, hashes và licenses.
- Không cấp signing/deployment keys cho untrusted PR build logic.
- Chỉ publish từ protected CI, không từ máy developer bất kỳ.
- Không đưa private keys/API tokens vào generated source hoặc native binaries.
- Bảo vệ remote cache bằng server-side write ACL.
- Tạo artifact digest/provenance, smoke-test native executable rồi promote **cùng bytes**.
- Tách debug symbols nếu có dữ liệu nhạy cảm; đừng upload symbol bundles ra public không kiểm soát.
- Kiểm reproducible build inputs: timestamps, absolute paths, locale, random seeds, compiler versions.
- Chạy static analysis/sanitizers (ASan/UBSan/TSan, khi compiler/target hỗ trợ) cho project C++ quan trọng.
- Kiểm bản build trên target runtime thật, không chỉ compile trên host.

### 20.1. Vì sao checksum thay đổi giữa compilers?

Cùng C++ source nhưng GCC và Clang có thể tạo assembly/object khác. Swift compiler versions cũng có thể khác metadata/optimizations. Byte-for-byte hash khác **không tự nói build sai**, nhưng binary được đưa vào production phải là binary đã được kiểm thử/được phép qua đúng artifact identity.

### 20.2. Phân phối native binary

Native apps thường cần thêm:

- Target-specific binary.
- Shared runtime libraries.
- Platform installer/launcher.
- Debug symbols tùy policy.
- License notices.
- Code signing/notarization cho Apple hoặc Windows khi yêu cầu.
- Runtime health/smoke tests và rollback artifact.

`assembleRelease` không tự ký hoặc notarize ứng dụng. Swift/C++ Gradle core plugins cũng không thay một release pipeline dành riêng cho App Store/Apple platforms.

## 21. Một checklist trước khi mở PR native Gradle build

1. Đã chọn đúng plugin `cpp-application`/`cpp-library`/`swift-application`/`swift-library` chưa?
2. Có tránh legacy native plugins khi bắt đầu project mới không?
3. Máy chạy Gradle có JVM hợp lệ không?
4. C++ compiler hoặc Swift toolchain **thực sự** được cài không?
5. Windows MSVC workloads/SDK hoặc macOS Xcode/CLI tools đã đủ chưa?
6. Linux PATH/sysroot/system headers đã đúng chưa?
7. Source files nằm đúng `src/main/cpp` hoặc `src/main/swift` chưa?
8. Header public/private được phân loại đúng chưa?
9. Có explicit targetMachines nếu sản phẩm yêu cầu nhiều architectures không?
10. Có hiểu `targetMachines` không tự tạo cross compiler không?
11. Có phân biệt debug/release cùng binary path/linkage không?
12. Có kiểm compile rồi link rồi runtime smoke riêng không?
13. Có native tests thật sự chạy không, hay chỉ `check` với zero tests?
14. Có kiểm unit test runner exit codes và reports không?
15. Có dùng ABI phù hợp giữa native dependencies/toolchains không?
16. Có phân biệt compiler args GCC/Clang/MSVC không?
17. Có Swift module/runtime compatibility test khi upgrade Swift compiler không?
18. Có khai báo native dependencies theo variant/`api`/`implementation` không?
19. Có kiểm deployed shared-library dependencies không?
20. Có CI matrix cho Linux/macOS/Windows theo ngôn ngữ thực được hỗ trợ không?
21. Có ghi Gradle/Java/compiler/SDK versions trong CI logs không?
22. Có kiểm output binary digest/source commit và promotion không rebuild không?
23. Có tránh secrets trong native artifacts và remote cache không?
24. Có test clean build khi nghi stale caches không?
25. Có scripts/paths dùng được trên Windows lẫn Unix khi cần không?
26. Có xác minh IDE build và CLI Wrapper build nhất quán không?
27. Có rollback/release strategy riêng từng OS/arch không?
28. Có artifact naming phân biệt target + build type không?
29. Có đánh giá xem Gradle native plugin hay CMake/SwiftPM phù hợp yêu cầu thực tế hơn không?
30. Có documentation cho người mới setup từng host OS không?

## 22. Bài tập thực hành

**Bài tập A — phân biệt toolchains.** Giải thích vì sao Java 17 và Gradle Wrapper đủ để chạy `./gradlew --version` nhưng không đủ để compile C++/Swift.

**Bài tập B — C++ host.** Kiểm `uname`/`where.exe`, GCC/Clang/MSVC, SDK và runtime libraries. Viết checklist cho một Linux/Windows/macOS host thực tế.

**Bài tập C — dựng C++ lab.** Tạo `cpp-native-lab` theo mục 5, chạy `assembleDebug installDebug`, xác nhận executable in `native-cpp=OK; total=55`.

**Bài tập D — compile trực tiếp.** Biên dịch cùng C++ source bằng `g++`/`clang++`/`cl` theo host. So kết quả với Gradle output và nêu vai trò của Gradle.

**Bài tập E — C++ unit smoke.** Viết/biên dịch `sum_test.cpp` theo mục 6, quan sát `cpp-unit-smoke=PASS`, giải thích vì sao `check` chưa tự biết test này.

**Bài tập F — CPP unit-test plugin.** Tích hợp `cpp-unit-test` và framework thật vào một bản sao. Chứng minh `check` chạy tests và fail khi assertion sai.

**Bài tập G — Swift host.** Kiểm `swiftc --version`, PATH, Xcode/Swift installation và SDK. Vì sao Swift Gradle app không tương đương Windows `cpp-application`?

**Bài tập H — dựng Swift lab.** Tạo `swift-native-lab`, chạy `assembleDebug`, tìm binary và xác nhận `native-swift=OK; total=55`.

**Bài tập I — Swift compiler trực tiếp.** Dùng `swiftc` build same `main.swift`, so output và nêu trường hợp Gradle failure chỉ do toolchain discovery.

**Bài tập J — Swift XCTest.** Áp dụng `xctest` trong bản sao, tạo tests phù hợp, xác nhận test reports và lỗi khi assertion sai.

**Bài tập K — variants.** So `assembleDebug` với `assembleRelease`; tìm object/executable outputs và giải thích debug symbols/optimization.

**Bài tập L — targetMachines.** Thử khai báo Linux x86_64 và macOS x86_64 trong project Linux. Giải thích tại sao Gradle không tự cài macOS SDK/cross linker.

**Bài tập M — Linux/Windows ABI.** Giải thích vì sao một ELF x86_64 không chạy được trên Windows x86_64 chỉ bằng đổi đuôi `.exe`.

**Bài tập N — library.** Chuyển sum code thành `cpp-library`, phân loại `src/main/public` và `headers`; build shared/static variants.

**Bài tập O — API dependency.** Một native library public header phụ thuộc thư viện khác. Nêu khi nào dùng `api` thay `implementation`.

**Bài tập P — compiler flags.** Thiết kế task configuration dùng `-Wall` với GCC/Clang và `/W4` với MSVC, tránh truyền nhầm flag.

**Bài tập Q — shared library runtime.** Build app dùng một `.so`/`.dylib`/`.dll`, kiểm loader paths và installed layout khi deploy.

**Bài tập R — Gradle cache.** So no-cache với cache-hit. Vì sao không coi `FROM-CACHE` là chứng minh native binary an toàn?

**Bài tập S — Java 17 verification.** Dùng `tools/NativeSmoke.java` gọi native C++/Swift binary, xác nhận `native-smoke=PASS` và kiểm behavior khi expected stdout sai.

**Bài tập T — CI matrix.** Thiết kế các jobs cho C++ Linux/Windows/macOS và Swift Linux/macOS; nêu compiler/SDK/setup/test/digest gates cho từng job.

**Bài tập U — diagnose linker.** Cố tình không compile/link `sum.cpp` trong bản sao C++ lab. Vì sao lỗi link khác lỗi `#include` thiếu?

**Bài tập V — security.** Thiết kế remote cache policy chỉ trusted CI được PUSH và không lưu signing keys trong artifact.

**Bài tập W — migration.** Nếu chuyển từ CMake/SwiftPM sang Gradle, lập bảng những behaviors phải giữ: source layout, dependency graph, variants, tests, packaging và IDE integration.

**Bài tập X — release.** Với một ứng dụng native multi-target, đặt immutable artifact names/digests cho Linux x86_64, macOS arm64 và Windows x86_64 rồi mô tả cách promote không rebuild.

### Câu hỏi tự kiểm tra

1. Gradle native plugin khác Java Application plugin ở bước compile ra sao?
2. Plugin ID để tạo C++ executable là gì?
3. Plugin ID để tạo Swift library là gì?
4. Gradle Swift plugin hỗ trợ host OS nào theo tài liệu chính thức?
5. Trên Windows, công cụ nào thường cần để Gradle build C++?
6. Trên macOS, vì sao Xcode/SDK/`xcode-select` ảnh hưởng compiler selection?
7. Trên Linux, Gradle phát hiện GCC/Clang/Swift compiler bằng cách nào?
8. `java.toolchain` có tự cài `g++` hoặc `swiftc` không?
9. C++ conventional source directory là gì?
10. Swift conventional source directory là gì?
11. Private C++ headers và public headers khác nhau ở đâu?
12. `compileDebugCpp` khác `linkDebug` ở giai đoạn nào?
13. `installDebug` hữu ích khi executable có shared runtime libraries ra sao?
14. `assemble` mặc định thường chọn build type nào?
15. Vì sao `check` chưa tự chạy tests nếu không có native test plugin?
16. `cpp-unit-test` cần thêm thành phần test nào để thực sự có assertions?
17. `xctest` chạy loại tests nào trên macOS/Linux?
18. `targetMachines` có tự cung cấp Windows SDK trên Linux không?
19. OS và architecture có bao gồm mọi ABI/runtimes constraints không?
20. Shared và static C++ library khác nhau thế nào?
21. `api` dependencies nên dùng khi public header lộ loại dependency nào?
22. Vì sao compiler arguments cho GCC và MSVC không hoàn toàn giống nhau?
23. Binary compiled bằng Clang có chắc byte-identical với GCC không?
24. SwiftPM layout khác Gradle Swift layout mặc định ở đâu?
25. Khi `swiftc` chạy tốt nhưng Gradle fail, nên kiểm những gì?
26. Khi Gradle compile pass nhưng executable fail, nên điều tra layer nào?
27. Vì sao native CI cần OS/arch matrix?
28. Có nên dùng remote cache untrusted PR writer cho release binaries không?
29. Java `ProcessBuilder` trong lab là test gì, và không phải JNI ra sao?
30. Khi nào nên ưu tiên CMake/SwiftPM/Xcode thay vì native Gradle plugins?

## 23. Tài liệu chính thức

- [Gradle — Building C++ Projects](https://docs.gradle.org/current/userguide/building_cpp_projects.html)
- [Gradle — C++ Application Plugin](https://docs.gradle.org/current/userguide/cpp_application_plugin.html)
- [Gradle — C++ Library Plugin](https://docs.gradle.org/current/userguide/cpp_library_plugin.html)
- [Gradle — C++ Unit Test Plugin](https://docs.gradle.org/current/userguide/cpp_unit_test_plugin.html)
- [Gradle — Testing C++ Projects](https://docs.gradle.org/current/userguide/cpp_testing.html)
- [Gradle — Building Swift Projects](https://docs.gradle.org/current/userguide/building_swift_projects.html)
- [Gradle — Swift Application Plugin](https://docs.gradle.org/current/userguide/swift_application_plugin.html)
- [Gradle — Swift Library Plugin](https://docs.gradle.org/current/userguide/swift_library_plugin.html)
- [Gradle — XCTest Plugin](https://docs.gradle.org/current/userguide/xctest_plugin.html)
- [Gradle — Testing Swift Projects](https://docs.gradle.org/current/userguide/swift_testing.html)
- [Gradle — Native Plugin Reference](https://docs.gradle.org/current/userguide/standard_plugins.html)
- [Gradle — Xcode IDE Plugin](https://docs.gradle.org/current/userguide/xcode_plugin.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Swift — Official Installation](https://www.swift.org/install/)

**Ghi nhớ:** Gradle có plugins hiện đại để build C++/Swift, nhưng Gradle **không thay compiler/linker/SDK của host**. C++ dùng GCC/Clang/Visual C++ theo OS; Swift Gradle plugin hiện nhắm official Swift toolchain trên macOS/Linux. `targetMachines` mô tả variants chứ không tự tạo cross compiler. Hãy phân biệt Gradle JVM với native toolchain, chạy compile → link → native tests → runtime smoke trên đúng target, kiểm dependencies/ABI và CI matrix. Chỉ coi một native release sẵn sàng khi binary đã được xác minh trên môi trường tương ứng và **chính artifact đó** được triển khai.