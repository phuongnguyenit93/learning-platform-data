# Lọc subscription và phân phối SNS đến nhiều SQS queue

## 1. Bài toán: một sự kiện, nhiều consumer

Một hệ thống bán hàng viết bằng Spring Boot phát sinh các sự kiện **ORDER_CREATED**, **ORDER_PAID** và **ORDER_CANCELLED**. Khi nhận thông tin này, dịch vụ email gửi thư xác nhận, dịch vụ kiểm soát rủi ro xem xét các giao dịch bất thường, còn hệ thống phân tích cần ghi nhận **mọi** sự kiện. Nếu dịch vụ đơn hàng gọi trực tiếp từng worker, nó phải biết danh sách người nhận và phụ thuộc vào trạng thái của họ.

**Amazon Simple Notification Service (SNS)** cho phép ứng dụng **publish** một message vào **topic**. Mỗi **subscription** có thể gửi một bản thông báo đến **Amazon Simple Queue Service (SQS)** và dùng **filter policy** để chỉ nhận thông điệp đáp ứng điều kiện. Các worker lấy message từ queue của mình và xử lý bất đồng bộ.

Bài học này thuộc chương **Amazon SNS và SES**, trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành Spring Boot kết nối dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Trọng tâm ở đây là messaging AWS; những nguyên tắc về danh tính, quyền truy cập, secret, kiểm thử tích hợp và lựa chọn cloud provider vẫn áp dụng cho toàn bộ module.

Sau bài học, bạn có thể:

- Giải thích đường đi **publisher → SNS topic → subscription filter → nhiều SQS queue → worker**.
- Thiết kế **FilterPolicy** theo **MessageAttributes** và **MessageBody**, gồm điều kiện AND, OR, prefix và numeric.
- Khai báo SNS topic, ba SQS queue, queue policy và subscription bằng CloudFormation.
- Phát sự kiện từ Spring Boot, theo dõi fan-out, kiểm thử việc lọc và chẩn đoán lỗi giao nhận.
- Phân biệt raw delivery, DLQ của SNS, DLQ của SQS, quyền IAM và tính nhất quán của subscription filter.

## 2. Kiến trúc fan-out có chọn lọc

Giả sử topic **order-events-dev** nối với ba queue:

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Publisher"] -->|"Publish"| T(("SNS topic<br/>order-events-dev"))
    T -->|"eventType=ORDER_CREATED"| E["SQS<br/>email-jobs-dev"]
    T -->|"eventType=ORDER_PAID<br/>AND riskLevel=HIGH"| F["SQS<br/>fraud-review-dev"]
    T -->|"không filter"| A["SQS<br/>analytics-events-dev"]
    E --> EW["Email worker<br/>sau đó có thể gọi SES"]
    F --> FW["Fraud worker"]
    A --> AW["Analytics worker"]
~~~

Một message có thể được chuyển đến **nhiều queue khác nhau**. SNS đánh giá chính sách của **từng subscription độc lập**. Các queue có tốc độ tiêu thụ, retry, visibility timeout và dead-letter queue (DLQ) riêng. SQS consumer chủ động gọi **ReceiveMessage** (hoặc Spring Cloud AWS listener) để nhận message; SNS không chạy mã nghiệp vụ bên trong worker.

| Message được phát | Queue email | Queue fraud | Queue analytics |
| --- | --- | --- | --- |
| **ORDER_CREATED**, LOW | Nhận | Không | Nhận |
| **ORDER_PAID**, HIGH | Không | Nhận | Nhận |
| **ORDER_PAID**, LOW | Không | Không | Nhận |
| **ORDER_CANCELLED**, LOW | Không | Không | Nhận |
| Thiếu **eventType**, HIGH | Không | Không | Nhận |

Queue analytics không có filter nên nhận mọi message được phân phối thành công. Nếu tất cả subscription đều có filter và message không thỏa điều kiện nào, SNS sẽ không giao message đến queue nào; đó là hành vi lọc hợp lệ.

### Thành phần cần phân biệt

| Khái niệm | Trách nhiệm |
| --- | --- |
| **Publisher** | Gọi SNS Publish, cung cấp payload và message attributes |
| **SNS topic** | Đích logic trung tâm được xác định bởi một topic ARN |
| **Subscription** | Liên kết topic và endpoint, chứa filter, raw delivery và các cấu hình giao nhận |
| **SQS queue** | Lưu tạm message, cho phép worker xử lý bất đồng bộ |
| **Worker/consumer** | Poll queue, thực thi nghiệp vụ, xóa message khi hoàn tất |
| **Amazon SES** | Gửi email giao dịch nếu email worker gọi SES; không đảm nhiệm routing fan-out |

## 3. Subscription FilterPolicy hoạt động thế nào?

### 3.1. Lọc theo MessageAttributes

Phạm vi mặc định của **FilterPolicyScope** là **MessageAttributes**. Publisher có thể gửi phần thân sự kiện như JSON và hai thuộc tính metadata bên ngoài phần thân:

~~~json
{
  "Message": "{\"eventId\":\"evt-101\",\"eventType\":\"ORDER_PAID\",\"orderId\":\"ord-101\",\"riskLevel\":\"HIGH\"}",
  "MessageAttributes": {
    "eventType": {"DataType": "String", "StringValue": "ORDER_PAID"},
    "riskLevel": {"DataType": "String", "StringValue": "HIGH"}
  }
}
~~~

Đây là **minh họa dữ liệu của PublishRequest**, không phải nguyên văn body mà consumer nhận từ SQS.

Filter cho queue email:

~~~json
{
  "eventType": ["ORDER_CREATED"]
}
~~~

Filter cho queue fraud:

~~~json
{
  "eventType": ["ORDER_PAID"],
  "riskLevel": ["HIGH"]
}
~~~

**Quy tắc chính:**

1. **AND giữa các khóa:** filter fraud yêu cầu cả **eventType=ORDER_PAID** *và* **riskLevel=HIGH**.
2. **OR giữa các giá trị của cùng khóa:** **{"eventType":["ORDER_CREATED","ORDER_PAID"]}** khớp một trong hai.
3. Thuộc tính không được nhắc trong filter không tác động đến việc so khớp.
4. Thuộc tính bắt buộc bị thiếu hoặc sai kiểu sẽ làm filter không khớp; chuỗi **HIGH** và **high** khác nhau ở kiểu so khớp thông thường.
5. Subscription **không có FilterPolicy** nhận mọi thông báo của topic, tùy quyền và trạng thái endpoint.

### 3.2. Lọc theo MessageBody

Nếu publisher phát **JSON object** hợp lệ nhưng không gửi metadata riêng, đặt **FilterPolicyScope=MessageBody** để lọc theo các trường trong body.

Ví dụ phần thân:

~~~json
{
  "eventId": "evt-101",
  "eventType": "ORDER_PAID",
  "risk": {
    "level": "HIGH",
    "score": 92
  }
}
~~~

Filter JSON theo body:

~~~json
{
  "eventType": ["ORDER_PAID"],
  "risk": {
    "level": ["HIGH"]
  }
}
~~~

**MessageBody** hỗ trợ truy cập trường lồng nhau trong JSON. Với **MessageAttributes**, tên trường là tên message attribute độc lập, không tự động truy cập các trường bên trong JSON body. Nếu scope là **MessageAttributes**, việc payload chứa **eventType** chưa đủ để subscription khớp nếu publisher không gửi attribute cùng tên.

### 3.3. Một số toán tử có ích

| Nhu cầu | FilterPolicy | Ý nghĩa |
| --- | --- | --- |
| Hai loại sự kiện | **{"eventType":["ORDER_CREATED","ORDER_PAID"]}** | OR |
| Bỏ qua môi trường thử | **{"environment":[{"anything-but":"sandbox"}]}** | Loại giá trị sandbox |
| Tenant có tiền tố | **{"tenantId":[{"prefix":"vip-"}]}** | Chuỗi bắt đầu bằng vip- |
| Điểm rủi ro cao | **{"riskScore":[{"numeric":[">=",80]}]}** | So sánh số |
| Có trace ID | **{"traceId":[{"exists":true}]}** | Yêu cầu tồn tại |

Với attribute-based filtering, gửi **Number** attribute phù hợp khi dùng numeric filter, và không dùng **Binary** attribute làm khóa lọc. Tên attribute, kiểu, chữ hoa/thường và giá trị phải tương thích với chính sách. Khi có nhiều nhánh điều kiện, kiểm tra giới hạn tổ hợp và độ phức tạp filter hiện hành của SNS thay vì gộp hàng nghìn giá trị vào một policy.

**Thay đổi FilterPolicy không luôn có hiệu lực ngay:** theo tài liệu AWS, thay đổi có thể cần **tới 15 phút** để lan truyền đầy đủ. Trong integration test, chờ cấu hình ổn định trước khi kết luận message bị lọc sai.

## 4. Cấu hình ba queue và subscription bằng CloudFormation

Mẫu **CloudFormation** sau triển khai một Standard SNS topic và ba Standard SQS queue. Mỗi subscription có điều kiện riêng; queue analytics cố ý không có filter. Ví dụ dùng trong môi trường sandbox/dev và được lưu thành **sns-fanout.yml** khi thực hành.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Filtered SNS fan-out to three SQS queues

Resources:
  OrderEventsTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: order-events-dev

  EmailQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: email-jobs-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  FraudQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: fraud-review-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  AnalyticsQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: analytics-events-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  QueueAccessPolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref EmailQueue
        - !Ref FraudQueue
        - !Ref AnalyticsQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: AllowOnlyOrderEventsTopic
            Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource:
              - !GetAtt EmailQueue.Arn
              - !GetAtt FraudQueue.Arn
              - !GetAtt AnalyticsQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref OrderEventsTopic

  EmailSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt EmailQueue.Arn
      FilterPolicyScope: MessageAttributes
      FilterPolicy:
        eventType: [ORDER_CREATED]
      RawMessageDelivery: true

  FraudSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt FraudQueue.Arn
      FilterPolicyScope: MessageAttributes
      FilterPolicy:
        eventType: [ORDER_PAID]
        riskLevel: [HIGH]
      RawMessageDelivery: true

  AnalyticsSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt AnalyticsQueue.Arn
      RawMessageDelivery: true

Outputs:
  TopicArn:
    Value: !Ref OrderEventsTopic
  EmailQueueUrl:
    Value: !Ref EmailQueue
  FraudQueueUrl:
    Value: !Ref FraudQueue
  AnalyticsQueueUrl:
    Value: !Ref AnalyticsQueue
  EmailSubscriptionArn:
    Value: !Ref EmailSubscription
  FraudSubscriptionArn:
    Value: !Ref FraudSubscription
~~~

Có thể triển khai bằng AWS CLI (cú pháp Bash):

~~~bash
aws cloudformation deploy \
  --template-file sns-fanout.yml \
  --stack-name sns-fanout-dev \
  --region ap-southeast-1

aws cloudformation describe-stacks \
  --stack-name sns-fanout-dev \
  --query "Stacks[0].Outputs" \
  --output table \
  --region ap-southeast-1
~~~

**Các điểm cần hiểu trong template:**

- **!Ref OrderEventsTopic** trả về topic ARN, dùng để định tuyến Publish và ràng buộc queue policy.
- **Endpoint** của subscription SQS là **queue ARN**, còn AWS CLI **receive-message** dùng **queue URL**; không tráo đổi hai giá trị.
- **AWS::SQS::QueuePolicy** cho phép SNS service gọi **sqs:SendMessage**, nhưng chỉ khi **aws:SourceArn** khớp topic cụ thể. Tránh dùng quyền gửi không giới hạn nguồn.
- **DependsOn** đảm bảo queue policy được tạo trước subscription, giảm rủi ro quan sát nhầm khi vừa triển khai xong.
- **RawMessageDelivery=true** khiến worker nhận body gốc dễ parse; đây là lựa chọn của từng subscription, không phải cấu hình của topic.
- **AnalyticsSubscription** không có FilterPolicy nên nhận mọi message. Một queue có thể nhận từ nhiều topic nếu được cấu hình, nhưng ví dụ này giữ một topic để tập trung giải thích fan-out.

IAM của ứng dụng Spring Boot **chỉ cần sns:Publish** lên topic. IAM của từng SQS worker cần **sqs:ReceiveMessage**, **sqs:DeleteMessage** và **sqs:GetQueueAttributes** trên queue được giao; pipeline IaC cần thêm quyền quản lý topic/queue/subscription. Không hardcode access key/secret key; dùng IAM role của workload, hoặc AWS profile trong môi trường phát triển. Queue dùng KMS key tự quản cần bổ sung KMS permissions/key policy phù hợp cho luồng SNS → SQS.

## 5. Gửi event từ Spring Boot

Spring Cloud AWS 3.x cung cấp **SnsTemplate**. Thêm starter SNS và BOM có phiên bản tương thích với Spring Boot:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Trong **application.yml**:

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

**ORDER_EVENTS_TOPIC_ARN** lấy từ CloudFormation Outputs. Trên AWS, ưu tiên IAM role; tại máy cá nhân sử dụng AWS credentials provider chain/profile đã cấu hình bên ngoài source.

Định nghĩa sự kiện:

~~~java
package demo.orders;

import java.time.Instant;

public record OrderEvent(
        String eventId,
        String eventType,
        String orderId,
        String riskLevel,
        Instant occurredAt
) {}
~~~

Publisher dùng Spring Messaging **Message**. Payload được tuần tự hóa thành JSON trước khi đưa vào SnsTemplate, còn **eventType** và **riskLevel** được gắn làm headers để chuyển thành message attributes:

~~~java
package demo.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventsPublisher {
    private final SnsTemplate snsTemplate;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventsPublisher(
            SnsTemplate snsTemplate,
            ObjectMapper objectMapper,
            @Value("${app.sns.topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public void publish(OrderEvent event) throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader("eventType", event.eventType())
                .setHeader("riskLevel", event.riskLevel())
                .build();

        snsTemplate.send(topicArn, message);
    }
}
~~~

Ví dụ gọi:

~~~java
publisher.publish(new OrderEvent(
        "evt-101", "ORDER_PAID", "ord-101",
        "HIGH", java.time.Instant.now()
));
~~~

Trong ví dụ đó, SNS sẽ chọn subscription fraud và analytics, không chọn email. Nếu gửi **ORDER_PAID** với **LOW**, chỉ analytics được chọn.

**Phân biệt hai loại dữ liệu:** body JSON chứa sự kiện nghiệp vụ; các SNS message attributes **eventType** và **riskLevel** được dùng cho subscription filter. **MessageHeaders.id** do Spring sinh không phải ID nghiệp vụ. Tạo **eventId** một lần khi phát sinh sự kiện, giữ nguyên khi retry, để consumer chống xử lý trùng.

Có thể dùng trực tiếp **SnsClient.publish** (AWS SDK v2) khi cần tạo **MessageAttributeValue** theo kiểu cụ thể như **Number** hoặc muốn lấy **PublishResponse.messageId**. **SnsTemplate.send** giúp thuận tiện hơn trong Spring nhưng kết quả gọi thành công chỉ nói rằng SNS đã chấp nhận publish; nó không bảo đảm tất cả worker đã xử lý xong.

## 6. Kiểm thử fan-out qua AWS CLI

Để kiểm chứng logic filter độc lập với Spring Boot, dùng AWS CLI phát thông điệp mẫu. Trong Bash, gán **TOPIC_ARN** bằng output thực tế của CloudFormation. Dưới đây là các lệnh phát event:

**ORDER_CREATED, LOW**:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-201","eventType":"ORDER_CREATED","orderId":"ord-201","riskLevel":"LOW"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"ORDER_CREATED"},"riskLevel":{"DataType":"String","StringValue":"LOW"}}' \
  --region ap-southeast-1
~~~

**ORDER_PAID, HIGH**:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-202","eventType":"ORDER_PAID","orderId":"ord-202","riskLevel":"HIGH"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"ORDER_PAID"},"riskLevel":{"DataType":"String","StringValue":"HIGH"}}' \
  --region ap-southeast-1
~~~

Đọc từng queue (thay queue URL theo Outputs của stack):

~~~bash
aws sqs receive-message \
  --queue-url "$EMAIL_QUEUE_URL" \
  --message-system-attribute-names All \
  --message-attribute-names All \
  --max-number-of-messages 10 \
  --wait-time-seconds 5 \
  --region ap-southeast-1
~~~

Đọc lại cấu hình của subscription bằng ARN trả về từ CloudFormation:

~~~bash
aws sns get-subscription-attributes \
  --subscription-arn "$FRAUD_SUBSCRIPTION_ARN" \
  --region ap-southeast-1
~~~

Trong output, kiểm tra **FilterPolicy**, **FilterPolicyScope**, **RawMessageDelivery**, **Endpoint**, **TopicArn**. Nếu thay filter mới, chờ đủ thời gian lan truyền trước khi đánh giá kết quả.

Để không nhầm lẫn trong test, dùng queue riêng và **eventId** duy nhất; đảm bảo không còn message của lượt test trước và không có consumer khác đang lấy message. SQS có ngữ nghĩa at-least-once, và một lần **receive-message** trả về rỗng không chứng minh queue chắc chắn không có message. Message được receive sẽ xuất hiện lại sau visibility timeout nếu chưa được **DeleteMessage**.

## 7. Raw message delivery và định dạng SQS body

**RawMessageDelivery=false:** SNS gửi một notification envelope tới SQS. Body của SQS sẽ chứa một đối tượng JSON gồm **Type**, **MessageId**, **TopicArn**, **Timestamp**, **Message** và những trường SNS khác. Ví dụ rút gọn:

~~~json
{
  "Type": "Notification",
  "TopicArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events-dev",
  "Message": "{\"eventId\":\"evt-201\",\"eventType\":\"ORDER_CREATED\"}"
}
~~~

**RawMessageDelivery=true:** SQS body chính là nội dung JSON gốc:

~~~json
{
  "eventId": "evt-201",
  "eventType": "ORDER_CREATED",
  "orderId": "ord-201",
  "riskLevel": "LOW"
}
~~~

Khi raw=true, những message attributes được hỗ trợ được chuyển thành SQS message attributes, còn envelope SNS không bao bọc body. **SNS → SQS với raw=true chỉ hỗ trợ tối đa 10 message attributes**; vượt giới hạn khiến thông điệp của subscription raw không được giao. Đừng sử dụng attributes như kho lưu metadata không giới hạn.

**Điều kiện filter không phụ thuộc việc bật raw delivery.** Filter lựa chọn *queue nào* nhận message; RawMessageDelivery xác định *consumer đọc body theo dạng nào*. Khi bật/tắt raw, cần thay parser của worker và các assertion trong integration test.

## 8. Quyền, thử lại, DLQ và quan sát

Có ba vị trí cần phân biệt rõ:

| Vị trí | Điều gì có thể xảy ra? | Cách xử lý |
| --- | --- | --- |
| **Publisher → SNS** | Sai topic ARN/region, thiếu **sns:Publish**, timeout | Kiểm tra IAM, log, retry có backoff; dùng transactional outbox khi cần |
| **SNS → queue** | Queue policy không cho **sqs:SendMessage**, KMS sai hoặc endpoint lỗi | Kiểm tra subscription, SQS queue policy, SNS delivery metrics và subscription DLQ |
| **Queue → consumer** | Worker lỗi khi xử lý, visibility timeout hết, message được nhận lại | Idempotent worker, retry và **SQS consumer DLQ** |

**SNS subscription DLQ** là queue nhận message SNS không thể giao tới endpoint sau các lần thử lại theo cơ chế dịch vụ. **SQS DLQ của worker** là queue nhận message đã nằm trong queue chính nhưng consumer xử lý thất bại nhiều lần. Đây là hai giai đoạn khác nhau, không thay thế nhau.

Quan sát **SNS CloudWatch metrics** liên quan số message publish, message giao thành công/thất bại, message bị filter. Quan sát **SQS metrics** về số message khả kiến, message in-flight, tuổi message cũ nhất và DLQ. Ở worker, log **eventId**, thời gian xử lý, số lần thử và lỗi nghiệp vụ.

Đảm bảo dữ liệu nhạy cảm không được fan-out tới các subscriber không cần thiết. Chỉ cấp **quyền tối thiểu**, dùng mã hóa/KMS theo yêu cầu, lưu credentials bằng cơ chế AWS role hoặc secret manager phù hợp; không đính kèm token, mật khẩu vào message. SNS thông thường có giới hạn message **256 KiB** tính cả message attributes; dữ liệu lớn nên lưu vào storage và chỉ gửi định danh/đường dẫn có kiểm soát.

### Standard và FIFO

Bài mẫu dùng **SNS Standard → SQS Standard**: thông lượng cao, at-least-once và có thể nhận trùng/không đúng thứ tự. Nếu nghiệp vụ cần thứ tự theo **orderId**, cân nhắc **SNS FIFO topic** kết hợp **SQS FIFO queue**, đặt **MessageGroupId** và **MessageDeduplicationId** ổn định. Một SNS FIFO topic cũng có thể nối SQS Standard nếu consumer chịu được ngữ nghĩa Standard ở nhánh đó.

Không suy ra rằng FIFO loại bỏ nhu cầu idempotency ở tầng nghiệp vụ; worker vẫn phải chống tác động phụ khi nhận sự kiện lặp. SNS FIFO hỗ trợ tập protocol khác SNS Standard, nên không giả định có thể subscribe trực tiếp HTTP/S hoặc email vào FIFO topic.

## 9. Ma trận kiểm thử và chẩn đoán lỗi

Khi kiểm thử tích hợp với AWS sandbox hoặc trình giả lập SNS/SQS có hỗ trợ filter, kiểm tra các kết quả sau trong môi trường queue riêng:

| Test | Dữ liệu | Email | Fraud | Analytics |
| --- | --- | --- | --- | --- |
| A | ORDER_CREATED / LOW | 1 | 0 | 1 |
| B | ORDER_PAID / HIGH | 0 | 1 | 1 |
| C | ORDER_PAID / LOW | 0 | 0 | 1 |
| D | ORDER_CANCELLED / LOW | 0 | 0 | 1 |
| E | Thiếu eventType / HIGH | 0 | 0 | 1 |
| F | order_created (sai chữ hoa/thường) / LOW | 0 | 0 | 1 |

Trong bảng, **1** nghĩa là subscription phù hợp được chọn để giao event trong mô hình lý tưởng, **không phải bảo đảm mỗi worker chỉ nhận đúng một lần**. Dùng **eventId** xác định chính xác message của test, không dựa vào tổng số message chung.

Thử thêm các tình huống:

1. Thu hồi quyền SNS gửi vào queue email trong sandbox: Publish vẫn có thể thành công nhưng email queue không nhận được; kiểm tra SNS delivery failure/DLQ.
2. Đổi scope sang **MessageBody**, gửi body JSON có eventType nhưng không có attribute: kiểm tra so khớp theo body.
3. Chuyển **RawMessageDelivery** thành false: xác minh consumer giải mã SNS envelope trước khi đọc payload JSON.
4. Cho worker lỗi trước khi xóa message: kiểm tra retry, visibility timeout, idempotency và SQS DLQ.
5. Đổi FilterPolicy rồi kiểm thử khi cấu hình đã lan truyền; tránh kết luận sai do eventual consistency.

**Những lỗi cần chẩn đoán:**

- **Publish bị AccessDenied:** quyền IAM **sns:Publish**, topic ARN và KMS.
- **Publish thành công nhưng mọi queue trống:** topic/subscription sai, queue policies, KMS, metrics hoặc test đang đọc sai queue.
- **Chỉ một queue trống:** filter policy, FilterPolicyScope, attribute bị thiếu, sai case/kiểu hoặc filter chưa có hiệu lực đầy đủ.
- **Worker không parse được JSON:** RawMessageDelivery và parser không tương ứng.
- **Worker xử lý hai lần:** idempotency chưa đúng hoặc message được redeliver.
- **Consumer lỗi nhưng SNS không báo failed delivery:** SNS đã giao vào SQS thành công; cần xem log worker và SQS DLQ.

## 10. Bài tập và tài liệu tham khảo

**Bài tập:** tạo topic **order-events-dev** và ba queue theo CloudFormation ở mục 4; viết Spring Boot publisher phát bốn event trong bảng kiểm thử; tạo ba worker ghi log **eventId**. Sau đó đổi filter fraud sang **riskScore >= 80**, so sánh MessageAttributes/MessageBody, kiểm tra raw delivery và mô phỏng consumer fail để quan sát SQS DLQ.

**Tự trả lời:**

1. Tại sao cùng một message có thể xuất hiện ở analytics queue và email queue?
2. Trong filter có hai khóa, SNS áp dụng AND hay OR? Một khóa có hai giá trị thì sao?
3. Body chứa **eventType** nhưng scope là **MessageAttributes** và không có attribute tương ứng: message có khớp không?
4. Vì sao IAM của Spring Boot và resource policy của SQS đều cần được cấu hình?
5. SNS subscription DLQ khác SQS consumer DLQ ở thời điểm nào?
6. RawMessageDelivery thay đổi điều gì, và vì sao nó không thay thế FilterPolicy?
7. Vì sao cần idempotency dù đang dùng queue managed?

**Tài liệu AWS và Spring Cloud AWS:**

- [Amazon SNS — Message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html)
- [Amazon SNS — Subscription filter policies](https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html)
- [Amazon SNS — Filter policy scope](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering-scope.html)
- [Amazon SNS — Applying a filter policy](https://docs.aws.amazon.com/sns/latest/dg/message-filtering-apply.html)
- [Amazon SNS — Subscribe an SQS queue](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html)
- [Amazon SNS — Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [Amazon SNS — Dead-letter queues](https://docs.aws.amazon.com/sns/latest/dg/sns-dead-letter-queues.html)
- [CloudFormation — AWS::SNS::Subscription](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sns-subscription.html)
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html)

**Kết quả mong đợi:** bạn có thể triển khai và kiểm thử đường đi **Spring Boot → SNS topic → các subscription được lọc → nhiều SQS queue**, cấu hình quyền đúng ở cả publisher và queue, và quan sát thành công/thất bại của từng nhánh giao nhận.
