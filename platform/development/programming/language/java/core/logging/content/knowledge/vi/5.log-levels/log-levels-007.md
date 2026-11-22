# Chọn level phù hợp trong Java Logging

**Log level** là mức phân loại mức độ quan trọng hoặc mục đích của một sự kiện log. Chọn level phù hợp giúp người vận hành phân biệt diễn biến bình thường, dấu hiệu bất thường và thất bại thật sự; đồng thời quyết định lượng log xuất hiện ở từng môi trường. Một sự kiện được đặt sai level có thể khiến lỗi bị bỏ sót vì đang tắt DEBUG, hoặc khiến hệ thống cảnh báo liên tục dù mọi yêu cầu vẫn thành công.

Trong Java, tên level khác nhau giữa `java.util.logging` (**JUL**) và các API/backend như SLF4J, Logback, Log4j 2. Tuy nhiên, nguyên tắc chung là **xét kết quả thực tế, mức ảnh hưởng và nhu cầu điều tra** trước khi chọn mức ghi.

## 1. Level trả lời câu hỏi gì?

Trước khi viết một lệnh logging, hãy xác định:

1. **Sự kiện có được dự kiến trong luồng bình thường không?** Ví dụ, người dùng nhập sai mật khẩu hoặc yêu cầu tài nguyên không tồn tại là những tình huống ứng dụng có thể chủ động xử lý.
2. **Hoạt động có đạt kết quả mong muốn không?** Một lần thử gọi API bị timeout nhưng retry thành công khác với yêu cầu cuối cùng thất bại.
3. **Có suy giảm dịch vụ hoặc dấu hiệu rủi ro cần người vận hành chú ý không?** Ví dụ, phải dùng fallback, hàng đợi gần đầy, tài nguyên sắp cạn.
4. **Dữ liệu này có cần xuất hiện khi production hoạt động bình thường không?** Các bước kiểm tra biến trung gian thường chỉ cần khi bật chẩn đoán.
5. **Ai sẽ hành động khi đọc dòng log?** Level nên giúp người chịu trách nhiệm quyết định khi nào cần điều tra, thay vì chỉ biểu thị cảm xúc của tác giả.

**Không chọn level chỉ dựa vào từ ngữ** trong message hoặc loại Java exception. Một `IllegalArgumentException` phát sinh từ input không hợp lệ có thể là lỗi dự kiến; một giá trị trả về không ném exception vẫn có thể báo hỏng nghiệp vụ nghiêm trọng.

## 2. Các mức level thường gặp

| Mục đích | SLF4J / Logback thường gặp | JUL gần tương ứng | Nguyên tắc lựa chọn |
| --- | --- | --- | --- |
| Theo dõi rất chi tiết từng bước | `TRACE` | `FINER` / `FINEST` | Chỉ để điều tra sâu về luồng xử lý; khối lượng lớn, thường tắt trên production. |
| Chẩn đoán logic và trạng thái kỹ thuật | `DEBUG` | `FINE` | Giá trị trung gian, quyết định nhánh, retry riêng lẻ; có thể tắt khi hoạt động bình thường. |
| Diễn biến bình thường quan trọng | `INFO` | `INFO` | Khởi động hoàn tất, công việc quan trọng thành công, thay đổi trạng thái có ích khi vận hành. |
| Bất thường vẫn xử lý được hoặc cần theo dõi | `WARN` | `WARNING` | Fallback, tình trạng suy giảm, gần ngưỡng tài nguyên, retry nhiều lần; cần ngữ cảnh để đánh giá. |
| Một thao tác hoặc thành phần thật sự thất bại | `ERROR` | `SEVERE` | Yêu cầu quan trọng không hoàn tất, hệ thống không khởi động được, lỗi phụ thuộc ảnh hưởng đến kết quả cuối cùng. |

Đây chỉ là **đối chiếu ý nghĩa gần đúng**. JUL có các mức `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`; `ALL` và `OFF` được dùng chủ yếu cho cấu hình ngưỡng. `CONFIG` phục vụ thông tin cấu hình và không có mức tương ứng một-một trong SLF4J. Log4j 2 có thể cung cấp `FATAL`; SLF4J API thông dụng không định nghĩa một phương thức `fatal()` tương ứng. Không sao chép tên level của backend này sang backend khác mà không kiểm tra API.

Trong JUL, các mức có giá trị ưu tiên từ cao xuống thấp: `SEVERE (1000)`, `WARNING (900)`, `INFO (800)`, `CONFIG (700)`, `FINE (500)`, `FINER (400)`, `FINEST (300)`. Ngưỡng `INFO` thông thường nhận các mức `INFO`, `WARNING` và `SEVERE`, nhưng loại `CONFIG`/`FINE`/`FINER`/`FINEST`. Các level tùy biến có thể tồn tại, nên không nên hiểu đây là danh sách duy nhất của mọi ứng dụng.

## 3. Quy trình quyết định level cho một sự kiện

Có thể dùng cây quyết định sau để thảo luận trong code review. Các mức gợi ý cần được điều chỉnh theo quy ước của hệ thống và yêu cầu vận hành.

```text
Sự kiện vừa xảy ra
  |
  +-- Chỉ là trạng thái trung gian phục vụ chẩn đoán?
  |       +-- Có -> DEBUG/FINE; cực chi tiết -> TRACE/FINER/FINEST
  |
  +-- Hành vi dự kiến, được xử lý đúng hợp đồng?
  |       +-- Có -> Không bắt buộc log; INFO nếu là mốc quan trọng,
  |                hoặc DEBUG/FINE/access log nếu chỉ là chi tiết thông thường
  |
  +-- Có bất thường, fallback hoặc suy giảm cần chú ý?
  |       +-- Có, thao tác vẫn thành công -> WARN/WARNING khi cần theo dõi
  |                (hoặc INFO/DEBUG nếu fallback là hoạt động thường lệ)
  |
  +-- Kết quả cuối cùng thất bại ngoài mong đợi?
          +-- Có -> ERROR/SEVERE nếu ảnh hưởng đến thao tác/thành phần
          +-- Không -> INFO cho kết quả vận hành đáng ghi nhận,
                       hoặc không log nếu không tạo giá trị
```

Cây này không phải quy tắc máy móc: một sự kiện bảo mật có thể cần kênh audit riêng bất kể level, còn lỗi người dùng có thể là kết quả từ chối hợp lệ theo hợp đồng. **Mức ảnh hưởng phải được đánh giá ở ranh giới nghiệp vụ**, nơi biết yêu cầu đã thành công, được phục hồi hay thất bại.

### 3.1. Chọn INFO cho cột mốc đáng ghi nhận

`INFO` phù hợp khi hoạt động diễn ra đúng kỳ vọng và việc ghi nhận sự kiện giúp vận hành, ví dụ:

- Dịch vụ khởi động xong và đã sẵn sàng phục vụ.
- Một batch job quan trọng hoàn tất với số lượng bản ghi đã xử lý.
- Một tác vụ quản trị được phép thay đổi trạng thái cấu hình.
- Một yêu cầu quan trọng hoàn thành và cần khả năng truy vết ở mức nghiệp vụ.

Không nhất thiết ghi `INFO` cho mỗi method được gọi, mỗi lần kiểm tra field hoặc mọi HTTP request thành công. Với dịch vụ lưu lượng lớn, log chi tiết request có thể thuộc access log được quản lý riêng, metric hoặc trace. Một dòng `INFO` cho mọi sự kiện nhỏ có thể khiến log hữu ích bị chìm trong nhiễu.

**Ví dụ tốt:** `event=batch.completed jobId=job-9 processed=1200 failed=0 durationMs=2400`. Đây là kết quả cuối cùng và có bối cảnh rõ.

### 3.2. Chọn WARN/WARNING cho điều bất thường chưa gây thất bại cuối cùng

`WARN`/`WARNING` biểu thị tình huống không hoàn toàn bình thường, có nguy cơ hoặc cần quan sát, dù chương trình vẫn phục vụ được:

- Phải chuyển sang bản sao dự phòng khi kho dữ liệu chính tạm thời không khả dụng.
- Một lần gọi dependency quá chậm, đã retry và thành công, nhưng tổng số lần retry tăng đáng kể.
- Hàng đợi hoặc bộ nhớ gần ngưỡng đã được xác định là đáng chú ý.
- Nhận cấu hình không tối ưu nhưng có giá trị dự phòng hợp lệ.

Nếu fallback là cơ chế thông thường, diễn ra liên tục theo thiết kế và không ảnh hưởng dịch vụ, ghi WARN cho mọi lượt có thể gây cảnh báo giả. Có thể chọn INFO/DEBUG cùng metric tổng hợp và một WARN khi tỷ lệ suy giảm vượt ngưỡng. Tên level không thay thế định nghĩa ngưỡng cảnh báo và chính sách quan sát của hệ thống.

**Ví dụ tốt:** `event=inventory.fallback requestId=req-12 strategy=cache reason=upstream_timeout outcome=recovered`.

### 3.3. Chọn ERROR/SEVERE cho thất bại có tác động thật

`ERROR`/`SEVERE` phù hợp khi **đơn vị công việc cuối cùng không thể hoàn tất** hoặc thành phần không thể cung cấp chức năng bắt buộc:

- Ứng dụng không thể khởi động vì thiếu cấu hình thiết yếu.
- Job kết thúc thất bại sau số lần retry cho phép.
- Giao dịch thanh toán không thể hoàn tất do hệ thống phụ thuộc ngừng đáp ứng.
- Dịch vụ mất khả năng xử lý một chức năng bắt buộc và không có fallback hợp lệ.

Ghi lỗi ở nơi có đủ bối cảnh về `operation`, `outcome`, `errorCode` và `requestId`. Với Java exception bất ngờ, lưu `Throwable` để có stack trace thay vì chỉ `ex.getMessage()`. Một lỗi đã được phục hồi có thể phù hợp với WARN hoặc DEBUG hơn ERROR, vì kết quả chung vẫn thành công.

**Ví dụ tốt:** `event=payment.failed requestId=req-12 paymentId=pay-8 errorCode=UPSTREAM_TIMEOUT attempts=3 outcome=failed` (kèm `Throwable` khi cần).

### 3.4. Chọn DEBUG/FINE và TRACE/FINER/FINEST cho chẩn đoán

`DEBUG/FINE` dành cho các thông tin cần khi điều tra một luồng xử lý cụ thể: quyết định dùng cache hay database, mapping một trạng thái, số phần tử đầu vào sau validation, nhánh thuật toán được chọn.

`TRACE/FINER/FINEST` hữu ích khi cần mức chi tiết lớn hơn: bước tuần tự trong parser, từng phase nhỏ của thuật toán hoặc các thông tin chẩn đoán chuyên sâu. Không đưa toàn bộ payload hay dữ liệu nhạy cảm vào những mức này với giả định rằng “vì mặc định tắt nên an toàn”.

**Ví dụ:** `event=pricing.rule_selected ruleId=rule-3 branch=member_discount` ở FINE; chỉ bật có kiểm soát cho component đang điều tra.

## 4. Tình huống thực tế: cùng một lỗi kỹ thuật có thể cần level khác nhau

| Tình huống | Kết quả cuối cùng | Level tham khảo | Lý do |
| --- | --- | --- | --- |
| Server khởi động thành công | Sẵn sàng phục vụ | `INFO` | Mốc vòng đời đáng ghi lại. |
| Sự kiện thay đổi state của đơn hàng quan trọng | Xử lý thành công | `INFO`, tùy lưu lượng | Có ích để điều tra dòng nghiệp vụ, nếu không quá dày. |
| Kiểm tra từng trường JSON khi parse | Bình thường | `DEBUG/FINE` hoặc không log | Chi tiết triển khai, tần suất cao. |
| Người dùng gửi dữ liệu sai định dạng, API trả 400 đúng hợp đồng | Bị từ chối như dự kiến | Access log, `DEBUG` hoặc `INFO` tùy chính sách | Không tự động biến lỗi client thành sự cố server. |
| Một request nhận 404 do đường dẫn không tồn tại | Bị từ chối theo contract | Access log/`DEBUG` tùy chính sách | Không nhất thiết là lỗi hệ thống. |
| Lần gọi kho hàng timeout, retry sau đó thành công | Request thành công | `DEBUG` mỗi attempt; `WARN` khi hiện tượng bất thường đáng chú ý | Phân biệt lỗi của một lần thử với kết quả toàn yêu cầu. |
| Phải dùng cache dự phòng vì dịch vụ chính lỗi | Phục hồi, nhưng suy giảm | `WARN/WARNING` nếu cần quan sát | Có fallback, chưa thất bại cuối cùng. |
| Job thất bại sau tất cả retry | Job thất bại | `ERROR/SEVERE` | Cần điều tra và xử lý hậu quả. |
| Kết nối cơ sở dữ liệu không tạo được khi startup | Dịch vụ không sẵn sàng | `ERROR/SEVERE` | Chặn khả năng phục vụ. |
| Một lần login sai mật khẩu | Từ chối dự kiến | Security event/audit theo chính sách, `INFO`/`DEBUG` ở app log tùy nhu cầu | Không mặc định `ERROR` cho mỗi lần nhập sai; tránh tiết lộ danh tính/bí mật. |
| Nhiều lần đăng nhập thất bại bất thường | Có thể là rủi ro an ninh | Sự kiện an ninh riêng + cảnh báo theo quy tắc phát hiện | Đánh giá theo mẫu và ngữ cảnh, không chỉ mức severity của từng request. |
| Latency tăng trên nhiều request | Dịch vụ suy giảm | Metric và alert; có thể `WARN` cho chuyển trạng thái vượt ngưỡng | Log từng request chậm không thay thế SLO/metric. |
| Một exception đã được bắt và trả về fallback hợp lệ | Xử lý thành công | `DEBUG` hoặc `WARN` nếu cần chú ý | Không log `ERROR` chỉ vì có stack trace. |

Bảng là **hướng dẫn lựa chọn**, không phải luật bắt buộc. Đội ngũ nên đặt tiêu chí riêng theo mức độ ảnh hưởng của tính năng, đối tượng cần thông báo, độ thường xuyên, yêu cầu audit và chi phí vận hành.

## 5. Retry, fallback và exception: tránh nhầm mức của “lần thử” với “kết quả”

Xét việc gọi dịch vụ thanh toán với tối đa ba lần thử:

```text
attempt=1 -> timeout
attempt=2 -> timeout
attempt=3 -> success
kết quả cuối cùng -> thanh toán thành công
```

Nếu mỗi timeout đều ghi ERROR với stack trace đầy đủ, hệ thống cảnh báo có thể báo ba lỗi nghiêm trọng trong khi yêu cầu cuối cùng thành công. Thay vào đó, có thể:

- Ghi từng attempt ở `DEBUG/FINE` kèm `attempt`, `maxAttempts` và nguyên nhân phân loại được.
- Ghi `WARNING` nếu retry nhiều lần là dấu hiệu bất thường đáng chú ý hoặc làm tăng độ trễ.
- Ghi `INFO` cho kết quả nghiệp vụ thành công nếu loại event này có giá trị vận hành.
- Ghi `ERROR/SEVERE` khi **tất cả lần thử thất bại** và thao tác cuối cùng không đáp ứng hợp đồng.

Tuy nhiên, nếu retry khiến kết quả trùng giao dịch, mất dữ liệu hoặc vi phạm cam kết, severity có thể cao hơn dù có lần thử thành công; phải đánh giá hậu quả thực tế.

### Ghi Throwable tại nơi chịu trách nhiệm

Với JUL, ví dụ xử lý một thất bại cuối cùng:

```java
// Đoạn mã minh họa trong một method; giả sử LOG, requestId đã tồn tại.
try {
    performPayment();
} catch (RuntimeException error) {
    LOG.log(
        java.util.logging.Level.SEVERE,
        "event=payment.failed requestId=" + requestId,
        error
    );
    throw error;
}
```

Ví dụ trên **không phải chương trình độc lập**: `performPayment()` là phương thức của ứng dụng. Khi truyền `Throwable` vào overload `log(Level, String, Throwable)`, record giữ thông tin exception và handler/formatter phù hợp có thể xuất stack trace. Khi dùng `error.getMessage()` đơn lẻ, nguồn lỗi và stack trace dễ bị mất.

Chỉ log rồi ném lại ở đây nếu tầng này chịu trách nhiệm ghi nhận lỗi. Nếu controller hoặc exception handler cũng log cùng một exception, nhiều bản ghi ERROR giống nhau sẽ xuất hiện. Nên xác định ranh giới chịu trách nhiệm chính và dùng mã lỗi, correlation ID để liên hệ các sự kiện qua các tầng.

## 6. Level trong JUL: ngưỡng logger và ngưỡng handler đều có tác dụng

**Level của record** (gắn vào từng sự kiện) và **ngưỡng cho phép xuất log** (cấu hình) là hai khái niệm khác nhau. Chỉ viết `logger.fine(...)` không đảm bảo sẽ thấy một dòng FINE trong console.

Trong JUL, một event phải đi qua ít nhất hai bước kiểm soát:

```text
Call logger.log(Level, message)
             |
    Logger có cho phép level?
          /       \
        không      có
         |          |
       bỏ qua   LogRecord đến handler
                    |
          Handler có cho phép level?
                /       \
             không       có
               |          |
             bỏ qua   format -> output
```

Cấu hình filter tùy logger/handler có thể tạo thêm bước lọc. Record cũng có thể được chuyển đến handler của logger cha, tùy `useParentHandlers`, nhưng **level của parent logger không nhất thiết được dùng để lọc lại record đã được logger con chấp nhận trên đường truyền đến parent handler**. Vì thế cần hiểu cấp nào quyết định ngưỡng và handler thực tế đang làm gì.

Ví dụ:

- Logger `INFO`, handler `ALL`: record `FINE` bị logger loại; `INFO/WARNING/SEVERE` có thể đến handler.
- Logger `FINE`, handler `INFO`: logger cho phép FINE, nhưng handler loại FINE.
- Logger `FINE`, handler `ALL`: FINE có thể xuất hiện nếu không bị filter khác chặn.
- Logger có `level=null`: lấy level hiệu lực từ logger cha gần nhất có level xác định; không có nghĩa là cho phép mọi mức.

Trong SLF4J, việc bật level và đích xuất phụ thuộc backend/provider, vì facade `LoggerFactory` chỉ là điểm gọi API. Cấu hình `logging.properties` của JUL không tự điều khiển các logger được phục vụ bởi Logback hoặc Log4j 2.

## 7. Ví dụ Java 17 hoàn chỉnh: chọn level và nhìn thấy các ngưỡng lọc

Ví dụ sử dụng JUL, không yêu cầu thư viện ngoài JDK. Để stdout ổn định trên các máy, chương trình tự cấu hình một handler xuất ra `System.out`, bỏ formatter mặc định có timestamp và tắt parent handlers.

Lưu vào tệp **`LogLevelSelectionDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogLevelSelectionDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            // Level logger đang là INFO nên FINE bị loại.
            logger.fine("event=diagnostic.dropped_by_logger");

            // Các event sau mô phỏng những tình huống độc lập.
            logger.info("event=service.ready");
            logger.log(
                    Level.WARNING,
                    "event=inventory.fallback requestId={0}",
                    "req-12"
            );
            logger.log(
                    Level.SEVERE,
                    "event=job.failed jobId={0} reason={1}",
                    new Object[]{"job-9", "timeout"}
            );

            // Bật FINE tại logger, nhưng handler còn chặn.
            logger.setLevel(Level.FINE);
            output.setLevel(Level.INFO);
            logger.fine("event=diagnostic.dropped_by_handler");

            // Khi cả hai ngưỡng đều cho phép, FINE được xuất.
            output.setLevel(Level.ALL);
            logger.fine("event=diagnostic.visible");
            output.flush();
        } finally {
            logger.removeHandler(output);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LogLevelSelectionDemo.java
java LogLevelSelectionDemo
```

**Standard output chính xác** (không bao gồm dấu nhắc lệnh):

```text
INFO event=service.ready
WARNING event=inventory.fallback requestId=req-12
SEVERE event=job.failed jobId=job-9 reason=timeout
FINE event=diagnostic.visible
```

Tại sao kết quả này hợp lý?

1. `event=diagnostic.dropped_by_logger` có level `FINE`, thấp hơn `INFO` nên không được logger chấp nhận.
2. `service.ready` là cột mốc bình thường nên `INFO`; nó xuất hiện vì logger và handler đều cho phép.
3. `inventory.fallback` dùng `WARNING` vì dịch vụ vẫn có thể tiếp tục bằng giải pháp dự phòng nhưng cần được chú ý.
4. `job.failed` dùng `SEVERE` vì đó là thất bại cuối cùng của một job; sự kiện này mô phỏng job khác với những dòng trước, không phải hậu quả của `service.ready`.
5. Sau `logger.setLevel(Level.FINE)`, một sự kiện FINE có thể đến handler nhưng vẫn bị handler có ngưỡng `INFO` loại.
6. Sau `output.setLevel(Level.ALL)`, `event=diagnostic.visible` xuất hiện. `formatMessage(record)` xử lý tham số kiểu JUL `{0}`, `{1}`; `output.flush()` đảm bảo nội dung buffered được đẩy ra trước khi `main` kết thúc.
7. `setUseParentHandlers(false)` ngăn record bị chuyển đến các handler của logger cha và tránh dòng log lặp do cấu hình console khác của JUL.

Đây là ví dụ giảng dạy, không phải khuyến nghị tự dựng handler trong mỗi thao tác nghiệp vụ. Ứng dụng thật thường cấu hình mức log và appender/handler ở bước khởi động.

## 8. Cấu hình level khi phát triển và vận hành

### Cấu hình tập trung theo thành phần

Giả sử code dùng logger theo tên class `com.example.orders.OrderService`. Muốn điều tra vùng orders, có thể bật thêm thông tin ở prefix package thay vì cho toàn ứng dụng xuất FINE.

Ví dụ tệp `logging.properties` dành cho JUL:

```properties
# Level root logger.
.level=INFO

# Chỉ tăng chi tiết cho khu vực orders.
com.example.orders.level=FINE

# Console phải đủ mở để in FINE.
handlers=java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Sau khi có class `com.example.Main` đã được biên dịch, có thể khởi động theo mẫu:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Lệnh là **minh họa nạp cấu hình**, không chạy demo ở mục 7 (demo tự thiết lập level, handler). Khi quan sát kết quả cần xác nhận chương trình đang sử dụng JUL, tên logger trùng prefix được cấu hình, cấu hình đã được nạp, handler không lọc lại `FINE` và không có code ghi đè level khác. Với nhiều backend, cú pháp cấu hình và cấp hiệu lực khác nhau.

### Chọn mặc định theo môi trường

| Môi trường / mục đích | Cách bắt đầu thường hợp lý | Điều kiện bổ sung |
| --- | --- | --- |
| Local development | `INFO`, mở `DEBUG/FINE` theo module đang phát triển | Đảm bảo log không lộ token hoặc dữ liệu thật. |
| Test/CI | `INFO` và bật chẩn đoán theo test khi điều tra | Không để log vô nghĩa lấn át kết quả kiểm thử. |
| Production bình thường | `INFO` trở lên ở đa số thành phần; mức chi tiết có kiểm soát | Phụ thuộc lưu lượng, quy định hệ thống, chính sách giữ log. |
| Điều tra production có thời hạn | Bật `DEBUG/FINE` cho package hoặc instance cần thiết | Giới hạn phạm vi, thời gian, dung lượng và quyền truy cập. |
| Một số dependency sinh quá nhiều log | Nâng threshold riêng cho namespace đó | Tránh chặn các cảnh báo/lỗi thực sự cần thấy. |

Không đặt `OFF` toàn hệ thống như một cách khắc phục tình trạng log quá nhiều: có thể bỏ lỡ sự cố quan trọng. Tương tự, không bật `ALL` trong production diện rộng mà không biết lượng dữ liệu, chi phí và rủi ro lộ thông tin.

### Level không thay thế metric, trace hay alert rule

Một log `WARN` không tự xác định “cần đánh thức on-call ngay”. Cảnh báo nên xét số lần xuất hiện, tỷ lệ lỗi, độ trễ, phạm vi ảnh hưởng hoặc trạng thái dịch vụ. Các lỗi hiếm nghiêm trọng có thể kích hoạt cảnh báo tức thời, còn cảnh báo lặp cho một fallback có kiểm soát cần ngưỡng phù hợp.

Việc đổi level có thể làm dashboard và alert bỏ qua một loại sự kiện nếu chúng phụ thuộc vào `ERROR` hoặc `WARN`. Khi chỉnh level trong code review, đánh giá cả cấu hình collector, retention, bộ lọc và quy tắc giám sát.

## 9. Tránh các sai lầm khi chọn level

### Sai lầm 1: Mọi exception đều là ERROR

`catch` có thể xử lý input không hợp lệ, kết thúc retry thành công hoặc phục hồi fallback. Nếu nghiệp vụ đã đạt kết quả hợp lệ, log ERROR thường phản ánh sai tình hình. Hãy phân biệt **exception kỹ thuật** với **mức ảnh hưởng của kết quả cuối cùng**.

### Sai lầm 2: Ghi lỗi lớn ở DEBUG

Nếu một job quan trọng thất bại cuối cùng nhưng chỉ có `FINE/DEBUG`, thông tin có thể bị loại trong production. Hãy ghi một event ở `ERROR/SEVERE` tại ranh giới có trách nhiệm, kèm mã lỗi và ngữ cảnh đủ điều tra.

### Sai lầm 3: Cùng một exception bị log nhiều lần

Một exception đi qua repository, service và controller có thể tạo ba stack trace ERROR. Xác định nơi ghi lỗi chính, dùng propagation của exception và request/correlation ID để không cần lặp toàn bộ log ở mỗi tầng.

### Sai lầm 4: Ghi WARN cho hoạt động thường lệ

Nếu cache miss, người dùng nhập sai và retry một lần là hoạt động bình thường, một `WARN` ở mỗi lần sẽ khiến người vận hành không còn tin log cảnh báo. Có thể ghi DEBUG/INFO tùy nhu cầu, dùng metric để phát hiện khi tần suất bất thường.

### Sai lầm 5: Chọn level dựa vào HTTP status một cách máy móc

Không phải mọi 4xx đều là `WARN/ERROR` hay mọi 5xx đều là cùng mức lỗi của hệ thống hiện tại. Cần nhìn vào trách nhiệm và trạng thái nghiệp vụ. Ví dụ 404 do người dùng gọi URL không tồn tại khác với 404 từ service nội bộ khi dữ liệu bắt buộc phải có.

### Sai lầm 6: Nhầm “logger đã bật” với “log chắc chắn xuất hiện”

JUL có level ở logger và handler; backend khác có logger, appender và filter riêng. Khi một log mong đợi không xuất hiện, hãy kiểm tra ngưỡng hiệu lực, handler, propagation, định dạng và vị trí đầu ra trước khi thay đổi severity của event.

### Sai lầm 7: Dùng DEBUG để chứa dữ liệu không được phép

Token, mật khẩu, session cookie, private key và dữ liệu cá nhân không cần thiết phải được loại khỏi log ở **mọi level**. Một mức log mặc định đang tắt không phải là biện pháp bảo vệ; level có thể bị bật khi chẩn đoán hoặc bị collector lưu lại.

### Sai lầm 8: Chọn level theo câu chữ thiếu kết quả

`"Cannot connect"` có thể là một lần thử đang retry, một fallback thành công hoặc một sự cố làm ngừng dịch vụ. Cùng nội dung text không đủ để quyết định WARN hay ERROR. Log phải nêu `attempt`, `outcome`, `errorCode` và kết quả cuối cùng khi cần.

## 10. Checklist review một dòng log

Trước khi merge một lệnh logging hoặc thay level, có thể kiểm tra:

- **Kết quả:** thao tác đã thành công, suy giảm hay thất bại cuối cùng? Level có phản ánh đúng trạng thái đó?
- **Tính dự kiến:** tình huống có phải phần hợp lệ của contract, ví dụ validation failure hay không?
- **Khả năng hành động:** khi đọc INFO/WARN/ERROR, người vận hành có biết cần làm gì và cần tra cứu ở đâu?
- **Thông tin:** có mã sự kiện, component, correlation ID, nguyên nhân và thông tin exception phù hợp không?
- **Tần suất:** mức level này sẽ sinh bao nhiêu event khi tải tăng? Có tạo alert fatigue hoặc chi phí quá mức không?
- **Độ nhất quán:** các team, service và dependency khác có dùng level cùng ý nghĩa không?
- **Tính quan sát:** logger và handler/appender có thực sự cho phép level đó xuất hiện ở môi trường đích không?
- **Bảo mật:** event có chứa bí mật, dữ liệu nhạy cảm hoặc input chưa được xử lý an toàn không?
- **Giám sát:** đổi level có làm thay đổi quy tắc alert, dashboard, logging pipeline hay retention không?

**Nguyên tắc ghi nhớ:** Chọn level theo *mức ảnh hưởng đã xảy ra* và *giá trị vận hành của sự kiện*. `INFO` giải thích cột mốc bình thường, `WARN/WARNING` nêu bất thường cần chú ý, `ERROR/SEVERE` đánh dấu thất bại có tác động, còn `DEBUG/FINE` và `TRACE/FINER/FINEST` dành cho chi tiết điều tra. Sau đó xác nhận cấu hình logger và nơi xuất log để sự kiện quan trọng thật sự được ghi nhận.