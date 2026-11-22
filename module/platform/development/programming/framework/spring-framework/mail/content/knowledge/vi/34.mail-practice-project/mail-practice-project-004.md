# Thêm attachment và inline image từ classpath

## 1. Mục tiêu của dự án thực hành

Trong **Spring Framework Mail**, một email không nhất thiết chỉ có vài dòng văn bản. Ứng dụng thường phải gửi thư có:

- **Nội dung plain text** để người nhận vẫn đọc được khi email client không hiển thị HTML.
- **Nội dung HTML** với bố cục, màu sắc và liên kết.
- **Inline image** như logo hoặc hình minh họa được hiển thị *bên trong* HTML, không phải chỉ là một đường dẫn đến ảnh trên Internet.
- **Attachment** như PDF hướng dẫn, hóa đơn mẫu hoặc biểu mẫu mà người nhận có thể tải xuống.

Bài thực hành **“Thêm attachment và inline image từ classpath”** xây dựng một dịch vụ gửi email theo cấu trúc:

~~~text
Spring Boot application
    |
    +-- src/main/resources/mail/images/brand-logo.png
    +-- src/main/resources/mail/attachments/welcome-guide.pdf
    |
    v
ClasspathResource
    |
    v
MimeMessage + MimeMessageHelper
    |
    +-- plain text
    +-- HTML <img src="cid:brandLogo">
    +-- inline PNG (Content-ID: brandLogo)
    +-- attached PDF
    |
    v
JavaMailSender
    |
    v
SMTP server / test inbox
~~~

Sau bài này, người học cần hiểu được:

1. Phân biệt **attachment** và **inline resource**.
2. Đặt file đúng thư mục **classpath** để đọc được cả khi chương trình được đóng gói thành JAR.
3. Tạo email MIME với **MimeMessageHelper** và cấu hình multipart phù hợp.
4. Gắn một file PDF từ **ClassPathResource** bằng **addAttachment(...)**.
5. Gắn hình PNG từ **ClassPathResource** bằng **addInline(...)**, rồi tham chiếu trong HTML bằng **cid:**.
6. Hiểu vì sao **Content-ID**, **Content-Type**, thứ tự thêm inline resource và MIME structure ảnh hưởng việc hiển thị.
7. Tổ chức service, cấu hình SMTP thử nghiệm, kiểm thử các MIME parts và xử lý lỗi an toàn.
8. Biết giới hạn của ví dụ classpath khi chuyển sang file được tạo động hoặc dữ liệu riêng của từng người dùng.

Trong ví dụ, mọi tên miền và địa chỉ dùng dạng **example.com/example.net** hoặc host giả lập. Không gửi thư tới hộp thư thật trong quá trình học nếu chưa có quyền.

## 2. Phân biệt attachment với inline image

Hai resource có thể cùng là file PNG/PDF nhưng cách thể hiện trong MIME khác nhau.

| Tiêu chí | Attachment | Inline image |
|---|---|---|
| Mục tiêu | File đính kèm để tải/lưu/mở | Tài nguyên hiển thị trong phần HTML |
| Spring API | **MimeMessageHelper.addAttachment(...)** | **MimeMessageHelper.addInline(...)** |
| MIME disposition thường gặp | **attachment** | **inline** |
| Liên kết với HTML | Không cần | Qua **Content-ID** và **cid:** |
| Ví dụ | welcome-guide.pdf | brand-logo.png |
| Hiển thị trong mail client | Tên file, nút tải xuống | Hình hiển thị bên trong thư nếu client hỗ trợ |
| Có thể hiện như file đính kèm? | Có | Có thể, tùy email client |
| Có được nhúng dưới dạng base64 trong HTML? | Không cần | Không; file là một MIME part riêng |

Ví dụ HTML:

~~~html
<h1>Chào mừng đến với ứng dụng</h1>
<p>Logo được đính kèm trong MIME và hiển thị ngay dưới đây:</p>
<img src="cid:brandLogo" alt="Logo" width="180">
<p>Tài liệu hướng dẫn được gửi dưới dạng file PDF đính kèm.</p>
~~~

Trong đó:

- **cid:brandLogo** tham chiếu một MIME part có **Content-ID** tương ứng.
- Hình không phải tải từ URL công khai như **https://.../logo.png**.
- File PDF là một part độc lập với Content-Disposition attachment.

**Điểm dễ nhầm:** một hình dùng **addAttachment("logo.png", ...)** sẽ không tự hiện vào vị trí **img src="cid:brandLogo"**. Muốn dùng **cid:** phải thêm inline resource với đúng Content-ID.

## 3. Classpath là gì trong ví dụ này?

Trong dự án Spring Boot tiêu chuẩn:

~~~text
src/main/resources/
    application.yml
    mail/
        images/
            brand-logo.png
        attachments/
            welcome-guide.pdf
~~~

Những file trong **src/main/resources** thường được build tool copy vào **classpath** của ứng dụng.

Khi chạy trong IDE, resource có thể được truy cập từ thư mục build classes:

~~~text
target/classes/mail/images/brand-logo.png
~~~

hoặc:

~~~text
build/resources/main/mail/images/brand-logo.png
~~~

Khi đóng gói Spring Boot executable JAR, chúng có thể nằm bên trong archive:

~~~text
BOOT-INF/classes/mail/images/brand-logo.png
BOOT-INF/classes/mail/attachments/welcome-guide.pdf
~~~

Vì vậy **classpath không đồng nghĩa với một thư mục file vật lý mà mọi môi trường đều truy cập được qua java.io.File**.

Để truy cập resource một cách portable, dùng:

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

ClassPathResource guide =
        new ClassPathResource("mail/attachments/welcome-guide.pdf");
~~~

Đường dẫn trong **ClassPathResource(...)** là đường dẫn tương đối đến *classpath root*. Không đưa tiền tố **src/main/resources/** vào chuỗi.

## 4. Chuẩn bị môi trường

Một dự án ví dụ:

- Java phiên bản được Spring Boot đang dùng hỗ trợ (ví dụ Java 17+ trong dự án Spring Boot 3.x).
- Spring Boot và **spring-boot-starter-mail**.
- Một SMTP server thử nghiệm/capture inbox.
- Hai tài nguyên hợp lệ có sẵn ở classpath: PNG và PDF.

Dependency Maven nếu dự án quản lý version thông qua Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

Nếu muốn tạo REST endpoint demo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Tương đương Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Lưu ý về Jakarta Mail:** những dự án Spring Framework 6 / Spring Boot 3 trở lên dùng package **jakarta.mail.\***. Dự án Spring 5 / Boot 2 cũ có thể dùng **javax.mail.\***. Không trộn class MIME và dependencies từ hai hệ sinh thái trong cùng một ví dụ.

Bài tập không yêu cầu tạo PDF thật bằng Java, cũng không yêu cầu gửi mail đến provider thương mại. Để chạy thử, hãy đặt một file PNG và một file PDF hợp lệ vào đúng resource path.

## 5. Cấu trúc thư mục mẫu

~~~text
spring-mail-classpath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/maildemo/
    │   │   ├── MailDemoApplication.java
    │   │   ├── mail/
    │   │   │   ├── MailAssetProperties.java
    │   │   │   ├── MailResourceLoader.java
    │   │   │   ├── WelcomeMailService.java
    │   │   │   └── MailDemoController.java
    │   └── resources/
    │       ├── application.yml
    │       └── mail/
    │           ├── images/
    │           │   └── brand-logo.png
    │           └── attachments/
    │               └── welcome-guide.pdf
    └── test/
        ├── java/com/example/maildemo/mail/
        │   └── WelcomeMailServiceTest.java
        └── resources/
~~~

Đối với ứng dụng thật, không bắt buộc dùng toàn bộ class như sơ đồ. Điều quan trọng là **email composition**, **resource loading**, **transport** và **API authorization** có trách nhiệm rõ ràng.

### File trong resources có phải dữ liệu runtime không?

Tài nguyên classpath thường thích hợp cho file **tĩnh đi kèm phiên bản ứng dụng**, ví dụ logo và tài liệu hướng dẫn mặc định.

Không nên dùng classpath làm nơi lưu:

- Hóa đơn PDF được tạo riêng cho từng người dùng.
- File người dùng upload sau khi ứng dụng đã deploy.
- Tài liệu chứa dữ liệu cá nhân cần xóa theo yêu cầu riêng.
- File thay đổi thường xuyên mà không muốn build/deploy lại.

Các trường hợp đó phù hợp hơn với **database/object storage/durable file storage** có kiểm soát quyền và retention.

## 6. Chọn đường dẫn tài nguyên nhất quán

Ba cách có thể gặp:

~~~java
new ClassPathResource("mail/images/brand-logo.png");

resourceLoader.getResource(
        "classpath:mail/images/brand-logo.png"
);

new ClassPathResource(
        "/mail/images/brand-logo.png"
);
~~~

Với **ClassPathResource**, nên dùng đường dẫn classpath-relative rõ ràng, không cần slash đầu. Với **ResourceLoader**, tiền tố **classpath:** thể hiện protocol của resource.

Không nên viết:

~~~java
new ClassPathResource(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

vì **src/main/resources** là vị trí trong source tree, không phải một phần của đường dẫn sau khi đóng gói vào classpath.

Không nên ghép các phần đường dẫn bằng chuỗi từ input không đáng tin cậy:

~~~java
new ClassPathResource(
        "mail/attachments/" + userProvidedFilename
);
~~~

Việc này có thể dẫn đến truy cập nhầm resource hoặc tiết lộ nội dung không dự định gửi. Tài nguyên phải được chọn từ một **allowlist** do ứng dụng kiểm soát.

## 7. MIME multipart là gì?

Email truyền qua SMTP theo MIME có thể chứa nhiều body parts. Một MIME message có thể có cấu trúc:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png
    │       Content-ID: <brandLogo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="welcome-guide.pdf"
~~~

Đây là **cấu trúc khái niệm** cho một email có plain text, HTML, inline image và attachment. Chi tiết MIME tree cuối cùng phụ thuộc cấu hình helper, Jakarta Mail implementation và cách thư được tạo.

Các multipart subtype có chức năng khác nhau:

- **multipart/mixed:** chứa các phần nội dung/attachment độc lập.
- **multipart/related:** nhóm HTML với resource phụ thuộc, chẳng hạn hình tham chiếu bằng Content-ID.
- **multipart/alternative:** cung cấp các phiên bản cùng nội dung, thường plain text và HTML.

Nếu chỉ tạo **SimpleMailMessage**, không có API MIME multipart để gắn ảnh inline và file đính kèm theo cách này. Cần **MimeMessage**.

## 8. MimeMessageHelper hỗ trợ gì?

Spring cung cấp **MimeMessageHelper** từ package:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

Nó giúp:

- Đặt From, To, Cc, Bcc, Subject.
- Đặt nội dung plain text/HTML.
- Thiết lập charset.
- Tạo multipart message.
- Thêm attachment qua **DataSource**, **File** hoặc **InputStreamSource**.
- Thêm inline resource qua **addInline(...)**.

Một helper chỉ nhận MimeMessage mà **không bật multipart** không đủ cho trường hợp bài tập.

Ví dụ nên dùng:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

**MULTIPART_MODE_MIXED_RELATED** được dùng để tổ chức body có inline resources và attachments. Cách này thường phù hợp với email HTML có logo và tài liệu đính kèm.

Constructor:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

cũng bật multipart; tuy nhiên việc dùng hằng **MULTIPART_MODE_MIXED_RELATED** làm ý định thiết kế rõ hơn trong bài thực hành.

## 9. Vì sao cần plain text cùng HTML?

Một số người nhận tắt HTML, email client hỗ trợ HTML không đồng đều, hoặc thư được đọc trong phần mềm assistive. Nếu chỉ có HTML, người nhận có thể khó đọc khi nội dung không được render.

Spring hỗ trợ:

~~~java
helper.setText(
        "Chào mừng bạn! Vui lòng xem tài liệu đính kèm.",
        "<h1>Chào mừng bạn!</h1>"
                + "<p>Vui lòng xem tài liệu đính kèm.</p>"
);
~~~

Khi truyền hai chuỗi, **tham số đầu là plain text**, tham số thứ hai là HTML. Helper sẽ tạo cấu trúc phù hợp với **multipart/alternative**.

Đừng nhầm với overload:

~~~java
helper.setText(
        "<h1>Chào mừng</h1>",
        true
);
~~~

Overload thứ hai có nghĩa **nội dung HTML**, không phải một bản plain text và một bản HTML riêng.

Hãy giữ nội dung chính tương đương ở cả hai phiên bản; không để plain text toàn quảng cáo trong khi HTML chứa nội dung giao dịch khác biệt.

## 10. Dịch vụ gửi email hoàn chỉnh

Đây là phần trung tâm của bài thực hành. Tạo **WelcomeMailService**:

~~~java
package com.example.maildemo.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "brandLogo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcomeMail(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("welcome@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn đến với ứng dụng");

        String plainText = """
                Xin chào!

                Cảm ơn bạn đã tham gia.
                Hướng dẫn bắt đầu được gửi trong file PDF đính kèm.
                """;

        String html = """
                <!doctype html>
                <html lang="vi">
                <body>
                    <h1>Chào mừng bạn!</h1>
                    <p>Cảm ơn bạn đã tham gia.</p>
                    <img src="cid:brandLogo"
                         alt="Logo ứng dụng"
                         width="180">
                    <p>Hướng dẫn bắt đầu nằm trong file
                       <strong>welcome-guide.pdf</strong> đính kèm.</p>
                </body>
                </html>
                """;

        // Đặt nội dung trước khi thêm inline resources.
        helper.setText(plainText, html);

        ClassPathResource logo = new ClassPathResource(
                "mail/images/brand-logo.png"
        );

        helper.addInline(
                LOGO_CID,
                logo,
                "image/png"
        );

        ClassPathResource guide = new ClassPathResource(
                "mail/attachments/welcome-guide.pdf"
        );

        helper.addAttachment(
                "welcome-guide.pdf",
                guide,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Ý nghĩa các bước:

1. **createMimeMessage()** tạo message MIME dùng session của JavaMailSender.
2. **MimeMessageHelper(..., MULTIPART_MODE_MIXED_RELATED, "UTF-8")** bật multipart và charset.
3. **setFrom, setTo, setSubject** đặt metadata chính.
4. **setText(plainText, html)** tạo hai phiên bản nội dung.
5. **addInline("brandLogo", logo, "image/png")** thêm một MIME resource gắn Content-ID.
6. **addAttachment("welcome-guide.pdf", guide, "application/pdf")** thêm PDF dưới dạng attachment.
7. **mailSender.send(message)** gửi message qua SMTP transport.

Trong project thật, **recipient phải được xác thực và kiểm tra quyền gửi**. Service trên giữ ngắn để minh họa cách tạo MIME; nó không cố mô phỏng toàn bộ policy production.

## 11. Tại sao nên chỉ định MIME Content-Type?

Hai lệnh:

~~~java
helper.addInline("brandLogo", logo, "image/png");

helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

chỉ định rõ:

- PNG là **image/png**.
- PDF là **application/pdf**.

Nếu không đưa Content-Type, một overload của MimeMessageHelper có thể cố suy ra loại nội dung từ tên file hoặc file type map. Với tài nguyên đặt tên lạ, extension bị thiếu hoặc hệ thống có file type map khác nhau, việc suy đoán có thể không chính xác.

Khi biết nội dung của resource là PNG/PDF hợp lệ, **chỉ định media type tường minh** giúp kết quả ổn định hơn.

Một số media type thông dụng:

| Loại file | Content-Type gợi ý |
|---|---|
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| PDF | **application/pdf** |
| Plain text | **text/plain** |
| CSV | **text/csv** |

Content-Type là **metadata**, không tự xác minh bytes bên trong. Không nên đổi đuôi một file không rõ nguồn thành .png rồi tin rằng nó là PNG an toàn.

## 12. Content-ID liên kết HTML với resource

Trong code:

~~~java
String cid = "brandLogo";
helper.addInline(cid, logo, "image/png");
~~~

Trong HTML:

~~~html
<img src="cid:brandLogo" alt="Logo ứng dụng" width="180">
~~~

Hai phần cần trùng nhau:

~~~text
HTML src:
    cid:brandLogo
          |
          v
MIME header:
    Content-ID: <brandLogo>
~~~

**MimeMessageHelper.addInline(...)** thường tạo header **Content-ID** có dạng angle-bracket theo MIME convention; khi gọi API dùng chuỗi ID **không có dấu < và >**.

Đừng viết sai như:

~~~java
helper.addInline("<brandLogo>", logo);
~~~

để rồi tham chiếu:

~~~html
<img src="cid:brandLogo">
~~~

Việc đưa dấu ngoặc vào ID ở API có thể tạo giá trị header không mong đợi.

### Có cần CID là email address đầy đủ?

Trong MIME, Content-ID có ngữ nghĩa kiểu **msg-id**. Nhiều ví dụ dùng ID đơn giản như brandLogo và được email client chấp nhận. Khi cần tương thích rộng hoặc quản lý nhiều inline resource, có thể dùng ID duy nhất dạng:

~~~text
brandLogo.12345@mailer.example.com
~~~

HTML khi đó cần tham chiếu **cid:brandLogo.12345@mailer.example.com**, thống nhất chính xác với giá trị helper truyền vào. Nếu hệ thống tự tạo CID, hãy đảm bảo tính duy nhất và encode phù hợp, tránh đưa dữ liệu không đáng tin vào header.

Với dự án bài tập, **brandLogo** là ID dễ theo dõi.

## 13. Thứ tự gọi setText và addInline

Trong ví dụ chuẩn:

~~~java
helper.setText(plainText, html);
helper.addInline("brandLogo", logo, "image/png");
~~~

Đây là thứ tự nên dùng. Một số MIME readers nhạy với thứ tự parts, và tài liệu Spring khuyến nghị gọi **setText(...) trước addInline(...)** để tránh inline resource không được client phân tích như mong muốn.

Không nên:

~~~java
helper.addInline("brandLogo", logo, "image/png");
helper.setText(plainText, html);
~~~

Mặc dù một số client vẫn hiển thị, cách này có thể giảm khả năng tương thích.

Attachment có thể thêm sau inline:

~~~java
helper.setText(plainText, html);
helper.addInline("brandLogo", logo, "image/png");
helper.addAttachment("welcome-guide.pdf", guide, "application/pdf");
~~~

Khi render nhiều resource, đặt nội dung HTML/plain text trước, rồi addInline và addAttachment theo nhóm sẽ làm code dễ hiểu.

## 14. Tại sao dùng ClassPathResource thay vì File?

Hai đoạn:

~~~java
ClassPathResource resource = new ClassPathResource(
        "mail/images/brand-logo.png"
);

resource.getInputStream();
~~~

và:

~~~java
File file = new File(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

không tương đương.

**ClassPathResource** tìm tài nguyên theo classpath, làm việc với file được đóng gói trong classpath/JAR. **File** theo đường dẫn tương đối lại phụ thuộc working directory của tiến trình.

Khi chạy:

~~~text
java -jar mail-demo.jar
~~~

working directory có thể là **/opt/app**, không chứa **src/main/resources**.

Vì vậy lệnh:

~~~java
resource.getFile()
~~~

không nên được giả định luôn thành công với file nằm trong JAR. **getInputStream()** là cách truy cập portable hơn.

Trong bài thực hành, MimeMessageHelper nhận trực tiếp **ClassPathResource** vì resource này triển khai **InputStreamSource**.

## 15. InputStreamSource và khả năng đọc lại

**ClassPathResource** có thể trả về một InputStream mới khi được yêu cầu, phù hợp cho attachment/inline content trong quá trình message được tạo và ghi ra SMTP.

Ví dụ:

~~~java
ClassPathResource guide = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
);

helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

Một số API Jakarta Mail có thể cần đọc stream nhiều lần, chẳng hạn khi tính kích thước, chuẩn bị MIME encoding và thực hiện gửi. Vì vậy **không nên dùng một InputStream đã mở sẵn** làm InputStreamSource chỉ dùng một lần.

Ví dụ dễ lỗi:

~~~java
InputStream once = guide.getInputStream();

// Không dùng một nguồn chỉ trả về đúng stream once
// qua nhiều lần gọi getInputStream().
~~~

Với file classpath, dùng **ClassPathResource** trực tiếp. Với bytes đã được tạo động, dùng một nguồn có thể đọc lại như **ByteArrayResource**, nhưng cần cân nhắc kích thước và bộ nhớ.

### Nếu resource quá lớn?

Không nên tải mọi attachment hàng chục MB vào heap chỉ để tiện thao tác. Cân nhắc file/object storage có streaming hoặc gửi đường dẫn tải xuống đã cấp quyền, tùy giới hạn SMTP và chính sách dữ liệu.

## 16. Chỉ định tên file đính kèm

Ở API:

~~~java
helper.addAttachment(
        "welcome-guide.pdf",
        guide,
        "application/pdf"
);
~~~

**"welcome-guide.pdf"** là tên file dự kiến hiển thị với người nhận, không phải đường dẫn classpath.

Bạn có thể lấy filename từ ClassPathResource:

~~~java
String filename = guide.getFilename();
~~~

Nhưng vì tên file có thể null ở một số nguồn Resource khác, và vì ứng dụng thường muốn tên file hiển thị riêng, có thể chỉ định tên tường minh.

Ví dụ cùng một resource PDF:

~~~java
helper.addAttachment(
        "Huong-dan-bat-dau.pdf",
        guide,
        "application/pdf"
);
~~~

Tên attachment không nên chứa CR/LF, path separator, control characters hoặc chuỗi do user trực tiếp cung cấp. Cần sanitize display filename và dùng encoding charset phù hợp, vì mail clients xử lý tên file Unicode không đồng nhất.

## 17. Một nội dung nhiều hình inline

Ví dụ có logo và biểu tượng trợ giúp:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/images/brand-logo.png");

ClassPathResource helpIcon =
        new ClassPathResource("mail/images/help-icon.png");

String html = """
        <html><body>
            <img src="cid:brandLogo" alt="Logo">
            <p>Liên hệ hỗ trợ:
                <img src="cid:helpIcon" alt="Hỗ trợ" width="20">
            </p>
        </body></html>
        """;

helper.setText("Liên hệ hỗ trợ qua ứng dụng.", html);
helper.addInline("brandLogo", logo, "image/png");
helper.addInline("helpIcon", helpIcon, "image/png");
~~~

Mỗi inline image có **Content-ID riêng**, và HTML tham chiếu đúng ID.

Không dùng cùng một CID cho hai resource khác nhau trong một message, vì mail client có thể chọn part không như mong đợi.

Nếu logo xuất hiện nhiều nơi trong cùng HTML, có thể tham chiếu **cùng một CID** nhiều lần mà không cần thêm resource lặp lại:

~~~html
<img src="cid:brandLogo" alt="Logo đầu thư">
<img src="cid:brandLogo" alt="Logo cuối thư">
~~~

## 18. Gửi nhiều attachment cùng một email

Một message có thể chứa nhiều file tĩnh:

~~~java
helper.addAttachment(
        "welcome-guide.pdf",
        new ClassPathResource("mail/attachments/welcome-guide.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "terms.pdf",
        new ClassPathResource("mail/attachments/terms.pdf"),
        "application/pdf"
);
~~~

Với số lượng nhỏ, code tường minh dễ đọc. Nếu số lượng tùy theo template, cần một **allowlist catalog** để mapping logical asset name sang path/content type/display filename.

Ví dụ:

~~~text
Asset ID: WELCOME_GUIDE
  path: mail/attachments/welcome-guide.pdf
  contentType: application/pdf
  displayName: welcome-guide.pdf

Asset ID: BRAND_LOGO
  path: mail/images/brand-logo.png
  contentType: image/png
  cid: brandLogo
~~~

Không cho caller bên ngoài đưa danh sách đường dẫn bất kỳ để tự động đính kèm mọi thứ có thể đọc từ classpath.

## 19. Attachment PDF và inline image không thay thế nhau

Ví dụ:

~~~html
<p>Hãy xem hướng dẫn PDF đính kèm.</p>
<img src="cid:welcomeGuide">
~~~

Nếu bạn thêm PDF bằng **addAttachment(...)**, tag **img** không thể render PDF như ảnh PNG/JPEG. Nếu muốn một ảnh thumbnail cho PDF, phải:

- Chuẩn bị một file PNG/JPEG thumbnail riêng trong classpath; hoặc
- Sinh thumbnail theo pipeline phù hợp, rồi gắn nó là inline image.

PDF vẫn được gửi dưới dạng attachment:

~~~text
HTML -> thumbnail image via cid:guidePreview
Attachment -> welcome-guide.pdf
~~~

Không nên gắn toàn bộ PDF như Content-ID của thẻ img và kỳ vọng email client hiển thị được.

## 20. Cấu hình SMTP để chạy thử an toàn

Với Spring Boot, **JavaMailSender** thường được auto-configure khi có starter mail và các thuộc tính cần thiết.

Ví dụ cấu hình một SMTP capture server chạy trên máy phát triển:

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Cấu hình này **chỉ dành cho SMTP test server không cần xác thực, trong môi trường local cô lập**. Không sử dụng cấu hình thiếu TLS/không authentication để gửi Internet production.

Nếu cần dùng SMTP có xác thực:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các biến môi trường phải được cung cấp bằng secret manager hoặc cấu hình bảo mật tương ứng. Kiểm tra đúng host, port, TLS mode và chính sách của provider; không giả định mọi server sử dụng cùng cấu hình.

**MailHog/Mailpit/GreenMail** là những ví dụ thường được dùng cho môi trường thử nghiệm. Cách chạy, cổng SMTP và cổng web UI phụ thuộc bản cài đặt; địa chỉ **localhost:1025** ở trên là ví dụ và cần được điều chỉnh cho đúng SMTP test server.

## 21. Chạy Spring Boot application

Class khởi động:

~~~java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailDemoApplication.class, args
        );
    }
}
~~~

Nếu thư viện Spring Mail và cấu hình SMTP đã có, **WelcomeMailService** sẽ được Spring tạo với bean JavaMailSender phù hợp.

Trong bài tập có thể gọi service từ:

- Một **CommandLineRunner** khi muốn kiểm tra gửi đúng một email mẫu trong môi trường local.
- Một **integration test**.
- Một **endpoint nội bộ** đã được bảo vệ.

Không nên để ứng dụng production tự động gửi email thật mỗi lần start, vì pod restart/scale có thể tạo nhiều email.

Ví dụ runner chỉ kích hoạt khi profile demo được bật:

~~~java
package com.example.maildemo;

import com.example.maildemo.mail.WelcomeMailService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class DemoMailRunner {

    @Bean
    @Profile("mail-demo")
    CommandLineRunner sendOneExample(
            WelcomeMailService service
    ) {
        return args -> service.sendWelcomeMail(
                "student@example.net"
        );
    }
}
~~~

Chỉ bật profile **mail-demo** với SMTP capture server hoặc địa chỉ test được phép. Nếu chạy profile trong môi trường production, cần ràng buộc để runner không tự gửi trùng hoặc tạo email ngoài ý muốn.

## 22. Kiểm tra resource có tồn tại trước khi tạo email

Khi đường dẫn sai, lỗi có thể chỉ xuất hiện khi Jakarta Mail thực sự đọc resource để write MIME/SMTP DATA.

Một helper đơn giản:

~~~java
import org.springframework.core.io.ClassPathResource;

public final class MailResourceLoader {

    public ClassPathResource required(String path) {
        ClassPathResource resource =
                new ClassPathResource(path);

        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException(
                    "Required mail resource is missing: " + path
            );
        }

        return resource;
    }
}
~~~

Trong ví dụ này **path là hằng hoặc giá trị đã được kiểm soát của ứng dụng**, không phải đường dẫn do caller truyền trực tiếp. Nếu bạn nhận path từ người dùng hoặc tenant configuration, không log/truy cập tùy ý; hãy dùng catalog ID được allowlist.

Ví dụ service:

~~~java
MailResourceLoader resources = new MailResourceLoader();

ClassPathResource logo = resources.required(
        "mail/images/brand-logo.png"
);

ClassPathResource pdf = resources.required(
        "mail/attachments/welcome-guide.pdf"
);
~~~

**exists()** và **isReadable()** là bước phát hiện sớm, không bảo đảm file không lỗi trong mọi trường hợp. Khi đọc stream hoặc gửi vẫn có thể xuất hiện IOException/MailException, vì vậy error handling vẫn cần ở transport boundary.

## 23. Khởi động mà thiếu tài nguyên: fail fast hay fail khi gửi?

Giả sử ứng dụng cần logo và PDF ở mọi email welcome:

~~~text
Build thành công
JAR thiếu welcome-guide.pdf
Ứng dụng start
Đến khi có user mới -> send fails
~~~

Có hai lựa chọn:

**Fail fast lúc start**

- Kiểm tra những tài nguyên bắt buộc trong một startup validation service.
- Phát hiện lỗi cấu hình/package sớm.
- Phù hợp khi những resource là thành phần thiết yếu của luồng mail.

**Kiểm tra lúc compose**

- Một lỗi ở template hiếm dùng không làm toàn bộ ứng dụng không start.
- Phù hợp khi có nhiều chiến dịch/optional resources.
- Cần quan sát và trạng thái lỗi riêng cho notification tương ứng.

Ví dụ startup validator:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

@Configuration
public class MailAssetValidationConfiguration {

    @Bean
    ApplicationRunner verifyRequiredMailAssets() {
        return args -> {
            require("mail/images/brand-logo.png");
            require("mail/attachments/welcome-guide.pdf");
        };
    }

    private void require(String path) {
        ClassPathResource resource =
                new ClassPathResource(path);
        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException(
                    "Missing mail asset: " + path
            );
        }
    }
}
~~~

Nên đặt các resource bắt buộc và optional theo chính sách rõ ràng. Không dùng fail-fast cho file có thể được tạo động sau khi service khởi động.

## 24. Tổ chức danh mục tài nguyên có type và CID

Khi bài thực hành mở rộng lên nhiều template, các path hardcoded có thể được gom thành catalog:

~~~java
public enum MailAsset {

    BRAND_LOGO(
            "mail/images/brand-logo.png",
            "image/png",
            "brandLogo"
    ),

    WELCOME_GUIDE(
            "mail/attachments/welcome-guide.pdf",
            "application/pdf",
            null
    );

    private final String path;
    private final String mediaType;
    private final String contentId;

    MailAsset(
            String path,
            String mediaType,
            String contentId
    ) {
        this.path = path;
        this.mediaType = mediaType;
        this.contentId = contentId;
    }

    public String path() {
        return path;
    }

    public String mediaType() {
        return mediaType;
    }

    public String contentId() {
        return contentId;
    }
}
~~~

Áp dụng:

~~~java
MailAsset logoAsset = MailAsset.BRAND_LOGO;

helper.addInline(
        logoAsset.contentId(),
        new ClassPathResource(logoAsset.path()),
        logoAsset.mediaType()
);
~~~

Lợi ích:

- Không lấy đường dẫn do người nhận tự cung cấp.
- Hạn chế nhầm media type.
- Dễ thay đổi asset theo phiên bản template.
- Có thể validate toàn bộ catalog ở build/deploy.

Trong production đa tenant, catalog có thể tham chiếu assets được quản lý theo tenant/template version, nhưng cần authorization rõ ràng trước khi tải.

## 25. Tách bước compose và bước send

Để dễ kiểm thử, có thể thiết kế một component chỉ có trách nhiệm **soạn MIME**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class WelcomeMimeComposer {

    public void compose(
            MimeMessage message,
            String approvedFrom,
            String recipient
    ) throws MessagingException {

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(approvedFrom);
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String text = "Xin chào! Xem file PDF đính kèm.";
        String html = """
                <html><body>
                <h1>Xin chào!</h1>
                <img src="cid:brandLogo"
                     alt="Logo ứng dụng"
                     width="180">
                <p>Xem file hướng dẫn PDF đính kèm.</p>
                </body></html>
                """;

        helper.setText(text, html);

        helper.addInline(
                "brandLogo",
                new ClassPathResource(
                        "mail/images/brand-logo.png"
                ),
                "image/png"
        );

        helper.addAttachment(
                "welcome-guide.pdf",
                new ClassPathResource(
                        "mail/attachments/welcome-guide.pdf"
                ),
                "application/pdf"
        );
    }
}
~~~

Gửi qua service riêng:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailDispatcher {

    private final JavaMailSender sender;
    private final WelcomeMimeComposer composer;

    public WelcomeMailDispatcher(
            JavaMailSender sender,
            WelcomeMimeComposer composer
    ) {
        this.sender = sender;
        this.composer = composer;
    }

    public void send(String approvedRecipient)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();

        composer.compose(
                message,
                "welcome@example.com",
                approvedRecipient
        );

        sender.send(message);
    }
}
~~~

Đây là **biến thể có tách trách nhiệm** của WelcomeMailService ban đầu, không phải yêu cầu phải dùng đồng thời hai service để gửi cùng một email. Nó giúp kiểm thử MIME composition mà không gọi SMTP.

## 26. Không nên gửi qua endpoint công khai không bảo vệ

Một controller kiểu:

~~~java
@PostMapping("/send-email")
public void send(@RequestParam String email) {
    welcomeMailService.sendWelcomeMail(email);
}
~~~

nếu không có authentication/authorization, validation và rate limit có thể biến máy chủ thành công cụ gửi thư hàng loạt.

Trong bài tập, ưu tiên:

- **CommandLineRunner** chỉ bật trong profile local; hoặc
- **Test SMTP server** được cấu hình riêng; hoặc
- Endpoint nội bộ có Spring Security và giới hạn recipient theo allowlist.

Nếu thêm controller production:

1. Người gọi phải được xác thực.
2. Chỉ gửi loại email được quyền.
3. Recipient phải thuộc phạm vi được phép.
4. Có idempotency/rate limit.
5. Không cho caller chỉnh **From/Reply-To/SMTP host** tùy ý.
6. Có trạng thái gửi trung thực, không báo “delivered” chỉ vì send() return.

## 27. Xử lý exception khác nhau ở prepare và send

Hai giai đoạn:

~~~text
Prepare:
  create MimeMessage
  build HTML/plain text
  load ClassPathResource
  addInline/addAttachment

Transport:
  JavaMailSender.send(...)
  connect/auth/TLS/SMTP DATA/final reply
~~~

**MessagingException** thường liên quan thao tác MIME/Jakarta Mail. **MailException** là họ unchecked exceptions của Spring Mail ở tầng gửi/preparation/transport.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.MailException;

public void deliver(String recipient) {
    try {
        dispatcher.send(recipient);
    } catch (MessagingException ex) {
        // Không nên retry SMTP vô hạn:
        // có thể do MIME/header/content composition.
        throw new MailCompositionFailure(ex);
    } catch (MailException ex) {
        // Phân loại auth, provider 4xx/5xx, timeout,
        // hoặc outcome chưa rõ theo phase.
        throw new MailTransportFailure(ex);
    }
}
~~~

**MailCompositionFailure** và **MailTransportFailure** là application exceptions minh họa.

Một resource bị thiếu có thể tạo ra IOException hoặc được translate thành MailException khi MIME được ghi ra SMTP. Không suy luận mọi MailException đều do server; cần xem cause chain và phase.

Nếu đã bắt đầu truyền SMTP DATA và không nhận final reply, kết quả có thể **UNKNOWN**. Một request retry tự động có thể tạo email trùng.

## 28. Không giữ database transaction khi gửi SMTP

Một ví dụ không nên dùng:

~~~java
@Transactional
public void createUserAndSendMail(...) {
    saveUser();
    welcomeMailService.sendWelcomeMail(...);
}
~~~

Lý do:

- SMTP có thể mất nhiều giây và giữ DB transaction/lock không cần thiết.
- Database rollback không thu hồi được mail đã được SMTP accepted.
- Nếu mail transport lỗi, nghiệp vụ tạo user có thể bị rollback dù email chỉ là thông báo bổ sung.

Nếu ứng dụng cần bảo đảm **không mất ý định gửi** sau khi tạo user, cân nhắc:

~~~text
Business transaction:
    saveUser()
    insertNotificationOutbox()
COMMIT
       |
       v
Worker:
    compose from classpath resources
    JavaMailSender.send(...)
~~~

File classpath vẫn được dùng để compose email ở worker, miễn worker artifact chứa đúng resources. Trường hợp worker chạy tách deployment/version, cần đảm bảo tương thích template và assets giữa producer/consumer.

## 29. Kiểm thử MIME composition không cần SMTP thật

Vì **WelcomeMimeComposer** chỉ thao tác trên MimeMessage, có thể tạo một Jakarta Mail Session trong test mà không kết nối mạng.

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class WelcomeMimeComposerTest {

    private final WelcomeMimeComposer composer =
            new WelcomeMimeComposer();

    @Test
    void preparesSubjectAndMultipartMessage()
            throws Exception {

        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        composer.compose(
                message,
                "welcome@example.com",
                "student@example.net"
        );

        message.saveChanges();

        assertEquals("Chào mừng bạn", message.getSubject());
        assertNotNull(message.getContent());
    }
}
~~~

Đây là **bài test cơ sở** cho việc tạo message. Vì mục tiêu của bài thực hành là attachment và inline image, cần thêm assertion kiểm tra MIME tree và Content-ID, chứ không chỉ kiểm tra Subject.

### Tại sao không kiểm tra raw message bằng contains đơn giản?

Nội dung HTML và attachment có thể được MIME encoding (quoted-printable/base64), Content-Type có parameters, và header có thể được fold qua nhiều dòng. Vì vậy:

~~~java
message.toString().contains("cid:brandLogo")
~~~

không phải cách đáng tin để xác nhận MIME structure.

Thay vào đó dùng **Part.getContent()**, **MimeMultipart**, **BodyPart** và các headers trên từng part để kiểm tra cấu trúc đã tạo.

## 30. Duyệt MIME parts để tìm attachment và inline resource

Một helper test có thể duyệt multipart tree:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MimePartCollector {

    private MimePartCollector() {
    }

    public static List<Part> collect(Part root) throws Exception {
        List<Part> results = new ArrayList<>();
        walk(root, results);
        return results;
    }

    private static void walk(
            Part part,
            List<Part> results
    ) throws Exception {

        results.add(part);

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int index = 0;
                 index < multipart.getCount();
                 index++) {

                BodyPart bodyPart = multipart.getBodyPart(index);
                walk(bodyPart, results);
            }
        }
    }
}
~~~

Hàm nhận một **Part** và thu thập tất cả parts, kể cả các multipart container. Dùng nó để tìm:

- Một part có **Content-ID: <brandLogo>**.
- Một part có **image/png**.
- Một part có **application/pdf**, filename phù hợp và disposition attachment.
- Một part **text/html** chứa tham chiếu **cid:brandLogo**.
- Một part **text/plain** chứa phần nội dung tương đương.

### Ví dụ assertion

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class WelcomeMimeContentTest {

    @Test
    void includesInlineLogoAndPdfAttachment()
            throws Exception {

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        new WelcomeMimeComposer().compose(
                message,
                "welcome@example.com",
                "student@example.net"
        );
        message.saveChanges();

        List<Part> parts = MimePartCollector.collect(message);

        assertTrue(parts.stream().anyMatch(part -> {
            try {
                String[] ids = part.getHeader("Content-ID");
                return ids != null
                        && ids.length > 0
                        && ids[0].contains("brandLogo")
                        && part.isMimeType("image/png");
            } catch (Exception ex) {
                return false;
            }
        }));

        assertTrue(parts.stream().anyMatch(part -> {
            try {
                return part.isMimeType("application/pdf")
                        && "welcome-guide.pdf"
                                .equals(part.getFileName());
            } catch (Exception ex) {
                return false;
            }
        }));
    }
}
~~~

Các assertion này kiểm tra hai **parts cần thiết**. Chúng chưa chứng minh mọi mail client sẽ hiển thị hình đúng, vì client có thể áp dụng chính sách chặn ảnh, thay đổi layout hoặc có MIME parser riêng.

### Tại sao dùng isMimeType?

Một part có Content-Type:

~~~text
image/png; name="brand-logo.png"
~~~

so sánh equality với chuỗi **image/png** có thể sai vì có thêm parameters. **Part.isMimeType("image/png")** giúp kiểm tra media type theo MIME semantics.

## 31. Kiểm thử service gọi JavaMailSender đúng một lần

Không cần thực sự mở kết nối SMTP để xác nhận dispatcher gọi sender với message đã compose.

Ví dụ Mockito:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.times;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.mail.javamail.JavaMailSender;

class WelcomeMailDispatcherTest {

    @Test
    void sendsComposedMimeOnce() throws Exception {

        JavaMailSender sender =
                Mockito.mock(JavaMailSender.class);

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage()).thenReturn(message);

        WelcomeMailDispatcher dispatcher =
                new WelcomeMailDispatcher(
                        sender,
                        new WelcomeMimeComposer()
                );

        dispatcher.send("student@example.net");

        verify(sender, times(1)).send(message);
    }
}
~~~

**Mockito verification** xác nhận invocation. Nó không chứng minh:

- SMTP server nhận message.
- Provider accepted RCPT TO/DATA.
- Nội dung đến inbox.
- Attachment đúng bytes.
- DNS, TLS, authentication đã hoạt động.

Các vấn đề này thuộc integration test hoặc kiểm thử end-to-end phù hợp.

## 32. Kiểm thử bytes attachment và inline image

Chỉ có tên file và Content-Type chưa đủ. Có thể có một attachment PDF **0 byte** nếu resource sai nhưng code không phát hiện sớm.

Với file kiểm thử có kích thước xác định, có thể:

1. Đọc resource expected từ classpath.
2. Tìm body part tương ứng trong MIME tree.
3. Đọc input stream nội dung của part.
4. So sánh bytes hoặc SHA-256 hash với resource expected.

Ví dụ phần đọc resource:

~~~java
import org.springframework.core.io.ClassPathResource;

byte[] expectedPdf = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
).getInputStream().readAllBytes();
~~~

Phần body part:

~~~java
byte[] actualPdf;
try (var input = pdfPart.getInputStream()) {
    actualPdf = input.readAllBytes();
}
~~~

Trong đó **pdfPart** là **Part** tìm được bằng helper duyệt MIME từ phần trước. So sánh:

~~~java
org.junit.jupiter.api.Assertions.assertArrayEquals(
        expectedPdf, actualPdf
);
~~~

Đây là test về **nội dung attachment**, không chỉ kiểm tra tên.

Với file lớn, test không cần đọc toàn bộ bytes vào RAM nếu có thể stream và so sánh hash; bài tập dùng file nhỏ để dễ thực hành.

## 33. Integration test với SMTP capture server

Sau khi test MIME composition, nên kiểm tra gửi qua một SMTP capture server. Ví dụ kiến trúc:

~~~text
JUnit / Spring Boot test
        |
        v
WelcomeMailService
        |
        v
JavaMailSender configured to test SMTP
        |
        v
Mailpit / GreenMail / equivalent SMTP capture
        |
        v
Read received message
        |
        +-- Subject
        +-- To/From
        +-- HTML with cid
        +-- Inline PNG
        +-- PDF attachment
~~~

Một kịch bản:

1. Khởi động SMTP test server trong môi trường cách ly.
2. Cấu hình Spring test profile trỏ JavaMailSender tới server đó.
3. Gọi **sendWelcomeMail("student@example.net")**.
4. Lấy message từ server thử nghiệm.
5. Kiểm tra recipients, MIME tree, Content-ID và attachment bytes.
6. Đảm bảo test cleanup mailbox/server sau khi hoàn tất.

**Không dùng một SMTP production account làm test server**, nhất là khi attachment là tài liệu chưa được phép gửi ra ngoài.

### Điều gì vẫn cần kiểm tra thủ công?

Các mail client như Gmail, Outlook, Apple Mail hoặc webmail nội bộ có cách render khác nhau. SMTP capture server thường cho phép xem raw MIME và một bản HTML preview; nó không đại diện hoàn toàn cho mọi client.

Khi cần hỗ trợ nhiều client, nên kiểm thử hiển thị thực tế trên một **test inbox** được phép, đặc biệt khi thư có các hình inline và tệp đính kèm.

## 34. Kiểm tra cấu trúc MIME raw khi gặp lỗi

Nếu ảnh không hiển thị, một hướng điều tra là xem nguồn MIME:

~~~text
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/related; boundary="inner"

--inner
Content-Type: text/html; charset=UTF-8

<img src="cid:brandLogo">

--inner
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline

[encoded PNG bytes]

--outer
Content-Type: application/pdf
Content-Disposition: attachment; filename="welcome-guide.pdf"

[encoded PDF bytes]
~~~

Raw MIME thực tế còn chứa nhiều headers và encoding boundaries; sơ đồ trên cố ý lược bỏ chi tiết.

Hãy kiểm tra:

- HTML có đúng **cid:brandLogo**?
- MIME image part có đúng **Content-ID: <brandLogo>**?
- Content-Type của part là image/png?
- Nội dung image part có bytes hợp lệ?
- Attachment có Content-Disposition attachment và tên file?
- Multipart boundaries có được tạo đúng?

Nếu một mail client không hỗ trợ cấu trúc nào đó, có thể thử mode MIME phù hợp hơn thay vì kết luận Spring Mail bị lỗi.

## 35. Lỗi: ảnh thành attachment thay vì hiện trong HTML

Một số email client hiển thị inline image đồng thời trong danh sách attachments. Điều đó **không nhất thiết** chứng minh code sai; UI của client có thể quyết định cách thể hiện.

Kiểm tra nguyên nhân:

1. Có dùng **addInline(...)**, hay chỉ **addAttachment(...)**?
2. HTML có tham chiếu **cid:...** đúng ID không?
3. **setText(...)** có được gọi trước **addInline(...)** không?
4. MIME có **multipart/related** chứa HTML và resource theo cấu trúc tương thích không?
5. Client có chặn ảnh hoặc sanitization làm mất thẻ img không?
6. File có phải PNG/JPEG thực sự không?
7. Có nhiều Content-ID trùng nhau không?

Không dùng base64 data URI trong HTML như một phép thay thế mặc định. Nhiều email client có giới hạn hoặc loại bỏ dạng **data:image/...;base64,...**, trong khi **cid:** là cơ chế chuẩn dành cho inline MIME resource.

## 36. Lỗi: ClassPathResource không tìm thấy file

Ví dụ:

~~~text
FileNotFoundException:
class path resource [mail/images/brand-logo.png]
cannot be opened because it does not exist
~~~

Các nguyên nhân:

- File đặt nhầm ở **src/test/resources** thay vì **src/main/resources** nên có trong test nhưng thiếu ở production.
- Đường dẫn ClassPathResource có thêm **src/main/resources/**.
- Khác chữ hoa/chữ thường giữa Windows và Linux.
- File chưa được commit/package vào artifact.
- Maven/Gradle resource filtering hoặc build configuration loại trừ extension.
- Worker chạy bản JAR cũ chưa có resource.
- Resource path được xây từ cấu hình tenant và trỏ nhầm nơi.

Hướng xử lý:

1. Kiểm tra file vật lý trong source project.
2. Kiểm tra artifact build có chứa đường dẫn dưới classpath root.
3. Kiểm tra tên file và case chính xác.
4. Dùng **ClassPathResource.exists() / isReadable()** để phát hiện sớm.
5. Chỉ dùng **getInputStream()** hoặc truyền Resource vào helper thay vì bắt buộc có File vật lý.

**Không ghi workaround** đọc đường dẫn tương đối của working directory nếu deployment target là Spring Boot JAR. Điều đó chỉ khiến code hoạt động ngẫu nhiên trong IDE mà lỗi sau deploy.

## 37. Lỗi: ảnh vẫn hiện trong IDE nhưng mất sau khi build JAR

Khi dùng IDE, thư mục resource có thể được truy cập như file thật, khiến đoạn code dưới đây tưởng như đúng:

~~~java
File logo = new File(
        "src/main/resources/mail/images/brand-logo.png"
);
~~~

Khi đóng gói JAR, đường dẫn **src/main/resources/...** không còn là đường dẫn file hệ thống trong runtime. Thay thế:

~~~java
ClassPathResource logo = new ClassPathResource(
        "mail/images/brand-logo.png"
);
~~~

và:

~~~java
helper.addInline("brandLogo", logo, "image/png");
~~~

Nếu cần kiểm tra một archive mà không chạy chương trình, có thể kiểm tra danh sách các entry trong JAR bằng công cụ thích hợp của môi trường build. Với Spring Boot executable JAR, resource thường thuộc **BOOT-INF/classes/**; với cách đóng gói khác, layout có thể thay đổi.

Đừng tự mở archive bằng đường dẫn Windows/Linux rồi giải nén resource ra thư mục cố định chỉ để gửi email; điều đó làm tăng phức tạp triển khai, cleanup và rủi ro concurrency.

## 38. Lỗi: logo không hiện dù CID đúng

Có thể xảy ra:

~~~text
cid:brandLogo  = đúng
Content-ID     = <brandLogo>
Image bytes    = đúng
Nhưng email client vẫn ẩn hình
~~~

Một số nguyên nhân không nằm trong classpath:

- Email client có **remote/inline image display policy**.
- HTML bị sanitizer loại bỏ hoặc sửa tag.
- Client hỗ trợ MIME multipart khác nhau.
- Thư bị đánh dấu đáng ngờ hoặc gửi từ domain chưa xác thực.
- CSS/layout làm ảnh có kích thước bằng 0 hoặc bị ẩn.
- Content-Type không khớp bytes thực.
- Image bị corrupt hoặc có định dạng client không hỗ trợ.
- Thẻ img đang dùng URL không chính xác hoặc CID có ký tự không được encode thích hợp.

Để điều tra, cần tách:

1. **Resource loading:** byte PNG có thực sự được load?
2. **MIME composition:** Content-ID và image/png part có đúng?
3. **SMTP submission:** provider có nhận message nguyên vẹn?
4. **Mail rendering:** client cụ thể có hiển thị ảnh?

Không chỉ nhìn một màn hình Gmail/Outlook rồi kết luận phần Spring code sai.

## 39. Vì sao một số client thích multipart/related?

Email có HTML:

~~~html
<img src="cid:brandLogo">
~~~

cần resource liên kết với HTML. **multipart/related** thể hiện các phần nội dung có quan hệ, giúp client nhận biết hình là một resource được tham chiếu bởi body.

Một email cũng có PDF attachment độc lập; **multipart/mixed** thường bao ngoài phần HTML/inline content.

Spring hỗ trợ một số multipart mode:

- **MULTIPART_MODE_NO:** không dùng multipart.
- **MULTIPART_MODE_MIXED:** dùng multipart/mixed đơn.
- **MULTIPART_MODE_RELATED:** dùng multipart/related.
- **MULTIPART_MODE_MIXED_RELATED:** tổ chức mixed cùng related.

Với bài tập **vừa inline PNG vừa attachment PDF**, dùng **MULTIPART_MODE_MIXED_RELATED** là cách có chủ đích để nhóm chúng.

Khi có yêu cầu tương thích đặc biệt với client cũ, kiểm tra MIME thực tế và chọn mode phù hợp; không tự chuyển mode chỉ vì một client hiển thị attachment theo cách không mong muốn.

## 40. Thiết kế HTML cho email với ảnh inline

HTML dùng trong email nên đơn giản và chịu được việc client loại bỏ một phần CSS.

Ví dụ:

~~~html
<!doctype html>
<html lang="vi">
<body style="margin:0;padding:16px;font-family:Arial,sans-serif">
  <table role="presentation"
         cellpadding="0"
         cellspacing="0"
         style="max-width:600px;width:100%">
    <tr>
      <td>
        <img src="cid:brandLogo"
             width="180"
             alt="Logo ứng dụng"
             style="display:block;border:0">
      </td>
    </tr>
    <tr>
      <td>
        <h1>Chào mừng bạn</h1>
        <p>Chúng tôi đã đính kèm tài liệu
           welcome-guide.pdf để bạn bắt đầu.</p>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

Những nguyên tắc:

- Dùng **alt text** có nghĩa khi ảnh không được hiển thị.
- Giữ logo nhỏ và kích thước hiển thị tường minh.
- Tránh phụ thuộc hoàn toàn vào JavaScript hoặc CSS phức tạp; nhiều email client chặn chúng.
- Nội dung quan trọng phải tồn tại ở dạng văn bản, không chỉ nằm trong ảnh.
- Dùng **plain text alternative** để hỗ trợ trường hợp HTML bị tắt.
- Không đưa user-controlled HTML chưa escape/sanitize vào body.

**Ảnh inline không phải thay thế cho nội dung quan trọng:** nếu logo bị ẩn, email vẫn phải truyền đạt được thông điệp chính.

## 41. Escape nội dung người dùng khi dựng HTML

Giả sử service nhận tên khách hàng:

~~~text
customerName = <img src=x onerror=...>
~~~

Nếu nối chuỗi trực tiếp:

~~~java
String html = "<p>Xin chào " + customerName + "</p>";
~~~

thì HTML chứa input không đáng tin. Dù nhiều mail client sanitize HTML, ứng dụng không nên dựa vào cơ chế client để bảo vệ người nhận.

Cách tốt hơn:

- Dùng template engine có **HTML escaping** phù hợp.
- Tách phần HTML markup được kiểm soát khỏi text của người dùng.
- Validate nội dung/độ dài trước khi render.
- Không cho input tự thêm CID, remote image URL, script hoặc event handlers.
- Giới hạn scheme hợp lệ khi thêm links.

Nếu dùng **Thymeleaf**, cần phân biệt expression được escape với expression unescaped. Trong email, mặc định nên render text dưới dạng escaped khi nội dung do người dùng cung cấp.

Ví dụ template:

~~~html
<p th:text="'Xin chào ' + ${customerName}">
  Xin chào!
</p>
<img src="cid:brandLogo" alt="Logo ứng dụng">
~~~

**th:text** chèn text với escaping. Chỉ dùng unescaped HTML từ nguồn đã được kiểm soát và sanitize theo policy.

## 42. Dùng template engine có thay đổi cách addInline không?

Không. Template engine chỉ dựng **chuỗi HTML**, còn **MimeMessageHelper** vẫn phải tạo CID-linked MIME part.

Luồng:

~~~text
Thymeleaf/Freemarker/template renderer
       |
       v
HTML String with src="cid:brandLogo"
       |
       v
MimeMessageHelper.setText(plainText, html)
       |
       v
MimeMessageHelper.addInline("brandLogo", ClassPathResource)
       |
       v
MimeMessageHelper.addAttachment("welcome-guide.pdf", ClassPathResource)
       |
       v
JavaMailSender.send(...)
~~~

Một lỗi thường gặp là dùng template:

~~~html
<img src="/mail/images/brand-logo.png">
~~~

Đây là đường dẫn tương đối của **trang web**, không phải một đường dẫn classpath hoặc CID mà mail client tự hiểu. Khi email được mở ngoài ứng dụng, client không có base URL của website.

Hãy dùng:

~~~html
<img src="cid:brandLogo">
~~~

nếu mục tiêu là hình inline MIME; hoặc dùng URL HTTPS công khai do ứng dụng chủ động chọn khi mục tiêu là remote image.

## 43. Inline CID so với ảnh HTTPS từ CDN

| Tiêu chí | CID inline | HTTPS remote image |
|---|---|---|
| Ảnh có trong MIME? | Có | Không |
| Cần client tải qua mạng lúc mở thư? | Thường không cần tải từ website ngoài | Có, nếu client cho phép |
| Kích thước email | Tăng theo bytes ảnh | Nhỏ hơn vì chỉ chứa URL |
| Có thể bị client chặn/ẩn? | Có | Có |
| Cập nhật ảnh sau khi gửi | Khó vì bytes đã gắn trong mail | Có thể đổi nội dung ở URL, nhưng ảnh cache ảnh hưởng |
| Theo dõi lượt mở | Không phải cơ chế tracking | Có thể bị ảnh hưởng bởi proxy/privacy caching |
| Quản lý quyền | Resource nằm trong message đã gửi | Cần quản lý remote hosting/URL |

Không có cách nào đảm bảo ảnh luôn hiển thị. Với logo nhỏ và bài thực hành, **CID** giúp học về MIME multipart và tránh phụ thuộc remote CDN.

Với marketing cần nhiều asset lớn, remote images có thể giảm kích thước mail, nhưng phải cân nhắc privacy, caching, khả năng truy cập và chính sách của email providers.

## 44. Kích thước attachment và giới hạn của SMTP

Ví dụ một file PDF:

~~~text
Original PDF: 10 MB
Base64 MIME transport: larger than original bytes
Additional headers/boundaries: extra overhead
~~~

MIME encoding có thể làm tổng kích thước message tăng đáng kể. Giới hạn được áp dụng theo **toàn bộ message**, không chỉ file nguồn.

Nên:

1. Giới hạn file size trước khi compose.
2. Giới hạn tổng số attachments và tổng message size.
3. Không coi SMTP server chấp nhận một file 25 MB ở mọi domain.
4. Với tài liệu lớn, cân nhắc **HTTPS download link đã cấp quyền** thay vì attachment.
5. Nếu dùng link có thời hạn, đảm bảo thời hạn phù hợp với trải nghiệm người nhận.
6. Không chia một file nhạy cảm ra nhiều email như workaround mặc định.

Một ví dụ kiểm tra kích thước file classpath:

~~~java
ClassPathResource guide = new ClassPathResource(
        "mail/attachments/welcome-guide.pdf"
);

long bytes = guide.contentLength();
long maxBytes = 5L * 1024 * 1024;

if (bytes > maxBytes) {
    throw new IllegalStateException(
            "Welcome guide is larger than configured limit"
    );
}
~~~

**contentLength()** có thể cần mở stream tùy loại resource. Đây là giới hạn ví dụ, không phải limit mặc định của Spring Mail.

## 45. Charset, Unicode và tên file tiếng Việt

Nội dung tiếng Việt cần charset nhất quán:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Điều này giúp Subject/body tiếng Việt được mã hóa phù hợp. Tên file có dấu như:

~~~text
Hướng dẫn bắt đầu.pdf
~~~

có thể được mã hóa bằng MIME parameters/encoded words tùy implementation và cấu hình Jakarta Mail.

Vì không phải mọi mail client xử lý tên file Unicode giống nhau, nếu cần tương thích rất rộng có thể dùng tên hiển thị ASCII:

~~~text
Huong-dan-bat-dau.pdf
~~~

Phần nội dung HTML/plain text vẫn có thể dùng tiếng Việt Unicode bình thường.

Không encode sẵn Subject bằng Base64 bằng tay rồi gọi **helper.setSubject(...)** nếu không hiểu Jakarta Mail encoding, vì dễ gây double-encoding.

## 46. Không nhầm inline resource với embedded HTML base64

Hai phương pháp khác nhau:

**CID inline MIME**

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

Tương ứng một part riêng:

~~~text
Content-Type: image/png
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

**Data URI**

~~~html
<img src="data:image/png;base64,iVBORw0...">
~~~

Trong trường hợp này bytes ảnh nằm trong thuộc tính HTML, **không** tham chiếu một Content-ID part.

Một số mail client loại bỏ hoặc không render data URI. Vì bài học là thêm resource từ classpath bằng Spring Mail, nên dùng **addInline(...) + cid:** thay vì tự chuyển bytes ảnh sang base64 để nối vào HTML.

## 47. Tài nguyên tĩnh và versioning

Khi deploy một phiên bản ứng dụng mới, file:

~~~text
mail/images/brand-logo.png
~~~

có thể đổi nội dung. Email đã gửi vẫn giữ bytes MIME của lần gửi trước; email chưa gửi sẽ dùng phiên bản asset nằm trong worker artifact hiện tại.

Nếu notification được đưa vào queue trước deployment và gửi sau deployment:

~~~text
Day 1:
  Outbox N100 created
  logo v1 in app artifact

Day 2:
  Deploy new app
  logo v2 in worker artifact

Day 2:
  N100 gets sent with logo v2
~~~

Điều này có thể chấp nhận với logo chung, nhưng với tài liệu phiên bản pháp lý/hợp đồng hoặc file cần audit, cần **pin asset version**:

~~~text
asset_id = welcome-guide
asset_version = 2026-11
asset_ref = immutable storage ref
~~~

Không kỳ vọng classpath của **JAR phiên bản hiện tại** tự chứa tất cả tài liệu tĩnh của mọi phiên bản cũ nếu pipeline yêu cầu replay lâu dài.

## 48. Khi nào không nên dùng classpath cho attachment?

Để phân biệt đúng phạm vi, hãy xét:

| File cần gửi | Classpath phù hợp? | Gợi ý |
|---|---|---|
| Logo mặc định đi kèm ứng dụng | **Có** | PNG/JPEG có version |
| Tài liệu hướng dẫn công khai cho mọi người nhận | **Có** | PDF tĩnh, cập nhật qua deploy |
| Hướng dẫn cài đặt theo phiên bản sản phẩm | **Có điều kiện** | Giữ rõ phiên bản tài liệu |
| Hóa đơn có tên/giá của khách | **Không** | Generate + durable storage riêng |
| File user upload | **Không** | Object storage + validation |
| File bí mật thay đổi thường xuyên | **Không nên** | Secure storage, authorization, retention |
| Tài liệu có yêu cầu xóa theo từng người dùng | **Không nên** | Kho dữ liệu quản lý theo record |
| Thư campaign cần mỗi người một QR code | **Không** | Tạo bytes theo user, dùng repeatable resource |

Để gửi dữ liệu động:

~~~java
byte[] generatedPdf = invoiceGenerator.render(invoiceId);

helper.addAttachment(
        "invoice.pdf",
        new org.springframework.core.io.ByteArrayResource(generatedPdf),
        "application/pdf"
);
~~~

Ví dụ này cho thấy **ByteArrayResource** thích hợp cho bytes động nhỏ-vừa, nhưng không có nghĩa nên giữ hàng trăm file lớn trong heap. Ngoài ra, **invoiceGenerator** và invoiceId phải được ủy quyền theo tenant; code trên chỉ thể hiện cách truyền resource tới helper.

Với file lớn hoặc gửi bất đồng bộ, dùng **storage reference** có authorization và lifecycle rõ ràng.

## 49. An toàn dữ liệu trong attachment và inline image

Không phải file trong classpath đều nên được đính kèm.

Các tài nguyên không bao giờ được đưa vào email chỉ vì nằm trên classpath:

- **application.yml** chứa secret/config.
- Private keys hoặc TLS certificates.
- Credential/service-account JSON.
- Tài liệu nội bộ không dành cho recipient.
- Resource chứa data sample có thông tin cá nhân.
- Template nháp hoặc debug fixtures.

Ứng dụng nên dùng **allowlisted mail assets**:

~~~text
WELCOME_LOGO
WELCOME_GUIDE
SUPPORT_ICON
TERMS_PDF_V1
~~~

Sau đó ánh xạ ID tới đường dẫn classpath do developer kiểm soát. Không để HTTP request truyền tên file/đường dẫn raw vào ClassPathResource.

### Resource được gửi ra ngoài không còn trong quyền kiểm soát

Một khi email đã accepted, recipient có thể lưu, chuyển tiếp hoặc trích xuất attachment và inline image. **Không đưa dữ liệu bí mật vào file chỉ vì nó “nằm trong phần inline” thay vì attachment.**

Nếu cần thu hồi quyền truy cập tài liệu sau một thời gian, dùng link tới một dịch vụ có authentication/authorization/expiry phù hợp thay vì đính kèm bytes vĩnh viễn.

## 50. Bảo vệ địa chỉ gửi, người nhận và nội dung HTML

Một luồng production tối thiểu cần:

1. **Sender address** nằm trong danh sách domain/profile được phép.
2. **Recipient** được xác minh theo nghiệp vụ; không tạo open relay.
3. Subject và display filename không chứa CR/LF hoặc input độc hại.
4. Nội dung người dùng được HTML-escape.
5. Links trong HTML dùng HTTPS và được kiểm tra scheme/domain khi cần.
6. Inline resources/attachments được giới hạn số lượng và dung lượng.
7. Không ghi raw body, attachment, signed URL hoặc SMTP credentials vào logs thường.
8. Có consent/suppression policy thích hợp theo loại email.
9. Nếu mail là thông báo sau giao dịch, không gửi khi business event đã rollback hoặc không còn hợp lệ.
10. MIME/attachment phải dùng content type phù hợp, không gắn một file không tin cậy thành “image/png” chỉ bằng cách đặt tên.

**ClasspathResource không phải công cụ bảo mật**. Nó chỉ cung cấp cơ chế truy cập resource, còn quyền gửi và dữ liệu nào được chia sẻ là trách nhiệm của ứng dụng.

## 51. Observability và xử lý sự cố

Đối với email có attachment và inline image, log một số metadata hữu ích:

~~~text
notification_id: N100
message_kind: WELCOME
template_version: v3
asset_catalog: WELCOME_LOGO,WELCOME_GUIDE
asset_version: 2026-11
smtp_provider: test-smtp
attempt: 1
outcome: SUBMITTED
~~~

Không nên log:

~~~text
recipient email plaintext (nếu không cần và chưa kiểm soát)
full HTML
attachment bytes
base64 MIME
SMTP password
auth token
secret links
~~~

Nếu cần điều tra lỗi **RESOURCE_MISSING**, có thể log **asset ID**, **artifact version** và một path tĩnh đã được kiểm soát. Không log path do người dùng tự đưa vào.

Một số metric:

| Metric logic | Mục đích |
|---|---|
| **mail.compose.success** | Số messages đã soạn MIME thành công |
| **mail.compose.failure** | Lỗi chuẩn bị MIME/resource |
| **mail.asset.missing** | Asset bắt buộc không tồn tại |
| **mail.attachment.size** | Phân bố kích thước attachment |
| **mail.smtp.submission.duration** | Độ trễ gửi tới SMTP |
| **mail.smtp.attempts** | Số attempts theo outcome |
| **mail.smtp.unknown** | Attempts không rõ SMTP acceptance |

Không dùng **recipient**, **notificationId** hoặc attachment filename tùy ý làm metric labels vì dễ gây high cardinality và rủi ro lộ thông tin.

### Đừng gộp preparation error với provider outage

Một file classpath thiếu dẫn tới **composition/configuration failure**, cần sửa build/deployment. SMTP provider outage thường cần retry/backoff/failover theo policy.

Nếu dùng outbox, nên phân biệt:

~~~text
PREPARATION_FAILED / RESOURCE_NOT_FOUND
RETRY_WAIT / SMTP_451
FAILED / SMTP_REJECTED_PERMANENT
UNKNOWN / FINAL_REPLY_NOT_RECEIVED
SUBMITTED / SMTP_ACCEPTED
~~~

Không để worker retry nhanh vô hạn khi JAR thiếu **welcome-guide.pdf**: mỗi lần retry vẫn không thể tạo được cùng tài nguyên.

## 52. Bảng xử lý lỗi thực hành

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ClasspathResource.exists() false | Sai đường dẫn/case, chưa đóng gói | Kiểm tra src/main/resources và artifact |
| Chạy IDE được, JAR lỗi | Dùng File tương đối/getFile() | Đổi sang ClassPathResource/InputStream |
| HTML hiện, ảnh trống | CID sai, ảnh hỏng, client chặn | Kiểm tra HTML src và Content-ID, image part |
| Ảnh hiện thành attachment | Client behavior hoặc MIME mode | Xem multipart/related, addInline |
| File PDF không có | Chưa addAttachment hoặc source missing | Kiểm tra MIME parts và resource |
| File PDF nhận được nhưng 0 byte | Nguồn stream không hợp lệ | Kiểm tra repeatable InputStreamSource/bytes |
| Tên file hiển thị ký tự lạ | Encoding/filename handling | UTF-8, MIME parameters, thử tên ASCII |
| Subject tiếng Việt lỗi font | Charset cấu hình không phù hợp | Helper charset UTF-8 |
| Email quá lớn bị từ chối | MIME overhead/attachment size limit | Đo total message size, dùng download link |
| SMTP 535 authentication failed | Sai credential/provider policy | Kiểm tra secret và SMTP config |
| SMTP 451 tạm thời | Provider/recipient server tạm lỗi | Backoff trong deadline |
| SMTP 550 5.7.x | Policy/auth/reputation | Không quy ngay là recipient invalid |
| Timeout sau DATA | Acceptance chưa rõ | UNKNOWN và reconciliation |
| Resource khác nhau giữa pods | Deployed artifact versions lệch | Pin asset version, kiểm tra deployment |
| Logo của tenant A gửi cho tenant B | Sai mapping sender/template | Tenant-scoped asset/authorization |
| Attachment chứa secret | Allowlist thiếu hoặc path injection | Restrict asset catalog, incident response |

### Khi gặp lỗi, xác định tầng trước

~~~text
File có trong source tree?
        |
        v
Resource có trong classpath của artifact?
        |
        v
MimeMessageHelper tạo đúng parts?
        |
        v
SMTP server accepted?
        |
        v
Email client hiển thị đúng?
~~~

Việc phân tầng giúp tránh nhầm lỗi packaging với lỗi SMTP, hoặc nhầm giới hạn render của email client với lỗi ClassPathResource.

## 53. Bài tập mở rộng: thiết kế welcome email có hai ảnh

Thêm một file:

~~~text
src/main/resources/mail/images/help-icon.png
~~~

Yêu cầu:

1. Giữ logo hiện ở đầu thư.
2. Thêm help icon gần liên kết hướng dẫn.
3. Hai resource có CID khác nhau.
4. HTML vẫn đọc được nếu ảnh bị ẩn.
5. Vẫn giữ plain text alternative và PDF attachment.

Gợi ý:

~~~java
helper.setText(plainText, html);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png"
);

helper.addInline(
        "helpIcon",
        new ClassPathResource("mail/images/help-icon.png"),
        "image/png"
);
~~~

HTML:

~~~html
<img src="cid:brandLogo" alt="Logo">
<p>
  Xem hướng dẫn
  <img src="cid:helpIcon" alt="Trợ giúp" width="20">
</p>
~~~

Mở SMTP capture inbox và quan sát MIME tree: có **hai image parts** với **hai Content-ID**.

## 54. Bài tập mở rộng: nhiều attachment có version

Thêm:

~~~text
src/main/resources/mail/attachments/terms-v1.pdf
src/main/resources/mail/attachments/security-guide.pdf
~~~

Yêu cầu:

- Chỉ định media type **application/pdf**.
- Tên file hiển thị rõ ràng.
- Không gửi trùng file do template mapping lỗi.
- Không tự nhận path bất kỳ từ REST request.
- Giữ tổng kích thước message dưới giới hạn được cấu hình.
- Ghi asset version của tài liệu khi tạo email.

Gợi ý:

~~~java
helper.addAttachment(
        "terms-v1.pdf",
        new ClassPathResource(
                "mail/attachments/terms-v1.pdf"
        ),
        "application/pdf"
);

helper.addAttachment(
        "security-guide.pdf",
        new ClassPathResource(
                "mail/attachments/security-guide.pdf"
        ),
        "application/pdf"
);
~~~

Trong bài tập, file là tài liệu mẫu không chứa dữ liệu nhạy cảm. Khi dùng trong nghiệp vụ thật, cần xác định người nhận có quyền nhận từng tài liệu hay không.

## 55. Bài tập mở rộng: chọn inline image theo template

Giả sử có hai mẫu:

~~~text
WELCOME:
  brandLogo -> mail/images/brand-logo.png
  attachment -> welcome-guide.pdf

SECURITY_TIPS:
  shieldIcon -> mail/images/shield.png
  attachment -> security-guide.pdf
~~~

Một cách thiết kế:

~~~text
TemplateKind
       |
       v
Trusted asset catalog
       |
       +-- allowed inline resource IDs
       +-- allowed attachments
       +-- content types
       +-- display filenames
       |
       v
MimeMessageHelper
~~~

Không cho caller tự khai:

~~~text
template=SECURITY_TIPS
attachmentPath=application-prod-secrets.yml
~~~

và đưa nguyên path vào ClassPathResource. **Template kind và asset IDs nên thuộc allowlist** hoặc cấu hình quản trị có authorization và validation nghiêm ngặt.

## 56. Checklist hoàn thành dự án thực hành

**Chuẩn bị project**

1. Đã thêm **spring-boot-starter-mail** chưa?
2. Đang dùng đúng namespace **jakarta.mail** hay **javax.mail** theo phiên bản Spring?
3. Đã đặt PNG và PDF trong **src/main/resources/mail/** chưa?
4. Đường dẫn resource có phân biệt chữ hoa/chữ thường đúng không?
5. SMTP test profile có trỏ tới capture server, không phải production recipient không?

**Tạo MIME**

6. Có dùng **MimeMessage**, không chỉ SimpleMailMessage không?
7. Có bật multipart với mode phù hợp cho related + attachment không?
8. Có đặt charset **UTF-8** không?
9. Có plain text alternative và HTML body không?
10. **setText(...)** có được gọi trước **addInline(...)** không?
11. HTML có **src="cid:brandLogo"** không?
12. **addInline("brandLogo", ClassPathResource, "image/png")** có dùng cùng CID không?
13. **addAttachment(..., ClassPathResource, "application/pdf")** có tạo file đúng tên không?
14. Có tránh thêm **src/main/resources/** vào ClassPathResource path không?
15. Có tránh dùng **getFile()** khi chạy từ executable JAR không?
16. Tài nguyên có thể được đọc lại nếu MIME cần nhiều lượt không?

**Bảo mật và vận hành**

17. Sender/recipient có được cấp quyền đúng không?
18. Asset path có được allowlist không?
19. HTML do người dùng cung cấp có được escape không?
20. Attachment có size/count limit không?
21. Logs có tránh raw body, token, attachment bytes không?
22. SMTP credentials có nằm trong secret management không?
23. Không gửi mail tự động khi application restart trừ khi có chủ đích chứ?

**Kiểm thử**

24. Unit test đã xác nhận Subject, HTML và MIME parts chưa?
25. Có kiểm tra Content-ID và Content-Type của inline image không?
26. Có kiểm tra PDF attachment và bytes của nó không?
27. Có chạy thử qua SMTP capture server khi cần không?
28. Có xem raw MIME để xác nhận multipart/related và mixed không?
29. Có thử chạy bản JAR thay vì chỉ IDE không?
30. Có kiểm tra client cụ thể nếu yêu cầu hỗ trợ Gmail/Outlook không?

## 57. Tổng kết

Trong dự án **“Thêm attachment và inline image từ classpath”**, ba thành phần chính cần phối hợp:

~~~text
Classpath resources
    |
    +-- brand-logo.png
    +-- welcome-guide.pdf
    |
    v
MimeMessageHelper
    |
    +-- setText(plainText, html)
    +-- addInline("brandLogo", ClassPathResource, "image/png")
    +-- addAttachment("welcome-guide.pdf",
    |                 ClassPathResource, "application/pdf")
    |
    v
JavaMailSender.send(MimeMessage)
~~~

Những điều cần ghi nhớ:

1. **ClasspathResource** cho phép truy cập tài nguyên đóng gói trong ứng dụng một cách portable, kể cả khi chạy từ JAR.
2. **Attachment** là file đính kèm; **inline image** là MIME resource được liên kết với HTML bằng **Content-ID/cid:**.
3. **MULTIPART_MODE_MIXED_RELATED** giúp tổ chức HTML, inline image và attachment theo ý định rõ ràng.
4. **setText trước addInline** là thứ tự nên tuân theo để tăng khả năng tương thích email clients.
5. **Chỉ định Content-Type và charset** để tránh phụ thuộc nhận diện file và encoding mặc định.
6. **Không dùng getFile() cho resource trong JAR**, và không truyền stream một lần đọc cho API có thể cần đọc lại.
7. **Tách MIME composition khỏi SMTP transport** để kiểm thử cấu trúc parts mà không cần gửi thư thật.
8. **Mỗi client có cách render khác nhau**; hãy kiểm tra MIME đúng rồi mới phân tích hiển thị.
9. **Classpath thích hợp cho assets tĩnh**, không phải kho dữ liệu cá nhân, tài liệu sinh động hoặc file upload.
10. **Quyền gửi, dữ liệu bí mật, exception handling và delivery semantics** vẫn là trách nhiệm của ứng dụng ngay cả khi API helper làm việc đơn giản.

**Kết quả mong đợi là một email có nội dung plain text và HTML, logo được tham chiếu bằng CID ngay trong body, PDF xuất hiện như attachment riêng, và cả hai tài nguyên đều đọc từ classpath mà không phụ thuộc đường dẫn file của máy đang chạy.**





