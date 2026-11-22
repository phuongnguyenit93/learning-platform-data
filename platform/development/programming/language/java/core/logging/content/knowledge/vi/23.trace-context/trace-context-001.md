# Trace ID trong Java Core Logging

## Mục tiêu

Bài học thuộc nhóm **Trace context**. Sau bài này, bạn có thể giải thích Trace ID, phân biệt nó với Span ID, Request ID và Correlation ID, hiểu cách Trace ID đi qua nhiều service và luồng xử lý Java, đưa Trace ID vào log để truy vết, đồng thời tránh các lỗi mất hoặc rò ngữ cảnh. Trọng tâm là **Trace ID trong Java Core Logging**; tracing được giới thiệu đến mức cần thiết để áp dụng đúng.

## 1. Trace ID là gì?

**Trace** mô tả một hành trình xử lý, chẳng hạn một HTTP request đi qua API Gateway → Order Service → Payment Service → cơ sở dữ liệu. Mỗi thao tác con có thể được mô tả bằng một **span**. **Trace ID** là định danh chung cho toàn bộ trace: mọi span thuộc cùng trace dùng **cùng Trace ID**, trong khi mỗi span có **Span ID riêng**.

```text
Client
  |
  v
API Gateway        trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  v
Order Service      trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  +--> Payment Service     trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  |
  +--> Database operation  trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
```

Các log có thể nằm ở nhiều service và xen kẽ với request khác, nhưng bạn có thể tìm theo `trace_id` để gom các sự kiện liên quan. Trace ID **không tự biểu diễn thứ tự, thời lượng hay quan hệ cha–con**; để biết các thông tin đó cần span, thời điểm và mối quan hệ parent-child. Một Trace ID được in vào log cũng chưa chứng minh rằng trace đã được gửi đến backend tracing.

### Các ID dễ nhầm

| Định danh | Phạm vi và ý nghĩa |
| --- | --- |
| **Trace ID** | Chung cho các span của một trace, có thể đi qua nhiều service. |
| **Span ID** | Định danh một span cụ thể, thay đổi khi sang span khác. |
| **Request ID** | Do ứng dụng/gateway định nghĩa, có thể chỉ gắn với một HTTP request hoặc một hop; không bắt buộc trùng Trace ID. |
| **Correlation ID** | Tên tổng quát của ID để liên kết sự kiện/log; có thể dùng Trace ID hoặc một ID riêng. |
| **User ID / Order ID** | Định danh nghiệp vụ, có vòng đời và yêu cầu bảo vệ dữ liệu khác; không thay thế Trace ID. |

Một đơn hàng có thể trải qua nhiều lần thử thanh toán. `order_id` giữ nguyên nhưng mỗi lần thử có thể tạo trace mới. Không tái sử dụng một Trace ID cho mọi thao tác của một khách hàng, và không xem Trace ID là khóa nghiệp vụ.

## 2. Trace ID và chuẩn W3C Trace Context

Trong `traceparent` phiên bản `00` theo W3C, Trace ID được biểu diễn bằng **16 byte = 128 bit = 32 ký tự hexadecimal viết thường** (`0-9` và `a-f`). Giá trị toàn số `0` (`00000000000000000000000000000000`) là không hợp lệ. ID cần có tính ngẫu nhiên và xác suất trùng rất thấp; khi tiếp tục trace hợp lệ, phải giữ nguyên Trace ID thay vì sinh ID mới ở mỗi service.

Ví dụ header HTTP:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Các phần theo thứ tự:

- `00`: phiên bản header.
- `4bf92f3577b34da6a3ce929d0e0e4736`: **Trace ID** của cả hành trình.
- `00f067aa0ba902b7`: **parent-id** của request được truyền, tức Span ID phía gửi (8 byte = 16 ký tự hex); ID toàn số `0` cũng không hợp lệ.
- `01`: **trace-flags**, trong đó bit thấp nhất là `sampled`. `00` biểu thị bit này không bật; nó không có nghĩa mọi log sẽ bị tắt.

Khi Payment Service nhận một `traceparent` hợp lệ, nó có thể tạo span mới với Span ID khác nhưng vẫn giữ Trace ID cũ. Khi gọi service tiếp theo, tracing instrumentation truyền context hiện hành và cập nhật parent-id phù hợp. Không sao chép cứng toàn bộ header qua mọi hop, vì parent-id phải phản ánh span phía gửi tại mỗi lần truyền.

`tracestate` là header bổ sung mang trạng thái tracing riêng của vendor. `baggage` là cơ chế khác truyền các cặp key-value ngữ cảnh; không đặt dữ liệu nghiệp vụ hoặc bí mật vào Trace ID.

**Validation quan trọng:** Header từ bên ngoài có thể sai định dạng hoặc giả mạo. Cần kiểm tra phiên bản, dấu phân cách, độ dài, ký tự hex, ID toàn số `0` và flags theo đặc tả. Khi context không hợp lệ, propagator không được tiếp tục context đó; ứng dụng thường bắt đầu trace mới theo chính sách. Nên dùng propagator của OpenTelemetry/thư viện tracing thay vì parser tự viết bằng `split("-")` trong production.

## 3. Trace ID đi qua hệ thống như thế nào?

1. **Entry point:** HTTP request hoặc message đến. Instrumentation *extract* context từ header/metadata. Nếu hợp lệ và được tiếp tục theo chính sách thì sử dụng Trace ID đó; nếu không, bắt đầu trace mới với ID mới.
2. **Trong ứng dụng:** Controller, service, repository, HTTP client và các span con cùng thuộc một trace sẽ dùng chung Trace ID. Logger đọc context hiện hành để thêm trường `trace_id`.
3. **Ra ngoài process:** HTTP client hoặc message producer *inject* context vào header/metadata phù hợp. Service/consumer phía nhận *extract* context trước khi xử lý.
4. **Qua luồng bất đồng bộ:** `ExecutorService`, `CompletableFuture`, callback hoặc scheduler cần wrapper/instrumentation để truyền context. `ThreadLocal` và MDC thông thường không tự sao chép sang worker thread.
5. **Hoàn tất:** Đóng scope và khôi phục context trước đó; xóa các giá trị tạm trong MDC/ThreadLocal để tránh thread pool tái sử dụng Trace ID của request cũ.

```text
HTTP inbound
  -> extract traceparent / tạo trace mới
  -> đặt trace context vào scope hiện tại
  -> ghi log có trace_id khi xử lý
  -> HTTP outbound / messaging: inject context
  -> đóng scope và khôi phục context trước đó
```

Không ép mọi sự kiện liên quan đến một Order ID vào cùng một trace. Message bất đồng bộ, batch hoặc fan-out/fan-in có thể cần quan hệ bằng *span links* hoặc trace mới tùy semantics; cách propagate qua queue còn tùy instrumentation của producer/consumer.

## 4. Đưa Trace ID vào log để truy vết

Ví dụ hai sự kiện trong một trace:

```text
level=INFO service=order-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 event=order-created
level=INFO service=payment-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 event=payment-authorized
```

Cùng Trace ID giúp tìm các log của hành trình; Span ID giúp định vị thao tác cụ thể. Nên quy ước trường nhất quán (`trace_id`, `span_id`, tên service), giữ ID ở dạng **chuỗi** và cấu hình log collector để không bỏ các trường đó. Log JSON thường thuận tiện cho việc truy vấn và tương quan hơn việc nối ID trực tiếp vào message text.

Ví dụ truy vấn tìm chính xác một ID, với cú pháp cụ thể tùy backend:

```text
trace_id:"4bf92f3577b34da6a3ce929d0e0e4736"
```

Quy trình debug: lấy Trace ID từ log lỗi hoặc response, tìm log ở tất cả service theo ID, sắp xếp theo thời gian rồi đối chiếu Span ID/span tree để hiểu tiến trình. Thiếu log không nhất thiết là thao tác không chạy: log level, sampling, log collector, retention hoặc context propagation đều có thể ảnh hưởng.

## 5. Java 17: Ví dụ chạy độc lập với ThreadLocal và ExecutorService

Ví dụ sau dùng **chỉ JDK** để minh họa cách *capture → gắn ngữ cảnh ở worker → dọn ngữ cảnh*. Nó là mô phỏng correlation cho logging, **không phải** distributed tracer/OpenTelemetry hoàn chỉnh. Trace ID được cố định để kết quả chạy kiểm chứng được; trong hệ thống thật phải lấy từ trace context hoặc tạo mới tại ranh giới trace.

Tạo file `TraceIdLogDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TraceIdLogDemo {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    private static void log(String event) {
        System.out.println("trace_id=" + TRACE_ID.get() + " event=" + event);
    }

    public static void main(String[] args) throws Exception {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";
        ExecutorService pool = Executors.newSingleThreadExecutor();

        TRACE_ID.set(traceId);
        try {
            log("request-start");

            String capturedTraceId = TRACE_ID.get();
            Future<?> task = pool.submit(() -> {
                TRACE_ID.set(capturedTraceId);
                try {
                    log("async-work");
                } finally {
                    TRACE_ID.remove();
                }
            });

            task.get();
            log("request-end");
        } finally {
            TRACE_ID.remove();
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac TraceIdLogDemo.java
java TraceIdLogDemo
```

Kết quả chuẩn trên **stdout**:

```text
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=request-start
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=async-work
trace_id=4bf92f3577b34da6a3ce929d0e0e4736 event=request-end
```

Giải thích:

- `TRACE_ID` là `ThreadLocal`: giá trị tại main thread **không tự chuyển** sang thread của `pool`.
- `capturedTraceId` được lấy trước `submit` rồi đặt trong worker; vì thế `async-work` có cùng ID. `task.get()` làm cho `request-end` xuất hiện sau log worker.
- `finally` dọn context ở hai thread kể cả khi ném exception. Nếu quên dọn trong thread pool, log request sau có thể mang nhầm ID request trước.
- Ví dụ dùng một tác vụ worker độc lập. Một wrapper dùng chung trong production cần **khôi phục giá trị context trước đó**, nhất là khi các scope lồng nhau. Tốt nhất dùng context-aware executor/instrumentation của thư viện tracing.

**Tự kiểm tra lỗi:** bỏ dòng `TRACE_ID.set(capturedTraceId);` trong lambda. Log `async-work` sẽ in `trace_id=null`. Đây là cách tái hiện lỗi mất ngữ cảnh khi chuyển thread.

## 6. Tạo Trace ID khi cần tự instrument

Thông thường **tracer** phải chịu trách nhiệm tạo Trace ID, không phải logger. Không sinh Trace ID mới cho từng method, từng span hoặc từng dòng log. Nếu cần hiểu cách sinh chuỗi đúng định dạng bằng Java 17, có thể dùng `SecureRandom` và `HexFormat`.

Tạo file `GenerateTraceId.java`:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class GenerateTraceId {
    private static final SecureRandom RANDOM = new SecureRandom();

    private static String newTraceId() {
        byte[] bytes = new byte[16];
        boolean allZero;

        do {
            RANDOM.nextBytes(bytes);
            allZero = true;
            for (byte b : bytes) {
                if (b != 0) {
                    allZero = false;
                    break;
                }
            }
        } while (allZero);

        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) {
        String id = newTraceId();
        System.out.println(id.length());
        System.out.println(id.matches("[0-9a-f]{32}"));
        System.out.println(!id.equals("0".repeat(32)));
    }
}
```

```bash
javac GenerateTraceId.java
java GenerateTraceId
```

Output:

```text
32
true
true
```

ID thực tế thay đổi ngẫu nhiên qua mỗi lần chạy nhưng ba phép kiểm tra trên luôn đúng: 16 byte tạo 32 ký tự hex viết thường, và vòng lặp loại ID toàn số `0`. Mã ví dụ **chưa** tạo span, truyền context, sampling hoặc export trace; không thay thế tracer/propagator trong production.

Tránh dùng timestamp đơn thuần, counter chỉ duy nhất trong một process, user ID, email, IP hoặc order ID làm Trace ID. Các cách đó có thể trùng, tiết lộ thông tin hoặc tạo quan hệ truy vết sai.

## 7. Triển khai với OpenTelemetry, SLF4J và MDC

Trong ứng dụng Java thực tế, có thể dùng OpenTelemetry Java agent hoặc instrumentation phù hợp để tạo span, quản lý context và tự inject/extract qua các protocol được hỗ trợ. Khi một scope đã được instrument, API cho phép đọc context hiện hành:

```java
// Trích đoạn trong method có OpenTelemetry API trên classpath:
io.opentelemetry.api.trace.SpanContext sc =
        io.opentelemetry.api.trace.Span.current().getSpanContext();

if (sc.isValid()) {
    String traceId = sc.getTraceId();
    String spanId = sc.getSpanId();
    // Thêm vào structured log nếu logging stack chưa tự làm.
}
```

Đoạn trên **không phải chương trình Java độc lập**. Nếu context không hợp lệ, đừng thay bằng ID giả toàn số `0` hoặc tự tạo ID mới cho mỗi lần log.

**MDC (Mapped Diagnostic Context)** trong SLF4J/Logback, hoặc cơ chế tương đương của Log4j, giúp thêm giá trị context vào log event. Ví dụ một **phần** pattern encoder của Logback:

```xml
<pattern>%d{ISO8601} %-5level trace_id=%X{trace_id} span_id=%X{span_id} %logger - %msg%n</pattern>
```

Đây không phải file `logback.xml` hoàn chỉnh. Pattern chỉ đọc các khóa MDC: phải có agent/bridge hoặc ứng dụng đặt giá trị `trace_id`/`span_id` vào MDC hay log record thì mới hiển thị. OpenTelemetry Java agent có cơ chế MDC correlation cho các logging library được hỗ trợ, nhưng cách bật và cấu hình thực tế tùy agent, phiên bản và logging stack. Với structured logging, sử dụng trường JSON tương đương.

Nếu tự đặt giá trị bằng `MDC.put(...)`, phải dùng `try/finally` để xóa hoặc khôi phục giá trị cũ và tránh rò context. Nếu đã có cơ chế injection tự động, tránh tự chèn trùng hoặc ghi đè. Không giữ Trace ID của request trong biến `static` chung. MDC/ThreadLocal thường gắn với thread: khi dùng `CompletableFuture`, scheduler hoặc pool, cần context-aware executor, scope/wrapper hoặc instrumentation thích hợp.

Để một hệ thống hoạt động end-to-end, cần kiểm tra **ba lớp**: (1) context được tạo/extract/inject đúng, (2) logger thêm đúng các trường từ context hiện hành, (3) pipeline giữ lại các trường khi vận chuyển và index log. Việc có ID ở service A nhưng mất ở service B thường là lỗi ở một trong ba lớp này.

## 8. Sampling, bảo mật và vận hành

- **Sampling khác logging.** Trace có cờ `sampled` không bật vẫn có thể có Trace ID trong context và log. Ngược lại, log có ID không bảo đảm span đã được export; có thể không có trace để mở ở backend.
- **Trace ID không phải credential.** Không dùng nó để xác thực, phân quyền hoặc làm bí mật. Không nhúng dữ liệu cá nhân, token, session secret hoặc thông tin người dùng vào ID. Với `baggage` phải kiểm soát dữ liệu được truyền qua service boundary.
- **Không tin tuyệt đối header bên ngoài.** Validate `traceparent`, giới hạn kích thước header và áp dụng chính sách trust boundary. Đừng dựa vào Trace ID do client gửi để quyết định quyền truy cập tài nguyên.
- **Định dạng nhất quán.** Giữ ID là chuỗi hex viết thường và đầy đủ 32 ký tự theo W3C; không parse sang số vì có thể mất số `0` ở đầu. Log/collector thống nhất tên và kiểu trường.
- **Cardinality của metrics.** Mỗi request thường có ID riêng; đưa `trace_id` làm nhãn metrics thông thường gây cardinality rất lớn. Phù hợp hơn khi lưu trong log và liên kết với trace.
- **Retention và sampling khác nhau.** Log vẫn có thể còn sau khi trace đã hết hạn hoặc không được lưu. ID vẫn hữu ích để truy tìm các log liên quan.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| A có Trace ID nhưng B không có | HTTP client không inject hoặc B không extract | Kiểm tra instrumentation hai phía và `traceparent` ở môi trường kiểm thử. |
| Trace ID đổi ở mỗi service | Mỗi service tạo root trace mới | Dùng propagator thống nhất và tiếp tục context hợp lệ. |
| `trace_id=null` trong `CompletableFuture` | Context gắn thread không được truyền | Dùng context-aware executor/wrapper hoặc async instrumentation. |
| Log request sau mang ID request trước | Quên dọn MDC/ThreadLocal trong pool | Đóng scope và restore/clear trong `finally`. |
| Mỗi log có ID khác nhau | Sinh ID ngay trong logger | Lấy Trace ID từ active context, sinh mới tại trace boundary. |
| Log có ID nhưng không thấy trace | Sampling, exporter, collector, retention | Kiểm tra sampler, exporter, backend và khoảng lưu. |
| Tìm log theo ID không thấy | Collector bỏ field hoặc parser/index sai | Kiểm tra raw log, schema `trace_id` và cú pháp query. |
| Header bị từ chối | Sai version, độ dài, hex hoặc toàn số `0` | Để propagator xử lý validation theo W3C. |

### Bài tập xác minh

1. Cho một HTTP request đi qua hai service. Tìm `trace_id` ở log của hai bên: **Trace ID giống nhau**, còn Span ID có thể khác.
2. Chạy `ExecutorService` và so sánh log trước/sau khi truyền context; xác nhận log worker có đúng ID.
3. Gửi hai request độc lập liên tiếp qua cùng thread pool; xác nhận ID request cũ không rò sang request mới.
4. Thử `traceparent` có Trace ID toàn số `0` trên môi trường kiểm thử; xác minh propagator xử lý context không hợp lệ.
5. Lọc theo Trace ID và mở trace backend. Nếu trace không có, kiểm tra sampling/export/retention trước khi kết luận ID sai.

**Tiêu chí đạt:** Bạn hiểu vì sao Trace ID ổn định trong một trace, Span ID thay đổi theo span; biết lấy ID từ context, truyền qua boundary, ghi thành trường log, dọn scope và kiểm chứng qua nhiều service.

## Tài liệu tham khảo

- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent`, trace-id, parent-id, trace-flags và validation.
- [OpenTelemetry — Java instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/) — context, spans và propagation.
- [OpenTelemetry Java instrumentation — Logger MDC](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md) — tương quan trace/span với log qua MDC.
