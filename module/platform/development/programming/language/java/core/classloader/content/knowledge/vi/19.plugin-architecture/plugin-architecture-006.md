# Quy trình dừng plugin, hủy đăng ký và giải phóng tài nguyên trong kiến trúc ClassLoader

## 1. Vì sao plugin “đã tắt” vẫn còn chiếm bộ nhớ?

Một ứng dụng Java có thể cài plugin bằng `URLClassLoader` riêng, tìm implementation qua một API/SPI chung, gọi `start()` để đăng ký sự kiện, khởi tạo executor và mở file hoặc kết nối. Khi không cần plugin, ứng dụng gọi `URLClassLoader.close()` rồi tưởng tất cả class, thread và resource của plugin đã biến mất.

Thực tế, **đóng ClassLoader không đồng nghĩa dừng mã plugin hoặc unload class ngay lập tức**. Plugin vẫn có thể được giữ sống bởi:

- Callback/listener đã đăng ký trong event bus của host.
- Scheduled task, executor, thread, timer, task queue, `Future` hoặc các đối tượng runnable.
- Thread Context ClassLoader (TCCL) do thread sống lâu giữ.
- `ThreadLocal` trên thread pool, đặc biệt khi value được định nghĩa trong loader plugin.
- Static registry hoặc singleton của host giữ instance, `Class<?>`, `Method`, `MethodHandle`, lambda, proxy hoặc ClassLoader của plugin.
- MBean, shutdown hook, logging handler, JDBC driver, service provider hoặc một registry bên thứ ba không được hủy đăng ký.
- Tài nguyên chưa đóng: socket, file stream, watcher, JAR handle, connection pool, native handle.
- Request đang chạy hoặc callback chưa hoàn thành và vẫn tham chiếu code/plugin instance.

Do đó **plugin shutdown là một giao thức phối hợp vòng đời**, không phải một lệnh duy nhất. Phải dừng nguồn sinh công việc, tháo các tham chiếu từ host, chờ công việc đang chạy theo chính sách, đóng những resource do plugin sở hữu, sau đó mới đóng ClassLoader và bỏ các tham chiếu còn lại.

## 2. Phân biệt stop, close, unload và GC

| Khái niệm | Nội dung thực tế | Không bảo đảm điều gì? |
| --- | --- | --- |
| **Quiesce / stop accepting** | Không cho request/event/job mới đi vào plugin | Không tự hủy mọi task đang chạy |
| **Unregister** | Tháo callback, command handler, route, provider hoặc listener khỏi registry bên ngoài | Không tự đóng executor và socket đã mở |
| **Stop** | Yêu cầu plugin ngừng phục vụ, có thể chờ/cancel công việc theo hợp đồng | Không nhất thiết class loader được đóng |
| **Close / dispose** | Giải phóng tài nguyên thuộc sở hữu: executor, stream, connection, timer, watcher | Không chứng minh class runtime đã bị GC |
| **`URLClassLoader.close()`** | Đóng các resource mà URLClassLoader quản lý (ví dụ JAR handle đã mở), chặn khả năng nạp class/resource mới theo hợp đồng API | Không tự chấm dứt thread/callback, không gỡ class đã định nghĩa |
| **Unload class** | JVM có thể thu hồi class metadata khi các điều kiện reachability và GC cho phép | Không được bảo đảm xảy ra đúng lúc `close()` |
| **Garbage collection** | Có thể thu hồi đối tượng/loader không còn reachable | Không phải API đồng bộ “ép unload” an toàn cho ứng dụng |

**Điểm mấu chốt:** sau khi `close()` trên `URLClassLoader`, một class đã được định nghĩa vẫn có thể tồn tại, các instance và method của nó vẫn có thể được thực thi. Close tác động vào những nguồn/tài nguyên loader quản lý, không phải “kill switch” của code.

Nếu cần bảo đảm dừng **mã không tin cậy hoặc không hợp tác**, ClassLoader riêng không phải ranh giới cách ly đủ mạnh. Thực thi plugin trong process/container riêng với hợp đồng IPC và quyền phù hợp thường dễ cưỡng chế dừng hơn.

## 3. Vòng đời plugin nên được mô hình hóa bằng trạng thái rõ ràng

Một thiết kế thực tế có thể sử dụng:

```text
       install / load
NEW --------------------> LOADED
                           |
                         start()
                           v
                         ACTIVE
                           |
                    stop requested
                           v
                       QUIESCING
                           |
                no new work; drain/cancel
                           v
                       STOPPING
                           |
              unregister; close resources
                           v
                        STOPPED
                           |
                close loader; drop refs
                           v
                        DISPOSED
```

Có thể có trạng thái lỗi như `FAILED_START`, `FAILED_STOP` hoặc `LEAK_SUSPECTED`. Điều quan trọng là **không làm trạng thái trông như đã dừng hoàn toàn khi vẫn còn thread/callback hoạt động**.

Các điều kiện cần xác định:

1. **Idempotency:** gọi `stop()` hoặc `close()` nhiều lần phải không gây double-close hỏng hoặc đăng ký âm; trường hợp có exception vẫn cố cleanup phần có thể cleanup.
2. **Concurrency:** không cho đồng thời start và stop làm state không nhất quán; cần lock, atomic state hoặc state machine có kiểm thử.
3. **Ownership:** thành phần nào tạo resource thì có trách nhiệm đóng, hoặc hợp đồng chuyển ownership phải rõ ràng.
4. **Deadline:** shutdown không nên chờ vô hạn; có thời hạn cho drain/await, chính sách cancel/fallback và cách báo lỗi rõ ràng.
5. **Failure isolation:** lỗi cleanup của một plugin không được chặn cleanup những plugin/resource còn lại.
6. **No resurrection:** callback đến muộn không được tự khởi động lại plugin đang đóng.

Không có thứ tự “chuẩn duy nhất” áp dụng cho mọi framework; thứ tự phải dựa trên luồng phụ thuộc của plugin. Tuy nhiên, một quy trình stop hữu ích sẽ ưu tiên **chặn work mới trước khi đóng những resource mà work đang dùng**.

## 4. Trình tự dừng gợi ý cho một plugin đang chạy

### Bước 1 — Công bố yêu cầu dừng

Đặt trạng thái plugin thành `QUIESCING` hoặc `STOPPING` bằng thao tác đồng bộ phù hợp. API chuyển trạng thái phải được chỉ định là **một chiều** cho lượt dừng này.

Từ thời điểm ấy:

- Dispatcher không gửi request mới cho plugin.
- Scheduler/command router không cấp thêm job mới.
- Health/readiness không còn coi plugin là một instance phục vụ request bình thường.
- Việc load hoặc tạo instance mới của plugin cùng phiên bản được từ chối theo policy.

Nếu host tự tiếp tục phát lệnh sau khi plugin `close()`, việc plugin “dừng sạch” là bất khả thi.

### Bước 2 — Hủy đăng ký tại các hệ thống bên ngoài plugin

Tháo subscription/listener, route HTTP, command handler, job scheduler entry, ServiceRegistry entry và mọi registration mà host đã cấp. Một pattern tốt là API `register(...)` trả về một **handle `AutoCloseable`/`Registration`** để hủy đăng ký bằng đúng handle đó.

```java
Registration subscription = eventBus.subscribe(listener);
try {
    // Sử dụng subscription khi plugin đang ACTIVE.
} finally {
    subscription.close();  // hủy đăng ký ở host
}
```

Đây là đoạn minh họa (giả định `Registration` và `eventBus` đã được định nghĩa). Không nên chỉ gọi `listeners.clear()` **trong plugin** nếu host vẫn giữ reference tới listener gốc.

### Bước 3 — Dừng tác vụ đang chạy

- Executor: `shutdown()` để ngừng nhận task mới; chờ `awaitTermination(timeout, unit)`.
- Nếu quá deadline: cân nhắc `shutdownNow()` (gửi interrupt tới task đang chạy theo hợp đồng), rồi chờ lại.
- Task phải hợp tác với interrupt/cancellation; `shutdownNow()` **không thể cưỡng chế** một thread đang chặn trong code không hợp tác.
- Thread tự tạo phải có cờ dừng, interrupt hoặc cơ chế signal thích hợp và được `join` có deadline.
- Scheduled executor: cancel periodic jobs và kiểm tra policy đối với delayed tasks.

Không dùng `Thread.stop()` để cưỡng chế dừng; API này không an toàn. Không khóa registry dài qua `awaitTermination` nếu task cần registry để hoàn thành, vì có thể gây deadlock.

### Bước 4 — Đóng resource theo hướng ngược với lúc khởi tạo

Ví dụ khởi tạo: mở socket → tạo worker → đăng ký listener; shutdown thường làm ngược: unregister listener → stop worker → close socket. Nếu task đang cần socket, hãy drain task **trước** khi socket bị đóng; nếu chính việc đóng socket là tín hiệu phá blocking I/O, quy trình cần mô tả rõ.

Áp dụng `try-with-resources` hoặc `finally` để cleanup từng phần và giữ `suppressed exceptions` khi có nhiều lỗi. Resource có thể gồm:

- `InputStream`, `OutputStream`, `WatchService`, `JarFile`.
- `Socket` / HTTP client/connection pool.
- JDBC connections, listeners/drivers đã đăng ký, timer/scheduler.
- Logging/appender, metrics instrument callbacks, exporter.
- Native library handle hoặc plugin-specific unmanaged state.

### Bước 5 — Dọn context và registry sống lâu

Hủy `ThreadLocal` thuộc plugin trên đúng thread khi kết thúc xử lý; khôi phục TCCL khi tạm thay:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Thực thi API cần context loader của plugin.
} finally {
    thread.setContextClassLoader(previous);
}
```

Snippet cần biến `pluginLoader`. TCCL là một tham chiếu mạnh; thread pool sống sau plugin có thể giữ loader qua TCCL nếu không khôi phục. `ThreadLocal.remove()` chỉ tác động đến **thread đang gọi**; host không thể tùy tiện xóa mọi ThreadLocal của thread khác từ xa một cách an toàn.

### Bước 6 — Đóng ClassLoader và bỏ tham chiếu

Khi các hoạt động đã kết thúc:

- Gọi `URLClassLoader.close()` bằng try-with-resources hoặc trong bước dispose của manager.
- Gỡ entry plugin khỏi registry/route/cache của host.
- Bỏ reference tới instance, class, reflection metadata, threads, module layer và các đối tượng plugin liên quan khi không cần nữa.
- Chuyển trạng thái sang `DISPOSED` theo các điều kiện cleanup thực sự được bảo đảm.

Sau bước này, loader/class **có thể** trở nên unreachable và được GC/unload khi JVM quyết định. Không được báo “class đã unload” chỉ vì `close()` trả về bình thường.

## 5. Ví dụ Java 17 tự chạy: ngừng nhận callback, shutdown executor, đóng URLClassLoader

Ta tách code thành **API dùng chung do host định nghĩa**, **implementation do plugin loader định nghĩa** và **host chịu trách nhiệm điều phối**. Ví dụ có một event bus đơn giản dùng một thread để giữ stdout xác định. Plugin đăng ký callback giữ reference tới `this`, tạo một worker executor và có API dừng đóng idempotent.

### 5.1. Cấu trúc thư mục

```text
src/
├── example/spi/
│   ├── HostServices.java
│   └── Plugin.java
├── example/impl/
│   └── EchoPlugin.java
└── PluginShutdownDemo.java

out/
├── host/         (host + shared SPI)
└── plugin/       (plugin implementation)
```

**Quan trọng:** lúc chạy, `out/plugin` **không** nằm trong application classpath. Implementation phải được nạp qua `URLClassLoader` riêng, còn các interface `example.spi.*` được cung cấp bởi parent application loader.

### 5.2. File `src/example/spi/HostServices.java`

```java
package example.spi;

public interface HostServices {
    Registration subscribe(Runnable listener);

    interface Registration extends AutoCloseable {
        @Override
        void close();
    }
}
```

Đây là hợp đồng callback: lời gọi `subscribe` trả một `Registration` mà plugin phải đóng khi dừng. Host sở hữu registry, nên hủy đăng ký qua handle do host cấp giúp giảm rủi ro host còn giữ lambda của plugin.

### 5.3. File `src/example/spi/Plugin.java`

```java
package example.spi;

public interface Plugin extends AutoCloseable {
    void start(HostServices services) throws Exception;
    void stop();

    @Override
    void close() throws Exception;
}
```

Phân biệt trách nhiệm:

- `start`: tạo resource và đăng ký công việc khi bắt đầu.
- `stop`: chuyển sang không phục vụ, hủy callback/entry từ host.
- `close`: gọi `stop` nếu cần và đóng tài nguyên riêng của plugin.

Trong hệ thực tế, manager có thể có thêm `quiesce()`, `awaitIdle()` hoặc `dispose()` riêng. Ví dụ cố ý giữ API nhỏ để dễ quan sát.

### 5.4. File `src/example/impl/EchoPlugin.java`

```java
package example.impl;

import example.spi.HostServices;
import example.spi.Plugin;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class EchoPlugin implements Plugin {
    private HostServices.Registration registration;
    private ExecutorService worker;
    private boolean running;

    private void handleEvent() {
        if (running) {
            System.out.println("event=handled");
        }
    }

    @Override
    public void start(HostServices services) throws Exception {
        if (worker != null) {
            throw new IllegalStateException("Already started");
        }

        worker = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "echo-plugin-worker");
            // Worker không giữ TCCL plugin sau khi khởi tạo.
            thread.setContextClassLoader(
                    ClassLoader.getSystemClassLoader());
            return thread;
        });

        try {
            // Buộc worker đã tạo, rồi chờ task ngắn hoàn thành.
            worker.submit(() -> {}).get();
            registration = services.subscribe(this::handleEvent);
            running = true;
            System.out.println("plugin=started");
        } catch (Exception failure) {
            if (registration != null) {
                registration.close();
                registration = null;
            }
            worker.shutdownNow();
            worker = null;
            throw failure;
        }
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        running = false;

        if (registration != null) {
            registration.close();
            registration = null;
        }
        System.out.println("plugin=stopped");
    }

    @Override
    public void close() throws InterruptedException {
        stop();
        if (worker == null) {
            return;
        }

        worker.shutdown();
        if (!worker.awaitTermination(2, TimeUnit.SECONDS)) {
            worker.shutdownNow();
            if (!worker.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not terminate");
            }
        }
        worker = null;
        System.out.println("plugin=resources-closed");
    }
}
```

**Điều đã được làm rõ:**

- Callback `this::handleEvent` có reference tới instance plugin. Nếu host không tháo callback, registry có thể giữ instance và cả loader liên quan.
- `stop()` không chỉ đặt `running=false` mà còn gọi `registration.close()`.
- `close()` dừng intake nếu cần, rồi shutdown executor và chờ bounded timeout.
- Worker thread được gán TCCL của system loader theo chính sách demo, tránh giữ plugin loader lâu dài chỉ qua TCCL.
- `close()` gọi lặp sau khi đã đóng worker sẽ return; `stop()` gọi lặp không in log/deregister thêm lần nữa.

**Giới hạn:** `running` ở đây chỉ được thay và đọc theo một luồng điều phối của demo; trong môi trường callback đa luồng, cần `volatile`/atomic state hoặc synchronization phù hợp để không có data race. Cơ chế `shutdownNow()` vẫn phụ thuộc task hợp tác với interrupt.

### 5.5. File `src/PluginShutdownDemo.java`

```java
import example.spi.HostServices;
import example.spi.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class PluginShutdownDemo {

    static final class EventBus implements HostServices {
        private final List<Runnable> listeners = new ArrayList<>();

        @Override
        public Registration subscribe(Runnable listener) {
            listeners.add(listener);
            return new Registration() {
                private boolean closed;

                @Override
                public void close() {
                    if (!closed) {
                        closed = true;
                        listeners.remove(listener);
                    }
                }
            };
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }

        int subscribers() {
            return listeners.size();
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        URL pluginUrl = Path.of("out/plugin").toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{pluginUrl},
                PluginShutdownDemo.class.getClassLoader())) {

            Class<?> implementation =
                    loader.loadClass("example.impl.EchoPlugin");

            Plugin plugin = (Plugin) implementation
                    .getDeclaredConstructor().newInstance();

            try {
                plugin.start(bus);
                bus.publish();
                System.out.println("subscribersBeforeStop="
                        + bus.subscribers());
            } finally {
                try {
                    plugin.stop();
                } finally {
                    plugin.close();
                }
            }

            System.out.println("subscribersAfterStop="
                    + bus.subscribers());
            bus.publish(); // Không còn listener plugin.
        }

        System.out.println("loader=closed");
    }
}
```

Host giữ tham chiếu tới `plugin` và `implementation` trong một scope hữu hạn; đóng loader ở cuối khối `try` không bảo đảm GC ngay. Trong bản production, registry/manager cần gỡ mọi reference lâu dài khi dispose và phân biệt plugin stop thành công với quá trình unload tiềm năng.

### 5.6. Biên dịch và chạy

Từ thư mục gốc của ví dụ, dùng shell hỗ trợ `mkdir -p` (Linux/macOS/Git Bash):

```bash
mkdir -p out/host out/plugin
javac --release 17 -d out/host src/example/spi/HostServices.java src/example/spi/Plugin.java src/PluginShutdownDemo.java
javac --release 17 -cp out/host -d out/plugin src/example/impl/EchoPlugin.java
java -cp out/host PluginShutdownDemo
```

Trên Windows PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force out/host,out/plugin`, rồi chạy các lệnh `javac` và `java` còn lại. Classpath ở đây chỉ có **một root** nên không cần separator `:` hoặc `;`.

**Stdout mong đợi trên JDK 17+ khi thực thi thành công:**

```text
plugin=started
event=handled
subscribersBeforeStop=1
plugin=stopped
plugin=resources-closed
subscribersAfterStop=0
loader=closed
```

### 5.7. Vì sao kết quả có ý nghĩa?

1. `plugin=started`: implementation được loader riêng nạp và khởi tạo, worker đã chạy task ngắn, callback đã đăng ký.
2. `event=handled`: host phát sự kiện khi plugin đang hoạt động.
3. `subscribersBeforeStop=1`: registry bên ngoài plugin còn giữ đúng một callback.
4. `plugin=stopped`: plugin chuyển state và đóng registration handle.
5. `plugin=resources-closed`: executor đã ngừng và plugin xóa reference của mình tới worker.
6. `subscribersAfterStop=0`: host không giữ callback nữa; đây là **một điều kiện cần** để loại bỏ nguồn rò rỉ tham chiếu.
7. `loader=closed`: loader được đóng nhờ try-with-resources, **không khẳng định** tất cả class đã unload.

Bài thực hành cố ý **không dùng** `System.gc()` để minh họa “unload đã hoàn tất”, vì việc GC/unloading không có thời điểm xác định theo yêu cầu của ứng dụng.

## 6. Cleanup cả khi start thất bại

Startup có thể fail ở nhiều điểm:

```text
load class -> instantiate -> create executor -> open socket
           -> register listener -> schedule job -> ACTIVE
```

Nếu exception xảy ra giữa chuỗi, những resource đã tạo **vẫn phải được thu hồi**, kể cả plugin chưa đạt trạng thái ACTIVE. Vì vậy mọi bước cấp phát/đăng ký nên có rollback tương ứng, hoặc được quản lý trong một stack các cleanup actions.

Pattern minh họa:

```java
Deque<AutoCloseable> cleanup = new ArrayDeque<>();
try {
    AutoCloseable resource = openResource();
    cleanup.push(resource);

    AutoCloseable subscription = registerCallback();
    cleanup.push(subscription);

    markActive();
} catch (Exception failure) {
    while (!cleanup.isEmpty()) {
        try {
            cleanup.pop().close();
        } catch (Exception cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }
    }
    throw failure;
}
```

Đây là **pseudocode Java có API giả định** (`openResource`, `registerCallback`, `markActive` và imports chưa định nghĩa), không phải chương trình độc lập. Đối với implementation thật, hãy đảm bảo nếu startup thành công, ownership của stack cleanup được chuyển rõ ràng cho plugin/manager thay vì để object bị quên.

Bài demo ở phần 5 xử lý việc startup lỗi trong `EchoPlugin.start` bằng cách deregister và shutdown worker. Tuy nhiên, code sản phẩm cần quan tâm cả exception từ registration close, worker shutdown, external side effects và khả năng `start()` đã khởi tạo một phần trước khi throw.

## 7. Unregister là hủy reference ở nơi đã đăng ký

Một lỗi thiết kế phổ biến:

```text
Host singleton EventBus
    └── List<Listener>
           └── lambda -> PluginInstance
                            └── PluginClass
                                  └── PluginClassLoader
```

Ngay cả khi ứng dụng xóa entry `PluginManager.plugins.remove(pluginId)`, event bus vẫn giữ listener => plugin vẫn reachable. Chỉ đặt `plugin = null` ở local variable không đủ.

**Nguyên tắc:**

- Mọi `subscribe/register/addListener` cần một thao tác đối xứng `unsubscribe/unregister/removeListener`.
- Nên trả về **registration token/handle** thay vì buộc plugin đoán object nào cần remove.
- Nếu framework dùng annotation để auto-scan/register, phải có API unregister cho scope plugin khi stop.
- Nếu registry phân theo pluginId, manager có thể thực hiện `unregisterAll(pluginId)` để thu hồi khi plugin lỗi.
- Nếu callback đang chạy trong lúc unregister, cần định nghĩa rõ **drain semantics**: unsubscribe chặn callback mới hay đợi callback đang chạy? Hai khả năng khác nhau.
- Nếu plugin có một lambda listener, không tạo lambda mới rồi gọi remove và mong hai instance luôn tương đương; hãy giữ **chính handle hoặc listener instance** đã đăng ký.

### Những registry ngoài event bus

| Registry hoặc tích hợp | Thao tác thường cần khi dừng | Lý do |
| --- | --- | --- |
| HTTP route / servlet filter | Unregister route/filter, đợi in-flight requests | Không gọi plugin đã disposed |
| Scheduler/cron | Cancel job, wait/cancel executing tasks | Job có thể giữ reference tới code plugin |
| Event listener / message consumer | Unsubscribe/close consumer, drain queue | Tránh callback vào instance đã dừng |
| JDBC driver | Dỡ đăng ký driver do plugin tự đăng ký khi ownership đúng | DriverManager có thể giữ class/loader |
| JMX MBean | Unregister MBean đã đăng ký bởi plugin | MBean server sống lâu giữ implementation |
| Logging handler/appender | Remove handler rồi close | Thread/stream/cache giữ plugin |
| Service registry | Remove service implementation và provider metadata được cache | Host ngừng tra provider cũ |
| Metrics observer | Remove callback/instrument listener, close exporter | Tránh giữ lambda/plugin |
| Shutdown hook | Remove hook nếu được API cho phép và chưa shutdown | Hook Thread có thể giữ loader |
| GUI/desktop listener | Remove listener/observer | Host UI có vòng đời lâu hơn plugin |

Không phải mọi plugin đều dùng mọi registry. **Danh sách cleanup phải phản ánh ownership thực tế**, tránh gọi deregister lên resource do host chung quản lý và gây ảnh hưởng plugin khác.

## 8. Executor, thread và tác vụ đang chạy

Executor thường là nguyên nhân plugin không dừng:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
// Nếu không shutdown, worker có thể tiếp tục sống sau khi plugin "đóng".
```

Đây là snippet. Pattern cleanup cơ bản (có thể trích vào helper có owner rõ ràng):

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            // Báo trạng thái FAILED_STOP, đừng khẳng định cleanup hoàn tất.
        }
    }
} catch (InterruptedException interrupted) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Snippet giả định biến `executor`, import `TimeUnit` và context được phép can thiệp executor. Nếu task đang chờ network I/O hoặc khóa ứng dụng và bỏ qua interrupt, gọi `shutdownNow()` **không** bảo đảm thread đã chết.

### Dừng request và draining

Một shutdown có khả năng drain có thể:

1. Hủy route/consumer intake hoặc ngăn request mới nhận plugin.
2. Theo dõi số request đang chạy bằng counter/phaser.
3. Chờ counter về 0 tới deadline.
4. Nếu vượt deadline, hủy/cancel theo chính sách; phân biệt yêu cầu idempotent với non-idempotent.
5. Chỉ đóng connection/resource sau khi các request đã rời khỏi đoạn code cần nó.

**Không tự ý kill thread** để giữ SLA shutdown. Nếu cần cưỡng chế cứng (hard kill) đối với plugin không hợp tác, hãy cô lập plugin vào process riêng và giới hạn quyền/runtime phù hợp.

### Kiểm soát TCCL của worker

Thread tạo khi TCCL của parent đang trỏ tới plugin loader có thể **kế thừa** context loader đó. Nếu thread còn sống sau plugin, nó tiếp tục giữ strong reference tới loader. Thread factory của plugin nên đặt TCCL theo policy host hoặc khôi phục sau từng task, và phải đảm bảo không phá các API đang cần loader plugin trong suốt thời gian plugin hoạt động.

**Lưu ý:** chỉ set TCCL về system loader không giải quyết các reference khác (lambda, ThreadLocal, runnable queue). Phải dừng thread và dọn toàn bộ các kênh giữ tham chiếu.

## 9. ThreadLocal, static cache và class loader leak

`ThreadLocal<T>` dễ bị xem nhẹ. Nếu một thread pool của **host** sống suốt tiến trình còn value ThreadLocal có class do plugin loader định nghĩa, nó có thể giữ plugin loader reachable ngay cả khi manager đã bỏ plugin.

Thực hành:

- Khi plugin đặt ThreadLocal, nó nên gọi `remove()` trong `finally` của **chính thread** thực thi task.
- Đừng giữ plugin-defined object trong ThreadLocal của host worker nếu không có teardown rõ ràng.
- Với TCCL tạm thời, khôi phục TCCL trong `finally` trên từng thread.
- Nếu plugin dùng global static cache của thư viện chung, phải kiểm tra API clear/deregister theo pluginId hoặc loader scope.
- Nếu framework dùng weak keys, đừng vội kết luận đã an toàn: **value mạnh** hoặc các đường tham chiếu khác vẫn có thể giữ loader.

Snippet minh họa một task plugin (giả định `context` là `ThreadLocal<?>` thích hợp):

```java
try {
    // Gắn context vào thread khi thực hiện một request.
} finally {
    context.remove();
}
```

Đây là snippet không độc lập; không gọi `ThreadLocal.remove` từ thread khác rồi mong value trên worker được xóa.

### Có nên dùng WeakReference kiểm tra unload?

Có thể dùng `WeakReference<ClassLoader>` để quan sát **khả năng thu hồi** trong bài kiểm thử leak, nhưng:

- Phải bỏ hết strong references từ test, event bus, threads, cache và reflection artifacts.
- GC không có cam kết hoàn tất trong một khoảng thời gian cụ thể.
- `System.gc()` chỉ là gợi ý theo môi trường VM; không phải chứng nhận class đã unload.
- Một weak reference vẫn chưa bị clear **không tự chứng minh** leak nếu GC chưa thu hồi; và việc nó đã clear không chứng minh tất cả resource bên ngoài đã đóng.

Muốn chứng minh leak, nên kết hợp heap dump, class histogram, reference chains, thread dump và quan sát sau nhiều chu kỳ load–unload.

## 10. ServiceLoader, module layer và plugin reload

`ServiceLoader` có provider cache của chính instance đó: `reload()` xóa cache, **không** thay class bytes của loader cũ. Khi retire plugin, host phải bỏ provider instances/descriptors đã đăng ký và các cache giữ generation cũ. Nếu đổi binary implementation, hãy tạo loader/layer mới; **shared API/SPI** vẫn phải do loader/layer chung định nghĩa. Với JPMS, kiểm tra service declarations và references tới `ModuleLayer`, không coi việc close URLClassLoader là cơ chế unload module.

## 11. Quản lý lỗi khi shutdown: best effort nhưng không che giấu

Trong thực tế, nhiều bước có thể ném exception: unsubscribe lỗi, thread không dừng, stream close lỗi, `URLClassLoader.close` ném `IOException`.

Một shutdown manager cần tránh “fail-fast bỏ dở toàn bộ cleanup”. Cách làm phổ biến:

1. Đặt trạng thái STOPPING ngay cả khi callback đang chạy.
2. Gọi cleanup của mọi resource độc lập theo thứ tự phù hợp.
3. Gom lỗi; giữ exception chính và add các lỗi tiếp theo thành suppressed hoặc report aggregate.
4. Hết deadline thì báo `FAILED_STOP`/`PARTIAL_CLEANUP` thay vì trả thành công giả.
5. Đảm bảo các handle đã đóng được đánh dấu để không double-close.
6. Chỉ công bố `DISPOSED` khi những điều kiện mà hợp đồng yêu cầu đã đạt; nếu một worker còn sống, ghi rõ.
7. Có cơ chế buộc quản trị viên đánh giá/restart process khi trạng thái không thể hồi phục.

### Pattern hợp nhất lỗi đóng tài nguyên

```java
Exception primary = null;
for (AutoCloseable resource : ownedResources) {
    try {
        resource.close();
    } catch (Exception error) {
        if (primary == null) {
            primary = error;
        } else {
            primary.addSuppressed(error);
        }
    }
}
if (primary != null) {
    throw primary;
}
```

Đây là đoạn minh họa (giả định `ownedResources` là danh sách đã xác định thứ tự cleanup), không phải một chương trình độc lập. Trong production cần xử lý cả `Error` nghiêm trọng theo chiến lược hệ thống, không bắt rộng `Throwable` để tiếp tục như không có lỗi. Điều quan trọng là **đừng để lỗi đóng resource đầu tiên che mất các resource còn lại**.

### Đóng loader trong tình trạng plugin stop thất bại

Nếu `stop()` không đạt deadline, có thể vẫn cần đóng JAR handles và ngừng route mới. Nhưng đừng xem `URLClassLoader.close()` là phương pháp giết những thread đang chạy. Trạng thái hệ thống cần báo còn hoạt động/rò rỉ tiềm năng; trong plugin untrusted hoặc không hợp tác, restart process hoặc isolation boundary là biện pháp quản lý đáng tin hơn.

## 12. Thiết kế plugin API có khả năng shutdown tốt

Một hợp đồng lớn hơn có thể phân vai trò rõ:

```java
public interface ManagedPlugin extends AutoCloseable {
    void prepare(PluginContext context) throws Exception;
    void start() throws Exception;
    void quiesce();
    boolean awaitIdle(long timeout, TimeUnit unit)
            throws InterruptedException;
    void stop();
    @Override
    void close() throws Exception;
}
```

Đây là **interface minh họa**, cần import `TimeUnit` và định nghĩa `PluginContext` mới có thể biên dịch; không phải API chuẩn của JDK.

Có thể bổ sung:

- `PluginHandle` chứa ID/version, loader, registrations và resource ownership.
- `PluginContext.register(...)` trả cleanup token, do manager giám sát.
- Event bus của host có khả năng unregister theo pluginId và drain.
- Router áp dụng atomic switch từ phiên bản cũ sang mới.
- Manager duy trì trạng thái transition và timeout monotonic.
- Metrics: active requests, remaining listeners, alive threads, executor termination, handles open, dispose latency.
- Audit logs: pluginId, version, loader identity, shutdown reason, lỗi cleanup.

**Idempotency nên được kiểm thử**, không chỉ ghi trong tài liệu: gọi stop hai lần, close hai lần, stop sau lỗi start, stop trong lúc callback chạy, và start/stop đồng thời.

## 13. Cách phát hiện “classloader leak” sau nhiều lần reload

Không thấy exception không chứng minh shutdown sạch. Triệu chứng thường thấy:

- Số instance `URLClassLoader` hoặc loader riêng tăng theo mỗi lần reload.
- Metaspace tăng đều và không ổn định trở lại sau những chu kỳ GC đầy đủ.
- Nhiều thread còn tên plugin cũ.
- Registry chứa listener/route/service đã thuộc phiên bản cũ.
- JAR file không thể thay/xóa trên một số nền tảng vì còn handle mở.
- Thread dump xuất hiện stack của class plugin cũ.
- Heap dump chỉ ra các reference chain từ GC root tới loader cũ.

### Quy trình điều tra

1. **Đo baseline** trước khi load: số thread, subscriptions, file handles, Metaspace và loader.
2. Load plugin, chạy một số request và quan sát class/loader được định nghĩa.
3. Gọi shutdown theo trình tự đã mô tả; kiểm tra count của registry về baseline.
4. Kiểm tra executor thread còn sống, jobs còn queued, TCCL của worker sống lâu, ThreadLocal và shutdown hooks.
5. Kiểm tra `ServiceLoader` cache, MBean/JDBC/logging registrations, URLClassLoader đã close.
6. Bỏ tất cả reference có chủ đích tới plugin/loader trong manager.
7. Chạy lại load–stop–dispose nhiều vòng; tìm tăng trưởng tích lũy bất thường.
8. Dùng heap dump/histogram và GC-root path để xem loader cũ bị ai giữ. Không xem một lần `System.gc()` là phép đo quyết định.

Có thể xem thông tin JVM bằng các lệnh tham khảo:

```bash
jcmd <pid> Thread.print
jcmd <pid> GC.class_histogram
jcmd <pid> VM.classloader_stats
```

Các lệnh này phụ thuộc phiên bản JDK, quyền attach và khả năng JVM hỗ trợ. Thay `<pid>` bằng tiến trình thật; không chạy heap dump lớn ở production nếu chưa đánh giá chi phí.

Có thể bật unified logging khi JVM/JDK phù hợp:

```bash
java -Xlog:class+unload=info -cp app/classes com.example.Main
```

Đây là cú pháp tham khảo; sự kiện unload chỉ xuất hiện khi VM thực sự unload class, không gắn chặt với thời điểm `URLClassLoader.close()`. Log không thay thế việc kiểm tra tài nguyên ngoại JVM.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `URLClassLoader.close()` rồi kết luận plugin đã dừng | Callback/thread còn hoạt động, loader có thể vẫn reachable | Stop ingress, unregister, drain/close, rồi đóng loader |
| Chỉ xóa plugin khỏi một `Map` quản lý | Event bus/static cache còn giữ reference | Hủy đăng ký **tại nơi đăng ký** bằng handle |
| Dùng `System.gc()` làm thao tác shutdown | Không bảo đảm class unload; resource bên ngoài còn mở | Đóng resource rõ ràng và bỏ references |
| Stop nhận thêm request đến tận lúc đóng socket | In-flight/new requests thấy trạng thái resource hỏng | Quiesce ingress trước, drain rồi close |
| Dùng `shutdownNow()` và luôn coi là đã dừng | Task có thể không chịu interrupt | Chờ deadline, báo partial failure, cô lập plugin khi cần |
| Không dọn TCCL ở host thread pool | Thread sống lâu giữ loader cũ | Khôi phục TCCL trong `finally` |
| Dọn ThreadLocal từ sai thread | Value trên worker vẫn còn | Remove trong đúng worker/task lifecycle |
| Ghi `running=false` nhưng giữ callback trong registry | Host vẫn giữ plugin instance | Unregister; hỗ trợ in-flight callback race |
| Stop ném lỗi rồi bỏ qua cleanup còn lại | Leak resource khác | Aggregate lỗi, cleanup best effort có trách nhiệm |
| Reuse cùng loader để “reload class” | Binary name đã định nghĩa không tự thay | Tạo loader/module layer mới khi cần |
| API/SPI bị plugin định nghĩa lại | Host không cast được provider/plugin | Đặt API chung ở parent/module chia sẻ |
| Plugin đóng tài nguyên do host sở hữu | Làm hỏng plugin khác | Theo dõi ownership, token riêng cho mỗi plugin |

## 15. Bài tập tự kiểm tra

**Câu 1.** Gọi `URLClassLoader.close()` thành công. Có chắc những class do nó định nghĩa đã bị JVM unload chưa?

**Đáp án:** Không. Close giải phóng các tài nguyên loader quản lý và không phải lệnh bắt buộc JVM unload class; reachability và GC quyết định khả năng unload.

**Câu 2.** Vì sao event bus callback có thể gây ClassLoader leak?

**Đáp án:** Host event bus sống lâu giữ callback; callback/lambda có thể giữ plugin instance; plugin instance liên quan class do loader plugin định nghĩa, làm loader reachable.

**Câu 3.** Nên unregister callback trước hay sau khi đóng database connection mà callback đang sử dụng?

**Đáp án:** Thường quiesce/unregister callback mới, chờ hoặc hủy các callback đang chạy theo hợp đồng, rồi đóng connection. Cần định nghĩa rõ in-flight semantics.

**Câu 4.** `ExecutorService.shutdownNow()` có luôn giết worker thread tức thì không?

**Đáp án:** Không. Nó cố dừng các task và gửi interrupt; task có thể không hợp tác. Phải chờ bounded timeout và báo trạng thái thực.

**Câu 5.** `ThreadLocal.remove()` trên main thread có xóa giá trị của worker thread không?

**Đáp án:** Không. ThreadLocal state gắn với từng thread; cần cleanup trên đúng thread/task.

**Câu 6.** Tại sao đặt TCCL về loader host trước khi plugin thread kết thúc có ích?

**Đáp án:** Có thể loại bỏ một strong reference từ thread sống lâu tới loader plugin. Nhưng nó không thay thế việc dừng thread hoặc dọn những reference khác.

**Câu 7.** Plugin mới có class cùng tên và JAR đã đổi. Có thể dùng loader cũ và gọi `loadClass` lần nữa để lấy bytes mới không?

**Đáp án:** Không theo cơ chế nạp lớp thông thường. Cùng defining loader không tự định nghĩa lại class cùng binary name; thường cần loader mới và lifecycle handoff.

**Câu 8.** Một plugin stop lỗi nhưng các resource khác vẫn có thể đóng. Manager nên làm gì?

**Đáp án:** Tiếp tục cleanup phù hợp, gom/ghi nhận các lỗi, không báo dispose hoàn tất giả, và đánh dấu partial failure hoặc yêu cầu vận hành can thiệp.

**Câu 9.** `subscribersAfterStop=0` trong ví dụ chứng minh gì và không chứng minh gì?

**Đáp án:** Chứng minh event bus của demo không còn giữ callback ấy sau stop; không chứng minh mọi reference trong JVM đều đã mất hoặc class đã unload.

**Câu 10.** Vì sao ClassLoader riêng không đủ để kill một plugin tùy ý khi nó chạy vòng lặp vô hạn?

**Đáp án:** Loader chỉ quản lý việc định nghĩa/tìm class và một số resource nạp; nó không cung cấp cơ chế cưỡng chế dừng thread/code không hợp tác. Cần isolation/process boundary cho hard stop.

## 16. Checklist triển khai và vận hành

- [ ] Mỗi plugin có state rõ: ACTIVE → QUIESCING → STOPPING → STOPPED → DISPOSED.
- [ ] Đóng ingress trước khi resource plugin bị giải phóng.
- [ ] Mọi registration có unsubscribe handle; registry host hết tham chiếu sau stop.
- [ ] Có xử lý request/callback đang chạy và timeout/drain policy.
- [ ] Shutdown executor/worker và chờ bounded timeout; phản ánh đúng partial failure.
- [ ] Dọn ThreadLocal/TCCL trên đúng thread; không bỏ worker lâu dài giữ plugin loader.
- [ ] Đóng file/socket/connection/watchers/logging/MBeans/JDBC registrations thuộc plugin.
- [ ] Quản lý exceptions trong cleanup, giữ causes/suppressed errors.
- [ ] Plugin stop/close idempotent trong các đường lỗi và gọi lặp.
- [ ] Close URLClassLoader sau cleanup; không coi close tương đương unload.
- [ ] Xóa tham chiếu plugin/class/loader/service provider cũ khỏi mọi registry/cache host.
- [ ] Test restart/hot reload nhiều vòng, kiểm tra threads/listeners/resources về baseline.
- [ ] Kiểm tra heap/thread dump và GC root path khi nghi loader leak.
- [ ] Với plugin không tin cậy/không hợp tác, dùng cách ly tiến trình và chính sách cưỡng chế phù hợp.

## 17. Kết luận và tham khảo

Dừng plugin đúng cách là **một quy trình đảo ngược các phụ thuộc đã tạo lúc start**: ngừng nhận work mới → hủy đăng ký → hoàn tất/hủy các hoạt động đang chạy → đóng resource → close loader → bỏ mọi tham chiếu còn lại. Hủy đăng ký là bước quan trọng nhất để host không giữ plugin bằng callback hoặc registry; shutdown executor và dọn context giúp tránh thread giữ class loader sống lâu.

**`URLClassLoader.close()` không phải lệnh unload class.** Đây chỉ là một phần của việc thu hồi tài nguyên loader; khả năng JVM unload class phụ thuộc vào reachability và GC. Phân biệt trạng thái shutdown của plugin với việc thu hồi class metadata giúp viết ứng dụng có lifecycle chính xác, dễ debug và an toàn hơn.

Tài liệu chính thức:

- Java SE 17 `URLClassLoader` (`close()` và hành vi nạp lớp): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `ExecutorService` (`shutdown`, `shutdownNow`, `awaitTermination`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 `ServiceLoader` (`reload()` và provider cache): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JVMS 17 §5, *Loading, Linking, and Initializing*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
