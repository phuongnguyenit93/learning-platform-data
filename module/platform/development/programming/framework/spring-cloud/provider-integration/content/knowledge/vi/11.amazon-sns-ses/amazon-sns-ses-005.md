# Phân quyền publish, subscribe và phối hợp topic policy với queue policy

## 1. Bài toán và mục tiêu

Giả sử dịch vụ **Order Service** được phát triển bằng Spring Boot và cần phát sự kiện **ORDER_CREATED**. Một ứng dụng khác đọc sự kiện từ Amazon SQS để gửi email bằng Amazon SES. Nhóm phát triển đã cấp quyền **sns:Publish** cho Order Service, tạo subscription **SNS → SQS**, nhưng message vẫn không đến queue. Nguyên nhân có thể nằm ở **queue policy**, vốn là lớp quyền độc lập với quyền publish.

Để triển khai đúng, cần phân biệt ba câu hỏi:

1. **Ai được phát thông báo lên SNS topic?** — quyền **sns:Publish**.
2. **Ai được đăng ký endpoint vào topic?** — quyền **sns:Subscribe**.
3. **SNS được phép gửi message vào SQS queue nào?** — quyền **sqs:SendMessage** trong **SQS queue resource policy**.

Bài học nằm trong chương **Amazon SNS và SES** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module tập trung thực hành Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, trong đó có danh tính/quyền, messaging, storage, dữ liệu, bảo vệ secret, kiểm thử tích hợp và lựa chọn cloud provider. Với SNS/SQS, hiểu các lớp quyền là yêu cầu nền tảng trước khi tích hợp Spring Cloud AWS vào hệ thống thực tế.

Sau bài học, bạn sẽ có thể:

- Phân biệt **IAM identity-based policy**, **SNS topic resource policy** và **SQS queue resource policy**.
- Cấp quyền publish và subscribe với nguyên tắc **least privilege**, không trao quyền tạo/sửa hạ tầng cho publisher.
- Thiết kế chính sách **SNS topic A → SQS queue B** trong cùng tài khoản và khác tài khoản AWS.
- Dùng **aws:SourceArn** và principal **sns.amazonaws.com** để giới hạn quyền SNS gửi vào queue.
- Kiểm tra **Subscription confirmation**, KMS encryption và quyền của worker đọc queue.
- Chẩn đoán một ca **Publish thành công nhưng không có message trong SQS** bằng các bước có thể lặp lại.

## 2. Ba ranh giới quyền trong một luồng SNS → SQS

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Service"] -->|"1. sns:Publish<br/>IAM role"| T(("SNS topic<br/>order-events"))
    A["Subscription admin"] -->|"2. sns:Subscribe<br/>IAM + topic policy"| T
    T -->|"3. sqs:SendMessage<br/>SQS queue policy"| Q["SQS queue<br/>order-email-jobs"]
    Q -->|"4. sqs:ReceiveMessage<br/>sqs:DeleteMessage"| W["Spring Boot<br/>Email Worker"]
    W -->|"ses:SendEmail<br/>quyền riêng nếu cần"| E["Amazon SES"]
~~~

**Các hành động này được kiểm soát tách biệt:**

| Chủ thể gọi API | API/action | Đối tượng | Chính sách thường liên quan |
| --- | --- | --- | --- |
| Publisher (Spring Boot) | **sns:Publish** | SNS topic ARN | IAM policy của workload; topic policy khi cần |
| Người quản lý subscription | **sns:Subscribe** | SNS topic ARN | IAM policy của người gọi; topic policy khi cross-account |
| Dịch vụ SNS giao message | **sqs:SendMessage** | SQS queue ARN | **SQS queue policy** cho principal **sns.amazonaws.com** |
| SQS worker | **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes** | SQS queue ARN | IAM policy của workload; queue policy khi cần cross-account |
| Worker gửi thư qua SES | **ses:SendEmail** (hoặc quyền SES thích hợp) | SES resources tương ứng | IAM/SES identity policies tùy cấu hình |

SNS **Publish** trả về kết quả thành công khi SNS chấp nhận yêu cầu; điều đó **không chứng minh SNS đã giao tới mọi subscription**, càng không chứng minh worker đã gửi email thành công.

### 2.1. IAM policy khác resource policy thế nào?

**Identity-based policy** gắn vào IAM role/user và trả lời: *Danh tính này được thực hiện hành động gì trên tài nguyên nào?*

**Resource-based policy** gắn vào chính tài nguyên (SNS topic, SQS queue) và trả lời: *Principal nào được truy cập tài nguyên này, bằng hành động nào, dưới điều kiện gì?* Resource policy có trường **Principal**; identity policy thông thường không có trường đó.

Một số quy tắc đánh giá quyền cần ghi nhớ:

- **Mặc định từ chối:** khi không có Allow phù hợp, yêu cầu bị từ chối.
- **Explicit Deny thắng mọi Allow:** deny trong IAM, resource policy, SCP hoặc chính sách kiểm soát phù hợp có thể chặn yêu cầu.
- **Cùng AWS account:** trong những trường hợp IAM thông thường, identity policy hoặc resource policy có thể cấp quyền; nhưng permission boundary, session policy, SCP, điều kiện resource và loại principal có thể thay đổi kết quả.
- **Khác AWS account:** thường cần **phía chủ tài nguyên cho phép bằng resource policy** và **phía principal gọi API có quyền identity-based thích hợp**. Đừng chỉ cấp Allow trong account của người gọi rồi giả định họ có thể dùng tài nguyên account khác.
- **AWS service principal:** khi SNS giao vào SQS, principal là dịch vụ **sns.amazonaws.com**, vì vậy policy cho ứng dụng publisher không thay thế queue resource policy.

Không nên diễn giải toàn bộ IAM thành phép cộng hai chính sách đơn giản: explicit Deny, tổ chức (SCP), permission boundary, endpoint policy và điều kiện request đều có thể ảnh hưởng. Khi chẩn đoán, cần xem **principal thực tế** đang gọi API, **resource ARN thực tế** và **hành động bị từ chối**.

## 3. Quyền sns:Publish cho ứng dụng Spring Boot

Giả sử topic cùng tài khoản AWS có ARN:

~~~text
arn:aws:sns:ap-southeast-1:111122223333:order-events
~~~

IAM role của Spring Boot publisher chỉ cần action **sns:Publish** trên topic này:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishOrderEventsOnly",
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

Đây là **identity-based policy**, gắn vào role của workload đang chạy ứng dụng. Ví dụ:

- **ECS**: task role.
- **EC2**: instance profile role.
- **EKS**: cơ chế cấp quyền workload phù hợp với cluster.
- **Máy phát triển**: AWS CLI profile/SDK credentials provider chain.

**Không hardcode access key/secret key vào application.yml, biến hằng trong Java hay Git.** Nếu phải quản lý secret ứng dụng, dùng hệ thống secret manager phù hợp và giới hạn quyền đọc secret riêng theo từng workload.

Publisher **không cần** các quyền **sns:CreateTopic**, **sns:SetTopicAttributes**, **sns:Subscribe** hay **sqs:SendMessage** khi trách nhiệm duy nhất của nó là phát lên topic đã provision. Các quyền tạo/sửa hạ tầng nên dành cho pipeline IaC hoặc người quản trị.

### 3.1. Cùng account có bắt buộc sửa topic policy?

Khi publisher và topic cùng account, một IAM Allow trên role thường đủ để gọi **sns:Publish**, miễn không có Deny hay điều kiện kiểm soát khác ngăn cản. Không cần tự thêm một Allow rộng cho **Principal: "*"** trong SNS topic policy chỉ để publisher cùng account hoạt động.

Khi một **AWS account khác** hoặc một **AWS service** cần publish lên topic, topic resource policy thường là nơi cấp quyền cho principal bên ngoài, và có thể kèm điều kiện hạn chế nguồn. Với service-to-service như S3 → SNS hay EventBridge → SNS, principal và điều kiện phải theo **tài liệu của dịch vụ nguồn**, không sử dụng mẫu cross-account IAM role một cách máy móc.

### 3.2. Ví dụ topic policy cho publisher khác tài khoản

Giả sử một role cụ thể ở account **444455556666** được phát thông báo lên topic account **111122223333**. Thêm **statement** sau vào SNS topic access policy của topic (giữ lại các statement quản trị hợp lệ đang có):

~~~json
{
  "Sid": "AllowExternalPublisherRole",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/external-order-publisher"
  },
  "Action": "sns:Publish",
  "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
}
~~~

Đồng thời role **external-order-publisher** cần quyền gọi **sns:Publish** trên ARN đó ở phía IAM account của role. Giới hạn Principal tới role thực sự cần publish; hạn chế dùng cả account nếu không có lý do quản trị rõ ràng.

**Cảnh báo thao tác:** Ví dụ trên là **một statement**, không phải toàn bộ JSON topic policy. Không dùng nó để ghi đè mù quáng policy hiện tại; làm như vậy có thể xóa các quyền quản lý topic cần thiết. Cập nhật thông qua IaC hoặc lấy policy hiện có, sửa có kiểm soát rồi kiểm tra lại.

## 4. Quyền sns:Subscribe và ai sở hữu subscription

**sns:Subscribe** là quyền gửi yêu cầu tạo quan hệ giữa một SNS topic và endpoint, ví dụ:

~~~text
Topic:    arn:aws:sns:ap-southeast-1:111122223333:order-events
Protocol: sqs
Endpoint: arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs
~~~

**Topic ARN** là đối tượng cần có quyền **sns:Subscribe**; **Endpoint** là ARN của queue sẽ nhận, không phải ARN của topic.

### 4.1. IAM policy cho người tạo subscription

Khi subscription admin thuộc account của topic và được ủy quyền quản lý hạ tầng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubscribeOnlyOrderTopic",
      "Effect": "Allow",
      "Action": "sns:Subscribe",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

Quyền này **chưa cấp** quyền cấu hình queue, xem message hay xử lý email. Khi account B sở hữu SQS queue muốn tự tạo subscription vào topic account A, cả **topic policy ở A** lẫn **IAM policy của principal thực hiện Subscribe tại B** phải phù hợp.

### 4.2. Topic policy cho phép account khác subscribe

Account A sở hữu topic **order-events**. Account B sở hữu queue **order-email-jobs** và role **queue-subscription-admin**. Trên **SNS topic policy ở A**, thêm statement:

~~~json
{
  "Sid": "AllowExternalQueueOwnerToSubscribe",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/queue-subscription-admin"
  },
  "Action": "sns:Subscribe",
  "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events",
  "Condition": {
    "StringEquals": {
      "sns:Protocol": "sqs",
      "sns:Endpoint": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs"
    }
  }
}
~~~

Ở phía account B, gắn thêm IAM policy cho role **queue-subscription-admin**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubscribeToAccountATopic",
      "Effect": "Allow",
      "Action": "sns:Subscribe",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

Condition keys **sns:Protocol** và **sns:Endpoint** hạn chế **loại endpoint** và **địa chỉ endpoint** được đăng ký. Chúng thuộc SNS topic policy, khác với **aws:SourceArn** trên SQS queue policy ở mục sau.

**Trách nhiệm sở hữu subscription:** Với SNS → SQS khác account, AWS khuyến nghị **queue owner tạo subscription**, giúp subscription của SQS được xác nhận tự động trong luồng được hỗ trợ. Nếu người không sở hữu queue tạo subscription, có thể phải xác nhận subscription bằng thông điệp xác nhận gửi tới queue trước khi nhận notification. Với email/HTTP(S), cơ chế xác nhận endpoint có quy tắc riêng. Đừng xem trạng thái **PendingConfirmation** là đã sẵn sàng giao message.

Sau khi tạo subscription, dùng **SubscriptionArn** để theo dõi và quản lý các thuộc tính. Việc unsubscribe/confirm có quy tắc xác thực và quyền sở hữu riêng; không giả định cấp **sns:Subscribe** tự động cho phép thao tác quản trị mọi subscription.

## 5. Queue policy: cho phép SNS thực hiện sqs:SendMessage

Một queue SQS cần cấp phép cho **SNS service principal** để nhận message từ một topic. Đây là lớp quyền riêng, ngay cả khi publisher có thể publish và subscription đã tồn tại.

Giả sử queue nằm ở account B:

~~~text
arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs
~~~

**SQS queue access policy** nên chứa statement:

~~~json
{
  "Sid": "AllowOnlyOrderEventsTopic",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  }
}
~~~

**Giải thích từng phần:**

| Field | Giá trị | Lý do |
| --- | --- | --- |
| **Principal** | **Service: sns.amazonaws.com** | AWS SNS là bên trực tiếp yêu cầu SQS nhận message |
| **Action** | **sqs:SendMessage** | Chỉ cho phép hành động gửi message; không cấp quyền đọc/xóa |
| **Resource** | **queue ARN** | Quyền áp dụng trên đúng queue của account B |
| **Condition** | **ArnEquals aws:SourceArn = topic ARN** | Chỉ cho phép message có nguồn là topic A, giảm rủi ro confused deputy |

Nếu queue nhận từ nhiều topic, có thể khai báo nhiều statement/ARN phù hợp và tuân thủ giới hạn policy; không mở **Principal: "*"** hay bỏ điều kiện nguồn chỉ để khắc phục một ca giao nhận thất bại. **aws:SourceAccount** có thể bổ sung ràng buộc account theo tình huống, nhưng khi biết chính xác topic thì **aws:SourceArn** cụ thể là cách giới hạn rõ ràng hơn.

**Chú ý quan trọng:** **aws:SourceArn ở queue policy là ARN của SNS topic**, không phải ARN subscription, IAM role của publisher hay queue URL. Khi queue dùng encryption với customer-managed AWS KMS key, queue policy đúng vẫn có thể chưa đủ: SNS có thể cần **kms:GenerateDataKey** và **kms:Decrypt** trên KMS key theo key policy. Phần KMS được trình bày ở mục 8.

### 5.1. JSON queue policy hoàn chỉnh

Để cấu hình trong SQS Access policy hoặc Terraform/CloudFormation, đặt statement trên vào một policy JSON có **Version** và **Statement**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyOrderEventsTopic",
      "Effect": "Allow",
      "Principal": {
        "Service": "sns.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
        }
      }
    }
  ]
}
~~~

Khi queue đã có policy phục vụ các mục đích khác, hợp nhất statement vào policy hiện có và giữ quyền cần thiết. Tránh áp dụng một document mới làm mất các statement đang được dùng.

### 5.2. Policy cho SQS worker là quyền khác

Worker trong account B đọc queue và xóa message sau khi hoàn thành:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrderEmailJobs",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs"
    }
  ]
}
~~~

Đây là **identity-based policy** của worker, không phải policy cấp cho principal SNS. Cấp quyền đọc/xóa cho SNS sẽ không giúp worker tiêu thụ queue; cấp quyền đọc/xóa cho publisher cũng không cần thiết nếu publisher chỉ phát lên topic.

## 6. Cách phối hợp topic policy và queue policy giữa hai AWS account

Ví dụ:

- **Account A (111122223333):** SNS topic **order-events**, role Spring Boot publisher.
- **Account B (444455556666):** SQS queue **order-email-jobs**, role quản lý subscription và role worker.
- Cả hai resource ở **ap-southeast-1** để dễ thực hành. Các ARN trong bài chỉ là dữ liệu mẫu.

~~~mermaid
sequenceDiagram
    participant IA as "Spring Boot / IAM role A"
    participant S as "SNS topic / account A"
    participant AD as "Subscription admin / account B"
    participant Q as "SQS queue / account B"
    participant W as "Consumer / IAM role B"

    AD->>S: Subscribe(topic A, queue ARN B)
    Note over AD,S: IAM role B + SNS topic policy A cho sns:Subscribe
    S-->>AD: SubscriptionArn / confirmation status
    IA->>S: Publish(message)
    Note over IA,S: IAM role A cho sns:Publish
    S->>Q: SendMessage(message)
    Note over S,Q: Queue policy B cho sns.amazonaws.com và SourceArn=topic A
    W->>Q: ReceiveMessage
    Q-->>W: Message + ReceiptHandle
    W->>Q: DeleteMessage khi xử lý thành công
~~~

### 6.1. Quy trình cấu hình khuyến nghị

1. **A tạo topic**, lưu topic ARN và cấp **sns:Publish** cho role publisher.
2. **B tạo queue**, lưu queue ARN/URL và chuẩn bị quyền worker đọc queue.
3. **A bổ sung SNS topic policy** cho role subscription admin B được **sns:Subscribe** vào topic A. Có thể giới hạn protocol và endpoint.
4. **B bổ sung queue policy** cho service **sns.amazonaws.com** được **sqs:SendMessage**, điều kiện **SourceArn=topic A**.
5. **B gọi Subscribe** bằng danh tính **queue owner**, theo dõi trạng thái subscription. Nếu pending confirmation, xử lý xác nhận đúng quy trình của AWS.
6. **A thử Publish** bằng role publisher. **B xác minh SQS nhận** và worker xóa message sau khi xử lý.
7. **Quan sát lỗi** ở từng bước và thêm retry/DLQ phù hợp; nếu dùng KMS, kiểm tra key policy.

**Không có policy nào trong ba loại này tự thay thế được hai policy còn lại.**

### 6.2. Lệnh AWS CLI để kiểm tra

Các lệnh dưới đây dùng hai AWS CLI profile đã cấu hình: **topic-owner** cho account A và **queue-owner** cho account B. Những ARN/account ID cần đổi theo môi trường thực.

Kiểm tra danh tính đang dùng và quyền quan sát topic:

~~~bash
aws sts get-caller-identity --profile topic-owner
aws sts get-caller-identity --profile queue-owner

aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --query 'Attributes.Policy' \
  --output text \
  --region ap-southeast-1 \
  --profile topic-owner
~~~

Kiểm tra queue policy bằng queue **URL**:

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/444455556666/order-email-jobs \
  --attribute-names QueueArn Policy \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

Tạo subscription **bằng danh tính thuộc account sở hữu queue**, sau khi cả hai policy đã được cấu hình:

~~~bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --protocol sqs \
  --notification-endpoint arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

Thao tác này đòi hỏi profile **queue-owner** sử dụng principal được topic policy cho phép Subscribe và có IAM permission phù hợp; nên chọn queue owner để subscription được tự xác nhận theo hướng dẫn AWS.

Xem danh sách subscription:

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1 \
  --profile topic-owner
~~~

Gửi một message và kiểm tra queue:

~~~bash
aws sns publish \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --message '{"eventId":"evt-1001","eventType":"ORDER_CREATED","orderId":"ord-1001"}' \
  --region ap-southeast-1 \
  --profile topic-owner

aws sqs receive-message \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/444455556666/order-email-jobs \
  --wait-time-seconds 10 \
  --max-number-of-messages 10 \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

Trong thực tế, có thể cần profile riêng cho **publisher**, **subscription admin**, **consumer** vì **topic-owner/queue-owner** ở ví dụ chỉ thể hiện ranh giới tài khoản. Lệnh đọc queue cần quyền **sqs:ReceiveMessage**; lệnh list/read cần quyền IAM đọc tương ứng. **Một lần receive-message trả về rỗng không đủ để khẳng định message không tồn tại**, nhất là khi có consumer đang poll hoặc message chưa được giao xong.

## 7. Tích hợp với Spring Boot

Một ứng dụng Spring Boot chỉ publish thông điệp không cần biết có bao nhiêu SQS queue subscribe, và không cần SDK SQS. Ví dụ dùng **Spring Cloud AWS 3.x** với **SnsTemplate**.

**Gradle (Groovy DSL)**:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Chọn **springCloudAwsVersion** tương thích với Spring Boot của dự án; dùng BOM để quản lý version đồng bộ.

**application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}

app:
  sns:
    topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

**Publisher**:

~~~java
package demo.notifications;

import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public OrderNotificationPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.sns.topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void sendOrderCreated(String orderId) {
        OrderCreated message = new OrderCreated("ORDER_CREATED", orderId);
        snsTemplate.sendNotification(topicArn, message, "Order created");
    }

    public record OrderCreated(String eventType, String orderId) {}
}
~~~

Ở đây **SnsTemplate** dùng Jackson message converter để tuần tự hóa POJO thành JSON; không cần nối chuỗi JSON thủ công. Trong ứng dụng thật, bổ sung **eventId** và **schemaVersion** vào hợp đồng sự kiện. Nếu yêu cầu filter theo **MessageAttributes**, sử dụng Spring Messaging headers hoặc SDK **MessageAttributeValue** để gửi metadata tương ứng.

**Runtime credentials:** AWS SDK dùng credentials provider chain. Trên AWS, nên cấp quyền cho runtime role; tại máy phát triển sử dụng AWS CLI profile. Không gắn access key vào source. Nếu SDK báo AccessDenied ở **sns:Publish**, kiểm tra role và topic policy trước khi tìm lỗi SQS.

## 8. KMS encryption và những giới hạn của policy thông thường

Khi mã hóa bằng **customer-managed KMS key**, có thêm một lớp quyền riêng ngoài IAM/topic/queue policies.

### 8.1. Queue dùng SSE-KMS với key do khách hàng quản lý

Nếu queue ở account B dùng KMS key do khách hàng quản lý, **KMS key policy** cần cho **sns.amazonaws.com** sử dụng các hành động phù hợp để SNS giao message vào queue, thường là **kms:GenerateDataKey** và **kms:Decrypt**. Ví dụ statement minh họa trong **KMS key policy**:

~~~json
{
  "Sid": "AllowSNSToEncryptForQueue",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*"
}
~~~

**Resource: "*" trong KMS key policy** biểu thị chính KMS key mà policy được gắn; đây **không phải** khuyến nghị cấp **kms:*** trên tất cả các khóa cho ứng dụng. Khi áp dụng thực tế, bổ sung các điều kiện ràng buộc nguồn/account phù hợp theo tài liệu KMS/SQS để tránh cấp quyền quá rộng. Worker đọc queue mã hóa cũng cần **kms:Decrypt** khi cấu hình KMS yêu cầu. KMS key policy, IAM role và loại key phải được đánh giá cùng nhau.

### 8.2. Topic cũng dùng SSE-KMS

Nếu chính **SNS topic** được mã hóa bằng customer-managed key, publisher có thể cần quyền KMS bổ sung; nếu AWS service làm publisher, KMS key policy phải cho phép service nguồn thực hiện thao tác cần thiết. Việc queue dùng KMS và topic dùng KMS là hai chặng khác nhau: xác minh từng key ARN và quyền theo đúng phương án mã hóa.

### 8.3. Filter không giải quyết vấn đề quyền

**Subscription FilterPolicy** chỉ quyết định message có khớp điều kiện giao hàng hay không. Nó **không cấp quyền** publish, subscribe hoặc gửi vào SQS; một message khớp filter nhưng thiếu queue policy vẫn có thể không được giao. Ngược lại, một message không khớp filter bị loại là hành vi thiết kế hợp lệ, không phải lỗi AccessDenied.

## 9. Chẩn đoán từng loại AccessDenied và lỗi phân phối

| Triệu chứng | Nơi cần kiểm tra | Hành động |
| --- | --- | --- |
| Spring Boot **AccessDenied** khi Publish | IAM role publisher, topic ARN, topic policy, SCP/permission boundary, KMS topic | Xác định principal từ runtime; đối chiếu **sns:Publish** |
| Account B **AccessDenied** khi Subscribe | IAM policy của role B và SNS topic policy ở A | Cấp **sns:Subscribe** cho đúng role/ARN, không mở wildcard |
| Subscription vẫn **PendingConfirmation** | Người tạo không sở hữu queue hoặc endpoint chưa xác nhận | Xác nhận theo quy trình SNS cho SQS/endpoint |
| Publish thành công nhưng queue rỗng | **SQS queue policy**, aws:SourceArn, subscription, queue ARN/URL, KMS, filter | Xem queue policy và metric delivery của SNS |
| SNS giao được vào queue nhưng worker không nhận | IAM worker, SQS visibility timeout, consumer cạnh tranh, queue URL | Xem **sqs:ReceiveMessage**, metrics và log consumer |
| Worker nhận nhưng không xóa được | IAM worker thiếu **sqs:DeleteMessage** hoặc receipt handle sai | Cập nhật đúng quyền và logic DeleteMessage |
| Message đến queue nhưng worker lỗi giải mã | **RawMessageDelivery** và định dạng SNS envelope | Đồng bộ cấu hình subscription với parser |
| Nhiều bản của cùng event được xử lý | At-least-once delivery hoặc retry | Dùng **eventId** và idempotent consumer |

Đường kiểm tra nên bắt đầu từ chỗ yêu cầu đầu tiên bị từ chối: *ai gọi action nào trên ARN nào?* Nếu **Publish thành công** nhưng SQS không có message, hãy kiểm tra subscription, filter và queue policy; kiểm tra CloudWatch SNS metrics, lỗi giao hàng và subscription DLQ nếu có. Nếu message đã nằm trong SQS, quan sát tiếp worker, retry và SQS DLQ.

**SNS subscription DLQ** xử lý thông điệp SNS không giao tới endpoint thành công. **SQS consumer DLQ** xử lý thông điệp đã vào queue chính nhưng worker thất bại sau các lần nhận. Hai loại DLQ ở hai giai đoạn khác nhau và cũng phải được cấu hình quyền phù hợp.

### 9.1. Bài kiểm tra quyền chủ động

Trong **AWS sandbox**, không nên thử bằng cách tăng role lên **AdministratorAccess**. Hãy thực hiện các thay đổi có chủ đích rồi quan sát:

1. Bỏ **sns:Publish** khỏi role publisher: Publish phải bị từ chối trừ khi có một Allow hợp lệ khác.
2. Bỏ quyền **sns:Subscribe** của role B hoặc statement cho role B trên topic A: yêu cầu Subscribe cross-account phải bị từ chối.
3. Khôi phục quyền Subscribe, nhưng bỏ statement **sqs:SendMessage** trong queue policy: subscription có thể tồn tại, nhưng SNS không giao được message vào queue.
4. Đổi **aws:SourceArn** trong queue policy thành ARN topic khác: message từ topic ban đầu bị chặn.
5. Khôi phục queue policy nhưng đặt filter không khớp: message bị lọc và không vào queue, không nhất thiết có delivery failure.
6. Với KMS key dùng cho queue, kiểm tra quyền của principal SNS và consumer trong môi trường thử nghiệm; quan sát lỗi mã hóa riêng với lỗi policy SQS.

Các phép thử thao tác trên sandbox riêng có thể ảnh hưởng luồng giao nhận và số lượng message, nên chỉ dùng tài nguyên test. Khôi phục chính sách theo IaC được quản lý sau mỗi tình huống.

## 10. Câu hỏi ôn tập và bài tập thực hành

**Câu hỏi kiểm tra:**

1. Tại sao role publisher có **sns:Publish** vẫn chưa bảo đảm SQS queue nhận message?
2. Trên topic policy của account A, khi nào cần thêm **Principal** là role của account B?
3. **sns:Subscribe** được xét trên topic ARN hay queue ARN?
4. Ai là principal trong queue policy khi SNS giao message sang SQS, và vì sao **aws:SourceArn** nên là topic ARN?
5. Hai tài khoản cùng cấu hình Subscribe nhưng một bên đang **PendingConfirmation**: bạn sẽ kiểm tra ai tạo subscription trước như thế nào?
6. Nếu subscriber đã nhận được message nhưng consumer không xóa được message, quyền nào đang thiếu?
7. Vì sao một Allow rộng trong SQS queue policy có thể tạo lỗ hổng **confused deputy**?
8. Topic được mã hóa và queue được mã hóa có thể cần những kiểm tra KMS quyền khác nhau ở đâu?

**Bài tập thực hành:**

- Provision SNS topic trong account A và SQS queue trong account B.
- Gắn IAM policy **sns:Publish** cho role Order Service ở A.
- Gắn IAM policy **sns:Subscribe** cho role subscription admin ở B, đồng thời thêm SNS topic statement cấp quyền cho role này.
- Gắn SQS queue policy cho **sns.amazonaws.com** với **aws:SourceArn** trỏ đúng topic A.
- Tạo subscription bằng principal thuộc account B, xác minh trạng thái subscription.
- Publish một sự kiện và xác minh queue nhận được; chạy consumer có quyền đọc và xóa message.
- Cố tình tạo một lỗi trong từng lớp quyền, ghi lại API thất bại, mã lỗi, chính sách nguyên nhân và cách khắc phục.

**Tiêu chí hoàn thành:** publisher chỉ có quyền publish đúng topic; subscription admin chỉ được đăng ký endpoint cần thiết; SNS chỉ được gửi vào queue từ topic xác định; consumer chỉ có quyền trên queue cần đọc; mọi lỗi đều được truy vết tới đúng lớp quyền.

## 11. Tài liệu tham khảo

- [AWS SNS — Using identity-based policies](https://docs.aws.amazon.com/sns/latest/dg/sns-using-identity-based-policies.html): sự khác nhau giữa IAM và SNS topic policy, cùng condition keys **sns:Protocol**/**sns:Endpoint**.
- [AWS SNS — Subscribing an SQS queue to a topic](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html): queue policy và **aws:SourceArn**.
- [AWS SNS — Sending SNS messages to SQS in another account](https://docs.aws.amazon.com/sns/latest/dg/sns-send-message-to-sqs-cross-account.html): điều kiện cross-account và subscription confirmation.
- [AWS SQS — Subscribe a queue to SNS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html): các bước trên queue owner và quyền theo account.
- [AWS SNS — Access policy examples](https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-use-cases.html): topic và queue policy thực hành.
- [AWS SNS — Server-side encryption with encrypted SQS](https://docs.aws.amazon.com/sns/latest/dg/sns-enable-encryption-for-topic-sqs-queue-subscriptions.html): quyền KMS khi SNS giao vào SQS mã hóa.
- [AWS SQS — Least-privilege KMS policies](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-least-privilege-policy.html): bảo vệ khóa, service producer và consumer.
- [Spring Cloud AWS 3.x — Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html): starter SNS, SnsTemplate, AWS credentials/region.

**Kết quả mong đợi:** người học tự cấu hình được một luồng **Spring Boot → SNS → SQS**, phân định rõ **sns:Publish**, **sns:Subscribe**, **sqs:SendMessage**, IAM của worker và key policy; đồng thời xác minh đúng cơ chế liên tài khoản và chẩn đoán sự cố giao nhận dựa trên từng ranh giới quyền.
