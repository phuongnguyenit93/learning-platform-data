# ERROR — mức log cho sự cố nghiêm trọng trong Java

## 1. ERROR có nghĩa là gì?

Trong kiến trúc logging, **ERROR** là mức log dùng để báo rằng một thao tác hoặc thành phần đã gặp **thất bại có ý nghĩa đối với hệ thống hoặc nghiệp vụ**, cần được ghi nhận để điều tra, sửa chữa hay theo dõi sức khỏe dịch vụ. Ví dụ: không thể lưu đơn hàng sau khi đã hết cơ hội thử lại; giao dịch cần thiết bị hủy vì hệ thống lưu trữ không khả dụng; xử lý yêu cầu thất bại do lỗi không mong đợi.

Khi nhìn thấy ERROR, người vận hành thường cần trả lời:

- **Cái gì đã thất bại?** Thao tác, dịch vụ, thành phần và mã lỗi ổn định.
- **Ảnh hưởng là gì?** Một request thất bại, một công việc nền không hoàn tất, hay cả một thành phần bị gián đoạn?
- **Lỗi xảy ra lúc nào và trong ngữ cảnh nào?** Thời gian, môi trường, phiên bản triển khai, mã liên kết request/trace.
- **Có thể làm gì tiếp?** Thử lại, kiểm tra hệ thống phụ thuộc, khôi phục dữ liệu, chuyển xử lý thủ công hay sửa mã.

ERROR **không phải tên chung cho mọi trường hợp xuất hiện đối tượng `Exception`**. Một ngoại lệ được xử lý bình thường có thể chỉ đáng ghi `DEBUG` hoặc `WARN`; ngược lại, kết quả nghiệp vụ thất bại nghiêm trọng có thể cần ERROR dù không có exception Java nào được ném.

Ví dụ đối chiếu:

| Tình huống | Mức thường cân nhắc | Lý do |
| --- | --- | --- |
| Yêu cầu bị từ chối vì người dùng nhập số tiền âm | `INFO` hoặc `DEBUG`; đôi khi `WARN` tùy chính sách | Kiểm tra hợp lệ hoạt động đúng, chưa chứng minh hệ thống có lỗi. |
| Một lần gọi dịch vụ ngoài bị timeout nhưng sẽ tự thử lại và cuối cùng thành công | `WARN` hoặc `DEBUG` | Có bất thường, nhưng thao tác logic vẫn được phục hồi. |
| Hết số lần thử lại, giao dịch thanh toán không thể hoàn tất | `ERROR` | Thao tác có ảnh hưởng thực tế đã thất bại. |
| Không thể đọc cấu hình bắt buộc và ứng dụng không thể khởi động | `ERROR`, có thể mức nghiêm trọng hơn nếu backend có | Chức năng trọng yếu không hoạt động. |
| Một tác vụ nền thất bại nhưng hệ thống đã chuyển vào hàng đợi xử lý thủ công thành công | `WARN` hoặc `ERROR` theo cam kết nghiệp vụ | Quyết định dựa vào việc tác vụ đã thực sự được xử lý hay chưa và mức ảnh hưởng. |
| Nhận HTTP 404 vì tài nguyên không tồn tại, đúng hành vi API | Thường không phải ERROR | Trạng thái HTTP 4xx không tự động tương đương sự cố máy chủ. |

Mức log là **chính sách phân loại sự kiện**, không phải cơ chế xử lý ngoại lệ: ghi ERROR không tự rollback transaction, không trả HTTP 500, không tự retry, cũng không đảm bảo có cảnh báo.

## 2. ERROR nằm ở đâu trong thang mức log?

Hệ sinh thái Java có nhiều API/backend với tên mức khác nhau.

| API / backend | Mức liên quan | Cách phát log |
| --- | --- | --- |
| SLF4J (`org.slf4j.Logger`) | `ERROR` | `logger.error("Không thể hoàn tất thanh toán")` |
| Logback (backend SLF4J phổ biến) | `ERROR` | Có thể cấu hình ngưỡng `ERROR` cho logger/appender. |
| Log4j 2 | `ERROR` và mức `FATAL` riêng | `logger.error(...)`; `FATAL` là lựa chọn đặc thù backend. |
| `System.Logger` (JDK 9+) | `System.Logger.Level.ERROR` | `System.getLogger("...").log(System.Logger.Level.ERROR, "...")` |
| `java.util.logging` (JUL) | **`SEVERE`**, không có hằng `Level.ERROR` | `logger.log(Level.SEVERE, "...")` |

Trong nhiều hệ thống thực tế, một logger có chuỗi mức tương tự:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

Ngưỡng `WARN` thường nhận cả sự kiện `WARN` và `ERROR`; ngưỡng `ERROR` chỉ nhận ERROR và những mức cao hơn nếu backend có hỗ trợ. Thứ tự này mô tả SLF4J/Logback/Log4j2 ở mức khái niệm; **không chép nguyên tên TRACE/DEBUG/ERROR vào JUL**, vì JUL dùng `FINEST`, `FINER`, `FINE`, `INFO`, `WARNING`, `SEVERE` và một số mức khác.

### ERROR so với WARN

Có thể dùng câu hỏi **“thao tác đã hết cách phục hồi theo cơ chế hiện tại chưa, và kết quả thất bại có ảnh hưởng thực sự không?”**

- **WARN:** dấu hiệu bất thường hoặc nguy cơ thất bại; hệ thống có thể vẫn cung cấp kết quả được chấp nhận. Ví dụ đã phải dùng bản sao dự phòng nhưng kết quả vẫn đúng.
- **ERROR:** thất bại cần điều tra hoặc hành động theo chính sách phục vụ. Ví dụ bản sao dự phòng cũng không hoạt động và request cuối cùng bị lỗi.

Không nên áp dụng máy móc quy tắc “bắt được exception thì WARN, không bắt thì ERROR”. Một exception được bắt nhưng khiến nghiệp vụ thất bại vẫn có thể là ERROR. Ngược lại, một ngoại lệ được framework bắt và chuyển thành phản hồi 400 đúng hợp đồng không nhất thiết là ERROR.

### ERROR có khác FATAL không?

Một số backend, chẳng hạn Log4j 2, có mức `FATAL` để biểu diễn lỗi đặc biệt nghiêm trọng, có thể khiến ứng dụng không thể tiếp tục. SLF4J và Logback phổ biến chỉ có `ERROR` là mức cao nhất trong thang thông dụng. **Không giả định ứng dụng Java nào cũng có FATAL.** Nếu mất kết nối cơ sở dữ liệu khiến toàn bộ service dừng, vẫn có thể ghi ERROR và để chỉ số sức khỏe/điều phối tiến trình thể hiện mức ảnh hưởng của sự cố.

## 3. Khi nào nên ghi ERROR?

Nên xác định rõ **ranh giới xử lý** và **trách nhiệm đối với kết quả**:

1. **Request:** khi cuối cùng không thể hoàn thành thao tác do lỗi máy chủ hoặc phụ thuộc quan trọng, sau khi đã áp dụng xử lý ngoại lệ, fallback hoặc retry thích hợp.
2. **Công việc nền (job):** khi một job logic bị thất bại và không còn được tự động hoàn thành trong luồng xử lý bình thường.
3. **Khởi động/cấu hình:** khi thiếu tài nguyên bắt buộc hoặc cấu hình không hợp lệ khiến thành phần không khởi động hoặc không hoạt động đúng.
4. **Tính toàn vẹn:** khi phát hiện trạng thái không hợp lệ, ghi dữ liệu quan trọng thất bại, hoặc vi phạm bất biến hệ thống cần can thiệp.
5. **Phụ thuộc bên ngoài:** khi hệ thống ngoài làm yêu cầu cuối cùng thất bại. Lỗi tạm thời đang được thử lại có thể log ở WARN, còn thất bại cuối cùng ở ERROR.

Ví dụ xử lý thanh toán có ba bước:

```text
Gọi cổng thanh toán lần 1 -> timeout
    -> WARN: sẽ thử lại
Gọi lần 2 -> timeout
    -> WARN: tiếp tục thử lại (nếu còn lượt)
Gọi lần cuối -> timeout, hết retry
    -> ERROR: payment.failed, kết quả nghiệp vụ thất bại
```

Nếu ghi ERROR ở cả ba lần timeout và lại thêm ERROR tại lớp HTTP bên ngoài, dashboard có thể đếm nhiều ERROR cho **một giao dịch thất bại**. Điều này không mặc nhiên sai về mặt ghi nhật ký, nhưng làm tín hiệu trở nên khó hiểu. Cần định nghĩa rõ **một lỗi kỹ thuật theo lần thử** và **một thất bại theo thao tác logic**, cùng quy tắc nơi phát sự kiện cuối cùng.

**Ghi lỗi tại nơi có thể diễn giải hậu quả.** Lớp repository có thể chỉ ném ngoại lệ bổ sung ngữ cảnh; lớp xử lý giao dịch hoặc ranh giới API biết rằng request đã thất bại và phát một sự kiện ERROR bao gồm mã lỗi và ngữ cảnh. Nếu nhiều tầng đều log rồi ném lại cùng một lỗi, người xem sẽ thấy nhiều stack trace trùng lặp.

## 4. Một bản ghi ERROR hữu ích chứa những gì?

Thông báo “ERROR: something went wrong” không cho biết cần xử lý gì. Nên ghi **sự kiện rõ nghĩa, mã lỗi ổn định và dữ liệu liên kết đủ để truy vết**.

Ví dụ dạng dữ liệu có cấu trúc:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "event": "payment.failed",
  "error_code": "PROVIDER_UNAVAILABLE",
  "order_id": "O-17",
  "trace_id": "trace-123",
  "request_id": "req-456",
  "attempt": 3,
  "outcome": "failed",
  "duration_ms": 1842
}
```

Ý nghĩa các trường chính:

| Trường | Mục đích |
| --- | --- |
| `level` | Nhận biết mức nghiêm trọng của sự kiện. |
| `event` | Tên hành vi ổn định, dùng thống kê và tìm kiếm; tránh đổi tùy câu chữ. |
| `error_code` | Mã lỗi có nghĩa với ứng dụng; giữ ổn định qua các lần phát hành. |
| `service`, `environment`, `version` | Xác định dịch vụ, môi trường và bản triển khai. |
| `trace_id`, `request_id` | Đi từ lỗi sang các log liên quan trong một luồng xử lý. |
| `order_id` / `job_id` | Định danh nghiệp vụ khi được phép ghi; cần chính sách bảo vệ dữ liệu. |
| `attempt` | Phân biệt một lượt thử với kết quả cuối của job/request. |
| `duration_ms` | Thời gian xử lý, luôn nêu rõ đơn vị và đối tượng đo. |
| `exception.type`, stack trace | Loại ngoại lệ và vị trí lỗi kỹ thuật (khi có và khi phù hợp). |

Dòng log nên trả lời **“lỗi gì, ở thao tác nào, ảnh hưởng gì?”**. Ví dụ:

```text
ERROR event=payment.failed service=checkout
error_code=PROVIDER_UNAVAILABLE order_id=O-17
trace_id=trace-123 outcome=failed attempts=3
```

Đây là mẫu định dạng văn bản; trong triển khai thật, dùng logging có cấu trúc (JSON hoặc cơ chế trường có kiểu) để hệ thống thu thập truy vấn được mà không phải dựa vào việc tách chuỗi dễ vỡ.

### Lưu cả nguyên nhân mà không làm lộ bí mật

Khi ngoại lệ giúp chẩn đoán, ghi **đối tượng Throwable** qua API logger để backend có thể xuất stack trace. Tránh chỉ ghi `exception.getMessage()` vì mất loại ngoại lệ, nguyên nhân lồng nhau và nơi phát sinh. Tuy nhiên, message của exception đôi khi chứa URL với token, câu lệnh SQL có tham số nhạy cảm hoặc dữ liệu đầu vào; cần che hoặc loại bỏ trước khi đưa sang hệ thống log.

Không đưa mật khẩu, API key, access token, số thẻ, dữ liệu cá nhân, toàn bộ request body hoặc thông tin đăng nhập vào log. Ngay cả `order_id` hay `user_id` cũng phải tuân theo quyền truy cập, chính sách lưu và mục đích sử dụng. Có thể log mã tham chiếu được phép hoặc hash phù hợp thay cho giá trị nhạy cảm.

## 5. Các API Java thể hiện ERROR như thế nào?

### 5.1. SLF4J: mức `ERROR`

Với ứng dụng đã dùng SLF4J và có backend (ví dụ Logback), một mẫu phổ biến:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void process(String orderId) {
        try {
            callProvider();
        } catch (ProviderException ex) {
            LOG.error("event=payment.failed orderId={} errorCode=PROVIDER_UNAVAILABLE",
                    orderId, ex);
            throw ex;
        }
    }

    // callProvider() và ProviderException thuộc ứng dụng thật.
}
```

Đây là **đoạn mã minh họa**, chưa biên dịch độc lập vì `callProvider()` và `ProviderException` là thành phần giả định của ứng dụng. Trong SLF4J, khi truyền `Throwable` làm đối số cuối phù hợp với overload định dạng, backend có thể ghi stack trace của ngoại lệ. Với SLF4J 2.x, cũng có thể dùng API fluent và `setCause(ex)`.

**Cần lưu ý điểm đặt log:** mẫu trên chỉ hợp lý khi lớp `PaymentService` là nơi chịu trách nhiệm xác nhận thất bại cuối cùng. Nếu lớp gọi bên ngoài cũng ghi ERROR cho cùng ngoại lệ, cần quyết định một nơi ghi sự kiện thất bại hoặc phân biệt hai sự kiện có mục đích khác nhau.

### 5.2. API `System.Logger` của JDK

Từ Java 9, JDK có giao diện `System.Logger` với mức `ERROR` thật sự:

```java
System.Logger log = System.getLogger("com.example.payment");
log.log(System.Logger.Level.ERROR, "payment.failed");
```

API này có thể hoạt động mà không thêm SLF4J. Cách xuất bản ghi và cấu hình phụ thuộc `LoggerFinder`/nhà cung cấp logging được chọn; khi dùng provider mặc định của JDK có thể liên hệ tới JUL. **Không xem định dạng console hay cách ánh xạ mức của mọi provider là giống nhau.**

### 5.3. `java.util.logging`: dùng `SEVERE`

JUL **không có `Level.ERROR`**. Mức gần nhất về ý nghĩa thông thường là `Level.SEVERE`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger log = Logger.getLogger("com.example.payment");
log.log(Level.SEVERE, "event=payment.failed", failure);
```

Đây là đoạn minh họa trong một ngữ cảnh đã có biến `failure` kiểu `Throwable`. Cú pháp nhận `Throwable` là overload `log(Level, String, Throwable)`. Đừng viết `Level.ERROR` trong JUL vì mã sẽ không biên dịch.

## 6. Ví dụ Java 17 chạy độc lập: phân biệt INFO, WARNING và thất bại cuối

Bài này dùng JUL để chạy **không cần thư viện ngoài**. Vì JUL không có hằng ERROR, ví dụ dùng `SEVERE` cho tình huống tương đương về ý nghĩa. Một handler nhỏ in ra định dạng cố định, giúp đầu ra dễ đối chiếu. Trong sản phẩm thực tế, formatter/logger backend nên giữ stack trace đầy đủ và các trường cấu trúc.

Lưu thành `ErrorLevelDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorLevelDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("lesson.checkout");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                Throwable failure = record.getThrown();
                String cause = failure == null ? ""
                        : " cause=" + failure.getClass().getSimpleName()
                        + ":" + failure.getMessage();

                System.out.println(record.getLevel().getName() + " "
                        + record.getMessage() + cause);
            }

            @Override
            public void flush() {
                // Không dùng bộ đệm riêng trong ví dụ.
            }

            @Override
            public void close() {
                // Không đóng System.out vì không sở hữu luồng này.
            }
        };

        output.setLevel(Level.ALL);
        log.addHandler(output);

        // Từ chối đầu vào không hợp lệ là hành vi bình thường.
        log.info("event=request.rejected reason=INVALID_AMOUNT");

        // Một lỗi tạm thời còn được retry: chưa phải kết quả thất bại cuối.
        log.warning("event=payment.retry order_id=O-17 attempt=1");

        try {
            charge();
        } catch (IllegalStateException failure) {
            // Đây là ranh giới quyết định thanh toán cuối cùng thất bại.
            log.log(Level.SEVERE,
                    "event=payment.failed order_id=O-17 "
                    + "error_code=PROVIDER_UNAVAILABLE",
                    failure);
            System.out.println("result=FAILED");
        }

        log.removeHandler(output);
        output.close();
    }

    private static void charge() {
        throw new IllegalStateException("provider unavailable");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ErrorLevelDemo.java
java ErrorLevelDemo
```

**Stdout chính xác của ví dụ:**

```text
INFO event=request.rejected reason=INVALID_AMOUNT
WARNING event=payment.retry order_id=O-17 attempt=1
SEVERE event=payment.failed order_id=O-17 error_code=PROVIDER_UNAVAILABLE cause=IllegalStateException:provider unavailable
result=FAILED
```

**Vì sao mỗi dòng ở mức đó?**

1. Đầu vào không hợp lệ bị từ chối theo đúng hợp đồng, nên ví dụ ghi `INFO`.
2. Lượt gọi ngoài có vấn đề và dự kiến thử lại; `WARNING` giúp ghi nhận bất thường nhưng chưa kết luận toàn bộ thao tác thất bại.
3. Phương thức `charge()` ném `IllegalStateException`. Nhánh `catch` mô tả kết quả cuối cùng nên phát `SEVERE` — tương ứng với chủ đích ghi ERROR ở các API có mức ERROR.
4. Khi truyền `failure` vào `log(Level.SEVERE, message, failure)`, `LogRecord` giữ tham chiếu tới Throwable. Handler minh họa chỉ in tên loại và message để stdout ổn định; nó **không thể hiện stack trace đầy đủ**. Formatter production cần xuất ngoại lệ và nguyên nhân phù hợp để điều tra.
5. `log.setUseParentHandlers(false)` ngăn các dòng được phát thêm bởi handler của logger cha, giúp tránh log trùng ở ví dụ. Trong dự án thật phải kiểm tra cấu hình thu thập chung trước khi tắt lan truyền.
6. `output.setLevel(Level.ALL)` bảo đảm handler không bỏ các bản ghi đã vượt qua ngưỡng `INFO` ở logger. Nếu đặt handler `SEVERE`, hai dòng INFO và WARNING sẽ không được in.

**Lưu ý về kịch bản:** dòng WARNING chỉ là một sự kiện thử lại giả lập trước khi lần gọi cuối thất bại. Ví dụ không xây dựng bộ retry đầy đủ. Mục tiêu là cho thấy **mức log phản ánh kết quả và ý nghĩa vận hành**, không phải dạy thuật toán retry hay điều khiển transaction.

## 7. Cấu hình hiển thị và định tuyến ERROR

Ứng dụng có thể phát ERROR đúng, nhưng người vận hành vẫn không nhìn thấy nếu handler/appender hoặc pipeline thu thập lọc sai.

Ví dụ cấu hình Logback cho ứng dụng đã dùng SLF4J + Logback:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Ở đây root `INFO` **vẫn nhận ERROR** vì ERROR có mức nghiêm trọng cao hơn INFO. Mẫu `%ex` thể hiện thông tin ngoại lệ khi có, còn `%logger` cho biết nơi phát; định dạng cụ thể phụ thuộc phiên bản và cấu hình backend.

Nếu muốn chỉ xem ERROR tại một kênh riêng, có thể dùng appender với bộ lọc theo mức, ví dụ `ThresholdFilter` ở ngưỡng `ERROR` trong Logback. Cần phân biệt:

- **Mức logger:** quyết định sự kiện có được tạo và đi tiếp không.
- **Mức/bộ lọc appender:** quyết định nơi nhận có chấp nhận sự kiện không.
- **Cấu hình lan truyền:** có thể đưa một sự kiện đến appender của cha hoặc tạo bản sao ở nhiều đích.
- **Pipeline bên ngoài:** bộ thu thập còn có thể lấy mẫu, làm rơi, đổi cấu trúc hoặc định tuyến bản ghi.

Một dòng ERROR gửi đồng thời tới console và nơi lưu lâu dài có thể là fan-out hợp lệ. Hai bản ghi giống nhau xuất hiện **trong cùng một kênh** do cấu hình appender ở cả logger con và logger cha thường là trùng lặp cần kiểm tra.

Trong JUL, cấu hình tương đương cần dùng `SEVERE`, chẳng hạn `java.util.logging.ConsoleHandler.level=SEVERE` trong `logging.properties` nếu muốn console chỉ nhận các mức từ SEVERE trở lên. Không trộn cú pháp Logback vào tệp cấu hình JUL.

## 8. ERROR, HTTP status và số liệu sự cố

Một ngộ nhận là “cứ có ERROR thì chắc là HTTP 500” hoặc “một HTTP 500 tương ứng một dòng ERROR”. Thực tế:

- Một request có thể phát nhiều ERROR ở các lớp khác nhau, hoặc không phát ERROR nếu đường xử lý không ghi log.
- Một ERROR trong tác vụ nền không gắn với HTTP status nào.
- HTTP 5xx có thể phát sinh do proxy, load balancer hoặc timeout trước khi mã ứng dụng kịp ghi sự kiện ERROR.
- Lỗi của downstream có thể được fallback thành một response thành công có suy giảm chức năng; mức log tùy ngữ nghĩa phục vụ.
- `IllegalArgumentException` không tự chứng minh request phải là 500; nếu do dữ liệu đầu vào không hợp lệ, ứng dụng có thể chuyển thành 400 đúng hợp đồng.

**Không dùng số dòng ERROR làm số request thất bại nếu không có quy ước sự kiện duy nhất và đầy đủ.** Muốn tính error rate HTTP, nên dùng nguồn đếm request hoàn tất hoặc metric có định nghĩa, ví dụ `http.server.requests` phân theo trạng thái. Dùng log ERROR để điều tra nguyên nhân, phân loại mã lỗi và liên kết với trace.

Ví dụ ở dashboard: “5xx tăng từ 0,2% lên 3% trong 5 phút”. Truy vấn log ERROR cùng `service`, `environment`, `version` và khoảng thời gian; sau đó gom theo `error_code`, `route`, `dependency`. Nếu thấy nhiều `PROVIDER_UNAVAILABLE`, chọn một `trace_id` để đối chiếu request và lần gọi tới hệ thống phụ thuộc.

### Đối với retry và nhiều luồng

Nếu một job có ba attempt và phát một ERROR ở mỗi attempt, cần biết phép đếm là “số lần thử thất bại” hay “số job cuối cùng thất bại”. Dùng `attempt` và `job_id` hoặc các sự kiện khác nhau như `payment.attempt_failed`, `payment.failed` để diễn giải rõ. Trường có số lượng giá trị lớn như `trace_id` phù hợp để truy tìm từng sự kiện, không nên dùng làm label metric tổng hợp.

Nhiều luồng và nhiều service có thể khiến log đến nơi thu thập không đúng thứ tự thời gian; không dựa vào vị trí dòng trong giao diện log để kết luận nguyên nhân. Nên dùng timestamp có múi giờ rõ ràng, mã liên kết và trace phân tán phù hợp.

## 9. Chọn nội dung và cách ghi ngoại lệ cho an toàn

Một sự kiện ERROR tốt cần thông tin chẩn đoán **vừa đủ**. Những nguyên tắc quan trọng:

1. **Thông điệp có hành động rõ:** `event=payment.failed error_code=PROVIDER_UNAVAILABLE` có ích hơn `ERROR!!!`.
2. **Ghi Throwable khi cần stack trace:** với SLF4J, gọi overload hỗ trợ Throwable; với JUL dùng `log(Level.SEVERE, message, throwable)`.
3. **Chọn nơi ghi có trách nhiệm:** tránh mọi tầng đều `log + rethrow` cùng một ngoại lệ. Có thể thêm ngữ cảnh vào ngoại lệ và để ranh giới API/job phát một ERROR.
4. **Giữ nguyên nguyên nhân:** nếu chuyển exception, dùng constructor nhận `cause` khi có, giúp giữ chuỗi nguyên nhân. Không biến mọi exception thành một message rỗng ngữ cảnh.
5. **Đặt mã lỗi ổn định:** dữ liệu có thể đếm, lọc và cảnh báo mà không phụ thuộc văn bản message.
6. **Không để log tự tạo lỗi mới:** handler/appender lỗi, logger chứa biểu thức tính tốn hoặc chuỗi hóa object nặng có thể ảnh hưởng đường xử lý. Tránh thực thi tác vụ tốn kém trong biểu thức tạo log.
7. **Lược bỏ bí mật:** message/stack trace cũng có thể chứa chuỗi kết nối, URL có token hay tham số nhạy cảm. Cần kiểm soát đầu vào và bộ thu thập.
8. **Chọn retention và quyền đọc:** ERROR thường phục vụ điều tra sự cố, nhưng không có nghĩa được lưu vô hạn; cần chính sách bảo mật và thời hạn phù hợp.
9. **Phân biệt log với alert:** mức ERROR là dữ liệu nguồn. Cảnh báo nên xét tỷ lệ thất bại, ảnh hưởng, số lượng mẫu và thời gian kéo dài; không phải mọi ERROR đơn lẻ đều cần đánh thức người trực.
10. **Biết giới hạn ghi log:** ghi bất đồng bộ có thể bị mất khi hàng đợi đầy hoặc JVM dừng đột ngột; ghi đồng bộ quá nhiều có thể ảnh hưởng độ trễ. Những sự kiện cần bảo đảm giao nhận cần cơ chế chuyên biệt hơn logging thông thường.

## 10. Những lỗi thường gặp khi dùng ERROR

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Ghi ERROR cho mọi `catch` | Log ồn, người trực khó nhận ra sự cố thực sự | Xác định kết quả cuối và mức ảnh hưởng trước khi chọn level. |
| Ghi ERROR cho mọi 400/404 hợp lệ | Tăng báo động sai | Phân biệt lỗi người dùng và lỗi phục vụ từ hệ thống. |
| Retry 3 lần, log ERROR 3 lần rồi lại log ở controller | Cùng một thao tác bị đếm thành nhiều lỗi | Phân biệt attempt và final outcome; chốt một nơi ghi sự kiện cuối. |
| Chỉ ghi `exception.getMessage()` | Mất stack trace và nguyên nhân | Truyền đối tượng Throwable vào API logger. |
| Ghi nguyên request/response và token | Rò rỉ dữ liệu vào kho log | Chỉ ghi trường được phép, che hoặc bỏ dữ liệu nhạy cảm. |
| Dùng `Level.ERROR` với JUL | Không biên dịch | Dùng `Level.SEVERE` hoặc `System.Logger.Level.ERROR` tùy API. |
| Đặt root `INFO` rồi tưởng ERROR bị ẩn | Hiểu sai ngưỡng | Kiểm tra mức có thứ tự; INFO thường bao gồm ERROR ở SLF4J/Logback. |
| Không thấy ERROR sau triển khai | Handler/filter, collector hoặc cấu hình thay đổi | Kiểm tra logger nguồn, appender/handler, luồng thu thập và môi trường. |
| Dùng số dòng ERROR để tính SLO | Đếm trùng, thiếu sự kiện, mất số liệu | Dùng chỉ số/request completion có định nghĩa và mức đầy đủ xác minh được. |
| Log mà không có `trace_id` hay mã lỗi | Khó khoanh vùng và phân nhóm | Chuẩn hóa tên event/error_code và liên kết yêu cầu khi phù hợp. |

## 11. Bài tập tự kiểm tra

Giả sử một dịch vụ Java xử lý thanh toán theo chuỗi:

1. Một request gửi số tiền âm. Bộ kiểm tra hợp lệ trả phản hồi 400 đúng thiết kế.
2. Một request khác gọi cổng thanh toán bị timeout lần đầu, nhưng retry thành công.
3. Request thứ ba gọi cổng thanh toán thất bại ba lần và trả kết quả thất bại cuối cùng.
4. Một tác vụ nền có exception được bắt và chuyển thành kết quả dự phòng vẫn đúng yêu cầu.
5. Bộ khởi động không tải được cấu hình bắt buộc nên tiến trình phải dừng.

**Câu hỏi:** Trường hợp nào nên xem xét ghi ERROR, trường hợp nào nên dùng INFO/WARN? Với trường hợp 3, có nên log ERROR ở cả lớp gọi mạng, lớp dịch vụ và controller không? Với JUL phải dùng hằng nào để biểu đạt mức tương tự ERROR?

**Gợi ý đáp án:** Trường hợp 1 thường là INFO/DEBUG hoặc có thể không log từng request hợp lệ bị từ chối. Trường hợp 2 có thể WARN ở lần timeout và INFO khi kết quả thành công. Trường hợp 3 là ERROR ở nơi xác định kết quả cuối; các attempt riêng có thể là WARN hoặc sự kiện có tên khác, tránh ba tầng cùng ghi lại một exception. Trường hợp 4 có thể WARN nếu cần theo dõi fallback, hoặc DEBUG nếu đây là nhánh bình thường không đáng chú ý; phụ thuộc mức suy giảm dịch vụ. Trường hợp 5 đáng ghi ERROR vì thành phần không thể hoạt động. JUL dùng `Level.SEVERE`, còn API `System.Logger` có `Level.ERROR`.

**Bài tập mở rộng:** Thiết kế một sự kiện `payment.failed` có `error_code`, `trace_id`, `attempts`, `outcome` và `duration_ms`; giải thích vì sao các trường đó giúp điều tra. Sau đó nêu cách chứng minh bộ thu thập nhận được bản ghi ERROR và vì sao số bản ghi ERROR không tự động bằng số yêu cầu thất bại.

Khi bạn phân biệt được **mức log của sự kiện**, **trách nhiệm xử lý exception**, **hậu quả của thao tác** và **cách đo tỷ lệ thất bại**, bạn đã sử dụng ERROR như một tín hiệu vận hành có ý nghĩa thay vì một nhãn gắn cho mọi ngoại lệ.