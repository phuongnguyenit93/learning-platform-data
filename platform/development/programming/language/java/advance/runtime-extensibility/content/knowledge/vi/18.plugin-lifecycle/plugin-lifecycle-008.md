# Hủy callback, lịch chạy, executor và đóng tài nguyên do plugin sở hữu

## 1. Vì sao dừng plugin không đơn giản là gọi stop()?

Một plugin có thể được host nạp động, khởi tạo, bật rồi vô hiệu hóa hoặc thay phiên bản mà **không khởi động lại JVM**. Trong thời gian hoạt động, plugin có thể đăng ký listener vào event bus của host, lên lịch tác vụ lặp lại, tạo thread/executor, mở kết nối hoặc giữ các `AutoCloseable` khác. Chỉ thay trạng thái từ `ACTIVE` sang `STOPPED` không tự hủy những thứ ấy.

Nếu một callback còn trong registry của host, registry có thể tiếp tục gọi vào plugin đã “dừng”. Nếu một task hoặc thread còn chạy, nó có thể giữ đối tượng plugin, `Class<?>` hoặc classloader cũ. Một JAR được tháo khỏi danh sách plugin không có nghĩa các class của nó được JVM giải phóng. Vì vậy, **quản lý vòng đời phải bao gồm tháo đăng ký, hủy công việc và đóng tài nguyên thực sự**.

Bốn nhóm cần kiểm soát:

| Nhóm do plugin sở hữu | Cơ chế có thể tạo ra | Thao tác kết thúc thích hợp |
|---|---|---|
| Callback / listener / subscription | `eventBus.register(...)`, `addListener(...)`, callback của host | Gọi handle `unsubscribe()` / `close()` / `removeListener(...)` tương ứng |
| Lịch chạy / task đã hẹn | `ScheduledExecutorService.schedule(...)`, `scheduleAtFixedRate(...)`, timer của host | Giữ `ScheduledFuture<?>` hoặc token và gọi `cancel(...)` |
| Executor / worker thread | `ExecutorService`, `ScheduledExecutorService`, thread tự tạo | Ngừng nhận task, `shutdown()` hoặc `shutdownNow()` tùy chính sách, `awaitTermination(...)`, bảo đảm worker thực sự kết thúc |
| Tài nguyên I/O và đăng ký bên ngoài | File, stream, socket, watcher, DB connection, `AutoCloseable`, hook/registry | `close()`/`dispose()`/`unregister()` theo đúng API, thường theo thứ tự ngược lúc cấp phát |

**Nguyên tắc quyền sở hữu:** thành phần **nào tạo hoặc được giao quyền quản lý tài nguyên** phải có trách nhiệm đóng/thu hồi tài nguyên ấy. Plugin không được tùy tiện đóng executor hoặc kết nối **dùng chung do host sở hữu**; thay vào đó plugin hủy các task/subscription của mình và trả lại quyền điều khiển cho host.

## 2. Thứ tự dừng an toàn

Một quy trình thực dụng:

```text
Host yêu cầu STOP / UNLOAD
          |
          v
Đánh dấu STOPPING, chặn công việc mới
          |
          v
Hủy đăng ký listener/callback ở host
          |
          v
Hủy các lịch chạy và task đã xếp hàng
          |
          v
Dừng executor/worker do plugin sở hữu
          |
          v
Đợi công việc đang chạy kết thúc (bounded wait)
          |
          v
Đóng tài nguyên I/O, session, connection, watcher
          |
          v
Gỡ tham chiếu từ host/registry/cache, trạng thái STOPPED
          |
          v
Chỉ khi hết tham chiếu mới có cơ hội GC/unload classloader
```

Trình tự cụ thể phụ thuộc phụ thuộc tài nguyên. Mấu chốt là **không đóng một đối tượng đang bị task sử dụng** rồi tiếp tục cho task đó chạy. Đôi khi một resource phải đóng sớm để đánh thức worker đang chờ I/O; host nên thiết kế stop protocol rõ ràng cho trường hợp ấy.

### 2.1. Chặn công việc mới trước

Khi nhận tín hiệu dừng, đặt `accepting=false` (có thể dùng `AtomicBoolean`), đổi trạng thái sang `STOPPING` và từ chối đăng ký tác vụ mới. Nếu làm ngược lại, một callback đang chạy có thể tiếp tục lên lịch công việc ngay sau khi host đã hủy các task cũ.

Một kiểm tra tối thiểu bên trong callback:

```java
if (!accepting.get()) {
    return;
}
handleEvent(event);
```

Đây là **đoạn minh họa**: `accepting` là `AtomicBoolean`, `event` và `handleEvent` do ứng dụng định nghĩa. Kiểm tra cờ không đủ để chứng minh không còn callback nào đang thực thi: callback có thể đã qua điều kiện trước khi host đặt cờ false. Với plugin có yêu cầu dừng mạnh, phải **đợi hoặc phối hợp các callback in-flight** trước khi đóng tài nguyên mà chúng đang sử dụng.

### 2.2. Hủy đăng ký ở nơi đăng ký

Nếu plugin đăng ký vào event bus của host:

```java
AutoCloseable subscription = eventBus.register(listener);
```

hãy giữ **handle đăng ký** để gọi `subscription.close()` khi dừng. Đây là API minh họa do host định nghĩa, không phải API chuẩn của tất cả event bus.

Các API thực tế có dạng khác: `removeListener(listener)`, `unsubscribe()`, `Disposable.dispose()`, `Registration.close()`. Quan trọng là phải giữ đúng listener/registration token; tạo một lambda mới có nội dung giống nhau **không đảm bảo** xóa được lambda đã đăng ký.

```java
// KHÔNG đảm bảo xóa listener đã đăng ký:
bus.addListener(event -> onEvent(event));
bus.removeListener(event -> onEvent(event)); // lambda khác object!
```

Đây là ví dụ **sai có chủ đích**, chỉ minh họa identity của lambda. Cách đúng là lưu listener hoặc handle:

```java
Consumer<Event> listener = event -> onEvent(event);
bus.addListener(listener);
// ... khi dừng:
bus.removeListener(listener);
```

Đoạn này giả định `Event`, `bus` và `onEvent` tồn tại trong API của host.

**Unregister không phải luôn đồng nghĩa drain:** nếu hệ thống đã sao chép danh sách listener để dispatch, một invocation vẫn có thể chạy sau lúc `removeListener` được gọi. Plugin manager cần kết hợp chặn công việc mới, draining các invocation đang chạy hoặc chính sách cho phép hoàn thành trước khi resource bị đóng.

## 3. Hủy ScheduledFuture: cancel là yêu cầu, không phải phép dừng cưỡng bức

Khi tạo task:

```java
ScheduledFuture<?> heartbeat = scheduler.scheduleAtFixedRate(
        this::sendHeartbeat, 0, 10, TimeUnit.SECONDS);
```

hãy lưu `heartbeat`. Lúc dừng:

```java
heartbeat.cancel(true);
```

`Future.cancel(mayInterruptIfRunning)` có ý nghĩa:

- `cancel(false)`: cố hủy các lần chạy chưa bắt đầu; nếu task đang chạy, không yêu cầu ngắt thread chạy task đó.
- `cancel(true)`: cũng **yêu cầu ngắt** thread đang chạy task; không có bảo đảm mã task sẽ lập tức kết thúc. Một số tác vụ không hỗ trợ interrupt, bỏ qua interrupt hoặc đang xử lý I/O theo cách khác.
- `cancel` trả `boolean` theo trạng thái hủy của Future; `true` không có nghĩa mọi tác dụng phụ của task đã được hoàn tác hay mã task đã dừng hoàn toàn.
- `isCancelled()` và `isDone()` giúp quan sát trạng thái Future, nhưng một task đã nhận interrupt vẫn có thể cần thêm thời gian dọn dẹp.

Mã task nên **hợp tác với hủy**, ví dụ kiểm tra `Thread.currentThread().isInterrupted()` khi làm việc theo vòng lặp; nếu bắt `InterruptedException` mà không tiếp tục ném, cần khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` rồi thoát ở thời điểm an toàn.

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn ví dụ ở trong một phương thức trả `void`, không phải chương trình độc lập. Không nên bắt `InterruptedException` rồi tiếp tục chạy vòng lặp vô hạn như chưa hề có lệnh dừng.

**Khác nhau giữa hủy một Future và dừng cả executor:** `heartbeat.cancel(true)` chỉ tác động tới task đó; `scheduler.shutdown()` / `shutdownNow()` tác động tới executor do plugin sở hữu. Nếu plugin đăng ký nhiều lịch, phải quản lý tất cả Futures/tokens, không chỉ lịch cuối cùng.

Đối với `ScheduledThreadPoolExecutor`, việc giữ lại các task đã hủy trong hàng đợi có thể ảnh hưởng bộ nhớ; cấu hình `setRemoveOnCancelPolicy(true)` hữu ích khi có nhiều hủy/đăng ký trong quá trình chạy. Đây là API của **ScheduledThreadPoolExecutor**, không phải phương thức trên mọi `ScheduledExecutorService`.

## 4. ExecutorService: shutdown(), shutdownNow() và awaitTermination()

| API | Tác dụng | Cạm bẫy |
|---|---|---|
| `shutdown()` | Không nhận task mới; cố hoàn tất các task đã gửi trước đó | Task dài/vô hạn có thể ngăn executor kết thúc |
| `shutdownNow()` | Cố dừng các task đang thực thi (thường bằng interrupt), không xử lý các task chờ và trả danh sách task chưa bắt đầu | Không đảm bảo task đang chạy đã dừng; phải phối hợp mã task |
| `awaitTermination(timeout, unit)` | Đợi executor kết thúc hoặc hết hạn thời gian | `false` nghĩa là chưa kết thúc trong hạn; không được coi là đã quiescent |
| `isShutdown()` | Cho biết đã yêu cầu shutdown | Không chứng minh mọi task đã ngừng |
| `isTerminated()` | Cho biết tất cả task đã hoàn tất sau shutdown | Có thể kiểm tra trước khi đóng resource mà task dùng |

Mẫu dừng theo hai pha phổ biến (tùy mức độ ưu tiên graceful shutdown):

```java
// Đoạn minh họa trong một method có thể ném InterruptedException.
executor.shutdown();
if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Executor still running");
    }
}
```

Đây là mã dừng **executor do plugin sở hữu**, không áp dụng cho executor chung của host. Nếu luồng dừng bị interrupt, mã thực tế thường chuyển sang `shutdownNow()`, khôi phục cờ interrupt và báo lại để host xử lý. Không dùng `Thread.stop()` như một cách “dừng chắc chắn”: cơ chế đó không an toàn và đã bị deprecated.

**Scheduled executor có điểm cần xem riêng:** với `ScheduledThreadPoolExecutor`, chính sách mặc định sau `shutdown()` có thể cho phép delayed task đã đăng ký trước tiếp tục chạy theo điều kiện của nó; tác vụ định kỳ có quy tắc tiếp tục khác. Nếu plugin phải ngừng ngay tất cả lịch, nên **hủy từng Future theo ownership** và sau đó shutdown executor. Đừng giả định chỉ gọi `shutdown()` sẽ lập tức hủy mọi lịch.

## 5. Đóng tài nguyên với AutoCloseable và thứ tự phụ thuộc

Nhiều tài nguyên như `InputStream`, `OutputStream`, `Socket`, `WatchService`, `Connection` (JDBC), `ExecutorService` qua cơ chế shutdown, hoặc các handle đăng ký do host cung cấp cần được giải phóng theo contract cụ thể.

### 5.1. Dùng try-with-resources khi phạm vi rõ ràng

```java
try (InputStream input = Files.newInputStream(path)) {
    // Đọc dữ liệu do plugin sở hữu.
}
```

Đây là đoạn minh họa, giả định `path` và các import `java.nio.file.Files`, `java.io.InputStream`. Java gọi `close()` ngay khi rời khối, kể cả khi có exception. Với nhiều tài nguyên trong cùng `try`, Java đóng chúng **theo thứ tự ngược lúc khai báo** và ghi lại lỗi close dưới dạng suppressed exceptions khi cần.

### 5.2. Plugin sống dài hơn một method

Plugin thường có vòng đời kéo dài qua nhiều lời gọi; không thể bọc toàn bộ plugin trong try-with-resources ở `start()` rồi đóng ngay lập tức. Thay vào đó, plugin **lưu handle** đến lúc `stop/close`. Nên giải phóng theo thứ tự ngược khi cấp phát khi các phụ thuộc cho phép.

Ví dụ:

```text
start(): mở DB connection -> tạo watcher -> đăng ký listener -> lên lịch task
stop():  chặn task mới -> hủy listener -> hủy task
         -> đợi worker dừng -> đóng watcher -> đóng DB connection
```

Nếu watcher cần DB connection để dừng hoặc flush, thứ tự ngược là hợp lý. Nếu một task đang chờ trên socket, cần đóng socket sớm để giải phóng task trước khi hoàn tất shutdown; đây là ngoại lệ phải được thiết kế rõ ràng.

**Mỗi handle chỉ nên có một owner rõ ràng**. Nếu host đưa shared connection hoặc shared executor vào plugin, plugin không tự đóng nó, mà chỉ trả lại subscription/task handles thuộc mình.

### 5.3. Dọn tiếp khi một close() thất bại

Giả sử plugin có ba tài nguyên: listener, executor và file. Nếu listener `close()` ném exception, không được bỏ qua việc dừng executor và đóng file. Dùng các khối `try/finally` hoặc một cơ chế tổng hợp lỗi để **tiếp tục cleanup**, đồng thời báo lỗi gốc và gắn các lỗi phụ làm `suppressed`.

Trong một thiết kế lớn, có thể quản lý tài nguyên theo một “cleanup stack” với các `AutoCloseable`, đóng lần lượt theo thứ tự ngược khi dừng. Tuy nhiên, đừng giả định `AutoCloseable.close()` tự idempotent: một số implementation có thể ném lỗi nếu đóng hai lần; lớp quản lý plugin cần bảo vệ trạng thái dừng.

## 6. Ví dụ Java 17 chạy được: listener + lịch chạy + executor + resource

Ví dụ trong **một tệp Java**, không dùng thư viện ngoài. Host quản lý một event bus đơn giản; plugin tự sở hữu một scheduler và resource. Plugin giữ `AutoCloseable` registration token, `ScheduledFuture` của heartbeat, rồi đóng tất cả khi host gọi `close()`.

Để stdout **xác định và dễ so sánh**, heartbeat được lên lịch bắt đầu sau **1 ngày**; chương trình dừng plugin ngay sau sự kiện đầu tiên. Điều này chỉ là lựa chọn kiểm thử, không phải chu kỳ heartbeat được đề xuất cho hệ thống thật.

**Tệp `PluginCleanupDemo.java`:**

```java
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class PluginCleanupDemo {
    static final class EventBus {
        private final CopyOnWriteArrayList<Consumer<String>> listeners =
                new CopyOnWriteArrayList<>();

        AutoCloseable register(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    static final class DemoResource implements AutoCloseable {
        private boolean closed;

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("resource=closed");
            }
        }
    }

    static final class DemoPlugin implements AutoCloseable {
        private final EventBus bus;
        private final ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        private final AtomicBoolean accepting = new AtomicBoolean(false);
        private final DemoResource resource = new DemoResource();

        private AutoCloseable registration;
        private ScheduledFuture<?> heartbeat;
        private boolean started;
        private boolean closed;

        DemoPlugin(EventBus bus) {
            this.bus = bus;
        }

        synchronized void start() throws Exception {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            if (started) {
                return;
            }

            try {
                accepting.set(true);
                registration = bus.register(event -> {
                    if (accepting.get()) {
                        System.out.println("callback=" + event);
                    }
                });

                heartbeat = scheduler.scheduleAtFixedRate(() -> {
                    if (accepting.get()) {
                        System.out.println("heartbeat");
                    }
                }, 1, 1, TimeUnit.DAYS);

                started = true;
                System.out.println("plugin=active");
            } catch (RuntimeException | Error failure) {
                try {
                    close();
                } catch (Exception cleanup) {
                    failure.addSuppressed(cleanup);
                }
                throw failure;
            }
        }

        @Override
        public synchronized void close() throws Exception {
            if (closed) {
                return;
            }
            closed = true;
            accepting.set(false);
            System.out.println("plugin=stopping");

            Exception unregisterFailure = null;
            try {
                if (registration != null) {
                    registration.close();
                }
            } catch (Exception ex) {
                unregisterFailure = ex;
            }

            if (heartbeat != null) {
                heartbeat.cancel(true);
            }
            scheduler.shutdownNow();

            boolean terminated;
            try {
                terminated = scheduler.awaitTermination(3, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                if (unregisterFailure != null) {
                    interrupted.addSuppressed(unregisterFailure);
                }
                throw interrupted;
            }

            if (!terminated) {
                IllegalStateException failure =
                        new IllegalStateException("Executor still running");
                if (unregisterFailure != null) {
                    failure.addSuppressed(unregisterFailure);
                }
                throw failure;
            }

            resource.close();
            System.out.println("plugin=stopped");

            if (unregisterFailure != null) {
                throw unregisterFailure;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        DemoPlugin plugin = new DemoPlugin(bus);
        try {
            plugin.start();
            bus.publish("first");
            System.out.println("listeners.before=" + bus.listenerCount());
        } finally {
            plugin.close();
        }

        plugin.close(); // Lời gọi thứ hai không dọn lặp.
        System.out.println("listeners.after=" + bus.listenerCount());
        bus.publish("second"); // Listener đã được gỡ.
        System.out.println("done");
    }
}
```

**Biên dịch/chạy với JDK 17+** trong thư mục chứa file:

```powershell
javac PluginCleanupDemo.java
java PluginCleanupDemo
```

**Stdout của ví dụ khi chạy bình thường:**

```text
plugin=active
callback=first
listeners.before=1
plugin=stopping
resource=closed
plugin=stopped
listeners.after=0
done
```

Phân tích điều đã xảy ra:

1. `start()` mở trạng thái nhận sự kiện, đăng ký listener và đặt lịch heartbeat; không có heartbeat nào chạy vì delay 1 ngày.
2. Host publish sự kiện `first`, listener thấy `accepting=true` và in `callback=first`.
3. Host gọi `close()` trong `finally`. Plugin đặt `accepting=false` **trước** khi hủy đăng ký.
4. Registration token làm `listeners.remove(...)`; event bus không còn giữ callback của plugin.
5. `heartbeat.cancel(true)` hủy lịch; `shutdownNow()` và `awaitTermination(...)` kết thúc scheduler trước khi resource bị đóng.
6. Resource in `resource=closed` đúng một lần; plugin in `plugin=stopped`.
7. `plugin.close()` lần thứ hai không lặp cleanup. Số listener là `0` và publish `second` không còn gọi callback; cuối cùng in `done`.

Ví dụ cố ý để toàn bộ publish và stop ở **cùng main thread** nhằm có stdout xác định; khi host dispatch callback đồng thời trên thread khác, cần cơ chế draining bổ sung. `AutoCloseable` token trong ví dụ là **một API do event bus demo thiết kế**; hệ framework thực tế sẽ có kiểu token/phương thức hủy riêng.

**Giới hạn mẫu demo:** nếu `awaitTermination` hết hạn, ví dụ **ném lỗi thay vì đóng resource có thể còn bị worker dùng**; trong production, host phải đánh dấu trạng thái cleanup chưa hoàn tất, có cơ chế retry/escalation hoặc cô lập tiến trình. Nếu `close()` bị ngắt, phải tiếp tục theo chính sách dừng, không được tuyên bố plugin đã dỡ hoàn toàn. Ví dụ cũng chỉ tổng hợp lỗi từ `registration.close()`; hệ thống thực tế nên bọc và tổng hợp lỗi từ **mọi** bước cleanup.

## 7. Tránh callback in-flight và race condition khi unload

### 7.1. Unregister không chờ callback đang chạy

Giả sử event bus dùng `CopyOnWriteArrayList` như ví dụ. Khi thread A đang duyệt snapshot listener, thread B gọi `remove(listener)`. Thread A **vẫn có thể giữ reference và gọi listener** từ snapshot cũ. Tương tự, nếu callback đã bắt đầu trước khi `accepting` chuyển false, nó có thể tiếp tục thao tác với resource.

Vì vậy, việc “listener count bằng 0” chỉ chứng minh **không còn đăng ký mới** trong danh sách live, không chứng minh **không còn callback in-flight**. Với callback dùng file/socket/DB, host cần một trong các cơ chế:

- Event bus có API `unregisterAndDrain(...)` hoặc đợi invocation còn chạy.
- Plugin dùng bộ đếm `inFlight`, một `Phaser`, lock/counter hoặc một cơ chế lifecycle gate để đợi những callback đã nhận vào hoàn tất.
- Mọi callback được chuyển qua executor do plugin sở hữu, ngăn nhận task mới và đợi executor quiescent trước khi đóng resource.
- Định nghĩa deadline: nếu callback không chịu dừng, host ghi nhận plugin chưa hoàn tất unload thay vì dùng resource đã đóng.

### 7.2. Khi shutdown tranh chấp với việc schedule()

Một tác vụ có thể đang cố `scheduler.schedule(...)` cùng lúc host gọi shutdown. Hãy đặt cờ `STOPPING` trước, rồi ngăn hoặc từ chối schedule mới. Nếu vẫn có race, `RejectedExecutionException` sau shutdown là trạng thái dự kiến cần xử lý, không nên tự động tạo executor mới để “cứu” một plugin đang dừng.

Nếu plugin tạo thêm `CompletableFuture` hoặc chain callback ngoài scheduler do mình sở hữu, cần kiểm kê **tất cả** nguồn tạo công việc và cơ chế hủy/phối hợp tương ứng. `CompletableFuture.cancel(true)` có quy tắc riêng và không bảo đảm ngắt mã đang thực hiện; phải kiểm tra contract của từng abstraction.

### 7.3. Chặn lời gọi sau stop ở API công khai

Các entry point do host gọi như `handleRequest()` hoặc `onMessage()` nên kiểm tra state, tránh truy cập resource đã đóng. Một enum trạng thái điển hình:

```text
NEW -> STARTING -> ACTIVE -> STOPPING -> STOPPED
          |
          +---------> FAILED -> CLEANUP_ATTEMPTED
```

Đây là state machine **do host/plugin manager định nghĩa**, không phải lifecycle do JVM tự cấp. Nếu `start()` thất bại giữa chừng, vẫn phải thu hồi registration/executor/resource đã tạo trước đó. Nếu `stop()` thất bại, trạng thái phải phản ánh lỗi cleanup, thay vì luôn gắn nhãn `STOPPED` và quên các task còn chạy.

## 8. Ownership và cleanup theo từng loại tài nguyên

| Đối tượng / quyền | Owner thông thường | Thao tác plugin nên làm khi dừng |
|---|---|---|
| Event bus do host cung cấp | Host | Chỉ đóng subscription token hoặc remove listener của plugin |
| Executor riêng tạo bởi plugin | Plugin | Ngăn submit, hủy Future, shutdown, bounded await, giải phóng tham chiếu |
| Executor chung do host cấp | Host | Hủy **task của plugin**, không shutdown cả executor của host |
| `ScheduledFuture` của heartbeat | Plugin hoặc owner registration | `cancel(...)` rồi bảo đảm scheduler/task đã quiescent |
| File stream / socket / watcher plugin mở | Plugin | `close()` sau khi các task dùng nó dừng; kiểm tra lỗi |
| Client DB/HTTP được host chia sẻ | Host hoặc scope quản lý được giao | Không tự đóng client chung; trả lại lease/handle nếu có |
| Executor thread do plugin tạo | Plugin | Yêu cầu kết thúc, tránh thread sống qua unload |
| `ThreadLocal` của worker sống lâu | Thành phần sở hữu worker | Gỡ giá trị khi rời task, tránh giữ instance/classloader cũ |
| `Thread.contextClassLoader` | Thread/executor owner | Phục hồi context classloader sau khi gọi code plugin nếu từng thay |
| MBean, registry, listener OS/GUI | Bên đăng ký hoặc plugin | Unregister/dispose tương ứng; đừng để host giữ reference tới plugin |

**Dọn metadata và registry của host:** khi plugin dừng, host cần xóa entry trong routing table, lookup cache, service registry hoặc danh sách command nếu chúng giữ instance plugin, callback hoặc lớp provider cũ. Đây có thể là nguyên nhân leak ngay cả khi plugin đã đóng mọi file.

**Đừng tự đóng tài nguyên shared:** plugin A không được gọi `hostExecutor.shutdownNow()` nếu plugin B còn dùng executor đó. Phân biệt ownership ở API thiết kế ngay từ đầu, ví dụ truyền `Executor` không có quyền shutdown hoặc cấp riêng `TaskHandle` cho các công việc plugin đăng ký.

## 9. Nguy cơ classloader leak khi đóng plugin

Trong hệ dùng `URLClassLoader` hoặc `ModuleLayer` riêng cho plugin, Java không cung cấp “unload lớp ngay lập tức” chỉ bằng cách xóa JAR khỏi thư mục hay gọi `close()` trên loader. Class unloading phụ thuộc khả năng thu gom classloader định nghĩa lớp và các object còn liên quan.

Những nguồn giữ tham chiếu thường gặp:

1. **Thread còn chạy**: stack frame, target runnable, `ThreadLocal` hoặc context classloader có thể giữ lớp/plugin loader.
2. **`ScheduledFuture` và hàng đợi executor**: task lambda/`Runnable` có thể capture `this` của plugin; scheduler chưa shutdown vẫn giữ task.
3. **Event bus/registry của host**: listener lambda capture plugin instance và được host giữ lâu dài.
4. **Cache tĩnh hoặc singleton phía host**: map giữ `Class`, `Method`, callback hoặc provider object từ plugin.
5. **ServiceLoader/provider cache, logging hook, MBean, file watcher**: cơ chế tích hợp giữ callback hoặc class cũ.
6. **Thread context class loader (TCCL)**: thread pool do host sở hữu từng đổi TCCL sang pluginLoader nhưng quên phục hồi.

`URLClassLoader.close()` giúp đóng các tài nguyên do loader quản lý, nhưng không tự dừng worker và không bảo đảm class được GC. Đừng đóng loader **trước khi** các tác vụ/plugin callback cần dùng lớp/tài nguyên của loader đã kết thúc. Thứ tự thường là: **stop plugin → ngừng background work → unregister → close I/O → gỡ tham chiếu → close loader**. Thời điểm garbage collection/unload là quyết định của JVM, không có bảo đảm tức thì.

### Kiểm tra rò rỉ

Có thể dùng kiểm thử integration theo vòng:

- Load một plugin bằng classloader riêng.
- Tạo listener, schedule và tài nguyên thử.
- Stop/unload plugin.
- Kiểm tra registry không còn listener/task, executor terminated và các resource báo đã close.
- Lặp lại nhiều vòng để quan sát thread count, heap, file handle và lượng classloader còn giữ.
- Nếu dùng `WeakReference<ClassLoader>` để quan sát, đừng coi một lần gọi `System.gc()` là phép chứng minh đầy đủ: GC không bảo đảm xảy ra theo yêu cầu.

## 10. Xử lý lỗi và thời gian dừng

### 10.1. Không để cleanup dừng ở lỗi đầu tiên

Một lời gọi `registration.close()` có thể lỗi trong khi scheduler và file vẫn cần đóng. Production nên gom lỗi:

```text
- Dừng nhận công việc mới.
- Thử unregister callback; ghi lại failure nếu có.
- Thử cancel lịch; ghi lại failure nếu có.
- Shutdown executor; đợi trong deadline và ghi nhận timeout.
- Nếu không còn task sử dụng resource, thử đóng resource; ghi nhận lỗi.
- Báo lại trạng thái cleanup và các lỗi kèm suppressed exceptions.
```

Không nuốt ngoại lệ rồi in “stopped” nếu vẫn còn worker chưa dừng. `InterruptedException` trong thread thực hiện cleanup cần được xử lý theo chính sách: thường yêu cầu dừng nhanh, khôi phục interrupt flag, báo host và không khẳng định dỡ sạch plugin.

### 10.2. Timeout không phải thanh công

Khi `awaitTermination(5, TimeUnit.SECONDS)` trả `false`, host biết **chưa chứng minh được executor terminated**. Có thể tăng thời gian theo chính sách, cảnh báo, cách ly tiến trình plugin, hoặc từ chối unload để tránh thao tác với resource đã đóng. Không ép hủy bằng `Thread.stop()`.

Với hệ thống chứa plugin không đáng tin, chạy plugin trong **tiến trình cách ly** có thể giúp host thực thi giới hạn thời gian/tài nguyên tốt hơn. Classloader hay TCCL không phải sandbox an toàn.

### 10.3. ShutdownGraceful và ShutdownImmediate là hai chính sách

Plugin xử lý giao dịch có thể cần **graceful shutdown**: từ chối yêu cầu mới, chờ hoàn thành giao dịch trong một deadline, flush dữ liệu rồi đóng connection. Plugin xử lý nhiệm vụ thuần tính toán có thể ưu tiên **cancel/interrupt** ngay. Không dùng cùng thứ tự/timeout một cách máy móc cho mọi plugin; hợp đồng lifecycle phải xác định semantics của các tác vụ in-flight.

## 11. Checklist trước khi coi plugin đã dừng

- [ ] Trạng thái đã chuyển sang `STOPPING` trước khi đóng registry/task?
- [ ] Không còn lời gọi mới từ host đến plugin?
- [ ] Mọi listener/subscription đã được unregister, và callback đang chạy được drain hoặc xử lý rõ?
- [ ] Tất cả scheduled task / timer / retry loop đã cancel?
- [ ] Executor do plugin sở hữu đã shutdown; đã kiểm tra `isTerminated()` hoặc `awaitTermination(...)`?
- [ ] Mã task hợp tác với `interrupt`; không có worker sống bất thường?
- [ ] Các tài nguyên plugin tạo đã close, kể cả khi một close khác thất bại?
- [ ] Không vô tình đóng shared resource do host/plugin khác sở hữu?
- [ ] Registry/cache/TCCL/ThreadLocal của host không còn giữ plugin?
- [ ] `close()` idempotent và xử lý startup failure?
- [ ] Trạng thái cuối cùng phản ánh đúng `STOPPED` hay `FAILED_TO_STOP`, có log/cause?

Danh sách này là **tiêu chí nghiệm thu** cho một plugin manager, không phải một hành động JVM tự làm.

## 12. Bài tập và câu hỏi ôn tập

1. **Vì sao unregister listener chưa đủ để đóng resource ngay?** Vì callback đã bắt đầu hoặc đang nằm trong snapshot dispatch có thể tiếp tục chạy.
2. **`ScheduledFuture.cancel(true)` có đảm bảo task đã dừng chưa?** Không. Nó yêu cầu hủy/interrupt; task phải hợp tác và có thể cần đợi termination.
3. **Khi nào dùng `shutdown()` và khi nào dùng `shutdownNow()`?** Tùy chính sách graceful vs immediate; với cả hai, vẫn cần kiểm tra tác vụ đã chấm dứt.
4. **Plugin được host cấp shared executor có được gọi `shutdownNow()` không?** Thông thường không; plugin chỉ hủy công việc mình sở hữu.
5. **Vì sao Java không thể unload plugin chỉ bằng cách close URLClassLoader?** Vì thread, registry, task, cache, provider hoặc đối tượng khác vẫn có thể giữ tham chiếu tới loader/class.
6. **Tại sao close nên idempotent?** Host có thể gọi stop nhiều lần hoặc gọi cleanup sau startup failure; dọn lặp có thể ném lỗi, đóng nhầm tài nguyên hoặc làm sai trạng thái.
7. **Nếu awaitTermination timeout, có nên đánh dấu STOPPED thành công không?** Không; phải ghi nhận chưa hoàn tất, thực hiện escalation hoặc isolation phù hợp.

**Thực hành 1:** đổi delay heartbeat thành `0` và chu kỳ `100` mili-giây; quan sát một số heartbeat khi plugin hoạt động. Để kiểm thử xác định, dùng latch thay vì dựa vào `Thread.sleep`, và bảo đảm sau stop không còn tick mới.

**Thực hành 2:** giả lập lỗi trong `registration.close()`. Chỉnh cleanup để vẫn dừng scheduler và đóng resource, cuối cùng ném lỗi gốc cùng các lỗi phụ dưới dạng `suppressed`.

**Thực hành 3:** tạo hai plugin dùng chung host event bus nhưng mỗi plugin có scheduler riêng. Stop plugin A và kiểm tra plugin B vẫn nhận sự kiện; sau đó stop B và xác minh listener count bằng 0.

**Thực hành 4:** truyền executor dùng chung từ host thay vì tạo riêng trong plugin. Thiết kế API chỉ trả về token `cancelTask()`; xác nhận stop plugin A không shutdown executor của B.

## Tài liệu tham khảo

- Oracle Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 — `ScheduledExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
- Oracle Java SE 17 — `Future` và `cancel(boolean)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `ScheduledThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
- Oracle Java SE 17 — `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Oracle Java SE 17 — `URLClassLoader` và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
