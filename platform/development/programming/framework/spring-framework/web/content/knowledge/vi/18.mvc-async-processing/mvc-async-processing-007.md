# Spring MVC — Phát hiện ngắt kết nối, dọn tài nguyên và xử lý lỗi sau khi đã gửi header

## 1. Vấn đề thực tế và mục tiêu

Spring MVC hỗ trợ xử lý bất đồng bộ bằng `Callable`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody` và một số reactive return types. Controller có thể kết thúc method từ lâu nhưng HTTP response vẫn mở. Nếu client đóng tab, ngắt mạng, hủy download hoặc reverse proxy chủ động đóng kết nối, server có thể vẫn giữ scheduled task, subscription, buffer hoặc stream đang phục vụ client đó.

Ví dụ endpoint SSE thông báo tiến độ:

~~~http
GET /api/events HTTP/1.1
Accept: text/event-stream
~~~

Server phát:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-store

event: progress
data: {"job":"A123","percent":30}

: heartbeat

event: progress
data: {"job":"A123","percent":50}
~~~

Một browser đóng tab khi đã nhận 50% không làm Servlet thread tự động được gọi một callback "remote disconnected" ngay tại thời điểm đó. Nếu kết nối không còn hoạt động nhưng không có lần ghi mới, backend có thể chưa biết. Trong lúc chờ, những đối tượng còn sống có thể gây **memory leak, task leak, subscriber leak, thread exhaustion và lãng phí tài nguyên**.

Sau bài học, bạn cần giải thích được:

- **Phát hiện disconnect**: giới hạn Servlet API, write/flush failure, heartbeat SSE, proxy idle timeout, `IOException` và `AsyncRequestNotUsableException`.
- **Quản lý lifecycle**: `SseEmitter.onCompletion`, `onTimeout`, `onError`, `DeferredResult` và container ASYNC dispatch.
- **Cleanup idempotent**: dọn client registry, ScheduledFuture, broker subscription, file/DB stream, queue, MDC; chống nhiều callback chạy cạnh tranh.
- **HTTP response committed**: khi status/headers đã gửi, không thể tùy tiện đổi status 200 thành 500 hay trả JSON lỗi mới.
- **Lỗi streaming**: in-band SSE error event nếu connection còn usable; dừng ghi và cleanup nếu I/O failure.
- **Kiểm thử**: Java 17 / Spring Boot 3.5, Maven, MockMvc async và kiểm thử socket disconnect thật.

Đây là bài về **Spring MVC trên Servlet stack**. WebFlux và WebSocket có lifecycle, API và backpressure khác; không sao chép giả định của một stack sang stack kia.

## 2. Vòng đời của Servlet async processing

### 2.1. Request đồng bộ

~~~text
Client -> Filter -> DispatcherServlet -> Controller
       -> View/Converter -> Response write -> Request complete
~~~

Controller return thường gắn gần với thời điểm server kết thúc xử lý response.

### 2.2. Callable và DeferredResult

~~~text
REQUEST dispatch
  |
  +-> Controller returns Callable/DeferredResult
  |
  +-> Servlet request enters async mode
  |
  +-> Initial servlet thread released
  |      HTTP response remains pending
  |
  +-> Worker or callback provides result
           |
           v
       ASYNC dispatch
           |
           v
       Serialize/complete response
~~~

- `Callable<T>`: Spring MVC submit Callable vào `AsyncTaskExecutor`; khi trả giá trị/exception, request được async-dispatch để hoàn tất.
- `DeferredResult<T>`: ứng dụng giữ handle và tự gọi `setResult` hoặc `setErrorResult` từ callback/thread khác; MVC xử lý kết quả cuối.
- `SseEmitter` và `ResponseBodyEmitter`: một request có thể phát **nhiều** dữ liệu/events cho đến complete, timeout hoặc error.
- `StreamingResponseBody`: callback viết trực tiếp vào OutputStream; Spring MVC có executor cho phần ghi, nhưng Servlet I/O vẫn thường blocking.

**Controller return không phải kết thúc đời sống tài nguyên của SSE.** Nếu tạo ScheduledFuture trong controller rồi gọi cancel trong `finally` của controller method, timer có thể bị hủy ngay trước khi stream thật sự chạy. Cần gắn cleanup vào **async lifecycle callbacks**.

### 2.3. Filter và interceptor cũng thay đổi

Một `OncePerRequestFilter` có thể thoát khỏi initial REQUEST dispatch trong khi SSE stream còn mở. Vì vậy duration đo bởi `try/finally` quanh `chain.doFilter` ban đầu là **dispatch duration**, không phải toàn bộ stream lifetime.

`AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` được gọi khi MVC bắt đầu xử lý concurrent, thay vì `postHandle` và `afterCompletion` ngay ở lượt đầu. Khi result hoàn thành, có thể có ASYNC redispatch. Timeout/disconnect cần callback tương ứng; không giả định interceptor `afterCompletion` luôn chạy cùng lúc với controller method return.

Servlet configuration cũng cần `asyncSupported=true` cho DispatcherServlet và filters liên quan; filter mappings phải xét `DispatcherType.ASYNC` nếu một filter cần hoạt động trong redispatch. Spring Boot thường thiết lập tích hợp MVC căn bản, nhưng custom registration vẫn cần kiểm tra.

## 3. Client disconnect được phát hiện lúc nào?

**Servlet API không cung cấp một notification tức thời đáng tin rằng remote client vừa biến mất.** Đây là giới hạn được tài liệu Spring MVC nêu rõ. Với HTTP streaming, cách phổ biến để phát hiện client ngắt là **thử ghi**; khi TCP connection/proxy không còn usable, write/flush có thể ném exception.

### 3.1. Một dòng thời gian

~~~text
12:00:00  Browser mở EventSource
12:00:01  Server gửi event #1
12:00:05  Browser mất mạng / đóng tab
12:00:06  Không có event nào để gửi -> server có thể chưa biết
12:00:15  Heartbeat write/flush -> có thể phát hiện lỗi
12:00:15+ AsyncListener/container error notification
           Spring MVC completes async lifecycle
~~~

Thời gian chỉ minh họa. OS socket buffers, reverse proxy buffering, TCP timeouts, kernel/network stack và cách container flush có thể làm **lần ghi đầu tiên sau disconnect chưa thất bại ngay**. Heartbeat giúp giảm khoảng im lặng nhưng không bảo đảm phát hiện trong đúng một số giây.

### 3.2. Những tín hiệu cần phân biệt

| Sự kiện | Ý nghĩa hợp lý | Không được suy ra |
| --- | --- | --- |
| `IOException: Broken pipe` | Ghi lên connection đã đóng hoặc bị reset | Mọi IOException đều do người dùng chủ động hủy |
| `Connection reset by peer` | Peer/proxy TCP reset | HTTP status 500 đã được trả tới client |
| `AsyncRequestNotUsableException` | Async response không còn usable do lỗi ghi, container error, hoặc lifecycle đã hoàn tất | Có thể tiếp tục viết thêm JSON |
| `SseEmitter.onError(Throwable)` | Container báo lỗi async | Chắc chắn do client đóng tab |
| `SseEmitter.onTimeout()` | Servlet async timeout | Người dùng chủ động ngắt |
| `SseEmitter.onCompletion()` | Async request kết thúc vì bất kỳ nguyên nhân nào | Luôn là lỗi |
| `emitter.send(...)` không ném exception | Write API hiện tại không báo lỗi | Client đã render/nhận trọn payload |

Class cụ thể:

~~~java
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
~~~

`AsyncRequestNotUsableException` kế thừa `IOException` và biểu thị response async không còn usable theo các cơ chế Spring/container. Không cần catch nó riêng cho mọi endpoint; cần hiểu nó khi đọc stacktrace và thiết kế cleanup.

### 3.3. Client-side close và server-side completion khác nhau

Browser `EventSource.close()` ngừng mở/reconnect ở phía browser. Server có thể chỉ biết sau write failure hoặc container error/completion. Trong khi đó, `emitter.complete()` là hành động **server-side** đánh dấu request hoàn tất; nó không có nghĩa "remote browser đã chủ động disconnect".

Tương tự, nếu proxy idle timeout đóng downstream nhưng vẫn giữ upstream một lúc, quá trình nhận biết có thể khác nhau giữa gateway và ứng dụng.

## 4. Heartbeat là một phần của thiết kế SSE

SSE hỗ trợ comment-only event:

~~~text
: heartbeat

~~~

Dòng bắt đầu bằng dấu `:` là comment trong SSE. Browser thường bỏ qua comment này thay vì tạo business message event. Spring cung cấp:

~~~java
emitter.send(SseEmitter.event().comment("heartbeat"));
~~~

Ý nghĩa:

- Tạo một lần write/flush định kỳ để có cơ hội phát hiện connection đã đóng.
- Giảm nguy cơ một số ingress/proxy cho rằng upstream response bị idle.
- Giúp đo tỷ lệ write failures và tuổi thọ stream.

Nhưng heartbeat không chứng minh mọi byte đã được browser xử lý; TCP/proxy buffers có thể khiến write thành công tạm thời dù downstream không còn hoạt động.

### 4.1. Ba thời gian cần chọn riêng

| Timeout | Ở đâu | Ghi chú |
| --- | --- | --- |
| Servlet async timeout | `new SseEmitter(timeoutMillis)` hoặc MVC config | Giới hạn async processing theo container/Spring |
| Proxy read/idle timeout | Nginx, ingress, CDN | Có thể đóng response nếu lâu không có dữ liệu |
| Client idle/reconnect | Browser, HTTP client, mobile app | Có thể tự hủy/reconnect tùy protocol |

Ví dụ `new SseEmitter(60_000L)` đặt timeout async 60 giây. Heartbeat mỗi 10 giây **không nhất thiết reset thời hạn async request**. Nếu stream phải sống lâu, cần chọn chính sách timeout/reconnection phù hợp thay vì chỉ gửi comment heartbeat.

### 4.2. Proxy buffering

Nginx có thể giữ dữ liệu ở buffer khiến browser không nhận heartbeat kịp thời dù Spring đã write. Với một số cấu hình, response có thể đặt:

~~~http
Content-Type: text/event-stream
Cache-Control: no-store
X-Accel-Buffering: no
~~~

`X-Accel-Buffering: no` là hint liên quan Nginx, **không phải chuẩn SSE của browser** và có thể bị upstream cấu hình bỏ qua. Cần test qua proxy thật và dùng cấu hình streaming/timeout phù hợp ở từng hop.

## 5. ResponseBodyEmitter, SseEmitter và callbacks

### 5.1. Đăng ký lifecycle trước khi publish emitter

~~~java
SseEmitter emitter = new SseEmitter(60_000L);
emitter.onTimeout(() -> cleanupOnce());
emitter.onError(error -> cleanupOnce());
emitter.onCompletion(() -> cleanupOnce());
return emitter;
~~~

Đây là fragment; `cleanupOnce()` phải thuộc connection state thực tế. Callback có thể xảy ra trên **container thread**, không phải thread controller. Multiple callbacks có thể xảy ra cho cùng một request.

Javadoc Spring 6.2:

- `onTimeout(Runnable)`: container báo async timeout.
- `onError(Consumer<Throwable>)`: container báo error async processing.
- `onCompletion(Runnable)`: container hoàn tất async request **vì bất kỳ lý do nào**, gồm network error và timeout.

**onCompletion là terminal cleanup, không phải detector riêng cho disconnect.**

### 5.2. Quy tắc then chốt: IOException từ emitter.send()

Tài liệu Spring MVC ghi rõ: khi `ResponseBodyEmitter.send(...)` ném `IOException` (ví dụ remote client đã rời đi), **ứng dụng không phải và không nên gọi `emitter.complete()` hay `emitter.completeWithError(exception)` chỉ vì lỗi ghi đó**.

Servlet container tự phát async error notification; Spring MVC tiếp nhận lỗi và thực hiện xử lý, có thể gồm ASYNC dispatch tới exception resolution. Ứng dụng cần **dừng nguồn phát và dọn tài nguyên do mình sở hữu**.

Đúng về nguyên tắc:

~~~java
try {
    emitter.send(SseEmitter.event().name("update").data(payload));
} catch (IOException writeFailure) {
    cleanupMySubscription();
    // KHÔNG gọi emitter.complete() / completeWithError(writeFailure).
}
~~~

Đây là fragment với `payload` và `cleanupMySubscription` từ ứng dụng. Điều này **khác** lỗi business tự phát hiện khi channel vẫn usable: trường hợp đó có thể dùng error SSE event hoặc `completeWithError` theo trạng thái response.

### 5.3. Không cố gửi lỗi thứ hai trên socket đã lỗi

Sai:

~~~java
try {
    emitter.send(event);
} catch (IOException ex) {
    emitter.send(SseEmitter.event()
            .name("error")
            .data("Connection lost"));
}
~~~

Connection có thể không còn usable; lần ghi thứ hai thường chỉ gây thêm exception. Không cố trả HTTP 500 JSON sau khi SSE đã bắt đầu, bởi status/headers có thể đã committed.

## 6. HTTP response committed là gì?

Servlet `HttpServletResponse` hỗ trợ:

~~~java
boolean committed = response.isCommitted();
~~~

Response **committed** khi HTTP status và headers đã được gửi khỏi phần response buffering để tới tầng output. Sau commit:

- Không thể rút lại status 200 đã phát và đổi thành 500/409/404 trong cùng response.
- Không thể gửi một response hoàn toàn mới với headers khác.
- `reset()` hoặc `resetBuffer()` sau commit có thể ném `IllegalStateException`.
- `sendError(...)` sau commit không thể sửa response hợp lệ; có thể thất bại hoặc tạo lỗi phụ tùy container.
- `@RestControllerAdvice`/`@ExceptionHandler` không thể tự biến các bytes SSE đã gửi thành body `application/problem+json`.

### 6.1. Timeline

~~~text
Controller returns SseEmitter
   |
Response headers prepared
   |
First event sent / flush occurs
   |
HTTP 200 + Content-Type are committed
   |
Later producer fails
   |
Cannot replace with HTTP 500 JSON on the same connection
~~~

Lưu ý `setStatus(200)` chưa chắc đã commit ngay; buffering và flush quyết định thời điểm. Đừng giả định controller return đồng nghĩa response committed; khi debug có thể kiểm `isCommitted()` nhưng vẫn cần tuân framework lifecycle.

### 6.2. Lỗi trước commit

Nếu controller đã biết request không hợp lệ/không được cấp quyền/job không tồn tại, hãy kiểm **trước khi tạo hoặc phát stream**:

~~~java
@GetMapping(path = "/events/{jobId}",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
SseEmitter events(@PathVariable String jobId) {
    jobService.verifyAccess(jobId);     // 401/403 nếu cần
    jobService.verifyExists(jobId);     // 404
    jobService.verifyStreamingState(jobId); // 409
    return streamService.subscribe(jobId);
}
~~~

Fragment này cần service methods được triển khai. Khi lỗi xảy ra trước commit, Spring `@ExceptionHandler` có thể trả status và JSON/ProblemDetail an toàn. Đây là lý do validation, auth và preconditions nên được giải quyết sớm.

### 6.3. Lỗi sau commit nhưng còn gửi được

Một business producer gặp lỗi nhưng SSE channel vẫn usable có thể phát **in-band error event**:

~~~text
event: app-error
data: {"code":"JOB_FAILED","message":"Không thể tiếp tục"}

~~~

Trong Java (fragment):

~~~java
emitter.send(SseEmitter.event()
        .name("app-error")
        .data(Map.of(
                "code", "JOB_FAILED",
                "message", "Không thể tiếp tục")));
emitter.complete();
~~~

HTTP status vẫn là 200 trước đó; frontend phải phân biệt **transport status** với **application-level event code**. Chỉ làm điều này khi có thể gửi; không dùng để chữa failed write hoặc đã unusable.

### 6.4. Lỗi I/O sau commit

Nếu write bị `IOException`:

1. Hủy scheduled tasks, unsub broker và giải phóng business resources.
2. Không cố phát JSON hoặc error SSE event.
3. Không gọi `complete()/completeWithError()` chỉ vì IOException từ `ResponseBodyEmitter.send`.
4. Để Servlet container/Spring hoàn tất request error lifecycle.
5. Ghi metric/log phù hợp, tránh một stacktrace ERROR cho từng browser đóng tab bình thường.

## 7. Cleanup idempotent và race conditions

Một session có thể bị timeout, onError, write failure, manual cancel, shutdown hoặc complete trong khoảng rất gần nhau. Những callbacks có thể chạy trên nhiều threads.

Sai:

~~~java
void cleanup() {
    registry.remove(id);
    future.cancel(false);
    subscription.close();
    activeCount.decrementAndGet();
}
~~~

Nếu chạy hai lần, activeCount bị trừ hai lần; có thể double-close hoặc xóa nhầm session khác cùng id.

Cách thiết kế:

~~~java
final AtomicBoolean closed = new AtomicBoolean(false);

void cleanup() {
    if (!closed.compareAndSet(false, true)) {
        return;
    }
    registry.remove(id, thisSession);
    if (future != null) future.cancel(false);
    subscription.close();
    activeCount.decrementAndGet();
}
~~~

Đây là fragment minh họa. Dùng **connection ID duy nhất**, `ConcurrentMap.remove(id, instance)` và exactly-once cleanup. Cần xử lý race `onCompletion` diễn ra **trước khi ScheduledFuture được gán**: setter lưu Future rồi kiểm `closed.get()` và cancel nếu đã đóng.

### 7.1. Những tài nguyên cần dọn

| Tài nguyên | Hành động |
| --- | --- |
| Map giữ SseEmitter/session | Remove đúng object/value |
| ScheduledFuture heartbeat | Cancel future của connection |
| Broker subscription | Unsubscribe theo SDK contract |
| Stream/file InputStream | Close bằng try-with-resources |
| DB cursor/transaction resources | Close tại ownership boundary; không giữ lâu không cần |
| Per-client queue/buffer | Clear references và có capacity giới hạn |
| Future background job | Cancel/cooperative interrupt nếu client không còn cần |
| MDC/ThreadLocal | Restore/clear trên worker thread tương ứng |
| Metrics active connections | Decrement một lần |
| Application scheduler | Chỉ shutdown khi application lifecycle kết thúc, không shutdown per client |

**Không lấy một shared executor rồi shutdown trong `onCompletion` của từng request**, vì như vậy sẽ ảnh hưởng các client khác.

### 7.2. Các race cần kiểm thử

- Timeout callback xảy ra ngay khi timer task đang `send`.
- Write failure kích hoạt container `onError` và cuối cùng `onCompletion`.
- Future vừa schedule nhưng callback cleanup đã chạy.
- Client reconnect tạo session mới cùng logical user; cleanup session cũ xóa nhầm session mới.
- App shutdown đồng thời với client disconnect.
- Broker callback vào queue trước khi session closed nhưng chạy sau closed.

Kiểm `closed` trước mỗi send và dùng per-connection state; không lock toàn cục qua network write. Các operations đang chạy có thể cần cancellation/cooperative stopping riêng.

## 8. SSE reconnect và Last-Event-ID

Browser `EventSource` thường tự reconnect sau một số lỗi connection. Khi có SSE event id:

~~~text
id: 102
event: update
data: {"percent":70}

~~~

browser có thể gửi `Last-Event-ID: 102` khi reconnect. Server **chỉ replay events** nếu có storage/sequence history thực sự; một map emitter in-memory không đảm bảo durability.

Nếu yêu cầu không mất sự kiện, cần:

- Event IDs tăng/độc nhất theo stream contract.
- Durable event store hoặc message broker retention.
- Reconnect với cursor đã được xác thực.
- Replay từ sequence tiếp theo, xử lý duplicate/idempotency.
- Retention/window và behavior khi cursor quá cũ.

Nếu chỉ gửi progress giá trị mới nhất, có thể chọn **latest-state snapshot sau reconnect** thay vì replay toàn bộ.

Phía frontend phải gọi `eventSource.close()` khi unmount/không cần stream để tránh reconnect mãi. Server vẫn cần cleanup khi phát hiện disconnect, không chỉ dựa vào frontend tuân thủ.

## 9. Dự án chạy được: SSE + DeferredResult

Dự án dùng Java 17, Spring Boot 3.5.0. Có:

- `GET /api/stream`: mở SSE, gửi heartbeat mỗi 10 giây.
- `GET /api/once`: DeferredResult được hoàn tất sau 50 ms.
- `GET /api/stream-count`: đếm active subscriptions để học/dễ test.
- Lifecycle cleanup onCompletion/onTimeout/onError, AtomicBoolean exactly-once.
- Khi `send()` ném IOException, chỉ dọn resources; không gọi emitter.complete/error.
- Một `ScheduledExecutorService` dùng chung làm Spring bean, shutdown lúc app tắt.

### 9.1. Cấu trúc

~~~text
async-disconnect-demo/
├── pom.xml
└── src/
    ├── main/java/demo/AsyncDisconnectApplication.java
    └── test/java/demo/AsyncDisconnectTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-disconnect-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.3. AsyncDisconnectApplication.java

Đặt toàn bộ code vào **một file** `src/main/java/demo/AsyncDisconnectApplication.java`. Một top-level public class; các class còn lại package-private. Demo không có database, không có login/security và không có business broker.

~~~java
package demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class AsyncDisconnectApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDisconnectApplication.class, args);
    }
}

@Configuration
class SchedulerConfig {
    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService scheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}

@Service
class StreamService {
    private static final Logger LOG =
            LoggerFactory.getLogger(StreamService.class);

    private final ScheduledExecutorService scheduler;
    private final ConcurrentMap<String, Connection> connections =
            new ConcurrentHashMap<>();

    StreamService(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    SseEmitter subscribe() {
        String id = UUID.randomUUID().toString();
        SseEmitter emitter = new SseEmitter(60_000L);
        Connection connection = new Connection(id, emitter);
        connections.put(id, connection);

        emitter.onCompletion(() -> close(connection, "completion"));
        emitter.onTimeout(() -> close(connection, "timeout"));
        emitter.onError(ex -> {
            LOG.info("stream_error id={} kind={}",
                    id, ex.getClass().getSimpleName());
            close(connection, "container-error");
        });

        try {
            ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
                    () -> heartbeat(connection),
                    1, 10, TimeUnit.SECONDS);
            connection.setFuture(future);
        } catch (RuntimeException ex) {
            close(connection, "scheduler-failed");
            throw ex; // Chưa trả emitter, HTTP error handling còn cơ hội.
        }
        return emitter;
    }

    int activeCount() {
        return connections.size();
    }

    private void heartbeat(Connection connection) {
        if (connection.closed.get()) {
            return;
        }
        try {
            // SSE comment, browser không dispatch business message event.
            connection.emitter.send(
                    SseEmitter.event().comment("heartbeat"));
        } catch (IOException ioFailure) {
            // Không complete()/completeWithError() sau write IOException.
            LOG.info("stream_write_failed id={} kind={}",
                    connection.id,
                    ioFailure.getClass().getSimpleName());
            close(connection, "write-failure");
        } catch (IllegalStateException noLongerUsable) {
            close(connection, "not-usable");
        } catch (RuntimeException unexpected) {
            LOG.warn("stream_producer_failed id={} kind={}",
                    connection.id,
                    unexpected.getClass().getSimpleName());
            close(connection, "producer-failure");
        }
    }

    private void close(Connection connection, String reason) {
        if (!connection.closed.compareAndSet(false, true)) {
            return;
        }
        connections.remove(connection.id, connection);
        ScheduledFuture<?> f = connection.future;
        if (f != null) {
            f.cancel(false);
        }
        LOG.info("stream_closed id={} reason={}", connection.id, reason);
    }

    @PreDestroy
    void cleanupOnShutdown() {
        for (Connection connection : connections.values()) {
            close(connection, "shutdown");
        }
        // Spring hủy scheduler bean; không shutdown cho mỗi client.
    }

    private static final class Connection {
        final String id;
        final SseEmitter emitter;
        final AtomicBoolean closed = new AtomicBoolean();
        volatile ScheduledFuture<?> future;

        Connection(String id, SseEmitter emitter) {
            this.id = id;
            this.emitter = emitter;
        }

        void setFuture(ScheduledFuture<?> scheduled) {
            this.future = scheduled;
            if (closed.get()) {
                scheduled.cancel(false);
            }
        }
    }
}

@RestController
class AsyncController {
    private final StreamService streams;
    private final ScheduledExecutorService scheduler;

    AsyncController(StreamService streams,
                    ScheduledExecutorService scheduler) {
        this.streams = streams;
        this.scheduler = scheduler;
    }

    @GetMapping(path = "/api/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> stream() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Accel-Buffering", "no")
                .body(streams.subscribe());
    }

    @GetMapping(path = "/api/once",
                produces = MediaType.APPLICATION_JSON_VALUE)
    DeferredResult<ResponseEntity<Map<String, String>>> once() {
        DeferredResult<ResponseEntity<Map<String, String>>> result =
                new DeferredResult<>(2_000L);

        ScheduledFuture<?> future = scheduler.schedule(
                () -> result.setResult(
                        ResponseEntity.ok(Map.of("state", "done"))),
                50, TimeUnit.MILLISECONDS);

        result.onCompletion(() -> future.cancel(false));
        result.onError(error -> future.cancel(false));
        result.onTimeout(() -> {
            future.cancel(false);
            result.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(Map.of("code", "WAIT_TIMEOUT")));
        });
        return result;
    }

    @GetMapping("/api/stream-count")
    Map<String, Integer> count() {
        return Map.of("activeConnections", streams.activeCount());
    }
}
~~~

### 9.4. Vì sao implementation xử lý được race?

- `ConcurrentMap` dùng id riêng cho mỗi connection.
- `AtomicBoolean.compareAndSet(false,true)` bảo đảm cleanup **exactly once**.
- `connections.remove(id, connection)` không xóa nhầm object khác cùng key.
- `setFuture` kiểm lại closed vì timeout có thể đến trước khi Future được gán.
- Các callbacks chỉ đóng **owned scheduled task**, không shutdown global scheduler.
- Khi send ném IOException, không chủ động gọi `complete()` hay `completeWithError()`; Spring/container quản lý async error.
- Timeout và error callbacks có thể ở thread khác; state/registry được thiết kế thread-safe.
- `SseEmitter(60_000L)` có timeout 60 giây; heartbeat không nhất thiết kéo dài timeout này.

**Giới hạn demo:** Một ScheduledFuture cho mỗi connection tốn scheduling overhead nếu rất nhiều clients; production có thể dùng shared heartbeat loops hoặc chiến lược khác. Registry in-memory mất khi restart, không đảm bảo replay. Mọi endpoint demo đều public, cần authentication/authorization và quota nếu dùng dữ liệu thật. `stream-count` nên là metric/admin endpoint được bảo vệ.

### 9.5. Chạy và quan sát

Từ thư mục Maven:

~~~bash
mvn spring-boot:run
~~~

Terminal thứ hai:

~~~bash
curl -N -i http://localhost:8080/api/stream
~~~

`-N` làm curl không buffer output, thuận tiện quan sát stream. Response headers có thể gồm:

~~~http
HTTP/1.1 200
Content-Type: text/event-stream
Cache-Control: no-store
X-Accel-Buffering: no
~~~

Sau khoảng một giây rồi mỗi mười giây:

~~~text
:heartbeat

:heartbeat

~~~

Mở terminal khác:

~~~bash
curl -s http://localhost:8080/api/stream-count
~~~

Ví dụ khi đang có một subscription:

~~~json
{"activeConnections":1}
~~~

Nhấn Ctrl+C ở client. Server **có thể chưa ngay lập tức biết**; sau write/timeout callbacks, registry sẽ được dọn và count có thể về 0:

~~~json
{"activeConnections":0}
~~~

Đây là kết quả ví dụ, không phải cam kết timing chính xác. Trong production cần quan sát proxy behavior, TCP buffering, heartbeat interval, timeouts và số active subscriptions thật.

### 9.6. Browser EventSource

~~~javascript
const source = new EventSource("/api/stream");

source.onopen = () => {
  console.log("SSE opened");
};
source.onerror = () => {
  console.log("Disconnected or reconnecting");
};

function stop() {
  source.close();
}
~~~

Demo chỉ gửi SSE **comments** nên browser không nhận business message events. Nếu ứng dụng cần event nghiệp vụ, gửi `event: update` và data phù hợp, đăng ký listener tương ứng. Client phải gọi `close()` khi không còn cần stream để không reconnect mãi.

### 9.7. Một DeferredResult có kết quả một lần

~~~bash
curl -i http://localhost:8080/api/once
~~~

Kết quả tương đương:

~~~json
{"state":"done"}
~~~

Sau khoảng 50ms cộng overhead, MVC redispatch kết quả. Nếu request timeout trước khi task chạy, timeout callback cancel Future và có thể set HTTP 503 theo chính sách demo; thực tế race/Servlet container default handling cần được kiểm thử. `future.cancel(false)` sau khi Future đã hoàn tất không gây hại.

## 10. MockMvc tests

File `src/test/java/demo/AsyncDisconnectTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDisconnectTest {
    @Autowired MockMvc mvc;

    @Test
    void deferredResultCompletesViaAsyncDispatch() throws Exception {
        MvcResult initial = mvc.perform(get("/api/once"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("done"));
    }

    @Test
    void sseStartsAsyncWithStreamingHeaders() throws Exception {
        MvcResult result = mvc.perform(get("/api/stream"))
            .andExpect(status().isOk())
            .andExpect(request().asyncStarted())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().string(
                    "X-Accel-Buffering", "no"))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_TYPE,
                    containsString("text/event-stream")))
            .andReturn();

        assertTrue(result.getRequest().isAsyncStarted());
    }

    @Test
    void countEndpointExposesNumericValue() throws Exception {
        mvc.perform(get("/api/stream-count"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.activeConnections").isNumber());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

MockMvc kiểm MVC asyncStarted, asyncDispatch và HTTP headers. Nó **không giả lập TCP disconnect một cách đầy đủ**. Với `SseEmitter`, test `andReturn()` khi asyncStarted không đồng nghĩa stream đã complete; phải thiết kế timeout/lifecycle cleanup và nếu cần dùng integration tests với embedded Tomcat và HTTP socket thật.

## 11. StreamingResponseBody: xử lý lỗi giữa download

Với file download lớn, Spring MVC có `StreamingResponseBody`:

~~~java
@GetMapping("/download")
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = storage.open("report.csv")) {
            input.transferTo(output);
            output.flush();
        }
    };
}
~~~

Đây là fragment, cần `InputStream`, `StreamingResponseBody` imports và `storage` service thực. Nếu OutputStream ghi thất bại do client disconnect:

- `try-with-resources` giúp đóng InputStream.
- Không tự viết JSON `{"error":"..."}` lên output đã lỗi.
- Log/metric ngắn với classification phù hợp.
- Stop producer và hủy resources/cursor còn phụ thuộc download.

Nếu server đã gửi 5MB của file 10MB rồi lỗi, HTTP headers/status có thể đã committed. Client chỉ nhận file không đầy đủ, không nhận được một HTTP 500 mới. Nếu giao thức yêu cầu resume/integrity, cần `Content-Length` đúng, range requests, ETag/checksum và các semantics riêng.

**Blocking I/O:** StreamingResponseBody không làm JDBC/file/socket writes tự trở thành non-blocking. Cần bounded task executor, timeouts, quotas và xử lý slow clients.

## 12. DeferredResult: timeout và cancellation

`DeferredResult<T>` thể hiện **một** async result. Trong callback:

~~~java
boolean accepted = result.setResult(value);
if (!accepted) {
    // Request đã timeout/complete hoặc result đã được set.
    // Dừng công việc không còn cần thiết.
}
~~~

Đây là fragment với result/value xác định trong ứng dụng. Không phát kết quả nhiều lần; không tin timeout callback luôn thắng task đã sắp kết thúc.

Ví dụ lifecycle:

~~~java
DeferredResult<String> response = new DeferredResult<>(5_000L);
response.onCompletion(() -> cancelJob());
response.onError(error -> cancelJob());
response.onTimeout(() -> {
    cancelJob();
    response.setErrorResult(new TimeoutException("Expired"));
});
~~~

Fragment này cần `cancelJob()` và import `TimeoutException`. `Future.cancel(true)` chỉ gửi tín hiệu interrupt nếu task hỗ trợ; không bảo đảm thread dừng. Với job dài hơn timeout HTTP, cân nhắc trả `202 Accepted + jobId` rồi client polling/SSE, thay vì giữ kết nối đến khi business job hoàn tất.

## 13. Thiết kế lỗi trước và sau commit

| Thời điểm | Ví dụ lỗi | Hướng xử lý |
| --- | --- | --- |
| Trước khi tạo stream | Invalid input, 401/403, 404, business 409 | Trả HTTP status + JSON/ProblemDetail an toàn |
| Sau khi stream bắt đầu nhưng channel usable | Job failed, business task stopped | Gửi SSE `app-error` event hoặc kết thúc theo contract |
| Sau committed + write IOException | Broken pipe, connection reset | Không viết thêm, dọn producer, để container/Spring xử lý |
| Sau committed + internal producer failure | Serialization/business exception | In-band error nếu usable; ngược lại log/cleanup/close |
| DeferredResult chưa committed | Worker exception | `setErrorResult`, MVC exception resolver |
| Stream hoàn thành bình thường | Business completed | `emitter.complete()` và onCompletion cleanup |
| Async timeout | Deadline exceeded | onTimeout cleanup, framework timeout behavior hoặc result policy |
| Reverse proxy closes connection | Idle timeout/network | Có thể phát hiện ở heartbeat/send tiếp theo |

Phân biệt:

- **HTTP transport status** được chốt khi response committed.
- **Event-level status** có thể thay đổi trong payload SSE vì đó là dữ liệu ứng dụng.
- **Business job state** có thể tiếp tục sau khi HTTP stream kết thúc, tùy nghiệp vụ; hủy SSE không nhất thiết hủy durable job.

Không coi `@ExceptionHandler` là “bộ sửa 500 cho mọi tình huống”, vì nó không thể đảo ngược bytes đã phát.

## 14. Metrics và logging cho streaming

Nên ghi khi mở và đóng:

~~~text
stream_open connectionId=<id> endpoint=/api/stream
stream_close connectionId=<id> reason=timeout lifetimeMs=60000
stream_write_failed connectionId=<id> kind=AsyncRequestNotUsableException
~~~

Đây là log mẫu, không phải output cố định.

Các metrics hữu ích:

- Active SSE connections (gauge).
- Opened/closed total theo **reason nhóm hữu hạn**.
- Stream lifetime histogram.
- IO write failures theo endpoint/reason nhóm nhỏ.
- Timeout rate, reconnect rate và heartbeat latency.
- Scheduler queue/executor saturation.
- Cleanup failures và broker subscription backlog.

Không gắn userId/requestId/connectionId vào Prometheus low-cardinality labels. Có thể dùng correlation ID trong log/trace với privacy review. Đừng log token, cookie, email hoặc raw request body để debug disconnect.

Một số gateways như Nginx log **499** cho client closed request; đây là ký hiệu **nonstandard, riêng proxy**, không phải HTTP status Spring MVC cần trả cho client đã disconnect.

Lỗi "Broken pipe" do client ngắt thông thường thường không đáng log stacktrace ERROR mỗi lần; theo dõi bằng counter và log ở mức phù hợp. Nếu failures tăng bất thường theo deployment mới, cần điều tra proxy/network/timeout và code.

## 15. Slow client, backpressure và production capacity

Kênh SSE có thể giữ hàng nghìn kết nối. Nếu producer sinh events nhanh hơn tốc độ mạng client nhận, queue tăng, RAM tăng và threads có thể bị block.

Các khuyến nghị:

1. Giới hạn connections trên instance/tenant/user theo trust và authentication policy.
2. Chọn bounded buffers/queues, tránh tích tụ vô hạn per-client.
3. Với progress/latest state, ưu tiên **coalescing**: giữ giá trị mới nhất thay vì mọi event cũ.
4. Với dữ liệu bắt buộc không mất, dùng durable log/replay cursor.
5. Chọn scheduler/thread pool có metrics và shutdown.
6. Đặt heartbeat hợp lý với proxy idle read timeout.
7. Dọn broker subscriptions và Future ngay lúc lifecycle kết thúc.
8. Không giữ database transaction, file handle hoặc ServletRequest suốt stream nếu không cần.
9. Chạy soak tests với nhiều connections, slow readers và disconnect storm.
10. Tách HTTP stream lifetime khỏi business job lifetime; không hủy durable job chỉ vì browser đóng tab trừ khi nghiệp vụ yêu cầu.

### 15.1. Nginx minh họa

~~~nginx
location /api/stream {
    proxy_pass http://backend:8080;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
~~~

Đây là fragment, cần config TLS, host validation, auth và routing khác. `proxy_read_timeout` thường đo khoảng idle giữa reads từ upstream, không phải tổng stream lifetime. Với SSE hãy test qua proxy public thật, không chỉ backend.

Nếu upstream đã gửi HTTP headers mà sau đó lỗi, gateway cũng không thể phát thêm một HTTP 502 response mới trong cùng stream đã bắt đầu; thường phải đóng connection. Client có thể reconnect theo SSE semantics.

## 16. Câu hỏi luyện tập

**Bài 1:** Browser đóng SSE connection khi stream không có event trong 2 phút. Tại sao Servlet API không đảm bảo phát hiện ngay? Nên thiết kế heartbeat, timeout và proxy như thế nào?

**Bài 2:** `SseEmitter.send()` ném `IOException: Broken pipe`. Theo Spring, có nên gọi `completeWithError` ngay trong catch không? Tại sao cần dọn scheduled tasks nhưng để container hoàn tất lifecycle?

**Bài 3:** Có onError, onTimeout và onCompletion cùng gọi cleanup. Viết code sử dụng `AtomicBoolean.compareAndSet` để tránh giảm active counter nhiều lần.

**Bài 4:** Response SSE đã gửi status 200 cùng hai events. Một business exception xuất hiện. Tại sao `@RestControllerAdvice` không thể biến thành HTTP 500? Khi nào gửi `event: app-error`?

**Bài 5:** Một stream giữ broker subscription và scheduled heartbeat. Hãy vẽ lifecycle của hai resources khi client disconnect, timeout, shutdown và normal complete.

**Bài 6:** Một `DeferredResult` bị timeout nhưng worker gọi `setResult` sau đó. Đọc boolean return và thiết kế cancellation phù hợp.

**Bài 7:** Download file 100MB bị ngắt ở byte thứ 1 triệu. Làm sao đóng InputStream? Vì sao không thể gửi JSON lỗi sau khi đã truyền file bytes?

**Bài 8:** Heartbeat SSE comment khác với event business như thế nào? Browser có tạo message event từ comment không?

**Bài 9:** Proxy buffer SSE khiến client không thấy dữ liệu. Nêu cách kiểm `X-Accel-Buffering`, `proxy_buffering`, timeouts và TCP socket behavior.

**Bài 10:** Thiết kế metrics stream.active, stream.closed.total{reason} và stream.lifetime, tránh dùng connectionId làm metric label.

**Bài 11:** EventSource reconnect nhưng client cần không mất message. Hãy thiết kế event IDs và replay history; nếu không có durable history thì contract cần nói gì?

**Bài 12:** Viết MockMvc test cho DeferredResult asyncStarted/asyncDispatch và đề xuất một test integration socket disconnect mà MockMvc không thể mô phỏng đầy đủ.

## 17. Checklist trước khi triển khai

- [ ] Input, authentication, authorization và business preconditions được kiểm tra trước khi stream commit.
- [ ] Hiểu và định nghĩa được async timeout, proxy idle timeout, client reconnect policy.
- [ ] Có heartbeat định kỳ nhưng không giả định phát hiện disconnect tức thời.
- [ ] Đăng ký onCompletion/onTimeout/onError khi tạo emitter.
- [ ] Cleanup once dùng thread-safe state, cancel futures, unsubscribe broker và gỡ registry.
- [ ] IOException từ ResponseBodyEmitter.send không bị application double-complete.
- [ ] Exception sau committed không cố đổi HTTP status hoặc gửi JSON response mới.
- [ ] Event-level error protocol rõ ràng nếu muốn báo lỗi trong SSE vẫn usable.
- [ ] Có limits per-user/per-instance, bounded buffers và slow-client policy.
- [ ] Không shutdown shared executor theo request.
- [ ] Có resource cleanup khi application shutdown.
- [ ] Có metrics active/lifetime/disconnect/timeout và alert leak.
- [ ] Có tests streaming headers, MVC async lifecycle, concurrent callbacks, socket disconnect và proxy behavior.
- [ ] Frontend EventSource đóng khi không cần và xử lý reconnect/event replay có chủ đích.

## 18. Ghi nhớ

- **Servlet không cung cấp callback ngay lập tức, đáng tin cậy cho remote disconnect.** Write failure hoặc container async error notification thường là cách phát hiện.
- **Heartbeat SSE** vừa giữ stream có hoạt động vừa tạo cơ hội phát hiện kết nối lỗi.
- **onCompletion** xảy ra vì nhiều lý do, nên dùng làm terminal cleanup; **onTimeout/onError** cung cấp thêm dấu hiệu chứ không phải bằng chứng chắc chắn của client cancellation.
- Khi **SseEmitter.send ném IOException**, dừng producer và cleanup owned resources; **không tự gọi complete hoặc completeWithError** chỉ vì lỗi ghi đó.
- Khi **HTTP response committed**, không thể thay status/headers hay trả JSON error mới trong cùng response.
- Lỗi business khi SSE còn usable có thể truyền qua **SSE app-error event**; lỗi transport thì dừng ghi.
- **Cleanup phải idempotent** vì callbacks có thể cạnh tranh; mọi Future, subscription và buffer có owner rõ.
- `DeferredResult`, `StreamingResponseBody` và MVC async filters/interceptors đều cần timeout/cancellation đúng ranh giới.
- MockMvc kiểm MVC lifecycle, nhưng **disconnect cần integration test với socket/proxy thật**.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, ResponseBodyEmitter, SseEmitter, StreamingResponseBody, disconnects.
- [Spring Framework 6.2 — ResponseBodyEmitter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html): send, complete, completeWithError và lifecycle callbacks.
- [Spring Framework 6.2 — SseEmitter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Spring Framework 6.2 — AsyncRequestNotUsableException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/AsyncRequestNotUsableException.html).
- [Spring Framework 6.2 — DeferredResult](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html).
- [Jakarta Servlet 6.0 — ServletResponse](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse): isCommitted, reset và resetBuffer.
- [HTML Living Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): EventSource, SSE framing, reconnect.
