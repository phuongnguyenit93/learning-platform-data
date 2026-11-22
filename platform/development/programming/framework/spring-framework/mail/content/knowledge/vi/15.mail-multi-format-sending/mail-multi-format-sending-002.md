# Chọn phần ưu tiên khi mail client hỗ trợ nhiều loại

Một email có thể cung cấp cùng một nội dung dưới nhiều cách biểu diễn. Ví dụ, thư xác nhận đơn hàng có thể có:

- **Plain text** để đọc được trên mọi môi trường email cơ bản, thiết bị hỗ trợ hoặc client không hiển thị HTML.
- **HTML** để trình bày tiêu đề, bảng sản phẩm, màu sắc và nút xem đơn hàng.

Nếu chỉ gửi HTML, người dùng cấu hình email client ở chế độ text-only hoặc hệ thống lọc HTML có thể không hiển thị nội dung như mong muốn. Nếu chỉ gửi plain text, người nhận vẫn đọc được nhưng không có bố cục phong phú. Chuẩn MIME giải quyết bài toán này bằng cấu trúc **`multipart/alternative`**: một message chứa nhiều phần tương đương về ý nghĩa, mỗi phần dùng một định dạng khác nhau.

Điểm quan trọng của bài học là **thứ tự các phần biểu diễn thể hiện mức ưu tiên của người gửi**. Theo quy tắc MIME, các phần được xếp từ dạng ít được ưu tiên hơn đến dạng được ưu tiên hơn; phần cuối cùng là lựa chọn ưu tiên nhất. Email client chọn phần mà nó có thể hiển thị phù hợp với khả năng và cài đặt của người dùng.

Với email thông thường, ứng dụng thường đặt **plain text trước, HTML sau**. Khi client hỗ trợ cả hai, HTML là lựa chọn ưu tiên; khi client chỉ hỗ trợ text, nó có thể dùng phần plain text. Spring Mail hỗ trợ cách này qua `MimeMessageHelper.setText(plainText, htmlText)`.

## 1. Vì sao một email cần nhiều định dạng?

Không phải mọi người nhận đều xem email trong cùng một môi trường:

- Có người dùng email client chỉ hiển thị plain text.
- Một số tổ chức tắt HTML hoặc loại bỏ nội dung chủ động để giảm rủi ro bảo mật.
- Công cụ hỗ trợ đọc màn hình có thể hoạt động tốt hơn với nội dung text đơn giản, có thứ tự rõ ràng.
- Một số client trên thiết bị nhỏ hiển thị HTML/CSS không giống trình duyệt.
- Email gateway có thể lọc hoặc chuyển đổi một số phần MIME.
- Người dùng có thể chọn chế độ xem text-only dù client có khả năng hiển thị HTML.

Một email chỉ có HTML có thể trông đẹp trong một client nhưng gây khó đọc trong môi trường khác. Ngược lại, một email chỉ có text thường dễ tương thích nhưng khó trình bày danh sách sản phẩm hoặc nút hành động.

**Multipart alternative** cho phép ứng dụng gửi cả hai biểu diễn trong cùng một message, thay vì gửi hai email riêng. Người nhận vẫn chỉ nhận một email và client chọn phần phù hợp.

### 1.1. Các phần phải có cùng ý nghĩa

Các phần trong `multipart/alternative` là những cách biểu diễn thay thế của **cùng một nội dung**. Ví dụ:

| Nội dung nghiệp vụ | Plain text | HTML |
| --- | --- | --- |
| Mã đơn hàng | Đơn hàng A123 đã được xác nhận. | Tiêu đề “Đơn hàng A123 đã được xác nhận” |
| Tổng tiền | Tổng cộng: 220.000 ₫ | Bảng tổng tiền với nhãn và kiểu chữ |
| Hành động | Xem đơn hàng: URL đầy đủ | Nút “Xem đơn hàng” trỏ tới cùng URL |
| Hỗ trợ | Liên hệ support@example.com | Liên kết email tới support@example.com |

Không nên để bản HTML chứa một khoản tiền, còn bản plain text chứa một khoản khác. Cũng không nên đưa thông tin quan trọng chỉ vào HTML rồi để người đọc text không có cách tiếp cận. Nếu một phần chứa dữ liệu khác hẳn phần còn lại, nó không phải alternative tương đương; cần xem xét cấu trúc MIME khác hoặc thiết kế lại nội dung.

## 2. `multipart/alternative` hoạt động như thế nào?

MIME định nghĩa một container có thể chứa nhiều body part. Với `multipart/alternative`, mỗi part mô tả cùng thông tin theo một định dạng khác nhau.

Một email đơn giản có thể có cấu trúc:

~~~text
Content-Type: multipart/alternative; boundary="mail-boundary"

--mail-boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin chào Nguyễn An,

Đơn hàng A123 đã được xác nhận.
Tổng cộng: 220.000 ₫
Xem đơn hàng: https://app.example.com/orders/A123

--mail-boundary
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html>
  <body>
    <h1>Đơn hàng A123 đã được xác nhận</h1>
    <p>Xin chào Nguyễn An,</p>
    <strong>Tổng cộng: 220.000 ₫</strong>
    <a href="https://app.example.com/orders/A123">Xem đơn hàng</a>
  </body>
</html>

--mail-boundary--
~~~

Đây là ví dụ rút gọn để thể hiện cấu trúc, không phải header cố định mà mọi thư viện phải tạo giống hệt. Boundary và transfer encoding thực tế được thư viện MIME tạo ra.

Các phần:

1. Header ngoài cùng khai báo `Content-Type: multipart/alternative`.
2. `boundary` phân tách các body part.
3. Phần thứ nhất có `Content-Type: text/plain`.
4. Phần thứ hai có `Content-Type: text/html`.
5. Dấu boundary cuối cùng có thêm `--` để kết thúc multipart.

Email client đọc cấu trúc này, nhận diện những content type mà nó hỗ trợ rồi chọn cách biểu diễn thích hợp. Nó không cần hiển thị cả plain text lẫn HTML nối tiếp nhau.

### 2.1. Quy tắc thứ tự: ít ưu tiên trước, ưu tiên nhất sau

Theo quy tắc của `multipart/alternative` trong MIME (RFC 2046), các phần được sắp xếp theo thứ tự **tăng dần mức độ ưu tiên**. Phần cuối cùng được coi là phần được ưu tiên nhất.

Ví dụ phổ biến:

~~~text
1. text/plain       # fallback, ít ưu tiên hơn
2. text/html        # presentation phong phú, ưu tiên hơn
~~~

Nếu client hỗ trợ cả plain text và HTML, nó thường chọn HTML vì đây là phần cuối và được người gửi ưu tiên hơn. Nếu client không hỗ trợ HTML, nó có thể chọn plain text.

Có thể hình dung:

1. **Phần 1 — `text/plain` (fallback):** nội dung chữ đơn giản, có khả năng tương thích rộng.
2. **Phần 2 — `text/html` (ưu tiên hơn):** bố cục, bảng, liên kết và định dạng trình bày.

Thứ tự trong `multipart/alternative` đi từ ít ưu tiên đến ưu tiên nhất; phần cuối cùng là lựa chọn được người gửi ưu tiên.

Thứ tự này là **tín hiệu ưu tiên theo chuẩn MIME**, không phải lệnh bắt buộc buộc mọi email client phải hiển thị HTML. Client có thể áp dụng cài đặt người dùng, chính sách bảo mật, bộ lọc nội dung hoặc giới hạn hỗ trợ riêng.

### 2.2. Nếu đảo thứ tự thì sao?

Giả sử message chứa:

~~~text
1. text/html
2. text/plain
~~~

Theo quy tắc thứ tự, plain text trở thành lựa chọn ưu tiên hơn vì nó nằm cuối. Client hỗ trợ cả hai có thể chọn plain text, dù HTML phong phú hơn. Client chỉ hỗ trợ HTML vẫn có thể dùng HTML vì đó là phần duy nhất nó hỗ trợ.

Do đó, nếu mục tiêu là **ưu tiên HTML nhưng vẫn có fallback text**, hãy đặt text trước, HTML sau. Không nên đảo thứ tự chỉ vì muốn “HTML xuất hiện đầu tiên” trong raw MIME.

## 3. Phân biệt multipart/alternative với các cấu trúc MIME khác

Không phải cứ một email có nhiều part là dùng `multipart/alternative`. Cần chọn cấu trúc đúng theo ý nghĩa các part.

| MIME type | Mục đích | Ví dụ |
| --- | --- | --- |
| `multipart/alternative` | Nhiều cách biểu diễn tương đương của cùng nội dung | Plain text và HTML |
| `multipart/mixed` | Nhiều thành phần độc lập được gửi cùng nhau | Body email và file PDF đính kèm |
| `multipart/related` | Các part liên quan với nhau để tạo một nội dung hoàn chỉnh | HTML body và ảnh inline được tham chiếu bằng CID |

### 3.1. Alternative không phải danh sách attachment

Không nên đưa plain text và HTML vào `multipart/mixed` chỉ để gửi hai phiên bản:

~~~text
multipart/mixed
  text/plain
  text/html
~~~

`multipart/mixed` nói rằng các phần là các thành phần cùng tồn tại trong một message. Một số client có thể hiển thị một part, coi part khác như attachment hoặc đưa ra hành vi không như mong muốn.

Với hai phiên bản tương đương, dùng `multipart/alternative` để client hiểu rằng **chỉ cần chọn một cách biểu diễn**.

### 3.2. Khi có file đính kèm

Nếu email có cả body plain/HTML và PDF, cấu trúc thường dùng là `multipart/mixed` bên ngoài, chứa body alternative và attachment:

~~~text
multipart/mixed
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain
  |     |
  |     +-- text/html
  |
  +-- application/pdf
       Content-Disposition: attachment
~~~

Ở đây:

- `multipart/mixed` gom body email và file đính kèm.
- `multipart/alternative` cho phép client chọn plain text hoặc HTML.
- `application/pdf` là file riêng, không phải một phiên bản thay thế của body.

### 3.3. Khi HTML có ảnh inline

HTML có thể tham chiếu ảnh bằng Content-ID:

~~~html
<img src="cid:company-logo" alt="Company logo">
~~~

Ảnh inline liên quan đến HTML thường được đóng gói trong `multipart/related`. Khi kết hợp plain text, HTML và ảnh inline, cấu trúc khái quát có thể là:

~~~text
multipart/mixed
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain
  |     |
  |     +-- multipart/related
  |           |
  |           +-- text/html
  |           +-- image/png (Content-ID: company-logo)
  |
  +-- application/pdf (attachment)
~~~

Việc lồng multipart giúp phân biệt:

- **Alternative:** plain text hay phiên bản HTML.
- **Related:** HTML cần những tài nguyên inline nào.
- **Mixed:** message còn có những file độc lập nào.

Thư viện có thể tạo một cách lồng part cụ thể tùy multipart mode; điều quan trọng là ý nghĩa MIME được giữ đúng.

## 4. Tạo hai phiên bản bằng Spring Mail

`SimpleMailMessage` chỉ hỗ trợ thông điệp text đơn giản. Muốn gửi nhiều định dạng trong cùng email, hãy dùng `MimeMessage` thông qua `JavaMailSender` và `MimeMessageHelper`.

### 4.1. Dùng setText(plainText, htmlText)

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderMailService {
    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient)
            throws MessagingException {

        String plainText = """
                Xin chào Nguyễn An,

                Đơn hàng A123 đã được xác nhận.
                Tổng cộng: 220.000 ₫

                Xem đơn hàng:
                https://app.example.com/orders/A123

                Nếu cần hỗ trợ, hãy trả lời email này.
                """;

        String htmlText = """
                <!DOCTYPE html>
                <html lang="vi">
                <body>
                  <h1>Đơn hàng A123 đã được xác nhận</h1>
                  <p>Xin chào Nguyễn An,</p>
                  <p><strong>Tổng cộng: 220.000 ₫</strong></p>
                  <p>
                    <a href="https://app.example.com/orders/A123">
                      Xem đơn hàng
                    </a>
                  </p>
                  <p>Nếu cần hỗ trợ, hãy trả lời email này.</p>
                </body>
                </html>
                """;

        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng A123");

        // Plain text là alternative trước, HTML là alternative sau.
        helper.setText(plainText, htmlText);

        mailSender.send(mime);
    }
}
~~~

Điểm quan trọng là lời gọi:

~~~java
helper.setText(plainText, htmlText);
~~~

Hai tham số có thứ tự:

1. `plainText` — phiên bản văn bản thuần.
2. `htmlText` — phiên bản HTML.

Spring Mail sử dụng chúng để tạo nội dung alternative. Với cách gọi thông thường này, plain text là fallback và HTML là phần được ưu tiên hơn.

### 4.2. Vì sao constructor nhận multipart = true?

Trong ví dụ:

~~~java
new MimeMessageHelper(mime, true, "UTF-8");
~~~

Tham số `true` yêu cầu helper làm việc với cấu trúc multipart. Đây là lựa chọn phù hợp khi cần alternative body, inline resource hoặc attachment. `false` phù hợp với một body đơn giản không cần multipart; không dùng nó cho ví dụ plain + HTML ở trên.

### 4.3. setText(html, true) khác setText(plain, html)

Hai cách gọi có ý nghĩa khác nhau:

~~~java
// Chỉ một phần HTML; không có plain-text alternative.
helper.setText(htmlText, true);

// Hai phần tương đương: plain text và HTML.
helper.setText(plainText, htmlText);
~~~

Ở overload đầu, tham số boolean cho biết chuỗi text là HTML. Nó **không** có nghĩa “bật HTML và tự sinh plain text”. Nếu cần fallback, ứng dụng phải tự tạo nội dung plain text và gọi overload hai chuỗi.

### 4.4. Không đưa thẻ HTML vào SimpleMailMessage

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setText("<h1>Xin chào</h1>");
~~~

Đoạn này vẫn tạo **plain text** chứa các ký tự `<h1>`, vì `SimpleMailMessage` không đánh dấu body là HTML và không tạo MIME alternative. Để gửi HTML hoặc nhiều định dạng, cần `MimeMessage`.

## 5. Tự tạo multipart/alternative bằng Jakarta Mail

`MimeMessageHelper.setText(plainText, htmlText)` là lựa chọn đơn giản cho thứ tự phổ biến. Nếu ứng dụng cần **chủ động chọn thứ tự ưu tiên khác**, có thể dựng `MimeMultipart("alternative")` trực tiếp.

### 5.1. Ưu tiên HTML, plain text làm fallback

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import org.springframework.mail.javamail.JavaMailSender;

public void sendHtmlPreferred(
        JavaMailSender sender,
        String recipient,
        String plainText,
        String htmlText) throws Exception {

    MimeMessage message = sender.createMimeMessage();
    message.setFrom(new InternetAddress("news@example.com"));
    message.setRecipients(
            Message.RecipientType.TO,
            InternetAddress.parse(recipient, true)
    );
    message.setSubject("Thông báo mới", StandardCharsets.UTF_8.name());

    MimeMultipart alternative = new MimeMultipart("alternative");

    MimeBodyPart plainPart = new MimeBodyPart();
    plainPart.setText(plainText, StandardCharsets.UTF_8.name());
    alternative.addBodyPart(plainPart); // Ít ưu tiên hơn.

    MimeBodyPart htmlPart = new MimeBodyPart();
    htmlPart.setContent(
            htmlText,
            "text/html; charset=UTF-8"
    );
    alternative.addBodyPart(htmlPart); // Ưu tiên nhất.

    message.setContent(alternative);
    sender.send(message);
}
~~~

Thứ tự thêm part là **plain trước, HTML sau**, nên HTML là alternative cuối cùng và được ưu tiên theo MIME.

Ví dụ dùng `InternetAddress.parse(..., true)` để parse địa chỉ nghiêm ngặt hơn và `setSubject(..., UTF-8)` để thiết lập subject có thể chứa tiếng Việt. Trong code sản phẩm, nên bắt/khai báo những exception cụ thể phù hợp chữ ký method thay vì dùng `throws Exception` tổng quát.

### 5.2. Ưu tiên plain text

Nếu sản phẩm có yêu cầu đặc biệt rằng **plain text là cách biểu diễn ưu tiên**, có thể đảo thứ tự:

~~~java
MimeMultipart alternative = new MimeMultipart("alternative");

MimeBodyPart htmlPart = new MimeBodyPart();
htmlPart.setContent(htmlText, "text/html; charset=UTF-8");
alternative.addBodyPart(htmlPart); // Ít ưu tiên hơn.

MimeBodyPart plainPart = new MimeBodyPart();
plainPart.setText(plainText, "UTF-8");
alternative.addBodyPart(plainPart); // Ưu tiên nhất.

message.setContent(alternative);
~~~

Client hỗ trợ cả hai được khuyến nghị chọn phần cuối theo thứ tự ưu tiên MIME, nhưng vẫn có thể chịu ảnh hưởng từ cấu hình text-only, policy hoặc hành vi riêng của client.

Không nên đảo thứ tự chỉ để thử nghiệm tùy tiện. Hãy có lý do sản phẩm rõ ràng, ví dụ môi trường yêu cầu nội dung không phụ thuộc HTML, rồi kiểm tra các client mục tiêu.

## 6. Chọn định dạng theo khả năng của mail client

Người gửi không biết chắc mọi khả năng hiển thị của client người nhận. `multipart/alternative` cho client biết những cách biểu diễn sẵn có và mức ưu tiên, nhưng **client là bên quyết định cuối cùng**.

Một cách diễn giải đơn giản:

| Client / cài đặt | Các phần có thể dùng | Kết quả thường gặp |
| --- | --- | --- |
| Chỉ hỗ trợ plain text | `text/plain` | Hiển thị bản text |
| Hỗ trợ HTML và text | Cả hai | Thường chọn HTML nếu HTML đứng cuối |
| Người dùng chọn text-only | Cả hai trong message | Có thể hiển thị plain text theo cài đặt |
| Gateway loại bỏ HTML | Phần text còn lại | Người nhận đọc fallback |
| Client không hiểu một content type | Các phần client hiểu | Chọn phần được hỗ trợ phù hợp |
| Client có policy lọc HTML | Tùy policy | Có thể chuyển sang text hoặc biến đổi nội dung |

Đây là mô hình hành vi khái quát. Không thể suy ra chính xác giao diện của mọi Outlook, Gmail, Apple Mail, webmail hoặc ứng dụng di động chỉ từ thứ tự MIME.

### 6.1. Người gửi không thể ép client hiển thị HTML

Việc HTML nằm cuối multipart alternative có nghĩa **người gửi ưu tiên HTML**, không có nghĩa client buộc phải hiển thị HTML. Người nhận có thể:

- bật chế độ chỉ đọc text;
- dùng công cụ đọc mail không hỗ trợ HTML;
- dùng gateway bảo mật loại bỏ hoặc biến đổi HTML;
- mở email bằng công cụ chỉ trích xuất text.

Vì vậy, plain text phải tự chứa thông tin quan trọng. Không viết bản text kiểu “Trình xem email của bạn không hỗ trợ HTML” rồi bỏ toàn bộ thông tin giao dịch.

### 6.2. Không gửi nhiều email để thay thế multipart

Một cách làm không phù hợp là gửi một email HTML và một email text riêng cho cùng người nhận. Cách này có thể khiến người dùng nhận hai thư, tạo hai thread, gây nhầm lẫn và làm tăng số lần gửi.

`multipart/alternative` gói cả hai cách biểu diễn vào **một email**. Client chỉ chọn một phần để hiển thị theo khả năng và cài đặt của nó.

## 7. Nội dung hai phần phải đồng bộ

Nếu HTML và plain text được viết ở hai nơi riêng, chúng có thể lệch nhau theo thời gian:

~~~text
HTML:       Tổng cộng 220.000 ₫
Plain text: Tổng cộng 200.000 ₫
~~~

Đây là lỗi nội dung nghiêm trọng vì người nhận có thể thấy thông tin khác nhau tùy client.

### 7.1. Dùng một model cho cả hai

Thay vì tạo hai luồng lấy dữ liệu:

~~~text
Order -> HTML query -> HTML
Order -> Text query -> Plain text
~~~

nên tạo một model duy nhất:

~~~text
Order
  |
  v
OrderConfirmationMailModel
  |                         |
  v                         v
HTML template          Plain-text renderer
  |                         |
  +-----------+-------------+
              |
              v
        MimeMessage
~~~

Ví dụ:

~~~java
public record OrderMailModel(
        String customerName,
        String orderNumber,
        List<String> lineTexts,
        String totalText,
        String orderUrl) {
}
~~~

HTML và plain text cùng đọc `customerName`, `orderNumber`, `lineTexts`, `totalText` và `orderUrl`. Nhờ đó, hai phần có cùng dữ liệu nguồn.

### 7.2. Tạo plain text từ model

~~~java
public String renderPlainText(OrderMailModel model) {
    StringBuilder text = new StringBuilder();
    text.append("Xin chào ")
            .append(model.customerName())
            .append(",\n\n");
    text.append("Đơn hàng ")
            .append(model.orderNumber())
            .append(" đã được xác nhận.\n\n");

    for (String line : model.lineTexts()) {
        text.append("- ").append(line).append('\n');
    }

    text.append("\nTổng cộng: ")
            .append(model.totalText())
            .append("\n");
    text.append("Xem đơn hàng: ")
            .append(model.orderUrl())
            .append("\n");
    return text.toString();
}
~~~

Đây là một renderer plain text đơn giản. Với nhiều loại email và locale, có thể dùng text template riêng thay vì nối chuỗi. Dù chọn cách nào, hai phần vẫn nên được tạo từ **cùng model và cùng quy tắc nghiệp vụ**.

### 7.3. Đồng bộ liên kết và hành động

Nếu HTML có nút:

~~~html
<a href="https://app.example.com/orders/A123">Xem đơn hàng</a>
~~~

plain text phải có URL hoặc hướng dẫn tương đương:

~~~text
Xem đơn hàng:
https://app.example.com/orders/A123
~~~

Không để người đọc text mất khả năng thực hiện hành động. URL phải được sinh từ domain tin cậy, dùng HTTPS khi phù hợp và kiểm tra quyền ở backend khi người nhận mở.

## 8. Charset và transfer encoding cho từng alternative

Mỗi MIME part có header riêng. Với nội dung tiếng Việt, cả plain text và HTML nên có charset được xác định rõ:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

...

Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

...
~~~

`charset=UTF-8` cho biết bytes của phần text cần được giải mã bằng UTF-8. `Content-Transfer-Encoding` mô tả cách biểu diễn bytes để truyền, ví dụ quoted-printable hoặc base64.

Không nhầm:

- **Charset:** chuyển văn bản Unicode thành bytes như thế nào.
- **Transfer encoding:** bytes được biểu diễn trong MIME ra sao.
- **Alternative order:** client được gợi ý ưu tiên phần nào.

Đây là ba khía cạnh độc lập.

### 8.1. Cấu hình UTF-8 với Spring Mail

Khi dùng helper:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());
~~~

Đồng thời có thể đặt encoding mặc định của Spring Boot:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

Khi constructor helper đã chỉ định encoding, đó là encoding được dùng cho những phần text mà helper tạo theo cấu hình này. Nên kiểm tra raw MIME nếu nội dung có dấu tiếng Việt bị lỗi; không chuyển chuỗi Unicode sang Base64 thủ công trước khi gọi `setText`.

### 8.2. Không encode toàn bộ HTML bằng Base64 trước

Không nên:

~~~java
String encodedHtml = Base64.getEncoder().encodeToString(
        htmlText.getBytes(StandardCharsets.UTF_8)
);
helper.setText(plainText, encodedHtml);
~~~

Khi làm vậy, phần được khai báo là HTML thực tế chỉ chứa ký tự Base64. Email client sẽ không tự giải mã nó thành HTML như bạn mong muốn. Hãy truyền chuỗi Unicode gốc; thư viện MIME đảm nhiệm transfer encoding.

## 9. Kết hợp alternative với attachment

Một email hóa đơn có thể cần:

- bản plain text;
- bản HTML;
- file PDF hóa đơn.

Spring Mail:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn A123");
helper.setText(
        "Hóa đơn A123 đã được phát hành. Tổng cộng: 220.000 ₫.",
        "<html><body>"
        + "<h1>Hóa đơn A123</h1>"
        + "<p>Tổng cộng: <strong>220.000 ₫</strong></p>"
        + "</body></html>"
);
helper.addAttachment(
        "Hoa-don-A123.pdf",
        new FileSystemResource(invoiceFile)
);

sender.send(mime);
~~~

`setText(plain, html)` vẫn tạo alternative cho body. `addAttachment(...)` thêm một MIME part độc lập. Cấu trúc chính xác có thể lồng multipart theo chế độ helper, nhưng về mặt ý nghĩa:

~~~text
multipart/mixed
  multipart/alternative
    text/plain
    text/html
  application/pdf
~~~

File PDF **không phải** alternative của body. Người nhận cần có body (chọn một trong hai cách biểu diễn) và có thêm attachment.

### 9.1. Kết hợp ảnh inline

Nếu HTML tham chiếu ảnh bằng CID:

~~~html
<img src="cid:logo" alt="Logo">
~~~

helper có thể thêm ảnh inline:

~~~java
helper.setText(plainText, htmlText);
helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Đặt nội dung trước rồi thêm inline resource theo hướng dẫn của `MimeMessageHelper`. Ảnh liên quan tới HTML nên được biểu diễn bằng `multipart/related`; helper có multipart mode phù hợp để quản lý cấu trúc đó. Plain text không cần chứa ảnh, nhưng nên có tên tổ chức hoặc thông tin mà logo thể hiện nếu đó là nội dung cần thiết.

## 10. Khi nào cần thay đổi thứ tự ưu tiên?

Mặc định phổ biến là **plain text trước, HTML sau**. Chỉ thay đổi khi có lý do cụ thể.

| Mục tiêu | Thứ tự nên cân nhắc | Lý do |
| --- | --- | --- |
| Ưu tiên HTML, giữ text fallback | text/plain → text/html | Cách dùng phổ biến |
| Ưu tiên plain text, giữ HTML thay thế | text/html → text/plain | Phần cuối là text |
| Chỉ gửi nội dung văn bản | Chỉ text/plain | Không cần multipart alternative |
| Chỉ gửi HTML | Chỉ text/html | Không có fallback; cần cân nhắc tương thích |
| Có body và attachment | alternative cho body bên trong mixed | Attachment là nội dung độc lập |

Nếu chỉ dùng `MimeMessageHelper.setText(plain, html)`, Spring cung cấp thứ tự thông dụng plain rồi HTML. Nếu muốn thứ tự ưu tiên khác, có thể dựng `MimeMultipart("alternative")` trực tiếp và thêm các part theo thứ tự mong muốn.

### 10.1. Không dùng thứ tự để thay thế chính sách bảo mật

Nếu tổ chức không cho phép HTML, đảo thứ tự không phải biện pháp đủ để loại bỏ HTML. Client có thể vẫn hỗ trợ và chọn HTML theo cài đặt riêng; gateway cũng có thể xử lý message theo chính sách khác.

Nếu thật sự cần gửi text-only vì lý do bảo mật hoặc quy định, hãy **chỉ tạo một part `text/plain`**, không tạo HTML rồi hy vọng client không chọn nó.

### 10.2. Không dùng HTML chỉ vì muốn có nút bấm

Plain text cũng có thể chứa URL đầy đủ và hướng dẫn rõ ràng. Nếu email rất đơn giản, không cần bố cục hoặc hình ảnh, chỉ gửi text có thể là lựa chọn dễ bảo trì. Multipart alternative hữu ích khi có hai cách trình bày thực sự cần thiết, không phải điều kiện bắt buộc cho mọi email.

## 11. Kiểm thử thứ tự alternative

Khi dùng `MimeMessageHelper`, nên kiểm tra MIME đã tạo chứ không chỉ xác nhận method được gọi. Có thể serialize message ra bytes hoặc đọc multipart content trong test.

### 11.1. Kiểm tra cấu trúc MIME bằng Jakarta Mail

Ví dụ khung kiểm thử khi message đã được dựng:

~~~java
Object content = mimeMessage.getContent();
assertTrue(content instanceof Multipart);

Multipart multipart = (Multipart) content;
~~~

Tùy multipart mode của `MimeMessageHelper` và việc có attachment/inline image hay không, `Multipart` ngoài cùng có thể là `mixed` hoặc `related`, không nhất thiết trực tiếp là `alternative`. Vì vậy, test thực tế nên **đi sâu qua các part** và tìm multipart có subtype `alternative`.

Một helper đệ quy có thể duyệt:

~~~java
void inspectPart(Part part) throws Exception {
    Object content = part.getContent();

    if (content instanceof Multipart multipart) {
        System.out.println(
                multipart.getContentType()
        );
        for (int i = 0; i < multipart.getCount(); i++) {
            inspectPart(multipart.getBodyPart(i));
        }
    } else {
        System.out.println(part.getContentType());
    }
}
~~~

Đây là code minh họa cách duyệt cấu trúc; test nên dùng assertion thay vì chỉ in ra console. Khi gặp `multipart/alternative`, kiểm tra:

- số lượng part mong đợi;
- part text có `Content-Type` là `text/plain`;
- part HTML có `Content-Type` là `text/html`;
- plain text đứng trước HTML nếu HTML là phần ưu tiên;
- nội dung của hai phần có cùng thông tin nghiệp vụ.

### 11.2. Kiểm thử qua raw MIME

Có thể lưu message test thành file `.eml` hoặc dùng SMTP server giả lập như Mailpit/GreenMail để xem raw message. Kiểm tra:

1. Header multipart có subtype `alternative`.
2. Boundary phân tách đúng các part.
3. `Content-Type` và charset của mỗi part đúng.
4. Plain text xuất hiện trước HTML khi muốn ưu tiên HTML.
5. Nội dung Unicode được giải mã đúng.
6. Nếu có attachment, attachment nằm ở nhánh MIME độc lập, không bị coi là alternative.

Không nên viết test yêu cầu chuỗi boundary, transfer encoding hoặc cách gấp header phải giống tuyệt đối một ví dụ. Thư viện có thể tạo boundary và encoding khác nhau nhưng vẫn hợp lệ. Nên parse message và kiểm tra **ngữ nghĩa MIME**.

### 11.3. Kiểm thử hành vi email client

Ngoài raw MIME, nên thử với các client mà sản phẩm cần hỗ trợ:

- client hiển thị HTML;
- client được cấu hình text-only;
- client trên thiết bị di động;
- môi trường có gateway lọc HTML;
- công cụ đọc màn hình hoặc công cụ truy cập nội dung text.

Kiểm thử này giúp biết phần ưu tiên có được diễn giải như mong muốn trong thực tế hay không. Không có unit test Java nào thay thế hoàn toàn việc xem email ở các client mục tiêu.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Người nhận chỉ thấy thẻ HTML | Gửi bằng `SimpleMailMessage` hoặc đánh dấu HTML sai | Dùng `MimeMessageHelper` và MIME HTML |
| Email có HTML nhưng không có text fallback | Chỉ gọi `setText(html, true)` | Gọi `setText(plainText, htmlText)` |
| Client hỗ trợ cả hai lại chọn plain text | Plain text nằm cuối alternative | Đặt HTML sau plain text nếu muốn ưu tiên HTML |
| Client text-only không thấy nội dung | Không tạo `text/plain` hoặc phần text quá sơ sài | Tạo fallback tự chứa thông tin |
| Client hiển thị cả hai phần như hai file | Dùng `multipart/mixed` thay vì `multipart/alternative` cho hai biểu diễn | Dùng subtype `alternative` |
| Attachment bị chọn như body | Đưa attachment vào nhánh alternative | Dùng `multipart/mixed` bên ngoài |
| Ảnh CID không hiển thị | Cấu trúc related/CID không khớp | Dùng helper multipart phù hợp, kiểm tra Content-ID |
| HTML và text có tổng tiền khác nhau | Tạo hai luồng dữ liệu riêng | Dùng cùng model cho cả hai renderer |
| Tiếng Việt lỗi dấu ở một part | Charset hoặc bytes của part không khớp | Dùng UTF-8 nhất quán và kiểm tra raw MIME |
| Nghĩ HTML cuối bắt buộc mọi client dùng HTML | Nhầm ưu tiên MIME với quyền điều khiển client | Tôn trọng cài đặt và policy phía nhận |
| Thư viện tạo cấu trúc MIME lồng nhau khác ví dụ | Multipart mode hoặc attachment/inline resource làm thay đổi nesting | Duyệt MIME tree, không giả định root luôn là alternative |

### 12.1. Lỗi do thiếu plain-text alternative

Ví dụ chỉ có HTML:

~~~java
helper.setText("<h1>Đơn hàng đã xác nhận</h1>", true);
~~~

Một số client có thể hiển thị tốt, nhưng client text-only có thể không có phiên bản dự phòng. Đối với email giao dịch, hãy tạo bản text:

~~~java
helper.setText(
        "Đơn hàng A123 đã được xác nhận. Tổng cộng: 220.000 ₫.",
        "<html><body><h1>Đơn hàng A123 đã được xác nhận</h1>"
        + "<p>Tổng cộng: 220.000 ₫.</p></body></html>"
);
~~~

### 12.2. Lỗi do dùng mixed cho hai phiên bản

Nếu plain và HTML được thêm như hai body part trong `multipart/mixed`, client có thể coi chúng là hai thành phần riêng, thay vì hai cách hiển thị thay thế. Hãy chọn subtype dựa trên **quan hệ ngữ nghĩa giữa các part**, không chỉ dựa vào việc có bao nhiêu part.

### 12.3. Lỗi do giả định helper luôn tạo root alternative

Khi helper bật multipart, thêm inline image hoặc attachment, message có thể có các container lồng nhau. Test chỉ kiểm tra `mimeMessage.getContent()` có subtype alternative ngay ở root có thể thất bại dù cấu trúc thực tế hợp lệ.

Duyệt cây MIME và tìm part có `multipart/alternative`. Với attachment, kiểm tra thêm `Content-Disposition` để xác định part tải xuống.

## 13. Một ví dụ dịch vụ hoàn chỉnh với dữ liệu động

Ví dụ dưới đây dùng cùng dữ liệu để tạo plain text và HTML:

~~~java
package com.example.mail.application;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender sender;

    public NotificationMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendOrderConfirmed(OrderMailModel model)
            throws MessagingException {

        String plainText = """
                Xin chào %s,

                Đơn hàng %s đã được xác nhận.
                Tổng cộng: %s

                Xem đơn hàng:
                %s
                """.formatted(
                model.customerName(),
                model.orderNumber(),
                model.totalText(),
                model.orderUrl()
        );

        // Dữ liệu động trong HTML phải được escape theo ngữ cảnh.
        // Ví dụ này giả định các biến đã được render qua template engine.
        String htmlText = renderHtml(model);

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setTo(model.recipient());
        helper.setSubject(
                "Xác nhận đơn hàng " + model.orderNumber()
        );
        helper.setText(plainText, htmlText);

        sender.send(mime);
    }

    private String renderHtml(OrderMailModel model) {
        // Trong ứng dụng thực tế, render bằng Thymeleaf/FreeMarker
        // để dữ liệu động được escape đúng ngữ cảnh.
        return "<html><body><h1>Đơn hàng đã được xác nhận</h1>"
                + "<p>Tổng cộng: "
                + escapeHtml(model.totalText())
                + "</p></body></html>";
    }

    private String escapeHtml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
~~~

Đây là ví dụ rút gọn để minh họa luồng. Trong ứng dụng thật, nên dùng template engine thay cho một hàm escape tự viết, và cần escape **từng giá trị theo đúng ngữ cảnh** (text node, attribute hoặc URL). Phần `OrderMailModel` là DTO do ứng dụng định nghĩa, có `recipient`, `customerName`, `orderNumber`, `totalText` và `orderUrl`.

Điểm quan trọng vẫn là `helper.setText(plainText, htmlText)`: hai biểu diễn được đưa vào cùng message. Khi HTML được ưu tiên, nó đứng sau phần text trong alternative.

## 14. Quy tắc chọn phần ưu tiên trong thiết kế email

Khi xây email mới, có thể quyết định theo các bước:

1. **Xác định nội dung cốt lõi:** người nhận phải biết điều gì dù chỉ đọc text?
2. **Tạo plain text đầy đủ:** thông tin, số tiền, thời hạn và URL không phụ thuộc HTML.
3. **Tạo HTML tương đương:** thêm bố cục và định dạng, không thay đổi ý nghĩa.
4. **Chọn thứ tự:** thường text trước, HTML sau để ưu tiên HTML.
5. **Dùng đúng MIME subtype:** `multipart/alternative` cho hai biểu diễn, `mixed` cho attachment, `related` cho tài nguyên inline.
6. **Thiết lập charset:** UTF-8 nhất quán cho nội dung Unicode.
7. **Kiểm tra MIME tree:** xác nhận thứ tự part và quan hệ lồng nhau.
8. **Thử trên client mục tiêu:** bảo đảm text-only vẫn đọc được và HTML không bị vỡ.

### 14.1. Ma trận lựa chọn nhanh

| Yêu cầu | Cách tạo nội dung |
| --- | --- |
| Chỉ cần email chữ | `SimpleMailMessage` hoặc MIME `text/plain` |
| HTML có text fallback | `MimeMessageHelper.setText(plain, html)` |
| HTML không có fallback | `MimeMessageHelper.setText(html, true)` |
| Plain text là phần ưu tiên hơn HTML | Tự tạo `multipart/alternative` với HTML trước, text sau |
| HTML + PDF | `multipart/mixed` bên ngoài, alternative cho body |
| HTML + ảnh inline + text | alternative chứa text và nhánh related cho HTML/ảnh |
| HTML + ảnh inline + PDF | Kết hợp alternative, related và mixed theo quan hệ part |

## 15. Tình huống tổng hợp: email hóa đơn đa định dạng

Một ứng dụng gửi hóa đơn cho khách hàng Nguyễn An. Nội dung cần có:

- Mã hóa đơn INV-2026-001.
- Tổng tiền 2.200.000 ₫.
- Đường dẫn xem hóa đơn.
- Một file PDF đính kèm.
- Logo công ty trong bản HTML.

Nội dung plain text:

~~~text
Xin chào Nguyễn An,

Hóa đơn INV-2026-001 đã được phát hành.
Tổng cộng: 2.200.000 ₫.

Xem hóa đơn:
https://app.example.com/invoices/INV-2026-001

File PDF được đính kèm trong email này.
~~~

Nội dung HTML có thể hiển thị bảng thông tin, logo và nút “Xem hóa đơn”. Cả hai dùng cùng mã hóa đơn, tổng tiền và URL. MIME được xây dựng theo ý nghĩa:

~~~text
multipart/mixed
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain
  |     |
  |     +-- multipart/related
  |           |
  |           +-- text/html
  |           +-- image/png (company logo)
  |
  +-- application/pdf (invoice attachment)
~~~

Khi client hỗ trợ HTML, nó có thể chọn phần HTML và hiển thị bố cục cùng logo. Khi client chỉ đọc text, nó dùng phần plain text và vẫn có mã hóa đơn, tổng tiền, link và thông tin file đính kèm. PDF vẫn là attachment riêng dù client chọn phần body nào.

**Chọn phần ưu tiên** vì vậy không phải thao tác chọn định dạng bằng một cờ trong UI. Đó là việc người gửi **đóng gói các cách biểu diễn đúng chuẩn MIME và sắp xếp theo mức ưu tiên**, để client người nhận có đủ thông tin quyết định cách hiển thị.

### Tài liệu tham khảo

- **RFC 2046 — Multipurpose Internet Mail Extensions (MIME) Part Two:** `multipart/alternative`, thứ tự các phần và cách chọn representation.
- **RFC 2045 — MIME Part One:** cấu trúc MIME, content type, charset và transfer encoding.
- **RFC 2049 — MIME Conformance Criteria and Examples:** ví dụ và yêu cầu phù hợp MIME.
- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và gửi plain text/HTML.
- **Spring Framework API — `MimeMessageHelper.setText(String, String)`:** cung cấp plain text và HTML text trong một message.
- **Jakarta Mail API — `MimeMultipart` / `MimeBodyPart`:** tạo multipart alternative và các body part.
