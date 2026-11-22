# Giới hạn của plain text khi cần định dạng

Trong **Spring Framework Mail**, cách gửi email đơn giản nhất thường bắt đầu bằng **SimpleMailMessage**: chọn người gửi, người nhận, tiêu đề, nội dung rồi gọi **JavaMailSender.send(...)**. Cách này phù hợp với những thông báo chỉ cần văn bản rõ ràng như mã xác minh, cảnh báo hệ thống hoặc xác nhận một thao tác. Nhưng khi email cần tiêu đề lớn, màu sắc, nút hành động, bảng trình bày, logo hay ảnh đặt ngay trong nội dung, **plain text không còn diễn đạt được yêu cầu hiển thị một cách đáng tin cậy**.

Điểm cần hiểu không phải plain text là một định dạng “kém”, mà là nó có **hợp đồng hiển thị khác với HTML**. Trong plain text, người gửi cung cấp **ký tự và ngắt dòng**; ứng dụng đọc thư quyết định kiểu chữ, kích thước, màu sắc và cách trình bày. Nội dung như **<strong>Quan trọng</strong>** không tự biến thành chữ đậm. Tương tự, dấu sao của Markdown không tự trở thành định dạng trong một email văn bản thuần.

Bài học này giải thích giới hạn đó trong chương **Simple mail**, cho thấy khi nào nên giữ **SimpleMailMessage**, khi nào chuyển sang **MimeMessage** và **MimeMessageHelper**, và cách gửi cả **plain text + HTML** để người đọc vẫn có nội dung sử dụng được khi HTML bị tắt hoặc không được hỗ trợ.

## 1. Plain text trong email thực chất là gì?

Một email có phần thân văn bản thuần thường được biểu diễn với **Content-Type: text/plain**. MIME có thể thêm tham số charset, ví dụ:

~~~text
MIME-Version: 1.0
From: notifications@example.test
To: learner@example.test
Subject: Thông báo
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

Phần raw ở trên minh họa nội dung **“Xin chào!”** được chuyển từ ký tự thành byte UTF-8, sau đó mã hóa bằng **quoted-printable** để vận chuyển. Khi trình đọc thư giải mã, người dùng thấy văn bản thông thường.

Cần phân biệt ba khái niệm:

| Khái niệm | Quy định điều gì? | Ví dụ |
| --- | --- | --- |
| **Content-Type** | Dữ liệu cần được hiểu là văn bản thuần, HTML hay loại nội dung khác | **text/plain**, **text/html** |
| **Charset** | Byte biểu diễn ký tự theo bộ mã nào | **UTF-8** |
| **Content-Transfer-Encoding** | Byte được biểu diễn thế nào trong phần thân MIME để truyền tải | **quoted-printable**, **base64**, **7bit** |

**UTF-8 không biến plain text thành HTML**, và **Base64 không tạo ra định dạng đậm/nghiêng**. Các cơ chế mã hóa giải quyết chuyện bảo toàn ký tự/byte, còn loại nội dung quyết định cách trình đọc thư diễn giải chúng.

### SimpleMailMessage có quan hệ gì với text/plain?

Trong Spring Mail, **SimpleMailMessage** là đối tượng chứa các thuộc tính cơ bản của thư:

- **From**, **Reply-To**, **To**, **Cc**, **Bcc**.
- **Subject**.
- **Sent date** nếu cần.
- **Text**: chuỗi nội dung văn bản thuần.

Khi gửi bằng **JavaMailSender** hoặc implementation phù hợp, thư viện chuẩn bị thông điệp mail cần thiết để nộp cho transport. **SimpleMailMessage không có API chọn HTML body, thêm MIME part nội tuyến hay đính kèm file** như **MimeMessageHelper**.

Vì vậy, nếu cần một email với phần thân có cấu trúc hiển thị phức tạp, việc chỉ thay chuỗi truyền vào **SimpleMailMessage.setText(...)** thường không đủ. Cần chuyển sang API tạo MIME message phù hợp.

## 2. Những gì plain text làm tốt

Văn bản thuần vẫn có giá trị lớn vì đơn giản, dễ đọc và ít phụ thuộc cách trình bày của email client.

Ví dụ một thông báo có thể viết:

~~~text
XÁC NHẬN ĐĂNG KÝ

Xin chào Lan,

Bạn đã đăng ký thành công khóa học "Spring Boot Cơ bản".

Mã đăng ký: REG-1528
Thời gian:   09:00 ngày 20/11/2026

Để xem chi tiết:
https://learning.example.test/registrations/REG-1528

Nếu bạn không thực hiện yêu cầu này, hãy liên hệ bộ phận hỗ trợ.

Trân trọng,
Đội ngũ học tập
~~~

Nội dung này vẫn có thứ tự, khoảng cách đoạn và liên kết dạng chữ. Người nhận có thể đọc được ngay cả khi ứng dụng mail hạn chế HTML, ảnh hoặc CSS.

Các công cụ trình bày có thể dùng an toàn trong plain text gồm:

- **Đoạn văn** với dòng trống ngăn cách.
- **Tiêu đề bằng chữ**, ví dụ một dòng viết hoa hoặc thêm dấu phân cách.
- **Danh sách** đánh số hoặc gạch đầu dòng dưới dạng ký tự thông thường.
- **Nhãn và giá trị**, chẳng hạn **Mã đơn: ORDER-125**.
- **Đường dẫn đầy đủ** có giao thức **https://**, thuận tiện để sao chép.
- **Các bước thao tác** theo thứ tự rõ ràng.

Tuy vậy, việc các ký tự xuất hiện đúng không có nghĩa chúng sẽ được trình bày bằng cùng font, độ rộng, cỡ chữ hoặc bố cục trên mọi thiết bị.

### Plain text cũng hỗ trợ tiếng Việt và Unicode

Văn bản thuần **không bị giới hạn ở ASCII** nếu thông điệp dùng charset/transfer encoding phù hợp. Một nội dung như:

~~~text
Chào bạn,
Mã xác minh của bạn là: 482193
Mã này hết hạn sau 10 phút.
~~~

có thể được gửi bằng UTF-8. Khi người nhận bị lỗi dấu, cần kiểm tra charset, mã hóa dữ liệu đầu vào và MIME headers, thay vì kết luận plain text không thể chứa tiếng Việt.

Ký tự Unicode hoặc emoji cũng có thể được biểu diễn trong text/plain. Nhưng việc glyph được hiển thị thế nào còn phụ thuộc font, hệ điều hành và email client; không nên dựa vào emoji như **phương tiện duy nhất để truyền đạt trạng thái quan trọng**.

## 3. Giới hạn đầu tiên: không điều khiển được kiểu chữ và màu sắc

Giả sử yêu cầu giao diện là:

> Dòng “Thanh toán thành công” phải màu xanh, chữ lớn; số tiền màu đậm; cảnh báo ở cuối màu đỏ.

Đặt chuỗi sau vào SimpleMailMessage:

~~~text
<h1 style="color:green">Thanh toán thành công</h1>
Số tiền: <strong>350.000 VND</strong>
<p style="color:red">Không chia sẻ mã giao dịch.</p>
~~~

**không biến nó thành HTML khi thư được gửi dưới dạng text/plain**. Người đọc thường sẽ thấy các dấu **<**, **>**, thuộc tính và thẻ nguyên văn, như một đoạn code không được diễn giải.

Một chuỗi kiểu Markdown cũng không tự tạo định dạng:

~~~text
# Thanh toán thành công
**Số tiền:** 350.000 VND
~~~

Khi nằm trong body **text/plain**, ký tự **#** và **\*\*** vẫn là ký tự. Một số ứng dụng có thể áp dụng quy tắc riêng cho việc hiển thị, nhưng không có hợp đồng chuẩn rằng mọi email client sẽ render Markdown thành heading và chữ đậm.

**Không nên hy vọng người nhận sử dụng cùng công cụ xem Markdown hoặc HTML preview như lập trình viên**. Email client xử lý nội dung dựa vào MIME type và khả năng hiển thị, không dựa vào việc lập trình viên có ý định “định dạng” chuỗi text thế nào.

### Vì sao không thể dùng ANSI escape codes?

Một số chương trình terminal hỗ trợ mã điều khiển ANSI để đổi màu, in đậm hoặc điều khiển con trỏ. Email client không có nghĩa vụ diễn giải những chuỗi này trong **text/plain**. Đưa escape codes vào email có thể làm xuất hiện ký tự lạ, làm hỏng khả năng đọc hoặc tạo rủi ro khi dữ liệu đi qua các hệ thống log/terminal.

Plain text không phải một terminal tương tác; các thủ thuật đổi màu của console không phải phương án định dạng email đáng tin cậy.

## 4. Giới hạn thứ hai: căn cột, bảng và bố cục dễ bị lệch

Bạn có thể viết một bảng đơn giản bằng dấu cách:

~~~text
Sản phẩm           Số lượng    Thành tiền
Khóa học Spring    1           500.000
Tài liệu bổ sung   2           100.000
-------------------------------------------
Tổng cộng                      600.000 VND
~~~

Nó có vẻ ngay hàng trong trình soạn thảo **monospace**, nhưng không bảo đảm hiển thị đúng ở email client:

- Trình đọc thư có thể sử dụng **font tỷ lệ**; ký tự **i** và **W** có chiều rộng khác nhau.
- Client trên điện thoại có thể tự xuống dòng vì vùng xem hẹp.
- Tiếng Việt, ký tự rộng, dấu tổ hợp hoặc emoji có thể chiếm số cột hiển thị khác số ký tự.
- Người dùng có thể phóng to chữ theo cài đặt trợ năng.
- Một số client tự diễn giải định dạng dòng hoặc làm thay đổi cách hiển thị khoảng trắng.

Vì vậy, đừng dùng việc đệm dấu cách để bảo đảm hóa đơn, báo cáo hoặc bảng so sánh giữ nguyên cột trên mọi thiết bị.

### Trình bày thay thế khi vẫn muốn giữ plain text

Thay bảng nhiều cột bằng các khối thông tin có nhãn:

~~~text
ĐƠN HÀNG #ORD-1528

1. Khóa học Spring
   Số lượng: 1
   Thành tiền: 500.000 VND

2. Tài liệu bổ sung
   Số lượng: 2
   Thành tiền: 100.000 VND

TỔNG CỘNG: 600.000 VND
~~~

Cách này thường bền vững hơn trên màn hình hẹp vì ý nghĩa không phụ thuộc vào khoảng cách ngang. Nhưng nếu yêu cầu thật sự là **bảng có đường kẻ, căn phải số tiền, nền xen kẽ và nhóm hàng**, bạn sẽ cần nội dung HTML (hoặc tệp đính kèm như PDF khi muốn giữ bố cục cố định).

### Ngắt dòng cũng không tuyệt đối

Trong chuỗi Java, ký tự **\n** biểu diễn xuống dòng logic; thư viện vận chuyển có thể chuẩn hóa sang **CRLF** theo quy tắc email. Email client có thể quấn dòng dài để vừa khung hiển thị. **Ngắt dòng do người gửi tạo** và **dòng bị client quấn khi hiển thị** là hai việc khác nhau.

Plain text còn có cơ chế như **format=flowed** để gợi ý cách trình bày những dòng văn bản, nhưng không nên mặc định **SimpleMailMessage** tạo kiểu nội dung đó, hay mọi client đều áp dụng một cách giống nhau.

Nếu cần nhấn mạnh một cảnh báo, nên viết cảnh báo dưới dạng câu độc lập, dễ đọc, thay vì dựa vào khoảng trắng hoặc số cột.

## 5. Giới hạn thứ ba: liên kết không thành nút hành động có chủ đích

Trong text/plain:

~~~text
Xem đơn hàng của bạn:
https://orders.example.test/order/1528
~~~

nhiều email client sẽ **tự phát hiện URL và biến thành liên kết có thể bấm**, nhưng đó là hành vi của client. Người gửi không điều khiển đáng tin cậy nhãn nút, màu sắc, vùng bấm hay trạng thái hover như trong HTML.

Bạn cũng không thể tạo nút thật chỉ bằng cách viết:

~~~text
[ XEM ĐƠN HÀNG ]
~~~

Dòng này chỉ là các ký tự. Người đọc có thể hiểu ý nghĩa, nhưng không có một URL gắn vào vùng hiển thị được xác định bởi **text/plain**. Cú pháp Markdown kiểu **[Xem đơn hàng](https://orders.example.test/order/1528)** cũng không được bảo đảm trở thành link có nhãn đẹp trong email plain text.

Khi cần **call-to-action** (CTA) như nút “Đặt lại mật khẩu”, “Xác nhận email” hoặc “Xem hóa đơn”, HTML có thể biểu diễn phần tử liên kết với nhãn và kiểu trình bày rõ ràng:

~~~html
<a href="https://orders.example.test/order/1528">
  Xem đơn hàng
</a>
~~~

Tuy nhiên, chính HTML cũng có mức hỗ trợ CSS khác nhau giữa email clients. **Link HTML là yếu tố chức năng**, còn việc làm nó trông như một nút đẹp phải được thiết kế và kiểm tra theo các client mục tiêu.

Với plain text fallback, nên cung cấp URL đầy đủ, dễ sao chép. Tránh dùng lời hướng dẫn “bấm nút màu xanh bên dưới” khi trong phần plain text thực sự không có nút.

## 6. Giới hạn thứ tư: hình ảnh, tệp đính kèm và nội dung nhiều phần

**SimpleMailMessage.setText(...)** chỉ tiếp nhận chuỗi văn bản. Nếu bạn truyền vào đường dẫn ảnh:

~~~text
Logo: /assets/brand-logo.png
~~~

thì ứng dụng đọc thư không tự truy cập file nằm trên đĩa của server để hiển thị logo. Tương tự, chèn **byte của PDF** hoặc chuỗi Base64 vào text body không tự tạo tệp đính kèm.

Trong email, các nội dung này là những **MIME parts** khác nhau:

| Yêu cầu | Cách biểu diễn thường gặp |
| --- | --- |
| Văn bản đơn giản | **text/plain** |
| Nội dung có heading, danh sách HTML, màu sắc, link có nhãn | **text/html** |
| Hai phiên bản nội dung tương đương plain + HTML | **multipart/alternative** |
| Ảnh được HTML tham chiếu bằng **cid:** | **multipart/related** với ảnh có **Content-ID** |
| File PDF, CSV hoặc ZIP đính kèm | MIME part có **Content-Disposition: attachment**; thường nằm trong **multipart/mixed** |

**MIME là cơ chế đóng gói**, còn **HTML** là một loại nội dung bên trong MIME. Việc có attachment không nhất thiết đồng nghĩa email phải có body HTML; một email vẫn có thể có phần nội dung text/plain và một PDF đính kèm.

Khi cần những MIME parts này trong Spring, **JavaMailSender** phối hợp với **MimeMessage** và **MimeMessageHelper** phù hợp hơn **SimpleMailMessage**.

## 7. Gửi plain text bằng SimpleMailMessage

Đây là ví dụ hoàn chỉnh ở mức service Spring về cách gửi một thông báo văn bản:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationPlainMailService {

    private final JavaMailSender mailSender;

    public RegistrationPlainMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendRegistrationNotice(
            String recipient,
            String registrationCode
    ) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("notifications@example.test");
        mail.setTo(recipient);
        mail.setReplyTo("support@example.test");
        mail.setSubject("Xác nhận đăng ký");

        String body = """
                XÁC NHẬN ĐĂNG KÝ

                Xin chào,

                Yêu cầu đăng ký của bạn đã được ghi nhận.
                Mã đăng ký: %s

                Nếu cần hỗ trợ, hãy trả lời email này.

                Trân trọng,
                Đội ngũ học tập
                """.formatted(registrationCode);

        mail.setText(body);
        mailSender.send(mail);
    }
}
~~~

Điều quan trọng trong đoạn mã:

- **setSubject(...)** đặt tiêu đề email; nó không phải tiêu đề HTML bên trong body.
- **setText(...)** đặt nội dung văn bản thuần. Xuống dòng và các ký tự trong text block là một phần của chuỗi nội dung.
- **setReplyTo(...)** định hướng nơi người dùng gửi thư trả lời; không làm body trở thành HTML.
- **send(mail)** nộp thông điệp qua transport được cấu hình. Nó không bảo đảm thư đã được phát đến Inbox.

Ví dụ sử dụng domain **example.test** nhằm minh họa. Trong ứng dụng thật, **registrationCode** cần được tạo và kiểm soát bởi nghiệp vụ; địa chỉ, cấu hình SMTP và quyền gửi phải hợp lệ theo nhà cung cấp.

### Nếu đưa HTML vào setText thì sao?

Ví dụ:

~~~java
mail.setText("""
        <h1>Đăng ký thành công</h1>
        <p><strong>Mã đăng ký:</strong> REG-1528</p>
        """);
~~~

Đây vẫn là **chuỗi văn bản**. Không có tham số nào của **SimpleMailMessage.setText(...)** để nói rằng phần thân là **text/html**. Vì vậy, người nhận có thể nhìn thấy nguyên các thẻ, thay vì thấy tiêu đề đậm và đoạn văn được render.

**Không nên sửa vấn đề bằng cách đặt Content-Type thủ công ở nơi không có API MIME thích hợp.** Hãy dùng **MimeMessage** khi thật sự cần HTML và quản lý đúng kiểu MIME part.

## 8. Chuyển sang HTML bằng MimeMessageHelper

Nếu yêu cầu là một email có tiêu đề HTML, đoạn văn được đánh dấu và nút liên kết, sử dụng **MimeMessageHelper.setText(html, true)**.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationHtmlMailService {

    private final JavaMailSender mailSender;

    public RegistrationHtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đăng ký");

        String html = """
                <html>
                  <body>
                    <h1 style="color: #17653a;">Đăng ký thành công</h1>
                    <p>Yêu cầu của bạn đã được ghi nhận.</p>
                    <p>
                      <a href="https://learning.example.test/account"
                         style="background: #17653a;
                                color: white;
                                padding: 12px 20px;
                                text-decoration: none;">
                        Xem tài khoản
                      </a>
                    </p>
                  </body>
                </html>
                """;

        helper.setText(html, true);
        mailSender.send(message);
    }
}
~~~

Tham số **true** ở **setText(html, true)** cho biết chuỗi này là nội dung **HTML**. Khi đó thư viện có thể tạo phần MIME với loại **text/html** và charset tương ứng. Nếu đặt **false**, cùng các ký tự HTML sẽ được coi là văn bản thuần.

**MimeMessageHelper(message, false, "UTF-8")** ở ví dụ có tham số **false** chỉ **không tạo cấu trúc multipart ngay từ đầu**; nó không có nghĩa helper chỉ có thể tạo plain text. Để phân biệt cho đúng, cần xem **hai cờ ở hai vị trí khác nhau**:

| Lời gọi | Ý nghĩa |
| --- | --- |
| **new MimeMessageHelper(message, false, "UTF-8")** | Tạo helper không multipart cho một nội dung chính |
| **helper.setText(html, true)** | Phần body đã cho là HTML |
| **helper.setText(text, false)** | Phần body đã cho là plain text |
| **new MimeMessageHelper(message, true, "UTF-8")** | Bật hỗ trợ cấu trúc multipart, có thể cần cho các nội dung phức tạp |

Đây là điểm dễ nhầm khi chuyển từ SimpleMailMessage sang MIME: **multipart** và **HTML** không phải hai từ đồng nghĩa. Một email HTML đơn giản có thể dùng một phần text/html; một email có PDF có thể dùng multipart nhưng body lại là text/plain.

### HTML không bảo đảm mọi thiết kế đều giống nhau

Mã trên minh họa cú pháp, không phải mẫu email tương thích với mọi client. Trong thực tế, các ứng dụng mail có cách hỗ trợ CSS khác nhau; một số có thể bỏ thuộc tính hoặc thay đổi cách trình bày. Với template sản xuất, cần kiểm tra các client, thiết bị và chế độ dark mode mà người dùng thực sự sử dụng.

Đặc biệt, email HTML không phải trang web tương tác thông thường. Script JavaScript, form phức tạp và một số CSS có thể bị chặn hoặc không được hỗ trợ; không nên xây chức năng cốt lõi dựa trên việc email client cho chạy các mã đó.

## 9. Giải pháp tốt cho email có định dạng: multipart/alternative

Khi người dùng cần nhận nội dung HTML nhưng vẫn phải có bản có thể đọc bằng văn bản thuần, một lựa chọn phổ biến là tạo **hai phiên bản tương đương** trong cùng thông điệp:

~~~text
MIME message
    |
    '-- multipart/alternative
          |
          +-- text/plain; charset=UTF-8
          |     "Xác nhận đăng ký. Truy cập https://..."
          |
          '-- text/html; charset=UTF-8
                <h1>Xác nhận đăng ký</h1>
                <a href="https://...">Xem tài khoản</a>
~~~

Đây là **hai cách trình bày thay thế của cùng một nội dung**, không phải hai email khác nhau được gửi tới người nhận. Phần mềm đọc thư chọn phần phù hợp với khả năng hoặc cài đặt của nó.

### Ví dụ Spring: setText(plainText, htmlText)

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationAlternativeMailService {

    private final JavaMailSender mailSender;

    public RegistrationAlternativeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String recipient,
            String code
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                "UTF-8"
        );

        helper.setFrom("notifications@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đăng ký");

        String plainText = """
                XÁC NHẬN ĐĂNG KÝ

                Mã đăng ký: %s

                Xem tài khoản tại:
                https://learning.example.test/account
                """.formatted(code);

        String htmlText = """
                <html>
                  <body>
                    <h1>Xác nhận đăng ký</h1>
                    <p>Mã đăng ký: <strong>%s</strong></p>
                    <p>
                      <a href="https://learning.example.test/account">
                        Xem tài khoản
                      </a>
                    </p>
                  </body>
                </html>
                """.formatted(code);

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
~~~

**helper.setText(plainText, htmlText)** là overload phục vụ hai phiên bản nội dung. Với cách gọi này, helper cần ở **multipart mode** để tạo cấu trúc MIME phù hợp. Ở ví dụ, constructor với **true** đáp ứng yêu cầu đó.

Một số đặc điểm:

- **Plain text** có các thông tin chính: mã đăng ký và địa chỉ xem tài khoản.
- **HTML** có cùng thông tin, nhưng dùng heading, strong và link có nhãn.
- Hai phiên bản cùng mô tả **một sự kiện**. Không nên để chúng có số tiền, trạng thái hoặc đường dẫn khác nhau.
- JavaMailSender và Jakarta Mail đảm nhiệm việc tạo MIME và transfer encoding phù hợp; ứng dụng không phải tự Base64-encode hai phiên bản text.

Trong ví dụ, biến **code** là dữ liệu được hệ thống tạo với định dạng đã kiểm soát. Nếu đưa dữ liệu tùy ý của người dùng vào **htmlText** bằng nội suy chuỗi, cần thực hiện bước **HTML escaping**; phần tiếp theo giải thích cách xử lý.

### Không bắt buộc mọi email HTML phải có ảnh hoặc file đính kèm

Một thông điệp chỉ chứa plain text và HTML đã có thể dùng **multipart/alternative**, không cần attachment. Ngược lại, một thông điệp có logo nội tuyến hoặc PDF thường cần cấu trúc MIME lồng nhau như **multipart/related** và **multipart/mixed**. **MimeMessageHelper** giúp xây dựng cấu trúc đó mà không phải ghép boundary thủ công.

## 10. Giữ plain fallback có ý nghĩa, không chỉ là một dòng “hãy bật HTML”

Một bản plain text có chất lượng cần truyền đạt **đầy đủ nội dung thiết yếu**, chứ không chỉ có:

~~~text
Vui lòng bật HTML để xem thông báo.
~~~

Đoạn này không hữu ích nếu người nhận dùng trình đọc thư chỉ hỗ trợ text, hoặc nếu HTML bị chặn trong môi trường truy cập của họ.

Giả sử phiên bản HTML có:

~~~html
<h2>Yêu cầu đặt lại mật khẩu</h2>
<p>Liên kết có hiệu lực trong 15 phút.</p>
<a href="https://accounts.example.test/reset/xyz">
  Đặt lại mật khẩu
</a>
~~~

Bản plain text tương ứng nên là:

~~~text
YÊU CẦU ĐẶT LẠI MẬT KHẨU

Liên kết đặt lại mật khẩu có hiệu lực trong 15 phút.

Truy cập:
https://accounts.example.test/reset/xyz

Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.
~~~

Ở cả hai bản, người dùng nhận cùng thông tin về **mục đích**, **thời hạn** và **đường dẫn hành động**. Sự khác biệt chỉ nằm ở cách trình bày. Với các link có token, phải tạo token an toàn và có thời hạn theo nghiệp vụ, tránh đưa vào log không cần thiết; việc có hai MIME parts không có nghĩa phải tạo hai token khác nhau.

### Có nên tự động bỏ hết thẻ HTML để tạo plain text?

Một cách làm đơn giản là xóa mọi HTML tag khỏi chuỗi rồi dùng kết quả làm plain text. Nhưng cách đó thường làm mất:

- **Nhãn và URL thật của link**: người đọc chỉ thấy “Xem tài khoản” mà không có đường dẫn.
- **Ranh giới đoạn/danh sách**: các phần tử có thể dính vào nhau.
- **Nội dung do thuộc tính mô tả**, chẳng hạn alt text của ảnh mang thông tin.
- **Ngữ nghĩa bảng**: giá trị ở các cột có thể mất quan hệ.

Với nội dung quan trọng, nên **soạn bản plain text có chủ đích** hoặc dùng bộ chuyển đổi HTML-to-text có quy tắc rõ ràng, được kiểm tra bằng thư nhận thực tế. Hai bản nên được tạo từ cùng một **mô hình dữ liệu thông báo** để tránh sai lệch.

## 11. Nội dung HTML cần thoát ký tự và kiểm soát URL

Khi chuyển sang HTML, một lớp rủi ro mới xuất hiện: dữ liệu từng được coi là văn bản trong plain text giờ có thể bị **diễn giải như markup**.

Giả sử tên người dùng là:

~~~text
Lan <Manager>
~~~

Nếu đưa trực tiếp vào HTML:

~~~html
<p>Xin chào Lan <Manager></p>
~~~

thì chuỗi **<Manager>** có thể bị trình xử lý HTML coi là tag, khiến nội dung hiển thị khác mong muốn. Tương tự, dữ liệu nhận từ biểu mẫu có thể chứa các ký tự có ý nghĩa đặc biệt như **&**, **"**, **<** hoặc **>**.

Spring có lớp **HtmlUtils** giúp escape văn bản dùng làm nội dung HTML:

~~~java
import org.springframework.web.util.HtmlUtils;

String displayName = "Lan <Manager>";
String safeDisplayName = HtmlUtils.htmlEscape(
        displayName,
        "UTF-8"
);

String html = "<p>Xin chào " + safeDisplayName + "</p>";
~~~

Khi render HTML, phần text được xử lý để ký tự đặc biệt hiển thị như dữ liệu, thay vì bị diễn giải như cấu trúc HTML. Lớp **HtmlUtils** thuộc Spring Web; nếu ứng dụng không có module đó, có thể dùng giải pháp escaping phù hợp với thư viện template đang sử dụng.

**Không nên gọi HtmlUtils.htmlEscape trên toàn bộ HTML template đã hoàn chỉnh**, vì hành động đó có thể khiến cả thẻ **<p>**, **<a>** hiển thị nguyên văn. Hãy escape **giá trị động** tại vị trí chèn vào HTML hoặc sử dụng template engine có cơ chế escaping đúng ngữ cảnh.

### Escape văn bản khác với kiểm tra URL

Với một link HTML, không chỉ quan tâm nội dung nhìn thấy mà còn phải kiểm soát **href**:

~~~html
<a href="https://accounts.example.test/confirm">Xác nhận email</a>
~~~

Nếu URL được tạo từ dữ liệu do người dùng nhập, cần giới hạn scheme và domain theo nghiệp vụ, encode các thành phần URL đúng chỗ và escape giá trị thuộc tính HTML. **HTML escaping không tự biến một URL nguy hiểm thành URL đáng tin cậy**. Tránh để người nhận bị điều hướng tới domain tùy ý do nguồn dữ liệu không kiểm soát.

Với email giao dịch, việc dùng một URL HTTPS rõ domain cùng với bản plain text tương đương thường dễ kiểm tra hơn so với tạo link động bằng nối chuỗi không kiểm soát.

## 12. Nếu email cần logo hoặc PDF thì chuyển sang multipart

Khi yêu cầu định dạng vượt khỏi HTML thông thường, email có thể cần nhiều MIME parts. Một cấu trúc thường gặp là:

~~~text
multipart/mixed
 |
 +-- multipart/related
 |    |
 |    +-- multipart/alternative
 |    |    +-- text/plain
 |    |    '-- text/html
 |    |
 |    '-- image/png (inline, Content-ID)
 |
 '-- application/pdf (attachment)
~~~

Đây là một **sơ đồ khái niệm**; cấu trúc multipart chính xác do cách tạo MIME message và hỗ trợ của thư viện quyết định. Nó cho thấy các phần có nhiệm vụ khác nhau:

- **text/plain** là bản nội dung dễ đọc khi không sử dụng HTML.
- **text/html** giữ markup để email client hiển thị khi hỗ trợ.
- **image/png** có thể là logo được HTML tham chiếu qua **cid:**.
- **application/pdf** là tệp được gắn vào thư, không phải văn bản nằm trong body.

Một ví dụ thêm attachment bằng Spring Mail:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailSender {
    private final JavaMailSender sender;

    public InvoiceMailSender(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, Path invoicePdf)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("billing@example.test");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn");

        helper.setText(
                "Hóa đơn đã được đính kèm. Vui lòng xem file invoice.pdf.",
                "<p>Hóa đơn đã được đính kèm.</p>"
                    + "<p>Vui lòng xem file <strong>invoice.pdf</strong>.</p>"
        );

        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(invoicePdf.toFile())
        );

        sender.send(message);
    }
}
~~~

Ở ví dụ này, **FileSystemResource** cung cấp byte PDF từ một file thực tế. Lớp mail xây MIME part cho attachment; **không cần chuyển PDF thành chuỗi Base64 rồi đặt nó trong setText**.

Khi thêm ảnh nội tuyến, helper có phương thức **addInline(...)** để liên kết một resource với **Content-ID** mà HTML tham chiếu bằng **cid:**. Với API này, thông thường nên đặt HTML qua **setText(...)** trước khi gọi **addInline(...)**, và cần khớp CID giữa HTML với tên dùng trong helper.

Tệp đính kèm làm tăng tổng kích thước thư do mã hóa MIME, header và multipart boundaries. Một tệp quá lớn có thể vượt giới hạn SMTP/provider dù bản thân tệp trên đĩa nhỏ hơn ngưỡng mà người dùng mong đợi. Nếu tệp rất lớn, có thể cân nhắc gửi **đường dẫn tải có quyền truy cập và thời hạn** thay vì nhúng file vào từng email.

## 13. HTML có thể định dạng nhiều hơn, nhưng không kiểm soát tuyệt đối

Việc chuyển từ plain text sang HTML giúp thể hiện mục đích trình bày rõ ràng hơn. Tuy nhiên, email client không phải trình duyệt web đầy đủ và không có hợp đồng rendering giống nhau trên mọi nền tảng.

| Yêu cầu định dạng | Plain text | HTML email |
| --- | --- | --- |
| Ngắt đoạn, danh sách ký tự | Có | Có |
| Tiêu đề lớn, chữ đậm, màu sắc | Không điều khiển tin cậy | Có thể mô tả, nhưng hỗ trợ CSS khác nhau |
| Link với nhãn riêng | Thường cần URL nguyên dạng; auto-link tùy client | Dùng thẻ **a** |
| Nút CTA trực quan | Chỉ mô phỏng bằng chữ | Có thể thiết kế bằng link và kiểu trình bày |
| Bảng nhiều cột | Căn bằng dấu cách dễ lệch | Dùng cấu trúc bảng HTML nếu client hỗ trợ |
| Logo và ảnh trong body | Không nhúng trực tiếp | Có thể tham chiếu ảnh từ xa hoặc ảnh inline |
| File đính kèm | Không qua SimpleMailMessage | Cần MIME attachment; có thể dùng cùng plain text/HTML |
| Cách trình bày trên màn hình nhỏ | Client tự quấn dòng | Có thể thiết kế responsive nhưng cần thử nghiệm |
| Tương tác JavaScript phức tạp | Không | Hầu hết email client không cho chạy mã như trang web |

Khi soạn HTML email nên cân nhắc:

- **Ảnh có thể bị chặn**: nội dung cốt lõi không được đặt hoàn toàn trong một ảnh.
- **Dark mode có thể đổi màu**: kiểm tra độ tương phản khi client thay đổi nền/chữ.
- **CSS có mức hỗ trợ khác nhau**: không lấy kết quả trong Chrome làm bằng chứng email sẽ giống hệt.
- **Nút dạng link phải có nhãn rõ nghĩa**: người dùng cần hiểu mình sẽ mở gì.
- **Cỡ chữ và khoảng cách cần đọc được** trên màn hình nhỏ, khi zoom và với công cụ trợ năng.
- **Thông điệp chứa dữ liệu nhạy cảm** phải tuân theo chính sách bảo mật; HTML không làm nội dung mail bí mật hơn.

Nói cách khác, HTML giúp **mô tả ý định định dạng**; người nhận vẫn sử dụng một email client có quyền quyết định cách thể hiện cuối cùng.

### Plain text không nhất thiết kém hiệu quả hơn HTML

Đối với thông báo ngắn, mã OTP hoặc hướng dẫn kỹ thuật, một email plain text gọn và rõ đôi khi lại có trải nghiệm tốt hơn một mẫu HTML nặng. Nó giảm công việc bảo trì template và ít phụ thuộc CSS/ảnh.

Không có quy tắc phổ quát rằng “gửi HTML luôn vào Inbox hơn” hoặc “gửi plain text luôn tránh spam”. Khả năng chuyển phát phụ thuộc nhiều yếu tố khác như danh tiếng gửi thư, xác thực miền, danh sách người nhận, nội dung và chính sách provider. Chọn HTML hay plain text chủ yếu theo **nhu cầu nội dung và trải nghiệm**, không dùng Content-Type như mẹo bảo đảm inbox.

## 14. Thiết kế nội dung trước, chọn định dạng sau

Một lỗi thiết kế hay gặp là viết HTML trước, rồi cố nhét lại HTML vào SimpleMailMessage khi muốn tái sử dụng chức năng gửi mail. Cách rõ ràng hơn là phân tách:

~~~text
Sự kiện nghiệp vụ
   |
   v
Dữ liệu thông báo đã xác thực
   |  recipient, title, orderId, total, targetUrl
   v
Render nội dung
   |
   +-- Plain renderer -> text/plain
   |
   '-- HTML renderer  -> text/html
   |
   v
Mail sender
   |
   +-- Chỉ text -> SimpleMailMessage hoặc MIME text/plain
   |
   '-- HTML / alternative / attachment -> MimeMessage
   |
   v
SMTP provider
~~~

Với cách này, **định dạng không quyết định dữ liệu nghiệp vụ**. Một thông báo đặt hàng có tổng tiền, mã đơn, thời hạn và URL được tạo một lần theo business data; các renderer chỉ trình bày chúng khác nhau.

### Ví dụ cùng dữ liệu, hai dạng hiển thị

Dữ liệu đầu vào:

~~~text
orderId = ORD-1528
total = 600.000 VND
url = https://orders.example.test/ORD-1528
~~~

Plain text:

~~~text
ĐƠN HÀNG ĐÃ ĐƯỢC XÁC NHẬN

Mã đơn: ORD-1528
Tổng tiền: 600.000 VND

Xem đơn hàng:
https://orders.example.test/ORD-1528
~~~

HTML:

~~~html
<h2>Đơn hàng đã được xác nhận</h2>
<p><strong>Mã đơn:</strong> ORD-1528</p>
<p><strong>Tổng tiền:</strong> 600.000 VND</p>
<p>
  <a href="https://orders.example.test/ORD-1528">
    Xem đơn hàng
  </a>
</p>
~~~

Hai cách hiển thị đều truyền đạt chính xác cùng một nội dung. Khi cập nhật trạng thái hay số tiền, thay đổi dữ liệu chung sẽ giúp tránh sự mâu thuẫn giữa hai bản.

### Đừng đặt thông tin bắt buộc chỉ trong ảnh hoặc CSS

Nếu email HTML dùng biểu tượng màu xanh để diễn đạt “thành công”, người dùng plain text hoặc email client chặn ảnh có thể không hiểu trạng thái. Thay vì chỉ dùng biểu tượng, viết rõ:

~~~text
Trạng thái: THANH TOÁN THÀNH CÔNG
~~~

Tương tự, nếu phải diễn đạt lỗi, không chỉ dùng chữ màu đỏ. Hãy dùng nhãn như **“Không thành công”**, kèm lý do và bước cần thực hiện. Cả hai phiên bản nên dùng câu chữ có nghĩa độc lập với màu sắc.

## 15. Kiểm tra email phải phản ánh cách client nhận MIME

Vì plain text và HTML có cơ chế hiển thị khác nhau, việc chỉ in chuỗi **mail.getText()** ở console chưa chứng minh email sẽ được nhận và render đúng. Một quá trình kiểm tra có thể gồm:

1. **Quan sát message thực sự được tạo** qua một SMTP test sink hoặc mail capture được kiểm soát, không dùng địa chỉ khách hàng thật.
2. **Xem MIME structure**: thư chỉ plain text hay chứa **multipart/alternative**, **text/html**, inline images và attachment đúng dự kiến?
3. **Đọc bản plain text**: liệu người dùng có đủ nội dung, URL và bước hành động khi không có HTML?
4. **Mở bản HTML** trên các client mục tiêu, gồm màn hình nhỏ và cài đặt hạn chế ảnh.
5. **Kiểm tra tiếng Việt/Unicode**: charset và transfer encoding phải giữ đúng dấu, không xuất hiện mã QP hoặc Base64 nguyên văn.
6. **Kiểm tra liên kết, alt text và độ tương phản**: người dùng phải hiểu và truy cập được hành động chính.
7. **Kiểm tra giới hạn dung lượng** khi nội dung HTML, ảnh và attachment làm thông điệp lớn hơn.

Nếu muốn xem raw email, có thể nhìn các header như:

~~~text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-example"

--alt-example
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xem t=C3=A0i kho=E1=BA=A3n: https://learning.example.test/account

--alt-example
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xem t=C3=A0i kho=E1=BA=A3n:
<a href=3D"https://learning.example.test/account">M=E1=BB=9F</a></p>

--alt-example--
~~~

Đây là **ví dụ rút gọn** để minh họa multipart và quoted-printable. Trình đọc mail phù hợp giải mã từng part và chọn bản hiển thị. Dòng chứa **=3D** trong HTML raw là ký tự **=** được mã hóa theo quoted-printable; nó không có nghĩa HTML bị hỏng.

Trong nội dung thực tế, các phần MIME có thể được sắp xếp/lồng theo cách khác khi có attachment hoặc ảnh nội tuyến. Hãy để Jakarta Mail tạo boundary và content transfer encoding, tránh tự ghép raw MIME bằng chuỗi.

## 16. Những nhầm lẫn thường gặp khi chuyển từ simple mail

### Nhầm 1: “Có tag HTML trong setText thì email sẽ đẹp hơn”

Với **SimpleMailMessage**, **setText** tạo văn bản thuần. Tag HTML là ký tự được hiển thị, không phải phần tử để client render. Muốn HTML, tạo MimeMessage và gọi **MimeMessageHelper.setText(html, true)**.

### Nhầm 2: “Muốn bold thì dùng Markdown”

Email có MIME type **text/plain** không có cơ chế mặc định để biến dấu **\*\*** thành chữ đậm. Nếu cần nhấn mạnh, dùng chữ và cấu trúc rõ ràng trong plain text; nếu cần kiểu chữ thực sự, dùng HTML.

### Nhầm 3: “Cứ xuống dòng và thêm dấu cách là có bảng đẹp”

Căn cột bằng dấu cách phụ thuộc font, độ rộng màn hình và cách client quấn dòng. Với các nội dung phải trình bày theo cột, dùng HTML table có kiểm tra tương thích hoặc attachment phù hợp; đừng dựa vào bảng ASCII để bảo đảm bố cục.

### Nhầm 4: “Đường dẫn ảnh trong text sẽ được nhúng vào email”

Một đường dẫn file local hoặc URL chỉ là chuỗi ký tự khi đưa vào text/plain. Muốn ảnh nội tuyến, cần MIME/HTML và tài nguyên ảnh được tham chiếu theo cách email client hỗ trợ. Ngay cả như vậy, người nhận có thể chặn việc tải ảnh.

### Nhầm 5: “Bật multipart thì tự động có HTML”

Multipart mô tả **cấu trúc nhiều phần**, không tự quyết định nội dung là HTML. **MimeMessageHelper.setText(html, true)** hoặc overload **setText(plain, html)** mới thể hiện ý định tạo HTML body.

### Nhầm 6: “Dùng HTML thì không cần plain text”

Một bản HTML vẫn có thể hiển thị đúng trên nhiều client, nhưng có bản plain text tương đương giúp những trình đọc hạn chế HTML hoặc người dùng ưu tiên văn bản thuần vẫn tiếp cận được nội dung. Trong những email có hành động bắt buộc, plain fallback nên có URL và hướng dẫn thật sự sử dụng được.

### Nhầm 7: “HTML lúc nào cũng đẹp như trang web”

Email clients có thể chặn ảnh, bỏ một số CSS hoặc thay đổi màu sắc. Template phải được xây dựng cho môi trường email và thử trên các client mục tiêu. Không nên phụ thuộc vào JavaScript, CSS phức tạp hoặc hiệu ứng tương tác như trang web.

### Nhầm 8: “Gửi bằng MimeMessage nghĩa là chắc chắn người dùng đã xem HTML”

MimeMessage chỉ mô tả và gửi nội dung. Email client có thể chọn plain part, chặn HTML/ảnh hoặc áp dụng chính sách riêng. Thao tác **JavaMailSender.send(...)** thành công cũng chỉ thể hiện trạng thái gửi ở tầng ứng dụng/transport, không chứng minh đã hiển thị hay đọc.

## 17. Chọn giải pháp theo yêu cầu

| Yêu cầu nghiệp vụ | Cách tiếp cận phù hợp | Lý do |
| --- | --- | --- |
| Mã OTP, thông báo ngắn, nội dung thuần ký tự | **SimpleMailMessage** | Ít cấu trúc, dễ đọc |
| Thư có vài đoạn văn, nhãn và URL đầy đủ | **SimpleMailMessage** hoặc MIME plain text | Chưa cần markup phức tạp |
| Thư thương hiệu với heading, màu, CTA có nhãn | **MimeMessage** chứa **text/html** | Cần ngữ nghĩa HTML để diễn đạt kiểu trình bày |
| Thư HTML phải có bản đọc được khi HTML không khả dụng | **multipart/alternative** qua MimeMessageHelper | Cung cấp plain + HTML tương đương |
| Logo nội tuyến trong HTML | MIME với **related** parts và Content-ID | Ảnh là một tài nguyên riêng |
| PDF, CSV, tài liệu kèm theo | MIME với **attachment** | File là byte/resource, không phải chuỗi text |
| Bảng hóa đơn cần bố cục cố định khi lưu/in | PDF attachment hoặc đường dẫn tới tài liệu | Giữ bố cục tài liệu độc lập với email client |
| Email mang dữ liệu rất lớn | Đường dẫn tải có kiểm soát thay vì nhúng toàn bộ | Tránh giới hạn dung lượng và overhead MIME |

Lựa chọn có thể kết hợp. Ví dụ một email hóa đơn có **plain + HTML** trong body và **PDF attachment**. Nếu chỉ cần thông báo đơn giản, việc dùng SimpleMailMessage vẫn hoàn toàn hợp lý.

## 18. Tự kiểm tra bằng các tình huống

**Tình huống A — Người dùng phải nhìn thấy tiêu đề màu đỏ và số tiền in đậm.**  
SimpleMailMessage có đáp ứng trực tiếp không?

Không. Nó dùng text/plain. Có thể diễn đạt bằng nhãn dễ đọc trong văn bản, nhưng để tạo ý định hiển thị màu/đậm cần HTML MIME, và vẫn phải chấp nhận sự khác nhau giữa email clients.

**Tình huống B — Thư chứa Markdown: \*\*Quan trọng\*\*.**  
Có chắc sẽ hiển thị chữ đậm không?

Không. Trong text/plain, các dấu sao là ký tự thông thường. Không nên dựa vào việc mail client có cơ chế render Markdown riêng.

**Tình huống C — Cần gửi file PDF nhưng nội dung body vẫn thuần văn bản.**  
Có bắt buộc body HTML không?

Không. Dùng MimeMessage multipart có phần **text/plain** và phần attachment **application/pdf** là đủ. MIME attachment không phụ thuộc body phải là HTML.

**Tình huống D — Đã có HTML đẹp nên tạo plain text chỉ gồm “vui lòng bật HTML”.**  
Đây có phải fallback tốt?

Không. Plain fallback nên chứa thông tin và hành động thiết yếu. Với nút xác nhận trong HTML, bản plain cần có đường dẫn đầy đủ và hướng dẫn rõ ràng.

**Tình huống E — Một URL trong plain text không tự chuyển thành link có thể nhấp.**  
Có phải Spring gửi sai?

Không nhất thiết. Việc tự nhận diện URL để biến thành link là hành vi email client. Trong plain text hãy hiển thị URL đầy đủ; nếu cần liên kết với nhãn và bố cục cụ thể, dùng HTML.

**Tình huống F — Email HTML hiển thị ổn trong trình duyệt nhưng bị lệch trên điện thoại.**  
Nên sửa ở đâu?

Kiểm tra template HTML email, cách CSS được hỗ trợ và quy tắc responsive của các client mục tiêu. Đừng suy ra HTML email tương thích như trang web từ preview trên Chrome.

**Tình huống G — Dùng MimeMessageHelper.setText(html, false).**  
Tại sao người nhận thấy thẻ HTML nguyên văn?

Tham số **false** của phương thức **setText** nói rằng body là plain text. Để dùng HTML phải truyền **true** hoặc dùng overload nhận **plainText, htmlText** trong multipart mode.

**Tình huống H — Chuyển nội dung tiếng Việt sang HTML để sửa lỗi dấu.**  
Chuyển Content-Type như vậy đã đủ chưa?

Chưa chắc. Nếu lỗi nằm ở charset hoặc byte đầu vào, HTML cũng có thể hiển thị sai. Cần kiểm tra UTF-8, MIME headers và đường chuyển đổi dữ liệu; **có HTML** và **có Unicode đúng** là hai vấn đề riêng.

## 19. Nguyên tắc ghi nhớ

~~~text
Email chỉ cần ký tự, đoạn văn, danh sách, URL rõ ràng?
    -> SimpleMailMessage / text/plain

Cần heading, màu, chữ đậm, CTA có nhãn, bảng?
    -> MimeMessage + text/html

Cần cả bản dễ đọc và bản có định dạng?
    -> MimeMessage + multipart/alternative
       text/plain + text/html

Cần ảnh nội tuyến hoặc file đính kèm?
    -> MimeMessage + MIME parts phù hợp

Nội dung chứa tiếng Việt?
    -> Dùng charset phù hợp, thường UTF-8
       Không nhầm encoding với khả năng định dạng

Cần bảo đảm bố cục giống tài liệu để in/lưu?
    -> Cân nhắc PDF hoặc tài liệu tải riêng
~~~

**Giới hạn cốt lõi của plain text là nó truyền đạt nội dung bằng ký tự, không mang một ngôn ngữ mô tả bố cục phong phú như HTML.** Với Spring Framework Mail, **SimpleMailMessage** là công cụ phù hợp cho thư đơn giản và rõ nghĩa. Khi yêu cầu trình bày vượt khả năng text/plain, hãy dùng **MimeMessage/MimeMessageHelper** để tạo HTML, multipart/alternative và attachment đúng ngữ nghĩa, đồng thời giữ bản plain text hữu ích cho khả năng truy cập và tương thích.
