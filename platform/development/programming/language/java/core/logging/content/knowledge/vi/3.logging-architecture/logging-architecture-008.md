# Đọc và phân tích log trong kiến trúc Java Logging

## Mục tiêu

Sau bài này, bạn có thể đọc một log entry theo ngữ cảnh, hiểu dữ liệu đi qua các thành phần logging trong Java, truy vết một request qua nhiều bản ghi, khoanh vùng sự cố bằng thời gian/level/identifier, phân biệt dấu hiệu với nguyên nhân gốc, và áp dụng cách đọc log dạng text, JSON hay nhiều dòng. Bạn cũng sẽ viết và chạy một ví dụ **Java 17+** tạo log bằng **java.util.logging (JUL)**, đọc lại từ tệp rồi tổng hợp các sự kiện.

Trọng tâm là **đọc và phân tích log** trong phần **Kiến trúc logging**: từ bản ghi ứng dụng phát ra đến file/console và hệ thống lưu trữ, sau đó đến thao tác tìm kiếm, lọc, liên kết và giải thích dữ liệu. Các câu lệnh dùng công cụ bên ngoài là tùy chọn; ví dụ Java chính chỉ sử dụng JDK.

## 1. Log được đọc từ đâu trong kiến trúc logging?

Khi Java chạy lệnh logging, bản ghi không tự động xuất hiện ở một nơi duy nhất. Đường đi đơn giản thường là:

~~~mermaid
flowchart LR
    A["Mã ứng dụng / thư viện"] --> B["Logger tạo LogRecord"]
    B --> C["Ngưỡng level, filter"]
    C --> D["Handler / Appender"]
    D --> E["Formatter / Encoder"]
    E --> F["Console, file hoặc đích khác"]
    F --> G["Collector / shipper (nếu có)"]
    G --> H["Lưu trữ và lập chỉ mục"]
    H --> I["Truy vấn, dashboard, cảnh báo"]
~~~

Tùy framework, thứ tự vận dụng filter/formatter và cơ chế xuất có thể khác; sơ đồ cho thấy **luồng khái niệm**, không khẳng định API nào cũng thực thi lần lượt giống hệt. Trong JUL, logger, handler, filter và formatter có vai trò cụ thể; Logback/Log4j 2 sử dụng các tên/cấu hình không hoàn toàn giống JUL.

- **Ứng dụng** quyết định sự kiện nào được ghi log, level nào và ngữ cảnh nào được đưa vào message/record.
- **Logger** nhận yêu cầu log, áp dụng ngưỡng/một số quy tắc lọc, có thể truyền tới parent handlers.
- **Handler/Appender** quyết định đưa record tới đích nào và có thể lọc thêm. JUL có ConsoleHandler, FileHandler, StreamHandler và những handler khác.
- **Formatter/Encoder** biến record thành byte hoặc ký tự: một dòng text, XML, JSON hoặc định dạng riêng.
- **Collector/shipper** (nếu dùng) lấy log từ stdout, file hoặc network, thêm metadata, đệm và vận chuyển tới backend.
- **Storage/index** lưu và chuẩn bị để truy vấn theo thời gian, service, level, trace ID và các field khác.
- **Người phân tích** đọc thông tin từ console, file, công cụ tìm kiếm hoặc dashboard.

Cần phân biệt ba mốc: **thời điểm xảy ra sự kiện**, **thời điểm record được tạo/ghi ra**, và **thời điểm backend nhận/hiển thị**. Khi có buffer, batch, retry, hàng đợi hoặc mạng chậm, các mốc này không trùng nhau. Một log xuất hiện muộn không nhất thiết là sự kiện mới xảy ra.

**Không thấy bản ghi** chưa đủ chứng minh sự kiện không xảy ra: mã có thể không gọi logger, level/filter có thể loại record, collector gặp sự cố, retention hết hạn hoặc sampling bỏ bớt sự kiện. **Thấy bản ghi** cũng chưa bảo đảm sự kiện nghiệp vụ đã commit bền vững; log có thể phát trước khi transaction hoàn tất.

## 2. Đọc từng trường của log entry

Xét một dòng minh họa:

~~~text
2026-11-09T10:15:30.123Z | WARNING | demo.checkout | event=payment.timeout requestId=req-7 dependency=payments attempt=1
~~~

| Thành phần | Ý nghĩa | Câu hỏi khi phân tích |
| --- | --- | --- |
| Timestamp | Thời điểm record được gắn thời gian; ở ví dụ là UTC vì có Z | Sự kiện nằm trong khoảng nào? Đồng hồ nguồn có đáng tin? |
| WARNING | Mức severity | Điều gì bất thường? Đã được xử lý hay còn ảnh hưởng? |
| demo.checkout | Tên logger/thành phần phát log | Record xuất phát từ phần nào của hệ thống? |
| event=payment.timeout | Tên sự kiện ổn định trong message | Hoạt động nào timeout? |
| requestId=req-7 | Identifier liên kết | Còn những log nào thuộc cùng một yêu cầu? |
| dependency=payments | Thành phần phụ thuộc liên quan | Lỗi có liên quan dịch vụ ngoài hay không? |
| attempt=1 | Số lần thử | Đây là lần retry nào và kết quả cuối cùng ra sao? |

Trong JUL, **LogRecord** vốn có các metadata như level, logger name, message, instant, parameters và Throwable. Những cặp như requestId, event, durationMs ở ví dụ lại nằm trong **message do lập trình viên tự quy ước**; chúng không mặc nhiên trở thành field riêng của JUL. Khi backend hoặc logging library hỗ trợ structured logging, có thể lưu chúng thành field độc lập để truy vấn chính xác hơn.

Một thông điệp không có ngữ cảnh như “Timeout” có thể là dấu hiệu, nhưng không cho biết request, thao tác hay dependency. Đọc bản ghi hữu ích nghĩa là xác định được **ai/việc gì, điều gì, khi nào, kết quả và tác động**, đồng thời nhận ra dữ liệu nào còn thiếu.

### Timestamp, timezone và thứ tự

- ISO 8601 có timezone rõ ràng (ví dụ Z cho UTC, hoặc +07:00) giúp phối hợp nhiều nguồn. Không coi một chuỗi ngày giờ thiếu timezone là UTC.
- Thống nhất timezone trước khi so sánh: 17:15+07:00 tương ứng 10:15Z trong cùng ngày; đừng ghép timeline từ giờ local và UTC mà không chuẩn hóa.
- Múi giờ và độ phân giải timestamp (giây, mili giây, nano giây) ảnh hưởng độ chính xác, nhất là khi nhiều sự kiện diễn ra gần nhau.
- Log của **một tiến trình ghi tuần tự vào một file** thường dễ xem theo thứ tự ghi. Log từ nhiều máy, nhiều luồng, nhiều buffer hoặc shipper **không tạo thành một thứ tự tổng thể đáng tin chỉ bằng timestamp**.
- Nếu có trace/span ID và trình tự thao tác, dùng quan hệ nghiệp vụ kết hợp timestamp để tái dựng dòng xử lý; cân nhắc lệch đồng hồ.

### Level không tự trả lời “lỗi có nghiêm trọng không”

Trong JUL, các level thông dụng gồm SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST (cùng ALL và OFF để điều khiển ngưỡng). Một số framework khác dùng ERROR/WARN/DEBUG/TRACE. **Không đồng nhất tuyệt đối các tên level giữa framework** khi truy vấn nhiều nguồn.

WARNING có thể mô tả retry được phục hồi; SEVERE có thể mô tả thao tác thất bại thật. INFO có thể chứa “status=503” nếu hệ thống chọn một sự kiện tổng kết vận hành ở mức INFO. Hãy đọc **level cùng event và outcome**, tránh thống kê lỗi chỉ bằng số dòng ERROR hoặc SEVERE.

## 3. Phân biệt định dạng log trước khi parse

### Text một dòng

~~~text
2026-11-09T10:15:30Z | INFO | demo.checkout | event=request.finished requestId=req-7 status=200 durationMs=238
~~~

Ưu điểm: đọc nhanh bằng mắt và công cụ tìm chuỗi. Nhược điểm: nếu delimiter, dấu cách hoặc ký tự đặc biệt không được escape, parser tự chế có thể nhận nhầm ranh giới field. Khi lọc “503”, chuỗi đó có thể là mã HTTP, mã đơn hàng hoặc một phần của URL.

### JSON Lines (mỗi record là một JSON object trên một dòng)

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"checkout","event":"request.finished","requestId":"req-7","status":200,"durationMs":238}
~~~

JSON cho phép truy vấn đúng kiểu trường số (durationMs > 100), nhóm theo service hoặc lấy chính xác requestId. Phải biết schema thực tế và cách collector chuyển đổi (tên trường đôi khi bị thay hoặc chuẩn hóa). Nếu có Throwable/stack trace chứa newline, JSON encoder nên escape phù hợp để mỗi record vẫn là một object; đừng giả định text nhiều dòng đã là JSON Lines hợp lệ.

### XML hoặc text nhiều dòng

JUL **FileHandler mặc định thường dùng XMLFormatter** nếu không đặt formatter khác. Không đọc XML log như thể nó là text key=value, và không mặc định một line là một record. Một bản ghi ngoại lệ có thể trải qua nhiều dòng:

~~~text
2026-11-09T10:15:30Z ERROR checkout: payment failed requestId=req-7
java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:42)
    at com.example.OrderService.pay(OrderService.java:71)
~~~

Đây là **một lỗi và một stack trace minh họa**, không phải ba sự kiện mới. Khi phân tích, cần xác định ranh giới record bằng pattern timestamp/header, parser multiline hoặc định dạng có cấu trúc; đếm mỗi dòng văn bản là một event sẽ thổi phồng số lượng lỗi.

**Quy tắc:** xác định rõ nguồn, encoding (thường UTF-8), formatter, separator, escaping, cấu trúc record và chính sách multiline **trước** khi viết regex hoặc thống kê. Một parser tự chế dùng cho demo dữ liệu kiểm soát không nên áp trực tiếp lên log production không đồng nhất.

## 4. Quy trình điều tra một vấn đề từ log

Một cách làm hiệu quả là bắt đầu từ **triệu chứng có thể kiểm chứng**, rồi thu hẹp dần:

1. **Xác định triệu chứng và phạm vi.** Ví dụ: khoảng 10:15–10:20 UTC, checkout trả nhiều 503, chỉ ở một môi trường hay mọi region? Ghi timezone và nguồn xác nhận (ticket, metric, trace, phản ánh người dùng).
2. **Tìm log ở điểm gần triệu chứng.** Lọc đúng service/environment, khoảng thời gian đủ rộng, request/trace ID hoặc endpoint. Không đọc hàng triệu dòng từ đầu tệp khi đã biết thời gian.
3. **Phân biệt kết quả và nguyên nhân.** “request.finished status=503” nói lên kết quả của yêu cầu; lỗi ở inventory dependency có thể là một mắt xích cần kiểm chứng.
4. **Dùng identifier để dựng đường đi.** Truy mọi log của cùng requestId; nếu nhiều service, ưu tiên traceId/spanId. Kiểm tra lần thử, retry, timeout, fallback và kết quả cuối.
5. **Đặt các mốc trên timeline.** Tìm lần cuối thành công, sự kiện bất thường đầu tiên được quan sát, các thay đổi liên quan (deploy/config/load), thời gian gián đoạn và lúc phục hồi.
6. **Đọc exception và ngữ cảnh.** Tìm cause chain, loại exception, điểm bắt/ném và điều kiện xảy ra; kiểm tra có log lặp cùng exception ở nhiều tầng không.
7. **Kiểm chứng giả thuyết bằng nguồn khác.** So log với metric (tỷ lệ lỗi, p95/p99 latency), trace, trạng thái dependency và thay đổi gần đó; một stack trace đơn lẻ thường chưa đủ.
8. **Đánh giá tác động thực tế.** Bao nhiêu request thất bại, users liên quan theo mức được phép, latency tăng ra sao? Đếm theo request/transaction chứ không đếm mỗi dòng “error”.
9. **Ghi nhận bằng chứng và giới hạn.** Lưu khoảng thời gian, truy vấn, requestId/traceId đã che dữ liệu nhạy cảm, các mốc, kết luận có độ tin cậy và những giả thuyết còn mở.

Có thể lặp lại các bước khi phát hiện thêm manh mối. “Dòng lỗi đầu tiên” có thể là **dấu hiệu đầu tiên có trong log** chứ chưa hẳn là nguyên nhân gốc: ví dụ dependency ngừng phản hồi vì đã quá tải từ nhiều phút trước.

### Đọc dọc theo một request thay vì từng dòng rời

~~~text
10:15:30.010 INFO    event=request.started requestId=req-7
10:15:30.080 WARNING event=payment.timeout requestId=req-7 attempt=1
10:15:30.150 INFO    event=payment.retry_succeeded requestId=req-7 attempt=2
10:15:30.248 INFO    event=request.finished requestId=req-7 status=200 durationMs=238
~~~

Các timestamp trên là **minh họa về timeline**, không phải đầu ra cố định của chương trình ở mục thực hành. Phân tích đúng: có một lần timeout, một lần retry thành công, và kết quả cuối là HTTP 200. **Không kết luận req-7 thất bại chỉ vì có WARNING.** Ngược lại, nếu một request khác có status=503, truy ngược để xem đó là lỗi xử lý, timeout dependency hay quy tắc nghiệp vụ.

## 5. Kỹ thuật tìm kiếm, lọc, nhóm và so sánh

### Lọc theo thời gian, nguồn và mức độ

Ưu tiên tổ hợp điều kiện: time window + service/environment + requestId/traceId hoặc event. Chỉ tìm theo chuỗi “ERROR” có thể bỏ sót sự kiện thất bại được ghi INFO, đồng thời bắt cả chữ “error” trong phần text không mang ý nghĩa level.

Với text log, có thể đọc một đoạn có kiểm soát bằng công cụ hệ điều hành.

**PowerShell** (Windows):

~~~powershell
Get-Content -Path .\app.log -Tail 50
Select-String -Path .\app.log -Pattern 'requestId=req-7'
Select-String -Path .\app.log -Pattern '\bWARNING\b|\bSEVERE\b'
Get-Content -Path .\app.log -Tail 20 -Wait
~~~

Lệnh cuối theo dõi nội dung tệp đang được ghi; dùng Ctrl+C để dừng. Một record multiline sẽ hiển thị nhiều dòng. Các mẫu này dựa trên **định dạng text**, không phân tích schema JSON.

**Bash/GNU tools** (Linux/macOS, khi công cụ có sẵn):

~~~bash
tail -n 50 app.log
grep -n 'requestId=req-7' app.log
grep -E 'WARNING|SEVERE' app.log
tail -n 20 -f app.log
~~~

**Nếu file là JSON Lines** và có công cụ jq:

~~~bash
jq -r 'select(.level == "ERROR") | [.timestamp, .traceId, .message] | @tsv' app.jsonl
jq -r 'select(.event == "request.finished" and (.durationMs > 100)) | [.requestId, .durationMs] | @tsv' app.jsonl
~~~

Đây là cú pháp dành cho JSON có field tương ứng. Với backend tập trung, thường nên dùng query theo **trường có cấu trúc** và filter của backend, thay vì grep trên toàn bộ raw message.

### Nhóm đúng đơn vị phân tích

- **Theo requestId/traceId:** dựng đường đi và kết quả của **một yêu cầu**.
- **Theo event:** đếm số lần request.finished, payment.timeout, retry_succeeded trong một khoảng thời gian.
- **Theo level:** xem phân bố WARNING/SEVERE để tìm dấu hiệu; không thay số đếm request thất bại.
- **Theo service, host, region hoặc version:** kiểm tra lỗi tập trung ở một thành phần hay sau một lần deploy.
- **Theo thời gian:** nhóm vào cửa sổ 1 phút/5 phút để thấy đỉnh tải, tương quan với spike latency.
- **Theo latency/status:** tính tỷ lệ status 5xx, thời lượng xử lý, p95/p99 (khi số lượng mẫu đủ và dữ liệu đáng tin).

Phải chọn **mẫu số** trước khi tính tỷ lệ. Ví dụ tỷ lệ thất bại của request cần số request thất bại chia tổng request tương ứng; không lấy số dòng SEVERE chia tổng dòng INFO. Retry, log trùng, sampling và log bị mất đều có thể làm phép đếm record lệch khỏi số giao dịch.

### Tìm mối quan hệ thay vì chỉ tìm từ khóa

Một mẫu thường gặp là event A xảy ra rồi event B xuất hiện. Nếu mọi timeout đều đi sau một deploy, đây là **tương quan** cần điều tra, chưa đủ chứng minh deploy là nguyên nhân. Xem version, thời điểm bắt đầu, các thay đổi cấu hình, tình trạng dependency và đối chứng ở nhóm không ảnh hưởng để kiểm chứng.

## 6. Thực hành Java 17+: tạo log, đọc file, phân tích sự kiện

Ví dụ này minh họa một pipeline nhỏ: **Logger → FileHandler → Formatter → file UTF-8 → parser → truy vấn bằng Stream API**. Chương trình ghi chín record kiểm soát, đóng handler để flush, đọc file thành đối tượng Entry, đếm severity, tái dựng request req-7, tìm yêu cầu chậm và đếm HTTP 5xx.

Để đầu ra dễ kiểm chứng, chương trình lấy timestamp thật của mỗi LogRecord, nhưng chỉ **in kết quả tổng hợp xác định trước** ra stdout. Tệp log tạm được tạo trong thư mục hệ thống và xóa sau khi đọc; thay đổi bước xóa nếu muốn giữ file để mở bằng editor.

Tạo tệp **LogReadAnalyzeDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogReadAnalyzeDemo {
    record Entry(Instant timestamp, Level level, String logger,
                 Map<String, String> fields) {}

    static Entry parse(String line) {
        String[] columns = line.split(" \\| ", 4);
        if (columns.length != 4) {
            throw new IllegalArgumentException("Unexpected log format");
        }
        Map<String, String> fields = new LinkedHashMap<>();
        for (String token : columns[3].split(" ")) {
            int equals = token.indexOf('=');
            if (equals > 0) {
                fields.put(token.substring(0, equals),
                        token.substring(equals + 1));
            }
        }
        return new Entry(Instant.parse(columns[0]),
                Level.parse(columns[1]), columns[2], fields);
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("log-read-demo-", ".log");
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        FileHandler handler = new FileHandler(path.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getInstant() + " | "
                        + record.getLevel().getName() + " | "
                        + record.getLoggerName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            logger.info("event=request.started requestId=req-7 path=/checkout");
            logger.warning("event=payment.timeout requestId=req-7 attempt=1");
            logger.info("event=payment.retry_succeeded requestId=req-7 attempt=2");
            logger.info("event=request.finished requestId=req-7 status=200 durationMs=238");
            logger.info("event=request.started requestId=req-8 path=/catalog");
            logger.info("event=request.finished requestId=req-8 status=200 durationMs=12");
            logger.info("event=request.started requestId=req-9 path=/checkout");
            logger.severe("event=inventory.unavailable requestId=req-9 dependency=inventory");
            logger.info("event=request.finished requestId=req-9 status=503 durationMs=115");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<Entry> entries;
        try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
            entries = lines.map(LogReadAnalyzeDemo::parse).toList();
        } finally {
            Files.deleteIfExists(path);
        }

        long warningCount = entries.stream()
                .filter(entry -> entry.level().equals(Level.WARNING)).count();
        long severeCount = entries.stream()
                .filter(entry -> entry.level().equals(Level.SEVERE)).count();

        List<String> requestEvents = entries.stream()
                .filter(entry -> "req-7".equals(entry.fields().get("requestId")))
                .map(entry -> entry.fields().get("event")).toList();

        List<String> slowRequests = entries.stream()
                .filter(entry -> "request.finished".equals(entry.fields().get("event")))
                .filter(entry -> Integer.parseInt(
                        entry.fields().getOrDefault("durationMs", "0")) > 100)
                .map(entry -> entry.fields().get("requestId")).toList();

        long serverErrors = entries.stream()
                .filter(entry -> "request.finished".equals(entry.fields().get("event")))
                .filter(entry -> Integer.parseInt(
                        entry.fields().getOrDefault("status", "0")) >= 500)
                .count();

        System.out.println("totalRecords=" + entries.size());
        System.out.println("WARNING=" + warningCount + " SEVERE=" + severeCount);
        System.out.println("req-7=" + String.join(" -> ", requestEvents));
        System.out.println("slow(>100ms)=" + String.join(",", slowRequests));
        System.out.println("http5xx=" + serverErrors);
    }
}
~~~

Chạy bằng **JDK 17 trở lên** ở thư mục chứa file:

~~~bash
javac LogReadAnalyzeDemo.java
java LogReadAnalyzeDemo
~~~

**Stdout chính xác** với dữ liệu mẫu đã tạo trong code:

~~~text
totalRecords=9
WARNING=1 SEVERE=1
req-7=request.started -> payment.timeout -> payment.retry_succeeded -> request.finished
slow(>100ms)=req-7,req-9
http5xx=1
~~~

Giải thích theo từng phần:

1. **FileHandler** tạo file log và tự xử lý tài nguyên liên quan; **setEncoding("UTF-8")** thống nhất encoding. Việc tắt parent handlers ngăn record xuất ra console thêm một lần qua root logger trong demo.
2. **Formatter** chuyển mỗi record thành một dòng có bốn trường phân cách bằng dấu ** | **: timestamp UTC dạng ISO-8601, level, logger name và message. Vì message của ví dụ không có newline hoặc delimiter ** | **, một record đúng bằng một dòng.
3. **Đóng handler trước khi đọc** giúp flush các log đã ghi và giải phóng lock file. Tệp tạm được xóa sau phân tích để không để lại file phát sinh.
4. **parse(...)** chia thành đúng bốn phần; message sau đó được tách thành token dạng key=value. Entry giữ Instant, Level, logger và map field để truy vấn theo thuộc tính thay vì tìm chuỗi tùy ý.
5. **Tổng hợp theo level:** có một payment.timeout ở WARNING và một inventory.unavailable ở SEVERE. Đây là số **record**, không phải số request lỗi.
6. **Liên kết req-7:** một request có chuỗi started → timeout → retry_succeeded → finished. Kết quả cuối **status=200** nằm trong bản ghi request.finished.
7. **Tìm request chậm:** có hai bản ghi request.finished mang durationMs vượt **100** (req-7: 238 ms, req-9: 115 ms).
8. **Đếm lỗi HTTP 5xx:** trong ba request.finished, chỉ req-9 có status=503; bộ đếm là **1**. Vì dataset quá nhỏ, không suy ra chất lượng của hệ thống production.
9. **Phạm vi parser:** parser trên chỉ đúng với message được kiểm soát chứa token key=value **không có khoảng trắng, dấu bằng không được escape hay ký tự newline**. Với log thật, cần schema, encoder, parser và xử lý escape/multiline đúng chuẩn; không dùng đoạn split đơn giản để phân tích payload không tin cậy.

Chương trình dùng JUL nhưng không dùng thư viện ngoài JDK. **Record của Java** (Entry) là một kiểu Java từ Java 16, dùng ổn định ở Java 17. **Files.lines** trả stream đọc file, nên chương trình sử dụng try-with-resources để đóng stream.

### Đọc các kết quả của demo như một điều tra nhỏ

| Request | Chuỗi sự kiện được ghi | Kết quả cuối | Cách đọc |
| --- | --- | --- | --- |
| req-7 | start → payment timeout → retry succeeded → finish | 200, 238 ms | Có bất thường đã phục hồi; request vẫn thành công nhưng chậm |
| req-8 | start → finish | 200, 12 ms | Yêu cầu thành công trong dữ liệu mẫu |
| req-9 | start → inventory unavailable → finish | 503, 115 ms | Yêu cầu kết thúc lỗi phía server, cần kiểm tra dependency inventory |

Đừng gán “sự cố độc lập” cho từng log WARNING/SEVERE. req-7 có WARNING nhưng thành công; req-9 có SEVERE và status 503. Từ bảng, ta có **giả thuyết** dependency inventory liên quan req-9, nhưng cần thêm dữ liệu của dependency, metrics và trace trước khi xác nhận nguyên nhân gốc.

## 7. Phân tích exception và stack trace

Khi đọc lỗi có Throwable, xem **loại exception, cause chain, stack trace, hành động gây lỗi và xử lý tiếp theo**. Bắt đầu từ message ở ranh giới nghiệp vụ (“payment request failed”) rồi đi vào nơi exception phát sinh. Với các lỗi được wrap nhiều tầng, **Caused by** thường cho biết lỗi bên trong, nhưng không mặc định mọi “Caused by” là nguyên nhân gốc hệ thống: timeout có thể do mạng chậm, quá tải, cấu hình, circuit breaker hoặc nhiều yếu tố khác.

Ví dụ minh họa:

~~~text
2026-11-09T10:15:30Z SEVERE event=payment.failed requestId=req-12
java.lang.IllegalStateException: Payment service unavailable
    at com.example.PaymentService.charge(PaymentService.java:81)
Caused by: java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:46)
~~~

Cách đọc: **PaymentService** không hoàn thành thao tác; **SocketTimeoutException** cho biết lời gọi downstream hết thời gian đọc; cần xem host, endpoint, duration, retry, traces và tình trạng dependency. Các dòng stack trace thuộc **cùng một record lỗi**, không nên đếm thành nhiều lần lỗi độc lập. Khung stack không có nghĩa tất cả phương thức đều “gây lỗi”.

Các kiểm tra cần nhớ:

- Một exception có thể bị ghi nhiều lần khi code log rồi rethrow qua các tầng, làm phồng thống kê.
- Không được tin mọi thông điệp exception đã an toàn: nó có thể chứa SQL, URL, header, token hoặc dữ liệu cá nhân.
- Stack trace bị cắt/truncate sẽ mất một phần bằng chứng; ghi nhận giới hạn trước khi kết luận.
- Exception được bắt và xử lý hợp lệ chưa chắc là sự cố vận hành cần cảnh báo.
- Nếu một dòng stack trace không có timestamp/header, đừng để parser đếm nó như log event mới.

## 8. Các vấn đề phân tích thường gặp ở hệ thống nhiều service

### Correlation và bất đồng bộ

requestId phù hợp để nối log trong một request tại service; **traceId/spanId** phù hợp hơn để theo dõi đường xử lý qua nhiều service. Cần truyền context qua ranh giới thread, executor, message queue hoặc async callback. Trong Java, thông tin gắn bằng ThreadLocal không tự động đi qua mọi luồng/tác vụ, và context bị rò nếu không dọn trong thread pool. Nếu thiếu correlation ID, hãy bổ sung công cụ trace và ghi nhận rằng việc ghép log theo timestamp gần nhau chỉ mang tính suy đoán.

### Trễ vận chuyển, log bị mất, log lặp

Collector có thể đọc file theo batch, thất bại rồi retry; buffering khiến log tới backend muộn, retry có thể nhân đôi record. Rotation/retention có thể khiến thiếu một đoạn file; sampling hoặc filter chỉ giữ một phần traffic. Hãy so **event time** với **ingestion time**, kiểm tra nguồn và số lượng record, đừng kết luận event chưa xảy ra chỉ vì chưa được index.

### Đa dạng format và phiên bản

Các service có thể dùng JUL, Log4j 2, Logback, HTTP access log hoặc JSON encoder với field khác nhau. Một bản ghi có field **time**, bản ghi khác dùng **timestamp**; level có thể là ERROR hoặc SEVERE; duration có thể tính theo ms, µs hoặc ns. Trước khi union dữ liệu, **chuẩn hóa tên field, timezone, đơn vị và ngữ nghĩa event**, nếu không dashboard sẽ phân tích sai.

### Mức tin cậy của dữ liệu log

Một message do lập trình viên viết có thể sai thời điểm (“success” trước khi commit), thiếu ngữ cảnh, bị cắt, hoặc phản ánh một lần retry chưa phải kết quả cuối. Dùng log để **hình thành và kiểm chứng giả thuyết**, kết hợp trạng thái nghiệp vụ, metrics, traces, cơ sở dữ liệu và kết quả bên ngoài nếu cần.

## 9. Bảo mật và hiệu năng khi đọc log

**Đọc log cũng là thao tác tiếp xúc dữ liệu nhạy cảm.** Người phân tích cần được cấp quyền đúng môi trường và chỉ truy xuất dữ liệu phục vụ điều tra. Không đưa log chứa access token, mật khẩu, secret, session cookie, payment card hoặc payload cá nhân lên dịch vụ không được phép. Khi chia sẻ log trong issue hay chat, loại bỏ/che thông tin nhạy cảm, kể cả trong stack trace và URL query.

Khi dùng công cụ tìm kiếm hoặc hiển thị:

- Dữ liệu do người dùng kiểm soát có thể chứa newline và ký tự điều khiển để giả mạo log (log injection). Chỉ tin metadata từ pipeline đã được parse/escape đúng.
- Regex trên log khổng lồ hoặc mẫu regex không tối ưu có thể gây chi phí cao; giới hạn time window/service, ưu tiên field index và tránh quét vô hạn.
- Không dùng tất cả record ở level chi tiết để suy biến chất lượng hệ thống khi một phần bị sampling. Mẫu được lấy không đại diện có thể làm sai tỷ lệ.
- Cẩn thận với logging vòng lặp và request payload lớn: ảnh hưởng I/O, disk, ingestion bill và retention. Dùng metrics cho thống kê lặp lại, traces cho chuỗi xử lý; log tập trung vào ngữ cảnh sự kiện.
- Khi chạy truy vấn trên backend, để ý độ trễ cập nhật index và timezone của giao diện; query “last 15 minutes” trên backend có thể phụ thuộc ingestion timestamp.

## 10. Lỗi phân tích thường gặp và cách sửa

| Nhận định/việc làm sai | Hướng sửa |
| --- | --- |
| “Không có log tức là không có lỗi.” | Kiểm tra logger level/filter, collector, loss, sampling và retention. |
| “Một dòng trong file là một record.” | Xác định JSON/XML/multiline stack trace trước khi đếm. |
| “Một WARNING là một request thất bại.” | Nối cùng requestId và xem trạng thái cuối cùng. |
| “Đếm SEVERE để ra tỷ lệ lỗi.” | Đếm kết quả theo request/operation, có mẫu số xác định. |
| “Sắp tất cả log từ nhiều máy theo timestamp là thứ tự tuyệt đối.” | Chuẩn hóa timezone, tính clock skew và dùng trace/quan hệ nghiệp vụ. |
| “Có SocketTimeoutException nên chắc chắn mạng hỏng.” | Kiểm tra dependency, saturation, timeout config, metric và thời gian chờ. |
| “Lấy full payload để debug nhanh.” | Dùng field đã cho phép, identifier và chính sách redaction. |
| “Parse bằng split dấu cách cho mọi message.” | Dùng parser có schema/escape và hỗ trợ multiline phù hợp. |
| “Dòng log đầu tiên là nguyên nhân gốc.” | Tái dựng timeline, xem thay đổi hệ thống và kiểm chứng bằng nguồn khác. |
| “Log thành công nghĩa là transaction đã commit.” | Xác định vị trí log so với commit/ack và bằng chứng trạng thái thực. |

## 11. Checklist khi đọc và phân tích log

1. Xác nhận **sự kiện/tình huống** cần điều tra, khoảng thời gian, múi giờ và môi trường.
2. Xác định **nguồn log và đường đi**: service/logger → handler/file/stdout → collector → backend.
3. Nhận diện **format, encoding, field/schema, timezone, multiline và timestamp semantics**.
4. Lọc theo **service, version, time window, event, requestId/traceId** trước khi mở rộng phạm vi.
5. Đọc **level + message + outcome + context** cùng nhau; phân biệt dấu hiệu và kết quả cuối.
6. Nối các bản ghi thành **timeline**, chú ý retry, timeout, async, duplicate và clock skew.
7. Xem **Throwable/cause chain**, kiểm chứng với metrics/traces và dependency khi tìm nguyên nhân.
8. Khi thống kê, xác định rõ **đơn vị đếm, mẫu số, sampling và dữ liệu thiếu**.
9. Che dữ liệu nhạy cảm, giới hạn phạm vi truy vấn và lưu lại bằng chứng đủ để người khác tái hiện.
10. Viết kết luận gắn với bằng chứng thực tế; ghi rõ điều còn chưa chắc chắn.

## Câu hỏi tự kiểm tra

**1.** Có 20 dòng SEVERE trong một phút. Có thể kết luận 20 request thất bại không?  
**Trả lời:** Không. Một request có thể ghi nhiều dòng SEVERE, log có thể lặp qua retry/collector; cần đếm các kết quả cuối theo request hoặc transaction.

**2.** Một record có timestamp 17:15:00+07:00, record khác là 10:15:00Z; có phải hai thời điểm khác nhau?  
**Trả lời:** Không, đó là cùng một thời điểm UTC nếu hai clock đúng.

**3.** Vì sao không nên parse Java stack trace bằng cách đếm mỗi dòng?  
**Trả lời:** Stack trace của một Throwable thường gồm nhiều dòng thuộc một record; đếm từng dòng sẽ tạo event giả và làm sai thống kê.

**4.** Trong demo Java, vì sao req-7 có WARNING mà vẫn được coi là request thành công?  
**Trả lời:** payment.timeout ở attempt=1 đã được retry và event request.finished cuối cùng có status=200. WARNING diễn tả bất thường ở một bước, không tự quyết định kết quả của request.

**5.** Nếu backend chưa có log mới, bước kiểm tra nào hữu ích?  
**Trả lời:** Xem logger/handler level và filter, việc ghi stdout/file, collector/shipper, thời điểm ingest, retention, sampling, và quyền truy vấn. Việc thiếu log chưa đủ kết luận không có sự kiện.

**Ghi nhớ:** Đọc log là **chuyển các record rời thành bức tranh về một chuỗi sự kiện có kiểm chứng**. Hãy hiểu đường đi và format của dữ liệu, liên kết bằng context, giữ đúng thời gian và đơn vị đếm, rồi so bằng chứng log với metrics/traces/trạng thái nghiệp vụ trước khi kết luận nguyên nhân.
