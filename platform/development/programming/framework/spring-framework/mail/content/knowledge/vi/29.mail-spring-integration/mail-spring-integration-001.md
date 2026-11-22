# Outbound mail adapter và message channel

Khi một ứng dụng cần gửi email xác nhận đơn hàng, thông báo trạng thái hoặc email từ các sự kiện nghiệp vụ, cách đơn giản nhất thường là gọi trực tiếp `JavaMailSender.send(...)`. Nhưng khi hệ thống có nhiều nguồn phát sự kiện, cần kiểm soát luồng xử lý, biến đổi nội dung, phân tuyến, giới hạn tốc độ hoặc tách logic gửi mail khỏi business service, **Spring Integration Mail** cung cấp một cách tổ chức dựa trên **message channel** và **outbound mail adapter**.

Trong mô hình này, nghiệp vụ không nhất thiết gọi SMTP trực tiếp. Nghiệp vụ phát một **Spring Integration Message** vào một **MessageChannel**. Các endpoint tiếp theo có thể kiểm tra dữ liệu, enrich mail headers, biến đổi payload và cuối cùng chuyển message cho **mail outbound adapter**. Adapter dùng hạ tầng gửi mail của Spring để submit thông điệp.

Điểm quan trọng nhất: **outbound mail adapter là một endpoint tiêu thụ thông điệp ở cuối luồng**, không phải inbox, message broker bền vững hay API báo email đã vào hộp thư người nhận. Channel quy định **cách giao công việc** giữa các endpoint; adapter quy định **cách chuyển thông điệp thành thao tác gửi mail**. Hiểu rõ ranh giới này giúp tránh nhầm lẫn giữa việc một message được nhận vào channel, SMTP submission và email đã delivered.

Bài học thuộc chương **Spring Integration Mail** của module **Spring Framework Mail**, tập trung vào hai thành phần: **Outbound mail adapter và message channel**. Các ví dụ dùng Java, Spring Integration Java DSL, `JavaMailSender`, `MailSendingMessageHandler` và những cấu hình channel phổ biến. Phần cuối giải thích lỗi gửi, async, poller, retry, test và các rủi ro vận hành.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, bạn sẽ:

1. Giải thích `MessageChannel`, `Message<?>`, `MessageHandler` và outbound channel adapter.
2. Vẽ được luồng từ business event đến SMTP qua Spring Integration.
3. Cấu hình outbound mail adapter bằng Java DSL hoặc `@ServiceActivator`.
4. Truyền body và các mail headers `TO`, `CC`, `BCC`, `FROM`, `REPLY_TO`, `SUBJECT`.
5. Phân biệt payload `String`, `MailMessage` và `byte[]`; biết khi nào cần transformer.
6. Chọn `DirectChannel`, `ExecutorChannel` hoặc `QueueChannel` theo hành vi mong muốn.
7. Hiểu poller bắt buộc với nguồn `PollableChannel` ở endpoint tiêu thụ.
8. Nhận biết khi nào lỗi gửi quay về caller và khi nào phải xử lý bất đồng bộ.
9. Thiết kế một pipeline không làm mất thông báo khi process restart.
10. Kiểm thử nội dung mail và tính chất luồng mà không gửi tới SMTP production.

## 2. Spring Mail và Spring Integration Mail khác nhau ở đâu?

`Spring Framework Mail` cung cấp các abstraction như:

- `MailSender` và `JavaMailSender` để gửi email.
- `SimpleMailMessage` cho nội dung text đơn giản.
- `MimeMessageHelper` để hỗ trợ HTML, multipart, ảnh inline, attachment.
- `JavaMailSenderImpl` để kết nối và gửi qua SMTP.

`Spring Integration` là framework cho các **Enterprise Integration Patterns (EIP)**: channels, transformers, routers, filters, service activators, pollers, gateways và các adapter kết nối hệ thống bên ngoài.

`Spring Integration Mail` kết hợp hai miền này:

```text
Ứng dụng nghiệp vụ
       |
       v
Message<?> của Spring Integration
       |
       v
MessageChannel
       |
       v
Transformer / Header Enricher / Filter / Router
       |
       v
Outbound Mail Adapter
       |
       v
MailSendingMessageHandler
       |
       v
JavaMailSender / SMTP Provider
```

Đối tượng `org.springframework.messaging.Message<?>` ở đây **khác** với `jakarta.mail.Message` hoặc `MimeMessage`. Một đối tượng là envelope cho **luồng tích hợp bên trong ứng dụng**, còn đối tượng kia là cấu trúc **thư điện tử**.

| Khái niệm | Package hoặc phạm vi | Trách nhiệm |
| --- | --- | --- |
| `Message<?>` | `org.springframework.messaging` | Payload + headers cho pipeline tích hợp |
| `MessageChannel` | `org.springframework.messaging` | Chuyển Spring Integration Message đến consumer |
| `MessageHandler` | `org.springframework.messaging` | Tiêu thụ message từ channel |
| `MailSendingMessageHandler` | Spring Integration Mail | Chuyển payload/headers thành thao tác gửi mail |
| `MailMessage` | `org.springframework.mail` | Mô hình message mail của Spring |
| `MimeMessage` | `jakarta.mail.internet` | MIME email, headers và multipart parts |
| `JavaMailSender` | `org.springframework.mail.javamail` | Dịch vụ tạo/gửi MIME và mail đơn giản |

**Hai tầng message không được đánh đồng.** Header của Spring Integration như `id` và `timestamp` chỉ là metadata trong pipeline; chúng không tự biến thành header RFC của email. Những header dành cho mail có cơ chế mapping riêng.

## 3. Outbound mail adapter là gì?

Trong Spring Integration, **outbound channel adapter** là endpoint tiêu thụ message từ channel rồi gọi một hệ thống bên ngoài. Với mail, hệ thống bên ngoài là mail sender/SMTP transport.

Khung luồng:

```text
[Integration Message]
         |
         v
    outboundMail
         |
         v
   +-------------+
   | Mail adapter|  -----> SMTP server
   +-------------+
         |
         +--- Không tạo reply payload theo kiểu request/reply
```

Một adapter dạng **one-way** không có nghĩa không thể báo lỗi. Nếu một operation lỗi, exception vẫn có thể được chuyển về caller hoặc error infrastructure tùy cách channel dispatch.

### Adapter không làm những việc sau

- Không phải inbox để đọc email đến bằng POP3/IMAP.
- Không phải SMTP server nhận mail từ client.
- Không mặc định lưu queue bền vững trên database.
- Không tự retry tất cả lỗi một cách an toàn.
- Không có cam kết exactly-once delivery.
- Không mặc định cung cấp callback `delivered`, `bounced` hoặc `opened`.
- Không tự chuyển một object nghiệp vụ bất kỳ thành email hoàn chỉnh nếu chưa có mapping/transformer phù hợp.

Những tính năng đó cần các thành phần khác hoặc một tầng kiến trúc bổ sung.

## 4. MessageChannel giữ vai trò gì?

`MessageChannel` là đường truyền thông điệp giữa producer và consumer. Producer chỉ cần biết **đẩy gì vào channel**, không nhất thiết biết producer SMTP cụ thể đang xử lý thế nào.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

Message<String> mailRequest = MessageBuilder
        .withPayload("Đơn hàng đã được xác nhận.")
        .build();

boolean acceptedByChannel = outboundMail.send(mailRequest);
```

Hàm `send(...)` trả boolean theo contract channel, nhưng **`true` không được diễn giải chung là email đã delivered**. Với `DirectChannel`, việc dispatch thường chạy ngay trong caller thread; với `QueueChannel`, nó có thể mới chỉ được đặt vào queue; với `ExecutorChannel`, xử lý có thể được giao cho executor khác.

### Một channel phân tách hai bên

```text
OrderService / PaymentService / Scheduler
                   |
                   v
              outboundMail
                   |
                   v
             Mail Adapter
                   |
                   v
               SMTP Relay
```

Nếu thay mail adapter bằng một test handler hoặc đổi SMTP provider, producer không nhất thiết phải thay đổi. Tuy nhiên, **producer vẫn chịu trách nhiệm nghiệp vụ**: ai cần nhận, khi nào được gửi và nội dung có hợp lệ hay không.

## 5. Các dependency cần chuẩn bị

Với dự án Spring Boot hiện đại dùng namespace `jakarta.mail`, thường cần module tích hợp mail:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là ví dụ Gradle cho dự án dùng Spring Boot dependency management. Trong một số phiên bản starter/module, dependency transitively được đưa vào theo cách khác; hãy kiểm tra dependency graph thực tế và tránh khai báo các phiên bản Spring Integration/Spring Framework không tương thích.

Với Spring Integration hiện đại, lớp JavaMail sử dụng `jakarta.mail.*`. Dự án Spring 5/Integration đời cũ có thể dùng `javax.mail.*`. Không trộn hai namespace trong cùng code mà không có chiến lược migration rõ.

### Tài liệu nên đối chiếu theo phiên bản

API Java DSL và package có thể thay đổi qua các major version. Các ví dụ sử dụng các API được nêu trong Spring Integration Mail reference, gồm `Mail.outboundAdapter(...)`, `IntegrationFlow`, `MailSendingMessageHandler` và `MailHeaders`. Khi triển khai, đối chiếu tài liệu đúng phiên bản Spring Integration do Spring Boot quản lý.

## 6. Ví dụ đơn giản nhất: DirectChannel + outbound adapter

Ví dụ này sử dụng `JavaMailSender` đã được Spring Boot cấu hình và một `DirectChannel` để nhận thông điệp text.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mail.dsl.Mail;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OutboundMailIntegrationConfig {

    @Bean
    public MessageChannel outboundMail() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow outboundMailFlow(
            MessageChannel outboundMail,
            JavaMailSender mailSender
    ) {
        return IntegrationFlow.from(outboundMail)
                .handle(Mail.outboundAdapter(mailSender))
                .get();
    }
}
```

Ý nghĩa của từng phần:

1. `@Bean outboundMail()` tạo channel nhận những yêu cầu gửi.
2. `DirectChannel` dispatch message trực tiếp tới subscriber trong cùng thread theo hành vi thông thường.
3. `IntegrationFlow.from(outboundMail)` nhận message từ channel.
4. `handle(Mail.outboundAdapter(mailSender))` gắn mail-sending handler ở cuối flow.
5. `get()` kết thúc cấu hình DSL.

Với text payload, ta cần cung cấp các header mail cần thiết để adapter biết recipient, From và subject. Không nên nghĩ rằng chỉ `String` body là đủ để gửi một email hợp lệ nếu chưa có người nhận.

## 7. Gửi một message bằng MessageBuilder

Giả sử channel `outboundMail` đã được inject vào một service:

```java
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class NotificationPublisher {

    private final MessageChannel outboundMail;

    public NotificationPublisher(MessageChannel outboundMail) {
        this.outboundMail = outboundMail;
    }

    public void publishOrderConfirmed() {
        boolean channelAccepted = outboundMail.send(
                MessageBuilder
                        .withPayload("Đơn hàng #A123 đã xác nhận.")
                        .setHeader(
                                MailHeaders.TO,
                                "tester@example.net"
                        )
                        .setHeader(
                                MailHeaders.FROM,
                                "notify@example.org"
                        )
                        .setHeader(
                                MailHeaders.SUBJECT,
                                "Xác nhận đơn hàng"
                        )
                        .build()
        );

        if (!channelAccepted) {
            throw new IllegalStateException(
                    "Outbound channel did not accept message"
            );
        }
    }
}
```

Địa chỉ dùng trong ví dụ là **địa chỉ giả** để minh họa cấu trúc. Khi chạy, SMTP sender phải được cấu hình với một server test/sandbox và các sender domain được phép.

### Điểm cần tránh

Hàm `publishOrderConfirmed()` chỉ kiểm tra channel trả `true`; **không thể đặt tên biến `mailDelivered` cho kết quả đó**. Nếu channel là `DirectChannel` và downstream đồng bộ, method có thể ném exception khi sender lỗi. Nếu channel là async/queue, kết quả thường chỉ nói rằng công việc đã được nhận vào một tầng trung gian.

## 8. MailHeaders và quy tắc mapping

Spring Integration Mail định nghĩa các hằng số mail header:

| Header constant | Nội dung | Ví dụ |
| --- | --- | --- |
| `MailHeaders.TO` | Người nhận chính | `tester@example.net` |
| `MailHeaders.CC` | Người nhận Cc | `supervisor@example.net` |
| `MailHeaders.BCC` | Người nhận Bcc | `audit@example.net` |
| `MailHeaders.FROM` | Địa chỉ người gửi | `notify@example.org` |
| `MailHeaders.REPLY_TO` | Địa chỉ nhận phản hồi | `support@example.org` |
| `MailHeaders.SUBJECT` | Chủ đề | `Đơn hàng đã xác nhận` |

Mail adapter có thể map những header này sang thuộc tính email. **Tên header nên lấy từ `MailHeaders` constants**, không tự viết chuỗi `"to"`, `"subject"` theo cảm tính.

### Header là metadata của Integration Message

```text
Message<String>
  payload = "Xin chào"
  headers:
    mail_to      = "tester@example.net"
    mail_from    = "notify@example.org"
    mail_subject = "Thử nghiệm"
    id           = UUID của Spring Message
    timestamp    = ...
```

Đây là cách nhìn khái niệm; tên string thực của header phải sử dụng giá trị constants của phiên bản thư viện. `id` và `timestamp` là metadata Spring message, không tự được đặt thành `Message-ID` và `Date` trong MIME.

## 9. Header Enricher để tách nội dung khỏi metadata gửi

Thay vì mỗi producer tự đặt recipient và sender, luồng có thể dùng **header enricher** trước outbound adapter:

```text
Message<String> body
       |
       v
Header Enricher
  mail_to = ...
  mail_from = ...
  mail_subject = ...
       |
       v
Outbound Mail Adapter
```

Ví dụ DSL với các giá trị test cố định:

```java
@Bean
public IntegrationFlow simpleMailFlow(
        JavaMailSender mailSender
) {
    return IntegrationFlow
            .from("mailBodyInput")
            .enrichHeaders(h -> h
                    .header(
                            MailHeaders.TO,
                            "tester@example.net"
                    )
                    .header(
                            MailHeaders.FROM,
                            "notify@example.org"
                    )
                    .header(
                            MailHeaders.SUBJECT,
                            "Thông báo từ Integration"
                    ))
            .handle(Mail.outboundAdapter(mailSender))
            .get();
}
```

Ví dụ này minh họa cách dùng DSL, không phù hợp để gửi cho nhiều recipient khác nhau khi mọi email đều dùng một giá trị To cố định. Trong thực tế, có thể enrich từ payload DTO hoặc một bước kiểm tra/transformer.

### Vì sao nên enrich tại một nơi?

- Tập trung quy tắc From và Reply-To.
- Giảm việc mỗi producer quên đặt Subject.
- Cho phép route/tenant-specific policy trước khi tới adapter.
- Dễ kiểm thử header mapping độc lập với SMTP.
- Giúp phân biệt business payload và thuộc tính mail transport.

Tuy nhiên, nếu header enricher ghi đè `MailHeaders.TO` từ producer mà không kiểm soát, có thể gửi **nhầm người nhận**. Quy tắc overwrite/default-overwrite phải được quyết định theo contract luồng.

## 10. MailHeaders có thể override MailMessage

Nếu payload là một `MailMessage` đã có thuộc tính To, nhưng Spring Integration Message đi kèm `MailHeaders.TO` khác, tài liệu Spring Integration mô tả rằng **mail header có thể được dùng để ghi đè giá trị tương ứng trong MailMessage**.

```text
Payload MailMessage:
  To = original@example.net

Integration Message Header:
  MailHeaders.TO = override@example.net

Sau mapping trong mail outbound handler:
  Recipient có thể thành override@example.net
```

Đây là một điểm dễ gây lỗi bảo mật và tính đúng đắn. Chẳng hạn payload được tạo từ notification đã xác thực nhưng một bước enrich sau đó lấy To từ dữ liệu không đáng tin, thư có thể bị gửi sai.

Khuyến nghị:

1. Chỉ đặt recipient ở **một nơi có ownership rõ ràng**.
2. Nếu phải override, có policy và validation tường minh.
3. Không cho user input bất kỳ trở thành mail header không kiểm tra.
4. Viết test case có cả To trong payload và To trong header để xác nhận precedence.
5. Tránh forward nguyên headers của một message từ bên ngoài nếu không có allowlist.

## 11. Payload String: cách đơn giản nhất cho mail text

Khi payload là một `String`, mail outbound handler có thể tạo một message dạng text đơn giản và dùng mail headers để thiết lập recipient, subject, sender.

```java
var integrationMessage = MessageBuilder
        .withPayload("Đơn hàng đã thanh toán thành công.")
        .setHeader(MailHeaders.TO, "buyer@example.net")
        .setHeader(MailHeaders.FROM, "billing@example.org")
        .setHeader(MailHeaders.SUBJECT, "Thanh toán thành công")
        .build();

outboundMail.send(integrationMessage);
```

Phù hợp với:

- Thông báo text không cần định dạng HTML.
- Flow minh họa hoặc notification nội bộ đơn giản.
- Đầu ra transformer đã là một `String` hoàn chỉnh.

Không tự hiểu `String` có nội dung `"<h1>Xin chào</h1>"` là HTML được gắn `Content-Type: text/html`. Để gửi HTML, ảnh inline hoặc attachment có chủ đích, nên dùng một bước dựng MIME rõ ràng phù hợp với contract của handler.

## 12. Payload MailMessage: tách xây mail khỏi gửi

`MailMessage` là abstraction của Spring Mail, với những triển khai như `SimpleMailMessage` cho nội dung đơn giản.

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notify@example.org");
mail.setTo("tester@example.net");
mail.setSubject("Thông báo tài khoản");
mail.setText("Tài khoản của bạn đã được cập nhật.");

Message<SimpleMailMessage> request = MessageBuilder
        .withPayload(mail)
        .build();

outboundMail.send(request);
```

Khi nhận payload `MailMessage`, handler có thể chuyển đối tượng mail đã chuẩn bị cho sender. Đây là một cách giữ logic compose nội dung ở transformer/business boundary, trong khi adapter chỉ làm nhiệm vụ submit.

### Không dùng object mutable chung giữa nhiều notification

`SimpleMailMessage` là mutable. Nếu cùng một instance được chia sẻ giữa các thread rồi sửa `setTo`/`setText`, nội dung và recipient có thể bị lẫn. Mỗi notification nên có một payload riêng hoặc dùng DTO bất biến cho các bước trước khi compose.

## 13. Payload byte[] và attachment filename

Tài liệu về `MailSendingMessageHandler` mô tả khả năng map một payload `byte[]` thành attachment; trong trường hợp đó cần header `MailHeaders.ATTACHMENT_FILENAME` để xác định tên tệp.

```java
byte[] fileBytes = loadSyntheticBytes();

Message<byte[]> request = MessageBuilder
        .withPayload(fileBytes)
        .setHeader(MailHeaders.TO, "tester@example.net")
        .setHeader(MailHeaders.FROM, "report@example.org")
        .setHeader(MailHeaders.SUBJECT, "Tệp thử nghiệm")
        .setHeader(
                MailHeaders.ATTACHMENT_FILENAME,
                "sample.bin"
        )
        .build();

outboundMail.send(request);
```

`loadSyntheticBytes()` là method giả định của ứng dụng; khi test, nên dùng bytes giả và SMTP sandbox.

Giới hạn:

- Không tự động tạo ra một email HTML phức tạp chỉ từ `byte[]`.
- Đừng bỏ header filename khi contract handler yêu cầu.
- Đừng đưa tệp chứa dữ liệu nhạy cảm vào log hoặc test environment không kiểm soát.
- Với tệp lớn, `byte[]` có thể tạo memory pressure; nên cân nhắc một bước compose chuyên dụng với resource đọc lại được.

## 14. Payload DTO và transformer

Một DTO nghiệp vụ thường có nhiều dữ liệu hơn đoạn text:

```java
public record OrderMailCommand(
        UUID notificationId,
        String recipient,
        String orderCode,
        String customerDisplayName
) {}
```

Không nên đẩy DTO đó thẳng vào mail adapter rồi hy vọng adapter tự đoán `recipient` và `subject`. Thay vào đó, dùng transformer hoặc header enricher:

```text
Message<OrderMailCommand>
        |
        v
Validate + Render
        |
        v
Message<String> + MailHeaders.*
        |
        v
Mail adapter
```

Ví dụ chuẩn bị message từ DTO:

```java
public Message<String> toTextMail(
        OrderMailCommand command
) {
    String body = "Xin chào " + command.customerDisplayName()
            + ", đơn hàng " + command.orderCode()
            + " đã được xác nhận.";

    return MessageBuilder.withPayload(body)
            .setHeader(MailHeaders.TO, command.recipient())
            .setHeader(
                    MailHeaders.FROM,
                    "orders@example.org"
            )
            .setHeader(
                    MailHeaders.SUBJECT,
                    "Xác nhận " + command.orderCode()
            )
            .setHeader(
                    "appNotificationId",
                    command.notificationId().toString()
            )
            .build();
}
```

Lưu ý: `appNotificationId` là **header nội bộ do ứng dụng tự đặt**, không phải một header SMTP/MIME hoặc constant của Spring Integration Mail. Đừng tự giả định header này sẽ được provider phản hồi trong delivery webhook. Còn các giá trị recipient/orderCode/displayName phải được validate và encode/escape phù hợp với đường truyền và loại nội dung.

## 15. Java DSL với Mail.outboundAdapter(host)

Ngoài việc truyền một bean `JavaMailSender`, Spring Integration Java DSL có factory tạo outbound mail adapter bằng hostname:

```java
@Bean
public IntegrationFlow smtpMailFlow() {
    return IntegrationFlow.from("outboundMail")
            .handle(
                    Mail.outboundAdapter("127.0.0.1")
                            .port(2525)
                            .protocol("smtp")
            )
            .get();
}
```

Ví dụ này trỏ đến **SMTP test server trên localhost** tại port 2525. Trong một dự án thật, hostname, port, credentials và TLS settings cần được quản lý bằng configuration/secret manager, không hard-code vào source.

Khi muốn thử cấu hình credential trực tiếp, Java DSL cung cấp dạng tương tự:

```java
Mail.outboundAdapter(smtpHost)
        .port(smtpPort)
        .credentials(smtpUsername, smtpPassword)
        .protocol("smtp")
        .javaMailProperties(properties ->
                properties.put(
                        "mail.smtp.starttls.enable",
                        "true"
                ));
```

Đây là DSL mô tả adapter, không tự gửi mail khi khởi tạo bean. Gửi chỉ xảy ra khi flow nhận message phù hợp và mail handler được kích hoạt.

### Nên chọn injected JavaMailSender khi nào?

Khi đã có một `JavaMailSender` được cấu hình chung trong Spring Boot, cách:

```java
.handle(Mail.outboundAdapter(javaMailSender))
```

thường thuận tiện vì:

- Reuse SMTP host/port, timeout, TLS, authentication policy.
- Dễ thay bằng một sender dùng SMTP test server trong test.
- Có thể quản lý nhiều provider sender beans riêng.
- Tránh cấu hình mail bị phân tán giữa integration flow và application properties.

Không cấu hình đồng thời hai nơi rồi cho rằng chúng chắc chắn đồng nhất. Nếu sender bean và adapter-host DSL mang hai cấu hình khác nhau, cần biết flow thật sự dùng sender nào.

## 16. Cấu hình SMTP trong Spring Boot

Một cách cấu hình `JavaMailSenderImpl` qua Spring Boot:

```yaml
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
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Lưu ý:

- `STARTTLS` và SMTP implicit TLS là hai cách kết nối khác nhau; port và properties phải phù hợp provider.
- Không bật `mail.debug` chứa thông tin nhạy cảm trong production.
- Timeout là ví dụ, cần lựa chọn theo workload và SLA; không giữ worker vô hạn nếu server treo.
- Credentials nên đến từ secret management, không commit vào repository.
- Các thuộc tính cụ thể phải tương thích với thư viện Jakarta Mail/Angus Mail trên classpath.

Khi flow dùng `Mail.outboundAdapter(javaMailSender)`, nó sẽ sử dụng sender đã được cấu hình. **Spring Integration không thay thế yêu cầu cấu hình SMTP chính xác.**

## 17. Cấu hình bằng @ServiceActivator

Spring Integration còn hỗ trợ đặt một `MessageHandler` trên channel bằng annotation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;

@Configuration
public class MailHandlerConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "outboundMail")
    public MessageHandler outboundMailMessageHandler(
            JavaMailSender mailSender
    ) {
        return new MailSendingMessageHandler(mailSender);
    }
}
```

`@ServiceActivator` đăng ký handler để tiêu thụ từ `outboundMail`. `MailSendingMessageHandler` là thành phần thực hiện mapping mail và delegate gửi.

### Java DSL và annotation khác nhau thế nào?

| Cách khai báo | Ưu điểm | Khi dùng |
| --- | --- | --- |
| `@ServiceActivator` + `MailSendingMessageHandler` | Thấy rõ handler và channel trực tiếp | Cấu hình gọn, cần tùy chỉnh handler |
| `IntegrationFlow.from(...).handle(Mail.outboundAdapter(...))` | Dễ đặt enrich/transform/filter/route theo chuỗi | Pipeline có nhiều endpoint |
| XML `int-mail:outbound-channel-adapter` | Phù hợp dự án dùng XML config | Legacy hoặc cấu hình XML hiện có |

**Chọn một cách đăng ký consumer thực sự cho từng mục đích.** Nếu vô tình vừa đăng ký `@ServiceActivator(inputChannel="outboundMail")` vừa đăng ký flow cũng tiêu thụ cùng `DirectChannel`, kết quả không nhất thiết là mỗi message đi qua cả hai. `DirectChannel` có cơ chế dispatch tới subscriber; không nên dựa vào số subscriber để gửi “bản sao” một cách tình cờ.

## 18. XML outbound channel adapter

Với dự án cấu hình XML, dạng thường gặp:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-mail="http://www.springframework.org/schema/integration/mail"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd
         http://www.springframework.org/schema/integration/mail
         https://www.springframework.org/schema/integration/mail/spring-integration-mail.xsd">

    <int:channel id="outboundMail"/>

    <int-mail:outbound-channel-adapter
        channel="outboundMail"
        mail-sender="mailSender"/>
</beans>
```

`mailSender` là bean được khai báo riêng. Trong bài thực hành Java DSL, không cần đồng thời thêm XML này, tránh cấu hình hai endpoint vô tình tiêu thụ cùng channel.

## 19. DirectChannel: synchronous handoff

`DirectChannel` thuộc loại `SubscribableChannel`. Khi một message được gửi vào channel, handler subscriber thường được gọi trên **thread gửi message**.

```text
HTTP request thread
      |
      v
outboundMail.send(message)
      |
      v
DirectChannel dispatch
      |
      v
MailSendingMessageHandler
      |
      v
JavaMailSender.send(...) -> SMTP I/O
      |
      v
Caller receives completion or exception
```

### Ưu điểm

- Dễ hiểu vì flow chạy gần như một call stack đồng bộ.
- Caller có thể nhận exception từ downstream khi gửi thất bại.
- Không cần thread pool riêng nếu lưu lượng nhỏ.
- Debug luồng đơn giản.

### Nhược điểm

- Caller bị giữ trong thời gian tạo/gửi SMTP message.
- Nếu caller là HTTP request, latency phụ thuộc network/provider.
- Nếu nằm trong transaction database, có thể giữ transaction/connection lâu.
- Không tự tạo queue hay khả năng retry bền vững.
- Khi traffic lớn, nhiều request threads có thể cùng gửi mail và tạo áp lực SMTP.

Không nên chọn DirectChannel đồng bộ chỉ vì ít cấu hình mà bỏ qua thời gian SMTP submission trong giao dịch chính.

## 20. QueueChannel: nhận công việc trước, xử lý sau

`QueueChannel` thuộc loại `PollableChannel`. Producer đưa message vào hàng đợi; một **poller** lấy message từ queue rồi gọi mail handler.

```text
Producer thread
     |
     v
QueueChannel (bounded)
     |
     +--> message stored in channel buffer
              |
              v
          Poller thread
              |
              v
       Mail outbound adapter
              |
              v
             SMTP
```

Điều này có thể giảm thời gian chờ của producer, nhưng có rủi ro:

- QueueChannel mặc định thường nằm **trong memory**, không phải durable queue.
- Nếu process restart, message chưa xử lý có thể mất.
- Nếu queue đầy, `send(...)` có thể fail, block theo timeout hoặc bị từ chối tùy cách gọi/cấu hình.
- Một message đã được poll ra khỏi queue không tự trở lại khi SMTP handler ném exception; cơ chế retry/requeue phải được thiết kế.
- Producer nhận `send=true` **không có nghĩa SMTP đã thực hiện**.

### Queue có capacity hữu hạn

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Bean
public PollableChannel queuedMailRequests() {
    return new QueueChannel(100);
}
```

`100` chỉ là giá trị minh họa. Queue capacity nên dựa vào peak load, độ trễ SMTP, RAM và chính sách admission. Không đẩy một mảng `byte[]` attachment hàng chục MiB vào hàng nghìn message đang đợi.

## 21. Poller cho outbound adapter đọc PollableChannel

Khi nguồn của endpoint là một `QueueChannel`, cần một **poller** để kéo message ra. Spring Integration DSL hỗ trợ cấu hình poller tại endpoint:

```java
@Bean
public IntegrationFlow queuedMailFlow(
        PollableChannel queuedMailRequests,
        JavaMailSender mailSender
) {
    return IntegrationFlow.from(queuedMailRequests)
            .handle(
                    Mail.outboundAdapter(mailSender),
                    endpoint -> endpoint.poller(
                            p -> p.fixedDelay(1000)
                                  .maxMessagesPerPoll(5)
                    )
            )
            .get();
}
```

Các giá trị trong ví dụ:

- `fixedDelay(1000)`: minh họa poll theo chu kỳ 1.000 ms.
- `maxMessagesPerPoll(5)`: một lượt poll xử lý tối đa 5 message theo cấu hình.
- Không có nghĩa tối đa 5 SMTP connections toàn hệ thống.
- Không tự bảo đảm exactly-once hay durable delivery.

### Nếu không có poller thì sao?

Đối với một endpoint được gắn với `PollableChannel`, cần có cấu hình poller tương ứng (trực tiếp hoặc cấu hình mặc định phù hợp). Nếu thiếu, endpoint không có cơ chế chủ động lấy message khỏi queue theo cách mong muốn hoặc cấu hình có thể không hợp lệ.

Đây là điểm phân biệt quan trọng với `DirectChannel`, nơi producer đẩy message trực tiếp đến subscribed handler và không cần poller.

## 22. ExecutorChannel: async dispatch qua TaskExecutor

`ExecutorChannel` dùng một `TaskExecutor` để điều phối xử lý sang thread khác:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean
public MessageChannel asyncMailChannel(
        TaskExecutor mailTaskExecutor
) {
    return new ExecutorChannel(mailTaskExecutor);
}
```

Nếu sender xử lý qua channel này:

```text
HTTP thread --> ExecutorChannel
                    |
                    v
                TaskExecutor
                    |
                    v
               Worker thread
                    |
                    v
              SMTP mail handler
```

**Không có poller** theo kiểu QueueChannel, vì ExecutorChannel là subscribable channel dispatch qua executor.

### Điều cần cân nhắc

- SMTP exception trong worker không tự quay về HTTP caller sau khi handoff thành công.
- Error handling phải được cấu hình đúng cho async boundary.
- ThreadPoolTaskExecutor phải có giới hạn, queue capacity và rejection policy.
- ExecutorChannel không tự có database durability.
- Task bị executor từ chối cần được ghi nhận và xử lý, tránh đánh mất notification.
- Transaction context của caller thường **không đi xuyên qua thread boundary** như khi chạy cùng thread.

Nếu email rất quan trọng, một executor trong memory chỉ nên là tầng thực thi; yêu cầu gửi cần được ghi bền vững ở database/outbox hoặc durable broker trước đó.

## 23. So sánh ba channel theo kết quả caller nhìn thấy

| Kênh | Cách giao việc | Caller có chờ SMTP? | Bền vững qua restart? | Error handling |
| --- | --- | --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ trên caller thread | Thường có | Không tự có | Exception downstream thường về caller |
| `ExecutorChannel` | Giao việc cho executor | Thường không sau khi handoff | Không tự có | Xử lý lỗi bất đồng bộ |
| `QueueChannel` | Đặt vào queue cho poller | Không khi chỉ enqueue | In-memory mặc định thì không | Lỗi ở poller/worker, cần policy |

**Chọn channel là chọn semantics xử lý**, không chỉ chọn tên bean. Khi đổi một flow từ DirectChannel sang ExecutorChannel, behavior của exception, transaction, observability và API response có thể thay đổi.

## 24. Không dùng PublishSubscribeChannel để gửi email một cách vô ý

`PublishSubscribeChannel` có thể phát cùng message tới **nhiều subscribers**:

```text
              PublishSubscribeChannel
                 /           \
                v             v
        Mail handler A   Mail handler B
                |             |
                v             v
             SMTP A        SMTP B
```

Đây là cấu trúc phù hợp khi chủ động muốn multicast sự kiện đến nhiều consumer độc lập. Nhưng nếu hai subscriber đều gửi email, một notification có thể được gửi **hai lần**.

Để chọn một trong hai provider SMTP, dùng routing hoặc một route selector rõ ràng, không gắn hai outbound mail adapter vào cùng publish-subscribe channel rồi hy vọng framework tự chọn một.

### DirectChannel nhiều subscribers cũng không phải broadcast

`DirectChannel` dispatch message tới subscriber theo chiến lược của channel. Không dùng việc đăng ký nhiều mail handlers trên một DirectChannel làm cơ chế backup/failover thiếu kiểm soát: kết quả phụ thuộc dispatcher, load balancing và exception behavior. Nếu cần provider routing, nên thiết kế và kiểm thử ở tầng riêng.

## 25. Có cần reply channel không?

Một outbound mail adapter là **one-way consumer**. Thông thường nó không phát một reply message mô tả mail đã delivered.

```text
Input Channel -> Outbound Mail Adapter -> External SMTP
                    |
                    +-- no ordinary reply payload
```

Vì vậy, việc viết request-reply gateway đòi hỏi một `replyChannel` và chờ reply từ adapter là sai mô hình. Nếu cần kết quả nghiệp vụ:

- Dùng submission outcome được bắt ở tầng xử lý gửi.
- Ghi status theo notification/attempt ID vào repository.
- Có thể phát **event trạng thái** riêng sau khi SMTP submit.
- Nhận provider webhook/bounce feedback cho delivery outcome sau đó.

Không tạo reply `DELIVERED` ngay khi `JavaMailSender.send(...)` trả về; đó mới là kết quả submission ở tầng quan sát được.

## 26. Gateway giúp business service không biết MessageChannel

`@MessagingGateway` có thể cung cấp một interface gần giống method Java thông thường nhưng đưa lời gọi vào Spring Integration channel.

```java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "outboundMail")
public interface TextMailGateway {

    void sendText(
            @Payload String text,
            @Header(MailHeaders.TO) String to,
            @Header(MailHeaders.FROM) String from,
            @Header(MailHeaders.SUBJECT) String subject
    );
}
```

Business service:

```java
@Service
public class OrderNotificationService {

    private final TextMailGateway mailGateway;

    public OrderNotificationService(
            TextMailGateway mailGateway
    ) {
        this.mailGateway = mailGateway;
    }

    public void notifyOrder() {
        mailGateway.sendText(
                "Đơn hàng đã xác nhận.",
                "tester@example.net",
                "orders@example.org",
                "Xác nhận đơn hàng"
        );
    }
}
```

Hãy đảm bảo cấu hình component scan/`@IntegrationComponentScan` phù hợp để Spring tạo gateway proxy trong phiên bản dự án. Method `void` minh họa một flow gửi **one-way**, không có ordinary reply payload.

**Quan trọng:** khi dùng DirectChannel, lời gọi gateway có thể bị giữ đến khi SMTP submit hoàn tất; khi dùng async/queue channel, gateway có thể trả về sau handoff. Thay đổi channel có thể thay đổi thời gian phản hồi của business method mà không sửa interface.

## 27. Các lỗi thường gặp khi dùng gateway

| Hiện tượng | Nguyên nhân có thể |
| --- | --- |
| Gateway không được tạo bean | Thiếu component scan/IntegrationComponentScan |
| Không có handler cho channel | Sai tên channel hoặc flow chưa được đăng ký |
| Gateway chờ reply không có | Interface/gateway cấu hình request-reply cho one-way adapter |
| Method trả sớm dù SMTP chưa xong | Async/queue boundary |
| SMTP exception không về caller | Xử lý đang chạy trên worker thread |
| Gửi sai To/Subject | Header mapping hoặc precedence không đúng |
| Dùng DTO phức tạp nhưng body sai | Chưa có transformer/mapper |
| Method gửi mail bị gọi hai lần | Hai luồng nghiệp vụ hoặc retry tạo duplicate |

Gateway giúp **đơn giản hóa interface phía nghiệp vụ**, nhưng không thay thế việc định nghĩa reliability và kết quả gửi.

## 28. Khi dùng async, đâu là nơi ghi nhận trạng thái?

Một pipeline có thể ghi các mốc:

```text
BusinessEvent
      |
      v
Notification stored (PENDING)
      |
      v
Publish to channel / claim
      |
      v
Compose mail (PROCESSING)
      |
      v
Mail outbound adapter -> SMTP
      |
      +-- known success --> SUBMITTED
      |
      +-- known failure --> RETRY_WAIT or FAILED
      |
      +-- uncertain result --> UNKNOWN
```

Để cập nhật status đúng, business service không nên ghi `SUBMITTED` ngay khi một `QueueChannel.send(...)` trả `true`. Cần một worker hoặc tầng giám sát quanh thao tác gửi ghi kết quả khi SMTP submission thực sự được thực hiện.

Khi có nhiều thành phần trong flow, xác định **ai là chủ sở hữu trạng thái** để tránh hai nơi ghi đè status theo những định nghĩa khác nhau.

## 29. Xử lý lỗi với DirectChannel

Với `DirectChannel`, adapter thường chạy trong cùng call stack khi producer gọi `send(...)`. Nếu SMTP transport gặp lỗi, exception có thể lan về caller, đôi khi được Spring Integration bọc trong `MessagingException`.

```java
try {
    outboundMail.send(integrationMessage);
} catch (org.springframework.messaging.MessagingException ex) {
    // Exception từ flow có thể được wrap.
    // Gắn notificationId và phân loại lỗi an toàn.
    recordIntegrationFailure(notificationId, ex);
}
```

Ví dụ minh họa; cần xử lý cả các trường hợp exception từ Spring Mail và những runtime exceptions phù hợp với contract của flow. Không mặc định mọi lỗi đều được bọc đúng một lớp `MessagingException`.

### SMTP failure không giống validation failure

| Lỗi | Giai đoạn có thể phát sinh | Xử lý |
| --- | --- | --- |
| Recipient input sai cú pháp | Validation/transform/compose | Chặn trước adapter |
| Thiếu `MailHeaders.TO` | Mapping/compose | Fail fast, cảnh báo cấu hình |
| Template render exception | Transformer | Không gửi mail thiếu nội dung |
| SMTP authentication error | Mail sender | Sửa credential/config, không retry mù |
| SMTP 4xx tạm thời | Transport | Retry có backoff theo policy |
| SMTP 5xx vĩnh viễn | Transport | Phân loại, sửa recipient/policy |
| Timeout sau DATA | Transport | Outcome có thể `UNKNOWN` |
| Executor/Queue rejection | Channel/admission | Không được báo submitted |

Tránh một `catch (Exception)` rồi luôn retry cùng message mà không biết nó đã được SMTP server chấp nhận hay chưa.

## 30. Xử lý lỗi bất đồng bộ

Khi message đi qua `ExecutorChannel` hoặc poller của `QueueChannel`, caller có thể đã nhận kết quả “channel accepted” từ lâu. Exception phát sinh trong mail handler **không tự quay ngược về HTTP caller**.

```text
HTTP request
   |
   v
ExecutorChannel.submit()
   |
   +--> HTTP returns ACCEPTED
                |
                v
         Worker executes mail handler
                |
                +--> SMTP exception
                         |
                         v
                   Async error path
```

Spring Integration có cơ chế `errorChannel`/`ErrorMessage` để xử lý lỗi bất đồng bộ, nhưng cách publish lỗi còn phụ thuộc channel, poller, task executor và endpoint error handler được cấu hình. Không nên mặc định mọi exception đều tự xuất hiện ở một channel mà không có người lắng nghe.

### Một error handler đơn giản

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class MailErrorConsumer {

    @ServiceActivator(inputChannel = "mailErrors")
    public void consume(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();

        // Ghi loại lỗi/correlation ID đã được kiểm soát.
        // Không log toàn bộ failedMessage, body hay recipient.
        recordMailFailureClass(
                failure.getClass().getSimpleName()
        );
    }
}
```

`recordMailFailureClass(...)` là method minh họa. Để handler thực sự nhận được lỗi, cần **cấu hình error channel của async flow/poller** hoặc route `ErrorMessage` tới channel `mailErrors` theo API phiên bản đang dùng. Chỉ khai báo `@ServiceActivator` ở trên chưa đủ để bảo đảm mọi lỗi SMTP đều được đưa đến đó.

### Khi error handler lại lỗi

Nếu error handler ném exception hoặc không thể ghi database, bạn cần một chiến lược vận hành rõ ràng. Có thể dùng durable event/outbox và retry processing để không mất notification; không xử lý lỗi bằng cách lặp lại SMTP send ngay tại error channel nếu chưa phân loại outcome.

## 31. ErrorMessage có thể chứa thông tin nhạy cảm

Một lỗi Spring Integration có thể kèm reference tới `failedMessage`. Payload/headers của nó có thể chứa:

- Recipient To/Cc/Bcc.
- Tên hoặc nội dung khách hàng.
- OTP/magic link/reset token.
- Attachment bytes hoặc resource path.
- Internal correlation metadata.

Không làm:

```java
logger.error(
        "Mail failed: {}", errorMessage
);
```

và không tự serialize nguyên `failedMessage` vào monitoring event. Tốt hơn là log `notificationId`/`attemptId` nội bộ, error type, SMTP stage nếu có bằng chứng, provider route và outcome.

### Mẫu diagnostic tối thiểu

```text
notificationId=N-400-123
attemptId=A-400-001
channel=outboundMail
stage=SMTP_SUBMISSION
exceptionClass=MailSendException
outcome=UNKNOWN
```

Không đoán `outcome=FAILED` khi timeout có thể xảy ra sau khi server đã nhận DATA. Classification phải dựa vào ngữ cảnh vận hành.

## 32. Exception từ MailSendingMessageHandler có tự chứa trạng thái delivery không?

Không. Adapter delegate cho `JavaMailSender`, trong khi `MailSendException`, `MailAuthenticationException` và các exception transport chỉ mô tả lỗi quan sát trong quá trình build/submit.

Một `MailSendException` có thể chứa:

- Danh sách message object bị lỗi ở cấp attempt.
- Nested exceptions từ Jakarta Mail.
- Một số thông tin recipient hợp lệ hoặc bị từ chối nếu transport cung cấp.

Nhưng:

- Một message có thể có nhiều SMTP recipients.
- Một recipient đã được `250` tại RCPT không nhất thiết đã nhận DATA.
- `sendpartial=true` có thể khiến một phần recipient đã được submit trong khi handler vẫn ném exception.
- Timeout sau DATA tạo trạng thái không chắc chắn.
- SMTP submission thành công không có nghĩa email đã tới Inbox.

Vì thế, outbound adapter cần đi cùng một **status management layer** nếu sản phẩm có retry hoặc SLA.

## 33. Đừng dùng queue trong memory làm durable mail outbox

Một kiến trúc dễ mắc lỗi:

```text
OrderService updates database
       |
       v
QueueChannel with in-memory queue
       |
       +--> Process crashes before poll
       |
       v
Email request is lost
```

Ngay cả khi `QueueChannel.send(...)` trả `true`, điều đó chỉ chứng minh message đã được nhận bởi channel tại thời điểm đó, **không có bảo đảm lưu qua restart** nếu channel không có durable store tương ứng.

### Khi nào QueueChannel đủ?

- Demo hoặc ứng dụng thử nghiệm.
- Email không quan trọng, chấp nhận được việc mất task khi restart.
- Pipeline có nguồn durable upstream có thể phát lại theo policy.
- Workload mà mất một thông báo không gây hậu quả nghiệp vụ.

Với email giao dịch quan trọng, cần suy nghĩ về **transactional outbox**, durable queue hoặc một cơ chế persistence có confirmation và retry. Spring Integration có các message store/channel adapter khác, nhưng phải cấu hình đúng contract chứ không chỉ đổi tên channel.

## 34. Transactional outbox cùng Spring Integration

Một kiến trúc tham khảo:

```text
Business transaction
  UPDATE order
  INSERT mail_notification(PENDING)
          |
          v
        COMMIT
          |
          v
Outbox dispatcher / poller
          |
          v
MessageChannel (carries notification ID / DTO)
          |
          v
Load data + validate + compose
          |
          v
Outbound Mail Adapter
          |
          v
SMTP submission
          |
          v
Persist attempt outcome
```

Trong thiết kế này, channel có thể được dùng để **tổ chức flow** còn database/outbox bảo đảm yêu cầu gửi không mất khi process restart.

### Gợi ý dữ liệu outbox

```text
notification_id
recipient_id
template_key
template_version
data_reference
status = PENDING / PROCESSING / SUBMITTED /
         RETRY_WAIT / FAILED / UNKNOWN
attempt_count
next_attempt_at
created_at
```

Không bắt buộc lưu raw HTML/MIME hoặc attachment bytes trong database. Có thể lưu tham chiếu tới dữ liệu bền vững, với điều kiện nội dung không bị xóa hoặc thay đổi trái ý nghĩa giữa các attempts.

## 35. Không giữ database transaction mở trong khi gửi SMTP

Ví dụ dễ gây vấn đề:

```java
@Transactional
public void processMail(UUID notificationId) {
    Notification n = repository.findById(
            notificationId
    ).orElseThrow();

    // Thao tác I/O mạng có thể tốn nhiều giây.
    outboundMail.send(toIntegrationMessage(n));

    n.markSubmitted();
}
```

Nếu `outboundMail` là `DirectChannel`, lệnh `send(...)` có thể gọi SMTP ngay trong transaction DB. Điều này giữ JDBC connection/locks lâu, và rollback DB **không thể thu hồi email đã được SMTP chấp nhận**.

Nên phân tách:

1. Claim notification trong một transaction ngắn.
2. Load/render/submit ở ngoài transaction dài.
3. Record outcome trong transaction ngắn khác.
4. Có cơ chế xử lý crash giữa SMTP acceptance và cập nhật DB.

Đây là trade-off reliability, không được giải quyết chỉ bằng cách thay `DirectChannel` thành `ExecutorChannel`.

## 36. Cơ chế retry: nơi nào nên sở hữu?

Có nhiều tầng có thể retry:

- Spring Integration advice/retry quanh handler.
- Poller error handling và requeue.
- Worker/outbox scheduler.
- SMTP provider tự retry delivery sau khi đã accepted.

Nếu tất cả đều retry mà không phối hợp, một notification có thể được gửi nhiều lần.

### Nguyên tắc

1. Có **một owner** chịu trách nhiệm retry submission theo notification/attempt.
2. Ghi từng attempt ID, recipient scope và provider route.
3. Phân loại lỗi chắc chắn chưa submit với outcome mơ hồ.
4. Không retry nguyên batch nếu một phần đã được gửi.
5. Tôn trọng suppression và unsubscribe policy.
6. Đặt max attempts, backoff và jitter.
7. Không coi `Message-ID` là khóa dedup chung của SMTP.
8. Chỉ bật retry advice khi behavior thực tế phù hợp với policy.

### Ví dụ retry policy ở tầng nghiệp vụ

```text
Mail handler failure
      |
      v
Classify:
  connection failed before submission -> RETRY_WAIT
  temporary SMTP 4xx (known)          -> RETRY_WAIT
  invalid recipient / permanent       -> FAILED
  timeout after DATA                  -> UNKNOWN
      |
      v
Persist outcome
      |
      v
Outbox worker schedules next attempt if allowed
```

Khi dùng retry advice của Spring Integration, hãy kiểm tra khả năng retry quá gần với SMTP side effect: nếu bước gửi trước đó thực ra đã được server nhận nhưng client không nhận phản hồi, tự gọi lại handler có thể tạo duplicate.

## 37. Rate limit và backpressure trên message channel

SMTP provider có thể giới hạn:

- Message/giây.
- Recipient/message.
- Số kết nối đồng thời.
- Kích thước MIME.
- Quota theo account/domain.
- Tần suất AUTH hoặc session.

Channel choice ảnh hưởng cách hệ thống phản ứng với quá tải:

| Channel | Dấu hiệu quá tải | Biện pháp |
| --- | --- | --- |
| DirectChannel | Caller/request thread bị giữ lâu | Tách durable scheduling, giảm gửi đồng bộ |
| ExecutorChannel | Executor queue tăng, task bị reject | Bounded pool, backpressure, admission |
| QueueChannel | Capacity đạt giới hạn, poller không theo kịp | Bounded capacity, xử lý rejection |
| Durable broker/outbox | Lag/backlog tăng | Scale workers theo quota, alert queue age |

Một email kèm PDF 20 MiB có chi phí không giống email text 1 KiB. Đừng chỉ đếm số message đang chờ khi dimension kích thước có thể gây heap, disk và network pressure.

### Không thêm worker vô hạn

Nếu SMTP provider chỉ cho tối đa một số kết nối hoặc throughput, tăng số worker quá mức có thể tạo `421/4xx`, timeout, retry storm và giảm tỷ lệ gửi thành công. Hãy đặt giới hạn theo tài nguyên thực và đo queue lag, error rate, submit latency.

## 38. Payload quá lớn trong QueueChannel

Một anti-pattern:

```java
record MailWork(
        UUID notificationId,
        String recipient,
        byte[] invoicePdf
) {}
```

Nếu một queue có 1.000 task, mỗi task giữ 10 MiB PDF độc lập, chỉ các mảng byte đã chiếm khoảng 10.000 MiB trong memory, chưa tính MIME và object khác.

Phương án khác:

```java
record MailWorkReference(
        UUID notificationId,
        UUID recipientId,
        String attachmentStorageKey
) {}
```

Worker tải tệp khi đến lượt, đảm bảo nguồn đọc lại được và tồn tại qua retry. Tuy nhiên, storage key phải được bảo vệ và trỏ tới nội dung bất biến/phiên bản xác định; không tự động lưu dữ liệu nhạy cảm ở URL công khai.

## 39. Header filter và bảo mật

Trong integration flow, message có thể đến từ HTTP, JMS, Kafka hoặc các hệ thống khác. Nếu copy tất cả headers vào outbound mail adapter, dữ liệu không tin cậy có thể can thiệp:

- `MailHeaders.TO`, `BCC`: thay người nhận, lộ thông tin.
- `MailHeaders.FROM`: giả mạo sender domain.
- `MailHeaders.REPLY_TO`: hướng phản hồi sang địa chỉ xấu.
- `MailHeaders.SUBJECT`: chèn giá trị không mong muốn.
- Correlation headers chứa access token hoặc dữ liệu nội bộ.

### Nguyên tắc kiểm soát

- Chỉ cho phép header mail được tạo bởi code đã xác thực và validate.
- Không nhận `From` tùy ý từ HTTP request nếu policy chỉ cho sender domain cụ thể.
- Bcc phải được xử lý theo quyền và mục đích.
- Đừng echo tất cả headers vào email body hoặc MIME.
- Giới hạn độ dài subject, recipient count, attachment size.
- Không dùng message headers như nơi lưu password/token lâu dài.
- Áp dụng escaping đối với HTML tại template layer.

**Header Enricher không phải cơ chế bảo mật tự động.** Nó chỉ đặt hoặc tính giá trị; ứng dụng phải xác định nguồn dữ liệu nào đáng tin.

## 40. Mail outbound adapter và MIME phức tạp

Text mail có thể xử lý gọn bằng `String` và `MailHeaders`. Nhưng HTML, plain-text alternative, inline image và attachment đa phần cần logic MIME riêng.

```text
OrderMailCommand
       |
       v
HTML template renderer
       |
       v
MimeMessageHelper:
  setText(plain, html)
  addInline(contentId, resource)
  addAttachment(name, resource)
       |
       v
MimeMessage
       |
       v
JavaMailSender.send(MimeMessage)
```

Đừng kỳ vọng `String` có HTML tags được outbound handler tự thêm multipart/related, CID, Content-Type hoặc attachment theo nghiệp vụ.

### Khi nên dùng custom handler cho MimeMessage

Nếu flow đã dựng `jakarta.mail.internet.MimeMessage`, một cách rõ contract là viết handler riêng gọi `JavaMailSender.send(MimeMessage)`:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;

@Bean
public MessageHandler preparedMimeHandler(
        JavaMailSender sender
) {
    return integrationMessage -> {
        Object payload = integrationMessage.getPayload();
        if (!(payload instanceof MimeMessage mime)) {
            throw new IllegalArgumentException(
                    "Expected MimeMessage payload"
            );
        }
        sender.send(mime);
    };
}
```

Sau đó:

```java
@Bean
public IntegrationFlow preparedMimeFlow(
        MessageHandler preparedMimeHandler
) {
    return IntegrationFlow.from("preparedMimeMail")
            .handle(preparedMimeHandler)
            .get();
}
```

**Phân biệt rõ:** đây là một **custom outbound MessageHandler trong Spring Integration**, không phải lời khẳng định rằng mọi version của `MailSendingMessageHandler` tự động nhận mọi dạng `MimeMessage` payload qua cùng mapping. Khi yêu cầu là MIME phức tạp, dùng một transformer/handler với contract tường minh sẽ dễ kiểm thử hơn.

### Chú ý thread-safety

`MimeMessage` là mutable. Không truyền cùng một instance qua nhiều thread rồi đồng thời sửa subject/recipient/attachment. Nếu queue bất đồng bộ, hãy để worker sở hữu việc dựng và gửi MIME cho từng notification/attempt.

## 41. Một flow rõ ràng: DTO → header enricher → text → mail adapter

Ta có thể kết hợp các thành phần chính:

```text
OrderMailCommand
       |
       v
mailCommands (DirectChannel)
       |
       v
Header Enricher
  - TO từ recipient đã validate
  - FROM từ địa chỉ hệ thống
  - SUBJECT từ orderCode
       |
       v
Transformer
  OrderMailCommand -> String
       |
       v
Mail Outbound Adapter
       |
       v
SMTP test/sandbox
```

Ví dụ Java DSL:

```java
@Bean
public IntegrationFlow orderTextMailFlow(
        JavaMailSender mailSender
) {
    return IntegrationFlow.from("mailCommands")
            .enrichHeaders(h -> h
                    .headerExpression(
                            MailHeaders.TO,
                            "payload.recipient"
                    )
                    .header(
                            MailHeaders.FROM,
                            "orders@example.org"
                    )
                    .headerExpression(
                            MailHeaders.SUBJECT,
                            "'Xác nhận ' + payload.orderCode"
                    ))
            .transform(
                    OrderMailCommand.class,
                    command -> "Đơn hàng "
                            + command.orderCode()
                            + " đã được xác nhận."
            )
            .handle(Mail.outboundAdapter(mailSender))
            .get();
}
```

`OrderMailCommand` là record đã khai báo ở phần trước, có accessors `recipient()` và `orderCode()`. Trong Spring Expression Language (SpEL), khả năng truy cập property của record phụ thuộc phiên bản Spring/SpEL; nếu một project không resolve được `payload.recipient` hoặc `payload.orderCode`, hãy dùng cú pháp gọi accessor tương ứng hoặc một transformer/enricher Java thuần rõ ràng. Code phải được đối chiếu với version thực tế của Spring Integration và Spring Framework.

### Vì sao enrich trước transform?

Ở đầu flow, payload là `OrderMailCommand` nên có `recipient` và `orderCode`. Sau khi transform, payload là `String` nội dung mail, không còn các property đó. Nếu đặt `headerExpression("payload.recipient")` sau bước transform, biểu thức sẽ không tìm thấy field.

Vì vậy, thứ tự endpoint không chỉ là chuyện trình bày:

```text
DTO -> enrich headers -> render body -> send
```

và

```text
DTO -> render body -> enrich from DTO properties -> send
```

không tương đương trừ khi bạn đã chủ động giữ thông tin DTO ở header hoặc context riêng.

## 42. Lựa chọn transformer cho DTO phức tạp

Một flow email thực tế thường có các bước:

1. Validate notification status và recipient eligibility.
2. Chọn template version.
3. Load dữ liệu đã được snapshot hoặc có version.
4. Render plain/HTML.
5. Tạo attachment hoặc tham chiếu immutable resource.
6. Build mail message.
7. Submit bằng mail sender.

Transformer là nơi chuyển **dạng dữ liệu**, không nhất thiết là nơi thực hiện mọi side effect. Khi mỗi bước có hợp đồng rõ:

- Unit test transformer chỉ kiểm tra dữ liệu render.
- Test mail composer kiểm tra MIME/headers.
- Test outbound adapter kiểm tra submission.
- Integration test kiểm tra toàn flow với SMTP sandbox.

Không biến một transformer thành một service vừa trừ tiền, vừa cập nhật database, vừa gửi mail. Khi flow bị retry, các side effect ấy có thể chạy lặp.

## 43. Router giữa hai outbound mail adapters

Nếu ứng dụng có nhiều provider hoặc các nhóm email khác nhau, có thể routing trước adapter:

```text
mailRequests
      |
      v
Select route
  |
  +---- providerAChannel ---> Adapter A ---> SMTP A
  |
  +---- providerBChannel ---> Adapter B ---> SMTP B
```

Khi thiết kế:

- Route phải được chọn từ danh sách approved providers.
- Ghi `providerKey` và `attemptId` trước khi gửi.
- Mỗi outgoing route có sender/credentials riêng.
- Không routing bằng dữ liệu user tùy ý dẫn đến SMTP host attacker-controlled.
- Không multicast cùng notification sang A/B chỉ để “dự phòng” nếu không chấp nhận duplicate.
- Không failover tự động một attempt có kết quả SMTP `UNKNOWN`.

### Ví dụ cấu hình hai flow nhận từ hai channel

```java
@Bean
public IntegrationFlow providerAMailFlow(
        JavaMailSender providerASender
) {
    return IntegrationFlow.from("providerAMail")
            .handle(Mail.outboundAdapter(providerASender))
            .get();
}

@Bean
public IntegrationFlow providerBMailFlow(
        JavaMailSender providerBSender
) {
    return IntegrationFlow.from("providerBMail")
            .handle(Mail.outboundAdapter(providerBSender))
            .get();
}
```

Tên `providerAMail` và `providerBMail` là các channel endpoint của Spring Integration. Routing logic phải chuyển đúng một message đến channel được chọn và theo dõi attempt.

## 44. Không nhầm channel router với SMTP retry/failover

Một router chọn **đường gửi của message chưa thử**. Một retry/failover quyết định xử lý **attempt đã có kết quả lỗi hoặc mơ hồ**.

```text
Routing trước gửi:
  Notification N -> choose A -> Attempt 1 on A

Failover sau gửi:
  Attempt 1 on A -> error classification
                   |
                   +--> Retry approved? -> Attempt 2 on B
```

Nếu A đã nhận DATA nhưng ứng dụng mất phản hồi cuối, retry trên B có thể gửi trùng. Do đó flow routing không được tự biến một `MailSendException` bất kỳ thành “hãy gửi tiếp qua B”.

Phần lớn provider tiếp tục retry delivery sau khi đã accepted, vì vậy nhận event deferred cũng không mặc định là lý do để submit cùng email qua provider khác.

## 45. Theo dõi message tại các ranh giới channel

Các mốc quan sát hữu ích:

| Mốc | Có thể đo | Không được suy ra |
| --- | --- | --- |
| Producer tạo request | Notification count | SMTP đã được gọi |
| Channel nhận message | Channel acceptance / queue depth | Email đã sent |
| Poller lấy message | Queue wait time | SMTP đã accepted |
| Transformer hoàn tất | Render duration | MIME sẽ hợp lệ trên mọi client |
| Adapter bắt đầu | Submission attempt start | Email sẽ delivered |
| Mail sender return | Submission duration/result | Inbox arrival |
| Provider delivery webhook | Remote-delivered/bounce nếu có | Người dùng đã đọc |

Đừng dùng một tên metric `mail_sent_total` cho cả enqueue và SMTP accepted; nếu không, dashboard có thể báo số “đã gửi” cao hơn thực tế khi queue backlog.

### Đặt tên metric rõ ràng

```text
mail.notifications.created
mail.channel.enqueued
mail.channel.rejected
mail.adapter.attempted
mail.smtp.submitted
mail.smtp.failed
mail.smtp.unknown
mail.queue.oldest.age
mail.provider.remote.delivered
```

Các metric tên trên là gợi ý do ứng dụng định nghĩa, không phải tên tự động của Spring Integration. Một endpoint có thể cung cấp framework metrics tùy cấu hình; nên phân biệt framework metric và business outcome metric.

## 46. Monitoring và tracing trong IntegrationFlow

Một request có thể đi qua nhiều endpoint:

```text
HTTP / Event source
      |
      v
Inbound Gateway
      |
      v
Transformer
      |
      v
outboundMail channel
      |
      v
Mail Adapter
      |
      v
SMTP
```

Khi ghi trace:

- Dùng `notificationId` hoặc một opaque correlation ID.
- Ghi route, stage và latency phù hợp.
- Giới hạn label cardinality và retention.
- Không dùng recipient email, Subject, Bcc hoặc OTP làm trace attributes.
- Không log toàn bộ Integration Message vì payload có thể chứa nội dung/attachment.

### WireTap chỉ quan sát, không biến thành SMTP duplicate

Trong Spring Integration, `wireTap` có thể gửi một bản message sang một channel phụ để quan sát:

```text
outboundMail channel
      |
      +-- tap --> metrics/diagnostic handler
      |
      +--------> mail adapter
```

Tuy nhiên, nếu channel phụ cũng nối tới outbound mail adapter, bạn có thể vô tình gửi bản email thứ hai. Chỉ dùng wire tap cho **metadata được kiểm soát**, tránh lưu body/header nhạy cảm và không làm observation ảnh hưởng latency hay kết quả gửi.

## 47. Test 1: Channel + handler, không cần SMTP thật

Để kiểm thử flow routing ở cấp channel, có thể thay mail handler bằng một consumer test thu thập message.

```java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class DirectChannelRoutingTest {

    @Test
    void deliversMessageToSubscribedHandler() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> observed =
                new AtomicReference<>();

        channel.subscribe(observed::set);

        Message<String> message = MessageBuilder
                .withPayload("Nội dung thử nghiệm")
                .build();

        assertTrue(channel.send(message));
        assertNotNull(observed.get());
        assertEquals(
                "Nội dung thử nghiệm",
                observed.get().getPayload()
        );
    }
}
```

Test này kiểm tra behavior dispatch của `DirectChannel`, **không kiểm tra mail adapter hoặc SMTP**. Nó có giá trị khi phát triển transformer/headers/filter/routing trước khi nối tới sender thật.

## 48. Test 2: MailSendingMessageHandler gửi qua SMTP local

Một integration test có thể tạo `MailSendingMessageHandler` bằng `JavaMailSenderImpl` và gắn vào `DirectChannel`, sau đó gửi một `Message<String>` chứa `MailHeaders`.

Ví dụ dùng **GreenMail** làm SMTP test server:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailHeaders;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OutboundMailAdapterIntegrationTest {

    @Test
    void sendsToLocalSmtpServer() throws Exception {
        GreenMail greenMail = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1", "smtp"
                )
        );
        greenMail.start();

        try {
            JavaMailSenderImpl sender = new JavaMailSenderImpl();
            sender.setHost("127.0.0.1");
            sender.setPort(greenMail.getSmtp().getPort());

            DirectChannel channel = new DirectChannel();
            channel.subscribe(
                    new MailSendingMessageHandler(sender)
            );

            boolean accepted = channel.send(
                    MessageBuilder.withPayload(
                            "Đây là email thử nghiệm."
                    )
                    .setHeader(
                            MailHeaders.TO,
                            "tester@example.net"
                    )
                    .setHeader(
                            MailHeaders.FROM,
                            "notify@example.org"
                    )
                    .setHeader(
                            MailHeaders.SUBJECT,
                            "Mail Integration Test"
                    )
                    .build()
            );

            assertTrue(accepted);
            assertTrue(
                    greenMail.waitForIncomingEmail(5000, 1)
            );

            MimeMessage[] received =
                    greenMail.getReceivedMessages();
            assertTrue(received.length >= 1);
            assertEquals(
                    "Mail Integration Test",
                    received[0].getSubject()
            );
        } finally {
            greenMail.stop();
        }
    }
}
```

Test cần thêm GreenMail dependency tương thích với namespace Jakarta Mail của dự án. API và overload có thể khác theo phiên bản; ví dụ minh họa cách tổ chức test, không mặc định đã chạy qua test suite của dự án.

### Test chứng minh gì?

- DirectChannel gửi message đến subscribed mail handler.
- Handler map text payload + mail headers và gọi sender.
- Sender có thể submit đến SMTP test server cục bộ.
- SMTP server test nhận một thư có Subject kỳ vọng.

Nó không chứng minh Gmail/Outlook sẽ hiện đúng format, cũng không chứng minh email đã tới Inbox của một người thật.

## 49. Test 3: kiểm tra MailHeaders precedence

Một tình huống cần test:

```text
SimpleMailMessage payload:
  To = first@example.net

Integration Message:
  MailHeaders.TO = second@example.net
```

Kỳ vọng theo mapping được mô tả trong tài liệu Spring Integration là header `MailHeaders.TO` có ưu tiên đối với thuộc tính To.

Ý tưởng kiểm thử:

1. Tạo `SimpleMailMessage` với recipient A.
2. Bọc nó trong `Message<?>` có `MailHeaders.TO` = B.
3. Gửi qua handler đến SMTP test server.
4. Ghi nhận **SMTP RCPT TO** hoặc recipient đã nhận để xác nhận là B.
5. Kiểm tra A không được gửi theo chính sách mong muốn.

Với test này, chỉ đọc Subject có thể không phát hiện lỗi mapping. Cần quan sát **recipient thực tế của SMTP envelope**; header `To` chưa luôn đủ để chứng minh lệnh RCPT đã được gửi cho đúng người.

## 50. Test 4: QueueChannel không đồng nghĩa đã submit

Một unit test có thể tạo `QueueChannel` và **không kết nối poller**, sau đó:

```java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel channel = new QueueChannel(2);

Message<String> request = MessageBuilder
        .withPayload("Email test chưa được gửi")
        .build();

boolean enqueued = channel.send(request);

assertTrue(enqueued);
assertEquals(1, channel.getQueueSize());
```

Ví dụ này cho thấy message có thể nằm trong channel mà chưa có email nào được submit. Trong test thật, poller sẽ lấy message và kích hoạt handler; lúc ấy mới có SMTP submission attempt.

Đừng viết API HTTP trả “mail delivered” ngay khi `QueueChannel.send(...)` trả `true`.

## 51. Test 5: lỗi async không về caller

Một test dành cho `ExecutorChannel` nên chứng minh:

- Message có thể được handoff sang executor.
- Handler chạy trên thread khác theo executor configuration.
- SMTP exception không được xem như kết quả đồng bộ của HTTP caller.
- Error channel/handler được cấu hình để nhận thất bại.
- Notification status được cập nhật sau khi worker xử lý.
- Executor rejection được xử lý khi queue đầy.

Đừng dùng `Thread.sleep(...)` cố định để chờ; sử dụng `CountDownLatch`, `CompletableFuture` hoặc test framework helper với timeout hữu hạn. Nếu test quá phụ thuộc thread scheduling, nó sẽ flaky trên CI.

## 52. Test 6: gửi email MIME phức tạp

Khi dùng custom handler cho `MimeMessage`:

1. Dùng `JavaMailSender.createMimeMessage()` tạo email thử.
2. Dùng `MimeMessageHelper` với `MULTIPART_MODE_MIXED_RELATED`.
3. Gọi `setText(plain, html)`, `addInline(...)` và `addAttachment(...)`.
4. Đưa `MimeMessage` vào một channel dành riêng cho prepared MIME.
5. Test SMTP server nhận email; parse MIME tree.
6. Kiểm tra part `text/plain`, `text/html`, `multipart/related` và attachment.
7. Đọc decoded bytes của attachment/inline để so với fixture.

### Phải giữ resource đủ lâu

`FileSystemResource` và `InputStreamSource` có thể chỉ được đọc trong lúc serialize/send. Nếu một producer tạo file tạm, đưa MimeMessage vào async channel rồi xóa file ngay sau `channel.send(...)`, worker có thể gặp attachment missing.

Đối với async flow, tốt hơn để worker tải dữ liệu/compose MIME từ **immutable storage reference** trong đúng attempt, tránh truyền một `MimeMessage` mutable mang tham chiếu file dễ mất qua nhiều tầng.

## 53. Test 7: retry và không gửi trùng

Một test quan trọng về reliability:

```text
Attempt 1:
  SMTP test server receives all DATA
  Server closes without final 250 reply
  Application sees timeout / unknown

Expected:
  status = UNKNOWN
  no blind immediate second send
  no automatic fallback to another provider
```

Test khác khi connection bị từ chối **trước** SMTP submit có thể kiểm tra policy retry thích hợp.

Không nên kết hợp mọi lỗi dưới `catch (MailException) -> channel.send(original)`. Với email có nhiều recipient và `sendpartial=true`, một phần có thể đã submit trong khi handler vẫn ném exception.

## 54. Test 8: không bị trùng consumer

Nếu hệ thống vô tình đăng ký hai mail handlers:

```text
outboundMail -> Mail handler A
outboundMail -> Mail handler B
```

Một test cần xác minh **số lần SMTP DATA được chấp nhận** tương ứng số notification dự định gửi, không phải số subscribers được đăng ký. Với `PublishSubscribeChannel`, một message có thể đi tới cả A và B; với `DirectChannel`, dispatcher có thể chọn một subscriber thay vì broadcast.

Đừng coi việc có hai mail handlers trên một channel là cơ chế HA/retry mặc định. Thiết kế producer, router và consumer ownership rõ ràng hơn.

## 55. Quản lý lifecycle của IntegrationFlow

Spring Integration endpoint có lifecycle trong application context. Trong nhiều cấu hình, endpoint tự start khi Spring context khởi động; trong một số trường hợp bạn có thể chủ động điều khiển startup, nhất là khi provider chưa sẵn sàng hoặc cần thực hiện maintenance.

### Vì sao cần quan tâm?

- Một poller có thể bắt đầu lấy task ngay khi service start.
- Nếu SMTP config sai, worker có thể tạo hàng loạt lỗi ngay khi deploy.
- Khi shutdown, những task đang chạy phải được xử lý theo chính sách.
- Một endpoint stop không tự đồng nghĩa các message in-memory đã được lưu bền vững.
- Nếu nhiều instance chạy cùng một outbox, cần claim/lease chống xử lý đồng thời.

Endpoint lifecycle và nghiệp vụ notification lifecycle là hai phần riêng. Đừng lấy `autoStartup=false` làm một cơ chế “tạm lưu mail an toàn” khi queue vẫn chỉ ở memory.

## 56. Graceful shutdown

Một outbound mail flow có thể đang gửi attachment lớn khi ứng dụng nhận tín hiệu shutdown.

```text
Shutdown begins
      |
      v
Stop accepting new work
      |
      v
Wait for in-flight tasks within configured bound
      |
      +-- completed -> record SUBMITTED or FAILED
      |
      +-- interrupted/timeout -> record UNKNOWN or reclaim lease
      |
      v
Release executor / sockets / resources
```

Với SMTP send, stop thread không thể “rollback” một message mà mail server đã nhận. Nếu process chết sau DATA nhưng trước khi cập nhật database, worker khác có thể không biết kết quả thực và retry gây duplicate.

Do đó:

1. Có request admission control khi shutdown.
2. Đừng nhận thêm vô hạn notification mới.
3. Dùng durable outbox/lease expiration cho task đang xử lý.
4. Ghi stage và attempt ID.
5. Chỉ requeue chắc chắn an toàn theo policy.
6. Có reconciliation cho trạng thái không rõ.

## 57. Bcc trong flow: khác nhau giữa headers và SMTP recipients

`MailHeaders.BCC` là metadata giúp adapter dựng danh sách recipient ẩn. Nhưng điều này không phải lý do để đưa Bcc vào logs hoặc dashboard mở rộng.

```java
Message<String> request = MessageBuilder
        .withPayload("Bản tin thử nghiệm")
        .setHeader(
                MailHeaders.TO,
                "primary@example.net"
        )
        .setHeader(
                MailHeaders.BCC,
                "audit@example.net"
        )
        .setHeader(
                MailHeaders.FROM,
                "notice@example.org"
        )
        .setHeader(
                MailHeaders.SUBJECT,
                "Bản tin"
        )
        .build();
```

Khi kiểm thử:

- Kiểm tra SMTP test server nhìn thấy recipient Bcc ở `RCPT TO`.
- Kiểm tra MIME gửi tới người nhận không làm lộ header Bcc theo hành vi thực tế.
- Không dựa chỉ vào một `Message<String>` trước mapping để kết luận về wire representation.
- Không log toàn bộ message hoặc failed message khi exception xảy ra.

Với notification cá nhân hóa cần bảo mật danh sách người nhận, cân nhắc một message/recipient thay vì gom nhiều To/Cc.

## 58. Correlation ID không tự là Message-ID của email

Một Integration Message thường có headers:

```text
id = UUID of Spring Message
timestamp = ...
correlationId = custom value (nếu ứng dụng đặt)
```

Một email SMTP/MIME có:

```text
Message-ID: <...>
Date: ...
From: ...
To: ...
Subject: ...
```

Hai miền này không mặc định được đồng bộ. `MessageHeaders.ID` dùng trong pipeline không phải `MimeMessage.getMessageID()` và cũng không chắc là ID mà provider trả về trong webhook.

Khi tracking:

- `notificationId` định danh yêu cầu nghiệp vụ.
- `attemptId` định danh một lần thử SMTP/provider.
- `providerMessageId` nếu provider trả về và có contract.
- `MimeMessage Message-ID` có thể là thông tin hỗ trợ, không phải khóa duy nhất cho mọi trường hợp.

Đừng lấy subject hoặc email address làm correlation key vì dễ trùng và có nguy cơ lộ dữ liệu.

## 59. Không mặc định mọi handler chạy đúng một lần

Ngay cả khi business event được tạo một lần, notification có thể được xử lý lại vì:

- Poller hoặc worker restart.
- Database transaction commit chậm sau SMTP submission.
- Error channel retry.
- Message broker redelivery.
- Manual requeue.
- Mất kết nối sau DATA.
- Failover giữa SMTP providers.

`MessageChannel` và outbound adapter không cung cấp một **global exactly-once SMTP send contract**. Nếu sản phẩm cần giảm duplicate:

- Ghi notification ID và attempt history.
- Có idempotent claim/lease với durable store.
- Tránh gửi cùng notification đang `PROCESSING` song song.
- Không retry `UNKNOWN` tự động khi chưa đánh giá rủi ro.
- Bắt buộc có business policy cho resend.
- Giữ audit của manual retry.

Đừng chỉ thêm `synchronized` trong một instance rồi cho rằng cả cluster không thể gửi trùng; nhiều instance có các JVM độc lập.

## 60. Khi nào không cần Spring Integration Mail?

Không phải mọi hệ thống đều có lợi khi dùng channel adapter.

Nếu nhu cầu là một method service:

```java
public void sendWelcome(String address) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(address);
    message.setFrom("welcome@example.org");
    message.setSubject("Chào mừng");
    message.setText("Cảm ơn bạn đã đăng ký.");
    mailSender.send(message);
}
```

và không cần routing, transform pipeline, async handoff, channels hoặc phối hợp nhiều hệ thống, cách gọi `MailSender` trực tiếp có thể dễ hiểu và ít cấu hình hơn.

**Spring Integration Mail phù hợp hơn** khi:

- Email là một phần của pipeline EIP có sẵn.
- Nhiều nguồn sự kiện dùng chung cơ chế chuyển đổi/route.
- Cần channel adapters để tách producer khỏi transport.
- Có nhiều bước enrich, validate, transform và filter.
- Muốn lắp ghép flow với AMQP, JMS, Kafka, HTTP hoặc hệ thống nội bộ thông qua adapter tương ứng.
- Đội ngũ đã có observability và vận hành dành cho Spring Integration.

Không dùng thêm framework chỉ vì “gửi email bất đồng bộ”; một outbox worker và `JavaMailSender` thuần cũng có thể đáp ứng tốt nếu nghiệp vụ đơn giản.

## 61. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi channel `send=true` là email delivered | Status nghiệp vụ sai | Chỉ coi là channel acceptance theo semantics |
| Dùng `String` HTML và nghĩ adapter tự tạo MIME HTML | Client thấy raw markup | Dựng MIME HTML hoặc custom handler |
| Gửi DTO chưa transform | Body sai hoặc mapping fail | Transform/enrich trước adapter |
| Quên `MailHeaders.TO` | Không có recipient hợp lệ | Validate trước gửi |
| Tin `MailHeaders.TO` không thể override payload | Gửi nhầm người nhận | Kiểm tra precedence |
| Dùng header string tùy ý | Mapping không hoạt động | Sử dụng `MailHeaders` constants |
| Gắn pollable channel mà thiếu poller | Message không được tiêu thụ như mong muốn | Cấu hình poller rõ |
| Dùng QueueChannel in-memory cho mail bắt buộc gửi | Mất task khi restart | Durable outbox/broker |
| Dùng ExecutorChannel và catch lỗi ở HTTP caller | Bỏ sót lỗi async | Error channel/status tracking |
| Gắn hai mail adapters vào publish-subscribe channel | Có thể gửi trùng | Router chọn một route |
| Thêm hai consumers để “HA” một DirectChannel | Dispatch khó đoán với mục tiêu nghiệp vụ | Owner/routing rõ ràng |
| Đẩy raw PDF `byte[]` vào queue lớn | Heap/GC pressure | Storage reference, bounded queue |
| Xóa file tạm sau enqueue | Worker không đọc được attachment | Quản lý file lifecycle |
| Giữ DB transaction xuyên SMTP | Lock và connection lâu, rollback không hoàn tác mail | Short transactions + outbox |
| Retry mọi `MailSendException` ngay | Duplicate hoặc retry lỗi vĩnh viễn | Classify + policy |
| Log toàn bộ `ErrorMessage` | Lộ recipient/OTP/attachment | Structured safe metadata |
| Coi SMTP accepted là Inbox delivered | Báo sai kết quả | Provider delivery feedback riêng |
| Không test subscriber/channel choice | Lỗi sync/async/duplicate | Channel + SMTP integration tests |
| Sửa cấu hình bean nhưng flow dùng adapter host khác | Kết nối sai SMTP | Một nguồn cấu hình rõ ràng |
| Đặt SMTP credential trong source | Lộ secret | Secret management/rotation |

## 62. Checklist xây dựng outbound mail flow

### Cấu hình

- [ ] Đã có `spring-integration-mail` và mail implementation phù hợp.
- [ ] Đã kiểm tra namespace `jakarta.mail` hoặc `javax.mail` theo version.
- [ ] `JavaMailSender` có host, port, TLS, auth và timeout chính xác.
- [ ] Mail adapter dùng sender bean hoặc host config có owner rõ.
- [ ] Không khai báo trùng endpoint trên cùng channel ngoài ý muốn.

### Message contract

- [ ] Producer biết payload cần là `String`, `MailMessage` hay DTO trước transformer.
- [ ] Có `MailHeaders.TO` và sender/subject phù hợp.
- [ ] Header precedence và overwrite được kiểm soát.
- [ ] User input được validate trước khi đặt mail headers.
- [ ] HTML/attachment phức tạp được dựng bằng MIME chuyên dụng.
- [ ] Correlation ID không chứa dữ liệu cá nhân.

### Channel semantics

- [ ] Đã chọn `DirectChannel`, `QueueChannel` hoặc `ExecutorChannel` có chủ đích.
- [ ] Có poller cho `PollableChannel`.
- [ ] Queue/executor có capacity và backpressure hợp lý.
- [ ] Không coi enqueue là SMTP submission.
- [ ] Async error path được triển khai và kiểm thử.
- [ ] Có cơ chế durable outbox nếu không được mất notification.

### Reliability

- [ ] Có notification ID và attempt ID.
- [ ] Có trạng thái `PENDING/PROCESSING/SUBMITTED/FAILED/RETRY_WAIT/UNKNOWN`.
- [ ] Không giữ DB transaction dài qua SMTP send.
- [ ] Không retry mù những attempts có kết quả mơ hồ.
- [ ] Có phương án shutdown/reclaim/reconciliation.
- [ ] Bcc và suppression policy được tuân thủ.

### Kiểm thử và giám sát

- [ ] Có unit test cho transformer và header mapping.
- [ ] Có test channel sync/async/queue behavior.
- [ ] Có SMTP test server cho integration tests.
- [ ] Có test recipient, Subject, Content-Type và MIME khi cần.
- [ ] Có test lỗi SMTP, timeout và executor rejection.
- [ ] Metrics tách channel accepted với SMTP submitted.
- [ ] Không log raw message/recipient/token/attachment.

## 63. Bài tập 1 — Chọn channel phù hợp

Ứng dụng gửi email marketing không quan trọng bằng một worker độc lập; HTTP request cần trả ngay.

**Câu hỏi:** Chọn DirectChannel hay QueueChannel?

**Gợi ý:** QueueChannel + poller hoặc ExecutorChannel có thể phù hợp cho async handoff. Nhưng nếu không được mất yêu cầu gửi qua restart, cần durable store/outbox/broker ngoài kênh memory. Không coi async channel tự tạo durability.

## 64. Bài tập 2 — Handler không nhận message

Producer gửi message vào `queuedMailRequests`, nhưng không có email nào được submit.

**Câu hỏi:** Kiểm tra gì trước?

**Gợi ý:** channel là `PollableChannel` hay `SubscribableChannel`, endpoint đã start chưa, poller có được cấu hình hay không, handler có đúng input channel và log/error path hay không.

## 65. Bài tập 3 — Header To không khớp payload

Payload `SimpleMailMessage` có To A, nhưng Integration Message có `MailHeaders.TO` là B.

**Câu hỏi:** Có thể gửi tới B không?

**Gợi ý:** có. Theo mapping của outbound mail handler, mail header có thể override thuộc tính tương ứng của MailMessage. Test precedence bằng SMTP test server và đặt ownership recipient rõ ràng.

## 66. Bài tập 4 — Queue gửi true nhưng server chưa nhận

`QueueChannel.send(...)` trả `true`, dashboard lập tức ghi `DELIVERED`. Nửa phút sau poller mới lấy message.

**Gợi ý:** dashboard đã nhầm channel acceptance với submission/delivery. Cần ghi `ENQUEUED` hoặc `PENDING`, rồi cập nhật `SUBMITTED` khi adapter hoàn tất theo bằng chứng SMTP.

## 67. Bài tập 5 — Gửi một mail HTML kèm logo và PDF

Producer đẩy một chuỗi HTML và một `MailHeaders.SUBJECT` vào mail adapter, rồi mong nó tạo `multipart/mixed` với ảnh CID.

**Gợi ý:** adapter text mapping không tự tạo cấu trúc MIME phức tạp như vậy. Dùng một MIME composer và `MimeMessageHelper`, rồi một custom handler gửi `MimeMessage`, hoặc chọn integration design có contract tạo MIME được hỗ trợ rõ.

## 68. Bài tập 6 — Lỗi từ async flow biến mất

Ứng dụng dùng `ExecutorChannel`, nhưng chỉ đặt `try/catch` quanh `channel.send(...)` trong controller. SMTP server từ chối recipient sau khi controller đã trả response.

**Gợi ý:** exception trong worker không tự về caller. Cần error channel/async handler, persistent attempt state, metric và retry policy đúng ngữ cảnh.

## 69. Bài tập 7 — Hai outbound adapters nhận cùng một sự kiện

Một `PublishSubscribeChannel` có hai consumers, cả hai là mail adapter với hai SMTP providers khác nhau.

**Gợi ý:** publish-subscribe có thể phát cùng message tới hai consumers, tạo email trùng. Nếu mục tiêu là chọn route A hoặc B, dùng router với chính sách rõ ràng và một active provider cho notification/attempt.

## 70. Bài tập 8 — Crash sau khi SMTP accepted

Worker gọi mail adapter; server đã nhận DATA. Process crash trước khi cập nhật database.

**Gợi ý:** không có transaction chung giữa SMTP và database. Khi restart, attempt có thể ở `PROCESSING` cũ hoặc `UNKNOWN`. Không retry tự động nếu chưa đánh giá duplicate; dùng attempt ledger, lease và reconciliation.

## 71. Bài tập 9 — Attachment biến mất trong queue

Producer tạo file PDF tạm, đính kèm bằng `FileSystemResource` rồi đẩy `MimeMessage` vào async channel. Producer xóa file sau khi enqueue.

**Gợi ý:** MIME serialization có thể chỉ đọc file trong worker về sau. Cần giữ file đủ lâu hoặc đưa notification DTO + immutable storage reference vào queue, để worker dựng mail khi đến lượt.

## 72. Bài tập 10 — SMTP response thành công nhưng người nhận không thấy

`JavaMailSender.send(...)` không ném exception, song người nhận không thấy email trong Inbox.

**Gợi ý:** kiểm tra provider events, bounce, suppression, spam placement, mailbox rules và delivery feedback. Spring Integration outbound adapter chỉ chứng minh submission ở tầng quan sát được, không bảo đảm Inbox.

## 73. Tài liệu tham khảo

- **Spring Integration — Mail Support:** https://docs.spring.io/spring-integration/reference/mail.html
- **Spring Integration — Configuring Message Channels:** https://docs.spring.io/spring-integration/reference/channel/configuration.html
- **Spring Integration — Error Handling:** https://docs.spring.io/spring-integration/reference/error-handling.html
- **Spring Framework — Email Integration:** https://docs.spring.io/spring-framework/reference/integration/email.html

Những liên kết trên giúp đối chiếu API với phiên bản thư viện thực tế. Trong ví dụ của bài, hostname và email address là giá trị minh họa; cần thay bằng cấu hình SMTP sandbox và dữ liệu test được kiểm soát trước khi chạy.

## 74. Kết luận

**Outbound mail adapter** trong Spring Integration là một endpoint tiêu thụ `Message<?>` từ **message channel** và giao việc gửi email cho `JavaMailSender`. Nó giúp tách producer nghiệp vụ khỏi SMTP, đồng thời cho phép xây pipeline enrich headers, transform payload, validate, route và giám sát. `MailSendingMessageHandler` xử lý những trường hợp text, `MailMessage` và mapping thông dụng; các tình huống MIME phức tạp nên được dựng bằng composer/handler có contract rõ ràng.

**Lựa chọn message channel quyết định hành vi hệ thống**: `DirectChannel` thường xử lý trong caller thread, `QueueChannel` cần poller để lấy message và `ExecutorChannel` chuyển xử lý sang executor. Đổi channel có thể đổi latency, exception propagation, transaction boundary và nguy cơ mất task. Không có channel nào tự biến SMTP thành exactly-once delivery hay mặc định đảm bảo message đã vào Inbox.

Trong ứng dụng thực, cần một nguồn trách nhiệm rõ cho recipient và headers, phân loại lỗi theo giai đoạn, bảo vệ payload nhạy cảm, giới hạn concurrency, và lưu notification/attempt bền vững nếu yêu cầu gửi không được phép mất. Kết hợp **outbound adapter + channel semantics + reliable outbox + SMTP test server** sẽ tạo một hệ thống email có thể mở rộng và kiểm thử được mà không nhầm lẫn giữa “đã vào channel”, “đã submit SMTP” và “đã delivered”.
