# Ghi Correlation ID vào log trong Java

## 1. Mục tiêu và ranh giới của bài học

Sau khi ứng dụng **tạo hoặc nhận** một Correlation ID và **truyền** nó qua HTTP hay message, bước tiếp theo là làm cho ID này xuất hiện trong các sự kiện log. Nếu chỉ mang ID trong header nhưng không ghi vào log, người vận hành vẫn khó nối các sự kiện giữa controller, service và các hệ thống phụ thuộc.

Ví dụ: một request có `correlationId=corr-42` đi qua ba bước:

```text
INFO  cid=corr-42 event=order.received orderId=o-17
INFO  cid=corr-42 event=inventory.reserved orderId=o-17
ERROR cid=corr-42 event=payment.failed orderId=o-17 errorCode=TIMEOUT
```

Ở đây **cùng một Correlation ID** giúp người đọc ghép các log thành một luồng xử lý, còn `event` và `orderId` cho biết điều gì đã xảy ra với thực thể nào.

**Phạm vi bài này:** đưa ID đã được kiểm tra ở ranh giới đầu vào vào logging context, cấu hình đầu ra để thật sự ghi ID, bảo đảm không rò ID giữa các công việc, và xác minh bản ghi được tạo ra. Cách **tạo, nhận và truyền** ID đã nằm ở các bài trước; cách **tìm** ID trong log nằm ở bài tiếp theo.

## 2. Phải phân biệt ba bước: có ID, gắn context và xuất ra log

Việc một chuỗi được lưu trong biến Java **không đồng nghĩa** ID đã được ghi vào log.

| Bước | Ví dụ | Nếu bỏ qua |
| --- | --- | --- |
| Có ID tin cậy | `String correlationId = ...` | Không có khóa liên kết hoặc dùng giá trị không được kiểm tra |
| Gắn ID vào ngữ cảnh logging | `MDC.put("correlationId", correlationId)` | Logger không biết ID của công việc hiện tại |
| Cấu hình nơi xuất log | `%X{correlationId}` trong Logback | Context có ID nhưng log text không hiển thị ID |

Đối với structured logging, bước thứ ba là cấu hình encoder/collector phát ra **field riêng**, chẳng hạn `correlationId`, thay vì chỉ nhúng chuỗi vào `message`.

**MDC không tự gửi ID qua mạng** và cũng không thay thế việc truyền header/message property. Nó là cơ chế lưu các cặp khóa–giá trị để logging backend sử dụng trong **ngữ cảnh thực thi hiện tại**.

## 3. Ví dụ Java với SLF4J MDC và Logback

Ví dụ sau giả định project đã có `slf4j-api` và một logging provider hỗ trợ MDC, chẳng hạn `logback-classic`. Tên khóa `correlationId` là **quy ước của ứng dụng**, không phải tên bắt buộc của SLF4J.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class CorrelationLoggingExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(CorrelationLoggingExample.class);
    private static final String CORRELATION_KEY = "correlationId";

    private CorrelationLoggingExample() {}

    public static void processOrder(String correlationId, String orderId) {
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("Missing correlationId");
        }

        // Lưu context cũ vì phương thức có thể chạy lồng trong context khác.
        String previous = MDC.get(CORRELATION_KEY);
        try {
            MDC.put(CORRELATION_KEY, correlationId);
            LOG.info("event=order.received orderId={}", orderId);

            try {
                reserveInventory(orderId);
                LOG.info("event=inventory.reserved orderId={}", orderId);
            } catch (RuntimeException error) {
                LOG.error("event=inventory.failed orderId={}", orderId, error);
                throw error;
            }
        } finally {
            // Tránh để thread tái sử dụng mang ID của request trước.
            if (previous == null) {
                MDC.remove(CORRELATION_KEY);
            } else {
                MDC.put(CORRELATION_KEY, previous);
            }
        }
    }

    private static void reserveInventory(String orderId) {
        // Chỉ là thao tác minh họa, không gọi kho dữ liệu thật.
    }

    public static void main(String[] args) {
        processOrder("corr-42", "o-17");
    }
}
```

Điều quan trọng trong ví dụ:

- Dùng `MDC.put` **trước khi phát sự kiện** cần gắn Correlation ID.
- Dùng placeholder `{}` cho dữ liệu nghiệp vụ, không nối chuỗi thủ công chỉ để ghi ID.
- Truyền đối tượng `Throwable` vào `LOG.error` để backend có thể lưu stack trace; Correlation ID **không thay thế** thông tin lỗi.
- Khôi phục hoặc xóa ID trong `finally`, kể cả khi xảy ra exception.
- Không tạo ID mới ở mỗi lần gọi `LOG.info`; các log trong cùng công việc phải dùng cùng ID theo hợp đồng.

Nếu biết chắc đây là scope mới và không cần giữ context lồng nhau, SLF4J còn có `MDC.putCloseable(key, value)` để tự loại bỏ khóa khi rời `try-with-resources`. Tuy nhiên, phương thức này **loại bỏ khóa** khi đóng chứ không tự khôi phục giá trị cũ; vì thế ví dụ trên lưu `previous` để bảo vệ ngữ cảnh lồng nhau.

## 4. Cấu hình Logback để in giá trị từ MDC

Ví dụ `src/main/resources/logback.xml` cho Logback:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] cid=%X{correlationId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Với cấu hình này, các dòng log có thể hiển thị:

```text
2026-11-16T10:00:00.120 INFO  [main] cid=corr-42 CorrelationLoggingExample - event=order.received orderId=o-17
2026-11-16T10:00:00.125 INFO  [main] cid=corr-42 CorrelationLoggingExample - event=inventory.reserved orderId=o-17
```

Nếu quên `%X{correlationId}`, hai lời gọi `LOG.info` vẫn chạy nhưng bản ghi text **không xuất ID**, dù `MDC.get("correlationId")` có giá trị đúng. Cú pháp này dành cho PatternLayout của **Logback**; logging backend khác có thể yêu cầu cấu hình khác.

Đối với backend đã xuất JSON, nên giữ một field riêng:

```json
{
  "timestamp": "2026-11-16T10:00:00.120Z",
  "level": "INFO",
  "service": "order-service",
  "correlationId": "corr-42",
  "event": "order.received",
  "orderId": "o-17",
  "message": "Order received"
}
```

Đây là **ví dụ về cấu trúc mong muốn**, không phải kết quả mặc định của cấu hình XML ở trên. Việc đưa MDC vào JSON phụ thuộc encoder/provider và pipeline thu thập log thực tế. Cần xác nhận schema sau khi log đến hệ thống tập trung.

## 5. Nên ghi gì cùng Correlation ID?

Correlation ID giúp **liên kết** sự kiện, nhưng không đủ để giải thích sự kiện. Một logging contract thực tế nên xác định:

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| `correlationId` | Liên kết sự kiện theo luồng xử lý | Giữ nhất quán tên và định dạng giữa các service |
| `timestamp` | Xếp sự kiện theo thời gian | Đồng bộ đồng hồ và chỉ rõ timezone |
| `level` | Mức độ nghiêm trọng | Không phải mọi sự cố đều là `ERROR` |
| `service` | Xác định nguồn phát log | Có ích khi nhiều JVM cùng ghi vào một nơi |
| `event` hoặc `eventCode` | Phân loại loại sự kiện | Ưu tiên giá trị có hợp đồng ổn định |
| `requestId`, `messageId` | Định danh request/message cụ thể | Có thể khác Correlation ID |
| `traceId`, `spanId` | Liên kết với distributed tracing | Không mặc nhiên bằng Correlation ID |
| `errorCode` | Mã lỗi có thể tìm kiếm | Không thay stack trace hoặc nguyên nhân |

Ví dụ một Correlation ID có thể xuất hiện qua nhiều sự kiện, còn `event` phải cho biết hành động cụ thể. Không được xem Correlation ID là **idempotency key**, token xác thực hay mã định danh duy nhất của người dùng.

## 6. Ranh giới thread, async và reactive

MDC thường gắn với ngữ cảnh thread của logging provider. Vì vậy, đoạn mã sau **không bảo đảm** log trong công việc bất đồng bộ sẽ thấy cùng ID:

```java
MDC.put("correlationId", "corr-42");
executor.execute(() -> LOG.info("event=async.started"));
MDC.remove("correlationId");
```

Worker có thể chạy trên thread khác, ở thời điểm khác; việc đọc MDC trong lambda không tự tạo cơ chế truyền ngữ cảnh. Với thread pool, lỗi còn có thể xuất hiện theo chiều ngược lại: **ID bị giữ lại** trên worker và lẫn sang tác vụ kế tiếp.

Một cách minh họa cho executor thông thường là **chụp giá trị ở nơi submit** và gắn trong worker:

```java
String idAtSubmission = MDC.get("correlationId");
executor.execute(() -> {
    String previous = MDC.get("correlationId");
    try {
        if (idAtSubmission == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", idAtSubmission);
        }
        LOG.info("event=async.started");
        // Thực hiện công việc của tác vụ tại đây.
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
});
```

Đoạn này minh họa **một khóa**; nếu ứng dụng dùng nhiều thuộc tính MDC, cần sao chép/khôi phục context đầy đủ theo hợp đồng và kiểm tra không rò dữ liệu nhạy cảm.

Với Reactor/WebFlux, coroutine, virtual thread, task executor hoặc instrumentation tự động, cơ chế truyền context thay đổi theo framework/provider. Không giả định `ThreadLocal`/MDC truyền đúng qua mọi chuyển tiếp. Dùng cơ chế context propagation phù hợp, sau đó kiểm chứng các log thực tế trên từng ranh giới.

## 7. Gắn Correlation ID tại ranh giới HTTP

Ở ứng dụng web, nơi hợp lý để gắn ID cho log là **filter hoặc middleware** chạy sau bước kiểm tra/chuẩn hóa ID đầu vào và trước xử lý nghiệp vụ:

```text
HTTP request
  → nhận và kiểm tra correlationId
  → gắn vào logging context
  → controller / service / repository phát log
  → tạo HTTP response
  → dọn hoặc khôi phục logging context
```

Không nên để mỗi service tự `MDC.put` một ID mới. Cũng không được tin mù quáng giá trị header do client cung cấp: cần hợp đồng về chiều dài, ký tự cho phép, nguồn tin cậy và giá trị mặc định. Thao tác trả lại Correlation ID trong response header là quyết định của API contract, không phải tác dụng tự động của MDC.

Nếu request được xử lý bất đồng bộ sau khi filter kết thúc, phải chuyển ID đến công việc mới bằng cơ chế được hỗ trợ; không kỳ vọng MDC của request thread còn tồn tại.

## 8. Những lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `cid=` trống dù đã `MDC.put` | Pattern dùng nhầm tên key hoặc provider không hỗ trợ | Đồng bộ key giữa Java, cấu hình và backend |
| ID xuất hiện ở log đầu nhưng mất ở worker | Không truyền context sang executor | Chụp và gắn context trong worker, dọn đúng scope |
| Request B mang ID của request A | Không `remove`/khôi phục MDC trên thread pool | Dọn trong `finally` và kiểm tra chạy liên tiếp |
| Text log có ID, JSON log không có | Encoder/collector chưa xuất trường MDC | Kiểm tra mapping của encoder và schema lưu trữ |
| ID khác nhau giữa service A và B | Header/message property chưa được truyền | Kiểm tra transport contract ở mỗi hop |
| Thấy `correlationId` nhưng không có stack trace | Log lỗi chỉ ghi message | Ghi exception theo API logging đúng |
| Tìm thấy ID trong message nhưng không filter chính xác | ID không là field riêng | Chuẩn hóa structured logging |

### Checklist kiểm thử

1. Với ID `corr-42`, phát hai sự kiện và xác nhận cả hai có đúng `correlationId=corr-42`.
2. Sau khi scope kết thúc, kiểm tra MDC **không còn** ID của request trước.
3. Chạy hai tác vụ liên tiếp trên **cùng một worker thread** và xác nhận không lẫn ID.
4. Kích hoạt một exception và xác nhận log có ID, mã sự kiện và thông tin exception.
5. Kiểm tra bản ghi **đã xuất ra**, không chỉ gọi `MDC.get` trong unit test.
6. Nếu dùng JSON logging, kiểm tra `correlationId` là field có thể tìm theo giá trị chính xác.
7. Kiểm tra trường hợp ID đầu vào thiếu, sai định dạng hoặc vượt độ dài giới hạn.
8. Nếu dùng tracing, xác nhận `traceId` và `spanId` vẫn có ngữ nghĩa riêng.

## 9. Bảo mật và chi phí vận hành

- **Không dùng dữ liệu bí mật làm Correlation ID**: token đăng nhập, API key, mật khẩu, session cookie hoặc email/định danh cá nhân không cần thiết.
- Nếu ID đến từ người dùng, giới hạn kích thước và ký tự để giảm nguy cơ **log injection**, tăng dung lượng log hoặc phá cú pháp bản ghi.
- Không log toàn bộ request header/body chỉ để ghi một ID. Chọn đúng trường theo mục đích chẩn đoán.
- Không dùng Correlation ID như bằng chứng xác thực hay quyền truy cập; người dùng có thể biết hoặc tự cung cấp ID.
- Đánh giá cardinality và thời gian lưu dữ liệu khi đưa ID vào label của hệ metrics. Trường có cardinality rất cao thường phù hợp với log/tracing hơn là metric label.

## 10. Tổng kết và bài tập thực hành

Để **ghi Correlation ID đúng**, phải đồng bộ ba yếu tố: ID đã kiểm tra, logging context có scope rõ ràng, và logging backend thực sự xuất ra field đó. Khi có async, message hoặc nhiều service, việc truyền context là trách nhiệm riêng; `MDC.put` không tự bảo đảm tính xuyên suốt.

**Bài tập:** xây dựng một request handler phát `request.received`, `work.completed` và `request.failed` khi có lỗi. Kiểm tra các log đều dùng cùng một ID; chạy hai request liên tiếp trên một worker pool; tạo một công việc async; thử tình huống không có ID ở đầu vào; xác nhận không có rò rỉ context sau khi mỗi công việc hoàn tất.

### Tài liệu chính thức

- [SLF4J — MDC API và `putCloseable`](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Logback — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [Logback — PatternLayout](https://logback.qos.ch/manual/layouts.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)

