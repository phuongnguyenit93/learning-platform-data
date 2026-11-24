# Thư viện .so, .dll, .dylib và nền tảng đích

Khi Spring Boot được biên dịch thành **GraalVM Native Image**, kết quả là một executable dành cho một hệ điều hành và kiến trúc CPU cụ thể. Tuy nhiên, ứng dụng vẫn có thể cần gọi mã native bên ngoài: thư viện C/C++ của nhà cung cấp, driver, thư viện xử lý ảnh, mã tính toán hoặc thành phần tích hợp hệ thống. Những thư viện chia sẻ này thường có phần mở rộng **.so trên Linux, .dll trên Windows và .dylib trên macOS**.

Để ứng dụng chạy được, không chỉ cần có file thư viện. Executable, thư viện JNI và các thư viện hệ thống mà chúng phụ thuộc phải tương thích về **OS, CPU architecture, ABI, calling convention, libc/runtime và phiên bản symbol**. Một file build thành công trên máy phát triển vẫn có thể không nạp được trong container production nếu khác nền tảng hoặc thiếu dependency.

Bài học thuộc chương **Serialization và JNI** của mô-đun `SPRING_BOOT_NATIVE_IMAGE`. Ta sẽ phân biệt native executable với JNI shared library, biên dịch một thư viện JNI nhỏ, nạp thư viện theo tên hoặc đường dẫn, kiểm tra phụ thuộc động và lựa chọn nền tảng build/container phù hợp.

## 1. Phân biệt executable native và shared library

GraalVM Native Image tạo một chương trình native từ ứng dụng Java. Nếu ứng dụng dùng JNI để gọi mã C/C++, thư viện JNI thường vẫn là một file riêng được nạp trong quá trình chạy.

| Thành phần | Vai trò | Ví dụ trên Linux |
| --- | --- | --- |
| Native executable | Chương trình Spring Boot sau khi GraalVM biên dịch | `orders-service` |
| JNI shared library | C/C++ code cung cấp hàm native cho Java | `libimagecodec.so` |
| Native dependency của JNI library | Thư viện mà JNI library liên kết hoặc nạp tiếp | `libjpeg.so`, `libstdc++.so` |
| System runtime | Loader, libc và các thư viện hệ thống | glibc, dynamic linker |

Một JNI library không tự động được nhúng vào native executable chỉ vì ứng dụng có khai báo `native` method. Nếu dùng `System.loadLibrary(...)`, file thư viện và các dependency cần thiết phải có sẵn trong môi trường runtime, trừ khi dự án chủ động cấu hình một cách liên kết khác.

Ba loại file thường gặp:



| Hệ điều hành | Định dạng phổ biến | Ví dụ tên |
| --- | --- | --- |
| Linux | ELF shared object, hậu tố `.so` | `libimagecodec.so`, `libimagecodec.so.2` |
| Windows | PE/COFF dynamic-link library, hậu tố `.dll` | `imagecodec.dll` |
| macOS | Mach-O dynamic library, hậu tố `.dylib` | `libimagecodec.dylib` |

Không thể đổi tên `libimagecodec.so` thành `imagecodec.dll` để dùng trên Windows. Nội dung file, định dạng object, symbol, ABI và loader của từng nền tảng khác nhau.

### 1.1. Shared library và static library

Các hậu tố `.so`, `.dll`, `.dylib` thường chỉ thư viện được nạp động. Trên Linux, static archive thường là `.a`; trên Windows thường là `.lib`. Static archive được native linker dùng ở thời điểm build để đưa object code vào executable hoặc shared library; không thể truyền file `.a` cho `System.loadLibrary(...)`. Nếu một JNI `.so` được liên kết với static archive, phần code đó trở thành một phần của `.so`; nếu liên kết với shared library khác, dependency động vẫn phải có ở runtime.

## 2. Native library phải khớp với nền tảng đích

Một native artifact có thể được mô tả bằng tổ hợp:

- **Operating system:** Linux, Windows hoặc macOS.
- **CPU architecture:** x86_64/AMD64, AArch64/ARM64 và các kiến trúc được toolchain hỗ trợ.
- **Binary format:** ELF, PE/COFF hoặc Mach-O.
- **ABI và calling convention:** cách truyền tham số, trả kết quả, quản lý stack và symbol.
- **C runtime:** ví dụ glibc hoặc musl trên Linux; runtime tương ứng trên Windows/macOS.
- **Runtime dependency:** phiên bản thư viện hệ thống mà binary cần khi load.

Ví dụ ma trận:

| Build target | Executable | JNI library | Có thể chạy trực tiếp trên |
| --- | --- | --- | --- |
| Linux x86_64, glibc | Linux ELF x86_64 | ELF x86_64 .so | Linux x86_64 có runtime tương thích |
| Linux AArch64, glibc | Linux ELF AArch64 | ELF AArch64 .so | Linux ARM64 tương thích |
| Windows x86_64 | PE x86_64 .exe | PE x86_64 .dll | Windows x86_64 |
| macOS ARM64 | Mach-O ARM64 | Mach-O ARM64 .dylib | macOS ARM64 tương thích |

Một ứng dụng Linux x86_64 không thể nạp JNI library Windows x64 hoặc macOS ARM64. Cùng kiến trúc CPU cũng chưa đủ: Linux glibc và Linux musl là hai môi trường ABI khác nhau, và một binary build với symbol version glibc mới có thể không chạy trên hệ thống cũ hơn.

### 2.1. GraalVM build cho target nào?

Native Image thông thường tạo executable cho **OS và kiến trúc của môi trường build**, với toolchain native tương ứng. Không nên giả định có thể build trên Windows x86_64 một executable Linux ARM64 chỉ bằng cách đổi tên file hoặc đặt một property Maven.

Đối với các target khác nhau, cách dễ dự đoán nhất là build trên runner/container tương ứng:

- Linux x86_64: runner Linux AMD64 có GraalVM và compiler phù hợp.
- Linux ARM64: runner ARM64 hoặc môi trường build có hỗ trợ target ARM64 thực tế.
- Windows: runner Windows với toolchain C/C++ tương ứng.
- macOS: runner macOS cho kiến trúc mục tiêu.

Khả năng cross-compilation phụ thuộc GraalVM distribution, phiên bản, target và toolchain. Chỉ sử dụng khi tài liệu phiên bản xác nhận rõ cấu hình hỗ trợ. Trong CI đa nền tảng, nên tạo artifact riêng cho từng target và kiểm thử trên môi trường đích.

### 2.2. Không nhầm kiến trúc máy build với kiến trúc container

Máy phát triển có thể là Apple Silicon ARM64, nhưng image production cần chạy trên Linux AMD64. Docker Desktop có thể mô phỏng một số target bằng emulation, nhưng native compilation và kiểm thử hiệu năng qua emulation có thể khác đáng kể.

Hãy ghi lại target thực tế trong pipeline, ví dụ:

- `linux/amd64`
- `linux/arm64`
- `windows/amd64`
- `darwin/arm64`

Tên target chỉ mô tả OS/architecture; vẫn cần xác minh libc, ABI và dependency.

## 3. JNI hoạt động như thế nào?

JNI (Java Native Interface) là cơ chế để Java gọi hàm được viết bằng C/C++ và cho phép mã native tương tác ngược với JVM/runtime Java thông qua JNI API.

Một luồng gọi cơ bản:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot bean
    participant Java as Java native method
    participant Loader as OS dynamic loader
    participant C as JNI shared library
    App->>Java: calculate(...)
    Java->>Loader: System.loadLibrary(...)
    Loader->>C: load .so / .dll / .dylib
    Java->>C: gọi JNI function
    C-->>Java: trả kết quả qua JNI
    Java-->>App: kết quả Java
~~~

Java khai báo một method có modifier `native`:

~~~java
package com.example.nativebridge;

import java.nio.file.Path;

public final class NativeMath {

    private NativeMath() {
    }

    // Gọi từ runtime startup sau khi Spring context bắt đầu khởi tạo.
    public static void loadLibrary() {
        String path = System.getenv("APP_NATIVE_LIBRARY");
        if (path == null || path.isBlank()) {
            System.loadLibrary("nativecalc");
        }
        else {
            System.load(Path.of(path).toAbsolutePath().toString());
        }
    }

    public static native long add(long left, long right);
}
~~~

Có thể gọi việc nạp thư viện từ một bean khởi tạo lúc runtime:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
class NativeLibraryInitializer implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        NativeMath.loadLibrary();
    }
}
~~~

Bean này minh họa việc nạp thư viện trong lifecycle khởi tạo của Spring. Nếu native function không bắt buộc ngay lúc startup, có thể nạp thư viện theo lifecycle khác phù hợp hơn.

Với `System.loadLibrary("nativecalc")`, truyền **tên logic** của thư viện, không ghi prefix `lib` hoặc hậu tố file. JVM/native runtime sẽ tìm tên file theo quy ước của nền tảng, ví dụ:

- Linux: `libnativecalc.so`
- macOS: `libnativecalc.dylib`
- Windows: `nativecalc.dll`

Nếu cần nạp một file theo đường dẫn tuyệt đối, dùng `System.load("/absolute/path/to/library")`. Phương thức này yêu cầu đường dẫn đầy đủ và phụ thuộc file thực sự tồn tại trên máy/container.

### 3.1. JNI function phía C

Có thể dùng `javac -h` để sinh header C từ Java native method. Header giúp tên hàm và chữ ký khớp với khai báo Java.

Ví dụ mã C tương ứng:

~~~c
#include <jni.h>
#include "com_example_nativebridge_NativeMath.h"

JNIEXPORT jlong JNICALL
Java_com_example_nativebridge_NativeMath_add(
        JNIEnv *env,
        jclass type,
        jlong left,
        jlong right) {
    return left + right;
}
~~~

Vì method trong ví dụ là `static native`, tham số thứ hai là `jclass`. Với instance native method, tham số đó là `jobject`. Không tự viết tên symbol theo cảm tính; dùng header được sinh hoặc cơ chế `RegisterNatives` và kiểm tra chữ ký JNI.

### 3.2. Sinh JNI header

Ví dụ với JDK tương ứng:

~~~bash
mkdir -p build/classes build/include build/native
javac -h build/include -d build/classes src/main/java/com/example/nativebridge/NativeMath.java
~~~

Lệnh tạo class và header trong thư mục build. Khi dự án dùng Maven/Gradle, có thể cấu hình một native build task riêng để sinh header và compile C; không nên đặt file sinh vào source tree đã commit nếu pipeline có thể tái tạo chúng.

## 4. Biên dịch JNI library trên từng nền tảng

Mã C ở phần trước có thể được biên dịch thành shared library, nhưng compiler, include directory và linker flag phụ thuộc OS.

### 4.1. Linux: tạo .so

Ví dụ dùng GCC hoặc Clang trên Linux x86_64:

~~~bash
cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o build/native/libnativecalc.so src/main/c/nativecalc.c
~~~

Ý nghĩa các tùy chọn:

- `-fPIC`: tạo position-independent code, thường cần cho shared object.
- `-shared`: tạo shared library thay vì executable.
- `-I`: thêm thư mục header JNI và header được sinh.
- `-o`: đặt tên output theo quy ước Linux.

Kiểm tra file:

~~~bash
file build/native/libnativecalc.so
readelf -h build/native/libnativecalc.so
nm -D build/native/libnativecalc.so
~~~

### 4.2. macOS: tạo .dylib

Ví dụ dùng Apple Clang trên macOS:

~~~bash
mkdir -p build/native
clang -dynamiclib -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" -Ibuild/include -o build/native/libnativecalc.dylib src/main/c/nativecalc.c
~~~

Kiểm tra binary và dependency:

~~~bash
file build/native/libnativecalc.dylib
otool -L build/native/libnativecalc.dylib
nm -gU build/native/libnativecalc.dylib
~~~

macOS dùng Mach-O và quy tắc install name / @rpath riêng. Nếu dylib phụ thuộc một dylib khác, phải bảo đảm install name và run path trỏ tới vị trí được đóng gói hợp lệ. Việc chỉ đặt file cạnh executable chưa chắc giải quyết mọi dependency lồng nhau.

### 4.3. Windows: tạo .dll

Ví dụ dùng Microsoft Visual C++ Build Tools trong Developer Command Prompt:

~~~bat
if not exist build\native mkdir build\native
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" src\main\c\nativecalc.c /link /OUT:build\native\nativecalc.dll
~~~

Tùy shell và cấu trúc project, cần tạo thư mục output trước. MSVC có thể cần cấu hình runtime phù hợp, và các DLL phụ thuộc (ví dụ Visual C++ runtime) phải có trên máy đích.

Kiểm tra:

~~~bat
dumpbin /HEADERS build\native\nativecalc.dll
dumpbin /DEPENDENTS build\native\nativecalc.dll
dumpbin /EXPORTS build\native\nativecalc.dll
~~~

Các lệnh minh họa giả định đã cài Visual Studio Build Tools và đang dùng developer environment có `cl.exe`/`dumpbin.exe` trong PATH.

## 5. Nạp thư viện theo tên hoặc đường dẫn

Có hai cách chính.

### 5.1. System.loadLibrary

~~~java
static {
    System.loadLibrary("nativecalc");
}
~~~

Cách này dùng tên logic, cho phép runtime/loader tìm thư viện theo quy ước và search path của nền tảng. Nó tiện khi thư viện được cài vào vị trí chuẩn hoặc search path đã được cấu hình.

### 5.2. System.load

~~~java
static {
    String path = System.getProperty("app.native.library");
    if (path == null || path.isBlank()) {
        throw new IllegalStateException("Missing app.native.library");
    }
    System.load(Path.of(path).toAbsolutePath().toString());
}
~~~

Cách này dùng đường dẫn tuyệt đối. Nó hữu ích khi ứng dụng quản lý thư viện trong thư mục riêng, ví dụ một mount path trong container. Cần kiểm tra file tồn tại, quyền đọc và dependency của chính thư viện.

Không đưa đường dẫn từ HTTP request vào `System.load`. Chỉ cho phép đường dẫn do deployment cấu hình, giới hạn thư mục hợp lệ và bảo vệ quyền ghi vào thư mục chứa thư viện. Nạp native library đồng nghĩa đưa mã native vào process với quyền của process đó.

## 6. Runtime loader tìm shared library ở đâu?

Tìm thấy file JNI library chưa đủ; OS loader còn phải tìm được các dependency mà thư viện đó cần.

| Nền tảng | Các cơ chế thường gặp | Công cụ kiểm tra |
| --- | --- | --- |
| Linux | RPATH/RUNPATH, loader cache, thư mục chuẩn, `LD_LIBRARY_PATH` | `ldd`, `readelf -d`, `ldconfig -p` |
| macOS | install name, `@rpath`, `@loader_path`, `DYLD_LIBRARY_PATH` và cơ chế bảo mật hệ thống | `otool -L`, `otool -l` |
| Windows | DLL search order, thư mục ứng dụng, system directories và `PATH` | `dumpbin /DEPENDENTS`, Process Monitor |

### 6.1. Linux

Có thể chạy:

~~~bash
LD_LIBRARY_PATH=/opt/orders/native-libs ./target/orders-service
~~~

Đây là ví dụ cho process được khởi động trong shell có biến môi trường đó. Với production, nên cân nhắc RPATH/RUNPATH phù hợp, thư mục thư viện được quản lý và cách đóng gói nhất quán. Không dựa vào thư mục làm việc hiện tại để tìm thư viện.

Kiểm tra dependency:

~~~bash
ldd /opt/orders/native-libs/libnativecalc.so
readelf -d /opt/orders/native-libs/libnativecalc.so
~~~

`ldd` hữu ích trên artifact tin cậy trong môi trường kiểm tra. Với binary không tin cậy, ưu tiên công cụ đọc metadata tĩnh như `readelf -d` thay vì chạy qua cơ chế loader của hệ thống.

### 6.2. macOS

macOS có quy tắc install name và run path riêng. Có thể dùng:

~~~bash
otool -L /opt/orders/native-libs/libnativecalc.dylib
otool -l /opt/orders/native-libs/libnativecalc.dylib
~~~

Các token như `@rpath`, `@loader_path` và `@executable_path` giúp xác định vị trí tìm dependency tương đối. `DYLD_LIBRARY_PATH` có thể hữu ích khi debug, nhưng không phải lựa chọn triển khai phổ quát; cơ chế bảo vệ của macOS có thể ảnh hưởng các biến môi trường loader trong một số trường hợp.

### 6.3. Windows

Windows tìm DLL theo quy tắc loader search order. Đặt DLL trong thư mục ứng dụng hoặc cấu hình PATH theo cách kiểm soát được thường dễ dự đoán hơn phụ thuộc vào working directory. Tránh thêm thư mục có thể bị người dùng không tin cậy ghi vào PATH, vì điều đó tạo rủi ro DLL search-order hijacking.

Kiểm tra dependency trực tiếp bằng:

~~~bat
dumpbin /DEPENDENTS build\native\nativecalc.dll
~~~

Nếu một dependency DLL khác bị thiếu, lỗi có thể xuất hiện khi nạp thư viện chính dù file chính vẫn tồn tại.

## 7. ABI, libc và runtime dependency

Cùng định dạng .so không có nghĩa hai thư viện tương thích. Linux shared library còn phụ thuộc ABI, symbol version và C runtime.

### 7.1. glibc và musl

Các Linux distribution phổ biến như Debian/Ubuntu thường dùng glibc; Alpine Linux dùng musl. Một thư viện build trên môi trường glibc không thể mặc nhiên chạy trên Alpine musl. Lỗi có thể là loader không tìm thấy interpreter, thiếu symbol hoặc không tương thích libc.

Hướng xử lý:

- Build và chạy trên môi trường có libc tương thích.
- Dùng builder/runtime base image được lựa chọn có chủ đích.
- Nếu cần musl, dùng toolchain và cấu hình Native Image hỗ trợ musl đúng phiên bản.
- Kiểm tra dependency thực tế thay vì giả định file .so là portable giữa mọi Linux distribution.

### 7.2. Symbol version và phiên bản hệ thống

Một thư viện build trên distribution mới có thể tham chiếu symbol version mới của glibc hoặc thư viện hệ thống. Khi chạy trên distribution cũ hơn, loader có thể báo thiếu symbol dù kiến trúc đều là x86_64.

Cách giảm rủi ro là build trên baseline tương thích thấp nhất mà sản phẩm hỗ trợ, hoặc dùng builder/runtime image theo ma trận đã kiểm thử. Không nên build trên máy cá nhân mới nhất rồi giả định mọi server cũ đều chạy được.

### 7.3. C++ ABI và runtime

Nếu JNI wrapper gọi thư viện C++, còn phải xét:

- ABI của compiler/toolchain và thư viện C++ runtime.
- Phiên bản libstdc++/libc++ hoặc Microsoft Visual C++ runtime.
- Cách export symbol và name mangling.
- Quyền sở hữu bộ nhớ giữa hai phía; tránh cấp phát ở một runtime rồi giải phóng bằng runtime khác không tương thích.

Nếu có thể, tạo một C ABI ổn định ở ranh giới JNI/C++: nhận kiểu dữ liệu đơn giản, định nghĩa rõ ownership, mã lỗi và phiên bản API.

## 8. JNI metadata trong Spring AOT và Native Image

JNI library có thể gọi ngược vào Java thông qua JNI API, ví dụ tìm class, lấy method ID, truy cập field hoặc gọi Java method. Khi Native Image build, các kiểu/thành viên mà native code truy cập theo cách động cần metadata phù hợp.

Spring Framework cung cấp Runtime Hints API cho JNI. Ví dụ minh họa khi C code cần gọi method public của một callback Java:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(CallbackJniHints.class)
class NativeCallbackConfiguration {
}

class CallbackJniHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
                NativeCallback.class,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Có thể gắn registrar với configuration bằng `@ImportRuntimeHints` hoặc đăng ký theo cơ chế AOT phù hợp. Ví dụ này dành cho trường hợp native code dùng JNI để tìm/gọi method của `NativeCallback`. Không cần đăng ký mọi class của ứng dụng nếu C code chỉ thực hiện phép tính và không gọi ngược vào Java.

Phân biệt hai chiều:

- **Java gọi native method:** cần thư viện được nạp và native method được liên kết/đăng ký đúng.
- **Native code truy cập Java qua JNI:** cần các type/member mà C code truy cập được giữ với JNI metadata tương ứng.

Runtime Hints không thay thế file .so/.dll/.dylib và không sửa được lỗi ABI. Nếu loader không thể nạp shared library, bổ sung reflection/JNI hints sẽ không giải quyết nguyên nhân đó.

## 9. Đóng gói native executable cùng JNI libraries

Một layout triển khai rõ ràng:

~~~text
orders-native/
├── bin/
│   └── orders-service
└── lib/
    ├── libnativecalc.so
    └── libvendorcodec.so
~~~

Trên Windows/macOS, file và layout tương ứng sẽ dùng .dll/.dylib. Cần quyết định rõ:

- Binary nạp JNI library bằng tên hay đường dẫn tuyệt đối.
- Thư viện nằm ở vị trí nào trong image/package.
- Các dependency bắc cầu của thư viện nằm ở đâu.
- Loader path/RPATH/install name/PATH được cấu hình ra sao.
- User chạy ứng dụng có quyền đọc/thực thi phù hợp.
- Phiên bản thư viện có được khóa và phát hành cùng ứng dụng không.

Không nên để thư viện native trong thư mục tạm có thể bị process khác thay thế. Thư mục chứa mã native cần quyền ghi hạn chế, và artifact nên được xác minh checksum/signature theo quy trình phát hành.

## 10. Đóng gói container Linux

Native executable và JNI .so cần được build cho cùng target OS/architecture và runtime ABI. Ví dụ Dockerfile nhiều stage:

~~~dockerfile
# Builder phải khớp target Linux/CPU và GraalVM toolchain.
FROM ghcr.io/graalvm/native-image-community:21 AS builder
WORKDIR /workspace

COPY . .
RUN ./mvnw -Pnative -DskipTests package
RUN mkdir -p target/native-libs build/include build/classes && javac -h build/include -d build/classes src/main/java/com/example/nativebridge/NativeMath.java && cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o target/native-libs/libnativecalc.so src/main/c/nativecalc.c

# Runtime image phải có ABI/system libraries tương thích với builder output.
FROM debian:bookworm-slim
WORKDIR /app

COPY --from=builder /workspace/target/orders-service /app/orders-service
COPY --from=builder /workspace/target/native-libs/ /app/lib/

ENV APP_NATIVE_LIBRARY=/app/lib/libnativecalc.so
ENV LD_LIBRARY_PATH=/app/lib
EXPOSE 8080
ENTRYPOINT ["/app/orders-service"]
~~~

Dockerfile là minh họa; tên builder tag, đường dẫn native output và vị trí thư viện phải được thay theo dự án. Runtime image cần có các thư viện hệ thống mà executable/JNI library phụ thuộc. Không dùng `scratch` nếu binary hoặc JNI libraries cần dynamic loader, libc hay dependency chưa được đóng gói.

Thư mục `target/native-libs/` trong ví dụ phải được tạo bởi một Maven/Gradle task riêng biên dịch mã C ở bước trước; Spring Boot Maven/Gradle plugin không tự biên dịch mọi file C trong source tree. Builder cũng cần có C compiler và JNI headers tương ứng. Nếu thư viện có dependency bắc cầu nằm cùng thư mục `/app/lib`, `LD_LIBRARY_PATH` giúp Linux loader tìm các dependency đó; với nền tảng khác, dùng cơ chế loader tương ứng.

Trong ví dụ Java phía trên, ứng dụng đọc `APP_NATIVE_LIBRARY` bằng `System.getenv(...)` và gọi `System.load(...)`. Có thể chạy container như sau:

~~~bash
docker run --rm -p 8080:8080 -e APP_NATIVE_LIBRARY=/app/lib/libnativecalc.so orders-service:native
~~~

Nếu dùng `System.loadLibrary("nativecalc")`, cấu hình search path phù hợp trong image hoặc thiết kế RPATH/RUNPATH. Sau khi build image, chạy smoke test bên trong container và kiểm tra dependency bằng công cụ có sẵn hoặc một debug stage tương thích.

### 10.1. Multi-platform container build

Nếu phát hành cho cả AMD64 và ARM64, cần tạo native executable và JNI libraries riêng cho mỗi kiến trúc. Docker manifest list có thể trỏ tới nhiều image platform, nhưng manifest list không chuyển đổi binary bên trong image.

Ví dụ khái niệm:

~~~text
registry.example.com/orders-service:1.0
├── linux/amd64 -> executable AMD64 + JNI .so AMD64
└── linux/arm64 -> executable ARM64 + JNI .so ARM64
~~~

Không copy một file .so AMD64 vào image ARM64 chỉ vì tên và đường dẫn giống nhau. Hãy xác minh architecture của mọi shared library trong từng image.

## 11. Chẩn đoán lỗi nạp thư viện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `UnsatisfiedLinkError: no ... in java.library.path` | Không tìm thấy JNI library theo tên | Kiểm tra tên logic, filename, search path và quyền đọc |
| `UnsatisfiedLinkError: ... wrong ELF class` | Sai kiến trúc hoặc sai bitness | Dùng `file`/`readelf -h` kiểm tra executable và .so |
| `cannot open shared object file` | Thiếu file hoặc dependency bắc cầu, loader path sai | Dùng `ldd`/`readelf -d` và kiểm tra thư mục |
| `undefined symbol` | ABI/symbol version hoặc thư viện dependency không khớp | Kiểm tra exported/required symbols, version và thứ tự load |
| `GLIBC_x.y not found` | Build yêu cầu glibc mới hơn runtime | Chọn baseline tương thích hoặc rebuild |
| macOS báo image not found | install name/@rpath hoặc dylib dependency sai | Dùng `otool -L` và `otool -l` |
| Windows báo DLL load failed | Thiếu DLL phụ thuộc, runtime C++ hoặc kiến trúc sai | Dùng `dumpbin /DEPENDENTS` và kiểm tra PATH |
| Native executable chạy nhưng JNI call crash | Chữ ký JNI, ownership, memory hoặc thread handling sai | Kiểm tra header sinh từ javac, JNI signature và native debugger |

Quy trình điều tra:

~~~mermaid
flowchart TD
    A["Native app không load/call được thư viện"] --> B{"File thư viện có tồn tại?"}
    B -- "Không" --> C["Kiểm tra packaging, mount và path"]
    B -- "Có" --> D{"OS/CPU/binary format có khớp?"}
    D -- "Không" --> E["Build lại JNI library cho target đúng"]
    D -- "Có" --> F{"Dependency và ABI có tương thích?"}
    F -- "Không" --> G["Kiểm tra libc, symbol version, runtime và loader path"]
    F -- "Có" --> H{"JNI symbol/signature có khớp?"}
    H -- "Không" --> I["Sinh lại header, sửa signature/RegisterNatives"]
    H -- "Có" --> J["Kiểm tra JNI metadata, memory, thread và native crash"]
~~~

Luôn giữ log và output của đúng binary đang chạy. Kiểm tra file trên máy build không chứng minh file trong container production giống hệt hoặc có cùng dependency.

## 12. Các lệnh kiểm tra artifact theo nền tảng

| Mục tiêu | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Xem định dạng/kiến trúc | `file libnativecalc.so` | `file libnativecalc.dylib` | `dumpbin /HEADERS nativecalc.dll` |
| Xem dependency | `ldd libnativecalc.so` | `otool -L libnativecalc.dylib` | `dumpbin /DEPENDENTS nativecalc.dll` |
| Xem symbol | `nm -D libnativecalc.so` | `nm -gU libnativecalc.dylib` | `dumpbin /EXPORTS nativecalc.dll` |
| Xem dynamic section/path | `readelf -d libnativecalc.so` | `otool -l libnativecalc.dylib` | Công cụ PE/loader diagnostics |

Chạy kiểm tra trên cả executable và JNI library. Một .so có thể đúng kiến trúc nhưng lại phụ thuộc vào một .so khác sai kiến trúc hoặc không có trên runtime image.

## 13. Checklist phát hành đa nền tảng

- [ ] Xác định OS và CPU architecture của từng target.
- [ ] Native executable được build cho đúng target.
- [ ] JNI shared libraries được build cho cùng OS/architecture/ABI.
- [ ] JNI header và signature khớp với khai báo Java.
- [ ] Tên thư viện phù hợp quy tắc từng OS hoặc dùng absolute path được quản lý.
- [ ] Các dependency bắc cầu có mặt và loader path được cấu hình.
- [ ] Kiểm tra glibc/musl, symbol version và C/C++ runtime.
- [ ] JNI callbacks vào Java có metadata cần thiết nếu truy cập động.
- [ ] Container base image tương thích với executable và các shared libraries.
- [ ] User runtime có quyền đọc thư viện nhưng không thể tùy tiện thay thế file.
- [ ] Kiểm thử native call trên từng target thực tế, không chỉ trên máy build.
- [ ] Lưu checksum, version và kiến trúc của executable cùng từng JNI library.

### Câu hỏi tự đánh giá

1. Native executable và JNI shared library khác nhau như thế nào trong quá trình build và deploy?
2. Vì sao một file .so x86_64 không thể được nạp trong Linux ARM64?
3. `System.loadLibrary("nativecalc")` khác `System.load("/path/libnativecalc.so")` ở điểm nào?
4. Vì sao cùng Linux x86_64 nhưng glibc và musl vẫn có thể không tương thích?
5. Nếu JNI library tồn tại nhưng báo thiếu symbol, cần kiểm tra những dependency và ABI nào?
6. Khi C code gọi ngược Java qua JNI, Runtime Hints có vai trò gì?
7. Vì sao multi-platform Docker image cần executable và JNI libraries riêng cho từng architecture?
8. Tại sao không nên dùng `scratch` làm runtime image khi ứng dụng còn phụ thuộc dynamic libraries chưa được đóng gói?

## Tài liệu tham khảo

- [GraalVM Native Image — JNI](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): hỗ trợ JNI và metadata cho truy cập từ native code.
- [GraalVM Native Image — Build Configuration](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildConfiguration/): cấu hình native-image builder và toolchain.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints API, gồm các khả năng reflection/JNI/resource.
- [JNI Design Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): kiến trúc và quy tắc giao tiếp Java Native Interface.
- [Linux dynamic linker](https://man7.org/linux/man-pages/man8/ld.so.8.html): quy tắc tìm shared objects trên Linux.

**Kết quả cần đạt:** có thể chọn đúng thư viện .so/.dll/.dylib cho target, biên dịch và nạp JNI library, xác minh dependency/ABI và đóng gói cùng native executable. Khi triển khai đa nền tảng, mỗi artifact phải được build và kiểm thử trên tổ hợp OS, architecture và runtime tương thích; tên file giống nhau không bảo đảm binary có thể thay thế cho nhau.
