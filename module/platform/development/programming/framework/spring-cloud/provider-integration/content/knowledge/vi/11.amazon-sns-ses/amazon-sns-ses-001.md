# Topic, subscription và mô hình phân phối thông báo SNS

## 1. Bài toán và mục tiêu học tập

Giả sử ứng dụng Spring Boot vừa ghi nhận một đơn hàng. Cùng sự kiện **ORDER_CREATED**, hệ thống cần gửi email xác nhận, cập nhật thống kê và khởi chạy quy trình xử lý đơn. Nếu dịch vụ đơn hàng gọi trực tiếp cả ba hệ thống, nó phải biết từng địa chỉ nhận, cách gọi, chính sách thử lại và tình trạng của các dịch vụ phụ thuộc.

**Amazon Simple Notification Service (SNS)** cho phép ứng dụng phát hành một thông điệp tới **topic**, sau đó SNS chuyển thông điệp tới các **subscription** đủ điều kiện. Đây là mô hình **publish/subscribe (pub/sub)** và thường được sử dụng để **fan-out**: một sự kiện được phân phối tới nhiều nhánh xử lý độc lập.

Sau bài học, người học có thể:

- Phân biệt **publisher**, **topic**, **subscription**, **endpoint** và thông điệp được phân phối.
- Thiết kế luồng fan-out từ Spring Boot đến SQS, Lambda hoặc HTTP/S; hiểu vai trò của subscription filter.
- Phân biệt **SNS Standard** và **SNS FIFO**, bao gồm thứ tự, bản sao thông điệp và cơ chế chống xử lý trùng.
- Cấu hình quyền, gửi sự kiện bằng Spring Cloud AWS và quan sát lỗi phân phối.
- Biết khi nào sử dụng SNS, SQS và SES trong bài toán tích hợp dịch vụ managed của AWS.

Trong phạm vi module **SPRING_CLOUD_PROVIDER_INTEGRATION**, trọng tâm là cách Spring Boot dùng danh tính và quyền AWS để phát hành sự kiện, tích hợp dịch vụ messaging và kiểm thử hành vi phân phối. Những nguyên tắc về tách cấu hình, quyền tối thiểu, quản lý secret và kiểm thử tích hợp có thể áp dụng khi so sánh với các dịch vụ managed tương ứng trên Azure và Google Cloud.

## 2. Các thành phần cốt lõi

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Publisher** | Ứng dụng gọi API **Publish** để gửi thông điệp | Dịch vụ đơn hàng viết bằng Spring Boot |
| **Topic** | Kênh logic tiếp nhận sự kiện và phân phối cho các subscription | **order-events** |
| **Subscription** | Quan hệ đăng ký giữa một topic với một endpoint, kèm thuộc tính lọc và phân phối | Topic **order-events** → hàng đợi **order-email-jobs** |
| **Endpoint** | Đích thực tế nhận thông điệp | SQS queue, AWS Lambda, HTTPS endpoint, email |
| **Message** | Nội dung thông điệp (*body*) và các thuộc tính (*message attributes*) tùy chọn | JSON đơn hàng + **eventType=ORDER_CREATED** |

Topic được xác định bằng **ARN (Amazon Resource Name)**. Ví dụ:

~~~text
arn:aws:sns:ap-southeast-1:123456789012:order-events
~~~

Một topic có thể có nhiều subscription; một endpoint cũng có thể nhận thông điệp từ nhiều topic nếu được cấu hình phù hợp. Khi publisher gọi **Publish** thành công, kết quả trả về có **MessageId** của SNS. **MessageId không xác nhận rằng mọi subscriber đã xử lý thành công**; việc phân phối và xử lý diễn ra sau đó.

### 2.1. Luồng fan-out minh họa

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Order Service"] -->|"Publish ORDER_CREATED"| T(("SNS topic<br/>order-events"))
    T -->|"Subscription A<br/>lọc ORDER_CREATED"| Q["SQS queue<br/>order-email-jobs"]
    T -->|"Subscription B<br/>lọc ORDER_CREATED"| L["AWS Lambda<br/>analytics-handler"]
    T -->|"Subscription C"| H["HTTPS webhook"]
    Q -->|"Poll + xử lý"| W["Spring Boot<br/>Email Worker"]
~~~

Theo sơ đồ, SNS **đẩy** thông báo đến các đích đã đăng ký; riêng worker đọc SQS bằng cách **poll/pull** từ queue. Việc dùng SQS ở giữa giúp giữ thông điệp khi worker tạm ngừng hoạt động và cho phép worker kiểm soát tốc độ xử lý. SNS là tầng định tuyến/phân phối; SQS là tầng lưu đệm và tiêu thụ bất đồng bộ.

Không phải mọi endpoint đều nhận cùng một định dạng. Ví dụ, với SQS và **RawMessageDelivery=false** (mặc định), phần thân SQS chứa một *SNS notification envelope* gồm các trường như **Type**, **MessageId**, **TopicArn**, **Timestamp**, **Message** và thông tin khác. Khi bật **RawMessageDelivery=true**, phần thân SQS là nội dung **Message** gốc của publisher. Consumer cần đọc đúng định dạng đã cấu hình.

## 3. Topic: Standard hay FIFO?

SNS có hai loại topic phục vụ các yêu cầu phân phối khác nhau:

| Tiêu chí | **Standard topic** | **FIFO topic** |
| --- | --- | --- |
| Mục tiêu | Thông lượng và phân phối linh hoạt | Giữ thứ tự trong từng nhóm thông điệp và giảm trùng lặp |
| Thứ tự | **Best effort**; có thể đến không đúng thứ tự phát hành | Giữ thứ tự theo **MessageGroupId** trong các điều kiện phân phối được hỗ trợ |
| Trùng lặp | Có thể nhận thông điệp lặp; thiết kế consumer **idempotent** | Có cơ chế deduplication bằng **MessageDeduplicationId** hoặc content-based deduplication trong cửa sổ giới hạn |
| Tên topic | Ví dụ **order-events** | Phải có hậu tố **.fifo**, ví dụ **order-events.fifo** |
| Chọn khi | Thông báo hoạt động, cập nhật chỉ số, tác vụ độc lập | Các sự kiện của cùng một thực thể cần được tiêu thụ tuần tự |

Với **FIFO**, producer gán **MessageGroupId**, chẳng hạn mã đơn hàng; các sự kiện cùng nhóm được sắp theo thứ tự. Cần thêm **MessageDeduplicationId** hoặc cấu hình content-based deduplication. Khả năng giao nhận theo thứ tự và chống lặp phụ thuộc loại endpoint và cấu hình liên quan (đặc biệt là queue FIFO khi tích hợp SNS–SQS). **Không diễn giải FIFO thành bảo đảm “mỗi thao tác nghiệp vụ chỉ chạy đúng một lần”**: consumer vẫn phải xử lý idempotent, kể cả trong các lần thử lại hoặc sau sự cố.

Ví dụ, nếu hệ thống chỉ cần gửi tín hiệu “đã có đơn mới” đến ba dịch vụ, Standard thường đủ. Nếu các sự kiện **ORDER_CREATED → ORDER_PAID → ORDER_CANCELLED** của cùng một đơn phải đến theo thứ tự và pipeline đích hỗ trợ FIFO, hãy xem xét SNS FIFO kết hợp SQS FIFO.

## 4. Subscription quyết định ai nhận thông điệp

Đăng ký một endpoint với topic tạo ra một **subscription**. Các protocol phổ biến gồm **sqs**, **lambda**, **https**, **email**, **sms**; việc hỗ trợ và chi tiết phân phối phụ thuộc loại topic và endpoint.

Một subscription có thể cần xác nhận hoặc cấp quyền bổ sung:

- **Email/HTTP(S):** endpoint thường phải xác nhận yêu cầu đăng ký (*subscription confirmation*) trước khi bắt đầu nhận thông báo; cần thiết kế bước xác nhận trong vận hành.
- **SQS:** hàng đợi phải có **resource policy** cho phép SNS topic cụ thể thực hiện **sqs:SendMessage**. Quyền IAM của publisher **sns:Publish** không tự động cấp quyền gửi vào queue.
- **Lambda:** cần quyền invoke thích hợp cho SNS trên Lambda function.

Một subscriber được gỡ bỏ sẽ không tiếp tục nhận thông điệp mới qua subscription đó. SNS cũng **không cung cấp cơ chế replay lịch sử topic** cho một subscription mới: cần dùng queue lưu giữ thông điệp, kho lưu trữ sự kiện hoặc thiết kế phát lại riêng nếu nghiệp vụ cần đọc lại sự kiện cũ.

### 4.1. Lọc theo thuộc tính thông điệp

Không nhất thiết mọi subscription đều nhận mọi sự kiện. Với **FilterPolicy**, một subscription có thể chỉ nhận thông điệp thỏa điều kiện. Ví dụ publisher gắn các thuộc tính:

~~~json
{
  "eventType": "ORDER_CREATED",
  "tenantId": "tenant-42"
}
~~~

Đây là các giá trị khái niệm của **message attributes**. Tại subscription A, đặt **FilterPolicyScope=MessageAttributes** (phạm vi mặc định) và chính sách:

~~~json
{
  "eventType": ["ORDER_CREATED"],
  "tenantId": ["tenant-42"]
}
~~~

Subscription này chỉ khớp nếu **cả hai** khóa đều thỏa điều kiện (AND giữa các khóa); các giá trị trong cùng danh sách được so khớp theo OR. Nếu publisher không gửi thuộc tính bắt buộc, thông điệp sẽ không khớp bộ lọc. Có thể dùng **FilterPolicyScope=MessageBody** để lọc trên các trường của phần thân JSON, nhưng lúc đó body phải phù hợp cấu trúc và chính sách lọc.

Giả sử có hai queue:

| Subscription | Bộ lọc | Điều gì được nhận? |
| --- | --- | --- |
| **order-email-jobs** | **eventType = ORDER_CREATED** | Tín hiệu gửi email xác nhận đơn |
| **order-cancel-jobs** | **eventType = ORDER_CANCELLED** | Tín hiệu xử lý hủy đơn |

Một sự kiện **ORDER_CREATED** đi qua topic, được SNS so khớp chính sách của **từng subscription**, sau đó chỉ gửi đến đích phù hợp. Việc thêm bộ lọc là thay đổi ở tầng phân phối; publisher không cần tự gọi lần lượt từng consumer.

**Lưu ý:** Thay đổi thuộc tính subscription và filter có thể cần thời gian để được áp dụng trên hệ thống phân tán. Trong thời gian chuyển tiếp, kiểm thử nên cho phép sai khác tạm thời thay vì giả định cấu hình có hiệu lực tức thì.

## 5. Tích hợp SNS với Spring Boot và Spring Cloud AWS

Trong ứng dụng Spring Boot, có thể dùng **Spring Cloud AWS** để cấu hình AWS client theo region và chuỗi cung cấp thông tin xác thực mặc định. Ví dụ sau dùng **SnsClient** của AWS SDK for Java v2 qua dependency AWSpring; cách này làm rõ lệnh **Publish** và các message attributes.

### 5.1. Khai báo dependency

Ví dụ **Gradle (Groovy DSL)**, với **springCloudAwsVersion** là phiên bản BOM được chọn **tương thích với phiên bản Spring Boot** của dự án:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Mẫu này sử dụng thế hệ **Spring Cloud AWS 3.x** với namespace **io.awspring.cloud** và AWS SDK v2. Nếu ứng dụng dùng thế hệ cũ, API, dependency và tên cấu hình có thể khác; cần chọn một bộ phiên bản nhất quán.

### 5.2. Cấu hình region và topic ARN

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}

app:
  sns:
    order-events-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

Ví dụ đặt **ORDER_EVENTS_TOPIC_ARN** trong biến môi trường của runtime. **Không đặt access key/secret key trong mã nguồn hoặc application.yml**. Ở môi trường AWS, ưu tiên IAM role của workload (chẳng hạn ECS task role hoặc EC2 instance role); ở máy phát triển có thể dùng AWS profile được quản lý ngoài dự án. Chuỗi xác thực mặc định sẽ tìm thông tin xác thực theo các nguồn được SDK hỗ trợ.

IAM policy tối thiểu cho publisher có thể giới hạn hành động **sns:Publish** vào đúng topic:

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

ARN và account ID ở đây chỉ là ví dụ. Quyền tạo topic, tạo subscription và sửa queue policy thường thuộc về cấu hình hạ tầng, không cần cấp cho ứng dụng chỉ làm publisher.

### 5.3. Phát hành sự kiện và thuộc tính lọc

~~~java
package example.notification;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import software.amazon.awssdk.services.sns.model.PublishRequest;

import java.util.Map;

@Service
public class OrderEventPublisher {
    private final SnsClient snsClient;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventPublisher(
            SnsClient snsClient,
            ObjectMapper objectMapper,
            @Value("${app.sns.order-events-topic-arn}") String topicArn) {
        this.snsClient = snsClient;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public String publishOrderCreated(String eventId, String orderId, String tenantId)
            throws JsonProcessingException {
        String body = objectMapper.writeValueAsString(Map.of(
                "eventId", eventId,
                "eventType", "ORDER_CREATED",
                "orderId", orderId,
                "tenantId", tenantId
        ));

        Map<String, MessageAttributeValue> attributes = Map.of(
                "eventType", MessageAttributeValue.builder()
                        .dataType("String")
                        .stringValue("ORDER_CREATED")
                        .build(),
                "tenantId", MessageAttributeValue.builder()
                        .dataType("String")
                        .stringValue(tenantId)
                        .build()
        );

        return snsClient.publish(PublishRequest.builder()
                .topicArn(topicArn)
                .message(body)
                .messageAttributes(attributes)
                .build()).messageId();
    }
}
~~~

**Điểm cần hiểu trong đoạn mã:**

1. **OrderEventPublisher** chỉ biết topic ARN, không biết danh sách subscriber.
2. **body** là JSON chứa dữ liệu sự kiện. **messageAttributes** là metadata để SNS có thể đánh giá subscription filter.
3. **eventId** là định danh sự kiện nghiệp vụ được tạo một lần và giữ nguyên qua các lần thử gửi lại; phía consumer có thể lưu/đối chiếu ID này để bỏ qua xử lý trùng. **MessageId** trả về từ SNS là định danh do SNS cấp khi chấp nhận publish.
4. Lời gọi **publish** có thể ném ngoại lệ do quyền, cấu hình, mạng hoặc giới hạn dịch vụ; ứng dụng cần quyết định chiến lược retry phù hợp. Nếu sự kiện phải gắn chặt với giao dịch cập nhật database, cân nhắc **transactional outbox** để tránh tình trạng ghi dữ liệu thành công nhưng phát hành sự kiện thất bại.

Một số giải pháp Spring Cloud AWS cũng cung cấp **SnsTemplate** để đơn giản hóa thao tác publish; dùng **SnsClient** ở đây nhằm minh họa rõ API SNS và bộ lọc theo attributes.

## 6. Tạo topic và subscription SNS → SQS

Ví dụ minh họa sử dụng **AWS CLI**. Trước tiên tạo topic và queue bằng Console, CLI hoặc hạ tầng dưới dạng mã (Terraform/CloudFormation/CDK). Hai lệnh CLI cơ bản:

~~~bash
aws sns create-topic \
  --name order-events \
  --region ap-southeast-1

aws sqs create-queue \
  --queue-name order-email-jobs \
  --region ap-southeast-1
~~~

Lấy **TopicArn** từ kết quả tạo topic; lấy **QueueArn** bằng **sqs get-queue-attributes** với thuộc tính **QueueArn**. Giả sử cả hai ở account **123456789012**, tạo subscription:

~~~bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-southeast-1:123456789012:order-events \
  --protocol sqs \
  --notification-endpoint arn:aws:sqs:ap-southeast-1:123456789012:order-email-jobs \
  --region ap-southeast-1
~~~

**Trước khi kiểm thử giao nhận**, cấu hình **resource policy** trên queue để SNS có thể gửi message. Ví dụ statement trong queue access policy (đặt bằng Console/IaC và thay ARN thực tế):

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
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-email-jobs",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
        }
      }
    }
  ]
}
~~~

Giới hạn theo **aws:SourceArn** giảm nguy cơ một SNS topic khác gửi thông điệp vào queue. Với KMS encryption tùy chỉnh, còn phải kiểm tra quyền KMS phù hợp cho đường phân phối.

Sau khi subscription đã được tạo, có thể gán **FilterPolicy** bằng CLI (thay **SUBSCRIPTION_ARN** bằng ARN subscription nhận được):

~~~bash
aws sns set-subscription-attributes \
  --subscription-arn "$SUBSCRIPTION_ARN" \
  --attribute-name FilterPolicy \
  --attribute-value '{"eventType":["ORDER_CREATED"]}'
~~~

Hoặc đặt cấu hình tương ứng trong IaC để version-control và tránh cấu hình bằng tay chênh lệch giữa môi trường. Ví dụ trên dùng mặc định **FilterPolicyScope=MessageAttributes**; thông điệp trong Java ở mục 5.3 sẽ khớp filter.

## 7. Thử lại, lỗi phân phối và tính tin cậy

Ba thời điểm lỗi cần được tách rõ:

| Vị trí | Ví dụ lỗi | Cách xử lý |
| --- | --- | --- |
| **Publisher → SNS** | Thiếu **sns:Publish**, sai region/ARN, timeout | Log nguyên nhân; retry có backoff khi phù hợp; dùng outbox nếu cần bảo đảm phát hành sau commit |
| **SNS → endpoint** | Queue policy từ chối, webhook trả lỗi, đích không sẵn sàng | Kiểm tra quyền và delivery status; dùng cơ chế retry của SNS và **subscription DLQ** khi áp dụng |
| **Consumer xử lý** | Worker nhận SQS message nhưng database lỗi | Dùng retry/visibility timeout và **SQS DLQ**; thiết kế idempotent |

**Subscription DLQ** (SNS redrive) xử lý thông điệp mà SNS không thể giao đến endpoint sau chính sách thử lại. **SQS DLQ** của queue tiêu thụ lại phục vụ thông điệp đã vào SQS nhưng consumer không xử lý được. Hai loại DLQ thuộc **hai giai đoạn khác nhau**.

Để hệ thống hoạt động ổn định:

- **Idempotency:** lưu hoặc nhận diện **eventId** đã xử lý; không gửi email hoặc ghi sổ kép khi nhận lặp.
- **Quan sát:** theo dõi số lần publish, số thông điệp được phân phối/thất bại, tuổi thông điệp trong SQS, số message trong DLQ và lỗi xử lý của consumer. Gắn correlation ID hoặc event ID vào log.
- **Bảo mật:** chỉ cấp quyền IAM cần thiết, bảo vệ endpoint HTTPS, áp dụng mã hóa và KMS theo yêu cầu, tránh đưa secret hoặc dữ liệu nhạy cảm không cần thiết vào body.
- **Hợp đồng sự kiện:** có **eventType**, **eventId**, thời điểm xảy ra, phiên bản schema khi cần; xem xét tính tương thích ngược vì nhiều subscriber có thể nâng cấp vào thời điểm khác nhau.
- **Dung lượng:** tuân thủ giới hạn kích thước thông điệp SNS (thông điệp thông thường tối đa **256 KiB**); với payload lớn, lưu đối tượng vào storage rồi phát sự kiện chỉ chứa định danh hoặc đường dẫn truy cập có kiểm soát.

Lưu ý quan trọng: **Publish thành công ≠ gửi tới mọi endpoint thành công ≠ xử lý nghiệp vụ thành công**. Cần quan sát đủ ba chặng.

## 8. Kiểm thử tích hợp SNS và SQS

Có thể kiểm thử luồng bằng môi trường AWS sandbox hoặc bộ giả lập dịch vụ tương thích SNS/SQS như LocalStack. Unit test nên kiểm tra publisher tạo **PublishRequest** đúng topic, body và attributes; integration test nên kiểm tra **phân phối thực tế** qua subscription và queue.

Kịch bản tích hợp tối thiểu:

| Bước | Thao tác | Kỳ vọng |
| --- | --- | --- |
| 1 | Tạo topic Standard, hai queue, hai subscription và queue policies hợp lệ | Hai subscription ở trạng thái sẵn sàng nhận |
| 2 | Đặt filter queue A **ORDER_CREATED**, queue B **ORDER_CANCELLED** | Mỗi queue có điều kiện rõ ràng |
| 3 | Publish **ORDER_CREATED** kèm attribute **eventType** | Chỉ queue A nhận message mới phù hợp |
| 4 | Publish **ORDER_CANCELLED** | Chỉ queue B nhận message mới phù hợp |
| 5 | Publish thiếu **eventType** | Không queue nào nhận nếu cả hai filter đều yêu cầu trường này |
| 6 | Kiểm tra **RawMessageDelivery** và parser consumer | Consumer đọc chính xác **Message** trong envelope hoặc body gốc |
| 7 | Gây lỗi tiêu thụ, xử lý lại message hoặc gửi hai event có cùng **eventId** | Logic nghiệp vụ chỉ áp dụng hiệu ứng một lần; retry/DLQ hoạt động đúng thiết kế |

Với subscription filter vừa thay đổi, tránh assertion tức thời vì có độ trễ lan truyền cấu hình. Ngoài payload, cần kiểm tra queue policy, region, ARNs, quyền IAM/KMS và metrics khi message không tới.

## 9. SNS, SQS và SES nên dùng khi nào?

| Dịch vụ | Công việc chính | Ví dụ |
| --- | --- | --- |
| **SNS** | Phát sự kiện và phân phối tới nhiều subscriber | Một sự kiện đơn hàng tới ba nhánh xử lý |
| **SQS** | Lưu đệm message để worker chủ động lấy và xử lý | Queue công việc gửi email, có retry và DLQ |
| **SES (Simple Email Service)** | Gửi email ứng dụng hoặc email giao dịch với khả năng quản lý danh tính gửi và vận hành email | Email xác nhận đơn hàng có nội dung, template và domain xác thực |

**SNS email subscription** phù hợp một số dạng thông báo đến người nhận đã xác nhận subscription. Khi xây dựng chức năng gửi email cho khách hàng cuối, cần cân nhắc **SES**: worker nhận sự kiện từ SQS rồi gọi SES để gửi email. SNS không thay thế trực tiếp toàn bộ khả năng gửi email ứng dụng của SES.

Thiết kế thường gặp:

~~~mermaid
flowchart LR
    O["Spring Boot<br/>Order Service"] --> S(("SNS<br/>order-events"))
    S --> Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Email Worker"]
    W --> E["Amazon SES"]
    E --> U["Khách hàng"]
~~~

Thiết kế này cô lập quá trình tạo đơn khỏi việc gửi email, đồng thời cho phép thêm subscriber mới mà không đổi mã phát sự kiện.

## 10. Bài tập tự thực hành và câu hỏi kiểm tra

**Bài tập:** Xây dựng ứng dụng Spring Boot phát **ORDER_CREATED** và **ORDER_CANCELLED** lên một SNS Standard topic. Tạo hai SQS queue có filter tương ứng, cấu hình quyền queue policy, viết consumer đọc message và log **eventId**. Thử cả hai chế độ **RawMessageDelivery**, sau đó bổ sung cơ chế tránh xử lý lặp cho consumer.

Các câu hỏi cần tự trả lời được:

1. Vì sao một lệnh **Publish** có thể kích hoạt nhiều nghiệp vụ nhưng publisher không cần biết địa chỉ từng consumer?
2. **Topic** khác **subscription** ở điểm nào? Nếu subscription thiếu quyền gửi vào SQS, publisher sẽ quan sát thấy điều gì?
3. Vì sao **MessageId** trả về từ SNS chưa chứng minh email đã được gửi?
4. Khi nào dùng **FilterPolicyScope=MessageBody** thay cho **MessageAttributes**?
5. **Subscription DLQ** khác **SQS DLQ** như thế nào?
6. Khi nào nên chọn FIFO, và vì sao cả với FIFO consumer vẫn nên idempotent?

**Kết quả mong đợi:** người học mô tả và triển khai được hành trình **Spring Boot publisher → SNS topic → subscription filter → SQS/Lambda/HTTPS endpoint**, gắn đúng quyền AWS, quan sát các giai đoạn giao nhận và lựa chọn SES khi mục tiêu cuối là gửi email ứng dụng.
