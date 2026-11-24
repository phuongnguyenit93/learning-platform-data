# Thiết lập kết nối AWS giả lập bằng LocalStack

## 1. Vì sao cần AWS giả lập khi học Spring Boot và Spring Cloud AWS?

Một dịch vụ Spring Boot có thể dùng Amazon S3 để lưu tệp, Amazon SQS để trao đổi thông điệp, AWS Secrets Manager để đọc secret và DynamoDB để lưu dữ liệu. Nếu mỗi lần phát triển hay chạy kiểm thử đều gọi vào AWS thật, nhóm phải xử lý thêm nhiều yếu tố: tài khoản và IAM role, hạ tầng được tạo sẵn, kết nối mạng, chi phí, độ trễ và nguy cơ tác động nhầm tới dữ liệu thật.

**LocalStack** là công cụ chạy môi trường mô phỏng một tập API/dịch vụ AWS trên máy phát triển hoặc trong container. Thay vì gọi endpoint của AWS thật, ứng dụng cấu hình **endpoint của LocalStack** và sử dụng tài nguyên được tạo trong môi trường giả lập. Cách làm này giúp kiểm tra luồng tích hợp một cách lặp lại được.

Bài này thuộc chương **Nền tảng AWS** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mục tiêu chung của module là thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud thông qua các thư viện Spring Cloud tương ứng, bao gồm identity/permission, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và sự khác biệt giữa cloud provider. Bài học tập trung vào cấu hình **Spring Cloud AWS của AWSpring**, **AWS SDK for Java 2.x** và **LocalStack** trong môi trường local/test.

Sau bài học, bạn có thể:

1. Giải thích vai trò của LocalStack trong quy trình phát triển và những giới hạn so với AWS thật.
2. Khởi chạy LocalStack bằng Docker Compose, tạo bucket S3 và queue SQS giả lập.
3. Cấu hình **endpoint, region, credential, path-style S3** cho AWS SDK v2 hoặc Spring Cloud AWS.
4. Thực hiện một vòng ghi/đọc S3 và gửi/nhận SQS để chứng minh kết nối hoạt động.
5. Viết integration test với **Testcontainers** và cấu hình động cho Spring Boot.
6. Chẩn đoán lỗi Docker network, endpoint, region, DNS, credential và bean auto-configuration.
7. Thiết kế ranh giới ngăn test/local gửi nhầm request tới AWS production.

> **Phạm vi phiên bản:** Ví dụ Java sử dụng AWS SDK for Java **2.x** và phong cách cấu hình Spring Cloud AWS **3.x**. Phiên bản LocalStack, Testcontainers, AWSpring và Spring Boot phải được chọn theo tài liệu tương thích thực tế của dự án. Dịch vụ/tính năng có sẵn, yêu cầu giấy phép hoặc token LocalStack có thể khác theo **release và edition**; kiểm tra phiên bản LocalStack đang sử dụng trước khi chạy.

## 2. LocalStack nằm ở đâu trong kiến trúc?

Ở môi trường thật, SDK tạo request hướng đến AWS service endpoint. Ở môi trường local, ta giữ phần lớn **mã gọi SDK hoặc AWSpring** nhưng chuyển endpoint sang LocalStack và provision tài nguyên giả.

~~~mermaid
flowchart TB
    APP["Spring Boot application"] --> SPR["AWSpring S3Template / SqsTemplate<br/>hoặc AWS SDK Java v2"]
    SPR --> CONF{"Cấu hình môi trường"}
    CONF -->|local / integration-test| EMU["LocalStack API endpoint<br/>http://localhost:4566"]
    CONF -->|staging / production| AWS["AWS service endpoint thật"]
    EMU --> S3L["S3 giả lập"]
    EMU --> SQSL["SQS giả lập"]
    AWS --> S3A["Amazon S3"]
    AWS --> SQSA["Amazon SQS"]
~~~

Điểm cần phân biệt:

| Khái niệm | Mục đích | Khi dùng LocalStack |
| --- | --- | --- |
| Service client | `S3Client`, `SqsClient` hoặc template Spring gọi operation AWS | Vẫn dùng SDK/API quen thuộc |
| Endpoint | Địa chỉ HTTP(S) nhận request | Đổi sang URL của LocalStack |
| Region | Ngữ cảnh vùng của client và request signing | Đặt vùng test nhất quán, ví dụ `us-east-1` |
| Credentials | Giá trị SDK dùng để ký request | Dùng **credential giả** dành riêng cho emulator |
| Resource | Bucket, queue, table, secret | Phải tạo trong LocalStack hoặc khởi tạo khi test |
| Identity & policy | Principal IAM, trust policy, KMS, SCP | **Không thể coi mô phỏng là bằng chứng quyền AWS thật** |
| Network | DNS, port, container network, proxy | Phải trỏ đúng host/port theo nơi ứng dụng chạy |

**LocalStack không thay thế AWS trong mọi loại kiểm thử.** Một luồng `PutObject`/`GetObject` hoặc `SendMessage`/`ReceiveMessage` có thể chạy được trong emulator nhưng thất bại trên AWS do IAM, bucket policy, KMS, network/VPC endpoint, queue configuration, quota hoặc đặc tính dịch vụ chưa được mô phỏng đủ.

### 2.1. Chọn những phép thử phù hợp cho emulator

LocalStack đặc biệt hữu ích khi muốn xác minh:

- Spring context có tạo bean S3/SQS đúng không.
- Request/response dùng đúng SDK, serializer, tên bucket, object key, queue URL.
- Adapter gọi đúng operation, xử lý kết quả và một số lỗi dịch vụ.
- Producer và consumer giao tiếp được với queue trong môi trường kiểm soát.
- Luồng tích hợp chạy được lặp lại trong CI khi tạo tài nguyên từ đầu.

Với những tình huống **phụ thuộc chính xác vào AWS thật**, như IAM role trust trên ECS/EKS, policy KMS cross-account, endpoint private, độ trễ ở tải lớn, giới hạn dịch vụ hoặc hành vi lỗi hiếm gặp, cần thêm integration/smoke test trên AWS sandbox.

## 3. Chuẩn bị công cụ và quy ước an toàn

Trước khi thực hành, chuẩn bị:

- Docker Engine hoặc Docker Desktop có thể chạy Linux containers.
- Docker Compose plugin (`docker compose`).
- AWS CLI v2 hoặc công cụ tương đương để gọi AWS API vào emulator.
- JDK và dự án Spring Boot phù hợp với phiên bản AWSpring định dùng.
- LocalStack image thuộc release/edition có hỗ trợ các tính năng S3 và SQS mà bài test sử dụng.

Kiểm tra khả năng chạy các lệnh:

~~~bash
docker version
docker compose version
aws --version
java -version
~~~

Đây là các lệnh thực hành; bài học không giả định chúng đã được chạy trên máy của người học.

### 3.1. Chỉ dùng tài nguyên test

Ví dụ trong bài sử dụng:

| Giá trị | Mục đích |
| --- | --- |
| `http://localhost:4566` | LocalStack edge endpoint khi app chạy **trên host** |
| `http://localstack:4566` | Endpoint khi app chạy trong **cùng Docker Compose network** với service tên `localstack` |
| `us-east-1` | Region test thống nhất để đơn giản hóa thao tác S3 |
| `test` / `test` | Dummy access key và secret key cho emulator |
| `training-documents-local` | Bucket S3 giả |
| `training-events-local` | Queue SQS giả |

Những giá trị này **không đại diện cho môi trường production**. Khi gọi AWS thật, sử dụng IAM role hoặc profile có quyền được cấp hợp lệ, vùng thật và ARN tài nguyên đã provision.

### 3.2. Luôn biết request đang đi đâu

Với SDK v2, các khái niệm sau **độc lập**:

- `endpointOverride(...)` chọn URL nhận request.
- `region(...)` chọn vùng của client và được dùng trong quá trình ký request.
- `credentialsProvider(...)` chọn nguồn credentials.
- `bucket(...)`, `key(...)`, `queueUrl(...)` chọn tài nguyên nghiệp vụ.

Đặt endpoint của LocalStack **không tự động làm SDK bỏ qua region hoặc credentials**. Ngược lại, dùng dummy credentials mà quên endpoint override có thể khiến SDK gửi request đến AWS thật và gặp lỗi xác thực.

## 4. Khởi động LocalStack bằng Docker Compose

Tạo ví dụ Compose sau **trong một thư mục thực hành riêng**. Đoạn YAML ở đây chỉ là nội dung hướng dẫn, không phải file được bài học tự tạo:

~~~yaml
services:
  localstack:
    image: localstack/localstack:${LOCALSTACK_IMAGE_TAG:-latest}
    ports:
      - "127.0.0.1:4566:4566"
    environment:
      SERVICES: s3,sqs
      AWS_DEFAULT_REGION: us-east-1
~~~

Giải thích:

- `4566` là cổng edge endpoint thông dụng của LocalStack; nhiều service được truy cập qua cổng này.
- `127.0.0.1:4566:4566` chỉ bind vào loopback của host để tránh vô ý công bố emulator trên mạng bên ngoài.
- `SERVICES=s3,sqs` hướng tới hai service phục vụ bài tập; hỗ trợ tùy phiên bản/edition.
- `AWS_DEFAULT_REGION` ở đây là **cấu hình của LocalStack**, không thay thế `AWS_REGION` của Java SDK đang chạy ở process khác.
- `LOCALSTACK_IMAGE_TAG` cho phép pin release. Giá trị `latest` thuận tiện cho bài demo nhưng **không tái lập ổn định** trong CI; nên pin một tag/digest đã được nhóm kiểm chứng khi triển khai test thật.

Ví dụ khởi động:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail 100 localstack
~~~

Chờ dịch vụ ở trạng thái sẵn sàng trước khi tạo tài nguyên. Có thể kiểm tra health endpoint khi release hỗ trợ:

~~~bash
curl http://localhost:4566/_localstack/health
~~~

Nếu LocalStack phiên bản đang dùng yêu cầu cấu hình token hoặc edition tương ứng, hãy bổ sung theo hướng dẫn chính thức của release đó. Đừng đưa token thật vào Dockerfile hoặc file Compose đã commit.

### 4.1. Không mount Docker socket khi không cần

Một số tài liệu LocalStack cho các chức năng nhất định có thể dùng Docker socket mount. **Bài thực hành S3/SQS cơ bản không yêu cầu mặc định cấp quyền Docker socket cho container giả lập.** Docker socket cung cấp quyền nhạy cảm trên daemon/host; chỉ cân nhắc khi tính năng và tài liệu của release thực sự yêu cầu.

### 4.2. Dữ liệu giả lập tồn tại trong bao lâu?

Nếu không cấu hình persistence, dữ liệu do LocalStack lưu có thể mất khi container được tạo lại. Với integration test, việc **khởi tạo resource từ đầu** thường là lợi thế vì hạn chế phụ thuộc trạng thái cũ.

Để debug thủ công, có thể dùng cơ chế persistence được LocalStack release hỗ trợ, nhưng không nên để CI phụ thuộc một volume cũ chứa bucket/queue từ lần chạy trước. Mỗi bài test cần kiểm soát resource setup, cleanup và tên tài nguyên.

### 4.3. Dừng môi trường

~~~bash
docker compose down
~~~

Nếu dùng volume lưu trữ, `docker compose down` và `docker compose down -v` có tác dụng khác nhau. Chỉ xóa volume khi đó là dữ liệu test có thể tái tạo và người thực hành biết chính xác tài nguyên nào sẽ bị xóa.

## 5. AWS CLI phải trỏ đến LocalStack

AWS CLI bình thường mặc định gọi AWS thật. Với LocalStack, cần chỉ rõ endpoint giả lập và dùng dummy credentials khi thử trên máy local.

Trên Bash:

~~~bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export AWS_PAGER=""
~~~

Trên PowerShell:

~~~powershell
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_REGION = "us-east-1"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:AWS_PAGER = ""
~~~

Các biến này chỉ nên được thiết lập trong **terminal dành cho emulator**. Không trộn terminal đó với các lệnh thao tác production. Dùng `--endpoint-url` tường minh cho từng lệnh LocalStack để biết chính xác request đi đâu.

### 5.1. Tạo bucket S3 giả lập

Với region test `us-east-1`:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3api create-bucket \
  --bucket training-documents-local
~~~

Trong region khác `us-east-1`, thao tác tạo bucket theo semantics S3 thường cần cấu hình location constraint phù hợp. Sử dụng `us-east-1` giúp phần thực hành cơ bản có ít khác biệt hơn.

Kiểm tra:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3api list-buckets
~~~

Lệnh trên chỉ kiểm tra môi trường giả lập. Trên AWS thật, `ListBuckets` còn chịu IAM policy và các quy tắc dịch vụ tương ứng; emulator có thể không mô phỏng đầy đủ.

### 5.2. Tạo queue SQS giả lập

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  sqs create-queue \
  --queue-name training-events-local
~~~

Lấy **queue URL do emulator trả về**:

~~~bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  sqs get-queue-url \
  --queue-name training-events-local
~~~

Queue URL có thể khác theo release và endpoint strategy của LocalStack. Nó cũng có thể chứa hostname phù hợp với container/host khác nhau. Đừng tự đoán rằng queue URL luôn là `http://localhost:4566/000000000000/training-events-local`; ưu tiên lấy từ `CreateQueue` hoặc `GetQueueUrl` thực tế và đảm bảo hostname có thể truy cập từ process sẽ sử dụng URL đó.

### 5.3. Xác nhận có resource trước khi chạy Spring

Bạn nên kiểm tra bucket và queue đã tồn tại trong emulator trước khi khởi động listener Spring Boot. Điều này đặc biệt quan trọng với `@SqsListener` vì listener container có thể bắt đầu resolve tên queue **ngay trong giai đoạn tạo ApplicationContext**. Nếu queue chưa có, startup có thể thất bại hoặc library tự tạo queue tùy cấu hình/version, làm test khó lặp lại.

## 6. AWS SDK Java v2: kết nối S3 bằng endpoint override

Cách kiểm chứng tốt nhất trước khi tích hợp Spring là thử một SDK client đơn giản. Khi client có thể thực hiện một vòng ghi/đọc dữ liệu với LocalStack, ta biết những yếu tố cơ bản như network, endpoint, region, credentials và API đã được thiết lập nhất quán.

### 6.1. Dependency

Nếu dự án dùng Maven và đã quản lý version SDK bằng BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
</dependency>
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("software.amazon.awssdk:s3")
}
~~~

Nếu không có BOM/dependency management phù hợp, cần khai báo version SDK cụ thể đã được xác nhận. Không đặt các module `s3`, `sqs`, `auth` ở nhiều version không nhất quán.

### 6.2. Tạo S3Client cho local

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public final class LocalS3ClientFactory {

    public static S3Client create(URI endpoint) {
        return S3Client.builder()
                .endpointOverride(endpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

Giải thích từng cấu hình:

- `endpointOverride(endpoint)` trỏ request đến LocalStack, ví dụ `http://localhost:4566` khi chạy trên host.
- `Region.US_EAST_1` tạo vùng test nhất quán cho client và chữ ký request.
- `StaticCredentialsProvider` dùng dummy key cho emulator. **Không đem cấu hình này sang môi trường thật.**
- `pathStyleAccessEnabled(true)` khiến URL S3 dùng dạng path-style, giúp tránh vấn đề DNS khi emulator không hỗ trợ hostname kiểu `bucket.localhost`.
- `S3Client` nên được tái sử dụng theo vòng đời ứng dụng/test và đóng khi không còn cần.

### 6.3. Thử ghi rồi đọc một object

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;

public class LocalS3RoundTrip {
    public static void main(String[] args) {
        try (S3Client s3 = LocalS3ClientFactory.create(
                URI.create("http://localhost:4566"))) {

            String bucket = "training-documents-local";
            String key = "receipts/example-001.txt";
            String content = "Spring Boot va LocalStack";

            s3.putObject(request -> request
                    .bucket(bucket)
                    .key(key),
                    RequestBody.fromString(content, StandardCharsets.UTF_8));

            String stored = s3.getObjectAsBytes(request -> request
                    .bucket(bucket)
                    .key(key))
                    .asUtf8String();

            if (!content.equals(stored)) {
                throw new IllegalStateException("Noi dung doc lai khac ban dau");
            }
            System.out.println("S3 round-trip PASS");
        }
    }
}
~~~

Ví dụ giả định bucket `training-documents-local` đã được tạo ở bước AWS CLI. Có thể dùng nội dung tiếng Việt có dấu nếu source code và môi trường biên dịch dùng UTF-8; ở đây payload ngắn nhằm làm rõ đường gọi API.

**Cách đọc kết quả:**

- Nếu `PutObject` thất bại do `Connection refused`, kiểm tra port, container và URL.
- Nếu lỗi DNS hostname của bucket, kiểm tra path-style và endpoint.
- Nếu `NoSuchBucket`, kiểm tra bước tạo bucket, trạng thái container và region.
- Nếu nhận 403 khi gọi AWS thật, kiểm tra IAM/resource policy, chứ không được kết luận LocalStack test đã chứng minh permission đúng.

## 7. AWS SDK Java v2: kết nối SQS và gửi/nhận thông điệp

Thêm module SDK:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
</dependency>
~~~

Tạo client local:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

public final class LocalSqsClientFactory {

    public static SqsClient create(URI endpoint) {
        return SqsClient.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(endpoint)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .build();
    }
}
~~~

Khi giao tiếp với SQS, phân biệt:

- **Client endpoint:** địa chỉ API SQS mà SDK gửi request.
- **Queue URL:** URL định danh queue cụ thể được dùng trong `SendMessageRequest`/`ReceiveMessageRequest`.
- **Region:** vùng của client/queue, phải phù hợp với cấu hình giả lập hoặc AWS thật.

### 7.1. Gửi, nhận và xóa message

~~~java
import java.net.URI;
import software.amazon.awssdk.services.sqs.SqsClient;

public class LocalSqsRoundTrip {
    public static void main(String[] args) {
        try (SqsClient sqs = LocalSqsClientFactory.create(
                URI.create("http://localhost:4566"))) {

            String queueUrl = sqs.getQueueUrl(request -> request
                    .queueName("training-events-local"))
                    .queueUrl();

            sqs.sendMessage(request -> request
                    .queueUrl(queueUrl)
                    .messageBody("{\"eventId\":\"evt-001\",\"type\":\"DocumentUploaded\"}"));

            var received = sqs.receiveMessage(request -> request
                    .queueUrl(queueUrl)
                    .maxNumberOfMessages(1)
                    .waitTimeSeconds(5))
                    .messages();

            if (received.isEmpty()) {
                throw new IllegalStateException("Khong nhan duoc message");
            }

            for (var message : received) {
                System.out.println(message.body());
                sqs.deleteMessage(request -> request
                        .queueUrl(queueUrl)
                        .receiptHandle(message.receiptHandle()));
            }
        }
    }
}
~~~

Ví dụ giả định queue được tạo trước bằng AWS CLI. Khi truyền queue URL do emulator trả về, URL phải có hostname/port truy cập được từ JVM hiện tại.

### 7.2. Vì sao phải xóa message sau khi xử lý?

`ReceiveMessage` không đồng nghĩa message đã được tiêu thụ vĩnh viễn. SQS sử dụng **visibility timeout**: message được ẩn tạm thời trong lúc consumer xử lý, sau đó có thể xuất hiện trở lại nếu chưa được xóa. Lệnh `DeleteMessage` cần đúng **receipt handle** của lần nhận đó.

LocalStack có thể mô phỏng những hành vi này, nhưng kiểm thử idempotency, thứ tự FIFO, redrive policy và lỗi mạng vẫn cần đánh giá trên AWS thật ở những luồng quan trọng.

### 7.3. Thử lỗi có kiểm soát

Để xác nhận code không chỉ đi được đường thành công:

- Thử tên queue không tồn tại và kiểm tra exception.
- Thử payload trùng `eventId` để đánh giá logic idempotency nghiệp vụ.
- Thử handler xử lý chậm hơn visibility timeout và quan sát việc nhận lại message trong môi trường giả lập.
- Thử cấu hình vùng hoặc endpoint sai để nhận diện lỗi kết nối khác với lỗi business.
- Với consumer Spring, kiểm tra acknowledgement và DLQ theo phiên bản AWSpring/SQS đang sử dụng.

## 8. Kết nối Spring Boot qua Spring Cloud AWS của AWSpring

Khi SDK thuần đã hoạt động, có thể sử dụng starter AWSpring để tạo template/bean, giúp code nghiệp vụ gần với cách tổ chức quen thuộc của Spring.

### 8.1. Chọn starter và BOM

Ví dụ Maven, **giả định đã có Spring Boot parent/dependency management**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
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
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-aws.version` phải là **release AWSpring có thật, tương thích với Spring Boot/JDK của dự án**. Không tự suy rằng mọi bản AWSpring 3.x đều tương thích với mọi bản Spring Boot 3.x. BOM giúp quản lý version, còn starter bổ sung khả năng tích hợp.

Nếu nguồn ứng dụng tự import SDK client, có thể khai báo thêm module SDK v2 trực tiếp (ví dụ `software.amazon.awssdk:s3`), với version đã được quản lý nhất quán. Không trộn ví dụ của SDK Java 1.x (`com.amazonaws.*`) vào ứng dụng được xây trên SDK v2.

### 8.2. Cấu hình chỉ dành cho local

Ví dụ `application-local.yml` với phong cách property thường thấy trong AWSpring 3.x:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: us-east-1
      credentials:
        access-key: test
        secret-key: test
      s3:
        endpoint: ${LOCALSTACK_ENDPOINT:http://localhost:4566}
        path-style-access-enabled: true
      sqs:
        endpoint: ${LOCALSTACK_ENDPOINT:http://localhost:4566}

app:
  storage:
    bucket: training-documents-local
  messaging:
    queue: training-events-local
~~~

Giải thích:

- `spring.cloud.aws.region.static` gán region cho các bean client AWSpring tạo trong cấu hình này.
- `credentials.access-key` và `credentials.secret-key` là **dummy credentials chỉ dành cho emulator**, được đặt trong Spring profile `local`.
- `s3.endpoint` và `sqs.endpoint` đưa hai service về LocalStack thay vì endpoint AWS thật.
- `path-style-access-enabled` hỗ trợ địa chỉ bucket trên emulator; tên property/tính năng cần kiểm tra với **release AWSpring chính xác**.
- `app.storage.bucket` và `app.messaging.queue` là property nghiệp vụ do ứng dụng định nghĩa, không phải AWSpring tự hiểu.

**Không kích hoạt profile `local` trong production.** Trong cấu hình production, ứng dụng nên lấy region/tài nguyên thật từ deployment config và credentials từ IAM workload role/default provider chain, không dùng dummy credentials hay endpoint test.

### 8.3. Ghi file bằng S3Template

~~~java
import io.awspring.cloud.s3.S3Template;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageAdapter {
    private final S3Template s3;
    private final String bucket;

    public DocumentStorageAdapter(S3Template s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void storeText(String key, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        s3.upload(bucket, key, new ByteArrayInputStream(bytes));
    }
}
~~~

Đây là ví dụ với payload nhỏ. Với file lớn, cần xem streaming/multipart và giới hạn bộ nhớ. `S3Template` không cần biết ứng dụng đang chạy với LocalStack hay AWS thật: endpoint/credentials đến từ **client bên dưới**, do cấu hình môi trường quyết định.

### 8.4. Gửi message qua SqsTemplate

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

record DocumentUploaded(String eventId, String objectKey) {}

@Service
public class DocumentEventPublisher {
    private final SqsTemplate sqs;
    private final String queue;

    public DocumentEventPublisher(SqsTemplate sqs,
            @Value("${app.messaging.queue}") String queue) {
        this.sqs = sqs;
        this.queue = queue;
    }

    public void publish(DocumentUploaded event) {
        sqs.send(to -> to.queue(queue).payload(event));
    }
}
~~~

`SqsTemplate` phụ thuộc phần tích hợp SQS và client SDK do AWSpring cung cấp. Cần kiểm tra conversion/serialization cho kiểu `DocumentUploaded`, vì test emulator nhận được JSON không đồng nghĩa mọi service consumer trong production hiểu cùng schema.

### 8.5. Nhận message bằng @SqsListener

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class DocumentEventConsumer {

    @SqsListener("${app.messaging.queue}")
    public void onUploaded(DocumentUploaded event) {
        // Xử lý idempotent theo eventId.
        // Nếu xử lý thất bại, cần để cơ chế lỗi/ack phản ánh đúng thất bại.
    }
}
~~~

Listener có thể bắt đầu polling **ngay khi Spring context khởi động**. Nếu queue chưa tồn tại, phải provision nó trước startup hoặc dùng cơ chế queue creation được release cho phép với kiểm soát rõ. Để test hành vi consumer đáng tin cậy, cần kiểm tra visibility timeout, concurrency, acknowledgement mode, serialization và cơ chế retry/DLQ.

## 9. Khi cần tự tạo client trong Spring

Một dự án có thể không muốn phụ thuộc vào property auto-configuration của AWSpring vì cần endpoint/region riêng cho từng adapter. Khi đó, tạo bean SDK client có cấu hình tường minh:

~~~java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

@Configuration(proxyBeanMethods = false)
@Profile("local")
public class LocalAwsClients {

    @Bean(name = "localS3Client", destroyMethod = "close")
    S3Client localS3Client(
            @Value("${localstack.endpoint:http://localhost:4566}")
            String endpoint) {
        return S3Client.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(URI.create(endpoint))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

**Chú ý tương tác auto-configuration:** khi tự khai báo bean `S3Client`, AWSpring có thể **back off** hoặc chọn wiring khác tùy release và điều kiện tạo bean. Nếu bạn vừa cần `S3Template` mặc định vừa cần nhiều `S3Client` ở các vùng/endpoint khác nhau, hãy dùng qualifier/factory và kiểm tra ApplicationContext thực tế. Tên bean `localS3Client` không bảo đảm mọi template sẽ tự chọn bean đó.

Đối với code nghiệp vụ, nên tạo adapter tách khỏi chi tiết kết nối. Một interface `DocumentStore` có thể được triển khai bằng S3 ở production, S3 LocalStack ở integration test và fake đơn giản ở unit test, giúp quản lý cấu hình nhất quán.

## 10. Vấn đề phổ biến: localhost của host khác localhost của container

Đây là nguyên nhân thường gặp nhất khiến LocalStack đã chạy nhưng Java vẫn báo `Connection refused`.

Giả sử có hai container cùng Docker Compose:

~~~mermaid
flowchart LR
    HOST["Máy host"] -->|"http://localhost:4566"| PORT["Docker published port"]
    PORT --> LS["Container localstack:4566"]
    APP["Container spring-app"] -->|"http://localstack:4566"| LS
    APP -. "localhost:4566 chỉ chính container app" .-> APP
~~~

| Nơi ứng dụng chạy | Endpoint thường dùng | Vì sao |
| --- | --- | --- |
| Java chạy trực tiếp trên host | `http://localhost:4566` | Docker publish cổng 4566 ra loopback host |
| Java chạy trong cùng Compose network | `http://localstack:4566` | DNS service name của Compose |
| Testcontainers chạy JVM trên host | `container.getEndpointOverride(...)` | Host và mapped port do Testcontainers cấp |
| Docker container ở network khác | Endpoint/alias truy cập được theo network đã cấu hình | Không mặc định kết nối được tới service name của network khác |
| CI runner dùng Docker daemon từ xa | Endpoint do Testcontainers/network environment trả về | `localhost` của runner có thể không trỏ vào Docker host |

### 10.1. Vì sao không hard-code localhost vào mọi test?

Khi CI chạy Docker qua daemon từ xa, cổng được publish có thể nằm trên host khác máy JVM. Testcontainers cung cấp `getHost()`, `getMappedPort(...)` hoặc `getEndpointOverride(...)` để xác định endpoint theo môi trường. Với module LocalStack, nên dùng hàm endpoint tương ứng **thay vì ghép URL bằng tay từ port 4566**.

### 10.2. DNS cho S3 virtual-hosted style

S3 SDK có thể gửi request đến hostname dạng `bucket.endpoint-host`. Trong emulator, hostname đó có thể không phân giải được. Đó là lý do nhiều bài local dùng `pathStyleAccessEnabled(true)` để yêu cầu URL dạng `/bucket/key`.

Với endpoint và DNS khác, virtual-hosted style cũng có thể hoạt động. Quyết định phụ thuộc cấu hình emulator và network, không phải quy tắc bắt buộc cho mọi môi trường S3.

### 10.3. Queue URL từ emulator

Queue URL trả về từ `GetQueueUrl` có thể chứa hostname mà JVM hoặc container không truy cập được. Cần kiểm tra **giá trị thực tế**, endpoint strategy của LocalStack và DNS/network; không thay bằng URL tự chế trong production. Với consumer/publisher Spring, cần bảo đảm tên queue/URL được chuyển đổi đúng theo API AWSpring và SDK đang dùng.

## 11. Integration test tự động bằng Testcontainers

Chạy LocalStack thủ công phù hợp để học và debug, nhưng integration test trong CI cần khởi tạo/dọn tài nguyên có thể lặp lại. **Testcontainers** giúp Java test quản lý vòng đời container Docker và lấy endpoint thực tế ngay lúc runtime.

### 11.1. Dependency kiểm thử

Ví dụ Maven mang tính cấu trúc:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chọn đúng LocalStack module thuộc thế hệ Testcontainers đang dùng. -->
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>localstack</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tên artifact `localstack`/`junit-jupiter` trên là cách khai báo của **Testcontainers 1.x**. Với **Testcontainers 2.x**, module coordinates có thể chuyển sang dạng `testcontainers-localstack` và `testcontainers-junit-jupiter`. Hãy chọn **đúng generation/BOM của Testcontainers mà dự án đang dùng**, thay các artifact và import nếu release yêu cầu. Không copy hai thế hệ dependency vào cùng project.

Khi viết Gradle, dùng các module test tương ứng trong `testImplementation(...)` và BOM/platform thích hợp. Testcontainers yêu cầu Docker runtime khả dụng; unit test thuần không cần Docker.

### 11.2. Test Spring Boot kết nối tới LocalStack động

Ví dụ dưới đây thể hiện cách dùng **Testcontainers API truyền thống** để truyền endpoint test vào Spring Boot:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class LocalStackS3IntegrationTest {

    @Container
    static final LocalStackContainer localstack =
            new LocalStackContainer(DockerImageName.parse(
                    "localstack/localstack:latest"))
                    .withServices(
                            LocalStackContainer.Service.S3,
                            LocalStackContainer.Service.SQS);

    @DynamicPropertySource
    static void configureAws(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.aws.region.static",
                localstack::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key",
                localstack::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key",
                localstack::getSecretKey);
        registry.add("spring.cloud.aws.s3.endpoint",
                () -> localstack.getEndpointOverride(
                        LocalStackContainer.Service.S3).toString());
        registry.add("spring.cloud.aws.sqs.endpoint",
                () -> localstack.getEndpointOverride(
                        LocalStackContainer.Service.SQS).toString());
        registry.add("spring.cloud.aws.s3.path-style-access-enabled",
                () -> "true");
    }

    @Autowired
    S3Client s3;

    @Test
    void shouldWriteAndReadS3Object() {
        String bucket = "training-local-" +
                UUID.randomUUID().toString().substring(0, 8);
        String key = "documents/test.txt";
        String content = "Testcontainers with LocalStack";

        s3.createBucket(request -> request.bucket(bucket));
        s3.putObject(request -> request
                .bucket(bucket)
                .key(key),
                RequestBody.fromString(content, StandardCharsets.UTF_8));

        String readBack = s3.getObjectAsBytes(request -> request
                .bucket(bucket)
                .key(key))
                .asUtf8String();

        assertEquals(content, readBack);
    }
}
~~~

**Giả định của ví dụ:** starter AWSpring S3 tạo được một bean `S3Client` cho ApplicationContext, các property phù hợp release AWSpring đang dùng và môi trường test **không có SQS listener khởi động trước khi queue tồn tại**. Nếu ứng dụng có `@SqsListener`, phải provision queue **trước khi Spring context khởi động**, ví dụ bằng init hook của LocalStack hoặc test initializer. Nếu chỉ tạo queue trong `@BeforeEach` thì có thể đã quá muộn cho giai đoạn listener startup.

Ngoài ra:

- Image `latest` chỉ dùng cho minh họa. Trong CI nên pin một tag/digest LocalStack tương thích đã kiểm chứng.
- Các import/artifact Testcontainers phụ thuộc major version; nếu chọn Testcontainers 2.x, cập nhật theo API/docs của generation đó.
- Có thể dùng `@ServiceConnection` ở những phiên bản Spring Boot/Testcontainers hỗ trợ, nhưng endpoint/property cho AWSpring vẫn cần được xác định rõ theo integration đang dùng.
- `@DynamicPropertySource` đưa endpoint từ **container thực tế** vào Spring context; không giả định cổng được map luôn là 4566 trên host.
- `LocalStackContainer` do Testcontainers quản lý vòng đời. Nếu tạo SDK client riêng trong test, hãy đóng client sau khi dùng.
- Khi test chạy song song, tạo tên bucket/queue duy nhất cho từng test hoặc cách ly container/context để tránh trùng dữ liệu.

### 11.3. Provision tài nguyên trước khi context khởi động

Một vấn đề đặc thù khi test Spring + SQS listener là thứ tự:

~~~mermaid
flowchart TD
    A["Test bắt đầu"] --> B["LocalStack container ready"]
    B --> C["Tạo queue/bucket cần cho startup"]
    C --> D["Spring ApplicationContext khởi động"]
    D --> E["SQS listener resolve queue"]
    E --> F["Chạy test"]
    F --> G["Cleanup"]
~~~

Nếu ứng dụng chỉ test S3 adapter, có thể tạo bucket ngay trong `@Test`. Nếu có `@SqsListener`, nhiều release AWSpring resolve queue từ lúc container startup; cần provision queue trước context. Một cách là dùng **LocalStack initialization hooks** của release tương thích: script đặt dưới `/etc/localstack/init/ready.d/` trong container để tạo queue trước khi test ứng dụng khởi động.

Ví dụ nội dung một init script dành cho môi trường giả lập:

~~~sh
#!/bin/sh
set -eu

awslocal s3 mb s3://training-documents-local
awslocal sqs create-queue --queue-name training-events-local
~~~

Khi dùng init hook, cần kiểm tra bản LocalStack hỗ trợ cơ chế mount/copy script, quyền execute, thời điểm ready và log thực thi. Đảm bảo script đã hoàn tất trước khi khởi động Spring context. Nếu có listener tự động tạo queue theo cấu hình AWSpring, vẫn nên kiểm soát chính sách đó để tránh behavior khác giữa local và production.

### 11.4. Nên kiểm tra điều gì trong integration test?

| Luồng | Kiểm thử tiêu biểu |
| --- | --- |
| S3 | Tạo bucket, PutObject/GetObject, content/metadata, key không tồn tại |
| SQS producer | Gửi event, kiểm tra payload/attributes, queue URL/region |
| SQS consumer | Xử lý JSON, acknowledgement, lỗi handler và phát lại message |
| Wiring Spring | Bean S3/SQS sử dụng endpoint và credential **của test** |
| Isolation | Không có request AWS thật; không phụ thuộc profile người chạy |
| Error handling | Timeout, object/queue thiếu, serialization lỗi trong phạm vi emulator |
| Retry/idempotency | Message trùng, phản hồi chậm và side effect được xử lý an toàn |
| Startup lifecycle | Queue cần thiết tồn tại trước khi listener container start |

Testcontainers giải quyết **vòng đời Docker/container**. Nó không tự đảm bảo context Spring dùng đúng endpoint nếu ứng dụng có custom client bean hoặc credential provider override. Vì vậy cần một kiểm thử đi qua chính adapter/bean mà ứng dụng production sẽ dùng.

## 12. Ngăn test vô tình gọi AWS thật

Đây là yêu cầu quan trọng nhất khi sử dụng emulator trong code có khả năng thay đổi dữ liệu.

### 12.1. Cấu hình theo Spring profile

Nên tách rõ `local`, `test`, `staging` và `prod`:

- `local`: LocalStack endpoint, region test, dummy credentials, tài nguyên test.
- `test`: endpoint do Testcontainers cung cấp động; không phụ thuộc trạng thái LocalStack thủ công.
- `staging`: AWS sandbox hoặc staging thật, IAM role và resource riêng.
- `prod`: endpoint chuẩn của AWS, IAM workload identity, tài nguyên production.

**Không bật `local` hoặc `test` ngoài phạm vi có kiểm soát.** Có thể kiểm tra `spring.profiles.active` và các property kết nối lúc startup; từ chối khởi động nếu một production deployment lại thấy `localhost:4566`, `localstack` hoặc dummy credentials.

### 12.2. Không dùng credential của máy developer cho test

Nếu SDK test chỉ gọi `S3Client.create()` mà không override endpoint/credentials, default credentials provider chain có thể tìm AWS profile của người chạy hoặc IAM role của CI runner. Tốt hơn nên dùng **`StaticCredentialsProvider` với dummy credentials** và **endpoint LocalStack tường minh** trong test.

Nếu Spring AWSpring tạo client, cấu hình test phải override cả region/endpoint/credential cho các bean mà test sử dụng. Đừng chỉ đổi một property rồi giả định các bean tự động dùng nó.

### 12.3. Tách test emulator khỏi AWS sandbox

Một bộ test nên có hai lớp:

1. **Integration test qua LocalStack:** chạy thường xuyên trên developer laptop/CI, kết quả nhanh và ít phụ thuộc cloud thật.
2. **Smoke test trên AWS sandbox:** chạy với IAM role test được cấp quyền tối thiểu, resource ARN cố định theo môi trường, kiểm tra IAM/KMS/network/semantics thật.

Không cho phép smoke test account production trở thành mặc định trong `mvn test` hoặc `gradle test` khi người học chỉ muốn chạy kiểm thử local.

### 12.4. Rào chắn thực tế

Các rào chắn hữu ích:

- Trong config test, endpoint phải thuộc allowlist local/test container.
- Nếu test dùng dummy credential, bắt buộc endpoint test tường minh; ngược lại báo lỗi startup.
- Với bài kiểm thử AWS thật, xác nhận account qua `GetCallerIdentity` và đối chiếu allowlist **trước** khi ghi/xóa dữ liệu.
- Resource name/ARN dành cho test phải có prefix/tag riêng.
- CI không cấp credential production cho job chạy emulator.
- Không đưa endpoint giả lập, dummy key hoặc file init test vào image/config production.

## 13. Những lỗi kết nối LocalStack thường gặp

### 13.1. Bảng tra cứu triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Connection refused` tới `localhost:4566` | Container chưa ready, sai port, Java chạy trong container khác | `docker compose ps`, logs, port mapping, endpoint theo network |
| `UnknownHostException` với `localstack` | Java chạy trên host, không ở Compose network | Dùng `localhost:4566` trên host hoặc cấu hình DNS tương ứng |
| `UnknownHostException` với `bucket.localhost` | S3 virtual-hosted style không phù hợp DNS emulator | Dùng path-style trong test hoặc cấu hình DNS đúng |
| `NoSuchBucket` | Bucket chưa được tạo, sai tên/region hoặc dữ liệu đã reset | CLI gọi endpoint test, liệt kê bucket |
| `QueueDoesNotExist` | Queue chưa tạo; sai tên, queue URL, region, endpoint | GetQueueUrl từ chính emulator |
| `Unable to load credentials` | SDK chưa nhận dummy test credentials; cấu hình provider khác override | Kiểm tra Spring properties/bean/SDK chain |
| `Unable to load region` | Client không có region; nhầm `AWS_DEFAULT_REGION` của CLI/LocalStack với `AWS_REGION` của SDK | Đặt region SDK test tường minh |
| `SignatureDoesNotMatch` | Region/signing/endpoint/clock mismatch hoặc request đến AWS thật | Xác minh endpoint và client region |
| S3 pass nhưng SQS fail | Cấu hình S3/SQS có endpoint độc lập; queue URL không reachable | Kiểm tra client thực tế mỗi service |
| `@SqsListener` lỗi ngay lúc startup | Queue chưa có trước Spring context; auto-creation/config không phù hợp | Provision trước khi listener start |
| Test pass local, fail CI | Host/port thay đổi, Docker daemon remote, image tag chưa pin | Dùng Testcontainers endpoint, kiểm tra Docker runtime |
| Test pass LocalStack, fail AWS | IAM, KMS, SCP, VPC/network, throttling hoặc semantics khác | Smoke test sandbox với role thật |

### 13.2. Các bước chẩn đoán theo thứ tự

1. **Container:** LocalStack đã chạy/ready và service cần dùng có được hỗ trợ trong image hiện tại không?
2. **Network:** JVM chạy trên host, Compose container hay CI? Endpoint nào có thể truy cập từ đúng process?
3. **Endpoint:** SDK/AWSpring bean thực tế có đang dùng LocalStack hay đang dùng endpoint AWS thật?
4. **Region/credentials:** Client đã có region và dummy credentials của test chưa?
5. **Resource:** Bucket, queue, table hoặc secret đã được tạo ở endpoint và region đúng chưa?
6. **Serialization/lifecycle:** Payload, listener container, queue URL, acknowledgement và startup thứ tự đúng chưa?
7. **Service semantics:** Nếu lỗi chỉ xảy ra ở AWS thật, kiểm tra IAM/KMS/network, quota, retry và hành vi riêng của dịch vụ.

Không “sửa” lỗi kết nối bằng cách cấp IAM AdministratorAccess hoặc copy access key thật vào profile local. Nếu emulator hoạt động nhưng code production thất bại, cần xác định tầng sai trước.

### 13.3. Không ghi log secrets khi debug

Khi bật SDK HTTP logging hoặc trace, có nguy cơ log request/response headers, access tokens hoặc payload. Trong bài test, dữ liệu nên là **giả và không nhạy cảm**. Đối với Secrets Manager hoặc service có dữ liệu mật, kiểm tra logging/masking và không lưu secret thật trong LocalStack fixture.

## 14. LocalStack khác AWS thật ở đâu?

Emulator có thể hỗ trợ một API nhưng không đảm bảo mọi hành vi đều giống cloud provider:

| Nhóm khác biệt | Ví dụ | Hệ quả kiểm thử |
| --- | --- | --- |
| IAM/identity | Workload role, STS, trust policy, SCP, resource-based policy | LocalStack pass không chứng minh quyền production |
| KMS/encryption | Customer-managed key, key policy, encryption context | Cần test trên AWS sandbox khi luồng dùng KMS thật |
| S3 behavior | Bucket addressing, multipart, consistency/edge cases, object versioning | Kiểm chứng use case thực tế và dữ liệu lớn riêng |
| SQS behavior | Long polling, visibility timeout, FIFO, DLQ/redrive, duplicate delivery | Thiết kế idempotency và test AWS thật cho luồng quan trọng |
| Network | VPC endpoint, private DNS, proxy, TLS, latency vùng | Local emulator không thay được test hạ tầng |
| Quota/throttling | Rate limit, throughput và giới hạn tài khoản/vùng | Cần load/performance test có kiểm soát |
| Version/API | Tính năng mới chỉ có ở AWS hoặc có giới hạn theo LocalStack edition | Chọn phiên bản/edition hỗ trợ và kiểm tra release notes |
| Vận hành | CloudWatch metrics, CloudTrail, IAM audit, HA và recovery | Cần quan sát production/sandbox thật |

Với SDK/AWSpring, **bề mặt API giống nhau** giúp giảm công viết integration test, nhưng không xóa sự khác biệt về quyền, triển khai, chi phí và semantics của managed service.

## 15. Một quy trình kiểm thử hợp lý cho module đa cloud

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** còn hướng tới các dịch vụ Azure và Google Cloud. Bài LocalStack minh họa mẫu **adapter → client SDK → endpoint test** mà bạn có thể áp dụng khái niệm tương tự với emulator khác.

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Local emulator | LocalStack theo dịch vụ và edition | Azurite cho Azure Storage, emulator riêng khi có | Pub/Sub emulator, Firestore emulator và các emulator theo dịch vụ |
| Client trong Spring | AWSpring + AWS SDK Java v2 | Spring Cloud Azure + Azure SDK | Spring Cloud GCP + Google Cloud Java client |
| Cấu hình test | Endpoint override + region + dummy credentials | Storage connection/endpoint + credential test | Emulator host + project test/ADC thích hợp |
| Điều phải kiểm tra trên cloud thật | IAM role, resource policy, KMS, region/VPC | Managed Identity/RBAC, resource endpoint | Service account/IAM, project/location |

**Không cố tạo một cấu hình endpoint chung cho mọi provider**. S3/SQS, Azure Blob Storage và Google Cloud Storage có API, mô hình resource và cơ chế xác thực riêng. Tầng nghiệp vụ có thể dùng interface chung như `DocumentStore` hoặc `EventPublisher`, còn adapter và kiểm thử tích hợp phải tôn trọng khác biệt từng provider.

### 15.1. Chiến lược kiểm thử nhiều tầng

~~~mermaid
flowchart TD
    U["Unit tests<br/>Fake/mock adapter"] --> I["Integration tests<br/>LocalStack / emulator"]
    I --> S["Smoke tests<br/>AWS sandbox / Azure / GCP test project"]
    S --> O["Operational tests<br/>IAM, network, load, metrics, recovery"]
~~~

- **Unit test** xác minh logic nghiệp vụ nhanh, không cần Docker hoặc cloud.
- **Integration test với emulator** xác minh SDK wiring, serialization và một tập operation gần thực tế.
- **Smoke test trên cloud sandbox** xác minh identity, IAM, resource và network của môi trường mục tiêu.
- **Operational test** đánh giá timeout, retry, concurrency, quota, observability và failure recovery.

Mỗi tầng trả lời một câu hỏi khác nhau. Dùng LocalStack thay hết các tầng còn lại sẽ tạo khoảng trống về IAM, bảo mật secret và hành vi sản phẩm cloud.

## 16. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây ứng dụng Spring Boot `document-service` nhận nội dung văn bản, lưu file vào bucket `training-documents-local` và phát event `DocumentUploaded` lên queue `training-events-local`. Một consumer nhận event để kiểm tra object vừa tạo.

### Nhiệm vụ A — Khởi động và chuẩn bị môi trường

1. Viết Docker Compose chạy LocalStack, chỉ bind edge port trên loopback.
2. Khởi chạy container và kiểm tra trạng thái sẵn sàng.
3. Dùng AWS CLI với dummy credentials và `--endpoint-url` để tạo bucket/queue.
4. Ghi lại endpoint đúng cho ứng dụng chạy **trên host** và ứng dụng chạy **trong Compose network**.
5. Giải thích vì sao không cần access key thật để thực hiện các lệnh lên emulator.

### Nhiệm vụ B — Gọi AWS SDK v2

1. Viết `S3Client` dùng `endpointOverride`, `Region.US_EAST_1`, `StaticCredentialsProvider` test và path-style.
2. Thực hiện một vòng `PutObject → GetObject`, kiểm tra byte/string đọc về giống dữ liệu ban đầu.
3. Viết `SqsClient` gửi JSON event, nhận message và `DeleteMessage` bằng receipt handle.
4. Thử gửi message tới queue không tồn tại; phân tích exception và thứ tự kiểm tra endpoint/region/resource.

### Nhiệm vụ C — Tích hợp Spring Cloud AWS

1. Import BOM AWSpring tương thích, thêm S3/SQS starter.
2. Tạo `application-local.yml` với dummy credentials, region và endpoint theo dịch vụ.
3. Viết `DocumentStorageAdapter` bằng `S3Template`, `DocumentEventPublisher` bằng `SqsTemplate`.
4. Tạo `@SqsListener`, provision queue trước context startup và xử lý payload idempotent.
5. Đảm bảo profile `local` không được bật trong staging/production.

### Nhiệm vụ D — Tự động hóa với Testcontainers

1. Chuyển test từ LocalStack thủ công sang `LocalStackContainer`.
2. Dùng `@DynamicPropertySource` lấy endpoint thực từ Testcontainers thay vì hard-code host/port.
3. Đảm bảo container/tài nguyên sẵn sàng trước khi listener Spring khởi động.
4. Chạy test với bucket/queue riêng cho từng lượt test và cleanup theo lifecycle.
5. Mô tả khác biệt giữa test vừa chạy và smoke test trên AWS sandbox có IAM role thật.

### Nhiệm vụ E — Debug các lỗi cố ý

| Tình huống | Câu hỏi cần trả lời |
| --- | --- |
| App nằm trong Docker container nhưng dùng `localhost:4566` | `localhost` đang chỉ tới container nào? |
| S3 báo `UnknownHostException` cho `bucket.localhost` | S3 addressing style và DNS đang hoạt động ra sao? |
| SQS listener báo queue không tồn tại | Queue đã được tạo trước ApplicationContext chưa? Client đang dùng endpoint nào? |
| JVM có `AWS_PROFILE=prod-readonly`, test chỉ override region | Làm sao ngăn test gọi nhầm AWS thật? |
| LocalStack test pass nhưng ECS bị 403 | Cần kiểm tra IAM task role, bucket/queue policy và KMS thế nào? |
| CI chạy test trên Docker daemon từ xa | Vì sao `localhost:4566` không đáng tin cậy, và Testcontainers cung cấp gì? |

### Tiêu chí đạt

Bài thực hành đạt khi:

- Có thể khởi động LocalStack và tạo resource giả lập từ đầu.
- Ghi/đọc S3 và gửi/nhận/xóa message SQS thành công qua SDK v2.
- Spring Boot dùng đúng AWSpring bean và endpoint/credentials của profile local.
- Integration test tự cấp endpoint, không phụ thuộc port cố định hoặc AWS profile developer.
- Có ranh giới cấu hình tránh request từ test/local tác động vào production.
- Nêu được ít nhất ba giới hạn của LocalStack và một smoke test cần chạy trên AWS sandbox.

## 17. Ghi nhớ

**Thiết lập kết nối AWS giả lập bằng LocalStack** gồm bốn thành phần cần luôn đi cùng nhau: **emulator đã sẵn sàng, endpoint đúng theo network, region nhất quán và dummy credentials cho test**. Sau đó mới có ý nghĩa kiểm tra resource S3/SQS, AWS SDK clients và các abstraction của Spring Cloud AWS.

Ở máy host, endpoint thường là `http://localhost:4566`; trong Compose network, có thể dùng `http://localstack:4566`; với Testcontainers, lấy endpoint do container runtime cung cấp. S3 giả lập thường cần path-style khi DNS virtual-hosted không phù hợp, và SQS cần queue URL thực tế mà emulator trả về. SQS listener phải được chuẩn bị tài nguyên đúng thời điểm Spring context khởi động.

LocalStack giúp kiểm thử thao tác tích hợp nhanh và lặp lại được, nhưng **không chứng minh IAM/KMS, network, quota và mọi hành vi AWS production**. Một quy trình phát triển tốt kết hợp unit test, emulator integration test và smoke test trên AWS sandbox có quyền tối thiểu, từ đó tạo nền tảng vững cho các bài tiếp theo về storage, messaging, dữ liệu và secret, cũng như thực hành với Azure và Google Cloud.
