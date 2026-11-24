# LocalStack cho những API AWS được hỗ trợ

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua Spring Cloud và SDK tương ứng. Với nhánh AWS, ứng dụng có thể gọi S3 để lưu file, SQS/SNS để trao đổi message, DynamoDB để lưu dữ liệu hoặc Secrets Manager để đọc cấu hình nhạy cảm. Nếu mọi lần kiểm thử tích hợp đều cần AWS account, resource thật và chi phí cloud, vòng lặp phát triển sẽ chậm và khó chạy ổn định trên CI.

**LocalStack** cung cấp môi trường giả lập nhiều AWS service chạy trên máy phát triển hoặc trong container. Ứng dụng vẫn dùng AWS SDK for Java và Spring Cloud AWS; endpoint của client được chuyển sang LocalStack. **Testcontainers** giúp khởi động LocalStack theo vòng đời JUnit test, cấp endpoint/port động và dọn container sau khi test hoàn tất.

Tên bài nhấn mạnh một giới hạn quan trọng: LocalStack chỉ giả lập những service và API operation được hỗ trợ ở phiên bản/gói đang dùng. Một service xuất hiện trong danh sách không có nghĩa mọi operation, semantics, IAM behavior, quota và đặc tính vận hành của AWS thật đều giống hệt.

Sau bài này, bạn có thể:

- Xác định operation AWS nào được LocalStack hỗ trợ trước khi thiết kế test.
- Kết nối Spring Boot/AWS SDK for Java 2.x tới LocalStack qua endpoint override.
- Dùng Testcontainers và JUnit 5 để quản lý LocalStack container.
- Kiểm thử luồng S3, SQS, SNS, DynamoDB và Secrets Manager ở mức API được hỗ trợ.
- Tách cấu hình local test khỏi cấu hình AWS production.
- Quản lý resource, dữ liệu và container để test độc lập, lặp lại được.
- Nhận biết những gì LocalStack không chứng minh được và bổ sung smoke test trên AWS thật khi cần.

## 2. LocalStack và phạm vi kiểm thử

LocalStack là cloud emulator. Nó nhận request theo AWS API endpoint và mô phỏng hành vi của một số AWS service để ứng dụng có thể chạy cục bộ mà không cần gọi trực tiếp tới AWS.

~~~mermaid
flowchart LR
    T[JUnit 5 integration test] --> A[Spring Boot application]
    A --> B[AWS SDK v2 / Spring Cloud AWS]
    B -->|endpoint override| L[(LocalStack container)]
    L --> S3[S3 API]
    L --> SQS[SQS API]
    L --> SNS[SNS API]
    L --> DDB[DynamoDB API]
    L --> SM[Secrets Manager API]
~~~

Trong test, ứng dụng vẫn chạy cùng code path dùng AWS SDK. Điểm khác biệt chính là client được cấu hình endpoint của LocalStack, region test và credentials giả lập. LocalStack xử lý request rồi trả response theo implementation của nó.

LocalStack phù hợp để kiểm tra:

- AWS SDK được cấu hình đúng endpoint, region và credentials hay chưa.
- Ứng dụng tạo bucket/queue/table/secret và gọi API được hỗ trợ.
- Mapping request/response, serialization và error handling.
- Luồng publish/consume message hoặc upload/download object.
- Một số tương tác giữa service, ví dụ S3 notification hoặc SNS fan-out sang SQS khi integration tương ứng được hỗ trợ.

LocalStack không tự chứng minh ứng dụng có thể vận hành trên AWS production. Nó không thay thế kiểm thử network, IAM role thật, KMS key policy, quota, service limit, latency, throughput, failure mode và các semantics chỉ tồn tại trên dịch vụ managed thực tế.

## 3. Kiểm tra API coverage trước khi viết test

Trước khi chọn LocalStack, hãy xác định chính xác API operation mà code gọi. Đừng chỉ kiểm tra tên service.

Ví dụ, luồng upload tài liệu có thể gọi:

- S3: CreateBucket, PutObject, GetObject, HeadObject, DeleteObject.
- SQS: CreateQueue, SendMessage, ReceiveMessage, DeleteMessage.
- SNS: CreateTopic, Subscribe, Publish.
- DynamoDB: CreateTable, PutItem, GetItem, Query, UpdateItem.
- Secrets Manager: CreateSecret, GetSecretValue, PutSecretValue.

Tra từng operation trong API Coverage của service trên tài liệu LocalStack. Bảng coverage thể hiện operation đã implement, operation chưa implement và gói nào có quyền sử dụng. Coverage có thể thay đổi theo phiên bản, edition và license; hãy kiểm tra lại tại thời điểm nâng version.

<text>Ảnh chụp tài liệu tại thời điểm biên soạn (24-11-2026):</text>

| Service | Operation được ghi nhận | Lưu ý |
|---|---:|---|
| S3 | 100/116 | S3 Control có bảng coverage riêng, 31/97 |
| SQS | 23/23 | Có giới hạn riêng về thay đổi MessageRetentionPeriod |
| SNS | 36/42 | Filter policy không hỗ trợ toán tử cidr |
| DynamoDB | 47/58 | Một số API import/export và một số global-table operation chưa hỗ trợ |
| Secrets Manager | 22/23 | StopReplicationToReplica chưa implement |

Các con số này là snapshot của tài liệu, không phải cam kết cố định. Hãy mở trang coverage mới nhất và xác nhận plan/license của môi trường đang dùng trước khi dựa vào một operation.

### 3.1. Lập ma trận API cho use case

Trước khi viết test, ghi lại:

| Use case | Service | Operation cần gọi | Coverage | Kết quả |
|---|---|---|---|---|
| Upload file | S3 | CreateBucket, PutObject, GetObject | Kiểm tra trang S3 | Dùng LocalStack nếu đủ |
| Gửi job | SQS | CreateQueue, SendMessage, ReceiveMessage | Kiểm tra trang SQS | Dùng LocalStack nếu đủ |
| Fan-out event | SNS/SQS | CreateTopic, Subscribe, Publish | Kiểm tra cả hai service | Test luồng end-to-end |
| Lưu bản ghi | DynamoDB | CreateTable, PutItem, Query | Kiểm tra trang DynamoDB | Dùng LocalStack nếu đủ |
| Đọc secret | Secrets Manager | CreateSecret, GetSecretValue | Kiểm tra trang Secrets Manager | Dùng LocalStack nếu đủ |

Nếu một operation chưa được implement hoặc bị giới hạn bởi plan, không viết test giả định operation đó hoạt động. Chọn một trong các hướng: mock adapter cho unit test, dùng service thật trong một integration test riêng hoặc thay đổi phạm vi test để chỉ kiểm tra API có hỗ trợ.

## 4. Vị trí của LocalStack trong chiến lược kiểm thử

Một ứng dụng Spring Boot nên có nhiều lớp test với mục tiêu khác nhau:

| Loại test | Hạ tầng | Điều cần chứng minh |
|---|---|---|
| Unit test | Mock/fake | Business logic và nhánh xử lý lỗi |
| Slice test | Spring context rút gọn | Wiring, serialization hoặc repository boundary |
| LocalStack integration test | AWS API được giả lập | AWS SDK/client và luồng API được hỗ trợ |
| AWS smoke/contract test | AWS account test riêng | IAM, policy, encryption, network và semantics thật |
| Production monitoring | AWS production | Hành vi vận hành, latency, error rate và quota |

Không cần khởi động LocalStack cho mọi unit test. Hãy dùng nó khi cần xác minh ứng dụng và AWS API thực sự trao đổi với nhau. Những logic thuần như validate file name, tính phí hoặc mapping domain object nên được test nhanh bằng unit test.

Một pipeline phổ biến:

~~~text
Pull request
  -> Unit tests
  -> Spring integration tests + LocalStack
  -> Build/package
  -> AWS smoke tests trên account test (khi thay đổi cloud contract)
  -> Deploy
  -> Production monitoring
~~~

## 5. Dependency cho Spring Boot và Testcontainers

Với Spring Cloud AWS, dùng BOM tương thích với Spring Boot đang chạy. Theo compatibility matrix hiện hành, dòng Spring Cloud AWS 3.4.x phù hợp Spring Boot 3.5.x; dòng 4.x dành cho Spring Boot 4.0.x. Không ghép version tùy ý giữa Spring Boot, Spring Cloud AWS và AWS SDK.

Ví dụ Maven cho một ứng dụng dùng S3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>3.4.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-localstack</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ trên dùng Spring Cloud AWS 3.4.2 cho Spring Boot 3.5 và Testcontainers 2.0.5. Nếu dự án dùng Spring Boot 4, chọn dòng Spring Cloud AWS 4.x tương thích. Từ Testcontainers 2.x, artifact module có tiền tố testcontainers- và package Java của module được chuyển sang namespace module. Nếu dự án còn dùng Testcontainers 1.x, dependency/package có thể khác.

Nếu test SQS/SNS/DynamoDB/Secrets Manager, thêm starter hoặc AWS SDK module tương ứng. Chỉ thêm những client cần thiết cho ứng dụng.

## 6. Chạy LocalStack độc lập để phát triển

LocalStack có thể chạy qua Docker hoặc Docker Compose. Gateway API mặc định thường dùng port 4566. Ví dụ cấu hình Compose tối giản:

~~~yaml
services:
  localstack:
    image: localstack/localstack:latest
    ports:
      - "4566:4566"
    environment:
      SERVICES: s3,sqs,sns,dynamodb,secretsmanager
      AWS_DEFAULT_REGION: us-east-1
      LOCALSTACK_AUTH_TOKEN: $LOCALSTACK_AUTH_TOKEN
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
~~~

Trong môi trường thực tế, pin image theo version hoặc digest đã được kiểm thử thay vì phụ thuộc tag latest. Giữ auth token trong secret store hoặc biến môi trường của máy/CI; không commit token vào file Compose.

Từ ngày 23-03-2026, image LocalStack được Testcontainers hướng dẫn sử dụng yêu cầu biến môi trường LOCALSTACK_AUTH_TOKEN để khởi động. Nếu thiếu token, container có thể dừng ngay khi start. Hãy kiểm tra yêu cầu authentication của image và license/plan hiện tại.

Để kiểm tra nhanh endpoint, có thể dùng AWS CLI với endpoint LocalStack:

~~~bash
aws --endpoint-url=http://localhost:4566 s3api list-buckets
aws --endpoint-url=http://localhost:4566 sqs list-queues
~~~

LocalStack yêu cầu AWS credentials và region cho các API operation như SDK AWS. Trong local test có thể dùng credentials giả lập như test/test; tuyệt đối không dùng access key production.

## 7. Quản lý vòng đời container bằng Testcontainers

Testcontainers khởi động container trước test và dọn nó sau khi test kết thúc. Cách này giúp tránh phụ thuộc vào một LocalStack server chạy sẵn trên máy developer hoặc một port cố định trên CI.

Ví dụ JUnit 5 với Testcontainers 2.0.5:

~~~java
import org.testcontainers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class LocalStackContainerTest {

    private static String requiredAuthToken() {
        String token = System.getenv("LOCALSTACK_AUTH_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "Set LOCALSTACK_AUTH_TOKEN before running LocalStack tests");
        }
        return token;
    }

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse(
                            System.getProperty(
                                    "localstack.image",
                                    "localstack/localstack:latest")))
                    .withServices("s3", "sqs")
                    .withEnv("LOCALSTACK_AUTH_TOKEN", requiredAuthToken());
}
~~~

Đặt image version cố định trong cấu hình build/CI, ví dụ truyền system property localstack.image tới version đã được team xác nhận. Ví dụ trên dùng latest làm fallback để minh họa cách truyền image; không nên để tag mutable làm mặc định trong pipeline release.

Các điểm cần nhớ:

- Testcontainers cần Docker hoặc container runtime được hỗ trợ đang hoạt động.
- Port được map động; lấy endpoint từ container thay vì hardcode localhost:4566.
- withServices chỉ bật các service cần cho test, giúp giảm thời gian khởi động và tài nguyên.
- Static @Container được chia sẻ giữa các test method trong class; dữ liệu service vẫn tồn tại giữa các method cho tới khi container dừng.
- Instance @Container tạo lifecycle riêng theo từng test method, đổi lại thời gian chạy sẽ tăng.
- Testcontainers JUnit 5 extension được kiểm thử chủ yếu với test chạy tuần tự; nếu bật parallel execution, phải thiết kế cô lập resource và kiểm tra giới hạn của extension.

## 8. Kết nối Spring Boot tới endpoint LocalStack

Spring Cloud AWS có thể tự cấu hình S3Client từ starter. Dùng @DynamicPropertySource để truyền endpoint, region và credentials mà Testcontainers cấp:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void awsProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.cloud.aws.s3.endpoint",
            () -> LOCALSTACK.getEndpoint().toString());
    registry.add(
            "spring.cloud.aws.region.static",
            LOCALSTACK::getRegion);
    registry.add(
            "spring.cloud.aws.credentials.access-key",
            LOCALSTACK::getAccessKey);
    registry.add(
            "spring.cloud.aws.credentials.secret-key",
            LOCALSTACK::getSecretKey);
    registry.add(
            "spring.cloud.aws.s3.path-style-access-enabled",
            () -> true);
}
~~~

Với SQS hoặc SNS, đặt endpoint tương ứng, ví dụ spring.cloud.aws.sqs.endpoint hoặc spring.cloud.aws.sns.endpoint. Có thể dùng spring.cloud.aws.endpoint làm endpoint chung nếu phiên bản Spring Cloud AWS đang dùng hỗ trợ cấu hình chung đó; cấu hình endpoint theo service giúp tránh vô tình đổi endpoint của client khác.

Trong application.yml production, không đặt endpoint LocalStack và không ghi credentials giả lập. Cấu hình test được nạp từ @DynamicPropertySource hoặc profile test để tránh ứng dụng production gọi nhầm endpoint giả lập.

### 8.1. Nếu tự tạo AWS SDK client

Khi không dùng Spring Cloud AWS starter hoặc cần kiểm soát client riêng, tạo AWS SDK for Java 2.x client trực tiếp:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(
                                LOCALSTACK.getAccessKey(),
                                LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();
~~~

Endpoint override, region và credentials đều cần thiết để request được ký và gửi đúng nơi. Endpoint từ getEndpoint() phù hợp cho test chạy trên host. Nếu application cũng chạy trong một container Docker khác, dùng Docker network và địa chỉ nội bộ phù hợp; endpoint host-mapped không nhất thiết truy cập được từ container ngang hàng.

## 9. Kiểm thử S3: tạo bucket, upload và download

S3 là ví dụ phù hợp để kiểm tra luồng lưu file cơ bản. Với Spring Cloud AWS S3 starter, Spring context cung cấp S3Client bean. Test nên tạo bucket riêng, upload object, tải lại và so sánh nội dung.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Testcontainers
@SpringBootTest
class S3LocalStackIT {
    private static String authToken() {
        String token = System.getenv("LOCALSTACK_AUTH_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException("LOCALSTACK_AUTH_TOKEN is required");
        }
        return token;
    }

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse("localstack/localstack:latest"))
                    .withServices("s3")
                    .withEnv("LOCALSTACK_AUTH_TOKEN", authToken());

    @DynamicPropertySource
    static void awsProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.aws.s3.endpoint",
                () -> LOCALSTACK.getEndpoint().toString());
        registry.add("spring.cloud.aws.region.static", LOCALSTACK::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key",
                LOCALSTACK::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key",
                LOCALSTACK::getSecretKey);
        registry.add("spring.cloud.aws.s3.path-style-access-enabled",
                () -> true);
    }

    @Autowired
    S3Client s3Client;

    @Test
    void uploadsAndDownloadsObject() {
        String bucket = "it-" + UUID.randomUUID().toString();
        String key = "documents/example.txt";
        String expected = "LocalStack integration test";

        s3Client.createBucket(CreateBucketRequest.builder()
                .bucket(bucket)
                .build());

        try {
            s3Client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType("text/plain")
                            .build(),
                    RequestBody.fromString(expected));

            String actual = s3Client.getObjectAsBytes(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build())
                    .asUtf8String();

            assertEquals(expected, actual);
        } finally {
            s3Client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
            s3Client.deleteBucket(DeleteBucketRequest.builder()
                    .bucket(bucket)
                    .build());
        }
    }
}
~~~

Ví dụ tập trung vào API CreateBucket, PutObject, GetObject, DeleteObject và DeleteBucket; hãy xác nhận từng operation trong API Coverage của phiên bản LocalStack đang pin. Nếu ứng dụng dùng S3Template hoặc S3Resource, hãy inject abstraction đó và kiểm thử qua API tương tự để xác minh cả wiring Spring Cloud AWS lẫn adapter nghiệp vụ.

## 10. Kiểm thử SQS: gửi, nhận và xác nhận message

SQS giúp kiểm tra producer/consumer boundary. Có thể dùng Spring Cloud AWS SqsTemplate hoặc AWS SDK SqsClient. Một test ở mức SDK có thể thực hiện:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.UUID;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.CreateQueueRequest;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.DeleteQueueRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

SqsClient sqs = SqsClient.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                        LOCALSTACK.getAccessKey(),
                        LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();

String queueUrl = sqs.createQueue(CreateQueueRequest.builder()
        .queueName("it-" + UUID.randomUUID())
        .build()).queueUrl();

try {
    sqs.sendMessage(SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody("document-42")
            .build());

    var messages = sqs.receiveMessage(ReceiveMessageRequest.builder()
            .queueUrl(queueUrl)
            .waitTimeSeconds(2)
            .maxNumberOfMessages(1)
            .build()).messages();

    assertEquals("document-42", messages.get(0).body());

    sqs.deleteMessage(DeleteMessageRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(messages.get(0).receiptHandle())
            .build());
} finally {
    sqs.deleteQueue(DeleteQueueRequest.builder()
            .queueUrl(queueUrl)
            .build());
    sqs.close();
}
~~~

Đoạn code minh họa API flow; trong test thực tế cần xử lý trường hợp receive trả danh sách rỗng bằng Awaitility hoặc polling có timeout, thay vì truy cập phần tử đầu tiên ngay lập tức. Nếu kiểm thử listener bất đồng bộ của Spring Cloud AWS, chờ assertion theo trạng thái nghiệp vụ và dùng timeout hữu hạn.

Đừng xem SendMessage thành công là bằng chứng consumer đã xử lý message. Hãy kiểm tra kết quả sau khi listener hoàn tất và xác minh acknowledgement/delete theo semantics mà ứng dụng sử dụng.

## 11. Kiểm thử SNS và luồng SNS → SQS

SNS dùng publish/subscribe; SQS giữ message để consumer xử lý sau. Một integration test có thể:

1. Tạo SNS topic.
2. Tạo SQS queue.
3. Đăng ký queue làm subscription của topic.
4. Cấu hình queue policy cho phép SNS gửi message.
5. Publish một event.
6. Nhận message từ SQS và xác minh body/attributes.

LocalStack hỗ trợ nhiều API của SNS, nhưng không phải toàn bộ. Ví dụ, tài liệu hiện hành ghi nhận một số API SMS sandbox chưa implement và toán tử cidr trong filter policy không được hỗ trợ. Nếu ứng dụng dựa vào các tính năng này, cần kiểm tra coverage và test trên AWS thật.

Khi kiểm tra notification delivery, hãy xác minh cả cấu hình subscription và queue policy. Chỉ kiểm tra SNS Publish trả MessageId chưa chứng minh message đã tới subscriber.

## 12. Kiểm thử DynamoDB

LocalStack hỗ trợ một phần DynamoDB API, phù hợp để kiểm tra thao tác cơ bản:

- CreateTable và DescribeTable.
- PutItem, GetItem, UpdateItem, DeleteItem.
- Query và Scan trong các use case được hỗ trợ.
- Một số transaction operation như TransactWriteItems và TransactGetItems.

Ví dụ client:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
        .endpointOverride(LOCALSTACK.getEndpoint())
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                        LOCALSTACK.getAccessKey(),
                        LOCALSTACK.getSecretKey())))
        .region(Region.of(LOCALSTACK.getRegion()))
        .build();
~~~

Trong test, tạo table có tên duy nhất và schema đúng với ứng dụng, ghi một item rồi đọc lại bằng partition key. Sau test, xóa table hoặc dùng namespace/table name riêng cho test suite.

Không kết luận LocalStack đã xác minh mọi DynamoDB behavior. Tài liệu hiện hành có ghi các giới hạn với global tables, replication và một số import/export API. Ví dụ global tables Version 2019 được hỗ trợ, nhưng legacy Version 2017 không được hỗ trợ; DynamoDB Streams trên replicated tables và một số batch operation trên replicated tables có giới hạn.

Nếu ứng dụng phụ thuộc transaction isolation, conditional write phức tạp, TTL timing, global-table conflict resolution hoặc capacity behavior, cần bổ sung kiểm thử AWS thật.

## 13. Kiểm thử Secrets Manager, Parameter Store và KMS

LocalStack có thể hỗ trợ một số API của Secrets Manager và Systems Manager Parameter Store. Với Secrets Manager, luồng cơ bản có thể tạo secret, đọc SecretString, cập nhật version và xóa secret theo API được hỗ trợ.

Ví dụ đọc secret bằng AWS SDK v2:

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;

String value = secretsManager.getSecretValue(
        GetSecretValueRequest.builder()
                .secretId("integration-test/database")
                .build())
        .secretString();
~~~

Trong test, chỉ dùng secret giả lập. Không sao chép secret production vào LocalStack fixture hoặc log. Tạo secret với tên test riêng, đọc giá trị và dọn resource sau test.

KMS và encryption cần được đánh giá riêng. LocalStack có thể mô phỏng một số KMS API và luồng tích hợp, nhưng việc test được một Encrypt/Decrypt operation không chứng minh IAM key policy, grant, rotation, HSM-backed security hoặc encryption behavior của AWS production. Những yêu cầu bảo mật quan trọng phải được kiểm thử trên AWS account test với key và policy riêng.

## 14. Credentials, region và cô lập cấu hình

AWS SDK cần credentials và region để ký request. Trong LocalStack, dùng credentials giả lập do container cung cấp:

- Access key: LOCALSTACK.getAccessKey().
- Secret key: LOCALSTACK.getSecretKey().
- Region: LOCALSTACK.getRegion().
- Endpoint: LOCALSTACK.getEndpoint().

Không để AWS SDK vô tình lấy credentials production từ máy developer hoặc CI. Cấu hình endpoint override rõ ràng trong test để request không thể đi tới AWS thật.

Ở production:

- Dùng IAM role, task role, IRSA/EKS Pod Identity hoặc workload identity phù hợp.
- Không dùng static test credentials.
- Không đặt endpoint LocalStack trong profile production.
- Không cấp quyền AWS thật cho test container.

LocalStack hỗ trợ một số chức năng IAM và policy theo coverage/plan, nhưng test permission enforcement trên emulator không thay thế xác minh IAM role, resource policy, SCP, permission boundary và KMS key policy trong AWS thật.

## 15. Những khác biệt cần biết so với AWS thật

LocalStack mô phỏng API và một phần behavior của service; AWS thật là hạ tầng managed phân tán với nhiều điều kiện vận hành khác.

| Khía cạnh | LocalStack | AWS thật |
|---|---|---|
| API operation | Chỉ operation được implement trong coverage | Theo API contract của AWS service |
| IAM | Mức hỗ trợ tùy service/feature/plan | IAM, resource policy, SCP, role và policy evaluation đầy đủ theo AWS |
| Event delivery | Mô phỏng luồng tích hợp được hỗ trợ | Có delivery retry, filter, quota và behavior theo dịch vụ |
| Consistency | Có thể khác timing/consistency thực tế | Theo semantics từng AWS service |
| Network | Container/network cục bộ | VPC, subnet, endpoint, DNS, NAT, firewall và routing |
| Quota/throttling | Không phản ánh đầy đủ quota production | Service quota và throttling thật |
| Encryption | Một số API/flow được mô phỏng | KMS, key policy, rotation, grant và dịch vụ managed thật |
| Performance | Phụ thuộc máy chạy container | Phụ thuộc region, capacity và service managed |
| Observability | Log/container diagnostics của emulator | CloudWatch, X-Ray, CloudTrail và metrics native |

Các khác biệt này không làm LocalStack kém hữu ích. Chúng xác định đúng phạm vi mà một test local có thể chứng minh.

## 16. Quản lý dữ liệu và cleanup

Testcontainers có thể chia sẻ một container giữa nhiều method. Resource được tạo trong LocalStack không tự mất sau mỗi method nếu container vẫn chạy.

Các nguyên tắc cô lập:

- Tạo bucket/table/queue/secret với suffix UUID hoặc test run ID.
- Xóa object trước khi xóa bucket.
- Xóa message/queue hoặc purge queue sau test khi phù hợp.
- Xóa subscription trước topic nếu cần.
- Không để test phụ thuộc resource do test khác tạo.
- Dùng try/finally hoặc @AfterEach để cleanup kể cả khi assertion thất bại.

LocalStack có persistence và snapshot feature tùy cấu hình/plan. Trong integration test thông thường, ưu tiên container mới để state sạch. Nếu bật persistence hoặc reusable container nhằm tăng tốc, phải có chiến lược namespace/cleanup rõ ràng và không để state cũ làm test pass giả.

Với DynamoDB, tài liệu LocalStack lưu ý chế độ DYNAMODB_IN_MEMORY có thể làm dữ liệu mất khi container dừng dù persistence được bật. Không dùng chế độ này nếu test cần dữ liệu tồn tại qua restart.

## 17. Kiểm thử bất đồng bộ và eventual consistency

SQS/SNS và các event-driven workflow thường không hoàn tất ngay khi producer gửi message. Test nên chờ điều kiện nghiệp vụ bằng timeout hữu hạn.

Ví dụ với Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
    .atMost(10, SECONDS)
    .untilAsserted(() -> {
        var result = jobRepository.findById(jobId).orElseThrow();
        assertEquals(JobStatus.COMPLETED, result.status());
    });
~~~

Tránh Thread.sleep() cố định vì test có thể chậm không cần thiết hoặc flaky khi CI tải cao. Dùng polling interval hợp lý và timeout đủ lớn để phát hiện lỗi nhưng không treo pipeline lâu.

Với consumer, xác minh:

- Message được nhận và handler được gọi.
- Business side effect được ghi bền vững.
- Message được ack/delete sau khi xử lý thành công.
- Message lỗi được retry hoặc dead-letter theo cấu hình mà LocalStack hỗ trợ.
- Consumer idempotent khi message được giao lại.

Không kết luận semantics retry, visibility timeout, FIFO ordering hoặc DLQ production đã đúng chỉ dựa trên một happy-path test.

## 18. Chạy LocalStack trong CI

Testcontainers thường chạy LocalStack trong Docker daemon của CI runner. Pipeline cần:

1. Cài đặt Docker/container runtime được Testcontainers hỗ trợ.
2. Cấp LOCALSTACK_AUTH_TOKEN dưới dạng CI secret nếu image yêu cầu.
3. Pin LocalStack image version/digest và Testcontainers version.
4. Chạy integration test với endpoint lấy từ Testcontainers.
5. Lưu log container khi test fail để hỗ trợ chẩn đoán.
6. Cho Testcontainers dọn container và network sau test.

Không hardcode port 4566 trên host trong test. Testcontainers map port ngẫu nhiên để tránh xung đột khi nhiều job CI chạy song song.

Ví dụ GitHub Actions ở mức khái niệm:

~~~yaml
jobs:
  integration-test:
    runs-on: ubuntu-latest
    env:
      LOCALSTACK_AUTH_TOKEN: "inject this value from the CI secret store"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - name: Run integration tests
        run: ./mvnw -B verify -Pintegration
~~~

Thay giá trị minh họa của LOCALSTACK_AUTH_TOKEN bằng secret binding của CI platform. Không ghi token vào repository, command output hoặc test report. Không cấp AWS production credentials cho job này. Nếu cần kiểm thử AWS thật, tạo một job riêng với account test, role giới hạn và resource có tên riêng.

## 19. Troubleshooting và bài tập thực hành

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Container không khởi động | Thiếu LOCALSTACK_AUTH_TOKEN, Docker không sẵn sàng hoặc image không tương thích | Kiểm tra token, Docker daemon và log container |
| SDK gọi nhầm AWS thật | Thiếu endpoint override hoặc profile production bị nạp | Xác minh endpoint, region và profile test |
| Signature/region error | Region hoặc credentials không khớp | Lấy region/credentials từ LocalStackContainer |
| S3 bucket request lỗi host-style | S3 endpoint/virtual-host routing không phù hợp | Dùng endpoint từ container và bật path-style access khi cần |
| SQS receive trả rỗng | Test đọc quá sớm hoặc queue URL sai | Poll có timeout, xác minh queue và endpoint |
| SNS publish thành công nhưng queue không có message | Subscription hoặc queue policy chưa đúng | Kiểm tra protocol, subscription confirmation và policy |
| DynamoDB operation không được hỗ trợ | API nằm ngoài coverage hoặc giới hạn plan | Kiểm tra operation-level coverage |
| Test pass riêng nhưng fail cả suite | Dữ liệu/container state dùng chung | Dùng resource name duy nhất và cleanup |
| Test chạy song song bị flaky | Shared LocalStack/container/resource collision | Tách namespace, giới hạn parallel hoặc container lifecycle |
| LocalStack pass nhưng AWS fail | Khác biệt IAM, quota, consistency, encryption hoặc network | Bổ sung AWS smoke/contract test |

### Bài tập A — S3

Viết integration test cho upload/download file bằng S3Client được Spring Cloud AWS auto-configure. Tạo bucket duy nhất cho test, kiểm tra content type và nội dung file, sau đó cleanup object/bucket.

### Bài tập B — SQS

Tạo queue, gửi message và xác minh consumer cập nhật trạng thái job. Dùng Awaitility thay cho sleep; kiểm tra message không bị xóa trước khi business transaction hoàn tất.

### Bài tập C — SNS/SQS

Tạo topic và queue, subscribe queue vào topic, publish event và xác minh message tới queue. Kiểm tra policy và giới hạn filter policy theo API coverage.

### Bài tập D — DynamoDB

Tạo table với partition key, ghi item, đọc item và kiểm tra conditional update. Ghi lại operation nào đã được LocalStack hỗ trợ và operation nào cần test trên AWS.

### Bài tập E — Secrets Manager

Tạo secret test, đọc SecretString và xóa secret. Bảo đảm giá trị không xuất hiện trong log hoặc test report.

### Câu hỏi tự kiểm tra

1. **LocalStack là gì?** Một emulator chạy cục bộ cho một tập AWS service/API operation.
2. **Vì sao phải kiểm tra operation-level API coverage?** Vì service có thể được hỗ trợ nhưng một số API operation vẫn chưa implement hoặc bị giới hạn theo plan.
3. **Testcontainers giúp gì?** Quản lý lifecycle container, port động và cleanup theo vòng đời test.
4. **Testcontainers 2.0.5 dùng artifact LocalStack nào?** org.testcontainers:testcontainers-localstack.
5. **LocalStack container cần biến môi trường nào từ 23-03-2026 theo hướng dẫn Testcontainers?** LOCALSTACK_AUTH_TOKEN.
6. **Vì sao AWS SDK cần endpoint override?** Để request được gửi tới LocalStack thay vì AWS endpoint thật.
7. **Có nên dùng AWS production credentials trong test LocalStack không?** Không; dùng credentials giả lập từ container.
8. **SQS SendMessage thành công có chứng minh job hoàn tất không?** Không; phải xác minh consumer xử lý và cập nhật trạng thái nghiệp vụ.
9. **LocalStack có thay thế AWS smoke test không?** Không; IAM, KMS, quota, network, consistency và managed behavior cần kiểm tra riêng.
10. **Làm sao tránh test phụ thuộc state cũ?** Resource name duy nhất, cleanup và container lifecycle cô lập.

## 20. Tổng kết

LocalStack là công cụ hữu ích để kiểm thử tích hợp Spring Boot với những AWS API operation mà emulator hỗ trợ. Kết hợp AWS SDK for Java 2.x, Spring Cloud AWS, Testcontainers và JUnit 5 giúp test tạo resource, gọi API, xác minh dữ liệu và chạy được trong CI mà không cần kết nối tới AWS production.

Trước khi viết test, hãy tra API Coverage theo từng operation và plan. Dùng endpoint/region/credentials từ LocalStackContainer, không hardcode port, không dùng production credentials và dọn resource sau test. Với luồng bất đồng bộ, chờ kết quả nghiệp vụ bằng timeout; không coi việc publish message là hoàn tất công việc.

LocalStack giúp phát hiện lỗi wiring, request mapping và luồng tích hợp sớm. AWS smoke/contract test vẫn cần thiết cho IAM, resource policy, KMS, quota, network, eventual consistency, performance và behavior của dịch vụ managed. Dùng đúng phạm vi cho từng lớp test để có vòng lặp phát triển nhanh nhưng vẫn giữ độ tin cậy khi triển khai cloud thật.

### Tài liệu tham khảo chính thức

- [LocalStack — Getting Started](https://docs.localstack.cloud/aws/getting-started/)
- [LocalStack — AWS API Coverage](https://docs.localstack.cloud/aws/services/)
- [LocalStack — S3 API Coverage and Limitations](https://docs.localstack.cloud/aws/services/s3/)
- [LocalStack — SQS API Coverage and Limitations](https://docs.localstack.cloud/aws/services/sqs/)
- [LocalStack — SNS API Coverage and Limitations](https://docs.localstack.cloud/aws/services/sns/)
- [LocalStack — DynamoDB API Coverage and Limitations](https://docs.localstack.cloud/aws/services/dynamodb/)
- [LocalStack — Secrets Manager API Coverage](https://docs.localstack.cloud/aws/services/secretsmanager/)
- [LocalStack — AWS SDK for Java](https://docs.localstack.cloud/aws/connecting/aws-sdks/java/)
- [LocalStack — Testcontainers Integration](https://docs.localstack.cloud/aws/customization/integrations/testing/testcontainers/)
- [Testcontainers for Java — LocalStack Module](https://java.testcontainers.org/modules/localstack/)
- [Testcontainers for Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Spring Cloud AWS — Compatibility Matrix and Supported Integrations](https://github.com/awspring/spring-cloud-aws)
- [Spring Cloud AWS — S3 Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html#s3-integration)
