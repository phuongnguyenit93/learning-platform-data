# cid URL và Content-ID

Một email thông báo đơn hàng thường có logo, biểu tượng hoặc hình minh họa ngay bên trong phần HTML. Nếu ứng dụng chỉ đặt đường dẫn ảnh trên website vào thuộc tính `src`, trình đọc thư có thể phải tải ảnh từ Internet khi người nhận mở email. Một cách khác là **đính kèm dữ liệu ảnh ngay trong message** rồi tham chiếu ảnh đó từ HTML bằng một địa chỉ `cid:`.

Cơ chế này dựa trên hai thành phần liên kết với nhau:

- **Content-ID** là header MIME định danh một phần nội dung, chẳng hạn một ảnh PNG được đính kèm ở chế độ inline.
- **cid URL** là địa chỉ được dùng trong nội dung HTML để tham chiếu phần MIME có Content-ID tương ứng.

Trong **Spring Framework Mail**, `MimeMessageHelper.addInline(...)` giúp thêm tài nguyên inline và đặt Content-ID cho nó. HTML body có thể dùng `<img src="cid:...">` để hiển thị ảnh. Điều quan trọng là **giá trị Content-ID trong MIME và giá trị sau tiền tố `cid:` trong HTML phải khớp nhau**.

Bài này giải thích cấu trúc MIME, cách tạo CID, cách dùng `MimeMessageHelper` và `JavaMailSender`, những lưu ý về tài nguyên, kiểm thử và các lỗi thường gặp khi gửi email có ảnh inline.

## 1. Inline resource là gì?

Một email có thể chứa nhiều phần MIME: văn bản thuần, HTML, ảnh, tài liệu đính kèm. **Inline resource** là tài nguyên được đặt trong message để phần nội dung có thể tham chiếu và hiển thị nó tại một vị trí cụ thể.

Ví dụ email có logo:

~~~html
<html>
  <body>
    <h2>Đơn hàng đã được xác nhận</h2>
    <img src="cid:brand-logo" alt="Logo công ty">
    <p>Cảm ơn bạn đã mua hàng.</p>
  </body>
</html>
~~~

Ở đây `cid:brand-logo` không phải URL website và cũng không phải đường dẫn file trên máy chủ. Nó là một **tham chiếu tới MIME part** có Content-ID tương ứng trong cùng message.

Trong message, phần ảnh có thể có header dạng:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brand-logo>
Content-Disposition: inline
~~~

Dòng `Content-ID: <brand-logo>` định danh phần ảnh. Phần HTML tham chiếu bằng `cid:brand-logo`, bỏ cặp dấu ngoặc nhọn của header.

~~~mermaid
flowchart LR
    A["HTML body"] -->|"src = cid:brand-logo"| B["Content-ID: <brand-logo>"]
    B --> C["MIME part chứa logo.png"]
    C --> D["Trình đọc email hiển thị ảnh inline"]
~~~

Ảnh được gửi cùng email dưới dạng một phần của nội dung MIME. Người nhận không cần truy cập đường dẫn file nội bộ của ứng dụng để lấy ảnh đó.

## 2. Content-ID là gì?

**Content-ID** là header MIME dùng để nhận diện một phần nội dung trong message. Giá trị thường được biểu diễn theo dạng message-id nằm trong dấu ngoặc nhọn:

~~~text
Content-ID: <brand-logo>
~~~

Đối với HTML email, trình đọc thư có thể tìm MIME part có Content-ID được tham chiếu bởi một URL `cid:`.

Ví dụ:

| Vị trí | Giá trị |
| --- | --- |
| Header MIME của ảnh | `Content-ID: <brand-logo>` |
| Thuộc tính HTML | `src="cid:brand-logo"` |
| Giá trị truyền vào `addInline` | `brand-logo` |

Trong API `MimeMessageHelper.addInline(contentId, ...)`, truyền **ID** làm đối số. Không thêm tiền tố `cid:` và thông thường không tự thêm dấu ngoặc nhọn. Helper sẽ tạo header MIME thích hợp.

### 2.1. Content-ID phải khớp với cid URL

Giả sử helper thêm ảnh với ID:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png"
);
~~~

HTML phải tham chiếu đúng:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Nếu HTML viết `cid:company-logo` trong khi MIME part mang Content-ID `brand-logo`, trình đọc thư không tìm thấy tài nguyên tương ứng. Ảnh có thể bị hiển thị như ảnh hỏng hoặc bị ẩn.

**Không nên thêm cặp ngoặc nhọn vào URL HTML**:

~~~html
<!-- Đúng -->
<img src="cid:brand-logo" alt="Logo">

<!-- Không dùng dạng header ở trong cid URL -->
<img src="cid:<brand-logo>" alt="Logo">
~~~

Dấu ngoặc nhọn thuộc cách biểu diễn header Content-ID, còn cid URL tham chiếu giá trị ID theo cú pháp URL.

### 2.2. Chọn ID duy nhất

Một message có thể chứa nhiều ảnh inline:

~~~text
brand-logo
product-image
footer-banner
~~~

Mỗi phần cần một ID phân biệt để tham chiếu đúng. Theo nguyên tắc của Content-ID, nên dùng định danh duy nhất; khi gửi số lượng lớn email, tránh dùng một ID chung có thể va chạm trong các hệ thống xử lý hoặc khi message được tổng hợp.

Có thể tạo ID từ UUID:

~~~java
String contentId = "logo-" + UUID.randomUUID();
~~~

Nếu muốn định danh theo dạng có miền, có thể sử dụng một giá trị giống message-id như `logo-uuid@mail.example.org`, nhưng cần biểu diễn đúng các ký tự dành riêng khi tạo cid URL. Đối với ví dụ ứng dụng đơn giản, token ASCII an toàn như `logo-550e8400-e29b-41d4-a716-446655440000` thường dễ ghép và kiểm tra hơn.

Không dùng tên file tùy ý làm ID nếu tên có khoảng trắng, ký tự đặc biệt hoặc có thể trùng. Content-ID là định danh của **MIME part**, không phải tên file hiển thị.

## 3. cid URL hoạt động như thế nào?

`cid:` là URL scheme dùng để tham chiếu nội dung có Content-ID trong message. Ví dụ:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Trình đọc email phân tích HTML, nhận ra cid URL và tìm MIME part tương ứng trong cấu trúc message. Nếu tìm thấy phần ảnh với Content-ID phù hợp, nó có thể dùng byte ảnh đó để hiển thị.

Sự liên kết có thể hình dung:

~~~text
HTML part:
  <img src="cid:brand-logo">

Related image part:
  Content-Type: image/png
  Content-ID: <brand-logo>
  Content-Disposition: inline
  [dữ liệu ảnh]
~~~

### 3.1. cid URL không phải HTTP URL

Hai cách tham chiếu khác nhau:

~~~html
<!-- Ảnh tải từ website -->
<img src="https://cdn.example.org/images/logo.png" alt="Logo">

<!-- Ảnh được nhúng trong message -->
<img src="cid:brand-logo" alt="Logo">
~~~

Với URL HTTPS, trình đọc email có thể phải tải ảnh từ server bên ngoài. Với CID, dữ liệu ảnh đã nằm trong MIME message, nên trình đọc không cần gọi website để lấy chính ảnh đó.

CID không có nghĩa ảnh được mã hóa bí mật. Nội dung ảnh vẫn nằm trong email và có thể được người nhận lưu hoặc trích xuất như các phần MIME khác.

### 3.2. Ký tự đặc biệt trong Content-ID

Theo cú pháp cid URL, giá trị tham chiếu cần tuân theo quy tắc URL và percent-encoding đối với ký tự đặc biệt khi cần. Để tránh sai khác giữa thư viện và các email client, nên chọn Content-ID ngắn, ổn định trong một message và dùng các ký tự ASCII an toàn như chữ, số, dấu gạch ngang hoặc dấu chấm.

Nếu sử dụng ID có ký tự cần percent-encode, phải bảo đảm cid URL trong HTML biểu diễn cùng ID theo quy tắc tương ứng. Không tự encode tùy tiện cả chuỗi header hoặc thêm dấu ngoặc nhọn vào URL.

## 4. Quan hệ giữa multipart/related và inline resource

Ảnh CID thường được gửi trong một cấu trúc MIME `multipart/related`. Cấu trúc này biểu thị một nhóm các phần có quan hệ với nhau: một phần gốc, thường là HTML, và các tài nguyên mà phần HTML tham chiếu.

Sơ đồ khái niệm:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:brand-logo">
└── image/png
    ├── Content-ID: <brand-logo>
    └── Content-Disposition: inline
~~~

HTML là phần nội dung chính; ảnh là tài nguyên liên quan. Thông tin Content-ID giúp trình đọc thư ghép tham chiếu HTML với dữ liệu ảnh.

### 4.1. Khi có cả plain text và HTML

Email giao dịch thường muốn cung cấp plain text dự phòng cùng bản HTML có logo. Khi đó, cấu trúc có thể lồng multipart:

~~~text
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html
│       └── <img src="cid:brand-logo">
└── image/png
    └── Content-ID: <brand-logo>
~~~

Tùy cách dựng message và chế độ multipart, cấu trúc ngoài có thể khác hoặc có thêm `multipart/mixed` nếu message có tệp đính kèm. Điều quan trọng về mặt logic là HTML tham chiếu tới một ảnh thuộc cùng message và phần ảnh có Content-ID phù hợp.

`MimeMessageHelper` cung cấp các chế độ multipart để hỗ trợ các cấu trúc thường dùng. Với HTML có ảnh inline và có thể thêm attachment, chế độ `MULTIPART_MODE_MIXED_RELATED` thường là lựa chọn phù hợp.

### 4.2. Inline khác attachment thông thường

| Đặc điểm | Inline resource | Attachment |
| --- | --- | --- |
| Mục đích | Hiển thị trong body, thường được HTML tham chiếu bằng CID | Cho người nhận mở hoặc tải file |
| Header thường gặp | `Content-Disposition: inline` | `Content-Disposition: attachment` |
| HTML tham chiếu | `src="cid:..."` | Thường không cần tham chiếu |
| API Spring | `addInline(...)` | `addAttachment(...)` |
| Ví dụ | Logo, biểu tượng trong email | Hóa đơn PDF, bảng tính |

Một phần inline vẫn là dữ liệu đính kèm trong message theo nghĩa MIME, nhưng vai trò hiển thị của nó khác file attachment mà người dùng tải xuống.

## 5. Dùng MimeMessageHelper.addInline(...)

Trong Spring Mail, `MimeMessageHelper` cung cấp các overload `addInline` để thêm tài nguyên vào message và gắn Content-ID.

Các dạng sử dụng thường gặp:

~~~java
helper.addInline("brand-logo", resource);
~~~

hoặc chỉ rõ MIME content type:

~~~java
helper.addInline(
        "brand-logo",
        resource,
        "image/png"
);
~~~

Đối số đầu tiên là **Content-ID** để HTML tham chiếu. Đối số thứ hai là tài nguyên nội dung, thường là `Resource` hoặc `InputStreamSource`. Đối số thứ ba, khi sử dụng overload tương ứng, là MIME content type của tài nguyên.

### 5.1. Tạo helper ở chế độ multipart

Ví dụ đơn giản:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Tham số `true` bật chế độ multipart. Khi cần kiểm soát rõ cấu trúc có liên quan đến ảnh inline, có thể chọn chế độ:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);
~~~

`MULTIPART_MODE_MIXED_RELATED` hỗ trợ trường hợp message có các nội dung related và có thể chứa attachment ngoài. Với một message HTML đơn giản có ảnh inline, constructor multipart thông dụng cũng thường đủ.

### 5.2. Đặt HTML trước rồi thêm inline resource

Thứ tự gọi có ý nghĩa với `MimeMessageHelper`. Nên **gọi `setText(...)` trước, rồi gọi `addInline(...)`**:

~~~java
helper.setText(
        "<html><body>"
        + "<img src=\"cid:brand-logo\" alt=\"Logo\">"
        + "<p>Đơn hàng đã được xác nhận.</p>"
        + "</body></html>",
        true
);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);
~~~

Nếu gọi `addInline` trước `setText`, một số thao tác đặt body có thể thay đổi cấu trúc multipart và ảnh hưởng tới các phần đã thêm. Tài liệu Spring khuyến nghị đặt text trước rồi thêm inline elements để tránh các vấn đề tương thích.

### 5.3. Không đưa tiền tố cid: vào addInline

Ví dụ đúng:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

HTML tương ứng:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Không viết:

~~~java
helper.addInline("cid:brand-logo", logoResource, "image/png");
~~~

Bởi vì `addInline` nhận **Content-ID**, còn `cid:` là scheme trong URL mà HTML sử dụng để tham chiếu.

## 6. Ví dụ hoàn chỉnh: gửi email HTML có logo inline

Giả sử file logo nằm trong:

~~~text
src/main/resources/mail/images/logo.png
~~~

Ứng dụng có Spring Boot Mail starter và SMTP đã được cấu hình.

### 6.1. Phụ thuộc

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

### 6.2. Dịch vụ gửi thư

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InlineImageMailService {

    private final JavaMailSender mailSender;

    public InlineImageMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(String recipient)
            throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Địa chỉ người nhận không được để trống"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        String contentId = "brand-logo-" + UUID.randomUUID();

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("Đơn hàng của bạn đã được xác nhận");

        String html = """
                <html>
                  <body>
                    <div>
                      <img src="cid:%s"
                           alt="Logo công ty"
                           width="160">
                    </div>
                    <h2>Đơn hàng đã được xác nhận</h2>
                    <p>Cảm ơn bạn đã mua hàng.</p>
                  </body>
                </html>
                """.formatted(contentId);

        // Đặt body trước khi thêm tài nguyên inline.
        helper.setText(html, true);

        ClassPathResource logo =
                new ClassPathResource("mail/images/logo.png");

        helper.addInline(contentId, logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Ví dụ giả định logo có thật trong classpath và `From` được SMTP provider cho phép. `UUID.randomUUID()` giúp tránh dùng chung một ID cho nhiều lần gửi. CID được đặt vào HTML và dùng làm đối số `addInline` nên hai nơi luôn khớp.

### 6.3. Điều gì xảy ra khi gửi?

1. `createMimeMessage()` tạo một message mới.
2. `MimeMessageHelper` được khởi tạo ở chế độ multipart.
3. Ứng dụng tạo Content-ID cho ảnh.
4. `setText(html, true)` đặt HTML body có URL `cid:...`.
5. `addInline(...)` thêm byte ảnh và header Content-ID tương ứng.
6. `JavaMailSender.send(message)` chuyển message qua SMTP đã cấu hình.

Khi email client xử lý message, nó tìm ảnh trong các MIME part liên quan dựa trên Content-ID. Nếu ảnh tồn tại, CID đúng và client hỗ trợ hiển thị inline, logo có thể xuất hiện ngay trong body.

## 7. Sử dụng Resource từ classpath, file hoặc bộ nhớ

`addInline` cần một nguồn dữ liệu mà Jakarta Mail có thể đọc khi serialize message. Spring cung cấp các loại `Resource` hữu ích.

| Nguồn | Ví dụ | Trường hợp phù hợp |
| --- | --- | --- |
| `ClassPathResource` | `new ClassPathResource("mail/images/logo.png")` | Ảnh tĩnh đóng gói cùng ứng dụng. |
| `FileSystemResource` | `new FileSystemResource(path)` | File đã được ứng dụng lưu ở vị trí được kiểm soát. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Nội dung đã được đọc và kiểm tra trong bộ nhớ. |
| `InputStreamSource` | Nguồn tạo stream mới mỗi lần được yêu cầu | Tích hợp nguồn dữ liệu tùy chỉnh có thể đọc lại. |

### 7.1. ClassPathResource

Đây là lựa chọn gọn cho logo hoặc icon do ứng dụng quản lý:

~~~java
Resource logo =
        new ClassPathResource("mail/images/logo.png");

helper.addInline("brand-logo", logo, "image/png");
~~~

Đường dẫn tính từ classpath, thường tương ứng với file trong `src/main/resources` khi chạy dự án. Không dùng đường dẫn Windows hoặc đường dẫn tuyệt đối của máy phát triển làm CID; Content-ID không liên quan đến vị trí file trên máy chủ.

### 7.2. FileSystemResource

Nếu ảnh nằm ngoài classpath, có thể dùng `FileSystemResource`:

~~~java
Resource image =
        new FileSystemResource("/srv/app/mail/logo.png");

helper.addInline("brand-logo", image, "image/png");
~~~

Đường dẫn chỉ là ví dụ trên môi trường Linux. Trong ứng dụng thực, file phải nằm trong vùng lưu trữ mà ứng dụng được phép đọc. Không ghép trực tiếp một path tùy ý từ request vào `FileSystemResource`; trước đó phải kiểm soát quyền truy cập và vị trí lưu file.

### 7.3. ByteArrayResource

Nếu ảnh đã được đọc vào byte array và kiểm tra trước:

~~~java
byte[] imageBytes = loadApprovedImage();

Resource image = new ByteArrayResource(imageBytes);

helper.addInline("brand-logo", image, "image/png");
~~~

`ByteArrayResource` phù hợp với dữ liệu có kích thước giới hạn và có thể đọc lại. Cần kiểm soát dung lượng để tránh giữ ảnh lớn trong bộ nhớ cùng lúc với nhiều email.

### 7.4. InputStreamSource cần đọc lại được

Quá trình dựng hoặc gửi MIME có thể đọc nguồn dữ liệu nhiều hơn một lần. Vì vậy, `InputStreamSource.getInputStream()` nên cung cấp **một stream mới cho mỗi lần gọi**, nếu loại nguồn hỗ trợ.

Không nên mở một `InputStream` duy nhất, đọc cạn nó rồi dùng lại cho nhiều thao tác. Những resource dạng stream chỉ đọc một lần có thể dẫn tới attachment rỗng hoặc lỗi khi provider serialize message.

Các resource như `ClassPathResource`, `FileSystemResource` và `ByteArrayResource` thường phù hợp hơn vì có thể mở lại nội dung theo cách triển khai của chúng.

## 8. Content-Type của ảnh inline

Content-ID chỉ xác định **phần nào** được tham chiếu; Content-Type cho biết **dữ liệu đó là loại nội dung gì**.

Ví dụ:

| Loại ảnh | Content-Type |
| --- | --- |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml` |

Với ảnh raster phổ biến như PNG hoặc JPEG, nên khai báo MIME type chính xác:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

Nếu file thực sự là JPEG mà lại khai báo `image/png`, trình đọc email có thể không giải mã đúng. Không nên chỉ dựa vào phần mở rộng do người dùng cung cấp; MIME type nên được xác định từ nội dung đã kiểm tra hoặc từ nguồn tài nguyên đáng tin cậy.

### Không tin Content-Type do client tự khai báo

Khi upload file, client có thể gửi header `Content-Type` không chính xác. Nếu ứng dụng lấy nguyên giá trị đó rồi đưa vào MIME part, nó có thể mô tả sai dữ liệu. Cần xác minh loại file bằng cơ chế phù hợp, kiểm tra nội dung và chỉ chấp nhận các loại được cho phép.

Việc nhận dạng file bằng magic bytes cũng có giới hạn; nó nên kết hợp với chính sách loại file, kiểm tra kích thước và quét nội dung khi phù hợp.

## 9. CID URL và Content-ID có phải đường dẫn công khai không?

Không. CID chỉ có ý nghĩa trong phạm vi message chứa MIME part đó. Ví dụ `cid:brand-logo` không thể được dán vào trình duyệt để truy cập một ảnh trên website.

Nếu người nhận chuyển tiếp email hoặc ứng dụng mail lưu trữ lại message, tài nguyên inline có thể được giữ trong message được chuyển tiếp. Nhưng CID không phải một địa chỉ bền vững để các ứng dụng bên ngoài truy cập độc lập.

Cần phân biệt:

| Giá trị | Có thể mở trực tiếp trên trình duyệt? | Phạm vi |
| --- | --- | --- |
| `https://cdn.example.org/logo.png` | Có, nếu server công khai và truy cập được | Tài nguyên web |
| `cid:brand-logo` | Không như một URL web độc lập | MIME message hiện tại |
| `file:///srv/app/logo.png` | Không phải URL hợp lệ cho người nhận email truy cập file server | Máy cục bộ/host |
| `/static/logo.png` | Không đủ ngữ cảnh cho người nhận bên ngoài | Đường dẫn tương đối |

Không đặt đường dẫn local hoặc URL tương đối vào `src` của email rồi mong người nhận nhìn thấy file. Hãy nhúng resource bằng CID hoặc dùng URL HTTPS công khai phù hợp với chính sách hiển thị ảnh từ xa.

## 10. CID, ảnh từ xa và ảnh đính kèm: chọn cách nào?

Có ba cách phổ biến để hiển thị ảnh trong email:

| Cách | Dữ liệu ảnh nằm ở đâu? | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| CID inline | Trong MIME message | Không cần tải ảnh từ website khi mở thư; phù hợp logo/ảnh nhỏ | Tăng dung lượng email; cần MIME client hỗ trợ |
| HTTPS remote image | Trên server/CDN | Email nhỏ hơn; cập nhật ảnh trên server | Client có thể chặn ảnh từ xa; phát sinh request khi tải |
| Attachment thông thường | Trong message, disposition attachment | Người nhận có thể tải file | Không nhất thiết hiển thị tại vị trí trong HTML |

CID hữu ích cho **logo, biểu tượng và ảnh minh họa nhỏ cần đi cùng nội dung**. Với ảnh lớn hoặc nội dung thay đổi thường xuyên, ảnh remote từ CDN có thể phù hợp hơn nếu chính sách riêng tư và client mục tiêu cho phép. Với PDF hoặc tài liệu cần tải về, dùng `addAttachment`.

Không nên nhúng toàn bộ thư viện ảnh hoặc file dung lượng lớn vào mọi email nếu người nhận chỉ cần một logo nhỏ. Mỗi inline image đều làm message lớn hơn.

### 10.1. CID không bảo đảm client luôn hiển thị ảnh

Trình đọc thư có thể có chính sách riêng: tắt hình ảnh, hạn chế loại MIME, hoặc hiển thị nội dung inline theo cách khác. Do đó, luôn cung cấp `alt` có ý nghĩa:

~~~html
<img src="cid:brand-logo" alt="Logo công ty">
~~~

Nội dung quan trọng không nên chỉ tồn tại trong hình ảnh. Ví dụ mã đơn hàng, trạng thái và hướng dẫn cần được thể hiện bằng văn bản thực tế trong body.

### 10.2. CID không phải cơ chế bảo vệ quyền riêng tư tuyệt đối

Ảnh CID được gửi trong message; người nhận có thể lưu ảnh. CID tránh một request tải ảnh từ xa khi mở email, nhưng không ngăn người nhận chia sẻ message hoặc trích xuất dữ liệu. Không đưa bí mật hoặc dữ liệu cá nhân không cần thiết vào ảnh inline.

## 11. Nhiều inline resource trong cùng message

Một email có thể cần logo, biểu tượng trạng thái và ảnh sản phẩm:

~~~java
String logoId = "logo-" + UUID.randomUUID();
String statusId = "status-" + UUID.randomUUID();
String productId = "product-" + UUID.randomUUID();

String html = """
        <html>
          <body>
            <img src="cid:%s" alt="Logo">
            <h2>Đơn hàng đã được xác nhận</h2>
            <img src="cid:%s" alt="Đã xác nhận">
            <p>Sản phẩm:</p>
            <img src="cid:%s" alt="Ảnh sản phẩm">
          </body>
        </html>
        """.formatted(logoId, statusId, productId);

helper.setText(html, true);

helper.addInline(
        logoId,
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);

helper.addInline(
        statusId,
        new ClassPathResource("mail/images/confirmed.png"),
        "image/png"
);

helper.addInline(
        productId,
        productImageResource,
        "image/jpeg"
);
~~~

Ví dụ giả định `productImageResource` đã được khai báo và là resource có thể đọc lại. Mỗi ảnh có một Content-ID riêng, và mỗi URL trong HTML tham chiếu đúng ID của ảnh tương ứng.

Nên quản lý các ID trong biến hoặc một cấu trúc dữ liệu nhỏ thay vì gõ lặp chuỗi ở nhiều vị trí. Điều này giảm lỗi chính tả và giúp test xác nhận mọi CID được tham chiếu đều có MIME part tương ứng.

## 12. Kết hợp inline resource với attachment PDF

Một email có thể vừa hiển thị logo inline vừa đính kèm hóa đơn PDF. Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name()
);

String logoId = "logo-" + UUID.randomUUID();

helper.setFrom("billing@example.org");
helper.setTo(recipient);
helper.setSubject("Hóa đơn của bạn");

String html = """
        <html>
          <body>
            <img src="cid:%s" alt="Logo công ty" width="140">
            <h2>Hóa đơn đã sẵn sàng</h2>
            <p>Vui lòng xem file PDF đính kèm.</p>
          </body>
        </html>
        """.formatted(logoId);

helper.setText(
        "Hóa đơn đã sẵn sàng. Vui lòng xem file PDF đính kèm.",
        html
);

helper.addInline(
        logoId,
        new ClassPathResource("mail/images/logo.png"),
        "image/png"
);

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf"
);

mailSender.send(message);
~~~

Ví dụ giả định `invoiceResource` là một `InputStreamSource`/`Resource` hợp lệ, có thể đọc trong lúc gửi và chứa PDF đã được tạo, kiểm tra. Cần chọn chế độ multipart phù hợp và tuân theo thứ tự đặt text trước inline resource.

Mô hình khái niệm:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       └── <img src="cid:logo-id">
│   └── image/png
│       └── Content-ID: <logo-id>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Cấu trúc MIME chính xác do helper và Jakarta Mail dựng. Sơ đồ nhằm minh họa vai trò của các phần: HTML tham chiếu ảnh inline, còn PDF là attachment riêng.

## 13. Kiểm tra message có Content-ID đúng hay không

Trong môi trường phát triển, có thể đọc các header của MIME message:

~~~java
String[] contentIds = message.getHeader("Content-ID");
~~~

Đối với message có multipart, Content-ID của ảnh nằm trên **part ảnh**, không nhất thiết nằm ở cấp message ngoài. Vì vậy, chỉ gọi `message.getHeader("Content-ID")` không đủ để tìm mọi inline resource.

Có thể duyệt cấu trúc multipart bằng API Jakarta Mail để kiểm tra từng part:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;

static void inspectParts(MimeMessage message)
        throws Exception {

    Object content = message.getContent();

    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart part = multipart.getBodyPart(i);

            String contentType = part.getContentType();
            String disposition = part.getDisposition();
            String[] ids = part.getHeader("Content-ID");

            System.out.println("Part: " + contentType);
            System.out.println("Disposition: " + disposition);

            if (ids != null) {
                for (String id : ids) {
                    System.out.println("Content-ID: " + id);
                }
            }

            // Multipart có thể được lồng trong một part khác.
            Object nested = part.getContent();
            if (nested instanceof Multipart nestedMultipart) {
                inspectMultipart(nestedMultipart);
            }
        }
    }
}

static void inspectMultipart(Multipart multipart)
        throws Exception {

    for (int i = 0; i < multipart.getCount(); i++) {
        BodyPart part = multipart.getBodyPart(i);

        System.out.println("Part: " + part.getContentType());

        String[] ids = part.getHeader("Content-ID");
        if (ids != null) {
            for (String id : ids) {
                System.out.println("Content-ID: " + id);
            }
        }

        Object nested = part.getContent();
        if (nested instanceof Multipart nestedMultipart) {
            inspectMultipart(nestedMultipart);
        }
    }
}
~~~

Đây là ví dụ quan sát mang tính minh họa, có thể đơn giản hóa tùy cấu trúc thực tế; trong mã production cần tránh đọc lặp toàn bộ stream hoặc in nội dung nhạy cảm. Việc kiểm tra nên xác nhận:

- HTML chứa CID dự kiến.
- Có MIME part với Content-ID khớp.
- MIME type của part là loại ảnh được mong đợi.
- Disposition phù hợp với mục đích inline.
- Tài nguyên có dữ liệu và có thể serialize.

Không dựa vào việc header ở cấp ngoài có Content-ID để kết luận ảnh inline đã được thêm đúng.

## 14. Các lỗi thường gặp khi dùng cid URL và Content-ID

### 14.1. Không khớp Content-ID và cid URL

**Sai:**

~~~java
helper.addInline("brand-logo", logo, "image/png");
~~~

~~~html
<img src="cid:company-logo" alt="Logo">
~~~

Hai ID khác nhau nên client không tìm được ảnh. Hãy dùng cùng một biến `contentId` cho cả HTML và `addInline`.

### 14.2. Đưa cid: vào tham số addInline

**Sai:**

~~~java
helper.addInline("cid:brand-logo", logo, "image/png");
~~~

**Đúng:**

~~~java
helper.addInline("brand-logo", logo, "image/png");
~~~

`cid:` thuộc URL trong HTML; tham số của helper là Content-ID.

### 14.3. Đưa ngoặc nhọn vào src

**Sai:**

~~~html
<img src="cid:<brand-logo>" alt="Logo">
~~~

**Đúng:**

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Dấu ngoặc nhọn xuất hiện trong header Content-ID theo dạng `<brand-logo>`; không sao chép nguyên phần header đó vào cid URL.

### 14.4. Gọi addInline trước setText

Việc đặt body sau khi thêm inline resource có thể làm thay đổi cấu trúc multipart và khiến phần inline không được giữ như mong đợi.

**Cách làm:** gọi `setText(...)` trước, rồi `addInline(...)`, sau đó mới gửi message.

### 14.5. Không bật multipart

Nếu helper được tạo ở chế độ non-multipart:

~~~java
new MimeMessageHelper(message, false, "UTF-8");
~~~

thì việc thêm inline resource không phù hợp với cấu trúc message cần thiết và có thể gây lỗi. Hãy bật multipart hoặc chọn multipart mode rõ ràng.

### 14.6. Nhầm attachment với inline resource

Dùng `addAttachment` tạo file đính kèm để tải về, không phải cách phù hợp để HTML tham chiếu ảnh bằng CID. Dùng `addInline` cho tài nguyên được body tham chiếu.

### 14.7. MIME type không đúng

File PNG nhưng khai báo `image/jpeg` có thể làm client giải mã sai. Xác định MIME type từ nội dung được kiểm tra, không tin hoàn toàn metadata upload của client.

### 14.8. Resource không còn đọc được

Một `Resource` có thể tồn tại lúc tạo message nhưng không còn khả dụng khi Jakarta Mail serialize. Dùng resource có vòng đời rõ ràng và khả năng đọc lại; xử lý lỗi I/O trong quy trình gửi.

### 14.9. Dùng InputStream chỉ đọc được một lần

Một stream đã bị đọc cạn không thể tự quay lại đầu. Hãy dùng resource có thể mở stream mới, chẳng hạn `ClassPathResource` hoặc `ByteArrayResource`, hoặc một `InputStreamSource` được triển khai để trả về stream mới mỗi lần.

### 14.10. CID trùng giữa nhiều ảnh

Nếu nhiều phần có cùng Content-ID, việc phân giải tham chiếu có thể trở nên mơ hồ. Tạo ID duy nhất cho từng ảnh trong message và dùng một nguồn duy nhất để dựng HTML với danh sách inline resource.

### 14.11. Kích thước ảnh quá lớn

Inline image làm tăng dung lượng message; dữ liệu binary khi chuyển qua MIME có thể được Base64 encode, khiến phần dữ liệu truyền lớn hơn file gốc. Resize và tối ưu ảnh trước khi gửi, đồng thời tuân theo giới hạn của provider.

### 14.12. Mong ảnh luôn hiển thị trong mọi email client

Client có thể tắt hình ảnh, không hỗ trợ một định dạng hoặc trình bày khác. Thêm `alt`, giữ thông tin quan trọng trong văn bản và kiểm thử trên các ứng dụng đọc thư mục tiêu.

## 15. Kiểm thử email có inline resource

Có thể kiểm thử ở nhiều tầng mà không gửi thư thật ra Internet.

### 15.1. Unit test cho cách dựng message

Thay `JavaMailSender` bằng mock/fake để thu `MimeMessage` được tạo và xác nhận:

- Subject, From và To được đặt đúng.
- Body HTML có `src="cid:..."`.
- MIME part ảnh có Content-ID trùng với giá trị trong HTML.
- Content-Type là `image/png` hoặc loại được mong đợi.
- Message được dựng ở chế độ multipart.

Với message multipart lồng nhau, test nên duyệt các part thay vì giả định ảnh luôn nằm ở chỉ số cố định trong multipart cấp ngoài.

### 15.2. Integration test với SMTP test server

Một SMTP server dùng cho kiểm thử có thể nhận email và cho phép xem MIME raw. Đây là cách tốt để kiểm tra:

- MIME boundary được tạo đúng.
- `Content-ID` nằm trên part ảnh.
- `Content-Disposition` thể hiện mục đích inline.
- HTML tham chiếu đúng cid URL.
- Ảnh có byte dữ liệu và content type phù hợp.

SMTP test server nên được cấu hình riêng cho môi trường test, không dùng credential production và không chuyển thư thử ra người nhận thật.

### 15.3. Kiểm tra trên email client

Sau khi xác nhận MIME, nên mở thư thử trên các client mục tiêu. Kiểm tra logo có xuất hiện đúng kích thước, alt text có ý nghĩa, bố cục không phụ thuộc duy nhất vào ảnh và các attachment khác vẫn hoạt động.

Một message hợp lệ về cấu trúc MIME không bảo đảm mọi client có cùng cách hiển thị. Việc kiểm thử giao diện vẫn cần thiết nếu hình ảnh đóng vai trò quan trọng.

## 16. Quyền riêng tư và hiệu năng của inline resource

CID inline có một số đặc tính vận hành cần cân nhắc:

- **Dung lượng:** ảnh được gửi trong từng email; gửi cùng một logo cho hàng nghìn người sẽ nhân dung lượng truyền theo số message.
- **Bộ nhớ:** khi dựng nhiều message song song, các byte ảnh và dữ liệu MIME có thể chiếm bộ nhớ đáng kể.
- **Cache:** ảnh inline thuộc từng message; không có cơ chế CDN cache chung như URL remote.
- **Quyền riêng tư:** không tạo request tải ảnh từ xa khi mở thư theo cách remote image thường hoạt động, nhưng bản thân email vẫn chứa ảnh và người nhận có thể trích xuất.
- **Khả năng hiển thị:** client vẫn có thể chặn hoặc không hiển thị ảnh vì chính sách riêng.
- **Bản quyền và dữ liệu:** chỉ nhúng hình ảnh ứng dụng có quyền sử dụng và phù hợp với người nhận.

Với logo nhỏ dùng chung, CID thường thuận tiện. Với ảnh sản phẩm lớn, ảnh động hoặc gallery, nên cân nhắc URL CDN và chính sách tải ảnh từ xa thay vì nhúng tất cả vào message.

## 17. Câu hỏi thực hành

**Câu 1.** Nếu gọi `helper.addInline("brand-logo", logo, "image/png")` thì HTML nên tham chiếu thế nào?

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Giá trị sau `cid:` phải khớp Content-ID mà helper tạo.

**Câu 2.** Có cần truyền `cid:brand-logo` vào `addInline` không?

Không. `addInline` nhận Content-ID, còn tiền tố `cid:` chỉ xuất hiện trong URL ở body HTML.

**Câu 3.** Vì sao header là `Content-ID: <brand-logo>` nhưng HTML là `cid:brand-logo`?

Header MIME biểu diễn Content-ID trong dấu ngoặc nhọn. Cid URL tham chiếu ID mà không đưa nguyên cặp dấu ngoặc nhọn vào URL.

**Câu 4.** Có thể đặt `src="/images/logo.png"` trong email để người nhận tải ảnh từ ứng dụng Spring không?

Không nên. Đường dẫn tương đối không có host của website cho người nhận bên ngoài. Dùng CID hoặc URL HTTPS tuyệt đối do ứng dụng quản lý.

**Câu 5.** Có thể gọi `addAttachment("logo.png", logo)` rồi tham chiếu `cid:logo` không?

Không tự động. Attachment thông thường không có hợp đồng CID tương ứng. Dùng `addInline` và tham chiếu đúng Content-ID.

**Câu 6.** Vì sao nên gọi `setText` trước `addInline`?

Vì helper tổ chức cấu trúc multipart khi đặt body. Thêm inline resource sau khi body đã được đặt giúp tránh thao tác đặt text làm thay đổi cấu trúc chứa resource.

**Câu 7.** Một email có logo và icon trạng thái. Hai ảnh có thể dùng cùng Content-ID không?

Không nên. Mỗi inline part cần ID riêng để URL tham chiếu không bị mơ hồ.

**Câu 8.** `cid:brand-logo` có phải URL mở được trong trình duyệt không?

Không. Nó tham chiếu một MIME part trong message hiện tại, không phải tài nguyên web độc lập.

**Câu 9.** Đặt `Content-Type: image/png` có bảo đảm dữ liệu là PNG không?

Không. Header chỉ mô tả loại nội dung. Ứng dụng phải xác minh byte ảnh hoặc lấy dữ liệu từ nguồn tin cậy trước khi khai báo.

**Câu 10.** `send(...)` trả về bình thường có chứng minh người nhận nhìn thấy logo không?

Không. Nó chỉ phản ánh thao tác gửi được SMTP relay chấp nhận theo phản hồi nhận được. Khả năng hiển thị còn phụ thuộc MIME thực, client và chính sách hiển thị ảnh.

## 18. Mô hình ghi nhớ

Để gửi ảnh inline trong Spring Framework Mail, hãy kết nối ba phần:

~~~mermaid
flowchart TD
    A["HTML body"] --> B["src = cid:logo-id"]
    C["MimeMessageHelper.addInline"] --> D["Content-ID: <logo-id>"]
    D --> E["MIME part image/png"]
    B --> F["Trình đọc email ghép CID với MIME part"]
    E --> F
    G["JavaMailSender.send(message)"] --> F
~~~

Các nguyên tắc chính:

1. **Content-ID định danh MIME part** chứa ảnh hoặc tài nguyên inline.
2. **cid URL tham chiếu Content-ID** từ HTML; giá trị sau `cid:` phải khớp ID đã thêm.
3. **`addInline` nhận ID, không nhận tiền tố `cid:`**; helper chịu trách nhiệm tạo header Content-ID.
4. **Message cần multipart phù hợp.** Với inline resource, bật multipart và chọn mode thích hợp.
5. **Đặt body trước rồi thêm inline resource.** Dùng `setText(...)` trước `addInline(...)`.
6. **Resource cần đọc được khi serialize.** Ưu tiên nguồn có thể mở stream mới, khai báo Content-Type đúng và kiểm soát kích thước.
7. **Inline không giống attachment thông thường.** Dùng `addInline` cho ảnh được HTML tham chiếu; dùng `addAttachment` cho file tải về.
8. **CID không phải URL công khai.** Nó chỉ có ý nghĩa trong message chứa MIME part.
9. **Không phụ thuộc hoàn toàn vào ảnh.** Cung cấp alt text và thể hiện thông tin quan trọng bằng văn bản.
10. **Kiểm thử MIME và client thực tế.** Kiểm tra Content-ID, cid URL, MIME type, dữ liệu ảnh và khả năng hiển thị.

Trong một email Spring, `MimeMessageHelper` giúp liên kết HTML body với resource inline; Jakarta Mail đóng gói các phần trong cấu trúc MIME; `JavaMailSender` gửi toàn bộ message qua SMTP. Khi Content-ID và cid URL khớp nhau, trình đọc thư có thể tìm đúng ảnh đã được nhúng và hiển thị nó tại vị trí mong muốn trong nội dung HTML.
