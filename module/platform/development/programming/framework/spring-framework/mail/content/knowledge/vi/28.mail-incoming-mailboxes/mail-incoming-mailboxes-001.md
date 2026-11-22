# Phạm vi gửi thư của JavaMailSender so với đọc thư trong Spring Framework Mail

Trong Spring Framework Mail, `JavaMailSender` là abstraction quen thuộc để **gửi email**. Lập trình viên có thể tạo `SimpleMailMessage` hoặc `MimeMessage`, cấu hình SMTP host, username, password và gọi `send(...)`. Nhưng khi ứng dụng cần **đọc Inbox**, tìm email mới, tải attachment nhận được hoặc xử lý thư phản hồi, chỉ có `JavaMailSender` là chưa đủ.

Đây là một ranh giới kiến trúc quan trọng: **gửi email** và **đọc email** là hai loại hoạt động khác nhau, thường sử dụng giao thức, quyền truy cập, trạng thái và vòng đời kết nối khác nhau. Phía gửi làm việc với SMTP submission; phía đọc thường làm việc với IMAP, POP3 hoặc API riêng của nhà cung cấp mailbox.

Bài học giải thích chính xác phạm vi API của Spring Mail, cách sử dụng Jakarta Mail để truy xuất mailbox, lý do không thể “đọc email đã gửi” chỉ bằng `JavaMailSender`, ví dụ Java/Spring cho hai chiều, xử lý MIME và attachment, quản lý UID, bảo mật, lựa chọn Spring Integration Mail cùng các quy tắc kiểm thử và vận hành.

## 1. Câu trả lời ngắn gọn: JavaMailSender làm gì và không làm gì?

`JavaMailSender` nằm trong package `org.springframework.mail.javamail`, mở rộng `MailSender` và bổ sung khả năng làm việc với MIME message.

Chức năng chính:

- Tạo `MimeMessage` bằng `createMimeMessage()`.
- Gửi `SimpleMailMessage` dạng text đơn giản.
- Gửi `MimeMessage` có HTML, attachment, inline resource và nhiều header.
- Sử dụng Jakarta Mail transport để giao tiếp với SMTP server theo cấu hình.
- Thông báo lỗi preparation, authentication hoặc submission qua exception phù hợp.

Những chức năng **không phải hợp đồng của JavaMailSender**:

- Mở hộp thư Inbox.
- Lấy danh sách thư đã nhận.
- Tìm các thư unread trong mailbox.
- Đọc nội dung thư người khác đã gửi đến tài khoản.
- Quản lý IMAP folders hoặc flags `SEEN`, `ANSWERED`, `DELETED`.
- Đồng bộ mailbox sau khi kết nối lại.
- Tìm thư bằng IMAP UID hoặc POP3 UIDL.
- Tự cung cấp webhook cho email đến.
- Tự đánh dấu một message SMTP đã gửi là delivered hoặc opened.

**Kết luận:** `JavaMailSender` là sender, không phải một “JavaMailReceiver” đa năng của Spring Framework Mail.

## 2. Sơ đồ luồng gửi và luồng đọc

Hai chiều có thể dùng cùng thư viện nền Jakarta Mail nhưng không cùng một giao thức.

~~~text
                     ỨNG DỤNG SPRING
                            |
              +-------------+-------------+
              |                           |
              v                           v
       GỬI EMAIL                      ĐỌC EMAIL
              |                           |
       JavaMailSender                Jakarta Mail
              |                      Session + Store
              v                           |
       SMTP transport                     v
              |                      IMAP / POP3
              v                           |
      Submission relay                    v
              |                       Mailbox
              v
      Hệ thống nhận
              |
              v
         Recipient mailbox
~~~

Trong đường gửi, ứng dụng là **SMTP client** nói chuyện với SMTP submission server. Trong đường đọc, ứng dụng là **mailbox client** kết nối tới mailbox server thông qua `Store` và `Folder`.

Cùng một provider có thể cung cấp cả hai dịch vụ, nhưng endpoint, port, authentication scope và policy thường khác nhau.

## 3. SMTP, IMAP, POP3 phục vụ mục đích khác nhau

| Giao thức | Công dụng chính | Port phổ biến | Đối tượng ứng dụng thao tác |
| --- | --- | ---: | --- |
| SMTP submission + STARTTLS | Gửi email tới relay | 587 | Envelope, DATA, submission response |
| SMTP implicit TLS | Gửi email qua kết nối TLS từ đầu | 465 | Tương tự SMTP submission |
| SMTP relay | Truyền giữa mail servers | 25 | Truyền tiếp giữa các server |
| IMAP | Truy xuất và quản lý mailbox trên server | 143; IMAPS 993 | Folder, message, flags, UID |
| POP3 | Tải mail từ mailbox với mô hình đơn giản | 110; POP3S 995 | Message retrieval, UIDL nếu hỗ trợ |

Đây là các cổng phổ biến, không phải mọi provider đều cung cấp đúng toàn bộ những cổng đó. Luôn dùng endpoint theo tài liệu nhà cung cấp.

**SMTP không có lệnh chuẩn để “liệt kê các email trong Inbox”.** Ngược lại, IMAP không thay thế được một SMTP transport dùng để gửi thư đến recipient bên ngoài.

### Tại sao cần phân biệt?

Nếu một ứng dụng lưu `spring.mail.host=smtp.example.com` rồi dùng host đó với `Store.getFolder("INBOX")`, kết nối sẽ thất bại vì endpoint SMTP có thể không cung cấp IMAP. Tương tự, dùng port 993 cho `JavaMailSenderImpl` cấu hình protocol SMTP không có nghĩa sẽ gửi được thư.

## 4. MailSender và JavaMailSender trong Spring

Spring Mail có hai mức abstraction:

| API | Đối tượng hỗ trợ | Chức năng |
| --- | --- | --- |
| `MailSender` | `SimpleMailMessage` | Gửi email text đơn giản |
| `JavaMailSender` | `SimpleMailMessage` và `MimeMessage` | Tạo MIME, gửi HTML/attachment/inline |
| `JavaMailSenderImpl` | Implementation chính | Cấu hình host, port, protocol, credentials và JavaMail properties |
| `MimeMessageHelper` | Helper khi tạo message | Thiết lập From/To/Subject, HTML, multipart, attachment |

Ví dụ phương thức thường gặp:

~~~java
JavaMailSender mailSender = ...;

MimeMessage message = mailSender.createMimeMessage();

// Dùng MimeMessageHelper để chuẩn bị nội dung.
mailSender.send(message);
~~~

Không có một `mailSender.receive()` chuẩn để lấy email từ Inbox. Một `JavaMailSenderImpl` có thể cung cấp Jakarta Mail `Session` nội bộ, nhưng **đừng vì vậy coi sender là mailbox reader**. Ranh giới service và credential nên được tách riêng.

## 5. Cấu hình Spring Boot cho gửi email

Khi ứng dụng có `spring-boot-starter-mail`, Spring Boot có thể cấu hình `JavaMailSender` từ `spring.mail.*`.

Ví dụ `application.yml`:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Các giá trị là ví dụ. `SMTP_USERNAME`/`SMTP_PASSWORD` phải được inject từ môi trường hoặc secret manager; không commit credential thật.

Ý nghĩa:

- `spring.mail.host/port` trỏ tới SMTP submission server.
- `spring.mail.username/password` cung cấp credential theo cơ chế SMTP AUTH đã chọn.
- `mail.smtp.auth` bật authentication của SMTP transport.
- `mail.smtp.starttls.*` cấu hình nâng cấp kết nối lên TLS.
- `mail.smtp.ssl.checkserveridentity` giúp kiểm tra hostname của certificate server.
- `mail.smtp.*timeout` tránh chờ network vô hạn.

**Các properties này không tự tạo inbound mail listener hoặc IMAP mailbox reader.** Muốn đọc mail, cần cấu hình riêng và implementation phù hợp.

## 6. Ví dụ gửi email với JavaMailSender

Service gửi plain text:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final JavaMailSender mailSender;

    public NotificationSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(recipient);
        mail.setSubject("Xác nhận đơn hàng " + orderCode);
        mail.setText(
            "Đơn hàng " + orderCode + " đã được xác nhận."
        );

        mailSender.send(mail);
    }
}
~~~

Service xây message và gửi bằng SMTP. Nó **không truy cập Inbox** của `orders@example.com`, không tự tạo bản sao trong Sent folder và không bảo đảm thư xuất hiện trong Inbox của recipient.

### Với HTML và attachment

~~~java
MimeMessage mime = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn mới");
helper.setText(
    "Hóa đơn của bạn đã được phát hành.",
    "<html><body><h1>Hóa đơn</h1>"
        + "<p>Vui lòng xem tệp đính kèm.</p>"
        + "</body></html>"
);

helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(pdfFile)
);

mailSender.send(mime);
~~~

`pdfFile` là một `java.io.File` hợp lệ do ứng dụng chuẩn bị. Cần bảo đảm resource tồn tại, đọc được và được phép gửi. Spring Mail hỗ trợ nhiều loại nội dung, nhưng vẫn chỉ đi theo chiều **outgoing SMTP submission**.

## 7. Khi send trả về thành công, điều gì thực sự đã được xác nhận?

Phải phân biệt các mốc:

~~~text
CREATED
   |
   v
ENQUEUED
   |
   v
SMTP submission attempt
   |
   v
SMTP accepted
   |
   v
Downstream relay/filtering
   |
   v
DELIVERED / DEFERRED / BOUNCED
   |
   v
Recipient reads or interacts (nếu có bằng chứng)
~~~

`JavaMailSender.send(...)` kết thúc bình thường thường tương ứng SMTP submission thành công theo hợp đồng của transport. Điều đó không đồng nghĩa:

- Recipient đã nhận vào Inbox.
- Message không bị lọc spam.
- Recipient đã mở hoặc đọc.
- Provider không bounce sau đó.
- Email đã xuất hiện trong Sent folder của tài khoản gửi.

SMTP reply thành công sau `DATA` là bằng chứng relay đang kết nối đã chấp nhận message. Delivery ở downstream là một giai đoạn khác, cần provider events, DSN hoặc thông tin mailbox riêng khi được phép truy cập.

Nếu sender ném exception, cũng không được mặc định mọi recipient đều chưa nhận: timeout sau DATA hoặc partial send có thể tạo kết quả không chắc chắn.

## 8. Jakarta Mail dùng Store và Folder để đọc

Đối với IMAP/POP3, Jakarta Mail cung cấp những abstraction quan trọng:

| Type | Vai trò |
| --- | --- |
| `Session` | Cấu hình JavaMail provider và properties |
| `Store` | Kết nối tới mailbox store theo IMAP/POP3 |
| `Folder` | Thư mục như INBOX, Sent, Archive |
| `Message` | Một email trong folder |
| `MimeMessage` | Biểu diễn message MIME có header/body |
| `Multipart` | Container nhiều MIME parts |
| `BodyPart` | Một phần text, HTML, attachment hoặc inline |
| `Flags` | Trạng thái đọc, đánh dấu, xóa... |
| `SearchTerm` | Điều kiện tìm message |
| `UIDFolder` | Làm việc với UID/UIDVALIDITY trên folder có hỗ trợ |

Phía gửi thường sử dụng `Transport` bên dưới `JavaMailSender`; phía đọc dùng `Store` và `Folder`.

~~~text
Jakarta Mail Session
        |
        +--> Transport (SMTP) --> send
        |
        +--> Store (IMAP) ------> Folder --> Message
        |
        +--> Store (POP3) ------> retrieval
~~~

Không nhầm `MimeMessage` với việc “đọc email”: đó là **kiểu dữ liệu biểu diễn nội dung email**, có thể xuất hiện ở cả chiều gửi và chiều nhận. Nó không tự mở kết nối tới mailbox.

## 9. Cấu hình inbound mailbox riêng

Spring Boot `spring.mail.*` định hướng việc gửi SMTP. Đối với inbox reader tự viết, có thể tạo namespace cấu hình riêng, ví dụ:

~~~yaml
app:
  mail:
    incoming:
      protocol: imaps
      host: imap.example.com
      port: 993
      username: ${INBOX_USERNAME}
      password: ${INBOX_PASSWORD}
      folder: INBOX
      poll-batch-size: 20
~~~

Các `app.mail.incoming.*` là **properties do ứng dụng định nghĩa**, không phải cấu hình tự động bật một inbox reader của Spring Boot.

Có thể bind bằng `@ConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.incoming")
public record IncomingMailProperties(
    String protocol,
    String host,
    int port,
    String username,
    String password,
    String folder,
    int pollBatchSize
) {}
~~~

Để Spring tạo bean này, có thể dùng `@EnableConfigurationProperties(IncomingMailProperties.class)` hoặc configuration properties scanning theo project.

Nên có cấu hình bảo mật, validation và secret manager riêng cho inbound. Đừng mặc định một SMTP username/password có thể đăng nhập IMAP; provider/tenant có thể cấp credential và quyền khác nhau.

## 10. Một ví dụ IMAP đọc Inbox bằng Jakarta Mail

Ví dụ sau đọc **metadata của một số thư mới nhất theo thứ tự trong folder**. Nó không xử lý toàn bộ mailbox và không tự đánh dấu thư đã đọc; mục tiêu là minh họa `Session → Store → Folder → Message` rõ ràng.

~~~java
import jakarta.mail.Address;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.internet.InternetAddress;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Properties;

import org.springframework.stereotype.Service;

@Service
public class ImapInboxReader {

    private final IncomingMailProperties settings;

    public ImapInboxReader(IncomingMailProperties settings) {
        this.settings = settings;
    }

    public List<IncomingMailSummary> readLatest(int requestedLimit)
            throws MessagingException {

        int limit = Math.max(1, Math.min(requestedLimit, 100));

        Properties props = new Properties();
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password()
            );

            Folder inbox = store.getFolder(settings.folder());
            inbox.open(Folder.READ_ONLY);

            try {
                int total = inbox.getMessageCount();
                if (total <= 0) {
                    return List.of();
                }

                int first = Math.max(1, total - limit + 1);
                Message[] messages = inbox.getMessages(first, total);

                List<IncomingMailSummary> result = new ArrayList<>();

                for (Message message : messages) {
                    Address[] from = message.getFrom();
                    String sender = null;

                    if (from != null && from.length > 0) {
                        Address firstFrom = from[0];
                        if (firstFrom instanceof InternetAddress ia) {
                            sender = ia.getAddress();
                        } else {
                            sender = firstFrom.toString();
                        }
                    }

                    Date received = message.getReceivedDate();

                    result.add(new IncomingMailSummary(
                        sender,
                        message.getSubject(),
                        received == null
                            ? null
                            : received.toInstant()
                    ));
                }

                return result;
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

DTO:

~~~java
import java.time.Instant;

public record IncomingMailSummary(
    String fromAddress,
    String subject,
    Instant receivedAt
) {}
~~~

Ví dụ sử dụng `imaps`/port 993. `session.getStore("imaps")` mở đúng protocol provider tương ứng. `READ_ONLY` không cho phép ứng dụng sửa flags theo API trong lúc đọc.

Đoạn code là một **bounded metadata read**, không phải production mailbox synchronization engine: nó chỉ lấy tối đa 100 message cuối theo thứ tự folder và không có checkpoint, UID dedup hoặc xử lý nội dung. Các phần tiếp theo giải thích những yếu tố cần có để mở rộng.

## 11. Cách đóng Store và Folder đúng

IMAP giữ kết nối mạng và state phía server. Nếu không đóng tài nguyên:

- Connection có thể bị cạn.
- Folder có thể còn ở trạng thái open.
- Mail server phải giữ session lâu.
- Worker không giải phóng socket/thread đúng lúc.
- Test sau bị ảnh hưởng bởi connection cũ.

Thứ tự an toàn thường là:

1. Tạo `Session`.
2. Lấy và connect `Store`.
3. Lấy và open `Folder`.
4. Đọc metadata/body trong phạm vi cho phép.
5. Đóng `Folder` trong `finally`.
6. Đóng `Store` trong `finally`.

~~~java
Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

try {
    // Read messages.
} finally {
    if (folder.isOpen()) {
        folder.close(false);
    }
}
~~~

`close(false)` không yêu cầu expunge các message đã đánh dấu xóa. Trong một số giao thức/hành vi provider, các thao tác flags vẫn có semantic riêng; không dùng folder `READ_WRITE` hoặc `expunge` nếu use case chỉ đọc.

Không chia sẻ một `Folder` đang mở giữa nhiều threads một cách tùy tiện. Nếu cần throughput cao, thiết kế worker ownership, connection lifecycle hoặc provider-supported pooling thật rõ.

## 12. Khi nào cần IMAP thay vì POP3?

IMAP thích hợp cho những use case như:

- Đọc Inbox và các folders.
- Tìm mail chưa đọc hoặc có flags.
- Đồng bộ mailbox qua nhiều thiết bị/worker.
- Lưu checkpoint UID.
- Di chuyển email sang folder đã xử lý nếu provider hỗ trợ.
- Theo dõi trạng thái thư trên server.

POP3 thích hợp hơn cho những tình huống đơn giản chỉ cần tải message theo mailbox, với mô hình folder và flags hạn chế hơn.

| Đặc điểm | IMAP | POP3 |
| --- | --- | --- |
| Nhiều folders | Có | Thường không |
| Server-side search/flags | Tốt hơn | Hạn chế |
| Truy xuất một phần message | Phụ thuộc server/provider | Hạn chế hơn |
| Đồng bộ trạng thái | Có UID/flags | UIDL tùy server |
| Push-like notifications | IMAP IDLE nếu hỗ trợ | Không cùng cơ chế |
| Workflow xử lý inbox lâu dài | Thường phù hợp | Phù hợp tải đơn giản |

Đừng chọn POP3 nếu nghiệp vụ yêu cầu folder, flags và mailbox synchronization phức tạp. Nhưng cũng không bắt buộc dùng IMAP nếu provider chỉ cung cấp API inbound mail hoặc webhook đã chuẩn hóa.

## 13. Message number không phải định danh bền vững

Trong IMAP, một message trong folder có **message sequence number** và có thể có **UID**. Cần phân biệt:

- `message.getMessageNumber()`: thứ tự/sequence trong folder đang mở.
- `UIDFolder.getUID(message)`: UID của message trong một folder có hỗ trợ.
- `UIDFolder.getUIDValidity()`: thế hệ UID của folder; khi thay đổi, checkpoint UID cũ không còn ý nghĩa như trước.

Message numbers có thể thay đổi khi message khác bị xóa/expunge. Vì vậy, dùng “message số 42” làm idempotency key lâu dài là không đáng tin.

Ví dụ lấy UID khi folder hỗ trợ:

~~~java
if (inbox instanceof UIDFolder uidFolder) {
    long uidValidity = uidFolder.getUIDValidity();

    for (Message message : messages) {
        long uid = uidFolder.getUID(message);

        log.debug(
            "IMAP message reference: uidValidity={}, uid={}",
            uidValidity,
            uid
        );
    }
}
~~~

Import `jakarta.mail.UIDFolder`. Trong production nên dùng khóa gồm mailbox identity, folder identity, UIDVALIDITY và UID để chống xử lý trùng trong phạm vi folder.

## 14. UID, UIDVALIDITY và idempotency

Một bảng ghi nhận message đã xử lý có thể có schema PostgreSQL:

~~~sql
CREATE TABLE processed_incoming_mail (
    mailbox_id       VARCHAR(120) NOT NULL,
    folder_name      VARCHAR(255) NOT NULL,
    uid_validity     BIGINT NOT NULL,
    uid              BIGINT NOT NULL,
    processing_state VARCHAR(30) NOT NULL,
    processed_at     TIMESTAMPTZ,
    PRIMARY KEY (
        mailbox_id,
        folder_name,
        uid_validity,
        uid
    )
);
~~~

Khi worker đọc được một UID:

1. Kiểm tra bảng đã xử lý.
2. Nếu chưa có, **claim atomically** và đánh dấu đang xử lý.
3. Parse nội dung theo giới hạn an toàn.
4. Lưu kết quả nghiệp vụ bền vững.
5. Đánh dấu PROCESSED.
6. Sau đó mới thay đổi folder/flag nếu workflow yêu cầu.
7. Nếu crash, job có thể được reclaim và xử lý idempotently.

Không chỉ đánh dấu `SEEN` rồi coi đó là “đã xử lý thành công”: một worker có thể đánh dấu đã đọc trước khi lưu database và crash, khiến email không được quét lại.

**Một message chuyển sang folder khác có thể nhận UID khác.** Nếu muốn chống xử lý trùng trên toàn mailbox, cần logic correlation bổ sung dựa trên business key hoặc metadata đáng tin, không chỉ UID của một folder.

## 15. Message-ID có thay thế UID không?

Header `Message-ID` được gửi kèm trong RFC 5322 message và có ích cho correlation, nhưng:

- Có email thiếu Message-ID.
- Có client tạo Message-ID không đúng hoặc không duy nhất.
- Message-ID có thể bị giữ nguyên khi email được chuyển/copy.
- Kẻ gửi có thể giả mạo Message-ID.
- Một mailbox có thể chứa nhiều bản copy cùng Message-ID.

Vì vậy, không dùng Message-ID đơn lẻ làm khóa bảo đảm uniqueness của mỗi message trong mailbox. Dùng UID + UIDVALIDITY trong scope mailbox/folder, và thêm business idempotency key nếu inbound message kích hoạt sự kiện nghiệp vụ.

Đối với POP3, `UIDL` nếu server hỗ trợ có semantics khác IMAP UID; không tái sử dụng một schema mà không lưu nguồn protocol và mailbox/folder phù hợp.

## 16. Tìm email chưa đọc bằng IMAP

Một số use case cần đọc email chưa được đánh dấu SEEN. Jakarta Mail hỗ trợ `SearchTerm`, ví dụ:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;
import jakarta.mail.search.FlagTerm;

Message[] unread = inbox.search(
    new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
    )
);
~~~

Đoạn này giả định `inbox` là một `Folder` đã mở. `false` yêu cầu tìm những message không có flag SEEN.

Nhưng **UNSEEN không đồng nghĩa UNPROCESSED** trong hệ thống xử lý nghiệp vụ:

- Người dùng có thể mở email bằng client khác.
- Một worker khác có thể đọc trước.
- Server/client có thể cập nhật flags.
- Một worker có thể đã xử lý email rồi nhưng chưa set SEEN.
- Message có thể được di chuyển/expunge.

Với workflow cần độ tin cậy, dùng durable processing ledger theo UID, còn flags chỉ là tín hiệu phụ hoặc thao tác UX trên mailbox.

### Tránh quét vô hạn

`folder.search(...)` có thể trả nhiều message. Trong production cần paging/checkpoint hoặc giới hạn volume phù hợp. Không mặc định tải toàn bộ inbox vào memory rồi lọc Java nếu mailbox có hàng trăm nghìn email.

## 17. Đọc MIME body cần xử lý multipart

Phía nhận có thể chứa:

~~~text
MimeMessage
    |
    +--> text/plain
    |
    +--> text/html
    |
    +--> multipart/alternative
    |       +--> text/plain
    |       +--> text/html
    |
    +--> multipart/mixed
            +--> multipart/alternative
            +--> attachment: invoice.pdf
            +--> multipart/related
                    +--> inline image
~~~

`Message.getContent()` không phải lúc nào cũng trả String. Với multipart, kết quả có thể là `Multipart`. Không viết:

~~~java
String body = (String) message.getContent();
~~~

nếu không biết MIME type. Cast như vậy có thể ném `ClassCastException`.

Khi đọc email nhận, cần duyệt parts và phân biệt:

- Body text/plain.
- Body text/html.
- Attachment.
- Inline resource.
- Nested multipart.
- Embedded message/rfc822.
- Content-Disposition, filename và Content-ID.

Không phải mọi message đều có plain-text alternative; một số chỉ có HTML hoặc có cấu trúc lạ. Parser cần xử lý lỗi và giới hạn tài nguyên.

## 18. Ví dụ tìm phần text trong MIME

Ví dụ helper dùng cho message đơn giản, có chủ đích bỏ qua attachment:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static String findTextPart(
        Part part,
        String wantedMimeType) throws Exception {

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        return null;
    }

    if (part.isMimeType(wantedMimeType)) {
        Object content = part.getContent();
        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String nested = findTextPart(
                multipart.getBodyPart(i),
                wantedMimeType
            );

            if (nested != null) {
                return nested;
            }
        }
    }

    return null;
}
~~~

Sử dụng:

~~~java
String plain = findTextPart(message, "text/plain");
String html = findTextPart(message, "text/html");
~~~

Helper trả về text part đầu tiên phù hợp. Nó không phải parser production an toàn cho mọi MIME tree: cần giới hạn nesting depth, number of parts, decoded body bytes, charset và xử lý embedded message. Khi một mailbox nhận email không tin cậy từ Internet, phải bảo vệ khỏi MIME bombs, nested parts quá sâu và tệp đính kèm quá lớn.

**Không hiển thị raw HTML email nhận được trực tiếp trong ứng dụng web** mà không sanitize/sandbox. HTML có thể chứa nội dung gây hại hoặc tracking resources.

## 19. Đọc attachment nhận được khác với thêm attachment khi gửi

Khi gửi, ta thêm attachment:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(pdfFile)
);
~~~

Khi đọc, phải duyệt `Part` và lấy thông tin:

~~~java
if (Part.ATTACHMENT.equalsIgnoreCase(
        part.getDisposition())) {

    String fileName = part.getFileName();

    try (InputStream input = part.getInputStream()) {
        // Stream to a bounded, quarantined destination.
    }
}
~~~

Dùng `Part.getInputStream()` để lấy decoded bytes theo transfer encoding phù hợp, nhưng phải giới hạn kích thước, số lượng parts và loại nội dung; không đơn giản `readAllBytes()` cho mọi email ngoài Internet.

Trước khi lưu/cho phép tải attachment:

1. Giới hạn số lượng file và tổng bytes.
2. Kiểm tra Content-Type khai báo nhưng không tin tuyệt đối.
3. Chuẩn hóa filename, chặn path traversal.
4. Lưu ngoài web root hoặc vào object storage có quyền phù hợp.
5. Scan malware theo chính sách.
6. Phân loại file nguy hiểm (script/executable/archive).
7. Không tự mở hoặc thực thi file.
8. Chỉ cấp URL tải xuống có kiểm soát và thời hạn phù hợp.

Một attachment `filename="../../something"` không được dùng nguyên làm destination path. Người gửi có toàn quyền tạo MIME headers, nên chúng là dữ liệu không tin cậy.

## 20. Email nhận được là dữ liệu không tin cậy

Không vì email xuất hiện trong mailbox mà mặc định nội dung từ người dùng hợp lệ. Kẻ tấn công có thể giả mạo From/display name, gửi HTML nguy hiểm, file malware, links lừa đảo hoặc nested MIME khiến parser tốn nhiều tài nguyên.

Những lớp kiểm tra thường cần:

- Authentication/authorization của workflow sử dụng thư.
- Danh sách sender/domain được phép khi hợp lý.
- SPF/DKIM/DMARC verdict từ provider nếu cần và có nguồn đáng tin.
- Kiểm tra token hoặc correlation ID gắn với workflow.
- Size limit, MIME limits, anti-malware.
- HTML sanitization hoặc text-only rendering.
- Rate limit theo mailbox/source.
- Idempotent processing để chống replay.
- Audit và retention policy.

**Header From không phải bằng chứng xác thực danh tính.** Nếu một thư trả lời yêu cầu thay đổi thông tin tài khoản, không thực hiện thao tác nhạy cảm chỉ dựa vào một địa chỉ From khớp.

## 21. JavaMailSender có đọc được thư từ Sent folder không?

Không trực tiếp. **Việc gửi qua SMTP không đảm bảo bản sao của email xuất hiện trong thư mục Sent của mailbox gửi.**

Tùy provider và cách gửi:

- Một webmail client có thể lưu bản sao Sent khi chính client gửi.
- Một SMTP provider có thể tự lưu Sent copies theo chính sách.
- Một ứng dụng SMTP client tùy biến có thể chỉ submit qua SMTP mà không append vào Sent.
- Một provider dùng virtual mailbox hoặc API mà không cung cấp Sent folder tương ứng.

Nếu sản phẩm cần lưu bản sao đã gửi, cần tự thiết kế:

1. Lưu `notificationId`, rendered content snapshot và submission result trong database/storage.
2. Hoặc, nếu mailbox provider cho phép, kết nối IMAP và append một `MimeMessage` vào đúng folder Sent.
3. Hiểu folder name khác nhau theo provider: `Sent`, `Sent Items` hoặc tên localized/special-use.
4. Tránh tạo hai bản Sent nếu provider đã tự lưu khi SMTP submission.
5. Không coi sự tồn tại của bản Sent là bằng chứng người nhận đã nhận email.

### Ví dụ IMAP append vào folder

~~~java
Folder sent = store.getFolder("Sent");
sent.open(Folder.READ_WRITE);

try {
    sent.appendMessages(
        new Message[] { mimeMessage }
    );
} finally {
    sent.close(false);
}
~~~

Ví dụ chỉ minh họa API `appendMessages`; `store` phải là IMAP Store đã connect và `mimeMessage` phải chứa nội dung phù hợp. Một số provider có cơ chế lưu Sent đặc biệt, folder name và policy riêng. Trong production, không hard-code folder `Sent` nếu chưa xác định đúng mailbox.

## 22. Có thể dùng JavaMailSender để kiểm tra email người nhận đã đọc chưa?

Không. `JavaMailSender` chỉ gửi. Một email đã được SMTP relay chấp nhận có thể tiếp tục qua nhiều mail servers, rồi vào Inbox/Spam hoặc bị bounce.

Không thể tùy ý truy cập Inbox của người nhận chỉ vì ứng dụng biết địa chỉ email của họ. Để đọc mailbox cần có quyền truy cập hợp lệ và credential/ủy quyền do mailbox owner hoặc provider cấp.

Ngay cả khi có quyền đọc một mailbox:

- Đọc được message chứng minh mailbox đó chứa một bản email.
- Flag `SEEN` không chứng minh người thật đã đọc kỹ.
- Không có flag SEEN không chứng minh email chưa được mở bằng mọi client.
- Email tracking pixel/click events cũng có sai lệch do proxy/bot/security scanner.
- Delivery/bounce nên được theo dõi bằng ESP/provider events khi có.

Đừng dùng IMAP polling vào một hộp thư test làm bằng chứng mọi người dùng thật đều nhận email như nhau.

## 23. Dùng chung một tài khoản SMTP và IMAP có được không?

Có thể, nếu provider và chính sách account cho phép, nhưng đó là **quyết định của provider**, không phải bảo đảm của Spring Mail.

Ví dụ:

~~~text
SMTP submit endpoint:
  host = smtp.example.com
  port = 587
  account = service@example.com

IMAP mailbox endpoint:
  host = imap.example.com
  port = 993
  account = service@example.com
~~~

Dù cùng username, hai protocol có thể:

- Dùng credential khác nhau.
- Có quyền truy cập khác nhau.
- Dùng OAuth scopes/audience riêng.
- Bị tắt độc lập theo tenant policy.
- Có authentication mechanism khác.
- Có quota/concurrent connection limit khác.

Đừng copy toàn bộ `spring.mail.properties.mail.smtp.*` sang IMAP và kỳ vọng nó hoạt động. Cần dùng `mail.imaps.*` cho protocol `imaps` hoặc properties phù hợp với provider.

## 24. Bảo mật kết nối IMAP/POP3

Đối với đọc mailbox production, nên ưu tiên TLS và xác minh server identity.

Ví dụ IMAPS:

~~~java
Properties props = new Properties();
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");
props.put("mail.imaps.ssl.checkserveridentity", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

Với IMAPS thường kết nối TLS ngay khi bắt đầu qua port 993. Nếu dùng IMAP + STARTTLS trên port 143 theo provider, cần cấu hình `mail.imap.starttls.enable`, `mail.imap.starttls.required` và trust/hostname validation tương ứng.

Không dùng trust-all hoặc tắt hostname verification để “chữa” certificate errors trong production. Cần sửa hostname, CA/trust store, certificate chain và chế độ TLS cho đúng.

Đối với POP3S, provider/session prefix thường là `mail.pop3s.*`. Không lấy properties của IMAP dùng nguyên cho POP3S.

## 25. OAuth và quyền truy cập mailbox

Một số provider hạn chế hoặc vô hiệu hóa basic password authentication cho IMAP/POP3; người dùng có thể phải dùng OAuth2/XOAUTH2 hoặc provider API.

Cần tách quyền:

- Quyền **SMTP gửi** email.
- Quyền **IMAP đọc** mailbox.
- Quyền đọc một mailbox cụ thể hoặc toàn tenant.
- Quyền ghi flags/move/delete.
- Quyền quản lý settings hoặc subscription.

Một access token có quyền SMTP không chắc được chấp nhận cho IMAP. OAuth access token thường có audience, scope và expiry; reader phải xin token dành cho đúng endpoint và đúng loại quyền.

Trong một số Jakarta Mail provider, cơ chế `XOAUTH2` có thể được dùng cho IMAP khi server/client hỗ trợ, nhưng cách cấu hình và grant phụ thuộc nhà cung cấp. Không đưa refresh token trực tiếp vào `Store.connect(...)` như password. Token provider phải xin access token còn hạn và làm mới theo chính sách.

Nếu ứng dụng chỉ cần nhận sự kiện đến email qua API webhook của provider, có thể không cần cấp quyền IMAP toàn bộ mailbox.

## 26. IMAP polling và IMAP IDLE

Có hai kiểu phát hiện thư mới:

### Polling

Ứng dụng định kỳ kết nối hoặc dùng session hiện tại để tìm message mới.

~~~text
Every N seconds:
   Connect
   Open INBOX
   Find new UID range
   Claim unprocessed messages
   Process
   Save checkpoint
   Close
~~~

Ưu điểm: dễ hình dung, dễ retry và giám sát. Nhược điểm: có thể tốn kết nối, tăng latency và phải quản lý checkpoint.

### IMAP IDLE

Một số IMAP servers hỗ trợ extension IDLE, cho phép client nhận thông báo thay đổi mailbox trong lúc connection được giữ. Nó có thể giúp giảm latency và polling không cần thiết, nhưng:

- Server/provider phải hỗ trợ.
- Connection có thể bị ngắt, cần reconnect/backoff.
- Notifications không thay thế durable reconciliation.
- Vẫn phải kiểm tra UID và deduplicate.
- Không nên tạo một thread/connection vô hạn cho từng tenant nếu provider có connection limits.
- Cần xem client library hỗ trợ ra sao.

Trong Jakarta Mail/Angus Mail, một số functionality IMAP IDLE có thể nằm ở provider-specific IMAP folder implementation. Không giả định `JavaMailSender` cung cấp `idle()`.

## 27. Spring Integration Mail khi cần inbound pipeline

Nếu chỉ cần đọc vài message, Jakarta Mail `Store`/`Folder` có thể đủ. Nhưng ứng dụng có luồng inbound liên tục, chuyển email thành message cho các bước xử lý, cần poller/adapter, có thể xem **Spring Integration Mail**.

Những khái niệm thường gặp:

- `ImapMailReceiver`: nhận message qua IMAP.
- `Pop3MailReceiver`: nhận message qua POP3.
- `ImapIdleChannelAdapter`: adapter dựa trên IMAP IDLE khi server hỗ trợ.
- Inbound channel adapter và message channel: đưa email nhận thành messages cho pipeline xử lý.
- Filters, transformers, service activators: các bước xử lý nội dung và routing.

Sơ đồ:

~~~text
Mailbox provider
       |
       v
Spring Integration Mail inbound adapter
       |
       v
Message channel
       |
       v
Parser / validator / dedup
       |
       v
Business command or inbox event
       |
       v
Durable storage / downstream processing
~~~

**Spring Integration Mail là module/tính năng bổ sung**, không phải method `receive()` được thêm vào `JavaMailSender`. Cần dependency và cấu hình riêng, tương thích Spring version.

Spring Integration giúp tổ chức luồng messaging nhưng không tự giải quyết toàn bộ concerns: credential security, UID checkpoint, idempotency, mailbox permissions, attachment sanitization và business transaction semantics vẫn cần được thiết kế.

## 28. Kiến trúc khi ứng dụng vừa gửi vừa nhận email

Một service có thể hỗ trợ cả outgoing notifications và incoming customer replies, nhưng nên tách port:

~~~java
public interface OutboundMailPort {
    void send(OutgoingMail mail);
}
~~~

~~~java
public interface InboundMailboxPort {
    List<IncomingMailSummary> poll(
        String mailboxId,
        int limit
    );
}
~~~

Ứng dụng tổ chức thành:

~~~text
                 Business application
                         |
          +--------------+--------------+
          |                             |
          v                             v
    OutboundMailPort               InboundMailboxPort
          |                             |
          v                             v
   SmtpMailAdapter               ImapMailboxAdapter
          |                             |
          v                             v
    JavaMailSender                  Session + Store
          |                             |
          v                             v
      SMTP server                   Mailbox server
~~~

Cách này tránh việc một `MailService` khổng lồ vừa có logic template/gửi vừa trực tiếp quản lý mailbox flags, UID checkpoint, attachment scanning và inbound routing.

### Tách DTO chiều gửi và chiều nhận

`OutgoingMail` có thể gồm recipient, template, subject, body, attachment references. `IncomingMail` có thể gồm mailbox source, UID, headers đã chuẩn hóa, received timestamp, parsed parts và processing status. Đừng dùng chung DTO để tránh vô tình tin dữ liệu From do người ngoài cung cấp như recipient có quyền hệ thống.

## 29. Khi xử lý email phản hồi: Reply-To và reply matching

Một hệ thống gửi thư hỗ trợ phản hồi có thể đặt `Reply-To`:

~~~java
helper.setFrom("notifications@example.com");
helper.setReplyTo("support@example.com");
~~~

Khi người dùng nhấn Reply, email client thường hướng trả lời về địa chỉ Reply-To. Nhưng việc đặt Reply-To **không khiến ứng dụng tự nhận reply**. Cần inbound mailbox, provider inbound routing hoặc webhook được cấu hình.

Để liên kết reply tới notification/ticket, có thể dùng:

- Một địa chỉ reply có mã routing riêng được quản lý an toàn.
- `In-Reply-To` và `References` headers khi có.
- Ticket/notification ID trong header tùy chỉnh hoặc metadata.
- Business token/verification code rõ ràng.
- Subject như một tín hiệu phụ, không phải khóa xác thực.

`In-Reply-To`/`References` hữu ích nhưng có thể thiếu hoặc bị sửa; subject có thể thay đổi theo email client. Không thực hiện hành động nhạy cảm chỉ dựa trên một thread header.

Nếu người dùng gửi reply qua một mailbox bên ngoài, ứng dụng cần quyền đọc mailbox đó hoặc provider inbound gateway chuyển message đến hệ thống.

## 30. Nhận bounce và DSN có nhất thiết phải đọc Inbox?

Không nhất thiết. Bounce/Delivery Status Notification (DSN) có thể được gửi tới envelope return-path mailbox, hoặc Email Service Provider có event API/webhook.

Các lựa chọn:

| Nguồn | Thông tin có thể nhận | Lưu ý |
| --- | --- | --- |
| SMTP relay logs | Submission, queue/defer/reject | Cần quyền truy cập server/provider |
| ESP webhook | Delivered, bounced, deferred, complaint | Provider-specific, cần verify signature |
| Return-path mailbox | DSN/bounce messages | Cần parser DSN và inbound reader |
| Người nhận phản hồi | Reply content | Không đồng nghĩa delivery event chuẩn |
| Sent folder | Bản copy của mail gửi | Không chứng minh delivered |

Nếu provider có webhook có cấu trúc tốt, việc xử lý sự kiện giao thư qua webhook có thể đơn giản hơn parse các DSN rất đa dạng trong mailbox. Nếu hệ thống tự vận hành SMTP, đọc bounce mailbox có thể là một phần của vận hành.

Một DSN cũng là email không tin cậy theo góc nhìn parser: phải correlation, dedup, tránh chạy hành động nguy hiểm và không suy ra nhầm từ From/subject.

## 31. Sender và receiver cần state machine riêng

Outgoing notification:

~~~text
PENDING
   |
   v
SUBMITTING
   |
   +--> SUBMITTED
   +--> RETRY_WAIT
   +--> FAILED
   +--> AMBIGUOUS
~~~

Incoming message:

~~~text
DISCOVERED
   |
   v
CLAIMED
   |
   +--> PARSED
   |      |
   |      v
   |   PROCESSED
   |
   +--> RETRY_WAIT
   +--> REJECTED
   +--> QUARANTINED
~~~

Hai state machines có semantics khác nhau:

- Outgoing retry có nguy cơ gửi trùng nếu SMTP outcome ambiguous.
- Incoming retry có nguy cơ xử lý cùng email nhiều lần nếu worker crash sau khi side effect đã commit.
- Outgoing cần provider rate limit và deadline.
- Incoming cần UID checkpoint, mailbox reconciliation và safe parsing.
- Outgoing status SUBMITTED không tương đương incoming status PROCESSED.

Nếu một ứng dụng có cả hai chiều, nên dùng separate repositories/metrics hoặc model đủ rõ để tránh ghi cùng một cột `sent` cho mọi loại mail.

## 32. Một incoming worker an toàn về độ tin cậy

Một luồng thực tế:

~~~text
IMAP poller
   |
   v
Read mailbox UID/UIDVALIDITY
   |
   v
Check durable dedup ledger
   |
   v
Claim unprocessed UID
   |
   v
Load bounded MIME content
   |
   v
Validate sender/routing/token
   |
   v
Store sanitized artifacts
   |
   v
Apply business action idempotently
   |
   v
Mark PROCESSED in DB
   |
   v
Optional mark SEEN / move to processed folder
~~~

Nếu process crash **sau business commit nhưng trước khi mark PROCESSED**, email có thể được xử lý lại. Vì vậy business handler cần idempotency key chứ không chỉ checkpoint mailbox.

Nếu mark SEEN trước khi lưu trạng thái, có nguy cơ bỏ sót. Nếu move message trước khi hoàn tất xử lý, UID có thể thay đổi và khiến recovery phức tạp.

Không giữ mailbox connection mở trong toàn bộ database transaction kéo dài, không download attachments khổng lồ trong transaction và không chạy business actions trực tiếp từ thư không xác thực.

## 33. Kết nối nhiều mailbox hoặc multi-tenant

Khi ứng dụng phục vụ nhiều mailbox, cần phân biệt:

- SMTP account dùng để gửi.
- IMAP account dùng để đọc.
- Quyền mỗi tenant/mailbox.
- Thời hạn/rotation của credential.
- Concurrency/connection quota mỗi provider.
- UID checkpoint namespace theo mailbox.
- Storage isolation cho nội dung/attachments.
- Retention và privacy policy.

Không dùng chung mutable `Store`/`Folder` giữa tenant A và B một cách thiếu kiểm soát. Không lấy host/port/mailbox credentials tùy ý từ HTTP request rồi kết nối ngay; cần chống SSRF, giới hạn endpoint và secret storage.

Với nhiều mailboxes, một poller có thể cần lịch phân bổ capacity và circuit breaker theo provider để lỗi của một tenant không làm nghẽn toàn bộ người dùng khác.

## 34. Performance khi đọc mailbox lớn

Một mailbox có hàng trăm nghìn message không thích hợp để mỗi phút gọi `getMessages(1, total)` rồi tải nội dung toàn bộ.

Giới hạn thường cần:

- **Batch size:** số UID/messages xử lý mỗi lượt.
- **Page/checkpoint:** chỉ lấy phần chưa xử lý.
- **Prefetch headers:** lấy metadata trước, tránh tải body sớm.
- **Body size budget:** từ chối/quarantine message quá lớn.
- **Attachment count/bytes budget:** tránh tiêu thụ RAM/disk quá mức.
- **Concurrency:** giới hạn số IMAP connections.
- **Timeout/reconnect:** không block mãi khi server mất kết nối.
- **Backpressure:** nếu downstream xử lý chậm, giảm tốc độ đọc.
- **Retention:** dọn processed artifacts theo chính sách.
- **Server search/UID API:** tận dụng đúng khi provider hỗ trợ.

Các API Jakarta Mail như `FetchProfile` có thể giúp yêu cầu trước những trường cần thiết, tùy provider implementation:

~~~java
FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

inbox.fetch(messages, profile);
~~~

Đoạn này cần import `jakarta.mail.FetchProfile`, `Message` và folder đã mở. Không có nghĩa server chắc chắn thực thi hiệu quả giống nhau trên mọi provider.

## 35. Các lỗi thường gặp khi đọc IMAP/POP3

| Triệu chứng | Khả năng | Hướng điều tra |
| --- | --- | --- |
| Connect tới SMTP host bằng IMAP | Sai protocol/endpoint | Dùng IMAP host và port riêng |
| `AuthenticationFailedException` | Credential, OAuth scope hoặc policy | Kiểm tra quyền mailbox, không chỉ SMTP |
| TLS handshake failure | Chế độ port/certificate sai | Xác minh host, trust store, TLS mode |
| `FolderNotFoundException` | Tên folder khác hoặc không tồn tại | List folders, xem namespace/special-use |
| `FolderClosedException` | Server đóng folder/connection | Reconnect và resume theo UID |
| `MessageRemovedException` | Message bị xóa/expunge khi đang đọc | Reconcile UID/checkpoint |
| Query unread trả rỗng | Flags đã thay đổi hoặc mailbox khác | Không dựa riêng vào UNSEEN |
| Cùng email xử lý hai lần | Thiếu durable dedup | UIDVALIDITY + UID và business idempotency |
| Body cast sang String lỗi | Multipart message | Duyệt MIME tree |
| Attachment làm hết RAM | Không giới hạn stream/size | Bounded streaming + quarantine |
| Không có bản Sent sau SMTP | Provider không tự lưu | Thiết kế explicit Sent/archive policy |
| Sender gửi thành công, reader không thấy trong Inbox | Hai mailbox khác nhau hoặc downstream chưa giao | Phân biệt submit/delivery và kiểm tra provider |
| Mailbox polling chậm | Full mailbox scan/connection churn | UID checkpoint, batching/prefetch |

Mỗi lỗi cần đọc nested exception và protocol phase. Không tự suy ra lỗi IMAP là `JavaMailSender` hỏng khi sender vẫn submit SMTP bình thường.

## 36. Kiểm thử chiều gửi và chiều nhận bằng GreenMail

Một SMTP integration test đơn giản có thể dùng GreenMail capture server và gọi `getReceivedMessages()`. Tuy nhiên, cách đó chỉ đọc API capture của test server; nó **không** mở IMAP mailbox.

Nếu muốn thực sự kiểm tra cả hai protocol, chạy GreenMail SMTP và IMAP:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

ServerSetup smtpSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
);

ServerSetup imapSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_IMAP
);

GreenMail greenMail = new GreenMail(
    new ServerSetup[] { smtpSetup, imapSetup }
);

greenMail.start();

try {
    greenMail.setUser(
        "reader@example.test",
        "reader",
        "test-secret"
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(greenMail.getSmtp().getPort());

    SimpleMailMessage outgoing = new SimpleMailMessage();
    outgoing.setFrom("sender@example.test");
    outgoing.setTo("reader@example.test");
    outgoing.setSubject("SMTP và IMAP");
    outgoing.setText("Nội dung kiểm thử hai chiều.");

    sender.send(outgoing);

    // Confirm test SMTP has captured the submitted message.
    boolean received = greenMail.waitForIncomingEmail(5000, 1);
    if (!received) {
        throw new AssertionError("No message reached test SMTP");
    }

    Session session = Session.getInstance(new Properties());
    Store store = session.getStore("imap");

    try {
        store.connect(
            "127.0.0.1",
            greenMail.getImap().getPort(),
            "reader",
            "test-secret"
        );

        Folder inbox = store.getFolder("INBOX");
        inbox.open(Folder.READ_ONLY);

        try {
            Message[] messages = inbox.getMessages();
            if (messages.length != 1) {
                throw new AssertionError("Unexpected message count");
            }

            if (!"SMTP và IMAP".equals(
                    messages[0].getSubject())) {
                throw new AssertionError("Wrong subject");
            }
        } finally {
            inbox.close(false);
        }
    } finally {
        store.close();
    }
} finally {
    greenMail.stop();
}
~~~

Ví dụ cần dependency GreenMail tương thích với Jakarta Mail/Angus Mail và import tương ứng. Vì test server chạy trên loopback, example sử dụng protocol `imap` không TLS cho môi trường test cục bộ. **Không sao chép cấu hình plaintext này sang production.**

Kết quả test chứng minh:

1. JavaMailSender submit message qua SMTP test server.
2. Test mailbox đã lưu message.
3. Jakarta Mail Store kết nối IMAP và đọc subject được.

Không chứng minh email gửi qua một SMTP provider production sẽ vào Inbox của mọi recipient.

## 37. Cấu hình @SpringBootTest khi vừa gửi vừa đọc

Với Spring Boot integration test:

- Khởi động SMTP/IMAP test server trước khi Spring context resolve properties.
- Override `spring.mail.host/port` cho JavaMailSender.
- Override `app.mail.incoming.host/port` cho inbox reader.
- Dùng credential test, không dùng secret production.
- Gọi application use case gửi mail.
- Chờ test server nhận với deadline.
- Gọi reader bean dùng Jakarta Mail Store.
- Assert metadata/body hoặc UID theo yêu cầu.
- Dọn mailbox/test server và application state sau test.

`@DynamicPropertySource` có thể cung cấp port động vào context theo cách phù hợp phiên bản Spring Test.

Cần phân biệt ba loại assertion:

| Assertion | Bằng chứng |
| --- | --- |
| Mock sender được gọi | Application cố gắng gửi |
| GreenMail `getReceivedMessages()` có mail | SMTP test server capture được message |
| IMAP Store đọc được message | Mailbox test có thể truy xuất qua IMAP |

Nếu project chỉ kiểm thử JavaMailSender, thường không cần khởi động IMAP. Chỉ mở rộng sang IMAP khi bài test muốn bao phủ hành vi nhận/đọc thật sự.

## 38. Kiểm thử dữ liệu và tình huống biên cho inbound

Một bộ test dành cho reader nên bao gồm:

1. Inbox trống.
2. Một message plain text.
3. HTML-only và multipart/alternative.
4. Subject tiếng Việt và các charset khác.
5. Message không có From/Message-ID.
6. Nhiều From/To recipients.
7. Attachment lớn hơn giới hạn.
8. Filename chứa path traversal.
9. Nested multipart quá sâu.
10. Duplicate message cùng Message-ID.
11. Cùng UID được poll lại hai lần.
12. UIDVALIDITY thay đổi.
13. Message bị expunge khi đang đọc.
14. IMAP connection bị đóng giữa batch.
15. Unread flag thay đổi do client khác.
16. Crash sau business processing trước khi mark processed.
17. OAuth token hết hạn hoặc quyền IMAP bị thu hồi.
18. Multi-tenant account isolation.
19. Backpressure khi downstream chậm.
20. Không log raw body hoặc secret.

Với test integration, có thể dùng GreenMail hoặc server giả lập phù hợp. Các lỗi protocol cụ thể như mất kết nối đúng thời điểm hoặc UIDVALIDITY reset có thể cần stub/proxy hoặc test fixture chuyên dụng.

## 39. Hướng lựa chọn cho ứng dụng thực tế

Chọn thiết kế theo mục tiêu:

| Nhu cầu | Giải pháp phù hợp | Lưu ý |
| --- | --- | --- |
| Chỉ gửi transactional mail | `JavaMailSender` + SMTP provider | Outbox/retry nếu quan trọng |
| Gửi HTML/attachment | `JavaMailSender` + `MimeMessageHelper` | Kích thước và repeatable resources |
| Đọc vài thư trong một mailbox | Jakarta Mail `Store`/`Folder` | Resource lifecycle, UID và TLS |
| Đồng bộ Inbox liên tục | IMAP worker hoặc Spring Integration Mail | UID checkpoint, reconnect, dedup |
| Chỉ tải mail từ mailbox đơn giản | POP3 nếu provider hỗ trợ | Giới hạn folder/flags |
| Nhận reply từ khách hàng | Inbound mailbox hoặc provider inbound webhook | Routing, validation, security |
| Nhận bounce/delivery status | Provider events/DSN | Submission khác delivery |
| Xem Sent folder | IMAP Store + folder tương ứng | SMTP không tự bảo đảm Sent copy |
| Hệ thống lớn nhiều mailboxes | Inbound service/workers chuyên biệt | Isolation, quota và backpressure |
| Test SMTP mail đã gửi | GreenMail/Mailpit SMTP capture | Không cần IMAP nếu chỉ test sender |
| Test cả gửi và đọc | GreenMail SMTP + IMAP | Kiểm tra hai giao thức thực |

Không cần thêm IMAP nếu hệ thống chỉ gửi. Việc cấp quyền đọc mailbox chỉ để xác minh sender “đã gửi thành công” thường tạo thêm quyền truy cập nhạy cảm và không chứng minh delivery cho những hộp thư khác.

## 40. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Gọi `JavaMailSender.receive()` | API không có hợp đồng đọc thư | Dùng Store/Folder hoặc inbound adapter |
| Dùng SMTP host/port 587 để mở Inbox | Sai giao thức | Dùng IMAP/POP3 endpoint |
| Dùng `spring.mail.*` và nghĩ Spring tự poll Inbox | Auto-config chủ yếu cho outbound | Cấu hình inbound riêng |
| Coi `MimeMessage` là một mailbox connection | Nó là object biểu diễn MIME | Phân biệt Message và Store |
| Coi `send()` thành công là delivered | Relay chỉ xác nhận submission | Theo dõi provider events |
| Coi có thư ở Sent là recipient đã nhận | Sent là bản lưu phía sender | Phân biệt sent copy và delivery |
| Đọc Inbox người khác không có quyền | Vấn đề bảo mật/quyền riêng tư | Chỉ truy cập mailbox được cấp quyền |
| Dùng Message-ID làm dedup key duy nhất | Có thể trùng/thiếu/giả | UIDVALIDITY + UID + business key |
| Dùng IMAP message number làm checkpoint | Sequence thay đổi khi expunge | Dùng UID |
| Chỉ xử lý UNSEEN | Flag không phải processing status | Durable ledger |
| Mark SEEN trước khi lưu business result | Có thể bỏ sót sau crash | Persist before ack/flag |
| Cast mọi body sang String | Multipart gây lỗi | Parse MIME tree |
| Load mọi attachment vào RAM | Có thể OOM | Bounded streaming |
| Tin tuyệt đối From/filename/HTML | Dữ liệu từ bên ngoài | Validate và sanitize |
| Dùng một Store/Folder cho mọi tenant | Isolation/concurrency rủi ro | Scope từng account |
| Bật IMAP plaintext trên production | Lộ credential/nội dung | TLS và hostname validation |
| Không đóng Store/Folder | Rò socket/connection | Lifecycle/finally |
| Dùng SMTP test capture như bằng chứng IMAP | Hai API khác nhau | Test Store/Folder riêng |
| IMAP IDLE được xem là durable queue | Connection có thể ngắt | Reconcile UID và checkpoint |

## 41. Một checklist triển khai theo hướng kiến trúc

Trước khi xây hệ thống, trả lời:

- Ứng dụng chỉ cần gửi hay còn cần đọc/nhận?
- Người sở hữu mailbox có cấp quyền đọc hợp lệ không?
- Provider cung cấp IMAP/POP3, inbound API hay webhook?
- Nếu dùng IMAP, có cần folders, flags, UID và IDLE?
- Mailbox có lớn không? Batch size và checkpoint là gì?
- Có xử lý attachment hoặc HTML từ bên ngoài không?
- Giới hạn size/nesting/scan malware đã có chưa?
- Incoming message sẽ kích hoạt nghiệp vụ gì và idempotency key nào?
- Store/Folder lifecycle, reconnect, retry và timeout được quản lý ra sao?
- Có nhiều tenant/mailboxes với secret và quota khác nhau không?
- Outgoing submission state có được tách khỏi incoming processing state không?
- Có monitoring về poll lag, UID checkpoint và parse failures không?
- Test có dùng local SMTP/IMAP server thay cho hộp thư production không?

Nếu nhu cầu chỉ gửi xác nhận đơn hàng, nên giữ kiến trúc đơn giản với JavaMailSender và outbox nếu cần. Nếu cần xử lý replies, bounces hoặc inbound tickets, bổ sung đường nhận có ranh giới và quyền truy cập rõ ràng.

## 42. Ghi nhớ

- **JavaMailSender là API gửi mail**, không phải API mở Inbox.
- `MailSender` hỗ trợ `SimpleMailMessage`; `JavaMailSender` hỗ trợ thêm MIME.
- Spring Boot `spring.mail.*` cấu hình SMTP sender, không tự tạo IMAP receiver.
- SMTP dùng để submit/relay; IMAP/POP3 dùng để đọc mailbox.
- Jakarta Mail `Session`, `Store`, `Folder` và `Message` là các thành phần chính khi đọc thư.
- `MimeMessage` biểu diễn nội dung; nó không tự quyết định giao thức gửi hay đọc.
- Dùng `imaps`/port 993 hoặc chế độ TLS phù hợp provider khi đọc production mailbox.
- Cần đóng `Folder` và `Store` để giải phóng connection.
- Dùng UID và UIDVALIDITY cho IMAP checkpoint, không dùng message sequence number lâu dài.
- Message-ID hữu ích cho correlation nhưng không phải dedup key tuyệt đối.
- `UNSEEN` không tương đương “chưa xử lý”; cần durable processing ledger.
- MIME inbound có thể multipart, HTML và attachment; luôn parse có giới hạn và bảo vệ dữ liệu.
- Header From, filename và body nhận được là dữ liệu không tin cậy.
- SMTP submission success không chứng minh Inbox delivery hay người nhận đọc thư.
- SMTP gửi thành công không tự bảo đảm Sent folder có bản sao.
- Reply-To chỉ định hướng thư phản hồi; không tự làm ứng dụng nhận mail.
- Spring Integration Mail có thể giúp tổ chức inbound adapters/pollers nhưng là module riêng.
- GreenMail có thể test SMTP capture, và nếu bật IMAP có thể test Store/Folder thực sự.
- Hệ thống gửi và đọc hai chiều nên có adapters, credentials, trạng thái và metrics riêng.

**Nguyên tắc cốt lõi:** Trong Spring Framework Mail, hãy dùng **`JavaMailSender` để gửi** và dùng **Jakarta Mail `Store`/`Folder` hoặc một inbound integration chuyên dụng để đọc**. Dù hai chiều có thể cùng thao tác với `MimeMessage`, chúng khác nhau về giao thức, quyền truy cập, durability và cách xử lý lỗi. Phân định rạch ròi từ đầu sẽ giúp ứng dụng tránh nhầm lẫn “đã gửi” với “đã nhận”, quản lý mailbox an toàn và xây các workflow inbound/outbound có thể kiểm thử, vận hành và mở rộng độc lập.
