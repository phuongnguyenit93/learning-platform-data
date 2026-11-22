# Chuyển đổi mail message thành domain event

Khi xây dựng một ứng dụng với **Spring Framework Mail** và **Spring Integration Mail**, ta có thể nhận thư từ hộp thư IMAP/POP3 rồi đưa vào các luồng xử lý tự động: tạo ticket hỗ trợ khách hàng, ghi nhận đơn yêu cầu, phát hiện phản hồi, hoặc đồng bộ trao đổi với CRM. Tuy nhiên, **một email nhận được không tự động là một sự kiện nghiệp vụ đáng tin cậy**. Email là dữ liệu bên ngoài dưới dạng MIME, còn domain event là thông tin có cấu trúc và ý nghĩa được hệ thống xác nhận.

Ví dụ, một khách hàng gửi thư với Subject “Yêu cầu hỗ trợ” và nội dung mô tả lỗi. Ở tầng nhận thư, đó là **jakarta.mail.Message**. Qua Spring Integration, nó có thể xuất hiện dưới dạng **org.springframework.messaging.Message<?>** trên một channel. Chỉ sau khi được đọc, chuẩn hóa, kiểm tra điều kiện và gắn với một đối tượng trong domain, hệ thống mới có thể tạo sự kiện như **SupportRequestReceived** hoặc **CustomerReplyRecorded**.

Tài liệu này đi từ cấu trúc thông điệp email, các inbound adapters của Spring Integration, phân tích MIME, mapping và validation, đến việc phát hành domain event an toàn khi có nhiều workers, retry hoặc network failure. Ví dụ tập trung vào **Spring Integration Mail với Jakarta Mail**; các class biểu diễn nghiệp vụ như SupportRequestReceived, InboundMailKey và repository đều là **mô hình minh họa tự xây dựng**, không phải API có sẵn trong Spring Mail.

> **Nguyên tắc cốt lõi:** Nhận được email là một sự kiện ở **ranh giới tích hợp**. Chỉ phát hành **domain event** sau khi có quyết định nghiệp vụ hợp lệ và kết quả cần thiết đã được lưu bền vững. Cần tách **email header do người gửi kiểm soát** khỏi **nguồn tin cậy**, và không dùng cờ SEEN hoặc Message-ID như bảo đảm exactly-once.

## 1. Phân biệt mail message, Spring message và domain event

Ba loại “message” thường cùng xuất hiện:

| Khái niệm | Thư viện/lớp | Nội dung | Vai trò |
| --- | --- | --- | --- |
| **Mail message** | **jakarta.mail.Message** / MimeMessage | Header RFC 5322, MIME parts, flags, địa chỉ, body | Dữ liệu email được lấy từ mailbox |
| **Integration message** | **org.springframework.messaging.Message<T>** | Payload và headers của kênh Spring Integration | Vận chuyển dữ liệu giữa các bước trong flow |
| **Domain event** | Class/record do ứng dụng định nghĩa | Event ID, aggregate, business facts, time, correlation | Ghi nhận một sự kiện có nghĩa và đã được domain chấp nhận |

Ví dụ:

~~~text
IMAP INBOX
   |
   v
jakarta.mail.internet.MimeMessage
   |
   v
Spring Integration inbound mail adapter
   |
   v
org.springframework.messaging.Message<?>
   |
   v
MIME parser / Normalizer
   |
   v
InboundMailCandidate (dữ liệu chưa tin cậy)
   |
   v
Validation + Domain Application Service
   |
   +--> Reject / Quarantine / Needs review
   |
   '--> Persist domain state
               |
               v
          Domain Event
               |
               v
       Outbox / Event Publisher
~~~

### Không dùng trùng tên Message trong Java

Hai lớp sau **khác nhau**:

~~~java
jakarta.mail.Message rawEmail;
org.springframework.messaging.Message<?> channelMessage;
~~~

Khi viết code cùng cần cả hai, nên import một loại và dùng tên đầy đủ cho loại còn lại để tránh xung đột. Header của Spring Message được quản lý bởi message channel; nó không tương đương hoàn toàn với email headers như **From**, **Subject**, **Message-ID** và **Content-Type**.

### Domain event khác “lệnh” và “dữ liệu đầu vào”

**InboundMailReceived** có thể là integration event mang thông tin “mailbox nhận được thư”. **CreateSupportTicket** là command yêu cầu hệ thống làm gì đó. **SupportTicketOpened** là domain event mô tả sự việc đã xảy ra sau khi ticket được tạo.

Không gọi mọi DTO sau parse email là domain event. Một domain event phải thể hiện **điều domain công nhận là đã xảy ra**, không phải điều người gửi email tuyên bố.

## 2. Ví dụ nghiệp vụ: email mở ticket hỗ trợ

Giả sử công ty vận hành mailbox:

~~~text
support@example.test
~~~

Một email đến:

~~~text
From: customer@example.test
To: support@example.test
Subject: Không đăng nhập được
Message-ID: <example-123@sender.test>
Date: ...

Tôi không thể đăng nhập từ sáng nay.
~~~

Ứng dụng cần:

1. Nhận thư từ mailbox được cấu hình.
2. Ghi nhận danh tính kỹ thuật nguồn: mailbox, folder, UIDVALIDITY, UID.
3. Phân tích MIME, lấy văn bản và tham chiếu tệp đính kèm nếu có.
4. Kiểm tra dữ liệu, giới hạn dung lượng và xác định người yêu cầu phù hợp.
5. Áp quy tắc domain để mở ticket hoặc nối vào ticket đang có.
6. Lưu ticket và dấu vết đã xử lý email.
7. Tạo sự kiện **SupportTicketOpened**, chỉ khi ticket thực sự được tạo.
8. Phát hành event qua một cơ chế chịu được crash/retry.
9. Tùy chính sách, đánh dấu thư đã đọc hoặc chuyển folder sau khi xử lý.

### Cùng email có thể dẫn tới các kết quả khác nhau

~~~text
Email A -> hợp lệ, mở ticket mới
           -> SupportTicketOpened

Email B -> là phản hồi ticket đã tồn tại
           -> SupportReplyAdded

Email C -> tự động trả lời hoặc spam
           -> Không có domain event về ticket

Email D -> thiếu thông tin, không xác thực được
           -> NeedsManualReview / RejectedInboundMail
~~~

Đây là lý do mapping không thể chỉ làm **new SupportTicketOpened(subject, body)** ngay khi đọc được email.

## 3. Vai trò của Spring Integration Mail

**Spring Integration** dựa trên mô hình Enterprise Integration Patterns: inbound adapter, message channel, transformer, filter, router, service activator, error channel và outbound adapter. Module Mail cung cấp khả năng nhận/gửi email bằng các giao thức được hỗ trợ.

### Inbound Mail Adapter

Adapter đọc mailbox định kỳ hoặc nhận thông báo thay đổi khi implementation hỗ trợ (ví dụ IMAP IDLE). Nó tạo Spring messages để đưa vào flow.

Các thành phần thường gặp:

- **ImapMailReceiver**: receiver đọc từ IMAP.
- **Pop3MailReceiver**: receiver đọc từ POP3.
- **MailReceivingMessageSource**: nguồn polling dùng receiver.
- **ImapIdleChannelAdapter**: hướng sự kiện cho IMAP IDLE.
- **IntegrationFlow**: DSL định nghĩa pipeline xử lý.
- **MessageChannel**: kênh chuyển thông điệp giữa các endpoint.

Tên lớp/API thuộc Spring Integration Mail, không phải các đối tượng của **org.springframework.mail.javamail.JavaMailSender**. JavaMailSender dùng chủ yếu để gửi SMTP.

### Bối cảnh kỹ thuật và phiên bản

Với các phiên bản Spring Integration hiện đại trên nền Jakarta EE, email thường sử dụng **jakarta.mail.***. Các dự án Spring Framework/Spring Integration cũ hơn có thể dùng **javax.mail.***. Không trộn hai namespace trong cùng một pipeline nếu dependency không tương thích.

Hành vi payload, auto-mark-as-read, xóa sau nhận, cách tải multipart và phương thức DSL có thể khác theo **receiver configuration** và phiên bản. Vì thế phải xác định payload contract thực tế của adapter trước khi viết transformer.

### Cấu trúc flow cơ bản

~~~text
IMAP
  |
  v
Inbound Channel Adapter
  |
  v
mailInboundChannel
  |
  v
Envelope/Source-Key Extractor
  |
  v
MIME Normalizer
  |
  v
Validation + Classification
  |
  v
Domain Application Service
  |
  v
Event Outbox
  |
  v
Kafka / AMQP / internal subscribers
~~~

Các chức năng ngoài cùng flow (database, broker, quản lý attachments) do ứng dụng triển khai; Spring Integration giúp nối các bước, không tự định nghĩa domain events của hệ thống.

## 4. Cấu hình kết nối nhận thư an toàn

Một ứng dụng thường dùng IMAPS:

~~~properties
app.mail.inbound.protocol=imaps
app.mail.inbound.host=imap.example.test
app.mail.inbound.port=993
app.mail.inbound.folder=INBOX
~~~

Đây là properties của ứng dụng minh họa, **không phải cấu hình Spring Boot tự động tạo inbound mail adapter**. Phải tạo receiver/flow riêng và truyền host, credentials, folder, timeout, security policy vào.

Với Jakarta Mail:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Store;

Properties props = new Properties();
props.put("mail.store.protocol", "imaps");
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");
props.put("mail.imaps.writetimeout", "10000");
props.put("mail.imaps.ssl.checkserveridentity", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

Nếu dùng IMAP thường với STARTTLS, các properties nằm dưới tiền tố **mail.imap.**, chẳng hạn:

~~~properties
mail.imap.starttls.enable=true
mail.imap.starttls.required=true
mail.imap.ssl.checkserveridentity=true
~~~

Các phương thức xác thực có thể là credentials ứng dụng, OAuth 2.0 hoặc cơ chế khác tùy provider. Không đưa password/token vào URL hoặc logs. Ví dụ URL receiver chứa credentials có thể tiện cho demo nhưng trong production cần cấu hình secret handling và URL escaping phù hợp.

### SMTP và inbound là hai phần riêng

Hệ thống có thể cùng lúc có:

~~~text
JavaMailSender  -> SMTP provider -> Gửi phản hồi
Mail Receiver   <- IMAP mailbox  <- Nhận yêu cầu
~~~

Sử dụng Spring Boot starter mail không đồng nghĩa một **inbound IntegrationFlow** đã tồn tại. Cần thêm dependency và cấu hình Spring Integration Mail tương thích với dự án.

## 5. Payload contract của inbound adapter

Một Spring Integration **Message<?>** có hai thành phần:

~~~java
Object payload = message.getPayload();
var headers = message.getHeaders();
~~~

Payload chính xác phụ thuộc cách cấu hình receiver:

- Có thể là đối tượng **jakarta.mail.Message** hoặc **MimeMessage**.
- Một số cách cấu hình/phiên bản có thể biến payload thành nội dung đơn giản, mảng messages hoặc kiểu khác.
- Nếu đã có bước transformer upstream, payload có thể là DTO của ứng dụng.
- Headers do flow tạo/enrich có thể chứa metadata; không nên giả định một header đã có và mang giá trị đáng tin khi chưa xác nhận nguồn.

Vì vậy, **domain mapper phải nhận một hợp đồng rõ**, chẳng hạn **RawInboundMail** chứa một MimeMessage và metadata nguồn, hoặc **ParsedInboundMail** sau bước parse. Không cast tùy tiện:

~~~java
// Dễ lỗi nếu adapter đã cấu hình đơn giản hóa payload:
jakarta.mail.internet.MimeMessage mime =
        (jakarta.mail.internet.MimeMessage) message.getPayload();
~~~

Trong flow đã chọn rõ raw MimeMessage payload, cast có thể hợp lệ. Nhưng cần một bước kiểm tra/normalization tại ranh giới thay vì để business service phụ thuộc vào cấu hình receiver.

### Header của Spring Message chưa phải thông tin được xác minh

Khi một transformer chuyển From/Subject từ MIME sang Spring headers, những giá trị đó vẫn là **dữ liệu do email sender cung cấp**. Việc chúng nằm trong **MessageHeaders** không làm chúng trở thành trusted identity.

Đừng dùng:

~~~java
// Không đủ an toàn cho phân quyền:
if ("admin@example.test".equals(mailFrom)) {
    approvePayment();
}
~~~

Để thực hiện các thao tác nghiệp vụ quan trọng, phải có xác thực/ủy quyền ở một tầng đáng tin, ví dụ link xác nhận đăng nhập, token một lần, mapping người dùng đã xác minh, hoặc bằng chứng từ inbound provider được tin cậy cùng chính sách domain.

## 6. Kiến trúc hai lần chuyển đổi

Nên tách **technical normalization** và **domain interpretation**:

~~~text
MimeMessage
    |
    v
[Technical Mapper]
    |
    v
InboundMailCandidate
  - source key
  - sender/display name (untrusted)
  - recipients (untrusted)
  - headers
  - text/plain
  - sanitized HTML reference (if any)
  - attachment metadata/references
    |
    v
[Business Validator / Application Service]
    |
    v
Domain Model / Business Action
    |
    v
Domain Event
~~~

Lợi ích:

1. Parser MIME có thể test độc lập với nghiệp vụ.
2. Thay IMAP bằng webhook inbound của một ESP chỉ ảnh hưởng adapter.
3. Không kéo **jakarta.mail.Message** vào domain model.
4. Domain event có schema ổn định, không phụ thuộc raw MIME boundary/encoding.
5. Có nơi ghi nhận lỗi parse và quarantine mà chưa tạo tác động nghiệp vụ.
6. Có thể bổ sung nguồn tin cậy, kiểm soát kích thước, chống trùng trước domain processing.

### InboundMailCandidate chưa phải domain event

Record **InboundMailCandidate** chỉ diễn tả dữ liệu đã được trích xuất, chưa chắc người gửi có quyền mở ticket/duyệt đơn. Nó có thể nằm trong một **integration layer** hoặc **anti-corruption layer**, không nhất thiết đi vào event stream của domain.

### Event chỉ được tạo khi domain chấp nhận

Một email reply có thể map thành:

~~~text
Mail candidate
   |
   v
TicketApplicationService.recordReply(...)
   |
   +--> TicketReplyRejected (nếu model của hệ thống có định nghĩa)
   |
   '--> TicketReplyAdded (khi reply được lưu)
~~~

Không phải mọi ứng dụng đều cần event Rejected; một số trường hợp chỉ cần log, quarantine hoặc báo lỗi vận hành. Nhưng event **TicketReplyAdded** không được phát hành nếu việc thêm reply chưa thành công.

## 7. Mô hình dữ liệu cho ranh giới inbound

Ví dụ khai báo record:

~~~java
import java.time.Instant;
import java.util.List;

public record InboundMailSource(
        String tenantId,
        String mailboxId,
        String folderName,
        long uidValidity,
        long uid
) {
}

public record InboundAttachment(
        String storageKey,
        String suppliedFileName,
        String detectedMediaType,
        long sizeBytes
) {
}

public record InboundMailCandidate(
        InboundMailSource source,
        String providerMessageId,
        String rawFrom,
        List<String> rawRecipients,
        String subject,
        String plainText,
        String htmlText,
        List<InboundAttachment> attachments,
        Instant emailSentAt,
        Instant observedAt
) {
}
~~~

Các record này là ví dụ. Với những hệ thống không nhận HTML, có thể chỉ giữ văn bản thuần. Với tệp đính kèm, nên lưu **storageKey do ứng dụng sinh**, không gửi raw bytes trong mọi domain event.

### Chú ý đặt tên trường

- **rawFrom**: giá trị từ email header, chưa phải danh tính đã được xác thực.
- **providerMessageId**: thường lấy từ Message-ID; có thể null/trùng/giả mạo.
- **emailSentAt**: lấy từ Date/SentDate, có thể bị sender điều chỉnh.
- **observedAt**: thời điểm ứng dụng ghi nhận thư; không nhất thiết là thời điểm server nhận chính xác.
- **uid + uidValidity**: định danh kỹ thuật trong một folder cụ thể; không phải khóa global.
- **attachments**: metadata và references đã được lưu an toàn.

Tách tên như vậy giúp hạn chế việc một developer dùng rawFrom hoặc Message-ID làm bằng chứng phân quyền.

## 8. Định danh nguồn thư và chống xử lý trùng

Một IMAP message có **message sequence number** chỉ là vị trí tương đối trong folder tại thời điểm đó. Khi xóa/expunge thư, số thứ tự có thể thay đổi. Để xác định lại một message giữa các lần poll, IMAP có **UID** và **UIDVALIDITY**.

Một khóa nguồn minh họa:

~~~text
tenantId
  +
mailboxId
  +
folderId / folderName
  +
UIDVALIDITY
  +
UID
  =
InboundMailSourceKey
~~~

### Tại sao cần UIDVALIDITY?

Hai messages thuộc hai lần tạo lại mailbox khác nhau có thể cùng số UID. UIDVALIDITY phân biệt các “epoch” của mailbox. Nếu server thay UIDVALIDITY, checkpoint UID cũ không còn cùng nghĩa; app cần quy trình resynchronization có kiểm soát.

### Tại sao Message-ID không đủ?

Header **Message-ID** có thể bị thiếu, bị sender đặt trùng hoặc thay đổi qua forwarding/copy. Hai bản copy của một email ở hai folders cũng có thể cùng Message-ID nhưng UID khác nhau. Message-ID hữu ích cho correlation/reply threading, **không phải khóa bảo đảm một sự kiện nghiệp vụ duy nhất**.

### UID của một bản copy có thể khác UID nguồn

Nếu app đọc thư từ INBOX rồi copy/move sang Processed, message tại folder mới có thể nhận UID khác. Khóa nguồn gốc phải được bảo toàn ở bảng application hoặc mapping, tránh tạo cùng ticket lần hai chỉ vì bản copy xuất hiện trong folder khác.

### Không giả định mọi inbound source đều có IMAP UID

Với **POP3**, mô hình flags/UID khác; POP3 có UIDL khi server hỗ trợ, không có UIDVALIDITY theo IMAP. Với **HTTP inbound webhook**, nhà cung cấp có thể cấp event ID/request ID. Nên định nghĩa một **source identity abstraction** cho mỗi transport, ví dụ:

~~~java
public sealed interface MailSourceIdentity
        permits ImapSourceIdentity, ProviderEventIdentity {
}

public record ImapSourceIdentity(
        String mailboxId,
        String folder,
        long uidValidity,
        long uid
) implements MailSourceIdentity {
}

public record ProviderEventIdentity(
        String provider,
        String accountId,
        String eventId
) implements MailSourceIdentity {
}
~~~

Đây là mô hình mở rộng minh họa: nếu dùng sealed interface, cần phiên bản Java tương thích. Với POP3 có thể bổ sung Pop3SourceIdentity gồm account/mailbox và UIDL cùng chính sách retention.

### UID phải được lấy trong đúng vòng đời folder

Jakarta Mail API:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public static InboundMailSource identify(
        Message message,
        String tenantId,
        String mailboxId
) throws Exception {
    Folder folder = message.getFolder();
    if (folder == null || !folder.isOpen()) {
        throw new IllegalStateException(
                "IMAP folder phải còn mở khi lấy UID"
        );
    }
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder không hỗ trợ UIDFolder"
        );
    }

    return new InboundMailSource(
            tenantId,
            mailboxId,
            folder.getFullName(),
            uidFolder.getUIDValidity(),
            uidFolder.getUID(message)
    );
}
~~~

Trong Spring Integration, **không được giả định mọi Message payload còn giữ Folder mở tại thời điểm handler chạy**. Receiver có thể fetch/đóng folder trước downstream; hành vi phụ thuộc cấu hình và implementation. Nếu UID cần cho dedup, giải pháp đúng là **đưa source metadata vào message trong lúc receiver vẫn có đủ thông tin**, dùng một receiver/transformer hoặc cơ chế header/metadata được kiểm chứng với phiên bản thực tế, rồi mới tách processing sang worker khác. Đừng dựa vào việc gọi **message.getFolder()** tùy ý sau khi adapter đã đóng connection.

## 9. Thiết lập inbound adapter và channel trong Spring Integration

Một cấu hình polling có thể bắt đầu từ một **ImapMailReceiver**. Ví dụ dùng Spring Integration DSL:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class InboundMailFlowConfiguration {

    @Bean
    public ImapMailReceiver mailReceiver() {
        ImapMailReceiver receiver = new ImapMailReceiver(
                "imaps://mail-reader:example-password@imap.example.test:993/INBOX"
        );
        receiver.setShouldMarkMessagesAsRead(false);
        receiver.setShouldDeleteMessages(false);
        return receiver;
    }

    @Bean
    public IntegrationFlow inboundMailFlow(
            ImapMailReceiver receiver,
            InboundMailHandler handler
    ) {
        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(
                        source,
                        e -> e.poller(
                                Pollers.fixedDelay(
                                        Duration.ofSeconds(30)
                                )
                        )
                )
                .handle(handler)
                .get();
    }
}
~~~

**Đây là ví dụ cấu trúc**, cần điều chỉnh theo phiên bản Spring Integration đang dùng. Các convenience DSL factories và một số overload có thể thay đổi giữa các phiên bản. URL/credentials trong ví dụ chỉ là placeholder để thấy cấu trúc, **không viết password thật trong source**. Thực tế nên nhận cấu hình qua secret manager, xử lý percent-encoding khi sử dụng mail store URI, và không in URI chứa credentials trong logs.

### Vì sao tắt auto-mark-read và auto-delete?

Nếu receiver đánh dấu SEEN hoặc xóa message ngay sau khi lấy ra khỏi mailbox, business handler có thể thất bại trước khi tạo ticket nhưng lần poll sau không còn nhận lại đúng candidates. Vì vậy đối với pipeline cần xử lý bền vững, nên xác định rõ:

- Receiver có tự đánh dấu SEEN không?
- Có tự xóa/expunge messages không?
- Dùng thư chưa đọc hay UID checkpoint để tìm messages?
- Nếu flow bị crash, có thể discovery lại source messages an toàn không?

**setShouldMarkMessagesAsRead(false)** cho phép chủ động kiểm soát thời điểm đánh dấu khi receiver/provider hỗ trợ semantics đó. Nhưng **đọc body bằng IMAP không dùng PEEK vẫn có thể ảnh hưởng SEEN**; cần kiểm tra cấu hình fetch và provider thực tế. Không xem một property là bảo đảm tuyệt đối.

### Polling cần kiểm soát concurrency

Một instance poller có thể fetch nhiều messages; nhiều replicas cũng có thể cùng đọc INBOX. Chỉ tắt auto-mark-read không giải quyết việc hai workers xử lý cùng một message. Cần persistent source key và cơ chế claim/dedup ở database.

### Spring Integration không thay cho Spring Mail sender

Inbound adapter nhận mail thành messages trên channel; để gửi phản hồi qua SMTP, có thể dùng outbound mail adapter hoặc JavaMailSender theo thiết kế. Không gắn logic gửi phản hồi vào parser MIME một cách khó kiểm soát side effect.

## 10. Tạo handler chỉ nhận raw mail

Mục tiêu là ranh giới mã rõ ràng: handler nhận **Spring Message<?>**, kiểm tra shape của payload và gọi service chuyên xử lý inbound mail. Không truyền thẳng raw MimeMessage sang domain.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.stereotype.Component;

@Component
public class InboundMailHandler implements MessageHandler {

    private final InboundMailProcessingService service;

    public InboundMailHandler(InboundMailProcessingService service) {
        this.service = service;
    }

    @Override
    public void handleMessage(Message<?> message) {
        Object payload = message.getPayload();
        if (!(payload instanceof MimeMessage mime)) {
            throw new IllegalArgumentException(
                    "Expected raw MimeMessage; check receiver configuration"
            );
        }

        service.process(mime, message.getHeaders());
    }
}
~~~

**InboundMailProcessingService** là thành phần của ứng dụng. Ví dụ trên hợp lệ khi inbound adapter đã được cấu hình để output từng **MimeMessage** và nó còn truy cập được dữ liệu cần thiết. Nếu receiver trả payload khác (ví dụ simple content, đối tượng Message không phải MimeMessage, hoặc batch), phải thêm một normalization adapter đúng loại thay vì cast.

### Đừng lấy SourceKey từ một header ngẫu nhiên

Nếu UID/UIDVALIDITY đã được enrich vào Spring MessageHeaders trước đó, handler có thể lấy các headers được định nghĩa bởi ứng dụng như **mailboxId**, **folder**, **uidValidity** và **uid**. Nhưng chỉ tin chúng khi chúng được **adapter nội bộ** tạo từ nguồn đã xác minh; không dùng header email do bên ngoài đặt trùng tên rồi coi là nguồn kỹ thuật.

### Header extraction nên diễn ra trước khi resource bị đóng

Để xử lý asynchronous trên ExecutorChannel hoặc queue, **không chuyển nguyên MimeMessage phụ thuộc Folder đang mở sang thread/host khác**. Thay vào đó:

1. Trong ranh giới nhận thư, trích UID/source identity.
2. Tải/stream phần dữ liệu cần thiết theo giới hạn.
3. Lưu một **inbound snapshot** bền vững hoặc DTO đã chuẩn hóa.
4. Chuyển **snapshot ID** hoặc DTO độc lập qua channel.
5. Đóng Folder/Store khi hoàn tất transport work.

Làm vậy giúp downstream không bị **FolderClosedException** khi đọc body và không gắn trạng thái domain với lifecycle của IMAP connection.

## 11. Chuẩn hóa MIME: không chỉ lấy Subject và Body

Email MIME có thể có:

- **text/plain**: nội dung văn bản thuần.
- **text/html**: nội dung HTML.
- **multipart/alternative**: nhiều biến thể nội dung.
- **multipart/mixed**: body cùng attachments.
- **multipart/related**: HTML và các nội dung tham chiếu CID.
- **message/rfc822**: email lồng bên trong.
- **transfer encodings** và **charsets** khác nhau.

Ví dụ:

~~~text
MimeMessage
  |
  '-- multipart/mixed
        |
        +-- multipart/alternative
        |      |
        |      +-- text/plain
        |      '-- text/html
        |
        +-- application/pdf (attachment)
        '-- image/png (attachment)
~~~

Không dùng một phép cast cứng:

~~~java
// Có thể ClassCastException khi message là Multipart.
String body = (String) mime.getContent();
~~~

Thư viện có thể trả về **String**, **Multipart**, **InputStream**, hoặc kiểu khác theo MIME type và implementation.

### Parse từng bước

Một parser an toàn thường:

1. Đọc header metadata với giới hạn.
2. Kiểm tra message size và số MIME parts.
3. Chọn text/plain hoặc chuyển HTML thành dạng text theo policy.
4. Chuẩn hóa Unicode/newlines nhưng giữ nội dung có ý nghĩa.
5. Tách attachments vào storage riêng, scan/validate.
6. Trả **InboundMailCandidate** bất biến cho domain layer.

### Lưu ý chọn plain-text trong multipart/alternative

Thư có thể chứa cả plain và HTML với nội dung không hoàn toàn giống nhau. Nếu ứng dụng chỉ tự động phân tích plain text, phải hiểu rằng sender có thể tạo plain khác HTML. Đối với nghiệp vụ nhạy cảm, không quyết định quyền hoặc số tiền chỉ dựa vào nội dung email chưa được xác minh.

## 12. Một MIME parser có giới hạn tài nguyên

Đoạn mã sau minh họa **duyệt phần văn bản**, không phải parser attachments đầy đủ. Giới hạn độ sâu/số part/chiều dài văn bản giúp giảm nguy cơ dữ liệu đầu vào quá lớn:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.BodyPart;
import java.util.concurrent.atomic.AtomicInteger;

public final class PlainTextExtractor {

    private final int maxDepth = 8;
    private final int maxParts = 80;
    private final int maxTextChars = 200_000;

    public String extract(Part root) throws Exception {
        StringBuilder text = new StringBuilder();
        AtomicInteger parts = new AtomicInteger();
        visit(root, text, parts, 0);
        return text.toString();
    }

    private void visit(
            Part part,
            StringBuilder text,
            AtomicInteger parts,
            int depth
    ) throws Exception {
        if (depth > maxDepth || parts.incrementAndGet() > maxParts) {
            throw new IllegalArgumentException(
                    "MIME structure limit exceeded"
            );
        }

        String disposition = part.getDisposition();
        if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
            return; // Xử lý attachment bằng pipeline riêng.
        }

        if (part.isMimeType("text/plain")) {
            Object content = part.getContent();
            if (content instanceof String value) {
                if ((long) text.length() + value.length()
                        > maxTextChars) {
                    throw new IllegalArgumentException(
                            "Text body too large"
                    );
                }
                if (!text.isEmpty()) {
                    text.append('\n');
                }
                text.append(value);
            }
            return;
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                visit(child, text, parts, depth + 1);
            }
        }
    }
}
~~~

Đoạn mã trên nhằm giải thích traversal; với **Java StringBuilder** trong JDK, kiểm tra method isEmpty theo phiên bản Java (nếu JDK không hỗ trợ, dùng **text.length() > 0**). Đoạn mã cũng chưa giới hạn raw MIME bytes **trước khi** thư viện decode body: một part được nén/mã hóa có thể lớn trước khi tạo String. Production phải giới hạn **kích thước nguồn, bytes thực đọc, số phần tử, thời gian xử lý và dung lượng attachments**, đồng thời xử lý charset/MIME malformed.

### Không lấy attachment bằng cách tin file name

**part.getFileName()** là dữ liệu do sender cung cấp, có thể chứa ký tự điều khiển, path separators hoặc phần mở rộng không phản ánh nội dung thật. Nếu cần lưu tệp, tạo storage key do server sinh và lưu supplied filename như metadata đã chuẩn hóa, không dùng trực tiếp làm đường dẫn.

### HTML phải được coi là dữ liệu chưa tin cậy

Nếu cần hiển thị HTML trong giao diện nội bộ, hãy áp **sanitization** phù hợp và chặn script, tracking, external references theo policy. Không nhúng trực tiếp HTML email vào giao diện dashboard như HTML đáng tin.

## 13. Phân tích header để phân loại, không để xác thực quyền

Các header hữu ích gồm:

| Header/thuộc tính | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **From** | Địa chỉ người gửi được khai báo | Có thể bị giả mạo |
| **Reply-To** | Địa chỉ mong muốn nhận phản hồi | Không tự chứng minh quyền sở hữu |
| **To / Cc** | Người nhận được trình bày | Có thể khác envelope recipient, Bcc không hiện |
| **Subject** | Tiêu đề email | Có thể thiếu hoặc bị sửa |
| **Message-ID** | Dấu vết để threading | Có thể thiếu, giả mạo, trùng |
| **In-Reply-To** | Tham chiếu message cha | Không đủ để cho phép ghi vào ticket |
| **References** | Chuỗi tham chiếu luồng thư | Có thể bị sender giả |
| **Date** | Thời điểm sender khai báo | Không đáng tin cho event occurredAt |
| **Auto-Submitted** | Có thể chỉ ra tự động phản hồi | Không phải tín hiệu chống loop tuyệt đối |
| **Content-Type** | MIME type đã khai báo | Cần kiểm chứng khi xử lý attachment |
| **Authentication-Results** | Kết quả xác thực email được hệ thống nhận thêm vào | Chỉ tin khi đến từ hạ tầng inbound/trust boundary đã xác định |

### Lấy thông tin header với Jakarta Mail

~~~java
import jakarta.mail.Message;
import jakarta.mail.Address;
import java.util.Date;

public static void inspect(Message message) throws Exception {
    Address[] from = message.getFrom();
    String subject = message.getSubject();
    Date sent = message.getSentDate();
    String[] messageIds = message.getHeader("Message-ID");
    String[] replies = message.getHeader("In-Reply-To");

    // Chuẩn hóa, giới hạn độ dài và chuyển sang candidate.
    // Không dùng raw From hoặc In-Reply-To để phê duyệt giao dịch.
}
~~~

### Header Authentication-Results phải có nguồn tin cậy

Một email đi qua mail gateway có thể được ghi thêm kết quả SPF/DKIM/DMARC. Nhưng kẻ gửi cũng có thể chèn một **Authentication-Results** giả trong raw message. Nếu cần dựa vào kết quả xác thực để ánh xạ người gửi, phải lấy dữ liệu từ **inbound provider đáng tin cậy**, có quy trình loại bỏ/ghi đè những header do người ngoài có thể tự khai và biết chính xác trust boundary.

### Xử lý reply threading

Một email chứa:

~~~text
In-Reply-To: <original-ticket-notice@example.test>
References: <original-ticket-notice@example.test>
~~~

có thể là phản hồi cho ticket cũ. Nhưng cần xác định:

1. Message-ID gốc có mapping tới ticket trong database không?
2. Mailbox nhận có thuộc tenant đang xử lý không?
3. Người gửi có được phép thêm nội dung vào ticket đó không?
4. Ticket đã bị đóng hoặc bị giới hạn truy cập chưa?
5. Có dấu hiệu email tự động/loop/spoof không?

Chỉ sau khi các điều kiện nghiệp vụ đạt, mới phát **SupportReplyAdded**. Không chỉ cần tìm thấy Message-ID trong References là đủ.

## 14. Chuẩn hóa và validation trước khi vào domain

Một input boundary có thể chia validation thành bốn tầng:

1. **Transport validation**: kết nối và mailbox đã được cấu hình, email tồn tại, nguồn định danh hợp lệ.
2. **MIME validation**: parse thành công, kích thước/charset/attachment loại được phép.
3. **Application validation**: tenant, recipient route, required fields, schema của mail command.
4. **Domain authorization**: người gửi có quyền yêu cầu hành động, ticket/order hiện tại cho phép thay đổi.

### Ví dụ các lỗi khác nhau

| Tình huống | Kết quả gợi ý | Có nên phát domain event? |
| --- | --- | --- |
| Không lấy được MIME do IMAP timeout | RETRY_WAIT | Không |
| MIME hỏng, không thể parse | QUARANTINE / PERMANENT_FAILED | Không phát event domain thành công |
| Body rỗng nhưng policy yêu cầu nội dung | REJECTED / REVIEW | Không |
| Người gửi chưa xác thực cho thao tác nhạy cảm | REVIEW / REJECTED | Không |
| Reply trỏ tới ticket không tồn tại | REJECTED hoặc unmatched queue | Không phát SupportReplyAdded |
| Ticket mở thành công và được lưu | PROCESSED | Có thể phát SupportTicketOpened |
| Cùng UID đã PROCESSED | DUPLICATE | Không phát lần nữa |
| Ticket service timeout sau external side effect | UNKNOWN | Đối soát trước retry |

Không dùng một exception chung dẫn tới retry vĩnh viễn. Parser malformed sẽ bị chạy lại vô hạn nếu mọi lỗi đều được coi là transient. Ngược lại, network timeout tạm thời không nên khiến một email bị bỏ đi ngay.

### Tách lỗi có thể retry và lỗi vĩnh viễn

Một mô hình ứng dụng:

~~~java
public enum InboundFailureKind {
    TRANSIENT_TRANSPORT,
    TRANSIENT_DEPENDENCY,
    INVALID_MIME,
    UNSUPPORTED_ATTACHMENT,
    UNAUTHORIZED_SENDER,
    UNMATCHED_THREAD,
    AMBIGUOUS_BUSINESS_OUTCOME
}
~~~

Các enums này là do dự án thiết kế. **AMBIGUOUS_BUSINESS_OUTCOME** khác lỗi retry thông thường: side effect có thể đã xảy ra, cần đối soát để tránh tạo hai tickets hoặc gửi hai phản hồi.

## 15. Mapping thành một domain event có cấu trúc

Với use case mở ticket mới, một domain event nên chứa **business facts**:

~~~java
import java.time.Instant;
import java.util.UUID;

public record SupportTicketOpened(
        UUID eventId,
        int schemaVersion,
        UUID ticketId,
        String tenantId,
        String customerId,
        String sourceMailboxId,
        String sourceReference,
        Instant occurredAt,
        String correlationId
) {
}
~~~

Ở đây:

- **eventId** được tạo một lần khi domain event được ghi bền vững, không thay đổi mỗi lần publish retry.
- **schemaVersion** cho phép xử lý thay đổi format.
- **ticketId** là ID aggregate nghiệp vụ, khác source UID.
- **tenantId/customerId** đã được ánh xạ qua chính sách domain; không lấy raw From làm customerId.
- **sourceMailboxId/sourceReference** hỗ trợ trace mà không cần nhúng raw MIME vào event.
- **occurredAt** là lúc domain ghi nhận hành động đã xảy ra, không mặc định bằng Date header.
- **correlationId** liên kết mail poll, processing record, ticket và event outbox.

### Event tối thiểu hay đầy đủ?

Hai thiết kế thường gặp:

**Event mang định danh:**

~~~text
SupportTicketOpened {
  eventId,
  ticketId,
  occurredAt,
  ...
}
~~~

Consumer tra ticket details theo hợp đồng riêng khi cần. Ưu điểm là tránh lan truyền PII và schema gọn; nhược điểm là consumer phụ thuộc lookup.

**Event mang snapshot được chọn lọc:**

~~~text
SupportTicketOpened {
  eventId,
  ticketId,
  category,
  priority,
  summary,
  ...
}
~~~

Ưu điểm là consumer có đủ dữ liệu tối thiểu. Nhưng phải có chính sách quyền riêng tư, encryption/retention và schema evolution khi chứa fields có thể nhạy cảm.

Không nhúng toàn bộ MIME, access token, password reset link hoặc file attachment bytes vào một public event bus chỉ để “giữ nguyên thông tin”.

### Tránh event tên có ý nghĩa sai

Không nên gọi **EmailReceived** là **OrderApproved** chỉ vì email có Subject “Approve order”. Để phát **OrderApproved**, domain phải xác nhận người yêu cầu có quyền, order đang trong trạng thái cho phép và thay đổi đã được lưu.

## 16. Từ candidate đến quyết định nghiệp vụ

Một flow application service:

~~~text
InboundMailCandidate
       |
       v
Identify tenant + classify purpose
       |
       v
Resolve customer identity safely
       |
       v
Dedup / claim source key
       |
       v
Validate ticket request/reply
       |
       v
Apply domain rules
       |
       +-- Reject / Needs review
       |
       '--> Persist Ticket and TicketEvent
                   |
                   v
          Commit business transaction
                   |
                   v
              Publish event
~~~

### Một kiểu trả kết quả rõ nghĩa

~~~java
public enum InboundDecisionType {
    PROCESSED,
    DUPLICATE,
    REJECTED,
    RETRY_WAIT,
    NEEDS_REVIEW
}

public record InboundDecision(
        InboundDecisionType type,
        String eventId,
        String reasonCode
) {
}
~~~

Với loại PROCESSED, eventId có thể chứa ID domain event đã lưu. Với DUPLICATE, có thể trả ID event đã được ghi trước đó. Với REJECTED, không nhất thiết phát domain event cùng tên với tác vụ thành công; hệ thống có thể lưu audit ở tầng integration.

### Không để parser thực hiện hành động nghiệp vụ

Parser chỉ trích xuất/chuẩn hóa và báo lỗi dữ liệu:

~~~java
InboundMailCandidate candidate =
        normalizer.normalize(rawMail, source);

InboundDecision decision =
        applicationService.handle(candidate);
~~~

Tách hai bước giúp việc thay MIME parser, receiver hay message channel không thay đổi quy tắc mở ticket.

## 17. Domain service và ranh giới transaction

Giả sử việc tạo ticket và ghi event cùng sử dụng một database. Một thiết kế an toàn là:

~~~text
BEGIN DB TRANSACTION
    |
    +-- Lock/claim source key
    |
    +-- Validate customer and ticket
    |
    +-- Insert ticket / reply
    |
    +-- Mark inbound processing PROCESSED
    |
    '-- Insert domain event into outbox
    |
COMMIT
    |
    v
Separate publisher reads event outbox
    |
    v
Publish to broker, retry safely
~~~

Với các thay đổi **cùng database** và cùng transaction manager, ticket, trạng thái inbound và event outbox được commit hoặc rollback cùng nhau. Việc gọi IMAP server, object storage hoặc broker **không tự động** tham gia cùng database transaction đó.

### Ví dụ application service minh họa

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupportMailApplicationService {

    private final InboundProcessingRepository inbound;
    private final CustomerResolver customers;
    private final SupportTicketRepository tickets;
    private final DomainEventOutbox events;
    private final Clock clock;

    public SupportMailApplicationService(
            InboundProcessingRepository inbound,
            CustomerResolver customers,
            SupportTicketRepository tickets,
            DomainEventOutbox events,
            Clock clock
    ) {
        this.inbound = inbound;
        this.customers = customers;
        this.tickets = tickets;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public InboundDecision handle(InboundMailCandidate candidate) {
        String sourceKey = sourceKeyOf(candidate.source());

        if (!inbound.tryRegisterOnce(sourceKey)) {
            return new InboundDecision(
                    InboundDecisionType.DUPLICATE,
                    inbound.eventIdOf(sourceKey),
                    "ALREADY_PROCESSED"
            );
        }

        String customerId = customers.resolveAuthorizedCustomer(
                candidate
        );

        UUID ticketId = tickets.openTicket(
                candidate.source().tenantId(),
                customerId,
                candidate.subject(),
                candidate.plainText()
        );

        SupportTicketOpened event = new SupportTicketOpened(
                UUID.randomUUID(),
                1,
                ticketId,
                candidate.source().tenantId(),
                customerId,
                candidate.source().mailboxId(),
                sourceKey,
                Instant.now(clock),
                sourceKey
        );

        events.save(event);
        inbound.markProcessed(sourceKey, event.eventId().toString());
        return new InboundDecision(
                InboundDecisionType.PROCESSED,
                event.eventId().toString(),
                "TICKET_OPENED"
        );
    }

    private String sourceKeyOf(InboundMailSource source) {
        return source.tenantId() + ":"
                + source.mailboxId() + ":"
                + source.folderName() + ":"
                + source.uidValidity() + ":"
                + source.uid();
    }
}
~~~

**InboundProcessingRepository**, **CustomerResolver**, **SupportTicketRepository** và **DomainEventOutbox** là interfaces do ứng dụng tự triển khai. Phương thức **tryRegisterOnce** phải thật sự atomic, ví dụ dựa trên unique constraint/row lock; code trên giả định dữ liệu cùng database và lỗi không thành công sẽ rollback transaction. **sourceKeyOf** chỉ là demo cho cấu trúc định danh; production nên dùng encoding có cấu trúc/length prefix hoặc hash canonical representation để tránh nhập nhằng do dấu hai chấm trong các thành phần.

### Transactional subtleties

Không thực hiện toàn bộ IMAP download, virus scan hoặc gọi API bên ngoài **bên trong transaction** nếu có thể tránh, vì chúng có thời gian không dự đoán được và có thể giữ DB locks lâu. Nên chia:

1. Fetch + normalize + lưu snapshot có kiểm soát.
2. Claim source/processing record.
3. Trong transaction ngắn: domain mutation + event outbox + processing state.
4. Sau commit: đồng bộ IMAP SEEN/move và phát hành outbox.

Nếu bước 2 và 3 thuộc nhiều transactions, phải có lease/version để nhiều workers không cùng xử lý. Nếu side effect ở một external API, cần idempotency key hoặc reconciliation riêng.

## 18. Bảo đảm eventId ổn định khi retry

Một lỗi phổ biến:

~~~text
Lần poll #1:
  UID 108 -> tạo SupportTicketOpened(eventId=A)
  Gửi broker -> timeout

Lần poll #2:
  UID 108 -> tạo SupportTicketOpened(eventId=B)
  Gửi broker -> accepted
~~~

Nếu tạo eventId mới mỗi lần thử, consumers khó biết A và B là cùng một logical event. Cần lưu **eventId bền vững** trong transaction, sau đó retries publisher sử dụng lại eventId đó.

~~~text
Inbound source key -> unique processing row
                  -> one domain mutation
                  -> one event outbox row
                  -> stable eventId
                  -> many delivery attempts (if necessary)
~~~

### Database unique constraint minh họa

~~~sql
CREATE TABLE inbound_mail_processed (
    source_key VARCHAR(512) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    event_id UUID,
    processed_at TIMESTAMPTZ
);

CREATE TABLE domain_event_outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    publish_attempts INTEGER NOT NULL DEFAULT 0
);
~~~

Các bảng là ví dụ PostgreSQL, không phải Spring Integration auto-generated schema. Nếu outbox publisher bị crash sau khi broker **đã nhận** event nhưng trước khi cập nhật published_at, nó có thể publish lại. Consumers vẫn cần idempotent processing theo **eventId** hoặc aggregate version.

### Domain event không có bảo đảm exactly-once toàn hệ thống

Unique key giúp mỗi source tạo một business mutation; transactional outbox giúp không mất event giữa business commit và enqueue. Nhưng external broker/API và consumers có thể nhận lại event do retries. Vì vậy mục tiêu thực tế thường là **at-least-once delivery + idempotent consumers**, không tự tuyên bố exactly-once end-to-end chỉ vì dùng outbox.

## 19. Spring Integration Transformer, Filter và Service Activator

Một pipeline rõ ràng có thể gồm những bước của Spring Integration:

~~~text
Inbound Adapter
     |
     v
Raw Mail Channel
     |
     v
Transformer: MimeMessage -> InboundMailCandidate
     |
     v
Filter: basic eligibility (size/type/auto-reply)
     |
     v
Service Activator: domain application service
     |
     v
Domain Decision Channel
     |
     +--> PROCESSED -> Event outbox publisher
     +--> RETRY_WAIT -> Retry management
     '--> REJECTED / QUARANTINE -> Review
~~~

### Transformer chỉ chuẩn hóa, không tự tạo domain event

Ví dụ method:

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

public class MailNormalizationComponent {

    private final InboundMailNormalizer normalizer;

    public MailNormalizationComponent(InboundMailNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Transformer(inputChannel = "rawMailChannel",
                 outputChannel = "normalizedMailChannel")
    public InboundMailCandidate transform(Message<?> springMessage) {
        return normalizer.normalize(springMessage);
    }
}
~~~

**InboundMailNormalizer** là service do ứng dụng định nghĩa, có trách nhiệm kiểm tra payload và nguồn metadata. Annotation **@Transformer** thuộc Spring Integration. Trong một số cấu hình dùng Java DSL thay annotation, định nghĩa tương đương có thể là **.transform(normalizer, "normalize")** nếu method signature được framework chấp nhận.

### Filter chỉ nên quyết định điều kiện kỹ thuật cơ bản

~~~java
public boolean allowForProcessing(InboundMailCandidate mail) {
    return mail.plainText() != null
            && mail.plainText().length() <= 200_000
            && mail.source() != null;
}
~~~

Filter thường đơn giản hóa pipeline, nhưng với email **bị từ chối**, phải có đường audit/quarantine và lý do để không im lặng làm mất dấu công việc. Domain authorization của người gửi vẫn nên nằm tại application service, không chỉ ở một filter sơ sài dựa trên Subject.

### Service Activator là ranh giới nghiệp vụ

~~~java
import org.springframework.integration.annotation.ServiceActivator;

public class InboundDomainHandler {

    private final SupportMailApplicationService service;

    public InboundDomainHandler(
            SupportMailApplicationService service
    ) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "normalizedMailChannel")
    public InboundDecision handle(InboundMailCandidate mail) {
        return service.handle(mail);
    }
}
~~~

Đây là các lựa chọn cấu trúc; không cần dùng cả **@Transformer** và DSL tương đương hai lần cho cùng flow. Nếu annotation method trả ra dữ liệu, cấu hình output channel/reply handling phải rõ; một handler không có nơi nhận reply có thể gây cảnh báo/lỗi tùy endpoint contract.

### Tránh gọi publishEvent trực tiếp trong transformer

Transformer có thể được gọi lại khi message được retry. Nếu nó vừa parse vừa tạo ticket vừa publish event, rất khó đảm bảo idempotency. Domain mutation và event creation cần một transaction/service rõ ràng.

## 20. Ack, cờ SEEN, xóa mail và trạng thái domain

Một inbound mail adapter có thể được cấu hình đánh dấu thư đã đọc, xóa thư hoặc để nguyên. Nhưng **IMAP flag SEEN** không phải ACK transaction của database và không phải xác nhận event đã được consumer nhận.

### Ba trạng thái tách biệt

| Trạng thái | Nơi lưu | Ý nghĩa |
| --- | --- | --- |
| **Mailbox read state** | IMAP server, flag SEEN | Hộp thư đang hiển thị đã đọc/chưa đọc |
| **Processing state** | Database ứng dụng | Email đã được xử lý nghiệp vụ chưa |
| **Event publish state** | Event outbox/broker | Domain event đã được publish/ack chưa |

Một tình huống:

~~~text
1. Mail receiver đọc email và tự mark SEEN.
2. MIME parse thành công.
3. Ticket repository gặp lỗi.
4. Flow ném exception.
5. Lần poll sau chỉ tìm UNSEEN.

Kết quả: Mail bị bỏ sót nếu không có recovery riêng.
~~~

Vì vậy với pipeline cần bảo đảm không bỏ sót, chỉ đánh dấu SEEN **sau khi business state đã được lưu an toàn**, và nên dựa vào bảng processing/UID chứ không phụ thuộc duy nhất vào UNSEEN.

### Nếu set SEEN thất bại sau commit?

~~~text
Domain ticket = committed
Event outbox = committed
IMAP flag-sync = failed
~~~

Hệ thống **không được tạo lại ticket** vì flag-sync thất bại. Thay vào đó, có thể để một job **mail_flag_sync** riêng và retry set SEEN theo source UID/UIDVALIDITY. Nếu thư bị move/expunge, ghi nhận kết quả và ngừng retry vô hạn.

### Nếu business requirement muốn giữ thư unread?

Không phải workflow nào cũng cần đánh dấu. Ví dụ một ứng dụng chỉ index mail hỗ trợ có thể giữ SEEN theo hành vi của nhân viên webmail; khi đó cờ SEEN là trạng thái giao diện người dùng và **PROCESSED** là trạng thái automation.

### Xóa/expunge không phải ack mặc định

Đừng dùng **setShouldDeleteMessages(true)** hoặc close(expunge=true) như một cách “đánh dấu đã xử lý” nếu chưa có lưu trữ/retention chính thức. Một lần xóa email có thể làm mất bằng chứng cần đối soát và gây hậu quả trên shared mailbox.

## 21. Error channel và phân luồng lỗi

Spring Integration có cơ chế **error channel**, sử dụng các thông điệp lỗi để chuyển exceptions từ các thành phần flow tùy cấu hình endpoint, thread và message channel.

~~~text
inboundMailFlow
      |
      +--> NORMALIZE SUCCESS -> domain service
      |
      +--> MIME PARSE FAILURE -----------+
      |                                 |
      +--> DB TEMPORARY FAILURE --------+--> Error handling
      |                                 |      |
      +--> UNKNOWN BUSINESS OUTCOME ----+      +--> Retry
                                             +--> Quarantine
                                             '--> Reconciliation
~~~

### Phân loại lỗi

| Loại lỗi | Hướng xử lý |
| --- | --- |
| IMAP connection reset / timeout trước fetch | Retry theo backoff, dùng source checkpoint |
| MIME bị hỏng, không thể parse | Quarantine hoặc manual review, không retry vô hạn |
| Attachment quá lớn/không an toàn | Reject/quarantine, audit theo policy |
| Không xác định được tenant/customer | Needs review, không tự tạo sự kiện đặc quyền |
| DB temporarily unavailable | Retry sau backoff, source key giữ nguyên |
| Unique key đã PROCESSED | Duplicate no-op |
| Publisher broker failure | Retry event outbox, không reprocess email |
| External ticket API timeout mơ hồ | UNKNOWN, đối soát để tránh tạo ticket trùng |

### Message-handling error có thể là ErrorMessage

Một thành phần xử lý lỗi có thể kiểm tra payload:

~~~java
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.Message;

public void onError(Message<?> message) {
    if (message instanceof ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        // Phân loại nguyên nhân, ghi metadata đã redact.
        // Không in toàn bộ failed mail payload.
    }
}
~~~

Mã minh họa cách xem ErrorMessage; việc đặt nó vào một error channel cụ thể cần cấu hình channel/endpoint tương ứng. Với flow polling đồng bộ, exception có thể được ném ở thread poller và đi qua error handling khác với flow dùng ExecutorChannel/asynchronous; không giả định mọi lỗi tự xuất hiện trên một channel nếu chưa cấu hình.

### Không dùng error channel làm “thùng rác”

Nếu một lỗi parse bị gửi tới error channel rồi chỉ log một dòng và bỏ qua, email có thể bị mất khỏi luồng xử lý. Cần quyết định cụ thể: retry, quarantine, reject có audit hay manual review. Message source identity phải được lưu để xử lý lại đúng thư.

## 22. Retry, idempotency và chống event trùng

Không thể đặt một **RetryTemplate** quanh toàn bộ flow rồi mặc định không sinh trùng domain events. Hãy phân biệt:

~~~text
Retry IMAP fetch:
  đọc lại cùng email, chưa có business mutation

Retry MIME parse:
  cùng input, thông thường có thể làm lại nếu parser không có side effect

Retry domain operation:
  chỉ an toàn nếu idempotent/transaction-aware

Retry event publishing:
  dùng cùng eventId từ outbox, consumer dedup

Retry IMAP flag sync:
  chỉ cập nhật SEEN, không chạy lại business operation
~~~

### Các loại retry có nguy cơ khác nhau

| Giai đoạn | Tác dụng phụ? | Cách làm |
| --- | --- | --- |
| Fetch metadata | Thường ít, nhưng phụ thuộc flags/fetch | READ_ONLY/peek, reconnect |
| Parse raw MIME | Chủ yếu tính toán, có thể tốn tài nguyên | Giới hạn và quarantine |
| Lưu business state | Có thay đổi DB | Unique key và transaction |
| Gọi external API tạo ticket | Có side effect ngoài DB | Idempotency key hoặc reconciliation |
| Publish domain event | Có side effect broker | Transactional outbox + dedup consumer |
| Set IMAP SEEN | Có side effect mailbox | Đồng bộ riêng, retry theo UID |

### Không thay event ID mỗi lần delivery

Một broker redeliver hai lần:

~~~text
Event id = 123
Delivery #1 -> consumer xử lý -> response lost
Delivery #2 -> consumer thấy id 123 đã xử lý -> skip
~~~

Đây là **idempotent consumer**. Nếu publisher tự sinh event ID mới ở mỗi lần retry, consumer khó biết hai deliveries là một logical event.

### Không nhầm HTTP request idempotency với UID dedup

UID giúp xác định thư nguồn. Nếu business service tạo nhiều records từ cùng thư theo yêu cầu (ví dụ email chứa nhiều order lines), nó có thể cần idempotency key ở cấp **mail source + operation**, chứ không nhất thiết một boolean “email đã xử lý” cho toàn bộ nghiệp vụ.

## 23. Quản lý attachments trong sự kiện

Một email có thể kèm ảnh lỗi, log, hóa đơn hoặc file độc hại. Domain event **không nên mặc định chứa toàn bộ attachment bytes**:

~~~text
MimeMessage
  |
  v
Attachment processor
  |
  +-- Validate size/content type
  +-- Scan/quarantine according to policy
  +-- Store in protected object storage
  '-- Return opaque storage reference
                 |
                 v
       InboundMailCandidate
                 |
                 v
         Domain decision
                 |
                 v
      SupportTicketOpened
        + attachment IDs
~~~

### Vì sao không nhúng Base64 vào event?

- Event size tăng nhanh; một attachment 20 MiB có thể khiến broker record vượt giới hạn.
- Tăng nguy cơ nhân bản PII qua nhiều consumers.
- Không thể thay đổi quyền truy cập hoặc xóa nội dung dễ dàng.
- Malware/retention policies khó được thực thi đồng nhất.
- Domain event schema bị gắn chặt với cách lưu MIME.

Thay vào đó, event có thể chứa **attachment reference IDs** đã được kiểm tra quyền truy cập. Consumer nhận reference không tự động có quyền đọc file: storage service cần kiểm tra tenant/role, TTL và mục đích sử dụng.

### MIME Content-Type không phải chứng cứ loại file thật

Email có thể khai báo:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

nhưng bytes thực tế không phải PDF. Không mở hay đưa file cho người dùng dựa duy nhất vào filename hoặc content type do sender cung cấp. Dùng validation, signature/content inspection, giới hạn kích thước và malware policy tương ứng.

### Xử lý ảnh inline và CID

Ảnh inline trong **multipart/related** có Content-ID và có thể xuất hiện ở body HTML như cid:image-001. Nếu domain cần hiển thị email, phải xử lý CID references theo policy và bảo vệ khỏi remote-content tracking; nếu chỉ cần tạo ticket từ text, không nhất thiết import mọi ảnh inline làm attachment domain.

### Bảo vệ khỏi filename path traversal

Không ghi tệp bằng:

~~~java
// Không an toàn khi filename do sender điều khiển.
var destination = uploadDir.resolve(part.getFileName());
~~~

Hãy dùng storage ID sinh từ server và giữ filename gốc như metadata đã chuẩn hóa, giới hạn độ dài/ký tự. Khi xuất file ra filesystem, kiểm soát path canonicalization và quyền truy cập.

## 24. Thiết kế schema evolution cho domain event

Một integration event có thể chỉ dùng trong một service; một domain event đưa lên Kafka/AMQP có thể có nhiều consumers độc lập. Khi đổi schema, cần tránh phá vỡ consumers cũ.

Ví dụ phiên bản 1:

~~~json
{
  "eventId": "8c75f2c1-0000-4000-8000-000000000001",
  "eventType": "SupportTicketOpened",
  "schemaVersion": 1,
  "ticketId": "9f1a00a0-0000-4000-8000-000000000002",
  "tenantId": "tenant-7",
  "occurredAt": "2026-01-01T10:00:00Z"
}
~~~

Phiên bản 2 có thể thêm **category** như một optional field; consumers cũ có thể bỏ qua field không biết nếu deserializer/config cho phép. Nếu thay đổi ý nghĩa một field đã tồn tại, cần versioning rõ và migration contract, không chỉ đổi tên Java record.

### Sự kiện nên mô tả điều đã xảy ra

~~~text
SupportTicketOpened
SupportReplyAdded
CustomerContactVerified
~~~

là các tên event có ý nghĩa quá khứ trong domain. **ParseInboundMail** hay **CreateTicketFromEmail** thường là commands/steps, không phải domain facts.

### Lưu metadata trong event envelope

Một event envelope:

~~~java
public record DomainEventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateType,
        String aggregateId,
        String tenantId,
        String correlationId,
        String causationId,
        java.time.Instant occurredAt,
        T payload
) {
}
~~~

**correlationId** theo dõi toàn luồng inbound email, **causationId** có thể liên kết sự kiện nguồn trực tiếp; cần định nghĩa semantics rõ để không nhầm email Message-ID không tin cậy với causationId nội bộ.

### Ordering theo aggregate

Nếu một ticket nhận 3 thư liên tiếp, các events **SupportReplyAdded** có thể cần ordering theo ticket ID/aggregate version. Ordering trong mailbox và ordering publish ra broker không nhất thiết giống nhau vì retry, nhiều workers hoặc provider delays.

Một thiết kế có thể lưu **aggregateVersion** tăng trong transaction, chọn partition key broker theo ticket ID và để consumer xử lý bản cũ/bản trùng theo version. Không dựa vào email Date header hoặc sequence number làm thứ tự nghiệp vụ tuyệt đối.

### Domain event không phải data dump

Một event có thể chứa ticketId, category và createdAt; nội dung nhạy cảm của email có thể nằm ở domain repository với quyền riêng. Chọn payload theo nhu cầu hợp lệ của consumers, không theo mọi thứ có sẵn từ MimeMessage.

## 25. Tránh vòng lặp tự động phản hồi

Hệ thống đọc hộp thư và gửi email tự động có thể vô tình trả lời **auto-reply** của hệ thống khác:

~~~text
System A nhận mail -> auto reply
System B nhận reply -> auto reply
System A nhận reply -> ...
~~~

Hậu quả là vòng lặp thư, tăng quota, spam và backlog xử lý.

### Tín hiệu tham khảo

- **Auto-Submitted** thường chỉ ra email tạo tự động.
- Một số thông báo bounce/DSN dùng multipart/report.
- Subject bắt đầu bằng “Automatic reply”, “Out of office” là tín hiệu yếu.
- Một số header do ESP/gateway bổ sung giúp nhận diện bounce/complaint.
- Envelope sender null (MAIL FROM:<>) có thể xuất hiện trong DSN; không phải từ From header.

Không có một header duy nhất an toàn cho mọi provider. Các trường này có thể bị spoof, cần kết hợp chính sách, đặc điểm provider và giới hạn rate.

### Không tạo ticket vô hạn từ DSN

Nếu hệ thống gửi phản hồi và mailbox nhận bounce của chính thư đó, không nên tự coi mỗi DSN như yêu cầu hỗ trợ mới, trừ khi use case thực sự là xử lý bounce. Các email tự động và thông báo lỗi nên được route sang **integration event hoặc workflow chuyên dụng**.

### Phân loại không xóa dữ liệu ngay

Khi phát hiện auto-reply, có thể đánh dấu status **IGNORED_AUTO_REPLY**, lưu source key và reason để tránh xử lý lặp. Không nhất thiết xóa thư khỏi hộp thư; retention/phân quyền phải tuân theo chính sách vận hành.

## 26. Không tin email để thực hiện hành động có quyền cao

Một email có Subject:

~~~text
Subject: APPROVE TRANSFER 1000000
From: ceo@example.test
~~~

không đủ cơ sở để phát **TransferApproved**. Email headers dễ bị giả mạo, nội dung có thể bị chỉnh sửa/forward và một mailbox hỗ trợ có thể nhận thư từ bất kỳ nơi nào.

### Ranh giới bảo mật

Các trường cần tách:

~~~text
Raw From address        -> user-supplied claim
Inbound mailbox ID      -> integration-configured source
Provider auth metadata  -> only trusted if verified at boundary
Customer identity       -> resolved by application
Business permission     -> checked against domain policy
Domain event            -> emitted after authorized mutation
~~~

Một số trường hợp có thể cần signed payload, portal authentication, one-time confirmation link hoặc yêu cầu người dùng đăng nhập để xác nhận. Không mặc định SPF/DKIM pass đồng nghĩa người gửi có quyền phê duyệt một hành động nghiệp vụ.

### Reply có chứa một ticket ID cũng không đủ

Nếu ai đó đoán được ticket ID và gửi email “Reply to TICKET-123”, không được cho họ đọc/sửa mọi ticket. Ngoài kiểm tra threading, phải xác minh sender đã được liên kết với ticket/tenant theo rule đáng tin.

### Giới hạn việc dùng email làm command bus

Những command ít rủi ro như “mở yêu cầu hỗ trợ” có thể chấp nhận inbound email sau validation. Những thao tác nhạy cảm như thay đổi quyền, chuyển tiền, reset MFA hoặc xuất dữ liệu nhạy cảm nên có một kênh xác nhận mạnh hơn. Điều đó ảnh hưởng trực tiếp đến loại domain event được phép phát sinh từ inbox.

## 27. Bảo vệ dữ liệu cá nhân trong event pipeline

Một email có thể chứa:

- Tên, số điện thoại, địa chỉ.
- Token đăng nhập/OTP.
- Hóa đơn, số tài khoản hoặc nội dung hợp đồng.
- Attachment có thông tin sức khỏe/nhân sự.
- Chữ ký email và chuỗi lịch sử trao đổi.

Nếu chuyển toàn bộ email thành một JSON event trên broker mà nhiều service có quyền subscribe, phạm vi tiếp xúc dữ liệu mở rộng đáng kể.

### Nguyên tắc thiết kế

1. **Data minimization:** event chỉ chứa fields mà consumer thực sự cần.
2. **Access control:** chỉ service được phép mới đọc payload/attachment.
3. **Encryption:** bảo vệ transport và dữ liệu lưu ở DB/object storage/broker phù hợp.
4. **Retention:** xác định thời gian lưu raw MIME, normalized candidate, event và logs riêng.
5. **Redaction:** không log credentials, token, body hoặc attachment bytes.
6. **Tenant isolation:** tenantId được xác định từ mailbox/ủy quyền nội bộ, không lấy trực tiếp từ header người gửi.
7. **Audit:** có thể tra cứu ai đã xử lý email và phát event nào bằng IDs nội bộ.
8. **Deletion lifecycle:** khi phải xóa PII theo chính sách, cần biết dữ liệu đã được copy sang những stores/consumers nào.

### Opaque sourceReference

Một domain event có thể mang:

~~~text
sourceReference = "inbound-mail:7f23..."
~~~

tham chiếu đến một bản ghi được phân quyền. Người tiêu thụ event không nên mặc nhiên có quyền truy cập raw mailbox credentials hoặc toàn bộ MIME chỉ vì họ biết reference.

### Logs là một phần của dữ liệu cần bảo vệ

Ghi:

~~~text
event=inbound_mail_processed
mailbox_id=support-1
source_key_hash=sha256:...
decision=PROCESSED
event_id=...
duration_ms=190
~~~

thường hữu ích hơn việc log đầy đủ From, Subject và 10.000 ký tự body. Nếu cần debug chi tiết, sử dụng nơi lưu an toàn theo quyền hạn và TTL, không bật raw protocol trace mặc định.

## 28. Chọn kênh đồng bộ và bất đồng bộ

Spring Integration cung cấp nhiều loại message channel. Lựa chọn channel tác động tới thread, transaction context, error handling và khả năng retry.

### DirectChannel

Một flow đồng bộ thường xử lý message trong thread caller/poller:

~~~text
IMAP poller thread
     |
     v
DirectChannel
     |
     v
Transformer -> Domain Handler
~~~

Ưu điểm là dễ quan sát exception và transaction boundary, ít crossing thread. Nhược điểm là parser/domain logic chậm có thể giữ poller bận và làm tăng độ trễ nhận thư. Nếu raw payload còn phụ thuộc folder đang mở, cần kiểm tra lifecycle của adapter trước khi dùng đồng bộ flow này.

### ExecutorChannel

Một flow bất đồng bộ có thể:

~~~text
IMAP poller
     |
     v
Snapshot/normalize + persist source data
     |
     v
ExecutorChannel
     |
     v
Business handler in another thread
~~~

ExecutorChannel tách thread nhưng **không tự biến message thành durable queue**. Nếu JVM crash, message chỉ tồn tại trong memory executor có thể mất. Nếu cần chắc chắn không bỏ sót giữa transport và xử lý, hãy lưu snapshot/processing record trước, hoặc dùng một queue/message store có bảo đảm phù hợp.

### QueueChannel và persistent MessageStore

Một QueueChannel in-memory giúp tách producer/consumer trong process nhưng chưa đủ durability. Spring Integration có các khả năng backed by MessageStore/JDBC tùy cấu hình. Tuy nhiên, cần đánh giá:

- Payload có serialize được không?
- Có đang giữ raw MimeMessage phụ thuộc Store/Folder không?
- Transaction/ack/retry và thứ tự xử lý là gì?
- MessageStore có thực sự bền vững và tương thích schema không?

Trong nhiều ứng dụng, một **inbound processing table + domain outbox** vẫn là thiết kế dễ kiểm soát hơn việc serialize thẳng MimeMessage vào persistent channel.

### Khi nào nên dùng IntegrationFlow để phát event?

IntegrationFlow phù hợp để orchestrate các bước. Nhưng nếu domain event cần được commit atomically với business data, bước quyết định nên là **domain application service** và lưu event outbox trong transaction, còn integration flow chỉ kích hoạt service/quan sát outcome. Không nên coi việc một Spring channel handler nhận được event là tương đương sự kiện đã được phát bền vững.

## 29. Quan sát toàn bộ chuỗi inbound mail đến domain event

Nếu dashboard chỉ hiển thị **IMAP connection healthy**, ứng dụng vẫn có thể không phát event vì MIME parser lỗi, database không hoạt động hoặc inbox chứa nhiều messages không được domain chấp nhận.

Nên tách các mốc:

~~~text
IMAP mail observed
     |
     v
Source key recorded
     |
     v
MIME normalized
     |
     v
Candidate classified
     |
     v
Domain state persisted
     |
     v
Event outbox committed
     |
     v
Event published / acked
     |
     v
Consumer processed
~~~

### Metrics gợi ý

| Metric | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **inbound_mail_poll_total** | Counter | Số lần poll theo kết quả |
| **inbound_mail_discovered_total** | Counter | Số source messages được phát hiện |
| **inbound_mail_normalized_total** | Counter | Thành công/thất bại khi parse |
| **inbound_mail_candidate_rejected_total** | Counter | Lý do từ chối kỹ thuật |
| **inbound_mail_domain_processed_total** | Counter | Số source messages đã xử lý theo outcome |
| **inbound_mail_duplicate_total** | Counter | Cùng source key đã được xử lý |
| **inbound_mail_pending_jobs** | Gauge | Số source records chờ nghiệp vụ |
| **inbound_mail_oldest_pending_age_seconds** | Gauge | Độ trễ của source record cũ nhất |
| **domain_event_outbox_pending** | Gauge | Event đã commit nhưng chưa publish |
| **domain_event_publish_total** | Counter | Attempts publish theo result |
| **domain_event_publish_duration_seconds** | Timer | Độ trễ publish |
| **inbound_mail_flag_sync_failures_total** | Counter | Không thể mark SEEN/move |
| **inbound_mail_uidvalidity_changes_total** | Counter | Mailbox epoch thay đổi |

Đây là các metric **do ứng dụng tự định nghĩa**, không phải metrics mặc định có sẵn từ Spring Integration Mail. Tên được export sang Prometheus có thể được chuẩn hóa và Counter có hậu tố **_total** theo registry.

### Labels có cardinality thấp

Nên dùng:

~~~text
purpose=support_reply|support_new|other
result=processed|duplicate|rejected|retry|review
reason=invalid_mime|too_large|unmatched_thread|...
source=imap|pop3|provider_webhook
~~~

Không gắn **email address**, Subject, UID, Message-ID, ticketId hoặc raw exception text vào metric labels; có thể gây nổ cardinality và lộ dữ liệu.

### Dùng tracing qua các ranh giới

~~~text
trace=inbound-mail-opaque-correlation
  span=mail.poll
  span=mail.source.identify
  span=mail.mime.normalize
  span=mail.domain.apply
  span=mail.outbox.commit
  span=mail.event.publish
~~~

Nếu một Spring message đi qua asynchronous boundary, cần propagate correlation/trace context một cách rõ ràng. Không đặt raw MIME vào tracing attributes.

### Dashboard phân biệt parse và publish lag

Ví dụ:

~~~text
Last successful IMAP poll:     2 sec ago
New source messages:          250 / hour
MIME parse failed:              3 / hour
Domain processed:             240 / hour
Pending inbound records:       18
Domain events not published:   120
Oldest event outbox age:       11 min
Flag sync failed:               4
~~~

Nếu inbound count vẫn tăng và domain event outbox pending cũng tăng, lỗi có thể ở **event publisher/broker**, không phải IMAP receiver. Nếu MIME parse failures tăng, tăng số workers publish không giải quyết nguyên nhân.

## 30. Unit test bộ mapping thuần túy

Các hàm mapping từ candidate sang dữ liệu nghiệp vụ nên **dễ kiểm thử không cần server mail**. Dùng input đã chuẩn hóa để kiểm tra rule:

- Subject thiếu/rỗng.
- Email body chỉ có HTML, không có text/plain.
- Sender không khớp customer.
- Mailbox tenant mismatch.
- Attachment vượt giới hạn.
- Thư tự động/DSN.
- Reply không có ticket mapping.
- Cùng source key đã được xử lý.

### Ví dụ classifier nhỏ

~~~java
public enum MailIntent {
    NEW_SUPPORT_REQUEST,
    SUPPORT_REPLY,
    AUTOMATED_MESSAGE,
    NEEDS_REVIEW
}

public record MailIntentDecision(
        MailIntent intent,
        String reason
) {
}

public final class SupportMailClassifier {

    public MailIntentDecision classify(
            InboundMailCandidate mail,
            boolean automaticMessage,
            boolean trustedReplyMappingExists
    ) {
        if (automaticMessage) {
            return new MailIntentDecision(
                    MailIntent.AUTOMATED_MESSAGE,
                    "AUTO_SUBMITTED"
            );
        }

        if (mail.subject() == null
                || mail.subject().isBlank()) {
            return new MailIntentDecision(
                    MailIntent.NEEDS_REVIEW,
                    "SUBJECT_MISSING"
            );
        }

        if (trustedReplyMappingExists) {
            return new MailIntentDecision(
                    MailIntent.SUPPORT_REPLY,
                    "KNOWN_THREAD"
            );
        }

        return new MailIntentDecision(
                MailIntent.NEW_SUPPORT_REQUEST,
                "NEW_REQUEST"
        );
    }
}
~~~

Đây là classifier minh họa, không phải thuật toán đầy đủ để phát hiện email tự động hoặc xác thực reply. Trong thực tế, hai boolean phải đến từ các bước kiểm tra có nghĩa; nhất là **trustedReplyMappingExists** không chỉ dựa vào header In-Reply-To có chuỗi trùng.

### Ví dụ JUnit

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;

class SupportMailClassifierTest {

    private final SupportMailClassifier classifier =
            new SupportMailClassifier();

    private InboundMailCandidate candidate(String subject) {
        return new InboundMailCandidate(
                new InboundMailSource(
                        "tenant-7", "mailbox-1", "INBOX", 42, 108
                ),
                "untrusted-message-id",
                "customer@example.test",
                List.of("support@example.test"),
                subject,
                "Mô tả vấn đề",
                null,
                List.of(),
                Instant.parse("2026-01-01T09:00:00Z"),
                Instant.parse("2026-01-01T09:01:00Z")
        );
    }

    @Test
    void rejectsEmptySubjectForReview() {
        MailIntentDecision decision = classifier.classify(
                candidate(""),
                false,
                false
        );
        assertEquals(MailIntent.NEEDS_REVIEW, decision.intent());
    }

    @Test
    void doesNotCreateTicketForAutoReply() {
        MailIntentDecision decision = classifier.classify(
                candidate("Automatic reply"),
                true,
                false
        );
        assertEquals(
                MailIntent.AUTOMATED_MESSAGE,
                decision.intent()
        );
    }

    @Test
    void knownAuthorizedThreadBecomesReply() {
        MailIntentDecision decision = classifier.classify(
                candidate("Re: Support request"),
                false,
                true
        );
        assertEquals(MailIntent.SUPPORT_REPLY, decision.intent());
    }
}
~~~

Unit tests này không kiểm chứng MIME decoding, IMAP flags hay transaction. Đó là lý do cần kiểm thử tích hợp thêm ở boundary.

## 31. Kiểm thử tích hợp bằng mailbox cô lập

Một integration test có thể chạy **GreenMail** (SMTP + IMAP) hoặc server IMAP thử nghiệm trong container:

~~~text
Test JVM
  |
  +-- JavaMailSender -> local SMTP fixture
  |                        |
  |                        v
  |                     Test INBOX
  |                        |
  '-- Spring Integration Mail inbound adapter
                           |
                           v
                    Candidate normalizer
                           |
                           v
                    Fake domain repository
                           |
                           v
                       Event outbox
~~~

### Các giả định fixture

- SMTP fixture nhận message vào mailbox test, **không relay ra Internet**.
- IMAP fixture cho phép đọc và có UID/flags nếu test cần.
- Username/password chỉ dành cho test, không dùng account thật.
- Port động để tránh xung đột giữa tests.
- Không cho các test chia sẻ mailbox state ngoài ý muốn.
- Có timeout cho SMTP/IMAP operations.
- Nếu kiểm thử TLS/auth, fixture phải thật sự enforce TLS/certificate/credentials, không chỉ bắt mail.

### Ví dụ gửi email thử nghiệm vào mailbox

~~~java
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

public static void seedMailbox(
        String smtpHost,
        int smtpPort
) throws Exception {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost(smtpHost);
    sender.setPort(smtpPort);

    var message = sender.createMimeMessage();
    var helper = new MimeMessageHelper(
            message, false, "UTF-8"
    );
    helper.setFrom("customer@example.test");
    helper.setTo("support@example.test");
    helper.setSubject("Không đăng nhập được");
    helper.setText("Tôi không thể đăng nhập.");

    sender.send(message);
}
~~~

Fixture phải cung cấp người nhận và SMTP routing tương ứng. Code trên chỉ tạo email thử nghiệm, **không tự chạy Spring Integration**; integration test tiếp theo sẽ khởi động flow nhận IMAP và assert processing.

### Test happy path

~~~text
Given:
  Fixture INBOX có một email hợp lệ
  Domain customer mapping cho phép mở ticket

When:
  Spring Integration poll/receive một message

Then:
  Candidate normalized đúng subject/body
  Source key được ghi nhận
  Một support ticket được commit
  Một SupportTicketOpened event được lưu
  Event có eventId/schemaVersion/ticketId đúng
~~~

### Test retry cùng source

~~~text
Given:
  UIDVALIDITY=42, UID=108 đã PROCESSED

When:
  Mail adapter nhận lại cùng source message

Then:
  Không tạo ticket mới
  Không tạo domain event mới
  Có thể retry flag sync nếu lần trước lỗi
~~~

### Test domain transaction rollback

~~~text
Given:
  Mail hợp lệ
  Ticket repository ném lỗi trước commit

When:
  Handler thực thi

Then:
  Ticket không được persist
  Event outbox không có SupportTicketOpened mới
  Processing record không báo PROCESSED
  Có thể retry theo policy
~~~

### Test broker unavailable

~~~text
Given:
  Business transaction đã commit ticket và event outbox
  Event broker tạm thời down

When:
  Publisher thử gửi event

Then:
  Event vẫn tồn tại trong outbox
  Không tạo ticket thứ hai
  Khi broker phục hồi publisher dùng cùng eventId
~~~

### Test Read/Seen behavior

Nếu hệ thống phải giữ thư UNSEEN cho tới khi business commit, cần mô phỏng:

1. Đọc body với receiver/fetch configuration thực.
2. Parse/validate.
3. Inject DB error.
4. Mở IMAP session mới và xác nhận flag SEEN theo policy.

Không dùng một mock **MimeMessage** rồi kết luận không có tác dụng phụ lên IMAP server.

## 32. Những trường hợp lỗi khó cần fault injection

### Worker crash sau khi ghi ticket nhưng trước khi publish event

Nếu ticket và outbox cùng transaction, publisher có thể tiếp tục sau restart. Nếu code chỉ gọi **ApplicationEventPublisher** sau save rồi chết giữa hai bước mà không có outbox, event có thể bị mất.

### Worker crash sau publish nhưng trước khi mark published

Broker có thể đã nhận event. Publisher retry dùng cùng eventId; consumer phải dedup. Không tạo một domain event mới chỉ để “gửi lại” vì sẽ làm mất tính idempotent.

### IMAP reconnect với UIDVALIDITY mới

Source checkpoint cũ có thể không hợp lệ. Test bảo đảm không đồng nhất UID cũ với UID mới và không xóa trạng thái các events đã phát trước.

### Hai replicas cùng poll một mailbox

Cả hai có thể nhận cùng source UID. Test concurrency với database unique key và atomic claim cho thấy chỉ một business mutation được commit, kể cả khi hai Spring messages được tạo.

### Read body khiến message tự chuyển SEEN

Test bằng IMAP fixture và receiver configuration đã chọn. Nếu cần giữ unread, không được cho phép bước MIME parse tự làm mail biến thành đã đọc trước khi business transaction thành công.

### External API timeout sau khi tạo ticket

Một external ticket API có thể đã tạo ticket nhưng response mất. Retry mà không có idempotency key sẽ tạo hai tickets. Test nên mô phỏng **server accepted / client timeout**, rồi xác nhận hệ thống giữ **UNKNOWN** và đối soát hoặc retry với khóa idempotency được provider bảo đảm.

### Message có multipart và attachment rất lớn

Một MIME tree hợp lệ nhưng có quá nhiều parts hoặc tệp lớn có thể làm worker hết memory. Test parser phải có giới hạn đầu vào/tài nguyên phù hợp với yêu cầu vận hành.

### Header spoof để truy cập ticket người khác

Người gửi đặt In-Reply-To trùng một ticket ID mà họ không có quyền. Domain phải từ chối hoặc chuyển review; không có event SupportReplyAdded.

### Email tự động liên tục

Fixture nạp các DSN/auto-replies vào INBOX. Hệ thống phải classify và giới hạn response; không tạo vòng lặp auto-reply.

## 33. Runbook khi email đã đến nhưng không có domain event

Khi người dùng báo “đã gửi email mà không có ticket”, không nên lập tức replay toàn bộ mailbox. Cần đi theo các mốc của pipeline để tìm giai đoạn bị dừng.

### Bước 1 — Xác minh nguồn email

- Đúng mailbox và folder được app theo dõi không?
- IMAP/POP3 credentials còn hợp lệ không?
- Kết nối TLS, hostname và port đúng không?
- Adapter có đang poll/IDLE và ghi nhận lần thành công gần nhất?
- Email đã bị move, expunge hoặc gắn SEEN trước khi adapter tìm chưa?
- Có nhiều replicas/consumers cùng kiểm soát mailbox không?

Không giả định thư gửi tới địa chỉ hiển thị trên To đều nằm trong INBOX được app cấu hình. Provider có routing, aliases và spam folders.

### Bước 2 — Kiểm tra discovery và source key

Tìm từ source identity:

~~~text
tenant
mailbox
folder
UIDVALIDITY
UID
~~~

Nếu không có record nguồn, lỗi có thể nằm ở inbound adapter/filter/UID checkpoint. Nếu đã có record **PROCESSED**, không replay mù; xem business record/event ID đã ghi.

### Bước 3 — Kiểm tra normalize và validation

- MIME parser có reject vì charset/content type không hỗ trợ không?
- Email body nằm ở multipart/alternative hay attachment được embed?
- Có vượt size/part/depth limit không?
- Có bị phân loại automated message, spam hoặc DSN không?
- Tenant/customer mapping có hợp lệ không?
- Có cần manual review do source chưa xác thực không?

Khi điều tra cần xem metadata và error category, tránh tự in toàn bộ raw MIME chứa PII vào logs.

### Bước 4 — Kiểm tra domain persistence

Có ticket/reply tương ứng không? Nếu service báo duplicate, đó có thể là hành vi đúng khi message đã xử lý trước đó. Nếu lỗi DB, cần biết transaction đã commit hay rollback.

Nếu external ticket API timeout, có thể side effect đã xảy ra; dùng idempotency key hoặc reconciliation trước khi thử lại.

### Bước 5 — Kiểm tra event outbox

~~~text
Business state committed?
         |
         +-- No  -> Review domain processing
         |
         '-- Yes
              |
              v
       Event outbox exists?
             |           |
             No          Yes
             |           |
             v           v
         Transaction/   Published?
         persistence       |           |
         design issue      No          Yes
                          |           |
                          v           v
                     Publisher/      Consumer
                     broker issue    processing
~~~

Nếu event outbox đã có record nhưng chưa publish, lỗi không còn ở IMAP hoặc parser. Sửa publisher/broker, không chạy lại domain service.

### Bước 6 — Khôi phục an toàn

- **IMAP fetch lỗi:** poll lại bằng source checkpoint/UID.
- **MIME lỗi cố định:** quarantine/review, không retry vô hạn.
- **DB transaction rollback:** retry processing idempotently.
- **Business side effect UNKNOWN:** đối soát, không tạo lại vô điều kiện.
- **Event outbox pending:** retry publish cùng event ID.
- **Flag sync failed:** chỉ retry set SEEN/move, không tạo lại ticket.

### Bước 7 — Xác nhận phục hồi

Sau xử lý sự cố, cần thấy:

1. Source UID được ghi nhận một lần ở bảng identity.
2. Business mutation phù hợp được commit.
3. Event outbox có event ID đúng.
4. Broker/consumer nhận event theo hợp đồng.
5. Không có event/ticket trùng.
6. Cờ mailbox được đồng bộ đúng policy.
7. Lỗi trong mailbox khác không bị ảnh hưởng.

## 34. Những lỗi thiết kế thường gặp

### Lỗi 1 — Coi mọi email được đọc là domain event

Một email auto-reply, spam hoặc message chưa xác thực có thể không mang sự kiện nghiệp vụ hợp lệ. Chỉ phát domain event sau validation và domain mutation.

### Lỗi 2 — Trộn Jakarta Mail Message và Spring Message

Hai class trùng tên nhưng khác tầng. Một là MIME/mailbox object, một là envelope dùng giữa Spring Integration components. Nên định nghĩa hợp đồng payload và import rõ.

### Lỗi 3 — Cast mọi payload thành MimeMessage

Receiver có thể trả payload đã được simplify/transform hoặc nhiều messages theo cấu hình. Kiểm tra payload contract ở boundary thay vì cast trong domain service.

### Lỗi 4 — Dùng From làm user ID đáng tin

From có thể bị spoof. Sử dụng customer identity resolution, permission checks và trusted authentication evidence phù hợp.

### Lỗi 5 — Dùng Message-ID làm unique key duy nhất

Header do sender đặt có thể thiếu/trùng; dùng source identity phù hợp như mailbox + folder + UIDVALIDITY + UID, và record idempotency riêng.

### Lỗi 6 — Lấy UID sau khi folder đã đóng

MimeMessage downstream có thể không còn context IMAP. Trích UID/source metadata trong receiver boundary khi dữ liệu còn sẵn, rồi lưu/enrich trước asynchronous handoff.

### Lỗi 7 — Mark SEEN ngay khi adapter nhận

Business handler có thể lỗi, poll lần sau không thấy UNSEEN. Tách trạng thái đọc và trạng thái xử lý, dùng UID/dedup và đồng bộ flags sau commit.

### Lỗi 8 — Coi SEEN là lock

Hai consumers có thể cùng thấy UNSEEN. Dùng atomic DB claim và unique constraint; không dựa vào SEEN chống trùng.

### Lỗi 9 — Publish event trước business commit

Consumer có thể thấy event trong khi ticket chưa tồn tại hoặc transaction rollback. Ghi domain event vào outbox cùng transaction và publish sau commit.

### Lỗi 10 — Chỉ dùng @TransactionalEventListener để bảo đảm delivery

Một callback AFTER_COMMIT giúp trì hoãn handler tới sau transaction, nhưng nếu JVM chết ngay sau commit hoặc broker không nhận, event có thể mất nếu chưa được lưu bền vững. Dùng transactional outbox khi cần độ tin cậy qua crash.

### Lỗi 11 — Sinh event ID mới khi publisher retry

Consumer khó dedup cùng sự kiện. Event ID phải được lưu một lần trong outbox, publisher dùng lại.

### Lỗi 12 — Retry toàn bộ flow khi flag-sync lỗi

Ticket đã commit nhưng set SEEN fail; retry toàn flow có thể tạo ticket trùng. Retry riêng bước sync flags.

### Lỗi 13 — Deserialize raw MIME vào event bus

Payload lớn, chứa dữ liệu nhạy cảm và phụ thuộc protocol implementation. Chuyển sang domain facts tối thiểu và attachment references.

### Lỗi 14 — Dựa vào Content-Type hay filename để tin attachment

Sender có thể giả metadata. Kiểm chứng bytes, scan, giới hạn size và dùng storage key do server tạo.

### Lỗi 15 — Xử lý HTML như nội dung an toàn

Email HTML có thể chứa markup độc hại, remote tracking và link giả. Sanitization/escaping và xử lý content policy là bắt buộc khi hiển thị.

### Lỗi 16 — Dùng một ExecutorChannel in-memory như durable queue

Khi process crash, messages chưa xử lý có thể mất. Lưu source snapshot/processing state hoặc dùng persistent store thật trước khi chuyển asynchronous.

### Lỗi 17 — Nhầm broker ACK với business success

Event được broker accepted không tự chứng minh downstream consumer đã xử lý. Cần monitor consumers, idempotency và error/DLQ policy riêng.

### Lỗi 18 — Không xử lý UIDVALIDITY đổi

UID cũ có thể chỉ message khác sau mailbox reset. So sánh UIDVALIDITY và resynchronize, không bỏ qua epoch.

### Lỗi 19 — Dùng email Date làm occurredAt của domain event

Date header có thể sai hoặc bị giả. Event occurredAt nên phản ánh thời điểm domain action thực sự được commit/ghi nhận theo đồng hồ tin cậy của hệ thống.

### Lỗi 20 — Auto-reply cho mọi email

DSN và auto-responses có thể kích hoạt vòng lặp. Phân loại Auto-Submitted, bounce, rate limit và quản lý phản hồi tự động theo policy.

### Lỗi 21 — Dùng raw In-Reply-To để truy cập ticket

Header threading không thay thế authorization. Cần mapping message cha và kiểm tra quyền tenant/customer.

### Lỗi 22 — Log hết raw MIME khi exception

MIME có thể chứa OTP, reset token, PII, attachment. Log reason code/correlation IDs; dữ liệu chi tiết lưu ở nơi có kiểm soát.

### Lỗi 23 — Không phân biệt permanent failure với transient

MIME malformed bị retry vô hạn hoặc network timeout bị bỏ vĩnh viễn. Phân loại đúng và có quarantine/review.

### Lỗi 24 — Xóa email khỏi mailbox như một ACK mặc định

Một lần xóa/expunge có thể làm mất dữ liệu chưa xử lý và ảnh hưởng shared mailbox. Chỉ dùng destructive operations nếu có policy, retention và khả năng phục hồi phù hợp.

### Lỗi 25 — Đếm email nhận thay cho domain event

Không phải mọi email tạo ticket/event. Dashboard phải tách discovered, normalized, rejected, processed, outbox published và consumer handled.

## 35. Tình huống luyện tập

### Tình huống A — Một email tạo hai ticket

Hai pods poll cùng IMAP INBOX, đều nhận UID 108.

**Hỏi:** dùng SEEN để tránh trùng có đủ không?

**Đáp:** không. Cần source key theo UID/UIDVALIDITY và atomic claim/unique constraint ở database. Domain operation cũng phải idempotent khi có external side effect.

### Tình huống B — MIME parser chạy thành công nhưng ticket không tồn tại

Parser đã trả InboundMailCandidate, nhưng customer resolver xác định người gửi không có quyền.

**Hỏi:** có nên phát SupportTicketOpened?

**Đáp:** không. Candidate chỉ là dữ liệu kỹ thuật; domain event cần một thay đổi nghiệp vụ hợp lệ đã được lưu.

### Tình huống C — Email có Subject “APPROVE INVOICE”

From hiển thị là quản lý, nhưng chưa có xác minh sender/permission.

**Hỏi:** tạo InvoiceApproved event?

**Đáp:** không. Không dùng raw From/Subject làm ủy quyền. Chuyển sang workflow xác nhận an toàn hơn.

### Tình huống D — Publisher gặp broker outage

Ticket đã commit và SupportTicketOpened nằm trong event outbox.

**Hỏi:** có cần poll lại email để phát event?

**Đáp:** không. Retry publisher trên outbox record cùng event ID. Không tạo ticket lần nữa.

### Tình huống E — IMAP flag SEEN không cập nhật

Ticket đã tạo, message vẫn UNSEEN do network error.

**Hỏi:** lần poll tới có phải tạo event mới?

**Đáp:** không. Source key đã PROCESSED; chỉ retry flag-sync nếu policy muốn mark read.

### Tình huống F — Subject tiếng Việt bị mã hóa

Raw header chứa MIME encoded-words thay vì văn bản dễ đọc.

**Hỏi:** nên copy raw header nguyên vào domain event?

**Đáp:** nên dùng Jakarta Mail API/decoder phù hợp để chuẩn hóa chuỗi, giới hạn độ dài và xử lý malformed encoding. Không log raw body/headers nhạy cảm.

### Tình huống G — Attachment 30 MiB

Event broker chỉ cho payload vài MiB, người gửi đính kèm file rất lớn.

**Hỏi:** nên Base64 file vào event?

**Đáp:** không. Kiểm tra/scan rồi lưu storage phù hợp, event chứa reference ID có kiểm soát, hoặc reject theo policy.

### Tình huống H — UIDVALIDITY đổi

Mailbox được restore; UID 108 trong epoch mới không phải message cũ.

**Hỏi:** source key nên thay đổi không?

**Đáp:** có, vì UIDVALIDITY là một phần định danh. Cần rescan/reconciliation thay vì lấy UID cũ trực tiếp.

### Tình huống I — ExecutorChannel bị mất khi JVM crash

Adapter đã đẩy MimeMessage vào executor in-memory, process chết.

**Hỏi:** có thể bảo đảm email vẫn sẽ tạo ticket không?

**Đáp:** không chỉ nhờ ExecutorChannel. Cần lưu source/snapshot bền vững hoặc bảo đảm rescan và dedup; raw MimeMessage có thể phụ thuộc connection đã đóng.

### Tình huống J — Email auto-reply

Một người gửi nhận phản hồi tự động từ hệ thống; mailbox tiếp tục nhận “Out of office”.

**Hỏi:** nên tự mở ticket và trả lời nữa không?

**Đáp:** tùy policy, thường nên classify auto-reply/DSN và ngăn reply loop; không phát event SupportTicketOpened vô điều kiện.

### Tình huống K — Body chỉ có HTML

Parser chỉ nhận text/plain và trả body rỗng.

**Hỏi:** có phải email không có nội dung?

**Đáp:** chưa chắc. Cần hỗ trợ multipart/HTML theo policy, trích xuất text an toàn hoặc đưa manual review nếu không thể xử lý.

### Tình huống L — Có cùng Message-ID ở hai messages

Hai thư gửi vào một mailbox dùng cùng header Message-ID.

**Hỏi:** có nên bỏ qua thư thứ hai là duplicate?

**Đáp:** không dựa vào Message-ID duy nhất. Dùng mailbox source key và business dedup rule phù hợp.

### Tình huống M — Email reply tới ticket của tenant khác

In-Reply-To trùng một message đã gửi ra nhưng sender/tenant không khớp.

**Hỏi:** có tạo SupportReplyAdded không?

**Đáp:** không nếu authorization fail. Header threading là gợi ý, không phải quyền sửa aggregate.

### Tình huống N — Một domain event được broker gửi hai lần

Publisher đã nhận timeout sau lần gửi đầu, retry cùng record.

**Hỏi:** consumer nên làm gì?

**Đáp:** dedup theo stable eventId/aggregate version, không thực hiện side effect lần hai nếu đã xử lý.

### Tình huống O — Sự kiện cần được phát trước khi commit?

Một developer gọi publisher.publishEvent ngay trong transformer để phản hồi nhanh.

**Hỏi:** rủi ro?

**Đáp:** event có thể được publish dù domain transaction chưa commit hoặc rollback, đồng thời transformer bị retry có thể phát lặp. Nên ghi event outbox trong transaction, publisher gửi sau commit.

### Tình huống P — Lỗi setFlag làm HTTP phản hồi lỗi

Ứng dụng đã tạo ticket thành công nhưng không mark SEEN được.

**Hỏi:** user có nên thấy “tạo ticket thất bại” không?

**Đáp:** không nhất thiết. Business success và mailbox flag-sync là hai outcome khác nhau. Có thể báo ticket đã tạo và ghi một job flag-sync cần retry.

### Tình huống Q — Một support email chứa đường dẫn reset password

Body có thể chứa token một lần.

**Hỏi:** event có nên chứa nguyên nội dung?

**Đáp:** chỉ nếu thực sự cần và được phép; thông thường event mang ticketId/source reference, nội dung nhạy cảm được lưu ở domain storage có quyền và retention riêng.

### Tình huống R — Domain event không có version

Consumer cũ lỗi khi producer thêm trường bắt buộc mới.

**Hỏi:** nên tổ chức như thế nào?

**Đáp:** có schemaVersion/schema registry/hợp đồng tương thích phù hợp, phát triển schema theo quy tắc, test consumer contracts trước release.

## 36. Quy trình triển khai từ inbox đến domain event

Một kế hoạch triển khai có thể đi theo các giai đoạn rõ ràng:

~~~text
XÁC ĐỊNH NGHIỆP VỤ
      |
      +-- Loại email nào tạo hành động?
      +-- Điều kiện domain nào phải đúng?
      +-- Source sender nào đủ tin cậy?
      '-- Event nào đại diện sự việc đã xảy ra?
      |
      v
THIẾT KẾ NHẬN THƯ
      |
      +-- IMAP/IMAPS hoặc provider webhook?
      +-- Mailbox/account/folder mapping?
      +-- TLS/auth và secret management?
      +-- Polling / IMAP IDLE / backoff?
      '-- Payload contract của Spring Integration?
      |
      v
CHUẨN HÓA MIME
      |
      +-- Header/text/HTML/attachment parser
      +-- Size/parts/depth/charset limits
      +-- Source identity UID + UIDVALIDITY
      +-- Security/privacy controls
      '-- InboundMailCandidate
      |
      v
VALIDATE + CLASSIFY
      |
      +-- Tenant/mailbox authorization
      +-- Sender trust/identity resolution
      +-- Anti-loop / auto-reply detection
      +-- Ticket/order threading
      '-- Domain invariants
      |
      v
DURABLE PROCESSING
      |
      +-- Atomic dedup/claim source
      +-- Transactional domain mutation
      +-- Mark inbound PROCESSED
      '-- Save domain event into outbox
      |
      v
EVENT DISPATCH
      |
      +-- Publish stable eventId
      +-- Retry with backoff
      +-- Consumer idempotency
      '-- DLQ/reconciliation if necessary
      |
      v
MAILBOX STATE SYNCHRONIZATION
      |
      +-- Optional mark SEEN
      +-- Optional move/label
      '-- Retry flag-sync separately
      |
      v
OBSERVABILITY + TESTING
      |
      +-- Source discovery and lag
      +-- MIME/domain error categories
      +-- Event outbox health
      +-- Duplicate prevention
      '-- Fault injection and incident runbook
~~~

### Một cấu trúc packages hợp lý

~~~text
com.example.inboundmail
  |
  +-- adapter
  |     +-- ImapInboundFlowConfiguration
  |     +-- MailSourceIdentityExtractor
  |     '-- MailReceiverHandler
  |
  +-- parsing
  |     +-- MimeNormalizer
  |     +-- SafeAttachmentExtractor
  |     '-- InboundMailCandidate
  |
  +-- application
  |     +-- InboundMailProcessingService
  |     +-- MailIntentClassifier
  |     +-- SenderAuthorizationPolicy
  |     '-- InboundProcessingRepository
  |
  +-- domain
  |     +-- SupportTicket
  |     +-- SupportTicketOpened
  |     '-- SupportReplyAdded
  |
  +-- persistence
  |     +-- ProcessedMailEntity
  |     +-- DomainEventOutboxEntity
  |     '-- AttachmentStorageAdapter
  |
  +-- publishing
  |     +-- OutboxPublisher
  |     '-- EventSerializer
  |
  '-- operations
        +-- MailMetrics
        +-- MailErrorClassifier
        '-- MailboxFlagSyncWorker
~~~

Đây là phân chia minh họa, không bắt buộc mỗi lớp phải có package riêng. Điểm quan trọng là **domain** không cần import Jakarta Mail hay Spring Integration APIs, để model nghiệp vụ vẫn rõ nghĩa và có thể nhận sự kiện từ kênh khác.

### Tách đường “nhận và ghi” khỏi “xử lý và phát”

Một mô hình có thể lưu **InboundMailSnapshot** ngay sau khi nhận MIME, sau đó background worker đọc snapshot để xử lý. Ưu điểm là giảm phụ thuộc vào IMAP connection và dễ retry; nhược điểm là cần bảo vệ raw email data trong storage và xác định retention. Nếu chỉ có workload nhỏ và business handler nhanh, có thể bắt đầu bằng flow đồng bộ nhưng vẫn cần idempotency và event outbox ở ranh giới domain.

### Không làm việc bất đồng bộ trước khi có dữ liệu bền vững

Nếu worker nhận MimeMessage rồi đẩy vào một in-memory queue, process crash có thể mất việc. Khi cần bảo đảm không bỏ sót, lưu source identity/snapshot hoặc có khả năng **re-discovery theo IMAP UID** với flags không bị thay đổi sai. Đừng để receiver tự xóa message trước khi việc lưu bền vững hoàn tất.

## 37. Checklist triển khai và kiểm thử

### Inbound transport

- **Protocol:** đã xác định IMAP/POP3/webhook và sự khác biệt về flags/UID?
- **Connection:** TLS/hostname verification, timeout, credentials/OAuth an toàn?
- **Mailbox:** đúng tenant, account, folder; xử lý rename/reset/UIDVALIDITY?
- **Receiver:** có biết payload shape, auto-SEEN và auto-delete behavior?
- **Lifecycle:** có trích source identity trước khi folder/connection đóng?
- **Concurrency:** nhiều pollers/workers có atomic dedup/claim?

### MIME và security

- **Parser:** hỗ trợ plain/HTML/multipart theo use case?
- **Limits:** có giới hạn raw bytes, MIME depth, số parts, attachment size và processing time?
- **Charsets:** xử lý Unicode và malformed input có kiểm soát?
- **Attachments:** scan, content type validation, server-generated storage keys?
- **HTML:** không render nội dung chưa được sanitize?
- **Trust:** không dùng From/Subject/Message-ID như quyền người gửi?
- **Auto-reply:** có tránh DSN/auto-response loops?
- **Privacy:** không log raw body, OTP, password, access token hoặc attachments?

### Domain mapping

- **Boundary:** đã tách MimeMessage, Spring Message và domain event?
- **Candidate:** đã chuẩn hóa raw sender, tenant/mailbox identity, timestamps và source key?
- **Classification:** mỗi loại email có quyết định accepted/rejected/review rõ?
- **Authorization:** người gửi và ticket/order relationship được kiểm tra?
- **Domain event:** tên mô tả một việc đã xảy ra, không phải mệnh lệnh?
- **Schema:** có eventId ổn định, schemaVersion, aggregateId, correlation?
- **Payload:** chỉ chứa dữ liệu cần thiết, không copy raw MIME mù quáng?

### Durability và recovery

- **Source key:** tenant + mailbox + folder + UIDVALIDITY + UID được định nghĩa rõ?
- **Claim:** unique constraint/lease/version chống xử lý đồng thời?
- **Commit:** domain mutation, processed record và event outbox cùng transaction khi phù hợp?
- **Publish:** broker outage không làm mất domain event đã commit?
- **Consumer:** có dedup theo eventId và handling redelivery?
- **Retry:** phân biệt parse transient, permanent, UNKNOWN business outcome?
- **SEEN:** optional flag-sync sau commit, retry riêng khi fail?
- **Recovery:** có runbook nếu UIDVALIDITY đổi hoặc source message bị expunge?

### Tests và vận hành

- **Unit tests:** normalization, classification, unauthorized reply, auto-responses?
- **Integration tests:** SMTP/IMAP fixture, UID persistence và receiver flags?
- **Failure injection:** crash giữa commit/publish, broker unavailable, duplicate polls?
- **Monitoring:** có metric về poll, normalize, domain processed, outbox pending, flag sync?
- **Alert:** phát hiện event publish lag, mailbox connection failures và pending backlog?
- **Data governance:** raw email retention, quyền truy cập storage và audit rõ?

Checklist này là hướng dẫn triển khai. Một hệ thống đơn giản có thể không cần mọi thành phần, nhưng **rủi ro về identity, idempotency, event consistency và dữ liệu nhạy cảm** cần được thiết kế rõ thay vì để mặc định từ mail adapter.

## 38. Tóm tắt nguyên tắc cốt lõi

~~~text
jakarta.mail.Message
    = dữ liệu email/MIME từ mailbox

org.springframework.messaging.Message<?>
    = thông điệp đi qua Spring Integration channels

InboundMailCandidate
    = email đã chuẩn hóa nhưng chưa được domain chấp nhận

Domain event
    = sự thật nghiệp vụ sau validation và mutation thành công

From / Subject / Message-ID
    != bằng chứng authorization

IMAP UID + UIDVALIDITY + folder + mailbox
    = source identity tốt hơn message number

SEEN
    != PROCESSED
    != một lock
    != event published

Transformer
    -> normalize data, không tự gây side effect domain

Application Service
    -> validate + apply invariants + persist business state

Transactional Outbox
    -> giữ domain event bền vững cùng commit nghiệp vụ

Event ID ổn định
    -> hỗ trợ retry publish và consumer dedup

Attachment reference
    -> tốt hơn nhúng raw MIME/bytes vào event

UNKNOWN external outcome
    -> đối soát, không retry mù

Flag-sync failure
    -> retry cờ đọc riêng, không tạo lại ticket
~~~

**Chuyển đổi mail message thành domain event** trong Spring Integration Mail không đơn thuần là lấy Subject/Body từ MimeMessage rồi phát một Java object lên message channel. Đó là một ranh giới quan trọng từ **dữ liệu email bên ngoài, có thể bị giả mạo và lặp lại** sang **sự kiện nghiệp vụ được hệ thống xác nhận**. Spring Integration giúp nhận thư và tổ chức pipeline; Jakarta Mail giúp truy cập MIME/Store/Folder; còn ứng dụng phải chịu trách nhiệm về định danh nguồn, chuẩn hóa nội dung, kiểm tra quyền, chống trùng, transaction và phát hành bền vững. Khi tách rõ **mail transport**, **integration candidate** và **domain fact**, dùng source key phù hợp, transactional outbox và đồng bộ IMAP flags độc lập, hệ thống có thể mở ticket hoặc ghi nhận phản hồi từ email mà không đánh mất event, không tạo tác động trùng và không biến nội dung email chưa được tin cậy thành quyền nghiệp vụ.
