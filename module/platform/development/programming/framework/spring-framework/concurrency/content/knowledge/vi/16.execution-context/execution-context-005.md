# Truyền mã liên kết yêu cầu và ngữ cảnh ghi nhật ký trong Spring Framework

Khi một HTTP request đi qua controller rồi được giao cho `@Async`, `ThreadPoolTaskExecutor` hoặc `CompletableFuture`, mã liên kết yêu cầu (*correlation ID*) thường bị mất khỏi các dòng log ở worker thread. Nguyên nhân không phải Spring “đánh rơi” một tham số thông thường, mà vì nhiều thư viện logging lưu **Mapped Diagnostic Context (MDC)** theo **thread**. Thread xử lý HTTP và thread lấy task từ pool không nhất thiết là một. Thread pool còn **tái sử dụng worker**, nên nếu không dọn context đúng cách, một request có thể bị gắn nhầm mã của request trước.

Mục tiêu của bài học thuộc nhóm **Ngữ cảnh thực thi** của module **Spring Framework – concurrency** là xây dựng cách truyền correlation ID và logging context qua ranh giới bất đồng bộ **đúng thời điểm, đúng phạm vi, có cleanup**, đồng thời phân biệt với distributed tracing và security context. Những quy tắc này giúp truy vết một yêu cầu qua controller, executor, worker và các dịch vụ tiếp theo mà không trộn log của nhiều khách hàng.

> Nguyên tắc cốt lõi: **correlation ID là dữ liệu định danh luồng xử lý; MDC chỉ là một phương tiện gắn dữ liệu đó vào log của thread hiện tại.** Nếu muốn giá trị đi qua một task hoặc một hệ thống khác, phải có cơ chế truyền riêng; không thể dựa vào việc cùng một JVM hay cùng một request.

## 1. Correlation ID giải quyết vấn đề gì?

Một request tạo báo cáo có thể trải qua nhiều bước:

```text
                         X-Correlation-ID: req-8f2
                                      |
                                      v
Client ----HTTP----> Spring MVC Filter ----> Controller / Service
                           |                       |
                           | MDC[corrId=req-8f2]   | submit
                           v                       v
                     Log request thread     ThreadPoolTaskExecutor
                                                    |
                                       [queue] -> pooled worker
                                                    |
                                         MDC cần được truyền
                                                    |
                                            Database / API
                                                    |
                                          outbound HTTP header
                                                    |
                                                    v
                                              Downstream service
```

Nếu các dòng log có cùng mã `req-8f2`, hệ thống quan sát có thể tìm toàn bộ sự kiện liên quan đến cùng một yêu cầu, kể cả khi các bước thực thi trên nhiều thread hoặc nhiều dịch vụ.

Ví dụ log minh họa:

```text
INFO  [http-nio-8080-exec-2] [corr=req-8f2] Received report request
INFO  [report-1]            [corr=req-8f2] Started report generation
INFO  [report-1]            [corr=req-8f2] Stored report result
```

Các tên thread ở ví dụ chỉ minh họa; thread thực tế, thời điểm và thứ tự log phụ thuộc executor/scheduler.

**Không có correlation ID**, việc tra các dòng log chỉ theo timestamp, endpoint hoặc tên worker rất dễ sai khi ứng dụng xử lý hàng nghìn task song song. **Có correlation ID nhưng truyền sai**, còn nguy hiểm hơn vì log của hai yêu cầu có thể bị nhập chung, khiến quá trình điều tra sai nguyên nhân.

### 1.1. Ba yêu cầu của một correlation ID tốt

1. **Ổn định trong phạm vi logic cần truy vết.** Các bước xử lý cùng một request/job nên biết cùng ID hoặc quan hệ parent-child rõ ràng.
2. **Có thể truyền qua ranh giới.** HTTP header, queue message metadata, job payload và task wrapper đều có cơ chế cụ thể.
3. **Không chứa bí mật hoặc PII.** Tránh email, token, số thẻ, số điện thoại hay nội dung nghiệp vụ nhạy cảm làm correlation ID. Mã cần đủ khó trùng và có validation/giới hạn độ dài nếu lấy từ client.

Correlation ID **không phải** bằng chứng authentication/authorization; bất kỳ người dùng nào cũng có thể gửi một HTTP header giả nếu hệ thống công khai cho phép. Dùng ID để tìm log, **không dùng nó làm điều kiện cấp quyền**.

## 2. Phân biệt correlation ID, request ID, job ID, trace ID và span ID

Các hệ thống dùng những từ gần nhau nhưng phạm vi khác nhau. Không nên ép một biến vào mọi vai trò.

| Định danh | Phạm vi điển hình | Dùng để làm gì? |
| --- | --- | --- |
| **Request ID** | Một HTTP request tại một service/edge | Tìm log hoặc lỗi gắn với request cụ thể |
| **Correlation ID** | Một luồng nghiệp vụ có thể qua nhiều bước | Gom log của các bước liên quan, có thể qua async/broker |
| **Job ID** | Một tác vụ nền được theo dõi | Truy vấn trạng thái QUEUED/RUNNING/SUCCEEDED/FAILED |
| **Trace ID** | Một distributed trace | Liên kết các span theo chuẩn tracing |
| **Span ID** | Một bước/operation trong trace | Định danh hoạt động con, đo latency/parent-child |
| **Idempotency key** | Một yêu cầu logic có thể gửi lại | Tránh thực hiện tác động nghiệp vụ hai lần |

Ví dụ một client POST tạo báo cáo với `X-Correlation-ID=req-8f2`. Server có thể tạo `jobId=job-92` rồi trả HTTP 202. Nếu worker chạy sau khi HTTP response đã kết thúc, log của worker có thể lưu cả `correlationId=req-8f2` và `jobId=job-92`. Một client khác gọi `GET /jobs/job-92` tạo **request ID mới**, nhưng vẫn liên hệ được với cùng job.

**Distributed tracing** thường dùng chuẩn W3C Trace Context như `traceparent` và `tracestate`; `traceId`/`spanId` có định dạng và ngữ nghĩa riêng. Một custom header `X-Correlation-ID` **không thay thế** tracing instrumentation. Nếu dùng Micrometer Tracing/OpenTelemetry, ưu tiên quy tắc propagation của tracing framework; có thể ghi thêm correlation ID khi nghiệp vụ cần.

## 3. MDC là gì? Vì sao dễ mất khi sang thread khác?

`org.slf4j.MDC` cung cấp API để đặt/đọc các cặp key-value dùng trong logging context:

```java
MDC.put("correlationId", "req-8f2");
String id = MDC.get("correlationId");
MDC.remove("correlationId");
MDC.clear();
```

Đây là **fragment**, cần SLF4J API và một backend hỗ trợ MDC như Logback trong project. MDC không phải API lưu trạng thái request ở database; nó lưu ngữ cảnh được logging adapter gắn với thread hiện tại.

Trong mô hình SLF4J/Logback phổ biến, MDC dùng thread-local context:

```text
Thread HTTP-A     MDC = { correlationId: req-A }
Thread HTTP-B     MDC = { correlationId: req-B }
Thread worker-1   MDC = { }          // Chưa tự nhận req-A
Thread worker-2   MDC = { }          // Chưa tự nhận req-B
```

Từ đó có hai lỗi đối nghịch:

- **Không truyền:** worker log không có mã `correlationId`, dù caller đang có.
- **Không dọn:** worker giữ MDC của task trước; lần sau có thể gắn nhầm `req-A` vào log của task `req-B`.

Hãy phân biệt:

- **ThreadLocal:** cơ chế lưu dữ liệu theo thread; không tự gắn dữ liệu vào `Runnable`/`Callable` được giao qua executor.
- **MDC:** API logging abstraction có backend cụ thể. Với Logback, MDC thường gắn với thread-local, do đó cần sao chép/khôi phục khi chuyển thread.
- **InheritableThreadLocal:** có thể truyền snapshot khi *tạo thread con* trong một số tình huống, nhưng **không phù hợp làm lời giải mặc định cho thread pool tái sử dụng**. Worker thường được tạo trước khi request tới, và dữ liệu có thể rò rỉ giữa các request.
- **Reactor Context:** context theo luồng reactive subscription; không đồng nhất với `ThreadLocal`. WebFlux có thể đổi thread, nên cần cơ chế tích hợp context propagation riêng.

**Không có ràng buộc:** một object `CompletableFuture` không tự chuyển toàn bộ MDC của thread caller sang mọi dependent callback.

## 4. Vì sao ThreadPoolTaskExecutor cần cách truyền có chủ đích?

`ThreadPoolTaskExecutor` của Spring quản lý một pool worker và hàng đợi. Khi controller gọi:

```java
executor.execute(() -> generateReport(reportId));
```

`execute` giao một `Runnable` cho executor. Worker sẽ chạy task vào một thời điểm khác, có thể trên một thread tồn tại sẵn. MDC của controller được đặt trên thread request, **không tự nằm trong worker**.

Một cách giải quyết là **chụp (capture) context tại thời điểm submit** và **cài đặt (install) context đó khi worker bắt đầu chạy**. Cuối cùng **khôi phục context có trước của worker**, kể cả khi task ném exception:

```text
Request thread:  MDC[corr=req-8f2]
       |
       | submit
       v
TaskDecorator chụp snapshot {corr=req-8f2}
       |
       | executor queue
       v
Worker thread:
    previous = snapshot MDC hiện có của worker
    try:
        install {corr=req-8f2}
        run business task
    finally:
        restore previous
```

Với `ThreadPoolTaskExecutor`, Spring cung cấp `TaskDecorator` để bọc `Runnable` được executor nhận. Đây là điểm thích hợp để triển khai chính sách context capture/restore tập trung cho các task đi qua bean executor đó.

### 4.1. Vì sao phải chụp lúc submit, không phải lúc run?

Nếu chỉ gọi `MDC.get("correlationId")` ở trong worker, bạn đang đọc **context của worker**, vốn không có request ID hoặc chứa dữ liệu cũ. Snapshot phải lấy từ nơi còn context đúng: **thread đang giao task**.

Ví dụ sai:

```java
executor.execute(() -> {
    String id = MDC.get("correlationId"); // Có thể null hoặc stale
    log.info("job {}", id);
});
```

Ví dụ đúng về mặt nguyên lý:

```java
String capturedId = MDC.get("correlationId");
executor.execute(() -> {
    String previous = MDC.get("correlationId");
    try {
        if (capturedId == null) MDC.remove("correlationId");
        else MDC.put("correlationId", capturedId);
        doWork();
    } finally {
        if (previous == null) MDC.remove("correlationId");
        else MDC.put("correlationId", previous);
    }
});
```

Hai đoạn là **fragment**, cần executor/logger/`doWork` và imports thích hợp. Trong dự án có nhiều task, nên **không chép thủ công** đoạn wrapper này vào từng call site; một `TaskDecorator` có kiểm tra rõ ràng dễ duy trì hơn.

### 4.2. Tại sao restore thay vì chỉ clear?

Nếu worker trước khi task bắt đầu đã có một context hợp lệ do một wrapper bên ngoài đặt, gọi `MDC.clear()` sau task có thể xóa mất context của scope bao ngoài. **Restoring previous** xử lý cả hai trường hợp:

- Trước task không có MDC → dọn về rỗng.
- Trước task có MDC → khôi phục đúng context đó.

Điều này đặc biệt hữu ích khi có **decorator lồng nhau**, instrumentation hoặc một executor wrapper khác. Không được để một task ghi dữ liệu context rồi quên cleanup khi có exception.

## 5. Java 17 runnable: chứng minh ThreadLocal không tự truyền và cần cleanup

Ví dụ thuần JDK không phụ thuộc Spring/SLF4J. Nó dùng `ThreadLocal<String>` để mô phỏng một trường `correlationId` trong MDC của Logback. Một single-thread executor cho thấy giá trị ở caller **không tự xuất hiện** trên worker. Sau đó một wrapper **capture → install → restore** truyền đúng ID và làm sạch sau khi task kết thúc.

Lưu chương trình vào **ContextBoundaryDemo.java**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ContextBoundaryDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    private static String current() {
        String id = REQUEST_ID.get();
        return id == null ? "absent" : id;
    }

    private static void assign(String value) {
        if (value == null) {
            REQUEST_ID.remove();
        } else {
            REQUEST_ID.set(value);
        }
    }

    private static Runnable capture(Runnable action) {
        // Dòng này chạy ở thread SUBMIT, trước khi có worker.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                assign(captured);
                action.run();
            } finally {
                assign(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pooled-worker"));

        try {
            REQUEST_ID.set("req-123");

            // Không truyền: worker không thấy ThreadLocal của caller.
            pool.submit(() ->
                    System.out.println("without: " + current())).get();

            // Wrapper chụp req-123 khi submit, rồi đặt vào worker.
            pool.submit(capture(() ->
                    System.out.println("with: " + current()))).get();

            // Worker không bị rò rỉ req-123 sang task kế tiếp.
            pool.submit(() ->
                    System.out.println("after: " + current())).get();

            System.out.println("caller: " + current());
        } finally {
            REQUEST_ID.remove();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac ContextBoundaryDemo.java
java ContextBoundaryDemo
```

**Stdout xác định của chương trình:**

```text
without: absent
with: req-123
after: absent
caller: req-123
```

Phân tích:

1. `REQUEST_ID.set("req-123")` chỉ đặt giá trị trên main thread. `ThreadLocal` thường không thừa kế giá trị sang worker, nên dòng đầu là `without: absent`.
2. `capture(...)` chạy **trên main thread lúc tạo wrapper**, giữ snapshot `req-123` trước khi giao cho pool.
3. Wrapper đặt ID trong worker, chạy action, rồi `finally` **restore `previous`**. Vì worker chưa có giá trị nên restore bằng `remove()`.
4. Task kế tiếp dùng lại single-thread pool và thấy `after: absent`, chứng minh wrapper không để lại context.
5. Main thread vẫn thấy `caller: req-123` cho tới khi `finally` dọn giá trị của main.
6. Mỗi lệnh `Future.get()` đợi task trước hoàn thành, vì vậy thứ tự các dòng in không phụ thuộc may rủi scheduling. Không cần `Thread.sleep` để giả định lúc nào worker chạy xong.

**Giới hạn:** demo minh họa `ThreadLocal`, **không phải implementation của SLF4J MDC**. Trong Spring/Logback, thay vì một `String`, thường chụp cả `Map<String,String>` qua `MDC.getCopyOfContextMap()`. Cần xử lý snapshot `null` (không có map) khác với map có dữ liệu và restore đúng context của worker.

## 6. Spring TaskDecorator để sao chép và khôi phục MDC

Một `TaskDecorator` triển khai cơ chế snapshot một cách tập trung:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        // Capture trên thread submit, không phải trong worker.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // Có thể có context hợp lệ của scope ngoài.
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Class trên có thể được biên dịch trong dự án có **Spring Core và SLF4J MDC backend**. Nó cũng được dùng trong ứng dụng hoàn chỉnh ở phần sau (bài Spring Boot dùng class cùng ý tưởng).

### Vì sao các chi tiết này quan trọng?

- `MDC.getCopyOfContextMap()` lấy **snapshot**, tránh truyền một map dùng chung để hai thread sửa cùng một object.
- `decorate(...)` được gọi khi executor nhận `Runnable` để tạo wrapper; trong trường hợp này nó capture MDC trên luồng submit. Thời điểm capture phải nằm **trước** khi request filter dọn context.
- Khi worker chạy, code chụp `previous` trước khi ghi đè. Sau task, `finally` restore nguyên trạng. Nếu task ném lỗi, `finally` vẫn chạy.
- `captured == null` nghĩa không có map; ở worker cần **clear** để không log bằng ID cũ.
- `MDC.setContextMap(...)` dùng một bản đồ string keys/values; không nên đưa object nghiệp vụ mutable hay secret vào MDC.

Với task cực ngắn và tần suất rất cao, capture/restore context có overhead. Cần đo trong trường hợp đặc biệt, nhưng **không bỏ cleanup để “tối ưu”**. Có thể chỉ propagate những key cần thiết thay vì toàn bộ map khi yêu cầu bảo mật và hiệu năng chặt chẽ.

### 6.1. Không capture một lần khi tạo bean executor

Một lỗi tinh vi:

```java
Map<String, String> startupMdc = MDC.getCopyOfContextMap();

executor.setTaskDecorator(task -> () -> {
    MDC.setContextMap(startupMdc);
    task.run();
});
```

Đây là **phản ví dụ, không dùng trong production**; `setContextMap` còn không chấp nhận `null` an toàn trong mọi backend. `startupMdc` được chụp **một lần lúc startup**, thường trống, chứ không phải tại mỗi task submission. Nó cũng thiếu restore trong `finally`.

**Đúng:** đặt lệnh `MDC.getCopyOfContextMap()` **trong `TaskDecorator.decorate(...)`**, rồi restore previous trong wrapper. Không lưu ID của một request vào field singleton của executor hoặc service.

### 6.2. TaskDecorator chỉ bao trùm task qua đúng executor

Nếu một method dùng `@Async("workExecutor")`, decorator của `workExecutor` có thể áp dụng. Nhưng nếu code gọi:

```java
CompletableFuture.supplyAsync(() -> compute());
```

mà **không truyền executor**, JDK thường dùng `ForkJoinPool.commonPool()` (với quy tắc fallback riêng). Pool đó **không tự đi qua `TaskDecorator` của Spring `workExecutor`**.

Nếu cần continuation chạy qua executor có propagation:

```java
CompletableFuture.supplyAsync(() -> compute(), workExecutor);
```

Đây là fragment, cần `compute` và `workExecutor` được khai báo. Đồng thời, `whenComplete`/`thenApply` **không có hậu tố Async** có thể chạy trên thread hoàn tất hoặc registration thread tùy timing. Không nên dựa vào việc “đã từng đi qua một executor” để khẳng định mọi callback sau này sẽ có MDC. Khi cần bảo đảm rõ ràng, truyền correlation ID như dữ liệu, hoặc dùng context-aware executor cho **từng điểm scheduling** quan trọng.

## 7. Spring Boot 3.x runnable: filter + executor + @Async + MDC

Ví dụ sau minh họa end-to-end trong **Spring Boot 3.x / Spring Framework 6.x / Java 17+**, với dependency `spring-boot-starter-web` (bao gồm Spring MVC và logging thông dụng). Nó có bốn thành phần:

1. `OncePerRequestFilter` lấy hoặc tạo `X-Correlation-ID`, validate và đặt vào MDC trên request thread.
2. `ThreadPoolTaskExecutor` có `TaskDecorator`, capture/restore MDC cho worker.
3. `WorkService` chạy method `@Async("workExecutor")`; log trên worker và trả lại mã thực sự nhìn thấy.
4. `WorkController` gọi bean service khác qua proxy, dùng correlation ID từ request để kiểm tra kết quả.

Đặt **toàn bộ mã dưới đây** vào **src/main/java/com/example/demo/CorrelationApplication.java**:

```java
package com.example.demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
@EnableAsync
public class CorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }

    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("work-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.setTaskDecorator(new MdcTaskDecorator());
        return pool; // Spring quản lý initialize và shutdown của bean
    }
}

final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable runnable) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) MDC.clear();
                else MDC.setContextMap(captured);
                runnable.run();
            } finally {
                if (previous == null) MDC.clear();
                else MDC.setContextMap(previous);
            }
        };
    }
}

@Component
class CorrelationFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String KEY = "correlationId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String incoming = request.getHeader(HEADER);

        // Chỉ nhận ID ngắn, không có ký tự điều khiển/CRLF.
        String correlationId =
                incoming != null
                && incoming.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
                ? incoming
                : UUID.randomUUID().toString();

        String previous = MDC.get(KEY);
        try {
            MDC.put(KEY, correlationId);
            response.setHeader(HEADER, correlationId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) MDC.remove(KEY);
            else MDC.put(KEY, previous);
        }
    }
}

record WorkResult(
        String jobId,
        String requestCorrelationId,
        String workerCorrelationId) {}

@Service
class WorkService {
    private static final Logger log =
            LoggerFactory.getLogger(WorkService.class);

    @Async("workExecutor")
    public CompletableFuture<WorkResult> process(
            String jobId, String requestCorrelationId) {
        String workerCorrelationId = MDC.get("correlationId");
        log.info("Processing job {}", jobId);

        WorkResult result = new WorkResult(
                jobId, requestCorrelationId, workerCorrelationId);
        return CompletableFuture.completedFuture(result);
    }
}

@RestController
class WorkController {
    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);
    private final WorkService service;

    WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping("/work/{id}")
    public CompletableFuture<WorkResult> process(
            @PathVariable String id) {
        String correlationId = MDC.get("correlationId");
        log.info("Accepted work {}", id);
        return service.process(id, correlationId);
    }
}
```

**Lưu ý về cấu trúc:** tất cả các class package-private đặt chung một file với public class `CorrelationApplication` là hợp lệ trong Java. Dự án cần Spring Boot 3.x, logging backend mặc định hoặc backend tương đương và HTTP stack Jakarta Servlet. Không thể dùng `javac CorrelationApplication.java` khi không có dependencies Spring.

Ví dụ chạy trong project có Gradle wrapper:

```bash
./gradlew bootRun
curl -i -H "X-Correlation-ID: req-demo-01" \
  http://localhost:8080/work/J7
```

Trên Windows PowerShell có thể dùng `gradlew.bat bootRun` rồi chạy riêng lệnh `curl.exe`; dấu `\` nối dòng trong ví dụ shell phía trên dành cho bash, không phải cú pháp tiếp dòng của PowerShell.

Khi request được nhận và worker hoàn thành, **phần JSON kết quả** có giá trị tương đương:

```json
{
  "jobId": "J7",
  "requestCorrelationId": "req-demo-01",
  "workerCorrelationId": "req-demo-01"
}
```

**Vì sao có thể quan sát điều đó?**

1. Filter nhận một mã hợp lệ và đặt `MDC["correlationId"]` trên servlet thread.
2. Controller đọc mã trong MDC và truyền **tường minh** thành tham số `requestCorrelationId` vào service.
3. Controller gọi bean `WorkService` khác, lời gọi `@Async` được Spring proxy intercept và giao task cho `workExecutor`.
4. `TaskDecorator.decorate(...)` capture snapshot MDC **tại lúc task được submit**.
5. Worker chạy wrapper và cài MDC trước khi gọi method thực, nên `MDC.get("correlationId")` trong `WorkService` là `req-demo-01`.
6. Sau khi task kết thúc, wrapper restore MDC trước đó của worker, tránh rò rỉ sang task tiếp theo.
7. Filter restore giá trị cũ của servlet thread sau khi rời scope xử lý request.

Dù method `WorkService.process` trả `CompletableFuture.completedFuture(...)` trong worker, **Spring MVC vẫn phản hồi khi `CompletableFuture` trả về từ controller đã hoàn tất**. Đây là response của endpoint demo, không phải giao thức job `202 Accepted`. JSON được tạo từ **giá trị truyền tường minh và giá trị worker quan sát**; không phụ thuộc việc callback serialization của Spring MVC chạy ở thread nào.

### 7.1. Hiện correlation ID trong log với Logback

MDC chỉ hữu ích khi layout log **đọc key tương ứng**. Trong Spring Boot dùng Logback, có thể cấu hình mẫu console log, ví dụ trong `src/main/resources/application.properties`:

```properties
logging.pattern.console=%d{HH:mm:ss.SSS} %-5level [%thread] [corr=%X{correlationId}] %logger{36} - %msg%n
```

Đây là cấu hình minh họa dùng Logback pattern `%X{correlationId}`. Log thực tế có timestamp/tên thread khác nhau, nhưng khi filter và decorator hoạt động đúng, request và worker có thể cùng có đoạn:

```text
[corr=req-demo-01] ... Accepted work J7
[corr=req-demo-01] ... Processing job J7
```

Không dự đoán tên thread hoặc thứ tự tuyệt đối của mọi log trong xử lý bất đồng bộ. Nếu dùng JSON structured logging, thêm trường `correlationId` từ MDC theo cấu hình encoder, **đừng ghi ID bằng cách nối chuỗi thủ công ở mọi log statement** nếu backend đã hỗ trợ field.

### 7.2. Nếu client không gửi header?

Filter dùng `UUID.randomUUID().toString()` tạo mã mới, đặt vào MDC và trả trong response header `X-Correlation-ID`. Client có thể lưu mã đó để cung cấp khi báo lỗi. Giá trị cụ thể thay đổi mỗi request và **không thể coi là stdout cố định**.

Nếu client gửi giá trị chứa dấu xuống dòng, quá dài hoặc ký tự ngoài regex, filter thay bằng UUID do server tạo. Đây là một biện pháp đơn giản tránh log injection và header abuse; trong production còn có thể muốn giới hạn theo chính sách gateway và chuẩn ID của tổ chức.

### 7.3. Cần hiểu giới hạn servlet async dispatch

`OncePerRequestFilter` mặc định có cách chọn những dispatcher types cần lọc; quá trình Spring MVC trả `CompletableFuture` có thể bao gồm **async dispatch** sau khi filter scope ban đầu đã kết thúc. Demo chỉ cần filter đặt MDC **lúc ban đầu controller submit task**, nên `TaskDecorator` capture kịp.

Không suy ra MDC sẽ tự có ở **mọi filter invocation, error dispatch, log của framework sau response hay async dispatch thread**. Nếu cần correlation ID tại tất cả các giai đoạn servlet async, phải thiết kế propagation/filtering theo dispatcher type/lifecycle phù hợp, hoặc dùng observability/context propagation integration hỗ trợ.

## 8. Cơ chế khởi tạo và chọn executor trong Spring

Trong mẫu trên:

```java
@Bean("workExecutor")
ThreadPoolTaskExecutor workExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setTaskDecorator(new MdcTaskDecorator());
    return executor;
}
```

Đây là **fragment rút gọn**; trong ví dụ đầy đủ còn có sizing và rejection policy. `ThreadPoolTaskExecutor` là Spring bean, container có thể quản lý initialization và shutdown theo lifecycle. `@Async("workExecutor")` chọn chính executor có decorator đó.

Các trường hợp MDC không được truyền:

- Một method `@Async` chọn bean executor **khác** không có decorator.
- Code `CompletableFuture.supplyAsync(fn)` không truyền executor và chạy trên default JDK facility.
- Code tự gọi `this.asyncMethod()` bên trong cùng bean trong proxy mode nên **không qua Spring async proxy**.
- Một thư viện bên ngoài tự tạo thread và không dùng executor được trang bị propagation.
- A callback `thenApply(...)` non-async thực thi inline trên thread không có MDC theo thời điểm hoàn tất.
- Scheduler/message listener khởi chạy task khi chưa tạo correlation ID cho job/message gốc.

Cần hiểu **đường gọi thực tế** và **executor thực tế**. Không được gán trách nhiệm cho `TaskDecorator` nếu task không hề đi qua executor đó.

### 8.1. Rejection xảy ra lúc nào?

`ThreadPoolTaskExecutor` có giới hạn pool và queue. Nếu dùng `AbortPolicy` và executor quá tải hoặc đã shutdown, việc submit có thể phát `TaskRejectedException`. Task bị từ chối **không chạy worker wrapper**, nhưng request thread đang submit vẫn có MDC, nên log tại điểm catch có thể có correlation ID:

```java
try {
    workExecutor.execute(task);
} catch (TaskRejectedException ex) {
    log.warn("Executor rejected a task", ex);
    // Phản hồi 503/429 hoặc lưu job bền vững tùy hợp đồng.
}
```

Đây là fragment, giả định `log`, `task` và `workExecutor` tồn tại. Không dùng một handler discard im lặng rồi hứa rằng mọi task đã thực thi. Việc trace rejection quan trọng vì log trên worker sẽ **không tồn tại** cho task chưa được nhận.

### 8.2. TaskDecorator và exception của Future

Spring lưu ý `TaskDecorator` có thể nhận một wrapper `Runnable` thay vì user-supplied task nguyên bản; với lời gọi `submit`, wrapper có thể là một `FutureTask` che exception. Vì vậy đừng coi `TaskDecorator` là nơi đáng tin để **bắt mọi exception nghiệp vụ** bằng `catch (Throwable)` rồi ghi log. Để quan sát lỗi, dùng Future/CompletableFuture callback, `@Async` exception handler phù hợp hoặc error handler ở tầng công việc.

**Trách nhiệm của decorator là thiết lập/khôi phục context**, không phải biến nó thành nơi xử lý mọi kết quả nghiệp vụ.

## 9. Truyền correlation ID qua CompletableFuture chain

Ví dụ:

```java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> fetchData(), workExecutor)
                .thenApply(this::transform);
```

`supplyAsync(..., workExecutor)` được scheduling qua executor có decorator, nhưng `thenApply` **không có hậu tố Async** có thể chạy trên completion thread hoặc registration thread tùy timing. Khi callback cần logging context, phải hiểu nơi thực thi:

- Nếu upstream chưa hoàn tất, callback non-async có thể chạy trước khi worker wrapper của upstream restore MDC, nên quan sát được context trong worker.
- Nếu upstream đã hoàn tất trước khi callback đăng ký, nó có thể chạy inline trên caller thread; context phụ thuộc caller đó.
- Nếu stage được hoàn tất từ một thread khác hoặc context đã được restore, callback có thể không thấy MDC mong đợi.
- Dùng `thenApplyAsync(fn, workExecutor)` khi thật sự cần dispatch qua executor đã trang bị context propagation. **Tuy nhiên capture diễn ra ở thread submit continuation**, thread đó phải có context cần truyền.

### Không cho rằng propagation ở upstream sẽ “lây” tự động mãi mãi

```java
CompletableFuture<String> next =
        upstream.thenApplyAsync(this::work, workExecutor);
```

Đây là fragment. Nếu `upstream` chưa hoàn tất, hành động scheduling continuation có thể xảy ra trên thread hoàn tất upstream. `TaskDecorator` chụp **MDC đang có trên thread scheduling đó**, không nhất thiết là MDC của HTTP request ban đầu. Nếu upstream được hoàn tất từ một foreign executor không mang context, việc chỉ truyền `workExecutor` chưa chắc làm ID “hồi sinh”.

Khi yêu cầu correlation nhất quán qua nhiều stage, có những lựa chọn rõ ràng:

1. Truyền **correlation ID như dữ liệu**: `record Context(jobId, correlationId)` đi cùng payload, không phụ thuộc thread.
2. Bọc callback với snapshot context **tại thời điểm còn biết ID đúng**, rồi restore khi chạy.
3. Dùng context-aware executor hoặc cơ chế context propagation có hỗ trợ chính thức, kiểm tra mọi ranh giới asynchronous.
4. Tránh dựa vào callback timing/thread identity vì `CompletableFuture` không cam kết non-async stage chạy trên một thread cố định.

### 9.1. Truyền như dữ liệu khi job sống lâu hơn HTTP request

Một cách ít phụ thuộc MDC là định nghĩa:

```java
record JobContext(
        String jobId,
        String correlationId,
        String traceId) {}

record WorkItem(JobContext context, String payload) {}
```

Đây là **fragment record Java 17**. Worker nhận `WorkItem`, đưa `context.correlationId()` vào MDC cho **scope xử lý của job**, rồi cleanup. Nếu job được lưu trong database/broker, metadata có thể được lưu/publish cùng job và được phục hồi sau restart.

Điểm lợi là một job dài vài phút không cần giữ HTTP request object hoặc servlet thread. **Không lưu toàn bộ security context, access token hoặc session vào job chỉ để có một correlation ID.**

## 10. Ngoài JVM: propagate correlation header qua dịch vụ khác

`MDC.put(...)` chỉ thay đổi logging context của thread hiện tại. Nó **không tự thêm header** vào outgoing HTTP request và **không tự đi vào Kafka/RabbitMQ message**.

Ví dụ Java 17 standard `HttpClient`:

```java
String correlationId = MDC.get("correlationId");

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://service.example.test/data"))
        .header("X-Correlation-ID",
                correlationId == null ? "unknown" : correlationId)
        .GET()
        .build();
```

Đây là **fragment**, cần `java.net.URI`, `java.net.http.HttpRequest` và SLF4J MDC. Dùng `"unknown"` chỉ để giải thích; hệ thống thật nên **tạo ID hợp lệ ở ranh giới ingress hoặc job** thay vì dùng mã chung gây nhập log nhiều request.

Tốt hơn, tích hợp một outbound interceptor phù hợp với client đang sử dụng, ví dụ Spring `RestClient`/`WebClient`/`RestTemplate` hoặc HTTP client do thư viện cung cấp, và dùng một **CorrelationContext** đã được xác định đúng theo request/job. Với message broker, đặt correlation ID trong **headers/message metadata** khi publish và đọc nó khi consume.

```text
Service A:
  MDC[corr=req-8f2]  --> outgoing HTTP header / message header
                                       |
                                       v
Service B:
  ingress filter / listener reads corr=req-8f2
  validates value and chooses trust policy
  sets MDC for local scope
  runs work, propagates onward if needed
  finally restores/clears MDC
```

**Quan trọng:** service B không nên xem correlation ID như một identity đã xác thực; header có thể do client bất kỳ tạo. Trace/span context có quy tắc propagation riêng nếu dùng OpenTelemetry/Micrometer Tracing. Correlation ID dùng để nối log, không thay thế một trace có parent/child span chuẩn.

### 10.1. Với Kafka/RabbitMQ và scheduled jobs

- **Producer:** lấy mã từ request/job context và ghi vào message headers; không giả định MDC tự được serialize.
- **Consumer:** validate/normalize mã từ message, đặt vào MDC trong scope xử lý một message, rồi **restore/clear trong finally** để không rò sang message kế.
- **Scheduled job:** không có HTTP header; tạo một correlation ID cho mỗi lần kích hoạt/job logic và ghi vào metadata trước khi submit. Nếu một lượt schedule gửi hàng trăm task, xác định có cùng correlation ID cha hay thêm child/job ID.
- **Retry/redelivery:** nên giữ correlation ID ổn định cho cùng job logic nếu mục tiêu là truy vết cùng workflow, đồng thời ghi thêm `attempt` để phân biệt lần thử. Không dùng correlation ID làm idempotency key duy nhất.
- **Distributed trace:** nếu broker/client instrumentation hỗ trợ trace context, dùng propagation chuẩn thay vì tự tạo trace/span IDs bằng chuỗi ngẫu nhiên và cho rằng đã có distributed tracing.

## 11. Micrometer Context Propagation, tracing và Reactor Context

Trong hệ sinh thái Spring hiện đại, một hệ thống có thể dùng:

- **Micrometer Observation/Tracing** để tạo span và trace, log correlation với `traceId`/`spanId`.
- **Micrometer Context Propagation** để capture/restore một số context qua các ranh giới thread/reactive thông qua các accessor đã đăng ký.
- **`ContextPropagatingTaskDecorator`** của Spring để dùng cơ chế context snapshot khi đủ dependency và cấu hình thích hợp.
- **Reactor Context** để lưu dữ liệu theo chuỗi reactive thay vì dựa vào `ThreadLocal` của một event-loop worker.

Điều quan trọng không phải chọn một tên class thần kỳ, mà là hiểu **context nào đang được quản lý** và **điểm capture/restore nào được áp dụng**. Không mặc định bật Micrometer tracing sẽ copy mọi MDC custom key tự tạo hoặc toàn bộ security context qua mọi `CompletableFuture`/raw thread.

### 11.1. Khi nào cần context propagation framework?

Một `MdcTaskDecorator` đơn giản có thể đủ cho ứng dụng Spring MVC với một vài executor rõ ràng. Khi luồng xử lý đi qua nhiều loại boundary — servlet, async task, reactor operator, broker listener, tracing span — giải pháp framework có accessor/observation chuẩn dễ duy trì hơn, miễn là ứng dụng kiểm tra khả năng propagation trong phiên bản thư viện đang dùng.

**Không trộn nhầm:**

- `traceId` và `spanId` do tracing system quản lý; không tự ý thay thế bằng `correlationId`.
- `MDC` là ngữ cảnh hiển thị vào log, không phải context propagation protocol.
- `SecurityContextHolder` có chính sách khác; không nên sao chép authentication vào MDC.
- Reactor operator có thể chuyển thread theo scheduler; `MDC.get(...)` không tự phản ánh Reactor Context ở mọi callback.
- Logging có thể chạy ở thread khác khi dùng async appender; kiểm tra cơ chế MDC capture của logging backend và test end-to-end.

Đọc tài liệu theo **phiên bản Spring Framework/Spring Boot thực tế** trước khi ghép các giải pháp propagation với nhau để tránh double wrapping, mất context hoặc overhead không cần thiết.

## 12. Bảo mật và kiểm soát dữ liệu trong logging context

Correlation ID có vẻ vô hại nhưng vẫn là dữ liệu do client có thể kiểm soát. Một số nguyên tắc an toàn:

### 12.1. Validate header, không tin chuỗi tùy ý

Một header chứa `\r`/`\n`, ký tự điều khiển hoặc chuỗi dài hàng megabyte có thể gây log injection, tăng chi phí lưu log hoặc làm sai cấu trúc JSON. Hãy giới hạn:

- Độ dài (ví dụ tối đa 64 ký tự).
- Bộ ký tự cho phép (ví dụ chữ, số, `-`, `_`, dấu chấm).
- Số lượng header lặp lại.
- Chính sách khi không hợp lệ: tự tạo ID mới hoặc từ chối request theo yêu cầu API.

Đừng dùng request body, access token hoặc tên người dùng làm correlation ID.

### 12.2. MDC chỉ chứa thông tin cần truy vết

Không đặt password, authorization bearer token, cookie, dữ liệu thẻ thanh toán, nội dung email hay dữ liệu cá nhân nhạy cảm vào MDC chỉ để dễ debug. Context được copy sang worker/structured logger và có thể được gửi tới hệ thống lưu log tập trung.

Chỉ nên chứa các giá trị có phạm vi và retention rõ: `correlationId`, `jobId`, `component` hoặc request path đã được chuẩn hóa nếu hợp lệ. Nếu cần thông tin principal để phân quyền, dùng cơ chế bảo mật phù hợp và đánh giá propagation riêng.

### 12.3. Cross-tenant và ID collision

Nếu nhận ID trực tiếp từ internet, hai người dùng có thể cùng gửi `X-Correlation-ID=abc` để cố ý trộn log. Có thể:

- Tạo ID tin cậy **tại gateway** và không để client tùy ý ghi đè.
- Dùng ID server-generated kết hợp với external client-provided ID ở **trường riêng biệt**, có nhãn nguồn tin cậy.
- Không truy vấn dữ liệu nhạy cảm chỉ bằng một correlation ID.
- Dùng tenant/authorization policy chính thức trong API status; correlation ID không cho phép truy cập log hoặc job của người khác.

Nếu một hệ thống cần distributed tracing, tuân thủ chính sách sampling/trust/propagation tại ingress chứ không tùy tiện tin mọi trace context bên ngoài.

## 13. Cleanup, nested scopes và khả năng rò rỉ ngữ cảnh

### 13.1. Worker thread là tài nguyên được tái sử dụng

Giả sử pool có một worker:

```text
Task A: MDC.put("correlationId", "req-A")
        run...
        // Quên remove

Task B: không đặt MDC
        log.info("Processing")
        => log của B có thể mang corr=req-A (SAI)
```

Một lỗi chỉ xuất hiện dưới tải thực có thể khó tái hiện, vì vài lần test tạo thread mới không cho thấy việc tái sử dụng. Luôn có `finally`, kể cả khi task timeout, cancel hợp tác hoặc ném exception.

### 13.2. Restore toàn bộ map khi có nested contexts

Giả sử worker đang có context `{traceId=abc, component=outer}` từ một wrapper. Một decorator chỉ làm `MDC.remove("correlationId")` có thể giữ lại các key mới do task tự thêm; một decorator chỉ `MDC.clear()` có thể xóa cả `traceId` của scope ngoài.

Cách snapshot đầy đủ:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.setContextMap(captured);
    runnable.run();
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
```

Đây là **fragment**, với giả thiết `captured` không null. Nếu null, cần `MDC.clear()` ở đầu như class `MdcTaskDecorator` hoàn chỉnh. Việc restore map giải quyết các key phát sinh trong task một cách tập trung.

### 13.3. Cleanup filter khi controller trả CompletableFuture

Một Spring MVC controller trả `CompletableFuture` có thể hoàn tất HTTP response sau khi servlet thread ban đầu đã thoát khỏi filter. Filter `finally` vẫn nên restore MDC trên thread của nó. Đừng giữ MDC mãi “để MVC còn log”; làm vậy sẽ rò rỉ ID sang request tiếp theo chạy trên cùng servlet thread.

Đối với log phát sinh ở MVC async/error dispatch sau đó, dùng cơ chế context propagation phù hợp cho dispatch mới hoặc framework observability. **MDC không phải kho trạng thái request bền vững xuyên mọi dispatch.**

## 14. Xử lý lỗi, cancellation và shutdown không làm mất dấu vết

Một request có thể gửi task vào executor rồi kết thúc trước khi worker chạy. Nếu client timeout, **task có thể vẫn tiếp tục**. Mã liên kết nên được giữ trong job payload hoặc context snapshot cho task đã được nhận; không phụ thuộc HTTP thread còn tồn tại.

Các tình huống cần kiểm thử:

| Tình huống | Điều cần giữ đúng |
| --- | --- |
| Task ném exception | Log ở worker có mã đúng; `finally` restore MDC |
| Task bị từ chối trước khi chạy | Log ở submitter có mã đúng; không gán trạng thái “đã chạy” |
| Task chờ queue lâu | Context được capture lúc submit, không phải lúc worker lấy task |
| Client request timeout | Job có thể tiếp tục; correlation/job ID lưu riêng nếu cần theo dõi |
| CompletableFuture callback ngoài executor | Không mặc định có MDC của request |
| Worker được tái sử dụng | Không được giữ lại correlation ID của task trước |
| App shutdown / task interrupt | Cleanup MDC dù thoát sớm trong nhánh lỗi |
| Retry cùng job | Giữ logical correlation ID, thêm attempt ID riêng |
| Cross-service HTTP | Đưa correlation ID vào header rõ ràng; receiver validate lại |
| Broker consumer | Đọc message headers, đặt MDC trong scope message, restore sau xử lý |

**Log của worker hoàn tất muộn** có thể xuất hiện sau HTTP 202/timeout; đây không phải vấn đề nếu hệ thống có job ID/correlation ID và state machine rõ ràng. Không diễn giải “client đã ngừng chờ” thành “worker chắc chắn không chạy nữa”.

### 14.1. @Async void và CompletableFuture exception

`@Async void` không trả Future cho caller; exception cần được quan sát qua `AsyncUncaughtExceptionHandler`/logging, và handler có thể chạy theo execution lifecycle riêng. Với method trả `CompletableFuture<T>`, caller nên gắn `whenComplete` hoặc `handle` phù hợp để ghi nhận kết quả.

`whenComplete` **không có hậu tố Async** có thể chạy trên thread hoàn tất future hoặc thread đăng ký, tùy timing. Nếu callback logging cần ID chắc chắn, hãy **mang correlation ID vào closure bằng một biến immutable** hoặc định tuyến callback qua context-aware executor; không tin `MDC.get` lúc callback luôn giống HTTP request.

Một giải pháp tường minh:

```java
String requestCorrelationId = MDC.get("correlationId");

future.whenComplete((result, error) -> {
    // Dùng requestCorrelationId làm dữ liệu truy vết,
    // không suy luận MDC của thread callback luôn có ID.
    if (error != null) {
        log.warn("Job failed, correlationId={}",
                requestCorrelationId, error);
    }
});
```

Đây là fragment; cần `future` và `log`. Để callback log theo MDC layout, vẫn cần đặt/restore MDC trong callback hoặc sử dụng context-aware scheduling; việc ghi ID tường minh vào message ở đây chỉ tránh suy luận sai về thread.

## 15. Kiểm thử propagation đúng cách

Chỉ nhìn hai dòng log có cùng ID trong một lần chạy **chưa đủ**. Cần kiểm thử cả trường hợp có nhiều request, lỗi và tái sử dụng thread.

### 15.1. JDK unit test ý tưởng

Với `ContextBoundaryDemo.java`, kiểm tra ba invariant:

1. Không bọc: worker không thấy request ID của caller.
2. Có wrapper: worker thấy đúng snapshot từ caller.
3. Sau wrapper: worker không giữ snapshot của request trước.

Mở rộng test bằng cách cố ý ném `RuntimeException` trong action được decorate, bắt qua `Future.get()` rồi submit task tiếp để kiểm tra MDC đã được restore nhờ `finally`.

### 15.2. Spring integration test

Với ứng dụng `CorrelationApplication`:

- Gửi request mang `X-Correlation-ID: req-A`, kiểm tra response body `requestCorrelationId=workerCorrelationId=req-A`.
- Gửi request mang `X-Correlation-ID: req-B` ngay sau đó, xác minh worker không mang `req-A`.
- Gửi request không có header, kiểm tra response header chứa ID do server tạo và body dùng cùng ID đó.
- Gửi header quá dài/ký tự không hợp lệ, kiểm tra filter không copy thẳng vào MDC/response.
- Cố tình làm `WorkService` ném exception; xác minh task sau vẫn có MDC đúng và không leak.
- Kiểm thử `@Async` gọi **qua bean khác** và đúng `workExecutor`; self-invocation không được dùng làm test propagation.
- Dùng pool core=1 trong test để tạo khả năng tái sử dụng cùng worker và giảm biến số lịch trình.
- Kiểm thử callback `CompletableFuture.thenApply` sau upstream hoàn tất để thấy registration thread có thể tham gia, không giả định MDC ở tất cả callback.

Với logging thực tế có thể dùng appender capture hoặc test instrumentation để kiểm tra MDC tại thời điểm log event được tạo, thay vì chỉ so sánh chuỗi format output bị tác động bởi appender async.

### 15.3. Production monitoring

Nên theo dõi cả chất lượng propagation:

- Tỷ lệ log/job thiếu `correlationId` ở điểm cần có.
- Các job/HTTP request có correlation ID bất thường, quá dài hoặc trùng lặp.
- Task ở worker có ID khác với metadata trong payload.
- Execution time, queue wait, rejection count và exception theo executor.
- Số lượng request/job kết thúc nhưng worker vẫn tiếp tục — có thể hợp lệ nhưng cần liên kết log.
- Tương quan giữa `correlationId`, `jobId`, `traceId`/`spanId` trong structured logs.

Không xuất toàn bộ MDC map hoặc payload người dùng vào metric labels: cardinality cực cao và rò rỉ dữ liệu. **Correlation ID thường có cardinality lớn**, phù hợp với log và trace lookup hơn là làm label chính cho mọi metric time series.

## 16. Các lỗi phổ biến

**Lỗi 1 — Tưởng MDC tự đi theo @Async.** ThreadPoolTaskExecutor dùng worker riêng; MDC thường thread-local và cần propagation.

**Lỗi 2 — Đọc MDC trong worker rồi nghĩ đó là ID của request submit.** Worker có thể chưa có context hoặc giữ ID cũ. Capture từ submitter.

**Lỗi 3 — Capture MDC một lần khi khởi tạo singleton executor.** Snapshot startup không phải snapshot từng task.

**Lỗi 4 — Đặt MDC ở worker nhưng không có finally.** Exception hoặc cancel hợp tác có thể làm rò rỉ context sang request khác.

**Lỗi 5 — Chỉ clear mà không restore previous.** Có thể phá scope của instrumentation/decorator bao ngoài.

**Lỗi 6 — Dùng InheritableThreadLocal để thay TaskDecorator trong pool tái sử dụng.** Giá trị chỉ liên quan thời điểm tạo thread, không phù hợp với mỗi lần submit.

**Lỗi 7 — Truyền toàn bộ MDC vô điều kiện.** Có thể sao chép PII/token và quá nhiều key không cần thiết; chọn phạm vi tối thiểu.

**Lỗi 8 — Tin rằng CompletablFuture.supplyAsync(...) không truyền executor dùng Spring pool.** Mặc định JDK async facility thường là commonPool, không đi qua TaskDecorator Spring.

**Lỗi 9 — Tin callback non-Async luôn chạy trên worker mang context.** Callback có thể chạy inline trên registration thread khi stage đã hoàn tất hoặc theo completion policy khác.

**Lỗi 10 — Tưởng @Async("workExecutor") áp dụng cho this.method() trong cùng bean.** Self-invocation ở proxy mode bỏ qua interceptor.

**Lỗi 11 — Chỉ đặt MDC mà không cấu hình log pattern/structured encoder.** Correlation ID không tự xuất hiện trong log output nếu layout không đọc field.

**Lỗi 12 — Dùng correlation ID làm authentication hoặc idempotency key độc lập.** ID do client có thể tự đặt và không chứng minh quyền hay tính duy nhất của tác động nghiệp vụ.

**Lỗi 13 — Không propagate outgoing HTTP/message headers.** MDC của Service A không tự xuất hiện trong Service B.

**Lỗi 14 — Tưởng custom correlation ID là trace context chuẩn.** W3C trace/span có ngữ nghĩa riêng; dùng tooling tracing đúng khi cần distributed trace.

**Lỗi 15 — Bọc task nhưng dùng trực tiếp một executor khác ở nhánh lỗi hoặc retry.** Không phải task nào cũng đi qua cùng decorator; cần inventory các execution boundaries.

**Lỗi 16 — Dùng correlation ID làm metric label cho mọi task.** Cardinality bùng nổ; nên log/trace theo ID và đo metric aggregate.

**Lỗi 17 — Giữ ServletRequest hoặc SecurityContext như mutable object trong job dài.** Request đã kết thúc, thread thay đổi; chỉ truyền dữ liệu đã được kiểm chứng và cần thiết.

**Lỗi 18 — Tin rằng TaskDecorator bắt hết exception của Callable/Future.** Với `FutureTask`, exception có thể được lưu trong Future; quan sát đường lỗi đúng thay vì chỉ `catch` quanh `Runnable.run()`.

## 17. Checklist triển khai cho một hệ thống Spring

- [ ] Quy định **tên và phạm vi ID**: correlation ID, request ID, job ID, trace ID khác nhau thế nào.
- [ ] Xác định điểm ingress tạo/validate ID: gateway, servlet filter, message listener hoặc scheduler.
- [ ] Dùng header nhất quán như `X-Correlation-ID` nếu có hợp đồng; không coi header do client gửi là trusted identity.
- [ ] Đặt MDC trong scope ngắn của request/task và **restore trong finally**.
- [ ] Đăng ký `TaskDecorator` cho đúng `ThreadPoolTaskExecutor` được `@Async` hoặc service sử dụng.
- [ ] Chụp MDC **trên submitting thread tại mỗi task**, không chụp singleton lúc startup.
- [ ] Khi task không có snapshot, **clear worker MDC** để ngăn dữ liệu cũ.
- [ ] Với `CompletableFuture`, rà soát các callback non-async/Async và explicit executor ở mỗi bước cần propagation.
- [ ] Với job/broker, truyền correlation ID trong **job payload/headers** và định nghĩa retry attempt.
- [ ] Với HTTP client, thêm outbound propagation và validation tại downstream ingress.
- [ ] Khi dùng Micrometer Tracing, không tự tạo trace/span IDs thay thế chuẩn; kiểm tra integrations context propagation.
- [ ] Không đặt secret/PII vào MDC; kiểm soát độ dài/ký tự header và retention log.
- [ ] Thiết lập Logback/structured logging đọc key `correlationId`.
- [ ] Kiểm thử request A/B trên **cùng worker tái sử dụng**, exception, shutdown và callback chạy ở thread khác.
- [ ] Log/metric executor rejection với correlation ID của caller, không chờ worker log một task chưa nhận.
- [ ] Giám sát tỷ lệ log thiếu hoặc sai correlation ID và tính toàn vẹn liên kết job/request/trace.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Controller đặt `MDC.put("correlationId","req-1")` rồi gọi `@Async`. Worker chắc chắn đọc được `req-1` chưa?

**Đáp án:** Chưa. MDC thường là thread-local; cần TaskDecorator hoặc context propagation phù hợp, hoặc truyền ID như dữ liệu.

**Câu 2.** Tại sao phải chụp `MDC.getCopyOfContextMap()` trong `decorate` thay vì trong `run` của wrapper?

**Đáp án:** `decorate` được tạo tại điểm submit, nơi caller còn request context. `run` chạy trên worker, thường không có MDC của caller.

**Câu 3.** Vì sao cần `finally` dù task thường return bình thường?

**Đáp án:** Pool tái sử dụng worker; task có thể ném exception hoặc thoát sớm. `finally` bảo đảm restore/clear context, tránh rò ID sang task sau.

**Câu 4.** `MDC.clear()` sau task có luôn đúng hơn restore previous?

**Đáp án:** Không. Nếu wrapper hoặc instrumentation bên ngoài đã đặt context hợp lệ trên worker, clear sẽ xóa dữ liệu của scope đó. Snapshot/restore previous là cách lồng scope an toàn hơn.

**Câu 5.** `CompletableFuture.supplyAsync(fn)` có tự sử dụng bean `ThreadPoolTaskExecutor` gắn TaskDecorator trong Spring không?

**Đáp án:** Không. Nếu không truyền executor, nó dùng default async facility của JDK. Phải kiểm soát executor hoặc truyền ID như dữ liệu.

**Câu 6.** `@Async("workExecutor")` có khiến mọi `thenApply` phía sau luôn có đúng MDC không?

**Đáp án:** Không. Non-async continuation có thể chạy trên completion thread hoặc registration thread tùy timing; snapshot và boundary phải được quản lý rõ ràng.

**Câu 7.** Một consumer nhận Kafka message mang correlation ID nhưng không có HTTP request. Nên làm gì?

**Đáp án:** Đọc metadata, validate ID, đặt vào MDC trong scope của xử lý message, propagate khi publish tiếp và restore/clear sau khi xử lý. Không cần tạo ServletRequest giả.

**Câu 8.** Có nên đưa email khách hàng hoặc bearer token vào correlation ID?

**Đáp án:** Không. Dùng ID không chứa PII/secret; token không được ghi vào MDC hay log tập trung.

**Câu 9.** Correlation ID có thay thế W3C `traceparent` và OpenTelemetry span không?

**Đáp án:** Không. Correlation ID gom sự kiện theo ứng dụng; distributed tracing dùng trace/span context và cơ chế propagation chuẩn. Có thể dùng cả hai với mục đích rõ ràng.

**Câu 10.** Worker log có `correlationId=req-A` khi đang làm task của req-B. Nơi cần kiểm tra trước là gì?

**Đáp án:** Xem task nào đã đặt MDC mà không restore/clear, task req-B có đi qua TaskDecorator đúng executor không, và có capture snapshot từ submitter hay nhầm từ worker không.

**Câu 11.** Filter đã restore MDC sau HTTP request, liệu background job có cần giữ nguyên ServletRequest để còn ID không?

**Đáp án:** Không. Job nên có correlation ID như metadata immutable hoặc snapshot khi submit; giữ ServletRequest qua lifecycle lâu dài có thể gây lỗi/rò dữ liệu.

## Tóm tắt

Trong Spring Framework, **MDC là ngữ cảnh gắn với thread**, còn một logical request/job có thể chạy qua **nhiều thread và nhiều service**. Vì vậy:

1. **Tạo/validate correlation ID tại ingress**; phân biệt request/job/trace/span/idempotency IDs.
2. **Truyền nó tại ranh giới bất đồng bộ** bằng TaskDecorator capture tại submit, install trước khi worker chạy và restore previous trong `finally`; hoặc truyền ID như dữ liệu/job metadata.
3. **Không giả định `@Async`, `CompletableFuture`, raw thread, Reactor hay HTTP client tự chuyển MDC**. Mỗi ranh giới cần cơ chế propagation phù hợp.
4. **Trả đúng ID trong response header và đưa vào log pattern/structured logging**. Khi đi sang dịch vụ khác, truyền qua header hoặc message metadata với validation/trust policy.
5. **Bảo mật và đo lường:** không copy secret/PII, không dùng ID làm authorization, không biến ID có cardinality cao thành metric label; kiểm thử worker reuse và exception cleanup.

Một correlation ID được truyền đúng không chỉ giúp “tìm log nhanh hơn”, mà còn bảo đảm **log của request A không bị gán sang request B** trong hệ thống concurrency thực tế.

## Tài liệu tham khảo

1. SLF4J API — `MDC`: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
2. Logback Manual — Mapped Diagnostic Context: https://logback.qos.ch/manual/mdc.html
3. Spring Framework Javadoc — `TaskDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html
4. Spring Framework Javadoc — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
5. Spring Framework Reference — Task Execution and Scheduling (`@Async`): https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework Javadoc — `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
7. Spring Framework Reference — MVC asynchronous requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
8. Java SE 17 — `ThreadLocal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
9. W3C Trace Context — `traceparent` and `tracestate`: https://www.w3.org/TR/trace-context/
