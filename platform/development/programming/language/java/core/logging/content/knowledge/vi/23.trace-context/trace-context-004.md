# Liên kết log với trace trong Java

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao một `trace_id` giúp nối các dòng log của nhiều dịch vụ thành một luồng xử lý, phân biệt `trace_id` với `span_id`, đưa hai định danh này vào log Java, truyền trace context qua HTTP/tác vụ bất đồng bộ và kiểm tra việc liên kết bằng dữ liệu thực tế.

## 1. Log và distributed trace bổ sung cho nhau như thế nào?

- **Log** ghi một sự kiện cụ thể: request đến, truy vấn thất bại, thanh toán được duyệt, exception xảy ra. Log trả lời “đã xảy ra điều gì?”.
- **Trace** mô tả đường đi của một tác vụ xuyên suốt các thành phần. Một trace gồm nhiều **span**; mỗi span đại diện cho một công việc có thời điểm bắt đầu, kết thúc, quan hệ cha–con và thuộc tính. Trace trả lời “công việc đi qua đâu, mất thời gian ở đâu?”.
- **Liên kết log với trace (log correlation)** là ghi định danh của trace/span đang hoạt động vào log tại thời điểm sự kiện xảy ra. Từ một dòng log có thể tìm trace tương ứng, và từ một span có thể truy vấn các dòng log liên quan nếu hệ thống lưu trữ hỗ trợ liên kết này.

Một request `POST /orders` có thể lần lượt đi qua `api-gateway` → `orders` → `payments`. Nếu mỗi dịch vụ chỉ log “processing request”, rất khó biết ba dòng log có cùng một giao dịch hay không khi nhiều request chạy đồng thời. Khi trace context được truyền đúng, các log đều mang **cùng `trace_id`**; `span_id` xác định công việc cụ thể đang ghi log.

| Trường | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `trace_id` | Định danh của toàn bộ trace | Giữ nguyên trong các span thuộc cùng trace; theo W3C Trace Context là 16 byte, biểu diễn bằng 32 ký tự hex |
| `span_id` | Định danh span hiện tại | 8 byte, biểu diễn bằng 16 ký tự hex; thay đổi khi chuyển sang span khác |
| `service.name` hoặc `service` | Dịch vụ phát sinh sự kiện | Cho biết log đến từ thành phần nào; không thay thế trace ID |
| `timestamp`, `level`, `message` | Thời gian, mức độ, nội dung sự kiện | Giúp đọc và lọc log; nên dùng định dạng có cấu trúc |
| `request_id` / business ID | Mã request do ứng dụng cấp hoặc mã nghiệp vụ | Có thể hữu ích song song; không mặc nhiên đồng nghĩa `trace_id` |

Không nên đồng nhất một **trace** với một **request HTTP duy nhất**: trace có thể bao gồm nhiều RPC, message hoặc tác vụ con. Ngược lại, nếu thiếu cơ chế truyền context, một request liên dịch vụ có thể bị tách thành nhiều trace khác nhau.

## 2. Trace context đi qua các dịch vụ

Với HTTP, chuẩn W3C Trace Context định nghĩa header `traceparent` có dạng:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             vv-<trace-id 32 hex>---------------<parent-id 16 hex>-ff
```

Trong ví dụ: `00` là phiên bản; phần 32 hex là trace ID; `00f067aa0ba902b7` là span ID của phía gửi (parent ID được truyền đi); `01` là cờ sampling được bật. Giá trị `01` không bảo đảm rằng trace sẽ được lưu trữ thành công ở backend. Một trace ID hoặc span ID toàn số 0 là không hợp lệ theo chuẩn này.

Luồng điển hình:

1. **Nhận request.** Bộ nhận context (propagator) đọc `traceparent`/`tracestate` được chấp nhận từ phía trước; nếu không có context hợp lệ, hệ thống tracing có thể tạo trace mới.
2. **Tạo/activate server span.** Dịch vụ `orders` có một span hiện tại; các log trong phạm vi span đó lấy `trace_id` và `span_id` từ context đang active.
3. **Gọi dịch vụ tiếp theo.** HTTP client instrumentation đưa context hiện tại vào header outbound. `payments` nhận context và tạo span con với span ID mới nhưng tiếp tục dùng trace ID cũ.
4. **Ghi và thu thập dữ liệu.** Dịch vụ xuất log có trường trace/span; tracing SDK/agent xuất span tới collector/backend. Hệ thống quan sát có thể lọc log theo trace ID và đối chiếu thời gian/span.

Ví dụ ba sự kiện thuộc một trace:

```json
{"service":"orders","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","message":"Order accepted"}
{"service":"payments","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"b7ad6b7169203331","message":"Payment approved"}
{"service":"orders","level":"INFO","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","message":"Response sent"}
```

Hai span ID khác nhau **không phải lỗi**: chính sự thay đổi này cho thấy log được ghi trong những công việc khác nhau của cùng trace. Để tạo ra sự liên kết, chỉ bổ sung trường vào log là chưa đủ; context phải được truyền và kích hoạt đúng ở nơi thực thi.

## 3. Ví dụ Java 17 chạy độc lập: cơ chế gắn định danh vào log

Ví dụ sau dùng `ThreadLocal` để mô phỏng “context hiện tại” và in log theo định dạng nhất quán. Nó cố ý dùng ID cố định để output có thể kiểm chứng; **không phải thư viện distributed tracing**, không thực hiện HTTP propagation, không tạo/xuất span và không nên tự sao chép cách sinh ID này vào production.

Lưu thành `TraceLogDemo.java`:

```java
public class TraceLogDemo {
    record TraceIds(String traceId, String spanId) {}

    private static final ThreadLocal<TraceIds> CURRENT = new ThreadLocal<>();

    static void inSpan(TraceIds ids, Runnable work) {
        TraceIds previous = CURRENT.get();
        CURRENT.set(ids);
        try {
            work.run();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    static void log(String service, String event) {
        TraceIds ids = CURRENT.get();
        String traceId = ids == null ? "-" : ids.traceId();
        String spanId = ids == null ? "-" : ids.spanId();
        System.out.printf(
                "service=%s trace_id=%s span_id=%s event=%s%n",
                service, traceId, spanId, event);
    }

    public static void main(String[] args) {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";

        inSpan(new TraceIds(traceId, "00f067aa0ba902b7"),
                () -> log("orders", "order-created"));
        inSpan(new TraceIds(traceId, "b7ad6b7169203331"),
                () -> log("payments", "payment-approved"));

        log("orders", "background-idle");
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac TraceLogDemo.java
java TraceLogDemo
```

Stdout chính xác:

```text
service=orders trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 event=order-created
service=payments trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331 event=payment-approved
service=orders trace_id=- span_id=- event=background-idle
```

`inSpan` đặt context trước khi chạy công việc và **khôi phục context trước đó trong `finally`**, kể cả khi có exception. Vì vậy, log `background-idle` không vô tình mang trace ID của tác vụ đã kết thúc. Trong chương trình thực, việc quản lý span, active context và propagation nên giao cho tracing SDK/instrumentation.

## 4. Tích hợp với OpenTelemetry, SLF4J và Logback

Một cách triển khai thực tế ở hệ sinh thái Java là:

- Dùng **OpenTelemetry** (SDK hoặc Java agent/instrumentation tương thích) để tạo span, quản lý active context, trích xuất/chèn trace header và xuất dữ liệu tracing.
- Dùng **SLF4J** làm API logging, với một logging backend như **Logback** để định dạng và xuất log.
- Đưa `trace_id` và `span_id` của **span hiện tại** vào **MDC** (Mapped Diagnostic Context) hoặc các thuộc tính log có cấu trúc. MDC gắn metadata vào log của luồng đang xử lý; bản thân MDC không phải distributed trace context.
- Đảm bảo log collector/backend thực sự nhận và lập chỉ mục các trường này, tốt nhất dưới dạng field riêng, để có thể tìm kiếm và liên kết với trace.

**Chọn một cơ chế điền trường**: nếu OpenTelemetry Java agent hoặc logging instrumentation hiện dùng đã tự đưa trace/span ID vào MDC/log record, hãy dùng tính năng đó và xác minh tên field được xuất. Tránh tự chèn thêm làm sinh dữ liệu trùng hoặc ghi đè không nhất quán. Tên khóa có thể khác giữa agent, logging adapter và backend (ví dụ `trace_id` so với `traceId`); cấu hình thống nhất từ nguồn tới nơi truy vấn.

### Minh họa cách điền MDC theo active span

Đây là một **lớp tích hợp** cho ứng dụng đã có các dependency tương thích `io.opentelemetry:opentelemetry-api`, `org.slf4j:slf4j-api` và SLF4J provider, đồng thời đã khởi tạo tracing ở nơi khác. Đoạn này không tự tạo span, không tự khởi động SDK/collector và không chứa `main` độc lập:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

import java.util.Map;

public final class TraceMdc {
    private TraceMdc() {}

    public static void runWithCurrentSpan(Runnable action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            SpanContext span = Span.current().getSpanContext();

            if (span.isValid()) {
                MDC.put("trace_id", span.getTraceId());
                MDC.put("span_id", span.getSpanId());
            } else {
                MDC.remove("trace_id");
                MDC.remove("span_id");
            }

            action.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
```

Ở nơi đang có một span active, có thể gọi `TraceMdc.runWithCurrentSpan(() -> logger.info("Payment approved"));`. Nếu `Span.current()` không hợp lệ, không nên gán ID giả để tạo cảm giác log đã liên kết. Việc lưu và khôi phục snapshot MDC trong `finally` tránh rò rỉ metadata sang một công việc khác trên thread được tái sử dụng.

Ví dụ một phần cấu hình `logback.xml` khi bạn **chủ động** sử dụng các khóa MDC `trace_id`, `span_id`:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level trace_id=%X{trace_id} span_id=%X{span_id} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Pattern giúp nhìn thấy ID khi debug, nhưng trong môi trường nhiều dịch vụ nên cân nhắc **structured JSON logging** để các trường `trace_id`/`span_id` được lưu thành thuộc tính riêng, tránh phụ thuộc vào regex phân tích chuỗi. Với các dòng log ngoài span, trường có thể trống hoặc bị bỏ qua theo cấu hình. Đừng coi mọi dòng log thiếu trace ID là lỗi; sự kiện startup, cron độc lập hoặc health check chưa có active span có thể thuộc trường hợp này.

## 5. Bất đồng bộ: nơi dễ mất liên kết nhất

Active OpenTelemetry context và MDC thường liên quan đến phạm vi thực thi hiện tại, hay dùng cơ chế theo thread. Khi chuyển qua `ExecutorService`, thread pool, `CompletableFuture`, callback, scheduler hoặc consumer message, không được giả định context tự di chuyển sang thread khác.

Với OpenTelemetry API, một cách truyền active context vào một `Runnable` là capture nó ở thread gọi rồi bao công việc khi gửi qua executor:

```java
// Minh họa tại nơi đã có Executor và tracing SDK/instrumentation.
io.opentelemetry.context.Context captured =
        io.opentelemetry.context.Context.current();

executor.execute(captured.wrap(() ->
        TraceMdc.runWithCurrentSpan(() ->
                logger.info("Async payment event"))));
```

Ở đây `captured.wrap(...)` giúp active tracing context có mặt khi callback chạy; `TraceMdc` điền lại MDC ngay trong thread thực thi. Đây là **đoạn tích hợp**, cần các biến `executor`, `logger`, dependency và active span thích hợp từ ứng dụng. Instrumentation tự động của framework cũng có thể đảm nhiệm propagation, nên kiểm tra trước khi tự bọc nhiều lớp.

Với message queue, cần truyền context trong message headers lúc publish và extract nó khi consume; bản thân việc đưa `trace_id` vào log chỉ phục vụ truy vấn, không khôi phục quan hệ cha–con của trace. Với HTTP cũng vậy: hãy dùng propagator/instrumentation của tracing thay vì tự sao chép chuỗi trace ID và tự đặt `span_id`.

## 6. Kiểm chứng bằng tình huống thực tế

Giả sử người dùng gọi `orders`, dịch vụ này gọi `payments` rồi trả lỗi timeout. Cách kiểm tra liên kết log/trace:

1. Gửi một request có thể nhận diện bằng thời gian và endpoint. Xác nhận server span ở `orders` được tạo và các dòng log trong phạm vi request có `trace_id` hợp lệ.
2. Trong log của `payments`, tìm cùng `trace_id`. `span_id` có thể khác vì đó là span của `payments`. Kiểm tra cây trace có quan hệ giữa span gọi HTTP và span xử lý HTTP tương ứng.
3. Truy vấn log theo `trace_id` và sắp xếp thời gian; đối chiếu sự kiện timeout với duration, lỗi và attributes của các span. Không suy ra thời gian tuần tự chỉ từ thứ tự log nếu đồng hồ giữa máy lệch hoặc tác vụ chạy song song.
4. Kiểm tra các nhánh async, exception và request liên tiếp trên cùng thread pool: log không được giữ lại trace ID của request trước; context phải được reset/restore.
5. Kiểm tra log và trace được gửi đến đúng backend, các field được parse thành thuộc tính truy vấn được, và liên kết điều hướng (nếu có) dùng cùng cách đặt tên ID.

Ví dụ một phép lọc theo thuộc tính trong hệ thống log có hỗ trợ field này (cú pháp phụ thuộc nhà cung cấp):

```text
trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
```

Nếu tìm thấy log nhưng không thấy trace, **chưa thể kết luận correlation sai**. Trace có thể không được lấy mẫu, bị lỗi export, hết thời gian lưu hoặc bị thu thập ở backend khác. Ngược lại, có trace nhưng không có log có thể do mức log, cấu hình appender, pipeline lọc hoặc MDC chưa được điền ở thời điểm ghi.

## 7. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra hoặc sửa |
| --- | --- | --- |
| Mỗi dịch vụ có `trace_id` khác nhau | Không inject/extract `traceparent`; thiếu instrumentation ở HTTP client/server hoặc queue | Kiểm tra header outbound/inbound và cấu hình propagator |
| `trace_id` đúng nhưng `span_id` sai/cũ | MDC được điền một lần ở đầu request, sau đó active span đã thay đổi | Đọc ID từ span đang active ở thời điểm log; dùng logging instrumentation theo span |
| Thread pool log mang trace của request trước | Không dọn/khôi phục MDC hoặc scope context | Dùng `try/finally`, đóng span scope, restore context và kiểm thử reuse thread |
| Log trong callback không có trace ID | Tracing context/MDC không được truyền sang callback | Truyền context rõ ràng hoặc bật instrumentation hỗ trợ async |
| Log có ID nhưng UI không tìm ra trace | Sampling, exporter, collector, retention hoặc khác backend | Kiểm tra trạng thái sampling, pipeline và thời gian lưu; không tự tạo fake trace |
| Log là text khó tìm `trace_id` | Pattern in thiếu field hoặc collector không parse đúng | Xuất log có cấu trúc, chuẩn hóa field name và kiểu dữ liệu |
| Có `request_id` nhưng không tìm được trace | Mã request nghiệp vụ bị nhầm với tracing identifier | Ghi `request_id` riêng, bổ sung `trace_id` lấy từ tracing context |

### Lưu ý về bảo mật và vận hành

- `traceparent` và baggage từ phía ngoài là **dữ liệu đầu vào**, không phải bằng chứng xác thực danh tính. Thiết lập chính sách trust/propagation phù hợp; không lấy bất kỳ header tùy ý nào rồi tin đó là trace context hợp lệ.
- Không ghi access token, mật khẩu, dữ liệu thẻ, PII hoặc toàn bộ baggage chưa lọc vào log chỉ vì muốn dễ liên kết; tracing cũng có thể mang dữ liệu nhạy cảm trong attributes.
- `trace_id` là định danh có số lượng giá trị rất lớn. Cân nhắc chiến lược index, chi phí và retention của log backend; không biến mỗi trace ID thành một label gây bùng nổ cardinality trong hệ thống không phù hợp.
- Một trace có thể không được sampling/export nhưng log vẫn mang trace ID hợp lệ. Đừng dùng “không thấy trace trên UI” như tiêu chí duy nhất để xác định logic ứng dụng thất bại.

## 8. Tiêu chí hoàn thành

Một triển khai liên kết log với trace có thể coi là hoạt động đúng khi: request xuyên nhiều dịch vụ giữ cùng `trace_id`; mỗi log lấy `span_id` của span thực sự đang active; propagation qua HTTP/queue/async được kiểm tra; context được khôi phục sau mỗi công việc; log có các field truy vấn được tại backend; và kết quả tra cứu log–trace khớp với dữ liệu tracing được thu thập. Các phép thử này nên bao gồm cả luồng thành công, lỗi và xử lý đồng thời.