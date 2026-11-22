# Định tuyến message theo loại email

## 1. Định tuyến email inbound là gì?

Trong **Spring Integration Mail**, ứng dụng có thể nhận email từ mailbox thông qua **IMAP/POP3**, biến email thành một **Spring Integration Message**, rồi đưa message đến những luồng xử lý khác nhau. **Định tuyến message theo loại email** là bước quyết định email nào cần tới bộ phận hoặc quy trình nào dựa trên các tín hiệu đã được đọc và phân loại.

Ví dụ, một địa chỉ inbox chung có thể nhận:

- Email yêu cầu hỗ trợ từ khách hàng.
- Email phản hồi cho ticket đã có.
- Hóa đơn và chứng từ do đối tác gửi.
- Delivery Status Notification (DSN) báo email đã gửi bị bounce.
- Thông báo tự động từ hệ thống giám sát.
- Thư rác, thư không hợp lệ hoặc thư chưa nhận diện được loại.

Nếu tất cả email cùng đi tới một handler, handler sẽ phải chứa nhiều câu lệnh if/else, xử lý MIME, tra cứu ticket, cập nhật bounce, lưu attachment và quản lý lỗi. Điều này gây khó kiểm thử, dễ lẫn ranh giới bảo mật và khiến một loại email lỗi ảnh hưởng các loại còn lại.

Spring Integration cho phép tách thành ba trách nhiệm:

1. **Nhận thư:** kết nối mail server và nhận thông điệp.
2. **Phân loại:** trích xuất các thuộc tính cần thiết rồi xác định loại nghiệp vụ.
3. **Định tuyến:** chuyển message đã phân loại đến đúng channel/handler, có nhánh fallback cho trường hợp chưa biết.

**Định tuyến ở đây là routing bên trong ứng dụng**, không phải chuyển tiếp một email từ mail server này sang mail server khác. Chức năng của **RecipientListRouter**, **HeaderValueRouter**, **MethodInvokingRouter** hay **@Router** trong Spring Integration là quyết định **Spring Message channel đích**, không tự gửi lại email bằng SMTP.

## 2. Một ví dụ nghiệp vụ

Giả sử doanh nghiệp có một mailbox tích hợp:

~~~text
automation@example.com
~~~

Mailbox nhận các email:

| Email nhận được | Dấu hiệu | Loại nghiệp vụ | Handler |
|---|---|---|---|
| Khách hàng hỏi tình trạng đơn | Nội dung yêu cầu hỗ trợ | SUPPORT_REQUEST | Tạo ticket |
| Khách hàng trả lời email hỗ trợ | In-Reply-To/References và ticket hợp lệ | SUPPORT_REPLY | Cập nhật ticket |
| Đối tác gửi PDF hóa đơn | Nguồn đối tác được phép, attachment phù hợp | INVOICE | Quy trình tiếp nhận hóa đơn |
| Hệ thống nhận trả DSN | MIME report-type=delivery-status | DELIVERY_REPORT | Đối chiếu bounce/delivery |
| Hệ thống nội bộ gửi cảnh báo | Nguồn xác thực và định dạng được chấp nhận | SYSTEM_ALERT | Incident workflow |
| Email không đủ tín hiệu | Không match hoặc nhiều tín hiệu xung đột | UNKNOWN | Quarantine/triage |

Đây là **bảng quy tắc của ứng dụng**, không phải những loại message được khai báo sẵn trong Spring Integration Mail.

Một email có attachment PDF **không tự động là hóa đơn**; một Subject chứa chữ “invoice” cũng không chứng minh người gửi là đối tác đáng tin. Classifier phải kết hợp **tín hiệu cấu trúc, ngữ cảnh mailbox, dữ liệu nghiệp vụ và mức độ tin cậy**.

## 3. Sơ đồ luồng Spring Integration Mail

~~~text
                IMAP / POP3 mailbox
                        |
                        v
              Mail inbound adapter
                        |
                        v
                 rawMailChannel
                        |
                        v
             Normalize / MIME parse
                        |
                        v
              Durable inbox + dedup
                        |
                        v
              EmailTypeClassifier
                        |
                        v
               classifiedChannel
                        |
                        v
                 @Router
             /      |       \
            /       |        \
      support   delivery     invoice
      channel    channel     channel
         |         |           |
         v         v           v
      Ticket     Bounce      Document
      handler    handler      handler
            \      |       /
             \     |      /
                  UNKNOWN
                     |
                     v
            Quarantine / triage
~~~

Trong một hệ thống có yêu cầu không mất thư, bước **durable inbox** nên xuất hiện trước các side effect nghiệp vụ. Có thể phân loại trước khi ghi dữ liệu bền vững nếu lưu được cả kết quả và raw message trong cùng quy trình, nhưng không nên xóa/đánh dấu đã xử lý email trên server trước khi đã lưu đủ để khôi phục.

## 4. Phân biệt loại email, loại MIME và loại payload

Từ “loại” có ba ý nghĩa khác nhau:

**Loại nghiệp vụ (business email type):**

~~~text
SUPPORT_REQUEST
SUPPORT_REPLY
INVOICE
DELIVERY_REPORT
SYSTEM_ALERT
UNKNOWN
~~~

**MIME Content-Type:**

~~~text
text/plain
text/html
multipart/alternative
multipart/mixed
multipart/report
application/pdf
~~~

**Kiểu payload trong Spring Integration:**

~~~text
jakarta.mail.internet.MimeMessage
Custom InboundEmail record
Custom MailEvent record
String / byte[] / other payload type
~~~

Không nên dùng ba khái niệm thay cho nhau. Một email hóa đơn có thể là **multipart/mixed**, một email hỗ trợ cũng có thể là **multipart/mixed**. Cả hai cùng chứa HTML và PDF nhưng phải đi vào handler khác nhau.

Để routing theo nghiệp vụ dễ hiểu, nên xác định **EmailType** trước rồi định tuyến dựa trên giá trị đó, thay vì routing trực tiếp bằng chuỗi Content-Type.

## 5. Spring Mail và Spring Integration Mail đóng vai trò gì?

| Thành phần | Vai trò trong ứng dụng |
|---|---|
| **JavaMailSender** | Tạo/gửi email ra SMTP; không phải inbound mailbox router |
| **Jakarta Mail Session/Store/Folder/Message** | Kết nối IMAP/POP3 và đọc nội dung email |
| **ImapMailReceiver / Pop3MailReceiver** | Thành phần nhận thư trong Spring Integration Mail |
| **MailReceivingMessageSource** | Làm nguồn cho một polling flow |
| **IMAP IDLE inbound adapter** | Nhận tín hiệu mailbox thay đổi khi server hỗ trợ IDLE |
| **Transformer** | Chuẩn hóa MimeMessage thành dữ liệu ứng dụng |
| **Filter** | Chặn message không phù hợp một điều kiện |
| **Router** | Chọn một hoặc nhiều output channels |
| **ServiceActivator** | Xử lý message ở channel phù hợp |
| **Error channel** | Điểm nhận lỗi ở những flow có error handling bất đồng bộ |
| **Persistent inbox/queue** | Ghi trạng thái chống trùng và cho phép retry độc lập |

**Spring Integration** tổ chức các thành phần trên thành **Enterprise Integration Patterns** như Message Channel, Message Router, Filter, Transformer và Service Activator.

Không phải mọi endpoint đều có một giao dịch ACID chung. Đặc biệt **IMAP/POP3 server không tham gia transaction của database** ứng dụng, và việc một channel chuyển message thành công không đồng nghĩa đã xử lý nghiệp vụ hoàn tất.

## 6. Routing là quyết định về kênh, không tự động là xử lý thành công

Giả sử:

~~~text
INVOICE email
     |
     v
Router -> invoiceChannel
     |
     v
InvoiceHandler
     |
     +-- Object storage unavailable
     |
     v
Exception
~~~

Router đã chọn đúng kênh, nhưng invoice vẫn xử lý thất bại. Vì vậy phải có:

- **Trạng thái inbox** cho từng email nhận.
- **Error handling** và retry phù hợp từng loại.
- **Idempotency** để retry không tạo hai hóa đơn hoặc ticket.
- **Quarantine/dead-letter** cho dữ liệu không thể xử lý.
- **Metrics** phân tách lỗi phân loại, lỗi routing và lỗi handler.

Một thiết kế coi “đã route” là “đã xử lý” có nguy cơ mất dữ liệu khi application crash hoặc downstream service tạm unavailable.

## 7. Định nghĩa EmailType như một domain enum

Ví dụ:

~~~java
public enum EmailType {
    DELIVERY_REPORT,
    SUPPORT_REPLY,
    SUPPORT_REQUEST,
    INVOICE,
    SYSTEM_ALERT,
    UNKNOWN
}
~~~

Thứ tự trong enum không tự mang ý nghĩa ưu tiên; thứ tự **quy tắc classifier** mới quyết định điều gì được xét trước.

Một số loại cần mức độ tin cậy đặc biệt:

- **DELIVERY_REPORT**: dựa vào cấu trúc DSN đáng tin và correlation, không dựa vào Subject “Delivery failure”.
- **SUPPORT_REPLY**: cần đối chiếu ticket qua thread/correlation và quyền người trả lời.
- **INVOICE**: không chỉ nhìn filename .pdf mà cần chính sách nguồn, định dạng và kiểm tra file.
- **SYSTEM_ALERT**: cần nguồn được xác thực thay vì cho phép bất kỳ người gửi nào tự gắn Subject “ALERT”.
- **UNKNOWN**: là kết quả hợp lệ của classifier khi chưa đủ bằng chứng, không phải exception bắt buộc.

## 8. Model đầu vào sau khi chuẩn hóa

Đừng buộc mọi handler tự đọc **MimeMessage** và tự xử lý các MIME parts. Có thể thiết kế một model chung:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;

public record InboundEmail(
        String inboxId,
        String tenantId,
        String mailboxId,
        String fromAddress,
        List<String> toAddresses,
        String subject,
        String messageId,
        List<String> referenceMessageIds,
        String plainText,
        String sanitizedHtml,
        List<AttachmentRef> attachments,
        String rawMessageRef,
        Instant receivedAt,
        EmailType type,
        Map<String, String> routingFacts
) {
}

public record AttachmentRef(
        String storageKey,
        String safeDisplayName,
        String detectedMediaType,
        long sizeBytes
) {
}
~~~

Đây là **domain model minh họa**, không phải class có sẵn trong Spring Integration.

Những nguyên tắc khi tạo model:

1. **tenantId/mailboxId** đến từ cấu hình connector được xác thực, không tin MIME header do sender tự đặt.
2. **inboxId** là định danh bền vững để chống trùng và truy vết.
3. **rawMessageRef** tham chiếu bản EML đã lưu trong vùng bảo vệ khi cần đối soát.
4. **attachments** chỉ chứa reference tới dữ liệu đã lưu/scan hoặc đang quarantine, không cần nhét toàn bộ file vào Spring Message.
5. **sanitizedHtml** khác với raw HTML, vì HTML nhận từ email không được tin cậy.
6. **type** là kết quả phân loại; có thể lưu riêng version của classifier.
7. **routingFacts** chỉ chứa metadata đã chuẩn hóa, không đưa raw body hoặc PII không cần thiết vào metric labels.

Trong ứng dụng thật, nên có validation và defensive copy cho những list/map; model ở đây tập trung vào ranh giới trách nhiệm.

## 9. Chọn thời điểm phân loại

Có ba chiến lược:

| Thời điểm | Lợi ích | Đánh đổi |
|---|---|---|
| **Trước khi persist** | Có thể route nhanh, giảm lưu dữ liệu nếu email không phù hợp | Nếu process crash trước persist, có thể mất dấu; khó reclassify |
| **Sau khi persist raw EML** | Có nguồn dữ liệu để retry, audit và thay đổi classifier | Tốn storage; cần bảo vệ raw content |
| **Hai giai đoạn: coarse và deep** | Phân loại sơ bộ bằng headers rồi kiểm tra MIME/attachment khi cần | Cần quản lý trạng thái và sự khác biệt giữa hai lần phân loại |

Với hệ thống nghiệp vụ cần tính tin cậy, lựa chọn phổ biến là:

~~~text
Fetch -> assign mailbox identity -> persist safely
      -> parse -> classify -> route -> process
~~~

Đối với mailbox có traffic rất lớn, có thể tối ưu bằng **header-first inspection**, nhưng không được coi phân loại dựa trên header chưa được xác minh là căn cứ cho thao tác nhạy cảm.

## 10. Dependency và cấu hình cơ bản

Ví dụ một dự án **Spring Boot** hiện đại dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    // Khi ứng dụng có gửi SMTP ra ngoài.
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Spring Integration Mail** hỗ trợ inbound email; starter-mail dành cho chức năng gửi SMTP thường được dùng cùng ứng dụng nhưng không phải điều kiện bắt buộc của mọi inbound-only application.

Ví dụ Java dưới đây dùng **jakarta.mail.***, phù hợp với dòng Spring Framework/Spring Integration dùng Jakarta Mail. Những dự án cũ dùng **javax.mail.*** phải lựa chọn dependency và API tương thích, không trộn hai namespace.

Cần xác nhận **Spring Boot, Spring Integration và Jakarta Mail** thuộc cùng thế hệ được hỗ trợ. Ví dụ DSL/annotation có thể thay đổi giữa các phiên bản; những đoạn mã sau minh họa một kiến trúc hợp lý, không thay thế việc cấu hình receiver/authentication cụ thể với provider.

## 11. Tạo inbound receiver và đưa vào một input channel

Với Spring Integration Mail, một lựa chọn là **poll IMAP** bằng **ImapMailReceiver** kết hợp **MailReceivingMessageSource**.

Mô hình:

~~~text
ImapMailReceiver
        |
        v
MailReceivingMessageSource
        |
        v
Inbound channel adapter + Poller
        |
        v
mailRawChannel
~~~

Ví dụ khung khai báo flow:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class MailPollingFlowConfiguration {

    @Bean
    public IntegrationFlow imapPollingFlow(
            MailReceivingMessageSource source
    ) {
        return IntegrationFlow
                .from(
                        source,
                        spec -> spec.poller(
                                Pollers.fixedDelay(
                                        30,
                                        TimeUnit.SECONDS
                                )
                        )
                )
                .channel("mailRawChannel")
                .get();
    }
}
~~~

Đoạn này giả định **MailReceivingMessageSource** đã được cấu hình thành bean bởi ứng dụng với **ImapMailReceiver** phù hợp. Mail receiver phải có endpoint, TLS, authentication và policy đọc/mark messages rõ ràng. Không đưa username/password vào source code hoặc log URL chứa credential.

Đây là flow **polling**, không phải IMAP IDLE. Nếu sử dụng IDLE, thành phần inbound adapter và quản lý reconnect khác đi, nhưng phần **normalize → classify → route** phía sau có thể được tái sử dụng.

### Chú ý payload đầu vào

Tùy adapter, header mapper và cấu hình receiver, payload có thể là **Jakarta Mail Message/MimeMessage** hoặc một dạng đã được chuyển đổi. Ví dụ phía dưới giả định payload là **MimeMessage**.

Trước khi nối các bước, cần nắm đúng contract của adapter trong phiên bản Spring Integration đang chạy. Không cast mọi payload thành MimeMessage nếu cấu hình receiver thực tế đã tạo payload kiểu khác.

## 12. Khai báo các MessageChannel có tên ổn định

Để minh họa việc định tuyến, có thể dùng các **DirectChannel**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class MailRoutingChannels {

    @Bean
    public MessageChannel mailRawChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailClassifiedChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailDeliveryReportChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSupportReplyChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSupportRequestChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailInvoiceChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSystemAlertChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailUnknownChannel() {
        return new DirectChannel();
    }
}
~~~

Trong thực tế, **Spring Integration có thể tự tạo/resove một số channel theo tên** tùy cấu hình. Việc khai báo rõ ở đây giúp tài liệu chỉ ra được những kênh nào tồn tại và người vận hành có thể gắn interceptor/metrics theo từng channel.

### DirectChannel có ý nghĩa gì?

**DirectChannel** gọi subscriber trong thread của bên gửi theo cách trực tiếp. Nó không phải một queue bền vững. Nếu handler ném exception, lỗi có thể lan ngược về bước upstream trong cùng chuỗi xử lý đồng bộ.

Khi cần xử lý bất đồng bộ hoặc isolation tốt hơn, có thể chuyển sang **ExecutorChannel**, **QueueChannel**, message broker hoặc **persistent inbox + worker**. Tuy nhiên thay channel không tự mang lại lưu trữ bền vững hay exactly-once; phải xác định cấu hình persistence và acknowledgment.

## 13. Chuẩn hóa MimeMessage trước khi route

Một message từ inbound adapter có thể có:

~~~text
From: customer@example.net
To: support@example.com
Subject: Re: Ticket #123
In-Reply-To: <ticket-123@service.example>
Content-Type: multipart/mixed
~~~

Không nên để mỗi handler tự parse lại header, MIME và attachment. Một **Transformer** có thể chuyển từ đối tượng Jakarta Mail sang domain model:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class MailNormalizationTransformer {

    private final InboundMailNormalizer normalizer;
    private final EmailTypeClassifier classifier;

    public MailNormalizationTransformer(
            InboundMailNormalizer normalizer,
            EmailTypeClassifier classifier
    ) {
        this.normalizer = normalizer;
        this.classifier = classifier;
    }

    @Transformer(
            inputChannel = "mailRawChannel",
            outputChannel = "mailClassifiedChannel"
    )
    public InboundEmail normalize(MimeMessage raw)
            throws Exception {

        InboundEmail candidate = normalizer.normalize(raw);
        return classifier.withType(candidate);
    }
}
~~~

**InboundMailNormalizer** và **EmailTypeClassifier** là interface/service do ứng dụng định nghĩa, không phải class có sẵn của Spring Integration.

Điều normalizer cần làm tùy bài toán:

- Gắn **mailboxId/tenantId** từ cấu hình receiver đáng tin cậy.
- Lấy From/To/Subject/Message-ID, In-Reply-To/References khi cần.
- Parse MIME theo giới hạn size/depth/parts.
- Trích xuất plain text/HTML và attachment references.
- Ghi raw email hoặc identifier bền vững trước khi gây side effect.
- Xác định các routing signals an toàn và trạng thái nghi ngờ.

Ví dụ chỉ biểu diễn **ràng buộc kênh và kiểu dữ liệu**; thiết kế production cần cung cấp mailbox context theo adapter đã được xác thực. Nếu nguồn vào từ nhiều mailbox, không nên dùng một normalizer mặc định gắn cứng tất cả email vào cùng tenant.

## 14. Tách classifier khỏi Spring Router

**Classifier** quyết định một email thuộc loại nào. **Router** quyết định loại đó đi tới channel nào.

~~~text
InboundEmail raw facts
         |
         v
EmailTypeClassifier
         |
         +-- EmailType.INVOICE
         |
         v
Spring Integration Router
         |
         +-- mailInvoiceChannel
~~~

Lợi ích của việc tách hai bước:

- Unit test classifier như một hàm nghiệp vụ, không cần khởi động Spring Integration.
- Thay đổi channel topology mà không sửa quy tắc phân loại.
- Thay classifier version mà không làm thay đổi logic retry/dispatch.
- Cho phép reclassify email đang ở trạng thái UNKNOWN bằng một workflow có kiểm soát.
- Log/metric biết liệu lỗi xảy ra ở **classification** hay **routing/channel resolution**.

Một model tín hiệu:

~~~java
public record ClassificationSignals(
        boolean suspiciousOrMalformed,
        boolean correlatedDeliveryReport,
        boolean authorizedTicketReply,
        boolean trustedInvoiceSource,
        boolean validatedInvoiceAttachment,
        boolean authenticatedSystemAlert,
        boolean eligibleSupportRequest
) {
}
~~~

Các boolean mang nghĩa đã được xác minh bởi những thành phần phù hợp. Ví dụ **authorizedTicketReply** không phải kết quả của việc Subject chứa “Re:”, mà là kết quả đối chiếu ticket/thread và quyền được trả lời.

## 15. Ví dụ classifier có thứ tự ưu tiên

~~~java
public final class DefaultEmailClassifier {

    public EmailType classify(ClassificationSignals signals) {

        if (signals.suspiciousOrMalformed()) {
            return EmailType.UNKNOWN;
        }

        if (signals.correlatedDeliveryReport()) {
            return EmailType.DELIVERY_REPORT;
        }

        if (signals.authorizedTicketReply()) {
            return EmailType.SUPPORT_REPLY;
        }

        if (signals.trustedInvoiceSource()
                && signals.validatedInvoiceAttachment()) {
            return EmailType.INVOICE;
        }

        if (signals.authenticatedSystemAlert()) {
            return EmailType.SYSTEM_ALERT;
        }

        if (signals.eligibleSupportRequest()) {
            return EmailType.SUPPORT_REQUEST;
        }

        return EmailType.UNKNOWN;
    }
}
~~~

Thứ tự trong ví dụ là **policy minh họa**, không phải thứ tự chung cho mọi tổ chức:

- Email DSN được xét sớm để tránh đưa bounce vào support ticket.
- Reply đã xác thực được phân biệt với support request mới.
- Invoice yêu cầu cả nguồn phù hợp và attachment đã kiểm tra.
- System alert chỉ được xem là alert khi có bằng chứng xác thực.
- Trường hợp không đủ tín hiệu đi vào UNKNOWN.

Nếu nhiều quy tắc đồng thời đúng nhưng không có một thứ tự ưu tiên nghiệp vụ rõ ràng, có thể chọn **AMBIGUOUS/UNKNOWN để triage** thay vì lặng lẽ nhận nhánh đầu tiên.

### Không sử dụng mọi boolean như giá trị do sender tự khai

Những tín hiệu như trustedInvoiceSource, correlatedDeliveryReport hay authenticatedSystemAlert phải đến từ **quy trình xác minh của hệ thống**, không phải một MIME header tự khai:

~~~text
X-Email-Type: INVOICE
~~~

Một người gửi bên ngoài có thể tự tạo header đó. Nếu dùng custom header, cần xác định được **nguồn đáng tin**, chữ ký hay kênh phân phối có kiểm soát.

## 16. Định tuyến bằng @Router

Annotation **@Router** của Spring Integration có thể nhận payload kiểu domain rồi trả về tên channel đích:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.stereotype.Component;

@Component
public class InboundEmailRouter {

    @Router(inputChannel = "mailClassifiedChannel")
    public String route(InboundEmail email) {
        return switch (email.type()) {
            case DELIVERY_REPORT -> "mailDeliveryReportChannel";
            case SUPPORT_REPLY -> "mailSupportReplyChannel";
            case SUPPORT_REQUEST -> "mailSupportRequestChannel";
            case INVOICE -> "mailInvoiceChannel";
            case SYSTEM_ALERT -> "mailSystemAlertChannel";
            case UNKNOWN -> "mailUnknownChannel";
        };
    }
}
~~~

Trong ví dụ:

1. Transformer tạo **InboundEmail** có type đã xác định.
2. **@Router** nhận InboundEmail từ **mailClassifiedChannel**.
3. Phương thức **route(...)** trả tên channel bean tương ứng.
4. Spring Integration chuyển message sang channel được chọn.
5. Một **ServiceActivator** đăng ký ở channel đó xử lý nghiệp vụ.

**Không return null** để xử lý UNKNOWN nếu chưa biết chính xác semantics của router và discard configuration đang dùng. Một kênh **mailUnknownChannel** rõ ràng giúp giữ email chưa phân loại và giám sát chúng.

### Switch expression và exhaustive cases

Việc route trên enum với **switch** rõ ràng giúp khi thêm một EmailType mới, người phát triển phải quyết định channel cho type đó (tùy ngôn ngữ/biểu thức có được compile exhaustively hay không). Điều này an toàn hơn routing bằng chuỗi dynamic có thể tạo tên channel từ input chưa tin cậy.

## 17. Xử lý theo channel bằng Service Activator

Ví dụ:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class MailBusinessHandlers {

    private final TicketService ticketService;
    private final InvoiceIngestionService invoiceService;
    private final DeliveryReportService deliveryReportService;
    private final AlertIngestionService alertService;
    private final MailTriageService triageService;

    public MailBusinessHandlers(
            TicketService ticketService,
            InvoiceIngestionService invoiceService,
            DeliveryReportService deliveryReportService,
            AlertIngestionService alertService,
            MailTriageService triageService
    ) {
        this.ticketService = ticketService;
        this.invoiceService = invoiceService;
        this.deliveryReportService = deliveryReportService;
        this.alertService = alertService;
        this.triageService = triageService;
    }

    @ServiceActivator(inputChannel = "mailSupportRequestChannel")
    public void createTicket(InboundEmail email) {
        ticketService.openFromInboundMail(email);
    }

    @ServiceActivator(inputChannel = "mailSupportReplyChannel")
    public void appendReply(InboundEmail email) {
        ticketService.appendAuthorizedReply(email);
    }

    @ServiceActivator(inputChannel = "mailInvoiceChannel")
    public void ingestInvoice(InboundEmail email) {
        invoiceService.ingest(email);
    }

    @ServiceActivator(inputChannel = "mailDeliveryReportChannel")
    public void recordDelivery(InboundEmail email) {
        deliveryReportService.process(email);
    }

    @ServiceActivator(inputChannel = "mailSystemAlertChannel")
    public void recordAlert(InboundEmail email) {
        alertService.ingest(email);
    }

    @ServiceActivator(inputChannel = "mailUnknownChannel")
    public void quarantine(InboundEmail email) {
        triageService.quarantine(email);
    }
}
~~~

**TicketService, InvoiceIngestionService, DeliveryReportService, AlertIngestionService, MailTriageService** là interface/service của ứng dụng. Spring Integration chỉ cung cấp cơ chế gọi chúng khi message được đưa vào đúng input channel.

Các handler nên **idempotent** theo inboxId và business key. Một message có thể được deliver lại sau retry, restart hoặc khi bị đưa lại vào channel; handler không được mặc định chỉ được chạy đúng một lần.

## 18. Routing bằng Java DSL và channel mapping

Ngoài annotation **@Router**, Spring Integration Java DSL còn cho phép khai báo định tuyến trong một **IntegrationFlow**. Một ý tưởng thường gặp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ClassifiedMailFlow {

    @Bean
    public IntegrationFlow routeClassifiedMail() {
        return IntegrationFlow
                .from("mailClassifiedChannel")
                .route(
                        InboundEmail.class,
                        InboundEmail::type,
                        mapping -> mapping
                                .channelMapping(
                                        EmailType.DELIVERY_REPORT,
                                        "mailDeliveryReportChannel"
                                )
                                .channelMapping(
                                        EmailType.SUPPORT_REPLY,
                                        "mailSupportReplyChannel"
                                )
                                .channelMapping(
                                        EmailType.SUPPORT_REQUEST,
                                        "mailSupportRequestChannel"
                                )
                                .channelMapping(
                                        EmailType.INVOICE,
                                        "mailInvoiceChannel"
                                )
                                .channelMapping(
                                        EmailType.SYSTEM_ALERT,
                                        "mailSystemAlertChannel"
                                )
                                .defaultOutputChannel(
                                        "mailUnknownChannel"
                                )
                )
                .get();
    }
}
~~~

Đoạn này minh họa cách dùng **payload-based route với channel mappings**. Các overload và class DSL phải được chọn phù hợp với phiên bản Spring Integration thực tế.

**Chọn một trong hai kiểu khai báo:** nếu đã dùng **@Router(inputChannel = "mailClassifiedChannel")** như mục trước, đừng đồng thời cấu hình thêm DSL flow trên cùng channel mà không chủ động thiết kế **competing consumers**. Hai router đăng ký như các subscriber độc lập trên DirectChannel có thể gây xung đột/không xác định endpoint nào nhận, tùy channel/dispatcher.

Trong tài liệu này, hai đoạn @Router và DSL là **hai lựa chọn thay thế**, không phải hai bean phải bật cùng lúc.

### Vì sao channel mapping tốt hơn tạo tên channel từ chuỗi?

Không nên để dữ liệu do người gửi tự khai điều khiển output channel:

~~~java
// Anti-pattern: giá trị do email khai tự tạo tên channel.
return "mail" + rawHeaderValue + "Channel";
~~~

Một email độc hại hoặc sai định dạng có thể làm router tìm một channel không hợp lệ hoặc không được dự kiến. Hãy dùng **enum allowlist** và mapping xác định để giữ topology an toàn.

## 19. Routing theo header: khi nào dùng HeaderValueRouter?

Spring Integration cung cấp hướng **HeaderValueRouter** để lấy một Spring Message header làm routing key, ví dụ:

~~~text
Spring Message:
  payload = InboundEmail
  headers:
    emailType = INVOICE
~~~

Luồng ý tưởng:

~~~text
Classification transformer
      |
      +-- Set header emailType = INVOICE
      |
      v
HeaderValueRouter(emailType)
      |
      +-- INVOICE -> mailInvoiceChannel
      +-- UNKNOWN -> mailUnknownChannel
~~~

Điều kiện bắt buộc: **emailType trong Spring Message header phải do classifier của ứng dụng tạo ra**, không phải tự động sao chép một raw MIME header như **X-Email-Type** từ người gửi.

Trong Spring Integration, **Spring Message headers** và **MIME headers** không phải cùng một hệ thống:

- MIME header đến từ email, có thể bị giả.
- Spring Message header dùng để truyền metadata trong integration pipeline.
- Không nên mặc định mọi metadata nội bộ đều trở nên đáng tin chỉ vì nó đã được đặt thành Spring Message header.
- Transformer/header enricher cần giữ ranh giới nguồn dữ liệu và chỉ tạo các khóa đáng tin sau khi xác minh.

**Payload-based router** thường phù hợp khi domain model có EmailType typed. **HeaderValueRouter** phù hợp khi kiểu routing là metadata chung cho nhiều payload hoặc được middleware quyết định.

## 20. Routing một đích hay nhiều đích?

Một email đôi khi phục vụ nhiều mục đích:

~~~text
Email invoice:
  -> Lưu chứng từ
  -> Tạo audit event
  -> Cập nhật báo cáo
~~~

Cần phân biệt:

- **Router chọn luồng nghiệp vụ chính**: ví dụ INVOICE đi tới invoiceChannel.
- **Fan-out sau khi xử lý**: invoice service phát event đã ingest thành công tới audit/reporting.
- **RecipientListRouter / PublishSubscribeChannel**: có thể gửi cùng một Spring Message đến nhiều channel/subscriber khi thiết kế yêu cầu.

Không nên route một email thẳng tới ba handler có side effect rồi coi tất cả là một giao dịch nguyên tử:

~~~text
Invoice email
  |
  +-- create invoice (success)
  +-- write audit (success)
  +-- send acknowledgement (failure)
~~~

Nếu fan-out đồng bộ không có transaction phù hợp, retry cả email có thể tạo invoice trùng.

Kiến trúc an toàn hơn:

~~~text
INVOICE -> InvoiceIngestionService
             |
             v
       DB transaction commit
             |
             v
       Business outbox event
             |
         +---+---+
         |       |
         v       v
        Audit   Report
~~~

**Định tuyến một đích cho trách nhiệm chính** giúp ownership/rollback rõ hơn. Những side effects bổ sung có thể phát sinh từ một event bền vững sau khi nghiệp vụ chính hoàn tất.

## 21. Quy tắc ưu tiên và xung đột

Một email có thể mang đồng thời nhiều tín hiệu:

~~~text
Subject: Re: Invoice #123
In-Reply-To: <ticket-123@service.example>
Attachment: invoice.pdf
From: external-partner@example.net
Content-Type: multipart/mixed
~~~

Có nên coi đây là **SUPPORT_REPLY** hay **INVOICE**?

Không có câu trả lời chung. Những nguyên tắc nên dùng:

1. **Xác định quyền và ngữ cảnh mailbox trước.** Một mailbox chuyên nhận invoice có thể ưu tiên luồng invoice hơn mailbox support.
2. **Đối chiếu correlation có thể tin cậy.** Thread được xác nhận thuộc ticket hiện có là tín hiệu mạnh hơn chữ “Re:” trong subject.
3. **Không coi attachment là bằng chứng duy nhất.** File PDF có thể chỉ là tài liệu gửi kèm phản hồi.
4. **Dùng thứ tự ưu tiên được mô tả bằng policy**, không dựa vào thứ tự ngẫu nhiên của một map.
5. **Khi xung đột không giải quyết được**, chuyển triage/UNKNOWN thay vì âm thầm chọn nhánh ít an toàn.

Ví dụ có thể bổ sung enum:

~~~java
public enum ClassificationOutcome {
    MATCHED,
    AMBIGUOUS,
    UNKNOWN,
    REJECTED_UNSAFE
}
~~~

Sau đó lưu cả **type** và **outcome** để người vận hành biết một email được route vì bằng chứng gì. Nếu policy chỉ dùng EmailType.UNKNOWN, vẫn nên lưu reason code riêng như **CONFLICTING_SIGNALS** hoặc **UNVERIFIED_SENDER**.

## 22. DSN/bounce: không phân loại chỉ bằng Subject

Một DSN có thể có MIME structure:

~~~text
Content-Type: multipart/report;
  report-type=delivery-status
  |
  +-- text/plain
  |
  +-- message/delivery-status
  |
  +-- message/rfc822-headers (optional)
~~~

Trong phần **message/delivery-status** có thể có:

~~~text
Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Một classifier đáng tin nên kết hợp:

- MIME subtype và **report-type** của DSN.
- Các trường delivery-status có cấu trúc.
- Kiểm tra nguồn message hoặc ingestion path phù hợp.
- **Correlation** với notification-recipient do ứng dụng đã gửi.
- Các quy tắc chống DSN giả mạo, backscatter và duplicate.

Không nên:

~~~java
// Không đủ để quyết định DELIVERY_REPORT.
if (subject.contains("Mail delivery failed")) {
    return EmailType.DELIVERY_REPORT;
}
~~~

Người gửi bên ngoài có thể tạo một email thường với Subject như vậy. Nếu handler dùng email giả đó để suppress recipient, hệ thống có thể chặn nhầm người nhận hợp lệ.

### Cần phân biệt routing với xác nhận kết quả chuyển phát

Một email được phân loại DELIVERY_REPORT chưa đủ để kết luận tất cả recipient đã hard bounce. Handler vẫn phải parse:

- **Action** failed/delayed/delivered/...
- **Status** và Diagnostic-Code.
- Những recipient cụ thể liên quan.
- Provider event/notification correlation.
- Chính sách chuyển trạng thái delivery phù hợp.

Router chỉ chọn **mailDeliveryReportChannel**, còn **DeliveryReportService** chịu trách nhiệm xác định và cập nhật trạng thái bền vững.

## 23. Phân loại phản hồi theo In-Reply-To/References

Một email trả lời có thể có:

~~~text
Message-ID: <reply-456@customer.example>
In-Reply-To: <support-123@service.example>
References: <support-123@service.example>
Subject: Re: Yêu cầu hỗ trợ 123
~~~

Để route thành **SUPPORT_REPLY**, ứng dụng có thể:

1. Lấy In-Reply-To và References từ headers qua Jakarta Mail.
2. Đối chiếu với bảng **outbound_message_correlation** của ứng dụng.
3. Tìm ticket hợp lệ gắn với message ID/correlation token.
4. Kiểm tra người gửi hoặc tenant có quyền cập nhật ticket theo chính sách.
5. Nếu match và authorized thì phân loại SUPPORT_REPLY.
6. Nếu không, có thể route SUPPORT_REQUEST hoặc UNKNOWN tùy mailbox policy.

**Không xem In-Reply-To là bằng chứng xác thực**. Sender có thể tự đặt header và tham chiếu tới Message-ID của người khác nếu nhìn thấy giá trị đó. Việc kiểm tra quyền thay đổi ticket phải được thực hiện độc lập.

### Khi Subject có mã ticket

Ví dụ:

~~~text
Subject: [TICKET-123] Tôi muốn bổ sung ảnh
~~~

Mã ticket có thể là tín hiệu bổ trợ, nhưng nếu mã dễ đoán thì không đủ để nhận quyền cập nhật ticket. Có thể dùng **opaque reply token** hoặc định tuyến bằng địa chỉ nhận riêng cho từng thread, kết hợp với kiểm tra identity/authorization và retention.

## 24. Phân loại hóa đơn: tài liệu đính kèm là điều kiện cần hay đủ?

Một email có file **invoice.pdf** không chắc đã là hóa đơn hợp lệ.

Ví dụ:

~~~text
From: vendor@example.net
To: invoices@example.com
Subject: Invoice INV-2026-104
Content-Type: multipart/mixed
Attachment: invoice.pdf
~~~

Classifier có thể dùng:

| Tín hiệu | Mức tin cậy |
|---|---|
| Hộp thư nhận là mailbox invoice được cấu hình | Định tuyến sơ bộ hữu ích |
| From thuộc danh sách đối tác | Cần xác thực nguồn, không chỉ so chuỗi |
| DKIM/DMARC từ trust boundary phù hợp | Tăng bằng chứng về domain, chưa chứng minh nghiệp vụ |
| MIME part có attachment | Cho biết có file |
| File type được kiểm tra từ bytes và policy | Mạnh hơn chỉ dựa extension |
| Invoice number khớp đơn hàng/đối tác | Bằng chứng nghiệp vụ |
| Chữ ký/format của chứng từ hợp lệ | Phụ thuộc bài toán |

Định tuyến có thể chia hai giai đoạn:

~~~text
Header-level candidate = POSSIBLE_INVOICE
          |
          v
Attachment quarantine / scan / metadata validation
          |
          v
CLASSIFIED = INVOICE or UNKNOWN/REJECTED_UNSAFE
~~~

Nếu scan tệp lâu, không cần giữ phiên IMAP và router thread đang chờ. Có thể persist email rồi chuyển sang document validation worker có budget và timeout riêng.

## 25. Phân loại cảnh báo hệ thống

Một số tổ chức nhận email từ hệ thống giám sát hoặc dịch vụ bên ngoài:

~~~text
From: monitor@alerts.example
Subject: CRITICAL Database latency
X-Alert-Type: database
~~~

**Không nên** route tới luồng tự động xử lý sự cố chỉ dựa trên Subject bắt đầu bằng “CRITICAL” hoặc header X-Alert-Type.

Cần xác minh:

- Mailbox/kênh nhận đã được dành riêng và bảo vệ chưa.
- Nhà cung cấp có chữ ký, API credential hoặc cơ chế xác thực domain nào.
- Message có tương ứng một integration đã đăng ký không.
- Payload có schema hợp lệ và không chứa lệnh tùy ý.
- Quyền tác động của alert handler giới hạn ở mức nào.

Nếu email hệ thống có thể kích hoạt restart, mở quyền truy cập hoặc chuyển tài sản, cần **approval hoặc xác thực ngoài email** cho các hành động có rủi ro.

### Email không phải command channel đáng tin cậy theo mặc định

Nhận một email từ một địa chỉ “trông giống admin” không đủ để thực hiện một thao tác nhạy cảm. Routing chỉ chọn quy trình kiểm tra tiếp theo, không tự tạo quyền cho người gửi.

## 26. Email không xác định phải đi đâu?

Luồng UNKNOWN nên được thiết kế như một kết quả nghiệp vụ bình thường:

~~~text
Unknown or ambiguous email
           |
           v
mailUnknownChannel
           |
           v
Store reason code + raw reference
           |
           v
Quarantine / manual triage queue
           |
           +-- Reclassify after rule update
           +-- Assign to support
           +-- Reject under policy
           +-- Delete after retention
~~~

Các lý do có thể được chuẩn hóa:

~~~text
UNSUPPORTED_MIME
MALFORMED_MESSAGE
UNTRUSTED_SENDER
CONFLICTING_SIGNALS
NO_MATCHING_RULE
MISSING_REQUIRED_ATTACHMENT
CORRELATION_NOT_FOUND
POLICY_REJECTED
~~~

Không nên dùng một channel UNKNOWN để **drop silently** mọi email chưa phân loại nếu có rủi ro đánh mất dữ liệu nghiệp vụ quan trọng.

Nhưng cũng không nên vô hạn lưu tất cả spam và attachment khổng lồ. Cần chính sách retention, size cap, quarantine storage và chống lạm dụng.

## 27. Định tuyến theo nhiều chiều: tenant, mailbox và type

Trong SaaS, **EmailType** thường không đủ để chọn handler:

~~~text
Tenant A / support inbox / SUPPORT_REPLY
    -> Ticket service của tenant A

Tenant B / support inbox / SUPPORT_REPLY
    -> Ticket service của tenant B

Tenant A / invoice inbox / INVOICE
    -> Invoice workflow của tenant A
~~~

Mô hình đúng:

~~~text
Authenticated mailbox configuration
           |
           +-- tenantId
           +-- mailboxId
           +-- allowed email types
           |
           v
EmailTypeClassifier
           |
           v
Router -> typed channel
           |
           v
Tenant-scoped handler (authorization enforced)
~~~

Đừng tạo dynamic channel name từ **tenantId do người gửi cung cấp**. Trong đa số trường hợp, handler có thể dùng **cùng một channel theo EmailType** nhưng thực thi với tenant context đã xác thực và kho dữ liệu có tenant-scoped authorization.

Nếu cần isolation mạnh, có thể phân vùng worker/queue theo tenant hoặc nhóm tenant, nhưng routing và quota topology phải được quản lý từ cấu hình nội bộ, không từ raw MIME header.

## 28. Định tuyến và chống trùng: đừng dựa vào một lần poll

Một email có thể xuất hiện nhiều lần ở inbound flow:

- IMAP polling lặp lại cùng thư khi ứng dụng chưa đánh dấu hoặc chưa lưu checkpoint.
- IMAP IDLE mất kết nối rồi đồng bộ bù từ UID cũ.
- POP3 giữ thư trên server và tải lại trong phiên sau.
- Process crash sau khi persist nhưng trước khi update trạng thái mailbox.
- Một email được copy/move giữa các folder và xuất hiện với định danh folder khác.
- Nhiều worker cùng đọc một mailbox.

Nếu router chuyển tất cả bản lặp tới **TicketService.openFromInboundMail(...)**, ứng dụng có thể tạo nhiều ticket từ cùng một email.

**Định tuyến không phải cơ chế dedup.** Cần một **inbox identity** bền vững trước khi phát sinh side effect.

Ví dụ:

~~~text
IMAP:
  (tenantId, mailboxId, folderId, uidValidity, uid)

POP3:
  (tenantId, mailboxId, uidl)

Application:
  inboxId (generated after successful unique insert)
~~~

Không dùng một mình Message-ID header làm unique key tuyệt đối: header có thể thiếu, bị trùng, bị sửa hoặc do sender tùy ý khai báo.

## 29. Inbox Pattern: lưu trước, route sau

Một thiết kế ưu tiên độ tin cậy:

~~~text
IMAP/POP3 adapter
       |
       v
Extract mailbox identity
       |
       v
BEGIN DATABASE TRANSACTION
  INSERT mail_inbox with unique source identity
  INSERT routing_work_item
COMMIT
       |
       v
Business worker reads inboxId
       |
       v
Parse / classify / route
       |
       v
Handler transaction
       |
       v
PROCESSED or RETRY/QUARANTINED
~~~

Nếu cùng thư được fetch lại, unique constraint ngăn tạo thêm cùng một inbox record. Nếu đã lưu thành công nhưng message chưa được route vì process crash, **routing_work_item** vẫn tồn tại để worker xử lý lại.

Ví dụ bảng:

~~~sql
CREATE TABLE mail_inbox (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         VARCHAR(120) NOT NULL,
    mailbox_id        VARCHAR(120) NOT NULL,
    folder_id         VARCHAR(300),
    uid_validity      BIGINT,
    imap_uid          BIGINT,
    pop3_uidl         VARCHAR(600),
    raw_object_key    VARCHAR(1200),
    classified_type   VARCHAR(50),
    classifier_version VARCHAR(50),
    state             VARCHAR(40) NOT NULL,
    received_at       TIMESTAMP WITH TIME ZONE,
    ingested_at       TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Ví dụ PostgreSQL partial unique indexes:

~~~sql
CREATE UNIQUE INDEX uq_mail_inbox_imap
ON mail_inbox (
    tenant_id, mailbox_id, folder_id,
    uid_validity, imap_uid
)
WHERE imap_uid IS NOT NULL;

CREATE UNIQUE INDEX uq_mail_inbox_pop3
ON mail_inbox (tenant_id, mailbox_id, pop3_uidl)
WHERE pop3_uidl IS NOT NULL;
~~~

Đây là **schema minh họa**. Trong thực tế cần validate các trường identity bắt buộc theo protocol để không tạo nhiều record có UID null, và cần table riêng cho work item/attempt nếu workflow phức tạp.

### Transaction boundary

Database commit **không commit cùng lúc với IMAP/POP3 server**. Khi đã lưu inbox thành công nhưng chưa mark thư trên server, lần poll sau vẫn có thể thấy thư. Đây là hành vi có thể chấp nhận được khi dedup hoạt động đúng.

Vì vậy mục tiêu thực tế thường là **at-least-once ingestion + idempotent processing**, không phải “mỗi email được nhận đúng một lần tuyệt đối” chỉ nhờ Spring Integration.

## 30. IMAP UID, UIDVALIDITY và routing checkpoint

IMAP **message sequence number** có thể thay đổi khi message khác bị xóa/expunge. Để nhận diện và checkpoint lâu dài:

~~~text
mailbox = support-A
folder = INBOX
UIDVALIDITY = 91320
UID = 4221
~~~

Một UID chỉ có ý nghĩa trong cùng mailbox và cùng thế hệ UIDVALIDITY. Khi UIDVALIDITY đổi, phải đồng bộ lại và dùng dedup thích hợp.

Lỗi checkpoint điển hình:

~~~text
UID 100 -> route thành công
UID 101 -> lỗi lưu inbox
UID 102 -> route thành công

lastUID = 102
~~~

UID 101 có thể bị bỏ qua vĩnh viễn nếu worker chỉ tìm UID lớn hơn lastUID ở lần sau.

Cách làm an toàn hơn:

- Chỉ advance **contiguous checkpoint** sau khi mọi UID đã thấy trước đó được lưu bền vững; hoặc
- Lưu trạng thái theo từng UID/inbox record, cho phép UID 101 tồn tại dưới trạng thái RETRY và discovery cursor tiến một cách có điều kiện.

**Không dùng IMAP Seen flag làm bằng chứng email đã xử lý**, vì người dùng khác có thể đọc thư, client có thể thay flag, và Seen không đồng bộ với DB commit nghiệp vụ.

## 31. POP3 UIDL và định tuyến

Với POP3, nhiều server hỗ trợ **UIDL** để định danh email trong maildrop. Một identity điển hình:

~~~text
(mailboxId, uidl)
~~~

Không lấy **POP3 message number** làm khóa bền vững: số thứ tự thay đổi khi các message bị xóa.

Nếu POP3 server không hỗ trợ UIDL ổn định:

- Xác định chính sách fallback dedup bằng hash/raw bytes hoặc một tổ hợp metadata.
- Lưu rõ độ tin cậy và phạm vi của fingerprint.
- Không chỉ dựa trên Subject + From (hai email khác nhau có thể giống nhau).
- Không xóa email khỏi server trước khi dữ liệu đã được lưu bền vững.

Spring Integration Mail giúp nhận message nhưng không tự giải quyết mọi quy tắc identity của mailbox. Đó là phần cần được thiết kế quanh các receiving adapters và inbox store.

## 32. State machine cho email sau khi nhận

Một state machine minh họa:

~~~text
DISCOVERED
    |
    v
PERSISTED
    |
    v
CLASSIFYING
    |
    +-- invalid MIME --> QUARANTINED
    +-- insufficient evidence --> NEEDS_TRIAGE
    |
    v
CLASSIFIED
    |
    v
ROUTED
    |
    v
PROCESSING
    |
    +-- transient failure --> RETRY_WAIT
    +-- permanent policy rejection --> QUARANTINED
    |
    v
PROCESSED
~~~

Trạng thái **ROUTED** không đồng nghĩa **PROCESSED**. Một message chuyển tới channel nhưng handler bị lỗi vẫn cần được retry hoặc đánh dấu thất bại có thể điều tra.

### State và retry theo từng loại

| Loại | Retry có thể phù hợp | Side effect cần bảo vệ |
|---|---|---|
| SUPPORT_REQUEST | API ticket/database tạm lỗi | Không tạo ticket trùng |
| SUPPORT_REPLY | Ticket service unavailable | Không append comment trùng |
| INVOICE | Storage/validation service tạm lỗi | Không nhập hai hóa đơn |
| DELIVERY_REPORT | DB delivery status tạm lỗi | Không cập nhật bounce hai lần |
| SYSTEM_ALERT | Incident platform tạm lỗi | Không mở nhiều incident giống nhau |
| UNKNOWN | Reclassification sau sửa policy | Không mất raw email hoặc tạo vòng xử lý |

Không retry vô hạn một MIME malformed hoặc sender không đáng tin. Đưa vào quarantine có thể là kết quả đúng và cần được giám sát.

## 33. Error channel khác với Unknown channel

Hai khái niệm rất dễ bị lẫn:

**Unknown channel** phục vụ **message được nhận và đọc thành công nhưng không có route nghiệp vụ phù hợp**.

**Error channel** phục vụ **exception trong integration pipeline** theo cơ chế error handling của từng endpoint/channel.

Ví dụ:

~~~text
Email hợp lệ nhưng không match rule
     -> mailUnknownChannel

MIME parser throws MessagingException
     -> error handling / mail quarantine

Invoice handler throws DatabaseUnavailable
     -> retry/error handling

Router trả tên channel sai
     -> routing/channel resolution error
~~~

Không nên catch mọi exception rồi gán EmailType.UNKNOWN:

~~~java
try {
    return classifier.classify(email);
} catch (Exception exception) {
    return EmailType.UNKNOWN;  // che giấu lỗi code/hạ tầng
}
~~~

Một lỗi database bị mất kết nối không có nghĩa email thuộc loại UNKNOWN. Cần giữ nguyên **error category** và trạng thái RETRY nếu là lỗi tạm thời.

### ErrorChannel có hoạt động tự động không?

Spring Integration có cơ chế **ErrorMessage** và error channels, nhưng cách một exception được chuyển tới error channel phụ thuộc vào **endpoint, poller, thread boundary và error handling configuration**. Với **DirectChannel đồng bộ**, exception có thể lan ngược lên caller; với poller/executor, lỗi có thể được bao thành ErrorMessage gửi đến configured error channel.

Không được giả định chỉ tạo một bean tên **errorChannel** là mọi exception từ mọi flow sẽ được xử lý bền vững. Cần kiểm tra contract của endpoint thực tế và bảo đảm inbox item không bị đánh dấu PROCESSED khi handler thất bại.

## 34. Phân loại lỗi để retry đúng

| Nhóm lỗi | Ví dụ | Phản ứng |
|---|---|---|
| **Mail server/network** | IMAP disconnect, read timeout | Reconnect/reconcile UID/UIDL |
| **Authentication** | Token revoked, credential hết hạn | Refresh/re-authorize, cảnh báo |
| **Malformed MIME** | Cấu trúc không parse được | Quarantine, không retry nóng |
| **Unsafe content** | Malware attachment, HTML độc hại | Quarantine, không route tới business handler |
| **Classification ambiguous** | Nhiều rule không phân giải được | UNKNOWN/triage |
| **Business downstream** | Ticket service/DB unavailable | Retry từ durable inbox |
| **Routing misconfiguration** | Channel đích không tồn tại | Alert lỗi triển khai/cấu hình |
| **Authorization** | Tenant mismatch, không có quyền | Reject/quarantine, audit |

Không giữ phiên IMAP mở trong lúc retry một business API. Nên lưu MIME/metadata trước và để business worker retry độc lập.

## 35. Queue và channel: chọn theo yêu cầu đảm bảo

Trong Spring Integration có nhiều loại channel, nhưng chúng không tương đương:

| Cách | Đặc điểm | Khi phù hợp |
|---|---|---|
| **DirectChannel** | Gọi subscriber trong thread hiện tại | Pipeline ngắn, synchronous |
| **ExecutorChannel** | Giao việc qua TaskExecutor | Tách thread, tăng concurrency; không tự bền vững |
| **QueueChannel** | Giữ message chờ consumer poll | Buffering; mặc định không đồng nghĩa lưu bền vững qua crash |
| **PublishSubscribeChannel** | Phát tới nhiều subscriber | Fan-out có chủ đích |
| **Broker-backed channel** | Queue/topic bên ngoài | Decouple service, có thể bền vững theo broker config |
| **Inbox DB + worker** | Lưu message state trong database | Audit, retry, idempotency, kiểm soát transaction |

Với thư chứa attachment hoặc body lớn, không nên giữ cả **MimeMessage** mở kết nối trong queue in-memory quá lâu. Hãy lưu raw EML/attachment rồi truyền **inboxId/metadata** cho consumer.

### Không coi message đã rời channel là đã commit nghiệp vụ

Chuyển một message từ channel A sang B chỉ là hoạt động messaging. Nếu handler cần cập nhật database và phát event, hãy quản lý transaction, outbox và idempotency riêng.

## 36. Backpressure và isolation theo loại email

Ví dụ mailbox nhận 10.000 invoice nhưng chỉ có 10 support replies:

~~~text
10.000 INVOICE messages
10 SUPPORT_REPLY messages
~~~

Nếu tất cả được xử lý đồng bộ theo thứ tự đọc, ticket replies có thể phải chờ hàng giờ dù handler ticket rất nhanh.

Một thiết kế:

~~~text
mailRawChannel
     |
     v
Classifier
     |
     +--> Invoice queue   -> 4 document workers
     |
     +--> Support queue   -> 2 ticket workers
     |
     +--> Delivery queue  -> 2 DSN workers
     |
     +--> Unknown queue   -> bounded triage
~~~

Cần:

- **Quota/in-flight** cho từng loại và tenant.
- **Bounded queues** để tránh phình RAM hoặc backlog vô hạn.
- **Retry budget** riêng; một loại email lỗi không chiếm hết worker.
- **Oldest due age** và SLA cho từng channel/stream.
- **Expired jobs** theo chính sách, không tự động xử lý email OTP quá hạn.

Chỉ dùng một **ExecutorChannel** với thread pool vô hạn không phải giải pháp hiệu năng bền vững.

## 37. Chuẩn hóa metadata cho quan sát và truy vết

Một email sau khi vào ứng dụng nên có một bộ metadata nội bộ dễ truy vết:

~~~text
inboxId:        INB-1001
tenantId:       tenant-A
mailboxId:      support-primary
sourceProtocol: imaps
mailIdentity:   UIDVALIDITY=903, UID=1045
classifier:     email-type-v3
emailType:      SUPPORT_REPLY
routeChannel:   mailSupportReplyChannel
state:          PROCESSING
attempt:        2
traceId:        7d0c...
~~~

Những metadata này phục vụ:

- Đối chiếu email đã route vào channel nào.
- Tìm nguyên nhân routing UNKNOWN.
- Phân biệt retry cùng một inbox item với email mới.
- Điều tra khi cùng Message-ID xuất hiện ở hai mailbox.
- Biết classifier version nào quyết định type.
- Theo dõi độ trễ từ email đến mailbox tới khi nghiệp vụ hoàn tất.

### Spring Message header hay domain record?

Có thể đưa một số metadata vào **Spring MessageHeaders** để correlation/observability, nhưng phải kiểm soát:

- **MessageHeaders** do Spring Integration tạo khác với MIME headers của email.
- Không biến mọi field do người gửi khai báo thành metadata tin cậy.
- Chỉ lưu những trường cần thiết; không sao chép raw body/attachment vào headers.
- Khi message qua broker, header serialization và mapping có thể thay đổi.
- Source of truth cho inbox processing là database/ledger bền vững, không phải header chỉ tồn tại trong RAM.

## 38. Ghi metric theo email type mà không lộ dữ liệu

Một dashboard định tuyến nên trả lời:

| Metric logic | Ý nghĩa |
|---|---|
| **mail.inbound.discovered** | Số message identity được nhìn thấy |
| **mail.inbound.persisted** | Số unique inbox item lưu thành công |
| **mail.inbound.classified** | Số email theo loại đã phân loại |
| **mail.inbound.routed** | Số message chuyển tới channel đích |
| **mail.inbound.routing.errors** | Số lỗi chọn/resolve channel |
| **mail.inbound.unknown** | Số email phải triage |
| **mail.inbound.processing** | Số xử lý theo loại và result |
| **mail.inbound.queue.age** | Tuổi item chưa hoàn thành theo loại |
| **mail.inbound.reclassified** | Số email được phân loại lại |
| **mail.inbound.duplicates** | Số bản lặp bị dedup loại bỏ |

Những label hữu hạn nên dùng:

~~~text
email_type=INVOICE|SUPPORT_REQUEST|SUPPORT_REPLY|...
result=success|failed|retry|quarantined
stream=inbound-support|inbound-finance|...
error_category=parser|auth|routing|downstream|...
~~~

**Không đưa** Subject, địa chỉ email, Message-ID, UID cụ thể, attachment filename hoặc inboxId vào **Prometheus metric label**, vì gây high cardinality và có thể lộ dữ liệu cá nhân.

Ví dụ Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;

public final class MailRoutingMetrics {

    private final MeterRegistry registry;

    public MailRoutingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void routed(EmailType type) {
        registry.counter(
                "mail.inbound.routed",
                "email_type", type.name()
        ).increment();
    }
}
~~~

Nếu cần biết có bao nhiêu email **đã xử lý thành công**, cần metric khác hoặc result=processed ở đúng boundary handler. Counter **routed** không thay cho counter **processed**.

### Khi nào ghi counter?

Nếu ghi counter trước khi channel.send thành công, một exception có thể khiến metric “routed” tăng dù dispatch thất bại. Nên xác định nghĩa chính xác:

- **routing_decision_total**: classifier/router đã chọn một channel.
- **routing_dispatched_total**: dispatch thành công tới channel.
- **processing_completed_total**: handler xác nhận hoàn thành nghiệp vụ.

Các counter chỉ hỗ trợ quan sát, không có transaction chung với database. Nếu cần số liệu kế toán chính xác về inbox item, hãy đối soát từ bảng trạng thái bền vững.

## 39. Phát hiện rule regression và thay đổi tỷ lệ phân loại

Ví dụ sau một lần triển khai classifier:

~~~text
Trước deploy:
  SUPPORT_REQUEST  50%
  SUPPORT_REPLY    30%
  INVOICE          15%
  UNKNOWN           5%

Sau deploy:
  SUPPORT_REQUEST  10%
  SUPPORT_REPLY     5%
  INVOICE          15%
  UNKNOWN          70%
~~~

Lưu lượng tổng có thể không đổi, nhưng tỷ lệ UNKNOWN tăng đột biến là tín hiệu **rule regression, lỗi parser, thay đổi schema mail hoặc thiếu dữ liệu correlation**.

Nên theo dõi:

- Distribution email types theo thời gian.
- UNKNOWN/AMBIGUOUS ratio và reason code.
- Parser error ratio.
- Tỷ lệ ticket reply không match được correlation.
- Tỷ lệ invoice validation bị từ chối theo nhóm nguyên nhân.
- Tỷ lệ delivery report không match notification.
- Tuổi của triage queue.

Không nên tạo cảnh báo chỉ vì thay đổi phần trăm khi mẫu quá nhỏ. Áp dụng **cửa sổ, ngưỡng số lượng tối thiểu và baseline** phù hợp từng stream.

## 40. Đánh dấu classifier version và reclassification

Khi quy tắc phân loại thay đổi, những email đã nằm trong UNKNOWN có thể được phân loại lại:

~~~text
Inbox item INB-1001
  raw EML persisted
  classifier_version=v2
  type=UNKNOWN
  reason=UNRECOGNIZED_INVOICE_FORMAT
       |
       | deploy classifier v3
       v
  reclassify (controlled)
       |
       v
  type=INVOICE
  route to invoice workflow
~~~

Cần bảo đảm:

1. Chỉ reclassify **item đủ điều kiện**, không tùy ý chạy lại mọi email đã PROCESSED.
2. Ghi **previous type, new type, classifier version và thời điểm** để audit.
3. Giữ **same inboxId**, không tạo email inbound mới.
4. Kiểm tra tenant/sender authorization theo chính sách hiện tại.
5. Không phát sinh side effect trùng nếu email từng được xử lý một phần.
6. Có rate limit để reclassification hàng loạt không chiếm hết worker production.

Một lần phân loại lại không nhất thiết thay đổi dữ liệu gốc. Nếu raw EML đã được persist, nên **giữ nguyên bản nhận** và lưu classifier output như metadata có version.

## 41. Unit test classifier không cần SMTP server

Vì classifier chỉ nhận các tín hiệu đã chuẩn hóa, có thể test như một hàm thuần:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class DefaultEmailClassifierTest {

    private final DefaultEmailClassifier classifier =
            new DefaultEmailClassifier();

    @Test
    void routesCorrelatedDsnToDeliveryReport() {
        ClassificationSignals signals = new ClassificationSignals(
                false, // suspiciousOrMalformed
                true,  // correlatedDeliveryReport
                false, // authorizedTicketReply
                false, // trustedInvoiceSource
                false, // validatedInvoiceAttachment
                false, // authenticatedSystemAlert
                false  // eligibleSupportRequest
        );

        assertEquals(
                EmailType.DELIVERY_REPORT,
                classifier.classify(signals)
        );
    }

    @Test
    void doesNotTreatPdfAsInvoiceWithoutTrustedSource() {
        ClassificationSignals signals = new ClassificationSignals(
                false,
                false,
                false,
                false, // nguồn chưa được xác minh
                true,  // có PDF/attachment hợp lệ về hình thức
                false,
                false
        );

        assertEquals(
                EmailType.UNKNOWN,
                classifier.classify(signals)
        );
    }

    @Test
    void suspiciousMessageGoesToUnknown() {
        ClassificationSignals signals = new ClassificationSignals(
                true,  // suspiciousOrMalformed
                true,  // trông giống một DSN
                false,
                false,
                false,
                false,
                false
        );

        assertEquals(
                EmailType.UNKNOWN,
                classifier.classify(signals)
        );
    }
}
~~~

Những test này kiểm tra **policy phân loại**, không cần Spring ApplicationContext, IMAP server hay SMTP. Chúng giả định những tín hiệu đã được xác minh ở bước trước, vì vậy cần test riêng phần **trích xuất và xác minh signals** từ MIME/header.

### Các ca nên bổ sung

- Email thiếu Subject.
- Message-ID trống hoặc trùng.
- Reply chỉ có “Re:” nhưng không match ticket.
- Delivery report không có notification correlation.
- Invoice có nguồn đáng tin nhưng attachment không đạt policy.
- Alert có Subject CRITICAL nhưng chưa xác thực nguồn.
- Hai rule đồng thời match, classifier chọn precedence hoặc AMBIGUOUS theo contract.
- Email có nhiều recipient và phân quyền tenant khác nhau.
- MIME malformed và dữ liệu quá giới hạn.

## 42. Unit test router chọn đúng channel

Với cách khai báo @Router, logic chọn channel có thể tách thành một hàm thuần:

~~~java
public final class EmailChannelMapping {

    public String channelFor(EmailType type) {
        return switch (type) {
            case DELIVERY_REPORT -> "mailDeliveryReportChannel";
            case SUPPORT_REPLY -> "mailSupportReplyChannel";
            case SUPPORT_REQUEST -> "mailSupportRequestChannel";
            case INVOICE -> "mailInvoiceChannel";
            case SYSTEM_ALERT -> "mailSystemAlertChannel";
            case UNKNOWN -> "mailUnknownChannel";
        };
    }
}
~~~

Router có thể delegate tới service này:

~~~java
@Router(inputChannel = "mailClassifiedChannel")
public String route(InboundEmail email) {
    return channelMapping.channelFor(email.type());
}
~~~

Unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class EmailChannelMappingTest {

    private final EmailChannelMapping mapping =
            new EmailChannelMapping();

    @Test
    void mapsInvoiceToInvoiceChannel() {
        assertEquals(
                "mailInvoiceChannel",
                mapping.channelFor(EmailType.INVOICE)
        );
    }

    @Test
    void mapsUnknownToTriageChannel() {
        assertEquals(
                "mailUnknownChannel",
                mapping.channelFor(EmailType.UNKNOWN)
        );
    }
}
~~~

Đây là test quyết định định tuyến, không phải test Spring Integration đã thực sự gửi message tới bean channel. Phần đó cần **integration test** riêng.

## 43. Integration test router và handler không cần IMAP thật

Khi muốn kiểm tra annotation/DSL đã nối đúng channel, có thể khởi động một Spring test context có các channel và handler, sau đó **đẩy InboundEmail đã chuẩn hóa** vào mailClassifiedChannel.

Kiến trúc:

~~~text
JUnit + Spring Integration test context
       |
       v
send InboundEmail(type=INVOICE)
       |
       v
mailClassifiedChannel
       |
       v
Router
       |
       v
mailInvoiceChannel
       |
       v
Test handler / mock InvoiceService
       |
       v
verify exactly one invoice processing call
~~~

Các assert nên có:

- Invoice đi tới invoice handler, không đi tới ticket/DSN.
- DELIVERY_REPORT đi đúng delivery handler.
- UNKNOWN được quarantine hoặc ghi triage.
- Nếu handler ném lỗi, inbox item **không bị đánh dấu PROCESSED**.
- Không có channel name chưa được khai báo hoặc không có subscriber.
- Khi một message đã dedup, việc gửi lại không gây side effect lần hai.

Khi test nhiều loại, dùng fixture có địa chỉ/subject/tenant khác nhau để không vô tình kiểm tra nhầm message.

### Test với @SpringIntegrationTest

Spring Integration cung cấp hỗ trợ kiểm thử cho flows, channels và endpoint mocks trong module test tương ứng. Tên annotation, cấu hình test context và cách thay endpoint phụ thuộc phiên bản thư viện. Chỉ thêm chúng khi muốn kiểm tra wiring/dispatch thực sự; unit test classifier/route mapping đơn thuần không cần khởi động toàn bộ context.

## 44. End-to-end test với IMAP/POP3 test server

Để kiểm tra từ mailbox đến handler, có thể dùng một **mail server thử nghiệm** hỗ trợ SMTP để nhận thư và IMAP/POP3 để client đọc.

Ví dụ kiến trúc:

~~~text
JUnit
   |
   +-- Start test SMTP + IMAP/POP3 server
   |
   +-- Deliver test MIME messages:
   |     1 support reply
   |     1 invoice with PDF
   |     1 DSN delivery report
   |     1 unknown email
   |
   v
Spring Integration Mail inbound adapter
   |
   v
Normalizer + classifier + router
   |
   +-- Ticket store
   +-- Invoice store
   +-- Delivery status store
   +-- Triage store
   |
   v
Assert each message reaches one correct workflow
~~~

Có thể dùng **GreenMail phiên bản tương thích Jakarta Mail**, server container hoặc test harness khác theo hạ tầng dự án.

Những nội dung cần kiểm tra ở tầng này:

- Receiver thực sự đọc được email từ mailbox.
- Payload type và MIME content đúng với normalizer mong đợi.
- IMAP UID/UIDVALIDITY hoặc POP3 UIDL được lưu đúng.
- Một lần poll/reconnect thứ hai không tạo tác dụng phụ trùng.
- Mailbox A không được gắn nhầm tenantId của mailbox B.
- MIME có attachment/DSN được phân loại đúng.
- Email không match được xử lý ở UNKNOWN, không biến mất.
- Kết nối và test mailbox được dọn sạch sau mỗi test.

Không dùng mailbox cá nhân hoặc SMTP production chỉ để kiểm thử routing; dữ liệu test cần được giả lập và cô lập.

## 45. Runbook: email vào inbox nhưng không tới handler

Khi một email đã xuất hiện trong mailbox nhưng không tạo ticket/invoice/delivery update, hãy điều tra theo tầng:

### Bước 1 — Xác nhận receiver

- Mailbox và folder được cấu hình đúng chưa?
- IMAP/POP3 có kết nối và xác thực thành công không?
- Poller đang chạy hoặc IMAP IDLE đã reconnect sau disconnect chưa?
- Có vượt giới hạn kết nối/provider throttle không?
- Email có bị filter trước khi vào mailRawChannel không?

### Bước 2 — Xác nhận inbox persistence

- Có record theo UID/UIDVALIDITY hoặc UIDL không?
- Unique key có khiến message bị nhận diện là bản lặp không?
- Raw EML/attachment đã được lưu an toàn chưa?
- Checkpoint có bị advance trước khi commit không?
- Inbox đang ở trạng thái PERSISTED, CLASSIFIED hay RETRY_WAIT?

### Bước 3 — Xác nhận classification

- Classifier version đang chạy là gì?
- EmailType là gì?
- Các routing signals đã được xác minh từ nguồn nào?
- Email có bị đánh UNKNOWN do thiếu correlation, thiếu attachment hoặc source không đáng tin không?
- Có dấu hiệu parser lỗi với MIME multipart/charset không?

### Bước 4 — Xác nhận routing

- Channel đích có tồn tại đúng tên?
- Có subscriber/ServiceActivator cho channel đó không?
- Có vô tình cấu hình cả @Router và DSL router cạnh tranh trên một input channel không?
- Có filter hoặc header mapping loại bỏ metadata cần thiết không?
- Có exception được chuyển tới errorChannel hoặc lan ngược về poller không?

### Bước 5 — Xác nhận handler

- Handler nhận inboxId nào?
- Có retry đang chờ hay dead-letter/quarantine?
- Database/API downstream có khả dụng không?
- Một idempotency key có ngăn xử lý vì nghiệp vụ thực sự đã hoàn tất không?
- Có transaction rollback hoặc state update bị lỗi sau side effect không?

### Bước 6 — Phục hồi có kiểm soát

Nếu mail đã persist, ưu tiên **replay từ inbox record** theo idempotency key. Không tải lại/xóa nguyên cả mailbox hoặc gửi trực tiếp một payload chưa được xác minh tới business handler chỉ để “sửa nhanh”.

## 46. Runbook: tỷ lệ UNKNOWN tăng đột biến

Một biểu đồ UNKNOWN cao bất thường có thể do:

- Thay đổi domain/format email của đối tác.
- Thay đổi thư mục mailbox hoặc rule filter ở provider.
- Classifier release có bug hoặc rule precedence đổi.
- Hệ thống correlation ticket/notification tạm unavailable.
- MIME parser không hiểu charset/attachment mới.
- Authentication-Results hoặc trusted metadata từ mail gateway bị thay đổi.
- Spam campaign bất thường.

Quy trình:

1. Xác định thời điểm bắt đầu, mailbox, tenant và loại email bị ảnh hưởng.
2. So sánh **reason code distribution**, không chỉ tổng UNKNOWN.
3. Xem một số inbox sample **đã được phép truy cập** trong môi trường điều tra bảo mật.
4. Phân biệt **không match rule** với **exception parser/database**; đây là nguyên nhân khác nhau.
5. Kiểm tra thay đổi deployment/provider gần thời điểm xuất hiện.
6. Nếu do rule thiếu, bổ sung classifier và replay những item đủ điều kiện có kiểm soát.
7. Nếu do email độc hại, tăng quarantine/rate limit và bảo vệ hệ thống, không nới lỏng xác thực nguồn.
8. Kiểm tra side effects đã xảy ra trước đó để tránh tạo trùng khi reprocess.

Không đổi mọi UNKNOWN thành SUPPORT_REQUEST chỉ để biểu đồ trông “đẹp hơn”. Việc đó có thể đưa spam, DSN giả hoặc tài liệu không hợp lệ vào quy trình nghiệp vụ.

## 47. Runbook: email được xử lý trùng

Một số nguyên nhân:

~~~text
Poll/reconnect -> cùng message được fetch lại
       |
       +-- Không có unique inbox identity
       +-- IMAP checkpoint sai UIDVALIDITY
       +-- POP3 UIDL không được lưu
       +-- Mark Seen thất bại rồi retry
       +-- Hai pod cùng đọc mailbox
       +-- Router dispatch lại khi lỗi downstream
       +-- Handler không idempotent
~~~

Các bước:

1. Xác định hai bản ghi có cùng **mailbox identity** hay thực sự là hai email được gửi.
2. Kiểm tra **inboxId, UID/UIDVALIDITY/UIDL, Message-ID, raw MIME hash** với phạm vi phù hợp.
3. Kiểm tra unique constraint và transaction của bước ghi inbox.
4. Xem quá trình claim/lease của worker và số active pollers.
5. Kiểm tra handler có idempotency theo inboxId và business key không.
6. Nếu mail đã được xử lý một phần, chỉ retry bước chưa hoàn tất theo trạng thái bền vững.
7. Điều chỉnh checkpoint/reconciliation, không tự động xóa mọi thư đọc rồi.

Đặc biệt, **exactly-once effect** ở những tác vụ có side effect trên dịch vụ ngoài cần cơ chế idempotency của chính dịch vụ đó hoặc quy trình reconciliation; chỉ có router và outbox chưa đủ.

## 48. Anti-pattern thường gặp khi route email

| Anti-pattern | Hậu quả | Cách thay thế |
|---|---|---|
| Dựa duy nhất vào Subject để phân loại DSN | DSN giả vào delivery handler | Parse DSN cấu trúc và correlate |
| Dựa vào attachment .pdf để quyết định invoice | File tùy ý vào invoice workflow | Kiểm tra nguồn và nội dung |
| Dùng From là bằng chứng quyền ticket | Sender spoof sửa ticket của người khác | Kiểm tra correlation và authorization |
| Dùng MIME Content-Type làm EmailType | Mixed chứa nhiều loại nghiệp vụ | Classifier có model nghiệp vụ |
| Sao chép X-Email-Type thành trusted routing header | Người gửi tự điều khiển router | Header nội bộ chỉ do service tạo sau xác minh |
| Tạo dynamic channel từ input | Sai topology hoặc truy cập luồng ngoài ý muốn | Enum/allowlist channel mapping |
| Không có default UNKNOWN route | Email không match bị rơi hoặc gây exception không xử lý | Explicit triage/quarantine |
| Catch mọi exception rồi gán UNKNOWN | Che lỗi DB, parser, cấu hình | Tách business unknown và technical error |
| Một handler khổng lồ với nhiều if/else | Khó kiểm thử, lỗi lan rộng | Classifier, router, handler chuyên trách |
| Dùng Seen flag làm processed state | Mất thư hoặc xử lý sai khi người dùng đọc | Inbox state riêng |
| Dùng IMAP sequence number làm unique key | UID bị lệch khi expunge | UIDVALIDITY + UID |
| Không dedup trước side effect | Tạo ticket/invoice trùng | Unique inbox key và idempotent handler |
| Coi DirectChannel là durable queue | Mất việc khi crash | Inbox DB/broker bền vững |
| Coi routing thành công là business complete | Không retry khi handler thất bại | State machine và commit boundary |
| Giữ MimeMessage gắn với Folder vào async queue | Lỗi folder closed, memory/network leakage | Persist raw EML và chuyển inboxId |
| Một executor vô hạn cho mọi type | Invoice spike làm support lag | Bounded queues và per-type capacity |
| Log raw MIME để debug | Lộ PII/attachment/token | Metadata/redacted logs |
| Unit test chỉ verify router method được gọi | Không biết channel có subscriber đúng | Channel/flow integration test |
| Bật cả annotation router và DSL router trên một channel | Competing subscriptions/dispatch không rõ | Chọn một topology có chủ đích |
| Retry lại toàn bộ flow không phân biệt side effect | Handler chạy lại phần đã thành công | Idempotent workflow + retry có trạng thái |

## 49. Thiết kế ưu tiên sự rõ ràng trước tối ưu hóa

Một ứng dụng nhỏ chỉ có hai loại email có thể bắt đầu với:

~~~text
IMAP poller -> normalize -> classify -> @Router
                                |
                  +-------------+------------+
                  |                          |
                  v                          v
                SUPPORT                    UNKNOWN
                  |                          |
                  v                          v
                Ticket                    Triage
~~~

Khi có thêm invoice, bounce, nhiều tenant hoặc SLA cao, có thể thêm:

~~~text
Mailbox poller
     |
     v
Durable inbox
     |
     v
Classification worker
     |
     v
Typed message broker / work queues
     |
     +-- Ticket worker group
     +-- Invoice worker group
     +-- Delivery worker group
     +-- Triage worker group
~~~

Không nhất thiết phải dùng broker ngay từ đầu nếu một database inbox và worker đã đáp ứng khối lượng. Nhưng khi một mail type có tác vụ nặng như OCR/virus scan, nên tách worker resource budget để nó không giữ toàn bộ inbound flow.

### Khi nào không nên xây route bằng email?

Nếu nhà cung cấp có **webhook/API đáng tin cậy và giàu metadata** để nhận events hoặc file, có thể phù hợp hơn IMAP/POP3:

- Bounce/delivery events từ ESP có event ID và chữ ký xác thực.
- Hóa đơn từ đối tác qua authenticated API.
- Cảnh báo hệ thống qua webhook có schema rõ.
- Ticket updates qua hệ thống hỗ trợ đã tích hợp.

Email routing có thể vẫn cần để hỗ trợ đối tác không có API, nhưng không nên mặc định nó là integration channel an toàn nhất cho mọi loại dữ liệu nhạy cảm.

## 50. Ví dụ end-to-end: từ mailbox tới một ticket reply

Giả sử khách hàng trả lời vào email hỗ trợ:

~~~text
Message:
  From: customer@example.net
  To: support@example.com
  Subject: Re: Ticket 123
  In-Reply-To: <support-outbound-123@service.example>
  Content-Type: multipart/alternative
~~~

Luồng xử lý:

1. **IMAP receiver** đọc message tại UID xác định.
2. **Inbox writer** lưu raw EML có kiểm soát và identity theo mailbox+UIDVALIDITY+UID, tạo inboxId **INB-1001**.
3. **Normalizer** đọc header và plain text/HTML (giới hạn MIME).
4. **Correlation service** đối chiếu In-Reply-To với ticket 123 và xác minh quyền người trả lời.
5. **Classifier** trả **SUPPORT_REPLY**, lưu classifier version.
6. **Spring Integration @Router** chọn **mailSupportReplyChannel**.
7. **TicketService** thêm reply với idempotency key **INB-1001**, rồi commit database.
8. **Inbox status** được chuyển thành **PROCESSED**.
9. Nếu cần, ứng dụng có thể đánh dấu Seen/move mail sau khi đã persist và xử lý theo policy.

Nếu service lỗi ở bước 7, item có trạng thái RETRY_WAIT. Khi retry từ inbox, không cần tải lại MimeMessage từ mail server. Nếu phía ticket API đã ghi reply nhưng response mất, idempotency key giúp tránh tạo reply trùng.

### Nếu reply không được xác thực?

Ví dụ **In-Reply-To** giống ticket 123 nhưng người gửi không có quyền. Classifier không được gán **authorizedTicketReply=true**. Email sẽ theo policy đi vào **UNKNOWN/triage** hoặc một quy trình xác minh khác, không được tự thêm comment vào ticket.

## 51. Checklist triển khai routing theo loại email

**Phân loại và topology**

1. Đã liệt kê các **EmailType** nghiệp vụ cần xử lý chưa?
2. Có thứ tự ưu tiên hoặc chính sách xử lý xung đột không?
3. Có fallback **UNKNOWN/AMBIGUOUS** không?
4. Router có map từng enum value sang channel có subscriber không?
5. Đã chọn một kiểu @Router hoặc DSL router, tránh đăng ký cạnh tranh không chủ ý chưa?
6. Có tách classifier, router và handler để test riêng không?

**Bảo mật và dữ liệu**

7. Mailbox/tenant identity lấy từ nguồn đáng tin cậy chứ?
8. Có phân biệt MIME header với Spring Message header không?
9. Có xác thực nguồn/correlation trước khi route email nhạy cảm không?
10. HTML/attachment có giới hạn, sanitize/scan phù hợp chưa?
11. Có ngăn một tenant dùng routing rule/channel của tenant khác không?
12. Có chính sách không log raw EML, credential và PII không?

**Tin cậy và phục hồi**

13. Có inbox identity theo IMAP UID+UIDVALIDITY hoặc POP3 UIDL không?
14. Có unique constraint chống xử lý trùng không?
15. Email đã được persist trước khi đánh dấu/xóa trên server chưa?
16. Có thể retry từ inbox record mà không fetch lại mailbox không?
17. Handler đã idempotent và có state transition rõ chưa?
18. Error channel, retry, dead-letter, quarantine có được phân biệt không?
19. Khi process crash hoặc IMAP reconnect, có reconciliation không?

**Hiệu năng và vận hành**

20. Có giới hạn số email/attachment cần parse mỗi batch không?
21. Có tách capacity giữa invoice, support, delivery và triage khi cần không?
22. Queue/backlog có bounded policy không?
23. Có metric UNKNOWN ratio, route errors, processing age và duplicates không?
24. Có cách reclassify email chưa xử lý khi rule thay đổi không?
25. Đã kiểm thử classifier unit, routing integration và mailbox end-to-end chưa?

Checklist là công cụ thiết kế, không phải bằng chứng hệ thống tự động đạt các bảo đảm trên khi cài đặt Spring Integration Mail.

## 52. Ghi nhớ

**Định tuyến message theo loại email** trong Spring Integration Mail là quá trình chuyển email từ mailbox thành một thông điệp nội bộ đã được phân loại và phân phối tới đúng handler:

~~~text
IMAP/POP3 -> Normalize/Persist -> Classify -> Router
                                         |
                      +------------------+-------------------+
                      |                  |                   |
                    Ticket             Invoice             Delivery
                      |                  |                   |
                      +------------------+-------------------+
                                         |
                                         v
                                Business state / audit
~~~

Những điểm quan trọng:

- **EmailType** là loại nghiệp vụ; không đồng nhất với **Content-Type MIME** hoặc Java payload class.
- **Transformer/classifier** xác định loại dựa trên dữ liệu đã chuẩn hóa và bằng chứng đáng tin; **Router** ánh xạ loại tới channel.
- **@Router**, Java DSL router, HeaderValueRouter và ServiceActivator là những công cụ Spring Integration có thể phối hợp, nhưng cần topology và contract nhất quán.
- **UNKNOWN/triage** là nhánh bắt buộc về mặt thiết kế đối với email chưa đủ tín hiệu; technical exception phải có error/retry flow riêng.
- **IMAP Seen, UID, POP3 UIDL và Message-ID** có vai trò khác nhau; idempotency cần một định danh mailbox-scoped và trạng thái xử lý bền vững.
- **Routing thành công chưa phải xử lý thành công.** Handler cần idempotent, có transaction phù hợp, retry và quarantine.
- **Email từ bên ngoài không đáng tin**: From, Subject, MIME headers, attachment và custom headers không tự cấp quyền cho workflow.
- **Đo được kết quả** bằng classified/routed/processed counters, UNKNOWN reason codes, queue age và tests theo từng tầng.

**Một hệ thống inbound email tốt không chỉ phân biệt được “đây là hóa đơn hay thư hỗ trợ”, mà còn chứng minh được vì sao chọn nhánh đó, giữ được email khi xảy ra lỗi và không để dữ liệu chưa xác thực kích hoạt sai quy trình nghiệp vụ.**





