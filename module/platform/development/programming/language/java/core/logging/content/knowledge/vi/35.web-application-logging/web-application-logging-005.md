# Request duration trong Java Web Logging

## 1. Request duration là gì?

**Request duration** là khoảng thời gian mà hệ thống ghi nhận để xử lý một HTTP request, tính từ **mốc bắt đầu được xác định rõ** đến **mốc kết thúc được xác định rõ**. Ví dụ, một dịch vụ Java nhận `GET /api/orders/42`, thực hiện xác thực, gọi database, xây response và trả HTTP 200. Nếu thời gian từ đầu đến cuối phạm vi đo là 127,4 ms, một log tổng kết có thể là:

```text
2026-11-10T10:15:20.123Z INFO event=http.request.completed method=GET route=/api/orders/{id} status=200 duration_ms=127.400 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

Ở đây `duration_ms` là **độ dài một khoảng thời gian**, không phải timestamp. Một dòng như `duration_ms=127.400` chỉ có nghĩa khi biết **điểm bắt đầu, điểm kết thúc và phạm vi instrumentation**. Ví dụ một filter trong ứng dụng có thể không bao gồm thời gian kết nối TLS ở load balancer hoặc thời gian client tải toàn bộ body response.

Trong nhóm **Logging trong ứng dụng web**, đo request duration giúp:
- Phát hiện endpoint chậm hoặc đột ngột tăng độ trễ.
- Đối chiếu request nhanh/chậm với HTTP status, trace, service, version, pod.
- Điều tra các request timeout, retry hoặc error.
- Truy dấu thời gian bị tiêu tốn ở authentication, controller, downstream HTTP, database và queue.
- Xác minh tác động của release/cấu hình mới lên trải nghiệm người dùng.

**Không nên chỉ dựa vào một log của một request để kết luận hiệu suất hệ thống.** Logs tốt cho điều tra từng request, còn metrics về latency distribution, p95/p99 và throughput thường phù hợp hơn để giám sát toàn bộ lưu lượng.

## 2. Một request có nhiều “thời gian xử lý” khác nhau

```text
Client          Proxy/Load balancer        Java Server            Database
  |---- DNS/TCP/TLS ---->|
  |---- request bytes -->|---- forward ---->|
  |                      |                   |-- auth/filter -----|
  |                      |                   |-- controller ------|
  |                      |                   |-- DB query ----------------->|
  |                      |                   |<--------- result ------------|
  |                      |                   |-- serialize/write |
  |<--- response bytes --|<---- response ----|
```

Có ít nhất bốn phạm vi đo cần phân biệt:

| Loại duration | Điểm bắt đầu → điểm kết thúc | Bao gồm gì / bỏ qua gì |
| --- | --- | --- |
| **Client-perceived latency** | Client bắt đầu gọi → client nhận kết quả mong muốn | Có thể gồm DNS, connect, TLS, network, redirect, download, retry; phụ thuộc cách client đo |
| **Proxy/edge duration** | Proxy bắt đầu nhận → proxy hoàn tất xử lý theo định nghĩa của nó | Có thể gồm chờ upstream và chuyển response; không trùng tuyệt đối server duration |
| **HTTP server request duration** | Điểm bắt đầu instrumentation trong server → điểm kết thúc tương ứng | Thường gồm một phần filter/framework/controller/downstream; không có DNS/TLS client |
| **Handler/controller duration** | Vào method handler → method trả về/kết thúc | Hẹp hơn end-to-end request; có thể bỏ auth, filter, serialization hoặc async completion |

Ví dụ các số đo sau **có thể đều đúng**:

```text
client_e2e_ms=450.0
proxy_ms=370.0
server_request_ms=325.0
controller_ms=280.0
database_ms=210.0
```

Không cộng chúng lại: nhiều khoảng **lồng nhau**, không phải các pha độc lập nối tiếp. Tránh giả định `server_request_ms + db_ms` bằng request duration — DB đã nằm trong phạm vi xử lý request nếu lời gọi DB xảy ra đồng bộ trong request.

**Bước đầu tiên khi chẩn đoán “duration sai”: xác định instrumentation đang đo chính xác đoạn nào.**

## 3. Đơn vị đo và timestamp khác duration

Thời gian bắt đầu một sự kiện có thể dùng `Instant.now()` để ghi timestamp cho log. Nhưng đo **elapsed time** nên dùng clock đơn điệu như `System.nanoTime()`:

```java
long startedAtNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startedAtNanos;
    double durationMs = elapsedNanos / 1_000_000.0;
    log.info("duration_ms={}", durationMs);
}
```

Đây là **đoạn tích hợp trong ứng dụng đã có `log` và `doWork()`**, không phải chương trình Java độc lập. `System.nanoTime()` thích hợp để tính chênh lệch hai lần đọc trong cùng tiến trình JVM. Giá trị tuyệt đối của nó có origin tùy ý, **không phải Unix timestamp**, không dùng để so hai process.

Tại sao tránh `System.currentTimeMillis()` để đo duration?

- Wall-clock có thể được NTP điều chỉnh, đôi khi bị nhảy tiến/lùi.
- Độ phân giải và lịch điều chỉnh đồng hồ có thể làm số đo ngắn thiếu ổn định.
- Timestamp wall-clock hữu ích để định vị một sự kiện trên timeline, **không thay thế monotonic elapsed clock**.

Ví dụ tính sai:

```java
long start = System.currentTimeMillis();
// ... công việc diễn ra ...
long duration = System.currentTimeMillis() - start;
```

Khi đồng hồ hệ thống nhảy lùi, duration có thể âm; khi chỉnh tiến, duration có thể tăng ảo. Thay bằng `nanoTime` cho đo khoảng thời gian. Không lấy `Instant.now().toEpochMilli()` làm clock đơn điệu.

### 3.1. Dùng đúng đơn vị

| Giá trị | Ý nghĩa | Chuyển đổi |
| --- | --- | --- |
| `ns` | Nanosecond | 1 ms = 1.000.000 ns |
| `µs` | Microsecond | 1 ms = 1.000 µs |
| `ms` | Millisecond | 1 s = 1.000 ms |
| `s` | Second | 1 s = 1.000.000.000 ns |

Nếu duration là `123_456_789 ns` thì:
- `TimeUnit.NANOSECONDS.toMillis(...)` trả **123 ms** (cắt phần dư).
- Chia cho `1_000_000.0` trả **123.456789 ms** (dạng số thực).
- `Duration.ofNanos(...).toMillis()` cũng trả **123 ms**.

Không nên đặt field `duration_ms` nhưng lại ghi nanoseconds. Nếu cần phân tích rất ngắn, giữ giá trị số nguyên `duration_ns` hoặc chuẩn hóa theo schema backend, tránh trộn nhiều đơn vị vào cùng một field.

## 4. Ví dụ Java 17+ chạy độc lập với kết quả xác định

Chương trình dưới dùng **clock giả được inject** để minh họa phép tính chính xác mà không phụ thuộc tốc độ máy. Trong production, thay clock giả bằng `System::nanoTime`. Mục tiêu là hiểu cách ghi **một summary log khi xử lý kết thúc**, kể cả khi work ném exception.

Lưu thành `RequestDurationDemo.java`:

```java
import java.util.Locale;
import java.util.function.LongSupplier;

public class RequestDurationDemo {
    private static final class FakeNanoClock implements LongSupplier {
        private final long[] ticks = {
                1_000_000_000L, 1_023_450_000L,
                2_000_000_000L, 2_004_500_000L
        };
        private int index;

        @Override
        public long getAsLong() {
            return ticks[index++];
        }
    }

    private static void handle(String method,
                               String route,
                               int status,
                               LongSupplier clock,
                               Runnable work) {
        long startedAt = clock.getAsLong();
        try {
            work.run();
        } finally {
            long nanos = clock.getAsLong() - startedAt;
            double millis = nanos / 1_000_000.0;
            System.out.printf(Locale.ROOT,
                    "event=http.request method=%s route=%s "
                  + "status=%d duration_ms=%.3f%n",
                    method, route, status, millis);
        }
    }

    public static void main(String[] args) {
        LongSupplier clock = new FakeNanoClock();

        handle("GET", "/api/orders/{id}", 200, clock, () -> {});

        try {
            handle("POST", "/api/orders", 500, clock,
                    () -> { throw new IllegalStateException("simulated"); });
        } catch (IllegalStateException ex) {
            System.out.println("handled=IllegalStateException");
        }
    }
}
```

Chạy trên JDK 17 hoặc cao hơn:

```bash
javac --release 17 RequestDurationDemo.java
java RequestDurationDemo
```

Stdout chính xác:

```text
event=http.request method=GET route=/api/orders/{id} status=200 duration_ms=23.450
event=http.request method=POST route=/api/orders status=500 duration_ms=4.500
handled=IllegalStateException
```

**Giải thích:**
1. Lần thứ nhất hai mốc là 1.000.000.000 ns và 1.023.450.000 ns → chênh **23,45 ms**.
2. Lần thứ hai hai mốc là 2.000.000.000 ns và 2.004.500.000 ns → chênh **4,5 ms**.
3. `finally` vẫn ghi duration khi công việc ném exception; sau đó exception đi tới `catch` ở main.
4. Trong chương trình minh họa, `status` **được truyền vào** để kiểm tra formatting; nó không tự suy ra trạng thái HTTP thật. Một web filter phải lấy status từ response/framework.
5. Fake clock khiến output xác định, **không phải benchmark**. Trong ứng dụng thật không ghi stdout thủ công theo mẫu này; dùng logger phù hợp.

Chú ý: không được giả định bất cứ `finally` nào cũng chạy nếu JVM bị kill cưỡng bức, mất điện hoặc tiến trình crash ở mức native. Và vì `finally` có thể ghi lỗi trước khi HTTP error handler quyết định status cuối, phải hiểu lifecycle framework.

## 5. Ghi một request summary log có cấu trúc

Một bản ghi tốt nên có các trường được kiểm soát:

```json
{
  "event": "http.request.completed",
  "timestamp": "2026-11-10T10:15:20.123Z",
  "service.name": "order-service",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "duration_ms": 127.4,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-42",
  "outcome": "SUCCESS"
}
```

Đây là **schema mẫu**, không phải tên trường được mọi backend tự động nhận. Nếu dùng OpenTelemetry semantic conventions, nên đối chiếu tên trường và đơn vị theo phiên bản đang sử dụng (ví dụ `http.request.method`, `http.route` và `http.response.status_code`). Khi thêm structured logging, test end-to-end encoder → collector → backend, tránh vừa giữ tên cũ vừa tạo bản ghi duplicate.

Các trường cần lưu ý:

- **`method`**: HTTP method, thường là số lượng giá trị thấp.
- **`route`**: **route template** như `/api/orders/{id}`, không phải raw URL có ID/token/query string. Nếu không match route, dùng nhóm `unmatched` hay `not_found`.
- **`status`**: mã trạng thái phản hồi **tại thời điểm instrumentation hoàn tất**; không nhất thiết là status cuối cùng nếu error dispatch diễn ra sau.
- **`duration_ms`**: một số nguyên hoặc số thập phân rõ đơn vị và nơi đo; không để text `"127 ms"` vào field số.
- **`trace_id` / `span_id`**: giúp liên kết log với trace có sẵn, không tự sinh trace nếu chưa có instrumentation.
- **`request_id`**: ID do hệ thống kiểm soát, không phải access token/session ID.
- **`outcome/error_type`**: mã/loại lỗi đã chuẩn hóa, không cần in exception message chứa dữ liệu bí mật.
- **`instance/environment/version`**: giúp phân biệt các pod hoặc phiên bản khi một endpoint có độ trễ khác nhau.

Không đưa mật khẩu, Authorization/Cookie, raw query, body, user token hay PII không cần thiết vào summary log. Cần đặc biệt thận trọng với `request.getRequestURI()` vì **đường dẫn cũng có thể chứa mã bí mật**.

## 6. Spring Boot 3: đo request đồng bộ bằng OncePerRequestFilter

Trong ứng dụng **Spring Boot 3 + Spring MVC/Jakarta Servlet + SLF4J**, có thể minh họa điểm đặt đồng hồ ở một filter. Ví dụ dưới đây **chỉ ghi summary cho lượt request đồng bộ**. Nó cố tình không tuyên bố đo trọn thời gian cho Servlet async — trường hợp đó sẽ được xử lý riêng ở phần sau.

File `src/main/java/com/example/logging/SyncRequestDurationFilter.java`:

```java
package com.example.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public final class SyncRequestDurationFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(SyncRequestDurationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        boolean exceptionEscaped = false;

        try {
            chain.doFilter(request, response);
        } catch (IOException | ServletException | RuntimeException | Error ex) {
            exceptionEscaped = true;
            throw ex;
        } finally {
            if (!request.isAsyncStarted()) {
                long elapsed = System.nanoTime() - started;
                long durationMs = TimeUnit.NANOSECONDS.toMillis(elapsed);

                Object pattern = request.getAttribute(
                        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
                String route = pattern instanceof String s
                        ? s : "unmatched";

                LOG.info(
                    "event=http.request method={} route={} "
                  + "status={} duration_ms={} exception_escaped={}",
                    request.getMethod(), route, response.getStatus(),
                    durationMs, exceptionEscaped);
            }
        }
    }
}
```

Đây là **class dành cho dự án Spring Boot đã có dependencies**, không phải file Java độc lập biên dịch bằng `javac` mà không có classpath. Khi chạy:
- Filter lấy mốc thời gian trước `chain.doFilter(...)`.
- `finally` chạy khi chain trả về hoặc ném exception.
- Route lấy từ `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` nếu MVC đã match handler; dùng `unmatched` nếu chưa có, tránh raw URL.
- `response.getStatus()` phản ánh **status ở thời điểm filter ghi**; khi exception thoát ra, container có thể thực hiện ERROR dispatch sau đó, khiến status cuối khác.
- `exception_escaped` chỉ cho biết throwable đã thoát khỏi filter chain. Nếu exception được controller advice bắt và xử lý bên trong chain, flag có thể false dù response là 500.
- `TimeUnit.NANOSECONDS.toMillis` **làm tròn xuống** tới millisecond. Nếu muốn giữ độ chính xác dưới 1 ms, dùng chia số thực, nhưng phải quy định định dạng/thống nhất schema.
- Khi request đang ở async mode sau `doFilter`, ví dụ **không ghi duration** nhằm tránh một số đo dở dang bị nhầm là kết quả cuối. Cần framework observation hoặc instrument vòng đời async nếu muốn đo chúng.

### 6.1. Vì sao không lấy `System.nanoTime()` trong controller thôi?

Controller có thể không bao gồm authentication, rate limiting, các filter trước đó, argument binding, JSON serialization, response commit hay middleware. Controller duration hữu ích khi đo riêng logic handler, nhưng **khác server request duration**. Nếu yêu cầu là end-to-end ở phía JVM, cần đặt instrumentation bên ngoài các thành phần muốn đo. Thứ tự filter, error dispatch và async lifecycle ảnh hưởng phạm vi.

### 6.2. Vị trí filter trong chain

Spring Security, CORS, authentication, tracing, compression, routing và application filters có thể chạy trước/sau. Một filter nằm **sau** authentication sẽ không đo request bị từ chối ngay tại authentication trước đó. Nếu muốn đo cả 401/403, instrumentation phải bao được phạm vi cần thiết và có cấu hình filter order/registration phù hợp.

Đừng thay đổi filter order tùy tiện chỉ để log thêm vài mili giây: chuyển vị trí filter có thể tác động security, MDC hoặc lifecycle. Hãy xác định yêu cầu đo trước và kiểm thử các nhánh 2xx/3xx/4xx/5xx.

## 7. Cạm bẫy lớn: Servlet async, DeferredResult và streaming

Với endpoint trả `Callable`, `DeferredResult` hoặc dùng Servlet async, `chain.doFilter(...)` có thể **trả về trước khi request thật sự hoàn tất**.

Ví dụ:

```text
00 ms: Filter bắt đầu, chain.doFilter(...)
02 ms: Controller khởi động async và trả control
03 ms: chain.doFilter(...) quay lại filter
...
240 ms: async task có kết quả
245 ms: response được gửi và async lifecycle hoàn tất
```

Nếu ghi duration ngay ở `finally` tại mốc 03 ms, log sẽ báo **3 ms**, trong khi phía server vẫn xử lý request cho đến khoảng 245 ms. Điều này khiến một request chậm trông như rất nhanh. Để tránh, filter minh họa bên trên bỏ summary khi `request.isAsyncStarted()`.

**OncePerRequestFilter không đồng nghĩa một HTTP request chỉ có một lần thực thi filter trong mọi trường hợp.** Spring mô tả nó chạy một lần **trong từng dispatch**; REQUEST, ASYNC và ERROR dispatch có thể ở các thread khác nhau. Mặc định `shouldNotFilterAsyncDispatch()` là `true`; ERROR dispatch cũng có tùy chọn riêng. Việc thay đổi flag/dispatcher mapping không tự giải quyết timing lifecycle nếu thiếu trạng thái và completion hook.

### 7.1. Cách đúng cho Servlet async

Ưu tiên **observation HTTP server của framework** khi có. Nếu bắt buộc tự triển khai cho Servlet async, cần:
1. Lưu **một mốc start monotonic** tại lần đầu nhận request, không reset mỗi async redispatch.
2. Theo dõi **kết thúc cuối cùng** bằng lifecycle phù hợp (ví dụ `AsyncListener.onComplete` hoặc completion abstraction do framework cung cấp).
3. Ghi **một** summary per request, kể cả qua nhiều dispatch, dùng guard như `AtomicBoolean.compareAndSet`.
4. Xử lý `onTimeout` và `onError` để ghi trạng thái/metric phù hợp nhưng **không mặc định chúng luôn là điểm kết thúc cuối**; container có thể tiếp tục error dispatch.
5. Khi `onStartAsync` khởi tạo một async cycle mới, listener có thể cần được đăng ký lại theo contract Servlet.
6. Bảo đảm chính sách filter registration bao gồm dispatcher types cần dùng; không chỉ override một method rồi tin toàn bộ pipeline hoạt động.
7. Kiểm tra status cuối, request ID, MDC và thread context sau async; không dùng một `ThreadLocal` trên worker để giả định đó là request ban đầu.
8. Kiểm thử timeout, client disconnect, exception, restart và request hoàn thành thành công.

Các callback `onComplete`, `onTimeout`, `onError` và `onStartAsync` thuộc `jakarta.servlet.AsyncListener`. Một snippet vài dòng gắn listener **không đủ** làm giải pháp production nếu chưa xử lý các nhánh kể trên; dùng observation đã được framework hỗ trợ thường ít lỗi hơn.

### 7.2. Spring WebFlux và reactive streams

Spring WebFlux sử dụng chuỗi reactive `Mono`/`Flux`. Thời điểm method trả về một `Mono` **không phải** thời điểm publisher hoàn tất hoặc response đã gửi. Không đo duration bằng việc gọi `System.nanoTime()` trước/sau một method chỉ tạo publisher. Cần instrument tại điểm subscription/termination hoặc dùng built-in HTTP server observation. Với streaming/SSE, một request kéo dài lâu có thể là **hành vi bình thường**; định nghĩa “duration hoàn tất” phải nêu rõ là thời gian tới first byte, completion hay disconnect.

## 8. Spring Boot Actuator/Micrometer: metrics không thay thế log, và ngược lại

Spring Framework/Micrometer hỗ trợ observation tên thường dùng `http.server.requests` cho server-side HTTP exchanges; khi bật Actuator/metrics và các thành phần phù hợp, có thể nhận timer/histogram với tags theo HTTP method, route template, status/outcome. Trong Spring Boot 3, hệ thống Observation được tích hợp với instrumentation cho Spring MVC/WebFlux.

Không nên tự viết thêm một filter đo duration **chỉ vì muốn p95/p99** nếu hệ thống đã có timer từ framework. Hai lớp đo với phạm vi khác nhau có thể tạo hai con số khiến đội vận hành nhầm. Nên bắt đầu bằng việc kiểm tra:
- Actuator/Observation đã được bật chưa?
- Tên meter và các tag thực tế là gì trong phiên bản framework đang chạy?
- Có route bị bỏ qua vì lỗi chưa match handler không?
- Có async request hoặc streaming cần phân loại khác không?
- Có cả metric HTTP server và HTTP client nhưng dashboard dùng nhầm không?

`http.server.requests` thường đo phía **server**; `http.client.requests` đo các outbound HTTP client calls. Không so một metric client với một metric server rồi khẳng định request bị “mất thời gian” mà chưa tính network/proxy/retry.

### 8.1. Timer đo count và total time, histogram đo phân phối

Micrometer `Timer` dành cho duration. Nó có thể thu:
- Số event `count`.
- Tổng thời gian `totalTime`.
- Thời gian lớn nhất hoặc thống kê cửa sổ, tùy implementation.
- Percentiles/histogram khi cấu hình được backend hỗ trợ.

Ví dụ code **minh họa khi dự án đã có Micrometer**:

```java
Timer timer = Timer.builder("app.operation.duration")
        .description("Time spent processing an application operation")
        .tags("operation", "lookup")
        .register(meterRegistry);

Timer.Sample sample = Timer.start(meterRegistry);
try {
    performLookup();
} finally {
    sample.stop(timer);
}
```

Đoạn này không phải file Java độc lập: cần `io.micrometer.core.instrument.Timer`, biến `meterRegistry` và method `performLookup()`. `Timer.Sample` đo chênh lệch bằng clock của registry; `stop(timer)` ghi sample sau khi công việc kết thúc.

Trong Spring Boot, HTTP request observation đã có thể tạo timer; không nhất thiết phải thêm timer custom bọc lại cùng scope. Nếu muốn thống kê công việc con, đặt tên metric khác và nêu rõ phạm vi.

### 8.2. Tại sao trung bình không đủ?

Giả sử có 100 request:
- 95 request hoàn tất khoảng 40 ms.
- 5 request mất khoảng 2.000 ms.

Trung bình có thể trông tương đối thấp so với nhóm bị chậm nghiêm trọng; người dùng ở tail vẫn trải nghiệm latency cao. Dùng **p50, p95, p99** cùng throughput và error rate sẽ có bức tranh đầy đủ hơn.

**p95** là mức mà khoảng 95% quan sát **không vượt quá** theo cách định nghĩa percentile tương ứng; **p99** tập trung vào tail xa hơn. Percentile ước lượng có thể khác nhau theo thuật toán/window/backend.

Micrometer phân biệt:
- **Percentile histogram**: ghi các bucket để backend phù hợp tính percentile xấp xỉ và có thể aggregate theo dimension.
- **Client-side percentiles**: tính trong một meter ở ứng dụng, khó/không thể aggregate trực tiếp thành percentile đúng qua nhiều pod.
- **Một dòng log slow request**: giúp xem request cụ thể nhưng không đủ để suy ra p99 của toàn bộ traffic.

Hạn chế cardinality: không gắn `request_id`, `user_id`, raw URL `/orders/42`, email hoặc token làm **metric label**. Dùng `http.route=/orders/{id}`, method, status class, service và các nhãn có tập giá trị hữu hạn.

### 8.3. Dashboard nên kết hợp tín hiệu nào?

| Tín hiệu | Câu hỏi trả lời |
| --- | --- |
| Request rate | Mỗi giây có bao nhiêu request? |
| Error rate / status mix | 4xx/5xx thay đổi ra sao? |
| p50/p95/p99 latency | User ở trung vị/tail bị ảnh hưởng thế nào? |
| Histogram buckets/SLO | Bao nhiêu request nằm dưới ngưỡng 100/300/1000 ms? |
| Slow-request logs | Request nào chậm, route/trace/status gì? |
| Distributed traces | Thời gian nằm ở DB, downstream, queue, serialization hay app? |
| Resource metrics | CPU/GC/thread pool/DB pool có nghẽn không? |

Không dùng riêng logs để tạo biểu đồ percentile nếu pipeline log có sampling/drop; khi đó mẫu không đại diện đầy đủ trừ khi đã thiết kế có thể hiệu chỉnh.

## 9. Chính sách ghi request duration: mỗi request hay chỉ request chậm?

Tùy lưu lượng và nhu cầu điều tra, có thể chọn:

1. **Summary mọi request**: phù hợp service nhỏ hoặc nhu cầu audit được duyệt; dễ truy tìm nhưng có chi phí disk, network và ingest đáng kể.
2. **Chỉ slow requests**: giữ event quá ngưỡng, ví dụ `duration_ms >= 500`; giảm noise nhưng mất một số ngữ cảnh của request nhanh.
3. **Sample các request bình thường, giữ slow/error**: hỗ trợ điều tra khi traffic lớn; cần ghi tỷ lệ sampling và không coi counts từ logs là counts tuyệt đối.
4. **Metrics toàn bộ + logs theo ngưỡng + traces lấy mẫu phù hợp**: thường cân bằng tốt giữa quan sát và chi phí.

Một policy minh họa:

```text
IF status >= 500:
    log WARN/ERROR summary (không lặp stack trace không cần thiết)
ELSE IF duration_ms >= 1000:
    log WARN event=http.request.slow
ELSE IF sample request bình thường:
    log INFO event=http.request.completed
ELSE:
    không cần event chi tiết; vẫn ghi timer metrics
```

Threshold chỉ là ví dụ; `1000 ms` không phải ngưỡng chuẩn của mọi API. Nên phân loại theo route, phương thức và mục tiêu SLO. Một endpoint streaming có thể chạy hàng phút mà không bị xem là lỗi; một endpoint auth quan trọng có thể cần giới hạn thấp hơn.

**Không cho thread ghi log thực hiện công việc I/O nặng trên critical path chỉ để đo latency.** Nếu appender sync ghi chậm, nó có thể làm duration và chính request bị ảnh hưởng. Async logging cũng có queue-full/drop policy: nếu đang mất log khi tải cao, p99 được suy từ log sẽ thiếu chính những request xấu nhất.

## 10. Đo thế nào để không làm lệch kết quả?

Một số lỗi instrumentation có thể ảnh hưởng phép đo:

### 10.1. Sai vị trí start/end

- Bắt đầu timer **sau** authentication: bỏ qua request bị trả 401/403 sớm.
- Dừng trước JSON serialization: thiếu chi phí chuyển object thành response.
- Dừng ở controller return khi servlet async mới start: đo một khoảng quá ngắn.
- Bọc quá nhiều tầng: metric “server duration” vô tình gồm công việc khác không thuộc HTTP request.
- Đo ở gateway và so với Spring filter nhưng không nêu phạm vi khác nhau.

### 10.2. Double logging/double instrumentation

Nếu container access log, Spring request filter, gateway và Collector cùng phát log cho một request, dashboard có thể thấy nhiều bản và tưởng đó là request duplicate. Xác định tên event/scope (`gateway.request`, `http.server.request`, `handler.duration`) thay vì ghép các bản thành một thống kê. Không gắn thêm filter timer trùng hệt Actuator rồi cộng hai lần.

### 10.3. Logging quá nhiều dữ liệu

Một summary request duration **không cần** Authorization, Cookie, request body, response body hay raw query. In nguyên object `HttpServletRequest` hoặc exception có thể lộ dữ liệu nhạy cảm. Ghi method, route template, status, duration, request/trace ID và outcome đã được duyệt là đủ cho phần lớn trường hợp.

### 10.4. Độ chính xác và overhead

- Thời lượng ngắn dưới 1 ms sẽ hiện `duration_ms=0` nếu ép về `long` millisecond.
- Dùng số thực có 3 chữ số thập phân nếu cần µs-level readability; giữ nhất quán schema.
- `System.nanoTime()` có chi phí nhỏ nhưng không bằng 0; regex, format, MDC/JSON encoding mới có thể chiếm nhiều CPU hơn.
- Không benchmark bằng một request đơn lẻ. Dùng load test và so baseline với instrumentation bật/tắt.
- Đừng cho log message chứa object có `toString()` đắt đỏ, nhất là mỗi request.

## 11. Phân tích timeout và lỗi

Một request chậm có thể dẫn đến 504 tại proxy hoặc 503/500 tại server, nhưng **không phải mọi timeout đều nằm trong ứng dụng Java**.

| Kịch bản | Có thể thấy gì? | Cần đối chiếu |
| --- | --- | --- |
| Client timeout trước server hoàn tất | Client báo timeout, server có thể tiếp tục | Client deadline, server completion, disconnect |
| Gateway timeout 504 | Proxy đã hết thời gian chờ upstream | Proxy timer và server logs/traces |
| DB pool exhaustion | Request chờ lấy connection trước khi query | Pool wait, active/idle, JDBC metrics |
| Outbound HTTP retry | Server duration lớn hơn một lần gọi downstream | Retry count, trace spans, timeout budget |
| JVM GC pause | Nhiều request cùng tăng duration | GC logs, CPU, thread scheduling |
| Thread pool saturation | Request queue hoặc scheduling kéo dài | Executor queue, pending tasks |
| Servlet async timeout | Work chưa hoàn tất đúng deadline | Async lifecycle, onTimeout/onComplete |
| Client disconnect | Server write lỗi hoặc request bị hủy | I/O errors, cancellation signals |
| 4xx validation sớm | Request rất nhanh | Filter order, body parsing, auth branch |

Khi log duration ở `finally`, một exception có thể **thoát ra ngoài** và được Spring Security, exception resolver hoặc servlet container xử lý sau. `response.getStatus()` tại filter không nhất thiết là status cuối. Nếu cần status cuối tuyệt đối cho metric, dùng điểm hoàn tất lifecycle phù hợp và test ERROR dispatch.

Đối với request bị hủy, đừng mặc định rằng “status 200 trong response object” nghĩa client đã nhận đủ bytes. Duration phía server và trải nghiệm client có thể khác nhau.

## 12. Trace giúp phân tích request duration chi tiết

Một request server kéo dài 950 ms có thể gồm:

```text
http.server 950 ms
  auth/check        18 ms
  DB connection    240 ms
  SQL query        510 ms
  serialize JSON    42 ms
  other/overlap     ...
```

Đây là các thời gian **minh họa**, không nên cộng bừa tất cả span durations: các span có thể **lồng nhau hoặc chạy song song**. Trace thể hiện quan hệ cha-con và thứ tự nhân quả; log summary có thể chứa `trace_id` để điều hướng tới trace.

Một log hữu ích:

```text
WARN event=http.request.slow method=GET route=/api/orders/{id} status=200 duration_ms=950 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

Sau đó kiểm tra trong trace:
- Chờ DB connection hay thực thi SQL?
- HTTP client call nào mất thời gian?
- Có retry/backoff?
- Có concurrent tasks hay lock contention?
- Có queue trước handler/worker?
- Có lỗi/timeout mà exception đã được xử lý?

Trace ID chỉ giúp tương quan; nó không tự chứng minh request duration đúng scope. Thời gian trong span cũng cần clock và instrumentation thích hợp.

## 13. Vấn đề cardinality và privacy khi gắn route

Với web APIs:

```text
/api/orders/41
/api/orders/42
/api/orders/43
```

Nếu dùng raw path làm metric tag, mỗi order ID tạo **một time series**. Điều này tăng memory, storage và chi phí query. Tương tự, user ID, trace ID, request ID và query string là nhãn có cardinality rất cao.

Thay bằng:

```text
method=GET route=/api/orders/{id} status=200
```

Ngay cả trong log (không phải metric), raw path có thể chứa token trong password-reset link hoặc dữ liệu cá nhân. Trong Spring MVC, `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể cung cấp route template sau mapping; khi chưa match, dùng nhãn `unmatched` thay vì fallback sang URI gốc.

Đặt route template chuẩn giữa Spring MVC, WebFlux, gateway và tracing instrumentation; nếu mỗi tầng đặt tên khác nhau thì phân tích latency liên service sẽ khó. Không đưa nguyên request headers/cookies vào log chỉ để biết endpoint nào chậm.

## 14. Checklist kiểm thử request duration

| Case | Kỳ vọng |
| --- | --- |
| GET 200 xử lý đồng bộ | Có một summary, duration không âm, đúng đơn vị |
| POST 400 do validation | Được tính nếu nằm trong phạm vi instrumentation |
| 401/403 từ Spring Security | Được tính **nếu** filter/observation đặt đủ sớm |
| 500 do exception | Duration được ghi, kết quả/status phản ánh lifecycle đúng |
| Exception được handler bắt | Không suy outcome chỉ từ “exception escaped” |
| Servlet `Callable` / `DeferredResult` | Không nhầm thời điểm trả khỏi `doFilter` với HTTP complete |
| Async timeout | Một kết quả cuối, không ghi đôi qua dispatch |
| Servlet ERROR dispatch | Không tạo hai summary ngoài chủ đích |
| WebFlux `Mono` / `Flux` | Đo publisher completion/cancel thích hợp, không đo lúc tạo Mono |
| Streaming/SSE | Contract duration phân biệt first byte và stream complete |
| Gateway 504 | So mốc gateway và server, không giả định cùng timeout |
| Outbound HTTP/DB chậm | Trace/metrics con giúp phân loại |
| Route chứa ID hoặc token | Chỉ ghi template, không raw URL |
| Parallel load | Histogram p95/p99, RPS và error rate có thể kiểm chứng |
| Log appender nghẽn | Không nhầm đo chậm do logging với nghiệp vụ chậm |
| Collector ingest muộn | Không nhầm event timestamp với observed/ingest time |

### 14.1. Một phép test đơn vị cho công thức duration

Từ `RequestDurationDemo` ở trên, fake clock đã cố định hai cặp mốc. Trong unit test production có thể inject một `LongSupplier`/clock abstraction, assert chênh lệch và log fields mà **không dùng `Thread.sleep(...)`**. Sleep làm test chậm, flakey và phụ thuộc scheduler.

Test tích hợp Spring Boot nên khởi chạy server thật hoặc `MockMvc` theo scope phù hợp để xác nhận filter order, error handling và route template. Với Servlet async, dùng một test thật sự khởi động async/hoàn tất response; test controller đồng bộ không chứng minh instrumentation async đúng.

## 15. Quy trình chẩn đoán “duration log không khớp”

1. **Xác định hai con số** đang so sánh: client, gateway, server observation, filter hay controller timer.
2. **So mốc start/end** của từng công cụ; có bao gồm network, auth, serialization và async lifecycle không?
3. **Xem đơn vị và precision**: ns, µs, ms, s; integer truncation hay floating point.
4. **Kiểm tra clock**: elapsed dùng `nanoTime` hay wall-clock? Có so timestamp khác máy không?
5. **Xem filter order/dispatch**: 401/403, exception, ERROR/ASYNC có bị bỏ hoặc đo đôi?
6. **Đối chiếu method, route template, status, trace ID, instance** để chắc chắn cùng request/scope.
7. **Kiểm tra pipeline**: log appender queue, Collector delay, query sort, sampling/drop có làm dòng đến trễ không?
8. **Tìm bottleneck thật**: trace, DB pool, GC, thread pool, network, retry.
9. **Kiểm tra dashboard**: p95/p99 đang tính trên histogram nào, có aggregate đúng qua instance và dimension không?
10. **Lặp lại bằng workload đã kiểm soát**, giữ cả source log, metric và trace.

Đừng “sửa” sai lệch bằng cách trừ đi một hằng số tùy ý hoặc gắn `Thread.sleep`. Cần đo đúng phạm vi và trình bày tên metric/log rõ ràng.

## 16. Lỗi phổ biến và cách phòng tránh

**Lỗi 1 — dùng `System.currentTimeMillis()` cho elapsed:** đồng hồ có thể bị chỉnh; dùng `System.nanoTime()` rồi chuyển đúng đơn vị.

**Lỗi 2 — đo controller rồi đặt tên “request duration”:** bỏ qua một số middleware/serialization; đặt tên `handler_duration_ms` hoặc đổi vị trí đo.

**Lỗi 3 — `finally` trên Servlet async được xem là điểm cuối:** đo thiếu thời gian; dùng observation hoặc completion lifecycle, bảo đảm một lần ghi.

**Lỗi 4 — log final status trước ERROR dispatch:** `response.getStatus()` có thể chưa là status cuối; cần xác định status tại điểm nào.

**Lỗi 5 — gắn raw path làm metric label:** tạo cardinality lớn, dễ lộ token; dùng route template có tập giá trị hữu hạn.

**Lỗi 6 — tính p99 từ vài slow-request logs:** sample thiếu sự kiện bình thường, có thể có drop; dùng timer histogram cho thống kê.

**Lỗi 7 — ghi mọi request với payload/headers:** tăng overhead và rủi ro privacy; summary nên là metadata an toàn.

**Lỗi 8 — đo bị ảnh hưởng bởi logging:** appender đồng bộ nghẽn hoặc quá nhiều formatting làm tăng latency; đo overhead và cân nhắc policy async.

**Lỗi 9 — so duration khác scope:** client 500 ms và handler 250 ms không mâu thuẫn nếu còn TLS/network/proxy/serialization.

**Lỗi 10 — cộng span durations:** các span có thể lồng nhau/chạy đồng thời; dùng critical path/trace topology, không cộng ngây thơ.

**Lỗi 11 — không có ID tương quan:** khó biết log chậm thuộc request nào; dùng trace/request ID được tạo an toàn.

**Lỗi 12 — metric duration không có error/status context:** p95 tăng nhưng không biết 5xx hay route nào; chọn low-cardinality tags hợp lý.

## 17. Tóm tắt quyết định triển khai

Khi cần ghi **Request duration** trong ứng dụng web Java, trình tự thực dụng là:

1. Định nghĩa chính xác **start/end/scope** của duration.
2. Dùng clock đơn điệu cho elapsed, timestamp riêng cho thời điểm event.
3. Ưu tiên **HTTP server Observation/Micrometer** có sẵn trong framework để đo cả request lifecycle; đặc biệt với async/WebFlux.
4. Nếu tự ghi request summary, kiểm tra filter order, exception, async dispatch, status và tránh duplicate.
5. Ghi method, route template, status/outcome, duration, trace/request ID và service metadata đã được phê duyệt.
6. Dùng timer/histogram cho p50/p95/p99, request rate và SLO; dùng logs cho điều tra request cụ thể.
7. Theo dõi overhead, queue-full/loss, cardinality, privacy và retention.
8. Test sync, error, timeout, async, streaming, multi-instance và collector ingest.

**Ghi nhớ:** một con số `duration_ms` chỉ có giá trị khi nó đo một khoảng thời gian được định nghĩa rõ. Trong web logging, hãy đo bằng clock đúng, kết thúc tại lifecycle đúng và liên hệ được với route/status/trace, thay vì chỉ đặt đồng hồ quanh một method rồi gọi đó là toàn bộ HTTP latency.

## Tài liệu tham khảo

- [Oracle Java – System.nanoTime()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).
- [Oracle Java – TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html).
- [Spring Framework – OncePerRequestFilter và async/error dispatch](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- [Jakarta Servlet 6.0 – AsyncListener lifecycle](https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html).
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).
- [Spring Boot – Metrics / http.server.requests](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Micrometer – Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).
- [OpenTelemetry – HTTP semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).