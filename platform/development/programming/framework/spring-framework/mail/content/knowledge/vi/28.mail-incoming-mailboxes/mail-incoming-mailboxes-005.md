# Inbound channel adapter và polling

Trong Spring Framework Mail, phần lớn chương trình bắt đầu từ việc **gửi thư** qua `JavaMailSender` và SMTP. Nhưng một hệ thống quản lý ticket, hóa đơn, phản hồi khách hàng hoặc tích hợp đối tác có thể cần **nhận thư** từ một mailbox: kiểm tra hộp thư định kỳ, đọc email mới, chuyển nội dung thành một tác vụ nghiệp vụ, lưu attachment và cập nhật trạng thái.

Để triển khai bài toán này theo phong cách Spring, có thể dùng **Spring Integration Mail** với một **inbound channel adapter** và **poller**. Mail receiver kết nối IMAP hoặc POP3; `MailReceivingMessageSource` cung cấp dữ liệu cho integration flow; poller định kỳ gọi nguồn nhận; channel chuyển message tới handler. Nhờ đó, phần đọc mailbox được tách khỏi phần xử lý ticket, lưu file hay phản hồi nghiệp vụ.

~~~mermaid
flowchart LR
    A["IMAP/POP3 mailbox"] --> B["Mail receiver"]
    C["Poller"] --> D["MailReceivingMessageSource"]
    B --> D
    D --> E["Inbound channel adapter"]
    E --> F["Message channel"]
    F --> G["Ingestion handler"]
    G --> H["Database / job queue"]
~~~

Tuy nhiên, cấu hình poller chạy mỗi 30 giây **không bảo đảm** email chỉ được nhận đúng một lần, không bị mất khi server lỗi, hoặc attachment luôn an toàn. Một hệ thống inbound mail cần chủ động quản lý **UID, UIDVALIDITY, cờ đã đọc, idempotency, acknowledgment, MIME parsing, retry và backpressure**.

Bài học này giải thích mô hình inbound channel adapter, cấu hình Java DSL, so sánh polling với IMAP IDLE, nhận dạng thư mới, lỗi thường gặp và kiến trúc vận hành, cùng các ví dụ JUnit/integration test phù hợp với Spring Integration Mail.

## 1. Nhận thư và gửi thư là hai luồng khác nhau

| Khía cạnh | Gửi thư | Nhận thư |
| --- | --- | --- |
| Thành phần tiêu biểu | `JavaMailSender` | Spring Integration Mail receiver |
| Giao thức | SMTP | IMAP/IMAPS, POP3/POP3S |
| Nguồn kích hoạt | Business event, API, outbox | Poller hoặc thông báo IMAP IDLE |
| Hành động | Đưa MIME message lên SMTP relay | Tìm thư, lấy metadata và nội dung |
| Kết quả ban đầu | Relay nhận hoặc từ chối submission | Một message đi vào integration flow |
| Trạng thái cần quản lý | Retry gửi, submission outcome | Mailbox UID, processing state, acknowledgment |
| Nguy cơ | Gửi trùng, quota, throttling | Nhận trùng, bỏ sót, parse thư không an toàn |

`JavaMailSender` không có chức năng polling inbox. Một receiver IMAP không biến email nhận được thành SMTP send. Nếu ứng dụng có cả inbound và outbound, nên thiết kế riêng credential, endpoint, queue và business policy cho hai chiều.

Đặc biệt, **đã tải email từ mailbox** không đồng nghĩa **đã xử lý xong yêu cầu trong email**. Các bước đọc, lưu bền vững, xử lý nghiệp vụ và đánh dấu trên mail server có thể thất bại độc lập.

## 2. Inbound channel adapter là gì?

Trong Spring Integration, inbound channel adapter là endpoint đưa dữ liệu từ hệ thống ngoài vào một `MessageChannel`. Phần nhận thư có các thành phần:

- **Mail receiver:** đọc thư từ mailbox qua một giao thức phù hợp.
- **Message source:** một đối tượng có thể được gọi để lấy message, ví dụ `MailReceivingMessageSource`.
- **Poller:** lịch gọi source định kỳ.
- **Integration channel:** chuyển tiếp message đã nhận.
- **Service activator/handler:** xử lý payload, lưu dữ liệu hoặc tạo job.
- **Error handling:** ghi nhận và điều phối lỗi từ source/handler.

Ví dụ một lần poll:

~~~text
Poller kích hoạt
  -> MailReceivingMessageSource.receive()
  -> ImapMailReceiver tìm thư hợp lệ
  -> Thư được chuyển thành integration Message
  -> Channel phân phối tới MailIntakeService
  -> Intake persist metadata + file
  -> Tạo business job
~~~

**Inbound channel adapter thường là một chiều.** Nó không tự tạo thư phản hồi hoặc yêu cầu một response SMTP. Nếu nghiệp vụ cần gửi acknowledgment email, đó là một use case riêng dùng outbound gateway/sender sau khi request đã được xác thực và xử lý.

## 3. Spring Integration Mail và dependency

Với Gradle trong ứng dụng Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Nếu cùng ứng dụng cần gửi email:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Spring Integration Mail và outbound mail starter có trách nhiệm khác nhau. Hãy dùng dependency versions tương thích theo Spring Boot BOM/management. Trong hệ Spring Framework hiện đại, Jakarta Mail dùng namespace `jakarta.mail`; việc trộn tùy tiện các phiên bản cũ `javax.mail` và mới `jakarta.mail` có thể gây lỗi classpath.

Không phải một ứng dụng chỉ nhận email cũng phải dùng `JavaMailSender`. Nó chỉ cần outbound sender nếu workflow thực sự gửi phản hồi hoặc thông báo.

## 4. IMAP và POP3 khác nhau ở đâu?

| Tiêu chí | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Folder | Hỗ trợ nhiều folder | Thường tiếp cận hộp thư theo mô hình đơn giản |
| Flags | Có `\Seen`, `\Deleted` và flags khác | Không có hệ flags IMAP tương tự |
| UID | UID gắn với folder và UIDVALIDITY | UIDL theo semantics POP3 server |
| Tìm kiếm trên server | Có IMAP SEARCH | Hạn chế hơn |
| Đánh dấu đã đọc | Có IMAP flags | Không tương đương trực tiếp |
| Xóa thư | Flags/expunge tùy lệnh | Deletion semantics theo POP3 |
| IMAP IDLE | Có thể được hỗ trợ | Không hỗ trợ IMAP IDLE |

**IMAPS** là IMAP được bảo vệ bằng TLS trực tiếp, thường dùng cổng 993. **POP3S** tương tự cho POP3, thường dùng cổng 995. Giao thức và cổng cụ thể phải theo provider.

Với workflow cần lưu thư, đánh dấu, archive và theo dõi trạng thái nhiều worker, IMAP thường thuận tiện. POP3 có thể đủ cho luồng tải thư đơn giản khi provider hỗ trợ. Không tự giả định IMAP IDLE, OAuth2 hay mọi IMAP extension đều có ở tất cả server.

## 5. Polling chính xác là gì?

Polling nghĩa là ứng dụng định kỳ hỏi mailbox có thư nào phù hợp với search criteria không.

~~~text
00:00  poll -> thư A
00:30  poll -> chưa có thư
01:00  poll -> thư B, C
01:30  poll -> chưa có thư
02:00  poll -> thư D
~~~

Mỗi lần poll **không phải** một email mới. Một lần poll có thể trả 0, 1 hoặc nhiều thư tùy source, batch và cấu hình.

Có hai câu hỏi độc lập:

1. **Khi nào chạy?** Do poller quyết định.
2. **Nhận thư nào?** Do mail receiver, search strategy và trạng thái mailbox quyết định.

Nếu poller chạy đúng lịch nhưng receiver chỉ tìm thư chưa đọc, email đã bị một người dùng khác mở có thể không được thấy. Nếu receiver không đánh dấu thư và không có idempotency, cùng một email có thể lặp lại ở mỗi poll.

## 6. Fixed delay, fixed rate và độ trễ xử lý

**Fixed delay:** một lần poll mới được lên lịch sau một khoảng chờ tính từ lúc lần trước hoàn tất.

**Fixed rate:** nhắm tới nhịp thời gian tính theo thời điểm bắt đầu, tùy scheduler và cách xử lý tác vụ kéo dài.

Ví dụ:

~~~text
Fixed delay: 30 giây
  poll #1 bắt đầu t=0, kết thúc t=8
  poll #2 bắt đầu khoảng t=38

Fixed rate: 30 giây
  mục tiêu bắt đầu gần t=0, t=30, t=60...
~~~

Không suy ra mọi cấu hình fixed rate sẽ có nhiều thread chạy chồng nhau; việc chạy song song còn tùy scheduler/task executor.

Với mailbox nhận attachment lớn và handler nặng, fixed delay thường dễ dự đoán. Tuy nhiên, nếu cần SLA rất thấp, nên tách intake khỏi business processor thay vì chỉ giảm poll interval đến mức quá nhỏ.

## 7. Cấu hình Spring Boot cho inbound

`spring.mail.*` thông thường mô tả outbound SMTP. Đối với inbound, ứng dụng có thể tạo namespace riêng:

~~~yaml
app:
  mail:
    inbound:
      enabled: true
      protocol: imaps
      host: ${MAILBOX_IMAP_HOST}
      port: 993
      username: ${MAILBOX_IMAP_USER}
      folder: INBOX
      poll-delay: 30s
      max-messages-per-poll: 10
      delete-after-ingest: false
~~~

Đây là **custom configuration**, không phải mặc định Spring Boot tự hiểu toàn bộ. Phải bind bằng `@ConfigurationProperties` hoặc cách cấu hình tương ứng.

Credential thực nên đặt trong secret manager hoặc một nguồn cấu hình được bảo vệ. Không hardcode password/app token, không đưa password vào log và không in đầy đủ mail URL.

### Tách SMTP host khỏi IMAP host

Ví dụ cùng một provider có hai endpoint:

~~~text
SMTP submission: smtp.provider.example:587
IMAPS inbox:     imap.provider.example:993
~~~

Chúng có giao thức và quyền truy cập khác nhau. SMTP account gửi thư không mặc định cũng có quyền mở IMAP folder.

## 8. Java DSL với ImapMailReceiver

Ví dụ cấu hình thành phần chính trong Spring Integration Mail:

~~~java
import java.time.Duration;
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class InboundMailConfiguration {

    @Bean
    ImapMailReceiver imapReceiver(
            @Value("${app.mail.inbound.url}")
            String mailUrl) {

        ImapMailReceiver receiver =
                new ImapMailReceiver(mailUrl);

        receiver.setShouldDeleteMessages(false);
        receiver.setShouldMarkMessagesAsRead(false);

        Properties props = new Properties();

        props.put(
                "mail.imaps.connectiontimeout", "5000"
        );
        props.put(
                "mail.imaps.timeout", "10000"
        );
        props.put(
                "mail.imaps.ssl.checkserveridentity",
                "true"
        );

        receiver.setJavaMailProperties(props);
        return receiver;
    }

    @Bean
    IntegrationFlow inboundMailFlow(
            ImapMailReceiver receiver,
            MailIntakeService intake) {

        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(
                                    Duration.ofSeconds(30)
                            ).maxMessagesPerPoll(10)
                    )
                )
                .handle(intake, "accept")
                .get();
    }
}
~~~

Đoạn code minh họa cấu trúc receiver → source → polling endpoint → service activator. Các overload/tên API Java DSL cần tương thích với phiên bản Spring Integration dự án sử dụng.

`app.mail.inbound.url` có thể là URL receiver dạng `imaps://user:credential@host:993/INBOX` được tạo từ nguồn config tin cậy. Nếu URI chứa secret, phải xử lý URL encoding và không log URI nguyên vẹn. Provider dùng OAuth2 có thể yêu cầu cấu hình auth/token khác với URL password thông thường.

Hai lựa chọn trong ví dụ là chủ đích:

- `setShouldDeleteMessages(false)`: không tự xóa email sau khi fetch.
- `setShouldMarkMessagesAsRead(false)`: không tự biến việc fetch thành acknowledgment “đã xử lý”.

Điều này **không ngăn duplicate**. Vì thư vẫn có thể được receiver nhìn thấy lại, ứng dụng bắt buộc có idempotency store hoặc một search/ack policy rõ ràng.

## 9. MailIntakeService xử lý phần nào?

Một handler không nên làm toàn bộ công việc nặng khi session IMAP còn mở. Hướng hợp lý:

~~~java
public final class MailIntakeService {

    private final InboundMailIngestor ingestor;

    public MailIntakeService(
            InboundMailIngestor ingestor) {
        this.ingestor = ingestor;
    }

    public void accept(MimeMessage message)
            throws MessagingException {

        InboundEnvelope normalized =
                extractEnvelope(message);

        ingestor.persistIfNew(normalized);
    }

    private InboundEnvelope extractEnvelope(
            MimeMessage message)
            throws MessagingException {

        // Đọc metadata và content cần thiết.
        // Áp giới hạn MIME/attachment.
        // API ứng dụng tự định nghĩa.
        throw new UnsupportedOperationException(
                "Triển khai extractor theo dự án"
        );
    }
}
~~~

Các type `InboundEnvelope` và `InboundMailIngestor` là abstraction của ứng dụng, không phải API Spring sẵn có. Ví dụ cố ý để phương thức trích xuất ở dạng khung, bởi cách parse MIME và lấy UID cần phù hợp vòng đời folder trong implementation thực tế.

Điểm quan trọng:

- Intake phải biết mailbox/account source.
- Tạo một key ổn định cho email.
- Parse dữ liệu tối thiểu theo giới hạn.
- Persist metadata/content và job bền vững.
- Không tạo nhiều ticket chỉ vì một email được poll lại.
- Không chuyển một live `MimeMessage` vào queue tồn tại qua restart.

## 10. maxMessagesPerPoll không phải giới hạn kích thước

Ví dụ:

~~~java
Pollers.fixedDelay(
        Duration.ofSeconds(30)
).maxMessagesPerPoll(10)
~~~

Thông thường, `maxMessagesPerPoll` kiểm soát số lần nhận/message mà poller xử lý từ source mỗi lượt. Nhưng mail receiver có thể fetch metadata hoặc content theo batch, và tùy implementation nó có thể lấy nhiều candidate từ server trước khi poller hoàn tất.

Nó không đồng nghĩa:

- Mỗi lần polling chỉ dùng tối đa 10 MiB heap.
- Server chỉ gửi tối đa 10 MIME parts.
- Attachment được kiểm tra an toàn.
- Không có hơn 10 email đang nằm trong hệ thống.
- Business handler chỉ chạy 10 job toàn cluster.

Cần giới hạn **message size, attachment count, batch fetch, handler concurrency và queue capacity** bằng những cơ chế riêng.

## 11. Poll interval nên chọn thế nào?

Các yếu tố:

- Mailbox volume.
- Độ trễ phát hiện chấp nhận được.
- Provider connection/query quota.
- Thời gian fetch MIME/attachment.
- Năng lực CPU/heap/network.
- Backlog processing.
- Khả năng dùng IMAP IDLE.
- Mức độ ưu tiên của email.

Một hệ thống ticket không cần thời gian thực có thể poll mỗi vài chục giây; một hệ thống nhận báo cáo hàng ngày có thể poll theo phút. Đây chỉ là ví dụ, không có ngưỡng chung.

Giảm interval xuống một giây khi mailbox/server xử lý chậm có thể làm tăng throttling và kết nối bị reset. Cần đo **mailbox arrival → durable ingest → business processed** thay vì chỉ đo số poll/phút.

## 12. Polling khác IMAP IDLE

IMAP IDLE là extension cho phép client duy trì kết nối và nhận tín hiệu mailbox thay đổi. Spring Integration Mail có hướng **IMAP IDLE channel adapter** khi provider hỗ trợ.

| Yếu tố | Polling | IMAP IDLE |
| --- | --- | --- |
| Phát hiện | Theo lịch | Theo thông báo server khi kết nối IDLE |
| Độ trễ | Liên quan poll interval | Có thể thấp hơn |
| Kết nối | Theo chiến lược connect/fetch | Thường giữ session IDLE |
| IMAP support | Có thể dùng IMAP hoặc POP3 | Cần server hỗ trợ IDLE |
| Reconnect | Poll lần sau và retry | Phải reconnect/khởi động lại IDLE |
| Duplicate | Vẫn có thể | Vẫn có thể |
| Bỏ sót event khi đứt mạng | Cần rescan | Cần backfill/reconcile |

**IMAP IDLE không phải webhook HTTP** và không thay thế việc fetch nội dung. Khi mất kết nối, ứng dụng vẫn phải có cơ chế quét lại, xử lý duplicate và quản lý trạng thái.

Với nhu cầu đơn giản hoặc server không hỗ trợ IDLE ổn định, polling là lựa chọn rõ ràng, dễ quan sát và kiểm soát.

## 13. Search strategy: thế nào là thư mới?

Receiver IMAP có thể lọc theo:

- Folder được cấu hình.
- `\Seen` hoặc các flags.
- Server-side search terms.
- Ngày/thời điểm nhận.
- User flag do ứng dụng dùng.
- Các điều kiện custom theo chính sách.

Ví dụ:

~~~text
Poll receiver INBOX
  -> search UNSEEN
  -> fetch A và B
  -> đưa A, B vào channel
~~~

Nếu nhân viên mở A trong webmail trước khi poller chạy, `\Seen` có thể được đặt mặc dù application chưa ingest A. Ngược lại, nếu receiver không mark read và luôn search UNSEEN, A có thể được đưa lại qua các poll sau.

**Unseen khác unprocessed.** Flags của mailbox là trạng thái giao thức, không phải bằng chứng nghiệp vụ đã hoàn tất.

### Chỉ dựa vào timestamp cũng dễ mất thư

Một cơ chế “lấy các mail có receivedAt lớn hơn lần trước” có thể bỏ sót mail đến muộn, trùng timestamp hoặc các bản ghi server thay đổi metadata. Nếu dùng mốc thời gian để giảm tập tìm kiếm, nên có overlap/reconciliation kết hợp idempotency.

## 14. Thư đã đọc, đã xóa và đã xử lý

| Trạng thái | Nơi lưu | Ý nghĩa |
| --- | --- | --- |
| `\Seen` | IMAP mailbox | Server đánh dấu đã đọc |
| `\Deleted` | IMAP mailbox | Message được đánh dấu xóa theo IMAP |
| INGESTED | Database ứng dụng | Metadata/content cần thiết đã lưu |
| PROCESSING | Database/job queue | Worker đang xử lý nghiệp vụ |
| PROCESSED | Database | Nghiệp vụ đã hoàn thành |
| RETRY | Job store | Xử lý thất bại tạm thời |
| QUARANTINED | Database/storage riêng | Thư không thể xử lý bình thường |

Lỗi nguy hiểm:

~~~text
1. Receiver lấy email.
2. Mark Seen hoặc delete.
3. Database insert thất bại.
4. Poller chỉ tìm unseen.
5. Email không được tiếp nhận lại.
~~~

Vì vậy, nếu không có cơ chế phục hồi khác, **đừng xóa/đánh dấu loại khỏi search trước khi dữ liệu đã được persist bền vững**.

Một thứ tự phù hợp:

~~~text
Fetch candidate
  -> Extract key/content
  -> Persist unique inbox record
  -> Commit
  -> Ack / mark / move theo chính sách
  -> Process business job
~~~

Nếu acknowledgment thất bại sau commit, poll tiếp có thể phát hiện lại. Unique key giúp tránh tạo job mới.

## 15. IMAP sequence number, UID và UIDVALIDITY

Không nên dùng message number làm identifier bền vững.

**Sequence number** là vị trí message trong folder tại một thời điểm. Nó có thể thay đổi khi message bị expunge hoặc folder thay đổi.

**UID** là định danh ổn định theo semantics của một IMAP folder nhưng phải đặt trong namespace có **UIDVALIDITY**.

**UIDVALIDITY** giúp phân biệt những lần server thay namespace UID. Nếu thay đổi, không thể tiếp tục coi UID cũ và UID mới tương đương chỉ vì con số bằng nhau.

Một khóa phù hợp:

~~~text
mailboxAccountId
  + folderId
  + uidValidity
  + uid
~~~

~~~java
public record ImapMessageKey(
        String mailboxAccountId,
        String folderId,
        long uidValidity,
        long uid) {
}
~~~

Ví dụ khóa:

~~~text
(account-support, INBOX, 982341, 1077)
~~~

Nếu cùng email được copy sang folder khác, có thể có UID khác. Đây là định danh của **một occurrence trong mailbox**, không phải hash toàn cục của nội dung email.

## 16. Lấy UID qua Jakarta Mail

Jakarta Mail cung cấp `UIDFolder` khi folder hỗ trợ:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.UIDFolder;

public ImapMessageKey toKey(
        String accountId,
        String folderId,
        Message message) throws MessagingException {

    Folder folder = message.getFolder();

    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Không có UIDFolder"
        );
    }

    long uidValidity =
            uidFolder.getUIDValidity();

    long uid =
            uidFolder.getUID(message);

    return new ImapMessageKey(
            accountId,
            folderId,
            uidValidity,
            uid
    );
}
~~~

Đây là minh họa khi message/folder **còn hợp lệ và được mở**. Nếu receiver đã đóng folder hoặc message được chuyển tới handler sau khi connection kết thúc, việc lấy UID hoặc attachment lazy có thể thất bại.

Thiết kế tốt cần capture UID và metadata cần thiết **trong giai đoạn truy cập mailbox** theo lifecycle được receiver hỗ trợ. Không giữ session IMAP mở nhiều giờ chỉ vì business handler xử lý chậm.

## 17. Message-ID có đủ để dedupe không?

Header `Message-ID` thường hữu ích cho threading/tracing, nhưng:

- Có thể thiếu.
- Có thể bị lặp.
- Có thể bị sender giả mạo.
- Cùng message được copy vào folder khác có UID khác.
- Một email gửi lại có thể dùng Message-ID cũ hoặc mới.

Vì vậy, không dùng riêng Message-ID như khóa ingestion tuyệt đối. Với IMAP, tuple account/folder/UIDVALIDITY/UID bảo vệ việc ingest cùng một mailbox message.

Ngoài ra, nghiệp vụ có thể cần idempotency key riêng từ một request ID hoặc token hợp lệ trong email. Hai lớp này không giống nhau:

1. **Ingestion idempotency:** một occurrence IMAP được lưu một lần.
2. **Business idempotency:** một hành động nghiệp vụ không bị thực hiện lặp không chủ đích.

## 18. Idempotency store trong database

Một bảng minh họa:

~~~text
inbound_mail
------------
id
mailbox_account_id
folder_id
uid_validity
uid
message_id_header
sender_address
received_at
raw_object_key
ingestion_status
processing_status
first_seen_at
last_seen_at
~~~

Một unique constraint:

~~~sql
UNIQUE (
    mailbox_account_id,
    folder_id,
    uid_validity,
    uid
)
~~~

Khi một poller khác hoặc cùng poller chạy lại, insert duplicate key phải được xử lý theo contract:

~~~text
Insert thành công:
  -> mail mới, tạo business job.

Đã tồn tại unique key:
  -> mail đã ingest; không tạo job mới.
  -> có thể retry acknowledgment khi cần.
~~~

Không làm quy trình “SELECT chưa có rồi INSERT” mà thiếu unique constraint khi có nhiều worker; hai thread có thể cùng nhìn thấy chưa có rồi cùng ghi.

Nếu cần lưu raw MIME hoặc attachment, phải quản lý storage reference và transaction boundary để không tạo orphan objects hoặc xác nhận thành công trước khi dữ liệu đã bền vững.

## 19. At-least-once và lỗi giữa các bước

| Thời điểm crash/lỗi | Tình huống | Phục hồi |
| --- | --- | --- |
| Trước khi fetch | Chưa thấy thư | Poll lại |
| Fetch rồi, chưa persist | Content chỉ nằm tạm | Poll lại khi thư còn ở server |
| Persist xong, chưa mark Seen | Server có thể trả lại thư | Dedupe bằng unique key |
| Mark Seen xong, DB lỗi | Có nguy cơ bị bỏ sót | Tránh thứ tự này |
| Business worker lỗi | Inbound record còn | Retry job |
| Move/ack IMAP lỗi | Inbound đã lưu | Retry acknowledgment |
| Server đổi UIDVALIDITY | Key namespace mới | Reconcile theo policy |

Database và IMAP server không chung một transaction ACID. Vì vậy hệ thống thường thiết kế **ít nhất một lần phát hiện/ingest và xử lý có idempotency**, thay vì tuyên bố exactly-once chỉ do poller chạy một thread.

Nếu mailbox có chính sách xóa thư tự động, cần bảo đảm thời gian retention đủ dài để phục hồi khi ứng dụng ngừng nhiều giờ/ngày.

## 20. Tách intake khỏi xử lý nghiệp vụ dài

Một email có thể yêu cầu:

- Parse MIME.
- Quét attachment.
- OCR PDF.
- Trích dữ liệu hóa đơn.
- Tạo ticket.
- Gọi API bên thứ ba.
- Gửi email phản hồi.

Không nên giữ vòng poller và kết nối mailbox chờ toàn bộ công việc này khi throughput hoặc độ tin cậy quan trọng.

~~~mermaid
flowchart TD
    A["IMAP/POP3 poll"] --> B["Fetch + metadata"]
    B --> C["Validate MIME/size"]
    C --> D["Persist unique inbound record"]
    D --> E["Persist raw content/attachment"]
    E --> F["Business queue"]
    F --> G["Worker"]
    G --> H{"Kết quả"}
    H -->|"Đúng"| I["PROCESSED"]
    H -->|"Tạm lỗi"| J["RETRY"]
    H -->|"Lỗi cố định"| K["QUARANTINED"]
~~~

Sau khi đã capture bền vững, business worker đọc dữ liệu từ database/object storage thay vì từ một `MimeMessage` còn gắn với folder/session.

### Vì sao không đưa live MimeMessage vào queue?

Một `MimeMessage` có thể dùng lazy content hoặc stream từ folder/server. Khi handler xử lý muộn, folder có thể đã đóng, dẫn tới lỗi đọc body/attachment. Queue bền vững cũng không nên serialize toàn bộ Jakarta Mail object.

Chuyển thành DTO có metadata nhỏ, object storage key, nội dung đã kiểm tra hoặc raw MIME được lưu có giới hạn.

## 21. MIME email inbound là dữ liệu không đáng tin

Một email có thể có:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
├── image/png (inline)
└── invoice.pdf (attachment)
~~~

Các rủi ro:

- Sender From giả mạo.
- Subject chứa token/ký tự bất thường.
- HTML có markup độc hại hoặc remote tracking.
- Attachment chứa malware.
- Filename có path traversal.
- MIME part lồng sâu hoặc malformed.
- ZIP bomb.
- Nội dung cực lớn gây cạn heap.
- Email chứa dữ liệu nhạy cảm phải tuân thủ retention và access policy.

Đừng dùng `message.getFrom()` để quyết định ai có quyền sửa một ticket. Email sender identity là dữ liệu có thể giả mạo, cần xác thực theo nghiệp vụ bằng token, identity binding hoặc chính sách được phê duyệt.

### HTML trong email không nên render trực tiếp vào admin UI

Một màn hình xem email cần sanitize nội dung, giới hạn tải remote images và dùng sandbox/CSP phù hợp. `MimeMessage.getContent()` không phải một HTML sanitizer.

## 22. Trích xuất multipart có giới hạn

Một helper minh họa:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public void inspectPart(
        Part part,
        int depth) throws Exception {

    if (depth > 12) {
        throw new IllegalArgumentException(
                "MIME nesting quá sâu"
        );
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart =
                (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            inspectPart(
                    multipart.getBodyPart(i),
                    depth + 1
            );
        }

        return;
    }

    if (part.isMimeType("text/plain")) {
        // Giới hạn số bytes/chars trước khi lưu.
        return;
    }

    if (part.isMimeType("text/html")) {
        // Lưu/sanitize theo policy, không render trực tiếp.
        return;
    }

    // Phần khác: attachment, inline file,
    // nested message hoặc content không được hỗ trợ.
}
~~~

Đây là **phác thảo**, không phải MIME parser production. Cần xử lý nested `message/rfc822`, charset, filename encoding và stream lifecycle đúng. `multipart/alternative` thường biểu diễn cùng nội dung ở plain text và HTML, không phải hai yêu cầu nghiệp vụ riêng.

Không tin Content-Type hoặc filename sender cung cấp để xác định file an toàn. Với loại file nhạy cảm, cần kiểm tra bytes, scan và size caps phù hợp.

## 23. Size policy và attachment streaming

Một vài giới hạn có thể thiết lập:

| Giới hạn | Mục đích |
| --- | --- |
| Max total MIME bytes | Chặn email quá lớn |
| Max attachment bytes | Chặn một file lớn |
| Max total attachment bytes | Giới hạn tổng tài nguyên |
| Max part count | Tránh hàng nghìn MIME parts |
| Max nesting depth | Tránh nội dung lồng sâu |
| Max HTML/plain bytes | Tránh body bất thường |
| Max processing time | Bảo vệ worker |
| Max concurrent fetch | Giới hạn áp lực mailbox |
| Quarantine TTL | Retention và bảo vệ dữ liệu |

Nếu attachment lớn, stream vào managed storage với bộ đếm byte và giới hạn; không vô điều kiện gọi `readAllBytes()` hoặc lưu cả file dưới `byte[]` trong queue. Với email multipart malformed hoặc kích thước vượt policy, có thể quarantine và vẫn tiếp tục các email khác.

## 24. IMAPS, POP3S và quản lý credential

Trong production:

1. Dùng TLS đúng provider.
2. Bật hostname/certificate verification.
3. Không tắt TLS validation để chữa lỗi kết nối.
4. Cấu hình connection/read timeouts.
5. Dùng secret manager cho credential.
6. Hỗ trợ OAuth2/token refresh nếu provider yêu cầu.
7. Không log URI chứa username/password.
8. Giới hạn egress host/port theo provider approved.
9. Theo dõi authentication failure và lockout.
10. Không mở quyền đọc mailbox production cho automated tests.

Một URL-based receiver đôi khi dùng cấu trúc:

~~~text
imaps://user:secret@imap.example.org:993/INBOX
~~~

Đây là ví dụ cú pháp, không phải nơi đặt password trong source code. Ký tự đặc biệt trong credential phải được encode đúng theo cách receiver diễn giải URL; secret không được in lại trong exception.

### Một miền gửi không nhất thiết có IMAP mailbox

Một application có thể có quyền gửi bằng SMTP subaccount nhưng không có inbox tương ứng. Nếu muốn nhận reply/bounce, cần cấu hình mailbox hoặc provider webhook riêng. Không suy luận từ địa chỉ From rằng IMAP credentials chắc chắn tồn tại.

## 25. Nhiều tenant hoặc nhiều mailbox

Một nền tảng có thể nhận:

~~~text
support@tenant-a.example
invoices@tenant-b.example
reply@platform.example
~~~

Mỗi mailbox cần cấu hình:

- Account ID/tenant scope.
- Endpoint và folder.
- Credential reference.
- Poll interval và connection limit.
- Search strategy.
- Idempotency namespace.
- Storage/retention policy.
- Business destination.

Nếu một mailbox tập trung chứa email cho nhiều tenant qua alias, phải có quy tắc mapping đáng tin. Header `To` hoặc From không luôn đủ để xác minh tenant, nhất là email forwarding/Bcc. Có thể dùng recipient alias token đã cấp cho tenant/workflow và xác thực trước khi thực hiện thao tác.

Poller chạy nền không có HTTP actor request. Không nên dựa vào một `ThreadLocal` tenant context từ request cũ.

## 26. Nhiều worker cùng poll một inbox

Giả sử:

~~~text
Pod A -> poll INBOX
Pod B -> poll INBOX
~~~

Hai pod có thể thấy cùng UID. IMAP không tự cung cấp cơ chế phân phối đúng một message cho một worker giống Kafka consumer group.

Các phương án:

- Một active poller cho mỗi mailbox.
- Leader election/distributed lease.
- Phân hoạch mailbox/account cho từng instance.
- DB unique key bảo vệ duplicate ingestion.
- Kết hợp lease và idempotency để tăng hiệu quả.

**IMAP Seen flag không phải distributed lock.** Hai client có thể tìm cùng thư trước khi một client đánh dấu, hoặc server có semantics khác với transaction DB.

Lease cần có owner, expiration và cơ chế bảo vệ worker cũ sau khi lease bị chuyển. Nếu không, process chết có thể làm inbox ngừng được poll vô thời hạn.

## 27. Transaction giữa inbox và database

`@Transactional` trên service có thể quản lý transaction database, nhưng không biến thao tác IMAP mark/move/delete thành một phần commit nguyên tử.

Một thứ tự đề xuất:

~~~text
Fetch mail
  -> Extract UID + content
  -> Begin DB transaction
  -> Insert inbox unique key
  -> Persist business job
  -> Commit DB
  -> Mark/move mail theo policy
~~~

Nếu mark/move lỗi sau commit, có thể poll lại và dedupe. Nếu DB lỗi trước commit, thư vẫn còn trong mailbox và có thể được ingest lại.

Cần tránh việc một lỗi ở mailbox khiến một transaction DB kéo dài hàng chục giây trong khi đang giữ lock. Mở transaction ngắn quanh phần persist, tách thao tác network khi thích hợp.

## 28. Xử lý lỗi và retry

| Lỗi | Cách xử lý |
| --- | --- |
| IMAP connection timeout | Reconnect/backoff |
| AUTH failure | Refresh credential/alert, không retry nóng |
| TLS/certificate error | Sửa trust/config, không bỏ validation |
| Folder bị đổi hoặc xóa | Configuration failure, cảnh báo |
| Server throttling | Giảm poll rate, backoff |
| MIME malformed | Quarantine và tiếp tục |
| Attachment vượt size | Quarantine/reject có lý do |
| Duplicate UID | Bỏ qua side effect trùng |
| Database unavailable | Không ack mất thư |
| Business API lỗi | Retry job riêng |
| Ack/move lỗi | Retry acknowledgment, giữ dedupe |
| Unknown mailbox state | Reconcile theo key và server metadata |

Spring Integration có error channel/error handling cho các flow, nhưng nhận được error event **không tự giải quyết** trạng thái email trên server. Handler lỗi cần xác định: có cần retry poll, retry business job hay đưa thư vào quarantine?

Một poison message malformed có thể xuất hiện tại mọi poll và chặn những thư phía sau. Nên ghi trạng thái lỗi/UID, áp retry limit và cho các message hợp lệ tiếp tục đi qua.

## 29. Polling và backpressure

Giả sử mailbox nhận 500 email/phút nhưng processor chỉ xử lý được 100/phút. Việc giảm poll delay từ 30 giây xuống 1 giây không tăng năng lực xử lý nghiệp vụ; backlog có thể tăng nhanh hơn.

Một kiến trúc cần:

- Bounded poller/worker concurrency.
- Queue/job persistence.
- Limits trên MIME size.
- Max in-flight data/attachments.
- Rate limit theo mailbox/provider.
- Retry schedule, không busy loop.
- Ưu tiên mail quan trọng.
- Theo dõi oldest pending message.
- Cơ chế giảm intake khi storage gần đầy.

Nếu dùng queue in-memory và acknowledge mailbox trước khi job được persist, restart có thể làm mất công việc. Với nghiệp vụ quan trọng, durable intake nên nằm trước acknowledgment.

## 30. Monitoring và cảnh báo

| Metric | Ý nghĩa |
| --- | --- |
| `mail_inbound_poll_total` | Số lần poll |
| `mail_inbound_poll_duration_seconds` | Độ trễ poll |
| `mail_inbound_poll_failure_total` | Lỗi mailbox |
| `mail_inbound_candidate_total` | Số candidate |
| `mail_inbound_ingested_total` | Số email ingest mới |
| `mail_inbound_duplicate_total` | Số lần gặp lại UID |
| `mail_inbound_quarantined_total` | Thư bị cách ly |
| `mail_inbound_processing_failure_total` | Lỗi nghiệp vụ |
| `mail_inbound_backlog_count` | Công việc chưa xong |
| `mail_inbound_oldest_pending_age_seconds` | Độ trễ lớn nhất |
| `mail_inbound_reconnect_total` | Lần reconnect |
| `mail_inbound_lease_conflict_total` | Tranh chấp lease |

Label nên dùng mailbox ID nội bộ, protocol và error category. Đừng gắn email sender, subject hay tên attachment vào mọi metric vì có thể lộ thông tin và gây cardinality lớn.

Alert hữu ích khi:

- Không có successful poll vượt SLA.
- Credential/TLS fail lặp lại.
- Backlog và oldest pending age tăng.
- Quarantine tăng bất thường.
- Lượng duplicate ingestion tăng mạnh.
- UIDVALIDITY thay đổi, cần resync.
- Mailbox storage gần cạn quota.
- Một tenant có email chờ quá lâu.

## 31. Unit test những gì?

Các bài test không cần mailbox thật:

**Key idempotency:**

~~~java
@Test
void sameUidWithinSameNamespaceIsSameMessage() {
    ImapMessageKey first =
            new ImapMessageKey(
                    "account-a",
                    "INBOX",
                    100L,
                    200L
            );

    ImapMessageKey second =
            new ImapMessageKey(
                    "account-a",
                    "INBOX",
                    100L,
                    200L
            );

    assertEquals(first, second);
}
~~~

**Business ingestion:** mock mailbox adapter nhưng dùng repository/transaction test phù hợp để xác nhận unique constraint chống trùng.

**MIME extractor:** dựng MIME fixture với `text/plain`, `text/html`, nested multipart, filename Unicode và attachment nhỏ; kiểm tra size/depth limits.

**Security:** email From giả hoặc subject chứa ticket ID không được phép tạo side effect nếu thiếu authorization token/identity hợp lệ.

**Retry state machine:** những lỗi parse cố định chuyển quarantine, lỗi DB tạm thời không được ack mất thư, lỗi business có nextAttemptAt.

## 32. Integration test với IMAP test server

Một integration test có thể dùng GreenMail hoặc công cụ test IMAP tương đương:

~~~text
Test IMAP server
  -> Test mailbox + seeded MIME message
  -> ImapMailReceiver
  -> Polling adapter
  -> MailIntakeService
  -> Inbound repository
  -> Assertions by correlation/UID
~~~

Các bước:

1. Khởi tạo mailbox test riêng với port/credential riêng.
2. Seed một email có correlation ID.
3. Chạy poller hoặc kích hoạt polling có kiểm soát.
4. Đợi record ingestion xuất hiện.
5. Kiểm tra metadata/nội dung đã persist.
6. Poll lần nữa và xác nhận không có duplicate.
7. Mô phỏng DB failure và retry.
8. Cleanup tài nguyên của test.

Không dùng inbox production hoặc một mailbox dùng chung toàn CI. Các test chạy song song cần isolate server/recipient/UID namespace và không gọi delete-all trên tài nguyên của test khác.

### Đợi theo điều kiện thay vì Thread.sleep

Ví dụ với thư viện Awaitility nếu dự án sử dụng:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertTrue(
                inboundRepository.existsByCorrelationId(
                        correlationId
                )
            );
        });
~~~

`existsByCorrelationId` là test helper/repository method minh họa. Mục tiêu là quan sát đúng dữ liệu thuộc test, không kiểm tra mailbox “newest message” toàn cục.

## 33. Ma trận kiểm thử lỗi

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Inbox trống | Poll không tạo job |
| Có thư mới | Ingest một record |
| Poll cùng UID hai lần | Không tạo business side effect trùng |
| Hai JVM cùng poll | Unique constraint/lease bảo vệ |
| UIDVALIDITY đổi | Không dùng offset UID cũ mù quáng |
| Thư đã Seen | Xử lý theo search policy có chủ đích |
| IMAP mất kết nối | Reconnect/backoff |
| Credential bị khóa | Alert, không vòng lặp login nóng |
| MIME hỏng | Quarantine và tiếp tục |
| Attachment quá lớn | Không làm cạn heap |
| DB lỗi trước commit | Không ack mất thư |
| Ack thất bại sau commit | Poll lại dedupe |
| Worker crash sau ingest | Job bền vững còn |
| Folder đóng trước đọc attachment | Dữ liệu cần thiết đã capture |
| Poison message đầu queue | Không chặn mail khác |
| Restart giữa poll | Tái đồng bộ mà không mất dữ liệu |

Không phải tất cả test cần provider thật. Một fake receiver/transport có thể phát lỗi có cấu trúc ở unit/component test; một IMAP test server nên kiểm tra interaction và lifecycle thực tế.

## 34. Những lỗi triển khai thường gặp

### 34.1. Dùng JavaMailSender để truy vấn hộp thư

`JavaMailSender` dùng SMTP. Nhận thư cần IMAP/POP3 mail receiver hoặc adapter phù hợp.

### 34.2. Tin rằng poller tự bảo đảm exactly-once

Poller chỉ kích hoạt source; không có transaction chung giữa mailbox và DB.

### 34.3. Chỉ xem \Seen là đã xử lý

Một client khác có thể đánh dấu đọc. Flag không phản ánh trạng thái nghiệp vụ.

### 34.4. Mark Seen/delete trước khi persist

DB lỗi có thể khiến email không được thấy lại khi search unseen.

### 34.5. Dùng message number làm UID

Sequence number có thể thay đổi khi folder expunge.

### 34.6. Bỏ qua UIDVALIDITY

UID không thể được hiểu đúng nếu namespace UID đã thay đổi.

### 34.7. Dedupe bằng Message-ID duy nhất

Header có thể thiếu/trùng/bị giả. Cần key mailbox và business policy.

### 34.8. Hai pod cùng poll mà không coordination

Có thể double ingest; dùng lease/leader và DB unique constraint.

### 34.9. Tin maxMessagesPerPoll là giới hạn RAM

Một email 100 MiB vẫn có thể làm heap bùng nổ. Cần MIME size policy.

### 34.10. Xử lý OCR lâu trực tiếp trong polling handler

Giữ thread/kết nối quá lâu. Tách durable intake và processor.

### 34.11. Cho MimeMessage sống qua queue/restart

Folder/session có thể đóng; nên persist nội dung cần thiết.

### 34.12. Cho rằng IMAP IDLE không cần rescan

Connection có thể đứt và cần backfill/reconnect.

### 34.13. Retry vô hạn thư hỏng

Poison message gây backlog; dùng quarantine và reason code.

### 34.14. Tin sender From là người đã được xác thực

Header có thể giả. Không cập nhật dữ liệu nhạy cảm chỉ theo From/subject.

### 34.15. Hiển thị HTML trực tiếp lên dashboard

Có nguy cơ nội dung độc hại và tracking. Sanitize/sandbox.

### 34.16. Tin Content-Type/filename attachment

Metadata không chứng minh file an toàn; cần validation/scanning.

### 34.17. Log toàn bộ raw MIME

Có thể lộ PII, token và file đính kèm.

### 34.18. Dùng mailbox production trong test

Có nguy cơ đánh dấu/xóa mail thật hoặc lộ credential.

### 34.19. Dùng Thread.sleep để test async

Dễ flaky; đợi theo correlation ID và timeout.

### 34.20. Gộp tenant bằng một shared inbox thiếu mapping tin cậy

Có thể xử lý thư sai tenant; cần trusted alias/token/ownership validation.

## 35. Câu hỏi thực hành

**Câu 1.** `JavaMailSender` có tự polling IMAP không?

Không. Nó là outbound SMTP abstraction.

**Câu 2.** Poller 30 giây có bảo đảm một thư chỉ được xử lý một lần?

Không. Cần search/ack policy và idempotency.

**Câu 3.** Receiver không mark Seen và không có dedupe store. Điều gì xảy ra?

Cùng thư có thể được fetch lại nhiều lần.

**Câu 4.** UID 100 ở hai folder khác nhau có nhất thiết là cùng message không?

Không. UID thuộc namespace của folder và UIDVALIDITY.

**Câu 5.** Message-ID có đủ để chống trùng toàn bộ không?

Không. Nó có thể thiếu, trùng hoặc bị giả mạo.

**Câu 6.** DB commit xong nhưng chưa mark Seen, app crash. Làm thế nào?

Poll lại, unique key nhận ra đã lưu và tiếp tục acknowledgment.

**Câu 7.** Mark Seen trước khi DB commit có rủi ro gì?

Nếu DB lỗi và search chỉ lấy unseen, email có thể bị bỏ sót.

**Câu 8.** IMAP IDLE có tự tạo durable queue không?

Không. Nó chỉ hỗ trợ phát hiện thay đổi, vẫn cần persist/recovery.

**Câu 9.** Nhiều pod cùng poll một mailbox có được IMAP chia message như Kafka không?

Không mặc định. Cần coordination/idempotency.

**Câu 10.** maxMessagesPerPoll bằng 1 có an toàn trước email 200 MiB không?

Không. Cần size limits và streaming.

**Câu 11.** Subject có ticket ID nghĩa sender được quyền sửa ticket?

Không. Phải xác thực/authorize theo nghiệp vụ.

**Câu 12.** Có nên chuyển MimeMessage vào job queue xử lý sau một ngày?

Không nên dựa vào live object. Persist DTO/raw content có kiểm soát.

**Câu 13.** Email malformed bị fetch liên tục. Xử lý ra sao?

Quarantine/reason code/retry limit để không chặn toàn bộ mailbox.

**Câu 14.** Hai email có cùng Message-ID nhưng UID khác, ứng dụng làm gì?

Ingest theo key mailbox rồi áp business dedupe policy phù hợp, không kết luận tự động.

**Câu 15.** Muốn xác nhận transport IMAP hoạt động, nên test ở đâu?

Integration test với mailbox/test server cô lập, không cần provider production.

## 36. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["IMAP / POP3 mailbox"] --> B["Poller"]
    B --> C["MailReceivingMessageSource"]
    C --> D["Inbound channel adapter"]
    D --> E["Extract UID + metadata"]
    E --> F["Validate MIME / size / security"]
    F --> G{"Đã ingest?"}
    G -->|"Rồi"| H["Dedupe / ack theo policy"]
    G -->|"Chưa"| I["Persist unique record"]
    I --> J["Commit dữ liệu + job"]
    J --> K["Ack/move mailbox"]
    J --> L["Business worker"]
    L --> M{"Xử lý"}
    M -->|"Success"| N["PROCESSED"]
    M -->|"Temporary"| O["RETRY"]
    M -->|"Permanent"| P["QUARANTINED"]
~~~

Những điểm quan trọng:

1. **Inbound channel adapter đưa email từ mailbox vào Spring Integration channel**, không gửi qua SMTP.
2. **Poller quyết định lịch gọi**, còn receiver/search strategy quyết định candidate.
3. **IMAP/POP3 khác nhau** về folder, UID, flags và deletion semantics.
4. **IMAP IDLE giảm độ trễ khi được hỗ trợ**, nhưng vẫn cần reconnect/backfill/idempotency.
5. **Unread, ingested và processed là ba khái niệm khác nhau.**
6. **Không mark/delete trước durable persistence** nếu có nguy cơ mất thư.
7. **IMAP key nên gồm account, folder, UIDVALIDITY và UID**, không chỉ message number.
8. **Polling lặp lại là bình thường**; cần unique constraint và business idempotency.
9. **Nhiều instance cần lease/coordination**, không coi IMAP flag là distributed lock.
10. **MIME inbound là untrusted input**; áp size/depth caps, scanning và business authorization.
11. **Không giữ live MimeMessage qua worker dài**, nên lưu content/metadata bền vững.
12. **maxMessagesPerPoll không phải memory size cap**; cần bounded resources.
13. **Monitoring phải theo dõi poll failures, backlog, duplicates, quarantine và latency.**
14. **Test với mailbox cô lập** và bao phủ crash recovery, UIDVALIDITY, duplicate và MIME lỗi.

Trong Spring Framework Mail, nhận thư đáng tin cậy không chỉ là “cứ 30 giây lại đọc INBOX”. **Inbound channel adapter và polling tạo điểm vào có cấu trúc cho email**, còn ứng dụng phải quyết định thư nào là mới, khi nào được xem là đã lưu bền vững, cách xử lý trùng và cách phục hồi sau sự cố. Tách receiver, poller, idempotency store, durable intake, business processing và monitoring sẽ giúp mailbox trở thành nguồn dữ liệu có kiểm soát, thay vì một vòng lặp dễ bỏ sót thư hoặc thực hiện cùng một nghiệp vụ nhiều lần.
