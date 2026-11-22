# Context qua executor trong Java Logging: truyền MDC đúng và tránh rò rỉ

Trong một ứng dụng Java, log của một request thường cần `requestId`, `traceId`, `spanId` hoặc tên thao tác để có thể ghép nhiều sự kiện thành một luồng xử lý. Trong cùng một thread, logging backend có thể đọc các trường này từ **Mapped Diagnostic Context (MDC)**. Tuy nhiên, khi gửi công việc sang `ExecutorService`, `ThreadPoolExecutor`, `CompletableFuture` hoặc task executor của framework, công việc chạy trên thread khác. **Context gắn với caller thread không tự động đi theo trong mọi trường hợp**.

**Context qua executor** là cơ chế **chụp context khi giao việc → thiết lập nó trên worker trong thời gian chạy task → khôi phục context worker cũ trong `finally`**. Hai lỗi cần tránh là **mất correlation ID** (worker không thấy `requestId`) và **lẫn correlation ID** (worker phục vụ request mới nhưng giữ MDC của request cũ).

Ví dụ:

```text
INFO [thread=request-thread] requestId=req-A - event=request_received
INFO [thread=context-worker-1] requestId=none - event=without_propagation
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_runnable
INFO [thread=context-worker-1] requestId=none - event=after_restore
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_callable
INFO [thread=context-worker-1] requestId=req-B - event=next_request
```

Đây là output của ví dụ Java 17 + Logback trong bài: cùng worker được dùng lại, nhưng context đúng **chỉ tồn tại trong phạm vi của task tương ứng**. `none` trong pattern là ký hiệu không có request ID, không phải ID thật.

## 1. Logging context gồm những gì?

Một structured log có thể có:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "level": "INFO",
  "service": "checkout-service",
  "thread": "payment-worker-2",
  "requestId": "req-A",
  "traceId": "trace-42",
  "spanId": "span-7",
  "event": "payment_authorized"
}
```

Đây là JSON minh họa, không phải output mặc định của Java. Các trường trả lời những câu hỏi khác nhau:

| Trường | Vai trò | Lưu ý |
| --- | --- | --- |
| `thread` | Luồng phát event | Thread pool có thể tái sử dụng cùng thread cho nhiều request |
| `requestId` | Request của ứng dụng | Có thể đi qua nhiều thread và service |
| `traceId` / `spanId` | Trace/span trong distributed tracing | Phải phù hợp ngữ nghĩa tracing, không chỉ là chuỗi tùy ý |
| `operation` / `event` | Bước xử lý | Nên dùng tên ổn định, tránh cardinality cao |
| `tenantId` | Tenant liên quan nếu chính sách cho phép ghi | Không dùng một MDC key thay cơ chế phân quyền |
| `service` / `instance` | Nguồn phát log | Có thể đến từ cấu hình deployment thay vì thread |

**SLF4J MDC** là API cung cấp một map key-value kiểu chuỗi mà backend thích hợp dùng để format log. Trên cùng một thread:

```java
// Fragment: LOG là org.slf4j.Logger đã khởi tạo.
org.slf4j.MDC.put("requestId", "req-A");
try {
    LOG.info("event=request_started");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

Trong đoạn này, `MDC.remove` dọn một key đã đặt. Khi có ngữ cảnh MDC trước đó hoặc nhiều key do framework giữ, cần **khôi phục snapshot trước scope** thay vì xóa toàn bộ map mà không suy xét.

**MDC không phải tất cả execution context**: tracing `Context`, `SecurityContext`, locale, transaction, deadline, cancellation hoặc `ThreadLocal` riêng đều là các thành phần khác. Copy SLF4J MDC **không mặc nhiên** truyền những ngữ cảnh đó. Ngược lại, truyền tracing context đúng cũng không bảo đảm một encoder tự in mọi field MDC nếu chưa có integration.

## 2. Vì sao `ExecutorService` làm mất context?

Khi xử lý tuần tự:

```text
request-thread:
  MDC.put(requestId=req-A)
    -> service.call()
    -> LOG.info(...) thấy req-A
  MDC.remove(requestId)
```

Khi giao việc sang pool:

```text
request-thread                        context-worker-1
  MDC: {requestId=req-A}              MDC: {} hoặc scope khác
           |
           +-- executor.submit(task) ----> task.run()
                                           LOG.info(...)
```

MDC trong Logback classic gắn với thread. Một worker có thể được tạo từ lâu trước request, hoặc được tái sử dụng. `executor.submit(task)` **không có hợp đồng chung** tự mang SLF4J MDC của caller qua worker.

Hậu quả:

1. **Mất context:** log worker trống `requestId`, không ghép được với request.
2. **Rò rỉ context:** worker từng xử lý `req-A` không dọn MDC; sau đó task của `req-B` có thể ghi nhầm `req-A`.
3. **Xóa nhầm context:** task đặt MDC rồi gọi `clear()`, khiến một framework hoặc scope bên ngoài mất map vốn đã có.

Không giải quyết bằng cách đổi tên thread theo request. `context-worker-1` có thể phục vụ rất nhiều request; ngược lại, một request có thể đi qua nhiều worker. **Thread name giúp điều tra concurrency; request ID giúp tương quan nghiệp vụ.**

### `InheritableThreadLocal` không phải giải pháp mặc định

`InheritableThreadLocal` có thể truyền giá trị theo mô hình kế thừa khi tạo thread, nhưng **thread pool tái sử dụng worker** và thời điểm tạo thread không đồng nghĩa với thời điểm submit task. Dữ liệu kế thừa có thể cũ, không đầy đủ hoặc nằm ngoài vòng đời request. Với executor, context phải được quản lý **theo lần thực thi tác vụ**, không dựa vào việc thread được tạo từ đâu.

## 3. Công thức an toàn: capture → install → run → restore

```text
THREAD GỬI                               THREAD WORKER
-----------                              -------------
MDC = {requestId=req-A}
     |
     +-- snapshot map ở caller
     |
     +-- submit(wrappedTask) ----------------> previous = snapshot MDC worker
                                             install(req-A)
                                             try {
                                                 task.run()
                                             } finally {
                                                 restore(previous)
                                             }
```

Bốn bước:

1. **Capture ở thread gửi:** gọi `MDC.getCopyOfContextMap()` **trước khi submit**, khi caller vẫn còn context hợp lệ. API trả bản sao map hoặc `null`.
2. **Giữ snapshot riêng:** không lấy lại MDC của caller sau khi task được xếp hàng; caller có thể đã dọn hoặc nhận request mới.
3. **Install trên worker:** nếu snapshot có dữ liệu thì gọi `MDC.setContextMap(snapshot)`; nếu `null` thì `MDC.clear()`.
4. **Restore trong `finally`:** lấy lại map của worker trước task và phục hồi nó, kể cả khi task ném exception.

Tại sao **restore** tốt hơn chỉ `clear`?

```text
Trước task: {jobId=batch-3}
Trong task: {requestId=req-A}
Sau task:   {jobId=batch-3}    <- phục hồi scope trước
```

Nếu chỉ `MDC.clear()` ở cuối, ta làm mất `jobId` vốn có trước đó. Nếu không dọn, ta để `req-A` bám vào worker. `MDC.setContextMap` thay thế map bằng bản sao, do đó không cần tự ghép từng key cho bài toán **thực thi task dưới một snapshot hoàn chỉnh**.

Theo SLF4J 2.x, `MDC.setContextMap(null)` được chấp nhận; dùng nhánh `clear()` cho `null` vẫn là cách viết rõ ràng và tránh phụ thuộc vào cách xử lý null của một số adapter cũ.

## 4. Ví dụ đầy đủ Java 17 + Maven + SLF4J + Logback

Ví dụ dùng **Java 17**, **SLF4J API 2.0.17** và **Logback classic 1.5.18**. Logback làm backend/provider có hỗ trợ MDC. Mã dùng một `ExecutorService` có một thread được đặt tên chủ động để chứng minh propagation và sự tái sử dụng worker.

Các version là lựa chọn cụ thể cho bài thực hành, **không được hiểu là phiên bản mới nhất**. Muốn đưa vào production cần theo dependency management và chính sách cập nhật bảo mật của dự án.

Cấu trúc:

```text
executor-context-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/ExecutorContextDemo.java
    └── resources/logback.xml
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>executor-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.ExecutorContextDemo</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`slf4j-api` chỉ định nghĩa facade và MDC API; `logback-classic` xử lý event và viết log. **Không thêm một provider SLF4J thứ hai** như `slf4j-simple` hoặc `slf4j-nop` vào cùng runtime khi mong muốn hành vi Logback.

### 4.2. `logback.xml`

Đặt tại `src/main/resources/logback.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%level [thread=%thread] requestId=%X{requestId:-none} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
```

`%level` in mức sự kiện, `%thread` là tên thread, `%X{requestId:-none}` đọc MDC hoặc in giá trị dự phòng `none` nếu không có key, `%msg` là thông điệp. Appender gửi output tới **stderr**.

Pattern cố ý không có timestamp để ví dụ có output ổn định. Trong production, cần timestamp/offset rõ ràng, tên logger, service, trace ID, exception và định dạng phù hợp collector.

### 4.3. `ExecutorContextDemo.java`

```java
package com.example.logging;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class ExecutorContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ExecutorContextDemo.class);

    private ExecutorContextDemo() {
    }

    private static void install(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    private static Runnable withMdc(Runnable task) {
        // Capture trên thread gửi trước khi submit.
        Map<String, String> submitted = MDC.getCopyOfContextMap();

        return () -> {
            // Giữ nguyên context trước đó của worker.
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                install(submitted);
                task.run();
            } finally {
                install(previous);
            }
        };
    }

    private static <T> Callable<T> withMdc(Callable<T> task) {
        Map<String, String> submitted = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                install(submitted);
                return task.call();
            } finally {
                install(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        Thread producer = Thread.currentThread();
        String originalName = producer.getName();
        producer.setName("request-thread");

        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "context-worker-1"));

        try {
            // Khởi tạo worker và bảo đảm context ban đầu trống.
            pool.submit(() -> MDC.clear()).get();

            MDC.put("requestId", "req-A");
            try {
                LOG.info("event=request_received");

                // Không wrap: worker không có req-A.
                pool.submit(() ->
                        LOG.info("event=without_propagation")).get();

                // Wrap Runnable: worker thấy req-A trong task.
                pool.submit(withMdc(() ->
                        LOG.info("event=wrapped_runnable"))).get();

                // Sau khi restore, worker lại không có requestId.
                pool.submit(() ->
                        LOG.info("event=after_restore")).get();

                // Wrap Callable để nhận giá trị từ worker.
                String result = pool.submit(
                        withMdc((Callable<String>) () -> {
                            LOG.info("event=wrapped_callable");
                            return MDC.get("requestId");
                        })).get();

                System.out.println("callableRequestId=" + result);
            } finally {
                MDC.clear();
            }

            // Request khác dùng lại đúng worker cũ.
            MDC.put("requestId", "req-B");
            try {
                pool.submit(withMdc(() ->
                        LOG.info("event=next_request"))).get();
            } finally {
                MDC.clear();
            }
        } finally {
            pool.shutdown();
            producer.setName(originalName);
        }

        System.out.println("finished=true");
    }
}
```

### 4.4. Chạy và kiểm chứng

Trong thư mục `executor-context-demo/`:

```bash
mvn -q compile exec:java
```

**Sáu log event ứng dụng trên stderr, theo đúng thứ tự:**

```text
INFO [thread=request-thread] requestId=req-A - event=request_received
INFO [thread=context-worker-1] requestId=none - event=without_propagation
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_runnable
INFO [thread=context-worker-1] requestId=none - event=after_restore
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_callable
INFO [thread=context-worker-1] requestId=req-B - event=next_request
```

**Stdout do chương trình tự in:**

```text
callableRequestId=req-A
finished=true
```

Maven hoặc terminal có thể có output khác của công cụ build. Nếu stdout và stderr được gộp, thứ tự **xen kẽ giữa hai stream** không được đảm bảo tuyệt đối; riêng các event log trong ví dụ đồng bộ được gửi theo thứ tự nhờ `Future.get()`.

Giải thích kết quả:

1. `request_received` ở producer có `req-A`.
2. `without_propagation` chạy trong worker mà không được copy MDC, nên chỉ hiện `none`.
3. `wrapped_runnable` được tạo khi producer có `req-A`; worker cài snapshot trước `LOG.info`.
4. `after_restore` được chạy trên cùng worker sau khi wrapper đã kết thúc; vì map trước wrapper trống, output là `none`, không rò rỉ `req-A`.
5. `wrapped_callable` vẫn có `req-A` và trả giá trị đó về caller qua `Future<String>`.
6. `next_request` cho thấy worker được tái sử dụng nhưng không giữ ID trước; task mới nhận `req-B` đúng phạm vi.

**Lưu ý về Java 17:** Ví dụ dùng `shutdown()` và các `Future.get()` đã chờ đủ task; không dùng `try-with-resources` cho `ExecutorService` vì không nên giả định interface này triển khai `AutoCloseable` trong JDK 17. Trong hệ thống thật, cần chiến lược shutdown/awaitTermination/timeout và interrupt handling phù hợp.

### 4.5. Kiểm tra mặt ngược của wrapper

Nếu chuyển hai lời gọi `withMdc(() -> LOG.info(...))` thành task thuần, log worker sẽ không tự nhận context từ producer. Nếu bỏ `install(previous)` trong `finally`, một task sau đó có thể nhận **requestId cũ**. Nếu lấy snapshot **bên trong worker** thay vì caller, ta chỉ copy context của worker, không giải quyết propagation.

Bài thực hành chính nhằm chứng minh cả **truyền đúng** lẫn **phục hồi đúng**, vì test chỉ kiểm tra “task A thấy ID A” chưa phát hiện được rò rỉ sang task B.

## 5. Các API MDC cần hiểu

| API | Tác dụng | Điểm cần chú ý |
| --- | --- | --- |
| `MDC.put(k, v)` | Thêm/cập nhật key trên thread hiện tại | Không dùng để truyền trực tiếp qua thread khác |
| `MDC.get(k)` | Đọc key trên thread hiện tại | Có thể trả `null` |
| `MDC.remove(k)` | Xóa một key | Không tự phục hồi giá trị cũ nếu key bị ghi đè |
| `MDC.clear()` | Xóa cả map MDC của thread hiện tại | Có thể làm mất key do framework đang quản lý |
| `MDC.getCopyOfContextMap()` | Lấy bản sao map hiện tại | Có thể trả `null` |
| `MDC.setContextMap(map)` | Thay map hiện tại bằng bản sao | Dùng cùng cơ chế restore để tạo scope |
| `MDC.putCloseable(k, v)` | Trả scope có thể tự đóng để bỏ một key | Không thay thế được snapshot/restore cả map trong mọi tình huống |

**`MDC.getCopyOfContextMap()` trả snapshot**, không phải một tham chiếu live được tự cập nhật khi caller thay context. Điều này cần thiết: task đã gửi cho `req-A` phải giữ ngữ nghĩa `req-A` kể cả khi producer chuyển sang xử lý `req-B` trước lúc worker lấy task từ queue.

### Tại sao wrapper có `finally`?

```java
// Fragment mô tả nguyên tắc: previous, submitted và task đã có.
try {
    install(submitted);
    task.run();
} finally {
    install(previous);
}
```

Ngay cả khi `task.run()` ném exception, `finally` vẫn phục hồi map. Không dùng một `catch (Exception ignored)` để nuốt lỗi. Với `ExecutorService.submit`, lỗi từ task thường nằm trong `Future` và xuất hiện khi gọi `get()` dưới dạng `ExecutionException`. Nếu code không bao giờ quan sát Future, việc ghi log lỗi và xử lý sự cố cần một chính sách riêng.

## 6. `execute`, `submit` và `Callable<T>`

Tại ranh giới giao task, cần dùng wrapper phù hợp kiểu callback:

```java
// Fragment: executor, withMdc và các hàm nghiệp vụ được định nghĩa sẵn.
executor.execute(withMdc(() -> sendMessage()));

executor.submit(withMdc(() -> writeAuditSummary()));

java.util.concurrent.Future<String> result = executor.submit(
        withMdc((java.util.concurrent.Callable<String>) () ->
                calculateResult()));
```

Đây là fragment, không phải chương trình độc lập; các method như `sendMessage()` phải do ứng dụng cung cấp.

- `execute(Runnable)` không trả Future; cách xử lý lỗi phụ thuộc executor/uncaught exception handling.
- `submit(Runnable)` hoặc `submit(Callable<T>)` trả `Future`; `get()` giúp chờ và quan sát exception.
- **Capture trước submission** là nguyên tắc cho cả hai.
- Nếu framework đã trang bị context propagation tại executor, nên xác định liệu còn cần wrapper tại caller hay không, tránh tạo các scope với nguồn context cạnh tranh.
- Khi task bị từ chối (`RejectedExecutionException`), wrapper chưa được chạy, nên không nên để việc khôi phục context worker phụ thuộc vào một task chưa từng thực thi.
- Khi task bị cancel hoặc bị interrupt trong lúc chạy, `finally` vẫn cần restore; không được che giấu hoặc nuốt interrupt tùy tiện.

### Task được xếp hàng và caller đã thay context

```text
t0 caller MDC = req-A
t1 tạo wrapper và capture req-A
t2 gọi submit(...)
t3 caller kết thúc req-A, clear MDC
t4 caller nhận req-B, put(req-B)
t5 worker chạy task của req-A -> phải thấy req-A
t6 worker restore context trước đó
```

Đó là lý do **không lấy MDC của caller quá muộn**. Snapshot theo task phản ánh quan hệ của task với nơi tạo nó, không phụ thuộc vào thread nào sẽ được executor chọn.

## 7. `CompletableFuture`: mỗi giai đoạn async có thể đổi thread

Một chain có thể gồm nhiều callback:

```text
supplyAsync(...)       -> worker A
thenApply(...)         -> có thể chạy ở thread hoàn thành stage trước
thenApplyAsync(...)    -> có thể schedule sang executor khác
whenCompleteAsync(...) -> có thể schedule một callback khác
```

**Không tự động suy ra** rằng một wrapper ở `supplyAsync` bảo đảm context cho toàn chain. Với các stage async, cần propagation tại đúng boundary. Stage không có hậu tố Async như `thenApply` cũng không có nghĩa chắc chắn chạy ở thread caller.

Ví dụ một `Supplier` wrapper:

```java
// Fragment: method trong utility có imports Map, Supplier, MDC.
static <T> java.util.function.Supplier<T> withMdcSupplier(
        java.util.function.Supplier<T> action) {

    Map<String, String> submitted = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (submitted == null) MDC.clear();
            else MDC.setContextMap(submitted);

            return action.get();
        } finally {
            if (previous == null) MDC.clear();
            else MDC.setContextMap(previous);
        }
    };
}
```

Áp dụng trong một class có method `withMdcSupplier`:

```java
// Fragment: executor và callDownstream() có sẵn.
java.util.concurrent.CompletableFuture<String> future =
        java.util.concurrent.CompletableFuture.supplyAsync(
                withMdcSupplier(() -> callDownstream()),
                executor);
```

Đây là **fragment**, không phải chương trình chạy độc lập. Các callback dạng `Function`, `Consumer`, `BiFunction` có thể cần wrapper tương ứng hoặc một **context-aware executor** được cấu hình tại tầng hạ tầng.

**Tránh double wrapping tùy tiện:** nếu ứng dụng đã có một executor decorator truyền context, việc bọc từng stage thêm lần nữa có thể tạo thứ tự snapshot không mong muốn hoặc tăng chi phí. Chọn một chiến lược nhất quán, thử với cả success, failure, cancel và continuation.

## 8. Scheduled tasks: đừng giữ snapshot request vô hạn

Với `ScheduledExecutorService`:

```java
// Fragment: scheduler và job đã được khai báo.
scheduler.scheduleAtFixedRate(
        withMdc(job), 0, 1,
        java.util.concurrent.TimeUnit.MINUTES);
```

Nếu `withMdc(job)` được tạo lúc `requestId=req-A` và job chạy mỗi phút trong nhiều giờ, mỗi lượt có thể tiếp tục mang **req-A cũ**. Về mặt code wrapper restore vẫn đúng, nhưng ý nghĩa context đã sai.

Đối với scheduled/background jobs:

- Tạo `jobId` hoặc `runId` phù hợp **mỗi lần thực thi**.
- Chỉ giữ `originRequestId` nếu thực sự cần liên kết với yêu cầu đã tạo công việc và chính sách cho phép.
- Không biến một request ID ngắn hạn thành danh tính vĩnh viễn của định kỳ.
- Dọn scope MDC ở cuối mỗi execution, nhất là khi scheduler tái sử dụng thread.
- Nếu tác vụ được lưu và chạy sau restart, lưu metadata nghiệp vụ hợp lệ trong job record, không kỳ vọng `ThreadLocal` còn tồn tại.

## 9. Spring: TaskDecorator và context propagation tích hợp

Spring Framework hỗ trợ `TaskDecorator` để wrap task khi `TaskExecutor` giao việc. Đây là nơi tốt để **tập trung logic propagation**, tránh yêu cầu mỗi developer tự nhớ `withMdc`.

Một fragment cấu hình `ThreadPoolTaskExecutor`:

```java
// Fragment trong cấu hình Spring; executor đã là ThreadPoolTaskExecutor.
executor.setTaskDecorator(task -> {
    java.util.Map<String, String> submitted =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> previous =
                org.slf4j.MDC.getCopyOfContextMap();

        try {
            if (submitted == null) org.slf4j.MDC.clear();
            else org.slf4j.MDC.setContextMap(submitted);

            task.run();
        } finally {
            if (previous == null) org.slf4j.MDC.clear();
            else org.slf4j.MDC.setContextMap(previous);
        }
    };
});
```

Đây là fragment cần Spring và executor được khởi tạo đúng; không phải class standalone. Cần đăng ký decorator **trước khi task được gửi** và xác minh executor mà `@Async`/code thực sử dụng là executor đã trang bị decorator.

Spring Framework 6.1+ còn có `ContextPropagatingTaskDecorator` sử dụng Micrometer Context Propagation:

```java
// Fragment với Spring Framework/Micrometer integration phù hợp.
executor.setTaskDecorator(
        new org.springframework.core.task.support
                .ContextPropagatingTaskDecorator());
```

Đoạn này có yêu cầu dependency/version/integration tương ứng. **Không mặc định** nó sao chép mọi custom `ThreadLocal` và MDC trong mọi dự án; phải xem context accessor nào đã đăng ký, trace observation context nào đang active và test end-to-end. Decorator có thêm overhead với task rất nhỏ.

Nếu `@Async` không chuyển thread do self-invocation/proxy hoặc cấu hình sai, đó là một lỗi **kích hoạt async**, cần xử lý trước khi kết luận MDC propagation không hoạt động.

## 10. Log4j 2 ThreadContext có cùng nguyên tắc

Log4j 2 dùng `ThreadContext` cho map và stack context (NDC). Một ví dụ fragment với ThreadContext **map**:

```java
// Fragment: org.apache.logging.log4j.ThreadContext và Map đã import.
Map<String, String> submitted = ThreadContext.getImmutableContext();

Runnable wrapped = () -> {
    Map<String, String> previous = ThreadContext.getImmutableContext();
    try {
        ThreadContext.clearMap();
        ThreadContext.putAll(submitted);
        task.run();
    } finally {
        ThreadContext.clearMap();
        ThreadContext.putAll(previous);
    }
};
```

Fragment này giả định `task` đã khai báo và wrapper được tạo **ở caller**. `getImmutableContext()` cung cấp snapshot map; `clearMap`/`putAll` gắn và phục hồi map. Nếu ứng dụng dùng **ThreadContext stack/NDC**, bản copy map không tự truyền stack — cần cơ chế riêng.

Với ứng dụng dùng SLF4J nhưng backend Log4j 2, hãy kiểm tra chính xác SLF4J provider, bridge và sự tương thích của MDC. Không đặt những bridge SLF4J ↔ Log4j 2 đi hai chiều trong cùng runtime vì có thể tạo vòng lặp.

## 11. OpenTelemetry tracing context khác SLF4J MDC

OpenTelemetry có `Context`/`Scope` để truyền span hiện hành và những dữ liệu context được định nghĩa. API Java cung cấp các cách wrap `Runnable`/`Callable`/executor:

```java
// Fragment: pool là Executor đã tồn tại, ứng dụng có OTel Context.
java.util.concurrent.Executor propagated =
        io.opentelemetry.context.Context.taskWrapping(pool);

propagated.execute(() -> performOperation());
```

Đây là fragment, không phải chương trình thuần JDK; `performOperation()` do ứng dụng cung cấp. `Context.taskWrapping` có mục tiêu chuyển **OpenTelemetry Context** qua executor. Nó không tự động chứng minh mọi MDC key tùy biến được truyền hoặc xuất ra encoder. Cần integration giữa tracing và logging để `traceId`/`spanId` xuất hiện đúng ở log event.

Phân biệt:

| Context | API ví dụ | Phạm vi |
| --- | --- | --- |
| SLF4J MDC | `MDC.put`/`MDC.getCopyOfContextMap` | Metadata cho log, thường theo thread |
| Log4j 2 map/stack | `ThreadContext` | Metadata Log4j event |
| OpenTelemetry | `Context.current()`, `Scope`, `Context.taskWrapping` | Tracing/context propagation |
| Spring Security | `SecurityContext` và executor wrappers tương ứng | Thông tin principal/authorization, phải có cơ chế bảo mật đúng |
| Reactor | Reactor `Context`/context propagation | Context qua reactive operators/scheduler |

**Không dùng logging MDC như kho chứa principal đáng tin cho authorization.** Cơ chế bảo mật phải có chính sách truyền và kiểm tra riêng; MDC chủ yếu phục vụ điều tra và quan sát.

### Reactive và virtual threads

- Trong **Reactor**, pipeline có thể chuyển thread qua scheduler; `ThreadLocal` đơn thuần không đủ cho mọi asynchronous boundary. Cần Reactor Context hoặc context-propagation integration phù hợp.
- **Virtual threads** được hỗ trợ chính thức trong Java 21+; chúng có ThreadLocal nhưng cấu trúc thực thi khác pool truyền thống. Không suy ra rằng mọi MDC từ caller tự động được sao chép qua nơi tạo virtual thread hoặc mọi callback reactive.
- Ví dụ chính của bài dùng **Java 17 platform threads**, nên không phụ thuộc API của Java 21.

## 12. Async business task khác async log appender

Có hai dạng “async” dễ bị nhầm:

1. **Async business execution:** `ExecutorService` chuyển business code sang worker khác. **Phải xem propagation ngữ cảnh qua task**.
2. **Async logging backend:** business code phát log, backend chụp log event rồi queue sang thread ghi file/console. **Backend/encoder phải giữ metadata của event** qua queue.

Bật `AsyncAppender` của Logback **không làm** `ExecutorService.submit` tự truyền SLF4J MDC. Ngược lại, wrapper task đúng không bảo đảm queue của logging backend không drop event hoặc collector đã nhận record.

Nếu tự viết formatter bất đồng bộ, đừng gọi `Thread.currentThread().getName()` ở worker ghi log rồi coi đó là thread của event; hãy dùng metadata được backend capture tại thời điểm phát log.

## 13. Những lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Worker thiếu request ID | Không capture/propagate | Snapshot ở caller, install khi worker chạy |
| Log request B mang ID của A | Không restore previous, worker bị reuse | Dùng `finally` restore; test cùng worker hai request |
| Snapshot ra null | Caller chưa có MDC hoặc provider không phù hợp | Kiểm tra nơi đặt context và SLF4J backend |
| Worker có ID nhưng encoder không in | Pattern/JSON encoder thiếu MDC key | Kiểm tra `%X{requestId}` và field mapping |
| `CompletableFuture` đầu đúng, stage sau sai | Async boundary mới không propagate | Wrap từng stage hoặc dùng context-aware executor |
| `Callable` chạy nhưng exception không thấy | `submit` giữ lỗi trong `Future` | Quan sát `get()`/callback lỗi |
| Dùng `InheritableThreadLocal` nhưng lúc đúng lúc sai | Worker tạo/reuse không đồng bộ với submit | Propagate theo task, không chỉ theo thread creation |
| Scheduled job ghi ID cũ | Snapshot chụp một lần lúc lên lịch | Tạo context cho từng lần chạy |
| Spring `@Async` không thấy decorator | Executor khác hoặc proxy không active | Kiểm tra cấu hình executor và async activation |
| Mất context framework trên worker | Chỉ gọi `clear()` cuối mà không restore | Lưu previous rồi restore |
| Có MDC nhưng trace ID sai | OTel context khác với SLF4J MDC | Truyền đúng tracing context và tích hợp log |
| Log4j 2 NDC stack mất | Chỉ copy ThreadContext map | Dùng propagation cho stack nếu cần |
| Tác vụ cực nhỏ bị chậm | Copy quá nhiều MDC/đúp wrapper | Giới hạn key, đo overhead, dùng decorator thích hợp |
| Task lỗi rồi context vẫn còn | Không dùng `finally` hoặc error handler nuốt lỗi | Scope `finally`; không che giấu exception |
| Cross-tenant leakage | Request context chưa dọn hoặc chứa dữ liệu không hợp lệ | Test isolation, dọn context, security review |
| Test dùng SLF4J NOP/Simple | Provider không hỗ trợ MDC như Logback | Kiểm tra runtime/test classpath |
| Thread name đúng nhưng request ID sai | Thread name không phải correlation ID | Theo dõi MDC và request lifecycle riêng |

**Trình tự điều tra:**

```text
Caller có requestId khi submit?
    |
    v
Snapshot được lấy trước khi clear?
    |
    v
Đúng wrapper/executor được thực thi?
    |
    v
Worker được install trước LOG.info?
    |
    v
Appender/encoder có đọc MDC?
    |
    v
finally có restore previous?
    |
    v
Task tiếp theo cùng worker còn context cũ không?
```

Nếu mỗi bước đúng mà dashboard vẫn thiếu ID, tiếp tục kiểm tra collector/structured field mapping. **Đọc đúng MDC trong Java không tự chứng minh pipeline đã lưu field đó**.

## 14. Kiểm thử: chứng minh có propagation và không leak

Một bộ test thực tế nên bao gồm:

1. **Caller có context:** `requestId=req-A` trước khi nộp task.
2. **Unwrapped task:** trong môi trường Logback demo, worker không tự thấy req-A.
3. **Wrapped Runnable:** worker thấy req-A.
4. **Post-restore task:** ngay sau wrapper, cùng worker không còn req-A.
5. **Wrapped Callable:** `Future.get()` nhận giá trị đúng.
6. **Request B:** cùng worker phải thấy req-B, không lẫn A.
7. **Exception path:** task ném lỗi nhưng `finally` vẫn restore.
8. **Nested scopes:** worker vốn có context của framework, sau child task vẫn giữ nguyên.
9. **Multiple keys:** request ID, trace ID và operation được xử lý nhất quán.
10. **Async chain:** các `CompletableFuture` stages cần propagation đều có ID đúng.
11. **Cancel/reject:** task chưa chạy hoặc hủy không làm hỏng context của producer/worker.
12. **Scheduled execution:** job sinh run ID phù hợp mỗi lần chạy.
13. **Backend/collector:** log text hoặc JSON thực tế chứa field và cho phép truy vấn.
14. **Security:** không copy token, secret, raw request body hoặc thông tin tenant vượt quyền.

Một kiểm tra có thể thêm vào code thực hành:

```java
// Fragment: pool và withMdc(Runnable) đã khai báo trong lớp demo.
var failed = pool.submit(withMdc(() -> {
    LOG.info("event=before_failure");
    throw new IllegalStateException("simulated failure");
}));

try {
    failed.get();
} catch (java.util.concurrent.ExecutionException expected) {
    // Ở bài test, xác nhận nguyên nhân lỗi; worker đã restore ở finally.
}

pool.submit(() -> LOG.info("event=after_failure")).get();
```

Đây là **fragment**, không chạy độc lập. Trong production, không để `catch` trống và không bỏ qua nguyên nhân exception; mục tiêu bài tập là kiểm chứng context của task lỗi đã được dọn trước task kế tiếp.

## 15. Bảo mật, giới hạn và chiến lược vận hành

- **Chỉ đưa metadata tối thiểu vào MDC:** request ID/trace ID/operation khi có ích. Tránh password, token, cookie phiên, dữ liệu thanh toán hoặc raw HTTP body.
- **Xác thực input dùng làm request ID:** giới hạn độ dài, ký tự và nguồn tạo ID; không tin vào header client tự xưng là ID hợp lệ mà không có quy tắc.
- **Giới hạn số key và độ dài value:** map quá lớn làm tăng overhead snapshot/restore, memory footprint của task đang chờ.
- **Không giữ object request lớn trong ThreadLocal:** dễ giữ tham chiếu lâu hơn scope, gây memory leak.
- **Đừng lan truyền quyền bảo mật chỉ bằng MDC:** dùng security context mechanism thích hợp và authorize lại ở boundary cần thiết.
- **Không truyền MDC của request sống vài giây vào job sống nhiều giờ** nếu chỉ cần một job ID độc lập.
- **Sử dụng một chiến lược nhất quán:** wrapper thủ công, executor decorator hoặc framework instrumentation. Nếu phối hợp, phải xác định thứ tự ưu tiên/scope và test.
- **Quan sát overhead:** với hàng triệu task nhỏ, context capture/restore có thể đáng kể; đo latency, queue depth và throughput.
- **Phân biệt propagation với reliability:** context đúng không đảm bảo log không bị lọc theo level, dropped trong async queue hoặc bị collector cắt.
- **Khi gửi việc qua process/network:** MDC trong JVM không tự theo HTTP/gRPC/Kafka. Cần hợp đồng truyền correlation/tracing metadata, kiểm soát trust boundary và làm sạch ở consumer.

**Kết luận:** Logging context qua executor không phải chỉ là thêm `MDC.put` bên trong worker. Đó là **scope quản lý theo task**, gồm snapshot lúc gửi, cài đặt lúc chạy và khôi phục context trước đó trong `finally`. Đặt đúng scope sẽ giúp log của cùng một request có correlation ID xuyên thread, đồng thời ngăn request mới bị gắn nhầm ID cũ khi thread pool tái sử dụng worker.

## Tài liệu chính thức

- SLF4J — MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback — MDC and managed threads: https://logback.qos.ch/manual/mdc.html
- Logback — PatternLayout và `%X{key:-default}`: https://logback.qos.ch/manual/layouts.html
- Oracle Java 17 — ExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java 17 — CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework — ContextPropagatingTaskDecorator: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- OpenTelemetry Java — Context propagation: https://opentelemetry.io/docs/languages/java/api/
