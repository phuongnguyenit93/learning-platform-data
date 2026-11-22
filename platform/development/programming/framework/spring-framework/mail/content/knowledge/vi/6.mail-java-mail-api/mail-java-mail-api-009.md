# Gửi nhiều message và tái sử dụng sender

## 1. Bài toán gửi nhiều email trong Spring Framework Mail

Ứng dụng Spring Boot có thể cần gửi một email xác nhận đơn hàng, hàng trăm thông báo kết quả hoặc một đợt thông báo theo lịch. Nếu tạo cấu hình SMTP và kết nối mới cho **từng** email, ứng dụng tốn thời gian bắt tay TCP/TLS, xác thực SMTP và nhiều chi phí kết nối. Nếu gom tất cả vào một lệnh gửi rất lớn, ứng dụng lại có thể gặp giới hạn tốc độ, áp lực bộ nhớ và khó xử lý khi chỉ một số thư thất bại.

Trong **Spring Framework Mail**, cần phân biệt hai cách tối ưu:

1. **Tái sử dụng JavaMailSender**: các service dùng chung một Spring bean sender đã được cấu hình.
2. **Gửi nhiều message trong một lời gọi**: truyền mảng hoặc varargs đến phương thức send để thư viện có cơ hội tái sử dụng kết nối SMTP trong batch.

Tái sử dụng **sender object** không đồng nghĩa giữ một **SMTP connection** mở mãi. Ngược lại, batch nhiều message có thể tiết kiệm kết nối mà không cần ứng dụng tự quản lý Transport.

~~~text
Nghiệp vụ / tác vụ lập lịch / worker
                   |
                   v
          Spring Mail service
                   |
          Danh sách thông điệp
                   |
                   v
       JavaMailSender (Spring bean)
                   |
           send(message[])
                   |
                   v
        Jakarta Mail SMTP Transport
          |         |         |
         msg 1     msg 2     msg 3
          |         |         |
          +---------+---------+
                    |
               SMTP server
                    |
               SMTP queue / relay
                    |
           Các máy chủ người nhận
~~~

Spring Mail đóng vai trò **SMTP client** của ứng dụng. Nó không tự cung cấp hàng đợi bền vững chỉ nhờ gửi nhiều message, và việc lời gọi send thành công không phải bằng chứng người nhận đã mở email.

## 2. Các overload gửi một hoặc nhiều message

**JavaMailSender** mở rộng giao diện **MailSender** và hỗ trợ thông điệp MIME qua Jakarta Mail.

| API | Loại dữ liệu | Khi nào dùng? |
|---|---|---|
| **send(SimpleMailMessage message)** | Một thư văn bản đơn giản | Thông báo chỉ có text |
| **send(SimpleMailMessage... messages)** | Nhiều thư văn bản đơn giản | Gửi batch thông báo text |
| **send(MimeMessage message)** | Một thông điệp MIME đã tạo | Email có HTML, attachment, inline image |
| **send(MimeMessage... messages)** | Mảng thông điệp MIME | Gửi nhiều MIME message đã dựng |
| **send(MimeMessagePreparator preparator)** | Callback chuẩn bị một MIME message | Tách tạo MIME khỏi thao tác gửi |
| **send(MimeMessagePreparator... preparators)** | Nhiều callback chuẩn bị MIME | Dựng và gửi nhiều thông điệp qua callbacks |

Các cách gọi tương ứng:

~~~java
mailSender.send(firstSimpleMessage);
mailSender.send(firstSimpleMessage, secondSimpleMessage);

mailSender.send(firstMimeMessage);
mailSender.send(new MimeMessage[] {
        firstMimeMessage, secondMimeMessage
});

mailSender.send(firstPreparator, secondPreparator);
~~~

Các overload cùng tên có kiểu tham số khác nhau, do đó cần khai báo rõ kiểu biến khi muốn tránh nhầm lẫn giữa SimpleMailMessage, MimeMessage và MimeMessagePreparator.

### Nhiều người nhận trong một message khác với nhiều message

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("alice@example.net", "bob@example.net");
message.setSubject("Shared announcement");
message.setText("A shared message.");
mailSender.send(message);
~~~

Đây là **một message có hai người nhận**. Mặt khác:

~~~java
SimpleMailMessage alice = new SimpleMailMessage();
alice.setTo("alice@example.net");
alice.setSubject("Hello Alice");
alice.setText("A message for Alice.");

SimpleMailMessage bob = new SimpleMailMessage();
bob.setTo("bob@example.net");
bob.setSubject("Hello Bob");
bob.setText("A message for Bob.");

mailSender.send(alice, bob);
~~~

Đây là **hai message độc lập**. Chúng có thể được cá nhân hóa, theo dõi kết quả riêng và tránh để lộ địa chỉ của người nhận khác. Không nên thay gửi các email riêng bằng cách thêm mọi người vào To/CC khi nội dung hoặc yêu cầu riêng tư khác nhau.

## 3. Gửi nhiều SimpleMailMessage trong một lần gọi

Với thông báo text, có thể tạo mảng các đối tượng **SimpleMailMessage** rồi gửi cùng nhau:

~~~java
import java.util.List;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TextNotificationService {
    private final JavaMailSender mailSender;

    public TextNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotifications(List<Notice> notices) {
        SimpleMailMessage[] messages =
                new SimpleMailMessage[notices.size()];

        for (int i = 0; i < notices.size(); i++) {
            Notice notice = notices.get(i);
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom("notifications@example.com");
            message.setTo(notice.recipient());
            message.setSubject("Account notification");
            message.setText(notice.body());
            messages[i] = message;
        }

        mailSender.send(messages);
    }

    public record Notice(String recipient, String body) {
    }
}
~~~

Mỗi vòng lặp tạo **một SimpleMailMessage mới**. Không nên tái sử dụng cùng một mutable message rồi thêm nhiều reference của nó vào array:

~~~java
// Sai về ý định: cả hai phần tử đều tham chiếu cùng object.
SimpleMailMessage reused = new SimpleMailMessage();
SimpleMailMessage[] wrong = new SimpleMailMessage[2];

reused.setTo("alice@example.net");
wrong[0] = reused;
reused.setTo("bob@example.net");
wrong[1] = reused;

// wrong[0] và wrong[1] đều đang chứa recipient cuối cùng.
~~~

Nếu có nội dung chung, có thể dùng constructor sao chép:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("notifications@example.com");
template.setSubject("Status update");

SimpleMailMessage aliceMessage = new SimpleMailMessage(template);
aliceMessage.setTo("alice@example.net");
aliceMessage.setText("Hello Alice.");

SimpleMailMessage bobMessage = new SimpleMailMessage(template);
bobMessage.setTo("bob@example.net");
bobMessage.setText("Hello Bob.");

mailSender.send(aliceMessage, bobMessage);
~~~

Template được dùng như nguồn cấu hình, còn mỗi bản sao có nội dung độc lập. Không nên sửa template từ nhiều thread khi đang sử dụng để tạo batch.

## 4. Gửi nhiều MimeMessage có HTML hoặc attachment

Email HTML và attachment dùng **MimeMessage** và thường được hỗ trợ xây dựng bằng **MimeMessageHelper**. Mỗi email cần một MimeMessage riêng.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlNotificationService {
    private final JavaMailSender mailSender;

    public HtmlNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcomeMessages(List<Recipient> recipients)
            throws MessagingException {
        MimeMessage[] messages = new MimeMessage[recipients.size()];

        for (int i = 0; i < recipients.size(); i++) {
            Recipient recipient = recipients.get(i);
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());
            helper.setFrom("welcome@example.com");
            helper.setTo(recipient.email());
            helper.setSubject("Welcome!");
            helper.setText(
                    "<p>Welcome, " + escapeHtml(recipient.displayName())
                            + ".</p>",
                    true);

            messages[i] = message;
        }

        mailSender.send(messages);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

    public record Recipient(String email, String displayName) {
    }
}
~~~

Trong ví dụ, **false** trong constructor MimeMessageHelper nghĩa là không yêu cầu multipart cho body HTML đơn giản. Khi có attachment hoặc nhiều phần MIME cần thiết, có thể chọn chế độ multipart phù hợp.

Ví dụ một MIME message có attachment:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Monthly report");
helper.setText("Please find the attached report.");
helper.addAttachment(
        "report.pdf",
        new org.springframework.core.io.FileSystemResource(
                "/var/reports/report.pdf"));

mailSender.send(message);
~~~

Để gửi nhiều email có attachment, xây dựng từng MimeMessage và thêm vào mảng. Resource hoặc file nguồn phải còn đọc được trong quá trình Jakarta Mail serialize email. Nếu một lần gửi chứa rất nhiều file lớn, cần chú ý số resource đang mở, memory và thời gian I/O.

**MimeMessage là đối tượng mutable, không nên chia sẻ rồi sửa đồng thời giữa nhiều thread.** JavaMailSender có thể tái sử dụng làm thành phần gửi, còn nội dung message phải được tạo và quản lý riêng cho từng thao tác.

## 5. Dùng MimeMessagePreparator cho nhiều thông điệp

**MimeMessagePreparator** là callback cấu hình MimeMessage do sender cung cấp. Cách này giúp tách logic dựng nội dung khỏi thao tác gửi.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class ReminderMailService {
    private final JavaMailSender mailSender;

    public ReminderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReminders(List<Reminder> reminders) {
        MimeMessagePreparator[] preparators = reminders.stream()
                .map(reminder -> (MimeMessagePreparator) mimeMessage -> {
                    MimeMessageHelper helper = new MimeMessageHelper(
                            mimeMessage,
                            false,
                            StandardCharsets.UTF_8.name());
                    helper.setFrom("reminders@example.com");
                    helper.setTo(reminder.recipient());
                    helper.setSubject("Upcoming deadline");
                    helper.setText(reminder.text(), false);
                })
                .toArray(MimeMessagePreparator[]::new);

        mailSender.send(preparators);
    }

    public record Reminder(String recipient, String text) {
    }
}
~~~

Ưu điểm: không phải gọi createMimeMessage trong code vòng lặp bên ngoài; callback làm việc với một message mới, dễ tổ chức nội dung MIME phức tạp; nhiều callback có thể được gom vào một lần send.

Tuy nhiên, **callback không phải job queue bền vững**. Nó chạy trong luồng gửi; nếu việc chuẩn bị message lỗi, Spring Mail có thể phát sinh **MailPreparationException**. Dữ liệu mà callback nắm giữ cũng cần ổn định cho tới khi callback chạy. Không dùng callback bắt reference đến một đối tượng mutable đang bị thay đổi bởi luồng khác.
## 6. Tái sử dụng JavaMailSender trong Spring container

Thông thường, ứng dụng cấu hình một **JavaMailSender** dưới dạng **Spring bean singleton**. Các service khác nhau dùng constructor injection để nhận cùng sender:

~~~text
                 Spring ApplicationContext
                            |
                   JavaMailSender bean
                     (SMTP config)
                       /        \
                      v          v
           InvoiceMailService   AlertMailService
                   |                 |
                   +--------+--------+
                            |
                 Cùng một sender bean
~~~

Ví dụ cấu hình Spring Boot với SMTP submission và STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Ở đây Spring Boot có thể tự cấu hình JavaMailSender khi có dependency mail và điều kiện cấu hình thích hợp. Username/password lấy từ môi trường hoặc secret store; không ghi credential thật vào source code. Các timeout tính bằng **mili giây** và cần lựa chọn phù hợp hạ tầng thực tế.

Hai service độc lập có thể cùng nhận sender đã được tiêm:

~~~java
@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
    // Phương thức gửi hóa đơn...
}

@Service
public class AlertMailService {
    private final JavaMailSender mailSender;

    public AlertMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
    // Phương thức gửi cảnh báo...
}
~~~

Cả hai không cần lặp lại logic khởi tạo Session, hostname, username hay TLS. Cấu hình sender được đặt ở **một nguồn nhất quán**, dễ giám sát và thay đổi.

### Có thể tái sử dụng sender giữa nhiều thread không?

**JavaMailSenderImpl** thường được dùng như một service singleton có cấu hình cố định và được gọi từ nhiều request/worker. Tuy nhiên, điều đó không có nghĩa mọi thành phần phía dưới đều thread-safe nếu ứng dụng tự thao tác hoặc sửa chúng. Khi chạy đồng thời:

- **Không gọi setHost, setUsername, setPassword hoặc sửa JavaMailProperties** của cùng JavaMailSenderImpl trong lúc các thread khác đang gửi.
- **Không chia sẻ một MimeMessage hoặc SimpleMailMessage mutable** giữa các thao tác gửi có nội dung khác nhau.
- **Không chia sẻ một SMTP Transport đang mở** để nhiều thread cùng gọi sendMessage thủ công mà không có thiết kế đồng bộ và vòng đời được kiểm chứng.
- **Không giả định singleton sender tạo ra một khóa toàn cục** hay tự giới hạn số kết nối đồng thời. Giới hạn concurrency phải được quản lý theo năng lực hạ tầng SMTP.

Nếu ứng dụng cần nhiều tài khoản hoặc nhiều SMTP provider, hãy tạo những sender **được cấu hình độc lập** và chọn đúng sender cho từng công việc. Tránh đổi username/password của một singleton theo từng người nhận vì dễ gây race condition, nhầm quyền gửi và lộ credential giữa các request.

### Tái sử dụng bean không có nghĩa giữ TCP connection mãi

**JavaMailSenderImpl** dùng **Jakarta Mail Session** và **Transport** để thực thi SMTP. Trong đường gửi thông thường, implementation có thể dùng lại một Transport cho nhiều message **trong cùng lời gọi send(array)**, nếu kết nối còn hợp lệ. Khi phương thức kết thúc, Transport thông thường được đóng. Các lời gọi send độc lập không mặc nhiên chia sẻ socket SMTP đang mở.

~~~text
Singleton JavaMailSenderImpl
         |
         +-- send(batch A) --> SMTP connection A --> đóng sau lời gọi
         |
         +-- send(batch B) --> SMTP connection B --> đóng sau lời gọi
         |
         +-- send(single)  --> SMTP connection C --> đóng sau lời gọi
~~~

Đây là mô hình khái niệm cho triển khai SMTP thường gặp. Khi server ngắt kết nối giữa batch hoặc gặp lỗi, client có thể cần kết nối lại. Số lần mở socket thực tế phụ thuộc implementation, transport và server. **Tái sử dụng JavaMailSender** chủ yếu là tái sử dụng thành phần cấu hình và API; **gửi array** mới là cách tạo cơ hội tiết kiệm vòng kết nối bên trong một lần gửi.

## 7. Một lần send(array) có luôn tốt hơn gọi send() nhiều lần?

Hai cách:

~~~java
// Nhiều lời gọi độc lập.
for (SimpleMailMessage message : messages) {
    mailSender.send(message);
}

// Một lời gọi gửi batch.
mailSender.send(messages);
~~~

Với **JavaMailSenderImpl** và SMTP transport thông dụng, lời gọi batch thường hiệu quả hơn khi cần gửi nhiều thông điệp liên tiếp qua cùng máy chủ và danh tính xác thực, vì có thể giảm số lần thiết lập kết nối, TLS và SMTP AUTH. Nhưng mức cải thiện tùy thuộc network latency, tốc độ SMTP, chính sách hạn mức và sự ổn định của server.

So sánh khái niệm:

| Tiêu chí | Vòng lặp send(single) | Một send(array) |
|---|---|---|
| Số lời gọi API | N lần | 1 lần |
| Cơ hội dùng lại kết nối SMTP trong lời gọi | Thấp giữa các lời gọi độc lập | Có, tùy implementation và kết nối còn sống |
| Theo dõi trạng thái theo message | Có thể bắt lỗi riêng ở mỗi vòng | Cần xử lý lỗi một phần và tương quan message |
| Bộ nhớ trước khi gọi | Có thể dựng từng message | Thường giữ danh sách/array của batch |
| Kiểm soát nhịp gửi | Dễ thêm delay/backoff từng item | Nên chia batch và điều tiết ở lớp worker |
| Phù hợp | Ít thư, yêu cầu theo dõi từng thư chặt | Nhiều thư nhỏ, hạ tầng hỗ trợ gửi liên tiếp |

Batch lớn không đương nhiên tốt hơn: SMTP provider có thể giới hạn số thư/phút, số người nhận/ngày, số kết nối đồng thời, kích thước message hoặc số lần gửi liên tục trên một kết nối. Nếu tăng batch quá mức, thời gian giữ kết nối kéo dài, số byte trong bộ nhớ tăng, và việc khôi phục khi lỗi phức tạp hơn.

### Chia batch thành những nhóm có kích thước hợp lý

Thay vì tạo một mảng 100.000 MimeMessage, có thể xử lý các đợt có kích thước tối đa, ví dụ **50 message mỗi đợt**. Số 50 chỉ để minh họa; cần điều chỉnh theo throughput, giới hạn provider, memory và yêu cầu điều hành.

~~~java
import java.util.List;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class BatchMailSender {
    private final JavaMailSender sender;
    private final int batchSize;

    public BatchMailSender(JavaMailSender sender, int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be positive");
        }
        this.sender = sender;
        this.batchSize = batchSize;
    }

    public void submit(List<SimpleMailMessage> messages) {
        for (int start = 0; start < messages.size(); start += batchSize) {
            int end = Math.min(start + batchSize, messages.size());
            SimpleMailMessage[] batch = messages
                    .subList(start, end)
                    .toArray(SimpleMailMessage[]::new);

            sender.send(batch);
        }
    }
}
~~~

Ví dụ trên minh họa **cách chia mảng thành các lượt gửi**, không phải giải pháp production hoàn chỉnh. Nếu một batch thất bại và ngoại lệ thoát khỏi submit, các batch tiếp theo sẽ chưa được chạy; một số thư trong batch vừa lỗi vẫn có thể đã được server chấp nhận. Phải thêm lưu trạng thái, retry và chính sách điều tiết ở lớp nghiệp vụ nếu yêu cầu hệ thống là gửi hàng loạt đáng tin cậy.

Khi lượng dữ liệu rất lớn, tốt hơn là **đọc theo trang từ database/job store** rồi tạo message cho từng batch, thay vì nạp toàn bộ người nhận, template render và các attachment vào RAM cùng lúc.

## 8. Partial failure: một batch không phải giao dịch nguyên tử

Giả sử gửi ba email bằng một lời gọi:

~~~text
JavaMailSender.send([A, B, C])
      |
      +-- A: SMTP chấp nhận
      +-- B: SMTP từ chối
      +-- C: SMTP chấp nhận hoặc chưa thử
~~~

Batch gửi email **không phải một transaction ACID**. Nếu B lỗi, không thể giả định email A được rollback hay mọi người nhận đều thất bại. Ngược lại, nếu một kết nối bị mất giữa chừng, kết quả của C có thể chưa rõ. Việc gửi lại toàn bộ batch trong mọi tình huống có thể tạo thư trùng cho A.

**MailSendException** cung cấp phương thức **getFailedMessages()** trả về một map các đối tượng message bị báo lỗi và nguyên nhân tương ứng khi implementation có thể cung cấp thông tin. Các exception khác như **MailAuthenticationException** hoặc **MailPreparationException** có ngữ nghĩa khác. Không nên suy ra “mọi message không xuất hiện trong failedMessages đã tới Inbox”: thông tin đó chỉ phản ánh phạm vi xử lý mà transport quan sát được.

Ví dụ quan sát lỗi trong lời gọi batch:

~~~java
import java.util.Map;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class ObservableMailBatch {
    private final JavaMailSender mailSender;

    public ObservableMailBatch(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void submit(SimpleMailMessage[] batch) {
        try {
            mailSender.send(batch);
            // Ghi sự kiện SMTP_SUBMISSION_ACCEPTED cho batch.
            // Không ghi MAILBOX_DELIVERED chỉ vì send() return.
        } catch (MailAuthenticationException ex) {
            // Kiểm tra credential, quyền hoặc cấu hình SMTP AUTH.
            // Không retry gấp liên tục với cùng credential sai.
            throw ex;
        } catch (MailSendException ex) {
            Map<Object, Exception> failures = ex.getFailedMessages();
            // Liên kết từng key trong failures với ID nghiệp vụ.
            // Những message thiếu kết quả đáng tin cần trạng thái
            // UNKNOWN/REQUIRES_RECONCILIATION trước khi retry.
            recordTransportFailures(failures);
            throw ex;
        } catch (MailException ex) {
            // Ghi nhận lỗi submission ở cấp batch.
            throw ex;
        }
    }

    private void recordTransportFailures(
            Map<Object, Exception> failedMessages) {
        // Ví dụ minh họa: tích hợp hệ thống lưu sự kiện/monitoring.
        // Chỉ lưu định danh và mã lỗi đã được làm sạch,
        // tránh ghi toàn bộ nội dung thư hoặc credential.
    }
}
~~~

Trong hệ thống thật, cần liên kết **businessMailId**, **recipient** và đối tượng message bằng metadata/record do ứng dụng quản lý. Một trường hợp thất bại chuẩn bị MIME trước khi gọi transport không nhất thiết có kết quả từng message như lỗi chuyển giao SMTP. Nếu cần độ chính xác retry cao, hãy thiết kế trạng thái và ranh giới công việc theo **từng email**, không dựa duy nhất trên một boolean kết quả batch.

### SMTP accepted khác với delivered

Ngay cả khi mọi message trong batch được **send()** xử lý thành công, điều thường biết tại ứng dụng chỉ là SMTP submission server đã chấp nhận thông điệp tương ứng. Phía sau còn MTA queue, chuyển tiếp SMTP và phát thư vào mailbox. Các sự kiện phát cuối cùng có thể đến qua DSN, provider event/webhook hoặc log mail server, tùy hệ thống.

Một chuỗi trạng thái có thể thiết kế:

~~~text
PENDING
   |
   v
PREPARING
   |
   v
SUBMITTING
   +----> SUBMISSION_UNKNOWN (timeout hoặc mất phản hồi)
   |
   +----> SUBMISSION_FAILED (đã xác nhận từ chối)
   |
   v
SMTP_ACCEPTED
   |
   +----> DEFERRED / BOUNCED (thông tin phía hạ tầng)
   |
   v
DELIVERED_TO_KNOWN_BOUNDARY (chỉ khi có bằng chứng)
~~~

Tên trạng thái là gợi ý mô hình nghiệp vụ, không phải enum có sẵn của Spring Mail. Không phải SMTP provider nào cũng cung cấp đủ event để cập nhật tới kết quả phát vào mailbox.
## 9. Gửi bất đồng bộ: tái sử dụng sender cùng hàng đợi ứng dụng

Nếu một HTTP request gửi ngay hàng chục email, request có thể bị chậm bởi TLS handshake, SMTP server, mạng hoặc timeout. Việc chuyển công việc sang một worker giúp HTTP API phản hồi sớm và kiểm soát nhịp gửi tốt hơn.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Spring API
    participant D as Database / Outbox
    participant W as Mail Worker
    participant S as SMTP Server
    U->>A: Yêu cầu gửi nhiều email
    A->>D: Lưu request và các item PENDING
    D-->>A: Commit
    A-->>U: 202 Accepted + requestId
    W->>D: Claim một nhóm item
    W->>W: Tạo message độc lập cho từng item
    W->>S: JavaMailSender.send(batch)
    S-->>W: Xác nhận/ lỗi SMTP submission
    W->>D: Lưu kết quả từng item theo dữ liệu quan sát được
~~~

Có thể dùng hàng đợi nội bộ, broker, database queue hoặc **transactional outbox**. Chọn cách nào tùy nhu cầu bền vững, khả năng phục hồi và hệ thống hiện có. **@Async** cũng có thể chuyển lời gọi sang thread pool, nhưng bản thân nó **không cung cấp hàng đợi bền vững qua restart**, không giải quyết giao dịch database–SMTP và không tự theo dõi được kết quả delivery.

### Vì sao transactional outbox hữu ích?

Ví dụ khi đơn hàng vừa được xác nhận, ứng dụng cần vừa lưu trạng thái đơn hàng, vừa tạo yêu cầu gửi email. Nếu gọi SMTP trong cùng transaction và SMTP chấp nhận thư trước khi transaction bị rollback, khách hàng có thể nhận email về đơn hàng chưa được lưu. Nếu chỉ commit database trước rồi mới gửi, ứng dụng có thể crash ở khoảng trống giữa hai bước.

Với outbox, **thay đổi nghiệp vụ và bản ghi yêu cầu gửi** được lưu trong cùng transaction database. Sau commit, worker đọc bản ghi và gọi JavaMailSender. Cách này giảm mất job do crash, nhưng không tự bảo đảm gửi exactly-once:

~~~text
Worker gọi SMTP
       |
       v
SMTP trả 250 accepted
       |
       v
Worker crash trước khi đánh dấu trạng thái trong DB
       |
       v
Worker chạy lại và có thể gửi cùng email lần nữa
~~~

Vì vậy cần có **businessMailId**, các trạng thái theo từng item, retry có giới hạn, cơ chế khôi phục công việc bị giữ quá lâu và chiến lược xử lý trùng phù hợp với nghiệp vụ. Một Message-ID được gắn trong MIME có thể giúp truy vết, nhưng không bắt buộc SMTP server tự phát hiện trùng dựa trên ID đó.

### Có nên tự động retry cả batch?

Không nên mặc định cứ gặp một MailException là gửi lại toàn bộ batch. Một số message có thể đã được SMTP server chấp nhận trước lỗi. Đặc biệt, mất kết nối sau khi client truyền hết DATA nhưng trước khi nhận được phản hồi có thể tạo trạng thái **không chắc đã nhận hay chưa nhận**. Retry mù có nguy cơ gửi hai thư.

Một workflow phù hợp là ghi nhận trạng thái riêng theo item, xác định phần đã bị từ chối rõ ràng, phần chờ retry và phần cần đối soát. Nếu provider có idempotency key hoặc event ID, dùng chúng theo đúng phạm vi đảm bảo trong tài liệu provider; SMTP chuẩn không cung cấp đảm bảo exactly-once xuyên suốt.

## 10. Kiểm soát concurrency, throughput và giới hạn SMTP

Gửi batch không có nghĩa nên tăng số lượng thread vô hạn. Hạ tầng SMTP thường có giới hạn số kết nối đồng thời, số email mỗi khoảng thời gian, số người nhận, tổng dung lượng và đôi khi giới hạn riêng theo tài khoản.

Những biến số nên theo dõi và điều chỉnh:

| Tham số | Khi quá thấp | Khi quá cao |
|---|---|---|
| **batchSize** | Mở kết nối nhiều lần, overhead cao | Gửi một lần lâu, tốn RAM, khó phục hồi lỗi từng item |
| **workerConcurrency** | Queue tăng nhanh khi tải lớn | Quá nhiều kết nối SMTP, bị throttle hoặc tốn tài nguyên |
| **rateLimit** | Thông báo bị chậm | Bị SMTP server trả 4xx/5xx hoặc chặn chính sách |
| **connectionTimeout** | Dễ lỗi khi mạng chậm hợp lệ | Thread có thể chờ quá lâu |
| **socketReadTimeout** | Dễ timeout với SMTP server chậm | Thời gian bị treo của job tăng |
| **retryBackoff** | Retry quá dồn dập, làm nặng server | Thời gian hoàn tất email kéo dài |

Không có một số **batchSize** tối ưu chung cho mọi SMTP server. Có thể bắt đầu với batch nhỏ và worker concurrency thấp, rồi quan sát queue latency, thời gian gửi, tỷ lệ lỗi và giới hạn provider. Tăng batch hoặc worker chỉ khi số liệu cho thấy cải thiện.

### Điều tiết bằng worker pool

Ví dụ tổ chức:

~~~text
Database mail_outbox (nhiều item chờ gửi)
               |
        Claim có giới hạn
               |
       +-------+-------+
       |               |
    Worker 1        Worker 2
       |               |
    Batch A          Batch B
       |               |
       +-------+-------+
               |
     Shared JavaMailSender bean
               |
      SMTP submission server
~~~

Worker có thể cùng nhận một singleton JavaMailSender đã được cấu hình cố định, nhưng **mỗi worker tạo message riêng**. Worker count là một quyết định về mức độ gửi song song, không phải lời hứa sender tự bảo đảm giới hạn trên tổng socket đang dùng. Để tránh hai worker lấy cùng job, cơ chế claim tại database/broker phải được thiết kế cho xử lý đồng thời; mỗi item nên có identity và trạng thái lease/claim phù hợp.

Nếu nhà cung cấp trả lỗi tạm thời do quá tải như nhóm **4xx**, có thể giảm nhịp gửi và retry theo chính sách. Nếu tài khoản bị từ chối vì sai secret hoặc cấm relay, tăng retry chỉ làm hệ thống tệ hơn. Phân loại lỗi theo phản hồi cụ thể thay vì chỉ theo số lần gửi.

## 11. Khi cần nhiều SMTP account hoặc provider

Việc dùng lại **một** sender hợp lý khi các thư cùng đi qua một SMTP endpoint/tài khoản. Nhưng ứng dụng có thể có hai tuyến gửi:

- Thông báo giao dịch qua một dịch vụ gửi thư.
- Email nội bộ qua SMTP relay của tổ chức.

Khi đó có thể tạo **hai JavaMailSenderImpl bean riêng biệt** và dùng **@Qualifier** để chọn:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.mail.javamail.JavaMailSender;

@Service
public class TransactionalMailService {
    private final JavaMailSender transactionalSender;

    public TransactionalMailService(
            @Qualifier("transactionalSender") JavaMailSender sender) {
        this.transactionalSender = sender;
    }
    // Các message nghiệp vụ dùng transactionalSender.
}
~~~

Trong trường hợp này, bean có tên **transactionalSender** phải được cấu hình riêng trong Spring context, ví dụ bằng một phương thức **@Bean** xây dựng JavaMailSenderImpl với hostname, tài khoản, TLS và timeout của tuyến tương ứng. Các giá trị được cung cấp từ cấu hình/secret management.

**Không đổi mật khẩu, hostname hay property của một singleton JavaMailSenderImpl ngay trước mỗi lời gọi** để dùng các tài khoản khác nhau. Cách đó dễ gây race condition khi các thread đồng thời gửi và có thể gửi sai tài khoản. Tái sử dụng sender chỉ nên diễn ra **trong phạm vi một cấu hình SMTP nhất quán**.

### Tái sử dụng nội dung chung khác với tái sử dụng SMTP sender

Một template email chung không nhất thiết là MimeMessage đã dựng sẵn. Có thể dùng một DTO hoặc template engine để sinh **subject, text, HTML** cho từng recipient, rồi tạo mỗi MimeMessage mới từ đầu. Làm như vậy giúp kiểm soát personalization, Message-ID, attachment, địa chỉ nhận và header riêng của từng thông điệp. Sử dụng chung dữ liệu template an toàn hơn sử dụng chung một đối tượng MimeMessage mutable.

## 12. Các lỗi thiết kế thường gặp

**Tạo JavaMailSenderImpl mới trong mỗi request.** Điều này làm lặp lại cấu hình và khó quản lý bảo mật, timeout, metric, routing. Khi ứng dụng có cùng SMTP endpoint, nên dùng bean cấu hình ổn định được inject vào service.

**Tưởng singleton sender giữ socket SMTP vĩnh viễn.** Spring bean thường sống suốt ứng dụng, nhưng Transport của Jakarta Mail có vòng đời kết nối riêng. Batch varargs thường tạo điều kiện dùng lại kết nối trong lời gọi; không được giả định các lời gọi độc lập dùng một socket mở mãi.

**Tái sử dụng một SimpleMailMessage cho nhiều recipient.** Vì đối tượng mutable, một array chứa nhiều reference tới cùng message có thể khiến mọi phần tử mang địa chỉ/body cuối cùng. Phải tạo message riêng hoặc sao chép từ template cố định.

**Chia sẻ MimeMessage giữa nhiều thread.** MimeMessage đang được chỉnh sửa không phải đối tượng nội dung bất biến. Tạo mới cho từng thư và tránh sửa sau khi đã giao gửi.

**Gửi một message đến nhiều người để thay cho batch cá nhân hóa.** Điều này có thể làm lộ người nhận qua To/CC và không hỗ trợ subject/body riêng. Chọn mô hình theo yêu cầu dữ liệu và quyền riêng tư.

**Cho rằng send(batch) là giao dịch nguyên tử.** Một số thư có thể đã được chấp nhận trước khi một thư khác lỗi. Không rollback SMTP bằng cách ném exception trong Java; phải lưu trạng thái theo item và đối soát.

**Retry nguyên batch khi timeout.** Nếu phản hồi sau DATA bị mất, server có thể đã lưu thư. Retry vô điều kiện dễ gây gửi trùng; cần phân biệt lỗi được xác nhận với trạng thái không chắc chắn.

**Giữ toàn bộ attachment của hàng nghìn email trong RAM.** Điều này tăng heap, làm GC nặng và dễ hết tài nguyên. Chia batch, dùng resource phù hợp và đọc job theo trang.

**Bật nhiều worker để “đẩy nhanh” mà không đo provider quota.** SMTP provider có thể throttle, từ chối hoặc khóa luồng gửi; worker concurrency và rate limit cần phối hợp.

**Chỉ log “mail sent” cho cả batch.** Khi một vài message lỗi, log tổng không giải thích được message nào cần đối soát. Dùng request ID, recipient/job ID và sự kiện theo từng giai đoạn, tránh log body và credential.

## 13. Quan sát hiệu năng và khả năng gửi thành công

Một hệ thống gửi nhiều message nên đo không chỉ số lần gọi JavaMailSender mà còn:

| Chỉ số | Ý nghĩa |
|---|---|
| **messagesPrepared** | Bao nhiêu message đã dựng nội dung xong |
| **messagesSubmitted** | Bao nhiêu message đã được gửi thử đến transport |
| **smtpAccepted** | Bao nhiêu message có bằng chứng submission server chấp nhận |
| **submissionUnknown** | Bao nhiêu message chưa xác định được kết quả do timeout/mất kết nối |
| **batchDuration** | Thời gian xử lý một lần send(array) |
| **queueDepth** | Số job đang chờ tại ứng dụng |
| **oldestJobAge** | Độ trễ của công việc lâu nhất chưa xử lý |
| **retryCount** | Số lần thử lại của từng item |
| **providerResponseClass** | Tỷ lệ lỗi tạm thời/vĩnh viễn theo SMTP response |

Có thể gắn **businessMailId** cho mỗi yêu cầu gửi và lưu thêm provider message ID hoặc queue ID nếu hạ tầng trả về. **Message-ID** trong MIME hữu ích để tương quan nhưng không bắt buộc duy nhất xuyên toàn bộ các hệ thống; cùng một email có thể mang queue ID khác nhau khi qua các MTA.

Để quan sát chậm, cần phân tách các đoạn thời gian: thời gian chờ job, dựng template/MIME, kết nối TLS/AUTH, gửi từng message và nhận phản hồi SMTP. Một số SMTP provider còn tiếp tục xử lý thông điệp trong queue sau khi client đã nhận kết quả success. Không đo gộp tất cả thành “email delivered time” nếu chỉ có dữ liệu submission.

Khi benchmark, nên dùng SMTP test server hoặc tài khoản test được phép, với số lượng và nội dung phù hợp. Các phép đo tốt nhất tập trung vào **số kết nối, thời gian batch và tỷ lệ lỗi** trong điều kiện có kiểm soát. Những số liệu ấy là căn cứ để chọn batchSize và concurrency; không có công thức cố định tối ưu cho mọi tổ chức.

## 14. Chọn cách triển khai phù hợp với khối lượng gửi

| Nhu cầu | Cách tổ chức thường phù hợp |
|---|---|
| Một thông báo text ngắn | Gửi một SimpleMailMessage |
| Vài chục thông báo text có người nhận riêng | Tạo mảng SimpleMailMessage và gọi send(array) |
| Nhiều thông báo HTML hoặc có attachment | Tạo MimeMessage riêng cho mỗi email hoặc dùng MimeMessagePreparator |
| Nhiều đợt email trong cùng ứng dụng | Inject JavaMailSender singleton được cấu hình cố định |
| Hàng nghìn email và cần phục hồi sau restart | Database/broker/outbox + worker + batch nhỏ + trạng thái theo từng item |
| Nhiều SMTP provider hoặc tài khoản | Nhiều sender bean cấu hình riêng và định tuyến rõ ràng |
| Theo dõi kết quả thực tế đến miền/mailbox | Kết hợp event/DSN/provider webhook thay vì chỉ dựa vào send() |

Trong Spring Framework Mail, **tái sử dụng sender** giúp tập trung cấu hình và giảm khởi tạo thành phần; **gửi nhiều message bằng overload varargs** giúp tối ưu công đoạn SMTP trong phạm vi một batch. Hai kỹ thuật nên đi cùng **tạo message độc lập, chia batch có kiểm soát, lưu trạng thái từng thư và xử lý partial failure**.

Hãy luôn hiểu đúng ranh giới trách nhiệm: **send() thành công phản ánh việc gửi qua SMTP submission ở mức transport**, còn đưa thư vào mailbox, vào Inbox hay người nhận đã đọc là các bước phía sau cần bằng chứng riêng.
