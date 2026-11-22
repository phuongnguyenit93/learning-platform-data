# Mục đích của tài nguyên inline trong email HTML

## 1. Tài nguyên inline là gì?

Email HTML có thể chứa hình ảnh, biểu tượng hoặc những tài nguyên khác cần xuất hiện ngay trong phần nội dung. Ví dụ, một email xác nhận đơn hàng có thể hiển thị logo thương hiệu ở đầu thư, ảnh sản phẩm cạnh thông tin đơn hàng hoặc biểu đồ nhỏ trong phần báo cáo.

Một cách thực hiện là **đưa tài nguyên vào chính thông điệp email dưới dạng một MIME part có quan hệ với phần HTML**, sau đó để HTML tham chiếu tới part đó. Trong email, cách này thường được gọi là **inline resource**. Với Spring Framework Mail, lớp **MimeMessageHelper** hỗ trợ thêm tài nguyên inline thông qua phương thức **addInline(...)**.

Ví dụ HTML tham chiếu logo:

~~~html
<img src="cid:brandLogo" alt="Logo thương hiệu">
~~~

Java thêm ảnh tương ứng:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

Ở đây, **cid:brandLogo** là tham chiếu từ HTML đến một MIME part có **Content-ID** tương ứng. Ảnh được đóng gói trong email; email client có thể đọc part đó và hiển thị ở vị trí của thẻ img khi hỗ trợ kiểu nội dung này.

Tài nguyên inline thường được dùng cho logo, icon, hình minh họa nhỏ hoặc biểu đồ cần đi cùng nội dung thư. Nó giúp email không phải tải ảnh từ một URL bên ngoài để hiển thị phần hình đó. Tuy nhiên, **inline không bảo đảm mọi email client sẽ luôn hiển thị ảnh**: client có thể chặn hình, giới hạn HTML hoặc trình bày MIME khác nhau.

## 2. Vì sao email HTML cần tài nguyên inline?

Một email chỉ có văn bản có thể truyền tải thông tin mà không cần ảnh. Nhưng một số thông điệp có hình ảnh hỗ trợ cách đọc và nhận diện:

- **Logo thương hiệu** giúp người nhận nhận biết nguồn gửi.
- **Icon trạng thái** giúp phân biệt thành công, cảnh báo hoặc thông tin.
- **Ảnh sản phẩm** giúp người nhận nhận ra mặt hàng được đề cập.
- **Biểu đồ hoặc hình minh họa** giúp tóm tắt báo cáo.
- **Sơ đồ nhỏ** có thể giải thích quy trình hoặc trạng thái.
- **Ảnh chữ ký** có thể dùng trong một số mẫu thông báo, nếu vẫn có thông tin văn bản tương đương.

Ví dụ email xác nhận đơn hàng có thể có phần đầu:

~~~text
+-----------------------------------+
|          Logo thương hiệu         |
|                                   |
|      Đơn hàng đã được xác nhận    |
|                                   |
|      Mã đơn hàng: ORD-2026-015    |
|      Trạng thái: Đang xử lý       |
|                                   |
|           [Xem đơn hàng]          |
+-----------------------------------+
~~~

Logo có thể được nhúng inline để nằm cùng thông điệp. Nội dung về mã đơn hàng, trạng thái và hành động vẫn phải là văn bản/HTML thực, không nên biến toàn bộ thông tin quan trọng thành một ảnh duy nhất.

### Những mục đích chính

| Mục đích | Ví dụ | Lợi ích |
|---|---|---|
| Nhận diện | Logo ở đầu email | Giữ hình ảnh thương hiệu trong nội dung thư |
| Minh họa | Ảnh sản phẩm hoặc sơ đồ | Giúp người nhận hiểu đối tượng được đề cập |
| Trực quan hóa | Biểu đồ nhỏ trong báo cáo | Cho phép đọc nhanh một xu hướng |
| Trạng thái | Icon cảnh báo hoặc hoàn tất | Hỗ trợ nhận biết trạng thái |
| Bố cục | Hình trang trí nhỏ | Tạo điểm nhấn cho mẫu HTML |

Không phải email nào cũng cần ảnh inline. Với một thông báo đơn giản như mã OTP hoặc thông tin xác nhận ngắn, nội dung text có thể rõ ràng và nhẹ hơn. Chỉ thêm ảnh khi nó hỗ trợ một mục đích cụ thể và có phương án thay thế khi ảnh không hiển thị.

## 3. Ba cách đưa hình ảnh vào email HTML

Có ba cách phổ biến để HTML email sử dụng hình:

| Cách | Ví dụ trong HTML | Dữ liệu ảnh nằm ở đâu? | Đặc điểm |
|---|---|---|---|
| **Remote image** | img src="https://static.example.com/logo.png" | Trên máy chủ web/CDN | Email client cần truy cập URL để tải ảnh |
| **Inline resource bằng CID** | img src="cid:brandLogo" | Trong một MIME part của email | HTML tham chiếu part qua Content-ID |
| **Data URI** | img src="data:image/png;base64,..." | Nhúng trực tiếp trong chuỗi HTML | Hỗ trợ trong email client không đồng nhất, HTML dài hơn |

### Remote image

~~~html
<img
  src="https://static.example.com/email/brand-logo.png"
  alt="Logo thương hiệu">
~~~

Ảnh được lưu trên website hoặc CDN. Email chỉ chứa URL. Khi người nhận mở thư, email client có thể tải ảnh từ máy chủ đó.

**Ưu điểm:**

- Không làm tăng nhiều dung lượng MIME của email.
- Có thể cập nhật ảnh ở máy chủ mà không phải gửi lại email.
- Phù hợp với banner lớn hoặc nhiều ảnh.
- Có thể tận dụng CDN và cache.

**Hạn chế:**

- Email client có thể chặn ảnh từ xa hoặc yêu cầu người nhận cho phép tải.
- URL có thể hết hạn, bị đổi hoặc máy chủ ảnh gặp sự cố.
- Việc tải ảnh có thể tiết lộ thông tin truy cập, địa chỉ IP hoặc thời điểm mở thư, tùy cách client và proxy hoạt động.
- Nếu URL chứa token hoặc định danh cá nhân, việc tải ảnh có thể làm lộ dữ liệu qua log hoặc hệ thống trung gian.

### Inline resource bằng CID

~~~html
<img src="cid:brandLogo" alt="Logo thương hiệu">
~~~

Ảnh được đính kèm trong cấu trúc MIME và có Content-ID. Email client tìm part tương ứng khi xử lý HTML.

**Ưu điểm:**

- Không cần email client tải ảnh đó từ website bên ngoài.
- Ảnh đi cùng thông điệp và không phụ thuộc vào việc URL ảnh còn hoạt động sau này.
- Hữu ích cho logo hoặc icon nhỏ cần được đóng gói cùng email.
- Có thể giữ hình ảnh ở đúng phiên bản tại thời điểm gửi.

**Hạn chế:**

- Làm tăng dung lượng email.
- Phụ thuộc vào khả năng hỗ trợ MIME/CID của email client.
- Một số client vẫn chặn hoặc không hiển thị ảnh.
- Hình có thể xuất hiện trong danh sách attachment tùy cách client trình bày.

### Data URI

~~~html
<img
  src="data:image/png;base64,iVBORw0KGgo..."
  alt="Biểu tượng">
~~~

Dữ liệu ảnh được nhúng trực tiếp trong thuộc tính src. Cách này không cần MIME part riêng nhưng có mức hỗ trợ không đồng nhất trong email client. Nó cũng khiến HTML dài và khó quản lý hơn. Với email cần tương thích rộng, **CID hoặc remote image thường là lựa chọn dễ kiểm soát hơn**, tùy mục tiêu.

## 4. Tài nguyên inline khác attachment như thế nào?

Inline resource và attachment đều có thể được biểu diễn bằng các MIME part, nhưng ý định sử dụng khác nhau:

- **Inline resource** được nội dung HTML tham chiếu để hiển thị ngay trong phần thân thư.
- **Attachment** là tệp người nhận có thể mở hoặc tải xuống độc lập, ví dụ PDF hóa đơn.

Ví dụ:

~~~html
<html lang="vi">
  <body>
    <img src="cid:brandLogo" alt="Logo thương hiệu">
    <h2>Hóa đơn của bạn</h2>
    <p>Hóa đơn PDF được đính kèm trong email.</p>
  </body>
</html>
~~~

Trong Java:

~~~java
helper.setText(plainText, htmlText);

// Ảnh được HTML tham chiếu để hiển thị trong nội dung.
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);

// PDF là tệp đính kèm để người nhận tải xuống.
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

| Tiêu chí | Inline resource | Attachment |
|---|---|---|
| Mục đích | Hiển thị cùng HTML | Cung cấp tệp riêng |
| API helper | **addInline(...)** | **addAttachment(...)** |
| HTML tham chiếu | Thường dùng **cid:** | Không cần HTML tham chiếu |
| Content-ID | Dùng để liên kết với HTML | Không phải yêu cầu thông thường |
| Content-Disposition | Thường có ý định inline | Thường là attachment |
| Ví dụ | Logo, icon, ảnh minh họa | PDF, CSV, tài liệu |

Một số email client có thể hiển thị inline resource trong khu vực attachment hoặc cho người nhận xem riêng. Đó là khác biệt về cách trình bày của client; ứng dụng vẫn nên đặt đúng ý định MIME.

## 5. Content-ID và cú pháp cid:

Để HTML tham chiếu được một ảnh inline, cần có hai phần khớp nhau:

1. **HTML** chứa một URL theo scheme cid, ví dụ **cid:brandLogo**.
2. **MIME part** chứa dữ liệu ảnh và header **Content-ID** tương ứng, thường được biểu diễn trong header bằng dấu ngoặc nhọn góc.

Ví dụ về part:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline
~~~

HTML:

~~~html
<img src="cid:brandLogo" alt="Logo thương hiệu">
~~~

Trong Spring:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

**Tham số contentId của addInline là brandLogo**, không kèm tiền tố **cid:** và không tự thêm dấu ngoặc nhọn. HTML chịu trách nhiệm viết **cid:brandLogo** trong thuộc tính src.

Nên dùng ID đơn giản, có ý nghĩa và duy nhất trong phạm vi thông điệp, ví dụ **brandLogo**, **invoiceChart** hoặc **supportIcon**. Nếu Content-ID có ký tự đặc biệt, cần tuân thủ cú pháp identifier và mã hóa tham chiếu URL thích hợp; không nối dữ liệu tùy ý từ người dùng vào CID.

### CID không phải URL website

Chuỗi **cid:brandLogo** không phải đường dẫn HTTP, không phải đường dẫn file local và không phải endpoint Spring MVC. Nó là một tham chiếu nội bộ của nội dung email, dùng để liên kết phần HTML với MIME part tương ứng.

Nếu email client không tìm được part có Content-ID tương ứng, ảnh có thể không hiển thị. Khi đó cần kiểm tra cả HTML và raw MIME thay vì chỉ nhìn đoạn code Java.

## 6. multipart/related biểu diễn quan hệ giữa HTML và ảnh

Email có hình inline thường sử dụng cấu trúc **multipart/related**. Subtype này mô tả các phần MIME có liên hệ với nhau: phần HTML chính tham chiếu đến những tài nguyên phụ như ảnh.

Sơ đồ:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

Ví dụ MIME khái quát:

~~~text
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related_001"

--related_001
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <h2>Chào mừng bạn</h2>
    <img src="cid:brandLogo" alt="Logo">
  </body>
</html>

--related_001
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brandLogo>
Content-Disposition: inline

... dữ liệu ảnh được mã hóa ...

--related_001--
~~~

Đây là ví dụ minh họa cấu trúc, không phải nội dung MIME hoàn chỉnh để gửi trực tiếp. Jakarta Mail sẽ tạo boundary, header và encoding cần thiết. Không nên tự nối chuỗi MIME thô khi có thể dùng MimeMessageHelper.

### Khi email có cả plain text và HTML

Nếu ứng dụng muốn hỗ trợ cả người đọc HTML và người đọc text, body thường có cấu trúc **multipart/alternative**. Khi thêm ảnh inline, một cấu trúc lồng nhau có thể xuất hiện:

~~~text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    │       └── <img src="cid:brandLogo">
    └── image/png
        └── Content-ID: <brandLogo>
~~~

Nếu email còn có file đính kèm thông thường, có thể có lớp **multipart/mixed** bao ngoài:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png; Content-ID: <brandLogo>
    └── application/pdf; attachment
~~~

Đây là các sơ đồ quan hệ logic. Cây MIME thực tế có thể khác theo multipart mode và cách Jakarta Mail dựng thông điệp. Điều cần hiểu là:

- **alternative** chứa các biểu diễn thay thế của cùng nội dung.
- **related** chứa nội dung chính và tài nguyên được nội dung đó tham chiếu.
- **mixed** chứa các phần độc lập đi cùng một email, ví dụ body và attachment.

## 7. Lợi ích của inline resource đối với độ tin cậy nội dung

Với ảnh remote, email client cần tải ảnh từ một máy chủ ngoài. Nếu server ngừng hoạt động, URL bị đổi hoặc client chặn ảnh từ xa, hình có thể biến mất.

Với ảnh inline, byte ảnh được gửi cùng email. Vì thế nội dung không cần truy cập máy chủ ảnh bên ngoài để lấy chính part đó. Điều này hữu ích khi:

- Email là bản ghi thông báo cần lưu trữ và hiển thị về sau.
- Logo cần giữ đúng phiên bản tại thời điểm email được gửi.
- Người nhận thường đọc thư trong môi trường hạn chế truy cập tài nguyên ngoài.
- Tài nguyên nhỏ và ít thay đổi, như logo hoặc icon.

Tuy nhiên, cần phân biệt **tài nguyên có mặt trong email** với **tài nguyên được client cho phép hiển thị**. Một client có thể vẫn yêu cầu người dùng cho phép xem ảnh, áp dụng chính sách bảo mật hoặc hiển thị MIME part dưới dạng file đính kèm.

Do đó, inline resource giúp giảm phụ thuộc vào việc tải URL bên ngoài; nó không tạo cam kết hiển thị tuyệt đối.

## 8. Lợi ích về tính nhất quán và lưu trữ

Ảnh remote có thể được thay thế tại cùng URL. Khi người nhận mở lại một email cũ, họ có thể thấy ảnh mới nếu máy chủ đã thay nội dung. Với ảnh inline, nội dung ảnh đã được đóng gói trong email tại thời điểm gửi.

Ví dụ:

~~~text
Thời điểm gửi:
  Email A + logo phiên bản 1
        |
        v
  Người nhận lưu email
        |
        v
Thời điểm sau:
  Website đổi logo sang phiên bản 2
        |
        v
  Email A vẫn chứa dữ liệu logo phiên bản 1
~~~

Đây là lợi ích khi cần **tính nhất quán lịch sử**: thư cũ vẫn giữ hình ảnh đã gửi cùng nó, miễn là mailbox còn lưu đủ MIME content.

Tính nhất quán này đặc biệt hữu ích với báo cáo, hóa đơn minh họa, thông báo trạng thái hoặc tài liệu lưu trữ. Tuy nhiên, nếu ảnh chứa dữ liệu động, việc đóng gói ảnh trong từng email cũng làm tăng dung lượng và trách nhiệm quản lý dữ liệu. Chỉ inline những tài nguyên thật sự cần cố định theo thông điệp.

## 9. Lợi ích và chi phí về quyền riêng tư

Ảnh remote có thể tạo ra yêu cầu HTTP khi email client tải ảnh. Tùy hạ tầng, yêu cầu đó có thể để lộ thông tin như thời điểm truy cập, địa chỉ IP hoặc một định danh theo dõi. Một số email client dùng proxy hoặc cache ảnh nên dữ liệu quan sát được không phản ánh trực tiếp hành vi người dùng.

Inline resource không cần một request HTTP đến website ảnh để lấy dữ liệu đã nằm trong email. Điều này có thể giảm một nguồn theo dõi từ việc tải ảnh remote.

Tuy vậy:

- Email client và hệ thống mailbox vẫn xử lý thông điệp và có thể lưu dữ liệu.
- Nhà cung cấp gửi thư vẫn có thông tin vận chuyển và người nhận.
- Nội dung inline có thể chứa dữ liệu nhạy cảm nếu ứng dụng đưa dữ liệu đó vào ảnh.
- Người nhận có thể tải, lưu hoặc chuyển tiếp ảnh cùng email.
- Một email có thể được quét bởi gateway bảo mật và hệ thống chống malware.

Vì vậy, **inline không phải mã hóa** và cũng không phải cơ chế phân quyền. Nếu ảnh chứa dữ liệu cá nhân, ứng dụng cần kiểm soát người nhận, quyền truy cập, thời gian lưu và nội dung được phép hiển thị.

## 10. Khi nào nên dùng inline resource?

Inline phù hợp khi hình ảnh có vai trò hỗ trợ nội dung và nên được đóng gói cùng email:

### Logo thương hiệu

Logo nhỏ ở phần đầu hoặc chân email giúp người nhận nhận diện nguồn gửi. Nếu logo là tài nguyên ổn định, ClassPathResource có thể lấy từ tài nguyên đóng gói trong ứng dụng.

### Icon trạng thái

Một biểu tượng nhỏ có thể hỗ trợ thông báo hoàn tất, cảnh báo hoặc yêu cầu chú ý. Tuy nhiên, trạng thái vẫn phải có chữ như **“Đã hoàn tất”** hoặc **“Cần xử lý”** để người dùng không phụ thuộc vào màu/icon.

### Biểu đồ tóm tắt

Một email báo cáo có thể chứa biểu đồ PNG nhỏ được sinh tại thời điểm gửi. Inline giữ biểu đồ cùng snapshot dữ liệu của email. Với biểu đồ lớn hoặc cần tương tác, nên cung cấp liên kết tới dashboard có quyền truy cập.

### Hình minh họa ngắn

Ảnh nhỏ giúp giải thích một thao tác hoặc sản phẩm. Nếu hình không hiển thị, alt text và đoạn mô tả cần vẫn truyền đạt ý chính.

### Tài nguyên trang trí

Có thể dùng hình nền hoặc họa tiết nhỏ, nhưng nên thận trọng: CSS background image không được hỗ trợ đồng nhất trong email client. Không đặt thông tin quan trọng trong hình trang trí.

## 11. Khi nào không nên dùng inline resource?

Không nên nhúng mọi hình ảnh vào mọi email. Một số trường hợp khác phù hợp hơn:

| Trường hợp | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Banner lớn hoặc nhiều ảnh sản phẩm | Remote image/CDN | Giảm dung lượng từng email |
| Hình cần cập nhật sau khi gửi | Remote image | Có thể thay nội dung ở máy chủ, nếu phù hợp quyền riêng tư |
| Ảnh chỉ là file người nhận cần tải | Attachment | Ý định tải xuống rõ hơn |
| Ảnh không quan trọng với nội dung | Bỏ ảnh | Email nhẹ và ít phụ thuộc render |
| Nội dung có thể trình bày bằng text | Plain text/HTML text | Dễ đọc, tìm kiếm và truy cập hơn |
| Biểu đồ tương tác hoặc dashboard lớn | Link tới ứng dụng web được bảo vệ | Email không phải môi trường tương tác đầy đủ |
| Ảnh rất lớn hoặc số lượng nhiều | Link tải an toàn hoặc CDN | Tránh vượt giới hạn message |

Một quy tắc thực tế: **dùng inline cho tài nguyên nhỏ, có mục đích rõ và cần đi cùng nội dung; dùng attachment cho tệp độc lập; dùng remote image khi cần tải nội dung từ web và chấp nhận các tác động về hiển thị/quyền riêng tư.**

## 12. Dùng MimeMessageHelper để thêm inline resource

Trong Spring Framework Mail, **MimeMessageHelper** cung cấp API để thêm inline resource. Một ví dụ cơ bản:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcome(
        JavaMailSender mailSender,
        String recipient
) throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("welcome@example.com");
    helper.setTo(recipient);
    helper.setSubject("Chào mừng bạn");

    String plainText = """
            Xin chào!

            Tài khoản của bạn đã được tạo thành công.
            Truy cập https://example.com/account để xem thông tin.
            """;

    String htmlText = """
            <html lang="vi">
              <body>
                <img src="cid:brandLogo"
                     alt="Logo thương hiệu"
                     width="160">
                <h2>Chào mừng bạn!</h2>
                <p>Tài khoản của bạn đã được tạo thành công.</p>
                <p>
                  <a href="https://example.com/account">
                    Xem thông tin tài khoản
                  </a>
                </p>
              </body>
            </html>
            """;

    // Đặt nội dung trước khi thêm resource inline.
    helper.setText(plainText, htmlText);

    helper.addInline(
            "brandLogo",
            new ClassPathResource("mail/brand-logo.png"),
            "image/png"
    );

    mailSender.send(message);
}
~~~

Ví dụ giả định:

- Ứng dụng có bean **JavaMailSender** được cấu hình SMTP hợp lệ.
- Tệp **mail/brand-logo.png** nằm trong classpath, ví dụ dưới **src/main/resources/mail/**.
- Địa chỉ From được nhà cung cấp gửi cho phép.
- Tài nguyên có định dạng PNG thật và kích thước phù hợp.

### Giải thích các bước

1. **createMimeMessage()** tạo một đối tượng thông điệp MIME.
2. **MimeMessageHelper(..., MULTIPART_MODE_RELATED, UTF-8)** tạo helper với cấu trúc multipart/related phù hợp cho HTML và tài nguyên inline.
3. **setFrom**, **setTo** và **setSubject** thiết lập header cơ bản.
4. **setText(plainText, htmlText)** tạo hai biểu diễn thay thế của nội dung.
5. **addInline("brandLogo", resource, "image/png")** thêm part ảnh có Content-ID tương ứng.
6. **send(message)** nộp thông điệp cho mail transport.

### Vì sao setText nên được gọi trước addInline?

Với MimeMessageHelper, việc đặt body có thể tạo hoặc thay đổi cấu trúc multipart bên trong. Vì vậy, thứ tự nên dùng là:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logoResource, "image/png");
~~~

Đặt inline resource trước khi thiết lập nội dung có thể làm cấu trúc multipart không như mong đợi trên một số đường xử lý. Hãy giữ thứ tự **setText trước, addInline sau**.

## 13. Chọn multipart mode phù hợp

MimeMessageHelper cung cấp các chế độ multipart để mô tả cách tổ chức nội dung:

| Mode | Mục đích tổng quát | Trường hợp thường gặp |
|---|---|---|
| **MULTIPART_MODE_NO** | Không tạo multipart | Email chỉ có một phần nội dung đơn giản |
| **MULTIPART_MODE_MIXED** | Cấu trúc multipart/mixed | Body cùng các attachment thông thường |
| **MULTIPART_MODE_RELATED** | Cấu trúc multipart/related | HTML có tài nguyên inline |
| **MULTIPART_MODE_MIXED_RELATED** | Kết hợp lớp mixed và related | Email có inline resource và attachment |

Nếu email chỉ có HTML và logo CID, có thể dùng **MULTIPART_MODE_RELATED**. Nếu email vừa có ảnh inline vừa có PDF attachment, thường cân nhắc **MULTIPART_MODE_MIXED_RELATED**.

Constructor với boolean:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

bật multipart theo chế độ mặc định của helper. Khi cần kiểm soát rõ cấu trúc cho inline resource và attachment, có thể chỉ định mode cụ thể.

Không dùng **MULTIPART_MODE_NO** rồi kỳ vọng addInline tự tạo cây MIME phù hợp. Cấu trúc MIME cần hỗ trợ part liên quan tới body.

## 14. Chọn nguồn tài nguyên inline

Phương thức addInline có thể nhận các nguồn khác nhau tùy overload. Một số lựa chọn thường dùng:

### ClassPathResource

Phù hợp với logo hoặc icon cố định được đóng gói cùng ứng dụng:

~~~java
helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
~~~

Đường dẫn runtime tính từ classpath root; không thêm **src/main/resources** vào tên resource.

### FileSystemResource

Phù hợp khi ảnh được lưu trên filesystem:

~~~java
helper.addInline(
        "reportChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

File phải tồn tại, đọc được và còn nguyên trong lúc gửi. Không dùng đường dẫn tùy ý từ request mà chưa kiểm tra quyền và phạm vi truy cập.

### ByteArrayResource

Phù hợp khi ảnh được tạo động và đã có trong bộ nhớ:

~~~java
byte[] pngBytes = chartRenderer.renderPng();

helper.addInline(
        "reportChart",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

ByteArrayResource có thể cung cấp stream mới từ cùng dữ liệu, thuận tiện cho việc đọc lặp lại. Nhưng ảnh lớn hoặc nhiều email đồng thời có thể làm tăng áp lực heap.

### InputStreamSource tùy chỉnh

Nếu nguồn lưu trữ có API mở stream mới, có thể truyền một InputStreamSource:

~~~java
InputStreamSource logoSource =
        () -> objectStorage.openStream(bucket, objectKey);

helper.addInline("brandLogo", logoSource, "image/png");
~~~

**objectStorage.openStream(...)** là API giả định của ứng dụng. Mỗi lần getInputStream() cần trả về stream mới đọc cùng một phiên bản dữ liệu. Tránh bọc một InputStream đã mở và đã tiêu thụ vào source rồi giả định có thể đọc lại.

## 15. Content-Type, filename và kích thước ảnh

Khi thêm inline resource, hãy xác định media type đúng:

| Dữ liệu | Content-Type thường dùng |
|---|---|
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| WebP | **image/webp**; cần kiểm tra hỗ trợ của client |
| SVG | **image/svg+xml**; cần kiểm tra kỹ khả năng hỗ trợ và chính sách client |

Không khai báo **image/png** cho dữ liệu JPEG chỉ vì tên file kết thúc bằng .png. Content-Type là metadata để client xử lý dữ liệu; nó không biến dữ liệu sai định dạng thành ảnh hợp lệ.

### Tối ưu kích thước

Ảnh inline được đóng gói vào email. Dữ liệu nhị phân thường được chuyển mã base64 khi truyền qua MIME, làm kích thước phần biểu diễn tăng khoảng một phần ba, chưa kể header, boundary và nội dung khác.

Ví dụ ước lượng:

~~~text
Ảnh PNG gốc:             300 KB
Phần base64 ước lượng:   khoảng 400 KB
MIME header/boundary:    tăng thêm một phần nhỏ
Tổng message:            còn có body và các attachment khác
~~~

Đây là ước lượng, không phải kích thước chính xác của mọi message.

Nên:

- Dùng ảnh có kích thước hiển thị phù hợp.
- Nén ảnh trước khi gửi.
- Tránh nhúng cùng một ảnh nhiều lần bằng nhiều Content-ID nếu không cần.
- Hạn chế số ảnh inline trong một thông điệp.
- Xem giới hạn kích thước của SMTP/ESP.
- Với ảnh lớn, cân nhắc remote image hoặc link tải an toàn.

## 16. Tài nguyên inline và khả năng tương thích email client

Các email client không xử lý HTML và MIME hoàn toàn giống nhau. Dù MIME có Content-ID đúng, hình vẫn có thể không xuất hiện vì:

- Client chặn ảnh theo chính sách bảo mật.
- Client không xử lý cấu trúc multipart/related theo cách mong đợi.
- HTML tham chiếu CID sai hoặc MIME part thiếu Content-ID.
- Content-Type không đúng hoặc byte ảnh bị hỏng.
- Client trình bày inline part trong khu vực attachment.
- CSS/HTML xung quanh ảnh bị loại bỏ hoặc thay đổi.

Vì vậy, inline resource nên có **alt text**:

~~~html
<img
  src="cid:brandLogo"
  alt="Logo thương hiệu"
  width="160">
~~~

Alt text hữu ích khi ảnh không tải, đồng thời giúp người dùng trình đọc màn hình hiểu vai trò của hình. Nếu ảnh chỉ mang tính trang trí, có thể dùng alt rỗng theo ngữ cảnh; không nên dùng alt để thay cho một đoạn nội dung quan trọng.

### Đừng đặt thông tin quan trọng chỉ trong ảnh

Không nên tạo một ảnh duy nhất có chứa:

- Mã OTP hoặc mã xác nhận.
- Số hóa đơn hoặc số tiền cần thanh toán.
- Hạn thanh toán hoặc hạn sử dụng.
- Link hoặc hành động người dùng cần thực hiện.
- Thông tin pháp lý hoặc cảnh báo quan trọng.

Những nội dung đó cần là text thật trong email. Ảnh chỉ nên hỗ trợ cách trình bày.

## 17. Inline resource và khả năng truy cập

Email có ảnh inline vẫn cần được thiết kế để người dùng có thể hiểu nội dung mà không phụ thuộc vào hình.

**Một số nguyên tắc:**

1. Dùng alt text mô tả đúng ý nghĩa của ảnh.
2. Không dùng màu hoặc biểu tượng làm cách duy nhất truyền tải trạng thái.
3. Giữ tiêu đề, đoạn mô tả và hành động dưới dạng text/link thật.
4. Cung cấp plain-text alternative bằng **setText(plainText, htmlText)**.
5. Đảm bảo thứ tự đọc hợp lý khi ảnh không hiển thị.
6. Dùng kích thước ảnh phù hợp để không phá vỡ bố cục màn hình nhỏ.

Ví dụ:

~~~html
<img src="cid:successIcon" alt="Đã hoàn tất">
<h2>Yêu cầu của bạn đã được xử lý</h2>
<p>Bạn có thể xem kết quả trong tài khoản.</p>
<a href="https://example.com/requests">Xem yêu cầu</a>
~~~

Ngay cả khi ảnh không hiện, tiêu đề và đoạn văn vẫn truyền đạt trạng thái. Link có nhãn mô tả giúp người dùng biết hành động.

### Plain text phải có cùng ý nghĩa

~~~java
helper.setText(
        """
        Yêu cầu của bạn đã được xử lý.
        Xem kết quả tại https://example.com/requests
        """,
        htmlText
);
~~~

Bản text không cần mô tả từng chi tiết trang trí của ảnh, nhưng phải giữ thông tin nghiệp vụ và URL quan trọng. Đây là phương án dự phòng cho client không render HTML hoặc người dùng chọn xem dạng text.

## 18. Quyền riêng tư: inline không phải mã hóa

Một lý do có thể chọn CID là giảm phụ thuộc vào request tải ảnh từ một máy chủ ngoài. Với remote image, việc tải có thể tạo dữ liệu quan sát được về thời điểm mở thư hoặc thông tin kết nối, tùy email client, proxy và cache.

Inline resource nằm trong MIME message nên không cần tải ảnh từ website bên ngoài. Tuy nhiên, điều đó **không đồng nghĩa nội dung email được mã hóa đầu cuối**:

- SMTP server và các hệ thống vận chuyển vẫn xử lý thông điệp.
- Mailbox lưu email có thể giữ cả dữ liệu ảnh.
- Người nhận có thể tải, lưu hoặc chuyển tiếp ảnh.
- Gateway bảo mật có thể quét nội dung.
- Dữ liệu nhạy cảm được vẽ vào ảnh vẫn có thể bị đọc như nội dung thư.

Nếu ảnh chứa dữ liệu riêng của một khách hàng, cần kiểm tra quyền người nhận và tránh gửi chung một email cho nhiều người. CID chỉ là cơ chế liên kết tài nguyên trong MIME.

## 19. Bảo mật nguồn ảnh và dữ liệu động

Nếu ảnh lấy từ một nguồn động, cần kiểm soát cả nguồn và dữ liệu:

### File trên filesystem

- Chỉ đọc trong thư mục được phép.
- Không dùng đường dẫn do người dùng nhập trực tiếp.
- Kiểm tra path traversal và symbolic link.
- Xác nhận người nhận có quyền xem ảnh.

### Ảnh từ remote storage

- Dùng credential có quyền tối thiểu.
- Giới hạn kích thước và thời gian tải.
- Pin version hoặc snapshot nếu cần dữ liệu nhất quán.
- Không tải URL tùy ý từ request để tránh SSRF.
- Đóng stream và xử lý lỗi mạng đúng cách.

### Ảnh sinh từ dữ liệu người dùng

- Escape text khi render HTML.
- Không đưa nội dung không tin cậy vào SVG/HTML có thể chứa markup chủ động.
- Kiểm tra loại ảnh và giới hạn kích thước pixel/dung lượng.
- Quét hoặc xử lý ảnh theo chính sách của ứng dụng.
- Không ghi byte ảnh nhạy cảm hoặc token vào log.

Một ảnh PNG đã được kiểm tra định dạng vẫn có thể chứa thông tin riêng. Việc kiểm tra media type và quyền dữ liệu là hai bước khác nhau.

## 20. Nhiều tài nguyên inline trong một email

Một email có thể chứa nhiều ảnh inline. Mỗi ảnh cần Content-ID riêng:

~~~html
<html lang="vi">
  <body>
    <header>
      <img src="cid:brandLogo" alt="Logo thương hiệu" width="150">
    </header>
    <h2>Báo cáo tháng</h2>
    <img src="cid:revenueChart" alt="Biểu đồ doanh thu theo tháng">
    <p>Doanh thu được tổng hợp trong báo cáo.</p>
    <img src="cid:supportIcon" alt="Biểu tượng hỗ trợ" width="24">
  </body>
</html>
~~~

Java:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
helper.addInline(
        "revenueChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);
helper.addInline(
        "supportIcon",
        new ClassPathResource("mail/support-icon.png"),
        "image/png"
);
~~~

Các Content-ID **brandLogo**, **revenueChart** và **supportIcon** phải khớp với phần sau **cid:** trong HTML. Không dùng cùng một ID cho những dữ liệu ảnh khác nhau trong cùng thông điệp.

Nếu một template không sử dụng ảnh nào, có thể không thêm các part tương ứng để giảm dung lượng. Nếu ảnh được thêm động theo loại email, hãy quản lý danh sách CID và resource tập trung để tránh template tham chiếu một ID không tồn tại.

## 21. Kết hợp inline resource với attachment

Email có thể chứa cả ảnh được hiển thị trong HTML và một tệp độc lập:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("reports@example.com");
helper.setTo(recipient);
helper.setSubject("Báo cáo của bạn");
helper.setText(
        "Báo cáo được đính kèm. Biểu đồ nằm trong nội dung HTML.",
        """
        <html lang="vi">
          <body>
            <img src="cid:reportChart" alt="Biểu đồ báo cáo">
            <p>Báo cáo chi tiết được đính kèm dưới dạng PDF.</p>
          </body>
        </html>
        """
);

helper.addInline(
        "reportChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

Đây là ví dụ minh họa; các biến **recipient**, **chartPngBytes** và **reportPath** phải được tạo và kiểm tra trước. File PDF và ảnh phải thuộc cùng báo cáo và người nhận phải có quyền xem cả hai.

**MULTIPART_MODE_MIXED_RELATED** thường phù hợp khi cần nhóm tài nguyên related cho HTML và attachment độc lập. Cấu trúc MIME chi tiết được helper/Jakarta Mail tạo; không nên tự giả định mọi email client sẽ trình bày inline part và attachment giống nhau.

## 22. Lỗi thường gặp khi dùng tài nguyên inline

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ảnh không hiện, chỉ thấy biểu tượng ảnh lỗi | HTML CID không khớp Content-ID hoặc thiếu MIME part | Đối chiếu cid trong HTML với addInline và raw MIME |
| Dùng **cid:brandLogo** làm tham số addInline | Content-ID bị truyền kèm tiền tố cid | Chỉ truyền **brandLogo** |
| Ảnh xuất hiện như file đính kèm | Client trình bày MIME part theo cách riêng hoặc cấu trúc không phù hợp | Kiểm tra multipart/related, Content-ID và Content-Disposition |
| Inline resource bị mất sau khi setText | Gọi addInline trước khi thiết lập body | Gọi setText trước, addInline sau |
| Không thêm được inline resource | Helper không bật multipart | Dùng MULTIPART_MODE_RELATED hoặc MIXED_RELATED |
| Ảnh hỏng hoặc hiển thị sai | Content-Type không đúng hoặc dữ liệu không phải ảnh hợp lệ | Kiểm tra định dạng thật và media type |
| Resource không tìm thấy | Sai classpath path hoặc file không được đóng gói | Kiểm tra src/main/resources và tên resource |
| Ảnh remote không tải | URL hết hạn, client chặn remote image hoặc server lỗi | Kiểm tra URL; cân nhắc CID nếu ảnh nhỏ và cần đi cùng thư |
| Email quá lớn | Nhúng nhiều ảnh hoặc ảnh dung lượng cao | Tối ưu ảnh, giảm số part hoặc dùng remote image |
| Client này hiện ảnh, client khác không | Khác biệt hỗ trợ HTML/MIME hoặc chính sách ảnh | Giữ alt text và nội dung text; thử trên client mục tiêu |
| Hình không có mô tả với trình đọc màn hình | Thiếu alt text | Thêm alt có ý nghĩa hoặc alt rỗng nếu chỉ trang trí |
| Logo tối biến mất ở dark mode | Hình không phù hợp nền tối | Dùng tài sản phù hợp hoặc bố cục nền có tương phản |

### Cách kiểm tra raw MIME

Khi cần chẩn đoán, gửi thư tới SMTP test inbox và xem **Show original**, **View source** hoặc raw message. Tìm:

1. Phần HTML có **src="cid:brandLogo"**.
2. Một MIME part có **Content-ID: <brandLogo>**.
3. **Content-Type** đúng, ví dụ **image/png**.
4. Quan hệ **multipart/related** phù hợp giữa HTML và ảnh.
5. Dữ liệu ảnh được mã hóa và truyền đầy đủ.

Header có thể được sắp xếp theo thứ tự khác; điều cần kiểm tra là quan hệ giữa HTML và part ảnh. Raw message có thể chứa địa chỉ, token, dữ liệu cá nhân hoặc file; chỉ xem/lưu trong môi trường được phép và không chép nội dung nhạy cảm vào log công khai.

## 23. Hiệu năng và giới hạn kích thước

Tài nguyên inline làm tăng kích thước của mỗi email. Nếu cùng một logo được nhúng vào hàng nghìn email, dữ liệu ảnh được gửi lặp lại trong từng message. Điều này có thể làm tăng:

- Băng thông gửi và nhận.
- Thời gian serialize và truyền MIME.
- Bộ nhớ cần dùng khi tạo nhiều message đồng thời.
- Dung lượng lưu trữ trong mailbox.
- Khả năng vượt giới hạn message của SMTP provider.

### Ước lượng base64

Dữ liệu ảnh nhị phân thường được biểu diễn bằng base64 trong MIME. Kích thước phần base64 thường lớn hơn dữ liệu gốc khoảng một phần ba, chưa tính header và xuống dòng. Vì vậy, ảnh 600 KB có thể tạo phần base64 khoảng 800 KB trước khi cộng body và các part khác.

Đây là ước lượng để thiết kế, không phải phép đo chính xác cho mọi email. Tổng kích thước phụ thuộc cách mã hóa, số ảnh, attachment và transport.

### Cân nhắc remote image khi phù hợp

Nếu email có nhiều ảnh sản phẩm hoặc banner lớn, remote image từ CDN có thể giảm đáng kể dung lượng mỗi thư. Đổi lại, client có thể chặn ảnh, URL có thể thay đổi và hoạt động tải ảnh có thể liên quan đến quyền riêng tư. Lựa chọn cần dựa trên mục đích, đối tượng người nhận và chính sách dữ liệu.

## 24. Thử nghiệm email có inline resource

Không nên chỉ kiểm tra bằng cách mở HTML trong trình duyệt. Trình duyệt không xử lý MIME email theo cách một email client xử lý.

Một quy trình thử nghiệm hữu ích:

1. Tạo một message mẫu có plain text, HTML và một ảnh CID.
2. Gửi tới SMTP test server hoặc sandbox.
3. Kiểm tra raw MIME để xác nhận Content-ID, Content-Type và multipart/related.
4. Mở thư trên các email client người nhận thực sự sử dụng.
5. Thử khi ảnh bị chặn và kiểm tra alt text.
6. Thử trên giao diện sáng/tối và màn hình nhỏ.
7. Kiểm tra kích thước message và cách client trình bày ảnh trong danh sách attachment.
8. Kiểm tra plain-text alternative để chắc chắn nội dung chính vẫn đầy đủ.

Nếu email có dữ liệu riêng, hãy dùng dữ liệu thử nghiệm. Không gửi báo cáo hoặc hóa đơn thật cho người nhận không được phép chỉ để kiểm tra cách hiển thị.

### Kiểm tra code không thay thế kiểm tra client

Unit test có thể xác nhận service gọi addInline với đúng Content-ID và resource. Integration test có thể kiểm tra MIME part sau khi serialize. Nhưng chỉ việc mở thư trong email client mục tiêu mới xác nhận được trải nghiệm hiển thị thực tế.

## 25. Lựa chọn inline resource theo mục tiêu

| Mục tiêu | Lựa chọn thường phù hợp | Điều cần lưu ý |
|---|---|---|
| Logo cố định trong thư | CID với ClassPathResource | Giữ đúng phiên bản logo, kiểm tra dark mode |
| Icon nhỏ | CID hoặc text/icon đơn giản | Không để trạng thái chỉ phụ thuộc vào màu/hình |
| Biểu đồ snapshot | CID với ByteArrayResource | Kiểm tra kích thước và nội dung dữ liệu |
| Banner lớn | Remote image/CDN | Client có thể chặn; cần alt text |
| File người dùng cần tải | Attachment | Đặt filename và Content-Type đúng |
| Dashboard tương tác | Link tới ứng dụng web | Kiểm soát xác thực và quyền truy cập |
| Hình trang trí không cần thiết | Có thể bỏ | Email nhẹ và dễ đọc hơn |

Không có một phương pháp duy nhất phù hợp cho mọi loại email. Hãy xác định hình ảnh có thực sự giúp người nhận hiểu hoặc thực hiện hành động hay không, sau đó cân nhắc dung lượng, khả năng tương thích và quyền riêng tư.

## 26. Ghi nhớ

**Tài nguyên inline trong email HTML** là dữ liệu được đóng gói thành MIME part và được phần HTML tham chiếu, thường thông qua **cid:** và **Content-ID**. Trong Spring Framework Mail, **MimeMessageHelper.addInline(...)** giúp thêm tài nguyên; cấu trúc **multipart/related** biểu diễn quan hệ giữa phần HTML và hình ảnh.

Inline resource hữu ích cho logo, icon, hình minh họa và biểu đồ nhỏ cần đi cùng email. Nó giúp giảm phụ thuộc vào việc tải ảnh từ máy chủ bên ngoài và giữ phiên bản ảnh tại thời điểm gửi. Đổi lại, email lớn hơn và vẫn phụ thuộc vào khả năng xử lý MIME/HTML của client. Inline không phải attachment thông thường, không phải URL remote và cũng không phải cơ chế mã hóa.

Khi triển khai, hãy chọn resource phù hợp, dùng Content-ID duy nhất, thiết lập multipart mode thích hợp, gọi **setText(...) trước addInline(...)**, khai báo Content-Type chính xác và giữ alt text cùng plain-text alternative. **Mục đích của tài nguyên inline là hỗ trợ nội dung email ngay tại vị trí cần hiển thị, trong khi thông điệp vẫn dễ hiểu khi hình ảnh không xuất hiện.**
