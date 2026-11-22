# Quan hệ giữa tham chiếu JNI, GC và khả năng dỡ lớp trong Java

## 1. Ba vòng đời liên quan nhưng không đồng nhất

Một chương trình Java dùng JNI có thể giữ đối tượng Java ở phía C/C++, trong khi ứng dụng lại muốn GC thu hồi object và dỡ những class của plugin để tiết kiệm bộ nhớ hoặc triển khai phiên bản mới. Muốn dự đoán hệ quả chính xác, phải phân biệt ba vòng đời:

1. **Đối tượng Java (object lifetime):** Garbage Collector (GC) xác định object nào còn reachable thông qua các gốc tham chiếu (GC roots), gồm cả tham chiếu JNI hợp lệ. Object không còn được giữ mạnh *có thể* được thu hồi theo chính sách GC.
2. **Class và class loader (class unloading):** Một class Java được định danh bởi *tên nhị phân + defining class loader*. Theo Java Language Specification (JLS `12.7), class chỉ **có thể** được dỡ khi defining loader có thể được GC thu hồi. Ngay cả khi đủ điều kiện, JVM không bắt buộc dỡ class ngay.
3. **Thư viện JNI native (native-library unloading):** Với thư viện JNI động nạp thông qua `System.loadLibrary`/`System.load`, JVM quản lý thư viện theo class loader. JNI quy định thư viện có thể được dỡ khi loader chứa nó bị GC; hook `JNI_OnUnload` (nếu được export) được gọi trong quá trình đó. Đây không phải một API “dỡ ngay” mà ứng dụng có thể gọi theo yêu cầu.

Mối liên hệ là **JNI reference mạnh có thể giữ Java object hoặc `Class` còn sống → giữ class loader liên quan còn sống → làm class không đủ điều kiện unload → gián tiếp trì hoãn việc dỡ thư viện JNI thuộc loader**. Việc bỏ biến Java hay gọi `System.gc()` không phá được một tham chiếu mạnh còn giữ tại phía native.

Điểm then chốt: ***đủ điều kiện để GC/unload* khác với *đã được GC/unload***. Viết code hoặc kiểm thử dựa vào thời điểm dỡ class chính xác là sai giả định về hợp đồng Java/JNI.

## 2. GC nhìn thấy những reference JNI nào?

`jobject`, `jclass`, `jstring`, `jarray` là các **JNI object reference** do JVM quản lý, không phải địa chỉ Java object ổn định. JVM dùng chúng để theo dõi khả năng reachability, kể cả khi GC di chuyển object trong heap. Không được cast reference thành con trỏ C rồi giả định đó là vị trí heap của object.

| Loại JNI reference | Cách tạo thường gặp | Giữ object khỏi GC? | Phạm vi, giải phóng |
| --- | --- | --- | --- |
| **Local reference** | Tham số object của native method, `FindClass`, `GetObjectClass`, `NewLocalRef` | **Có**, khi còn hợp lệ | Gắn với native frame/thread; thường tự giải phóng lúc native method return; có thể gọi `DeleteLocalRef` sớm |
| **Global reference** | `NewGlobalRef` | **Có**, đến khi xóa global ref | Dùng qua nhiều JNI calls và trên nhiều attached threads theo quy tắc đồng bộ; **phải** `DeleteGlobalRef` |
| **Weak global reference** | `NewWeakGlobalRef` | **Không**; referent có thể bị GC thu hồi | Có thể dùng để theo dõi object mà không giữ mạnh; cần `DeleteWeakGlobalRef` để giải phóng bản thân handle |
| **`jmethodID`/`jfieldID`** | `GetMethodID`/`GetFieldID` và biến thể static | **Không phải object reference, không giữ class khỏi unload** | Có hiệu lực khi defining class còn được load; vô hiệu sau khi class bị unload |

Một local reference tồn tại đến cuối native call vẫn có thể làm object không bị GC thu hồi, dù trong code C đã không còn đọc tới biến đó. Vì vậy, trong vòng lặp dài, gọi `DeleteLocalRef` ngay khi đã xử lý xong object sẽ giảm áp lực GC và số lượng JNI handles.

Ví dụ đối tượng đi qua native call:

```text
Java stack / Java heap / JNI roots
             │
             ├─ Java local / field / array element ──► Object X
             │
             ├─ JNI local ref (trong native frame) ───► Object X
             │
             ├─ JNI global ref (đến khi Delete) ─────► Object Y
             │
             └─ JNI weak global ref - - - - - - - - -> Object Z
                                          không giữ mạnh
```

Sơ đồ thể hiện quan hệ tham chiếu, không phải định dạng vật lý mà HotSpot hay một JVM cụ thể buộc phải dùng. `NULL` hoặc reference đã xóa không phải một GC root hợp lệ. Native pointer `malloc` riêng không tự trở thành Java root; nếu C cần giữ Java object, phải dùng JNI reference đúng loại.

### 2.1. Local reference: giữ object khi native frame đang hoạt động

```c
/* Fragment C JNI: env hợp lệ trên thread hiện tại. */
jclass cls = (*env)->GetObjectClass(env, obj);
if (cls == NULL) {
    return; /* Có thể có Java exception pending. */
}

/* ... sử dụng cls ... */

(*env)->DeleteLocalRef(env, cls);
```

`cls` là local `jclass` tới Java `Class` object. Trong thời gian local ref hợp lệ, nó là tham chiếu mạnh. Khi xóa ref, điều đó **không có nghĩa object `Class` bị dỡ ngay**: object/class có thể còn nhiều đường strong reachability khác.

Không được cache `cls` trong một biến static C để dùng sau khi method kết thúc: khi local ref hết hạn, giá trị đó không còn là JNI reference hợp lệ. Đối với native thread đã attach, local ref cần được quản lý trong phạm vi attach/local frame; `PushLocalFrame`/`PopLocalFrame` cũng giúp xác định rõ lifetime.

### 2.2. Global reference: nguồn giữ sống kéo dài

```c
/* Fragment C: obj là local/global ref hợp lệ, khác NULL. */
jobject kept = (*env)->NewGlobalRef(env, obj);
if (kept == NULL) {
    return; /* Nếu hết bộ nhớ, có thể đang có OOME pending. */
}

/* kept tiếp tục giữ Java object còn reachable. */

/* Khi không còn cần giữ object: */
(*env)->DeleteGlobalRef(env, kept);
kept = NULL;
```

Một global reference là strong root **kể cả khi phía Java không còn biến nào trỏ đến object**. `DeleteGlobalRef` chỉ giải phóng một reference; nếu còn reference mạnh khác, object vẫn sống. Nếu hết toàn bộ strong refs, object trở thành ứng viên cho GC, không nhất thiết bị thu hồi ngay.

**Quy tắc quản lý:** mỗi lần tạo global ref phải có người sở hữu, điểm giải phóng, và chính sách tránh double-delete hoặc use-after-delete. Không thể gọi `free(kept)` để xóa một JNI reference.

### 2.3. Weak global reference: không giữ object sống

```c
/* Fragment: obj là JNI object reference hợp lệ. */
jweak weak = (*env)->NewWeakGlobalRef(env, obj);
if (weak == NULL) {
    return; /* NULL do đầu vào null hoặc lỗi cấp phát. */
}

/* weak không tự ngăn GC thu hồi referent. */

/* Cleanup handle, dù referent đã bị GC thu hồi: */
(*env)->DeleteWeakGlobalRef(env, weak);
```

Khi referent đã bị GC thu hồi, weak global reference trở nên có hiệu lực như `NULL`. `IsSameObject(env, weak, NULL)` có thể kiểm tra trạng thái tại một thời điểm, nhưng GC có thể chạy ngay sau phép kiểm tra. Nếu cần **dùng object** sau đó, trước hết hãy promote sang một strong local reference:

```c
/* Fragment an toàn cho việc dùng tiếp referent của một jweak
   còn hợp lệ. */
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong != NULL) {
    /* Object được giữ mạnh trong phạm vi strong ref hợp lệ. */
    /* ... sử dụng strong ... */
    (*env)->DeleteLocalRef(env, strong);
} else {
    /* Referent có thể đã bị thu hồi; đồng thời kiểm tra
       exception pending nếu thao tác cấp phát thất bại. */
}
```

**Không sử dụng `jweak` như một cách “ghi nhớ object vĩnh viễn nhưng không tốn bộ nhớ”.** Khi referent mất đi, việc dereference qua weak ref không còn an toàn; khi weak handle không cần nữa cũng phải xóa.

## 3. Từ JNI reference đến điều kiện class unloading

Class Java không chỉ là mã nguồn trên đĩa. JVM tạo metadata cho class, gắn class với defining loader, và có một đối tượng `java.lang.Class` đại diện cho class đó. Class loader đóng vai trò định danh loại class trong JVM; ví dụ hai loader khác nhau có thể tạo ra hai class đều tên `plugin.Widget` nhưng **không cùng kiểu**.

Xét một hệ thống plugin:

```text
GC root: JNI global reference
          │
          ▼
java.lang.Class object: plugin.Widget
          │
          ▼
Class metadata / defining loader relationship
          │
          ▼
PluginClassLoader (L)
          │
          ▼
Các class khác do L định nghĩa
```

Nếu code native tạo global ref tới `Class<?>` của `plugin.Widget`, class đó vẫn cần còn tồn tại; loader định nghĩa class ấy không thể được coi là một loader đã có thể bị thu hồi để dỡ class. Cùng hiệu ứng có thể xảy ra khi native giữ global ref tới **một instance** của class plugin, vì instance đang sống cần class của nó tồn tại.

Ngoài ra, chuỗi reachability có thể đi theo đường khác:

```text
GC root: thread / static registry / JNI global reference
                   │
                   ▼
        plugin instance / callback
                   │
                   ▼
      plugin class và defining loader
```

Vì vậy, khi một ứng dụng server “đóng plugin” nhưng memory usage tiếp tục tăng sau nhiều lần deploy, nguyên nhân không nhất thiết là bug của GC. Có thể plugin loader **vẫn còn reachable** thông qua global JNI ref, thread context class loader, thread đang chạy code plugin, listener, cache Java, hoặc callback chưa hủy.

### 3.1. Điều kiện cần, không phải lời hứa tự động

JLS `12.7 nêu rằng một class/interface **chỉ có thể bị unload nếu defining class loader của nó có thể bị GC thu hồi**. Các class của bootstrap loader không được unload theo quy tắc đó. Việc unload là một tối ưu có tính trong suốt; ứng dụng không được giả định JVM sẽ unload đúng lúc, hoặc thậm chí sẽ chọn unload trong một khoảng thời gian đoán trước.

Để một loader tùy biến như `URLClassLoader` có cơ hội được thu hồi, thực tế cần phá các đường reachability giữ class, instance, metadata và loader liên quan còn sống; những đường này có thể gián tiếp qua **JNI strong references**.

Phân biệt các thao tác:

| Thao tác | Thực sự có nghĩa gì? | Có bảo đảm class unload ngay? |
| --- | --- | --- |
| `DeleteLocalRef` | Bỏ một local JNI reference trong native frame | Không |
| `DeleteGlobalRef` | Bỏ một strong global JNI reference | Không |
| `DeleteWeakGlobalRef` | Bỏ weak JNI handle, không nhất thiết tác động đến referent | Không |
| `URLClassLoader.close()` | Đóng tài nguyên file/JAR để tải class mới theo hợp đồng loader | Không |
| Bỏ biến Java trỏ đến loader | Bỏ một đường strong reference, các đường khác có thể vẫn tồn tại | Không |
| `System.gc()` | Đề nghị JVM thực hiện GC; JVM có quyền không thực hiện theo mong muốn | Không |
| JVM GC thực sự xác định loader có thể thu hồi | Có thể giải phóng loader và unload class theo chính sách VM | **Không có lịch biểu bảo đảm cho ứng dụng** |

**Một vòng tham chiếu nội bộ không tự nó làm object sống mãi.** Ví dụ static field của class plugin trỏ tới một singleton plugin, singleton lại trỏ về loader: nếu toàn bộ nhóm không còn đường từ GC roots, GC vẫn có thể thu hồi nhóm ấy. Điểm cần điều tra là **đường từ root bên ngoài** như JVM thread sống lâu, registry của application hoặc JNI global ref.

### 3.2. `jmethodID` và `jfieldID` không phải global reference

Mã native thường cache kết quả của `GetMethodID` và `GetFieldID`:

```c
/* Fragment: clazz là jclass hợp lệ. */
jmethodID mid =
        (*env)->GetMethodID(env, clazz, "execute", "()V");
```

Một `jmethodID` không phải `jobject`, **không thể truyền vào `NewGlobalRef` để biến thành reference mạnh**, và **không tự ngăn JVM unload class**. Sau khi class bị unload, ID trước đó không còn hợp lệ. Nếu cần dùng ID qua nhiều vòng đời, phải giữ một reference sống tới underlying class trong đúng phạm vi, hoặc tra cứu lại ID cho class mới sau reload.

Giữ một global `jclass` để bảo đảm ID sống sẽ đổi lấy việc **chặn class unloading**. Thiết kế cache phải lựa chọn có chủ đích: cache cố định theo process (và chấp nhận loader tồn tại), hoặc cache theo plugin lifecycle có lệnh teardown rõ ràng.

## 4. Ví dụ Java 17+ và JNI C: global `jclass` giữ class loader

Ví dụ sẽ làm rõ quan hệ reachability mà không dựa vào việc `System.gc()` có chạy hay không. Một class `host.NativeRoots` do application loader định nghĩa nạp JNI library **một lần**; class `plugin.Widget` do loader tạm thời định nghĩa. Native code tạo **global `jclass`** trỏ tới `plugin.Widget` và lưu trong biến static C.

Điều quan trọng là **thư viện JNI thuộc loader của host**, còn class plugin thuộc loader khác. Bằng cách đó, ví dụ tập trung vào đường giữ sống do global reference, không nhầm với vòng đời native library gắn với loader của plugin.

Cấu trúc tệp:

```text
project/
├── src/
│   ├── host/
│   │   ├── NativeRoots.java
│   │   └── Demo.java
│   └── plugin/
│       └── Widget.java
├── native/
│   └── native_roots.c
└── build/               # được tạo bởi lệnh biên dịch
```

### 4.1. Lớp khai báo JNI trong host

**Tệp `src/host/NativeRoots.java`:**

```java
package host;

public final class NativeRoots {
    static {
        System.loadLibrary("native_roots");
    }

    private NativeRoots() {
    }

    public static native void hold(Class<?> type);

    public static native boolean holds(Class<?> type);

    public static native boolean hasRoot();

    public static native void release();
}
```

`Class<?>` được truyền xuống JNI dưới dạng `jclass`. Trong ví dụ, `hold` chỉ được gọi với class khác null. Để code dễ kiểm chứng, ví dụ chỉ chạy trên một thread; ứng dụng thực cần đồng bộ thao tác thay/xóa reference nếu nhiều thread cùng truy cập native cache.

### 4.2. Plugin được tải bằng một loader riêng

**Tệp `src/plugin/Widget.java`:**

```java
package plugin;

public final class Widget {
    public String message() {
        return "Hello from plugin";
    }
}
```

Không đưa `build/plugin` vào application classpath khi chạy driver: thư mục ấy chỉ được cấp cho `URLClassLoader` của plugin.

### 4.3. Driver tạo plugin loader, sau đó chỉ giữ weak reference tới loader ở Java

**Tệp `src/host/Demo.java`:**

```java
package host;

import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Demo {
    private static WeakReference<ClassLoader> install(Path pluginDir)
            throws Exception {

        URL[] urls = {pluginDir.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader())) {

            Class<?> type = Class.forName(
                    "plugin.Widget", true, loader);

            NativeRoots.hold(type);
            System.out.println(
                    "JNI holds plugin class: " + NativeRoots.holds(type));

            return new WeakReference<>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: host.Demo <plugin-class-directory>");
        }

        WeakReference<ClassLoader> loaderRef =
                install(Path.of(args[0]).toAbsolutePath());

        try {
            System.out.println(
                    "JNI global root exists: " + NativeRoots.hasRoot());
            System.out.println(
                    "Plugin loader reachable: " +
                    (loaderRef.get() != null));
        } finally {
            NativeRoots.release();
        }

        System.out.println(
                "JNI global root after release: " + NativeRoots.hasRoot());
    }
}
```

`Class.forName(..., true, loader)` buộc class được định nghĩa bởi loader plugin (vì `build/plugin` không có trên application classpath và không chứa trong platform loader). Phương thức `install` kết thúc, nên các biến local Java của nó không còn được sử dụng; driver chỉ giữ một `WeakReference` tới loader.

Sau khi `NativeRoots.hold(type)` chạy thành công, global JNI reference tới `plugin.Widget.class` giữ class và defining loader còn sống. `URLClassLoader.close()` trong `try-with-resources` đã đóng tài nguyên tìm kiếm của loader, nhưng **không xóa global JNI ref**.

### 4.4. Triển khai native với global reference và cleanup

**Tệp `native/native_roots.c`:**

```c
#include "host_NativeRoots.h"

/* Ví dụ chỉ gọi từ một thread; production cần đồng bộ. */
static jclass held_class = NULL;

JNIEXPORT void JNICALL Java_host_NativeRoots_hold(
        JNIEnv *env, jclass ignored, jclass type) {
    (void)ignored;

    /* type phải là non-null hợp lệ theo contract của ví dụ. */
    jclass replacement =
            (jclass)(*env)->NewGlobalRef(env, type);

    if (replacement == NULL) {
        /* Nếu lỗi cấp phát, trả về với exception pending. */
        return;
    }

    if (held_class != NULL) {
        (*env)->DeleteGlobalRef(env, held_class);
    }
    held_class = replacement;
}

JNIEXPORT jboolean JNICALL Java_host_NativeRoots_holds(
        JNIEnv *env, jclass ignored, jclass type) {
    (void)ignored;

    if (held_class == NULL) {
        return JNI_FALSE;
    }
    return (*env)->IsSameObject(env, held_class, type);
}

JNIEXPORT jboolean JNICALL Java_host_NativeRoots_hasRoot(
        JNIEnv *env, jclass ignored) {
    (void)env;
    (void)ignored;
    return held_class != NULL ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_host_NativeRoots_release(
        JNIEnv *env, jclass ignored) {
    (void)ignored;

    if (held_class != NULL) {
        (*env)->DeleteGlobalRef(env, held_class);
        held_class = NULL;
    }
}
```

**Giải thích:** `NewGlobalRef` tạo một strong JNI reference mới. `IsSameObject` kiểm tra đúng danh tính `Class` object thay vì so hai giá trị handle `jclass`. `DeleteGlobalRef` kết thúc việc giữ object của native cache và đưa con trỏ C về `NULL` để tránh dùng lại reference đã xóa.

Lưu ý về lỗi: nếu `NewGlobalRef` thất bại vì thiếu bộ nhớ, nó có thể trả `NULL` với `OutOfMemoryError` pending; khi đó driver Java nhận exception và không có stdout thành công như bên dưới. Code minh họa không triển khai các tình huống `hold(null)` và truy cập đồng thời; khi đưa vào production hãy kiểm tra input và quản lý mutex/ownership.

### 4.5. Biên dịch/chạy trên Linux

Đứng tại thư mục `project`, dùng JDK 17 trở lên và GCC/Clang. `JAVA_HOME` phải là thư mục JDK có `include/jni.h`.

```bash
mkdir -p build/host build/plugin build/headers

javac -h build/headers -d build/host \
  src/host/NativeRoots.java \
  src/host/Demo.java

javac -d build/plugin src/plugin/Widget.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_roots.c -o libnative_roots.so

java -Djava.library.path=. -cp build/host \
  host.Demo build/plugin
```

**Stdout mong đợi** (không ép GC; Java/JNI code hoàn thành bình thường):

```text
JNI holds plugin class: true
JNI global root exists: true
Plugin loader reachable: true
JNI global root after release: false
```

Dòng cuối chỉ xác nhận **global reference của ví dụ đã được xóa**; nó không xác nhận class hay loader đã unload. Có thể vẫn còn tham chiếu mạnh hoặc JVM chưa thực hiện class unloading. Để chủ động quan sát GC, có thể thêm thử nghiệm riêng sau `release` bằng `System.gc()` và đọc `loaderRef.get()`; kết quả **không ổn định theo lần chạy và không nên viết một expected stdout cố định**.

Trên JDK áp dụng chính sách native access mới, tùy cách đóng gói và phiên bản JDK có thể cần `--enable-native-access=ALL-UNNAMED` cho code trên classpath. Tùy chọn này **không thay đổi GC rooting hay class unloading**. Trên Windows/macOS phải build lại thư viện native với tên đuôi và JNI include của nền tảng tương ứng.

## 5. Tại sao xóa global ref vẫn chưa đủ để đảm bảo unload?

Một global reference là **một** cạnh trong đồ thị reachability. Xóa nó không bảo đảm những cạnh khác cũng bị xóa. Ví dụ:

```text
Host static Map<String, Object> registry
                 │
                 ▼
       plugin callback object
                 │
                 ▼
          plugin class
                 │
                 ▼
        PluginClassLoader
```

Dù native code đã `DeleteGlobalRef`, host registry vẫn giữ callback, nên plugin loader còn sống. Tương tự, một thread vẫn chạy trong code plugin hoặc `Thread.contextClassLoader` còn tham chiếu tới loader cũ có thể giữ nó alive.

Những đường giữ sống cần xem xét gồm:

- **JNI:** global `jobject`/`jclass` chưa giải phóng; local ref của một native call kéo dài; callback từ C giữ đối tượng Java; attached native threads vẫn tạo/giữ references qua JNI.
- **Java application:** cache/static registry do class trong loader sống lâu định nghĩa, listener, scheduled task, executor, MBean, logging registry, reflection `Class<?>`/`Method`/`MethodHandle`; các object plugin vẫn còn được giữ.
- **Threads:** task chưa hoàn thành, thread đang chạy code plugin, thread context class loader, `ThreadLocal`/inheritable values còn chứa plugin object.
- **Native resources:** native heap allocations, file descriptors, callbacks và threads phía C cần cleanup, dù chúng không tự động là Java GC roots nếu không có JNI reference hoặc Java object giữ chúng.

Một điểm đáng chú ý: **chỉ việc có `malloc` buffer phía C không ngăn Java object bị GC**. Native raw pointer không được coi là Java reference. Ngược lại, nếu buffer chứa một số được ép từ `jobject` rồi dùng như reference sau này, đó là lỗi JNI, không phải kỹ thuật giữ object hợp lệ.

### 5.1. Về cache ID và class loader

`jmethodID` và `jfieldID` là token định danh method/field do JNI trả về; **bản thân chúng không ngăn class unload**. Nếu lưu chúng lâu hơn vòng đời class mà không giữ strong class reference, sau khi class bị unload ID trở thành không hợp lệ. Nếu giữ strong global `jclass` cho cache, bạn sẽ làm class/loader vẫn sống cho đến khi cleanup. Cần định nghĩa vòng đời cache theo đúng lifecycle của plugin.

Đặc biệt tránh một cache native **toàn cục cho cả JVM** dùng key chỉ là class name. Hai class cùng tên trong hai loader khác nhau vẫn là hai kiểu khác nhau. Bất kỳ cache `jclass`, ID hay callback nào cũng phải phân biệt defining loader và có bước hủy khi plugin rời hệ thống.

## 6. Class unloading và native-library unloading là hai sự kiện khác nhau

**Class unloading** là JVM giải phóng phần biểu diễn runtime của class khi JVM cho phép và điều kiện GC phù hợp. **Native library unloading** là quá trình JVM quản lý module JNI do một loader sở hữu và giải phóng module đó khi vòng đời loader cho phép. Chúng có quan hệ qua loader nhưng không phải thao tác giống nhau.

JNI quy định **mỗi class loader quản lý thư viện JNI riêng và cùng một JNI native library không thể cùng lúc nạp vào nhiều loader**; nạp lại từ loader khác khi thư viện đã thuộc loader trước có thể gây `UnsatisfiedLinkError`. Nếu loader cũ được GC thu hồi, library của loader ấy *có thể* được dỡ theo cơ chế JVM, nhưng không có lệnh `System.unloadLibrary()` công khai để ép sự kiện ngay lập tức.

### 6.1. `JNI_OnLoad` và `JNI_OnUnload`

Với thư viện động, JNI hỗ trợ hai hook tùy chọn:

```c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Cleanup native đơn giản trong ngữ cảnh không xác định. */
}
```

Đây là **fragment độc lập minh họa hai hook**, không phải mã triển khai đầy đủ của `native_roots.c` ở phần 4. `JNI_OnLoad` được gọi khi VM nạp thư viện JNI. `JNI_OnUnload` được gọi khi loader chứa native library bị GC, nếu thư viện cung cấp hook. JNI specification cảnh báo callback unload có thể chạy trong ngữ cảnh không xác định; cần hạn chế sử dụng JVM services và tránh tùy tiện gọi ngược Java.

**Không dùng `JNI_OnUnload` làm bước cleanup duy nhất của nghiệp vụ.** Nếu global reference hoặc thread của ứng dụng giữ loader sống mãi, hook unload có thể không bao giờ xảy ra trong vòng đời quan sát của process. Nếu native data cần được giải phóng khi plugin disabled, hãy cung cấp API `close()/dispose()/release()` explicit và thực hiện cleanup trước khi bỏ loader.

Trong ví dụ phần 4, thư viện `native_roots` thuộc **application loader**, do đó ngay cả khi plugin loader sau này được GC, **không suy ra rằng `libnative_roots.so` sẽ unload**. Đây là khác biệt quan trọng giữa một reference giữ class và library ownership.

### 6.2. Những giả định dễ sai

- **“Đóng `URLClassLoader` là dỡ toàn bộ class.”** `close()` chỉ đóng nguồn dữ liệu và tài nguyên mà loader quản lý; class đã load có thể tiếp tục được sử dụng.
- **“Xóa `jclass` bằng `DeleteGlobalRef` là hủy class.”** Nó chỉ bỏ một reference. Class vẫn có thể được sử dụng từ Java, native frame hoặc root khác.
- **“`System.gc()` bảo đảm giải phóng Metaspace.”** Đó là lời đề nghị GC; class unloading phụ thuộc JVM/GC, reachability và tùy chọn runtime.
- **“Đã không còn instance Java nên class chắc chắn unload.”** Còn `Class<?>` global ref, reflection cache, method handle, class loader reference hoặc class khác dùng nó vẫn có thể giữ loader.
- **“`jmethodID` cache tự giữ class.”** ID không phải strong Java object reference; nếu class unload, ID không còn hợp lệ.
- **“Thấy memory native tăng là class loader leak.”** Có thể là global JNI ref leak, JNI local table tăng, buffer `malloc` chưa free, direct buffers, JIT/code cache, OS library mapping hoặc các nguyên nhân khác. Cần đo đúng loại bộ nhớ.

## 7. Thiết kế teardown để plugin có cơ hội được unload

Với ứng dụng có thể nạp/bỏ plugin nhiều lần, thiết kế vòng đời nhất quán sẽ quan trọng hơn một lệnh “force GC”:

1. **Dừng hoạt động:** ngăn request mới, hoàn tất hoặc hủy task đang chạy; ngăn native callback mới truy cập plugin.
2. **Hủy đăng ký với host:** gỡ listener, event handler, scheduler, registry, cache, MBean và thread-local data do host giữ.
3. **Dừng native work:** dừng native worker thread, đợi callback đang thực thi kết thúc; với native thread attach vào JVM, detach đúng lúc. Không để `JNIEnv *` của một thread bị dùng trên thread khác.
4. **Giải phóng references:** `DeleteGlobalRef` cho strong global roots, `DeleteWeakGlobalRef` cho weak handles; xóa cache `jclass`/method IDs theo vòng đời plugin.
5. **Giải phóng tài nguyên native:** đóng file/socket, trả `malloc` buffers, release JNI array elements/critical regions đúng API; không trộn `free` với JNI reference deletion.
6. **Đóng loader và bỏ strong references:** `URLClassLoader.close()` khi phù hợp, sau đó bỏ object/class/loader references còn giữ ở host.
7. **Quan sát GC/class unloading:** dùng công cụ chẩn đoán để tìm root còn sống; không xem một lần GC không unload là bằng chứng chương trình sai.

Trật tự phải tuân theo concurrency: **không xóa global ref khi thread khác còn sử dụng nó mà chưa có cơ chế sở hữu/đồng bộ**. Cần có giao thức “stop → drain callbacks → release handles → release loader”, nhất là khi JNI callback quay lại Java bất đồng bộ.

Nếu yêu cầu vận hành đòi hỏi **dỡ thư viện C/C++ tại thời điểm chính xác**, tách native worker vào một process riêng và restart process đó thường tạo ranh giới vòng đời rõ ràng hơn. Class unloading trong JVM không được thiết kế làm cơ chế hot swap mã native có thời hạn cứng.

## 8. Cách kiểm tra trong thực tế

### 8.1. Theo dõi class loader mà không giữ mạnh nó

`WeakReference<ClassLoader>` phía Java có thể dùng để quan sát xem loader còn strongly reachable hay đã bị GC thu hồi. Tuy nhiên, không được giữ biến `Class<?>` hoặc plugin instance trong chính công cụ đo quá lâu; các biến ấy có thể vô tình ngăn unload.

```java
import java.lang.ref.WeakReference;

// Fragment: loader là một custom ClassLoader đã tồn tại.
WeakReference<ClassLoader> watch = new WeakReference<>(loader);

// Sau khi cleanup toàn bộ strong references, tại một thời điểm:
boolean alreadyCollected = watch.get() == null;
```

Đoạn trên **không phải chương trình độc lập** và không yêu cầu JVM đã GC. Nếu `watch.get() != null`, loader có thể còn root hoặc đơn giản chưa được GC thu hồi. Nếu `watch.get() == null`, object loader đã bị thu hồi trong lần quan sát đó, nhưng không suy ra thời điểm library ở mức OS đã được unmap.

### 8.2. Kiểm tra qua công cụ JVM

Trên HotSpot/JDK hỗ trợ, có thể:

```bash
# Quan sát sự kiện dỡ class (khi JVM thực sự thực hiện).
java -Xlog:class+unload=info -cp build/host \
  -Djava.library.path=. host.Demo build/plugin

# Trên tiến trình JVM đang chạy (thay PID thực tế):
jcmd <PID> VM.classloader_stats
```

Mã `<PID>` là **placeholder của dòng lệnh**, không nhập cả dấu ngoặc nhọn vào shell. Các tùy chọn `-Xlog`/`jcmd` và định dạng đầu ra là chi tiết của HotSpot/JDK, không phải API đảm bảo mọi JVM đều giống nhau.

Bài demo kết thúc nhanh và không chủ động chạy GC, nên không thấy class-unload log là điều bình thường. Khi chẩn đoán plugin leak thật, hãy đặt tải thử có nhiều vòng đời plugin, quan sát số lượng loader/class theo thời gian và kết hợp heap dump/GC roots analysis; không chỉ dựa trên một con số Metaspace.

Ngoài ra có thể dùng `-Xcheck:jni` (JVM hỗ trợ) để phát hiện nhiều lỗi dùng JNI reference; JNI checking giúp tìm bug, nhưng không thể thay thế phân tích đường strong reachability.

### 8.3. Nhìn dấu hiệu để định vị lỗi

| Dấu hiệu | Kiểm tra ưu tiên |
| --- | --- |
| Nhiều `PluginClassLoader` cũ còn sống sau redeploy | Host registry, listener, class cache, thread context loader, JNI `NewGlobalRef` chưa delete |
| JVM báo lỗi khi load cùng JNI library từ loader mới | Library đang thuộc loader cũ; phân biệt với classloader leak và chính sách nạp JNI |
| Java heap tăng dù plugin idle | Global refs tới plugin objects, native threads giữ local refs lâu, host caches |
| Metaspace tăng khi reload plugin nhiều lần | Loader/class không đủ điều kiện unload hoặc JVM chưa thực hiện class unloading |
| Native memory tăng nhưng Java heap ổn định | `malloc`, JNI resources, direct buffers, thư viện C/C++ và các loại native allocations khác |
| `JNI_OnUnload` không xuất hiện | Loader sở hữu thư viện có thể vẫn sống hoặc chưa GC; hook không có/không thuộc đúng library |

**Không thể chẩn đoán chắc chắn chỉ từ một dấu hiệu.** Điều quan trọng là xác định root thực sự đang giữ một object/loader; với native references, cần quan sát bằng công cụ hỗ trợ JNI handles/heap roots và kiểm tra ownership trong code.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Java đã bỏ mọi biến trỏ tới đối tượng `plugin.Widget`, nhưng JNI vẫn có `jobject cached = NewGlobalRef(env, widget)`. Object có đủ điều kiện GC chưa?  
**Đáp án:** Chưa, vì global JNI reference còn giữ mạnh object. Tham chiếu ấy có thể gián tiếp giữ defining class loader của plugin.

**Câu 2.** Chuyển global ref thành weak global ref có tự động bảo đảm class unload không?  
**Đáp án:** Không. Weak ref không giữ mạnh referent, nhưng class/loader có thể còn các strong roots khác và JVM không bắt buộc unload ngay sau khi đủ điều kiện.

**Câu 3.** `DeleteGlobalRef` được gọi xong, vậy `JNI_OnUnload` chắc chắn chạy trước khi function return?  
**Đáp án:** Không. Xóa một reference không phải một yêu cầu unload. `JNI_OnUnload` gắn với thời điểm VM GC class loader **sở hữu thư viện native**, và library phải định nghĩa hook đó.

**Câu 4.** Một C static cache chỉ lưu `jmethodID`, không lưu `jclass`. Điều này có giữ class không unload?  
**Đáp án:** Không. `jmethodID` không phải root. Khi class unload, ID không còn hợp lệ và không được dùng lại cho class mới sau reload.

**Câu 5.** Vì sao `URLClassLoader.close()` chưa đủ để giải phóng plugin?  
**Đáp án:** Nó chỉ đóng tài nguyên loader quản lý. Những class/instance/callback/global JNI refs đã tồn tại vẫn có thể còn reachable và giữ loader sống.

**Câu 6.** Muốn dùng object chỉ được lưu bằng `jweak` trong một native callback, nên làm gì?  
**Đáp án:** Tạo strong local reference bằng `NewLocalRef`, kiểm tra null/exception, thao tác qua strong ref, rồi `DeleteLocalRef`. Chỉ kiểm tra `IsSameObject(weak, NULL)` trước đó không bảo vệ object khỏi GC race.

**Câu 7.** Nếu native library được nạp từ application loader nhưng giữ global `jclass` của plugin loader, việc dỡ plugin loader sẽ đồng nghĩa native library unload chứ?  
**Đáp án:** Không. Cleanup global `jclass` chỉ loại một lý do khiến plugin loader sống. Library thuộc application loader có vòng đời riêng, thường kéo dài tới khi JVM kết thúc.

## 10. Ghi nhớ

- JNI local/global references có thể hoạt động như **strong GC roots**; weak global refs thì không giữ object còn sống.
- Một **global `jclass` hoặc `jobject` của plugin** có thể giữ defining class loader còn sống, ngăn class unloading.
- `jmethodID`/`jfieldID` là ID, **không phải object roots**; ID trở nên không hợp lệ sau class unload.
- **Bỏ một reference ≠ thu hồi object ≠ dỡ class ≠ dỡ thư viện native**. Đó là các mốc vòng đời khác nhau.
- Class unloading chỉ có thể diễn ra khi defining loader có thể được GC thu hồi, và JVM giữ quyền quyết định khi nào unload.
- Thiết kế plugin teardown phải đồng thời cleanup Java callbacks, threads, JNI strong/weak refs, native handles và caches. Đừng ép GC như một cơ chế quản lý tài nguyên.
- `JNI_OnUnload` xảy ra theo vòng đời loader sở hữu thư viện JNI động; cần cleanup chủ động ngay khi ngừng plugin, thay vì đợi hook này.

### Tài liệu chính thức

- [Oracle JNI Design Overview — Referencing Java Objects, Local/Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): các JNI reference giữ object và tính hợp lệ của method/field IDs.
- [Oracle JNI Functions — Local, Global, Weak Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `NewLocalRef`, `NewWeakGlobalRef`, `DeleteWeakGlobalRef`.
- [Oracle JNI Invocation API — Library Lifecycle and JNI_OnUnload](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): native library thuộc loader và vòng đời native library khi loader GC.
- [Java Language Specification — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): điều kiện cần để class unloading diễn ra.
- [Java SE 17 API — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()): giới hạn của hành vi đóng loader.
