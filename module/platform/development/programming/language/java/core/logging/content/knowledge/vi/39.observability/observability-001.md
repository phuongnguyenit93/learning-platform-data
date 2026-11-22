# Log, Metric, Trace trong Java Observability

## 1. Ba tín hiệu để hiểu một hệ thống đang làm gì

Khi một ứng dụng Java hoạt động bình thường, người dùng thấy request trả kết quả. Khi hệ thống chậm hoặc lỗi, developer cần biết **đã xảy ra sự kiện gì, mức độ ảnh hưởng bao lớn, và request đi qua những bước nào**. Đó là mục tiêu của **observability**: dùng dữ liệu phát ra từ hệ thống để hiểu trạng thái và hành vi bên trong.

Ba tín hiệu thường dùng là **logs, metrics và traces**:

- **Log:** bản ghi một sự kiện cụ thể tại một thời điểm, ví dụ xác thực thất bại hoặc DB connection timeout.
- **Metric:** số đo được tổng hợp theo thời gian hoặc theo tập nhãn, ví dụ request/giây, error rate, p95 latency, số connection đang dùng.
- **Trace:** chuỗi các **span** mô tả đường đi, duration và quan hệ nhân quả của một request/workflow qua các thành phần.

Không có tín hiệu nào hoàn toàn thay thế hai tín hiệu còn lại. Một metric cho biết **“5% request lỗi”** nhưng thường không nói request nào; log cho biết **“request X bị từ chối vì lỗi Y”** nhưng không tự cung cấp phân phối latency; trace cho biết **“request X dành 720 ms chờ database”** nhưng có thể đã được sampling nên không có trace cho mọi request.

### 1.1. Bảng so sánh nhanh

| Câu hỏi | Log | Metric | Trace |
| --- | --- | --- | --- |
| Điều gì vừa xảy ra? | Chi tiết event, level, error code | Số lượng/tỷ lệ sự kiện | Event/span trong luồng |
| Bao nhiêu request bị lỗi? | Đếm được nếu log đầy đủ | **Rất phù hợp** qua counter/rate | Chỉ khi trace coverage đủ |
| p95/p99 độ trễ là bao nhiêu? | Không lý tưởng nếu có sampling/drop | **Histogram/timer** phù hợp | Chi tiết từng request được trace |
| Vì sao một request chậm? | Error/debug messages | Chỉ ra endpoint/tập máy bị ảnh hưởng | **Đường đi và span duration** |
| Cần xem chính xác input nào? | Chỉ metadata đã được phép log | Không đưa input cụ thể vào nhãn | Chỉ attributes đã được kiểm soát |
| Tài nguyên của service nào gây lỗi? | Resource + correlation ID | Resource/low-cardinality labels | service.name của từng span |
| Một request đi qua bao nhiêu service? | Có thể dựng bằng IDs, khó hơn | Không đủ quan hệ call graph | **Phù hợp nhất** với parent/child spans |
| Cảnh báo SLO có bị vi phạm? | Không phải nguồn chuẩn khi sampling | **Metric** nên là nền tảng | Traces hỗ trợ điều tra |

**Quy tắc ghi nhớ:**
- **Metrics** phát hiện và định lượng vấn đề.
- **Traces** khoanh vùng nơi thời gian/lỗi xuất hiện trên đường đi.
- **Logs** giải thích ngữ cảnh, trạng thái và các bước quyết định cụ thể.

Đây là cách phối hợp thường hiệu quả, không phải trình tự bắt buộc cho mọi sự cố. Có những lỗi chỉ có log, có những metric hệ thống quan trọng nhưng không gắn với request, và có trace không chứa bất kỳ log nào.

## 2. Một tình huống thực tế: đặt hàng chậm

Giả sử một khách hàng gọi `POST /api/orders`. Request đi qua gateway, service đặt hàng, service tồn kho và database:

```text
Client
  |
  v
API Gateway -------- 1 HTTP request -------->
  |
  v
Order Service (HTTP SERVER span)
  |--- validate payload (INTERNAL span)
  |--- Inventory Service (HTTP CLIENT span) ---> Inventory HTTP SERVER span
  |--- JDBC query (DB CLIENT span) ------------> Database
  |
  v
HTTP response
```

Khi có vấn đề, ba tín hiệu có thể biểu diễn như sau.

**Metric** (các số chỉ là ví dụ minh họa):

```text
http.server.request.count{route="/api/orders",status="500"} += 1
http.server.duration histogram: một observation = 1.400 s
service CPU utilization = 82%
db connection pool pending = 12
```

**Log**:

```text
ERROR event=order.create_failed route=/api/orders
      error_type=STORAGE_TIMEOUT request_id=req-42
      trace_id=4bf92f3577b34da6a3ce929d0e0e4736
```

**Trace**:

```text
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
  POST /api/orders             1,400 ms
    inventory.validate           60 ms
    db.connection.acquire     1,050 ms
    db.insert                  180 ms
```

Nhìn metric biết đây không phải một request cá biệt nếu p95 và pending connections cùng tăng. Trace cho biết có **connection-pool wait** lớn; log cho biết loại lỗi ở boundary. Các span có thể lồng nhau hoặc chạy song song, nên **không cộng mọi duration trong trace một cách máy móc**.

Những tên field ở trên chỉ là **mô hình minh họa**, không phải mọi backend đều dùng cùng tên. Với OpenTelemetry, nên tuân theo semantic conventions của phiên bản instrumentation đã chọn.

## 3. Logs: mỗi sự kiện có bối cảnh và mức độ

Một log event nên trả lời:
- Thời điểm xảy ra sự kiện.
- Service/instance nào phát ra.
- Event type hoặc message có nghĩa gì.
- Mức độ (DEBUG/INFO/WARN/ERROR) và kết quả.
- Request/trace/span nào liên quan, nếu có.
- Metadata đủ để chẩn đoán nhưng **không chứa secret hoặc dữ liệu cá nhân thừa**.

Một structured log minh họa:

```json
{
  "timestamp": "2026-11-10T10:15:20.123Z",
  "severity": "ERROR",
  "event": "payment.provider_failed",
  "service.name": "orders-service",
  "operation": "authorize_payment",
  "error.type": "REMOTE_TIMEOUT",
  "http.route": "/api/orders",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

Dòng này có các field tùy chỉnh, không phải JSON OTLP chuẩn. OpenTelemetry Logs Data Model định nghĩa các trường khái niệm như `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, `TraceId` và `SpanId`. Encoder và Collector sẽ quyết định cách chuyển log framework sang mô hình đó.

### 3.1. Severity không phải tỷ lệ ảnh hưởng

Một lỗi được ghi `ERROR` có thể chỉ là một request duy nhất; hàng nghìn WARN có thể gây ảnh hưởng lớn hơn. Level giúp phân loại event, còn **mức độ ảnh hưởng trên toàn hệ thống nên đo bằng metrics** như error rate, availability, latency và queue depth.

Không dùng `log.error` như cách duy nhất để tính số request thất bại nếu log có sampling, drop, duplicate hoặc nhiều logger cùng ghi một failure.

### 3.2. Đúng một nơi ghi failure tổng kết

Khi repository ném exception, service bọc lỗi, controller handler quyết định HTTP 503: không cần cả ba tầng log cùng stack trace ở ERROR. Chọn nơi **sở hữu outcome** và thêm context như error code/trace ID; các tầng dưới chỉ log diagnostic khi có thông tin riêng.

Điều này làm log rõ ràng hơn và tránh tăng chi phí không cần thiết. Một trace có thể có nhiều span ghi error status, nhưng không nên hiểu mỗi span ERROR đồng nghĩa một lỗi độc lập.

### 3.3. Không ghi credential vào log

Không log raw `Authorization`, `Cookie`, access token, refresh token, API key, password, query string có signed URL, raw SQL binds hoặc nguyên request body. **Trace ID không phải secret dùng để xác thực**, nhưng vẫn là metadata có thể liên kết hoạt động và cần retention/ACL phù hợp.

Dùng route template `/api/orders/{id}` thay vì raw path chứa ID hoặc mã khôi phục; các giá trị kỹ thuật cũng cần qua policy riêng tư.

## 4. Metrics: số liệu tổng hợp và xu hướng

Metric thường cho biết hiện trạng hoặc lượng công việc theo **series** được xác định bởi tên metric và tập attributes/labels.

Các loại thường gặp:

| Loại | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Counter/monotonic sum | `http.requests.total` | Tổng request, chỉ tăng trong mỗi vòng đời phù hợp |
| UpDownCounter | Số tác vụ đang chạy | Có thể tăng/giảm theo sự kiện |
| Gauge | Heap in use, connection active | Giá trị được quan sát tại thời điểm |
| Histogram | Request duration | Phân phối quan sát thành buckets, count và sum |
| Timer (Micrometer) | `http.server.requests` | Đo count + total duration và tùy cấu hình histogram/percentile |

Các tên trên là ví dụ; OTel, Micrometer, Prometheus và backend có quy tắc đặt tên/đơn vị, chuyển đổi khác nhau. Khi dùng semantic conventions, tuân thủ tên và unit đã công bố thay vì tự đặt cùng khái niệm theo nhiều schema.

### 4.1. Vì sao không tính p95 từ trung bình?

Giả sử 100 request, 95 request mất 40 ms và 5 request mất 2.000 ms. Trung bình:

```text
(95 × 40 + 5 × 2000) / 100 = 138 ms
```

Trung bình 138 ms không mô tả được nhóm người dùng chịu 2 giây. Percentiles như **p50, p95, p99** cùng throughput và error rate hữu ích để theo dõi tail latency. Percentile cần phân phối/histogram hoặc dữ liệu phù hợp và có thể khác nhau theo phương pháp ước lượng.

Không suy p99 của toàn traffic chỉ từ các slow-request logs đã sampling. Nếu histogram được cấu hình và backend hỗ trợ, dùng bucket distribution; nhớ rằng client-side percentile đo tại từng instance **không thể tùy tiện lấy trung bình để ra percentile toàn cụm**.

### 4.2. Tính rate từ Counter

Counter kiểu cumulative được backend xử lý theo quy tắc temporality/reset. Ví dụ request counter là 1.000 lúc 10:00 và 1.120 lúc 10:01 (cùng instance, không reset) thì số request tăng 120 trong 60 giây, rate trung bình **2 request/giây**.

Nếu instance restart, raw cumulative counter có thể giảm về 0; hệ thống truy vấn phải xử lý reset. Không trừ tùy tiện hai mẫu từ hai pod khác nhau mà thiếu resource identity và reset awareness.

### 4.3. High cardinality là một lỗi kiến trúc metrics

Sai:

```text
http_requests_total{user_id="123",request_id="req-42",url="/orders/42"}
```

Những nhãn thay đổi theo người dùng/request tạo rất nhiều series. Hậu quả là tăng memory, storage, index, query cost; có thể khiến pipeline metric chậm hoặc quá tải. Dùng:

```text
http_requests_total{method="GET",route="/orders/{id}",status="200"}
```

**Low cardinality attributes** như method, route template, status class, operation hoặc service version phù hợp cho aggregation. `trace_id` và `request_id` nên ở log/trace để điều tra request riêng, **không phải metric label**.

### 4.4. Metric units và temporality

Duration có thể được xuất theo đơn vị `s` hoặc `ms` tùy instrument và backend; đừng so 0,25 s với 0,25 ms. OTel metrics phân biệt các cách biểu diễn như cumulative/delta temporality; Collector/backend có thể phải chuyển đổi.

Một metric histogram là **số liệu tổng hợp**, không tự chứa đầy đủ danh sách request gốc. Việc mất log không có nghĩa counter cũng mất, và một trace bị drop vì sampling không tự làm histogram sai nếu metrics pipeline vẫn hoạt động.

## 5. Traces: quan hệ và thời gian giữa các span

Một **trace** thường đại diện luồng xử lý một request/workflow. Nó có nhiều **span**, mỗi span biểu diễn một đơn vị công việc:

- `name`, `start/end timestamp`, `duration`.
- `trace_id` chung trong trace.
- `span_id` riêng cho từng span.
- `parent_span_id` nối quan hệ cha/con.
- `span.kind` như SERVER, CLIENT, INTERNAL, PRODUCER hoặc CONSUMER.
- `attributes`, `events`, `links`, `status`.

Ví dụ:

```text
trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
  [server span] POST /orders     1.40 s
      ├─ [client span] inventory 0.06 s
      ├─ [client span] JDBC      1.20 s
      │      ├─ connection wait 1.05 s
      │      └─ INSERT          0.15 s
      └─ [internal] build DTO    0.02 s
```

Trace chỉ hiển thị các span thực sự được tạo và được export/giữ lại. **Không thấy một span không có nghĩa thao tác đó không xảy ra**: có thể instrument chưa phủ, context bị mất, span bị sampling hoặc exporter không gửi thành công.

### 5.1. Trace ID, Span ID và quan hệ nhân quả

Theo W3C Trace Context, một `traceparent` minh họa:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Các phần là version, trace ID (32 chữ số hex), parent ID (16 chữ số hex) và trace flags. Trace ID không được toàn số 0; span ID cũng không được toàn số 0. Khi service B tạo span con, nó có **span ID mới**, thường kế thừa trace ID và gắn parent relationship theo propagation.

Bit sampled trong trace flags là tín hiệu trong context, **không bảo đảm trace đã được lưu ở backend**. Backend có thể không nhận vì exporter lỗi, retention hoặc chính sách sampling khác.

### 5.2. Span duration khác thời gian của cả request

Một span DB có thể là 600 ms nằm trong span HTTP 900 ms; không cộng chúng thành 1.500 ms. Các span lồng nhau có thể cùng tồn tại trên timeline; span song song cũng có thể overlap.

Một span CLIENT và một span SERVER qua hai service có thể có thời gian bắt đầu/giờ hệ thống lệch do clock skew. Cần dùng quan hệ parent/child và các mốc nhân quả để diễn giải, không chỉ sort timestamp của nhiều máy.

### 5.3. Span Event không thay thế mọi application log

Một span event mô tả một mốc có timestamp trong một operation. Nó phù hợp cho việc đánh dấu `"cache.miss"` hoặc `"retry.scheduled"` trong span có liên quan, nhưng không có nghĩa mọi log DEBUG đều phải biến thành span event. Logs và span events có retention, indexing, sampling và cách truy vấn khác nhau.

## 6. Correlation: kết nối logs, metrics, traces bằng gì?

Có ba trục tương quan chính:

1. **Context:** `trace_id` và `span_id` nối log với một span đang active.
2. **Resource:** `service.name`, service version, environment, instance/pod và host nhận diện nguồn phát sinh cả ba signals.
3. **Time + dimensions:** khoảng thời gian incident, route template, method, status, operation và business domain giúp chọn metric/log/trace liên quan.

Một workflow điều tra:
- Metric chỉ ra `GET /orders/{id}` ở service orders có p95 cao.
- Dashboard mở trace/exemplar liên quan, hoặc truy vấn traces theo service + route + thời gian.
- Trong trace thấy DB span chiếm phần lớn duration.
- Dùng `trace_id`/`span_id` tìm log WARN của connection pool wait hoặc timeout.
- Kiểm tra DB pool metrics để biết lỗi ảnh hưởng rộng hay một request.

### 6.1. Trace ID trong log không có nghĩa có trace trong backend

Có thể có log:

```text
WARN ... trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7
```

nhưng tìm trace không thấy. Các nguyên nhân:
- Sampler bỏ trace.
- Collector/exporter/transport chưa hoạt động.
- Backend retention khác log retention.
- UI/query sai environment/tenant hoặc service.
- Instrumentation ghi ID vào MDC nhưng không bật exporter.
- Span không được end/flush, hoặc SDK bị shutdown trước khi gửi.

Ngược lại, trace có thể hiện đầy đủ nhưng log không chứa trace ID nếu logger không nhận context, MDC injection chưa bật, log xảy ra ngoài active span hoặc encoder không in field đó. **Hai chiều phải được kiểm tra độc lập**.

### 6.2. Exemplar nối metric với trace

Trong OTel Metrics Data Model, **exemplar** là một observation được giữ cùng metric point để liên kết giá trị metric với trace context khi có. Ví dụ histogram duration có exemplar gắn `trace_id` và `span_id` cho một sample. Dashboard hỗ trợ exemplar có thể đưa người vận hành từ bucket latency tới một trace cụ thể.

Nhưng exemplar:
- Có thể không tồn tại tùy cấu hình/instrumentation/backend.
- Không lưu mọi request, không phải danh sách trace đầy đủ.
- Không được dùng để “sửa” p95 bằng cách chỉ xem vài sample.
- Có thể mất link nếu trace được sampling/drop hoặc đã hết retention.

Dùng exemplar để **điều tra một ví dụ đại diện**, không thay thế aggregate histogram.

## 7. Java 17+ runnable: mô phỏng ba tín hiệu với cùng một request

Ví dụ sau **chỉ dùng JDK**, chạy được bằng `javac`/`java` mà không cần Collector hay OpenTelemetry SDK. Nó mô phỏng một request có HTTP span và DB span, một metric count + sum duration, và một application log được gắn trace/span ID.

**Đây là mô hình giáo dục**, không phải exporter OpenTelemetry thật. Mục đích là hiểu data shape và cách correlation hoạt động. Các ID và timestamp là test fixture tổng hợp; ứng dụng production phải để instrumentation tạo trace IDs và đo clock phù hợp.

Tạo file `ThreeSignalsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ThreeSignalsDemo {
    private static final String TRACE_ID =
            "4bf92f3577b34da6a3ce929d0e0e4736";
    private static final String SERVER_SPAN_ID =
            "00f067aa0ba902b7";
    private static final String DB_SPAN_ID =
            "b7ad6b7169203331";

    private static final class Capture extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.three.signals");
        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            // Fake monotonic time (nanoseconds), so output is deterministic.
            long httpStart = 1_000_000_000L;
            long dbStart = 1_002_000_000L;
            long dbEnd = 1_006_000_000L;
            long httpEnd = 1_013_000_000L;

            long httpNanos = httpEnd - httpStart;
            long dbNanos = dbEnd - dbStart;
            int requestCount = 1;

            logger.info("event=db.lookup.completed operation=find_order "
                    + "trace_id=" + TRACE_ID
                    + " span_id=" + DB_SPAN_ID);

            System.out.printf(Locale.ROOT,
                    "METRIC requests_total=%d duration_sum_ms=%.3f%n",
                    requestCount, httpNanos / 1_000_000.0);

            System.out.printf(Locale.ROOT,
                    "TRACE name=http.server span_id=%s "
                    + "parent=none duration_ms=%.3f%n",
                    SERVER_SPAN_ID, httpNanos / 1_000_000.0);

            System.out.printf(Locale.ROOT,
                    "TRACE name=db.query span_id=%s "
                    + "parent=%s duration_ms=%.3f%n",
                    DB_SPAN_ID, SERVER_SPAN_ID,
                    dbNanos / 1_000_000.0);

            for (String line : capture.lines()) {
                System.out.println("LOG " + line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Chạy trên JDK 17+:

```bash
javac --release 17 ThreeSignalsDemo.java
java ThreeSignalsDemo
```

Stdout chính xác:

```text
METRIC requests_total=1 duration_sum_ms=13.000
TRACE name=http.server span_id=00f067aa0ba902b7 parent=none duration_ms=13.000
TRACE name=db.query span_id=b7ad6b7169203331 parent=00f067aa0ba902b7 duration_ms=4.000
LOG INFO event=db.lookup.completed operation=find_order trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=b7ad6b7169203331
```

Giải thích:
- `requests_total=1` và tổng duration 13 ms là **metric tổng hợp minh họa cho một observation**, chưa đủ để tính p95.
- HTTP span kéo dài từ 1.000.000.000 đến 1.013.000.000 ns: **13,000 ms**.
- DB span kéo dài từ 1.002.000.000 đến 1.006.000.000 ns: **4,000 ms** và có parent là HTTP span.
- Log `db.lookup.completed` có cùng trace ID và dùng span ID của DB span nên có thể liên hệ tới phần truy vấn dữ liệu.
- `Capture` tránh JUL console mặc định và không tự thêm timestamp; output độc lập với tốc độ máy và locale.
- Không có W3C propagation, remote call, real histogram, SDK hay exporter trong ví dụ. Các dòng có nhãn METRIC/TRACE/LOG là **stdout mô phỏng**, không tự xuất OTLP.

Trong ứng dụng thật, elapsed time dùng `System.nanoTime()` (hoặc clock của tracing/metrics library) thay cho số cố định. Muốn tạo real telemetry, sử dụng OpenTelemetry API/SDK, Micrometer, Java agent hoặc instrumentation phù hợp ở các phần tiếp theo.

## 8. Kiến trúc OpenTelemetry cho Java

Một kiến trúc phổ biến:

```text
Java application
  ├─ SLF4J/Logback/Log4j2 ------> App logs ----\
  ├─ OTel Java agent / API -----> Traces --------+--> OTel Collector
  ├─ Micrometer/OTel Meter -----> Metrics -------/         |
  └─ W3C context propagation                           processors
                                                          |
                                                       exporters
                                                          |
                                         Logs / Metrics / Trace backends
```

Đây là sơ đồ khái niệm. Log có thể được Collector đọc từ stdout/file **hoặc** được chuyển thành OTel LogRecords qua logging bridge/appender tương thích. Không cần luôn dùng cả hai con đường cho cùng một event: **thu stdout lẫn OTLP log của cùng event vào một backend có thể tạo duplicate**.

### 8.1. Vai trò các thành phần

- **Logging framework:** SLF4J là façade; Logback, Log4j 2 hoặc JUL thực hiện ghi event theo cấu hình.
- **OpenTelemetry API:** cung cấp interfaces cho span, meter, log context; không đồng nghĩa exporter đã được cấu hình.
- **OpenTelemetry SDK:** thu/xử lý/export tín hiệu theo configuration, sampling, processors.
- **Java agent (zero-code):** tự instrument những library/framework được hỗ trợ (HTTP server/client, JDBC, v.v.) mà không sửa trực tiếp nghiệp vụ.
- **Micrometer:** API metrics/observation dùng phổ biến trong Spring; observation có thể được nối với tracing khi handlers/bridge được cấu hình.
- **Collector:** nhận telemetry qua receivers, xử lý bằng processors rồi gửi đến exporters/backends.
- **Backend:** index/query logs, timeseries metrics, trace store và UI correlation.

**Đừng nhầm “đã thêm dependency API” với “đã có telemetry trong dashboard”.** Cần instrumentation, SDK/provider, pipeline export và backend thực nhận dữ liệu. Ngược lại, agent có thể tự tạo span mà không cần manual API ở mọi method.

### 8.2. Java agent: ví dụ cấu hình local

Sau khi tải **Java agent JAR** từ release chính thức và có ứng dụng Java đã build, có thể chạy ở môi trường thử nghiệm kiểu Bash:

```bash
export OTEL_SERVICE_NAME="orders-service"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=dev,service.version=1.0.0"

export OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:4318"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="otlp"

java -javaagent:/path/to/opentelemetry-javaagent.jar -jar app.jar
```

Đây là **command tích hợp cần JAR agent, app.jar và một OTLP receiver đang chạy**. Đường dẫn JAR là đường dẫn minh họa; phải thay bằng đường dẫn thật. Cấu hình này chỉ phù hợp **local/test không có secret**: endpoint HTTP không có TLS/auth, không nên mở công khai trên production.

Với Java agent 2.x, giao thức OTLP mặc định của agent thường là `http/protobuf`; ví dụ vẫn đặt tường minh để tránh nhầm cổng `4318` (HTTP) với `4317` (gRPC). Tùy version và instrumentation, log capture từ framework có thể cần cấu hình riêng. **Bật `OTEL_LOGS_EXPORTER=otlp` không chứng minh mọi dòng Logback đã được bridge/export.** Kiểm tra thư viện được hỗ trợ, logger integration, pipeline và kết quả thực.

Không nên bật đồng thời nhiều instrumentation độc lập tạo cùng HTTP server span hoặc cùng metric mà không hiểu duplicate. Nếu Spring Boot có Micrometer observation, kiểm tra OTel agent và bridge trước khi tự instrument chồng lên cùng scope.

## 9. OpenTelemetry Collector: ba pipelines tách biệt

Đây là **ví dụ cấu hình Collector cho local development**, dùng OTLP receiver và `debug` exporter để quan sát cấu trúc telemetry:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "127.0.0.1:4317"
      http:
        endpoint: "127.0.0.1:4318"

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Sơ đồ này cho thấy **tên pipeline riêng** `traces`, `metrics` và `logs`. Một receiver OTLP có thể cung cấp đầu vào cho cả ba, nhưng **không có nghĩa chúng là cùng một tín hiệu**. Trong production cần thêm auth/TLS, memory limits, retry/batch, resource attribution, backend exporters, high-availability, monitoring và chính sách riêng tư.

Cấu hình `debug` có thể in telemetry nhạy cảm vào log của Collector; chỉ dùng trong môi trường an toàn với dữ liệu tổng hợp. Nếu Collector chạy trong container riêng, `127.0.0.1` của container không phải loopback của host hoặc app container; chỉnh network endpoint theo topology thực tế, tránh mở `0.0.0.0` công khai nếu chưa có kiểm soát.

### 9.1. Pipeline logs: chọn một nguồn chính cho cùng event

Có hai đường phổ biến:
- **stdout/file → filelog/agent receiver → backend**.
- **logging bridge/SDK → OTLP receiver → backend**.

Cả hai hợp lệ. Nhưng nếu cùng một event đến cùng backend qua hai đường mà không có policy fan-out/dedup, dashboard có thể thấy hai record. Việc service ghi một bản console và một bản file **không phải tự động sai**; lỗi xảy ra khi pipeline ingest hai bản ấy như hai logical events ngoài mong muốn.

### 9.2. Batch, retry và thời gian quan sát

Collector processors/exporters có batching, buffering và retry. Một log phát trước có thể tới backend sau log khác; `Timestamp` (thời gian nguồn) và `ObservedTimestamp` (thời gian được quan sát) có thể khác. Traces và metrics cũng có độ trễ export riêng. Không dùng thứ tự ghi nhận tại dashboard để suy tuyệt đối thứ tự thực thi của nhiều service.

## 10. Liên kết application logs với active trace context

Trên ứng dụng dùng SLF4J/Logback hoặc Log4j 2, một hướng thường dùng là để instrumentation điền `trace_id`, `span_id` vào logging context/MDC khi có active span, sau đó encoder đưa chúng ra log.

Một pattern **Logback** minh họa:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
      trace_id=%X{trace_id:-} span_id=%X{span_id:-}
      %logger{36} - %msg%n</pattern>
</encoder>
```

Đây là **đoạn XML bên trong appender đã được khai báo**, không phải file `logback.xml` hoàn chỉnh. Trong dự án thật pattern thường được viết trên một dòng để tránh whitespace xuống dòng không mong muốn. `%X{trace_id:-}`/`%X{span_id:-}` đọc MDC; không tự sinh IDs.

**Điều kiện:** logging instrumentation đang gắn context vào MDC với các key tương ứng, ứng dụng có active span và MDC được xử lý đúng. Nếu không, field có thể hiển thị trống. Việc chỉ thêm pattern **không làm hệ thống tự có distributed tracing**.

### 10.1. Lấy trace context thủ công bằng OpenTelemetry API

Khi dự án đã có dependency `io.opentelemetry:opentelemetry-api` và SDK/agent tạo context, có thể lấy active span:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

// Fragment trong method có SLF4J Logger log.
SpanContext context = Span.current().getSpanContext();

if (context.isValid()) {
    log.info("event=order.lookup.completed trace_id={} span_id={}",
            context.getTraceId(), context.getSpanId());
} else {
    log.info("event=order.lookup.completed trace_context=absent");
}
```

Đây là **snippet tích hợp**, không chạy độc lập nếu thiếu OpenTelemetry API và logger. `Span.current()` chỉ trả active context tương ứng thread/scope; nếu chưa instrument hoặc context bị mất, `isValid()` có thể false.

Nếu logger đã inject trace/span ID qua MDC hoặc structured encoder, **không nhất thiết phải tự nhúng lại IDs vào message**: làm vậy tạo duplication trong record và tăng chi phí. Ưu tiên cấu hình chuẩn một lần cho toàn dự án; manual IDs chỉ khi thực sự cần và test được.

### 10.2. Context propagation giữa thread và service

W3C Trace Context giúp truyền span context qua HTTP headers; SDK/instrumentation thực hiện **inject/extract** ở ranh giới network. Với `CompletableFuture`, executor, Reactor, message queues, callbacks và virtual threads, cần instrumentation/context propagation phù hợp.

Một lỗi thường thấy: request thread có trace ID, nhưng worker thread tự chạy tiếp và log mất trace ID. Không sửa bằng cách copy raw Authorization hay đưa token vào baggage. Baggage có thể truyền qua service boundary; **không chứa secret hoặc PII không cần thiết**.

Với async operations, span có thể kết thúc trước khi worker chạy nếu code chỉ mở scope quanh bước submit chứ không quanh completion. Khi thiết kế custom spans, ràng buộc lifecycle với đơn vị công việc thật, đóng scope trong `finally`, `end()` span khi operation kết thúc, và kiểm thử các nhánh exception/cancellation.

## 11. Metrics + Tracing trong Spring Boot/Micrometer

Spring Boot dùng Micrometer để thu metrics và Micrometer Observation để tạo một điểm instrumentation có thể phục vụ cả metrics và tracing khi handlers phù hợp được đăng ký.

Một snippet minh họa, **cần Micrometer Observation và ObservationRegistry được cấu hình**:

```java
import io.micrometer.observation.Observation;

// Fragment trong service có observationRegistry, repository và id.
Observation observation =
        Observation.createNotStarted("order.lookup", observationRegistry)
                .lowCardinalityKeyValue("operation", "find_by_id")
                .start();

try (Observation.Scope scope = observation.openScope()) {
    repository.findById(id);
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
```

Ý nghĩa:
- `Observation` xác định một đơn vị công việc.
- Low-cardinality key `operation=find_by_id` phù hợp cho metrics.
- `openScope()` gắn context vào scope hiện hành để handler có thể sử dụng.
- `error(ex)` báo lỗi cho observation; exception vẫn được ném lại.
- `stop()` kết thúc đơn vị công việc, kể cả khi có lỗi.

**Chỉ tạo ObservationRegistry không bảo đảm tự có spans/metrics**. Cần ObservationHandlers, MeterRegistry/tracing bridge và exporter thực tế; tên metric/span, conventions và thuộc tính phụ thuộc cấu hình Spring/Micrometer. Nếu framework đã instrument HTTP/JDBC thì không bọc lại cùng operation bằng một observation trùng tên chỉ để “cho đủ ba tín hiệu”.

### 11.1. Timer/Histogram giúp biết tail latency

Với Micrometer timer, thống kê gồm count và total time, có thể có histogram/percentiles nếu cấu hình. Timer không phải trace và không lưu toàn bộ raw request durations. Một câu lệnh `timer.record(...)` không tự gắn trace ID cho mọi observation trừ khi hệ thống có exemplar/context integration phù hợp.

Một pattern đánh giá tốt:
- `http.server.requests`/HTTP server metrics đánh giá SLO.
- Custom observation cho business operation thật sự cần nhìn riêng.
- Log structured error events chỉ khi có điều gì cần điều tra.
- Trace spans cho đường đi service-to-service và các thao tác quan trọng.

Đừng dùng `user_id`, `request_id` hoặc `trace_id` làm low-cardinality metric tags.

## 12. Sampling: vì sao có logs nhưng không thấy traces?

Trace sampling làm giảm volume và chi phí nhưng có thể khiến một log có trace ID không tìm thấy trace tương ứng.

Các cách sampling:
- **Head sampling:** quyết định sớm, thường gần lúc tạo root trace.
- **Tail sampling:** Collector hoặc backend cân nhắc sau khi có đủ span/trace trong một khoảng thời gian, ví dụ giữ các traces lỗi/chậm theo policy.
- **Adaptive sampling:** tỷ lệ được điều chỉnh theo lưu lượng/điều kiện tùy hệ thống.

Đây là các khái niệm; cấu hình cụ thể phải theo thư viện/backend và cần xét memory, latency, tính nhất quán của traces đi qua nhiều collectors.

**Không đánh đồng trace sampling với log sampling và metric aggregation:**
- Trace được chọn 10% có thể vẫn giữ metric histogram cho toàn request, nếu instrumentation metrics hoạt động độc lập.
- Log vẫn có thể được ghi khi trace không export, tùy log instrumentation/pipeline.
- Sampling log một cách mù quáng có thể loại đúng những ERROR hiếm; nên có policy theo severity/event.
- Metric points có thể bị drop do lỗi pipeline riêng; việc trace vẫn hoạt động không chứng minh metrics đầy đủ.

Một trace ID trong log giúp correlation **khi trace còn có thể truy cập**, không phải bảo đảm tìm được trace.

### 12.1. Exemplars và sampling

Một metric exemplar có thể trỏ tới một trace sample, nhưng không phải mọi observation có exemplar và không phải mọi exemplar còn trace ở backend. Nếu backend có hỗ trợ, người vận hành có thể chọn exemplar của bucket chậm và mở trace liên quan.

Để alert, vẫn ưu tiên histogram/rate và SLO. Một trace exemplar không phải chứng cứ thống kê đầy đủ.

## 13. Timestamp và đồng hồ: ba tín hiệu không nhất thiết hiện cùng lúc

Có nhiều mốc thời gian:
- **Event timestamp:** khi log event xảy ra ở nguồn.
- **Observed timestamp:** lúc Collector/receiver nhận biết event.
- **Span start/end:** thời điểm bắt đầu/kết thúc operation, có thể đo ở các service khác nhau.
- **Metric observation timestamp / collection interval:** thời điểm điểm đo được ghi nhận hoặc xuất tổng hợp.
- **Ingestion time:** lúc backend lưu và index.

Một log có `Timestamp=10:00:00.100` nhưng chỉ ingest lúc `10:00:01.000` vì queue/retry. Metric collection có thể cập nhật dashboard vài giây sau. Trace exporter cũng batch riêng. **Khác thời điểm hiển thị không tự nghĩa hệ thống thực thi sai thứ tự.**

Clock skew giữa các host có thể làm timestamps đảo dù quan hệ HTTP request/response đúng. Dùng W3C parent/child context và monotonic elapsed clocks ở phạm vi phù hợp để giải thích duration. `System.nanoTime()` dùng tính chênh lệch trong cùng JVM, không dùng giá trị tuyệt đối giữa các JVM như Unix timestamp.

Trong OTel Logs, `Timestamp` và `ObservedTimestamp` là hai trường khác nhau. Không xóa timestamp nguồn để “cả hệ thống cùng giờ” mà chưa hiểu giá trị chẩn đoán bị mất.

## 14. Chi phí, cardinality và bảo vệ dữ liệu

Ba tín hiệu có kiểu chi phí khác nhau:

| Tín hiệu | Yếu tố chi phí | Tối ưu hóa nên làm |
| --- | --- | --- |
| Logs | Số records, kích thước, index, retention | Structured events, levels, sampling có policy, tránh duplicate |
| Metrics | Số time series theo labels, bucket count, scrape/export frequency | Low-cardinality dimensions, histogram hợp lý |
| Traces | Số traces/spans, attributes, events, sampling, retention | Instrument operations có ý nghĩa; sampling và attribute limits |
| Collector | CPU/memory queue, batch/retry, exporters | Bounded pipelines, monitoring, backpressure và SLO |

Dữ liệu có độ nhạy cảm khác nhau:
- **Logs:** message hoặc exception có thể chứa PII, SQL binds, token.
- **Metrics:** labels có thể vô tình chứa raw user ID/URL, gây cả rủi ro privacy lẫn cardinality.
- **Traces:** span attributes, events, baggage, HTTP headers hoặc DB query có thể chứa secret.

Không log nguyên `Authorization`, `Cookie`, password, access token, refresh token, client secret, private key, signed URL/query hoặc raw SQL bind values. Tránh đưa những dữ liệu đó vào span attributes, baggage hoặc metric tags; sanitizer ở Collector chỉ là lớp bảo vệ bổ sung **sau khi dữ liệu đã rời JVM**.

Áp dụng least privilege, retention phù hợp, TLS/auth giữa exporter và backend, và secret scanning trên synthetic fixtures. Một log có thể được sao chép sang alert/ticket/backup, nên xóa từ app console không loại bỏ bản đã lưu ở nơi khác.

### 14.1. Cardinality nên được kiểm soát ở đúng tín hiệu

`request_id` phù hợp cho **log correlation**, nhưng không cho metric label. Trong trace, high-cardinality attribute đôi khi hữu ích để tìm một request cụ thể nhưng vẫn có chi phí/privacy cần cân nhắc; **không có nghĩa phải cấm mọi ID trong trace**. Cần policy khác nhau theo instrument, backend, sampling và mục đích.

`http.route` nên là route template; raw URI với order ID có thể có tập giá trị gần như vô hạn. Với HTTP metrics, method + route + status thường đủ cho aggregation.

## 15. Sự cố ví dụ: p95 tăng, tìm nguyên nhân bằng ba tín hiệu

Bối cảnh: service `orders-service` đột ngột có p95 latency từ 180 ms lên 1.600 ms sau deploy.

### Bước 1 — Metric: xác nhận phạm vi

Kiểm tra:
- `http.server.requests` và p95/p99 theo route.
- Error rate và request rate (có tăng đột biến không?).
- CPU, GC, heap, thread pool.
- DB pool active/pending/acquire time.
- Service version/pod khác nhau để so trước–sau.

Nếu chỉ một route bị ảnh hưởng, thu hẹp nhanh. Nếu cả cụm tăng, có thể hạ tầng chung bị nghẽn.

### Bước 2 — Trace: xem critical path

Chọn traces từ route và thời gian incident, ưu tiên traces chậm/lỗi có mặt trong backend:
- HTTP server span có bao lâu?
- DB client span có bao lâu?
- Có outbound HTTP retry, queue wait, lock contention?
- Các span chạy song song hay lồng nhau?
- Có missing span do instrumentation chưa phủ không?

Đừng cộng duration của mọi span; tìm đoạn nằm trên **critical path**.

### Bước 3 — Logs: tìm ngữ cảnh cụ thể

Lấy trace ID từ span rồi truy vấn log:
- `event=storage.connection_wait` hoặc `event=repository.slow_operation`.
- Error type và retry attempt.
- Request/operation ID phù hợp.
- Log chứa dấu hiệu đã qua fallback hoặc một exception được xử lý.

Nếu log không có trace ID, kiểm tra MDC/active context; tìm theo time + service + route chỉ là phương án gần đúng, có thể trả về nhiều request khác nhau.

### Bước 4 — Hành động và xác minh

Giả sử phát hiện connection pool pending cao sau release, nên kiểm tra connection leak, quá nhiều concurrency, query slow hoặc giới hạn pool/DB. Sửa nguyên nhân, sau đó xác minh **metric p95 giảm, trace DB wait giảm, log warnings giảm**. Không chỉ tắt WARN logger để cảnh báo biến mất.

## 16. Khi một trong ba tín hiệu không xuất hiện

### 16.1. Có logs nhưng không có traces

Kiểm tra:
1. Java agent/API/SDK có thật sự khởi tạo?
2. Span có được tạo, đang active và được end?
3. Head/tail sampling có bỏ trace?
4. W3C propagator có inject/extract qua HTTP/messaging?
5. OTLP exporter/Collector traces pipeline có hoạt động?
6. Backend trace index/tenant/retention có đúng?
7. Clock/timestamp/search filter có khiến trace nằm ngoài khoảng tìm không?

Có `trace_id` trong log chỉ chứng minh nó được ghi ở một tầng nào đó, không chứng minh collector đã nhận span.

### 16.2. Có traces nhưng logs không có trace_id

Kiểm tra:
1. Log có được phát trong active span/scope?
2. Logger backend có injection MDC/context phù hợp không?
3. Encoder có xuất đúng `trace_id` và `span_id` không?
4. Khi `CompletableFuture`/Reactor xử lý async, context có được propagate?
5. Có log sớm trước khi tạo span hoặc sau khi span đã kết thúc?
6. Log chỉ đến từ filelog receiver nhưng parser không nhận diện field ID?

Không “sửa” bằng cách lấy ID từ một thread-local của request khác hoặc từ header do client tự cung cấp mà không validate.

### 16.3. Có traces/logs nhưng metric bằng 0

Kiểm tra:
- Có MeterProvider/MeterRegistry và metric exporter không?
- Metric instrument có được cập nhật hay chỉ mới đăng ký?
- Collection interval có quá dài, data chưa export?
- Collector metrics pipeline có receiver/exporter tương ứng?
- Unit/temporality có bị backend hiểu sai?
- Dashboard query có đúng service/route labels?
- Cardinality limits có drop series hoặc labels thay đổi?

**Ba pipelines có thể lỗi độc lập**. Không suy “OTel đã bật” là mọi tín hiệu chắc chắn có dữ liệu.

## 17. Các lỗi triển khai thường gặp

**Lỗi 1 — tin rằng Logback sẽ tự sinh trace:** SLF4J/Logback ghi log, không tự có distributed spans; cần instrumentation/context.

**Lỗi 2 — dùng `trace_id` làm metric label:** tăng cardinality tới mức metric backend khó vận hành.

**Lỗi 3 — chỉ nhìn logs để tính p99:** log sampling/drop/duplicate khiến tập quan sát thiếu hoặc méo; dùng histogram/timer metrics.

**Lỗi 4 — tạo span cho từng getter/setter:** volume lớn, khó đọc trace; chọn unit of work thực sự có giá trị.

**Lỗi 5 — dùng một trace cho cả batch công việc không liên quan:** có thể tạo trace khổng lồ và sai quan hệ; phân biệt parent/child và span links theo semantics workflow.

**Lỗi 6 — mất context khi chuyển thread:** async worker log thiếu trace ID; instrumentation/context propagation phải bao đúng lifecycle.

**Lỗi 7 — log cả token vào MDC/baggage:** rò secret xuyên logger/trace/service. Dùng request ID an toàn thay thế.

**Lỗi 8 — vừa stdout/filelog vừa OTLP log trực tiếp:** một event bị ingest hai lần vào cùng backend nếu không chủ đích.

**Lỗi 9 — gắn cả OTel agent và manual instrumentation cùng HTTP server scope:** có thể duplicate spans/metrics; cần kiểm tra bản đồ instrumentation.

**Lỗi 10 — dùng service.name mặc định/không ổn định:** logs, metrics, traces khó join; cấu hình resource nhất quán.

**Lỗi 11 — coi trace sampled là dữ liệu thống kê toàn bộ traffic:** sampling có thể thiên lệch; metrics dùng riêng cho SLO và rate.

**Lỗi 12 — so timestamp của nhiều service như đồng hồ tuyệt đối:** clock skew và queueing có thể đảo; xem causal span relationships.

**Lỗi 13 — ghi lỗi ở mỗi tầng:** cùng một failure có nhiều ERROR logs và span events vô ích; một nơi sở hữu log tổng kết.

**Lỗi 14 — sử dụng Collector debug exporter trong production:** có thể in telemetry nhạy cảm vào chính log của Collector và tăng volume.

**Lỗi 15 — đo “thành công” ngay trước transaction commit:** log hoặc span success có thể sai nếu commit thất bại sau đó. Với audit bền vững, dùng outbox/transactional storage.

## 18. Ma trận QA cho Java Observability

| Test | Điều cần kiểm tra |
| --- | --- |
| HTTP 200 đồng bộ | Có request metric, một server span khi được sampling, log theo policy |
| HTTP 500 lỗi JDBC | Error metrics phản ánh outcome, trace/span status hợp lý, log error có error type |
| Một request qua 2 service | Trace ID được propagate, service B tạo span ID mới |
| Log trong active span | Log chứa trace/span ID theo schema nếu đã cấu hình |
| Log ngoài active span | Không giả mạo ID; event vẫn hợp lệ |
| Async/CompletableFuture | Context được propagate, span lifecycle theo completion |
| Head sampling bỏ trace | Metric vẫn cập nhật; log behavior theo policy độc lập |
| Collector/exporter lỗi | Có diagnostics/queue retry; nhận biết loss thay vì im lặng |
| Exemplar hỗ trợ | Metric link tới trace khi thực sự có; không mặc định mọi mẫu đều có |
| Logback + OTLP/filelog | Không ingest duplicate cùng event vào một index |
| HTTP route chứa ID | Metrics dùng route template; không dùng raw URI |
| Exception message có token giả | Không lộ canary secret vào log/span/metric attributes |
| High-cardinality input | Metric label policy không cho raw user/request/token |
| Restart service | Counter resets và telemetry shutdown/export được xử lý đúng |
| Clock skew | Causal trace và source timestamp không bị hiểu sai |
| Spring Observation + OTel agent | Không có duplicate instrumentation cho cùng operation |
| Traffic spike | Không mất metrics do series explosion; bounded export pipeline |
| Dashboard correlation | Từ metric route → trace → log theo ID/resource và khoảng thời gian |

Dùng một trace ID tổng hợp trong unit test để assert formatting, nhưng với integration cần cho tracer/agent thực sự tạo IDs và propagation. Khi test sản xuất, không sử dụng credential thật, không mở debug exporter ra ngoài mạng.

## 19. Quy trình triển khai có thể lặp lại

1. **Định nghĩa mục tiêu:** availability, error rate, p95 latency, DB pool wait, queue delay, business operation nào cần thấy?
2. **Xác định resource identity:** `service.name`, environment, version, instance; thống nhất ba tín hiệu.
3. **Chọn phương án instrumentation:** Java agent, Spring/Micrometer Observation hoặc manual API ở những khoảng còn thiếu.
4. **Xác định schema log:** event code, severity, error type, route template, request/trace/span IDs đã được duyệt.
5. **Cấu hình metrics:** counter/gauge/histogram với low-cardinality labels và đơn vị rõ ràng.
6. **Cấu hình traces:** span name/kind, parent relationships, W3C propagation, sampling hợp lý.
7. **Thiết lập exporters/Collector:** OTLP protocol, receiver, processor, pipelines riêng, TLS/auth, buffering/retry.
8. **Kiểm tra log path:** stdout/file shipper hay OTLP bridge, tránh ingest hai bản cùng event.
9. **Kiểm thử correlation:** từ một request thử, tìm log bằng trace ID, kiểm tra spans và metrics increment.
10. **Test failure/async/restart:** context loss, timeout, queue-full, retry và shutdown.
11. **Kiểm soát cost/privacy:** cardinality, sampling, retention, access control, secret redaction ngay nguồn.
12. **Vận hành theo tín hiệu:** alert bằng metrics/SLO, drill down bằng traces, chẩn đoán chi tiết bằng logs.

**Kết luận:** Logs trả lời **“điều gì đã xảy ra?”**, Metrics trả lời **“xảy ra nhiều đến mức nào, có xu hướng gì?”**, Traces trả lời **“xảy ra ở đoạn nào trong hành trình xử lý?”**. Observability hiệu quả không phải phát thật nhiều dữ liệu, mà là thiết kế **ba tín hiệu nhất quán về service, thời gian, context và quyền riêng tư** để một sự cố có thể được phát hiện, khoanh vùng và giải thích có bằng chứng.

## Tài liệu tham khảo chính thức

- [OpenTelemetry – Signals: Logs, Metrics, Traces](https://opentelemetry.io/docs/concepts/signals/).
- [OpenTelemetry – Java overview](https://opentelemetry.io/docs/languages/java/).
- [OpenTelemetry – Java Agent zero-code instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/).
- [OpenTelemetry – Java Agent configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/).
- [OpenTelemetry – Logs Data Model và correlation](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OpenTelemetry – Log Correlation](https://opentelemetry.io/docs/specs/otel/logs/).
- [OpenTelemetry – Metrics Data Model và exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/).
- [OpenTelemetry – Trace API, SpanContext và propagation](https://opentelemetry.io/docs/specs/otel/trace/api/).
- [OpenTelemetry – Propagators API](https://opentelemetry.io/docs/specs/otel/context/api-propagators/).
- [OpenTelemetry – Collector processors](https://opentelemetry.io/docs/collector/components/processor/).
- [OpenTelemetry – Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/).
- [Micrometer – Observation handlers](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).