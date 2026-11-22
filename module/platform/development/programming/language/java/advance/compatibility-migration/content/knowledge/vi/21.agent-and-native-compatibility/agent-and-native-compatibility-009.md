# Chẩn đoán lỗi native và phân biệt với lỗi liên kết lớp Java

## 1. Vì sao hai nhóm lỗi này dễ bị nhầm?

Khi nâng cấp JDK, đổi container base image hoặc cập nhật thư viện, một ứng dụng Java có thể thất bại ngay khi khởi động, khi gọi một phương thức native hoặc sau nhiều giờ xử lý. Thông báo lỗi thường có những từ giống nhau như *library*, *class*, *symbol*, *link*, *load* hoặc *not found*. Nếu chỉ nhìn một dòng exception, nhóm phát triển rất dễ sửa sai tầng.

Ví dụ:

~~~text
java.lang.UnsatisfiedLinkError: no nativecalc in java.library.path
~~~

khác về bản chất với:

~~~text
java.lang.NoClassDefFoundError: com/example/api/Request
~~~

và khác cả:

~~~text
java.lang.NoSuchMethodError:
  'void com.example.api.Request.setId(java.lang.String)'
~~~

Trong trường hợp thứ nhất, ứng dụng không nạp được một **thư viện native** theo tên yêu cầu. Trường hợp thứ hai, JVM không tìm thấy hoặc không thể định nghĩa/khởi tạo một **class Java** cần thiết. Trường hợp thứ ba, bytecode của bên gọi trỏ tới **một method descriptor không còn khớp** với class Java có mặt lúc chạy.

Tuy nhiên, ranh giới không hoàn toàn trùng với cây kế thừa exception: `UnsatisfiedLinkError` cũng là một subclass của `LinkageError`. Vì thế, “có chữ LinkageError” **không đủ** để kết luận lỗi là Java-only; phải xem error subtype, giai đoạn xảy ra, stack trace, thông điệp và những thư viện đã nạp.

Bài học này cung cấp một phương pháp chẩn đoán có hệ thống cho Java Advance Compatibility Migration, trong chương **Agent và mã native**: từ classpath/module path, JNI/JNA, JVM loader và OS dynamic linker cho đến crash dump, class-file version, dependency resolution và tích hợp agent.

## 2. Bức tranh tổng thể: nhiều bộ nạp và nhiều tầng liên kết

Một chương trình Java có thể trải qua các giai đoạn:

~~~text
Source Java (.java)
        |
        v
Compiler (javac)  --->  Class files (.class)
                               |
                    Java ClassLoader / Module Layer
                               |
                     JVM link / verify / resolve
                               |
                     Java class initialization
                               |
                     Native method or library call
                               |
                System.load / System.loadLibrary / FFI
                               |
                     OS dynamic loader
                               |
                    Native .dll / .so / .dylib
                               |
                Dependent libraries + exported symbols
                               |
                       Native execution
~~~

Cần phân biệt **ít nhất bốn loại liên kết**:

1. **Java class loading:** tìm và định nghĩa class từ classpath, module path hoặc class loader tùy chỉnh.
2. **JVM linkage:** kiểm tra/giải quyết tham chiếu constant-pool tới class, field và method với descriptor, accessibility và dạng static/instance thích hợp.
3. **Native library loading:** OS dynamic loader tìm file nhị phân và các dependency của nó; JVM đưa thư viện vào ngữ cảnh của tiến trình.
4. **JNI/FFM symbol resolution:** runtime liên kết một native method hoặc foreign function tới symbol/địa chỉ tương ứng.

Một lỗi ở bước trước có thể **kéo theo lỗi hiển thị ở bước sau**. Chẳng hạn static initializer của class Java gọi `System.loadLibrary` rồi ném `UnsatisfiedLinkError`; những lần sử dụng class tiếp theo có thể chỉ thấy `NoClassDefFoundError: Could not initialize class...`. Vì vậy cần tìm **lỗi đầu tiên** trong log, không chỉ exception cuối.

## 3. Bảng phân biệt nhanh các triệu chứng

| Triệu chứng | Tầng thường liên quan | Gợi ý điều tra đầu tiên |
| --- | --- | --- |
| `UnsatisfiedLinkError: no X in java.library.path` | Tìm native library | Tên thư viện, đường dẫn, OS/architecture |
| `UnsatisfiedLinkError: ... cannot open shared object file` | OS dynamic loader | File native hoặc thư viện phụ thuộc, ELF dependencies |
| `UnsatisfiedLinkError: ... wrong ELF class: ELFCLASS32` | Native binary ABI | JVM 64-bit và native library 32-bit không khớp |
| `UnsatisfiedLinkError: '... nativeMethod(...)'` | JNI native symbol/method binding | Tên symbol JNI, chữ ký method, JAR/native version |
| `NoClassDefFoundError: com/.../Type` | Class loading/initialization | Runtime classpath/module path, root cause đầu tiên |
| `ClassNotFoundException` | Lookup class được yêu cầu động | `Class.forName`, class loader, module/dependency |
| `NoSuchMethodError` | Java binary method linkage | Method descriptor và JAR được resolve |
| `NoSuchFieldError` | Java binary field linkage | Tên/descriptor field và class runtime |
| `IllegalAccessError` | Java access/module linkage | Access modifiers và module exports |
| `IncompatibleClassChangeError` | Thay đổi dạng class/method/field | Static/instance, interface/class, ABI |
| `UnsupportedClassVersionError` | Java class-file version | Major version và JVM runtime |
| `ExceptionInInitializerError` | Class initialization | Exception gốc trong `<clinit>` |
| `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION`, `hs_err_pid*.log` | JVM fatal/native/unsafe | Problematic frame, native stack, JDK/agent/JNI |
| `ClassCastException` giữa hai class “cùng tên” | Runtime type identity/class loaders | Class loader của mỗi type; đây không phải `LinkageError` |

Đây là **các điểm bắt đầu**, không phải quy tắc khẳng định nguyên nhân duy nhất. Ví dụ, native library có thể được nạp từ static initializer; nếu native loader thất bại, phần tiếp theo của log có thể chứa cả lỗi Java initialization.

## 4. Phân biệt exception hierarchy một cách chính xác

Trong Java, `Error` thường mô tả những vấn đề nghiêm trọng mà code nghiệp vụ không nên xử lý bằng cách bắt rộng rồi tiếp tục như không có gì. Các lớp liên quan:

~~~text
Throwable
  +-- Error
       +-- LinkageError
            +-- UnsatisfiedLinkError
            +-- NoClassDefFoundError
            +-- IncompatibleClassChangeError
            |    +-- NoSuchMethodError
            |    +-- NoSuchFieldError
            |    +-- AbstractMethodError
            |    +-- IllegalAccessError
            +-- ClassFormatError
            |    +-- UnsupportedClassVersionError
            +-- VerifyError
       +-- ExceptionInInitializerError
  +-- Exception
       +-- ClassNotFoundException
       +-- RuntimeException
            +-- ClassCastException
~~~

Sơ đồ tập trung vào các nhánh quan trọng, không liệt kê mọi subtype.

**Điểm thường bị hiểu sai:** `UnsatisfiedLinkError` thuộc `LinkageError`, nhưng lỗi của nó thường liên quan đến **native library hoặc native method binding**. Ngược lại, `NoSuchMethodError` thường là liên kết method Java ở bytecode level. Phân nhóm theo *nơi JVM thất bại* hữu ích hơn chỉ phân nhóm theo base class.

### 4.1. Tại sao không nên `catch (LinkageError)` để che lỗi?

~~~java
try {
    service.start();
} catch (LinkageError ignored) {
    // Nguy hiểm: làm hệ thống tiếp tục với class/native state không hợp lệ.
}
~~~

Đây là anti-pattern. Việc bỏ qua lỗi liên kết có thể khiến chương trình hỏng ở chỗ khác và mất bằng chứng đầu tiên. Với một component tùy chọn, có thể thiết kế fallback rõ ràng khi *chưa* gọi vào nó hoặc khi biết chính xác exception có thể xử lý, nhưng phải ghi nhận root cause và giới hạn chức năng.

## 5. `UnsatisfiedLinkError` có nhiều nguyên nhân khác nhau

Không nên gộp mọi `UnsatisfiedLinkError` thành “thiếu DLL”. Có thể chia thành:

1. JVM không tìm thấy thư viện native theo tên.
2. JVM tìm thấy file nhưng OS loader không thể nạp vì architecture, ABI, permissions hoặc dependencies.
3. Thư viện nạp được nhưng một native method không liên kết được tới implementation.
4. Thư viện đúng tên nhưng sai version, thiếu exported symbol hoặc dùng calling convention/visibility không phù hợp.
5. Có xung đột class loader/native library ownership hoặc trình tự nạp.
6. Code native đã nạp nhưng lỗi phát sinh trong init/hook hoặc kết quả liên kết bị từ chối.

Ví dụ:

~~~text
java.lang.UnsatisfiedLinkError:
  no nativecalc in java.library.path: ...
~~~

thường cho thấy việc gọi `System.loadLibrary("nativecalc")` chưa xác định được file phù hợp theo search path.

~~~text
java.lang.UnsatisfiedLinkError:
  'int example.nativebridge.NativeMath.add(int, int)'
~~~

thường gợi ý native method `add` được khai báo nhưng chưa có implementation native tương ứng được JVM liên kết, kể cả khi một JAR và một library đã có mặt.

### 5.1. Đọc toàn bộ thông điệp, không chỉ tên class

Với JNI, tên method, kiểu tham số và kiểu trả về trong thông điệp là dấu hiệu rất quan trọng. Với OS loader, tên file, `cannot open shared object file`, `undefined symbol` hoặc tên dependency native mới là đầu mối.

Với Windows, lỗi có thể được diễn đạt như “The specified module could not be found” ngay cả khi DLL chính tồn tại: **một DLL phụ thuộc** của nó có thể thiếu. Không vội kết luận `java.library.path` sai khi chưa xem dependency graph native.

## 6. `System.load` và `System.loadLibrary`

Hai API tiêu biểu:

~~~java
System.load("/absolute/path/libnativecalc.so");
System.loadLibrary("nativecalc");
~~~

**`System.load`** nhận đường dẫn tuyệt đối tới file thư viện native. **`System.loadLibrary`** nhận **logical library name** và để JVM ánh xạ tên, tìm thư viện qua cơ chế tìm kiếm áp dụng cho runtime/platform.

Ví dụ ánh xạ thông thường:

| OS | Logical name `nativecalc` | File điển hình |
| --- | --- | --- |
| Windows | `nativecalc` | `nativecalc.dll` |
| Linux | `nativecalc` | `libnativecalc.so` |
| macOS | `nativecalc` | `libnativecalc.dylib` |

Không thêm `lib` hoặc đuôi `.so` vào lời gọi `loadLibrary` nếu thư viện đang được đặt theo quy ước logical name, trừ khi API/vendor có quy tắc riêng.

### 6.1. `java.library.path` không phải `java.class.path`

`java.class.path` điều khiển đường tìm kiếm các Java classes/JARs theo cơ chế classpath. `java.library.path` ảnh hưởng cách tìm native libraries của `System.loadLibrary` trên JVM phù hợp.

~~~bash
java -Djava.library.path=/opt/app/native \
     -cp app.jar example.Main
~~~

Lệnh chỉ minh họa. `-Djava.library.path` là JVM option và cần được truyền trước entry point. Thay đổi `System.setProperty("java.library.path", "...")` sau khi JVM đã chạy **không phải cách đáng tin cậy** để yêu cầu JVM tra lại native search path, vì nội bộ loader có thể đã khởi tạo/cached thông tin.

Với môi trường cần độ xác định cao, có thể dùng `System.load` với một **absolute path được quản lý và kiểm chứng**, thay vì dựa vào giá trị tình cờ trong OS path. Nhưng việc load theo path tuyệt đối cũng không tự giải quyết các thư viện phụ thuộc mà OS dynamic loader cần tìm.

## 7. OS loader: tìm được file chưa chắc nạp được

Native file thường liên kết với các thư viện khác:

~~~text
Java app
   |
   v
libnativecalc.so
   +-- libc.so
   +-- libstdc++.so
   +-- libvendorcrypto.so
   +-- platform runtime libraries
~~~

Nếu `libnativecalc.so` có mặt nhưng thiếu `libvendorcrypto.so`, việc nạp có thể thất bại.

### 7.1. Linux

Các công cụ tham khảo khi làm việc với thư viện **đáng tin**:

~~~bash
file /opt/app/native/libnativecalc.so
readelf -h /opt/app/native/libnativecalc.so
readelf -d /opt/app/native/libnativecalc.so
ldd /opt/app/native/libnativecalc.so
~~~

`file`/`readelf` hỗ trợ xem loại ELF, architecture, shared dependencies hoặc RPATH/RUNPATH metadata. `ldd` giúp xem thư viện phụ thuộc được resolution ở môi trường hiện tại, nhưng cần thận trọng với **binary không đáng tin**; đối với file chưa rõ provenance, ưu tiên công cụ phân tích tĩnh như `readelf` trước.

Đường tìm kiếm native dependencies ở Linux có thể liên quan `RPATH`, `RUNPATH`, `LD_LIBRARY_PATH`, cấu hình loader và system library directories. Không tự giả định `java.library.path` cũng áp dụng cho mọi lần OS loader giải quyết thư viện phụ thuộc.

### 7.2. macOS

~~~bash
file /opt/app/native/libnativecalc.dylib
otool -L /opt/app/native/libnativecalc.dylib
~~~

Kiểm tra architecture, install names, dependencies, `@rpath`/`@loader_path` và các quy tắc runtime. Biến môi trường `DYLD_*` có thể bị hạn chế trong những ngữ cảnh có System Integrity Protection, do đó không nên coi đặt một biến môi trường là cách sửa universal.

### 7.3. Windows

Với Developer Command Prompt/Visual Studio toolchain:

~~~text
dumpbin /HEADERS nativecalc.dll
dumpbin /DEPENDENTS nativecalc.dll
dumpbin /EXPORTS nativecalc.dll
~~~

Các lệnh chỉ có khi công cụ Windows tương ứng được cài. Ngoài DLL chính, cần kiểm tra các dependent DLL và runtime như Microsoft Visual C++ Redistributable được yêu cầu bởi toolchain tạo DLL.

Không tải một DLL tên giống nhau từ Internet để sửa lỗi “module not found”: việc đó tạo rủi ro supply-chain và có thể nạp nhầm binary không tương thích.

## 8. Mismatch architecture, ABI, libc và runtime nền tảng

Một thư viện native có thể đúng tên nhưng sai kiến trúc:

- JVM 64-bit nhưng DLL/SO 32-bit.
- Container chạy `linux/arm64` nhưng native library chỉ có `x86_64`.
- Binary liên kết `glibc` trong khi image dùng `musl`, hoặc ngược lại.
- Binary cần symbol/version của thư viện hệ điều hành mới hơn image.
- Windows DLL được biên dịch bằng toolchain yêu cầu runtime chưa được cài.
- macOS binary chỉ chứa architecture slice khác với CPU/runtime hiện tại.

Ví dụ thông điệp:

~~~text
wrong ELF class: ELFCLASS32
~~~

hoặc:

~~~text
version 'GLIBC_2.xx' not found
~~~

Hai trường hợp không thể sửa bằng thêm JAR Java. Cần lựa chọn binary đúng platform/architecture/ABI, cài đúng native dependency được phép hoặc thay image/toolchain để tương thích.

### 8.1. Container base image là một phần của bài toán

Đổi image từ Debian/Ubuntu sang Alpine có thể ảnh hưởng glibc/musl dù version JDK vẫn giống nhau. Đổi từ `amd64` sang `arm64` có thể làm JNI library lỗi trong khi toàn bộ Java bytecode vẫn chạy được.

Trong Java compatibility migration, hãy ghi **JDK vendor + release + OS image + libc + CPU architecture** như một bộ version chung, không chỉ ghi “Java 21”.

## 9. JNI native method linking: vì sao có thư viện nhưng method vẫn không tìm thấy?

Ví dụ Java:

~~~java
package example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("nativecalc");
    }

    private NativeMath() {}

    public static native int add(int left, int right);
}
~~~

JVM cần tìm implementation phù hợp khi phương thức `add` được gọi. Nếu thư viện đã nạp nhưng không cung cấp symbol/registration tương ứng, JVM có thể ném `UnsatisfiedLinkError` cho chính method.

Những nguyên nhân phổ biến:

- Đổi Java package, class hoặc method name nhưng không rebuild native library.
- Đổi số lượng/kiểu tham số, static/instance hoặc chữ ký method.
- Native function không được export đúng cách.
- C/C++ name mangling hoặc calling convention sai.
- Library JAR và native artifact đến từ hai version khác nhau.
- Native method dự kiến đăng ký qua `RegisterNatives` nhưng registration không thành công.
- Class loader nạp khác class mà native registration nhắm tới.

**Quan trọng:** Cùng tên method ở Java **không đủ** để JNI linkage chính xác. Method descriptor gồm cả kiểu tham số và kiểu trả về ở JVM level; overloaded native methods cần cơ chế tên JNI hoặc registration thích hợp.

## 10. Tạo JNI header bằng `javac -h`

Không tự đoán tên hàm JNI nếu có package, overload, ký tự đặc biệt hoặc tên đã đổi. Với JDK hiện đại, dùng compiler sinh header:

~~~bash
javac -h build/headers \
      -d build/classes \
      src/main/java/example/nativebridge/NativeMath.java
~~~

Compiler tạo header minh họa `example_nativebridge_NativeMath.h` với prototype tương ứng:

~~~c
JNIEXPORT jint JNICALL
Java_example_nativebridge_NativeMath_add(
    JNIEnv *, jclass, jint, jint);
~~~

Với method `static`, tham số thứ hai là `jclass`; với instance native method thường là `jobject`. `JNIEnv*` là handle tương tác JNI trong native code.

Native implementation mẫu, minh họa với các giá trị nhỏ:

~~~c
#include "example_nativebridge_NativeMath.h"

JNIEXPORT jint JNICALL
Java_example_nativebridge_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
~~~

Trong code C production, phải xem thêm kiểm tra overflow, validation, error propagation, allocation và memory safety theo nghiệp vụ. Ví dụ chỉ giúp quan sát **khớp chữ ký JNI**, không phải thư viện native được thiết kế hoàn chỉnh.

### 10.1. Biên dịch thư viện mẫu trên Linux

Với compiler C và JDK headers phù hợp:

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/native/libnativecalc.so \
  src/native/nativecalc.c
~~~

Giả định thư mục output đã được tạo. Cờ compiler và đường dẫn headers khác nhau giữa Windows, macOS và Linux; không copy lệnh Linux sang Windows rồi coi compiler/JNI hỏng.

Chạy:

~~~bash
java -Djava.library.path=build/native \
     -cp build/classes example.nativebridge.Main
~~~

`Main` là entry point ứng dụng minh họa, phải tự tạo để gọi `NativeMath.add(2, 3)`. Với một thư viện thực, ưu tiên build script có toolchain/version cố định thay vì bước biên dịch thủ công ngoài CI.

## 11. Kiểm tra symbol JNI và method descriptor

Ở phía Java:

~~~bash
javap -classpath build/classes \
      -private -s example.nativebridge.NativeMath
~~~

Một phần output có dạng:

~~~text
public static native int add(int, int);
  descriptor: (II)I
~~~

`(II)I` nghĩa là method nhận hai `int` và trả `int`. Nếu Java chuyển sang `long`, descriptor sẽ khác; chỉ rebuild Java mà không rebuild native library có thể gây lỗi.

Ở Linux, xem exported symbols:

~~~bash
nm -D --defined-only build/native/libnativecalc.so
readelf -Ws build/native/libnativecalc.so
~~~

Ở macOS, có thể dùng `nm`/`otool` theo cách phù hợp Mach-O. Ở Windows, xem `dumpbin /EXPORTS`. Tìm tên JNI function được export hoặc xác định code đã dùng `RegisterNatives`.

### 11.1. Dynamic registration không dùng cùng quy tắc tên export

JNI hỗ trợ `RegisterNatives` để gắn một Java native method với function pointer đã đăng ký. Khi đó native function không nhất thiết export theo mẫu tên dài `Java_package_Class_method`.

Vì vậy, **không thấy tên hàm JNI trong bảng export chưa đủ** để kết luận library hỏng. Cần biết dự án dùng **name-based resolution** hay **explicit registration**. Nếu dùng registration, phải kiểm tra mapping method names/descriptors và kết quả trả về của `RegisterNatives`.

### 11.2. Trường hợp overload

Giả sử có:

~~~java
public static native int convert(int value);
public static native long convert(long value);
~~~

JNI name-based mangling cho overloaded methods có quy tắc phân biệt chữ ký tham số. Không copy tên function từ một bản Java cũ rồi đổi typedef theo cảm tính. Hãy regenerate headers và xem exported symbol thật.

## 12. `JNI_OnLoad` và khởi tạo native library

Một native library có thể khai báo `JNI_OnLoad` để thực hiện một số bước khởi tạo JNI và trả JNI version được hỗ trợ. Đây là hook tùy chọn; **không phải mọi JNI library đều cần khai báo `JNI_OnLoad`**.

Ví dụ C:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    return JNI_VERSION_1_8;
}
~~~

Trong thực tế, library có thể dùng hook này để lấy `JNIEnv`, đăng ký native methods, khởi tạo cache hoặc kiểm tra runtime. Lỗi khi khởi tạo native library cần được đối chiếu với JVM logs và native library implementation.

Không nên thay đổi giá trị JNI version tùy tiện để “cho JDK mới chạy”; phải xem API JNI version mà thư viện thật sử dụng và quy tắc JVM hỗ trợ.

### 12.1. Một thư viện native không chỉ phụ thuộc Java

`JNI_OnLoad` có thể gọi code từ các native libraries khác hoặc bắt đầu hoạt động của một subsystem. Nếu tiến trình lỗi ngay tại lần `System.loadLibrary`, cần xem:

- Native constructors/initializers và hook `JNI_OnLoad`.
- Thư viện phụ thuộc và environment variables.
- Đồng bộ/threading trong code khởi tạo.
- JNI exception pending hoặc lỗi returned status.
- Phiên bản JDK/JNI và vendor support.

Đừng coi tất cả lỗi trong giai đoạn này là thiếu file SO/DLL.

## 13. Java class linkage: lỗi Java có cơ chế riêng

JVM sử dụng thông tin từ class files và constant pool để liên kết các class/method/field. Một JAR có thể biên dịch được với thư viện v1 nhưng được chạy cùng thư viện v2 không giữ binary compatibility.

Ví dụ:

~~~java
// Library v1
public class UserService {
    public String load(String id) {
        return id;
    }
}
~~~

Consumer đã được compile với method `load(String):String`. Library v2 đổi thành:

~~~java
// Library v2: incompatible method descriptor
public class UserService {
    public long load(long id) {
        return id;
    }
}
~~~

Khi chạy consumer bytecode cũ với v2, JVM có thể ném `NoSuchMethodError`. Điều này **không liên quan JNI** chỉ vì từ “linkage” xuất hiện.

Giải pháp là giữ binary-compatible overload/adapter nếu cần consumer cũ, hoặc rebuild toàn bộ consumer với API mới và triển khai bộ artifact nhất quán.

### 13.1. `NoSuchFieldError` và `IncompatibleClassChangeError`

Đổi tên/kiểu field hoặc xóa field có thể gây `NoSuchFieldError`. Đổi static method thành instance method hoặc thay một quan hệ class/interface có thể dẫn tới `IncompatibleClassChangeError` và các subtype liên quan.

Không sửa bằng đặt `java.library.path` hoặc copy thêm native DLL. Cần xem **Java ABI và JAR resolution**.

## 14. `NoClassDefFoundError` khác `ClassNotFoundException`

### 14.1. `ClassNotFoundException`

Exception dạng checked thường xuất hiện khi code chủ động tìm một class theo tên:

~~~java
Class<?> type = Class.forName(
        "com.example.optional.Plugin");
~~~

Nếu class loader không tìm thấy class, lời gọi có thể ném `ClassNotFoundException`. Điều tra tên class, class loader đang dùng, module path và dependency được triển khai.

### 14.2. `NoClassDefFoundError`

`NoClassDefFoundError` là `LinkageError`. Nó có thể xảy ra khi một class cần thiết từng có mặt lúc compile nhưng không thể được JVM tìm hoặc định nghĩa tại runtime, hoặc một class từng **khởi tạo thất bại**.

Ví dụ:

~~~text
java.lang.NoClassDefFoundError:
  com/example/shared/Request
~~~

Kiểm tra runtime artifact, classpath/module path, dependency exclusions, shading hoặc class loader.

### 14.3. `Could not initialize class`

Ví dụ:

~~~java
public final class NativeClient {
    static {
        System.loadLibrary("nativecalc");
    }
}
~~~

Lần dùng đầu tiên có thể thất bại ngay ở `System.loadLibrary` với `UnsatisfiedLinkError`. Class initialization không thành công; những lần dùng tiếp theo có thể báo:

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class com.example.NativeClient
~~~

Nếu chỉ thấy `NoClassDefFoundError` cuối cùng rồi thêm JAR, có thể bỏ qua lỗi native gốc. Cần tìm **stack trace đầu tiên trong cùng JVM process** và xem nguyên nhân khởi tạo class.

## 15. `ExceptionInInitializerError` và lỗi trong `<clinit>`

JVM thực hiện static initialization trong phương thức nội bộ thường được hiển thị là `<clinit>`.

~~~java
final class Config {
    static final String VALUE = initialize();

    static String initialize() {
        throw new IllegalStateException("invalid configuration");
    }
}
~~~

Nếu class initialization thất bại do một exception thông thường, JVM có thể bọc nó bằng `ExceptionInInitializerError`. Nhưng nếu mã static init ném một `Error` (chẳng hạn `UnsatisfiedLinkError`), không được giả định JVM sẽ luôn bọc nó bằng `ExceptionInInitializerError`.

Khi gặp:

~~~text
java.lang.ExceptionInInitializerError
    at ...
Caused by: java.lang.IllegalStateException: ...
~~~

hãy đọc `Caused by`. Khi gặp `NoClassDefFoundError: Could not initialize class`, hãy tìm event khởi tạo thất bại ban đầu của JVM đó.

### 15.1. Tại sao restart có thể làm thông báo thay đổi?

Class có initialization failure sẽ ở trạng thái lỗi trong phạm vi định nghĩa class tương ứng. Sau restart, lần dùng đầu lại kích hoạt initialization và có thể hiển thị lỗi gốc. Vì vậy “restart thì thấy exception khác” không chứng minh vấn đề đã đổi bản chất.

## 16. Classpath/module path và transitive dependency mismatch

Trong môi trường Java, hai phiên bản cùng một library có thể xuất hiện qua dependency graph:

~~~text
app
  +-- library-a
  |    +-- common-api:2.x
  +-- library-b
       +-- common-api:1.x
~~~

Build tool chọn phiên bản nào phụ thuộc resolution policy, BOM hoặc constraints. Consumer `library-a` có thể đã compile với `common-api:2.x`, nhưng runtime lại chứa `1.x`. Kết quả có thể là `NoSuchMethodError` hoặc `NoSuchFieldError`.

### 16.1. Gradle

Các lệnh điều tra dự án:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
  --dependency common-api \
  --configuration runtimeClasspath
~~~

Những lệnh này dành cho workflow chẩn đoán tại dự án; trong công việc viết bài không cần chạy build. Cần đọc **resolved version** thay vì chỉ số version được khai báo.

### 16.2. Maven

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Xác định dependencies trong classpath được triển khai, kể cả scope, BOM, exclusions, shading và các dependencies do application server đưa vào.

### 16.3. Module path

Nếu dùng Java Platform Module System, cần kiểm tra `module-info.java`, `requires`, module resolution và accessible packages. Một `ClassNotFoundException` hoặc `IllegalAccessError` có thể liên quan module path/exports khác classpath truyền thống.

Không nên dùng `--add-opens` diện rộng để sửa `NoSuchMethodError`: mở quyền reflection không khôi phục một method đã bị xóa khỏi JAR.

## 17. `UnsupportedClassVersionError` không phải lỗi native architecture

Khi JVM quá cũ cố nạp một class file có version mới hơn, có thể gặp:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime
~~~

Ví dụ bảng phổ biến:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Kiểm tra bằng:

~~~bash
javap -verbose -classpath app.jar \
  com.example.Main
~~~

Tìm `major version`. Nếu artifact target Java 21 mà runtime là Java 17, lựa chọn là chạy bằng JVM mới phù hợp hoặc compile bằng `--release 17` nếu nguồn/API/dependencies thực sự cho phép.

Ngược lại, native message `wrong ELF class` là mismatch **native binary architecture**, không phải Java class-file major version. Đừng sửa một lỗi bằng cách đổi `--release` khi root cause là ELF/DLL sai kiến trúc.

## 18. Multiple class loaders: cùng tên class chưa chắc cùng type

Trong application servers, plugin frameworks, OSGi hoặc container có loader isolation, type identity không chỉ là tên class mà còn bao gồm defining class loader. Hai class có cùng fully qualified name nhưng từ hai class loaders khác nhau có thể là hai kiểu khác nhau.

Triệu chứng:

~~~text
java.lang.ClassCastException:
  class com.example.Model cannot be cast
  to class com.example.Model
~~~

Thông điệp thực tế có thể cung cấp thêm thông tin class loader/module. Đây là lỗi type identity, **không phải `UnsatisfiedLinkError`**.

Native libraries cũng có liên quan class loader: JVM có cơ chế gắn native library với ngữ cảnh class loader khi load. Một thông điệp kiểu:

~~~text
Native Library ... already loaded in another classloader
~~~

gợi ý cùng thư viện native được tải từ một loader khác và xung đột ownership. Giải pháp có thể là quản lý nơi load thư viện, class-loader architecture hoặc phân tách runtime, không phải sao chép cùng DLL/SO sang nhiều folder ngẫu nhiên.

### 18.1. Class loader debugging

Có thể dùng class-load logging của JDK hiện đại:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Lệnh này giúp quan sát classes được nạp và nguồn khi runtime hỗ trợ unified logging. Do log có thể rất lớn, nên giới hạn việc thu thập và xử lý dữ liệu nhạy cảm. Với những JVM versions khác, kiểm tra `java -Xlog:help` để chọn tags/levels được hỗ trợ.

## 19. Phân biệt lỗi native load với JVM crash

Một native library **không nạp được** thường biểu hiện thành Java exception/error, ví dụ `UnsatisfiedLinkError`. Một native library **nạp được và thực thi code không an toàn** có thể gây lỗi nghiêm trọng làm JVM dừng:

~~~text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=..., pid=..., tid=...
# Problematic frame:
# C  [libnativecalc.so+0x...]
~~~

Hoặc trên Windows:

~~~text
EXCEPTION_ACCESS_VIOLATION
Problematic frame: C [nativecalc.dll+...]
~~~

Đây là hai nhóm lỗi khác nhau:

- **Java error có stack trace:** JVM còn hoạt động đủ để ném một đối tượng `Throwable`.
- **Fatal VM/native crash:** tiến trình có thể bị chấm dứt; bằng chứng chính là fatal error log, core/minidump hoặc OS event logs.

Không kỳ vọng `try/catch (Throwable)` có thể bắt mọi `SIGSEGV` do native code. Một lỗi segmentation fault có thể làm toàn JVM chết, không đi qua exception handling của Java.

### 19.1. Không phải mọi JVM crash đều do JNI

Problematic frame có thể nằm trong:

- Native library JNI/JNA của ứng dụng.
- Native JVMTI profiler/agent.
- JVM/JIT/GC runtime code.
- JNI helper hoặc platform library.
- Driver, SSL/crypto/native compression dependency.

Cần đọc frame và stack, so JDK vendor/build, agent versions và điều kiện tái hiện. Không mặc định JVM có bug chỉ vì process Java bị crash; cũng không khẳng định lỗi JNI khi frame nằm trong JVM mà chưa điều tra.

## 20. `hs_err_pid*.log` và bằng chứng từ fatal error

HotSpot thường tạo file fatal error log có tên dạng:

~~~text
hs_err_pid12345.log
~~~

Một số mục quan trọng:

| Mục | Cách sử dụng |
| --- | --- |
| Signal/exception | Xác định `SIGSEGV`, `SIGBUS`, access violation... |
| Problematic frame | Native library/JVM frame gần điểm phát hiện lỗi |
| Current thread | Thread đang gặp lỗi và trạng thái |
| Native frames | Các hàm native trên stack, nếu có symbol information |
| Java frames | Đường gọi Java liên quan nếu log thu được |
| Loaded libraries | Danh sách native modules đã nạp và đường dẫn |
| JVM arguments | JDK flags, agent, GC, module settings |
| VM/version/OS/CPU | Ràng buộc môi trường để tái hiện |
| Memory/thread information | Trạng thái bộ nhớ và một số dấu hiệu crash |

Không phải mọi log đều đầy đủ; lỗi rất nghiêm trọng hoặc môi trường hạn chế quyền ghi có thể khiến file không được tạo hoặc bị thiếu thông tin.

### 20.1. Chỉ định nơi lưu fatal error log

Với HotSpot hỗ trợ:

~~~bash
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log \
  -jar app.jar
~~~

`%p` là placeholder cho process ID trong option này. Cần bảo đảm thư mục tồn tại, process có quyền ghi và môi trường container có cơ chế giữ artifact khi container bị restart.

Fatal error logs có thể chứa đường dẫn, environment, arguments và những dữ liệu nhạy cảm. Hãy **redact** trước khi chia sẻ ngoài phạm vi được phép.

### 20.2. Core dump

Một core dump có thể cho phép native debugger xem stack và memory tại thời điểm crash, nhưng việc tạo core dump phụ thuộc OS, giới hạn process, quyền, `core_pattern`, container runtime và cấu hình JVM.

Ví dụ trên Linux:

~~~bash
ulimit -c unlimited
~~~

Đây chỉ là một trong những điều kiện cho core dump, không phải bảo đảm sẽ có file. Core dumps có thể chứa **toàn bộ dữ liệu nhạy cảm trong bộ nhớ**, nên phải tuân thủ chính sách lưu trữ, mã hóa, quyền truy cập và thời hạn xóa.

## 21. Symbolication và native stack traces

Thông điệp:

~~~text
Problematic frame:
C [libnativecalc.so+0x16a4]
~~~

cho biết offset trong native library nhưng không nhất thiết có tên hàm/source line. Để phân tích sâu, cần:

- Binary đúng **cùng build ID** với file đang chạy.
- Debug symbols tương ứng, ví dụ build với thông tin `-g` khi phù hợp.
- Native debugger tương thích môi trường như gdb/lldb/WinDbg.
- Core/minidump hoặc stack trace chứa địa chỉ hợp lệ.
- Thông tin ASLR và loaded module addresses để quy đổi chính xác.

Ví dụ trên Linux:

~~~bash
readelf -n /opt/app/native/libnativecalc.so
addr2line -e /opt/app/native/libnativecalc.so 0x16a4
~~~

`addr2line` chỉ hữu ích nếu địa chỉ/offset được quy đổi đúng và có symbol/debug information tương ứng. Không lấy tùy ý một offset từ log rồi xem kết quả là bằng chứng chắc chắn khi binary đã được strip hoặc khác build.

### 21.1. Debugger và thay đổi môi trường chạy

Gắn debugger vào một JVM production có thể dừng threads hoặc tác động timing. Chỉ thực hiện theo quyền/quy trình vận hành. Nên tái hiện trên staging với cùng native binary, JDK, architecture và input nếu có thể.

## 22. Những lỗi JNI memory và thread không biểu hiện bằng LinkageError

Không phải lỗi native nào cũng gây `UnsatisfiedLinkError`. Một JNI library đã liên kết thành công vẫn có thể làm hỏng bộ nhớ hoặc crash vì:

- Sử dụng `JNIEnv*` từ thread không phù hợp.
- Dùng local reference sau khi lifetime của nó kết thúc.
- Không giải phóng `GetStringUTFChars`/`Get*ArrayElements` theo contract.
- Vượt biên array/native buffer, use-after-free hoặc double free.
- Sử dụng sai `NewGlobalRef`/`DeleteGlobalRef`.
- Dùng pointer native đã bị invalid khi Java object hoặc native allocation thay đổi vòng đời.
- Không kiểm tra pending Java exception khi tiếp tục gọi JNI APIs.
- Gọi Java từ thread native chưa attach vào JVM đúng cách.
- Lỗi alignment, calling convention, encoding hoặc signed integer conversion.

Những lỗi này có thể biểu hiện là crash, dữ liệu sai hoặc deadlock chứ không phải Java exception có ý nghĩa rõ ràng.

### 22.1. `JNIEnv*` gắn với thread

Mã native không nên giữ một `JNIEnv*` rồi sử dụng từ thread khác. Nếu một native thread cần gọi vào JVM, phải tuân thủ API attach/detach thread của JNI và quản lý `JNIEnv*` ở đúng thread. Những vấn đề này có thể lộ ra khi nâng JDK do thay đổi timing, concurrency hoặc GC behavior, dù bug đã tồn tại từ trước.

### 22.2. Java reference lifetime và native pointers

Một JNI global reference giữ Java object theo quy tắc JNI cho đến khi được xóa. Một native pointer trỏ vào memory không tự có cùng lifecycle với Java object hoặc `MemorySegment`. Cần biểu diễn ownership rõ ràng: ai cấp phát, ai giải phóng, sau thời điểm nào không được truy cập.

Đừng coi một bug memory safety được “chữa” chỉ vì chạy lại test không crash.

## 23. `-Xcheck:jni` và chẩn đoán JNI contract violations

HotSpot cung cấp chế độ kiểm tra bổ sung:

~~~bash
java -Xcheck:jni \
  -Djava.library.path=/opt/app/native \
  -jar app.jar
~~~

`-Xcheck:jni` có thể phát hiện/cảnh báo một số cách dùng JNI không đúng hoặc dẫn đến lỗi khi gặp vi phạm. Đây là **công cụ chẩn đoán**, không phải chứng minh library không có bug và có thể tạo overhead hoặc thay đổi cách lỗi biểu hiện.

Nên dùng trong môi trường test/staging có workload tái hiện được, tránh tự ý bật trên hệ production tải cao mà không đánh giá ảnh hưởng.

### 23.1. Native sanitizers

Đối với code C/C++ JNI tự quản lý, các công cụ như AddressSanitizer (ASan) hoặc UndefinedBehaviorSanitizer (UBSan) có thể giúp phát hiện vấn đề memory/UB nếu native code được build với instrumentation phù hợp. Kết hợp với tests có input biên và code coverage native để tìm lỗi.

Native sanitizer không thay thế JVM class linkage diagnostics, và cách thiết lập sanitizer với JVM process cần đúng toolchain/OS. Không mặc định có thể gắn một flag compiler rồi chạy được trên mọi production image.

## 24. Native Memory Tracking và memory leak

Một ứng dụng có thể không crash ngay, nhưng tăng memory đến khi OS kill process. Đây có thể là:

- Java heap leak.
- Direct buffers hoặc native memory allocations.
- Thread stacks.
- JIT code cache, class metadata, GC/native JVM structures.
- JNI/JNA allocations hoặc native library leak.
- Memory sử dụng bởi agent hoặc exporter.

Với HotSpot có Native Memory Tracking (NMT), có thể khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -jar app.jar
~~~

và truy vấn bằng công cụ được phép:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

`<pid>` là placeholder cần thay bằng PID thật. NMT giúp quan sát những category mà JVM/HotSpot theo dõi; **nó không nhất thiết ghi nhận đầy đủ mọi allocation do thư viện native bên thứ ba tự thực hiện**. Vì thế một báo cáo NMT không có tăng bất thường không loại trừ hoàn toàn native memory leak.

Khi điều tra container OOMKill, so container memory usage, heap/direct memory, native libraries, thread count và OS kill logs. Đừng vội kết luận heap leak chỉ vì JVM process dùng nhiều RAM.

## 25. Agent/JVMTI có thể thay đổi toàn bộ quá trình chẩn đoán

Trong chủ đề “Agent và mã native”, một trường hợp quan trọng là JVM nạp Java agent hoặc native JVMTI agent khi khởi động:

~~~bash
java -javaagent:/opt/agent/apm.jar \
     -agentpath:/opt/agent/libprofiler.so \
     -jar app.jar
~~~

Nếu ứng dụng crash trong native library của profiler hoặc một agent dùng bytecode parser không hỗ trợ JDK mới, lỗi không nằm ở business JNI library dù stack trace liên quan class loading.

Kiểm kê:

- `-javaagent`, `-agentlib`, `-agentpath`.
- Agent versions, binary architecture và vendor support.
- Embedded ASM/Byte Buddy/native dependencies.
- Java Module System access và JVM flags.
- Dynamic attach qua công cụ vận hành hoặc test tooling.
- Instrumented libraries đã được framework/JDK nâng version.

### 25.1. So sánh có và không có agent

Trong một môi trường an toàn được phép thử:

1. Chạy cùng artifact/JDK với agent và ghi outcome.
2. Chạy bản thử nghiệm không agent hoặc chỉ một agent để khoanh vùng.
3. Đối chiếu startup, memory, crash log và native frames.
4. Xác định agent nào tạo ra khác biệt.
5. Khôi phục đúng cấu hình observability cần thiết và thử lại với agent tương thích.

Không được tắt các agent bảo mật/giám sát production như giải pháp vĩnh viễn chỉ vì việc tắt chúng làm lỗi biến mất. Chẩn đoán A/B là bằng chứng khoanh vùng, còn giải pháp cần đáp ứng policy của hệ thống.

## 26. JDK 21 và dynamic attach khác với lỗi native linkage

Trên JDK 21, JEP 451 đưa ra cảnh báo đối với việc nạp Java agent động trong những trường hợp phù hợp. Một công cụ mocking/test hoặc profiler có thể tự attach và làm logs xuất hiện warning. Đây là **chính sách instrumentation** chứ không nhất thiết là:

- Thiếu `libX.so`.
- Không tìm thấy JNI symbol.
- `NoSuchMethodError` của Java bytecode.
- JVM crash.

Nếu logs có warning dynamic loading, trước hết xác định agent nào đã được nạp, thông qua startup hay attach, và vendor guidance. Không chữa bằng copy thư viện native ngẫu nhiên hoặc thêm JVM module flags không liên quan.

Nếu dynamic attach bị policy chặn, cần xem target JVM flags, permissions và cách công cụ hỗ trợ startup agent. Không coi việc “attach được” đồng nghĩa “native library hoặc transformer tương thích”.

## 27. FFM API: thay thế JNI có giải quyết mọi vấn đề không?

Foreign Function & Memory (FFM) API, được chuẩn hóa trong Java 22, cung cấp cách tương tác với native code và off-heap memory qua Java APIs mà không phải viết JNI glue trong mọi tình huống. Nhưng chuyển từ JNI sang FFM **không xóa các ràng buộc native**:

- Native shared library vẫn phải phù hợp OS, architecture và ABI.
- Symbol và function descriptors phải khớp.
- Memory allocation, lifetime và thread confinement/ownership phải được quản lý đúng.
- Native access policy của runtime phải được tuân thủ.
- JDK version và sự khác biệt giữa preview/incubator với final API cần được xác định.

Nếu JDK mục tiêu là Java 17 hoặc 21, không thể copy ví dụ của FFM API final Java 22 mà mặc định compile được; phải xem API/trạng thái tương ứng trong JDK đang dùng. Với migration JDK 22+, FFM có thể là lựa chọn chiến lược, nhưng vẫn cần test native loading, symbol resolution, resource scope và performance.

### 27.1. Phân biệt lỗi qua biên FFM

Khi dùng FFM, một lỗi lookup symbol, descriptor sai hoặc memory lifetime có thể biểu hiện bằng những exception/diagnostics khác JNI. Không nên ép chúng vào bảng `UnsatisfiedLinkError` của `System.loadLibrary` một cách máy móc. Phân tích API gọi foreign function và OS loader vẫn là nguyên tắc cốt lõi.

## 28. Luồng chẩn đoán: bắt đầu từ dấu hiệu đầu tiên

~~~mermaid
flowchart TD
  A[Ứng dụng không chạy hoặc crash] --> B{Có hs_err/core/fatal signal?}
  B -->|Có| C[Đọc problematic frame, native stack, libraries]
  B -->|Không| D{Throwable đầu tiên là gì?}
  D -->|UnsatisfiedLinkError| E{Lỗi load library hay native method?}
  E -->|Load| F[Kiểm tra file, dependencies, ABI, search path]
  E -->|Method| G[Kiểm tra JNI symbol, descriptor, RegisterNatives]
  D -->|NoClassDefFoundError hoặc ClassNotFoundException| H[Kiểm tra runtime classpath, modules, init cause]
  D -->|NoSuchMethodError hoặc NoSuchFieldError| I[Kiểm tra Java ABI và dependency graph]
  D -->|UnsupportedClassVersionError| J[Kiểm tra major version và JVM]
  D -->|Khác| K[Đọc nguyên nhân gốc và tầng phát sinh]
  C --> L[Reproduce với đúng JDK, OS, native binary và agents]
  F --> L
  G --> L
  H --> L
  I --> L
  J --> L
  K --> L
  L --> M[Chọn thay đổi tối thiểu và integration tests]
~~~

Sơ đồ mang tính định hướng. Một lỗi class initialization có thể bọc hoặc che lỗi native phát sinh trước; vì thế khi nghi ngờ nhiều tầng, cần dựng **timeline của lỗi đầu tiên** theo process.

## 29. Bộ bằng chứng tối thiểu cho một báo cáo sự cố

Một incident record nên có:

~~~text
Incident ID:
First error timestamp:
JDK vendor/version/build:
OS/container image/architecture/libc:
Application artifact/hash:
Java classpath/module path:
Native library paths/versions/checksums:
JNI/JNA/FFM dependency versions:
Startup JVM flags (secrets redacted):
Java agents and JVMTI agents:
Reproduction inputs/steps:
First Java stack trace or fatal error log:
Native loader error text:
Suspected class/method/native symbol:
Baseline working combination:
Target failing combination:
Owner and next diagnostic action:
~~~

Không cần paste toàn bộ environment variables, secrets hoặc core dump vào ticket. Chỉ chia sẻ dữ liệu cần thiết, đã được bảo vệ và redact. Nếu lỗi xảy ra trong production với dữ liệu người dùng, quản lý log và artifacts theo chính sách bảo mật.

### 29.1. Đừng làm mất lỗi đầu tiên

Khi nhiều threads cùng khởi động và một static initializer thất bại, những thread đến sau có thể chỉ thấy `NoClassDefFoundError`. Hãy giữ stderr/startup logs từ lúc process bắt đầu, không chỉ phần cuối sau restart loop.

## 30. Bước thực hành: chẩn đoán native library không load trên Linux

Giả sử:

~~~text
java.lang.UnsatisfiedLinkError:
  /app/native/libencoder.so: libcodec.so: cannot open shared object file
~~~

Thư viện chính `libencoder.so` đã được tìm theo path nhưng dependency `libcodec.so` thiếu hoặc không resolve được.

### 30.1. Điều tra

1. Xác nhận `libencoder.so` có tồn tại trong **container runtime cuối cùng**.
2. Kiểm tra architecture và binary bằng `file`/`readelf -h`.
3. Xem dependency entries bằng `readelf -d`.
4. Với binary đáng tin, dùng `ldd` để xem resolution; chú ý `not found`.
5. Kiểm tra `RPATH/RUNPATH` và loader configuration.
6. Xác định package/deployment nào phải cung cấp `libcodec.so`.
7. Đảm bảo đúng version/ABI, không chỉ file trùng tên.
8. Chạy lại trong image tương ứng, không chỉ máy dev.

### 30.2. Lựa chọn sửa

Có thể đóng gói native dependency đúng vào image, điều chỉnh loader paths theo policy, chọn binary được build đúng ABI hoặc cập nhật dependency stack. Không khắc phục bằng cách thêm một Java JAR không liên quan hoặc đổi `--release`.

### 30.3. Kiểm chứng

Test phải thực sự gọi chức năng dùng native library. Một test chỉ khởi tạo Java DTO có thể không chạm đường `System.loadLibrary` vì lazy loading, nên pass không chứng minh native đã được đóng gói đúng.

## 31. Bước thực hành: thư viện load nhưng `nativeMethod` vẫn báo lỗi

Giả sử:

~~~text
java.lang.UnsatisfiedLinkError:
  'long example.nativebridge.NativeMath.add(long, long)'
~~~

Trong phiên bản cũ Java native method nhận `int` và trả `int`; phiên bản mới đổi sang `long` để hỗ trợ giá trị lớn hơn. Nếu native library vẫn là bản cũ, tên/mapping JNI hoặc registration không khớp.

### 31.1. Điều tra

1. Kiểm tra Java class runtime thật bằng `javap -s -p`.
2. Xác nhận JAR đang dùng không phải artifact cũ được cache.
3. Regenerate header bằng `javac -h` từ source tương ứng.
4. Kiểm tra native exported symbols bằng `nm`/`dumpbin` nếu dùng name-based JNI.
5. Nếu dùng `RegisterNatives`, xác nhận name/signature mapping.
6. Kiểm tra native library file/checksum và load path thực tế.
7. Rebuild JAR/native library thành một **cặp version nhất quán**.
8. Test cả boundary values, không chỉ một phép tính nhỏ.

### 31.2. Không sửa bằng cách ép Java/JNI cast vô điều kiện

Thay `long` thành `int` để khớp native library cũ có thể gây overflow hoặc thay business semantics. Đúng hơn là quản lý compatibility contract giữa wrapper Java và native ABI. Nếu cần duy trì public API cũ, có thể cung cấp adapter/overload rõ ràng và kiểm tra miền giá trị khi chuyển đổi.

## 32. Bước thực hành: `NoSuchMethodError` khi đổi framework

Giả sử:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.User.getName()'
~~~

Consumer được compile với API cũ. Runtime deployment chọn library khác version, nơi `getName()` đã đổi hoặc bị xóa.

### 32.1. Điều tra

1. Xác định JAR thực sự chứa `com.example.api.User` ở runtime.
2. Kiểm tra method descriptor bằng `javap -s`.
3. Xem resolved dependency graph và BOM/constraints.
4. Kiểm tra classloader nếu có nhiều bản JAR.
5. So API trước/sau, đặc biệt parameters, return type, static/instance.
6. Cân nhắc giữ method/bridge/adapter hoặc rebuild consumers.
7. Test bằng đúng artifact packaging cuối, không chỉ IDE classpath.

**Không cần kiểm tra `LD_LIBRARY_PATH`** nếu stack trace cho thấy một method Java thuần bị mất, không có code native liên quan trong đường lỗi.

## 33. Bước thực hành: static initializer che lỗi native gốc

Class:

~~~java
public final class CryptoEngine {
    static {
        System.loadLibrary("cryptobackend");
    }

    public static byte[] encrypt(byte[] input) {
        // Logic sử dụng native backend.
        throw new UnsupportedOperationException("example");
    }
}
~~~

Một JVM khởi động với native dependency thiếu.

**Lần đầu:**

~~~text
java.lang.UnsatisfiedLinkError:
  no cryptobackend in java.library.path
    at java.lang.System.loadLibrary(...)
    at com.example.CryptoEngine.<clinit>(...)
~~~

**Lần tiếp theo trong cùng runtime:**

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class com.example.CryptoEngine
~~~

Nếu chỉ xem log cuối, người điều tra có thể tưởng Java class mất khỏi classpath. Nhưng vấn đề ban đầu là native dependency không load được.

Cách xử lý:

1. Giữ startup logs và lỗi đầu tiên.
2. Xác định đường gọi `<clinit>`.
3. Kiểm tra native search path và binary dependencies.
4. Sửa deployment/image.
5. Khởi chạy JVM mới để thử lại, không dựa vào việc class đã lỗi sẽ tự hồi phục.

## 34. Ma trận thí nghiệm khi nâng JDK và native dependency

Để phân biệt tác động JDK với native library hoặc agent, dùng các tổ hợp:

| Thử nghiệm | JDK | Java JARs | Native libraries | Agent | Ý nghĩa |
| --- | --- | --- | --- | --- | --- |
| A | JDK cũ | Graph cũ | Binary cũ | Agent cũ | Baseline |
| B | JDK mới | Graph cũ | Binary cũ | Agent cũ | Xem JDK mới tự lộ incompatibility không |
| C | JDK mới | Graph cũ | Binary mới | Agent cũ | Khoanh vùng native binary |
| D | JDK mới | Graph mới | Binary mới | Agent cũ | Khoanh vùng Java dependency graph |
| E | JDK mới | Graph mới | Binary mới | Agent mới | Tổ hợp đích |
| F | JDK mới | Graph mới | Binary mới | Không agent, chỉ staging | Khoanh vùng instrumentation |

Không phải mọi tổ hợp đều được hỗ trợ. Ví dụ binary mới có thể yêu cầu libc/JDK cao hơn hoặc agent cũ không hỗ trợ JDK mới; ghi **unsupported combination** thay vì cố chạy và coi exception là kết quả kiểm thử có ý nghĩa.

### 34.1. Giữ môi trường càng giống càng tốt

Khi so sánh, cần cố định OS image, CPU architecture, config, database/driver, input data và startup flags khi khả thi. Nếu thay JDK cùng lúc với image từ glibc sang musl, việc lỗi native không thể quy ngay cho JDK.

## 35. Khi nào nên nâng thư viện, khi nào cần thay kiến trúc?

| Kết luận điều tra | Hướng xử lý thường phù hợp |
| --- | --- |
| Thiếu native file | Bổ sung binary chính xác vào packaging/deployment |
| Thiếu native dependency | Cung cấp dependency tương thích và loader path đúng |
| Sai OS/CPU/ABI/libc | Chọn/build binary đúng image |
| JNI signature mismatch | Rebuild JAR và native library đồng bộ; kiểm chứng descriptors |
| Native API đã không còn được vendor duy trì | Đánh giá thay thế library, API Java hoặc FFM khi JDK mục tiêu phù hợp |
| Lỗi Java `NoSuchMethodError` | Sửa dependency resolution và binary compatibility |
| `NoClassDefFoundError` sau init fail | Tìm nguyên nhân đầu tiên, có thể là native library |
| Agent/parser không hỗ trợ class-file mới | Nâng agent/tool theo support matrix |
| Native memory corruption/crash | Phân tích hs_err/core, debugger/sanitizers, sửa native code |
| Dynamic attach bị chính sách cấm | Dùng startup instrumentation hoặc giải pháp vận hành được phê duyệt |

Chọn bản vá nhỏ nhất giải quyết **nguyên nhân** và không phá support policy. Nếu native library đã ngừng bảo trì, việc thêm flags tạm có thể duy trì ngắn hạn nhưng cần lộ trình thay thế.

## 36. Checklist điều tra và migration

- [ ] Đã lưu **exception/fatal error đầu tiên**, không chỉ lỗi cuối.
- [ ] Đã phân biệt Java class loading, Java linkage, native loader và native method binding.
- [ ] Đã nhận diện `UnsatisfiedLinkError` là subtype của `LinkageError`.
- [ ] Đã phân biệt `ClassNotFoundException`, `NoClassDefFoundError` và class initialization failures.
- [ ] Đã dùng `javap -s/-verbose` khi nghi ngờ Java method descriptor/class-file version.
- [ ] Đã kiểm tra resolved JARs, runtime classpath/module path và classloader.
- [ ] Đã xác định native logical name, absolute file path và binary checksum.
- [ ] Đã kiểm tra architecture 32/64-bit, OS, libc và image.
- [ ] Đã xem native dependencies bằng công cụ phù hợp platform.
- [ ] Đã xác nhận `java.library.path` khác OS dependent library lookup.
- [ ] Đã kiểm tra JNI generated header, exported symbols hoặc `RegisterNatives` mapping.
- [ ] Đã xác nhận Java wrapper và native artifact thuộc bộ version nhất quán.
- [ ] Nếu có `SIGSEGV`/fatal error, đã lưu hs_err/core theo quy định bảo mật.
- [ ] Đã xem problematic frame, native stack và loaded libraries.
- [ ] Khi cần, đã dùng `-Xcheck:jni`/sanitizers trên môi trường phù hợp.
- [ ] Đã kiểm tra agent Java/JVMTI và bytecode tooling khi lỗi chỉ xảy ra ở JVM mới.
- [ ] Đã xác nhận đúng JDK vendor/version, OS image và architecture ở production.
- [ ] Đã test chức năng **thực sự gọi native path**, không chỉ khởi động app.
- [ ] Đã có ma trận A/B khi thay đổi JDK, Java dependencies, native binary và agents.
- [ ] Đã xác nhận fixes không yêu cầu nới lỏng permissions vô điều kiện.
- [ ] Có kế hoạch rollout, canary và rollback/roll-forward được chủ sở hữu duyệt.
- [ ] Incident notes không chứa secrets, raw core dump hoặc dữ liệu nhạy cảm không được phép.

## 37. Những hiểu lầm thường gặp

**“`UnsatisfiedLinkError` không phải `LinkageError`.”** Sai. Nó là một subclass của `LinkageError`, nhưng phần lớn triệu chứng của nó liên quan đến native loading/binding.

**“Có DLL/SO rồi thì chắc chắn native method chạy.”** Sai. File có thể sai ABI, thiếu dependency, thiếu symbol, sai registration hoặc bị loader khác nạp.

**“Chỉ cần thêm thư mục vào `java.library.path`.”** Không đủ nếu OS loader còn thiếu dependent library hoặc binary sai architecture.

**“`NoClassDefFoundError` luôn nghĩa là thiếu JAR.”** Sai. Class initialization có thể đã thất bại do lỗi native trước đó.

**“`ClassNotFoundException` và `NoClassDefFoundError` là một.”** Sai. Chúng thuộc nhánh exception/error khác nhau và thường biểu hiện ở đường xử lý khác nhau.

**“`NoSuchMethodError` phải sửa JNI.”** Không đúng nếu error trỏ tới method Java có ABI không còn khớp. Cần xem class và descriptor thực tế.

**“Java 21 chạy class-file Java 17 nên native code chắc chắn tương thích.”** Sai. Native binary còn phụ thuộc ABI, platform, JDK integration và thư viện nhúng.

**“`UnsupportedClassVersionError` và `wrong ELF class` có cùng nguyên nhân.”** Sai. Một bên là class-file Java version, bên kia thường là kiến trúc ELF/native.

**“`try/catch Throwable` sẽ bắt được mọi crash JNI.”** Sai. Native fatal signal có thể kết thúc JVM.

**“`hs_err_pid` chứng minh lỗi JVM.”** Không nhất thiết. Problematic frame có thể là JNI/native agent hoặc platform library.

**“`ldd` có thể chạy an toàn trên mọi file tải về.”** Không nên. Cần đánh giá provenance và ưu tiên công cụ phân tích tĩnh khi binary chưa đáng tin.

**“`-Xcheck:jni` không báo gì thì không có memory bug.”** Sai. Nó phát hiện một số vi phạm JNI, không thay toàn bộ memory-safety testing.

**“NMT sẽ hiển thị mọi allocation native của bên thứ ba.”** Không được bảo đảm.

**“Tắt agent là giải pháp production.”** Không phải khi agent cần cho security, monitoring hoặc quality policy. Dùng A/B staging để khoanh vùng và nâng đúng agent.

**“Thay JNI bằng FFM tự loại bỏ mọi vấn đề native.”** Sai. Library, ABI, symbol và memory lifetime vẫn cần được quản lý.

## 38. Tài liệu nên đối chiếu khi điều tra thực tế

Các nguồn kỹ thuật cần đọc theo JDK và OS được triển khai:

- **Java SE API — `UnsatisfiedLinkError`, `LinkageError`, `NoClassDefFoundError` và `ClassNotFoundException`:** phân biệt loại lỗi.
- **Java Virtual Machine Specification:** class loading, linking, initialization, method/field resolution và class-file format.
- **Java Native Interface Specification:** name resolution, JNI types, `JNIEnv`, `RegisterNatives` và library lifecycle.
- **`javac` và `javap` tool guides:** `javac -h`, method descriptors và class-file version.
- **JDK troubleshooting guide và HotSpot fatal error log documentation:** `hs_err_pid`, native crash, core dumps.
- **HotSpot `-Xcheck:jni` và Native Memory Tracking documentation:** chẩn đoán JNI/native memory.
- **Linux dynamic linker/ELF documentation:** `readelf`, `ldd`, RPATH/RUNPATH và symbol resolution.
- **macOS dynamic loader/Mach-O documentation:** `otool`, install names và `@rpath`.
- **Microsoft PE/DLL loading documentation:** dependency search, runtime/architecture và debug symbols.
- **Java Instrumentation/JVMTI và agent vendor documentation:** class loading, Java/native agent support theo JDK.
- **FFM API documentation trên JDK hỗ trợ:** foreign symbol lookup, descriptors và memory lifecycle nếu ứng dụng chuyển khỏi JNI.

Phiên bản JDK, vendor, libc, container image và native toolchain đều có thể làm thay đổi biểu hiện lỗi; cần đối chiếu đúng release thay vì áp dụng máy móc một kết luận từ môi trường khác.

## 39. Kết luận

Trong Java Advance Compatibility Migration, **lỗi native** và **lỗi liên kết class Java** có thể xuất hiện gần nhau nhưng yêu cầu cách điều tra khác nhau. `UnsatisfiedLinkError` thường dẫn tới đường tìm native library, ABI, dependency và JNI symbol binding; `NoSuchMethodError` hoặc `NoSuchFieldError` thường dẫn tới Java method/field descriptors và resolved JARs; `NoClassDefFoundError` có thể là thiếu class hoặc hậu quả của class initialization thất bại. Một JVM fatal crash đòi hỏi phân tích `hs_err_pid`, native frames hoặc core dump thay vì chỉ đọc Java stack trace.

Hướng tiếp cận đáng tin cậy là **xác định lỗi đầu tiên, phân tầng nơi thất bại, thu thập môi trường chạy chính xác, kiểm tra Java/JNI/native artifacts theo version nhất quán rồi tái hiện bằng ma trận có kiểm soát**. Đối với hệ thống dùng Java agents hoặc native JVMTI, phải đưa cả agent, class-file parser, module access và image/architecture vào danh sách tương thích. Khi nguyên nhân được chứng minh và sửa ở đúng tầng, việc nâng JDK mới thực sự có cơ sở an toàn, thay vì chỉ làm một exception biến mất để lỗi chuyển sang vị trí khác.
