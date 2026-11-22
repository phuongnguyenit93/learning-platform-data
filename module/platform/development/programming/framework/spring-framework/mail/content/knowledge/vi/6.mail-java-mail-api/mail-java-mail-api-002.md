# JavaMailSender và khả năng tạo MimeMessage

## 1. JavaMailSender giải quyết vấn đề gì?

Trong một ứng dụng Java sử dụng **Spring Framework Mail**, nhu cầu gửi email thường bắt đầu từ những thông tin nghiệp vụ: người nhận, tiêu đề, nội dung, hình ảnh và tệp đính kèm. Để chuyển các thông tin ấy thành thư điện tử hợp lệ, ứng dụng cần một API tạo thông điệp, đặt header, mã hóa nội dung và giao tiếp với hệ thống gửi mail.

**`JavaMailSender`** là giao diện của Spring dành cho việc gửi thư thông qua **Jakarta Mail**. Nó cung cấp hai năng lực quan trọng:

1. **Tạo một `MimeMessage`** để ứng dụng chủ động xây dựng email có cấu trúc MIME.
2. **Gửi `MimeMessage` hoặc chuẩn bị và gửi message** thông qua một mail transport đã cấu hình, thường là SMTP.

`MimeMessage` là kiểu thông điệp của Jakarta Mail có thể biểu diễn email văn bản, HTML, nhiều phiên bản nội dung, tài nguyên inline và attachment. `JavaMailSender` không phải SMTP server, không phải giao diện soạn thư cho người dùng và không tự bảo đảm thông điệp được người nhận đọc. Nó là **điểm tích hợp phía ứng dụng** giữa logic nghiệp vụ của Spring và cơ chế tạo/vận chuyển email của Jakarta Mail.

Ví dụ các tình huống cần `JavaMailSender`:

- Gửi email xác minh tài khoản có đường dẫn và HTML template.
- Gửi hóa đơn PDF kèm thông điệp văn bản.
- Gửi báo cáo với bảng HTML và logo hiển thị ngay trong nội dung.
- Gửi email hai phiên bản `text/plain` và `text/html` để các mail client có thể lựa chọn cách hiển thị phù hợp.
- Tạo hoặc đọc lại một thư MIME từ nguồn `.eml` để xử lý theo nghiệp vụ được phép.

Nếu chỉ cần vài dòng văn bản thuần không attachment, Spring còn có `SimpleMailMessage`; khi cần các khả năng MIME, `JavaMailSender.createMimeMessage()` là điểm khởi đầu tự nhiên.

## 2. Đặt JavaMailSender trong kiến trúc Spring Mail

Các lớp liên quan có vai trò khác nhau:

| Thành phần | Vai trò | Ai sở hữu? |
| --- | --- | --- |
| `MailSender` | Hợp đồng Spring gửi `SimpleMailMessage` | Spring Framework |
| `JavaMailSender` | Mở rộng `MailSender`, tạo và gửi `MimeMessage`; hỗ trợ `MimeMessagePreparator` | Spring Framework |
| `JavaMailSenderImpl` | Cài đặt thông dụng, quản lý cấu hình và gọi Jakarta Mail transport | Spring Framework |
| `MimeMessage` | Đối tượng thông điệp MIME, chứa header/body và các part | Jakarta Mail |
| `MimeMessageHelper` | Lớp hỗ trợ đặt To/Cc/Bcc, Subject, text/HTML, inline resource và attachment | Spring Framework |
| `MimeMessagePreparator` | Callback chuẩn bị `MimeMessage` do sender cấp | Spring Framework |
| `Session` / `Transport` | Cấu hình môi trường và vận chuyển thư theo cơ chế Jakarta Mail | Jakarta Mail |
| SMTP server/provider | Tiếp nhận, xác thực, chuyển thư theo giao thức/chính sách | Hạ tầng email |

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    A["Service nghiệp vụ Spring"] --> B["JavaMailSender"]
    B --> C["createMimeMessage()"]
    C --> D["MimeMessage"]
    E["MimeMessageHelper hoặc MimeMessagePreparator"] --> D
    D --> F["send(...)"]
    F --> G["Jakarta Mail Transport"]
    G --> H["SMTP Server / email provider"]
    H --> I["Hạ tầng chuyển phát"]
~~~

Trong ứng dụng Spring Boot thông dụng, starter mail cùng cấu hình `spring.mail.*` có thể cung cấp bean `JavaMailSender`. Trong ứng dụng Spring Framework thuần, ta có thể khai báo một bean `JavaMailSenderImpl` theo cách cấu hình của dự án.

Điểm cần phân biệt: **`JavaMailSender` là interface**, còn **`JavaMailSenderImpl` là implementation**. Service nên phụ thuộc vào interface để dễ thay transport, cấu hình hoặc kiểm thử.

## 3. API cốt lõi của JavaMailSender

`JavaMailSender` kế thừa khả năng gửi `SimpleMailMessage` từ `MailSender` và bổ sung các thao tác dành cho MIME.

| Phương thức tiêu biểu | Công dụng | Kết quả cần hiểu đúng |
| --- | --- | --- |
| `createMimeMessage()` | Tạo một `MimeMessage` mới | Chỉ tạo đối tượng để soạn; **chưa gửi email** |
| `createMimeMessage(InputStream)` | Tạo/parse `MimeMessage` từ dữ liệu MIME đã được serialize | Phù hợp đọc một nguồn chứa message hoàn chỉnh, ví dụ `.eml` |
| `send(MimeMessage)` | Gửi một thông điệp đã chuẩn bị | Kích hoạt mail transport; có thể phát sinh `MailException` |
| `send(MimeMessage...)` | Gửi nhiều thông điệp | Không mặc nhiên bảo đảm tính nguyên tử cho toàn bộ lô |
| `send(MimeMessagePreparator)` | Để sender tạo message, gọi callback chuẩn bị rồi gửi | Thuận tiện khi muốn gói việc xây dựng và gửi |
| `send(MimeMessagePreparator...)` | Chuẩn bị và gửi nhiều message | Cần xử lý trường hợp một phần thành công/một phần lỗi |
| `send(SimpleMailMessage)` | Gửi thư text đơn giản | Thuộc hợp đồng `MailSender` mà `JavaMailSender` kế thừa |

API này **không cung cấp giao diện Inbox, tìm kiếm thư đã nhận hoặc quản lý thư nháp của người dùng**. Nó phục vụ nhánh tạo/gửi email ở server. Những chức năng nhận và đọc mail thường phải dùng API khác, chẳng hạn các phần của Jakarta Mail hoặc API riêng của nhà cung cấp.

### 3.1. createMimeMessage() khác send() ra sao?

Xét vòng đời:

~~~text
JavaMailSender
    |
    +-- createMimeMessage()
    |       |
    |       +-- MimeMessage ban đầu
    |               |
    |               +-- setFrom, setTo, setSubject, setText...
    |               +-- thêm các MIME part nếu cần
    |               |
    |               +-- send(message)
    |                       |
    |                       +-- Jakarta Mail transport
    |                               |
    |                               +-- SMTP submission
    |
    +-- createMimeMessage(InputStream)
            |
            +-- parse message từ dữ liệu MIME nguồn
~~~

Khi gọi `createMimeMessage()`, ứng dụng **chưa tạo kết nối SMTP chỉ vì phương thức này được gọi**, và chưa có người nhận hay body nếu lập trình viên chưa gán. Việc gửi chỉ xảy ra khi `send(...)` được gọi hoặc một workflow gửi tương đương được kích hoạt.

Điều đó có các hệ quả:

- Có thể chuẩn bị, xem header, bổ sung attachment hoặc serialize message trước lúc gửi.
- Có thể phát hiện lỗi tạo MIME trước giai đoạn gửi qua mạng.
- Không nên kết luận “đã gửi thành công” chỉ vì một `MimeMessage` đã được tạo.
- Không nên tái sử dụng cùng một đối tượng `MimeMessage` rồi thay đổi nó đồng thời từ nhiều luồng; mỗi lượt gửi nên tạo message riêng theo dữ liệu của lượt đó.

### 3.2. MimeMessage có thể chứa những gì?

Thông điệp MIME gồm **các header**, phần **body** và có thể nhiều node con trong một cấu trúc `multipart`.

Ví dụ message chỉ chứa text:

~~~text
MimeMessage
├── From: reports@example.com
├── To: lan@example.net
├── Subject: Weekly report
└── text/plain; charset=UTF-8
    "Báo cáo tuần đã sẵn sàng."
~~~

Ví dụ message có text, HTML, ảnh inline và PDF:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       <img src="cid:weekly-logo">
    │   └── image/png
    │       Content-ID: <weekly-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="weekly-report.pdf"
~~~

Đây là **cấu trúc minh họa**; cây cụ thể phụ thuộc cách sử dụng `MimeMessageHelper`, chế độ multipart và cách các thành phần được thêm vào. `multipart/alternative` diễn tả các phiên bản thay thế của cùng một nội dung, `multipart/related` nhóm body với tài nguyên liên quan, còn `multipart/mixed` thường kết hợp body với attachment độc lập.

## 4. Tạo MimeMessage đơn giản với MimeMessageHelper

`MimeMessage` thuộc Jakarta Mail và có API trực tiếp để đặt các trường. Tuy nhiên Spring cung cấp **`MimeMessageHelper`** để các thao tác thường gặp trở nên ngắn gọn, đặc biệt khi cần charset, HTML hoặc multipart.

Ví dụ service gửi email văn bản với Spring Framework 6 và package `jakarta.mail.*`:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailer {

    private final JavaMailSender mailSender;

    public AccountNotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false, // Không cần multipart cho plain text đơn giản.
                StandardCharsets.UTF_8.name());

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");
        helper.setText("Xin chào " + displayName
                + ", tài khoản của bạn đã sẵn sàng.", false);

        mailSender.send(message);
    }
}
~~~

Diễn giải từng phần:

1. **Tiêm dependency** `JavaMailSender` qua constructor; service không phụ thuộc vào lớp `JavaMailSenderImpl`.
2. **Tạo message** bằng `mailSender.createMimeMessage()`. Chưa có email nào được gửi.
3. **Tạo helper** với `multipart=false`, charset `UTF-8` để soạn thư văn bản.
4. **Đặt các trường** `From`, `To`, `Subject` và body bằng `helper`.
5. **Gọi send** để Jakarta Mail thực hiện việc vận chuyển qua server cấu hình.

`helper.setText(body, false)` có tham số `false` nghĩa là **plain text**. Nếu đặt `true`, nội dung được biểu diễn là **HTML**. Với text đơn giản, có thể dùng `SimpleMailMessage`; ví dụ dùng `MimeMessage` để giải thích API và thuận tiện mở rộng về sau.

Trong ứng dụng thực tế, `recipient` phải được kiểm tra theo hợp đồng nghiệp vụ, `displayName` phải được xử lý phù hợp, và địa chỉ `From` phải được hệ thống SMTP cho phép sử dụng. Ví dụ trên không xây dựng endpoint công khai để ai cũng có thể gửi tới địa chỉ tùy ý.

### 4.1. Có thể thao tác trực tiếp trên MimeMessage không?

Có. Ví dụ với Jakarta Mail:

~~~java
MimeMessage message = mailSender.createMimeMessage();
message.setFrom(new jakarta.mail.internet.InternetAddress(
        "notifications@example.com"));
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        jakarta.mail.internet.InternetAddress.parse("lan@example.net"));
message.setSubject("Thông báo", "UTF-8");
message.setText("Nội dung thông báo", "UTF-8");

mailSender.send(message);
~~~

Các setter trên `MimeMessage` có thể ném `MessagingException`; ví dụ giả định đang nằm trong method khai báo hoặc xử lý ngoại lệ phù hợp. Lưu ý lớp `MimeMessage` không yêu cầu sử dụng `MimeMessageHelper`, nhưng khi cấu trúc thư phức tạp, helper giúp quản lý multipart, charset và nguồn tài nguyên dễ hơn.

## 5. Tạo email HTML với bản plain text dự phòng

Nhiều email giao dịch cần định dạng HTML nhưng vẫn nên có bản văn bản thuần. Một số trình đọc thư không hiển thị HTML, hoặc người dùng tắt HTML vì chính sách bảo mật/khả năng truy cập.

Thông điệp nên có `multipart/alternative`:

~~~text
multipart/alternative
├── text/plain
│   "Đơn hàng #A102 đã được xác nhận."
└── text/html
    "<p>Đơn hàng <strong>#A102</strong> đã được xác nhận.</p>"
~~~

Với `MimeMessageHelper` đã được khởi tạo ở chế độ multipart, có thể tạo hai phiên bản:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Xác nhận đơn hàng");

String plainText = "Đơn hàng #A102 đã được xác nhận.";
String htmlText =
        "<p>Đơn hàng <strong>#A102</strong> đã được xác nhận.</p>";

helper.setText(plainText, htmlText);

mailSender.send(message);
~~~

Phương thức `setText(String plainText, String htmlText)` tạo **hai phiên bản của cùng nội dung** theo ngữ nghĩa MIME. Đây là lựa chọn rõ ràng hơn việc tự thêm hai body part độc lập vào `multipart/mixed`, vì client có thể hiểu sai và hiển thị cả hai.

Nếu chỉ có HTML, một dạng ngắn hơn là:

~~~java
helper.setText(
        "<p>Đơn hàng đã <strong>được xác nhận</strong>.</p>",
        true);
~~~

Tham số `true` yêu cầu content type HTML. Nó **không tự bổ sung bản plain text**: nếu muốn có cả hai, hãy dùng overload với hai chuỗi.

### 5.1. Tạo HTML đúng MIME không có nghĩa mọi client hiển thị giống nhau

Client email có thể bỏ CSS phức tạp, JavaScript, form hoặc hình ảnh từ xa. Dù `Content-Type: text/html` đúng, HTML mail vẫn cần được thiết kế phù hợp với các phần mềm đích. Với dữ liệu do người dùng cung cấp, phải escape và chèn vào template một cách an toàn; không nên nối HTML tùy ý rồi coi đó là nội dung đã tin cậy.

Ngoài ra, chuỗi HTML là **body**; nội dung bên trong không được dùng để thay thế những trường `From`/`To`/`Subject` nằm trong header của thông điệp.

## 6. Tạo attachment và ảnh inline trong một MimeMessage

Khi gửi email có PDF và logo hiển thị trong HTML, chỉ một nội dung `text/html` đơn lẻ là chưa đủ. Cần quan hệ MIME giữa body, ảnh nhúng và attachment.

Spring cung cấp các thao tác:

- `MimeMessageHelper.addAttachment(...)` để thêm file đính kèm độc lập.
- `MimeMessageHelper.addInline(...)` để thêm tài nguyên có `Content-ID` và tham chiếu trong HTML bằng `cid:...`.
- Các chế độ `MULTIPART_MODE_*` để chọn cách tổ chức MIME containers.

Ví dụ service tạo email có bản text, HTML, logo PNG và PDF:

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
public class WeeklyReportMailer {

    private final JavaMailSender mailSender;

    public WeeklyReportMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            Resource logoPng,
            Resource reportPdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tuần");

        String plain = "Báo cáo tuần đã sẵn sàng."
                + " Xem tệp PDF đính kèm.";

        String html = "<p>Báo cáo tuần đã <strong>sẵn sàng</strong>.</p>"
                + "<img src=\"cid:weekly-logo\" alt=\"Logo\">"
                + "<p>Xem tệp PDF đính kèm.</p>";

        helper.setText(plain, html);
        helper.addInline("weekly-logo", logoPng, "image/png");
        helper.addAttachment("weekly-report.pdf", reportPdf);

        mailSender.send(message);
    }
}
~~~

**Các chi tiết quan trọng:**

**Chế độ multipart.** `MULTIPART_MODE_MIXED_RELATED` thường tạo một `multipart/mixed` bên ngoài để phân biệt attachment với body, và một `multipart/related` bên trong cho body cùng những tài nguyên inline. Các part `text/plain` và `text/html` tiếp tục được tổ chức theo quan hệ `alternative`.

**Content-ID.** Trong HTML, `src="cid:weekly-logo"` phải tương ứng với ID `weekly-logo` được truyền vào `helper.addInline(...)`. MIME có thể tạo header `Content-ID: <weekly-logo>`; dấu ngoặc góc là cách thể hiện header, không thuộc chuỗi `cid:` trong HTML.

**Thứ tự thao tác.** Hãy gọi `setText(...)` trước `addInline(...)` khi xây dựng HTML có ảnh nhúng, để phần body HTML tồn tại đúng lúc tài nguyên inline được thêm vào.

**Nguồn dữ liệu.** `Resource` phải cung cấp dữ liệu đọc được. Với `InputStreamSource`, một số quá trình serialize/gửi có thể cần mở luồng nhiều lần; không nên cung cấp một stream đã bị tiêu thụ và không thể mở lại. Có thể dùng file resource hoặc `ByteArrayResource` nếu dữ liệu đã được kiểm soát kích thước và phù hợp với cách triển khai.

**File đính kèm.** Tên tệp `weekly-report.pdf` là tên hiển thị cho người nhận, không nhất thiết trùng đường dẫn của file trên server. Không nên cho phía client tự chọn một đường dẫn máy chủ để gửi file; backend phải xác nhận quyền truy cập và giới hạn kích thước.

### 6.1. Các chế độ multipart trong MimeMessageHelper

| Chế độ | Mục đích chính | Trường hợp lưu ý |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Không tạo cây multipart để quản lý inline/attachment | Phù hợp message đơn giản, không cần nhiều MIME part |
| `MULTIPART_MODE_MIXED` | Một container `multipart/mixed` | Cách hiển thị tài nguyên inline có thể khác giữa các client |
| `MULTIPART_MODE_RELATED` | Container `multipart/related` | Quan hệ body và attachment có thể được diễn giải khác nhau |
| `MULTIPART_MODE_MIXED_RELATED` | `mixed` bao ngoài `related` | Thường phù hợp khi body có ảnh inline và thư có attachment |

Không có một kiểu cây duy nhất phù hợp tuyệt đối với mọi client. Nếu email hiển thị khác nhau giữa các ứng dụng, cần inspect nội dung MIME thực tế và chọn cấu trúc tương thích với nhóm client mục tiêu.

### 6.2. Khi nào cần xem MIME tree được tạo ra?

Nếu một email tới nơi nhưng PDF biến mất hoặc logo thành hình lỗi, hãy xem toàn bộ cây MIME, không chỉ HTML string:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png [inline] Content-ID=<weekly-logo>
    └── application/pdf [attachment] filename=weekly-report.pdf
~~~

Kiểm tra các trường `Content-Type`, `Content-ID`, `Content-Disposition`, charset, filename và boundary của từng part. Nếu ảnh được đặt nhầm trong một nhánh không liên quan, hoặc PDF được coi là alternative của HTML, client có thể hiển thị ngoài dự kiến.

## 7. MimeMessagePreparator: tạo và gửi trong một callback

Ngoài cách gọi `createMimeMessage()` rồi `send(message)`, `JavaMailSender` hỗ trợ **`MimeMessagePreparator`**. Callback nhận một `MimeMessage` mà sender đã tạo, để code nghiệp vụ đặt nội dung:

~~~java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class PasswordChangedMailer {

    private final JavaMailSender mailSender;

    public PasswordChangedMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        mailSender.send(mimeMessage -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mimeMessage, false, "UTF-8");

            helper.setFrom("security@example.com");
            helper.setTo(recipient);
            helper.setSubject("Mật khẩu đã thay đổi");
            helper.setText(
                    "Mật khẩu tài khoản của bạn vừa được thay đổi.",
                    false);
        });
    }
}
~~~

Ở đây:

1. `JavaMailSender` tạo một `MimeMessage` mới.
2. Callback được gọi để thiết lập các trường.
3. Khi callback hoàn tất, sender thực hiện gửi thông điệp.
4. Nếu callback hoặc vận chuyển thất bại, API Spring báo lỗi qua hệ thống ngoại lệ mail phù hợp.

Ưu điểm của cách này là tạo và gửi message nằm trong một lời gọi ở service, giảm nguy cơ quên `send(...)`. Hạn chế là nếu muốn giữ lại đối tượng để quan sát nhiều bước trước khi gửi, cách tạo `MimeMessage` trực tiếp thường rõ ràng hơn.

Không nên hiểu `MimeMessagePreparator` là một job chạy nền hay một tính năng tự gửi lại. Callback chạy như một phần của lời gọi gửi thư; việc gửi bất đồng bộ, đưa vào hàng đợi hoặc retry cần cơ chế riêng.

### 7.1. Chọn cách viết nào?

| Cách dùng | Ví dụ | Nên chọn khi |
| --- | --- | --- |
| Tạo trước rồi gửi | `MimeMessage m = sender.createMimeMessage(); ...; sender.send(m);` | Cần inspect, bổ sung các phần theo nhiều bước hoặc serialize trước khi gửi |
| Dùng preparator | `sender.send(message -> { ... });` | Việc chuẩn bị đơn giản, gói trọn trong một callback |
| Dùng simple message | `sender.send(simpleMailMessage);` | Email text thuần, không cần các MIME part phức tạp |

Đây là những cách dùng cùng nền tảng transport Spring Mail. Chọn cách phù hợp với nhu cầu đọc code, khả năng mở rộng và ranh giới nghiệp vụ.

## 8. createMimeMessage(InputStream): đọc lại thông điệp MIME có sẵn

Đa số ví dụ dùng `createMimeMessage()` không tham số để soạn email từ đầu. Nhưng `JavaMailSender` còn cung cấp:

~~~java
MimeMessage createMimeMessage(InputStream contentStream);
~~~

Mục đích là **tạo một `MimeMessage` từ dữ liệu thông điệp MIME đã được serialize**, chẳng hạn nguồn `.eml` gồm header và body:

~~~text
From: reports@example.com
To: lan@example.net
Subject: Report
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Report is ready.
~~~

Ví dụ minh họa việc nạp message nguồn:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

// Giả định đã có JavaMailSender mailSender trong phạm vi sử dụng.
try (InputStream source = Files.newInputStream(Path.of("sample.eml"))) {
    MimeMessage parsed = mailSender.createMimeMessage(source);
    System.out.println(parsed.getContentType());
}
~~~

Đoạn ví dụ cần được đặt trong method có khai báo hoặc xử lý các ngoại lệ `IOException` và `MessagingException` phù hợp. Nó **không gửi email**. Việc gửi chỉ xảy ra nếu code tiếp tục gọi `mailSender.send(parsed)`.

Điểm khác biệt lớn: đối số `InputStream` ở đây là **toàn bộ dữ liệu email ở dạng MIME**, không phải chỉ bytes của một file PDF định đính kèm. Nếu muốn đính kèm PDF, phải tạo `MimeMessage` bình thường rồi sử dụng `MimeMessageHelper.addAttachment(...)` hoặc các API MIME tương ứng.

Khi nạp lại message có sẵn, cần quan tâm nguồn dữ liệu, header, quyền xử lý và tính toàn vẹn. Việc gửi lại một email cũ, nhất là thư ký số hoặc thông điệp có header vận chuyển đặc thù, có thể tạo vấn đề nghiệp vụ. Đây là năng lực parse/tạo message, không phải chức năng tự động forward email an toàn cho mọi tình huống.

## 9. Cấu hình JavaMailSender trong Spring Boot và Spring Framework thuần

### 9.1. Spring Boot: tự động cấu hình khi đáp ứng điều kiện

Trong Spring Boot thông dụng, dependency `spring-boot-starter-mail` và cấu hình gửi thư có thể tạo bean `JavaMailSender`. Ví dụ cấu hình SMTP submission:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: account-from-secure-configuration
    password: secret-from-secure-configuration
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Các giá trị `username`/`password` là chuỗi minh họa, không phải credentials thực tế. Trong môi trường triển khai, lấy thông tin xác thực qua biến môi trường/kho bí mật, đồng thời bảo đảm địa chỉ `From` được phép gửi.

Các thuộc tính có ý nghĩa:

- `host` và `port` chỉ ra endpoint SMTP. Cổng 587 thường dùng submission với STARTTLS.
- `mail.smtp.auth` bật SMTP authentication theo cơ chế nhà cung cấp hỗ trợ.
- `mail.smtp.starttls.enable` yêu cầu thử nâng cấp kết nối qua STARTTLS khi server công bố; `required` buộc TLS phải được thiết lập thành công.
- `connectiontimeout`, `timeout` và `writetimeout` tính bằng mili-giây, tránh để hoạt động I/O vô hạn khi server hoặc đường truyền có sự cố.

Nhà cung cấp dùng cổng 465 thường yêu cầu TLS ngay từ đầu kết nối (*implicit TLS*), khác với STARTTLS trên cổng 587. Không thay số cổng mà giữ nguyên giả định giao thức; hãy cấu hình theo tài liệu nhà cung cấp.

### 9.2. Spring Framework thuần: tự khai báo JavaMailSenderImpl

Khi không sử dụng Spring Boot auto-configuration, ta có thể tạo bean trực tiếp:

~~~java
package com.example.mailconfig;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.net");
        sender.setPort(587);
        sender.setUsername("account-from-secure-configuration");
        sender.setPassword("secret-from-secure-configuration");
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

Đoạn mã minh họa cách cấu hình. Trong dự án thật, các giá trị host, user, password phải được lấy từ cấu hình an toàn có thể quản trị theo môi trường thay vì ghi cố định trong source. `setDefaultEncoding("UTF-8")` ảnh hưởng encoding mặc định khi tạo `MimeMessage` bằng implementation này, nhưng từng template vẫn cần dùng encoding hợp lý và tương thích với quá trình dựng nội dung.

Không nên tạo một `JavaMailSenderImpl` mới mỗi lần gửi email. Bean Spring được cấu hình tập trung giúp dùng cùng chính sách máy chủ, timeout và transport. Ngược lại, **mỗi email cần `MimeMessage` riêng** để tránh trạng thái các recipient, header và body bị trộn giữa những lần gửi.

## 10. Tạo message và gửi là hai giai đoạn lỗi khác nhau

Với `JavaMailSender`, cần phân biệt các giai đoạn:

~~~mermaid
flowchart TD
    A["createMimeMessage"] --> B["Gán header và body / multipart"]
    B --> C{"Chuẩn bị MIME thành công?"}
    C -->|Không| D["Lỗi tạo message"]
    C -->|Có| E["JavaMailSender.send"]
    E --> F{"SMTP chấp nhận?"}
    F -->|Không| G["Lỗi kết nối, xác thực, sender, recipient hoặc data"]
    F -->|Có| H["Server đã tiếp nhận để xử lý"]
    H --> I["Chuyển phát về sau / báo cáo trạng thái riêng"]
~~~

Các lỗi khác nhau nên được xử lý ở vị trí phù hợp:

| Vị trí lỗi | Ví dụ | Thông tin nên ghi nhận |
| --- | --- | --- |
| Tạo `MimeMessage`/helper | Địa chỉ không hợp lệ, lỗi xây dựng multipart/attachment, `MessagingException` | ID yêu cầu, trường liên quan, nguyên nhân; tránh log toàn bộ dữ liệu nhạy cảm |
| Kết nối SMTP | DNS, timeout, server không sẵn sàng | Endpoint, thời điểm, loại timeout, khả năng retry |
| Xác thực/TLS | Credentials sai, TLS không được hỗ trợ theo chính sách | Loại lỗi bảo mật/cấu hình, không ghi secret |
| `MAIL FROM`/`RCPT TO` | Địa chỉ không được phép, recipient bị từ chối | Mã phản hồi và tập recipients bị ảnh hưởng |
| `DATA`/sau DATA | Thư vượt giới hạn, nội dung bị từ chối, mất kết nối | Phản hồi cuối hoặc trạng thái không chắc chắn |
| Sau server chấp nhận | Bounce, chính sách spam, trì hoãn chuyển phát | Theo dõi trạng thái qua tín hiệu từ provider hoặc DSN |

### 10.1. MessagingException và MailException

Các thao tác của Jakarta Mail như `MimeMessage#setSubject` hoặc `MimeMessageHelper#setText` có thể khai báo **`MessagingException`** (checked). Khi gọi `JavaMailSender.send(...)`, Spring chủ yếu biểu diễn lỗi gửi qua họ **`MailException`** (runtime), ví dụ:

- `MailAuthenticationException`: vấn đề xác thực với máy chủ.
- `MailSendException`: một hoặc nhiều thông điệp không được gửi thành công, tùy tình huống.
- `MailParseException`: lỗi parse/chuẩn bị message được báo qua abstraction mail.
- `MailPreparationException`: lỗi trong quá trình chuẩn bị thông điệp, ví dụ callback preparator.

Không nên chỉ bắt `MessagingException` quanh tất cả code rồi cho rằng đã xử lý mọi lỗi gửi SMTP. Ngược lại, chỉ bắt `MailException` cũng không thay thế việc xử lý lỗi checked khi xây dựng message thủ công.

### 10.2. Thành công ở send có phải delivered không?

`mailSender.send(message)` trả về bình thường thường có nghĩa thao tác submission đã được mail transport hoàn tất theo phản hồi mà nó nhận. Điều đó **không bảo đảm** email đã xuất hiện trong Inbox, không bị spam filtering hoặc đã được người nhận mở. Với SMTP, server có thể trả `250` sau `DATA` và tiếp tục chuyển tiếp về sau.

Đối với nghiệp vụ cần theo dõi, nên phân biệt:

1. `CREATED`: message đã được chuẩn bị trong ứng dụng.
2. `SUBMISSION_ACCEPTED`: provider/SMTP server đã chấp nhận xử lý.
3. `DELIVERED` hoặc `BOUNCED`: có bằng chứng trạng thái chuyển phát từ hệ thống có thẩm quyền.
4. `OPENED`: nếu có dữ liệu theo dõi hợp lệ, đây vẫn chỉ là tín hiệu phụ thuộc công nghệ/chính sách riêng, không suy ra chắc từ SMTP.

Tên trạng thái trên là ví dụ thiết kế nghiệp vụ, **không phải enum có sẵn trong `JavaMailSender`**.

### 10.3. Gửi nhiều MimeMessage không tự trở thành một giao dịch nguyên tử

Với:

~~~java
mailSender.send(messageOne, messageTwo, messageThree);
~~~

một hoặc nhiều message có thể đã được máy chủ chấp nhận trước khi lỗi xảy ra. Không thể dùng cơ chế rollback transaction của cơ sở dữ liệu để thu hồi email đã được SMTP tiếp nhận. Khi retry, cần biết message nào đã gửi thành công, và cần cân nhắc trường hợp mất kết nối khiến kết quả không chắc chắn.

Với email nghiệp vụ quan trọng, việc ghi yêu cầu gửi trong cơ sở dữ liệu/hàng đợi và xử lý bằng worker (ví dụ outbox) có thể giúp quản lý retry, theo dõi và giảm rủi ro mất yêu cầu. Đây là thiết kế ở tầng ứng dụng, không phải tính năng mặc định của `JavaMailSender`.

## 11. Kiểm tra MimeMessage trước khi gửi

Vì `createMimeMessage()` trả về một đối tượng có thể thao tác được, ta có thể **serialize** nó trong môi trường kiểm thử để quan sát cấu trúc MIME:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

// Ví dụ rút gọn; giả sử có JavaMailSender mailSender.
MimeMessage message = mailSender.createMimeMessage();
message.setFrom(new jakarta.mail.internet.InternetAddress(
        "reports@example.com"));
message.setRecipients(
        jakarta.mail.Message.RecipientType.TO,
        jakarta.mail.internet.InternetAddress.parse("lan@example.net"));
message.setSubject("Báo cáo", "UTF-8");
message.setText("Nội dung báo cáo", "UTF-8");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("message-sample.eml"))) {
    message.writeTo(output);
}

// Chỉ gửi khi nghiệp vụ chủ động yêu cầu:
// mailSender.send(message);
~~~

Ví dụ giả định code được đặt trong method xử lý/khai báo các ngoại lệ I/O và `MessagingException`. `saveChanges()` cập nhật các thay đổi cần thiết trước khi ghi ra dạng MIME; `writeTo(...)` serialize thành dữ liệu tương tự thư `.eml`. **Ghi ra file không đồng nghĩa gửi qua SMTP.**

Có thể quan sát:

- `From`, `To`, `Cc`, `Subject` và các MIME header;
- `Content-Type` ở root và từng part;
- `multipart/alternative`, `multipart/related`, `multipart/mixed`;
- `Content-ID` của ảnh inline và `cid:...` trong HTML;
- `Content-Disposition: attachment`, filename và charset.

Không nên commit hoặc chia sẻ file `.eml` thật chứa email riêng tư, token hay attachment nội bộ. Khi cần xem giao thức SMTP, protocol trace còn có thể chứa thông tin nhạy cảm, vì vậy chỉ bật debug có kiểm soát.

### 11.1. Một tình huống cần phân biệt MIME và SMTP

Ứng dụng gửi một email HTML; `JavaMailSender.send(...)` hoàn tất nhưng người nhận thấy nguyên dòng:

~~~text
<p>Xin chào <strong>Lan</strong></p>
~~~

Đây có thể là lỗi **Content-Type** của body (`text/plain` thay vì `text/html`), không phải lỗi SMTP. Kiểm tra lời gọi `helper.setText(html, true)` và dữ liệu MIME thực tế trước/sau gửi. Nếu bản MIME đúng nhưng client vẫn hiện sai, tiếp tục xem chính sách client và hệ thống trung gian.

Một tình huống khác: SMTP server từ chối `RCPT TO` với lỗi quyền relay. Khi đó việc sửa HTML hoặc chuyển multipart mode sẽ không giải quyết nguyên nhân; cần xem cấu hình tài khoản, domain sender/recipient và chính sách SMTP.

## 12. Những nhầm lẫn thường gặp

**“Tạo được MimeMessage nghĩa là đã kết nối SMTP?”**  
Không. `createMimeMessage()` tạo message để soạn; kết nối/transport xảy ra khi gửi hoặc khi thao tác kết nối rõ ràng được thực hiện.

**“JavaMailSender chỉ gửi plain text?”**  
Không. Nó có thể gửi `MimeMessage` chứa HTML, text alternative, inline resources và attachment. `SimpleMailMessage` mới là lớp đơn giản dành cho thư text.

**“Muốn email có HTML thì cần tự nối chuỗi boundary MIME?”**  
Không. `MimeMessageHelper` và Jakarta Mail xây dựng MIME structure; tự tạo boundary bằng chuỗi dễ sai encoding hoặc quan hệ giữa các part.

**“Dùng setText(html, true) là đã có cả bản text dự phòng?”**  
Không. Đây chỉ là body HTML. Muốn plain và HTML cùng tồn tại trong `multipart/alternative`, dùng overload `setText(plainText, htmlText)` với helper multipart thích hợp.

**“Đính kèm file tức là dùng createMimeMessage(InputStream)?”**  
Không. Overload này đọc **một thông điệp MIME có sẵn**. Tệp riêng lẻ được thêm thông qua API MIME, thường là `MimeMessageHelper.addAttachment(...)`.

**“Header From và SMTP MAIL FROM luôn giống nhau?”**  
Không nhất thiết. Header `From:` là thành phần của `MimeMessage`; SMTP envelope sender có thể được mail transport xác định theo message/cấu hình và có thể khác header gửi hiển thị, ví dụ khi dùng địa chỉ bounce riêng.

**“send trả về bình thường nghĩa là người nhận đã đọc?”**  
Không. Thư có thể chỉ vừa được SMTP server chấp nhận để xử lý; chuyển phát và trạng thái đọc là các bước khác.

**“Dùng MimeMessagePreparator là tự động gửi nền, có retry?”**  
Không. Callback chuẩn bị nội dung ngay trong luồng của lời gọi gửi; quản lý queue, async và retry cần được thiết kế độc lập.

## 13. Ví dụ tình huống từ nghiệp vụ tới email hoàn chỉnh

Giả sử hệ thống quản lý dự án gửi báo cáo tuần. Tầng nghiệp vụ có mã báo cáo, người nhận được xác thực, file PDF và một template HTML. Một triển khai có thể chia trách nhiệm như sau:

~~~text
ReportService
  ├── Kiểm tra quyền nhận báo cáo
  ├── Tạo dữ liệu nội dung (plain text / HTML)
  ├── Lấy PDF và logo từ nguồn được phép
  └── Gọi WeeklyReportMailer
        ├── javaMailSender.createMimeMessage()
        ├── new MimeMessageHelper(... MIXED_RELATED ...)
        ├── setFrom / setTo / setSubject
        ├── setText(plain, html)
        ├── addInline(logo)
        ├── addAttachment(report.pdf)
        └── javaMailSender.send(message)
              └── Jakarta Mail SMTP transport
                    └── SMTP server tiếp nhận thư
~~~

Thiết kế này làm rõ:

- **Service nghiệp vụ** quyết định *ai được nhận* và *nội dung nào được phép gửi*.
- **`JavaMailSender`** cấp message và kích hoạt thao tác gửi.
- **`MimeMessage`** là biểu diễn email có thể quan sát, serialize và bổ sung MIME parts.
- **`MimeMessageHelper`** giúp xây dựng email đúng dạng mà không tự xử lý boundary/encoding.
- **Jakarta Mail và SMTP provider** xử lý giao thức, xác thực và bước tiếp nhận/chuyển phát.

Hiểu rõ hai thao tác **tạo `MimeMessage`** và **gửi `MimeMessage`** giúp ứng dụng kiểm soát nội dung, kiểm tra cấu trúc, xử lý lỗi ở đúng giai đoạn và mở rộng từ text đơn giản sang HTML, ảnh inline hoặc attachment. Đó là vai trò trung tâm của `JavaMailSender` trong API Java Mail của Spring Framework.
