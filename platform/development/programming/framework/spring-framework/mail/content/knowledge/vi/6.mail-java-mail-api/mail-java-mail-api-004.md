# MimeMessagePreparator để chuẩn bị message

## 1. MimeMessagePreparator là gì?

Trong **Spring Framework Mail**, **MimeMessagePreparator** là một **functional interface** thuộc package **org.springframework.mail.javamail**. Nó mô tả công việc **chuẩn bị nội dung của một MimeMessage** do tầng gửi mail cung cấp. Ứng dụng triển khai interface này để điền người gửi, người nhận, tiêu đề, nội dung văn bản, HTML, attachment hoặc các thành phần MIME khác, rồi chuyển callback cho **JavaMailSender.send(...)**.

Khái niệm cốt lõi:

> **MimeMessagePreparator quyết định cách dựng thư; JavaMailSender quyết định thời điểm tạo thông điệp và thực hiện thao tác gửi.**

Thay vì viết trực tiếp toàn bộ thao tác **createMimeMessage() → chỉnh sửa MimeMessage → send(mimeMessage)**, ứng dụng có thể cung cấp một callback **prepare(MimeMessage)** cho JavaMailSender:

~~~java
MimeMessagePreparator preparator = mimeMessage -> {
    // Chuẩn bị các trường và cấu trúc MIME ở đây.
};

mailSender.send(preparator);
~~~

Đây là một trong các API hữu ích khi nội dung email phức tạp, có thể tái sử dụng logic dựng thư, hoặc cần tách **khâu chuẩn bị** khỏi **khâu gửi** trong thiết kế ứng dụng.

### Chữ ký interface

Về mặt ý nghĩa, hợp đồng của interface tương đương:

~~~java
package org.springframework.mail.javamail;

@FunctionalInterface
public interface MimeMessagePreparator {
    void prepare(jakarta.mail.internet.MimeMessage mimeMessage) throws Exception;
}
~~~

Đoạn trên trình bày **chữ ký để học**, không phải mã cần khai báo lại trong ứng dụng. Ở Spring Framework 6 và các ứng dụng Spring Boot 3+, kiểu thông điệp MIME thuộc **jakarta.mail.internet**. Khi sử dụng Spring Framework 5 hoặc Spring Boot 2, các API mail ở nền thường dùng namespace **javax.mail**; cần thống nhất dependency và import theo phiên bản framework trong dự án.

Interface chỉ có một phương thức trừu tượng nên có thể triển khai bằng **lambda**, **anonymous class** hoặc một lớp riêng.

## 2. MimeMessagePreparator nằm ở đâu trong Spring Mail?

Các thành phần liên quan cần phân biệt:

| Thành phần | Nhiệm vụ | Có tự gửi email không? |
|---|---|---|
| **MimeMessagePreparator** | Callback tùy biến đối tượng **MimeMessage** đã được cấp | **Không** |
| **MimeMessage** | Thông điệp MIME thực tế của Jakarta Mail, chứa header và body | **Không** |
| **MimeMessageHelper** | Tiện ích xây dựng header, body HTML/plain text, attachment, inline resource | **Không** |
| **JavaMailSender** | Hợp đồng Spring cho tạo và gửi thông điệp MIME | **Có**, qua các overload **send(...)** |
| **JavaMailSenderImpl** | Triển khai phổ biến sử dụng Jakarta Mail và SMTP | **Có**, khi được cấu hình phù hợp |
| **SimpleMailMessage** | Đối tượng dữ liệu cho email văn bản thuần | **Không** |

Không nhầm **MimeMessagePreparator** với **MimeMessageHelper**. Preparator là **hợp đồng callback**, còn Helper là **công cụ thao tác trên thông điệp** bên trong callback.

Sơ đồ dòng lệnh điển hình:

~~~text
          Application / NotificationService
                        |
                        | Tạo MimeMessagePreparator
                        v
               JavaMailSender.send(...)
                        |
                        | Tạo MimeMessage
                        v
           MimeMessagePreparator.prepare(...)
                        |
                        | Dùng MimeMessageHelper thiết lập nội dung
                        v
                  MimeMessage đã chuẩn bị
                        |
                        | JavaMailSenderImpl + Jakarta Mail
                        v
                     SMTP server
                        |
                        v
              Hệ thống chuyển phát email
~~~

Một lời gọi **prepare(...)** không xác nhận thư đã được gửi. Kể cả khi **send(...)** hoàn tất thành công, điều đó cũng không bảo đảm thư đã vào Inbox của người nhận; các chặng SMTP và hệ thống mail đích có thể tiếp tục xử lý sau đó.

## 3. Vì sao dùng callback thay vì tự tạo MimeMessage?

Để hiểu lợi ích, hãy xem hai cách tổ chức cùng một thao tác.

**Cách A — tạo trực tiếp và gửi:**

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setTo("user@example.net");
helper.setFrom("no-reply@example.com");
helper.setSubject("Thông báo");
helper.setText("Nội dung thư");
mailSender.send(message);
~~~

**Cách B — giao callback cho JavaMailSender:**

~~~java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setTo("user@example.net");
    helper.setFrom("no-reply@example.com");
    helper.setSubject("Thông báo");
    helper.setText("Nội dung thư");
};

mailSender.send(preparator);
~~~

Hai cách đều hợp lệ, tùy yêu cầu. **Cách A** dễ theo dõi khi ứng dụng cần giữ một đối tượng MimeMessage để cấu hình thủ công. **Cách B** tập trung logic dựng thư vào một callback và để JavaMailSender điều phối vòng đời thông điệp. Với các use case có template HTML, attachment hoặc nhiều loại thông báo, callback có thể trở thành một đơn vị logic riêng dễ truyền vào tầng gửi.

Lợi ích đáng chú ý:

- **Tập trung khâu chuẩn bị**: thông tin người nhận, header và body được mô tả ở một nơi.
- **Tách trách nhiệm**: lớp xây dựng nội dung không cần quản lý kết nối SMTP.
- **Dễ kết hợp với Spring DI**: service phụ thuộc vào interface JavaMailSender và các dịch vụ dựng template.
- **Tái sử dụng**: một hàm hoặc lớp có thể tạo preparator từ dữ liệu nghiệp vụ và trả về callback cho tầng gửi.
- **Mỗi lần gửi có đối tượng MIME do sender cấp**: tránh vô tình dùng một MimeMessage cũ đã bị thay đổi ở lần gửi trước.

Preparator **không** tự động tạo hàng đợi, retry, transaction hay khả năng gửi bất đồng bộ. Đây chỉ là API chuẩn bị nội dung trong quá trình gửi email.

## 4. Ví dụ cơ bản: gửi email plain text bằng MimeMessagePreparator

Đối với email rất đơn giản, **SimpleMailMessage** là lựa chọn gọn hơn. Tuy nhiên, ví dụ sau giúp thấy cách callback vận hành, trước khi chuyển sang HTML hoặc attachment.

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class WelcomeEmailService {

    private final JavaMailSender mailSender;

    public WelcomeEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("no-reply@example.com");
            helper.setTo(recipient);
            helper.setSubject("Chào mừng bạn");
            helper.setText("Tài khoản của bạn đã được tạo thành công.");
        };

        mailSender.send(preparator);
    }
}
~~~

Ở đây:

1. **WelcomeEmailService** nhận **JavaMailSender** qua constructor injection.
2. Lambda nhận **MimeMessage** do JavaMailSender cung cấp và sử dụng **MimeMessageHelper** để thiết lập các trường.
3. **helper.setText(String)** tạo phần body plain text.
4. **mailSender.send(preparator)** kích hoạt quy trình chuẩn bị và gửi.

Địa chỉ và nội dung trong ví dụ phục vụ minh họa; ứng dụng cần SMTP server, quyền gửi và địa chỉ người gửi đã được cấu hình phù hợp.

### Tại sao lambda không khai báo throws MessagingException?

Phương thức **prepare(...)** của MimeMessagePreparator được khai báo **throws Exception**. Vì vậy callback có thể gọi các API Jakarta Mail hoặc MimeMessageHelper có checked exception mà không phải tự bọc bằng RuntimeException trong từng lệnh. Khi JavaMailSender thực thi callback, lỗi từ bước chuẩn bị hoặc bước gửi được đưa ra cho ứng dụng qua cơ chế ngoại lệ của Spring Mail.

Tuy nhiên, **lỗi cấu trúc email** vẫn khác với **lỗi giao thông SMTP**. Phải xem loại exception và nguyên nhân bên trong trước khi quyết định sửa dữ liệu hay thử gửi lại.

## 5. Ví dụ quan trọng: dựng email HTML và plain text thay thế

Một thông báo nghiệp vụ thường muốn người nhận xem được cả email HTML và bản plain text tương đương. **MimeMessagePreparator** kết hợp thuận tiện với **MimeMessageHelper** để tạo các phần MIME này.

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class AccountEmailService {

    private final JavaMailSender mailSender;

    public AccountEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAccountReady(String recipient, String displayName) {
        String safeName = escapeHtml(displayName);

        String plainText = """
                Xin chào %s,

                Tài khoản của bạn đã sẵn sàng.
                Truy cập https://example.com/account để xem thông tin.
                """.formatted(displayName);

        String htmlText = """
                <html lang="vi">
                  <body>
                    <h2>Xin chào %s!</h2>
                    <p>Tài khoản của bạn đã sẵn sàng.</p>
                    <p><a href="https://example.com/account">
                      Truy cập trang tài khoản
                    </a></p>
                  </body>
                </html>
                """.formatted(safeName);

        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    true,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("no-reply@example.com");
            helper.setTo(recipient);
            helper.setSubject("Tài khoản đã sẵn sàng");
            helper.setText(plainText, htmlText);
        };

        mailSender.send(preparator);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
~~~

Ví dụ sử dụng **Java text block** và **String.formatted(...)**, phù hợp với Java 21. Hàm escapeHtml ở đây chỉ minh họa yêu cầu escape một chuỗi văn bản khi chèn vào *text node* HTML; trong ứng dụng thực tế nên sử dụng template engine có cơ chế escaping theo ngữ cảnh. Không sử dụng kiểu escape này để tự bảo vệ giá trị nhúng tùy ý vào URL, JavaScript hoặc CSS.

Các điểm chính:

- **MimeMessageHelper(mimeMessage, true, "UTF-8")** bật chế độ multipart và thiết lập encoding.
- **setText(plainText, htmlText)** tạo hai biểu diễn thay thế của cùng nội dung, thường nằm trong **multipart/alternative**.
- Hai bản phải nhất quán về nội dung và hành động cần thực hiện; bản text cần có URL đọc được nếu HTML dùng nút bấm.
- **MimeMessagePreparator** chỉ thiết lập nội dung, còn **JavaMailSender** quản lý lời gọi gửi.

Nếu chỉ truyền **setText(htmlText, true)** thì helper đánh dấu một phần nội dung là HTML; phương thức đó không tự tạo bản text tương đương.

## 6. Chuẩn bị email có attachment

MIME cho phép email chứa một hoặc nhiều tệp đính kèm. Helper hỗ trợ các phương thức như **addAttachment(...)** bên trong callback, miễn là đã bật chế độ multipart.

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, File invoicePdf) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("billing@example.com");
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn của bạn");
            helper.setText(
                    "Hóa đơn PDF được đính kèm.",
                    "<p>Hóa đơn PDF được đính kèm.</p>"
            );
            helper.addAttachment("invoice.pdf", invoicePdf);
        };

        mailSender.send(preparator);
    }
}
~~~

Ý nghĩa của **MULTIPART_MODE_MIXED_RELATED** là Spring dựng cây multipart phù hợp cho việc kết hợp các phần nội dung với attachment và tài nguyên inline. Cấu trúc MIME thực tế có thể có các lớp **multipart/mixed**, **multipart/related** và **multipart/alternative** lồng nhau, vì các kiểu này biểu diễn những quan hệ khác nhau:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   └── multipart/alternative
    │       ├── text/plain
    │       └── text/html
    └── application/pdf (attachment)
~~~

Sơ đồ là ví dụ về **quan hệ logic** giữa các phần, không phải cam kết mọi mail client hay phiên bản Jakarta Mail sẽ tạo chính xác từng node theo cùng cấu trúc.

Một số nguyên tắc khi thêm attachment:

1. Chỉ cho phép tệp thuộc phạm vi nghiệp vụ và đã được kiểm soát quyền truy cập.
2. Giới hạn dung lượng; nhiều nhà cung cấp SMTP có hạn mức kích thước thông điệp.
3. Không dùng tên file do người dùng nhập trực tiếp làm đường dẫn tùy ý.
4. Đảm bảo dữ liệu attachment còn đọc được **khi callback được thực thi và thư được gửi**.
5. Tránh lưu tệp mật hoặc dữ liệu nhạy cảm vào log khi bắt lỗi.

Nếu nội dung đính kèm được tạo tạm thời và đóng/xóa quá sớm, quá trình dựng hoặc gửi MIME có thể thất bại dù ứng dụng đã xây được preparator.

## 7. Hình ảnh inline và nội dung HTML

Khác với file đính kèm tải xuống, hình ảnh inline thường được HTML tham chiếu qua **Content-ID** với cú pháp **cid:**.

Ví dụ ý tưởng:

~~~java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
    );

    helper.setFrom("brand@example.com");
    helper.setTo("recipient@example.net");
    helper.setSubject("Thông báo");
    helper.setText(
            "Thương hiệu gửi thông báo mới.",
            "<p>Thông báo mới</p><img src=\"cid:brandLogo\" alt=\"Logo\">"
    );

    helper.addInline("brandLogo", logoResource);
};

mailSender.send(preparator);
~~~

Đoạn mã giả định **logoResource** là một **org.springframework.core.io.Resource** đã được chuẩn bị sẵn. Khi sử dụng **MimeMessageHelper**, nên **đặt nội dung bằng setText(...) trước rồi mới gọi addInline(...)** để tăng khả năng tương thích với các email client.

Hình inline là một **thành phần liên quan của HTML** (quan hệ *related*), không phải một phiên bản alternative thứ ba của phần thân. Dù có ảnh, email vẫn nên truyền tải được nội dung quan trọng nếu client chặn hiển thị hình ảnh.

## 8. Chuẩn bị message bằng lambda, anonymous class hoặc lớp riêng

Vì MimeMessagePreparator chỉ có một phương thức trừu tượng, cú pháp lambda thường gọn nhất:

~~~java
MimeMessagePreparator preparator = mimeMessage -> {
    MimeMessageHelper helper = new MimeMessageHelper(mimeMessage, "UTF-8");
    helper.setTo("user@example.net");
    helper.setFrom("sender@example.com");
    helper.setSubject("Nhắc lịch");
    helper.setText("Cuộc hẹn sẽ bắt đầu vào ngày mai.");
};
~~~

Nếu cần một thành phần có cấu hình hoặc nhiều thao tác phức tạp, có thể định nghĩa lớp riêng:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class ReminderPreparator implements MimeMessagePreparator {

    private final String recipient;
    private final String content;

    public ReminderPreparator(String recipient, String content) {
        this.recipient = recipient;
        this.content = content;
    }

    @Override
    public void prepare(MimeMessage mimeMessage) throws Exception {
        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage, "UTF-8"
        );
        helper.setFrom("reminders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Nhắc lịch");
        helper.setText(content);
    }
}
~~~

Lúc gửi:

~~~java
mailSender.send(
        new ReminderPreparator(
                "recipient@example.net",
                "Lịch hẹn của bạn sẽ bắt đầu vào ngày mai."
        )
);
~~~

Điều này hữu ích khi ứng dụng có nhiều loại thông báo nhưng muốn giữ phần dựng thông điệp trong những lớp chuyên biệt. Tuy nhiên, với callback chỉ vài dòng, việc tạo thêm một class có thể khiến luồng đọc khó theo dõi hơn; chọn hình thức phù hợp với độ phức tạp.

## 9. Tách việc tạo preparator khỏi việc gọi send()

Một cách tổ chức thường gặp là tách **dữ liệu thông báo**, **builder tạo preparator** và **adapter gửi thư**:

~~~text
Controller / Domain Service
        |
        v
Notification command (recipient, template data)
        |
        v
EmailPreparatorFactory
        |   Tạo callback dựa trên dữ liệu đầu vào
        v
MimeMessagePreparator
        |
        v
JavaMailSender.send(preparator)
        |
        v
SMTP / Email provider
~~~

Ví dụ một factory trả về callback:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class AlertMailFactory {

    private AlertMailFactory() {
    }

    public static MimeMessagePreparator create(
            String recipient,
            String subject,
            String body
    ) {
        return mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage, "UTF-8"
            );
            helper.setFrom("alerts@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body);
        };
    }
}
~~~

Ở service:

~~~java
MimeMessagePreparator preparator = AlertMailFactory.create(
        "operator@example.net",
        "Cảnh báo hệ thống",
        "Một tác vụ cần được kiểm tra."
);

mailSender.send(preparator);
~~~

Chú ý callback có thể **được tạo trước lúc thực thi**. Vì vậy nên truyền dữ liệu bất biến hoặc snapshot của dữ liệu cần gửi; tránh tham chiếu tới biến/đối tượng mutable mà luồng khác có thể thay đổi giữa lúc tạo callback và lúc sender gọi **prepare()**. Callback cũng nên hạn chế side effect như thay đổi trạng thái đơn hàng hoặc ghi dữ liệu nghiệp vụ, vì trách nhiệm chính của nó là chuẩn bị email.

## 10. Kết hợp template engine để soạn nội dung

Nội dung email thực tế thường không phải chuỗi HTML cố định. Ứng dụng có thể dùng **Thymeleaf**, **FreeMarker** hoặc một template engine khác để tạo HTML và plain text trước khi nộp thông điệp.

Ví dụ luồng xử lý:

~~~text
Thông tin giao dịch
      |
      v
Service lấy dữ liệu đã được phép dùng
      |
      +--> Template plain text --> plainText
      |
      +--> Template HTML ------> htmlText
      |
      v
MimeMessagePreparator
      | helper.setText(plainText, htmlText)
      v
JavaMailSender.send(...)
~~~

Nên xây dựng nội dung từ **một nguồn dữ liệu nghiệp vụ nhất quán** để tránh HTML và text có số tiền, mã đơn hàng hoặc hạn sử dụng khác nhau. Nếu thông điệp có link xác nhận, bản text nên có URL có thể sao chép; HTML có thể dùng nút bấm hoặc liên kết có nhãn.

Khi đưa dữ liệu người dùng vào HTML, dùng khả năng **escape theo ngữ cảnh** của template engine. Tránh nối thẳng tên hiển thị, nội dung ghi chú hoặc URL chưa được kiểm soát vào HTML; email client có cách diễn giải HTML khác nhau và có thể xử lý một số thẻ không mong muốn.

Không nhất thiết phải render HTML **bên trong callback**. Có thể render trước và để callback chỉ gắn các chuỗi vào MimeMessage. Cách đó giữ callback đơn giản và tách rõ lỗi render template khỏi lỗi gửi. Ngược lại, nếu render trong callback, exception từ template sẽ là một lỗi chuẩn bị message; cần nhận diện và xử lý tương ứng.

## 11. Một lần gửi nhiều preparator

**JavaMailSender** hỗ trợ các phương thức **send(...)** nhận một preparator hoặc một mảng các preparator.

Ví dụ:

~~~java
MimeMessagePreparator first = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom("alerts@example.com");
    helper.setTo("first@example.net");
    helper.setSubject("Thông báo riêng");
    helper.setText("Nội dung dành cho người nhận thứ nhất.");
};

MimeMessagePreparator second = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom("alerts@example.com");
    helper.setTo("second@example.net");
    helper.setSubject("Thông báo riêng");
    helper.setText("Nội dung dành cho người nhận thứ hai.");
};

mailSender.send(first, second);
~~~

Mỗi preparator biểu diễn **một thông điệp email riêng cần được chuẩn bị**. Không nhầm thao tác gửi nhiều preparator với một thư có nhiều địa chỉ To/Cc/Bcc: đó là hai mô hình khác nhau.

Quan trọng: **send(first, second)** không phải transaction nguyên tử xuyên qua các message. Một message có thể được hệ thống gửi chấp nhận trong khi message khác thất bại. Khi cần báo cáo trạng thái theo người nhận hoặc xử lý retry, hãy lưu dấu vết của từng thông điệp và đối chiếu với phản hồi từ hạ tầng gửi.

## 12. Xử lý exception: lỗi chuẩn bị khác lỗi vận chuyển

Khi dùng callback, có hai nơi có thể phát sinh lỗi:

**Nhóm 1 — Lỗi chuẩn bị (preparation)**

- Địa chỉ email hoặc dữ liệu đầu vào không hợp lệ.
- Lỗi truy xuất template hoặc dữ liệu.
- Không đọc được tệp đính kèm khi dựng nội dung.
- Sai cấu trúc MIME, encoding hoặc thao tác trên MimeMessage.
- Callback ném exception trong lúc chạy.

**Nhóm 2 — Lỗi gửi/vận chuyển (transport)**

- SMTP host, cổng hoặc DNS không đúng.
- Kết nối timeout, handshake TLS thất bại.
- SMTP AUTH thất bại.
- SMTP relay từ chối sender, recipient hoặc dữ liệu.
- Server quá tải, giới hạn tốc độ hoặc vấn đề mạng sau khi nộp thư.

Trong Spring Mail, các lỗi có thể xuất hiện dưới những ngoại lệ thuộc họ **MailException**, chẳng hạn:

| Ngoại lệ | Ý nghĩa thường gặp |
|---|---|
| **MailPreparationException** | Exception khi thực thi callback chuẩn bị thông điệp. |
| **MailParseException** | Không thể diễn giải hoặc dựng một thông điệp hợp lệ. |
| **MailAuthenticationException** | Không xác thực được với mail server. |
| **MailSendException** | Lỗi khi gửi thông điệp, có thể chứa thông tin chi tiết theo từng message. |

Không giả định mọi **MessagingException** đều được Spring bọc theo cùng một loại ở mọi tình huống. Cần đọc **cause** và thông điệp lỗi thực tế để biết exception xuất phát từ chuẩn bị thư hay quá trình giao tiếp SMTP.

Ví dụ service ghi nhận lỗi tại tầng điều phối:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class MailDispatchService {

    private final JavaMailSender sender;

    public MailDispatchService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void dispatch(MimeMessagePreparator preparator) {
        try {
            sender.send(preparator);
        } catch (MailPreparationException ex) {
            // Kiểm tra dữ liệu và cách dựng nội dung.
            throw ex;
        } catch (MailAuthenticationException ex) {
            // Kiểm tra tài khoản và quyền sử dụng SMTP.
            throw ex;
        } catch (MailException ex) {
            // Ghi nhận thông tin chẩn đoán an toàn và phân loại thêm.
            throw ex;
        }
    }
}
~~~

Đoạn mã phân biệt loại lỗi, chưa cài chính sách retry. Cần tránh ghi mật khẩu SMTP, token, nội dung thư hoặc các đường dẫn bí mật ra log.

### Trường hợp lỗi không rõ đã gửi hay chưa

Nếu kết nối mất ngay sau khi client gửi dữ liệu mà chưa nhận được xác nhận của SMTP server, có thể **server đã nhận thư nhưng client vẫn quan sát thấy timeout**. Retry tự động mà không theo dõi thông điệp có nguy cơ tạo email trùng.

Khi email là chức năng quan trọng, nên theo dõi **notification ID**, **attempt ID**, trạng thái tạm thời/vĩnh viễn và tình huống **UNKNOWN**; đồng thời đối soát với log của nhà cung cấp nếu có. **MimeMessagePreparator không tự cung cấp exactly-once delivery**.

## 13. Đồng bộ, bất đồng bộ và transaction

Gọi **mailSender.send(preparator)** theo cách thông thường là thao tác **đồng bộ**: caller chờ tới khi quy trình chuẩn bị và nộp email hoàn tất hoặc ném exception. Callback không biến thao tác này thành bất đồng bộ.

Nếu giao diện người dùng cần phản hồi nhanh hoặc cần cơ chế retry độc lập với HTTP request, ứng dụng có thể lưu một yêu cầu gửi thư và để background worker thực hiện:

~~~text
HTTP request
     |
     v
Lưu dữ liệu nghiệp vụ + yêu cầu gửi trong outbox
     |
   COMMIT
     |
     v
Background worker
     |
     +--> Dựng MimeMessagePreparator từ dữ liệu đã lưu
     |
     +--> JavaMailSender.send(preparator)
     |
     +--> Ghi nhận accepted / failed / unknown
~~~

Nếu dữ liệu nghiệp vụ và ý định gửi email cần commit nhất quán, mô hình **transactional outbox** có thể hữu ích: lưu bản ghi nghiệp vụ và outbox trong cùng transaction database, sau đó worker đọc outbox và gửi. Tuy nhiên, SMTP không tham gia transaction database: nếu worker gửi thành công rồi chết trước khi cập nhật trạng thái outbox, việc chạy lại có thể gửi trùng. Cần thiết kế retry và chống xử lý trùng theo khả năng của hệ thống.

Không nên đưa các đối tượng MimeMessage, MimeMessageHelper hoặc lambda có tham chiếu tới tài nguyên sống (connection, stream tạm) trực tiếp vào queue lưu trữ lâu dài. Thay vào đó, **lưu dữ liệu nghiệp vụ có thể serialize** rồi dựng callback lúc worker xử lý.

## 14. Kiểm thử thành phần dùng MimeMessagePreparator

Vì callback là một thành phần thuần chuẩn bị thông điệp, có thể kiểm tra logic xây dựng MIME mà không phải gửi email thật. Ví dụ, dùng một JavaMailSender giả hoặc mock để lấy preparator rồi gọi **prepare(...)** lên một MimeMessage thử nghiệm do Jakarta Mail tạo.

Ý tưởng minh họa với Mockito:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

import java.util.Properties;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class WelcomeEmailServiceTest {

    @Test
    void preparesAddressAndSubject() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        WelcomeEmailService service = new WelcomeEmailService(sender);

        service.sendWelcome("recipient@example.net");

        org.mockito.ArgumentCaptor<MimeMessagePreparator> captured =
                org.mockito.ArgumentCaptor.forClass(
                        MimeMessagePreparator.class
                );
        verify(sender).send(captured.capture());

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );
        captured.getValue().prepare(message);

        org.junit.jupiter.api.Assertions.assertEquals(
                "Chào mừng bạn", message.getSubject()
        );
        org.junit.jupiter.api.Assertions.assertEquals(
                "recipient@example.net",
                message.getRecipients(jakarta.mail.Message.RecipientType.TO)[0].toString()
        );
    }
}
~~~

Ví dụ giả định môi trường kiểm thử đã có JUnit 5, Mockito và Jakarta Mail. Nó minh họa cách **quan sát callback và đối tượng MIME sau khi prepare**, không gọi SMTP. Với HTML, attachment hoặc header phức tạp, có thể kiểm tra nội dung các **BodyPart** và kiểu MIME tương ứng. Kiểm thử kết nối SMTP vẫn là một phạm vi riêng, thường cần một mail server giả lập hoặc hạ tầng thử nghiệm.

Mục tiêu là xác nhận **cấu trúc và dữ liệu thông điệp**, không đánh đồng việc MIME đúng với bảo đảm thư sẽ được chuyển phát thành công qua Internet.

## 15. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao dễ gây vấn đề | Hướng xử lý |
|---|---|---|
| Gọi **prepare(...)** nhưng không gọi **send(...)** | Callback chỉ dựng thư, không thực hiện gửi | Truyền preparator cho JavaMailSender.send(...). |
| Tạo lambda nhưng phụ thuộc vào đối tượng mutable bên ngoài | Dữ liệu có thể thay đổi trước khi callback chạy | Capture dữ liệu bất biến hoặc snapshot đã kiểm tra. |
| Tạo MimeMessage một lần rồi tái sử dụng giữa nhiều lần gửi | Dễ mang theo header/body cũ, thay đổi ngoài ý muốn | Dùng đối tượng mới cho từng thông điệp hoặc để sender tạo qua preparator. |
| Chỉ tạo HTML, không có plain text | Người chọn chế độ text có thể khó đọc hoặc thiếu thông tin | Dùng setText(plainText, htmlText) khi cần alternative. |
| Thêm attachment khi helper không ở chế độ multipart | Không có cây multipart phù hợp | Khởi tạo MimeMessageHelper với multipart=true hoặc mode phù hợp. |
| Gọi addInline trước setText | Có thể ảnh hưởng khả năng hiển thị trên một số email client | Thiết lập body trước, rồi thêm inline resource. |
| Render nội dung từ dữ liệu không escape | Có thể làm hỏng HTML và gây rủi ro chèn nội dung | Dùng template engine có escaping theo ngữ cảnh. |
| Coi MailPreparationException như lỗi mạng | Retry lặp lại một thông điệp sai | Sửa nguồn dữ liệu hoặc cấu trúc trước khi gửi lại. |
| Coi send() thành công là đã vào Inbox | SMTP chỉ xác nhận một chặng của quá trình phát | Theo dõi event, bounce và trạng thái từ ESP nếu cần. |
| Đưa lambda capture file tạm vào queue rồi xử lý rất muộn | File có thể đã bị xóa hoặc stream đóng | Lưu dữ liệu bền vững và tạo preparator tại thời điểm worker gửi. |
| Gửi email ngay bên trong transaction nghiệp vụ quan trọng | Database có thể rollback sau khi thư đã gửi | Xem xét outbox và worker cho yêu cầu cần độ tin cậy cao. |

## 16. Khi nào nên chọn MimeMessagePreparator?

**Chọn MimeMessagePreparator khi:**

- Cần dựng MIME bằng callback rõ ràng, giữ cho service gửi thư chỉ nhận yêu cầu chuẩn bị.
- Email có HTML, attachment, inline image, nhiều header hoặc các cấu hình MIME tùy biến.
- Muốn tái sử dụng logic tạo email cho nhiều lời gọi gửi.
- Muốn tách phần xây thông điệp khỏi cấu hình SMTP và cơ chế gọi send.
- Muốn kiểm tra riêng nội dung MimeMessage bằng cách thực thi callback trên message thử nghiệm.

**Một số trường hợp có lựa chọn gọn hơn:**

- Email chỉ có subject và plain text: **SimpleMailMessage** + **MailSender** đủ đáp ứng.
- Ứng dụng cần trực tiếp thao tác một đối tượng MimeMessage đã có: dùng **JavaMailSender.createMimeMessage()**, **MimeMessageHelper**, sau đó **send(message)**.
- Dự án đã có notification gateway riêng: có thể để gateway tạo/nhận preparator bên trong adapter, còn nghiệp vụ chỉ biết gửi thông báo.

Việc chọn callback không làm thay đổi khả năng gửi cốt lõi của Spring Mail; khác biệt chủ yếu nằm ở **cách tổ chức bước chuẩn bị message**.

## 17. Tổng kết

**MimeMessagePreparator** là functional interface trong **Spring Framework Mail** với phương thức **prepare(MimeMessage)**. Nó cho phép ứng dụng mô tả cách xây dựng email, thường sử dụng **MimeMessageHelper** để thiết lập From, To, Cc, Bcc, Subject, plain text, HTML, attachment hoặc inline resource. Khi truyền preparator vào **JavaMailSender.send(...)**, sender tạo thông điệp, thực thi callback chuẩn bị, rồi chuyển thông điệp sang hệ thống gửi thư.

Cần nhớ ba ranh giới: **preparator chỉ chuẩn bị nội dung**; **sender thực hiện lời gọi gửi**; còn **SMTP và hệ thống nhận chịu trách nhiệm chuyển phát qua các chặng tiếp theo**. Tách rõ ba vai trò này giúp mã ứng dụng dễ đọc, dễ tổ chức, dễ kiểm soát lỗi và phù hợp hơn với những quy trình email phức tạp.
