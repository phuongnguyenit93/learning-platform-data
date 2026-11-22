# Các thành phần sẽ gặp trong một module gửi mail

Trong ứng dụng Java, chức năng gửi email thường xuất hiện ở những nghiệp vụ như xác nhận đăng ký, khôi phục mật khẩu, thông báo đơn hàng hoặc gửi báo cáo. Với **Spring Framework Mail**, ta có thể xây dựng chức năng này bằng một tập hợp thành phần có trách nhiệm rõ ràng: nhận yêu cầu từ nghiệp vụ, tạo nội dung thư, dựng thông điệp email, kết nối máy chủ gửi thư và xử lý kết quả.

Bài học này giới thiệu **bản đồ các thành phần** thường gặp trong một module gửi mail. Mục tiêu là hiểu mỗi thành phần làm gì, chúng phối hợp với nhau như thế nào, thành phần nào do Spring cung cấp và thành phần nào do ứng dụng tự xây dựng. Một module nhỏ không nhất thiết phải có đủ mọi lớp được liệt kê; kiến trúc nên tăng dần theo yêu cầu thực tế.

## 1. Module gửi mail thực sự làm những việc gì?

Một hành động “gửi email” gồm nhiều công đoạn khác nhau:

1. **Phát sinh yêu cầu:** nghiệp vụ quyết định cần thông báo cho ai và vì lý do gì.
2. **Chuẩn bị dữ liệu:** lấy địa chỉ người nhận, tiêu đề, dữ liệu để điền vào mẫu thư và các tài liệu đính kèm nếu có.
3. **Soạn thông điệp:** chọn thư văn bản thuần, HTML hoặc thư nhiều phần (MIME).
4. **Chuyển thư:** sử dụng thư viện mail để giao thông điệp cho máy chủ SMTP hoặc dịch vụ gửi thư khác.
5. **Ghi nhận kết quả:** ghi nhận thao tác gửi, phân loại lỗi và thực hiện retry/giám sát khi cần.

Sơ đồ luồng điển hình:

~~~mermaid
flowchart LR
    A["Sự kiện nghiệp vụ / API / lịch chạy"] --> B["Mail application service"]
    B --> C["Dữ liệu người nhận + mẫu nội dung"]
    C --> D["Tạo email: text hoặc MIME"]
    D --> E["JavaMailSender"]
    E --> F["SMTP server / nhà cung cấp email"]
    F --> G["Máy chủ thư của người nhận"]
    B -. "Ghi nhận kết quả, lỗi" .-> H["Log / trạng thái / metric"]
~~~

**Phân biệt quan trọng:** khi phương thức gửi thư trả về thành công, thông thường điều đó chỉ có nghĩa ứng dụng đã giao thông điệp cho máy chủ gửi thư và máy chủ chấp nhận thao tác tương ứng. Nó **không bảo đảm** email đã tới hộp thư đến, đã được đọc hoặc không bị phân loại là spam. Những trạng thái như delivered, bounced, complained thường cần cơ chế phản hồi riêng từ nhà cung cấp.

## 2. Những thành phần thường có trong module

| Thành phần | Vai trò | Ví dụ | Bắt buộc? |
| --- | --- | --- | --- |
| **Nguồn kích hoạt (trigger)** | Quyết định lúc nào phải gửi thư | Đăng ký tài khoản, sự kiện thanh toán, tác vụ theo lịch | Phải có một nguồn kích hoạt, nhưng không nhất thiết là REST API |
| **Request/command hoặc event** | Mang thông tin cần gửi, tách khỏi giao thức gọi | `SendWelcomeEmailCommand`, `OrderPaidEvent` | Khuyến nghị khi nghiệp vụ phức tạp |
| **Application service** | Điều phối quy trình gửi, chọn loại thư và xử lý kết quả | `NotificationMailService` | Thường có |
| **Template và dữ liệu mẫu** | Sinh nội dung phù hợp ngữ cảnh, ngôn ngữ, thương hiệu | `welcome.html`, tên người dùng, đường dẫn xác nhận | Tùy nhu cầu |
| **Message builder/composer** | Biến nội dung thành thông điệp email chuẩn | `SimpleMailMessage`, `MimeMessageHelper` | Có dưới một hình thức nào đó |
| **Mail sender / transport adapter** | Gửi thông điệp tới máy chủ mail | `JavaMailSender`, `JavaMailSenderImpl` | Có khi dùng Spring Mail qua SMTP |
| **Cấu hình SMTP và danh tính gửi** | Cung cấp host, port, xác thực, mã hóa, From | `spring.mail.*`, `app.mail.from` | Có khi dùng SMTP |
| **Theo dõi lỗi và trạng thái** | Biết lần gửi nào lỗi và vì sao | Log, metric, trạng thái tác vụ | Nên có |
| **Queue / worker / outbox** | Tách việc gửi khỏi request và hỗ trợ xử lý lại | Message broker, hàng đợi công việc | Tùy quy mô, độ tin cậy |
| **Kiểm thử và môi trường giả lập mail** | Kiểm tra nội dung và luồng gửi an toàn | Mock sender, Mailpit, GreenMail | Nên có trong dự án |

Với chức năng đơn giản như gửi một thông báo nội bộ, service gọi trực tiếp `JavaMailSender` là đủ. Khi có nhiều loại thư, nhiều nhà cung cấp hoặc cần đảm bảo không mất yêu cầu gửi, có thể bổ sung composer, gateway, queue và outbox.

## 3. Các lớp và interface cốt lõi của Spring Mail

Spring cung cấp API gửi thư, còn việc lưu trữ template, quyết định gửi và xử lý nghiệp vụ thường do ứng dụng thiết kế.

### 3.1. `MailSender` và `JavaMailSender`

- **`MailSender`** là abstraction đơn giản cho thư văn bản dạng `SimpleMailMessage`.
- **`JavaMailSender`** kế thừa `MailSender` và bổ sung khả năng tạo, gửi `MimeMessage`. Đây là interface thường được inject vào service trong ứng dụng Spring hiện đại.
- **`JavaMailSenderImpl`** là implementation SMTP thông dụng do Spring cung cấp. Khi dùng Spring Boot và cấu hình mail phù hợp, Boot có thể tự tạo bean sender; nếu dùng Spring Framework thuần, ứng dụng có thể tự cấu hình bean `JavaMailSenderImpl`.

Nhìn quan hệ theo hướng sử dụng:

~~~text
MailSender (interface)
  └── JavaMailSender (interface)
        └── JavaMailSenderImpl (SMTP implementation)

NotificationMailService
  └── phụ thuộc vào JavaMailSender, không phụ thuộc trực tiếp vào implementation
~~~

Điểm cần nhớ: **service nên phụ thuộc vào interface** để dễ thay đổi cách cấu hình và thay bằng implementation giả khi kiểm thử.

### 3.2. `SimpleMailMessage`: email văn bản thuần

`SimpleMailMessage` của Spring phù hợp với email text đơn giản. Nó có các trường như người gửi, người nhận, CC, BCC, tiêu đề và nội dung văn bản. Đây **không** phải dạng thư dành cho HTML hay file đính kèm.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Xác nhận đăng ký");
message.setText("Tài khoản của bạn đã được tạo.");

mailSender.send(message);
~~~

### 3.3. `MimeMessage` và `MimeMessageHelper`: HTML, nhiều phần, đính kèm

`MimeMessage` thuộc **Jakarta Mail** (`jakarta.mail.internet.MimeMessage`), biểu diễn một thông điệp email theo chuẩn MIME. Nó hỗ trợ nội dung HTML, nhiều phần thay thế (text/HTML), hình ảnh nội tuyến và file đính kèm.

`MimeMessageHelper` thuộc **Spring** (`org.springframework.mail.javamail.MimeMessageHelper`), giúp cấu hình `MimeMessage` dễ hơn: set người nhận, tiêu đề, encoding, text/HTML, attachment.

~~~java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn của bạn");
helper.setText(
    "Hóa đơn đã sẵn sàng. Vui lòng xem nội dung đính kèm.",
    "<h1>Hóa đơn đã sẵn sàng</h1><p>Xin cảm ơn bạn.</p>"
);
helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);

mailSender.send(mime);
~~~

Ví dụ trên đặt phần nội dung text và HTML thay thế nhau, đồng thời đính kèm PDF. Phần mã này cần biến `pdfBytes` chứa dữ liệu PDF và xử lý `MessagingException` (ngoại lệ được khai báo khi cấu hình MIME). Với `ByteArrayResource`, dữ liệu tệp đã nằm trong bộ nhớ; tệp lớn nên được xử lý theo chiến lược lưu trữ và giới hạn dung lượng phù hợp.

| Nhu cầu | Thành phần thường dùng |
| --- | --- |
| Thông báo dạng text | `SimpleMailMessage` + `JavaMailSender` |
| Nội dung HTML | `MimeMessage` + `MimeMessageHelper` |
| Text và HTML thay thế | `MimeMessageHelper.setText(plainText, htmlText)` |
| File đính kèm | `MimeMessageHelper.addAttachment(...)` |
| Hình ảnh hiển thị trong nội dung | `MimeMessageHelper.addInline(...)` |

## 4. Các thành phần do ứng dụng tự xây dựng

### 4.1. Trigger: ai quyết định gửi?

Một module gửi mail không tự biết khi nào người dùng vừa đăng ký hay đơn hàng đã thanh toán. Tín hiệu đó thường đến từ:

- **Controller/API:** nhận một yêu cầu có xác thực; phù hợp với thao tác gửi thủ công hoặc công cụ nội bộ.
- **Application/domain service:** gọi chức năng gửi sau một nghiệp vụ như tạo tài khoản.
- **Event consumer:** nhận sự kiện `UserRegistered` hoặc `OrderPaid` từ hệ thống khác.
- **Scheduler/batch job:** gửi báo cáo hằng ngày hoặc nhắc hạn theo lịch.
- **Queue worker:** xử lý yêu cầu gửi đã được lưu trong hàng đợi.

Một hệ thống chỉ dùng event consumer vẫn là module gửi mail hoàn chỉnh dù không có controller. Không nên mở endpoint công khai cho phép người ngoài tùy ý đặt người nhận và nội dung, vì dễ bị lạm dụng để gửi spam.

### 4.2. DTO, command và dữ liệu nghiệp vụ

Command diễn đạt **ý định gửi** ở mức ứng dụng, ví dụ `SendPasswordResetEmail(userId, resetLink)`. Thông thường nghiệp vụ cung cấp dữ liệu (địa chỉ, tên, loại thông báo, mã giao dịch); mail service chịu trách nhiệm chọn template và dựng thư.

Phân biệt hai mức dữ liệu:

- **Dữ liệu nghiệp vụ:** user ID, order ID, đường dẫn xác nhận, ngôn ngữ mong muốn.
- **Dữ liệu giao thức email:** From, To, Subject, phần thân text/HTML, attachment.

Không nên để domain service tự ghép chuỗi HTML, thông số SMTP và logic retry. Điều này khiến thay đổi mẫu thư hoặc provider ảnh hưởng không cần thiết tới nghiệp vụ.

### 4.3. Template renderer: ai tạo nội dung?

Nếu một loại email chỉ có vài dòng, service có thể tạo nội dung text trực tiếp. Nếu có nhiều loại email hoặc yêu cầu đa ngôn ngữ, nên tách template thành tài nguyên riêng:

~~~text
src/main/resources/
  templates/
    mail/
      welcome.html
      order-confirmed.html
      password-reset.html
~~~

Template engine như Thymeleaf có thể ghép dữ liệu vào HTML trước khi composer tạo `MimeMessage`. Nên truyền dữ liệu đã được chọn lọc, escape các giá trị không tin cậy theo đúng ngữ cảnh HTML/URL, không nối thẳng chuỗi do người dùng nhập vào markup. Với email quan trọng, cung cấp thêm bản text để hỗ trợ client không hiển thị HTML.

### 4.4. Mail application service: điểm điều phối chính

Service nhận yêu cầu gửi, kiểm tra thông tin cơ bản, chọn cách dựng thư rồi gọi sender. Với module nhỏ, có thể viết trực tiếp như sau:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendText(String to, String subject, String content) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(content);
        mailSender.send(message);
    }
}
~~~

Code trên tập trung vào **vai trò của thành phần**, chưa giải quyết việc xác thực nguồn gọi, kiểm tra địa chỉ người nhận, cơ chế chống gửi trùng, retry hay quản lý trạng thái. Những việc đó thuộc các lớp phù hợp khác hoặc được bổ sung khi có yêu cầu.

Khi cần thay được SMTP bằng HTTP API của nhà cung cấp, có thể tạo interface riêng như `MailGateway` ở ứng dụng rồi cung cấp implementation `SmtpMailGateway`. Khi chỉ có một phương thức SMTP đơn giản, inject trực tiếp `JavaMailSender` vẫn hợp lý.

## 5. Cấu hình kết nối và nhà cung cấp email

### 5.1. Dependency

Với **Spring Boot**, starter thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter đưa các thành phần Spring Mail và thư viện Jakarta Mail cần thiết vào ứng dụng. Spring Boot hỗ trợ cấu hình `JavaMailSender` qua thuộc tính `spring.mail.*` khi điều kiện auto-configuration được đáp ứng. Trong ứng dụng chỉ dùng Spring Framework thuần, cần khai báo dependency mail và cấu hình sender thủ công.

### 5.2. Cấu hình ví dụ cho SMTP dùng STARTTLS

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
~~~

Ý nghĩa các nhóm thuộc tính:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `host`, `port` | Máy chủ SMTP và cổng kết nối |
| `username`, `password` | Thông tin xác thực theo yêu cầu của nhà cung cấp |
| `mail.smtp.auth` | Bật xác thực SMTP |
| `mail.smtp.starttls.enable` | Cho phép nâng cấp kết nối SMTP sang TLS bằng STARTTLS |
| `mail.smtp.starttls.required` | Yêu cầu STARTTLS thành công, tránh tiếp tục trên kết nối không mã hóa |
| Các timeout | Giới hạn thời gian kết nối, đọc và ghi để tránh chờ vô hạn |
| `app.mail.from` | Địa chỉ From do ứng dụng quản lý, cần được nhà cung cấp cho phép |

Ví dụ trên dùng cổng 587 theo cách cấu hình STARTTLS phổ biến; giá trị thực tế phải theo nhà cung cấp. Nếu dùng SMTPS qua cổng 465, cấu hình TLS trực tiếp như `mail.smtp.ssl.enable` cần được thiết lập theo hướng dẫn của provider. Không sao chép mù quáng các thuộc tính bảo mật giữa hai chế độ kết nối.

**Không lưu mật khẩu SMTP trong mã nguồn hoặc file được commit.** Có thể đọc từ biến môi trường hoặc secret manager. Bên cạnh đó, địa chỉ From và domain gửi thường cần xác thực với nhà cung cấp; việc điền một địa chỉ bất kỳ trong code không đồng nghĩa server sẽ chấp nhận gửi thay địa chỉ đó.

### 5.3. SMTP server, provider và việc thư đến hộp nhận

`JavaMailSenderImpl` gửi email qua SMTP server. SMTP server có thể do doanh nghiệp tự vận hành hoặc do nhà cung cấp email giao dịch quản lý. Nhà cung cấp thường thực hiện thêm việc xếp hàng, chuyển thư, trả kết quả bounce và hỗ trợ xác thực domain qua SPF/DKIM/DMARC.

Cần phân biệt:

- **SMTP transport:** giao tiếp kỹ thuật để nộp thư.
- **Mail provider:** hệ thống thực sự chuyển và theo dõi thư, có thể cung cấp dashboard/webhook/API.
- **Mail client:** Gmail, Outlook hoặc ứng dụng người nhận dùng để xem thư.

Spring Mail chủ yếu giải quyết phía **tạo và gửi** thông điệp. Nó không tự xây dựng inbox, quản lý bounce, bảo đảm thư vào Inbox hay cung cấp lịch sử gửi bền vững.

## 6. Cách các lớp được tổ chức trong một dự án

Một cấu trúc có thể áp dụng khi module đã có nhiều loại email:

~~~text
src/main/java/com/example/mail/
  api/
    MailAdminController.java          # Tùy chọn: API nội bộ
    SendMailRequest.java              # Input và validation
  application/
    NotificationMailService.java      # Điều phối nghiệp vụ gửi
    MailCommand.java                  # Ý định gửi
  template/
    MailTemplateRenderer.java         # Tạo text/HTML
  transport/
    SmtpMailGateway.java              # Gói tương tác JavaMailSender
  config/
    MailConfiguration.java            # Chỉ khi cần cấu hình riêng
  worker/
    MailJobConsumer.java              # Tùy chọn: nhận job từ queue
src/main/resources/
  application.yml
  templates/mail/
~~~

Đây là **cấu trúc minh họa**, không phải tên package bắt buộc của Spring. Nếu không có API thì bỏ `api/`; nếu Spring Boot đã cấu hình sender đúng thì không cần tạo lại `MailConfiguration`; nếu service chỉ có vài dòng thì chưa cần tách `SmtpMailGateway`.

Nguyên tắc chọn ranh giới:

| Lớp/thành phần | Nên biết gì? | Không nên gánh việc gì? |
| --- | --- | --- |
| Business service / event producer | Vì sao cần gửi, dữ liệu nghiệp vụ nào liên quan | Host, port SMTP, cấu trúc MIME |
| Application mail service | Ai nhận, loại email nào, luồng điều phối | Tự quản socket SMTP |
| Template renderer | Nội dung và biến dữ liệu hiển thị | Chính sách retry, mật khẩu SMTP |
| Composer / transport adapter | Cách dựng và gửi message đúng giao thức | Quyết định nghiệp vụ có phát sinh email hay không |
| Infrastructure config | SMTP host, bảo mật, credentials, timeout | Nội dung email của từng nghiệp vụ |

## 7. Gửi đồng bộ, bất đồng bộ và hàng đợi

### 7.1. Gửi đồng bộ

~~~text
HTTP request → Xử lý nghiệp vụ → mailService.send(...) → SMTP → HTTP response
~~~

Ưu điểm là đơn giản, dễ theo dõi; phù hợp tác vụ nội bộ hoặc lưu lượng nhỏ. Nhược điểm là request phải chờ thao tác SMTP. Nếu SMTP chậm hoặc bị gián đoạn, luồng nghiệp vụ có thể chậm hoặc thất bại theo.

### 7.2. Gửi qua worker/queue

~~~text
HTTP request → Lưu nghiệp vụ + tạo yêu cầu gửi → Phản hồi
                                      ↓
                                  Queue / Job
                                      ↓
                                Mail worker → SMTP
~~~

Trong kiến trúc này, thành phần nhận yêu cầu **ghi nhận công việc**, còn worker mới thực hiện gửi. Queue giúp giải phóng luồng request và tạo chỗ cho retry, giới hạn tốc độ hoặc xử lý theo ưu tiên. Nếu yêu cầu gửi cần đi cùng một transaction nghiệp vụ, **transactional outbox** là một lựa chọn: lưu sự kiện cần gửi cùng transaction rồi một tiến trình khác phát đi, giảm khả năng cập nhật nghiệp vụ thành công nhưng mất yêu cầu mail.

Gửi bất đồng bộ không tự động đồng nghĩa “đã giao thư”. API có thể trả về trạng thái **đã nhận yêu cầu xử lý** và cung cấp ID để tra cứu; trạng thái này khác với **đã gửi đến SMTP** và **đã giao đến mailbox**.

### 7.3. Retry và trùng thư

Lỗi mạng tạm thời hoặc SMTP trả mã lỗi có thể cần thử lại theo backoff. Nhưng nếu máy chủ đã nhận thư còn client bị timeout trước khi nhận phản hồi, gửi lại có thể tạo **thư trùng**. Vì vậy, hệ thống quan trọng cần có ID sự kiện/yêu cầu, cơ chế chống xử lý trùng ở phía ứng dụng, số lần thử tối đa và trạng thái cuối cùng hoặc hàng đợi lỗi.

Không nên retry vô hạn cho mọi lỗi. Sai credentials, địa chỉ người nhận không hợp lệ hay vi phạm chính sách provider thường cần xử lý cấu hình/dữ liệu trước, trong khi lỗi tạm thời có thể retry.

## 8. Kết quả gửi, ngoại lệ và quan sát vận hành

Các lỗi trong Spring Mail có thể được biểu diễn bằng hệ thống ngoại lệ `MailException` (unchecked) cùng những kiểu cụ thể như `MailAuthenticationException`, `MailSendException` hoặc `MailPreparationException`. Với MIME, thao tác tạo/cấu hình thông điệp có thể phát sinh `MessagingException` của Jakarta Mail. Cần phân biệt lỗi **chuẩn bị thư**, **xác thực**, **kết nối** và **SMTP từ chối** để quyết định cách xử lý.

Một số thông tin đáng ghi nhận cho từng yêu cầu:

- ID nghiệp vụ hoặc ID yêu cầu gửi, loại template, thời điểm tạo và thời điểm thử gửi;
- trạng thái xử lý như PENDING, PROCESSING, SUBMITTED, FAILED; mã lỗi rút gọn và số lần thử;
- thời gian gọi provider, số lần retry, tỷ lệ lỗi và lượng tác vụ đang chờ.

Tránh ghi vào log mật khẩu SMTP, token reset mật khẩu, nội dung nhạy cảm trong thư hoặc toàn bộ địa chỉ email khi không cần thiết. Nếu nhà cung cấp có webhook bounce/delivery, có thể cập nhật trạng thái **sau khi nộp thư** dựa trên các sự kiện đó.

## 9. Kiểm thử từng ranh giới

Các thành phần khác nhau dẫn đến cách kiểm thử khác nhau:

| Phần cần kiểm thử | Cách tiếp cận phù hợp | Điều cần quan sát |
| --- | --- | --- |
| Application service | Mock/fake `JavaMailSender` hoặc gateway | Có gọi gửi đúng người nhận, subject, nội dung không |
| Template renderer | Render template với bộ dữ liệu mẫu | Nội dung/escaping, biến thiếu, ngôn ngữ |
| Composer MIME | Tạo `MimeMessage` không cần gửi ra Internet | Multipart, content type, attachment, encoding |
| Kết nối SMTP | SMTP server giả lập tại local/test environment (ví dụ Mailpit hoặc GreenMail) | Ứng dụng kết nối, xác thực và nộp thư được |
| Worker/queue | Test tích hợp có job và trạng thái | Retry, xử lý trùng, giới hạn lần thử |

Trong môi trường phát triển, SMTP giả lập giúp kiểm tra thư mà không gửi email thật cho khách hàng. Test unit cũng không nên phụ thuộc trực tiếp vào dịch vụ SMTP bên ngoài vì vừa chậm vừa dễ không ổn định.

## 10. Những nhầm lẫn thường gặp khi đọc code gửi mail

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có `spring-boot-starter-mail` là gửi được ngay.” | Còn cần sender được cấu hình, host/provider khả dụng, credentials, kết nối và From hợp lệ. |
| “`SimpleMailMessage` gửi được HTML.” | Nó dành cho plain text; dùng MIME để tạo HTML và đính kèm. |
| “`MimeMessageHelper` là máy chủ gửi thư.” | Nó chỉ giúp dựng thông điệp; `JavaMailSender` mới gửi đi. |
| “Module gửi mail luôn phải có REST controller.” | Có thể khởi phát từ nghiệp vụ, event, scheduler hoặc worker. |
| “Không ném exception nghĩa là người nhận đã đọc thư.” | Điều đó không xác nhận delivery hoặc read receipt. |
| “Bật `@Async` là có queue đáng tin cậy.” | `@Async` chỉ chạy công việc ở thread khác; nó không tự cung cấp lưu trữ bền vững hay retry qua restart. |
| “Chỉ cần retry mọi lỗi SMTP.” | Cần phân loại lỗi, có giới hạn thử lại và xử lý nguy cơ gửi trùng. |

## 11. Ghép các thành phần vào một tình huống cụ thể

Giả sử ứng dụng cần gửi thư xác nhận sau khi người dùng đăng ký:

1. **User service** hoàn tất đăng ký và phát sinh yêu cầu `SendWelcomeEmailCommand` với user ID và thông tin cần thiết.
2. **NotificationMailService** chọn template “welcome”, lấy email người nhận và dựng dữ liệu cho template.
3. **Template renderer** sinh phần text/HTML. Nội dung chứa tên người dùng đã được escape phù hợp.
4. **Composer** tạo `MimeMessage`, thêm subject, From, To và nội dung bằng `MimeMessageHelper`.
5. **`JavaMailSender`** nộp thư cho SMTP provider qua kết nối đã cấu hình.
6. **Cơ chế ghi nhận kết quả** lưu lần gửi thành công hay thất bại; worker/queue xử lý tiếp nếu kiến trúc có yêu cầu retry.

Qua ví dụ này, có thể nhận diện ba nhóm chính khi đọc code của bất kỳ module mail nào:

- **Ứng dụng quyết định gửi cái gì, cho ai và khi nào**: trigger, command, application service, template.
- **Spring/Jakarta biến yêu cầu thành email và gửi đi**: `SimpleMailMessage` hoặc `MimeMessage`, `MimeMessageHelper`, `JavaMailSender`.
- **Hạ tầng bảo đảm thao tác vận hành được**: SMTP configuration, provider, timeout, trạng thái, queue/retry và giám sát khi cần.

Nắm được ranh giới giữa các nhóm này sẽ giúp bạn đọc cấu trúc dự án dễ hơn và biết phải sửa đúng chỗ khi phát sinh yêu cầu đổi mẫu thư, thêm attachment, thay SMTP server hoặc nâng cấp cơ chế gửi.
