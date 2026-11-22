# Tích hợp Spring Cloud AWS và kiểm tra ma trận tương thích

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Spring Cloud AWS trong ứng dụng Spring Boot và phân biệt lớp tích hợp Spring với AWS SDK for Java 2.x.
- Đọc và áp dụng ma trận tương thích giữa Spring Cloud AWS, Spring Cloud release train, Spring Boot, Spring Framework, Java và AWS SDK.
- Chọn đúng release line 3.x hoặc 4.x; tránh ghép Spring Cloud AWS 2.x/3.x/4.x với Spring Boot không tương thích.
- Quản lý dependency bằng Spring Cloud AWS BOM, Spring Boot dependency management và AWS SDK BOM khi thực sự cần override.
- Chọn starter theo từng dịch vụ: S3, SQS, SNS, DynamoDB, Secrets Manager, Parameter Store, SES, CloudWatch và những tích hợp có sẵn.
- Hiểu auto-configuration của AwsCredentialsProvider, AwsRegionProvider, AWS clients và cách override chúng an toàn.
- Tích hợp S3 qua S3Client/S3Template, SQS qua SqsTemplate/@SqsListener, và cấu hình ngoài qua spring.config.import.
- Thiết kế IAM permissions theo least privilege, sử dụng workload role, quản lý endpoint/Region và không đưa credentials thật vào application config.
- Tùy chỉnh synchronous/asynchronous clients, HTTP timeouts, retries, connection pools và endpoint cho môi trường local.
- Kiểm thử integration bằng LocalStack + Testcontainers, xác minh compatibility qua dependency tree, build và startup test.
- Di chuyển ứng dụng từ Spring Cloud AWS 2.x lên 3.x/4.x; chẩn đoán lỗi version conflict, auto-configuration, IAM, Region, SQS listener và Config Data.

**Bối cảnh module:** Bài thuộc chương **Ứng dụng Java và Spring Boot** trong CLOUD_PROVIDERS_AWS. Hành trình AWS của module bao gồm Region/AZ, IAM, VPC, compute, storage, database, integration và serverless. Spring Cloud AWS giúp ứng dụng Spring sử dụng AWS theo các idiom quen thuộc của Spring, đồng thời dựa trên AWS SDK for Java để gọi các dịch vụ thật.

> **Phạm vi:** Nội dung tập trung vào Spring Cloud AWS 3.x/4.x và AWS SDK for Java 2.x. Ma trận dưới đây là ma trận theo release line được công bố bởi dự án; patch releases thay đổi theo thời gian. Luôn kiểm tra trang release/reference hiện hành và POM của phiên bản sẽ triển khai. Không xem một version number mới hơn là bằng chứng nó tương thích với mọi Spring Boot version.

## 1. Bài toán: ứng dụng Spring gọi AWS cần bao nhiêu lớp?

Một Spring Boot service nhận yêu cầu upload tài liệu, lưu file vào S3, phát sự kiện sang SQS và đọc thông tin kết nối từ Secrets Manager.

Nếu chỉ dùng AWS SDK, developer phải tự tạo clients, cấu hình Region, credentials provider, HTTP transport, lifecycle và mapping dữ liệu. Spring Cloud AWS bổ sung starter và auto-configuration để các client này hoạt động trong Spring ApplicationContext.

~~~mermaid
flowchart TB
    API[Spring MVC / WebFlux Controller] --> Service[Business services]
    Service --> S3[S3Template / S3Client]
    Service --> SQS[SqsTemplate / SqsAsyncClient]
    S3 --> AWS[(Amazon S3)]
    SQS --> QUEUE[(Amazon SQS)]
    BOOT[Spring Boot Config Data] --> SM[Secrets Manager]
    BOOT --> PS[Systems Manager Parameter Store]
    CORE[Spring Cloud AWS core] --> CRED[AwsCredentialsProvider]
    CORE --> REGION[AwsRegionProvider]
    CRED --> S3
    CRED --> SQS
    REGION --> S3
    REGION --> SQS
~~~

Có ba lớp cần hiểu:

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Spring Boot | Application context, dependency injection, configuration, lifecycle, health | @SpringBootApplication, @ConfigurationProperties |
| Spring Cloud AWS | Spring starter, auto-configuration, templates, listeners, config import | S3Template, SqsTemplate, @SqsListener |
| AWS SDK for Java 2.x | AWS API clients, SigV4 signing, credentials/Region providers, HTTP clients | S3Client, SqsAsyncClient, StsClient |

Spring Cloud AWS không thay thế AWS SDK. Nó cung cấp lớp tích hợp và tự động cấu hình; khi cần một AWS service hoặc API không có abstraction Spring riêng, ứng dụng vẫn có thể inject AWS SDK client trực tiếp.

## 2. Spring Cloud AWS là gì và khi nào nên dùng?

Spring Cloud AWS là dự án tích hợp các AWS services với Spring/Spring Boot theo các pattern như dependency injection, auto-configuration, configuration properties, message listener và Spring Config Data.

Một số giá trị chính:

- Tự cấu hình AWS Region và credentials provider cho AWS clients.
- Cung cấp starter theo từng dịch vụ để chỉ đưa dependency cần thiết vào classpath.
- Tích hợp S3, SQS, SNS, DynamoDB, SES, Parameter Store, Secrets Manager và CloudWatch.
- Cung cấp abstraction như S3Template, SqsTemplate, @SqsListener.
- Kết hợp AWS SDK clients với Spring lifecycle và configuration.
- Hỗ trợ test với LocalStack/Testcontainers.

### Khi nào chỉ cần AWS SDK?

Dùng AWS SDK trực tiếp là lựa chọn hợp lý nếu:

- Ứng dụng không dùng Spring;
- Chỉ cần một vài client SDK và không cần Spring abstraction;
- Dùng API mới hoặc dịch vụ chưa có Spring Cloud AWS integration;
- Muốn tự quản lý hoàn toàn client configuration.

### Khi nào Spring Cloud AWS có lợi?

Spring Cloud AWS phù hợp khi ứng dụng đã dùng Spring Boot và muốn:

- Auto-configure Region/credentials;
- Inject S3/SQS/DynamoDB clients;
- Dùng listener annotation và template;
- Load configuration từ Secrets Manager/Parameter Store;
- Tích hợp metrics và LocalStack theo Spring conventions.

Không cần ép mọi AWS API đi qua abstraction của Spring Cloud AWS. Có thể dùng starter cho những services được hỗ trợ và AWS SDK client cho phần còn lại.

## 3. Đọc ma trận tương thích: không chọn version theo cảm tính

Spring Cloud AWS phụ thuộc vào các Spring projects. Một release line được kiểm thử với những dòng Spring Cloud, Spring Boot và Spring Framework cụ thể.

<text color="secondary">Ma trận release line theo compatibility table của dự án Spring Cloud AWS; patch versions cần đối chiếu release notes trước khi khóa dependency.</text>

| Spring Cloud AWS | Spring Cloud train | Spring Boot | Spring Framework | AWS SDK |
| --- | --- | --- | --- | --- |
| 2.3.x | 2020.0.x (Ilford) | 2.4.x, 2.5.x | 5.3.x | 1.x |
| 2.4.x | 2021.0.x (Jubilee) | 2.6.x, 2.7.x | 5.3.x | 1.x |
| 3.0.x | 2022.0.x (Kilburn) | 3.0.x, 3.1.x | 6.0.x | 2.x |
| 3.1.x | 2023.0.x (Kilburn) | 3.2.x | 6.1.x | 2.x |
| 3.2.x | 2023.0.x | 3.2.x, 3.3.x | 6.1.x | 2.x |
| 3.3.x | 2024.0.x | 3.4.x | 6.2.x | 2.x |
| 3.4.x | 2025.0.x | 3.5.x | 6.2.x | 2.x |
| 4.x | 2025.1.x | 4.0.x | 7.0.x | 2.x |

**Cách đọc bảng:**

- Spring Cloud AWS 2.x gắn với AWS SDK for Java 1.x và Spring Boot 2.x.
- Spring Cloud AWS 3.x chuyển sang AWS SDK for Java 2.x, Spring Boot 3.x và Spring Framework 6.x.
- Spring Cloud AWS 4.x thuộc thế hệ Spring Boot 4.x/Spring Framework 7.x, vẫn dùng AWS SDK for Java 2.x.
- Spring Cloud AWS 3.4.x là release line cho Spring Boot 3.5.x.
- Spring Cloud AWS 4.x là release line cho Spring Boot 4.0.x trong compatibility table được dự án công bố.

**Ví dụ lựa chọn:**

| Project hiện có | Release line nên xem xét |
| --- | --- |
| Spring Boot 2.7.x legacy | Spring Cloud AWS 2.4.x nếu cần duy trì SDK v1 |
| Spring Boot 3.2.x | Spring Cloud AWS 3.1.x/3.2.x theo Spring Cloud train và patch |
| Spring Boot 3.4.x | Spring Cloud AWS 3.3.x |
| Spring Boot 3.5.x | Spring Cloud AWS 3.4.x |
| Spring Boot 4.0.x | Spring Cloud AWS 4.x |

Không ghép Spring Cloud AWS 4.x với Boot 3.5.x chỉ vì cả hai đều là major versions mới hơn. Cũng không nâng riêng Spring Framework hoặc Spring Cloud Commons ngoài ma trận rồi kỳ vọng compatibility verifier sẽ bảo vệ toàn bộ runtime.

## 4. Java version và build tool requirements

Spring Boot 3.x và 4.x hiện đại đều yêu cầu Java 17 trở lên theo system requirements tương ứng; các bản cụ thể có thể hỗ trợ thêm những Java releases mới hơn.

| Nền tảng | Điểm cần kiểm tra |
| --- | --- |
| Spring Boot 3.5.x | Java 17+, Spring Framework 6.2.x |
| Spring Boot 4.0.x | Java 17+, Spring Framework 7.0.x |
| Maven | Phiên bản Maven tối thiểu theo Spring Boot release |
| Gradle | Gradle wrapper nằm trong dải được Spring Boot release hỗ trợ |
| JDK CI | Nên giống JDK dùng compile/test và runtime production |
| AWS SDK for Java 2.x | Kiểm tra Java baseline của SDK release cụ thể và thư viện phụ thuộc |

Một dự án có thể compile trên JDK mới nhưng runtime container lại dùng JRE thấp hơn. Cần xác minh cả JDK chạy Maven/Gradle, maven.compiler.release hoặc Gradle toolchain, Java version trong Docker image và Java version của Lambda/ECS/EKS/EC2 runtime.

Ví dụ Maven compiler:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Nếu chọn Java 21 hoặc 25, kiểm tra thêm compatibility của Spring Boot, AWS SDK, native-image tooling và các thư viện phụ thuộc.

## 5. Chọn đúng Spring Cloud AWS BOM

**Bill of Materials (BOM)** quản lý các phiên bản module Spring Cloud AWS và dependencies liên quan theo một release line đã được dự án kiểm thử.

Thay vì khai báo version riêng cho từng starter, import BOM rồi dùng dependency không có version.

Ví dụ Maven cho một project Spring Boot 4.0.x và Spring Cloud AWS 4.2.1:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-aws.version>4.2.1</spring-cloud-aws.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.2.1</version>
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

Nếu project dùng Spring Boot 3.5.x, chọn bản Spring Cloud AWS 3.4.x phù hợp thay vì copy version 4.2.1 ở ví dụ trên.

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:4.2.1"))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")
}
~~~

BOM version phải khớp với release line Spring Boot/Spring Cloud của project.

## 6. Spring Boot BOM, Spring Cloud BOM và AWS SDK BOM phối hợp thế nào?

Ba BOM có phạm vi quản lý khác nhau:

| BOM | Quản lý |
| --- | --- |
| Spring Boot dependency management | Spring Boot, Spring Framework và nhiều dependency nền |
| Spring Cloud release BOM | Spring Cloud projects nếu ứng dụng dùng các module thuộc release train |
| Spring Cloud AWS dependencies BOM | Spring Cloud AWS modules và các dependency được dự án kiểm thử |
| AWS SDK for Java BOM | AWS SDK v2 modules như s3, sqs, sts, dynamodb |

Mặc định, để Spring Cloud AWS BOM chọn AWS SDK version đã được kiểm thử cùng release.

Nếu cần một AWS SDK version mới hơn version do Spring Cloud AWS BOM quản lý, tài liệu Spring Cloud AWS yêu cầu khai báo AWS SDK BOM trước BOM nào khác đang cấu hình AWS SDK dependencies trong dependency management. Sau khi override, cần test compatibility vì đã rời khỏi dependency set mặc định được dự án kiểm thử.

Ví dụ cấu trúc khi có lý do rõ ràng để override:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.2.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Không khai báo version khác nhau cho software.amazon.awssdk:s3, sqs, sts, auth và regions. Các SDK modules nên đồng bộ cùng một BOM.

## 7. Starter nào dùng cho AWS service nào?

Spring Cloud AWS cung cấp starter theo từng tích hợp. Chỉ thêm starter của service ứng dụng thực sự sử dụng.

| AWS integration | Maven artifact |
| --- | --- |
| Core auto-configuration | spring-cloud-aws-starter |
| S3 | spring-cloud-aws-starter-s3 |
| SQS | spring-cloud-aws-starter-sqs |
| SNS | spring-cloud-aws-starter-sns |
| SES | spring-cloud-aws-starter-ses |
| DynamoDB | spring-cloud-aws-starter-dynamodb |
| Parameter Store | spring-cloud-aws-starter-parameter-store |
| Secrets Manager | spring-cloud-aws-starter-secrets-manager |
| EC2 Instance Metadata | spring-cloud-aws-starter-imds |
| AppConfig (release lines có hỗ trợ) | spring-cloud-aws-starter-app-config |

Ngoài ra, các release line mới có thể bổ sung tích hợp như AppConfig, Spring Integration adapters, Kinesis binder và các thành phần khác. Kiểm tra danh sách starter trong reference docs của đúng release đang dùng.

### Starter đã kéo module lõi

Nếu thêm spring-cloud-aws-starter-s3, không cần thêm riêng module spring-cloud-aws-s3 chỉ để có API cơ bản. Starter đã khai báo module và dependencies cần thiết.

Không thêm tất cả starters vào mọi ứng dụng. Mỗi starter có thể kích hoạt auto-configuration, client, background listener/poller hoặc Config Data import tương ứng.

## 8. Tên package và thay đổi lớn giữa 2.x, 3.x, 4.x

| Thế hệ | AWS SDK | Package Spring Cloud AWS | Spring Boot |
| --- | --- | --- | --- |
| 2.x | AWS SDK v1 | org.springframework.cloud.aws... | 2.x |
| 3.x | AWS SDK v2 | io.awspring.cloud... | 3.x |
| 4.x | AWS SDK v2 | io.awspring.cloud... | 4.x |

Một số thay đổi khi nâng từ 2.x lên 3.x:

- Chuyển từ AWS SDK v1 sang v2; các clients và request/response models đổi package/API.
- Namespace cấu hình cũ cloud.aws.* chuyển sang spring.cloud.aws.* ở những property tương ứng.
- Spring Boot 3 dùng Jakarta APIs; thư viện còn phụ thuộc javax.* có thể gây lỗi.
- Parameter Store/Secrets Manager dùng Config Data import (spring.config.import) thay cho cách resolve prefix cũ.
- SQS message collection conversion và acknowledgment behavior có thay đổi.
- Một số tích hợp Cognito/RDS/EC2/ElastiCache/CloudFormation cũ không còn trong Spring Cloud AWS 3.x/4.x; dùng AWS SDK hoặc Spring project phù hợp.

Spring Cloud AWS 4.x tiếp tục trên nền Spring Boot 4 và Spring Framework 7. Khi nâng 3.x lên 4.x, kiểm tra Spring Boot 4 migration guide, Jackson version, Jakarta APIs, auto-configuration conditions và starter changes.

## 9. Auto-configuration: Spring Cloud AWS tạo bean nào?

Khi starter được đặt trên classpath, Spring Cloud AWS auto-configures core AWS components và các clients tương ứng.

Các thành phần cốt lõi:

- AwsCredentialsProvider: trả credentials để ký AWS requests.
- AwsRegionProvider: trả Region cho AWS clients.
- AWS SDK service clients: S3Client, SqsAsyncClient, SnsClient, DynamoDbClient...
- Spring abstractions: S3Template, SqsTemplate, listener containers và configuration property sources.

~~~mermaid
flowchart TD
    CP[Spring Boot Environment] --> AC[Spring Cloud AWS Auto Configuration]
    AC --> Cred[DefaultCredentialsProvider]
    AC --> Reg[DefaultAwsRegionProviderChain]
    AC --> S3C[S3Client]
    AC --> SQSC[SqsAsyncClient]
    AC --> DDB[DynamoDbClient]
    Cred --> S3C
    Cred --> SQSC
    Cred --> DDB
    Reg --> S3C
    Reg --> SQSC
    Reg --> DDB
    S3C --> S3T[S3Template]
    SQSC --> SQT[SqsTemplate / Listener containers]
~~~

Nếu cung cấp custom AwsCredentialsProvider bean hoặc AwsRegionProvider bean, auto-configuration mặc định tương ứng có thể không được tạo. Chỉ override khi có yêu cầu rõ ràng và bảo đảm custom provider xử lý đúng refresh/lifecycle.

## 10. Credentials provider: dùng identity của runtime

Spring Cloud AWS mặc định sử dụng AWS SDK DefaultCredentialsProvider chain. Các nguồn chính được kiểm tra theo thứ tự:

1. Java system properties;
2. Environment variables;
3. Web identity token;
4. Shared AWS profiles;
5. ECS/container credentials;
6. EC2 Instance Metadata Service (IMDS).

| Môi trường | Credentials nên dùng |
| --- | --- |
| Laptop developer | IAM Identity Center SSO profile / AWS profile |
| EC2 | Instance profile / IAM role |
| ECS | ECS task role |
| EKS | Pod Identity hoặc IRSA/web identity |
| CI/CD | OIDC federation hoặc role do runner assume |
| Cross-account | Source workload role + STS AssumeRole |

Không đặt static access key/secret trong application.yml hoặc Docker image. Thuộc tính spring.cloud.aws.credentials.access-key và secret-key tồn tại cho các tình huống đặc biệt/test, nhưng không nên dùng làm credentials production dài hạn.

### Local profile

Có thể đăng nhập SSO bằng AWS CLI rồi chọn profile qua environment:

~~~bash
aws sso login --profile dev-sso

# Linux/macOS
export AWS_PROFILE=dev-sso

# Windows PowerShell
$env:AWS_PROFILE = "dev-sso"
~~~

Nếu environment variables chứa credentials cũ, chúng có thể được chọn trước profile. Xác minh identity bằng aws sts get-caller-identity --profile dev-sso và kiểm tra AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN.

### Web identity trên EKS

Spring Cloud AWS hỗ trợ StsWebIdentityTokenFileCredentialsProvider cho môi trường Kubernetes/EKS. Starter có thể sử dụng token file và role ARN được môi trường thiết lập; khi cần cấu hình rõ ràng, các thuộc tính gồm:

~~~yaml
spring:
  cloud:
    aws:
      credentials:
        sts:
          role-arn: arn:aws:iam::111122223333:role/orders-api
          async-credentials-update: true
~~~

Chỉ khai báo role ARN khi cần override giá trị do EKS Pod Identity/IRSA setup cung cấp. Role trust policy phải tin đúng OIDC provider/service account hoặc identity provider tương ứng.

## 11. Region provider: không nhầm Region của Identity Center với Region của service

Spring Cloud AWS sử dụng DefaultAwsRegionProviderChain để xác định Region. Những nguồn phổ biến:

1. Java system property aws.region;
2. Environment variable AWS_REGION;
3. Shared AWS profile configuration;
4. EC2 metadata.

Có thể đặt Region rõ ràng trong application.yml:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Region là cấu hình của service clients. Nếu ứng dụng gọi S3 ở Singapore nhưng IAM Identity Center SSO instance đặt ở Region khác, Region của SSO không thay thế Region của S3.

### Multi-Region application

Nếu một service phải gọi AWS services ở nhiều Regions, auto-configured default Region có thể không đủ. Tạo client riêng cho từng Region:

~~~java
@Configuration
class AwsClientConfiguration {

    @Bean
    S3Client singaporeS3(AwsCredentialsProvider credentialsProvider) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .credentialsProvider(credentialsProvider)
            .build();
    }

    @Bean
    S3Client tokyoS3(AwsCredentialsProvider credentialsProvider) {
        return S3Client.builder()
            .region(Region.AP_NORTHEAST_1)
            .credentialsProvider(credentialsProvider)
            .build();
    }
}
~~~

Hai clients dùng cùng provider nếu principal/permissions cho phép truy cập cả hai Regions. Cần quản lý bean names/qualifiers rõ ràng và không vô tình inject nhầm client.

## 12. Cấu hình ứng dụng cơ bản bằng application.yml

Một cấu hình thường gặp:

~~~yaml
spring:
  application:
    name: orders-api
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: orders-documents
    prefix: orders/
~~~

Tách cấu hình theo profile:

- application-local.yml: Region, endpoint LocalStack hoặc profile developer;
- application-test.yml: Testcontainers connection;
- application-prod.yml: Region production, không chứa credentials;
- runtime role/identity do EC2/ECS/EKS/CI cung cấp.

Không commit account-specific secret values hoặc private endpoint nhạy cảm. Những giá trị có thể công khai trong cấu hình vẫn cần kiểm soát thay đổi qua deployment pipeline.

## 13. S3 integration: dùng S3Client khi cần API đầy đủ

Khi có spring-cloud-aws-starter-s3, Spring Cloud AWS auto-configures AWS SDK S3 client. Có thể inject S3Client và gọi API SDK trực tiếp:

~~~java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class DocumentService {

    private final S3Client s3;

    public DocumentService(S3Client s3) {
        this.s3 = s3;
    }

    public void createBucket(String bucketName) {
        s3.createBucket(b -> b.bucket(bucketName));
    }

    public void upload(String bucket, String key, RequestBody body) {
        s3.putObject(
            PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build(),
            body
        );
    }
}
~~~

Đoạn code chỉ minh họa cách inject client và gọi API; production cần xử lý bucket ownership, bucket policy, encryption, versioning, object key, content type, streaming và retry.

Không tạo AWS SDK client trong từng HTTP request. Client là tài nguyên dùng chung, thread-safe theo contract SDK; để Spring quản lý lifecycle.

## 14. S3Template: abstraction theo phong cách Spring

S3Template cung cấp các thao tác thông dụng như upload/download object, đọc/ghi Java object và tạo signed URL.

Ví dụ service upload:

~~~java
import io.awspring.cloud.s3.S3Template;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class DocumentStorage {

    private final S3Template s3Template;

    public DocumentStorage(S3Template s3Template) {
        this.s3Template = s3Template;
    }

    public void upload(String bucket, String key, InputStream content) {
        s3Template.upload(bucket, key, content);
    }
}
~~~

Một số use cases:

- Lưu file người dùng gửi lên;
- Đọc object về dưới dạng Spring Resource;
- Lưu Java object dưới dạng JSON;
- Tạo presigned GET/PUT URL trong thời gian ngắn.

### Chọn S3Template hay S3Client?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Upload/download phổ biến | S3Template |
| Lấy đầy đủ control từ AWS API | S3Client |
| Transfer lớn, multipart/parallel transfer | S3TransferManager/CRT khi cần |
| Presigned URL | S3Template hoặc SDK presigner |
| S3 API mới/chưa có helper Spring | AWS SDK trực tiếp |

Signed URL là bearer capability: ai có URL trong thời hạn còn hiệu lực có thể dùng quyền mà URL đại diện. Không log URL đầy đủ hoặc đặt expiration quá dài.

## 15. S3 configuration, IAM và streaming

Ứng dụng cần quyền đúng với operations thực tế:

| Use case | IAM actions thường cần |
| --- | --- |
| List objects | s3:ListBucket trên bucket ARN |
| Download | s3:GetObject trên object ARN |
| Upload | s3:PutObject trên object ARN |
| Delete | s3:DeleteObject trên object ARN |
| SSE-KMS | Thêm quyền KMS phù hợp, ví dụ kms:Encrypt, kms:Decrypt, kms:GenerateDataKey theo operation |

Bucket-level actions và object-level actions dùng ARN khác nhau. Với KMS encryption, IAM policy của principal, key policy và grants đều có thể ảnh hưởng kết quả.

### Upload file lớn

- Dùng stream để tránh đọc toàn bộ file vào heap;
- Cân nhắc multipart/transfer manager;
- Giới hạn concurrency và memory buffers;
- Đặt timeout/retry cho network;
- Kiểm tra multipart upload cleanup;
- Không dùng byte array lớn cho mọi file.

### Object key

Không tin trực tiếp tên file client gửi lên. Chuẩn hóa key, ngăn path traversal trong ứng dụng, tách tenant prefix và tránh lưu PII trong object key nếu không cần.

## 16. SQS integration: @SqsListener và message listener container

Spring Cloud AWS hỗ trợ SQS với @SqsListener, MessageListenerContainer, SqsTemplate và acknowledgment handling.

Ví dụ listener:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @SqsListener("orders-events")
    public void onOrderCreated(OrderCreated event) {
        // Validate event, process idempotently, persist business result.
    }
}
~~~

Spring Boot auto-configuration tạo listener container và message adapter cho method được annotate. SQS message payload là string ở service boundary; Spring Cloud AWS có message converter để serialize/deserialize object.

### Gửi message với SqsTemplate

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final SqsTemplate sqsTemplate;

    public OrderEventPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }

    public void publish(OrderCreated event) {
        sqsTemplate.send("orders-events", event);
    }
}
~~~

Khi dùng Spring Boot auto-configuration, SqsTemplate có thể được inject nếu application context chưa có template bean khác. Template immutable và thread-safe.

## 17. SQS delivery semantics: xử lý lặp, visibility timeout và DLQ

SQS Standard queue cung cấp **at-least-once delivery**. Một message có thể được giao nhiều lần, vì vậy listener phải idempotent.

Một consumer an toàn nên:

1. Validate message/schema/version;
2. Kiểm tra idempotency key/event ID;
3. Ghi business state trong transaction;
4. Chỉ acknowledge sau khi xử lý thành công theo acknowledgment mode;
5. Retry lỗi transient có backoff;
6. Chuyển poison messages sang DLQ theo redrive policy;
7. Theo dõi queue depth, age of oldest message và DLQ count.

Visibility timeout phải lớn hơn thời gian xử lý dự kiến hoặc được gia hạn đúng cách. Nếu processing vượt visibility timeout, message có thể được giao cho consumer khác trong khi consumer đầu tiên vẫn chạy.

### Standard và FIFO

| Thuộc tính | Standard | FIFO |
| --- | --- | --- |
| Ordering | Best-effort | Theo message group |
| Duplicate delivery | Có thể xảy ra | Có deduplication window, vẫn thiết kế idempotent |
| Throughput | Phù hợp throughput cao | Gắn với message group/deduplication constraints |
| Use case | Event processing, background jobs | Workflow cần thứ tự theo entity/group |

Không coi FIFO queue là một database transaction. Business side effects vẫn cần idempotency và transactional design.

## 18. SQS concurrency, acknowledgment và error handling

SQS listener container poll messages bất đồng bộ. Tăng maxConcurrentMessages có thể tăng throughput, nhưng cũng tăng DB connection usage, API concurrency, memory/CPU, khả năng đụng throttling downstream và số messages đang invisible.

Tune concurrency theo khả năng downstream, không chỉ theo queue backlog.

### Acknowledgment

Spring Cloud AWS có các acknowledgment modes và batching behavior. Chọn mode theo semantics:

- Acknowledge khi xử lý thành công;
- Manual acknowledgment nếu cần quyết định theo business transaction;
- Batch acknowledgment nếu handler xử lý batch có kết quả từng message.

Không acknowledge trước khi durable side effect hoàn tất. Nếu handler đã ghi DB nhưng message ack thất bại, lần giao lại cần được idempotent.

### Retry và DLQ

Phân biệt lỗi transient (timeout, throttling), lỗi dữ liệu (schema invalid), lỗi permission/configuration và poison message. Retry có giới hạn/backoff; lỗi permission cần sửa IAM/Region/queue config thay vì retry vô hạn.

maxReceiveCount trong redrive policy cần phù hợp với retry window và visibility timeout.

## 19. SNS, SQS và fan-out pattern

SNS có thể fan-out một event tới nhiều SQS queues để mỗi bounded context xử lý độc lập.

~~~mermaid
flowchart LR
    Order[Order service] --> SNS[(SNS topic)]
    SNS --> Q1[(Billing queue)]
    SNS --> Q2[(Shipping queue)]
    SNS --> Q3[(Analytics queue)]
    Q1 --> B[Billing consumer]
    Q2 --> S[Shipping consumer]
    Q3 --> A[Analytics consumer]
~~~

Spring Cloud AWS cung cấp SnsClient/SnsTemplate và SQS listener integrations. Khi SNS publish tới SQS:

- Queue policy phải cho phép SNS topic gửi message;
- Subscription phải đúng Region/account;
- Filter policy phải phù hợp message attributes;
- Consumer vẫn cần idempotency;
- Dead-letter strategy có thể đặt ở subscription/queue theo kiến trúc.

Không dùng SNS notification như đảm bảo một database transaction được commit cùng lúc. Nếu cần outbox, transaction boundary phải nằm trong ứng dụng/database.

## 20. Secrets Manager: load secret bằng Spring Config Data

Spring Cloud AWS tích hợp Secrets Manager qua spring.config.import.

Ví dụ secret /secrets/orders-db chứa JSON:

~~~json
{
  "username": "orders_app",
  "password": "REDACTED"
}
~~~

Cấu hình:

~~~yaml
spring:
  config:
    import: aws-secretsmanager:/secrets/orders-db?prefix=spring.datasource.
~~~

Các top-level keys của JSON secret được thêm vào Spring Environment với prefix tương ứng. Có thể bind bằng @ConfigurationProperties hoặc inject bằng @Value.

Nếu secret bắt buộc và không tồn tại/không đọc được, application startup nên fail để tránh chạy với cấu hình thiếu. Nếu secret thực sự optional, dùng optional:aws-secretsmanager: có chủ đích.

### Plain text secret

Nếu secret là plain text, có thể import theo tên secret và map value vào property phù hợp. Với nhiều secrets, phân tách theo syntax trong reference docs của version đang dùng.

### Prefix tránh trùng property

Nếu JSON có keys chung như username, password, hãy dùng ?prefix=db. hoặc prefix phù hợp để tránh đè property khác.

Không in secret values trong logs, Actuator env endpoint, startup banner hoặc exception message. Bảo vệ quyền đọc /actuator/env và những endpoints có thể hiển thị configuration.

## 21. Secret rotation và reload configuration

Secrets Manager hỗ trợ rotation, nhưng rotation ở AWS không tự động chứng minh mọi object trong JVM đã dùng credential mới.

Spring Cloud AWS có tính năng reload property source theo cấu hình. Cần phân biệt:

- Reload property source;
- Refresh @ConfigurationProperties/@RefreshScope beans;
- Thay đổi connection pool hoặc client đã được tạo;
- Kết nối DB đang mở với credential cũ.

Nếu database password được rotate, cần một chiến lược end-to-end để DataSource/connection pool mở kết nối mới bằng credentials mới và xử lý connections cũ. Đừng chỉ nhìn secret value đã đổi trong console rồi cho rằng HikariCP tự cập nhật.

Reload có thể dùng refresh hoặc restart_context strategy tùy integration. Tính năng reload cần dependencies/configuration bổ sung và phải được test theo lifecycle của ứng dụng.

## 22. Systems Manager Parameter Store: cấu hình theo path

Parameter Store phù hợp với cấu hình dạng key/value, feature flags, endpoint và non-secret parameters. Dùng SecureString cho dữ liệu cần encryption; quản lý KMS permissions theo key.

Ví dụ parameters:

~~~text
/config/orders-api/payment-url = https://payments.example.internal
/config/orders-api/max-retries = 3
/config/orders-api/feature/new-checkout = true
~~~

Import path:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/orders-api/
~~~

Các parameter dưới path được đưa vào Spring Environment. Có thể dùng prefix để ánh xạ vào namespace cụ thể:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/database/?prefix=spring.datasource.
~~~

Quyền IAM phổ biến cho path-based lookup là ssm:GetParametersByPath. Nếu đọc SecureString mã hóa bằng customer managed KMS key, principal có thể cần kms:Decrypt và key policy phải cho phép.

### Secrets Manager hay Parameter Store?

| Nhu cầu | Nên cân nhắc |
| --- | --- |
| Password, API token, database secret và rotation | Secrets Manager |
| App config, endpoint, feature flag, non-secret values | Parameter Store |
| Hierarchical config theo path | Parameter Store |
| Secret lifecycle/rotation integration | Secrets Manager |
| Giá và quota | Kiểm tra pricing/limits của từng service |

Không lưu plaintext secret vào Parameter Store Standard chỉ vì việc import thuận tiện.

## 23. CloudWatch metrics và observability

Spring Cloud AWS có thể tích hợp Micrometer CloudWatch registry. Dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-cloudwatch2</artifactId>
</dependency>
~~~

Cấu hình namespace và export interval:

~~~yaml
management:
  cloudwatch:
    metrics:
      export:
        namespace: OrdersApi
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
~~~

Cần quyền CloudWatch tương ứng, thường bao gồm cloudwatch:PutMetricData. Không bật CloudWatch metrics exporter cho mọi local profile nếu không cần.

### Theo dõi application và AWS integration

| Metric/Signal | Ý nghĩa |
| --- | --- |
| HTTP request rate, error rate, p95/p99 | Trải nghiệm API |
| SQS queue depth/age | Backlog và consumer lag |
| Listener failures/DLQ count | Message processing health |
| S3 request failures/latency | Upload/download health |
| AWS SDK retry count | Throttling/network instability |
| Secrets/Parameter import failures | Application config readiness |
| JVM heap/thread/connection pool | Resource saturation |
| CloudWatch service metrics | AWS-side behavior |

Dùng correlation ID và event ID xuyên API → SQS → consumer; tránh đưa secrets, payload nhạy cảm hoặc PII vào metric dimensions.

## 24. Customizing AWS clients: timeout, HTTP transport và retry

Spring Cloud AWS cho phép customizer cho nhóm synchronous và asynchronous AWS clients.

| Client type | Ví dụ integrations |
| --- | --- |
| Synchronous | DynamoDB, SES, SNS, Parameter Store, Secrets Manager, S3 |
| Asynchronous | SQS, CloudWatch |

Có thể cấu hình AwsSyncClientCustomizer hoặc AwsAsyncClientCustomizer, hoặc customizer riêng cho từng client.

Ví dụ customizer synchronous:

~~~java
import io.awspring.cloud.autoconfigure.AwsSyncClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
class AwsHttpConfiguration {

    @Bean
    AwsSyncClientCustomizer syncClientCustomizer() {
        return builder -> builder.overrideConfiguration(config ->
            config.apiCallTimeout(Duration.ofSeconds(20))
        );
    }
}
~~~

Đây là ví dụ timeout tổng cho API call; cần cân nhắc timeout per attempt, retry strategy, connection acquisition timeout và HTTP client pool theo tải thật.

### Retry không thay business idempotency

AWS SDK có retry strategy cho lỗi retryable. Nhưng một POST có thể đã commit rồi response bị timeout. Nếu caller retry mà business operation không idempotent, ứng dụng có thể tạo duplicate order/payment.

Đối với SQS consumer, dùng event ID/unique constraint/outbox hoặc idempotency store. Đối với API, dùng idempotency key theo contract.

## 25. Endpoint và LocalStack: tách endpoint test khỏi production

Spring Cloud AWS hỗ trợ cấu hình endpoint cho các auto-configured clients:

~~~yaml
spring:
  cloud:
    aws:
      endpoint: http://localhost:4566
      region:
        static: ap-southeast-1
~~~

Endpoint này phù hợp môi trường AWS-compatible/local test. Không đưa LocalStack endpoint vào production profile và không dùng fake credentials cho AWS thật.

Trong test, có thể dùng spring-cloud-aws-testcontainers và @ServiceConnection với LocalStackContainer để Spring Cloud AWS tự cấu hình Region/credentials trỏ tới container.

### LocalStack và chi phí/tooling

Từ thay đổi LocalStack năm 2026, image localstack:latest community có thể yêu cầu LOCALSTACK_AUTH_TOKEN. Pin version phù hợp hoặc cấu hình token theo điều khoản hiện hành. Test nên fail rõ nếu container không khởi động thay vì fallback ngầm sang AWS thật.

## 26. Integration test với Testcontainers

Ví dụ test setup theo Spring Boot service connection:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class LocalAwsTestConfiguration {

    @Bean
    @ServiceConnection
    LocalStackContainer localStackContainer() {
        return new LocalStackContainer(
            DockerImageName.parse("localstack/localstack:4.12.0")
        );
    }
}
~~~

Cần dependency Testcontainers LocalStack và spring-cloud-aws-testcontainers được quản lý bởi BOM. Với version LocalStack mới cần auth token, cấu hình môi trường container phù hợp; version trong ví dụ chỉ là một pin minh họa từ tài liệu, hãy chọn version đang được hỗ trợ.

### Những gì nên test

- Application context khởi động với đúng release line;
- AWS clients được tạo đúng Region/credentials;
- Upload/download S3 và object key;
- SQS send/listener/acknowledgment;
- DLQ/redrive behavior;
- Secrets Manager/Parameter Store config import;
- IAM AccessDenied paths nếu integration environment cho phép;
- Retry/idempotency của consumer.

LocalStack không thay thế contract test với AWS thật cho mọi feature. Một số IAM, KMS, event delivery, consistency hoặc service limits có thể khác AWS.

## 27. Compatibility verifier và dependency diagnostics

Spring Cloud có compatibility verifier để phát hiện một số Spring Boot versions không tương thích với release train. Đây là lớp bảo vệ hữu ích, nhưng không thay thế kiểm tra đầy đủ:

- Nó không chứng minh mọi transitive dependency đều tương thích;
- Không phát hiện mọi binary/API conflict;
- Không xác minh AWS account/Region/IAM permissions;
- Không thay thế integration test.

Khi startup báo compatibility error, đọc version được chấp nhận và nâng/hạ đúng release train. Không tắt verifier chỉ để ứng dụng boot qua nếu chưa xác định rõ lý do.

### Maven diagnostics

~~~bash
mvn -q help:effective-pom

mvn dependency:tree \
  -Dincludes=io.awspring.cloud,org.springframework.boot,org.springframework,org.springframework.cloud,software.amazon.awssdk
~~~

### Gradle diagnostics

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-aws \
  --configuration runtimeClasspath
~~~

Tìm các dấu hiệu:

- Có hai versions của software.amazon.awssdk modules;
- Có Spring Framework 6.x và 7.x cùng runtime;
- Spring Cloud AWS 4.x nhưng Boot 3.x;
- Spring Cloud AWS 3.x nhưng Spring Framework 7.x;
- Starter version bị override bằng direct module version khác;
- AWS SDK v1 và v2 cùng tồn tại do legacy dependencies.

## 28. Migration từ Spring Cloud AWS 2.x sang 3.x

Migration 2.x → 3.x là thay đổi lớn:

| Vấn đề | 2.x | 3.x |
| --- | --- | --- |
| AWS SDK | v1 | v2 |
| Spring Boot | 2.x | 3.x |
| Spring Framework | 5.x | 6.x |
| Java namespace | javax.* phổ biến | Jakarta jakarta.* |
| Package Spring Cloud AWS | org.springframework.cloud.aws | io.awspring.cloud |
| Property namespace | Một số cloud.aws.* / aws.* | spring.cloud.aws.* |
| Config import | Cơ chế cũ | Spring Boot Config Data |

### Một số property migration

| Property cũ | Property mới |
| --- | --- |
| cloud.aws.credentials.access-key | spring.cloud.aws.credentials.access-key |
| cloud.aws.credentials.secret-key | spring.cloud.aws.credentials.secret-key |
| cloud.aws.region.static | spring.cloud.aws.region.static |
| aws.paramstore.region | spring.cloud.aws.parameterstore.region |
| aws.secretsmanager.region | spring.cloud.aws.secretsmanager.region |
| management.metrics.export.cloudwatch.* | management.cloudwatch.metrics.export.* |

Parameter Store 3.x dùng spring.config.import=aws-parameterstore:/path/ thay vì ghép các prefix/default context/name theo cơ chế 2.x.

### Quy trình migration an toàn

1. Inventory mọi Spring Cloud AWS dependencies và property cũ.
2. Chọn Spring Boot/Spring Cloud release train mục tiêu.
3. Thay AWS SDK v1 clients/models bằng SDK v2 APIs.
4. Đổi package imports và Jakarta dependencies.
5. Thay Parameter Store/Secrets Manager config loading sang Config Data import.
6. Chuyển SQS listener/template và kiểm tra payload conversion/acknowledgment.
7. Chạy dependency tree để tìm version conflicts.
8. Chạy unit/integration tests trên LocalStack.
9. Test trên AWS non-production account với IAM least privilege.
10. Canary deploy, theo dõi errors/latency/DLQ trước khi rollout.

## 29. Migration từ 3.x sang 4.x

Spring Cloud AWS 4.x nhắm tới Spring Boot 4.x/Spring Framework 7.x theo compatibility matrix. Các ứng dụng Boot 3.5.x nên ở release line 3.4.x nếu chưa có kế hoạch nâng Boot 4.

Khi migration:

- Nâng Spring Boot trước hoặc cùng dependency set đã được kiểm thử;
- Kiểm tra Spring Cloud train phù hợp;
- Nâng Spring Cloud AWS BOM lên 4.x;
- Kiểm tra Spring Boot 4 migration notes và Jackson version;
- Xem xét thay đổi auto-configuration/classpath conditions;
- Build toàn bộ module, không chỉ module có AWS starter;
- Test Config Data import, SQS message conversion và service connection.

Không nâng riêng Spring Cloud AWS BOM lên 4.x trong project Boot 3.5.x. Compatibility table cần được tôn trọng ở cả Boot/Cloud/Framework/AWSpring.

## 30. Dịch vụ nào không có Spring Cloud AWS integration?

Không phải mọi AWS service đều có starter/abstraction Spring Cloud AWS. Compatibility matrix cũng thể hiện một số integrations có trong 2.x nhưng không còn trong 3.x/4.x.

| AWS service | Cách tiếp cận |
| --- | --- |
| RDS/Aurora | Spring Boot DataSource/JDBC/JPA + driver; AWS SDK/Secrets Manager/IAM auth theo use case |
| EC2 control plane | AWS SDK EC2 client |
| ElastiCache | Redis client/Spring Data Redis; AWS networking/auth theo engine |
| CloudFormation | AWS SDK CloudFormation client hoặc IaC pipeline |
| API Gateway | AWS SDK/API Gateway hoặc Spring Web endpoints triển khai phía sau |
| Lambda | AWS SDK Lambda client, Spring Cloud Function/AWS adapter tùy kiến trúc |
| Kinesis | Spring Cloud AWS Kinesis binder/integration khi release line hỗ trợ, hoặc SDK |
| AppConfig | AppConfig starter ở release lines hỗ trợ; kiểm tra matrix |

Không nhầm “không có Spring Cloud AWS starter” với “không thể dùng AWS service trong Spring”. Có thể inject AWS SDK client bằng cấu hình riêng.

## 31. IAM, KMS và network cho Spring Cloud AWS

Một ứng dụng có thể boot thành công nhưng vẫn nhận AccessDenied khi gọi service. Auto-configuration không tự cấp quyền IAM.

Thiết kế permission theo từng feature:

| Integration | IAM actions tiêu biểu |
| --- | --- |
| S3 read | s3:GetObject, s3:ListBucket |
| S3 write | s3:PutObject |
| SQS consumer | sqs:ReceiveMessage, sqs:DeleteMessage, sqs:ChangeMessageVisibility, sqs:GetQueueAttributes |
| SQS publisher | sqs:SendMessage |
| SNS publisher | sns:Publish |
| Secrets Manager | secretsmanager:GetSecretValue, secretsmanager:DescribeSecret |
| Parameter Store | ssm:GetParametersByPath/ssm:GetParameter theo cách truy vấn |
| CloudWatch metrics | cloudwatch:PutMetricData |
| KMS encrypted resources | kms:Decrypt/kms:Encrypt/kms:GenerateDataKey theo operation |

Các quyền thực tế phải giới hạn theo resource ARN, prefix, queue/topic ARN và key ARN. Một số actions cần Resource *, hãy xem IAM service authorization reference.

### Network

Ứng dụng private subnet cần route/DNS/egress tới service endpoints hoặc VPC endpoints phù hợp. Ví dụ S3 gateway endpoint, SQS interface endpoint, Secrets Manager interface endpoint, Systems Manager interface endpoint, STS endpoint và CloudWatch monitoring endpoint.

Kiểm tra Security Groups, endpoint policy, DNS private hosted zones và TLS. Credentials hợp lệ không giúp request đi qua một network path bị chặn.

## 32. Troubleshooting: lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| NoSuchBeanDefinitionException cho S3Client | Thiếu S3 starter, auto-config bị exclude hoặc bean custom conflict | Kiểm tra starter, classpath và conditions |
| No region provided | Không có region property/env/profile/metadata | Đặt spring.cloud.aws.region.static hoặc AWS_REGION |
| Unable to load credentials | Không có credentials provider thành công | Xác minh AWS_PROFILE, SSO login, workload role/IMDS |
| ExpiredToken | Static/temporary credentials đã hết hạn hoặc source identity không refresh | Dùng provider chain/role, không giữ credentials tĩnh |
| AccessDenied S3 | IAM, bucket policy, KMS key policy hoặc SCP deny | Kiểm tra action, resource ARN, encryption và identity ARN |
| SQS listener không nhận message | Queue/Region sai, thiếu ReceiveMessage, listener container không start | Kiểm tra queue URL/name, IAM, startup logs và CloudWatch |
| Message được xử lý lặp | At-least-once delivery, ack thất bại, visibility timeout | Idempotency, visibility, acknowledgment và DLQ |
| App fail lúc startup khi import secret | Secret/path không tồn tại hoặc IAM/network/KMS deny | Kiểm tra secret ARN, role và optional/required semantics |
| Secret đổi nhưng DB pool vẫn dùng password cũ | Config refresh không cập nhật connection pool đang tồn tại | Thiết kế pool refresh/reconnect và kiểm thử rotation |
| SdkClientException timeout | DNS, VPC endpoint, proxy, SG/NACL hoặc HTTP timeout | Kiểm tra network path và client timeout |
| NoSuchMethodError/ClassNotFoundException | SDK/Spring versions xung đột | dependency:tree, BOM, clean rebuild |
| Compatibility verifier fail | Spring Boot/Cloud release train không tương thích | Chọn đúng matrix, không tắt verifier tùy tiện |
| SQS payload conversion error | Jackson/message type header/version mismatch | Kiểm tra converter, payload schema và type mapping |
| LocalStack test gọi AWS thật | Endpoint/ServiceConnection không được áp dụng | Kiểm tra profile test, endpoint và credentials dummy |
| Startup fail do config import | Import scheme thiếu starter, required resource missing | Thêm starter, sửa URI hoặc optional khi hợp lý |

### Trình tự điều tra

~~~text
1. Xác nhận Spring Boot, Spring Cloud train, Spring Cloud AWS và Java versions.
2. Xem effective POM/dependency tree để phát hiện version conflicts.
3. Kiểm tra auto-configuration conditions và startup logs.
4. Xác minh Region và endpoint.
5. Xác minh identity bằng STS GetCallerIdentity.
6. Kiểm tra IAM identity/resource policies, KMS và SCP.
7. Kiểm tra VPC endpoints, DNS, TLS và timeout.
8. Với SQS: kiểm tra queue attributes, listener container, visibility và DLQ.
9. Với Config Data: kiểm tra import URI, resource existence và IAM.
10. Re-run integration test rồi mới triển khai canary.
~~~

Không bật debug logs chứa request Authorization headers, secret values hoặc full configuration environment.

## 33. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Chọn ma trận tương thích

Một dự án dùng Spring Boot 3.5.x, Spring Framework 6.2.x và AWS SDK v2. Developer định thêm Spring Cloud AWS 4.x vì đây là major mới hơn.

**Yêu cầu:** Chọn release line phù hợp theo compatibility table; giải thích vì sao Boot 3.5.x thuộc Spring Cloud AWS 3.4.x và vì sao 4.x dành cho Boot 4.0.x.

### Bài tập 2 — Quản lý BOM

Một Maven project khai báo spring-cloud-aws-starter-s3:3.4.x, spring-cloud-aws-sqs:3.3.x và software.amazon.awssdk:s3:2.x riêng lẻ.

**Yêu cầu:** Viết lại dependencyManagement dùng Spring Cloud AWS BOM, starter version-less và mô tả khi nào mới cần AWS SDK BOM override.

### Bài tập 3 — SSO profile chạy local

Ứng dụng Spring Boot chạy local đã aws sso login --profile dev-sso, nhưng Java nhận credentials của account cũ.

**Yêu cầu:** Giải thích provider chain precedence, kiểm tra AWS_ACCESS_KEY_ID/AWS_SESSION_TOKEN, đặt AWS_PROFILE và xác minh bằng STS.

### Bài tập 4 — ECS production

Một service trên ECS Fargate có credentials access key/secret trong application.yml.

**Yêu cầu:** Chuyển sang ECS task role, thiết kế IAM permissions S3/SQS tối thiểu, mô tả vì sao task execution role khác task role.

### Bài tập 5 — S3 upload

Viết một Spring service inject S3Template để upload file; sau đó mô tả khi nào cần S3Client hoặc S3TransferManager. Liệt kê IAM actions và cách bảo vệ object key.

### Bài tập 6 — SQS consumer

Một @SqsListener xử lý payment event, ghi database rồi đôi khi message xuất hiện lại.

**Yêu cầu:** Giải thích at-least-once delivery, thiết kế idempotency key, transaction boundary, acknowledgment, visibility timeout và DLQ.

### Bài tập 7 — Secrets Manager

Database secret JSON có keys username/password. Spring Boot cần load secret vào spring.datasource.* và không khởi động khi secret bắt buộc thiếu.

**Yêu cầu:** Viết spring.config.import với prefix; mô tả IAM secretsmanager:GetSecretValue, KMS Decrypt, và lý do không nên expose Actuator env.

### Bài tập 8 — LocalStack Testcontainers

Một test tích hợp vô tình ghi object vào bucket AWS thật thay vì LocalStack.

**Yêu cầu:** Thiết kế @ServiceConnection với LocalStackContainer, kiểm tra endpoint/Region/credentials test, pin image và ngăn fallback tới AWS thật.

### Câu hỏi ngắn

1. **Spring Cloud AWS có thay AWS SDK không?** Không; nó bổ sung Spring abstractions/auto-configuration trên AWS SDK.
2. **Spring Cloud AWS 3.x dùng AWS SDK v1 hay v2?** AWS SDK v2.
3. **Spring Cloud AWS 4.x tương thích Spring Boot release line nào theo matrix?** Spring Boot 4.0.x.
4. **Spring Cloud AWS 3.4.x gắn với Boot line nào?** Spring Boot 3.5.x.
5. **BOM có lợi ích gì?** Giữ các module cùng release line và dependency versions được kiểm thử.
6. **Có nên khai báo version riêng cho từng AWS SDK module?** Không; dùng một SDK BOM nếu cần override.
7. **S3 starter artifact là gì?** spring-cloud-aws-starter-s3.
8. **SQS listener annotation là gì?** @SqsListener.
9. **S3Template dùng làm gì?** Upload/download, object mapping và signed URL cho use cases phổ biến.
10. **Spring Cloud AWS default credentials provider dùng nguồn nào?** Java properties, environment, web identity, profile, container, EC2 metadata.
11. **Region static property là gì?** spring.cloud.aws.region.static.
12. **Secrets Manager Config Data scheme là gì?** aws-secretsmanager:.
13. **Parameter Store Config Data scheme là gì?** aws-parameterstore:.
14. **Optional import có tác dụng gì?** Cho phép app tiếp tục start nếu external resource không tồn tại, khi resource thực sự optional.
15. **SQS Standard queue có thể giao lặp không?** Có; consumer phải idempotent.
16. **LocalStack test có thể thay hoàn toàn AWS integration test không?** Không; một số behavior phải xác minh trên AWS non-production.
17. **Compatibility verifier có chứng minh runtime AWS permissions đúng không?** Không; nó kiểm tra một phần framework compatibility.
18. **Có nên tắt compatibility verifier để bỏ qua lỗi version?** Không, trừ khi có lý do đã đánh giá và test rõ ràng.

## 34. Checklist trước production

- [ ] Spring Cloud AWS release line khớp Spring Boot, Spring Cloud train và Spring Framework.
- [ ] Java version, Maven/Gradle wrapper và runtime container được xác minh.
- [ ] Chọn đúng Spring Cloud AWS BOM; các starter không khai báo patch version riêng.
- [ ] AWS SDK modules đồng bộ version; chỉ override AWS SDK BOM khi có lý do.
- [ ] Không trộn Spring Cloud AWS 2.x/3.x/4.x APIs và package namespaces.
- [ ] Credentials lấy từ SSO profile local hoặc workload identity/runtime role.
- [ ] Không lưu access key/secret/session token trong Git, Docker image hoặc application.yml.
- [ ] Region được cấu hình rõ; SSO Region không bị nhầm với service Region.
- [ ] S3 bucket/object permissions, KMS policies và object key rules được kiểm tra.
- [ ] SQS queue policy, listener concurrency, visibility timeout, acknowledgment và DLQ được thiết kế.
- [ ] Consumer có idempotency và transaction boundary phù hợp.
- [ ] Secrets Manager/Parameter Store import có required/optional semantics rõ ràng.
- [ ] Secret reload/rotation được test tới connection pool hoặc client thực tế.
- [ ] IAM policies chỉ cấp actions/resources cần thiết.
- [ ] VPC endpoints, DNS, Security Groups, TLS và timeout đã kiểm tra.
- [ ] CloudWatch/Micrometer namespace và metrics không chứa PII/secrets.
- [ ] AWS client customizers không tạo client mới cho từng request.
- [ ] LocalStack endpoint/credentials chỉ nằm trong test/local profiles.
- [ ] Testcontainers image được pin và auth requirements được xử lý.
- [ ] Dependency tree không có Spring Framework/AWS SDK version conflicts.
- [ ] Integration test cover S3/SQS/config import và failure cases.
- [ ] Non-production AWS test xác minh IAM, KMS, event delivery và Region.
- [ ] Deployment có canary, dashboard, alert, rollback và runbook.
- [ ] Đã đọc release notes và compatibility table cho patch version sẽ deploy.

## 35. Tổng kết

Spring Cloud AWS giúp Spring Boot sử dụng AWS services theo idiom của Spring: starter theo dịch vụ, auto-configuration cho credentials/Region, templates, message listeners, Config Data import, metrics và testing utilities. AWS SDK for Java 2.x vẫn là lớp thực hiện API calls; khi cần tính năng chưa có Spring abstraction, inject SDK client trực tiếp.

**Ma trận tương thích là điều kiện đầu tiên của tích hợp ổn định.** Theo compatibility table của dự án, Spring Cloud AWS 3.4.x phù hợp Spring Boot 3.5.x/Spring Cloud 2025.0.x/Spring Framework 6.2.x; Spring Cloud AWS 4.x phù hợp Spring Boot 4.0.x/Spring Cloud 2025.1.x/Spring Framework 7.0.x. Hai release lines hiện đại dùng AWS SDK for Java 2.x. Patch releases và support windows thay đổi, vì vậy phải kiểm tra đúng release docs trước khi khóa dependency.

Sau khi chọn version, dùng BOM để giữ dependency graph đồng bộ, chọn đúng starters, sử dụng workload identity, đặt Region rõ ràng, cấp IAM least privilege và test integration bằng LocalStack/Testcontainers cùng AWS non-production account. Với SQS, thiết kế idempotency/acknowledgment; với Secrets Manager, test rotation tới resource đang giữ connection; với S3, kiểm soát object permissions và streaming.

### Tài liệu chính thức

- [Spring Cloud AWS Reference Documentation 4.2.1](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html)
- [Spring Cloud AWS project README và Compatibility Matrix](https://github.com/awspring/spring-cloud-aws/blob/main/README.md)
- [Spring Cloud AWS Bill of Materials](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#bill-of-materials)
- [Spring Cloud AWS Credentials and Region](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#spring-cloud-aws-core)
- [Spring Cloud AWS S3 Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#s3-integration)
- [Spring Cloud AWS SQS Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#sqs-integration)
- [Spring Cloud AWS Secrets Manager](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#secrets-manager-integration)
- [Spring Cloud AWS Parameter Store](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#parameter-store-integration)
- [Spring Cloud AWS Testing with LocalStack](https://docs.awspring.io/spring-cloud-aws/docs/4.2.1/reference/html/index.html#testing)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Release 2025.0 Reference](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html)
- [Spring Cloud Release 2025.1 Reference](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html)

**Lưu ý:** Patch versions, Java baseline, starter inventory và support windows thay đổi. Hãy dùng compatibility matrix của dự án và reference docs của đúng Spring Cloud AWS artifact version; build/test với dependency tree thực tế trước khi đưa ứng dụng lên production.
