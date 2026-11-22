# Pipeline log trong kiến trúc Java Logging

## 1. Pipeline log là gì?

**Pipeline log (logging pipeline)** là chuỗi xử lý một sự kiện ghi log, từ lúc mã Java tạo ra sự kiện đến khi thông tin được định dạng, chuyển tới nơi nhận, lưu trữ và có thể tìm lại. Pipeline quyết định **sự kiện nào được ghi, dữ liệu nào đi kèm, cách biểu diễn, nơi gửi và cách xử lý khi thành phần ghi log gặp lỗi hoặc quá tải**.

Ví dụ, service xử lý đơn hàng gọi logger khi một yêu cầu tới:

- Code nghiệp vụ tạo sự kiện: `INFO`, thông điệp “Order accepted”, `orderId` và `correlationId`.
- Hệ thống logging kiểm tra ngưỡng cấp độ, áp dụng chính sách lọc và bổ sung ngữ cảnh phù hợp.
- Sự kiện được mã hóa thành một dòng JSON rồi xuất tới stdout của container, tệp hoặc endpoint thu thập log.
- Bộ thu thập chuyển dòng log tới kho lưu trữ; người vận hành tìm theo thời gian, service, cấp độ và `correlationId`.

Như vậy, lời gọi `logger.info(...)` **mới là đầu vào của pipeline**. Đã gọi logger không có nghĩa sự kiện chắc chắn đã được lưu bền vững ở kho trung tâm: nó có thể bị lọc, rơi khi hàng đợi đầy, lỗi truyền hoặc bị xóa theo chính sách lưu giữ.

Bài này tập trung vào **kiến trúc luồng log**, không nhầm với pipeline xử lý dữ liệu nghiệp vụ (request handler, batch ETL) hay một sản phẩm tập trung log cụ thể. Các bước và thứ tự dưới đây là mô hình khái niệm; framework, cấu hình và hạ tầng thực tế có thể đặt bộ lọc, encoder hoặc hàng đợi ở các vị trí khác nhau.

## 2. Bức tranh từ lời gọi logger đến truy vấn

```text
     Java application / library
                |
      1. Tạo LogEvent
       (level, message,
        exception, context)
                |
      2. Logger / API facade
         + level gate
                |
      3. Filter / enrich / redact
         (tùy framework)
                |
      4. Routing / fan-out
           /          \
      5a. Sync      5b. Async queue
         |              |
         +------v-------+
                |
      6. Formatter / encoder
         (text, key-value, JSON)
                |
      7. Handler / appender / sink
         (stdout, file, network)
                |
      8. Collector / transport
         (nếu có)
                |
      9. Storage / index / retention
                |
     10. Search, dashboard, alert
```

Mỗi bước có một trách nhiệm riêng:

| Công đoạn | Đầu vào → đầu ra | Cần quyết định |
| --- | --- | --- |
| **Producer** | Sự kiện nghiệp vụ → lời gọi logger | Ghi điều gì, cấp độ nào, bao nhiêu chi tiết? |
| **Logging API / facade** | Lời gọi → sự kiện được xét xử lý | Dùng API nào, có nên tạo sự kiện khi cấp độ đang tắt? |
| **Level gate / filter** | Nhiều sự kiện → tập hợp được chấp nhận | Bỏ DEBUG ở production? Lọc thông báo ít giá trị? |
| **Context / enrichment** | Sự kiện → sự kiện có trường bổ sung | Service, environment, trace/correlation ID lấy từ đâu? |
| **Redaction / policy** | Dữ liệu thô → dữ liệu được phép ghi | Chặn token, mật khẩu và dữ liệu nhạy cảm ra sao? |
| **Routing / buffering** | Sự kiện → một hoặc nhiều đích; hàng đợi nếu async | Đích nào nhận ERROR? Khi đầy queue thì làm gì? |
| **Encoder / formatter** | Sự kiện → chuỗi/byte | JSON Lines, text, UTF-8, timestamp UTC, exception format |
| **Appender / handler / sink** | Byte/chuỗi → stdout, file hoặc mạng | Flush, rotate, retry, timeout và lỗi I/O |
| **Collector / storage** | Dữ liệu đã gửi → dữ liệu tìm kiếm được | Thu thập, phân tích, chỉ mục, lưu giữ, quyền truy cập |
| **Consumer** | Log có thể truy vấn → kết quả vận hành | Tìm sự cố, điều tra và cảnh báo theo tiêu chí nào? |

**Thuật ngữ:** Trong `java.util.logging` (JUL) có `Logger`, `Filter`, `Formatter` và `Handler`. Các hệ như Logback/Log4j 2 thường gọi thành phần ghi ra đích là *appender*. SLF4J là một *facade* API; bản thân SLF4J không đóng vai trò kho lưu trữ hay bộ thu thập log. Một ứng dụng thường dùng SLF4J làm API và một logging provider/backend làm phần triển khai.

## 3. Giai đoạn tạo log: event phải mang ý nghĩa rõ ràng

Khi code gọi logger, một sự kiện nên chứa:

- **Timestamp:** thời điểm được tạo/nhận; quy định rõ định dạng và múi giờ.
- **Severity/level:** mức quan trọng như `DEBUG`, `INFO`, `WARN`, `ERROR` (tên cụ thể tùy API).
- **Logger name:** tên class hoặc thành phần phát sinh.
- **Message:** mô tả hành động hoặc tình trạng, đủ cụ thể để diễn giải.
- **Exception:** ngoại lệ thật, bao gồm stack trace khi cần; đừng chỉ lưu mỗi `e.getMessage()`.
- **Context/attributes:** `service`, `environment`, `traceId`/`correlationId`, `operation`, mã đối tượng nghiệp vụ được phép ghi.

Ví dụ cấu trúc mong muốn khi ghi JSON:

```json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "WARN",
  "service": "order-service",
  "logger": "com.example.orders.PaymentClient",
  "correlationId": "req-1001",
  "event": "PAYMENT_TIMEOUT",
  "message": "Payment provider timed out",
  "durationMs": 3000
}
```

Một câu `"Something went wrong"` rất khó lọc và đối chiếu. Sự kiện `PAYMENT_TIMEOUT` có tên ổn định và các trường có thể truy vấn sẽ có ích hơn. Tuy nhiên, **đừng ghi tất cả thuộc tính của request hoặc entity**; hãy thiết kế allowlist trường để tránh rò rỉ dữ liệu và giảm dung lượng.

Với logging kiểu tham số, ưu tiên tạo thông điệp theo cách backend có thể hoãn xử lý khi level bị tắt, ví dụ về mặt ý tưởng:

```java
// Minh họa lời gọi API SLF4J khi dự án có SLF4J và backend tương ứng.
// Đây là một dòng mã trong ứng dụng, không phải chương trình chạy độc lập.
logger.debug("Order {} processed in {} ms", orderId, durationMs);
```

Không nên nối chuỗi đắt tiền hoặc serialize cả đối tượng trước khi kiểm tra cấp độ; việc tính toán đó vẫn có thể xảy ra dù log cuối cùng bị bỏ.

## 4. Level gate và filter: hai câu hỏi khác nhau

**Level gate:** có nhận một sự kiện ở mức này không? Ví dụ logger chỉ nhận từ `INFO` trở lên. Nó thường là bước kiểm tra rẻ, trước phần xử lý tốn kém.

**Filter:** dù đã qua ngưỡng cấp độ, sự kiện có thỏa chính sách nội dung/ngữ cảnh không? Ví dụ bỏ một nhóm thông báo lặp lại hoặc chặn một loại sự kiện không được phép ghi. Một ứng dụng có thể có cả filter ở logger và filter riêng cho handler/appender.

Ví dụ với JUL:

- `Logger.setLevel(Level.INFO)` khiến `FINE` bị loại tại logger.
- `Logger.setFilter(...)` quyết định có tiếp nhận bản ghi đã qua level gate hay không.
- `Handler.setLevel(Level.WARNING)` chỉ cho `WARNING` và `SEVERE` đi tới handler đó.

Vì vậy, **logger đã chấp nhận một bản ghi chưa chắc handler sẽ xuất nó**. Khi có nhiều handler, cùng sự kiện có thể đi tới một số đích nhưng bị loại ở đích khác.

Không coi filter chuỗi đơn giản là biện pháp bảo mật đầy đủ. Dữ liệu bí mật phải được ngăn ngay tại nơi tạo sự kiện hoặc xử lý bằng chính sách redaction đáng tin cậy, trước khi bất kỳ sink không an toàn nào nhận được.

## 5. Enrichment và context propagation

Khi một yêu cầu đi qua controller → service → repository → HTTP client, các dòng log nên chia sẻ cùng mã liên kết như `correlationId` hoặc `traceId`. Nhờ đó có thể tìm đúng một giao dịch mà không cần đoán từ timestamp và thread.

**Ngữ cảnh có thể bổ sung:** tên service, phiên bản ứng dụng, môi trường triển khai, operation, request ID, trace/span ID, tenant ID khi được phép. Phân biệt:

- `eventId`: mã duy nhất của một sự kiện log/audit nếu cần định danh hoặc loại trùng.
- `correlationId`: mã nối các hoạt động thuộc một yêu cầu hoặc chuỗi nghiệp vụ.
- `traceId` và `spanId`: mã dùng trong distributed tracing. Log có thể đính kèm chúng để chuyển từ trace sang log.

Trong các backend hỗ trợ **MDC** (Mapped Diagnostic Context), thuộc tính thường được gắn với ngữ cảnh thực thi hiện tại, nhiều implementation dựa trên `ThreadLocal`. Vì vậy:

1. Đặt context khi bắt đầu xử lý yêu cầu.
2. Kế thừa/truyền context khi chuyển việc sang executor hoặc thread khác theo cơ chế được hỗ trợ.
3. Gỡ hoặc khôi phục context trong `finally` (hoặc scope được hỗ trợ) để thread tái sử dụng không lẫn dữ liệu giữa các yêu cầu.
4. Trong xử lý bất đồng bộ/reactive, **không giả định context tự đi theo thread**; cần bridge/propagation tương ứng với runtime.

Không chép toàn bộ HTTP headers, cookie hay thông tin định danh thô vào MDC. Context có thể theo cùng sự kiện qua nhiều sink, khiến một lần rò rỉ bị nhân rộng.

## 6. Formatter/encoder: từ event sang dữ liệu có thể đọc

**Formatter** quyết định cách biểu diễn bản ghi; **encoder** chuyển event thành byte để ghi hoặc gửi. Thuật ngữ và ranh giới cụ thể phụ thuộc framework. Hai dạng thường gặp:

```text
2026-11-09T10:15:30Z WARN order-service req-1001 Payment provider timed out
```

```jsonl
{"timestamp":"2026-11-09T10:15:30Z","level":"WARN","service":"order-service","correlationId":"req-1001","message":"Payment provider timed out"}
```

**Text pattern** dễ đọc trực tiếp bằng mắt nhưng khó parse khi format đổi, khi thông điệp chứa dấu phân cách hoặc stack trace nhiều dòng. **Structured JSON Lines** tạo dữ liệu theo trường; phù hợp cho collector và truy vấn, nhưng cần schema ổn định và serializer đúng chuẩn.

Các nguyên tắc:

- Dùng UTC hoặc timestamp chứa offset rõ ràng; nhất quán về độ chính xác thời gian.
- Giữ tên trường ổn định qua version; nếu thay đổi phá tương thích, có quy tắc migration hoặc `schemaVersion`.
- Escape dấu nháy, backslash và control characters; dữ liệu người dùng có newline không được tạo log giả hoặc phá ranh giới mỗi dòng.
- Chọn encoding thống nhất (thường UTF-8) từ JVM tới collector.
- Quy định max event size; đo và cảnh báo khi bị truncate để người vận hành không tưởng log còn đầy đủ.
- Stack trace cần định dạng truy vấn được, hoặc có chính sách nhóm các dòng thành một event logic.

Nếu encoder/collector biến một sự kiện có nội dung nhiều dòng thành nhiều record độc lập, việc tìm kiếm và tương quan có thể sai lệch. Thống nhất quy ước event boundary ngay trong thiết kế pipeline.

## 7. Sink, routing và lưu trữ

Một pipeline có thể phân nhánh: log nghiệp vụ thông thường tới stdout; log lỗi nghiêm trọng tới stderr hoặc một kênh cảnh báo; sự kiện audit quan trọng tới kho audit chuyên biệt. **Fan-out** giúp mỗi đích phục vụ mục tiêu riêng nhưng cũng làm tăng chi phí và rủi ro ghi trùng.

Các sink thường gặp:

| Sink | Ưu điểm | Hạn chế/điều cần kiểm soát |
| --- | --- | --- |
| Console/stdout | Dễ tích hợp với container runtime, process supervisor và collector | Nếu không có thành phần thu thập thì log có thể mất khi process/container bị thay thế. |
| File | Có thể lưu cục bộ khi mất mạng, hỗ trợ tail/rotate | Cần dung lượng, rotation, retention, phân quyền và cơ chế tránh mất khi đổi file. |
| Remote endpoint | Chuyển trực tiếp tới dịch vụ thu thập | Phụ thuộc mạng, timeout, retry, TLS và buffer khi kết nối gián đoạn. |
| Queue/broker | Tách tốc độ producer và consumer, hỗ trợ xử lý lại tùy cấu hình | Phải xử lý trùng, độ trễ, backlog, xác nhận nhận và độ bền. |

Sau sink, collector có thể gắn thêm metadata triển khai, parse bản ghi, lọc, chuyển tiếp tới kho tìm kiếm hoặc lưu trữ dài hạn. **Việc sink gọi thành công chưa đồng nghĩa đã lập chỉ mục thành công**; mỗi chặng có cơ chế xác nhận và thất bại riêng.

Các vấn đề cần quản trị ở phần hậu kỳ: quyền truy cập, phân vùng/index theo thời gian, thời hạn lưu giữ, rotate và xóa đúng hạn, chi phí ingest, trường có cardinality quá cao (như ID duy nhất bị dùng làm nhãn index), và khả năng truy vấn nhiều service bằng một correlation ID.

## 8. Đồng bộ và bất đồng bộ: đánh đổi hiệu năng, độ trễ, độ bền

**Synchronous pipeline:** thread gọi log thực hiện nhiều phần xử lý và có thể chờ sink. Cách này đơn giản hơn về luồng kiểm soát, nhưng sink chậm hoặc lock I/O có thể kéo dài latency của request.

**Asynchronous pipeline:** thread ứng dụng đưa event vào buffer/queue rồi tiếp tục. Worker riêng xử lý encoder và xuất tới sink. Cách này có thể giảm thời gian chờ của request nhưng tạo rủi ro khác: hàng đợi đầy, crash trước khi flush, reorder giữa nhiều worker hoặc mất context nếu snapshot không đúng.

```text
Application threads            Background logger/collector
       |                                  |
  Create event                             |
       |                                  |
  Capture context                         |
       |                                  |
  Bounded queue ---> dequeue ---> encode ---> sink ---> store
       |
  Queue full?
       |--- block caller
       |--- discard some events
       |--- synchronous fallback
       +--- fail/report according to policy
```

Hành vi khi queue đầy **không có một mặc định chung cho mọi framework**. Các chính sách thường gặp:

- **Block producer:** giữ sự kiện nhưng làm request chậm; có thể gây dây chuyền chờ khi sink lỗi.
- **Drop có kiểm soát:** ưu tiên giữ WARN/ERROR, bỏ một phần log ít quan trọng; cần metric đếm bị bỏ.
- **Fallback đồng bộ:** đẩy công việc về thread ứng dụng khi quá tải; đánh đổi latency để giảm mất log.
- **Spool bền vững:** đệm qua file/broker có cơ chế khôi phục; tốn tài nguyên và cần thiết kế ack/replay.

Không khẳng định “async luôn nhanh hơn” hoặc “async không mất log”. Tốc độ còn phụ thuộc encoder, sink, cấu hình, kích thước queue và cách flush. Đối với audit hoặc log thuộc yêu cầu kiểm soát bắt buộc, **không lấy mẫu hoặc bỏ ngẫu nhiên** chỉ để giảm tải; phải xác định chính sách độ bền, thiếu log và cơ chế phục hồi riêng.

## 9. Ví dụ Java 17+: một pipeline thực với java.util.logging

JDK cung cấp sẵn **Java Util Logging (JUL)**, đủ để minh họa các bước logger level → logger filter → handler level → formatter → output. Ví dụ chạy độc lập, không cần Maven hoặc thư viện bên ngoài.

Tạo file **`LoggingPipelineDemo.java`**:

```java
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingPipelineDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.pipeline");

        // Cô lập logger demo để không nhân đôi bản ghi qua parent handler.
        logger.setUseParentHandlers(false);
        for (Handler existing : logger.getHandlers()) {
            logger.removeHandler(existing);
        }

        // Bước 1: chỉ chấp nhận INFO trở lên tại logger.
        logger.setLevel(Level.INFO);

        // Bước 2: minh họa filter nội dung (không phải cơ chế bảo mật).
        Filter filter = record ->
                !record.getMessage().startsWith("INTERNAL:");
        logger.setFilter(filter);

        // Bước 3: định dạng kết quả thành một dòng JSON cho mỗi record.
        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "{\"service\":\"orders\","
                        + "\"level\":\"" + record.getLevel().getName() + "\","
                        + "\"message\":\""
                        + escapeJson(formatMessage(record))
                        + "\"}\n";
            }
        };

        // Bước 4: StreamHandler ghi vào stdout, flush sau từng publish
        // để kết quả minh họa xuất hiện ngay.
        StreamHandler output = new StreamHandler(System.out, formatter) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        // Bước 5: sink này chỉ chấp nhận WARNING trở lên.
        output.setLevel(Level.WARNING);
        logger.addHandler(output);

        logger.fine("Debug diagnostics");
        logger.info("Request accepted");
        logger.warning("Downstream latency high");
        logger.warning("INTERNAL: do not expose this message");
        logger.severe("Order create failed");
    }

    private static String escapeJson(String input) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append('\\').append('u')
                                .append(String.format("%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LoggingPipelineDemo.java
java LoggingPipelineDemo
```

**Stdout chính xác**:

```jsonl
{"service":"orders","level":"WARNING","message":"Downstream latency high"}
{"service":"orders","level":"SEVERE","message":"Order create failed"}
```

Vì sao chỉ có hai dòng?

1. `logger.fine("Debug diagnostics")` bị loại bởi ngưỡng `Logger=INFO`, trước khi tới handler.
2. `logger.info("Request accepted")` qua được logger và filter nhưng bị chặn bởi ngưỡng `Handler=WARNING`.
3. `logger.warning("Downstream latency high")` qua cả hai ngưỡng và filter, được formatter tạo JSON rồi StreamHandler xuất ra stdout.
4. `logger.warning("INTERNAL: ...")` đủ cấp độ nhưng bị `Logger Filter` loại.
5. `logger.severe("Order create failed")` được xuất ra dòng thứ hai.

Phần `escapeJson` minh họa cách escape dấu nháy, backslash, ký tự xuống dòng và ký tự điều khiển. Với hệ thống thật, dùng thư viện serializer được dự án quản lý và kiểm thử cả Unicode, dữ liệu không đáng tin, kích thước lớn; ví dụ trên cố tình giữ số trường ít để tập trung vào pipeline. Trường `service="orders"` trong formatter là giá trị tĩnh của demo, không phải enrichment từ ngữ cảnh thực.

**Các giới hạn phải hiểu đúng:**

- Ví dụ dùng **pipeline đồng bộ**, không có hàng đợi, transport hay kho lưu trữ tập trung.
- `StreamHandler` ghi trực tiếp stdout; không tự cam kết disk durability, retry, rotate hoặc audit retention.
- `Filter` dùng tiền tố `INTERNAL:` chỉ để chứng minh thứ tự xử lý. Nó **không** thể ngăn toàn bộ bí mật vô tình xuất hiện trong message; ứng dụng thật cần chính sách bảo vệ dữ liệu ngay từ nguồn.
- Để tránh mất hoặc nhân đôi log khi chạy trong ứng dụng thật, logging config nên được quản lý tập trung, không tùy tiện xóa handler dùng chung hoặc tạo handler mới trong mỗi request.
- `java.util.logging.ConsoleHandler` thông thường hướng tới `System.err`; ví dụ chủ động dùng `StreamHandler(System.out, ...)` để minh họa kết quả ở **stdout**. Các level của JUL tên là `FINE`/`INFO`/`WARNING`/`SEVERE`, không nhất thiết trùng tên level của Logback/Log4j 2.

### Đối chiếu code với kiến trúc

| Kiến trúc | Thành phần trong ví dụ |
| --- | --- |
| Producer | Năm lời gọi `logger.fine/info/warning/severe(...)` |
| Logger/level gate | `Logger.setLevel(Level.INFO)` |
| Logger filter | `Logger.setFilter(filter)` |
| Routing/sink threshold | `logger.addHandler(output)`, `output.setLevel(Level.WARNING)` |
| Encoder/formatter | `Formatter.format(LogRecord)` và `escapeJson` |
| Sink | `StreamHandler(System.out, formatter)` |
| Collector/storage/search | Không có trong demo; là các bước sau stdout ở môi trường triển khai |

Trong kiến trúc có nhiều handler, có thể gắn một handler cho ERROR, một handler cho log tổng quát; mỗi handler có threshold, formatter và sink riêng. Luôn kiểm tra nguy cơ **log trùng** khi dùng parent logger hoặc nhiều appender trỏ tới cùng đích.

## 10. Khi dùng SLF4J, Logback hoặc Log4j 2

Trong nhiều ứng dụng Java hiện đại, code nghiệp vụ gọi API SLF4J, còn backend như Logback hoặc Log4j 2 quyết định cấu hình cấp độ, layout/encoder, filter, appender và async. Một số thư viện dùng JUL hoặc API khác; nếu tích hợp bridge, cần cấu hình đúng chiều chuyển tiếp để tránh hai pipeline cùng ghi, vòng lặp bridge hoặc log trùng.

Có thể hình dung:

```text
Ứng dụng --SLF4J API--> backend logging
                           |
             logger level / context / filter
                           |
                       appenders
                      /         \
                 console      async queue
                    |              |
                 stdout       remote/file
                    \             /
                     collector (tùy hệ thống)
                           |
                      search/storage
```

Trong một số backend, filter có thể chạy ở nhiều vị trí (trước tạo event, tại logger, tại appender, tại collector); encoder có thể thực hiện trước hoặc sau enqueue. **Không dựa vào sơ đồ khái niệm để suy ra tuyệt đối thời điểm chạy hoặc ngữ cảnh đã được copy**. Hãy đọc cấu hình backend đang dùng và quan sát event thật tại từng chặng khi điều tra.

Một cấu hình cần trả lời rõ: log mức nào; một event đi đến những appender nào; đồng bộ hay async; queue capacity; chiến lược đầy queue; timeout và retry; layout/schema; nơi collector đọc; retention và quyền truy cập. Nếu chỉ biết “dự án có SLF4J” thì chưa đủ để kết luận các chính sách trên.

## 11. Quan sát và kiểm thử toàn pipeline

Chỉ kiểm tra có dòng log trong console là chưa đủ để biết toàn pipeline khỏe. Khi có collector và kho log, cần đo hoặc theo dõi:

| Chỉ số/kiểm tra | Dấu hiệu vấn đề |
| --- | --- |
| Số event đầu vào, số bị filter và số đi tới sink | Bị lọc nhầm hoặc thay đổi cấu hình làm mất log cần thiết. |
| Queue size, tỷ lệ đầy, thời gian chờ enqueue | Consumer chậm, queue sắp tràn, request latency tăng. |
| Số event bị drop, retry, fail-to-send | Mất dữ liệu hoặc sự cố transport/sink đang bị che khuất. |
| Ingestion lag: lúc xảy ra → lúc truy vấn được | Log “đến muộn”, cảnh báo hoặc điều tra thiếu dữ liệu mới. |
| Throughput và kích thước event | Tăng chi phí, tăng áp lực I/O và khả năng truncate. |
| Storage/query error và retention | Log không tìm được, chỉ mục lỗi, thiếu dung lượng hoặc xóa sai. |

Các ca kiểm thử có giá trị học tập:

1. **Level:** gửi lần lượt `DEBUG/FINE`, `INFO`, `WARN/WARNING`, `ERROR/SEVERE`, xác nhận chính xác ngưỡng tại từng handler.
2. **Filter:** gửi sự kiện đủ cấp độ nhưng trúng quy tắc lọc; xác nhận event không xuất hiện ở sink không được phép.
3. **Định dạng:** thử chuỗi chứa `"`, backslash, newline và ký tự Unicode; log phải còn parse được và không tạo bản ghi giả.
4. **Context:** hai request dùng thread pool, nhiều bước async; không được trộn `correlationId` của yêu cầu trước vào yêu cầu sau.
5. **Fan-out:** một event tới hai sink khi dự kiến, không bị nhân bản ngoài chủ ý.
6. **Backpressure:** mô phỏng sink chậm và queue đầy, kiểm tra policy block/drop/fallback, metric và ảnh hưởng latency.
7. **Process crash/network outage:** xác nhận điều gì còn lại, điều gì có thể mất và cơ chế phát lại hoạt động đúng phạm vi cam kết.
8. **End-to-end:** tạo sự kiện có ID biết trước, tìm được ở kho trung tâm với timestamp và trường dữ liệu đúng sau thời gian thu thập dự kiến.

Nếu thấy số lượng dòng trong ứng dụng và kết quả tìm kiếm ở kho khác nhau, hãy đối chiếu các chặng: điều kiện level → filter → queue → handler/appender → transport → collector parse → storage/index → truy vấn/retention. Đừng lập tức quy lỗi cho nơi hiển thị cuối cùng.

## 12. Các lỗi thiết kế thường gặp

- **Chỉ cấu hình level mà quên ngưỡng handler/appender:** `INFO` đã qua logger nhưng không được xuất vì handler chỉ nhận `WARNING`.
- **Không tắt parent handler khi muốn một đích duy nhất:** cùng event xuất lặp hai lần.
- **Tạo chuỗi/serialize đối tượng nặng trước khi kiểm tra level:** tốn CPU ngay cả khi log bị loại.
- **Ghi mọi log ở ERROR hoặc log quá nhiều:** báo động nhiễu, chi phí cao, không phân biệt lỗi và thông tin.
- **Bỏ qua context khi xử lý async:** không nối được sự kiện theo một request, hoặc tệ hơn là lẫn dữ liệu giữa requests.
- **Dùng async mà không thiết kế queue full và shutdown flush:** mất log trong giờ cao điểm hoặc khi process kết thúc.
- **Để bí mật đi vào log rồi trông đợi collector che lại:** dữ liệu đã có thể xuất hiện ở stdout, file hoặc đường truyền trước collector.
- **Nhầm stdout với storage bền vững:** container có log không có nghĩa dữ liệu đã tới kho trung tâm.
- **Không có schema/escape/UTF-8 nhất quán:** JSON hỏng, stack trace vỡ thành nhiều event, bộ lọc truy vấn không ổn định.
- **Không đo drop count và ingestion lag:** pipeline mất dữ liệu nhưng hệ thống không báo tín hiệu.
- **Dùng sampling chung cho audit/security events bắt buộc:** mất sự kiện quan trọng mà không có cơ chế chứng minh hoặc phục hồi.

## 13. Checklist áp dụng cho một service Java

Trước khi đưa pipeline vào môi trường vận hành, xác định:

1. **Nguồn:** những hành động/cấp độ log nào có giá trị, không ghi bí mật và thông tin thừa.
2. **Dữ liệu:** các trường cấu trúc nào được phép ghi; quy ước timestamp, logger, service, correlation/trace ID và error code.
3. **Routing:** logger/backend, level và filter ở từng tầng, các sink và nguy cơ duplicate.
4. **Hiệu năng:** synchronous hay asynchronous, dung lượng queue, xử lý queue full, flush và giới hạn chi phí.
5. **Vận chuyển:** collector nào nhận stdout/file/network, timeout, retry và yêu cầu TLS/quyền truy cập.
6. **Lưu trữ:** khả năng search, thời hạn giữ, phân quyền, quản lý chi phí và trách nhiệm với audit/security logs.
7. **Chất lượng:** có ca kiểm thử log từ ứng dụng tới kho cuối, đo được mất/trùng/trễ và phát cảnh báo khi pipeline gặp lỗi.

**Kết luận:** pipeline log là một chuỗi xử lý có điều kiện và nhiều điểm có thể thất bại. Hiểu rõ từng bước giúp giải thích vì sao một lời gọi logger không xuất hiện, vì sao xuất trùng, vì sao request bị chậm hoặc vì sao dữ liệu không có ở kho tập trung. Một pipeline tốt vừa tạo log có ích và dễ truy vết, vừa kiểm soát chi phí, bảo mật và tính tin cậy của dữ liệu.