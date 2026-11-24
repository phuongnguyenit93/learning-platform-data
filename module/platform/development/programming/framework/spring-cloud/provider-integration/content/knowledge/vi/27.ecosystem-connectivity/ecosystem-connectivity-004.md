# Ranh giới giữa cấu hình nhà cung cấp và Spring Cloud Config

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud, SDK và connector tương ứng. Để các kết nối đó hoạt động an toàn ở local, test, staging và production, ứng dụng cần nhiều loại cấu hình: Region, endpoint, queue/topic, bucket/container, database URL, timeout, retry policy, feature flag, client ID và secret.

Những giá trị này thường bị đặt chung trong một file YAML. Cách làm đó khiến ranh giới giữa **cấu hình ứng dụng**, **cấu hình kết nối nhà cung cấp** và **bí mật (secret)** trở nên mờ. Một endpoint không nhạy cảm có thể được quản lý như cấu hình thường; password, private key và token cần secret store, quyền truy cập riêng, audit và rotation. Một số cấu hình cần thay đổi động mà không restart; một số chỉ được đọc lúc khởi động và cần rollout để áp dụng.

**Spring Boot ConfigData** cung cấp cơ chế nạp cấu hình từ nhiều nguồn theo thứ tự và profile. **Spring Cloud Config** bổ sung mô hình server/client để tập trung cấu hình ứng dụng, thường dùng Git hoặc backend khác làm nguồn. Các dịch vụ cloud-native như AWS Systems Manager Parameter Store, AWS AppConfig, AWS Secrets Manager, Azure App Configuration, Azure Key Vault và Google Secret Manager cung cấp khả năng lưu, phân phối hoặc quản lý cấu hình/secret theo cách riêng của từng nhà cung cấp.

Các cơ chế này có thể phối hợp, nhưng không thay thế nhau hoàn toàn. Spring Cloud Config không tự động trở thành adapter cho mọi cloud parameter store. Một provider secret manager không phải kho cấu hình ứng dụng đầy đủ. Việc chọn nguồn phải dựa trên lifecycle, độ nhạy, tốc độ thay đổi, identity, audit và cách ứng dụng nhận cập nhật.

Sau bài học, bạn có thể:

1. Phân biệt application config, provider connection config, feature flag và secret.
2. Hiểu Spring Boot ConfigData, profile, import và property precedence.
3. Thiết kế Spring Cloud Config Server/Client và backend phù hợp.
4. Phân biệt Config Server tập trung với dịch vụ cấu hình/secret native của cloud.
5. Chọn AWS Parameter Store, AppConfig, Secrets Manager, Azure App Configuration/Key Vault hoặc Google Secret Manager đúng mục đích.
6. Cấu hình workload identity và quyền đọc theo least privilege.
7. Thiết kế refresh, rotation, fail-fast, fallback và xử lý khi config source outage.
8. Kiểm thử cấu hình theo môi trường mà không đưa secret thật vào test.
9. Vận hành cấu hình bằng audit, versioning, validation, monitoring và rollback.

> **Phạm vi:** Bài tập trung vào ranh giới kiến trúc và cách tích hợp Spring. Tên starter, ConfigData import prefix và property cụ thể phụ thuộc phiên bản Spring Boot, Spring Cloud và provider integration. Hãy dùng release train tương thích và xác minh tài liệu đúng phiên bản trước khi triển khai.

## 2. Phân loại cấu hình trước khi chọn nguồn

### 2.1. Bốn nhóm dữ liệu khác nhau

| Nhóm | Ví dụ | Đặc tính | Nguồn thường phù hợp |
| --- | --- | --- | --- |
| Application config | Feature mode, business limit, page size, timeout nghiệp vụ | Không nhất thiết gắn với cloud; có thể cần profile/refresh | Config Server, Git, environment, ConfigMap, App Configuration |
| Provider connection config | AWS Region, S3 bucket, queue URL, Azure endpoint, Pub/Sub topic | Gắn với deployment/provider; thường thay đổi cùng hạ tầng | Environment, deployment config, Parameter Store/App Configuration |
| Secret | Password, client secret, API token, private key, DB credential | Nhạy cảm, cần access control, audit, rotation | Secrets Manager, Key Vault, Secret Manager, Vault |
| Dynamic operational config | Feature flag, rollout percentage, kill switch, routing rule | Có thể thay đổi nhanh khi app đang chạy | AWS AppConfig, Azure App Configuration, feature flag service |

Không phải mọi giá trị trong nhóm provider connection config đều là secret. Ví dụ Region, bucket name và endpoint thường không phải credential, nhưng vẫn có thể tiết lộ topology và cần quyền xem phù hợp. Ngược lại, connection string có thể chứa password; cần tách secret khỏi phần endpoint nếu có thể.

### 2.2. Một ví dụ phân loại

Giả sử service upload tài liệu lên S3, gửi thông báo qua queue và kết nối database:

~~~yaml
app:
  documents:
    bucket: rental-documents-prod
    max-upload-size: 20MB
  notifications:
    queue-name: reservation-notifications
  processing:
    retry-limit: 4

spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/rental
    username: rental_app
    password: value-from-secret-store

aws:
  region: ap-southeast-1
~~~

Trong ví dụ:

- Bucket, queue, Region và retry limit là cấu hình deployment/application, không cần nhúng access key.
- Database URL và username thường là connection config; password là secret.
- Nếu bucket/queue thay đổi theo môi trường, quản lý bằng environment hoặc config source phù hợp.
- Nếu retry limit là policy nghiệp vụ thay đổi theo rollout, có thể đưa vào dynamic config, nhưng phải có validation và giới hạn an toàn.

Không ghi chuỗi giả như `value-from-secret-store` vào production. Ví dụ chỉ minh họa ranh giới; integration phải thực sự resolve secret từ nguồn được cấp quyền.

### 2.3. Cấu hình phải có owner và lifecycle

Mỗi key nên có owner, nguồn authoritative và thời điểm áp dụng:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Owner | Team nào được phép thay đổi? |
| Source of truth | Git, IaC, Config Server hay provider store? |
| Scope | Toàn hệ thống, environment, service, tenant hay instance? |
| Lifecycle | Đọc lúc startup, refresh định kỳ hay push event? |
| Validation | Kiểm tra kiểu, range và quan hệ giữa các key ở đâu? |
| Sensitivity | Có phải secret hoặc dữ liệu topology hạn chế không? |
| Rollback | Khôi phục version trước bằng cách nào? |
| Audit | Ai thay đổi, khi nào, lý do gì? |

Tránh để cùng một key được quản lý đồng thời ở Git, environment, Config Server và provider store mà không có precedence rõ. Khi xảy ra sự cố, team cần biết giá trị cuối cùng đến từ nguồn nào.

## 3. Spring Boot ConfigData và property resolution

### 3.1. Spring Boot nạp cấu hình từ nhiều nguồn

Spring Boot có thể nạp cấu hình từ:

- File `application.properties` hoặc `application.yaml`.
- File profile-specific như `application-prod.yaml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config tree, mounted secret/config files.
- Nguồn ngoài được tích hợp qua ConfigData loader như Spring Cloud Config hoặc provider integration.

Các nguồn được tổ chức thành Environment/PropertySource. Một key có thể xuất hiện ở nhiều nơi; giá trị được chọn theo precedence của property source và thứ tự import. Không nên đoán giá trị cuối chỉ bằng cách nhìn một file YAML.

### 3.2. Profile và profile-specific config

Ví dụ:

~~~yaml
# application.yaml
app:
  storage:
    provider: s3
    connect-timeout: 2s
    read-timeout: 30s
~~~

~~~yaml
# application-local.yaml
app:
  storage:
    endpoint: http://localhost:4566
    bucket: local-documents
~~~

~~~yaml
# application-prod.yaml
app:
  storage:
    bucket: rental-documents-prod
~~~

Kích hoạt profile bằng environment hoặc command line:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Profile chỉ chọn cấu hình phù hợp; nó không phải ranh giới bảo mật. Không đưa production secret vào file profile rồi commit Git. Cũng không nên tạo profile cho từng tenant nếu tenant là dữ liệu runtime có số lượng lớn; dùng tenant-aware configuration/service phù hợp hơn.

### 3.3. ConfigData import

Từ Spring Boot 2.4, ConfigData API là cơ chế chuẩn để import nguồn cấu hình ngoài. Spring Cloud Config Client hiện đại thường được kích hoạt qua:

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import: configserver:http://config-server.internal:8888
~~~

Dùng `optional:configserver:` khi ứng dụng được phép khởi động mà không có Config Server. Bỏ `optional:` khi cấu hình remote là bắt buộc và khởi động thiếu config có thể gây lỗi vận hành hoặc bảo mật.

Ví dụ:

~~~yaml
spring:
  config:
    import: optional:configserver:
~~~

Khi dùng import không chỉ định URL, client có thể lấy URI từ `spring.cloud.config.uri` hoặc cơ chế discovery tương ứng. Cấu hình chi tiết phụ thuộc phiên bản client và deployment.

Không nhầm ConfigData import với legacy bootstrap context. Các dự án Spring Cloud cũ có thể dùng `bootstrap.yml`/bootstrap starter; dự án hiện đại nên theo hướng dẫn release train đang sử dụng. Tránh bật đồng thời hai cơ chế mà không hiểu thứ tự nạp.

### 3.4. Property precedence và override

Spring Boot có thứ tự precedence giữa command line, system properties, environment, config data và các nguồn khác. Các profile document và ConfigData import cũng có quy tắc xử lý riêng. Spring Cloud Config còn có thuộc tính điều khiển remote property source có thể bị local property override hay không.

Nguyên tắc vận hành:

1. Chọn một source of truth cho mỗi nhóm key.
2. Ghi rõ key nào được phép override bằng environment/command line.
3. Không cho secret mặc định trong file bị vô tình ghi đè bằng giá trị rỗng.
4. Không giả định `application-prod.yaml` luôn thắng remote config; kiểm tra Environment thực tế của phiên bản đang dùng.
5. Khi cần chẩn đoán, dùng `/actuator/env` hoặc `/actuator/configprops` trong môi trường được bảo vệ và không công khai endpoint này.

Đặc biệt, các flag như `spring.cloud.config.allowOverride`, `overrideNone` hoặc `overrideSystemProperties` có semantics phụ thuộc client/server release. Chỉ cấu hình khi đã đọc đúng tài liệu phiên bản và có test chứng minh nguồn nào thắng.

### 3.5. Bind cấu hình vào type an toàn

Ưu tiên `@ConfigurationProperties` cho nhóm cấu hình có cấu trúc thay vì rải `@Value`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @NotBlank String provider,
        @NotBlank String bucket,
        @Positive int maxUploadBytes,
        Duration readTimeout) {
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Có thể thêm validation range, allow-list provider và kiểm tra chéo cấu hình. Với record/immutable object, việc thay đổi cấu hình runtime cần cân nhắc cách bean được tạo lại; không giả định mọi `@ConfigurationProperties` bean tự refresh.

## 4. Spring Cloud Config: tập trung cấu hình ứng dụng

### 4.1. Config Server giải quyết bài toán gì?

Spring Cloud Config Server cung cấp HTTP API để client lấy cấu hình theo application name, profile và label. Ví dụ client có thể yêu cầu cấu hình cho `reservation-service`, profile `prod`, label `main`.

Các khái niệm:

- **Application name:** định danh service, thường lấy từ `spring.application.name`.
- **Profile:** môi trường/biến thể như `dev`, `staging`, `prod`.
- **Label:** nhánh, tag hoặc version backend; với Git thường là branch/tag/commit.
- **Repository/backend:** nguồn cấu hình, ví dụ Git repository, filesystem native hoặc Vault.
- **Config Client:** tải property sources và đưa vào Spring Environment.

Config Server có thể cung cấp cùng một cấu hình cho nhiều instance và service. Git backend giúp review bằng pull request, version history và rollback commit. Vault backend có thể phục vụ secret theo cơ chế lease/policy phù hợp. Backend native/file system hữu ích cho một số môi trường nhưng cần quản lý quyền và HA.

### 4.2. Dependency và server setup

Server cần dependency Config Server và annotation enable:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
~~~

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Quản lý version bằng Spring Cloud BOM tương thích với Spring Boot. Không lấy version mới nhất của Config Server độc lập với release train của ứng dụng.

### 4.3. Git-backed configuration

Ví dụ server cấu hình Git repository:

~~~yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.org/platform/application-config.git
          default-label: main
          clone-on-start: true
~~~

Trong repository, file có thể đặt theo convention:

~~~text
application.yaml
application-prod.yaml
reservation-service.yaml
reservation-service-prod.yaml
~~~

Config Server kết hợp application name/profile/label để chọn property source. Không đặt private key Git hoặc token truy cập repository trực tiếp trong file được commit. Dùng deploy key/token qua secret injection, TLS và quyền read-only tối thiểu.

### 4.4. Client setup

Dependency client:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Client:

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import: configserver:http://config-server.internal:8888
  cloud:
    config:
      label: main
      profile: prod
~~~

Profile thường được suy ra từ active profiles của Spring Boot; `spring.cloud.config.profile` và `label` có thể điều khiển request cụ thể. Tránh khai báo profile mâu thuẫn ở nhiều nơi.

### 4.5. Config Server không phải provider parameter store

Config Server là server phân phối property sources. Nó có thể đọc từ Git, Vault hoặc backend được hỗ trợ; bản thân nó không tự động đọc AWS Parameter Store, Azure App Configuration hoặc Google Secret Manager chỉ vì ứng dụng chạy trên cloud đó.

Có thể triển khai Config Server trên ECS/EKS, Azure Container Apps/AKS hoặc Cloud Run/GKE. Vị trí triển khai không quyết định backend. Ví dụ Config Server chạy trên AWS vẫn có thể đọc Git; ứng dụng chạy trên GCP vẫn có thể dùng Config Server tập trung.

Nếu dùng provider store làm nguồn, cần integration cụ thể hoặc backend/custom adapter tương thích. Không coi URL Config Server và URI Secret Manager là cùng một loại import.

### 4.6. Khi nào Config Server có giá trị?

Chọn Spring Cloud Config khi:

- Nhiều service cần cấu hình được quản lý tập trung theo app/profile/label.
- Cần Git review, versioning, rollback và audit thay đổi.
- Muốn cùng một cơ chế phân phối cấu hình cho nhiều cloud.
- Có thể vận hành Config Server HA, bảo mật và kiểm soát quyền truy cập.
- Cần tách lifecycle cấu hình khỏi release ứng dụng.

Không nhất thiết triển khai Config Server cho một service nhỏ chỉ có vài environment variables. Thêm server đồng nghĩa thêm dependency runtime, network, authentication, availability và vận hành.
## 5. AWS: Parameter Store, AppConfig và Secrets Manager

### 5.1. Chọn dịch vụ theo mục đích

AWS có nhiều dịch vụ liên quan đến cấu hình nhưng lifecycle khác nhau:

| Dịch vụ | Dùng cho | Không nên nhầm với |
| --- | --- | --- |
| Systems Manager Parameter Store | Hierarchical parameters, String/SecureString, config theo path/environment | Feature flag rollout chuyên dụng |
| AWS AppConfig | Dynamic configuration, feature flags, gradual deployment, validation và rollback | Kho password/key tổng quát |
| AWS Secrets Manager | Password, API token, database credential, secret rotation | Kho config không nhạy cảm cho mọi key |
| Environment/Task definition | Giá trị gắn với deployment như Region, endpoint, resource name | Nơi lưu secret dài hạn không có rotation |

Parameter Store phù hợp với tham số cấu hình phân cấp, có thể dùng SecureString khi cần mã hóa. AppConfig phù hợp với cấu hình cần rollout có kiểm soát và theo dõi deployment. Secrets Manager phù hợp với secret có lifecycle, version và rotation.

### 5.2. Parameter Store với Spring Cloud AWS

AWSpring cung cấp integration Parameter Store theo release. Với phiên bản hỗ trợ ConfigData, dependency thường là:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
</dependency>
~~~

Ví dụ import một path:

~~~yaml
spring:
  config:
    import: aws-parameterstore:/config/reservation-service/
~~~

Các parameter trong path được đưa vào Environment theo quy tắc của integration. Prefix, context, profile resolution, optional import và property mapping phụ thuộc phiên bản AWSpring. Kiểm tra tài liệu version đang dùng trước khi chọn path convention; không giả định mọi version có cùng cách resolve profile.

Workload identity cần quyền đọc đúng path, ví dụ quyền SSM GetParametersByPath/GetParameter và quyền KMS decrypt nếu SecureString dùng customer-managed key. Không cấp quyền đọc toàn bộ Parameter Store nếu service chỉ cần một path.

### 5.3. Secrets Manager với Spring Cloud AWS

Secret có thể được import bằng integration Secrets Manager:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
</dependency>
~~~

Ví dụ ConfigData import:

~~~yaml
spring:
  config:
    import: aws-secretsmanager:/reservation-service/database
~~~

Tên secret, prefix import và cách flatten JSON secret thành property phụ thuộc AWSpring release. Nếu secret chứa JSON gồm username/password, xác minh mapping property name trước khi bind. Không in object secret ra log khi debug.

Quyền runtime nên giới hạn vào secret ARN cụ thể, cùng kms:Decrypt nếu customer-managed KMS key yêu cầu. Secret rotation có thể cập nhật version tại Secrets Manager nhưng ứng dụng không nhất thiết tự nhận giá trị mới ngay; cần cơ chế refresh/reconnect rõ ràng.

### 5.4. AWS AppConfig cho dynamic configuration

AppConfig phù hợp với feature flag và operational config cần rollout:

- Có thể validate configuration trước khi deploy.
- Có thể triển khai theo strategy/percentage và theo dõi alarm.
- Có thể rollback deployment khi alarm kích hoạt.
- Có thể dùng AppConfig Agent làm local endpoint/cache cho ứng dụng.
- Ứng dụng lấy configuration profile qua AppConfigData API hoặc agent.

AppConfig không nên bị xem như một PropertySource tự refresh của Spring nếu integration cụ thể chưa cung cấp hành vi đó. Có thể viết adapter đọc từ AppConfigData/agent và publish thay đổi vào application-level configuration service. Phải xác định polling interval, cache TTL, token/session lifecycle và behavior khi agent/API unavailable.

Không đưa password/private key vào feature flag document chỉ vì AppConfig có thể lưu JSON. Secret vẫn nên ở Secrets Manager hoặc secret store có quyền và rotation phù hợp.

### 5.5. Cấu hình AWS identity

Trong production, ưu tiên role gắn với workload:

- ECS task role cho task.
- EKS Pod Identity hoặc IRSA cho Kubernetes workload.
- EC2 instance profile cho ứng dụng trên EC2.
- Local developer profile chỉ dùng ở máy phát triển.

AWS SDK credential provider chain giúp lấy credential từ môi trường runtime và refresh theo cơ chế provider. Không khai báo access key/secret key trong application.yaml. Region có thể được truyền qua deployment config; Region không phải credential.

### 5.6. Một mô hình kết hợp AWS

~~~yaml
spring:
  application:
    name: reservation-service
  config:
    import:
      - aws-parameterstore:/config/reservation-service/
      - aws-secretsmanager:/reservation-service/database
~~~

Ví dụ trên chỉ dùng khi AWSpring version của dự án hỗ trợ hai ConfigData loader và import syntax tương ứng. Tách path parameter không nhạy cảm khỏi secret; không dùng cùng một role có quyền đọc toàn bộ secret account nếu không cần.

## 6. Azure: App Configuration và Key Vault

### 6.1. Phân vai dịch vụ

| Dịch vụ | Dùng cho | Đặc điểm |
| --- | --- | --- |
| Azure App Configuration | Application settings, labels, feature flags và dynamic refresh | Quản lý cấu hình tập trung, key/label filter và refresh |
| Azure Key Vault | Secrets, keys và certificates | Access policy/RBAC, version, audit và rotation |
| Environment/Container App settings | Deployment-specific settings | Gắn với môi trường chạy, phù hợp endpoint/resource reference |

App Configuration hỗ trợ Key Vault references để một setting trỏ tới secret trong Key Vault. Ứng dụng cần identity có quyền đọc setting trong App Configuration và quyền resolve secret trong Key Vault. Quyền ở hai dịch vụ là hai boundary riêng.

### 6.2. App Configuration integration

Spring Cloud Azure cung cấp starter/integration cho App Configuration theo release. Dependency thường có dạng:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-appconfiguration-config</artifactId>
</dependency>
~~~

Ví dụ khai báo endpoint store:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: https://reservation-config.azconfig.io
            selects:
              - key-filter: "*"
                label-filter: prod
~~~

Đây là cấu trúc minh họa; kiểm tra đúng schema/property name theo phiên bản Spring Cloud Azure. Label có thể phân tách environment hoặc deployment ring. Không dùng label để thay thế authorization: quyền đọc store được quyết định bởi identity/RBAC.

App Configuration hỗ trợ refresh có điều kiện theo sentinel key hoặc refresh strategy của integration. Chỉ những bean/config consumer được thiết kế để nhận cập nhật mới thay đổi an toàn. Với thay đổi ảnh hưởng connection pool, credential hoặc cấu trúc bean, có thể cần recreate resource hoặc restart deployment.

### 6.3. Key Vault references và secret

Có thể lưu reference tới Key Vault trong App Configuration thay vì lưu secret value trực tiếp. Ứng dụng dùng Managed Identity/Workload Identity để đọc App Configuration và resolve Key Vault secret.

Nếu dùng Key Vault Secrets starter trực tiếp, dependency và property source/ConfigData support phụ thuộc release. Không tự giả định prefix import giống AWS hoặc Google. Xác minh tài liệu của Spring Cloud Azure đang dùng để chọn cách resolve secret, endpoint và credential provider.

Key Vault role nên cấp quyền đọc secret cần thiết, không cấp quyền quản lý key/vault nếu workload chỉ đọc. Secret versioning cho phép kiểm soát version; rotation cần phối hợp với ứng dụng và downstream service.

### 6.4. Azure identity

Ưu tiên Managed Identity cho Azure-hosted workload hoặc Workload Identity khi chạy Kubernetes. DefaultAzureCredential hỗ trợ lựa chọn credential theo môi trường nhưng cần cấu hình rõ trong production để tránh vô tình fallback sang credential developer. Tách identity cho App Configuration và Key Vault nếu cần quyền khác nhau.

### 6.5. Dynamic refresh và feature flags

Azure App Configuration có thể refresh key-value và feature flag theo policy. Cần đặt refresh interval phù hợp với độ trễ chấp nhận được và request cost. Không poll mọi key quá thường xuyên. Dùng sentinel key để chỉ trigger refresh khi một nhóm cấu hình đã được cập nhật đồng bộ.

Feature flag cần có default an toàn, owner, expiry date và kế hoạch xóa sau rollout. Không dùng feature flag làm cơ chế authorization; quyền truy cập phải được kiểm tra độc lập.

## 7. Google Cloud: Secret Manager và nguồn cấu hình ứng dụng

### 7.1. Secret Manager không phải general configuration service

Google Cloud Secret Manager lưu secret version, IAM policy, replication và audit. Nó phù hợp với password, token, certificate/private key và các giá trị nhạy cảm. Không nên dùng secret manager cho mọi key không nhạy cảm như page size, retry count hay tên queue chỉ vì có sẵn API.

Google Cloud không có một dịch vụ general-purpose application configuration tương đương hoàn toàn với AWS AppConfig hoặc Azure App Configuration trong mọi use case. Các lựa chọn phổ biến:

- Environment variables hoặc deployment configuration cho giá trị gắn với Cloud Run/GKE/Compute Engine.
- ConfigMap cho cấu hình không nhạy cảm trong GKE.
- Git-backed Spring Cloud Config khi cần review/versioning tập trung.
- Secret Manager cho secret và credential.
- Custom application config service nếu cần dynamic refresh/feature flag chuyên dụng.

### 7.2. Spring Cloud GCP Secret Manager integration

Spring Cloud GCP có integration Secret Manager theo release. Dependency thường có dạng:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-secretmanager</artifactId>
</dependency>
~~~

Ví dụ bật Secret Manager ConfigData integration:

~~~yaml
spring:
  config:
    import: sm://
~~~

Có thể tham chiếu secret theo prefix của integration trong property/config phù hợp. Ví dụ minh họa:

~~~yaml
spring:
  datasource:
    password: sm://reservation-db-password
~~~

Tên starter, import prefix, cách chọn project và secret version phụ thuộc phiên bản Spring Cloud GCP. Xác minh đúng reference trước khi áp dụng; không giả định `sm://` là scheme chung của Spring Boot ngoài integration này.

### 7.3. Workload Identity trên GCP

Trong GKE, ưu tiên Workload Identity Federation for GKE để Kubernetes service account ánh xạ tới Google service account hoặc principal được cấp quyền. Với Cloud Run, dùng service identity của service. Trên môi trường local, dùng Application Default Credentials cho developer account theo policy.

Cấp quyền Secret Manager Secret Accessor ở cấp secret cụ thể nếu có thể. Không cấp project-wide secret access nếu workload chỉ cần một vài secret. Secret Manager API access và quyền truy cập dữ liệu ứng dụng là hai lớp riêng.

### 7.4. Version, alias và rotation

Secret Manager có secret version và trạng thái enabled/disabled/destroyed. Dùng alias/version selection theo policy; không hard-code version cũ nếu cần rotation. Tuy nhiên, chuyển sang latest version không tự làm object đang chạy thay đổi. Ứng dụng phải đọc lại secret, refresh credential hoặc restart connection pool phù hợp.

Với database password rotation, cần phối hợp hai pha: cập nhật credential ở database/provider, sau đó cập nhật secret và làm mới connection pool. Đảm bảo có overlap window hoặc cơ chế rollback để tránh toàn bộ instance mất khả năng kết nối.

## 8. So sánh các lựa chọn theo provider

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Config tập trung không nhạy cảm | Parameter Store, AppConfig, Spring Cloud Config | App Configuration, Spring Cloud Config | Git/Config Server, deployment env, GKE ConfigMap |
| Dynamic feature flag | AppConfig | App Configuration Feature Management | Feature flag service hoặc application solution |
| Secret | Secrets Manager, Parameter Store SecureString | Key Vault | Secret Manager |
| Secret reference từ config store | AppConfig integration/custom resolution tùy thiết kế | Key Vault reference trong App Configuration | Secret Manager integration |
| Workload identity | IAM role | Managed Identity/Workload Identity | Workload Identity/Cloud Run service identity |
| Refresh | AppConfig polling/agent hoặc integration-specific | App Configuration refresh | Integration-specific Secret Manager refresh; app config cần giải pháp riêng |

Không chọn chỉ dựa trên danh sách feature. Cần xem service đang chạy ở đâu, team vận hành cloud nào, latency/network boundary, IAM model, audit requirement, refresh behavior, quota và chi phí. Một Config Server đa cloud có thể giúp chuẩn hóa application config; secret thường vẫn nên nằm trong secret manager của môi trường triển khai hoặc một vault được quản lý tập trung.
## 9. Refresh, rotation và runtime lifecycle

### 9.1. Nạp lúc startup khác với refresh runtime

Một ConfigData loader thường đọc nguồn cấu hình trong quá trình bootstrap/startup. Sau khi application context được tạo, thay đổi tại nguồn không tự động làm mọi bean thay đổi. Phải xác định rõ từng key thuộc loại nào:

- **Startup-only:** Region, endpoint, pool size, TLS truststore hoặc topology cần recreate client. Thường áp dụng khi restart/rollout.
- **Refreshable:** feature mode, ngưỡng nghiệp vụ hoặc routing rule được thiết kế để đọc lại an toàn.
- **Secret rotation:** password/token cần được tải lại và cập nhật client/connection pool theo quy trình.
- **Deployment config:** thay đổi thông qua rollout workload, không nhất thiết refresh tại chỗ.

Không hứa hẹn "dynamic config" chỉ vì nguồn hỗ trợ cập nhật giá trị. Ứng dụng phải có cơ chế nhận thay đổi, validate, publish và áp dụng cho component đang chạy.

### 9.2. Spring Cloud Config refresh

Spring Cloud Config có thể phối hợp Spring Boot Actuator và Spring Cloud Bus để phát sự kiện refresh tới nhiều instance. Một số ứng dụng dùng endpoint refresh để yêu cầu context cập nhật các bean được hỗ trợ.

Ví dụ dependency Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Một bean có thể được đánh dấu refresh scope:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@RefreshScope
@Component
public class NotificationPolicy {

    private final NotificationProperties properties;

    public NotificationPolicy(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean shouldSend(String eventType) {
        return properties.enabledEventTypes().contains(eventType);
    }
}
~~~

Ví dụ này minh họa bean có thể được tạo lại trong refresh scope; việc inject và bind properties cần được thiết kế nhất quán. Không đánh dấu mọi bean `@RefreshScope` một cách đại trà. Các client giữ connection, thread, executor hoặc resource native có thể cần close/recreate rõ ràng.

Endpoint refresh và bus endpoint là bề mặt quản trị nhạy cảm. Chỉ expose trong network/management plane được bảo vệ, bật authentication/authorization, audit và giới hạn quyền gọi. Không expose toàn bộ Actuator trên public internet.

### 9.3. Refresh an toàn bằng version và validation

Một quy trình refresh nên:

1. Tải version mới từ config source.
2. Parse và bind vào typed configuration.
3. Validate range, enum, cross-field constraints và allow-list.
4. Kiểm tra dependency có thể áp dụng cấu hình mới không.
5. Chuyển đổi atomically sang snapshot mới.
6. Ghi nhận version, thời điểm và kết quả refresh.
7. Nếu validation/apply thất bại, tiếp tục dùng snapshot hợp lệ gần nhất và phát cảnh báo.

Với cấu hình có nhiều key liên quan, tránh để ứng dụng quan sát trạng thái nửa cũ nửa mới. Dùng version/revision hoặc document tổng hợp để cập nhật nguyên tử. Feature flag có thể có default safe; routing/security policy không nên fallback về trạng thái cho phép rộng hơn.

### 9.4. Secret rotation không chỉ là đọc giá trị mới

Khi password database đổi, pool connection hiện tại có thể vẫn giữ connection được xác thực bằng credential cũ. Việc cập nhật property không tự làm pool reconnect. Thiết kế cần trả lời:

- Secret version mới được phát hiện bằng polling, event hay restart?
- Credential mới có overlap với credential cũ không?
- Pool tạo connection mới bằng credential nào?
- Connection cũ được drain/close ra sao?
- Nếu rotation một phần thất bại, có rollback secret/database không?
- Token client có cơ chế refresh trước expiry không?

Với OAuth/client credentials, dùng token provider hỗ trợ refresh; không cache access token vô thời hạn. Với database, ưu tiên cơ chế rotation do provider hỗ trợ và pool có thể cập nhật credential/recreate. Không log secret khi rotation lỗi.

### 9.5. Không dùng config refresh thay cho deployment

Thay đổi Region, endpoint, TLS trust, network path, encryption key hoặc topology có thể yêu cầu restart/rollout. Thay đổi số connection pool hoặc SDK client cũng cần đánh giá resource lifecycle. Refresh chỉ phù hợp khi code được thiết kế để đọc và áp dụng giá trị mới một cách an toàn.

## 10. Fail-fast, fallback và xử lý outage

### 10.1. Chọn optional hay required

Config Server Client hỗ trợ chế độ fail-fast/retry theo phiên bản. ConfigData import có thể dùng prefix optional. Quyết định phụ thuộc loại config:

| Trường hợp | Hành vi thường phù hợp |
| --- | --- |
| Config Server bắt buộc để xác định database/queue production | Fail startup nếu không lấy được config |
| Config bổ sung không ảnh hưởng an toàn, có default hợp lệ | Có thể optional |
| Secret cần để kết nối database hoặc ký token | Fail startup/operation; không dùng secret giả hoặc rỗng |
| Feature flag không critical | Dùng default safe đã được phê duyệt |
| Dynamic config source tạm outage | Giữ snapshot hợp lệ gần nhất, cảnh báo và retry có giới hạn |

Optional không có nghĩa là an toàn. Nếu thiếu remote property khiến app dùng endpoint mặc định hoặc secret rỗng, application có thể khởi động nhưng fail muộn hoặc kết nối nhầm resource.

### 10.2. Retry Config Client

Config Client có thể cấu hình retry khi Config Server tạm thời không sẵn sàng. Tùy release, retry cần dependency hỗ trợ và property cho attempts, initial interval, multiplier và max interval. Tổng thời gian retry phải phù hợp startup deadline/orchestrator health check.

Ví dụ minh họa policy bounded retry:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 6
        initial-interval: 1000
        max-interval: 2000
        multiplier: 1.1
~~~

Tên property và dependency hỗ trợ retry phụ thuộc Config Client release; một số phiên bản cần Spring Retry/AOP và cách khai báo retry khác khi dùng ConfigData import. Không sao chép snippet mà chưa xác minh với release train của dự án.

Không retry vô hạn. Nếu Config Server mất kết nối lâu, rollout có thể treo và làm cạn capacity. Dùng timeout, bounded retry, alert và quy trình phục hồi. Không chuyển sang config dev/local như fallback cho production.

### 10.3. Cache và last-known-good

Với dynamic configuration, có thể giữ snapshot hợp lệ gần nhất để tiếp tục hoạt động khi source tạm unavailable. Snapshot phải:

- Được xác thực nguồn và version.
- Được lưu theo policy bảo mật nếu chứa secret.
- Có giới hạn tuổi tối đa và cảnh báo khi quá cũ.
- Không chứa cấu hình cho phép rộng hơn khi thiếu dữ liệu.
- Có quy trình invalidate/rollback.

Không cache secret trong file plaintext hoặc shared volume không kiểm soát. Nếu dùng local cache của agent, xác minh encryption, permissions và behavior sau restart.

### 10.4. Circuit breaker và dependency isolation

Không để mỗi request nghiệp vụ đều gọi trực tiếp config/secret API. Tải cấu hình lúc startup hoặc qua refresh/cache có kiểm soát. Secret provider outage không nên tạo request storm. Có thể dùng circuit breaker/backoff ở integration layer; tuy nhiên, không dùng stale secret vượt quá security policy hoặc token expiry.

## 11. Bảo vệ cấu hình và secret

### 11.1. Secret không được commit vào Git

Git-backed Config Server thuận tiện cho review và versioning nhưng không nên chứa secret plaintext. Nếu dùng encrypted property hoặc Vault backend, cần quản lý encryption key/lease/token riêng. Một secret đã xóa khỏi file hiện tại vẫn có thể tồn tại trong Git history.

Nguyên tắc:

- Lưu secret trong Secrets Manager, Key Vault, Secret Manager hoặc Vault.
- Lưu reference/identifier trong config repository thay vì secret value.
- Hạn chế quyền đọc secret theo service/environment.
- Không in Environment, binding object hoặc toàn bộ config trong log.
- Không expose Actuator env/configprops công khai.
- Scan repository và CI artifacts để phát hiện credential bị commit.
- Có quy trình rotate/revoke khi secret lộ.

### 11.2. Config Server encryption

Spring Cloud Config hỗ trợ cơ chế encrypt/decrypt property trong một số cấu hình. Giá trị mã hóa có thể được lưu dưới dạng cipher text trong repository và được Config Server giải mã khi trả cho client.

Điều này không tự động thay thế secret manager. Config Server trở thành thành phần nắm encryption capability; key phải được bảo vệ, rotate, backup và audit. Nếu server bị compromise, attacker có thể lấy config đã giải mã hoặc sử dụng endpoint decrypt tùy quyền. Chỉ expose encryption endpoint trong management network có authentication và authorization chặt.

### 11.3. Identity và least privilege

Dùng identity riêng theo service/environment:

- Config Client chỉ được đọc application/profile/label cần thiết.
- Config Server chỉ được đọc repository/backend mà nó quản lý.
- Workload chỉ được đọc secret cụ thể cần thiết.
- Runtime identity không được tạo/xóa secret hoặc thay đổi policy nếu không cần.
- CI/CD identity được phép publish config theo workflow, không dùng chung runtime credential.

Tách role cho dev, staging và production. Không dùng một service account có quyền đọc toàn bộ secrets của mọi service.

### 11.4. TLS và network boundary

Bật TLS giữa client và Config Server/provider API. Với private endpoint, cấu hình DNS, route và firewall/security group/network policy đúng. Kiểm tra certificate hostname, truststore rotation và proxy. Không tắt certificate validation để chữa lỗi kết nối.

### 11.5. Audit và data classification

Mỗi config change cần có actor, timestamp, source revision, environment, reason và approval khi cần. Secret access cần audit riêng; không log secret value. Cấu hình có thể chứa internal hostname, account ID hoặc topology; phân loại dữ liệu trước khi cho phép truy cập qua Config Server/Actuator.
## 12. Kiểm thử cấu hình và provider integration

### 12.1. Unit test typed configuration

Kiểm tra binding và validation với các giá trị test, không dùng secret thật:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class StoragePropertiesTest {

    @Test
    void bindsStorageSettings() {
        var source = new MapConfigurationPropertySource();
        source.put("app.storage.provider", "s3");
        source.put("app.storage.bucket", "test-documents");
        source.put("app.storage.max-upload-bytes", "1048576");
        source.put("app.storage.read-timeout", "10s");

        StorageProperties properties = new Binder(source)
                .bind("app.storage", StorageProperties.class)
                .orElseThrow();

        assertThat(properties.provider()).isEqualTo("s3");
        assertThat(properties.maxUploadBytes()).isEqualTo(1048576);
    }
}
~~~

Ví dụ kiểm tra binder cơ bản. Với validation annotation, khởi tạo validation infrastructure hoặc dùng Spring Boot test context để xác minh invalid value làm startup/test fail đúng như mong đợi.

### 12.2. Test profile và property precedence

Dùng test properties hoặc environment test để xác minh:

- Profile local/staging/prod chọn đúng endpoint/bucket.
- Environment variable override đúng key được cho phép.
- ConfigData import có thứ tự mong muốn.
- Required property thiếu sẽ fail startup.
- Optional source outage không làm app dùng nhầm endpoint production/local.
- Typed config validation bắt được giá trị ngoài range.

Không chỉ assert một property value. Kiểm tra cả nguồn được chọn và behavior khi một nguồn không có key hoặc trả giá trị không hợp lệ.

### 12.3. Test Config Client với Config Server

Có thể chạy Config Server test instance với repository local/test fixture hoặc stub HTTP để kiểm tra client. Xác minh application name, profile, label, property source order và error behavior. Không dùng production Config Server/secret store trong unit test.

Một contract test nên kiểm tra endpoint Config Server trả đúng property source cho một app/profile/label; client bind đúng type; thay đổi label/version được phản ánh theo quy trình refresh/restart đã thiết kế.

### 12.4. Test provider config source

Test integration theo provider:

- **AWS:** local test profile với LocalStack khi integration hỗ trợ; staging kiểm tra IAM role, Parameter Store path, Secrets Manager ARN, KMS và AppConfig session/agent.
- **Azure:** test App Configuration/Key Vault bằng test store hoặc Azure test subscription; xác minh Managed Identity/RBAC và Key Vault reference resolution.
- **Google Cloud:** test Secret Manager client với emulator/mock phù hợp; staging xác minh Workload Identity và secret-level IAM.

Emulator không chứng minh IAM, network boundary, encryption key policy, audit hoặc rotation của cloud thật. Giữ một bộ staging contract test nhỏ, có giới hạn chi phí và resource cleanup.

### 12.5. Không để secret trong test artifact

Dùng synthetic secret và test-only identity. Không ghi giá trị thật vào application-test.yaml, snapshot, assertion message, build log, report hoặc CI environment dump. Nếu cần kiểm tra secret resolution, assert rằng bean nhận được giá trị test đã định trước, không in giá trị ra output.

## 13. Quan sát và vận hành configuration plane

### 13.1. Metric cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Config fetch success/failure | Client có lấy được property source không |
| Config fetch latency | Startup/refresh bị chậm ở nguồn nào |
| Refresh success/failure | Thay đổi có được áp dụng không |
| Current config revision/label | Instance đang dùng phiên bản nào |
| Secret access denied | Identity hoặc policy có vấn đề |
| Secret refresh age | Credential đang dùng đã cũ bao lâu |
| Config validation failure | Giá trị không hợp lệ hoặc schema drift |
| Config source availability | Config Server/provider API có sẵn không |

Không đưa secret value, token hoặc raw configuration vào metric label. Revision, application name và environment nên có cardinality được kiểm soát.

### 13.2. Log và trace an toàn

Log có thể ghi:

- Application name, profile và config source type.
- Config revision/label/version.
- Fetch/refresh duration và kết quả.
- Secret identifier đã mask nếu policy cho phép.
- Error code và correlation ID.

Không log toàn bộ Environment, configuration properties object, secret JSON, connection string hoặc token. Khi cần debug, chỉ in key name và trạng thái resolved/unresolved; bảo vệ Actuator endpoints và management port.

### 13.3. Runbook khi Config Server outage

1. Kiểm tra DNS, TLS, route và health của Config Server.
2. Kiểm tra Git/backend availability và credential của server.
3. Xác định instance mới đang fail startup hay instance cũ vẫn chạy với snapshot hợp lệ.
4. Không thay bằng profile local/dev hoặc secret rỗng.
5. Nếu có last-known-good, xác minh version và tuổi của snapshot.
6. Khôi phục backend/server rồi rollout/refresh theo policy.
7. Kiểm tra tất cả instance đang dùng cùng revision dự kiến.

Config Server là dependency của startup và có thể trở thành điểm lỗi tập trung. Triển khai HA, health checks, connection timeout, cache phù hợp và capacity cho burst khi nhiều instance restart cùng lúc.

### 13.4. Runbook khi secret rotation thất bại

1. Kiểm tra secret version mới và trạng thái enabled.
2. Xác minh workload identity có quyền đọc version mới và decrypt nếu cần.
3. Kiểm tra downstream database/API đã chấp nhận credential mới chưa.
4. Kiểm tra ứng dụng đã refresh token/connection pool chưa.
5. Nếu một phần instance lỗi, dừng rollout và giữ khả năng dùng credential hợp lệ gần nhất theo security policy.
6. Khôi phục/rollback rotation theo runbook của provider.
7. Xác minh không có secret bị log hoặc lưu ở file tạm.

### 13.5. Cost và request rate

Config/secret API có quota và chi phí. Không gọi secret manager cho mỗi HTTP request. Cache secret/config theo lifecycle, dùng agent/refresh interval hợp lý và tránh poll tất cả key liên tục. Secret rotation và config refresh nên có jitter để nhiều replica không đồng thời tạo request burst.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Config Server trả 404 | Sai application name/profile/label hoặc repository layout | Kiểm tra endpoint request và file naming |
| Client không lấy remote config | Thiếu ConfigData import hoặc dùng nhầm bootstrap mechanism | Kiểm tra release train và spring.config.import |
| Giá trị local thắng remote | Property precedence/override policy khác dự kiến | Kiểm tra Environment và override flags đúng version |
| App khởi động khi thiếu secret | Import optional hoặc default rỗng không an toàn | Đánh dấu nguồn required và validate startup |
| AWS Parameter Store AccessDenied | Sai role/path/KMS permission | Kiểm tra task/pod role, path ARN và kms:Decrypt |
| Azure App Configuration không refresh | Sentinel/refresh policy hoặc identity chưa đúng | Kiểm tra key filter, refresh trigger và Managed Identity |
| Key Vault reference không resolve | Thiếu quyền Key Vault hoặc reference sai | Kiểm tra RBAC và endpoint/key reference |
| GCP Secret Manager permission denied | Service identity thiếu accessor trên secret | Kiểm tra Workload Identity và IAM ở cấp secret |
| Secret đổi nhưng connection vẫn lỗi | Bean/pool giữ credential cũ | Refresh/recreate client hoặc rollout |
| Refresh làm cấu hình nửa cũ nửa mới | Nhiều key được cập nhật không nguyên tử | Dùng versioned snapshot và apply atomically |
| Config Server startup chậm | Clone Git, DNS/TLS hoặc backend chậm | Clone-on-start có chủ đích, timeout và health check |
| Secret lộ trong log | Dump Environment/config object hoặc exception | Mask log, hạn chế Actuator và rotate secret |
## 15. Quy trình thiết kế và migration

Khi chuyển từ cấu hình hard-code hoặc file YAML sang external config, làm theo trình tự:

1. Liệt kê key đang dùng và phân loại application config, provider config, feature flag và secret.
2. Xác định owner, source of truth, profile/environment và lifecycle của từng key.
3. Chọn Config Server, provider store hoặc deployment environment theo use case.
4. Thiết kế key naming/path, label, version và secret reference.
5. Tạo workload identity và policy least privilege.
6. Thêm ConfigData/property source integration và typed configuration validation.
7. Test local, integration, outage, refresh và rotation.
8. Triển khai canary/staging, xác minh giá trị resolved và metric.
9. Rollout production; kiểm tra revision trên tất cả instance.
10. Xóa credential/config cũ sau khi xác minh không còn consumer.

Không chuyển tất cả key sang một provider store chỉ vì muốn tập trung. Hãy giữ cấu hình deployment gần deployment system khi phù hợp, application config ở nguồn có review/versioning và secret ở secret manager.

## 16. Checklist trước production

1. **Classification:** mỗi key được phân loại thành application config, provider config, feature flag hoặc secret.
2. **Ownership:** có owner và source of truth; không có key trùng nguồn thiếu precedence.
3. **Compatibility:** Spring Boot, Spring Cloud và provider starter nằm trong release train tương thích.
4. **ConfigData:** import/profile/label và property precedence đã được test.
5. **Validation:** typed properties có type/range/enum và cross-field validation.
6. **Identity:** workload identity riêng theo service/environment, không static credential trong source.
7. **Least privilege:** chỉ đọc đúng app/profile/path/secret cần thiết.
8. **Secret handling:** secret không ở Git, log, metric, header hoặc test artifact.
9. **Refresh:** biết key nào startup-only, refreshable và cần restart.
10. **Rotation:** secret rotation có quy trình update downstream và recreate client/pool.
11. **Resilience:** fail-fast/optional, retry, timeout và last-known-good được quyết định rõ.
12. **Security:** TLS, management endpoint, audit và network boundary được bảo vệ.
13. **Testing:** unit, Config Server contract, provider staging và outage/rotation test.
14. **Operations:** metric, alert, revision visibility và runbook có sẵn.
15. **Rollback:** có thể quay về revision/config hợp lệ mà không khôi phục secret đã bị revoke.

## 17. Bài tập tự luyện

1. Phân loại 15 key của một Spring Boot service thành application config, provider config, feature flag và secret; chỉ ra source of truth cho từng nhóm.
2. Cấu hình Config Server với Git backend và một Config Client dùng ConfigData import; xác minh application name/profile/label.
3. Tạo hai profile local và prod; kiểm tra property precedence giữa YAML, environment và remote config.
4. Bind storage/database properties bằng `@ConfigurationProperties`; thêm validation để startup fail khi bucket hoặc timeout không hợp lệ.
5. Tích hợp AWS Parameter Store cho path cấu hình và Secrets Manager cho database password; cấp role chỉ đọc đúng resource.
6. Dùng AWS AppConfig cho feature flag; thiết kế refresh, cache, default safe và rollback.
7. Tích hợp Azure App Configuration với label theo environment và Key Vault reference; xác minh identity cần quyền ở cả hai service.
8. Dùng Google Secret Manager qua Spring Cloud GCP; phân biệt secret với cấu hình không nhạy cảm từ environment/Config Server.
9. Mô phỏng Config Server outage lúc startup và lúc runtime; xác định fail-fast hay last-known-good.
10. Mô phỏng secret rotation database; chứng minh pool tạo connection bằng credential mới và không log secret.
11. Viết test chứng minh một key đến từ đúng source và override theo policy.
12. Thiết kế runbook khi config revision sai được rollout tới một phần instance.

**Tiêu chí hoàn thành:** người học phân biệt đúng Spring Cloud Config với provider-native configuration/secret service, chọn được nguồn theo lifecycle và sensitivity, cấu hình được client bằng ConfigData, dùng workload identity/least privilege, kiểm soát refresh/rotation/outage và chứng minh behavior bằng test.

## Tài liệu tham khảo

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, profiles, ConfigData và precedence.
- [Spring Cloud Config Reference](https://docs.spring.io/spring-cloud-config/reference/): Config Server, Config Client, backend và encryption.
- [Spring Cloud Config — Client configuration](https://docs.spring.io/spring-cloud-config/reference/client.html): ConfigData import, profile, label và retry.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): Parameter Store và Secrets Manager integration theo release.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html): parameter hierarchy, SecureString và access control.
- [AWS AppConfig](https://docs.aws.amazon.com/appconfig/latest/userguide/what-is-appconfig.html): dynamic configuration, validation và deployment strategy.
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html): secret lifecycle và rotation.
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): App Configuration, Key Vault và identity integration.
- [Azure App Configuration](https://learn.microsoft.com/azure/azure-app-configuration/overview): key-value, label, feature flag và refresh.
- [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/overview): secrets, keys, certificates và access control.
- [Spring Cloud GCP Secret Manager](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html): Secret Manager integration và configuration.
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs/overview): secret version, IAM và audit.
