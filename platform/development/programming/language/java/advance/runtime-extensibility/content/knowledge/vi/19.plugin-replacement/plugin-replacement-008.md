# Tìm tham chiếu giữ class loader từ cache, ThreadLocal, luồng và callback khi thay thế plugin

## 1. Bài toán: plugin đã dừng nhưng loader cũ vẫn còn

Một Java host có thể nạp plugin phiên bản A bằng `URLClassLoader` riêng, rồi thay bằng phiên bản B với một loader mới. Đã gọi `close()` trên loader A, xóa file JAR cũ và không còn thấy chức năng của A trên giao diện, nhưng heap/metaspace vẫn tăng qua mỗi lần deploy. Vấn đề thường **không nằm ở việc JVM quên giải phóng class**: một hoặc nhiều tham chiếu từ đối tượng còn sống vẫn giữ loader A hoặc lớp/instance được nó định nghĩa.

Ví dụ đường giữ tham chiếu (*retaining path*):

```text
GC Root
  -> static field của host
  -> ConcurrentHashMap
  -> plugin callback instance
  -> Class của callback
  -> defining ClassLoader của plugin A
  -> các class / metadata liên quan
```

Một nguồn giữ khác:

```text
GC Root
  -> Java Thread đang sống trong executor pool
  -> contextClassLoader (TCCL)
  -> plugin ClassLoader A
```

Hoặc:

```text
GC Root
  -> Java Thread trong pool
  -> ThreadLocalMap entry.value
  -> object do plugin A định nghĩa
  -> Class / defining loader A
```

Các đường trên là **sơ đồ khái niệm**; tên field và hình dạng nút hiển thị trong heap analyzer phụ thuộc JVM và phiên bản. Bài học tập trung vào việc **tìm, giải thích và loại bỏ những đường tham chiếu có thật** từ cache, `ThreadLocal`, thread và callback, thay vì gọi `System.gc()` hoặc `URLClassLoader.close()` như một phép “force unload”.

**Kết quả mong đợi:** người học phân biệt được resource leak với class-loader retention, xác định ai sở hữu reference, tạo được thí nghiệm Java 17 tái hiện bốn nguồn giữ, biết dùng heap dump/GC roots để điều tra và lập quy trình thay thế plugin không để lại tham chiếu từ phiên cũ.

## 2. Điều kiện cho class unloading: đóng loader chưa đủ

Trong JVM, danh tính runtime của một lớp phụ thuộc **binary name và defining class loader**. Một lớp `com.example.Plugin` thuộc loader A không phải cùng class với lớp trùng tên do loader B định nghĩa. Khi nâng cấp plugin, loader mới có thể tạo định nghĩa class mới trong khi loader cũ vẫn sống.

Điểm cần phân biệt:

- **`URLClassLoader.close()`:** giải phóng các tài nguyên như JAR/file handle mà loader đã mở và ngăn việc sử dụng loader đã đóng để nạp lớp/resource mới theo hợp đồng API. Nó **không** hủy instance, static state, thread hay class đã được định nghĩa.
- **Kết thúc plugin logic:** dừng nhận request, ngừng callback, hoàn tất/cancel công việc, tháo đăng ký với host. Đây là trách nhiệm của ứng dụng; `ClassLoader` không tự thực hiện.
- **Class unloading:** JVM/GC có thể thu hồi metadata class khi không còn các reference giữ loader/class/instance ở trạng thái cần thiết. Không có API Java 17 an toàn kiểu `unloadClass("demo.plugin.X")` cho phép bắt buộc gỡ từng class.
- **File JAR có thể đã đóng nhưng loader vẫn sống.** Một đối tượng `ClassLoader` được giữ trong `static Map` hoặc TCCL vẫn là đối tượng Java reachable ngay cả khi không còn handle hệ điều hành.
- **Không thấy unload ngay không tự nó chứng minh leak.** GC, class unloading và thời điểm thu gom có thể diễn ra muộn; cần phân biệt *chưa GC*, *còn reference chủ đích*, *retention vô tình* và *leak tăng qua các generation*.

Muốn chẩn đoán chính xác, phải đặt câu hỏi: **“Từ GC root nào vẫn đi đến object của loader cũ?”** chứ không chỉ hỏi “Tại sao `close()` không làm heap giảm ngay?”.

## 3. Phân loại bốn nguồn giữ thường gặp

| Nguồn giữ | Chuỗi tham chiếu điển hình | Dấu hiệu trong ứng dụng | Cách giải phóng |
|---|---|---|---|
| Cache/registry của host | `static Map → plugin instance / Class / Method / ClassLoader` | Reload xong nhưng số entry hoặc thế hệ cũ vẫn tăng | Invalidate entry theo plugin ID + generation, clear reference có đúng owner |
| `ThreadLocal` trên thread sống lâu | `Thread → threadLocals → entry.value → plugin object` | Pool đã qua nhiều request mà vẫn giữ class cũ | `remove()` trong **chính thread** đã gọi `set()`, tốt nhất trong `finally` |
| Luồng/TCCL | `Thread → contextClassLoader → plugin loader`; hoặc `Thread → Runnable → plugin` | Worker vẫn chạy/chờ; TCCL hiện tên loader cũ | Restore TCCL; dừng/join worker sở hữu bởi plugin; drain pool/queue |
| Callback/listener/subscription | `host event bus → listener list → plugin listener` | Event không còn cần thiết vẫn gọi hoặc registry còn subscription | `unsubscribe`/remove chính instance; hủy scheduled jobs, chờ callback in-flight |

Một loader có thể bị giữ qua **nhiều** đường đồng thời. Xóa một entry cache không đủ nếu thread pool còn TCCL, và dừng thread cũng không đủ nếu event bus vẫn giữ listener. Heap analyzer thường chỉ hiển thị một số đường ngắn nhất; khi sửa xong một đường có thể xuất hiện đường khác.

Phân biệt **reference trực tiếp tới loader** với **reference tới object do loader định nghĩa**: giữ `Class<?>`, `Method`, `Constructor<?>`, lambda, proxy hoặc plugin instance cũng có thể khiến defining loader không được giải phóng. Không chỉ tìm những field khai báo kiểu `ClassLoader`.

## 4. Cache và static registry: nơi dễ bỏ sót nhất

Host thường dùng cache để tra cứu plugin nhanh:

```java
// Ví dụ phản mẫu (không phải chương trình độc lập).
static final Map<String, Object> PLUGIN_CACHE = new HashMap<>();
PLUGIN_CACHE.put("reporter", pluginInstance);
```

Nếu `PLUGIN_CACHE` thuộc class được application/parent loader định nghĩa và tồn tại suốt vòng đời process, `pluginInstance` có thể giữ loader của plugin cũ. Đổi entry sang version mới chỉ an toàn khi **mọi** reference tới object cũ thực sự biến mất; không nên suy ra điều đó từ một thao tác cập nhật map.

Những loại cache cần kiểm tra:

1. **Instance cache:** `Map<PluginId, Plugin>` hoặc `Map<String,Object>` giữ đối tượng trực tiếp.
2. **Class/reflection cache:** `Class<?>`, `Method`, `Field`, `Constructor<?>`, `MethodHandle`, metadata JSON/DI hoặc annotation scanner trỏ tới class do plugin loader định nghĩa.
3. **Factory/provider registry:** các factory hoặc `ServiceLoader.Provider<?>` có thể giữ provider class hoặc object.
4. **Cache key cũng có thể giữ:** một `Map<Class<?>,Metadata>` giữ class ở khóa ngay cả khi value là cấu trúc của host; `Class<?>` có liên hệ với defining loader.
5. **Value giữ key ngược lại:** thay cache thành `WeakHashMap` không phải giải pháp thần kỳ. Nếu value tham chiếu mạnh tới key hoặc class/loader, chuỗi reachability có thể vẫn tồn tại.
6. **Cache trong thư viện:** serializer, dependency injection, logging, ORM, reflection, bean introspection, template engines hoặc framework event bus có cơ chế cache riêng. Phải kiểm tra API invalidation chính thức của từng thư viện, không đụng reflection vào nội bộ một cách tùy tiện.

Một chiến lược đáng tin cậy là đặt cache theo **lifetime của plugin generation** và có phương thức `close()/clear()` do host gọi khi rút plugin. Còn cache toàn process thì entry cần được gắn tên plugin + generation, xóa chính xác khi teardown. Tránh `clear()` bừa toàn bộ cache dùng chung nếu đang có plugin khác hoạt động.

### Nhận diện trong heap dump

Đường như:

```text
HostRegistry.class (GC root / static field)
  -> registry.cache
  -> ConcurrentHashMap$Node.value
  -> demo.plugin.VersionAHandler
  -> java.lang.Class
  -> URLClassLoader(version A)
```

gợi ý rõ owner là **host registry**, không phải bộ gom rác hay Java class loader. Cần truy ra **ai đã đăng ký**, có đối tượng subscription/handle không và lifecycle nào đáng ra phải gỡ entry đó.

## 5. ThreadLocal: phải dọn ở đúng thread sở hữu value

`ThreadLocal<T>` cung cấp một value riêng cho mỗi thread. API `ThreadLocal.remove()` xóa value **của thread đang gọi**, không phải xóa tất cả giá trị từng được gán ở những thread khác. Đây là điểm quan trọng nhất trong hệ thống dùng executor pool.

Phản mẫu:

```java
// Minh họa bên trong một Runnable thực thi trên pooled worker.
PLUGIN_CONTEXT.set(pluginRequest);
handleRequest();                   // có thể ném exception
// Thiếu PLUGIN_CONTEXT.remove(): worker sống tiếp, value còn giữ.
```

Mẫu đúng:

```java
PLUGIN_CONTEXT.set(pluginRequest);
try {
    handleRequest();
} finally {
    PLUGIN_CONTEXT.remove();       // chạy trên cùng pooled worker
}
```

Hai đoạn trên là **minh họa**, giả sử `PLUGIN_CONTEXT` và `handleRequest` được khai báo trong host. Nếu thread pool tái sử dụng worker cho nhiều request, việc không gọi `remove()` có thể giữ plugin object lâu hơn nhiều so với vòng đời request.

**Bẫy phổ biến:** Sau khi unload plugin, thread quản lý gọi `PLUGIN_CONTEXT.remove()`. Nếu trước đó chính pooled worker đã `set(pluginObject)`, lệnh `remove()` trên thread quản lý **không xóa value của pooled worker**. Phải thực hiện cleanup trên đúng worker, hoặc cho worker kết thúc sau khi hoàn tất công việc; với pool dùng chung, cần cơ chế decorator/cleanup gắn với từng task.

Ở những triển khai OpenJDK thông dụng, cấu trúc nội bộ `ThreadLocalMap` thường chứa key yếu (weak key) nhưng value có thể còn được giữ cho đến khi entry được dọn. Đừng hiểu việc garbage collect đối tượng `ThreadLocal` key là chắc chắn giải phóng value ngay. Đây là chi tiết implementation, không phải lời hứa để thiết kế API; lập trình viên vẫn nên chủ động `remove()`.

### InheritableThreadLocal cũng đáng kiểm tra

`InheritableThreadLocal` có thể truyền giá trị từ thread cha sang thread mới ở thời điểm tạo thread (theo chính sách child value). Nếu value là plugin instance hoặc object chứa loader, một thread do host tạo sau đó có thể bắt đầu với reference tới plugin A ngoài dự kiến. Kể cả khi thread cha đã dọn, thread con vẫn có bản value riêng cần được xử lý. Với thread pools, inheritance còn phụ thuộc thời điểm tạo worker, không phải mỗi request submit; tuyệt đối không dùng nó như request context an toàn mặc định.

## 6. Luồng, TCCL và tác vụ đang chạy

Mỗi `Thread` có **thread context class loader (TCCL)**: đọc bằng `Thread.currentThread().getContextClassLoader()` và thay bằng `setContextClassLoader(...)`. Nhiều framework và `ServiceLoader.load(service)` dùng TCCL để tìm provider/resources. Một plugin có thể tạm gắn loader của mình vào thread để thực thi code trong bối cảnh plugin.

Nếu code quên khôi phục TCCL, pooled worker tồn tại sau plugin unload vẫn có thể giữ loader A:

```text
Host executor (sống xuyên nhiều plugin versions)
  -> worker Thread
  -> contextClassLoader = URLClassLoader(A)
  -> class loader A không thể được xem là đã hết references
```

Mẫu đổi TCCL đúng (mã minh họa, `pluginLoader` và `runPluginTask` được cung cấp bởi caller):

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    current.setContextClassLoader(previous);
}
```

Dùng `try/finally` để bảo đảm restoration khi plugin ném exception. Nếu phía host đã bắt đầu task với TCCL của plugin cũ do phiên trước quên restore, việc chụp `previous` lúc đó rồi “khôi phục” chỉ tái gắn loader cũ. Phải đặt quy tắc **baseline TCCL của worker thuộc host** ở điểm tạo worker hoặc khi quản lý executor.

Thread có thể giữ plugin mà **không cần TCCL**:

- `Thread.target`/Runnable do plugin định nghĩa, thread giữ target trong lifecycle chạy.
- Lambda/closure hoặc method reference capture instance/plugin class.
- Thread đang thực thi method của plugin, stack frame và local variables còn tham chiếu tới plugin object/class.
- `ExecutorService` queue chứa `Runnable`, `FutureTask`, `ScheduledFuture` hoặc `CompletableFuture` có closure giữ plugin.
- Plugin tự tạo thread hoặc `Timer`, background poller, file watcher, scheduler mà không dừng khi unload.
- Thread bị chặn lâu ở I/O/lock hoặc vòng lặp, nên shutdown flag chưa làm thread thoát.

Thường phải dừng **nhận công việc mới**, cancel/drain task liên quan, signal shutdown, chờ finish/join theo timeout và có phương án quarantine nếu plugin không hợp tác. Không nên dùng `Thread.stop()` (deprecated, không an toàn) để cưỡng bức cleanup. Luôn dọn task-owned `ThreadLocal`/TCCL trên đúng worker và tách lifetime của plugin-owned thread khỏi host-owned executor.

## 7. Callback, event bus và subscription: listener là strong reference

Plugin có thể đăng ký callback với host:

```java
// Phản mẫu minh họa, các biến do ứng dụng cung cấp:
eventBus.subscribe("ready", pluginCallback);
// Khi thay plugin, không còn nhớ chính callback/registration đó.
```

Nếu event bus nằm ở host và giữ listener trong danh sách mạnh, `pluginCallback` sẽ sống theo event bus. Một lambda do plugin tạo hoặc method reference như `instance::onEvent` cũng có thể capture plugin instance và giữ loader. Ngay cả khi callback chỉ được gọi rất ít, **việc còn đăng ký** vẫn đủ tạo reference.

Thiết kế hợp đồng đăng ký nên trả một **registration handle**:

```java
// Mẫu API lý tưởng, không phải chương trình độc lập:
AutoCloseable registration = eventBus.subscribe("ready", pluginCallback);
try {
    // Plugin đang active.
} finally {
    registration.close(); // tháo đúng đăng ký/instance cũ
}
```

Trong ứng dụng thật phải bảo đảm `close()` của handle mang ngữ nghĩa unregister và không vô tình xóa subscriber của plugin B. Duy trì **danh sách toàn bộ registration handles theo plugin generation** để teardown có thể thực hiện hoàn chỉnh dù plugin đã mất kết nối với đường code đăng ký ban đầu.

Các nguồn giữ cùng nhóm callback: `PropertyChangeListener`, UI listener, `Flow.Subscription`, observer, MBean callback, JDBC driver registration, event hooks, scheduled timer task, shutdown hook, queue consumer, reactive stream subscription, HTTP/filter/interceptor registry và cron-like scheduler. Mỗi framework có API tháo đăng ký/hủy riêng.

**Race khi teardown:** Remove listener không nhất thiết hủy một callback **đang thực thi**. Cần dừng ingress, chặn registration mới và chờ callback in-flight hoàn tất trước khi đóng loader/resource. Một exception trong callback cũng không được làm host bỏ qua các registration khác cần dọn.

## 8. Chương trình Java 17 chạy độc lập: quan sát bốn đường giữ

Ví dụ gồm **hai source file**. Plugin chứa một `Runnable`; host nạp nó bằng `URLClassLoader` riêng, rồi cố ý giữ callback trong cache, listener list và `ThreadLocal`/TCCL của một host worker. Sau đó host xóa từng reference và kiểm tra lại.

**Điều cần hiểu trước:** chương trình **không** chứng minh GC đã thu gom loader. Trong method `main`, các local variables `pluginLoader`, `cls`, `callback` còn tồn tại trong scope; vì vậy ngay sau cleanup vẫn có thể còn strong references khác. Demo cố ý **chỉ kiểm tra bốn nguồn giữ đã tạo**. Phân tích GC thực tế ở mục 10–11.

### 8.1. Cấu trúc thư mục

```text
loader-roots-demo/
  src/
    plugin/demo/plugin/GreetingCallback.java
    host/demo/app/LeakRootsDemo.java
  build/
    plugin/       (tạo bởi javac)
    host/         (tạo bởi javac)
```

**Tệp `src/plugin/demo/plugin/GreetingCallback.java`:**

```java
package demo.plugin;

public final class GreetingCallback implements Runnable {
    @Override
    public void run() {
        System.out.println("plugin-callback=ready");
    }
}
```

Plugin dùng interface `java.lang.Runnable` có sẵn từ Java platform. Host không cần bản SPI tùy biến ở đây, nhờ đó ví dụ cô lập trọng tâm reference retention.

**Tệp `src/host/demo/app/LeakRootsDemo.java`:**

```java
package demo.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentHashMap;

public final class LeakRootsDemo {
    private static final Map<String, Object> CACHE =
            new ConcurrentHashMap<>();
    private static final List<Runnable> LISTENERS =
            new CopyOnWriteArrayList<>();
    private static final ThreadLocal<Object> REQUEST_CONTEXT =
            new ThreadLocal<>();

    private static String workerHolders(ExecutorService worker,
                                        ClassLoader pluginLoader)
            throws Exception {
        return worker.submit(() ->
                "tl=" + (REQUEST_CONTEXT.get() != null)
                + ",tccl=" + (Thread.currentThread()
                        .getContextClassLoader() == pluginLoader)).get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor(r ->
                new Thread(r, "host-worker"));
        try {
            ClassLoader previousTccl = worker.submit(() ->
                    Thread.currentThread().getContextClassLoader()).get();
            Path pluginDir = Path.of("build/plugin").toAbsolutePath();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] { pluginDir.toUri().toURL() },
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> cls = Class.forName(
                        "demo.plugin.GreetingCallback", true, pluginLoader);
                Runnable callback = cls.asSubclass(Runnable.class)
                        .getDeclaredConstructor().newInstance();
                CACHE.put("plugin", callback);
                LISTENERS.add(callback);
                worker.submit(() -> {
                    REQUEST_CONTEXT.set(callback);
                    Thread.currentThread()
                            .setContextClassLoader(pluginLoader);
                }).get();
                System.out.println("plugin-owned=" +
                        (cls.getClassLoader() == pluginLoader));
                System.out.println("cache-before=" + CACHE.size());
                System.out.println("listeners-before=" + LISTENERS.size());
                System.out.println("worker-before=" +
                        workerHolders(worker, pluginLoader));
                LISTENERS.forEach(Runnable::run);

                CACHE.remove("plugin");
                LISTENERS.remove(callback);
                worker.submit(() -> {
                    REQUEST_CONTEXT.remove();
                    Thread.currentThread().setContextClassLoader(previousTccl);
                }).get();
                System.out.println("cache-after=" + CACHE.size());
                System.out.println("listeners-after=" + LISTENERS.size());
                System.out.println("worker-after=" +
                        workerHolders(worker, pluginLoader));
            }
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
```

**Lưu ý:** chương trình được thiết kế để minh họa nhánh chạy thành công và in các trạng thái xác định. Việc remove cache/listener và reset TCCL/ThreadLocal ở đây không nằm trong một `finally` riêng khi một bước trước đó lỗi; mã teardown production phải bảo đảm cleanup trong `finally` ngay cả khi callback/task ném exception (xem mục 12). `worker.shutdownNow()` chỉ gửi interrupt để cố dừng những tác vụ còn lại, không phải bảo đảm rằng code plugin bất hợp tác sẽ thoát ngay.

### 8.2. Biên dịch/chạy trên Windows PowerShell

Đứng tại thư mục `loader-roots-demo/`, có JDK 17 trở lên:

```powershell
New-Item -ItemType Directory -Force -Path build/plugin,build/host | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/GreetingCallback.java
javac --release 17 -d build/host src/host/demo/app/LeakRootsDemo.java
java -cp build/host demo.app.LeakRootsDemo
```

### 8.3. Biên dịch/chạy trên Linux/macOS

```bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin src/plugin/demo/plugin/GreetingCallback.java
javac --release 17 -d build/host src/host/demo/app/LeakRootsDemo.java
java -cp build/host demo.app.LeakRootsDemo
```

**Quan trọng:** không thêm `build/plugin` vào tham số `java -cp`. Nếu host application loader tìm thấy `demo.plugin.GreetingCallback` qua class path, `URLClassLoader` có thể delegate cho parent phù hợp và test defining-loader mất ý nghĩa. Ở đây parent được chỉ định là platform class loader, còn plugin class được nạp từ URL của child; `Runnable` là API chung do JDK cung cấp.

### 8.4. Stdout chính xác

```text
plugin-owned=true
cache-before=1
listeners-before=1
worker-before=tl=true,tccl=true
plugin-callback=ready
cache-after=0
listeners-after=0
worker-after=tl=false,tccl=false
```

Mã đã được biên dịch thực tế với `javac --release 17` và chạy trong môi trường JDK tương thích; stdout khớp các dòng trên. Không dựa vào thời điểm GC hay thứ tự scheduling ngẫu nhiên: mọi thao tác worker cần thiết đều được chờ bằng `Future.get()`.

## 9. Giải thích ví dụ: reference nằm ở đâu?

**Trước cleanup:**

1. `plugin-owned=true`: `cls.getClassLoader() == pluginLoader`, chứng minh plugin implementation được child loader định nghĩa.
2. `CACHE.put("plugin", callback)` tạo đường `host static Map → plugin instance → Class → pluginLoader`. Dù static Map do host sở hữu, value là object của plugin.
3. `LISTENERS.add(callback)` tạo một đường giữ độc lập từ listener list. Thao tác `LISTENERS.forEach(Runnable::run)` chứng minh callback vẫn được gọi.
4. `REQUEST_CONTEXT.set(callback)` chạy **trên host worker**. Thread pool không kết thúc sau task, nên value có thể tiếp tục ở `ThreadLocalMap` của worker.
5. `setContextClassLoader(pluginLoader)` tạo **đường trực tiếp** từ worker Thread tới loader. `workerHolders` chạy tiếp trên cùng single-thread executor để kiểm tra hai nguồn giữ này.

**Khi cleanup:**

1. `CACHE.remove("plugin")` xóa reference do cache giữ.
2. `LISTENERS.remove(callback)` xóa đúng listener đã đăng ký.
3. Submit task gọi `REQUEST_CONTEXT.remove()` trên **chính worker đã set value**.
4. Khôi phục worker TCCL về `previousTccl` được ghi nhận **trước** khi gắn plugin loader.
5. Đợi `Future.get()` rồi mới đo `worker-after=tl=false,tccl=false`.
6. Ra khỏi `try-with-resources` để gọi `pluginLoader.close()`; shutdown executor ở `finally` ngoài cùng.

**Những gì không thể kết luận từ stdout:** class loader đã được GC thu gom, mọi class của loader đã unload, metaspace đã giảm hoặc heap đã sạch trong JVM thực. Trong demo, local variables và các closure sống trong thời gian nhất định vẫn có thể giữ object. Thêm nữa, VM có thể trì hoãn class unloading ngay cả sau khi bỏ hết reference; không viết assertion `weakRef.get() == null` ngay sau cleanup.

## 10. Tìm đường giữ loader bằng heap dump và GC roots

Trong một ứng dụng đang chạy lâu, cách hiệu quả nhất là phân tích **đường từ GC root tới object của plugin generation cũ**. Ưu tiên môi trường staging/incident được phê duyệt vì heap dump có thể lớn, gây pause và chứa dữ liệu nhạy cảm.

### 10.1. Chuẩn bị một phép thử tái hiện có kiểm soát

1. Chọn một plugin có generation rõ, ví dụ `reporting/v41`. Ghi thời gian install/uninstall và identity của loader, không chỉ tên class.
2. Khởi động host với workload ổn định; tạo plugin A, gọi một số API để cache/callback/threadlocal thực sự được sử dụng.
3. Thay bằng plugin B, gọi teardown của A, bảo đảm không còn request hợp lệ đang dùng A.
4. Quan sát số lượng loader cũ, class count, metaspace và registry size qua nhiều lần reload; đừng dùng một snapshot đơn lẻ làm bằng chứng leak.
5. Chụp heap dump ở những mốc có kiểm soát và phân tích reference tới **A**, tránh lẫn loader B hiện còn hoạt động đúng.

### 10.2. Các lệnh quan sát với JDK/HotSpot

Ví dụ cú pháp trong terminal (thay PID và đường dẫn cho phù hợp):

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /path/to/plugin-retention.hprof
```

- `VM.classloader_stats` hỗ trợ xem class loader và số class mà chúng gắn với loader data trong một số JVM HotSpot. Tên lệnh, chi tiết output và khả năng attach phụ thuộc vendor/JDK/policy.
- `GC.class_histogram` giúp quan sát số object theo class; không thay thế retained-path analysis.
- Heap dump cần đủ disk và quyền đọc; có thể làm ứng dụng tạm dừng, và có thể kích hoạt GC. Hãy tránh thu thập ở môi trường nhạy cảm nếu chưa có quy trình bảo vệ dữ liệu.
- Đối với Java 17 HotSpot có Unified Logging, có thể khởi động test với:

```bash
java -Xlog:class+load=info,class+unload=info -cp build/host demo.app.LeakRootsDemo
```

Lệnh logging là ví dụ bổ sung cho demo; nó phát sinh nhiều log do JVM quyết định, **không có stdout cố định**. Sự xuất hiện sự kiện class unloading là tín hiệu dương; vắng sự kiện trong một khoảng thời gian ngắn chưa chứng minh loader bị leak.

### 10.3. Eclipse MAT hoặc công cụ heap analyzer tương đương

Trình tự điều tra khuyến nghị:

1. Mở heap dump; tìm object type `java.net.URLClassLoader` hoặc custom `PluginClassLoader` và xác định instance thuộc generation A. Khi có nhiều loaders cùng class, kết hợp URL/path, identifier và reference để nhận đúng instance.
2. Chọn **Path to GC Roots** / **Shortest Path to GC Roots** và loại các đường chỉ dựa trên weak/soft/phantom references nếu công cụ cung cấp tùy chọn phù hợp.
3. Đọc đường đi từ root xuống loader hoặc class/instance do loader định nghĩa. Đừng dừng ở tên một `HashMap$Node`; cần lần lên field/registry/owner có thể sửa.
4. Nếu thấy root là **static field**, điều tra chủ sở hữu cache và key/value cụ thể.
5. Nếu thấy root là **Thread**, xem TCCL, `threadLocals`/`inheritableThreadLocals`, stack local, Runnable/target và task queue.
6. Nếu thấy root là **event bus** hoặc subscriber registry, truy ra registration handle, listener list, callback active và cơ chế unsubscribe.
7. Sau khi sửa một đường, chụp lại snapshot ở điều kiện tương tự; loader có thể còn đường giữ thứ hai chưa thấy ở lần đầu.

**Không xem mọi “GC root” hiển thị là do ứng dụng đã tạo leak.** Đường từ host tới loader của **phiên đang hoạt động** là bình thường. Vấn đề là loader generation **đã retired** vẫn được giữ sau khi hoàn thành lifecycle và hết grace period.

## 11. WeakReference dùng để quan sát, không dùng làm phép chứng minh tuyệt đối

Một cách giám sát việc liệu JVM *có thể* thu gom loader sau khi bỏ strong reference là giữ một weak reference:

```java
// Đoạn minh họa, không phải chương trình độc lập:
WeakReference<ClassLoader> monitor = new WeakReference<>(pluginLoader);
// Xóa tất cả strong reference do host/plugin còn giữ.
// Sau một hoặc nhiều lượt GC ở thời điểm phù hợp:
boolean wasCollected = (monitor.get() == null);
```

Cần `import java.lang.ref.WeakReference;` trong chương trình dùng đoạn code này. **Không** đặt `pluginLoader` ở static field khác hay ở biến local sống quá lâu rồi chờ weak reference tự về null. Trong chính scope dùng biến `pluginLoader`, JIT có thể xem biến còn live theo tình huống; không nên suy ra hành vi GC từ một lần thử.

Lưu ý khi viết test:

- `monitor.get() != null` ngay sau cleanup **không chứng minh leak**: có thể chưa có GC hoặc loader chưa đủ điều kiện unload tại thời điểm đó.
- `System.gc()` là một yêu cầu gợi ý với JVM, **không bảo đảm** chạy GC, dọn mọi reference hoặc class unload ngay. Không đặt test chính xác tuyệt đối dựa trên một lần gọi.
- Nên test **nguồn giữ cụ thể** bằng kiểm tra registry, TCCL và ThreadLocal trên đúng worker; sau đó dùng heap dump để tìm retained paths ở generation đã retired.
- Nếu cần quan sát theo thời gian, `ReferenceQueue` có thể nhận thông báo khi weak referent được clear/enqueue theo semantics phù hợp; vẫn không thay thế việc xác minh tất cả owner đã teardown.
- Một test đo số class loader cũ sau 100 vòng redeploy có ích hơn test `sleep(100); assertNull(weak.get())`, nhưng cũng phải kiểm soát GC/warmup/workload và tránh kỳ vọng collection theo một deadline cứng.

**Điểm phân biệt:** sử dụng weak reference làm *probe* không loại bỏ strong references ở cache/thread/callback. Nếu đồ thị còn một đường giữ mạnh, weak reference không buộc JVM bỏ qua đường đó.

## 12. Mẫu teardown exception-safe trong môi trường production

Sau khi tìm được các nguồn giữ, runtime cần một trình tự teardown được **thực hiện kể cả khi một bước lỗi**. Không nên để lỗi callback A khiến host bỏ qua việc dọn timer, ThreadLocal hoặc cache của A.

Một trình tự đề xuất:

1. Đánh dấu plugin generation A là **DRAINING**; chặn request/registration mới đến A, chuyển request mới sang B.
2. Cancel/dispose các subscription và scheduled tasks của A; ngăn callback mới được xếp hàng.
3. Đợi callback/task in-flight kết thúc hoặc chấm dứt theo timeout và chính sách quarantine; không vội đóng JAR loader khi vẫn còn code cần lazy-load class/resource.
4. Ở những worker đã chạy code A, bảo đảm `ThreadLocal.remove()` và restore baseline TCCL. Với host executor dùng chung, cleanup phải chạy ở đúng mỗi worker có state; submit một task duy nhất **không bảo đảm** nó sẽ đi đến tất cả worker nếu pool có nhiều threads.
5. Xóa đúng cache/registry entries, listener handles, DI scopes, reflection metadata và những references mà **host** giữ đối với A.
6. Dừng và join những threads **do A tạo và sở hữu**. Với thread bất hợp tác, phải có chính sách cô lập; không giả định `shutdownNow()` sẽ kill chắc chắn.
7. Đóng file watcher/streams/timer/URLClassLoader của A, sau đó xóa strong references do plugin manager/monitoring giữ.
8. Đo lại các đường từ GC roots, theo dõi class unloading và memory qua nhiều vòng thay thế.

Với một task cụ thể, đây là mẫu restoration bất chấp exception (đoạn minh họa, các biến phụ thuộc context):

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    PLUGIN_CONTEXT.set(pluginRequest);
    pluginCallback.run();
} finally {
    try {
        PLUGIN_CONTEXT.remove();
    } finally {
        Thread.currentThread().setContextClassLoader(previous);
    }
}
```

Khối `finally` lồng nhau giúp cố gắng restore TCCL dù cleanup ThreadLocal gặp ngoại lệ bất thường. Mã trên chỉ giải phóng thread-local value và TCCL **trên thread gọi**; nó **không** tự unregister `pluginCallback` khỏi registry. Registry registration phải có lifecycle riêng, thường dùng `AutoCloseable` hoặc hàm unsubscribe.

Với toàn bộ plugin, teardown manager nên gom kết quả các bước cleanup, báo lỗi từng nguồn và vẫn cố dọn các bước độc lập còn lại. Đừng catch lỗi rồi tuyên bố unload thành công nếu thực tế còn callback/thread sống.

## 13. Đừng bỏ quên các nguồn giữ gián tiếp

Bốn loại nguồn giữ chính thường có các biến thể:

### Reflection, proxy và metadata

- Cache chứa `Class<?>`, `Method`, `MethodHandle`, dynamic proxy class, annotation proxy hoặc record component của plugin.
- Class key của metadata map do parent loader định nghĩa.
- Lambda implementation, method reference hoặc `invokedynamic` call site có closure/call target liên quan tới plugin instance.
- Logging/serializer/DI libraries giữ metadata hoặc factory toàn process.

**Điều tra:** lọc các class do loader A định nghĩa và xem reverse references. Nếu root là thư viện, sử dụng API clear/close/unregister của thư viện, tránh xóa nội bộ bằng reflection không được hỗ trợ.

### ServiceLoader và đăng ký dịch vụ

`ServiceLoader` có thể cache provider instance/type. Nếu host giữ `ServiceLoader` hoặc provider lâu hơn vòng đời plugin A, nó có thể tiếp tục giữ provider class/instance và loader. Gọi `ServiceLoader.reload()` có thể clear cache nội bộ để khám phá lại provider, nhưng không gỡ reference ở những registry/biến khác; không phải một API “unload toàn bộ plugin”. Khi thay plugin, hãy quản lý provider lifecycle và ownership rõ ràng.

### Driver, shutdown hooks, JMX, native code

Một số thư viện/plugin đăng ký JDBC driver, shutdown hook, MBean, JNI/global native references hoặc event callback vào registries tồn tại suốt tiến trình. Những đăng ký đó có thể giữ instance hoặc class của loader A; cách teardown phụ thuộc API tương ứng. Không tự xóa toàn bộ entries của hệ thống nếu còn driver/plugin khác đang sử dụng.

### Thread stack và hoạt động chưa kết thúc

Thread dump có thể cho thấy worker vẫn trong code của A; đó là bằng chứng có task đang chạy/chờ, khác với một ThreadLocal value tồn lưu sau khi task đã kết thúc. Dừng task hợp lệ trước; nếu có class file/resource lazy-load khi đang chạy, đóng loader sớm có thể tạo lỗi giả.

### Caches mà plugin sở hữu

Một static field nằm trong class **chỉ do plugin loader A định nghĩa** không nhất thiết tự tạo đường từ một GC root độc lập tới A nếu toàn bộ graph A đã cô lập và unreachable. Cần tìm **đường nối từ host/JVM root** tới graph đó. Ngược lại static field của host chứa plugin object là đường giữ trực tiếp. Phân biệt hai tình huống này khi đọc heap analyzer để không “sửa leak” chỉ bằng cách xóa static field của class đã không reachable.

## 14. Phân tích retained path theo từng loại root

Khi heap analyzer trả một đường dẫn, đối chiếu với bảng:

| Root/đường nhìn thấy | Suy luận có căn cứ | Chỗ cần sửa |
|---|---|---|
| `HostRegistry.staticCache → Map.Node.value → PluginHandler` | Registry host giữ instance | API invalidate theo plugin generation |
| `HostCache.classCache → Class<PluginType>` | Host giữ metadata class | Cache eviction/clear scope |
| `Thread → contextClassLoader → PluginLoader` | Worker còn TCCL plugin | Restore baseline trên đúng thread |
| `Thread → threadLocals → entry.value → PluginContext` | Pooled worker giữ context | `remove()` trên worker, thường `finally` của task |
| `Thread → target / stack / Runnable` | Code/plugin task còn sống hoặc queued | Stop/drain/cancel/join, inspect queue và futures |
| `EventBus → listeners → PluginListener` | Chưa unregister listener | Giữ subscription handle, remove cụ thể |
| `ScheduledThreadPoolExecutor → queue → plugin task` | Timer/task còn pending | Cancel scheduled task, purge khi phù hợp |
| `ServiceLoader → provider instance/type` | Provider cache còn được giữ | Dọn owner của loader/provider; không chỉ gọi reload |
| `Host static → WeakHashMap value → PluginClass/loader` | Weak key không phá được chuỗi giữ mạnh | Thiết kế lại cache/value hoặc lifecycle |
| `Class<?> / Method / MethodHandle của A` | Metadata phản chiếu giữ class của A | Gỡ reflection cache và những callable còn giữ |

**Một đường ngắn nhất không có nghĩa là đường duy nhất.** Nếu xóa `HostRegistry.staticCache` mà loader vẫn sống, hãy chạy lại path-to-roots và kiểm tra thread/callback/metadata; thao tác dọn toàn bộ graph có thể phải thực hiện bởi nhiều component owners.

## 15. Logging, instrumentation và chỉ số nên có

Ngay từ lúc load plugin, host nên gắn một identity riêng cho **mỗi generation**, không chỉ tên file JAR:

```text
plugin-id=reporting
generation=9f7a-...           (ID của bản triển khai)
loader-type=PluginClassLoader
loader-identity=<identity hash + ID generation>
artifact=plugins/reporting-v41.jar
state=ACTIVE | DRAINING | RETIRED
```

Phần trên là **ví dụ định dạng log**, không phải API Java. `System.identityHashCode(loader)` có ích để nhận diện trong một thời điểm, nhưng không phải ID bền vững toàn tiến trình hay UUID bảo đảm duy nhất; gắn thêm generation ID do host sinh ra.

Những chỉ số hữu ích:

- Số generation đang ACTIVE/DRAINING/RETIRED và thời gian từ lúc retire.
- Số callbacks/listeners/timers/subscriptions còn đăng ký theo generation.
- Số cache entries/chứa reference tới generation A, số futures/tác vụ chưa hoàn tất.
- Tên và số worker có TCCL trỏ tới loader A; số worker/context có ThreadLocal value thuộc A (đo qua instrumentation do host kiểm soát, không dò bừa field private của JDK).
- Metaspace usage, số class loader/class đã được nạp, class unloading events qua GC/JFR/Unified Logging khi được bật.
- Heap dump retained-size/traces khi xảy ra leak, gắn kèm thời điểm, workload, generation ID.

Cảnh báo khi tính “loader count”: không phải mọi class loader trong JVM là plugin loader; runtime, app server, frameworks hoặc tool agents có thể tạo loaders hợp lệ. Hãy lọc đúng plugin class/identity và theo dõi xu hướng qua **nhiều** lần replace giống nhau.

## 16. Kiểm thử hồi quy có giá trị

Một bộ test nên tách **deterministic ownership assertions** khỏi **GC observations**:

| Tình huống | Assert có thể dự đoán | Phần chỉ quan sát |
|---|---|---|
| Cache giữ plugin A | Cache chứa instance/class của A trước cleanup | Loader A vẫn có thể chưa GC |
| Cache eviction | Entry A biến mất khỏi map đúng owner | Không ép metaspace giảm ngay |
| Pooled ThreadLocal | Task trên đúng worker đọc ra value A trước, null sau `remove` | Không assert weak ref cleared tức thì |
| TCCL | Worker TCCL bằng A trước, baseline sau | GC vẫn phụ thuộc các references khác |
| Listener registration | Registry có A trước, không có A sau unsubscribe | Callback in-flight có thể còn đang chạy |
| Plugin-owned thread | Thread A dừng/join trong deadline hợp lý | Class unload không có deadline chắc chắn |
| Plugin A → B → C | A/B đã RETIRED không còn registration/caches | Xu hướng loader count và metaspace qua nhiều GC |
| Fault injection | Callback hoặc cleanup ném lỗi nhưng các bước độc lập vẫn chạy | Heap analysis dùng để tìm path sót |
| Parallel reload | New requests vào B; không task mới vào A; old tasks drained | Race phụ thuộc workload |
| Weak reference probe | Không yêu cầu null trong thời điểm cố định | Quan sát sau các chu kỳ GC phù hợp |

Đặc biệt nên có test “plugin A cố tình tạo đủ bốn roots → teardown A → từng root được tháo → plugin B vẫn hoạt động”. Sau đó kiểm tra **retaining path** trong staging nếu số loader cũ tăng tuyến tính qua nhiều vòng. Test này trực tiếp bắt đúng bug thay thế plugin hơn là một assertion mơ hồ dựa trên thời gian chờ GC.

## 17. Những sai lầm thường gặp

1. **“Đã `URLClassLoader.close()`, vậy class chắc chắn unload.”** Sai: close chỉ quản lý tài nguyên loader; còn GC roots quyết định reachability.
2. **“Xóa plugin khỏi map tổng là đủ.”** Chưa chắc: callback registry, threadlocal, queue và TCCL là các đường giữ độc lập.
3. **“Gọi `ThreadLocal.remove()` trên main sẽ dọn pool.”** Sai: remove chỉ ảnh hưởng thread đang gọi.
4. **“ThreadLocal key đã thành weak thì value tự biến mất ngay.”** Không bảo đảm; stale entries trong implementation có thể giữ value lâu.
5. **“Thread daemon không giữ loader.”** Thread daemon vẫn có context loader, stack, target và ThreadLocal; cờ daemon không tự loại references.
6. **“Dừng scheduling là xong.”** Một callback/task đang chạy hoặc queued vẫn có thể giữ plugin.
7. **“Vừa gọi unsubscribe là không ai đang gọi listener nữa.”** Cần xử lý in-flight callbacks và tính nhất quán của event bus.
8. **“Để cache là WeakHashMap thì chắc chắn hết leak.”** Value có thể tham chiếu mạnh đến key hoặc plugin class.
9. **“Thử `System.gc()` một lần rồi đếm loader là đủ.”** Timing GC không được bảo đảm, và snapshot không chỉ ra owner của retaining path.
10. **“Cache bên trong class của plugin chắc chắn là nguyên nhân.”** Cần xem có đường từ GC root vào graph plugin hay không.
11. **“Cho host ghi đè loader A bằng biến trỏ loader B là đủ.”** Còn thread/registrations/cache khác giữ A.
12. **“Close loader ngay khi bắt đầu drain.”** Task cũ có thể cần lazy-load dependency; nên chờ đúng lifecycle.
13. **“Xóa mọi callback của event bus để chắc chắn sạch.”** Nguy hiểm với plugin khác; phải remove theo registration/generation.
14. **“Log tên class thôi là nhận diện được loader.”** Hai generation có thể có class trùng binary name nhưng defining loader khác.
15. **“WeakReference.get()!=null chứng minh memory leak.”** Chưa chắc đã có GC; phải xem retaining path và lifecycle.
16. **“Chỉ quan sát Metaspace là đủ.”** Heap callback/threadlocal values, file handles và native resources cũng cần được theo dõi.

## 18. Quy trình ngắn gọn để xử lý một sự cố thực tế

Khi phát hiện sau nhiều lần nâng cấp plugin mà memory không ổn định:

1. **Khoanh vùng** đúng plugin generation đã RETIRED và thu thập identity của class loader cũ.
2. **Kiểm tra owner rõ ràng:** host cache, listener registry, scheduler/futures, `ThreadLocal`/TCCL của worker và plugin-owned threads. Assert theo generation.
3. **Tạo snapshot có kiểm soát:** `jcmd VM.classloader_stats`, GC/class-unload logs và heap dump khi cần.
4. **Đọc Path to GC Roots:** tìm reference mạnh từ root tới loader hoặc plugin class/instance; ghi lại root owner và vị trí đăng ký.
5. **Sửa tại lifecycle owner:** evict đúng cache, unsubscribe đúng callback, `remove()` trên đúng worker, restore TCCL, dừng/join thread/task.
6. **Lặp lại kiểm chứng:** các root cụ thể đều biến mất; không request nào vào generation cũ; theo dõi đường giữ và xu hướng classloader/metaspace qua các vòng A→B→C.
7. **Đưa teardown vào hợp đồng plugin:** registration handles, managed worker scopes, generation-scoped caches và cleanup exception-safe để sự cố không lặp lại.

**Ghi nhớ:** class loader cũ không được giải phóng chỉ vì tên biến `pluginLoader` được gán sang phiên bản mới hoặc vì `URLClassLoader.close()` đã chạy. Phải cắt **mọi đường strong reference còn reachable từ GC roots** — nhất là cache của host, ThreadLocal trên worker sống lâu, TCCL/threads và callback registrations — rồi để JVM quyết định thời điểm class unloading. Chẩn đoán bằng **retaining paths**, sửa theo **ownership/lifecycle** và kiểm chứng bằng cả assert deterministic lẫn quan sát GC có kiểm soát.

**Tài liệu chuẩn Java 17:** [ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html), [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html), [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [Java 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/) và [Java Command / Unified Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
