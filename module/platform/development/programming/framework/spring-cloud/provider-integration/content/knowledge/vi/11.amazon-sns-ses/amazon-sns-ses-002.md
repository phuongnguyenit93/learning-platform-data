# Phát thông báo bằng SnsTemplate và thuộc tính thông điệp

## 1. Bài toán thực tế

Một hệ thống bán hàng viết bằng Spring Boot phát sinh các sự kiện **ORDER_CREATED**, **ORDER_PAID** và **ORDER_CANCELLED**. Dịch vụ gửi email chỉ quan tâm **ORDER_CREATED**; dịch vụ hoàn tiền quan tâm **ORDER_CANCELLED**; dịch vụ phân tích cần nhận cả ba. Nếu publisher trực tiếp gọi từng dịch vụ, mỗi thay đổi về người nhận đều có thể kéo theo thay đổi mã nguồn.

**Amazon Simple Notification Service (SNS)** giải quyết bài toán phân phối bằng **topic** và **subscription**. Ứng dụng gửi một thông điệp tới topic; SNS đối chiếu chính sách của từng subscription rồi chuyển tới endpoint phù hợp. Với Spring Boot, **Spring Cloud AWS SnsTemplate** cung cấp API theo phong cách Spring Messaging để publish payload và gắn **message attributes**.

Bài học nằm trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành kết nối Spring Boot với dịch vụ managed của AWS, áp dụng cách cấu hình danh tính, quyền truy cập, messaging, bảo vệ secret và kiểm thử tích hợp. Từ ví dụ AWS, người học có thể so sánh các khái niệm pub/sub, routing metadata và quyền truy cập với giải pháp tương ứng trên Azure và Google Cloud. Trọng tâm ở đây là **phát thông báo bằng SnsTemplate và thuộc tính thông điệp** trong chương **Amazon SNS và SES**.

**Sau bài này, bạn cần làm được:**

1. Thêm starter SNS và cấu hình topic ARN, region, danh tính AWS cho ứng dụng Spring Boot.
2. Sử dụng **SnsTemplate** để gửi chuỗi, đối tượng JSON và Spring Messaging **Message**.
3. Gắn **message attributes** đúng kiểu và tạo **subscription filter policy** tương ứng.
4. Giải thích khác biệt giữa payload, message attributes, Spring headers và SNS metadata.
5. Kiểm thử tuyến phát hành, xử lý lỗi và xác định khi nào cần chuyển xuống **SnsClient**.

## 2. Vị trí của SnsTemplate trong kiến trúc

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Publisher"] -->|"SnsTemplate.send"| T(("SNS topic<br/>order-events"))
    T -->|"Filter: ORDER_CREATED"| Q["SQS queue<br/>email-jobs"]
    T -->|"Filter: ORDER_CANCELLED"| R["SQS queue<br/>refund-jobs"]
    T -->|"Không filter"| L["Lambda<br/>analytics"]
    Q --> W["Email worker"]
    W --> SES["Amazon SES"]
~~~

Luồng thực thi cần phân biệt:

- **Publisher:** sử dụng **SnsTemplate** để gửi payload và thông tin định tuyến.
- **Topic:** địa chỉ logic được xác định bằng ARN, ví dụ **arn:aws:sns:ap-southeast-1:123456789012:order-events**.
- **Subscription:** kết nối một topic với một endpoint; có thể kèm chính sách lọc.
- **Endpoint/consumer:** SQS, Lambda, HTTP/S hoặc giao thức SNS hỗ trợ. Consumer phụ trách thực thi nghiệp vụ, retry và xử lý lặp.
- **SES:** dịch vụ gửi email giao dịch. Nếu cần gửi email có nội dung cho khách hàng, worker có thể gọi SES sau khi nhận sự kiện qua SNS/SQS.

**SnsTemplate** không phải hàng đợi lưu trữ thông điệp và không phải email sender. Nó là một lớp API Java giúp ứng dụng gọi **SNS Publish** qua AWS SDK. Publish được SNS chấp nhận **không đồng nghĩa** tất cả subscriber đã xử lý xong.

### 2.1. Chọn SnsTemplate hay SnsClient?

| Nhu cầu | Cách dùng |
| --- | --- |
| Gửi nhanh chuỗi hoặc POJO qua API Spring | **SnsTemplate.sendNotification** |
| Gửi payload kèm thuộc tính định tuyến | **SnsTemplate.send** với Spring **Message**, hoặc **convertAndSend** với map headers |
| Gửi theo nhóm và deduplication trên FIFO topic | **SnsTemplate.sendNotification** với **SnsNotification** hoặc giao diện **SnsOperations** |
| Cần **PublishResponse.messageId**, cấu hình chi tiết từng PublishRequest | **SnsClient.publish** từ AWS SDK v2 |
| Cần gửi SMS chuyên biệt | **SnsSmsTemplate** của Spring Cloud AWS, tùy yêu cầu |

Bài viết dùng API của **Spring Cloud AWS 3.x** (package **io.awspring.cloud**) cùng **AWS SDK for Java v2**. API của Spring Cloud AWS 2.x khác; lựa chọn BOM phải phù hợp phiên bản Spring Boot của dự án.

## 3. Cấu hình Spring Boot

### 3.1. Thêm starter và BOM

Trong **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

**springCloudAwsVersion** là biến phiên bản do bản build cung cấp, được chọn theo ma trận tương thích của Spring Cloud AWS/Spring Boot. Nếu dùng Maven, nhập BOM **spring-cloud-aws-dependencies** trong **dependencyManagement**, sau đó thêm **spring-cloud-aws-starter-sns**.

Starter thường tự cấu hình các bean **SnsClient** và **SnsTemplate**. Không cần tự tạo hai bean này nếu cấu hình mặc định đáp ứng nhu cầu.

### 3.2. Region và topic ARN

Trong **application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}

app:
  messaging:
    sns:
      order-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

Ở runtime, ví dụ:

~~~text
AWS_REGION=ap-southeast-1
ORDER_EVENTS_TOPIC_ARN=arn:aws:sns:ap-southeast-1:123456789012:order-events
~~~

**Nên dùng ARN đầy đủ** được provision bởi Terraform, CloudFormation, CDK hoặc quy trình quản lý hạ tầng. SnsTemplate có thể nhận tên topic để resolver xác định ARN; một số cấu hình resolver có thể thử tạo topic nếu topic chưa tồn tại. Dùng ARN rõ ràng giúp tránh phụ thuộc hành vi tự tạo topic và chỉ cần quyền publish.

### 3.3. Danh tính và IAM

AWS SDK sử dụng **credentials provider chain**; trong AWS, ưu tiên **IAM role** gắn với workload (ECS task role, EKS workload identity hoặc EC2 instance profile). Trên máy phát triển có thể dùng profile CLI; không hardcode access key và secret key trong source hoặc YAML.

Policy tối thiểu cho vai trò **publisher**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
    }
  ]
}
~~~

Policy này chỉ phục vụ publish tới topic cụ thể. Quyền **sns:CreateTopic**, **sns:Subscribe**, **sns:SetSubscriptionAttributes** và cấu hình policy của SQS thường cấp cho quy trình quản lý hạ tầng. Nếu topic có mã hóa bằng KMS key do khách hàng quản lý, cần kiểm tra thêm key policy/IAM permission tương ứng.

## 4. Ba cách phát thông báo bằng SnsTemplate

### 4.1. Gửi String và POJO

SnsTemplate hỗ trợ gửi chuỗi và chuyển đối tượng Java thành JSON bằng message converter được cấu hình.

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SimpleSnsPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public SimpleSnsPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.messaging.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void publishText() {
        snsTemplate.sendNotification(
                topicArn,
                "Order service started",
                "Order service"
        );
    }

    public void publishObject() {
        snsTemplate.sendNotification(
                topicArn,
                new OrderStatus("ord-1001", "ORDER_CREATED"),
                "Order created"
        );
    }

    public record OrderStatus(String orderId, String eventType) {}
}
~~~

**sendNotification(destination, message, subject)** phát thông điệp và đặt **subject** của SNS khi endpoint/protocol hỗ trợ. Đây là lời gọi đồng bộ tới SDK, nhưng phương thức không trả về trạng thái xử lý của từng subscriber.

**Object → JSON** chỉ hoạt động đúng khi message converter phù hợp đã sẵn sàng. Trong Spring Boot có Jackson, starter có thể cấu hình **MappingJackson2MessageConverter**; nếu tự cấu hình converter, cần bảo đảm consumer hiểu cách payload được tuần tự hóa.

### 4.2. Gửi Spring Message với headers

**Spring Messaging Message** chứa **payload** và **headers**. Khi gửi qua SnsTemplate, các header do ứng dụng gắn, nếu được hỗ trợ, được chuyển thành **SNS message attributes**. Những header đặc biệt dành riêng cho SNS như subject, group ID, deduplication ID được chuyển vào tham số tương ứng của request.

Tạo một kiểu sự kiện rõ ràng:

~~~java
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String eventType,
        String orderId,
        String tenantId,
        int schemaVersion,
        Instant occurredAt
) {}
~~~

Publisher:

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final SnsTemplate snsTemplate;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventPublisher(
            SnsTemplate snsTemplate,
            ObjectMapper objectMapper,
            @Value("${app.messaging.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public void publish(OrderEvent event) throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader("eventType", event.eventType())
                .setHeader("tenantId", event.tenantId())
                .setHeader("schemaVersion", String.valueOf(event.schemaVersion()))
                .build();

        snsTemplate.send(topicArn, message);
    }
}
~~~

Trong trường hợp này, ví dụ **send** chủ động serialize POJO thành JSON String để nội dung gửi tới SNS có định dạng dự đoán được. Cách **convertAndSend** ở mục 4.3 thực hiện chuyển đổi payload bằng message converter.

- **Payload** của Spring Message là chuỗi JSON được serialize từ **OrderEvent**, đi vào SNS **Message**.
- Header **eventType=ORDER_CREATED** dùng cho subscription filter.
- Header **tenantId=tenant-42** giúp tách tuyến sự kiện theo tenant nếu thiết kế yêu cầu.
- Header **schemaVersion=1** hỗ trợ consumer xác định version hợp đồng sự kiện.
- **eventId** được tạo **trước** khi publish và giữ nguyên khi retry cùng một sự kiện; consumer có thể sử dụng nó để chống xử lý trùng.

Ví dụ nơi gọi publisher:

~~~java
OrderEvent event = new OrderEvent(
        "evt-2026-0001",
        "ORDER_CREATED",
        "ord-1001",
        "tenant-42",
        1,
        java.time.Instant.now()
);

orderEventPublisher.publish(event);
~~~

**Lưu ý:** Spring **MessageHeaders.id** và **timestamp** được Spring sinh tự động không nên xem là định danh nghiệp vụ ổn định; sử dụng **eventId** riêng trong payload khi cần truy vết xuyên dịch vụ và idempotency.

### 4.3. Dùng convertAndSend với map headers

Khi đã có một đối tượng Java và danh sách attributes, có thể viết gọn:

~~~java
snsTemplate.convertAndSend(
        topicArn,
        event,
        java.util.Map.of(
                "eventType", event.eventType(),
                "tenantId", event.tenantId(),
                "schemaVersion", String.valueOf(event.schemaVersion())
        )
);
~~~

So với ví dụ **MessageBuilder**, cách này giữ cùng ý tưởng: truyền **payload** riêng và **headers** riêng. Không nhét dữ liệu định tuyến vào tên topic hay dựng thêm một topic cho từng loại sự kiện khi chỉ cần filter.

## 5. Phân biệt payload và message attributes

Một bản tin gửi đi có thể hình dung như sau:

~~~json
{
  "Message": "{\"eventId\":\"evt-2026-0001\",\"eventType\":\"ORDER_CREATED\",\"orderId\":\"ord-1001\",\"tenantId\":\"tenant-42\",\"schemaVersion\":1,\"occurredAt\":\"2026-11-24T08:00:00Z\"}",
  "MessageAttributes": {
    "eventType": {
      "DataType": "String",
      "StringValue": "ORDER_CREATED"
    },
    "tenantId": {
      "DataType": "String",
      "StringValue": "tenant-42"
    },
    "schemaVersion": {
      "DataType": "String",
      "StringValue": "1"
    }
  }
}
~~~

Đây là **mô tả khái niệm của các trường gửi tới Publish API**, không phải JSON nguyên văn mà SnsTemplate tạo ra hoặc định dạng body mà mọi subscriber nhận được. Trong API SNS, mỗi attribute có **DataType** và giá trị tương ứng; khi SNS gửi sang SQS theo chế độ thông thường, message thường nằm trong envelope riêng.

| Thành phần | Dùng cho | Quy tắc thiết kế |
| --- | --- | --- |
| **Message body** | Nội dung nghiệp vụ đầy đủ, ví dụ ID đơn, thời điểm, phiên bản schema | Chứa dữ liệu consumer cần để xử lý; có version khi schema tiến hóa |
| **Message attributes** | Metadata nhỏ giúp routing/filter, phân loại và xử lý | Tên ổn định, kiểu rõ ràng; tránh dữ liệu nhạy cảm |
| **SNS Subject** | Tiêu đề thông báo cho endpoint phù hợp | Không thay thế event type và không phải tất cả protocol đều dùng |
| **SNS MessageId** | ID SNS cấp sau khi chấp nhận publish | Không đồng nhất với **eventId** nghiệp vụ hoặc xác nhận tiêu thụ thành công |
| **Spring MessageHeaders** | Metadata khi đi qua Spring Messaging | Một số header dành riêng cho framework; chỉ chọn header cần truyền sang SNS |

### 5.1. Kiểu dữ liệu và giới hạn cơ bản

SNS hỗ trợ attribute **String**, **Number**, **String.Array** và **Binary**. Mỗi attribute có tên, kiểu và giá trị không rỗng; tên phân biệt chữ hoa/chữ thường. Một số prefix như **AWS.** và **Amazon.** được dành riêng, không nên sử dụng làm tên custom attribute.

- **String:** phù hợp eventType, tenantId, schemaVersion biểu diễn như chuỗi. Đây là lựa chọn ổn định cho filter exact-match.
- **Number:** phù hợp dữ liệu số cần so sánh định lượng; phải khớp kỳ vọng của filter.
- **String.Array:** hỗ trợ nhiều giá trị trong một attribute; nội dung được biểu diễn theo cú pháp array hợp lệ.
- **Binary:** dùng khi thực sự cần binary metadata; không dùng làm khóa lọc theo SNS filter policy.

**Message attributes được tính vào giới hạn kích thước message của SNS.** Mặc định payload cho thông điệp SNS thường giới hạn ở **256 KiB**, bao gồm dữ liệu attribute. Không đính kèm toàn bộ tài liệu lớn, bí mật hoặc thông tin nhạy cảm nếu consumer chỉ cần một object ID.

**Chú ý với SQS:** nếu subscription bật **Raw Message Delivery**, SNS chỉ hỗ trợ tối đa **10 message attributes** trên một message gửi tới SQS subscription đó. Nếu cần nhiều hơn, phải cân nhắc tắt raw delivery hoặc thu gọn attributes.

## 6. Dùng attributes để lọc subscription

Thay vì code publisher có ba câu lệnh publish tới ba topic, hãy publish tới **một topic**, rồi để các subscription quyết định thông điệp nào cần nhận.

### 6.1. Ví dụ chính sách lọc

Giả sử service gửi thông điệp:

~~~text
Message attributes:
  eventType     = ORDER_CREATED
  tenantId      = tenant-42
  schemaVersion = 1
~~~

Đặt **FilterPolicyScope=MessageAttributes** (giá trị mặc định) cho subscription tới **email-jobs**:

~~~json
{
  "eventType": ["ORDER_CREATED"],
  "tenantId": ["tenant-42"]
}
~~~

SNS áp dụng **AND giữa các khóa** (cần khớp **eventType** *và* **tenantId**) và **OR giữa các giá trị** của cùng một khóa. Các thuộc tính không được nhắc trong filter, như **schemaVersion**, không ảnh hưởng tới kết quả.

Ví dụ có ba subscription:

| Subscription | FilterPolicy | Với ORDER_CREATED/tenant-42 |
| --- | --- | --- |
| **email-jobs** | eventType = ORDER_CREATED; tenantId = tenant-42 | **Được nhận** |
| **refund-jobs** | eventType = ORDER_CANCELLED | **Không được nhận** |
| **analytics** | Không có filter | **Được nhận** |

Đặt chính sách bằng AWS CLI (thay ARN thực tế và bảo đảm subscription đã tồn tại):

~~~bash
aws sns set-subscription-attributes --subscription-arn "arn:aws:sns:ap-southeast-1:123456789012:order-events:subscription-id" --attribute-name FilterPolicyScope --attribute-value MessageAttributes
aws sns set-subscription-attributes --subscription-arn "arn:aws:sns:ap-southeast-1:123456789012:order-events:subscription-id" --attribute-name FilterPolicy --attribute-value '{"eventType":["ORDER_CREATED"],"tenantId":["tenant-42"]}'
~~~

Cú pháp nháy đơn trong ví dụ CLI phù hợp với shell kiểu Bash; với PowerShell, cần truyền JSON theo quy tắc trích dẫn của shell hoặc dùng file JSON để tránh lỗi escaping.

Trong sản xuất, nên đặt subscription và filter trong hạ tầng dạng mã (IaC), đồng thời triển khai cùng quyền cho endpoint.

### 6.2. Vì sao thông điệp bị lọc sai?

- **Thiếu header:** publisher không gửi **eventType** nhưng subscription yêu cầu trường này.
- **Sai chữ hoa/thường:** **ORDER_CREATED** khác **order_created**.
- **Sai kiểu:** filter số và attribute chuỗi không nhất thiết khớp, dù cùng hiển thị là “1”.
- **Sai scope:** filter dựa trên attributes nhưng subscription dùng **MessageBody**, hoặc ngược lại.
- **Sai JSON:** thiếu dấu ngoặc vuông cho danh sách giá trị, cấu trúc không hợp lệ.
- **Thay đổi cấu hình chưa lan truyền:** filter policy có thể mất thời gian để đồng bộ; không nên giả định hiệu lực tức thời.

Khi **FilterPolicyScope=MessageBody**, SNS đánh giá các trường trong payload JSON thay vì message attributes; cách này hữu ích khi nguồn phát không thể tùy biến metadata. Với luồng publisher Spring Boot tự quản lý, sử dụng **message attributes** rõ ràng thường dễ kiểm thử hơn.

## 7. Những lưu ý khi gửi sang SQS

SNS topic cần có subscription trỏ tới queue; điều kiện filter chỉ là một phần của việc phân phối. **Queue resource policy** phải cho phép topic thực hiện **sqs:SendMessage**, thường giới hạn bằng **aws:SourceArn** để chỉ topic được chỉ định có quyền gửi.

Ví dụ phần statement cho queue **email-jobs**:

~~~json
{
  "Sid": "AllowOrderEventsSns",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:email-jobs",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
    }
  }
}
~~~

Statement này thuộc **SQS queue policy** và cần nằm trong policy hợp lệ đã áp dụng trên queue. Một publisher có quyền **sns:Publish** không thể tự động cấp SNS quyền gửi vào SQS; hai mặt quyền được cấu hình độc lập.

**RawMessageDelivery=false** (thường là mặc định): SQS body chứa SNS notification envelope, trong đó trường **Message** giữ nội dung publisher phát đi và **MessageAttributes** được biểu diễn trong envelope. Consumer phải giải mã lớp envelope trước khi đọc event JSON.

**RawMessageDelivery=true:** SQS body trực tiếp là payload của publisher; message attributes chuyển thành thuộc tính SQS tương ứng trong giới hạn hỗ trợ. Consumer đọc theo cấu hình này sẽ đơn giản hơn khi payload là JSON nghiệp vụ, nhưng không còn đầy đủ SNS envelope trong body.

Không thể giả định rằng mọi consumer đều sẽ nhận cùng một cấu trúc JSON: Lambda, SQS, HTTP/S và email có định dạng giao nhận khác nhau.

## 8. Gửi lên SNS FIFO bằng SnsTemplate

Nếu thứ tự các sự kiện trong cùng một đơn hàng là yêu cầu nghiệp vụ, xem xét topic **.fifo** cùng endpoint và cấu hình hỗ trợ FIFO. Với Spring Cloud AWS 3.x, **SnsNotification** cho phép đặt **groupId** và **deduplicationId**:

~~~java
import io.awspring.cloud.sns.core.SnsNotification;
import io.awspring.cloud.sns.core.SnsTemplate;

public void publishOrderedEvent(
        SnsTemplate snsTemplate,
        String fifoTopicArn,
        OrderEvent event) {

    SnsNotification<OrderEvent> notification =
            SnsNotification.builder(event)
                    .groupId(event.orderId())
                    .deduplicationId(event.eventId())
                    .header("eventType", event.eventType())
                    .header("tenantId", event.tenantId())
                    .build();

    snsTemplate.sendNotification(fifoTopicArn, notification);
}
~~~

- **MessageGroupId:** nhóm cần được xử lý theo thứ tự, ví dụ các sự kiện cùng **orderId**.
- **MessageDeduplicationId:** nhận diện thông điệp trùng trong cửa sổ deduplication có giới hạn. Sử dụng **eventId** ổn định giữa các lần retry của cùng một sự kiện.
- **Header eventType/tenantId:** vẫn phục vụ filter policy theo message attributes.

FIFO không thay thế thiết kế **idempotent consumer**. Thứ tự và cơ chế deduplication chỉ áp dụng theo điều kiện và loại subscription/endpoint được hỗ trợ; bản thân nghiệp vụ vẫn có thể bị gọi lại sau lỗi xử lý hoặc retry ở tầng khác.

## 9. Xử lý lỗi và bảo đảm tính nhất quán

### 9.1. Đừng đánh đồng ba trạng thái

1. **Publisher gọi SnsTemplate thành công:** yêu cầu Publish đã được SNS tiếp nhận.
2. **SNS phân phối thành công:** một endpoint/subscription nhận được thông điệp.
3. **Consumer xử lý thành công:** tác động nghiệp vụ, chẳng hạn ghi DB hoặc gửi email bằng SES, đã hoàn tất.

**send**, **convertAndSend**, **sendNotification** của SnsTemplate không cung cấp danh sách subscriber đã xử lý. Nếu cần **SNS MessageId** của PublishResponse ngay trong ứng dụng phát, dùng **SnsClient.publish** thay vì giả định API void của SnsTemplate có response đó.

### 9.2. Các lỗi thường gặp

| Hiện tượng | Kiểm tra |
| --- | --- |
| **AccessDeniedException** khi publish | IAM role có **sns:Publish** trên đúng ARN? Có thiếu quyền KMS? |
| **NotFound** hoặc sai topic | ARN, account, region có khớp môi trường chạy? |
| Publish thành công nhưng SQS trống | Subscription đã xác nhận/chính xác? Queue policy có **sqs:SendMessage**? Filter có khớp attributes? |
| Consumer nhận body không đúng dạng | **RawMessageDelivery** và parser của consumer có nhất quán? |
| Có xử lý lặp | Consumer đã dùng **eventId** để chống xử lý trùng? |
| FIFO bị từ chối | Topic có đuôi **.fifo**, groupId/deduplicationId đúng và đích hỗ trợ FIFO? |

Nếu việc ghi đơn hàng vào DB và publish SNS là hai thao tác tách biệt, có thể xảy ra tình huống DB commit xong nhưng SNS Publish thất bại. Với nghiệp vụ cần độ tin cậy cao, xem xét **transactional outbox**: ghi event vào bảng outbox trong cùng giao dịch DB, rồi worker phát lại một cách idempotent.

Đối với những lỗi tạm thời, áp dụng retry có backoff và giới hạn, theo dõi CloudWatch metrics/logs và dead-letter queue (DLQ) tại điểm phù hợp. Cần phân biệt **SNS subscription DLQ** (SNS không giao được message tới endpoint) với **SQS DLQ** (consumer không xử lý được message đã nằm trong queue).

## 10. Kiểm thử ứng dụng

### 10.1. Unit test ở publisher

Dùng Mockito giả lập **SnsTemplate**, gọi phương thức publish, bắt tham số của **snsTemplate.send** và kiểm tra:

- Destination bằng đúng topic ARN cấu hình.
- Payload có **eventId**, **eventType**, **orderId** và **schemaVersion** mong đợi.
- Header **eventType**, **tenantId** có giá trị chính xác.
- Khi lỗi SDK được trả về, ứng dụng phản ứng theo chiến lược xử lý lỗi đã định, không lặng lẽ coi publish thành công.

Ví dụ assertion cho một Spring Message đã được bắt từ mock:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals("ORDER_CREATED", capturedMessage.getHeaders().get("eventType"));
assertEquals("tenant-42", capturedMessage.getHeaders().get("tenantId"));
var json = new ObjectMapper().readTree((String) capturedMessage.getPayload());
assertEquals("ORDER_CREATED", json.path("eventType").asText());
~~~

Đây là mảnh kiểm tra minh họa trong một phương thức test khai báo **throws Exception**; **capturedMessage** là đối tượng thu được qua **ArgumentCaptor** trong unit test. Không cần gọi AWS thật cho unit test.

### 10.2. Integration test với SNS và SQS

Có thể dùng môi trường AWS sandbox hoặc LocalStack để thử đường đi tích hợp (đánh giá mức hỗ trợ tính năng của trình giả lập trước khi dùng làm tiêu chuẩn production):

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Provision SNS Standard topic, hai queue và subscription + queue policies | Cả hai queue có quyền nhận từ SNS |
| 2 | Gắn filter **ORDER_CREATED** cho queue A, **ORDER_CANCELLED** cho queue B | Hai tuyến nhận khác nhau |
| 3 | Publisher gửi **ORDER_CREATED** với header **eventType** | Queue A nhận, queue B không nhận |
| 4 | Publisher gửi **ORDER_CANCELLED** | Queue B nhận, queue A không nhận |
| 5 | Publisher bỏ header **eventType** | Message không thỏa filter yêu cầu trường này |
| 6 | Thử hai chế độ RawMessageDelivery | Consumer giải mã đúng envelope hoặc payload gốc |
| 7 | Publish lặp cùng **eventId** | Consumer idempotent không gây tác động nghiệp vụ hai lần |
| 8 | Thu hồi quyền SNS→SQS trong môi trường test | Ghi nhận lỗi phân phối và theo dõi chỉ số/DLQ đúng cấu hình |

Khi vừa thay đổi filter, kết quả tích hợp có thể tạm thời không đồng nhất do thời gian lan truyền policy. Chờ policy ổn định rồi mới đánh giá kết quả phân phối, tránh flakiness.

## 11. Bài tập thực hành

**Yêu cầu:** Xây một Spring Boot service có phương thức **publishOrderEvent(OrderEvent event)** sử dụng **SnsTemplate**. Mỗi event cần **eventId**, **eventType**, **orderId**, **tenantId**, **schemaVersion** và **occurredAt**. Gắn ít nhất **eventType**, **tenantId** làm message attributes.

1. Tạo một SNS topic **order-events** và hai queue **order-created-jobs**, **order-cancelled-jobs**.
2. Tạo subscription, queue policy và FilterPolicy tương ứng.
3. Gửi hai loại sự kiện và đối chiếu message đến queue.
4. Thử bỏ **eventType** khỏi headers, đổi chữ hoa/chữ thường hoặc dùng sai scope để quan sát kết quả lọc.
5. Bật/tắt **RawMessageDelivery**, điều chỉnh parser của consumer cho đúng.
6. Ghi nhận tác động của retry và triển khai idempotency bằng **eventId**.
7. *Nâng cao:* đổi pipeline sang SNS FIFO + SQS FIFO, đặt **groupId** bằng **orderId**.

**Tự kiểm tra kiến thức:**

- SnsTemplate khác SnsClient ở tầng trừu tượng nào?
- Vì sao **eventType** nên có trong attributes dù payload JSON đã chứa trường này?
- Message thuộc subscription A được nhận nhưng B không nhận là hành vi gì trong thiết kế pub/sub?
- Thiếu **sns:Publish** và thiếu **sqs:SendMessage** khác nhau ở điểm nào?
- Vì sao publisher không thể dựa vào thành công của phương thức **sendNotification** để khẳng định email đã được gửi bằng SES?
- Tình huống nào nên dùng **MessageBody** filter thay cho **MessageAttributes**?

## 12. Tài liệu tham khảo

- [Spring Cloud AWS 3.3.1 — SNS Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#sns-integration): starter, SnsTemplate, SnsOperations và cách publish.
- [Spring Cloud AWS 3.3.1 — SnsTemplate API](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/apidocs/io/awspring/cloud/sns/core/SnsTemplate.html): các phương thức send, convertAndSend và sendNotification.
- [Amazon SNS — Message attributes](https://docs.aws.amazon.com/sns/latest/dg/sns-message-attributes.html): kiểu dữ liệu, cách dùng, giới hạn và raw delivery.
- [Amazon SNS — Subscription filter policies](https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html): filter theo message attributes hoặc message body.
- [AWS IAM — Chính sách truy cập SNS](https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-use-cases.html): quyền truy cập topic và nguyên tắc resource policy.

**Kết quả cuối bài:** Có thể phát sự kiện từ Spring Boot qua **SnsTemplate**, tách payload khỏi **message attributes**, cấu hình subscription để phân phối có điều kiện và kiểm chứng cả quyền truy cập lẫn đường đi thực tế của thông điệp.
