# Tạo HTML nhưng quên plain text thay thế

Trong ứng dụng sử dụng **Spring Framework Mail**, việc gửi email có định dạng HTML thường bắt đầu rất đơn giản: tạo một chuỗi có thẻ **h1**, **p**, **a**, sau đó truyền cho **MimeMessageHelper** với tham số **html=true**. Email nhìn đẹp trong một số hộp thư và developer dễ nghĩ đã hoàn thành. Nhưng một lỗi production thường gặp là **chỉ tạo phần text/html mà bỏ quên phần text/plain tương đương**.

Email HTML-only không nhất thiết bị mọi mail client từ chối; nhiều clients vẫn hiển thị được. Vấn đề là ứng dụng đã bỏ mất một biểu diễn dự phòng quan trọng cho người nhận, công cụ tự động và những môi trường không dùng/không muốn render HTML. Khi HTML bị chặn, lỗi, không được hỗ trợ hoặc bị hệ thống xử lý khác loại bỏ, người nhận có thể thiếu nội dung chính. Vì vậy, một email cần trình bày chuyên nghiệp thường nên cung cấp **cả plain text và HTML** trong cùng thông điệp MIME.

Trong Spring Mail, cách làm trực tiếp là:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Xác nhận đăng ký");
helper.setText(
        "Chào bạn,\n\nĐăng ký đã được xác nhận.\n\n"
                + "Chi tiết: https://app.example.test/account",
        "<p>Chào bạn,</p><p>Đăng ký đã được "
                + "<strong>xác nhận</strong>.</p>"
                + "<p><a href=\"https://app.example.test/account\">"
                + "Xem chi tiết</a></p>"
);
~~~

Ở đây overload **setText(String plainText, String htmlText)** tạo hai biến thể biểu diễn, được đóng gói dưới **multipart/alternative** theo cấu trúc MIME mà helper tạo ra. Đây là **một email duy nhất**, không phải gửi hai thư khác nhau.

> **Điểm cần nhớ:** Nếu yêu cầu là gửi email có định dạng nhưng vẫn đọc được khi không hiển thị HTML, hãy tạo **text/plain và text/html từ cùng dữ liệu nghiệp vụ**, dùng overload hai chuỗi của **MimeMessageHelper.setText(...)**. Plain text phải có **nội dung đầy đủ và các hành động quan trọng**, không phải chuỗi trống hoặc vài chữ “hãy bật HTML”.

## 1. Biểu hiện của lỗi HTML-only

Một đoạn code dễ gặp:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo("recipient@example.test");
helper.setSubject("Đơn hàng đã được xác nhận");
helper.setText(
        "<h1>Đặt hàng thành công</h1>"
                + "<p>Đơn hàng ORD-1528 đã được xác nhận.</p>",
        true
);
mailSender.send(message);
~~~

Overload **setText(String text, boolean html)** với **html=true** đánh dấu nội dung truyền vào là HTML. Nó **không yêu cầu ứng dụng cung cấp một phần text/plain tương đương**.

### Tình huống phát sinh vấn đề

- Người nhận mở thư bằng client chỉ hỗ trợ văn bản thuần hoặc đã cấu hình đọc theo văn bản thuần.
- Hệ thống trung gian có chính sách chỉ lấy phần text/plain để lập chỉ mục/phân loại.
- Công cụ đọc mail tự động hoặc kiểm thử giả định message có plain text, nhưng phần đó không tồn tại.
- Một client xử lý HTML không đầy đủ, làm mất bảng, nút hoặc link ở bản hiển thị.
- Người đọc sao chép nội dung vào môi trường không giữ format hoặc không lấy được URL nằm sau chữ “Nhấn vào đây”.

Đây là **rủi ro tương thích và chất lượng nội dung**, không phải quy luật “email HTML-only chắc chắn thất bại”. Cần nhìn đúng phạm vi tác động.

### Không được kết luận “SMTP gửi lỗi” chỉ vì plain text thiếu

SMTP server có thể vẫn chấp nhận message HTML-only và trả thành công. Khi đó **vấn đề nằm trong MIME content / trải nghiệm downstream**, không phải kết nối SMTP, credentials hoặc JavaMailSender.send() bị lỗi.

## 2. Vì sao email có thể có nhiều cách biểu diễn?

Email hiện đại sử dụng MIME để mô tả nội dung khác nhau. Hai media types quan trọng:

| MIME type | Nội dung | Khi nào được dùng |
| --- | --- | --- |
| **text/plain** | Văn bản không có HTML formatting | Client đọc text-only, hệ thống xử lý văn bản, fallback |
| **text/html** | Nội dung có markup, link, layout | Client hỗ trợ HTML và được phép render |

**text/plain** không có nghĩa email phải xấu hoặc thiếu thông tin. Nó có thể có heading, các đoạn văn, bullet và URL thuần. **text/html** cho phép tiêu đề lớn, bảng, nút CTA và hình ảnh, nhưng phải được xây an toàn và kiểm thử ở mail clients.

### Ví dụ cùng một nội dung

Bản plain:

~~~text
XÁC NHẬN ĐƠN HÀNG

Xin chào khách hàng,

Đơn ORD-1528 đã được xác nhận.
Tổng tiền: 250.000 ₫.

Xem đơn hàng:
https://app.example.test/orders/ORD-1528

Nếu bạn không thực hiện giao dịch, hãy liên hệ
support@example.test.
~~~

Bản HTML:

~~~html
<h1>Xác nhận đơn hàng</h1>
<p>Xin chào khách hàng,</p>
<p>Đơn <strong>ORD-1528</strong> đã được xác nhận.</p>
<p>Tổng tiền: <strong>250.000 ₫</strong>.</p>
<p><a href="https://app.example.test/orders/ORD-1528">
  Xem đơn hàng
</a></p>
<p>Nếu bạn không thực hiện giao dịch,
  hãy liên hệ <a href="mailto:support@example.test">
    support@example.test</a>.</p>
~~~

Hai bản có thể khác **cách trình bày**, nhưng cần nhất quán về **sự thật nghiệp vụ**: mã đơn, số tiền, hành động được phép và địa chỉ liên hệ.

## 3. MIME multipart/alternative là gì?

**multipart/alternative** chứa nhiều biểu diễn của **cùng một nội dung logic**. Client chọn phiên bản phù hợp với khả năng và preference. Theo quy ước MIME, các phần thường được sắp xếp **từ đơn giản tới phong phú hơn**.

~~~text
MimeMessage
  Content-Type: multipart/alternative
  |
  +-- Part 1
  |     Content-Type: text/plain; charset=UTF-8
  |
  '-- Part 2
        Content-Type: text/html; charset=UTF-8
~~~

**Plain text đứng trước, HTML đứng sau** là cấu trúc thông dụng. Các parts là **alternatives**, không phải hai đoạn phải được hiển thị liên tiếp cho cùng người dùng.

### Một email, không phải hai notifications

Nhầm lẫn dễ xảy ra:

~~~text
Sai cách hiểu:
  send(plainMessage)
  send(htmlMessage)
  -> người nhận có thể nhận hai thư.

Đúng:
  một MimeMessage
    multipart/alternative
      text/plain
      text/html
  -> người nhận nhận một thư với hai biểu diễn.
~~~

Việc gửi hai email riêng có thể tạo duplicate notifications, làm sai metrics/consent và khiến người nhận khó hiểu. **multipart/alternative** là giải pháp trong cùng MIME message.

### Không dùng multipart/mixed để giả lập hai alternatives

Nếu đặt hai body parts độc lập dưới **multipart/mixed**, client có thể xem chúng như hai nội dung cộng thêm, đôi khi hiển thị cả plain lẫn HTML hoặc như attachment. Với hai biểu diễn cùng một nội dung, cần **multipart/alternative** (có thể nằm bên trong mixed/related khi cần).

### Plain và HTML phải có cùng ý nghĩa

Không nên để plain:

~~~text
Bạn đã đăng ký thành công.
~~~

nhưng HTML:

~~~text
Đăng ký chưa hoàn tất. Cần xác thực trong 15 phút.
~~~

Sự khác biệt này không phải “alternative” về trình bày; nó tạo mâu thuẫn nghiệp vụ. Nguồn dữ liệu và quy tắc kiểm tra phải dùng chung.

## 4. Những overload setText() dễ bị nhầm

**MimeMessageHelper** có các overload thường dùng:

~~~java
helper.setText("Nội dung văn bản thuần");

helper.setText(
        "<strong>Nội dung HTML</strong>",
        true
);

helper.setText(
        "Nội dung văn bản thuần",
        "<strong>Nội dung HTML</strong>"
);
~~~

### So sánh

| Lời gọi | Mục đích | Có phần plain thay thế? |
| --- | --- | --- |
| **setText(String text)** | Chỉ plain text | Bản thân message là plain |
| **setText(String text, boolean html)** với false | Plain text | Bản thân message là plain |
| **setText(String text, boolean html)** với true | Chỉ HTML | **Không tự tạo bản plain tương đương** |
| **setText(String plainText, String htmlText)** | Cả plain và HTML | **Có**, hai alternatives |

Với email HTML có khả năng fallback, chọn overload **hai String**. Đừng thấy hai tham số rồi nhầm **(html, true)** với **(plain, html)**: trong overload thứ hai, tham số thứ hai là **String HTML**, không phải boolean.

### Không đảo vị trí

~~~java
// Sai nghĩa: HTML sẽ được đặt làm plain part,
// plain text sẽ được đặt làm HTML part.
helper.setText(html, plain);
~~~

Phải truyền:

~~~java
helper.setText(plain, html);
~~~

### Không cần gọi setText hai lần

Đoạn code sau không phải cách đáng tin để tạo alternatives:

~~~java
helper.setText(plain);
helper.setText(html, true);
~~~

Lời gọi thứ hai có thể thay cấu hình phần nội dung của helper, tùy implementation; nó **không tương đương** với overload hai String. Dùng đúng:

~~~java
helper.setText(plain, html);
~~~

## 5. Cấu hình MimeMessageHelper để dùng alternatives

Để helper tạo cấu trúc multipart với plain và HTML, cần khởi tạo ở **multipart mode** phù hợp.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MailExample {

    private final JavaMailSender sender;

    public MailExample(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) throws Exception {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("Thông báo tài khoản");

        String plain =
                "Xin chào,\n\nTài khoản đã được kích hoạt.\n";
        String html =
                "<p>Xin chào,</p><p>Tài khoản đã được "
                + "<strong>kích hoạt</strong>.</p>";

        helper.setText(plain, html);
        sender.send(message);
    }
}
~~~

**new MimeMessageHelper(message, true, "UTF-8")** bật multipart và chọn encoding cho helper. Phần text/plain/text/html được tạo bằng **setText(plain, html)**. Host SMTP và credentials được cấu hình tại JavaMailSender bên ngoài ví dụ.

### Có cần multipart khi email chỉ plain?

Không nhất thiết:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("Chỉ có văn bản.");
~~~

Khi không có HTML hoặc attachment, dùng text/plain đơn là hợp lý; lỗi trong bài **không phải thiếu multipart ở mọi loại email**, mà là **đã có HTML nhưng không cung cấp plain alternative khi cần hỗ trợ nội dung tương đương**.

### Tại sao UTF-8?

Email tiếng Việt có dấu cần charset phù hợp; **UTF-8** giúp Subject/Body thể hiện Unicode. Tuy nhiên, charset không tạo plain text giúp bạn. **UTF-8 + HTML-only** vẫn là HTML-only.

### Spring Boot mail starter không tự bổ sung plain

Spring Boot cấu hình JavaMailSender/SMTP không đồng nghĩa tự tạo text/plain từ HTML. Ứng dụng phải **tự chuẩn bị hai body** trước khi gọi helper. Không trông chờ provider SMTP hoặc Thymeleaf âm thầm làm việc đó.

## 6. Triệu chứng trong raw MIME và cách phát hiện

Một email HTML-only có thể gần giống:

~~~text
From: notifications@example.test
To: customer@example.test
Subject: =?UTF-8?...?=
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<h1>Đơn hàng thành công</h1>
~~~

Hoặc một cấu trúc nested MIME có **text/html** nhưng không có **text/plain**. Việc message root là multipart **không tự chứng minh** đã có alternatives.

Một email có cả hai:

~~~text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alternative-boundary"

--alternative-boundary
Content-Type: text/plain; charset=UTF-8

Đơn ORD-1528 đã được xác nhận.
Xem: https://app.example.test/orders/ORD-1528

--alternative-boundary
Content-Type: text/html; charset=UTF-8

<p>Đơn <strong>ORD-1528</strong> đã được xác nhận.</p>
<p><a href="https://app.example.test/orders/ORD-1528">Xem</a></p>

--alternative-boundary--
~~~

Các boundary và encoded headers là minh họa. Jakarta Mail có thể tự sinh boundary và transfer encodings khác nhau. Khi kiểm thử, nên parse MIME tree và assert semantics thay vì so khớp raw boundary strings.

### Không đoán dựa vào Content-Type root

Nếu có attachment, root có thể là **multipart/mixed**. Nếu có ảnh inline, có thể thêm **multipart/related**. Do đó một test kiểu:

~~~java
assertTrue(message.getContentType().startsWith(
        "multipart/alternative"
));
~~~

có thể fail dù message vẫn chứa plain+HTML hợp lệ bên trong. Cần duyệt MIME tree theo cấu trúc và tìm cặp alternatives đúng.

### Đừng tưởng hai phần trong MIME là hai emails

**multipart/alternative** có cùng envelope recipient và cùng notification business key. Khi email được gửi, SMTP xử lý một message, không hai email độc lập.

## 7. Kiến trúc đúng: tạo hai nội dung từ cùng model

Một cách chống mâu thuẫn giữa hai phiên bản là dùng **cùng dữ liệu nghiệp vụ đã được chốt** và render hai templates riêng:

~~~text
OrderConfirmed event
        |
        v
Immutable notification model
  - customer name
  - order code
  - total/currency
  - trusted order URL
        |
        +--------------------+
        |                    |
        v                    v
Plain template          HTML template
        |                    |
        v                    v
Rendered plain          Rendered HTML
        |                    |
        +----------+---------+
                   |
                   v
            Validate consistency
                   |
                   v
             setText(plain, html)
                   |
                   v
              SMTP submission
~~~

### Dùng record cho model

~~~java
import java.math.BigDecimal;
import java.net.URI;
import java.util.Currency;

public record OrderConfirmationModel(
        String customerDisplayName,
        String orderCode,
        BigDecimal totalAmount,
        Currency currency,
        URI orderUrl
) {
}
~~~

Model được tạo từ một business snapshot phù hợp, không nên có các template độc lập tự gọi database để lấy đơn hàng tại những thời điểm khác nhau.

### Renderer trả về cả hai parts

~~~java
public record MailContent(
        String subject,
        String plainText,
        String html
) {
}

public interface OrderConfirmationRenderer {
    MailContent render(OrderConfirmationModel model);
}
~~~

Business service không nhất thiết phải biết chi tiết **MimeMessageHelper**. Nó tạo model và yêu cầu renderer; mail composer nhận MailContent đã được validate.

### Tại sao không chỉ render HTML rồi xóa tags?

HTML-to-text conversion có thể hữu ích khi hệ thống lưu HTML legacy và không có plain template, nhưng không tự bảo đảm thông tin tương đương. Các tình huống dễ mất:

- Text hiển thị **“Xác nhận tài khoản”** nhưng URL thật nằm trong thuộc tính **href**.
- Bảng có cột tên/số lượng/giá, khi strip tags bị dính thành một dòng khó hiểu.
- Ảnh có chữ hoặc diagram quan trọng nhưng không có alt text.
- CSS dùng để ẩn/hiện nội dung theo viewport hoặc display.
- HTML sử dụng entity và nested elements làm xuống dòng sai.
- Disclaimer/unsubscribe nằm trong footer bị converter bỏ sót.

**Hai templates từ cùng model** thường dễ kiểm soát hơn khi email có chức năng nghiệp vụ quan trọng.

## 8. Plain text phải đầy đủ về mặt hành động

Một bản text/plain tốt trả lời được:

- Email này nói về **sự việc gì**?
- Những dữ liệu nghiệp vụ quan trọng là gì?
- Người nhận cần **làm gì tiếp theo**?
- Nếu có link, họ có thể sử dụng URL đầy đủ hoặc cách thay thế?
- Có chỉ dẫn liên hệ, thời hạn, cảnh báo hoặc unsubscribe theo policy không?

### Ví dụ lỗi: CTA chỉ có trong HTML

Plain sai:

~~~text
Tài khoản của bạn cần được xác nhận.
Vui lòng mở phiên bản HTML để thao tác.
~~~

HTML:

~~~html
<p>Tài khoản của bạn cần được xác nhận.</p>
<a href="https://app.example.test/confirm?t=example-token">
  Xác nhận tài khoản
</a>
~~~

Phiên bản plain không chứa link; với text-only client, người nhận không thể thực hiện hành động.

Plain tốt hơn:

~~~text
XÁC NHẬN TÀI KHOẢN

Tài khoản của bạn cần được xác nhận.

Đường dẫn xác nhận:
https://app.example.test/confirm?t=example-token

Liên kết có hiệu lực trong 15 phút.
Nếu bạn không yêu cầu, hãy bỏ qua thư này.
~~~

**Lưu ý bảo mật:** Token trong ví dụ là placeholder. Link xác nhận thật cần được tạo từ service được tin cậy, có thời hạn, policy dùng một lần và không ghi raw token vào logs. Plain và HTML nên dùng **cùng verified URL**; không sinh hai token khác nhau chỉ vì có hai parts.

### Link anchor là điểm hay bị mất nhất

HTML có thể biểu diễn:

~~~html
<a href="https://app.example.test/orders/ORD-1528">
  Theo dõi đơn hàng
</a>
~~~

Plain phải có link:

~~~text
Theo dõi đơn hàng:
https://app.example.test/orders/ORD-1528
~~~

Một converter chỉ lấy text node có thể trả **“Theo dõi đơn hàng”** và làm mất URL. Với CTA quan trọng, nên test cụ thể URL trong cả hai phần.

## 9. Plain text không phải HTML bỏ thẻ tùy tiện

Nếu plain được sinh bằng thao tác đơn giản:

~~~java
String plain = html.replaceAll("<[^>]+>", "");
~~~

đây là một **cách không phù hợp** cho email production. Regex này:

- Không hiểu cấu trúc HTML đầy đủ.
- Có thể bỏ mất URL trong href.
- Không định nghĩa cách xuống dòng cho p, br, li, tr.
- Không xử lý encoding/entities đúng nghĩa.
- Có thể gây lỗi với markup bất thường.
- Không bảo đảm nội dung hiển thị rõ ràng.

### Một converter phải hiểu HTML document

Nếu bắt buộc chuyển HTML thành text, cần parser HTML phù hợp, sau đó xử lý:

1. Tách phần không hiển thị như script/style/tracking theo policy.
2. Chuyển heading, paragraph, list, line breaks thành cấu trúc văn bản.
3. Đưa URL của các links quan trọng ra dạng có thể đọc.
4. Chuyển table thành dòng có labels hoặc một format dễ hiểu.
5. Ghi alternative text cho ảnh khi có ý nghĩa.
6. Giải mã HTML entities và chuẩn hóa Unicode.
7. Giới hạn kích thước và tài nguyên.
8. Kiểm tra không mất disclaimer/CTA.

Ngay cả parser tốt cũng khó biết **ý nghĩa nghiệp vụ** của một layout. Vì vậy converter nên là **phương án dự phòng có test**, không phải giả định “HTML đã đủ thì plain tự đúng”.

### Lựa chọn chiến lược

| Chiến lược | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Hai templates từ cùng model | Kiểm soát nội dung và layout theo kênh | Cần duy trì hai templates |
| HTML-to-text bằng parser | Tự động hóa, giảm công viết ban đầu | Khó giữ CTA/bảng/ý nghĩa |
| Chỉ plain text | Đơn giản, rõ ràng | Không có trình bày HTML |
| Chỉ HTML | Ít công nhất | Không có representation plain thay thế |

Với email giao dịch/bảo mật, hai templates có kiểm thử thường đáng chi phí. Với email đơn giản, có thể dùng một **canonical text content** rồi tạo HTML bằng renderer an toàn, miễn cả hai vẫn đúng nghĩa.

## 10. Cấu trúc nội dung plain text tốt

Text/plain vẫn cần trình bày dễ đọc. Có thể sử dụng:

~~~text
XÁC NHẬN ĐƠN HÀNG
------------------

Xin chào khách hàng,

Đơn hàng:  ORD-1528
Trạng thái: Đã xác nhận
Tổng tiền: 250.000 ₫

XEM CHI TIẾT
https://app.example.test/orders/ORD-1528

HỖ TRỢ
Nếu bạn có câu hỏi, vui lòng liên hệ
support@example.test.
~~~

### Gợi ý trình bày

- Viết ngắn, rõ, chia đoạn.
- Tránh tạo bảng ASCII quá rộng khó đọc trên màn hình hẹp.
- Giữ nhãn/giá trị gần nhau để dễ hiểu dù email client wrap lines.
- Viết đầy đủ URL của CTA quan trọng.
- Dùng bullet hoặc số thứ tự cho danh sách.
- Không phụ thuộc màu sắc hoặc hình ảnh để phân biệt trạng thái.
- Giữ văn bản có dấu tiếng Việt chính xác bằng UTF-8.
- Đừng nhúng raw HTML entities như **&amp;** vào plain nếu mục tiêu là hiển thị dấu **&**.

### Với email nhiều dòng hàng

Plain:

~~~text
ĐƠN ORD-1528

Sản phẩm:
- Sách Java: 1 × 120.000 ₫ = 120.000 ₫
- Sổ ghi chú: 2 × 65.000 ₫ = 130.000 ₫

Tổng: 250.000 ₫
~~~

HTML có thể trình bày cùng dữ liệu bằng table. Hai representation phải thống nhất quantities và totals; formatting có thể khác.

### Về độ dài dòng

Một số clients/transport có quy tắc line length, wrapping và transfer encodings riêng. JavaMail xử lý nhiều chi tiết MIME/transfer encoding. Ứng dụng vẫn nên tạo plain text dễ wrap và không dựa vào khoảng trắng để cố định cột rộng. Không tự chèn CRLF vào headers hoặc sửa raw MIME tùy tiện.

## 11. Plain text cho email bảo mật và xác thực

Các email **OTP, password reset, account verification, login alert** cần ưu tiên rõ ràng:

~~~text
XÁC NHẬN ĐĂNG NHẬP

Mã xác nhận: 482193
Mã có hiệu lực trong 5 phút.

Không chia sẻ mã này với bất kỳ ai.
Nếu bạn không yêu cầu đăng nhập, vui lòng kiểm tra
bảo mật tài khoản theo hướng dẫn chính thức.
~~~

Bản HTML có thể làm nổi bật mã bằng typography, nhưng **plain text cũng phải chứa mã** hoặc một kênh thực hiện khác theo yêu cầu sản phẩm. Không nên đặt thông tin quan trọng chỉ trong hình ảnh hoặc CSS pseudo-elements.

### Không tạo OTP riêng cho từng bản MIME

Sai:

~~~text
HTML template calls generateOtp() -> 482193
Plain template calls generateOtp() -> 917201
~~~

Điều này khiến một phần hiển thị mã sai. Đúng hơn là tạo **một OTP trong service nghiệp vụ**, lưu state/TTL phù hợp rồi truyền cùng model sang cả hai renderers.

### Token URL phải có cùng semantics

HTML và plain dùng cùng URL đã được validate từ trusted service. Nếu plain link không giống HTML link, đó là **sự khác biệt nghiêm trọng** chứ không phải vấn đề thẩm mỹ.

### Đừng lưu token trong log để debug rendering

Nếu email yêu cầu OTP, password reset link hoặc mã thanh toán, không log đầy đủ rendered plain/html, vì cả hai có thể chứa secrets. Quan sát bằng notification ID opaque, template revision, render status và error category. Preview/test dùng token giả.

## 12. Email marketing và footer bắt buộc

Với email marketing, bản plain không được bỏ đi các đoạn nội dung mà quy trình/luật áp dụng yêu cầu, ví dụ sender identity, thông tin liên hệ và **cơ chế hủy đăng ký** phù hợp.

Ví dụ text:

~~~text
THÔNG TIN SẢN PHẨM MỚI

Chúng tôi cập nhật các tính năng mới tháng này.

Xem thông tin:
https://app.example.test/updates

Bạn nhận email vì đã đăng ký nhận tin.
Hủy đăng ký:
https://app.example.test/preferences/unsubscribe?token=sample
~~~

HTML có thể dùng nút “Hủy đăng ký”, nhưng nếu text/plain bị bỏ trống hoặc thiếu link, người dùng text-only khó thực hiện lựa chọn. Cần đồng bộ với chính sách consent/suppression trên server; một URL trong footer không thay thế được việc hệ thống thực sự tôn trọng opt-out.

### List-Unsubscribe headers

Một số email marketing còn dùng **List-Unsubscribe** và/hoặc **List-Unsubscribe-Post** theo cơ chế thích hợp. Các headers này không thể thay thế hoàn toàn nội dung/hướng dẫn hủy đăng ký trong body khi chính sách yêu cầu. Đồng thời, text/plain cũng không tự tạo được header List-Unsubscribe.

### Đừng sao chép nhầm hủy đăng ký vào email bảo mật

Security/transactional messages có mục đích khác marketing. Không dùng một footer marketing chung có unsubscribe semantics sai cho password reset hoặc thông báo bảo mật bắt buộc. **Template purpose** cần quyết định phần footer và policy phù hợp, đồng thời cả plain/HTML phải thể hiện chính xác.

## 13. HTML và plain text có thể dùng cùng một template model

Trong hệ thống có nhiều email templates, nên đặt model trong một object do ứng dụng tạo, rồi render hai versions:

~~~java
import java.math.BigDecimal;
import java.net.URI;
import java.util.Currency;
import java.util.Locale;

public record OrderMailModel(
        String customerDisplayName,
        String orderCode,
        BigDecimal totalAmount,
        Currency currency,
        URI orderUrl,
        Locale locale
) {
}
~~~

### Renderer không nên query dữ liệu độc lập

Sai:

~~~text
Plain renderer:
  find order total from database at 10:00:00

HTML renderer:
  find order total from database at 10:00:02
~~~

Nếu có thay đổi hoặc một service trả kết quả khác, hai parts có thể lệch nhau. Nên tạo **model snapshot** trước, validate rồi đưa cùng snapshot vào hai renderers.

### Một giao diện renderer có hợp đồng rõ

~~~java
public interface MailContentRenderer<M> {

    MailContent render(M model);
}

public record MailContent(
        String subject,
        String plain,
        String html
) {
}
~~~

Một service có thể:

~~~java
MailContent content = renderer.render(model);

validateMailContent(content);

helper.setSubject(content.subject());
helper.setText(content.plain(), content.html());
~~~

Đây là code minh họa. **validateMailContent** là function do ứng dụng định nghĩa, kiểm tra nội dung/URL/schema theo policy; Spring không tự cung cấp method này.

### Các thông tin cần nhất quán

| Field | Cùng giá trị trong plain và HTML? |
| --- | --- |
| Mã đơn hàng | Có |
| Số tiền, đơn vị tiền | Có |
| Mã OTP | Có |
| Thời hạn của link | Có |
| Hướng dẫn hành động | Có |
| Link dẫn tới nơi thực hiện hành động | Có |
| Trạng thái giao dịch | Có |
| Thông tin liên hệ quan trọng | Có |
| Cỡ chữ, màu sắc, thẻ HTML | Không cần giống |

### Tránh tự phát minh văn bản ở hai service

Nếu plain template nằm trong code A, HTML template nằm trong code B và hai nhóm sở hữu khác nhau, nội dung có thể lệch theo thời gian. Một **template registry có versioning** hoặc một release process chung giúp biết bản plain và HTML nào thuộc cùng notification template revision.

## 14. Ví dụ Thymeleaf render HTML và plain text

**Thymeleaf** có thể render template HTML và text khi được cấu hình đúng. Nó không tự động tạo plain alternative chỉ vì HTML đã được render.

Ví dụ file **order-confirmed.html**:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<body>
  <h1>Xác nhận đơn hàng</h1>
  <p>Xin chào <strong th:text="${customerDisplayName}">bạn</strong>,</p>
  <p>Đơn <span th:text="${orderCode}">ORD-000</span>
     đã được xác nhận.</p>
  <p>Tổng tiền: <strong th:text="${formattedTotal}">0 ₫</strong></p>
  <a th:href="${orderUrl}">Xem chi tiết</a>
</body>
</html>
~~~

Ví dụ file **order-confirmed.txt** khi dùng Thymeleaf TEXT template mode:

~~~text
XÁC NHẬN ĐƠN HÀNG

Xin chào [[${customerDisplayName}]],

Đơn [[${orderCode}]] đã được xác nhận.
Tổng tiền: [[${formattedTotal}]]

Xem chi tiết:
[[${orderUrl}]]
~~~

### Lưu ý về template modes

**Thymeleaf HTML mode** phù hợp với th:text, th:href; **TEXT mode** dùng cú pháp inline text tương ứng. Nếu chỉ cấu hình một ClassLoaderTemplateResolver cho HTML, việc gọi **process("order-confirmed.txt", context)** có thể không cho kết quả mong đợi nếu template mode không được chọn đúng.

Một hướng thiết kế:

~~~text
TemplateEngine HTML
  -> resolver HTML
  -> order-confirmed.html

TemplateEngine TEXT
  -> resolver TEXT
  -> order-confirmed.txt
~~~

Có thể dùng một engine với nhiều resolvers được cấu hình theo suffix/pattern, nhưng phải xác định **mode**, **resolver order** và **cache key**. Không cần cố gộp cả hai vào một Java string.

### Context dùng chung

~~~java
import org.thymeleaf.context.Context;

Context context = new Context(model.locale());
context.setVariable(
        "customerDisplayName", model.customerDisplayName()
);
context.setVariable("orderCode", model.orderCode());
context.setVariable("formattedTotal", formattedTotal);
context.setVariable("orderUrl", model.orderUrl().toString());
~~~

**formattedTotal** nên được tính bằng formatter đã kiểm soát locale/currency và dùng chung cho cả hai parts. **orderUrl** phải được tạo/validate từ trusted application service, không lấy host tùy ý do người dùng cung cấp.

### Render trước khi gửi

~~~java
String plain = textEngine.process(
        "order-confirmed.txt", context
);

String html = htmlEngine.process(
        "order-confirmed.html", context
);

helper.setText(plain, html);
~~~

**textEngine** và **htmlEngine** là hai TemplateEngine đã được cấu hình với resolver phù hợp; đây là minh họa kiến trúc, không phải beans có sẵn chỉ từ spring-boot-starter-mail.

## 15. Ví dụ Spring Boot: service gửi HTML kèm plain

Dưới đây là ví dụ sử dụng **JavaMailSender** và class riêng để render hai content variants. Phần render trong ví dụ tạo chuỗi trực tiếp để code độc lập, nhưng trong dự án lớn có thể thay bằng Thymeleaf/registry.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailService {

    private final JavaMailSender sender;

    public AccountNotificationMailService(
            JavaMailSender sender
    ) {
        this.sender = sender;
    }

    public void sendActivated(
            String recipient,
            AccountActivationMail model
    ) throws MessagingException {
        // 1. Validate recipient, sender, model và URL ở lớp ngoài.
        // 2. Render cả hai biến thể từ cùng model.
        String plain =
                "Xin chào " + model.displayName() + ",\n\n"
                + "Tài khoản của bạn đã được kích hoạt.\n\n"
                + "Xem thông tin tài khoản:\n"
                + model.accountUrl() + "\n";

        String html =
                "<p>Xin chào " + model.escapedDisplayName()
                + ",</p>"
                + "<p>Tài khoản của bạn đã được "
                + "<strong>kích hoạt</strong>.</p>"
                + "<p><a href=\"" + model.escapedAccountUrl()
                + "\">Xem thông tin tài khoản</a></p>";

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("accounts@example.test");
        helper.setTo(recipient);
        helper.setSubject("Tài khoản đã được kích hoạt");
        helper.setText(plain, html);
        sender.send(mime);
    }
}
~~~

Với record minh họa:

~~~java
public record AccountActivationMail(
        String displayName,
        String escapedDisplayName,
        String accountUrl,
        String escapedAccountUrl
) {
}
~~~

**escapedDisplayName** và **escapedAccountUrl** là dữ liệu giả định đã được encode/validate đúng cho từng HTML context bởi tầng render tin cậy, không phải thứ nên để caller tùy ý cung cấp. Trong production, **không nối HTML bằng chuỗi để render dữ liệu người dùng** như pattern chính; dùng engine tự escape theo context và URI validator. Ví dụ chỉ minh họa rằng **cùng thông tin hiển thị trong plain lẫn HTML**, không phải một hệ thống escaping hoàn chỉnh.

### Hạn chế của ví dụ

- Chưa có SMTP host/port/TLS/credentials; chúng thuộc cấu hình sender.
- Chưa có suppression/consent/sender policy.
- Chưa lưu notification/outbox để retry an toàn.
- Chưa kiểm tra model bằng Bean Validation hay schema riêng.
- Chưa hỗ trợ attachment, inline images hoặc nhiều locale.
- Chưa định nghĩa idempotency khi provider accepted nhưng response mất.

Không nên lấy service demo và xem nó là toàn bộ giải pháp production. Tuy nhiên, điểm sửa lỗi chính đã có: **setText(plain, html)** thay cho **setText(html, true)**.

## 16. MIME tree khi có attachments

Khi thư có tệp đính kèm, root MIME có thể chuyển thành **multipart/mixed**, bên trong có alternative cho body.

~~~text
MimeMessage
  Content-Type: multipart/mixed
  |
  +-- multipart/alternative
  |     |
  |     +-- text/plain
  |     '-- text/html
  |
  '-- application/pdf (attachment)
~~~

Tùy MIME helper mode, cấu trúc còn có **multipart/related** trung gian. Điều quan trọng không phải tên root phải bằng **multipart/alternative**, mà là body có **plain và HTML dưới quan hệ alternative đúng**.

### Ví dụ thêm attachment

~~~java
import org.springframework.core.io.ByteArrayResource;

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setTo(recipient);
helper.setSubject("Biên nhận đơn hàng");
helper.setText(plain, html);
helper.addAttachment(
        "receipt.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

sender.send(message);
~~~

**ByteArrayResource** có thể phù hợp cho dữ liệu nhỏ đã có trong memory; với attachments lớn cần quản lý size, storage/streaming và resource lifecycle để tránh giữ toàn bộ bytes trong heap. Bản plain có thể nói “Biên nhận PDF được đính kèm”, nhưng không được chứa raw PDF bytes.

### Đính kèm không phải plain alternative

Một PDF attachment chứa nội dung hóa đơn **không thay thế** việc có text/plain khi HTML body là nội dung chính. Email vẫn nên có lời giải thích/CTA có nghĩa ở plain. Tùy nghiệp vụ, details đầy đủ có thể được lưu trong attachment và body nêu cách truy cập nó.

### Không hiển thị hai alternatives như attachments

Nếu test SMTP catcher hiển thị hai MIME parts, đó có thể là representations bình thường. Không tự kết luận “người nhận nhận hai nội dung” khi MIME tree đúng, cũng không cố xóa một part để làm UI thử nghiệm nhìn gọn.

## 17. MIME tree khi HTML có ảnh inline CID

HTML email có thể tham chiếu ảnh inline:

~~~html
<p>Xin chào!</p>
<img src="cid:brand-logo" alt="Logo công ty">
~~~

Với cấu trúc thường gặp:

~~~text
MimeMessage
  multipart/mixed
    |
    '-- multipart/related
          |
          +-- multipart/alternative
          |      |
          |      +-- text/plain
          |      '-- text/html
          |
          '-- image/png
                 Content-ID: <brand-logo>
~~~

Code:

~~~java
import org.springframework.core.io.ClassPathResource;

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

String plain =
        "Xin chào!\n\nThông tin tài khoản có tại:\n"
                + "https://app.example.test/account";
String html =
        "<p>Xin chào!</p>"
        + "<img src=\"cid:brand-logo\" alt=\"Logo công ty\">"
        + "<p><a href=\"https://app.example.test/account\">"
        + "Xem tài khoản</a></p>";

helper.setText(plain, html);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

Ở ví dụ này, tài nguyên cần tồn tại và có MIME type phù hợp; code không thực sự gọi sender.send() trong đoạn cuối để tập trung vào compose. Theo hướng dẫn thường dùng của MimeMessageHelper, **gọi setText(...) trước addInline(...)** để giữ hành vi tương thích với mail clients.

### Plain không cần hình nhưng cần thông tin

Không nhất thiết chuyển ảnh logo thành ASCII art. Plain text có thể ghi brand name, nội dung và link rõ ràng. Nếu ảnh chứa dữ liệu quan trọng (ví dụ mã giảm giá chỉ nằm trong banner), plain cần diễn đạt thông tin đó bằng văn bản.

### Alternative và related có nhiệm vụ khác nhau

| Multipart | Quan hệ giữa parts |
| --- | --- |
| **alternative** | Các cách biểu diễn cùng nội dung |
| **related** | Tài nguyên liên kết để hiển thị một nội dung (CID) |
| **mixed** | Các thành phần độc lập cùng email, ví dụ attachment |

Không dùng **related** để thay **alternative**. Một email có cả ba cần nesting hợp lý; các MIME helper modes hỗ trợ nhưng phải kiểm tra cấu trúc và mail client mục tiêu.

## 18. Plain text và accessibility

Một lý do hỗ trợ plain text là giúp một số clients và quy trình đọc văn bản có thể tiếp cận nội dung dễ hơn. Nhưng **có plain text không tự động làm email accessible**, và ngược lại HTML có semantic markup tốt cũng có thể hỗ trợ screen readers.

### Những nguyên tắc có ích ở cả hai bản

- Nội dung chính không được phụ thuộc duy nhất vào màu sắc.
- CTA có nhãn mô tả hành động thực sự, không chỉ “Nhấn vào đây”.
- Ảnh có nội dung quan trọng cần alt text/diễn đạt bằng chữ.
- Thông tin tiền, thời gian, mã và link phải rõ ràng.
- Tránh layout table gây thứ tự đọc khó hiểu.
- Dùng headings/list semantic trong HTML khi phù hợp.
- Plain có đoạn, bullet và link đầy đủ.
- Không dùng ký tự trang trí dày đặc khiến screen reader khó đọc.

### Text-only không thay thế kiểm thử accessibility

Nếu sản phẩm có yêu cầu accessibility, cần kiểm tra rendered HTML với tools/clients phù hợp và kiểm tra plain text thủ công. Không có quy tắc chung rằng mọi screen reader sẽ luôn dùng text/plain; nhiều công cụ đọc màn hình vẫn đọc HTML do mail client render.

## 19. Encoding, line ending và MIME headers

Một email chứa tiếng Việt cần quan tâm:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=UTF-8
~~~

Khi dùng **MimeMessageHelper(..., "UTF-8")**, helper thiết lập encoding phù hợp cho nội dung. Jakarta Mail có thể chọn transfer encoding như **quoted-printable** hoặc **base64** tùy nội dung/implementation.

### Không tự suy ra plain từ encoded HTML bytes

Nếu raw source là:

~~~text
Content-Transfer-Encoding: quoted-printable
~~~

đó là **cách mã hóa dữ liệu truyền qua MIME**, không phải một plain-text representation. Decode quoted-printable của HTML vẫn cho HTML; nó không tự xóa thẻ hoặc bổ sung text/plain.

### Subject dùng encoding riêng

Subject là header, thường được mã hóa theo quy tắc MIME header; body là MIME part. Một email có Subject UTF-8 đúng vẫn có thể thiếu plain alternative.

### Header injection

Không cho biến từ người dùng chứa CR/LF đi thẳng vào Subject/From/To/Reply-To. Có thể dùng APIs của Jakarta Mail/Spring Mail để compose nhưng vẫn phải validate dữ liệu theo policy. Plain text body có line breaks là bình thường; **header** chèn CRLF trái ý định có thể tạo header injection.

### Plain và HTML có thể có transfer encoding khác nhau

Trong raw MIME, một part có thể là quoted-printable, phần kia là base64. Test nên dùng Jakarta Mail parser decode nội dung, không so sánh raw bytes hoặc yêu cầu cả hai parts cùng transfer encoding.

## 20. Email deliverability: không phóng đại vai trò plain text

Nhiều bài hướng dẫn khẳng định “không có text/plain là email bị spam”. Cần phân biệt thực tế:

- Một số spam filters và mail clients có thể sử dụng mức độ hoàn chỉnh của MIME/nội dung khi đánh giá thư.
- Có plain alternative giúp khả năng tương thích và làm nội dung dễ trích xuất hơn ở một số hệ thống.
- Nhưng **không có bảo đảm rằng thêm plain text sẽ đưa email vào Inbox**, và không có công thức chung cho mọi provider.
- Deliverability còn phụ thuộc SPF, DKIM, DMARC, sender reputation, consent, recipient engagement, nội dung và chính sách mail provider.

### Plain text là chất lượng nội dung, không phải mẹo vượt spam

Không nên tạo một plain part rỗng, chứa keywords vô nghĩa hoặc sai khác với HTML chỉ để “lách spam filter”. Điều đó có thể gây vấn đề tin cậy hoặc classification.

### Cần kiểm tra end-to-end

Một chiến lược kiểm thử:

1. Parse MIME tree, xác minh có đúng plain/HTML alternatives.
2. Kiểm tra nội dung chính nhất quán.
3. Gửi qua SMTP fixture hoặc mailbox thử nghiệm.
4. Xem hiển thị text-only/HTML theo clients được hỗ trợ.
5. Theo dõi accepted, delivered/bounced theo provider khi có dữ liệu.

**SMTP 250 accepted** không bằng **đã đến Inbox**; thêm text/plain không thay đổi nguyên tắc này.

## 21. Email clients chọn alternative như thế nào?

Với **multipart/alternative**, client thường chọn một representation có thể render và phù hợp preference. HTML có thể được ưu tiên khi client hỗ trợ, còn plain là bản thay thế nếu HTML không phù hợp.

### Những giả định không nên dùng

| Giả định | Vấn đề |
| --- | --- |
| Client luôn render cả hai | Alternatives thường không dùng để hiển thị cộng dồn |
| Client luôn chọn HTML | Có client/preference dùng plain |
| Chỉ cần text/plain trống | Người dùng text-only sẽ không có nội dung |
| Client sẽ tự strip HTML tốt | Không bảo đảm; có thể mất links |
| MIME tree root luôn là alternative | Attachments/CID tạo nesting |
| Dùng plain text thì HTML không cần semantic markup | HTML vẫn cần accessibility |
| Email HTML-only luôn bị từ chối | Không đúng với nhiều clients/providers |

### Nếu client có tùy chọn “View as plain text”

Khi thư có **text/plain**, ứng dụng nhận có thể hiển thị phần đó. Nếu thư chỉ có HTML, client có thể tự chuyển HTML sang text hoặc vẫn hiển thị HTML tùy implementation. Không nên yêu cầu người nhận dựa vào conversion của client để thực hiện CTA quan trọng.

### Nhiều content parts khác nhau

Một thư có thể có cả HTML body, inline images, attachments và embedded emails. Client render theo MIME nesting và các chính sách riêng; test cần phản ánh cấu trúc thật, không đơn giản tìm chuỗi **"text/plain"** trong raw MIME rồi kết luận đúng.

## 22. Viết hàm kiểm tra plain/HTML trong MIME tree

Với **Jakarta Mail**, có thể duyệt MIME để xem một message chứa **multipart/alternative** có cả text/plain và text/html không.

Để kiểm tra **đúng relationship**, không nên chỉ đếm tổng số part:

~~~text
multipart/mixed
  +-- text/plain (đoạn ghi chú riêng)
  '-- text/html (attachment)
~~~

Trong ví dụ này có cả hai MIME types nhưng **không phải cặp alternatives** của cùng một body.

### Recursive inspector tập trung vào MIME structure

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class AlternativeInspector {

    public record AlternativeInfo(
            boolean hasPlain,
            boolean hasHtml
    ) {
        public boolean complete() {
            return hasPlain && hasHtml;
        }
    }

    public static boolean hasCompleteAlternative(Part root)
            throws Exception {
        return inspect(root, 0);
    }

    private static boolean inspect(
            Part part,
            int depth
    ) throws Exception {
        if (depth > 20) {
            throw new IllegalArgumentException(
                    "MIME tree too deeply nested"
            );
        }

        if (!part.isMimeType("multipart/*")) {
            return false;
        }

        Multipart multipart = (Multipart) part.getContent();

        if (part.isMimeType("multipart/alternative")) {
            boolean plain = false;
            boolean html = false;

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                plain |= child.isMimeType("text/plain");
                html |= child.isMimeType("text/html");
            }

            if (plain && html) {
                return true;
            }
        }

        for (int i = 0; i < multipart.getCount(); i++) {
            if (inspect(multipart.getBodyPart(i), depth + 1)) {
                return true;
            }
        }

        return false;
    }
}
~~~

Đây là **inspector minh họa** cho tree phổ biến có text/plain và text/html là con trực tiếp của multipart/alternative. Một MIME message hợp lệ có thể có nested related hoặc cấu trúc phức tạp hơn, lúc đó inspector cần mở rộng theo yêu cầu thực tế. Không dùng hàm này làm security validator cho MIME tùy ý từ Internet mà không có giới hạn số parts, bytes và thời gian. Trong unit test cho email **do chính ứng dụng tạo**, nó là một guard hữu ích.

### Vì sao kiểm tra completeAlternative?

Chỉ kiểm tra:

~~~java
assertTrue(message.isMimeType("multipart/*"));
~~~

chưa đủ: một email có attachment cũng là multipart nhưng có thể chỉ có HTML. Test phải đi sâu tới **alternative relationship**.

### Đừng buộc boundary phải cố định

Jakarta Mail tự sinh boundary có thể khác mỗi lần save/send; assertion dựa vào raw boundary sẽ flaky. Inspector dùng MIME APIs thì bền vững hơn.

## 23. Unit test không cần SMTP: kiểm tra MIME alternatives

Có thể dùng **JavaMailSenderImpl** để tạo một MimeMessage mà chưa kết nối SMTP. Test kiểm tra cấu trúc ngay sau khi compose.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class MailAlternativeTest {

    @Test
    void htmlMailAlsoProvidesPlainText() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Xác nhận đăng ký");

        helper.setText(
                "Đăng ký đã được xác nhận.",
                "<p>Đăng ký đã được <b>xác nhận</b>.</p>"
        );

        message.saveChanges();

        assertTrue(
                AlternativeInspector.hasCompleteAlternative(message)
        );
    }
}
~~~

Test này không nộp thư tới SMTP; nó kiểm tra cấu trúc do helper tạo. Nếu một team refactor:

~~~java
helper.setText(html, true);
~~~

test có thể phát hiện phần plain biến mất.

### Test negative path để tránh kiểm thử “luôn xanh”

Một test đối chứng:

~~~java
@Test
void htmlOnlyDoesNotPassAlternativeCheck() throws Exception {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setText("<p>Hello</p>", true);
    message.saveChanges();

    assertFalse(
            AlternativeInspector.hasCompleteAlternative(message)
    );
}
~~~

Test trên có thể đặt trong cùng test class và dùng lại imports. Khi kiểm tra quality gate, cần chắc chắn inspector không chỉ trả true khi thấy multipart root.

## 24. Kiểm tra nội dung thực tế, không chỉ MIME types

Một email có cấu trúc:

~~~text
multipart/alternative
  text/plain: ""
  text/html: "<h1>Payment due</h1><a href=...>Pay</a>"
~~~

đã có hai parts theo hình thức nhưng chưa có plain fallback có ích.

### Những assertion nên bổ sung

- Plain không blank và không chỉ chứa boilerplate.
- Plain chứa các trường business facts bắt buộc.
- HTML cũng chứa những facts đó.
- CTA URL trong plain và URL trong HTML trỏ đến cùng một nguồn tin cậy.
- Locale/tiền tệ/mã/timestamp thống nhất.
- Nếu có unsubscribe/footer bắt buộc, nó có mặt ở cả hai parts.
- Plain không còn thẻ HTML thô hoặc placeholders chưa được render.
- HTML không hiển thị token do người khác sở hữu.

### Tách MIME inspection và business assertions

**MIME inspection** trả lời “message có cấu trúc alternative đúng không?”. **Content assertions** trả lời “plain và HTML có thông tin tương đương theo domain không?”. Cần cả hai khi yêu cầu quan trọng.

### Một test render-level

~~~java
import static org.junit.jupiter.api.Assertions.*;

@Test
void plainContainsRequiredOrderFacts() {
    MailContent content = renderer.render(model);

    assertFalse(content.plain().isBlank());
    assertTrue(content.plain().contains("ORD-1528"));
    assertTrue(content.plain().contains(
            "https://app.example.test/orders/ORD-1528"
    ));
    assertTrue(content.html().contains("ORD-1528"));
}
~~~

**renderer** và **model** là fixtures/test dependencies của ứng dụng; ví dụ không định nghĩa chúng để tránh trộn việc xây domain vào test MIME. Trong dự án thật phải cung cấp test fixture cụ thể cho từng template.

### Test tương đương ngữ nghĩa tốt hơn byte equality

Không assert rằng **plain.equals(stripHtml(html))**. Plain có formatting khác HTML theo thiết kế; điều cần là consistency của **business fields** và actionable links.

## 25. Integration test bằng SMTP fixture và email client

Unit test MimeMessage chưa đủ để biết lúc email được nộp qua sender và nhận bởi server thử nghiệm có giữ hai parts. Có thể dùng **GreenMail** hoặc SMTP catcher cô lập.

~~~text
Spring service
   |
   v
Renderer returns plain + HTML
   |
   v
MimeMessageHelper
   |
   v
Local SMTP test server
   |
   v
Captured MimeMessage
   |
   +--> Verify multipart/alternative
   +--> Verify text/plain
   +--> Verify text/html
   '--> Verify subject/recipient/attachment
~~~

### Ví dụ test integration với GreenMail

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class AlternativeSmtpIntegrationTest {

    private GreenMail greenMail;

    @BeforeEach
    void start() {
        greenMail = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );
        greenMail.start();
    }

    @AfterEach
    void stop() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void smtpDeliveryRetainsBothAlternatives()
            throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(greenMail.getSmtp().getPort());

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("sender@example.test");
        helper.setTo("recipient@example.test");
        helper.setSubject("Thư có fallback");
        helper.setText(
                "Đây là nội dung plain.",
                "<p>Đây là nội dung <b>HTML</b>.</p>"
        );

        sender.send(mime);

        assertTrue(greenMail.waitForIncomingEmail(5000, 1));
        MimeMessage received =
                greenMail.getReceivedMessages()[0];

        assertTrue(
                AlternativeInspector.hasCompleteAlternative(received)
        );
    }
}
~~~

Fixture chạy trên loopback và không gửi tới recipient thật. Cần chọn phiên bản GreenMail hỗ trợ **Jakarta Mail** phù hợp với Spring Boot/Jakarta Mail dependency graph; không kết luận code áp dụng nguyên vẹn cho bản Javax Mail cũ mà không đổi imports.

### Test gửi qua fixture không tương đương test Inbox thật

GreenMail có thể xác nhận MIME được SMTP tiếp nhận. Nó không kiểm chứng rendering trên Gmail/Outlook hoặc deliverability thực tế. Nếu sản phẩm có mail clients chính, có thể kiểm tra hiển thị bằng mailbox thử nghiệm được quản lý, không dùng dữ liệu khách hàng.

### Test khi có attachments và CID

Thêm scenarios:

- HTML + plain + PDF attachment.
- HTML + plain + CID logo.
- HTML + plain + CID + PDF.
- Plain body chứa URL khi HTML có CTA button.
- Charset tiếng Việt và ký tự Unicode.

MIME inspector cần tìm alternatives đúng trong tree lồng nhau; không ép root luôn là multipart/alternative.

## 26. Content preview và cách nhận ra plain bị bỏ quên

Một nhóm chỉ xem preview HTML thường không nhận ra không có text/plain, vì màn hình review cũng ưu tiên HTML. Cần có **hai chế độ xem**:

~~~text
Template preview
  |
  +-- HTML view
  |    + layout, fonts, links, images
  |
  '-- Plain-text view
       + heading and paragraphs
       + full URLs
       + required business facts
       + unsubscribe/contact text
~~~

### Những điều cần kiểm tra khi preview text

| Nhóm | Kiểm tra |
| --- | --- |
| **Nội dung** | Tiêu đề, mã đơn, tiền, thời hạn giống HTML |
| **Links** | URL chính xác, không mất đích của nút |
| **Chữ Việt** | Dấu, ký tự Unicode, xuống dòng |
| **Bảng** | Các trường vẫn đọc được khi xuống dòng |
| **Hình ảnh** | Nội dung quan trọng có text thay thế |
| **Footer** | Thông tin liên hệ và chính sách liên quan |
| **Dữ liệu rìa** | Tên dài, nhiều items, field optional vắng |
| **Biến** | Không còn placeholder chưa render |
| **Security** | Không có token/PII của người dùng thật trong preview |

### Preview HTML-only có thể tạo cảm giác an toàn giả

Nếu editor chỉ render HTML trong trình duyệt thì sẽ thấy nút, logo và bảng. Nhưng khi MIME được tạo bằng **setText(html, true)**, email vẫn thiếu plain part. **UI preview không thay thế MIME tree test**.

### Template registry phải quản lý cả hai

Một revision của email giao dịch có thể chứa:

~~~yaml
templateKey: ORDER_CONFIRMED
revision: 18
locale: vi-VN
content:
  subject: order-confirmed.subject.txt
  plain: order-confirmed.txt
  html: order-confirmed.html
~~~

Manifest là cấu trúc do ứng dụng định nghĩa. Không nên cho phép publish revision với **html** nhưng thiếu **plain** nếu delivery policy của template yêu cầu alternatives.

## 27. Fail fast khi thiếu plain text

Không chờ tới SMTP provider hoặc người nhận phát hiện thiếu plain. Nên kiểm tra trước khi compose:

~~~java
public final class MailContentValidator {

    public void validate(MailContent content) {
        if (content == null) {
            throw new IllegalArgumentException(
                    "Mail content is missing"
            );
        }

        if (content.subject() == null
                || content.subject().isBlank()) {
            throw new IllegalArgumentException(
                    "Subject is missing"
            );
        }

        if (content.plain() == null
                || content.plain().isBlank()) {
            throw new IllegalArgumentException(
                    "Plain text alternative is required"
            );
        }

        if (content.html() == null
                || content.html().isBlank()) {
            throw new IllegalArgumentException(
                    "HTML body is missing"
            );
        }

        if (content.subject().contains("\r")
                || content.subject().contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject contains line break"
            );
        }
    }
}
~~~

Đây là một policy **cho các templates bắt buộc có plain+HTML**. Không áp dụng mù cho plain-only notifications: nếu template chỉ gửi text/plain có chủ đích, thiếu HTML không phải lỗi.

### Không được sửa lỗi bằng fallback rỗng

Sai:

~~~java
String plain = renderedPlain == null
        ? ""
        : renderedPlain;
helper.setText(plain, renderedHtml);
~~~

Code chỉ che lỗi thiếu template. Một part rỗng không mang thông tin cho client text-only.

### Không phải mọi render error đều retryable

Nếu plain template không tồn tại hoặc model không phù hợp, retry SMTP lặp lại không giải quyết. Nên phân loại **TEMPLATE_INVALID**, **PLAIN_TEMPLATE_MISSING**, **RENDER_MODEL_MISSING** và báo team chịu trách nhiệm. Retry chỉ hợp lý khi dependency render tạm thời không truy cập được và có chiến lược backoff.

### Template validation không đủ nếu không có runtime validation

Một template có file plain nhưng runtime variables làm output trống (ví dụ tất cả nội dung nằm trong conditional không được kích hoạt). Runtime cần kiểm tra **rendered output**, không chỉ sự tồn tại của template source.

## 28. Quản lý phiên bản plain và HTML cùng nhau

Một lỗi tinh vi xuất hiện khi chỉ cập nhật HTML:

~~~text
Template revision 18:
  plain -> "Mã giảm giá còn hạn tới 31/12"
  HTML  -> "Mã giảm giá còn hạn tới 30/11"
~~~

Hai parts có cấu trúc đúng nhưng thông tin không nhất quán. Vì vậy phiên bản nội dung phải coi **subject + plain + HTML + assets** là một bộ đã được phê duyệt.

### Sửa HTML phải xem tác động tới plain

Những thay đổi cần đồng bộ:

- URL đích của CTA.
- Thời hạn của mã/link.
- Điều khoản pháp lý, privacy hoặc footer.
- Mức giá, discount, thuế/fee.
- Hướng dẫn xác thực.
- Thông tin liên hệ và đường dẫn hỗ trợ.

Không phải thay đổi CSS nào cũng cần đổi plain body. Nhưng khi **thông tin** thay đổi, cả hai nên được review dưới cùng revision.

### Pin revision trong notification outbox

~~~text
notificationId = N-108
templateRevision = ORDER_CONFIRMED / vi-VN / rev18
modelSnapshot = {...}
retry 1 -> plain18 + html18
retry 2 -> plain18 + html18
~~~

Nếu retry tự chọn HTML rev19 và plain rev18, cùng một notification có nội dung lệch. Resolver nên chọn revision một lần, renderer lấy đầy đủ parts của revision đó.

### Nếu plain bị thiếu trong revision đã published

Thay vì sửa đè rev18, tạo rev19 bổ sung plain đúng nghĩa và đưa qua validation/approval. Những notifications chưa attempt có thể được migrate theo chính sách có audit; những notifications đã accepted không được âm thầm ghi lại lịch sử.

## 29. Liên hệ với transactional outbox và retry

Sự cố thiếu plain có thể được phát hiện trước hoặc sau khi nộp SMTP:

~~~text
Business transaction
    |
    v
Outbox notification PENDING
    |
    v
Select pinned template revision
    |
    v
Render plain + HTML
    |
    v
Validate both parts
    |
    +-- Invalid -> TEMPLATE_FAILED / NEEDS_REVIEW
    |
    '-- Valid -> Compose MIME
                       |
                       v
                  SMTP submit
                       |
             +---------+---------+
             |         |         |
          ACCEPTED  PROVEN_FAIL  UNKNOWN
             |         |         |
             v         v         v
           Record    RETRY    Reconcile
~~~

### Nếu phát hiện trước SMTP

Không gửi message HTML-only theo kiểu best effort nếu policy yêu cầu plain alternative. Có thể đưa job vào trạng thái lỗi template và báo nội dung chưa sẵn sàng; không đổi notification key khi retry sau khi template được sửa.

### Nếu phát hiện sau khi provider đã accepted

Thư có thể đã được gửi cho người nhận dưới dạng HTML-only. Không được tự động gửi lại toàn bộ notification chỉ vì “thiếu plain”, vì sẽ tạo duplicate email. Nếu lỗi gây hậu quả nghiệp vụ, cần **correction notice** riêng theo policy và audit, không phải retry âm thầm.

### Nếu SMTP outcome là UNKNOWN

Một timeout sau khi truyền DATA không chứng minh server chưa nhận message. Không kết hợp “sửa plain” với việc retry mù, vì người nhận có thể nhận cả phiên bản HTML-only ban đầu và bản đã sửa. Cần reconciliation hoặc quyết định nghiệp vụ có kiểm soát.

### Outbox không tự tạo plain

Transactional outbox giúp ý định gửi bền vững, không thay thế renderer và MIME composition quality gate. Một hệ thống có outbox rất tốt vẫn có thể gửi hàng nghìn HTML-only emails nếu composer sai overload.

## 30. Những lỗi thường gặp khi sửa HTML-only

### Lỗi 1 — Đổi setText(html, true) thành setText(html)

Điều này biến toàn bộ HTML markup thành **text/plain**, nhiều clients hiển thị nguyên thẻ HTML. Không phải giải pháp.

~~~java
// Không phải sửa lỗi đúng.
helper.setText("<p>Hello</p>");
~~~

**Đúng:** tạo plain có nghĩa rồi gọi **setText(plain, html)**.

### Lỗi 2 — Gửi hai emails riêng

**Sai:** sender.send(messagePlain); sender.send(messageHtml). Hai thư có thể được nhận riêng, làm sai logic notification/dedup.

**Đúng:** một message với multipart/alternative.

### Lỗi 3 — Gọi setText hai lần

**Sai:** gọi **setText(plain)** rồi **setText(html, true)** và cho rằng hai calls được cộng vào MIME.

**Đúng:** dùng overload hai String.

### Lỗi 4 — Đảo vị trí plain và HTML

**Sai:** setText(html, plain).

**Đúng:** setText(plain, html).

### Lỗi 5 — Tạo multipart nhưng thiếu text/plain

**Sai:** khởi tạo helper multipart=true, sau đó chỉ setText(html, true).

**Đúng:** multipart mode là điều kiện cấu trúc, cần thêm đúng cả plain và HTML.

### Lỗi 6 — Cho rằng attachment là plain alternative

**Sai:** HTML + PDF, nhưng không có text/plain.

**Đúng:** có alternative body thích hợp; attachment nằm ở quan hệ mixed riêng.

### Lỗi 7 — Strip HTML bằng regex

**Sai:** replaceAll("<[^>]+>", "") có thể mất URL và dính nội dung.

**Đúng:** plain template từ cùng model hoặc parser có kiểm thử ngữ nghĩa.

### Lỗi 8 — Plain chứa “Xem phiên bản HTML”

**Sai:** người dùng text-only không có hành động tương ứng.

**Đúng:** plain bao gồm dữ liệu và URLs quan trọng.

### Lỗi 9 — Link trong HTML khác plain

**Sai:** nút HTML trỏ URL A, plain trỏ URL B.

**Đúng:** một trusted URL trong model, dùng chung hai renderers.

### Lỗi 10 — Chỉ HTML có OTP

**Sai:** plain trống hoặc thiếu mã.

**Đúng:** plain chứa OTP/hướng dẫn phù hợp, cùng mã với HTML.

### Lỗi 11 — Plain không có unsubscribe

**Sai:** marketing HTML có nút hủy đăng ký, plain không có cách thực hiện.

**Đúng:** cả hai thể hiện chính sách và đường dẫn phù hợp.

### Lỗi 12 — Không kiểm tra MIME tree

**Sai:** unit test chỉ assert helper.setText() được gọi.

**Đúng:** parse MimeMessage thực, xác minh multipart/alternative chứa cả hai parts.

### Lỗi 13 — Chỉ kiểm tra root Content-Type

**Sai:** yêu cầu root = multipart/alternative dù message có attachments/CID.

**Đúng:** duyệt cấu trúc lồng nhau, xác minh alternatives.

### Lỗi 14 — Assert raw MIME boundary cứng

**Sai:** test so khớp boundary="XYZ" trong output.

**Đúng:** dùng Jakarta Mail parser và assertions trên body parts.

### Lỗi 15 — Coi SPF/DKIM là thay thế text/plain

**Sai:** email ký DKIM thành công nên plain không cần thiết.

**Đúng:** authentication và content alternatives giải quyết các bài toán khác nhau.

### Lỗi 16 — Coi text/plain là bảo đảm Inbox

**Sai:** thêm plain sẽ luôn tránh spam folder.

**Đúng:** plain cải thiện khả năng tương thích; deliverability cần nhiều yếu tố khác.

### Lỗi 17 — Log toàn bộ plain/HTML để debug

**Sai:** logs chứa OTP, token hoặc dữ liệu đơn hàng.

**Đúng:** log content status/size/hash (khi phù hợp), notification ID opaque và lỗi đã redact.

### Lỗi 18 — Bỏ qua plain trong template approval

**Sai:** reviewer chỉ duyệt HTML screenshot.

**Đúng:** preview và sign-off cho cả subject/plain/HTML và actionable links.

### Lỗi 19 — Plain/HTML khác ngôn ngữ

**Sai:** bản plain tiếng Anh, HTML tiếng Việt ngoài policy.

**Đúng:** locale/translation version thống nhất và được kiểm tra.

### Lỗi 20 — Tạo plain từ một model khác

**Sai:** HTML render order total hiện tại, plain render snapshot cũ.

**Đúng:** render cả hai từ cùng verified business snapshot.

## 31. Phân biệt lỗi nội dung và lỗi transport

Một vấn đề dễ khiến team mất thời gian là chẩn đoán sai: **email không thể đọc được ở client text-only** không có nghĩa **SMTP bị lỗi**.

| Triệu chứng | Lớp cần kiểm tra |
| --- | --- |
| Người nhận thấy HTML raw | MIME type/overload setText sai |
| Plain text không có CTA URL | Plain template/converter sai |
| HTML có tiền khác plain | Template model/revision mismatch |
| SMTP auth failed | Sender credentials/provider, không phải plain |
| SMTP read timeout | Transport outcome/reconciliation |
| Mail accepted nhưng bị bounce | Downstream delivery/recipient |
| Client HTML blocked, thư trống | Thiếu plain alternative hoặc client behavior |
| PDF attachment không hiển thị | MIME mixed/attachment issue |
| CID image không load | MIME related/Content-ID/resource issue |
| Chữ Việt lỗi dấu | Charset/encoding/template source |
| Không tìm thấy text/plain ở root | Có thể có nested MIME; inspect tree |

### Sửa đúng ranh giới

Nếu lỗi là composer gọi sai **setText**, sửa composer và thêm MIME regression test. Nếu lỗi là plain template thiếu link, sửa template/render và thêm content assertion. Nếu lỗi là SMTP reject, điều tra transport; thêm plain không chắc giải quyết SMTP failure.

### Không gọi gửi lại chỉ để “xem thử”

Để điều tra, có thể tái render bằng synthetic model và gửi tới **test fixture** hoặc mailbox đã được cấp phép. Không resend email giao dịch production tới khách hàng mà không có nghiệp vụ rõ ràng.

## 32. Checklist kiểm thử trước khi phát hành template

### MIME và composer

- Với email có HTML, helper sử dụng **setText(plain, html)**.
- Helper được khởi tạo trong multipart mode phù hợp.
- MIME tree có **multipart/alternative** với hai parts đúng loại.
- Plain không blank, không chỉ là placeholder.
- HTML được render hoàn chỉnh, không chứa biểu thức template còn sót.
- Attachments/CID không phá cấu trúc alternatives.
- Text/plain và text/html đều có charset phù hợp tiếng Việt.
- Không có hai SMTP submissions cho một notification chỉ vì muốn “fallback”.

### Nội dung nghiệp vụ

- Subject, plain, HTML cùng dùng template revision/model snapshot.
- Mã đơn, số tiền, đơn vị tiền, thời hạn và trạng thái thống nhất.
- Link CTA của plain và HTML dùng cùng trusted URL.
- Hướng dẫn liên hệ/hủy đăng ký/cảnh báo có ở bản cần thiết.
- Không để thông tin quan trọng chỉ trong ảnh hoặc nút HTML.
- Plain có headings/paragraphs/bullets dễ đọc.
- Locale của plain và HTML phù hợp người nhận.
- Optional/default variables không làm mất nội dung.

### An toàn

- From/To/Reply-To/Subject được validate.
- Link token có TTL, không log raw token.
- Không render user input thành HTML/template source chưa tin cậy.
- HTML escaping theo context và URL validation.
- Không chèn CSS/markup gây tracking ngoài policy.
- Test fixtures dùng dữ liệu giả, không copy dữ liệu khách hàng thật.

### Chất lượng gửi

- Chạy unit test MIME tree và render-level checks.
- Có integration test SMTP fixture.
- Preview ở chế độ HTML và plain.
- Kiểm tra client thực tế nếu sản phẩm có compatibility requirement.
- Có quan sát render errors và content policy violations.
- Không tự resend production khi phát hiện lỗi sau accepted.

Checklist tập trung vào **lỗi thiếu plain text thay thế**; nó không thay thế mọi kiểm thử bảo mật, consent, SMTP hay deliverability của hệ thống.

## 33. Tình huống luyện tập

### Tình huống A — HTML hiển thị đẹp nhưng text-only trống

Ứng dụng gọi:

~~~java
helper.setText(html, true);
~~~

**Hỏi:** xử lý thế nào?

**Đáp:** tạo một bản plain đầy đủ từ cùng model và dùng **helper.setText(plain, html)** với multipart mode thích hợp. Kiểm tra MIME tree sau compose, không chỉ preview HTML.

### Tình huống B — Hai lần gọi setText

Developer:

~~~java
helper.setText(plain);
helper.setText(html, true);
~~~

**Hỏi:** có chắc tạo hai alternatives?

**Đáp:** không. Đây không phải API hợp đồng tạo alternatives; dùng overload hai String.

### Tình huống C — Plain chỉ chứa “Click here”

HTML có nút tới URL quan trọng, plain chỉ ghi “Nhấn vào đây”.

**Hỏi:** đã đạt fallback chưa?

**Đáp:** chưa. Text-only client không biết URL; phải ghi đầy đủ URL hoặc cách thực hiện hành động tương đương.

### Tình huống D — Plain và HTML có hai OTP

Hai renderer tự gọi generateOtp().

**Hỏi:** sửa gì ngoài MIME?

**Đáp:** tạo một OTP ở service nghiệp vụ, dùng chung model, rồi render hai parts. Không tạo mã mới trong template.

### Tình huống E — Root là multipart/mixed

Email có plain+HTML+PDF; test chỉ chấp nhận root multipart/alternative.

**Hỏi:** test có đúng không?

**Đáp:** không. Root có thể mixed/related; cần tìm nested alternative và kiểm tra hai body parts.

### Tình huống F — HTML bị chặn ảnh

HTML thông báo trạng thái chỉ bằng một hình banner, plain không có trạng thái.

**Hỏi:** plain giúp gì?

**Đáp:** plain cần diễn đạt trạng thái bằng văn bản. Đồng thời HTML cũng nên có alt text/semantic content; không dùng plain như lý do bỏ qua accessibility.

### Tình huống G — Email HTML-only được SMTP chấp nhận

Server trả 250 OK, QA báo text-only content thiếu.

**Hỏi:** đây là lỗi SMTP hay nội dung?

**Đáp:** lỗi content/MIME composition. SMTP accepted không xác nhận chất lượng các MIME alternatives.

### Tình huống H — HTML link được thay sau retry

Attempt đầu dùng URL X, lần retry plain lấy URL Y vì service tạo token lại.

**Hỏi:** rủi ro?

**Đáp:** cùng notification không nhất quán, thậm chí hai links có TTL/quyền khác nhau. Cần pin revision/model/link policy và phân loại outcome trước retry.

### Tình huống I — Subject tiếng Việt đúng nhưng body lỗi dấu

Helper dùng UTF-8 ở subject nhưng HTML/plain sources bị đọc bằng charset khác.

**Hỏi:** chỉ đổi Content-Transfer-Encoding đã đủ?

**Đáp:** không. Phải kiểm soát charset ở template files, renderer và MIME parts; transfer encoding chỉ là cách truyền bytes, không sửa văn bản đã decode sai.

### Tình huống J — Thư có PDF hóa đơn

HTML body nói “Hóa đơn trong tệp đính kèm”, plain không có gì.

**Hỏi:** PDF đã thay cho plain chưa?

**Đáp:** không. Plain nên thông báo loại thư, mã đơn, hướng dẫn mở attachment và liên hệ nếu có vấn đề. PDF là một mixed attachment riêng.

### Tình huống K — Footer unsubscribe chỉ nằm trong HTML

Email marketing thiếu URL hủy đăng ký ở plain.

**Hỏi:** cần sửa gì?

**Đáp:** đưa hướng dẫn/link phù hợp vào plain, giữ policy consent/suppression đúng trên server và kiểm tra những headers unsubscribe riêng nếu áp dụng.

### Tình huống L — Plain được tạo bằng regex

HTML có thẻ a chứa URL trong href; converter trả “Theo dõi đơn hàng” không có link.

**Hỏi:** thay regex bằng parser có tự bảo đảm đúng?

**Đáp:** parser có thể giúp xử lý cấu trúc, nhưng cần quy tắc xuất href và test content. Với CTA quan trọng, plain template từ cùng model thường tốt hơn.

### Tình huống M — Plain được sinh từ HTML version cũ

HTML rev19 ghi “7 ngày”, plain rev18 ghi “14 ngày”.

**Hỏi:** đây là lỗi MIME không?

**Đáp:** MIME alternatives có thể đúng về cấu trúc nhưng sai ngữ nghĩa. Cần pin và duyệt subject/plain/HTML cùng revision, test business facts.

### Tình huống N — Người dùng chỉ thích text-only

Sản phẩm vẫn gửi một HTML-only email.

**Hỏi:** có thể dựa vào client tự convert không?

**Đáp:** có client làm được, nhưng không bảo đảm conversion giữ link/table. Chủ động cung cấp plain alternative sẽ đáng tin hơn.

### Tình huống O — Test kiểm tra multipart=true

Một unit test assert root có MIME multipart nhưng không xem parts.

**Hỏi:** phát hiện HTML-only được không?

**Đáp:** không. Multipart có thể do attachment hoặc related resources. Test phải kiểm tra alternatives và nội dung.

### Tình huống P — Plain text rỗng

Developer:

~~~java
helper.setText("", html);
~~~

**Hỏi:** có coi như đã sửa lỗi không?

**Đáp:** không. Một part rỗng không phải bản thay thế hữu ích. Runtime validator phải reject nếu policy yêu cầu plain.

### Tình huống Q — Có HTML nhưng Plain chứa raw markup

Plain là string HTML y hệt, truyền vào đối số plain.

**Hỏi:** có gì sai?

**Đáp:** MIME type text/plain khiến các thẻ hiển thị như văn bản, không phải một representation text được biên tập. Cần tạo text không chứa markup không cần thiết.

### Tình huống R — Email đã accepted với lỗi plain

Hàng nghìn email đã được nộp SMTP trước khi nhóm nhận ra thiếu text/plain.

**Hỏi:** có nên tự gửi lại tất cả?

**Đáp:** không. Việc gửi lại có thể gây trùng và làm phiền người nhận. Cần đánh giá tác động, phân loại đã accepted/unknown, quyết định có cần một correction notice riêng hay chỉ sửa cho notifications mới.

### Tình huống S — Plain và HTML khác địa chỉ liên hệ

Plain ghi support-old@example.test, HTML ghi support@example.test.

**Hỏi:** cần kiểm tra gì?

**Đáp:** dùng cùng contact configuration/model và template revision, test các fields mang ý nghĩa nghiệp vụ, không chỉ kiểm tra part tồn tại.

### Tình huống T — HTML-only bị nghi là nguyên nhân spam

Nhóm nhận deliverability giảm, phát hiện thiếu plain.

**Hỏi:** sửa plain có bảo đảm phục hồi Inbox placement?

**Đáp:** không. Thêm plain là cải thiện chất lượng MIME, nhưng vẫn cần điều tra authentication, reputation, bounce/complaint, consent, content và provider policy.

## 34. Runbook khắc phục lỗi HTML-only trên production

### Bước 1 — Xác định phạm vi

Thu thập:

~~~text
templateKey:
templateRevision:
mailPurpose:
affectedLocale:
affectedTenant:
firstAffectedAt:
numberCreated:
numberSubmitted:
numberPending:
numberUnknown:
~~~

Không in plain/HTML đã có PII hoặc link token vào logs chỉ để đếm.

### Bước 2 — Xác định lỗi tại đâu

- Renderer không tạo plain text?
- Renderer trả plain rỗng?
- Composer dùng sai overload?
- Composer chỉ gọi setText(html,true)?
- MIME tree bị thay đổi khi thêm attachments/CID?
- Template version plain không đồng bộ HTML?
- Adapter gửi SMTP render lại nội dung với template khác?

Một MIME sample **synthetic/test** giúp xác định phần nào bị thiếu mà không cần resend cho khách hàng thật.

### Bước 3 — Sửa ở đúng lớp

~~~text
Plain template missing
  -> Create reviewed plain template

Renderer output empty
  -> Fix variable/conditional/schema

Wrong helper overload
  -> Use setText(plain, html)

Nested MIME broken
  -> Adjust multipart mode and addInline/addAttachment order

Plain/HTML facts mismatch
  -> Shared model snapshot / revision validation
~~~

### Bước 4 — Kiểm thử trước release

Chạy các test:

- MIME tree unit test, cả positive và negative.
- Render-level content assertions với mã, link, số tiền.
- MIME integration test với SMTP fixture.
- Preview plain/HTML bằng synthetic data.
- Các trường hợp mail có attachment/CID/multiple locales.

Đây là gợi ý quy trình cho hệ thống production. Trong phạm vi soạn bài STEP 4 này chỉ viết tài liệu, **không chạy content QA hay Gradle**.

### Bước 5 — Xử lý notifications đang chờ

Nếu hệ thống có template registry/outbox:

- Những notifications **chưa có SMTP attempt** có thể được sửa/migrate theo content policy.
- Những notifications **IN_FLIGHT/UNKNOWN** không được chuyển content rồi retry mù.
- Những notifications **ACCEPTED** đã nộp provider; không thay lịch sử để giả vờ đã có plain.
- Những notifications bị **RENDER_FAILED trước submission** có thể retry sau khi template được sửa nếu policy cho phép.

### Bước 6 — Theo dõi sau release

- Tỷ lệ messages có cả plain+HTML theo composer tests/observability.
- Render failures và missing plain errors.
- Pending jobs không tăng vì template invalid.
- Tỷ lệ provider accepted/bounced nếu có sự liên quan.
- Feedback text-only clients và các trường hợp content mismatch.

### Bước 7 — Ngăn tái diễn

Thêm một **quality gate** tại template publish/renderer: nếu email purpose yêu cầu HTML+plain thì không thể publish hoặc submit khi plain missing. Guard này hiệu quả hơn lời nhắc thủ công chỉ tồn tại trong checklist.

## 35. Quan sát bằng metrics và logs

Một hệ thống production có thể định nghĩa metrics riêng cho chất lượng render:

| Metric logic | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **mail_content_render_total** | Counter | Số lần render theo result |
| **mail_content_missing_plain_total** | Counter | Plain missing/blank bị phát hiện |
| **mail_content_alternative_validation_total** | Counter | Kết quả validate hai parts |
| **mail_content_mime_compose_total** | Counter | MIME composer success/failure |
| **mail_content_render_seconds** | Timer | Thời gian render |
| **mail_content_template_schema_error_total** | Counter | Template/model mismatch |
| **mail_content_cta_mismatch_total** | Counter | CTA URL mismatch được test/policy phát hiện |
| **mail_content_pending_due_template** | Gauge | Pending notifications bị lỗi template |

Đây là **metrics do ứng dụng thiết kế**, không phải metrics mặc định của JavaMailSender. Với Prometheus, Counter có thể được export với hậu tố **_total**; cần kiểm tra tên thực tế tại registry.

### Tags an toàn

~~~text
purpose=security|transactional|marketing
result=success|missing_plain|template_invalid
renderer=thymeleaf|custom
locale=vi-VN|en-US|other
~~~

Không đặt recipient email, OTP, token, order ID hay raw Subject/HTML vào metric labels. Với nhiều template revisions, nếu cần phân tích từng revision, có thể dùng logs/audit có kiểm soát thay vì tạo label high-cardinality.

### Structured log ví dụ

~~~text
event=mail_content_validation_finished
notification_id=opaque-N-108
template_key=ORDER_CONFIRMED
template_revision=18
has_plain=true
has_html=true
plain_chars=420
html_chars=1038
validation_result=SUCCESS
~~~

Độ dài parts không thể thay cho việc kiểm tra content semantics; một plain text dài vẫn có thể thiếu URL. Nhưng metadata giúp phát hiện lỗi rỗng hàng loạt mà không cần lưu nội dung nhạy cảm.

### Không theo dõi nội dung bằng raw logs

Nếu team cần tra cứu email thực tế do khách hàng báo lỗi, dùng một quy trình riêng được cấp quyền, có audit/retention, redact PII/token. Không bật SMTP debug protocol hay dump raw MIME trên production không kiểm soát.

## 36. Chuyển hệ thống HTML-only cũ sang có plain text

Một hệ thống đã chạy lâu có thể có hàng chục templates chỉ có HTML. Việc sửa một dòng setText ở composer **chưa đủ** nếu renderer không có plain content để truyền.

### Các bước migration

~~~text
Inventory existing templates
       |
       v
Classify: security / transactional / marketing
       |
       v
Identify critical facts and CTA links
       |
       v
Create plain templates from canonical models
       |
       v
Version and review subject/plain/HTML together
       |
       v
Update composer to setText(plain, html)
       |
       v
Add MIME + semantic regression tests
       |
       v
Canary deployment / verify SMTP fixture
       |
       v
Monitor render failures and user feedback
~~~

### Bắt đầu từ templates quan trọng

Ưu tiên:

1. Account verification/password reset/OTP.
2. Biên nhận, hóa đơn, xác nhận đặt hàng.
3. Thông báo thay đổi bảo mật hoặc deadline.
4. Thư hỗ trợ có CTA hoặc attachment quan trọng.
5. Marketing/newsletter.

Thứ tự thực tế còn phụ thuộc số lượng người nhận, rủi ro nghiệp vụ và yêu cầu compliance; điểm chung là phải giữ thông tin quan trọng khi client không render HTML.

### Nếu không thể viết ngay hàng chục plain templates?

Có thể chọn một **HTML-to-text converter dùng HTML parser** và áp rule để giữ links, lists, tables cho giai đoạn chuyển tiếp. Nhưng:

- Không chấp nhận converter output trống.
- Kiểm thử với templates thực, nhất là CTA.
- Không coi converter là đảm bảo ngữ nghĩa.
- Lên kế hoạch dùng plain templates được review cho các emails quan trọng.

Không chuyển đổi bằng regex đơn giản rồi tuyên bố đã giải quyết.

### Phân loại trạng thái email cũ

Hệ thống có thể đã gửi HTML-only tới người nhận. Migration không thể sửa MIME đã được gửi. Không tự resend dữ liệu lịch sử chỉ vì muốn có plain. Chỉ gửi correction notice nếu có một vấn đề thực sự ảnh hưởng người dùng và quyết định nghiệp vụ cho phép.

## 37. Policy theo loại thông báo: không cứng nhắc áp một luật cho mọi mail

Nhiều loại email có yêu cầu khác nhau:

| Loại | Nội dung chính | Policy phù hợp |
| --- | --- | --- |
| **Plain-only system alert** | Văn bản ngắn, không cần styling | text/plain đơn, không bắt buộc HTML |
| **HTML transactional** | Mã đơn, link, giá, trạng thái | Bắt buộc text/plain + text/html |
| **Security/OTP with HTML** | Mã/token/TTL và cảnh báo | Bắt buộc fallback đầy đủ, kiểm tra consistency |
| **Marketing HTML** | Nội dung quảng bá, CTA, unsubscribe | Có plain đầy đủ, review footer/consent |
| **HTML + attachment** | Giải thích và tệp | Cặp alternatives cho body; attachment riêng |
| **HTML + CID images** | Nội dung nhiều hình ảnh | Cặp alternatives + related resources |
| **Raw MIME forward** | Chuyển tiếp một message đã có | Chính sách xử lý/giữ MIME riêng, không sửa mù |

### Thiết kế content policy rõ ràng

~~~java
public enum MailBodyPolicy {
    PLAIN_ONLY,
    HTML_WITH_PLAIN_ALTERNATIVE
}

public record MailTemplatePolicy(
        String templateKey,
        MailBodyPolicy bodyPolicy
) {
}
~~~

Renderer/composer dựa vào policy:

~~~text
PLAIN_ONLY
  -> setText(plain)

HTML_WITH_PLAIN_ALTERNATIVE
  -> validate plain nonblank
  -> validate html nonblank
  -> setText(plain, html)
~~~

Điều này tránh một lỗi ngược: sửa lỗi HTML-only bằng cách bắt mọi email đơn giản đều phải tạo HTML, gây công việc không cần thiết.

### Giữ policy ở ranh giới chuẩn hóa

Nếu mỗi developer tự quyết định gọi setText overload nào ngay trong business service, lỗi dễ quay lại. Có thể tạo **MailComposer** chung, yêu cầu đối tượng **RenderedMailContent** và enforce policy tại một chỗ.

### Reject khác fallback

Nếu policy yêu cầu cả hai parts mà plain missing, không nên tự động đổi sang HTML-only để “đảm bảo gửi”. Một lựa chọn rõ hơn là **fail validation** trước SMTP, đưa notification vào trạng thái sửa được và gửi alert. Chỉ dùng fallback policy khác nếu được định nghĩa và review riêng.

## 38. Ví dụ composer áp policy và validate trước khi gửi

Ví dụ dưới đây gom quyết định MIME body trong một class thay vì để nhiều service tự gọi overload:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PolicyAwareMailComposer {

    private final JavaMailSender sender;

    public PolicyAwareMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(
            String verifiedFrom,
            String recipient,
            MailContent content,
            MailBodyPolicy bodyPolicy
    ) throws MessagingException {
        requireText(verifiedFrom, "from");
        requireText(recipient, "recipient");
        requireText(content.subject(), "subject");
        requireText(content.plain(), "plain text");

        if (content.subject().contains("\r")
                || content.subject().contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject must be a single line"
            );
        }

        MimeMessage mime = sender.createMimeMessage();

        if (bodyPolicy == MailBodyPolicy.PLAIN_ONLY) {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, false, "UTF-8"
            );
            setEnvelope(helper, verifiedFrom, recipient,
                    content.subject());
            helper.setText(content.plain());
        } else if (bodyPolicy
                == MailBodyPolicy.HTML_WITH_PLAIN_ALTERNATIVE) {
            requireText(content.html(), "HTML body");
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime, true, "UTF-8"
            );
            setEnvelope(helper, verifiedFrom, recipient,
                    content.subject());
            helper.setText(content.plain(), content.html());
        } else {
            throw new IllegalArgumentException(
                    "Unsupported mail body policy"
            );
        }

        sender.send(mime);
    }

    private static void setEnvelope(
            MimeMessageHelper helper,
            String verifiedFrom,
            String recipient,
            String subject
    ) throws MessagingException {
        helper.setFrom(verifiedFrom);
        helper.setTo(recipient);
        helper.setSubject(subject);
    }

    private static void requireText(
            String value,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing " + fieldName
            );
        }
    }
}
~~~

Đoạn ví dụ dùng **MailContent** và **MailBodyPolicy** đã định nghĩa ở các phần trước. Nó minh họa **guard chống thiếu plain**; không thay thế recipient validation, verified sender identity, URL validation, consent/suppression, outbox, SMTP timeouts hay phân loại kết quả gửi. **sender.send(...)** có thể ném MailException runtime ngoài MessagingException; worker production phải phân loại outcome và tránh retry mù khi kết quả SMTP không rõ.

### Vì sao composer nên dùng helper đúng overload?

Toàn bộ HTML-capable flow đi qua một branch:

~~~java
helper.setText(content.plain(), content.html());
~~~

Khi có một chuẩn chung, unit test MIME được đặt ở class composer thay vì viết một test riêng cho hàng trăm business services. Business service vẫn cần test nội dung/URL cụ thể.

### Thử nghiệm policy plain-only

Một email chỉ có plain:

~~~java
MailContent content = new MailContent(
        "Máy chủ đã phục hồi",
        "Dịch vụ đã hoạt động trở lại.",
        null
);

composer.send(
        "ops@example.test",
        "admin@example.test",
        content,
        MailBodyPolicy.PLAIN_ONLY
);
~~~

Đây không phải HTML-only bug vì không hề yêu cầu HTML. Validation cần phù hợp mục đích.

### Thử nghiệm policy HTML+plain

~~~java
MailContent content = new MailContent(
        "Xác nhận đơn ORD-1528",
        "Đơn ORD-1528 đã được xác nhận.\n"
                + "Xem: https://app.example.test/orders/ORD-1528",
        "<p>Đơn <b>ORD-1528</b> đã được xác nhận.</p>"
                + "<p><a href=\"https://app.example.test/orders/"
                + "ORD-1528\">Xem chi tiết</a></p>"
);

composer.send(
        "orders@example.test",
        "customer@example.test",
        content,
        MailBodyPolicy.HTML_WITH_PLAIN_ALTERNATIVE
);
~~~

Nếu plain là chuỗi rỗng, composer dừng trước SMTP submission theo policy.

## 39. Sơ đồ quyết định khi gửi HTML email

~~~text
                  Chuẩn bị email
                        |
                        v
                Có yêu cầu HTML?
                  |           |
                 Không        Có
                  |           |
                  v           v
              Plain body   Render từ cùng model
                  |           |
                  v           +---------+---------+
              Validate        |                   |
                  |           v                   v
                  v       text/plain          text/html
             setText(plain)   |                   |
                  |           +---------+---------+
                  |                     |
                  |                     v
                  |              Validate consistency
                  |                     |
                  |              +------+------+
                  |              |             |
                  |           Invalid         Valid
                  |              |             |
                  |              v             v
                  |         Reject/Review   setText(plain, html)
                  |                            |
                  +-------------+--------------+
                                |
                                v
                          Compose MimeMessage
                                |
                                v
                       Optional CID/attachments
                                |
                                v
                         Inspect MIME policy
                                |
                         +------+------+
                         |             |
                      Invalid         Valid
                         |             |
                         v             v
                     Fix/review      SMTP submit
                                       |
                                       v
                               Track provider outcome
~~~

**MIME policy inspection** có thể là quality gate trong tests và runtime validator tùy chi phí/kiến trúc. Không cần parse lại mọi message ở production nếu composer có contract chặt và test đầy đủ; nhưng phải có cách phát hiện regressions.

## 40. Tóm tắt ghi nhớ

~~~text
setText(html, true)
    -> HTML body, không tự tạo plain alternative

setText(plain, html)
    -> yêu cầu tạo text/plain + text/html alternatives

multipart/alternative
    -> nhiều cách biểu diễn cùng một nội dung

multipart/mixed
    -> các thành phần độc lập, ví dụ attachments

multipart/related
    -> tài nguyên đi kèm để render HTML (CID images)

One mail with alternatives
    != gửi hai email riêng

Plain part exists
    != plain part useful nếu nội dung rỗng

HTML-to-text regex
    != bảo đảm giữ URL và ý nghĩa nghiệp vụ

Shared model snapshot
    -> giữ mã, số tiền, OTP, thời hạn và link nhất quán

Rendered content validator
    -> chặn thiếu plain trước SMTP

MIME tree test
    -> xác nhận alternative relationship đúng

Plain text
    -> hỗ trợ một số text-only clients và downstream tools

Plain text
    != bảo đảm email vào Inbox

SMTP accepted
    != người nhận đã nhận/đọc

Content bug after SMTP accepted
    != lý do tự động resend
~~~

**Tạo HTML nhưng quên plain text thay thế** là lỗi phổ biến vì email vẫn có thể nhìn đẹp trong một số clients và SMTP vẫn chấp nhận message. Sửa lỗi không chỉ là thêm một chuỗi cho đủ hai tham số: ứng dụng phải cung cấp **bản text/plain có ý nghĩa tương đương** với **text/html**, đặc biệt với mã xác thực, số tiền, thời hạn, URL và hướng dẫn bắt buộc. Trong Spring Framework Mail, **MimeMessageHelper.setText(plainText, htmlText)** là cách trực tiếp để tạo alternatives trong một MIME message; khi có CID images hoặc attachments, các parts vẫn phải được lồng đúng quan hệ **alternative / related / mixed**. Với hệ thống production, hãy tạo cả hai từ một model/template revision đã được validate, thêm quality gates và MIME tests, preview dưới dạng text-only, và phân biệt lỗi nội dung với lỗi transport. Như vậy email có định dạng đẹp mà vẫn cung cấp một lựa chọn đọc và xử lý rõ ràng khi HTML không được hiển thị.
