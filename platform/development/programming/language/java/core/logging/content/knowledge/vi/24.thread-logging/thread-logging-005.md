# Context của thread khi ghi log trong Java

## 1. Context của thread là gì?

Khi nhiều yêu cầu chạy đồng thời, các dòng log từ những luồng khác nhau thường xen kẽ nhau. Chỉ thấy thông báo “Bắt đầu xử lý”, “Gọi database”, “Hoàn thành” thì khó biết mỗi dòng thuộc yêu cầu nào. **Logging context** là tập thông tin đi kèm một đơn vị công việc (request, tác vụ, giao dịch) để các dòng log có thể được liên kết với nhau.

Ví dụ các trường thường gặp:

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| `requestId` | Nhận diện một HTTP request hoặc công việc cụ thể | Sinh hoặc kiểm tra giá trị ở ranh giới tiếp nhận request |
| `traceId`, `spanId` | Liên kết log với trace/span của hệ thống quan sát phân tán | Do thư viện tracing quản lý, cần cơ chế truyền qua mạng |
| `operation`, `component` | Cho biết thao tác hoặc thành phần đang xử lý | Giữ giá trị ngắn, có ý nghĩa |
| `thread` / tên thread | Hỗ trợ xác định luồng đang ghi log | Một thread trong pool có thể xử lý nhiều request liên tiếp |

Ví dụ minh họa:

```text
[http-worker-1] requestId=req-101 INFO Bắt đầu xử lý
[http-worker-2] requestId=req-102 INFO Bắt đầu xử lý
[http-worker-1] requestId=req-101 INFO Đã lưu dữ liệu
[http-worker-2] requestId=req-102 INFO Đã lưu dữ liệu
```

Hai yêu cầu xen kẽ nhưng vẫn phân biệt được qua `requestId`. **Tên thread chỉ cho biết nơi lệnh log được thực hiện tại thời điểm đó; nó không phải định danh của request.** “Context của thread” trong bài này nói về dữ liệu chẩn đoán phục vụ logging, không phải `Thread.State`, context class loader hay trạng thái nghiệp vụ chung của toàn ứng dụng.

## 2. Cơ chế nền tảng: `ThreadLocal<T>`

`ThreadLocal<T>` cho mỗi thread một giá trị riêng của cùng biến `ThreadLocal`: thread A gọi `set(x)` thì thread B không tự thấy `x` khi gọi `get()`. API chính gồm `set(value)`, `get()` và `remove()`. Vì vậy, `ThreadLocal` thường được dùng để giữ thông tin cần xuất hiện trong nhiều phương thức được gọi liên tiếp trên **cùng một thread**, mà không phải truyền thêm tham số qua từng phương thức.

Cần phân biệt hai vòng đời:

- **Vòng đời thread:** một thread trong `ExecutorService` có thể sống lâu và chạy nhiều tác vụ.
- **Vòng đời context:** `requestId` thường chỉ có hiệu lực trong một request hoặc tác vụ, sau đó phải được dọn dẹp.

### Ví dụ Java 17+ chạy độc lập

Tệp `ThreadContextDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private static void log(String step) {
        System.out.printf("[%s] requestId=%s | %s%n",
                Thread.currentThread().getName(), REQUEST_ID.get(), step);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "worker-1"));

        try {
            REQUEST_ID.set("req-42");
            log("receive");

            pool.submit(() -> log("without-propagation")).get();

            String captured = REQUEST_ID.get();
            pool.submit(() -> {
                String previous = REQUEST_ID.get();
                try {
                    if (captured == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(captured);
                    }
                    log("with-propagation");
                } finally {
                    if (previous == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(previous);
                    }
                }
            }).get();

            pool.submit(() -> log("after-cleanup")).get();
        } finally {
            REQUEST_ID.remove();
            pool.shutdown();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ThreadContextDemo.java
java ThreadContextDemo
```

Kết quả stdout (các tác vụ được `get()` đợi theo thứ tự; thread của pool được đặt tên cố định):

```text
[main] requestId=req-42 | receive
[worker-1] requestId=null | without-propagation
[worker-1] requestId=req-42 | with-propagation
[worker-1] requestId=null | after-cleanup
```

Giải thích:

1. Thread `main` giữ `req-42` trong `REQUEST_ID` của chính nó.
2. Công việc gửi sang `worker-1` **không tự nhận** giá trị `ThreadLocal` của `main`.
3. Chương trình chủ động chụp giá trị ở thread gửi, thiết lập tại thread nhận trước khi ghi log, rồi khôi phục giá trị cũ trong `finally`.
4. Công việc tiếp theo dùng lại `worker-1` thấy `null`, chứng tỏ request trước không làm rò ngữ cảnh sang request sau.

Ví dụ này cố tình dùng `ThreadLocal` thuần Java để làm rõ nguyên lý. Trong ứng dụng có logging framework, hãy dùng API MDC của framework để gắn các trường chẩn đoán vào log; đừng tự xây một cơ chế ghi log toàn diện chỉ từ ví dụ này.

## 3. MDC: đưa context vào dòng log

**MDC (Mapped Diagnostic Context)** là cơ chế lưu các cặp khóa–giá trị chẩn đoán gắn với ngữ cảnh thực thi hiện tại. Trong hệ sinh thái SLF4J, lớp `org.slf4j.MDC` cung cấp các thao tác quen thuộc:

| API | Ý nghĩa |
| --- | --- |
| `MDC.put("requestId", id)` | Gắn hoặc thay giá trị trong context hiện tại |
| `MDC.get("requestId")` | Lấy một giá trị |
| `MDC.remove("requestId")` | Bỏ một khóa |
| `MDC.clear()` | Xóa context hiện tại |
| `MDC.getCopyOfContextMap()` | Lấy bản sao snapshot các trường, có thể là `null` |
| `MDC.setContextMap(map)` | Thay context hiện tại bằng một map được sao chép |

`MDC` của SLF4J là facade; hành vi lưu trữ và xuất log phụ thuộc vào **logging backend** thực tế (ví dụ Logback). Trong cách dùng phổ biến với Logback, MDC là ngữ cảnh riêng theo thread và được đưa vào bản ghi log khi logger tạo sự kiện. Không nên giả định mọi backend có cùng quy tắc kế thừa hoặc tự truyền context sang thread khác. Ứng dụng phải có cả SLF4J API và một backend được cấu hình phù hợp; nếu thiếu backend hỗ trợ, gọi MDC không đảm bảo tạo ra trường trong output.

### Thiết lập tại đầu request, khôi phục ở cuối

Đây là một lớp minh họa có thể đặt trong ứng dụng Java dùng SLF4J và Logback; phương thức `process` được gọi từ nơi tiếp nhận request:

```java
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class PaymentLogger {
    private static final Logger LOG = LoggerFactory.getLogger(PaymentLogger.class);

    public void process(String requestId) {
        Objects.requireNonNull(requestId, "requestId");
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("requestId", requestId);
            MDC.put("component", "payment");

            LOG.info("Bắt đầu xử lý thanh toán");
            LOG.info("Hoàn tất xử lý thanh toán");
        } finally {
            restore(previous);
        }
    }

    private static void restore(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
```

`previous` giữ toàn bộ context tồn tại trước lời gọi. Cách khôi phục này quan trọng khi `process` được gọi lồng bên trong một phạm vi khác đã có `requestId` hoặc các khóa MDC khác. Nếu chỉ gọi `clear()` vô điều kiện, phương thức có thể xóa context của bên gọi. Tại biên ngoài cùng, nếu trước đó không có context thì `restore(null)` sẽ xóa sạch giá trị mới thiết lập. `finally` chạy cả khi phần xử lý phát sinh exception.

### Cấu hình Logback để in MDC

Với Logback, ví dụ `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level requestId=%X{requestId} component=%X{component} %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%thread` in tên thread; `%X{requestId}` và `%X{component}` lấy trường từ MDC; `%msg` là nội dung thông báo. Khi gọi `process("req-42")`, hai log của phương thức sẽ mang `requestId=req-42` và `component=payment`; thời gian, mức log và logger vẫn do Logback định dạng. Nếu trường chưa được đặt, chỗ thay thế MDC thường rỗng. Cú pháp pattern này dành cho **Logback**; khi dùng Log4j2 cần xem cấu hình và API `ThreadContext` tương ứng.

MDC hữu ích vì mỗi lớp gọi `LOG.info(...)` không phải nhận và nối `requestId` vào từng chuỗi thông báo. Tuy nhiên, MDC chỉ là **thông tin phục vụ chẩn đoán**: không dùng nó làm nguồn dữ liệu nghiệp vụ, quyền truy cập hay cách thay thế tham số bắt buộc của phương thức.

## 4. Qua ranh giới thread: phải truyền context có chủ đích

Ví dụ thường gặp: thread xử lý HTTP request đặt MDC rồi gọi `executor.submit(...)`, `CompletableFuture.runAsync(...)` hoặc một callback bất đồng bộ. Tác vụ có thể chạy trên thread khác, vốn có MDC riêng. Nếu bỏ qua ranh giới này, log ở phần xử lý async có thể thiếu `requestId` hoặc nguy hiểm hơn là chứa context cũ do thread pool chưa được dọn dẹp.

Một cách truyền rõ ràng gồm bốn bước: **chụp snapshot lúc gửi việc → lưu context trước đó ở thread nhận → cài snapshot rồi chạy việc → khôi phục trong `finally`**. Không dùng một `Map` biến đổi dùng chung cho nhiều request.

### Ví dụ tích hợp với SLF4J MDC và `CompletableFuture`

Tệp `MdcPropagationExample.java` dưới đây chạy trong dự án đã có dependency SLF4J và backend Logback được cấu hình như phần trên:

```java
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MdcPropagationExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(MdcPropagationExample.class);

    private static void restore(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    private static Runnable withCapturedMdc(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                restore(captured);
                task.run();
            } finally {
                restore(previous);
            }
        };
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "log-worker"));
        Map<String, String> original = MDC.getCopyOfContextMap();

        try {
            MDC.put("requestId", "req-42");
            LOG.info("Nhận yêu cầu");

            CompletableFuture<Void> future = CompletableFuture.runAsync(
                    withCapturedMdc(() -> LOG.info("Xử lý async")),
                    executor);
            future.join();
        } finally {
            restore(original);
            executor.shutdown();
        }
    }
}
```

Với pattern ở trên, hai dòng log sẽ có `requestId=req-42`, một dòng từ `main` và một dòng từ `log-worker`. Thời gian chạy và phần tên logger thay đổi tùy cấu hình; đó là **minh họa hành vi**, không phải stdout cố định như ví dụ `ThreadContextDemo`.

Điểm cần hiểu:

- `withCapturedMdc(...)` được gọi **ở thread gửi**, vì vậy snapshot đúng là context tại thời điểm tạo tác vụ; đặt lời gọi vào trong lambda của worker sẽ lấy nhầm context của worker.
- `restore(captured)` thiết lập cả trường hợp snapshot trống, tránh tác vụ vô tình dùng context đang có sẵn ở thread pool.
- `restore(previous)` trong `finally` trả thread nhận về đúng trạng thái trước khi chạy, kể cả khi task ném exception.
- `CompletableFuture` chỉ quản lý hoàn thành và giá trị kết quả; bản thân nó không hứa tự sao chép MDC. Các stage sau đó, đặc biệt các stage `*Async`, cũng cần cơ chế truyền context thích hợp.
- Đoạn wrapper minh họa cho `Runnable`. Khi dùng `Callable<T>` hoặc `Supplier<T>`, áp dụng nguyên tắc snapshot/khôi phục tương tự hoặc dùng bộ tích hợp của framework/tracing library thay vì bỏ sót luồng thực thi.

Nếu ứng dụng đã có cơ chế context propagation do framework cung cấp (ví dụ task decorator, instrumentation của hệ thống quan sát), ưu tiên cấu hình nhất quán ở ranh giới executor thay vì để mỗi nhóm tự tạo wrapper hơi khác nhau.

## 5. Context theo request không đồng nghĩa context theo thread

Xét một luồng xử lý:

```text
HTTP request req-42
    |
    v
Thread A: đặt MDC, ghi log
    |
    +--> Executor / CompletableFuture --> Thread B: cần chuyển MDC
    |
    +--> HTTP call sang service khác --> cần truyền trace/request header
    |
    v
Kết thúc request: khôi phục hoặc xóa MDC ở Thread A
```

- **Đổi thread trong cùng JVM:** `ThreadLocal`/MDC gắn với thread hiện tại, do đó phải truyền đúng dữ liệu tại nơi chuyển giao tác vụ.
- **Đổi process/service qua HTTP, message queue:** MDC của JVM không tự đi qua mạng. Cần cơ chế propagator cho trace context hoặc header tương ứng; service nhận mới đọc, xác thực rồi đưa các trường cần thiết vào logging context của nó.
- **Distributed tracing:** `traceId`/`spanId` có ngữ nghĩa và vòng đời riêng. OpenTelemetry hoặc công cụ tracing quản lý trace context và có thể tích hợp để MDC hiển thị các ID này. Việc tự đặt một khóa `traceId` trong MDC không tự tạo span hay truyền trace sang service khác.
- **Reactive/asynchronous pipelines:** trong Reactor hoặc các pipeline mà một công việc có thể chạy qua nhiều thread, dùng cơ chế context của framework và tích hợp truyền context; không giả định toàn bộ pipeline luôn ở một thread.
- **`InheritableThreadLocal`:** chỉ nói đến việc khởi tạo giá trị cho thread con lúc thread được tạo; không phải cơ chế truyền context mỗi lần nộp task vào executor đã có thread. Nó không giải quyết việc tái sử dụng thread pool và cần xem ngữ nghĩa kế thừa cụ thể.
- **Virtual threads (Java 21+):** có hỗ trợ `ThreadLocal`, nhưng đó vẫn là dữ liệu gắn với thread, không mặc nhiên là context của một chuỗi tác vụ phân tán. Tránh giữ map hoặc đối tượng lớn cho mỗi virtual thread và vẫn cleanup đúng phạm vi.

Khi request có nhiều nhánh song song, snapshot đúng thời điểm giúp mọi nhánh có cùng correlation ID mà không chia sẻ map mutable. Nếu một nhánh cần thêm trường riêng (ví dụ `operation`), hãy thêm trong phạm vi của nhánh rồi khôi phục trước khi thoát.

## 6. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Log async mất `requestId` | Task chạy trên thread khác | Capture/propagate context tại ranh giới submit, khôi phục sau task |
| Request B xuất hiện ID của request A | Thread pool tái sử dụng thread còn MDC cũ | `try/finally` với snapshot và restore/clear ở mọi entrypoint |
| Hàm lồng làm mất context bên ngoài | Gọi `MDC.clear()` khi kết thúc hàm con | Lưu map trước khi thay đổi và khôi phục map cũ |
| Log chỉ có tên `pool-...`, khó ghép request | Tên worker không định danh công việc | Dùng `requestId`/`traceId` nhất quán |
| Có `traceId` trong log nhưng không nối được các service | Chỉ trang trí log, không propagate qua mạng | Dùng trace-context propagator và instrumentation thực sự |
| Log lộ token hoặc dữ liệu khách hàng | Đưa dữ liệu nhạy cảm vào MDC | Chỉ lưu trường được phép, kiểm soát nguồn và định dạng |
| Context tăng bộ nhớ theo thời gian | Thread sống lâu giữ tham chiếu qua `ThreadLocal` hoặc context quá lớn | Dọn ở `finally`; MDC chỉ giữ vài chuỗi ngắn cần thiết |

Thói quen kiểm thử hữu ích: chạy hai request lần lượt trên **cùng một thread pool một worker** với ID khác nhau, xác nhận log của từng request đúng ID và tác vụ không context ở cuối không còn ID cũ. Kiểm tra thêm nhánh ném exception để bảo đảm `finally` vẫn khôi phục. Với async, kiểm tra log cả trước và sau chuyển thread. Với hệ thống phân tán, kiểm tra trace/header thực tế ở service nhận.

## 7. Quy tắc áp dụng trong dự án

1. **Đặt context ở ranh giới vào** (HTTP filter/interceptor, message consumer, job runner), sau khi tạo hoặc xác thực ID hợp lệ. Dùng ID truy vết không chứa dữ liệu nhạy cảm; tránh tin tuyệt đối vào header do client tùy ý gửi.
2. **Ghi log có cấu trúc và thống nhất khóa** (ví dụ `requestId`, `traceId`, `spanId`) qua các lớp. Đặt thread name ở pattern nếu cần, nhưng đừng dùng nó thay ID của công việc.
3. **Truyền context ở mọi điểm đổi môi trường thực thi**: executor, `CompletableFuture`, scheduled job, message handler, network boundary. Dùng thư viện hỗ trợ khi có để tránh viết lặp và sót đường đi.
4. **Giới hạn vòng đời bằng `try/finally`**; khôi phục context trước đó để an toàn với lời gọi lồng nhau. Không đặt một ID cố định ở static field dùng chung cho nhiều request.
5. **Không đưa mật khẩu, token, cookie, thông tin cá nhân hoặc object lớn vào MDC.** MDC dùng để chẩn đoán; dữ liệu nghiệp vụ và quyền hạn phải được truyền, kiểm tra bằng cơ chế riêng.

**Ghi nhớ:** thread là nơi thực thi, còn request/task là đơn vị cần theo dõi. MDC giúp đưa dữ liệu chẩn đoán vào log của thread hiện tại; muốn giữ correlation xuyên qua bất đồng bộ hoặc qua service, ứng dụng phải truyền context đúng ranh giới và luôn dọn sau khi sử dụng.
