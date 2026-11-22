# Thư viện bản địa gắn với class loader và giới hạn nạp lại trong Java

## 1. Vì sao một thư viện native không giống một class Java?

Một ứng dụng Java có thể tạo nhiều `ClassLoader` để nạp các phiên bản class khác nhau, ví dụ khi chạy plugin, ứng dụng server hoặc một hệ thống hot deployment. Tuy nhiên, **thư viện JNI native** (`.so`, `.dll`, `.dylib`) không thể được nạp và thay thế linh hoạt theo cách đơn giản như bytecode Java.

Theo hợp đồng của Java Native Interface (JNI), **mỗi class loader quản lý tập thư viện native riêng; cùng một thư viện JNI không được nạp đồng thời bởi hai class loader khác nhau**. Khi loader thứ hai cố nạp cùng thư viện đã thuộc loader thứ nhất, JVM ném `UnsatisfiedLinkError`. Quy tắc này bảo vệ sự tách biệt kiểu Java giữa các class loader: hai class cùng tên nhưng do hai loader khác nhau định nghĩa là hai kiểu khác nhau, trong khi mã native có thể lưu `jclass`, `jmethodID` hoặc các reference chỉ có ý nghĩa trong ngữ cảnh đã tạo ra chúng.

Hệ quả thực tế: **thay JAR của plugin hoặc tạo class loader mới không tự động thay được thư viện native đang chạy**. Khả năng dỡ native library phụ thuộc vòng đời của class loader sở hữu thư viện và các tham chiếu còn sống; không có lời gọi `System.unloadLibrary()` công khai cho ứng dụng yêu cầu dỡ một thư viện JNI ngay lập tức.

Bài này tập trung vào cơ chế **JNI native library loading trong một JVM**. Cơ chế nạp bằng Foreign Function & Memory API (FFM) có API và vòng đời riêng, không được suy ra máy móc từ các quy tắc sở hữu JNI bên dưới.

## 2. Class loader quyết định không gian tên của JNI

### 2.1. Class có danh tính gồm tên và defining loader

Giả sử có hai class loader `L1` và `L2` cùng định nghĩa class mang tên `plugin.NativeProbe`. Khi đó:

- `plugin.NativeProbe` do `L1` định nghĩa và `plugin.NativeProbe` do `L2` định nghĩa **không phải cùng một Java class**; `Class<?>`, kiểu đối tượng, static fields và kiểm tra ép kiểu của chúng cũng tách biệt.
- Một thư viện JNI có thể dùng các tên symbol như `Java_plugin_NativeProbe_doubleValue` hoặc `RegisterNatives` để liên kết phương thức với implementation. Nếu thư viện bị dùng lẫn cho class khác loader, native cache và các JNI reference có thể liên kết sai đối tượng/kiểu.
- Vì vậy, JVM theo dõi native libraries theo loader và chặn việc đăng ký lại cùng JNI library cho loader khác.

Điều này vẫn đúng khi cả hai loader cùng đọc **một bản JAR hoặc cùng thư mục chứa `.class`**. Địa chỉ tệp bytecode giống nhau không làm hai class có cùng danh tính khi defining loader khác nhau.

### 2.2. Cơ chế thường gặp khi nạp thư viện

```java
// Nạp bằng tên logic; JVM ánh xạ tên theo hệ điều hành.
System.loadLibrary("native_probe");

// Nạp bằng đường dẫn tuyệt đối đến tệp thư viện cụ thể.
System.load("/opt/app/native/libnative_probe.so");
```

- `System.loadLibrary("native_probe")` nhận **tên thư viện logic**, không thêm đường dẫn hay phần mở rộng. Với cách đặt tên thông dụng, Linux dùng `libnative_probe.so`, Windows dùng `native_probe.dll`. JVM tìm thư viện theo cơ chế tìm kiếm native của loader/JVM/nền tảng; custom `ClassLoader.findLibrary` có thể trả về đường dẫn tuyệt đối do chính loader chọn.
- `System.load("/.../libnative_probe.so")` nhận **đường dẫn tuyệt đối** tới tệp native. Nó giúp xác định đúng tệp được yêu cầu, nhưng **không bỏ qua ràng buộc mỗi thư viện JNI chỉ thuộc một loader tại một thời điểm**.
- Java class nào **thực sự gọi** `System.load`/`System.loadLibrary` rất quan trọng: trong tình huống thông thường, JNI library được gắn với class loader định nghĩa class thực hiện lời gọi. Đừng nhầm với **thread context class loader**: đổi `Thread.currentThread().setContextClassLoader(...)` không tự chuyển quyền sở hữu thư viện JNI.
- Load lại cùng thư viện trong **chính loader đã sở hữu** thường được JVM xem là thư viện đã được nạp và không tạo thêm một bản hoạt động mới. Một lời gọi thứ hai không thay thế mã máy bằng phiên bản khác vừa ghi lên đĩa.

`System.mapLibraryName("native_probe")` giúp xác định tên tệp native tương ứng trên nền tảng hiện tại, nhưng không tự đảm bảo tệp có tồn tại, đúng ABI hoặc có thể nạp.

### 2.3. Mô hình sở hữu

```text
JVM process
│
├── ClassLoader L1
│   ├── plugin.NativeProbe (class do L1 định nghĩa)
│   └── JNI library: /path/libnative_probe.so   ← đã được L1 nạp
│
└── ClassLoader L2
    └── plugin.NativeProbe (class khác, do L2 định nghĩa)
        └── System.load(cùng thư viện) → UnsatisfiedLinkError
```

Đây là **quy tắc liên kết JNI của JVM**, không phải chỉ là lỗi “không tìm thấy file” của bộ nạp thư viện hệ điều hành. Đổi `java.library.path`, thử lại trong một class loader khác hoặc sửa tên class Java thường không giải quyết đúng nguyên nhân.

## 3. Các tình huống nạp lại: điều gì thực sự xảy ra?

| Tình huống | Kết quả/cần hiểu |
| --- | --- |
| `L1` gọi `System.load` cho library lần đầu | JVM kiểm tra và nạp JNI library nếu đường dẫn, kiến trúc, dependencies, quyền truy cập và entry point hợp lệ |
| `L1` tiếp tục gọi load cho cùng library | Thường được xem như đã nạp; không tự khởi tạo bản mã mới hay hot swap |
| `L2` khác `L1` cố nạp **chính library đó** khi `L1` còn sở hữu | `UnsatisfiedLinkError`, thường kèm thông tin đã được nạp ở class loader khác |
| Đóng `URLClassLoader` bằng `close()` | Đóng tài nguyên tìm kiếm class/JAR theo hợp đồng `URLClassLoader`; **các class đã load vẫn có thể được sử dụng**, không có cam kết unload native ngay |
| Bỏ tất cả tham chiếu tới `L1` và các class/instance liên quan | `L1` *có thể* trở thành đối tượng đủ điều kiện để GC; chưa chứng minh thư viện đã được dỡ |
| GC thực sự thu hồi loader sở hữu library | JNI quy định library **có thể được unload** cùng vòng đời loader, với `JNI_OnUnload` nếu thư viện cung cấp; thời điểm GC/unload không được ứng dụng kiểm soát chính xác |
| Ghi đè tệp `.so`/`.dll` trên đĩa sau khi đã load | Mã đã nạp không tự đổi sang bản mới; thao tác có thể thất bại hoặc nguy hiểm tùy OS/filesystem |
| Đổi tên hoặc copy thành một tệp native khác | Có thể thay đổi cách JVM/OS nhận diện thư viện, nhưng **không bảo đảm độc lập về symbol, C global state, dependencies hay ABI**; không phải chiến lược hot reload đáng tin cậy |

Thông điệp cốt lõi: **unload được về lý thuyết không đồng nghĩa có thể ra lệnh unload tại một thời điểm cụ thể**. Tính sẵn sàng để thay phiên bản native cần được thiết kế, không được ngầm suy ra từ việc tạo một loader mới.

## 4. Ví dụ chạy được: hai class loader cùng nạp một JNI library

Ví dụ sử dụng **JDK 17 trở lên, Linux, GCC/Clang và một JDK có header JNI**. Một Java class trong plugin nạp `libnative_probe.so`, rồi chương trình tạo hai `URLClassLoader` khác nhau trỏ tới cùng thư mục bytecode. Việc sử dụng `parent = null` giúp mỗi loader tự định nghĩa class `plugin.NativeProbe`, thay vì vô tình ủy quyền cho application class loader nạp một class chung.

Tạo cây tệp:

```text
project/
├── src/
│   ├── LoaderCollisionDemo.java
│   └── plugin/
│       └── NativeProbe.java
├── native/
│   └── native_probe.c
└── build/                    # sinh ra bằng lệnh build
```

### 4.1. Java class trực tiếp gọi `System.load`

**Tệp `src/plugin/NativeProbe.java`:**

```java
package plugin;

public final class NativeProbe {
    static {
        String path = System.getProperty("demo.native.path");
        if (path == null || path.isBlank()) {
            throw new IllegalStateException(
                    "Set -Ddemo.native.path to an absolute native library path");
        }
        System.load(path);
    }

    private NativeProbe() {
    }

    public static native int doubleValue(int number);
}
```

Khi `NativeProbe` được **khởi tạo lần đầu**, static initializer chạy `System.load`. Vì mỗi loader sẽ tự định nghĩa `NativeProbe`, chúng tạo ra hai lần khởi tạo class độc lập. Việc dùng cùng đường dẫn native cố tình tạo xung đột ở lần thứ hai.

### 4.2. Java driver tạo hai class loader thực sự khác nhau

**Tệp `src/LoaderCollisionDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderCollisionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderCollisionDemo <classes-directory>");
        }

        URL classesUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader first =
                     new URLClassLoader(new URL[]{classesUrl}, null);
             URLClassLoader second =
                     new URLClassLoader(new URL[]{classesUrl}, null)) {

            Class<?> inFirst =
                    Class.forName("plugin.NativeProbe", true, first);
            Object result = inFirst
                    .getMethod("doubleValue", int.class)
                    .invoke(null, 21);
            System.out.println("L1 -> " + result);

            try {
                Class.forName("plugin.NativeProbe", true, second);
                System.out.println("L2 -> unexpectedly loaded");
            } catch (UnsatisfiedLinkError expected) {
                System.out.println("L2 -> UnsatisfiedLinkError");
            }
        }
    }
}
```

`Class.forName(name, true, loader)` vừa tải vừa yêu cầu **initialize** class, nên static initializer `System.load` chắc chắn được thực thi trong ví dụ. Lời gọi `getMethod(...).invoke(null, 21)` kiểm tra JNI method ở loader đầu thực sự hoạt động, không chỉ nạp tệp thành công.

`try-with-resources` đóng hai `URLClassLoader` khi kết thúc phạm vi; như sẽ thấy ở phần sau, thao tác này **không xác nhận native library đã unload**. Việc bắt `UnsatisfiedLinkError` ở loader thứ hai nhằm mô tả lỗi dự kiến trong môi trường build hợp lệ; nếu loader đầu thất bại, phải kiểm tra lỗi tệp/ABI thay vì hiểu là xung đột class loader.

### 4.3. Native implementation

**Tệp `native/native_probe.c`:**

```c
#include "plugin_NativeProbe.h"

JNIEXPORT jint JNICALL Java_plugin_NativeProbe_doubleValue(
        JNIEnv *env, jclass clazz, jint number) {
    (void)env;
    (void)clazz;
    return number * 2;
}
```

Hàm C sử dụng prototype từ header tạo bởi `javac -h`. `JNIEXPORT` và `JNICALL` giữ quy ước export/calling convention JNI; vì method là `static`, tham số ẩn thứ hai là `jclass`. Với số đầu vào 21, kết quả 42 nằm trong miền `jint` nên phép nhân không gặp tràn.

### 4.4. Biên dịch và chạy trên Linux

Tại thư mục `project`, giả sử biến môi trường `JAVA_HOME` trỏ tới JDK đang dùng:

```bash
mkdir -p build/classes build/headers

javac -h build/headers -d build/classes \
  src/plugin/NativeProbe.java \
  src/LoaderCollisionDemo.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_probe.c -o build/libnative_probe.so

java -Ddemo.native.path="$(pwd)/build/libnative_probe.so" \
  -cp build/classes LoaderCollisionDemo build/classes
```

**Kết quả stdout mong đợi khi chạy trên JDK 17 với môi trường JNI đúng:**

```text
L1 -> 42
L2 -> UnsatisfiedLinkError
```

Để biết thông báo gốc khi xử lý sự cố, có thể thêm `System.err.println(expected.getMessage());` trong `catch`; văn bản thông báo có thể thay đổi theo JDK và hệ điều hành, nên ví dụ chỉ cố định tên loại lỗi trên stdout.

**JDK 24 trở lên:** việc load/link JNI thuộc nhóm thao tác native access bị kiểm soát; có thể xuất hiện cảnh báo trên stderr nếu chưa cấp quyền. Với class trên **classpath** trong ví dụ, thêm tùy chọn `--enable-native-access=ALL-UNNAMED` trước tên main class:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.path="$(pwd)/build/libnative_probe.so" \
  -cp build/classes LoaderCollisionDemo build/classes
```

Tùy chọn native access chỉ xử lý chính sách cho phép thao tác native, **không làm biến mất lỗi một JNI library thuộc hai loader**. Với module có tên, nên giới hạn quyền bằng `--enable-native-access=<module-name>` theo phiên bản JDK đang dùng.

Trên macOS hoặc Windows, cần build lại native library cho ABI của hệ đó, thay tên tệp và lệnh biên dịch/link phù hợp; **không dùng trực tiếp** bản `.so` Linux cho JVM trên nền tảng khác.

### 4.5. Vì sao ví dụ không thể “sửa” bằng `System.gc()`?

Khi loader thứ hai được khởi tạo, `first` và `inFirst` vẫn còn tham chiếu mạnh trong chương trình. Thư viện native của loader thứ nhất vẫn thuộc loader đó. Kể cả sau khi thoát `try`, đóng loader không tự biến mọi class/object thành không còn tham chiếu; việc GC/thu hồi là quyết định của JVM. Gọi `System.gc()` chỉ là **đề nghị thu gom**, không cung cấp đồng bộ “đã dỡ xong thư viện”. Không có cách nâng cấp đáng tin cậy dựa vào một vòng lặp `System.gc()` rồi tải lại cùng thư viện.

## 5. Vòng đời của JNI library và các hook quản lý

Với thư viện JNI được **liên kết động**, các hook sau là tùy chọn:

```c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Khởi tạo tài nguyên cần thiết cho lần nạp JNI này. */
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Chỉ cleanup native đơn giản, an toàn trong ngữ cảnh bất định. */
}
```

- `JNI_OnLoad` được JVM gọi khi nạp JNI library có cung cấp hook này; nó trả về phiên bản JNI mà library yêu cầu. Khi dùng `RegisterNatives`, việc đăng ký method với đúng class/loader thường được tổ chức trong quá trình load.
- `JNI_OnUnload` được JVM gọi khi loader chứa thư viện được GC theo vòng đời JNI. Hook có thể chạy trong ngữ cảnh không xác định; JNI specification yêu cầu thận trọng khi sử dụng dịch vụ JVM, **tránh gọi ngược Java một cách tùy tiện**.
- Không nên đặt độ đúng của chức năng ứng dụng vào việc `JNI_OnUnload` xảy ra ngay sau một sự kiện như “plugin disabled”. Cleanup quan trọng cần có API **explicit close/dispose**, được gọi khi ứng dụng còn biết tài nguyên thuộc về ai.
- Library được nạp bởi loader sống suốt tiến trình (ví dụ loader chung của ứng dụng) thường tiếp tục tồn tại đến khi JVM kết thúc; mong đợi một hot reload native trong chính tiến trình là giả định thiếu an toàn.

**Lưu ý:** `JNI_OnLoad_L`/`JNI_OnUnload_L` được dùng cho **thư viện JNI liên kết tĩnh với VM** theo quy định JNI; không nhầm với `JNI_OnLoad`/`JNI_OnUnload` của thư viện động trong ví dụ.

### 5.1. Những gì giữ class loader còn sống

Một loader có thể không được thu hồi vì các tham chiếu tưởng như nhỏ:

- Object của plugin, `Class<?>`, `Method`, `MethodHandle`, singleton hoặc cache trong code của ứng dụng vẫn trỏ tới class do loader ấy định nghĩa.
- Thread còn chạy code plugin, task trong executor, timer, listener, callback, `ThreadLocal` hoặc thread context class loader vẫn giữ liên hệ với plugin.
- Một `jobject`/`jclass` được JNI lưu bằng **global reference** và chưa `DeleteGlobalRef` có thể giữ object/class tương ứng còn sống. Native cache lưu class và method ID mà không kiểm soát vòng đời cũng dễ trở thành nguồn lỗi khi reload.
- Native thread được tạo/attach vào JVM, callback hoặc handle phía C vẫn dùng tài nguyên của bản plugin cũ; không nên unload khi một luồng còn có thể thực thi mã trong thư viện.
- Framework, registry, MBean, scheduler hoặc logging appender còn giữ reference tới loader cũ.

`WeakReference<ClassLoader>` có thể giúp **quan sát** xem loader đã trở thành có thể thu hồi sau khi giải phóng tham chiếu hay chưa; bản thân nó không ép loader bị GC và không chứng minh tệp native đã thực sự được hệ điều hành giải phóng.

### 5.2. Native memory không thuộc riêng “heap của plugin”

Class loader tổ chức **danh tính kiểu** và liên kết JNI trong JVM; nó **không tạo sandbox ở cấp tiến trình**. Mã C có thể nắm giữ con trỏ native heap, file descriptor, socket, thread, process-global data và phụ thuộc vào thư viện hệ thống. Những tài nguyên này không tự biến mất khi Java object không còn sử dụng. Một thư viện native lỗi còn có thể làm sập cả JVM.

Vì thế, cơ chế dispose phải mô tả rõ vòng đời của native handle, callback, thread và bộ đệm; việc bỏ class loader chỉ là một phần trong toàn bộ quá trình teardown.

## 6. Thiết kế cho hệ thống plugin và hot reload

### 6.1. Thiết kế khuyến nghị: một JNI bridge cố định, plugin chỉ gọi API Java chung

Nếu nhiều plugin cần **cùng một bản JNI library** trong cùng tiến trình, đặt class khai báo `native` và lời gọi `System.loadLibrary` trong một **module Java chung do parent loader ổn định định nghĩa**. Plugin loader con ủy quyền để cùng sử dụng API Java của bridge đó.

```text
Application / shared parent loader
└── shared.NativeBridge
    ├── static { System.loadLibrary("native_core"); }
    └── public static native int compute(int value);
         ↑
         ├── Plugin loader A → gọi shared.NativeBridge.compute(...)
         └── Plugin loader B → gọi shared.NativeBridge.compute(...)
```

Ví dụ Java bridge (chỉ là fragment cho cấu trúc kiến trúc; thư viện `native_core` và hàm JNI tương ứng cần được triển khai):

```java
package shared;

public final class NativeBridge {
    static {
        System.loadLibrary("native_core");
    }

    private NativeBridge() {}

    public static native int compute(int value);
}
```

Cả hai plugin gọi **phương thức native khai báo trên cùng `shared.NativeBridge`**, vì đó là class của loader cha. Cần chú ý: việc thư viện được loader cha nạp **không tự bảo đảm** rằng một phương thức `native` *khai báo riêng trong class do loader con định nghĩa* có thể liên kết tới thư viện ấy. Do đó, hãy đặt chính entry point native trong bridge chung và giao tiếp qua interface/API Java ổn định.

**Lợi ích:** plugin có thể reload logic Java mà không cần nạp lại cùng thư viện JNI. **Giới hạn:** native core là thành phần có vòng đời của loader cha; thay phiên bản native core vẫn thường cần khởi động lại JVM hoặc thay kiến trúc xử lý.

### 6.2. Khi các plugin cần các phiên bản native khác nhau

Đừng vội copy cùng thư viện sang tên khác rồi gọi `System.load` như một cơ chế cô lập. Tùy OS/linker, các bản copy có thể cùng phụ thuộc vào global symbol, thư viện dùng chung hoặc trạng thái hệ thống; JNI code và C code thường không được thiết kế để coexist theo nhiều phiên bản trong một process. Đặc biệt nguy hiểm nếu hai phiên bản có C++ ABI khác nhau, singleton native khác nhau hoặc quản lý tài nguyên giao thoa.

Có ba hướng cần cân nhắc:

1. **Thiết kế native API cho phép nhiều instance độc lập** trong cùng một library: mỗi instance dùng opaque handle, không dựa vào static global mutable state; plugin gọi bridge Java chung để tạo/hủy handle. Đây là cách đơn giản nếu nhu cầu là nhiều plugin sở hữu **trạng thái** khác nhau chứ không phải nhiều bản mã máy khác nhau.
2. **Một tiến trình con riêng cho native component** khi cần nâng cấp phiên bản độc lập. Java trao đổi với worker qua IPC/RPC; khi cập nhật native library, dừng/restart worker process. Đây là ranh giới vòng đời rõ ràng nhất và giảm tác động crash native lên JVM chính.
3. **Class loader riêng và native library riêng** chỉ khi kiến trúc, cơ chế deployment và dependencies đã được kiểm chứng cho mọi nền tảng mục tiêu. Vẫn phải chấp nhận rằng unload không tức thời và việc “replace while running” không phải API được đảm bảo bởi JNI.

Nếu yêu cầu là **reload plugin Java thường xuyên** còn JNI library ổn định, hướng (1) hoặc bridge cha thường phù hợp. Nếu yêu cầu là **thay mã native đang chạy mà không restart ứng dụng Java**, hướng tiến trình con thường dễ kiểm soát hơn.

### 6.3. Quy trình dừng plugin trước khi thử giải phóng loader

Với plugin thực sự sở hữu JNI library riêng, thứ tự teardown hợp lý là:

1. Ngừng định tuyến request mới tới plugin và chờ/cancel các tác vụ đang chạy theo hợp đồng ứng dụng.
2. Gọi API `close()`/`dispose()` ở Java và native để ngừng callback, thread, executor, timer; giải phóng native handle, buffer và tài nguyên liên quan.
3. Hủy đăng ký listener/registry, cleanup `ThreadLocal`, xóa cache, xóa JNI global reference đúng cách; tránh thread context class loader còn trỏ đến loader cũ.
4. Đóng `URLClassLoader` (nếu dùng) để giải phóng tài nguyên tìm kiếm tệp/JAR; bỏ những tham chiếu mạnh còn lại tới loader, class và object của plugin.
5. Theo dõi khả năng loader được GC và trạng thái thư viện bằng công cụ chẩn đoán. **Không** thiết kế thao tác load phiên bản mới dựa trên giả định rằng bước 4 đã hoàn tất unload native.

Các bước này giúp giảm rò rỉ, nhưng **không biến JVM thành hệ thống thay thế thư viện native tức thời**. Nếu bắt buộc phải chuyển phiên bản tại một thời điểm xác định, hãy dùng restart tiến trình chứa thư viện hoặc giao thức chuyển giao phiên bản riêng đã được kiểm chứng.

## 7. Phân biệt những lỗi dễ bị chẩn đoán nhầm

`UnsatisfiedLinkError` không chỉ có một nguyên nhân. Phân loại theo thời điểm và thông tin lỗi:

| Biểu hiện | Cần kiểm tra |
| --- | --- |
| `no native_core in java.library.path` | Tên logic, vị trí file, search path, `findLibrary` và cách đóng gói |
| `Native Library ... already loaded in another classloader` | Class nào gọi `System.load`, defining loader của class đó, thư viện nào đã nạp trước |
| `Can't find dependent libraries` hoặc lỗi dependency của linker | Thư viện phụ thuộc, loader path của hệ điều hành, runtime C/C++, kiến trúc |
| `wrong ELF class`, `not a valid Win32 application`, sai machine type | CPU/OS/bitness/ABI của JVM và thư viện native |
| `'...nativeMethod(...)'` / `Native method not found` sau khi load library | Tên JNI symbol, `javac -h`, descriptor, static/instance, `RegisterNatives`, symbol visibility |
| JVM crash hoặc dữ liệu hỏng dù load thành công | JNI signature, lifetime của pointer/reference, synchronization, native memory safety |

Một số trường hợp báo lỗi ở **lúc nạp file**, một số chỉ ở **lúc JVM cần liên kết phương thức native lần đầu**. Cần giữ nguyên stack trace và thông báo gốc, rồi kiểm tra thư viện thực sự được nạp, đừng kết luận từ tên ngoại lệ đơn lẻ.

### Gợi ý quan sát

- Trong Java, in `someClass.getClassLoader()` và xác định class thực hiện `System.load`; nếu cần, đối chiếu object identity của loader chứ không chỉ tên class loader.
- Dùng `javap -s` để xem descriptor Java; `javac -h` để sinh prototype JNI; dùng `nm -D`/`readelf -Ws` trên Linux hoặc `dumpbin /exports` trên Windows để kiểm tra symbol native.
- Các sự kiện JFR `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload` có thể giúp quan sát vòng đời thư viện trên các JDK hỗ trợ; hãy kiểm tra cấu hình recording và phiên bản JDK. Một sự kiện unload quan sát được là bằng chứng, còn **không thấy sự kiện** không đủ kết luận rằng chỉ có lỗi class loader.
- Với JVM HotSpot, `jcmd <pid> VM.classloader_stats` có thể giúp điều tra loader còn tồn tại; lệnh/chẩn đoán cụ thể phụ thuộc JDK.

### Hai ngộ nhận thường gặp

**“Đổi tên file native là cô lập được plugin.”** Không có bảo đảm: native code sống trong cùng process, có thể chia sẻ symbols, dependencies, native globals và memory; loader có tên mới chỉ giải quyết một phần cách JVM nhận diện đường dẫn.

**“Gọi `URLClassLoader.close()` là thư viện đã unload.”** Sai. `close()` đóng tài nguyên loader dùng để tìm class/JAR; những class đã load vẫn có thể dùng được. Thu hồi class loader và giải phóng JNI library là những bước vòng đời khác, phụ thuộc GC và tham chiếu còn sống.

## 8. Câu hỏi tự kiểm tra

**1.** Hai plugin có class `plugin.NativeProbe` giống hệt nhau nhưng do hai class loader độc lập định nghĩa. Cả hai gọi `System.loadLibrary("native_core")`. Plugin đầu đã load thành công. Plugin sau có chắc load được?  
**Không.** Nếu cả hai resolve tới cùng JNI native library trong khi loader đầu đang sở hữu nó, loader thứ hai bị chặn bằng `UnsatisfiedLinkError`.

**2.** Một plugin được cập nhật JAR và tạo loader mới, nhưng phương thức `native` cũ vẫn phải dùng cùng library. Có phương án giảm xung đột?  
**Có.** Đưa declaration/entry point `native` vào **bridge chung do loader cha nạp**, để các plugin gọi qua API Java thống nhất. Việc reload plugin khi đó không đòi nạp lại native library.

**3.** Vì sao `System.gc()` không nên nằm trong luồng cập nhật phiên bản native?  
Vì GC không cung cấp bảo đảm về **thời điểm** thu hồi loader hay unload thư viện. Chỉ cần một reference mạnh, thread hoặc global JNI ref còn tồn tại là vòng đời cũ có thể tiếp tục.

**4.** Nếu ứng dụng cần nâng cấp chính mã C/C++ theo từng plugin mà không restart JVM chính, hướng kiến trúc nào rõ ràng nhất?  
Dùng native worker **ở tiến trình riêng** và giao tiếp qua IPC/RPC; restart worker làm vòng đời binary, heap, thread và thư viện của nó được giải phóng theo ranh giới process.

**5.** Bật `--enable-native-access=ALL-UNNAMED` trên JDK 24+ có cho phép nạp cùng JNI library vào hai class loader không?  
**Không.** Tùy chọn này liên quan quyền dùng API native, còn quy tắc **một JNI library không đồng thời thuộc hai class loader** vẫn áp dụng.

## 9. Ghi nhớ và tài liệu đối chiếu

- **Đơn vị sở hữu JNI library là class loader**, do đó phải biết class nào thực hiện load và loader nào đã định nghĩa class đó.
- **Một thư viện JNI không thể đồng thời được nạp bởi nhiều class loader**. Lỗi thường thấy là `UnsatisfiedLinkError`; không nhầm với lỗi thiếu tệp hoặc thiếu JNI symbol.
- **Classloader reload không tương đương native-library hot reload**. `URLClassLoader.close()`, thay JAR, thay file native và gọi `System.gc()` đều không bảo đảm unload/reload đồng bộ.
- Để reload code Java dễ dàng, dùng **shared Java/native bridge**. Để nâng cấp mã native có thời điểm xác định, dùng **process boundary** hoặc thiết kế lifecycle chuyên biệt.
- JNI cleanup cần quy trình explicit cho callback, thread, native handles và global references; không dựa vào `JNI_OnUnload` để xử lý kịp thời các nghiệp vụ quan trọng.

Nguồn chuẩn để kiểm chứng các hợp đồng liên quan:

- [Oracle JNI Specification — Invocation API, Library and Version Management (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): quy tắc mỗi class loader quản lý native libraries và `JNI_OnLoad`/`JNI_OnUnload`.
- [Oracle JNI Specification — Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native method linking, naming, `System.loadLibrary`.
- [Java SE 17 API — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nghĩa thực tế của `close()`.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): `--enable-native-access` và thay đổi từ JDK 24.
