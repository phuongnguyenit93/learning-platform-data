# Chọn format cho Java Logging: text, key-value, JSON Lines và telemetry có cấu trúc

## 1. “Chọn format” trong chiến lược logging nghĩa là gì?

Khi thiết kế chiến lược log cho một ứng dụng Java, **format** là cách một **log event** được biểu diễn để con người hoặc hệ thống khác có thể đọc, lưu và phân tích. Format có thể là một dòng text dễ nhìn, các cặp key-value, một JSON object trên mỗi dòng, một bản tin syslog, hoặc một cấu trúc telemetry được truyền bằng giao thức như OTLP.

Ví dụ cùng một nghiệp vụ tạo đơn hàng thành công:

```text
2026-11-10T02:00:00Z INFO orders - Created order ord-42 in 27 ms
```

```text
ts=2026-11-10T02:00:00Z level=INFO event=order.create.result orderId=ord-42 outcome=SUCCEEDED durationMs=27
```

```json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27}
```

Ba cách ghi **có thể nói về cùng một event**, nhưng khác về độ dễ đọc, khả năng parse, quản lý schema, kiểu dữ liệu, kích thước và tính tương thích của logging pipeline.

**Không có “format tốt nhất” cho mọi hệ thống.** Một ứng dụng CLI chạy một lần có thể ưu tiên text đơn giản. Một hệ thống Java nhiều service đưa log vào một nơi truy vấn tập trung thường hưởng lợi từ **structured JSON Lines** hoặc một mô hình log record có cấu trúc chuẩn hóa. Nếu đã sử dụng OpenTelemetry, có thể chọn truyền records qua OTLP; tuy nhiên phải phân biệt **record data model, wire protocol và file output**.

Chọn format đúng phải dựa trên **mục đích quan sát, các trường cần tìm kiếm, tính nhất quán, công cụ nhận log, rủi ro bảo mật, thông lượng và chi phí vận hành**.

## 2. Phân biệt event, message, field, formatter, encoder và transport

Những khái niệm này dễ bị trộn lẫn:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Log event / LogRecord** | Một sự kiện: timestamp, severity, message, Throwable, context, các thuộc tính |
| **Message/template** | Lời mô tả như `Order creation finished` hoặc `orderId={}` |
| **Structured fields** | Các trường có tên và kiểu: `event`, `orderId`, `durationMs`, `outcome` |
| **Formatter / layout / encoder** | Chuyển record thành text, JSON hoặc bytes theo định dạng |
| **Appender / handler** | Chuyển dữ liệu tới console, file, socket, queue hoặc sink |
| **Framing** | Cách biết ranh giới giữa hai event: newline, length prefix, protocol message |
| **Transport** | Cách truyền: stdout, file tail, HTTP, gRPC, TCP, UDP... |
| **Schema** | Quy ước tên trường, kiểu dữ liệu, ý nghĩa, version và các field bắt buộc |
| **Collector** | Nhận, parse, enrich, filter, buffer và chuyển log tới storage |

Một event có cấu trúc **không tự động trở thành structured JSON** khi dùng `log.info("orderId={}", id)`. Nếu backend chỉ đưa tất cả vào một trường `message`, hệ đích vẫn nhìn thấy text, không nhất thiết có trường JSON độc lập `orderId`.

Ngược lại, một JSON object có thể chứa **chỉ một trường message text**. Nó là JSON hợp lệ nhưng vẫn thiếu cấu trúc cần cho phân tích nếu không có action, target, outcome hay correlation ID.

**Format và độ tin cậy delivery là hai chuyện khác nhau:** JSON Lines không làm một event được ghi bền vững hơn text. Async queue, rotation, flush, retry, collector và remote acknowledgment quyết định những phần khác của pipeline.

## 3. Ma trận so sánh các lựa chọn format

| Format | Dễ đọc trực tiếp | Máy parse/truy vấn | Nhược điểm và lưu ý | Dùng khi |
| --- | --- | --- | --- | --- |
| **Plain text / pattern** | Cao | Trung bình đến thấp nếu thiếu field chuẩn | Phụ thuộc regex, multiline exception, khó truy vấn riêng field | CLI, debug, service nhỏ hoặc local console |
| **Key=value** | Khá cao | Tốt nếu escaping và schema nhất quán | Dấu cách, quote, newline, dấu `=` gây mơ hồ nếu parser tự chế | Hệ thống cần compact, dễ grep, ingest qua parser thống nhất |
| **JSON Lines / JSONL** | Trung bình | Cao với JSON parser và fields ổn định | Overhead field names, serializer/escaping, nested schema, size | Microservices, centralized logging, dashboard |
| **Syslog (ví dụ RFC 5424)** | Phụ thuộc renderer | Tốt khi receiver hỗ trợ chuẩn | PRI/severity, metadata, encoding, framing/transport phải đúng | Tích hợp hệ thống syslog/SIEM có sẵn |
| **CEF/LEEF hoặc format SIEM chuyên dụng** | Có cấu trúc theo vendor/tool | Cao trong hệ đích tương thích | Mapping field, escaping và semantics phụ thuộc hệ đích | Khi SIEM yêu cầu định dạng này |
| **OTLP log records** | Không nhất thiết là text file | Có typed attributes, timestamps, severity/trace | Cần SDK/collector, giao thức và semantic conventions phù hợp | Hệ thống theo OpenTelemetry |

**OTLP không đơn thuần là “JSONL có tên khác”.** OpenTelemetry định nghĩa một mô hình log record và giao thức truyền; payload có thể được encode theo protobuf qua gRPC/HTTP hay các cách được spec hỗ trợ. Việc xuất OTLP và việc in JSONL ra file là **hai bước triển khai khác nhau**. Tên trường trong một JSON log tùy chỉnh cũng không tự được ánh xạ hoàn hảo sang semantic conventions của OpenTelemetry.

Với text, “parse được bằng regex” **không đồng nghĩa schema ổn định**: nếu nội dung message đổi, dấu cách khác, một trường tùy chọn bị thiếu hoặc có newline không escape, parser có thể sai.

## 4. Câu hỏi cần trả lời trước khi chọn

Trước khi quyết định, hãy trả lời:

1. **Ai đọc?** Kỹ sư xem console, support đọc log file, SRE query ở log search hay SIEM/collector máy tự phân tích?
2. **Khối lượng?** Vài trăm event/ngày hay hàng trăm nghìn event/giây? Độ lớn trung bình và tail latency bao nhiêu?
3. **Cần query gì?** Lọc theo `event`, `status`, `errorCode`, `requestId`, `traceId`, `durationMs` hay chỉ grep message?
4. **Có nhiều service không?** Nếu có, cần schema chung và mapping severity/time/trace IDs.
5. **Thành phần nào nhận log?** Console, sidecar, Fluent Bit/Vector/OTel Collector, syslog receiver, log gateway?
6. **Exception phức tạp?** Có `Caused by`, suppressed exceptions, stack trace nhiều dòng cần giữ nguyên?
7. **Dữ liệu có nhạy cảm?** Có request/user/message payload, credentials, IP, thiết bị, PII hoặc audit yêu cầu kiểm soát riêng?
8. **Mức độ thay đổi schema?** Có deployment nhiều version chạy song song, forward/backward compatibility?
9. **Ngân sách tài nguyên?** CPU encoding, GC allocation, file/network bytes, collector parsing và storage/indexing?
10. **Mức bảo đảm?** Log debug best-effort hay audit cần lưu/đối soát? Format không thể tự giải quyết durability.

Một quy tắc tham khảo:

- Nếu log chủ yếu được **người đọc trên terminal** và ít field, bắt đầu bằng pattern text rõ ràng.
- Nếu logs được **máy tự truy vấn/tổng hợp** trên nhiều service, ưu tiên **structured record + JSONL** hoặc cấu trúc telemetry được collector hỗ trợ.
- Nếu tổ chức đã có **SIEM/syslog contract**, format đầu ra phải đúng chuẩn giao tiếp và escaping của receiver.
- Nếu dùng **OpenTelemetry end-to-end**, kiểm tra việc xuất OTLP có đáp ứng logging context, cost và semantics hơn việc chuyển đổi text ở collector không.
- Nếu cần **hai đối tượng sử dụng**, có thể dùng formatter khác nhau cho console developer và pipeline production, nhưng phải kiểm soát việc phát **hai bản sao cùng event**.

## 5. Text pattern: đơn giản nhưng cần nhất quán

Một pattern log thông dụng:

```text
2026-11-10T02:00:00.000Z INFO  orders-api [traceId=abc123] com.example.OrderService - event=order.create.result orderId=ord-42 outcome=SUCCEEDED
```

Text có lợi cho người đọc trực tiếp, đặc biệt khi hệ thống có formatter cấp độ, timestamp, logger và thread sẵn. Nó phù hợp khi mục tiêu là chẩn đoán theo dòng đơn lẻ.

### 5.1. Các quy tắc để text không trở thành anti-pattern

- Có **timestamp rõ timezone**, level, component/logger, event code khi cần.
- Chỉ dùng message tiếng người cho giải thích; field quan trọng nên được định danh dễ nhận diện.
- Nếu đưa key-value vào text, phải thống nhất cách escape quote, dấu cách và ký tự điều khiển.
- Không dùng `System.out.println("Done")` như logging chuẩn của mọi service.
- Không thay đổi vị trí fields/pattern tùy tiện nếu collector đang parse bằng regex.
- Không ghi multiline payload tùy ý khi pipeline giả định **một dòng = một event**.
- Gắn `requestId`/`traceId` khi có và đúng scope; không dựa vào thứ tự dòng để suy ra request.
- Dùng **event code và errorCode ổn định**, không dùng toàn bộ câu message làm metric label.

### 5.2. Khi nào text phù hợp hơn JSON?

Ở công cụ command-line ngắn, console cho lập trình viên, log tạm trong test hoặc hệ thống không có truy vấn theo field, text có thể dễ dùng hơn. Không cần đưa mọi script Java nhỏ vào hệ thống JSON chỉ vì “structured” nghe chuyên nghiệp.

Tuy vậy, nếu bạn cần thường xuyên hỏi “Bao nhiêu lần `PAYMENT_TIMEOUT` xảy ra theo service và major version?” hay liên kết bằng trace ID, text không có field riêng sẽ tạo thêm việc ở collector/parser.

### 5.3. Text với stack trace

Exception qua SLF4J hoặc JUL có thể in nhiều dòng:

```text
ERROR order.persist.failed requestId=req-101
java.lang.IllegalStateException: cannot save
    at com.example.OrderService.save(...)
Caused by: java.io.IOException: storage unavailable
```

Đoạn này chỉ là minh họa. Nếu collector tail từng dòng, nó có thể tách một Throwable thành nhiều records. Cần multiline parser có giới hạn/timeout hoặc chọn **JSONL encoder ghi stack trace được escape thành một field trong một record**.

## 6. Key-value: dễ grep nhưng không phải lúc nào cũng có typed fields

Ví dụ:

```text
time=2026-11-10T02:00:00Z level=INFO event=order.create.result requestId=req-101 orderId=ord-42 durationMs=27 outcome=SUCCEEDED
```

Ưu điểm là ngắn gọn, dễ grep và có thể parse nếu quy ước chặt. Điểm cần chú ý là **grammar**:

- Giá trị chứa khoảng trắng có phải đặt trong quote không?
- Escape dấu quote, dấu backslash, dấu `=`, CR/LF và tab như thế nào?
- Khi field thiếu, ghi `null`, `-`, bỏ field hay chuỗi rỗng?
- Số `27` được parser hiểu là integer hay string?
- Tên key phân biệt chữ hoa/thường không?
- Khi giá trị có dấu unicode hoặc dấu phân cách, parser có còn đọc đúng không?
- Có giữ thứ tự các field hay key có thể hoán đổi?

Không được mặc định mọi chuỗi `key=value` tự thành structured attributes trong hệ log tập trung. Một số hệ dùng logfmt với quy tắc quote/escape riêng, một số dùng regex hoặc parser tùy chỉnh; phải chọn và test **một dialect nhất quán**.

**Không viết parser bằng `line.split(" ")`** rồi tin rằng có thể xử lý mọi value. Chuỗi `errorMessage="disk write failed"` sẽ bị chia sai nếu parser không hiểu quoting.

## 7. JSON Lines: lựa chọn phổ biến cho centralized logs

**JSONL** là một chuỗi các **JSON object riêng biệt, mỗi event trên một dòng**:

```json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27}
```

Một event khác nằm trên dòng kế tiếp. Dữ liệu nested hoặc array vẫn hợp lệ nếu thật sự cần, nhưng nên tránh object graph quá lớn.

Ưu điểm:

1. **Kiểu dữ liệu rõ:** number, boolean, string, array, object, null; `durationMs` có thể là số.
2. **Field được đặt tên:** parser không cần đoán vị trí từ câu message.
3. **Tương quan tốt:** requestId, traceId, messageId, jobRunId thành field riêng.
4. **Tìm kiếm và aggregation dễ hơn:** filter `event`, `errorCode`, `status`...
5. **Escaping chuẩn:** newline/quote trong string được encode thay vì phá một event thành nhiều dòng.
6. **Schema có thể version hóa:** field names/type được kiểm thử hợp đồng.
7. **Collector có nhiều parser hỗ trợ JSON:** nhưng vẫn phải bật đúng config.

Nhược điểm:

- Thêm overhead bởi dấu quote, dấu phân cách và lặp tên field.
- Người xem console phải đọc một dòng JSON dài; cần pretty-viewer nếu dùng để debug.
- Deeply nested fields hoặc array rất dài làm truy vấn/index và chính sách privacy khó.
- Encoder/serializer có thể tốn CPU/allocation hơn một pattern text đơn giản, tùy thư viện và tải.
- JSONL **phải** là JSON hợp lệ; không tự ghép raw message vào chuỗi JSON thủ công trong production.
- Một log event lớn có thể vượt line limit của agent, file tail parser, log gateway hoặc backend search.
- JSONL không tự tạo retry/ACK, không bảo đảm disk durability hay log collector nhận đủ.

**JSONL không có nghĩa file bắt buộc phải tên `.jsonl`.** Tên file là quy ước, còn điều quan trọng là **mỗi dòng là một JSON value theo schema đã định, thường là object** và pipeline không inject raw newline trong strings.

### 7.1. JSON phải là một event một dòng

Giả sử message có newline:

```text
first line
second line
```

JSON serializer hợp lệ sẽ ghi một string với escape sequence `\n`, ví dụ:

```json
{"event":"debug.message","message":"first line\nsecond line"}
```

Trong file, phần `\n` là **hai ký tự hiển thị** backslash và chữ n, không phải xuống dòng thực ở giữa JSON string. Mỗi dòng file vẫn chứa đúng một JSON object.

Nếu ứng dụng tự ghép thành:

```text
{"message":"first line
second line"}
```

thì đó **không phải một JSON object trên một dòng hợp lệ**; parser JSONL có thể coi là hai dòng hỏng.

## 8. Java 17 runnable: một LogRecord, hai định dạng

Ví dụ Java 17 này sử dụng **JUL `LogRecord` và `Formatter`** sẵn trong JDK. Cùng một event chứa timestamp, level, event code, request ID, order ID, outcome, duration và detail sẽ được biểu diễn dưới dạng:

- Một dòng **text key=value** dành cho người đọc.
- Một dòng **JSONL** dành cho JSON parser.

Để stdout hoàn toàn tái lập, chương trình đặt `Instant` cố định, gọi trực tiếp hai formatter và in kết quả. Nó **không ghi file hay gửi network**; trong ứng dụng thật, formatter/encoder phải được lắp với `Handler`/appender và cấu hình lifecycle của backend.

Giá trị `detail` chứa **dấu quote và newline**, nhằm chứng minh cả hai biểu diễn có thể escape thành **một dòng**.

Lưu file **`LogFormatDemo.java`**:

```java
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;

public class LogFormatDemo {
    record Fields(
            String requestId,
            String orderId,
            String outcome,
            long durationMs,
            String detail) {}

    // Chỉ minh họa một phần JSON string escaping trong JDK thuần.
    // Production nên dùng JSON encoder/serializer đã được kiểm chứng.
    private static String quote(String value) {
        if (value == null) {
            return "null";
        }

        StringBuilder out = new StringBuilder();
        out.append((char) 34);

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            if (c == 34 || c == 92) {
                out.append((char) 92).append(c);
            } else if (c == 10) {
                out.append((char) 92).append('n');
            } else if (c == 13) {
                out.append((char) 92).append('r');
            } else if (c == 9) {
                out.append((char) 92).append('t');
            } else if (c < 32) {
                String hex = Integer.toHexString(c);
                out.append((char) 92).append('u');
                out.append("0".repeat(4 - hex.length()));
                out.append(hex);
            } else {
                out.append(c);
            }
        }

        return out.append((char) 34).toString();
    }

    private static Fields fields(LogRecord record) {
        return (Fields) record.getParameters()[0];
    }

    static final class TextFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Fields f = fields(record);
            return record.getInstant() + " "
                    + record.getLevel().getName()
                    + " event=" + record.getMessage()
                    + " requestId=" + f.requestId()
                    + " orderId=" + f.orderId()
                    + " outcome=" + f.outcome()
                    + " durationMs=" + f.durationMs()
                    + " detail=" + quote(f.detail())
                    + System.lineSeparator();
        }
    }

    private static void stringField(
            StringBuilder out, String key, String value) {
        out.append(quote(key)).append(':').append(quote(value));
    }

    static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Fields f = fields(record);
            StringBuilder out = new StringBuilder("{");

            stringField(out, "timestamp",
                    record.getInstant().toString());
            out.append(',');
            stringField(out, "level", record.getLevel().getName());
            out.append(',');
            stringField(out, "event", record.getMessage());
            out.append(',');
            stringField(out, "requestId", f.requestId());
            out.append(',');
            stringField(out, "orderId", f.orderId());
            out.append(',');
            stringField(out, "outcome", f.outcome());
            out.append(',');
            out.append(quote("durationMs"))
                    .append(':').append(f.durationMs());
            out.append(',');
            stringField(out, "detail", f.detail());
            out.append('}').append(System.lineSeparator());
            return out.toString();
        }
    }

    public static void main(String[] args) {
        LogRecord record = new LogRecord(
                Level.INFO, "order.create.result");
        record.setInstant(Instant.parse("2026-11-10T02:00:00Z"));
        String detail = "accepted " + (char) 34 + "item"
                + (char) 34 + (char) 10 + "verified";
        record.setParameters(new Object[]{
                new Fields(
                        "req-101", "ord-42", "SUCCEEDED", 27, detail)
        });

        System.out.println("TEXT");
        System.out.print(new TextFormatter().format(record));
        System.out.println("JSONL");
        System.out.print(new JsonFormatter().format(record));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac LogFormatDemo.java
java LogFormatDemo
```

**Stdout chính xác** với hệ thống có line ending thông thường:

```text
TEXT
2026-11-10T02:00:00Z INFO event=order.create.result requestId=req-101 orderId=ord-42 outcome=SUCCEEDED durationMs=27 detail="accepted \"item\"\nverified"
JSONL
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","requestId":"req-101","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27,"detail":"accepted \"item\"\nverified"}
```

### 8.1. Tại sao output như vậy?

- `LogRecord` chứa severity và message code; `setInstant` cố định timestamp để không phụ thuộc đồng hồ máy.
- `Fields` là record Java 17 dùng để truyền dữ liệu event vào formatter demo, **không phải API chung của JUL**.
- `TextFormatter` viết một dòng chứa các cặp key/value. Trường `detail` được quote để không biến newline của input thành log line mới.
- `JsonFormatter` ghi một JSON object. `durationMs` là **number**, còn các trường còn lại là string.
- `quote` xử lý quote, backslash, CR/LF/tab và C0 control characters. Ví dụ input chứa newline thật nhưng stdout biểu diễn bằng `\n`.
- `TextFormatter` và `JsonFormatter` là các kiểu `java.util.logging.Formatter` thực sự có thể được dùng với JUL `Handler`; ví dụ gọi trực tiếp để kiểm tra rendering độc lập với console handler, file I/O và timestamp mặc định.
- `System.lineSeparator()` dùng line ending phù hợp hệ điều hành; khi xem stdout dưới dạng các dòng, nội dung logic giống nhau.
- Ví dụ chỉ có **một event** nên không minh họa log rotation, batch, async delivery hoặc collector.

### 8.2. Giới hạn bảo mật của ví dụ

Hàm `quote` được viết cho bài học, **không phải JSON serializer production**. Nó không thực hiện đầy đủ xử lý dữ liệu Unicode không hợp lệ (chẳng hạn unpaired UTF-16 surrogate), không giới hạn payload size, không che PII/secret, không quyết định schema và không kiểm tra semantic correctness của các field. Khi làm sản phẩm thật, dùng encoder/serializer đã được kiểm thử và cập nhật theo framework.

Phần text `key=value` cũng **không được tuyên bố tuân thủ một dialect logfmt chuẩn cụ thể**. Nó chỉ minh họa cách ghi một chuỗi dễ đọc. Giá trị ở `event`, `requestId`, `orderId` trong ví dụ là hằng đáng tin; với input thật, phải validate/escape tất cả trường text chứ không chỉ detail.

Nếu chạy trong hệ thống có nhiều dữ liệu, không tự tạo record rồi gọi formatter ở mọi business method. Hãy dùng logger/provider chuẩn để level/filter, MDC/context, batching và error handling được quản lý tập trung.

## 9. Gắn formatter vào JUL, SLF4J/Logback và Log4j 2

### 9.1. JUL: Formatter và Handler

Trong JUL, `LogRecord` chứa metadata log; `Formatter` chuyển record thành text; `Handler` quyết định nơi gửi. Khi thực sự dùng format trong ứng dụng, một handler phải được cấu hình với formatter phù hợp. **Chỉ gán `record.setParameters(...)` không tự khiến ConsoleHandler tạo JSON**.

Mảnh tích hợp:

```java
// Trong cùng lớp chứa JsonFormatter và logger phù hợp.
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setFormatter(new JsonFormatter());
handler.setLevel(java.util.logging.Level.INFO);

java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("demo.orders");
logger.setUseParentHandlers(false);
logger.addHandler(handler);

// Khi khởi tạo ứng dụng xong, cần cleanup handler ở lifecycle thích hợp.
```

Đoạn này **chỉ minh họa wiring**, không phải file độc lập. Nếu dùng `JsonFormatter` của demo, nó đòi `LogRecord.getParameters()[0]` là `Fields`; các bản ghi thông thường **không có** tham số này sẽ lỗi. Trong production, formatter phải xử lý mọi `LogRecord`, field thiếu, message parameters, resource bundles, Throwable, special characters và error policies. Không áp dụng formatter demo cho root logger của hệ thống đang chạy.

Một điểm thường gây bất ngờ: `ConsoleHandler` của JUL theo mặc định ghi vào **stderr**, không phải stdout. Vì vậy khi cần stdout cố định trong demo, chúng ta gọi formatter trực tiếp thay vì dựa vào console handler.

### 9.2. SLF4J không phải format đích

**SLF4J là API facade**, không phải encoder JSON. Một lời gọi:

```java
// Mã tích hợp, các biến đã được validate.
log.info("event=order.create.result orderId={} outcome={}",
        safeOrderId, outcomeCode);
```

có thể ra text hoặc JSON tùy provider/backend/layout. Placeholder `{}` là cơ chế tạo message, **không tự tạo thuộc tính JSON độc lập**.

Với **SLF4J 2.x**, có thể bổ sung key-value:

```java
// Đoạn tích hợp cho org.slf4j.Logger phiên bản 2.x.
log.atInfo()
        .addKeyValue("event", "order.create.result")
        .addKeyValue("orderId", safeOrderId)
        .addKeyValue("outcome", outcomeCode)
        .addKeyValue("durationMs", durationMs)
        .log("Order creation finished");
```

Tuy nhiên, provider/encoder vẫn phải **xuất key-value fields** thành format mong muốn. Một số pattern chỉ hiển thị message và bỏ attributes. Cần xác minh bản ghi tại sink thật, không chỉ sự tồn tại của lời gọi `addKeyValue`.

### 9.3. Logback Classic

Với Logback, một text pattern có thể sử dụng `PatternLayoutEncoder`:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level %logger - %msg%n%ex</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Đây là **mảnh cấu hình** trong một appender Logback tương thích. Nó có metadata và exception rendering; không phải JSONL.

Với JSONL, có thể dùng một encoder JSON phù hợp, ví dụ **logstash-logback-encoder** trong dự án có dependencies tương thích:

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
```

**`LogstashEncoder` không có sẵn trong JDK hoặc Logback Core**: phải thêm artifact/phiên bản tương thích và kiểm tra format, timezone, MDC, Throwable, structured arguments và quy tắc redaction trên chính dự án đó.

Một ứng dụng có thể muốn **text pattern ở local development** và **JSON encoder ở production**, nhưng đừng làm schema thay đổi ý nghĩa giữa môi trường. Nếu cùng lúc thêm console + file/remote appender, kiểm tra xem event có bị ship hai lần qua các tuyến độc lập không.

### 9.4. Log4j 2

Log4j 2 có PatternLayout và các cách xuất JSON có cấu trúc, chẳng hạn **JsonTemplateLayout** với dependency/config tương ứng. Lựa chọn layout và chi tiết resolver/field names phụ thuộc phiên bản. Không dùng XML class của Logback trong Log4j 2 hoặc ngược lại.

Dù backend nào, cần kiểm tra:

- Log event được encoder thành **một JSON object mỗi dòng** hay text nhiều dòng?
- MDC/ThreadContext, Throwable và thread/logger metadata có được xuất?
- Field names có đúng schema mong muốn và không duplicate/conflict?
- JSON numbers/booleans được giữ đúng kiểu?
- Có escape characters và masking?
- Encoder có còn hoạt động khi có `null`, exception sâu, marker và message cực dài?
- Các appender và collector có cùng timestamp/timezone/line framing?

## 10. Format và schema: trường nào cần chuẩn hóa?

Một structured event khuyến nghị:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service.name": "orders-api",
  "deployment.environment": "production",
  "event": "order.persist.failed",
  "operation": "SAVE_ORDER",
  "requestId": "req-101",
  "traceId": "e64c82e718934f48a84e7a5fcf72b9d1",
  "orderId": "ord-42",
  "outcome": "FAILED",
  "errorCode": "DB_CONNECTION_TIMEOUT",
  "durationMs": 103
}
```

Đây là **một schema minh họa**, không phải tên trường bắt buộc của OpenTelemetry, ECS hay mọi vendor. Tổ chức nên chọn **một convention** rồi lập bảng mapping sang hệ đích.

Các nhóm trường:

| Nhóm | Các ví dụ nên xem xét |
| --- | --- |
| **Envelope** | timestamp, severity/level, logger name, service, version, environment |
| **Sự kiện** | event code, operation, phase, outcome, errorCode |
| **Liên kết** | requestId, correlationId, traceId, spanId, messageId, jobRunId |
| **Đối tượng** | resource type, resource ID đã kiểm duyệt |
| **HTTP** | method, route template, status, duration |
| **Message consumer** | topic/queue, partition/offset hoặc delivery tag, attempt |
| **Exception** | exception type, cause chain/stack trace theo policy |
| **Hệ thống** | instance/pod/container, region, deployment version |
| **Số liệu** | durationMs, retryCount, itemsProcessed; kiểu số rõ ràng |

Không cần tất cả các trường trong **mọi** event. Một log startup có thể chỉ cần service/version/time, trong khi lỗi payment cần payment ID, operation, errorCode và traceId. Schema phải **phù hợp loại sự kiện**, tránh “one giant object” chứa hàng chục field rỗng ở mọi dòng.

### 10.1. Dùng kiểu dữ liệu ổn định

Trong JSONL:

- `durationMs: 27` là số; `"durationMs": "27ms"` là string, khó aggregate bằng số.
- `retryable: true` là boolean; `"retryable": "true"` là string.
- `status: 404` có thể là integer; việc lưu `"404"` cần có lý do và mapping.
- `requestId` nên là string, không ép số làm mất leading zeros.
- `timestamp` nên có timezone rõ ràng, thường RFC 3339/ISO-8601 UTC.
- `errorCode` nên là enum/cataloɡ giá trị hữu hạn, không lấy exception message thô.

Cùng một field không nên đổi giữa number và string sau deploy, vì query và index có thể lỗi. Nếu thay đổi ý nghĩa hoặc format, cần version hóa/schema migration.

### 10.2. Null, missing và unknown

Ba trạng thái có ý nghĩa khác nhau:

- **Missing:** field không được thu thập hoặc không áp dụng.
- **Null:** field được xác định nhưng không có giá trị theo schema.
- **Unknown:** không thể phân loại/tính toán, có thể biểu diễn bằng enum `UNKNOWN` khi hợp lý.

Đừng điền `"N/A"` vào một field số như `durationMs`. Với JSON, tốt hơn là bỏ field hoặc dùng `null` theo contract, và bảo đảm collector/storage hiểu thống nhất.

## 11. Timestamp, timezone và precision

Format timestamp ảnh hưởng khả năng hợp nhất log từ nhiều JVM:

```text
2026-11-10T02:00:00.123Z
2026-11-10T09:00:00.123+07:00
```

Hai chuỗi trên có thể chỉ **cùng một thời điểm**, nhưng không nên dùng so sánh text thô để kết luận khác nhau.

Khuyến nghị:

1. Chọn UTC hoặc offset rõ ràng, thường UTC cho lưu trữ/truy vấn.
2. Ghi timestamp theo định dạng parse được ổn định (ví dụ RFC 3339).
3. Xác định **event time** (khi xảy ra) và **observed/ingestion time** (khi collector nhận) khác nhau ra sao.
4. Nếu ứng dụng dùng `System.nanoTime()` để đo duration, đừng serialize giá trị đó làm timestamp wall-clock: nó là đồng hồ monotonic dùng để đo thời gian chênh.
5. Không mặc định clock của mọi node đồng bộ hoàn hảo; log và trace phân tán có thể lệch thứ tự.
6. Xác định đơn vị và precision: milliseconds, microseconds hoặc nanoseconds tùy nhu cầu thực.
7. Không dùng pattern thiếu timezone khi dữ liệu sẽ hợp nhất từ nhiều region.

Lưu ý rằng mức precision cao không đồng nghĩa timestamp luôn có độ chính xác thực tương ứng. Đồng hồ hệ điều hành, runtime và collector có giới hạn riêng.

## 12. Severity và tên level

Java ecosystem có nhiều hệ level:

- JUL: `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`.
- SLF4J/Logback: `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`.
- Log4j 2: `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` và các level được cấu hình phù hợp.

Nếu log từ JUL và Logback cùng vào collector, có thể cần **severity mapping**. Nhưng mapping không luôn 1-1 tuyệt đối; nên thống nhất cách xử lý `SEVERE` và `ERROR`, `WARNING` và `WARN`, các level thấp hơn cùng semantics.

Đừng dùng level như field duy nhất để nhận diện outcome. `WARN retrying` chưa chắc nghiệp vụ đã thất bại cuối cùng; `INFO result` có thể chứa `outcome=DENIED`. Đặt `event`, `outcome`, `errorCode` ổn định để query, level dùng để ưu tiên quan sát.

## 13. Throwable và multiline exception: một trong những lý do chọn format

Một exception có thể chứa:

- Class và message.
- Stack trace của wrapper và cause chain (`Caused by`).
- Suppressed exceptions (`Suppressed`).
- Request/operation context và error code.
- Dữ liệu nhạy cảm trong exception message nếu thư viện vô tình thêm vào.

Với **text**, stack trace thường nhiều dòng. Collector phải có multiline parser để nhận biết một event và ngăn stack trace bị chia thành nhiều records.

Với **JSONL**, encoder có thể đưa stack trace thành **một JSON string đã escape newline** hoặc một cấu trúc exception có trường riêng. Tuy nhiên tên field (`stack_trace`, `exception.stacktrace`...) và cách render cause/suppressed phụ thuộc encoder và schema.

Một event minh họa:

```json
{
  "event": "order.persist.failed",
  "errorCode": "STORAGE_UNAVAILABLE",
  "exceptionType": "OrderProcessingException",
  "rootCauseType": "IOException",
  "message": "Cannot create order"
}
```

Đây là **bản ghi tối giản**, chưa phải một stack trace đầy đủ. Muốn giữ bằng chứng, logger cần nhận **`Throwable` thực** chứ không chỉ `e.getMessage()`; encoder phải được cấu hình xuất exception. Có thể giới hạn stack depth/length vì cost và privacy, nhưng phải nhận thức rằng cắt mất cause chain sẽ làm điều tra khó.

Mảnh mã SLF4J:

```java
// Mảnh tích hợp: log là org.slf4j.Logger.
// failure là Throwable; safeOrderId đã được kiểm duyệt.
log.error("event=order.persist.failed orderId={}",
        safeOrderId, failure);
```

Với JUL:

```java
// Mảnh tích hợp: logger là java.util.logging.Logger.
logger.log(java.util.logging.Level.SEVERE,
        "Order persistence failed", failure);
```

Dùng `log.error("Failed: {}", failure.getMessage())` không truyền toàn bộ Throwable/cause chain. Và formatter tự viết chỉ nhìn `record.getMessage()` như demo sẽ **không tự đưa `record.getThrown()` vào output**: muốn dùng production phải xử lý trường này với encoder chuyên dụng.

## 14. Correlation, MDC và structured context

Một event có thể mang `requestId`, `traceId`, `spanId`, `messageId` hoặc `jobRunId`. Format nào cũng phải cho phép **giữ ID đúng scope và không bị trộn** giữa các request/thread.

Với SLF4J:

```java
import org.slf4j.MDC;

// Mảnh tích hợp: requestId đã được kiểm tra.
String old = MDC.get("requestId");
try {
    MDC.put("requestId", validatedRequestId);
    processRequest();
} finally {
    if (old == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", old);
    }
}
```

Mảnh mã này cần `processRequest()` và các biến có sẵn. `MDC` không tự phát sự kiện, cũng không bảo đảm encoder luôn xuất `requestId`. Pattern Logback có thể dùng `%X{requestId}`; một JSON encoder có thể xuất MDC thành fields nếu cấu hình tương ứng.

Cẩn thận:

- Thread pool tái sử dụng thread: clear/restore trong `finally`.
- Với `CompletableFuture`, executor hoặc WebFlux/reactive stack, context không tự lan qua mọi thread.
- Trace ID không phải business ID; request ID không chứng minh danh tính người dùng.
- ID lấy từ header client có thể giả mạo hoặc rất dài, phải validate/trust policy.
- Không dùng requestId, traceId hoặc userId làm **metric label** high cardinality.

Một format đẹp nhưng thiếu correlation fields khi cần phân tích phân tán vẫn là một log design yếu.

## 15. Tính nhất quán giữa service và schema version

Một vấn đề phổ biến khi ứng dụng có nhiều service:

```text
Service A: traceId, orderId, durationMs
Service B: trace_id, order_id, elapsed
Service C: TraceID, order_number, time_ms
```

Dù cả ba xuất JSONL, dashboard và truy vấn phải xử lý mapping phức tạp. Cần một **schema contract**:

1. **Catalog tên field** theo domain và convention chung.
2. **Kiểu dữ liệu** cụ thể cho từng field.
3. **Ý nghĩa**: duration được đo từ đâu đến đâu? status là HTTP hay business?
4. **Required vs optional** cho từng loại event.
5. **Nhãn phân loại**: errorCode/outcome/event code ổn định.
6. **Ownership** của trường: ứng dụng hay collector tạo.
7. **Version** nếu thay đổi lớn hoặc các service rollout lệch nhịp.
8. **Mapping** sang storage/index hoặc OpenTelemetry semantic conventions khi cần.
9. **Compatibility tests** ở cả encoder và collector.

Đừng đổi `"durationMs": 27` thành `"durationMs": "27 ms"` trong cùng index mà không migration; storage có thể không còn aggregate đúng. Đừng đổi ý nghĩa `order.created` từ “DB committed” sang “message accepted” rồi giữ nguyên event name.

Version hóa có thể là `schemaVersion: 1` hoặc một cơ chế contract/release riêng. Không phải mọi dòng log cần một field version nếu nơi nhận đã biết schema từ topic/index, nhưng **ngữ nghĩa thay đổi phải được quản lý**.

## 16. Pretty JSON khác JSONL

JSON để debug đôi khi được pretty print:

```json
{
  "event": "order.create.result",
  "outcome": "SUCCEEDED"
}
```

Đây là JSON hợp lệ như một document, nhưng **chiếm nhiều dòng**. Nếu collector đang tail theo dòng và trông đợi một event trên mỗi dòng, pretty JSON có thể bị chia thành nhiều records không hợp lệ.

Trong file hoặc stdout được sidecar/agent thu thập, ưu tiên **compact single-line JSON**; nơi xem log có thể pretty print sau khi parse. Trừ khi collector được cấu hình rõ để hỗ trợ framing/multiline JSON, **đừng pretty print trong production log stream**.

Cũng cần phân biệt JSONL với **một JSON array toàn file**: array cần delimiter/đóng file để parse, không thân thiện với append và tail streaming như các object trên từng dòng.

## 17. Security: format phải đi cùng redaction và escaping

Chọn JSON không có nghĩa tự động an toàn. Một JSON object vẫn có thể chứa:

```json
{
  "event": "login.failed",
  "password": "DO_NOT_LOG_THIS",
  "accessToken": "DO_NOT_LOG_THIS"
}
```

Đây là ví dụ **các field phải tránh**, không phải template nên dùng.

Các nguy cơ:

1. **PII/secret leak:** token, cookie, password, email, địa chỉ, chi tiết tài chính hoặc y tế.
2. **Log injection:** input chứa CR/LF/control characters có thể giả mạo text log.
3. **Oversized event:** raw request/response body làm đầy queue, disk hoặc collector.
4. **Dynamic fields:** user-controlled JSON keys khiến schema/index bùng nổ.
5. **Deep nesting / cyclic object:** serialize một object Java tùy ý có thể tốn tài nguyên, lỗi recursion hoặc làm lộ dữ liệu.
6. **Exception messages:** driver có thể đưa SQL/query/URL/internal path vào `getMessage()`.
7. **Source ambiguity:** client tự khai `User-Agent`, correlation ID, IP forwarding headers có thể bị giả mạo.
8. **Index mapping explosion:** sinh field name động theo user/resource ID.
9. **Retained duplicates:** gửi log đến nhiều sink có thể tăng phạm vi truy cập dữ liệu.

Thực hành:

- **Data minimization** ngay tại code; chỉ log field cần thiết cho mục đích định rõ.
- Dùng encoder/serializer có escaping đúng chuẩn thay vì tự nối JSON string.
- Validate và giới hạn input (ID, header, reason) trước khi ghi.
- Với text, escape quote, newline, backslash và ký tự điều khiển; không coi SLF4J placeholder là sanitizer.
- Dùng allowlist cho field names và event codes.
- Tránh log raw payload; dùng IDs, loại đối tượng và error codes.
- Quy định quyền đọc, retention, redaction và encryption phù hợp.
- Test bằng payload quote, newline, tab, control chars, unicode và dòng rất dài.

**Format chỉ quyết định biểu diễn, không quyết định dữ liệu nào được phép lưu.** Redaction cần áp dụng đúng chỗ trong pipeline và kiểm chứng dữ liệu cuối tại storage.

## 18. Kích thước, CPU và chi phí storage

Một đánh đổi đáng quan tâm:

- **Text pattern** có thể ngắn và rẻ nếu ít field, nhưng truy vấn riêng fields có thể tốn công parse.
- **JSONL** có overhead lặp tên key, dấu quote và escaping. Bù lại, parser có thể giữ dữ liệu có cấu trúc.
- **Key=value** có thể compact nhưng parser và escaping semantics phụ thuộc convention.
- **OTLP / binary/protobuf** có thể phù hợp transport hiện đại, batching, compression và typed fields, nhưng cần exporter/collector và quan sát riêng.

Không nên kết luận “JSON luôn nhanh hơn text” hay “protobuf luôn tiết kiệm hơn” khi chưa đo. Hiệu năng tùy field count, độ dài message, encoder, batching, compression, JVM allocation và log rate.

Có thể tính gần đúng:

```text
bytes_per_second ≈ events_per_second × average_encoded_bytes_per_event
bytes_per_day    ≈ bytes_per_second × 86,400
```

Ví dụ: **5.000 event/giây × 800 bytes/event = 4 MB/giây** (MB thập phân), tương đương khoảng **345,6 GB/ngày trước compression/replication/index overhead**. Nếu JSONL tăng 200 bytes mỗi event so với text trong trường hợp này, sẽ tăng khoảng **86,4 GB/ngày** dữ liệu raw. Đây là ước lượng, không phải số đo benchmark của một ứng dụng cụ thể.

Quyết định format cần đi cùng **sampling, log level, retention, compression và policy audit**. Không nên tắt các event audit bắt buộc chỉ để giảm chi phí encoding.

## 19. Format ảnh hưởng pipeline và file rotation ra sao?

Một log event đi qua:

```text
Java code -> Logger -> Formatter/Encoder -> Appender
                                      |
                            file/stdout/network
                                      |
                           Sidecar/Node Collector
                                      |
                              Parse/Enrich/Buffer
                                      |
                           Central logging storage
```

Nếu dùng file/stdout line-based:

- **Một event một dòng** giúp tail/parse ổn định.
- File rotation phải phối hợp với collector (rename/inode/checkpoint) để tránh đọc thiếu/trùng.
- Logback/Log4j2/JUL có rolling policies khác nhau; format và rotation là **hai quyết định riêng**.
- Encoder có thể flush theo appender; việc gọi logger không đồng nghĩa sink đã nhận.
- Truncated/cut log event do limit của runtime/collector có thể tạo JSON hỏng.
- JSON object có thể bị split bởi transport line limit; cần giới hạn event size.
- Nếu dùng remote exporter, cần hiểu retry/backpressure/cancellation và batch acknowledgment.
- Nếu stdout container được node agent thu thập, không cần sidecar nếu hạ tầng đã hỗ trợ yêu cầu.

Một structured JSONL ghi xuống disk **không tự bền vững sau crash**. Muốn audit có guarantee, thiết kế giao dịch/outbox hoặc đường lưu bền vững đúng nghiệp vụ; một text message đẹp hay JSON đầy đủ không thay thế.

## 20. Test format: kiểm chứng output thật, không chỉ gọi logger

Một kế hoạch kiểm thử nên gồm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| INFO event bình thường | Có timestamp, level, event, outcome đúng |
| Duration | JSON là number, đơn vị rõ |
| Error code | Mã hữu hạn ổn định, không dùng exception message |
| Request/trace ID | Đúng scope, được validate, có thể absent |
| String chứa quote | JSON vẫn parse được |
| String chứa newline/tab | **Một event một dòng** khi dùng JSONL |
| Unicode tiếng Việt | Round-trip UTF-8 đúng |
| Null/field thiếu | Theo schema, không biến số thành string `"N/A"` |
| Throwable và cause chain | Được xuất/giới hạn theo policy |
| Suppressed exception | Không bị mất ngoài policy |
| MDC/context trong thread pool | Không leak sang request khác |
| Async callback | Context propagate đúng |
| Text parser | Quote/space/equals không làm lệch field |
| JSON parser | Tách được fields và kiểu dữ liệu |
| File tail/collector | Không tách record, không thiếu/trùng ngoài contract |
| Event dài | Bị giới hạn và báo phù hợp, không silently corrupt |
| PII/secrets | Không xuất tới sink ngoài policy |
| Schema migration | Query cũ/mới xử lý được các version cần hỗ trợ |
| High-cardinality labels | Không dùng IDs động làm metric labels |
| Logging level/filter | Biết event nào bị loại và vì sao |
| Async queue đầy | Có policy drop/block và metrics, không giả định lossless |

Một test automation thực tế:

1. Ghi log vào **test appender/handler** hoặc temp file riêng.
2. Tạo event có ID và timestamp ổn định.
3. Nếu là JSONL, dùng **JSON parser thực** để parse từng dòng.
4. Assert field names/types/values, field bắt buộc, optional/null.
5. Assert escaping, unicode, stack trace và control characters.
6. Với text, dùng **parser production** để xác nhận round-trip.
7. Đưa output qua collector test nếu pipeline có nhiều chặng.
8. Sau đổi version backend/encoder, chạy lại contract test.
9. Kiểm tra redaction ở **đích cuối**, không chỉ output trong JVM.
10. So sánh CPU/bytes/event/latency theo tải thật để quyết định có cần tối ưu.

### 20.1. Đừng chỉ so khớp một string literal

Một test `assertTrue(output.contains("Order created"))` không khẳng định field `outcome` hay `durationMs` được lưu kiểu đúng. Với JSONL, hãy parse và assert:

```text
event == "order.create.result"
outcome == "SUCCEEDED"
durationMs == 27  (number)
timestamp has explicit timezone
```

Đây là **assertion minh họa**, không phải cú pháp Java/JUnit. Với time và trace IDs sinh động, dùng test fixture/injectable clock hoặc kiểm tra kiểu/format thay vì snapshot timestamp của đồng hồ thực.

## 21. Lộ trình chuyển từ text sang JSONL

Nếu hệ thống cũ có text logs và muốn chuyển sang structured logs, hãy thực hiện có kiểm soát:

1. **Khảo sát nguồn:** logger/backend, pattern, appender, collector, multiline, dashboards, alert rules.
2. **Xác định field schema:** timestamp, severity, event, service, request/trace IDs, outcome/errorCode, business fields cần thiết.
3. **Chuẩn hóa event codes** ở ứng dụng thay vì chỉ parse message câu chữ.
4. **Chọn encoder** tương thích với version Logback/Log4j2/JUL và test dependencies.
5. **Thiết lập UTF-8 và JSONL** cho file/stdout line-oriented.
6. **Chuyển parser ở collector:** nhận biết text legacy và JSON mới theo nguồn, không đoán bằng message content.
7. **Đặt feature flag / staging rollout** nếu môi trường cho phép, đo parse errors và bytes/event.
8. **Giữ schema song song có chủ đích:** không ship hai bản cho cùng event vô tình.
9. **Cập nhật queries/dashboards/alerts** để dùng field typed thay regex.
10. **Đánh giá privacy:** structured fields có thể khiến một số ID dễ truy vấn hơn, nên xem lại quyền đọc và retention.
11. **Thử failure modes:** crash, async queue, rotation, line too long, network outage.
12. **Dọn legacy parsers** sau khi đã đối soát dữ liệu và hoàn thành migration.

Một lựa chọn thực tiễn là giữ **human-readable message** trong một field `message` của JSON, đồng thời đưa `event`/`errorCode`/`operation` thành fields độc lập. Không phải chọn “chỉ JSON” hoặc “không có message”.

### 21.1. Hai outputs khác nhau cho hai mục đích

Có thể dùng text console trong local development và JSONL ở production. Cũng có thể phát text và JSON qua hai appenders phục vụ hai sink riêng. Nhưng khi cả hai đến cùng hệ tập trung, phải xác định chính sách dedup để không đếm một event hai lần.

Nếu bật JSON tại production nhưng text ở test, các lỗi escaping/stack trace/schema có thể chỉ xuất hiện sau deploy. Nên có **integration test chạy đúng encoder production**, kể cả khi console developer dùng một format khác.

## 22. Những lỗi phổ biến khi chọn format

### 22.1. “Đã dùng JSON là structured logging tốt”

Không đúng nếu mọi thứ vẫn nằm trong `message: "Done"`, không có operation, outcome và IDs. JSON chỉ là container biểu diễn.

### 22.2. “Format text đơn giản sẽ không bao giờ cần schema”

Nếu collector dùng regex hoặc đội SRE cần query theo fields, text cũng phải có convention và grammar. Nếu không, wording đổi sẽ làm parser hỏng.

### 22.3. “Key=value luôn dễ parse”

Sai với value chứa space, quote, dấu `=`, newline hoặc Unicode đặc biệt mà không có escaping rõ.

### 22.4. “Pretty JSON tốt hơn JSONL cho collector”

Pretty JSON nhiều dòng có thể làm một event bị tách, trừ khi collector hỗ trợ framing/multiline tương ứng.

### 22.5. “JSON encoder tự che token”

Serializer chỉ đảm bảo escaping/encoding theo quy tắc, **không tự quyết định field nào được phép lưu**. Data minimization/redaction là việc riêng.

### 22.6. “MDC là structured logging”

MDC chỉ cung cấp context. Encoder phải export nó, đồng thời đảm bảo không leak giữa thread/request.

### 22.7. “Timestamp càng nhiều chữ số càng chính xác”

Precision được in không bảo đảm clock thực chính xác tương ứng. Timezone/clock skew vẫn cần quan tâm.

### 22.8. “Dùng raw exception message làm errorCode là tiện”

Message của driver/JDK có thể thay đổi hoặc chứa data nhạy cảm. Error code cần ổn định, có catalog và kiểm thử.

### 22.9. “OTLP thay thế mọi quyết định về log schema”

Không. Vẫn phải thiết kế event names, attributes, severity, trace context, privacy và lifecycle của exporter/collector.

### 22.10. “JSONL đảm bảo không mất log”

Không. Format không thay thế flush, durability, rotation, retry, offset/checkpoint và sink acknowledgment.

### 22.11. “Một formatter demo cũng đủ cho production”

Không. Formatter phải xử lý mọi LogRecord, Throwable, Unicode không hợp lệ, field missing, concurrent logging, encoder performance, buffering và I/O errors.

### 22.12. “Schema càng nhiều field càng tốt”

Không. Field thừa tăng cost, độ nhạy cảm và khả năng lẫn nghĩa. Chỉ thêm trường khi giải quyết câu hỏi vận hành/nghiệp vụ thật.

## 23. Checklist chọn format cho dự án Java

- [ ] Xác định người đọc chủ yếu và loại câu hỏi cần truy vấn.
- [ ] Phân biệt format, schema, appender, transport và delivery guarantee.
- [ ] So sánh text pattern, key=value, JSONL, syslog/SIEM và OTLP theo hạ tầng hiện có.
- [ ] Nếu cần centralized query, ưu tiên structured fields và parser đáng tin.
- [ ] Thiết kế event code, outcome/errorCode, IDs, durations với kiểu rõ ràng.
- [ ] Chuẩn hóa timestamp UTC/offset, severity, service và environment.
- [ ] Bảo đảm một event trên một dòng với JSONL; không pretty-print stream tail nếu chưa hỗ trợ.
- [ ] Chọn encoder JSON thật, có escaping, Unicode và Throwable support.
- [ ] Không coi SLF4J placeholders là JSON fields nếu backend không xuất structured attributes.
- [ ] Cấu hình MDC/thread context và propagation qua async đúng scope.
- [ ] Bảo vệ PII/secret, validate input, chống log injection và giới hạn kích thước event.
- [ ] Không dùng raw IDs làm metric labels hay dynamic JSON field names.
- [ ] Kiểm soát lưu lượng log, CPU/GC, bytes/event, compression và retention.
- [ ] Kiểm tra file rotation/collector parse và line limit trên đúng environment.
- [ ] Test JSON parser round-trip, field types, exception chain, schema compatibility và dữ liệu tại sink.
- [ ] Nếu thay format, cập nhật parser/dashboard/alert và lập kế hoạch rollout tương thích.
- [ ] Với audit bắt buộc lưu, thiết kế durability/integrity/ack riêng, không dựa vào JSONL.

**Kết luận:** **Chọn format** là chọn một **hợp đồng dữ liệu và vận hành** cho Java Logging. Text pattern dễ đọc; key=value gọn nếu grammar rõ; JSON Lines thuận tiện cho log tập trung và truy vấn fields; syslog/SIEM và OTLP phù hợp những hệ sinh thái tương ứng. Cách lựa chọn tốt là xuất phát từ **mục đích điều tra, schema, typing, khả năng parse, exception handling, bảo mật và chi phí**, rồi kiểm chứng với backend/collector thật. **Một event đúng ngữ nghĩa, có context tối thiểu và định dạng nhất quán quan trọng hơn việc chỉ đổi đuôi file sang JSON.**
