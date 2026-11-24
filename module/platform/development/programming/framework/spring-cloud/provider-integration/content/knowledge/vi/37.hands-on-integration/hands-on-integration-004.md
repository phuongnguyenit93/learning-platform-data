# Nạp cấu hình và xoay vòng bí mật mà không ghi khóa vào mã

Ứng dụng Spring Boot thường cần database password, API token, signing key, certificate hoặc connection credential để gọi dịch vụ managed. Nếu đặt các giá trị này trong source code, file application.yml được commit, Docker image hoặc pipeline log, mỗi lần chia sẻ mã hay phát hành artifact đều có thể làm lộ credential. Cách triển khai an toàn là lưu secret trong dịch vụ quản lý bí mật của cloud, cấp quyền đọc cho workload bằng danh tính workload, nạp giá trị vào Spring Environment khi khởi động và thiết kế quy trình xoay vòng có kiểm chứng.

Bài thực hành này dùng một document-service chạy trên AWS, Azure hoặc Google Cloud. Cùng một ứng dụng cần đọc database username/password và partner API key, trong khi endpoint, region, project ID và feature flag là cấu hình thông thường. Tùy cloud, ứng dụng sử dụng AWS Secrets Manager/Systems Manager Parameter Store, Azure Key Vault hoặc Google Cloud Secret Manager thông qua tích hợp Spring tương ứng.

Mục tiêu không chỉ là thay chuỗi password trong application.yml bằng một tham chiếu secret. Một lần rotate còn phải cập nhật credential ở dịch vụ đích, đưa secret version mới tới từng instance, làm mới client hoặc connection pool, kiểm tra luồng nghiệp vụ, giữ khả năng rollback và chỉ thu hồi credential cũ sau khi toàn bộ workload đã chuyển đổi.

## 1. Mục tiêu và kiến trúc thực hành

Sau bài học, bạn có thể:

1. Phân biệt cấu hình thông thường với secret và xác định dữ liệu nào cần lưu trong secret manager.
2. Dùng Spring Boot Config Data API và PropertySource để nạp cấu hình từ nguồn bên ngoài.
3. Cấu hình Spring Cloud AWS để đọc Secrets Manager và Parameter Store.
4. Cấu hình Spring Cloud Azure để đọc Azure Key Vault Secrets.
5. Cấu hình Spring Framework on Google Cloud để đọc Google Cloud Secret Manager.
6. Xác thực workload bằng IAM role, managed identity hoặc Application Default Credentials.
7. Cấp quyền đọc secret theo least privilege.
8. Phân biệt secret version, current version, pending version và previous version.
9. Thiết kế quy trình rotate database password hoặc API token có thời gian chuyển tiếp.
10. Làm mới Spring bean, HTTP client và JDBC connection pool sau khi secret đổi.
11. Kiểm thử secret thiếu, quyền bị từ chối, version sai, credential hết hạn và rollback.
12. Xây dựng runbook có owner, lịch rotate, giám sát và bằng chứng kiểm tra.

~~~mermaid
flowchart TD
    A["CI/CD hoặc operator"] --> B["Tạo credential mới ở dịch vụ đích"]
    B --> C["Ghi secret version mới"]
    C --> D["Kiểm tra secret mới bằng canary"]
    D --> E["Phát hành cấu hình/version tới workload"]
    E --> F["Spring Boot nạp secret mới"]
    F --> G["Tạo lại client hoặc connection pool"]
    G --> H["Kiểm tra request và metric"]
    H --> I["Thu hồi credential cũ"]
    C -. "Lưu version cũ để rollback" .-> J["Secret history"]
    D -. "Nếu thất bại" .-> K["Rollback về version tốt"]
    K --> F
~~~

**Secret manager lưu và kiểm soát vòng đời credential. Spring Cloud tích hợp secret manager với Spring Environment. Ứng dụng vẫn phải xử lý việc làm mới bean và kết nối đang tồn tại.**

## 2. Phân biệt configuration và secret

### 2.1. Configuration thông thường

Configuration mô tả cách ứng dụng hoạt động trong một môi trường:

- Tên service, profile và feature flag.
- Base URL của dịch vụ nội bộ.
- Region, project ID, resource ID và bucket name.
- Timeout, retry count, batch size và giới hạn đồng thời.
- Log level và sampling rate.
- Tên queue, topic, database schema hoặc secret resource.

Những giá trị này có thể nằm trong application.yml không chứa bí mật, environment variable, cloud parameter store, configuration service hoặc Kubernetes ConfigMap. Chúng vẫn cần quản lý theo môi trường và thay đổi có kiểm soát, nhưng không nhất thiết phải có cơ chế bảo vệ giống password.

### 2.2. Secret

Secret là giá trị mà người không được phép biết có thể dùng để truy cập, giả mạo danh tính hoặc vượt qua kiểm soát:

- Database password.
- API key, OAuth client secret hoặc refresh token.
- Private key, signing key và certificate có private key.
- SMTP credential.
- Access key hoặc connection string chứa credential.
- Encryption key hoặc token dùng để ký request.

Secret không nên xuất hiện trong:

- Git repository hoặc pull request.
- Dockerfile, build argument hoặc image layer.
- File application-prod.yml được đóng gói trong JAR.
- CI/CD log, command history hoặc build artifact.
- Exception message, stack trace, metrics label hoặc distributed trace.
- Endpoint Actuator không được bảo vệ.
- Ticket, chat hoặc tài liệu runbook công khai.

### 2.3. Tách cấu hình theo mức độ nhạy cảm

| Giá trị | Nơi lưu phù hợp | Ví dụ |
| --- | --- | --- |
| Region, project ID, endpoint | application.yml hoặc config store | ap-southeast-1 |
| Feature flag, timeout, retry | Config store/Parameter Store/App Configuration | app.retry.max-attempts |
| Database username/password | Secret Manager/Key Vault | document-db-credential |
| Partner API token | Secret Manager/Key Vault | partner-api-token |
| Private key/certificate | Secret Manager hoặc certificate/key service | document-signing-key |
| Secret version ID | Deployment configuration/metadata | version 17 |
| Secret resource name | Application configuration | secret path hoặc secret ID |

Không đưa giá trị bí mật vào tên secret, tag hoặc description. Metadata giúp nhận diện mục đích và owner, không nên chứa password hay token.

### 2.4. Secret manager không phải configuration database

Secret manager tối ưu cho lưu trữ, truy cập và quản lý vòng đời dữ liệu nhạy cảm. Dùng nó cho mọi feature flag hoặc thông số không nhạy cảm có thể làm tăng API calls, chi phí và quyền truy cập không cần thiết.

AWS có Parameter Store cho cấu hình và SecureString; Azure có App Configuration cho cấu hình ứng dụng và Key Vault cho secrets; Google Cloud có các nguồn cấu hình riêng và Secret Manager cho secret payload. Bài tập trung vào secret và chỉ dùng parameter store khi cần minh họa cấu hình không nhạy cảm.

## 3. Spring Boot nạp cấu hình bên ngoài

### 3.1. Spring Environment và PropertySource

Spring Boot gom giá trị từ nhiều nguồn thành Environment. Bean có thể đọc giá trị qua:

- @Value cho một vài property đơn giản.
- Environment khi cần truy vấn property động.
- @ConfigurationProperties cho nhóm property có cấu trúc, validation và type-safe binding.

Thứ tự ưu tiên PropertySource quyết định giá trị cuối cùng khi cùng một key xuất hiện ở nhiều nơi. Environment variable, system property và command-line argument có thể ghi đè giá trị từ config data. Vì vậy, một environment variable cũ có thể vô tình che giá trị secret mới được nạp từ cloud.

Trong production, quy định rõ nguồn có quyền ghi đè secret. Không dùng default value cho database password hoặc API token bắt buộc. Nếu secret bị thiếu, ứng dụng nên fail startup hoặc fail readiness để deployment không nhận traffic với credential rỗng.

### 3.2. Spring Boot Config Data API

Spring Boot hỗ trợ nạp nguồn cấu hình bên ngoài bằng property spring.config.import. Các cloud starter có thể đăng ký resolver riêng để Spring Boot đọc dữ liệu từ secret manager trong giai đoạn Config Data.

Ví dụ dạng tổng quát:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Config tree hữu ích khi platform mount secret thành file. Tên file hoặc thư mục được ánh xạ thành property. Cách này hoạt động với Kubernetes Secret volume, Docker secrets hoặc secret volume do platform cung cấp.

Với secret manager trực tiếp, mỗi cloud starter có cú pháp import riêng. Không dùng prefix của AWS cho Azure hoặc Google Cloud.

### 3.3. Required và optional import

Có hai trường hợp:

- Secret bắt buộc để mở kết nối database hoặc gọi API: import phải required. Thiếu secret hoặc không đọc được secret phải làm startup thất bại.
- Cấu hình tùy chọn như feature flag thử nghiệm: có thể dùng optional import nếu ứng dụng có hành vi mặc định an toàn.

Không dùng optional để che giấu lỗi quyền hoặc thiếu credential production. Nếu import secret bị lỗi nhưng ứng dụng vẫn chạy với password rỗng/default, lỗi sẽ xuất hiện muộn hơn và khó điều tra hơn.

### 3.4. Cấu hình theo profile

Giữ application.yml chỉ chứa cấu hình chung và không chứa secret. Dùng profile riêng để bật resolver phù hợp môi trường:

~~~text
application.yml
application-aws.yml
application-azure.yml
application-gcp.yml
~~~

Ví dụ chọn profile khi chạy:

~~~bash
SPRING_PROFILES_ACTIVE=aws
~~~

Mỗi profile chỉ khai báo nguồn cấu hình và tên secret resource của cloud tương ứng. Cùng một business service có thể dùng property key chung như spring.datasource.username, spring.datasource.password và partner.api.key.

### 3.5. Binding có validation

Ví dụ cấu hình partner client:

Thêm validation starter để các annotation Jakarta Validation được thực thi khi bind cấu hình:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.validation.annotation.Validated;

@Validated
@RefreshScope
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    @NotBlank
    private String key;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    @Override
    public String toString() {
        return "PartnerApiProperties{key=[REDACTED]}";
    }
}
~~~

Bật configuration properties scanning trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DocumentServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentServiceApplication.class, args);
    }
}
~~~

Không dùng record có secret field nếu generated toString() có thể ghi toàn bộ giá trị. Nếu dùng record, phải kiểm soát serialization/logging và không in object ra log. Không đưa PartnerProperties vào JSON response hoặc actuator endpoint.

### 3.6. Property refresh không đồng nghĩa client đã đổi credential

Khi secret manager phát hiện version mới, PropertySource có thể được nạp lại hoặc Spring có thể refresh một số bean. Nhưng một JDBC DataSource hoặc HTTP client singleton đã được tạo từ trước có thể vẫn giữ credential cũ.

Ví dụ HikariCP tạo connection pool lúc startup. Đổi spring.datasource.password trong Environment không tự bảo đảm pool hiện tại đóng connection cũ, tạo connection mới bằng password mới hoặc ngắt các session cũ.

Với credential dùng cho connection pool, phương án an toàn thường là rolling restart hoặc cơ chế thay pool có drain/close rõ ràng. Chỉ dùng refresh in-place khi đã kiểm thử chính xác bean nào được tạo lại và connection cũ được thu hồi như thế nào.

## 4. Chuẩn bị ứng dụng thực hành

### 4.1. Cấu hình chung

File application.yml không chứa credential:

~~~yaml
spring:
  application:
    name: document-service
  datasource:
    url: jdbc:postgresql://db.internal.example:5432/documents
    hikari:
      pool-name: document-service-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000

partner:
  base-url: https://partner.example/api
~~~

URL, pool size và partner endpoint là cấu hình thông thường trong ví dụ này. Username/password và API key được lấy từ secret manager. Nếu database URL chứa password trong query string, URL cũng phải được xem là secret.

### 4.2. Secret contract dùng chung

Để chuyển provider mà không sửa business code, quy ước cùng property key:

| Property | Ý nghĩa | Loại |
| --- | --- | --- |
| spring.datasource.username | Database login | Secret |
| spring.datasource.password | Database password | Secret |
| partner.api.key | Partner API token | Secret |
| spring.datasource.url | Database endpoint | Configuration |
| partner.base-url | Partner endpoint | Configuration |
| app.rotation.expected-version | Secret version dự kiến trong deployment | Metadata/configuration |

Mỗi provider có thể đặt tên secret resource khác nhau. Điều quan trọng là giá trị cuối cùng được bind vào cùng property key trong Spring Environment.

### 4.3. Danh tính runtime

Mỗi workload phải dùng identity của chính runtime:

- AWS: IAM role gắn với EC2 instance profile, ECS task role hoặc EKS workload identity/IRSA.
- Azure: system-assigned hoặc user-assigned managed identity; local development có thể dùng DefaultAzureCredential.
- Google Cloud: service account gắn với Cloud Run/GCE hoặc Workload Identity Federation cho GKE.

Không lưu access key, client secret hoặc service-account JSON key trong image nếu nền tảng hỗ trợ workload identity. Cấp quyền đọc đúng secret resource thay vì quyền admin toàn account/project/subscription.

### 4.4. Tương thích phiên bản Spring

Các starter có release train riêng. Chọn BOM theo Spring Boot/Spring Cloud version của ứng dụng, không ghép ngẫu nhiên các dependency:

| Hệ sinh thái | Dòng thư viện hiện hành tham khảo | Spring Boot tương thích |
| --- | --- | --- |
| Spring Cloud AWS | 4.1.x | Spring Boot 4.x; dòng 3.4.x dành cho Boot 3.5.x |
| Spring Cloud Azure | 7.5.x | Spring Boot 4.0.x/4.1.x; dòng 6.x hoặc 5.x phù hợp Boot 3.5.x theo mapping |
| Spring Framework on Google Cloud | 8.2.x | Spring Boot 4.0.x/4.1.x; dòng 7.5.x phù hợp Boot 3.5.x |

Bảng là mốc tham khảo theo tài liệu/release hiện hành tại thời điểm soạn bài. Kiểm tra compatibility matrix và release notes trước khi nâng cấp. Dùng BOM để đồng bộ Spring, cloud SDK và transitive dependencies.

## 5. AWS: Secrets Manager và Parameter Store

### 5.1. Chọn dịch vụ

AWS cung cấp hai lựa chọn thường gặp:

- **Secrets Manager:** lưu database credentials, API token và secret cần lifecycle/rotation. Có version và staging labels như AWSCURRENT, AWSPREVIOUS, AWSPENDING; hỗ trợ rotation workflow qua Lambda.
- **Systems Manager Parameter Store:** lưu cấu hình phân cấp, hỗ trợ String, StringList và SecureString. SecureString được mã hóa bằng AWS KMS. Parameter Store phù hợp cấu hình và một số secret đơn giản; không thay thế rotation workflow của Secrets Manager.

Nếu cần tự động rotate database password hoặc API credential, ưu tiên Secrets Manager. Với Parameter Store SecureString, ứng dụng/automation phải tự xây dựng quy trình cập nhật giá trị và credential ở dịch vụ đích.

### 5.2. Dependency

Dùng Spring Cloud AWS BOM và hai starter cần thiết:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>4.1.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
    </dependency>
</dependencies>
~~~

Nếu ứng dụng chỉ dùng Secrets Manager, bỏ Parameter Store starter. Nếu dự án đang dùng Spring Boot 3.5.x, chọn dòng Spring Cloud AWS tương thích Boot 3.5.x thay vì dùng BOM 4.x.

### 5.3. Tạo secret JSON

Tạo secret resource cho document-service, ví dụ:

~~~json
{
  "username": "DOCUMENT_SERVICE_DB_USER",
  "password": "VALUE_PROVIDED_BY_SECRET_ROTATION_WORKFLOW"
}
~~~

Đây là cấu trúc dữ liệu minh họa. Giá trị thực được tạo bằng quy trình cấp credential và nhập trực tiếp vào Secrets Manager qua Console/API/automation có bảo vệ. Không đưa giá trị thật vào source code, shell history hoặc ticket.

Tên secret ví dụ:

~~~text
/prod/document-service/database
~~~

JSON top-level keys sẽ trở thành property keys trong Spring Environment. Có thể dùng prefix để tránh trùng tên với property của module khác.

Partner API key được lưu trong secret riêng để có owner, version và lịch rotate độc lập:

~~~json
{
  "key": "VALUE_PROVIDED_BY_PARTNER_CREDENTIAL_WORKFLOW"
}
~~~

Đặt tên resource là /prod/document-service/partner-api và import với prefix partner.api. để tạo property partner.api.key.

### 5.4. Nạp Secrets Manager và Parameter Store

File application-aws.yml:

~~~yaml
spring:
  config:
    import: "aws-secretsmanager:/prod/document-service/database?prefix=spring.datasource.,aws-secretsmanager:/prod/document-service/partner-api?prefix=partner.api.,aws-parameterstore:/prod/document-service/"
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Secret JSON cung cấp username/password với prefix spring.datasource. Parameter Store có thể cung cấp các property không nhạy cảm như app.retry.max-attempts hoặc app.feature.new-workflow.

Nếu secret database là bắt buộc, giữ import ở chế độ required. Chỉ dùng optional cho nguồn cấu hình thật sự tùy chọn. Spring Cloud AWS cũng cho phép import nhiều secret/path và thêm prefix để tránh property collision.

### 5.5. Dùng Parameter Store cho cấu hình

Ví dụ cây parameter:

~~~text
/prod/document-service/app/retry/max-attempts
/prod/document-service/app/feature/new-workflow
/prod/document-service/app/partner/timeout
~~~

Khi import path /prod/document-service/, Spring Cloud AWS đưa các key con vào Environment. Với cấu hình nhạy cảm cần mã hóa, dùng SecureString và KMS. IAM policy có thể cần ssm:GetParametersByPath; nếu SecureString dùng customer-managed KMS key, workload còn cần kms:Decrypt trên key tương ứng.

Parameter Store standard parameter có giới hạn payload nhỏ hơn advanced parameter. Không gom một cấu hình lớn vào một parameter nếu vượt giới hạn. Với nhiều key, dùng path hierarchy và prefix.

### 5.6. IAM policy cho workload

Workload chỉ đọc secret được chỉ định:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:ACCOUNT_ID:secret:/prod/document-service/database-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:ACCOUNT_ID:parameter/prod/document-service/*"
    }
  ]
}
~~~

Nếu secret được mã hóa bằng customer-managed KMS key, thêm kms:Decrypt cho đúng key ARN và giới hạn qua encryption context khi phù hợp. Không cấp secretsmanager:* hoặc ssm:* cho runtime chỉ để lấy một secret.

Tách role:

- Application role: GetSecretValue và quyền đọc Parameter Store.
- Rotation Lambda role: đọc/ghi version, thay credential ở database/service và test credential mới.
- Secret administrator: tạo secret, cấu hình rotation, policy và tags.
- Auditor: đọc metadata/audit nhưng không cần payload secret.

### 5.7. AWS Default Credentials Provider Chain

Spring Cloud AWS dùng AWS SDK credential provider chain. Trên production, ưu tiên IAM role thay vì access key:

- EC2 dùng instance profile.
- ECS dùng task role.
- EKS dùng IRSA hoặc EKS Pod Identity theo kiến trúc cluster.
- Local development dùng profile của AWS CLI/SSO.
- CI/CD dùng OIDC federation/assume role nếu nền tảng hỗ trợ.

Không thêm aws.access-key-id và aws.secret-access-key vào application.yml. Không dùng user cá nhân làm identity runtime production.

### 5.8. Secrets Manager version labels

Secrets Manager gắn staging labels vào secret version:

| Label | Ý nghĩa |
| --- | --- |
| AWSCURRENT | Version đang được ứng dụng lấy mặc định |
| AWSPREVIOUS | Version trước đó, thường là bản có thể rollback |
| AWSPENDING | Version đang trong quy trình rotate |

Rotation Lambda chuẩn có bốn bước:

1. createSecret: tạo secret version mới và gắn AWSPENDING.
2. setSecret: cập nhật credential ở database hoặc dịch vụ đích.
3. testSecret: thử đăng nhập hoặc gọi API bằng credential mới.
4. finishSecret: chuyển AWSCURRENT sang version mới; version trước trở thành AWSPREVIOUS.

Rotation function phải idempotent. Nếu workflow dừng giữa chừng, lần chạy tiếp theo phải nhận diện version AWSPENDING và tiếp tục/khôi phục đúng trạng thái. Không ghi password mới hoặc cũ vào CloudWatch Logs.

### 5.9. Bật reload trong Spring Cloud AWS

PropertySource reload của Secrets Manager/Parameter Store mặc định tắt. Để dùng refresh hoặc restart strategy, bổ sung các dependency cần thiết:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Ví dụ cấu hình reload Secrets Manager:

~~~yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: restart_context
          period: 30s
          max-wait-time-for-restart: 10s
~~~

Các chiến lược:

- refresh: refresh bean được hỗ trợ, như bean cấu hình dùng @ConfigurationProperties hoặc @RefreshScope.
- restart_context: khởi động lại Spring ApplicationContext để tạo lại bean từ cấu hình mới. Cần bật và bảo vệ restart actuator endpoint theo tài liệu Spring Cloud AWS.

Nếu chọn restart_context, cấu hình endpoint theo tài liệu starter và chỉ expose qua management network đã xác thực:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: restart
~~~

Đối với database password, rolling restart có kiểm soát thường dễ kiểm chứng hơn. Không giả định đổi secret sẽ tự thay password trong mọi connection HikariCP đang mở.

### 5.10. Kiểm tra AWS

- Kiểm tra VersionIdsToStages bằng DescribeSecret, không in SecretString.
- Xác nhận AWSCURRENT trỏ đúng version đã test.
- Xác nhận role của application chỉ đọc secret cần thiết.
- Thử thiếu ssm:GetParametersByPath hoặc secretsmanager:GetSecretValue để kiểm tra lỗi 403.
- Xác minh refresh/restart đã tạo DataSource mới.
- Kiểm tra CloudTrail và log rotation Lambda không chứa credential.

## 6. Azure: Key Vault Secrets và Spring Cloud Azure

### 6.1. Key Vault lưu secret theo version

Azure Key Vault lưu mỗi lần set secret thành một version mới. Giá trị version cũ vẫn tồn tại theo retention/soft-delete và policy của vault. Ứng dụng thường đọc version hiện hành thông qua SecretClient/PropertySource.

Key Vault quản lý secrets, keys và certificates. Với cấu hình không nhạy cảm như feature flag, endpoint hoặc timeout, Azure App Configuration là dịch vụ phù hợp hơn. Không biến Key Vault thành nơi lưu toàn bộ application configuration.

### 6.2. Dependency

Dùng Spring Cloud Azure BOM và Key Vault Secrets starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>7.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud Azure 7.x phù hợp với Spring Boot 4.x. Nếu ứng dụng dùng Spring Boot 3.5.x, chọn dòng Spring Cloud Azure tương thích 5.x/6.x theo compatibility mapping và release notes.

### 6.3. Secret name và property mapping

Tên secret trong Key Vault chỉ hỗ trợ chữ cái, số và dấu gạch nối. Dấu chấm trong property key không hợp lệ ở secret name.

Ví dụ ánh xạ:

| Secret name trong Key Vault | Spring property |
| --- | --- |
| spring-datasource-username | spring.datasource.username |
| spring-datasource-password | spring.datasource.password |
| partner-api-key | partner.api.key |

Spring Cloud Azure KeyVaultPropertySource ánh xạ tên secret thành property key. Khi cần key có ký tự đặc biệt hoặc cấu trúc khác, dùng property placeholder trong application configuration.

### 6.4. Cấu hình PropertySource

Ví dụ application-azure.yml:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: document-service-secrets
              endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - spring-datasource-username
                - spring-datasource-password
                - partner-api-key
              refresh-interval: 5m
~~~

Endpoint được thay bằng URI vault thực tế qua cấu hình môi trường. Danh sách secret-keys giới hạn những secret mà property source cần đọc; nếu bỏ trường này, integration có thể lấy toàn bộ secrets trong vault theo cấu hình.

Refresh interval mặc định của KeyVaultPropertySource là 30 phút. Ví dụ trên rút xuống 5 phút để minh họa; thời gian ngắn hơn làm tăng số lần gọi Key Vault và không thay thế quy trình rotation.

### 6.5. Managed Identity và DefaultAzureCredential

Trên Azure App Service, VM, Container Apps hoặc AKS, ưu tiên managed identity hoặc workload identity. Ví dụ system-assigned managed identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
~~~

Với user-assigned managed identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID
~~~

Trong local development, DefaultAzureCredential có thể dùng danh tính đã đăng nhập qua Azure CLI/IDE. Khi chạy trên Azure, credential chain có thể dùng managed identity. Không lưu client secret của service principal trong application.yml nếu workload identity có thể đáp ứng use case.

### 6.6. Azure RBAC cho Key Vault

Với mô hình Azure RBAC, runtime principal cần role Key Vault Secrets User để đọc secret payload. Role Key Vault Reader chỉ đọc metadata, không đọc secret value. Key Vault Contributor quản lý tài nguyên control plane nhưng không tự cấp quyền đọc data plane.

Tách vai trò:

- Application managed identity: Key Vault Secrets User ở scope vault hoặc secret cần đọc.
- Rotation Function identity: quyền đọc/ghi secret và cập nhật credential ở dịch vụ đích.
- Secret operator: Key Vault Secrets Officer để tạo/cập nhật secret.
- Vault administrator: quản lý vault và role assignment theo trách nhiệm.

Không cấp Key Vault Administrator hoặc Owner cho ứng dụng runtime. Ưu tiên RBAC thay vì legacy access policy khi triển khai vault mới theo chuẩn hiện hành.

### 6.7. Refresh PropertySource

KeyVaultPropertySource tự refresh secrets theo refresh-interval. Giá trị mặc định là 30 phút; đặt 0 để tắt tự refresh.

Cần phân biệt:

- PropertySource refresh: tải lại secret value từ Key Vault.
- Spring bean refresh: cập nhật object đã bind property.
- Client refresh: tạo lại HTTP client hoặc DataSource đang giữ credential.
- Credential revoke: thu hồi password/key cũ ở hệ thống đích.

Bốn việc này không tự động đồng thời. Với database password, dùng rolling restart hoặc custom pool replacement đã được kiểm thử. Với partner client, có thể dùng @RefreshScope cho configuration bean và tái tạo client theo lifecycle phù hợp.

### 6.8. Xoay vòng secret bằng Event Grid

Key Vault có thể phát event khi secret mới được tạo hoặc secret gần hết hạn. Một quy trình tự động thường gồm:

1. Key Vault phát SecretNearExpiry hoặc SecretNewVersionCreated.
2. Event Grid chuyển event tới Azure Function/worker.
3. Rotation worker xác định secret và credential đích.
4. Worker tạo credential mới ở dịch vụ đích hoặc tạo key mới.
5. Worker ghi secret version mới vào Key Vault.
6. Worker kiểm tra credential mới.
7. Ứng dụng nhận version mới qua PropertySource refresh hoặc rolling restart.
8. Sau khi tất cả instance dùng version mới, worker thu hồi credential cũ.

Với database/service chỉ cho phép một password, có thể có khoảng thời gian giữa cập nhật Key Vault và cập nhật hệ thống đích. Ưu tiên dual credential/overlap nếu dịch vụ hỗ trợ. Nếu không hỗ trợ, cần quy trình đổi password có phối hợp, health check và rollback cụ thể.

### 6.9. Kiểm tra Azure

- Xác minh managed identity đúng principal.
- Xác minh Key Vault Secrets User có scope đúng.
- Thử truy cập secret không được cấp để xác nhận 403.
- Kiểm tra secret name có dấu chấm hoặc ký tự không hợp lệ không.
- Xác nhận refresh interval và secret-keys đúng.
- Kiểm tra DataSource/HTTP client có được tái tạo sau rotation.
- Kiểm tra Event Grid delivery và Function execution log đã redact secret.

## 7. Google Cloud: Secret Manager và Spring Framework on Google Cloud

### 7.1. Secret version là immutable

Google Cloud Secret Manager tách secret resource khỏi secret version. Payload nằm trong version và không thể sửa trực tiếp. Khi thay giá trị, tạo version mới. Secret có thể có nhiều version đang enabled/disabled/destroyed.

Tài liệu hiện hành khuyến nghị pin version number cho production deployment thay vì luôn tham chiếu latest. latest thuận tiện nhưng version lỗi có thể được phân phối đồng loạt tới tất cả instance khi ứng dụng restart hoặc scale out.

### 7.2. Dependency và BOM

Dùng Spring Framework on Google Cloud BOM và Secret Manager starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>8.2.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
    </dependency>
</dependencies>
~~~

Spring Framework on Google Cloud 8.x phù hợp với Spring Boot 4.x. Với Spring Boot 3.5.x, dùng dòng 7.x và BOM tương ứng. Không trộn Spring Cloud GCP 7.x với Boot 4.x.

### 7.3. Application Default Credentials

Spring Cloud GCP mặc định dùng Application Default Credentials (ADC). Trên runtime, ADC có thể lấy credential từ service account gắn với workload hoặc Workload Identity Federation. Trên GKE, ưu tiên Workload Identity cho Kubernetes service account; trên Cloud Run/GCE dùng service identity tương ứng.

Local development có thể dùng gcloud application-default login. Không commit service-account JSON key vào repository hoặc Docker image. Nếu dùng GCE/GKE, xác minh OAuth scope cloud-platform theo yêu cầu nền tảng và cấu hình IAM role đúng service account.

### 7.4. IAM role

Runtime chỉ cần đọc payload secret được chỉ định:

~~~text
roles/secretmanager.secretAccessor
~~~

Cấp role ở cấp secret nếu ứng dụng chỉ đọc một vài secret. Không cấp ở project scope nếu không cần đọc tất cả secret trong project.

Tách identity:

- Application service account: Secret Accessor trên secret cụ thể.
- Rotation worker: Secret Version Adder để tạo version mới.
- Rotation operator: Secret Version Manager khi cần enable/disable/destroy version.
- Secret administrator: Secret Manager Admin để quản lý secret và IAM.

Việc cấp quyền đọc secret không đồng nghĩa được tạo hoặc phá hủy version.

### 7.5. Secret Manager Config Data Resource

Starter dùng Spring Boot Config Data API. Từ Spring Framework on Google Cloud 6.0, cú pháp mới sm@ là cú pháp được khuyến nghị; cú pháp sm:// cũ phát cảnh báo deprecation.

Ví dụ application.properties:

~~~properties
spring.config.import=sm@
spring.cloud.gcp.project-id=YOUR_GCP_PROJECT_ID

spring.datasource.username=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/document-db-username/versions/7}
spring.datasource.password=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/document-db-password/versions/12}
partner.api.key=${sm@projects/YOUR_GCP_PROJECT_ID/secrets/partner-api-key/versions/4}
~~~

Thay project ID và version ID bằng resource thực tế. Dùng version number cố định để một deployment có thể tái tạo và rollback. Không đặt payload secret trực tiếp trong file properties.

Với regional secret, dùng resource path có locations và location ID theo cú pháp tài liệu Secret Manager. Kiểm tra replication/location policy của secret theo yêu cầu residency.

### 7.6. SecretManagerTemplate

Spring Framework on Google Cloud cung cấp SecretManagerTemplate để đọc, tạo và cập nhật secret bằng API trong Java. Dùng template khi ứng dụng/automation cần thao tác imperative, ví dụ worker tạo version mới. Không để application runtime có quyền tạo version nếu nó chỉ cần đọc secret.

Khi dùng template, xử lý response metadata/version ID và không log payload. Các API version operation phải có IAM permission tương ứng.

### 7.7. Refresh secret qua Actuator

Tích hợp GCP hỗ trợ refresh secret mà không restart cho bean phù hợp:

1. Thêm Spring Boot Actuator.
2. Expose refresh endpoint có kiểm soát.
3. Cấu hình bean dùng @ConfigurationProperties và @RefreshScope.
4. Cập nhật secret version trong Secret Manager.
5. Gọi POST /actuator/refresh qua management network đã xác thực.
6. Xác minh bean nhận giá trị mới.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.validation.annotation.Validated;

@Validated
@RefreshScope
@ConfigurationProperties(prefix = "partner.api")
public class PartnerConfiguration {

    @NotBlank
    private String key;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    @Override
    public String toString() {
        return "PartnerConfiguration{key=[REDACTED]}";
    }
}
~~~

Actuator refresh không tự bảo đảm DataSource, HikariCP hoặc mọi singleton được tạo lại. Với database credential, thực hiện rolling restart hoặc custom DataSource replacement có drain connection và test riêng. Không expose refresh endpoint công khai.

### 7.8. Rotation notification qua Pub/Sub

Secret Manager có thể gửi message SECRET_ROTATE tới Pub/Sub topic theo rotation schedule. Secret Manager chỉ gửi notification; subscriber/worker phải thực hiện việc tạo credential mới, thêm secret version và cập nhật hệ thống đích.

Các điểm cần nhớ:

- Rotation period tối thiểu một giờ.
- next_rotation_time phải được đặt phù hợp và không thể nhỏ hơn năm phút trong tương lai.
- Pub/Sub topic và subscriber phải được cấu hình.
- Worker phải idempotent và xử lý retry.
- Secret Manager không tự đổi password ở database hoặc API provider.
- Tránh chạy đồng thời nhiều rotation workflow trên cùng một secret.

### 7.9. Kiểm tra Google Cloud

- Xác minh ADC đang dùng service account mong muốn.
- Kiểm tra Secret Accessor chỉ được gán cho secret cần thiết.
- Kiểm tra version ID và trạng thái enabled.
- Thử đọc version bị disable để xác nhận ứng dụng xử lý lỗi.
- Xác minh Pub/Sub nhận SECRET_ROTATE.
- Kiểm tra worker tạo version mới và ghi nhận version ID.
- Kiểm tra rolling restart hoặc refresh bean hoạt động.
- Xác minh version cũ vẫn còn để rollback trong cửa sổ kiểm soát.

## 8. So sánh ba cloud provider

| Khả năng | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Dịch vụ secret | Secrets Manager | Key Vault Secrets | Secret Manager |
| Cấu hình không nhạy cảm | Parameter Store/AppConfig | App Configuration | Config service/ConfigMap |
| Spring integration | Spring Cloud AWS | Spring Cloud Azure | Spring Framework on Google Cloud |
| Nạp cấu hình | spring.config.import với aws-secretsmanager | KeyVaultPropertySource | Config Data resource sm@ |
| Danh tính workload | IAM role/STS web identity | Managed Identity/Workload Identity | ADC/Workload Identity Federation |
| Quyền đọc | secretsmanager:GetSecretValue | Key Vault Secrets User | roles/secretmanager.secretAccessor |
| Versioning | Secret versions + staging labels | Secret versions | Secret versions |
| Rotation trigger | Lambda rotation workflow | Event Grid + Function/worker | Pub/Sub rotation notification |
| Refresh mặc định | Reload integration tắt mặc định | PropertySource refresh 30 phút | Không tự liên tục; có Actuator refresh |
| Rollback | AWSPREVIOUS hoặc version stage | Chọn version trước | Pin version ID trước đó |
| Đặc điểm cần chú ý | Secrets Manager có quy trình rotation 4 bước | Secret name không chứa dấu chấm | latest có thể phân phối lỗi đồng loạt |

### 8.1. Khác biệt về rotation

AWS Secrets Manager có quy trình rotation tích hợp qua Lambda và staging labels. Azure Key Vault tạo version mới, còn Event Grid/Function hoặc worker chịu trách nhiệm phối hợp cập nhật credential ở dịch vụ đích. Google Cloud Secret Manager phát rotation notification qua Pub/Sub; subscriber thực hiện việc đổi credential và tạo version mới.

Không provider nào có thể tự biết mọi dịch vụ bên ngoài cần thay password theo cách giống nhau. Rotation workflow phải hiểu giao thức của hệ thống đích.

### 8.2. Khác biệt về refresh

- AWS: reload cần bật và có dependency hỗ trợ; refresh hoặc restart_context có hành vi khác nhau.
- Azure: KeyVaultPropertySource refresh theo chu kỳ; cần xác minh bean/client có nhận giá trị mới hay không.
- Google Cloud: Config Data nạp secret; Actuator refresh hỗ trợ bean @ConfigurationProperties/@RefreshScope theo tài liệu.

Với DataSource, client có pool, TLS context hoặc SDK client giữ credential, hãy coi rolling restart là lựa chọn mặc định cho đến khi có test chứng minh refresh in-place an toàn.

### 8.3. Không ép mọi provider vào một API giả lập

Business service có thể dùng cùng property key, nhưng provider adapter, identity, rotation trigger và version semantics vẫn khác nhau. Tách cấu hình theo profile và giữ business code phụ thuộc interface nghiệp vụ, không phụ thuộc AWS SecretsManagerClient, Azure SecretClient hay Google SecretManagerTemplate.

## 9. Quy trình xoay vòng bí mật an toàn

### 9.1. Chuẩn bị trước khi rotate

Mỗi secret cần có metadata quản trị:

- Owner nghiệp vụ và owner kỹ thuật.
- Ứng dụng, môi trường và resource sử dụng.
- Loại credential và hệ thống đích.
- Ngày tạo, ngày rotate gần nhất và hạn dùng nếu có.
- Secret resource ID và version ID.
- Số lượng replica/consumer.
- Quy trình rotate, test, rollback và revoke.
- Contact/on-call khi rotation thất bại.

Lập inventory cho database password, partner API key, SMTP credential, certificate và signing key. Không ghi payload secret vào inventory.

### 9.2. Ưu tiên overlap hoặc dual credential

Nếu hệ thống đích cho phép hai credential cùng hoạt động, dùng quy trình:

1. Tạo credential mới.
2. Giữ credential cũ còn hiệu lực.
3. Lưu credential mới thành secret version.
4. Triển khai canary hoặc một replica đọc version mới.
5. Kiểm tra kết nối và quyền.
6. Rolling restart các replica còn lại.
7. Theo dõi lỗi xác thực, connection pool và request latency.
8. Xác nhận không còn consumer dùng credential cũ.
9. Thu hồi credential cũ.

Overlap giúp có thời gian rollback nếu credential mới sai hoặc chưa được mọi instance nhận.

### 9.3. Khi hệ thống đích chỉ có một password

Một số database hoặc dịch vụ chỉ cho một password đang hoạt động. Khi đó cần phối hợp chặt:

1. Đưa ứng dụng vào maintenance/controlled rollout nếu cần.
2. Tạo backup hoặc xác nhận đường truy cập quản trị dự phòng.
3. Thay password ở hệ thống đích.
4. Cập nhật secret manager ngay sau đó.
5. Restart/refresh workload theo kế hoạch.
6. Kiểm tra kết nối từ từng vùng/replica.
7. Nếu lỗi, dùng tài khoản quản trị để đặt lại password và đồng bộ secret version.
8. Ghi lại thời gian gián đoạn và bằng chứng kiểm thử.

Với hệ thống hỗ trợ credential rollover, user A/B hoặc token overlap, nên chuyển sang mô hình đó để giảm downtime.

### 9.4. Canary và rolling deployment

Không thay secret đồng thời ở tất cả instance nếu không có lý do. Một quy trình rollout có thể:

- Canary: một instance hoặc một phần nhỏ traffic dùng version mới.
- Verify: health check, database connection, API success rate và authorization.
- Expand: chuyển tiếp các replica còn lại.
- Stabilize: theo dõi trong cửa sổ đã định.
- Revoke: thu hồi credential cũ sau khi xác nhận.

Mỗi deployment nên ghi version ID đang sử dụng. Không log payload, chỉ log version identifier hoặc metadata không nhạy cảm.

### 9.5. Rollback

Rollback không chỉ là đổi secret manager trỏ về version cũ. Credential cũ phải còn hiệu lực ở hệ thống đích. Nếu đã revoke credential cũ, rollback bằng version cũ sẽ không giúp kết nối thành công.

Trước khi thu hồi credential cũ:

- Xác nhận tất cả instance dùng version mới.
- Xác nhận job, scheduled task, batch worker và disaster recovery environment đã chuyển.
- Xác nhận connection pool đã được tạo lại.
- Kiểm tra audit/access log không còn lượt sử dụng credential cũ nếu hệ thống hỗ trợ.
- Giữ rollback path có thời hạn và owner rõ.

## 10. Làm mới Spring bean và connection pool

### 10.1. Vì sao refresh có thể chưa đủ?

Giả sử Spring Boot bind password vào DataSource lúc startup. Secret manager cập nhật giá trị mới trong Environment, nhưng DataSource/HikariCP đã được tạo trước đó. Pool có thể tiếp tục mở connection bằng password cũ.

Tương tự:

- HTTP client có thể cache Authorization header.
- SDK client có thể giữ token/certificate.
- TLS context có thể giữ certificate cũ.
- Background worker có thể giữ object cấu hình cũ.
- Bean singleton có thể không đọc Environment mỗi lần gọi.

### 10.2. Chọn chiến lược theo loại secret

| Loại secret | Cách rollout khuyến nghị |
| --- | --- |
| API key đọc mỗi request từ refresh-scoped config | Refresh bean và test request |
| HTTP client giữ API key trong interceptor | Tạo lại client sau refresh |
| Database username/password trong HikariCP | Rolling restart hoặc thay pool có drain |
| TLS client certificate | Reload SSL context/client hoặc restart |
| Signing key có key ID/version | Hỗ trợ nhiều key và key rotation overlap |
| Token ngắn hạn lấy từ identity provider | Refresh token qua credential provider, không rotate thủ công |

### 10.3. Dùng @RefreshScope đúng chỗ

@RefreshScope phù hợp với bean cấu hình có thể tạo lại sau refresh. Không bọc tùy tiện toàn bộ service hoặc DataSource mà không kiểm tra proxy, lifecycle và connection close. Với pool, cần bảo đảm:

- Không trả connection đang dùng về pool đã đóng.
- Không ngắt transaction đang chạy.
- Pool mới dùng secret version mới.
- Pool cũ được drain và close.
- Nếu pool mới không mở được, ứng dụng giữ trạng thái readiness an toàn hoặc rollback.

### 10.4. Bảo vệ Actuator

Nếu dùng /actuator/refresh hoặc /actuator/restart:

- Chỉ expose endpoint cần thiết.
- Chỉ truy cập từ management network.
- Bắt buộc authentication/authorization.
- Không expose env, configprops, heapdump hoặc endpoint nhạy cảm công khai.
- Ghi audit người gọi endpoint.
- Không để endpoint refresh trở thành public trigger có thể gây restart storm.

### 10.5. Readiness và startup

Nếu secret bắt buộc không đọc được, ứng dụng không nên nhận traffic. Dùng readiness check để chờ DataSource/client khởi tạo thành công. Liveness chỉ kiểm tra process còn sống; không restart liên tục chỉ vì secret manager tạm thời chậm.

Cấu hình retry startup có giới hạn và backoff. Nếu secret manager unavailable, quyết định fail startup hay tiếp tục dùng version đã cache phải là quyết định có chủ đích, được đánh giá theo mức rủi ro và yêu cầu availability.

## 11. Bảo mật và vận hành secret

### 11.1. Least privilege

- Application chỉ đọc secret cần cho service.
- Rotation worker có quyền tạo version và cập nhật credential đích.
- Operator quản lý lifecycle và policy.
- Auditor xem metadata/log nhưng không cần đọc payload.
- Tách secret theo app, environment và purpose.
- Tránh chia sẻ cùng một database password cho nhiều service.

### 11.2. Encryption và network

Secret manager mã hóa dữ liệu at rest và bảo vệ kết nối bằng TLS. Với yêu cầu network isolation, dùng private endpoint/VPC endpoint/service endpoint theo cloud. Network restriction không thay IAM; workload vẫn cần đúng identity và permission.

### 11.3. Logging và observability

Log metadata có thể hữu ích:

- Secret resource name hoặc opaque identifier.
- Version ID.
- Rotation event ID.
- Actor/rotation worker identity.
- Start/end timestamp.
- Outcome và failure code.
- Application deployment ID.

Không log secret payload, password, token, private key, certificate private material hoặc request header chứa credential.

### 11.4. Rotation metrics

Theo dõi:

- Secret age và thời điểm rotate gần nhất.
- Secret sắp hết hạn.
- Rotation success/failure.
- Số instance còn dùng version cũ.
- Secret access denied/timeout.
- Authentication failure sau rotation.
- Connection pool creation failure.
- Rollback count.
- Credential cũ còn được sử dụng sau cửa sổ chuyển đổi.

Đặt alert khi secret quá hạn rotate, rotation thất bại hoặc application chưa chuyển version trước deadline.

### 11.5. Audit và incident response

Khi nghi ngờ secret bị lộ:

1. Xác định secret và consumer bị ảnh hưởng.
2. Tạo credential mới hoặc revoke credential cũ theo mức độ khẩn cấp.
3. Cập nhật secret manager và rollout ứng dụng.
4. Kiểm tra access log/audit event của secret manager.
5. Kiểm tra hệ thống đích có request lạ hay không.
6. Thu hồi credential bị lộ sau khi xác nhận ứng dụng dùng credential mới.
7. Xem xét rotate các secret liên quan nếu chúng có cùng trust boundary.
8. Ghi timeline, owner và evidence.

Không chỉ xóa secret khỏi Git. Nếu secret từng được commit, phải coi credential đã bị lộ và rotate ở hệ thống đích.

## 12. Bài thực hành end-to-end

### 12.1. Tình huống

document-service chạy trên một cloud provider và cần:

- Kết nối PostgreSQL bằng username/password.
- Gọi partner API bằng API key.
- Đọc timeout và retry count từ cấu hình không nhạy cảm.
- Xoay vòng database password mỗi chu kỳ vận hành.
- Xoay partner API key khi nghi ngờ bị lộ.
- Rollback nếu version mới làm health check thất bại.

### 12.2. Chuẩn bị tài nguyên

Chọn một trong ba môi trường:

**AWS**

- Tạo Secrets Manager secret cho database credentials.
- Tạo Parameter Store path cho retry/timeout/feature flags.
- Gắn IAM role cho workload.
- Tạo rotation Lambda hoặc workflow rotation phù hợp database.
- Bật CloudTrail và CloudWatch monitoring.

**Azure**

- Tạo Key Vault cho môi trường tương ứng.
- Bật Azure RBAC permission model.
- Gắn managed identity cho workload.
- Gán Key Vault Secrets User cho identity ứng dụng.
- Tạo Event Grid subscription và Function/worker nếu cần tự động rotate.
- Bật diagnostic logs.

**Google Cloud**

- Tạo Secret Manager secret và version.
- Gắn service account hoặc Workload Identity cho workload.
- Gán Secret Accessor ở cấp secret.
- Tạo Pub/Sub topic/subscriber nếu dùng rotation schedule.
- Bật audit logs và monitoring.

### 12.3. Cấu hình Spring profile

Chọn profile theo môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=aws
~~~

Hoặc:

~~~bash
SPRING_PROFILES_ACTIVE=azure
~~~

Hoặc:

~~~bash
SPRING_PROFILES_ACTIVE=gcp
~~~

Chỉ profile tương ứng được dùng khi chạy một deployment. Không bật đồng thời ba profile secret manager trong production nếu ứng dụng không có nhu cầu đọc nhiều cloud.

### 12.4. Xác minh startup

Sau khi ứng dụng khởi động:

1. Xác nhận profile được kích hoạt.
2. Xác nhận secret resource được đọc bằng workload identity.
3. Xác nhận DataSource kết nối thành công.
4. Xác nhận partner client gọi endpoint test thành công.
5. Xác nhận property không nhạy cảm được bind đúng.
6. Kiểm tra log không chứa secret.
7. Kiểm tra quyền read chỉ giới hạn resource cần thiết.

Không tạo endpoint debug trả về Environment hoặc cấu hình đầy đủ để xác minh secret.

### 12.5. Xoay vòng database password

Thực hiện trong staging trước:

1. Tạo credential database mới theo cơ chế dual credential/overlap nếu hỗ trợ.
2. Ghi credential mới thành secret version.
3. Chọn version mới cho canary hoặc tạo deployment mới.
4. Restart canary để DataSource/HikariCP nạp password mới.
5. Chạy truy vấn smoke test và transaction rollback test.
6. Mở traffic cho canary và theo dõi lỗi kết nối.
7. Rolling restart các replica còn lại.
8. Xác nhận không còn replica dùng version cũ.
9. Thu hồi credential cũ.
10. Lưu version ID, deployment ID và kết quả kiểm thử.

### 12.6. Xoay partner API key

1. Yêu cầu partner cấp key thứ hai nếu họ hỗ trợ overlap.
2. Lưu key mới vào secret manager.
3. Refresh PartnerProperties hoặc rolling restart.
4. Tạo request canary và kiểm tra response.
5. Tăng dần traffic.
6. Xác nhận key cũ không còn được sử dụng.
7. Thu hồi key cũ ở partner.
8. Kiểm tra application log và partner audit.

Nếu partner chỉ cho một key hoạt động, phối hợp thời điểm đổi key và rollout để giảm thời gian gián đoạn.

### 12.7. Thử rollback

Tạo một secret version test không hợp lệ trong môi trường staging:

- Canary phải phát hiện authentication failure.
- Không mở rộng rollout.
- Ứng dụng ghi failure code và version metadata, không ghi payload.
- Khôi phục version tốt hoặc tạo lại credential.
- Recreate client/pool.
- Kiểm tra health và readiness.
- Giữ credential cũ còn hiệu lực cho tới khi hoàn tất rollback.

Không thử secret sai trên production hoặc credential dùng chung.

## 13. Kiểm thử

### 13.1. Unit tests

Kiểm tra:

- Configuration properties validate khi thiếu key bắt buộc.
- toString() và log không hiển thị secret.
- Client builder nhận property mới sau refresh.
- Retry không lặp vô hạn.
- Secret version metadata được lưu cùng deployment state.
- Rollback chọn version đã xác nhận.

### 13.2. Integration tests

Trong account/project/subscription test riêng:

1. Ứng dụng đọc được secret đúng.
2. Workload identity không cần static credential.
3. Secret thiếu làm startup thất bại nếu required.
4. Principal không có permission nhận lỗi authorization.
5. Secret version mới được đọc đúng.
6. DataSource mới dùng credential mới.
7. Partner client mới dùng API key mới.
8. Credential cũ bị thu hồi sau khi rollout hoàn tất.
9. Refresh endpoint không thể gọi từ public network.
10. Secret payload không xuất hiện trong log/trace/metric.

### 13.3. Negative tests

- Tắt quyền đọc secret.
- Đặt sai secret resource name.
- Disable secret version đang được tham chiếu.
- Đặt secret hết hạn hoặc not-yet-valid nếu provider hỗ trợ.
- Dùng credential mới nhưng chưa cập nhật hệ thống đích.
- Thu hồi credential cũ quá sớm trong staging.
- Tạo rotation event trùng lặp.
- Gửi refresh đồng thời từ nhiều replica.
- Làm secret manager tạm thời unavailable.

Ứng dụng phải fail an toàn, có metric/correlation ID và không lộ secret trong error message.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Spring startup không tìm thấy config import | Starter thiếu, prefix sai hoặc profile chưa bật | Kiểm tra dependency, profile và cú pháp provider |
| AWS AccessDeniedException | Thiếu GetSecretValue/GetParametersByPath hoặc KMS Decrypt | Kiểm tra IAM role, ARN, region và KMS key policy |
| AWS secret mới đã tạo nhưng app vẫn dùng cũ | Reload chưa bật hoặc bean không refresh | Bật reload, chọn restart_context hoặc rolling restart |
| Azure 403 Forbidden | Managed identity chưa có Key Vault Secrets User | Kiểm tra principal và RBAC scope |
| Azure secret không bind đúng property | Secret name dùng dấu chấm hoặc mapping sai | Dùng dấu gạch nối và kiểm tra key mapping |
| Azure thay version nhưng app chưa nhận | Refresh interval chưa tới hoặc singleton không được tái tạo | Chờ refresh có kiểm soát hoặc restart workload |
| GCP PermissionDenied | Thiếu Secret Accessor hoặc ADC sai service account | Kiểm tra workload identity và role trên secret |
| GCP Config Data resolver không hoạt động | Starter thiếu hoặc cú pháp sm@ sai | Kiểm tra BOM, dependency và cú pháp mới |
| GCP version mới không được dùng | Ứng dụng pin version cũ | Cập nhật deployment version và rollout |
| Database vẫn từ chối sau khi secret đổi | HikariCP giữ connection/credential cũ hoặc DB password chưa đổi | Recreate pool, kiểm tra hệ thống đích và credential overlap |
| API partner trả 401/403 | Key mới chưa được kích hoạt hoặc client chưa reload | Kiểm tra trạng thái key và tạo lại client |
| Rotation worker chạy hai lần | Event redelivery hoặc retry | Dùng idempotency key và lưu rotation state |
| Rollback version cũ không kết nối | Credential cũ đã bị revoke | Tạo credential khôi phục hoặc cập nhật DB trước khi rollback |
| Actuator refresh bị lộ | Endpoint được expose công khai | Hạn chế management network và bật authentication |
| Secret xuất hiện trong log | Debug serialization, exception hoặc actuator | Redact, sửa logging và rotate credential đã lộ |

## 15. Runbook vận hành

### 15.1. Trước mỗi lần rotate

- Xác định owner và thời điểm rotate.
- Xác định toàn bộ workload/replica/worker sử dụng secret.
- Kiểm tra khả năng overlap và rollback.
- Xác nhận secret manager và hệ thống đích hoạt động.
- Kiểm tra rotation worker permission.
- Thông báo maintenance window nếu cần.

### 15.2. Trong lúc rotate

- Tạo credential mới ở hệ thống đích.
- Ghi version mới vào secret manager.
- Chạy canary.
- Kiểm tra database/API authentication.
- Rollout theo từng nhóm replica.
- Theo dõi metric và log.
- Giữ credential cũ còn hiệu lực.

### 15.3. Sau khi rotate

- Xác nhận mọi instance dùng version mới.
- Xác nhận connection pool được tạo lại.
- Thu hồi credential cũ.
- Đóng rotation event.
- Ghi version ID và deployment ID.
- Kiểm tra audit logs.
- Cập nhật ngày rotate tiếp theo.

### 15.4. Khi rotation thất bại

- Dừng rollout.
- Không revoke credential cũ.
- Xác định lỗi ở secret manager, identity, hệ thống đích hay application binding.
- Rollback secret version hoặc tạo version khôi phục.
- Recreate client/pool.
- Kiểm tra health và readiness.
- Chỉ mở lại traffic khi canary pass.
- Ghi lại nguyên nhân và cải thiện automation.

## 16. Bài tập tự đánh giá

1. Cấu hình thông thường khác secret như thế nào?
2. Vì sao không commit database password vào application-prod.yml?
3. Spring Boot Config Data API nạp secret ở giai đoạn nào?
4. Vì sao không dùng optional import cho database password bắt buộc?
5. AWS Parameter Store khác Secrets Manager ở điểm nào?
6. AWS Secrets Manager staging labels AWSCURRENT, AWSPREVIOUS và AWSPENDING có ý nghĩa gì?
7. Bốn bước của Lambda rotation workflow là gì?
8. Vì sao AWS workload nên dùng IAM role thay vì access key tĩnh?
9. Azure Key Vault secret name có giới hạn ký tự nào?
10. Key Vault Secrets User khác Key Vault Contributor ở điểm nào?
11. DefaultAzureCredential và Managed Identity liên hệ như thế nào?
12. Vì sao Azure KeyVaultPropertySource refresh không đồng nghĩa HikariCP tự đổi password?
13. Google Secret Manager lưu payload trong secret resource hay secret version?
14. Vì sao production nên pin version ID thay vì latest?
15. roles/secretmanager.secretAccessor cấp quyền gì?
16. Rotation schedule của Google Cloud tự đổi password database hay chỉ phát Pub/Sub notification?
17. Khi nào dùng @RefreshScope?
18. Vì sao DataSource cần restart hoặc pool replacement sau password rotation?
19. Vì sao cần giữ credential cũ trong thời gian rollout?
20. Khi nào có thể thu hồi credential cũ?
21. Nếu rotation worker nhận cùng một event hai lần, cần bảo vệ gì?
22. Vì sao không log secret version payload khi debug?
23. Làm thế nào chứng minh toàn bộ replica đã chuyển sang version mới?
24. Nếu rollback secret version nhưng credential cũ đã bị revoke, cần xử lý thế nào?

**Đáp án định hướng:** Configuration mô tả hành vi còn secret cho phép xác thực/truy cập; Spring Config Data nạp nguồn ngoài khi khởi động; required secret phải làm startup fail khi thiếu; Parameter Store thiên về cấu hình và SecureString, Secrets Manager có version labels và rotation workflow; AWSCURRENT là bản hiện hành, AWSPENDING đang rotate, AWSPREVIOUS là bản trước; Lambda rotation gồm createSecret, setSecret, testSecret, finishSecret; IAM role cung cấp credential ngắn hạn; Key Vault secret name chỉ hỗ trợ chữ/số/gạch nối; Secrets User đọc data plane còn Contributor quản lý control plane; DefaultAzureCredential có thể dùng Managed Identity khi chạy trên Azure; refresh PropertySource không tự tái tạo singleton DataSource; GCP payload nằm trong version; pin version giúp rollout/rollback có kiểm soát; Secret Accessor cho phép đọc payload; Pub/Sub chỉ thông báo, subscriber thực hiện rotation; @RefreshScope phù hợp bean có thể tái tạo; Hikari cần drain/recreate; overlap giúp rollback; chỉ revoke credential cũ sau khi mọi consumer chuyển; event cần idempotency; log chỉ ghi metadata; xác minh version/deployment/metric; nếu credential cũ đã revoke phải tạo credential phục hồi rồi đồng bộ secret.

## 17. Tài liệu tham khảo chính thức

### Spring Boot

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data API, PropertySource, config import, config tree và property precedence.
- [Spring Cloud Context Refresh](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): RefreshScope và refresh lifecycle.

### AWS

- [Spring Cloud AWS 4.1.1 – Secrets Manager Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): starter, config import, JSON secret, reload strategy và IAM permission.
- [Spring Cloud AWS 4.1.1 – Parameter Store Integration](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): config import, prefix, SSM client, reload và IAM permission.
- [AWS Secrets Manager – Secret Versions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/whats-in-a-secret.html): version và staging labels.
- [AWS Secrets Manager – Lambda Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): createSecret, setSecret, testSecret và finishSecret.
- [AWS Secrets Manager – Rotation Strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html): single-user và alternating-user strategy.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html): parameter hierarchy, SecureString và KMS.

### Azure

- [Spring Cloud Azure – Secret Management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): KeyVaultPropertySource, secret-keys, property mapping và refresh interval.
- [Spring Cloud Azure – Authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication): DefaultAzureCredential, Managed Identity và Workload Identity.
- [Azure Key Vault RBAC Guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): Key Vault Secrets User, Secrets Officer và control/data plane.
- [Azure Key Vault Secret Rotation Tutorial](https://learn.microsoft.com/en-us/azure/key-vault/secrets/tutorial-rotation): Event Grid và Function rotation workflow.
- [Azure Key Vault Event Grid Schema](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-key-vault): SecretNewVersionCreated và SecretNearExpiry events.
- [Spring Cloud Azure Version Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): Spring Boot, Spring Cloud và Spring Cloud Azure compatibility.

### Google Cloud

- [Spring Framework on Google Cloud 8.2.4 – Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.4/reference/html/index.html): starter, Config Data resource, SecretManagerTemplate và refresh.
- [Google Cloud Secret Manager – Access a Secret Version](https://docs.cloud.google.com/secret-manager/docs/access-secret-version): version ID, latest và Secret Accessor role.
- [Google Cloud Secret Manager – IAM Access Control](https://docs.cloud.google.com/secret-manager/docs/access-control): Secret Accessor, Secret Version Adder và Secret Version Manager.
- [Google Cloud Secret Manager – Rotation Schedules](https://docs.cloud.google.com/secret-manager/docs/secret-rotation): Pub/Sub notification và rotation schedule.
- [Google Cloud Secret Manager – Rotation Recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations): gradual rollout, version pinning, rollback và idempotency.
- [Google Cloud Secret Manager – Best Practices](https://docs.cloud.google.com/secret-manager/docs/best-practices): version pinning, disable trước khi destroy và rotation.

**Ghi nhớ:** Secret manager bảo vệ payload và quản lý version; workload identity cấp quyền đọc; Spring Config Data đưa giá trị vào Environment; refresh chỉ cập nhật những bean hỗ trợ; rotation phải cập nhật cả hệ thống đích lẫn ứng dụng. Với database credential và client giữ connection, hãy rollout có overlap, kiểm tra canary, tái tạo pool/client, giữ đường rollback và chỉ thu hồi credential cũ sau khi mọi consumer đã chuyển sang version mới.
