# Log search trong Java Core Logging và Observability

## 1. Log search là gì và giải quyết vấn đề nào?

**Log search** là khả năng tìm, lọc, sắp xếp, liên kết và phân tích các bản ghi log theo điều kiện như thời gian, service, mức độ lỗi, tên sự kiện, request ID, trace ID hoặc nội dung message. Trong hệ thống Java, log search biến các dòng được tạo bởi `java.util.logging` (JUL), SLF4J/Logback, Log4j2 hoặc các thư viện khác thành dữ liệu có thể sử dụng để điều tra sự cố, giải thích hành vi ứng dụng và đánh giá ảnh hưởng tới người dùng.

Ví dụ, khi dashboard báo tỷ lệ HTTP 5xx của `checkout-api` tăng, các câu hỏi cần trả lời là:

1. Trong 5 phút bất thường, service nào ghi ERROR và lỗi tập trung ở endpoint nào?
2. Có phải mọi request đều thất bại, hay một số attempt gặp lỗi nhưng retry thành công?
3. Một request cụ thể đã đi qua những service nào, theo thứ tự nào?
4. Message gốc, exception type và error code cho thấy nguyên nhân gì?
5. Log đang thiếu do hệ thống không ghi, do query sai, hay do pipeline ingest trễ?
6. Các sự kiện tìm được có đủ tin cậy, không trùng và không chứa dữ liệu nhạy cảm hay không?

**Search không chỉ là Ctrl+F trong một file.** Với môi trường nhiều instance và container, log thường được thu thập, parse, bổ sung metadata, lưu tập trung rồi lập chỉ mục hoặc sắp xếp để truy vấn. Cần hiểu cách tạo dữ liệu ở Java và cách backend tổ chức dữ liệu thì kết quả tìm kiếm mới chính xác.

Mục tiêu học tập: phân biệt tìm kiếm text và field; thiết kế structured log phù hợp; lập query theo thời gian và correlation; hiểu event time/ingest time, indexing, sampling và retention; tối ưu chi phí truy vấn; bảo vệ dữ liệu; và tự chạy ví dụ Java 17 minh họa truy vấn có cấu trúc.

## 2. Log search nằm ở đâu trong đường đi observability?

```text
Java application
  -> logger API / logging backend
  -> console, file, appender hoặc OTLP log exporter
  -> container runtime / agent / OpenTelemetry Collector
  -> parse, validate, enrich, redact, route
  -> log backend: storage + indexing/search engine
  -> query, visualization, alert, incident investigation
```

Một số backend index mọi field, một số chỉ index field được chọn hoặc dùng cơ chế tìm kiếm riêng. Không giả định cách lưu và khả năng query của Elasticsearch/OpenSearch, Loki, Cloud Logging, CloudWatch Logs hay một dịch vụ SaaS là giống nhau. Cú pháp và giới hạn thực tế cần kiểm theo phiên bản và kiến trúc đang dùng.

Mỗi tầng có thể làm thay đổi khả năng tìm kiếm:

| Tầng | Trách nhiệm | Nếu cấu hình sai |
| --- | --- | --- |
| **Java logger** | Tạo đúng event, severity, timestamp, context | Thiếu log do level/filter; message không có trường cần tìm |
| **Encoder** | Biến event thành JSON/text, escape dữ liệu | Stack trace bị cắt thành nhiều dòng; JSON parse lỗi |
| **Agent/Collector** | Đọc log, bổ sung pod/service/tenant metadata, route | Event vào nhầm environment/project; mất hoặc nhân đôi |
| **Backend ingest** | Chấp nhận, phân tích và lưu event | Lỗi quota, permission, mapping, ingest lag |
| **Index/search** | Cho phép lọc, tìm text, tổng hợp theo field/time | Query chậm, kết quả thiếu do index/retention |
| **UI/alert** | Hiển thị kết quả và điều kiện phát hiện | Sai time zone, sai query, alert nhiễu |

Cần phân biệt ba trạng thái: **đã được ứng dụng phát**, **đã được backend nhận**, và **đã có thể truy vấn**. Log xuất hiện trong `kubectl logs` hoặc console chưa chứng minh log đã được ingest và index. Ngược lại, không thấy kết quả search chưa chứng minh không có sự kiện; có thể query sai phạm vi hoặc dữ liệu đến trễ.

## 3. Từ log text đến structured log

### Log text thuần

Một thông điệp như:

```text
2026-01-01T10:00:02Z ERROR Payment failed for order 42
```

có thể tìm theo từ `Payment` hoặc `ERROR`, nhưng khó phân biệt service, request, exception, tenant, order ID và kết quả cuối cùng nếu những trường đó không được ghi nhất quán.

Text search hữu ích khi cần tìm câu lỗi chưa biết schema, nhưng có thể trả về **false positive** vì message là dữ liệu tự do. Ví dụ tìm `timeout` có thể khớp một lời giải thích “request completed without timeout”. Phân tích số lần lỗi dựa vào text có thể lệch khi message thay đổi qua bản phát hành.

### Structured log

Một JSON Lines event dễ lọc theo field:

```json
{
  "timestamp": "2026-01-01T10:00:02Z",
  "severity": "ERROR",
  "service.name": "checkout-api",
  "service.version": "1.2.0",
  "deployment.environment.name": "prod",
  "event.name": "payment.failed",
  "operation": "payment.authorize",
  "http.route": "/api/payments",
  "request_id": "req-100",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "exception.type": "java.net.SocketTimeoutException",
  "message": "Payment provider did not respond"
}
```

Đây là **schema minh họa của ứng dụng**, không phải lời khẳng định mọi log backend tự hiểu các tên field đó. Một số backend sẽ lưu chúng trong JSON payload, số khác có mapping riêng. Với OpenTelemetry, resource attributes, log record attributes và semantic conventions cần được xuất/ánh xạ theo SDK và phiên bản tương ứng.

Những field thường có ích:

| Field | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| `timestamp` | Tìm theo thời gian xảy ra event | UTC hoặc offset; đồng bộ clock |
| `ingested_at` nếu có | Tìm khi backend nhận dữ liệu | Không nhầm với event time |
| `severity` | Lọc ERROR/WARN/INFO | Mapping level khác nhau theo framework/backend |
| `service.name`, `service.version` | Phân biệt service và deployment | Lấy từ cấu hình tin cậy |
| `deployment.environment.name` | Phân biệt prod/staging/test | Không chỉ dựa vào chuỗi client tự gửi |
| `event.name` | Tìm loại sự kiện ổn định | Nên chuẩn hóa tên qua nhiều service |
| `operation`, `http.route` | Lọc theo nghiệp vụ/endpoint | Dùng route template, không raw path chứa ID |
| `request_id`, `trace_id` | Truy request liên service | Không biến thành metric labels |
| `error.code`, `exception.type` | Phân nhóm lỗi | Dùng mã ổn định, không lấy message làm code |
| `message`, exception detail | Đọc ngữ cảnh sự cố | Sanitization, kiểm kích thước, quyền truy cập |

**Một event nên nằm trên một JSON line hợp lệ.** Newline trong message hoặc stack trace phải được encode thành ký tự escape bên trong JSON string, hoặc pipeline phải có multiline handling phù hợp. Nếu một stack trace bị chia thành 30 event, text search có thể tìm ra dòng giữa nhưng mất context của exception ban đầu.

## 4. Các kiểu tìm kiếm log thường dùng

| Kiểu tìm kiếm | Ví dụ ý định | Khi nào dùng |
| --- | --- | --- |
| **Field equality** | `service.name = checkout-api` | Lọc đúng một service hoặc event name |
| **Nhiều điều kiện AND** | service + severity + time window | Khoanh vùng sự cố với ít nhiễu |
| **OR/IN** | `severity ∈ {WARN, ERROR}` | Quan sát nhiều mức log liên quan |
| **Full-text** | Message chứa các từ liên quan timeout | Tìm dấu hiệu chưa có field riêng |
| **Phrase/exact match** | Message có cụm cụ thể | Hạn chế match ngoài ý muốn |
| **Range** | timestamp trong `[start, end)` | Điều tra một giai đoạn |
| **Prefix/regex/wildcard** | Event hoặc path pattern | Khi schema chưa chuẩn; chú ý cost và độ chính xác |
| **Aggregation/group-by** | Đếm lỗi theo service/route/error code | Xác định tập trung bất thường |
| **Sort/top-N** | Sự kiện gần nhất hoặc lỗi phổ biến | Triage nhanh |
| **Correlation timeline** | Tìm mọi event của `request_id=req-100` | Dựng luồng request qua service |
| **Comparison** | Trước và sau deployment | Kiểm regression theo version |

Không phải backend nào cũng hỗ trợ mọi toán tử hoặc cùng cách thực thi. Một số search index được token hóa nên `"payment.failed"` có thể không khớp như exact field; cần dùng truy vấn **exact/keyword field** khi muốn so sánh bằng chuỗi. Với regexp và wildcard rộng, có thể tăng chi phí rất nhiều; trước tiên nên khoanh vùng thời gian, service và field được index.

### Field query khác text query

Giả sử log có:

```json
{"severity":"INFO","message":"Recovery succeeded after prior timeout"}
```

Query text chứa `timeout` sẽ trả event này, nhưng query `severity=ERROR` thì không. Ngược lại, một ERROR có `error.code=DB_UNAVAILABLE` mà message chỉ là `"Dependency failed"` sẽ không khớp từ khóa `timeout`. Dùng **field có nghĩa ổn định** để phân loại; text search bổ sung cho điều tra chi tiết.

### Cú pháp minh họa độc lập nhà cung cấp

```text
WHERE service.name = "checkout-api"
  AND severity IN ("ERROR", "WARN")
  AND timestamp >= 2026-01-01T10:00:00Z
  AND timestamp <  2026-01-01T10:05:00Z
ORDER BY timestamp ASC
```

Đây là **pseudo-query để giải thích ý định**, không phải lệnh có thể dán nguyên vào mọi cloud console. Với SQL-like backend, các key chứa dấu chấm có thể cần quote; với hệ thống query theo labels hoặc text pipeline, cú pháp khác. Luôn kiểm cách backend xử lý case sensitivity, phân tích text, giá trị rỗng và missing field.

## 5. Chọn khoảng thời gian search cho đúng

Một truy vấn log phải xác định:

- **Event time:** thời điểm ứng dụng phát hoặc ghi sự kiện, thường do `Instant.now()`/logger timestamp tạo.
- **Ingest time:** thời điểm backend nhận log; có thể muộn hơn khi queue batch, retry hoặc network chậm.
- **Query time:** thời điểm người dùng tìm kiếm; giao diện có thể mặc định hiển thị timezone cục bộ.
- **Thời gian hoàn thành request:** có thể khác thời điểm một exception attempt trong request được log.

Ví dụ event xảy ra lúc `10:04:59Z` nhưng do backend throttling chỉ có thể query lúc `10:06:30Z`. Nếu UI đang lọc theo ingest time, nó xuất hiện trong cửa sổ sau; nếu lọc theo event time, nó thuộc khoảng trước. Cần biết hệ thống đang dùng timestamp nào.

Nên dùng khoảng **nửa mở** `[start, end)` cho truy vấn chương trình và báo cáo theo cửa sổ:

```text
start inclusive: 2026-01-01T10:00:00Z
end exclusive:   2026-01-01T10:05:00Z
```

Ưu điểm: hai cửa sổ liên tiếp không đếm trùng một event nằm đúng tại mốc `10:05:00Z`. Khi điều tra bằng UI, có thể nới khoảng trước/sau thời điểm báo lỗi để tránh bỏ sót log đến trễ, clock skew hoặc bước trước request. Không đổi timezone của timestamp một cách tùy tiện.

Nếu query trả về quá nhiều dữ liệu, thu hẹp từ 24 giờ xuống 15 phút hoặc 5 phút sau khi xác định mốc sự cố; nếu không có kết quả, thử mở rộng có kiểm soát **sau khi kiểm time field và pipeline ingest**, không kết luận event không tồn tại.

### Thứ tự sự kiện không chỉ dựa trên timestamp

Nhiều log có thể cùng timestamp hoặc đến sai thứ tự từ các thread/container. Nếu cần timeline ổn định, sắp xếp theo timestamp cùng một khóa phụ như event ID/sequence khi có. **Không suy ra thứ tự thực thi toàn cục từ các đồng hồ máy khác nhau**, đặc biệt khi clock skew hoặc asynchronous operations tồn tại. Trong tracing, parent/child span và sequence theo nghiệp vụ có thể giúp tái dựng causal order tốt hơn.

## 6. Ví dụ Java 17 chạy độc lập: tìm log theo field, thời gian và request ID

Ví dụ này dùng **chỉ JDK 17**, không cần database hay thư viện logging bên ngoài. Nó minh họa logic truy vấn trên **các sự kiện đã được parse thành record Java**, không thực hiện full-text index hoặc đọc JSON. Trong hệ thống thật, log được gửi vào backend và query tương tự được thực hiện bởi search engine. Dữ liệu ví dụ cố định để có stdout chính xác.

Bài toán:

1. Lấy tất cả `ERROR` của `checkout-api` trong `[10:00, 10:05)`.
2. Lấy timeline của `req-100` qua **nhiều service**, sắp xếp theo thời gian tăng.
3. Log `req-102` nằm ngoài cửa sổ ở phút 10:06 nên không thuộc kết quả truy vấn 1, nhưng không bị xóa khỏi tập dữ liệu gốc.

Tạo tệp **`LogSearchDemo.java`**:

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.function.Predicate;

public final class LogSearchDemo {
    record LogEvent(
            String eventId,
            Instant occurredAt,
            String severity,
            String service,
            String eventName,
            String requestId,
            String message) {}

    private static List<LogEvent> data() {
        return List.of(
                new LogEvent(
                        "e-001", Instant.parse("2026-01-01T10:00:00Z"),
                        "INFO", "checkout-api", "checkout.started",
                        "req-100", "Checkout started"),
                new LogEvent(
                        "e-002", Instant.parse("2026-01-01T10:00:01Z"),
                        "WARN", "inventory-api", "inventory.slow",
                        "req-100", "Inventory took longer than expected"),
                new LogEvent(
                        "e-003", Instant.parse("2026-01-01T10:00:02Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-100", "Payment provider timed out"),
                new LogEvent(
                        "e-004", Instant.parse("2026-01-01T10:01:00Z"),
                        "INFO", "checkout-api", "checkout.started",
                        "req-101", "Checkout started"),
                new LogEvent(
                        "e-005", Instant.parse("2026-01-01T10:01:02Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-101", "Payment provider timed out"),
                new LogEvent(
                        "e-006", Instant.parse("2026-01-01T10:06:00Z"),
                        "ERROR", "checkout-api", "payment.failed",
                        "req-102", "Payment provider timed out"));
    }

    private static List<LogEvent> search(
            List<LogEvent> events, Predicate<LogEvent> condition) {
        return events.stream()
                .filter(condition)
                .sorted(Comparator.comparing(LogEvent::occurredAt)
                        .thenComparing(LogEvent::eventId))
                .toList();
    }

    private static void printEvents(List<LogEvent> events) {
        for (LogEvent event : events) {
            System.out.println(
                    event.occurredAt() + " " + event.severity()
                    + " " + event.service() + " " + event.eventName()
                    + " req=" + event.requestId());
        }
    }

    public static void main(String[] args) {
        List<LogEvent> events = data();

        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        Instant end = Instant.parse("2026-01-01T10:05:00Z");

        List<LogEvent> errors = search(events, event ->
                "checkout-api".equals(event.service())
                && "ERROR".equals(event.severity())
                && !event.occurredAt().isBefore(start)
                && event.occurredAt().isBefore(end));

        System.out.println("QUERY 1: checkout-api ERROR [10:00,10:05)");
        printEvents(errors);

        List<LogEvent> timeline = search(events,
                event -> "req-100".equals(event.requestId()));

        System.out.println("QUERY 2: request_id=req-100");
        printEvents(timeline);
    }
}
```

Biên dịch và chạy:

```bash
javac LogSearchDemo.java
java LogSearchDemo
```

**Stdout chính xác:**

```text
QUERY 1: checkout-api ERROR [10:00,10:05)
2026-01-01T10:00:02Z ERROR checkout-api payment.failed req=req-100
2026-01-01T10:01:02Z ERROR checkout-api payment.failed req=req-101
QUERY 2: request_id=req-100
2026-01-01T10:00:00Z INFO checkout-api checkout.started req=req-100
2026-01-01T10:00:01Z WARN inventory-api inventory.slow req=req-100
2026-01-01T10:00:02Z ERROR checkout-api payment.failed req=req-100
```

Giải thích:

- `Predicate<LogEvent>` mô tả các điều kiện AND; mỗi điều kiện chỉ dùng field đã chuẩn hóa thay vì parse chuỗi message tự do.
- `Instant` và `!isBefore(start) && isBefore(end)` triển khai khoảng nửa mở; các event xảy ra đúng ở `end` sẽ không được tính.
- Query 1 có **hai** ERROR cùng service trong cửa sổ; `e-006` bị loại vì lúc 10:06, `e-002` bị loại vì service inventory và mức WARN.
- Query 2 không lọc service nên cho thấy một request đi qua cả `checkout-api` và `inventory-api`. Đây là bước đầu của correlation search, dù demo chưa có distributed tracing thực.
- `sorted` dùng thời gian rồi event ID để ổn định thứ tự nếu trùng timestamp; `Stream.toList()` có trong Java 16+, phù hợp Java 17.
- Trường `message` được giữ trong record nhưng cố ý **không in** trong kết quả mặc định, vì truy vấn đầu tiên nên hiển thị field có cấu trúc/ít nhạy cảm. Ở sản phẩm thật, mở message/stack trace khi có quyền và nhu cầu điều tra.
- Ví dụ không đo throughput hay chứng minh tính toàn vẹn của backend. Toàn bộ dữ liệu nằm trong RAM, không có index, ingest lag, sampling, retry, ACL hoặc bảo đảm retention. **Không dùng search in-memory trên toàn bộ log production**; chuyển logic này sang backend tìm kiếm có khả năng scale.

## 7. Lấy đủ field từ Java logger để phục vụ search

### JUL: java.util.logging

JUL có logger, `Handler`, `Formatter` và `Filter`. Mặc định, output thường là text, không tự có schema JSON giống bảng ở trên. Ví dụ minh họa:

```java
Logger logger = Logger.getLogger("checkout-api");
logger.log(Level.WARNING, "Payment provider timeout");
```

Đoạn này **không chạy độc lập** nếu chưa import và cấu hình, và không tự thêm `request_id`/`trace_id`. Muốn log search theo các field, ứng dụng phải dùng formatter/handler phù hợp hoặc có pipeline parser/enrichment.

### SLF4J với Logback/Log4j2

SLF4J là facade, provider/backend quyết định appender và encoder. Cách thông dụng là log message tham số hóa:

```java
logger.error("payment failed orderId={} errorCode={}",
        orderId, "DOWNSTREAM_TIMEOUT", exception);
```

Đây là **đoạn minh họa**, cần SLF4J logger, `orderId` và `exception` có sẵn. Nó không tự bảo đảm mọi placeholder trở thành field JSON. Nếu backend chỉ có text encoder, những giá trị đó nằm trong message; muốn query theo `error.code` riêng, cần structured arguments, key-value API hoặc encoder/instrumentation tương thích.

Với Spring Boot, cấu hình logging và dependency/provider thay đổi theo phiên bản. `logging.level.*` có thể quyết định mức log cho package; JSON encoder hoặc structured logging support cần được bật/thiết lập đúng stack. Không mặc định mọi version tự phát JSON đầy đủ trên stdout.

### Phân biệt trường “đang có” và trường “được gửi”

Một context trong MDC/ThreadContext chỉ giúp log search nếu appender/encoder được cấu hình **đưa MDC vào output**. Ví dụ gọi `MDC.put("request_id", id)` nhưng encoder chỉ in `%msg` thì log backend vẫn không thấy request ID. Ngược lại, encoder JSON ghi mọi MDC field mà không giới hạn có thể vô tình xuất token hoặc dữ liệu cá nhân.

Kiểm tra cả bốn chặng:

1. Request context có trường đúng.
2. Logger/backend giữ trường và encode đúng format.
3. Agent/Collector không loại hoặc đổi tên trường ngoài hợp đồng.
4. Backend parse/index thành field có thể query, không chỉ một JSON string nằm trong `message`.

## 8. Correlation search: request ID, trace ID và span ID

Khi hệ thống có nhiều microservice, lỗi thường xuất hiện ở service khác với nơi trả response cho client. Một quy trình điều tra thường đi như sau:

```text
HTTP 503 ở gateway (request_id=req-100)
    |
    +-- search request_id=req-100 trong cùng environment/time
           |
           +-- checkout-api: request started
           +-- inventory-api: warning slow dependency
           +-- payment-api: timeout / retry
           +-- checkout-api: request completed with 503
```

**Request ID** giúp lọc log cùng request, nhưng propagation phải có quy tắc tin cậy. Nếu client tự gửi request ID, gateway có thể cần kiểm tra cấu trúc và giới hạn độ dài, hoặc cấp ID mới. Không để client tự chọn các field nhạy cảm như tenant/service identity rồi coi chúng là bằng chứng.

**Trace ID** nối nhiều span của một trace phân tán; span ID chỉ định span cụ thể. Một request có thể tạo nhiều spans, nhiều log, nhiều retries. Log chứa `trace_id` vẫn hữu ích dù trace sampling khiến trace tương ứng không được lưu; không kết luận “không có trace = không có lỗi”.

Trong Java dùng SLF4J/Logback, MDC thường gắn với thread. Với `ExecutorService`, `CompletableFuture` hoặc reactive chain, MDC không tự động lan truyền qua mọi asynchronous task. Phải dùng context propagation phù hợp và khôi phục/xóa context sau request để tránh log request mới bị gắn nhầm ID cũ.

Khi search theo trace ID:

- Chọn cùng environment và khoảng thời gian phù hợp.
- Đảm bảo không nhầm `trace_id` của span với request ID của HTTP gateway.
- Nhóm theo service/span/operation để dựng timeline.
- Xem retry và parallel branches; đừng mặc định mọi log cùng trace có thứ tự nhân quả chỉ theo timestamp.
- Kiểm trace/span IDs có định dạng hợp lệ trước khi đưa vào query; không nối query từ input không kiểm tra nếu hệ thống có cú pháp đặc biệt.

## 9. Từ metric anomaly tới log search

Metric phát hiện tình hình, log giải thích nguyên nhân. Giả sử dashboard có spike `http.server.request.duration` hoặc số 5xx của `checkout-api`.

Quy trình:

1. Từ metric, lấy **service, environment, route, status/error code và khoảng thời gian**. Xác nhận đây là metric request hay attempt.
2. Tìm log có cấu trúc với cùng scope. Bắt đầu bằng completion events hoặc ERROR events, tùy câu hỏi.
3. Group theo `error.code`/`event.name`/`service.version` để thấy nhóm lỗi tập trung hoặc khác biệt giữa deployment.
4. Chọn vài request ID điển hình, xem toàn bộ timeline xuyên service, kể cả WARN và INFO.
5. Nếu có trace, mở trace/span liên quan để kiểm duration, retries và dependencies; nếu không có trace vì sampling, log vẫn có thể đủ để điều tra.
6. Kiểm có nhiều log của một request hoặc cùng event bị ingest trùng. Không dùng số dòng ERROR để thay trực tiếp failed request counter.
7. Đối chiếu exception message đã sanitize, thời gian và behavior thực tế; phân biệt lỗi đã recovered với lỗi cuối.
8. Nếu query không có kết quả, kiểm time window, service scope, retention, ingest errors, sampling và index lag trước khi kết luận metric sai.

Một metric tổng hợp có thể gồm hàng triệu request; **không gắn request ID vào mỗi metric label** vì cardinality có thể tăng không giới hạn. Với hệ thống hỗ trợ exemplar, một mẫu đo metric có thể gắn trace ID để điều tra; còn lookup chi tiết nên thực hiện trong log/trace.

## 10. Một số nhóm truy vấn vận hành hữu ích

### A. Lỗi theo service và thời gian

```text
filter:
  environment = prod
  service = checkout-api
  severity = ERROR
  timestamp in [start, end)
sort:
  timestamp ascending
```

Dùng khi muốn khoanh vùng các lỗi mới xuất hiện. Nếu kết quả quá nhiều, thêm `event.name`, `error.code` hoặc `http.route`.

### B. Lỗi theo endpoint/route

```text
filter:
  http.route = /api/orders/{orderId}
  http.status_code >= 500
  timestamp in [start, end)
group by:
  error.code, service.version
```

Tìm endpoint có cùng loại lỗi qua những version khác nhau. Route phải là **template đã match**, không phải `/api/orders/987123` chứa ID động.

### C. Timeline của request

```text
filter:
  request_id = req-100
  timestamp in [start - context, end + context]
sort:
  timestamp, event_id
```

Không lọc severity ở bước đầu; INFO/WARN thường cho biết request bắt đầu, retry, fallback hoặc được route sang service nào.

### D. So sánh trước/sau deployment

```text
filter:
  service = checkout-api
  timestamp in comparable windows
group by:
  service.version, event.name, error.code
```

Cần chuẩn hóa cửa sổ theo traffic, environment và route. Số ERROR logs tăng sau deployment có thể do logging level đổi chứ không phải tỷ lệ lỗi tăng; đối chiếu với request/error metrics.

### E. Tìm kiếm exception

```text
filter:
  exception.type = java.net.SocketTimeoutException
  error.code = DOWNSTREAM_TIMEOUT
  timestamp in [start, end)
```

Dùng field type/error code thay vì chỉ tìm cụm “timeout” trong message. Nếu system chưa có structured exception type, text search là bước khám phá, nhưng nên coi nó là kết quả có khả năng nhiễu.

### F. Audit và security events

```text
filter:
  event.name = authz.access.denied
  environment = prod
  timestamp in [start, end)
group by:
  service, target_type, reason_code
```

Chỉ dùng field đã được server xác minh, giới hạn quyền đọc theo chính sách. Audit logs có thể cần retention/durability riêng và không được sampling tùy tiện.

Các khối trên là **pseudo-query**, không phải cú pháp YAML config hay lệnh truy vấn hoàn chỉnh. Với backend cụ thể, chuyển chúng sang cú pháp query được hỗ trợ và kiểm khả năng index, permission, time range.

## 11. Search backend và index: điều gì ảnh hưởng hiệu năng?

Search log có thể cần scan lượng dữ liệu rất lớn. Chi phí và latency thường phụ thuộc:

- **Khoảng thời gian:** càng hẹp càng giảm số segment/chunk cần xét; phần lớn log stores phân vùng theo thời gian.
- **Phạm vi service/tenant/environment:** điều kiện chọn lọc từ đầu giúp giảm tập dữ liệu.
- **Indexed fields/labels:** truy vấn chính xác trên field được index/label thường khác về chi phí so với scan toàn message. Mỗi backend có trade-off index và storage riêng.
- **Text tokenization:** tìm token, phrase và exact keyword có thể cho kết quả khác nhau; case, dấu câu và analyzer rất quan trọng.
- **Regex và wildcard:** pattern trên quá nhiều event có thể đắt; đừng mặc định một regexp giống nhau được thực thi hiệu quả ở mọi backend.
- **Aggregation:** group theo giá trị cardinality cao có thể dùng nhiều bộ nhớ và tạo hàng nghìn buckets.
- **Sort, pagination và top-N:** lấy toàn bộ dữ liệu rồi sắp xếp theo thời gian tốn tài nguyên; query hạn chế page/result và xác định sort key để phân trang ổn định.
- **Retention và storage tier:** dữ liệu ở cold/archive có thể cần restore hoặc có thời gian truy vấn khác; log đã hết retention không thể tìm lại chỉ bằng mở rộng time window.

### Tránh cardinality cao ở nơi không phù hợp

Một log có thể chứa `request_id`, `trace_id` hay order ID để điều tra, nhưng không có nghĩa các giá trị đó nên là **index partition, label metric hoặc label stream**. Trong hệ thống dùng labels để chọn stream, gắn mỗi request ID thành label có thể tạo lượng stream rất lớn. Với metrics, request ID/trace ID tuyệt đối không phù hợp làm nhãn thông thường.

Ngược lại, bỏ mọi khả năng tìm theo request ID cũng có thể làm điều tra rất khó. Giải pháp là **chọn cấu trúc lưu trữ theo công nghệ**: có hệ thống hỗ trợ tìm request ID bằng indexed field, có hệ thống dùng scan filter trong những stream đã thu hẹp bằng service/environment/route. Đừng sao chép nguyên chính sách labels giữa Loki, Elasticsearch và Prometheus.

### Sampling làm giảm dữ liệu có thể search

Nếu ứng dụng/collector sampling DEBUG/INFO, một request có thể không có toàn bộ timeline. Điều này phải được nêu trong policy; không kết luận một event không xảy ra chỉ vì không tìm thấy log. Với ERROR hoặc audit bắt buộc, cần chính sách giữ theo mức độ quan trọng và khả năng tải.

## 12. Log đến trễ, mất log và trùng log

### Ingestion delay

Log được phát lúc 10:00 nhưng index tới 10:03 vì queue/retry. Nếu search UI có “Last 1 minute”, event có thể nằm ngoài cửa sổ tùy backend dùng event time hay ingest time. Xem pipeline latency, mở rộng range theo time field và dùng event ID để đối chiếu.

### Dữ liệu bị mất

Nguyên nhân có thể là:

- Logger level/filter loại trước khi tạo event.
- Async appender queue đầy và drop theo chính sách.
- Container runtime rotation hoặc agent không đọc kịp.
- Collector parse lỗi, thiếu exporter, quota/mạng/auth lỗi.
- Backend từ chối ingest, quá hạn retention hoặc sai project/tenant.

Đừng tạo một event "thử" trong log rồi lấy việc không search ra để tự suy ra root cause duy nhất. Cần xem metrics độc lập của source/agent/backend, kèm thử nghiệm end-to-end.

### Trùng event

Một exporter gửi event rồi mất ACK, retry có thể làm backend nhận hai bản sao. Cùng exception cũng có thể bị log ở DAO, service và controller. Hai loại trùng này khác nhau:

- **Duplicate transport:** cùng `event_id` logic được gửi lại; có thể dedup theo hợp đồng lưu trữ.
- **Duplicate semantic logging:** nhiều event độc lập được tạo từ một lỗi căn bản; cần chuẩn hóa điểm log, event name và owner.

Không dùng stack trace bằng nhau làm bằng chứng hai log là một event duy nhất. Nhiều request độc lập có thể lỗi tại cùng stack frame.

## 13. Bảo mật và quyền truy vấn log

Log thường chứa dữ liệu nhiều service/tenant, đôi khi có PII hoặc thông tin nội bộ. Một hệ thống search mạnh phải đi cùng kiểm soát truy cập.

- **Không ghi secrets tại nguồn:** access token, session cookie, password, private key, connection string có credential, số thẻ nhạy cảm hoặc payload khách hàng không cần thiết. Redaction tại Collector chỉ là lớp bổ sung vì dữ liệu đã có thể rời JVM.
- **Quyền đọc khác quyền ghi:** service có quyền ingest không đồng nghĩa được phép truy vấn toàn bộ logs; người dùng chỉ đọc theo vai trò/tenant/environment.
- **Retention và data residency:** giới hạn thời gian lưu và vùng dữ liệu theo chính sách thực tế. Không có một giá trị retention mặc định thích hợp cho mọi tổ chức.
- **Audit hoạt động truy vấn:** với dữ liệu nhạy cảm, cần theo dõi ai đã search, export hoặc thay đổi quyền/retention; hạn chế bulk export trái phép.
- **Query injection:** nếu ứng dụng tự nhận search parameters từ người dùng rồi nối chuỗi query, cần validation/escaping hoặc parameterized API tương ứng. Field/value allowlist và giới hạn time range, page size, query cost.
- **Log injection:** ký tự newline/control trong user input phải được JSON encoder escape; không để client giả mạo severity, service, actor hoặc audit outcome.
- **Context đáng tin:** request ID có thể do ingress xác thực/cấp mới; không lấy header chưa tin cậy làm danh tính hoặc tenant scope để phân quyền search.

Ví dụ một URI path hoặc query string chứa email/token không nên được ghi nguyên dưới tên `url.full` chỉ để tìm lỗi thuận tiện. Structured event với `http.route`, status, error code và correlation ID thường đủ cho mục tiêu vận hành; raw evidence nếu cần phải đi qua kênh hạn chế quyền.

### Phân biệt tìm kiếm dữ liệu với quyền suy luận

Ngay cả khi một dashboard chỉ hiển thị số lượng theo tenant, nhóm kết quả ít có thể làm lộ thông tin nhạy cảm gián tiếp. Cần cân nhắc giới hạn query, nhóm tổng hợp, masking và kiểm tra quyền trước khi trả kết quả cho người xem.

## 14. Tình huống chẩn đoán: "Không tìm thấy log của request lỗi"

Một chuỗi kiểm tra có hệ thống:

1. **Xác nhận event tồn tại theo contract:** request đã qua service nào, có log ở level nào, event name nào, được sampling hay không?
2. **Xác nhận ID:** request ID, trace ID, tenant ID, service name đã được tạo/truyền đúng chưa? Có đổi ID ở gateway hoặc asynchronous worker không?
3. **Xác nhận thời gian:** so UTC vs local, event time vs ingest time, đồng hồ máy và khoảng filter; mở range có kiểm soát.
4. **Xác nhận output:** console/file/OTLP có event hợp lệ không? Encoder có đưa trường tìm kiếm vào payload không?
5. **Xác nhận pipeline:** agent/Collector đã đọc, parse, route đúng backend/project/region/tenant chưa? Có exporter error/drop/queue backlog?
6. **Xác nhận schema:** tìm theo `event.name`/`request_id` exact field có match không? Field có đổi tên, bị nested hay bị lưu thành string text?
7. **Xác nhận policy:** retention đã hết, index/archive chưa sẵn, người query thiếu quyền hoặc có query quota không?
8. **Đối chiếu nguồn độc lập:** metric request/error, tracing spans nếu có, canary event, audit/transaction event để xác định blind spot.
9. **Ghi bằng chứng:** query, time range, số kết quả, các field thực tế, ingest lag và bước bị lỗi để khắc phục có thể tái hiện.

**Không có kết quả không nhất thiết bằng không có lỗi.** Query quá hẹp, sai route, dữ liệu đến muộn, level tắt hoặc quyền truy vấn đều có thể dẫn tới danh sách rỗng.

## 15. Kiểm thử cho khả năng log search

Một bộ test nên kiểm cả **nội dung tạo ra** và **khả năng tìm được tại backend**:

| Test | Kỳ vọng |
| --- | --- |
| INFO/ERROR có schema | Mọi field cần thiết có kiểu và tên đúng |
| Message chứa dấu nháy/newline | JSON Lines vẫn parse được, không bị tách sai event |
| Query ERROR theo service/time | Chỉ trả event đúng severity/service/window |
| Query request ID qua nhiều service | Timeline đủ theo policy, không trộn request khác |
| Same timestamp nhiều event | Sort ổn định theo khóa phụ nếu có |
| Request chứa token/PII | Không lộ vào message/query/raw path log mặc định |
| Exception với stack trace | Có exception type/error code và trace được bảo vệ |
| Async/Executor/reactive | Correlation ID không mất hoặc rò giữa thread |
| 404/401 trước controller | Event được phát nếu access/security policy yêu cầu |
| Retry exporter/ACK loss | Không đếm bản sao là lỗi nghiệp vụ mới |
| Queue overflow/Collector lỗi | Counters và cảnh báo phản ánh dropped events |
| Ingest trễ | Query theo event time và ingest time không đánh đồng |
| Deployment thay version | Search theo service.version cho thấy sự khác biệt |
| Phân quyền tenant | Người không có quyền không search được log ngoài scope |
| Retention/archive | Dữ liệu ở đúng tier/thời hạn và hành vi search đúng |
| Query có wildcard/regex đắt | Có giới hạn thời gian, kết quả và resource budget |

Unit test Java có thể dùng record và predicate như ví dụ để kiểm logic filter/sort, nhưng không chứng minh backend parse/index đúng. Integration test cần chạy **logger/backend/collector/indexer thực**, phát event có ID duy nhất rồi poll bằng điều kiện và timeout hữu hạn. Không lấy `Thread.sleep(1000)` làm bảo đảm event đã search được.

Khi so số lượng log với metrics, cần phân biệt request count, exception attempts, retries và log event count. Một request có thể tạo nhiều logs; sampling hoặc duplicate sẽ làm số lượng chênh lệch theo policy.

## 16. Quy trình viết truy vấn hiệu quả

Hãy bắt đầu từ câu hỏi và chọn cách query tương ứng:

1. **Phát biểu câu hỏi:** “Những request 5xx từ checkout-api sau deployment 1.2.0 trong 10 phút vừa rồi là gì?”
2. **Chọn scope:** service, environment, route, version, instance nếu cần.
3. **Chọn time window:** dùng event time nhất quán, mở đủ biên cho ingest lag và clock skew.
4. **Chọn kiểu điều kiện:** equality cho field, range cho thời gian/số, text/regex chỉ khi thực sự thiếu schema.
5. **Giảm dữ liệu trả:** chỉ lấy timestamp, event name, severity, error code, request ID và message đã sanitize; giới hạn rows/page.
6. **Group trước khi đọc chi tiết:** xác định top error codes/routes hoặc phiên bản lỗi nhiều nhất, rồi mở một số request điển hình.
7. **Dựng timeline:** mở rộng điều kiện theo request/trace ID, bỏ filter severity để không bỏ sót INFO/WARN liên quan.
8. **Kiểm điều kiện loại trừ:** sampling, level, missing fields, 404/unmatched route, lỗi permission/index và thời gian đến trễ.
9. **Lưu query có tên:** dashboard hoặc saved search, kèm mô tả schema/timezone và owner để nhóm dùng lại.
10. **Xác nhận hậu quả:** so với request/error metrics và data source độc lập trước khi kết luận nguyên nhân.

Nên chuẩn hóa tên trường trong các service và giữ một bảng mapping nếu nhiều backend dùng schema khác nhau. Những câu search thường dùng nhất nên có ví dụ query đã kiểm thử với đúng backend và phiên bản trong tài liệu nội bộ của dự án.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Chỉ tìm `ERROR` trong message | Bỏ sót error có code khác hoặc match sai text | Query severity/event/error code có cấu trúc |
| Search toàn bộ retention với wildcard rộng | Chậm, tốn tài nguyên và tiền | Thu hẹp time/service trước, giới hạn rows |
| Dùng raw URL làm route/metric label | Cardinality tăng theo ID và có thể lộ dữ liệu | Dùng matched route template |
| Quên khác biệt event time/ingest time | Bỏ sót log đến trễ | Kiểm time field và ingestion lag |
| Mặc định request ID tự truyền qua thread | Log async thiếu hoặc sai correlation | Context propagation + cleanup |
| Đếm ERROR logs làm số failed requests | Retry/rethrow/duplicate gây lệch | Metric final outcome tại boundary |
| Coi trace ID tồn tại là trace luôn được lưu | Tracing có sampling | Dùng log độc lập, kiểm trace sampling |
| Dùng query text thay exact-field query | Analyzer/tokenization cho kết quả sai | Dùng keyword/exact field khi cần |
| Đọc log của mọi tenant với một quyền chung | Rủi ro lộ thông tin | RBAC/IAM và tenant isolation |
| Ghi nguyên token/secret vào query/path | Lộ dữ liệu, khó xóa hết bản sao | Không phát secret; redaction/retention |
| Nghĩ log không search ra tức là không phát | Có thể do mất index/permission/ingest | Probe end-to-end và self-metrics |
| Không phân biệt transport duplicate với semantic duplicate | Đếm trùng và chẩn đoán sai | Event ID và log owner/event name |
| Không test schema khi đổi backend | Saved search/dashboard hỏng âm thầm | Contract test và versioned schema |
| Lạm dụng regex trên field có cấu trúc | Query phức tạp, tốn tài nguyên | Index/field equality, bounded labels |
| Chỉ xem log mà không kiểm metrics/traces | Thiếu góc nhìn về ảnh hưởng và causality | Correlate cả ba tín hiệu observability |

## 18. Checklist áp dụng cho một Java service

- [ ] Mỗi log quan trọng có `timestamp`, severity, service/environment, event name và metadata cần thiết?
- [ ] Structured encoder có sinh JSON hợp lệ, escape newline/quotes và giữ exception details an toàn?
- [ ] Log backend có parse các field dùng để search, không chỉ lưu JSON như một chuỗi message?
- [ ] Có thể tìm ERROR/WARN theo time window, service, operation, error code và deployment version?
- [ ] Có thể dựng timeline qua nhiều service bằng request ID/trace ID?
- [ ] Route dùng template, tránh raw path/ID động trong metric labels hoặc stream labels cardinality cao?
- [ ] Có phân biệt event timestamp với ingest timestamp, biết ingestion lag và retention?
- [ ] Query có scope/time/page limits; không dùng wildcard rộng một cách mặc định?
- [ ] Những query nhạy cảm có kiểm soát quyền theo role/tenant/environment và audit access?
- [ ] Không ghi secret hoặc PII không cần thiết; trường raw path/query/message có redaction/allowlist phù hợp?
- [ ] Sampling, level filtering, retry, duplicate, dropped logs và collector errors được quan sát?
- [ ] Có integration test phát event canary và search lại tại backend với timeout, không chỉ test console?
- [ ] Saved queries và dashboards có người phụ trách, schema/version được kiểm khi nâng cấp?
- [ ] Có quy trình từ metric spike → structured log search → request timeline → trace và root cause?

**Ghi nhớ:** khả năng **Log search** tốt bắt đầu từ khi Java tạo sự kiện: ghi các field nhất quán, dùng correlation ID và bảo vệ dữ liệu nhạy cảm. Sau đó phải bảo đảm pipeline thực sự ingest/parse/index được chúng, truy vấn theo đúng time window và ngữ nghĩa backend. **Field search trả lời “nhóm nào bị ảnh hưởng”, request/trace search trả lời “điều gì xảy ra với một request”, còn metric và trace giúp kiểm chứng mức độ và nguyên nhân của sự cố.**
