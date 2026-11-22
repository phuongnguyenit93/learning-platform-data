# Gọi SQS, SNS, STS và Secrets Manager từ Java

> **Chương:** AWS SDK cho Java  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Thiết lập project Maven/Gradle dùng **AWS SDK for Java 2.x**, BOM và các service modules cần thiết.
2. Tạo AWS service clients đúng **Region**, credentials provider và lifecycle.
3. Gửi, nhận, xóa, thay đổi visibility và gửi batch messages bằng **Amazon SQS**.
4. Xử lý delivery semantics, duplicate messages, ordering, FIFO, visibility timeout và dead-letter queue (DLQ).
5. Publish messages lên **Amazon SNS**, cấu hình topic/subscription, filter policy và fan-out SNS → SQS.
6. Dùng **AWS STS** để xem caller identity, assume role, quản lý temporary credentials và phân biệt role chaining.
7. Lấy **AWS Secrets Manager** secrets, xử lý SecretString/SecretBinary, KMS, rotation và caching.
8. Áp dụng IAM least privilege, resource policies, VPC endpoints, TLS và quản lý dữ liệu nhạy cảm.
9. Xử lý lỗi AWS SDK, retries, timeouts, idempotency và observability.
10. Viết integration tests và dùng AWS CLI **chỉ đọc** để kiểm tra các tài nguyên liên quan.

## 1. Bài toán: Java service cần gửi message, phát sự kiện và lấy secret

Một hệ thống Orders viết bằng **Spring Boot** chạy trên Amazon ECS. Khi người dùng đặt hàng, service cần:

- Gửi công việc xử lý hóa đơn vào **SQS** để worker chạy bất đồng bộ.
- Publish sự kiện **OrderCreated** lên **SNS** để nhiều consumer nhận thông báo.
- Dùng **STS AssumeRole** khi cần truy cập tài nguyên ở một AWS account khác.
- Đọc database credentials từ **Secrets Manager** thay vì lưu password trong source code hoặc file cấu hình.

~~~mermaid
flowchart TB
    API["Spring Boot Orders API"] --> SDK["AWS SDK for Java 2.x"]
    SDK --> SQS["Amazon SQS"]
    SDK --> SNS["Amazon SNS"]
    SDK --> STS["AWS STS"]
    SDK --> SM["AWS Secrets Manager"]
    SQS --> BILL["Billing worker"]
    SNS --> Q1["SQS inventory subscription"]
    SNS --> Q2["SQS analytics subscription"]
    SM --> DB["RDS / Aurora credentials"]
    STS --> ROLE["Temporary role credentials"]
~~~

SDK là lớp client gọi AWS APIs qua HTTPS. IAM xác định caller có quyền gì; service resource policies có thể giới hạn ai được gửi/nhận; VPC/network quyết định đường kết nối. **Tạo client thành công không có nghĩa request sẽ được IAM cho phép**.

### 1.1. Khi nào dùng dịch vụ nào?

| Dịch vụ | Vai trò | Ví dụ trong Orders |
| --- | --- | --- |
| **SQS** | Message queue để tách producer/consumer, buffer backlog và retry. | Gửi CreateInvoice cho worker. |
| **SNS** | Pub/sub để fan-out một thông báo tới nhiều subscriptions. | Publish OrderCreated cho Inventory, Analytics, Notification. |
| **STS** | Cấp temporary security credentials và thông tin identity. | Assume role trong account Billing. |
| **Secrets Manager** | Lưu, phân phối và xoay vòng secrets. | Lấy username/password database hoặc API credential. |

SQS phù hợp khi consumer cần tự pull và kiểm soát xử lý. SNS phù hợp khi producer publish một message tới nhiều subscriber. STS không phải message broker; Secrets Manager không phải nơi lưu mọi loại application configuration công khai.

## 2. AWS SDK for Java 2.x: dependencies và BOM

AWS SDK for Java 2.x dùng package software.amazon.awssdk.*, API builder và immutable request/response models. SDK 1.x dùng package com.amazonaws.* và có lifecycle/API khác.

Với code mới, ưu tiên **SDK 2.x**. Không trộn classes của SDK 1.x và 2.x trong cùng một đoạn code hoặc assume credential provider dùng chung.

### 2.1. Maven: import SDK BOM

BOM quản lý version đồng nhất cho các modules. Ví dụ pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <aws.sdk.version>2.x.y</aws.sdk.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sqs</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sns</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>secretsmanager</artifactId>
    </dependency>
</dependencies>
~~~

2.x.y là placeholder, không phải version có thể resolve. Thay bằng **một release 2.x cụ thể đã được tổ chức phê duyệt**, cập nhật BOM định kỳ và kiểm tra release notes/security advisories. Không để các service modules tự lệch version nếu đã dùng BOM.

### 2.2. Gradle: dùng platform BOM

~~~kotlin
dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.x.y"))

    implementation("software.amazon.awssdk:sqs")
    implementation("software.amazon.awssdk:sns")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:secretsmanager")
}
~~~

Với Gradle, platform(...) import dependency constraints từ BOM. Nếu dùng Spring Boot, kiểm tra dependency management đang quản lý version SDK nào để tránh conflict giữa BOM và dependency constraints khác.

### 2.3. Caching Secrets Manager (tùy chọn)

Nếu ứng dụng cần cache secret để giảm API calls, có thể thêm module riêng:

~~~xml
<dependency>
    <groupId>com.amazonaws.secretsmanager</groupId>
    <artifactId>aws-secretsmanager-caching-java</artifactId>
    <version>2.2.0</version>
</dependency>
~~~

Thư viện caching có versioning độc lập với AWS SDK BOM; release 2.2.0 của component sử dụng AWS SDK for Java 2.x. Kiểm tra release notes trước khi nâng cấp. Cache mặc định dùng LRU và refresh item sau khoảng một giờ; TTL có thể cấu hình. Cache không tự bảo vệ memory chứa secret và không tự invalidates item khi ứng dụng cần refresh tức thì.

## 3. Region, credentials provider và client lifecycle

### 3.1. Không hard-code access keys

AWS SDK for Java 2.x có **default credentials provider chain**. Chain tìm credentials từ các nguồn phù hợp với runtime, ví dụ:

- Java system properties/environment variables khi được cấu hình.
- Web identity token và role cho workload chạy trên nền tảng hỗ trợ.
- Shared AWS config/credentials files trong môi trường developer.
- ECS task role credentials.
- EC2 instance profile credentials.

Với production workloads trên ECS/EC2/Lambda/EKS, ưu tiên **IAM role/workload identity** và để SDK tự lấy/refresh credentials. Không commit access key/secret key vào Git, Docker image, application.yml hoặc Java source.

### 3.2. Tạo SQS client theo Region

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

public final class AwsClients {
    private AwsClients() {}

    public static SqsClient sqsClient() {
        return SqsClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

SDK tự dùng credentials provider mặc định nếu không truyền credentialsProvider. Region có thể được lấy từ application configuration/environment; ví dụ trên chỉ minh họa Singapore (ap-southeast-1).

**Region của client không tự chuyển tới Region chứa queue/topic/secret.** ARN/resource phải ở Region tương ứng với endpoint được gọi; khi truy cập tài nguyên ở Region khác, tạo client với Region đó theo kiến trúc và quyền được cấp.

### 3.3. Tạo client một lần và tái sử dụng

Các synchronous SDK clients là thread-safe và có thể được chia sẻ giữa các threads. Không tạo/đóng một client cho mỗi message/request.

~~~java
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;

public final class AwsClientFactory implements AutoCloseable {
    public final SqsClient sqs;
    public final SnsClient sns;
    public final StsClient sts;
    public final SecretsManagerClient secrets;

    public AwsClientFactory() {
        this.sqs = SqsClient.create();
        this.sns = SnsClient.create();
        this.sts = StsClient.create();
        this.secrets = SecretsManagerClient.create();
    }

    @Override
    public void close() {
        secrets.close();
        sts.close();
        sns.close();
        sqs.close();
    }
}
~~~

create() dùng cấu hình mặc định từ SDK environment/profile/Region chain. Trong ứng dụng thật, quản lý lifecycle bằng dependency injection, ví dụ Spring @Bean singleton và shutdown hook; không đóng client khi request kết thúc.

### 3.4. Cấu hình timeout

Có thể giới hạn thời gian một API call và mỗi attempt:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.regions.Region;

SqsClient client = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .overrideConfiguration(
        ClientOverrideConfiguration.builder()
            .apiCallAttemptTimeout(Duration.ofSeconds(3))
            .apiCallTimeout(Duration.ofSeconds(10))
            .build()
    )
    .build();
~~~

- **apiCallAttemptTimeout:** giới hạn một lần thử HTTP/API.
- **apiCallTimeout:** giới hạn tổng thời gian call, bao gồm retries.
- Timeout phải phù hợp SLO, network và service operation.
- Với long polling SQS, HTTP read timeout phải **dài hơn WaitTimeSeconds** và cộng thêm network margin; nếu thấp hơn, client có thể timeout trước khi SQS trả kết quả.

Không đặt timeout quá thấp rồi tăng retries vô hạn. Retry không thể sửa một request có cấu hình timeout sai.

## 4. SQS: gửi message bằng Java SDK 2.x

### 4.1. Gửi một message

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

public final class InvoicePublisher {
    private final SqsClient sqs;
    private final String queueUrl;

    public InvoicePublisher(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public String publish(String orderId, String operationId) {
        String body = """
            {
              "eventType": "CreateInvoice",
              "orderId": "%s",
              "operationId": "%s"
            }
            """.formatted(orderId, operationId);

        SendMessageRequest request = SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody(body)
            .build();

        SendMessageResponse response = sqs.sendMessage(request);
        return response.messageId();
    }
}
~~~

Ví dụ đơn giản để minh họa API. Trong production, **serialize JSON bằng Jackson** hoặc JSON library thay vì format string trực tiếp; orderId có thể chứa ký tự escape và không nên ghép chuỗi thành JSON bằng tay.

queueUrl là URL của queue, không phải queue ARN. Có thể lấy URL qua deployment configuration hoặc GetQueueUrl nếu IAM role có quyền và cần tra cứu.

### 4.2. Lấy queue URL theo tên

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.GetQueueUrlRequest;

String queueUrl = sqs.getQueueUrl(
    GetQueueUrlRequest.builder()
        .queueName("orders-invoice-queue")
        .build()
).queueUrl();
~~~

Đối với cross-account queue, request có thể cần QueueOwnerAWSAccountId và IAM/resource policy phù hợp. Dùng queue URL/ARN từ môi trường triển khai thay vì đoán tên hoặc account.

### 4.3. Metadata hữu ích của SendMessageResponse

Response có thể cung cấp:

- **messageId:** ID message do SQS cấp.
- **MD5OfMessageBody:** checksum của body theo API.
- **MD5OfMessageAttributes:** checksum attributes khi gửi attributes.
- **sequenceNumber:** thông tin sequence cho FIFO queue.

messageId không phải idempotency key nghiệp vụ. Khi producer timeout sau khi SQS đã nhận message nhưng chưa nhận được response, retry có thể tạo message khác. Hãy gắn **operationId/eventId ổn định** trong body hoặc message attributes và để consumer deduplicate.

## 5. SQS: nhận message, xử lý và xóa

SQS là **pull-based queue**: consumer gọi ReceiveMessage để lấy một batch messages, xử lý, sau đó DeleteMessage khi công việc thành công.

### 5.1. ReceiveMessage với long polling

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;

import java.util.List;

public final class InvoiceWorker {
    private final SqsClient sqs;
    private final String queueUrl;

    public InvoiceWorker(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public List<Message> poll() {
        ReceiveMessageRequest request = ReceiveMessageRequest.builder()
            .queueUrl(queueUrl)
            .maxNumberOfMessages(10)
            .waitTimeSeconds(20)
            .visibilityTimeout(60)
            .messageAttributeNames("All")
            .messageSystemAttributeNames(MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT)
            .build();

        return sqs.receiveMessage(request).messages();
    }
}
~~~

- maxNumberOfMessages tối đa **10** mỗi lần ReceiveMessage.
- waitTimeSeconds tối đa **20 giây** cho long polling.
- visibilityTimeout trong request có thể điều chỉnh thời gian ẩn message sau khi nhận.
- Empty list là bình thường: queue có thể chưa có message.
- Long polling giảm empty receives và số request polling so với short polling.

Một số SDK version dùng các overload/enum khác nhau cho message attributes; hãy chọn API tương ứng với version 2.x trong project.

### 5.2. Xử lý và DeleteMessage

~~~java
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public void handle(Message message) {
    String receiptHandle = message.receiptHandle();

    try {
        processInvoice(message.body());

        sqs.deleteMessage(DeleteMessageRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(receiptHandle)
            .build());
    } catch (RuntimeException failure) {
        // Không xóa message khi business operation thất bại.
        // Message có thể xuất hiện lại sau visibility timeout.
        throw failure;
    }
}
~~~

DeleteMessage cần receiptHandle của lần nhận hiện tại, không dùng messageId. Receipt handle có thể thay đổi mỗi lần message được receive. Dùng handle cũ có thể không xóa được bản nhận hiện tại.

Chỉ delete sau khi business operation commit thành công. Nếu xóa trước rồi database transaction thất bại, message không còn để retry.

### 5.3. Visibility timeout và duplicate delivery

Khi SQS trả message, nó tạm thời ẩn message khỏi các consumer khác trong khoảng **visibility timeout**. Nếu consumer không delete trước khi hết hạn, message có thể xuất hiện lại.

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Worker A
    participant X as Worker B
    Q->>W: Receive message M
    Note over Q: M invisible trong visibility timeout
    W->>W: Processing kéo dài
    Note over Q: Visibility timeout hết
    Q->>X: Message M xuất hiện lại
    W->>Q: Delete bằng receipt handle cũ
    X->>X: Có thể đang xử lý M
~~~

Để giảm duplicate processing:

- Chọn visibility timeout dài hơn thời gian xử lý thông thường và p99 có margin.
- Với công việc dài, dùng **ChangeMessageVisibility** để gia hạn.
- Consumer phải idempotent theo business operation ID.
- Cấu hình DLQ/maxReceiveCount cho poison messages.
- Tránh để worker crash sau side effect nhưng trước DeleteMessage mà không có idempotency.

SQS Standard dùng **at-least-once delivery**; duplicate messages có thể xảy ra kể cả khi visibility timeout được cấu hình hợp lý.

## 6. Gia hạn visibility timeout cho công việc dài

Nếu xử lý invoice có thể mất nhiều phút, consumer có thể gia hạn visibility khi đang làm việc:

~~~java
import software.amazon.awssdk.services.sqs.model.ChangeMessageVisibilityRequest;

public void extendVisibility(String receiptHandle, int seconds) {
    sqs.changeMessageVisibility(
        ChangeMessageVisibilityRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(receiptHandle)
            .visibilityTimeout(seconds)
            .build()
    );
}
~~~

- Giá trị visibility timeout của một lần thay đổi nằm trong giới hạn SQS **0–43.200 giây** (12 giờ) tính theo API.
- Tổng thời gian visibility tính từ lúc nhận ban đầu không thể kéo dài vô hạn bằng cách liên tục gia hạn.
- Nếu job thường xuyên vượt thời gian cho phép, chia nhỏ thành tasks, dùng workflow orchestration hoặc thiết kế lease/checkpoint ở lớp ứng dụng.
- Gia hạn quá muộn, sau khi visibility đã hết, có thể không còn receipt handle hợp lệ để kiểm soát message.

Không dùng visibility timeout làm distributed lock nghiệp vụ duy nhất. Consumer vẫn cần idempotency/conditional update vì duplicate delivery có thể xuất hiện.

## 7. SQS batch APIs: throughput và partial failures

Khi producer gửi nhiều messages, dùng batch APIs có thể giảm số request. SQS batch hỗ trợ tối đa **10 entries cho mỗi request**.

### 7.1. Gửi batch

~~~java
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

var batch = SendMessageBatchRequest.builder()
    .queueUrl(queueUrl)
    .entries(
        SendMessageBatchRequestEntry.builder()
            .id("entry-1")
            .messageBody("{\"orderId\":\"ORDER-1001\"}")
            .build(),
        SendMessageBatchRequestEntry.builder()
            .id("entry-2")
            .messageBody("{\"orderId\":\"ORDER-1002\"}")
            .build()
    )
    .build();

SendMessageBatchResponse response = sqs.sendMessageBatch(batch);

response.successful().forEach(entry ->
    System.out.println("Accepted entry: " + entry.id())
);

response.failed().forEach(entry ->
    System.err.println("Failed entry: " + entry.id() + " - " + entry.code())
);
~~~

Một batch HTTP/API call có thể thành công nhưng **một số entries thất bại**. Luôn đọc cả successful() và failed(); chỉ retry các entries thất bại sau khi phân loại lỗi. Nếu retry toàn bộ batch, các entries đã thành công có thể bị gửi trùng.

### 7.2. Xử lý partial failures

- Dùng ID duy nhất trong batch để map kết quả về business operation.
- Ghi lại failed entry ID, error code và sender fault.
- Retry transient failures với backoff.
- Không retry validation/permission errors vô hạn.
- Giữ idempotency key ở payload để consumer deduplicate nếu producer không biết request đã được nhận hay chưa.

Batch API giảm overhead, nhưng không phải một transaction: các entries không atomic với nhau.

## 8. SQS FIFO: ordering và deduplication

Dùng **FIFO queue** khi cần giữ thứ tự message trong một nhóm nghiệp vụ, ví dụ tất cả commands của một order hoặc một customer.

### 8.1. Gửi message FIFO

~~~java
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

sqs.sendMessage(SendMessageRequest.builder()
    .queueUrl(fifoQueueUrl)
    .messageBody(orderEventJson)
    .messageGroupId("ORDER#10023")
    .messageDeduplicationId("ORDER#10023#PAYMENT#TXN-91")
    .build());
~~~

- Queue FIFO có tên kết thúc bằng **.fifo**.
- MessageGroupId xác định nhóm có ordering riêng; các messages cùng group được xử lý theo thứ tự FIFO.
- Nhiều message groups có thể xử lý song song.
- MessageDeduplicationId dùng để deduplicate sends trong **cửa sổ 5 phút**; content-based deduplication có thể được bật ở queue.
- Không gửi cùng group ID cho mọi workload nếu muốn parallelism cao.

### 8.2. FIFO không bảo đảm business exactly-once

SQS FIFO có cơ chế deduplication và ordering ở tầng queue, nhưng consumer vẫn có thể chạy side effect rồi crash trước DeleteMessage. Khi message được nhận lại, side effect có thể lặp.

Vì vậy, payment/order/inventory consumer vẫn phải dùng **operation ID, inbox table, conditional write hoặc provider idempotency key**. FIFO giúp giảm duplicate sends trong cửa sổ dedup và giữ thứ tự trong group; nó không thay transaction nghiệp vụ.

### 8.3. Standard hay FIFO?

| Nhu cầu | Standard | FIFO |
| --- | --- | --- |
| Throughput/scale rộng | Phù hợp cho nhiều workloads. | Có quotas/throughput mode theo Region và cấu hình. |
| Ordering | Best-effort, không đảm bảo. | Theo từng MessageGroupId. |
| Duplicate delivery | Có thể xảy ra. | Deduplication khi gửi trong cửa sổ hỗ trợ; consumer vẫn cần idempotency. |
| Message groups | Không có. | Có, cho phép song song giữa các groups. |
| Use case | Notifications, background jobs độc lập. | Commands cần tuần tự theo order/account/aggregate. |

## 9. SQS dead-letter queue và redrive

**DLQ** nhận messages không xử lý thành công sau số lần receive/retry được cấu hình ở source queue.

### 9.1. Redrive policy

Redrive policy của source queue định nghĩa:

- **deadLetterTargetArn:** ARN của DLQ.
- **maxReceiveCount:** số lần message có thể được nhận trước khi chuyển DLQ.

DLQ giúp cách ly poison messages để worker không liên tục tiêu tốn tài nguyên cho một payload lỗi. Với FIFO source queue, DLQ cũng phải là FIFO; với Standard source queue, dùng Standard DLQ.

### 9.2. Quy trình xử lý DLQ

1. Alarm khi ApproximateNumberOfMessagesVisible của DLQ tăng.
2. Đọc message/error metadata theo quyền được cấp.
3. Xác định lỗi schema, business validation, IAM, dependency hay transient failure.
4. Sửa producer/consumer hoặc dữ liệu cần thiết.
5. Kiểm thử một message trong môi trường an toàn.
6. Dùng SQS redrive task/controlled replay hoặc consumer chuyên dụng để xử lý lại.
7. Đối chiếu business operation IDs và đánh dấu incident đã phục hồi.

Không tự xóa DLQ để làm dashboard trở về 0. Message trong DLQ có thể là dữ liệu cần khôi phục.

### 9.3. SQS redrive không phải retry vô hạn

Redrive đưa messages trở lại queue nguồn hoặc destination được chọn theo API/configuration; nó không tự sửa lỗi code hoặc permissions. Cần rate limit/monitoring khi redrive để tránh tạo backlog lớn hoặc tái kích hoạt side effects.

## 10. SNS: publish message lên topic

SNS là dịch vụ **push-based pub/sub**. Producer gửi message tới topic ARN; SNS phân phối tới các subscriptions đã được xác nhận và được phép nhận. Với Standard topic, delivery có semantics at-least-once và best-effort ordering; consumer cần idempotency nếu side effect không được phép lặp.

### 10.1. Publish một message

~~~java
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.PublishRequest;
import software.amazon.awssdk.services.sns.model.PublishResponse;

public final class OrderEventPublisher {
    private final SnsClient sns;
    private final String topicArn;

    public OrderEventPublisher(SnsClient sns, String topicArn) {
        this.sns = sns;
        this.topicArn = topicArn;
    }

    public String publish(String eventJson) {
        PublishResponse response = sns.publish(
            PublishRequest.builder()
                .topicArn(topicArn)
                .subject("OrderCreated")
                .message(eventJson)
                .build()
        );
        return response.messageId();
    }
}
~~~

Topic ARN có Region và account ID; client Region phải khớp topic Region. Caller cần quyền sns:Publish trên đúng topic ARN và topic policy phải cho phép nếu có resource-based restrictions.

### 10.2. Message attributes

Attributes cho phép subscriber filter hoặc phân loại message mà không cần parse toàn bộ body.

~~~java
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import java.util.Map;

sns.publish(PublishRequest.builder()
    .topicArn(topicArn)
    .message(eventJson)
    .messageAttributes(Map.of(
        "eventType", MessageAttributeValue.builder()
            .dataType("String")
            .stringValue("OrderCreated")
            .build(),
        "tenantTier", MessageAttributeValue.builder()
            .dataType("String")
            .stringValue("premium")
            .build()
    ))
    .build());
~~~

Message attributes là metadata cho routing/filtering. Không dùng attributes làm nơi chứa credentials, payment secrets hoặc PII không cần thiết.

### 10.3. Structured messages

SNS hỗ trợ message structure dạng JSON cho một số protocol-specific payloads. Khi dùng, phải chỉ định MessageStructure = json và cung cấp keys hợp lệ cho các protocol tương ứng. Không nhầm JSON nghiệp vụ bình thường trong Message body với SNS structured message envelope.

## 11. SNS subscriptions, fan-out và filter policy

Một SNS topic có thể có nhiều subscriptions: SQS, Lambda, HTTP/S, email hoặc các protocol được dịch vụ hỗ trợ. Mỗi subscription có delivery semantics, retry và permission riêng.

~~~mermaid
flowchart LR
    APP["Orders service"] --> TOPIC["SNS topic: order-events"]
    TOPIC --> Q1["SQS inventory"]
    TOPIC --> Q2["SQS analytics"]
    TOPIC --> L["Lambda notification"]
    Q1 --> W1["Inventory worker"]
    Q2 --> W2["Analytics worker"]
~~~

### 11.1. SNS → SQS queue policy

Để SNS gửi message tới SQS, queue policy phải cho phép SNS service principal gọi sqs:SendMessage, giới hạn đúng topic ARN.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSpecificSnsTopic",
      "Effect": "Allow",
      "Principal": {
        "Service": "sns.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-inventory",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
        }
      }
    }
  ]
}
~~~

ARNs trong ví dụ là placeholders. Dùng topic ARN và queue ARN thực tế. Condition aws:SourceArn giúp ngăn topic khác trong cùng account gửi message tới queue khi không được phép.

### 11.2. Raw message delivery

Với SQS subscription, có thể bật **RawMessageDelivery** để SQS nhận message body gốc thay vì SNS JSON envelope. Chọn theo consumer contract:

- Raw delivery: body là payload nghiệp vụ.
- Wrapped delivery: body chứa SNS metadata/envelope và message payload.

Consumer phải biết rõ format để deserialize đúng. Không đổi raw delivery giữa chừng mà không version hóa consumer contract.

### 11.3. Filter policy

Subscription filter policy cho phép chỉ gửi những messages khớp thuộc tính hoặc body fields.

Ví dụ filter theo message attribute eventType:

~~~json
{
  "eventType": ["OrderCreated", "OrderPaid"],
  "tenantTier": ["premium"]
}
~~~

Filter policy có thể được đặt để match **message attributes** hoặc **message body** tùy cấu hình subscription. Nếu filter theo body, JSON body phải đúng cấu trúc; thay đổi schema có thể làm subscriber không còn match.

### 11.4. Subscription confirmation và delivery

Một số protocols yêu cầu xác nhận subscription hoặc endpoint ownership. Với SQS subscription trong cùng account, thao tác thường được tích hợp khi tạo subscription và policy phù hợp; với HTTP/S hoặc cross-account, phải xử lý confirmation/authorization theo protocol.

SNS topic publish thành công chỉ chứng minh SNS đã nhận message; không chứng minh mọi downstream consumer đã xử lý business operation thành công. Theo dõi delivery failures, SQS backlog, Lambda errors và business acknowledgements.

## 12. SNS FIFO và thứ tự fan-out

SNS hỗ trợ **FIFO topics** cho use cases cần ordering và deduplication khi phân phối tới **SQS FIFO subscriptions**.

### 12.1. Publish tới FIFO topic

~~~java
sns.publish(PublishRequest.builder()
    .topicArn(fifoTopicArn)
    .message(orderEventJson)
    .messageGroupId("ORDER#10023")
    .messageDeduplicationId("ORDER#10023#EVENT#PAID#V4")
    .build());
~~~

- FIFO topic có tên kết thúc bằng **.fifo**.
- MessageGroupId xác định nhóm có thứ tự.
- MessageDeduplicationId hoặc content-based deduplication giúp loại duplicate publish trong cửa sổ deduplication của SNS FIFO.
- Cửa sổ deduplication của SNS FIFO là **5 phút**; đây là deduplication ở tầng publish, không phải cam kết exactly-once business processing.
- FIFO topic phù hợp với SQS FIFO subscriptions; không giả định mọi protocol subscription của SNS Standard đều dùng được với FIFO.
- Ordering được đảm bảo trong message group theo semantics dịch vụ, không phải một thứ tự toàn cục giữa mọi groups.

### 12.2. SNS FIFO và SQS FIFO

Nếu cần bảo toàn thứ tự end-to-end, dùng FIFO topic và FIFO queues ở các subscriber tương ứng, đồng thời giữ cùng business grouping key. Khi consumer xử lý bất đồng bộ, phải giữ logic idempotency và quản lý lỗi để không làm sai thứ tự nghiệp vụ.

SNS FIFO deduplication không thay idempotency của worker. Một consumer có thể commit side effect rồi lỗi trước khi xóa message khỏi SQS FIFO.

### 12.3. Fan-out có kiểm soát

Một topic có nhiều subscribers độc lập. Subscriber Inventory có thể filter OrderCreated, Billing nhận OrderPaid, Analytics nhận cả hai. Mỗi subscriber nên có queue riêng để:

- Tách tốc độ xử lý và backlog.
- Có DLQ riêng.
- Triển khai consumer độc lập.
- Không để consumer chậm làm các consumer khác phải chờ.
- Định nghĩa retry, retention và monitoring riêng.

## 13. STS: xác định caller identity

AWS Security Token Service (STS) cung cấp APIs để xem identity hiện tại và cấp temporary credentials.

### 13.1. GetCallerIdentity

~~~java
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.create()) {
    GetCallerIdentityResponse identity = sts.getCallerIdentity();
    System.out.println("Account: " + identity.account());
    System.out.println("ARN: " + identity.arn());
    System.out.println("User ID: " + identity.userId());
}
~~~

GetCallerIdentity trả account, ARN và user ID của principal đang ký request. API này **không yêu cầu IAM permission**; kể cả policy có explicit Deny cho sts:GetCallerIdentity, STS vẫn trả thông tin identity theo đặc tính của API.

Dùng API này trong diagnostics để xác minh workload đang chạy bằng ECS task role, EC2 instance profile hay assumed role. Không log toàn bộ credentials hoặc token.

### 13.2. ARN của assumed role

Một assumed role identity thường có ARN dạng:

~~~text
arn:aws:sts::111122223333:assumed-role/OrdersRuntimeRole/orders-api-session
~~~

ARN này khác role ARN dạng iam::...:role/OrdersRuntimeRole. ARN STS thể hiện session đang thực hiện request; role ARN là resource IAM được assume.

## 14. STS AssumeRole: truy cập account hoặc role khác

Khi service cần quyền thuộc một AWS account khác, dùng **AssumeRole** để nhận temporary access key, secret key và session token. Không sao chép access keys dài hạn từ account đích.

### 14.1. Hai phía cần cho phép

**Identity policy** của caller phải cho phép sts:AssumeRole trên role ARN đích. **Trust policy** của role đích phải tin cậy caller account/role và conditions phù hợp.

Ví dụ trust policy ở account Billing:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustOrdersRuntime",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/OrdersRuntimeRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Ví dụ identity policy gắn cho OrdersRuntimeRole:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/BillingReadRole"
    }
  ]
}
~~~

Các ARN chỉ là ví dụ. Trust policy còn có thể dùng ExternalId, SourceIdentity, session tags và điều kiện MFA khi phù hợp.

### 14.2. AssumeRole bằng Java SDK v2

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;
import software.amazon.awssdk.services.sqs.SqsClient;

StsClient sts = StsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();

AssumeRoleRequest assumeRequest = AssumeRoleRequest.builder()
    .roleArn("arn:aws:iam::444455556666:role/BillingReadRole")
    .roleSessionName("orders-api-billing-read")
    .durationSeconds(3600)
    .build();

StsAssumeRoleCredentialsProvider provider =
    StsAssumeRoleCredentialsProvider.builder()
        .stsClient(sts)
        .refreshRequest(assumeRequest)
        .build();

SqsClient billingSqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(provider)
    .build();
~~~

Provider quản lý việc lấy và refresh temporary credentials khi cần. Giữ provider sống cùng client; khi shutdown, đóng service client, provider và STS client theo lifecycle của ứng dụng.

Không tự gọi AssumeRole một lần rồi giữ credentials trong memory tới khi hết hạn nếu workload chạy lâu. Temporary credentials có expiration; dùng provider chuyên dụng giúp tự refresh.

### 14.3. Session duration và role chaining

- AssumeRole thường mặc định một giờ nếu không chỉ định duration.
- Thời lượng tối đa phụ thuộc cấu hình **MaxSessionDuration** của role, trong giới hạn STS.
- Nếu caller đang dùng assumed role rồi tiếp tục AssumeRole (role chaining), session mới bị giới hạn **tối đa một giờ**.
- Khi session hết hạn, SDK provider cần refresh bằng source credentials còn hợp lệ.

Không đặt session dài hơn mức cần thiết. Session name nên giúp audit biết workload/operation nào assume role, không chứa dữ liệu khách hàng.

### 14.4. ExternalId và cross-account third party

Khi một third-party service truy cập account của khách hàng, dùng **ExternalId** trong trust policy và AssumeRole request để giảm confused deputy risk. ExternalId không phải password và không thay thế việc kiểm soát Principal. Chỉ dùng giá trị do integration contract quy định.

### 14.5. Web identity và workload roles

Với EKS IRSA hoặc môi trường hỗ trợ web identity, SDK có thể dùng web identity token file và role ARN thông qua default credential provider chain. Không cần lấy static keys rồi gọi AssumeRole thủ công nếu workload identity đã cấp đúng role.

Với ECS task, gán task role; với EC2, dùng instance profile. Chỉ dùng AssumeRole bổ sung khi thực sự cần chuyển security boundary sang role khác.

## 15. Secrets Manager: lấy secret từ Java

Secrets Manager lưu secret values, metadata, versions và rotation configuration. Ứng dụng nên lấy secret qua SDK bằng IAM role và giữ secret trong memory ở phạm vi cần thiết.

### 15.1. Secret JSON mẫu

Một database secret có thể có cấu trúc:

~~~json
{
  "engine": "postgres",
  "host": "orders-db.cluster-example.ap-southeast-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "orders",
  "username": "orders_app",
  "password": "REDACTED"
}
~~~

Giá trị trên chỉ là cấu trúc minh họa. Không lưu secret thật trong bài học, source code hoặc log.

### 15.2. GetSecretValue bằng Java SDK v2

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class SecretReader {
    private final SecretsManagerClient secrets;

    public SecretReader(SecretsManagerClient secrets) {
        this.secrets = secrets;
    }

    public String readSecretString(String secretId) {
        GetSecretValueResponse response = secrets.getSecretValue(
            GetSecretValueRequest.builder()
                .secretId(secretId)
                .versionStage("AWSCURRENT")
                .build()
        );

        if (response.secretString() == null) {
            throw new IllegalStateException("Secret does not contain SecretString");
        }
        return response.secretString();
    }
}
~~~

secretId có thể là secret name hoặc ARN. Trong môi trường production, dùng ARN hoặc configuration rõ ràng để tránh lấy nhầm secret cùng tên ở account/Region khác. AWSCURRENT là staging label thường dùng cho version hiện tại.

### 15.3. SecretBinary

Secrets Manager hỗ trợ SecretString hoặc SecretBinary. Với binary data, SDK trả về SdkBytes:

~~~java
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

GetSecretValueResponse response = secrets.getSecretValue(request);

SdkBytes binary = response.secretBinary();
if (binary != null) {
    byte[] bytes = binary.asByteArray();
    // Chuyển đổi theo định dạng binary do ứng dụng định nghĩa.
}
~~~

Không giả định mọi secret đều là JSON string. Kiểm tra response field trước khi parse.

### 15.4. Parse JSON secret bằng Jackson

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public record DatabaseSecret(
    String engine,
    String host,
    int port,
    String dbname,
    String username,
    String password
) {}

ObjectMapper mapper = new ObjectMapper();
DatabaseSecret dbSecret =
    mapper.readValue(secretJson, DatabaseSecret.class);

// Dùng fields để cấu hình connection factory.
// Không in dbSecret hoặc password ra logs.
~~~

Record là ví dụ cho Java 17+. Thực tế cần xử lý thiếu field, schema version, rotation và lỗi parse; không giả định secret luôn có đầy đủ các keys.

## 16. Secrets Manager caching và rotation

### 16.1. Vì sao nên cache?

Nếu mọi HTTP request đều gọi GetSecretValue, ứng dụng sẽ:

- Tăng API calls và latency.
- Phụ thuộc Secrets Manager availability cho từng request.
- Tăng chi phí khi workload lớn.
- Có nguy cơ tạo burst khi nhiều instances cùng khởi động.

Cache trong memory giúp giảm các request lặp lại. Có thể dùng **AWS Secrets Manager Java caching client** hoặc một cache có TTL do ứng dụng quản lý. Thư viện caching có lifecycle/version riêng; xác minh SDK compatibility, thread safety, refresh interval và eviction behavior trước khi triển khai.

### 16.2. Cache cần có TTL và refresh strategy

- Không cache secret vô thời hạn.
- Chọn refresh interval phù hợp rotation schedule và yêu cầu availability.
- Có jitter để nhiều instances không cùng refresh đúng một thời điểm.
- Không log cache contents hoặc exception message có thể chứa secret.
- Khi authentication với database thất bại do credential rotation, dùng API refreshNow của caching client v2 (nếu đang dùng thư viện đó) hoặc refresh cache do ứng dụng quản lý, rồi thử lại có giới hạn.
- Không retry vô hạn bằng password cũ.

Ví dụ dùng caching client v2 để buộc refresh một secret sau khi nhận lỗi xác thực:

~~~java
import com.amazonaws.secretsmanager.caching.SecretCache;

try (SecretCache cache = new SecretCache()) {
    String current = cache.getSecretString(secretArn);
    // Dùng current để tạo credential/connection theo cấu hình ứng dụng.

    boolean refreshed = cache.refreshNow(secretArn);
    if (!refreshed) {
        throw new IllegalStateException("Could not refresh secret");
    }
    String rotated = cache.getSecretString(secretArn);
}
~~~

Một cache TTL dài làm giảm API calls nhưng tăng thời gian app tiếp tục dùng credential cũ. Cache implementation không phải security-hardened vault; giữ secret trong memory tối thiểu, kiểm soát heap dumps và không log giá trị. Đây là trade-off phải được ghi rõ trong security review.

### 16.3. Rotation lifecycle

Secrets Manager rotation thường dùng Lambda rotation function và staging labels:

- **AWSCURRENT:** version hiện hành mà ứng dụng nên dùng.
- **AWSPENDING:** version đang trong quá trình rotation.
- **AWSPREVIOUS:** version trước đó, nếu có.

Rotation flow chuẩn gồm các bước tạo secret mới, cập nhật target credential, kiểm tra credential mới và chuyển AWSCURRENT. Chi tiết phụ thuộc rotation template/target service.

~~~mermaid
sequenceDiagram
    participant SM as Secrets Manager
    participant L as Rotation Lambda
    participant DB as RDS / Database
    participant APP as Java application
    SM->>L: Create pending secret
    L->>DB: Set new credential
    L->>DB: Test new credential
    L->>SM: Promote AWSCURRENT
    APP->>SM: GetSecretValue AWSCURRENT
    SM-->>APP: Current secret version
    APP->>DB: Connect with refreshed credential
~~~

### 16.4. Database connection pools và rotation

Khi database password được xoay:

- Connections hiện hữu có thể vẫn hoạt động cho tới khi đóng hoặc server revoke session.
- Connection pool có thể tiếp tục tạo connection mới bằng credential cũ nếu secret cache chưa refresh.
- Ứng dụng cần phối hợp secret refresh với HikariCP/DataSource lifecycle.
- Với RDS Proxy và Secrets Manager, cấu hình rotation/authentication theo hướng dẫn của dịch vụ; proxy có thể dùng secret để thiết lập backend connection.
- Kiểm thử rotation khi có traffic, pool warm và app scale out.

Không restart toàn bộ service ngay sau mỗi rotation nếu có cách refresh có kiểm soát; nhưng cũng không giữ credential cũ vô thời hạn.

## 17. IAM và bảo mật khi gọi bốn dịch vụ

### 17.1. Quyền tối thiểu theo workload

| Workload | Actions thường cần | Resource scope |
| --- | --- | --- |
| SQS producer | sqs:SendMessage; có thể SendMessageBatch. | Một queue ARN cụ thể. |
| SQS consumer | sqs:ReceiveMessage, sqs:DeleteMessage, sqs:ChangeMessageVisibility, GetQueueAttributes nếu cần. | Queue ARN cụ thể. |
| SNS publisher | sns:Publish. | Topic ARN cụ thể. |
| STS caller | sts:AssumeRole. | Role ARN đích cụ thể. |
| Secrets reader | secretsmanager:GetSecretValue; DescribeSecret nếu cần metadata. | Secret ARN cụ thể. |
| KMS-backed secret reader | kms:Decrypt trên key phù hợp nếu secret dùng customer managed key. | KMS key ARN cụ thể. |

Không cấp sqs:* hoặc secretsmanager:* trên mọi resources chỉ để xử lý một use case.

### 17.2. Identity policy và resource policy

Để request được chấp nhận, cần xem xét:

- IAM identity policy của caller.
- Queue/topic/secret resource policy nếu resource policy được dùng.
- Trust policy của role khi AssumeRole.
- Permissions boundary và AWS Organizations SCP.
- KMS key policy nếu dữ liệu mã hóa bằng customer managed key.
- VPC endpoint policy nếu request đi qua interface/gateway endpoint.

**Explicit Deny thắng Allow.** Một IAM Allow ở application role không vượt qua explicit Deny từ SCP/resource policy/KMS policy.

### 17.3. SQS queue policy

Queue policy thường cần khi:

- SNS gửi message tới SQS.
- Một AWS account khác gửi/nhận message.
- Một AWS service principal cần quyền gửi.
- Muốn giới hạn producer theo source ARN/source account.

Khi dùng SNS → SQS, giới hạn aws:SourceArn vào đúng topic. Khi dùng cross-account, kết hợp identity policy ở sender account và resource policy ở queue owner account.

### 17.4. SNS topic policy

SNS topic policy có thể cho phép publisher khác account hoặc AWS service publish. Chỉ định Principal và sns:Publish trên topic ARN cần thiết; nếu tích hợp với AWS service, dùng conditions theo hướng dẫn của dịch vụ để tránh confused deputy.

### 17.5. Secrets Manager và KMS

- Secrets Manager mặc định mã hóa secret bằng AWS managed key hoặc key phù hợp cấu hình.
- Với customer managed KMS key, principal cần quyền decrypt và key policy phải cho phép.
- Truy cập cross-account secret cần identity policy, secret resource policy và customer managed KMS key có policy phù hợp.
- Không disable/delete KMS key khi vẫn cần đọc secret.
- Không đưa secret value vào CloudWatch, traces, exception telemetry hoặc support tickets.

### 17.6. VPC endpoints và private connectivity

Workloads trong private subnet có thể dùng VPC endpoints để gọi các AWS APIs mà không cần public internet route tương ứng:

- SQS interface VPC endpoint.
- SNS interface VPC endpoint.
- STS interface VPC endpoint.
- Secrets Manager interface VPC endpoint.

Kiểm tra endpoint service name, private DNS, subnet/AZ coverage, endpoint security group, route/DNS và endpoint policy. VPC endpoint không thay IAM; request vẫn phải được authorize.

## 18. Retry, timeout và lỗi trong AWS SDK for Java 2.x

### 18.1. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Service exception** | AccessDenied, ResourceNotFound, InvalidParameter, throttling. | Đọc error code/status/request ID; sửa permission/config hoặc retry nếu transient. |
| **Client/transport exception** | DNS, socket timeout, TLS, connection reset. | Kiểm tra network, endpoint, proxy, DNS và timeout. |
| **Business failure** | Duplicate operation, invalid state, message schema không hợp lệ. | Xử lý ở application layer, không retry mù. |
| **Partial batch failure** | Một số entries trong batch không thành công. | Chỉ retry entries lỗi sau khi phân loại. |

SDK service exceptions thường kế thừa AwsServiceException; lỗi phía client/network thường là SdkClientException. Service exception có status code, error details và request ID hữu ích cho support/diagnostics.

### 18.2. Retry strategy

AWS SDK for Java 2.x có retry strategy tích hợp. Dùng behavior chuẩn của SDK cho các lỗi retryable; điều chỉnh max attempts/backoff khi workload có yêu cầu rõ ràng.

Không retry các lỗi cấu hình vĩnh viễn như AccessDenied hoặc validation errors. Với throttling/transient service errors, backoff có jitter để giảm retry storm.

### 18.3. Retry và duplicate side effects

Giả sử SendMessage được SQS chấp nhận nhưng response bị mất do network timeout. SDK hoặc ứng dụng có thể gửi lại; producer không biết request trước đã thành công hay chưa.

Tương tự, SNS Publish có thể đã được nhận trước khi client timeout. Vì vậy:

- Dùng business event ID ổn định.
- Consumer deduplicate.
- Không coi messageId của SQS/SNS là business idempotency key.
- Với payment/third-party API, dùng idempotency key của hệ thống đích.
- Ghi outcome theo operation ID để reconciliation.

### 18.4. API call timeout và attempt timeout

Cấu hình attempt timeout để giới hạn một lần request; call timeout giới hạn tổng cả retries. Với long polling SQS, read/socket timeout phải dài hơn thời gian chờ queue. Với Secrets Manager/STS, timeout cần phù hợp cold start, network và refresh cadence.

Không dùng một timeout duy nhất cho mọi services mà không cân nhắc semantics. ReceiveMessage long poll 20 giây khác GetCallerIdentity hoặc GetSecretValue.

## 19. Observability và vận hành

### 19.1. SQS metrics

CloudWatch metrics hữu ích:

- **ApproximateNumberOfMessagesVisible:** backlog đang chờ nhận.
- **ApproximateNumberOfMessagesNotVisible:** messages đang bị ẩn/được xử lý.
- **ApproximateAgeOfOldestMessage:** tuổi message cũ nhất đang chờ.
- **NumberOfMessagesSent/Received/Deleted:** xu hướng producer/consumer.
- **NumberOfEmptyReceives:** số lần receive không có message.
- **ApproximateNumberOfMessagesDelayed:** messages đang bị delay.

Tên metric có thể dùng Approximate vì đây là số liệu gần đúng. Queue depth thấp không chứng minh consumer đã xử lý đúng business operation; cần app success/error metrics.

### 19.2. SNS metrics

Theo dõi các metrics như NumberOfMessagesPublished, NumberOfNotificationsDelivered, NumberOfNotificationsFailed và delivery failures theo protocol/subscriber. Một publish thành công không đồng nghĩa tất cả endpoints nhận hoặc xử lý thành công.

### 19.3. STS và Secrets Manager audit

- CloudTrail ghi các AWS API calls như AssumeRole, GetSecretValue và các control-plane operations.
- Không có secret value trong thông tin audit event tiêu chuẩn, nhưng logs vẫn cần được bảo vệ.
- Theo dõi AccessDenied, unexpected role assumptions, principal/account/Region và secret access pattern.
- Cảnh báo khi workload đọc secret quá thường xuyên hoặc từ Region/account không mong đợi.

### 19.4. Application metrics

Nên ghi:

- SQS publish success/failure và batch partial failures.
- Queue receive count, processing duration, delete outcome.
- Duplicate operation count và idempotency result.
- SNS publish success/failure và subscriber backlog.
- STS AssumeRole refresh failures và caller identity changes.
- Secrets refresh age, cache hit/miss và authentication failures.

Không ghi message body chứa PII hoặc secret chỉ để debug. Log correlation ID, operation ID, AWS request ID và error code.

## 20. AWS CLI chỉ đọc: kiểm tra queue, topic, role và secret metadata

Các lệnh dưới đây chỉ đọc trạng thái/cấu hình; không gửi message, publish, assume role hoặc lấy secret value.

### 20.1. Caller identity

~~~bash
aws sts get-caller-identity
~~~

Xác nhận account, ARN và UserId của AWS credentials đang dùng.

### 20.2. SQS queue metadata

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-invoice \
  --attribute-names All \
  --region ap-southeast-1
~~~

Xem VisibilityTimeout, ReceiveMessageWaitTimeSeconds, RedrivePolicy, QueueArn, ApproximateNumberOfMessages và encryption settings nếu được trả về. Queue URL là placeholder.

### 20.3. SNS topic và subscriptions

~~~bash
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1

aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1
~~~

Kiểm tra topic policy, encryption, delivery status settings và endpoint subscriptions. Không dùng list-subscriptions để kết luận subscriber đã xử lý message thành công.

### 20.4. Role metadata

~~~bash
aws iam get-role \
  --role-name BillingReadRole
~~~

GetRole đọc trust policy/role metadata. Để xem attached/inline policies, dùng các IAM list/get APIs có quyền phù hợp. Không cần assume role chỉ để xem caller identity.

### 20.5. Secrets Manager metadata

~~~bash
aws secretsmanager describe-secret \
  --secret-id arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/database-EXAMPLE \
  --region ap-southeast-1
~~~

DescribeSecret trả metadata, rotation configuration, KMS key ARN và version staging labels theo quyền; nó không trả secret value. **Không chạy get-secret-value trong terminal chia sẻ hoặc log công khai**, vì output chứa credential thật.

## 21. Kiểm thử ứng dụng Java

### 21.1. Unit tests

Mock service clients hoặc bọc chúng trong application interfaces để kiểm tra:

- SQS publisher tạo đúng queue URL, body và message attributes.
- Consumer chỉ DeleteMessage sau khi business operation thành công.
- Batch publisher xử lý successful/failed entries riêng.
- SNS publisher gửi đúng topic ARN và message attributes.
- STS provider được cấu hình role ARN/session name đúng.
- Secrets parser xử lý SecretString/SecretBinary và missing fields.

Unit test không chứng minh IAM policy hoặc resource policy trên AWS thật đã đúng.

### 21.2. Integration tests trong sandbox

Dùng một AWS account/Region dành riêng cho test:

1. Tạo SQS Standard/FIFO queues và DLQ theo IaC.
2. Tạo SNS topic/subscriptions và queue policy.
3. Tạo IAM role/trust policy cho STS AssumeRole.
4. Tạo secret giả không chứa credentials production.
5. Chạy producer/consumer với operation IDs cố định.
6. Kiểm thử visibility timeout, duplicate, redrive và SNS filter policy.
7. Kiểm thử rotation/cache refresh trong môi trường kiểm soát.
8. Xóa resources theo teardown process và theo dõi chi phí.

LocalStack hoặc service mocks có thể hỗ trợ developer feedback nhanh, nhưng không thay integration tests với AWS cho IAM, STS, KMS, SNS delivery và service-specific semantics.

### 21.3. Kiểm thử failure paths

- SQS AccessDenied hoặc queue URL sai.
- SNS topic ARN sai Region.
- Consumer crash trước DeleteMessage.
- SQS message hết visibility timeout và được receive lại.
- STS AssumeRole bị deny do trust policy.
- Temporary credentials hết hạn.
- Secret version bị rotate khi connection pool vẫn dùng credentials cũ.
- KMS key policy không cho phép decrypt.
- VPC endpoint policy chặn request.

## 22. Chi phí và lựa chọn kiến trúc

| Dịch vụ | Các khoản cần xem |
| --- | --- |
| **SQS** | Requests, payload/request units, FIFO usage, DLQ storage và data transfer theo pricing. |
| **SNS** | Publish/delivery requests, protocol, payload và delivery retries. |
| **STS** | API usage/quota và operational overhead; không tạo AssumeRole mới cho từng message nếu provider có thể refresh/reuse. |
| **Secrets Manager** | Số secrets lưu trữ, API calls, rotation Lambda và KMS requests. |
| **CloudWatch** | Metrics, alarms, dashboards, logs và data ingestion. |
| **VPC endpoints** | Endpoint hourly/data processing charges theo Region. |
| **KMS** | Customer managed key storage và cryptographic API requests. |

Không giả định mọi API call đều miễn phí hoặc cùng giá ở mọi Region. Dùng AWS Pricing Calculator/Cost Explorer để kiểm tra giá hiện hành.

### 22.1. Giảm chi phí mà vẫn giữ khả năng phục hồi

- Dùng SQS long polling và batch API khi phù hợp.
- Không poll liên tục với short polling khi queue rỗng.
- Đặt retention/DLQ lifecycle theo yêu cầu nghiệp vụ.
- Dùng SNS fan-out thay vì producer tự gọi nhiều consumers khi mô hình phù hợp.
- Cache secrets có TTL hợp lý thay vì gọi GetSecretValue cho từng request.
- Tái sử dụng STS credentials provider và AWS service clients.
- Theo dõi retries, duplicate processing và poison messages.
- Giới hạn log payload và CloudWatch retention.

## 23. Runbook: lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| SQS SendMessage AccessDenied | IAM identity/queue policy thiếu sqs:SendMessage, endpoint policy deny. | Caller ARN, queue ARN, IAM policies, CloudTrail. |
| SQS queue URL sai | URL thuộc account/Region khác hoặc queue đã đổi. | GetQueueUrl/queue metadata theo đúng Region. |
| Message lặp | At-least-once, timeout, consumer crash trước delete, visibility hết hạn. | ApproximateReceiveCount, operation ID, consumer logs. |
| Message không biến mất | Delete dùng receipt handle cũ hoặc sai queue URL. | Receipt handle của lần receive mới nhất và delete result. |
| FIFO message bị chặn | Message trước trong cùng group chưa được xử lý/delete. | MessageGroupId, visibility, DLQ và consumer status. |
| SNS publish AccessDenied | sns:Publish hoặc topic policy thiếu quyền. | Topic ARN, caller identity, policy và Region. |
| SNS không gửi tới SQS | Queue policy thiếu sns:SendMessage hoặc SourceArn sai. | Subscription status, queue policy, delivery metrics. |
| Filter policy không match | Attribute/body format hoặc filter scope không khớp. | Message attributes, filter policy scope và JSON structure. |
| STS AssumeRole AccessDenied | Caller policy hoặc role trust policy không cho phép. | Principal, target role ARN, external ID, SCP và CloudTrail. |
| STS credentials hết hạn | Provider không refresh hoặc source credentials hết hạn. | Provider lifecycle, role duration và source identity. |
| Secrets Manager AccessDenied | Thiếu GetSecretValue, secret resource policy hoặc KMS decrypt. | Secret ARN, IAM, resource policy và key policy. |
| Secret cũ sau rotation | Cache TTL hoặc connection pool chưa refresh. | Version stage AWSCURRENT, cache age và new connection test. |
| Secrets Manager timeout | VPC endpoint/DNS/SG/network hoặc service throttling. | Endpoint, private DNS, retry metrics và Region. |

### 23.1. Thứ tự chẩn đoán

1. Xác nhận account/Region và ARN/URL của resource.
2. Gọi GetCallerIdentity để biết principal hiện tại.
3. Phân biệt identity policy, resource policy, trust policy và KMS key policy.
4. Đọc error code, HTTP status và AWS request ID.
5. Kiểm tra CloudTrail/CloudWatch metrics và resource status.
6. Kiểm thử một request nhỏ trong sandbox.
7. Chỉ retry khi lỗi transient; không retry AccessDenied hoặc validation errors vô hạn.

## 24. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “SDK 2.x dùng package com.amazonaws.” | SDK 2.x dùng software.amazon.awssdk; com.amazonaws thường là SDK 1.x hoặc một số thư viện phụ trợ. |
| “Mỗi request nên tạo một SqsClient.” | Client thread-safe; tái sử dụng và đóng khi application shutdown. |
| “Region của client tự tìm queue ở Region khác.” | Region xác định endpoint; resource ARN/URL phải đúng Region. |
| “SQS SendMessage trả messageId là message đã được xử lý.” | Chỉ xác nhận SQS nhận message; consumer còn phải xử lý. |
| “SQS Standard exactly once.” | Standard at-least-once; duplicate có thể xảy ra. |
| “FIFO nghĩa consumer không bao giờ chạy lại side effect.” | FIFO dedup/order ở queue; consumer vẫn cần idempotency. |
| “Có thể DeleteMessage bằng messageId.” | Cần receiptHandle của lần receive hiện tại. |
| “Batch API là transaction.” | Batch entries có thể partial success/failure. |
| “Visibility timeout là distributed lock.” | Nó chỉ ẩn message tạm thời; không thay idempotency/coordination. |
| “SNS publish thành công nghĩa tất cả subscribers xử lý xong.” | SNS acceptance/delivery khác business processing. |
| “SNS topic policy thay queue policy.” | SNS → SQS cần queue policy cho phép service principal gửi. |
| “GetCallerIdentity cần quyền sts:GetCallerIdentity.” | API không yêu cầu permission theo đặc tính của STS. |
| “AssumeRole credentials sống vô hạn.” | Temporary credentials có expiration; dùng provider refresh. |
| “Role chaining có thể yêu cầu session 12 giờ.” | Role chaining bị giới hạn session tối đa một giờ. |
| “Secrets Manager cache có thể giữ secret mãi.” | Cache cần TTL/refresh và rotation-aware behavior. |
| “DescribeSecret trả password.” | DescribeSecret trả metadata; GetSecretValue mới trả secret value. |
| “IAM GetSecretValue đủ cho secret mã hóa bằng CMK.” | Còn cần KMS key policy/Decrypt permission phù hợp. |
| “Retry mọi lỗi SDK là an toàn.” | AccessDenied/validation/business errors không nên retry mù. |
| “VPC endpoint bỏ qua IAM.” | Endpoint là network path; IAM/resource/KMS authorization vẫn áp dụng. |
| “Log message/secret giúp debug tốt hơn.” | Có thể lộ PII/credentials; log IDs, metadata và error codes đã redacted. |

## 25. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Chọn dịch vụ cho background invoice

**Đề:** Orders API cần giao công việc tạo hóa đơn cho worker. Worker có thể chậm vài phút, cần retry và không được block HTTP request.

**Đáp án:** Dùng **SQS** để buffer và tách producer/consumer. Đặt visibility timeout phù hợp, DLQ và idempotency key theo order/payment operation. SNS chỉ cần nếu cùng event phải fan-out tới nhiều subscribers độc lập.

### Bài tập 2 — Fan-out OrderCreated

**Đề:** Khi một đơn hàng được tạo, Inventory, Analytics và Notification đều cần nhận thông báo với tốc độ xử lý riêng.

**Đáp án:** Publish một message lên **SNS topic**, tạo subscription riêng cho từng consumer; dùng SQS queue riêng ở mỗi subscription để buffer và tách backlog. Thêm queue policy cho SNS principal với aws:SourceArn giới hạn đúng topic.

### Bài tập 3 — SQS message được xử lý hai lần

**Đề:** Worker tạo invoice thành công, nhưng process crash trước DeleteMessage. Sau visibility timeout, message xuất hiện lại.

**Đáp án:** Đây là duplicate delivery có thể xảy ra. Consumer cần business operation ID và transactional inbox/unique constraint để không tạo invoice thứ hai. Chỉ DeleteMessage sau khi business transaction commit.

### Bài tập 4 — ReceiveMessage trả danh sách rỗng

**Đề:** Worker long-poll 20 giây và nhận empty list.

**Đáp án:** Đây là kết quả bình thường nếu queue chưa có message trong thời gian chờ. Không coi empty list là lỗi; worker có thể poll tiếp theo cadence phù hợp.

### Bài tập 5 — Batch SendMessage có partial failure

**Đề:** Một SendMessageBatch có 10 entries, response có 8 successful và 2 failed.

**Đáp án:** Chỉ retry 2 entries failed sau khi phân loại error code. Không gửi lại cả batch vì 8 entries đã thành công có thể bị duplicate. Batch API không phải transaction.

### Bài tập 6 — FIFO messages bị chặn

**Đề:** Một message của ORDER#10023 đang xử lý lâu; các messages sau cùng group chưa được worker khác xử lý.

**Đáp án:** FIFO giữ thứ tự trong cùng MessageGroupId. Kiểm tra visibility timeout, consumer processing và DLQ. Không dùng một group ID cho mọi orders nếu cần parallelism giữa orders.

### Bài tập 7 — DLQ tăng liên tục

**Đề:** DLQ có hàng nghìn messages sau khi consumer deploy phiên bản mới.

**Đáp án:** Dừng redrive tự động, kiểm tra schema/exception/ApproximateReceiveCount và tìm lỗi chung. Roll back hoặc sửa consumer, thử một message trong sandbox, rồi redrive có rate limit và đối chiếu operation IDs.

### Bài tập 8 — SNS publish thành công nhưng SQS không nhận

**Đề:** SDK publish trả messageId nhưng inventory queue không có message.

**Đáp án:** Kiểm tra subscription status, queue policy có sqs:SendMessage cho sns.amazonaws.com không, aws:SourceArn có đúng topic ARN không, topic/queue cùng Region hay có cross-account policy hợp lệ không. Publish success không chứng minh consumer xử lý.

### Bài tập 9 — Filter policy bỏ sót event

**Đề:** SNS filter policy match eventType = OrderPaid, nhưng consumer không nhận message vì producer gửi event_type.

**Đáp án:** Tên attribute phân biệt chính xác và phải khớp policy. Kiểm tra filter scope là message attributes hay body, tên field, data type và JSON shape.

### Bài tập 10 — STS AssumeRole AccessDenied

**Đề:** OrdersRuntimeRole có sts:AssumeRole nhưng vẫn bị deny khi assume BillingReadRole.

**Đáp án:** Kiểm tra cả identity policy của caller và trust policy của BillingReadRole. Sau đó kiểm tra SCP, permissions boundary, explicit Deny, ExternalId/conditions và đúng role ARN/account.

### Bài tập 11 — Role chaining

**Đề:** Một service đang chạy bằng assumed role, rồi assume role thứ hai và yêu cầu session 4 giờ.

**Đáp án:** Role chaining giới hạn session mới tối đa một giờ. Thiết kế source credentials/role chain phù hợp; không giả định MaxSessionDuration của role đích cho phép vượt giới hạn chaining.

### Bài tập 12 — GetCallerIdentity bị explicit Deny

**Đề:** IAM policy có explicit Deny sts:GetCallerIdentity; nhóm vận hành muốn biết caller ARN.

**Đáp án:** GetCallerIdentity không yêu cầu permission và vẫn trả identity theo đặc tính STS. Dùng nó để diagnostics, nhưng không log access keys/session tokens.

### Bài tập 13 — Secret đã rotation nhưng app vẫn dùng password cũ

**Đề:** Database secret chuyển AWSCURRENT sang version mới nhưng một số ECS tasks vẫn kết nối bằng credential cũ.

**Đáp án:** Kiểm tra cache TTL/refresh, task startup configuration và HikariCP connection lifecycle. Thiết kế refresh cache và tạo connection mới có kiểm soát; không log secret để debug.

### Bài tập 14 — Secrets Manager AccessDenied với CMK

**Đề:** Role có secretsmanager:GetSecretValue nhưng API trả AccessDenied khi secret dùng customer managed KMS key.

**Đáp án:** Ngoài secret permission, kiểm tra kms:Decrypt identity permission và KMS key policy/grants, cùng explicit Deny/SCP. Nếu cross-account, kiểm tra secret resource policy và CMK policy.

### Bài tập 15 — Long polling timeout

**Đề:** ReceiveMessage dùng WaitTimeSeconds=20 nhưng HTTP read timeout chỉ 5 giây.

**Đáp án:** Client có thể timeout trước khi long poll kết thúc. Đặt HTTP read timeout lớn hơn WaitTimeSeconds cộng network margin; API call timeout cũng cần đủ lớn.

### Bài tập 16 — AWS client được tạo trong mỗi request

**Đề:** Spring controller tạo mới SqsClient cho mỗi HTTP request và không đóng.

**Đáp án:** Đây là lifecycle sai, gây overhead và rò rỉ resources. Tạo singleton bean, tái sử dụng client thread-safe và đóng khi application shutdown.

### Bài tập 17 — Region của client không khớp topic

**Đề:** SNS topic ở ap-southeast-1 nhưng SnsClient gọi endpoint ap-northeast-1.

**Đáp án:** Tạo client với Region của topic hoặc thiết kế cross-Region routing đúng cách. Không dùng ARN topic của Region này với endpoint Region khác rồi mong SDK tự route.

### Bài tập 18 — Retry tạo duplicate publish

**Đề:** SNS đã nhận Publish nhưng response timeout; producer retry và subscribers nhận hai messages.

**Đáp án:** Đặt business event ID ổn định trong payload, deduplicate ở consumers, và cân nhắc SNS FIFO khi ordering/dedup publish phù hợp. Không dựa messageId transport để nhận diện cùng operation.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** AWS SDK for Java 2.x dùng package chính nào?  
**Đáp án:** software.amazon.awssdk.

**Câu 2.** BOM giúp gì cho Maven/Gradle?  
**Đáp án:** Quản lý version nhất quán cho các AWS SDK service modules.

**Câu 3.** Production ECS task nên lấy credentials từ đâu?  
**Đáp án:** IAM task role qua default credentials provider chain.

**Câu 4.** AWS SDK synchronous service clients có thread-safe không?  
**Đáp án:** Có; tái sử dụng client thay vì tạo một client mỗi request.

**Câu 5.** Region của SqsClient có tự tìm queue ở Region khác không?  
**Đáp án:** Không. Region xác định endpoint; phải cấu hình đúng Region của resource.

**Câu 6.** SQS ReceiveMessage trả tối đa bao nhiêu messages một lần?  
**Đáp án:** 10.

**Câu 7.** Long polling SQS tối đa bao nhiêu giây?  
**Đáp án:** 20 giây.

**Câu 8.** SQS DeleteMessage dùng trường nào?  
**Đáp án:** ReceiptHandle của lần receive hiện tại.

**Câu 9.** SQS Standard có exactly-once delivery không?  
**Đáp án:** Không; Standard at-least-once và duplicate có thể xảy ra.

**Câu 10.** Visibility timeout làm gì?  
**Đáp án:** Tạm ẩn message sau khi nhận để consumer có thời gian xử lý.

**Câu 11.** Vì sao consumer vẫn cần idempotency?  
**Đáp án:** Message có thể được nhận lại khi worker lỗi, timeout hoặc delete thất bại.

**Câu 12.** SQS batch API có atomic không?  
**Đáp án:** Không; response có thể có successful và failed entries.

**Câu 13.** FIFO ordering được đảm bảo trong phạm vi nào?  
**Đáp án:** Trong cùng MessageGroupId.

**Câu 14.** MessageDeduplicationId của FIFO dùng cửa sổ bao lâu?  
**Đáp án:** 5 phút.

**Câu 15.** DLQ nhận message theo cơ chế nào?  
**Đáp án:** Redrive policy của source queue và maxReceiveCount.

**Câu 16.** SNS phù hợp với mô hình nào?  
**Đáp án:** Pub/sub fan-out tới nhiều subscribers.

**Câu 17.** SNS publish thành công có chứng minh subscriber xử lý xong không?  
**Đáp án:** Không; cần theo dõi delivery và business processing riêng.

**Câu 18.** SNS gửi tới SQS cần policy nào ở queue?  
**Đáp án:** Queue resource policy cho phép sns.amazonaws.com gọi sqs:SendMessage, thường giới hạn bằng aws:SourceArn.

**Câu 19.** RawMessageDelivery ảnh hưởng gì?  
**Đáp án:** SQS subscriber nhận body gốc thay vì SNS JSON envelope.

**Câu 20.** SNS FIFO thường kết hợp subscription protocol nào?  
**Đáp án:** SQS FIFO subscriptions theo tính năng SNS FIFO.

**Câu 21.** STS GetCallerIdentity trả gì?  
**Đáp án:** Account, ARN và UserId của caller.

**Câu 22.** GetCallerIdentity có yêu cầu sts:GetCallerIdentity permission không?  
**Đáp án:** Không.

**Câu 23.** AssumeRole cần những quyền nào?  
**Đáp án:** Caller identity policy cho phép sts:AssumeRole và trust policy của role đích cho phép principal/conditions.

**Câu 24.** Role chaining session tối đa bao lâu?  
**Đáp án:** Một giờ.

**Câu 25.** Vì sao dùng StsAssumeRoleCredentialsProvider?  
**Đáp án:** Tự quản lý việc lấy và refresh temporary credentials cho client.

**Câu 26.** Secrets Manager API nào lấy secret value?  
**Đáp án:** GetSecretValue.

**Câu 27.** DescribeSecret có trả password không?  
**Đáp án:** Không; nó trả metadata/configuration. GetSecretValue mới trả secret value.

**Câu 28.** SecretString và SecretBinary khác nhau thế nào?  
**Đáp án:** Một trường chứa string; trường kia chứa binary bytes qua SDK SdkBytes.

**Câu 29.** Khi secret dùng customer managed KMS key, quyền nào có thể cần thêm?  
**Đáp án:** kms:Decrypt cùng key policy/grant phù hợp.

**Câu 30.** AWSCURRENT là gì?  
**Đáp án:** Staging label thường chỉ version secret hiện hành.

**Câu 31.** Cache secret vô thời hạn có rủi ro gì?  
**Đáp án:** Ứng dụng có thể tiếp tục dùng credential cũ sau rotation.

**Câu 32.** VPC endpoint có bỏ qua IAM authorization không?  
**Đáp án:** Không; endpoint chỉ cung cấp network path, IAM/resource/KMS policies vẫn áp dụng.

**Câu 33.** SDK service exception và client exception khác gì?  
**Đáp án:** Service exception phản ánh lỗi trả về từ AWS service; client exception thường liên quan transport/config/network.

**Câu 34.** Có nên retry AccessDenied vô hạn không?  
**Đáp án:** Không; sửa permission/policy hoặc cấu hình trước.

**Câu 35.** Vì sao SQS/SNS payload cần business event ID?  
**Đáp án:** Để consumer deduplicate và xử lý idempotent khi publish/retry có thể tạo duplicate.

## 27. Tổng kết và checklist production

### 27.1. Ghi nhớ vai trò từng dịch vụ

- **SQS:** queue pull-based, buffer backlog, visibility timeout, retries và DLQ.
- **SNS:** pub/sub fan-out, subscriptions, filter policy và FIFO topics khi cần ordering theo group.
- **STS:** xác định caller identity và cấp temporary credentials qua AssumeRole.
- **Secrets Manager:** lưu, phân phối, mã hóa và rotation secrets.

### 27.2. Checklist trước production

1. Dùng **AWS SDK for Java 2.x BOM** và các modules cùng release version đã được phê duyệt.
2. Tạo clients singleton, thread-safe, đúng Region và quản lý shutdown.
3. Dùng IAM roles/default credentials provider chain; không hard-code long-term access keys.
4. Đặt API attempt/call timeouts phù hợp; kiểm tra HTTP read timeout với SQS long polling.
5. Với SQS, cấu hình visibility timeout, long polling, DLQ và redrive policy.
6. Thiết kế consumer idempotency, operation ID và transaction boundaries trước khi DeleteMessage.
7. Với batch APIs, xử lý partial failures và chỉ retry entries lỗi.
8. Với FIFO, chọn MessageGroupId theo aggregate và không nhầm deduplication với business exactly-once.
9. Với SNS, kiểm tra topic ARN/Region, subscription status, filter policy và queue policy.
10. Với STS, review identity policy, trust policy, ExternalId/conditions, session duration và role chaining.
11. Với Secrets Manager, giới hạn GetSecretValue theo secret ARN, KMS decrypt và cross-account policies.
12. Đặt cache TTL/refresh strategy phù hợp rotation; phối hợp connection pool và không log secret.
13. Dùng VPC endpoints/private DNS/endpoint policies nếu workload chạy private subnet.
14. Theo dõi CloudWatch metrics, CloudTrail audit, AWS request IDs và application business outcomes.
15. Test AccessDenied, throttling, timeout, duplicate delivery, DLQ, role expiration và secret rotation trong sandbox.
16. Dự toán SQS/SNS/Secrets Manager/CloudWatch/KMS/VPC endpoint costs theo Region.

**Kết luận:** AWS SDK for Java 2.x giúp ứng dụng gọi SQS, SNS, STS và Secrets Manager qua API thống nhất, nhưng vận hành an toàn phụ thuộc vào cách quản lý credentials, Region, IAM/resource policies, retries và message semantics. Hãy coi SQS/SNS là delivery systems có thể retry, STS là nguồn temporary identity và Secrets Manager là nguồn credential có rotation. Khi kết hợp idempotency, cache refresh, observability và integration tests, Java services có thể tích hợp AWS bền vững mà không để lộ secrets hoặc tạo side effects trùng lặp.

### Tài liệu AWS chính thức

- [AWS SDK for Java 2.x Developer Guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html) — cài đặt, credentials, Region, clients và retry.
- [Set up the AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup.html) — Maven/Gradle và BOM.
- [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — cách SDK tìm credentials.
- [Configure service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html) — HTTP client, timeouts và lifecycle.
- [Amazon SQS Java examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sqs.html) — gửi, nhận và quản lý queue.
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) — xử lý message và duplicate delivery.
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html) — redrive policy và DLQ.
- [SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html) — ordering và deduplication.
- [Amazon SNS Java examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sns.html) — publish và subscription.
- [SNS FIFO topics](https://docs.aws.amazon.com/sns/latest/dg/fifo-topics.html) — ordering và deduplication.
- [SNS message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html) — subscription filter policies.
- [SNS to SQS fan-out](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html) — queue policies và delivery.
- [AWS STS AssumeRole](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — temporary credentials và role chaining.
- [STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — caller identity.
- [AWS SDK for Java 2.x STS credentials provider](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html) — assume-role provider.
- [Secrets Manager Java retrieval](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_java.html) — lấy secret từ Java.
- [Secrets Manager caching](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html) — cache secrets trong Java.
- [Secrets Manager rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html) — rotation lifecycle và staging labels.
- [Secrets Manager IAM policies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_iam-policies.html) — identity/resource permissions.


