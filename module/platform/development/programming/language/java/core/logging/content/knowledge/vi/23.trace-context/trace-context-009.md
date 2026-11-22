# Tương thích OpenTelemetry: liên kết Java Logging với Trace Context

## 1. Vấn đề cần giải quyết

Trong một ứng dụng Java có nhiều request chạy đồng thời, các dòng log thường xen kẽ nhau. Khi request đi qua nhiều service, chỉ nhìn thời gian và tên thread rất khó biết log nào thuộc cùng một luồng xử lý. **OpenTelemetry (OTel) giúp gắn ngữ cảnh truy vết vào log** để người vận hành có thể tìm log từ một trace, hoặc tìm trace từ một dòng log lỗi.

Ví dụ một yêu cầu đi qua `api-service → order-service → payment-service`. Nếu cả ba service truyền đúng trace context, các log phát sinh trong cùng yêu cầu có chung `trace_id`; mỗi span (đơn vị công việc được đo) có `span_id` riêng. Đây là **log–trace correlation**.

“Tương thích OpenTelemetry” trong phạm vi Java Logging có ba khía cạnh cần phân biệt:

1. **Truyền ngữ cảnh**: bảo toàn trace context trong lời gọi đồng bộ, qua thread/task và qua ranh giới service.
2. **Gắn ngữ cảnh vào log**: đưa ID của trace/span đang hoạt động vào log text hoặc log record có cấu trúc.
3. **Thu thập và xuất dữ liệu**: gửi log, trace cùng thông tin nhận diện service tới hệ thống quan sát, có thể thông qua OTLP/Collector.

Có `trace_id` trong console log **chưa có nghĩa** là ứng dụng đang xuất log qua OTLP; ngược lại, việc gửi log tới Collector không bảo đảm log đó có trace context nếu lúc ghi không tồn tại span hợp lệ.

## 2. Các thành phần và thuật ngữ

| Thành phần | Ý nghĩa trong bài này |
| --- | --- |
| SLF4J, Logback, Log4j 2, JUL | API hoặc framework tạo và định dạng log trong Java; có thể tiếp tục dùng khi tích hợp OTel. |
| OTel API | Cung cấp `Tracer`, `Span`, `Context`; mã ứng dụng và instrumentation cùng dùng để mô tả ngữ cảnh. |
| OTel SDK | Triển khai thu thập/xử lý/export telemetry. API đơn lẻ không tự xuất dữ liệu. |
| Java agent / Spring Boot starter | Hai cách triển khai instrumentation tự động; chọn theo hệ sinh thái và khả năng cấu hình của dự án. |
| MDC (Mapped Diagnostic Context) | Map ngữ cảnh được logging framework sử dụng khi tạo log event, thường có tính gắn với thread. |
| OTLP | Giao thức truyền telemetry từ ứng dụng/Collector tới bộ thu hoặc backend hỗ trợ. |
| OTel Collector | Thành phần có thể nhận, xử lý và chuyển tiếp traces, metrics, logs. |

Các trường nhận diện quan trọng:

- `trace_id`: 16 byte, thường biểu diễn bằng **32 ký tự hex**, cùng giá trị trên các span thuộc một trace.
- `span_id`: 8 byte, thường biểu diễn bằng **16 ký tự hex**, nhận diện một span cụ thể; thay đổi khi đi sang span mới.
- `trace_flags`: các cờ của trace context; ở W3C Trace Context, bit sampled cho biết quyết định lấy mẫu được lan truyền, **không phải bảo đảm trace đã được lưu ở backend**.
- `service.name`: thuộc tính tài nguyên (resource) để biết nguồn phát sinh telemetry; nên đặt rõ tên riêng cho từng service.

Ví dụ header W3C Trace Context hợp lệ:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Trong đó `00` đầu tiên là phiên bản; 32 ký tự tiếp theo là trace ID; 16 ký tự sau là **parent span ID được truyền từ upstream**; `01` là trace flags. Khi service nhận request và tạo server span, span mới thường có **span ID khác**, nhưng tiếp tục dùng trace ID của yêu cầu. Có thể có thêm header `tracestate` theo chuẩn W3C.

Không dùng một request ID tùy ý thay cho `trace_id` nếu ID đó không tuân thủ mô hình trace context. Có thể giữ cả `request_id` riêng cho nghiệp vụ hoặc gateway, nhưng phải xác định rõ quan hệ giữa hai ID.

## 3. Luồng liên kết log với trace

```text
HTTP request (traceparent)
        │
        ▼
Instrumentation đọc context → tạo/đặt span hiện hành
        │
        ├── Java application → SLF4J → Logback/Log4j
        │                              │
        │                              ├── MDC trên log event
        │                              │   → console/file chứa trace_id, span_id
        │                              │
        │                              └── OTel logging appender (nếu bật)
        │                                  → OTel LogRecord → OTLP
        │
        └── OTel tracing SDK → span → OTLP
                                        │
                                  OTel Collector
                                        │
                              Observability backend
```

Hai tuyến log phổ biến:

**Tuyến A – log text có ID:** framework vẫn ghi ra stdout/file; pattern layout in `trace_id` và `span_id`. Một log shipper/Collector có thể đọc log, parse các trường này và liên kết với trace nếu backend hỗ trợ. MDC injection tự nó **không gửi log qua mạng**.

**Tuyến B – log record OTel:** logging appender/bridge chuyển sự kiện log thành OTel LogRecord, có các trường tiêu chuẩn như `TraceId`, `SpanId`, `SeverityText`, `Body` và `Resource`; SDK/exporter gửi qua OTLP. Tên trường hiển thị khi tìm kiếm ở backend có thể khác tên key MDC `trace_id`.

Có thể kết hợp hai tuyến, nhưng cần cấu hình để **không ingest trùng một sự kiện log** (ví dụ vừa gửi trực tiếp qua OTLP vừa thu lại chính dòng stdout ấy).

## 4. Tích hợp dễ bắt đầu: Java agent + SLF4J/Logback

Với một ứng dụng Java đã dùng SLF4J và Logback (ví dụ Spring Boot), Java agent thường là điểm khởi đầu phù hợp vì nó tự instrument nhiều HTTP client/server và logging framework được hỗ trợ. Không phải thay toàn bộ `logger.info(...)` bằng OpenTelemetry Logger API. Thực tế, OTel Logs API chủ yếu phục vụ bridge/appender; ứng dụng vẫn có thể dùng logging API quen thuộc.

### Bước 1: chạy ứng dụng với agent

Tải agent từ bản phát hành chính thức:

```bash
curl -L -o opentelemetry-javaagent.jar \
  https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar
```

Ví dụ chạy trên Bash khi **đã có** `app.jar` và một OTLP receiver đang lắng nghe ở `localhost:4318`:

```bash
OTEL_SERVICE_NAME=orders-service \
OTEL_TRACES_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
java -javaagent:./opentelemetry-javaagent.jar -jar app.jar
```

`OTEL_SERVICE_NAME` xác định service; `OTEL_EXPORTER_OTLP_ENDPOINT` là địa chỉ bộ nhận OTLP, **không phải endpoint HTTP của ứng dụng**. Nếu không có Collector/backend hoạt động, ứng dụng vẫn có thể log ra console nhưng export telemetry sẽ không thành công. Ở Java agent hiện đại, giao thức OTLP mặc định thường là `http/protobuf`, nhưng khai báo tường minh giúp tránh nhầm cổng 4317 (gRPC) và 4318 (HTTP).

Ví dụ tương đương trong PowerShell:

```powershell
$env:OTEL_SERVICE_NAME = "orders-service"
$env:OTEL_TRACES_EXPORTER = "otlp"
$env:OTEL_LOGS_EXPORTER = "otlp"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
$env:OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
java "-javaagent:.\opentelemetry-javaagent.jar" -jar ".\app.jar"
```

Không cần bật `OTEL_LOGS_EXPORTER=otlp` chỉ để đưa ID vào dòng console. Nếu pipeline chỉ thu stdout/file, có thể cấu hình `OTEL_LOGS_EXPORTER=none` để không xuất thêm qua log bridge, tùy chính sách telemetry của hệ thống.

### Bước 2: in ID vào log text

Với Logback, đặt pattern trên appender thực sự đang ghi console/file. Ví dụ `src/main/resources/logback-spring.xml` trong Spring Boot:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} trace_id=%X{trace_id} span_id=%X{span_id} trace_flags=%X{trace_flags} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%X{trace_id}`, `%X{span_id}`, `%X{trace_flags}` lấy giá trị từ MDC của **log event**. Agent có instrumentation hỗ trợ đưa context của span hiện hành vào bản sao MDC khi log được tạo. Nếu ứng dụng đã có cấu hình Logback riêng, sửa **pattern hiện có** thay vì vô tình tạo appender console thứ hai và làm log lặp.

Đối với Spring Boot sử dụng pattern mặc định, một lựa chọn gọn hơn là cấu hình:

```properties
logging.pattern.level=trace_id=%mdc{trace_id} span_id=%mdc{span_id} trace_flags=%mdc{trace_flags} %5p
```

Chọn **một** cách phù hợp với cấu hình logging đang dùng; `logging.pattern.level` không nhất thiết thay đổi custom `logback-spring.xml` vốn tự định nghĩa encoder/pattern.

Với Log4j 2, ý tưởng tương tự nhưng PatternLayout dùng `%X{trace_id}` và `%X{span_id}`. Cần chọn instrumentation tương thích đúng framework, phiên bản và cách khởi tạo appender.

### Bước 3: để mã nghiệp vụ tiếp tục dùng logger bình thường

Ví dụ sau là controller dùng trong **một dự án Spring Boot đã có** `spring-boot-starter-web` và SLF4J; đây là lớp ứng dụng mẫu, không phải chương trình Java độc lập có thể chạy bằng một lệnh `javac`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderController.class);

    @GetMapping("/orders/{id}")
    public ResponseEntity<String> getOrder(@PathVariable long id) {
        LOG.info("Đang đọc đơn hàng id={}", id);
        return ResponseEntity.ok("order-" + id);
    }
}
```

Khởi động service với agent rồi gọi:

```bash
curl -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  http://localhost:8080/orders/42
```

Response body từ controller là `order-42`. Nếu agent instrument HTTP server và MDC logging đúng, dòng log có thể trông như sau (ID/span và thời gian là **minh họa**, không phải output cố định):

```text
10:15:32.421 INFO  [http-nio-8080-exec-1] OrderController trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=8b2d4ce1028fe355 trace_flags=01 - Đang đọc đơn hàng id=42
```

Trace ID giữ theo header đầu vào; span ID trong log là ID của span hiện hành phía server, không nhất thiết trùng parent span ID trong header. Nếu gọi health check, khởi động ứng dụng hoặc ghi log ngoài span hợp lệ, trường ID có thể rỗng; đây **không tự động là lỗi MDC**.

## 5. Tạo span thủ công khi nghiệp vụ cần thêm chi tiết

Agent tạo span cho nhiều hoạt động framework, nhưng không thể tự hiểu các bước nghiệp vụ như `invoice.validate`. Khi cần chi tiết đó, mã có thể dùng OTel API. Ví dụ dưới đây là **phương thức tích hợp vào class đang có** (có SLF4J và dependency `io.opentelemetry:opentelemetry-api` phù hợp phiên bản dự án); mã không tự cấu hình SDK/exporter:

```java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class InvoiceService {
    private static final Logger LOG =
            LoggerFactory.getLogger(InvoiceService.class);
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("invoice-service");

    public void validate(long invoiceId) {
        Span span = TRACER.spanBuilder("invoice.validate").startSpan();
        try (Scope scope = span.makeCurrent()) {
            LOG.info("Kiểm tra hóa đơn id={}", invoiceId);
            if (invoiceId <= 0) {
                throw new IllegalArgumentException("invoiceId phải dương");
            }
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            LOG.error("Không thể kiểm tra hóa đơn id={}", invoiceId, ex);
            throw ex;
        } finally {
            span.end();
        }
    }
}
```

Trong vùng `try (Scope scope = span.makeCurrent())`, `Span.current()` chỉ về span vừa tạo; khi scope đóng, context trước đó được khôi phục. `span.end()` hoàn tất span dù phương thức thành công hay ném exception. Nếu không cấu hình SDK/provider thực sự, API có thể chạy ở chế độ no-op và không xuất trace; chỉ thêm dependency API **không biến hệ thống thành observability pipeline**.

Để kiểm tra không phụ thuộc vào pattern logging:

```java
Span span = Span.current();
if (span.getSpanContext().isValid()) {
    String traceId = span.getSpanContext().getTraceId();
    String spanId = span.getSpanContext().getSpanId();
    // Có thể dùng hai ID này cho diagnostic có kiểm soát.
}
```

Đoạn trên cần các import `io.opentelemetry.api.trace.Span` và context hợp lệ đang hoạt động. Tránh tự gọi `MDC.put("trace_id", ...)` trong mọi phương thức nếu agent đã instrument logging: dễ gây xung đột giá trị, thiếu dọn dẹp MDC và khó duy trì. Chỉ thêm MDC thủ công khi có yêu cầu rõ, bảo đảm `remove`/khôi phục giá trị trong `finally`.

## 6. Bảo toàn trace context qua thread và service

**Qua service:** ở HTTP client instrumented, context được inject vào request outbound; HTTP server downstream extract context và tạo span con. Nhờ vậy hai service có cùng trace ID. Với messaging/Kafka hoặc giao thức riêng, phải dùng instrumentation/propagator tương ứng; không tự giả định header HTTP được truyền qua mọi môi trường. Mặc định phổ biến là W3C `tracecontext` cùng `baggage`; nếu hai bên dùng định dạng khác nhau, phải cấu hình propagator tương thích.

**Qua thread/task:** context hiện hành thường được gắn với phạm vi thực thi. Một `new Thread`, `ExecutorService`, `CompletableFuture` hoặc callback bất đồng bộ có thể mất ngữ cảnh nếu không được instrument/wrap. Với OTel Context API, có thể chủ động truyền ngữ cảnh khi submit công việc:

```java
import io.opentelemetry.context.Context;
import java.util.concurrent.Executor;
import org.slf4j.Logger;

public void submit(Executor executor, Logger logger) {
    Context captured = Context.current();
    executor.execute(captured.wrap(
            () -> logger.info("Hoàn thành tác vụ bất đồng bộ")));
}
```

Đây là **phương thức bổ sung trong class đang có**, nhận `Executor` và `Logger` từ bên ngoài. `captured.wrap(...)` đặt context đã bắt vào thread chạy task rồi khôi phục khi task kết thúc. Có thể dùng `Context.taskWrapping(executor)` để bọc toàn executor. Nếu agent/framework đã tự động propagate context qua executor được hỗ trợ, tránh bọc lặp thiếu cần thiết; hãy kiểm tra bằng trace ID thực tế.

Lưu ý rằng **MDC và OTel Context không đồng nhất**. MDC có thể lưu thêm `user_key`, `request_id` của ứng dụng; truyền OTel Context không đồng nghĩa tự động copy mọi key MDC tùy ý. Tương tự, việc copy MDC giữa thread không tự bảo đảm OTel active span vẫn đúng.

## 7. Chọn phương án tích hợp và thiết lập pipeline

| Nhu cầu | Cách làm | Kiểm tra cốt lõi |
| --- | --- | --- |
| Có trace ID trong stdout/file | Agent hoặc MDC instrumentation + pattern Logback/Log4j 2 | Log event trong request có `trace_id`, `span_id` đúng. |
| Xuất log có cấu trúc qua OTLP | OTel logging appender/bridge + SDK/exporter + Collector | LogRecord đến backend có TraceId, SpanId, service.name khi có active span. |
| Chỉ thu stdout bằng Collector | Pattern/JSON log có ID + collector/filelog receiver hoặc log shipper | Backend parse ID và có thể truy vấn chung với trace. |
| Tạo span nghiệp vụ | OTel API `Tracer`/`Span` trong context hiện hành | Trace thể hiện thêm công việc nghiệp vụ, phân cấp parent–child hợp lý. |
| Bất đồng bộ | Instrumentation executor hoặc `Context.wrap(...)` | Log trong task giữ đúng trace ID của request gốc. |

**Java agent và Spring Boot starter** có thể giải quyết những nhu cầu tương tự, nhưng không nên bật chồng hai bộ instrumentation chỉ vì nghĩ telemetry sẽ “đầy đủ hơn”. Khi tự cấu hình thêm OTel Logback/Log4j appender cùng agent, kiểm tra số lần export để tránh duplicate.

Ở backend, ít nhất phải liên kết được các thuộc tính:
- Trace: `trace_id`, `span_id`/parent, tên service và khoảng thời gian.
- Log: message/`Body`, level/`SeverityText`, timestamp, service/resource, TraceId/SpanId khi có.
- Resource: phân biệt service và môi trường triển khai, ví dụ `service.name=orders-service`.

Hệ thống truy vấn nên hỗ trợ tìm log theo trace ID và chuyển từ log sang trace. Việc hiện nút “View trace” phụ thuộc backend và cách parse/index dữ liệu, không phải tính năng bảo đảm chỉ nhờ thêm agent.

## 8. Xác minh bằng tình huống cụ thể

1. **Một request, nhiều log:** gửi một request có `traceparent` hợp lệ tới endpoint được instrument. Các log trong cùng trace phải có cùng trace ID; span ID có thể thay đổi khi chạy trong các span khác nhau.
2. **Qua hai service:** A gọi B thông qua HTTP client/server đã instrument; log ở A và B nên có cùng trace ID, trong khi hai server/client span là các span khác nhau.
3. **Qua task bất đồng bộ:** ghi log trước và trong executor; kiểm tra giá trị trace ID. Nếu mất, xem lại context propagation, scope và thời điểm capture.
4. **Log ngoài request:** log startup/background khi không có active span có thể thiếu ID; không tự điền chuỗi `000...` giả hoặc dùng trace ID của request trước.
5. **Tại Collector/backend:** kiểm tra trace đến nơi, log đến nơi, hai signal mang cùng service identity và hỗ trợ join/correlation. Tránh xác nhận thành công chỉ vì console có ID.
6. **Sampling:** nếu log có trace ID nhưng backend không thấy trace, kiểm tra sampling và việc export/retention; log vẫn có thể chứa context của một span không được ghi nhận.
7. **Chống trùng:** so số sự kiện log tạo trong ứng dụng với số log record được ingest. Nếu gấp đôi, kiểm tra đồng thời appender OTLP và stdout collector.

Ví dụ nhật ký lỗi mong muốn có thể là:

```text
2026-11-10T10:00:00Z ERROR service=orders-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=8b2d4ce1028fe355 order=42 - Payment gateway timeout
```

Đây chỉ là **mẫu định dạng**, không phải dòng log thực tế hay một kết quả chạy Java. Người vận hành lấy trace ID ở log để tìm toàn bộ đường đi của request, rồi xem span nào có latency/error tương ứng.

## 9. Lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `trace_id` luôn rỗng | Không có span hiện hành; agent không được nạp; logging instrumentation không áp dụng đúng framework | Kiểm tra `-javaagent`, version tương thích, request có tạo span, layout MDC được áp dụng. |
| Trace có ở backend nhưng console không in ID | Chưa đưa MDC keys vào pattern hoặc appender dùng layout khác | Kiểm tra Logback/Log4j config đang hoạt động và tên key `trace_id`/`span_id`. |
| A và B có trace ID khác nhau | Không inject/extract context, sai propagator, gọi downstream qua client chưa instrument | Kiểm tra `traceparent`/carrier thực tế qua mạng và instrumentation inbound/outbound. |
| Log trong async task mất ID | Ngữ cảnh bị đứt khi chuyển thread | Kiểm tra executor instrumentation và `Context.current().wrap(...)`, tránh capture quá muộn. |
| Log có ID nhưng không mở được trace | Traces chưa export, sampled out, TTL khác nhau hoặc backend không hỗ trợ liên kết | Kiểm tra sampling, exporter, Collector pipeline, service.name và mapping trường. |
| Log bị duplicate | Nhiều appender hoặc thu stdout và OTLP cho cùng sự kiện | Xác định một tuyến chính hoặc lọc tuyến trùng ở Collector. |
| Context của request cũ xuất hiện trong request mới | Scope/MDC bị giữ qua thread pool, không khôi phục | Luôn đóng `Scope`, dọn MDC thủ công qua `finally`; không lưu span ID ở static/global. |

Các nguyên tắc vận hành cần giữ:
- **Không log secrets, token, cookie, mật khẩu hoặc toàn bộ baggage**. Baggage có thể được truyền qua ranh giới tin cậy và dễ lộ dữ liệu nếu dump trực tiếp.
- Không biến `trace_id` thành khóa định danh người dùng hoặc bằng chứng bảo mật; nó phục vụ correlation, không xác thực danh tính.
- Không cố in ID giả khi `SpanContext.isValid()` là `false`.
- Dùng sampling, log level, filter và retention phù hợp lưu lượng; OTel không loại bỏ nhu cầu quản trị chi phí log/trace.
- Bảo đảm cùng chính sách thời gian, định danh service và mapping trường tại điểm export/index; nếu không, hai signal vẫn có thể tồn tại nhưng khó liên kết.

## 10. Tự kiểm tra kiến thức

1. Vì sao `trace_id` thường không đổi khi request đi từ service A sang B, còn `span_id` lại thay đổi?
2. Trường hợp nào chỉ cần MDC + stdout, và trường hợp nào cần OTel log appender + OTLP?
3. Điều gì xảy ra với log correlation khi một task chạy trên executor mà không được propagate context?
4. Vì sao một log có trace ID hợp lệ vẫn có thể không tìm thấy trace tương ứng ở backend?
5. Làm sao phân biệt một lỗi thiếu instrumentation với việc log nằm ngoài span hợp lệ?

Một hệ thống đạt mục tiêu **tương thích OpenTelemetry** khi trace context được truyền chính xác, log event có ID thích hợp khi đang trong span, log/traces được xuất qua pipeline được chọn và người vận hành thực sự truy vấn tương quan được trên backend.

## Tài liệu tham khảo

- [OpenTelemetry – Java instrumentation và context propagation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry – Java agent: Getting started](https://opentelemetry.io/docs/zero-code/java/agent/getting-started/)
- [OTel Java agent – MDC log correlation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md)
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OpenTelemetry – Java API và Context](https://opentelemetry.io/docs/languages/java/api/)
- [OpenTelemetry – cấu hình exporter và propagators](https://opentelemetry.io/docs/languages/sdk-configuration/general/)