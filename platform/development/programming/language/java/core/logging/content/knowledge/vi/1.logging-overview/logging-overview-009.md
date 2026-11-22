# Logging và observability trong Java Core

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
- Phân biệt logging, monitoring và observability; chọn đúng logs, metrics hoặc traces để điều tra một hiện tượng trong ứng dụng Java.
- Thiết kế log có ngữ cảnh, mức độ ưu tiên, dữ liệu có cấu trúc và khả năng liên kết các bước xử lý của một request.
- Sử dụng java.util.logging (JUL) trong chương trình Java 17+, hiểu vai trò của SLF4J và các logging backend phổ biến.
- Hiểu cách thu thập, truyền, liên kết và khai thác telemetry để phát hiện sự cố, tìm nguyên nhân và đo tác động.
- Tránh các lỗi thường gặp về độ ồn, hiệu năng, dữ liệu nhạy cảm, context propagation và chi phí lưu trữ.

**Phạm vi:** Đây là kiến thức nền tảng của Java Core Logging. Những công cụ như OpenTelemetry, Logback, Log4j 2, Prometheus và hệ thống quan sát tập trung được nêu theo vai trò và điểm tích hợp; không yêu cầu một framework cụ thể để hiểu nguyên lý.

## 2. Logging khác observability thế nào?

**Logging** là việc ứng dụng ghi lại những sự kiện có ý nghĩa: đã nhận request, xử lý thành công, thử lại kết nối, gặp lỗi xác thực, gọi dịch vụ ngoài thất bại… Một log hữu ích trả lời được: *chuyện gì xảy ra, ở đâu, khi nào, trong ngữ cảnh nào và kết quả là gì?*

**Monitoring (giám sát)** thường theo dõi các chỉ số và điều kiện đã xác định trước: tỷ lệ lỗi, thời gian đáp ứng, mức sử dụng bộ nhớ, số request mỗi giây, dung lượng hàng đợi. Nó giúp nhận ra *có vấn đề*.

**Observability (khả năng quan sát)** là khả năng suy ra trạng thái và hành vi bên trong hệ thống từ những tín hiệu nó phát ra. Nó giúp trả lời cả những câu hỏi chưa lường trước, chẳng hạn: *vì sao chỉ request của một loại tác vụ lại chậm khi gọi dịch vụ tồn kho?* Log là một nguồn tín hiệu của observability, nhưng một hệ thống có nhiều log chưa chắc dễ quan sát.

Ví dụ: endpoint tra cứu đơn hàng bắt đầu có độ trễ p95 tăng từ 120 ms lên 1,8 s.

- **Metrics** cho thấy độ trễ tăng từ thời điểm nào, ảnh hưởng bao nhiêu phần trăm request và tỷ lệ lỗi có đổi không.
- **Traces** cho thấy phần thời gian bị tiêu tốn ở bước tra cơ sở dữ liệu, gọi HTTP hay xử lý bên trong JVM.
- **Logs** giải thích sự kiện cụ thể: kết nối bị timeout, một lần retry xảy ra, mã lỗi từ upstream hoặc đường xử lý bất thường.

Cần cả ba để đi từ **phát hiện → khoanh vùng → giải thích → xác nhận khắc phục**. Observability còn có thể dùng profiles, thread dumps và sự kiện vận hành; ba tín hiệu dưới đây là nền tảng phổ biến, không phải toàn bộ khả năng quan sát.

## 3. Ba nhóm tín hiệu: logs, metrics và traces

| Tín hiệu | Dữ liệu điển hình | Câu hỏi trả lời tốt | Hạn chế cần nhớ |
| --- | --- | --- | --- |
| **Logs** | Sự kiện có thời điểm, mức độ, thông điệp, thuộc tính, exception | Chính xác sự kiện nào xảy ra với request này? | Rất nhiều bản ghi; khó suy ra phân phối độ trễ chỉ từ log |
| **Metrics** | Counter, gauge, histogram với timestamp và nhãn | Tỷ lệ lỗi, thông lượng, p95/p99, mức tài nguyên có thay đổi không? | Số liệu tổng hợp thường không có chi tiết từng request |
| **Traces** | Một trace gồm các span có quan hệ cha–con và khoảng thời gian thực thi | Request đã đi qua các thành phần nào; bước nào chậm? | Có thể bị sampling; instrumentation không đầy đủ sẽ tạo khoảng trống |

**Một số khái niệm cốt lõi:**

- **Log record/event:** đơn vị ghi nhận sự kiện. Các trường thường có thời gian, severity, logger, message, event name, service và các ID liên kết.
- **Counter:** giá trị tăng theo số lần xảy ra sự kiện, ví dụ số request hoặc số lỗi. Dùng mức tăng theo khoảng thời gian để tính rate; lưu ý counter có thể reset khi process khởi động lại.
- **Gauge:** giá trị hiện thời có thể tăng hoặc giảm, ví dụ số tác vụ đang chạy, heap đang dùng.
- **Histogram:** phân bố quan sát, ví dụ thời gian đáp ứng. Dùng để đánh giá phần đuôi độ trễ (p95/p99), thay vì chỉ nhìn trung bình.
- **Trace:** hành trình logic của một hoạt động qua các thành phần. **Span** mô tả một công đoạn, có thời gian bắt đầu/kết thúc, thuộc tính, sự kiện và trạng thái.
- **Trace ID:** định danh toàn bộ hành trình; **span ID:** định danh một công đoạn trong trace. **Request ID** do ứng dụng/gateway đặt có thể hữu ích nhưng không tự động thay thế trace ID.

Một tình huống có thể tạo ra cả ba tín hiệu:

~~~text
HTTP GET /orders/42
  trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  [server span: GET /orders/{id}]
    [client span: GET inventory-service]
      [server span: inventory lookup]
          WARNING event=inventory_timeout trace_id=... request_id=req-42
  metric: http.server.request.duration (histogram)
  metric: http.server.request.count / failed_requests (counter)
~~~

Dấu ba chấm ở ví dụ trên chỉ là cách rút gọn khi minh họa; telemetry thực tế phải chứa giá trị ID đầy đủ. Một log có trace ID chỉ liên kết với trace khi ID được truyền và đưa vào log đúng cách; hệ thống không tự ghép tương quan chỉ vì đã bật logger.

## 4. Luồng logging và công cụ trong hệ sinh thái Java

Một luồng ghi log điển hình:

~~~text
Mã Java tạo log event
        |
   Logging API / facade
        |
  Logger + level + filter
        |
 Handler / Appender + formatter / encoder
        |
 Console / file / telemetry pipeline
        |
 Collector / lưu trữ / tìm kiếm / cảnh báo
~~~

**java.util.logging (JUL)** nằm trong JDK, dùng các thành phần chính:
- **Logger:** nơi ứng dụng phát bản ghi và cấu hình ngưỡng level.
- **LogRecord:** dữ liệu về một sự kiện (level, message, thời điểm, logger, exception…).
- **Handler:** nơi đưa bản ghi ra đích, như ConsoleHandler hoặc FileHandler.
- **Formatter:** chuyển LogRecord thành văn bản. Formatter có thể tạo text, XML hoặc dạng cấu trúc do bạn triển khai.
- **Filter:** quyết định bản ghi có được chấp nhận hay không.

Một bản ghi có thể bị chặn tại logger, filter hoặc handler. Chẳng hạn logger cho phép FINE nhưng ConsoleHandler đang ở INFO thì bản ghi FINE vẫn không xuất hiện. JUL sử dụng hệ level như **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

**SLF4J** là một facade: mã ứng dụng gọi một API thống nhất, còn nhà cung cấp logging thực sự (ví dụ Logback hoặc Log4j 2 qua provider tương ứng) xử lý log. Đây là cách phổ biến trong nhiều ứng dụng Java; nó không đồng nghĩa mọi dự án Java đều có SLF4J. Khi dùng SLF4J 2.x, cần provider tương thích và cấu hình tránh nhiều provider hoặc bridge hai chiều gây vòng lặp. JUL có thể được nối với một backend khác thông qua bridge được chọn cẩn thận. Java 9+ còn có **System.Logger** như một API logging của JDK.

Mức log nên phản ánh **ý nghĩa vận hành**, không phải độ dài thông điệp:

| Mức thường gặp | Tình huống phù hợp |
| --- | --- |
| ERROR / JUL SEVERE | Tác vụ quan trọng thất bại, không thể hoàn tất tại lớp này |
| WARN / JUL WARNING | Điều kiện bất thường, retry, fallback hoặc rủi ro; hệ thống còn xử lý được |
| INFO | Sự kiện nghiệp vụ/vòng đời có giá trị, lượng bản ghi được kiểm soát |
| DEBUG / JUL FINE | Chi tiết cần khi điều tra; thường tắt trong môi trường chạy thật |
| TRACE / JUL FINER, FINEST | Dòng xử lý rất chi tiết, có thể tốn chi phí lớn |

Tên level và ánh xạ giữa các framework không hoàn toàn giống nhau. Ví dụ, SEVERE của JUL không phải một tên level trong API SLF4J. Đừng dùng ERROR cho một request do người dùng nhập sai hợp lệ hoặc ghi mọi lần gọi hàm ở INFO.

## 5. Thiết kế log có cấu trúc và đủ ngữ cảnh

Thay vì một chuỗi khó phân tích như “Có lỗi!”, hãy ghi **tên sự kiện ổn định** và các trường rõ nghĩa. Một bản ghi JSON một dòng minh họa:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "severity": "WARN",
  "service.name": "inventory",
  "environment": "production",
  "event": "stock_lookup_failed",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "dependency": "inventory-db",
  "error.type": "ConnectionTimeoutException",
  "retry_count": 1
}
~~~

Đây là dữ liệu ví dụ, không phải định dạng bắt buộc cho JUL. Trong hệ thống thực tế, nên thống nhất schema từ đầu (tên thuộc tính, kiểu dữ liệu, cách biểu diễn severity và exception) để tra cứu, nhóm sự kiện và dựng dashboard nhất quán.

Các nguyên tắc thiết kế:

1. **Ghi đủ để hành động:** thời gian chuẩn có múi giờ (thường UTC), service, môi trường, phiên bản triển khai, tên event, mức độ, kết quả, ID liên kết và thông tin lỗi có ý nghĩa. Chọn chi tiết theo nhu cầu điều tra.
2. **Tên sự kiện ổn định:** ưu tiên event=payment_authorization_failed và những field như reason, gateway thay vì tạo hàng nghìn message khác nhau. Field không nên thay đổi kiểu tùy trường hợp.
3. **Ngữ cảnh nhất quán:** request_id, trace_id, span_id và mã thao tác phi nhạy cảm phải được đưa qua các lớp liên quan. Đừng giả định chỉ log từ thread hiện tại đã đủ để tìm toàn bộ request.
4. **Exception đúng chỗ:** ghi nguyên nhân và stack trace tại ranh giới xử lý thích hợp; tránh ghi cùng một exception ở mọi lớp rồi làm đầy hệ thống bằng bản sao. Nếu đã xử lý và khôi phục thành công, severity có thể là WARN/INFO tùy hợp đồng vận hành.
5. **Chỉ ghi dữ liệu được phép:** không ghi mật khẩu, access token, private key, cookie phiên, thông tin thanh toán hoặc payload nhạy cảm. Cần masking/redaction trước khi ghi và chính sách truy cập/lưu giữ rõ ràng.
6. **Tách dữ liệu khỏi message:** structured encoder hỗ trợ trích xuất và escaping tốt hơn ghép chuỗi thủ công. Đặc biệt, nội dung từ người dùng có thể chứa newline hoặc ký tự điều khiển gây log injection; cần mã hóa đúng định dạng.
7. **Không phụ thuộc vào thứ tự tuyệt đối:** log giữa các JVM/host có thể lệch đồng hồ, được buffer hoặc chuyển đến collector trễ. Dùng timestamp kèm ID và quan hệ span để tái dựng diễn biến; đừng kết luận quan hệ nhân quả chỉ từ thứ tự hiển thị.

**Một dấu hiệu log hữu ích:** khi gặp event=stock_lookup_failed, người trực hệ thống biết phải lọc theo trace_id/request_id, xem dependency, error.type, retry_count và thời điểm để khoanh vùng; họ không cần đoán từ câu văn tự do.

## 6. Ví dụ Java 17+ chạy độc lập với java.util.logging

Ví dụ dùng API có sẵn trong JDK để ghi hai sự kiện và đếm request/lỗi. Chương trình cố ý tạo một request thành công và một request thất bại; formatter nhỏ giúp output dễ đối chiếu.

Tạo tệp **LoggingObservabilityDemo.java**:

~~~java
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.*;

public class LoggingObservabilityDemo {
    private static final Logger LOG = Logger.getLogger(LoggingObservabilityDemo.class.getName());
    private static final LongAdder REQUESTS = new LongAdder();
    private static final LongAdder ERRORS = new LongAdder();

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                String message = record.getLevel().getName() + " " + record.getMessage();
                Throwable error = record.getThrown();
                return message + (error == null ? "" : " exception=" + error.getClass().getSimpleName())
                        + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            lookup("req-001", false);
            lookup("req-002", true);
            handler.flush();

            System.out.println("metric.requests_total=" + REQUESTS.sum());
            System.out.println("metric.errors_total=" + ERRORS.sum());
        } finally {
            LOG.removeHandler(handler);
        }
    }

    private static void lookup(String requestId, boolean shouldFail) {
        REQUESTS.increment();
        long start = System.nanoTime();
        try {
            if (shouldFail) throw new IllegalStateException("stock unavailable");
            LOG.info("event=stock_lookup_success requestId=" + requestId);
        } catch (IllegalStateException error) {
            ERRORS.increment();
            LOG.log(Level.WARNING, "event=stock_lookup_failed requestId=" + requestId, error);
        } finally {
            long durationNanos = System.nanoTime() - start;
            LOG.log(Level.FINE, () -> "event=stock_lookup_finished requestId=" + requestId
                    + " duration_ns=" + durationNanos);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 LoggingObservabilityDemo.java
java LoggingObservabilityDemo
~~~

Output trên **stdout** (đã kiểm tra bằng biên dịch/chạy thực tế):

~~~text
INFO event=stock_lookup_success requestId=req-001
WARNING event=stock_lookup_failed requestId=req-002 exception=IllegalStateException
metric.requests_total=2
metric.errors_total=1
~~~

Giải thích các điểm đáng chú ý:

- **LOG.setUseParentHandlers(false)** tránh việc record bị in thêm một lần bởi root logger khi ta gắn handler riêng.
- **StreamHandler** có buffer; gọi **handler.flush()** trước khi in counters bảo đảm thứ tự output của ví dụ. Formatter này cố tình chỉ in tên exception để output ổn định. **Trong sản xuất phải cấu hình hiển thị/thu thập stack trace cần thiết**, không dùng formatter rút gọn này làm mẫu chuẩn.
- Logger và handler đều đang ở **INFO**, nên sự kiện **FINE** đo duration không xuất hiện. Dùng supplier **() -> ...** giúp chỉ tạo message chi tiết khi level cho phép.
- **System.nanoTime()** phù hợp tính khoảng thời gian trong cùng process; nó không phải timestamp lịch. Để gắn mốc thời gian cho log, dùng timestamp thời gian thực có múi giờ.
- **LongAdder** là bộ đếm an toàn hơn cho trường hợp nhiều thread cùng tăng. Tuy nhiên các giá trị in ra ở đây chỉ là **counter trong bộ nhớ**, chưa phải metrics đã được export; một hệ giám sát thật cần bộ thu thập và cách công bố metrics thích hợp.
- Một bộ đếm tổng không cho biết p95/p99. Muốn theo dõi độ trễ, hãy ghi các quan sát thời gian vào **histogram** qua thư viện metrics và xuất chúng cho backend phù hợp.

Ví dụ này minh họa được **sự kiện cụ thể + định danh ngữ cảnh + số liệu tổng hợp**. Nó chưa tạo distributed traces; trace phải được instrument và truyền context khi có nhiều bước hoặc nhiều dịch vụ.

## 7. Liên kết log trong một luồng xử lý và qua các thread

Khi request đi qua controller → service → repository → HTTP client, có thể muốn mọi log cùng mang một **request_id**. Trong ứng dụng dùng SLF4J, **MDC (Mapped Diagnostic Context)** cho phép gắn thông tin vào ngữ cảnh logging của thread hiện tại.

Đoạn sau **chỉ là minh họa tích hợp**, cần dependency SLF4J, provider hỗ trợ MDC và cấu hình layout/encoder đọc key requestId (không tự biên dịch độc lập với JDK):

~~~java
import org.slf4j.MDC;

// Trong handler đã nhận được requestId hợp lệ:
try (MDC.MDCCloseable ignored = MDC.putCloseable("requestId", requestId)) {
    // Xử lý request; logger có thể đọc MDC["requestId"] qua cấu hình encoder.
    processRequest();
}
// Đã đóng scope; tránh rò requestId sang request kế tiếp trên cùng thread.
~~~

Với Logback pattern encoder, một trường minh họa có thể là **%X{requestId}**. Nếu dùng structured encoder, hãy cấu hình xuất requestId dưới dạng một thuộc tính riêng. Đừng giả định mọi backend hoặc mọi cấu hình đều xuất MDC tự động.

**Bẫy quan trọng với concurrency:** MDC thường gắn với thread; chuyển xử lý sang **ExecutorService, CompletableFuture**, luồng khác hoặc pipeline async có thể làm mất requestId, hoặc gây rò context nếu quên dọn. Hãy truyền đúng context bằng wrapper/task decorator hoặc cơ chế propagation tương thích với thư viện đang dùng; dọn context trong finally hoặc scope có đóng. Không giả định context tự lan truyền qua mọi executor, virtual thread hay reactive pipeline.

Trong **distributed tracing**, cần truyền ngữ cảnh qua ranh giới process (thường qua HTTP headers theo W3C Trace Context như traceparent). Một ví dụ traceparent hợp lệ:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần phải nhận, tạo child span khi cần và inject context vào lời gọi outbound. OpenTelemetry là một lựa chọn phổ biến để instrument Java và chuyển telemetry; việc trace_id/span_id tự xuất hiện trong log **phụ thuộc cấu hình instrumentation và logging integration**, không phải chức năng mặc định của JUL hay SLF4J. Phải kiểm chứng correlation trên request thật.

## 8. Từ instrumentation đến hệ thống quan sát

Một kiến trúc triển khai thường gặp:

~~~text
Java service
  |-- structured logs ---------|
  |-- request/DB latency metrics|--> agent/collector --> backends --> dashboards/search/alerts
  |-- trace spans --------------|
~~~

Các thành phần có vai trò khác nhau:

- **Instrumentation:** ghi nhận request count, duration, lỗi, những span quan trọng (HTTP, DB, queue), và sự kiện có ý nghĩa. Tự động instrumentation giảm công sức nhưng không thay thế việc thêm thông tin nghiệp vụ cần thiết.
- **Propagation:** giữ trace context xuyên qua thread/task và ranh giới mạng; giới hạn, xác thực và làm sạch dữ liệu context nhận từ nguồn không tin cậy khi thích hợp.
- **Collection/export:** console/file handler, agent hoặc SDK/collector nhận telemetry, buffer, batch, gửi đến nơi lưu trữ. Cần xét chi phí CPU, bộ nhớ, mạng, retry và chính sách khi đầu ra bị nghẽn.
- **Storage & queries:** log search theo event/service/request_id/trace_id; metrics cho truy vấn theo thời gian và phân vị; trace viewer cho cây span.
- **Alerting:** cảnh báo dựa vào triệu chứng người dùng chịu ảnh hưởng và mục tiêu dịch vụ, chẳng hạn tỷ lệ lỗi và độ trễ kéo dài; đừng chỉ cảnh báo vì có một dòng ERROR.

Nhiều đội theo dõi **four golden signals**: **latency, traffic, errors, saturation**. Ví dụ, nếu tỷ lệ lỗi HTTP tăng, hãy nhóm theo route và mã trạng thái ở mức nhãn có số lượng hữu hạn; tránh nhãn metrics chứa raw URL có ID, request_id, user_id hoặc trace_id vì **cardinality** bùng nổ. Dữ liệu định danh chi tiết thường phù hợp hơn với log/traces đã được kiểm soát quyền truy cập.

Các kỹ thuật như **trace sampling** giảm lượng trace lưu trữ, nhưng có thể khiến một trace cụ thể không xuất hiện trong backend. Đừng mặc định mọi log đều có trace để mở. **Log sampling/rate limiting** cũng giảm độ ồn nhưng phải cân nhắc những sự kiện cần giữ nguyên (ví dụ bản ghi phục vụ điều tra bảo mật theo chính sách riêng).

## 9. Quy trình điều tra sự cố với logs–metrics–traces

Giả sử số request thất bại tăng khi hệ thống gọi inventory-service:

1. **Phát hiện bằng metrics:** xem tỷ lệ lỗi, request rate, p95/p99 và thời gian bắt đầu biến động. Phân biệt lỗi tăng do lưu lượng, do dependency hay do một phiên bản deploy.
2. **Khoanh vùng bằng traces:** chọn trace của một request thất bại (nếu có), xác định span chậm hoặc thất bại, quan hệ cha–con và endpoint/dependency bị ảnh hưởng. Một span dài không tự động chứng minh bên trong span là thủ phạm; cần xem các span con và dữ liệu bổ sung.
3. **Giải thích bằng logs:** lọc đúng service, khoảng thời gian, trace_id hoặc request_id; xem event, error.type, retry_count và log exception. Đối chiếu các node vì dữ liệu có thể tới nơi tập trung trễ.
4. **Kiểm tra giả thuyết:** so sánh khoảng thời gian trước/sau deploy, số connection bận, timeout, thread pool, GC hoặc giới hạn downstream tùy dấu hiệu thực tế. Không kết luận chỉ từ một message.
5. **Xác nhận sau sửa:** so sánh error rate, latency histogram và những trace/log mẫu trong cùng bối cảnh tải; bảo đảm triệu chứng người dùng thực sự giảm.

Nếu **metrics báo lỗi nhưng không tìm được log**, kiểm tra level/filter, pipeline, thời gian, service labels, redaction và việc ghi tại boundary phù hợp. Nếu **log có trace_id nhưng trace thiếu**, kiểm tra propagation, export, sampling và kết nối backend. Nếu **trace có span thiếu**, xem instrumentation tại bước đó, đừng lập tức suy diễn là bước không chạy.

## 10. Chi phí, độ tin cậy và bảo vệ dữ liệu

**Hiệu năng và mức độ ồn**
- Tránh tạo chuỗi lớn, JSON thủ công tốn kém hoặc serialize object nhạy cảm khi level tương ứng đang tắt; dùng parameterized logging/supplier của API tương ứng.
- Không ghi log cho từng phần tử của vòng lặp khối lượng lớn ở INFO/ERROR. Chọn event tại boundary, tổng hợp counters và bật DEBUG có thời hạn khi điều tra.
- Async logging/queue có thể giảm độ trễ trên luồng request, nhưng có thể **chặn, làm chậm hoặc bỏ log** khi đầy; phải hiểu chính sách backpressure, flush và shutdown của backend cụ thể.
- Chọn retention, mức log theo môi trường, log volume budget và sampling dựa vào giá trị điều tra. Cần theo dõi sức khỏe **của chính pipeline telemetry** (dropped events, queue fullness, exporter failures).

**Độ đúng**
- Ghi thời gian sự kiện (wall-clock timestamp) và đo duration bằng đồng hồ monotonic; định nghĩa rõ đơn vị ms, µs hoặc ns.
- Phân biệt lỗi đã xử lý có fallback và lỗi trả về người dùng. Severity phải nhất quán để alert không tăng giả.
- Tránh ghi exception nhiều tầng; ghi lỗi ở nơi có quyết định xử lý và giữ nguyên cause chain.
- Thông tin như service version, deployment, environment và route template giúp điều tra biến động theo release.

**Bảo mật và quyền riêng tư**
- Không log password, bearer token, API key, session cookie, dữ liệu thẻ thanh toán hoặc toàn bộ request/response body một cách mặc định.
- Redaction phải diễn ra trước khi dữ liệu đi tới console, file, collector hoặc backend; giới hạn ai có thể xem, xuất, lưu và xóa log.
- Trace attributes và MDC cũng có thể rò dữ liệu; việc không ghi vào message không có nghĩa dữ liệu đã an toàn.
- Không dùng dữ liệu không tin cậy làm tên metric label key hoặc tên event không kiểm soát; kiểm soát cả kích thước và cardinality của thuộc tính.

## 11. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ ghi “Error happened” | Không biết lớp xử lý, request, nguyên nhân | Thêm event name, service, correlation ID, error.type và exception phù hợp |
| Dùng ERROR cho mọi trường hợp dự kiến | Dashboard/cảnh báo nhiễu | Phân biệt lỗi vận hành và kết quả nghiệp vụ hợp lệ |
| Gắn request_id vào mọi metric label | Time series tăng theo số request | Dùng nhãn thấp cardinality như route template, method, status |
| Dùng thời gian hệ thống để đo duration | Sai lệch khi đồng hồ thay đổi | Dùng System.nanoTime()/timer thích hợp |
| Cho rằng MDC tự qua thread pool | Log mất hoặc dính ID của request khác | Truyền context và dọn ở mọi scope |
| Coi log có trace_id là chắc chắn có trace | Điều tra đứt mạch do sampling/export | Kiểm tra propagation, sampling và backend integration |
| Ghi toàn bộ object/request | Lộ dữ liệu; CPU, lưu trữ tăng | Chọn field cần thiết, redact dữ liệu nhạy cảm |
| Tự tin vào một log dòng cuối | Bỏ sót lỗi bị nuốt, xử lý song song | Đối chiếu metrics, spans, logs và các dấu hiệu độc lập |

## 12. Tự kiểm tra và vận dụng

**Tình huống A:** Độ trễ p99 tăng nhưng tỷ lệ lỗi không đổi. Nên bắt đầu bằng gì?  
**Gợi ý:** Kiểm tra duration histogram và lưu lượng theo route, sau đó chọn traces chậm để xem bước chiếm thời gian. Log riêng lẻ không đủ để thấy phân bố độ trễ.

**Tình huống B:** Log từ controller có request_id nhưng log trong CompletableFuture không có. Vì sao?  
**Gợi ý:** Logging context gắn với thread có thể không được truyền sang executor. Cần cơ chế propagation phù hợp và dọn context sau xử lý.

**Tình huống C:** Dashboard metrics có một chuỗi mới cho mỗi customerId. Sai ở đâu?  
**Gợi ý:** Customer ID là nhãn có cardinality cao. Sửa nhãn thành phân loại hữu hạn phục vụ truy vấn tổng hợp; chi tiết từng khách hàng (nếu hợp lệ) nên nằm trong telemetry có quyền truy cập và bảo vệ dữ liệu.

**Bài thực hành đề xuất:** Chạy chương trình JUL ở mục 6; đổi mức logger và handler từ INFO sang FINE để thấy bản ghi duration, quan sát giá trị thay đổi theo mỗi lần chạy. Sau đó mô tả một schema log ổn định cho sự kiện order_lookup_failed và ba metrics phục vụ quan sát endpoint: tổng request, tổng lỗi và histogram thời gian đáp ứng. Giải thích vì sao ba tín hiệu bổ sung cho nhau và thời điểm nào bạn sẽ tìm trace_id.
