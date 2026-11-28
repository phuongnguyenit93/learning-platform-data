# Đóng gói native library đúng hệ điều hành, kiến trúc và cơ chế nạp

## 1. Vì sao native library cần gói riêng theo nền tảng?

Ứng dụng Java có thể gọi mã C, C++ hoặc mã máy thông qua Java Native Interface (JNI). JNI hữu ích khi cần dùng thư viện hệ thống, thiết bị, codec, thuật toán hoặc dependency native đã có. Tuy nhiên, file native không có tính di động như JAR: nó được biên dịch cho một hệ điều hành, kiến trúc CPU và ABI cụ thể.

Một file DLL build cho Windows x64 không thể nạp trực tiếp trên Linux x64. Tương tự, thư viện Linux dùng glibc có thể không chạy trên môi trường musl; thư viện macOS x86_64 không mặc nhiên chạy như binary arm64.

Khi tạo runtime/application image, cần kiểm tra bốn lớp:

1. **Hệ điều hành:** Windows, Linux hoặc macOS.
2. **Kiến trúc CPU và JVM:** x86_64/AMD64, AArch64/ARM64 hoặc kiến trúc khác được hỗ trợ.
3. **ABI và thư viện phụ thuộc:** Windows runtime, glibc/musl, macOS deployment target, C/C++ runtime và shared library khác.
4. **Cơ chế nạp:** tên thư viện, đường dẫn tìm kiếm, class loader, quyền native access và cấu hình launcher.

`jlink` tạo runtime Java từ các module; nó không biên dịch, chuyển đổi hoặc tự tìm đúng binary native của ứng dụng. `jpackage` có thể đưa native library vào application payload, nhưng ứng dụng vẫn phải nạp đúng file và hệ điều hành phải tìm được các dependency native của file đó.

## 2. Lập ma trận binary theo OS và kiến trúc

Không nên đặt một binary duy nhất vào mọi gói phát hành. Hãy build và lưu artifact riêng cho từng target được hỗ trợ:

| Target | Tên file thường gặp | Các điểm cần kiểm tra |
| --- | --- | --- |
| Windows x86_64 | `codec.dll` | PE architecture, MSVC runtime, DLL phụ thuộc |
| Windows ARM64 | `codec.dll` | Binary ARM64, runtime và dependency đúng kiến trúc |
| Linux x86_64 | `libcodec.so` | ELF x86-64, glibc/musl và SONAME dependency |
| Linux AArch64 | `libcodec.so` | ELF AArch64, ABI và native dependency |
| macOS x86_64 | `libcodec.dylib` | Mach-O x86_64, deployment target và install name |
| macOS Apple Silicon | `libcodec.dylib` | Mach-O arm64 hoặc universal binary, code signing |

Một cấu trúc thư mục có thể dùng trong repository hoặc artifact staging:

~~~text
native/
  windows-x86_64/
    codec.dll
  windows-aarch64/
    codec.dll
  linux-x86_64/
    libcodec.so
  linux-aarch64/
    libcodec.so
  macos-x86_64/
    libcodec.dylib
  macos-aarch64/
    libcodec.dylib
~~~

Chỉ giữ các target mà sản phẩm thực sự hỗ trợ. Tên kiến trúc do JVM trả về có thể là `amd64`, `x86_64`, `aarch64` hoặc `arm64`; chuẩn hóa các alias thành khóa artifact thống nhất trong build/release pipeline.

Có thể đọc thuộc tính runtime để chọn biến thể:

~~~java
String osName = System.getProperty("os.name")
        .toLowerCase(java.util.Locale.ROOT);
String archName = System.getProperty("os.arch")
        .toLowerCase(java.util.Locale.ROOT);

System.out.println("OS: " + osName);
System.out.println("JVM architecture: " + archName);
~~~

`os.arch` mô tả kiến trúc JVM đang chạy, không nhất thiết là kiến trúc phần cứng vật lý nếu JVM chạy qua lớp tương thích. Hãy phân phối binary khớp với JVM thực tế và không suy luận chỉ từ tên máy. Nếu target không nằm trong ma trận đã build và kiểm thử, dừng với thông báo rõ ràng thay vì chọn đại một thư viện.

## 3. Khác biệt ABI và dependency native theo hệ điều hành

### Windows

- DLL phải đúng kiến trúc với tiến trình JVM.
- Các DLL phụ thuộc, chẳng hạn Visual C++ runtime, phải có trên máy hoặc được phân phối theo chính sách của ứng dụng.
- Windows loader có quy tắc tìm DLL riêng; tìm thấy DLL chính chưa đảm bảo tìm thấy các DLL mà nó phụ thuộc.
- Không đặt thư viện không tin cậy vào thư mục tìm kiếm có thể bị ứng dụng khác ghi nội dung.

### Linux

- Kiểm tra định dạng ELF, kiến trúc, SONAME và các shared library mà binary cần.
- Xác định binary được build cho glibc hay musl. Không giả định một binary glibc có thể chạy trên Alpine/musl.
- Chọn baseline glibc tương thích với các bản phân phối Linux được hỗ trợ.
- RPATH/RUNPATH, `$ORIGIN`, cache của dynamic linker và `LD_LIBRARY_PATH` ảnh hưởng việc tìm dependency.

### macOS

- Kiểm tra Mach-O architecture, minimum deployment target và install name của dylib.
- Apple Silicon và Intel cần binary tương ứng; universal binary có thể chứa nhiều slice nhưng vẫn phải kiểm tra bằng công cụ của macOS.
- Native library nằm trong app bundle cần tuân thủ quy trình code signing, hardened runtime và notarization phù hợp với cách phân phối.
- `DYLD_LIBRARY_PATH` có thể chịu giới hạn bởi cơ chế bảo vệ của macOS; không dựa vào biến này như giải pháp đóng gói phổ quát.

ABI là một phần của hợp đồng triển khai. Build thành công trên máy phát triển không chứng minh binary chạy được trên mọi máy có cùng hệ điều hành và kiến trúc.

## 4. Khai báo native method và nạp thư viện bằng JNI

Ví dụ lớp Java gọi một hàm native:

~~~java
package com.example.nativecodec;

public final class NativeCodec {
    static {
        System.loadLibrary("codec");
    }

    private NativeCodec() {
    }

    public static native int version();
}
~~~

`System.loadLibrary("codec")` nhận **tên logic** của thư viện. Không truyền prefix, extension hoặc đường dẫn nền tảng. JVM ánh xạ tên này theo hệ điều hành, ví dụ:

| Nền tảng | Tên được ánh xạ thường gặp |
| --- | --- |
| Windows | `codec.dll` |
| Linux | `libcodec.so` |
| macOS | `libcodec.dylib` |

Có thể xem tên ánh xạ bằng:

~~~java
System.out.println(System.mapLibraryName("codec"));
~~~

`System.loadLibrary` tìm thư viện theo cơ chế native library search path của JVM/class loader. Trong khi đó, `System.load` nhận đường dẫn tuyệt đối tới file native:

~~~java
System.load("C:\\Program Files\\NativeApp\\native\\codec.dll");
~~~

Đường dẫn trên chỉ minh họa cho Windows. Khi dùng `System.load`, phải tạo đường dẫn đúng nền tảng và truyền đường dẫn tuyệt đối; không truyền tên file tương đối.

## 5. Tạo JNI header và build native binary

JDK hiện đại dùng tùy chọn `javac -h` để sinh header JNI từ khai báo `native`. Không dùng công cụ `javah` cũ đã bị loại khỏi JDK.

Biên dịch lớp Java và sinh header:

~~~powershell
javac -h build\include -d build\classes src\com\example\nativecodec\NativeCodec.java
~~~

Header sinh ra mô tả chữ ký hàm native. Với phương thức `public static native int version()`, phần khai báo C tương ứng có dạng:

~~~c
#include <jni.h>
#include "com_example_nativecodec_NativeCodec.h"

JNIEXPORT jint JNICALL
Java_com_example_nativecodec_NativeCodec_version(JNIEnv *env, jclass type) {
    return 1;
}
~~~

Tên symbol cụ thể nên lấy từ header do `javac -h` sinh ra, nhất là khi tên package, overload hoặc chữ ký phương thức thay đổi.

Biên dịch C/C++ thành shared library bằng toolchain native cho từng target. Ví dụ trên Linux:

~~~bash
cc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  src/nativecodec.c \
  -o build/native/linux-x86_64/libcodec.so
~~~

Đường dẫn include và compiler flags khác nhau theo JDK, OS và toolchain. Windows dùng header trong `include/win32` cùng compiler phù hợp; macOS dùng header trong `include/darwin`. Build riêng cho từng target hoặc dùng cross-compiler được cấu hình và kiểm thử rõ ràng.

Không dùng binary native của máy build để phát hành cho kiến trúc khác. Trong CI, tạo artifact theo ma trận OS/CPU và gắn metadata build để biết compiler, ABI, dependency và target của từng file.

## 6. Đưa native library vào application image bằng jpackage

Native library của ứng dụng phải nằm trong application payload hoặc được cài theo cơ chế riêng. Với ứng dụng classpath, thư mục `--input` có thể chứa JAR và thư mục native:

~~~text
input/
  app.jar
  native/
    windows-x86_64/
      codec.dll
~~~

Đóng gói trên Windows x64:

~~~powershell
jpackage --type app-image --name NativeApp --input input --main-jar app.jar --main-class com.example.app.Main --java-options '--java.library.path=$APPDIR/native/windows-x86_64' --dest dist
~~~

`jpackage` đưa các file trong input directory vào application image. `$APPDIR` là token được launcher của `jpackage` mở rộng tại runtime thành thư mục chứa application payload. Ví dụ chỉ đóng gói biến thể Windows x64; pipeline Linux/macOS phải chọn đúng thư mục native tương ứng.

Với ứng dụng modular, có thể đưa thư mục native vào application payload bằng `--app-content`:

~~~powershell
jpackage --type app-image --name NativeApp --module-path mods --module com.example.app/com.example.app.Main --app-content native --java-options '--java.library.path=$APPDIR/native/windows-x86_64' --dest dist
~~~

Đảm bảo thư mục `native` được bố trí đúng vị trí mà launcher option tham chiếu. Kiểm tra application image sau khi đóng gói thay vì giả định đường dẫn staging và đường dẫn cài đặt luôn giống nhau.

Khi build app bundle trên macOS, kiểm tra yêu cầu cấu trúc của `--app-content`: nội dung bổ sung phải nằm trong thư mục Resources hoặc một vị trí hợp lệ bên trong Contents để bundle có thể được ký và notarize đúng cách.

`jlink` chỉ tạo Java runtime. Không đặt native library của ứng dụng vào `jmods` hoặc coi `--add-modules` là cách đóng gói DLL/SO/DYLIB. `jpackage --input` và `--app-content` là các cơ chế đưa file ứng dụng vào payload.

## 7. Nạp native library từ thư mục application image

Khi dùng `System.loadLibrary`, có thể cấu hình thư mục native thông qua `java.library.path` lúc JVM khởi chạy. Với launcher do `jpackage` tạo, `$APPDIR` giúp tham chiếu vị trí payload mà không hard-code thư mục cài đặt:

~~~powershell
jpackage --type app-image --name NativeApp --input input --main-jar app.jar --java-options '--java.library.path=$APPDIR/native/windows-x86_64' --dest dist
~~~

Sau đó mã Java có thể dùng:

~~~java
static {
    System.loadLibrary("codec");
}
~~~

Đặt `java.library.path` lúc JVM khởi chạy. Không dựa vào việc thay đổi `System.setProperty("java.library.path", ...)` sau khi JVM đã khởi tạo để cấu hình lại native library search path.

Nếu cần chọn file cụ thể theo cấu hình ứng dụng, có thể dùng `System.load` với đường dẫn tuyệt đối tới binary đã xác định:

~~~java
Path nativeFile = appNativeDirectory.resolve(
        System.mapLibraryName("codec"));
System.load(nativeFile.toAbsolutePath().toString());
~~~

`appNativeDirectory` cần được xác định từ thư mục cài đặt/payload của ứng dụng theo cách phù hợp với launcher và OS. Không nhận đường dẫn thư viện tùy ý từ input không tin cậy.

## 8. Khi native library được đóng gói bên trong JAR

JVM không nạp trực tiếp DLL/SO/DYLIB từ resource stream bên trong JAR. Nếu muốn lưu binary trong JAR theo từng target, cần:

1. Chọn resource path theo OS và kiến trúc JVM.
2. Đọc resource bằng `getResourceAsStream`.
3. Ghi file ra thư mục tạm riêng có quyền truy cập phù hợp.
4. Gọi `System.load` với đường dẫn tuyệt đối của file vừa ghi.
5. Bảo đảm các native dependency của file chính cũng được hệ điều hành tìm thấy.

Ví dụ phần trích xuất:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class NativeResourceLoader {
    private NativeResourceLoader() {
    }

    public static void load(String resourcePath, String libraryName)
            throws Exception {
        String mappedName = System.mapLibraryName(libraryName);
        Path directory = Files.createTempDirectory("native-app-");
        Path library = directory.resolve(mappedName);

        try (InputStream input =
                     NativeResourceLoader.class.getResourceAsStream(resourcePath)) {
            if (input == null) {
                throw new IllegalStateException(
                        "Native resource not found: " + resourcePath);
            }
            Files.copy(input, library, StandardCopyOption.REPLACE_EXISTING);
        }

        System.load(library.toAbsolutePath().toString());
    }
}
~~~

Ví dụ gọi loader với resource path đã được chọn từ danh sách target được hỗ trợ:

~~~java
NativeResourceLoader.load(
        "/native/windows-x86_64/codec.dll",
        "codec");
~~~

Đây là ví dụ Windows x64. Mỗi target phải có resource đúng tên file và đúng định dạng. Thư mục tạm cần được bảo vệ để người dùng khác không thể thay binary trước khi nạp. Với thư viện có dependency native đi kèm, cần cấu hình thêm đường dẫn tìm dependency theo quy tắc của OS; chỉ trích xuất file chính có thể chưa đủ.

## 9. Phân biệt Java library path và đường dẫn dependency của OS

`java.library.path` giúp JVM tìm **thư viện chính** khi gọi `System.loadLibrary`. Sau khi thư viện chính được tìm thấy, dynamic loader của hệ điều hành tiếp tục tìm các thư viện mà nó phụ thuộc.

| Nền tảng | Cơ chế thường liên quan tới dependency native |
| --- | --- |
| Windows | Quy tắc DLL search của Windows, thư mục ứng dụng, system directories và cơ chế thêm thư mục DLL an toàn |
| Linux | ELF RPATH/RUNPATH, SONAME, loader cache và `LD_LIBRARY_PATH` |
| macOS | `install_name`, `@rpath`, `@loader_path`, `@executable_path` và cơ chế bảo vệ của hệ điều hành |

Vì vậy, thêm thư mục vào `java.library.path` không tự giải quyết lỗi thiếu dependency bậc hai. Hãy thiết kế native binary với dependency path phù hợp khi build và kiểm tra trên máy đích.

Không khuyến nghị thêm thư mục ghi được bởi người dùng không tin cậy vào native search path. Nạp native code đồng nghĩa thực thi mã máy với quyền của tiến trình Java.

## 10. Native access restrictions trên JDK hiện đại

Từ JDK 24, các thao tác JNI có native access restrictions. Các trường hợp bị ảnh hưởng gồm:

- Gọi `System.loadLibrary`, `System.load`, `Runtime.loadLibrary` hoặc `Runtime.load`.
- Khai báo phương thức `native`.

Nếu module thực hiện các thao tác này chưa được cấp native access, JDK hiện đại phát cảnh báo theo mặc định. Ứng dụng cần khai báo rõ module được phép truy cập native bằng tùy chọn launcher `--enable-native-access`.

Với ứng dụng modular:

~~~powershell
jpackage --type app-image --name NativeApp --module-path mods --module com.example.app/com.example.app.Main --app-content native --java-options '--enable-native-access=com.example.app' --dest dist
~~~

Nếu module riêng `com.example.nativecodec` chứa lệnh nạp thư viện hoặc khai báo native method, cấp quyền cho module đó thay vì chỉ cấp cho module main:

~~~text
--enable-native-access=com.example.app,com.example.nativecodec
~~~

Với ứng dụng classpath, dùng `ALL-UNNAMED`:

~~~powershell
jpackage --type app-image --name NativeApp --input input --main-jar app.jar --java-options '--enable-native-access=ALL-UNNAMED' --dest dist
~~~

Chỉ cấp quyền cho module thực sự cần JNI. Không bật `ALL-UNNAMED` cho ứng dụng modular nếu có thể cấp quyền chính xác theo tên module. Native access không kiểm tra binary có đúng ABI hoặc an toàn hay không; nó chỉ xác nhận ứng dụng được phép thực hiện các thao tác native bị hạn chế.

JDK 16 chưa có cơ chế native access restrictions như JDK 24+. Nếu ứng dụng được phát triển từ Java 16 nhưng chạy trên JDK mới, hãy kiểm tra và cấu hình quyền native access cho runtime đích.

## 11. Quét và xác minh native dependency

JDK hiện đại cung cấp `jnativescan` để quét JAR/module path và phát hiện việc sử dụng native functionality, gồm lời gọi restricted methods và khai báo `native` methods.

Ví dụ quét ứng dụng classpath:

~~~powershell
jnativescan --class-path "input\app.jar;input\lib\*"
~~~

Với ứng dụng modular:

~~~powershell
jnativescan --module-path "mods;lib-modules" --add-modules com.example.app
~~~

Để lấy danh sách module cần native access:

~~~powershell
jnativescan --module-path "mods;lib-modules" --add-modules com.example.app --print-native-access
~~~

`jnativescan` phân tích bytecode; nó không xác minh binary native thực sự có đúng OS/CPU, ABI hoặc dependency. Hãy kết hợp quét tĩnh với kiểm tra file native và test tích hợp.

Các công cụ kiểm tra binary phổ biến:

| Nền tảng | Lệnh kiểm tra | Mục tiêu |
| --- | --- | --- |
| Windows | `dumpbin /headers codec.dll` | Kiểm tra PE machine/architecture |
| Windows | `dumpbin /dependents codec.dll` | Xem DLL dependency |
| Linux | `file libcodec.so` | Nhận diện định dạng và kiến trúc |
| Linux | `readelf -h libcodec.so` | Kiểm tra ELF class và machine |
| Linux | `readelf -d libcodec.so` | Kiểm tra NEEDED, RPATH và RUNPATH |
| macOS | `file libcodec.dylib` | Kiểm tra Mach-O architecture |
| macOS | `otool -L libcodec.dylib` | Xem install name và dependency |
| macOS | `lipo -info libcodec.dylib` | Kiểm tra các slice của universal binary |

Chỉ dùng công cụ phân tích trên binary đáng tin cậy. Khi kiểm tra dependency trên Linux, ưu tiên `readelf` để đọc metadata; không chạy thư viện không rõ nguồn gốc chỉ để xem nó có nạp được hay không.

## 12. Class loader và vòng đời native library

JVM quản lý native library theo class loader. Một native library JNI không thể được nạp đồng thời vào nhiều class loader khác nhau; nếu cùng file được nạp ở class loader khác, JVM có thể ném `UnsatisfiedLinkError`.

Điều này thường xuất hiện trong ứng dụng plugin, application server hoặc môi trường có nhiều class loader:

- Đặt việc nạp thư viện ở một class loader dùng chung nếu nhiều module/class cần cùng native code.
- Tránh mỗi plugin tự nạp lại cùng một native library.
- Kiểm soát phiên bản native library và tên file để tránh xung đột.
- Không giả định unload native library diễn ra ngay khi bỏ tham chiếu tới class loader.

Native code cũng có thể giữ global reference, thread hoặc tài nguyên ngoài heap. Thiết kế lifecycle rõ ràng và cung cấp hàm đóng tài nguyên nếu thư viện yêu cầu.

## 13. Chẩn đoán lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `UnsatisfiedLinkError: no ... in java.library.path` | JVM không tìm thấy thư viện chính | Kiểm tra tên `loadLibrary`, `java.library.path` và launcher |
| `Can't load ... wrong ELF class` hoặc bad image | Sai kiến trúc/bitness hoặc file không đúng định dạng | Kiểm tra `file`, `readelf`, `dumpbin` hoặc `lipo` |
| `UnsatisfiedLinkError: ... symbol not found` | Thiếu JNI symbol hoặc sai tên/chữ ký native method | So sánh header từ `javac -h` với symbol được export |
| DLL/SO/DYLIB chính có mặt nhưng vẫn không nạp | Thiếu dependency native bậc hai hoặc ABI không tương thích | Kiểm tra `dumpbin /dependents`, `readelf -d`, `otool -L` |
| Cảnh báo native access trên JDK mới | Module chưa được cấp native access | Thêm `--enable-native-access` cho module gọi restricted operation |
| `IllegalCallerException` khi nạp native | Native access không được bật theo chính sách runtime | Kiểm tra module gọi `System.load*` và launcher options |
| `Native Library ... already loaded in another classloader` | Cùng JNI library được nạp bởi nhiều class loader | Chuyển việc nạp sang class loader dùng chung |
| Chạy được trên máy build nhưng lỗi trên máy khách | Máy build có dependency native hoặc runtime khác | Test trên máy sạch/container đúng target |

Không xử lý lỗi ABI bằng cách đổi tên file hoặc thêm mọi thư mục vào search path. Xác định chính xác binary, dependency, class loader và launcher option gây lỗi.

## 14. Quy trình đóng gói native library

1. Xác định OS, kiến trúc JVM và ABI của từng target được hỗ trợ.
2. Build native binary riêng bằng toolchain phù hợp; ghi nhận compiler, runtime dependency và phiên bản.
3. Dùng `javac -h` sinh JNI header, build library và xác nhận symbol.
4. Đặt binary vào thư mục theo OS/architecture hoặc đóng gói như resource có kiểm soát.
5. Dùng `jpackage --input` hoặc `--app-content` để đưa native files vào application payload.
6. Cấu hình `java.library.path` bằng launcher token như `$APPDIR`, hoặc dùng `System.load` với đường dẫn tuyệt đối.
7. Trên JDK 24+, cấp `--enable-native-access` cho đúng module hoặc `ALL-UNNAMED` nếu ứng dụng chạy trên classpath.
8. Quét bytecode bằng `jnativescan` và kiểm tra binary bằng công cụ của OS.
9. Test nạp thư viện và chức năng native trên máy sạch cho từng OS/CPU target.
10. Với macOS, hoàn tất code signing/notarization; với Windows/Linux, kiểm tra native runtime dependency và chính sách cài đặt tương ứng.

**Ghi nhớ:** Native library là artifact riêng theo OS, kiến trúc và ABI. `jlink` không đóng gói hoặc chuyển đổi native library của ứng dụng; `jpackage` chỉ đưa file vào application payload. Dùng `System.loadLibrary` với tên logic hoặc `System.load` với đường dẫn tuyệt đối, cấu hình dependency loader của hệ điều hành, và cấp native access trên JDK 24 trở lên. Chỉ phát hành sau khi test trên đúng runtime image và từng nền tảng mục tiêu.

## 15. Khi nào nên cân nhắc Foreign Function and Memory API?

JNI vẫn là cơ chế ổn định và được hỗ trợ rộng rãi, đặc biệt khi thư viện đã có JNI binding hoặc cần tương tác với code native hiện hữu. Với dự án mới, có thể cân nhắc Foreign Function and Memory (FFM) API trong package `java.lang.foreign`.

FFM API được hoàn thiện thành API chính thức từ JDK 22. API này cho phép Java tìm symbol trong native library, mô tả chữ ký hàm bằng `FunctionDescriptor`, gọi hàm qua `Linker` và quản lý vùng nhớ native bằng `MemorySegment` cùng `Arena`. Cách này tránh phải viết lớp JNI trung gian và khai báo native method cho nhiều trường hợp gọi C function.

Ví dụ khung gọi một hàm C không tham số trả về int:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class FfmNativeExample {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                    Path.of("native", "libcodec.so"), arena);

            MemorySegment address =
                    library.find("codec_version").orElseThrow();

            MethodHandle version = linker.downcallHandle(
                    address,
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));

            int nativeVersion = (int) version.invokeExact();
            System.out.println(nativeVersion);
        }
    }
}
~~~

Đường dẫn `libcodec.so` chỉ minh họa cho Linux; Windows và macOS phải chọn đúng tên file và binary của target. Khi dùng FFM, thư viện vẫn phải được phân phối cùng ứng dụng hoặc có mặt ở đường dẫn đã cấu hình. FFM không chuyển đổi binary giữa OS/CPU và cũng không giải quyết dependency ABI của hệ điều hành.

FFM có native access restrictions. Trên JDK hiện đại, module gọi các restricted FFM methods vẫn cần được cấp quyền bằng `--enable-native-access`. Hãy chọn FFM khi thiết kế mới cần gọi foreign function hoặc quản lý native memory trực tiếp; tiếp tục dùng JNI khi tương thích với thư viện/binding hiện có là yêu cầu chính.

## Nguồn tham khảo chính thức

- [Java Native Interface Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/index.html)
- [System API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html)
- [Runtime API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html)
- [JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
- [JEP 454: Foreign Function and Memory API](https://openjdk.org/jeps/454)
- [Foreign Function and Memory API — JDK 26](https://docs.oracle.com/en/java/javase/26/core/foreign-function-and-memory-api.html)
- [The jnativescan Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jnativescan.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
