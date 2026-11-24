# Thay thế thư viện hoặc connector đã ngừng bảo trì

Một thư viện cloud có thể vẫn tải được từ Maven Central, vẫn biên dịch và thậm chí vẫn chạy trong production sau khi nhà cung cấp ngừng bảo trì. Điều đó không có nghĩa thư viện còn nhận bản vá bảo mật, hỗ trợ service mới hoặc tương thích với JDK và Spring Boot hiện tại. Khi dependency đã deprecated, archived hoặc end-of-support, đội phát triển cần xác định replacement được duy trì, lập kế hoạch chuyển đổi và chứng minh hành vi của ứng dụng vẫn đúng.

Việc thay thế thường không phải là đổi một tọa độ Maven. API mới có thể thay đổi cách tạo client, model request/response, credential chain, retry, async processing, pagination, transaction hoặc message settlement. Một connector có thể tự động đọc service binding trong môi trường cũ; replacement có thể yêu cầu khai báo cấu hình rõ ràng. Nếu chỉ sửa import cho đến khi build xanh, các khác biệt này dễ xuất hiện sau khi deploy.

Bài thuộc chương **Nâng cấp tích hợp** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Bài tập trung vào cách đánh giá thư viện thay thế, migration connector và SDK theo từng provider, kiểm tra tương thích và triển khai thay đổi an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện dependency deprecated, archived, maintenance-only hoặc end-of-support.
- Phân biệt thư viện tích hợp Spring Cloud, SDK của nhà cung cấp và connector của nền tảng triển khai.
- Đánh giá replacement theo support policy, compatibility, bảo mật, API và chi phí migration.
- Thay Spring Cloud Connectors bằng Java CFEnv khi ứng dụng chạy trên Cloud Foundry.
- Chuyển AWS SDK for Java 1.x sang AWS SDK for Java 2.x.
- Chuyển Azure Java SDK cũ sang các package hiện hành trong `com.azure`.
- Thay App Engine legacy bundled APIs bằng dịch vụ Google Cloud độc lập và Cloud Client Libraries khi phù hợp.
- Giữ dependency hội tụ bằng BOM của đúng hệ sinh thái.
- Kiểm thử authentication, authorization, retry, timeout, payload, ordering và resource lifecycle.
- Triển khai migration theo từng service, có quan sát và rollback.

## 2. Nhận diện một thư viện đã hết vòng đời

Không nên quyết định chỉ dựa vào số phiên bản hoặc lần phát hành cuối. Hãy kiểm tra trạng thái do maintainer công bố.

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Active / Supported | Có maintainer, phát hành và xử lý lỗi theo chính sách | Có thể tiếp tục dùng nếu tương thích |
| Deprecated | Được khuyến nghị chuyển sang API/package khác | Lập kế hoạch migration trước mốc xóa hoặc hết hỗ trợ |
| Maintenance mode | Chỉ nhận một nhóm bản sửa giới hạn, có thể không hỗ trợ tính năng/service mới | Đánh giá rủi ro và lên kế hoạch thay thế |
| End-of-support | Không còn bản cập nhật hoặc bản phát hành chính thức | Ưu tiên migration, nhất là với thành phần xử lý dữ liệu/credential |
| Archived | Repository chỉ đọc hoặc không còn phát triển | Tìm maintainer/replacement khác và đánh giá khả năng tự duy trì |
| Unsupported combination | Thư viện vẫn được duy trì nhưng không hỗ trợ Boot/JDK/provider version của ứng dụng | Nâng cả tổ hợp hoặc thay thư viện |

Các tín hiệu cần kiểm tra:

- Trang support policy hoặc danh sách deprecated chính thức.
- Release notes, changelog và ngày phát hành gần nhất.
- Repository có bị archive không; issue và pull request có được xử lý không.
- CVE/advisory có bản vá cho nhánh đang dùng không.
- Compatibility matrix có còn liệt kê Spring Boot, Spring Cloud train và JDK của ứng dụng không.
- Maven/Gradle có cảnh báo deprecated hoặc dependency conflict không.
- Nhà cung cấp có package thay thế và migration guide chính thức không.

Một dependency không có bản phát hành trong vài tháng chưa đủ để kết luận đã EOL. Ngược lại, một thư viện có bản phát hành gần đây vẫn có thể bị tuyên bố deprecated hoặc chỉ hỗ trợ một số nhánh. Luôn lấy support policy của maintainer làm nguồn chính.

### 2.1. Ví dụ về các mốc đã công bố

Các ví dụ dưới đây cho thấy vì sao cần phân biệt trạng thái và ngày hỗ trợ:

- AWS SDK for Java 1.x chuyển sang maintenance mode ngày 31-07-2024 và đạt end-of-support ngày 31-12-2025. Tại thời điểm 24-11-2026, SDK v1 không còn nhận cập nhật hoặc phát hành mới; AWS khuyến nghị chuyển sang SDK v2.
- Spring Cloud Connectors starter bị deprecated trong Spring Boot 2.2 để chuyển sang Java CFEnv và bị loại khỏi dependency management của Spring Boot 2.3.
- Microsoft công bố thư viện Java Service Bus cũ `com.microsoft.azure:azure-servicebus` đã retired ngày 30-09-2026; package thay thế là `com.azure:azure-messaging-servicebus`.
- Danh sách Azure SDK deprecated ghi nhận nhiều package Storage v8, Event Hubs và Key Vault cũ đã hết thời hạn hỗ trợ. Package thay thế và migration guide được liệt kê theo từng dịch vụ.
- App Engine Java 8 first-generation runtime bị deprecated từ 31-01-2026 và không còn cho phép deploy mới. Một số legacy bundled APIs vẫn có thể dùng trong second-generation runtime, nhưng Google khuyến nghị chuyển sang dịch vụ độc lập và Cloud Client Libraries khi có lựa chọn phù hợp.

Các mốc này phải được kiểm tra lại ở trang support hiện hành trước khi lập kế hoạch cho dự án khác. Không suy ra ngày EOL của một thư viện chỉ từ ngày EOL của thư viện khác cùng nhà cung cấp.

## 3. Phân biệt SDK, Spring integration và connector

Một ứng dụng Spring Cloud có thể dùng ba lớp thư viện:

| Lớp | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| Provider SDK | Gọi API dịch vụ cloud trực tiếp | AWS SDK, Google Cloud Java libraries, Azure SDK |
| Spring integration | Cung cấp auto-configuration, Spring abstractions, listener/template và property binding | Spring Cloud AWS, Spring Framework on Google Cloud, Spring Cloud Azure |
| Platform connector | Đọc service binding/environment của nền tảng và chuyển thành cấu hình cho ứng dụng | Spring Cloud Connectors, Java CFEnv |

Ba lớp có thể phụ thuộc lẫn nhau nhưng không thay thế nhau hoàn toàn. Ví dụ:

- AWS SDK v1 → v2 là migration SDK; Spring Cloud AWS có migration/version line riêng.
- Spring Cloud Connectors → Java CFEnv là thay thế connector cho Cloud Foundry service binding; nó không thay AWS SDK, Azure SDK hoặc Google Cloud client.
- `com.microsoft.azure:azure-servicebus` → `com.azure:azure-messaging-servicebus` là thay thế Azure service client; nếu ứng dụng dùng Spring Cloud Azure Service Bus starter, cần kiểm tra starter đã quản lý SDK mới nào.

Trước khi thay thế, xác định dependency đang cung cấp chức năng nào. Nếu bỏ một starter mà không thay phần auto-configuration hoặc service binding mà starter cung cấp, ứng dụng có thể compile nhưng không còn tạo DataSource, messaging client hoặc credential provider khi chạy.

## 4. Tiêu chí lựa chọn replacement

Một replacement tốt cần giải quyết được vấn đề vòng đời và đáp ứng yêu cầu runtime của ứng dụng.

| Tiêu chí | Câu hỏi cần trả lời | Bằng chứng cần lưu |
| --- | --- | --- |
| Support | Ai duy trì? Có support policy và security update không? | Trang support, repository, release cadence |
| Compatibility | Có hỗ trợ JDK, Boot, Cloud train và SDK BOM đang chọn không? | Compatibility matrix và release notes |
| Security | Credential chain, TLS, token refresh và CVE được xử lý thế nào? | Security docs/advisory |
| API fit | Có đủ thao tác ứng dụng đang dùng không? | API reference và feature matrix |
| Behavioral fit | Retry, timeout, ordering, ack, pagination, consistency có tương đương không? | Migration guide và contract tests |
| Operations | Có metrics, tracing, health, connection pooling và graceful shutdown không? | Observability docs và integration tests |
| Data migration | Có đổi format, schema, metadata, ID hoặc semantics không? | Data migration plan |
| Ecosystem | Có Spring starter, test support, emulator hoặc Testcontainers không? | Starter docs và test modules |
| Licensing | License và điều khoản hỗ trợ có phù hợp không? | LICENSE và vendor policy |
| Exit cost | Có thể thay tiếp nếu provider đổi chính sách không? | Adapter boundary và domain port |

Không chọn replacement chỉ vì nó có cùng tên dịch vụ. Một thư viện queue mới có thể không giữ nguyên thứ tự message, visibility timeout, dead-letter behavior hoặc cách xác nhận message. Một thư viện object storage mới có thể đổi metadata encoding, multipart upload, checksum hoặc cách tạo signed URL.

### 4.1. Kiểm tra compatibility trước khi viết lại code

Lập bảng phiên bản:

```text
JDK:                    21
Spring Boot:            4.x
Spring Cloud train:     2026.x
Provider integration:   release line được matrix xác nhận
Provider SDK:           version do BOM quản lý
Runtime platform:       Cloud Run / ECS / Azure App Service / Cloud Foundry
```

Đây là cấu trúc inventory, không phải một tổ hợp version cụ thể. Với Spring Cloud provider, luôn đọc matrix của từng dự án. Không suy luận rằng Spring Cloud core hỗ trợ một Boot version thì mọi provider integration cũng hỗ trợ version đó.

### 4.2. Kiểm tra dependency graph và API thực tế

Maven:

```bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aws-java-sdk-s3 --configuration runtimeClasspath
```

Tìm cả package import và artifact coordinates. Một dependency cũ có thể được kéo vào transitively dù đã xóa khỏi pom.xml của module chính.

Ví dụ tìm legacy package trong Java:

```bash
rg -n "com\\.amazonaws|com\\.microsoft\\.azure|org\\.springframework\\.cloud\\.connectors" .
rg -n "spring-boot-starter-cloud-connectors|aws-java-sdk-|azure-servicebus|azure-storage-blob" .
```

Kiểm tra thêm build.gradle, version catalog, parent POM, buildSrc, Dockerfile, Helm, Terraform, workflow CI/CD, sample và test fixture. Không chỉ grep trong src/main/java.

## 5. Thay Spring Cloud Connectors bằng Java CFEnv

Spring Cloud Connectors từng giúp ứng dụng đọc `VCAP_SERVICES`, tìm service binding và tự cấu hình kết nối trong Cloud Foundry. Spring Boot 2.2 đã deprecated `spring-boot-starter-cloud-connectors` để chuyển sang Java CFEnv; Spring Boot 2.3 đã loại starter này khỏi managed dependencies.

Java CFEnv đọc và phân tích `VCAP_SERVICES`, cung cấp thông tin service/credentials và có module Spring Boot để ánh xạ binding sang property chuẩn như `spring.datasource.url`.

### 5.1. Chọn module CFEnv

| Module | Công dụng |
| --- | --- |
| `java-cfenv` | Core parser cho `VCAP_SERVICES`, dùng được với Java application bất kỳ |
| `java-cfenv-jdbc` | Hỗ trợ tìm JDBC service và tạo JDBC URL |
| `java-cfenv-boot` | `EnvironmentPostProcessor` ánh xạ binding thành Spring Boot properties |
| `java-cfenv-boot-pivotal-scs` | Hỗ trợ Spring Cloud Services như Config Server và Service Registry |
| `java-cfenv-boot-pivotal-sso` | Hỗ trợ Single Sign-On service |
| `java-cfenv-all` | Gói nhiều module và kích hoạt profile `cloud` khi chạy trên Cloud Foundry |
| `java-cfenv-test-support` | Helper phục vụ test |

Chọn module nhỏ nhất đáp ứng ứng dụng. Nếu Java buildpack v5 tự thêm `java-cfenv-all`, hãy kiểm tra dependency trước khi khai báo một module trùng lặp.

Tài liệu Cloud Foundry hiện phân phiên bản theo Spring Boot: Java CFEnv 4.x cho Boot 4.x (từ 4.0.2), 3.x cho Boot 3.x (từ 3.5.3) và 2.x cho Boot 2.x đã EOL. Kiểm tra compatibility matrix trước khi chọn version.

### 5.2. Thay dependency

Xóa các dependency legacy, ví dụ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cloud-connectors</artifactId>
</dependency>
```

Hoặc các module Spring Cloud Connectors:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-connectors-core</artifactId>
</dependency>
```

Thêm module CFEnv cho Spring Boot:

```xml
<dependency>
    <groupId>io.pivotal.cfenv</groupId>
    <artifactId>java-cfenv-boot</artifactId>
    <version>4.0.2</version>
</dependency>
```

`4.0.2` là ví dụ version trong tài liệu Cloud Foundry cho Spring Boot 4.x; hãy chọn bản phù hợp với Boot của dự án tại thời điểm migration.

### 5.3. Tận dụng Spring Boot auto-configuration

`java-cfenv-boot` cung cấp `EnvironmentPostProcessor`, ví dụ `CfDataSourceEnvironmentPostProcessor`, để đặt `spring.datasource.url` từ service binding. Spring Boot tiếp tục tạo `DataSource` theo cấu hình chuẩn.

Nếu cần đọc binding trực tiếp:

```java
import io.pivotal.cfenv.core.CfEnv;
import io.pivotal.cfenv.core.CfService;

public class CloudFoundryBindingReader {

    public String redisHost() {
        CfEnv cfEnv = new CfEnv();
        CfService service = cfEnv.findServiceByTag("redis");
        return service.getHost();
    }
}
```

Với JDBC, có thể dùng `CfJdbcEnv` để đọc URL, username, password và driver class. Không cần tự parse JSON của `VCAP_SERVICES`.

### 5.4. Các thay đổi code cần rà soát

- Xóa annotation `@ServiceScan` hoặc `@CloudScan` do Spring Cloud Connectors cung cấp.
- Placeholder cũ `cloud.<property>` có thể cần chuyển sang `vcap.<property>`.
- `java-cfenv-all` kích hoạt Spring profile `cloud`; các module nhỏ hơn không tự kích hoạt profile này.
- Nếu cần nhiều service instance cùng loại, đọc credentials bằng CFEnv rồi cấu hình từng client rõ ràng. Không giả định mapper tự chọn đúng instance.
- Nếu có custom Spring Cloud Connector extension, chuyển logic thành Spring Boot auto-configuration và viết CFEnv extension để ánh xạ `VCAP_SERVICES` sang property.

Java CFEnv là giải pháp cho Cloud Foundry service binding. Với ứng dụng chạy trực tiếp trên ECS, GKE, Cloud Run hoặc Azure App Service, hãy dùng identity và configuration mechanism của nền tảng tương ứng.

## 6. Chuyển AWS SDK for Java 1.x sang 2.x

AWS SDK for Java 1.x đã end-of-support ngày 31-12-2025. AWS khuyến nghị chuyển sang SDK 2.x. SDK v1 cũ vẫn có thể tiếp tục chạy với các bản đã phát hành, nhưng không còn nhận bản cập nhật hoặc release mới.

### 6.1. Khác biệt chính

| Thành phần | SDK v1 | SDK v2 |
| --- | --- | --- |
| Maven groupId | `com.amazonaws` | `software.amazon.awssdk` |
| Package | `com.amazonaws...` | `software.amazon.awssdk...` |
| Client | `AmazonS3`, `AmazonDynamoDB` | `S3Client`, `DynamoDbClient` |
| Tạo client | Builder v1 hoặc constructor | Builder v2 |
| Model | Có setter/mutable request | Immutable model, builder |
| Getter/setter | `getX`, `setX`, `withX` | `x`, `x(...)` |
| Response class | `*Result` | `*Response` |
| Async | API riêng của v1 | `CompletableFuture` và non-blocking HTTP client |
| Pagination | Nhiều thao tác phải lặp token | Có paginator cho API hỗ trợ |

Một số package v1 có chữ `v2` trong tên, ví dụ `com.amazonaws.services.dynamodbv2`, nhưng vẫn thuộc SDK v1. Dấu hiệu đáng tin cậy là groupId/package root và dependency tree.

### 6.2. Thêm BOM v2 và chuyển artifact

Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>AWS_SDK_V2_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
</dependencies>
```

BOM quản lý các module SDK v2 đồng bộ. Thay `AWS_SDK_V2_VERSION` bằng bản đã chọn theo support policy tại thời điểm nâng cấp. Nếu ứng dụng dùng Spring Cloud AWS, kiểm tra BOM và compatibility matrix của Spring Cloud AWS trước khi thêm hoặc override AWS SDK BOM. Tránh import nhiều BOM mà không kiểm tra dependency resolution.

### 6.3. Ví dụ chuyển S3 client

SDK v1:

```java
AmazonS3 s3 = AmazonS3ClientBuilder.standard()
    .withRegion(Regions.AP_SOUTHEAST_1)
    .build();

ObjectListing listing = s3.listObjects(bucketName);
String firstKey = listing.getObjectSummaries()
    .get(0)
    .getKey();
```

SDK v2:

```java
try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {

    ListObjectsV2Request request = ListObjectsV2Request.builder()
        .bucket(bucketName)
        .build();

    s3.listObjectsV2Paginator(request)
        .contents()
        .forEach(object -> System.out.println(object.key()));
}
```

SDK v2 dùng model immutable và paginator cho việc duyệt toàn bộ kết quả. Nếu chỉ gọi `listObjectsV2`, kết quả có thể chỉ là một page; hãy chọn paginator khi nghiệp vụ cần duyệt tất cả object.

### 6.4. Credential chain có thể đổi hành vi

AWS SDK v2 thay đổi một số chi tiết của credential provider:

- Default credentials provider dùng builder hoặc `create()` thay cho constructor cũ.
- Thứ tự ưu tiên giữa system properties và environment variables khác SDK v1; SDK v2 kiểm tra system properties trước environment variables.
- Profile file format và một số provider class/method thay đổi.
- Asynchronous credential refresh không còn mặc định trong một số provider; cấu hình rõ khi ứng dụng cần.

Sau migration, kiểm tra credential source thực tế trong local, CI, ECS task role, EC2 instance profile, EKS web identity và Lambda. Một biến môi trường cũ có thể bị system property ghi đè, làm ứng dụng dùng nhầm principal.

### 6.5. Dùng migration tool nhưng vẫn phải review

AWS cung cấp migration tool dựa trên OpenRewrite để tự động chuyển nhiều SDK v1 service client và S3 TransferManager. Tool không chuyển tất cả high-level API; ví dụ `DynamoDBMapper` cần migration thủ công sang `DynamoDbEnhancedClient`.

Quy trình phù hợp:

1. Chạy migration tool trên branch riêng.
2. Review mọi thay đổi import, artifact và model.
3. Tìm lại `com.amazonaws` trong toàn repository.
4. Chuyển các API không được tool hỗ trợ.
5. Kiểm tra credential chain, retry, HTTP client và resource close.
6. Chạy integration tests với IAM role giống production.
7. Xóa toàn bộ SDK v1 dependency sau khi không còn code hoặc thư viện nào cần.

AWS cho phép dùng v1 và v2 song song trong giai đoạn chuyển đổi. Dùng cách này theo service boundary hoặc module boundary; không để một luồng nghiệp vụ trộn request/response model của hai SDK.

## 7. Chuyển Azure Java SDK cũ sang Azure SDK hiện hành

Các Azure SDK Java hiện hành thường dùng Maven groupId `com.azure` và package bắt đầu bằng `com.azure`. Nhiều thư viện lịch sử dùng `com.microsoft.azure`. Danh sách deprecated của Azure công bố package thay thế và support end date theo từng dịch vụ.

### 7.1. Mapping package thường gặp

| Thư viện cũ | Replacement hiện hành |
| --- | --- |
| `com.microsoft.azure:azure-servicebus` | `com.azure:azure-messaging-servicebus` |
| `com.microsoft.azure:azure-storage` | `com.azure:azure-storage-blob` |
| Azure Storage Blob v8 (`CloudBlob*`) | Azure Storage Blob v12 (`BlobServiceClient`, `BlobClient`, ...) |
| `com.microsoft.azure:azure-eventhubs` | `com.azure:azure-messaging-eventhubs` |
| `com.microsoft.azure:azure-keyvault` | `azure-security-keyvault-secrets`, `azure-security-keyvault-keys`, `azure-security-keyvault-certificates` |
| `azure-documentdb` | `com.azure:azure-cosmos` |

Mapping là điểm bắt đầu. Hãy mở migration guide của dịch vụ cụ thể vì một số API mới thay đổi cách xử lý message, async, paging, retry hoặc credential.

### 7.2. Service Bus: QueueClient sang builder/processor client

Thư viện `com.microsoft.azure:azure-servicebus` đã retired ngày 30-09-2026. Replacement là `com.azure:azure-messaging-servicebus`.

Ví dụ tạo sender mới:

```java
ServiceBusSenderClient sender = new ServiceBusClientBuilder()
    .connectionString(connectionString)
    .sender()
    .queueName(queueName)
    .buildClient();

sender.sendMessage(new ServiceBusMessage("invoice-created"));
sender.close();
```

SDK mới dùng builder làm điểm tạo client, có client sync và async riêng. Việc nhận message thường dùng `ServiceBusProcessorClient` hoặc receiver client. Khi thay receiver, cần kiểm tra:

- Peek-lock và thời hạn lock.
- Auto-complete so với complete/abandon/dead-letter thủ công.
- Lock renewal và thời gian xử lý message.
- Max concurrent calls và prefetch.
- Session handling và ordering.
- Retry, error handler và connection sharing.

Không coi việc thay `QueueClient` bằng một receiver mới là hoàn tất nếu chưa test settlement và redelivery. Một message được complete sớm hoặc lock không được renew có thể gây mất xử lý hoặc duplicate nghiệp vụ.

### 7.3. Storage Blob v8 sang v12

Azure Blob SDK v8 dùng `CloudStorageAccount`, `CloudBlobClient`, `CloudBlobContainer` và `CloudBlockBlob`. V12 chuyển sang builder và client theo resource:

| v8 | v12 |
| --- | --- |
| `CloudStorageAccount` | `BlobServiceClientBuilder` |
| `CloudBlobClient` | `BlobServiceClient` |
| `CloudBlobContainer` | `BlobContainerClient` |
| `CloudBlob` | `BlobClient` |
| `CloudBlockBlob` | `BlockBlobClient` |

Ví dụ v12:

```java
BlobServiceClient serviceClient =
    new BlobServiceClientBuilder()
        .connectionString(connectionString)
        .buildClient();

BlobClient blobClient = serviceClient
    .getBlobContainerClient(containerName)
    .getBlobClient(blobName);

blobClient.uploadFromFile(filePath, true);
```

V12 bổ sung các async client dựa trên Reactor. Nếu ứng dụng đang dùng RxJava hoặc callback cũ, phải chuyển cách xử lý async và backpressure. Kiểm tra metadata, content type, access tier, lease, SAS token, multipart/block upload và checksum trước khi chuyển dữ liệu thật.

### 7.4. Authentication và Azure Identity

Các SDK mới tích hợp với `azure-identity` và mô hình `TokenCredential`. Ưu tiên `DefaultAzureCredential` hoặc managed identity khi môi trường triển khai hỗ trợ, thay vì đưa connection string hoặc account key vào code.

Khi thay SDK:

- Xác minh role assignment/RBAC cho data plane.
- Kiểm tra tenant, subscription, endpoint và cloud environment.
- Test credential chain trong developer workstation, CI và production.
- Kiểm tra token refresh và retry khi credential endpoint tạm thời lỗi.
- Đảm bảo Key Vault, Blob và Service Bus dùng đúng identity được cấp quyền.

## 8. Thay thế API Google Cloud/App Engine legacy

Không phải mọi API cũ của Google Cloud đều đã bị ngừng bảo trì. Cần xác định ứng dụng đang dùng thư viện client hiện hành, legacy bundled service của App Engine hay một API đặc thù của runtime.

App Engine Java 8 first-generation runtime bị deprecated từ 31-01-2026 và không còn cho phép deploy mới. Một số legacy bundled APIs vẫn có thể truy cập trong second-generation runtime qua App Engine API JAR, nhưng đó chỉ là đường chuyển tiếp. Khi có dịch vụ Google Cloud độc lập phù hợp, nên chuyển sang dịch vụ đó và Cloud Client Libraries.

### 8.1. Mapping App Engine legacy services

| API/dịch vụ cũ | Hướng thay thế | Lưu ý |
| --- | --- | --- |
| Blobstore | Cloud Storage | Chuyển object, metadata, URL và access control |
| Datastore bundled API | Firestore in Datastore mode / Datastore client libraries | Cùng underlying service nhưng cần đổi client và quyền |
| Memcache | Memorystore | Chọn Redis/Memcached theo kiến trúc, không giả định API tương thích |
| Task Queue push | Cloud Tasks | Cần chuyển queue/task API; có thể giữ queue hiện có trong một số lộ trình |
| Task Queue pull | Pub/Sub | Xác định lại ack, lease, redelivery và worker model |
| URL Fetch | Java HTTP Client hoặc HTTP client hiện đại | Kiểm tra timeout, proxy, TLS và retry |
| App Identity | OIDC ID token hoặc Identity Platform tùy use case | Rà soát audience, issuer và trust |
| Mail | SMTP-based provider | Đây là thay đổi nhà cung cấp, deliverability và suppression |
| Search | Elasticsearch hoặc dịch vụ search phù hợp | Rebuild index và kiểm tra query semantics |
| Images | Cloud Storage, Cloud Run image service, CDN hoặc thư viện xử lý ảnh | Không có replacement 1:1 cho mọi thao tác |

Một số legacy API như Blobstore, Datastore hoặc Task Queues có thể còn khả dụng trên Java second-generation runtime. Tuy nhiên, migration sang standalone service giúp ứng dụng ít phụ thuộc vào App Engine runtime và dễ chuyển sang Cloud Run hoặc môi trường khác.

### 8.2. Ví dụ Datastore client

Nếu chuyển App Engine Datastore sang Firestore in Datastore mode, ứng dụng dùng Cloud Datastore client library. Ví dụ dependency được quản lý qua Google Cloud Libraries BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>libraries-bom</artifactId>
            <version>GOOGLE_CLOUD_LIBRARIES_BOM_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-datastore</artifactId>
    </dependency>
</dependencies>
```

Thay `GOOGLE_CLOUD_LIBRARIES_BOM_VERSION` bằng version đã chọn từ trang BOM tại thời điểm nâng cấp. BOM giúp đồng bộ Cloud Client Libraries và các thư viện nền như gRPC, protobuf, Guava và Google HTTP Client. Nếu ứng dụng dùng Spring Framework on Google Cloud, kiểm tra BOM/compatibility matrix của Spring integration trước khi import thêm BOM độc lập.

### 8.3. Ví dụ Blobstore sang Cloud Storage

Cloud Storage client:

```java
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobId blobId = BlobId.of(bucketName, objectName);
BlobInfo blobInfo = BlobInfo.newBuilder(blobId)
    .setContentType("application/octet-stream")
    .build();

storage.create(blobInfo, Files.readAllBytes(filePath));
```

Ví dụ minh họa đường ghi object. Migration thực tế còn phải chuyển dữ liệu cũ, metadata, ACL/IAM, lifecycle, retention, signed URL và URL được lưu trong database. Không đổi Blobstore API trước rồi xóa dữ liệu cũ khi chưa có đối soát object count và checksum.

### 8.4. Không có replacement 1:1 cho mọi API

Một số dịch vụ legacy không có standalone product tương đương hoàn toàn. Khi đó, phải phân tích use case và chọn giải pháp third-party hoặc thiết kế lại. Ví dụ, App Engine Search không tự động chuyển thành Elasticsearch mà không cần xây lại index, analyzer, ranking và query mapping. Memcache sang Memorystore cũng yêu cầu kiểm tra eviction, TTL, serialization và network latency.

## 9. Tránh thay thế bằng một dependency khác cũng sắp hết hỗ trợ

Một replacement chỉ tốt khi có vòng đời rõ ràng. Trước khi chọn, kiểm tra:

- Release line hiện tại và support policy.
- Java baseline và Spring Boot compatibility.
- API version được hỗ trợ.
- Security update cadence.
- License và model hỗ trợ.
- Test support và local emulator.
- Tình trạng repository, issue, maintainer và release.
- Roadmap và hướng dẫn migration.

Đối với thư viện community, xem số maintainer hoạt động và khả năng phản hồi issue. Không lấy số GitHub stars làm tiêu chí duy nhất. Một dự án có nhiều người dùng nhưng không còn release hoặc security response vẫn có thể là rủi ro.

Nếu vendor SDK có replacement chính thức, ưu tiên đánh giá replacement đó trước. Nếu chọn third-party, ghi rõ ai chịu trách nhiệm vá lỗ hổng, cập nhật API dịch vụ và tương thích với JDK mới.

## 10. Giữ dependency hội tụ trong Spring Boot

Khi thay SDK, dependency graph thường thay đổi mạnh. Không tự đặt version cho từng module nếu nhà cung cấp có BOM.

| Hệ sinh thái | BOM cần xem |
| --- | --- |
| AWS SDK v2 | `software.amazon.awssdk:bom` |
| Google Cloud Java client libraries | `com.google.cloud:libraries-bom` |
| Azure SDK Java trực tiếp | `com.azure:azure-sdk-bom` |
| Spring Cloud AWS | Spring Cloud AWS dependencies BOM |
| Spring Framework on Google Cloud | Spring Cloud GCP dependencies BOM |
| Spring Cloud Azure | Spring Cloud Azure dependencies BOM |

Một ứng dụng dùng Spring Cloud provider starter nên ưu tiên BOM của integration tương ứng và làm theo tài liệu provider. Không thêm BOM SDK riêng nếu nó ghi đè các phiên bản mà starter đã kiểm soát, trừ khi đã xác minh tổ hợp.

Sau khi thay dependency, kiểm tra:

```bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
./gradlew dependencies --configuration runtimeClasspath
```

Tìm các dependency cũ còn bị kéo transitively. Chỉ dùng exclusion khi đã biết dependency nào kéo nó vào và có test chứng minh việc loại bỏ không làm mất class/runtime behavior.

## 11. Chiến lược migration theo từng service

Không cần thay toàn bộ provider integration trong một lần. Chia theo service và boundary để giới hạn phạm vi ảnh hưởng.

### 11.1. Tạo abstraction ở tầng nghiệp vụ

Thay vì để business service phụ thuộc trực tiếp vào `S3Client`, `BlobClient` hoặc `Storage`, định nghĩa port theo nghiệp vụ:

```java
public interface DocumentStore {
    void put(String documentId, InputStream content, String contentType);
    InputStream get(String documentId);
    void delete(String documentId);
}
```

Adapter AWS, Azure hoặc Google Cloud triển khai interface này. Khi thay SDK, có thể giữ nguyên nghiệp vụ và chỉ viết lại adapter.

Tương tự, với messaging:

```java
public interface InvoiceEventPublisher {
    void publish(InvoiceCreated event);
}
```

Không tạo abstraction quá chung như `CloudClient` có hàng chục method cho mọi provider. Port nên thể hiện use case thực tế và những semantics ứng dụng cần.

### 11.2. Dùng adapter/strangler theo từng bước

1. Thêm replacement dependency và giữ API cũ trong module adapter.
2. Viết implementation mới theo port.
3. Chạy contract tests trên cả implementation cũ và mới.
4. Chuyển một nhóm workload hoặc một loại resource sang adapter mới.
5. Đối soát kết quả và metrics.
6. Chuyển traffic chính.
7. Gỡ SDK cũ sau khi không còn caller hoặc transitive dependency.

Với storage, có thể copy/backfill object rồi so sánh metadata/checksum trước khi chuyển read path. Với database, cần kế hoạch schema và dual-read nếu có thay đổi format. Với queue, dual-publish có thể tạo duplicate; cần idempotency key và chiến lược deduplication trước khi bật.

## 12. Kiểm thử hành vi thay vì chỉ kiểm tra compile

Replacement phải được kiểm tra ở nhiều lớp.

| Nhóm test | Điều cần chứng minh |
| --- | --- |
| Compile/API | Code dùng đúng package, model và method mới |
| Dependency | Không còn SDK cũ ngoài phạm vi được chủ động giữ |
| Configuration | Endpoint, region, project, subscription, vault và profile đúng |
| Identity | Principal/token đúng, role/RBAC đủ và không dư quyền |
| Contract | Payload, metadata, status, error mapping giữ đúng semantics |
| Failure | Timeout, retry, backoff, circuit breaker và resource missing |
| Messaging | Ordering, ack, redelivery, DLQ, session và duplicate handling |
| Storage | Content type, metadata, checksum, multipart, ACL/IAM và signed URL |
| Data | Query, transaction, pagination, consistency và index |
| Performance | Latency, throughput, memory, connection pool và startup |
| Observability | Log correlation, metrics, traces và health indicators |
| Operations | Shutdown, client close, token refresh và rollback |

Các test quan trọng phải chạy với identity gần production. Mock không phát hiện được thiếu IAM permission, endpoint sai, TLS trust, credential chain hoặc khác biệt của service thật.

## 13. Triển khai và rollback

Trước khi rollout, lưu lại:

- Artifact/image digest cũ và mới.
- Dependency tree và SBOM của hai bản.
- Cấu hình runtime, endpoint và identity binding.
- Schema/data migration version.
- Queue subscription/consumer configuration.
- Metrics baseline và smoke test result.

Triển khai canary hoặc một nhóm instance trước. Theo dõi error rate theo provider API, latency, retry, queue backlog, DLQ, storage failure, token refresh và connection pool.

Rollback cần xem xét dữ liệu và message đã tạo bởi SDK mới. Không chỉ đưa image cũ trở lại nếu format metadata, schema hoặc event payload đã thay đổi. Nếu replacement ghi dữ liệu theo format không tương thích, phải có backward-compatible reader hoặc migration data riêng.

## 14. Bài thực hành: thay thế connector và SDK cũ trong invoice-service

**Bối cảnh:** `invoice-service` có các thành phần:

- Spring Cloud Connectors để đọc Cloud Foundry `VCAP_SERVICES`.
- AWS SDK for Java 1.x để lưu hóa đơn vào S3.
- Azure Service Bus client cũ để gửi sự kiện.
- App Engine legacy Task Queue API để xử lý tác vụ nền.
- Spring Boot và Spring Cloud provider integration cần được nâng lên các nhánh còn hỗ trợ.

Mục tiêu là thay các thư viện đã deprecated/EOL và giữ nguyên contract nghiệp vụ.

### Bước 1 — Lập inventory

Chạy:

```bash
./mvnw dependency:tree -Dverbose
rg -n "com\\.amazonaws|com\\.microsoft\\.azure|org\\.springframework\\.cloud\\.connectors" .
rg -n "spring-boot-starter-cloud-connectors|azure-servicebus|aws-java-sdk-|QueueFactory|TaskQueue" .
```

Ghi lại mọi service binding, S3 operation, message send/receive và Task Queue operation. Phân loại phần nào là SDK, connector và Spring integration.

### Bước 2 — Thay Cloud Foundry connector

- Xóa Spring Cloud Connectors starter và các connector module cũ.
- Thêm `java-cfenv-boot` phù hợp với Spring Boot.
- Xóa `@ServiceScan` và `@CloudScan`.
- Kiểm tra `VCAP_SERVICES` có chứa binding cần thiết.
- Kiểm tra profile `cloud` nếu ứng dụng phụ thuộc profile này.
- Nếu có nhiều database/Redis instance, viết cấu hình từng instance rõ ràng.

### Bước 3 — Thay AWS SDK v1

- Import AWS SDK v2 BOM.
- Thêm module `s3` và các module khác thực sự dùng.
- Chuyển `AmazonS3` sang `S3Client`.
- Chuyển request model mutable sang builder.
- Kiểm tra paginator, multipart transfer và metadata.
- Kiểm tra IAM role và credential precedence.
- Xóa `aws-java-sdk-*` sau khi mọi code đã chuyển.

### Bước 4 — Thay Azure Service Bus SDK cũ

- Xóa `com.microsoft.azure:azure-servicebus`.
- Thêm `com.azure:azure-messaging-servicebus`.
- Tạo sender bằng `ServiceBusClientBuilder`.
- Chuyển consumer sang processor/receiver API phù hợp.
- Kiểm tra peek-lock, settlement, session, retry và dead-letter.
- Test duplicate message và message lock expiry.

### Bước 5 — Thay Task Queue

Nếu ứng dụng dùng push queue, chuyển sang Cloud Tasks. Nếu dùng pull queue, đánh giá Pub/Sub. Không đổi tên queue rồi cho rằng semantics giống nhau. Kiểm tra retry schedule, target HTTP endpoint, auth token, deadline, ack, redelivery và rate limit.

### Bước 6 — Kiểm thử contract

- Upload hóa đơn lên S3 và so sánh object metadata/checksum.
- Gửi `InvoiceCreated` lên Service Bus và xác minh consumer xử lý đúng theo idempotency key.
- Chạy tác vụ nền với success, timeout, retry và dead-letter.
- Kiểm tra principal của AWS/Azure/GCP và quyền tối thiểu.
- So sánh latency và retry volume với baseline.

### Bước 7 — Canary và gỡ thư viện cũ

Deploy một revision mới, quan sát metrics và log. Khi các luồng đạt yêu cầu, chuyển traffic và xóa dependency cũ. Tạo SBOM mới để xác nhận không còn artifact đã EOL bị kéo vào runtime.

## 15. Checklist review trước khi merge

- [ ] Đã xác nhận trạng thái support/EOL từ maintainer.
- [ ] Đã ghi lại replacement chính thức và migration guide.
- [ ] Đã phân biệt SDK, Spring integration và platform connector.
- [ ] Đã kiểm tra JDK, Spring Boot, Spring Cloud và provider compatibility.
- [ ] Đã kiểm tra dependency tree và package import toàn repository.
- [ ] Đã xác định behavior nào của thư viện cũ đang được ứng dụng sử dụng.
- [ ] Đã chọn BOM phù hợp và kiểm tra dependency convergence.
- [ ] Đã kiểm tra credential chain, IAM/RBAC và token refresh.
- [ ] Đã kiểm tra retry, timeout, pagination và client lifecycle.
- [ ] Đã kiểm tra storage metadata, checksum và data migration.
- [ ] Đã kiểm tra messaging ack, ordering, duplicate và DLQ.
- [ ] Đã chạy contract tests và provider integration tests.
- [ ] Đã chạy canary và so sánh với baseline.
- [ ] Đã có kế hoạch rollback cho image, config, data và message.
- [ ] Đã gỡ dependency cũ sau khi không còn caller/transitive requirement.
- [ ] Đã cập nhật SBOM và dependency inventory.

## 16. Câu hỏi tự kiểm tra

1. Khác biệt giữa deprecated, maintenance mode, end-of-support và archived là gì?
2. Vì sao một dependency vẫn tải được từ Maven Central không có nghĩa nó còn được hỗ trợ?
3. Spring Cloud Connectors khác Java CFEnv ở vai trò nào?
4. Vì sao `java-cfenv-boot` có thể dùng cùng Spring Boot auto-configuration?
5. AWS SDK v1 và v2 khác nhau về package, model, client và credential chain như thế nào?
6. AWS migration tool không chuyển tất cả high-level APIs nào?
7. Vì sao cần kiểm tra paginator khi chuyển AWS SDK?
8. Azure Service Bus SDK mới thay đổi cách tạo sender/receiver ra sao?
9. Storage Blob v8 và v12 khác nhau ở client hierarchy nào?
10. App Engine Task Queue push và pull nên được thay bằng dịch vụ nào?
11. Vì sao Cloud Client Libraries BOM quan trọng với Google Cloud Java?
12. Vì sao replacement có thể cần thay đổi IAM/RBAC dù service name không đổi?
13. Tại sao không nên dual-publish message trong migration nếu chưa có idempotency?
14. Một adapter/domain port giúp giảm chi phí thay SDK như thế nào?
15. Những dữ liệu và metrics nào cần lưu trước khi canary?
16. Khi rollback, vì sao phải kiểm tra cả schema, object metadata và event payload?

## 17. Ghi nhớ

Thay thế thư viện đã ngừng bảo trì bắt đầu từ việc xác minh support policy và hiểu chính xác chức năng dependency đang cung cấp. Chọn replacement dựa trên compatibility, security, behavior và khả năng vận hành. Đừng chỉ thay artifact hoặc package rồi coi migration đã hoàn tất.

Với Cloud Foundry, Java CFEnv thay phần lớn nhu cầu đọc service binding cũ. Với AWS, SDK v1 đã EOL và cần chuyển sang v2. Với Azure, các package `com.microsoft.azure` cũ có mapping sang SDK `com.azure` hiện hành. Với Google Cloud, hãy chuyển các legacy bundled APIs sang standalone services/Cloud Client Libraries khi phù hợp và kiểm tra lại IAM. **Mỗi migration cần contract test, dependency convergence, rollout có quan sát và rollback bao gồm cả dữ liệu đã ghi.**

## Tài liệu tham khảo chính thức

- [Cloud Foundry — Configuring service connections and migrating to Java CFEnv](https://docs.cloudfoundry.org/buildpacks/java/configuring-service-connections.html)
- [Spring Boot 2.3 — Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes)
- [AWS — AWS SDK for Java 1.x end-of-support](https://github.com/aws/aws-sdk-java)
- [AWS — Migration from SDK for Java 1.x to 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration.html)
- [AWS — Migration tool and limitations](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-tool.html)
- [AWS — Differences between SDK v1 and v2](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-whats-different.html)
- [Azure — Deprecated Java SDK packages and replacements](https://azure.github.io/azure-sdk/releases/deprecated/java.html)
- [Azure — Service Bus Java migration guide](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/servicebus/azure-messaging-servicebus/migration-guide.md)
- [Azure — Storage Blob v8 to v12 migration guide](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/storage/azure-storage-blob/migrationGuides/V8_V12.md)
- [Google Cloud — Java Cloud Client Libraries BOM](https://docs.cloud.google.com/java/docs/bom)
- [Google Cloud — App Engine Java legacy bundled services and alternatives](https://docs.cloud.google.com/appengine/docs/standard/services/overview?tab=java)
- [Google Cloud — Migrate App Engine Java 8 to second-generation runtime](https://docs.cloud.google.com/appengine/migration-center/standard/migrate-to-second-gen/java-differences)
- [Google Cloud — Migrate Java push queues to Cloud Tasks](https://docs.cloud.google.com/appengine/migration-center/standard/java/migrating-push-queues)
- [Google Cloud — Migrate App Engine Datastore to Firestore in Datastore mode](https://docs.cloud.google.com/appengine/migration-center/standard/java/migrate-datastore)

