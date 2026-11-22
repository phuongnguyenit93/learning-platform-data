# Kiểm thử cache không giữ plugin đã hết vòng đời

## 1. Vấn đề: plugin đã dừng nhưng classloader vẫn còn sống

Trong ứng dụng Java tải plugin động (plugin manager, server ứng dụng, công cụ kiểm thử, hệ thống hot reload), mỗi plugin có thể được nạp bằng một `ClassLoader` riêng, chẳng hạn `URLClassLoader`. Khi plugin bị gỡ, ứng dụng thường mong muốn không còn đối tượng, class hay metadata nào của plugin bị giữ bởi mã sống lâu hơn.

Một lỗi phổ biến là **cache reflection trong phần lõi ứng dụng vô tình giữ classloader của plugin**:

```text
GC roots của ứng dụng lõi
  └─ static metadataCache
      └─ Map entry
          ├─ key: Class<?> của plugin ──> defining ClassLoader
          └─ value: Method/Field/Constructor ──> declaring Class ──> ClassLoader
```

Một `Class<?>` được định nghĩa bởi plugin loader gắn với loader đó trong quá trình tồn tại; các đối tượng `Method`, `Field`, `Constructor` hay `MethodHandle` có thể giữ các tham chiếu liên quan tới class/plugin. Khi cache toàn cục giữ những đối tượng này, **`plugin.stop()` hoặc `URLClassLoader.close()` không đủ** để plugin trở nên không còn reachable.

Hệ quả có thể là:

- Số lượng classloader và class đã nạp tăng qua các lượt reload;
- Bộ nhớ metadata/class và heap không trở lại trạng thái ổn định;
- Plugin cũ còn giữ registry, listener hoặc dữ liệu; các bản plugin mới có thể gặp xung đột;
- Hot reload kéo dài dẫn tới tăng bộ nhớ, chi phí GC và lỗi tài nguyên.

Mục tiêu của bài này là **thiết kế kiểm thử xác nhận cache không giữ plugin sau khi kết thúc vòng đời**, đồng thời tránh ngộ nhận rằng chỉ một lần `System.gc()` không thu được classloader là bằng chứng chắc chắn có memory leak.

## 2. Hiểu chính xác “đã hết vòng đời” và “được giải phóng”

Một plugin thường trải qua các bước:

1. **Load**: tạo loader riêng, nạp class, phát hiện metadata, tạo instance và đăng ký dịch vụ.
2. **Use**: gọi plugin, có thể cache `Method`/`Field`/`MethodHandle`/descriptor để tránh scan lặp.
3. **Deactivate**: ngừng nhận yêu cầu mới, đợi tác vụ đang chạy kết thúc và không tạo callback mới.
4. **Cleanup**: unregister listener/service, cancel task, đóng tài nguyên, bỏ cache entries và xóa reference từ host.
5. **Close loader**: đóng `URLClassLoader` khi phù hợp; thao tác này giúp giải phóng resource và ngăn việc nạp từ các URL của loader theo hợp đồng API, nhưng **không cưỡng chế class unloading**.
6. **Observe eligibility**: không còn strong-reference path từ GC roots tới đối tượng classloader/class/plugin.
7. **Eventually collect**: GC *có thể* thu dọn classloader và các lớp liên quan khi chúng không còn reachable; **thời điểm không được cam kết**.

Phân biệt hai mục tiêu kiểm thử:

| Mục tiêu | Phương pháp đáng tin cậy |
| --- | --- |
| Host đã loại bỏ cache entry/registration theo hợp đồng? | Kiểm thử xác định bằng API: `cache.size() == 0`, registry không còn id, task canceled, `close()` được gọi |
| Loader đã trở nên eligible for collection? | Dùng `WeakReference<ClassLoader>`/`ReferenceQueue`, tách scope strong references, kiểm tra trong nhiều chu kỳ |
| Loader đã thực sự bị GC thu gom? | Quan sát `WeakReference.get() == null` hoặc queue event; thường cần thử nhiều lần, kết quả có thể không kết luận |
| Không còn leak trong môi trường thật? | Thử reload nhiều vòng + metrics classloader/class count/heap + profiler/JFR, không dựa vào một phép đo |

**“Không quan sát GC xảy ra” khác “có chứng cứ leak”.** `System.gc()` chỉ là yêu cầu/hint; GC có thể bị cấu hình hạn chế, hoãn hoặc có bộ thu khác nhau giữa JDK. Dùng timeout hợp lý, kết quả *inconclusive* và chẩn đoán reachability nếu cần.

## 3. Cache reflection nào có thể giữ plugin?

### 3.1. Strong-reference cache giữ key hoặc value của plugin

Ví dụ một framework sở hữu classloader lâu dài:

```java
static final java.util.Map<Class<?>, java.lang.reflect.Method> METHOD_CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Nếu key là `pluginClass` thì map giữ class đó mạnh. Nếu value là `Method` khai báo bởi plugin class, value cũng có thể giữ declaring class. Một cache `Map<String, Method>` cũng không an toàn chỉ vì key là `String`: value vẫn giữ method của plugin.

Tương tự, những kiểu metadata khác cần đánh giá:

- `Class<?>`, `Method`, `Field`, `Constructor<?>`, `RecordComponent`;
- `MethodHandle`, `VarHandle`, `MethodHandles.Lookup`, bound handle được `bindTo(pluginInstance)`;
- `MethodType` hoặc schema/descriptor chứa `Class<?>`, annotation instance, accessor lambda;
- `java.beans.BeanInfo`/`PropertyDescriptor` và framework metadata cache;
- `ServiceLoader`, factory, callback/`Runnable`, instance hoặc classloader được lưu trong registry.

Không phải mọi giá trị metadata đều chắc chắn giữ classloader; **phân tích object graph thực tế**. Nhưng coi bất kỳ entry nào có tham chiếu tới `Class<?>` hoặc instance của plugin là có nguy cơ cho tới khi chứng minh lifecycle an toàn.

### 3.2. `WeakHashMap` không tự động giải quyết mọi vòng tham chiếu

Ví dụ thiết kế dễ sai:

```java
Map<Class<?>, Method> cache = new WeakHashMap<>();
cache.put(pluginClass, pluginClass.getMethod("run"));
```

Fragment này cần import `Map`, `WeakHashMap`, `Method` và có `pluginClass`. Dù key là weak, **value `Method` có thể tham chiếu mạnh ngược về declaring class**. Vì `WeakHashMap` vẫn giữ value mạnh, đường `map -> value -> class (weak key)` có thể khiến class sống mãi; key không được dọn như kỳ vọng.

Weak key chỉ có ích nếu cấu trúc value không dẫn ngược về key hoặc loader qua bất cứ strong-reference path nào. Trong thực tế có thể dùng `ClassValue<T>` hoặc explicit eviction theo plugin lifecycle thay vì đoán một map có weak key là đủ.

### 3.3. `ClassValue<T>` cho metadata gắn với vòng đời class

`ClassValue` cung cấp cơ chế lưu một giá trị được tính dựa theo `Class<?>` và được JVM quản lý theo lifecycle của class. Ví dụ:

```java
private static final ClassValue<Method> REFLECTIVE_ADD = new ClassValue<>() {
    @Override
    protected Method computeValue(Class<?> type) {
        try {
            return type.getMethod("add", int.class);
        } catch (NoSuchMethodException e) {
            throw new IllegalStateException(e);
        }
    }
};
```

Đây là **fragment** cần import `java.lang.reflect.Method` và khai báo trong class. Cache gắn với class theo `ClassValue` phù hợp hơn một static strong map có key `Class<?>` cho nhiều trường hợp, đặc biệt hệ thống nạp lớp động.

Nhưng `ClassValue` **không bảo đảm plugin có thể unload** nếu cùng `Method`/plugin instance còn bị giữ ở nơi khác (ví dụ một static registry, listener hay queue). Ngoài ra, `computeValue` có thể chạy nhiều lần trong race; giá trị nên được tính theo cách idempotent và không dựa vào side effect duy nhất. Khi policy metadata thay đổi, cần chiến lược invalidation/`remove(type)` phù hợp.

### 3.4. Cache theo plugin ID và eviction

Nếu host chủ động quản lý vòng đời, một chính sách rõ ràng là cache theo plugin ID/generation và **xóa mọi descriptor gắn với generation tại unload**. Ví dụ:

```java
// Pseudocode minh họa kiến trúc, không phải Java API có sẵn.
onPluginUnload(pluginId) {
    stopNewCalls(pluginId);
    waitForInFlightCalls(pluginId);
    unregisterCallbacks(pluginId);
    reflectionCache.evictAll(pluginId);
    closePluginResources(pluginId);
    closeClassLoader(pluginId);
}
```

Ưu điểm: kiểm thử được eviction một cách **xác định**, không phải đợi GC. Điểm quan trọng là không để một nhiệm vụ async hoặc callback cũ có thể ghi lại cache entry sau khi vừa cleanup. Dùng generation token, trạng thái CLOSED hoặc synchronization phù hợp để ngăn *resurrection* của cache entries cũ.

## 4. Thiết kế một bài kiểm thử đúng

Một test chất lượng gồm cả **negative control** (mẫu cache sai thật sự giữ loader) và **positive case** (cleanup bỏ mọi strong references có thể kiểm soát).

### 4.1. Tạo plugin với loader riêng

Dùng `URLClassLoader` với URL trỏ tới thư mục chứa bytecode plugin và parent phù hợp. Plugin class phải được **định nghĩa thực sự bởi loader riêng**. Nếu chỉ tải `java.lang.String` từ bootstrap/platform loader và gắn `WeakReference` vào một loader rỗng, phép thử không chứng minh gì về metadata plugin.

Có thể tạo một Java source nhỏ, compile vào thư mục tạm bằng `javax.tools.JavaCompiler`, sau đó nạp class bằng `Class.forName(name, true, pluginLoader)`. Dùng `pluginClass.getClassLoader() == pluginLoader` làm assertion trước khi bắt đầu.

### 4.2. Tách scope mạnh khỏi bước quan sát

Trong hàm tạo/plugin-use, các biến cục bộ như `Class<?> pluginClass`, `Method method`, `Object pluginInstance` hoặc `URLClassLoader loader` đều có thể là strong references. JIT có quyền giữ local reachable lâu hơn bạn tưởng.

Vì vậy hãy đặt **tất cả load/use/close trong một hàm helper không inline ở mức thiết kế test** rồi chỉ trả ra `WeakReference<ClassLoader>`; không mang theo `Class<?>` hoặc `Method`. Việc tách hàm giảm nguy cơ chính test tự giữ loader. Đừng lưu plugin object vào trường static của test hoặc lambda callback, đừng ghi instance vào assertion failure message còn sống.

### 4.3. Dùng `WeakReference` và `ReferenceQueue` đúng mục đích

`WeakReference.get() == null` chứng tỏ referent đã được GC xóa weak reference. Khi đăng ký một reference với `ReferenceQueue`, có thể kiểm tra sự kiện enqueue bằng `queue.poll()` hoặc `queue.remove(timeout)`. Đó là **dấu hiệu GC thu dọn**, không phải tín hiệu synchronous từ `ClassLoader.close()`.

Thử nhiều lần có khoảng nghỉ; nếu không quan sát collection, báo *inconclusive* hoặc kích hoạt heap analysis. Không dùng `Thread.sleep(100)` như bằng chứng loader phải biến mất trong 100 ms. Không đặt timeout cực nhỏ khiến CI flaky; cũng không cấp phát vô hạn để “ép GC” đến `OutOfMemoryError`.

### 4.4. Cleanup phải đo được độc lập với GC

Cần assert các sự kiện có tính xác định:

- `cache.size()`/plugin-specific entry count về 0 sau unload;
- registry, listener, command handler, scheduled job, executor/task và callback của plugin được giải phóng;
- không còn thread của plugin hay TCCL (`Thread.contextClassLoader`) trỏ vào loader cũ;
- loader/resource được `close` theo hợp đồng; streams/JAR handles đã đóng;
- nếu có framework global caches, biết rõ cơ chế eviction/hook (ví dụ JavaBeans `Introspector.flushFromCaches(pluginClass)` trong ngữ cảnh thích hợp);
- không còn request in-flight tiếp tục gọi hoặc đăng ký lại listener/cache của plugin vừa unload.

Nếu những assertion này chưa đạt, không cần dựa vào GC để kết luận cleanup đang lỗi.

## 5. Ví dụ Java 17+ hoàn chỉnh: thấy cache sai giữ loader và dọn cache

Ví dụ dưới đây compile một plugin Java nhỏ **ngay trong thư mục tạm**, nạp bằng `URLClassLoader`, gọi method qua reflection, cố tình lưu `Class<?> -> Method` trong static cache **sai** để thể hiện đường strong reference, rồi xóa cache. Sau đó chương trình chỉ *thử quan sát* GC.

> Chạy bằng **JDK**, không phải JRE rút gọn, vì cần `ToolProvider.getSystemJavaCompiler()`. Chương trình tạo và xóa thư mục tạm trong quá trình chạy; không tải plugin từ mạng.

Lưu thành **`PluginCacheLifecycleDemo.java`**:

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class PluginCacheLifecycleDemo {
    // CỐ TÌNH SAI: host cache giữ mạnh cả Class lẫn Method của plugin.
    static final Map<Class<?>, Method> BAD_CACHE = new ConcurrentHashMap<>();
    static final ReferenceQueue<ClassLoader> QUEUE = new ReferenceQueue<>();

    // Trả ra CHỈ weak ref. Mọi strong ref tạm được giữ trong scope này.
    static WeakReference<ClassLoader> loadUseAndClose() throws Exception {
        Path root = Files.createTempDirectory("plugin-classloader-test-");
        Path javaFile = root.resolve("demo/Plugin.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile,
            "package demo; public class Plugin {"
            + " public Plugin() {}"
            + " public String hello() { return \"hello\"; }"
            + " }");

        try {
            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Please run on a full JDK");
            }

            int exit = compiler.run(null, null, null,
                "--release", "17", "-d", root.toString(), javaFile.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compile error: " + exit);
            }

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {root.toUri().toURL()},
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> plugin = Class.forName("demo.Plugin", true, loader);
                if (plugin.getClassLoader() != loader) {
                    throw new AssertionError("Plugin must use its own loader");
                }
                Method method = plugin.getMethod("hello");

                // Tạo đường tham chiếu mạnh: BAD_CACHE -> Class/Method -> loader.
                BAD_CACHE.put(plugin, method);

                Object instance = plugin.getConstructor().newInstance();
                System.out.println("plugin call: " + method.invoke(instance));
                return new WeakReference<>(loader, QUEUE);
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path :
                        paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    static boolean observeCollection(WeakReference<ClassLoader> ref)
            throws InterruptedException {
        for (int i = 0; i < 15; i++) {
            System.gc(); // Hint, KHÔNG bảo đảm chạy GC ngay.
            if (ref.get() == null || QUEUE.poll() == ref) {
                return true;
            }
            Thread.sleep(80);
        }
        return ref.get() == null;
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> reference = loadUseAndClose();

        System.out.println("bad cache size: " + BAD_CACHE.size());
        System.out.println("loader reachable via bad cache: "
                + (reference.get() != null));

        // Cleanup bắt buộc: entry thuộc plugin phải được evict.
        BAD_CACHE.clear();
        System.out.println("bad cache empty after cleanup: "
                + BAD_CACHE.isEmpty());

        boolean collected = observeCollection(reference);
        System.out.println("GC: " + (collected
                ? "collected (observed)"
                : "not observed (inconclusive)"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PluginCacheLifecycleDemo.java
java PluginCacheLifecycleDemo
```

Ba dòng đầu và dòng cleanup có kết quả xác định trong trường hợp biên dịch/nạp plugin thành công:

```text
plugin call: hello
bad cache size: 1
loader reachable via bad cache: true
bad cache empty after cleanup: true
```

Dòng cuối phụ thuộc thời điểm GC. Hai kết quả có thể xảy ra:

```text
GC: collected (observed)
```

hoặc:

```text
GC: not observed (inconclusive)
```

**Không coi nhánh thứ hai là test failure chắc chắn.** Kết quả chứng minh một phần quan trọng: khi `BAD_CACHE` còn entry, loader vẫn reachable thông qua cache; sau `BAD_CACHE.clear()`, đường tham chiếu cụ thể đó đã bị loại bỏ. Cần quan sát các đường tham chiếu khác của một ứng dụng thật nếu loader vẫn tồn tại qua nhiều lần GC.

Tại sao demo dùng `ClassLoader.getPlatformClassLoader()` làm parent? Class `demo.Plugin` không phụ thuộc class của host, và parent platform không có định nghĩa `demo.Plugin`; nhờ đó plugin class chắc chắn được định nghĩa trong loader riêng. Hệ thống thật có thể chọn parent khác để chia sẻ API plugin, nhưng phải bảo đảm không vô tình load plugin implementation từ loader cha.

Điểm giới hạn của demo: `BAD_CACHE.clear()` xóa **toàn bộ** cache giả lập cho một plugin. Trong hệ thống đa plugin, chỉ evict entries thuộc đúng plugin generation; không xóa metadata của plugin khác. Và `QUEUE` minh họa queue sự kiện weak ref; không phải cần thiết để xác nhận cache entry đã bị evict.

## 6. Viết test regression chắc chắn, tránh flaky GC test

Nên chia test thành hai tầng.

### Tầng A — Kiểm thử cleanup xác định (bắt buộc)

Tạo fake plugin với một ID hoặc generation rõ ràng. Thực hiện lần lượt:

1. Đăng ký service, tạo cache entries bằng reflection, tạo listener/task đã biết.
2. Xác minh trong trạng thái ACTIVE, các entries cần dùng có tồn tại.
3. Gọi `stop/unload`; chờ các tác vụ in-flight hoàn tất theo hợp đồng.
4. Assert cache không còn entries của **đúng plugin generation**.
5. Assert registry/listener/thread/task đã được unregister/cancel; loader đã đóng khi áp dụng.
6. Assert API không chấp nhận thêm call/cache write sau trạng thái CLOSED.
7. Nạp plugin thế hệ mới có cùng tên class và cùng plugin ID; đảm bảo metadata thế hệ cũ không bị tái sử dụng.

Đây là bài kiểm thử không cần ép GC; nó nên chạy ổn định trong CI ở mọi JDK được hỗ trợ.

### Tầng B — Kiểm thử quan sát loader collection (diagnostic/integration)

- Tạo classloader riêng và plugin class thật, dùng `WeakReference<ClassLoader>`; có thể bổ sung weak refs tới `Class<?>` hay plugin instance, nhưng **không giữ mạnh** các referent đó trong test.
- Chạy load/unload nhiều vòng, helper riêng cho mỗi vòng.
- Sau cleanup, yêu cầu GC theo chu kỳ **giới hạn** và lấy kết quả từ weak refs/`ReferenceQueue`.
- Nếu có weak ref bị clear, đó là bằng chứng collection đã được quan sát cho referent ấy.
- Nếu không clear, phân loại **không kết luận**, thu heap dump/đồ thị dominator để tìm root pinning; không mặc định “leak”.
- Dùng workload lặp và classloader metrics để tìm xu hướng retention lâu dài, không suy từ một điểm đo.

Một test chạy trên JUnit có thể dùng `assertTimeout` hoặc cơ chế deadline cho pha chờ **giữ ổn định thời gian kiểm thử**, nhưng tuyệt đối không ép việc GC phải xảy ra trước deadline trong môi trường mà JVM không hứa hẹn điều đó. Nếu sản phẩm có yêu cầu giải phóng tài nguyên định lượng, xác minh tài nguyên có hợp đồng release rõ ràng (đóng file descriptor, unregister listener, số cache entries) trước; kiểm chứng class unloading qua integration metrics riêng.

### Negative control: xác nhận test có thể nhận ra leak thật

Trong một lượt test được cách ly:

- Giữ `Class<?>` hoặc `Method` của plugin trong static cache host;
- Sau khi helper trả về chỉ weak ref, xác minh strong cache còn entry và `weak.get() != null`;
- Xóa entry đó, kiểm tra `cache.isEmpty()`;
- Sau đó **có thể** chờ/quan sát GC.

Với negative control này, bạn chứng minh bộ kiểm thử nhìn thấy ít nhất một đường retention xác định. Nếu chỉ test bản “tốt” mà không có mẫu rò rỉ có chủ ý, chưa chắc helper quan sát/cleanup đã được thiết kế đúng.

## 7. Những nguồn giữ classloader nằm ngoài cache reflection

Ngay cả khi metadata cache được thiết kế hợp lý, plugin vẫn có thể bị giữ bởi:

| Nguồn tham chiếu | Cách phát sinh | Hướng xử lý |
| --- | --- | --- |
| Static registry trong host | `Map<String, PluginHandler>` lưu instance/plugin callback | Unregister theo plugin generation |
| Executor/Thread đang chạy | Runnable/lambda nắm `pluginInstance`/`ClassLoader` | Stop và join/chờ task; loại references trong queue |
| Thread context classloader (TCCL) | Thread host gọi `setContextClassLoader(pluginLoader)` rồi không khôi phục | Dùng `try/finally` để khôi phục TCCL; dừng plugin threads |
| `ThreadLocal` | Thread sống lâu giữ value thuộc plugin | Gọi `remove()` trên đúng thread hoặc quản lý vòng đời thread |
| Listener/MBean/observer | Host event bus giữ listener class của plugin | Unregister theo token rõ ràng |
| Scheduler, timer, callback | Job tương lai capture plugin object | Cancel; loại queue entry và chặn re-registration |
| JavaBeans metadata | `Introspector` hoặc framework cache giữ `BeanInfo`/descriptor | Xem API flush/invalidation, ví dụ `Introspector.flushFromCaches(clazz)` khi phù hợp |
| Service discovery | `ServiceLoader`/factory giữ provider instances hoặc loader | Giải phóng loader/provider và cache liên quan |
| Logging / tracing / metrics | Logger appender, instrumentation hoặc exporter giữ callback/class | Remove registrations khi plugin stop |
| JNI/native handles/file resources | Native code/JAR handle giữ tài nguyên | Đóng đúng tài nguyên, giải phóng registration theo API native |

Một static field **nằm trong chính class plugin** không tự tạo GC root bên ngoài plugin nếu toàn bộ loader/class của nó đã unreachable; rủi ro là tham chiếu từ **host/JDK thread/registry sống lâu** dẫn ngược vào plugin. Khi điều tra, luôn hỏi “GC root nào đang giữ đường mạnh tới loader?”.

### Ví dụ khôi phục TCCL an toàn

```java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Tác vụ ngắn hạn cần loader của plugin.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
```

Fragment trên cần biến `pluginLoader` hợp lệ. Đây là hygiene cho các thread tái sử dụng từ pool. Nó không thay thế việc stop các thread thực sự được plugin tạo ra. Khi dùng thread pool, cần quản lý cả `Runnable`/`Callable` đang nằm trong queue.

## 8. Thiết kế cache cho nhiều plugin, classloader và hot reload

### Key phải phân biệt phiên bản plugin

Cùng tên fully qualified class, ví dụ `com.example.Plugin`, có thể được định nghĩa bởi **hai classloader khác nhau**. Ở Java, identity của class liên quan đến *binary name + defining classloader*. Vì vậy cache theo **string class name** đơn thuần có thể trả metadata cũ sai classloader sau reload.

Nếu cache theo tên, hãy gắn thêm plugin generation/classloader identity bằng một khóa có lifecycle quản lý chặt chẽ; đồng thời evict khi unload. Tránh lưu key strong-ref classloader vĩnh viễn vào global cache.

### Cache data “safe” vẫn có thể bị một value pinning

Một wrapper `CachedAccessPlan` có thể tưởng chỉ giữ tên/kiểu dưới dạng text, nhưng một field ẩn như `Method getter`, `Class<?> type`, `MethodHandle access` hay `Supplier<?> lambda` có thể giữ plugin. Kiểm tra object graph của **value**, không chỉ kiểu key.

### Dọn cache dưới concurrency

Plugin có thể bị unload đúng lúc request khác đang dùng cache:

1. Chuyển plugin sang trạng thái `STOPPING` để chặn cấp phiên gọi mới.
2. Đợi/hủy request in-flight theo hợp đồng.
3. Xóa metadata/registry/task đã thuộc generation đó.
4. Đóng tài nguyên/loader.
5. Đặt `CLOSED`; mọi lookup muộn của generation cũ phải bị từ chối.

Nếu chỉ gọi `cache.remove(key)` rồi một worker còn chạy lại `computeIfAbsent` và tạo entry mới, plugin cũ bị giữ lại. Kiểm thử race cần dùng barrier/latch điều phối một request đang lookup, đồng thời stop plugin; cuối test bảo đảm **không có repopulation**.

### Bảo vệ reference qua nhiều bản JDK

Nhiều bản JDK có thể thay đổi nội bộ reflection, GC và class unloading. Đừng dùng một magic threshold hoặc suy đoán cache internal `Method` để xác nhận unload. Kiểm thử trên JDK mục tiêu (ít nhất version được support) với assert dựa trên **public lifecycle contract**, kết hợp quan sát `WeakReference`/JFR/heap analysis. Đặc biệt khi nâng JDK, cache dùng internal accessor của JDK là thiết kế dễ vỡ.

## 9. Công cụ chẩn đoán khi loader chưa biến mất

Khi tích hợp reload nhiều vòng mà số loader/class không ổn định:

1. Ghi số plugin generations đã đóng, cache entries theo generation, thread/task/registry còn hoạt động.
2. Thử bật Unified Logging về class unload nếu cần: `-Xlog:class+unload=info` (trên HotSpot hỗ trợ cú pháp này). Log sự kiện class unload chỉ khi nó thật sự xảy ra, không phải cam kết thời điểm.
3. Dùng JFR hoặc heap dump và công cụ phân tích dominator paths để tìm **GC root → host cache/registry/thread → plugin classloader**.
4. Kiểm tra static map `Class<?> -> Method`, `WeakHashMap` có value tham chiếu key, `ClassValue` bị external leak, thread context loader, `ThreadLocal`, scheduled executors.
5. Xác định object thực sự đang bị giữ: loader, `Class<?>`, plugin instance, metadata/handle, thread hay resource. Một heap snapshot đơn lẻ cần được đọc cẩn thận; số classloaded cao có thể do workload hoặc GC chưa chạy.
6. Loại bỏ một strong-reference path, chạy lại chuỗi test tương đương; so sánh metrics và object graph. Tránh thay nhiều yếu tố cùng lúc rồi không còn biết nguyên nhân.

Khi phân tích đồ thị, nhớ rằng **một classloader có thể chứa nhiều lớp**; việc thấy một loader còn sống có thể giữ lại lượng lớn metadata dù chỉ một listener hoặc một `Method` bị cache sai.

## 10. Lỗi thường gặp và câu hỏi tự kiểm tra

- **“`URLClassLoader.close()` đã gọi, vậy class chắc chắn unload”:** sai; `close()` giải phóng tài nguyên loader nhưng không xóa các strong references hiện có.
- **“`System.gc()` một lần không thu gom thì chắc chắn memory leak”:** sai; GC không cam kết thời điểm.
- **“`WeakHashMap<Class<?>, Method>` là an toàn vì key weak”:** sai nếu value `Method` giữ class/key.
- **“`ClassValue` sửa mọi leak”:** sai khi listener, registry, thread hoặc một cache khác vẫn giữ plugin.
- **“Cache class name là đủ để phân biệt plugin sau reload”:** sai vì cùng tên class có thể đến từ hai loader khác nhau.
- **“Một lần xóa cache entry là xong dù plugin đang chạy song song”:** sai nếu task muộn có thể tạo lại entry.
- **“Chỉ đo heap usage ngay sau stop”:** chưa đủ; heap memory khác metaspace và còn phụ thuộc GC, allocation pressure, classloader count, JIT warm-up.
- **“Test giữ biến `Class<?>`/`Method` ngoài scope rồi chờ GC”:** chính test có thể là nguồn giữ plugin và tạo false positive.

Tự kiểm tra:

1. Static cache của host lưu `Method` khai báo trong plugin; plugin đóng URLClassLoader nhưng method vẫn trong cache. Có nguy cơ giữ loader không? **Có**: metadata có thể giữ declaring class và loader.
2. Cần test chắc chắn không flaky trong CI: dùng gì trước? **Assert eviction/unregistration/stop chính xác**, rồi quan sát GC ở tầng integration riêng.
3. `weak.get() != null` sau 100 ms có chứng minh leak? **Không**.
4. Dùng `WeakHashMap<Class<?>, Method>` có đủ an toàn không? **Không**, phải xét đường tham chiếu từ value về key.
5. Reload hai plugin class cùng tên nhưng khác loader: identity class có giống nhau không? **Không**.
6. Nếu cache đã xóa mà classloader vẫn sống, cần điều tra gì? **Các GC roots khác:** thread/TCCL, ThreadLocal, listener, task, service registry, framework cache và object graph.
7. Một request đang chạy có thể thêm cache entry của plugin `CLOSED` sau cleanup. Kiểm thử gì? **Race test với generation token/barrier**, đảm bảo không thể repopulate entry.

Đọc thêm từ API chuẩn:

- [`java.lang.ref.WeakReference` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html)
- [`ReferenceQueue` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html)
- [`ClassValue` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html)
- [`URLClassLoader.close` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [`java.util.WeakHashMap` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html)
- [`Introspector.flushFromCaches` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html#flushFromCaches(java.lang.Class))
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html)
