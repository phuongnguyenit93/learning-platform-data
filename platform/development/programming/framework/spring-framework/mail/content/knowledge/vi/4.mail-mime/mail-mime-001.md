# Cấu trúc MIME của một email

Khi xây dựng module gửi mail bằng **Spring Framework Mail**, một email có thể chỉ chứa vài dòng văn bản, nhưng cũng có thể gồm văn bản thuần, HTML, hình ảnh hiển thị trong nội dung và nhiều tệp đính kèm. Để các ứng dụng đọc thư có thể hiểu từng loại dữ liệu và cách chúng liên hệ với nhau, email sử dụng **MIME (Multipurpose Internet Mail Extensions)**.

MIME không phải là máy chủ gửi thư và không phải giao thức thay thế SMTP. **SMTP** đảm nhận trao đổi và chuyển thư giữa các hệ thống; **MIME** quy định cách mô tả và đóng gói nội dung thông điệp. Trong Spring, `JavaMailSender` gửi thông điệp, còn `MimeMessage` và `MimeMessageHelper` là những thành phần thường dùng để tạo nội dung MIME.

Sau bài học, bạn cần đọc được cấu trúc một email MIME, phân biệt các loại `multipart`, hiểu cách charset và transfer encoding ảnh hưởng tới nội dung, đồng thời hình dung cấu trúc mà Spring tạo ra khi gửi HTML, hình ảnh nội tuyến và tệp đính kèm.

## 1. Email có hai lớp cấu trúc: thông điệp và nội dung MIME

Một thông điệp email dạng Internet Message Format có phần **header**, một dòng trống và phần **body**:

~~~text
From: sender@example.com
To: recipient@example.net
Subject: Hello
Date: Thu, 12 Nov 2026 09:00:00 +0700
Message-ID: <message-123@example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello, this is the message body.
~~~

Các thành phần quan trọng:

- **Message headers** (`From`, `To`, `Date`, `Subject`, `Message-ID`): mô tả người gửi, người nhận hiển thị, tiêu đề, thời gian và danh tính thông điệp.
- **MIME headers** (`MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`...): mô tả cách đọc và diễn giải nội dung của message hoặc từng phần con.
- **Dòng trống**: phân cách header với body. Không được xóa dòng này khi phân tích một thông điệp thô.
- **Body**: có thể là văn bản đơn giản hoặc một cấu trúc `multipart` gồm nhiều phần lồng nhau.

Theo chuẩn gửi thư, các dòng trên đường truyền được phân cách bằng **CRLF** (ký tự `\r\n`); ví dụ trong tài liệu được hiển thị như những dòng văn bản thông thường để dễ đọc.

Điểm dễ nhầm: `From` và `To` trong phần header hiển thị **không đồng nhất** với `MAIL FROM` và `RCPT TO` của *SMTP envelope*. Envelope phục vụ vận chuyển; các header là một phần của dữ liệu email. Chúng có thể khác nhau, chẳng hạn thư gửi BCC vẫn có người nhận ở SMTP envelope nhưng không cần hiển thị người đó trong header `To`.

## 2. Các MIME header quan trọng

| Header | Ví dụ | Vai trò |
| --- | --- | --- |
| `MIME-Version` | `MIME-Version: 1.0` | Cho biết thông điệp tuân theo cơ chế MIME phiên bản 1.0. |
| `Content-Type` | `text/html; charset=UTF-8` | Cho biết loại dữ liệu và những tham số cần để hiểu dữ liệu. |
| `Content-Transfer-Encoding` | `base64` | Cho biết cách dữ liệu của phần nội dung được mã hóa cho việc truyền qua hệ thống mail. |
| `Content-Disposition` | `attachment; filename="invoice.pdf"` | Gợi ý ứng dụng đọc thư nên coi nội dung là đính kèm hay hiển thị nội tuyến. |
| `Content-ID` | `<logo-1@example.com>` | Gán danh tính cho một phần nội dung, thường dùng khi HTML tham chiếu hình ảnh nội tuyến bằng `cid:`. |
| `Content-Description` | `Company logo` | Mô tả thêm về một phần MIME khi cần. |

Không phải email nào cũng cần tất cả các header trên. Một thư text đơn giản không có file đính kèm sẽ có cấu trúc khác hẳn thư HTML có hình ảnh và PDF. Một số header xuất hiện ở cấp thông điệp; một số header nằm **bên trong từng MIME part**, vì các phần con có thể có kiểu dữ liệu và encoding khác nhau.

### 2.1. `Content-Type`: dữ liệu này là gì?

Một giá trị `Content-Type` gồm **media type**, **subtype** và có thể có **parameters**:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=UTF-8
Content-Type: application/pdf; name="invoice.pdf"
Content-Type: image/png; name="logo.png"
Content-Type: multipart/alternative; boundary="alt-abc"
~~~

- `text/plain`: phần thân là văn bản thuần, không diễn giải thẻ HTML.
- `text/html`: nội dung HTML để client hiển thị theo khả năng và chính sách bảo mật.
- `image/png`, `image/jpeg`, `application/pdf`: dữ liệu hình ảnh hoặc tài liệu.
- `application/octet-stream`: kiểu nhị phân tổng quát khi không biết chính xác loại file.
- `multipart/...`: đây là một **container**, bên trong gồm các MIME part khác nhau.

Tham số `charset` mô tả bảng mã ký tự của phần text; `boundary` là dấu phân cách giữa các phần của `multipart`. Không nên xem `charset` hay `boundary` là header độc lập ở ngoài `Content-Type`.

### 2.2. `Content-Transfer-Encoding`: dữ liệu được truyền ra sao?

Các cơ chế phổ biến:

| Giá trị | Dùng khi nào | Điều cần nhớ |
| --- | --- | --- |
| `7bit` | Nội dung chỉ dùng ký tự ASCII, các dòng đáp ứng ràng buộc của transport | Không phù hợp để ghi nguyên dạng các ký tự Unicode ngoài ASCII. |
| `8bit` | Nội dung có octet ngoài ASCII khi tuyến truyền có hỗ trợ phù hợp | Cần xét khả năng hỗ trợ `8BITMIME` và các điều kiện SMTP liên quan. |
| `quoted-printable` | Văn bản phần lớn là ký tự ASCII nhưng có thêm ký tự khác | Mã hóa các byte cần thiết thành dạng `=XX`; thường vẫn khá dễ đọc. |
| `base64` | Dữ liệu nhị phân, ví dụ hình ảnh/PDF; cũng có thể dùng cho text | Biến dữ liệu thành ký tự an toàn cho truyền tải; làm tăng kích thước. |
| `binary` | Dữ liệu nhị phân thô trong môi trường có hỗ trợ transport tương ứng | Không nên giả định SMTP thông thường hỗ trợ dạng này. |

**Transfer encoding không phải mã hóa bảo mật.** Người khác có dữ liệu Base64 vẫn giải mã được nội dung. Nếu cần bảo mật đầu cuối, phải dùng cơ chế riêng như S/MIME hoặc các giải pháp mã hóa phù hợp, không dựa vào Base64.

Một phần có thể có:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, b=E1=BA=A1n!
~~~

Sau khi giải mã `quoted-printable` theo UTF-8, nội dung hiển thị là **“Xin chào, bạn!”**. Quá trình đọc đúng gồm hai bước: **giải mã transfer encoding ra các byte ban đầu**, sau đó **giải mã các byte text bằng charset**. Nếu chỉ thực hiện một bước hoặc chọn sai charset, người nhận có thể thấy ký tự bị lỗi.

### 2.3. `Content-Disposition`: nội tuyến hay đính kèm?

Hai giá trị thường gặp:

~~~text
Content-Disposition: inline
Content-Disposition: attachment; filename="report.pdf"
~~~

- `inline`: gợi ý nội dung được hiển thị cùng thân email, chẳng hạn hình ảnh logo.
- `attachment`: gợi ý hiển thị như một tệp đính kèm có thể tải về.

`filename` là tên tệp gợi ý cho người nhận. Nó **không xác thực nội dung thực của tệp** và không cho phép ứng dụng mặc nhiên tin đây là file an toàn. Cách hiển thị cuối cùng phụ thuộc email client, chính sách bảo mật và loại nội dung.

Ký tự Unicode trong tên file có thể đòi hỏi encoding tham số MIME thích hợp; hãy để thư viện mail xử lý thay vì tự ghép chuỗi header bằng tay.

## 3. MIME part: đơn vị cơ bản để tạo cấu trúc

Mỗi **MIME part** có thể chứa một trong hai dạng:

1. **Leaf part (phần lá):** chứa dữ liệu thực như text, HTML, ảnh hay PDF.
2. **Multipart part (phần chứa):** chứa nhiều part khác và xác định quan hệ giữa chúng.

Có thể hình dung toàn bộ email như một **cây**:

~~~mermaid
flowchart TD
    M["Email message"]
    M --> H["Message headers"]
    M --> B["MIME body"]
    B --> P["multipart/mixed"]
    P --> A["multipart/alternative"]
    A --> T["text/plain"]
    A --> R["multipart/related"]
    R --> W["text/html"]
    R --> I["image/png - inline"]
    P --> F["application/pdf - attachment"]
~~~

Một part chứa dữ liệu khác nhau sẽ có `Content-Type` và `Content-Transfer-Encoding` riêng. Các container `multipart` có `boundary` và không phải là một file đính kèm thông thường. **Mối quan hệ giữa các part được quyết định bởi kiểu `multipart` cùng vị trí lồng nhau**, không chỉ bởi tên file.

## 4. Các loại `multipart` thường gặp

### 4.1. `multipart/mixed`: nhiều thành phần độc lập

Loại này thường dùng khi email có **thân thư kèm một hoặc nhiều attachment**.

~~~text
multipart/mixed
├── text/plain              (nội dung thư)
├── application/pdf         (invoice.pdf)
└── application/zip         (documents.zip)
~~~

Các phần có thể được hiển thị/lưu độc lập. `multipart/mixed` không có nghĩa các part là những cách hiển thị thay thế cho cùng một nội dung.

### 4.2. `multipart/alternative`: nhiều cách thể hiện cùng một nội dung

Loại này thường dùng khi cần cả **plain text** và **HTML** của một thông điệp:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

Hai phần là **các phiên bản thay thế**, không phải hai email khác nhau. Client thường chọn phiên bản phù hợp với khả năng, cấu hình và chính sách của nó. Quy ước là đặt cách thể hiện đơn giản trước, phong phú hơn sau; ví dụ text trước HTML.

Nội dung của hai phiên bản nên truyền tải **cùng thông tin cốt lõi**. Nếu HTML chứa đường dẫn xác nhận nhưng plain text lại bỏ sót, người dùng client chỉ hiển thị text có thể không hoàn thành được tác vụ.

### 4.3. `multipart/related`: các phần liên quan trực tiếp

Loại này dùng khi một tài liệu chính phụ thuộc vào các tài nguyên khác, ví dụ HTML có ảnh logo gắn bằng `Content-ID`:

~~~text
multipart/related
├── text/html                (HTML chứa <img src="cid:company-logo">)
└── image/png                (Content-ID: <company-logo>)
~~~

Đây là một tập hợp nội dung liên kết với nhau. Phần HTML thường là nội dung chính, còn hình ảnh là tài nguyên phụ cần để hiển thị nội dung đó. Khi một cấu trúc phức tạp hơn có tham số `start` hoặc `type`, chúng có thể giúp xác định phần root và kiểu tài liệu chính.

**Hình ảnh nội tuyến không giống file đính kèm.** Ảnh có thể là một part MIME và đồng thời được tham chiếu từ HTML, trong khi attachment PDF thường là một phần độc lập. Dù vậy, một số email client vẫn có thể hiển thị ảnh inline trong danh sách file đính kèm.

### 4.4. Chọn loại nào theo nhu cầu?

| Yêu cầu | Cấu trúc MIME thường phù hợp |
| --- | --- |
| Email chỉ có plain text | `text/plain`, không cần `multipart` |
| Email chỉ có HTML | `text/html`; có thể thêm phiên bản text để tăng khả năng tương thích |
| Cả plain text và HTML | `multipart/alternative` |
| HTML có ảnh hiển thị qua CID | `multipart/related` |
| Thân thư kèm PDF | `multipart/mixed` |
| Text + HTML + ảnh inline + PDF | Kết hợp `mixed`, `alternative` và `related` theo cấu trúc cây |

Tên `mixed`, `alternative` và `related` chỉ một **quan hệ**, không phải cấp độ cố định. Cây thực tế do thư viện dựng sẽ có thể khác nhau tùy multipart mode, API đã gọi và yêu cầu tương thích với email client. Quan trọng là các part được nhóm đúng quan hệ và có header hợp lệ.

## 5. Cách `boundary` phân chia các phần

Với `multipart`, header `Content-Type` khai báo một giá trị `boundary`. Body sử dụng giá trị đó để mở và kết thúc các part.

Ví dụ email có hai phiên bản nội dung:

~~~text
From: notification@example.com
To: reader@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-123"

--alt-123
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello, your account is ready.

--alt-123
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body><p>Hello, <b>your account is ready.</b></p></body></html>

--alt-123--
~~~

Phân tích:

- Header đặt `boundary="alt-123"`, nhưng dấu phân cách trong body bắt đầu bằng **hai dấu gạch nối**, tức `--alt-123`.
- Sau mỗi dấu phân cách, một MIME part mới bắt đầu; part đó có header riêng, dòng trống và nội dung riêng.
- Dòng `--alt-123--` có **hai dấu gạch nối ở cuối** để đóng multipart.
- Dòng trống giữa header và body của từng part vẫn phải được giữ.
- Boundary phải được chọn sao cho không gây nhầm với một dòng nội dung thật; các tầng multipart lồng nhau nên dùng boundary riêng.

Ngoài các part, chuẩn cho phép vùng *preamble* trước dấu phân cách đầu và *epilogue* sau dấu kết thúc, nhưng phần lớn ứng dụng hiển thị thư không dùng chúng làm nội dung chính. Nếu tự tạo raw MIME, dùng boundary sai hoặc thiếu dấu kết thúc sẽ làm client phân tích sai. **Với Spring, nên để Jakarta Mail tự sinh boundary.**

## 6. Ví dụ email hoàn chỉnh: text, HTML, logo inline và PDF

Giả sử một email hóa đơn cần có bốn yếu tố:

- Bản **plain text** cho client không hiển thị HTML.
- Bản **HTML** với đường dẫn tới logo nội tuyến.
- **Logo PNG** được tham chiếu bằng `cid:`.
- **File PDF** là attachment để người nhận tải về.

Một cấu trúc hợp lý được biểu diễn như sau:

~~~text
Email
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── multipart/related
    │       ├── text/html
    │       └── image/png (inline, Content-ID: company-logo)
    └── application/pdf (attachment: invoice.pdf)
~~~

Tại đây:

1. Root `mixed` gom nội dung chính và file đính kèm.
2. `alternative` cho người nhận hai cách đọc thư.
3. Bản HTML nằm trong `related` cùng logo mà HTML sử dụng.
4. PDF được đặt ngoài nhóm `alternative` để client không xem PDF là một cách thay thế cho nội dung text.

### 6.1. Biểu diễn raw MIME rút gọn

Đây là bản minh họa cấu trúc, **không phải toàn bộ file email hợp lệ để đem gửi trực tiếp**: các dòng Base64 dùng placeholder, nội dung/ID đơn giản hóa và một số header được lược bỏ để dễ quan sát.

~~~text
From: billing@example.com
To: customer@example.net
Subject: Invoice 123
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-1"

--mixed-1
Content-Type: multipart/alternative; boundary="alt-1"

--alt-1
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, h=C3=B3a =C4=91=C6=A1n c=E1=BB=A7a b=E1=BA=A1n =C4=91=C3=A3 s=E1=BA=B5n s=C3=A0ng.

--alt-1
Content-Type: multipart/related; boundary="related-1"

--related-1
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body>
  <h1>Your invoice is ready</h1>
  <img src="cid:company-logo" alt="Company logo">
</body></html>

--related-1
Content-Type: image/png; name="logo.png"
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline; filename="logo.png"

[BASE64_IMAGE_BYTES]

--related-1--
--alt-1--
--mixed-1
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

[BASE64_PDF_BYTES]

--mixed-1--
~~~

Hãy chú ý sự khác nhau giữa `Content-ID: <company-logo>` (khai báo ở MIME part của ảnh) và `src="cid:company-logo"` (tham chiếu trong HTML). Phần định danh phải khớp để client có cơ sở liên kết ảnh vào đúng vị trí. Trên hệ thống thật, Content-ID nên đủ duy nhất và tuân theo cú pháp thích hợp.

Một số email client có thể bỏ qua nội dung HTML hoặc không hiển thị ảnh vì chính sách bảo mật. Vì vậy, text thay thế và thuộc tính `alt` vẫn có ý nghĩa; đừng đặt thông tin bắt buộc chỉ trong ảnh.

## 7. Cách Spring Framework Mail xây dựng MIME

Trong Spring, các thành phần chính là:

| Thành phần | Thuộc thư viện | Công việc |
| --- | --- | --- |
| `JavaMailSender` | Spring Mail | Tạo và gửi `MimeMessage`; trừu tượng hóa thao tác gửi. |
| `MimeMessage` | Jakarta Mail (`jakarta.mail.internet.MimeMessage`) | Đối tượng đại diện thông điệp MIME và các header/body. |
| `MimeMessageHelper` | Spring Mail (`org.springframework.mail.javamail.MimeMessageHelper`) | Hỗ trợ tạo text/HTML, multipart, inline, attachment và encoding. |
| `MimeMultipart`, `MimeBodyPart` | Jakarta Mail | Các khối cấu tạo cấu trúc multipart ở cấp thấp khi cần thao tác trực tiếp. |
| `DataSource`, `Resource` | Jakarta Activation/Spring Core | Cung cấp nguồn dữ liệu cho tệp đính kèm và tài nguyên inline. |

Trong dự án Spring Boot, có thể đưa Spring Mail vào ứng dụng bằng dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ứng dụng cần cấu hình SMTP sender theo môi trường thực tế. MIME và SMTP là hai lớp trách nhiệm khác nhau: file MIME cấu trúc đúng vẫn không thể gửi nếu SMTP host hoặc thông tin xác thực sai; ngược lại, SMTP thông suốt không sửa được một nội dung MIME bị dựng sai.

### 7.1. Ví dụ 1: chỉ text

Với một thư đơn giản, `SimpleMailMessage` thường đủ:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Đăng ký thành công");
message.setText("Tài khoản của bạn đã được tạo.");

mailSender.send(message);
~~~

Spring sẽ chuyển thông điệp thành dạng phù hợp với sender. Nếu ứng dụng cần HTML hoặc attachment, phải chuyển sang `MimeMessage`. `SimpleMailMessage` không đại diện cho một cây MIME nhiều phần.

### 7.2. Ví dụ 2: text và HTML với `MimeMessageHelper`

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcome(JavaMailSender sender, String recipient)
        throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
    );

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Chào mừng");
    helper.setText(
        "Xin chào! Tài khoản của bạn đã sẵn sàng.",
        "<html><body><h1>Chào mừng!</h1>" +
        "<p>Tài khoản của bạn đã sẵn sàng.</p></body></html>"
    );

    sender.send(message);
}
~~~

`setText(plainText, htmlText)` tạo hai cách biểu diễn nội dung để client lựa chọn. Ở ví dụ, sử dụng chế độ multipart hỗ trợ mở rộng thêm ảnh inline và attachment; nếu chỉ cần một phần text đơn giản thì không cần đến cấu trúc phức tạp như vậy.

Lưu ý: ví dụ mô tả **API** và cách dựng nội dung, không khẳng định hình dạng chính xác từng tầng MIME của mọi phiên bản Spring/Jakarta Mail. Thư viện quyết định cấu trúc cụ thể dựa vào multipart mode và những thao tác trên helper.

### 7.3. Ví dụ 3: text + HTML + ảnh nội tuyến + PDF đính kèm

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            mime,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plain = "Xin chào, hóa đơn của bạn đã sẵn sàng.";
        String html = """
            <html><body>
              <h1>Hóa đơn đã sẵn sàng</h1>
              <p>Xin cảm ơn bạn.</p>
              <img src="cid:company-logo" alt="Company logo">
            </body></html>
            """;

        // Đặt nội dung trước khi khai báo inline resource.
        helper.setText(plain, html);
        helper.addInline(
            "company-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        sender.send(mime);
    }
}
~~~

Giải thích:

- `createMimeMessage()` tạo một đối tượng email MIME.
- `MULTIPART_MODE_MIXED_RELATED` hỗ trợ kết hợp các phần liên quan (nội dung/inline) với các attachment độc lập. Đây là một trong các mode Spring cung cấp để xử lý nhu cầu đa phần.
- `setText(plain, html)` tạo hai phiên bản của cùng nội dung email.
- `addInline("company-logo", ...)` thêm ảnh với ID dùng trong HTML `cid:company-logo`.
- `addAttachment("invoice.pdf", ...)` thêm file có tên và kiểu nội dung tương ứng.
- `sender.send(mime)` giao thông điệp MIME cho quá trình gửi qua transport được cấu hình.

Đoạn mã giả định ứng dụng có tài nguyên `src/main/resources/mail/logo.png` và `pdfBytes` chứa dữ liệu PDF đã được tạo trước đó. Các địa chỉ email chỉ là ví dụ. Với nội dung HTML lấy từ người dùng hoặc dữ liệu nghiệp vụ, cần xử lý escape và tạo liên kết an toàn thay vì nối chuỗi tùy ý.

**Thứ tự thao tác có ý nghĩa:** nên gọi `setText(...)` trước `addInline(...)` theo hướng dẫn sử dụng `MimeMessageHelper`, vì một số email client nhạy cảm với cách sắp xếp các part MIME.

## 8. Các multipart mode của `MimeMessageHelper`

`MimeMessageHelper` cung cấp một số mode để điều khiển cấu trúc khi cần tạo thư multipart:

| Mode | Ý tưởng | Khi có thể dùng |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Không bật multipart | Chỉ có một thân nội dung đơn giản, không cần inline/attachment. |
| `MULTIPART_MODE_MIXED` | Tạo cấu trúc `multipart/mixed` | Muốn gom các phần độc lập, đặc biệt attachment. |
| `MULTIPART_MODE_RELATED` | Tạo cấu trúc `multipart/related` | Email có các tài nguyên liên quan như ảnh inline. |
| `MULTIPART_MODE_MIXED_RELATED` | Kết hợp mixed với related lồng nhau | Email gồm nội dung HTML, tài nguyên inline và attachment. |

Không có mode nào đảm bảo mọi email client hiển thị tuyệt đối giống nhau. Chọn mode theo quan hệ giữa các phần và kiểm tra email thực tế với các client quan trọng của sản phẩm.

Hàm tạo `new MimeMessageHelper(message, true, "UTF-8")` thường được sử dụng để bật multipart; khi muốn làm rõ cấu trúc dự định, dạng truyền vào mode tường minh giúp người đọc code nhận biết ý đồ dễ hơn.

### 8.1. Cách nhận biết một đoạn code đang dựng MIME gì?

Đọc theo trình tự:

1. `MimeMessageHelper` có bật multipart và dùng mode nào?
2. `setText(...)` gọi với một chuỗi hay hai chuỗi? Tham số boolean `html` có được bật khi dùng overload tương ứng không?
3. `addInline(...)` có được sử dụng, và HTML có tham chiếu `cid:...` phù hợp không?
4. `addAttachment(...)` có xuất hiện và được gọi với file/resource nào?
5. `charset` truyền vào helper là gì?

Từ đó có thể suy ra email cần chứa text, HTML, ảnh hay tài liệu mà không phải mở ngay bản raw MIME.

## 9. Encoding, Unicode và header có dấu tiếng Việt

Một email có thể có **hai vấn đề encoding độc lập**:

1. **Nội dung body:** mỗi phần `text/*` có `charset` và `Content-Transfer-Encoding`.
2. **Header thông điệp:** các trường như `Subject` hoặc tên hiển thị người gửi có quy tắc biểu diễn ký tự riêng; chúng không được xem như body text.

Ví dụ:

~~~text
Subject: =?UTF-8?B?<base64-encoded-utf8-bytes>?=
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

Dòng `Subject` minh họa hình thức *encoded-word* dùng cho header theo cơ chế MIME. Phần trong dấu `<...>` chỉ là placeholder; thư viện sẽ tạo giá trị thực. Định dạng encoded-word có thể dùng Base64 (`B`) hoặc dạng `Q`, trong khi body có quy tắc transfer encoding riêng.

Trong Java/Spring, cách nên làm là:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");
helper.setSubject("Xác nhận đơn hàng của bạn");
helper.setText("Xin chào, đơn hàng đã được ghi nhận.", false);
~~~

Khi chọn UTF-8, thư viện chịu trách nhiệm xây dựng header và phần body phù hợp; không nên tự mã hóa Base64 rồi truyền chuỗi đã mã hóa vào `setSubject` trừ khi có yêu cầu rất cụ thể.

Ngoài MIME header encoding truyền thống còn có các mở rộng cho tên miền/địa chỉ và header quốc tế hóa. **Địa chỉ email có ký tự không ASCII** phụ thuộc khả năng hỗ trợ SMTPUTF8 và quy tắc tương thích liên quan; chỉ đặt charset UTF-8 cho body **không tự động** khiến mọi SMTP server nhận được địa chỉ quốc tế hóa.

### 9.1. Tại sao người nhận thấy ký tự như `Ã¡` hoặc `=C3=A1`?

Hai nguyên nhân hay gặp:

- **Sai charset:** byte UTF-8 được giải mã như bảng mã khác nên chữ có dấu biến dạng.
- **Chưa giải mã transfer encoding:** người đọc hoặc công cụ debug hiển thị nguyên chuỗi `=C3=A1` vốn cần được giải mã quoted-printable.

Vì vậy, khi kiểm tra một part bị lỗi tiếng Việt, hãy đọc **cả `Content-Type; charset=...` lẫn `Content-Transfer-Encoding`**, sau đó kiểm tra chuỗi byte thực tế.

## 10. Khác biệt giữa MIME, attachment và dữ liệu vận chuyển

### 10.1. MIME không quyết định email có gửi thành công hay không

Thư HTML đẹp, nội dung MIME hợp lệ vẫn có thể bị server từ chối vì sai địa chỉ, thiếu quyền gửi, file vượt giới hạn kích thước hoặc chính sách lọc. Ngược lại, `JavaMailSender.send(...)` trả về bình thường không chứng minh email đã tới Inbox; đó là kết quả thao tác gửi qua transport.

### 10.2. Base64 làm email lớn hơn

Ví dụ một PDF 1 MB khi mã hóa Base64 sẽ tăng kích thước khoảng một phần ba, chưa tính xuống dòng và header. Ngoài ra, các email có nhiều ảnh inline cũng làm tăng kích thước thực tế. Giới hạn mà provider đặt ra thường tính trên **thông điệp sau khi đóng gói**, không chỉ trên kích thước tệp gốc.

Với tệp lớn, có thể gửi đường dẫn tải xuống có kiểm soát thay vì attachment, nếu yêu cầu nghiệp vụ và bảo mật cho phép.

### 10.3. `Content-Type` chỉ là khai báo

Nếu một tệp độc hại bị gắn `Content-Type: application/pdf`, nó không tự trở thành PDF an toàn. Dữ liệu tệp vẫn cần được kiểm tra theo nhu cầu ứng dụng và chính sách xử lý file. Tương tự, `filename` không nên được dùng trực tiếp làm đường dẫn lưu file trên server.

### 10.4. Ảnh inline, ảnh từ URL và tracking pixel

HTML có thể tham chiếu:

~~~html
<img src="cid:company-logo" alt="Logo inline">
<img src="https://assets.example.com/logo.png" alt="Logo remote">
~~~

- `cid:...` trỏ tới một MIME part được đính kèm trong cùng email.
- `https://...` yêu cầu email client tải tài nguyên từ mạng khi được cho phép.

Ảnh remote có thể bị chặn để bảo vệ quyền riêng tư; ảnh inline làm tăng kích thước email nhưng giảm phụ thuộc vào việc tải tài nguyên ngoài. Một số client chặn hoặc thay đổi cả hai cách, vì thế cần dùng văn bản thay thế thích hợp.

## 11. Đọc và kiểm tra cấu trúc MIME trong lúc phát triển

Khi email bị lỗi định dạng, cách hữu ích nhất là xem **raw message / original message / source** trong công cụ test mail hoặc client hỗ trợ hiển thị nguồn.

Quy trình đọc:

1. Tìm `MIME-Version` và `Content-Type` của toàn message.
2. Nếu là `multipart`, đọc tham số `boundary` và xác định dấu mở/đóng.
3. Lần theo cây part; ở mỗi phần, đọc `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition` và `Content-ID` nếu có.
4. Xác định phần nào là text, HTML, ảnh inline và attachment.
5. Đối chiếu cách client hiển thị với cấu trúc MIME được tìm thấy.

Trong môi trường phát triển, có thể dùng SMTP server thử nghiệm (ví dụ Mailpit hoặc GreenMail) để xem email mà không gửi ra bên ngoài. Với Jakarta Mail, có thể xuất một `MimeMessage` ra tệp `.eml` để xem cấu trúc:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import jakarta.mail.internet.MimeMessage;

MimeMessage message = sender.createMimeMessage();
// ... dùng MimeMessageHelper để điền header và nội dung ...

message.saveChanges();
try (OutputStream output = Files.newOutputStream(Path.of("sample-mail.eml"))) {
    message.writeTo(output);
}
~~~

Ví dụ là thao tác phục vụ phát triển với message đã được chuẩn bị, không phải một bước cần chạy mỗi lần gửi. Tệp `.eml` có thể chứa đầy đủ địa chỉ, nội dung và attachment, vì vậy không lưu trong nơi công khai hoặc commit vào repository nếu có dữ liệu thật.

### 11.1. Lỗi thường gặp và cách nhìn từ cấu trúc MIME

| Hiện tượng | Gợi ý nguyên nhân | Phần cần kiểm tra |
| --- | --- | --- |
| HTML hiện như chuỗi `<h1>...` | Body đang khai báo text/plain hoặc gọi API như plain text | `Content-Type` và cách gọi `setText` |
| Chữ tiếng Việt bị lỗi | Sai charset hoặc decode sai encoding | `charset` và `Content-Transfer-Encoding` của part |
| Ảnh logo không hiện | `cid:` không khớp `Content-ID`, ảnh không nằm trong cấu trúc liên quan hoặc client chặn ảnh | `multipart/related`, `Content-ID`, đường dẫn trong HTML |
| PDF bị hiển thị như text/bị hỏng | Part hoặc transfer encoding sai, dữ liệu nguồn không phải bytes PDF hợp lệ | `Content-Type`, `Content-Transfer-Encoding`, nguồn `addAttachment` |
| Người nhận chỉ thấy bản text hoặc chỉ HTML | Client chọn một nhánh alternative; không phải mọi client hiển thị cả hai | `multipart/alternative` và nội dung từng nhánh |
| File xuất hiện như attachment dù định dùng inline | Client có quy tắc hiển thị riêng hoặc MIME part chưa khai báo phù hợp | `Content-Disposition`, `Content-ID` và quan hệ `related` |
| Toàn bộ nội dung bị nhập thành một part | Boundary không khớp hoặc thiếu dấu đóng | `boundary` và các dòng `--boundary` |
| Email quá lớn, SMTP từ chối | Base64 làm tăng kích thước, nhiều ảnh/attachment | Kích thước thông điệp MIME hoàn chỉnh |

### 11.2. Những câu hỏi nên tự trả lời khi nhìn một raw email

Xét một phần nội dung:

~~~text
Content-Type: application/pdf; name="receipt.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="receipt.pdf"

JVBERi0xLjQK...
~~~

Ta biết part này được khai báo là **PDF**, dùng **Base64** để biểu diễn bytes trên đường truyền, và được gợi ý hiển thị như **attachment** có tên `receipt.pdf`. Ta **chưa thể** khẳng định bytes giải mã thành tệp PDF hợp lệ, tệp đó an toàn, hay người nhận đã tải tệp.

Xét một phần khác:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
~~~

Ta biết part này là **HTML**, ký tự theo **UTF-8**, và dữ liệu phải được **giải mã quoted-printable** trước khi trình hiển thị diễn giải HTML.

## 12. Ghi nhớ cấu trúc qua ba cấp

Khi nhìn một email MIME, hãy đi từ ngoài vào trong:

1. **Cấp message:** xác định người gửi/nhận hiển thị, tiêu đề, thời gian và `Content-Type` của body.
2. **Cấp multipart:** xác định các nhóm `mixed`, `alternative`, `related` và các boundary, từ đó hiểu quan hệ giữa các phần.
3. **Cấp part:** xác định loại dữ liệu (`text/plain`, `text/html`, `image/png`, `application/pdf`), charset, transfer encoding, disposition và Content-ID.

Trong một module Spring Mail, từ nhu cầu **“email hóa đơn có bản text, HTML, logo và PDF”**, ta có thể suy ra các phần MIME phải tồn tại và cách nhóm chúng; từ đó sử dụng `MimeMessageHelper` để tạo thông điệp đúng ngữ nghĩa. Khi cần chẩn đoán email hiển thị sai, việc đọc **cây MIME cùng header của từng part** thường hữu ích hơn nhiều so với chỉ xem chuỗi HTML ban đầu.

### Tài liệu chuẩn để tra cứu thêm

- **RFC 5322 — Internet Message Format:** cấu trúc message, header và body email.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** các header MIME, kiểu nội dung, multipart và cơ chế mã hóa.
- **RFC 2387 — The MIME Multipart/Related Content-type:** mô hình nội dung chính và các tài nguyên liên quan.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** mở rộng biểu diễn tham số và tên file có ký tự đặc biệt.
- **RFC 6532 — Internationalized Email Headers:** mở rộng liên quan đến header email quốc tế hóa.

Các RFC mô tả cấu trúc và giao thức; còn API `JavaMailSender`, `MimeMessage` và `MimeMessageHelper` giúp chuyển những nguyên tắc đó thành email thực tế trong ứng dụng Java/Spring.
