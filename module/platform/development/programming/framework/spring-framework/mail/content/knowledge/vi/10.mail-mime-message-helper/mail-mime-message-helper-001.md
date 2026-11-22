# Khởi tạo MimeMessageHelper với message và encoding

## 1. Vai trò của MimeMessageHelper trong Spring Framework Mail

Khi một ứng dụng Spring gửi email, đối tượng `jakarta.mail.internet.MimeMessage` đại diện cho thông điệp email ở tầng Jakarta Mail: nó giữ header, địa chỉ, tiêu đề, nội dung và cấu trúc MIME. Lập trình viên có thể thao tác trực tiếp trên `MimeMessage`, nhưng việc tạo email có HTML, ký tự Unicode, nhiều người nhận, ảnh inline hoặc tệp đính kèm đòi hỏi nhiều thao tác chi tiết.

**`org.springframework.mail.javamail.MimeMessageHelper`** là lớp hỗ trợ của Spring Framework nhằm đơn giản hóa việc **soạn một `MimeMessage` đã có**, đặc biệt là quản lý ký tự, đặt các trường thông thường và xây dựng multipart. Helper **không tự tạo SMTP server và không tự gửi thư**. Đường đi phổ biến là:

~~~mermaid
flowchart LR
    A["JavaMailSender"] -->|"createMimeMessage()"| B["MimeMessage"]
    B --> C["new MimeMessageHelper(message, encoding)"]
    C --> D["setFrom / setTo / setSubject / setText"]
    D --> E["JavaMailSender.send(message)"]
    E --> F["Jakarta Mail / SMTP transport"]
~~~

Hai tham số cần hiểu ngay từ đầu là:

1. **`message`**: chính đối tượng `MimeMessage` mà helper sẽ chỉnh sửa. Helper làm việc trên đối tượng được truyền vào; nó không tạo một email độc lập rồi tự động đồng bộ trở lại message khác.
2. **`encoding`**: tên bảng mã ký tự dùng khi helper tạo nội dung hoặc header text có liên quan, thường là **`UTF-8`** để biểu diễn tiếng Việt và nhiều ngôn ngữ khác.

Ví dụ tối thiểu:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo: Báo cáo tuần");
helper.setText("Chào Lan, báo cáo tuần đã sẵn sàng.", false);

mailSender.send(message);
~~~

Đoạn mã giả định đang nằm trong method có xử lý hoặc khai báo `MessagingException` và biến `mailSender` có kiểu `JavaMailSender`. Chú ý lệnh **`mailSender.send(message)` gửi đúng đối tượng đã truyền vào helper**.

> **Ghi nhớ:** `new MimeMessageHelper(message, "UTF-8")` chỉ tạo một công cụ soạn thư có gắn với `message` và chọn bảng mã; phải gán thông tin thư rồi gọi API gửi mới thực hiện gửi email.

## 2. Tạo MimeMessage trước, sau đó mới tạo helper

Một service Spring thông thường phụ thuộc vào interface `JavaMailSender`:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
~~~

`JavaMailSender.createMimeMessage()` cung cấp một `MimeMessage` phù hợp với sender đang được cấu hình. Với implementation thông dụng `JavaMailSenderImpl`, message được tạo dựa trên Jakarta Mail `Session` của sender và có thể mang thông tin mặc định liên quan như encoding.

Nên sử dụng message do sender tạo vì:

- **Đúng ngữ cảnh**: email được xây dựng trong ngữ cảnh của mail sender được cấu hình cho ứng dụng.
- **Thuận tiện về mặc định**: sender có thể cung cấp default encoding và một số thông tin phục vụ helper.
- **Rõ vòng đời**: mỗi lượt soạn/gửi có một message riêng; service không cần tự quản lý Jakarta Mail `Session` chỉ để gửi.
- **Dễ thay thế trong test**: service phụ thuộc vào `JavaMailSender`, có thể kiểm thử bằng fake sender tạo message hợp lệ.

Có thể tạo `MimeMessage` trực tiếp từ Jakarta Mail `Session` trong những tình huống riêng, nhưng đối với ứng dụng Spring sử dụng `JavaMailSender`, cách trên giúp tránh hai nguồn cấu hình song song.

### 2.1. Không nhầm message với helper

Xem ví dụ:

~~~java
MimeMessage first = mailSender.createMimeMessage();
MimeMessage second = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(first, "UTF-8");
helper.setTo("lan@example.net");
helper.setText("Nội dung của first", false);

mailSender.send(second); // Không gửi nội dung vừa gán vào first.
~~~

Helper chỉ chỉnh sửa `first`; `second` vẫn là một message khác. Việc gửi `second` không thể tự lấy các trường đã gán vào `first`. Vì vậy nên đặt tên biến rõ ràng và gửi đúng message đang được xây dựng.

### 2.2. Một helper có thể dùng qua nhiều thao tác soạn thư

Sau khi khởi tạo, cùng một helper có thể lần lượt đặt:

~~~java
helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setCc("team@example.net");
helper.setReplyTo("support@example.com");
helper.setSubject("Báo cáo tháng");
helper.setText("Nội dung báo cáo...", false);
~~~

Những lời gọi này chỉnh sửa **cùng đối tượng `MimeMessage`** trong bộ nhớ. Chúng không tương ứng với từng lệnh SMTP được gửi ngay khi gọi setter. Giao thức SMTP được thực hiện ở giai đoạn gửi.

Không nên chia sẻ một `MimeMessage` hoặc một `MimeMessageHelper` đang bị thay đổi giữa nhiều request/luồng đồng thời. Mỗi lần soạn email mới nên tạo **message và helper riêng**, tránh tình huống header/người nhận/nội dung bị trộn.

## 3. Các constructor của MimeMessageHelper

Spring cung cấp nhiều constructor để lựa chọn **encoding** và **chế độ multipart**. Những dạng thường dùng:

~~~java
new MimeMessageHelper(message);
new MimeMessageHelper(message, "UTF-8");

new MimeMessageHelper(message, false);
new MimeMessageHelper(message, false, "UTF-8");

new MimeMessageHelper(message, true);
new MimeMessageHelper(message, true, "UTF-8");

new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED);
new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Lưu ý: các constructor bật multipart có thể khai báo `MessagingException` vì việc thiết lập cấu trúc MIME cần thao tác trên message.

| Constructor | Chọn encoding rõ ràng? | Chọn multipart? | Phù hợp với |
| --- | --- | --- | --- |
| `MimeMessageHelper(message)` | Không | Không | Soạn nội dung đơn giản khi mặc định đã phù hợp |
| `MimeMessageHelper(message, encoding)` | Có | Không | Text/HTML đơn giản cần charset kiểm soát được |
| `MimeMessageHelper(message, multipart)` | Không | Cờ boolean | Soạn thư có hoặc không có nhiều MIME part |
| `MimeMessageHelper(message, multipart, encoding)` | Có | Cờ boolean | Thư Unicode, có thể cần HTML/attachment/inline |
| `MimeMessageHelper(message, multipartMode)` | Không | Mode cụ thể | Điều khiển dạng cây MIME |
| `MimeMessageHelper(message, multipartMode, encoding)` | Có | Mode cụ thể | Điều khiển cả cây MIME và charset |

Trong bảng, `encoding` là `String` như `"UTF-8"`. `multipart` là `boolean`; `multipartMode` là hằng số `int` của `MimeMessageHelper`. Không nhầm:

~~~java
new MimeMessageHelper(message, true, "UTF-8");   // boolean
new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");                                 // int mode
~~~

Hai constructor đều cho phép dựng nhiều part, nhưng dạng có mode giúp thể hiện **cấu trúc mong muốn** rõ ràng khi thư chứa cả tài nguyên inline lẫn attachment.

### 3.1. Constructor với encoding nhưng không bật multipart

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
~~~

Ở đây helper sử dụng encoding được chỉ định và **không tự khởi tạo cây multipart**. Nó phù hợp khi chỉ cần một body text hoặc HTML đơn:

~~~java
helper.setSubject("Đã xác nhận đăng ký");
helper.setText("<p>Xin chào, đăng ký <strong>thành công</strong>.</p>", true);
~~~

`true` ở `setText(..., true)` nghĩa là **nội dung HTML**, không phải bật multipart. Hai khái niệm là khác nhau:

- **HTML** quyết định loại body `text/html`.
- **Multipart** cho phép message tổ chức nhiều phần, ví dụ text và HTML cùng tồn tại, hoặc body đi kèm attachment.

Nếu muốn gọi `addAttachment(...)` hoặc `addInline(...)`, hãy chọn constructor bật multipart từ đầu.

### 3.2. Constructor boolean và encoding

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

`multipart=true` kích hoạt cấu trúc multipart theo chế độ mặc định mà Spring helper sử dụng khi cờ này được bật. `encoding="UTF-8"` hướng dẫn helper khi ghi nội dung text và subject. Dạng này tiện khi không cần chỉ định chi tiết mode.

Với thư phức tạp, có thể viết rõ:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Mode `MIXED_RELATED` thường thích hợp khi body có ảnh tham chiếu bằng Content-ID đồng thời thư có attachment riêng. Điều này liên quan **cách tổ chức cây MIME**, còn `"UTF-8"` vẫn là lựa chọn bảng mã cho nội dung văn bản.

## 4. Encoding là gì và ảnh hưởng đến những thành phần nào?

Máy tính lưu và truyền dữ liệu dưới dạng byte; một ký tự như “á”, “Đ” hoặc “✓” cần được mã hóa thành bytes theo một **character encoding**. Trong email, nội dung text có thể có thêm lớp **Content-Transfer-Encoding** để các byte đó được vận chuyển dưới dạng phù hợp với MIME.

Ví dụ body:

~~~text
Chào bạn, tài khoản đã được kích hoạt.
~~~

Khi đặt bằng:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setText("Chào bạn, tài khoản đã được kích hoạt.", false);
~~~

helper sử dụng UTF-8 để tạo nội dung văn bản. Một part MIME có thể mang header dạng:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Hoặc có thể sử dụng `base64` hay cách transfer encoding khác, tùy thư viện và nội dung. **UTF-8 không phải Content-Transfer-Encoding**. Khi đọc thư, client giải mã lớp transfer encoding, rồi diễn giải bytes theo charset để khôi phục ký tự.

### 4.1. Ba khái niệm dễ nhầm

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Charset** | `UTF-8` | Chuyển ký tự văn bản thành bytes và ngược lại |
| **MIME Content-Type** | `text/plain`, `text/html` | Cho biết part chứa loại nội dung nào |
| **Content-Transfer-Encoding** | `quoted-printable`, `base64` | Biểu diễn bytes trên đường truyền MIME |

Một thư có:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: base64
~~~

không phải vì email “viết bằng base64” mà vì các bytes của HTML UTF-8 được chuyển sang dạng base64 để truyền. Email client sẽ giải mã base64 rồi dùng UTF-8 để hiển thị HTML.

### 4.2. UTF-8 không làm mọi thứ thành Unicode tự động

`"UTF-8"` trong constructor giúp với **nội dung text và những header được helper mã hóa thích hợp**, nhưng không giải quyết mọi vấn đề:

- **Địa chỉ email có ký tự quốc tế** có thể cần SMTP extension `SMTPUTF8`. Charset của body không tự cấp hỗ trợ cho địa chỉ như vậy.
- **Attachment dạng nhị phân** như PDF/PNG không được “chuyển thành UTF-8”; nó dùng MIME content type và transfer encoding riêng.
- **Filename của attachment** có quy tắc encoding header riêng; cần quan sát message thực và tương thích mail client.
- **HTML hiển thị** còn phụ thuộc HTML/CSS được client hỗ trợ, không chỉ charset.
- **Dữ liệu đầu vào đã lỗi trước khi dựng mail** không thể tự sửa bằng cách đổi encoding ở helper.

### 4.3. Charset của subject và body

`MimeMessageHelper.setSubject(...)` có thể dùng encoding của helper để tạo tiêu đề chứa Unicode:

~~~java
helper.setSubject("Xác nhận đơn hàng: Đã hoàn tất");
~~~

Khi serialize message, tiêu đề có thể xuất hiện dưới dạng **encoded-word** của MIME theo các quy tắc tương ứng. Người nhận nhìn thấy chuỗi tiếng Việt, trong khi raw header có thể chứa ký hiệu mã hóa. Không nên tự tạo encoded-word rồi lại truyền vào `setSubject(...)` vì có nguy cơ mã hóa lặp.

Tương tự:

~~~java
helper.setText("Đơn hàng của bạn đã được xác nhận.", false);
~~~

là lời gọi dành cho body text. Encoding được áp dụng khi thư viện dựng nội dung part. Nếu đặt cả plain và HTML, từng phần văn bản cũng phải có charset hợp lý:

~~~java
helper.setText(
        "Đơn hàng đã được xác nhận.",
        "<p>Đơn hàng đã <strong>được xác nhận</strong>.</p>");
~~~

Ví dụ `setText(plain, html)` được dùng với helper ở chế độ multipart; nó tạo hai phiên bản nội dung theo ngữ nghĩa `multipart/alternative`.

## 5. Có nên luôn truyền "UTF-8" trong constructor?

**Chỉ định UTF-8 rõ ràng** là lựa chọn thường hợp lý cho nội dung có tiếng Việt và những hệ thống cần kết quả dự đoán được. Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

Lập trình viên cũng có thể dựa vào **default encoding của mail sender** được cấu hình tập trung. Đối với `JavaMailSenderImpl` của Spring, `setDefaultEncoding("UTF-8")` cho biết encoding mặc định cho các message nó tạo. `MimeMessageHelper` có thể nhận biết mặc định này khi dùng message do sender tạo.

Ví dụ trong ứng dụng **Spring Boot**:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    default-encoding: UTF-8
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

Đây là cấu hình cấu trúc; phần credentials, địa chỉ gửi, chính sách TLS và provider phải được cấp từ môi trường triển khai thực tế. `spring.mail.default-encoding` là thuộc tính Spring Boot hỗ trợ cho sender được auto-configure, khác với việc cấu hình trực tiếp `MimeMessageHelper` trong code.

Khi sử dụng Spring Framework không dựa vào Boot, có thể cấu hình bean:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.net");
sender.setPort(587);
sender.setDefaultEncoding("UTF-8");
// Thêm xác thực, TLS, timeout theo yêu cầu hệ thống.
~~~

Không nên hiểu `setDefaultEncoding("UTF-8")` là cấu hình mã hóa SMTP server; đây là mặc định được sử dụng trong quá trình xây dựng message.

### 5.1. Khi không truyền encoding

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message);
~~~

Nếu message được tạo bởi `JavaMailSenderImpl` có default encoding được nhận diện, helper có thể dùng default đó. Với message tự tạo từ Jakarta Mail `Session` hoặc trong môi trường mặc định chưa được cấu hình, encoding hiệu lực có thể dựa vào quy tắc của thư viện/runtime.

Điểm cần nhớ là **không nên dựa vào một “mặc định UTF-8” mơ hồ** khi hệ thống cần gửi nội dung đa ngôn ngữ ổn định trên các môi trường. Có thể truyền encoding vào constructor hoặc xác lập một default sender rõ ràng, rồi kiểm tra thư đã serialize.

### 5.2. Khi nào cấu hình toàn cục, khi nào chỉ định tại chỗ?

| Tình huống | Cách chọn encoding |
| --- | --- |
| Tất cả email của ứng dụng đều dùng Unicode/UTF-8 | Cấu hình `JavaMailSenderImpl.setDefaultEncoding("UTF-8")` hoặc `spring.mail.default-encoding` |
| Một mailer muốn khai báo charset rõ ngay tại chỗ | `new MimeMessageHelper(message, "UTF-8")` |
| Thư có multipart và cần charset rõ | `new MimeMessageHelper(message, true, "UTF-8")` hoặc constructor với mode |
| Hệ thống nhận message nguồn đã dùng charset khác | Phân biệt thao tác parse message có sẵn với việc tạo message mới; tránh đổi charset tùy tiện |
| Email chỉ chứa tài nguyên nhị phân | Charset của helper không biến binary attachment thành text; dùng MIME type và attachment API phù hợp |

Khi chọn encoding, nên giữ một quy ước nhất quán trong hệ thống để dễ kiểm tra. Việc một method dùng UTF-8 và method khác bỏ qua encoding có thể tạo ra sự khác biệt khó phát hiện nếu default sender không được quản lý rõ.

## 6. Ví dụ đầy đủ: khởi tạo helper cho email văn bản tiếng Việt

Một service Spring Framework có thể viết:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailer {

    private final JavaMailSender mailSender;

    public RegistrationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name());

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn đến với hệ thống");
        helper.setText(
                "Xin chào!\nTài khoản của bạn đã được kích hoạt.",
                false);

        mailSender.send(message);
    }
}
~~~

Các thành phần chính:

1. **`JavaMailSender`** được inject qua constructor. Cấu hình SMTP thuộc Spring configuration, không nằm trong code gửi nội dung.
2. **`createMimeMessage()`** cung cấp message mới dành cho lần gửi hiện tại.
3. **`new MimeMessageHelper(message, false, UTF_8)`** khởi tạo helper **không multipart** và có encoding được nêu rõ. `StandardCharsets.UTF_8.name()` trả về tên charset `"UTF-8"`.
4. **`setFrom`, `setTo`, `setSubject`, `setText`** đặt header và body trên message.
5. **`mailSender.send(message)`** kích hoạt transport gửi chính đối tượng đó.

Trong ví dụ, `recipient` là dữ liệu đã được tầng gọi kiểm tra và cấp quyền. Code sản xuất cần sử dụng địa chỉ `From` được SMTP provider cho phép; không để người dùng chưa xác thực chọn tùy ý danh tính gửi.

### 6.1. Vì sao constructor dùng false?

Email này chỉ có một body `text/plain`. Không cần dựng cấu trúc `multipart/mixed` hay `multipart/related` để chứa các part phụ. Chọn `false` giúp ý định rõ ràng: đang gửi một thông điệp text đơn.

Nếu sau này muốn có plain text **và** HTML hoặc thêm PDF, có thể đổi lựa chọn ở lúc khởi tạo helper để bật multipart, rồi bổ sung các part thích hợp. Không nên lén thêm một attachment sau khi đã quyết định chế độ non-multipart.

### 6.2. Vì sao dùng StandardCharsets.UTF_8.name()?

Cả hai cách đều diễn đạt cùng charset:

~~~java
new MimeMessageHelper(message, false, "UTF-8");
new MimeMessageHelper(message, false,
        StandardCharsets.UTF_8.name());
~~~

Dùng `StandardCharsets.UTF_8.name()` tránh đánh máy sai tên charset và tận dụng constant tiêu chuẩn Java. Constructor này nhận một **`String`** encoding; không truyền trực tiếp `StandardCharsets.UTF_8` vì đó là đối tượng `Charset`, không phải `String`.

## 7. Ví dụ: helper có encoding và hai phiên bản text/HTML

Email giao dịch thường có HTML đẹp nhưng vẫn cung cấp bản plain text khi người nhận không dùng HTML:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Hóa đơn tháng 11");

String plain = "Hóa đơn tháng 11 đã sẵn sàng.";
String html = "<p>Hóa đơn tháng 11 đã "
        + "<strong>sẵn sàng</strong>.</p>";

helper.setText(plain, html);
mailSender.send(message);
~~~

Khi `setText(plain, html)` được gọi trên helper multipart, Spring tạo các part mang ý nghĩa **các phiên bản thay thế của cùng nội dung**. Dạng khái quát:

~~~text
MimeMessage
└── multipart/...
    └── multipart/alternative
        ├── text/plain; charset=UTF-8
        └── text/html; charset=UTF-8
~~~

Các container bên ngoài có thể khác theo multipart mode đang sử dụng. Điểm quan trọng là:

- `text/plain` và `text/html` là hai cách trình bày cùng thông tin.
- Charset phải phù hợp cho **mỗi part text**.
- Client email quyết định bản nào được hiển thị theo khả năng và chính sách.
- HTML phải chứa nội dung đã được escape/sanitize phù hợp nếu chèn dữ liệu không đáng tin cậy.

Đối chiếu với:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
helper.setText("<p>Chào bạn!</p>", true);
~~~

Lời gọi này tạo **một bản HTML**, và tham số `true` trong `setText` không bật multipart. Khi chỉ cần một body HTML và không có bản text/attachment, điều đó có thể hoàn toàn phù hợp.

## 8. Ví dụ: helper với mode, UTF-8, ảnh inline và PDF

Khi email có ảnh nhúng được tham chiếu từ HTML và một attachment, nên chọn một cấu trúc MIME có quan hệ rõ giữa body, tài nguyên inline và tệp độc lập.

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailer {

    private final JavaMailSender mailSender;

    public InvoiceMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            Resource logoPng,
            Resource invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn điện tử của bạn");

        String plain = "Hóa đơn đã sẵn sàng; vui lòng xem PDF.";
        String html = "<p>Hóa đơn đã <strong>sẵn sàng</strong>.</p>"
                + "<img src=\"cid:company-logo\" alt=\"Logo\">"
                + "<p>Vui lòng xem tệp PDF đính kèm.</p>";

        // Tạo body trước khi thêm tài nguyên inline.
        helper.setText(plain, html);
        helper.addInline("company-logo", logoPng, "image/png");
        helper.addAttachment("invoice.pdf", invoicePdf);

        mailSender.send(message);
    }
}
~~~

Ví dụ này cho thấy **hai lựa chọn độc lập** ở constructor:

- `MULTIPART_MODE_MIXED_RELATED` chọn cách tổ chức MIME: body và ảnh inline có quan hệ với nhau; PDF là attachment độc lập.
- `UTF-8` chọn encoding dùng cho text/subject do helper tạo.

Một cây điển hình có thể là:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       <img src="cid:company-logo">
    │   └── image/png
    │       Content-ID: <company-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Đây là cây minh họa của mode phổ biến; cần inspect message thực để biết cấu trúc cụ thể của thư viện trong ứng dụng.

**Những điều cần lưu ý:**

1. **`setText(plain, html)` trước `addInline(...)`**: Spring khuyến nghị thiết lập phần body trước khi thêm ảnh inline để tài nguyên được đặt vào quan hệ MIME thích hợp.
2. **CID khớp nhau**: `cid:company-logo` trong HTML phải tương ứng với ID `company-logo` truyền vào `addInline(...)`.
3. **Resource có thể đọc được**: logo và PDF phải đến từ nguồn đã được cấp quyền; tránh đưa đường dẫn nội bộ do người dùng tự chỉ định vào email.
4. **Nguồn stream có thể mở lại khi cần**: Jakarta Mail có thể cần đọc nội dung trong quá trình serialize; một `InputStreamSource` không thể mở lại sẽ dễ gây lỗi.
5. **Không biến binary thành text**: tham số `"UTF-8"` không làm thay đổi bản chất bytes của PDF/PNG; mỗi attachment có MIME content type và transfer encoding riêng.
6. **Giới hạn kích thước**: SMTP provider có thể đặt giới hạn tổng dung lượng email sau MIME encoding, lớn hơn dung lượng tệp gốc.

### 8.1. Khi nào constructor true là đủ?

Nếu chỉ thêm một PDF:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("Báo cáo đã sẵn sàng.", false);
helper.addAttachment("report.pdf", reportResource);
~~~

Dạng boolean có thể đủ cho nhiều ứng dụng. Nhưng khi cần kiểm soát rõ mối quan hệ giữa inline resource và attachment trên các mail client, việc chọn mode cụ thể thường dễ giải thích và kiểm tra hơn.

### 8.2. Các multipart mode thường gặp

| Mode | Cách tổ chức chính | Trường hợp cần cân nhắc |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Không dùng multipart để thêm tài nguyên | Email body đơn giản |
| `MULTIPART_MODE_MIXED` | Nhóm nhiều part dưới `multipart/mixed` | Kết hợp body/attachment; sự hỗ trợ inline có thể khác theo client |
| `MULTIPART_MODE_RELATED` | Nhóm các part có liên hệ dưới `multipart/related` | HTML kèm tài nguyên liên quan |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` bên ngoài, `related` cho body và inline ở bên trong | Email có cả inline image và attachment |

Chọn mode đúng là quyết định về **cấu trúc thư**, không phải quyết định về charset. Một email có thể dùng UTF-8 mà không multipart, hoặc có multipart phức tạp nhưng mỗi part text vẫn phải xác định charset phù hợp.

## 9. Lỗi dễ xảy ra ngay khi khởi tạo helper

### 9.1. Truyền sai message

~~~java
MimeMessage messageA = mailSender.createMimeMessage();
MimeMessage messageB = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(messageA, "UTF-8");

helper.setTo("lan@example.net");
helper.setText("Nội dung A", false);
mailSender.send(messageB);
~~~

Lỗi là **gửi messageB**, trong khi helper đang soạn trên messageA. Hãy giữ một biến message theo mỗi lần gửi và dùng biến đó nhất quán.

### 9.2. Quên bật multipart trước khi thêm attachment

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setText("Đã đính kèm báo cáo.", false);
helper.addAttachment("report.pdf", reportResource);
~~~

Helper được khởi tạo không multipart, nên thao tác thêm attachment đòi hỏi một cấu trúc mà nó chưa có. Cần chọn constructor multipart ngay từ đầu:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Đừng hiểu `helper.setText(html, true)` là đã bật multipart. `true` ở phương thức đó chỉ đánh dấu nội dung HTML.

### 9.3. Bỏ encoding và dựa vào môi trường

Một hệ thống chạy đúng trên máy lập trình viên nhưng chữ tiếng Việt bị lỗi ở một runtime khác có thể do charset đầu vào, default encoding hoặc dữ liệu serialize. Chỉ định UTF-8 rõ ràng hoặc cấu hình default sender giúp giảm biến số, nhưng vẫn cần kiểm tra xem dữ liệu nguồn **đã đúng trước khi tạo message** chưa.

Nếu body đầu vào đã là chuỗi `"ChÃ o"` thay vì `"Chào"`, chuyển sang `new MimeMessageHelper(message, "UTF-8")` không tự sửa chuỗi Java đã hỏng.

### 9.4. Tạo helper trước khi có message hợp lệ

Helper cần một `MimeMessage` thực sự. Trong test, nếu mock `JavaMailSender.createMimeMessage()` trả về `null`, việc khởi tạo hoặc gọi helper không thể hoạt động bình thường.

Khi kiểm thử code tạo thư, nên cấp một message hợp lệ bằng fake sender hoặc mock có cấu hình:

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
// Khi mock createMimeMessage(), trả lại message hợp lệ này.
~~~

Đoạn ví dụ cần import `jakarta.mail.Session`, `jakarta.mail.internet.MimeMessage` và `java.util.Properties`. Đây chỉ là ví dụ tạo message độc lập phục vụ **kiểm thử**, không yêu cầu kết nối SMTP.

### 9.5. Tạo message mới để sửa encoding của thư đã có

Giả sử ứng dụng đọc một email đã nhận mà part text khai báo charset khác. Khởi tạo `MimeMessageHelper(existingMessage, "UTF-8")` chỉ cấu hình các **thao tác gán nội dung tiếp theo của helper**, không tự chuyển đổi toàn bộ bytes đã tồn tại trong các part cũ sang UTF-8. Muốn chuẩn hóa thư có sẵn phải hiểu nội dung nguồn và cách parse/serialize, tránh ghi đè charset gây mất dữ liệu.

### 9.6. Dùng encoding có tên sai

~~~java
new MimeMessageHelper(message, "UTF_8"); // Không phải tên chuẩn nên dùng.
~~~

Nên dùng `"UTF-8"` hoặc `StandardCharsets.UTF_8.name()`. Nếu charset không được hỗ trợ, lỗi có thể xuất hiện khi helper hoặc Jakarta Mail áp dụng encoding vào header/body, tùy thao tác đang thực hiện.

## 10. Lỗi encoding có thể xuất hiện ở đâu?

| Hiện tượng | Vị trí nên kiểm tra | Giải thích có thể xảy ra |
| --- | --- | --- |
| Tiêu đề có ký tự `=?UTF-8?...?=` trên client | Raw header `Subject` và client parser | Header encoded-word bị hiển thị như văn bản thô hoặc mã hóa lặp |
| Body tiếng Việt thành ký tự rác | Bytes đầu vào, `Content-Type; charset`, Content-Transfer-Encoding | Nội dung được giải mã bằng bảng mã khác với bảng mã đã dùng |
| HTML xuất hiện dưới dạng thẻ text | `setText(text, isHtml)` và `Content-Type` | Đặt `isHtml=false` cho nội dung HTML |
| Chỉ hiện plain dù có HTML | Cây `multipart/alternative`, thứ tự part và chính sách client | Alternative không đúng hoặc client chọn bản plain |
| Ảnh inline bị hỏng | `cid:...`, `Content-ID`, `multipart/related` | Tài nguyên không khớp reference hoặc client không hỗ trợ |
| Tên PDF bị lỗi ký tự | Header filename của attachment, encoding tên tệp | Tên tệp có quy tắc encode header riêng |
| UTF-8 đúng trên local nhưng sai ở production | Default sender, config và dữ liệu template | Môi trường dùng nguồn dữ liệu hoặc encoding khác |

Điểm khác biệt quan trọng: **lỗi transport SMTP** như `MailAuthenticationException` hoặc `SocketTimeoutException` không thể sửa chỉ bằng cách đổi encoding constructor. Ngược lại, SMTP trả thành công nhưng mail hiển thị lỗi thì cần inspect MIME tree và dữ liệu thực, chưa chắc liên quan kết nối mạng.

## 11. Quan sát MimeMessage sau khi dùng helper

Vì constructor nhận `message`, ứng dụng vẫn giữ được chính đối tượng đang soạn và có thể serialize nó để quan sát MIME trước khi gửi. Trong môi trường thử nghiệm có kiểm soát:

~~~java
package com.example.mail;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MimePreview {

    private final JavaMailSender mailSender;

    public MimePreview(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void exportSample(Path destination)
            throws IOException, MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo("test-recipient@example.net");
        helper.setSubject("Báo cáo: Đã sẵn sàng");
        helper.setText("Xin chào, báo cáo đã được tạo.", false);

        message.saveChanges();
        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }
}
~~~

Phương thức này **chưa gửi email** vì không gọi `mailSender.send(message)`. Nó chỉ ghi message vào tệp `.eml` để xem cấu trúc.

Dạng header có thể gặp:

~~~text
From: reports@example.com
To: test-recipient@example.net
Subject: =?UTF-8?...?=
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

[Body được mã hóa theo Content-Transfer-Encoding nếu cần]
~~~

Đây là **ví dụ rút gọn**, không phải email raw hoàn chỉnh dùng để phát đi. Header thực tế, dạng subject encoded-word và transfer encoding cụ thể do Jakarta Mail quyết định.

Với thư multipart, root có thể mang `Content-Type: multipart/mixed` và **không có `charset=UTF-8` tại root**. Charset nằm tại các part `text/plain`/`text/html` ở bên trong. Khi chẩn đoán, phải duyệt các part chứ không chỉ xem `Content-Type` của message gốc.

### 11.1. Nếu email nhận được vẫn hiển thị lỗi

Hãy phân biệt bốn lớp dữ liệu:

1. **Java String trước khi đưa vào helper**: ký tự tiếng Việt đã đúng chưa?
2. **MimeMessage sau khi serialize**: Content-Type, charset và dữ liệu body có phù hợp không?
3. **Email thực ở hộp thư nhận**: gateway hoặc dịch vụ trung gian có thay đổi body/header không?
4. **Trình đọc thư**: client có lọc HTML, ảnh từ xa hoặc có cách giải mã khác không?

Nếu hai phiên bản plain/HTML nằm sai thứ tự trong `multipart/alternative`, thay đổi encoding không sửa được cây MIME. Nếu cây đúng nhưng bytes của body không khớp charset, cần quay lại dữ liệu nguồn và cách dùng helper.

Việc xuất `.eml` chỉ nên thực hiện với dữ liệu giả lập hoặc trong môi trường được phép; email thật có thể chứa thông tin cá nhân, URL nhạy cảm và tệp đính kèm không được công bố.

## 12. Kết hợp với cấu hình Spring Boot theo môi trường

Một ứng dụng chạy local, staging và production có thể dùng cùng code soạn thư:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

Trong khi đó, cấu hình SMTP nằm trong các property sources và Spring profiles. Ví dụ cấu hình chung:

~~~yaml
# application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Ví dụ môi trường local dùng SMTP sink cô lập:

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
~~~

Ví dụ production dùng SMTP submission với STARTTLS:

~~~yaml
# application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

Những placeholder được lấy từ environment hoặc nguồn bí mật phù hợp; không commit password thật vào repository. SMTP sink local không auth/TLS chỉ phù hợp với mạng thử nghiệm cô lập. Việc gửi qua provider thực tế cần TLS, xác thực và quyền gửi phù hợp với dịch vụ.

Ở ví dụ này:

- `spring.mail.default-encoding=UTF-8` đặt **mặc định cho sender**.
- `new MimeMessageHelper(message, false, "UTF-8")` khai báo charset **tại nơi soạn thư**.
- `spring.mail.host`, `port` và các properties SMTP quyết định **nơi và cách gửi thư**, không phải charset của body.

Khi helper đã nhận encoding tường minh, code gửi không cần đọc active profile để tự quyết định bảng mã. Nếu các môi trường đều cần nội dung tiếng Việt nhất quán, cách này tránh phụ thuộc vào những mặc định không rõ ràng.

## 13. Những nhầm lẫn cần tránh

**“MimeMessageHelper tạo ra một email mới?”**  
Helper là đối tượng hỗ trợ **chỉnh sửa `MimeMessage` được truyền vào**. Thông điệp thường được tạo trước qua `JavaMailSender.createMimeMessage()`.

**“Tôi đã gọi new MimeMessageHelper nên thư đã gửi?”**  
Chưa. Các constructor và setter chỉ chuẩn bị email. Cần gọi `JavaMailSender.send(message)` để gửi.

**“Tham số true ở constructor có nghĩa là HTML?”**  
Không. `new MimeMessageHelper(message, true, "UTF-8")` có `true` nghĩa là **multipart**. `helper.setText(body, true)` có `true` nghĩa là **HTML**.

**“Muốn HTML thì bắt buộc multipart?”**  
Không. Một email HTML đơn có thể dùng `new MimeMessageHelper(message, "UTF-8")` và `setText(html, true)`. Multipart cần khi kết hợp các phần như text/HTML alternatives, inline images hoặc attachments.

**“Đặt UTF-8 sẽ mã hóa cả ảnh và PDF theo kiểu text?”**  
Không. Nội dung nhị phân có cơ chế MIME/transfer encoding riêng. `UTF-8` ở helper chủ yếu phục vụ các trường văn bản mà helper tạo.

**“UTF-8 cho phép mọi địa chỉ email Unicode?”**  
Không. Địa chỉ email quốc tế có thể cần SMTP extension `SMTPUTF8` và provider hỗ trợ; charset của subject/body là một vấn đề khác.

**“Đổi encoding có tự sửa một thư đã tạo với charset sai?”**  
Không. Tạo helper mới với encoding khác không tự chuyển đổi mọi part cũ an toàn. Cần xử lý đúng dữ liệu nguồn và dựng lại nội dung nếu cần.

**“MimeMessageHelper(message) luôn dùng UTF-8?”**  
Không nên giả định như vậy khi chưa biết default sender và Jakarta Mail runtime. Có thể truyền `UTF-8` rõ ràng hoặc cấu hình default encoding được kiểm soát.

**“Vì sao root MIME không ghi UTF-8?”**  
Trong email multipart, charset thường được khai báo ở các part text con. Root chứa loại container như `multipart/mixed` hoặc `multipart/related`.

## 14. Chọn constructor nào cho từng nhu cầu?

| Nhu cầu | Constructor thường phù hợp | API tạo nội dung |
| --- | --- | --- |
| Email plain text tiếng Việt | `new MimeMessageHelper(message, false, "UTF-8")` | `setText(text, false)` |
| Email HTML đơn giản | `new MimeMessageHelper(message, "UTF-8")` | `setText(html, true)` |
| Email có plain và HTML | `new MimeMessageHelper(message, true, "UTF-8")` | `setText(plain, html)` |
| Email có PDF | `new MimeMessageHelper(message, true, "UTF-8")` | `setText(...)` và `addAttachment(...)` |
| HTML kèm ảnh CID và PDF | `new MimeMessageHelper(message, MULTIPART_MODE_MIXED_RELATED, "UTF-8")` | `setText(plain, html)`, `addInline(...)`, `addAttachment(...)` |
| Sender có default encoding quản lý tập trung | `new MimeMessageHelper(message)` hoặc constructor với mode | Setter phù hợp; xác định default sender trước |

Đối với phần lớn service gửi email văn bản thuần, mẫu khởi tạo có thể viết:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo mới");
helper.setText("Nội dung tiếng Việt được tạo bằng UTF-8.", false);

mailSender.send(message);
~~~

Khi cần nhiều MIME parts, chọn constructor bật multipart và dùng mode thích hợp. Trong mọi trường hợp, **`message` phải là đối tượng sẽ được gửi**, còn `encoding` nên là charset rõ ràng cho nội dung văn bản. Việc hiểu đúng hai tham số này cùng chế độ multipart giúp tránh lỗi ký tự, tránh gửi nhầm đối tượng và mở rộng an toàn từ email text đơn sang HTML, inline images hoặc attachment.
