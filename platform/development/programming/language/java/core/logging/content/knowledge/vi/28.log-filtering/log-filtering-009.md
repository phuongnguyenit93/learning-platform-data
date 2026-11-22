# Filter trước format trong Java Core Logging

## 1. “Filter trước format” nghĩa là gì?

Khi ứng dụng Java ghi log, mỗi sự kiện có thể đi qua nhiều bước: kiểm tra mức log, tạo hoặc nhận dữ liệu sự kiện, áp dụng bộ lọc (filter), định dạng thông điệp (format), rồi ghi ra console, file, queue hoặc hệ thống thu thập. **Filter trước format** là nguyên tắc **loại bỏ một log event không cần thiết trước khi thực hiện công việc định dạng tốn chi phí** cho event đó.

Ví dụ, trong production ta chỉ muốn lưu `INFO` trở lên và bỏ sự kiện `DEBUG` hoặc log heartbeat không có giá trị điều tra. Nếu hệ logging định dạng mọi event thành một chuỗi dài trước khi lọc, ứng dụng đã mất CPU và cấp phát bộ nhớ cho các event cuối cùng bị bỏ đi.

Mục tiêu:

- **Giảm chi phí:** bỏ event sớm, hạn chế chạy formatter/layout/encoder và I/O không cần thiết.
- **Giữ chính sách rõ ràng:** lựa chọn mức log hoặc tiêu chí chấp nhận trước khi quyết định xuất ra từng đích.
- **Tránh nhầm lẫn:** một event có thể được chấp nhận ở logger nhưng bị filter của một handler/appender từ chối.
- **Tối ưu đúng chỗ:** hiểu rằng bỏ format ở backend **không nhất thiết** tránh được việc code ứng dụng đã tạo chuỗi/đánh giá đối số trước khi gọi API logger.

Trong ví dụ ở bài này, `format` là bước `java.util.logging.Formatter.format(LogRecord)` hoặc bước tương đương như layout/encoder ở logging backend. **Không đồng nhất format của backend với mọi phép nối chuỗi hoặc `toString()` đã chạy trong mã ứng dụng.**

## 2. Pipeline minh họa: sự kiện bị từ chối ở đâu?

Một đường đi điển hình với **Java Util Logging (JUL)**:

~~~text
Loi goi LOGGER.info(...) / LOGGER.fine(...)
                   |
                   v
        Kiem tra level cua logger
                   |
           Event co duoc tao?
                   |
                   v
         Logger Filter (neu co)
                   |
           Co duoc chap nhan?
                   |
                   v
           Handler.publish(...)
                   |
                   v
       Handler level + Handler Filter
                   |
           Co duoc chap nhan?
                   |
                   v
             Formatter.format
                   |
                   v
           Output (console/file/...)
~~~

Đây là sơ đồ giải thích các điểm **lọc trước khi ghi** thường gặp, không phải lời hứa về từng chi tiết nội bộ của mọi logging framework. JUL thực hiện kiểm tra level ở logger trước khi chuyển sự kiện xuống xử lý; logger filter có thể từ chối một `LogRecord` trước khi event được chuyển đến handler. Khi viết custom `Handler`, chính phương thức `publish` phải kiểm tra `isLoggable(record)` trước khi gọi formatter.

**Cả hai vị trí filter đều có giá trị:**

1. **Logger filter:** quyết định event có được tiếp tục trên đường xử lý của logger nguồn hay không. Nếu bị từ chối, các handler của logger đó không nhận event từ lời gọi tương ứng.
2. **Handler filter:** quyết định **một đích xuất cụ thể** có chấp nhận event hay không. Ví dụ console chỉ nhận `INFO`, file audit nhận một tập khác; những handler khác vẫn có thể xử lý cùng event theo cấu hình riêng.

Trong JUL, `Handler.isLoggable(record)` kiểm tra level và filter của handler. Khi level không đủ, filter của handler có thể **không cần được gọi**. Ở logger, level thấp hơn ngưỡng có thể khiến event bị bỏ trước khi tạo `LogRecord` hoặc chạy logger filter.

**Điểm quan trọng:** nói “filter trước format” chỉ đúng khi backend hoặc custom handler thật sự **kiểm tra filter trước khi gọi formatter**. Một filter tự đọc thông điệp đã được định dạng hoặc một appender định dạng trước khi lọc có thể phá vỡ lợi ích hiệu năng mong muốn.

## 3. Ví dụ Java 17 độc lập: kiểm chứng thứ tự bằng bộ đếm

Ta sẽ dùng chỉ các lớp `java.util.logging` có sẵn trong JDK 17. Chương trình tạo năm log event, với bốn loại kết quả:

- `FINE`: logger chấp nhận vì level là `ALL`, nhưng handler từ chối vì ngưỡng của handler là `INFO`.
- `PRIVATE ...`: logger filter từ chối trước khi event tới handler.
- `NOISE ...`: handler filter từ chối.
- `INFO` và `WARNING` còn lại: vượt qua tất cả bộ lọc và mới được formatter định dạng.

Tạo file **`FilterBeforeFormatDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FilterBeforeFormatDemo {
    public static void main(String[] args) {
        AtomicInteger loggerFilterChecks = new AtomicInteger();
        AtomicInteger handlerPublishCalls = new AtomicInteger();
        AtomicInteger handlerFilterChecks = new AtomicInteger();
        AtomicInteger formatCalls = new AtomicInteger();

        Logger logger = Logger.getLogger("demo.filter.before.format");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Filter loggerFilter = record -> {
            loggerFilterChecks.incrementAndGet();
            return !record.getMessage().startsWith("PRIVATE ");
        };
        logger.setFilter(loggerFilter);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                handlerPublishCalls.incrementAndGet();

                // Custom Handler phai tu kiem tra truoc khi format.
                if (!isLoggable(record)) {
                    return;
                }

                System.out.print(getFormatter().format(record));
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        handler.setLevel(Level.INFO);
        handler.setFilter(record -> {
            handlerFilterChecks.incrementAndGet();
            return !record.getMessage().startsWith("NOISE ");
        });
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                formatCalls.incrementAndGet();
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            logger.fine("detail skipped");
            logger.info("PRIVATE internal event");
            logger.info("NOISE heartbeat");
            logger.info("accepted order=42");
            logger.warning("retry scheduled");

            System.out.println(
                    "loggerFilterChecks=" + loggerFilterChecks.get());
            System.out.println(
                    "handlerPublishCalls=" + handlerPublishCalls.get());
            System.out.println(
                    "handlerFilterChecks=" + handlerFilterChecks.get());
            System.out.println("formatCalls=" + formatCalls.get());
        } finally {
            logger.removeHandler(handler);
            logger.setFilter(null);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac FilterBeforeFormatDemo.java
java FilterBeforeFormatDemo
~~~

**Stdout chính xác trong ví dụ một thread:**

~~~text
INFO: accepted order=42
WARNING: retry scheduled
loggerFilterChecks=5
handlerPublishCalls=4
handlerFilterChecks=3
formatCalls=2
~~~

Không có stderr do ví dụ dùng `Handler` tự viết để in vào `System.out`, không dùng `ConsoleHandler` mặc định của JUL.

**Giải thích từng bộ đếm:**

| Log event | Logger filter | Handler `publish` | Handler filter | Formatter |
| --- | --- | --- | --- | --- |
| `FINE detail skipped` | Có, chấp nhận | Có | Không, bị chặn ở handler level `INFO` | Không |
| `INFO PRIVATE internal event` | Có, từ chối | Không | Không | Không |
| `INFO NOISE heartbeat` | Có, chấp nhận | Có | Có, từ chối | Không |
| `INFO accepted order=42` | Có, chấp nhận | Có | Có, chấp nhận | Có |
| `WARNING retry scheduled` | Có, chấp nhận | Có | Có, chấp nhận | Có |

Do đó có **5 lần** chạy logger filter, **4 lần** đi vào `Handler.publish`, **3 lần** chạy handler filter và chỉ **2 lần** thực hiện `Formatter.format`. Bước format chỉ xảy ra sau khi event vượt qua các điều kiện của handler.

**Vì sao không chỉ đếm số dòng log?** Số dòng là kết quả cuối; các bộ đếm cho thấy **event bị loại ở bước nào**. Điều này đặc biệt hữu ích khi điều tra việc log biến mất vì level, filter hay appender.

**Giới hạn của ví dụ:** đây là một custom handler được viết để minh họa đúng thứ tự. Một handler/appender khác có thể có cơ chế nội bộ, bộ đệm hoặc formatter khác. `AtomicInteger` giúp bộ đếm an toàn nếu mở rộng cho nhiều thread, nhưng chương trình hiện chạy một thread nên thứ tự stdout xác định.

## 4. Filter ở logger và filter ở handler khác nhau như thế nào?

Xét một logger `com.example.order` với hai đích xuất:

~~~text
                Logger com.example.order
                          |
                  Logger Filter
                          |
               +----------+----------+
               |                     |
           ConsoleHandler         FileHandler
           level=INFO             level=FINE
           filter=...             filter=...
               |                     |
          Formatter A             Formatter B
               |                     |
            stdout                 file
~~~

Một event bị **logger filter** từ chối thì không tiếp tục tới các handler đó. Một event vượt qua logger filter có thể được ghi ở file nhưng không xuất ở console nếu mỗi handler có level/filter khác nhau.

Ví dụ trong JUL:

~~~java
// Doan minh hoa trong noi da co Logger va hai Handler.
logger.setFilter(record -> record.getLevel().intValue()
        >= Level.INFO.intValue());

consoleHandler.setFilter(record -> !"healthcheck"
        .equals(record.getLoggerName()));
~~~

Đoạn trên chỉ là mã tích hợp, không phải chương trình độc lập. Lưu ý `record.getLoggerName()` là **tên logger**, không phải nội dung message; nếu muốn loại message về healthcheck, cần tiêu chí tương ứng (ví dụ trường cấu trúc hoặc message nguyên bản) thay vì so sánh nhầm với tên logger.

Không phải mọi filter nên đặt ở logger. Nếu bạn muốn **loại event trên mọi đích**, logger filter là vị trí hợp lý trong mô hình JUL. Nếu chỉ muốn **giảm nhiễu tại một đích**, handler filter thường phù hợp hơn. Tuy nhiên các framework như Logback và Log4j 2 có cách tổ chức filter, additivity và appender khác nhau; phải kiểm tra cơ chế cụ thể, không suy trực tiếp từ cấu trúc JUL.

## 5. “Trước format” không có nghĩa mọi phép tạo chuỗi đều được hoãn

Xem code sau:

~~~java
logger.fine("payload=" + expensiveToString());
~~~

Java đánh giá đối số của phương thức **trước khi gọi** `logger.fine`. Bởi vậy `expensiveToString()` có thể đã chạy ngay cả khi logger đang ở `INFO` và log `FINE` chắc chắn bị bỏ. Lợi ích lọc trước **`Formatter.format`** không hoàn lại chi phí đã phát sinh trong mã ứng dụng.

Với JUL, bạn có thể dùng overload nhận `Supplier<String>` để **hoãn tạo message khi mức log không bật**:

~~~java
logger.log(Level.FINE, () -> "payload=" + expensiveToString());
~~~

Đây là đoạn minh họa bên trong một phương thức đã có `logger` và `expensiveToString()`; không phải chương trình độc lập. Với lệnh này, nếu logger không bật `FINE`, supplier không cần được gọi để tạo message. **Không được suy ra rằng supplier sẽ luôn chưa bị đánh giá trước mọi filter tùy biến**: trình tự đó phụ thuộc API và triển khai. Một khi level đã bật, supplier có thể được chạy dù một filter nằm sau vẫn từ chối event.

Nếu muốn tránh cả việc chuẩn bị các tham số tốn kém khi mức log không bật, có thể chặn ngay tại nơi gọi:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("payload=" + expensiveToString());
}
~~~

Kiểm tra `isLoggable` giúp giảm chi phí không cần thiết ở mức log tắt, nhưng không thay thế filter trong backend. Nếu cấu hình level có thể đổi đồng thời giữa bước kiểm tra và ghi, vẫn nên coi đây là biện pháp tối ưu thông thường chứ không phải cơ chế đồng bộ hay một phép kiểm tra bất biến.

Trong **SLF4J**, cách thường dùng là truyền đối số qua placeholder:

~~~java
// Doan tich hop: can SLF4J va backend.
logger.debug("orderId={} status={}", orderId, status);
~~~

Cách này tránh **nối/format chuỗi trực tiếp** trước lời gọi theo cú pháp `"..." + value`, và backend có thể hoãn định dạng khi log bị tắt. Nhưng mọi biểu thức đối số Java như `expensiveCall()` trong `logger.debug("x={}", expensiveCall())` **vẫn chạy trước** khi logger được gọi. Nếu việc tính toán thật sự đắt, cân nhắc guard `isDebugEnabled()` hoặc cơ chế tham số lazy của API/backend đang dùng (ví dụ fluent `Supplier` trong SLF4J 2.x).

## 6. Cách các logging backend áp dụng filter trước layout/encoder

### 6.1. Java Util Logging (JUL)

- `Logger.isLoggable(Level)` kiểm tra level hiệu lực của logger.
- `Logger.setFilter(Filter)` đặt filter có thể từ chối `LogRecord` trên đường xử lý của logger nguồn.
- `Handler.setLevel(Level)` và `Handler.setFilter(Filter)` đặt điều kiện riêng cho đích xuất.
- `Handler.isLoggable(LogRecord)` là bước custom handler nên gọi **trước `getFormatter().format(record)`**.
- `Formatter.formatMessage(record)` có thể xử lý resource bundle và tham số khi formatter thực sự chạy; nếu filter gọi việc định dạng thông điệp thì chi phí có thể xuất hiện sớm hơn.

Với các handler chuẩn, đừng nhầm **level của logger cha** với **level của handler gắn trên cha**. Khi logger con đã tạo event và chuyển đến handler của cha, handler đó áp dụng level/filter của chính nó; mức của logger cha không nhất thiết chặn event lần thứ hai.

### 6.2. Logback với SLF4J

Logback Classic có **TurboFilter**: đây là cơ chế lọc sớm trong đường xử lý logger, có thể trả về `DENY`, `NEUTRAL` hoặc `ACCEPT` theo hợp đồng của Logback. Bộ lọc thông thường ở **Appender** quyết định event có được xuất tại appender đó hay không, trước khi encoder/layout được gọi trong quy trình appender phổ biến.

Cần phân biệt:

- **TurboFilter sớm:** có thể quyết định nhanh dựa trên level, marker, tên logger hoặc các tham số được cung cấp, trước một số công việc tạo event.
- **Appender filter:** đã có event và quyết định một appender có xử lý hay không.
- **Layout/encoder:** chuyển event được chấp nhận thành chuỗi/byte để ghi ra đích.

Trong Logback, một filter có thể chủ động yêu cầu formatted message hoặc dữ liệu khác, nên không phải filter nào cũng tránh toàn bộ việc định dạng. Cấu hình logger/root level và appender filter vẫn phải được kiểm tra cùng nhau.

### 6.3. Log4j 2

Log4j 2 hỗ trợ filter ở nhiều vị trí như context, logger, appender reference hoặc appender, tùy cấu hình. Một filter có thể loại event trước khi layout chuyển event sang dạng chuỗi/byte, nhưng **chi phí thực tế tùy loại filter và message**. Ví dụ filter dựa trên metadata có thể rẻ hơn filter dùng regular expression trên **formatted message**: loại sau có thể kích hoạt việc format để so khớp, dù event không được ghi cuối cùng.

Nếu sử dụng async logging, hãy phân biệt **thời điểm quyết định chấp nhận event**, **thời điểm format**, **thời điểm ghi output** và **thời điểm flush**. Không thể giả định mọi bước diễn ra trên cùng thread hay cùng thời điểm. Không nên áp dụng sơ đồ nội bộ của JUL như đặc tả chi tiết cho Logback hoặc Log4j 2.

## 7. Cách thiết kế filter ít tốn kém

Khi lựa chọn điều kiện filter, ưu tiên dữ liệu sẵn có và rẻ:

| Điều kiện | Ví dụ | Lưu ý |
| --- | --- | --- |
| Mức log | Chỉ nhận `INFO` trở lên | Thường là kiểm tra rất rẻ |
| Tên logger/package | Bỏ log debug của một package | Phù hợp khi không cần xem nội dung message |
| Marker hoặc thuộc tính cấu trúc | Chỉ gửi event `AUDIT` đến appender riêng | Phụ thuộc API/backend |
| Thông tin ngữ cảnh sẵn có | Chọn môi trường hoặc loại tác vụ | Cân nhắc chi phí truy cập MDC/context |
| Chuỗi thông điệp đã format | Regex/substring trên message cuối | Có thể khiến format chạy sớm, tốn CPU/bộ nhớ |
| Gọi mạng/đọc database trong filter | Tra cứu quyền hoặc chính sách từ dịch vụ khác | Tránh trên đường nóng vì độ trễ và nguy cơ lỗi dây chuyền |

**Các thực hành tốt:**

1. Lọc theo **level** sớm, rồi tới các điều kiện metadata đơn giản. Chỉ phân tích thông điệp khi thực sự cần.
2. Cân nhắc **đặt filter theo đích** khi console, file và hệ thống thu thập có chính sách khác nhau.
3. Tránh nối chuỗi lớn, tuần tự hóa JSON, đọc stack trace hoặc gọi `toString()` tốn kém **trước** khi biết log có khả năng được bật.
4. Với custom handler/appender, kiểm tra `isLoggable` hoặc tương đương trước khi gọi formatter, encoder, network hoặc disk I/O.
5. Không dùng filter có side effect nghiệp vụ. Filter có thể được gọi nhiều lần, trên nhiều thread hoặc trong các cấu hình khác nhau; nó nên nhanh và dễ dự đoán.
6. Đo **tốc độ tạo event, số event bị loại, số lần format và chi phí I/O** trước khi tối ưu. Chỉ đo thời gian gọi `logger.info` có thể bỏ sót phần việc async ở phía sau.

**Cẩn trọng với bảo mật:** loại event bằng filter không thay thế **redaction/masking tại nguồn**. Nếu message đã chứa token hoặc dữ liệu nhạy cảm, việc filter chặn ở một appender không bảo đảm thông tin chưa đi qua các bước khác hoặc đích khác. Hãy bảo đảm dữ liệu nhạy cảm không được đưa vào log ngay từ đầu, hoặc dùng cơ chế che dữ liệu phù hợp trước khi xuất.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `formatCalls` vẫn tăng dù log bị loại | Formatter được gọi trước filter hoặc filter tự lấy formatted message | Kiểm tra thứ tự gọi trong custom handler/filter |
| Một event không xuất ra console nhưng có trong file | Handler/appender có level hoặc filter riêng | Kiểm tra từng đích xuất, không chỉ logger level |
| `FINE` không có dù logger đặt `ALL` | Handler chỉ nhận `INFO` trở lên | Xem cả handler level và filter |
| CPU vẫn cao khi level `DEBUG` tắt | Code đã thực hiện nối chuỗi/`toString()` hoặc serialize trước khi gọi logger | Dùng placeholder, supplier hoặc guard level khi phù hợp |
| Filter theo prefix không hoạt động như mong đợi | `record.getMessage()` là message gốc/template, không nhất thiết là chuỗi cuối cùng sau `formatMessage` | Chọn trường phù hợp hoặc cơ chế filter của backend |
| Log bị ghi lặp | Nhiều handler và cơ chế kế thừa/additivity | Kiểm tra handler của logger cha và các appender reference |
| Bỏ lọc trên một đích nhưng còn xuất ở đích khác | Chính sách filter chỉ áp dụng cho một appender | Đặt rule ở đúng vị trí hoặc trên từng đích cần kiểm soát |
| Tối ưu filter làm mất log cần điều tra | Điều kiện quá rộng hoặc sampling quá gắt | Kiểm thử tình huống lỗi, quan sát tỷ lệ event được giữ |
| Async queue đầy hoặc log đến trễ | Backpressure, discard, buffering, flush/shutdown | Kiểm tra cấu hình queue và exporter của backend |

## 9. Bài thực hành kiểm chứng

Thử sửa **một điều kiện** trong `FilterBeforeFormatDemo.java` và chạy lại:

1. Đổi `handler.setLevel(Level.INFO)` thành `handler.setLevel(Level.ALL)`: event `FINE detail skipped` sẽ đi qua handler filter và formatter. Khi đó `handlerFilterChecks=4`, `formatCalls=3`; bộ đếm logger vẫn bằng 5 và publish vẫn bằng 4.
2. Giữ handler `INFO`, đổi điều kiện `startsWith("NOISE ")` thành `startsWith("UNUSED ")`: event heartbeat không còn bị loại; `formatCalls=3`, `handlerFilterChecks=3`.
3. Thử chuyển lời gọi `getFormatter().format(record)` lên **trước** `isLoggable(record)` (chỉ trong bản demo thử nghiệm): bộ đếm format sẽ tăng cho cả event bị handler từ chối. Đây là ví dụ của cách triển khai không mong muốn; sau khi quan sát cần khôi phục thứ tự ban đầu.
4. Thử gắn thêm một handler khác có level/filter khác: một event có thể tạo output ở handler này nhưng bị chặn ở handler kia. Cần loại bỏ handler thử nghiệm sau khi kết thúc để không ghi trùng hoặc giữ tài nguyên.

**Câu hỏi tự kiểm tra:** Logger level `ALL`, handler level `WARNING`, formatter đắt tiền. Một event `INFO` có nhất thiết được format không? **Không**, nếu handler kiểm tra level/filter trước formatter như cách triển khai ở ví dụ. Nhưng nếu code đã gọi `"value=" + expensiveToString()` để truyền vào `LOGGER.info`, chi phí `expensiveToString()` vẫn phát sinh.

**Ghi nhớ:** Lọc sớm chỉ giúp tiết kiệm những bước **chưa xảy ra**. Với Java logging, hãy phân biệt lọc level, logger filter, handler/appender filter và formatter/encoder. Đặt điều kiện rẻ trước việc format tốn kém, tránh tạo message sớm ở caller và kiểm chứng thứ tự bằng đo đếm thay vì chỉ nhìn số dòng log.