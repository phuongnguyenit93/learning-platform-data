# Danh tính gửi thư, sandbox và xử lý lỗi chuyển phát

## 1. Bối cảnh và mục tiêu học tập

Một ứng dụng Spring Boot gửi email xác nhận đơn hàng qua **Amazon Simple Email Service (Amazon SES)**. Lệnh gửi từ ứng dụng trả về thành công nhưng người nhận không thấy thư; hoặc SES từ chối yêu cầu vì địa chỉ From chưa xác minh, tài khoản vẫn ở sandbox, vượt quota hay bị tạm dừng gửi. Để vận hành đúng, cần hiểu vòng đời email từ **danh tính gửi → xác thực domain → quyền gửi → SES tiếp nhận → máy chủ nhận → bounce/complaint**.

Bài học nằm trong chương **Amazon SNS và SES** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng dẫn tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng, bao gồm danh tính/quyền truy cập, messaging, storage, dữ liệu, bảo vệ secret, kiểm thử và đánh giá khác biệt giữa cloud provider. Trọng tâm bài này là **danh tính gửi thư, sandbox và xử lý lỗi chuyển phát** khi dùng SES.

Sau bài học, bạn có thể:

1. Phân biệt email identity, domain identity, địa chỉ **From**, domain **MAIL FROM** và SES region.
2. Thiết lập xác minh domain/email, DKIM, SPF, DMARC và custom MAIL FROM.
3. Hiểu giới hạn **sandbox**, cách yêu cầu production access và quota theo region.
4. Cấu hình quyền IAM để Spring Boot gửi từ đúng identity.
5. Phân loại lỗi trước khi gửi, bounce, complaint, reject, delivery delay và suppression.
6. Thiết lập event publishing để quan sát trạng thái giao thư và xử lý phản hồi trong hệ thống.
7. Kiểm thử an toàn bằng SES mailbox simulator và xây dựng quy trình xử lý lỗi có thể lặp lại.

## 2. Danh tính gửi thư trong Amazon SES

### 2.1. Email identity và domain identity

**Verified identity** là địa chỉ email hoặc domain mà tài khoản AWS chứng minh được quyền kiểm soát. SES yêu cầu xác minh identity trước khi gửi thư từ identity đó.

| Loại identity | Ví dụ | Cách xác minh | Phù hợp |
| --- | --- | --- | --- |
| **Email identity** | **no-reply@example.com** | SES gửi email xác nhận tới hộp thư | Thử nghiệm nhanh, ít địa chỉ gửi |
| **Domain identity** | **example.com** | Thêm DNS record do SES cung cấp | Ứng dụng sản xuất có nhiều địa chỉ gửi |
| **Subdomain identity** | **mail.example.com** | Xác minh domain/subdomain riêng theo cấu hình | Tách luồng gửi, reputation và DNS theo nhu cầu |

Domain identity phù hợp khi ứng dụng có nhiều địa chỉ như **no-reply@example.com**, **billing@example.com** và **support@example.com**. Xác minh domain chứng minh quyền kiểm soát domain; nó không tự tạo mailbox để nhận thư. Nếu cần nhận email phản hồi, phải có dịch vụ nhận thư riêng hoặc cấu hình email receiving phù hợp.

**Identity gắn với AWS Region.** Xác minh **example.com** ở **ap-southeast-1** không có nghĩa identity đã tự động được xác minh ở region khác. Ứng dụng, SES identity, configuration set và quota cần được kiểm tra trong cùng region mà request gửi tới.

### 2.2. Xác minh domain và DKIM

Luồng thiết lập cơ bản:

1. Mở Amazon SES Console ở region dự kiến gửi.
2. Tạo **domain identity** với domain thuộc quyền quản lý của tổ chức.
3. Bật **Easy DKIM** hoặc cấu hình phương thức DKIM được SES hỗ trợ.
4. Thêm các **CNAME records** DKIM do SES cung cấp vào DNS.
5. Chờ DNS lan truyền, sau đó kiểm tra identity có trạng thái **Verified** và DKIM được bật/thành công.
6. Chỉ đưa domain vào cấu hình gửi production khi đã kiểm tra domain và địa chỉ From.

**DKIM (DomainKeys Identified Mail)** ký thông điệp bằng khóa thuộc domain gửi. Mail server nhận có thể kiểm tra chữ ký dựa trên public key được công bố trong DNS. SES Easy DKIM tạo các DNS record cần thiết và quản lý khóa ký theo cấu hình dịch vụ.

Ví dụ cấu hình DNS mang tính minh họa:

~~~text
Name:  <token-1>._domainkey.example.com
Type:  CNAME
Value: <token-1>.dkim.amazonses.com

Name:  <token-2>._domainkey.example.com
Type:  CNAME
Value: <token-2>.dkim.amazonses.com
~~~

Các token và số lượng record thực tế phải lấy từ SES Console/API; không tự tạo token từ ví dụ. Sau khi cập nhật DNS, kiểm tra trạng thái xác minh và DKIM trong SES, không chỉ dựa vào việc DNS provider báo đã lưu record.

### 2.3. SPF, DMARC và MAIL FROM

Ba khái niệm này thường bị nhầm với địa chỉ hiển thị **From**:

- **From header:** địa chỉ người nhận nhìn thấy trong ứng dụng email, ví dụ **no-reply@example.com**.
- **MAIL FROM / envelope sender:** địa chỉ ở tầng SMTP dùng cho phản hồi lỗi và một phần kiểm tra SPF; người dùng cuối thường không nhìn thấy trực tiếp như From header.
- **SPF:** khai báo hệ thống nào được phép gửi mail thay mặt một domain.
- **DKIM:** xác thực chữ ký của nội dung email theo domain ký.
- **DMARC:** yêu cầu alignment giữa domain ở From header và domain được SPF hoặc DKIM xác thực; đồng thời cho phép domain công bố chính sách và nhận báo cáo.

SES có thể dùng domain MAIL FROM mặc định thuộc **amazonses.com**. Nếu muốn dùng subdomain của tổ chức, cấu hình **custom MAIL FROM domain**, ví dụ **bounce.example.com**. SES yêu cầu các DNS record phù hợp, bao gồm:

~~~text
Name:  bounce.example.com
Type:  MX
Value: <feedback-endpoint-cua-region>.amazonses.com

Name:  bounce.example.com
Type:  TXT
Value: "v=spf1 include:amazonses.com ~all"
~~~

Giá trị MX chính xác phải lấy theo region SES và hướng dẫn trong Console. Đây là record cho endpoint feedback của SES, không phải MX record để chuyển thư đến mailbox người dùng. Custom MAIL FROM domain cần là subdomain đáp ứng các điều kiện SES; không tùy tiện dùng chính subdomain đang phục vụ gửi hoặc nhận email thông thường.

**DMARC** có thể được công bố tại **_dmarc.example.com**. Ví dụ chính sách ban đầu để quan sát báo cáo:

~~~text
Name:  _dmarc.example.com
Type:  TXT
Value: "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
~~~

**p=none** chỉ yêu cầu theo dõi, không yêu cầu receiver cách ly hoặc từ chối thư. Khi đã hiểu nguồn gửi hợp pháp, tổ chức có thể cân nhắc **quarantine** hoặc **reject** theo lộ trình quản trị domain. Không tự đặt DMARC nghiêm ngặt trước khi xác minh các hệ thống gửi hợp pháp của tổ chức; điều đó có thể ảnh hưởng cả email không gửi qua SES.

**Lưu ý:** DMARC pass khi SPF hoặc DKIM đạt alignment theo quy tắc DMARC. Custom MAIL FROM hỗ trợ SPF alignment; Easy DKIM có thể hỗ trợ DKIM alignment khi domain ký phù hợp. Việc có SPF record không tự động chứng minh From header đã được xác thực.

## 3. Sandbox và production access

### 3.1. Giới hạn của sandbox

Tài khoản SES mới thường bắt đầu ở **sandbox**, và trạng thái sandbox được quản lý **theo từng AWS Region**. Trong sandbox, tài khoản có thể sử dụng nhiều tính năng SES nhưng bị giới hạn người nhận và tốc độ gửi.

Theo tài liệu AWS, giới hạn sandbox mặc định thường là:

- Chỉ gửi tới **địa chỉ email/domain đã xác minh** hoặc **SES mailbox simulator**.
- Tối đa **200 recipient trong 24 giờ** theo giới hạn sandbox mặc định.
- Tốc độ gửi tối đa **1 email/giây**.

Các giới hạn và quota có thể thay đổi theo tài khoản/region; luôn kiểm tra **Sending limits** trong SES Console hoặc API. Quota tổng quát được tính theo số **recipient**, không chỉ số lần gọi API; một email gửi cho nhiều người nhận có thể tiêu thụ nhiều đơn vị quota.

Trong sandbox, ví dụ **customer@example.net** không được xác minh sẽ bị từ chối, kể cả khi **no-reply@example.com** là verified identity. Vì vậy, kiểm thử nên dùng địa chỉ người nhận đã xác minh hoặc mailbox simulator.

### 3.2. Request production access

Khi ứng dụng cần gửi cho người nhận thông thường, yêu cầu SES **production access** ở từng region sẽ dùng. Chuẩn bị thông tin trung thực về:

- Website hoặc ứng dụng gửi email.
- Loại email: **TRANSACTIONAL** cho xác nhận đơn, hóa đơn, reset password; **MARKETING** cho newsletter/quảng bá.
- Cách thu thập sự đồng ý và quản lý unsubscribe nếu gửi marketing.
- Quy trình xử lý bounce, complaint, suppression và yêu cầu ngừng nhận thư.
- Địa chỉ liên hệ có thể nhận phản hồi từ AWS.

Có thể yêu cầu bằng AWS CLI SES v2:

~~~bash
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url "https://app.example.com" \
  --contact-language EN \
  --additional-contact-email-addresses "ops@example.com" \
  --region ap-southeast-1
~~~

Đây là ví dụ cho ứng dụng gửi email giao dịch. Hãy thay website/contact bằng thông tin thật và dùng đúng region. Việc gửi yêu cầu không đồng nghĩa production access được cấp ngay; cần kiểm tra trạng thái account sau khi AWS xem xét.

Kiểm tra trạng thái:

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{ProductionAccess:ProductionAccessEnabled,SendingEnabled:SendingEnabled,Quota:SendQuota}'
~~~

**ProductionAccessEnabled** và **SendingEnabled** là hai trạng thái cần quan sát. Một account có production access nhưng khả năng gửi bị pause vẫn không gửi được.

### 3.3. Quota và tốc độ gửi

Quota là **theo region**. Không giả định chuyển từ **ap-southeast-1** sang region khác sẽ giữ nguyên giới hạn. SES cũng áp dụng giới hạn tốc độ; nếu vượt, request có thể bị throttling hoặc quota error.

Trong ứng dụng:

- Dùng queue/worker để điều tiết tốc độ gửi thay vì tạo burst lớn.
- Theo dõi số recipient trong mỗi email, quota 24 giờ và sending rate.
- Retry throttling với **exponential backoff + jitter**, giới hạn số lần thử.
- Không retry lỗi identity, recipient hoặc permission như thể đó là lỗi tạm thời.
- Nếu cần tăng quota, gửi yêu cầu tăng limit qua AWS Support sau khi đã có dữ liệu vận hành phù hợp.

## 4. Cấu hình danh tính và quyền cho Spring Boot

Bài tích hợp SES trước đó đã giới thiệu **MailSender**, **JavaMailSender**, SES API và SMTP. Ở đây tập trung vào các điều kiện để sender được phép sử dụng đúng identity.

### 4.1. Region và From address

Ví dụ **application.yml** cho Spring Cloud AWS 3.x:

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
    from: ${MAIL_FROM:no-reply@example.com}
~~~

- **spring.cloud.aws.region.static** chọn region mặc định cho AWS SDK.
- **spring.cloud.aws.ses.region** chỉ rõ region SES nếu cần tách khỏi region mặc định của các AWS client khác.
- **app.email.from** là property do ứng dụng định nghĩa; giá trị phải thuộc verified identity được phép gửi trong SES region đã cấu hình.

Trên AWS, ưu tiên **IAM role** của ECS task, EC2 instance hoặc workload identity trên EKS. Máy phát triển có thể dùng AWS CLI profile. Không hardcode AWS access key hoặc secret vào repository, file YAML được commit hay log.

### 4.2. IAM policy giới hạn identity

Ví dụ role của ứng dụng chỉ được gửi từ domain identity **example.com** ở account **123456789012**, region **ap-southeast-1**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendFromVerifiedExampleDomain",
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

- **ses:SendEmail** cho API gửi email thông thường.
- **ses:SendRawEmail** cần cho đường gửi MIME/raw email trong tích hợp Spring Mail.
- **Resource** giới hạn vào SES identity.
- **ses:FromAddress** hạn chế địa chỉ From được phép dùng.

Đây là policy minh họa cho sender trong cùng account với identity. Nếu dùng **sending authorization** để gửi thay mặt account sở hữu identity, cần policy của identity owner và quyền của delegate sender tương ứng. Không sao chép policy cross-account mà không hiểu principal thực tế.

### 4.3. Gửi thử bằng Spring Mail

Ví dụ ngắn với **MailSender**:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class SesMailService {
    private final MailSender mailSender;
    private final String from;

    public SesMailService(
            MailSender mailSender,
            @Value("${app.email.from}") String from) {
        this.mailSender = mailSender;
        this.from = from;
    }

    public void send(String recipient, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn " + orderId);
        message.setText("Đơn hàng " + orderId + " đã được tiếp nhận.");
        mailSender.send(message);
    }
}
~~~

Nếu dùng Spring Cloud AWS SES starter, request được gửi qua SES API và IAM role của ứng dụng được đánh giá. Nếu dùng SMTP, thay cơ chế xác thực bằng **SES SMTP credentials** đúng region; SMTP username/password không phải AWS SDK access key/secret key. Trong cả hai trường hợp, verified identity, sandbox, quota và suppression vẫn ảnh hưởng khả năng gửi.

## 5. Phân loại lỗi theo thời điểm

Không gom mọi lỗi email vào một loại **send failed**. Cần phân biệt lỗi trước khi SES chấp nhận request và lỗi sau khi SES đã tiếp nhận.

~~~mermaid
flowchart TD
    A["Spring Boot gửi email"] --> B{"SES tiếp nhận request?"}
    B -->|"Không"| C["API/SMTP error<br/>IAM, identity, sandbox, quota"]
    B -->|"Có"| D["SES MessageId"]
    D --> E{"Mail server người nhận?"}
    E -->|"Chấp nhận"| F["Delivery event"]
    E -->|"Từ chối vĩnh viễn"| G["Hard bounce"]
    E -->|"Lỗi tạm thời"| H["Soft bounce / delay"]
    D --> I["Người nhận báo spam"]
    I --> J["Complaint event"]
~~~

### 5.1. Lỗi trước khi SES tiếp nhận

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **MessageRejected / identity not verified** | From/recipient chưa được xác minh trong sandbox, hoặc identity không ở region gửi | Kiểm tra identity, From address và region |
| **AccessDenied** | IAM role thiếu **ses:SendEmail/ses:SendRawEmail**, resource hoặc condition sai | Xác định principal runtime, đối chiếu action, identity ARN và From |
| **Throttling / maximum sending rate exceeded** | Gửi vượt tốc độ cho phép | Queue, rate limiter, backoff có jitter |
| **Daily message quota exceeded** | Đã dùng hết quota 24 giờ | Kiểm tra quota theo region, giảm tốc độ hoặc xin tăng limit |
| **AccountSendingPaused / SendingEnabled=false** | AWS tạm dừng khả năng gửi của account | Kiểm tra trạng thái account và xử lý nguyên nhân với AWS |
| **Configuration set không tồn tại** | Request chỉ định tên configuration set sai hoặc set chưa được tạo | Kiểm tra SES configuration set ở đúng region |
| **SMTP 535 authentication failed** | Dùng sai SES SMTP username/password hoặc nhầm với AWS access key | Tạo/cấu hình SES SMTP credentials đúng region |
| **SMTP timeout/TLS failure** | Endpoint, port, TLS hoặc network egress sai | Kiểm tra endpoint, STARTTLS/SSL, firewall và timeout |

Một lỗi trước khi tiếp nhận thường có exception hoặc SMTP response code để ứng dụng phân loại. Không retry vô hạn với **AccessDenied**, **MessageRejected** hoặc identity chưa xác minh; cần sửa cấu hình hoặc dữ liệu trước.

### 5.2. Lỗi sau khi SES đã nhận email

Sau khi SES chấp nhận yêu cầu, mail server của người nhận mới quyết định chấp nhận hoặc từ chối thư. Những trạng thái thường gặp:

| Event | Ý nghĩa | Xử lý nghiệp vụ |
| --- | --- | --- |
| **Send** | SES ghi nhận yêu cầu gửi | Ghi nhận trạng thái accepted ở tầng SES |
| **Delivery** | Mail server đích chấp nhận email | Cập nhật delivered; không đồng nghĩa người nhận đã đọc |
| **Bounce** | Email không được giao tới địa chỉ/đích nhận | Phân loại permanent/transient và xử lý địa chỉ |
| **Complaint** | Người nhận báo email là spam | Ngừng gửi tới địa chỉ đó theo chính sách; kiểm tra consent và nội dung |
| **Reject** | SES từ chối message do nội dung/chính sách kiểm tra | Kiểm tra nội dung, virus scan hoặc điều kiện SES |
| **DeliveryDelay** | SES gặp vấn đề tạm thời khi giao tới mail server đích | Theo dõi retry và event tiếp theo |
| **RenderingFailure** | Không render được template SES | Kiểm tra template data và template version |

**Hard bounce/permanent bounce** thường báo địa chỉ không tồn tại hoặc không thể giao lâu dài. **Soft bounce/transient bounce** có thể do mailbox đầy, server tạm thời không sẵn sàng hoặc giới hạn nhận thư. Không tiếp tục retry hard bounce như một lỗi mạng tạm thời.

**Delivery** nghĩa là mail server nhận đã chấp nhận message. SES không thể khẳng định thư đã vào inbox chính, không bị lọc spam sau đó hoặc người nhận đã mở thư.

## 6. Bounce, complaint và suppression list

### 6.1. Vì sao phải xử lý bounce và complaint?

Gửi lặp tới địa chỉ không hợp lệ làm tăng bounce rate và ảnh hưởng uy tín domain/IP gửi. Gửi tới người đã báo spam làm tăng complaint rate, có thể khiến SES xem xét hoặc tạm dừng khả năng gửi của account.

Một hệ thống production cần:

- Ngừng gửi tới địa chỉ hard bounce.
- Xử lý complaint như một yêu cầu nghiêm túc về việc không muốn nhận thư.
- Tách email transactional và marketing theo consent, mục đích và chính sách unsubscribe.
- Ghi nhận thời gian, loại bounce/complaint, message ID và nguồn phát sự kiện.
- Không tự động thêm lại địa chỉ bị suppression chỉ vì một thao tác import danh sách.

### 6.2. Account-level suppression list

SES cung cấp **account-level suppression list** theo từng AWS Region. Tùy cấu hình, SES có thể thêm địa chỉ tạo **hard bounce** hoặc **complaint** vào danh sách suppression của account. Địa chỉ bị suppression sẽ được kiểm tra trước khi gửi.

Một số hành vi cần nhớ:

- Nếu địa chỉ nằm trong suppression list với reason đang được bật, SES có thể **chấp nhận request nhưng không thực hiện delivery**; ứng dụng cần quan sát bounce/event và suppression, không chỉ dựa vào API success.
- Địa chỉ trong account suppression list tồn tại cho đến khi được quản lý/xóa theo quy trình; đừng tự động retry cùng recipient.
- Chỉ bật reason cần thiết (**BOUNCE**, **COMPLAINT**) và có quy trình xử lý dữ liệu suppression.
- Suppression list của account là region-specific; kiểm tra đúng region khi điều tra.
- AWS global suppression list và account-level suppression list là hai khái niệm khác nhau. Không mặc định có thể truy vấn trực tiếp mọi địa chỉ trên global list.

Kiểm tra và bật account-level suppression list:

~~~bash
aws sesv2 get-account-suppression-attributes \
  --region ap-southeast-1

aws sesv2 put-account-suppression-attributes \
  --suppressed-reasons BOUNCE COMPLAINT \
  --region ap-southeast-1
~~~

Trước khi bật/thay đổi cấu hình account-wide, kiểm tra tác động với các ứng dụng khác cùng dùng SES trong region đó. Đừng coi suppression list là công cụ thay thế xác minh consent hoặc làm sạch danh sách người nhận.

### 6.3. Quy trình xử lý feedback

Một quy trình đơn giản:

1. Nhận bounce/complaint event từ SES.
2. Xác định **recipient**, **bounceType**, **bounceSubType**, **complaintFeedbackType**, **mail.messageId** và thông tin gửi liên quan.
3. Đối chiếu event với email/order/notification trong DB.
4. Với hard bounce, đánh dấu địa chỉ không hợp lệ hoặc suppressed; dừng gửi tự động.
5. Với complaint, cập nhật preference/consent và ngăn gửi tiếp theo chính sách.
6. Với soft bounce, chỉ retry khi lý do cho phép và trong giới hạn có backoff.
7. Ghi log có kiểm soát, tránh lưu toàn bộ nội dung email hoặc thông tin cá nhân không cần thiết.

Không sử dụng một retry policy giống nhau cho tất cả event. Ví dụ **mailbox full** có thể tạm thời, trong khi **no such user** cần dừng gửi.

## 7. Theo dõi trạng thái bằng configuration set và event publishing

### 7.1. Configuration set và event destination

**Configuration set** là nhóm cấu hình SES gắn với lần gửi, giúp định tuyến các sự kiện và áp dụng các tùy chọn theo dõi. Có thể gửi event tới các destination được SES hỗ trợ như:

- **Amazon SNS**: publish bounce/complaint/delivery events cho các subscriber.
- **Amazon EventBridge**: đưa sự kiện vào event bus để định tuyến đến nhiều đích.
- **Amazon CloudWatch**: theo dõi metric và cảnh báo.
- **Amazon Kinesis Data Firehose**: chuyển dữ liệu event tới hệ thống phân tích/lưu trữ khi được cấu hình.

Để bật event publishing:

1. Tạo configuration set trong đúng region SES.
2. Thêm event destination và chọn loại event cần theo dõi.
3. Cấu hình quyền cho SES gửi tới destination tương ứng.
4. Đảm bảo mỗi lần gửi sử dụng configuration set đó, hoặc đặt default configuration set cho identity nếu cấu hình hỗ trợ.
5. Gửi thư thử và xác nhận event xuất hiện ở destination.

Với SES API v2, request gửi email có thể chỉ định **ConfigurationSetName**. Ví dụ minh họa bằng AWS SDK for Java v2:

Thêm module **software.amazon.awssdk:sesv2** (version do AWS SDK BOM quản lý) nếu dự án chưa có:

~~~groovy
dependencies {
    implementation("software.amazon.awssdk:sesv2")
}
~~~

~~~java
import software.amazon.awssdk.services.sesv2.SesV2Client;
import software.amazon.awssdk.services.sesv2.model.Destination;
import software.amazon.awssdk.services.sesv2.model.EmailContent;
import software.amazon.awssdk.services.sesv2.model.Message;
import software.amazon.awssdk.services.sesv2.model.SendEmailRequest;

public class SesV2Sender {
    private final SesV2Client sesClient;

    public SesV2Sender(SesV2Client sesClient) {
        this.sesClient = sesClient;
    }

    public String send(String from, String to, String subject, String body) {
        SendEmailRequest request = SendEmailRequest.builder()
                .fromEmailAddress(from)
                .destination(Destination.builder()
                        .toAddresses(to)
                        .build())
                .content(EmailContent.builder()
                        .simple(Message.builder()
                                .subject(software.amazon.awssdk.services.sesv2.model.Content.builder()
                                        .data(subject).build())
                                .body(software.amazon.awssdk.services.sesv2.model.Body.builder()
                                        .text(software.amazon.awssdk.services.sesv2.model.Content.builder()
                                                .data(body).build())
                                        .build())
                                .build())
                        .build())
                .configurationSetName("transactional-events")
                .build();

        return sesClient.sendEmail(request).messageId();
    }
}
~~~

Ví dụ trên minh họa **SES API v2** để gắn configuration set vào request. Khi dùng **Spring Cloud AWS MailSender**, hãy xác nhận cách cấu hình configuration set mà phiên bản thư viện hỗ trợ; nếu cần điều khiển request chi tiết, có thể dùng adapter dựa trên **SesV2Client**. Không giả định mọi phương thức MailSender đều tự truyền configuration set.

### 7.2. Ví dụ event bounce

Một bounce event có thể chứa các trường khái niệm sau (payload thực tế phụ thuộc event schema và destination):

~~~json
{
  "eventType": "Bounce",
  "mail": {
    "messageId": "0100018example",
    "source": "no-reply@example.com"
  },
  "bounce": {
    "bounceType": "Permanent",
    "bounceSubType": "General",
    "bouncedRecipients": [
      {
        "emailAddress": "invalid-recipient@example.net",
        "status": "5.1.1",
        "action": "failed"
      }
    ]
  }
}
~~~

Worker nhận event cần xử lý idempotent vì event có thể được giao lại tùy destination. Khóa dedup có thể dựa trên message ID + event type + recipient hoặc event ID ổn định từ hệ thống nhận. Lưu lại trạng thái xử lý để không gửi lại thông báo hoặc cập nhật preference nhiều lần.

### 7.3. SNS feedback queue

Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Email sender"] --> SES(("Amazon SES"))
    SES -->|"Bounce / Complaint"| SNS(("SNS feedback topic"))
    SNS --> Q["SQS feedback queue"]
    Q --> W["Spring Boot<br/>Feedback worker"]
    W --> DB[("DB<br/>suppression / consent")]
~~~

Nếu dùng SNS làm event destination, cần cấu hình **SNS topic policy** cho phép SES publish. Nếu topic phân phối vào SQS, queue policy phải cho SNS service gửi message theo **aws:SourceArn**. Đây là luồng feedback; quyền của nó độc lập với quyền **ses:SendEmail** của sender.

## 8. Kiểm thử an toàn bằng SES mailbox simulator

SES có **mailbox simulator** giúp kiểm tra một số kết quả gửi thư mà không cần tạo mailbox thật hoặc gửi tới người dùng thật. Các địa chỉ mô phỏng phổ biến:

| Địa chỉ | Mục đích |
| --- | --- |
| **success@simulator.amazonses.com** | Kiểm tra luồng giao thư thành công |
| **bounce@simulator.amazonses.com** | Tạo bounce event |
| **complaint@simulator.amazonses.com** | Tạo complaint event |
| **suppressionlist@simulator.amazonses.com** | Kiểm tra hành vi suppression list |
| **ooto@simulator.amazonses.com** | Kiểm tra phản hồi ngoài văn phòng trong tình huống hỗ trợ |

Mailbox simulator được dùng trong sandbox và production; các giới hạn/quy tắc cụ thể của simulator cần theo tài liệu SES hiện hành. Sử dụng simulator thay vì thử bounce bằng email ngẫu nhiên hoặc gửi spam tới địa chỉ không thuộc quyền kiểm soát.

### 8.1. Ma trận kiểm thử

| Test | Chuẩn bị | Kết quả mong đợi |
| --- | --- | --- |
| Identity hợp lệ | From thuộc domain đã verify, đúng region | SES chấp nhận yêu cầu nếu quyền/quota hợp lệ |
| Identity sai region | Chỉ verify domain ở region khác | SES từ chối do identity chưa được xác minh tại region gửi |
| Sandbox recipient chưa verify | Gửi tới email thường chưa verify | Bị giới hạn theo sandbox |
| Sandbox simulator | Gửi tới mailbox simulator | Có thể mô phỏng kết quả theo địa chỉ simulator |
| IAM thiếu **ses:SendEmail** | Bỏ action khỏi role test | API bị từ chối |
| IAM thiếu **ses:SendRawEmail** | Gửi MIME bằng role chỉ có SendEmail | Đường raw email bị từ chối |
| Bounce simulator | Bật event destination, gửi tới bounce simulator | Nhận bounce event, worker cập nhật trạng thái |
| Complaint simulator | Bật event destination, gửi tới complaint simulator | Nhận complaint event, ngăn gửi tiếp theo chính sách |
| Account suppression | Thêm địa chỉ test vào suppression list | SES không thực hiện delivery khi reason tương ứng đang bật |
| Throttling | Phát nhiều request vượt rate thử nghiệm | Quan sát lỗi giới hạn và backoff |
| Sending paused | Kiểm tra account test bị pause nếu có | Không gửi được; chẩn đoán account state |

**Không nên** thay đổi trạng thái account production đang phục vụ người dùng chỉ để thử lỗi. Dùng account/region sandbox hoặc môi trường cô lập, policy riêng và địa chỉ simulator.

## 9. Runbook chẩn đoán lỗi chuyển phát

Khi người dùng báo “không nhận được email”, thực hiện theo thứ tự:

### Bước 1: Xác định request có được SES chấp nhận không

- Kiểm tra log Spring Mail/API, exception, SMTP response code và thời gian request.
- Nếu dùng SDK trực tiếp, ghi lại SES **MessageId** khi nhận response.
- Nếu dùng MailSender, ghi correlation ID và trạng thái request; không tự tạo MessageId giả.

Nếu request bị từ chối trước khi SES tiếp nhận, kiểm tra IAM, verified identity, region, sandbox, quota, account sending status và cấu hình SES.

### Bước 2: Kiểm tra identity và DNS

- Identity ở đúng region có **Verified** không?
- From address có thuộc identity được xác minh/ủy quyền không?
- DKIM record có trạng thái hợp lệ không?
- SPF/DMARC có alignment với domain gửi không?
- Custom MAIL FROM có MX và SPF record hợp lệ không?
- Nếu DNS vừa thay đổi, chờ propagation và xác minh lại từ SES.

### Bước 3: Kiểm tra trạng thái account và quota

~~~bash
aws sesv2 get-account \
  --region ap-southeast-1 \
  --query '{ProductionAccess:ProductionAccessEnabled,SendingEnabled:SendingEnabled,SendQuota:SendQuota}'
~~~

Nếu account bị pause, quota hết hoặc rate vượt, sửa theo nguyên nhân; không tăng retry ngay lập tức.

### Bước 4: Tra event delivery

- Tìm **mail.messageId**, recipient và timestamp.
- Nếu có **Delivery**, mail server đích đã chấp nhận thư; kiểm tra spam/quarantine/mailbox rule phía người nhận.
- Nếu **Bounce**, đọc bounce type/subtype và dừng gửi với hard bounce.
- Nếu **Complaint**, cập nhật preference/suppression và ngừng gửi theo chính sách.
- Nếu **DeliveryDelay**, theo dõi sự kiện tiếp theo và không tạo bản gửi mới không cần thiết.

### Bước 5: Kiểm tra suppression

Kiểm tra account-level suppression list trong đúng region và lý do địa chỉ bị thêm. Nếu địa chỉ hợp lệ đã được sửa, chỉ gỡ suppression khi có bằng chứng và quy trình nghiệp vụ cho phép; không tự động xóa hàng loạt để tăng delivery.

### Bước 6: Đối chiếu retry và trùng lặp

Dùng business event ID để kiểm tra email đã được SES chấp nhận trước đó chưa. Timeout không có nghĩa SES chưa nhận request. Nếu worker retry mà không lưu trạng thái, một email có thể được gửi nhiều lần.

## 10. Bảo mật và chất lượng gửi thư

- **Least privilege:** IAM role chỉ có action SES cần thiết và identity ARN cụ thể.
- **Không lộ secret:** không log nội dung nhạy cảm, SMTP password, access key hoặc token; dùng secret manager nếu cần.
- **Consent:** chỉ gửi email tới người nhận có cơ sở hợp lệ; marketing phải có quy trình unsubscribe và preference.
- **List hygiene:** loại địa chỉ không tồn tại, hard bounce và complaint; không mua hoặc import danh sách không rõ nguồn gốc.
- **Tách luồng gửi:** cân nhắc domain/subdomain, configuration set hoặc account riêng cho transactional và marketing để quản lý reputation.
- **Rate control:** dùng queue, giới hạn tốc độ và backoff; không phát burst vượt quota.
- **Theo dõi:** dashboard bounce/complaint/delivery, cảnh báo khi metric tăng bất thường; đánh giá xu hướng thay vì chỉ một request.
- **Kiểm thử:** dùng mailbox simulator, identity test và sandbox; chỉ chuyển production khi có quy trình feedback và suppression.

Danh tính gửi hợp lệ là điều kiện cần, không phải bảo đảm email vào inbox. Uy tín domain/IP, nội dung, hành vi người nhận, xác thực SPF/DKIM/DMARC và chính sách của mail provider đều tác động đến kết quả.

## 11. Bài tập và câu hỏi ôn tập

**Bài tập:** cấu hình một domain identity riêng cho môi trường thử nghiệm ở **ap-southeast-1**, bật Easy DKIM, công bố DMARC policy quan sát và xác minh From address. Dùng Spring Boot gửi email qua SES API trong sandbox, kiểm tra người nhận simulator, rồi bật event destination để xử lý bounce/complaint. Viết worker cập nhật trạng thái email và suppression idempotent.

Các nhiệm vụ:

1. Ghi lại identity, region, DKIM status, MAIL FROM status và sending status.
2. Gửi thư tới simulator thành công, bounce và complaint.
3. Ghi nhận event, đối chiếu message ID với bản ghi gửi trong DB.
4. Thử một request bị từ chối do quyền IAM hoặc identity chưa verify.
5. Tạo retry có backoff cho throttling, nhưng không retry hard bounce.
6. Viết unit test cho bộ phân loại event và integration test cho SES event destination.
7. So sánh gửi qua SES API với SMTP: xác thực, secret, lỗi và observability.

**Câu hỏi:**

1. Vì sao verify domain ở một region chưa bảo đảm gửi được từ region khác?
2. From header khác MAIL FROM domain ở điểm nào?
3. DKIM, SPF và DMARC hỗ trợ xác thực domain như thế nào?
4. Tài khoản sandbox có thể gửi tới những recipient nào?
5. Production access khác sending quota và **SendingEnabled** ra sao?
6. SES chấp nhận request nhưng không giao thư trong trường hợp nào?
7. Hard bounce, soft bounce và complaint cần được xử lý khác nhau thế nào?
8. Tại sao phải lưu message ID/correlation ID và xử lý feedback idempotent?
9. Vì sao mailbox simulator tốt hơn việc cố tình gửi thư tới địa chỉ không hợp lệ?
10. Khi email đã có Delivery event mà người nhận vẫn không thấy inbox, cần kiểm tra ở đâu tiếp theo?

## 12. Tài liệu tham khảo

- [Amazon SES — Getting started with sending email](https://docs.aws.amazon.com/ses/latest/dg/getting-started-sending.html): quy trình identity, sandbox, production access và thiết lập gửi.
- [Amazon SES — Verifying identities](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html): email/domain identities và xác minh.
- [Amazon SES — Easy DKIM](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim-easy.html): thiết lập DKIM và DNS record.
- [Amazon SES — SPF and DMARC](https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-spf.html): xác thực SPF, DKIM alignment và DMARC.
- [Amazon SES — Custom MAIL FROM domain](https://docs.aws.amazon.com/ses/latest/dg/mail-from.html): MAIL FROM, MX và SPF.
- [Amazon SES — Request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html): giới hạn sandbox và yêu cầu production.
- [Amazon SES — Sending quotas](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html): quota và tốc độ gửi theo region.
- [Amazon SES — Account-level suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html): bounce, complaint và suppression.
- [Amazon SES — Event publishing](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html): configuration sets và event destinations.
- [Amazon SES — Mailbox simulator](https://docs.aws.amazon.com/ses/latest/dg/send-an-email-from-console.html): kiểm thử delivery/bounce/complaint bằng simulator.
- [Spring Cloud AWS — SES Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#ses-integration): tích hợp SES với Spring Mail.

**Kết quả mong đợi:** người học cấu hình được danh tính gửi thư đã xác minh, hiểu sandbox và production access, tích hợp Spring Boot với SES đúng region/quyền, phân loại lỗi trước và sau khi gửi, đồng thời xử lý bounce/complaint/suppression dựa trên event thực tế.
