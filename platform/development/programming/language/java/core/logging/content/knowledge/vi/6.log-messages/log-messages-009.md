# Mã sự kiện trong log Java: đặt tên, giữ ổn định và khai thác

## 1. Mã sự kiện là gì?

Khi đọc một dòng log, con người thường chú ý câu thông báo như “Không thể hoàn tất thanh toán”. Nhưng câu chữ có thể được sửa để dễ hiểu hơn, dịch sang tiếng Việt/tiếng Anh hoặc bổ sung dữ liệu. Nếu biểu đồ, cảnh báo và chương trình phân tích phải tìm kiếm chính xác chuỗi thông báo ấy, chỉ một thay đổi câu chữ cũng có thể làm hệ thống giám sát mất khả năng nhận diện sự kiện.

**Mã sự kiện (event code)** là một định danh **ổn định cho loại sự kiện** mà ứng dụng muốn ghi nhận. Ví dụ:

- `checkout.started`: một lượt xử lý thanh toán bắt đầu.
- `payment.retry_scheduled`: hệ thống đã lên lịch thử lại một bước thanh toán.
- `payment.failed`: một thao tác thanh toán đã kết thúc với kết quả thất bại.
- `order.created`: đơn hàng mới được tạo thành công.

Mã này trả lời **“điều gì đã xảy ra?”** ở cấp *loại sự kiện*. Thông điệp log giải thích sự kiện bằng ngôn ngữ tự nhiên; các trường ngữ cảnh cung cấp chi tiết của *lần xảy ra cụ thể*.

Ví dụ hai bản ghi:

```text
INFO event_code=order.created order_id=O-18 trace_id=tr-42 message="Đã tạo đơn hàng"
INFO event_code=order.created order_id=O-19 trace_id=tr-57 message="Tạo đơn thành công"
```

Hai dòng có nội dung thông báo khác nhau nhưng cùng loại sự kiện `order.created`. Ta có thể đếm và phân nhóm theo `event_code` mà không phụ thuộc vào câu chữ; đồng thời dùng `order_id` hoặc `trace_id` để xem chi tiết từng lần xử lý.

Mã sự kiện **không tự làm log trở thành có cấu trúc**. Cần ghi mã vào một trường có tên thống nhất (ví dụ `event_code`), được bộ thu thập phân tích đúng; lý tưởng là dùng logging có cấu trúc với các trường dữ liệu có kiểu, chẳng hạn JSON.

### Mục đích của mã sự kiện

1. **Phân loại nhất quán:** biết dòng log đang nói về hành vi nào.
2. **Tìm kiếm và điều tra:** lọc `event_code=payment.failed` thay vì tìm nhiều cách diễn đạt “thanh toán lỗi”.
3. **Tổng hợp số liệu:** thống kê số lần tạo đơn, thất bại, thử lại theo khoảng thời gian và theo dịch vụ.
4. **Cảnh báo có ngữ nghĩa:** kết hợp mã sự kiện, kết quả, số lượng/tỷ lệ và thời gian để xác định bất thường.
5. **Liên kết tài liệu vận hành:** từ một mã ổn định tra được định nghĩa, ý nghĩa nghiệp vụ, chủ sở hữu và cách xử lý.
6. **Giảm phụ thuộc vào ngôn ngữ:** câu mô tả có thể được sửa/dịch mà truy vấn dùng mã vẫn hoạt động.

## 2. Phân biệt mã sự kiện với các thông tin dễ nhầm

Một bản ghi hữu ích có thể chứa nhiều “mã”, nhưng chúng có trách nhiệm khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ | Tính ổn định |
| --- | --- | --- | --- |
| **Mã sự kiện** (`event_code`) | Loại sự kiện nào xảy ra? | `payment.failed` | Ổn định giữa nhiều lần xảy ra cùng loại. |
| **Thông điệp** (`message`) | Người đọc cần hiểu gì? | `Không thể hoàn tất thanh toán` | Có thể chỉnh sửa câu chữ. |
| **Mã lỗi** (`error_code`) | Vì sao lỗi hoặc lỗi thuộc nhóm nào? | `UPSTREAM_TIMEOUT` | Ổn định theo loại nguyên nhân, có thể vắng mặt khi không lỗi. |
| **Mức log** (`level`) | Mức độ cần chú ý là gì? | `INFO`, `WARN`, `ERROR` | Chính sách phân loại nghiêm trọng. |
| **Tên logger** (`logger_name`) | Thành phần nào phát log? | `com.example.payment.Service` | Thường theo package/lớp; có thể đổi khi refactor. |
| **ID của lần xảy ra** (`event_id`) | Đây là bản ghi sự kiện riêng biệt nào? | `evt-9a21` | Duy nhất theo lần xảy ra nếu hệ thống cấp ID. |
| **ID truy vết** (`trace_id`) | Các bước này thuộc luồng xử lý nào? | `tr-42` | Có thể chung giữa nhiều sự kiện của cùng trace. |
| **ID nghiệp vụ** (`order_id`) | Sự kiện liên quan đối tượng nào? | `O-18` | Phân biệt từng đơn hàng, cần kiểm soát quyền ghi. |
| **Trạng thái/kết quả** (`outcome`) | Xử lý thành công hay thất bại? | `success`, `failed` | Tập giá trị thường có giới hạn. |

Chẳng hạn, `payment.failed` là **loại sự kiện**, còn `UPSTREAM_TIMEOUT` là **nguyên nhân**. Một lỗi timeout có thể xảy ra ở nhiều loại sự kiện; ngược lại, `payment.failed` có thể do timeout, cấu hình sai hoặc lỗi dữ liệu. Không nên dùng hai trường này thay cho nhau.

**Mã sự kiện khác ID sự kiện:** 1.000 đơn hàng được tạo có thể phát 1.000 bản ghi mang cùng `event_code=order.created`. Nếu cần nhận diện từng bản ghi để xử lý trùng, dùng `event_id` riêng hoặc một khóa định danh sự kiện đáng tin cậy. `trace_id` giúp liên kết nhiều bước, không mặc nhiên phân biệt duy nhất từng dòng log.

Mã sự kiện cũng **không đồng nghĩa với HTTP status**. `order.created` có thể gắn response 201, nhưng sự kiện nội bộ không bắt buộc gắn HTTP. Một lỗi HTTP 500 có thể liên quan nhiều sự kiện kỹ thuật. Cần dùng trường riêng nếu muốn phân tích status.

## 3. Thiết kế tên mã sự kiện dễ hiểu và dễ duy trì

Không có một chuẩn đặt tên bắt buộc cho tất cả ứng dụng Java. Quan trọng nhất là **đội phát triển thống nhất một quy ước và giữ được ngữ nghĩa ổn định**.

Một quy ước dễ đọc là:

```text
<miền nghiệp vụ hoặc thành phần>.<hành động hoặc kết quả>
```

Ví dụ:

```text
order.created
order.cancelled
payment.authorized
payment.retry_scheduled
payment.failed
inventory.reservation_failed
security.login_denied
job.completed
```

Các khuyến nghị thực tế:

- **Có miền và hành động rõ ràng:** `order.created` dễ hiểu hơn `SUCCESS_01`. Tránh tên chỉ nói mức độ như `common.error` vì không mô tả điều gì xảy ra.
- **Thống nhất dạng chữ:** chẳng hạn chữ thường, từ cách nhau bằng dấu gạch dưới trong mỗi phần, dấu chấm giữa miền và sự kiện. Chọn một quy tắc rồi áp dụng nhất quán.
- **Không chứa dữ liệu động:** không tạo `order.123.created` hoặc `payment.failed.user_42`. ID thuộc trường riêng.
- **Diễn đạt kết quả đúng thời điểm:** `payment.retry_scheduled` chỉ nên phát **sau khi lập lịch thử lại thành công**; `payment.failed` chỉ khi đã xác định thất bại theo định nghĩa nghiệp vụ.
- **Đủ cụ thể để truy vấn:** `order.created` khác `order.creation_failed`; `request.completed` khác `request.started`. Nếu hai tình huống có mẫu số, chủ sở hữu hoặc cách xử lý khác nhau, có thể cần mã khác nhau.
- **Không chia nhỏ vô hạn:** nếu nguyên nhân khác nhau nhưng sự kiện vẫn là “thanh toán thất bại”, giữ `payment.failed` và phân loại bằng `error_code`. Đừng tạo hàng trăm mã chỉ để mã hóa mọi thông điệp lỗi.
- **Tránh tên dễ đổi theo giao diện:** `button_blue_clicked` có thể nhanh lỗi thời; đặt tên theo hành vi có ý nghĩa nghiệp vụ khi đó là tín hiệu cần lưu lâu dài.

Mã có thể là **chuỗi** hoặc **số** tùy quy ước. Ví dụ `PAY_0042` cũng là một mã hợp lệ nếu có bảng tra cứu. Tuy nhiên, tên có ngữ nghĩa thường dễ đọc và dễ điều tra hơn một con số chỉ có ý nghĩa khi mở tài liệu đối chiếu.

### Sự kiện “bắt đầu”, “hoàn tất” và “thất bại”

Nhóm sự kiện thường phản ánh vòng đời một thao tác:

```text
checkout.started
    |
    +-- payment.retry_scheduled (có thể xảy ra 0..n lần)
    |
    +-- checkout.completed         (kết thúc thành công)
    |
    +-- checkout.failed            (kết thúc thất bại)
```

Đây là **một mô hình minh họa**, không phải mọi checkout đều phải có đúng các mã trên.

Để tránh đếm sai, cần nêu rõ ý nghĩa của từng mã. Ví dụ `checkout.started` đếm số lượt bắt đầu, không đếm số lượt đã hoàn tất; một request đang chạy hoặc bị dừng bất thường có thể có sự kiện bắt đầu nhưng chưa có kết thúc. Nếu muốn tính tỷ lệ thành công, phải định nghĩa mẫu số, tiêu chí hoàn tất, khoảng thời gian và cách xử lý sự kiện bị mất/trùng.

Trong hệ thống có retry, `payment.attempt_failed` có thể phát cho mỗi lần thử, còn `payment.failed` chỉ phát **một lần khi thao tác logic thất bại cuối cùng**. Khi thống kê “số giao dịch thất bại”, cần truy vấn đúng mã và vẫn xem xét khả năng ghi trùng/mất của pipeline.

## 4. Một bản ghi sự kiện nên chứa gì?

Mã sự kiện có giá trị nhất khi đi kèm ngữ cảnh có kiểu và quy ước rõ ràng:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "event_code": "payment.failed",
  "message": "Không thể hoàn tất thanh toán",
  "error_code": "UPSTREAM_TIMEOUT",
  "outcome": "failed",
  "attempts": 3,
  "duration_ms": 1842,
  "trace_id": "tr-42",
  "order_id": "O-18"
}
```

Ý nghĩa thiết kế:

- `timestamp`: mốc thời gian, ưu tiên ISO 8601 có múi giờ rõ ràng; không nhầm thời gian xảy ra với thời gian collector nhận.
- `service`, `environment`, `version`: xác định dịch vụ, môi trường và bản phát hành; hỗ trợ so sánh trước/sau triển khai.
- `event_code`: định danh ổn định để lọc và tổng hợp.
- `message`: giải thích dễ đọc; có thể dịch hoặc bổ sung diễn đạt mà không đổi mã.
- `level`: mức nghiêm trọng. Một sự kiện thất bại thường ở mức cao, nhưng chính sách mức phụ thuộc hậu quả.
- `error_code`: nguyên nhân cụ thể khi có lỗi, không thay thế mã sự kiện.
- `outcome`: kết quả để phân biệt các tình huống thành công/thất bại nếu một loại sự kiện cần mang nhiều kết quả.
- `attempts` và `duration_ms`: dùng kiểu số, quy ước rõ “số lần thử” và “mili giây”.
- `trace_id`, `order_id`: dùng để truy tìm; phải đáp ứng quy định bảo mật và phân quyền.

**Nên dùng trường nhất quán**. Nếu một nơi ghi `event_code` và nơi khác ghi `eventId` cho cùng ý nghĩa, dashboard cần logic chuyển đổi khó bảo trì. Nếu hệ thống đã thống nhất tên `event.name` hoặc `event.type`, có thể tiếp tục dùng tên đó; không nhất thiết phải đúng chữ `event_code`. Điều quan trọng là hợp đồng được ghi rõ, ổn định và được backend thu thập đúng.

Ở cấp ứng dụng Java, lời gọi logger có thể ghi chuỗi `event_code=...` để minh họa. Nhưng trong sản phẩm có nhiều nguồn, **logging có cấu trúc** giúp tránh lỗi khi message chứa dấu cách, dấu bằng hoặc ký tự xuống dòng. Cần bảo đảm bộ formatter/encoder tạo đúng JSON hoặc cấu trúc được hệ thống nhận hiểu.

## 5. Ví dụ Java 17 chạy độc lập: khai báo mã sự kiện bằng enum

Khai báo mã bằng `enum` giúp tránh rải chuỗi định danh ở nhiều nơi và hạn chế lỗi gõ nhầm. Ví dụ dùng `java.util.logging` (JUL) của JDK nên **không cần thư viện ngoài**. JUL dùng `INFO`, `WARNING` và `SEVERE`; hệ thống dùng SLF4J thường gọi các mức tương ứng là `INFO`, `WARN` và `ERROR`.

Ví dụ cố định dữ liệu đầu vào để stdout luôn giống nhau. Ở ứng dụng thật, mã sự kiện phát tại đúng điểm chuyển trạng thái, còn ID được lấy từ ngữ cảnh xử lý thực tế.

Lưu thành **`EventCodeDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class EventCodeDemo {
    enum EventCode {
        CHECKOUT_STARTED("checkout.started", Level.INFO),
        PAYMENT_RETRY_SCHEDULED("payment.retry_scheduled", Level.WARNING),
        PAYMENT_FAILED("payment.failed", Level.SEVERE);

        private final String value;
        private final Level level;

        EventCode(String value, Level level) {
            this.value = value;
            this.level = level;
        }
    }

    private static void emit(
            Logger logger,
            EventCode code,
            String traceId,
            String orderId,
            String errorCode) {

        String message = "event_code=" + code.value
                + " trace_id=" + traceId
                + " order_id=" + orderId
                + (errorCode == null ? "" : " error_code=" + errorCode);

        logger.log(code.level, message);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(record.getLevel().getName()
                        + " " + record.getMessage());
            }

            @Override
            public void flush() {
                // Ví dụ in trực tiếp; không có bộ đệm riêng.
            }

            @Override
            public void close() {
                // Không sở hữu System.out nên không đóng luồng này.
            }
        };

        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, EventCode.CHECKOUT_STARTED,
                "tr-42", "O-18", null);
        emit(logger, EventCode.PAYMENT_RETRY_SCHEDULED,
                "tr-42", "O-18", "UPSTREAM_TIMEOUT");
        emit(logger, EventCode.PAYMENT_FAILED,
                "tr-42", "O-18", "UPSTREAM_TIMEOUT");

        logger.removeHandler(output);
        output.close();
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac EventCodeDemo.java
java EventCodeDemo
```

**Stdout chính xác:**

```text
INFO event_code=checkout.started trace_id=tr-42 order_id=O-18
WARNING event_code=payment.retry_scheduled trace_id=tr-42 order_id=O-18 error_code=UPSTREAM_TIMEOUT
SEVERE event_code=payment.failed trace_id=tr-42 order_id=O-18 error_code=UPSTREAM_TIMEOUT
```

Giải thích:

1. `EventCode` chứa **một danh mục hữu hạn** định nghĩa mã và mức log ví dụ. Thay vì gõ `payment.failed` ở nhiều chỗ, mã gọi `EventCode.PAYMENT_FAILED` để giảm sai chính tả.
2. Hàm `emit` lấy mã từ `enum`, ghép trường liên kết và nguyên nhân tùy chọn. `trace_id=tr-42` giống nhau ở ba dòng, cho phép tìm cả luồng xử lý; mã sự kiện khác nhau vì **loại sự kiện** khác nhau.
3. `error_code=UPSTREAM_TIMEOUT` có thể xuất hiện ở cả sự kiện đã lên lịch thử lại và sự kiện cuối cùng thất bại. Cùng nguyên nhân không có nghĩa cùng một sự kiện.
4. `logger.setUseParentHandlers(false)` ngăn thêm dòng từ logger cha; handler tùy chỉnh in ra stdout để kết quả dễ kiểm tra.
5. `output.setLevel(Level.ALL)` tránh loại thêm bản ghi ở handler. Logger nguồn ở mức INFO cho phép cả WARNING và SEVERE. Nếu handler đặt WARNING, dòng checkout.started sẽ không được in.
6. Handler ở đây chỉ là **công cụ minh họa**, không tạo JSON chuẩn, không xử lý bất đồng bộ, không gửi log qua mạng và không ghi stack trace. Trong production, dùng backend/encoder phù hợp và kiểm tra khả năng mất log.

**Giới hạn cần nhớ:** ví dụ ghép chuỗi từ dữ liệu cố định. Khi giá trị đến từ request/user, không được đưa thẳng dữ liệu chưa kiểm soát vào thông điệp có định dạng tùy ý: có thể chứa ký tự xuống dòng hoặc dữ liệu nhạy cảm. Dùng các trường có kiểu, kiểm soát dữ liệu và encoder đáng tin cậy. Việc gắn một `Level` cố định cho từng mã trong enum cũng chỉ là chính sách minh họa; hệ thống thực tế có thể cần định nghĩa mức theo ngữ cảnh, miễn là ý nghĩa mã không bị thay đổi mập mờ.

## 6. Dùng mã sự kiện với logging có cấu trúc

Nếu ứng dụng sử dụng **SLF4J 2.x** và backend hỗ trợ trường key-value, có thể viết ví dụ sau bên trong một phương thức Java đã có `log` và `orderId`:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .log("Đã tạo đơn hàng");
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: cần thư viện SLF4J 2.x, logger `log`, biến `orderId` và backend được cấu hình để xuất những trường key-value này. Không phải mọi pattern hoặc encoder đều tự động hiển thị các trường bổ sung; cần kiểm tra output thực tế.

Một lựa chọn khác là dùng MDC (Mapped Diagnostic Context) cho **ngữ cảnh dùng chung trong một luồng xử lý**, ví dụ `trace_id` hoặc `request_id`, khi framework/backend hỗ trợ. MDC không tự biến `event_code` thành sự kiện; mã sự kiện vẫn cần được gắn đúng lúc xảy ra sự kiện. Trong xử lý bất đồng bộ hoặc chuyển luồng, cần xác nhận ngữ cảnh MDC được lan truyền và dọn dẹp đúng, tránh lẫn dữ liệu giữa request.

Lựa chọn JUL, SLF4J + Logback hay Log4j2 không làm thay đổi nguyên lý: **mã phải giữ ý nghĩa ổn định và được xuất thành trường truy vấn được**. Tên API khác nhau chỉ ảnh hưởng cách khai báo logger, formatter, appender và cấu hình mức.

## 7. Danh mục mã sự kiện như một hợp đồng

Trong dự án có nhiều service, mã sự kiện nên được quản lý bằng một **danh mục (event catalog)** hoặc tài liệu được kiểm tra khi thay đổi mã. Không nhất thiết phải tạo một thư viện chung quá lớn; có thể lưu định nghĩa cạnh module phát sự kiện và chuẩn hóa các trường cốt lõi.

Mỗi mã có thể có:

| Thuộc tính | Ví dụ cho `payment.failed` |
| --- | --- |
| Mã | `payment.failed` |
| Mô tả | Một thao tác thanh toán logic đã kết thúc thất bại |
| Chủ sở hữu | Nhóm phụ trách dịch vụ thanh toán |
| Thời điểm phát | Sau khi các đường xử lý, fallback và retry đã kết luận thất bại |
| Mức mặc định | ERROR/SEVERE, theo API thực tế |
| Trường bắt buộc | `trace_id`, `error_code`, `outcome`; `order_id` nếu được phép |
| Trường tùy chọn | `attempts`, `duration_ms`, `dependency` |
| Dữ liệu không được ghi | Token, mật khẩu, payload thanh toán, thông tin nhạy cảm |
| Kênh tiêu thụ | Tìm kiếm log, dashboard lỗi, quy trình điều tra |
| Cách xử lý | Xem mã lỗi, trace, phụ thuộc, tình trạng thử lại |
| Vòng đời | Đang dùng, sắp ngừng dùng, đã thay thế |

### Đổi mã mà không làm hỏng người tiêu thụ

Giả sử hệ thống đã dùng `payment.failed` trong dashboard và cảnh báo. Đổi sang `checkout.payment.error` chỉ vì thích tên mới có thể làm truy vấn cũ không còn thấy dữ liệu. Cách làm nên là:

1. Xác nhận ngữ nghĩa cũ và mới có thực sự khác nhau không; nếu chỉ đổi câu thông báo, **giữ nguyên mã**.
2. Nếu bắt buộc thay mã, cập nhật danh mục, nơi phát, bộ lọc, cảnh báo, dashboard và tài liệu vận hành.
3. Khi cần chuyển đổi dần, triển khai cơ chế chuyển tiếp rõ ràng để người tiêu thụ hiểu cả hai mã trong giai đoạn di trú; lưu ý không đếm trùng nếu phát hai sự kiện đại diện cùng một lần.
4. Chỉ ngừng hỗ trợ mã cũ sau khi đã kiểm tra người tiêu thụ và khoảng thời gian lưu log liên quan.

**Không dùng lại mã cũ cho một ý nghĩa mới.** Ví dụ `order.created` vốn có nghĩa “đã lưu đơn thành công” thì sau này không được đổi thành “vừa bắt đầu quá trình tạo đơn”. Sự thay đổi ngữ nghĩa ấy làm thống kê lịch sử và logic cảnh báo trở nên sai dù tên trường không đổi.

Nếu cần diễn giải cách phát mới hoặc nội dung trường thay đổi lớn, dùng tài liệu phiên bản và chính sách tương thích. Chỉ thêm hậu tố `v2` khi thay đổi thực sự làm hợp đồng không còn tương thích; tránh thêm version cho mọi thay đổi nhỏ của câu mô tả.

## 8. Từ mã sự kiện đến truy vấn và dashboard

Khi log được thu thập đúng, có thể đặt các câu hỏi có ngữ nghĩa ổn định:

- Trong 15 phút gần đây, `payment.failed` xảy ra bao nhiêu lần ở `service=checkout`, `environment=prod`?
- Tỷ lệ `payment.retry_scheduled` thay đổi thế nào sau khi triển khai một phiên bản mới?
- `payment.failed` thường đi kèm `error_code` nào?
- Lấy `trace_id` từ một sự kiện thất bại, các sự kiện trước đó trong cùng luồng xử lý là gì?
- Sự kiện `order.created` có phát nhiều lần cho cùng một thao tác logic do retry hay do pipeline thu thập gửi lại không?

Một truy vấn SQL **minh họa** (giả sử bộ thu thập đã đưa các trường vào bảng `logs`):

```sql
SELECT event_code, COUNT(*) AS total
FROM logs
WHERE service = 'checkout'
  AND environment = 'prod'
  AND timestamp >= :from_time
  AND timestamp < :to_time
GROUP BY event_code
ORDER BY total DESC;
```

Cú pháp tham số `:from_time`/`:to_time` phụ thuộc công cụ truy vấn thực tế; đây không phải lệnh chạy trực tiếp trên mọi hệ thống log. Muốn phân nhóm theo nguyên nhân, thêm `error_code` vào `SELECT` và `GROUP BY`. Muốn xem luồng xử lý cụ thể, lọc theo `trace_id`.

**Đếm log không mặc nhiên bằng đếm sự kiện nghiệp vụ thật.** Có thể mất bản ghi khi process dừng, hàng đợi ghi log đầy, collector bị nghẽn hoặc sự kiện bị lấy mẫu; có thể bị trùng khi đường truyền gửi lại, khi nhiều tầng cùng log một kết quả hoặc khi một thao tác retry nhiều lần. Những chỉ số dùng làm SLI/SLO quan trọng nên có định nghĩa và cơ chế thu thập đủ tin cậy. Mã sự kiện giúp **phân loại đúng dữ liệu có được**, không tự bảo đảm dữ liệu đầy đủ hoặc đúng một lần.

### Chọn trường nào làm nhóm thống kê?

`event_code`, `service`, `environment`, `status`, `error_code` thường là tập giá trị tương đối kiểm soát được nếu có quản trị. Trái lại, `trace_id`, `request_id`, `order_id` có thể có hàng triệu giá trị riêng, phù hợp **tìm kiếm chi tiết** chứ không phù hợp gắn làm metric label ở mọi phép đo. Phân biệt mục đích **tìm bản ghi** và **gom nhóm để vẽ biểu đồ**.

Nếu sự kiện có tần suất cao, cần cân đối log đầy đủ, lấy mẫu và metric trực tiếp. Ví dụ, toàn bộ sự kiện `request.completed` có thể dùng để điều tra, nhưng hệ thống vận hành vẫn cần counter/histogram trực tiếp để tính RPS và phân vị độ trễ khi log có thể bị lấy mẫu.

## 9. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tìm kiếm bằng nguyên văn `message` | Sửa câu chữ hoặc đổi ngôn ngữ làm truy vấn gãy | Truy vấn bằng `event_code` ổn định. |
| Dùng `event_code` làm request ID | Một mã khác nhau cho mọi request, mất khả năng phân nhóm | Dùng mã cố định theo loại; đưa ID riêng vào trường tương ứng. |
| Dùng mã `error_code` thay cho `event_code` | Không biết thất bại thuộc thao tác nào | Ghi rõ loại sự kiện và nguyên nhân ở hai trường. |
| Phát `payment.failed` cho từng lần thử lại | Đếm một job thành nhiều thất bại cuối | Dùng mã riêng cho attempt và final outcome. |
| Mọi log dùng `generic.error` | Không truy vấn được bản chất hành vi | Định nghĩa mã có miền và hành động rõ. |
| Dùng mã có thông tin người dùng, URL thô hoặc token | Phát sinh cardinality lớn, rò rỉ dữ liệu | Mã tĩnh; dữ liệu ngữ cảnh được lọc và bảo vệ. |
| Đổi tên mã tùy ý | Dashboard và cảnh báo mất dữ liệu | Quản trị mã như hợp đồng, có di trú khi cần. |
| Ghi mã trong chuỗi tự do nhưng collector không parse | Bộ lọc không thấy trường `event_code` | Dùng encoder có cấu trúc và kiểm tra đầu ra. |
| Phát sự kiện trước khi thực sự hoàn tất | Log “thành công” cho thao tác cuối cùng thất bại | Đặt điểm phát ở ranh giới kết quả đã xác nhận. |
| Đếm số dòng mà không kiểm soát mất/trùng | Chỉ số sai lệch | Thiết kế thu thập, ID sự kiện, dedupe và metric phù hợp. |
| Ghi dữ liệu nhạy cảm trong message hoặc trường ngữ cảnh | Mở rộng phạm vi rò rỉ qua kho log | Chỉ ghi dữ liệu được phép, che/bỏ bí mật và phân quyền truy cập. |

## 10. Bài tập vận dụng

Một dịch vụ xử lý đơn hàng thực hiện:

1. Nhận yêu cầu tạo đơn.
2. Kiểm tra tồn kho thành công.
3. Gọi thanh toán bị timeout lần đầu và đã lên lịch thử lại.
4. Lần thử tiếp theo thành công.
5. Đơn hàng được lưu thành công.

**Yêu cầu A:** Hãy đề xuất mã sự kiện rõ nghĩa cho từng bước cần theo dõi. Phân biệt mã sự kiện, mã lỗi và ID truy vết.

**Gợi ý:** Có thể chọn `order.creation_started`, `inventory.checked`, `payment.retry_scheduled`, `payment.authorized`, `order.created`. Ở bước 3, `event_code=payment.retry_scheduled` và `error_code=UPSTREAM_TIMEOUT` mô tả hai khía cạnh khác nhau. Tất cả có thể mang cùng `trace_id` để truy vết một luồng xử lý. Các mã được đề xuất là ví dụ quy ước; dự án có thể dùng mã khác nếu ngữ nghĩa và hợp đồng rõ ràng.

**Yêu cầu B:** Có nên phát `payment.failed` sau bước 3 hay không? Khi nào phát mã ấy?

**Gợi ý:** Nếu định nghĩa `payment.failed` là **thất bại cuối cùng của thao tác**, chưa nên phát vì còn đường thử lại và bước 4 đã thành công. Nếu muốn biết từng lượt thử lỗi, dùng `payment.attempt_failed` và lưu số thứ tự attempt. Chỉ phát `payment.failed` khi kết quả cuối cùng thực sự thất bại theo chính sách nghiệp vụ.

**Yêu cầu C:** Một hệ thống có 50 bản ghi `order.created` trong 1 phút. Có thể kết luận chính xác đã tạo 50 đơn hàng duy nhất không?

**Gợi ý:** Chưa đủ. Có thể có log trùng do gửi lại, nhiều tầng cùng phát hoặc một thao tác tạo trùng; cũng có thể thiếu log. Cần quy tắc phát sự kiện, khóa nhận diện thao tác hoặc event ID, khả năng thu thập và nguồn dữ liệu nghiệp vụ trước khi kết luận.

**Tự kiểm tra:** Bạn đã nắm chủ đề khi có thể giải thích vì sao `event_code` phải ổn định, phân biệt nó với `message`/`error_code`/`trace_id`, thiết kế mã cho các mốc của một quy trình, xây dựng ví dụ Java có tên mã dùng chung và chỉ ra điều gì có thể làm phép đếm từ log sai lệch.