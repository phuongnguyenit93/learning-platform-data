# Khởi tạo plugin và quản lý context class loader trong Java

Một ứng dụng có hệ thống plugin thường phải **nạp bytecode của plugin bằng loader riêng**, tạo instance plugin, gọi các hook vòng đời như `start()`/`stop()` và cho phép plugin khám phá implementation hoặc resource thuộc phạm vi của chính nó. Vấn đề là nhiều API nền tảng và framework có thể được **định nghĩa ở loader cha**, còn provider, config hay tài nguyên của plugin lại nằm trong **loader con**. Parent-first delegation giúp child tìm API ở parent, nhưng parent không tự nhìn xuống mọi child loader.

**Thread Context ClassLoader (TCCL)** là cơ chế cho phép code đang chạy trên **một thread** nói rõ “các API có hỗ trợ context-based lookup nên dùng loader nào cho tác vụ hiện tại”. Trong quá trình khởi tạo plugin, host có thể **tạm đặt TCCL = plugin loader**, gọi constructor/start hooks, rồi **khôi phục TCCL cũ trong `finally`**. Điều quan trọng hơn là phải xác định đúng **lúc nào cần context**, tránh leak qua thread pool, và đảm bảo loader không bị đóng trong khi plugin vẫn cần nạp class/resource.

Bài này thuộc nhóm **Kiến trúc plugin** trong Java core – classloader. Mục tiêu là thiết kế chu trình khởi tạo và hủy plugin có ranh giới rõ, hiểu sự khác biệt giữa defining loader và TCCL, triển khai mẫu Java 17+ có thể biên dịch/chạy, phân tích plugin SPI discovery, executor/thread, JPMS và hot reload, đồng thời xử lý lỗi lifecycle một cách có thể kiểm chứng.

## 1. Ba bối cảnh loader cần tách riêng

Có ba quan hệ thường bị gộp thành một:

| Khái niệm | Gắn với gì? | Dùng để làm gì? |
| --- | --- | --- |
| **Defining loader** | Mỗi `Class<?>` đã được JVM định nghĩa | Xác định runtime type identity và nguồn class; `type.getClassLoader()` |
| **Parent loader** | Quan hệ delegation của một `ClassLoader` | Child hỏi parent trước theo mô hình parent-first; `loader.getParent()` |
| **Thread context class loader** | Mỗi `Thread` | API chủ động đọc TCCL có thể dùng nó để tìm providers/classes/resources của ngữ cảnh hiện tại |

Cần ghi nhớ:

- **Đổi TCCL không đổi defining loader của class đã nạp.** Nếu `host.PluginManager` do system loader định nghĩa, đổi TCCL không làm class đó được nạp lại bởi plugin loader.
- **Đổi TCCL không sửa `getParent()`.** Plugin loader vẫn có parent được chỉ định khi tạo loader.
- **Không phải mọi API đều đọc TCCL.** `ServiceLoader.load(Service.class)` dùng TCCL theo hợp đồng Java 17; `Class.forName(String)` dùng defining loader của class chứa lời gọi, còn `Class.forName(name, boolean, loader)` dùng loader được truyền.
- **TCCL có phạm vi thread.** Một request trên thread A không tự thay TCCL của thread B đang chạy trong executor.
- **Loader chọn lúc discovery khác loader thực sự định nghĩa class kết quả.** Plugin loader có thể delegate `api.Plugin` cho parent, dù nó tự define `plugin.Entry`.

Vì vậy, khi một class không được tìm thấy, cần xác định **API lookup cụ thể** và **class/thread gọi nó**, chứ không mặc định luôn đổi TCCL.

## 2. Bài toán kiến trúc plugin thực tế

Giả sử host cung cấp hai interface:

- `api.Plugin`: contract gồm `start()` và `stop()`.
- `api.Greeting`: một SPI mà plugin có thể cung cấp provider.

Một plugin chứa:

- `plugin.Entry` implements `api.Plugin`.
- `plugin.GreetingProvider` implements `api.Greeting`.
- Descriptor `META-INF/services/api.Greeting` chứa tên `plugin.GreetingProvider`.

Đồ thị classloader:

```text
             [Application/System Loader]
               |               |
           api.Plugin       api.Greeting
               |               |
               +-------+-------+
                       ^
                       | parent-first
                       |
               [Plugin URLClassLoader]
                       |
                       +-- plugin.Entry
                       +-- plugin.GreetingProvider
                       +-- META-INF/services/api.Greeting
```

Host **phải** dùng chung `api.Plugin`/`api.Greeting` giữa host và plugin, vì JVM nhận diện một type bằng **binary name + defining loader**. Nếu mỗi plugin tự define bản `api.Plugin` khác, ép kiểu instance plugin về `api.Plugin` của host có thể thất bại dù tên interface và source code giống hệt.

Tại sao TCCL hữu ích? Vì `plugin.Entry.start()` có thể gọi `ServiceLoader.load(Greeting.class)` để tìm implementation chỉ có ở plugin loader. Nếu TCCL lúc đó vẫn là host loader, discovery có thể không thấy `META-INF/services/api.Greeting` của plugin. Nếu TCCL được tạm đặt là plugin loader, ServiceLoader có đường đúng để tìm metadata/provider.

**Nhưng** không nên biến TCCL thành một “biến toàn cục” cho toàn JVM; nếu host chạy nhiều plugin, mỗi tác vụ cần dùng loader **đúng của plugin đang phục vụ**, rồi phải trả lại context trước khi thread được tái sử dụng.

## 3. Trình tự khởi tạo plugin nên như thế nào?

Một chu trình đơn giản:

```text
Đọc/kiểm tra plugin artifact
       |
       v
Tạo ClassLoader mới, parent = shared API loader
       |
       v
Load entrypoint class bằng plugin loader
       |
       v
Kiểm tra entrypoint implement đúng api.Plugin
       |
       v
Lưu original TCCL của thread hiện tại
       |
       v
Đặt TCCL = plugin loader
       |
       +-- khởi tạo entrypoint instance
       |   (constructor, class initialization khi JVM yêu cầu)
       |
       +-- gọi plugin.start()
       |   (SPI, resources, framework initialization)
       |
       +-- đăng ký listener/task/provider khi start thành công
       |
       v
Khôi phục original TCCL trong finally
       |
       v
Plugin RUNNING; host giữ loader + instance + lifecycle handle
```

**Không đóng `URLClassLoader` ngay sau constructor/start** nếu plugin còn phải chạy sau đó. `close()` ngăn nạp class/resource mới từ các URL của loader; các class đã load có thể tiếp tục hoạt động nhưng dependency được lazy-load về sau có thể thất bại.

Phân chia rõ các giai đoạn:

1. **Prepare:** xác minh nguồn JAR, version/API compatibility, quyền chạy, dependency và đường resource; lập namespace plugin.
2. **Load/verify:** dùng loader đã tạo để tìm entrypoint, kiểm tra `Plugin.class.isAssignableFrom(entryClass)`.
3. **Initialize/start:** đặt context thích hợp, tạo instance và gọi hook `start()`; có rollback khi lỗi.
4. **Active:** quản lý các request/tasks gọi vào plugin, luôn mang context đúng trong phạm vi cần thiết.
5. **Stop/dispose:** ngừng nhận công việc mới, chờ/hủy tasks, đặt đúng context để gọi `stop()`, unregister listener/provider/cache, close loader rồi bỏ strong references.

Một entrypoint class **được load** chưa chắc đã **được initialized**. `ClassLoader.loadClass` thường chỉ load class; initializer `<clinit>` có thể chạy khi code thực sự tạo instance hoặc thực hiện thao tác Java yêu cầu initialization. Nếu initializer dùng API dựa trên TCCL, **đặt TCCL trước khi tạo instance**, không phải sau constructor.

## 4. Mẫu Java 17+ chạy được: host và plugin tách classpath

Đây là chương trình độc lập dùng `URLClassLoader`, `ServiceLoader`, hai interfaces chung và một provider descriptor. Ví dụ đã được biên dịch bằng `javac --release 17` và chạy thành công.

### 4.1 Cấu trúc

Tạo thư mục `plugin-context-demo`:

```text
plugin-context-demo/
├── host-src/
│   ├── api/
│   │   ├── Plugin.java
│   │   └── Greeting.java
│   └── host/
│       └── Launcher.java
├── plugin-src/
│   └── plugin/
│       ├── Entry.java
│       └── GreetingProvider.java
├── host-classes/                         (output host)
└── plugin-classes/
    ├── plugin/
    │   ├── Entry.class
    │   └── GreetingProvider.class
    └── META-INF/
        └── services/
            └── api.Greeting                (service descriptor UTF-8)
```

Tạo `host-classes` và `plugin-classes/META-INF/services` trước khi chạy lệnh. **Không thêm `plugin-classes` vào runtime classpath của host**, vì ta muốn chứng minh plugin class/resource chỉ có trong loader riêng.

### 4.2 API contract chung

File `host-src/api/Plugin.java`:

```java
package api;

public interface Plugin {
    void start();
    void stop();
}
```

File `host-src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String text();
}
```

Host biên dịch và định nghĩa hai interfaces. Plugin được biên dịch **against** `host-classes` và lúc chạy delegate về parent để dùng đúng một bản `api.Plugin`/`api.Greeting`.

### 4.3 Provider của plugin

File `plugin-src/plugin/GreetingProvider.java`:

```java
package plugin;

import api.Greeting;

public final class GreetingProvider implements Greeting {
    @Override
    public String text() {
        return "Hello from provider";
    }
}
```

File **`plugin-classes/META-INF/services/api.Greeting`** chứa chính xác một dòng:

```text
plugin.GreetingProvider
```

Đây là **file văn bản, không có extension `.txt`**, không phải Java source. Path phải nằm dưới **classpath/resource root của plugin loader**. `ServiceLoader` dùng binary service name `api.Greeting` để tìm descriptor, sau đó đọc provider class name `plugin.GreetingProvider`.

### 4.4 Entrypoint plugin phụ thuộc vào TCCL

File `plugin-src/plugin/Entry.java`:

```java
package plugin;

import api.Plugin;
import api.Greeting;
import java.util.ServiceLoader;

public final class Entry implements Plugin {
    public Entry() {
        System.out.println("entry sees plugin TCCL="
                + (Thread.currentThread().getContextClassLoader()
                    == Entry.class.getClassLoader()));
    }

    @Override
    public void start() {
        Greeting service = ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow();

        System.out.println("plugin started: " + service.text());
    }

    @Override
    public void stop() {
        System.out.println("plugin stopped");
    }
}
```

Tại sao constructor in TCCL? Để xác minh **host đã đổi context trước khi khởi tạo plugin**. Method `start()` gọi `ServiceLoader.load(Greeting.class)`, API theo Java 17 **chọn TCCL**, không nhất thiết chọn defining loader của `Entry`.

`findFirst().orElseThrow()` buộc `ServiceLoader` tìm và instantiate provider đầu tiên. Nếu thiếu descriptor hoặc loader không nhìn thấy provider, method này ném `NoSuchElementException`; nếu metadata/provider không hợp lệ, `ServiceConfigurationError` có thể xuất hiện khi duyệt.

### 4.5 Launcher tạo loader, tạm đặt TCCL và restore

File `host-src/host/Launcher.java`:

```java
package host;

import api.Plugin;
import api.Greeting;
import java.net.URLClassLoader;
import java.net.URL;
import java.nio.file.Path;
import java.util.ServiceLoader;

public class Launcher {
    public static void main(String[] args) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        System.out.println("host providers="
                + ServiceLoader.load(Greeting.class).stream().count());

        URL url = Path.of("plugin-classes").toUri().toURL();

        try (URLClassLoader pluginLoader =
                new URLClassLoader(
                        new URL[]{url},
                        ClassLoader.getSystemClassLoader())) {

            Class<?> clazz = pluginLoader.loadClass("plugin.Entry");

            System.out.println("same API="
                    + Plugin.class.isAssignableFrom(clazz));

            thread.setContextClassLoader(pluginLoader);
            try {
                Plugin plugin = (Plugin) clazz
                        .getDeclaredConstructor()
                        .newInstance();

                plugin.start();
                plugin.stop();
            } finally {
                thread.setContextClassLoader(original);
            }
        }

        System.out.println("restored="
                + (thread.getContextClassLoader() == original));

        System.out.println("host providers after="
                + ServiceLoader.load(Greeting.class).stream().count());
    }
}
```

Giải thích design choices:

- `Plugin.class.isAssignableFrom(clazz)` xác nhận class entrypoint triển khai **chính interface mà host dùng**, không phải một bản duplicate do child define.
- `pluginLoader.loadClass("plugin.Entry")` tìm class qua URL/plugin namespace; thao tác này không tự bảo đảm đã chạy static initializer. TCCL được đặt **trước khi invoke constructor**.
- `ClassLoader.getSystemClassLoader()` làm parent để plugin resolve được API `api.Plugin` và `api.Greeting`.
- `thread.setContextClassLoader(pluginLoader)` gắn context với thread hiện tại; các API dùng TCCL như `ServiceLoader` sẽ dùng đúng plugin loader khi `start()` chạy.
- `finally` restore original kể cả khi constructor/`start()`/`stop()` ném exception.
- `try-with-resources` đóng loader **sau khi** đã gọi `stop()` trong demo ngắn hạn.
- Mục đích demo là quan sát context, **không phải toàn bộ production plugin manager**. Với plugin thực tồn tại nhiều giờ, host phải giữ loader đang mở xuyên suốt state RUNNING và chỉ close sau toàn bộ cleanup.

### 4.6 Biên dịch và chạy

Từ thư mục `plugin-context-demo`, dùng JDK 17 trở lên:

```bash
javac --release 17 -d host-classes host-src/api/Plugin.java host-src/api/Greeting.java host-src/host/Launcher.java
javac --release 17 -cp host-classes -d plugin-classes plugin-src/plugin/GreetingProvider.java plugin-src/plugin/Entry.java
java -cp host-classes host.Launcher
```

Các lệnh chỉ cần một classpath entry tại mỗi thời điểm, nên cú pháp dùng được trên Windows/Linux/macOS. File SPI descriptor cần được tạo **đúng tên và đường dẫn** trước khi chạy.

Stdout chính xác đã kiểm tra:

```text
host providers=0
same API=true
entry sees plugin TCCL=true
plugin started: Hello from provider
plugin stopped
restored=true
host providers after=0
```

### 4.7 Ý nghĩa của từng dòng output

- `host providers=0`: loader của host không tìm thấy `api.Greeting` provider vì provider chỉ nằm trong `plugin-classes` chưa có trên host classpath.
- `same API=true`: plugin `Entry` implements đúng `api.Plugin` do parent/system loader định nghĩa, cho phép host cast.
- `entry sees plugin TCCL=true`: ngay lúc constructor chạy, thread context chính là plugin loader.
- `plugin started: Hello from provider`: `ServiceLoader.load(Greeting.class)` đọc `META-INF/services/api.Greeting` qua TCCL, định vị provider và gọi implementation.
- `plugin stopped`: hook stop được gọi trước khi host close loader.
- `restored=true`: TCCL thread đã trở lại giá trị ban đầu.
- `host providers after=0`: sau khi restore, discovery bên host lại dùng context ban đầu, không tự “thấy” provider của plugin.

**Không nhầm kết quả cuối với unloading:** `host providers after=0` chỉ chứng minh context discovery đã restore. Nó **không** chứng minh JVM ngay lập tức unload các class/plugin loader hoặc thu hồi metaspace.

### 4.8 Điều gì xảy ra nếu quên đổi TCCL?

Nếu `Launcher` không gọi `thread.setContextClassLoader(pluginLoader)` trong khi `Entry.start()` vẫn dùng `ServiceLoader.load(Greeting.class)`, lời gọi discovery có thể sử dụng **host/system loader** (theo context ban đầu của ví dụ). Nó không thấy descriptor của plugin, vì vậy `findFirst()` không có phần tử và `orElseThrow()` ném `NoSuchElementException`.

Nếu bỏ `finally` restore, dòng `restored` có thể trở thành `false`, và những tác vụ host sau đó có thể bị hướng tới provider namespace của plugin đã dừng. Đây là lỗi isolation/lifecycle, không phải feature hot reload.

## 5. TCCL trong constructor, static initializer và start hook

Khi khởi tạo plugin, ba điểm có thể chạy code tùy biến:

1. **Class initialization:** JVM chạy static field initializers/`static { ... }` khi class lần đầu được khởi tạo.
2. **Constructor:** tạo object plugin, có thể đọc config, đăng ký callback, gọi service discovery.
3. **Start hook:** khởi động thread/scheduler, service provider, connection hoặc tài nguyên khác.

Nếu bất kỳ điểm nào chủ động dùng `Thread.currentThread().getContextClassLoader()` hoặc API đọc TCCL, thì context phải được chọn **trước khi thao tác đó bắt đầu**.

Ví dụ class plugin:

```java
package plugin;

public final class ContextCheck {
    static {
        System.out.println("TCCL in clinit = "
                + Thread.currentThread().getContextClassLoader());
    }

    public ContextCheck() {
        System.out.println("TCCL in constructor = "
                + Thread.currentThread().getContextClassLoader());
    }
}
```

Đây là **class minh họa**, không bao gồm chương trình `main`. Nếu host chỉ gọi `pluginLoader.loadClass("plugin.ContextCheck")` trước khi set TCCL, static block **chưa chắc chạy**. Nếu host gọi `Class.forName(name, true, pluginLoader)` hoặc constructor trước khi set TCCL, static block có thể chạy với context sai và đã gây side effect không thể hoàn tác chỉ bằng đổi loader sau đó.

Cách host chọn loader và thời điểm init có thể viết:

```java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    Class<?> entry = Class.forName(
            "plugin.Entry", true, pluginLoader);
    Object instance = entry.getDeclaredConstructor().newInstance();
    // Gọi plugin.start() và framework initialization tại đây.
} finally {
    t.setContextClassLoader(previous);
}
```

Đây là **đoạn minh họa trong method có xử lý reflection exceptions**, giả định `pluginLoader` có sẵn. Đặt `initialize=true` có chủ đích khi muốn class initializer được chạy ngay trong context đang quản lý. Nếu không muốn static initialization quá sớm, có thể dùng `false` và chỉ init khi thực sự tạo instance.

**Chọn TCCL không thay thế chính sách khởi tạo class.** `Class.forName(String)` có loader mặc định của **class chứa call site**, không tự dùng TCCL. Khi host cần class do plugin định nghĩa, truyền loader explicit hoặc dùng `pluginLoader.loadClass`.

## 6. Viết helper để tránh quên restore

Trong code có nhiều entrypoints, nhân bản `try/finally` ở khắp nơi dễ gây quên. Có thể đóng gói thành helper nhận `ClassLoader` và `Callable<T>`:

```java
import java.util.concurrent.Callable;

public final class ContextLoaders {
    private ContextLoaders() { }

    public static <T> T withContext(
            ClassLoader loader, Callable<T> action)
            throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        try {
            thread.setContextClassLoader(loader);
            return action.call();
        } finally {
            thread.setContextClassLoader(original);
        }
    }
}
```

Đây là **class đầy đủ có thể biên dịch bằng Java 17**. Cách sử dụng, giả định `pluginLoader` và `Plugin plugin` đã có:

```java
ContextLoaders.withContext(pluginLoader, () -> {
    plugin.start();
    return null;
});
```

Helper này cung cấp vài bảo đảm:

- Original TCCL được lưu lại **của chính thread thực thi action**.
- Không có biến global chứa context.
- Restore diễn ra dù action ném checked exception, runtime exception hoặc error; `finally` vẫn được thực thi theo semantics Java (trừ các sự cố kết thúc JVM/tiến trình bất thường).
- Có thể dùng nested call: outer đặt loader A, inner đặt B, inner restore về A, outer restore về original.

Giới hạn:

- `Callable<T>` là **đồng bộ**: nó đặt TCCL cho khoảng thời gian `action.call()` chạy trên thread hiện tại.
- Nếu action **khởi chạy asynchronous task** rồi trả ngay, context của future task cần được quản lý riêng; helper không tự “truyền context qua executor”.
- Nếu thread có `SecurityManager` đặc biệt hoặc chính sách runtime giới hạn `setContextClassLoader`, có thể phát `SecurityException`; cần xử lý theo môi trường Java 17 cụ thể.
- Không để plugin code giữ tham chiếu tới thread/loader theo cách gây leak.

### Tại sao không sửa `Thread.currentThread()` một lần ở startup?

Vì thread pool sử dụng nhiều worker threads và nhiều plugin/request khác nhau. TCCL là trạng thái gắn với từng thread và có thể bị framework đổi ở các điểm khác nhau. Thiết lập một lần ở main thread **không bảo đảm** mọi background worker đang chạy có TCCL đúng khi xử lý công việc.

## 7. ExecutorService và lỗi lan truyền ngữ cảnh

`Thread` thông thường có thể **kế thừa TCCL** từ thread tạo ra nó khi tạo thread. Nhưng thread pool worker được **tạo và tái sử dụng**; worker có thể đã tồn tại **trước** khi host set TCCL cho một request/plugin, hoặc có thể bị tác vụ trước sửa context rồi không restore.

Đây là vấn đề:

```java
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(() -> {
    // KHÔNG được mặc định TCCL == pluginLoader.
    useServices();
});
```

Đây là **đoạn minh họa**, giả định `executor`/`pluginLoader`/`useServices()` có sẵn. Việc set TCCL trên **thread submit** không sửa context của một **worker thread đã tồn tại**.

Một pattern đúng:

```java
executor.submit(() -> {
    Thread t = Thread.currentThread();
    ClassLoader before = t.getContextClassLoader();
    try {
        t.setContextClassLoader(pluginLoader);
        return ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow().text();
    } finally {
        t.setContextClassLoader(before);
    }
});
```

Đây là **đoạn minh họa** trong code host đã có `executor`, `pluginLoader` và `Greeting`. Nó dùng overload `Callable<String>` của `submit` và trả một `Future<String>`. Nếu muốn quan sát exception, phải gọi `Future.get()`/thiết lập cơ chế error reporting; chỉ `submit` rồi bỏ Future có thể che đi lỗi start/discovery.

**Quan trọng:** để tránh deadlock/race trong lifecycle, plugin manager cần theo dõi futures/tasks thuộc plugin. Không close loader trong khi tác vụ khác đang dùng loader để nạp class hoặc đọc resource.

### Thread được plugin tự tạo

Nếu plugin tự tạo thread trong `start()`, thread mới có thể **kế thừa TCCL của thread đang tạo nó**. Điều này làm provider lookup trong thread plugin có vẻ hoạt động — nhưng khi undeploy, thread còn sống có thể giữ TCCL trỏ tới plugin loader mãi.

Cần có lifecycle chính thức:

- Host hoặc plugin ghi nhận thread/executor ownership.
- `stop()` yêu cầu cancel/interrupt và chờ termination hợp lý.
- Thread pool/task wrapper restore TCCL.
- Dọn `ThreadLocal`, callback và schedulers chứa object plugin.
- Không chỉ dựa vào `URLClassLoader.close()` hoặc `System.gc()`.

**Không khuyến khích tự tạo luồng vô hạn không quản lý** trong plugin. Những daemon threads vẫn có thể giữ reference tới plugin loader dù không ngăn JVM exit.

## 8. Host cần giữ những gì khi plugin chạy?

Một plugin có trạng thái RUNNING thường cần một handle quản lý:

```text
PluginHandle
  |
  +-- pluginId / version / lifecycleState
  +-- URLClassLoader
  +-- api.Plugin instance
  +-- registered services/listeners/callbacks
  +-- owned tasks/executor references
  +-- configuration/module/layer context (nếu có)
  +-- cleanup actions
```

Đây là sơ đồ thiết kế, không phải class Java SE có sẵn.

**Không đóng loader cuối method factory** khi trả instance để host sử dụng dài hạn:

```java
Plugin createPlugin() throws Exception {
    try (URLClassLoader loader =
            new URLClassLoader(urls, parent)) {
        Class<?> clazz = loader.loadClass("plugin.Entry");
        return (Plugin) clazz.getDeclaredConstructor().newInstance();
    }
}
```

Đây là **mã minh họa**, `urls`/`parent`/`Plugin` là thành phần giả định. Bởi `try-with-resources` kết thúc khi return, loader đóng quá sớm. Class/object đã nạp có thể hoạt động ở những đường code sẵn có, nhưng lần đầu cần dependency/resource mới từ plugin URL sau đó có thể thất bại.

Thay vào đó, host giữ loader và instance trong `PluginHandle`; close loader chỉ sau `stop`/unregister/cancel tasks.

## 9. Khởi tạo thất bại và rollback

Startup có thể thất bại ở bất cứ giai đoạn nào:

- Plugin artifact sai tên/thiếu class → `ClassNotFoundException`.
- Entrypoint không implements API → `ClassCastException` hoặc kiểm tra `isAssignableFrom` thất bại.
- Constructor/`<clinit>` lỗi → `InvocationTargetException`, `ExceptionInInitializerError` hoặc linkage errors.
- `ServiceLoader` đọc descriptor sai → `ServiceConfigurationError` khi duyệt.
- Provider thiếu dependency → `NoClassDefFoundError`/`ServiceConfigurationError` tùy ngữ cảnh.
- `start()` ném runtime exception sau khi đã đăng ký một số listeners.
- Hệ plugin khởi động tasks nhưng không hoàn tất trong thời hạn chờ.

Một quy trình rollback nên có thứ tự:

1. Chỉ chuyển state sang **RUNNING** sau khi các điều kiện startup thành công.
2. Ghi nhận từng resource/registration được tạo trong quá trình start để có cleanup tương ứng.
3. Nếu lỗi, **ngừng task/registration đã tạo**, không đợi tới một stop phase chưa chắc được gọi.
4. Gọi cleanup của plugin nếu đối tượng đã tạo và contract cho phép cleanup cả khi start chưa hoàn thành.
5. Luôn restore TCCL của thread hiện tại.
6. Sau khi không còn công việc loader phải phục vụ, close loader và giải phóng host references.
7. Báo lỗi gốc kèm suppressed cleanup exceptions; **không nuốt lỗi start** chỉ vì cleanup có lỗi.

### Ví dụ pseudocode quản lý state

```java
// Các kiểu PluginHandle, Registry và CleanupRegistry do host tự định nghĩa.
PluginHandle handle = preparePlugin(artifact);
boolean started = false;
try {
    withPluginContext(handle.loader(), () -> {
        handle.instance().start();
        return null;
    });
    started = true;
    publishRunning(handle);
} catch (Throwable startupFailure) {
    try {
        stopTasksAndUnregister(handle);
        if (handle.instance() != null) {
            withPluginContext(handle.loader(), () -> {
                handle.instance().stop();
                return null;
            });
        }
    } catch (Throwable cleanupFailure) {
        startupFailure.addSuppressed(cleanupFailure);
    } finally {
        handle.loader().close();
    }
    throw startupFailure;
}
```

**Pseudocode minh họa, không phải Java class hoàn chỉnh**: các method và kiểu như `preparePlugin`/`publishRunning` chưa được khai báo. Mẫu cho thấy ý tưởng rollback và không để cleanup exception che mất nguyên nhân đầu.

Trong code production, cần tránh mâu thuẫn state/race; dùng `try/finally` và cấu trúc cleanup mạnh hơn để đảm bảo **mọi thao tác cần cleanup được thử**, ngay cả khi một bước dọn dẹp đã thất bại. `close()` cũng có thể ném `IOException`, nên phải quản lý suppressed exception.

**Điểm tinh tế:** Nếu `start()` đã thất bại giữa chừng, một `stop()` không được thiết kế cho trạng thái partially initialized có thể ném lỗi tiếp. Plugin API nên xác định rõ có hỗ trợ rollback hay cần từng registration trả một handle để cleanup an toàn.

## 10. Quy tắc đặt context cho các hook lifecycle

| Hoạt động | TCCL nên chọn thế nào? | Vì sao? |
| --- | --- | --- |
| Host đọc metadata an toàn trước load | Thường không cần plugin TCCL | Có thể validate artifact ngoài vùng execution |
| Host gọi `pluginLoader.loadClass` | Không bắt buộc đổi TCCL cho chính `loadClass` | Loader đã explicit; nhưng class init chưa chắc xảy ra |
| Khởi tạo class/constructor plugin | **Plugin loader**, nếu initializer dùng context-aware API | Static init/constructor có thể khám phá resources/providers |
| `plugin.start()` | **Plugin loader** | SPI discovery và framework initialization |
| Host xử lý nghiệp vụ thuần của mình | **Context host trước đó** | Tránh plugin rò vào request không liên quan |
| Callback/event handler của plugin | **Plugin loader** trong khoảng callback | Provider/resource lookup có thể diễn ra muộn |
| Task/executor của plugin | Đặt TCCL **trong worker thread lúc chạy task** | TCCL không tự truyền qua thread pool |
| `plugin.stop()`/cleanup hook | **Plugin loader** khi còn cần resource/provider để dọn | Cleanup có thể dùng class/resource plugin |
| Close loader | Sau khi tasks và cleanup hoàn tất | Tránh race với class/resource loading |
| Unload thực sự | Không điều khiển qua TCCL | Phụ thuộc strong references và GC/JVM |

Bảng là **nguyên tắc thiết kế**, không phải quy định rằng **mọi method đều bắt buộc đọc TCCL**. Nếu plugin chỉ dùng explicit loader hoặc API không dựa context, giữ TCCL host có thể phù hợp. Nhưng nếu contract plugin yêu cầu context, nên thể hiện rõ và nhất quán.

## 11. Một API Java không đồng nghĩa một kiểu lookup

So sánh các API thường gặp trong quá trình start:

| API | Loader/source chọn mặc định | TCCL ảnh hưởng trực tiếp? |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | TCCL của thread đang gọi | **Có**, theo contract |
| `ServiceLoader.load(Service.class, loader)` | Loader được truyền | Không phụ thuộc TCCL cho lựa chọn ban đầu |
| `ServiceLoader.load(layer, Service.class)` | Named modules của layer và ancestors | Dựa vào ModuleLayer, không chỉ TCCL |
| `Class.forName("pkg.Impl")` | Defining loader của **class chứa câu lệnh gọi** | **Không** |
| `Class.forName("pkg.Impl", true, loader)` | Loader được truyền | Không, trừ khi chính bạn truyền giá trị TCCL |
| `pluginLoader.loadClass(name)` | Chính `pluginLoader` và parent delegation | Không mặc định |
| `ClassLoader.getSystemResource(...)` | System loader | Không mặc định |
| `Thread.currentThread().getContextClassLoader().getResource(...)` | Loader trả bởi TCCL | **Có**, do code chọn tường minh |
| `Main.class.getResource("config.json")` | Module/package/defining loader của `Main` | Không tự chọn TCCL |

Điều này giải thích một bug quen thuộc:

```java
// Đoạn code chạy trong host.FrameworkHelper do system loader định nghĩa:
Class<?> type = Class.forName("plugin.Entry");
```

Dù thread đang có TCCL = plugin loader, overload **một tham số** không tự sử dụng nó. Nếu host cần chọn plugin namespace, viết:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("plugin.Entry", true, context);
```

Cả hai là **đoạn minh họa**, yêu cầu caller xử lý `ClassNotFoundException`. Trong plugin manager production, thường tốt hơn là **truyền đúng `PluginHandle.loader()`** thay vì dựa gián tiếp vào TCCL có thể đổi.

## 12. ModuleLayer và plugin theo JPMS

Từ Java 9, một plugin có thể được đóng gói thành **named module** và resolve trong `ModuleLayer` riêng, thay vì chỉ JAR classpath/`URLClassLoader`. Khi ấy phải phân biệt **loader mapping** và **module service discovery**.

Các API:

- `ModuleLayer.defineModulesWithOneLoader(...)`: các modules layer mới chia sẻ loader.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: mỗi module layer mới có loader riêng.
- `layer.findLoader("m.plugin")`: lấy loader được gán cho named module cụ thể.
- `ServiceLoader.load(layer, Service.class)`: tìm providers trong layer và ancestor layers theo JPMS; **không phải classpath SPI discovery từ unnamed modules**.
- `module-info.java` với `uses`/`provides ... with ...`: khai báo service consumption/provision trong explicit named modules.

Ví dụ minh họa descriptor:

```java
module m.plugin {
    requires m.api;
    provides api.Greeting with plugin.GreetingProvider;
}
```

Đây là **file `module-info.java` minh họa**; cần module `m.api` chứa/export `api.Greeting` và cấu hình module path đúng.

Khi plugin hoạt động trong custom layer, **không mặc định cứ set TCCL là giải quyết mọi service discovery**. Có thể cần dùng `ServiceLoader.load(pluginLayer, Greeting.class)`; cũng phải xét module `uses` (đối với caller module phù hợp), exports/opens, read edges và package-to-loader mapping.

Một host có thể dùng TCCL để tích hợp thư viện cũ **đồng thời** dùng `ModuleLayer` explicit cho provider JPMS. Đó là hai cơ chế bổ trợ, không thể thay thế nhau trong mọi ngữ cảnh.

### Có nên gán TCCL cho layer loader?

Nếu một framework legacy chỉ hỗ trợ lookup dựa trên TCCL nhưng plugin được tạo trong custom ModuleLayer, host có thể chọn loader thích hợp của module làm TCCL trong phạm vi framework call. Tuy nhiên loader đó có thể chứa một hoặc nhiều module, và không có bảo đảm nó nhìn thấy **tất cả** module/provider trong layer như overload `ServiceLoader.load(layer, ...)`. Khi muốn khám phá chính xác theo module layer, ưu tiên API module-aware.

## 13. Plugin isolation, security và shared APIs

Khi startup, kiểm tra **shared API identity** trước khi cast; nếu child định nghĩa lại `api.*`, TCCL không sửa được lỗi type identity. Chọn đúng loader khi tìm resource/SPI, nhưng kiểm tra riêng URL resource vì parent-first có thể trả config trùng tên của host. `ClassLoader` và TCCL không tạo sandbox cho plugin không tin cậy; JPMS access rules vẫn có hiệu lực. Kiểm chứng artifact/version và dùng ranh giới process khi yêu cầu cách ly bảo mật.

## 14. Plugin hot reload và memory leak do TCCL

Một lý do rất phổ biến khiến custom classloader không được GC thu hồi sau undeploy là **thread còn giữ TCCL trỏ tới loader cũ**.

Đường tham chiếu ví dụ:

```text
GC root
   |
   v
Thread pool worker vẫn sống
   |
   +-- Thread.contextClassLoader
              |
              v
        OldPluginLoader
              |
              v
       plugin classes / metadata
```

Nếu worker từ tác vụ plugin A **quên restore TCCL**, host có thể close URLClassLoader của A và thậm chí bỏ reference trong registry, nhưng thread vẫn có strong reference tới loader A. Bởi vậy loader và các class do nó định nghĩa **không thể được thu hồi theo kỳ vọng** cho đến khi tham chiếu còn giữ bị giải phóng.

Các nguồn giữ khác cần cleanup:

- Static maps của host chứa provider/`Class<?>`/reflection `Method`.
- `ServiceLoader` cache hoặc provider instance được shared quá deployment scope.
- ThreadLocal values, `InheritableThreadLocal` và executor queues chứa object/plugin class.
- Event listeners, scheduled tasks, callbacks, MBeans, JDBC driver registrations, logging bridges.
- Threads do plugin tạo vẫn chạy khi plugin đã stop.
- JNI global references hoặc native resources nếu plugin có native code.

**`URLClassLoader.close()` không ép class unloading.** Đóng loader giải phóng nguồn URL/JAR handles và ngăn loader định nghĩa class mới từ các URL; metadata của class đã nạp có thể vẫn sống. JLS quy định việc unload phụ thuộc khả năng GC thu hồi defining loader và quyết định JVM, không có deadline.

### Quy trình undeploy/redeploy an toàn hơn

```text
RUNNING
    |
    +-- reject new requests
    +-- stop/await in-flight tasks
    |
    v
STOPPING (TCCL đúng plugin khi gọi stop hooks)
    |
    +-- unregister listeners/providers
    +-- cancel schedulers/threads
    +-- clear deployment-owned caches/ThreadLocals
    |
    v
CONTEXT_CLEANUP
    |
    +-- restore TCCL trên mọi worker có liên quan
    |
    v
CLOSE_LOADER
    |
    +-- URLClassLoader.close()
    |
    v
RELEASE_REFS
    |
    +-- bỏ PluginHandle/instances/Classes/Method references
    |
    v
GC_ELIGIBLE (nếu không còn strong references)
    |
    v
MAY_UNLOAD (khi JVM thực hiện)
```

Hot reload phiên bản mới thường cần **ClassLoader mới**. Việc thay `plugin.jar` trên đĩa không làm loader cũ “định nghĩa lại” cùng một binary class name. Nếu parent đã chứa class plugin trùng tên, loader mới có thể lại delegate parent và không thực sự nhận code mới — hãy kiểm tra `getClassLoader()`.

## 15. Rủi ro nhiều plugin chạy đồng thời

Giả sử host có `PluginA` và `PluginB` với hai loaders riêng. Một request A và request B có thể chạy trên hai threads; mỗi thread chỉ được đặt TCCL của đúng plugin trong khoảng công việc plugin.

**Không lưu loader đang chạy trong static field global** rồi đổi cho mọi request:

```java
// Minh họa anti-pattern; KHÔNG dùng:
static ClassLoader CURRENT_PLUGIN_LOADER;
```

Bởi vì request A có thể đổi giá trị sang loader A trong khi request B đang cần loader B. Ngay cả nếu dùng synchronized, việc “loader hiện tại của toàn JVM” không phù hợp với nhiều plugin song song.

Pattern lựa chọn theo task:

```java
// Pseudocode dùng PluginHandle do host tự định nghĩa.
PluginHandle h = registry.resolve(pluginId);
executor.submit(() -> {
    return ContextLoaders.withContext(h.loader(), () -> {
        return h.instance().process(input);
    });
});
```

Ở đây `PluginHandle`, `registry`, `process` và `input` là **thành phần ứng dụng giả định**; đoạn này minh họa mô hình context per task. Ngoài TCCL, cần quản lý locking/lifecycle để tránh tác vụ sử dụng `h` sau khi plugin đã dừng/loader đã close.

### Có cần tạo thread riêng cho từng plugin?

Không bắt buộc. Thread pool dùng chung có thể hoạt động nếu host gói tất cả invocation bằng context scope và quản lý ownership của tác vụ. Thread pool riêng cho plugin có thể đơn giản hóa isolation/lifecycle, nhưng tốn tài nguyên và vẫn phải shutdown/restore TCCL đúng.

**Quan trọng hơn số thread là scope:** mọi callback, task, SPI lookup và cleanup phải xác định đúng loader/module context trong khoảng thời gian chúng chạy.

## 16. Debug: tìm lỗi ở đâu khi plugin không khởi động?

### 16.1 In loader, module và context tại đúng thời điểm

Có thể thêm đoạn dưới vào constructor hoặc `start()` khi có class `Entry`:

```java
ClassLoader defining = Entry.class.getClassLoader();
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("defining=" + defining);
System.out.println("context=" + context);
System.out.println("same=" + (defining == context));
System.out.println("module=" + Entry.class.getModule());
```

Đây là **đoạn minh họa trong class `Entry`**, kết quả loader `toString()` tùy implementation nên không đưa stdout cố định. `same=false` không luôn là lỗi; chỉ là tín hiệu cần kiểm tra nếu contract plugin yêu cầu context = loader của entry.

### 16.2 Kiểm tra resource SPI được nhìn thấy

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

java.util.Enumeration<java.net.URL> resources =
        loader.getResources("META-INF/services/api.Greeting");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

Đây là **đoạn minh họa trong method xử lý `IOException`**, giả định `loader` khác null và application dùng classpath SPI. Có resource chứng minh descriptor **có thể được nhìn thấy**; không chứng minh provider class/constructor/dependencies đều hợp lệ.

### 16.3 Bảng lỗi và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa đúng tầng |
| --- | --- | --- |
| `ClassNotFoundException: plugin.Entry` | URL/classpath root sai, tên binary sai hoặc parent policy không phù hợp | Xác nhận `plugin/Entry.class` dưới plugin root và loader được dùng |
| `ClassCastException` sang `api.Plugin` | Plugin define bản `api.Plugin` riêng | Đưa shared API vào parent, kiểm tra `isAssignableFrom` |
| `ServiceLoader` trả 0 provider | TCCL sai hoặc thiếu `META-INF/services` / wrong resource root | Chọn explicit plugin loader, kiểm tra descriptor |
| `ServiceConfigurationError` | Descriptor sai, provider thiếu constructor/subtype hoặc initialization lỗi | Đọc cause, metadata/provider class |
| Constructor chạy với context host | TCCL được set sau `newInstance` | Set context **trước** khởi tạo |
| Startup ném exception, TCCL không restore | Thiếu `finally` | Dùng context helper và lifecycle rollback |
| Thread pool lâu lâu thấy provider plugin khác | Worker còn TCCL của request trước | Scope TCCL trong worker task, restore |
| Plugin start được nhưng callback sau đó lỗi resource | Callback được host gọi ngoài plugin context | Wrap mỗi callback ở plugin scope |
| `NoClassDefFoundError` sau close | Loader đóng sớm, dependency mới lazy-resolve hoặc plugin init từng lỗi | Giữ loader mở tới cuối lifecycle, xem cause |
| Hot reload tăng metaspace | Loader cũ vẫn reachable bởi threads/caches/registries | Xem retaining paths, TCCL, lifecycle cleanup |
| Module service không thấy provider | Layer/`uses`/`provides` không phù hợp | Dùng module-aware discovery và graph |
| `InaccessibleObjectException` khi reflection | Thiếu `opens` của named module | Sửa module access, không chỉ đổi TCCL |

Quy trình nhanh:

1. In defining loader của `api.Plugin` và `plugin.Entry`; xác nhận API shared.
2. In TCCL **ngay trong constructor/start/callback/worker** bị lỗi, không chỉ in ở main thread.
3. Nếu ServiceLoader: xác nhận `META-INF/services` ở root và dùng loader discovery đúng.
4. Nếu `Class.forName`: xác nhận overload và caller defining loader; chọn explicit plugin loader khi cần.
5. Nếu module path: kiểm tra layer, named-module service declarations và exports/opens.
6. Nếu lỗi chỉ sau undeploy: kiểm tra loader đã close khi còn callbacks/tasks hay chưa.
7. Nếu loader không unload: phân tích strong references từ thread/TCCL/cache/registry, không suy từ việc `System.gc()` không giải phóng ngay.

## 17. Phân biệt lỗi initialization và lỗi class loading

Khi debug, nhớ rằng “khởi tạo plugin” chứa nhiều thao tác:

**Load class**:

```java
Class<?> clazz = pluginLoader.loadClass("plugin.Entry");
```

Thường chưa yêu cầu static initializer chạy.

**Initialize class**:

```java
Class<?> clazz = Class.forName("plugin.Entry", true, pluginLoader);
```

Yêu cầu class initializer (nếu chưa initialized); có thể gây side effects và lỗi `ExceptionInInitializerError` nếu initializer thất bại.

**Create instance**:

```java
Object instance = clazz.getDeclaredConstructor().newInstance();
```

Yêu cầu constructor hợp lệ, class accessible theo Java/module rules và sẽ khởi tạo class nếu cần. Reflection có thể bọc exception do constructor ném trong `InvocationTargetException`.

**Start plugin**:

```java
((Plugin) instance).start();
```

Gọi code nghiệp vụ có thể tạo resource/thread/provider và cần rollback nếu lỗi.

Bốn đoạn trên là **mã minh họa trong method** với `pluginLoader`/`Plugin` đã được khai báo và exception được xử lý. Nếu `clazz` và `instance` được khai báo trong cùng scope, không lặp lại khai báo biến; tách từng bước chỉ để giải thích thao tác.

Với lỗi static initialization đầu tiên, JVM có thể báo `ExceptionInInitializerError`; những lần sử dụng class erroneous tiếp theo có thể báo `NoClassDefFoundError`. Không giải quyết bằng cách chỉ đổi TCCL sau khi class đã ở trạng thái initialization failure — phải sửa nguyên nhân và thường tạo loader/deployment mới để có một định nghĩa class mới trong lần reload hợp lệ.

## 18. Những nhận định dễ sai

| Nhận định | Giải thích |
| --- | --- |
| “`setContextClassLoader` đổi loader của class đang chạy.” | Không; defining loader của class không đổi. |
| “TCCL là parent loader mới.” | Không; `getParent()` vẫn giữ quan hệ cấu trúc. |
| “Host set TCCL một lần khi boot thì plugin nào cũng đúng.” | Không; nhiều plugin/thread có context khác nhau. |
| “Plugin load xong thì đổi TCCL không còn cần.” | Có thể cần trong constructor, start, callbacks, tasks và stop hooks. |
| “`Class.forName(String)` luôn đọc TCCL.” | Không; mặc định là loader của class caller. |
| “`ServiceLoader.load(Service.class)` dùng system loader.” | Theo Java 17 contract, nó dùng **current thread's TCCL**. |
| “TCCL của thread submit tự đi vào mọi executor worker.” | Không bảo đảm; worker có thể đã tồn tại với context khác. |
| “Đổi TCCL rồi quên restore cũng không sao.” | Có thể trộn providers, tạo lỗi multi-tenant và giữ loader sống. |
| “`close()` của URLClassLoader unload mọi class ngay.” | Không; class unloading phụ thuộc khả năng GC thu hồi defining loader. |
| “Thấy same API=true là plugin hoàn toàn tương thích.” | Chỉ chứng minh interface assignability; còn version/linking/behavior/resource và access checks. |
| “`ServiceLoader.reload()` reload plugin bytecode.” | Không; nó reset provider cache của ServiceLoader instance. |
| “TCCL đủ để sandbox plugin độc hại.” | Không; plugin cần kiểm soát trust/isolation riêng. |
| “Named module nào cũng tìm SPI giống classpath.” | Không; `uses`/`provides`/ModuleLayer có quy tắc riêng. |

## 19. Câu hỏi tự kiểm tra kèm đáp án

**1.** Vì sao plugin loader nên có parent là loader chứa `api.Plugin`?

**Đáp án:** Để plugin và host resolve cùng `Class<api.Plugin>`. Nếu mỗi loader tự define bản API cùng tên, class identity khác và host có thể không cast được.

**2.** Nếu `Entry.start()` gọi `ServiceLoader.load(Greeting.class)`, loader được chọn mặc định là gì?

**Đáp án:** TCCL của thread tại lúc gọi. Không mặc định là defining loader của `Entry` hoặc system loader, trừ khi context hiện tại thực sự trỏ tới loader đó.

**3.** Tại sao phải set TCCL trước constructor của plugin?

**Đáp án:** Constructor và class initializer có thể dùng TCCL hoặc API SPI. Nếu chỉ đổi context sau constructor, các side effects/discovery ở giai đoạn khởi tạo đã chạy với context cũ.

**4.** Nếu host đổi TCCL = plugin loader nhưng gọi `Class.forName("plugin.Entry")` ngay trong host helper, chắc chắn tìm được không?

**Đáp án:** Không. Overload một tham số dùng defining loader của class host caller. Muốn chọn plugin loader, dùng `Class.forName(name, initialize, pluginLoader)` hoặc `pluginLoader.loadClass`.

**5.** Tại sao `try/finally` quan trọng khi gọi `plugin.start()`?

**Đáp án:** Start có thể ném lỗi. `finally` vẫn restore original TCCL, tránh thread giữ context plugin trong các tác vụ host/tenant khác.

**6.** Khi `ExecutorService` có worker tồn tại sẵn, set TCCL ở thread submit đã đủ chưa?

**Đáp án:** Chưa. Phải set/restore trong **worker thread chạy task**, hoặc dùng executor/task wrapper có hợp đồng propagation rõ.

**7.** Nếu plugin tạo thread mới trong khi TCCL của thread hiện tại đang là plugin loader, điều gì có thể xảy ra?

**Đáp án:** Thread mới thường kế thừa TCCL của creator, nên có thể giữ plugin loader lâu hơn vòng đời nếu thread không được dừng. Cần quản lý task/thread và cleanup.

**8.** Vì sao ví dụ chạy `host providers after=0` sau khi khôi phục TCCL?

**Đáp án:** Host discovery lại chọn context gốc không thấy SPI descriptor nằm dưới child plugin loader. Kết quả không chứng minh loader đã GC/unload.

**9.** `URLClassLoader.close()` có nên được gọi ngay sau `plugin.start()` nếu plugin tiếp tục phục vụ request?

**Đáp án:** Không theo thiết kế chung. Những code paths tương lai có thể cần class/resource chưa load. Close sau khi stop/cleanup và không còn task sử dụng loader.

**10.** Lỗi `ClassCastException` giữa plugin `Entry` và host `Plugin` có giải quyết bằng TCCL không?

**Đáp án:** Không trực tiếp. Đó thường là vấn đề type identity/loader sharing. Cần sửa classpath/delegation để plugin dùng cùng API class với host.

**11.** Với plugin named module, phải luôn dùng `ServiceLoader.load(service, pluginLoader)` thay vì overload layer không?

**Đáp án:** Không. Cần xét module graph và API. `ServiceLoader.load(pluginLayer, Service.class)` có semantics tìm provider ở layer và ancestors, phù hợp module-aware discovery; TCCL không thay thế hoàn toàn.

**12.** Sau khi host đã close plugin loader mà vẫn không thấy metaspace giảm, nguyên nhân có thể là gì?

**Đáp án:** Thread/TCCL, plugin instances, class metadata, callback registries, caches hoặc native roots vẫn giữ strong references; JVM cũng có thể chưa thực hiện unloading. Cần kiểm tra retaining paths và GC behavior, không suy rằng close phải unload ngay.

## 20. Checklist production cho plugin startup và context

1. **Artifact:** JAR/plugin bytecode, dependencies, version và source đã được kiểm tra chưa?
2. **Shared contract:** `api.Plugin`, DTOs, service interfaces nằm trong parent loader phù hợp chưa?
3. **Entrypoint:** Host load đúng binary name qua đúng plugin loader và kiểm tra assignability chưa?
4. **Init timing:** Nếu static initialization/constructor dùng SPI, TCCL được đặt **trước init** chưa?
5. **Start hook:** Host gọi `start()` trong đúng context và chỉ đánh dấu RUNNING sau khi thành công chưa?
6. **Restore:** Có `try/finally` ở **mọi** context scope, cả exception path không?
7. **Executor:** Context được đặt trong worker thực thi chứ không chỉ thread submit chưa?
8. **Callbacks:** Listeners/timers/scheduled tasks của plugin được wrap bằng context đúng chưa?
9. **Resource lookup:** Provider descriptor/config ở đúng root; API dùng defining loader hay TCCL?
10. **Error/rollback:** Nếu constructor/start một nửa thất bại, cleanup registrations/tasks/resources được thử đầy đủ chưa?
11. **Stop order:** Reject new requests, await tasks rồi gọi `stop()` với đúng context trước close chưa?
12. **Cleanup:** TCCL, ThreadLocal, ServiceLoader cache, static registries, callbacks đã được gỡ đúng deployment?
13. **Close timing:** `URLClassLoader.close()` sau khi không còn class/resource loading đồng thời chưa?
14. **Reload:** Plugin version mới có loader mới, shared API đúng và không trùng class ở parent?
15. **Modules:** Nếu dùng ModuleLayer, đã giải quyết service discovery, `uses`/`provides`/exports/opens chưa?
16. **Isolation:** Có chính sách trust và không xem class loader/TCCL như security sandbox?
17. **Tests:** Có test provider visibility trước/trong/sau context, error path và thread pool reuse?
18. **Observability:** Có log pluginId, lifecycle phase, defining/context loader và cause để chẩn đoán?

## Kết luận

**Khởi tạo plugin** không chỉ là `loadClass` và gọi constructor. Host cần phối hợp **shared API identity, entrypoint class loading, class initialization, SPI discovery, context management, start/stop lifecycle và cleanup**.

**TCCL là context per thread**, hữu ích khi các API như `ServiceLoader.load(Service.class)` cần tìm provider nằm dưới loader plugin thay vì loader framework/host. Hãy **đặt TCCL đúng trước các thao tác cần context**, **khôi phục bằng `finally`**, đặt lại tại worker/callback thực thi thực tế và quản lý vòng đời loader như một resource sống cùng plugin. Đừng nhầm TCCL với parent/defining loader hoặc trông chờ nó giải quyết mọi lỗi classloading và JPMS.

Tài liệu chính thức Java 17:

- [Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, kế thừa context cho thread mới.
- [ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overload chọn TCCL, SPI, lazy discovery và `reload()`.
- [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation và `getParent()`.
- [Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `Class.forName` và class initialization.
- [URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, loader URL/JAR lifetime.
- [ModuleLayer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): named modules và module-to-loader mapping.
