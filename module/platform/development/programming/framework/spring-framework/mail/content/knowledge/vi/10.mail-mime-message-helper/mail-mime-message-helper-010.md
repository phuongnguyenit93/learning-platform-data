# Tham chiếu inline resource từ HTML bằng cid

## 1. Inline resource và cid giải quyết vấn đề gì?

Trong email HTML, ứng dụng thường cần hiển thị logo, biểu tượng, hình minh họa hoặc tài nguyên khác cùng với nội dung. Một phương pháp là đặt đường dẫn HTTP/HTTPS trong thẻ HTML; phương pháp khác là **đính kèm tài nguyên như một phần MIME liên quan đến nội dung HTML** và tham chiếu tài nguyên đó qua **Content-ID**, thường viết ngắn là **cid**.

Với **Spring Framework Mail**, lớp **MimeMessageHelper** hỗ trợ việc này thông qua phương thức **addInline(...)**. HTML chứa một tham chiếu như:

~~~html
<img src="cid:brandLogo" alt="Logo thương hiệu">
~~~

Sau đó Java tạo một MIME part chứa dữ liệu ảnh và gắn Content-ID tương ứng:

~~~java
helper.addInline("brandLogo", new ClassPathResource("mail/brand-logo.png"));
~~~

Khi email client đọc thư và hỗ trợ cấu trúc MIME liên quan, nó có thể tìm MIME part mang Content-ID **brandLogo** để hiển thị ngay tại vị trí thẻ img. **Không cần tải ảnh từ một URL công khai** như khi dùng ảnh remote, nhưng điều đó **không bảo đảm mọi email client sẽ hiển thị ảnh**: client có thể chặn hình, thay đổi HTML, hoặc hỗ trợ CID không giống nhau.

Điểm trọng tâm của bài học:

- **cid:** là một kiểu tham chiếu từ nội dung HTML tới tài nguyên có **Content-ID** trong cùng thông điệp MIME.
- **addInline(...)** đưa tài nguyên vào thông điệp và đặt Content-ID để client có thể tra cứu.
- **multipart/related** mô tả quan hệ giữa phần HTML chính và tài nguyên inline phụ thuộc vào nó.
- **setText(...) trước addInline(...)** là thứ tự nên dùng với MimeMessageHelper.
- Inline resource **khác** một tệp đính kèm thông thường và cũng **khác** ảnh được tải từ website bên ngoài.

## 2. Ba cách đưa hình ảnh vào email HTML

Giả sử email xác nhận đơn hàng có logo thương hiệu. Có ba cách thường gặp:

| Cách | Cú pháp trong HTML | Ưu điểm | Hạn chế |
|---|---|---|---|
| **Ảnh từ URL ngoài** | img src="https://..." | Không làm tăng nhiều dung lượng MIME; nội dung ảnh do web server/CDN phục vụ | Client có thể chặn remote images; cần URL truy cập được; có vấn đề quyền riêng tư và theo dõi tải ảnh |
| **Ảnh inline bằng CID** | img src="cid:brandLogo" | Ảnh nằm trong chính email, không cần HTTP URL công khai để lấy nội dung | Email lớn hơn; phụ thuộc MIME/client; vẫn có thể bị chặn hiển thị |
| **Ảnh dạng data URI** | img src="data:image/png;base64,..." | Nhúng dữ liệu trực tiếp vào HTML | Nhiều email client hỗ trợ hạn chế hoặc loại bỏ; làm HTML dài; không phải lựa chọn tương thích mặc định |

Với Spring Mail, phương pháp CID thuận tiện khi hình ảnh là một tài nguyên nhỏ, cố định và cần được đóng gói cùng thông điệp. Nó rất phổ biến cho logo hoặc icon trong email thông báo. Tuy nhiên, **ảnh CID không phải bảo đảm hiển thị trong mọi ứng dụng đọc thư**; email vẫn cần nội dung text thay thế.

### CID khác URL HTTP như thế nào?

~~~text
HTML dùng URL:
  <img src="https://static.example.com/logo.png">
                         |
                  Email client tải ảnh qua HTTPS

HTML dùng CID:
  <img src="cid:brandLogo">
                 |
         Tìm MIME part có Content-ID tương ứng
                 |
         Đọc dữ liệu ảnh nằm trong cùng email
~~~

CID là một **liên kết nội bộ trong thông điệp email**, không phải một API endpoint trong Spring MVC, không phải đường dẫn file local trên máy người nhận và cũng không phải URL HTTP mà trình duyệt thông thường có thể truy cập trực tiếp.

## 3. Content-ID và biểu thức cid: liên hệ ra sao?

MIME định danh một phần nội dung bằng header **Content-ID**. Ví dụ, phần ảnh có thể có các header:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <brandLogo>
~~~

Phần HTML tham chiếu tới ảnh bằng:

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

Hãy phân biệt:

| Vị trí | Giá trị | Ý nghĩa |
|---|---|---|
| Trong HTML | **cid:brandLogo** | URL scheme cid trỏ đến một MIME body part trong email. |
| Trong API Spring | **addInline("brandLogo", resource)** | Đăng ký nội dung gắn với Content-ID brandLogo. |
| Trong MIME header | **Content-ID: <brandLogo>** | Định danh của phần nội dung; trong header thường đặt trong dấu ngoặc nhọn góc. |

**Không truyền cả tiền tố cid: hoặc dấu ngoặc góc vào tham số contentId** của phương thức addInline. Với ví dụ này, chuỗi tham số là **brandLogo**, còn HTML tự thêm **cid:**.

Đối với Content-ID phức tạp, ID theo chuẩn MIME thường có hình thức tương tự message identifier và cần bảo đảm cú pháp/escaping phù hợp. Trong nội dung email tự sinh, nên dùng ID đơn giản, ổn định, duy nhất trong phạm vi thông điệp, chẳng hạn **brandLogo** hoặc **invoiceIcon**. Nếu sử dụng ID chứa ký tự có ý nghĩa đặc biệt trong URL, phần tham chiếu cid phải được mã hóa URL thích hợp thay vì nối chuỗi tùy tiện.

## 4. Cấu trúc MIME của HTML và ảnh inline

Một email HTML có ảnh inline không chỉ là một chuỗi HTML. Nó thường được biểu diễn bằng **multipart/related**:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

**multipart/related** nói rằng các phần MIME có quan hệ với nhau. Ở đây phần HTML là nội dung cần hiển thị, còn phần image/png là tài nguyên mà HTML cần để trình bày đầy đủ.

### MIME thô để hình dung

~~~text
From: notifications@example.com
To: customer@example.net
Subject: Example
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related_001"

--related_001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <p>Welcome!</p>
    <img src="cid:brandLogo" alt="Company logo">
  </body>
</html>

--related_001
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline

... base64-encoded image bytes ...

--related_001--
~~~

Ví dụ chỉ minh họa cấu trúc; **... base64-encoded image bytes ...** không phải dữ liệu ảnh hợp lệ. Trong thực tế, Jakarta Mail tự tạo boundary, header, encoding và dữ liệu transport phù hợp. Không nên tự nối MIME thô như trên để gửi trong production.

### multipart/related, multipart/alternative và multipart/mixed khác nhau

| MIME subtype | Mối quan hệ giữa các phần | Trường hợp |
|---|---|---|
| **multipart/related** | Các phần liên quan, có thể tham chiếu nhau | HTML và hình ảnh CID |
| **multipart/alternative** | Các biểu diễn thay thế của cùng nội dung | Plain text và HTML |
| **multipart/mixed** | Các thành phần đi cùng nhau | Nội dung email và file đính kèm thông thường |

Khi email vừa có plain text, HTML, ảnh inline và attachment, các subtype thường **lồng nhau**:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       └── <img src="cid:brandLogo">
    │   └── image/png; Content-ID: <brandLogo>
    └── application/pdf; attachment
~~~

Cây trên biểu diễn **quan hệ logic**. Cấu trúc MIME thực tế có thể khác đôi chút theo chế độ multipart và phiên bản thư viện. Không nên yêu cầu Content-Type ở root nhất thiết là multipart/related khi có attachment hoặc plain-text alternative.

## 5. Chuẩn bị Spring Boot để gửi email HTML

Trong một ứng dụng Spring Boot sử dụng Java 21, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ cấu hình SMTP qua cổng submission 587 với STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: account@example.com
    password: REPLACE_WITH_SECRET
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Địa chỉ máy chủ và tài khoản chỉ mang tính minh họa. Trong môi trường thật, mật khẩu/token SMTP phải được lấy từ biến môi trường hoặc secret manager; không lưu trực tiếp trong repository. Cấu hình cổng và chế độ TLS phải phù hợp với nhà cung cấp: cổng 465 thường dùng implicit TLS thay vì STARTTLS.

**Spring Boot** có thể tự cấu hình bean **JavaMailSender** từ thông tin phù hợp. **Spring Framework Mail** cung cấp **MimeMessageHelper** và API MIME; phần đóng gói CID được tạo khi ứng dụng xây dựng thông điệp chứ không phải một tùy chọn trong spring.mail.host.

Tài nguyên ảnh minh họa đặt tại:

~~~text
src/
└── main/
    └── resources/
        └── mail/
            └── brand-logo.png
~~~

Vì thuộc thư mục resources, file có thể được truy cập bằng **ClassPathResource("mail/brand-logo.png")**, cả khi ứng dụng đóng gói thành JAR, miễn tài nguyên được đưa vào classpath khi build.

## 6. Ví dụ hoàn chỉnh: hình ảnh inline bằng addInline

Dưới đây là một service dùng **JavaMailSender**, **MimeMessageHelper** và **ClassPathResource**. Email chứa cả bản văn bản thuần và bản HTML, trong đó bản HTML tham chiếu tới ảnh bằng CID.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

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

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String plainText = """
                Xin chào!

                Tài khoản của bạn đã sẵn sàng.
                Truy cập https://example.com/account để xem thông tin.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <img
                      src="cid:brandLogo"
                      alt="Logo thương hiệu"
                      width="140">
                    <h2>Xin chào!</h2>
                    <p>Tài khoản của bạn đã sẵn sàng.</p>
                    <p>
                      <a href="https://example.com/account">
                        Xem thông tin tài khoản
                      </a>
                    </p>
                  </body>
                </html>
                """;

        // Thiết lập nội dung text/HTML trước.
        helper.setText(plainText, htmlText);

        // Sau đó thêm MIME part mà HTML tham chiếu bằng cid:brandLogo.
        ClassPathResource logo =
                new ClassPathResource("mail/brand-logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Ví dụ giả định SMTP sender đã được cấu hình, người gửi được phép sử dụng địa chỉ **notifications@example.com**, và tài nguyên **mail/brand-logo.png** thực sự tồn tại trên classpath. Chuỗi **LOGO_CID** phải khớp với giá trị đứng sau **cid:** trong thuộc tính src của HTML.

### Phân tích những dòng quan trọng

**createMimeMessage():** Tạo đối tượng MimeMessage để xây nội dung email.

**MULTIPART_MODE_MIXED_RELATED:** Chọn chế độ multipart hỗ trợ tổ chức nội dung HTML, tài nguyên liên quan và cả attachment nếu sau này cần bổ sung. Tùy cách dùng, email có thể chứa nhiều lớp MIME lồng nhau.

**UTF-8:** Cho phép hiển thị nội dung tiếng Việt có dấu và hỗ trợ mã hóa header/body thích hợp.

**setText(plainText, htmlText):** Tạo hai cách biểu diễn thay thế cho cùng thông điệp. Bản plain text có thể đọc độc lập nếu client không hiển thị HTML hoặc ảnh.

**addInline("brandLogo", logo, "image/png"):** Thêm dữ liệu ảnh PNG vào một MIME body part có Content-ID tương ứng. Tham số thứ ba cho biết media type cụ thể của ảnh, giúp mail client xử lý phần nội dung.

**send(message):** Nộp thông điệp đã chuẩn bị cho hạ tầng gửi email. Việc gửi thành công ở chặng SMTP ban đầu không chứng minh ảnh được hiển thị ở mọi client hay toàn bộ thư đã vào Inbox.

## 7. Vì sao phải gọi setText trước addInline?

Với **MimeMessageHelper**, lời gọi **setText(...)** có thể thiết lập hoặc thay thế phần thân của message và một số cấu trúc multipart bên trong. Nếu gắn tài nguyên inline trước khi thiết lập body, một số cấu trúc MIME có thể không được tạo theo quan hệ mà email client mong đợi.

**Thứ tự nên áp dụng:**

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, MimeMessageHelper.MULTIPART_MODE_RELATED, "UTF-8"
);

helper.setFrom("sender@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Thông báo");

// 1. Đặt HTML trước.
helper.setText(
        "<p>Xin chào!</p><img src=\"cid:logo\" alt=\"Logo\">",
        true
);

// 2. Đưa tài nguyên inline vào sau.
helper.addInline(
        "logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

Đây là cách tạo một email HTML có ảnh inline mà không cần bản plain text thay thế. Trong ứng dụng thông báo tới nhiều loại email client, **nên có cả plain text** qua overload **setText(plainText, htmlText)**.

Không nên làm theo thứ tự ngược:

~~~java
// Thứ tự nên tránh trong ứng dụng thực tế.
helper.addInline("logo", logoResource, "image/png");
helper.setText(htmlText, true);
~~~

Đây là một lưu ý quan trọng về cách sử dụng API, không phải điều kiện của cú pháp URL cid. CID vẫn có nghĩa là tham chiếu tới Content-ID; vấn đề nằm ở cách thư viện dựng cây MIME khi các phương thức được gọi theo thứ tự.

## 8. Lựa chọn multipart mode cho inline image

**MimeMessageHelper** cung cấp các chế độ multipart, dùng khi khởi tạo helper:

| Chế độ | Ý nghĩa | Khi nào cân nhắc |
|---|---|---|
| **MULTIPART_MODE_NO** | Không sử dụng cấu trúc multipart | Email text/HTML một phần, không thêm inline resource hoặc attachment. |
| **MULTIPART_MODE_MIXED** | Tạo cấu trúc multipart/mixed | Phù hợp với phần nội dung và attachment, nhưng quan hệ inline có thể không tối ưu trên mọi client. |
| **MULTIPART_MODE_RELATED** | Tạo multipart/related | Email HTML có tài nguyên inline, khi không cần cấu trúc mixed bao ngoài. |
| **MULTIPART_MODE_MIXED_RELATED** | Kết hợp lớp mixed và related | Lựa chọn tổng quát khi vừa có inline resource vừa có attachment. |

Chế độ **true** trong constructor **MimeMessageHelper(message, true, encoding)** yêu cầu bật multipart, sử dụng một chế độ multipart mặc định của helper. Khi cần cấu trúc dễ dự đoán, có thể chỉ định tường minh mode phù hợp như các ví dụ ở trên.

### Trường hợp nào chọn RELATED?

Với email HTML chỉ có logo, có thể dùng:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

Khi có thêm file PDF cần người dùng tải về, cấu trúc thường cần **mixed** để phân biệt attachment với nội dung HTML và ảnh liên quan:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Việc chọn subtype MIME có thể ảnh hưởng đến cách các email client giải thích attachment và inline content. Không nên dùng **MULTIPART_MODE_NO** rồi kỳ vọng **addInline** có thể tạo tài nguyên liên quan đúng cách.

## 9. Các overload của addInline

**MimeMessageHelper** có những cách nhận nguồn tài nguyên khác nhau. Tùy trường hợp, có thể dùng File, Resource hoặc InputStreamSource kèm Content-Type.

### 9.1. File trên filesystem

~~~java
import java.io.File;

File logoFile = new File("/opt/app/assets/brand-logo.png");
helper.addInline("brandLogo", logoFile);
~~~

Ví dụ giả định file tồn tại ở vị trí đó. Đây là đường dẫn filesystem trên máy **chạy ứng dụng**, không phải đường dẫn mà email client sẽ mở. Dữ liệu file được đưa vào email dưới dạng MIME part khi thư được chuẩn bị/gửi.

**Hạn chế:** file có thể không tồn tại trong Docker container hoặc production server. Khi đóng gói ảnh cố định cùng ứng dụng, sử dụng ClassPathResource thường dễ di chuyển giữa môi trường hơn.

### 9.2. Resource trên classpath

~~~java
import org.springframework.core.io.ClassPathResource;

ClassPathResource logo =
        new ClassPathResource("mail/brand-logo.png");

helper.addInline("brandLogo", logo, "image/png");
~~~

**ClassPathResource** truy cập resource từ classpath. Cách này phù hợp với logo cố định được đóng gói trong thư mục **src/main/resources** của ứng dụng.

### 9.3. ByteArrayResource cho dữ liệu ảnh trong bộ nhớ

Giả sử ảnh được tạo từ dịch vụ render biểu đồ và ứng dụng đang giữ một mảng byte PNG hợp lệ:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pngBytes = generatePngBytes(); // Hàm ứng dụng cung cấp.

helper.addInline(
        "chartImage",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

Đoạn trên giả định **generatePngBytes()** trả về nội dung PNG hợp lệ; đây là hàm giả định để minh họa nguồn dữ liệu, không phải API có sẵn của Spring.

**ByteArrayResource** cho phép mở lại InputStream từ dữ liệu byte khi cần. Điều này hữu ích vì Jakarta Mail có thể đọc nguồn dữ liệu trong lúc serialize thông điệp hoặc thực hiện vận chuyển.

### 9.4. Resource và content type

Nếu thư viện không xác định đúng loại tài nguyên từ filename hoặc nguồn dữ liệu không có filename, nên dùng overload có media type:

~~~java
helper.addInline("brandLogo", resource, "image/png");
~~~

Media type phải đúng với dữ liệu thực tế, chẳng hạn **image/png**, **image/jpeg** hoặc **image/gif** khi thích hợp. Không đặt **image/png** cho byte JPEG chỉ vì phần mở rộng hoặc nội dung giả định.

## 10. Lưu ý quan trọng về InputStreamSource

Một tài nguyên inline không chỉ cần **mở được đúng một lần**. Khi xây MimeMessage, thư viện có thể yêu cầu đọc dữ liệu nhiều lần, tùy cách mã hóa, serialize và gửi.

Do đó, đối tượng truyền cho **addInline** nên có khả năng cung cấp **InputStream mới** cho mỗi lần được yêu cầu. Các lựa chọn thường phù hợp:

- **ClassPathResource** trỏ đến file classpath tồn tại.
- **FileSystemResource** trỏ đến file có thể đọc được.
- **ByteArrayResource** bọc mảng byte còn trong bộ nhớ.

Ngược lại, **InputStreamResource** thường bọc một luồng đã mở và không thích hợp nếu cùng luồng phải được đọc lại. Trường hợp nguồn chỉ có một InputStream, nên đọc dữ liệu thành byte[] có giới hạn kích thước trước, hoặc lưu tại vị trí bền vững rồi cung cấp Resource có thể mở lại.

Ví dụ không nên phụ thuộc vào một stream dùng một lần:

~~~java
// InputStream chỉ mở được một lần: có nguy cơ lỗi khi thư viện đọc lại.
InputStream stream = remoteClient.openLogoStream();
InputStreamResource oneShot = new InputStreamResource(stream);
helper.addInline("brandLogo", oneShot, "image/png");
~~~

Mô hình ổn định hơn là sử dụng ByteArrayResource:

~~~java
byte[] logoBytes = loadLogoBytesSafely();
ByteArrayResource repeatable = new ByteArrayResource(logoBytes);
helper.addInline("brandLogo", repeatable, "image/png");
~~~

Các hàm **remoteClient.openLogoStream()** và **loadLogoBytesSafely()** mang tính khái niệm. Trong production, cần giới hạn kích thước file, xử lý network timeout và kiểm tra nguồn tài nguyên trước khi đưa vào email. Không đọc một tài nguyên từ URL bất kỳ do người dùng nhập mà không kiểm soát, vì có thể gây **SSRF** hoặc lạm dụng tài nguyên.

## 11. Nhiều ảnh inline trong cùng email

Mỗi tài nguyên cần một **Content-ID riêng** để HTML có thể tham chiếu chính xác. Ví dụ email có logo và icon hỗ trợ:

~~~html
<!doctype html>
<html lang="vi">
  <body>
    <header>
      <img src="cid:brandLogo" alt="Logo" width="160">
    </header>
    <h2>Hóa đơn đã được phát hành</h2>
    <p>Liên hệ hỗ trợ nếu cần thêm thông tin.</p>
    <footer>
      <img src="cid:supportIcon" alt="Biểu tượng hỗ trợ" width="24">
    </footer>
  </body>
</html>
~~~

Code chuẩn bị:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/support-icon.png"),
        "image/png"
);
~~~

**Không dùng cùng Content-ID cho hai ảnh khác nhau** trong cùng một cây MIME cần tham chiếu rõ ràng. Client có thể chọn nhầm part hoặc không hiển thị như mong muốn.

Không cần tạo một MimeMessage cho mỗi ảnh: nhiều resource inline có thể cùng tồn tại trong **một email** và được nhóm trong multipart/related.

### Đặt tên Content-ID như thế nào?

Gợi ý thực hành:

- Dùng tên phân biệt vai trò, ví dụ **brandLogo**, **invoiceChart**, **supportIcon**.
- Giữ giá trị nhất quán giữa HTML và phương thức addInline.
- Không đưa thông tin bí mật hoặc dữ liệu nhận dạng cá nhân vào ID.
- Với hệ thống render template từ nhiều nguồn, quản lý ID tập trung để tránh trùng.
- Nếu cần ID tuân thủ cú pháp Content-ID đặc thù, dùng phương pháp sinh ID hợp lệ và mã hóa tham chiếu cid phù hợp.

## 12. Email có cả ảnh inline và file đính kèm

**Inline resource** và **attachment** mang ý nghĩa khác nhau. Logo dùng trực tiếp trong HTML nên được thêm bằng **addInline(...)**. Một file PDF để người nhận tải xuống nên thêm bằng **addAttachment(...)**.

Ví dụ:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.File;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailSender {

    private final JavaMailSender sender;

    public InvoiceMailSender(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, File invoicePdf)
            throws MessagingException {
        MimeMessage mimeMessage = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plainText = "Hóa đơn được đính kèm trong email này.";
        String htmlText = """
                <html lang="vi">
                  <body>
                    <img src="cid:brandLogo" alt="Logo thương hiệu">
                    <p>Hóa đơn được đính kèm trong email này.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );
        helper.addAttachment("invoice.pdf", invoicePdf);

        sender.send(mimeMessage);
    }
}
~~~

Trong ví dụ, **invoicePdf** phải là tệp có thật, hợp lệ và người nhận có quyền xem. Không gửi hóa đơn của người này cho người khác. Với file nhạy cảm, cần xem xét yêu cầu mã hóa, quyền truy cập và chính sách lưu trữ; MIME và CID không tự tạo bảo mật đầu cuối.

### Attachment có thể vẫn xuất hiện ở giao diện người đọc không?

Một số email client có thể hiển thị inline resource trong danh sách attachment hoặc sử dụng cách trình bày khác, dù MIME part được đặt **Content-Disposition: inline** và có Content-ID. Đây là hành vi phía client, không nhất thiết là lỗi gửi thư. Khác biệt giữa inline và attachment là **ý định và cấu trúc MIME**, không phải một bảo đảm thống nhất về giao diện.

## 13. Dùng CID trong template HTML

Trong ứng dụng thực tế, email thường được render từ Thymeleaf, FreeMarker hoặc một template engine. Khi đó HTML có thể chứa tham chiếu CID cố định:

~~~html
<table role="presentation">
  <tr>
    <td>
      <img
        src="cid:brandLogo"
        alt="Thương hiệu"
        width="160">
    </td>
  </tr>
  <tr>
    <td>
      <h2>Thông báo tài khoản</h2>
      <p>Nội dung thông báo được render từ template.</p>
    </td>
  </tr>
</table>
~~~

Service cần bảo đảm rằng mọi tham chiếu **cid:brandLogo** đều có MIME part tương ứng được thêm bằng helper. Nếu template khác không sử dụng logo, có thể bỏ qua việc thêm resource không cần thiết để giảm kích thước thư.

### Gắn dữ liệu động

Nếu email chứa tên người nhận, mã đơn hàng hoặc liên kết, hãy render dữ liệu vào template bằng cơ chế **escape theo ngữ cảnh**. Không nối trực tiếp nội dung người dùng vào HTML vì dữ liệu có thể chứa ký tự đặc biệt hoặc cấu trúc HTML ngoài ý muốn.

CID chỉ giải quyết **tham chiếu đến resource trong MIME**; nó không làm sạch dữ liệu HTML, không kiểm soát URL bên ngoài và không ngăn việc một template chứa liên kết độc hại.

Nếu tạo CID động từ dữ liệu đầu vào, phải kiểm tra và mã hóa phù hợp. Trong phần lớn use case, tốt hơn là đặt danh sách ID cố định do ứng dụng quản lý, ví dụ **brandLogo** và **productPhoto**.

## 14. MIME và hành vi email client

Thực tế, HTML email phải hoạt động trên nhiều email client với mức hỗ trợ HTML/CSS khác nhau. Một thư có MIME đúng vẫn có thể hiển thị khác nhau tùy thiết bị, client và chính sách bảo mật.

Một số lưu ý:

- **Ảnh có thể bị chặn hiển thị**, kể cả khi được nhúng inline. Cần thuộc tính **alt** và nội dung text không phụ thuộc duy nhất vào ảnh.
- **CSS trong email có giới hạn**. Không trông chờ JavaScript hay các API trình duyệt để tải hoặc chỉnh sửa nội dung.
- **Đường dẫn cid** trong thuộc tính img src là cách phổ biến nhất. Không giả định mọi client sẽ hỗ trợ CID như nhau trong CSS background-image.
- **Ảnh quá lớn** làm tăng kích thước thông điệp và có thể chậm tải hoặc vượt giới hạn của SMTP server.
- **Định dạng ảnh** như PNG/JPEG thường dễ hỗ trợ hơn một số định dạng mới hoặc ảnh SVG có khả năng xử lý khác nhau giữa client.
- **Ảnh trong email không bảo đảm đã được xem**. Trạng thái gửi thành công không đồng nghĩa client đã mở/hiển thị phần hình.

### Fallback khi không thấy logo

Không nên đặt thông tin quan trọng như mã xác nhận, số tiền, hạn thanh toán hay đường dẫn hành động **chỉ trong ảnh**. Ngay cả khi logo không hiển thị, email vẫn phải truyền đạt được nội dung cốt lõi.

Ví dụ, thay vì hiển thị mỗi một ảnh có chữ “Đơn hàng đã hoàn tất”, hãy có thêm dòng văn bản:

~~~html
<img src="cid:brandLogo" alt="Logo thương hiệu" width="160">
<h2>Đơn hàng của bạn đã hoàn tất</h2>
<p>Vui lòng đăng nhập để xem chi tiết.</p>
~~~

Với nội dung tương đương trong phần **text/plain**, người dùng đọc email ở chế độ text vẫn nhận được thông điệp mà không cần ảnh.

## 15. Vì sao CID ảnh hưởng kích thước email?

Ảnh được thêm bằng addInline là một phần của nội dung MIME. Dữ liệu nhị phân thường được biểu diễn qua **Content-Transfer-Encoding**, ví dụ base64, khi truyền trong email. Việc mã hóa này làm nội dung thư lớn hơn kích thước byte gốc của ảnh, chưa kể các header và boundary MIME.

Ví dụ về mặt ý nghĩa:

~~~text
Logo PNG trên đĩa
       |
       v
MIME part image/png + Content-ID
       |
       v
Chuyển mã cho giao thức email (thường base64)
       |
       v
Tổng kích thước MimeMessage tăng
~~~

Hệ quả thiết kế:

1. Tối ưu logo và hình trước khi đóng gói.
2. Giới hạn số ảnh inline và dung lượng mỗi ảnh.
3. Cân nhắc ảnh remote cho nội dung lớn, nhưng phải hiểu rủi ro về khả năng hiển thị và quyền riêng tư.
4. Đọc giới hạn kích thước thông điệp của SMTP/ESP sử dụng.
5. Tránh nhúng cùng một dữ liệu ảnh nhiều lần dưới nhiều Content-ID khi không thật sự cần.

Base64 trong MIME là **mã hóa truyền tải**, không phải mã hóa bảo mật. Người có quyền truy cập vào raw email vẫn có thể giải mã nội dung ảnh.

## 16. Các lỗi thường gặp khi tham chiếu CID

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| HTML hiển thị biểu tượng ảnh vỡ | HTML dùng **cid:brandLogo** nhưng không có MIME part khớp Content-ID | Kiểm tra giá trị CID trong HTML và addInline, xem raw MIME. |
| Dùng **cid:brandLogo** làm tham số addInline | Truyền sai giá trị ID; addInline cần ID không kèm tiền tố cid: | Gọi **addInline("brandLogo", resource)**. |
| Ảnh không hiển thị khi thêm vào email | Helper không ở chế độ multipart thích hợp | Tạo helper với **MULTIPART_MODE_RELATED** hoặc **MIXED_RELATED**. |
| Ảnh hiển thị như attachment | Cây MIME/disposition hoặc cách client xử lý khác dự kiến | Kiểm tra multipart/related, Content-ID, Content-Type và client cụ thể. |
| Hình mất sau khi đổi nội dung HTML | Gọi addInline trước khi setText, làm thay đổi cấu trúc multipart | Đặt **setText(...) trước addInline(...)**. |
| File classpath không được tìm thấy | Resource không có trong JAR hoặc sai classpath | Kiểm tra vị trí **src/main/resources/mail/** và tên file. |
| Attachment/inline bị lỗi khi gửi | Resource không còn đọc được, stream đã đóng hoặc chỉ đọc được một lần | Dùng Resource có thể mở lại; không dùng stream một lần không kiểm soát. |
| Email client không xác định được kiểu ảnh | Content-Type sai hoặc Resource không có filename | Dùng overload **addInline(contentId, source, contentType)** phù hợp. |
| Hai ảnh bị đổi chỗ hoặc chọn nhầm | Hai phần dùng trùng Content-ID | Gán ID duy nhất cho từng tài nguyên. |
| Ảnh không hiện chỉ trên một client | Client chặn hình hoặc không hỗ trợ cấu trúc/CSS cụ thể | Giữ fallback plain text/alt và kiểm tra khả năng hỗ trợ của client. |
| Gửi thư bị SMTP reject vì quá lớn | Quá nhiều ảnh inline hoặc tài nguyên quá nặng | Tối ưu ảnh, giảm số tài nguyên, xem giới hạn provider. |
| Dùng URL local trong HTML | Viết **src="C:\\assets\\logo.png"** hoặc đường dẫn file server | Dùng **cid:** với addInline hoặc URL HTTPS hợp lệ. |
| Email gửi thành công nhưng vẫn vào Spam | Vấn đề uy tín gửi, xác thực miền hoặc nội dung/chính sách nhận | Điều tra SMTP/ESP, SPF/DKIM/DMARC và hệ thống mail đích; CID không tự khắc phục. |

## 17. Quan sát raw message để hiểu tham chiếu thực tế

Trong quá trình phát triển, gửi email tới một SMTP test inbox hoặc mail server thử nghiệm rồi xem **Show original / View source / Raw message** để quan sát header và các MIME part.

Những thông tin quan trọng cần xác định:

1. Phần HTML có **img src="cid:..."** đúng tên ID.
2. Có MIME body part chứa **Content-ID** tương ứng.
3. Body part có **Content-Type** hợp lệ, ví dụ **image/png**.
4. Các phần HTML và resource được nhóm trong quan hệ **multipart/related** thích hợp.
5. Nếu có plain text, quan hệ **multipart/alternative** giữ hai bản nội dung tương đương.
6. Nếu có file tải về, phần này được biểu diễn như attachment, không nhầm với ảnh inline.
7. Resource tồn tại và dữ liệu nhị phân được ghi đủ vào raw MIME.

Ví dụ raw MIME thường chứa:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

Không nhất thiết tất cả header xuất hiện đúng thứ tự trên; mail transport và client có thể chuẩn hóa hoặc sắp xếp lại header. Điều cần nhận ra là **sự liên kết logic giữa cid trong HTML và Content-ID của MIME part**.

**Lưu ý dữ liệu:** Raw email có thể chứa địa chỉ người nhận, liên kết xác nhận, token, nội dung cá nhân và attachment. Chỉ mở hoặc lưu lại trong môi trường được phép; không chép dữ liệu nhạy cảm vào log hoặc hệ thống theo dõi lỗi công khai.

## 18. CID và an toàn khi xử lý tài nguyên

Tài nguyên inline thường có vẻ vô hại vì chỉ là logo hoặc hình minh họa. Tuy nhiên, ứng dụng vẫn phải kiểm soát dữ liệu đưa vào email.

**Nguồn file:** Nếu lấy resource từ đường dẫn do người dùng cung cấp, cần ngăn path traversal và truy cập file ngoài phạm vi cho phép. Với file tĩnh, dùng ClassPathResource từ đường dẫn cố định do ứng dụng định nghĩa.

**Nguồn URL:** Nếu phải tải ảnh từ một URL bên ngoài rồi đưa vào MIME, cần giới hạn domain, mạng đích, dung lượng và thời gian tải để tránh SSRF và tắc nghẽn worker. Không trao quyền tự do cho một URL trong request làm ứng dụng tải bất kỳ tài nguyên mạng nội bộ nào.

**Nội dung file:** Kiểm tra loại dữ liệu thực tế, kích thước, định dạng và quyền sử dụng. Không dựa hoàn toàn vào phần mở rộng khi đặt Content-Type.

**Dữ liệu cá nhân:** Không dùng cùng một email cho nhiều người nếu nội dung chứa ảnh, biểu đồ hoặc mã hóa thông tin riêng của một người. Inline image không làm thay đổi quyền đọc nội dung của recipient.

**Logging và retention:** Không log body MIME, base64 ảnh nhạy cảm, OTP hoặc link đặt lại mật khẩu. Nếu hệ thống lưu thông điệp để retry, cần quản lý vòng đời và quyền truy cập dữ liệu/tệp đính kèm.

## 19. Mô hình tái sử dụng inline resource trong ứng dụng

Khi nhiều loại email sử dụng cùng một logo, nên gom tên CID và đường dẫn tài nguyên vào một thành phần dùng chung. Ví dụ:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MailBranding {

    public static final String LOGO_CID = "brandLogo";

    private MailBranding() {
    }

    public static void addBrandLogo(MimeMessageHelper helper)
            throws MessagingException {
        helper.addInline(
                LOGO_CID,
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );
    }
}
~~~

Một service có thể sử dụng:

~~~java
String htmlText = """
        <html lang="vi">
          <body>
            <img src="cid:brandLogo" alt="Logo thương hiệu">
            <p>Thông báo mới từ hệ thống.</p>
          </body>
        </html>
        """;

helper.setText(
        "Thông báo mới từ hệ thống.",
        htmlText
);
MailBranding.addBrandLogo(helper);
~~~

Ở đây giá trị **brandLogo** trong HTML và **MailBranding.LOGO_CID** phải được giữ đồng nhất. Trong dự án lớn, template có thể nhận giá trị CID từ một hằng số hoặc model chung, thay vì viết lại chuỗi ở nhiều nơi.

Nếu nhiều thương hiệu hoặc nhiều tenant sử dụng logo khác nhau, nên định tuyến đến resource đã được cấu hình/phê duyệt theo tenant. Không chỉ thay tên CID; ứng dụng còn phải bảo đảm đúng file và đúng quyền sử dụng tài nguyên.

## 20. Khi nào nên dùng CID và khi nào không?

**CID phù hợp khi:**

- Email HTML cần logo/icon nhỏ được đóng gói cùng nội dung.
- Không muốn phụ thuộc vào một URL công khai khi email client dựng phần ảnh.
- Hệ thống đã có tài nguyên ổn định và có thể đọc được tại thời điểm gửi.
- Có thể chấp nhận dung lượng MIME tăng lên so với HTML chỉ dùng link HTTP.
- Nội dung vẫn có phương án fallback khi ảnh bị chặn.

**Nên cân nhắc giải pháp khác khi:**

- Có rất nhiều ảnh lớn, vì dung lượng thư có thể vượt giới hạn của provider.
- Tài nguyên được cập nhật thường xuyên nhưng không cần lưu bản ảnh cố định trong từng email.
- Cần tương thích với email client vốn không hỗ trợ tốt ảnh CID.
- Có yêu cầu theo dõi tải ảnh hoặc vận hành CDN, và việc sử dụng remote image được phép về mặt quyền riêng tư.
- Nội dung thực sự cần người dùng tải về: dùng attachment, không dùng addInline chỉ để giả làm tệp tải xuống.

Chọn phương pháp dựa trên **mục đích nội dung**, **khả năng tương thích**, **giới hạn dung lượng**, **bảo mật** và **yêu cầu vận hành** thay vì chỉ chọn vì code ngắn.

## 21. Tổng kết

Trong **Spring Framework Mail**, để HTML tham chiếu một tài nguyên nhúng bằng CID, ứng dụng cần hai phần khớp nhau:

1. **HTML** tham chiếu tài nguyên qua cú pháp **cid:contentId**, ví dụ **img src="cid:brandLogo"**.
2. **MimeMessageHelper** thêm tài nguyên có Content-ID tương ứng bằng **addInline("brandLogo", resource, "image/png")**.

Thông điệp phải dùng **chế độ MIME multipart phù hợp**, thường dựa trên **multipart/related**; khi có plain text và file đính kèm, có thể lồng **multipart/alternative** và **multipart/mixed**. Khi dùng MimeMessageHelper, **đặt nội dung bằng setText(...) trước, rồi gọi addInline(...)**; đồng thời dùng resource có thể đọc lại và media type chính xác.

CID giúp đóng gói hình cùng email để client tìm theo Content-ID, nhưng không thay thế fallback text/alt, không bảo đảm hiển thị trên mọi email client và không tự bảo mật nội dung. Hiểu đúng mối liên hệ **HTML cid → MIME Content-ID → dữ liệu resource** là nền tảng để tạo email HTML có hình inline ổn định trong Spring Framework Mail.
