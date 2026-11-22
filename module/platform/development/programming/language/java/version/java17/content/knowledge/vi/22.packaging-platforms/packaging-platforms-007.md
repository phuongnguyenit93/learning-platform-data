# JDK macOS/AArch64 và thư viện native cùng kiến trúc

Mac dùng Apple Silicon có CPU ARM 64-bit. Java 17 có các bản JDK dành cho macOS/AArch64 để chạy JVM trực tiếp trên kiến trúc này. Khi ứng dụng Java cần gọi thư viện native qua JNI, JNA hoặc một lớp tích hợp native khác, kiến trúc của thư viện phải tương thích với **kiến trúc của tiến trình JVM đang chạy**.

Đây là nguyên tắc cốt lõi khi đóng gói ứng dụng cho macOS:

- JDK chạy native trên Apple Silicon là tiến trình ARM64.
- JDK Intel chạy qua Rosetta 2 là tiến trình x86_64, dù máy vật lý là Apple Silicon.
- Một tiến trình JVM chỉ nạp được mã native có slice phù hợp với kiến trúc tiến trình đó.
- Mọi thư viện native phụ thuộc gián tiếp cũng phải có kiến trúc tương thích.
- Universal binary có thể chứa cả ARM64 và x86_64; macOS chọn slice phù hợp khi nạp.

Một JAR Java thuần thường không phụ thuộc CPU architecture. Tuy nhiên, ứng dụng đóng gói JAR cùng file .dylib, framework hoặc thư viện native đi kèm phải chọn đúng bộ native artifact cho tiến trình JVM. Chỉ đổi JDK sang ARM64 mà vẫn giữ native library x86_64 sẽ dẫn tới lỗi nạp thư viện.

## 1. Apple Silicon, AArch64 và x86_64

Apple Silicon là dòng SoC của Apple dùng kiến trúc ARM 64-bit. Trong tài liệu và công cụ, cùng một kiến trúc có thể được gọi là ARM64 hoặc AArch64. Trên macOS, tên kiến trúc thường thấy trong công cụ native là `arm64`; trong một số giá trị Java hoặc metadata có thể là `aarch64`.

Mac Intel dùng kiến trúc x86-64, thường được ghi là `x86_64`. Apple Silicon có thể chạy ứng dụng Intel thông qua Rosetta 2. Vì thế, một máy Apple Silicon có thể đồng thời chạy:

- JVM ARM64 native.
- JVM x86_64 được dịch bởi Rosetta 2.

Hai JVM đó là hai tiến trình có kiến trúc khác nhau. Chúng không thể nạp lẫn các native library chỉ được build cho kiến trúc còn lại.

### Ma trận tương thích

| Phần cứng | JVM process | Native library cần có |
| --- | --- | --- |
| Apple Silicon | ARM64 native | ARM64 hoặc universal có slice ARM64 |
| Apple Silicon | x86_64 qua Rosetta 2 | x86_64 hoặc universal có slice x86_64 |
| Mac Intel | x86_64 native | x86_64 hoặc universal có slice x86_64 |
| Mac Intel | Không chạy JVM ARM64 | Không thể nạp native ARM64 vào tiến trình Intel |

Vì vậy, câu hỏi cần trả lời khi chọn thư viện là: **JVM hiện tại đang chạy dưới kiến trúc nào?** Chỉ biết máy là Apple Silicon chưa đủ, vì JVM có thể đang chạy dưới Rosetta.

## 2. JDK macOS/AArch64 là gì?

JDK dành cho macOS/AArch64 là bộ JDK có các binary native được build cho macOS trên kiến trúc ARM64. JVM trong JDK đó chạy trực tiếp trên Apple Silicon, không cần Rosetta để dịch tiến trình JVM.

JDK thường được cài dưới dạng bundle có cấu trúc tương tự:

~~~text
/Library/Java/JavaVirtualMachines/
  <jdk-name>.jdk/
    Contents/
      Home/
        bin/
        lib/
        include/
~~~

Tên thư mục và cách đóng gói có thể khác giữa các nhà cung cấp, nhưng Java launcher và thư viện JVM nằm bên trong JDK home.

### Liệt kê JDK đã cài

macOS cung cấp công cụ `java_home`:

~~~bash
/usr/libexec/java_home -V
~~~

Lệnh liệt kê các JDK mà hệ thống nhận diện, cùng thông tin phiên bản và vị trí. Có thể yêu cầu JDK 17 dành cho ARM64:

~~~bash
/usr/libexec/java_home -v 17 -a arm64
~~~

Nếu có nhiều JDK 17 hoặc cài đặt tùy chỉnh không được hệ thống đăng ký, hãy kiểm tra lại đường dẫn JDK cụ thể thay vì giả định PATH luôn chọn đúng bản.

Đặt JAVA_HOME và PATH cho shell hiện tại:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17 -a arm64)
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Tùy chọn kiến trúc trong java_home giúp chọn bản JDK phù hợp nếu có nhiều kiến trúc được cài. Nếu hệ thống không tìm thấy JDK tương ứng, kiểm tra lại bản JDK đã cài và đường dẫn vendor cung cấp.

## 3. Xác định kiến trúc của JVM thực sự đang chạy

Không nên suy luận kiến trúc JVM từ tên máy hoặc chỉ từ model Mac. Hãy kiểm tra chính tiến trình Java.

### Xem system property os.arch

Chạy:

~~~bash
java -XshowSettings:properties -version 2>&1 | grep -E 'os.arch|os.name|java.home'
~~~

Trên một JDK ARM64 native, `os.arch` thường thể hiện `aarch64` hoặc tên ARM64 tương ứng với bản phân phối. Với JVM Intel chạy qua Rosetta, giá trị thường là `x86_64`.

Có thể kiểm tra từ code:

~~~java
public class RuntimeArchitecture {
    public static void main(String[] args) {
        System.out.println("os.name = "
                + System.getProperty("os.name"));
        System.out.println("os.arch = "
                + System.getProperty("os.arch"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
        System.out.println("java.version = "
                + System.getProperty("java.version"));
    }
}
~~~

`os.arch` mô tả kiến trúc mà JVM hiện tại đang chạy, không phải phép dò trực tiếp CPU vật lý. Đây là thông tin phù hợp để chọn native library cần nạp vào chính tiến trình đó. Khi so sánh giá trị, nên chuẩn hóa alias như `arm64` và `aarch64` về cùng một nhãn nội bộ.

### Kiểm tra process có đang chạy dưới Rosetta

Có thể kiểm tra kiến trúc process shell hiện tại:

~~~bash
arch
~~~

Trên macOS, `sysctl.proc_translated` có thể cho biết process hiện tại có đang được dịch bởi Rosetta hay không:

~~~bash
sysctl -in sysctl.proc_translated
~~~

Giá trị `1` cho biết process đang chạy qua Rosetta. Trên môi trường native, key có thể không được cung cấp; không nên xem lỗi không tìm thấy key là bằng chứng duy nhất về kiến trúc. Đối với ứng dụng Java, `System.getProperty("os.arch")` của JVM là kiểm tra trực tiếp và hữu ích nhất khi chọn thư viện.

### Kiểm tra binary của JDK

Sau khi chọn JAVA_HOME, có thể kiểm tra launcher và JVM shared library:

~~~bash
file -L "$JAVA_HOME/bin/java"
file -L "$JAVA_HOME/lib/server/libjvm.dylib"
lipo -archs "$JAVA_HOME/lib/server/libjvm.dylib"
~~~

Đường dẫn libjvm có thể khác ở một số cách đóng gói JDK; nếu không tìm thấy, hãy tìm file libjvm.dylib trong JDK home. Lệnh `file` hiển thị loại binary và architecture; `lipo -archs` liệt kê các slice có trong Mach-O binary.

Không phải mọi JDK đều là universal binary. Nhiều nhà cung cấp phát hành JDK riêng cho ARM64 và x86_64. Chọn đúng gói JDK ngay từ đầu sẽ dễ quản lý hơn việc giả định một gói có thể chạy mọi kiến trúc.

## 4. Vì sao native library phải cùng kiến trúc với JVM?

Java bytecode được thiết kế để JVM thực thi trên nhiều kiến trúc. Native library là mã máy dành cho một hoặc nhiều kiến trúc cụ thể.

Khi Java gọi:

~~~java
System.loadLibrary("native_math");
~~~

JVM yêu cầu macOS dynamic loader nạp một thư viện native vào không gian địa chỉ của tiến trình. Dynamic loader phải tìm được một Mach-O image có slice tương thích với tiến trình hiện tại.

Ví dụ:

- JVM ARM64 không thể nạp một dylib chỉ có slice x86_64.
- JVM x86_64 qua Rosetta không thể nạp một dylib chỉ có slice ARM64.
- Cả hai có thể nạp một universal dylib chứa cả ARM64 và x86_64.

Không có bước tự động chuyển mã của một dylib Intel thành ARM64 khi gọi JNI. Rosetta dịch tiến trình Intel; nó không cho phép trộn tùy ý module ARM64 vào tiến trình x86_64.

### Ví dụ lỗi architecture mismatch

Một lỗi thường thấy trong stack trace:

~~~text
java.lang.UnsatisfiedLinkError:
  dlopen(...): tried: ... (mach-o file, but is an incompatible architecture
  (have 'x86_64', need 'arm64'))
~~~

Thông báo cho biết JVM cần ARM64 nhưng file tìm được chỉ có x86_64. Cách xử lý là cài hoặc đóng gói bản native library có slice ARM64, hoặc chạy JVM x86_64 cùng bộ thư viện x86_64 nếu đó là lựa chọn triển khai có chủ đích.

### Không chỉ file JNI trực tiếp cần đúng kiến trúc

Một JNI library có thể phụ thuộc vào các dylib khác. Ví dụ:

~~~text
Java application
    |
    v
libnative_math.dylib
    |
    +---- libimagecodec.dylib
    |
    +---- libcrypto_adapter.dylib
              |
              +---- libvendor_runtime.dylib
~~~

Ngay cả khi `libnative_math.dylib` có slice ARM64, việc nạp vẫn thất bại nếu `libimagecodec.dylib` hoặc một dependency sâu hơn chỉ có x86_64. Toàn bộ chuỗi thư viện native phải có kiến trúc tương thích với JVM process.

## 5. Các định dạng native thường gặp trên macOS

macOS dùng định dạng Mach-O cho executable và thư viện native. Một số loại file thường gặp:

| File/định dạng | Vai trò |
| --- | --- |
| `.dylib` | Dynamic library trên macOS |
| `.framework` | Bundle framework; binary nằm bên trong bundle |
| `.bundle` | Bundle/plugin native trên macOS |
| Mach-O executable | Chương trình hoặc helper executable |
| `.jar` | Java archive; thường chứa bytecode, resource và có thể đóng gói native payload |
| `.so` | Thường dùng cho shared library trên Linux; không phải phần mở rộng native library chuẩn của macOS |

JNI library trên macOS thường được đóng gói dưới dạng `.dylib`. Không lấy phần mở rộng của Linux hoặc Windows rồi giả định macOS có thể nạp cùng file. Một JAR có thể chứa nhiều bản native binary theo hệ điều hành/kiến trúc, nhưng file được giải nén và nạp phải đúng với JVM đang chạy.

### Universal binary

Universal binary là một Mach-O binary chứa nhiều architecture slice trong cùng một file. Ví dụ một dylib có cả ARM64 và x86_64:

~~~bash
lipo -archs libnative_math.dylib
~~~

Kết quả có thể là:

~~~text
arm64 x86_64
~~~

Khi JVM ARM64 nạp file, dynamic loader dùng slice ARM64. Khi JVM x86_64 nạp cùng file, loader dùng slice x86_64.

Universal binary giúp phân phối một file native cho hai kiến trúc, nhưng không làm cho dependency đơn kiến trúc tự động trở thành universal. Mọi dependency được liên kết vẫn phải có slice phù hợp cho từng kiến trúc được hỗ trợ.

## 6. Kiểm tra kiến trúc của native library

Trước khi đưa một dylib vào gói ứng dụng, kiểm tra binary thực tế.

### Dùng file

~~~bash
file libnative_math.dylib
~~~

Output có thể cho biết đây là Mach-O 64-bit dynamically linked shared library và architecture của nó.

### Dùng lipo

~~~bash
lipo -info libnative_math.dylib
lipo -archs libnative_math.dylib
~~~

`lipo -archs` đặc biệt hữu ích với universal binary vì cho biết chính xác các slice hiện có. Không chỉ nhìn tên file như `libnative_math-arm64.dylib`; tên có thể sai hoặc artifact bị đóng gói nhầm.

### Kiểm tra dependency bằng otool

~~~bash
otool -L libnative_math.dylib
~~~

Lệnh hiển thị các dynamic library mà binary tham chiếu. Kiểm tra tiếp architecture của từng dependency có thể được tìm thấy trong bundle hoặc các thư mục cài đặt.

Ví dụ:

~~~bash
file /path/to/native/libnative_math.dylib
lipo -archs /path/to/native/libnative_math.dylib
otool -L /path/to/native/libnative_math.dylib

file /path/to/native/libimagecodec.dylib
lipo -archs /path/to/native/libimagecodec.dylib
~~~

Thực hiện kiểm tra đệ quy đối với dependency do ứng dụng đóng gói. `otool -L` chỉ liệt kê dependency trực tiếp; cần tiếp tục kiểm tra từng thư viện được tham chiếu để phát hiện dependency sâu hơn.

### Kiểm tra framework

Framework là bundle nên binary thường nằm trong thư mục `Versions/Current` hoặc đường dẫn được framework chỉ định. Có thể tìm binary rồi chạy:

~~~bash
find SomeFramework.framework -type f -maxdepth 5
file SomeFramework.framework/Versions/Current/SomeFramework
lipo -archs SomeFramework.framework/Versions/Current/SomeFramework
~~~

Đường dẫn thực tế phụ thuộc cấu trúc framework. Không kiểm tra riêng thư mục bundle rồi kết luận architecture; phải kiểm tra Mach-O executable bên trong.

## 7. Chọn JDK và native library theo cùng kiến trúc

Một ứng dụng macOS có thể hỗ trợ nhiều cấu hình. Điều quan trọng là chọn trọn bộ artifact nhất quán.

| Cấu hình phát hành | JDK | Native payload |
| --- | --- | --- |
| Apple Silicon native | macOS/AArch64 JDK 17 | ARM64 dylib/framework và dependency ARM64 |
| Mac Intel | macOS/x86_64 JDK 17 | x86_64 dylib/framework và dependency x86_64 |
| Một gói cho cả hai | JDK riêng theo kiến trúc hoặc cơ chế chọn runtime rõ ràng | Universal native libraries hoặc payload chọn theo process architecture |

Không nên đặt một JDK ARM64 cùng một thư viện JNI x86_64 vào cùng gói rồi kỳ vọng macOS tự dịch thư viện. Nếu hỗ trợ cả Intel và Apple Silicon, có thể:

1. Phát hành hai bộ cài riêng theo kiến trúc.
2. Dùng một gói ứng dụng chứa JDK/native payload cho từng kiến trúc và chọn đúng bộ khi cài/chạy.
3. Dùng universal native binaries cho phần native, đồng thời cung cấp JDK phù hợp cho từng kiến trúc.

Universal native binary không đồng nghĩa JDK trong gói cũng universal. Kiểm tra từng thành phần.

## 8. Kiểm tra và chuẩn hóa os.arch trong Java

Ứng dụng có thể đọc:

~~~java
String os = System.getProperty("os.name");
String arch = System.getProperty("os.arch");

System.out.println("OS: " + os);
System.out.println("Architecture: " + arch);
~~~

Giá trị architecture thường gặp:

| Giá trị | Cách hiểu |
| --- | --- |
| `aarch64` | ARM 64-bit |
| `arm64` | ARM 64-bit, alias thường gặp trong hệ sinh thái Apple |
| `x86_64` | Intel/AMD 64-bit |

Không nên chỉ so sánh chuỗi chính xác với một giá trị duy nhất. Có thể chuẩn hóa:

~~~java
static String normalizedMacArchitecture() {
    String arch = System.getProperty("os.arch")
            .toLowerCase(java.util.Locale.ROOT);

    return switch (arch) {
        case "aarch64", "arm64" -> "arm64";
        case "x86_64", "amd64" -> "x86_64";
        default -> throw new IllegalStateException(
                "Unsupported architecture: " + arch);
    };
}
~~~

Đoạn code chỉ nhận diện hai kiến trúc được ứng dụng hỗ trợ. Nếu sản phẩm có thêm kiến trúc khác, hãy mở rộng allowlist có kiểm thử thay vì âm thầm chọn một thư viện gần giống.

### Dùng kiến trúc JVM để chọn resource native

Ví dụ JAR chứa:

~~~text
native/
  macos-aarch64/
    libnative_math.dylib
  macos-x86_64/
    libnative_math.dylib
~~~

Ứng dụng chọn resource:

~~~java
String arch = normalizedMacArchitecture();
String resource = "/native/macos-" + arch
        + "/libnative_math.dylib";
~~~

Sau đó cần giải nén resource ra file thực trên filesystem và nạp bằng đường dẫn tuyệt đối:

~~~java
try (var input = NativeLoader.class.getResourceAsStream(resource)) {
    if (input == null) {
        throw new UnsatisfiedLinkError(
                "Native library not packaged: " + resource);
    }

    Path extracted = Files.createTempFile(
            "native-math-", ".dylib");
    Files.copy(input, extracted, StandardCopyOption.REPLACE_EXISTING);
    extracted.toFile().deleteOnExit();
    System.load(extracted.toAbsolutePath().toString());
}
~~~

Đây là mẫu tối giản. Ứng dụng thật cần quản lý quyền file, tên file duy nhất, cleanup, checksum và vòng đời của file được giải nén. Nếu native library phụ thuộc dylib khác, đường dẫn dependency của chúng cũng phải được cấu hình để loader tìm thấy.

Không chọn resource dựa trên kiến trúc phần cứng suy đoán từ model máy. Dùng kiến trúc JVM process để chọn binary cần nạp.

## 9. JNI trên macOS/AArch64

JNI (Java Native Interface) là giao diện được JDK công bố để Java gọi code native và native code gọi lại JVM. JNI header được cung cấp trong JDK, thường ở:

~~~text
$JAVA_HOME/include/jni.h
$JAVA_HOME/include/darwin/jni_md.h
~~~

Code native được biên dịch thành Mach-O dylib cho architecture mục tiêu. Cùng một source C/C++ có thể được build riêng cho ARM64 và x86_64 nếu compiler, SDK và mọi dependency hỗ trợ các target đó.

### Java declaration

Ví dụ class Java:

~~~java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(add(20, 22));
    }
}
~~~

`System.loadLibrary("native_math")` nhận tên thư viện logic, không truyền đường dẫn file đầy đủ. Trên macOS, `System.mapLibraryName("native_math")` thường ánh xạ sang tên file dạng `libnative_math.dylib`.

### Native implementation

File `native_math.c`:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_demo_NativeMath_add(
        JNIEnv *env,
        jclass type,
        jint left,
        jint right) {
    return left + right;
}
~~~

### Build dylib ARM64

Đặt JAVA_HOME trỏ tới JDK 17 ARM64:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17 -a arm64)

clang -dynamiclib \
  -arch arm64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Tùy dự án, cần thêm include path, linker flags, thư viện native phụ thuộc và deployment target macOS. Dùng JDK/toolchain đã chọn làm mục tiêu và xác minh dependency native cũng có slice ARM64.

### Biên dịch Java và chạy

~~~bash
javac --release 17 -d out NativeMath.java
java -Djava.library.path="$PWD" -cp out demo.NativeMath
~~~

Lệnh giả định source nằm đúng cấu trúc package hoặc được compiler nhận diện qua source path. Có thể dùng đường dẫn file tương ứng trong project.

Sau khi build, kiểm tra:

~~~bash
file libnative_math.dylib
lipo -archs libnative_math.dylib
~~~

Đảm bảo kết quả có slice ARM64 khi JVM chạy native trên Apple Silicon.

### Build cho Intel

Để tạo bản x86_64, build bằng target tương ứng:

~~~bash
clang -dynamiclib \
  -arch x86_64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Trong build pipeline cho Intel, JAVA_HOME nên trỏ tới JDK 17 x86_64 hoặc một toolchain/header setup đã được xác định rõ. Cần xác minh mọi thư viện được link cũng có slice x86_64.

### Build universal dylib

Nếu compiler và tất cả dependency hỗ trợ cả hai kiến trúc, Clang có thể tạo universal binary:

~~~bash
clang -dynamiclib \
  -arch arm64 \
  -arch x86_64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Hoặc build riêng từng kiến trúc rồi ghép:

~~~bash
lipo -create \
  -output libnative_math.dylib \
  libnative_math-arm64.dylib \
  libnative_math-x86_64.dylib
~~~

Kiểm tra kết quả:

~~~bash
lipo -archs libnative_math.dylib
~~~

Universal build chỉ thành công về mặt đóng gói khi mỗi slice được build đúng và các dependency tương ứng cũng sẵn có. Không thể lấy một dependency x86_64 rồi gắn nó vào slice ARM64 bằng lipo.

## 10. System.loadLibrary và System.load

Java cung cấp hai cách nạp thư viện native thường dùng:

| API | Đầu vào | Cách dùng |
| --- | --- | --- |
| `System.loadLibrary(name)` | Tên logic, không có path | JVM tìm library theo cơ chế và đường dẫn native library |
| `System.load(path)` | Đường dẫn tuyệt đối tới file | Nạp đúng file được chỉ định |

Ví dụ:

~~~java
System.loadLibrary("native_math");
~~~

Hoặc:

~~~java
System.load("/opt/myapp/native/arm64/libnative_math.dylib");
~~~

Với `System.loadLibrary`, có thể cấu hình:

~~~bash
java -Djava.library.path=/opt/myapp/native/arm64 \
     -cp app.jar \
     com.example.Main
~~~

`java.library.path` giúp JVM tìm thư viện JNI cấp đầu tiên. Nó **không tự sửa đường dẫn hoặc architecture của dependency mà dylib đó tham chiếu**. Nếu `libnative_math.dylib` liên kết tới `libimagecodec.dylib` qua install name hoặc rpath, macOS dynamic loader vẫn cần tìm được dependency đó.

### Phân biệt java.library.path và dyld search paths

Có hai bước tìm kiếm khác nhau:

1. JVM tìm file JNI mà ứng dụng yêu cầu qua System.loadLibrary hoặc System.load.
2. macOS dynamic loader tìm các dylib mà file JNI phụ thuộc dựa trên install name, rpath và cơ chế tìm kiếm của dyld.

Vì vậy, tăng `java.library.path` có thể sửa lỗi không tìm thấy file JNI chính, nhưng không nhất thiết sửa lỗi `Library not loaded` của một dylib phụ thuộc. Kiểm tra `otool -L` và rpath khi gặp trường hợp thứ hai.

## 11. Rpath và vị trí dependency trên macOS

Mach-O có thể ghi đường dẫn dependency theo các dạng:

- `@rpath`: tìm qua run-path search paths được khai báo.
- `@loader_path`: tương đối với thư mục chứa binary đang tham chiếu dependency.
- `@executable_path`: tương đối với thư mục chứa executable chính.

Ví dụ, một app bundle có thể đặt native libraries cùng thư mục:

~~~text
MyApp.app/
  Contents/
    MacOS/
      MyApp
    Frameworks/
      libnative_math.dylib
      libimagecodec.dylib
    app/
      application.jar
~~~

Một dylib trong Contents/Frameworks có thể dùng install name/rpath phù hợp để tìm dylib cùng thư mục, ví dụ dựa trên @loader_path. Cấu hình chính xác phụ thuộc vị trí của binary tham chiếu và cách linker tạo install name.

Kiểm tra load commands:

~~~bash
otool -L libnative_math.dylib
otool -l libnative_math.dylib
~~~

`otool -L` hiển thị dependency và install name. `otool -l` hiển thị load commands, bao gồm các LC_RPATH nếu có.

### Không nhầm java.library.path với rpath

java.library.path là cơ chế tìm thư viện do JVM sử dụng cho tên thư viện được nạp qua Java. Rpath là metadata của Mach-O dùng bởi dynamic loader để tìm dependency native. Hai cơ chế có liên quan trong quá trình load nhưng không thay thế nhau.

Đóng gói dylib cùng app bundle với rpath tương đối thường dễ triển khai và kiểm soát hơn việc phụ thuộc một thư mục cài đặt toàn cục trên máy người dùng.

## 12. JNA và các thư viện Java gọi native

JNA là thư viện bên thứ ba cho phép Java gọi native function mà không phải tự viết nhiều JNI boilerplate. Phần Java của JNA có thể chạy trên nhiều kiến trúc nếu bytecode tương thích, nhưng thành phần native dispatcher và các thư viện hệ thống/third-party mà JNA gọi vẫn cần đúng kiến trúc.

Khi dùng JNA trên Apple Silicon:

- Chọn phiên bản JNA có hỗ trợ macOS ARM64.
- Đảm bảo native dispatcher mà JNA nạp có slice phù hợp với JVM.
- Đảm bảo thư viện native đích mà JNA mở cũng hỗ trợ kiến trúc JVM process.
- Kiểm tra dependency native gián tiếp.
- Không giả định JAR Java thuần đồng nghĩa toàn bộ gói không có native code.

Các thư viện khác có JNI hoặc native bridge cũng tuân theo nguyên tắc tương tự. Kiểm tra tài liệu phân phối của thư viện và inspect native payload trong JAR hoặc thư mục cài đặt nếu có lỗi nạp.

### Native payload được đóng trong JAR

Một thư viện Java có thể chứa nhiều native resource:

~~~text
META-INF/
  native/
    macos-aarch64/
      libdispatch.dylib
    macos-x86_64/
      libdispatch.dylib
~~~

Loader của thư viện có thể chọn resource dựa trên OS/architecture, giải nén ra thư mục tạm và nạp. Khi cập nhật thư viện, kiểm tra JAR thực tế có payload cho kiến trúc mục tiêu; đừng chỉ nhìn version Java dependency.

## 13. Đóng gói dependency native theo OS và architecture

Nếu ứng dụng hỗ trợ cả macOS ARM64 và Intel, artifact native nên được phân loại rõ ràng. Một quy ước tên có thể là:

~~~text
native/
  macos-aarch64/
    libcodec.dylib
    libcrypto_adapter.dylib
  macos-x86_64/
    libcodec.dylib
    libcrypto_adapter.dylib
~~~

Hoặc đóng gói một universal library nếu toàn bộ dependency có đủ slice:

~~~text
native/
  macos-universal/
    libcodec.dylib
    libcrypto_adapter.dylib
~~~

Các tên thư mục trên là quy ước của ứng dụng, không phải chuẩn bắt buộc của macOS hoặc Maven/Gradle. Điều quan trọng là metadata artifact thể hiện được OS và architecture.

### Maven/Gradle dependency

Trong build system, có thể phát hành artifact native riêng theo classifier hoặc variant, ví dụ:

| Artifact variant | Nội dung |
| --- | --- |
| macOS ARM64 | Dylib và dependency cho ARM64 |
| macOS x86_64 | Dylib và dependency cho x86_64 |
| macOS universal | Dylib chứa cả hai slice cùng dependency tương ứng |

Không có một chuỗi classifier duy nhất bắt buộc cho mọi dự án. Chọn quy ước nhất quán trong repository và bảo đảm resolver chọn đúng variant.

Khi build native dependency, nên có CI matrix cho ARM64 và x86_64 hoặc một pipeline universal có xác minh cả hai slice. Không để máy build hiện tại tự quyết định architecture mục tiêu nếu artifact sẽ được phát hành cho nhiều nền tảng.

### Phân biệt build host và target architecture

Máy chạy compiler có thể khác kiến trúc mà bạn muốn phát hành. Ví dụ, một Mac ARM64 có thể cross-compile native code cho x86_64 nếu toolchain và dependency hỗ trợ. Ngược lại, việc build trên máy Intel không tự tạo ra binary ARM64.

Nên truyền target architecture như một tham số build tường minh:

~~~bash
./build-native.sh arm64
./build-native.sh x86_64
~~~

Script build cần dùng đúng compiler target, SDK, dependency và output directory. Không lấy os.arch của JVM build làm target mặc định khi pipeline đang cross-compile.

## 14. Kiểm tra architecture trong pipeline đóng gói

Một pipeline phát hành macOS có thể gồm:

1. Chọn JDK 17 ARM64 hoặc x86_64 theo artifact mục tiêu.
2. Biên dịch Java với target release phù hợp.
3. Build native library cho architecture mục tiêu.
4. Build hoặc lấy dependency native cùng architecture.
5. Kiểm tra từng Mach-O bằng file và lipo.
6. Kiểm tra dependency bằng otool -L.
7. Đặt dylib/framework vào đúng vị trí trong app bundle.
8. Cấu hình install name và rpath.
9. Chạy smoke test trên JVM cùng architecture.
10. Ký code và đóng gói sau khi binary đã hoàn tất.

### Ví dụ kiểm tra tự động

Một shell script đơn giản có thể yêu cầu slice ARM64:

~~~bash
#!/bin/bash
set -euo pipefail

LIB="dist/native/libnative_math.dylib"

file "$LIB"
ARCHS="$(lipo -archs "$LIB")"
echo "Architectures: $ARCHS"

case " $ARCHS " in
  *" arm64 "*) ;;
  *)
    echo "Missing arm64 slice: $LIB" >&2
    exit 1
    ;;
esac
~~~

Với artifact universal, kiểm tra cả hai:

~~~bash
ARCHS="$(lipo -archs dist/native/libnative_math.dylib)"
case " $ARCHS " in
  *" arm64 "*"x86_64 "*) ;;
  *)
    echo "Expected arm64 and x86_64 slices" >&2
    exit 1
    ;;
esac
~~~

Đối với nhiều thư viện, chạy kiểm tra trên toàn bộ danh sách binary native được đóng gói. Script mẫu chỉ xác minh slice của một file; nó không thay thế việc kiểm tra dependency đệ quy.

## 15. Code signing và đóng gói macOS

Ứng dụng macOS phân phối cho người dùng có thể cần code signing và notarization theo cách phân phối của sản phẩm. Native executable, dylib và framework nằm trong app bundle phải được đóng gói và ký phù hợp với chính sách của ứng dụng.

Các nguyên tắc quan trọng:

- Hoàn tất build và ghép universal slices trước khi ký.
- Kiểm tra binary sau khi copy vào app bundle.
- Ký các nested code theo đúng cấu trúc bundle và quy trình phát hành.
- Không sửa Mach-O sau khi ký.
- Thực hiện notarization theo yêu cầu phân phối của Apple.

Kiểm tra chữ ký:

~~~bash
codesign --verify --verbose=4 path/to/libnative_math.dylib
codesign -dv --verbose=4 path/to/libnative_math.dylib
~~~

Nếu dùng lipo -create hoặc một công cụ sửa Mach-O sau khi đã ký, chữ ký có thể không còn hợp lệ. Hãy hoàn tất việc ghép slice, chỉnh install name và bố trí dependency trước bước ký cuối.

Hardened Runtime, Library Validation và chính sách ký của ứng dụng có thể ảnh hưởng việc nạp native code. Khi gặp lỗi chữ ký, kiểm tra thông báo của hệ điều hành và cấu hình ký/notarization của sản phẩm. Không hướng dẫn người dùng tắt Gatekeeper hoặc vô hiệu hóa bảo vệ macOS như cách sửa mặc định.

## 16. Lỗi thường gặp và cách chẩn đoán

| Lỗi/triệu chứng | Nguyên nhân có thể | Kiểm tra và xử lý |
| --- | --- | --- |
| UnsatisfiedLinkError với incompatible architecture | Dylib không có slice của JVM process | Xem os.arch, file, lipo -archs; thay đúng artifact |
| Library not loaded | Không tìm thấy dependency dylib | Dùng otool -L, kiểm tra rpath và vị trí dependency |
| image not found | Sai đường dẫn hoặc install name | Kiểm tra System.load/java.library.path, otool -L |
| Symbol not found | ABI/symbol không khớp hoặc dependency sai version | Kiểm tra symbol export, version và dependency graph |
| no suitable image found | Binary không có slice phù hợp hoặc binary không hợp lệ | Kiểm tra Mach-O bằng file và lipo |
| code signature invalid | Binary bị sửa sau khi ký hoặc chữ ký không hợp lệ | Build/ký lại đúng thứ tự và xác minh nested code |
| JVM ARM64 nhưng JNA không nạp được dispatcher | JNA native payload không hỗ trợ ARM64 hoặc artifact sai | Nâng/chọn JNA hỗ trợ ARM64 và inspect payload |
| Chạy được khi mở Terminal qua Rosetta nhưng lỗi ở native mode | Hai lần chạy dùng kiến trúc JVM khác nhau | Kiểm tra os.arch; đóng gói đúng native slice |
| JNI library có ARM64 nhưng vẫn không load | Một dependency sâu chỉ có x86_64 | Duyệt dependency từ otool -L và kiểm tra từng binary |
| java.library.path đúng nhưng vẫn Library not loaded | JVM tìm thấy JNI library, dyld không tìm được dependency | Kiểm tra install name/rpath, không chỉ tăng java.library.path |
| Build host ARM64 tạo ra artifact Intel ngoài ý muốn | Target architecture không được cấu hình rõ | Chọn -arch/target tường minh trong native build |

### Quy trình debug theo thứ tự

Khi gặp lỗi native trên Apple Silicon:

1. In java.home, java.version và os.arch từ chính tiến trình lỗi.
2. Xác định JVM là ARM64 native hay x86_64 qua Rosetta.
3. Xác định file native thực sự được nạp, không chỉ file dự kiến trong build.
4. Chạy file và lipo -archs trên file đó.
5. Chạy otool -L để tìm dependency.
6. Kiểm tra architecture của từng dependency.
7. Kiểm tra rpath/install name nếu loader không tìm thấy file.
8. Kiểm tra code signature nếu lỗi liên quan xác thực binary.
9. Chạy lại trên runtime và môi trường đúng với gói phát hành.

Không đổi qua lại JDK ARM64 và x86_64 một cách ngẫu nhiên để che lỗi. Hãy xác định cấu hình sản phẩm cần hỗ trợ rồi giữ nguyên một tổ hợp runtime/native nhất quán trong test.

## 17. Có nên dùng Rosetta 2 cho ứng dụng Java?

Rosetta 2 cho phép chạy ứng dụng Intel trên Apple Silicon trong các trường hợp phù hợp. Vì thế, có thể chạy một JDK x86_64 và bộ native library x86_64 trên Mac ARM64 nếu ứng dụng còn phụ thuộc một thư viện chỉ có bản Intel.

Đây có thể là phương án chuyển tiếp khi dependency chưa có bản ARM64. Tuy nhiên:

- Toàn bộ native libraries trong tiến trình đó phải tương thích x86_64.
- Không thể nạp một dylib ARM64 vào JVM x86_64 đang chạy qua Rosetta.
- Ứng dụng đang chạy qua Rosetta không phải là ứng dụng JVM ARM64 native.
- Hiệu năng và mức tiêu thụ tài nguyên có thể khác native ARM64.
- Phải kiểm tra chính sách hỗ trợ của nhà cung cấp JDK và thư viện native.

Nếu dependency đã có ARM64, ưu tiên chạy JDK ARM64 native để có một stack cùng kiến trúc và tránh phụ thuộc vào translation layer.

Không nên coi Rosetta là cách biến một thư viện ARM64 thành thư viện Intel hoặc ngược lại. Rosetta dịch tiến trình x86_64; nó không cho phép một tiến trình trộn Mach-O image khác architecture.

## 18. Kiểm thử cả hai kiến trúc

Nếu ứng dụng phát hành cho cả Apple Silicon và Intel, cần kiểm thử trên cả hai cấu hình:

| Test | Apple Silicon native | Intel Mac |
| --- | --- | --- |
| JDK 17 đúng architecture | ARM64 | x86_64 |
| os.arch | ARM64/AArch64 | x86_64 |
| Native library | ARM64 hoặc universal | x86_64 hoặc universal |
| Dependency graph | Tất cả có ARM64 slice | Tất cả có x86_64 slice |
| JNI/JNA smoke test | Có | Có |
| File loading/rpath | Có | Có |
| Code signing | Xác minh bundle native | Xác minh bundle native |

Nếu không có máy Intel vật lý trong CI, có thể build/test target x86_64 trên môi trường phù hợp và kiểm tra slice bằng công cụ. Tuy nhiên, một lần chạy x86_64 qua Rosetta trên Apple Silicon không hoàn toàn thay thế kiểm thử trên Mac Intel thật; các khác biệt hệ điều hành, driver, SDK và native dependency vẫn có thể xuất hiện.

### Smoke test native

Một smoke test nên thực hiện tối thiểu:

- Khởi động JVM bằng đúng JDK mục tiêu.
- In os.arch và java.home.
- Nạp thư viện native.
- Gọi một native method đơn giản.
- Kiểm tra kết quả.
- Ghi nhận lỗi loader đầy đủ nếu có.

Ví dụ:

~~~java
public class NativeSmokeTest {
    public static void main(String[] args) {
        System.out.println("JVM architecture: "
                + System.getProperty("os.arch"));
        System.out.println("JDK home: "
                + System.getProperty("java.home"));

        System.loadLibrary("native_math");

        int result = NativeMath.add(20, 22);
        if (result != 42) {
            throw new AssertionError("Unexpected native result: " + result);
        }
        System.out.println("Native library loaded successfully");
    }
}
~~~

Smoke test xác nhận được đường nạp và lời gọi JNI cơ bản. Nó không thay thế test chức năng, concurrency, memory ownership hoặc error handling của native code.

## 19. ABI và macOS deployment target

Khớp architecture là điều kiện cần, nhưng chưa đủ. Native library còn phải tương thích với môi trường macOS mà ứng dụng hỗ trợ.

Các yếu tố cần kiểm tra:

- **macOS deployment target**: dylib có thể được build với minimum OS version mới hơn máy người dùng.
- **SDK và compiler**: binary có thể phụ thuộc symbol chỉ có trong SDK/runtime mới hơn.
- **ABI**: calling convention, struct layout, symbol visibility và các giả định giữa Java/native code phải khớp.
- **Dependency version**: thư viện native phụ thuộc có thể yêu cầu version khác.
- **Code signing**: binary phải đáp ứng chính sách ký của app.

Khi build bằng Clang, có thể đặt deployment target tường minh nếu dự án có yêu cầu:

~~~bash
clang -dynamiclib \
  -arch arm64 \
  -mmacosx-version-min=<minimum-supported-version> \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Giá trị minimum-supported-version phải phù hợp với macOS thấp nhất mà sản phẩm cam kết hỗ trợ, SDK, JDK và dependency. Không sao chép một giá trị tùy ý từ máy build.

Có thể xem thông tin build version và load commands bằng:

~~~bash
otool -l libnative_math.dylib
~~~

Tìm các load command liên quan phiên bản nền tảng, minimum OS và rpath. Cùng architecture nhưng yêu cầu minimum OS quá mới vẫn có thể làm thư viện không chạy trên máy cũ hơn.

## 20. Checklist đóng gói JDK macOS/AArch64

Trước khi phát hành bản Apple Silicon:

1. Chọn JDK 17 macOS/AArch64 từ nguồn phân phối được tổ chức hỗ trợ.
2. Kiểm tra java -version, java.home và os.arch.
3. Xác nhận JVM chạy native ARM64, không phải x86_64 qua Rosetta ngoài ý muốn.
4. Kiểm tra launcher và libjvm trong JDK bundle bằng file/lipo.
5. Chọn JNI/JNA/native payload có ARM64 slice.
6. Kiểm tra mọi dylib/framework dependency trực tiếp và gián tiếp.
7. Cấu hình java.library.path hoặc đường dẫn tuyệt đối cho thư viện JNI chính.
8. Cấu hình install name/rpath để dyld tìm được dependency.
9. Xác minh macOS deployment target và ABI của native library.
10. Chạy smoke test trên JDK ARM64.
11. Hoàn tất universal merge nếu có, rồi mới ký code.
12. Xác minh code signature và đóng gói/notarize theo quy trình macOS của sản phẩm.

Nếu phát hành đồng thời Intel và Apple Silicon, lặp lại quy trình cho x86_64 hoặc xác minh universal binary có đủ hai slice. Không đánh dấu một artifact universal chỉ dựa vào tên file.

## 21. Nguyên tắc thực hành

Khi đóng gói ứng dụng Java 17 có native dependency trên macOS:

1. Phân biệt kiến trúc phần cứng với kiến trúc JVM process.
2. Trên Apple Silicon, dùng JDK ARM64 native nếu dependency đã hỗ trợ.
3. Chọn native library theo os.arch của JVM, chuẩn hóa alias ARM64/AArch64.
4. Đảm bảo JNI/JNA library và toàn bộ dependency Mach-O có slice tương thích.
5. Dùng file, lipo và otool để kiểm tra binary thực tế.
6. Dùng universal binary khi mọi dependency có đủ slice và quy trình build đã xác minh.
7. Phân biệt java.library.path với rpath/install name của dyld.
8. Đặt target architecture rõ ràng trong native build; không nhầm build host với target.
9. Kiểm tra minimum macOS version, ABI và code signing ngoài architecture.
10. Chạy smoke test trên đúng JDK và kiến trúc mà gói phát hành hỗ trợ.

JDK macOS/AArch64 và thư viện native cùng kiến trúc giúp JVM chạy trực tiếp trên Apple Silicon và nạp được mã native tương ứng. Quyết định phải dựa trên kiến trúc của tiến trình JVM, không chỉ dựa vào phần cứng. Khi kiểm tra cả binary chính, dependency graph, đường dẫn dyld và chữ ký trước khi phát hành, lỗi architecture mismatch sẽ được phát hiện ở build/package stage thay vì xuất hiện trên máy người dùng.
