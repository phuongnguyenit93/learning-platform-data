# Tích hợp Amazon SES với cơ chế gửi thư của Spring

## 1. Bài toán và kết quả học tập

Ứng dụng đặt hàng viết bằng **Spring Boot** cần gửi email xác nhận đơn, biên nhận PDF và thông báo thay đổi trạng thái. Ứng dụng đã có lớp nghiệp vụ gọi **MailSender** hoặc **JavaMailSender**, nhưng cần gửi email qua dịch vụ managed của AWS thay vì tự vận hành máy chủ SMTP.

**Amazon Simple Email Service (Amazon SES)** là dịch vụ gửi email của AWS. **Spring Cloud AWS** có thể triển khai trực tiếp các abstraction gửi thư của Spring bằng SES API. Ngoài ra, **Spring Boot Mail** cũng có thể kết nối **SES SMTP endpoint** mà không cần thay đổi mã sử dụng JavaMailSender. Hai con đường này dùng cơ chế xác thực và giao tiếp khác nhau.

Bài học thuộc chương **Amazon SNS và SES** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mục tiêu của module là thực hành Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm danh tính/quyền, storage, messaging, dữ liệu, quản lý secret, kiểm thử và đánh giá khác biệt giữa các provider. Riêng bài này tập trung vào **cách tích hợp SES với Spring Mail**, từ gửi văn bản đến HTML/attachment, quyền truy cập và xử lý sự cố giao thư.

Sau bài học, người học sẽ:

1. Chọn đúng một trong hai đường tích hợp **SES API qua Spring Cloud AWS** hoặc **SES SMTP qua Spring Boot Mail**.
2. Cấu hình SES identity, region, sandbox/production access và quyền gửi thư phù hợp.
3. Gửi email văn bản bằng **MailSender**, email HTML hoặc tệp đính kèm bằng **JavaMailSender**.
4. Phân biệt **IAM role/AWS SDK credentials** với **SES SMTP username/password**, không đưa secret vào repository.
5. Kiểm thử gửi email, quan sát bounce/complaint và hiểu tại sao lời gọi send thành công chưa bảo đảm thư vào hộp thư người nhận.

## 2. Từ Spring Mail đến Amazon SES

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Order Email Service"] --> B["Spring Mail<br/>MailSender / JavaMailSender"]
    B -->|"Lựa chọn A: SES API"| C["Spring Cloud AWS<br/>SES starter"]
    B -->|"Lựa chọn B: SMTP"| D["Spring Boot Mail<br/>JavaMailSenderImpl"]
    C --> E(("Amazon SES"))
    D --> E
    E --> F["Email provider<br/>của người nhận"]
    E -->|"Delivery / Bounce / Complaint"| G["SES event destination<br/>SNS / EventBridge / CloudWatch"]
~~~

**Spring Mail** mô tả thao tác gửi thư bằng Java thay vì buộc business code tự xây dựng yêu cầu HTTP hoặc SMTP. Hai abstraction phổ biến:

| Spring abstraction | Dạng thư | Kiểu thông điệp | Ví dụ |
| --- | --- | --- | --- |
| **MailSender** | Text đơn giản | **SimpleMailMessage** | OTP, thông báo ngắn |
| **JavaMailSender** (mở rộng MailSender) | MIME: text, HTML, multipart, attachment | **MimeMessage**, **MimeMessageHelper** | Biên nhận HTML và PDF |
| **SesClient/SesV2Client** của AWS SDK | Yêu cầu AWS SES trực tiếp | AWS SDK request | Cần thao tác hoặc response đặc thù SES |

Trong **Spring Cloud AWS 3.x**, starter **spring-cloud-aws-starter-ses** tạo sender dùng **SES API**. Khi chỉ gửi **SimpleMailMessage**, nó có thể cung cấp **MailSender**. Khi classpath có **Jakarta Mail API + implementation**, Spring Cloud AWS có thể cung cấp **JavaMailSender** hỗ trợ MIME; bản thân thao tác gửi vẫn qua **SES API**, không cần cấu hình SMTP host/password.

Với **Spring Boot starter-mail**, một **JavaMailSenderImpl** gửi thư qua SMTP. Để gửi tới SES, cấu hình host SMTP của SES, port TLS và bộ **SES SMTP credentials** dành riêng cho region.

### 2.1. So sánh hai cách tích hợp

| Tiêu chí | **Spring Cloud AWS SES (API)** | **Spring Boot Mail (SMTP)** |
| --- | --- | --- |
| Dependency chính | **spring-cloud-aws-starter-ses** | **spring-boot-starter-mail** |
| Cách vận chuyển | AWS SDK **SesClient**, gọi SES API | SMTP tới SES regional endpoint |
| Xác thực | AWS credentials provider chain, ưu tiên **IAM role** của workload | **SMTP username/password** của SES |
| Secret tĩnh cần lưu trong ứng dụng AWS | Không cần khi workload sử dụng IAM role | Cần bảo vệ SMTP password nếu chọn password-based SMTP |
| Spring API nghiệp vụ | **MailSender/JavaMailSender** | **MailSender/JavaMailSender** |
| Lợi ích | Tích hợp IAM role tốt, tránh thêm SMTP handshake | Dễ thay đổi từ hệ thống đang có JavaMailSender cấu hình SMTP |
| Khác biệt cần chú ý | HTML/MIME dùng SES raw email operation | Cần quản lý kết nối, TLS, timeout, SMTP authentication |

**Quy tắc chọn:** với workload Spring Boot chạy trên AWS có thể dùng IAM role, **Spring Cloud AWS SES API** thường phù hợp hơn. Với hệ thống đã chuẩn hóa SMTP hoặc cần đổi provider SMTP qua cấu hình, **SES SMTP** cũng là lựa chọn hợp lệ. Không nên đồng thời bật hai auto-configuration tạo sender một cách vô thức; cần chọn rõ bean **MailSender/JavaMailSender** nào sẽ được inject.

## 3. Chuẩn bị SES trước khi viết mã

### 3.1. Chọn region và xác thực danh tính gửi

SES lưu **verified identities** theo **AWS Region**. Trước khi gửi, mở Amazon SES Console ở region sẽ sử dụng (ví dụ **ap-southeast-1**) và xác minh một địa chỉ email hoặc một domain gửi thư.

- **Email identity:** phù hợp thử nghiệm nhanh, ví dụ **no-reply@example.com** sau khi chủ hộp thư xác nhận.
- **Domain identity:** phù hợp sản xuất, ví dụ **example.com**, thường cần xác minh quyền kiểm soát domain bằng DNS và cấu hình DKIM.
- **SPF**, **DKIM** và **DMARC:** cần được xem xét để xác thực nguồn gửi và nâng chất lượng giao thư; quản lý bản ghi DNS theo tài liệu SES và chính sách domain.
- **From address:** phải được phép gửi dựa trên verified identity hoặc cơ chế sending authorization phù hợp. Ví dụ sử dụng **no-reply@example.com** trên domain đã xác minh.

Địa chỉ/domain trong ví dụ là **dữ liệu minh họa**, không phải địa chỉ có thể dùng để gửi email thật khi chưa xác minh. Trong môi trường khác region, không mặc nhiên dùng lại trạng thái verify của identity ở region ban đầu.

### 3.2. SES sandbox và production access

Tài khoản SES mới thường ở **sandbox theo từng region**. Trong sandbox, chỉ gửi tới **địa chỉ/domain đã xác minh** hoặc **SES mailbox simulator**. Theo giới hạn sandbox được AWS công bố, mặc định tối đa **200 email/24 giờ** và **1 email/giây**; các giới hạn gửi thực tế có thể thay đổi theo tài khoản/region.

Khi được chấp thuận **production access**, bạn có thể gửi tới người nhận chưa xác minh, nhưng **From identity vẫn phải được xác minh**. Production access không đồng nghĩa email luôn đến inbox; reputation, suppression list, spam filtering, bounce/complaint và quota tiếp tục có vai trò.

Kiểm tra trạng thái SES qua AWS CLI:

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{Production:ProductionAccessEnabled,Quota:SendQuota}'
~~~

Kiểm tra identity đã thiết lập:

~~~bash
aws sesv2 get-email-identity \
  --email-identity example.com \
  --region ap-southeast-1
~~~

Chọn đúng region và quyền IAM đọc cấu hình tương ứng. Với mục đích kiểm thử, ưu tiên **SES mailbox simulator**, tránh gửi số lượng lớn thư thử tới người dùng thật.

### 3.3. SES, SNS và SQS phục vụ ba vai trò khác nhau

**SES** gửi email thực sự. **SNS** phân phối sự kiện tới nhiều subscriber. **SQS** giữ tác vụ để worker gửi email bất đồng bộ.

~~~mermaid
flowchart LR
    O["Order Service"] -->|"Publish ORDER_CREATED"| N(("SNS topic"))
    N --> Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Email Worker"]
    W -->|"MailSender / SES"| S(("Amazon SES"))
    S --> R["Người nhận"]
    S -->|"Bounce / Complaint"| V["SNS/EventBridge<br/>feedback handler"]
~~~

**SNS email subscription** có thể gửi thông báo topic đến email endpoint đã xác nhận, nhưng không thay thế đầy đủ quy trình email giao dịch có nội dung, template, biên nhận và quản lý danh tính của **SES**.

## 4. Cách A — Spring Cloud AWS SES API với MailSender

### 4.1. Dependency

Ví dụ **Gradle Groovy DSL**, sử dụng Spring Boot và **Spring Cloud AWS 3.x**:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")
}
~~~

**springCloudAwsVersion** là phiên bản BOM do dự án khai báo theo bảng tương thích của Spring Cloud AWS với Spring Boot. Với Maven, nhập BOM **spring-cloud-aws-dependencies** trong **dependencyManagement**, rồi thêm dependency starter SES. Các ví dụ Java dưới đây dùng **Spring Boot 3 / Jakarta Mail**, vì vậy không copy trực tiếp import **javax.mail** của ứng dụng Spring Boot 2.

### 4.2. Region và From address

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
      ses:
        region: ${SES_REGION:ap-southeast-1}

app:
  email:
    from: ${MAIL_FROM}
~~~

- **spring.cloud.aws.ses.region** chọn region của **SesClient**, có thể khác region chạy ứng dụng.
- **app.email.from** là property ứng dụng tự định nghĩa; ánh xạ tới sender đã xác minh trong SES.
- Nếu cần áp dụng **configuration set** cho mọi email của sender, Spring Cloud AWS có thể dùng **spring.cloud.aws.ses.configuration-set-name**, cấu hình khi set đó đã tồn tại.
- Các property nâng cao như **spring.cloud.aws.ses.source-arn** và **spring.cloud.aws.ses.from-arn** chủ yếu phục vụ **SES sending authorization**; không phải yêu cầu mặc định cho ứng dụng gửi bằng identity của chính account.

Khi chạy trên AWS, cấu hình IAM role gắn với workload (ECS task role, EC2 instance profile, EKS workload identity). AWS SDK sử dụng **credentials provider chain**. Với máy phát triển, dùng AWS CLI profile và kiểm tra region; đừng đưa khóa truy cập vào mã nguồn.

### 4.3. Gửi SimpleMailMessage

~~~java
package demo.mail;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class OrderTextMailService {
    private final MailSender mailSender;
    private final String fromAddress;

    public OrderTextMailService(
            MailSender mailSender,
            @Value("${app.email.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendConfirmation(String recipient, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn hàng " + orderId);
        message.setText(
                "Đơn hàng " + orderId + " đã được tiếp nhận.\n"
                        + "Cảm ơn bạn đã sử dụng dịch vụ."
        );

        mailSender.send(message);
    }
}
~~~

**Điều đáng chú ý:**

1. Mã nghiệp vụ chỉ cần dependency **org.springframework.mail.MailSender**.
2. **SimpleMailMessage** mô tả from/to/subject/text; không cần tạo HTTP client AWS hay đối tượng SMTP session.
3. Với starter SES, Spring Cloud AWS dùng SES API ở tầng hạ tầng khi thực thi **send**.
4. **mailSender.send** có thể ném **MailException** nếu quá trình gửi gặp lỗi. Kết quả không trả về chứng cứ người nhận đã đọc thư.

Phương thức này thích hợp email dạng text không có tệp đính kèm. Nếu cần HTML, inline image hoặc file PDF, dùng **JavaMailSender + MimeMessage**.

## 5. Gửi email HTML và attachment với JavaMailSender

### 5.1. Kích hoạt Jakarta Mail cho SES starter

Trong Spring Cloud AWS 3.x, thêm **Jakarta Mail API và implementation**. Ví dụ:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-ses")

    implementation("jakarta.mail:jakarta.mail-api")
    runtimeOnly("org.eclipse.angus:jakarta.mail")
    implementation("org.springframework:spring-web") // dùng HtmlUtils ở ví dụ bên dưới
}
~~~

Khi các thành phần cần thiết có mặt trên classpath, starter SES tự cấu hình **JavaMailSender** có thể gửi MIME. **Tầng vận chuyển vẫn là SES API**, không phải SMTP. Spring Cloud AWS dùng **ses:SendEmail** cho text đơn giản và **ses:SendRawEmail** cho MIME/raw email theo loại lệnh gửi. Dependency **spring-web** chỉ cần nếu ứng dụng chưa có nó; ví dụ bên dưới dùng **HtmlUtils** để escape nội dung động trong HTML.

Nếu dependency resolution yêu cầu phiên bản rõ ràng cho Jakarta Mail/Angus, quản lý version bằng BOM phù hợp với nền tảng Spring Boot đang dùng. Tránh pha trộn **javax.mail** (thế hệ cũ) với **jakarta.mail** trong cùng ứng dụng Spring Boot 3.

### 5.2. Tạo mail có phần text, HTML và PDF

~~~java
package demo.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class ReceiptMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public ReceiptMailService(
            JavaMailSender mailSender,
            @Value("${app.email.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendReceipt(
            String recipient, String orderId, byte[] receiptPdf)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Biên nhận đơn hàng " + orderId);

        String safeOrderId = HtmlUtils.htmlEscape(orderId);
        String plainText = "Biên nhận cho đơn " + orderId;
        String htmlText = "<p>Biên nhận cho đơn <strong>"
                + safeOrderId + "</strong>.</p>";

        helper.setText(plainText, htmlText);
        helper.addAttachment(
                "receipt.pdf",
                new ByteArrayResource(receiptPdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

**Giải thích:**

- **createMimeMessage** tạo thư MIME; **MimeMessageHelper** điền trường header/body và file đính kèm.
- **setText(plainText, htmlText)** tạo hai phiên bản text/plain và text/html; client email có thể chọn phiên bản phù hợp.
- **ByteArrayResource** ở đây là dữ liệu PDF đã tạo từ trước; trong thực tế tránh tải cả file rất lớn vào bộ nhớ và kiểm soát loại/kích thước attachment.
- **HtmlUtils.htmlEscape** dùng khi đưa nội dung động vào HTML; với template engine hãy sử dụng escaping mặc định, tránh ghép trực tiếp HTML từ dữ liệu người dùng.
- **MessagingException** liên quan dựng MIME; **MailException** liên quan lỗi gửi và thường là runtime exception.
- Địa chỉ **recipient** cần được kiểm tra ở biên ứng dụng, không dùng input không tin cậy để dựng thêm SMTP headers tùy ý.

Mặc dù đoạn code dùng **JavaMailSender**, chính lớp triển khai của Spring Cloud AWS sẽ chuyển MIME thành raw email request đến SES. Không cần cấu hình **spring.mail.host** cho cách A.

## 6. IAM cho SES API: gửi text và raw email

Khi dùng starter SES API, IAM role của ứng dụng phải được phép gửi thư qua **verified identity**. Ví dụ identity **example.com** đã được verify ở account **123456789012**, region **ap-southeast-1**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOnlyFromVerifiedDomain",
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "arn:aws:ses:ap-southeast-1:123456789012:identity/example.com",
      "Condition": {
        "StringEquals": {
          "ses:FromAddress": "no-reply@example.com"
        }
      }
    }
  ]
}
~~~

**Ý nghĩa:**

- **ses:SendEmail** phục vụ email đơn giản mà starter gửi qua SES.
- **ses:SendRawEmail** phục vụ thư MIME/raw, cần khi gửi HTML và attachment theo abstraction được minh họa.
- **Resource** giới hạn vào SES identity đã verify thay vì cấp **Resource: "*"** cho mọi identity.
- **ses:FromAddress** tiếp tục hạn chế địa chỉ From được phép sử dụng.
- Policy này gắn với **runtime IAM role** của Spring Boot, không nhất thiết phải cấp cho mỗi người dùng ứng dụng.

Nếu sử dụng cơ chế **sending authorization** để gửi thay account sở hữu identity, policy và điều kiện sẽ khác; phải kiểm tra quyền của cả delegate sender lẫn identity owner. Các ví dụ mặc định gửi bằng identity của chính account.

**Đừng dùng permission mở rộng để giải quyết lỗi gửi:** khi chỉ có API text hoạt động mà MIME thất bại, trước tiên kiểm tra **ses:SendRawEmail**, trạng thái verified identity, region và chính sách From. Nếu toàn bộ thao tác bị từ chối, kiểm tra credentials provider, IAM permissions, SCP/permission boundary và chính sách account.

## 7. Cách B — Spring Boot JavaMailSender qua SES SMTP

Nếu ứng dụng đã dùng SMTP hoặc cần thay đổi SMTP provider qua cấu hình, thay cách A bằng **spring-boot-starter-mail** và cung cấp SES SMTP endpoint.

### 7.1. Dependency và cấu hình

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
}
~~~

Ví dụ **application.yml**:

~~~yaml
spring:
  mail:
    host: email-smtp.ap-southeast-1.amazonaws.com
    port: 587
    username: ${SES_SMTP_USERNAME}
    password: ${SES_SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000

app:
  email:
    from: ${MAIL_FROM}
~~~

Cấu hình trên dùng **SMTP port 587 + STARTTLS bắt buộc**. Có thể sử dụng cổng **465 (TLS Wrapper)** với cấu hình SSL/TLS tương ứng, nhưng không dùng lẫn lộn thiết lập SMTPS với STARTTLS. Port **25** thường bị giới hạn/throttle tại một số môi trường, đặc biệt EC2; ưu tiên các cổng được SES hướng dẫn.

**SMTP endpoint, SMTP username/password đều gắn với region.** Ví dụ **email-smtp.ap-southeast-1.amazonaws.com** dùng cho region đã chọn; cần kiểm tra endpoint được AWS hỗ trợ nếu chuyển region.

### 7.2. SMTP credentials khác AWS credentials

**SES SMTP credentials** lấy từ SES Console (SMTP settings) hoặc quy trình quản lý SMTP credentials phù hợp. Đây **không phải** cặp **AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY** được AWS SDK dùng để gọi API; password SMTP cũng không giống AWS secret access key. Một số quy trình SES hỗ trợ SMTP credential theo cơ chế IAM và/hoặc SES Mail Manager tùy lựa chọn.

| | **SES API** | **SES SMTP** |
| --- | --- | --- |
| Xác thực | AWS SDK credentials provider chain, có thể là IAM role ngắn hạn | SMTP username/password do SES cấp |
| Trong Spring Boot | Spring Cloud AWS SES starter | Spring Boot starter-mail |
| Cấu hình trọng tâm | **spring.cloud.aws.ses.region**, IAM role | **spring.mail.host**, port, username/password và TLS |
| Quản lý bí mật | Không cần access key tĩnh khi chạy bằng IAM role | Lưu SMTP password trong Secrets Manager hoặc môi trường quản lý secret |
| Quyền liên quan | **ses:SendEmail / ses:SendRawEmail** trên identity | SMTP credential/identity phải được SES cho phép gửi |

**Không đưa SMTP password trực tiếp vào Git**, cấu hình ví dụ hay log. Trong môi trường AWS, có thể nạp secret từ **AWS Secrets Manager**/Parameter Store với quyền đọc tối thiểu; trong local dev dùng biến môi trường hoặc cơ chế cấu hình bí mật được quản lý. Nếu email lỗi xác thực **535**, không giải quyết bằng cách đưa access key thường vào trường **spring.mail.password**.

### 7.3. Business code có cần sửa không?

Khi dùng SMTP, Spring Boot cấu hình **JavaMailSenderImpl**, vốn triển khai **JavaMailSender** và **MailSender**. Vì vậy **OrderTextMailService** và **ReceiptMailService** ở mục 4–5 vẫn có thể tái sử dụng qua constructor injection.

Điểm thay đổi chủ yếu nằm ở **dependency, cấu hình vận chuyển và nguồn credentials**. Tránh kích hoạt cùng lúc SES starter và SMTP auto-config nếu không thiết kế rõ qualifying bean; nếu có nhiều MailSender beans, injection theo type có thể trở nên mơ hồ.

**Khác biệt vận hành:** SMTP thực hiện nhiều bước giao thức (kết nối, EHLO, STARTTLS, AUTH, MAIL FROM, RCPT TO, DATA). Vì vậy cần cấu hình timeout và theo dõi socket, firewall, TLS và SMTP response codes; SES API trực tiếp thường đơn giản hơn khi workload đã có IAM role.

## 8. Trạng thái gửi thành công khác trạng thái giao thành công

Lời gọi **mailSender.send(message)** trả về không có exception nghĩa là request được xử lý thành công ở tầng gửi tương ứng. Với SES, điều này thường là SES **đã tiếp nhận email để xử lý**, chứ **không** chứng minh người nhận đã thấy thư trong inbox.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant SES as Amazon SES
    participant Mailbox as Receiving mail server
    participant Events as Event destination

    App->>SES: Send email
    SES-->>App: Accepted / API success
    Note over App,SES: Chưa chứng minh đã giao hoặc được đọc
    SES->>Mailbox: Attempt delivery
    alt Được mail server chấp nhận
        Mailbox-->>SES: Accepted
        SES-->>Events: Delivery event (nếu cấu hình)
    else Bị từ chối / bounce
        Mailbox-->>SES: Bounce / reject
        SES-->>Events: Bounce event (nếu cấu hình)
    end
~~~

### 8.1. SES event publishing

Sử dụng **SES configuration set** và **event destination** để theo dõi những sự kiện được SES hỗ trợ, chẳng hạn:

| Sự kiện | Diễn giải | Hành động ứng dụng |
| --- | --- | --- |
| **Send** | SES ghi nhận sự kiện gửi | Ghi log/mức độ chấp nhận của tầng gửi |
| **Delivery** | Máy chủ nhận đã chấp nhận email | Cập nhật trạng thái delivered, vẫn không có nghĩa người nhận đã đọc |
| **Bounce** | Email bị máy chủ nhận từ chối hoặc không thể giao | Phân loại hard/soft bounce, điều chỉnh chiến lược gửi |
| **Complaint** | Người nhận báo spam | Cập nhật preference/suppression, kiểm tra nội dung và quyền gửi |
| **Reject** | SES từ chối email theo kiểm tra nội dung/chính sách | Xem lý do và điều kiện gửi |
| **Open/Click** | Chỉ quan sát khi cấu hình chức năng theo dõi tương ứng | Tuân thủ quyền riêng tư và yêu cầu đồng ý liên quan |

Event destinations có thể dùng **SNS**, **EventBridge** hoặc **CloudWatch** tùy loại tích hợp. Nếu cần xử lý bounce/complaint bất đồng bộ, một hướng đi là **SES → SNS topic → SQS → Spring Boot feedback worker**. Cấu hình SNS/SQS policy và DLQ ở đường feedback độc lập với quyền **ses:SendEmail** của sender.

### 8.2. Retry và tránh gửi email trùng

Một request có thể timeout ở phía ứng dụng sau khi SES đã chấp nhận email; nếu retry ngay, người nhận có thể nhận **hai email**. Vì vậy:

1. Đặt **message/event ID nghiệp vụ** ổn định cho mỗi email cần gửi, ví dụ khóa **orderId + notificationType + version**.
2. Lưu trạng thái gửi trong DB/outbox và kiểm soát chuyển trạng thái, thay vì retry vô hạn không ghi nhận.
3. Dùng **backoff** và giới hạn số lần retry cho lỗi tạm thời/throttling; không retry mù quáng với địa chỉ không hợp lệ hay lỗi quyền.
4. Khi tiêu thụ SQS, thực hiện **idempotency** trước khi tạo tác động gửi email.
5. Xử lý trạng thái không chắc chắn (**timeout** hoặc worker chết sau gửi) bằng cơ chế đối soát/tracking phù hợp, vì SES không cung cấp transaction nguyên tử chung với DB.

Nếu gửi email là hậu quả của một giao dịch order trong DB, cân nhắc mô hình **transactional outbox**: ghi bản ghi event cùng transaction với order, rồi một worker phát tác vụ và gửi qua SES. Mô hình này giảm nguy cơ lưu đơn thành công nhưng quên gửi mail khi tiến trình gặp lỗi.

## 9. Kiểm thử Spring Mail và SES

### 9.1. Unit test không kết nối AWS

Ưu điểm của Spring **MailSender** là có thể mock/fake interface để kiểm tra dữ liệu được tạo đúng. Ví dụ test JUnit 5 + Mockito cho **OrderTextMailService**:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class OrderTextMailServiceTest {
    @Test
    void sendsOrderConfirmationWithExpectedFields() {
        MailSender mailSender = mock(MailSender.class);
        OrderTextMailService service =
                new OrderTextMailService(mailSender, "no-reply@example.com");

        service.sendConfirmation("customer@example.net", "ord-42");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mailSender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("no-reply@example.com", sent.getFrom());
        assertArrayEquals(new String[]{"customer@example.net"}, sent.getTo());
        assertEquals("Xác nhận đơn hàng ord-42", sent.getSubject());
        assertTrue(sent.getText().contains("ord-42"));
    }
}
~~~

Bài test không cần AWS account, SES verified identity hoặc SMTP credentials. Nó kiểm tra **nội dung và địa chỉ gửi**, không tự chứng minh dữ liệu đã đi qua AWS SES.

Với **JavaMailSender**, có thể mock sender, trả về một **MimeMessage** tạo trong bộ nhớ rồi kiểm tra subject, text/html và attachment. Cần unit test cả trường hợp HTML chứa ký tự đặc biệt, recipient không hợp lệ và tệp đính kèm rỗng/quá lớn theo chính sách ứng dụng.

### 9.2. Integration test thực tế

Sử dụng **AWS sandbox** và verified identity riêng cho môi trường thử nghiệm. Có thể dùng **SES mailbox simulator** để mô phỏng đường giao thư mà không phải gửi email đến hộp thư cá nhân.

| Bước | Hành động | Kỳ vọng |
| --- | --- | --- |
| 1 | Verify **example.com** hoặc địa chỉ From ở region test | Identity có trạng thái xác minh phù hợp |
| 2 | Cấp IAM role có **ses:SendEmail** | **SimpleMailMessage** gửi được |
| 3 | Thêm **ses:SendRawEmail**, gửi MIME với PDF | HTML/text và attachment được SES chấp nhận |
| 4 | Thử sender chưa verify hoặc sai region | Nhận lỗi từ SES, không coi là thành công |
| 5 | Kiểm tra sandbox: gửi tới recipient chưa verify | Bị giới hạn trừ mailbox simulator |
| 6 | Gửi tới địa chỉ mô phỏng success/bounce/complaint theo tài liệu SES | Quan sát đúng sự kiện SES nếu event publishing đã cấu hình |
| 7 | Tắt quyền **ses:SendRawEmail** trong sandbox | Gửi MIME thất bại với lỗi quyền |
| 8 | Gửi nhiều request tới giới hạn thử nghiệm | Quan sát throttling và retry có backoff |

Địa chỉ mailbox simulator phổ biến gồm **success@simulator.amazonses.com** và **bounce@simulator.amazonses.com**; xác minh chính sách simulator mới nhất trong tài liệu SES trước khi chạy. Không gửi thử tới email của người khác khi chưa được phép.

**Lưu ý:** Bộ giả lập/local mock có thể kiểm thử việc gọi SDK hoặc giao diện SMTP, nhưng khó thay thế hoàn toàn việc xác minh DNS identity, delivery, spam filtering và event pipeline thật. Đối với bài kiểm thử quyền/IAM, sandbox AWS giúp cho kết quả sát thực tế hơn.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Starter SES không inject được **MailSender** | Thiếu starter, auto-configuration bị tắt hoặc nhiều bean cùng type | Kiểm tra dependency, **spring.cloud.aws.ses.enabled**, bean và profile |
| Không inject được **JavaMailSender** | Chưa có Jakarta Mail API/implementation trên classpath | Thêm đúng Jakarta Mail + Angus, giữ version nhất quán |
| Lỗi **AccessDenied** qua API | IAM role thiếu **ses:SendEmail** hoặc **ses:SendRawEmail**, sai ARN identity/From | Kiểm tra role thực tế, region, policy và condition |
| **MessageRejectedException** | Chưa verify From/recipient sandbox, suppression hoặc điều kiện SES khác | Kiểm tra SES identity, sandbox và thông tin error |
| SMTP trả về **535 Authentication Credentials Invalid** | Dùng sai SMTP user/password hoặc nhầm AWS access key | Tạo/lấy SES SMTP credentials đúng region, kiểm tra secret |
| SMTP timeout / TLS handshake lỗi | Firewall, endpoint/port sai, thiếu STARTTLS hoặc chứng chỉ | Kiểm tra host, TLS và các mail.smtp timeout |
| Text gửi được, MIME/attachment lỗi | Thiếu **ses:SendRawEmail**, MIME sai hoặc attachment không hợp lệ | Kiểm tra quyền raw, MIME builder và dung lượng |
| API gửi thành công nhưng người nhận không thấy thư | Email bị bounce, suppression, spam filter hoặc delivery chậm | Xem SES event publishing/metrics và trạng thái receiver |
| Email trùng sau retry | Request trước đã được chấp nhận nhưng client timeout | Idempotency, outbox và log event ID |
| Email nhiều người nhận bị lộ danh sách | Tự thêm recipient vào To/Cc không phù hợp | Đặt privacy rules; dùng Bcc hoặc gửi riêng theo yêu cầu |

### 10.1. Chẩn đoán có thứ tự

1. **Ứng dụng dùng SES API hay SMTP?** Xác định từ dependency và bean runtime, vì nguyên nhân xác thực khác nhau.
2. **From identity và region có đúng không?** Kiểm tra verified identity và account sandbox/production access.
3. **AWS principal hoặc SMTP credentials có đúng không?** Với API kiểm tra IAM role; với SMTP kiểm tra bộ thông tin đăng nhập riêng.
4. **SES đã chấp nhận request chưa?** Phân biệt lỗi trong Spring trước khi gửi, lỗi API/SMTP và kết quả tiếp nhận.
5. **Trạng thái giao thư thế nào?** Xem SES event destination, bounce/complaint, suppression và log.
6. **Có retry/trùng event không?** Đối chiếu business event ID với lần gửi và consumer acknowledgment.

Nếu một **SES API SendEmail** trả về **MessageId** khi gọi SDK trực tiếp, đó là ID của thông điệp SES được chấp nhận, không phải bằng chứng người nhận đã đọc. Các phương thức **MailSender.send** của Spring không mặc định trả về MessageId này.

## 11. Khi nào cần dùng SDK trực tiếp?

**Spring Mail** phù hợp khi business service chỉ muốn gửi nội dung email. Một số nhu cầu SES cụ thể có thể cần **AWS SDK for Java v2** trực tiếp, chẳng hạn truy xuất **SendEmailResponse.messageId**, dùng những tính năng SES mới chưa được adapter hỗ trợ hoặc gắn tags/configuration set cho từng yêu cầu.

Có hai client SDK hay gặp:

- **SesClient**: SES API truyền thống mà Spring Cloud AWS SES sender dùng trong nhánh tích hợp đã minh họa.
- **SesV2Client**: SES API v2, hỗ trợ các thao tác và kiểu request riêng.

Khi sử dụng SDK trực tiếp, lớp adapter của ứng dụng có thể triển khai một interface nghiệp vụ như **TransactionalEmailGateway**, để code xử lý đơn hàng không phụ thuộc trực tiếp vào AWS SDK. Cả hai cách gửi đều cần quản lý region, verified identity, IAM và trạng thái giao thư phù hợp.

**Không tự triển khai JavaMailSender từ đầu** nếu chỉ cần gửi text hoặc MIME phổ thông; Spring Cloud AWS SES adapter và Spring Boot SMTP integration đã cung cấp hai con đường có thể kiểm thử.

## 12. Bài tập tự thực hành

**Yêu cầu:** phát triển một Spring Boot service gửi email xác nhận đơn hàng qua SES. Bắt đầu với **Spring Cloud AWS SES starter** và IAM role trong sandbox.

1. Verify domain/email From tại SES region đã chọn. Kiểm tra sandbox, quota và quyền gửi.
2. Khai báo **spring-cloud-aws-starter-ses**, cấu hình region và **app.email.from**.
3. Viết **OrderTextMailService** với **MailSender** và **SimpleMailMessage**.
4. Thêm Jakarta Mail/Angus và viết **ReceiptMailService** gửi HTML + text fallback + PDF bằng **JavaMailSender**.
5. Tạo IAM policy chỉ cho phép **ses:SendEmail** và **ses:SendRawEmail** từ verified identity dự định.
6. Viết unit test kiểm tra nội dung và recipient không cần AWS.
7. Kiểm thử tích hợp bằng SES mailbox simulator và theo dõi event delivery/bounce.
8. Thay dependency/cấu hình sang **spring-boot-starter-mail**, tạo SES SMTP credentials và lặp lại với cùng service code.
9. *Nâng cao:* đưa tác vụ gửi mail vào SQS, xử lý idempotent và phát sự kiện feedback qua SES configuration set → SNS/EventBridge.

### Câu hỏi ôn tập

1. Vì sao Spring Cloud AWS có thể gửi email qua **MailSender** mà không cần SMTP host/password?
2. **MailSender** và **JavaMailSender** khác nhau thế nào về loại message và IAM action SES?
3. Vì sao **ses:SendEmail** chưa đủ cho email MIME theo Spring Cloud AWS adapter?
4. AWS IAM role có thể dùng trực tiếp làm username/password của SES SMTP không?
5. Tài khoản SES trong sandbox có thể gửi ngay cho người nhận chưa verify không?
6. **Send thành công**, **delivery thành công** và **người nhận đọc email** khác nhau ở đâu?
7. Điều gì có thể xảy ra nếu client retry sau timeout dù SES đã nhận email?
8. Vì sao cấu hình SES feedback qua SNS/SQS hữu ích cho bounce/complaint?

## 13. Tài liệu tham khảo

- [Spring Cloud AWS 3.3.1 — SES Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#ses-integration): starter SES, MailSender/JavaMailSender, MIME, cấu hình region và IAM.
- [Spring Cloud AWS — API SimpleEmailServiceJavaMailSender](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/apidocs/io/awspring/cloud/ses/SimpleEmailServiceJavaMailSender.html): adapter JavaMailSender dùng SES API.
- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): verified identity và quyền gửi.
- [Amazon SES — Production access and sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html): hạn chế recipient/quota theo region.
- [Amazon SES — Obtaining SMTP credentials](https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html): SMTP credentials khác AWS access key.
- [Amazon SES — Sending via SMTP](https://docs.aws.amazon.com/ses/latest/dg/send-using-smtp-programmatically.html): SMTP endpoint, port và STARTTLS.
- [Amazon SES — Troubleshoot SMTP](https://docs.aws.amazon.com/ses/latest/dg/troubleshoot-smtp.html): mã lỗi xác thực, mạng và message.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): configuration sets, delivery, bounce và complaint.
- [AWS SDK for Java v2 — SES examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sesv2_code_examples.html): API gửi email và đọc MessageId.

**Kết quả cuối bài:** người học tích hợp được **Amazon SES với cơ chế gửi thư của Spring**, hiểu hai hình thức SES API/SMTP, gửi cả text và MIME, cấp quyền đúng, bảo vệ credentials, kiểm thử an toàn và theo dõi vòng đời email từ lúc gửi đến phản hồi của dịch vụ nhận.
