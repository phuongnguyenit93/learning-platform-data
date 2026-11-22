# Message ổn định trong Java logging

## 1. “Message ổn định” nghĩa là gì?

Một ứng dụng có thể ghi hàng triệu dòng log nhưng vẫn khó tra cứu nếu cùng một loại sự kiện được mô tả bằng nhiều câu khác nhau. Ví dụ, khi thanh toán bị từ chối:

```text
Đơn ORD-101 không thanh toán được vì thẻ hết hạn
Thanh toán ORD-102 thất bại: thẻ đã hết hạn
Không thể xử lý thanh toán của đơn ORD-103 (expired card)
```

Người đọc hiểu các câu này gần giống nhau, nhưng công cụ tìm kiếm, thống kê hay hệ thống cảnh báo có thể xem chúng là những mẫu văn bản khác nhau. Việc gắn mã đơn hàng, lý do và câu chữ theo cách tùy hứng khiến khó trả lời: “Có bao nhiêu lần thanh toán bị từ chối vì cùng một nguyên nhân?”.

**Message ổn định** là cách thiết kế thông điệp log có **mẫu diễn đạt (message template) và ý nghĩa nhất quán** cho cùng một loại sự kiện; phần thay đổi được đưa vào **tham số hoặc trường dữ liệu riêng**. Ví dụ:

```text
Mẫu: event=payment_result order_id={0} outcome={1} reason_code={2}

Lần 1: event=payment_result order_id=ORD-101 outcome=DECLINED reason_code=CARD_EXPIRED
Lần 2: event=payment_result order_id=ORD-102 outcome=DECLINED reason_code=CARD_EXPIRED
Lần 3: event=payment_result order_id=ORD-103 outcome=APPROVED reason_code=NONE
```

Cấu trúc và tên trường được giữ nguyên; giá trị đơn hàng, kết quả và nguyên nhân thay đổi theo lần xử lý. Người vận hành có thể lọc bằng `event=payment_result` rồi nhóm theo `outcome` hoặc `reason_code`.

**Ổn định không có nghĩa mọi bản ghi phải chứa cùng một chuỗi ký tự.** Nếu mã đơn hàng thay đổi thì bản ghi sau khi định dạng đương nhiên thay đổi. Điều cần giữ ổn định là *loại sự kiện, mẫu diễn đạt, tên trường và ngữ nghĩa của từng trường*. Sự kiện khác nhau về ý nghĩa nghiệp vụ vẫn nên có tên hoặc mẫu phù hợp riêng.

Đây là chủ đề **thiết kế nội dung log** thuộc kiến trúc Java logging; nó liên quan tới logger, formatter, handler/appender và hệ thống tìm kiếm log, nhưng trọng tâm là làm cho từng thông điệp có thể đọc, lọc và tổng hợp lâu dài.

## 2. Phân biệt mẫu log, thông điệp đã định dạng và dữ liệu ngữ cảnh

Một bản ghi thường có ba lớp thông tin:

1. **Mẫu thông điệp:** phần cố định mà mã nguồn dùng để mô tả sự kiện, ví dụ `"event=order_created order_id={0}"` trong `java.util.logging`.
2. **Tham số sự kiện:** giá trị thay đổi theo lần chạy, ví dụ `"ORD-101"`, `"ORD-102"`.
3. **Metadata của log:** mức `INFO`/`WARNING`, thời gian, logger name, thread, tên dịch vụ, mã tương quan... Một số trường do framework hoặc hệ thống thu thập bổ sung.

Luồng hình thành một dòng log có thể hình dung như sau:

```text
Mã ứng dụng gọi Logger
    |
    +-- mẫu cố định:  "event=order_created order_id={0}"
    +-- tham số:     ["ORD-101"]
    +-- mức log:     INFO
    |
    v
LogRecord (mẫu, tham số, mức và metadata)
    |
    v
Formatter / Encoder
    |
    v
"INFO event=order_created order_id=ORD-101"
    |
    v
Console / File / Hệ thống thu thập
```

Ở ví dụ này, chuỗi cuối cùng chứa giá trị cụ thể nên khác giữa các yêu cầu. Việc giữ mẫu ổn định giúp mã nguồn có quy ước rõ ràng; việc giữ **trường có cấu trúc** giúp hệ thống phân tích dễ truy vấn.

**Lưu ý:** log dạng `key=value` trong một chuỗi chưa mặc nhiên là “structured logging” đúng nghĩa. Nếu đầu ra chỉ là văn bản, collector có thể phải dùng parser để tách từng trường. Với backend hỗ trợ JSON hoặc các trường thuộc tính riêng của log event, hãy dùng khả năng đó khi cần tra cứu ổn định; đừng tự ghép JSON thủ công.

## 3. Vì sao message ổn định có ích?

### Dễ tìm kiếm và nhóm sự kiện

Với tên sự kiện cố định như `payment_result`, một truy vấn có thể lọc tất cả kết quả thanh toán, sau đó xem riêng `outcome=DECLINED` và nhóm theo `reason_code`. Nếu mỗi nhánh code viết một câu tùy ý, quy tắc lọc phải phụ thuộc nhiều biến thể tiếng Việt/tiếng Anh, dấu câu và cách diễn đạt.

### Giúp cảnh báo chính xác hơn

Một bộ cảnh báo có thể theo dõi số lần `reason_code=GATEWAY_TIMEOUT` trong khoảng thời gian nhất định. Mã lý do ổn định ít bị ảnh hưởng bởi việc người phát triển thay câu “Kết nối cổng thanh toán thất bại” thành “Lỗi gọi payment gateway”. Điều kiện cảnh báo dựa vào **trường và mã** đáng tin hơn điều kiện phụ thuộc nguyên văn văn bản hiển thị.

### Có thể so sánh theo phiên bản

Nếu bản triển khai hôm qua và hôm nay dùng cùng tên sự kiện và cùng ý nghĩa trường, ta có thể so sánh số lượng và tỷ lệ. Nếu hôm nay đổi `payment_declined` thành `pay_rejected` mà không cập nhật truy vấn, dashboard có thể hiển thị sai dù nghiệp vụ vẫn hoạt động.

### Hỗ trợ điều tra một trường hợp cụ thể

Mẫu ổn định không thay thế thông tin ngữ cảnh: mỗi bản ghi vẫn cần định danh liên quan như `order_id`, `request_id` hay `correlation_id`. Những trường đó giúp tìm một trường hợp cụ thể; tên sự kiện giúp so sánh trường hợp ấy với các trường hợp cùng loại.

### Giúp xác định phạm vi thay đổi

Khi mẫu message trở thành đầu vào của truy vấn, alert, parser hoặc báo cáo, việc đổi mẫu là thay đổi **hợp đồng quan sát hệ thống**. Đặt tên, kiểm thử và xem xét thay đổi log nghiêm túc giúp tránh làm hỏng công cụ vận hành bên ngoài mã Java.

## 4. Những phần nào nên ổn định, phần nào được thay đổi?

| Thành phần | Cách thiết kế | Ví dụ |
| --- | --- | --- |
| Tên sự kiện | Có quy ước, phản ánh một loại hành vi xác định | `payment_result`, `order_created` |
| Mẫu thông điệp | Giữ cấu trúc khi cùng một sự kiện lặp lại | `"event=payment_result order_id={0} outcome={1}"` |
| Tên trường | Thống nhất dấu, chữ hoa/thường, cách ghép từ | `order_id` thay vì lúc `orderId`, lúc `order-number` |
| Ý nghĩa trường | Một trường có cùng đơn vị/kiểu dữ liệu | `duration_ms` luôn tính bằng mili giây |
| Mã kết quả/lý do | Có bộ giá trị được quản lý, tránh câu chữ ngẫu nhiên | `APPROVED`, `DECLINED`, `CARD_EXPIRED` |
| Mức log | Theo mức độ ảnh hưởng và quy tắc vận hành | `INFO` cho từ chối hợp lệ, `SEVERE` cho lỗi nghiêm trọng |
| Giá trị theo lần xử lý | Được thay đổi, truyền bằng tham số hoặc thuộc tính | `order_id=ORD-101`, `correlation_id=req-7` |
| Thời gian và vị trí phát | Mỗi bản ghi có giá trị riêng | Timestamp, service, instance, trace id |
| Dữ liệu nhạy cảm | Không đưa trực tiếp vào message | Không ghi token, mật khẩu, số thẻ |

Không cần ép **mọi loại sự kiện** dùng chung một message mơ hồ như `"Action executed"`. Ví dụ `order_created` và `order_cancelled` là hai sự kiện khác nhau, dù cả hai có `order_id`. Gộp chúng thành `"Order processed"` mà không có mã hành động hoặc kết quả sẽ làm mất ý nghĩa.

Mặt khác, cùng loại kết quả thanh toán được chấp thuận hoặc bị từ chối có thể dùng một mẫu `payment_result` với `outcome` khác nhau, nếu hệ thống muốn phân tích chúng như những kết quả của cùng bước xử lý. Đây là lựa chọn mô hình hóa theo miền nghiệp vụ, cần được giữ nhất quán.

## 5. Ví dụ Java 17+ với mẫu thông điệp cố định

`java.util.logging` (JUL) có sẵn trong JDK hỗ trợ thông điệp có tham số. Trong JUL, mẫu dùng ký hiệu kiểu `{0}`, `{1}`, `{2}`; `Formatter.formatMessage(LogRecord)` xử lý các tham số này theo cơ chế định dạng của JUL.

Chương trình dưới đây có một hằng mẫu `PAYMENT_RESULT_TEMPLATE`. Ba lần xử lý thay đổi mã đơn, kết quả và mã lý do nhưng **không thay template**. Handler được cấu hình một lần để đầu ra dễ kiểm tra.

Lưu toàn bộ mã vào tệp **`StableLogMessageDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StableLogMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(StableLogMessageDemo.class.getName());

    private static final String PAYMENT_RESULT_TEMPLATE =
            "event=payment_result order_id={0}"
            + " outcome={1} reason_code={2}";

    private StableLogMessageDemo() {
    }

    private static void recordPayment(
            String orderId, String outcome, String reasonCode) {
        LOG.log(Level.INFO, PAYMENT_RESULT_TEMPLATE,
                new Object[] {orderId, outcome, reasonCode});
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            recordPayment("ORD-101", "APPROVED", "NONE");
            recordPayment("ORD-102", "DECLINED", "CARD_EXPIRED");
            recordPayment("ORD-103", "DECLINED", "INSUFFICIENT_FUNDS");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 StableLogMessageDemo.java
java StableLogMessageDemo
```

**stderr** nhận ba dòng từ `ConsoleHandler`:

```text
INFO event=payment_result order_id=ORD-101 outcome=APPROVED reason_code=NONE
INFO event=payment_result order_id=ORD-102 outcome=DECLINED reason_code=CARD_EXPIRED
INFO event=payment_result order_id=ORD-103 outcome=DECLINED reason_code=INSUFFICIENT_FUNDS
```

**stdout:** rỗng. Nếu chạy trong terminal, bạn vẫn thấy ba dòng vì terminal thường hiển thị cả stderr lẫn stdout.

### Diễn giải ví dụ

- Hằng `PAYMENT_RESULT_TEMPLATE` giữ phần văn bản cố định. Không tạo một câu khác nhau bằng chuỗi `if/else` cho từng lý do thanh toán.
- `recordPayment` chỉ nhận ba giá trị thay đổi. Các giá trị được chuyển trong mảng `Object[]` đến lời gọi `Logger.log`, thay cho ba vị trí `{0}`, `{1}` và `{2}` khi formatter xử lý.
- `LOG` là logger dùng lại theo lớp. Việc message ổn định **không phụ thuộc** vào việc mỗi sự kiện dùng một logger mới; một logger có thể phát nhiều loại sự kiện theo nhiều mẫu ổn định khác nhau.
- `formatMessage(record)` trả về phần thông điệp đã được thay tham số. Còn `record.getMessage()` ở `LogRecord` giữ thông điệp mẫu ban đầu được truyền vào logger, khi không có xử lý đặc biệt khác.
- `setUseParentHandlers(false)` ngăn logger này tiếp tục chuyển sự kiện đến handler của logger cha, giúp đầu ra ví dụ không xuất hiện thêm bản sao.
- Ví dụ dùng `INFO` cho cả kết quả `DECLINED` vì từ chối là một kết quả nghiệp vụ có thể dự kiến. Lỗi kết nối hoặc lỗi chương trình cần chính sách mức log riêng.

**Giới hạn minh họa:** chương trình không thực hiện thanh toán thật và không kết nối kho log tập trung. Các giá trị `orderId`, `outcome` và `reasonCode` được viết cố định trong `main` để đầu ra xác định. Khi lấy từ người dùng hoặc dịch vụ bên ngoài, cần kiểm tra và mã hóa/escape phù hợp trước khi đưa vào log. Dòng `key=value` trong ví dụ là văn bản; backend khác có thể hỗ trợ trường dữ liệu có cấu trúc tốt hơn.

## 6. Cách viết thiếu ổn định và cách sửa

### Sai lầm 1: ghép giá trị động vào mẫu

```java
// Ví dụ minh họa, không phải một chương trình độc lập:
LOG.info("Đơn " + orderId + " bị từ chối vì " + reasonText);
```

Với mỗi `orderId` và `reasonText` khác nhau, câu hoàn chỉnh khác nhau. Nếu muốn thống kê bằng cách nhóm nguyên văn message, mỗi mã đơn có thể thành một nhóm riêng.

Mẫu rõ ràng hơn với JUL:

```java
LOG.log(Level.INFO,
        "event=payment_declined order_id={0} reason_code={1}",
        new Object[] {orderId, reasonCode});
```

Thay một đoạn mô tả tự do bằng mã `reasonCode` có giá trị ổn định. Nếu cần lời giải thích cho người vận hành, có thể hiển thị nội dung dễ hiểu dựa vào mã lý do trong công cụ tra cứu; không dùng câu giải thích tự do làm định danh chính.

**Điểm tinh tế:** phép ghép chuỗi không phải lúc nào cũng sai. Việc nối những hằng văn bản để định nghĩa **một hằng template bất biến** như trong `PAYMENT_RESULT_TEMPLATE` hoàn toàn hợp lý. Vấn đề là đưa giá trị biến thiên vào phần vốn được dùng làm khóa nhóm hoặc phân tích log, khiến template không còn xác định được trước.

### Sai lầm 2: một sự kiện, nhiều cách đặt tên

```text
event=payment_failed
event=payment_rejected
event=pay_denied
```

Nếu chúng đều biểu thị cùng **một loại từ chối theo quy tắc** và được phát từ cùng bước xử lý, hãy chọn một tên thống nhất như `payment_declined` và dùng `reason_code` để phân biệt. Nếu một nhãn biểu thị lỗi kỹ thuật còn nhãn khác là quyết định từ chối của ngân hàng, **không gộp nhầm**: đó là hai ý nghĩa khác nhau, cần mô hình khác nhau.

### Sai lầm 3: thay ý nghĩa của trường mà giữ tên

```text
duration=850        # chỗ này đơn vị là mili giây
duration=0.85       # chỗ khác đơn vị là giây
```

Cùng trường `duration` nhưng khác đơn vị làm dashboard tính sai. Dùng tên như `duration_ms` và thống nhất giá trị là số mili giây; khi cần đổi đơn vị, đổi tên/phiên bản schema và cập nhật nơi tiêu thụ.

### Sai lầm 4: dùng message như mã lỗi

```java
// Không nên lấy nguyên văn câu hiển thị làm hợp đồng nghiệp vụ:
String error = "Payment was declined";
if (error.equals(logMessage)) {
    // ...
}
```

Code nghiệp vụ cần kết quả và mã lỗi dạng dữ liệu có kiểu/quy ước; log là quan sát về những gì đã xảy ra. Đổi câu chữ log không nên thay đổi quyết định nghiệp vụ. Tương tự, truy vấn báo cáo nên dựa vào `event`/`reason_code` thay vì hoàn toàn vào một câu văn.

## 7. Cú pháp tham số khác nhau giữa JUL và SLF4J

Trong hệ sinh thái Java, các API logging không dùng cùng ký hiệu placeholder.

| API | Ví dụ | Cách dùng |
| --- | --- | --- |
| JUL: `java.util.logging.Logger` | `LOG.log(Level.INFO, "order_id={0}", orderId);` | Vị trí tham số dạng `{0}` khi formatter áp dụng |
| SLF4J: `org.slf4j.Logger` | `LOG.info("order_id={}", orderId);` | Tham số dạng `{}` do API SLF4J xử lý |
| Ghép chuỗi thường | `LOG.info("order_id=" + orderId);` | Giá trị được ghép vào chuỗi trước lời gọi log; không còn mẫu riêng với tham số được truyền qua API |

Đoạn SLF4J dưới đây là **ví dụ bên trong một lớp có `LOG`**, cần thư viện SLF4J và implementation như Logback; không chạy chỉ với JDK:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void recordPayment(String orderId, String outcome, String reasonCode) {
    LOG.info("event=payment_result order_id={} outcome={} reason_code={}",
            orderId, outcome, reasonCode);
}
```

Với SLF4J, một backend có thể cung cấp khả năng ghi log có cấu trúc hoặc lưu các tham số trong sự kiện log; mức độ giữ lại thông tin template/đối số ở đích cuối cùng phụ thuộc implementation và cấu hình encoder/appender. Một dòng văn bản hiển thị đã render không tự cho phép suy ra toàn bộ dữ liệu ban đầu được lưu.

Với JUL, dấu `{0}` thuộc cơ chế định dạng dựa trên `MessageFormat` khi formatter xử lý. Lưu ý ký tự nháy đơn `'` và dấu ngoặc nhọn trong mẫu có thể ảnh hưởng cú pháp `MessageFormat`; nếu cần đưa chúng vào phần mẫu, phải tuân thủ quy tắc escape của API đang dùng. Đừng chép nguyên mẫu `"order_id={}"` của SLF4J sang JUL rồi kỳ vọng JUL tự thay tham số.

**Lưu ý hiệu năng:** truyền tham số cho logger thường tránh phải định dạng message trước khi quyết định ghi hay bỏ. Tuy nhiên **biểu thức tạo đối số** vẫn được đánh giá trước lời gọi. Nếu việc tính một giá trị rất tốn công, cần xem cách kiểm tra cấp log hoặc cơ chế supplier/lazy logging của API đang dùng; không đặt side effect nghiệp vụ trong hàm chỉ phục vụ log.

## 8. Message ổn định với log có cấu trúc

Trong hệ thống cần truy vấn lớn, nên xem log như sự kiện có **trường được đặt tên**, thay vì chỉ như câu văn. Một bản ghi minh họa:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "payment-service",
  "event": "payment_result",
  "order_id": "ORD-102",
  "outcome": "DECLINED",
  "reason_code": "CARD_EXPIRED",
  "correlation_id": "req-abc"
}
```

Đây là **JSON minh họa định dạng đích**, không phải đầu ra JSON của chương trình JUL ở phần 5.

Khi thu thập dạng cấu trúc, việc ổn định **`event`, tên trường và kiểu giá trị** thường quan trọng hơn giữ nguyên câu mô tả `message` đến từng dấu cách. Một thông điệp dễ đọc cho người vận hành vẫn có giá trị, nhưng dashboard nên lọc theo trường chuyên dụng.

Một số nguyên tắc thiết kế:

1. **Tên sự kiện biểu thị hành động/kết quả thực sự.** Không đặt `payment_succeeded` khi mới chỉ gửi yêu cầu tới cổng thanh toán. Tên ổn định nhưng sai ngữ nghĩa vẫn gây hiểu lầm.
2. **Dùng mã lý do thuộc tập được kiểm soát.** Ví dụ `CARD_EXPIRED`, `INSUFFICIENT_FUNDS`, `GATEWAY_TIMEOUT`; không dùng toàn bộ câu lỗi từ nhà cung cấp bên ngoài như mã chính.
3. **Giữ kiểu và đơn vị nhất quán.** Ví dụ `duration_ms` là số; `outcome` là chuỗi thuộc bộ giá trị xác định; mã tương quan là chuỗi.
4. **Tách giá trị có số lượng biến thể cao.** `order_id` và `request_id` được dùng để tra cứu từng trường hợp. Một số nền tảng tính phí theo số series/nhãn hoặc số trường được lập chỉ mục; không biến mọi giá trị động thành nhãn lập chỉ mục mà không xem xét chi phí.
5. **Có quy tắc khi trường không áp dụng.** Ví dụ thanh toán thành công có thể dùng `reason_code=NONE` nếu hợp đồng quy định vậy, hoặc bỏ trường theo schema đã thống nhất. Tránh lúc dùng `null`, lúc `"N/A"`, lúc chuỗi rỗng khi chúng mang cùng một ý nghĩa.
6. **Đặt dữ liệu chung ở nơi phù hợp.** Timestamp, service, environment, trace id thường do framework/collector thêm. Không nhất thiết lặp lại tất cả trong từng câu message nếu chúng đã có thành trường riêng.

Mẫu văn bản thuần chỉ phát huy tính ổn định khi công cụ downstream xử lý nó nhất quán. Khi có thể, sử dụng encoder JSON hoặc cơ chế structured attributes của backend thay vì dùng biểu thức chính quy mong manh để phân tích những câu tiếng người.

## 9. Message ổn định và mã tương quan

Hai sự kiện có thể cùng mẫu nhưng thuộc các giao dịch khác nhau:

```text
event=order_updated order_id=ORD-101 correlation_id=req-a result=SUCCESS
event=order_updated order_id=ORD-101 correlation_id=req-b result=SUCCESS
```

Ở đây `event` và tên trường đều ổn định. `order_id` trùng vì cùng đơn hàng, còn `correlation_id` khác nhau vì hai luồng xử lý khác nhau. Nếu ứng dụng xử lý retry, có thể bổ sung `operation_id` hoặc `attempt_id` để phân biệt các lần thử và tránh hiểu hai dòng là hai giao dịch nghiệp vụ hoàn tất.

**Một message ổn định không đủ để truy vết:** nếu thiếu mã tương quan, hàng nghìn dòng có cùng `event=order_updated` vẫn có thể khó ghép thành luồng xử lý chính xác.

Trong môi trường sử dụng MDC (Mapped Diagnostic Context) của một implementation phù hợp, correlation id có thể được gắn vào context theo request rồi đưa vào log qua encoder. Cần dọn context khi kết thúc request và truyền nó qua xử lý bất đồng bộ một cách có chủ đích. Không lưu `currentRequestId` trong một biến `static` thay đổi theo từng request chỉ để tận dụng logger dùng chung.

## 10. Ổn định nhưng không đánh đồng các trạng thái khác nhau

Cùng một bước thanh toán có nhiều khả năng:

```text
event=payment_result outcome=APPROVED
event=payment_result outcome=DECLINED reason_code=CARD_EXPIRED
event=payment_result outcome=FAILED reason_code=GATEWAY_TIMEOUT
```

Ba bản ghi dùng chung tiền tố và cấu trúc, nhưng **kết quả nghiệp vụ khác nhau**. Nếu công cụ vận hành cần cảnh báo lỗi kỹ thuật, phải lọc đúng `outcome=FAILED` và/hoặc `reason_code`. Không coi mọi từ chối `DECLINED` là `ERROR`; từ chối do hết hạn thẻ có thể là kết quả dự kiến của quy trình.

Tùy miền nghiệp vụ, hệ thống cũng có thể định nghĩa các tên sự kiện riêng như `payment_authorized`, `payment_declined`, `payment_gateway_failed`. Cả hai cách mô hình hóa đều có thể hợp lý khi mỗi tên có **một ý nghĩa rõ ràng**, được dùng đồng nhất và không ghi chồng chéo gây thống kê sai.

Ví dụ, khi có cả `payment_result outcome=APPROVED` và `payment_authorized` cho cùng một bước, phải nêu rõ chúng là hai sự kiện riêng hay hai hình thức biểu diễn của một kết quả. Đừng ngầm cộng số dòng từ hai mẫu để đếm số thanh toán được chấp thuận.

## 11. Có được thay đổi message sau khi triển khai?

Có, nhưng cần xem nó có đang được **bên khác tiêu thụ** hay không. Không có nghĩa phải đóng băng mọi câu chữ mãi mãi.

**Thay đổi tương đối an toàn:** sửa một câu giải thích cho người đọc mà không đổi `event`, mã lý do, tên trường và kiểu dữ liệu của log có cấu trúc; vẫn cần xem có hệ thống nào đang match nguyên văn message không.

**Thay đổi có thể phá vỡ truy vấn:** đổi `order_id` thành `orderId`, đổi `duration_ms` thành `duration_s` mà không đổi đơn vị rõ ràng, đổi `payment_result` thành `payment_finished`, hoặc đảo ý nghĩa `FAILED`/`DECLINED`. Những thay đổi này cần phối hợp dashboard, alert, parser và quy trình vận hành.

**Thêm trường mới:** có thể là thay đổi tương thích ngược nếu bên tiêu thụ cho phép trường bổ sung. Với parser dựa vào vị trí/biểu thức chính quy, thêm trường vào chuỗi có thể làm hỏng dù JSON có cấu trúc vẫn đọc được. Vì vậy hãy xét **định dạng và người tiêu thụ thực tế** trước khi kết luận tương thích.

Với schema được dùng lâu dài, nên có:

- Danh mục sự kiện và tài liệu ngắn về ý nghĩa từng `event`, trường bắt buộc/tùy chọn, các mã `outcome`/`reason_code`.
- Kiểm tra trong review hoặc test để tránh đổi tên vô tình.
- Cơ chế triển khai chuyển tiếp nếu bắt buộc đổi schema: cập nhật bộ tiêu thụ, có thể chấp nhận cả tên cũ/mới một thời gian và xác định ngày ngừng hỗ trợ.
- Phiên bản schema khi có thay đổi không tương thích và nhu cầu lưu trữ nhiều phiên bản cùng lúc, ví dụ trường `schema_version`; không thêm version chỉ vì sửa dấu câu không ảnh hưởng hợp đồng.

Một tổ chức nhỏ có thể quản lý quy ước bằng tài liệu và code review; hệ thống lớn có thể duy trì danh mục schema/sự kiện tập trung. Điều quan trọng là biết **điều gì được cam kết ổn định**.

## 12. Message ổn định không đồng nghĩa bảo đảm log đầy đủ

Giữ mẫu cố định giúp nhận diện sự kiện, nhưng không bảo đảm **mọi lần xử lý đều có log**. Log có thể bị lọc theo cấp, lấy mẫu, mất khi handler lỗi hoặc quá trình thu thập gián đoạn, ghi trùng do retry, hoặc đến chậm trong hệ thống tập trung.

Khi dùng log để tính số lượng hay tỷ lệ:

- Xác định đâu là **sự kiện chuẩn** được ghi tại một bước đã xác nhận; tránh ghi cùng tên trước và sau cập nhật trạng thái.
- Biết một nghiệp vụ có thể được thử lại nhiều lần. `payment_attempt_id`, `operation_id` hoặc idempotency key giúp phân biệt các lần thử trong phạm vi cần thiết.
- Cân nhắc mức sampling, retention và retry ở logger/collector; số dòng log không mặc nhiên bằng số giao dịch đã hoàn tất.
- Đối chiếu cơ sở dữ liệu, sổ cái hoặc hệ thống audit khi cần số liệu có tính chính thức, nhất quán hoặc kiểm toán.

Ví dụ, việc đếm `event=payment_result outcome=APPROVED` trong log được lấy mẫu không thể thay thế số lượng thanh toán được hệ thống giao dịch xác nhận. **Ổn định về mặt từ vựng khác với độ tin cậy của dữ liệu.**

## 13. Bảo mật và an toàn khi định dạng message

Message ổn định thường khuyến khích đưa giá trị biến thiên vào các tham số. Điều đó tạo cơ hội kiểm soát **loại dữ liệu được ghi**, nhưng bản thân parameterization của logging **không phải** cơ chế chống rò rỉ hoặc tự động escape mọi dữ liệu.

### Tránh thông tin nhạy cảm

Không ghi mật khẩu, token xác thực, OTP, API key, số thẻ đầy đủ hoặc dữ liệu cá nhân nhạy cảm trong template lẫn giá trị tham số. Với mã đối tượng, dùng định danh nội bộ phù hợp và quyền truy cập log chặt chẽ; trong một số hệ thống, bản thân ID cũng có thể cần che bớt hoặc mã hóa.

### Tránh log injection

Nếu nhận `reasonText` từ nguồn bên ngoài rồi ghép vào dòng log, ký tự xuống dòng, ký tự điều khiển hoặc dấu phân cách có thể khiến một sự kiện bị trình bày thành nhiều dòng hoặc giả mạo trường khác:

```text
reason_text=Invalid input
INFO event=payment_result outcome=APPROVED
```

Đây là **ví dụ nguy cơ** khi một giá trị đầu vào chứa ký tự xuống dòng; không phải đầu ra của chương trình trong bài.

Biện pháp: chỉ ghi các trường thực sự cần, dùng bộ mã hóa/formatter có cơ chế escape đáng tin cậy, giới hạn kích thước giá trị, và ánh xạ lỗi từ nhà cung cấp về mã `reason_code` nằm trong danh mục kiểm soát. Dùng placeholder `{0}` hay `{}` không tự loại bỏ tất cả ký tự gây nhiễu khỏi chuỗi đã render.

### Không sử dụng dữ liệu đầu vào như template

Mẫu nên do mã ứng dụng và cấu hình đáng tin cậy quyết định. Dữ liệu nhận từ người dùng nên là **giá trị** chứ không phải chuỗi định dạng để logger xử lý. Việc coi đầu vào tùy ý là template có thể làm mất tính nhất quán, phá cấu trúc định dạng và tạo bề mặt lỗi không cần thiết.

### Giới hạn dữ liệu và chi phí

Cấu trúc ổn định không đồng nghĩa ghi toàn bộ request/response. Message quá dài làm tăng chi phí, khó đọc và có thể bị cắt ở một khâu trong pipeline. Chọn vài trường mang giá trị chẩn đoán, tránh đưa stack trace hay payload lớn vào mọi sự kiện thông thường.

## 14. Ngôn ngữ hiển thị và message ổn định

Một ứng dụng phục vụ người dùng Việt Nam có thể cần thông báo thân thiện bằng tiếng Việt, còn công cụ vận hành có thể cần mã sự kiện độc lập với ngôn ngữ:

```text
event=payment_declined reason_code=CARD_EXPIRED
Hiển thị cho người dùng: Thẻ đã hết hạn. Vui lòng dùng phương thức khác.
```

Phần đầu là dữ liệu quan sát/kỹ thuật; phần sau là **thông báo sản phẩm** có thể được bản địa hóa. Không nên dùng câu người dùng nhìn thấy làm mã định danh cho log nếu sản phẩm có nhiều ngôn ngữ: đổi bản dịch hoặc dấu câu có thể khiến truy vấn log bị phá vỡ.

Nhiều hệ thống vẫn ghi phần `message` dễ đọc bằng tiếng Việt hoặc tiếng Anh; không có yêu cầu phải dùng một ngôn ngữ cố định cho mọi phần văn bản. Điều quan trọng là **tên sự kiện, mã kết quả, tên trường và ngữ nghĩa ổn định**, còn nội dung giải thích có thể được quản lý riêng khi cần. JUL cũng hỗ trợ tài nguyên bản địa hóa qua `ResourceBundle` trong một số cách cấu hình; điều đó không thay thế nhu cầu có mã sự kiện kỹ thuật ổn định.

## 15. Quy ước đặt tên message cho một dự án

Giả sử một ứng dụng đặt hàng dùng nhóm log nghiệp vụ. Một quy ước dễ duy trì có thể là:

| Trường / khái niệm | Quy ước | Ví dụ |
| --- | --- | --- |
| `event` | Chữ thường, từ phân cách bằng `_`, mô tả sự kiện | `order_created`, `payment_result` |
| `outcome` | Tập hữu hạn, chữ hoa | `STARTED`, `SUCCESS`, `DECLINED`, `FAILED` |
| `reason_code` | Mã nguyên nhân ổn định | `CARD_EXPIRED`, `GATEWAY_TIMEOUT` |
| `order_id` | Một định danh đơn hàng; không chứa thông tin nhạy cảm khi có thể | `ORD-101` |
| `correlation_id` | Nhận diện luồng yêu cầu xuyên các bước | `req-7a` |
| `duration_ms` | Thời lượng bằng mili giây, kiểu số nếu cấu trúc hỗ trợ | `125` |
| `service` | Tên dịch vụ ổn định theo hệ thống triển khai | `checkout-service` |

Đây là **quy ước ví dụ**, không phải chuẩn bắt buộc của Java. Dự án có thể dùng `camelCase` hoặc tên sự kiện ở dạng khác; quan trọng là có một quy tắc thống nhất và hiểu được hợp đồng dữ liệu.

Khi review một message mới, có thể hỏi:

1. **Một sự kiện có ý nghĩa gì?** Có đang gộp hai kết quả khác nhau hoặc phát trùng tên ở nhiều mốc không?
2. **Phần nào cố định, phần nào thay đổi?** Có đưa ID, tên người dùng, nguyên nhân tự do vào template không?
3. **Có mã và trường để truy vấn không?** Sau ba tháng, người trực vận hành có thể lọc bằng `event` và `reason_code` thay vì tìm câu văn không?
4. **Trường có đơn vị và kiểu rõ ràng không?** Một tiêu chí như `duration_ms` có được áp dụng đồng nhất không?
5. **Có vô tình phá dashboard hoặc alert hiện có không?** Nếu đổi schema, đã cập nhật các bên tiêu thụ chưa?
6. **Có tiết lộ dữ liệu riêng tư hoặc cho phép log injection không?** Dữ liệu nào là tối thiểu cần thiết?
7. **Nguồn phát và luồng xử lý có truy vết được không?** Có timestamp, service và mã tương quan phù hợp ở đâu trong sự kiện/pipeline?

## 16. Một cách kiểm tra tự động tính ổn định

Nếu logic tạo message là quan trọng với giám sát sản xuất, kiểm thử có thể xác nhận **template và tham số** khi log được tạo, thay vì chỉ so khớp toàn bộ dòng đã định dạng. Trong JUL, một `Handler` tùy biến trong test có thể nhận `LogRecord` rồi kiểm tra `record.getMessage()` và `record.getParameters()`.

Ví dụ ý tưởng bên trong một bài kiểm thử (chưa phải chương trình chạy độc lập):

```java
LogRecord record = capturedRecord;

assert "event=payment_result order_id={0} outcome={1} reason_code={2}"
        .equals(record.getMessage());
assert "ORD-101".equals(record.getParameters()[0]);
assert "APPROVED".equals(record.getParameters()[1]);
```

Nhờ vậy, khi ai đó thay template thành một câu ghép động, test có thể phát hiện việc hợp đồng message bị thay đổi. Tuy nhiên, cần phân biệt **kiểm thử mức tạo LogRecord** với **kiểm thử pipeline cuối**: dù template đúng, bộ thu hoặc encoder vẫn có thể làm sai trường, cắt dòng hoặc lọc mất sự kiện. Các bài kiểm thử đầu cuối cho log có cấu trúc nên tập trung vào vài sự kiện quan trọng thay vì sao chép chi tiết mọi thông điệp để tránh test giòn.

Một điều chỉnh chính đáng của template cần được thực hiện cùng với tài liệu/truy vấn/kiểm thử liên quan; không phải mọi thay đổi test đều là lỗi.

## 17. Sai lầm thường gặp

- **Thay câu chữ ở từng nhánh `if` cho cùng sự kiện:** tên sự kiện và mã nguyên nhân bị phân mảnh. Dùng template cố định, thay dữ liệu bằng tham số hoặc trường.
- **Đặt toàn bộ message làm khóa phân nhóm:** biến động `order_id` hoặc nội dung tự do tạo quá nhiều nhóm. Phân nhóm bằng `event`, `outcome` và `reason_code`.
- **Tạo một mẫu quá chung:** `"Processing completed"` áp dụng cho hàng trăm loại xử lý khiến log khó hiểu. Chọn tên sự kiện theo nghĩa cụ thể.
- **Nhầm placeholder của JUL và SLF4J:** JUL `{0}` khác với SLF4J `{}`; thông điệp có thể hiện placeholder nguyên văn nếu dùng sai API.
- **Giữ tên trường nhưng đổi đơn vị/ý nghĩa:** gây sai thống kê dù parser vẫn chạy. Thêm trường hoặc phiên bản hợp đồng khi cần.
- **Đổi `event` mà quên bộ lọc/alert:** tác vụ vận hành âm thầm mất dữ liệu. Xem schema log như giao diện có người tiêu thụ.
- **Ghi nguyên văn câu lỗi từ bên ngoài làm mã lý do:** nhà cung cấp đổi câu chữ là dashboard bị tách nhóm. Ánh xạ sang mã trong danh mục nội bộ.
- **Bỏ qua escaping vì đã dùng tham số:** dữ liệu động vẫn có thể chứa ký tự xuống dòng hoặc bí mật. Dùng encoder phù hợp và lọc dữ liệu.
- **Dùng log làm nguồn đếm giao dịch chính thức:** retry, sampling, mất log hay fan-out làm số liệu sai. Đối chiếu nguồn trạng thái giao dịch.
- **Lạm dụng hằng số cho mọi thông điệp:** không phải câu log nào cũng cần một hằng riêng; điều quan trọng là mẫu ổn định và có thể quản lý. Với sự kiện được nhiều chỗ phát hoặc có hợp đồng vận hành, đặt hằng/schema chung sẽ hữu ích hơn.

## 18. Tự kiểm tra kiến thức

1. **Hai log `"Đơn ORD-101 đã tạo"` và `"Đơn ORD-102 đã tạo"` khác nhau có phải là sai không?** Giá trị cụ thể được phép khác. Vấn đề nằm ở chỗ liệu mã nguồn có mẫu ổn định hay bộ dữ liệu có trường `event=order_created`/`order_id` để công cụ nhận diện cùng loại sự kiện.
2. **Khi nào dùng `reason_code` thay vì `reasonText`?** Khi cần lọc, nhóm và cảnh báo ổn định; nội dung tự do có thể đi kèm nếu có giá trị chẩn đoán, được bảo vệ và escape.
3. **Trong JUL, `"order_id={0}"` nhận giá trị từ đâu?** Từ tham số của bản ghi khi formatter xử lý; không phải trình biên dịch Java tự thay `{0}`.
4. **Có thể thay `{0}` bằng `{}` khi chuyển mẫu từ JUL sang SLF4J không?** Có, nhưng phải đổi đúng API và cách truyền tham số; hai cú pháp không tương đương tự động.
5. **Có nên cố định `correlation_id` bằng một hằng để message ổn định?** Không. Mã tương quan phải thay đổi theo luồng xử lý; cái ổn định là **tên trường** và vai trò của nó.
6. **Một alert theo `event=payment_result` biến mất sau khi đổi thành `payment_finished`. Vì sao?** Tên sự kiện là phần hợp đồng với bộ lọc; phải cập nhật nơi tiêu thụ hoặc triển khai quy trình chuyển đổi.
7. **`duration_ms=100` và `duration_ms=0.1` đều hợp lệ cho bước kéo dài 100 ms không?** Không. Với tên trường `duration_ms`, giá trị `0.1` mang ý nghĩa 0,1 ms; nếu muốn giây phải dùng trường/đơn vị khác.
8. **Có nên dựa vào số dòng cùng message để kết luận số giao dịch?** Không mặc nhiên. Cần hiểu retry, lưu trữ, sampling và điểm ghi sự kiện.
9. **Có thể dùng tiếng Việt cho phần lời giải thích message không?** Có. Mã sự kiện và các trường dùng trong phân tích nên có quy ước ổn định, không phụ thuộc bản dịch.
10. **Nếu người dùng nhập xuống dòng trong một trường, placeholder có tự ngăn log injection không?** Không. Phải dùng encoder/escape và chính sách giới hạn dữ liệu phù hợp.

**Ghi nhớ:** một message ổn định duy trì **ý nghĩa sự kiện, mẫu thông điệp và cấu trúc trường nhất quán**, đồng thời đưa ID, kết quả, mã lý do và ngữ cảnh của mỗi lần xử lý vào **tham số hoặc thuộc tính riêng**. Trong Java, hãy chọn đúng cú pháp theo API logging (JUL `{0}`, SLF4J `{}`), định nghĩa hợp đồng sự kiện có thể tìm kiếm, bảo vệ dữ liệu động và kiểm soát thay đổi ảnh hưởng đến hệ thống quan sát.
