# Tương thích log collector trong Java Structured Logging

## 1. “Tương thích log collector” nghĩa là gì?

Trong một ứng dụng Java, **structured logging** là việc phát bản ghi có những trường mang ý nghĩa rõ ràng, chẳng hạn `timestamp`, `level`, `event`, `service`, `order_id` và `duration_ms`. Tuy nhiên, chỉ vì ứng dụng tạo ra một chuỗi trông giống JSON thì **không có nghĩa** hệ thống thu thập log sẽ hiểu, lưu giữ và cho phép truy vấn đúng các trường ấy.

**Log collector** là thành phần nhận log từ ứng dụng hoặc môi trường chạy, sau đó có thể giải mã, chuẩn hóa, thêm metadata, lọc và gửi tới một hệ thống lưu trữ/tra cứu. Ví dụ về họ công cụ là Fluent Bit, OpenTelemetry Collector, Elastic Agent/Filebeat, Grafana Alloy hoặc một collector do tổ chức phát triển. Mỗi công cụ có nhiều receiver/input, processor và output/exporter; không có một cấu hình chung hoạt động mặc định với mọi đầu vào.

**Tương thích log collector** nghĩa là **producer và collector thống nhất được hợp đồng đầu-cuối** về:

1. **Nguồn thu**: stdout/stderr, file, socket, HTTP hay OTLP.
2. **Transport và framing**: byte được gửi như thế nào, mỗi sự kiện bắt đầu/kết thúc ở đâu.
3. **Encoding và format**: UTF-8, NDJSON, protobuf, syslog, GELF...
4. **Schema**: tên trường, kiểu dữ liệu, giá trị bắt buộc/tùy chọn và ý nghĩa.
5. **Timestamp**: múi giờ, đơn vị và thời điểm sự kiện được tạo hay thu thập.
6. **Severity và metadata**: ánh xạ mức log, tên dịch vụ, trace/correlation ID.
7. **Đầu ra collector**: parser, enrichment, filter, buffer, exporter và lưu trữ.
8. **Độ tin cậy/bảo mật**: sự kiện lỗi parse, mất/trùng dữ liệu, thông tin nhạy cảm, TLS và quyền truy cập.

Một đường logging tốt có thể cho người vận hành trả lời: “Tất cả bản ghi `payment_failed` của `checkout-service` trong 15 phút vừa qua là gì?”, “Lỗi này thuộc trace nào?” và “Có bản ghi nào bị collector từ chối vì sai schema không?”.

**Điểm mấu chốt:** “Java đã gọi `LOG.info`” chỉ xác nhận phần code có thể tạo sự kiện. “Collector đã nhận bytes” chỉ xác nhận một chặng. “Log xuất hiện trên dashboard với trường và thời gian đúng” mới là một phần của kiểm chứng tích hợp cần thiết.

## 2. Toàn bộ đường đi: producer → collector → storage

```text
Java application
  |
  +-- Logger.info(...) / Logger.log(...)
  |          |
  |          v
  |    LogEvent / LogRecord
  |          |
  |          v
  |    JSON Encoder / Formatter / Layout
  |          |
  v          v
 stdout       file / network exporter
  |                    |
  +----------+---------+
             |
             v
      Collector input
             |
             v
    Framing & decoding
      (line/JSON/OTLP)
             |
             v
      Field extraction
  timestamp / severity /
   attributes / resource
             |
             v
   Enrichment & filtering
             |
             v
    Queue / exporter / TLS
             |
             v
       Log storage
             |
             v
       Query / alert
```

Các bước có thể nằm ở những thành phần khác nhau, hoặc một số bước được bỏ qua khi đường truyền đã có dữ liệu typed. Ví dụ:

- Ứng dụng in **JSON Lines lên stdout**; runtime container giữ bản ghi; agent đọc log container, lấy phần `log`, parse JSON rồi gửi đến kho log.
- Ứng dụng ghi **file NDJSON**; một receiver `filelog`/tail theo dõi file và chuyển từng dòng sang LogRecord có các thuộc tính.
- Ứng dụng dùng **OTLP exporter**; collector nhận một cấu trúc telemetry theo giao thức OTLP, **không** giả định đó là một chuỗi NDJSON đọc bằng `readLine()`.

Trước khi chọn công nghệ hoặc sửa code Java, phải xác định **điểm tích hợp**. Nếu nền tảng đã thu stdout, thêm SocketAppender gửi trực tiếp đến một collector khác có thể tạo **hai đường ghi trùng nhau**. Nếu collector chỉ đọc file, chỉ cấu hình ConsoleAppender stdout có thể làm bản ghi không đến nơi cần.

## 3. Hợp đồng đầu vào: một collector cần biết gì?

Có thể bắt đầu bằng bảng **producer–collector contract** như sau:

| Hạng mục | Hợp đồng minh họa | Lỗi nếu hai phía không khớp |
| --- | --- | --- |
| Nguồn | stdout của service Java được agent thu | Collector theo dõi nhầm file hoặc chỉ đọc stderr |
| Framing | Một JSON object trên **một dòng** | Pretty JSON nhiều dòng bị tách thành nhiều sự kiện |
| Encoding | UTF-8 | Tên tiếng Việt lỗi, JSON có byte không hợp lệ |
| Timestamp | `timestamp`, RFC 3339/ISO 8601 có múi giờ, UTC | Log bị đặt sai giờ hoặc bị ingest với thời điểm nhận |
| Severity | `severity_text` là chuỗi; collector có mapping | `WARNING` của JUL bị coi như text không chuẩn hóa |
| Service | `service_name` là tên logic ổn định | Log không được nhóm đúng service |
| Event | `event` là mã sự kiện ổn định | Dashboard phụ thuộc câu message biến thiên |
| Duration | `duration_ms` là số nguyên mili giây | Tính P95 sai nếu ghi chuỗi hoặc đổi đơn vị |
| Trace | `trace_id`/`correlation_id` là chuỗi tùy chọn | Không ghép được luồng điều tra |
| Missing field | Có quy định khi không áp dụng | Parser hoặc query nhầm `null`, `""`, thiếu key |
| Exception | Trường exception có mã hóa phù hợp | Stack trace làm vỡ nhiều dòng log |
| Giới hạn | Byte/event, rate, retention, sampling | Bản ghi bị truncate/drop âm thầm |

Đây là **hợp đồng ví dụ cho một ứng dụng**, không phải schema chuẩn của Fluent Bit, OpenTelemetry hay Elastic ECS. Collector có thể yêu cầu các tên khác và đưa chúng tới các trường bên trong của hệ thống đích.

Một log “tương thích” cần thỏa ít nhất ba lớp:

- **Tương thích cú pháp:** collector giải mã được.
- **Tương thích ngữ nghĩa:** field, type, unit và severity được diễn giải đúng.
- **Tương thích vận hành:** dữ liệu tới đúng nguồn/đích, không bị rơi không kiểm soát và không phá hệ thống khi tải tăng.

## 4. JSON Lines (NDJSON): lựa chọn phổ biến cho stdout và file

Với collector đọc từng dòng, một hợp đồng đơn giản là **mỗi LogEvent tương ứng một JSON object hợp lệ trên đúng một dòng UTF-8**, kết thúc bằng newline `\n`.

Ví dụ:

```json
{"timestamp":"2026-11-09T12:00:00Z","severity_text":"INFO","service_name":"order-service","event":"order_created","order_id":"ORD-101","duration_ms":25}
{"timestamp":"2026-11-09T12:00:01Z","severity_text":"WARNING","service_name":"order-service","event":"payment_retry_scheduled","order_id":"ORD-102","duration_ms":1500}
```

Hai dòng trên là **hai JSON object riêng**, không phải một JSON array. Với parser JSON Lines, mỗi dòng có thể được giải mã thành một event.

Ví dụ **không phù hợp** khi collector đang đọc theo từng dòng:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "event": "order_created",
  "order_id": "ORD-101"
}
```

Đây là **một đối tượng JSON hợp lệ khi ghép cả khối**, nhưng mỗi dòng riêng lẻ như `"{"` hoặc `"order_id": ...` không phải một event JSON hoàn chỉnh. Nếu muốn xuất JSON nhiều dòng, collector cần **multiline framing** được cấu hình riêng. Với Fluent Bit, tài liệu phân biệt rõ JSON Lines và pretty-printed multiline JSON.

### Stack trace và xuống dòng

Một Java exception có thể được hiển thị nhiều dòng:

```text
java.io.IOException: timeout
    at example.Gateway.call(Gateway.java:42)
    at example.Checkout.run(Checkout.java:17)
```

Nếu ứng dụng xuất stack trace trực tiếp giữa các dòng NDJSON, collector có thể coi mỗi stack frame là một bản ghi mới. Có hai hướng hợp lý:

1. **JSON encoder** đưa stack trace thành **một giá trị chuỗi** và escape newline bằng ký tự `\n` trong chuỗi JSON. Toàn bộ object vẫn nằm trên một dòng vật lý.
2. Nếu hệ thống bắt buộc xuất stack trace text nhiều dòng, cấu hình **multiline parser** phù hợp ở collector để ghép các dòng trước khi parse.

**Đừng tự nối JSON bằng string** rồi giả định quote, dấu gạch chéo ngược, ký tự điều khiển và Unicode đã an toàn. Trong production hãy dùng encoder JSON của backend hoặc thư viện serializer đã được kiểm thử.

## 5. JSON hợp lệ chưa đủ: field phải đúng kiểu và đúng nghĩa

So sánh:

```json
{"event":"request_completed","duration_ms":150,"success":true}
```

với:

```json
{"event":"request_completed","duration_ms":"150","success":"true"}
```

Hai dòng đều là JSON hợp lệ. Nhưng ở dòng thứ nhất `duration_ms` là **số**, `success` là **boolean**; dòng thứ hai cả hai là **chuỗi**. Một collector hoặc hệ thống index có thể áp dụng mapping khác, làm phép tính trung bình và bộ lọc đúng/sai gặp vấn đề.

Một số quy tắc nên thống nhất:

- **Đơn vị trong tên field:** `duration_ms` là mili giây; `bytes_sent` là byte; không đổi sang giây nhưng vẫn giữ tên.
- **Kiểu ổn định:** không ghi `status_code=200` kiểu number ở service A rồi `"200"` kiểu string ở service B nếu cùng chỉ mục/schema.
- **Giá trị null:** phân biệt **thiếu trường**, `null`, `""` và `"UNKNOWN"` khi ngữ nghĩa khác nhau.
- **Tên trường:** thống nhất `order_id`, `orderId` hay `order.id` theo contract; tránh ngẫu nhiên thay theo team.
- **Trường lồng nhau:** collector phải biết có hỗ trợ object/nested field không, có giới hạn depth không và có flatten field không.
- **Key trùng:** tránh hai lần `"status"` trong cùng object; parser có thể giữ giá trị cuối hoặc có hành vi không tương thích.
- **Kích thước số:** số nguyên quá lớn có thể mất độ chính xác trong một số parser hoặc backend. Các ID lớn nên được lưu như chuỗi định danh thay vì đem tính toán.
- **NaN/Infinity:** không phải literal số hợp lệ trong JSON tiêu chuẩn; cần biểu diễn và chính sách riêng khi dữ liệu số không hữu hạn.
- **Dữ liệu tùy ý:** cân nhắc whitelist những trường cần quan sát; log nguyên object nghiệp vụ có thể gây nổ schema, rò rỉ dữ liệu và tăng chi phí.

### Một bản ghi nên có field nào?

Một schema ứng dụng có thể gồm:

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `timestamp` | String RFC 3339 | Thời điểm sự kiện phát sinh |
| `severity_text` | String | Mức log gốc từ logger |
| `service_name` | String | Dịch vụ logic phát bản ghi |
| `environment` | String | Ví dụ `production`, `staging` |
| `event` | String | Mã sự kiện ổn định |
| `message` | String | Mô tả con người đọc |
| `order_id` | String | Định danh nghiệp vụ theo từng bản ghi |
| `duration_ms` | Number | Thời lượng mili giây |
| `trace_id` | String, optional | Kết nối với distributed trace |
| `schema_version` | Number/String theo quy ước | Phiên bản hợp đồng của bản ghi |

Các trường này là **đề xuất cho một contract tự thiết kế**, không phải khẳng định ECS và OpenTelemetry dùng đúng các tên ấy. Nếu tổ chức đã có schema, cần theo schema đó để tránh chuyển đổi nhiều lần.

## 6. Timestamp: thời gian của sự kiện hay thời gian collector nhận?

Một lỗi rất khó thấy là log được ingest thành công nhưng **nằm sai khung thời gian** trên dashboard.

Phân biệt:

- **Event timestamp:** khi sự kiện xảy ra ở ứng dụng Java.
- **Observed/ingest timestamp:** khi agent/collector hoặc nơi lưu thấy bản ghi.
- **Indexed timestamp:** thời điểm dữ liệu được ghi vào kho tra cứu.

Một event có thể phát lúc `12:00:00Z`, được collector đọc lúc `12:00:02Z` và đến storage sau đó. Nếu collector không parse được thời gian gốc và thay bằng thời gian nhận, điều tra thứ tự sự kiện có thể bị sai.

Với JSON Lines, lựa chọn dễ đọc là:

```json
{"timestamp":"2026-11-09T12:00:00.123Z","event":"order_created"}
```

Dấu `Z` cho biết UTC. Nếu dùng offset như `+07:00` thì phải giữ chính xác ý nghĩa offset; đừng ghi giờ Việt Nam nhưng gắn nhãn `Z`.

Các trường hợp phải kiểm tra:

1. **Tên trường:** collector có tìm `timestamp`, `time`, `@timestamp` hay một tên khác?
2. **Định dạng:** RFC 3339, epoch milliseconds, epoch seconds, nanoseconds hoặc format tùy chỉnh?
3. **Timezone:** UTC, offset tường minh hay timezone mặc định của máy?
4. **Độ chính xác:** milli/micro/nanoseconds; có bị cắt hay chuyển đơn vị sai không?
5. **Clock skew:** đồng hồ host bị lệch so với collector và các host khác.
6. **Timestamp thiếu/không hợp lệ:** collector bỏ bản ghi, để nguyên chuỗi hay gán thời gian nhận?
7. **Retention theo thời gian nào:** event time hay ingest time?
8. **Dữ liệu đến trễ:** log bị buffer lâu có thể nằm ngoài khoảng tìm kiếm hiện tại.

**Đặc biệt với OpenTelemetry:** mô hình log phân biệt `Timestamp` và `ObservedTimestamp`. Trong giao thức OTLP, thời gian có thể được biểu diễn dưới dạng nanoseconds từ Unix epoch, **không giống** hợp đồng JSON text có field `timestamp` RFC 3339. Cần converter/processor khi đi từ format này sang format kia.

## 7. Severity: giữ log level và chuẩn hóa ở collector

Java có nhiều API logging:

| API Java | Các mức thường gặp | Cần lưu ý khi collector mapping |
| --- | --- | --- |
| JUL (`java.util.logging`) | `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST` | Không có `ERROR`/`WARN`/`DEBUG` theo tên mức JUL |
| SLF4J | `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | API không tự quyết định collector sẽ gán severity number nào |
| Log4j2 | `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | Một số mức có tên/giá trị riêng của backend |
| Collector/OTel | Severity text và/hoặc normalized severity number | Cần mapping có chủ đích, không đoán bằng tên chuỗi |

Ví dụ, JUL phát `Level.WARNING`. Nếu JSON encoder ghi `"severity_text":"WARNING"` nhưng một dashboard chỉ lọc `"WARN"`, sự kiện vẫn có thể được thu mà **không hiện trong kết quả**. Giải pháp là thống nhất:

- Giữ **severity text gốc** để phục vụ chẩn đoán.
- Chuẩn hóa về các nhóm như `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` ở collector nếu backend cần.
- Dùng một mapping rõ ràng cho các mức JUL `CONFIG`, `FINE`, `FINER`, `FINEST`.
- Nếu backend dùng **severity number**, quy định ánh xạ và kiểu number đúng chuẩn đích.
- Kiểm tra cả trường hợp **không có level**, giá trị sai hoặc mức tùy biến.

**Không sửa mọi lời gọi Java chỉ để làm hợp một bộ lọc dashboard** khi collector có thể mapping đúng và có quy trình quản trị schema. Tuy nhiên, nếu dự án đã dùng một chuẩn event chung từ nguồn, giữ sự nhất quán ở producer giúp giảm cấu hình transform.

## 8. Transport và framing: không trộn các giao thức

Một collector có thể hỗ trợ nhiều input, nhưng **địa chỉ và cổng không quyết định toàn bộ protocol**.

| Đường gửi | Dạng dữ liệu/hợp đồng | Điều cần xác minh |
| --- | --- | --- |
| **stdout/stderr container** | Log từ file descriptor chuẩn; runtime có thể bọc metadata riêng | Agent có thu đúng stream không? Có wrapper hay split dòng không? |
| **File tail** | Text, JSON Lines hoặc định dạng khác trong file | File path, rotation, encoding, newline, checkpoint/offset |
| **TCP socket** | Byte stream, cần framing | Newline, length prefix hoặc protocol riêng; SSL/TLS tùy yêu cầu |
| **UDP** | Datagram, có thể mất/đảo thứ tự | Kích thước gói, format, collector có đang lắng nghe UDP không? |
| **Syslog** | Header, priority, timestamp và framing theo chuẩn/cách triển khai | RFC format, TCP/TLS framing, hostname, app-name |
| **GELF** | Định dạng sự kiện Graylog và cơ chế vận chuyển cụ thể | GELF JSON/binary, nén và framing đúng |
| **OTLP/gRPC** | Request protobuf qua gRPC | Endpoint, TLS, service/method, OTLP schema và auth |
| **OTLP/HTTP** | HTTP request với protobuf binary hoặc JSON-encoded protobuf | Content-Type, endpoint, path `/v1/logs`, auth, schema |

**Một dòng NDJSON gửi vào cổng OTLP/HTTP không trở thành OTLP chỉ vì nội dung là JSON.** OTLP/HTTP JSON có cấu trúc request theo protobuf schema; thường gửi bằng HTTP POST với những trường và envelope cụ thể. Socket TCP gửi `{"event":"..."}\n` cũng không tự tương thích với syslog hay GELF.

Nếu dùng Log4j2 SocketAppender, phải làm rõ ở collector: nó mong **TCP text lines**, **TLS**, **GELF** hay **syslog**? Nếu dùng File/Console Appender, collector cần parser/receiver tương ứng chứ không phải “mở cổng rồi tự hiểu”.

### Docker/container wrapper

Ứng dụng có thể in JSON Lines lên stdout:

```json
{"timestamp":"2026-11-09T12:00:00Z","event":"order_created"}
```

Nhưng trong một file log JSON của một số runtime, bản ghi còn được bao bởi metadata của runtime, có dạng minh họa:

```json
{"log":"{\"timestamp\":\"2026-11-09T12:00:00Z\",\"event\":\"order_created\"}\n","stream":"stdout","time":"2026-11-09T12:00:01Z"}
```

Ở đây **outer JSON** mô tả dòng log của container; trường `log` bên trong lại là một **chuỗi JSON** từ ứng dụng. Collector cần biết nó đang đọc outer wrapper hay dòng app gốc. Nếu chỉ parse outer object, `event` sẽ không tự trở thành trường gốc. Có thể cần lấy `log` rồi parse JSON thêm một lần, tùy driver và pipeline.

Tương tự với container runtime khác, bản ghi có thể có header/timestamp/partial marker riêng. Không giả định mọi runtime dùng đúng format minh họa ở trên.

## 9. Ví dụ Java 17+ độc lập: xuất JSON Lines ra stdout

Để thấy nguyên tắc với **JDK thuần**, ví dụ này dùng `java.util.logging.Logger` và `StreamHandler(System.out, Formatter)`. Nó phát hai LogRecord có timestamp cố định, sau đó Formatter đưa dữ liệu vào hai object JSON trên stdout.

**Điểm chính của demo:** minh họa một **hợp đồng JSON Lines tự định nghĩa**, bảo toàn kiểu `duration_ms` là số, giữ severity text của JUL và escape các ký tự gây hỏng JSON. Các timestamp cố định chỉ để có **stdout xác định** khi học; ứng dụng thực phải dùng thời gian sự kiện thật.

**Giới hạn:** formatter tự viết trong ví dụ phục vụ học tập và chỉ hỗ trợ một mẫu event với bốn vị trí tham số có kiểu đã biết. Trong production, hãy dùng **JSON encoder/structured logging API được bảo trì**, không biến đoạn minh họa thành thư viện serializer hay schema chung cho mọi loại event.

Lưu thành **`CollectorCompatibleDemo.java`**:

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class CollectorCompatibleDemo {
    private static final Logger LOG =
            Logger.getLogger(CollectorCompatibleDemo.class.getName());

    private CollectorCompatibleDemo() {
    }

    // Quote một chuỗi thành JSON string hợp lệ cho bản demo.
    private static String quote(String value) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) c));
                    } else if (Character.isHighSurrogate(c)) {
                        if (i + 1 < value.length()
                                && Character.isLowSurrogate(
                                        value.charAt(i + 1))) {
                            result.append(c).append(value.charAt(++i));
                        } else {
                            result.append("\\uFFFD");
                        }
                    } else if (Character.isLowSurrogate(c)) {
                        result.append("\\uFFFD");
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    private static final class JsonLineFormatter
            extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] args = record.getParameters();
            String event = (String) args[0];
            String orderId = (String) args[1];
            String outcome = (String) args[2];
            long durationMs = (Long) args[3];

            return "{"
                    + "\"timestamp\":"
                    + quote(record.getInstant().toString()) + ","
                    + "\"severity_text\":"
                    + quote(record.getLevel().getName()) + ","
                    + "\"service_name\":\"order-service\","
                    + "\"event\":" + quote(event) + ","
                    + "\"order_id\":" + quote(orderId) + ","
                    + "\"outcome\":" + quote(outcome) + ","
                    + "\"duration_ms\":" + durationMs + ","
                    + "\"message\":"
                    + quote(record.getMessage())
                    + "}\n";
        }
    }

    private static LogRecord record(
            String timestamp, Level level, String message,
            String event, String orderId, String outcome,
            long durationMs) {
        LogRecord r = new LogRecord(level, message);
        r.setInstant(Instant.parse(timestamp));
        r.setParameters(new Object[] {
                event, orderId, outcome, durationMs
        });
        return r;
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        StreamHandler stdout =
                new StreamHandler(System.out, new JsonLineFormatter());
        stdout.setEncoding("UTF-8");
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        try {
            LOG.log(record(
                    "2026-11-09T12:00:00Z",
                    Level.INFO,
                    "Order created",
                    "order_created", "ORD-101",
                    "SUCCESS", 25L));

            LOG.log(record(
                    "2026-11-09T12:00:01Z",
                    Level.WARNING,
                    "Payment retry scheduled",
                    "payment_retry_scheduled", "ORD-102",
                    "RETRY", 1500L));

            stdout.flush();
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
            // Không close: StreamHandler.close() sẽ đóng System.out.
        }
    }
}
```

Biên dịch/chạy chỉ với JDK 17+:

```bash
javac -encoding UTF-8 CollectorCompatibleDemo.java
java CollectorCompatibleDemo
```

**Stdout chính xác:**

```json
{"timestamp":"2026-11-09T12:00:00Z","severity_text":"INFO","service_name":"order-service","event":"order_created","order_id":"ORD-101","outcome":"SUCCESS","duration_ms":25,"message":"Order created"}
{"timestamp":"2026-11-09T12:00:01Z","severity_text":"WARNING","service_name":"order-service","event":"payment_retry_scheduled","order_id":"ORD-102","outcome":"RETRY","duration_ms":1500,"message":"Payment retry scheduled"}
```

**Stderr từ ứng dụng:** không có dòng nào khi chạy bình thường, không tính thông báo của JVM nếu môi trường lỗi.

### Vì sao output có thể dùng để kiểm tra collector?

- Mỗi `LogRecord` có **timestamp được đặt rõ** qua `setInstant` để ví dụ không lệ thuộc đồng hồ lúc chạy.
- `JsonLineFormatter` xuất đúng **một object mỗi dòng**, ký tự xuống dòng nằm sau dấu `}`.
- `duration_ms` được biểu diễn dưới dạng **JSON number**, không có dấu nháy kép.
- `severity_text` giữ nguyên `INFO` và `WARNING` của JUL; collector cần mapping nếu dashboard dùng tên `WARN`.
- `service_name`, `event`, `order_id`, `outcome` và `message` là những trường **ứng dụng định nghĩa**.
- Hàm `quote` escape dấu nháy kép, backslash, control characters và xử lý surrogate không ghép cặp bằng replacement character escape. Mẫu này giúp giải thích **vì sao phải dùng serializer đúng**.
- `StreamHandler(System.out, ...)` đi stdout. JUL `ConsoleHandler` mặc định đi **stderr**, nên không thay thế hai handler rồi kỳ vọng cùng kết quả.
- `LOG.setUseParentHandlers(false)` tránh một bản ghi JUL bị in thêm qua handler của logger cha.
- `stdout.flush()` giúp nhìn thấy bytes trước khi kết thúc; không chứng minh collector đã lưu bền.

**Giới hạn chuyên môn:** JSON Formatter này phụ thuộc vào thứ tự bốn tham số trong `LogRecord`. Nếu một loại event khác truyền số lượng/kiểu tham số không khớp, code có thể lỗi tại `format`. Vì vậy nó chỉ phù hợp với demo. Hệ thống thực nên dùng API hỗ trợ attributes/key-value và encoder JSON chuẩn, cộng với schema test.

## 10. Kiểm chứng đầu ra và parser trước khi tích hợp thật

Trên Linux/macOS, tách stdout và stderr:

```bash
javac -encoding UTF-8 CollectorCompatibleDemo.java
java CollectorCompatibleDemo > events.ndjson 2> errors.txt
```

Với ví dụ, `events.ndjson` có hai dòng JSON đầy đủ, còn `errors.txt` rỗng khi không có lỗi.

Nếu có Python 3, có thể chạy kiểm thử JSON parser độc lập:

```bash
python3 -c 'import json,sys; rows=[json.loads(s) for s in sys.stdin if s.strip()]; assert len(rows)==2; assert all(isinstance(r["duration_ms"],int) for r in rows); print("parsed="+str(len(rows)))' < events.ndjson
```

**Stdout của lệnh Python khi dữ liệu đúng:**

```text
parsed=2
```

Đây là **kiểm tra syntax và một phần type**, không phải bằng chứng collector thật đã ingest thành công. Nếu muốn thử chính xác đường thu thập, cần chạy receiver/input có cấu hình tương ứng.

Các bước kiểm tra kết nối collector:

1. Gửi hai bản ghi demo vào **đúng nguồn** collector đang đọc, không phải một file/stream khác.
2. Xác nhận **số event input** collector thấy là 2, không phải 0, 1 hoặc nhiều hơn vì retry/duplicate.
3. Kiểm tra mỗi event có trường `event`, `order_id` và `duration_ms` với **đúng type**.
4. Xác nhận `timestamp` được parse thành **event time**, không chỉ lưu thành chuỗi trong body.
5. Xác nhận `severity_text` được nhận hoặc normalized đúng.
6. Xác nhận tên `service_name` được gắn đúng nguồn, không bị một processor ghi đè sai.
7. Truy vấn theo một trường, chẳng hạn `event=order_created` hoặc `order_id=ORD-101`.
8. Thử input chứa dấu tiếng Việt, dấu nháy kép, xuống dòng và thông điệp exception.
9. Quan sát parser errors, records dropped, retries và queue/flush behavior trong collector.
10. Thử collector restart và ứng dụng restart để hiểu giới hạn mất/trùng log.

## 11. Dùng Log4j2 JsonTemplateLayout với một collector đọc stdout

Với ứng dụng Log4j2, không cần tự viết `JsonLineFormatter` như demo. **JsonTemplateLayout** của Apache Log4j 2 có thể serialize LogEvent theo một JSON event template. Nó cần artifact riêng `log4j-layout-template-json` bên cạnh `log4j-api`/`log4j-core` với phiên bản tương thích.

Ví dụ phụ thuộc Maven (cố định **2.26.1** để minh họa, không coi là phiên bản mới nhất bắt buộc):

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-api</artifactId>
        <version>2.26.1</version>
    </dependency>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-core</artifactId>
        <version>2.26.1</version>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-layout-template-json</artifactId>
        <version>2.26.1</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây là **khối dependencies minh họa**, không phải POM hoàn chỉnh; phải đặt trong `<project>` cùng cấu hình Maven/JDK của ứng dụng.

File `src/main/resources/log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="JSON_STDOUT" target="SYSTEM_OUT">
            <JsonTemplateLayout
                eventTemplateUri="classpath:EcsLayout.json"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="JSON_STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

**Rất quan trọng:** `EcsLayout.json` là template định hướng **Elastic Common Schema (ECS)** của Log4j2. Nó **không phát ra đúng schema tự đặt** ở ví dụ `CollectorCompatibleDemo`. Đừng đổi từ JUL demo sang Log4j2 rồi khẳng định output vẫn có field `severity_text`, `service_name` hoặc `duration_ms` với cùng tên.

Với ECS, những trường như `@timestamp`, `message`, `log.level`, `service.name` và `ecs.version` có ý nghĩa được quy định riêng. Muốn dùng một schema nội bộ, cần **template JSON tùy biến** hoặc transform ở collector, đồng thời kiểm tra các resolver và đầu ra thực tế.

Ví dụ Java Log4j2 **trong một lớp đã có dependency**, không độc lập:

```java
private static final org.apache.logging.log4j.Logger LOG =
        org.apache.logging.log4j.LogManager.getLogger(OrderService.class);

LOG.info("event=order_created order_id={}", orderId);
```

Lời gọi `LOG.info` ở trên chỉ phát **message có tham số**. Nó không tự tách chuỗi `order_id=ORD-101` thành một thuộc tính JSON đúng tên `order_id`. Nếu collector yêu cầu field riêng, phải sử dụng dữ liệu có cấu trúc của LogEvent, context hoặc schema transformation được cấu hình tương ứng.

## 12. SLF4J và Logback: facade không quyết định schema

Nhiều ứng dụng Java dùng `org.slf4j.Logger`:

```java
LOG.info("event=order_created order_id={}", orderId);
```

Điều này quyết định **lời gọi API logging**, không xác định format cuối là text hay JSON. Backend/provider quyết định encoder, appender, MDC, cách xuất Throwable và metadata.

Với **SLF4J 2.x**, fluent API có thể gắn key-value:

```java
LOG.atInfo()
        .addKeyValue("event", "order_created")
        .addKeyValue("order_id", orderId)
        .addKeyValue("duration_ms", durationMs)
        .log("Order created");
```

Đây là snippet trong lớp đã có `LOG` và biến phù hợp, **không phải chương trình chạy độc lập**. Các cặp key-value được đưa vào sự kiện logging. **Có được xuất ra dưới dạng trường JSON hay không** còn phụ thuộc backend/encoder và pipeline. Đừng giả định một `ConsoleAppender` text sẽ tự hiểu `addKeyValue` thành JSON đầy đủ.

Logback có các encoder/layout và hệ sinh thái encoder JSON riêng. Muốn tương thích collector, cần chọn một encoder phù hợp với **phiên bản Logback/SLF4J** và kiểm chứng kết quả thật của nó. Không sao chép XML `log4j2.xml` vào `logback.xml`: tên plugin/cú pháp khác nhau.

Với JUL, `ConsoleHandler` mặc định gửi log tới stderr cùng Formatter mặc định; nếu collector chỉ thu stdout hoặc mong JSON, cần thay handler/formatter hoặc để agent parse định dạng đã được thống nhất. Hai ứng dụng cùng gọi `Logger.info` nhưng dùng backend khác nhau có thể tạo dữ liệu rất khác nhau.

## 13. Elastic ECS, OpenTelemetry và Loki không phải một schema

Một số hệ thống phổ biến có **mô hình dữ liệu riêng**:

| Hệ sinh thái | Các khái niệm/field thường gặp | Lưu ý tương thích |
| --- | --- | --- |
| **Elastic Common Schema (ECS)** | `@timestamp`, `message`, `log.level`, `service.name`, `ecs.version` | Mapping field và type theo ECS; đừng giả định `timestamp` tương đương `@timestamp` trong mọi pipeline |
| **OpenTelemetry log data model** | `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, trace/span IDs | Là mô hình typed; nếu nhận JSON Lines từ file/stdout, collector phải parse và map sang các field LogRecord tương ứng |
| **Grafana Loki** | Labels, log line, và có thể có structured metadata | Labels tạo streams; không đặt những ID có cardinality rất cao vào nhãn index |
| **Fluent Bit** | Input, parser, filter, output | Cấu hình nguồn/format/parser; có thể parse JSON Lines hoặc gộp multiline theo chế độ đã đặt |
| **Collector tùy biến** | Schema do tổ chức quy định | Cần tài liệu contract và kiểm thử giữa producer/collector |

### Chọn định dạng theo nơi tiêu thụ

Nếu hệ thống đích dùng ECS, có thể xuất JSON theo ECS ngay tại Log4j2, hoặc transform ở collector. Nếu pipeline chuẩn hóa sang OpenTelemetry, có thể parse `timestamp`/`severity_text`/`service_name` từ JSON và map sang `Timestamp`, `SeverityText` và resource attributes. Nếu chọn **OTLP exporter**, phải gửi đúng **giao thức OTLP**, chứ không gửi tùy tiện JSON text.

Một ứng dụng không nhất thiết phát **ba định dạng đồng thời** cho ECS, OTel và Loki. Cách thường dễ bảo trì hơn là có một **hợp đồng ứng dụng ổn định**, rồi đặt trách nhiệm transform ở một hoặc một số điểm được quản lý rõ. Cần xác định chủ sở hữu các mapping ấy, vì chúng cũng là code/config quan trọng.

### Cardinality ở Loki

Trong Loki, **mỗi tổ hợp label** có thể tạo ra một stream. Các giá trị biến thiên liên tục như `request_id`, `trace_id`, `order_id` hoặc `user_id` thường **không nên là indexed labels** vì tạo rất nhiều streams và tăng chi phí. Những giá trị này có thể nằm trong log line hoặc **structured metadata** tùy kiến trúc.

Ngược lại, các field như `service`, `environment`, `cluster` hoặc `namespace` thường có cardinality thấp hơn, phù hợp hơn để phân loại luồng. Quy tắc chính xác phụ thuộc phiên bản/triển khai và cách tổ chức tra cứu.

**Tương thích parser không đồng nghĩa tương thích mô hình lưu trữ:** JSON hợp lệ nhưng dùng label sai có thể khiến hệ thống vẫn ingest được mà hiệu năng và chi phí xấu đi nhanh chóng.

## 14. Ví dụ mapping giữa schema ứng dụng và collector

Giả sử ứng dụng phát:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "severity_text": "WARNING",
  "service_name": "order-service",
  "event": "payment_retry_scheduled",
  "order_id": "ORD-102",
  "duration_ms": 1500,
  "message": "Payment retry scheduled"
}
```

Đây là **một object JSON trình bày nhiều dòng để minh họa**, không phải định dạng NDJSON của file thật.

Một bảng mapping có thể được thỏa thuận:

| Schema ứng dụng | Ý nghĩa | Mapping đích ví dụ |
| --- | --- | --- |
| `timestamp` | Thời điểm tạo LogEvent | OTel `Timestamp` hoặc ECS `@timestamp` |
| `severity_text` | Chuỗi mức JUL gốc | OTel `SeverityText`; map `WARNING` sang nhóm WARN khi cần |
| `service_name` | Nguồn dịch vụ | OTel `Resource` attribute `service.name` hoặc ECS `service.name` |
| `event` | Tên loại sự kiện | Attribute/event classification theo contract |
| `order_id` | Định danh nghiệp vụ | Attribute; không tự biến thành label cardinality cao |
| `duration_ms` | Mili giây dạng số | Attribute số; giữ nguyên đơn vị hoặc chuyển có ghi rõ |
| `message` | Mô tả cho người đọc | OTel `Body` hoặc ECS `message` |

Bảng này là **kế hoạch chuyển đổi**, không khẳng định một collector bất kỳ tự làm đúng từng mapping. Ví dụ, tên trường `service_name` không được mặc định coi là `service.name` ở mọi pipeline. Phải cấu hình processor/transform hoặc encoder thích hợp.

**Không đánh tráo `event time` với `ingest time`** chỉ để có một trường không rỗng. Nếu không parse được timestamp, hãy theo chính sách rõ ràng: báo dữ liệu lỗi, gán thời gian nhận có đánh dấu, hoặc đưa bản ghi vào đường xử lý lỗi. Không âm thầm làm sai phép tính độ trễ.

## 15. Contract testing: kiểm chứng producer và collector cùng nhau

Một **contract test** có thể phát một bộ dữ liệu có chủ đích từ ứng dụng thử nghiệm, cho collector parse rồi kiểm tra đúng số bản ghi, field, type, thời gian và kết quả truy vấn.

Bộ test nên có những tình huống:

| Ca thử | Dữ liệu | Kết quả cần kiểm tra |
| --- | --- | --- |
| Event đơn giản | `order_created` với `order_id` | Một event, field nguyên vẹn |
| Hai event liên tiếp | Hai dòng NDJSON | Không gộp thành một hoặc chia thành nhiều |
| Dấu tiếng Việt | `message="Đã tạo đơn hàng"` | UTF-8 không bị lỗi |
| Quote/backslash | Chuỗi chứa `"` và `\` | JSON vẫn parse được |
| Xuống dòng trong message | `\n` là nội dung chuỗi JSON | Không tạo event thứ ba |
| Severity của JUL | `WARNING` | Được giữ/mapping đúng thành WARN ở nơi cần |
| Timestamp UTC | `2026-11-09T12:00:00Z` | Event time đúng, không bị cộng thêm 7 giờ |
| Type numeric | `duration_ms=1500` | Được lưu như số, không phải chuỗi |
| Field thiếu | Không có `order_id` với event không cần ID | Theo chính sách optional, không suy diễn lỗi |
| Exception | Throwable có cause | Có thể điều tra, không vỡ multiline framing |
| Dữ liệu quá dài | Message gần giới hạn collector | Drop/truncate có tín hiệu và chính sách |
| Collector restart | Gửi log khi collector gián đoạn | Biết giới hạn mất/trùng và trạng thái queue |
| Thay schema | Producer cũ/mới tồn tại song song | Collector chấp nhận/mapping theo kế hoạch chuyển tiếp |

**Đếm số sự kiện đầu-cuối** nên phân biệt:

- Ứng dụng **cố phát** bao nhiêu sự kiện.
- Handler/appender **đã nhận** bao nhiêu sự kiện sau level/filter.
- Collector **đã đọc** bao nhiêu.
- Parser **giải mã thành công** bao nhiêu.
- Exporter **gửi thành công** bao nhiêu.
- Backend **ingest/index** bao nhiêu.
- Query thực sự **trả về** bao nhiêu trong khoảng thời gian và điều kiện lọc.

Các con số này có thể khác nhau hợp lệ do filtering/sampling. Nhưng nếu có sự chênh bất thường, phải biết xảy ra ở chặng nào thay vì kết luận chỉ từ việc `LOG.info` không ném exception.

### Kiểm chứng không trùng

Đôi khi một event đi qua **hai đường**: Java vừa in stdout, vừa ghi file; collector lại thu cả stdout và file. Khi đó dashboard có thể có hai bản sao. Một nguồn trùng khác là retry exporter hoặc hệ thống downstream có cơ chế giao nhận ít nhất một lần.

Khi cần phân biệt sự kiện và lần gửi, cân nhắc `event_id` ổn định/idempotency key cho những sự kiện quan trọng. Nhưng **log thông thường không tự có exactly-once** chỉ nhờ thêm event ID; backend cần chiến lược xử lý trùng phù hợp.

## 16. Đổi schema mà không làm hỏng collector

Schema log thường trở thành **hợp đồng vận hành**, dù lúc đầu chỉ là một formatter nhỏ trong Java.

Ví dụ thay đổi gây ảnh hưởng:

- `timestamp` chuyển từ RFC 3339 string sang epoch milliseconds nhưng tên không đổi.
- `duration_ms` chuyển từ number sang string hoặc thành `duration_s` mà quên đổi tên.
- `service_name` đổi thành `service`, trong khi collector vẫn đọc tên cũ.
- `event=payment_failed` đổi thành `event=payment_declined` mà không phân biệt ngữ nghĩa.
- `severity_text=WARNING` đổi sang `WARN` khiến bộ lọc cũ không khớp.
- `trace_id` được chuyển vào nested object mới nhưng query vẫn tìm ở root.
- Một field trước là object sau thành string, gây mapping conflict ở storage.

Cách triển khai thay đổi an toàn:

1. **Xác định người tiêu thụ:** dashboard, alert, saved query, parser, pipeline, ETL, ứng dụng downstream.
2. **Định nghĩa contract mới:** tên, type, required/optional, enum, đơn vị, timestamp, privacy và cách migration.
3. **Thêm khả năng đọc song song tạm thời** nếu cần: collector nhận được cả schema cũ/mới hoặc mapping cả hai về field chuẩn.
4. **Triển khai và so sánh số liệu** trước khi xóa parser cũ.
5. **Sử dụng schema version khi cần** thay đổi không tương thích và nhiều phiên bản cùng tồn tại; không cần tăng version chỉ vì sửa câu hiển thị không có ai phụ thuộc.
6. **Đặt test fixtures** cho các event trọng yếu để pipeline CI phát hiện đổi tên/kiểu vô tình.
7. **Ghi rõ thời điểm kết thúc hỗ trợ** schema cũ nếu có.
8. **Theo dõi lỗi parse sau triển khai**, vì ứng dụng có thể vẫn trả HTTP 200 dù log collector đã mất field quan trọng.

Không có quy tắc “mọi field mới đều tương thích ngược”. Thêm trường thường dễ chấp nhận với parser linh hoạt, nhưng một số bộ parser sử dụng regex/định vị chuỗi hoặc schema strict có thể thất bại. Cần kiểm tra **bộ tiêu thụ thực tế**.

## 17. Log an toàn: dữ liệu nhạy cảm, escaping và giới hạn nguồn

Tương thích kỹ thuật không phải giấy phép ghi mọi dữ liệu vào collector. Khi log đi tập trung, nó có thể được lưu lâu, truy cập từ nhiều nhóm và truyền qua nhiều hạ tầng.

Checklist:

- **Không ghi** password, refresh/access token, API key, OTP, số thẻ đầy đủ, session cookie hoặc toàn bộ payload nhạy cảm.
- **Giới hạn trường cần thiết:** `order_id` nội bộ có thể đủ để tìm lỗi, không cần họ tên/địa chỉ khách hàng.
- **Escape đúng:** JSON encoder phải xử lý dấu nháy, backslash, ký tự điều khiển và Unicode; message chứa newline không được tạo event giả.
- **Hạn chế kích thước:** collector, container runtime và backend có thể cắt hoặc từ chối bản ghi quá lớn.
- **Giới hạn cardinality:** không tạo một tên trường hoặc nhãn index khác cho mỗi user/request.
- **Phân quyền:** xem ai đọc log và trường nào đi qua hệ thống trung gian.
- **Transport security:** nếu đẩy log trực tiếp qua mạng, dùng TLS/xác thực phù hợp và bảo vệ thông tin truy cập.
- **Retention/xóa:** schema có thể đúng nhưng chính sách giữ dữ liệu vẫn không phù hợp với yêu cầu pháp lý/nội bộ.
- **Ngăn log injection:** đặc biệt với text log, newline và control characters có thể giả mạo sự kiện; với JSON dùng serializer đúng ngữ cảnh.
- **Không tin vào `e.getMessage()` như dữ liệu sạch:** exception của driver/client có thể mang đường dẫn, URL có secret hoặc dữ liệu đầu vào không đáng ghi.

Trong một số dự án, collector có processor **redaction**; đó là lớp bổ sung hữu ích nhưng không thay thế việc ngăn ứng dụng gửi secret ngay từ nguồn. Khi dữ liệu đã ra stdout/file, những thành phần nằm trước redaction cũng có thể đã nhìn thấy nó.

## 18. Độ tin cậy và theo dõi lỗi của pipeline

Một collector không chỉ parse. Nó còn có thể buffer, batch, retry, nhận dạng nguồn, thêm metadata, lọc và export. Mỗi điểm đều có những khả năng lỗi:

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| Không có log ở collector | Sai input/source; level bị tắt; stdout/stderr nhầm; path/port sai |
| Bytes có nhưng không có events | Framing/parsing sai; JSON invalid; character encoding lỗi |
| Có event nhưng thiếu field | Parser chỉ giữ raw `message`; nested wrapper chưa parse; transform làm rơi field |
| Event nằm sai giờ | Timestamp chưa parse; sai timezone/epoch units; clock skew |
| Tìm WARN không thấy JUL WARNING | Mapping severity chưa được chuẩn hóa |
| Hai event thành nhiều dòng | Pretty JSON, stack trace multiline hoặc runtime split/truncate |
| Một event xuất hiện hai lần | Hai appender/agent nguồn; retries; additivity |
| Event “biến mất” khi tải cao | Queue đầy, sampling, rate limit, backpressure, drop ở collector/exporter |
| JSON parse đúng nhưng backend từ chối | Schema mapping conflict, invalid index, quyền, hạn mức |
| Truy vấn quá chậm/tốn | Index label cardinality cao, nhiều field không cần thiết |
| Java request chậm vì log | I/O console/socket, formatter nặng, queue đầy hoặc mạng nghẽn |
| Trace ID không link được | Sai format, không truyền context qua async hoặc field mapping chưa đúng |
| Collector restart gây gap | Buffer không bền, file checkpoint, lifecycle hoặc cơ chế retry |
| Security alert từ log | Secret bị ghi, thông tin nhạy cảm trong exception/metadata |

Chính sách độ tin cậy phụ thuộc nhu cầu: log chẩn đoán thông thường thường chấp nhận một mức mất khi sự cố; dữ liệu kiểm toán hoặc trạng thái tài chính cần **cơ chế lưu trữ đáng tin cậy chuyên biệt**. Không xem một câu `LOG.info("payment completed")` là bằng chứng đã commit giao dịch.

**Không đặt mọi log trên một kênh duy nhất nhưng yêu cầu vừa không gây độ trễ vừa không mất bản ghi trong mọi trường hợp.** Có những đánh đổi giữa latency, throughput, durability, chi phí và tính sẵn sàng. Cần thiết kế theo mục tiêu vận hành thực tế, không tuyên bố bảo đảm cao hơn khả năng của appender/collector.

## 19. Một quy trình triển khai “tương thích collector” từ đầu

Giả sử một dịch vụ Java sắp đưa structured logs lên môi trường production. Quy trình đề xuất:

### Bước 1 — Chốt đầu nhận và đường dữ liệu

Xác định collector cụ thể, receiver/input nào, nó nhận stdout, file, OTLP hay network protocol, cách authentication/TLS và nơi xuất dữ liệu cuối cùng. Nếu nền tảng Kubernetes đã tự thu stdout, bắt đầu bằng **một đường rõ ràng**, tránh đồng thời gửi trực tiếp qua network và qua agent khi không có lý do.

### Bước 2 — Chọn schema

Chọn ECS, mô hình OpenTelemetry hoặc schema ứng dụng riêng với mapping được ghi tài liệu. Quy định field name, types, timestamp, severity, required/optional, mã sự kiện và trường chẩn đoán.

### Bước 3 — Chọn encoder

Với Log4j2 có thể dùng `JsonTemplateLayout`; với Logback chọn encoder JSON phù hợp; với JUL cần handler/formatter/adapter tương ứng. Tránh tự ghép JSON ở production. Kiểm tra config thực phát **một record một dòng** nếu collector dùng line framing.

### Bước 4 — Chọn timestamp và context

Ưu tiên event time có timezone tường minh. Gắn `service.name`, environment, instance nếu pipeline yêu cầu. Thêm `trace_id`/`correlation_id` đúng vòng đời; dọn ThreadContext/MDC sau request và truyền context qua async khi cần.

### Bước 5 — Chạy canary contract test

Phát một số event đã biết: INFO, WARNING/ERROR, message tiếng Việt, Unicode, exception, number, field thiếu và timestamp cũ. Đọc lại tại **đích cuối** để đối chiếu nội dung và kiểu dữ liệu.

### Bước 6 — Kiểm tra lỗi đường thu

Thử collector ngừng, backend từ chối, mạng chậm, queue đầy, file rotate và service restart. Đo event count, parse failures, dropped records, retry và thời gian trễ.

### Bước 7 — Định nghĩa dashboard/alert đúng field

Truy vấn bằng `event`, `severity`, `service`/`resource` và các field ổn định. Không dựa hoàn toàn vào câu message tự do. Với Loki, giữ index labels có cardinality hợp lý.

### Bước 8 — Đóng gói contract vào CI

Lưu các **sample NDJSON/OTLP payload** không chứa dữ liệu thật; kiểm thử schema, tên trường, type và serializer sau mỗi lần thay đổi phiên bản logging library. Theo dõi lỗi ingestion sau deploy, không coi “test pass” là bằng chứng pipeline production luôn khỏe.

## 20. Những hiểu nhầm phổ biến

**1. “Đã in JSON lên console là collector tự parse.”** Không. Collector có thể chỉ giữ raw line. Cần bật parser hoặc đầu vào đã typed.

**2. “JSON một object nhiều dòng vẫn tương thích parser một dòng.”** Không. Cần một JSON object trên một dòng hoặc multiline framing có cấu hình.

**3. “String và number trong JSON được collector hiểu như nhau.”** Không. Type ảnh hưởng phép tổng hợp, index và query.

**4. “Tên field timestamp nào cũng dùng được.”** Không. ECS, OTel và pipeline nội bộ có quy ước riêng; cần mapping.

**5. “JUL WARNING mặc nhiên thành WARN của dashboard.”** Không. Cần severity mapping nếu hệ thống đích dùng tên/number khác.

**6. “Thêm `trace_id` vào text message đủ để trace tương quan.”** Chưa chắc. Phải giữ/trích xuất thành trường mà công cụ truy vấn/correlation hiểu.

**7. “Gửi JSON Lines vào OTLP port là được.”** Sai. OTLP có envelope, schema và giao thức HTTP/gRPC riêng.

**8. “Docker logs luôn chính là nội dung JSON của ứng dụng.”** Một số runtime lưu outer wrapper; collector phải hiểu định dạng ở nguồn thu thật.

**9. “Mọi field đều nên thành label Loki.”** Không. High-cardinality values như `order_id`/`trace_id` thường gây số stream rất lớn.

**10. “Một lần log thành công là collector đã lưu bền.”** Không. Cần xem queue, transport, collector và backend; mỗi điểm có giới hạn riêng.

**11. “Có hai bản ghi nghĩa là nghiệp vụ chạy hai lần.”** Không nhất thiết. Có thể collector thu hai đường hoặc retry/export lặp.

**12. “Chỉ cần sửa formatter khi schema thay đổi.”** Parser, dashboard, alert và bộ tiêu thụ khác cũng cần được nâng cấp có kế hoạch.

**13. “Logger dùng key-value bảo đảm encoder JSON giữ đủ các key.”** Không. Provider/encoder/template quyết định trường nào được xuất.

**14. “Trường log có thể chứa bí mật vì collector sẽ che sau.”** Không an toàn: dữ liệu đã đi qua ít nhất một số lớp trước khi redaction.

**15. “Có thể dùng log để tính giao dịch chính thức.”** Chỉ khi có hệ thống audit hoặc event store được thiết kế với bảo đảm tương ứng; log quan sát thông thường có thể bị mất/lặp/lọc.

## 21. Câu hỏi tự kiểm tra

1. **Tương thích collector gồm những lớp nào?** Nguồn/transport, framing, encoding/format, schema, timestamp, severity, parser/exporter và vận hành.
2. **NDJSON là gì?** Nhiều JSON object độc lập, mỗi object một dòng; không phải một JSON array.
3. **Vì sao pretty JSON có thể bị collector đọc sai?** Mỗi dòng không phải một event JSON hoàn chỉnh nếu parser dùng line framing.
4. **`"duration_ms":"1500"` và `"duration_ms":1500` có khác nhau không?** Có; string và number là hai kiểu JSON khác nhau.
5. **Timestamp `2026-11-09T12:00:00Z` chỉ giờ ở đâu?** UTC; nếu muốn dùng giờ địa phương phải biểu diễn offset đúng.
6. **OTel phân biệt Timestamp và ObservedTimestamp để làm gì?** Một trường là lúc sự kiện phát sinh, một trường là lúc được quan sát.
7. **JUL `WARNING` có chắc được backend lọc bằng `WARN` không?** Không, cần mapping theo contract.
8. **OTLP/HTTP có nhận một dòng JSON tùy ý không?** Không. Nó cần payload theo OTLP schema và HTTP endpoint/headers phù hợp.
9. **Muốn JSON có trường `order_id` từ Log4j2 phải làm gì?** Chọn template/encoder/attributes hoặc transform collector phù hợp; message `"order_id=..."` không tự thành field.
10. **Loki có nên dùng mỗi `request_id` làm label không?** Thường không vì cardinality cao; dùng log body/structured metadata thích hợp.
11. **Vì sao cần kiểm thử collector thật dù ví dụ Java đã in hai dòng JSON hợp lệ?** Đích nhận có thể sai parser, timestamp, mapping, backend hoặc mất/trùng sự kiện.
12. **Nếu collector báo ingest thành công nhưng log không xuất hiện trong 15 phút gần đây, cần kiểm tra gì?** Event time, timezone, ingest time, lọc query, retention và delay.
13. **Có nên đưa stack trace nhiều dòng thô vào file NDJSON không?** Không nếu collector yêu cầu một dòng một event; dùng JSON escaping/field riêng hoặc multiline parser.
14. **Khi log có cả stdout và file, có thể xảy ra gì?** Hai collector input có thể thu một sự kiện hai lần.
15. **Schema version có thay thế test không?** Không. Nó hỗ trợ migration; vẫn cần kiểm thử mapping và bộ tiêu thụ.
16. **Log collector có tự bảo đảm exactly-once không?** Không thể suy ra; cần xem thiết kế ack/retry/dedup và độ bền của từng chặng.
17. **Vì sao không nên ghi mật khẩu để collector redaction sau?** Dữ liệu đã rời ứng dụng và có thể bị lộ ở những lớp trước redaction.
18. **Một log có `"event":"payment_completed"` chứng minh thanh toán đã commit chưa?** Không. Nguồn trạng thái nghiệp vụ chính thức mới quyết định.
19. **Bộ test đầu-cuối tối thiểu cần xác nhận gì?** Số event, parser pass, field/types, timestamp, severity, query và lỗi drop/duplicate.
20. **Khi chuyển backend logging, có thể giữ nguyên code `LOG.info` mà vẫn mất tính tương thích không?** Có. Layout/encoder, schema, provider và dữ liệu context có thể khác.

## 22. Tài liệu tham khảo

Các tài liệu chính thức hữu ích để kiểm tra cấu hình của từng phiên bản:

- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry Protocol (OTLP): https://opentelemetry.io/docs/specs/otlp/
- OpenTelemetry Collector filelog receiver (contrib): https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver
- Fluent Bit, JSON parser: https://docs.fluentbit.io/manual/data-pipeline/parsers/json
- Fluent Bit, multiline parsing: https://docs.fluentbit.io/manual/data-pipeline/parsers/multiline-parsing
- Elastic Common Schema, base fields và `@timestamp`: https://www.elastic.co/docs/reference/ecs/ecs-base
- Grafana Loki, labels và cardinality: https://grafana.com/docs/loki/latest/get-started/labels/
- Apache Log4j 2, JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- Oracle Java 17, JUL StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html

**Ghi nhớ:** structured logging chỉ thực sự có ích khi **producer, collector và storage cùng hiểu một hợp đồng**. Đối với log Java, kiểm tra từ **nguồn → framing → JSON/schema → timestamp/severity → attributes → exporter → query**, không chỉ việc console hiển thị một chuỗi JSON. Dùng một encoder có cấu trúc được kiểm thử, giữ tên và kiểu trường ổn định, quản lý bảo mật/cardinality và đo được sự kiện bị mất, trùng hoặc lỗi parse trong pipeline.
