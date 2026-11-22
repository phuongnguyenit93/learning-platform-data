# multipart/alternative cho plain text và HTML thay thế

## 1. multipart/alternative giải quyết vấn đề gì?

Email hiện đại thường có hai cách biểu diễn cùng một nội dung:

- **Plain text**: chữ thuần, không có thẻ HTML hay định dạng phức tạp. Người đọc vẫn thấy được nội dung trong email client chỉ hỗ trợ text, khi tắt hiển thị HTML hoặc trong một số công cụ kiểm tra thư.
- **HTML**: nội dung có tiêu đề, đoạn văn, liên kết, bố cục, màu sắc và định dạng, phù hợp với các email client hỗ trợ HTML.

Nếu chỉ gửi HTML, những client không hỗ trợ hoặc không muốn hiển thị HTML có thể đọc thư kém thuận tiện. Nếu chỉ gửi plain text, ứng dụng bỏ lỡ khả năng trình bày trực quan. Chuẩn **MIME (Multipurpose Internet Mail Extensions)** giải quyết nhu cầu này bằng kiểu nội dung **multipart/alternative**.

Một email có **multipart/alternative** chứa nhiều phần (*body parts*) là **các cách biểu diễn thay thế của cùng một thông điệp**. Trường hợp phổ biến nhất là hai phần **text/plain** và **text/html**. Email client sẽ chọn một biểu diễn phù hợp để hiển thị; người nhận không được hiểu đây là hai email riêng hoặc hai nội dung cần đọc nối tiếp.

Trong **Spring Framework Mail**, ta thường xây dựng loại email này bằng **JavaMailSender** và **MimeMessageHelper**. Cặp phương thức đặc biệt quan trọng là **MimeMessageHelper.setText(plainText, htmlText)**: nó cung cấp hai nội dung tương ứng để helper tạo phần MIME thay thế.

## 2. MIME là lớp biểu diễn nội dung, không phải giao thức vận chuyển

Cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| **SMTP** | Chuyển thông điệp từ client đến máy chủ gửi và giữa các mail server. |
| **MIME** | Mô tả cấu trúc nội dung email: loại media, encoding, nhiều phần, attachment và các quan hệ giữa chúng. |
| **text/plain** | Biểu diễn nội dung dưới dạng văn bản thuần. |
| **text/html** | Biểu diễn nội dung bằng HTML. |
| **multipart/alternative** | Gom các phiên bản *thay thế nhau* của cùng một nội dung. |
| **JavaMailSender** | Interface Spring gửi thông điệp email, bao gồm MimeMessage. |
| **MimeMessageHelper** | Tiện ích của Spring giúp dựng cấu trúc MimeMessage và các phần MIME. |

Một ứng dụng Spring tạo **MimeMessage**, còn việc email có đi qua SMTP server thành công hay không là một vấn đề vận chuyển khác. Một thư có cấu trúc MIME đúng vẫn có thể bị SMTP từ chối, gặp lỗi xác thực miền hoặc bị đưa vào Spam.

### Vì sao gọi là alternative?

Hãy tưởng tượng một thông báo xác nhận tài khoản. Nội dung có thể xuất hiện như sau:

**Bản plain text**

~~~text
Xin chào!

Tài khoản của bạn đã được tạo thành công.
Vui lòng truy cập https://example.com/account để xem thông tin.

Trân trọng,
Đội ngũ hỗ trợ
~~~

**Bản HTML**

~~~html
<!doctype html>
<html lang="vi">
  <body>
    <h2>Xin chào!</h2>
    <p>Tài khoản của bạn đã được tạo thành công.</p>
    <p>
      Vui lòng truy cập
      <a href="https://example.com/account">trang tài khoản</a>
      để xem thông tin.
    </p>
    <p>Trân trọng,<br>Đội ngũ hỗ trợ</p>
  </body>
</html>
~~~

Hai bản mang **cùng thông tin cốt lõi**; chỉ khác cách trình bày. Khi một email client hỗ trợ HTML, nó thường chọn bản HTML; khi không hỗ trợ, nó có thể chọn bản plain text.

Đây **không phải cơ chế phát hiện HTML lỗi rồi tự động sửa HTML**. Việc lựa chọn phụ thuộc vào email client, tùy chọn của người dùng và hỗ trợ MIME. Nếu HTML có lỗi hiển thị, nhiều client vẫn có thể chọn phần HTML. Vì thế cả hai bản đều cần được soạn đầy đủ và có thể sử dụng độc lập.

## 3. Cấu trúc MIME của multipart/alternative

Ví dụ một email có hai phương án nội dung, biểu diễn bằng dạng MIME thô:

~~~text
From: no-reply@example.com
To: user@example.net
Subject: Account notification
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt_001"

--alt_001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your account is ready.
Open https://example.com/account to view it.

--alt_001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <p>Your account is ready.</p>
    <p><a href="https://example.com/account">View your account</a></p>
  </body>
</html>

--alt_001--
~~~

Ví dụ dùng nội dung ASCII để minh họa **Content-Transfer-Encoding: 7bit**. Với tiếng Việt hay các ký tự Unicode khác, thư viện gửi có thể chọn một encoding truyền tải phù hợp, chẳng hạn quoted-printable hoặc base64, cùng charset UTF-8. Không nên tự đặt 7bit cho phần nội dung chứa byte UTF-8 ngoài ASCII.

### Giải thích từng phần

1. **MIME-Version: 1.0** báo thông điệp sử dụng cấu trúc MIME.
2. **Content-Type: multipart/alternative** cho biết phần body bao gồm các biểu diễn thay thế.
3. **boundary="alt_001"** định nghĩa chuỗi phân cách các phần. Trong thư thực, thư viện thường tự tạo boundary duy nhất; ví dụ chỉ dùng tên dễ đọc.
4. **--alt_001** mở đầu từng phần.
5. Mỗi phần có **Content-Type** riêng, ví dụ text/plain hoặc text/html.
6. **--alt_001--** với hai dấu gạch ở cuối đóng multipart.

Không nên tự ghép chuỗi MIME bằng thao tác nối văn bản trong production. Các thư viện Jakarta Mail và Spring xử lý boundary, encoding, header và các cấu trúc lồng nhau đáng tin cậy hơn.

### Thứ tự các phần có ý nghĩa

Theo quy ước MIME cho **multipart/alternative**, các phần được sắp xếp từ biểu diễn **ít được ưu tiên hơn đến biểu diễn được ưu tiên hơn**; khi có nhiều lựa chọn mà client hiển thị được, client thường chọn **phần cuối cùng được hỗ trợ**.

Vì vậy, cặp phổ biến có thứ tự:

~~~text
multipart/alternative
├── text/plain    (biểu diễn cơ bản)
└── text/html     (biểu diễn phong phú hơn, thường được ưu tiên)
~~~

Điều đó không bắt buộc mọi email client luôn hiển thị HTML: một số client hoặc người dùng có thể ưu tiên plain text vì khả năng truy cập, an toàn hoặc chính sách cá nhân. Điểm thiết kế quan trọng là **cả hai phần phải chứa cùng thông tin chính và giữ được hành động người đọc cần thực hiện**.

## 4. So sánh multipart/alternative với mixed và related

Ba subtype thường xuất hiện trong email có nhiều phần:

| Kiểu MIME | Quan hệ giữa các phần | Ví dụ |
|---|---|---|
| **multipart/alternative** | Các phần là **phiên bản thay thế** của cùng nội dung. | text/plain và text/html của email thông báo. |
| **multipart/mixed** | Các phần là **những thành phần cần đi cùng nhau**, thường gồm body và file đính kèm. | Nội dung email kèm report.pdf. |
| **multipart/related** | Các phần có **quan hệ tham chiếu**, thường dùng cho HTML và tài nguyên inline. | Email HTML tham chiếu hình logo bằng Content-ID (cid). |

Chọn đúng subtype sẽ giúp email client diễn giải cấu trúc thư:

- Dùng **alternative** khi người nhận cần chọn **một trong các cách thể hiện cùng một thông điệp**.
- Dùng **mixed** khi thư gồm nội dung chính **và** một hoặc nhiều attachment.
- Dùng **related** khi phần HTML cần tài nguyên liên quan, chẳng hạn ảnh được nhúng inline.

Một email phức tạp có thể **lồng nhiều subtype** chứ không phải chọn một subtype duy nhất cho toàn bộ thư.

## 5. Tạo plain text + HTML với Spring Framework Mail

Spring Mail cung cấp phương thức hỗ trợ trực tiếp:

~~~java
MimeMessageHelper.setText(String plainText, String htmlText)
~~~

Phương thức được gọi trên đối tượng helper; hai chuỗi phải biểu diễn cùng nội dung. Đây là overload khác với **setText(String text, boolean html)**, vốn chỉ xác định một phần nội dung là plain text hay HTML.

### Ví dụ hoàn chỉnh dùng JavaMailSender

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class AccountNotificationMailService {

    private final JavaMailSender mailSender;

    public AccountNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAccountReady(String recipient) throws MessagingException {
        String plainText = """
                Xin chào!

                Tài khoản của bạn đã sẵn sàng.
                Truy cập https://example.com/account để xem thông tin.

                Trân trọng,
                Đội ngũ hỗ trợ
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <h2>Xin chào!</h2>
                    <p>Tài khoản của bạn đã sẵn sàng.</p>
                    <p>
                      <a href="https://example.com/account">
                        Truy cập trang tài khoản
                      </a>
                      để xem thông tin.
                    </p>
                    <p>Trân trọng,<br>Đội ngũ hỗ trợ</p>
                  </body>
                </html>
                """;

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Tài khoản đã sẵn sàng");
        helper.setText(plainText, htmlText);

        mailSender.send(mimeMessage);
    }
}
~~~

Ví dụ sử dụng Java text block (phù hợp với Java 21) và giả định ứng dụng đã cấu hình bean **JavaMailSender** cùng máy chủ gửi email.

### Vì sao cần chú ý từng dòng?

**mailSender.createMimeMessage()**: tạo thông điệp MIME bằng cấu hình của JavaMailSender.

**new MimeMessageHelper(mimeMessage, true, "UTF-8")**: bật chế độ multipart để helper có thể xây dựng nhiều phần nội dung. Trong constructor này, **true** yêu cầu multipart; tham số encoding cho phép xử lý văn bản Unicode tiếng Việt một cách phù hợp.

**helper.setText(plainText, htmlText)**: tạo hai cách biểu diễn thay thế. Helper xây dựng cấu trúc MIME thích hợp, bao gồm một **multipart/alternative** cho hai nội dung này.

**mailSender.send(mimeMessage)**: gửi thông điệp đã chuẩn bị tới hạ tầng mail. Phản hồi thành công của lời gọi này không tự bảo đảm thư nằm trong Inbox; các bước chuyển phát sau đó là trách nhiệm của hệ thống email.

**Lưu ý về cây MIME thực tế:** Khi tạo MimeMessageHelper với **multipart=true**, Spring có thể tạo một cấu trúc multipart bao ngoài (chẳng hạn mixed/related) rồi đặt phần alternative vào bên trong. Vì vậy, không nên bắt buộc **Content-Type ở gốc** luôn phải là multipart/alternative. Điều cần quan sát là **có hai phần text/plain và text/html được nhóm theo quan hệ alternative**.

### Hai overload setText dễ bị nhầm

| Lệnh gọi | Kết quả mong đợi |
|---|---|
| **helper.setText("Xin chào")** | Một phần nội dung plain text. |
| **helper.setText("<p>Xin chào</p>", true)** | Một phần nội dung HTML; không tự tạo bản plain text đầy đủ. |
| **helper.setText(plainText, htmlText)** | Hai biểu diễn thay thế, thường nằm trong multipart/alternative. |

Nếu muốn dùng overload hai chuỗi, cần khởi tạo helper ở **chế độ multipart**. Tạo helper ở chế độ một phần rồi gọi overload này có thể thất bại do không có cấu trúc multipart để chứa alternative.

## 6. Cấu hình trong Spring Boot

Đối với ứng dụng Spring Boot, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Tùy nhà cung cấp SMTP, có thể cấu hình trong **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Đây là cấu hình minh họa, không phải địa chỉ máy chủ hay tài khoản thực. Trong ứng dụng thật, thông tin xác thực phải lấy từ biến môi trường hoặc dịch vụ quản lý bí mật; **không commit mật khẩu SMTP vào repository**.

Spring Boot hỗ trợ thiết lập bean gửi email từ cấu hình phù hợp. Cấu trúc **multipart/alternative**, tuy vậy, là thuộc tính của **nội dung MimeMessage**, được tạo khi xây dựng email, không phải một tùy chọn của SMTP host hoặc cổng mạng.

## 7. Khi nào cấu trúc MIME trở nên lồng nhau?

Giả sử ứng dụng gửi hóa đơn có nội dung plain text, HTML và một tệp PDF. Hai biểu diễn nội dung vẫn là alternative, còn PDF là attachment đi kèm:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf (attachment)
~~~

Nếu HTML tham chiếu tới ảnh logo nhúng trực tiếp trong email, quan hệ giữa HTML và ảnh có thể cần **multipart/related**. Một cấu trúc điển hình:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html (tham chiếu cid:brandLogo)
│   └── image/png (inline, Content-ID: brandLogo)
└── application/pdf (attachment)
~~~

Cấu trúc cụ thể phụ thuộc vào cách message được tạo và chính sách tương thích của thư viện. Sơ đồ thể hiện **quan hệ ý nghĩa**: plain text và HTML là alternative; ảnh inline phụ thuộc vào HTML; attachment đi kèm toàn bộ email.

### Ví dụ Spring Mail thêm file đính kèm

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.io.File;
import java.nio.charset.StandardCharsets;

public void sendInvoice(
        JavaMailSender sender,
        String recipient,
        File invoicePdf
) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Hóa đơn của bạn");
    helper.setText(
            "Xin chào! Hóa đơn PDF được đính kèm trong email này.",
            "<p>Xin chào!</p><p>Hóa đơn PDF được đính kèm trong email này.</p>"
    );

    helper.addAttachment("invoice.pdf", invoicePdf);
    sender.send(message);
}
~~~

Ví dụ giả định **invoicePdf** là tệp PDF đã tồn tại và được phép gửi. Trong code thực tế, nên giới hạn kích thước tệp, xử lý lỗi file bằng loại exception cụ thể và không đưa tệp nhạy cảm vào email nếu chưa có cơ chế bảo vệ tương ứng.

Đối với hình ảnh inline, có thể dùng **helper.addInline(contentId, resource)** sau khi chuẩn bị nội dung HTML tham chiếu **cid:contentId**. Tài nguyên inline thuộc quan hệ **related**, không phải một bản text thứ ba của alternative.

## 8. Nếu cần multipart/alternative chính xác ở mức gốc

**MimeMessageHelper** tối ưu cho việc dựng email thông dụng và có thể tạo các lớp multipart bao ngoài. Khi một bài toán đặc thù yêu cầu chính xác **Content-Type ở gốc là multipart/alternative**, Jakarta Mail cho phép tự dựng cây MIME.

Ví dụ sử dụng các kiểu Jakarta Mail:

~~~java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import org.springframework.mail.javamail.JavaMailSender;

public void sendExactAlternative(
        JavaMailSender sender,
        String recipient
) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    message.setFrom(new InternetAddress("no-reply@example.com"));
    message.setRecipient(
            Message.RecipientType.TO,
            new InternetAddress(recipient)
    );
    message.setSubject("Thông báo", "UTF-8");

    MimeBodyPart plainPart = new MimeBodyPart();
    plainPart.setText("Xin chào! Tài khoản của bạn đã sẵn sàng.", "UTF-8");

    MimeBodyPart htmlPart = new MimeBodyPart();
    htmlPart.setContent(
            "<html><body><p>Xin chào! Tài khoản của bạn đã sẵn sàng.</p></body></html>",
            "text/html; charset=UTF-8"
    );

    MimeMultipart alternatives = new MimeMultipart("alternative");
    alternatives.addBodyPart(plainPart);
    alternatives.addBodyPart(htmlPart);

    message.setContent(alternatives);
    sender.send(message);
}
~~~

Ở đây các phần được thêm theo thứ tự **plain trước, HTML sau**, và **message.setContent(alternatives)** gắn multipart/alternative trực tiếp làm nội dung chính. Ví dụ phục vụ mục đích hiểu MIME; nếu không có yêu cầu cấu trúc đặc biệt, nên ưu tiên **MimeMessageHelper** để giảm mã thủ công.

## 9. Viết hai phiên bản sao cho tương đương

Một lỗi nội dung phổ biến là HTML có đầy đủ thông tin nhưng plain text chỉ ghi “Vui lòng bật HTML để xem email”. Cách này làm mất ý nghĩa của **alternative**: người dùng chọn plain text sẽ không thể hoàn thành công việc cần thiết.

Hai phiên bản nên có:

- **Cùng thông điệp chính**: kết quả, thông báo, trạng thái hoặc nội dung giao dịch.
- **Cùng hành động quan trọng**: nếu HTML có nút xác nhận, plain text phải có URL hoặc hướng dẫn tương ứng.
- **Cùng thông tin bắt buộc**: mã đơn hàng, thời hạn, liên hệ hỗ trợ, điều kiện quan trọng nếu liên quan.
- **Khả năng đọc độc lập**: plain text có xuống dòng, khoảng trắng và cách trình bày dễ hiểu; HTML dùng cấu trúc tiêu đề, đoạn văn và liên kết hợp lý.
- **Không có thông tin gây mâu thuẫn**: giá tiền, số lượng, ngày hết hạn, token, URL không được khác nhau giữa hai bản.

Ví dụ email xác nhận:

| Nội dung cần giữ | Plain text | HTML |
|---|---|---|
| Lời chào | Dòng “Xin chào” | Thẻ p hoặc h2 |
| Mô tả | Các dòng văn bản | Các đoạn p |
| Nút xác nhận | URL đầy đủ có thể sao chép | Liên kết a với nhãn mô tả |
| Thông tin liên hệ | Địa chỉ email hoặc URL rõ ràng | Liên kết mailto hoặc trang hỗ trợ |
| Thời hạn | Câu văn rõ ràng | Câu văn có thể định dạng nhấn mạnh |

Không nên giả định nội dung plain text có thể dùng cú pháp Markdown rồi email client tự chuyển thành HTML. Các dấu sao, dấu gạch và cú pháp liên kết Markdown thường chỉ là ký tự bình thường trong phần **text/plain**.

### Xử lý dữ liệu động và an toàn nội dung

Nếu email chứa tên người dùng hoặc dữ liệu lấy từ nguồn không đáng tin cậy, **phải escape dữ liệu khi chèn vào HTML** để ngăn thẻ/thuộc tính không mong muốn làm sai cấu trúc thư. Cần mã hóa và xây dựng URL đúng cách, đặc biệt là URL có token. Khi xây dựng HTML từ template, sử dụng cơ chế escape của template engine hoặc quy tắc tương đương; không nối trực tiếp dữ liệu người dùng vào thuộc tính HTML.

Nhiều email client loại bỏ JavaScript và CSS không được hỗ trợ, vì vậy HTML email nên đơn giản, có cấu trúc dễ đọc và không phụ thuộc vào script để hiển thị nội dung quan trọng. Ảnh có thể bị chặn; cần **alt text** và không đặt thông tin thiết yếu chỉ trong ảnh.

Nếu email chứa mã xác nhận, token đặt lại mật khẩu hoặc dữ liệu cá nhân, cả hai phiên bản phải được bảo vệ tương ứng. Không ghi toàn bộ MIME body vào log production và không để URL có token xuất hiện trong báo cáo lỗi không được bảo vệ.

## 10. Charset, Content-Transfer-Encoding và tiếng Việt

Hai khái niệm thường bị lẫn:

**charset** trong Content-Type, ví dụ **charset=UTF-8**, cho biết cách diễn giải bytes thành ký tự. Đây là lý do ứng dụng cần dùng UTF-8 để hiển thị chính xác tiếng Việt có dấu.

**Content-Transfer-Encoding**, ví dụ **quoted-printable** hoặc **base64**, cho biết cách mã hóa các byte nội dung để phù hợp đường truyền email. Đây không phải cách “mã hóa bảo mật” hay giải pháp che nội dung khỏi người có quyền truy cập.

Ví dụ một phần plain text có thể có header:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Jakarta Mail thường chọn cơ chế chuyển mã thích hợp khi ghi thông điệp. Ở tầng ứng dụng, ưu tiên cung cấp đúng chuỗi Unicode, khai báo charset phù hợp và để thư viện xử lý chuyển mã MIME. Tự tạo một email raw với nội dung tiếng Việt nhưng khai báo **7bit** không phù hợp có thể khiến các hệ thống gửi/nhận hiển thị sai.

Ngoài phần body, **Subject** có tiếng Việt cũng phải được mã hóa hợp lệ theo chuẩn header email; sử dụng API của Jakarta Mail hoặc MimeMessageHelper thay vì tự ghép header raw.

## 11. Các lỗi thường gặp khi tạo alternative trong Spring

| Hiện tượng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| Email chỉ hiển thị HTML, người chọn plain text không có nội dung đúng | Chỉ gọi **setText(html, true)** | Tạo plain text và gọi overload **setText(plain, html)**. |
| HTML xuất hiện dưới dạng các ký tự thẻ | Nội dung HTML bị đặt vào text/plain | Dùng **setText(html, true)** cho một phần HTML hoặc overload hai chuỗi cho alternative. |
| Lỗi khi gọi overload hai chuỗi | Helper chưa được khởi tạo ở chế độ multipart | Tạo **MimeMessageHelper** với multipart=true hoặc mode multipart phù hợp. |
| Text tiếng Việt bị sai dấu | Charset hoặc tự xây raw MIME sai | Sử dụng UTF-8 và API MIME để encode nội dung. |
| Email có attachment nhưng client hiển thị hai phần nội dung kỳ lạ | Cây MIME không phân biệt alternative với mixed/related | Giữ plain và HTML trong alternative, attachment trong mixed và ảnh inline trong related. |
| Plain text không có link hành động | Nội dung được viết chỉ cho HTML | Thêm URL và hướng dẫn tương ứng vào plain text. |
| HTML hiển thị khác trên nhiều client | CSS/HTML không được hỗ trợ đồng nhất, ảnh bị chặn | Dùng HTML email đơn giản, có plain text đầy đủ, kiểm tra trên các client đích. |
| SMTP trả lỗi hoặc thư vào Spam | Lỗi xác thực, DNS, policy, reputation hoặc vận chuyển | Điều tra SMTP/ESP và hệ thống nhận; alternative chỉ liên quan biểu diễn nội dung. |

Một điểm dễ bỏ qua: **multipart/alternative không phải cơ chế gửi email hai lần**. Chỉ có một thông điệp MIME, bên trong có nhiều lựa chọn biểu diễn. Nếu người nhận nhận hai email riêng biệt, cần kiểm tra lời gọi gửi, hàng đợi, retry hoặc sự kiện nghiệp vụ trùng, thay vì đổ lỗi cho việc tạo cả plain và HTML.

## 12. Cách quan sát một email alternative

Trong môi trường phát triển, có thể gửi vào một SMTP test inbox hoặc mail server kiểm thử và mở phần **raw message / show original** để quan sát MIME. Một email được xây dựng bằng helper multipart có thể hiển thị cây lồng nhau; cần tìm **multipart/alternative** cùng hai nhánh **text/plain** và **text/html**.

Những điều cần xem khi điều tra:

1. **Content-Type** có đúng ý nghĩa giữa các phần hay không.
2. **Thứ tự**: text/plain đứng trước text/html trong alternative.
3. **Charset**: chuỗi tiếng Việt hiển thị đúng.
4. **Giá trị nội dung**: hai bản có cùng thông tin và URL cần thiết.
5. **Attachment và inline**: có quan hệ mixed/related hợp lý, không bị hiểu thành bản alternative.
6. **Client behavior**: hiển thị được HTML và vẫn đọc được plain text khi client ưu tiên văn bản thuần.

Việc xem MIME thô nên giới hạn trong môi trường thử nghiệm hoặc công cụ bảo vệ dữ liệu, vì raw message có thể chứa địa chỉ người nhận, token và thông tin cá nhân.

### Sơ đồ quyết định của email client

~~~text
            Nhận một MimeMessage
                     |
                     v
        Đọc cấu trúc multipart/alternative
                     |
             +-------+-------+
             |               |
     Hỗ trợ/chọn HTML?    Chỉ chọn plain text?
             |               |
             v               v
      Hiển thị text/html   Hiển thị text/plain
             |               |
             +-------+-------+
                     |
                     v
        Người dùng thấy cùng thông tin chính
~~~

Sơ đồ là cách hình dung đơn giản. Thực tế, client chọn phương án dựa trên định dạng hỗ trợ, thứ tự ưu tiên trong MIME và tùy chọn người dùng; không có bảo đảm mọi client đều dùng quy tắc hiển thị giống hệt nhau.

## 13. Kết luận

**multipart/alternative** là cơ chế MIME để đưa **plain text và HTML như hai biểu diễn thay thế của cùng một email**. Trong trường hợp thông dụng, sắp xếp **text/plain trước, text/html sau**, giữ nội dung quan trọng tương đương và để email client chọn phương án phù hợp.

Với Spring Framework Mail, **JavaMailSender** tạo/gửi MimeMessage và **MimeMessageHelper.setText(plainText, htmlText)** giúp dựng các phần alternative. Khi có tệp đính kèm hoặc ảnh inline, kết hợp đúng **multipart/mixed** và **multipart/related** ở các cấp lồng nhau. Hãy coi plain text là một phiên bản hoàn chỉnh và có thể sử dụng độc lập, không chỉ là câu thông báo yêu cầu người nhận bật HTML.
