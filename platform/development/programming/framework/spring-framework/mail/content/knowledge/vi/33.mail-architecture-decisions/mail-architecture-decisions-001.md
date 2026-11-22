# Chọn gửi trực tiếp hay qua queue

## 1. Bài toán quyết định kiến trúc

Trong ứng dụng **Spring Framework Mail**, việc gọi **JavaMailSender.send(...)** để gửi một email là tương đối đơn giản. Quyết định khó hơn nằm ở chỗ **nên gọi phương thức gửi ngay trên luồng xử lý nghiệp vụ, hay đưa yêu cầu gửi vào queue để một worker xử lý sau**.

Ví dụ khi khách hàng đặt hàng:

~~~text
HTTP POST /orders
      |
      v
Create order
      |
      +-- Gửi email xác nhận ngay?
      |
      +-- Hay lưu một notification job để gửi sau?
~~~

Cả hai cách đều có thể hợp lý, nhưng sự khác biệt không chỉ là **đồng bộ** hay **bất đồng bộ**:

- Người dùng phải chờ SMTP bao lâu?
- Đơn hàng đã commit khi gửi mail hay chưa?
- Request thành công nhưng SMTP lỗi thì xử lý thế nào?
- SMTP accepted rồi ứng dụng crash thì có gửi trùng không?
- Khi provider ngừng hoạt động, yêu cầu nghiệp vụ có bị ảnh hưởng không?
- Email có thể trễ bao lâu trước khi mất giá trị?
- Hệ thống cần chứng minh email được tạo, thử gửi, được chấp nhận hoặc bị bỏ qua ra sao?
- Khi một chiến dịch tạo hàng trăm nghìn thư, các request giao dịch khác có bị nghẽn?
- Ai chịu trách nhiệm quản lý retry, quota, trạng thái, cảnh báo và chi phí vận hành?

**Chọn gửi trực tiếp hay qua queue là quyết định về ranh giới nghiệp vụ, độ tin cậy và vận hành**, không chỉ là chọn một annotation Spring.

Trong bài này, “**gửi trực tiếp**” chủ yếu là gọi SMTP transport ngay trong tiến trình đang phục vụ một request hoặc sự kiện. “**Qua queue**” là lưu một yêu cầu gửi vào một hàng đợi hoặc kho công việc rồi để worker độc lập thực hiện SMTP submission. Queue có thể được hiện thực bằng database, message broker hoặc dịch vụ job chuyên dụng.

## 2. Hai kiến trúc cơ bản

### A. Gửi trực tiếp trong request

~~~text
Client
  |
  v
Spring REST Controller
  |
  v
Business Service
  |
  +-- Save business data
  |
  +-- Build MimeMessage
  |
  +-- JavaMailSender.send(...)
  |       |
  |       v
  |   SMTP provider
  |
  v
HTTP response
~~~

**Đặc điểm:** kết quả từ phương thức gửi có thể được xử lý ngay để trả response, nhưng request phải gánh độ trễ kết nối mạng, TLS, SMTP DATA và rủi ro provider timeout.

### B. Gửi qua queue/worker

~~~text
Client
  |
  v
Spring REST Controller
  |
  v
Business Service
  |
  +-- Save business data
  |
  +-- Enqueue notification intent
  |
  v
HTTP response

          Queue / Durable outbox
                   |
                   v
              Mail Worker
                   |
                   v
            JavaMailSender
                   |
                   v
              SMTP provider
~~~

**Đặc điểm:** request không cần chờ SMTP, nhưng thành công của request **không có nghĩa thư đã được gửi**. Hệ thống phải quản lý trạng thái và kết quả của job bất đồng bộ.

Một biến thể production phổ biến là:

~~~text
Business transaction
    |
    +-- Update business entities
    +-- Insert email_outbox
    |
    v
Commit once
    |
    v
Outbox dispatcher -> Queue/broker -> Mail worker -> SMTP
~~~

Mục đích của outbox là bảo đảm **ý định gửi được lưu cùng giao dịch nghiệp vụ**, không phải bảo đảm SMTP chuyển phát exactly-once.

## 3. Bảng so sánh nhanh

| Tiêu chí | Gửi trực tiếp | Gửi qua queue |
|---|---|---|
| Độ phức tạp triển khai | Thấp nếu nhu cầu đơn giản | Cao hơn, có worker và trạng thái |
| HTTP latency | Phụ thuộc SMTP provider | Chủ yếu phụ thuộc bước enqueue |
| Cách hiển thị kết quả | Có thể biết SMTP submission outcome ngay | Ban đầu chỉ biết queued; cập nhật sau |
| Khi SMTP outage | Request có thể chậm hoặc lỗi | Có thể tiếp nhận intent và gửi lại |
| Retry qua process restart | Phải xây thêm persistence | Có thể bền vững nếu queue/outbox được cấu hình đúng |
| Peak traffic | Dễ tạo nhiều SMTP connections trên request threads | Có thể buffer và giới hạn dispatch |
| Rate limiting | Cần điều tiết ngay tại request path | Dễ phân phối quota/concurrency ở worker |
| Thứ tự/ưu tiên gửi | Phụ thuộc request arrival và threads | Có thể dùng priority/partition/worker pools |
| Quan sát lịch sử | Phải thêm logging/DB | Thường có job/attempt state |
| Trùng email | Vẫn có khi retry/timeout | Vẫn có khi retry/redelivery |
| Chi phí vận hành | Thường thấp ở quy mô nhỏ | Có broker/DB queue, DLQ, monitor, runbook |
| Phù hợp | Low-volume, chấp nhận phụ thuộc transport | Workload quan trọng, volume lớn, cần phục hồi |

**Queue không tự động tốt hơn nếu chỉ chuyển sang @Async hoặc một QueueChannel in-memory**. Hàng đợi phải được đánh giá theo durability, ownership, retry và semantics thừa nhận thông điệp.

## 4. Đừng đánh đồng HTTP thành công với email được giao

Có ít nhất bốn mốc:

~~~text
1. BUSINESS_COMMITTED
   -> Dữ liệu nghiệp vụ đã lưu thành công

2. QUEUED / OUTBOX_PERSISTED
   -> Ý định gửi đã được lưu để worker xử lý

3. SMTP_SUBMITTED / ACCEPTED
   -> SMTP endpoint/provider đã chấp nhận thông điệp

4. DELIVERY_CONFIRMED (theo provider)
   -> Provider ghi nhận delivery ở chặng họ quan sát
~~~

Người dùng có thể đọc email sau nhiều giây/phút, và thậm chí **SMTP accepted không bảo đảm thư vào primary inbox hay được người dùng mở**.

Ở phương án trực tiếp:

~~~java
mailSender.send(message);
~~~

trả về bình thường thường chỉ cho biết thao tác submission thành công theo transport contract. Điều đó **không phải bằng chứng người nhận đã thực sự đọc được thư**.

Ở phương án queue:

~~~text
HTTP 202 Accepted
{
  "notificationId": "N-100",
  "status": "QUEUED"
}
~~~

chỉ nên được hiểu là hệ thống đã **tiếp nhận yêu cầu gửi** theo mức bảo đảm cụ thể, không được diễn đạt “email đã gửi thành công”.

## 5. Các câu hỏi nên trả lời trước khi chọn

1. **Email có phải điều kiện bắt buộc để nghiệp vụ hoàn thành không?** Hay chỉ là thông báo sau khi nghiệp vụ đã thành công?
2. **Độ trễ tối đa người dùng chấp nhận là bao nhiêu?** Đặc biệt ở OTP, login link và cảnh báo bảo mật.
3. **Có được mất ý định gửi sau khi process crash không?**
4. **Khi SMTP outage, nghiệp vụ có được phép tiếp tục không?**
5. **Lưu lượng bình quân và peak là bao nhiêu?** Có chiến dịch burst hoặc retry storm không?
6. **Thư có deadline không?** Gửi sau thời hạn còn hữu ích không?
7. **Cần audit tới mức nào?** Có phải trả lời vì sao người nhận chưa nhận thư?
8. **Đã có broker hoặc database outbox infrastructure không?**
9. **Provider hỗ trợ API idempotency, webhook delivery, rate limits thế nào?**
10. **Đội vận hành có đủ khả năng giám sát backlog, DLQ, reconcile và sửa lỗi không?**

Không có một câu trả lời áp dụng cho mọi hệ thống. Một ứng dụng nhỏ gửi vài thư thử nghiệm mỗi ngày có lựa chọn khác một nền tảng SaaS nhiều tenant với hàng triệu notification.

## 6. Gửi trực tiếp phù hợp khi nào?

Gửi trực tiếp có thể là lựa chọn hợp lý nếu:

- Lưu lượng email thấp, tương đối đều và có giới hạn.
- Request có thể chịu độ trễ SMTP với timeout được cấu hình.
- Việc gửi không bắt buộc bền vững qua restart, hoặc ứng dụng đã có cách khôi phục ý định gửi.
- Email phục vụ một thao tác độc lập như **test mail configuration** của quản trị viên.
- Hành động “kiểm tra SMTP hiện có hoạt động không” thực sự cần phản hồi transport ngay.
- Không có yêu cầu SLA cao về throughput, rate control hoặc khả năng giải quyết backlog.
- Thất bại được hiển thị trung thực và người dùng có thể thực hiện lại một cách an toàn.

Ví dụ **Send Test Email**:

~~~text
Admin clicks "Test SMTP"
     |
     v
Spring API validates sender config
     |
     v
JavaMailSender.send(...)
     |
     +-- SMTP accepted -> show transport submission success
     |
     +-- Authentication/connection error -> show diagnostic
~~~

Ở đây nhu cầu chính là **xác định transport có hoạt động tại thời điểm test**. Gửi trực tiếp giúp phản hồi cụ thể hơn việc chỉ enqueue rồi nói “đã nhận yêu cầu”.

Tuy vậy cần rate limit, authorization, recipient allowlist và kiểm soát lạm dụng; endpoint thử SMTP không nên trở thành công cụ gửi mail hàng loạt.

## 7. Gửi trực tiếp không có nghĩa phải nằm trong transaction nghiệp vụ

Một anti-pattern:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(...);
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

Vấn đề:

- Transaction database giữ kết nối/lock trong khi chờ SMTP.
- Nếu SMTP accepted rồi transaction DB rollback, người dùng nhận thư về đơn hàng chưa tồn tại.
- Nếu SMTP thất bại, nghiệp vụ có thể rollback dù email chỉ là một thông báo phụ.
- Không có transaction nguyên tử giữa DB và SMTP; rollback DB **không thu hồi được email**.

Ngay cả nếu gọi send ở trong method annotated @Transactional, SMTP provider **không tham gia transaction JDBC**.

Nếu vẫn dùng gửi trực tiếp cho notification không quan trọng, hãy xác định rõ business commit boundary và xử lý lỗi. Khi yêu cầu không được mất notification sau commit, **transactional outbox** thường an toàn hơn chỉ gửi sau commit bằng callback trong bộ nhớ.

## 8. Gửi sau commit: tốt hơn nhưng vẫn có cửa sổ mất thư

Một kỹ thuật là phát event và xử lý:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreatedEvent event) {
    mailSender.send(...);
}
~~~

Điều này giúp tránh gửi mail nếu transaction nghiệp vụ rollback trước commit. Nhưng vẫn có các rủi ro:

- Process crash ngay **sau DB commit** nhưng **trước khi listener chạy**.
- Listener chạy nhưng SMTP lỗi không được persist để retry.
- Nếu listener đồng bộ, latency có thể vẫn nằm trên luồng hoàn tất transaction/request.
- Nếu thêm @Async, sự kiện có thể nằm trong hàng đợi thread nội bộ và mất khi process dừng.

**@TransactionalEventListener(AFTER_COMMIT) không phải transactional outbox bền vững.** Nó là cơ chế lifecycle event, không thay thế bảng ghi ý định gửi trong cùng transaction.

Nếu thiếu notification là chấp nhận được thì kỹ thuật này có thể đủ. Nếu notification cần được phục hồi sau crash, phải có durable intent.

## 9. Khi nào queue phù hợp hơn?

Queue hoặc durable outbox thường phù hợp khi:

- Email là một phần quan trọng của trải nghiệm hoặc quy trình kinh doanh.
- Nghiệp vụ vẫn cần trả HTTP nhanh khi provider SMTP chậm.
- Có lượng gửi lớn, burst traffic hoặc chiến dịch theo lịch.
- Cần retry/backoff, DLQ, suppression, unsubscribe hoặc quota theo tenant.
- Nhiều service phát sinh notification nhưng muốn dùng cùng một mail pipeline.
- Cần theo dõi trạng thái queued → processing → submitted → delivery feedback.
- Cần cô lập tác động của SMTP outage khỏi API chính.
- Có yêu cầu phục hồi những intent đã commit sau process restart.
- Muốn scale workers độc lập với HTTP instances.
- Có nhiều SMTP provider và cần kiểm soát failover.

Ví dụ:

~~~text
Order Service      Billing Service       Support Service
      |                  |                      |
      +------------------+----------------------+
                         |
                         v
                    Durable queue
                         |
                         v
                 Central Mail Workers
                         |
             +-----------+-----------+
             |                       |
             v                       v
        SMTP Provider A         SMTP Provider B
~~~

Kiến trúc này cho phép gom policy, template, bảo mật và observability. Nhưng cần quyết định liệu **một hàng đợi chung** có thể gây nghẽn những email thời gian thực khi campaign marketing lớn chạy hay không.

## 10. Queue còn nhiều loại: cần chọn đúng mức bảo đảm

| Cơ chế | Có bền vững qua restart không? | Những điểm cần hiểu |
|---|---|---|
| **@Async + TaskExecutor** | Không mặc định | Thread pool in-memory, không có durable retry |
| **BlockingQueue/ExecutorService** | Không | Mất dữ liệu khi JVM crash |
| **Spring Integration QueueChannel mặc định** | Không mặc định | Queue trong bộ nhớ nếu chưa cấu hình persistent store |
| **Database jobs/outbox** | Có sau commit | Cần atomic claim, indexes, retry, cleanup |
| **RabbitMQ durable queues + persistent messages** | Có thể, tùy cấu hình và confirms | Phải xét publisher confirms, consumer ACK, DLQ |
| **JMS durable/persistent messaging** | Có thể, theo broker/session configuration | Transaction/ack modes, reconnect, DLQ |
| **Kafka topic** | Có thể theo retention/acks/replication | Offset commits, duplicates, partition ordering |
| **Cloud task/queue service** | Theo service contract | Visibility timeout, delivery count, DLQ, quotas |

Các công cụ đều có thể giúp tách request khỏi sender, nhưng **durable queue không đồng nghĩa exactly-once side effect trên SMTP**.

Một kiến trúc tốt cần chỉ rõ: **lưu bền vững ở đâu, khi nào producer biết job đã được tiếp nhận, ai retry và khi nào coi công việc hoàn thành**.

## 11. Ví dụ Spring Boot gửi trực tiếp

Giả sử một API cho phép quản trị viên gửi thư kiểm tra cấu hình. Dependency tiêu biểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Cấu hình ví dụ qua environment/secret manager:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

**Port 587 với STARTTLS chỉ là ví dụ phổ biến**, phải dùng endpoint, TLS mode, authentication và chính sách provider thực tế. Những timeout trên là mili giây, không bảo đảm tổng thời gian gửi tối đa bằng tổng ba giá trị. Không log username/password hay SMTP protocol trace có token.

Service:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TestEmailService {

    private final JavaMailSender sender;

    public TestEmailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendTest(String approvedRecipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("system@example.com");
        message.setTo(approvedRecipient);
        message.setSubject("SMTP configuration test");
        message.setText("This is a transport configuration test.");

        try {
            sender.send(message);
        } catch (MailException exception) {
            // Phân loại lỗi theo cause/SMTP phase khi cần;
            // đừng giả định mọi exception đều chắc chắn chưa gửi.
            throw new TestEmailSubmissionException(exception);
        }
    }
}
~~~

**TestEmailSubmissionException** là exception do ứng dụng định nghĩa. Ví dụ tập trung vào direct submission, chưa gồm authorization, approvedRecipient validation, rate limit hoặc exception mapping cho HTTP.

Những điểm cần thể hiện ở API response:

- Nếu send hoàn thành: **SMTP submission accepted** theo contract.
- Nếu lỗi authentication/cấu hình: thể hiện lỗi phù hợp mà không lộ credential.
- Nếu timeout sau khi truyền DATA: kết quả có thể **mơ hồ**, không tự khẳng định email chưa gửi.
- Không cung cấp endpoint gửi mail cho địa chỉ tùy ý mà thiếu quyền và hạn mức.

## 12. Direct với MIME, HTML và attachment

Không phải mọi email chỉ có plain text. Với HTML và file:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendInvoiceDirectly(
        JavaMailSender sender,
        String recipient,
        byte[] pdf
) throws MessagingException {

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Your invoice");
    helper.setText(
            "Your invoice is attached.",
            "<p>Your invoice is attached.</p>"
    );

    helper.addAttachment(
            "invoice.pdf",
            new org.springframework.core.io.ByteArrayResource(pdf),
            "application/pdf"
    );

    sender.send(mime);
}
~~~

Đoạn mã chỉ minh họa MIME composition. Production cần **kiểm soát recipient, quyền truy cập hóa đơn, kích thước file, dữ liệu nhạy cảm và retention**.

Với attachment lớn, direct submission có thể kéo dài request đáng kể:

~~~text
Database query -> render PDF -> load bytes -> SMTP DATA
~~~

Nếu API cần trả lời nhanh, nên tách việc dựng và gửi file khỏi request, lưu **attachment reference** trong outbox thay vì nhét file lớn vào message broker.

## 13. @Async là một phương án trung gian, không phải durable queue

Spring có thể chạy logic gửi mail bất đồng bộ:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendAsync(
            SimpleMailMessage message
    ) {
        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Trong Spring cần bật asynchronous method execution và cấu hình TaskExecutor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncMailConfiguration {

    @Bean("mailExecutor")
    public TaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

Các giới hạn:

- Task nằm trong bộ nhớ JVM; process crash có thể làm mất yêu cầu gửi đang chờ.
- Một **CompletableFuture** hoàn thành ngoại lệ cần được caller theo dõi; trả HTTP xong rồi bỏ Future là bỏ trách nhiệm quan sát.
- **@Async** hoạt động qua Spring proxy; gọi method async bằng **this.sendAsync(...)** trong cùng bean thường không kích hoạt interception như mong muốn.
- Truyền entity JPA lazy hoặc request-scoped context sang thread khác có thể lỗi; truyền immutable DTO hoặc durable reference.
- Nếu queue đầy, cần rejection policy. Không tăng capacity vô hạn chỉ để tránh lỗi.
- Nếu email quan trọng, @Async nên là **worker đọc durable jobs**, thay vì là nơi duy nhất giữ message chưa gửi.

**@Async giúp giảm độ trễ HTTP nhưng không tự giải quyết bảo đảm không mất ý định gửi.**

## 14. Vì sao chỉ “đẩy vào broker” vẫn có thể mất notification?

Giả sử:

~~~text
Order service:
    1. BEGIN transaction
    2. INSERT order
    3. COMMIT
    4. Publish SendEmail event to broker
~~~

Nếu process crash giữa bước 3 và 4:

~~~text
Order đã tồn tại
Email event chưa tới broker
=> Mất notification
~~~

Đổi thứ tự thành publish trước commit cũng có vấn đề:

~~~text
Publish event thành công
DB transaction rollback
=> Email có thể được gửi về đơn hàng không tồn tại
~~~

Đây là **dual-write problem**: hai hệ thống khác nhau (database và broker) không có một commit nguyên tử tự nhiên.

Một cơ chế không có distributed transaction chỉ nên đưa ra bảo đảm phù hợp với thực tế. **Transactional outbox** thường giải quyết được chỗ tạo ý định và business state trong cùng database.

## 15. Transactional outbox giải quyết phần nào?

Trong **cùng database transaction**:

~~~sql
BEGIN;

INSERT INTO orders (...);

INSERT INTO email_outbox (
    id,
    business_event_id,
    notification_type,
    recipient_ref,
    status,
    created_at
) VALUES (
    :id,
    :eventId,
    'ORDER_CONFIRMED',
    :recipientRef,
    'PENDING',
    statement_timestamp()
);

COMMIT;
~~~

Khi transaction commit:

- Order và email intent cùng tồn tại.
- Nếu rollback, không có order lẫn intent.
- Nếu process crash sau commit, outbox row vẫn có thể được worker lấy lại.

Những điều **outbox chưa tự giải quyết**:

- Gửi SMTP exactly-once.
- Recipient có còn consent hoặc đủ điều kiện khi worker xử lý không.
- Template/attachment có còn truy cập được không.
- Provider quota, outage và retry.
- Cách biết message đã delivered hay bounced.
- Làm sao cleanup/archive outbox mà không mất lịch sử bắt buộc.

Outbox chuyển bài toán từ “không biết có yêu cầu gửi hay không” thành “**có record bền vững để xử lý và đối soát**”.

## 16. Hai cách triển khai outbox

### A. Database outbox cũng là work queue

~~~text
Order transaction -> email_outbox table
                            |
                            v
                       DB poller
                            |
                            v
                       Mail worker
                            |
                            v
                           SMTP
~~~

Ưu điểm: ít thành phần, dễ giữ tính nguyên tử ở producer, phù hợp quy mô vừa và vận hành tối giản. Đánh đổi: workload polling/claim/retry gây tải database; phải quản lý index, batch và cleanup.

### B. Outbox dispatcher đẩy sang broker

~~~text
Order transaction -> email_outbox table
                            |
                            v
                     Outbox dispatcher
                            |
                            v
                      RabbitMQ/Kafka
                            |
                            v
                       Mail worker
                            |
                            v
                           SMTP
~~~

Ưu điểm: broker giúp phân phối consumer, buffer và tách nhiều mail workers. Đánh đổi: có **hai tầng retry/dedup** và phải làm đúng **publisher confirmation, event publishing idempotency, ack/offset và broker retention**.

Trong cả hai mô hình, **nhiều lần deliver cùng một outbox event là điều có thể xảy ra**. Consumer phải idempotent ở phía business state và nhận diện đúng mức rủi ro với SMTP.

## 17. Schema outbox minh họa

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE email_outbox (
    id                UUID PRIMARY KEY,
    tenant_id         VARCHAR(120) NOT NULL,
    business_event_id VARCHAR(240) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    recipient_ref     VARCHAR(240) NOT NULL,
    template_version  VARCHAR(80) NOT NULL,
    payload_ref       TEXT NOT NULL,
    status            VARCHAR(40) NOT NULL,
    priority          SMALLINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL,
    next_attempt_at   TIMESTAMPTZ NOT NULL,
    expires_at        TIMESTAMPTZ,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    claim_token       UUID,
    lease_until       TIMESTAMPTZ,
    submitted_at      TIMESTAMPTZ,
    outcome_reason    VARCHAR(100),
    version           BIGINT NOT NULL DEFAULT 0,
    UNIQUE (
        tenant_id,
        business_event_id,
        notification_type,
        recipient_ref
    ),
    CHECK (attempt_count >= 0)
);

CREATE INDEX ix_email_outbox_due
ON email_outbox (
    priority DESC, next_attempt_at, id
)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

**Schema là ví dụ của ứng dụng, không phải bảng Spring Mail cung cấp.** Nó giả định business_event_id đủ cụ thể để phân biệt các lần gửi hợp lệ. Với digest/campaign theo kỳ, cần thêm period/campaign version; nếu không unique key có thể vô tình chặn email cần gửi ở kỳ sau.

**recipient_ref** có thể là khóa nội bộ thay cho địa chỉ email thô để giảm lộ PII. Payload có thể là reference tới JSON và attachment trong storage có quyền; worker cần kiểm tra tenant/context và retention khi đọc.

Một outbox production thường cần **attempt history**, state transition audit và policy metadata khác tùy mức yêu cầu.

## 18. Worker claim job an toàn khi chạy nhiều instance

Không nên:

~~~text
SELECT pending rows
for each row:
    send SMTP
    update status
~~~

Hai pod có thể cùng SELECT một row và gửi hai email. Với PostgreSQL có thể claim theo batch bằng transaction ngắn:

~~~sql
WITH due_jobs AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= statement_timestamp()
      AND (
          expires_at IS NULL
          OR expires_at > statement_timestamp()
      )
    ORDER BY priority DESC, next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE email_outbox AS o
SET
    status = 'CLAIMED',
    claim_token = gen_random_uuid(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    version = o.version + 1
FROM due_jobs AS d
WHERE o.id = d.id
RETURNING o.id, o.claim_token, o.tenant_id,
          o.notification_type, o.recipient_ref;
~~~

**SKIP LOCKED** hạn chế chờ lock khi nhiều worker, nhưng không thay thế claim token và state updates có điều kiện. Lease 2 phút là minh họa; phải chọn theo latency/heartbeat/timeout thật. Hàm UUID phải tồn tại ở database hoặc được thay bằng token ứng dụng tạo.

Sau claim:

1. Commit transaction claim nhanh chóng.
2. Đọc payload đã được persist.
3. Kiểm tra tenant, consent/suppression, business relevance và deadline.
4. Chuyển **CLAIMED → SENDING** có điều kiện với claim token.
5. Thực hiện SMTP submission **ngoài transaction giữ row lock**.
6. Ghi kết quả SUBMITTED/RETRY_WAIT/FAILED/UNKNOWN với claim token.

Nếu một row đã đổi sang trạng thái khác, worker không được bỏ điều kiện WHERE chỉ để cập nhật cho bằng được.

## 19. Spring Scheduler chạy database queue

Spring Scheduling có thể đánh thức worker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class MailSchedulingConfiguration {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxPollingJob {

    private final OutboxDispatchService dispatcher;

    public OutboxPollingJob(OutboxDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchDueJobs() {
        dispatcher.dispatchBatch();
    }
}
~~~

**OutboxDispatchService** là service do ứng dụng tự xây; phải có atomic claim, worker concurrency, timeout, retry và state handling. Fixed delay 1 giây không phải SLA mặc định; nó chỉ quyết định tần suất kích hoạt poll và có thể bị trễ khi công việc hoặc hệ thống quá tải.

Chạy cùng @Scheduled method ở nhiều instance có thể cùng quét; dùng **DB claim/lease, distributed coordination hoặc shard** theo topology. Không đặt niềm tin vào một synchronized block chỉ có tác dụng trong một JVM.

### @Scheduled không biến database thành queue chuyên dụng

Database polling cần:

- Index đúng với truy vấn due jobs.
- Batch size hữu hạn và giới hạn transaction duration.
- Backoff khi DB unavailable.
- Cleanup/archive trạng thái terminal.
- Metrics cho oldest due age và claim lag.
- Chống một tenant làm quá tải toàn bộ worker.

## 20. Worker xử lý email bằng interface có trách nhiệm rõ ràng

Một abstraction:

~~~java
public record MailJob(
        String id,
        String tenantId,
        String notificationType,
        String recipientRef,
        String templateVersion,
        String payloadRef,
        String claimToken
) {
}

public enum SubmissionOutcome {
    ACCEPTED,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE,
    UNKNOWN
}

public interface MailJobStore {
    java.util.List<MailJob> claimDue(int maxJobs);
    boolean markSending(MailJob job);
    void markAccepted(MailJob job);
    void scheduleRetry(MailJob job, java.time.Instant nextAttempt);
    void markFailed(MailJob job, String reason);
    void markUnknown(MailJob job, String reason);
}
~~~

Code dưới dạng **interface của ứng dụng** cho thấy cần tách:

- **Claim và fencing token** thuộc persistence.
- **Build MIME** thuộc template/message composition.
- **Send** thuộc SMTP adapter.
- **Classify failures** thuộc retry policy.
- **State transition** thuộc job store.
- **Metrics/audit** thuộc observability.

Nếu worker có quá nhiều code điều kiện trong một method vừa truy cập DB vừa render HTML, gửi SMTP, retry và log, sẽ khó kiểm soát những lần crash ở giữa các bước.

## 21. Queue delivery là at-least-once trong nhiều thiết kế

Một message broker hoặc database queue có thể phát lại một job khi:

~~~text
Worker receives SendEmail N100
        |
        v
SMTP provider accepts email
        |
        v
Worker crashes before ACK / offset commit
        |
        v
Broker redelivers N100
        |
        v
Potential second SMTP submission
~~~

**Consumer ACK không được liên kết nguyên tử với việc SMTP provider accepted.** Dù broker có transaction/idempotent producer, SMTP server không mặc nhiên tham gia transaction của broker.

Vì vậy cần:

- Một **notification/recipient idempotency key**.
- Durable job state và attempt records.
- Quy tắc ACK/offset sau khi persist kết quả.
- Chính sách xử lý outcome **UNKNOWN**.
- Provider API idempotency key nếu dịch vụ hỗ trợ thật.
- Reconciliation khi provider cho phép tra cứu.
- Chấp nhận thực tế rằng không phải mọi SMTP transport đều hỗ trợ exactly-once.

Một queue giúp **không mất việc chờ xử lý** nếu cấu hình đúng, nhưng không tự ngăn được **side effect gửi trùng** khi consumer bị redeliver.

## 22. Phân biệt ba mức bảo đảm cần nói rõ với sản phẩm

| Mức bảo đảm | Diễn giải | Có thể làm như thế nào? |
|---|---|---|
| **Best effort** | Cố gắng gửi; có thể mất khi process crash | Direct/async in-memory với xử lý lỗi tối giản |
| **Durable intent / at-least-once processing** | Ý định gửi được lưu; worker retry khi lỗi và chưa đạt terminal outcome | Outbox + claim + retry + audit |
| **Effectively-once business action** | Những lần retry không tạo hành động nghiệp vụ trùng theo phạm vi key | Unique constraint + idempotent handler + provider support/reconciliation |

“Exactly-once email delivery” là lời hứa rất mạnh, thường **không thể chứng minh chỉ bằng Spring Mail và SMTP**.

Thậm chí hai email MIME có cùng **Message-ID** không bảo đảm mail server/recipient sẽ deduplicate. Message-ID giúp threading/trace, không phải một idempotency API chuẩn của SMTP.

### Khi nào duplicate còn chấp nhận được?

Một thông báo hệ thống nội bộ có thể chịu được hai email hiếm gặp. Nhưng:

- Hóa đơn bị gửi hai lần có thể gây nhầm lẫn.
- OTP trùng có thể gây hiểu sai mã nào còn hiệu lực.
- Email tài chính chứa nội dung nhạy cảm gửi nhầm recipient là rủi ro nghiêm trọng.
- Campaign marketing gửi trùng gây complaint/reputation loss.

Vì vậy **mức độ chấp nhận duplicate** phải là input của quyết định kiến trúc, không chỉ là lựa chọn kỹ thuật của developer.

## 23. SMTP failure có thể là transient, permanent hoặc ambiguous

Ví dụ:

| Sự kiện | Khả năng kết quả | Hành động |
|---|---|---|
| DNS/connect fail trước SMTP DATA | Chưa submission, thường retryable nếu tạm thời | Backoff/retry trong deadline |
| Authentication rejected | Chưa được gửi; thường lỗi cấu hình/token | Sửa credential, tránh retry nóng |
| SMTP 451 temporary failure | Bị từ chối tạm thời nếu reply đủ rõ | Retry theo provider policy |
| SMTP 550 5.1.1 invalid recipient | Thường permanent cho recipient | Failed/suppression theo evidence |
| SMTP 5.7.1 policy reject | Có thể do sender reputation/auth | Điều tra, không hard-suppress bừa |
| Timeout sau DATA, không thấy final reply | **UNKNOWN**: server có thể đã accepted | Reconcile, không auto-retry mù |
| MailSendException với partial recipients | Một số recipient đã accepted | Theo dõi kết quả per-recipient |
| SMTP accepted nhưng DB update fail | Email có thể đã ra ngoài | Không coi job chắc chắn chưa gửi |

**Direct và queued đều chịu các trạng thái SMTP này**. Queue làm cho việc lưu/chuyển trạng thái và retry thuận tiện hơn, nhưng không làm kết quả mơ hồ biến mất.

Khi xây **MailRetryClassifier**, phải xét loại exception, cause chain, SMTP status/enhanced code, thời điểm lỗi và độ chắc chắn của bằng chứng acceptance. Không retry tất cả **MailException** như nhau.

## 24. Một state machine hợp lý cho queue

~~~text
PENDING
    |
    v
CLAIMED
    |
    +-- policy changed --> SKIPPED
    +-- expired --------> EXPIRED
    |
    v
SENDING
    |
    +-- accepted --------> SUBMITTED
    +-- retryable -------> RETRY_WAIT
    +-- permanent -------> FAILED
    +-- ambiguous -------> UNKNOWN
                               |
                               v
                         RECONCILIATION
~~~

Một số hệ thống gộp PENDING/RETRY_WAIT hoặc dùng status khác, nhưng cần giữ ngữ nghĩa:

- **PENDING**: intent đã ghi, chưa được xử lý.
- **CLAIMED**: worker được giao quyền.
- **SENDING**: SMTP attempt đã bắt đầu hoặc sắp đi qua ranh giới side effect.
- **SUBMITTED**: có bằng chứng SMTP accepted.
- **SKIPPED**: một policy cấm hoặc không cần gửi.
- **EXPIRED**: không được khởi động attempt mới sau deadline.
- **FAILED**: không còn retry theo bằng chứng/chính sách.
- **UNKNOWN**: có khả năng đã gửi nhưng thiếu chứng cứ kết quả.

Trong direct path, vẫn có thể cần state machine tương tự nếu phải audit/retry; khác nhau chủ yếu là **ai chạy attempt và thông tin được lưu khi nào**.

## 25. Lease hết hạn không đồng nghĩa email chưa gửi

Một ví dụ:

~~~text
Worker A claims N100
Worker A sends SMTP DATA
Worker A crashes before saving SUBMITTED
Lease expires
Worker B reclaims N100
~~~

Nếu B gửi lại ngay vì lease hết hạn, recipient có thể nhận hai bản.

Phân biệt:

**CLAIMED, chưa bước vào SMTP:** có thể reclaim khi có bằng chứng và kiểm tra deadline.

**SENDING, outcome chưa lưu:** phải cân nhắc **UNKNOWN** và reconciliation; không đơn giản reset về PENDING.

**Claim token/fencing** chỉ bảo vệ database update của stale worker. Nó **không thể dừng TCP connection cũ** đã bắt đầu gửi dữ liệu tới server ngoài.

Mô hình production cần attempt history và quy trình cho SENDING quá lâu. Câu hỏi “worker nào có quyền cập nhật DB?” và “email đã có thể được chấp nhận chưa?” là hai câu hỏi khác nhau.

## 26. ACK broker nên xảy ra khi nào?

Một kiến trúc consumer đơn giản:

~~~text
Receive queue message
       |
       v
Claim/lookup durable notification state
       |
       v
Apply policy + SMTP attempt
       |
       v
Commit durable outcome
       |
       v
ACK message
~~~

Nếu ACK **trước khi** có outcome bền vững, worker crash sau ACK có thể làm mất job (nếu không có outbox/DB scanner khác).

Nếu ACK **sau khi** outcome commit, crash giữa commit và ACK có thể khiến broker redeliver. Vì vậy:

1. Consumer phải **idempotent** khi thấy job đã SUBMITTED/SKIPPED/FAILED.
2. Nếu outcome còn UNKNOWN, consumer không được tự cho rằng chưa gửi.
3. Retry của SMTP và retry của broker phải có **một policy tổng hợp**, tránh hai vòng retry độc lập tạo storm.
4. Poison message phải đi vào DLQ/quarantine sau rule phù hợp, không chặn toàn bộ partition/queue.

ACK/offset commit semantics phụ thuộc broker. Không sử dụng một hình thức ACK tưởng tượng áp dụng y hệt cho RabbitMQ, JMS và Kafka.

## 27. Ví dụ RabbitMQ consumer qua Spring AMQP

Nếu hệ thống đã có RabbitMQ, Spring AMQP cho phép đăng ký consumer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ consumer chỉ nhận một **job ID**, không chứa cả MimeMessage:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
import java.util.UUID;

@Component
public class QueuedMailConsumer {

    private final MailDeliveryOrchestrator orchestrator;

    public QueuedMailConsumer(
            MailDeliveryOrchestrator orchestrator
    ) {
        this.orchestrator = orchestrator;
    }

    @RabbitListener(queues = "mail.send.jobs")
    public void onMessage(String notificationId) {
        orchestrator.process(UUID.fromString(notificationId));
    }
}
~~~

**MailDeliveryOrchestrator** là service ứng dụng có durable state, claim/dedup, retry và policy; nó không phải class Spring. Ví dụ dùng kiểu listener tối giản, **ACK tự động/manual, prefetch, consumer concurrency, retry advice, DLQ và publisher confirms** phải được cấu hình theo yêu cầu của dự án.

Nếu orchestrator ném exception, kết quả requeue/ACK phụ thuộc listener container và error handler. Không được dựa vào ví dụ này để suy ra broker luôn retry đúng hay luôn tránh mất thư.

### Vì sao chỉ truyền notificationId?

- Tránh message queue quá lớn vì HTML/attachment.
- Giảm lộ PII trong broker logs/management UI.
- Worker đọc template/payload version và tenant policy từ nguồn đáng tin.
- Có thể replay và reconcile bằng cùng ID.

Nếu message chứa correlation metadata, vẫn cần **xác minh** mapping tenant/notification từ DB, không tin hoàn toàn một tenantId do producer chưa được kiểm soát đưa vào header.

## 28. Kafka nên được dùng khác RabbitMQ như thế nào?

Kafka phù hợp khi hệ thống đã có event streaming và nhiều consumer khác nhau muốn đọc các sự kiện nghiệp vụ. Nhưng **Kafka topic không mặc nhiên là một delayed-job queue**.

Ví dụ:

~~~text
OrderCreated event (Kafka topic)
      |
      v
Notification intent consumer
      |
      v
Dedup + insert email_outbox
      |
      v
Mail dispatcher with next_attempt_at
      |
      v
SMTP
~~~

Những điểm cần cân nhắc:

- **Partition ordering** chỉ áp dụng trong phạm vi partition; không có global ordering.
- Khi một message thất bại, việc block partition có thể giữ nhiều events phía sau.
- **Kafka retry topics** hoặc retry scheduler cần được thiết kế riêng cho backoff dài và deadline.
- Kafka consumer offset commit **không commit nguyên tử SMTP side effect**.
- Kafka producer idempotence/transactions không tự khiến SMTP send exactly-once.
- Events có thể bị replay trong retention window; consumer phải idempotent.
- Notification intent đôi khi cần lâu hơn retention của một topic, vì vậy outbox database vẫn hữu ích.

Nếu mục tiêu chỉ là gửi vài email định kỳ, dựng cả Kafka cluster chỉ vì “phải dùng queue” thường không hiệu quả về chi phí/vận hành.

## 29. Database queue hay broker: quyết định thứ hai sau direct/queued

| Tiêu chí | Database jobs | Broker-backed queue |
|---|---|---|
| Hệ thống cần thêm | DB đã có | Broker/service riêng |
| Transaction với business DB | Dễ khi cùng database | Cần outbox/CDC hoặc cơ chế khác |
| Claim/due-job query | SQL + indexes/leases | Broker dispatch + retry scheduling |
| Backpressure | Giới hạn DB polling/batch | Prefetch, consumer concurrency, broker limits |
| Độ trễ | Poll interval và DB load | Event push thường nhanh, tùy topology |
| Retry delay dài | next_attempt_at tự nhiên | Cần delay queue/plugin/retry topology tùy broker |
| Thứ tự ưu tiên | ORDER BY/partitioning | Priority queues hoặc nhiều queues |
| Scale throughput | Tới giới hạn DB/locks | Scale consumers/broker theo kiến trúc |
| Quan sát | SQL/job ledger | Broker metrics + job ledger |
| Chi phí | Tải tăng lên DB chính | Broker ops/cost + kết nối |

**Database queue** thường đủ cho email số lượng vừa, SLA không quá gắt và đã có relational DB tin cậy.

**Broker** phù hợp hơn khi cần fan-out, throughput lớn, tách nhiều service hoặc đã có hạ tầng message processing chuẩn.

Nếu dùng broker nhưng vẫn phải ghi outbox để tránh dual-write, hãy tính tổng độ phức tạp của **cả hai tầng**.

## 30. Độ trễ: direct nhanh hơn về “bắt đầu gửi”, queue nhanh hơn về HTTP

Trực giác “direct luôn nhanh” hoặc “queue luôn nhanh” đều thiếu ngữ cảnh. Phải xác định **đo ở đâu**.

Ví dụ:

~~~text
Direct:
  HTTP + business logic  60 ms
  MIME preparation       20 ms
  SMTP submission       900 ms
  ----------------------------
  HTTP response          980 ms

Queue:
  HTTP + business logic  60 ms
  Persist outbox         20 ms
  ----------------------------
  HTTP response           80 ms

  Queue wait             200 ms
  MIME preparation        20 ms
  SMTP submission        900 ms
  ----------------------------
  SMTP accepted ~1.2 s from request
~~~

Đây là **số giả định để minh họa**, không phải benchmark của Spring Mail.

Trong ví dụ:

- Queue làm **HTTP latency thấp hơn**.
- Direct có thể đưa thư tới SMTP sớm hơn vì không phải chờ worker.
- Queue có thể đồng thời bảo vệ request thread khi provider chậm.

Với OTP, điều quan trọng có thể là **time-to-SMTP-accepted** hoặc **time-to-delivery**, chứ không chỉ response API. Một queue tắc nghẽn 5 phút là không chấp nhận được cho OTP dù API trả 80 ms.

### Nên đo ba latency

~~~text
API latency =
    response_at - request_received_at

Queue wait =
    attempt_started_at - intent_committed_at

SMTP submission latency =
    submission_result_at - attempt_started_at
~~~

Sau đó, nếu provider có webhook, đo thêm **provider delivery feedback latency** theo độ chính xác dữ liệu của họ.

## 31. Queue buffer burst nhưng không tự tạo throughput vô hạn

Giả sử:

~~~text
Campaign produces: 10,000 emails/minute
Provider allows:    2,000 recipients/minute
~~~

Nếu traffic giữ nguyên, backlog tăng khoảng **8.000 recipients/phút**, dù worker đã hoạt động tối đa.

Một ước lượng:

\[
\text{Backlog growth rate} \approx \lambda - \mu
\]

Trong đó:

- \(\lambda\): tốc độ tạo notification hợp lệ.
- \(\mu\): tốc độ xử lý thực tế, bị giới hạn bởi SMTP provider, CPU, I/O, quota và worker.

Khi \(\lambda > \mu\) liên tục, queue chỉ **dời áp lực sang tương lai**. Hệ thống cần admission control, lịch campaign, rate limits, capacity planning hoặc giảm/đổi khối lượng công việc.

Một phép tính ví dụ:

~~~text
Backlog = 48,000 recipients
Effective sending rate = 1,600 recipients/minute

Minimum drain time ~= 30 minutes
~~~

Đó là ước lượng trong điều kiện rate ổn định, không có job mới, retries hoặc provider outage. Trong thực tế, có thể lâu hơn.

**Không giải quyết overload bằng cách mở 500 SMTP connections nếu provider chỉ cho một quota nhỏ**; số connection cao hơn có thể tăng throttling, timeout và complaint risk.

## 32. Backpressure và hạn mức theo tenant

Một hệ thống SaaS có nhiều khách hàng:

~~~text
Tenant A: 100,000 marketing emails
Tenant B: 20 password-reset emails
Tenant C: 500 invoice emails
~~~

Nếu tất cả dùng một FIFO queue và một pool không giới hạn phân loại, backlog marketing có thể làm chậm email quan trọng.

Các cơ chế:

- **Per-stream queues**: security, transactional, marketing.
- **Reserved worker capacity** cho email có deadline ngắn.
- **Per-tenant rate limit** và fairness.
- **Per-provider concurrency cap**.
- **Bounded in-flight** jobs thay vì tạo vô hạn threads.
- **Deadlines** và skip những email đã hết giá trị.
- **Admission control** trước khi một chiến dịch tạo hàng triệu job không thể gửi đúng hạn.
- **Retry budget** riêng để provider outage không làm retry chiếm hết worker.

Tuy nhiên, không cho phép caller tự gắn **priority=SECURITY** mà không có validation. Nếu vậy, mọi tenant có thể vượt quota bằng cách đổi nhãn.

## 33. Queue ordering: email có cần gửi theo thứ tự không?

Không phải mọi email đều độc lập.

Ví dụ người dùng đổi mật khẩu:

~~~text
Event 1: Password changed
Event 2: Security alert acknowledged
~~~

Hoặc đơn hàng:

~~~text
Event 1: Order confirmed
Event 2: Order shipped
~~~

Nếu worker xử lý song song, email **Order shipped** có thể được gửi trước **Order confirmed**.

Một số lựa chọn:

1. Chấp nhận out-of-order nếu nội dung tự chứa đầy đủ ngữ cảnh.
2. **Sequence number** theo business aggregate/recipient và gate khi thật sự cần.
3. Partition/serialize theo recipient hoặc business key, đổi lại throughput.
4. Gom thông báo hoặc suppress email obsolete để giảm noise.
5. Thêm field thời gian/trạng thái hiện tại trong nội dung để không gây nhầm.

**Queue không mặc định bảo đảm global order**. RabbitMQ, Kafka và database workers có các semantics khác nhau; cả khi broker bảo đảm thứ tự trong partition/queue, nhiều consumers, retries và DLQ có thể làm thay đổi thứ tự side effects.

Nếu không có yêu cầu ordering nghiêm ngặt, đừng ép serialize toàn bộ email của mọi tenant chỉ để tránh một trường hợp ít gặp.

## 34. Deadline: email được gửi muộn có còn hợp lệ không?

Một queue có thể giữ job cho tới khi provider phục hồi. Nhưng gửi muộn không phải lúc nào cũng đúng:

| Email | Nếu trễ | Quyết định có thể phù hợp |
|---|---|---|
| OTP | Token có thể hết hạn | EXPIRED, không gửi mã vô dụng |
| Password reset | Link hết hạn theo TTL | Skip hoặc tạo intent mới có xác minh |
| Nhắc cuộc họp | Sự kiện đã bắt đầu/kết thúc | Skip |
| Campaign khuyến mại | Offer không còn hiệu lực | Skip |
| Nhắc thanh toán | Đơn có thể đã thanh toán | Revalidate business state |
| Hóa đơn | Thường vẫn có nghĩa vụ gửi | Retry với SLA, không drop tùy tiện |
| Security alert | Có thể cần gửi muộn nhưng nội dung phải đúng | Revalidate severity/status |

Trong outbox:

~~~text
scheduled_at = thời điểm mong muốn
next_attempt_at = thời điểm retry/worker được phép lấy
expires_at = hạn không bắt đầu submission mới
~~~

Worker cần kiểm tra deadline **trước claim và gần khi bắt đầu SMTP attempt**. Một expiration scanner chạy định kỳ có thể đánh trạng thái cho job chờ, nhưng không được là rào chắn duy nhất vì scheduler có thể trễ.

**Đừng biến một email đã SUBMITTED thành EXPIRED_NOT_SENT** chỉ vì deadline đi qua sau khi SMTP accepted.

## 35. Policy thay đổi trong lúc email đang chờ

Ví dụ:

~~~text
08:00  Create marketing notification N100
08:30  User unsubscribes
09:00  Worker would send N100
~~~

Nếu worker dùng consent snapshot được lưu trong message khi enqueue, nó có thể gửi trái với lựa chọn mới.

Trước SMTP, cần kiểm tra:

- Người nhận có thuộc tenant hợp lệ không?
- Địa chỉ có bị hard-bounce suppressed hoặc complaint không?
- Người nhận đã unsubscribe list/stream tương ứng chưa?
- Business event còn hợp lệ không?
- Campaign có bị hủy/tạm dừng không?
- Template và attachment version có được phép dùng không?
- Notification có còn trong sending window và deadline không?

Một job **PENDING từ trước** vẫn có thể chuyển thành **SKIPPED** khi tới lượt nếu policy mới cấm gửi.

Không được chỉ dựa vào label TRANSACTIONAL để bỏ qua mọi suppression hoặc yêu cầu bảo mật; phân loại phải dựa trên nghiệp vụ thực chất.

## 36. Nhiều recipient: mô hình một message hay nhiều job?

Nếu một MimeMessage có ba người nhận:

~~~text
To: A@example.net
Cc: B@example.net
Bcc: C@example.net
~~~

SMTP có thể chấp nhận một số người nhận và từ chối những người còn lại. Khi đó một job gắn với ba recipients phải có **per-recipient results** để retry đúng.

Hai kiến trúc:

**Một notification/job cho nhiều recipients**

- Ít job hơn, có thể chia sẻ MIME rendering.
- Cần hiểu partial SMTP acceptance và mapping từng envelope recipient.
- Dễ phát sinh lỗi bảo mật khi có Bcc, tenant hoặc nội dung cá nhân hóa.

**Một notification-recipient/job cho mỗi recipient**

- Dễ áp dụng unsubscribe/suppression, retry, deadline, idempotency riêng.
- Dễ lưu delivery/bounce outcome theo recipient.
- Tăng số job và số submission, cần batch/rate management.

Với email cá nhân hóa, security hoặc nhiều tenant, **mỗi recipient một job** thường đơn giản hơn về ranh giới quyền và quan sát. Với thông báo nội bộ gửi cho nhóm nhỏ, một message nhiều recipients có thể hợp lý nếu chính sách và tính riêng tư cho phép.

## 37. Attachment nên nằm ở đâu?

Không nên nhét toàn bộ PDF 20 MB vào mỗi queue message:

~~~text
Queue message:
  notificationId
  tenantId
  attachmentUrl with raw token
  entire PDF bytes
~~~

Đây là cách dễ tăng broker storage, network traffic và rủi ro lộ token/dữ liệu.

Một message nhỏ hơn:

~~~json
{
  "notificationId": "N100",
  "schemaVersion": 2
}
~~~

Worker đọc outbox để lấy:

~~~text
tenant_id
recipient_ref
template_version
payload_ref
attachment_object_refs
authorization context
~~~

Object storage:

- Đặt key do hệ thống tạo.
- Bảo vệ theo tenant/least privilege.
- Có retention dài hơn thời gian retry tối đa.
- Không cấp signed download link hết hạn trước khi worker tới lượt.
- Validate checksum/size/content type khi cần.
- Không log nội dung hoặc signed URL chứa token.

Nếu attachment được tạo sau khi outbox commit, cần có trạng thái **PREPARING/READY** và reconciliation; đừng claim job gửi trước khi dữ liệu mà nó cần được lưu bền vững.

## 38. Template nên render khi enqueue hay khi gửi?

Hai lựa chọn:

| Cách | Lợi ích | Rủi ro |
|---|---|---|
| **Render tại enqueue** | Nội dung phản ánh snapshot lúc business event xảy ra; audit ổn định | HTML/raw MIME lớn, attachment chưa sẵn, không phản ánh policy mới |
| **Render tại worker** | Request nhanh, dùng tài nguyên worker, có thể cập nhật nội dung hiện tại | Template thay đổi giữa lúc enqueue/gửi, reference không còn |

Một mô hình phối hợp:

~~~text
Outbox:
  template_id = order-confirmation
  template_version = v5
  safe_input_snapshot_ref = object://...
  business_event_id = ...
~~~

Worker dùng **template version được pin** và snapshot dữ liệu đủ để dựng nội dung, đồng thời **revalidate quyền gửi** và những business conditions có thể thay đổi.

Không nên render từ một entity hiện tại mà không nhận diện rằng nội dung có thể khác sự kiện gốc. Ví dụ order confirmation có thể phải phản ánh giá/địa chỉ tại thời điểm đặt hàng, không phải dữ liệu sửa hôm sau.

### Khi nào lưu raw MIME?

Nếu cần replay chính xác nội dung gửi ban đầu, có thể lưu **raw MIME/reference** sau composition với retention/bảo mật rõ. Nhưng vẫn phải hiểu replay cùng MIME khác với replay cùng hành động nghiệp vụ; duplicate send có thể xảy ra, và Message-ID không tự bảo đảm dedup ở mail server.

## 39. API contract khác nhau giữa direct và queued

Với direct, một endpoint có thể phản hồi theo kết quả SMTP ngay:

~~~text
POST /admin/test-email
    |
    +-- Submission accepted -> 200/appropriate success
    |
    +-- Known failure -> appropriate error
    |
    +-- Ambiguous timeout -> accepted status uncertain
~~~

Với queued, endpoint nên trả một **tracking ID**:

~~~http
POST /orders/ORD-100/notifications
Content-Type: application/json

{
  "kind": "ORDER_CONFIRMATION"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "N100",
  "status": "QUEUED"
}
~~~

Sau đó, một endpoint trạng thái:

~~~http
GET /notifications/N100
~~~

~~~json
{
  "notificationId": "N100",
  "status": "SUBMITTED",
  "lastAttemptAt": "2026-11-12T10:20:00Z",
  "deliveryStatus": "UNKNOWN"
}
~~~

Không hiển thị trạng thái **DELIVERED** nếu chỉ biết SMTP accepted. Một API cần kiểm tra tenant/user authorization trước khi trả notification status, vì metadata có thể tiết lộ địa chỉ người nhận và sự kiện nghiệp vụ.

### Bất đồng bộ còn cần idempotency ở producer

Nếu client gửi lại cùng request sau một HTTP timeout:

~~~text
POST create notification -> DB commit
HTTP response lost
Client retries POST
~~~

Hệ thống cần idempotency key hoặc unique business intent key để không tạo hai notification jobs. Queue consumer idempotency không sửa được lỗi producer tạo hai intent khác nhau nếu không có domain key.

## 40. Ví dụ service ghi outbox cùng nghiệp vụ

Ví dụ minh họa interface:

~~~java
public record CreateOrderCommand(
        String customerId,
        String productId,
        int quantity
) {
}

public interface OrderRepository {
    Order saveNew(CreateOrderCommand command);
}

public interface MailOutboxRepository {
    void insertOrderConfirmation(
            String tenantId,
            String eventId,
            String orderId,
            String recipientRef,
            java.time.Instant createdAt
    );
}
~~~

Service:

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox,
            Clock clock
    ) {
        this.orders = orders;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public Order createOrder(
            String authenticatedTenantId,
            CreateOrderCommand command,
            String idempotentEventId
    ) {

        Order order = orders.saveNew(command);

        outbox.insertOrderConfirmation(
                authenticatedTenantId,
                idempotentEventId,
                order.id(),
                order.customerRecipientRef(),
                Instant.now(clock)
        );

        return order;
    }
}
~~~

**Order**, **OrderRepository** và **MailOutboxRepository** là abstractions của ứng dụng. Ví dụ giả định cả hai repository dùng **cùng Spring transaction manager và cùng database**; nếu outbox ở một DB khác, annotation @Transactional không tự tạo atomic commit xuyên hai kho.

Các chi tiết production còn cần:

- Xác thực tenant/order/customer trước khi lưu.
- Validate quantity và business invariants.
- Chống tạo trùng order nếu request replay.
- Unique constraint trên idempotentEventId/notification intent.
- Chọn template version và persist input snapshot phù hợp.
- Không đưa dữ liệu cá nhân nhạy cảm vào logs.

Ưu điểm chính: **không có lệnh SMTP nào nằm trong transaction tạo order**.

## 41. Một code path, nhiều transport: tránh fallback tự phát

Một anti-pattern:

~~~text
Try queue.publish(notification)
      |
      +-- broker down
              |
              v
        mailSender.send(...) trực tiếp
~~~

Vấn đề:

1. Publish có thể đã thành công ở broker nhưng response tới producer bị mất.
2. Producer thấy timeout rồi gửi trực tiếp, trong khi broker vẫn giữ message.
3. Worker sau đó gửi thêm bản thứ hai.
4. Retry, suppression, quota và metrics của direct fallback có thể khác worker pipeline.
5. Business API bị kéo dài bởi SMTP outage dù ban đầu chọn queued để cô lập.

Nếu cần failover, **fallback phải dựa trên một durable intent ID và trạng thái điều phối chung**, không tự gọi SMTP chỉ vì queue publish exception.

Một thiết kế an toàn hơn:

~~~text
Durable outbox -> Queue available?
                      |
                 +----+----+
                 |         |
                Yes        No
                 |         |
                 v         v
              Broker   Outbox remains PENDING
                           |
                           v
                    Dispatcher retries later
~~~

Chỉ khi có kiến trúc hot-standby được thiết kế rõ ràng với fencing/idempotency và các giới hạn đã được kiểm thử mới cân nhắc nhiều tuyến dispatch hoạt động song song.

## 42. Circuit breaker, timeout và provider outage

Direct:

~~~text
SMTP provider unavailable
      |
      v
HTTP request thread waits / errors
      |
      v
Potential request backlog and thread exhaustion
~~~

Queued:

~~~text
SMTP provider unavailable
      |
      v
Worker attempts fail
      |
      v
Retry/backoff, circuit breaker, queue backlog
      |
      v
Business API can continue accepting valid intents
~~~

Queue giúp **cô lập lỗi** nhưng cần giới hạn:

- Connection/read/write timeouts hữu hạn.
- Per-provider retry budget.
- Exponential backoff với jitter.
- Circuit breaker tránh chồng thêm yêu cầu khi provider liên tục fail.
- Worker concurrency bounded.
- Backlog alert và maximum retention/deadline.
- Manual pause/resume có quyền.
- Failover provider theo chính sách, không tự retry double send khi outcome UNKNOWN.

**Circuit breaker không có nghĩa drop mọi email mới.** Khi circuit open, hệ thống có thể giữ những intents bền vững chờ retry, nhưng phải từ chối/throttle producer nếu backlog vượt sức chứa hoặc email hết hạn.

## 43. Retry policy: không retry mọi lỗi Spring Mail

Một bộ phân loại:

~~~java
public enum RetryDecision {
    RETRY_LATER,
    FAIL_PERMANENTLY,
    RECONCILE_UNKNOWN,
    STOP_EXPIRED
}
~~~

Ví dụ policy về mặt logic:

~~~text
if SMTP acceptance is ambiguous:
    RECONCILE_UNKNOWN

else if business deadline passed:
    STOP_EXPIRED

else if error is transient and attempts < maxAttempts:
    RETRY_LATER

else:
    FAIL_PERMANENTLY
~~~

Không dùng:

~~~java
@Retryable
public void sendMail(...) {
    mailSender.send(...);
}
~~~

mà thiếu phân loại, giới hạn lần thử, deadline và theo dõi outcome. Một timeout sau DATA có thể đã accepted, vì vậy tự động retry mọi exception có thể gửi trùng.

Các lỗi cấu hình như **MailAuthenticationException** không thường được giải quyết bằng cách retry từng giây với cùng credential. Cần mở circuit/alert/quy trình credential refresh.

### Retry nên có state bền vững

Nếu retry chỉ nằm trong một interceptor hoặc sleep loop, process crash sẽ mất lịch retry. Với notification quan trọng, nên persist:

~~~text
attempt_count
last_error_category
next_attempt_at
expires_at
provider_profile
outcome
~~~

Khi crash/restart, scheduler mới biết lúc nào được thử tiếp. Một email bị chính sách unsubscribe trước next_attempt_at phải được SKIPPED, không được retry theo snapshot cũ.

## 44. SMTP provider failover và khả năng gửi trùng

Một số doanh nghiệp muốn:

~~~text
Primary SMTP provider fails
       |
       v
Try Secondary SMTP provider
~~~

Điều này có thể cải thiện tính sẵn sàng **nếu biết chắc primary chưa nhận message**. Nhưng khi primary timeout ở final reply:

~~~text
Primary may have accepted
Secondary then accepts
=> Potential duplicate deliveries
~~~

Nên phân loại:

| Trạng thái primary | Có thể dùng secondary? |
|---|---|
| Connect refused trước SMTP session | Có thể theo failover policy |
| Authentication/config lỗi | Cần xác minh sender policy/credential |
| Known recipient rejection | Không chuyển provider để né recipient policy |
| Known temporary provider outage | Có thể dùng secondary theo hạn mức và deadline |
| UNKNOWN sau DATA | Cần reconciliation/duplicate-risk policy |
| Primary accepted | Không gửi lại chỉ vì chưa có delivery webhook |

Đổi provider cũng thay đổi SPF/DKIM/DMARC setup, bounce routing, quota và domain reputation. **Failover phải là kế hoạch đã được triển khai/kiểm thử trước**, không phải sửa một property SMTP trong singleton sender khi outage xảy ra.

## 45. Bảo mật và phân quyền trong queue

Một job có thể chứa:

- Tenant ID.
- Recipient email/address reference.
- Order ID/ticket ID.
- Template data.
- Attachment object key.
- URLs chứa token.
- Sender profile ID.

Nếu đưa cả payload vào message broker:

- Broker management UI có thể cho người vận hành nhìn thấy PII.
- Logs của consumer/proxy có thể ghi toàn bộ message.
- Retry/DLQ có thể giữ dữ liệu lâu hơn retention chính.
- Một compromised consumer có thể đọc dữ liệu các tenant không thuộc quyền.

Nên dùng:

1. **Minimal message schema**, ưu tiên notificationId.
2. ACL/network/TLS cho broker.
3. Authentication/authorization giữa producers và consumers.
4. Tenant-scoped read khi worker lấy payload.
5. Encryption và secret management phù hợp.
6. Redacted structured logs, không ghi raw MIME/access token.
7. Retention và DLQ cleanup có kiểm soát.
8. Không truyền credential/sender password trong payload.
9. Kiểm tra sender profile được cấp quyền cho tenant.
10. Không dùng raw external input tạo dynamic routing destination/queue name tùy ý.

**Async không làm dữ liệu tự nhiên an toàn hơn direct**; nó tạo thêm kho lưu trữ và bề mặt truy cập, nên cần thiết kế bảo mật riêng.

## 46. Cập nhật consent, bounce và trạng thái người nhận

Một pipeline queued còn chịu những tín hiệu đến **sau khi job được tạo**:

~~~text
Notification created 08:00
Provider hard bounce received 08:30
Worker processes notification 09:00
~~~

Worker cần đánh giá suppression ở 09:00, không dùng thông tin lúc 08:00.

Một send gate có thể trả:

~~~text
ALLOW
SKIPPED_UNSUBSCRIBED
SKIPPED_HARD_BOUNCE
SKIPPED_BUSINESS_OBSOLETE
EXPIRED
DEFERRED_PROVIDER_QUOTA
DENIED_TENANT_POLICY
~~~

Nếu không đủ điều kiện gửi, chuyển job theo **state transition bền vững** thay vì gọi SMTP rồi chỉ ghi log “skipped”.

Đừng gộp SKIPPED do unsubscribe vào MailSendException hoặc SMTP failure metrics. Một skip hợp lệ về nghiệp vụ không phải lỗi transport.

Với nhiều recipients, nên đánh giá per-recipient khi trạng thái khác nhau.

## 47. Chi phí vận hành và tổng độ phức tạp

Một bảng tương đối:

| Chi phí | Direct | Queued với DB | Queued với broker |
|---|---|---|---|
| Coding ban đầu | Thấp | Vừa | Vừa/cao |
| Storage intent | Tùy nhu cầu | DB rows/indexes | Broker + thường cả outbox |
| Monitoring | SMTP/API | Scheduler, rows, attempts | Thêm broker queues/DLQ/offset |
| Failure recovery | Thường thủ công nếu không persist | Có job ledger | Có broker retry + ledger |
| Scale workers | Gắn API threads | Tách batch/worker | Tách consumer pools |
| Infrastructure | Ít | DB đã có | Thêm cluster/managed service |
| Data retention | Ít nếu không log | Cleanup/archive DB | Cần retention cả broker/DLQ |
| On-call complexity | Thấp khi volume nhỏ | Vừa | Cao hơn nếu topology phức tạp |

Một hệ thống có 100 emails/ngày, không yêu cầu durable intent, có thể không cần broker.

Một hệ thống gửi 500.000 emails/ngày, có SLA, bounce policy, marketing/transactional streams và nhiều tenant, khó vận hành an toàn nếu mọi request đều gọi SMTP trực tiếp.

**Đánh giá tổng chi phí trong vòng đời**, gồm operational failures, downtime, replay thủ công và hỗ trợ người dùng, không chỉ số dòng code ban đầu.

## 48. Ma trận chọn kiến trúc theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Admin bấm “Kiểm tra kết nối SMTP” | **Direct** | Cần chờ transport result để báo ngay |
| Prototype gửi vài email không quan trọng/ngày | **Direct hoặc async best effort** | Đơn giản, chấp nhận rủi ro rõ ràng |
| Xác nhận đơn hàng cần audit và không được mất intent | **Transactional outbox + worker** | Commit ý định cùng order và phục hồi được |
| Gửi hóa đơn có attachment và yêu cầu đối soát | **Durable queue/outbox** | Cần retention, retry, per-recipient outcome |
| Marketing campaign hàng trăm nghìn người | **Queue + rate control/stream isolation** | Buffer burst, quota, unsubscribe, provider feedback |
| Password reset/OTP có TTL ngắn | **Priority durable queue hoặc direct có kiểm soát** | Cần end-to-end latency và deadline, không chỉ HTTP nhanh |
| Security alert quan trọng | **Durable intent + priority/secondary channel** | Không nên mất alert khi provider tạm lỗi |
| Báo cáo digest định kỳ | **Outbox/scheduler** | Misfire policy, idempotency theo kỳ, gửi bù có điều kiện |
| Một REST endpoint gửi thư thay mặt tenant | **Queue khi đa tenant hoặc rate cao** | Cô lập quota, abuse, sender profile, observability |
| Provider hỗ trợ native scheduled send API | **Có thể kết hợp local outbox + provider schedule** | Cần theo dõi hủy, status và giới hạn provider |

**Đây là hướng cân nhắc, không phải quy tắc bắt buộc.** OTP có thể cần direct nếu hệ thống không có queue đủ nhanh/tin cậy; ngược lại nhiều ứng dụng lớn gửi OTP qua queue ưu tiên với độ trễ thấp và outbox bền vững.

### Một ví dụ chọn phương án

Ứng dụng bán hàng quy mô vừa có:

~~~text
Peak HTTP requests: 1,000 req/min
Order confirmation: 50 messages/min
Digest: 20,000 messages/night
SMTP provider: strict rate limit
Need audit for invoices
~~~

Một phương án:

- Order confirmation và invoice: tạo durable intent cùng business transaction.
- Digest: scheduler tạo intents theo kỳ, dùng queue marketing/digest riêng.
- Worker có hạn mức/provider token bucket.
- OTP/security: pool ưu tiên với deadline và cảnh báo queue lag.
- Test SMTP của admin: direct endpoint có authorization/rate limit.

Không cần ép mọi loại email vào **cùng một cơ chế gửi** nếu SLA và risk profile khác nhau; nhưng nên dùng cùng **policy/transport abstraction** để tránh rẽ nhánh quy tắc bảo mật.

## 49. Cây quyết định đơn giản

~~~text
Email chỉ là phép thử SMTP/transport cần kết quả ngay?
      |
      +-- YES --> Direct with strict timeout, rate limit
      |
      +-- NO
            |
            v
Sau khi business commit, có chấp nhận mất ý định gửi?
      |
      +-- YES --> Direct after commit / @Async best effort
      |           (hiểu rõ rủi ro process crash)
      |
      +-- NO
            |
            v
Có cần atomic commit với business data?
      |
      +-- YES --> Transactional outbox
      |
      +-- NO  --> Durable queue accepted as source of truth
            |
            v
Workload cần scale độc lập/đã có broker?
      |
      +-- YES --> Outbox + broker/consumers khi cần
      |
      +-- NO  --> Database outbox polling worker
            |
            v
Email có deadline, priority, consent, quota?
      |
      +-- YES --> Implement eligibility/admission + policies
      |
      +-- NO  --> Still define retry + outcome + monitoring
~~~

Thực tế các nhánh không hoàn toàn tuyến tính. Ví dụ một dự án có broker bền vững, business data nằm trong một hệ thống khác và producer có transactional event store riêng. Khi đó cần mô tả chính xác consistency boundary thay vì mặc định mọi nơi phải tạo cùng một bảng.

**Câu hỏi nền tảng vẫn là: “Khi ứng dụng báo đã nhận trách nhiệm gửi, có bản ghi bền vững nào chứng minh trách nhiệm đó không?”**

## 50. Chiến lược hybrid: direct cho một số việc, queue cho phần còn lại

Một kiến trúc thực dụng:

~~~text
Spring Application
       |
       +-- Admin SMTP diagnostic
       |      |
       |      v
       |   Direct sender
       |
       +-- Business notifications
       |      |
       |      v
       |   Durable outbox + mail worker
       |
       +-- Large marketing campaigns
              |
              v
         Campaign scheduler
              |
              v
         Rate-limited mail queues
~~~

Những đường này vẫn nên chia sẻ:

- **Sender profile registry**: tenant, from domain, SMTP credentials.
- **Template/versioning policy**.
- **Recipient authorization/consent/suppression**.
- **MIME composition security**.
- **SMTP transport timeout và error classification**.
- **Correlation/telemetry**.

Nếu cùng một email có thể được gửi qua direct hoặc queued tùy trạng thái runtime, phải có cơ chế **idempotent job ownership**. Không bật fallback tự phát để direct “cứu” queue khi broker timeout mơ hồ.

### Một abstraction để giữ ranh giới

~~~java
public interface NotificationDispatcher {
    DispatchReceipt requestSend(NotificationCommand command);
}

public record DispatchReceipt(
        String notificationId,
        String acceptedState
) {
}
~~~

Một implementation có thể ghi outbox; một implementation chỉ gửi trực tiếp cho mail test. Giao diện của chúng không được đánh tráo semantics: **Direct submission accepted** khác **Queued intent accepted**.

## 51. Chuyển từ direct sang queue từng bước

Một hệ thống đang gọi SMTP trong controller có thể chuyển đổi theo các giai đoạn:

### Giai đoạn 1 — Đo đúng hiện trạng

- HTTP p50/p95/p99 latency khi SMTP bình thường và chậm.
- SMTP attempt duration/errors/timeouts.
- Số email theo business event, tenant, provider.
- Số lần người dùng retry request gây duplicate.
- Các trường hợp business transaction rollback sau SMTP accepted.

### Giai đoạn 2 — Trừu tượng hóa send intent

Tách:

~~~text
Business event -> NotificationCommand
      |
      v
Template/Recipient policy
      |
      v
Transport adapter
~~~

Không để mọi controller tự tạo MimeMessage và chọn sender riêng.

### Giai đoạn 3 — Thêm outbox transactionally

Trong cùng transaction nghiệp vụ, tạo notification row với unique key. Trong giai đoạn migration, **không bật cả direct và outbox worker cho cùng intent** nếu chưa có cơ chế owner rõ; nếu không sẽ gửi trùng.

### Giai đoạn 4 — Bật worker cho traffic thử nghiệm

Đặt stream/tenant test vào durable worker. Theo dõi queue latency, retries, unknown và provider response. Có thể so sánh metadata ở chế độ **shadow classification** nhưng không thực hiện song song hai SMTP submissions cho cùng email thật.

### Giai đoạn 5 — Mở rộng theo stream

Chuyển transactional rồi marketing/digest hoặc ngược lại theo rủi ro và khả năng vận hành. Giữ rollback plan:

- Tạm ngừng claim jobs mới nếu lỗi.
- Giữ outbox rows chưa hoàn thành.
- Không chuyển SENDING/UNKNOWN về PENDING chỉ để rollback code.
- Cho phép replay có kiểm soát sau khi sửa lỗi.

### Giai đoạn 6 — Dọn các đường direct không còn cần

Đảm bảo API không còn path cũ bypass consent, quota và audit. Giữ direct test endpoint tách biệt nếu vẫn có nhu cầu chẩn đoán SMTP.

## 52. Nên theo dõi metric nào khi chọn queued?

| Metric | Mục đích |
|---|---|
| **mail_outbox_created_total** | Producer tạo bao nhiêu intents |
| **mail_outbox_pending** | Có bao nhiêu jobs chưa xong |
| **mail_outbox_oldest_due_age_seconds** | Job đến hạn lâu nhất đang chờ |
| **mail_queue_wait_seconds** | Thời gian từ commit tới attempt |
| **mail_smtp_attempts_total** | Số SMTP attempts theo provider/kết quả |
| **mail_smtp_submission_duration_seconds** | Latency của SMTP transport |
| **mail_outbox_submitted_total** | Unique notifications đạt SUBMITTED |
| **mail_outbox_skipped_total** | Skip do consent, business, deadline |
| **mail_outbox_retry_wait** | Job đang chờ retry |
| **mail_outbox_unknown** | Submission outcome chưa rõ |
| **mail_worker_stale_claims_total** | Claim/lease hết hạn cần xem xét |
| **mail_dead_letter_total** | Jobs vào DLQ/quarantine |
| **mail_bounce_events_total** | Delivery feedback từ provider |

Các metrics cần được định nghĩa rõ **theo attempt, notification hay recipient**. Ví dụ một mail có ba recipients và một recipient bounce thì không nên coi cả ba đã bounce.

**Tránh high-cardinality labels** chứa email address, Subject, notificationId, raw exception message hoặc signed URL. Sử dụng các chiều hữu hạn như stream, tenant tier, provider và result/error category; thông tin chi tiết nên nằm trong database/log có quyền truy cập.

### Chọn SLI/SLO đúng

Ví dụ:

~~~text
99.9% valid OTP jobs must start SMTP submission
within 5 seconds of intent commit, before expiry.
~~~

Đây là **submission timeliness objective**, không phải bảo đảm recipient đọc được OTP trong 5 giây. Nếu cần đo end-to-end delivery, phụ thuộc dữ liệu và mức độ tin cậy của ESP.

Một hệ thống queued có API 20 ms nhưng queue wait p99 = 2 phút chưa chắc đáp ứng mục tiêu OTP.

## 53. Test kiến trúc direct: kiểm tra điều gì?

Đối với direct path, nên kiểm tra:

| Case | Kỳ vọng |
|---|---|
| SMTP thành công | API báo submission accepted, không hứa delivery |
| Authentication fail | API trả lỗi an toàn, không lộ password |
| Connect timeout | Request được kết thúc theo timeout policy |
| SMTP từ chối recipient rõ ràng | Không coi đã gửi thành công |
| Timeout final reply sau DATA | Outcome có thể UNKNOWN, tránh auto-retry mù |
| DB rollback sau khi event xảy ra | Không gửi mail xác nhận cho transaction đã rollback nếu thiết kế yêu cầu |
| Nhiều request đồng thời | Sender không bị sửa state/credential giữa threads |
| Người dùng gửi lặp | Idempotency key/endpoint policy phù hợp |
| Recipient không được phép | Không gọi transport |
| MIME có HTML/attachment | Render đúng và không lộ dữ liệu giữa tenant |

Có thể dùng một SMTP test server để quan sát số message đã nhận, nhưng cần phân biệt **lỗi phía client** với **server đã nhận DATA nhưng client không nhận final reply**.

### Unit test service trực tiếp

Một phép kiểm tra đơn giản dùng mock sender:

~~~java
import static org.mockito.Mockito.verify;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class DirectMailUnitTest {

    @Test
    void callsSenderWhenAuthorized() {
        JavaMailSender mockSender =
                Mockito.mock(JavaMailSender.class);

        TestEmailService service = new TestEmailService(mockSender);
        service.sendTest("allowed@example.net");

        verify(mockSender).send(
                Mockito.any(SimpleMailMessage.class)
        );
    }
}
~~~

Đây chỉ là **unit test behavior**, không kiểm tra TCP, SMTP replies, TLS hoặc DKIM. Authorization/recipient validation cần test riêng. SMTP integration test mới mô phỏng được các failure phases thực.

## 54. Test queued path: ưu tiên crash và transaction boundary

Các test quan trọng:

| Kịch bản | Kết quả kỳ vọng |
|---|---|
| Business transaction rollback | Không có outbox intent |
| Business commit thành công | Outbox intent tồn tại để worker lấy |
| Process crash sau commit trước dispatch | Intent không mất, worker khác có thể tiếp tục |
| Producer request retry cùng idempotency key | Không tạo duplicate business intent |
| Hai workers claim cùng row | Chỉ một claim thắng theo DB ownership |
| Worker crash khi CLAIMED, chưa SMTP | Reclaim an toàn theo state/lease policy |
| Worker crash khi SENDING | Không tự kết luận chưa gửi; đưa vào UNKNOWN/reconciliation |
| SMTP accepted nhưng DB update fail | Không replay mù và tạo duplicate |
| Broker redeliver sau ACK timeout | Consumer nhận diện durable state |
| Queue message có malformed job ID | Reject/quarantine theo policy, không kẹt queue |
| Provider SMTP outage | Retry có backoff và rate budget |
| Retry vượt expires_at | Không bắt đầu attempt mới |
| Người dùng unsubscribe sau enqueue | Worker SKIPPED, không gửi |
| Hard bounce suppression đến sau enqueue | Worker không bỏ qua current policy |
| Marketing burst | OTP/transactional không bị starvation quá SLA |
| DLQ replay | Có audit, idempotency, quyền operator |
| Outbox job bị xóa khỏi broker nhưng còn trong DB | Reconciliation/dispatcher tái phát khi hợp lệ |

### Test database claim thật

Khi dùng PostgreSQL **FOR UPDATE SKIP LOCKED**, cần integration test với database có cùng semantics và transaction isolation như production. Một unit test chỉ giả lập Queue bằng list trong bộ nhớ không chứng minh được tính nguyên tử của claim/update.

Giả lập:

~~~text
Thread A: claim next 1
Thread B: claim next 1

Given: 1 row PENDING

Assert:
  exactly one claim success
  unique claim token belongs to winning worker
~~~

Lặp test với trạng thái job hết hạn, cancellation đang chạy và lease thay đổi. Không được reset worker status bỏ qua claim token trong implementation production.

### SMTP capture integration test

Với môi trường mail test có thể trả SMTP replies có chủ đích:

- Gửi một notification hợp lệ: captured mail count theo intent.
- Lỗi 4xx xác định: đưa RETRY_WAIT nếu còn deadline.
- Lỗi 5xx recipient invalid: ghi result theo recipient.
- Timeout sau DATA: status UNKNOWN, không assert chắc chắn chưa gửi.
- Handler/worker restart: không tạo duplicate khi durable state đã SUBMITTED.

Các công cụ như test SMTP server chỉ phục vụ kiểm chứng integration; không nên gửi email tới recipient thật khi test retry/cancellation.

## 55. Runbook: HTTP API chậm vì SMTP

Nếu đang dùng direct và API latency tăng:

1. Xem trace breakdown: business DB, render MIME, DNS/TCP/TLS, SMTP DATA, read timeout.
2. Kiểm tra SMTP connection/authentication failures, provider throttling, quota.
3. Xem số request threads bị chờ network và connection pool.
4. Kiểm tra email có attachment lớn hay template render chậm không.
5. Xác định endpoint có thật cần chờ SMTP result không.
6. Nếu email không phải điều kiện nghiệp vụ bắt buộc, cân nhắc durable queue/outbox để tách latency.
7. Không chỉ tăng HTTP timeout như giải pháp lâu dài.
8. Không chuyển sang @Async in-memory rồi tuyên bố đã đạt durable delivery.

### Nếu buộc tiếp tục direct

- Có bounded concurrency.
- Có SMTP timeouts.
- Có rate limit và input validation.
- Tránh I/O SMTP trong long-running DB transaction.
- Có explicit error outcome và support diagnostics.
- Có idempotency nếu caller retry request.

Những biện pháp này làm direct an toàn hơn trong giới hạn của nó, nhưng không tạo ra một durable retry queue nếu chưa có persistence.

## 56. Runbook: queue tăng mà SMTP vẫn gửi được

Khi **mail_outbox_pending** và **oldest_due_age** tăng:

### Bước 1 — Xác định nguồn backlog

- Producer tăng đột biến hay throughput worker giảm?
- Job nào đang tích tụ: marketing, OTP, invoice?
- Một tenant/campaign chiếm phần lớn không?
- Provider rate limit có thấp hơn rate tạo job không?
- Có retries lặp lại quá nhanh không?

### Bước 2 — Kiểm tra worker

- Active worker count và in-flight jobs?
- Claim query/index có chậm hoặc nhiều DB locks?
- Lease có quá ngắn khiến job bị đánh stale?
- Queue consumer prefetch quá cao, một worker giữ quá nhiều messages?
- SMTP connection/authentication/timeout có thay đổi?

### Bước 3 — Xem policy và deadline

- Có job đã quá hạn cần EXPIRED, không nên gửi muộn?
- Campaign bị tạm dừng nhưng vẫn enqueue?
- Có consent/suppression đổi khiến nhiều job SKIPPED?
- Priority/quotas có làm security stream bị starvation?

### Bước 4 — Hành động

- Điều tiết producer/campaign.
- Tăng workers khi **provider quota và DB capacity thực sự cho phép**.
- Sửa index/claim contention.
- Điều chỉnh retry backoff, circuit breaker.
- Áp dụng expiry policy cho email hết giá trị.
- Tách stream/priority pools nếu hiện tại bị head-of-line blocking.
- Giữ UNKNOWN cần reconciliation; không chuyển tất cả SENDING về PENDING.

### Bước 5 — Xác minh phục hồi

Theo dõi:

~~~text
queue_wait_p95 / p99
oldest_due_age
SMTP accepted rate
provider 4xx/5xx rate
retry_wait count
unknown count
expired_due_to_capacity count
~~~

Đánh giá theo **stream và recipient**, không chỉ tổng throughput.

## 57. Runbook: email được gửi trùng

Một số nguyên nhân:

~~~text
Client retry -> tạo 2 intent IDs
      |
Broker retry -> cùng intent được deliver 2 lần
      |
Worker A lease expired -> Worker B sends again
      |
SMTP accepted -> result DB update failed
      |
Provider timeout after DATA -> retry without reconciliation
      |
Direct fallback and queue both send same notification
~~~

Quy trình:

1. Xác định **có hai business intents khác nhau** hay cùng một intent được retry.
2. Xem unique business key/recipient, outboxId và provider message IDs.
3. Kiểm tra attempt history và SMTP phase của từng lần.
4. Kiểm tra producer idempotency, broker ACK, queue re-delivery, lease và stale workers.
5. Nếu có failover provider, kiểm tra primary outcome trước khi secondary gửi.
6. Sửa state transitions/ownership, không chỉ thêm một if trên Subject/Message-ID.
7. Đánh dấu những notification chưa rõ là UNKNOWN và đối soát.
8. Kiểm thử lại crash windows có thể gây duplicate.

Đừng xóa attempt history khi điều tra duplicate; nó là bằng chứng phân biệt lỗi enqueue với lỗi SMTP.

## 58. Anti-pattern và cách thay thế

| Anti-pattern | Hậu quả | Thay thế |
|---|---|---|
| Gửi SMTP trong @Transactional business method | DB lock dài, rollback không thu hồi email | Outbox transactionally, send sau commit |
| Cho rằng @Async là durable queue | Mất job khi JVM crash | Persist intent hoặc chấp nhận best effort |
| Commit DB rồi publish broker không có outbox | Dual-write gap mất event | Transactional outbox |
| Publish broker trước business DB commit | Email về nghiệp vụ rollback | Atomic intent hoặc consistency model |
| ACK trước khi lưu outcome | Crash mất việc | Commit durable state trước ACK |
| ACK sau SMTP và giả định exactly-once | Redelivery có thể gửi trùng | Idempotency/UNKNOWN/reconciliation |
| Reset mọi stale SENDING về PENDING | Duplicate sau SMTP accepted | Phân biệt CLAIMED và UNKNOWN |
| Retry tất cả MailException | Retry cả permanent/ambiguous errors | Classifier + deadline/backoff |
| Queue vô hạn để hấp thụ overload | Backlog chỉ tăng, email lỗi thời | Admission/backpressure/capacity |
| Một FIFO cho OTP và marketing | OTP bị starvation | Priority/stream isolation |
| Thêm workers vượt provider quota | Throttling tăng | Provider token bucket/concurrency cap |
| Gắn trạng thái DELIVERED khi send() return | Báo sai kết quả | SUBMITTED + provider feedback |
| Tạo một job cho nhiều tenant recipients | Data isolation/partial results khó | Per-tenant/per-recipient jobs |
| Đẩy nguyên attachment vào broker | Broker bloat/PII risk | Durable object reference |
| Dùng template latest không pin version | Email replay khác nội dung gốc | Version/snapshot strategy |
| Tin consent snapshot khi enqueue | Gửi sau unsubscribe | Final eligibility gate |
| Tự direct fallback khi queue timeout | Gửi trùng | Durable intent + dispatcher retry |
| Dùng Message-ID làm khóa exactly-once | Không có SMTP dedup guarantee | Business idempotency/attempt state |
| Không có DLQ/replay procedure | Poison message nghẽn pipeline | Quarantine, controlled replay |
| Dùng email address làm Prometheus label | High cardinality và PII | Bounded dimensions, secured lookup |
| Chỉ đo HTTP latency của queue producer | Không thấy mail gửi trễ | Queue wait + SMTP result + delivery feedback |
| Quên cleanup/archive terminal outbox | DB phình và query chậm | Retention/partitioning/audit store |
| Broker có rồi nên luôn dùng Kafka | Tăng phức tạp không cần thiết | Chọn theo workload, semantics và team |

## 59. Checklist trước khi chốt kiến trúc

**Mục tiêu nghiệp vụ**

1. Email nào thực sự cần gửi và loại nào chỉ là best-effort notification?
2. Đã xác định khi nào HTTP được phép trả success chưa?
3. Có phân biệt **QUEUED**, **SUBMITTED** và **DELIVERED** không?
4. Độ trễ tối đa của OTP/security/campaign có được đo bằng end-to-end SLI phù hợp không?
5. Email gửi muộn còn hữu ích hay phải EXPIRED?
6. Có chấp nhận rủi ro duplicate SMTP trong những crash windows nhất định không?

**Chọn cơ chế**

7. Direct có thực sự cần phản hồi transport ngay không?
8. Nếu dùng @Async, đội phát triển hiểu đây là in-memory best effort chứ?
9. Nếu queue cần durable, producer có bảo đảm lưu intent sau business commit không?
10. Khi business state và email intent cùng DB, có được commit trong một transaction không?
11. Chọn database jobs hay broker dựa trên throughput, recovery, đội vận hành chưa?
12. Nếu dùng broker, ACK/offset, publisher confirm và DLQ đã được cấu hình chưa?
13. Có tránh direct fallback gây duplicate khi broker timeout không?

**State và idempotency**

14. Có unique key cho business event/recipient/notification type không?
15. Có claim token, lease và state transitions có điều kiện không?
16. Worker có nhận diện những job đã terminal khi broker redeliver không?
17. Có trạng thái **UNKNOWN** cho outcome SMTP mơ hồ không?
18. Có attempt history và provider correlation khi cần đối soát không?
19. Có ngăn worker cũ cập nhật DB khi mất lease không?
20. Có phân biệt idempotent business action với SMTP delivery không?

**Capacity, retry và policy**

21. Có rate/concurrency limit theo provider, stream và tenant không?
22. Có cảnh báo oldest due age, queue wait p95/p99 và throughput giảm không?
23. Có retry classifier cho transient/permanent/ambiguous errors không?
24. Retry có backoff, jitter, max attempts và deadline không?
25. Có priority/isolated capacity để marketing không làm chậm OTP không?
26. Có final consent/suppression/business eligibility gate trước send không?
27. Có cách expire/skip job không còn giá trị mà không gọi SMTP không?
28. Có backpressure khi producer rate vượt provider rate không?

**Bảo mật và vận hành**

29. Có kiểm tra sender profile thuộc đúng tenant không?
30. Queue chỉ chứa metadata/ref tối thiểu thay vì raw attachment/secret chứ?
31. Broker, DB, object storage và DLQ có retention/ACL phù hợp không?
32. Logs/metrics có tránh lộ recipient, Subject, token và nội dung không?
33. Có runbook khi SMTP outage, backlog, duplicate và UNKNOWN không?
34. Có owner cho replay/dead-letter và quyền thao tác admin không?
35. Có đối soát dữ liệu delivery/bounce webhook nếu provider hỗ trợ không?
36. Có kế hoạch cleanup/archive outbox sau thời gian retention không?

**Kiểm thử**

37. Test business rollback và crash ngay sau commit đã được thiết kế chưa?
38. Test hai worker claim cùng row và stale lease chưa?
39. Test broker redelivery sau commit trước ACK chưa?
40. Test accepted SMTP nhưng DB update fail chưa?
41. Test timeout sau DATA và policy UNKNOWN chưa?
42. Test unsubscribe sau enqueue và expiry trước send chưa?
43. Test burst marketing ảnh hưởng security/transactional chưa?
44. Test failover provider và duplicate-risk boundary chưa?

Checklist này là **công cụ thiết kế/đánh giá triển khai**. Bản thân Spring Framework Mail không tự đáp ứng tất cả các bảo đảm trên chỉ vì đã thêm một dependency hoặc annotation.

## 60. Tổng kết: chọn theo trách nhiệm và mức bảo đảm

Không có phương án luôn tốt nhất. **Direct, @Async, database queue và broker queue nằm ở những mức độ phức tạp và bảo đảm khác nhau**.

| Câu hỏi cốt lõi | Hướng quyết định |
|---|---|
| Có cần nhận SMTP response trong cùng thao tác người dùng không? | Cân nhắc **direct** với timeout/rate/authorization |
| Có chấp nhận mất notification khi JVM crash không? | Nếu có, **best effort** có thể đủ |
| Có phải lưu ý định gửi cùng business transaction không? | Dùng **transactional outbox** |
| Có cần retry, campaign, quota và worker độc lập không? | Dùng **durable queue/outbox** |
| Quy mô lớn, nhiều service, cần buffer/fan-out? | Cân nhắc **broker**, thường kết hợp outbox |
| Email có TTL ngắn hoặc cần gửi nhanh? | Chọn **priority lane và đo queue wait**, không chỉ HTTP latency |
| Có yêu cầu không gửi trùng tuyệt đối? | Làm rõ giới hạn SMTP, **idempotency và UNKNOWN reconciliation** |
| Có cần giảm rủi ro outage? | **Durable intent + bounded retries + backpressure** |

Một công thức thiết kế thực tế cho ứng dụng Spring quan trọng về nghiệp vụ:

~~~text
Business event
     |
     v
BEGIN DB TRANSACTION
  Save business change
  Save notification intent (unique business key)
COMMIT
     |
     v
Durable outbox / broker
     |
     v
Claim + current-policy check + deadline
     |
     v
Compose MIME from versioned template and safe references
     |
     v
JavaMailSender.send(...)
     |
     +-- Accepted -> SUBMITTED + feedback correlation
     +-- Transient -> RETRY_WAIT + backoff
     +-- Permanent -> FAILED/SKIPPED by policy
     +-- Ambiguous -> UNKNOWN + reconciliation
     |
     v
Metrics, audit, provider delivery/bounce events
~~~

**Gửi trực tiếp** vẫn là lựa chọn tốt cho những nhu cầu nhỏ, có kiểm soát và thực sự cần phản hồi SMTP ngay. Nhưng khi email là một trách nhiệm nghiệp vụ không được làm mất sau commit, **lưu ý định gửi bền vững và xử lý bằng worker** thường tạo ra một kiến trúc có khả năng phục hồi, đo lường và vận hành tốt hơn.

**Điểm quan trọng nhất không phải “có queue hay không”, mà là hệ thống tuyên bố đã nhận trách nhiệm gì, đã ghi lại trách nhiệm đó ở đâu, và có thể xử lý trung thực từng trường hợp thành công, thất bại, gửi trùng hoặc chưa rõ kết quả như thế nào.**









