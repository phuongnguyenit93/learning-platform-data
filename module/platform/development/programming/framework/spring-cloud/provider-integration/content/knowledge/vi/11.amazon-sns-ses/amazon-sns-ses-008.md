# Chọn SNS, SQS hay SES theo mục đích giao tiếp

## 1. Bài toán và mục tiêu học tập

Một ứng dụng thương mại điện tử viết bằng Spring Boot cần thực hiện ba việc sau khi khách đặt hàng:

- Phát sự kiện **ORDER_CREATED** tới dịch vụ kho, phân tích và chăm sóc khách hàng.
- Lưu công việc gửi email xác nhận để worker xử lý khi có năng lực.
- Gửi email giao dịch có nội dung HTML, template, tệp đính kèm và theo dõi bounce/complaint.

**Amazon Simple Notification Service (SNS)**, **Amazon Simple Queue Service (SQS)** và **Amazon Simple Email Service (SES)** đều có thể xuất hiện trong hệ thống này, nhưng chúng giải quyết các vấn đề khác nhau:

- **SNS** phân phối thông báo từ một publisher đến một hoặc nhiều subscriber theo mô hình publish/subscribe.
- **SQS** lưu message trong queue để một hoặc nhiều consumer chủ động lấy và xử lý bất đồng bộ.
- **SES** gửi email tới người nhận qua hạ tầng email của AWS, hỗ trợ danh tính gửi, xác thực domain và phản hồi chuyển phát.

Bài học thuộc chương **Amazon SNS và SES** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; người học cần biết chọn dịch vụ, cấu hình danh tính/quyền, bảo vệ secret, kiểm thử và đánh giá trade-off giữa các provider.

Sau bài này, bạn có thể:

1. Chọn SNS, SQS hoặc SES theo mục đích giao tiếp.
2. Phân biệt broadcast/fan-out, work queue, email delivery và các guarantee vận hành.
3. Thiết kế kiến trúc kết hợp SNS + SQS + SES thay vì cố dùng một dịch vụ cho mọi nhiệm vụ.
4. Tích hợp publisher, queue consumer và mail sender trong Spring Boot.
5. Xác định nơi đặt retry, DLQ, idempotency, IAM policy và observability.
6. Tránh các anti-pattern như dùng SNS thay queue lưu công việc, dùng SES như message broker hoặc gửi email đồng bộ trong transaction đặt hàng.

## 2. Bản chất của SNS, SQS và SES

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    SNS(("Amazon SNS<br/>Publish / Subscribe"))
    SQS["Amazon SQS<br/>Durable queue"]
    SES(("Amazon SES<br/>Email delivery"))
    SYS["Các service / subscriber"]
    WORKER["Queue workers"]
    MAIL["Hộp thư người nhận"]

    APP -->|"Publish event"| SNS
    SNS -->|"Push notification"| SYS
    SNS -->|"Fan-out"| SQS
    APP -->|"Send work item"| SQS
    SQS -->|"Poll / consume"| WORKER
    WORKER -->|"Send email"| SES
    SES -->|"SMTP delivery"| MAIL
~~~

| Thuộc tính | **SNS** | **SQS** | **SES** |
| --- | --- | --- | --- |
| Mục đích chính | Phân phối thông báo | Lưu đệm và xếp hàng công việc | Gửi email |
| Mô hình | Publisher → topic → subscribers | Producer → queue → consumers | Sender → SES → mail servers |
| Cách nhận | SNS chủ động giao đến endpoint (push) | Consumer chủ động lấy message (poll/pull; có thể được Lambda event source mapping hỗ trợ) | Người nhận nhận qua hệ thống email |
| Số consumer | Một topic có nhiều subscription độc lập | Nhiều worker cùng đọc một queue theo kiểu competing consumers | Nhiều người nhận email, có thể To/Cc/Bcc |
| Lưu trữ | Không phải nơi lưu message dài hạn để consumer tùy ý đọc lại | Giữ message trong retention period, tối đa 14 ngày | Không phải queue lưu tác vụ email của ứng dụng |
| Lọc | Filter policy ở subscription | Consumer tự quyết định sau khi đọc; có thể dùng nhiều queue/logic | Không định tuyến nghiệp vụ message như SNS |
| Tác vụ tiêu biểu | Phát sự kiện, fan-out, cảnh báo | Buffer, load leveling, retry công việc | Email giao dịch, email marketing có consent |
| Xử lý lỗi | Retry giao đến subscription; có thể dùng subscription DLQ | Visibility timeout, redrive policy, SQS DLQ | Bounce, complaint, reject, delivery delay và suppression |

**Một cách nhớ nhanh:**

- Muốn **phát một thông báo cho nhiều hệ thống** → nghĩ đến **SNS**.
- Muốn **giữ một công việc cho worker xử lý khi sẵn sàng** → nghĩ đến **SQS**.
- Muốn **gửi email cho con người** → nghĩ đến **SES**.

Các dịch vụ có thể kết hợp: SNS phát sự kiện, SQS giữ công việc riêng cho từng nhóm consumer, worker gọi SES để gửi email. Đây thường là cách thiết kế rõ trách nhiệm và dễ vận hành.

## 3. Khi nào chọn SNS?

### 3.1. SNS là tầng phân phối thông báo

Publisher gửi message tới một **topic**. SNS xét các subscription và chuyển message tới endpoint phù hợp. Một topic có thể có nhiều subscription, chẳng hạn SQS queue cho worker gửi email, SQS queue cho dịch vụ phân tích, Lambda cho tác vụ cập nhật cache, HTTPS endpoint cho webhook đối tác, hoặc email/SMS cho thông báo đơn giản được endpoint xác nhận/cấu hình.

SNS phù hợp khi publisher không cần biết danh sách người nhận và cần mở rộng thêm subscriber mà không thay đổi logic phát sự kiện.

~~~mermaid
flowchart LR
    P["Order Service"] --> T(("SNS topic<br/>order-events"))
    T --> Q1["SQS<br/>inventory-jobs"]
    T --> Q2["SQS<br/>analytics-jobs"]
    T --> Q3["SQS<br/>notification-jobs"]
    T --> L["Lambda<br/>cache invalidation"]
~~~

### 3.2. Các đặc tính cần cân nhắc

**SNS Standard** phù hợp thông lượng cao và các thông báo độc lập. Cần thiết kế consumer chịu được **at-least-once delivery**, message có thể lặp và thứ tự không được bảo đảm tuyệt đối.

**SNS FIFO** phù hợp khi cần thứ tự theo message group và deduplication trong phạm vi dịch vụ hỗ trợ. Với nhánh SQS FIFO, thiết kế **MessageGroupId** theo aggregate (ví dụ orderId) và **MessageDeduplicationId** ổn định. FIFO không loại bỏ yêu cầu idempotency ở tác động nghiệp vụ.

**Subscription filter policy** cho phép mỗi subscriber nhận loại message cần thiết. Ví dụ queue email nhận ORDER_CREATED, queue refund nhận ORDER_CANCELLED. Filter giảm lượng message không cần xử lý nhưng không thay thế authorization.

### 3.3. Khi không nên dùng SNS một mình

Không dùng SNS làm nơi lưu công việc để worker có thể dừng vài giờ rồi đọc lại tùy ý. SNS có retry theo protocol và subscription DLQ, nhưng không cung cấp mô hình retention/visibility/consumer acknowledgment giống SQS. Nếu endpoint là worker cần kiểm soát tốc độ và xử lý lại, kết hợp **SNS → SQS**.

SNS subscription trực tiếp tới email phù hợp thông báo đơn giản, ví dụ cảnh báo vận hành. Nó không thay thế dịch vụ email giao dịch cần template, MIME, quản lý identity, suppression, bounce và complaint. Với yêu cầu đó, dùng **SES**.

## 4. Khi nào chọn SQS?

### 4.1. SQS là hàng đợi công việc

Producer gửi message vào queue. Worker lấy message, xử lý và xóa message sau khi hoàn tất. Nếu worker chết hoặc không xóa, message có thể xuất hiện lại sau **visibility timeout**.

~~~mermaid
sequenceDiagram
    participant P as "Spring Boot Producer"
    participant Q as "SQS queue"
    participant W1 as "Worker A"
    participant W2 as "Worker B"

    P->>Q: SendMessage(job)
    W1->>Q: ReceiveMessage
    Q-->>W1: Job + receipt handle
    Note over W1: Xử lý job
    W1->>Q: DeleteMessage
    W2->>Q: ReceiveMessage (job khác)
~~~

Nhiều worker đọc cùng một queue theo mô hình **competing consumers**: một message thông thường được giao cho một consumer xử lý tại một thời điểm, không phải broadcast đến mọi worker. SQS Standard vẫn có thể giao lặp, nên consumer phải idempotent.

### 4.2. Vì sao queue giúp điều tiết tải?

Giả sử hệ thống nhận 500 đơn hàng trong một phút, nhưng dịch vụ gửi email chỉ có thể xử lý 100 email/phút. Nếu gọi SES đồng bộ ngay trong request đặt hàng, thời gian phản hồi và lỗi email có thể ảnh hưởng đến luồng đặt hàng.

Với SQS:

1. API ghi nhận order và tạo công việc gửi email.
2. Worker lấy công việc theo năng lực.
3. Khi SES throttling hoặc tạm lỗi, worker retry theo chiến lược có giới hạn.
4. Message không xử lý được sau số lần nhận tối đa được chuyển vào **SQS DLQ**.
5. API đặt hàng không phải chờ email hoàn tất.

SQS Standard giữ message tối đa **14 ngày**; thời gian retention, visibility timeout, long polling và redrive policy cần được cấu hình theo SLA công việc. Visibility timeout phải đủ cho thời gian xử lý bình thường; nếu công việc kéo dài, worker có thể gia hạn bằng **ChangeMessageVisibility**.

### 4.3. Standard và FIFO

| Tiêu chí | **SQS Standard** | **SQS FIFO** |
| --- | --- | --- |
| Thứ tự | Best effort; có thể không đúng thứ tự | Theo từng MessageGroupId |
| Delivery | At-least-once; có thể trùng | Deduplication trong cửa sổ giới hạn, thứ tự trong group |
| Throughput | Phù hợp thông lượng cao, mở rộng linh hoạt | Có giới hạn và mô hình throughput theo cấu hình |
| Dùng khi | Tác vụ độc lập, consumer idempotent | Các thao tác cùng aggregate cần tuần tự |

**Exactly-once processing** của FIFO cần hiểu đúng: dịch vụ hỗ trợ deduplication và ngữ nghĩa nhận/xóa trong phạm vi được mô tả, nhưng không tạo transaction nguyên tử với database, SES hay API bên ngoài. Nếu worker gọi SES xong rồi chết trước khi xóa message, công việc có thể được thực hiện lại. Dùng idempotency key, bảng trạng thái hoặc outbox để hạn chế email trùng.

### 4.4. Khi nào không nên dùng SQS một mình?

Nếu ba hệ thống độc lập đều cần nhận **mọi** sự kiện, dùng một queue duy nhất với ba consumer sẽ khiến các consumer cạnh tranh nhau và message không được broadcast. Có hai lựa chọn:

- Tạo ba queue riêng và publisher gửi từng queue, nhưng publisher phải biết các queue và tự quản lý fan-out.
- Dùng **SNS topic → ba SQS queue**, để SNS thực hiện phân phối và mỗi queue giữ bản sao độc lập cho consumer của mình.

Nếu nhu cầu chỉ là gửi email tới khách hàng, SQS chỉ giữ tác vụ; nó không thực hiện gửi email. Worker cần gọi **SES** hoặc một email provider khác.

## 5. Khi nào chọn SES?

### 5.1. SES là dịch vụ email, không phải broker

SES chuyên xử lý email: xác minh domain/email identity, DKIM, gửi SMTP/API, configuration set, event publishing, bounce, complaint, suppression và quota. Nó không cung cấp semantics queue để ứng dụng poll và ack một công việc.

Các tình huống phù hợp: email xác nhận đơn hàng và biên nhận; reset password, OTP và email bảo mật; thông báo trạng thái tài khoản; email marketing khi có consent, unsubscribe và quản lý reputation phù hợp; gửi MIME/HTML, template và attachment theo yêu cầu nghiệp vụ.

### 5.2. Điều kiện để email được gửi

Ứng dụng cần verified identity ở đúng SES region, From address được phép gửi, IAM permission nếu dùng SES API hoặc SES SMTP credentials nếu dùng SMTP, account được phép gửi tới recipient tương ứng (sandbox/production), quota/rate limit còn đủ và quy trình xử lý bounce, complaint, suppression.

**SES API** có thể được tích hợp với Spring Cloud AWS qua **MailSender/JavaMailSender** hoặc SDK trực tiếp. **SES SMTP** có thể dùng Spring Boot Mail. Hai cơ chế xác thực khác nhau: API dùng AWS credentials provider chain/IAM role; SMTP dùng SES SMTP username/password riêng.

### 5.3. Send thành công chưa phải delivery

Một lời gọi send thành công thường chỉ cho biết SES đã chấp nhận yêu cầu. Sau đó mail server đích có thể chấp nhận, từ chối, trì hoãn hoặc người nhận báo spam. Ứng dụng cần theo dõi event:

| Event | Ý nghĩa |
| --- | --- |
| **Send** | SES ghi nhận yêu cầu gửi |
| **Delivery** | Mail server đích chấp nhận email |
| **Bounce** | Email không thể giao tới người nhận |
| **Complaint** | Người nhận báo spam |
| **Reject** | SES từ chối message |
| **DeliveryDelay** | Giao thư bị trì hoãn do vấn đề tạm thời |

**Delivery không chứng minh người nhận đã đọc thư hoặc thư nằm trong inbox chính.** Bounce/complaint phải cập nhật suppression và preference; hard bounce không được retry như lỗi mạng tạm thời.

## 6. Chọn dịch vụ theo tình huống

| Yêu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Một sự kiện cần báo cho nhiều service độc lập | **SNS** | Một topic có nhiều subscription |
| Một công việc cần lưu để worker xử lý sau | **SQS** | Retention, visibility timeout, ack/delete, DLQ |
| Nhiều service cần nhận bản sao sự kiện và xử lý độc lập | **SNS + mỗi subscriber một SQS queue** | Fan-out và buffer riêng từng consumer |
| Gửi email xác nhận cho khách hàng | **SES** | Email identity, nội dung MIME, delivery feedback |
| Gửi email nhưng không muốn chặn API đặt hàng | **SQS + worker + SES** | Tách nhận đơn khỏi gửi thư |
| Cần email bounce/complaint về hệ thống | **SES + SNS/EventBridge + SQS** | SES phát feedback event; queue giúp worker xử lý |
| Cần thông báo vận hành đơn giản qua email | **SNS email subscription** có thể phù hợp | Cấu hình endpoint xác nhận nhanh; nội dung/khả năng giới hạn |
| Worker cần xử lý message theo thứ tự trong từng order | **SQS FIFO**, có thể kết hợp SNS FIFO | MessageGroupId và deduplication |
| Ba worker cùng cần xử lý mọi message | **SNS + ba SQS queue** | Một queue chung sẽ tạo competing consumers, không broadcast |

### 6.1. Decision tree

~~~mermaid
flowchart TD
    A{"Bạn muốn giao tiếp với ai?"}
    A -->|"Người nhận email"| E["SES"]
    A -->|"Một hoặc nhiều hệ thống"| B{"Một công việc hay thông báo cho nhiều consumer?"}
    B -->|"Một nhóm worker xử lý chung"| Q["SQS"]
    B -->|"Nhiều consumer độc lập"| N["SNS topic"]
    N --> C{"Consumer cần buffer/retry độc lập?"}
    C -->|"Có"| F["SNS → một SQS queue cho mỗi consumer"]
    C -->|"Không"| D["SNS → endpoint phù hợp"]
    E --> G{"Gửi ngay hay cần buffer?"}
    G -->|"Gửi ngay, tải nhỏ"| H["Spring Mail → SES"]
    G -->|"Bất đồng bộ / rate control"| I["SQS → mail worker → SES"]
~~~

Decision tree là gợi ý khởi đầu. Quyết định cuối cùng còn phụ thuộc delivery guarantee, throughput, thứ tự, chi phí, thời gian lưu, loại endpoint, bảo mật và năng lực vận hành.

## 7. Các kiến trúc kết hợp thường gặp

### 7.1. Work queue: SQS cho một nhóm worker

~~~mermaid
flowchart LR
    API["Order API"] -->|"SendMessage"| Q["SQS<br/>invoice-jobs"]
    Q --> W1["Invoice worker A"]
    Q --> W2["Invoice worker B"]
    W1 --> DB[("Database")]
    W2 --> DB
~~~

Dùng khi một công việc cần được xử lý bởi một worker trong nhóm. Nhiều worker cùng poll queue giúp tăng throughput; message không được broadcast cho từng worker. Nếu worker lỗi, visibility timeout và redrive policy quyết định message được thử lại và chuyển DLQ.

### 7.2. Fan-out: SNS + SQS cho từng consumer

~~~mermaid
flowchart LR
    P["Order Service"] --> T(("SNS<br/>order-events"))
    T --> Q1["SQS<br/>inventory"]
    T --> Q2["SQS<br/>analytics"]
    T --> Q3["SQS<br/>email-jobs"]
    Q1 --> W1["Inventory worker"]
    Q2 --> W2["Analytics worker"]
    Q3 --> W3["Email worker"]
~~~

Dùng khi mỗi service cần nhận và xử lý độc lập. Nếu analytics ngừng hoạt động, queue analytics giữ message trong retention; worker inventory vẫn có thể tiếp tục xử lý queue của mình. Publisher không cần gọi từng worker.

### 7.3. Gửi email giao dịch qua queue

~~~mermaid
flowchart LR
    O["Order Service"] -->|"Create notification job"| Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Mail Worker"]
    W --> SES(("Amazon SES"))
    SES --> M["Customer mailbox"]
    SES -->|"Bounce / Complaint"| FB(("SNS / EventBridge"))
    FB --> FQ["SQS<br/>email-feedback"]
    FQ --> FW["Feedback worker"]
    FW --> DB[("Suppression / consent")]
~~~

Đây là mẫu thường dùng cho email giao dịch:

1. Order Service tạo notification job và lưu trạng thái trong DB/outbox.
2. Email worker đọc job từ SQS, kiểm tra idempotency và gửi qua SES.
3. Worker cập nhật trạng thái theo kết quả API, ghi lại SES MessageId nếu có.
4. SES phát delivery/bounce/complaint event qua destination đã cấu hình.
5. Feedback worker cập nhật trạng thái, suppression hoặc preference.
6. DLQ và dashboard giúp phát hiện job không thể xử lý.

Nếu email phải gửi sau khi order commit, dùng **transactional outbox** để ghi sự kiện cùng transaction. Tránh gọi SES trong transaction database; lỗi mạng hoặc throttling có thể kéo dài transaction và khiến trải nghiệm đặt hàng bị ảnh hưởng.

### 7.4. SNS trực tiếp tới email hay SES?

| Nhu cầu | SNS email subscription | SES |
| --- | --- | --- |
| Cảnh báo đơn giản cho nhóm người nhận đã xác nhận | Phù hợp | Có thể dùng nhưng có thể quá nhiều cấu hình |
| Email giao dịch cá nhân hóa theo order | Hạn chế | Phù hợp |
| HTML template, MIME, attachment | Không phải mục tiêu chính | Phù hợp |
| Domain identity, DKIM, custom MAIL FROM | Không phải bộ tính năng email chuyên dụng | Có |
| Theo dõi bounce/complaint/suppression ở mức email | Không thay thế SES feedback | Có |
| Broadcast notification text tới email endpoint | Phù hợp | Có thể xây worker nếu cần nghiệp vụ email |

Không coi SNS email subscription là cách thay thế SES cho mọi email ứng dụng. SNS phù hợp gửi nội dung thông báo đơn giản; SES phù hợp khi email là một phần chính thức của sản phẩm.

## 8. Tích hợp Spring Boot: ví dụ lựa chọn theo từng vai trò

Các ví dụ sử dụng **Spring Cloud AWS 3.x** (package **io.awspring.cloud**) và **Spring Boot 3**. Chọn một phiên bản BOM tương thích với Spring Boot đang dùng; không trộn API thế hệ cũ.

### 8.1. Publisher: Spring Boot → SNS

Dependency:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
app:
  sns:
    order-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

Ví dụ publish POJO:

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public OrderEventPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void publish(OrderCreated event) {
        snsTemplate.sendNotification(topicArn, event, "Order created");
    }

    public record OrderCreated(
            String eventId, String orderId, String eventType) {}
}
~~~

Ứng dụng cần IAM role có **sns:Publish** trên topic ARN. Publisher không cần quyền **sqs:SendMessage** nếu chỉ publish lên SNS. Topic subscription và queue policy được quản lý ở hạ tầng.

### 8.2. Consumer: Spring Boot ← SQS

Dependency:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")
}
~~~

Listener:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class EmailJobListener {
    private final EmailJobProcessor processor;

    public EmailJobListener(EmailJobProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("email-jobs")
    public void receive(EmailJob job) {
        processor.processIdempotently(job);
    }
}
~~~

**EmailJobProcessor** cần xử lý idempotent theo eventId/job ID. Với acknowledgement mode mặc định phù hợp của container, message được xác nhận khi xử lý thành công; nếu xử lý thất bại, message có thể được thử lại theo cấu hình. Kiểm tra cấu hình listener/acknowledgement của phiên bản AWSpring đang dùng trước khi tùy chỉnh.

Worker cần IAM permission **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes** trên queue được giao; queue retention, visibility timeout và redrive policy được thiết lập ở SQS.

### 8.3. Email worker: Spring Boot → SES

Dependency SES API qua Spring Cloud AWS:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")
}
~~~

Ví dụ MailSender:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailSender {
    private final MailSender mailSender;

    public TransactionalEmailSender(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String from, String recipient, String subject, String text) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);
        mailSender.send(message);
    }
}
~~~

SES identity phải được xác minh ở đúng region, account phải có quyền gửi phù hợp, và IAM role cần action SES tương ứng (ví dụ **ses:SendEmail**). Nếu gửi MIME/attachment qua JavaMailSender của AWSpring, kiểm tra thêm **ses:SendRawEmail** và Jakarta Mail dependencies.

### 8.4. Quyền IAM theo vai trò

| Workload | Quyền tối thiểu tiêu biểu | Không cần nếu chỉ làm đúng vai trò |
| --- | --- | --- |
| Order publisher | **sns:Publish** trên topic cụ thể | SQS Receive/Delete, SES Send |
| Email worker | **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes**; **ses:SendEmail** nếu gửi SES | SNS CreateTopic/Subscribe |
| Analytics worker | Quyền đọc/xóa queue analytics | SES Send, SNS Publish |
| Feedback worker | Quyền đọc/xóa feedback queue và quyền cập nhật DB | SNS Publish business events |

Đối với SNS → SQS, queue resource policy cần cho **sns.amazonaws.com** thực hiện **sqs:SendMessage** và giới hạn bằng **aws:SourceArn** của topic. IAM role của publisher không thay thế queue policy. Với KMS encryption, bổ sung quyền/key policy cần thiết cho từng principal.

## 9. Reliability: retry, DLQ và idempotency ở đúng nơi

| Dịch vụ/đường đi | Nơi cấu hình xử lý lỗi | Điều cần thiết kế |
| --- | --- | --- |
| Publisher → SNS | Retry phía publisher, outbox nếu cần | Timeout không chắc request chưa được nhận; event ID ổn định |
| SNS → endpoint subscription | Retry delivery của SNS và **subscription DLQ** khi hỗ trợ | Kiểm tra endpoint policy, delivery status và lỗi permanent |
| SNS → SQS | SNS delivery retry, SQS queue policy, subscription DLQ | Đảm bảo SNS được phép SendMessage; không nhầm filter mismatch với delivery failure |
| SQS → worker | Visibility timeout, redrive policy, **SQS DLQ** | Idempotency, maxReceiveCount, xử lý message poison |
| Worker → SES | Retry có giới hạn, quota/rate control, outbox/job status | Tránh gửi email trùng khi timeout hoặc worker chết sau khi SES đã nhận |

**Hai loại DLQ cần phân biệt:**

- **SNS subscription DLQ:** nhận message SNS không giao được tới endpoint.
- **SQS consumer DLQ:** nhận message đã vào queue chính nhưng worker thất bại nhiều lần.

Một message bị **filter policy loại bỏ** không phải delivery failure; không nên trông đợi subscription DLQ nhận các message không khớp filter.

**Idempotency** quan trọng ở cả SQS worker và email sender. Standard queues/topic có at-least-once semantics; FIFO deduplication cũng không tạo transaction chung với SES hay database. Một khóa nghiệp vụ như **orderId + emailType + templateVersion** có thể giúp kiểm soát gửi trùng, nhưng cần lưu trạng thái gửi và xử lý các tình huống timeout không rõ kết quả.

## 10. Anti-pattern và cách cải thiện

| Anti-pattern | Vì sao có vấn đề | Thiết kế phù hợp |
| --- | --- | --- |
| Dùng SNS như queue để worker đọc lại sau vài giờ | SNS không có retention/visibility/ack semantics như SQS | SNS → SQS subscription |
| Dùng một SQS queue để broadcast tới nhiều service | Worker cạnh tranh, mỗi message không được gửi cho tất cả | Một queue riêng cho mỗi consumer, fan-out qua SNS |
| Dùng SES làm nơi lưu email job | SES gửi email, không quản lý backlog công việc ứng dụng | SQS giữ job, worker gửi qua SES |
| Gửi SES đồng bộ trong transaction đặt hàng | Kết nối mạng/throttling làm transaction dài và dễ lỗi | Outbox/SQS + email worker |
| Dựa vào API success để kết luận email delivered | SES có thể nhận request nhưng sau đó bounce/delay/suppression | Event publishing, feedback worker và dashboard |
| Retry vô hạn mọi lỗi | Lỗi quyền, identity hoặc hard bounce không tự hết | Phân loại lỗi permanent/transient và backoff |
| Cấp quyền Administrator cho mọi worker | Mở rộng phạm vi sự cố và tăng rủi ro | IAM least privilege theo role/resource |
| Dùng SNS email subscription cho email giao dịch phức tạp | Thiếu quy trình identity/template/feedback cần thiết | SES |

## 11. Chọn dịch vụ qua các tình huống thực tế

### Tình huống A: thông báo một sự kiện đến ba service

**Yêu cầu:** sau khi thanh toán, inventory, analytics và notification đều cần xử lý sự kiện riêng.

**Chọn:** SNS topic **payment-events** với ba SQS subscription.

**Lý do:** publisher chỉ publish một lần; từng queue giữ bản sao riêng, có worker và DLQ riêng. Dịch vụ analytics ngừng hoạt động không buộc inventory phải dừng xử lý.

### Tình huống B: xử lý ảnh nền

**Yêu cầu:** người dùng upload ảnh, hệ thống cần resize; nhiều worker có thể xử lý các ảnh khác nhau nhưng mỗi ảnh chỉ cần một worker thực hiện.

**Chọn:** SQS queue **image-resize-jobs**.

**Lý do:** đây là work queue, các worker cạnh tranh lấy job. Nếu sau khi resize cần thông báo nhiều service, có thể publish event kết quả lên SNS.

### Tình huống C: gửi email xác nhận đơn hàng

**Yêu cầu:** gửi email cá nhân hóa, HTML, kèm biên nhận và xử lý bounce.

**Chọn:** SQS **email-jobs** + worker + SES.

**Lý do:** SQS điều tiết tải và retry công việc; SES đảm nhiệm email delivery, identity và feedback. SNS có thể phân phối feedback event đến SQS hoặc hệ thống khác.

### Tình huống D: cảnh báo vận hành đến một nhóm email

**Yêu cầu:** gửi thông báo đơn giản khi một ngưỡng metric vượt giới hạn.

**Chọn:** SNS email subscription có thể đủ nếu endpoint đã xác nhận và nội dung không cần tùy biến sâu. Nếu cần template, domain gửi, tracking, bounce/complaint hoặc personalization, dùng SES.

### Tình huống E: công việc theo thứ tự của một đơn hàng

**Yêu cầu:** ORDER_CREATED → ORDER_PAID → ORDER_SHIPPED cần được xử lý tuần tự trong cùng aggregate.

**Chọn:** SQS FIFO hoặc SNS FIFO → SQS FIFO tùy số subscriber.

**Lý do:** MessageGroupId theo orderId giữ thứ tự trong nhóm. Consumer vẫn cần idempotent và kiểm soát side effect.

## 12. Checklist trước khi quyết định

Trước khi chọn dịch vụ, trả lời các câu hỏi:

- **Đối tượng giao tiếp:** service, worker hay người nhận email?
- **Mô hình nhận:** broadcast tới nhiều subscriber hay một worker trong nhóm?
- **Lưu trữ:** có cần giữ backlog và đọc lại trong nhiều giờ/ngày không?
- **Tải:** có cần buffer, rate control và load leveling không?
- **Thứ tự:** cần best effort hay thứ tự theo aggregate?
- **Delivery:** chấp nhận at-least-once, duplicate và retry ở mức nào?
- **Fan-out:** mỗi consumer có cần queue, retention và DLQ riêng không?
- **Email:** cần verified identity, HTML/MIME, attachment, template, bounce/complaint?
- **Bảo mật:** IAM role nào publish/consume/send, queue policy nào cho SNS?
- **Quan sát:** theo dõi SNS delivery, SQS age/depth/DLQ, SES bounce/complaint?
- **Vận hành:** ai chịu trách nhiệm replay, redrive, suppression và xử lý message poison?

Không có dịch vụ tốt nhất cho mọi bài toán. Chọn theo **semantics mà consumer cần**, rồi mới chọn Spring abstraction và cấu hình AWS tương ứng.

## 13. Bài tập và câu hỏi ôn tập

**Bài tập:** thiết kế luồng đặt hàng có ba nghiệp vụ: inventory, analytics và email confirmation. Vẽ kiến trúc và triển khai sandbox:

1. Order Service publish **ORDER_CREATED** lên SNS topic.
2. Tạo ba SQS queue độc lập cho inventory, analytics và email.
3. Dùng filter policy nếu từng nhánh chỉ nhận một số event type.
4. Viết Spring Boot listener cho mỗi queue; mỗi listener log event ID và xử lý idempotent.
5. Email worker gọi SES thông qua Spring **MailSender** hoặc **JavaMailSender**.
6. Bật SES event publishing để nhận bounce/complaint và cập nhật trạng thái.
7. Mô phỏng worker dừng, SES throttling và duplicate event; quan sát queue depth, retry và DLQ.
8. So sánh cách thiết kế với phương án publisher gọi trực tiếp ba service.

**Câu hỏi tự kiểm tra:**

1. Vì sao SNS phù hợp broadcast nhưng SQS phù hợp competing consumers?
2. Một message trong SQS Standard có thể được nhận nhiều lần trong trường hợp nào?
3. Vì sao SNS → mỗi consumer một SQS queue tốt hơn một queue chung khi cần fan-out?
4. SES khác SNS email subscription ở những khả năng nào?
5. Khi email worker không sẵn sàng, SQS giúp ích gì cho SES workflow?
6. Vì sao API SES success không chứng minh mail server đích đã giao thư?
7. DLQ của SNS subscription và DLQ của SQS worker xử lý lỗi ở giai đoạn nào?
8. Khi nào nên chọn FIFO và vì sao vẫn cần idempotency?
9. Vai trò nào cần **sns:Publish**, **sqs:ReceiveMessage** và **ses:SendEmail**?
10. Nếu cần vừa broadcast sự kiện vừa gửi email, vì sao không nên dùng SES thay SNS?

## 14. Tài liệu tham khảo

- [Amazon SNS — What is Amazon SNS?](https://docs.aws.amazon.com/sns/latest/dg/welcome.html): mô hình publish/subscribe, topic và subscriber.
- [Amazon SQS — What is Amazon SQS?](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html): queue, consumer và message retention.
- [Amazon SQS — Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html): cơ chế ẩn message trong lúc xử lý.
- [Amazon SQS — Dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html): redrive và xử lý message lỗi.
- [Amazon SNS — Message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html): filter policy theo subscription.
- [Amazon SNS — SNS to SQS fan-out](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html): phân phối message từ topic đến queue.
- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): identity, sandbox và gửi email.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): delivery, bounce, complaint và event destination.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html): SNS, SQS và SES integration cho Spring Boot.

**Kết quả mong đợi:** người học chọn đúng dịch vụ theo mục đích: **SNS để phân phối sự kiện, SQS để lưu và điều phối công việc, SES để gửi email**; đồng thời biết kết hợp chúng thành kiến trúc Spring Boot bất đồng bộ, có kiểm soát quyền, retry, DLQ và feedback.
