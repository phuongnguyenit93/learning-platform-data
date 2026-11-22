# Tìm lớp bằng `FindClass` và ảnh hưởng của ngữ cảnh class loader trong JNI

## 1. Vấn đề: tên lớp đúng nhưng JNI vẫn không tìm thấy

Khi C/C++ cần gọi phương thức Java, đọc field hoặc tạo object qua JNI, mã native thường bắt đầu bằng:

~~~c
jclass clazz = (*env)->FindClass(env, "com/example/Service");
~~~

`FindClass` không tra một danh sách lớp chung cho toàn bộ JVM. Nó dùng **ngữ cảnh class loader** gắn với nơi lời gọi JNI xuất phát. Vì vậy lớp `com.example.Service` có thể đang tồn tại trong tiến trình nhưng `FindClass` vẫn không tìm thấy do loader được chọn không nhìn thấy định nghĩa lớp đó. Ngược lại, nhiều loader có thể định nghĩa các lớp **cùng tên** nhưng có **danh tính kiểu khác nhau**.

Đây là vấn đề quan trọng khi Java gọi native code để tương tác ngược lại với Java, nhất là trong ứng dụng có plugin, custom `URLClassLoader`, OSGi, application server, Android và các **native worker thread** tự tạo.

Mục tiêu bài học:

- Dùng đúng cú pháp `FindClass`, kiểm tra `jclass` và xử lý ngoại lệ.
- Giải thích loader JNI chọn khi gọi từ native method, `JNI_OnLoad`, `JNI_OnUnload` và native thread tự attach.
- Phân biệt loader khai báo native method với **thread context class loader (TCCL)**.
- Chạy ví dụ Java 17+ với custom loader chứng minh kết quả tìm lớp.
- Dùng `Class<?>`, `GetObjectClass`, `ClassLoader.loadClass` hoặc global reference khi cần một loader cụ thể.
- Tránh cache local reference sai lifetime và nhầm hai class cùng tên từ hai loader.

## 2. Hợp đồng API `FindClass`

Khai báo C của JNI:

~~~c
jclass FindClass(JNIEnv *env, const char *name);
~~~

Cách gọi **C** và **C++** khác nhau về cú pháp:

~~~c
// C, trong hàm JNI có JNIEnv *env:
jclass cls = (*env)->FindClass(env, "java/lang/String");
~~~

~~~cpp
// C++, trong hàm JNI có JNIEnv *env:
jclass cls = env->FindClass("java/lang/String");
~~~

Tham số `name` là **tên nội bộ theo JNI**, được mã hóa bằng Modified UTF-8. Tên lớp dùng dấu `/` thay dấu `.`; tên mảng dùng cú pháp descriptor.

| Kiểu ở Java | Tên truyền cho `FindClass` |
| --- | --- |
| `java.lang.String` | `"java/lang/String"` |
| `com.example.Service` | `"com/example/Service"` |
| `com.example.Outer.Inner` (nested class) | `"com/example/Outer$Inner"` |
| `int[]` | `"[I"` |
| `java.lang.String[]` | `"[Ljava/lang/String;"` |
| `java.lang.String[][]` | `"[[Ljava/lang/String;"` |

Không truyền `"com.example.Service"` cho `FindClass` của một class thông thường; đó là tên dạng dotted được Java API như `ClassLoader.loadClass` sử dụng. Không dùng `"int"` để lấy `Class` của primitive `int`; có thể truyền `int.class` từ Java nếu cần.

**Kết quả thành công:** hàm trả một `jclass`, tức một JNI reference tới Java object kiểu `java.lang.Class`. Nó là một **local reference**, không phải một con trỏ C/C++ đến cấu trúc nội bộ của class.

**Kết quả thất bại:** hàm trả `NULL` và thường để lại Java exception/error đang chờ, chẳng hạn `NoClassDefFoundError`. Đặc tả còn liệt kê `ClassFormatError`, `ClassCircularityError` và `OutOfMemoryError` trong các trường hợp khác. Đừng mặc định mọi lần `NULL` đều do sai tên; cần xét loader, dependency và lỗi khởi tạo class.

Đoạn xử lý cơ bản (đặt bên trong một JNI function trả `void`, không phải chương trình độc lập):

~~~c
jclass target = (*env)->FindClass(env, "com/example/Target");
if (target == NULL) {
    // Không dùng target. Nếu có exception pending,
    // để nó truyền về Java hoặc xử lý một cách có chủ đích.
    return;
}

/* Dùng target để tra method/field ... */
(*env)->DeleteLocalRef(env, target);
~~~

Nếu `target == NULL`, không được gọi tiếp `GetMethodID`/`NewObject` bằng reference đó. Chỉ xóa pending exception với `ExceptionClear` khi đã có nhánh phục hồi thực sự; xóa vô điều kiện làm mất nguyên nhân lỗi.

## 3. Loader nào được sử dụng?

Đặc tả JNI xác định **loader theo ngữ cảnh**, như sau:

| Ngữ cảnh gọi `FindClass` | Loader được JNI chọn | Điều cần nhớ |
| --- | --- | --- |
| Bên trong native method do Java gọi | Loader của **lớp khai báo native method hiện tại** | Thường tìm được lớp thuộc cùng ứng dụng/plugin với lớp khai báo native |
| Trong `JNI_OnLoad` hoặc `JNI_OnLoad_L` | Loader của lớp đang nạp thư viện native | Thích hợp để tìm và cache class trước khi native worker chạy |
| Trong `JNI_OnUnload` hoặc `JNI_OnUnload_L` | **System class loader** | Loader dùng khi load có thể không còn tồn tại |
| Native thread tự tạo, sau `AttachCurrentThread`, không có native method Java làm ngữ cảnh | Quy tắc Invocation Interface: **system class loader** | Có thể không nhìn thấy các lớp riêng của plugin |
| Ứng dụng C/C++ nhúng JVM qua Invocation Interface | **System class loader** nếu không có native method hiện tại | Không mặc định tìm trong custom loader bất kỳ |

Khi gọi trong native method, điểm mấu chốt là **loader của class khai báo chính native method**, không phải loader của đối tượng tùy ý truyền cho hàm. Có thể có Java caller khác ở ngoài, nhưng quy tắc được xác định theo native method hiện tại.

### 3.1. TCCL không tự điều khiển `FindClass`

Java hỗ trợ:

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
~~~

Nhiều framework chủ động dùng **Thread Context ClassLoader** để tìm class hoặc resource. Tuy nhiên JNI `FindClass` không tự chuyển sang `pluginLoader` chỉ vì TCCL thay đổi. Native method của một class do **system loader** định nghĩa vẫn dùng loader theo ngữ cảnh của native method đó.

Ngược lại, một native method của `plugin.Bridge` (được custom loader định nghĩa) vẫn có thể `FindClass("plugin/Target")` thành công khi TCCL đang trỏ tới system loader. Ví dụ chạy được sau đây chứng minh đúng điều này.

## 4. Ví dụ Java 17+: chứng minh `FindClass` dùng loader của native method

Thiết lập ba lớp:

- `Launcher`: chỉ có trên application classpath, do system/application loader tải.
- `plugin.Bridge`: class chứa native method, do **`URLClassLoader` riêng** tải.
- `plugin.Target`: class cần tìm, nằm trong cùng custom loader với `Bridge`.

Mã C gọi `FindClass("plugin/Target")` trong native method của `Bridge` và trả `Class<?>` về Java. Java in tên, identity và loader thực tế để kiểm chứng.

### 4.1. Bố cục nguồn

~~~text
findclass-lab/
├── Launcher.java
├── plugin-src/
│   └── plugin/
│       ├── Bridge.java
│       └── Target.java
└── native/
    └── bridge.c

Sau khi build:
├── host/Launcher.class
├── plugin-classes/plugin/Bridge.class
├── plugin-classes/plugin/Target.class
├── native/plugin_Bridge.h
└── libfindclass_lab.so | libfindclass_lab.dylib | findclass_lab.dll
~~~

Giữ `plugin-classes` nằm **ngoài** application classpath của `Launcher`. Việc tách đường dẫn này là điều kiện của thí nghiệm.

### 4.2. `plugin-src/plugin/Target.java`

~~~java
package plugin;

public final class Target {
    private Target() {
    }
}
~~~

Không cần method hoặc field nào ở `Target`. Ta chỉ tìm đúng `Class` object và loader đã định nghĩa lớp này.

### 4.3. `plugin-src/plugin/Bridge.java`

~~~java
package plugin;

public final class Bridge {
    static {
        System.loadLibrary("findclass_lab");
    }

    private Bridge() {
    }

    public static native Class<?> lookupTarget();
}
~~~

`System.loadLibrary("findclass_lab")` nhận **tên logic** của thư viện và nạp file đúng tên theo OS (Linux: `libfindclass_lab.so`; macOS: `libfindclass_lab.dylib`; Windows: `findclass_lab.dll`). `lookupTarget` có kết quả Java là `Class<?>`, được biểu diễn bởi `jclass` trong JNI header được sinh.

### 4.4. `Launcher.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        boolean appCanSeeTarget;
        try {
            Class.forName("plugin.Target");
            appCanSeeTarget = true;
        } catch (ClassNotFoundException ex) {
            appCanSeeTarget = false;
        }

        URL pluginUrl = Path.of("plugin-classes")
                .toAbsolutePath()
                .toUri()
                .toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl},
                ClassLoader.getPlatformClassLoader())) {

            // TCCL là system loader, không phải pluginLoader.
            Thread.currentThread().setContextClassLoader(
                    ClassLoader.getSystemClassLoader());

            Class<?> bridge = Class.forName(
                    "plugin.Bridge", true, pluginLoader);

            Class<?> found = (Class<?>) bridge
                    .getMethod("lookupTarget")
                    .invoke(null);

            Class<?> explicitlyLoaded = Class.forName(
                    "plugin.Target", false, pluginLoader);

            System.out.println(
                    "App loader sees plugin.Target: " + appCanSeeTarget);
            System.out.println("FindClass result: " + found.getName());
            System.out.println(
                    "Resolved by plugin loader: "
                            + (found.getClassLoader() == pluginLoader));
            System.out.println(
                    "Matches explicit lookup: "
                            + (found == explicitlyLoaded));
            System.out.println(
                    "TCCL is plugin loader: "
                            + (Thread.currentThread()
                                    .getContextClassLoader() == pluginLoader));
        }
    }
}
~~~

`Launcher` nạp `Bridge` bằng reflection vì nó không có dependency biên dịch lên class plugin. `URLClassLoader` dùng **parent là platform loader**, để plugin có thể thấy Java API chuẩn mà không tự động lấy các class chỉ có trên application classpath. `plugin.Target` chỉ tồn tại trong `plugin-classes` do URLClassLoader quản lý.

`Class.forName("plugin.Target")` không truyền loader trong `Launcher` sử dụng loader gắn với `Launcher`; theo bố cục này sẽ ném `ClassNotFoundException`. Lời gọi `Class.forName("plugin.Target", false, pluginLoader)` tìm lớp với **loader tường minh**.

### 4.5. Sinh header và viết mã C

Trước khi biên dịch, tạo thư mục output. Trên Linux/macOS:

~~~bash
mkdir -p host plugin-classes native
~~~

Trên Windows CMD, trong thư mục `findclass-lab`:

~~~bat
mkdir host
mkdir plugin-classes
mkdir native
~~~

Chạy bằng **JDK 17 trở lên** (Linux/macOS):

~~~bash
javac -d host Launcher.java
javac -h native -d plugin-classes \
  plugin-src/plugin/Bridge.java \
  plugin-src/plugin/Target.java
~~~

Windows CMD (cùng tác dụng):

~~~bat
javac -d host Launcher.java
javac -h native -d plugin-classes plugin-src\plugin\Bridge.java plugin-src\plugin\Target.java
~~~

`javac -h native` tạo **`native/plugin_Bridge.h`**. Prototype trong header tương đương:

~~~c
JNIEXPORT jclass JNICALL Java_plugin_Bridge_lookupTarget(
        JNIEnv *, jclass);
~~~

Tạo toàn bộ file **`native/bridge.c`**:

~~~c
#include "plugin_Bridge.h"

JNIEXPORT jclass JNICALL Java_plugin_Bridge_lookupTarget(
        JNIEnv *env, jclass declaringClass) {
    (void) declaringClass;

    // Local reference được chuyển về Java thành Class<?>.
    return (*env)->FindClass(env, "plugin/Target");
}
~~~

Không cần `JNI_OnLoad` trong ví dụ này. `FindClass` chạy **trong native method của `plugin.Bridge`**, nên loader của `Bridge` được sử dụng. Nếu không thấy lớp, JVM sẽ báo lỗi khi lời gọi quay về Java; bản minh họa cố ý giữ nguyên nguyên nhân lỗi.

### 4.6. Biên dịch thư viện

Thiết lập `JAVA_HOME` là **thư mục gốc của JDK** có `include/jni.h`, và chọn compiler cùng kiến trúc với JVM (x64/ARM64...). Chạy **một** trong ba nhóm lệnh:

**Linux, GCC hoặc Clang:**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/bridge.c -o libfindclass_lab.so
~~~

**macOS, Clang:**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  native/bridge.c -o libfindclass_lab.dylib
~~~

**Windows x64, x64 Native Tools Command Prompt for Visual Studio:**

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" native\bridge.c /link /OUT:findclass_lab.dll
~~~

File thư viện được tạo ở thư mục gốc `findclass-lab`, nơi chạy JVM ở bước kế tiếp. Không dùng shared library khác kiến trúc hoặc khác OS với JVM.

### 4.7. Chạy và kết quả chính xác

Từ thư mục `findclass-lab`:

~~~bash
java -Djava.library.path=. -cp host Launcher
~~~

Stdout mong đợi với đúng cách build và classpath:

~~~text
App loader sees plugin.Target: false
FindClass result: plugin.Target
Resolved by plugin loader: true
Matches explicit lookup: true
TCCL is plugin loader: false
~~~

Giải thích:

1. **`false`:** application loader của `Launcher` không thấy `plugin.Target` vì `-cp` chỉ có `host`.
2. **`plugin.Target`:** `FindClass` trong native method tìm được class `Target`.
3. **`true`:** chính `pluginLoader` đã định nghĩa class được JNI trả về.
4. **`true`:** Java tìm class qua `pluginLoader` tường minh và nhận **cùng `Class<?>` object**.
5. **`false`:** TCCL không phải plugin loader nhưng `FindClass` vẫn thành công; điều này bác bỏ giả định rằng JNI luôn dùng TCCL.

Nếu vô tình thêm `plugin-classes` vào `-cp` của ứng dụng, kết quả thí nghiệm sẽ khác vì application loader cũng nhìn thấy `Target`. Giữ lớp ở đúng thư mục mới cô lập được hai loader.

### 4.8. Nhìn lại luồng JNI

~~~text
Launcher.class  (application/system loader)
      |
      | tạo URLClassLoader riêng
      v
pluginLoader --> plugin.Bridge + plugin.Target
      |
      | Class.forName("plugin.Bridge", true, pluginLoader)
      v
Bridge.<clinit> --> System.loadLibrary("findclass_lab")
      |
      | Bridge.lookupTarget() qua reflection
      v
JVM gọi Java_plugin_Bridge_lookupTarget(JNIEnv*, jclass)
      |
      | FindClass("plugin/Target")
      | JNI lấy loader của lớp khai báo native method: Bridge
      v
pluginLoader tìm được Target
      |
      v
JNI trả jclass --> Java nhận Class<?> --> getClassLoader() == pluginLoader
~~~

`FindClass` trả **class object**, không tự tạo instance `new Target()`. Muốn gọi method/constructor, native code cần thêm `GetMethodID`/`GetStaticMethodID` và các `Call*Method`/`NewObject` phù hợp. `JNIEnv *` và `jclass` của JNI signature là tham số **do JVM thêm**, không xuất hiện trong khai báo `lookupTarget()` của Java.

## 5. Native thread tự attach: tại sao kết quả có thể khác?

Trường hợp dễ xảy ra lỗi:

1. Java gọi native library.
2. Library C/C++ tạo thread OS riêng bằng cơ chế như `pthread_create` hoặc API thread hệ điều hành.
3. Thread đó gọi `JavaVM->AttachCurrentThread` để được dùng JNI và nhận `JNIEnv *` thuộc thread của nó.
4. Thread gọi `FindClass("plugin/Target")` **khi không có native method Java hiện tại làm ngữ cảnh**.
5. JNI sử dụng quy tắc của Invocation Interface, thường là **system class loader**; loader này có thể không thấy class chỉ nằm trong plugin loader.

Sơ đồ:

~~~text
Java Bridge.startWorker() --> native tạo OS thread
                                         |
                                         v
                              AttachCurrentThread
                                         |
                                         v
                                 JNIEnv* riêng
                                         |
                                         v
                         FindClass("plugin/Target")
                                         |
                       không có native method Bridge
                                         |
                                         v
                               system class loader
                                         |
                            plugin.Target không có
                                         |
                                         v
                         NULL / lỗi tìm định nghĩa
~~~

**Không phải cứ thread khác là lỗi.** Khi một **Java thread** thông thường gọi thẳng `Bridge.lookupTarget()`, JNI vẫn có native method context của `Bridge`, nên loader Bridge tiếp tục được sử dụng. Lỗi phát sinh đặc biệt với native thread **tự attach** khi không có context Java/native method phù hợp.

`JNIEnv *` là interface pointer **theo thread**; không chuyển `JNIEnv *` từ thread A sang B. Có thể giữ `JavaVM *` để attach/detach khi cần. Thread tự attach phải tuân thủ `DetachCurrentThread` trước khi chấm dứt theo Invocation API. Cả việc attach thành công **không** khiến loader của một plugin cũ tự trở thành loader mặc định.

### 5.1. Ba cách khắc phục

- **Truyền `Class<?>` từ Java** vào JNI nếu Java biết chính xác kiểu cần xử lý.
- **Truyền `ClassLoader` đúng** và gọi `loadClass` qua JNI khi tên lớp chỉ được biết lúc runtime.
- **Tra class từ ngữ cảnh đúng**, ví dụ `JNI_OnLoad` hoặc native method của plugin, rồi giữ `jclass` bằng `NewGlobalRef` để dùng trong worker thread.

Không chỉ thay đổi TCCL rồi giả định `FindClass` sẽ chọn loader đó. Có thể dùng TCCL cho **logic Java tự chọn loader**, nhưng JNI `FindClass` có quy tắc riêng.

## 6. `JNI_OnLoad` là ngoại lệ quan trọng

`JNI_OnLoad` là hook tùy chọn được JVM gọi khi nạp thư viện JNI. Theo đặc tả, `FindClass` chạy bên trong hook này dùng **class loader của class đã nạp thư viện**. Nếu `plugin.Bridge` gọi `System.loadLibrary` thì `JNI_OnLoad` thường nhìn thấy `plugin.Target`.

Điều đó thuận lợi cho việc cache class dùng về sau. Đoạn sau **minh họa kỹ thuật cache**, không cần thêm vào `native/bridge.c` của thí nghiệm nếu chưa thiết kế lifecycle:

~~~c
#include <jni.h>

static jclass g_target_class = NULL;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **) &env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    jclass local = (*env)->FindClass(env, "plugin/Target");
    if (local == NULL) {
        return JNI_ERR;
    }

    g_target_class = (jclass) (*env)->NewGlobalRef(env, local);
    (*env)->DeleteLocalRef(env, local);

    if (g_target_class == NULL) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

Ở đây:

- `local` là **local reference** từ `FindClass`; không được lưu nó vào biến global để dùng sau khi hàm kết thúc.
- `NewGlobalRef` tạo **global reference** hợp lệ qua nhiều lời gọi và thread JNI đã attach, đến khi được hủy.
- `DeleteLocalRef` giải phóng local reference vừa tạo.
- `DeleteGlobalRef` phải được gọi tại một **điểm cleanup có kiểm soát** khi chắc chắn không còn thread nào sử dụng.
- Strong global reference giữ sống Java `Class`, có thể khiến class loader không được GC/unload. Vì vậy không nên mặc nhiên trông đợi `JNI_OnUnload` dọn reference đang cản chính quá trình unload.

`JNI_OnUnload` dùng ngữ cảnh loader khác và có thể chạy khi loader gốc không còn tồn tại. Tránh dựa vào việc `FindClass` trong `JNI_OnUnload` vẫn thấy class của plugin.

## 7. Cách chọn class loader tường minh trong JNI

### 7.1. Truyền `Class<?>` hoặc object từ Java

Nếu Java đã biết class mục tiêu, nên để Java truyền chính class object:

~~~java
// Giao diện minh họa, chưa phải chương trình hoàn chỉnh.
public static native void processType(Class<?> type);
public static native void processValue(Object value);

// Gọi từ nơi nhìn thấy đúng class:
processType(plugin.Target.class);
processValue(targetInstance);
~~~

Khi JNI nhận một Java `Class<?>`, native có thể dùng nó như `jclass` để tra method/field đúng kiểu. Nếu nhận object thông thường, `GetObjectClass(env, obj)` trả `jclass` runtime của object đó; không cần `FindClass` bằng tên.

**Lợi ích:** class reference được xác định chính xác theo loader đã tạo đối tượng đó. Không cần đoán tên, loader hoặc dựa vào việc system loader có nhìn thấy nó hay không.

### 7.2. Truyền `ClassLoader` rồi gọi `loadClass`

Nếu runtime cần tìm một class theo tên nhưng loader đúng chỉ được biết ở Java, truyền đối tượng `ClassLoader` vào native và gọi `ClassLoader.loadClass(String)`. Helper C minh họa (giả định `loader` khác null, code phía gọi xử lý Java exception):

~~~c
#include <jni.h>

static jclass load_with_loader(JNIEnv *env, jobject loader) {
    if (loader == NULL) {
        return NULL;
    }

    jclass loader_type = (*env)->GetObjectClass(env, loader);
    if (loader_type == NULL) {
        return NULL;
    }

    jmethodID load_method = (*env)->GetMethodID(
            env,
            loader_type,
            "loadClass",
            "(Ljava/lang/String;)Ljava/lang/Class;");

    (*env)->DeleteLocalRef(env, loader_type);
    if (load_method == NULL) {
        return NULL;
    }

    // ClassLoader.loadClass cần tên dotted.
    jstring name = (*env)->NewStringUTF(env, "plugin.Target");
    if (name == NULL) {
        return NULL;
    }

    jobject result = (*env)->CallObjectMethod(
            env, loader, load_method, name);
    (*env)->DeleteLocalRef(env, name);

    // Trả local reference; NULL có thể kèm Java exception.
    return (jclass) result;
}
~~~

**Phân biệt tên:** `FindClass("plugin/Target")` dùng slash, còn `ClassLoader.loadClass("plugin.Target")` nhận dotted binary name. Descriptor của method Java `ClassLoader.loadClass(String)` là `(Ljava/lang/String;)Ljava/lang/Class;`. Nếu loader không tìm được class, lời gọi Java có thể ném **`ClassNotFoundException`**; `CallObjectMethod` để exception đó ở trạng thái pending.

`ClassLoader.loadClass` không mặc nhiên khởi tạo class ngay. Nếu cần khởi tạo rõ ràng, code Java có thể dùng `Class.forName(name, true, loader)` với loader đã chọn.

### 7.3. Cache global reference, method ID và vòng đời

`jclass` do `FindClass`/`GetObjectClass` trả về là **local JNI reference**. Sau khi native method kết thúc, một local reference chưa được chuyển thành global **không còn hợp lệ** để dùng qua các callback khác.

Để dùng nhiều lần:

1. Lấy `jclass` ở ngữ cảnh loader đúng.
2. Dùng `NewGlobalRef` nếu cần lưu qua các lời gọi hoặc thread.
3. Dùng `GetMethodID`/`GetStaticMethodID` cho **chính class đó**; các method/field ID không phải object references và có vòng đời gắn với class.
4. Khi native worker chắc chắn đã ngừng sử dụng, giải phóng bằng `DeleteGlobalRef`.
5. Trong hệ thống hot reload, đảm bảo ID/reference của loader cũ không bị áp dụng cho class mới cùng tên.

Nếu cần cho phép class loader được GC, có thể thiết kế dùng **weak global reference**, nhưng phải kiểm tra/promote thành local strong reference trước mỗi lần dùng và xử lý tình huống class đã unload. Không coi weak reference là handle luôn còn hiệu lực.

## 8. Danh tính class gồm tên và defining loader

Hai class cùng tên do hai loader **thực sự định nghĩa** là hai kiểu khác nhau:

~~~text
Loader A -- định nghĩa --> plugin.Target --> Class A
Loader B -- định nghĩa --> plugin.Target --> Class B

Class A.getName() == Class B.getName()   // true
Class A == Class B                       // false
~~~

Có thể gặp `ClassCastException`, lỗi tìm method, hoặc nhầm ID khi cache `jclass` của loader A nhưng dùng với object từ loader B. Không chỉ so sánh tên `getName()`; nên kiểm tra **defining loader** và identity của `Class<?>`.

Chú ý **parent delegation**: nếu loader A và B cùng nhờ một loader cha định nghĩa `plugin.Target` thì cả hai có thể trả về **cùng một `Class<?>`**, vì vậy chỉ gọi `loader.loadClass(...)` không chứng minh loader đó thực sự định nghĩa class. Thí nghiệm ở phần 4 sử dụng parent `getPlatformClassLoader()` và application classpath tách biệt để làm rõ điều này.

### 8.1. Native library cũng có ràng buộc class loader

Theo JNI Specification, **cùng một JNI native library** được quản lý theo class loader và không thể tùy tiện nạp vào hai loader khác nhau trong một JVM. Gọi `System.loadLibrary` cho cùng library từ loader khác có thể gây `UnsatisfiedLinkError`. Trong hệ thống nhiều plugin/hot reload, phải thiết kế vòng đời library/loader cùng nhau.

Một kiến trúc thường dễ kiểm soát hơn là để **native bridge trong loader ổn định** và truyền `Class<?>`/`ClassLoader`/object plugin làm tham số rõ ràng, thay vì để nhiều plugin loader cùng nạp một library hoặc để JNI tự suy tên lớp.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `FindClass("com.example.Foo")` trả `NULL` | Sai cú pháp tên JNI | Dùng `"com/example/Foo"` |
| `FindClass` thành công từ native method, thất bại trong attached native thread | Native thread dùng loader khác (thường system loader) | Truyền loader/`Class<?>` hoặc cache global ref từ ngữ cảnh đúng |
| Thành công trong `JNI_OnLoad` nhưng không thấy class về sau | `JNI_OnLoad` có loader của class tải library | Tra trước, quản lý global ref; hoặc dùng loader tường minh |
| Thấy class cùng tên nhưng cast không được | Hai defining loader khác nhau | Kiểm tra `Class.getClassLoader()` và identity |
| `NoClassDefFoundError` | Class/dependency không tìm thấy hoặc class từng khởi tạo lỗi | Xem exception gốc, dependency, loader và classpath |
| `ClassNotFoundException` từ `ClassLoader.loadClass` | Loader được truyền không tải được class | Dùng dotted name đúng; kiểm tra URL/JAR và ủy quyền loader |
| `UnsatisfiedLinkError ... already loaded in another classloader` | Một native library được nạp ở loader khác | Kiểm tra lớp gọi `loadLibrary` và kiến trúc bridge |
| `UnsatisfiedLinkError` khi gọi native method | JNI symbol/prototype sai, không phải lỗi tìm Java class | Sinh lại header `javac -h`, kiểm tra export/ABI |
| Crash sau khi cache `jclass` | Dùng local reference sau lifetime, hoặc native memory/ABI lỗi | Dùng global ref đúng và dừng worker trước khi cleanup |
| `GetMethodID` thất bại dù tên class đúng | Sai tên/descriptor hoặc class thuộc loader khác | Đối chiếu method descriptor, static/instance và class identity |

**Đừng gộp các exception thành một loại:** `FindClass` có thể dẫn tới `NoClassDefFoundError` khi không giải quyết được class, còn gọi trực tiếp `ClassLoader.loadClass` qua JNI có thể làm `ClassNotFoundException` pending. `UnsatisfiedLinkError` nói về nạp/liên kết **native library hoặc native method**, là vấn đề khác.

### 9.1. Quy trình debug có thứ tự

1. Ghi lại chính xác chuỗi `FindClass`, sửa `/`, `$`, array descriptor và chữ hoa/chữ thường nếu sai.
2. Xác định *class nào khai báo native method*, class loader của nó, và thread nơi `FindClass` đang được gọi.
3. Ở Java, in `clazz.getClassLoader()`, `clazz.getName()` và so `clazz == expectedClazz`; kiểm tra classpath/JAR/module layer của plugin.
4. Kiểm tra `FindClass` trả `NULL` và pending Java exception bằng `ExceptionCheck`/`ExceptionOccurred`. Nếu không chủ đích phục hồi, hãy để exception gốc truyền về Java; không `ExceptionClear` vô điều kiện.
5. Kiểm tra dùng `NewGlobalRef`/`DeleteGlobalRef`, `DeleteLocalRef`, đúng `JNIEnv *` theo thread và cache khi unload/reload.
6. Với HotSpot/OpenJDK, bật JNI validation trong lần chạy debug để hỗ trợ phát hiện nhiều lỗi sử dụng JNI:

~~~bash
java -Xcheck:jni -Djava.library.path=. -cp host Launcher
~~~

`-Xcheck:jni` không chứng minh toàn bộ logic class loader đúng và cũng không bắt được mọi lỗi native memory; cần kết hợp log, Java stack trace và kiểm tra loại reference. `ExceptionDescribe` có thể dùng khi debug nhưng có ảnh hưởng tới trạng thái exception; không coi nó là thao tác logging vô hại.

## 10. Các lỗi tư duy cần tránh

1. **Tên đúng là đủ:** `FindClass` còn phụ thuộc loader và tính khả dụng của dependency.
2. **TCCL luôn là loader JNI chọn:** `FindClass` có quy tắc riêng theo native method hoặc Invocation Interface.
3. **Native thread đã attach kế thừa loader của Java caller trước đó:** không có native method context thì không tự kế thừa.
4. **`jclass` là con trỏ sống mãi:** thường nó chỉ là local reference.
5. **Global reference nên giữ đến `JNI_OnUnload`:** strong global có thể ngăn chính loader unload; cần cleanup chủ động.
6. **`JNIEnv *` có thể chia sẻ qua threads:** mỗi thread attach dùng interface pointer của riêng mình.
7. **Tên class giống nhau tức là cùng kiểu:** phải xét defining loader.
8. **`GetObjectClass` và `FindClass` tương đương:** `GetObjectClass` lấy đúng lớp runtime của object đã có, còn `FindClass` tra theo tên và loader.
9. **`ClassLoader.loadClass` nhận tên slash giống JNI:** API Java này nhận tên dotted.
10. **Mọi `NULL` nên clear exception và chạy tiếp:** chỉ clear khi có chiến lược recovery cụ thể.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Java thread gọi `plugin.Bridge.lookupTarget()`, trong khi TCCL là system loader. Nếu `Bridge` do loader P định nghĩa, `FindClass` sẽ dùng loader nào?  
**Đáp án:** P, loader của **class khai báo native method**.

**Câu 2.** Native library tạo thread riêng rồi `AttachCurrentThread`. Vì sao `FindClass("plugin/Target")` có thể thất bại dù class tồn tại?  
**Đáp án:** Không có context native method của plugin; hệ thống dùng loader mặc định của Invocation Interface, thường không thấy plugin riêng.

**Câu 3.** Vì sao không giữ `jclass local = FindClass(...)` trong biến static rồi gọi qua nhiều callback?  
**Đáp án:** Local reference chỉ hợp lệ trong phạm vi của nó; phải chuyển thành global reference nếu cần giữ lâu và có cơ chế release.

**Câu 4.** `FindClass` trong `JNI_OnLoad` và trong `JNI_OnUnload` có dùng cùng loader không?  
**Đáp án:** Không. `JNI_OnLoad` dùng loader của lớp nạp library; `JNI_OnUnload` dùng system class loader.

**Câu 5.** Java đã có `Class<?> pluginType` đúng class plugin. Cách chắc chắn để native dùng class nào?  
**Đáp án:** Truyền chính `pluginType` qua JNI; nếu lưu sau lời gọi, quản lý reference lifetime.

**Câu 6.** Hai lớp `plugin.Target` có cùng tên và bytecode từ hai plugin loaders khác nhau có nhất thiết là cùng kiểu?  
**Đáp án:** Không nếu hai loader khác nhau **định nghĩa** hai class riêng; tên và defining loader cùng xác định danh tính kiểu.

## 12. Tài liệu kỹ thuật đối chiếu

- [Oracle Java SE 17 — JNI Specification: FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): tên lớp, loader được chọn, giá trị trả về và các error.
- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `AttachCurrentThread`, `JNI_OnLoad`, `JNI_OnUnload`, quan hệ native library và loader.
- [Oracle Java SE 17 — JNI Global/Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#global-and-local-references): `NewGlobalRef`, `DeleteGlobalRef`, `DeleteLocalRef`.
- [Oracle Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass` và parent delegation.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): vấn đề `FindClass` từ attached native thread và giải pháp tra/cached class sớm.

**Nguyên tắc ứng dụng:** Trước khi gọi `FindClass`, xác định **nội bộ tên lớp**, **native method hoặc hook/thread đang thực thi**, **loader thực sự sở hữu lớp cần dùng** và **vòng đời của `jclass`**. Khi ngữ cảnh loader không rõ ràng, truyền `Class<?>`/`ClassLoader` từ Java để lựa chọn tường minh.
