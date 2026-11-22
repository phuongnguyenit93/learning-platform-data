# Quản lý vòng đời plugin và tránh giữ tham chiếu không cần thiết

## Mục tiêu

Ứng dụng có kiến trúc plugin thường phải nạp thêm module khi chạy, khởi tạo các provider, cho phép plugin hoạt động trong một khoảng thời gian rồi dừng hoặc thay thế chúng. Với Java Platform Module System (JPMS), có thể tạo một `ModuleLayer` riêng cho plugin và dùng `ServiceLoader` để tìm implementation. Tuy nhiên, việc tạo layer mới không đồng nghĩa với việc có thể xóa layer ngay khi gọi một lệnh unload.

Bài này tập trung vào vòng đời của plugin, cách đóng tài nguyên và cách tránh giữ tham chiếu khiến class loader cùng các class của plugin tiếp tục tồn tại trong bộ nhớ.

Sau bài này, bạn có thể:

- Thiết kế các trạng thái nạp, khởi động, dừng và tháo plugin.
- Tạo child `ModuleLayer` và tìm provider bằng `ServiceLoader.load(layer, Service.class)`.
- Xác định các tham chiếu mạnh có thể giữ plugin sống sau khi dừng.
- Giải phóng listener, executor, thread, ThreadLocal, context class loader và cache.
- Thiết kế API đóng plugin bằng `AutoCloseable`.
- Hiểu điều kiện để class loader đủ điều kiện được garbage collector thu hồi.
- Phân biệt đóng plugin, đóng tài nguyên và class unloading.

Ví dụ dùng Java 17+ và API JPMS hiện hành. Các ví dụ thực nghiệm được biên dịch bằng `javac --release 17`.

## 1. Vòng đời plugin là một quy trình có trạng thái

Một plugin không chỉ có hai trạng thái loaded/unloaded. Nó có tài nguyên, callback và hoạt động bất đồng bộ cần được quản lý theo thứ tự.

Một vòng đời thường dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| DISCOVERED | Module/provider đã được tìm thấy và kiểm tra |
| STARTED | Plugin đã khởi tạo và được phép nhận công việc |
| QUIESCING | Ngừng nhận công việc mới, chờ tác vụ đang chạy hoàn tất |
| STOPPED | Đã dừng hoạt động, hủy tác vụ và đóng tài nguyên |
| DETACHED | Đã xóa khỏi registry, listener và các điểm truy cập của host |
| ELIGIBLE_FOR_GC | Không còn strong reference từ GC root; class loader có thể được thu hồi |

Luồng tổng quát:

~~~text
DISCOVERED
    |
    v
STARTED
    |
    v
QUIESCING  ---- chặn request mới, chờ request đang chạy
    |
    v
STOPPED    ---- hủy task, đóng tài nguyên, gỡ listener
    |
    v
DETACHED   ---- xóa registry và cache của host
    |
    v
ELIGIBLE_FOR_GC
             GC có thể thu hồi class loader và class của plugin
~~~

`close()` có thể đưa plugin đến trạng thái STOPPED hoặc DETACHED tùy thiết kế API. Nó không tự bảo đảm plugin đã được garbage collector thu hồi. Việc thu hồi bộ nhớ xảy ra sau đó nếu không còn đường tham chiếu mạnh từ các GC root.

Một plugin manager nên xác định rõ ai sở hữu từng tài nguyên và ai chịu trách nhiệm đóng tài nguyên đó. Nếu host đăng ký listener, executor hoặc callback thay mặt plugin, host cần có cách hủy đăng ký tương ứng.

## 2. Phân biệt ModuleLayer, ClassLoader và ServiceLoader

Ba đối tượng này có vai trò khác nhau:

- **ModuleLayer**: mô hình một tập module đã được phân giải và liên kết với các layer cha. Layer chứa quan hệ giữa module và class loader.
- **ClassLoader**: nạp định nghĩa class. Các đối tượng thuộc class được nạp bởi loader đó gắn với vòng đời của loader.
- **ServiceLoader**: tìm và khởi tạo provider cho một service type. Instance ServiceLoader có thể giữ cache provider và tham chiếu đến layer hoặc loader liên quan.

Khi tạo plugin layer, host thường có luồng:

1. Tìm module plugin trên module path.
2. Phân giải cấu hình và liên kết provider.
3. Tạo child ModuleLayer.
4. Tạo ServiceLoader cho layer đó.
5. Lấy provider và khởi động plugin.
6. Dừng plugin, đóng tài nguyên và bỏ các tham chiếu đến loader/layer.

Ví dụ API tạo layer:

~~~java
Configuration configuration = ModuleLayer.boot()
        .configuration()
        .resolveAndBind(
                ModuleFinder.of(),
                ModuleFinder.of(pluginPath),
                Set.of("com.example.plugin.hello"));

ModuleLayer pluginLayer = ModuleLayer.boot()
        .defineModulesWithOneLoader(configuration, null);
~~~

Ở đây, `pluginPath` là thư mục chứa modular JAR của plugin. Finder đầu tiên rỗng vì các module nền tảng và API host đã nằm trong cấu hình của boot layer; finder thứ hai tìm plugin. `null` chọn bootstrap class loader làm parent loader cho loader được tạo trong child layer.

Đây là cách tạo layer cho plugin module có dependency đến API module đã có trong parent layer. Nếu ứng dụng có cấu trúc loader hoặc parent layer khác, phải chọn parent loader phù hợp với loader hierarchy của layer đó.

Không nên cast loader do ModuleLayer tạo ra sang `URLClassLoader` hoặc giả định mọi loader đều có phương thức `close()`. JPMS không cam kết loại loader cụ thể cho các layer.

## 3. Tạo API plugin với hợp đồng đóng tài nguyên

Host và plugin nên giao tiếp qua một API module nhỏ, ổn định. Interface plugin có thể kế thừa `AutoCloseable`:

~~~java
package com.example.plugin.api;

public interface Plugin extends AutoCloseable {
    String id();

    void start();

    @Override
    void close();
}
~~~

Module API export package chứa interface:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Quy ước nên được ghi rõ trong hợp đồng:

- `start()` chỉ được gọi khi plugin đang ở trạng thái DISCOVERED.
- `close()` dừng plugin, hủy công việc nền và đóng tài nguyên plugin sở hữu.
- `close()` nên idempotent: gọi nhiều lần vẫn an toàn.
- Sau khi `close()` hoàn tất, plugin không tiếp tục phát callback hoặc gửi công việc mới cho host.
- Nếu plugin không thể dừng ngay, host cần một quy trình chờ hoặc timeout rõ ràng.
- Exception khi đóng một plugin không được ngăn host cố gắng đóng các plugin còn lại.

Có thể mở rộng hợp đồng để truyền context:

~~~java
public interface Plugin extends AutoCloseable {
    String id();

    void start(PluginContext context);

    @Override
    void close();
}
~~~

`PluginContext` nên cung cấp các API có thể thu hồi như đăng ký listener trả về một registration handle, đăng ký command trả về handle, hoặc tạo executor thuộc quyền sở hữu của plugin. Handle nên implement `AutoCloseable` để plugin có thể gỡ đăng ký trong `close()`.

## 4. Nạp plugin trong một child ModuleLayer

Ví dụ gồm ba module:

- `com.example.plugin.api`: chứa interface Plugin.
- `com.example.plugin.host`: ứng dụng host, khai báo `uses Plugin`.
- `com.example.plugin.hello`: provider module, khai báo `provides Plugin with HelloPlugin`.

Module host:

~~~java
module com.example.plugin.host {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Module plugin:

~~~java
module com.example.plugin.hello {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.hello.HelloPlugin;
}
~~~

Provider implementation:

~~~java
package com.example.plugin.hello;

import com.example.plugin.api.Plugin;

public final class HelloPlugin implements Plugin {
    private boolean started;

    public HelloPlugin() {
    }

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public void start() {
        if (started) {
            throw new IllegalStateException("Already started");
        }
        started = true;
        System.out.println("Hello from JPMS plugin");
    }

    @Override
    public void close() {
        if (!started) {
            return;
        }
        started = false;
        System.out.println("closed=hello");
    }
}
~~~

Host tìm provider trong đúng layer:

~~~java
ServiceLoader<Plugin> services =
        ServiceLoader.load(pluginLayer, Plugin.class);
~~~

Dùng overload có tham số `ModuleLayer` giúp chỉ rõ layer cần tìm provider. Điều này quan trọng khi ứng dụng có nhiều phiên bản plugin hoặc nhiều layer độc lập.

Với plugin nằm trong child layer, không nên giữ ServiceLoader trong singleton của host sau khi plugin đã dừng. ServiceLoader có thể giữ cache provider và giữ các tham chiếu cần thiết cho discovery.

## 5. Dừng plugin theo thứ tự an toàn

Một quy trình unload nên thực hiện theo thứ tự:

1. Chặn request mới đến plugin.
2. Đánh dấu plugin đang dừng để host không cấp thêm callback hoặc task.
3. Chờ các request/callback đang chạy hoàn tất hoặc hết thời gian chờ.
4. Gỡ listener, hook, command, route và callback đã đăng ký.
5. Hủy scheduled task và dừng executor do plugin sở hữu.
6. Đóng socket, file, watcher, connection và tài nguyên bên ngoài.
7. Xóa plugin instance khỏi registry và cache của host.
8. Bỏ ServiceLoader, Provider, Stream, Class, Method, MethodHandle, ModuleLayer và ClassLoader tham chiếu đến plugin.
9. Trả quyền điều khiển cho host; class loader chỉ đủ điều kiện được GC nếu không còn strong reference nào khác.

Không nên đóng plugin trước khi host đã ngừng gửi công việc mới. Nếu callback vẫn đang chạy khi plugin bị tháo, nó có thể truy cập tài nguyên đã đóng hoặc tiếp tục giữ class loader sống.

### 5.1. Đóng nhiều plugin mà vẫn cố gắng đóng hết

Khi một manager quản lý nhiều plugin, nên đóng theo thứ tự ngược với thứ tự khởi động và tiếp tục đóng các plugin khác nếu một plugin gặp lỗi:

~~~java
RuntimeException failure = null;

for (int i = activePlugins.size() - 1; i >= 0; i--) {
    try {
        activePlugins.get(i).close();
    } catch (RuntimeException ex) {
        if (failure == null) {
            failure = ex;
        } else {
            failure.addSuppressed(ex);
        }
    }
}

activePlugins.clear();

if (failure != null) {
    throw failure;
}
~~~

Ví dụ trên thể hiện chính sách đóng ngược thứ tự và gom lỗi. Trong ứng dụng thực tế, manager còn cần gỡ plugin khỏi registry, hủy đăng ký listener và chờ tác vụ nền trước khi xóa danh sách instance.

## 6. Những tham chiếu thường khiến plugin không được thu hồi

Garbage collector chỉ thu hồi một object graph khi không còn đường đi mạnh từ GC root. Việc gọi `close()` không xóa các đường tham chiếu mà host hoặc thread khác vẫn đang giữ.

### 6.1. Registry và cache của host

Ví dụ host giữ plugin trong map:

~~~java
Map<String, Plugin> plugins = new HashMap<>();
plugins.put(plugin.id(), plugin);
~~~

Sau khi dừng, nếu không xóa entry, map vẫn giữ plugin instance. Instance lại giữ class của plugin, và class gắn với class loader đã nạp nó.

Gỡ entry khi unload:

~~~java
Plugin plugin = plugins.remove(pluginId);

if (plugin != null) {
    plugin.close();
}
~~~

Trong ứng dụng đồng thời, cần phối hợp việc gỡ registry với trạng thái QUIESCING để không có thread khác lấy lại plugin trong lúc đang đóng.

Các cache khác cũng cần kiểm tra: cache callback, command registry, dependency injection container, router, scheduler, event bus và map lưu metadata.

### 6.2. Listener, callback và lambda

Một event bus thuộc host có thể giữ callback được tạo từ class plugin:

~~~java
eventBus.register(plugin::onEvent);
~~~

Method reference giữ tham chiếu đến receiver. Nếu host không unregister callback, receiver và class loader có thể còn sống.

Nên giữ registration handle:

~~~java
AutoCloseable registration = eventBus.register(plugin::onEvent);

try {
    // Plugin hoạt động.
} finally {
    registration.close();
}
~~~

Nếu plugin đăng ký nhiều listener, lưu các handle và đóng tất cả trong lifecycle cleanup. Không chỉ xóa instance plugin khỏi danh sách chính.

### 6.3. Thread và ExecutorService

Thread đang chạy code plugin có thể giữ stack frame, Runnable, context class loader hoặc ThreadLocal value thuộc plugin. Một thread chưa kết thúc có thể giữ class loader sống.

Plugin nên sở hữu executor của mình và dừng nó khi close:

~~~java
private ScheduledExecutorService executor;

public void start() {
    executor = Executors.newSingleThreadScheduledExecutor();
    executor.scheduleAtFixedRate(
            this::refresh,
            0,
            30,
            TimeUnit.SECONDS);
}

@Override
public void close() {
    ScheduledExecutorService current = executor;
    executor = null;

    if (current == null) {
        return;
    }

    current.shutdownNow();

    try {
        if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Plugin task did not terminate in time");
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
}
~~~

`shutdownNow()` gửi interrupt đến các task đang chạy; task phải hợp tác bằng cách kiểm tra interrupt hoặc thoát khỏi thao tác blocking phù hợp. Timeout không làm một task không hợp tác tự biến mất. Nếu thread còn chạy, plugin class loader vẫn có thể bị giữ.

Không dùng `Thread.stop()` để cưỡng bức dừng plugin. Cách đó không an toàn cho trạng thái dùng chung và không phải cơ chế lifecycle hợp lệ.

### 6.4. Thread context class loader

Một số thư viện dùng thread context class loader (TCCL) để tìm resource hoặc service. Nếu host thread pool đặt TCCL thành loader của plugin rồi không khôi phục, thread pool có thể giữ loader plugin sống.

Khi tạm thay TCCL, lưu và khôi phục giá trị cũ:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    invokePluginCallback();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Nếu plugin tạo thread riêng, nên đặt TCCL có chủ đích và kết thúc thread khi plugin dừng. Không để thread lâu dài của host giữ TCCL trỏ vào plugin đã tháo.

### 6.5. ThreadLocal trên thread dùng chung

ThreadLocal value có thể giữ object plugin trên thread pool tồn tại lâu hơn plugin:

~~~java
private static final ThreadLocal<Object> CONTEXT =
        new ThreadLocal<>();

void handle() {
    try {
        CONTEXT.set(pluginContext);
        doWork();
    } finally {
        CONTEXT.remove();
    }
}
~~~

Phải gọi `remove()` trên chính thread đã đặt value. Plugin không thể tự xóa ThreadLocal value đang nằm trên một thread khác nếu không có cơ chế phối hợp với thread đó. Vì vậy, ưu tiên scope rõ ràng và cleanup trong `finally`.

### 6.6. Static registry, MBean và shutdown hook

Các registry sống lâu thuộc host hoặc JDK có thể giữ object plugin:

- Event bus hoặc logging framework.
- MBean server.
- Shutdown hook.
- JDBC driver được đăng ký toàn cục.
- Timer, scheduler hoặc callback toàn cục.
- Cache static của host chứa Class, Method hoặc plugin instance.

Khi plugin đăng ký tài nguyên vào một registry ngoài quyền sở hữu của nó, phải giữ thông tin để deregister trong `close()`. Chỉ deregister đúng registration do plugin tạo; không xóa tài nguyên của module khác.

Static field bên trong chính plugin không tự tạo GC root. Vấn đề xuất hiện khi một object sống lâu hơn ở phía host/JDK/thread giữ tham chiếu tới object hoặc class plugin.

### 6.7. Reflection và metadata cache

Các đối tượng sau có thể giữ class hoặc loader plugin:

- `Class<?>`
- `Method`, `Constructor`, `Field`
- `MethodHandle`, `MethodType`, `MethodHandles.Lookup`
- Proxy class hoặc proxy instance
- `ServiceLoader.Provider`
- `Module`, `ModuleLayer`, `ClassLoader`

Nếu host cache metadata reflection theo plugin, phải xóa entry khi tháo plugin. Đừng chỉ xóa object instance trong khi vẫn giữ Class hoặc Method trong một cache toàn cục.

## 7. Quản lý ServiceLoader và Provider reference

ServiceLoader có thể cache provider đã được tạo. Các đối tượng `ServiceLoader.Provider`, provider instance và stream từ `ServiceLoader.stream()` cũng có thể giữ class/provider reference.

Khi kết thúc một phiên plugin:

- Không giữ ServiceLoader trong singleton hoặc cache lâu dài của host.
- Đóng hoặc kết thúc phạm vi xử lý stream nếu đang giữ stream.
- Xóa danh sách provider instance.
- Xóa các Provider object hoặc Class<?> đã lưu để hiển thị metadata.
- Không giữ plugin instance trong callback, task hoặc exception cache.
- Chỉ tạo ServiceLoader mới khi cần nạp layer hoặc phiên plugin mới.

`ServiceLoader.reload()` xóa cache provider của chính ServiceLoader đó, nhưng không gỡ listener, dừng thread, xóa provider instance do ứng dụng đã sao chép ra ngoài hoặc loại bỏ tham chiếu đến ModuleLayer. Không dùng `reload()` như một lệnh unload.

Với plugin layer, dùng API chỉ định layer:

~~~java
ServiceLoader<Plugin> services =
        ServiceLoader.load(pluginLayer, Plugin.class);
~~~

Khi đã dừng plugin, bỏ cả ServiceLoader và provider objects. Nếu cần tiếp tục dùng các plugin khác, hãy quản lý ServiceLoader theo từng layer hoặc từng phiên plugin.

## 8. Ví dụ hoàn chỉnh: nạp, chạy và đóng một plugin module

Ví dụ này biên dịch API và host thành các modular JAR nằm trong `host-mods`, còn plugin nằm riêng trong `plugin-mods`. Host tạo child layer từ plugin path, tìm provider, chạy rồi đóng plugin. Phạm vi method kết thúc sẽ giải phóng các local strong reference đến layer và ServiceLoader.

### 8.1. Cấu trúc dự án

~~~text
plugin-demo/
└── src/
    ├── com.example.plugin.api/
    │   ├── module-info.java
    │   └── com/example/plugin/api/Plugin.java
    ├── com.example.plugin.host/
    │   ├── module-info.java
    │   └── com/example/plugin/host/Main.java
    └── com.example.plugin.hello/
        ├── module-info.java
        └── com/example/plugin/hello/HelloPlugin.java
~~~

### 8.2. API module

File `src/com.example.plugin.api/module-info.java`:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

File `src/com.example.plugin.api/com/example/plugin/api/Plugin.java`:

~~~java
package com.example.plugin.api;

public interface Plugin extends AutoCloseable {
    String id();
    void start();
    @Override void close();
}
~~~

### 8.3. Host module

File `src/com.example.plugin.host/module-info.java`:

~~~java
module com.example.plugin.host {
    requires com.example.plugin.api;
    uses com.example.plugin.api.Plugin;
}
~~~

File `src/com.example.plugin.host/com/example/plugin/host/Main.java`:

~~~java
package com.example.plugin.host;

import com.example.plugin.api.Plugin;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) throws Exception {
        runPlugins(Path.of(args[0]));
    }

    private static void runPlugins(Path pluginPath) throws Exception {
        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        ModuleFinder.of(pluginPath),
                        Set.of("com.example.plugin.hello"));

        ModuleLayer pluginLayer = ModuleLayer.boot()
                .defineModulesWithOneLoader(configuration, null);

        ServiceLoader<Plugin> services =
                ServiceLoader.load(pluginLayer, Plugin.class);

        List<Plugin> active = new ArrayList<>();

        try {
            services.forEach(active::add);

            for (Plugin plugin : active) {
                plugin.start();
                System.out.println("started=" + plugin.id());
            }
        } finally {
            RuntimeException failure = null;

            for (int i = active.size() - 1; i >= 0; i--) {
                try {
                    active.get(i).close();
                } catch (RuntimeException ex) {
                    if (failure == null) {
                        failure = ex;
                    } else {
                        failure.addSuppressed(ex);
                    }
                }
            }

            active.clear();
            services = null;
            pluginLayer = null;

            if (failure != null) {
                throw failure;
            }
        }
    }
}
~~~

`ModuleFinder.of()` là finder rỗng ở phía trước parent configuration. Plugin được tìm trong `ModuleFinder.of(pluginPath)`. Boot layer đã chứa API module mà plugin cần. `resolveAndBind` giải quyết plugin module và các provider liên quan; `defineModulesWithOneLoader` tạo child layer với loader phù hợp với boot layer.

Method `runPlugins` giới hạn phạm vi tham chiếu: sau khi đóng plugin, danh sách provider được xóa, ServiceLoader và ModuleLayer không được trả ra ngoài. Khi method kết thúc, các local reference này không còn được giữ bởi host code.

### 8.4. Plugin module

File `src/com.example.plugin.hello/module-info.java`:

~~~java
module com.example.plugin.hello {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.hello.HelloPlugin;
}
~~~

File `src/com.example.plugin.hello/com/example/plugin/hello/HelloPlugin.java`:

~~~java
package com.example.plugin.hello;

import com.example.plugin.api.Plugin;

public final class HelloPlugin implements Plugin {
    private boolean started;

    public HelloPlugin() {
    }

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public void start() {
        if (started) {
            throw new IllegalStateException("Already started");
        }
        started = true;
        System.out.println("Hello from JPMS plugin");
    }

    @Override
    public void close() {
        if (!started) {
            return;
        }
        started = false;
        System.out.println("closed=hello");
    }
}
~~~

### 8.5. Biên dịch và đóng gói

Chạy tại thư mục `plugin-demo`:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.plugin.api,com.example.plugin.host,com.example.plugin.hello

mkdir host-mods
mkdir plugin-mods

jar --create --file host-mods/com.example.plugin.api.jar -C out/com.example.plugin.api .
jar --create --file host-mods/com.example.plugin.host.jar -C out/com.example.plugin.host .
jar --create --file plugin-mods/com.example.plugin.hello.jar -C out/com.example.plugin.hello .
~~~

Chạy host và truyền thư mục plugin:

~~~bash
java --module-path host-mods --module com.example.plugin.host/com.example.plugin.host.Main plugin-mods
~~~

Stdout chính xác:

~~~text
Hello from JPMS plugin
started=hello
closed=hello
~~~

Ví dụ xác nhận plugin được nạp từ module path riêng, tìm bằng ServiceLoader trong child layer, khởi động và nhận lệnh close. Nó không chứng minh class loader đã được GC ngay sau khi method kết thúc; việc đó phụ thuộc toàn bộ tham chiếu còn lại và thời điểm garbage collection.

## 9. Vì sao ModuleLayer không có lệnh unload?

`ModuleLayer` không implement `AutoCloseable` và không có API `unload()`. Module system cho phép tạo layer và truy cập module, nhưng không cung cấp lệnh cưỡng bức xóa class hoặc dừng mọi thread thuộc layer.

Class unloading gắn với class loader. Một class loader có thể đủ điều kiện thu hồi khi:

- Không còn object nào có thể truy cập class loader bằng strong reference.
- Không còn object instance, Class, reflection metadata hoặc callback sống lâu giữ class của plugin.
- Không còn thread đang chạy code plugin hoặc giữ TCCL trỏ đến loader.
- Không còn registry/cache ở host hoặc thư viện bên ngoài giữ object thuộc plugin.
- Không còn ModuleLayer, ServiceLoader hoặc provider reference được giữ từ vùng sống lâu.

Ngay cả khi các điều kiện này đã thỏa mãn, garbage collector vẫn quyết định thời điểm thu hồi. `System.gc()` chỉ là lời gợi ý; nó không bảo đảm class unloading xảy ra ngay hoặc xảy ra trong một khoảng thời gian xác định.

Không nên dùng việc `WeakReference.get() == null` trong một test đơn lẻ làm tiêu chí correctness bắt buộc. Có thể dùng WeakReference trong diagnostic hoặc stress test để quan sát xu hướng, nhưng GC có thể trì hoãn việc thu hồi.

### 9.1. Đóng URLClassLoader không đồng nghĩa unload

Với plugin classpath cũ, `URLClassLoader.close()` đóng các tài nguyên mở để đọc JAR và ngăn loader tiếp tục mở resource mới từ các URL đã đóng. Nó không cưỡng bức unload class, không dừng thread và không xóa tham chiếu do ứng dụng giữ.

Với plugin dùng JPMS ModuleLayer, hãy dùng lifecycle của plugin và bỏ các reference tới layer/loader; đừng giả định loader nội bộ là URLClassLoader để gọi `close()`.

### 9.2. Parent class loader và plugin class loader

Class loader của plugin thường giữ quan hệ cha để nhìn thấy API chung. Parent loader không tự động giữ tất cả child loader. Tuy nhiên, nếu host lưu plugin instance hoặc Class của plugin trong registry thuộc parent loader, object graph từ host sẽ giữ plugin sống.

Thiết kế API nên đặt interface ổn định ở parent layer; implementation nằm ở child layer. Khi unload, host chỉ giữ thông tin thuần như plugin ID, trạng thái hoặc cấu hình không tham chiếu đến class plugin.

## 10. Cách thiết kế PluginManager để không giữ reference

Một PluginManager có thể giữ một handle trong thời gian plugin hoạt động:

~~~java
final class PluginHandle {
    private final String id;
    private final Plugin plugin;

    PluginHandle(String id, Plugin plugin) {
        this.id = id;
        this.plugin = plugin;
    }

    String id() {
        return id;
    }

    void stop() {
        plugin.close();
    }
}
~~~

Khi tháo plugin, manager phải xóa handle khỏi registry:

~~~java
PluginHandle handle = registry.remove(pluginId);

if (handle != null) {
    handle.stop();
}
~~~

Ví dụ trên chỉ minh họa ownership cơ bản. Một manager thực tế còn giữ layer và ServiceLoader trong một đối tượng phiên plugin; khi đóng phiên, nó phải:

- Ngừng cấp request mới.
- Chờ các lời gọi đang chạy.
- Gọi close cho provider.
- Hủy các registration handle.
- Dừng executor và thread.
- Xóa provider list và ServiceLoader.
- Xóa PluginHandle khỏi registry.
- Xóa reference tới ModuleLayer và ClassLoader.
- Không trả các object plugin hoặc Class ra cache của host.

Nếu API trả một object plugin cho nhiều consumer, cần xác định rõ consumer phải ngừng sử dụng object đó trước khi unload. Một plugin không thể an toàn bị tháo trong khi thread khác vẫn đang gọi method của nó.

## 11. Hot reload an toàn

Hot reload thường nên tạo một phiên plugin mới trước, chuyển traffic sang phiên mới, rồi dừng phiên cũ:

1. Nạp module và tạo layer mới.
2. Khởi tạo provider mới, kiểm tra health.
3. Chuyển registry/route sang plugin mới.
4. Chặn request mới đến plugin cũ.
5. Chờ request cũ hoàn tất.
6. Đóng plugin cũ và tài nguyên của nó.
7. Gỡ listener, task, cache và handle cũ.
8. Bỏ ServiceLoader, provider, layer và loader cũ.

Trong thời gian chuyển đổi, hai phiên plugin có thể cùng tồn tại. Cần có giới hạn số phiên, timeout cho shutdown và chính sách rollback nếu plugin mới không khởi động được.

Không thay thế một class loader đang phục vụ request bằng cách sửa registry ngay lập tức rồi giả định các thread cũ tự dừng. Các request đã lấy reference tới plugin cũ vẫn có thể tiếp tục chạy.

## 12. Checklist tìm memory leak sau khi unload

Khi plugin đã close nhưng bộ nhớ không giảm hoặc class loader vẫn còn sống, kiểm tra theo thứ tự:

- [ ] Plugin đã ngừng nhận request và callback mới chưa?
- [ ] Các request/callback đang chạy đã hoàn tất chưa?
- [ ] Plugin instance đã bị xóa khỏi mọi registry và cache của host chưa?
- [ ] Listener, event handler, command, route và callback đã unregister chưa?
- [ ] Executor đã shutdown và thread đã kết thúc chưa?
- [ ] Thread context class loader trên thread dùng chung đã được khôi phục chưa?
- [ ] ThreadLocal value đã được remove trên đúng thread chưa?
- [ ] Timer, scheduler, watcher, socket và resource đã đóng chưa?
- [ ] MBean, logging handler, shutdown hook hoặc JDBC driver đã deregister chưa?
- [ ] ServiceLoader, Provider, Stream và danh sách provider đã được bỏ chưa?
- [ ] Cache Class, Method, MethodHandle, Proxy hoặc Module của plugin đã được xóa chưa?
- [ ] PluginManager đã bỏ ModuleLayer và ClassLoader reference chưa?
- [ ] Có exception, future hoặc task queue đang giữ stack/object của plugin không?

Heap dump và công cụ phân tích heap có thể giúp tìm đường tham chiếu từ GC root đến class loader. Hãy xem retained path thay vì chỉ xem số lượng instance. Một object plugin còn sống là hệ quả; retained path mới chỉ ra nơi đang giữ nó.

## 13. Các lỗi thiết kế thường gặp

### Chỉ gọi close nhưng giữ plugin trong map

Plugin đã ngừng hoạt động nhưng map vẫn giữ instance và loader. Hãy xóa registry sau khi đã ngừng nhận request và hoàn tất cleanup.

### Giữ ServiceLoader trong singleton

ServiceLoader giữ cache provider và tham chiếu đến phạm vi discovery. Hãy giới hạn ServiceLoader theo phiên layer và bỏ nó khi unload.

### Dùng executor chung nhưng không xóa task plugin

Executor host còn sống và queue có thể giữ Runnable/lambda của plugin. Hãy hủy task đã đăng ký và bỏ callback khỏi queue khi plugin dừng.

### Thread pool giữ TCCL của plugin

Một thread host có thể giữ class loader plugin qua context class loader. Khôi phục TCCL sau mỗi tác vụ.

### Dùng ThreadLocal nhưng không remove

Thread pool tái sử dụng thread; value cũ vẫn nằm trên thread và giữ object plugin. Đặt `remove()` trong `finally`.

### Nghĩ ModuleLayer có unload API

ModuleLayer không có `close()` hoặc `unload()`. Hãy thiết kế cleanup và giải phóng tham chiếu để class loader đủ điều kiện được GC.

### Ép GC trong production để unload

`System.gc()` không bảo đảm thời điểm thu hồi và có thể gây ảnh hưởng hiệu năng. Sửa retained reference và để GC quản lý bộ nhớ.

### Dùng WeakHashMap như cách chữa mọi memory leak

Weak key không giúp nếu value giữ ngược key hoặc một object khác trong cùng graph. Hãy xác định rõ ownership và đường tham chiếu.

## Tóm tắt

Vòng đời plugin cần được quản lý từ lúc discovery đến lúc dừng và tháo khỏi host. Khi dùng JPMS, `ModuleLayer` tạo phạm vi module và loader riêng; `ServiceLoader.load(layer, service)` tìm provider trong layer đó. Để plugin đủ điều kiện được thu hồi, phải ngừng công việc, đóng tài nguyên, gỡ listener, dừng thread/executor, khôi phục TCCL, xóa ThreadLocal và bỏ registry/cache, ServiceLoader, provider, Class, ModuleLayer cùng ClassLoader reference. JPMS không có lệnh unload cưỡng bức; class unloading do GC thực hiện khi không còn strong reference.

## Tài liệu tham khảo chính thức

- [Java SE 26 API — ModuleLayer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 26 API — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 26 API — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 26 API — Configuration.resolveAndBind](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/Configuration.html)
- [Java SE 26 API — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 26 API — WeakReference](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/WeakReference.html)
- [Java SE 26 API — ThreadLocal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java Language Specification 26 — §7.7 Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
