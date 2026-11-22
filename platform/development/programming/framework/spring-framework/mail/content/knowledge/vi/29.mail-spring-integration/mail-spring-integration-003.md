# MailSendingMessageHandler trong Spring Integration Mail

**MailSendingMessageHandler** là một thành phần quan trọng của **Spring Integration Mail** khi ứng dụng muốn gửi email như một bước trong luồng xử lý message thay vì gọi trực tiếp JavaMailSender từ mọi service nghiệp vụ. Handler này đóng vai trò **outbound channel adapter**: nhận một Spring Integration message tại đầu vào, chuyển nội dung email phù hợp sang mail sender và kích hoạt thao tác gửi qua transport đã cấu hình.

Trong một ứng dụng chỉ có một loại email, gọi JavaMailSender.send(...) trực tiếp có thể đã đủ. Nhưng khi hệ thống có nhiều nguồn sự kiện, bước transform, filter, route, retry, error handling, telemetry hoặc xử lý bằng worker, việc đặt gửi email ở cuối một integration flow giúp **tách orchestration khỏi SMTP transport**.

Bài học giải thích chi tiết MailSendingMessageHandler theo ngữ cảnh **Spring Framework Mail** và **Spring Integration Mail**: vị trí trong kiến trúc, input message, cấu hình bean, cách dựng SimpleMailMessage/MimeMessage, ranh giới đồng bộ và bất đồng bộ, xử lý exception, outbox, kiểm thử, observability, bảo mật và những lỗi thường gặp.

Một nguyên tắc xuyên suốt: **MailSendingMessageHandler gửi email chứ không bảo đảm email đã vào inbox hoặc được người nhận đọc.** Một lời gọi handler thành công chỉ cho biết thao tác gửi đồng bộ đã kết thúc theo hợp đồng JavaMailSender/transport tương ứng.

## 1. MailSendingMessageHandler giải quyết bài toán gì?

Một luồng xử lý có thể gồm:

~~~text
Order confirmed / Password reset / Report ready
                      |
                      v
             Application event
                      |
                      v
             MessageChannel
                      |
                      v
       Transform / Filter / Enrich / Route
                      |
                      v
         MailSendingMessageHandler
                      |
                      v
                JavaMailSender
                      |
                      v
                  SMTP relay
~~~

Ở mô hình này:

- **Producer**: thành phần tạo yêu cầu gửi email.
- **Message**: đối tượng được đẩy vào Spring Messaging/Integration, chứa payload và headers.
- **MessageChannel**: kênh chuyển message giữa các thành phần.
- **Transformer**: chuyển dữ liệu nghiệp vụ thành mail payload mà handler hiểu.
- **MailSendingMessageHandler**: endpoint tiêu thụ message ở cuối outbound flow.
- **JavaMailSender**: abstraction của Spring Framework Mail, chịu trách nhiệm tạo/gửi MIME message.
- **SMTP relay/provider**: hệ thống nhận lệnh SMTP và tiếp tục xử lý email.

Thành phần này thuộc **Spring Integration**, còn JavaMailSender và SimpleMailMessage thuộc **Spring Framework Mail**. Dùng kết hợp hai thư viện giúp đưa thao tác gửi mail vào mô hình Enterprise Integration Patterns.

### 1.1. Tại sao không gọi sender.send(...) ở mọi nơi?

Nếu controller, event listener, batch job và worker đều tự tạo JavaMailSender hoặc tự gọi send, code dễ gặp:

- Định dạng From/Reply-To không nhất quán.
- Lặp logic template và attachment.
- Quy tắc retry khác nhau.
- Không có một nơi chung để ghi metrics/trace.
- Khó chặn các event không đủ điều kiện.
- Khó thay provider hoặc route theo loại email.
- Khó kiểm thử luồng end-to-end mà không mở SMTP thật.

Một integration flow giúp chuẩn hóa các bước, trong khi transport có thể được thay bằng mock/test double.

### 1.2. Handler không thay thế tầng nghiệp vụ

MailSendingMessageHandler không tự quyết định đơn hàng nào phải gửi, recipient có quyền nhận không, token có hết hạn không hoặc outbox job đã được xử lý hay chưa. Những điều đó phải được giải quyết trước ở service/filter/policy tương ứng.

## 2. Handler nằm ở đâu trong Spring Integration?

Spring Integration dùng một số abstraction:

| Thành phần | Vai trò |
| --- | --- |
| **Message<?>** | Payload và headers |
| **MessageChannel** | Giao tiếp giữa các endpoint |
| **DirectChannel** | Gọi subscriber đồng bộ trên thread gửi |
| **ExecutorChannel** | Dispatch qua executor, có thể bất đồng bộ |
| **QueueChannel** | Lưu tạm message trong queue in-memory theo cấu hình |
| **Transformer** | Chuyển business DTO thành mail payload |
| **Filter** | Bỏ/chặn những message không hợp lệ theo chính sách |
| **Router** | Chọn kênh tiếp theo |
| **Service activator** | Gọi logic xử lý một message |
| **Outbound channel adapter** | Gửi dữ liệu ra hệ thống bên ngoài; thường không có reply |
| **MailSendingMessageHandler** | MessageHandler thực hiện outbound mail |

MailSendingMessageHandler về bản chất là một **MessageHandler** dùng ở một endpoint outbound.

### 2.1. Sơ đồ dữ liệu

~~~text
Message<OrderMailCommand>
        |
        v
Validate command
        |
        v
Message<SimpleMailMessage>
        |
        v
DirectChannel
        |
        v
MailSendingMessageHandler
        |
        v
JavaMailSender
~~~

Với email cần HTML hoặc attachment, payload có thể được dựng thành **MimeMessage** trước khi vào handler.

### 2.2. Một chiều, không phải request-reply

Khi dùng như outbound channel adapter, handler có nhiệm vụ thực hiện side effect gửi email. Không nên kỳ vọng một **reply Message** chứa delivery receipt hoặc SMTP provider message ID được trả về theo request-reply flow.

Nếu nghiệp vụ cần trả kết quả, có thể quản lý trạng thái trong outbox, event store hoặc một service wrapper riêng.

### 2.3. MessageChannel không tự bảo đảm durability

Message được gửi qua DirectChannel hoặc ExecutorChannel không tự trở thành một công việc được lưu bền vững. Nếu cần phục hồi sau process crash, phải kết hợp outbox hoặc một message broker/queue bền vững có cơ chế ack/retry phù hợp.

## 3. Dependency cần thiết

Nếu sử dụng Spring Boot với cấu hình dependency được quản lý theo phiên bản tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Spring Integration Mail thường kéo theo các phụ thuộc Spring Integration cần thiết. Trong dự án có dependency management riêng, phải bảo đảm các phiên bản Spring Framework, Spring Integration và Jakarta Mail tương thích.

### 3.1. Spring Framework Mail khác Spring Integration Mail

- **spring-boot-starter-mail**: cung cấp cấu hình JavaMailSender/Jakarta Mail phù hợp theo điều kiện auto-configuration.
- **spring-integration-mail**: cung cấp các thành phần tích hợp mail, bao gồm mail-related endpoints và outbound handler.

Thêm starter-mail **không tự tạo một integration flow**. Ứng dụng vẫn phải khai báo channel, endpoint/handler và luồng xử lý.

### 3.2. Jakarta Mail và javax.mail

Ở hệ sinh thái **Spring Framework 6 / Spring Integration 6 / Spring Boot 3**, API mail sử dụng namespace **jakarta.mail**. Những dự án cũ dùng **javax.mail** có thể cần thay import khi nâng cấp.

Không trộn ngẫu nhiên javax.mail.internet.MimeMessage với Jakarta Mail API của một bộ thư viện mới; lỗi kiểu dữ liệu có thể xảy ra ngay lúc compile.

### 3.3. Không đoán package bằng tên

Class handler của Spring Integration được dùng với tên đầy đủ:

~~~java
import org.springframework.integration.mail.MailSendingMessageHandler;
~~~

Các lớp liên quan thường dùng:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import jakarta.mail.internet.MimeMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
~~~

Các API và overload cụ thể có thể thay đổi theo major version. Ví dụ trong bài hướng đến Spring Integration 6 và Spring Framework 6, với JavaMailSender dùng Jakarta Mail.

## 4. Cấu hình SMTP trước khi gắn handler

Trước khi một MailSendingMessageHandler có thể gửi, ứng dụng phải có mail sender đã được cấu hình.

Ví dụ **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: mail-service
    password: example-placeholder-only
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Đây là cấu hình minh họa cho SMTP submission với STARTTLS. Trong dự án thực tế, **password phải lấy từ secret manager hoặc cấu hình bí mật ở runtime**, không lưu credential thật trong source.

### 4.1. Ba timeout thường dùng

| Property | Ý nghĩa |
| --- | --- |
| **mail.smtp.connectiontimeout** | Giới hạn chờ tạo kết nối |
| **mail.smtp.timeout** | Giới hạn chờ đọc trên socket |
| **mail.smtp.writetimeout** | Giới hạn chờ ghi dữ liệu |

Những timeout này không nhất thiết cộng thành một **overall deadline** cho toàn bộ lời gọi send. Một email có nhiều bước connect, TLS, AUTH và DATA nên tổng thời gian có thể lớn hơn một ngưỡng timeout đơn lẻ.

### 4.2. STARTTLS khác implicit TLS

Provider dùng implicit TLS trên cổng submission tương ứng thường yêu cầu **mail.smtp.ssl.enable=true** và cấu hình port khác. Không sao chép cấu hình STARTTLS sang mọi provider khi chưa đọc chính sách của họ.

### 4.3. SMTP sender authorization

Một tài khoản SMTP có thể chỉ được phép gửi bằng một số From domains. Cấu hình mail sender thành công không chứng minh mọi From/Reply-To do request cung cấp đều được phép sử dụng.

## 5. Ví dụ Java Config tối thiểu: DirectChannel và handler

Ví dụ ứng dụng Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class OutboundMailIntegrationConfig {

    @Bean("outboundMailChannel")
    public MessageChannel outboundMailChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "outboundMailChannel")
    public MessageHandler outboundMailHandler(
            JavaMailSender javaMailSender
    ) {
        return new MailSendingMessageHandler(
                javaMailSender
        );
    }
}
~~~

Kết quả:

~~~text
outboundMailChannel
        |
        v
outboundMailHandler
        |
        v
JavaMailSender
        |
        v
SMTP provider
~~~

### 5.1. ServiceActivator gắn handler vào channel

Annotation **@ServiceActivator(inputChannel=...)** trên bean MessageHandler đăng ký endpoint tiêu thụ message từ channel được chỉ định trong hạ tầng Spring Integration.

Đây là một lựa chọn cấu hình Java. Ứng dụng cũng có thể dùng Java DSL hoặc XML tùy convention.

### 5.2. Vì sao dùng DirectChannel?

DirectChannel dispatch tới subscriber **trên thread gửi message**, vì vậy code gọi outboundMailChannel.send(...) thường chờ handler hoàn tất hoặc báo lỗi.

Điều này đơn giản để hiểu và kiểm thử, nhưng nó cũng có nghĩa HTTP thread sẽ bị giữ trong thời gian SMTP chạy nếu gửi trực tiếp từ request.

### 5.3. Không có reply tự động

Handler là consumer outbound và không tạo một response có ý nghĩa kiểu “email đã đọc”. Nếu người gọi cần biết request đã được **chấp nhận vào hệ thống**, trả về một trạng thái nghiệp vụ như outbox enqueued thay vì suy từ handler.

## 6. Gửi SimpleMailMessage qua channel

Một luồng với email text đơn giản có thể tạo **SimpleMailMessage** trước rồi gửi nó như payload.

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class WelcomeMailPublisher {

    private final MessageChannel outboundMailChannel;

    public WelcomeMailPublisher(
            MessageChannel outboundMailChannel
    ) {
        this.outboundMailChannel =
                outboundMailChannel;
    }

    public void publishWelcome(String recipient) {
        SimpleMailMessage mail =
                new SimpleMailMessage();

        mail.setFrom("welcome@example.org");
        mail.setTo(recipient);
        mail.setSubject("Chào mừng");
        mail.setText(
                "Cảm ơn bạn đã đăng ký tài khoản."
        );

        outboundMailChannel.send(
                MessageBuilder
                        .withPayload(mail)
                        .setHeader(
                                "mailKind",
                                "welcome"
                        )
                        .build()
        );
    }
}
~~~

Khi dùng SimpleMailMessage, adapter nhận một mail payload rõ ràng thay vì phải tự diễn giải một String bất kỳ.

### 6.1. Payload khác header

- Payload **SimpleMailMessage** chứa các trường mail như From, To, Subject, Text.
- Header **mailKind** là metadata của Spring Integration message, phục vụ route/log hoặc observability.
- Không tự suy rằng một header tùy ý sẽ được chuyển thành SMTP header hoặc From field.

Nếu muốn các Spring Message headers được ánh xạ thành email header, cần sử dụng API/mapper hoặc bước transformer phù hợp với cấu hình và phiên bản.

### 6.2. SimpleMailMessage phù hợp nội dung nào?

**SimpleMailMessage** thường dùng cho thư plain text đơn giản. Nó không phải mô hình cho HTML multipart, inline image hoặc attachment phức tạp.

### 6.3. Chú ý khả năng biến đổi payload

SimpleMailMessage là object có setters, không hoàn toàn bất biến. Khi message đã được gửi qua một channel bất đồng bộ, không nên tiếp tục sửa payload ở thread producer vì worker có thể đọc trong lúc dữ liệu bị thay đổi.

Tốt hơn là tạo một instance riêng cho mỗi ý định gửi và không mutate sau khi publish.

### 6.4. Validation không được bỏ qua

Một setter SimpleMailMessage không phải một dịch vụ xác minh mailbox. Nên validate dữ liệu người nhận trước khi publish, theo chính sách địa chỉ và quyền gửi của ứng dụng.

## 7. Tạo MimeMessage cho email HTML

Với HTML email, tạo **MimeMessage** từ JavaMailSender rồi truyền vào integration flow.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class AccountMailFactory {

    private final JavaMailSender mailSender;

    public AccountMailFactory(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public MimeMessage createVerificationMail(
            String recipient,
            String verificationUrl
    ) {
        MimeMessage message =
                mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            true,
                            "UTF-8"
                    );

            helper.setFrom("security@example.org");
            helper.setTo(recipient);
            helper.setSubject("Xác minh tài khoản");
            helper.setText(
                    "Mở đường dẫn xác minh trong trình duyệt.",
                    "<p>Vui lòng xác minh tài khoản "
                  + "bằng đường dẫn an toàn đã được cấp.</p>"
            );

            return message;
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare verification mail",
                    ex
            );
        }
    }
}
~~~

Trong ví dụ, **verificationUrl** chưa được đưa vào HTML để tránh đưa thẳng URL không qua escaping vào chuỗi HTML. Trong ứng dụng thật, URL phải được xác thực/tạo ở tầng nghiệp vụ và được render qua template engine an toàn.

### 7.1. Gửi MimeMessage vào channel

~~~java
MimeMessage mimeMessage =
        accountMailFactory.createVerificationMail(
                recipient,
                verificationUrl
        );

outboundMailChannel.send(
        MessageBuilder
                .withPayload(mimeMessage)
                .setHeader(
                        "mailKind",
                        "account_verification"
                )
                .build()
);
~~~

Với mô hình này, **MimeMessage đã được chuẩn bị trước handler**, giúp tách lỗi render/MIME preparation khỏi lỗi transport.

### 7.2. Không tạo MimeMessage từ sender không tương thích một cách tùy tiện

Khi có nhiều provider với sender/session cấu hình khác nhau, cần thống nhất nơi tạo MimeMessage và nơi thực hiện send. Các thuộc tính Session và MIME encoding có thể ảnh hưởng hành vi; hãy thiết kế factory dùng cấu hình tương thích hoặc chuẩn hóa message trước khi chuyển nhà cung cấp.

### 7.3. MIME và Jakarta Mail là ranh giới riêng

MailSendingMessageHandler không tự thiết kế HTML template thay ứng dụng. Nó nhận mail payload đã chuẩn bị và chuyển qua sender. Logic cá nhân hóa/escape HTML, attachment permissions và template version thuộc tầng chuẩn bị.

## 8. Attachment và inline resource

Một email nhiều phần cần **MimeMessageHelper** ở chế độ multipart.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message =
        javaMailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                true,
                "UTF-8"
        );

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn");

helper.setText(
        "Hóa đơn của bạn được đính kèm.",
        "<html><body><p>Hóa đơn được đính kèm.</p></body></html>"
);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf"
);
~~~

Sau đó đưa message vào outbound channel.

### 8.1. Resource có thể được đọc muộn

Một FileSystemResource/ClassPathResource được gắn vào MIME part có thể chưa được đọc hết tại thời điểm gọi addAttachment. Việc mở InputStream có thể xảy ra lúc Jakarta Mail serialize message trong send.

Điều này ảnh hưởng tới exception, latency và retry. Không mặc định khẳng định “đã addAttachment thì file chắc chắn đọc được”.

### 8.2. InputStream phải có thể cung cấp dữ liệu phù hợp

Một InputStream đã bị tiêu thụ có thể không thể đọc lại khi MIME transport cần. Với dữ liệu nhỏ/đã giới hạn, **ByteArrayResource** thường thuận tiện vì có thể tạo InputStream mới từ bytes.

Với file lớn, cần thiết kế storage/streaming có giới hạn và cơ chế tái mở phù hợp, không buộc toàn bộ nội dung vào bộ nhớ nếu vượt ngân sách.

### 8.3. Không nhầm inline với attachment

Inline resource có Content-ID để HTML tham chiếu; attachment thường hiển thị như tệp. Chúng có cấu trúc MIME khác nhau và cần test riêng.

### 8.4. Không lưu full MIME vào log

MIME có thể chứa PII, token, hóa đơn, file đính kèm. Observability nên ghi event ID, mail kind, kết quả, duration và error category thay vì dump message bytes.

## 9. Java DSL: một cấu hình khác

Ngoài annotation, có thể dùng **IntegrationFlow**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
public class OutboundMailFlowConfig {

    @Bean
    public IntegrationFlow mailFlow(
            JavaMailSender sender
    ) {
        return IntegrationFlow
                .from("outboundMailChannel")
                .handle(
                        new MailSendingMessageHandler(sender)
                )
                .get();
    }
}
~~~

Flow đăng ký một consumer cho channel **outboundMailChannel** và dùng handler làm bước cuối.

### 9.1. Chỉ chọn một cách đăng ký cho cùng luồng

Không đồng thời gắn hai handler vào cùng DirectChannel rồi mặc định cho rằng cả hai sẽ xử lý mọi message theo thứ tự. DirectChannel là point-to-point dispatch channel có subscriber selection; nhiều consumers có thể tạo behavior phân phối khác mong đợi.

Nếu mục tiêu là gửi tới nhiều destinations, phải dùng đúng routing/recipient-list/publish-subscribe pattern thay vì đăng ký duplicate consumers ngẫu nhiên.

### 9.2. Java DSL thuận tiện khi có transformer/filter/router

Ví dụ luồng khái niệm:

~~~text
businessMailChannel
        |
        v
Filter: allowed recipient?
        |
        v
Transformer: business DTO -> MimeMessage
        |
        v
MailSendingMessageHandler
~~~

Cấu hình exact DSL cho transformer/filter phụ thuộc cách code và các kiểu payload của ứng dụng. Handler chỉ phụ trách phần gửi cuối.

## 10. Message<String> không nhất thiết là email hoàn chỉnh

Trong một hệ thống message-driven, nhiều producer gửi payload chỉ là String:

~~~java
MessageBuilder
        .withPayload("Đơn hàng đã được tạo")
        .build();
~~~

Đừng giả định handler luôn suy ra recipient, Subject, From và content type đúng từ String đó.

Để tránh phụ thuộc chuyển đổi ngầm và headers không được cấu hình đầy đủ, nên có bước transformer rõ ràng:

~~~text
Message<OrderEvent>
        |
        v
MailComposer
        |
        v
Message<SimpleMailMessage or MimeMessage>
        |
        v
MailSendingMessageHandler
~~~

### 10.1. Tại sao nên biến đổi sớm?

Khi payload đã là mail object hoàn chỉnh:

- Contract của outbound adapter dễ hiểu.
- Việc test Subject/To/From riêng biệt hơn.
- Lỗi validation xuất hiện trước send.
- Ít phụ thuộc vào header mapping ngầm.
- Dễ dùng chung ở nhiều nguồn nghiệp vụ.

### 10.2. Nếu dự án dùng MailHeaders

Spring Integration Mail có thể có các cách cấu hình header/expression cho outbound adapter tùy API và phiên bản. Khi áp dụng, phải kiểm tra chính xác hợp đồng của phiên bản đang dùng; không coi một header tùy đặt như **to** hoặc **subject** sẽ tự động biến thành header MIME trong mọi cấu hình.

## 11. So sánh gọi JavaMailSender trực tiếp và handler

| Tiêu chí | JavaMailSender.send trực tiếp | MailSendingMessageHandler |
| --- | --- | --- |
| Mục đích | Gửi mail từ code ứng dụng | Gửi mail từ integration message |
| Input | SimpleMailMessage, MimeMessage, preparator tùy overload | Spring Message mang mail payload tương thích |
| Đặt trong flow | Tự triển khai | Có thể gắn vào channel/endpoint |
| Filter/transform/router | Tự gọi theo code | Dùng Spring Integration components |
| Đồng bộ/bất đồng bộ | Theo cách caller thực thi | Phụ thuộc channel/executor trước handler |
| Retry | Tự thiết kế | Vẫn cần advice/policy/outbox phù hợp |
| Delivery receipt | Không tự có | Không tự có |
| Thích hợp | Luồng nhỏ, ít orchestration | Luồng tích hợp nhiều bước/nguồn |

**Không có công nghệ nào mặc định “an toàn hơn” trong mọi trường hợp.** Một flow cấu hình tốt giúp tổ chức code; độ bền và correctness còn phụ thuộc transaction, retry, validation và monitoring.

## 12. DirectChannel: gửi đồng bộ và lan truyền lỗi

Khi producer gửi qua DirectChannel:

~~~text
HTTP request thread
        |
        v
outboundMailChannel.send(...)
        |
        v
MailSendingMessageHandler
        |
        v
JavaMailSender.send(...)
        |
        +-- return or exception
        |
        v
Producer resumes
~~~

Code gửi message có thể bị giữ cho đến khi SMTP thao tác xong.

### 12.1. Ưu điểm

- Dễ hiểu thời điểm hoàn tất.
- Caller có thể bắt exception đồng bộ.
- Dễ kiểm thử integration flow.
- Không cần executor queue.

### 12.2. Nhược điểm

- HTTP request thread chờ mạng.
- Timeout có thể làm request chậm.
- Một provider outage có thể làm nhiều request bị giữ.
- Nếu send xảy ra trong @Transactional method, transaction có thể bị kéo dài.

### 12.3. Exception là transport result, không phải delivery status

Một lời gọi channel.send hoàn tất không có nghĩa khách đã nhận email. Nó chỉ cho biết consumer/transport đồng bộ đã được xử lý theo flow.

## 13. ExecutorChannel và bất đồng bộ

Muốn chuyển handler sang executor, có thể dùng **ExecutorChannel**:

~~~java
import java.util.concurrent.Executor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean("outboundMailChannel")
public MessageChannel outboundMailChannel(
        Executor mailExecutor
) {
    return new ExecutorChannel(mailExecutor);
}
~~~

Khi producer gửi message, tác vụ có thể được dispatch đến worker thread.

### 13.1. send trả về không chứng minh SMTP hoàn tất

Với ExecutorChannel, thời điểm trả về từ channel.send có thể chỉ phản ánh việc dispatch/enqueue vào executor. SMTP transport chạy sau đó, có thể thất bại dù producer đã trả response.

### 13.2. Error handling thay đổi

Exception phát sinh trong worker không tự quay về HTTP caller đã kết thúc. Cần cấu hình errorChannel, error handler/dispatcher hoặc cơ chế ghi trạng thái/notification phù hợp với topology Spring Integration đang dùng.

Không giả định mọi exception async mặc định được lưu hoặc retry cho đến khi thành công.

### 13.3. Executor queue không đồng nghĩa durable queue

Một executor thường giữ task trong memory. Nếu process crash trước khi worker thực hiện, task có thể mất. Với email quan trọng, nên có **transactional outbox** hoặc broker bền vững trước bước handler.

### 13.4. Backpressure và saturation

Nếu executor có số thread nhỏ và queue không giới hạn, backlog có thể tăng vô hạn khi SMTP chậm. Nếu queue bounded, submission có thể bị từ chối. Cần cấu hình thread pool, queue capacity, rejection policy và đo queue depth/age.

## 14. QueueChannel: nhận vào hàng đợi chưa phải gửi

Spring Integration có **QueueChannel** để giữ message cho một polling consumer. Tuy nhiên, một QueueChannel in-memory không mặc định chịu được process restart.

~~~text
Publisher -> QueueChannel -> Polling endpoint -> Mail handler
                   |
                   +-- Waiting messages
~~~

### 14.1. Kết quả enqueue và kết quả SMTP khác nhau

Nếu producer chỉ đưa message vào QueueChannel, “đã nhận yêu cầu” khác “đã gửi SMTP”. API hoặc dashboard cần phản ánh hai trạng thái.

### 14.2. Poller quyết định tốc độ xử lý

Một polling endpoint có thể giới hạn poll interval, số message mỗi lần và concurrency. Nếu SMTP chậm, queue sẽ tăng; cần quan sát queue delay cùng send latency.

### 14.3. Không dùng in-memory queue cho yêu cầu durability cao

Với email xác nhận giao dịch, khôi phục sau crash/restart thường là yêu cầu thiết kế. Cần outbox hoặc message store/broker được cấu hình bền vững và xử lý lỗi phù hợp.

## 15. Retry và request-reply semantics

MailSendingMessageHandler có thể được đặt trong flow có retry advice hoặc một worker retry loop. Nhưng **gửi email là side effect bên ngoài database**, nên retry cần thận trọng.

Một tình huống:

~~~text
MailSendingMessageHandler
        |
        v
SMTP sends DATA
        |
        v
Relay may accept message
        |
        v
Connection closes before final reply
        |
        v
Caller sees exception
        |
        v
Retry may send duplicate
~~~

### 15.1. Không retry mọi exception

Các trường hợp:

| Lỗi | Retry? | Lý do |
| --- | --- | --- |
| Recipient sai cú pháp | Thường không | Dữ liệu lỗi ổn định |
| Attachment thiếu | Tùy nguyên nhân | Có thể cần sửa nguồn |
| AUTH 535 | Thường dừng và sửa cấu hình | Retry dồn dập không giúp |
| TLS certificate sai | Cần sửa trust/endpoint | Không bypass TLS |
| SMTP 421/450 | Có thể backoff | Thường là lỗi tạm thời |
| Provider throttling | Backoff/giảm tốc | Tránh quá quota |
| Timeout trước khi connect | Có thể retry có giới hạn | Thường chưa gửi dữ liệu |
| Timeout sau DATA | Rủi ro duplicate | Kết quả có thể không rõ |

### 15.2. Retry là chính sách nghiệp vụ

Số lần thử, backoff, TTL/deadline và phân loại lỗi phải theo mail kind. Email reset password có link hết hạn cần quy tắc khác newsletter.

### 15.3. Handler không tự biến SMTP thành transaction

Không thể rollback một message đã được SMTP relay chấp nhận chỉ bằng rollback database transaction.

## 16. Transaction nghiệp vụ và email

Mẫu cần thận trọng:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.markConfirmed(id);

    outboundMailChannel.send(
            mailMessageFor(id)
    );
}
~~~

Nếu channel là DirectChannel, handler có thể gửi email **trong lúc transaction chưa commit**.

### 16.1. Kịch bản rollback nguy hiểm

~~~text
DB transaction begins
     |
     v
Order marked confirmed
     |
     v
SMTP relay accepts confirmation
     |
     v
DB commit fails / rollback
     |
     v
Customer receives email about an order
that was not actually confirmed
~~~

SMTP không tham gia cùng transaction database, nên không rollback theo.

### 16.2. Tách sau commit

Có thể tổ chức service orchestration gọi gửi sau khi transaction commit hoàn tất, hoặc dùng **@TransactionalEventListener(phase = AFTER_COMMIT)** cho workflow không yêu cầu durability tuyệt đối.

### 16.3. AFTER_COMMIT chưa đủ durable

Nếu process crash ngay sau commit nhưng trước khi listener kịp gửi, tác vụ có thể mất. Với email quan trọng, transactional outbox là lựa chọn mạnh hơn.

### 16.4. Async không giải quyết atomicity

Đưa send qua ExecutorChannel chỉ làm công việc chạy trên thread khác; nó không tự bảo đảm “chỉ gửi nếu transaction commit” hoặc “không mất tác vụ sau crash”.

## 17. Kết hợp transactional outbox với handler

Luồng đáng tin cậy hơn:

~~~text
Business transaction
     |
     +-- Update business record
     +-- Insert outbox mail event
     |
     v
COMMIT
     |
     v
Outbox worker claims pending event
     |
     v
Validate / render / build mail object
     |
     v
MessageChannel
     |
     v
MailSendingMessageHandler
     |
     v
JavaMailSender -> SMTP
     |
     v
Record attempt outcome and next action
~~~

### 17.1. Outbox là nơi giữ ý định gửi

Nó cho phép khôi phục sau restart, kiểm soát retry và quan sát backlog. MailSendingMessageHandler vẫn chỉ là bước gửi cuối.

### 17.2. Mỗi attempt cần trạng thái rõ

Một outbox event có thể có:

~~~text
mail_event_id
mail_kind
recipient_reference
created_at
status
attempts
next_attempt_at
last_attempt_started_at
last_error_category
last_provider_alias
~~~

Những trường này do ứng dụng định nghĩa.

### 17.3. Lưu rendered content hay DTO snapshot?

- **DTO snapshot + template version**: có thể render lại khi retry; ít lưu HTML nhưng chi phí render có thể lặp.
- **Rendered content**: giúp retry cùng nội dung, nhưng lưu dữ liệu cá nhân hóa và cần quản lý retention/access.
- **Kết hợp**: linh hoạt hơn nhưng cần thiết kế trạng thái cẩn thận.

### 17.4. Outbox không bảo đảm exactly-once SMTP

Relay có thể accept rồi worker crash trước khi cập nhật SENT. Retry có thể gửi trùng. Dùng idempotency nghiệp vụ, log attempt và cơ chế đối soát unknown outcome.

## 18. Error handling cho DirectChannel

Với channel đồng bộ, một exception từ sender/handler có thể lan ngược về producer trong cùng call stack.

Ví dụ:

~~~java
try {
    outboundMailChannel.send(message);
} catch (RuntimeException ex) {
    // Ghi nhận failure ở tầng điều phối.
    // Không khẳng định chắc chắn relay chưa chấp nhận.
    recordFailure(ex);
}
~~~

**recordFailure** trong ví dụ là hàm ứng dụng.

### 18.1. Nên catch ở ranh giới thích hợp

Producer HTTP không nhất thiết phải xử lý tất cả SMTP exception chi tiết. Một service điều phối/outbox thường là nơi phù hợp để phân loại lỗi, ghi trạng thái và quyết định retry.

### 18.2. Không nuốt lỗi rồi báo thành công

Nếu handler báo lỗi nhưng application catch rồi trả “email đã được gửi” mà không ghi trạng thái, hệ thống sẽ mất khả năng đối soát.

### 18.3. Không lặp gửi một cách vô hạn

Một catch đơn giản gọi lại outboundMailChannel.send ngay trong vòng lặp có thể gây storm tới SMTP provider và duplicate. Dùng retry policy có backoff, attempt cap và deadline rõ ràng.

## 19. Error handling trong flow bất đồng bộ

Với ExecutorChannel hoặc các endpoint async, lỗi xảy ra ở worker và cần một con đường xử lý riêng.

~~~text
Publisher thread
       |
       v
ExecutorChannel enqueues work
       |
       +-- Publisher returns
       |
       v
Worker runs handler
       |
       +-- Success -> record completion
       |
       +-- Failure -> error handling / outbox update
~~~

### 19.1. ErrorChannel không phải phép màu

Spring Integration có các cơ chế **errorChannel**, ErrorMessage và error handler cho một số luồng async; đường đi chính xác phụ thuộc loại channel, endpoint, task executor và cấu hình.

Cần cấu hình và kiểm thử thực tế rằng lỗi đi tới đúng nơi; không mặc định mọi exception async tự được publish đến một errorChannel bền vững.

### 19.2. Lưu trạng thái ở chỗ có chủ sở hữu

Nếu outbox worker sở hữu event, nó nên biết attempt thành công/thất bại và ghi durable state. Nếu một worker chỉ enqueue vào ExecutorChannel rồi đánh dấu SENT ngay, SMTP thực tế có thể thất bại sau khi event đã bị coi là xong.

### 19.3. Cân nhắc tránh hai tầng queue không cần thiết

Outbox đã là một durable queue. Đặt thêm ExecutorChannel queue dài có thể khiến thời gian queue thực tế khó theo dõi và việc acknowledge event trở nên phức tạp.

## 20. Header metadata và MIME headers

Một Spring message có dạng:

~~~java
Message<SimpleMailMessage> integrationMessage =
        MessageBuilder
                .withPayload(mail)
                .setHeader(
                        "mailEventId",
                        "mail-1842"
                )
                .setHeader(
                        "mailKind",
                        "order_confirmation"
                )
                .build();
~~~

Các headers này phục vụ workflow Spring Integration. Không mặc định tất cả chúng được gửi thành MIME headers cho người nhận.

### 20.1. Đặt metadata ở đâu?

- **Mail event ID**: trong logs/outbox/trace hoặc message headers nội bộ.
- **Recipient/Subject/Body**: trong mail payload đã validate.
- **From/Reply-To**: được cấu hình theo sender identity policy.
- **MIME Content-Type/Content-ID**: thiết lập khi dựng MimeMessage.

### 20.2. Không phản chiếu header tùy ý ra email

Nếu message header chứa internal ID, token hoặc tenant data, việc copy tất cả sang MIME headers có thể làm lộ metadata cho người nhận và các SMTP relays. Chỉ ánh xạ các MIME headers được phép.

### 20.3. Correlation phục vụ retry

Một mailEventId ổn định giúp nối message, outbox event và SMTP attempt. Nhưng Message-ID ở MIME không phải cơ chế đảm bảo provider sẽ loại bỏ email trùng.

## 21. Router nhiều provider với MailSendingMessageHandler

Một ứng dụng có thể có nhiều JavaMailSender và nhiều outbound channels:

~~~text
                         MailRouter
                         /        \
                        v          v
                  primaryMail   backupMail
                        |          |
                        v          v
                 Handler A     Handler B
                        |          |
                        v          v
                 SMTP A        SMTP B
~~~

Mỗi MailSendingMessageHandler dùng một sender đã cấu hình cho provider tương ứng.

### 21.1. Không đổi cấu hình singleton sender đồng thời

Nếu nhiều thread thay host/username của cùng JavaMailSenderImpl trước mỗi send, có nguy cơ gửi sai account/provider. Dùng sender instances tách biệt được đăng ký và chọn theo route.

### 21.2. Route phải giải thích được

Một quyết định route nên ghi:

~~~text
mailEventId
sourceAlias
providerAlias
accountAlias
routeReason
routePolicyVersion
~~~

Dữ liệu provider thực tế thuộc từng **attempt**, không chỉ thuộc event gốc.

### 21.3. Failover không luôn an toàn

Nếu attempt A timeout sau DATA, A có thể đã gửi thành công. Chuyển ngay sang B có thể tạo duplicate. Chỉ failover theo một policy hiểu loại lỗi và mức chắc chắn của kết quả.

### 21.4. From authorization và DKIM

Provider dự phòng phải được phép gửi From domain của ứng dụng, có cấu hình SPF/DKIM/DMARC phù hợp và đáp ứng yêu cầu bảo mật. Failover không nên bypass sender authorization.

## 22. Quan sát hiệu năng handler

Một lời gọi gửi có thể được chia:

~~~text
Business view loading
        |
        v
Template render
        |
        v
MimeMessage build
        |
        v
Channel dispatch / queue wait
        |
        v
MailSendingMessageHandler invocation
        |
        v
JavaMailSender.send
        |
        v
SMTP response
~~~

Có thể đo:

| Metric | Phạm vi |
| --- | --- |
| **mail.template.render.duration** | Render HTML/text |
| **mail.message.build.duration** | Dựng mail payload/MIME |
| **mail.channel.queue.delay** | Message nằm chờ trước worker |
| **mail.smtp.submit.call.duration** | Lời gọi sender.send |
| **mail.smtp.submit.attempts** | Số lần gửi |
| **mail.outbox.pending.count** | Backlog |
| **mail.event.to.relay.acceptance** | Business event đến relay accept |
| **mail.smtp.failures** | Lỗi theo provider/category |

### 22.1. Handler duration khác SMTP server processing

Nếu đo bao ngoài JavaMailSender.send, duration có thể chứa DNS, TCP, TLS, AUTH, MIME serialization, attachment lazy read, DATA và server replies. Không coi nó là thời gian provider xử lý thuần.

### 22.2. Async latency cần đo ở worker

Nếu timer chỉ bao quanh channel.send vào ExecutorChannel, nó có thể đo thời gian dispatch chứ không phải SMTP. Đặt Timer ở adapter hoặc một wrapper quanh send trong worker.

### 22.3. Ghi metrics cả khi lỗi

Dùng finally hoặc Micrometer Timer.Sample để duration lỗi/timeout không biến mất khỏi p95/p99.

## 23. Micrometer instrumentation cho outbound flow

Một wrapper phía application có thể đo mỗi attempt:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class ObservedMailTransport {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public ObservedMailTransport(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void submit(
            MimeMessage message,
            String mailKind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", mailKind,
                            "outcome", outcome
                    )
            );
        }
    }
}
~~~

Đây là một ví dụ **adapter/wrapper được ứng dụng xây dựng** để minh họa ranh giới đo. Nếu dùng MailSendingMessageHandler trực tiếp, có thể instrument phía JavaMailSender decorator, interceptor/advice hoặc wrapper được cấu hình phù hợp để không gửi hai lần.

### 23.1. Không thêm hai sender cạnh nhau

Đừng vừa để handler gửi vừa gọi ObservedMailTransport.submit trên cùng message chỉ để ghi metric: làm vậy tạo hai side effects gửi thư. Nên đặt instrumentation **bao quanh một lần transport**.

### 23.2. Chọn tag ít giá trị

kind nên lấy từ tập hữu hạn như order_confirmation, password_reset, security_alert. Không dùng recipient, Subject, mailEventId hoặc raw exception message làm Timer tags.

### 23.3. Gắn provider nếu đa SMTP

Nếu flow định tuyến provider, ghi provider alias thực tế ở attempt. Không suy provider từ header From hoặc route ban đầu khi đã có failover.

## 24. Structured logs và tracing

Một log sự kiện hợp lý:

~~~text
event=mail.smtp.attempt.finished
mailEventId=mail-1842
attemptId=mail-1842-2
mailKind=order_confirmation
provider=primary_smtp
outcome=failure
errorCategory=timeout
durationMs=10120
~~~

Nó giúp tra một attempt cụ thể mà không phải log message body.

### 24.1. Không log payload.toString một cách mù quáng

Một MailMessage/MimeMessage hoặc business DTO có thể chứa recipient, token, HTML hoặc attachment metadata. Tránh log toàn bộ message chỉ để debug channel routing.

### 24.2. Traces có thể nối các giai đoạn

~~~text
order.confirm
    |
    v
outbox.enqueue
    |
    v
mail.worker.process
    |
    +-- mail.transform
    +-- mail.route
    +-- mail.smtp.submit
~~~

Khi đi qua durable queue hoặc outbox, có thể dùng trace context hoặc span links để nối công việc bất đồng bộ, phù hợp chính sách privacy/retention.

### 24.3. Không coi success là delivered

SMTP submit success là một giai đoạn. Bounce, deferred hoặc delivered có thể đến từ webhook/API provider nếu tích hợp riêng; MailSendingMessageHandler không tự sinh các sự kiện downstream đó.

## 25. Bảo mật trong MailSendingMessageHandler flow

Khi đưa thao tác gửi qua message channel, cần bảo vệ cả dữ liệu và điều khiển luồng.

### 25.1. Recipient validation

- Không cho recipient null/blank.
- Kiểm tra cú pháp theo policy sản phẩm.
- Không chấp nhận danh sách nhiều recipient ở trường chỉ cho phép một.
- Kiểm tra quyền gửi theo tenant và mục đích.
- Không tin tưởng recipient được truyền từ message header tùy ý.

### 25.2. Header injection

Subject, display name, filename và các trường header không nên nhận CR/LF hoặc control characters ngoài hợp đồng. Dùng API Jakarta Mail/MimeMessageHelper và validation đầu vào, không ghép raw MIME header từ user input.

### 25.3. HTML template escaping

Dữ liệu người dùng trong template HTML cần được escape phù hợp. Không dùng string concatenation để chèn raw HTML/link ngoài trust policy.

### 25.4. Attachment path và resource

Không dùng filename do người dùng gửi làm filesystem path chưa được kiểm tra. Cần kiểm soát resource access, file size, type, retention và quyền đọc.

### 25.5. SMTP credentials

Lấy username/password/token từ secret manager. Không đưa vào message headers, logs, metrics, tracing hoặc email body.

### 25.6. Mail debug

Jakarta Mail protocol debug có thể ghi recipient và metadata; tránh bật mặc định trong production, đặc biệt các tùy chọn có thể làm lộ dữ liệu AUTH.

## 26. Kiểm thử MailSendingMessageHandler mà không có SMTP thật

Đối tượng này là MessageHandler, nên có thể tạo instance trong test rồi gọi handleMessage(...) với một Message có payload MimeMessage.

Ví dụ JUnit 5/Mockito:

~~~java
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

class MailSendingMessageHandlerTest {

    @Test
    void delegatesMimeMessageToSender() {
        JavaMailSender sender =
                mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties())
        );

        MailSendingMessageHandler handler =
                new MailSendingMessageHandler(sender);

        handler.handleMessage(
                MessageBuilder.withPayload(mime).build()
        );

        verify(sender, times(1))
                .send(same(mime));
    }
}
~~~

Mục đích test:

- Handler nhận integration message chứa MimeMessage.
- JavaMailSender được gọi một lần.
- Không tạo network request.
- Không cần SMTP account hoặc provider thật.

### 26.1. Vì sao dùng MimeMessage thật?

Một MimeMessage trong bộ nhớ có thể tạo từ Session giả. Điều này giúp test handler contract mà không phải mock sâu toàn bộ Jakarta Mail internals.

### 26.2. Kiểm thử email content ở tầng khác

Để kiểm tra Subject, From, To, MIME multipart và attachment, test factory/composer riêng. Unit test của handler nên tập trung vào **ủy quyền gửi** và số lời gọi send.

### 26.3. Không dùng send tới địa chỉ thật

Unit test không phải delivery test. Chỉ mock sender hoặc dùng SMTP capture server trong test tích hợp được kiểm soát.

## 27. Kiểm thử exception được lan truyền

Cho JavaMailSender gửi lỗi giả:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

@Test
void propagatesTransportFailure() {
    JavaMailSender sender = mock(JavaMailSender.class);

    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
    );

    doThrow(new MailSendException("simulated SMTP failure"))
            .when(sender)
            .send(same(mime));

    MailSendingMessageHandler handler =
            new MailSendingMessageHandler(sender);

    assertThrows(
            RuntimeException.class,
            () -> handler.handleMessage(
                    MessageBuilder.withPayload(mime).build()
            )
    );

    verify(sender, times(1))
            .send(same(mime));
}
~~~

Trong nhiều flow, Spring Integration có thể bọc hoặc truyền tiếp exception qua abstraction MessagingException; test nên assert hợp đồng lỗi ở boundary mong muốn, không giả định mọi version luôn giữ nguyên exception class ngoài cùng.

### 27.1. Không giả định exception nghĩa là chưa gửi

Một MailSendException do lỗi transport không tự chứng minh relay chưa accept DATA. Retry policy cần có phân loại phase và unknown outcome phù hợp.

### 27.2. Kiểm tra error channel ở test tích hợp

Nếu dùng ExecutorChannel/errorChannel, cần test luồng bất đồng bộ thực tế: producer có thể trả trước, worker gửi lỗi, ErrorMessage đi đúng kênh được cấu hình và outbox state được cập nhật.

## 28. Kiểm thử flow DirectChannel

Một test có thể đăng ký handler làm subscriber:

~~~java
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

@Test
void directChannelDispatchesToMailHandler() {
    JavaMailSender sender =
            mock(JavaMailSender.class);

    MailSendingMessageHandler handler =
            new MailSendingMessageHandler(sender);

    DirectChannel channel = new DirectChannel();
    channel.subscribe(handler);

    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
    );

    channel.send(
            MessageBuilder.withPayload(mime).build()
    );

    verify(sender, times(1)).send(same(mime));
}
~~~

### 28.1. Điều test chứng minh

DirectChannel nhận Message, dispatch đồng bộ đến subscriber và handler gọi sender.

### 28.2. Điều test chưa chứng minh

- SMTP server thật chấp nhận message.
- TLS/AUTH được cấu hình đúng.
- Email đã vào inbox.
- Retry/outbox durable.
- ErrorChannel async hoạt động.

Những hành vi đó cần test riêng với môi trường phù hợp.

## 29. Test nhiều provider và route selection

Nếu hệ thống có nhiều handler:

~~~text
Message<MailRequest>
        |
        v
Router
   /           \
  v             v
primaryChan   backupChan
  |             |
  v             v
primaryHandler backupHandler
  |             |
  v             v
senderA       senderB
~~~

Test cần bao phủ:

1. Route primary gửi qua sender A, không gọi B.
2. Route backup gửi qua sender B, không gọi A.
3. Lỗi recipient invalid không gọi sender nào.
4. Lỗi provider A được ghi đúng provider A.
5. Failover chỉ xảy ra khi policy cho phép.
6. Timeout sau DATA không mặc định gửi lại vô điều kiện.
7. Cùng event có nhiều attempts nhưng không đếm thành nhiều unique events.
8. Metadata của provider được ghi ở chính attempt tương ứng.

### 29.1. Không dùng một JavaMailSenderImpl được mutate trong test concurrency

Test nên có các sender độc lập để phản ánh cấu hình production. Việc thay host/username trên một singleton sender nhiều thread vừa khó test vừa dễ tạo lỗi.

### 29.2. Không nhầm router với load balancer tự động

Spring Integration Router đưa message đến channel theo logic đã cấu hình. Nó không tự đưa ra health/rate limit/retry policy cho SMTP provider. Những quyết định này phải được định nghĩa rõ.

## 30. Khi nào không nên dùng MailSendingMessageHandler?

Không nhất thiết phải có integration flow cho mọi tính năng. Gọi JavaMailSender trực tiếp có thể phù hợp nếu:

- Chỉ có một service gửi email.
- Không có routing, transformer/filter hoặc queue.
- Logic dựng message rõ ràng, dễ test.
- Không cần tách message-driven orchestration.
- Đội ngũ muốn hạn chế lớp abstraction không cần thiết.

MailSendingMessageHandler có ích khi ứng dụng đã dùng Spring Integration hoặc cần liên kết mail outbound với nhiều nguồn message.

### 30.1. Không thêm flow chỉ để đổi cú pháp

Thay:

~~~java
sender.send(mimeMessage);
~~~

bằng một channel + handler mà không có lợi ích về routing, error handling, kiểm thử hoặc orchestration có thể làm kiến trúc phức tạp hơn mà không tăng reliability.

### 30.2. Không nhầm handler với provider SDK

MailSendingMessageHandler dùng SMTP abstraction của Spring Mail. Những tính năng provider-specific như template gửi phía provider, analytics webhook hoặc message ID từ API có thể cần adapter/SDK khác.

## 31. Anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Gọi handler từ HTTP transaction dài | Giữ thread/DB connection | Tách sau commit/outbox |
| Cho rằng ExecutorChannel là durable | Mất task khi crash | Durable queue/outbox |
| Gửi String không có mail metadata rõ | Thiếu To/From/Subject | Dùng transformer tạo mail payload |
| Tạo SimpleMailMessage rồi mutate sau publish | Race với async consumer | Tạo object riêng, không mutate |
| Đưa PII vào Integration headers không kiểm soát | Dễ lộ qua log/tracing | Allowlist metadata |
| Log toàn MimeMessage | Lộ body/attachment | Structured safe logs |
| Không cấu hình SMTP timeouts | Worker có thể chờ rất lâu | Connection/read/write timeouts |
| Catch rồi bỏ exception | Báo thành công giả | Ghi trạng thái/raise đúng |
| Retry tất cả lỗi | Storm/duplicate | Phân loại và backoff |
| Coi send success là inbox delivered | Sai semantics | Theo dõi relay vs delivery |
| Gửi trước database commit | Email trái với rollback | Outbox/after-commit |
| Đánh dấu SENT ngay khi enqueue async | Chưa thực sự SMTP submit | Ack theo worker outcome |
| Dùng chung một sender rồi đổi host | Race/nhầm provider | Sender instances riêng |
| Không kiểm tra resource trước send | Lỗi file đọc muộn | Bounded preflight/reopenable source |
| Kỳ vọng DirectChannel fan-out với nhiều handlers | Message dispatch không như mong muốn | Router/pub-sub đúng EIP |
| Kiểm thử bằng SMTP production thật | Rủi ro gửi nhầm | Mockito/capture SMTP test |
| Đếm attempts như unique emails | Sai dashboard | Hai metric riêng |
| Không đo queue delay | Không thấy backlog | Queue/outbox metrics |

## 32. Ma trận kiểm thử theo ranh giới

| Nhóm | Tình huống | Expected behavior |
| --- | --- | --- |
| Payload | MimeMessage hợp lệ | Handler gọi sender một lần |
| Payload | SimpleMailMessage hợp lệ | Flow tạo và gửi đúng text mail theo contract |
| Payload | Dữ liệu business DTO chưa transform | Bị chặn/transform trước handler |
| Validation | Recipient sai | Không gọi transport |
| MIME | Template lỗi | Ghi lỗi preparation, không gọi SMTP |
| Attachment | Resource không tồn tại | Báo lỗi trước/ở serialize theo design |
| DirectChannel | Sender success | Caller hoàn tất đồng bộ |
| DirectChannel | Sender failure | Lỗi lan đến caller/handler boundary |
| ExecutorChannel | Send chậm | Caller không coi enqueue là delivery |
| ExecutorChannel | Worker failure | Lỗi tới handler/error state được cấu hình |
| Outbox | Commit thành công | Event bền vững được worker xử lý |
| Outbox | Rollback | Không tạo ý định gửi đã commit |
| Retry | SMTP 421/450 | Backoff theo policy |
| Retry | AUTH/config lỗi | Không retry dồn dập |
| Retry | Timeout sau DATA | Có trạng thái unknown/duplicate policy |
| Multi-provider | Route A | Chỉ sender A được gọi |
| Multi-provider | Failover A→B | Attempts được ghi đúng mỗi provider |
| Observability | Duration success/failure | Metrics được ghi cho cả hai |
| Security | Headers có PII | Không log/forward tùy tiện |
| Integration | SMTP capture test | Xác nhận MIME được submit, không gửi thật |

## 33. Câu hỏi thường gặp

**1. MailSendingMessageHandler thuộc Spring Framework Mail hay Spring Integration?**

Nó thuộc Spring Integration Mail và sử dụng mail sender của Spring Framework Mail để thực hiện outbound SMTP.

**2. Nó có phải một MessageHandler không?**

Có. Nó đóng vai trò handler tiêu thụ Spring Messaging message và được đăng ký như một outbound endpoint.

**3. Có thể dùng với JavaMailSenderImpl không?**

Có. JavaMailSenderImpl là implementation phổ biến cho SMTP và có thể được inject vào handler.

**4. Khi nào dùng SimpleMailMessage?**

Khi cần email plain text đơn giản, không có HTML/multipart/attachment phức tạp.

**5. Khi nào dùng MimeMessage?**

Khi cần HTML, multipart/alternative, attachment, inline resource hoặc MIME headers phong phú.

**6. Handler có tự render Thymeleaf template không?**

Không nên coi đó là nhiệm vụ của handler. Render template ở một composer/transformer trước khi đưa mail payload vào outbound flow.

**7. Có thể gửi payload String thẳng vào handler không?**

Không nên dựa vào giả định chung nếu chưa xác định contract/configuration của phiên bản. Với ứng dụng cần tính rõ ràng, tạo MailMessage/MimeMessage trong transformer trước.

**8. DirectChannel có làm gửi mail đồng bộ không?**

Với handler đồng bộ và DirectChannel, producer thường chờ việc xử lý handler hoàn tất trên cùng thread. Vì vậy, nó có thể chờ SMTP.

**9. ExecutorChannel có bảo đảm mail được gửi thành công sau khi send trả true không?**

Không. Kết quả đó có thể chỉ phản ánh message được chấp nhận dispatch, không phải SMTP đã hoàn tất.

**10. Có cần errorChannel khi dùng async không?**

Cần một chiến lược xử lý lỗi bất đồng bộ rõ ràng. Có thể sử dụng errorChannel và handler thích hợp, đồng thời ghi durable state nếu cần reliability.

**11. QueueChannel có tự lưu message qua restart không?**

Một QueueChannel in-memory thì không. Durability cần message store/broker hoặc transactional outbox được thiết kế đúng.

**12. Handler có tự retry SMTP 421 không?**

Không nên mặc định. Retry cần policy, advice hoặc worker orchestration, với backoff và giới hạn.

**13. Có thể gửi email trong @Transactional method không?**

Có thể về kỹ thuật, nhưng rủi ro SMTP side effect không rollback khi DB transaction rollback. Nên tách sau commit hoặc dùng outbox.

**14. AFTER_COMMIT listener đã đủ tin cậy chưa?**

Nó tránh gửi trước commit nhưng chưa durable qua crash giữa commit và gửi. Outbox mạnh hơn khi cần phục hồi chắc chắn.

**15. Gửi thành công có nghĩa người nhận đã đọc thư không?**

Không. SMTP submit success khác inbox delivery và read/open.

**16. Timeout có nghĩa relay chắc chắn chưa accept không?**

Không. Timeout sau DATA có thể làm outcome không xác định và retry có nguy cơ duplicate.

**17. Có thể dùng nhiều SMTP providers với handler không?**

Có thể cấu hình nhiều sender/handlers, route message đến channel phù hợp, rồi ghi provider attribution theo attempt.

**18. Handler có tự chọn provider tốt nhất không?**

Không. Router, health checks, rate limit và failover policy là trách nhiệm của kiến trúc ứng dụng.

**19. Có thể test handler mà không có SMTP server không?**

Có. Mock JavaMailSender, tạo MimeMessage trong bộ nhớ, gọi handleMessage hoặc gửi qua DirectChannel và verify lời gọi.

**20. Vì sao không test bằng inbox Gmail thật?**

Unit test sẽ phụ thuộc mạng, account, rate limit, spam filtering và có nguy cơ gửi nhầm. Cần SMTP capture server có kiểm soát cho integration test, mock cho unit test.

**21. Có thể gắn mailEventId vào Spring Message header không?**

Có thể để correlation nội bộ, nhưng không tự copy sang MIME headers hoặc metric labels. Cần chính sách privacy và audit.

**22. Dùng Spring Integration có làm SMTP nhanh hơn không?**

Không tự động. Nó giúp tổ chức flow và có thể hỗ trợ concurrency/routing, nhưng network và provider latency vẫn phải được đo/quản lý.

**23. Vì sao attachment có thể làm send chậm dù build nhanh?**

Resource có thể được đọc khi MIME serialize trong send; khi đó I/O của attachment nằm trong send-call latency.

**24. Có nên tạo một handler duy nhất rồi đổi SMTP host cho từng message?**

Không nên nếu sử dụng sender singleton giữa nhiều thread. Dùng các sender/handlers độc lập và router an toàn.

**25. Cần log những gì khi gửi thất bại?**

Event ID/attempt ID, mail kind, provider alias, error category, phase khi biết và duration. Tránh credentials, body, token và PII không cần thiết.

## 34. Ghi nhớ về MailSendingMessageHandler

**MailSendingMessageHandler là outbound channel adapter của Spring Integration Mail**, nối một Spring Messaging flow với hoạt động gửi email của **JavaMailSender**. Nó phù hợp khi ứng dụng muốn tách producer nghiệp vụ khỏi transport, chuẩn hóa transform/filter/router và tổ chức telemetry, error handling trong một integration flow.

Dùng **SimpleMailMessage** cho thư plain text và **MimeMessage/MimeMessageHelper** cho HTML hoặc multipart. Chuẩn bị đúng payload trước handler, validate recipient/From, kiểm soát attachment và không đưa nội dung/credentials nhạy cảm vào Spring Integration headers hoặc logs.

Chọn channel dựa trên semantics: **DirectChannel** thường xử lý đồng bộ, **ExecutorChannel** chuyển việc sang worker nhưng không làm tác vụ bền vững, và **QueueChannel** in-memory không tự bảo đảm khôi phục sau crash. Với email nghiệp vụ quan trọng, **transactional outbox** giúp giữ ý định gửi và quản lý retry sau commit; handler vẫn là bước thực hiện SMTP trong worker.

Cuối cùng, **send() trả thành công khác với email delivered hoặc được đọc**. Hãy đo và lưu kết quả từng attempt, phân biệt lỗi chuẩn bị với lỗi SMTP, thận trọng với timeout sau DATA và chỉ retry/failover theo policy có kiểm soát. Khi được đặt đúng ranh giới, MailSendingMessageHandler giúp hệ thống gửi mail có cấu trúc, dễ quan sát và dễ kiểm thử mà không nhầm integration messaging với bảo đảm chuyển phát.
