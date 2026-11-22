# Static field, cache reflection và tham chiếu từ ứng dụng chủ

> **Java Core → ClassLoader → Dỡ lớp và bộ nhớ.** Trong plugin architecture, không phải cứ gọi `URLClassLoader.close()` là Java classes, static state và Metaspace của phiên bản cũ biến mất. Điều quyết định là **đường tham chiếu mạnh từ GC roots đến loader/classes/plugin objects** còn tồn tại hay không. Bài này phân biệt static field trong plugin với static cache ở ứng dụng chủ, phân tích reflection metadata, `WeakHashMap`, `ClassValue`, TCCL, ThreadLocal và cách cleanup theo vòng đời.

## 1. Tại sao static/cache có thể ngăn class unloading?

Một runtime Java class được nhận diện bằng **binary name + defining class loader**. Plugin V1 và V2 có thể cùng khai báo `plugin.impl.Handler` nhưng là **hai runtime types** nếu được định nghĩa bởi hai plugin loaders riêng. Mỗi type có `Class<?>` mirror, static fields và state riêng.

JLS `12.7` nêu JVM **có thể** unload một class khi và chỉ khi **defining class loader có thể được garbage collector reclaim**. Đây là điều kiện cần cho class unloading, **không phải cam kết GC sẽ xảy ra ngay**.

Có hai đồ thị rất khác nhau:

~~~text
A. CHU TRÌNH BÊN TRONG PLUGIN, KHÔNG CÓ ROOT BÊN NGOÀI

  PluginLoader -> Class<Plugin> -> static INSTANCE
        ^                                |
        +-------- instance/class --------+

  Nếu toàn bộ cụm không reachable từ GC roots:
  tracing GC có thể thu hồi cả cụm; static không tự tạo root.

B. THAM CHIẾU TỪ HOST SỐNG LÂU

  GC root -> Host Class -> static Map<String, Method>
                                  |
                                  +-> Method
                                        |
                                        +-> declaring Class<Plugin>
                                                |
                                                +-> defining PluginLoader

  Root host còn giữ Method => loader V1 còn reachable.
~~~

**Nguyên tắc:** “Có static field” không phải kết luận đủ để gọi memory leak. Cần biết **static field thuộc lớp do loader nào định nghĩa**, giá trị của nó giữ object nào, và **có một GC root bên ngoài generation đã stop trỏ vào cụm này không**.

### 1.1. Thuật ngữ cần phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| GC root | Điểm khởi đầu phân tích reachability của JVM/collector, như live thread frames, runtime roots và reachable static state |
| Strong reference | Tham chiếu khiến referent tiếp tục reachable qua tracing GC |
| Weak reference | Không tự giữ referent sống; được clear khi GC xử lý đối tượng yếu-reachable |
| Defining loader | Loader thực sự định nghĩa runtime Class; ảnh hưởng type identity và unload eligibility |
| Class mirror | Đối tượng `Class<?>` biểu diễn runtime type |
| Metaspace | Bộ nhớ native dùng cho nhiều class metadata trong HotSpot, khác với Java heap |
| Class unloading | VM loại bỏ metadata của runtime classes khi loader eligible và collector thực hiện |
| Resource closing | Đóng JAR/stream/thread/connection theo API lifecycle, **khác** class unloading |

Một live loader không phải leak nếu plugin đang ACTIVE và phục vụ công việc. Leak là loader **đáng lẽ đã được retire** nhưng vẫn bị giữ bởi một root không còn hợp lệ theo lifecycle.

## 2. Static field ở plugin không tự động gây leak

Ví dụ plugin:

~~~java
package plugin.impl;

public final class InternalCache {
    public static final InternalCache INSTANCE =
            new InternalCache();

    private final byte[] data = new byte[4096];

    private InternalCache() {}

    public int bytes() {
        return data.length;
    }
}
~~~

Có một vòng class/static singleton/instance. Nếu không còn bất cứ root ngoài plugin giữ loader, class hay objects của generation, tracing GC có thể thu hồi cả vòng. **Không cần set mọi static field về null chỉ để phá một chu trình**.

Nhưng ngay khi plugin còn active, static map lớn vẫn có thể gây **heap pressure**. Tài nguyên như stream, thread, native handle, DB connection nên close rõ ràng trước khi chấm dứt plugin; không dựa GC để tự đóng.

### 2.1. Khi nào static field ở plugin trở thành vấn đề?

- Một host registry giữ `InternalCache.INSTANCE` trong `Map<String,Object>`.
- Một worker thread do plugin tạo vẫn chạy và giữ plugin `Runnable`/frame/TCCL.
- Plugin đăng ký listener vào **host singleton EventBus**, host nắm callback plugin.
- Một host serializer/DI framework cache `InternalCache.class` hoặc reflection metadata.
- Một global `ThreadLocal`/TCCL của pool worker giữ plugin object/classloader.
- Plugin giữ native resources mà lifecycle `stop` không close.

Không nên thay hết static fields bằng instance fields như một “fix” chung. Nếu instance vẫn được host giữ, classloader vẫn bị pin.

## 3. Static field ở host: nguồn pin loader dễ thấy nhất

Xem một host registry:

~~~java
public final class HostRegistry {
    public static final java.util.Map<String, Object> SERVICES =
            new java.util.concurrent.ConcurrentHashMap<>();

    private HostRegistry() {}
}
~~~

Host class sống xuyên nhiều lần reload V1→V2. Nếu host gọi:

~~~java
HostRegistry.SERVICES.put("plugin-old", pluginInstance);
~~~

thì có chuỗi `host static map → plugin instance → runtime class → defining plugin loader`. Gọi `URLClassLoader.close()` **không loại bỏ** entry này.

Cách xử lý đúng là host xác định ownership: mỗi entry thuộc generation nào, được remove khi nào, ai bảo đảm callback/request cũ kết thúc và có thể thêm lại entry hay không.

**Rủi ro với `static final`:** `final` chỉ khiến reference của `Map` không được gán lại bình thường; **nội dung Map vẫn mutable**. Mặc định Java không tự expire entries theo plugin lifecycle.

### 3.1. Host cache không chứa plugin instance vẫn có thể leak

Ví dụ host chỉ lưu Java reflection:

~~~java
static final java.util.Map<String, java.lang.reflect.Method> METHODS =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

Value `Method` biểu diễn member thuộc một **declaring Class** cụ thể. Có thể đi từ:

~~~java
java.lang.reflect.Method method = METHODS.get("plugin.label");
Class<?> declaring = method.getDeclaringClass();
ClassLoader loader = declaring.getClassLoader();
~~~

Đây là snippet phụ thuộc cache đã có key, không phải Java main độc lập. `Method`, `Field` và `Constructor<?>` có API `getDeclaringClass()`. Do đó host giữ reflection metadata của plugin có thể giữ **Class<?>** và defining loader ngay cả khi host đã bỏ instance plugin chính.

Tương tự những caches quan trọng:

| Value được host giữ | Khả năng liên hệ plugin generation |
| --- | --- |
| `Class<?>` | Định danh runtime type/defining loader |
| `Method` | Declaring class và method signature |
| `Field` | Declaring class và field type |
| `Constructor<?>` | Declaring class và parameter/exception types |
| `MethodHandle` | Target, method type hoặc runtime linkage tới plugin |
| `VarHandle` | Field/access semantics của runtime type |
| `MethodType` | Các `Class<?>` của parameter/return types |
| `MethodHandles.Lookup` | Lookup class/context |
| `Proxy`/generated accessor | Generated classes, interfaces, handler instance |
| `ServiceLoader`/`Provider<?>` | Discovered provider types/instances/cache |
| Captured lambda / `Runnable` | Captured plugin service/handler hoặc code của plugin |

Cần phân tích graph **thực tế** trên JVM khi nghi leak; không khẳng định mọi MethodHandle hoặc every framework cache đều giữ loader vĩnh viễn.

### 3.2. Cache dùng key String có an toàn?

~~~java
Map<String, Class<?>> types;
Map<String, Method> methods;
Map<String, Object> instances;
~~~

**Không tự động an toàn.** Key `String` là value độc lập với plugin class, nhưng **strong value** vẫn có thể trỏ đến plugin. Đổi cache key từ `Class<?>` sang tên class `String` không giải quyết nếu value vẫn giữ reflection object.

Nếu host chỉ cần hiển thị tên và phiên bản plugin, lưu lightweight descriptor:

~~~java
record PluginDescriptor(String id, String version,
                        String implementationName) {}
~~~

Đây là record Java 17 do host định nghĩa. Descriptor chứa strings thuần và không cần giữ `Class<?>` của plugin. Khi thật sự cần execute, resolve đúng instance của **active generation**; không dùng `Class.forName` vô ý trên system loader.

## 4. Thí nghiệm Java 17+: static host cache giữ `Method` sau close

Bài lab độc lập dưới đây dùng một plugin JAR và host program. Code chứng minh những điều có thể dự đoán chắc chắn **không cần `System.gc()`**: cache host vẫn giữ reflection Method, Method dẫn về plugin loader, method đã nạp còn gọi được sau `URLClassLoader.close()`, và entry được xóa khi host remove.

### 4.1. Source plugin

Cây thư mục:

~~~text
reflection-cache-lab/
├── plugin-src/demo/plugin/Feature.java
├── host-src/HostCacheDemo.java
└── build/                 (tạo bởi lệnh bên dưới)
    ├── plugin/
    ├── host/
    └── plugin.jar
~~~

Tệp **`plugin-src/demo/plugin/Feature.java`**:

~~~java
package demo.plugin;

public final class Feature {
    public static final byte[] LOCAL_BUFFER = new byte[1024];

    private Feature() {}

    public static String label() {
        return "hello-from-plugin";
    }
}
~~~

Static `LOCAL_BUFFER` minh họa state của runtime class plugin. Nó không tự biến loader thành GC root thuộc host.

### 4.2. Source ứng dụng chủ

Tệp **`host-src/HostCacheDemo.java`**:

~~~java
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class HostCacheDemo {
    private static final Map<String, Method> HOST_METHODS =
            new ConcurrentHashMap<>();

    private static WeakReference<ClassLoader> loadAndClose()
            throws Exception {
        URL pluginJar = Path.of("build", "plugin.jar")
                .toAbsolutePath().toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[] {pluginJar},
                ClassLoader.getPlatformClassLoader());

        Class<?> type = Class.forName(
                "demo.plugin.Feature", true, loader);
        Method method = type.getMethod("label");

        HOST_METHODS.put("feature.label", method);

        WeakReference<ClassLoader> observer =
                new WeakReference<>(loader);

        // Đóng JAR handles của loader; không xóa loaded Class.
        loader.close();
        return observer;
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> observer = loadAndClose();

        Method cached = HOST_METHODS.get("feature.label");
        ClassLoader owner =
                cached.getDeclaringClass().getClassLoader();

        System.out.println("cache size=" + HOST_METHODS.size());
        System.out.println("method owner matches="
                + (owner == observer.get()));
        System.out.println("invoke after close="
                + cached.invoke(null));

        HOST_METHODS.remove("feature.label");
        System.out.println("cache empty=" + HOST_METHODS.isEmpty());

        // Các biến 'cached' và 'owner' vẫn còn trong scope.
        // Không thể assert loader đã GC chỉ vì map được xóa.
    }
}
~~~

### 4.3. Biên dịch và chạy

Từ root `reflection-cache-lab`, trong POSIX shell (Linux/macOS, Git Bash), JDK 17 trở lên:

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Feature.java
jar --create --file build/plugin.jar -C build/plugin .

javac --release 17 -d build/host \
    host-src/HostCacheDemo.java

# Cố ý không đặt plugin.jar vào host classpath.
java -cp build/host HostCacheDemo
~~~

**Stdout theo cấu hình bài lab**:

~~~text
cache size=1
method owner matches=true
invoke after close=hello-from-plugin
cache empty=true
~~~

Giải thích:

1. `URLClassLoader` có parent là platform loader, nên plugin implementation trong JAR được **plugin loader** định nghĩa, không bị application loader lấy hộ do cùng classpath.
2. `HOST_METHODS` là static map thuộc host class. `Method` cached có `getDeclaringClass()` là `demo.plugin.Feature` của plugin loader.
3. `observer` là **weak reference**, không tự giữ loader. Nhưng `Method` còn trong map và biến local, nên loader vẫn reachable.
4. `Method.invoke(null)` gọi một static method đã được load; `URLClassLoader.close()` không xóa class hiện hữu.
5. `remove` dọn **một root ở host map**, nhưng `cached`, `owner` và local stack vẫn còn references. Không khẳng định unloading đã xảy ra.
6. Nếu static method lần đầu yêu cầu nạp class/resource khác từ JAR sau khi loader close, lời gọi có thể thất bại. Ví dụ này cố ý không phụ thuộc các classes chưa nạp.

Trên Windows, các lệnh tạo thư mục có thể thay bằng PowerShell; không cần đổi classpath separator vì lệnh chạy chỉ có **một entry `build/host`**.

### 4.4. Vì sao không đưa kết quả `WeakReference.get()` sau `System.gc()` vào stdout?

Một `WeakReference<ClassLoader>` chỉ chứng minh tham chiếu đó **không tự ngăn reclaim**. Nếu còn strong root khác, referent có thể tiếp tục sống. Nếu bạn đã xóa mọi root nhưng GC chưa chạy/không chọn unload, `get()` vẫn có thể khác null. Ngược lại, một thí nghiệm bị compiler/JIT tối ưu lifetime của local variables có thể cho kết quả khác bạn dự kiến.

Do đó không có stdout GC-unload cố định cho mọi JVM. Khi kiểm thử, ghi log observer/`ReferenceQueue` trong cửa sổ quan sát, kiểm tra heap roots và chú thích rằng class unloading phụ thuộc collector/runtime.

## 5. `WeakHashMap`: key yếu nhưng value mạnh

Một cách sửa cache quen thuộc:

~~~java
static final java.util.WeakHashMap<Class<?>,
                                  java.lang.reflect.Method> CACHE =
        new java.util.WeakHashMap<>();
~~~

Có thể vẫn giữ loader vì `WeakHashMap` giữ **value bằng strong reference**:

~~~text
Host -> WeakHashMap
        (key) --weak--> PluginClass
        (value) --strong--> Method -> declaring PluginClass
                                     |
                                     +-> PluginLoader
~~~

Value tham chiếu ngược key, nên key vẫn có đường strong reachability qua value. Đây là lỗi được Javadoc `WeakHashMap` cảnh báo: values **không nên giữ keys trực tiếp hoặc gián tiếp** nếu mong entry được tự thu hồi.

Một value chỉ chứa strings/primitives độc lập với plugin classes có thể phù hợp với weak key, nhưng còn phải xử lý việc entry bị GC xóa **không theo thời điểm cố định**. `WeakHashMap` không thread-safe mặc định.

### 5.1. Weak key không phải cơ chế lifecycle

Không thay quy trình stop/unregister bằng niềm tin rằng GC sẽ dọn. Khi đang có request sử dụng provider, việc entry bị xóa ngẫu nhiên có thể ảnh hưởng cache hit rate; khi plugin retire, host cần **deterministic release** các references do mình sở hữu.

Nếu muốn dùng `WeakReference<Method>` làm value, bạn phải xử lý `ref.get()==null` khi truy cập, tính lại metadata và quản lý concurrency. Weak cache là **tối ưu bộ nhớ**, không phải thay toàn bộ cleanup protocol.

## 6. `ClassValue`: per-class metadata cache

Java `ClassValue<T>` sinh ra cho trường hợp cần lưu metadata **theo từng `Class<?>`** mà không tự xây global strong-key map.

Ví dụ Java 17 helper:

~~~java
import java.lang.reflect.Method;

public final class AccessorCache {
    private AccessorCache() {}

    private static final ClassValue<Method> LABEL =
            new ClassValue<>() {
                @Override
                protected Method computeValue(Class<?> type) {
                    try {
                        return type.getMethod("label");
                    } catch (NoSuchMethodException problem) {
                        throw new IllegalArgumentException(problem);
                    }
                }
            };

    public static Method lookup(Class<?> type) {
        return LABEL.get(type);
    }

    public static void evict(Class<?> type) {
        LABEL.remove(type);
    }
}
~~~

Tệp **`AccessorCache.java`** có thể biên dịch với `javac --release 17`; đây là **library class**, không có `main`. Mục tiêu là liên kết computed metadata với class cụ thể và dùng `remove(type)` để xóa association khi cần.

Javadoc `ClassValue` cho biết `computeValue` có thể chạy **nhiều lần** dưới tranh chấp đồng thời, nhưng cơ chế sẽ chọn một value liên kết với `Class` theo contract. Không viết `computeValue` có side effects tài nguyên không idempotent mà không kiểm soát.

**Giới hạn quan trọng:** `ClassValue` không xóa roots khác (host registry, TCCL, event listeners) và không phải `unloadClass`. Nếu value chứa `AutoCloseable`, việc `remove` cũng không đồng nghĩa tự gọi `close()` cho value. Cần owner/lifecycle riêng.

## 7. Một cache có scope theo generation

Nếu host cần lookup method nhiều lần cho một plugin version, thường nên đặt cache **trong đối tượng generation**, thay vì static global:

~~~java
import java.lang.reflect.Method;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class GenerationMethods {
    private final Map<String, Method> methods =
            new ConcurrentHashMap<>();

    void put(String name, Method value) {
        methods.put(name, value);
    }

    Method get(String name) {
        return methods.get(name);
    }

    void clear() {
        methods.clear();
    }
}
~~~

Code biên dịch được nhưng chỉ minh họa cache object, **không chứa lifecycle coordination**. Để dùng trong production cần trạng thái `ACTIVE → DRAINING → CLOSED` và không cho một request V1 thêm Method cũ **sau khi** admin `clear()`.

Sơ đồ race sai:

~~~text
Request V1                           Admin
  giữ Method V1
                                      CACHE.clear()
  CACHE.put("key", Method V1)         close(loader V1)
  -> V1 được cache lại sau cleanup
~~~

`ConcurrentHashMap` chỉ bảo vệ các thao tác map ở mức thread safety, không làm hai hoạt động “clear old generation” và “không cho writer V1 thêm lại” thành một transaction.

Cách sửa: ngăn request mới trên V1, đợi in-flight work hoàn tất (read/write lock hoặc **generation lease/reference counting**), cleanup cache V1, đóng objects/resources, đóng loader, rồi bỏ references cuối.

### 7.1. Dùng generation id để tránh lẫn V1/V2

Nếu bắt buộc host giữ registry global, key nên chứa identity thế hệ **và** scope tenant/plugin, kèm eviction chính xác:

~~~java
record CacheKey(String pluginId, long generation,
                String operation) {}
~~~

Một key tốt **không tự giải phóng value**. Khi generation 42 stop, xóa tất cả entries thuộc generation 42 sau draining; không xóa nhầm 43 vừa publish. Với ứng dụng nhiều threads, đảm bảo iteration/removal và lookup không chạy ngoài lifecycle contract.

## 8. `MethodHandle`, `VarHandle`, proxy và framework cache

Reflection truyền thống không phải nguồn duy nhất:

- `MethodHandle` có thể giữ target hoặc runtime type liên quan tới implementation plugin.
- `VarHandle` có thể gắn với field type và declaring class của plugin.
- `MethodType` có `Class<?>` parameter/return types; một host cache MethodType chứa plugin type có thể pin loader.
- `MethodHandles.Lookup` chứa lookup class/context; giữ nó lâu hơn plugin generation có thể gây retention.
- Generated proxies/bytecode accessors/captured lambdas chứa interfaces, handler hoặc target object thuộc plugin loader.
- Serializer/ORM/DI frameworks cache annotation metadata, property descriptors, builders hoặc supplier của plugin type.
- `java.beans.Introspector` và các framework-specific introspection caches cần được xử lý theo API chính thức khi plugin unload.

Không khẳng định mọi cache do JVM/framework cung cấp đều leak; nhiều cache dùng weak keys hoặc lifecycle scopes phù hợp. **Chỉ khi có root path giữ loader đã retire** mới gọi là leak thực tế. Heap dump/dominator tree có ích hơn đoán dựa trên tên lớp.

## 9. TCCL và ThreadLocal: roots ẩn trong thread pool

Worker thread ở host có thể giữ plugin loader cũ qua `Thread.contextClassLoader` hoặc value của `ThreadLocal` sau khi task plugin kết thúc. Đây là đường `live Thread → plugin state/loader` mà dọn host static cache không xử lý hết.

Khôi phục TCCL bằng `finally`, gọi `ThreadLocal.remove()` tại **đúng worker thread**, và cancel/drain asynchronous tasks trước retire. Bài Thread/ThreadLocal/TCCL có thí nghiệm thread pool riêng.

## 10. Close resources không đồng nghĩa unload class

`URLClassLoader.close()` đóng nguồn class/resource và file handles do nó quản lý; các class, `Method` và instance đã được load vẫn có thể tiếp tục được host giữ. Một host cache còn giữ reflection `Method` sau close là ví dụ điển hình.

Muốn JVM **có cơ hội** unload, cắt các retaining references tới class/defining loader; GC timing là quyết định của VM.

## 11. Quy trình retirement để không để lại roots của V1

**STOP new work → DRAIN current work → UNREGISTER callbacks → CLEAR host caches and generation records → CLEAN TCCL/ThreadLocal → CLOSE owned resources and URLClassLoader → RELEASE strong references**.

Đối với bài này, kiểm tra trọng tâm là cache host không còn entries `Class<?>`, `Method`, `MethodHandle`, proxy hoặc instance thuộc V1, kể cả cache ẩn của framework. `WeakHashMap` cần xem cả value có tham chiếu ngược đến key không; `ClassValue` hoặc per-generation cache có thể phù hợp hơn.

## 12. Chẩn đoán chính xác bằng heap roots và Metaspace

Một sự kiện class unloading tùy thuộc JVM/GC. JLS `12.7` không yêu cầu class unload ngay khi loader đủ điều kiện. Java SE cũng không cung cấp lệnh `ClassLoader.unloadClass("name")`.

Khi nghi retention sau nhiều lần V1→V2:

1. Ghi **generation id/artifact hash/loader identity** ở startup và stop.
2. Đo số active plugins, in-flight calls, host cache entries, TCCL của long-lived workers.
3. Quan sát số classloaders, class count, Metaspace và heap qua nhiều vòng reload; không lấy một thời điểm tăng memory làm bằng chứng.
4. Thu heap dump khi phù hợp vận hành và dùng dominator tree / path to GC root để tìm giữ loader.
5. Ưu tiên đường `Host static Map → Method → Class → Loader`, `Thread → contextClassLoader`, `ThreadLocalMap → value`, `Host EventBus → listener`, `ServiceLoader cache → provider`.
6. Sửa **ownership/eviction/lifetime protocol**, không dùng GC loop như workaround.
7. Chạy lại nhiều vòng, kiểm tra nếu tổng loader count hoặc Metaspace không còn tăng không kiểm soát.

### 12.1. Lệnh hỗ trợ trên HotSpot/JDK tương ứng

~~~bash
java -version

# HotSpot unified logging khi chạy ví dụ:
java -Xlog:class+load=info,class+unload=info \
    -cp build/host HostCacheDemo

# Với process sống lâu, thay PID thật vào vị trí <pid>:
jcmd <pid> help
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace basic
jcmd <pid> Thread.print
~~~

`jcmd` và options phụ thuộc JVM/tool availability; xác nhận thông qua `jcmd PID help`. Heap dump/`GC.class_histogram` có thể gây chi phí stop-the-world, I/O lớn hoặc chứa dữ liệu nhạy cảm; chỉ thực hiện theo chính sách chẩn đoán phù hợp.

### 12.2. Giải thích dấu hiệu cẩn thận

| Dấu hiệu | Điều đã biết | Điều chưa thể kết luận |
| --- | --- | --- |
| Static host map có Method của V1 | Có root đến metadata V1 | Không còn bất kỳ root khác |
| `URLClassLoader.close()` thành công | Loader-owned file handles được cố đóng | Class V1 đã unload |
| `WeakReference.get()!=null` sau `System.gc()` | Loader chưa bị clear lúc quan sát | Chắc chắn leak |
| `WeakReference.get()==null` | Referent bị GC clear theo weak semantics | Tất cả plugin resources đã close |
| Có class unload log | JVM đã unload classes theo implementation | Mọi native/file/socket handle đã giải phóng |
| Metaspace tăng sau một số lượt reload | Có metadata/commit/reservation activity | Nguyên nhân chắc chắn là cache reflection |
| Host Method/Class cache liên tục tăng qua generations | Có retained metadata nghi vấn | Tự biết cache owner mà không kiểm tra heap path |

## 13. Các ngộ nhận thường gặp

1. “Static field của plugin tự nó gây leak.” — **Không nhất thiết** nếu toàn bộ loader graph không có root bên ngoài.
2. “Static final Map ở host không thể giữ thêm entries.” — **Sai**, final chỉ cố định Map reference.
3. “Cache `Method` không giữ plugin instance nên an toàn.” — **Sai**, Method liên quan declaring class.
4. “Dùng String làm cache key sẽ tránh classloader leak.” — **Sai** nếu value giữ `Class<?>`/Method/plugin object.
5. “`WeakHashMap<Class<?>, Method>` tự giải phóng mọi entry.” — **Sai**, value có thể giữ key.
6. “Chuyển sang `ClassValue` là xong mọi memory leak.” — **Sai**, còn host listeners/TCCL/registries.
7. “`URLClassLoader.close()` lập tức unload class.” — **Sai**.
8. “Static state V1 bị reset sau close.” — **Sai**, loaded class vẫn sống khi reachable.
9. “Worker daemon không bao giờ pin plugin loader.” — **Sai**, active thread có thể giữ roots.
10. “`System.gc()` chắc chắn làm loader biến mất.” — **Sai**, không có deadline/guarantee.
11. “Nếu hai classes cùng binary name thì host cache đang trỏ version mới.” — **Sai**, cần so defining loader identity.
12. “`ConcurrentHashMap.clear()` đã atomic với mọi request.” — **Sai**, writer có thể repopulate sau clear.
13. “ServiceLoader.reload() hot-reload bytecode.” — **Sai**, nó reset provider cache của instance hiện tại.
14. “Heap giảm thì Metaspace lập tức giảm.” — **Không chắc**, hai miền memory/GC policies khác nhau.
15. “Một lần class count chưa giảm là JVM vi phạm spec.” — **Sai**, unloading là tối ưu hóa tùy runtime.

## 14. Câu hỏi tự kiểm tra

1. Static `PluginCache.INSTANCE` chỉ tham chiếu nội bộ loader V1 đã retire, không có root ngoài. Nó có **bắt buộc** pin V1 không? **Không**.
2. Một host static `Map<String, Method>` có thể pin plugin loader không? **Có**, qua Method→Class→loader.
3. `WeakHashMap<Class<?>, Method>` có chắc an toàn không? **Không**, value có thể giữ key mạnh.
4. `URLClassLoader.close()` có xóa những `Class<?>` đã loaded không? **Không**.
5. Vì sao phải dừng V1 tasks trước khi clear cache? **Chặn repopulation và tránh dùng resource đã close**.
6. Dùng `WeakReference<ClassLoader>` quan sát, một lần GC không clear có chứng minh leak? **Không**.
7. `ClassValue` dùng để làm gì? **Cache computed metadata theo Class**, không ép class unload.
8. `ThreadLocal.remove()` giúp phòng rò trên pool worker thế nào? **Bỏ value plugin sau scope**.
9. Cache key `String` và value `Class<?>` có an toàn cho hot reload không? **Không khi value giữ V1**.
10. Reflection `Method.getDeclaringClass()` có ý nghĩa gì? **Xác định runtime Class nơi khai báo method**.
11. Heap dump/dominator tree tìm điều gì? **Strong path tới GC root giữ loader**.
12. Khi nào V1 loader còn sống không bị coi là leak? **Khi có request/service V1 active theo lifecycle**.
13. Dùng một classloader mới cho V2 đã loại bỏ mọi root của V1 chưa? **Chưa**, host cache/threads có thể còn giữ V1.
14. `System.gc()` là yêu cầu hay cam kết? **Lời gợi ý/request**, không có guarantee unload tức thì.
15. Static byte array thuộc miền memory nào chủ yếu? **Heap**; class metadata của HotSpot ở Metaspace.

## 15. Tài liệu chuẩn

1. [JLS `12.7` — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): lớp chỉ có thể unload khi defining loader có thể reclaim, và thời điểm do implementation quyết định.
2. [JVMS `5.3` — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime type identity, defining/initiating loader.
3. [ClassLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): delegation, define/load, findLoadedClass.
4. [URLClassLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): close, đã-load classes và JAR/file handles.
5. [Method — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): getDeclaringClass, invoke.
6. [WeakHashMap — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/WeakHashMap.html): weak keys/strong values có thể tham chiếu ngược key.
7. [ClassValue — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassValue.html): computed per-Class cache, get/remove.
8. [WeakReference — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): weak references và GC semantics.
9. [jcmd — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): VM.classloader_stats, VM.classloaders, VM.metaspace.
10. [Thread — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): TCCL và thread lifetime.
11. [ServiceLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider cache/reload.

**Kết luận:** Static fields không đương nhiên gây leak, nhưng **strong reference từ host/GC root tới plugin Class/Method/instance/loader** có thể giữ generation đã retire. Quản lý caches **theo owner/generation**, dừng in-flight work, unregister listeners, restore TCCL, remove ThreadLocal values, close đúng resources và quan sát retained paths. `URLClassLoader.close()` là bước cleanup I/O, **không phải class-unloading API**.
