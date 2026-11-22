# Listener, registry, ServiceLoader cache và nguyên nhân giữ plugin trong bộ nhớ

## 1. Vấn đề: plugin đã dừng nhưng ClassLoader vẫn còn sống

Một hệ Java plugin thường tạo một **ClassLoader riêng** để nạp implementation và dependencies. Khi plugin bị gỡ (unload/undeploy/redeploy), host có thể ngừng phục vụ request và gọi `URLClassLoader.close()`, nhưng bộ nhớ dành cho plugin **không nhất thiết được giải phóng**.

Nguyên nhân thường không phải JVM “quên unload class”, mà là **một hoặc nhiều tham chiếu còn giữ object/plugin class/ClassLoader ở trạng thái reachable**:

- Listener của plugin vẫn được đăng ký trong registry sống lâu của host.
- Plugin instance còn nằm trong list/map singleton, event bus, callback table.
- Một `ServiceLoader` được lưu trong cache host vẫn giữ loader/provider metadata và các instance đã được duyệt.
- Thread pool worker giữ `Thread Context ClassLoader (TCCL)` trỏ vào plugin loader.
- Executor, timer, thread, shutdown hook hoặc `ThreadLocal` vẫn giữ object/class thuộc plugin.
- Cache chứa `Class<?>`, reflection `Method`, `Constructor`, `MethodHandle`, lambda/proxy hoặc object được định nghĩa bởi plugin loader.
- Một resource khác (JDBC driver, MBean, logger/handler, scheduled job...) còn được đăng ký với một thành phần sống lâu.

**Trọng tâm bài học:** hiểu **đường tham chiếu mạnh** (strong reference path) từ GC roots đến plugin, phân biệt **stop**, **close**, **dereference** và **class unloading**, rồi thiết kế quy trình cleanup có thể xác minh.

Bài viết phù hợp Java 17+, có ví dụ chạy được về **listener registry + ServiceLoader cache**, ví dụ giới hạn của `reload()`, hướng nhận diện leak bằng JVM tooling và checklist redeploy an toàn.

## 2. Bốn khái niệm khác nhau của vòng đời

**Stop plugin** ngừng xử lý và hủy đăng ký nghiệp vụ; **`URLClassLoader.close()`** đóng class/resource source và JAR handles do loader quản lý; **GC eligibility** phụ thuộc loader generation còn reachable từ roots hay không; **class unloading** là quyết định của JVM khi điều kiện phù hợp.

Đối với `ServiceLoader`, gọi `reload()` làm sạch provider cache của chính `ServiceLoader` đó nhưng không xóa các provider instances được giữ ở host registry khác. Bài này tập trung vào ownership của listener/registry/provider caches.

## 3. ClassLoader, Class và object giữ nhau như thế nào?

Plugin instance, `Class<?>`, listener object hoặc ServiceLoader provider vẫn có thể dẫn về runtime type và **defining loader** của plugin. Ví dụ `host event bus → listener instance → runtime class → plugin loader`.

Vì JVM định danh class thông thường bằng `(binary name, defining loader)`, hai plugin versions có thể giữ hai runtime classes cùng tên khác nhau. Chỉ khi các registrations và references còn được host giữ bị xóa, defining loader cũ mới có cơ hội được reclaim.

## 4. Listener và callback registry là nguồn giữ plugin điển hình

Một event bus thường có API:

```java
public interface Listener {
    void onEvent(String message);
}
```

Đây là interface mẫu có thể đặt trong `Listener.java`. Host có thể giữ:

```java
// Trích đoạn: event bus thuộc một class do loader host định nghĩa.
private static final java.util.List<Listener> LISTENERS =
        new java.util.concurrent.CopyOnWriteArrayList<>();

public static void register(Listener l) {
    LISTENERS.add(l);
}

public static void unregister(Listener l) {
    LISTENERS.remove(l);
}
```

Nếu plugin gọi `register(new PluginListener())` mà không bao giờ gọi `unregister`, `LISTENERS` giữ object plugin. Khi host `ClassLoader` sống suốt JVM, registry thường vẫn reachable qua class/field của host.

**Cơ chế leak không phụ thuộc listener có đang nhận event hay không.** Chỉ cần reference vẫn nằm trong collection.

### Lambda và method references cũng là callbacks

Ví dụ:

```java
// Trích đoạn: eventBus là đối tượng host sống lâu, plugin là plugin instance.
eventBus.subscribe(event -> plugin.handle(event));
```

Lambda có thể capture `plugin` trong object callback. Host chỉ thấy một `Consumer<Event>`/interface chung, nhưng callback giữ object plugin phía sau. Tên class runtime của lambda có thể không giống `PluginListener`, khiến heap dump khó đọc hơn.

Tương tự, `plugin::handle` là method reference có thể giữ receiver `plugin`. Một callback chỉ tồn tại trong host registry **vẫn có thể giữ cả loader của plugin**.

**Thiết kế API tốt:** `subscribe` trả một đối tượng `AutoCloseable`/`Subscription` để plugin manager có thể hủy đăng ký dứt khoát:

```java
// Trích đoạn thiết kế API:
interface Subscription extends AutoCloseable {
    @Override
    void close();
}

Subscription subscription = eventBus.subscribe(listener);
try {
    // plugin hoạt động
} finally {
    subscription.close();
}
```

Đây là **trích đoạn** vì `eventBus`, `listener` và overload `subscribe` do ứng dụng định nghĩa. Trong hệ bất đồng bộ, `unsubscribe` chỉ loại bỏ callback khỏi danh sách tương lai; những event đã được dispatch hoặc task in-flight vẫn cần được chờ hoàn tất trước khi đóng loader.

## 5. Registry và singleton cache ở loader cha

Một host thường có:

```java
// Trích đoạn trong host class:
private static final java.util.Map<String, Object> PLUGINS =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Nếu `PLUGINS.put("alpha", pluginInstance)`, sau `plugin.stop()` nhưng không `remove("alpha")`, loader plugin có thể còn sống.

Các biến thể dễ bị bỏ sót:

- `Map<String, Class<?>>` lưu provider class để reflection tạo object sau.
- `Map<String, Method>` lưu method reflective trên class plugin.
- `List<Runnable>` lưu callbacks capture plugin.
- Cache framework lưu metadata về annotation, generated proxy, method handles, serializer, mapper, DI providers.
- `ThreadLocal` của một thread pool host lưu object thuộc class plugin.
- Cache giữ `ServiceLoader<?>` trỏ tới explicit plugin ClassLoader.
- Registry JDBC driver hoặc MBean server thuộc phần runtime sống lâu giữ implementation do plugin định nghĩa.

### Cẩn trọng với các reference gián tiếp

Không chỉ xem collection có chứa **ClassLoader** trực tiếp hay không. Một entry có kiểu `Object`, `Runnable`, `Listener` hay `Supplier<?>` cũng có thể giữ **object được định nghĩa bởi plugin loader**, rồi từ đó giữ runtime class/loader.

Một `static Map` nằm **trong class host/common loader** có thể giữ plugin qua nhiều lượt deploy. Một `static Map` chỉ nằm trong plugin class không nhất thiết sống lâu hơn loader nếu không có reference path từ bên ngoài.

Khi phân tích heap dump, đi từ **GC roots** tới loader bị nghi ngờ, xem **retaining/dominator path**, không chỉ tìm “class nào có static field”.

## 6. ServiceLoader cache giữ provider như thế nào?

`java.util.ServiceLoader<S>` tìm các implementations của service interface hoặc abstract class từ:
- `META-INF/services/<service-binary-name>` trong classpath/unnamed modules;
- `provides ... with ...` trong module descriptors;
- một module layer được chọn khi dùng `ServiceLoader.load(layer, service)`.

**ServiceLoader dùng lazy discovery/instantiation và cache theo instance ServiceLoader.** Với `iterator()` hoặc `findFirst()`, những providers đã instantiate có thể được giữ và trả lại khi duyệt tiếp. Một object `ServiceLoader` còn sống có thể giữ:
1. loader/ngữ cảnh discovery được cấu hình;
2. provider descriptors/types và objects đã cache sau khi duyệt;
3. các đối tượng phụ trợ phục vụ việc phát hiện providers.

Nếu host giữ `ServiceLoader<HostService>` trong static field qua nhiều thế hệ plugin, nó có thể giữ **plugin loader và provider instances của thế hệ cũ** dù host không còn gọi chúng.

```text
Host static field
     │
     ▼
ServiceLoader<HostService>
     ├── discovery ClassLoader = PluginLoader-v1
     └── provider instance cache
              │
              ▼
         PluginProvider-v1
              │
              ▼
         PluginLoader-v1

Dù đã deploy v2, v1 vẫn có thể reachable.
```

**Không có `ServiceLoader.close()` để tự đóng provider objects hoặc class loaders.** Host phải quản lý lifecycle của chính providers, service loader holder, callback resources và plugin loaders.

### reload() giải quyết gì và không giải quyết gì?

`serviceLoader.reload()` xóa cache providers của **chính ServiceLoader instance đó**, để lần duyệt sau thử khám phá lại. Nó **không**:
- xóa providers đang có references ở listener registries khác;
- tự bỏ tham chiếu đến **discovery ClassLoader** gắn với chính ServiceLoader;
- unload class đã được JVM định nghĩa;
- reset static initializer của class đã initialized;
- stop threads/connections do provider tạo;
- đóng `URLClassLoader`;
- thay thế architecture hot deploy bằng loader mới.

Vì vậy, nếu host định gỡ toàn bộ plugin loader, **chỉ gọi `reload()` thường không đủ**: host còn phải bỏ tham chiếu đến ServiceLoader cũ, providers cũ và các owners khác.

## 7. Ví dụ Java 17+ chạy được: Listener registry + ServiceLoader cache giữ plugin sau close()

Đây là ví dụ hoàn chỉnh, có stdout xác định và **không cần đoán thời điểm GC**. Ta tạo:
- Host API `api.Hook`;
- implementation `impl.PluginHook` trong thư mục plugin riêng;
- file `META-INF/services/api.Hook` để `ServiceLoader` khám phá implementation;
- host static registry lưu provider instance và cache `ServiceLoader`;
- `URLClassLoader` bị `close()` nhưng host vẫn gọi được provider đã nạp;
- cuối cùng host làm sạch registry và cache.

### 7.1. Cấu trúc source

```text
plugin-leak-demo/
├── src/
│   ├── api/
│   │   └── Hook.java
│   ├── impl/
│   │   └── PluginHook.java
│   └── host/
│       └── RegistryLeakDemo.java
├── host-out/
└── plugin-out/
    └── META-INF/
        └── services/
            └── api.Hook
```

### 7.2. File src/api/Hook.java

```java
package api;

public interface Hook {
    String message();
}
```

`Hook` là **shared API** của host. Plugin implementation sẽ implements chính `api.Hook` do application/host loader định nghĩa.

### 7.3. File src/impl/PluginHook.java

```java
package impl;

import api.Hook;

public final class PluginHook implements Hook {
    public PluginHook() {
        System.out.println("PluginHook constructed");
    }

    @Override
    public String message() {
        return "plugin active";
    }
}
```

### 7.4. Service provider configuration

Tạo file:

```text
plugin-out/META-INF/services/api.Hook
```

Nội dung một dòng:

```text
impl.PluginHook
```

Tên file metadata là binary name của **service**, không phải của provider. Provider class có public constructor không tham số, đáp ứng cơ chế classpath SPI trong ví dụ.

### 7.5. File src/host/RegistryLeakDemo.java

```java
package host;

import api.Hook;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class RegistryLeakDemo {
    // Các fields nằm ở host class, không phải plugin class.
    private static final List<Hook> LISTENERS = new ArrayList<>();
    private static ServiceLoader<Hook> cachedServices;
    private static ClassLoader pluginLoaderForComparison;

    private static void deploy() throws Exception {
        URL url = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {url},
                RegistryLeakDemo.class.getClassLoader()
        )) {
            ServiceLoader<Hook> services =
                    ServiceLoader.load(Hook.class, loader);
            Hook provider = services.findFirst().orElseThrow();

            LISTENERS.add(provider);
            cachedServices = services;
            pluginLoaderForComparison = loader;

            System.out.println("provider uses plugin loader: "
                    + (provider.getClass().getClassLoader() == loader));
        }
        // Tại đây loader đã được close(), nhưng host vẫn giữ references.
    }

    public static void main(String[] args) throws Exception {
        deploy();

        System.out.println("after close listeners: "
                + LISTENERS.size());
        System.out.println("provider still callable: "
                + LISTENERS.get(0).message());
        System.out.println("cache keeps same provider: "
                + (cachedServices.iterator().next()
                   == LISTENERS.get(0)));
        System.out.println("registry points to loader: "
                + (LISTENERS.get(0).getClass().getClassLoader()
                   == pluginLoaderForComparison));

        LISTENERS.clear();
        cachedServices = null;
        pluginLoaderForComparison = null;

        System.out.println("after cleanup listeners: "
                + LISTENERS.size());
        System.out.println("after cleanup cached: "
                + (cachedServices != null));
    }
}
```

Trường `pluginLoaderForComparison` chỉ là **dấu mốc kiểm chứng trong demo**, không phải cơ chế cần dùng ở host thật. Bản thân trường này cũng giữ một strong reference đến loader; trong hệ thực tế không nên lưu nó ở static field lâu hơn vòng đời plugin. Các dòng `LISTENERS` và `cachedServices` đã đủ minh họa hai loại reference path chính.

### 7.6. Biên dịch và chạy

Mở terminal trong `plugin-leak-demo`. Với Bash:

```bash
mkdir -p host-out plugin-out/META-INF/services
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force host-out,plugin-out/META-INF/services | Out-Null
```

Tạo file metadata như mục 7.4, rồi biên dịch bằng **JDK 17+**:

```bash
javac --release 17 -d host-out src/api/Hook.java src/host/RegistryLeakDemo.java
javac --release 17 -cp host-out -d plugin-out src/impl/PluginHook.java
java -cp host-out host.RegistryLeakDemo
```

**Chú ý:** command `java` chỉ đưa `host-out` vào application classpath. Không thêm `plugin-out` vào `-cp` của host: nếu parent loader nhìn thấy implementation trước, class sẽ không còn do plugin loader riêng định nghĩa và demo mất ý nghĩa cô lập.

### 7.7. Stdout chính xác

```text
PluginHook constructed
provider uses plugin loader: true
after close listeners: 1
provider still callable: plugin active
cache keeps same provider: true
registry points to loader: true
after cleanup listeners: 0
after cleanup cached: false
```

Kết quả đã được thử với `javac --release 17` và Java runtime mới hơn theo API Java 17.

### 7.8. Phân tích từng quan hệ giữ

**Bước 1:** Host tạo `URLClassLoader` mới, parent là host loader. Plugin loader có thể đọc `plugin-out` và tìm `impl.PluginHook`, còn API `api.Hook` do parent cung cấp. Provider assignable sang service interface host vì dùng chung một runtime type.

**Bước 2:** `ServiceLoader.load(Hook.class, loader)` tạo discovery object; `findFirst()` duyệt lazy, instantiate `PluginHook` và constructor in `PluginHook constructed`.

**Bước 3:** Host lưu provider trong `LISTENERS` và giữ ServiceLoader trong `cachedServices`. Chúng là các strong references ở class host sống lâu.

**Bước 4:** Kết thúc `try (URLClassLoader loader = ...)`, `close()` chạy. Nhưng đã được định nghĩa, provider class/object vẫn hiện hữu. Vì method `message()` không đòi tìm class/resource mới, lời gọi tiếp theo vẫn thành công. **Không được kết luận plugin sau close luôn hoạt động đầy đủ**: một method khác cần dependency chưa load có thể thất bại.

**Bước 5:** `cachedServices.iterator().next()` trả lại instance được cache từ lượt `findFirst()`. Điều này chứng minh cache của ServiceLoader có thể là một **đường giữ provider instance**.

**Bước 6:** `LISTENERS.get(0).getClass().getClassLoader()` bằng loader đã tạo. Host còn tham chiếu đến implementation thuộc loader đó.

**Bước 7:** `LISTENERS.clear()`, `cachedServices=null` và `pluginLoaderForComparison=null` xóa ba tham chiếu host của demo. Đây là **cleanup cấu trúc có thể xác nhận ngay**; nó **không chứng minh loader đã được garbage collected đúng lúc in dòng cuối**.

### Điều gì sẽ xảy ra nếu chỉ xóa một trong hai cache?

- Chỉ `LISTENERS.clear()`: `cachedServices` vẫn có thể giữ provider instances và discovery loader.
- Chỉ `cachedServices=null`: `LISTENERS` vẫn giữ provider instance.
- Chỉ `cachedServices.reload()`: cache providers được xóa, nhưng ServiceLoader vẫn là một object sống có loader/ngữ cảnh gắn với nó; ngoài ra listener registry vẫn giữ instance.
- Chỉ `loader.close()`: không tự bỏ bất kỳ reference nào trong host.
- Chỉ `System.gc()`: không phải cleanup, không giải quyết strong references.

Đó là lý do việc xác minh bằng cấu trúc registry/ownership quan trọng hơn một lần gọi GC trong test.

## 8. Gỡ từng listener phải chính xác: token hay remove theo identity?

Trong registry đơn giản, API `remove(listener)` có thể phù hợp. Nhưng thực tế phát sinh:
- một listener được đăng ký **nhiều lần**;
- callback được wrap/decorate nên object truyền vào lúc remove không giống object nằm trong registry;
- `equals()` của listener có logic riêng khiến remove nhầm object;
- dispatch bất đồng bộ đã copy callback sang queue trước khi unregister;
- event bus cần ngừng chấp nhận callbacks mới trong lúc cleanup.

Vì vậy token registration thường rõ ràng hơn:

```java
// Trích đoạn thiết kế:
AutoCloseable registration = eventBus.register(pluginListener);

try {
    plugin.run();
} finally {
    registration.close(); // unregister một registration cụ thể
}
```

Đây là **pseudocode thiết kế**, `eventBus` và `plugin` do ứng dụng cung cấp. Khi người dùng đóng `registration`, event bus nên loại bỏ đúng registration tương ứng (thường idempotent) và có chính sách rõ về callbacks đang chạy.

Nếu listener ở registry ứng dụng **mà plugin không sở hữu API unsubscribe**, manager vẫn phải có cơ chế cleanup khi undeploy. Một registry chỉ có `add` mà không có `remove`/`close`/`reset` phù hợp là dấu hiệu rủi ro leak.

### Registration theo scope

Một kiến trúc an toàn hơn đặt mọi subscriptions trong một đối tượng lifecycle:

```java
// Trích đoạn: registrations là List<AutoCloseable>.
void stopSubscriptions(List<AutoCloseable> registrations)
        throws Exception {
    Exception first = null;
    for (int i = registrations.size() - 1; i >= 0; i--) {
        try {
            registrations.get(i).close();
        } catch (Exception ex) {
            if (first == null) {
                first = ex;
            } else {
                first.addSuppressed(ex);
            }
        }
    }
    registrations.clear();
    if (first != null) {
        throw first;
    }
}
```

Đây là **phương thức minh họa** có thể đặt trong một class; không cần import ngoài `java.util.List`. Nó cố đóng **mọi** registrations theo thứ tự ngược và ghi nhận lỗi suppressed thay vì dừng sau thất bại đầu tiên. Trong production còn cần thread-safety và tránh ghi đè registrations lúc cleanup.

## 9. Thread Context ClassLoader giữ plugin trên thread pool

`Thread.currentThread().getContextClassLoader()` có thể giữ plugin loader khi framework/`ServiceLoader` dùng TCCL để khám phá providers. Nếu host worker thread sống qua nhiều lần reload và không reset context loader, nó có thể pin generation cũ.

Restore TCCL trong `finally`, dọn provider cache/registrations riêng theo owner. Bài Thread/ThreadLocal/TCCL giải thích đầy đủ tình huống pooled thread.

## 10. ThreadLocal, CompletableFuture và các công việc bất đồng bộ

`ThreadLocal` value, scheduled callback, `CompletableFuture` chain, executor queue và task đang chạy có thể giữ plugin object dù `ServiceLoader` hoặc event bus đã được clear.

Để retire, cancel/drain futures/tasks phù hợp, `remove()` ThreadLocal trên chính thread đã gán và tránh để callback mới được đăng ký khi đang shutdown. Bài threads chuyên sâu kiểm tra lỗi này.

## 11. JNI, JDBC, JMX, logging và registry do framework quản lý

Bên cạnh listener do bạn tự viết, nhiều thành phần JDK/framework cũng là **registries**:

- **JDBC DriverManager**: plugin đăng ký `java.sql.Driver` do loader plugin định nghĩa. Tùy cách driver được khởi tạo/đăng ký và runtime, cần **deregister** driver plugin sở hữu khi unload bằng API thích hợp. Không deregister driver của ứng dụng khác.
- **JMX MBeanServer**: MBeans đăng ký với server sống lâu có thể giữ object/class/loader plugin; cần unregister đúng `ObjectName`.
- **Logging handlers/appenders**: plugin logger/handler có thể được host logger tree, async queue hoặc logging context giữ; cần detach/stop/close theo API framework.
- **Shutdown hooks**: `Runtime.addShutdownHook(Thread)` giữ hook thread được đăng ký cho tới khi chạy hoặc xóa; plugin phải remove hook do nó sở hữu khi vẫn còn được phép.
- **Timer/Executor/Scheduler**: các task objects có thể capture plugin và tồn tại lâu hơn plugin.
- **Class/serializer/reflection caches** của framework dùng chung: có thể giữ `Class<?>`/`Method`/codegen proxy của plugin.
- **JNDI, service registries, DI containers**: bản chất tương tự khi chúng giữ provider object hoặc class metadata.

Đây là **nhóm nguồn cần điều tra**, không có nghĩa mọi thư viện/JVM implementation đều leak. Nhiều framework đã dùng weak references hoặc cleanup hooks. Phải đo và xác định reference path trên phiên bản đang dùng.

### Không dọn nhầm tài nguyên dùng chung

Nếu host sở hữu thread pool và nhiều plugins cùng sử dụng, plugin A không được `shutdown()` cả pool khi A undeploy. A chỉ phải cancel các tasks/callbacks của mình và trả quyền điều khiển về host.

Tương tự, driver/mbean/listener/resource chỉ nên được unregister bởi owner hoặc lifecycle manager theo registration token/ID của nó. Cleanup bừa có thể phá plugin B.

## 12. Quan hệ giữa ServiceLoader, ClassLoader và module layer

Trong ứng dụng modular (JPMS), ServiceLoader có thể khám phá providers qua module descriptors:

```java
module app.api {
    exports app.api;
}
```

```java
module plugin.impl {
    requires app.api;
    provides app.api.Plugin with plugin.impl.DefaultPlugin;
}
```

Đây là **hai descriptor minh họa**, giả định các types thực sự có. `ServiceLoader.load(layer, Plugin.class)` tìm provider trong `ModuleLayer` phù hợp theo API Java.

Một host tạo **child ModuleLayer** cho plugin có thể giữ:
- đối tượng `ModuleLayer`;
- `Module` objects;
- `ClassLoader` do layer sử dụng;
- `ServiceLoader`/provider descriptors;
- providers/instances và callbacks.

Dù không dùng `URLClassLoader` trực tiếp, reference path từ host đến child layer/plugin loaders/classes vẫn cần quản lý. Không xem `ModuleLayer` là một “vỏ” tự unload khi gọi method nào đó; bản thân `ModuleLayer` không có `close()`.

**Không tự đồng nhất JPMS export/open với memory isolation.** Module `requires`/`exports`/`opens` kiểm soát readability/access, không tự quản lý GC hoặc ngừng threads của plugin.

## 13. Vì sao WeakReference/WeakHashMap không phải giải pháp tự động?

Java có:
- `WeakReference<T>`: tham chiếu yếu, không giữ referent sống chỉ nhờ reference đó.
- `WeakHashMap<K,V>`: khóa yếu; entry có thể bị xóa khi key không còn strong reachable phù hợp.
- `ReferenceQueue<T>`: có thể quan sát tham chiếu yếu/phantom được enqueue theo tiến trình GC.
- `Cleaner` và phantom references: cơ chế cleanup dựa trên reachability, không có thời điểm thực thi bảo đảm.

Chúng hữu ích trong một số cache, nhưng **không thay thế explicit lifecycle cleanup**.

### Ví dụ bẫy WeakHashMap

```java
// Trích đoạn:
Map<ClassLoader, Holder> cache = new WeakHashMap<>();
cache.put(pluginLoader, new Holder(pluginLoader));
```

Ở đây `Holder` giả định có strong reference đến loader. Dù key của `WeakHashMap` là weak, **value Holder có thể giữ key loader một cách mạnh**, tạo đường:

```text
WeakHashMap (host)
     └── strongly-held value Holder
              └── strongly-held pluginLoader
                       └── key chưa collectible
```

Vì thế “đã dùng WeakHashMap” không tự bảo đảm entry biến mất. Cũng tương tự với cache chứa `Class<?>` hoặc provider instances có liên hệ đến loader.

### Weak listener có đủ không?

Một event bus chỉ dùng weak references đến listeners có thể tránh giữ listeners lâu ngoài ý muốn, nhưng làm phát sinh một vấn đề khác: listener có thể bị GC **khi vẫn cần nhận event** nếu owner không giữ reference. Trong nhiều hệ thống, **strong registration + explicit unsubscribe** đáng tin hơn, rõ ràng về thời gian và quyền sở hữu.

**Chỉ dùng weak references khi semantics của cache phù hợp**, không dùng để che việc thiếu API unregister/stop.

## 14. Dùng WeakReference để quan sát khả năng collectible

Có thể ghi nhận:

```java
// Trích đoạn:
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);

// Sau khi ngừng plugin, bỏ strong references ở đúng owner:
// pluginLoader = null;  // chỉ nếu biến có thể gán lại
//
// Sau đó tại thời điểm GC thực hiện:
ClassLoader stillThere = weak.get();
```

Đây là **trích đoạn**, cần import `java.lang.ref.WeakReference` và biến `pluginLoader` phù hợp. **`weak.get() != null` ngay sau cleanup không chứng minh leak**: GC có thể chưa chạy hoặc vẫn còn transient stack references. **`weak.get() == null`** cho thấy referent đã được GC thu hồi ở thời điểm quan sát đó, nhưng không thay thế việc kiểm tra resource cleanup.

Một số test harness thử lặp `System.gc()`, chờ `ReferenceQueue` và giới hạn timeout. Các bài test này dễ bất ổn trên CI/JVM/GC khác nhau, vì `System.gc()` là request, không phải bảo đảm. Nên:
- Dùng **structural assertions** để chứng minh registries empty, subscriptions closed, TCCL restored, executors stopped.
- Dùng **integration soak/redeploy tests** để theo dõi xu hướng loader count/metaspace.
- Dùng weak references/queue như **tín hiệu hỗ trợ**, không biến “GC phải xảy ra trong 100 ms” thành điều kiện đúng sai của application logic.

## 15. Cách quan sát class unloading bằng HotSpot

Với JDK HotSpot hỗ trợ unified logging, có thể bật:

```bash
java -Xlog:class+load=info,class+unload=info -cp host-out host.RegistryLeakDemo
```

Câu lệnh dùng demo ở mục 7. **Dòng log thực tế tùy JVM/JDK** và có thể rất dài. Không có nghĩa JVM bắt buộc unload plugin class trong phiên chạy ngắn này.

Với process đang hoạt động, có thể dùng:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> Thread.print -l
```

`<pid>` là placeholder cho process ID thật. Các lệnh và thông tin khả dụng tùy JVM/JDK. Trong HotSpot:
- `VM.classloader_stats` hỗ trợ xem ClassLoader statistics (nếu command có trong JVM tương ứng).
- Thread dump giúp tìm thread vẫn chạy code plugin hoặc TCCL liên quan.
- `GC.class_histogram`/heap dump có thể hỗ trợ phân tích instances và retention paths, nhưng cần cân nhắc overhead khi chạy production.
- Các công cụ heap analysis như Eclipse Memory Analyzer có thể giúp xem **path to GC roots**, dominator tree và retained heap.

### Đừng chỉ nhìn metaspace một lần

Metaspace có thể tăng do class loading hợp lệ, JVM caching hoặc hoạt động GC; mức sử dụng chưa giảm ngay không đủ kết luận leak. Tín hiệu mạnh hơn là **nhiều thế hệ plugin loader cũ tiếp tục reachable và tăng theo mỗi redeploy**, cùng reference paths cụ thể từ những GC roots sống lâu.

Phân biệt:
- **Bytes JAR bị mở/khóa**: vấn đề I/O/file handles; `URLClassLoader.close()` hỗ trợ giải phóng.
- **Object plugin còn trong listener registry**: vấn đề strong references; cần unregister.
- **ServiceLoader/provider caches chưa bỏ**: vấn đề discovery object/cache lifecycle.
- **Worker TCCL còn plugin loader**: vấn đề thread context/lifecycle.
- **Class metadata không unload ngay**: có thể là GC timing; cần đo qua thời gian/roots.

## 16. Heap dump: đọc “path to GC roots” đúng cách

Giả sử phát hiện `PluginClassLoader-v1` đáng lẽ đã bị dỡ mà còn sống. Một retaining path có thể là:

```text
GC Root: System ClassLoader's class / host static field
    └── host.EventBus.REGISTRATIONS
          └── ArrayList.elementData[5]
                └── impl.PluginHook instance
                      └── runtime Class / loader
                            └── PluginClassLoader-v1
```

Hoặc:

```text
GC Root: live executor Thread
    └── contextClassLoader
          └── PluginClassLoader-v1
```

Hoặc:

```text
GC Root: host static service registry
    └── cached ServiceLoader<Hook>
          ├── explicit discovery ClassLoader
          └── provider instance cache
                 └── PluginHook instance
```

Những sơ đồ này **mô tả nguyên nhân điển hình**, không phải tên field nội bộ chắc chắn giống nhau trên mọi JVM.

Quy trình đọc heap dump:
1. Chọn **loader instance thuộc thế hệ plugin cũ**, phân biệt với loader hiện tại.
2. Kiểm tra objects của plugin classes do loader cũ định nghĩa.
3. Dùng **path to GC roots, excluding weak/soft/phantom references** khi công cụ hỗ trợ để ưu tiên strong retention.
4. Nhận diện **owner bên ngoài plugin** (registry host, thread, module layer, singleton).
5. Tìm registration/cleanup path tương ứng và xác nhận nó có chạy ở normal + error shutdown.
6. Đo lại sau nhiều vòng redeploy và GC phù hợp.

Không “sửa” leak bằng cách giữ những objects nghi vấn trong debugger/test code rồi trông đợi GC unload: chính tool/test cũng có thể làm referent reachable.

## 17. Thiết kế PluginContext có quyền sở hữu rõ ràng

Một kiến trúc plugin bền vững có **một owner chịu trách nhiệm cho mỗi resource**. Host có thể tạo một context để plugin đăng ký mọi handles cần cleanup:

```text
PluginManager
   └── PluginSession
         ├── Plugin ClassLoader
         ├── ServiceLoader / provider instances
         ├── Event subscriptions
         ├── Scheduled tasks / Executor-owned handles
         ├── MBean / JDBC / logging registrations
         └── Closeable resources
```

Khi dừng:
- Ngừng nhận công việc plugin mới.
- Cho công việc đã bắt đầu hoàn thành hoặc cancel theo policy.
- Gọi stop hook của plugin khi loader và dependencies vẫn khả dụng.
- Đóng các subscriptions/registrations, hủy scheduled tasks.
- Cleanup ThreadLocals/TCCL theo đúng thread/scope.
- Đóng streams/sockets/connections do session sở hữu.
- Xóa các caches thuộc host trỏ vào instance/class/loader plugin.
- Bỏ giữ ServiceLoader cũ; nếu sẽ reload providers, tạo discovery context của thế hệ mới.
- Đóng URLClassLoader nếu host sở hữu và dùng loader loại đó.
- Loại bỏ session khỏi registry của PluginManager.

Nếu một cleanup bước thất bại, nên **vẫn thử các bước còn lại**, thu thập/suppress exceptions rồi báo cáo tổng hợp. Không dừng giữa chừng, để lại registrations khác chỉ vì một listener ném exception.

### Ví dụ resource stack đơn giản

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class CleanupStack implements AutoCloseable {
    private final Deque<AutoCloseable> resources =
            new ArrayDeque<>();

    public void own(AutoCloseable resource) {
        resources.push(resource);
    }

    @Override
    public void close() throws Exception {
        Exception failure = null;

        while (!resources.isEmpty()) {
            AutoCloseable resource = resources.pop();
            try {
                resource.close();
            } catch (Exception ex) {
                if (failure == null) {
                    failure = ex;
                } else {
                    failure.addSuppressed(ex);
                }
            }
        }

        if (failure != null) {
            throw failure;
        }
    }
}
```

Đây là một **file `CleanupStack.java` biên dịch được** trên Java 17. Đăng ký các resource theo thứ tự sở hữu; `push` và `pop` khiến cleanup chạy **ngược thứ tự đăng ký**.

Ví dụ sử dụng (trích đoạn):

```java
try (CleanupStack scope = new CleanupStack()) {
    scope.own(registrationA);
    scope.own(registrationB);
    // Thực thi plugin với các registrations còn hiệu lực.
}
```

`registrationA`/`registrationB` ở đây là placeholders cho `AutoCloseable` thực. Không nên dùng cùng một `CleanupStack` từ nhiều threads nếu chưa bổ sung đồng bộ; class minh họa quản lý một scope tuần tự. Đồng thời, thứ tự stop tác vụ trước cleanup callbacks/loader phải được quy định ở tầng PluginManager; không đẩy toàn bộ trách nhiệm lifecycle vào stack một cách mù quáng.

### Vì sao có ích?

- Resource owner rõ, tránh quên unsubscribe.
- Scope kết thúc vì `return`/exception vẫn gọi `close()`.
- Cleanup errors được giữ dạng suppressed.
- Dễ kiểm thử `close()` idempotent ở các wrappers riêng.
- Không biến `ServiceLoader.reload()` thành phương tiện stop plugin.

Đây là mẫu trợ giúp, không thay thế chính sách concurrency và lifecycle đầy đủ.

## 18. Thứ tự shutdown và trường hợp race

Cần tránh:

```text
Thread A: close PluginClassLoader
Thread B: đang load một class mới của plugin
Thread C: event bus đang gọi listener plugin
```

Với `URLClassLoader.close()`, Java API cảnh báo kết quả load class đồng thời với close không xác định. Về nghiệp vụ, dù loader đã đóng, event đã dispatch vẫn có thể tiếp tục gọi callback; nếu callback tải class/resource muộn, có thể lỗi.

Thứ tự an toàn thường là:

```text
ACTIVE
  ↓ 1. set state STOPPING (không nhận work mới)
STOPPING
  ↓ 2. cancel/drain, await in-flight work
QUIESCENT
  ↓ 3. stop providers, unregister callbacks/listeners
CLEANING
  ↓ 4. close owned resources, drop ServiceLoader/registry refs
  ↓ 5. restore per-thread context, shutdown owned executors
  ↓ 6. close loader và release session refs
CLOSED
  ↓ 7. GC có thể unload về sau
```

Các bước có thể thay đổi thứ tự chi tiết theo dependency. Ví dụ các threads phải restore TCCL **trước khi hoàn toàn dừng** nếu TCCL do chúng đã tự đặt; shutdown executor không tự cho phép host truy cập ThreadLocals của worker khác để remove đúng context. Thiết kế cleanup hooks chạy **ngay trong task/thread đã dùng context**, thay vì đợi đến cuối rồi cố “xóa thread local từ thread khác”.

### Dùng trạng thái rõ ràng

`PluginManager` nên có trạng thái như `NEW / STARTING / ACTIVE / STOPPING / CLOSED`, chặn callback/task mới sau `STOPPING`, và làm `stop()` **idempotent** khi có thể. Điều này giúp tránh hai threads cùng undeploy rồi remove/close lặp không đúng thứ tự.

Một listener registration token `close()` idempotent càng dễ bảo đảm cleanup toàn diện khi application shutdown gặp nhiều loại failure.

## 19. Vì sao static caches thuộc plugin không luôn là vấn đề?

Một cache static tự tham chiếu bên trong plugin generation **không tự tạo leak** nếu toàn bộ graph của generation không còn reachable từ GC roots. Ngược lại, **host static registry** giữ provider/listener/callback của plugin sẽ duy trì đường reference ngoài generation.

Phân biệt chủ sở hữu cache và chiều reference. Bài static field/cache reflection phân tích cụ thể những trường hợp nên dùng per-generation cache hoặc `ClassValue`.

## 20. Test các điều kiện cleanup mà không phụ thuộc GC

Một số assertions xác định ngay sau undeploy:
- `registry.size() == 0` đối với registrations của plugin cũ.
- `pluginSession.isClosed()` hoặc state `CLOSED`.
- Số subscriptions/handlers/timers do plugin đăng ký trở về mức nền.
- Worker tasks thuộc plugin không còn in-flight; executor owned đã shutdown.
- TCCL của workers được restore hoặc các workers thuộc plugin đã kết thúc.
- `ServiceLoader` và provider instances của **thế hệ cũ** không còn được host giữ trong registry/cache.
- Một loader mới có thể nạp implementation phiên bản mới qua shared API mà không xung đột runtime class identity.

Một tình huống test nên mô phỏng:

```text
Deploy v1
  → register listener, create provider/cache
  → assert plugin active and callable

Stop v1
  → unregister listener, clear caches, close loader
  → assert no old callbacks/owners
  → do NOT assert immediate class unloading

Deploy v2 with fresh loader
  → assert new implementation selected
  → assert shared host API still assignable

Repeat N times
  → check loader count/metaspace trend under controlled GC
```

Ở step soak, sử dụng heap dump/reference paths nếu trend tăng bất thường. Không biến bộ test thành vòng lặp `System.gc()` vô hạn, vì JVM có thể không thu gom class ngay và thời điểm GC không phải API đồng bộ.

## 21. Tình huống đặc biệt: ServiceLoader trong host dùng TCCL

Giả sử framework ở host loader gọi:

```java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);
```

Theo contract, overload này chọn TCCL của thread đang gọi. Nếu thread pool được tái sử dụng qua plugins:
- TCCL còn `PluginLoader-v1` → service discovery có thể tìm provider v1.
- Đổi TCCL sang `PluginLoader-v2` sau đó không có nghĩa `providers` cũ tự đổi discovery loader; nó đã được tạo trong ngữ cảnh cũ.
- Một host static cache `providers` còn giữ object ServiceLoader và các references liên quan đến loader cũ.

Giải pháp:
1. Scope TCCL theo task và restore `finally`.
2. Nếu host biết loader đúng, ưu tiên `ServiceLoader.load(service, pluginLoader)` cho rõ ràng.
3. Không cache `ServiceLoader` theo service type đơn thuần nếu thực tế provider set **phụ thuộc từng plugin generation/ClassLoader/ModuleLayer**.
4. Khi unload, drop cache entry của generation cũ, ngừng provider tasks và cleanup callback registrations.
5. Tạo ServiceLoader mới cho loader/layer thế hệ mới.

Đây là tình huống thường gây nhầm giữa **class loading**, **service discovery**, **thread context** và **memory retention**.

## 22. Dấu hiệu quan trọng trong log, heap dump và monitoring

| Dấu hiệu | Có thể liên quan | Kiểm tra tiếp |
|---|---|---|
| Listener tiếp tục nhận event sau plugin stop | Subscription chưa gỡ, queue in-flight | Registry snapshot, owner registration token |
| Plugin class loader cũ có nhiều instances sau redeploy | Registry/cache/threads giữ reference | Path to GC roots |
| `ServiceLoader` trả provider cũ sau cập nhật | Cache + loader cũ, chưa tạo context mới | ServiceLoader object, loader/layer, `reload`/replace |
| Metaspace tăng theo số lần redeploy | Classloader generations chưa được thu gom | Class loader stats, GC roots, trend |
| JAR không xóa được trên Windows | Open file handles | URLClassLoader.close, JarFile, streams khác |
| NoClassDefFoundError sau close | Code/plugin còn hoạt động, cần dependency mới | Shutdown order, lazy loading, in-flight tasks |
| Request B dùng provider của plugin A | TCCL của worker bị giữ từ request trước | TCCL set/restore trong task |
| Thread pool không dừng khi plugin stop | Executor/scheduled job còn sống | Threads, queue, owner shutdown |
| `WeakReference.get()` vẫn khác null sau stop | GC chưa chạy hoặc còn strong refs | Đừng kết luận ngay; xem registry/roots |
| Leak chỉ xảy ra khi error trong start | Cleanup không chạy ở failure path | try/finally, cleanup stack, partial registration |

Nếu có thể, logging nên gắn **plugin generation ID** với loader object identity (không chỉ tên class), và record số registrations/providers/tasks do generation đó còn sở hữu.

## 23. Một số anti-pattern phổ biến

### 23.1. “Close là đủ”

```java
// Anti-pattern ở cấp kiến trúc, trích đoạn:
pluginLoader.close();
// hostRegistry vẫn giữ plugin instances
```

**Sai** vì close không xóa registry entry. Phải unsubscribe/drop references trước hoặc trong shutdown protocol.

### 23.2. “Reload ServiceLoader sẽ xóa provider cũ ở mọi nơi”

```java
// Trích đoạn:
services.reload();
```

**Sai** nếu listener registry vẫn chứa provider, hoặc ServiceLoader còn giữ explicit plugin loader. `reload` không gọi `close()` cho provider.

### 23.3. “Dùng WeakHashMap là hết leak”

Sai khi map value hoặc reference khác vẫn giữ loader/key, và khi data cần strong lifecycle ownership.

### 23.4. “Dùng System.gc() để unload plugin”

```java
System.gc();
```

API chỉ request GC, không có bảo đảm thu gom một loader đang reachable. Đặc biệt, nếu host static field còn giữ callback/provider, GC không được phép thu hồi object đó.

### 23.5. “Dùng loader mới nhưng cache host vẫn giữ bản cũ”

Loader mới có thể định nghĩa cùng binary name thành runtime class mới, nhưng những `Class<?>`/provider objects của loader cũ trong host registry vẫn sống. Khi cast implementation qua hai generations có thể nhận `ClassCastException`.

### 23.6. “Xóa mọi static cache trong plugin bằng reflection”

Không cần thiết nếu không còn strong refs từ host/GC roots; còn có thể gây access issue trong JPMS. Đúng hơn là dọn các **references xuyên ranh giới loader** và resources owned có lifecycle cụ thể.

## 24. Checklist code review cho hệ plugin

### Trước khi triển khai

- Shared service API/interface nằm ở **host/common loader** hoặc shared module ổn định.
- Plugin implementation/dependencies private nằm ở loader riêng theo architecture.
- Có mô hình ownership cho loader, ServiceLoader, listeners, async tasks, ThreadLocals và external resources.
- Registration APIs trả token hoặc hỗ trợ unregister theo đúng owner.
- Quy định rõ có dùng TCCL hay explicit loader/module layer khi discovery.

### Trong vòng đời ACTIVE

- Theo dõi list subscriptions/providers/tasks thuộc từng plugin generation.
- TCCL được set/restore theo scope, đặc biệt ở executor.
- Không dùng global static cache keyed chỉ bằng class name cho các plugin có nhiều generations.
- Không để provider tự mở background thread vô hạn không có stop hook.
- Không đóng loader sớm nếu plugin có thể lazy-load class/resource.

### Khi STOPPING

- Chặn work mới, chờ in-flight tasks.
- Gọi stop hooks khi plugin dependencies còn hoạt động.
- Unregister listeners, MBeans, drivers, shutdown hooks do plugin sở hữu.
- Cancel timers/tasks và shutdown các executors do plugin sở hữu.
- Remove ThreadLocals, restore TCCL đúng thread.
- Đóng streams/sockets/connections, xử lý errors nhưng vẫn cleanup phần còn lại.
- Xóa host registry/cache refs tới provider instances, `Class<?>`, reflection objects, ServiceLoader, layer, loader.
- Gọi `URLClassLoader.close()` khi applicable và bỏ session references.

### Sau cleanup

- Assert các registry counts/owners về mức mong đợi.
- Không yêu cầu GC/unload đồng bộ.
- Chạy integration test reload với loader thế hệ mới.
- Theo dõi metaspace/loader generations trên nhiều vòng deploy; nếu tăng, phân tích GC roots.
- Không đụng vào resources của plugin khác khi teardown.

## 25. Câu hỏi tự kiểm tra

1. **`URLClassLoader.close()` có tự unload mọi class không?** Không, nó đóng nguồn tìm và tài nguyên; classes đã nạp có thể còn sống.
2. **Một listener nằm trong host static registry có thể giữ plugin loader không?** Có, qua object implementation/class/loader.
3. **Event bus không phát event nữa thì listener đã hết leak chưa?** Không; phải remove reference.
4. **`ServiceLoader.findFirst()` có thể làm cache giữ provider instance không?** Có, ServiceLoader instance có thể cache provider đã instantiate.
5. **`ServiceLoader.reload()` có clear listeners do host đăng ký không?** Không.
6. **ServiceLoader cũ còn giữ loader đã dùng khám phá sau `reload()` không?** Có thể, vì nó vẫn là discovery object với loader/ngữ cảnh đã cấu hình.
7. **Vì sao host static `Map<String, Class<?>>` nguy hiểm?** Nó có thể giữ plugin runtime Class và defining loader.
8. **Static field bên trong plugin tự trỏ vòng có luôn gây leak không?** Không; nếu cả nhóm không còn reachable từ GC roots, GC có thể thu gom.
9. **TCCL của thread pool còn trỏ plugin cũ thì sao?** Giữ strong reference và có thể chọn nhầm provider.
10. **Dùng `setContextClassLoader(null)` có luôn đúng khi cleanup không?** Không; restore đúng giá trị trước đó.
11. **ThreadLocal remove có tự stop background thread không?** Không; cần lifecycle task/executor riêng.
12. **Dùng `WeakHashMap` với value giữ mạnh key có tự làm entry biến mất không?** Không.
13. **`WeakReference.get() != null` ngay sau stop có chứng minh leak không?** Không; GC có thể chưa chạy.
14. **Nên test cleanup thế nào để ổn định?** Assert unregister, empty registries, dropped caches, completed tasks, restored TCCL; GC observation là bổ sung.
15. **Classloader count tăng qua nhiều redeploy nên điều tra gì?** Loader generations còn sống và path to GC roots.
16. **Có thể vừa thay provider thế hệ mới mà không dọn provider cũ không?** Có thể về mặt kỹ thuật, nhưng dễ gây leak, nhầm provider và type identity conflicts.
17. **Mục đích subscription token là gì?** Bảo đảm host có handle hủy đúng registration thuộc plugin.
18. **`ModuleLayer` có close()/unload tự động không?** Không.
19. **ServiceLoader có thread-safe không?** Không; phải phối hợp khi duyệt/reload từ nhiều threads.
20. **Mục tiêu thực tế của undeploy là gì?** Dừng plugin, cleanup resources và references; GC có thể unload classes sau đó.

## Tài liệu tham khảo chính thức

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): discovery, cache, `reload()`, threading và provider lifecycle.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): close behavior và các class/resource đã nạp.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation và runtime class identity.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): TCCL và thread lifecycle.
- [Java SE 17 — WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): reachability và tham chiếu yếu.
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys và cảnh báo values có thể giữ keys.
- [JVMS 17 — `5.3` Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loaders, runtime identity, class lifecycle.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): dữ liệu riêng theo thread và `remove()`.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layer runtime và ClassLoader mapping.

**Kết luận:** Khi plugin đã stop nhưng bộ nhớ không giảm, cần kiểm tra **ai còn giữ plugin**: listener registry, singleton/cache của host, `ServiceLoader` và cached provider instances, TCCL/ThreadLocal, background tasks hoặc các registries thuộc framework. `close()` và `reload()` chỉ xử lý **một phần vòng đời**; chúng không xóa strong references từ hệ thống. Cleanup đúng là **stop work → unregister/close owned resources → bỏ cache và references → close loader → để GC quyết định unloading**, với kiểm thử cấu trúc và phân tích GC roots thay vì đặt kỳ vọng vào `System.gc()`.
