# UnsatisfiedLinkError và native library trong nhiều ClassLoader

## 1. Vấn đề: Java class có thể cô lập, nhưng JNI library không được nạp tùy ý vào nhiều loader

Trong hệ thống plugin, một kiến trúc phổ biến là mỗi plugin sở hữu một `URLClassLoader` để tải class implementation và dependency của riêng mình. Các class có cùng *binary name* vẫn có thể tồn tại đồng thời nếu được **hai defining class loaders khác nhau** định nghĩa. Nhưng nếu mỗi plugin đều thực hiện `System.loadLibrary("nativecodec")` hoặc `System.load("/absolute/path/libnativecodec.so")` với **cùng một JNI native library**, lần nạp sau vào loader khác có thể thất bại với:

~~~text
java.lang.UnsatisfiedLinkError: Native Library ... already loaded in another classloader
~~~

Đây không nhất thiết là lỗi thiếu file. Trong trường hợp điển hình, **library đã tìm được và được nạp thành công**, nhưng đã được gắn với một class loader khác.

Đặc tả JNI Java 17 nêu rõ: **mỗi class loader quản lý tập native libraries riêng; cùng một JNI native library không thể được nạp vào nhiều class loaders**. Khi cố làm vậy, JVM ném `UnsatisfiedLinkError`. Quy tắc này nhằm bảo vệ *class-loader namespace separation*, tránh native code trộn các class có cùng tên nhưng khác runtime identity.

Vì vậy, câu hỏi đúng không chỉ là “đã cấu hình `java.library.path` chưa?” mà còn là:

1. **Thư viện native nào** được tải: tên logic, đường dẫn tuyệt đối, binary thực tế, dependency native?
2. **Java class nào** gọi `System.load`/`System.loadLibrary`? Nó thuộc **defining loader** nào?
3. **Library ấy đã được nạp vào loader khác chưa?** Vòng đời loader trước đã kết thúc thật sự chưa?
4. Lỗi xảy ra khi **tải thư viện native**, hay khi **liên kết lời gọi `native` với symbol**?
5. Plugin có thể dùng **một JNI bridge dùng chung ở parent loader** thay vì tải lại library ở mỗi child không?

Bài học phân biệt các nguyên nhân, thiết kế loader đúng và xây dựng ví dụ **Java 17 + C/JNI** có thể chạy để tái hiện chính xác việc nạp cùng một thư viện từ hai class loaders.

## 2. `UnsatisfiedLinkError` nằm ở đâu trong hệ thống lỗi Java?

Cấu trúc kế thừa:

~~~text
java.lang.Object
  └── java.lang.Throwable
      └── java.lang.Error
          └── java.lang.LinkageError
              └── java.lang.UnsatisfiedLinkError
~~~

`UnsatisfiedLinkError` là **`Error`**, không phải checked `Exception`. Nó có thể phát sinh khi JVM không liên kết được một native method declaration với implementation phù hợp, hoặc khi thao tác `System.load`/`System.loadLibrary` thất bại.

Ví dụ:

~~~java
public final class NativeCodec {
    static {
        System.loadLibrary("nativecodec");
    }

    public static native int encode(int value);
}
~~~

Đây là **mảnh code minh họa**, chưa chạy độc lập vì cần library native thực sự chứa implementation cho `NativeCodec.encode`.

Một trong nhiều kiểu lỗi có thể thấy:

~~~text
java.lang.UnsatisfiedLinkError: no nativecodec in java.library.path: ...
~~~

Nguyên nhân: thư viện không tìm thấy trong đường tìm đã cấu hình.

Một kiểu khác:

~~~text
java.lang.UnsatisfiedLinkError: Native Library ... already loaded in another classloader
~~~

Nguyên nhân: cùng JNI library đã gắn với loader khác.

Một kiểu nữa:

~~~text
java.lang.UnsatisfiedLinkError: 'int NativeCodec.encode(int)'
~~~

Đây là **dạng minh họa** cho trường hợp native method không có entry point/signature phù hợp; văn bản cụ thể của exception phụ thuộc JDK và signature.

Cả ba đều là `UnsatisfiedLinkError` nhưng cần **ba chiến lược điều tra khác nhau**. Không tự động giải quyết bằng cách thêm JAR, tăng quyền reflection hoặc đổi tên Java class.

## 3. Cơ chế JNI kết hợp với ClassLoader

Java cung cấp hai mô hình liên quan mà ta cần phân biệt.

**Java bytecode loading:**

~~~text
App class loader
  |
  +-- PluginLoader A -> (plugin.NativeBridge, Loader A)
  |
  +-- PluginLoader B -> (plugin.NativeBridge, Loader B)
~~~

Hai `Class<?>` mang tên `plugin.NativeBridge` là hai runtime types nếu mỗi child tự định nghĩa.

**JNI native library management:**

~~~text
PluginLoader A
      |
  System.load("/opt/native/libbridge.so")
      |
      v
JVM native-library registry / loader A
      |
      +--> libbridge.so  [loaded]

PluginLoader B
      |
  System.load("/opt/native/libbridge.so")
      |
      v
JVM phát hiện cùng JNI library thuộc loader A
      |
      +--> UnsatisfiedLinkError
~~~

**Quy tắc cơ bản:** việc một class Java được tải vào loader B **không biến native library đã gắn với A thành library của B**. JVM quản lý thông tin về native libraries, JNI entry points và classloader ownership theo đặc tả JNI.

### Vì sao giới hạn này cần thiết?

JNI nhận tham chiếu tới Java objects/classes và có thể cache `jclass`, `jmethodID`, `jfieldID`, global references, hoặc đăng ký native methods bằng `RegisterNatives`. Hai Java classes có **cùng binary name** nhưng khác defining loader **không phải cùng runtime type**.

Nếu một native binary bị gắn một cách tùy tiện với hai classloader namespaces, native code có thể nhầm metadata/type references và phá cô lập kiểu mà JVM muốn duy trì. Vì vậy JNI không coi native code đơn giản là “thư viện toàn tiến trình, class nào cũng dùng được” theo nghĩa classloader-independent.

**Đừng nhầm điều này với hành vi loader cha:** nếu cả hai plugin thực sự delegate tới **cùng Java JNI wrapper class ở parent**, thì method native được gọi qua **một runtime class duy nhất** và một native library được nạp ở parent. Đây là giải pháp kiến trúc quan trọng, giải thích ở phần sau.

## 4. Hai cách tải library: `System.load` và `System.loadLibrary`

| API | Đối số | Ví dụ | Điều cần lưu ý |
|---|---|---|---|
| `System.load(String absoluteFilename)` | **Đường dẫn tuyệt đối** tới native binary | `System.load("/opt/demo/libbridge.so")` | Không truyền đường dẫn tương đối |
| `System.loadLibrary(String libname)` | **Tên logic**, không có path, prefix hay extension | `System.loadLibrary("bridge")` | Dựa vào quy tắc tìm kiếm library của JVM/OS và `findLibrary` khi áp dụng |
| `System.mapLibraryName(String libname)` | Tên logic | `System.mapLibraryName("bridge")` | Trả tên file theo nền tảng, không tự tải thư viện |

Ví dụ tên được map:

~~~text
Linux:   bridge -> libbridge.so
macOS:   bridge -> libbridge.dylib
Windows: bridge -> bridge.dll
~~~

Đây là **tên điển hình**, còn naming conventions và hình thức binary có thể khác tùy nền tảng/implementation.

### `System.load`

~~~java
import java.nio.file.Path;

String absolute = Path.of("native", "libbridge.so")
        .toAbsolutePath().normalize().toString();

System.load(absolute);
~~~

Đây là **mảnh minh họa** cho Linux, yêu cầu file `libbridge.so` tồn tại và là native binary hợp lệ. Với macOS/Windows, file name khác. Thao tác này **không bỏ qua giới hạn một JNI library trên nhiều loaders**: đưa một absolute path hợp lệ cho cả hai child loaders vẫn có thể làm loader thứ hai thất bại.

### `System.loadLibrary`

~~~java
System.loadLibrary("bridge");
~~~

Không viết:

~~~java
System.loadLibrary("libbridge.so");   // Sai cách gọi API chuẩn
System.loadLibrary("/opt/native/libbridge.so");  // Sai: chứa path
~~~

Tùy hệ thống, JVM tra các vị trí thư viện native liên quan tới `java.library.path`, custom `ClassLoader.findLibrary` và hệ điều hành. Nếu library `bridge` không có ở nơi JVM tìm, sẽ phát sinh `UnsatisfiedLinkError` kiểu “no bridge in java.library.path”.

### `findLibrary` của custom loader

`ClassLoader` cung cấp hook:

~~~java
@Override
protected String findLibrary(String libname) {
    if ("bridge".equals(libname)) {
        return "/opt/my-plugin/native/libbridge.so";
    }
    return null;
}
~~~

Đây là **mảnh minh họa override trong subclass của ClassLoader**. Method phải trả một **absolute path** hợp lệ; trả `null` để dùng cơ chế tìm mặc định. Hook giúp loader tìm đúng binary, **không cho phép** nạp cùng JNI binary vào vô số loaders độc lập.

### Đừng coi `java.library.path` là “loader ownership”

`java.library.path` giải quyết **đường tìm native library**, không phải vấn đề cùng binary đã được đăng ký dưới loader khác. Đặt file đúng đường dẫn có thể sửa lỗi “no library in path” nhưng **không** sửa lỗi “already loaded in another classloader”.

Việc thay `System.setProperty("java.library.path", "...")` khi chương trình đã chạy **không có bảo đảm** thay được search path mà JVM đã chuẩn bị/ghi nhớ. Ưu tiên cấu hình ngay khi khởi chạy hoặc truyền absolute path qua `System.load` với cơ chế loader ownership rõ ràng.

## 5. Những nguyên nhân chính của UnsatisfiedLinkError

| Triệu chứng / thông báo điển hình | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `no bridge in java.library.path` | Native binary không thuộc đường tìm | Kiểm tra startup flags, `findLibrary`, absolute path |
| `already loaded in another classloader` | Native binary đã được loader khác sở hữu | Một shared JNI bridge ở parent; thay lifecycle/loader policy |
| `Can't load ...` hoặc “wrong ELF class” | Binary sai kiến trúc/bitness hay OS | Dùng binary đúng OS/CPU/ABI |
| `... cannot open shared object file ...` | Native binary hoặc **dependency native cấp dưới** không tìm thấy | Kiểm tra loader của hệ điều hành và transitive native dependencies |
| `undefined symbol` / `symbol not found` | Export/symbol ABI không khớp | Kiểm tra JNI header, C exports, linker, overload |
| Native method không liên kết | Chưa export tên JNI đúng, chưa load library, sai signature | Dùng `javac -h`, `JNIEXPORT`, `JNICALL`, `RegisterNatives` nếu thiết kế |
| `JNI_OnLoad` trả JNI version không hỗ trợ | Startup hook báo version không được VM hỗ trợ | Trả JNI version đúng theo JNI spec |
| Chỉ lỗi khi redeploy plugin | Loader cũ vẫn sống và giữ library | Dừng threads, bỏ references, xem class unloading/native unload |
| Chỉ lỗi trên máy CI/server | OS, CPU, permissions, runtime image, loader paths khác | Thu environment và native dependency report |
| Chỉ lỗi khi plugin A và B cùng bật | Hai plugin loaders riêng cùng `System.load` library | Kiểm tra defining loader của wrapper và native registry |

**Lưu ý:** dạng wording và nested causes phụ thuộc nền tảng/JDK. Các dòng trên là những mẫu chẩn đoán, **không phải thông báo byte-for-byte được bảo đảm**.

### Phân biệt lỗi thiếu native binary với lỗi không nạp được Java class

`ClassNotFoundException` phát sinh khi code tìm Java class theo tên không thành công.

`NoClassDefFoundError` thường phát sinh khi JVM cần Java class definition nhưng không tìm/link/initialize thành công theo tham chiếu bytecode; có thể có nguyên nhân khác nhau.

`UnsatisfiedLinkError` phát sinh ở **native linking/loading**, ví dụ native binary không tìm được hoặc native method chưa liên kết được. Một class `plugin.NativeBridge` có thể đã được Java classloader tìm thấy hoàn toàn hợp lệ, nhưng initializer `System.loadLibrary` vẫn ném `UnsatisfiedLinkError`.

## 6. Ví dụ Java 17 + JNI/C tái hiện lỗi ở loader thứ hai

Ví dụ này dùng **một thư viện native thật**, không giả lập lỗi bằng cách tự viết `throw new UnsatisfiedLinkError(...)`. Hai `URLClassLoader` khác nhau cùng định nghĩa Java wrapper `plugin.NativeBridge`. Wrapper chứa static initializer gọi `System.load(absolutePath)`.

Luồng thí nghiệm:

~~~text
                     Host: NativeLoaderLab
                               |
       +-----------------------+-----------------------+
       |                                               |
 URLClassLoader A                                URLClassLoader B
       |                                               |
 plugin.NativeBridge (A)                        plugin.NativeBridge (B)
       |                                               |
 System.load(native shared lib)                 System.load(CÙNG lib)
       |                                               |
       v                                               v
 First load succeeds                         UnsatisfiedLinkError
       |
 NativeBridge.answer() -> 42
~~~

**Yêu cầu:** JDK 17+, một C compiler/linker có thể tạo JNI shared library tương thích, và không có bản `plugin.NativeBridge` trên application classpath của host.

### 6.1. Cấu trúc thư mục

~~~text
project/
  src/
    plugin/
      plugin/
        NativeBridge.java
    host/
      NativeLoaderLab.java
    native/
      nativelab.c
  out/                       (sinh khi build)
    plugin/
    host/
  native/                    (header và .so/.dylib/.dll sinh khi build)
    plugin_NativeBridge.h
    libnativelab.so
~~~

Trên macOS, native output có thể là `libnativelab.dylib`; trên Windows là `nativelab.dll`. Không cố dùng Linux `.so` trên Windows.

### 6.2. File `src/plugin/plugin/NativeBridge.java`

~~~java
package plugin;

public final class NativeBridge {
    static {
        String absolutePath =
                System.getProperty("demo.native.path");

        if (absolutePath == null) {
            throw new IllegalStateException(
                    "Missing demo.native.path");
        }

        System.load(absolutePath);
    }

    private NativeBridge() {
    }

    public static native int answer();
}
~~~

- Mỗi loader tự định nghĩa `plugin.NativeBridge` vì class này **không ở application classpath**.
- Static initializer chạy **khi class được initialize**, không phải chỉ vì `Class.forName(name, false, loader)`.
- `System.load` nhận absolute path do host gán từ command-line argument.
- `answer()` là native method, không có Java method body; JVM liên kết nó với JNI function trong library.

### 6.3. File `src/native/nativelab.c`

~~~c
#include "plugin_NativeBridge.h"

JNIEXPORT jint JNICALL
Java_plugin_NativeBridge_answer(JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return 42;
}
~~~

Header `plugin_NativeBridge.h` do công cụ `javac -h` tự sinh từ Java declaration. Việc dùng header được sinh tránh đoán signature bằng tay; phần native implementation nhận `JNIEnv *` và `jclass` vì `answer()` là **static native method**.

Đây là JNI C implementation hoàn chỉnh cho method của ví dụ. Không cần gọi `RegisterNatives` vì symbol được export theo **quy tắc đặt tên JNI**.

### 6.4. File `src/host/NativeLoaderLab.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class NativeLoaderLab {
    private static final String BRIDGE = "plugin.NativeBridge";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: NativeLoaderLab <plugin-dir> <native-lib>");
        }

        URL pluginRoot = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();

        String nativePath = Path.of(args[1])
                .toAbsolutePath().normalize().toString();

        System.setProperty("demo.native.path", nativePath);

        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                    "plugin-A", new URL[]{pluginRoot}, parent);
             URLClassLoader loaderB = new URLClassLoader(
                    "plugin-B", new URL[]{pluginRoot}, parent)) {

            // Chỉ nạp, chưa chạy static initializer.
            Class<?> classA = Class.forName(BRIDGE, false, loaderA);
            Class<?> classB = Class.forName(BRIDGE, false, loaderB);

            System.out.println("same binary name: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("same runtime type: "
                    + (classA == classB));
            System.out.println("A owns class: "
                    + (classA.getClassLoader() == loaderA));
            System.out.println("B owns class: "
                    + (classB.getClassLoader() == loaderB));

            // Initializing class A calls System.load(nativePath).
            Class.forName(BRIDGE, true, loaderA);
            Object answer = classA.getMethod("answer").invoke(null);
            System.out.println("first native answer: " + answer);

            // Initializing class B tries to load SAME JNI library
            // but the library already belongs to loader A.
            try {
                Class.forName(BRIDGE, true, loaderB);
                System.out.println("second native load: success");
            } catch (UnsatisfiedLinkError error) {
                System.out.println(
                        "second native load: UnsatisfiedLinkError");
            }
        }
    }
}
~~~

**Giải thích từng kỹ thuật:**

1. Parent là **platform class loader** để hai plugin loaders không vô tình nhận `plugin.NativeBridge` từ application classpath. Trong production, parent thường cần chứa shared API; demo không cần API riêng.
2. `Class.forName(BRIDGE, false, loader)` trả runtime `Class<?>` mà **chưa chạy static initializer**; cho phép quan sát cùng tên nhưng khác defining loader.
3. `Class.forName(BRIDGE, true, loaderA)` chạy initializer của class A, gọi `System.load`; native lib được nạp dưới loader A.
4. Invocation `answer()` qua reflection gọi JNI function và trả số nguyên 42.
5. `Class.forName(BRIDGE, true, loaderB)` chạy initializer **khác** của class B, cố tải cùng library; JVM phát hiện library thuộc loader A và ném `UnsatisfiedLinkError`.
6. Chương trình chỉ in **loại lỗi**, không phụ thuộc text của `error.getMessage()` hoặc đường dẫn thật trên máy.
7. `URLClassLoader.close()` đóng các tài nguyên loader Java như JAR/file handle; **không tự bảo đảm native library được unload ngay**.

### 6.5. Build trên Linux (Bash + GCC)

Chạy từ thư mục `project`. Trước hết cần có **JDK** và `gcc`; `JAVA_HOME` phải trỏ đến JDK đang dùng:

~~~bash
mkdir -p out/plugin out/host native

javac -h native -d out/plugin \
    src/plugin/plugin/NativeBridge.java

javac -d out/host src/host/NativeLoaderLab.java

gcc -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -Inative \
    -o native/libnativelab.so \
    src/native/nativelab.c

java -cp out/host NativeLoaderLab \
    out/plugin native/libnativelab.so
~~~

Nếu `JAVA_HOME` chưa được đặt, xác định nó từ thư mục JDK cài đặt, ví dụ trên nhiều hệ Linux:

~~~bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
~~~

Lệnh này **phụ thuộc layout JDK của hệ thống**; trên hệ khác, đặt `JAVA_HOME` thủ công. Để kiểm tra: file `"$JAVA_HOME/include/jni.h"` và `"$JAVA_HOME/include/linux/jni_md.h"` phải tồn tại.

**Quan trọng:** `-cp out/host` chỉ chứa host class. **Không thêm `out/plugin` vào application classpath**, nếu không parent/caller có thể thấy Java wrapper trước và thí nghiệm hai defining loaders không còn đúng.

### 6.6. Build trên macOS (Bash + Clang)

Sau hai lệnh `javac` ở trên, thay lệnh GCC Linux bằng:

~~~bash
clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -Inative \
    -o native/libnativelab.dylib \
    src/native/nativelab.c

java -cp out/host NativeLoaderLab \
    out/plugin native/libnativelab.dylib
~~~

Có thể dùng `/usr/libexec/java_home` để xác định `JAVA_HOME` khi JDK được cài đặt theo bố cục macOS chuẩn. Với máy Apple Silicon, phải build native binary đúng kiến trúc của process Java đang chạy.

### 6.7. Build trên Windows

Dùng **Visual Studio Developer Command Prompt** có MSVC C compiler `cl` và đã đặt `JAVA_HOME` tới JDK:

~~~bat
mkdir out\plugin
mkdir out\host
mkdir native

javac -h native -d out\plugin src\plugin\plugin\NativeBridge.java
javac -d out\host src\host\NativeLoaderLab.java

cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" /I "native" src\native\nativelab.c /Fe:native\nativelab.dll

java -cp out\host NativeLoaderLab out\plugin native\nativelab.dll
~~~

Các lệnh là **Command Prompt**, không phải PowerShell; điều kiện là `cl`/linker/SDK đã được cấu hình, file native đầu ra được tạo thành công và kiến trúc DLL khớp JVM. Trên Windows, thư viện phụ thuộc có thể cần nằm trong đường tìm DLL của hệ điều hành.

### 6.8. Stdout mong đợi

Với chương trình mới chạy trong JVM sạch, đúng library và không có class `plugin.NativeBridge` trên parent classpath:

~~~text
same binary name: true
same runtime type: false
A owns class: true
B owns class: true
first native answer: 42
second native load: UnsatisfiedLinkError
~~~

**Đây là output dự kiến theo đặc tả JNI**; compiler C/linker hoặc launcher lỗi sẽ khiến chương trình không đến bước này. Chuỗi chi tiết của `UnsatisfiedLinkError` có thể khác giữa các JDK/OS; demo tránh in nó.

Lỗi này không phải do function `answer()` bị thiếu: lời gọi của class A trả 42, chứng minh thư viện native và symbol JNI hoạt động. Lỗi thứ hai xảy ra khi **đăng ký cùng library dưới defining loader khác**.

### 6.9. Có nên catch `UnsatisfiedLinkError` và tiếp tục như demo?

Trong demo, catch chỉ để **phân loại kết quả có chủ đích**. Trong production, không nên catch rồi giả vờ đã khởi tạo plugin thành công: **initialization của class B đã thất bại**, có thể làm class ấy ở trạng thái erroneous. Lần sử dụng tiếp theo có thể ném `NoClassDefFoundError: Could not initialize class ...`.

Nếu load native thất bại, hãy **dừng kích hoạt plugin generation đó**, ghi đầy đủ lỗi/cause và sửa loader architecture hoặc native packaging trước khi thử lại bằng generation mới. Không mù quáng loop `System.load` hoặc instantiate lại class đã failed initialization.

## 7. Giải pháp ưu tiên: một JNI bridge do parent loader sở hữu

Nếu nhiều plugin trong cùng JVM dùng **một native implementation có trạng thái chia sẻ**, thường nên tải JNI wrapper và native library **một lần trong loader cha dùng chung**:

~~~text
                 Application loader (parent)
                   |
            api.NativeBridge
            static { System.loadLibrary("bridge"); }
            public static native int answer();
                   |
            libbridge.so / bridge.dll
                   |
       +-----------+-----------+
       |                       |
 PluginLoader A            PluginLoader B
  plugin.ImplA              plugin.ImplB
       |                       |
       +---------call----------+
                 |
           api.NativeBridge
        (cùng một Class object)
~~~

Hai plugin delegate việc tìm `api.NativeBridge` về parent; parent định nghĩa đúng **một runtime class** chứa native method declaration. Khi gọi native bridge, chúng không cố gắng `System.loadLibrary` cùng JNI binary từ hai defining loaders riêng.

### 7.1. Shared API và implementation riêng

Để thiết kế rõ hơn, nên chia:

~~~text
shared-api.jar (application classpath)
  api.NativeCodec                    <- public interface

shared-native-bridge.jar (parent)
  bridge.JniNativeCodec              <- class gọi System.loadLibrary

plugin-a.jar (child A)
  plugin.a.ServiceA                   <- dùng api.NativeCodec

plugin-b.jar (child B)
  plugin.b.ServiceB                   <- dùng api.NativeCodec
~~~

Parent sở hữu cả **JNI wrapper có method native** và native binary; shared interface cũng thuộc parent. Khi plugin cần native function, nó gọi qua public API của parent hoặc một service object parent cung cấp.

Điều này có lợi:

- Không nạp lại cùng native library qua mỗi plugin classloader.
- Hạn chế duplicate Java wrapper classes liên quan JNI.
- Đặt điểm khởi tạo/shutdown native state vào một thành phần có lifecycle rõ.
- Dễ chẩn đoán và kiểm soát version chung của JNI ABI.

**Đánh đổi:** plugin không thể đồng thời sử dụng các native library versions có ABI không tương thích bằng cách giả vờ chúng là hai class phiên bản riêng. Nếu cần version isolation thực sự, có thể cần **process isolation** hoặc binary native hoàn toàn độc lập với tên/path và state được kiểm soát. Không có bảo đảm rằng copy cùng `.so`/.dll đổi tên thành hai file là đủ an toàn.

### 7.2. Vì sao “chỉ đặt shared interface ở parent” chưa đủ?

Giả sử parent có `api.NativeCodec` nhưng từng plugin child vẫn tự định nghĩa `plugin.NativeBridge` với static initializer gọi `System.loadLibrary("bridge")`.

Dù cả hai plugin có thể cast về `api.NativeCodec`, native bridge classes vẫn do **hai defining loaders riêng** sở hữu; chúng vẫn có thể tranh chấp cùng JNI library.

Đúng hơn là đặt **class thật sự gọi `System.load/System.loadLibrary` và khai báo native methods** trong parent hoặc một loader chung đủ ổn định, rồi expose method/service tới plugin.

### 7.3. Khi nào không nên tải native library lên parent?

Không phải mọi native library có thể chia sẻ:

- Hai plugins yêu cầu **ABI hoặc version native thực sự khác nhau**.
- Native code giữ **process-global state**, không hỗ trợ multi-tenancy, có singleton/worker threads hoặc callbacks vào classes của plugin.
- API wrapper ở parent không thể cấu hình state riêng per plugin.
- Plugin không tin cậy hoặc cần quyền hệ điều hành khác nhau.
- Native library có lifecycle gắn với một plugin và không được dùng bởi phần còn lại.

Trong các trường hợp này, phải thiết kế boundary cụ thể, có thể dùng process riêng. Một classloader khác **không tương đương một tiến trình native riêng**.

## 8. Tại sao “copy library thành nhiều file” không phải giải pháp mặc định?

Một số ứng dụng trích xuất cùng một native binary vào nhiều thư mục temp với tên khác nhau để mỗi plugin gọi `System.load` lên path khác.

Cách này **có thể thay đổi identity đường dẫn ở một số implementation**, nhưng không phải giải pháp portable/được JNI đảm bảo cho cô lập native state, vì:

- OS dynamic loader có thể có chính sách canonicalization/deduplication image khác.
- Native dependencies nội bộ có thể vẫn là **cùng những shared libraries** với global/static state.
- Native code có thể tự dùng process-global singleton, lock, network ports, temp files hoặc C runtime state.
- Native code có thể lưu `JNIEnv*` hoặc `jclass` sai vòng đời, tạo crash/undefined behavior.
- Hai binary giống nhau vẫn có thể export JNI symbols trùng hoặc trỏ tới cùng downstream native runtime.
- Windows thường khó xóa/ghi đè một DLL đang được process giữ.
- Packaging nhiều copies gây rác temp files, library handle leak và khó security audit.

Nếu một thư viện có tài liệu chính thức xác nhận hỗ trợ **multi-classloader JNI instances**, hãy làm theo cơ chế cụ thể của vendor. Nếu không, **shared parent bridge** hoặc **separate process** là hai lựa chọn dễ chứng minh đúng hơn.

## 9. `JNI_OnLoad`, `JNI_OnUnload` và cơ hội unload library

JNI có những lifecycle callbacks tùy chọn:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL
JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    // Chỉ cleanup những tài nguyên có thể cleanup an toàn.
}
~~~

Đây là **mảnh C minh họa về hooks**, **không** cần ghép vào file `nativelab.c` của demo để chạy; nếu thêm hooks, bảo đảm không định nghĩa trùng những symbols này trong cùng library.

- `JNI_OnLoad` được VM gọi khi native library động được load nếu library có export hook. Hook trả JNI version mà library cần.
- `JNI_OnUnload` có thể được gọi khi class loader chứa library được GC thu gom. **Không có lệnh Java phổ thông bảo đảm gọi hook ngay tại thời điểm mong muốn**.
- Đặc tả khuyến cáo `JNI_OnUnload` dùng Java VM services **thận trọng** vì callback có thể chạy trong ngữ cảnh không lường trước. Tránh callback tùy ý sang Java trong hook cleanup.
- Đừng giữ `JNIEnv*` xuyên threads: `JNIEnv` gắn với thread. Với native threads cần cơ chế attach/detach JVM đúng API.
- Không giữ Java object/class references lâu dài mà không có quản lý local/global/weak global references đúng JNI contract.

### `URLClassLoader.close()` có unload JNI library ngay không?

**Không có bảo đảm như vậy.** `URLClassLoader.close()` đóng những file/JAR handles mà URLClassLoader đã mở. Nó **không phải** một API `dlclose`/`FreeLibrary` tùy ý cho JNI library.

Một native library liên kết với loader có thể có cơ hội unload khi loader thật sự không còn reachable và được GC thu gom, nhưng:

1. Thread đang chạy, callback, TCCL, static caches hoặc application registry có thể giữ loader/class/plugin objects sống.
2. JVM không cam kết GC/unloading xảy ra ngay sau `System.gc()` hay `close()`.
3. Native library có thể giữ resources, threads và global references cần cleanup chuyên biệt.
4. Chính sách unload và native dependency behavior cũng phụ thuộc JVM/OS.

**Không dùng `System.gc()` như lời hứa rằng có thể reload library vào loader khác ngay lập tức.** Hãy quản lý vòng đời chủ động, và thiết kế shared native bridge nếu cần tái triển khai Java plugins thường xuyên.

## 10. `RegisterNatives`, JNI symbol và native method linkage

`UnsatisfiedLinkError` không chỉ xảy ra khi load library. Sau khi thư viện được nạp, lúc Java code gọi một `native` method, JVM vẫn phải tìm implementation tương ứng.

### 10.1. JNI naming

Với Java declaration:

~~~java
package plugin;

public final class NativeBridge {
    public static native int answer();
}
~~~

JNI C symbol thông thường (không overload trong ví dụ) là:

~~~c
JNIEXPORT jint JNICALL
Java_plugin_NativeBridge_answer(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return 42;
}
~~~

Dùng `javac -h native ...` để sinh header chính xác. Nếu native method có **overloads**, tên symbol có thể bao gồm thông tin signature được mangle theo quy tắc JNI; không nên tự đoán.

Với C++, cần tuân thủ xuất symbols đúng linkage (header JNI được JDK sinh thường xử lý `extern "C"` theo macro/cấu trúc phù hợp). Với C#/.NET native shim hoặc Rust, cần export ABI/symbol đúng contract của JNI và toolchain tương ứng.

### 10.2. `RegisterNatives`

Một native library có thể đăng ký con trỏ function bằng `RegisterNatives`. Cách này có thể hữu ích với generated/proxy JNI integrations nhưng cũng đòi hỏi:

- Sử dụng đúng `jclass` của **runtime class cần đăng ký**.
- Method names/signatures khớp khai báo Java.
- Không nhầm two classes cùng binary name nhưng thuộc different defining loaders.
- Quản lý JNI references và thread-safe native state.

**Không** dùng `RegisterNatives` như một mẹo để bỏ qua quy tắc “same JNI library cannot be loaded into more than one classloader”. Việc library ownership theo JNI vẫn phải được tôn trọng.

### 10.3. Phân biệt hai loại thất bại bằng thời điểm

~~~text
Java class initialization
       |
       +--> System.loadLibrary("bridge")
       |         |
       |         +--> no library / dependency failure
       |         +--> already loaded in another loader
       |         +--> bad architecture / JNI_OnLoad failure
       |
       v
native method invocation
       |
       +--> JNI symbol / RegisterNatives lookup
                 |
                 +--> symbol missing or incompatible signature
~~~

Thông báo `UnsatisfiedLinkError` của các nhánh có thể tương tự nhau, nên log **thao tác nào đã fail** cùng stack trace, defining loader và lib path.

## 11. JNI class loader lookup và callbacks từ native code

Native code đôi khi gọi JNI `FindClass` để tìm Java types. Quy tắc chọn class loader trong JNI có thể khác nhau tùy **call context**, ví dụ đang chạy trong một native method Java hay từ một native-attached thread không có Java frame phù hợp.

Vấn đề phổ biến:

- Cùng `plugin.Dto` có thể được mỗi plugin loader định nghĩa riêng.
- Native code cache sai một `jclass` rồi dùng cho plugin khác.
- Thread native tự attach vào JVM có thể không nhìn thấy class của plugin nếu tìm tên bằng loader không đúng.
- Thread context class loader của Java **không tự sửa mọi trường hợp JNI `FindClass` trên native thread**.

**Thiết kế khuyến nghị:**

1. Để Java side truyền `Class<?>`/`ClassLoader`/object đã được kiểm tra phù hợp vào native bridge khi cần; native code nhận đối tượng JNI hợp lệ.
2. Nếu native code cần giữ class/object lâu hơn một call, tạo global/weak global reference đúng API rồi cleanup.
3. Không lưu `JNIEnv*` trong biến global rồi dùng từ thread khác.
4. Tránh callback xuyên những plugin generations đã retire.
5. Nếu sử dụng `RegisterNatives`, đăng ký với đúng runtime class, không chỉ dựa vào chuỗi tên.
6. Bảo đảm API/DTO mà native bridge trao đổi với nhiều plugins được **định nghĩa ở parent loader** hoặc chuyển thành dữ liệu trung lập.

Những nguyên tắc này giúp ngăn lỗi JNI khó quan sát, nhưng **không làm một JNI library trở thành có thể tải lại vào nhiều defining loaders**.

## 12. Native library có phụ thuộc hệ điều hành và CPU architecture

Classloader có thể tìm được Java wrapper, nhưng native binary vẫn cần tương thích với **tiến trình JVM đang chạy**:

| Yếu tố | Ví dụ |
|---|---|
| OS | Linux `.so`, macOS `.dylib`, Windows `.dll` |
| CPU instruction set | x86_64, arm64/AArch64 |
| Process bitness | JVM 64-bit cần native binary 64-bit tương thích |
| Calling convention/ABI | JNI macros và compiler toolchain phù hợp |
| C/C++ runtime dependencies | glibc/libstdc++/MSVC runtime phù hợp |
| Transitive native libraries | `libcrypto.so`, runtime DLL, framework native khác |
| Library search path của OS | `LD_LIBRARY_PATH`, rpath, loader configuration, Windows DLL search |
| Security restrictions | File permissions, executable mapping, system policy, hardened runtime/codesigning khi có |

Một file thực sự tồn tại nhưng thiếu **transitive dependency** vẫn có thể làm `System.load` thất bại. Vì vậy “file exists = true” không chứng minh loader có thể map binary vào process.

### Công cụ điều tra theo hệ điều hành

**Linux:**

~~~bash
file native/libnativelab.so
ldd native/libnativelab.so
nm -D native/libnativelab.so
~~~

**macOS:**

~~~bash
file native/libnativelab.dylib
otool -L native/libnativelab.dylib
nm -gU native/libnativelab.dylib
~~~

**Windows:**

~~~text
dumpbin /DEPENDENTS native\nativelab.dll
dumpbin /EXPORTS native\nativelab.dll
~~~

Các lệnh trên là **lệnh chẩn đoán**, không phải output được bảo đảm trên mọi máy; tùy toolchain có thể cần bổ sung flags. `ldd` đối với binary không tin cậy có nguy cơ trên một số môi trường; không dùng tùy tiện cho artifact chưa được kiểm tra nguồn gốc.

### Kiểm tra Java process và library path

~~~java
System.out.println("java.version="
        + System.getProperty("java.version"));
System.out.println("os.name="
        + System.getProperty("os.name"));
System.out.println("os.arch="
        + System.getProperty("os.arch"));
System.out.println("java.library.path="
        + System.getProperty("java.library.path"));
System.out.println("mapped="
        + System.mapLibraryName("nativelab"));
~~~

Đây là **mảnh minh họa**. Các property hữu ích để debug, nhưng không thay thế phân tích native dependencies và defining loader.

## 13. Vòng đời plugin và tình huống redeploy

Giả sử application server tạo:

~~~text
Generation 1:
  PluginLoader-A
      |
      +-- NativeBridge loads libnativecodec.so
      |
      +-- Plugin A active

Redeploy:
  PluginLoader-A should retire
  PluginLoader-B created
      |
      +-- NativeBridge attempts same libnativecodec.so
      |
      +-- UnsatisfiedLinkError
~~~

Vì JVM chưa thể unload library thuộc loader A (loader A còn reachable), loader B không thể nhận cùng JNI native library như thể chưa từng được dùng.

**Nhiều reference gián tiếp khiến loader A còn sống:**

- Threads được plugin tạo ra chưa dừng.
- `ThreadLocal` hoặc thread context class loader của thread pool trỏ đến class/loader cũ.
- Host cache `Class<?>`, object plugin, `Method`, `MethodHandle` hoặc provider instance.
- Listener, registry, scheduled task, event subscription, MBean hoặc classpath framework cache chưa gỡ.
- Native code giữ global references hoặc callbacks vào plugin Java objects.

### Lifecycle đề xuất

~~~text
ACTIVE
  |
  | Không nhận công việc mới
  v
DRAINING
  |
  | Hoàn tất in-flight calls
  | Dừng plugin threads/background executors
  | Hủy callbacks/listeners, reset TCCL
  | Đóng streams/URLClassLoader
  | Bỏ strong references ở caches/registries
  v
RETIRED
  |
  | GC/unloading theo điều kiện của JVM
  v
MAY BE UNLOADED  (không cam kết thời điểm)
~~~

Nếu plugin cần redeploy thường xuyên, **đặt JNI bridge ở parent** và quản lý native state riêng per plugin ở tầng Java/native API nếu thư viện hỗ trợ. Không dựa vào việc loader cũ có thể được GC ngay đúng một thời điểm xác định.

### Khi native state không hỗ trợ multi-tenancy

Nếu native code chỉ có một process-global singleton hoặc không hỗ trợ nhiều versions/instances, API chung ở parent **vẫn chưa giải quyết mọi yêu cầu**. Cần:

- Một native process chung quản lý state theo contract rõ ràng, hoặc
- Mỗi plugin chạy trong một process/container riêng, hoặc
- Thiết kế lại JNI library để hỗ trợ nhiều *handles/contexts* độc lập khi vendor cho phép.

## 14. Quy trình chẩn đoán UnsatisfiedLinkError thực tế

### Bước 1 — Xác định lỗi xảy ra ở thao tác nào

Xem stack trace/cause chain:

- `System.loadLibrary`: lookup theo tên logic hoặc conflict ownership.
- `System.load`: absolute path/mapping hoặc conflict ownership.
- Lời gọi một method `native`: JNI symbol/method registration.
- Static initializer: có thể khiến cả class initialization thất bại.
- Plugin restart: cân nhắc classloader leak/native lifecycle.

### Bước 2 — Log classloader của Java wrapper

~~~java
Class<?> wrapper = plugin.NativeBridge.class;
ClassLoader owner = wrapper.getClassLoader();

System.out.println(wrapper.getName());
System.out.println(owner);
System.out.println(wrapper.getModule());
~~~

Đây là **mảnh minh họa** trong môi trường có thể tham chiếu `plugin.NativeBridge`; host không có wrapper ở compile classpath như demo nên phải dùng `Class<?>` lấy từ explicit loader.

Nếu đang debug từ host:

~~~java
Class<?> type = pluginLoader.loadClass("plugin.NativeBridge");

System.out.println(type.getClassLoader() == pluginLoader);
System.out.println(type.getModule());
~~~

**Đừng chỉ in tên loader**: hai instance khác nhau có thể đặt cùng tên. So sánh reference bằng `==` khi có thể và gắn logical generation IDs để log.

### Bước 3 — Kiểm tra native file và dependencies

- Xác minh **đường dẫn tuyệt đối thực** khi gọi `System.load`.
- Nếu gọi `System.loadLibrary`, kiểm tra tên **không chứa prefix/path/extension**.
- Dùng công cụ OS để kiểm tra architecture, dependencies và exports.
- Kiểm tra JDK/JVM process thực sự đang chạy, chứ không chỉ `JAVA_HOME` lúc build.
- Nếu chương trình chạy trong container, xác minh library có trong container image và đúng libc/ABI.
- Nếu nghi duplicate load, log Java wrapper class, owner loader và plugin generation ngay tại static initializer.

### Bước 4 — Xác nhận ownership conflict

Nếu **loader A đã nạp thành công cùng JNI binary** và loader B mới xuất hiện, đây là dấu hiệu rất mạnh của nguyên nhân “already loaded in another classloader”.

Đặc biệt, nếu tái khởi động **toàn bộ JVM** khiến lỗi biến mất nhưng hot redeploy một plugin gây lỗi, hãy ưu tiên điều tra **native library ownership + old classloader references**. Restart JVM là workaround vận hành, không phải giải pháp vòng đời bền vững.

### Bước 5 — Chọn fix theo bảng

| Kết quả chẩn đoán | Hướng sửa phù hợp |
|---|---|
| Không tìm thấy native binary | Sửa path/packaging và startup configuration |
| Native dependency thiếu | Đóng gói/cài các dependency native, sửa OS loader path |
| Sai CPU/OS/bitness | Build lại đúng target platform |
| JNI symbol sai hoặc export thiếu | `javac -h`, kiểm tra `JNIEXPORT`/`JNICALL`/symbol mangling |
| Duplicate load qua 2 plugin loaders | Shared JNI bridge ở parent hoặc kiến trúc native isolation rõ |
| Reload không unload được | Dọn old-loader references; tránh coi GC là deterministic |
| Native library ABI không chia sẻ được | Separate processes hoặc handle-based multi-instance nếu library hỗ trợ |
| Plugin chưa tin cậy | Isolate ở process/OS boundary, không chỉ classloader |

### Bước 6 — Thử trong môi trường sạch

Một test tái hiện nên:

1. Dùng **JVM mới**.
2. Log một classloader owner/generation ID mỗi lần nạp native binary.
3. Tải một wrapper Java từ loader A, gọi native method thành công.
4. Tạo loader B và cố tải cùng binary; phân loại `UnsatisfiedLinkError`.
5. Test phương án parent-owned bridge: cả hai plugin gọi cùng một wrapper runtime type.
6. Test redeploy/shutdown mà không dựa vào `System.gc()` như cam kết unload.

## 15. Liên hệ với ClassNotFoundException và NoClassDefFoundError

Trong plugin lifecycle, các lỗi có thể xuất hiện liên tiếp nhưng không đồng nhất:

~~~text
Host/Plugin ClassLoader
    |
    +-- loadClass("plugin.NativeBridge")
           |
           +-- Không thấy class Java -> ClassNotFoundException
           |
           +-- Thấy class Java -> Class<?> được tạo
                    |
                    +-- initialize class
                           |
                           +-- System.load(...)
                                  |
                                  +-- Native binary missing
                                  |     -> UnsatisfiedLinkError
                                  |
                                  +-- Already loaded by other loader
                                  |     -> UnsatisfiedLinkError
                                  |
                                  +-- JNI library loaded
                                          |
                                          +-- native method called
                                                 |
                                                 +-- JNI symbol missing
                                                       -> UnsatisfiedLinkError
~~~

Nếu `System.load` ném `UnsatisfiedLinkError` trong static initializer, đây là `Error` nên **có thể được ném trực tiếp**; không nhất thiết bị bọc thành `ExceptionInInitializerError` như trường hợp initializer ném một non-Error exception.

Khi initialization của class đã fail, JVM đánh dấu class ở trạng thái lỗi theo quy tắc initialization; lời gọi sau trên class đó có thể nhận `NoClassDefFoundError` kiểu “Could not initialize class ...”. Vì vậy **đừng thử nạp lại vô hạn trên cùng class** sau khi static initialization thất bại.

Các bước debug phải lưu **lỗi đầu tiên** chứ không chỉ lỗi của lần retry sau.

## 16. JNI trong bối cảnh JPMS và Java mới

JNI native loading và JPMS modularity là **hai chiều kiểm soát khác nhau**:

- `requires`, `exports`, `opens`, module layers điều khiển việc đọc/access theo Java modules.
- `System.loadLibrary` và native method resolution liên quan native-library ownership và ABI.
- Thêm `--add-opens` không làm thư viện native có thể được nạp một lúc vào hai class loaders.
- Tạo `ModuleLayer` mới không đảm bảo native library đã load ở layer/loader khác được load lại độc lập.
- Với các JDK mới có cơ chế **restricted native access**, cần tuân thủ chính sách native access flags tương ứng (ví dụ `--enable-native-access` khi môi trường yêu cầu). Demo định hướng **JDK 17**, không giả định mọi phiên bản mới đều giữ chính sách cảnh báo/từ chối y hệt.
- Foreign Function & Memory API (FFM) hoặc các thư viện bridging khác có thể thay đổi cách gọi mã native, nhưng **không mặc định biến native global state thành độc lập giữa các plugins**. Không dùng FFM như “fix tự động” cho lifecycle/ABI của mọi JNI library.

Cần phân biệt **classloader namespace separation**, **JPMS module access** và **process/OS isolation**; ba khái niệm phục vụ những nhu cầu khác nhau.

## 17. An toàn khi dùng native code và lỗi phổ biến

JNI code thực thi trong quyền của tiến trình Java, có thể truy cập bộ nhớ và tạo native threads. **ClassLoader không cách ly native memory hay quyền hệ điều hành**; nếu plugin không đáng tin cậy, cần process boundary cùng giới hạn tài nguyên và IPC phù hợp.

Năm ngộ nhận quan trọng cần tránh:

1. **“Thêm `java.library.path` chữa mọi `UnsatisfiedLinkError`.”** Đường tìm file không giải quyết JNI symbol/ABI, native dependency, CPU architecture hay *already loaded in another classloader*.
2. **“Một native library đã load cho plugin A thì plugin B tự dùng được.”** JNI sở hữu thư viện theo loader; nếu hai child tự gọi `System.load`, library có thể xung đột.
3. **“`URLClassLoader.close()` hoặc `System.gc()` chắc chắn unload ngay.”** Class/native unloading phụ thuộc reachability, lifecycle và lựa chọn JVM, không có thời điểm được bảo đảm.
4. **“Chỉ đưa shared interface vào parent là đủ.”** Nếu **JNI wrapper thật sự gọi `System.load`** vẫn nằm ở từng child, hai lần native load vẫn xảy ra. Parent cần sở hữu native bridge hoặc thiết kế state riêng rõ ràng.
5. **“Native code có thể giữ `JNIEnv*` dùng xuyên mọi thread hoặc `jclass` local reference vĩnh viễn.”** `JNIEnv*` gắn với thread; JNI object/class references có vòng đời cụ thể và cần global/weak-global quản lý đúng.

Các API như `RegisterNatives`, `--add-opens` hay việc sao chép file `.so` vào nhiều thư mục đều **không mặc nhiên** vượt quy tắc JNI library ownership. Khi xử lý lỗi runtime, giữ nguyên stack trace đầu tiên và phân loại xem thất bại ở bước **load native binary**, **symbol resolution** hay **Java class initialization**.

## 18. Checklist thực tế cho hệ plugin dùng JNI

- [ ] Xác định rõ **Java class khai báo native methods** và defining loader của class đó.
- [ ] Xác định **Java class trực tiếp gọi `System.load`/`loadLibrary`**, không suy đoán chỉ theo plugin ID.
- [ ] Chọn shared JNI wrapper ở parent nếu nhiều plugins dùng chung cùng native library.
- [ ] Giữ public API/DTO chung tại loader phù hợp để không duplicate runtime types.
- [ ] Không vô tình đóng gói thêm bản JNI wrapper ở từng plugin child với child-first policy.
- [ ] `System.loadLibrary` dùng **logical name**; `System.load` dùng **absolute path**.
- [ ] Đúng native binaries cho OS/CPU/bitness của JVM target.
- [ ] Kiểm tra đầy đủ **transitive native dependencies** và các JNI symbols.
- [ ] Header được sinh bằng `javac -h` hoặc signature được verify bằng toolchain tương ứng.
- [ ] Không cố load JNI library đã thuộc loader A vào loader B.
- [ ] Thiết kế native state có thể dùng chung hay cần contexts per plugin.
- [ ] Có policy restart/redeploy, không dựa vào GC timing.
- [ ] Dừng plugin threads/callbacks và bỏ TCCL/caches trước khi retire loader cũ.
- [ ] Có log classloader/generation, native absolute path, JNI ABI và full root cause.
- [ ] Kiểm thử startup sạch, hai plugins cùng lúc, hot redeploy và failure của `JNI_OnLoad`.
- [ ] Kiểm thử broken native symbol, missing native dependency và sai platform binary.
- [ ] Không chạy native code chưa tin cậy trong cùng JVM mà tưởng ClassLoader bảo vệ.
- [ ] Nếu dùng JPMS/newer JDK, kiểm tra riêng restricted native access policy.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Hai `URLClassLoader` khác nhau cùng định nghĩa `plugin.NativeBridge` và cả hai chạy `System.load("/same/path/libx.so")`. Vì sao loader thứ hai có thể ném `UnsatisfiedLinkError`?

**Đáp án:** Vì cùng một JNI native library đã được gắn với loader thứ nhất. Đặc tả JNI không cho nạp cùng thư viện vào hai classloaders.

**Câu 2.** `System.loadLibrary("libx.so")` có đúng cách dùng không?

**Đáp án:** Không theo contract chuẩn: `loadLibrary` nhận tên logic không prefix/extension/path. Nếu logical name là `x`, gọi `System.loadLibrary("x")`. Với path tuyệt đối, dùng `System.load(...)`.

**Câu 3.** Native binary tồn tại đúng path, nhưng vẫn `UnsatisfiedLinkError`. Có những nguyên nhân nào khác?

**Đáp án:** Sai OS/CPU/bitness, thiếu transitive native library, sai symbols/ABI, phiên bản JNI không hỗ trợ hoặc duplicate ownership giữa loaders.

**Câu 4.** Cho shared API ở parent nhưng mỗi plugin tự định nghĩa JNI wrapper riêng. Đã giải quyết duplicate load chưa?

**Đáp án:** Chưa. Cần đặt **JNI wrapper native owner** ở một shared loader phù hợp hoặc thiết kế native state/lifecycle khác.

**Câu 5.** `URLClassLoader.close()` có đảm bảo gọi `JNI_OnUnload` ngay không?

**Đáp án:** Không. JNI_OnUnload có thể được gọi khi loader chứa library được GC thu gom; thời điểm không được Java app điều khiển chính xác bằng close.

**Câu 6.** Có thể đưa cùng file native sang nhiều thư mục rồi xem như có hai phiên bản native độc lập không?

**Đáp án:** Không có bảo đảm portable. OS loader, dependencies, singleton native state và JNI ownership vẫn có thể gây xung đột hoặc lỗi vòng đời.

**Câu 7.** Khi `UnsatisfiedLinkError` phát sinh trong static initializer, vì sao lần gọi sau có thể trở thành `NoClassDefFoundError`?

**Đáp án:** Vì initialization của runtime class đã thất bại, JVM có thể đánh dấu class lỗi; lần active use sau không tự chạy lại initializer như class mới.

**Câu 8.** Trong demo, vì sao `classA == classB` là `false` dù tên nhị phân đều `plugin.NativeBridge`?

**Đáp án:** Vì A và B là hai defining loaders khác nhau, nên hai runtime types khác nhau.

**Câu 9.** Lỗi “native method not found” có bắt buộc là “already loaded in another classloader” không?

**Đáp án:** Không. Native library có thể được load thành công nhưng export sai JNI symbol, signature hoặc registration. Cần xem giai đoạn lỗi.

**Câu 10.** Khi native library không hỗ trợ multi-instance và mỗi plugin cần version khác nhau, đâu là boundary mạnh hơn classloader?

**Đáp án:** Separate process/container với IPC contract rõ ràng. Classloader không tạo native process-global namespace độc lập.

## 20. Quy trình quyết định

~~~text
             UnsatisfiedLinkError
                     |
                     v
       Xảy ra khi System.load* hay
           khi gọi native method?
                /          \
          System.load*     native invocation
                |               |
                v               v
       Library found?       JNI export/signature/
           /    \            RegisterNatives?
         Không   Có
          |       |
     Sửa path,   v
     OS deps    Already loaded elsewhere?
                /                  \
              Có                    Không
               |                      |
        Kiểm tra owner loader      Kiểm tra ABI,
               |                  dependency, arch
               v
     Nhiều plugin cùng dùng lib?
           /            \
         Có              Không
          |                |
   Shared JNI wrapper    Dọn lifecycle/
      ở parent          xem native state
          |
          v
       Test hai loaders / redeploy
          |
          v
     Không dựa vào GC hoặc
     copy file như giải pháp mặc định
~~~

**Kết luận:** `UnsatisfiedLinkError` trong nhiều classloaders không chỉ là “không tìm thấy thư viện”. Một native binary có thể tồn tại, có JNI symbol đúng và đã chạy thành công với plugin A, nhưng vẫn không được nạp lại vào plugin B vì quy tắc **native-library ownership theo class loader**. Cách giải quyết thường bền vững là **một parent-owned JNI bridge**, hợp đồng dùng chung rõ ràng, hoặc **cách ly process** khi native state/ABI không thể chia sẻ. Kết hợp việc xác định defining loader, native path, OS dependencies và lifecycle sẽ giúp phân biệt đúng nguyên nhân thay vì sửa classpath mù quáng.

### Tài liệu tham khảo chính thức

- [Java 17 JNI Specification — Invocation API / Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java 17 JNI Specification — Design Overview / Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Java SE 17 — System.load, System.loadLibrary, System.mapLibraryName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Java SE 17 — ClassLoader.findLibrary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String))
- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [Java SE 17 — UnsatisfiedLinkError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsatisfiedLinkError.html)
- [Java SE 17 — JNI Types and Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
