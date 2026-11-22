# Encoding nhất quán giữa các phần

Một email Spring Framework Mail có thể chứa nhiều phần MIME: bản văn bản thuần, bản HTML, ảnh inline, PDF đính kèm hoặc CSV. Các phần này có thể được tạo từ những nguồn dữ liệu khác nhau, nhưng khi ghép thành một message, ứng dụng cần bảo đảm mỗi phần được diễn giải đúng ký tự và đúng nội dung.

Với email tiếng Việt, lỗi encoding thường biểu hiện bằng các ký tự như **“Hóa đơn”** bị biến thành **“HÃ³a Ä‘Æ¡n”**, dấu tiếng Việt mất, tên người gửi hiển thị sai hoặc file CSV mở ra bị lỗi chữ. Nguyên nhân có thể nằm ở charset của body, cách chuyển String thành byte, header MIME, cách đọc template hoặc cách khai báo encoding cho attachment.

Cần phân biệt hai khái niệm:

- **Charset** cho biết cách ánh xạ byte thành ký tự, ví dụ UTF-8.
- **Content-Transfer-Encoding** cho biết byte của một MIME part được biểu diễn như thế nào để vận chuyển trong email, ví dụ quoted-printable hoặc Base64.

Hai khái niệm này giải quyết hai việc khác nhau. Base64 không thay thế UTF-8; UTF-8 cũng không tự quyết định MIME part được truyền bằng Base64 hay quoted-printable.

Trong Spring Mail, một cách triển khai dễ kiểm soát là dùng **UTF-8 nhất quán cho mọi phần văn bản**, để Spring/Jakarta Mail xử lý transfer encoding, đồng thời khai báo đúng MIME type cho attachment nhị phân. Với email có plain text và HTML, dùng **MimeMessageHelper.setText(plainText, htmlText)** để tạo hai biểu diễn của cùng nội dung.

## 1. Charset và Content-Transfer-Encoding khác nhau

Một email MIME có thể có part văn bản như:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 s=E1=BA=B5n s=C3=A0ng.
~~~

Trong ví dụ:

- **charset=UTF-8** nói rằng sau khi giải mã transfer encoding, các byte được giải mã thành văn bản theo UTF-8.
- **Content-Transfer-Encoding: quoted-printable** nói rằng byte của phần body được biểu diễn theo cú pháp quoted-printable.
- Các chuỗi như **=C3=A0** là cách biểu diễn byte trong quoted-printable; chúng không phải cách viết UTF-8 gốc của văn bản.

Một client thực hiện hai bước khái niệm:

~~~text
Nội dung trong MIME
       |
       v
Giải mã Content-Transfer-Encoding
       |
       v
Dãy byte
       |
       v
Giải mã theo charset UTF-8
       |
       v
Ký tự và văn bản hiển thị
~~~

Nếu charset bị khai báo sai, transfer encoding đúng vẫn có thể cho ra ký tự lỗi. Nếu transfer encoding bị diễn giải sai, client có thể hiển thị chuỗi mã hóa thay vì nội dung gốc.

### 1.1. Charset là gì?

Charset xác định cách biểu diễn ký tự thành byte và cách khôi phục byte thành ký tự.

Ví dụ, ký tự tiếng Việt **ơ** được biểu diễn bằng nhiều byte trong UTF-8. Nếu ứng dụng lấy byte UTF-8 rồi giải mã chúng bằng một charset khác, kết quả có thể sai.

Ví dụ Java:

~~~java
String text = "Đơn hàng đã được xác nhận";

byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);

String restored = new String(
        utf8Bytes,
        StandardCharsets.UTF_8
);
~~~

Hai phía dùng cùng UTF-8 nên chuỗi sau khi khôi phục giữ nguyên nội dung.

### 1.2. Content-Transfer-Encoding là gì?

MIME transfer encoding quyết định cách biểu diễn byte trong message. Các giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát | Trường hợp thường gặp |
| --- | --- | --- |
| **7bit** | Dữ liệu chỉ chứa byte 7-bit, tuân theo giới hạn dòng MIME | Nội dung ASCII phù hợp |
| **8bit** | Cho phép byte 8-bit trong body theo quy tắc MIME/transport | Một số transport hỗ trợ 8BITMIME |
| **quoted-printable** | Biểu diễn byte đặc biệt bằng dấu bằng và mã hex | Văn bản chủ yếu là ASCII, có một số ký tự ngoài ASCII |
| **base64** | Chuyển dữ liệu byte thành bảng ký tự Base64 | Ảnh, PDF và dữ liệu nhị phân; cũng có thể dùng cho text |

Transfer encoding không phải charset. Một phần văn bản UTF-8 có thể được truyền bằng quoted-printable hoặc Base64. Một ảnh PNG cũng có thể được truyền bằng Base64, nhưng ảnh không có charset UTF-8 như phần text.

### 1.3. Không tự Base64 hóa chuỗi trước khi đưa vào helper

Không nên làm:

~~~java
String text = "Hóa đơn đã sẵn sàng";

String base64 = Base64.getEncoder().encodeToString(
        text.getBytes(StandardCharsets.UTF_8)
);

helper.setText(base64, false);
~~~

Trong trường hợp này, body email chứa chính các ký tự Base64. Nếu helper tiếp tục tạo MIME, nó sẽ xử lý chuỗi Base64 đó như nội dung văn bản, không tự hiểu rằng cần giải mã để trở lại câu tiếng Việt.

Cách thông thường:

~~~java
helper.setText("Hóa đơn đã sẵn sàng", false);
~~~

Cung cấp String gốc và charset phù hợp cho helper. Jakarta Mail sẽ đảm nhiệm transfer encoding khi tuần tự hóa MIME message.

## 2. Vì sao cần encoding nhất quán giữa các phần?

Một email có thể chứa nhiều phần text khác nhau:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

Nếu plain text dùng UTF-8 nhưng HTML lại được tạo từ byte đọc theo Windows-1252, hai bản nội dung có thể hiển thị khác nhau. Người dùng chọn chế độ plain text sẽ thấy tiếng Việt đúng, trong khi chế độ HTML bị lỗi dấu.

Một message phức tạp hơn:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   └── image/png
└── application/pdf
~~~

Trong đó:

- **text/plain** là bản văn bản.
- **text/html** là bản HTML.
- **image/png** là dữ liệu nhị phân được HTML tham chiếu.
- **application/pdf** là tài liệu nhị phân đính kèm.

Encoding nhất quán không có nghĩa tất cả MIME part đều phải dùng cùng một Content-Transfer-Encoding. Điều cần thống nhất là **quy tắc ký tự của các phần văn bản** và **cách mỗi loại dữ liệu được mô tả đúng**.

| Part | Charset | Transfer encoding thường gặp |
| --- | --- | --- |
| text/plain | UTF-8 | quoted-printable, Base64 hoặc 7bit nếu nội dung phù hợp |
| text/html | UTF-8 | quoted-printable, Base64 hoặc dạng phù hợp với transport |
| text/csv attachment | UTF-8 nếu file được tạo bằng UTF-8 | quoted-printable hoặc Base64 tùy thư viện |
| application/pdf | Không khai báo charset văn bản thông thường | Base64 thường gặp |
| image/png | Không khai báo charset | Base64 thường gặp |
| image/jpeg | Không khai báo charset | Base64 thường gặp |

Ảnh và PDF là byte nhị phân. Không được giải mã chúng thành String UTF-8 chỉ để “đồng nhất encoding”. Hãy giữ nguyên byte và khai báo MIME type đúng.

## 3. Dùng UTF-8 cho plain text và HTML trong Spring Mail

Spring Framework cung cấp **MimeMessageHelper** để thiết lập nội dung MIME. Constructor nhận encoding cho phép ứng dụng xác định charset dùng khi tạo các phần văn bản.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);
~~~

Tham số thứ hai bật multipart; tham số thứ ba là encoding mặc định mà helper sử dụng cho nội dung và header phù hợp với API của nó.

Ví dụ:

~~~java
String plainText = """
        Xin chào An,

        Đơn hàng ORD-2026-001 đã được xác nhận.
        Tổng tiền: 500.000 đồng.

        Cảm ơn bạn.
        """;

String htmlText = """
        <!doctype html>
        <html lang="vi">
          <head>
            <meta charset="UTF-8">
            <title>Xác nhận đơn hàng</title>
          </head>
          <body>
            <h1>Xin chào An,</h1>
            <p>Đơn hàng <strong>ORD-2026-001</strong> đã được xác nhận.</p>
            <p>Tổng tiền: <strong>500.000 đồng</strong>.</p>
            <p>Cảm ơn bạn.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
~~~

**setText(plainText, htmlText)** cho phép gửi hai phiên bản thay thế của cùng nội dung. Khi helper được khởi tạo với UTF-8, nó dùng encoding đó để tạo các phần văn bản.

### 3.1. Ví dụ service hoàn chỉnh

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("orders@example.org");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng");

        String plainText = """
                Xin chào,

                Đơn hàng của bạn đã được xác nhận.
                Cảm ơn bạn đã mua sắm.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <head>
                    <meta charset="UTF-8">
                  </head>
                  <body>
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Cảm ơn bạn đã mua sắm.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
~~~

Các phần văn bản được tạo qua helper với cùng encoding UTF-8. Message có cả plain text và HTML, để client chọn cách hiển thị phù hợp.

Nếu message chỉ có plain text, có thể gọi **helper.setText(plainText, false)**. Nếu chỉ có HTML, gọi **helper.setText(htmlText, true)**. Khi cần hai biểu diễn, dùng overload nhận cả hai String.

### 3.2. Thẻ meta charset không thay thế MIME charset

Trong HTML có thể đặt:

~~~html
<meta charset="UTF-8">
~~~

Thẻ này là một chỉ dẫn bổ sung cho HTML. Nhưng email client trước hết xử lý MIME part và header **Content-Type**, ví dụ:

~~~text
Content-Type: text/html; charset=UTF-8
~~~

Nếu MIME header khai báo sai charset, thêm meta tag không phải cách đáng tin cậy để sửa lỗi. Hãy bảo đảm helper tạo phần HTML với UTF-8; meta tag chỉ giúp mô tả rõ hơn nội dung HTML.

## 4. Cấu trúc multipart/alternative và hai phiên bản nội dung

Khi email cần cả plain text và HTML, MIME subtype phù hợp là **multipart/alternative**.

Ví dụ cấu trúc:

~~~text
Content-Type: multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
~~~

Hai part biểu diễn cùng một thông điệp theo hai định dạng. Theo quy ước MIME, các alternative thường được sắp xếp từ dạng đơn giản hơn đến dạng phong phú hơn; client chọn phần cuối cùng mà nó hỗ trợ.

Vì vậy, khi dùng Spring:

~~~java
helper.setText(plainText, htmlText);
~~~

thứ tự tham số là **plain text trước, HTML sau**.

### 4.1. Hai bản cần nhất quán về ý nghĩa

Không nên để plain text nói “Đơn hàng đã thanh toán” trong khi HTML nói “Đang chờ thanh toán”. Hai phần là alternative của cùng một message, không phải hai nội dung nghiệp vụ độc lập.

Nên thống nhất mã đơn hàng, tên khách hàng, số tiền và đơn vị tiền tệ, trạng thái, thời gian, URL hành động hoặc hướng dẫn quan trọng, ngôn ngữ và locale.

Bố cục có thể khác nhau, nhưng dữ liệu và ý nghĩa phải nhất quán.

### 4.2. Không đặt nội dung chỉ có trong HTML nếu nó thiết yếu

Một số client hoặc người dùng có thể chọn plain text. Nếu mã xác nhận, thời hạn hoặc điều kiện quan trọng chỉ xuất hiện trong HTML, người đọc bản text sẽ thiếu thông tin.

Hãy bảo đảm bản plain text truyền đạt đầy đủ nội dung nghiệp vụ. HTML có thể bổ sung màu sắc, bảng và hình ảnh, nhưng không được là nơi duy nhất chứa thông tin cần thiết.

### 4.3. Tạo hai phiên bản từ cùng một model

Một cách tốt là xây dựng model một lần rồi render hai template:

~~~text
OrderMailData
      |
      +----> plain-text template
      |
      +----> HTML template
~~~

Ví dụ:

~~~java
public record OrderMailData(
        String customerName,
        String orderNumber,
        String totalAmount,
        String statusText
) {}
~~~

Cả hai renderer nhận cùng một DTO. Điều này giảm nguy cơ một bản được cập nhật mà bản còn lại quên sửa.

## 5. Cấu hình default encoding của Spring Boot

Với Spring Boot Mail, có thể đặt encoding mặc định trong application properties:

~~~properties
spring.mail.default-encoding=UTF-8
~~~

Hoặc YAML:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

Thuộc tính này cấu hình default encoding của mail sender do Boot quản lý. Tuy nhiên, nếu code tạo **MimeMessageHelper** thủ công, hãy truyền encoding tường minh khi khởi tạo:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

Cách này làm ý định của code rõ ràng, không phụ thuộc vào việc người đọc phải truy tìm default encoding từ cấu hình triển khai.

### 5.1. application.properties và application.yml tương đương

Properties:

~~~properties
spring.mail.default-encoding=UTF-8
~~~

YAML:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

Cả hai khai báo cùng một thuộc tính Boot. Không cần khai báo thêm một key riêng cho plain text và một key khác cho HTML nếu ứng dụng chủ động dùng chung encoding UTF-8.

### 5.2. Tránh mỗi nơi một charset

Một cấu hình dễ gây lỗi:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "ISO-8859-1"
);

String html = loadTemplateAsUtf8();
helper.setText(plainText, html);
~~~

Template đã được đọc thành String theo UTF-8, nhưng helper lại khai báo charset khác. Khi byte được tạo theo charset helper, các ký tự không thể biểu diễn trong ISO-8859-1 có thể bị thay thế hoặc lỗi.

Với nội dung tiếng Việt, nên dùng UTF-8 xuyên suốt từ file template, model, helper cho tới MIME part.

## 6. Đọc template từ file bằng UTF-8

Một nguồn lỗi phổ biến là đọc template bằng charset mặc định của máy chạy. Hãy chỉ định charset rõ ràng:

~~~java
String template = Files.readString(
        path,
        StandardCharsets.UTF_8
);
~~~

Nếu template nằm trong classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("templates/mail/order.html");

String html;

try (InputStream input = resource.getInputStream()) {
    html = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
    );
}
~~~

Cách này đọc byte từ resource và giải mã rõ ràng bằng UTF-8. Sau đó truyền String cho helper đã được khởi tạo với UTF-8.

### 6.1. Đảm bảo file template thực sự được lưu UTF-8

Khai báo charset trong code không thể sửa một file đã được lưu sai encoding. Nếu editor lưu template bằng Windows-1258 nhưng ứng dụng đọc như UTF-8, nội dung vẫn lỗi.

Cần thống nhất:

- File HTML/TXT được lưu UTF-8.
- Editor/IDE dùng UTF-8.
- Build/package không chuyển đổi encoding ngoài ý muốn.
- Code đọc file chỉ định UTF-8.
- Helper tạo MIME part với UTF-8.

### 6.2. Encoding của source Java

Nếu source code có literal tiếng Việt:

~~~java
String subject = "Thông báo thanh toán";
~~~

thì file .java cũng cần được compiler đọc đúng encoding. Có thể cấu hình encoding của source trong Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Đây là cấu hình cho source Java, khác với charset của email MIME. Một ứng dụng có thể compile source đúng nhưng vẫn tạo email sai nếu helper hoặc template reader dùng charset khác.

## 7. Encoding cho Subject và tên hiển thị người gửi

Body không phải phần duy nhất có thể chứa ký tự Unicode. Email header cũng có thể có Subject tiếng Việt, display name người gửi và display name người nhận.

Ví dụ:

~~~java
helper.setSubject("Hóa đơn điện tử tháng 11");
~~~

Khi helper được khởi tạo với UTF-8, nó có thể dùng encoding này khi đặt subject theo API của Spring.

Tên hiển thị:

~~~java
helper.setFrom(
        "billing@example.org",
        "Phòng Kế toán"
);
~~~

Đối với tên cá nhân hoặc display name Unicode, helper có overload nhận tên hiển thị và dùng encoding đã cấu hình. Cũng có thể tạo **InternetAddress** với charset tường minh:

~~~java
InternetAddress from = new InternetAddress(
        "billing@example.org",
        "Phòng Kế toán",
        StandardCharsets.UTF_8.name()
);

helper.setFrom(from);
~~~

### 7.1. Header không phải body text

Header Subject không nằm trong MIME body part text/plain hoặc text/html. Vì vậy, charset trong header được xử lý theo quy tắc MIME header encoding riêng, thường là encoded-word theo RFC 2047 đối với nội dung Unicode trong header.

Không thể sửa Subject bị lỗi chỉ bằng cách thêm thẻ meta charset vào HTML. Hãy dùng API header của Spring/Jakarta Mail với encoding phù hợp.

### 7.2. Địa chỉ email quốc tế hóa là vấn đề khác

UTF-8 cho body và display name không tự động bảo đảm mọi địa chỉ email có ký tự Unicode ở local-part đều được SMTP server hỗ trợ. Địa chỉ quốc tế hóa và SMTPUTF8 là một vấn đề giao thức riêng.

Với hệ thống cần hỗ trợ địa chỉ email quốc tế hóa, phải kiểm tra khả năng của SMTP provider và thư viện/transport. Không suy ra hỗ trợ SMTPUTF8 chỉ từ việc body dùng UTF-8.

## 8. Encoding của filename và attachment

Tên file đính kèm cũng có thể chứa Unicode:

~~~java
helper.addAttachment(
        "Hóa đơn-2026.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Filename được truyền qua API, sau đó thư viện mail xử lý việc biểu diễn tham số header theo cơ chế MIME phù hợp. Không tự nối raw Content-Disposition để cố ép encoding.

### 8.1. Filename và nội dung file là hai encoding riêng

Ví dụ attachment PDF:

- Filename có thể là Unicode và cần mã hóa trong MIME header.
- Nội dung PDF là dữ liệu nhị phân, không có charset UTF-8.
- Content-Transfer-Encoding của part có thể là Base64.

Với CSV:

- Filename là metadata header.
- Nội dung CSV có thể được tạo thành byte UTF-8.
- MIME type có thể khai báo charset UTF-8.
- Transfer encoding được xử lý riêng.

Ví dụ:

~~~java
byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "Báo cáo đơn hàng.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

### 8.2. Không chuyển PDF hoặc ảnh thành String UTF-8

Sai:

~~~java
String pdfText = new String(pdfBytes, StandardCharsets.UTF_8);
byte[] changedBytes = pdfText.getBytes(StandardCharsets.UTF_8);
~~~

PDF là dữ liệu nhị phân. Việc giải mã như UTF-8 có thể làm hỏng byte không hợp lệ hoặc thay đổi dữ liệu.

Đúng:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Giữ byte nguyên bản và khai báo MIME type tương ứng.

### 8.3. CSV cần charset rõ ràng

Nếu tạo CSV bằng Java String:

~~~java
String csv = """
        order_id,customer,total
        ORD-001,Nguyễn An,500000
        """;

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
~~~

Thì nội dung byte đã được mã hóa UTF-8. Khi thêm attachment, khai báo:

~~~java
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Một số spreadsheet có cách nhận diện UTF-8 khác nhau. Nếu cần hỗ trợ phần mềm cụ thể, hãy thử nghiệm cách mở file; không tự thêm BOM nếu chưa xác định nó cần thiết cho hợp đồng dữ liệu.

## 9. Encoding của inline resource

Inline resource cũng là MIME part, nhưng không phải tất cả inline resource đều là văn bản.

Ví dụ logo PNG:

~~~java
helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

PNG là dữ liệu nhị phân. Không khai báo charset UTF-8 cho image/png theo cách áp dụng cho text/html. MIME transfer encoding có thể là Base64; sau khi giải mã, byte phải giữ nguyên nội dung PNG.

Nếu inline resource là nội dung văn bản, chẳng hạn một part text hoặc CSS trong cấu trúc MIME đặc thù, khi đó charset có thể có ý nghĩa. Nhưng đối với ảnh PNG/JPEG thông thường, không có charset văn bản.

### 9.1. Content-ID không liên quan charset

Content-ID chỉ định danh part:

~~~text
Content-ID: <companyLogo>
~~~

HTML tham chiếu:

~~~html
<img src="cid:companyLogo">
~~~

Charset của HTML và byte của ảnh là các vấn đề độc lập. Việc đổi Content-ID không sửa lỗi dấu tiếng Việt; việc đổi charset không sửa một Content-ID không khớp.

## 10. Một ví dụ đầy đủ với plain text, HTML, inline image và PDF

Một email giao dịch có thể gồm:

- Plain text cho client không hiển thị HTML.
- HTML cho bố cục phong phú.
- Logo inline được tham chiếu bằng CID.
- PDF attachment để người nhận tải.

Cấu trúc MIME khái niệm:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   │       └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Ví dụ code:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailer {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            byte[] invoicePdf
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận hóa đơn điện tử");

        String plainText = """
                Xin chào,

                Hóa đơn điện tử của bạn đã sẵn sàng.
                Vui lòng xem file PDF đính kèm.

                Trân trọng,
                Phòng Kế toán
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <head>
                    <meta charset="UTF-8">
                    <title>Xác nhận hóa đơn</title>
                  </head>
                  <body>
                    <img
                      src="cid:companyLogo"
                      alt="Logo công ty"
                      width="160">
                    <h1>Hóa đơn điện tử đã sẵn sàng</h1>
                    <p>Xin chào,</p>
                    <p>Vui lòng xem file PDF đính kèm.</p>
                    <p>Trân trọng,<br>Phòng Kế toán</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        helper.addInline(
                "companyLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "Hoa-don-dien-tu.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Ví dụ dùng tên PDF ASCII để giảm khác biệt hiển thị filename giữa các client. Có thể dùng tên Unicode khi yêu cầu sản phẩm cần giữ tiếng Việt và đã kiểm tra khả năng tương thích.

### 10.1. Encoding của từng phần trong ví dụ

| Thành phần | Nội dung | Cách xử lý encoding |
| --- | --- | --- |
| Subject | Xác nhận hóa đơn điện tử | Helper dùng UTF-8 cho header phù hợp |
| Display name From | Phòng Kế toán | Helper/InternetAddress mã hóa tên hiển thị |
| text/plain | Tiếng Việt | Charset UTF-8 |
| text/html | Tiếng Việt và markup | Charset UTF-8 |
| Logo PNG | Byte ảnh | Binary, không charset UTF-8 |
| PDF | Byte tài liệu | Binary, không charset UTF-8 |
| PDF filename | Hoa-don-dien-tu.pdf | Tham số header filename do thư viện biểu diễn |

Từng part có cách xử lý riêng nhưng toàn bộ message vẫn nhất quán về ý nghĩa và encoding.

## 11. Đặt encoding trong Spring Boot và JavaMail properties

Với Spring Boot, cấu hình:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
    host: \${SMTP_HOST}
    port: \${SMTP_PORT:587}
    username: \${SMTP_USERNAME}
    password: \${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
~~~

Trong đó:

- **spring.mail.default-encoding** là default encoding cho mail sender do Boot cấu hình.
- **spring.mail.host/port/username/password** xác định SMTP connection.
- **spring.mail.properties[...]** chuyển JavaMail properties cho SMTP transport.
- Constructor MimeMessageHelper có thể nhận UTF-8 rõ ràng khi tạo message.

Không nhầm **mail.smtp.auth** hoặc **mail.smtp.starttls.enable** với charset. Chúng là tùy chọn của SMTP transport, không điều khiển cách byte body được giải mã thành ký tự.

### 11.1. Có cần đặt mail.mime.charset không?

Jakarta Mail có các thiết lập mặc định MIME charset trong một số ngữ cảnh, nhưng với ứng dụng Spring Mail, cách rõ ràng nhất là:

1. Dùng String Unicode trong ứng dụng.
2. Đọc template bằng UTF-8.
3. Khởi tạo MimeMessageHelper với UTF-8.
4. Dùng API helper cho body, subject và display name.
5. Khai báo charset cho các text attachment khi tạo byte.
6. Để thư viện quản lý Content-Transfer-Encoding.

Không nên thêm một JavaMail property toàn cục mà chưa hiểu phạm vi tác động. Một thiết lập global có thể ảnh hưởng tới nhiều message hoặc phần nội dung mà ứng dụng không dự định thay đổi.

### 11.2. Không nhầm encoding của JVM với encoding email

JVM chạy trên môi trường có default charset khác không nhất thiết làm mọi email lỗi nếu code chỉ định UTF-8 đúng. Ngược lại, JVM dùng UTF-8 mặc định cũng không bảo đảm mọi nguồn dữ liệu đều được đọc đúng.

Hãy kiểm soát encoding tại các ranh giới: đọc file, chuyển String thành byte[], tạo MIME part, tạo header và đọc CSV hoặc dữ liệu text từ nguồn ngoài.

## 12. Các kiểu lỗi encoding phổ biến

### 12.1. Mojibake: UTF-8 bị đọc bằng charset khác

Ví dụ nội dung gốc:

~~~text
Hóa đơn đã sẵn sàng
~~~

Nếu byte UTF-8 bị diễn giải nhầm thành Windows-1252 hoặc một charset không phù hợp, kết quả có thể thành:

~~~text
HÃ³a Ä‘Æ¡n Ä‘Ã£ sẵn sÃ ng
~~~

Đây là dấu hiệu byte và charset không khớp. Hãy tìm nơi byte được tạo và nơi byte được giải mã, thay vì chỉ sửa CSS hoặc HTML.

### 12.2. Double encoding

Một chuỗi đã được chuyển thành dạng mã hóa nhưng lại bị mã hóa thêm lần nữa có thể dẫn đến nội dung sai.

Ví dụ không nên tự tạo Base64 cho body rồi đưa vào setText như văn bản. Cũng không nên chuyển String UTF-8 thành byte, rồi giải mã byte bằng charset khác trước khi gửi.

Hãy giữ String Unicode trong tầng ứng dụng và để helper chuyển đổi theo encoding đã cấu hình.

### 12.3. Plain text đúng nhưng HTML sai

Nguyên nhân có thể:

- Plain text và HTML được đọc từ file với charset khác nhau.
- Một template có BOM hoặc byte không hợp lệ.
- HTML được tạo từ dữ liệu đã bị mojibake trước đó.
- Hai template dùng hai nguồn model khác nhau.
- MIME part HTML khai báo charset không đúng.

Kiểm tra riêng nội dung String trước khi gọi helper và charset trong MIME header của từng part.

### 12.4. HTML đúng nhưng Subject sai

Subject là header, không phải HTML body. Kiểm tra helper encoding, API setSubject và cách display name được tạo. Meta charset trong HTML không giải quyết được header.

### 12.5. CSV mở bằng Excel bị lỗi dấu

Có thể do byte CSV không phải UTF-8, charset không được khai báo hoặc phần mềm nhận diện file theo quy tắc riêng. Tạo byte rõ ràng:

~~~java
byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);
~~~

Và khai báo:

~~~java
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Sau đó kiểm tra với phần mềm mà người nhận sử dụng. Nếu cần BOM hoặc một quy ước CSV riêng, quyết định theo khả năng tương thích thực tế, không thêm ngẫu nhiên.

### 12.6. Emoji hoặc ký tự ngoài Basic Multilingual Plane bị lỗi

UTF-8 có thể biểu diễn emoji và các ký tự Unicode ngoài BMP. Tuy nhiên, toàn bộ chuỗi phải được giữ nguyên ở mọi bước. Một thư viện, database hoặc template có thể cắt chuỗi theo số UTF-16 code unit thay vì code point và làm hỏng surrogate pair.

Không cắt String ở giữa surrogate pair. Nếu cần giới hạn độ dài, dùng API hiểu code point hoặc grapheme phù hợp với nghiệp vụ.

## 13. Content-Transfer-Encoding nên để thư viện lựa chọn

Một câu hỏi thường gặp: có nên tự đặt Content-Transfer-Encoding là Base64 cho mọi phần của email hay không?

Thông thường **không cần**. Jakarta Mail có thể chọn cách transfer encoding phù hợp khi tạo MIME message. Nếu tự đặt header không đúng với byte thực tế, client có thể giải mã sai.

### 13.1. Text part

Văn bản có thể dùng quoted-printable, Base64 hoặc encoding phù hợp khác. Lựa chọn phụ thuộc nội dung, MIME provider và transport.

Quoted-printable thường thuận tiện khi văn bản chủ yếu là ASCII nhưng có một số ký tự ngoài ASCII. Base64 cũng có thể dùng cho text, nhưng thường khó đọc khi quan sát raw message.

### 13.2. Binary part

Ảnh và PDF thường dùng Base64 vì dữ liệu nhị phân có thể chứa byte không phù hợp để truyền trực tiếp như văn bản 7-bit.

Không giải mã ảnh/PDF thành String để áp dụng UTF-8. Hãy giữ byte nguyên bản và để MIME library xử lý transfer encoding.

### 13.3. 8bit và SMTP transport

Một MIME part có thể dùng 8bit trong những điều kiện phù hợp, nhưng việc truyền 8bit còn phụ thuộc khả năng SMTP server và các extension như **8BITMIME**. Không nên tự ép 8bit mà không xét transport.

Để gửi email tiếng Việt, không cần tự cấu hình SMTP sang 8bit chỉ vì có ký tự Unicode. Dùng charset UTF-8 và để Jakarta Mail/transport xử lý cách biểu diễn phù hợp.

## 14. Đảm bảo cùng một dữ liệu cho plain text và HTML

Một cách tốt là xây dựng model một lần:

~~~java
public record OrderMailData(
        String customerName,
        String orderNumber,
        String total,
        String status
) {}
~~~

Sau đó render hai template:

~~~java
String plainText = plainRenderer.render(data);
String htmlText = htmlRenderer.render(data);

helper.setText(plainText, htmlText);
~~~

Cả hai renderer nên dùng cùng locale và cùng dữ liệu đầu vào. Nếu định dạng tiền tệ hoặc ngày giờ được tạo riêng trong từng template, hãy dùng một formatter/service dùng chung hoặc truyền giá trị đã định dạng vào model.

### 14.1. Locale và charset là hai vấn đề khác nhau

**UTF-8** giúp biểu diễn ký tự. **Locale** quyết định quy tắc hiển thị ngôn ngữ, số, ngày giờ và tiền tệ.

Ví dụ cùng một giá trị số có thể được trình bày khác nhau theo locale. Việc cả hai part dùng UTF-8 không tự làm cho số tiền hoặc ngày tháng có cùng định dạng.

Hãy chọn locale rõ ràng cho message và dùng cùng quy tắc trong plain text lẫn HTML.

### 14.2. Tránh render hai lần với dữ liệu thay đổi

Nếu plain text và HTML được tạo bằng hai lần truy vấn database độc lập, dữ liệu có thể thay đổi giữa hai lần đọc. Tốt hơn là lấy một snapshot/model rồi render cả hai từ cùng dữ liệu.

Điều này giúp nội dung hai alternative đồng nhất ngay cả khi hệ thống có cập nhật đồng thời.

## 15. Kiểm tra raw MIME để xác định encoding

Khi email hiển thị sai, hãy quan sát raw MIME của message trong SMTP capture server hoặc công cụ test.

Ví dụ phần text/plain đúng:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Và HTML:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Điều cần xác nhận:

- Charset của các part text là UTF-8.
- Transfer encoding phù hợp với dữ liệu và được giải mã đúng.
- HTML và plain text chứa cùng thông tin nghiệp vụ.
- Attachment binary có MIME type đúng.
- Subject/display name được mã hóa header phù hợp.
- Filename Unicode được thư viện biểu diễn hợp lệ nếu có.

Không cần yêu cầu mọi part có cùng Content-Transfer-Encoding. Điều đó không phải mục tiêu của encoding nhất quán.

### 15.1. Quan sát Content-Type

Nếu raw message cho thấy:

~~~text
Content-Type: text/html; charset=ISO-8859-1
~~~

nhưng body thực được tạo với UTF-8, đây là dấu hiệu không khớp.

Nếu header là UTF-8 nhưng byte thực đã bị hỏng từ trước khi helper nhận String, việc đổi header sẽ không khôi phục được nội dung ban đầu.

### 15.2. Đừng chỉ nhìn raw message chưa giải mã

Nếu transfer encoding là quoted-printable hoặc Base64, raw body sẽ không giống văn bản người dùng đọc. Đó là bình thường. Cần giải mã transfer encoding trước rồi mới giải mã charset để đánh giá kết quả.

Một chuỗi như **=E1=BB...** có thể là quoted-printable hợp lệ của byte UTF-8, không phải lỗi. Tương tự, một đoạn Base64 trong part PDF không có nghĩa file bị mã hóa bảo mật.

## 16. Kiểm thử encoding trong ứng dụng Spring

### 16.1. Test nội dung String trước khi dựng MIME

Dùng một chuỗi có đủ ký tự tiếng Việt và ký tự đặc biệt:

~~~java
String expected =
        "Đơn hàng của Nguyễn An đã thanh toán: 500.000 đồng.";

assertEquals(expected, renderedPlainText);
~~~

Điều này giúp phân biệt lỗi template/model với lỗi MIME serialization.

### 16.2. Test MIME headers và body parts

Sau khi tạo message, có thể kiểm tra Content-Type và nội dung các part bằng Jakarta Mail API. Với multipart/alternative, lấy từng BodyPart và kiểm tra charset được khai báo cũng như nội dung sau khi thư viện giải mã.

Không nên test bằng cách so sánh một chuỗi raw MIME hoàn chỉnh, vì boundary, transfer encoding và thứ tự header có thể thay đổi theo provider.

### 16.3. Test attachment text và binary riêng

Với CSV, xác nhận byte sau khi giải mã đúng UTF-8. Với PDF hoặc PNG, so sánh byte gốc sau khi MIME transfer encoding được giải mã; không chuyển byte thành String.

### 16.4. Test trên email client mục tiêu

SMTP capture server giúp xác nhận message được tạo đúng. Nhưng email client có thể xử lý HTML, font và ảnh khác nhau. Hãy kiểm tra cả bản plain text, bản HTML, Subject và display name, filename Unicode nếu dùng, CSV mở bằng phần mềm mục tiêu, ảnh inline và attachment.

## 17. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tiếng Việt thành mojibake | Byte UTF-8 bị giải mã bằng charset khác | Dùng UTF-8 từ lúc đọc nguồn tới MIME |
| Plain text đúng, HTML sai | Hai template có encoding hoặc dữ liệu khác nhau | Đọc cả hai template bằng UTF-8 và render từ cùng model |
| HTML đúng, Subject sai | Header encoding khác body encoding | Dùng helper/InternetAddress với UTF-8 |
| Subject đúng, filename lỗi | MIME parameter encoding hoặc client khác nhau | Dùng API attachment, filename hợp lệ và test client |
| CSV mở lỗi dấu | Byte CSV hoặc charset khai báo không đúng | Tạo byte bằng UTF-8 và khai báo charset |
| PDF/PNG bị hỏng | Byte binary bị chuyển qua String hoặc encode sai | Giữ byte nguyên bản, MIME type đúng |
| Raw MIME có chuỗi =C3... | Quoted-printable | Bình thường nếu giải mã ra UTF-8 đúng |
| Body hiển thị Base64 | Ứng dụng tự Base64 hóa rồi gọi setText | Truyền String gốc, để MIME library xử lý |
| HTML meta UTF-8 nhưng vẫn lỗi | MIME part charset sai hoặc byte đã hỏng trước đó | Kiểm tra Content-Type và bước đọc template |
| Emoji bị thay thế | Nguồn, database hoặc thao tác cắt chuỗi làm mất Unicode | Kiểm tra từng ranh giới dữ liệu và surrogate pair |
| SMTP từ chối 8bit | Transport/server không hỗ trợ cách truyền đã ép | Để thư viện chọn transfer encoding phù hợp |
| Mỗi part dùng charset khác | Helper hoặc template được cấu hình không thống nhất | Dùng một quy ước UTF-8 cho mọi text part |

## 18. Quy trình thực hành để giữ encoding nhất quán

Một quy trình đơn giản:

1. **Nguồn dữ liệu:** giữ String Unicode trong ứng dụng; không chuyển đổi charset tùy tiện.
2. **Template:** lưu HTML và plain text ở UTF-8.
3. **Đọc template:** chỉ định StandardCharsets.UTF_8.
4. **Model:** tạo một DTO dùng chung cho cả hai template.
5. **MimeMessageHelper:** khởi tạo với UTF-8.
6. **Body:** dùng setText(plainText, htmlText) khi cần alternative.
7. **Header:** đặt Subject/display name qua API có encoding phù hợp.
8. **Attachment text:** tạo byte[] theo UTF-8 và khai báo charset trong MIME type.
9. **Attachment binary:** giữ nguyên byte[]; không giải mã thành String.
10. **Transport:** để thư viện mail xử lý Content-Transfer-Encoding.
11. **Quan sát:** kiểm tra raw MIME đã giải mã và hiển thị trên client mục tiêu.

~~~text
Template UTF-8 -----------+
                         |
Model chung --------------+--> Plain text (UTF-8) --+
                         |                          |
                         +--> HTML (UTF-8) ----------+--> MimeMessage
                                                    |
Binary PDF/PNG -------------------------------------+
                                                    |
Subject/display name -------------------------------+
                                                    |
                                                    v
                                            Jakarta Mail MIME
                                                    |
                                                    v
                                                SMTP send
~~~

Quy trình này không đòi hỏi mọi part dùng cùng transfer encoding. Nó bảo đảm các nguồn văn bản có quy tắc charset rõ ràng và dữ liệu nhị phân không bị xử lý nhầm như text.

## 19. Câu hỏi thường gặp

**1. UTF-8 và Base64 có giống nhau không?**

Không. UTF-8 là charset để ánh xạ ký tự thành byte. Base64 là transfer encoding để biểu diễn byte bằng ký tự ASCII trong MIME. Một phần text UTF-8 có thể được truyền bằng Base64.

**2. Có cần dùng cùng Content-Transfer-Encoding cho plain text và HTML không?**

Không. Hai part có thể dùng transfer encoding khác nhau. Điều quan trọng là mỗi part được khai báo và giải mã đúng; charset của các phần văn bản nên thống nhất theo quy ước ứng dụng.

**3. Vì sao cần setText(plainText, htmlText)?**

Để gửi hai biểu diễn thay thế của cùng nội dung. Plain text phục vụ client không dùng HTML; HTML cung cấp bố cục phong phú. Cả hai nên chứa cùng dữ liệu nghiệp vụ.

**4. Có cần thêm meta charset UTF-8 trong HTML không?**

Có thể thêm như một chỉ dẫn cho HTML, nhưng nó không thay thế MIME header **Content-Type: text/html; charset=UTF-8**. Hãy cấu hình charset đúng khi tạo MIME part.

**5. spring.mail.default-encoding có đủ không?**

Nó đặt default encoding cho mail sender do Spring Boot cấu hình. Nếu code tạo MimeMessageHelper trực tiếp, truyền UTF-8 tường minh vào constructor giúp ý định rõ ràng.

**6. Có nên tự đặt Content-Transfer-Encoding là Base64 không?**

Thông thường không. Hãy cung cấp String hoặc byte gốc và để Jakarta Mail chọn cách biểu diễn phù hợp. Chỉ can thiệp khi có yêu cầu MIME/transport cụ thể và đã kiểm tra kết quả.

**7. Có cần charset UTF-8 cho PDF không?**

Không. PDF là dữ liệu nhị phân. Giữ byte gốc và dùng MIME type application/pdf. Charset chỉ áp dụng cho nội dung văn bản thích hợp.

**8. CSV có cần charset không?**

Nếu nội dung CSV được mã hóa UTF-8, khai báo **text/csv; charset=UTF-8** giúp mô tả dữ liệu. Cũng cần kiểm tra phần mềm người nhận dùng để mở file.

**9. Vì sao Subject vẫn lỗi khi body đúng?**

Subject là header riêng, không phải body part. Dùng API Spring/Jakarta Mail với encoding UTF-8 cho subject và display name; meta tag HTML không ảnh hưởng header.

**10. Filename tiếng Việt có được hỗ trợ không?**

Các API MIME có cơ chế biểu diễn filename Unicode, nhưng client khác nhau có thể xử lý khác. Truyền filename qua addAttachment và thử nghiệm trên client mục tiêu; không tự ghép raw header.

**11. Vì sao raw MIME có ký tự =E1 hoặc chuỗi Base64?**

Đó có thể là Content-Transfer-Encoding hợp lệ. Giải mã transfer encoding trước, rồi giải mã byte theo charset mới biết văn bản hiển thị thực tế.

**12. SMTP có cần bật 8BITMIME để gửi tiếng Việt không?**

Không nhất thiết. Charset UTF-8 và transfer encoding là hai lớp khác nhau. Jakarta Mail/transport có thể chọn quoted-printable hoặc Base64 phù hợp mà không cần ứng dụng ép 8bit.

**13. Emoji có gửi được trong email UTF-8 không?**

Có, nếu toàn bộ chuỗi, template, MIME part và client giữ được Unicode. Cần tránh cắt chuỗi làm hỏng surrogate pair và thử nghiệm trên client mục tiêu.

## 20. Ghi nhớ về encoding nhất quán giữa các phần

**Charset** xác định cách byte được chuyển thành ký tự; **Content-Transfer-Encoding** xác định cách byte được biểu diễn khi vận chuyển trong MIME. Hai lớp này không thay thế nhau. Với email tiếng Việt, hãy dùng UTF-8 nhất quán cho plain text, HTML, template, subject và display name; để Spring/Jakarta Mail xử lý transfer encoding cho từng part.

Khi gửi nhiều định dạng, **multipart/alternative** chứa plain text và HTML là hai cách biểu diễn cùng nội dung. Dùng **MimeMessageHelper.setText(plainText, htmlText)** với helper được khởi tạo bằng UTF-8. Ảnh và PDF là dữ liệu nhị phân, không cần charset UTF-8; giữ nguyên byte và khai báo MIME type đúng. CSV hoặc text attachment cần được tạo byte theo charset đã chọn và khai báo charset tương ứng.

Hãy kiểm soát encoding tại mọi ranh giới: đọc template, chuyển String thành byte, tạo MIME part, đặt header và tạo attachment. Không tự Base64 hóa body trước khi gọi helper, không chuyển file nhị phân thành String và không dựa vào meta charset để sửa MIME header sai. Kiểm tra raw MIME sau khi giải mã và xem email trên các client mục tiêu để xác nhận nội dung hiển thị nhất quán.
