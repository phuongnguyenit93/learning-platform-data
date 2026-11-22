# Cấu hình Spring Boot theo môi trường và IAM role

Một dịch vụ Spring Boot có thể chạy trên máy lập trình, trong CI, Amazon ECS, Amazon EKS hoặc AWS Lambda. Cùng một file JAR có thể cần gọi Amazon S3, SQS, DynamoDB và Secrets Manager ở mọi môi trường, nhưng **bucket, queue, Region, endpoint và quyền truy cập** lại khác nhau. Nếu đóng cứng các giá trị vào source code hoặc đặt AWS access key trong application-prod.yml, việc triển khai dễ sai môi trường và tạo rủi ro lộ credential.

Thiết kế đúng cần tách ba khái niệm:

- **Spring profile** chọn cấu hình ứng dụng theo môi trường như dev, test, staging, prod.
- **Externalized configuration** đưa các giá trị có thể thay đổi ra YAML/properties, environment variables, command line, Systems Manager Parameter Store hoặc Secrets Manager.
- **IAM role của runtime** xác định danh tính AWS mà tiến trình được phép sử dụng. ECS task role, EKS Pod Identity/IRSA, EC2 instance profile và Lambda execution role cấp temporary credentials cho AWS SDK.

**Profile prod không tự tạo IAM role production.** Nó chỉ chọn cấu hình Spring. AWS identity đến từ nơi ứng dụng đang chạy và trust/permission policies của IAM. Tách hai lớp này giúp cùng một artifact được triển khai an toàn qua nhiều môi trường.

Bài học thuộc chương **Ứng dụng Java và Spring Boot** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối cấu hình ứng dụng với Region/AZ, IAM, VPC, compute, storage, database, integration và serverless, hướng tới triển khai có thể giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **Spring profiles**, externalized configuration, secrets và AWS IAM roles.
2. Tổ chức application.yml, application-dev.yml, application-prod.yml mà không tạo nhiều bản build.
3. Hiểu thứ tự ưu tiên của Spring Boot property sources và cách environment variables ghi đè cấu hình.
4. Dùng @ConfigurationProperties, validation và fail-fast để kiểm tra cấu hình lúc startup.
5. Cấp AWS credentials qua DefaultCredentialsProvider và IAM role theo runtime.
6. Phân biệt **ECS task role** với **task execution role**, EKS Pod Identity với IRSA, Lambda execution role và EC2 instance profile.
7. Dùng AWS Systems Manager Parameter Store/Secrets Manager với Spring Cloud AWS Config Data imports khi phù hợp.
8. Thiết kế IAM least privilege, VPC connectivity, Region selection và multi-account deployment.
9. Kiểm thử local/staging/production, kiểm tra danh tính thực bằng STS và xử lý lỗi credentials/AccessDenied.
10. Xây quy trình triển khai có rotation, observability, rollback và không lộ secrets.

## 2. Mô hình cấu hình: một artifact, nhiều môi trường

Một ứng dụng nên được build thành **một artifact có thể triển khai ở nhiều môi trường**. Mỗi môi trường cung cấp các giá trị khác nhau qua profile hoặc external configuration. Không cần build orders-api-dev.jar, orders-api-staging.jar và orders-api-prod.jar chỉ vì bucket hoặc queue khác nhau.

~~~mermaid
flowchart TD
    JAR["Một Spring Boot JAR"] --> ENV{"Runtime environment"}
    ENV --> DEV["Local / dev"]
    ENV --> TEST["Test / staging"]
    ENV --> PROD["Production"]
    DEV --> CFG["Spring Environment<br/>profiles + external config"]
    TEST --> CFG
    PROD --> CFG
    CFG --> APP["ConfigurationProperties<br/>Application beans"]
    DEV --> IDDEV["Developer AWS profile / SSO"]
    TEST --> IDTEST["Test task/pod IAM role"]
    PROD --> IDPROD["Production task/pod/Lambda role"]
    IDDEV --> SDK["AWS SDK credentials provider"]
    IDTEST --> SDK
    IDPROD --> SDK
    APP --> SDK
    SDK --> AWS["S3 / SQS / DynamoDB / Secrets Manager"]
~~~

### 2.1. Phân loại dữ liệu cấu hình

| Loại dữ liệu | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| **Application defaults** | Pagination size, feature defaults, timeout logic | application.yml trong source |
| **Environment-specific non-secret** | Bucket name, queue URL, endpoint, log level | Profile YAML, environment variables, Parameter Store |
| **Sensitive secrets** | DB password, API key, third-party token | Secrets Manager hoặc secret store phù hợp |
| **AWS identity** | Quyền s3:GetObject, sqs:SendMessage | IAM role + IAM policy |
| **Deployment/runtime settings** | CPU/memory, task count, port, health checks | ECS task definition, EKS manifests, Lambda configuration |
| **Region/partition** | ap-southeast-1, us-east-1 | Runtime config hoặc AWS region provider |

**Không coi IAM access key là application property.** Access key/secret key thuộc credential mechanism. Ứng dụng trên AWS nên nhận temporary credentials từ IAM role; chỉ local development mới thường dùng profile/SSO do developer đăng nhập.

### 2.2. Profile không phải security boundary

Profile dev có thể chọn bucket thử nghiệm và log DEBUG; profile prod chọn bucket production và log INFO. Nhưng nếu process production vô tình nhận credentials có quyền vào account khác, profile prod không ngăn được quyền đó. Security boundary là **IAM role, resource policies, SCP, VPC và service-level authorization**, không phải tên profile.

Không viết:

~~~yaml
spring:
  profiles:
    active: prod
aws:
  access-key: "AKIA..."
  secret-key: "..."
~~~

trong file được đóng gói vào JAR. Profile active phải được môi trường triển khai chọn; AWS identity phải do runtime cấp.

## 3. Spring Boot profiles và externalized configuration

Spring Boot hỗ trợ application.properties hoặc application.yaml làm cấu hình mặc định và các file application-{profile}.properties/application-{profile}.yaml để ghi đè theo profile. Có thể bật profile qua environment variable, system property hoặc command line.

### 3.1. Cấu trúc file đề xuất

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

application.yml giữ cấu hình chung:

~~~yaml
spring:
  application:
    name: orders-api

app:
  aws:
    region: ap-southeast-1
    catalog:
      bucket: orders-catalog-local
    orders:
      queue-url: http://localhost:4566/000000000000/orders-local
  features:
    enable-new-checkout: false

logging:
  level:
    root: INFO
~~~

File application-dev.yml chỉ ghi những khác biệt cần thiết:

~~~yaml
app:
  aws:
    catalog:
      bucket: orders-catalog-dev
    orders:
      queue-url: https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-dev
  features:
    enable-new-checkout: true

logging:
  level:
    com.example.orders: DEBUG
~~~

application-prod.yml trỏ tới tài nguyên production:

~~~yaml
app:
  aws:
    catalog:
      bucket: orders-catalog-prod
    orders:
      queue-url: https://sqs.ap-southeast-1.amazonaws.com/444455556666/orders-prod
  features:
    enable-new-checkout: true

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

Các tên bucket/queue trong ví dụ là minh họa. **Không đặt database password, AWS access key, private key hoặc token trong các profile file**, kể cả file application-prod.yml được giới hạn quyền trong Git.

### 3.2. Kích hoạt profile từ runtime

Có thể chọn profile mà không sửa source:

~~~bash
# Linux/macOS shell
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-api.jar
~~~

~~~powershell
# Windows PowerShell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar .\orders-api.jar
~~~

Hoặc:

~~~bash
java -jar orders-api.jar --spring.profiles.active=prod
~~~

Trong ECS task definition, Kubernetes Deployment hoặc Lambda configuration, đặt SPRING_PROFILES_ACTIVE theo environment. Tránh đưa prod làm profile mặc định trong JAR vì cùng artifact có thể được chạy nhầm ở môi trường khác.

### 3.3. Thứ tự ưu tiên property sources

Spring Boot có quy tắc ưu tiên giữa các property sources; cấu hình ở nguồn có ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn. Các nguồn thường gặp gồm:

| Nguồn | Ví dụ | Cách sử dụng |
|---|---|---|
| Default properties | SpringApplication.setDefaultProperties | Giá trị mặc định trong code |
| Config data trong JAR | application.yml, application-prod.yml | Defaults và profile configuration |
| Config data bên ngoài JAR | ./config/application-prod.yml | Cấu hình do môi trường mount |
| OS environment variables | APP_AWS_REGION, SPRING_PROFILES_ACTIVE | Container/task/pod runtime config |
| Java system properties | -Dapp.aws.region=... | JVM startup |
| Command-line arguments | --app.aws.region=... | Ghi đè khi khởi chạy |

Thứ tự đầy đủ còn có các nguồn như @PropertySource, test properties, DevTools và các config data imports. Hãy xem **Spring Boot Externalized Configuration** của đúng version khi một giá trị bất ngờ bị ghi đè.

### 3.4. Quy tắc quan trọng với spring.profiles.active

spring.profiles.active và spring.profiles.default chỉ được khai báo trong **non-profile-specific documents**. Không đặt spring.profiles.active: prod bên trong application-prod.yml hoặc một YAML document chỉ được activate khi profile prod đã active. Chọn profile từ deployment environment hoặc command line.

### 3.5. Environment variable mapping

Spring Boot có thể bind property:

~~~text
app.aws.catalog.bucket
~~~

từ environment variable:

~~~text
APP_AWS_CATALOG_BUCKET
~~~

Ví dụ ghi đè bucket mà không cần sửa JAR:

~~~bash
APP_AWS_CATALOG_BUCKET=orders-catalog-prod java -jar orders-api.jar
~~~

Tên biến môi trường thường viết uppercase và thay dấu chấm/gạch nối bằng underscore. Khi bind Map properties, quy tắc chuyển đổi có thể làm key lowercase; không dùng Map keys phân biệt chữ hoa/chữ thường nếu cấu hình đến từ environment variables.

## 4. Bind cấu hình bằng @ConfigurationProperties

Không nên rải hàng chục biểu thức @Value trong controller/service. **@ConfigurationProperties** gom các thuộc tính cùng nhóm thành một object có kiểu dữ liệu, dễ validate, test và tài liệu hóa.

### 4.1. Khai báo configuration record

~~~java
package com.example.orders.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.aws")
public record AwsApplicationProperties(
        @NotBlank String region,
        @NotNull @Valid Catalog catalog,
        @NotNull @Valid Orders orders) {

    public record Catalog(@NotBlank String bucket) {}

    public record Orders(@NotBlank String queueUrl) {}
}
~~~

Kích hoạt scan configuration properties ở application:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Thêm dependency validation phù hợp Spring Boot version, ví dụ **spring-boot-starter-validation**. Khi thiếu bucket hoặc queue URL bắt buộc, ứng dụng fail ở startup thay vì đợi đến request đầu tiên mới lỗi.

### 4.2. Inject properties vào service

~~~java
package com.example.orders.storage;

import com.example.orders.config.AwsApplicationProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AwsApplicationProperties properties;

    public CatalogService(AwsApplicationProperties properties) {
        this.properties = properties;
    }

    public String catalogBucket() {
        return properties.catalog().bucket();
    }
}
~~~

Ứng dụng có thể inject các properties vào AWS configuration bean để tạo client, hoặc để Spring Cloud AWS tự cấu hình service clients. Không đọc trực tiếp environment variables ở mọi business class; gom chúng vào configuration boundary.

### 4.3. Cấu hình endpoint và Region có validation

Một số giá trị phải kiểm tra chặt hơn @NotBlank:

- Region phải là Region AWS hợp lệ và service đó được hỗ trợ.
- Queue URL phải thuộc account/Region đúng với môi trường.
- Bucket name phải là tài nguyên môi trường hiện tại, không phải bucket production khi profile dev.
- Endpoint override chỉ bật trong local/test và phải nằm trong allowlist cấu hình.
- Timeout phải dương và nằm trong giới hạn đã định.

Có thể viết **custom validator** hoặc kiểm tra ở startup. Tránh gọi mọi AWS APIs chỉ để validate cấu hình nếu điều đó làm tăng thời gian khởi động và IAM permissions; chọn kiểm tra phù hợp với SLO và readiness model.

## 5. Secrets và cấu hình từ AWS Systems Manager/Secrets Manager

Profile YAML thích hợp cho non-secret values ít thay đổi. Với các cấu hình cần quản trị tập trung, audit, cập nhật độc lập và phân quyền, có thể dùng:

- **AWS Systems Manager Parameter Store:** cấu hình như queue path, feature setting, non-secret endpoints và SecureString theo nhu cầu.
- **AWS Secrets Manager:** DB passwords, third-party credentials, API tokens và secrets cần rotation.
- **Spring Cloud AWS Config Data integration:** nạp values vào Spring Environment ở bootstrap qua spring.config.import.

### 5.1. Chọn đúng loại dữ liệu

| Giá trị | Nơi lưu đề xuất | Ví dụ |
|---|---|---|
| Số lần retry mặc định | application.yml / Parameter Store | /config/orders-api/retry/max-attempts |
| Tên bucket theo môi trường | Parameter Store hoặc deployment env | /config/orders-api/storage/catalog-bucket |
| DB username/password | Secrets Manager hoặc RDS-managed secret | orders/prod/database |
| External payment API token | Secrets Manager | orders/prod/payment-provider |
| AWS role permissions | IAM policy, không phải Parameter Store | s3:GetObject trên bucket ARN |
| Region/runtime role | Runtime deployment configuration và IAM | AWS_REGION, ECS task role |

Không đưa **AWS access key/secret key** vào Secrets Manager chỉ để ứng dụng assume một role mà runtime đã có. Secrets Manager dành cho secrets của ứng dụng hoặc dịch vụ; IAM role là cơ chế cấp AWS API permissions.

### 5.2. Spring Cloud AWS: chọn version tương thích

Spring Cloud AWS cung cấp các starter cho core AWS integration, S3, SQS, Parameter Store, Secrets Manager và những dịch vụ khác. Dùng **Spring Cloud AWS BOM** để đồng bộ các modules. Chọn nhánh tương thích với Spring Boot/Spring Cloud release train của dự án; ví dụ **Spring Cloud AWS 3.4.x** tương thích dòng **Spring Boot 3.5.x**, còn nhánh **4.x** dành cho dòng Spring Boot 4.x tương ứng. Kiểm tra release matrix chính thức trước khi nâng cấp.

Ví dụ Maven dependencies cho Spring Cloud AWS 3.4.x:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.awspring.cloud</groupId>
      <artifactId>spring-cloud-aws-dependencies</artifactId>
      <version>3.4.x</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter</artifactId>
  </dependency>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
  </dependency>
  <dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
  </dependency>
</dependencies>
~~~

Đây là ví dụ coordinates; thay version bằng release cụ thể tương thích, không dùng chuỗi 3.4.x như version Maven thật. Chỉ thêm starter mà ứng dụng thực sự dùng.

### 5.3. Import Parameter Store vào Spring Environment

Với Spring Cloud AWS 3.x, có thể khai báo:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "aws-parameterstore:/config/orders-api/"
~~~

Các parameter nằm dưới path /config/orders-api/ được nạp vào Spring Environment. **Dấu slash cuối path có ý nghĩa** khi muốn tên property được nối tiếp theo cấu trúc path. Nếu cần shared config và app-specific config, có thể import nhiều paths theo cú pháp mà version Spring Cloud AWS đang dùng.

Ví dụ parameters:

~~~text
/config/orders-api/app/aws/catalog/bucket = orders-catalog-prod
/config/orders-api/app/aws/orders/queue-url = https://sqs.ap-southeast-1.amazonaws.com/444455556666/orders-prod
~~~

Sau khi được load, các giá trị có thể bind vào AwsApplicationProperties. IAM role của ứng dụng cần quyền đọc đúng Parameter Store paths; nếu dùng SecureString với customer-managed KMS key, cần quyền decrypt tương ứng theo policy.

### 5.4. Import Secrets Manager

Ví dụ secret tên orders/prod/database:

~~~yaml
spring:
  config:
    import: "aws-secretsmanager:orders/prod/database"
~~~

Secret dạng JSON có thể chứa:

~~~json
{
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE",
  "host": "orders-db.example.ap-southeast-1.rds.amazonaws.com",
  "port": 5432
}
~~~

Spring Cloud AWS có thể đưa các secret properties vào Spring Environment để bind qua @Value hoặc @ConfigurationProperties, tùy schema/loader của phiên bản. Secret không nên được in ra log khi bind hoặc khi debug.

### 5.5. Bắt buộc hay tùy chọn khi secret không tồn tại?

Mặc định, import secret không tồn tại có thể khiến ứng dụng **không khởi động**. Nếu một secret thực sự optional, có thể dùng prefix **optional:**:

~~~yaml
spring:
  config:
    import: "optional:aws-secretsmanager:orders/dev/optional-integration"
~~~

Không dùng optional cho DB password, encryption key hoặc credential bắt buộc của production. Nếu ứng dụng khởi động thiếu secret bắt buộc, fail-fast thường an toàn hơn việc phục vụ traffic với cấu hình sai.

### 5.6. Bootstrap dependency và IAM permissions

Config Data imports được xử lý trong giai đoạn bootstrap. Do đó ứng dụng phải có **Region và AWS credentials đủ sớm** để truy cập Parameter Store/Secrets Manager trước khi context hoàn tất. Trong ECS/EKS/Lambda, gắn IAM role đúng từ runtime; không chờ một bean được tạo sau đó mới cấp credentials cho config loader.

Quyền tối thiểu thường cần:

- Parameter Store: ssm:GetParameter/ssm:GetParameters hoặc ssm:GetParametersByPath trên đúng ARN/path.
- SecureString với customer-managed key: kms:Decrypt trên key phù hợp, kèm key policy.
- Secrets Manager: secretsmanager:GetSecretValue trên secret ARN cụ thể.
- Secret dùng customer-managed key: kms:Decrypt trên key tương ứng nếu cần.

**Không cấp ssm:*, secretsmanager:* hoặc kms:* trên toàn account** chỉ để Spring Boot khởi động. Đặt resource ARNs, prefix paths và KMS key scope rõ ràng.

## 6. AWS credentials provider: để runtime cấp danh tính

AWS SDK cần credentials để ký SigV4 cho các API requests. Với AWS SDK for Java 2.x, **DefaultCredentialsProvider** tìm credentials qua một chuỗi provider. Nếu không chỉ định provider trên service client, SDK dùng default chain.

### 6.1. Default credentials provider chain

Các nguồn phổ biến theo thứ tự tìm kiếm của SDK for Java 2.x:

1. **Java system properties:** aws.accessKeyId, aws.secretAccessKey, aws.sessionToken.
2. **Environment variables:** AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN.
3. **Web identity token:** AWS_WEB_IDENTITY_TOKEN_FILE và AWS_ROLE_ARN, thường dùng với EKS IRSA.
4. **Shared AWS profiles/config files:** IAM Identity Center SSO, role profiles và các cấu hình profile khác.
5. **ECS container credentials:** endpoint credentials do ECS agent cấp cho task role.
6. **EC2 instance profile:** credentials qua EC2 Instance Metadata Service.

Chain dừng tại provider đầu tiên lấy được credentials hợp lệ. Thứ tự này rất quan trọng: **AWS_ACCESS_KEY_ID cũ trong environment có thể được chọn trước web identity/ECS/EC2 role**, khiến ứng dụng dùng nhầm danh tính dù đã gắn IAM role đúng.

~~~mermaid
flowchart TD
    APP["AWS SDK client cần ký request"] --> CHAIN["DefaultCredentialsProvider"]
    CHAIN --> SYS["1. JVM system properties"]
    SYS --> ENV["2. Environment variables"]
    ENV --> WEB["3. Web identity token"]
    WEB --> PROFILE["4. Shared profile / SSO"]
    PROFILE --> ECS["5. ECS task credentials"]
    ECS --> EC2["6. EC2 instance profile"]
    SYS --> FOUND["Credentials hợp lệ"]
    ENV --> FOUND
    WEB --> FOUND
    PROFILE --> FOUND
    ECS --> FOUND
    EC2 --> FOUND
    FOUND --> SIGN["SigV4 request signing"]
~~~

Sơ đồ minh họa chuỗi tìm kiếm: khi provider hiện tại không có credentials hợp lệ, SDK thử provider tiếp theo. Nếu một nguồn credentials không mong muốn được đặt ở đầu chuỗi, nó có thể che mất role credentials mà người vận hành định sử dụng.

### 6.2. Tạo service client không hard-code credentials

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    // Không truyền access key/secret key.
    // SDK dùng DefaultCredentialsProvider.
    .build();
~~~

Đây thường là cấu hình phù hợp cho workload chạy trên AWS. Nếu Spring Cloud AWS starter được dùng, starter có thể tự cấu hình Region và credentials provider cho các integrations; không cần tạo thêm một credentials chain khác nếu không có yêu cầu rõ.

### 6.3. Explicit DefaultCredentialsProvider khi muốn thể hiện chủ đích

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

SqsClient sqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();
~~~

Việc chỉ rõ provider không làm thay đổi nguồn credentials mặc định; nó làm ý định sử dụng chain rõ ràng hơn. Nếu ứng dụng tự tạo provider hoặc HTTP clients có lifecycle riêng, cần quản lý/đóng đúng owner theo hướng dẫn SDK version.

## 7. Local development: dùng AWS IAM Identity Center/SSO profile

Máy lập trình không nên dùng access key của production role. Dùng **AWS IAM Identity Center** hoặc profile được tổ chức cấp quyền phát triển.

### 7.1. Profile trong AWS config

Ví dụ cấu hình trong file shared config:

~~~ini
[profile orders-dev]
sso_session = company
sso_account_id = 111122223333
sso_role_name = Developer
region = ap-southeast-1
output = json

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access
~~~

Các giá trị account, role và URL là placeholders. Tổ chức phải cấp quyền Identity Center tương ứng. Đăng nhập và chạy ứng dụng:

~~~bash
aws sso login --profile orders-dev
export AWS_PROFILE=orders-dev
export AWS_REGION=ap-southeast-1
export SPRING_PROFILES_ACTIVE=dev
java -jar orders-api.jar
~~~

AWS SDK for Java 2.x ProfileCredentialsProvider hỗ trợ cấu hình IAM Identity Center trong shared config theo phiên bản SDK. Khi SSO session hết hạn, đăng nhập lại bằng CLI; không copy SSO cache token vào file cấu hình ứng dụng.

Với AWS SDK for Java 2.x sử dụng IAM Identity Center profile, thêm các modules SSO tương ứng vào build nếu chưa được starter khác kéo vào:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>sso</artifactId>
</dependency>
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>ssooidc</artifactId>
</dependency>
~~~

Quản lý version bằng AWS SDK BOM. Nếu thiếu module cần thiết, ProfileCredentialsProvider có thể không xử lý được SSO profile dù file shared config đúng.

### 7.2. Thứ tự precedence có thể gây nhầm local

Nếu máy developer có cả AWS_PROFILE=orders-dev và AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, default chain có thể chọn environment credentials trước shared profile. Khi thấy account không đúng:

1. Kiểm tra AWS caller identity bằng AWS CLI và từ chính process/app nếu có thể.
2. Kiểm tra Java system properties aws.accessKeyId/aws.secretAccessKey.
3. Kiểm tra environment variables AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY và AWS_SESSION_TOKEN.
4. Kiểm tra AWS_PROFILE và SSO session.
5. Xác minh account/role và Region được cấp.

Không giải quyết bằng cách dán access keys mới vào application-dev.yml. Xóa biến môi trường credentials không mong muốn và dùng profile/SSO đúng.

### 7.3. Kiểm tra danh tính bằng STS

~~~bash
aws sts get-caller-identity --profile orders-dev
~~~

Output gồm Account, Arn và UserId. Kiểm tra account/role đúng trước khi chạy integration tests hoặc thao tác ghi dữ liệu. Lệnh này là **read-only** và không tiết lộ secret access key.

## 8. Production IAM role theo compute runtime

Trong production, IAM role được gắn với **runtime identity**. Ứng dụng chỉ cần dùng credentials provider chain tương thích; platform cấp temporary credentials và SDK làm mới chúng theo cơ chế provider.

### 8.1. ECS: task role và task execution role

Đây là hai vai trò khác nhau:

| Role | Ai sử dụng? | Ví dụ quyền |
|---|---|---|
| **Task execution role** | ECS/Fargate agent để chuẩn bị/chạy task | Pull image từ ECR, gửi logs CloudWatch, lấy secret được tham chiếu trong task definition |
| **Task role** | Code trong container của ứng dụng | s3:GetObject, sqs:SendMessage, dynamodb:GetItem trên resources cần thiết |

**Application Java cần task role** khi gọi AWS SDK. Không gắn quyền S3/SQS nghiệp vụ vào task execution role rồi mong container tự nhận được. Task execution role cho phép agent thực hiện các thao tác hạ tầng; task role cấp credentials cho ứng dụng.

Ví dụ ECS task definition (fragment):

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "essential": true,
      "environment": [
        {"name": "SPRING_PROFILES_ACTIVE", "value": "prod"},
        {"name": "AWS_REGION", "value": "ap-southeast-1"}
      ]
    }
  ]
}
~~~

Đây là fragment minh họa; task definition thực tế còn cần CPU/memory, network mode, ports, logging, health checks và cấu hình secrets nếu có. Task role được ECS cấp qua container credentials endpoint; SDK default chain có thể tự tìm credentials. Không đọc credential endpoint rồi tự ghi temporary keys ra log.

### 8.2. EKS: Pod Identity hoặc IRSA

**EKS Pod Identity** và **IAM Roles for Service Accounts (IRSA)** đều cho phép gắn IAM role với Kubernetes service account để từng workload có quyền riêng.

| Tiêu chí | EKS Pod Identity | IRSA |
|---|---|---|
| Cơ chế | EKS association + Pod Identity Agent | IAM OIDC provider + service account annotation/token |
| Trust principal | pods.eks.amazonaws.com | OIDC federated principal của cluster |
| Credentials delivery | Agent cung cấp credentials cho Pod | Web identity token file và STS AssumeRoleWithWebIdentity |
| Phạm vi | Service account gắn association với role | Service account được annotation role ARN |
| SDK | Default provider chain hỗ trợ theo version | WebIdentityTokenFileCredentialsProvider trong chain |

Với **Pod Identity**, cài Pod Identity Agent, tạo association giữa cluster/namespace/service account và IAM role. Với **IRSA**, cần OIDC provider cho cluster và trust policy giới hạn đúng subject và audience của service account. Chọn một cơ chế theo chuẩn cluster; không gắn quyền rộng vào node role thay cho workload role.

Các luồng web identity/AssumeRole cần AWS SDK STS module trên classpath. Với SDK trực tiếp, thêm software.amazon.awssdk:sts cùng version BOM; Spring Cloud AWS starter có thể đã quản lý dependency này theo integration/version.

Ví dụ Kubernetes service account dùng IRSA:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::444455556666:role/orders-api-irsa-role
~~~

Với EKS Pod Identity, association được tạo trong EKS; không dùng annotation IRSA này để thay association. Trong cả hai trường hợp, application Java dùng default credentials provider chain và không cần hard-code role ARN trong source code.

### 8.3. Lambda execution role

Lambda function có **execution role** do Lambda assume. Role đó chứa quyền mà code trong handler cần, ví dụ đọc một S3 prefix hoặc gửi message đến một SQS queue. AWS SDK lấy temporary credentials trong execution environment.

- Không tự gọi STS AssumeRole để assume lại chính execution role nếu không có yêu cầu cross-account/role chaining.
- Dùng một role riêng cho mỗi nhóm chức năng có quyền khác nhau.
- Đặt timeout/memory/concurrency và quyền network phù hợp.
- Nếu function ở private VPC subnets, bảo đảm đường đến AWS APIs qua NAT hoặc VPC endpoints cần thiết.

### 8.4. EC2 instance profile

Ứng dụng Java trên EC2 nhận credentials từ IAM role được gắn thông qua **instance profile**. SDK dùng EC2 Instance Metadata Service khi các provider trước đó không có credentials. Bật **IMDSv2**, giới hạn hop/metadata access và tránh để containers không tin cậy truy cập instance role. Với ECS trên EC2, ưu tiên task role riêng cho container application.

### 8.5. Không dùng một IAM role cho mọi môi trường

| Môi trường | Danh tính đề xuất | Quyền điển hình |
|---|---|---|
| Local developer | IAM Identity Center SSO profile | Dev bucket/queue/test resources |
| CI pipeline | OIDC federation/assume role cho pipeline | Build/deploy artifacts, không cần quyền runtime business |
| Test | ECS task role/EKS service account role riêng | Test tables, queues, buckets |
| Staging | Role riêng cho staging account/resources | Gần production nhưng dữ liệu tách biệt |
| Production | Task/pod/Lambda/instance role production | Chỉ quyền business cần thiết |

Tách roles giúp giảm blast radius và audit rõ workload nào gọi AWS APIs. Không dùng một access key của IAM user chia sẻ giữa developer, CI và production.

## 9. IAM policy: cấp đúng quyền cho ứng dụng

IAM role có hai phần cần phân biệt:

- **Trust policy** quy định ai/dịch vụ nào được assume role.
- **Permissions policy** quy định role sau khi được assume có thể làm gì trên AWS resources.

Một ECS task role có trust policy cho ecs-tasks.amazonaws.com, còn permissions policy có thể chỉ cho đọc object trong một S3 bucket và gửi message vào một SQS queue cụ thể.

### 9.1. Ví dụ trust policy cho ECS task role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEcsTasks",
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy này chỉ minh họa principal dịch vụ ECS tasks. Khi triển khai, dùng role trust conditions và guardrails phù hợp với account/organization; không tái sử dụng trust policy của Lambda/EKS cho ECS.

### 9.2. Permissions policy cho một Spring Boot service

Giả sử orders-api cần đọc catalog object và gửi đơn hàng vào một queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCatalogOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::orders-catalog-prod/*"
    },
    {
      "Sid": "SendOrdersOnly",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:orders-prod"
    }
  ]
}
~~~

Policy trên là ví dụ identity policy cho **task role**, cần bổ sung những actions thực tế mà code gọi. Nếu app liệt kê bucket, đọc KMS-encrypted objects hoặc dùng SSE-KMS, có thể cần thêm quyền tương ứng; chỉ cấp khi thật sự cần. Resource ARN phải trỏ tới tài nguyên của đúng môi trường.

### 9.3. Không nhầm quyền của runtime với quyền triển khai

| Principal | Công việc | Ví dụ quyền |
|---|---|---|
| **Application task/pod role** | Chạy nghiệp vụ | s3:GetObject, sqs:SendMessage, dynamodb:UpdateItem |
| **CI/CD deploy role** | Cập nhật ECS/EKS/Lambda resources | Update service/deployment, pass đúng task/execution role |
| **ECS task execution role** | Agent pull image/ghi logs/đọc secrets task definition | ECR pull, CloudWatch Logs, secret injection |
| **Platform administrator** | Tạo role, trust policy, network, service resources | IAM/ECS/EKS/VPC administration theo phạm vi |

Không đưa quyền CreateRole, AttachRolePolicy hoặc iam:PassRole rộng vào application task role. Application runtime không cần quyền tự thay đổi IAM role của chính nó.

### 9.4. EKS Pod Identity trust policy

EKS Pod Identity dùng service principal **pods.eks.amazonaws.com** và các actions **sts:AssumeRole**, **sts:TagSession**. Có thể giới hạn association bằng request tags về cluster/namespace/service account theo hướng dẫn EKS. Với IRSA, trust policy dùng OIDC provider và điều kiện subject/audience. Hai trust models không giống nhau; copy nhầm sẽ khiến Pod không nhận được credentials.

## 10. Region selection và cấu hình AWS clients

Region ảnh hưởng endpoint, resource ARN, service availability, data residency và latency. Một client SDK thông thường được cấu hình Region khi build; không lấy Region từ user request rồi thay đổi tùy ý cho từng call.

### 10.1. Region provider trong AWS SDK for Java 2.x

Default region provider chain thường xem:

1. Java system property **aws.region**.
2. Environment variable **AWS_REGION**.
3. Shared AWS config/profile.
4. EC2 instance metadata khi chạy trên EC2.

Với Spring Cloud AWS, có thể cấu hình Region tĩnh bằng **spring.cloud.aws.region.static**; nếu không, starter sử dụng region provider chain theo version. Không để app property và AWS_REGION trỏ tới hai Region khác nhau mà không có chủ đích.

Ví dụ cấu hình Spring Cloud AWS:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Nếu dùng SDK trực tiếp, có thể bind Region từ application properties:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class AwsClientConfiguration {
    @Bean
    S3Client s3Client(AwsApplicationProperties properties) {
        return S3Client.builder()
            .region(Region.of(properties.region()))
            .build();
    }
}
~~~

SDK tự dùng default credentials chain vì không truyền access key. Nếu dùng Spring Cloud AWS auto-configuration cho S3Client, không khai báo một bean S3Client thứ hai có cấu hình mâu thuẫn; chỉ custom bean khi cần override có chủ đích.

### 10.2. Khi cần nhiều Region

Ví dụ ứng dụng phục vụ dữ liệu tại ap-southeast-1 và ap-northeast-1:

- Tạo **client riêng cho mỗi Region** với endpoint/signing Region tương ứng.
- Đặt bucket/table/queue ARNs trong config theo Region, tránh nối tên ARN tùy tiện.
- Xác minh quyền IAM trên resource của cả hai Region.
- Thiết kế retry/failover và data consistency; đổi Region không tự sao chép dữ liệu.
- Với cross-Region S3 access, kiểm tra data transfer, KMS key Region và bucket policy.

Không thay đổi Region trên cùng client cho mỗi request bằng cách mutate builder hoặc dùng endpoint tùy ý.

### 10.3. Cross-account access bằng AssumeRole

Nếu production service ở Account A cần đọc một resource trong Account B, mô hình thường gồm:

1. Runtime role ở Account A có quyền sts:AssumeRole trên target role ARN.
2. Target role ở Account B có trust policy cho phép source role Account A.
3. Target role có permissions policy chỉ cấp quyền trên resource đích.
4. Java SDK dùng STS AssumeRole credentials provider để tự refresh temporary credentials.

Không cấp sts:AssumeRole trên wildcard nếu chỉ cần một target role. Nếu resource policy ở account đích cũng cần cho phép source principal, phải cấu hình cả hai phía theo loại dịch vụ.

## 11. VPC connectivity cho ứng dụng Spring Boot

IAM policy cho phép gọi API không có nghĩa ứng dụng có network path tới AWS service endpoint. Trong private subnets, cần thiết kế routing, DNS, security groups và VPC endpoints.

~~~mermaid
flowchart TD
    APP["Spring Boot ECS task / EKS Pod<br/>Private subnet"] --> DNS["VPC DNS resolution"]
    DNS --> VPCE["VPC endpoint"]
    DNS --> NAT["NAT Gateway / egress path"]
    VPCE --> S3["S3 Gateway endpoint"]
    VPCE --> API["Interface endpoints<br/>SQS / STS / SSM / Secrets Manager"]
    NAT --> PUBLIC["AWS public service endpoints<br/>HTTPS"]
    S3 --> IAM["IAM + bucket/resource policies"]
    API --> IAM
    PUBLIC --> IAM
~~~

### 11.1. Kiểm tra từng lớp

| Lớp | Cần xác minh |
|---|---|
| **Subnet/route** | Private subnet có route tới NAT hoặc VPC endpoint phù hợp |
| **Security group** | Egress TCP 443 và DNS được cho phép theo policy |
| **NACL** | Inbound/outbound ephemeral ports không bị chặn |
| **DNS** | VPC DNS support/hostnames, private DNS cho interface endpoints |
| **VPC endpoint policy** | Cho phép actions/resources mà ứng dụng cần |
| **IAM** | Runtime role có identity policy phù hợp |
| **Resource policy** | S3 bucket/SQS queue/secret policy không explicit Deny |
| **KMS** | Key policy/grants cho phép decrypt khi service/resource cần |

### 11.2. Interface endpoints và gateway endpoints

S3 thường có **Gateway VPC endpoint**; các dịch vụ như SQS, STS, Systems Manager và Secrets Manager có thể dùng **Interface VPC endpoints** theo availability/Region. Nếu dùng Spring Cloud AWS Parameter Store/Secrets Manager ở giai đoạn bootstrap, private subnet cần đường mạng tới các endpoints đó trước khi application context hoàn tất.

VPC endpoint giúp traffic tới dịch vụ đi qua private network path, nhưng **không thay IAM** và không tự cho phép mọi actions. Endpoint policy có thể giới hạn tài nguyên; bucket/queue/secret policy cũng có thể từ chối request.

### 11.3. Khi app chạy trong private subnet nhưng không gọi được Secrets Manager

Kiểm tra theo thứ tự: Region/endpoint đúng, DNS resolve interface endpoint, SG endpoint cho phép TCP 443 từ app SG, route/NACL, endpoint policy, task/pod role có GetSecretValue, secret resource policy và KMS key permissions. Không bật public IP hoặc mở security group toàn Internet chỉ để khắc phục lỗi.

## 12. Spring Cloud AWS auto-configuration và AWS SDK trực tiếp

Có hai cách tích hợp AWS APIs vào Spring Boot:

1. **Spring Cloud AWS starters** tự cấu hình một số AWS SDK clients và Spring integrations.
2. **AWS SDK for Java 2.x trực tiếp** khi ứng dụng muốn tự kiểm soát client beans, HTTP transport, retries hoặc chưa cần Spring Cloud AWS.

Không cần dùng cả hai cách cho cùng một client nếu điều đó tạo ra cấu hình trùng lặp.

### 12.1. Spring Cloud AWS core

Spring Cloud AWS core starter có thể auto-configure **AwsCredentialsProvider** và **AwsRegionProvider** cho application context. Với cấu hình mặc định, credentials provider dùng default chain của AWS SDK. Region có thể lấy từ provider chain hoặc cấu hình rõ bằng:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Các starters như S3/SQS/DynamoDB có thể cung cấp service integrations và auto-configured clients. Tên property, behavior và dependencies khác nhau theo Spring Cloud AWS version; đối chiếu reference của đúng release.

### 12.2. Tránh static credentials properties trong production

Spring Cloud AWS có những property cấu hình static access key/secret key cho các use cases đặc biệt. Không sử dụng chúng cho ECS/EKS/Lambda/EC2 production khi runtime IAM role đã có thể cấp temporary credentials. Không khai báo:

~~~yaml
spring:
  cloud:
    aws:
      credentials:
        access-key: "..."
        secret-key: "..."
~~~

trong application-prod.yml hoặc deployment manifest. Nếu local development cần SSO, dùng AWS_PROFILE/shared config; nếu production cần role, dùng runtime role.

### 12.3. Dùng AWS SDK trực tiếp khi cần custom client

Nếu không dùng Spring Cloud AWS auto-configured client, tạo client bean:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration
public class SqsConfiguration {
    @Bean
    SqsClient sqsClient(AwsApplicationProperties properties) {
        return SqsClient.builder()
            .region(Region.of(properties.region()))
            .build();
    }
}
~~~

Không truyền credentials để SDK sử dụng provider chain. Client là bean dùng chung theo application lifecycle; không build một client cho mỗi message hoặc HTTP request. Khi custom HTTP transport, timeouts hoặc retries, cấu hình bean theo một owner rõ ràng.

### 12.4. Kiểm tra version matrix

Spring Cloud AWS 2.x dùng các package/property names cũ và tương thích Spring Boot 2.x; Spring Cloud AWS 3.x chuyển sang AWS SDK v2 và Spring Boot 3.x; nhánh 4.x dành cho Spring Boot 4.x theo release matrix. Không trộn property prefix của 2.x với 3.x/4.x.

Ví dụ migration property prefix:

| Spring Cloud AWS 2.x | Spring Cloud AWS 3.x |
|---|---|
| cloud.aws.credentials.access-key | spring.cloud.aws.credentials.access-key |
| cloud.aws.credentials.secret-key | spring.cloud.aws.credentials.secret-key |
| aws.paramstore.region | spring.cloud.aws.parameterstore.region |
| aws.secretsmanager.region | spring.cloud.aws.secretsmanager.region |

Đây là ví dụ một số property đã thay đổi; kiểm tra migration guide đầy đủ trước khi nâng cấp.

## 13. Cấu hình deployment cho ECS, EKS và Lambda

Profile và environment variables nên được truyền bởi **deployment platform**, không được ghi lại trong image. Runtime role được gắn độc lập với profile.

### 13.1. ECS/Fargate: environment và task role

Một phần task definition có thể đặt:

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "environment": [
        {"name": "SPRING_PROFILES_ACTIVE", "value": "prod"},
        {"name": "AWS_REGION", "value": "ap-southeast-1"},
        {"name": "APP_AWS_CATALOG_BUCKET", "value": "orders-catalog-prod"}
      ]
    }
  ]
}
~~~

taskRoleArn là danh tính của Java application; executionRoleArn là danh tính của ECS agent. Nếu task definition inject secret vào environment, quyền lấy secret thuộc execution role theo cách ECS agent xử lý; nếu Java tự gọi Secrets Manager, application task role cần GetSecretValue. Phân biệt hai đường này khi cấp IAM.

### 13.2. EKS: profile và service account

Ví dụ deployment trỏ tới service account đã được liên kết với IAM role:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: AWS_REGION
              value: ap-southeast-1
            - name: APP_AWS_CATALOG_BUCKET
              value: orders-catalog-prod
~~~

Service account phải được cấu hình IRSA annotation hoặc EKS Pod Identity association trước khi Pod chạy. Chỉ đặt serviceAccountName không tự cấp IAM permissions. Khi rollout, kiểm tra Pods mới có credentials từ đúng workload role.

### 13.3. Lambda: environment variables và execution role

Trong Lambda configuration:

- Đặt **SPRING_PROFILES_ACTIVE=prod** và các non-secret settings.
- Gắn execution role có quyền tối thiểu.
- Chọn memory/timeout/concurrency phù hợp với Spring startup và workload.
- Tạo AWS SDK clients ngoài handler khi runtime reuse được.
- Nếu dùng Spring Cloud Function/AWS adapter, kiểm tra cách adapter quản lý application context và cold starts theo version.

Không nhúng production credentials vào Lambda environment variables. Nếu Lambda cần secret, dùng Secrets Manager/Parameter Store hoặc secret integration phù hợp; hạn chế quyền và không log secret value.

### 13.4. Không bake profile vào Docker image

Một Docker image production-ready nên không phụ thuộc môi trường:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Platform cung cấp SPRING_PROFILES_ACTIVE, AWS_REGION, non-secret application settings và IAM role khi chạy container. Image tag/digest được promote giữa môi trường sau khi test; không build lại image chỉ để đổi bucket/queue.

## 14. CI/CD identity và application runtime identity

CI pipeline cần quyền **build/deploy**, còn Spring Boot process cần quyền **chạy nghiệp vụ**. Hai danh tính này không nên gộp.

~~~mermaid
flowchart TD
    DEV["Developer / Git repository"] --> CI["CI pipeline"]
    CI --> OIDC["OIDC federation / deploy role"]
    OIDC --> DEPLOY["Deploy ECS/EKS/Lambda"]
    DEPLOY --> RUNTIME["Application runtime"]
    RUNTIME --> ROLE["Task / Pod / Lambda IAM role"]
    ROLE --> AWS["S3 / SQS / DynamoDB / Secrets Manager"]
~~~

### 14.1. CI role chỉ có quyền triển khai

CI role có thể cần đọc artifact registry, cập nhật ECS service/task definition hoặc cập nhật Kubernetes manifests. Nó không cần quyền gửi đơn hàng hoặc đọc dữ liệu khách hàng production chỉ vì ứng dụng có quyền đó.

### 14.2. Dùng OIDC federation thay access keys dài hạn

Các nền tảng CI có thể phát hành OIDC token để assume role trong AWS, với trust policy giới hạn repository, branch, tag hoặc environment. Khi deploy xong, runtime nhận role riêng từ ECS/EKS/Lambda. Không copy temporary credentials từ CI vào Docker image hoặc file cấu hình ứng dụng.

### 14.3. iam:PassRole phải giới hạn

Deploy role có thể cần iam:PassRole để gắn task/execution role hoặc Lambda execution role vào resource. Chỉ cho phép pass đúng các role ARN được duyệt và condition phù hợp với service. Không cấp iam:PassRole trên wildcard nếu pipeline chỉ deploy một ứng dụng.

### 14.4. Promotion qua môi trường

1. Build JAR/image một lần và tạo version/digest bất biến.
2. Chạy unit/integration tests.
3. Deploy vào test với test IAM role và test resources.
4. Promote cùng artifact sang staging, chạy smoke/load/security tests.
5. Production approval/deploy dùng deploy role; application sau deploy nhận production task/pod/Lambda role.
6. Theo dõi health/metrics và rollback version nếu lỗi.

**Artifact giống nhau, configuration và IAM role khác nhau.** Không promote một file application-prod.yml chứa credential từ staging.

## 15. Secret rotation và cập nhật cấu hình khi ứng dụng đang chạy

Secrets Manager có thể rotate credentials, nhưng **việc secret được rotate không đồng nghĩa mọi Spring bean đang giữ giá trị cũ tự động cập nhật**.

### 15.1. Cấu hình import thường được nạp lúc bootstrap

Khi Spring Cloud AWS Config Data loader import Parameter Store/Secrets Manager, values được thêm vào Spring Environment trong giai đoạn cấu hình ứng dụng. Nếu password đổi sau khi context đã khởi động, bean đã bind giá trị cũ có thể vẫn giữ giá trị đó cho đến khi có cơ chế refresh/reload hoặc application restart.

Không giả định việc dùng spring.config.import tự động đồng bộ mọi secret rotation vào mọi object đang chạy. Đọc tài liệu reload của đúng Spring Cloud AWS version và kiểm thử lifecycle của connection pool/secret consumer.

### 15.2. Ba chiến lược cập nhật secret

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| **Restart/redeploy** | Rotate secret, sau đó rollout task/pod/function configuration mới | Ứng dụng stateless, deploy pipeline kiểm soát được |
| **Explicit refresh/reload** | Cơ chế reload được cấu hình cập nhật Environment/beans theo hỗ trợ framework | Ứng dụng cần đổi config khi đang chạy, đã test bean refresh |
| **Fetch secret at use/connection time** | Secret provider/cache riêng lấy current value khi tạo connection mới | DB credentials hoặc integration cần rotation độc lập |

Với database password, connection pool có thể tiếp tục dùng connection cũ nhưng các **kết nối mới** cần password đã cập nhật. Khi rotate, phải kiểm thử pool eviction, connection lifetime, retry và khả năng chuyển đổi giữa old/new credentials.

### 15.3. Secrets trong ECS task definition

Nếu ECS task definition inject secret vào environment, secret value thường được resolve khi task khởi chạy. Khi secret đổi, task đang chạy không tự nhận environment value mới; cần **start/redeploy task mới** theo quy trình. Nếu application tự gọi Secrets Manager, task role cần GetSecretValue và ứng dụng phải có cache/refresh strategy.

### 15.4. Rotation không được làm lộ secret

- Không log Environment, ConfigurationProperties hoặc SecretString toàn bộ.
- Không bật Actuator env/configprops endpoints công khai.
- Không đưa password vào command-line arguments, Docker build args hoặc Git.
- Dùng Secrets Manager version stages và audit API calls.
- Chỉ refresh khi secret hợp lệ; nếu refresh thất bại, không ghi đè giá trị đang dùng bằng dữ liệu rỗng.
- Có cảnh báo khi rotation thất bại, secret sắp hết hạn hoặc ứng dụng dùng version cũ quá lâu.

## 16. Fail-fast, health checks và readiness

Ứng dụng cần phát hiện cấu hình sai trước khi nhận traffic, nhưng không nên biến mọi dependency tạm thời thành startup failure không kiểm soát.

### 16.1. Phân biệt cấu hình bắt buộc và dependency readiness

| Kiểm tra | Thời điểm phù hợp | Ví dụ |
|---|---|---|
| **Config binding/validation** | Startup | Bucket name, queue URL, Region, timeout dương |
| **Credential source exists** | Startup hoặc lần gọi đầu tiên | Runtime có role/profile credentials |
| **IAM permission** | Smoke test hoặc lần gọi API | Role được phép gửi SQS message |
| **Network connectivity** | Readiness/monitoring theo thiết kế | VPC endpoint DNS/route |
| **Downstream availability** | Readiness/health có timeout và semantics phù hợp | S3/SQS/DB tạm unavailable |
| **Business invariants** | Request/job execution | Order state, tenant permissions |

Không gọi nhiều AWS APIs đồng bộ trên mỗi health check; điều đó tạo tải và có thể làm health endpoint phụ thuộc vào một dịch vụ không nằm trên critical path. Dùng timeout ngắn, cache health status và phân biệt liveness với readiness.

### 16.2. Spring Boot Actuator

Có thể bật health endpoints để orchestration kiểm tra process:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Chỉ expose những endpoint cần thiết; bảo vệ management port/path và không mở env/configprops/beans/heapdump cho Internet. Liveness cho biết process còn sống; readiness cho biết instance có thể nhận traffic theo tiêu chí ứng dụng.

### 16.3. Không log cấu hình nhạy cảm khi startup

Một log an toàn có thể ghi:

~~~text
Application started
profile=prod
region=ap-southeast-1
awsAccount=444455556666
runtimeRole=orders-api-task-role
~~~

Chỉ log account/role metadata đã được duyệt; không log access key, session token, SecretString, password, full environment hoặc nội dung file config. Nếu cần xác minh IAM identity, có thể gọi STS GetCallerIdentity có kiểm soát và ghi ARN/account đã redaction.

### 16.4. Readiness không thay thế retry

Nếu SQS tạm thời throttle, service có thể vẫn phục vụ HTTP read operations. Không nhất thiết đánh readiness DOWN cho toàn bộ ứng dụng nếu chỉ một dependency phụ bị lỗi. Xác định dependency critical theo endpoint/feature; dùng circuit breaker, retry có giới hạn và degraded mode khi phù hợp.

## 17. Multi-account, cross-Region và phân tách môi trường

Một tổ chức có thể có account riêng cho development, staging, production và security/logging. Cấu hình Spring Boot cần biểu diễn **tài nguyên thuộc môi trường nào**, trong khi IAM xác định role được phép truy cập account/resource đó.

### 17.1. Cấu trúc config path

Một quy ước Parameter Store path có thể là:

~~~text
/orders-api/dev/app/aws/catalog/bucket
/orders-api/dev/app/aws/orders/queue-url
/orders-api/staging/app/aws/catalog/bucket
/orders-api/staging/app/aws/orders/queue-url
/orders-api/prod/app/aws/catalog/bucket
/orders-api/prod/app/aws/orders/queue-url
~~~

IAM role của từng môi trường chỉ được đọc path tương ứng. Không cấp quyền GetParametersByPath trên toàn bộ /orders-api/ cho mọi runtime role.

### 17.2. Tách account giúp giảm blast radius

| Account | Ví dụ tài nguyên | Runtime role |
|---|---|---|
| Dev | dev S3 buckets, test queues, sandbox DB | orders-api-dev-task-role |
| Staging | staging buckets/queues/DB snapshot data | orders-api-staging-task-role |
| Production | production data stores và event queues | orders-api-prod-task-role |
| Shared security | Audit/log archive, central KMS/logging | Chỉ role/automation được phê duyệt |

Không chỉ đổi profile prod; cần đổi **account, resource ARNs, task/pod role, KMS keys, secret ARNs và network path**.

### 17.3. Cross-account AssumeRole

~~~mermaid
flowchart LR
    APP["Orders API<br/>Account A runtime role"] --> STS["AWS STS AssumeRole"]
    STS --> TARGET["Read-only role<br/>Account B"]
    TARGET --> RESOURCE["S3 / DynamoDB<br/>Account B resources"]
    APP --> BASE["Account A resources"]
~~~

Target role ở Account B cần trust source role; source role cần sts:AssumeRole; target role permissions chỉ cho resource cần. SDK dùng **StsAssumeRoleCredentialsProvider** để cache/refresh temporary credentials. Đừng gọi AssumeRole thủ công cho mỗi API request.

### 17.4. Cross-Region không tự tạo DR

Đổi AWS_REGION từ ap-southeast-1 sang ap-northeast-1 không tạo bản sao dữ liệu, queues hoặc secrets. Phải thiết kế replication/backup, KMS key theo Region, endpoint, DNS, IAM resource ARNs và application config. Thử failover thực tế để chứng minh RTO/RPO.

## 18. Kiểm tra cấu hình và IAM identity bằng AWS CLI

Các lệnh dưới đây chủ yếu đọc metadata, không thay đổi tài nguyên. Chạy với profile/role của đúng môi trường; không in secret values hoặc credentials ra terminal log.

### 18.1. Kiểm tra caller identity và Region

~~~bash
aws sts get-caller-identity
aws configure list-profiles
aws configure get region --profile orders-dev
~~~

**get-caller-identity** cho biết Account, Arn và UserId thực tế. **configure list-profiles** chỉ liệt kê tên profiles; không in access keys. Lệnh kiểm tra Region từ profile không chứng minh ứng dụng Spring Boot đang dùng cùng Region nếu property source khác ghi đè.

### 18.2. Kiểm tra ECS task definition roles

~~~bash
aws ecs describe-task-definition \
  --task-definition orders-api \
  --query 'taskDefinition.{TaskRole:taskRoleArn,ExecutionRole:executionRoleArn,Family:family,Revision:revision}' \
  --output json
~~~

Đối chiếu TaskRoleArn và ExecutionRoleArn với policy đã review. Nếu task chạy trên ECS, kiểm tra thêm service/task đang dùng revision nào; task definition mới được tạo nhưng service chưa deploy thì workload vẫn có thể chạy revision cũ.

### 18.3. Kiểm tra EKS Pod Identity associations

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name orders-prod \
  --region ap-southeast-1 \
  --output json
~~~

Với IRSA, kiểm tra service account annotation, OIDC provider và trust policy của role. Danh sách Pod Identity associations không chứng minh Pod đã dùng đúng service account; xác minh Kubernetes Pod spec và runtime caller identity.

### 18.4. Kiểm tra secret metadata mà không đọc secret value

~~~bash
aws secretsmanager describe-secret \
  --region ap-southeast-1 \
  --secret-id orders/prod/database \
  --query '{Name:Name,Arn:ARN,KmsKey:KmsKeyId,RotationEnabled:RotationEnabled,LastRotated:LastRotatedDate}' \
  --output json
~~~

Không dùng get-secret-value trong kiểm toán thường ngày nếu không cần đọc password. Nếu phải kiểm thử quyền, thực hiện trong môi trường kiểm soát và không đưa SecretString vào terminal recording, CI output hoặc ticket.

### 18.5. Kiểm tra Parameter Store paths

~~~bash
aws ssm describe-parameters \
  --region ap-southeast-1 \
  --parameter-filters Key=Path,Option=Recursive,Values=/orders-api/prod/ \
  --query 'Parameters[].{Name:Name,Type:Type,Version:Version,LastModified:LastModifiedDate}' \
  --output table
~~~

Lệnh chỉ liệt kê metadata. Với SecureString, giá trị vẫn được bảo vệ; không dùng GetParameter --with-decryption để xuất giá trị nhạy cảm vào output nếu mục tiêu chỉ là kiểm tra path và quyền.

### 18.6. Mô phỏng IAM policy khi có quyền phù hợp

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::444455556666:role/orders-api-task-role \
  --action-names s3:GetObject sqs:SendMessage \
  --resource-arns arn:aws:s3:::orders-catalog-prod/sample.json arn:aws:sqs:ap-southeast-1:444455556666:orders-prod \
  --output json
~~~

Policy simulator giúp kiểm tra một số kết quả identity policy và điều kiện IAM. Nó không thay kiểm thử thực tế; resource policies, SCP, VPC endpoint policies, KMS key policies, network và service-specific behavior vẫn phải xem xét.

## 19. Kiểm thử cấu hình và IAM theo từng môi trường

Không nên đợi đến production mới phát hiện app dùng sai account hoặc role. Mỗi môi trường cần một bộ kiểm thử xác minh **profile, Region, resource names và caller identity**.

### 19.1. Unit test cho ConfigurationProperties

Kiểm tra validation bằng test context:

~~~java
import com.example.orders.config.AwsApplicationProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AwsApplicationPropertiesTest {
    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsRequiredProperties() {
        contextRunner
            .withPropertyValues(
                "app.aws.region=ap-southeast-1",
                "app.aws.catalog.bucket=orders-catalog-test",
                "app.aws.orders.queue-url=https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                AwsApplicationProperties properties =
                    context.getBean(AwsApplicationProperties.class);
                assertThat(properties.catalog().bucket())
                    .isEqualTo("orders-catalog-test");
            });
    }

    @EnableConfigurationProperties(AwsApplicationProperties.class)
    static class TestConfig {}
}
~~~

Test này xác minh binding và validation của non-secret properties. Không cần kết nối AWS thật cho unit test.

### 19.2. Test property precedence

Viết tests cho các trường hợp:

- application.yml có default bucket.
- application-dev.yml ghi đè bucket cho dev.
- APP_AWS_CATALOG_BUCKET ghi đè file config theo property source precedence.
- SPRING_PROFILES_ACTIVE chọn profile đúng.
- Thiếu queue URL bắt buộc làm startup fail.
- Secret import bắt buộc bị thiếu làm startup fail; optional secret được thiếu chỉ khi nghiệp vụ cho phép.

Không chỉ test happy path; kiểm tra sai profile hoặc Region có thể trỏ nhầm production resources.

### 19.3. Integration test với LocalStack

LocalStack có thể mô phỏng một số AWS services cho local integration tests. Dùng profile local riêng, endpoint override riêng và test credentials giả:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: us-east-1
      s3:
        endpoint: http://localhost:4566
~~~

~~~bash
SPRING_PROFILES_ACTIVE=local \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
AWS_REGION=us-east-1 \
java -jar orders-api.jar
~~~

Các credentials và endpoint này chỉ dành cho LocalStack/test. Không dùng chúng trong ECS/EKS/Lambda production. Không phải mọi IAM, STS, KMS hoặc service-specific semantics đều được mô phỏng hoàn toàn giống AWS; kiểm tra các luồng critical bằng AWS test account.

### 19.4. Smoke test IAM identity trong staging

Một smoke test có thể gọi STS GetCallerIdentity bằng cùng credentials provider mà ứng dụng dùng và kiểm tra:

- Account ID khớp account staging.
- ARN khớp role dự kiến.
- Region khớp môi trường.
- Đọc được đúng một test object hoặc gửi message vào test queue.
- Không truy cập được resource production nếu không được cấp.

Không ghi temporary credentials ra logs. Chỉ ghi account/role ARN cần thiết và che thông tin nhạy cảm trong telemetry.

## 20. Troubleshooting cấu hình và IAM role

Một lỗi AWS SDK thường là kết quả của nhiều lớp: Spring profile, property precedence, credentials provider, IAM authorization, Region, VPC network hoặc resource policy. Điều tra theo lớp giúp tránh cấp thêm quyền không cần thiết.

### 20.1. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| **Unable to load credentials from any provider** | Không có role/profile credentials, web identity token sai, metadata không truy cập được | Default chain, runtime role, AWS_PROFILE, ECS/EKS/EC2 credentials endpoint |
| **Ứng dụng dùng nhầm AWS account** | AWS_ACCESS_KEY_ID hoặc JVM system properties ghi đè role/profile | GetCallerIdentity từ đúng process, environment/system properties |
| **AccessDenied dù role đã gắn** | Policy thiếu action/resource, explicit Deny, SCP, boundary, resource policy | Caller ARN, action/resource, IAM evaluation và service policy |
| **ECS app không có quyền S3** | Gắn policy vào task execution role thay vì task role | taskRoleArn và executionRoleArn |
| **EKS Pod nhận node role** | Service account association/IRSA chưa đúng, Pod dùng sai service account | Pod spec, annotation/association, OIDC/Pod Identity Agent |
| **Lambda chạy local được nhưng production lỗi** | Local SSO profile có quyền rộng hơn execution role | Caller identity và execution role policy |
| **Parameter Store import lỗi khi startup** | Region/credentials chưa có ở bootstrap, path sai, thiếu ssm:GetParametersByPath | spring.config.import, AWS_REGION, task/pod role, VPC endpoint |
| **Secrets Manager import AccessDenied** | Role thiếu GetSecretValue hoặc secret/KMS policy chặn | Secret ARN, runtime role, KMS key policy |
| **KMS AccessDenied** | Secret SecureString/secret dùng customer-managed key nhưng role thiếu decrypt | KMS key ARN, kms:Decrypt, key policy/grants |
| **Profile prod không được active** | SPRING_PROFILES_ACTIVE sai hoặc bị property source khác ghi đè | Startup logs đã redaction, environment và command line |
| **Bucket/queue trỏ sai môi trường** | Environment variable ghi đè profile YAML hoặc file config mount cũ | Property source precedence và effective config đã redaction |
| **Invalid region / signing error** | app.aws.region, AWS_REGION và client Region không nhất quán | Region provider, service endpoint, ARN Region |
| **Timeout gọi AWS API** | VPC route, DNS, SG, NACL, NAT/VPC endpoint | Network path và endpoint DNS trước khi sửa IAM |
| **Secret rotation xong nhưng app vẫn dùng password cũ** | Bean/connection pool giữ giá trị đã bind lúc startup | Secret version, refresh/redeploy strategy, connection lifecycle |
| **Kubernetes Pod không assume role** | IRSA trust subject/audience sai hoặc Pod Identity association/agent thiếu | Service account, namespace, role trust policy, agent |
| **Cross-account AssumeRole bị từ chối** | Source role thiếu sts:AssumeRole hoặc target trust policy không cho phép | Hai phía trust/permissions và target role ARN |
| **LocalStack gọi được, AWS thật không được** | IAM, endpoint policy, KMS, service behavior khác local emulator | Integration test AWS staging và CloudTrail |

### 20.2. Quy trình điều tra nhanh

~~~mermaid
flowchart TD
    ERR["Spring Boot AWS call fails"] --> PROFILE{"Đúng profile/config?"}
    PROFILE -->|"Không"| CONFIG["Kiểm tra SPRING_PROFILES_ACTIVE,<br/>property precedence và config import"]
    PROFILE -->|"Có"| ID{"Đúng caller identity?"}
    ID -->|"Không"| CREDS["Kiểm tra default chain,<br/>runtime role, SSO, env keys"]
    ID -->|"Có"| REGION{"Đúng Region/endpoint?"}
    REGION -->|"Không"| REG["Kiểm tra AWS_REGION,<br/>spring.cloud.aws.region.static"]
    REGION -->|"Có"| NET{"Có network path?"}
    NET -->|"Không"| VPC["DNS, route, SG/NACL,<br/>NAT/VPC endpoint"]
    NET -->|"Có"| AUTH["IAM/resource/KMS policy<br/>và service error"]
    CONFIG --> FIX["Sửa nguyên nhân gốc<br/>và chạy smoke test"]
    CREDS --> FIX
    REG --> FIX
    VPC --> FIX
    AUTH --> FIX
~~~

### 20.3. Thứ tự kiểm tra thực tế

1. Xác nhận profile và application config đang được dùng, chỉ ghi giá trị không nhạy cảm.
2. Kiểm tra AWS caller identity từ chính runtime process hoặc cùng credentials provider.
3. Xác nhận Region và endpoint, đối chiếu resource ARN.
4. Kiểm tra network path tới service endpoint.
5. Kiểm tra IAM identity policy, trust policy, permissions boundary, SCP, resource policy và VPC endpoint policy.
6. Nếu resource mã hóa, kiểm tra KMS key policy/grants.
7. Kiểm tra service-specific conditions, tags, encryption context và data-plane permissions.
8. Sửa trong staging, chạy lại smoke tests và xác nhận không mở quyền quá rộng.

**Không phản ứng với mọi AccessDenied bằng cách gắn AdministratorAccess.** Lấy đúng action/resource/condition bị từ chối, tìm policy layer gây deny và cấp quyền tối thiểu.

## 21. Logging, metrics và audit

### 21.1. Những thông tin nên quan sát

| Signal | Mục tiêu |
|---|---|
| Active Spring profile | Phát hiện app chạy nhầm dev/staging/prod |
| AWS Region | Phát hiện endpoint/signing Region sai |
| Caller account/role ARN | Xác nhận runtime identity |
| AWS request ID/error code | Tương quan lỗi với AWS service |
| Secrets/Parameter import status | Phát hiện bootstrap failure và rotation |
| Application startup/readiness | Phát hiện config validation failure |
| Retry/throttling/latency | Phát hiện quota/network/dependency issues |
| Deployment revision/image digest | Tương quan config/role changes với release |

### 21.2. CloudTrail và application logs

CloudTrail ghi lại nhiều control-plane/data events tùy dịch vụ và cấu hình. Dùng CloudTrail để audit thay đổi IAM roles/policies, secret metadata, ECS/EKS resources và các API events được bật. Application logs nên ghi service operation, error code, request ID, account/role metadata đã duyệt và correlation ID.

Không giả định mọi lần credentials provider refresh, mọi lần Spring đọc environment variable hoặc mọi câu SQL đều được CloudTrail ghi lại. Dùng database/service-specific audit khi cần theo dõi data-plane actions.

### 21.3. Không expose Actuator nhạy cảm

Các endpoint như **env, configprops, heapdump, beans, mappings** có thể tiết lộ cấu hình, bean graph hoặc dữ liệu nhạy cảm. Chỉ expose qua management network được kiểm soát, bật authentication/authorization và che secret values. Không mở Actuator management endpoints công khai chỉ để tiện debug.

## 22. Bài tập tình huống

### Tình huống A — Profile prod nhưng AWS account là dev

Một ECS service có SPRING_PROFILES_ACTIVE=prod nhưng log caller identity cho thấy account dev. Container image không chứa access keys, nhưng task definition vẫn có AWS_ACCESS_KEY_ID từ một biến cũ.

**Câu hỏi:** vì sao task role production không được dùng?

**Gợi ý:** environment credentials nằm trước ECS container credentials trong default chain. Xóa biến credentials không cần thiết, xác minh taskRoleArn và kiểm tra GetCallerIdentity từ container sau khi deploy lại.

### Tình huống B — S3 AccessDenied trên ECS

Developer gắn s3:GetObject vào orders-api-execution-role. ECS task pull image và ghi CloudWatch logs thành công, nhưng Java code đọc object vẫn AccessDenied.

**Câu hỏi:** role nào cần policy đọc S3?

**Gợi ý:** application code cần quyền trên **task role**. Execution role phục vụ ECS agent. Kiểm tra taskRoleArn, policy resource ARN, bucket policy, KMS key nếu object SSE-KMS và VPC endpoint policy.

### Tình huống C — Spring Cloud AWS không đọc được secret lúc startup

Ứng dụng import aws-secretsmanager:orders/prod/database nhưng task ở private subnet không có NAT/VPC endpoint Secrets Manager. Context fail trước khi app sẵn sàng.

**Câu hỏi:** vì sao thêm bean SecretsManagerClient sau startup không sửa được?

**Gợi ý:** Config Data import được tải trong bootstrap, trước khi các application beans thông thường được tạo. Cần Region/credentials/network sẵn từ đầu, interface endpoint và task role GetSecretValue/KMS permissions.

### Tình huống D — EKS Pod dùng node role thay workload role

Pod orders-api cần đọc một bucket. Team đã tạo IAM role và gắn quyền nhưng deployment không khai báo serviceAccountName; Pod chạy bằng default service account.

**Câu hỏi:** cần xác minh gì?

**Gợi ý:** service account và namespace, IRSA annotation/OIDC trust hoặc EKS Pod Identity association/agent, role ARN và SDK version. Không cấp quyền bucket vào node role để chữa nhanh.

### Tình huống E — application-prod.yml chứa password

Một developer commit password database vào application-prod.yml trong private repository. Repo giới hạn thành viên nhưng đã có CI logs và artifact registry.

**Câu hỏi:** cần xử lý thế nào?

**Gợi ý:** xem credential đã lộ ở những nơi nào, rotate password/secret theo incident procedure, xóa khỏi source history/artifacts theo quy trình tổ chức, lưu current secret trong Secrets Manager và giới hạn GetSecretValue/KMS. Private repository không phải secret store.

### Tình huống F — Profile staging ghi đè nhầm production bucket

Một deployment production có SPRING_PROFILES_ACTIVE=prod nhưng biến APP_AWS_CATALOG_BUCKET còn sót giá trị orders-catalog-staging. App vẫn startup thành công và ghi nhầm dữ liệu.

**Câu hỏi:** làm sao ngăn lỗi này?

**Gợi ý:** validate bucket/account/Region theo môi trường, đặt allowlist/expected resource identifiers, log effective non-secret config, smoke test trước traffic và kiểm tra property source precedence. Không chỉ tin profile name.

### Tình huống G — IAM role đúng nhưng Parameter Store vẫn AccessDenied

Task role có ssm:GetParameter nhưng ứng dụng import path /orders-api/prod/ bằng GetParametersByPath. SecureString dùng customer-managed KMS key.

**Câu hỏi:** quyền nào có thể thiếu?

**Gợi ý:** API có thể cần ssm:GetParametersByPath trên đúng parameter ARNs/path, và kms:Decrypt trên key cùng key policy. Kiểm tra action thực tế mà config loader gọi; không thêm ssm:*.

### Tình huống H — Secret rotate nhưng application vẫn dùng password cũ

Secrets Manager đã rotate DB password, nhưng Spring bean DataSource bind password ở startup và connection pool vẫn tạo connections mới bằng giá trị cũ.

**Câu hỏi:** cần thiết kế refresh thế nào?

**Gợi ý:** chọn controlled redeploy/restart, framework reload đã cấu hình hoặc secret provider refresh khi tạo physical connection. Xác minh pool eviction/connection lifetime và rotation stages; không giả định Environment tự cập nhật bean.

### Tình huống I — CI pipeline có quyền production database

CI role dùng chung với ECS task role. Build pipeline có thể đọc production database secrets dù chỉ cần deploy container.

**Câu hỏi:** tách identity ra sao?

**Gợi ý:** CI dùng OIDC deploy role với quyền ECR/ECS/EKS/Lambda và iam:PassRole giới hạn; runtime dùng task/pod/Lambda role với quyền business. Không đưa production secrets vào build pipeline.

### Tình huống J — Local chạy được nhưng Lambda AccessDenied

Developer dùng SSO profile có quyền rộng; Lambda execution role chỉ có quyền S3 đọc một prefix, nhưng code gọi thêm s3:ListBucket và KMS decrypt.

**Câu hỏi:** vì sao unit/integration local không phát hiện?

**Gợi ý:** local identity khác production identity. Bổ sung staging tests với role tương đương production, cấp đúng ListBucket condition/prefix và KMS permission nếu use case cần; không mở quyền rộng theo profile developer.

### Tình huống K — Cross-account AssumeRole thất bại

Orders API trong account A có sts:AssumeRole trên target role ARN ở account B, nhưng target role trust policy chỉ cho phép một CI role khác.

**Câu hỏi:** sửa ở đâu?

**Gợi ý:** source permissions và target trust policy đều phải cho phép source runtime role. Xác minh session tags/external ID/conditions nếu có; sau AssumeRole, target role vẫn phải có quyền resource đích.

### Tình huống L — Secret import optional che mất lỗi production

DB password được khai báo optional để ứng dụng vẫn startup khi Secrets Manager lỗi. Service trở thành healthy nhưng mọi request database đều 500.

**Câu hỏi:** nên dùng optional ở đâu?

**Gợi ý:** optional chỉ cho integration thực sự không bắt buộc. DB credentials production là cấu hình bắt buộc; fail-fast hoặc readiness degraded có kiểm soát tốt hơn việc nhận traffic khi không thể phục vụ.

## 23. Checklist production

- [ ] Một artifact có thể chạy ở dev, test, staging và prod; profile được chọn bởi deployment environment.
- [ ] application.yml chỉ giữ defaults và cấu hình không nhạy cảm.
- [ ] Profile files chỉ ghi các khác biệt cần thiết; không chứa AWS access keys, DB passwords hoặc API tokens.
- [ ] Property precedence đã được kiểm thử; environment variables/command-line overrides không thể vô tình trỏ tới tài nguyên khác.
- [ ] spring.profiles.active không được khai báo trong profile-specific documents.
- [ ] Cấu hình được bind bằng @ConfigurationProperties và validate ở startup.
- [ ] Các giá trị bắt buộc như Region, bucket, queue URL và endpoint được kiểm tra theo môi trường.
- [ ] Đã chọn đúng Spring Cloud AWS BOM/version tương thích với Spring Boot và AWS SDK.
- [ ] Chỉ thêm các Spring Cloud AWS starters mà ứng dụng thực sự dùng.
- [ ] Config Data imports có Region, credentials và network path sẵn ở bootstrap.
- [ ] Secret bắt buộc không bị đánh dấu optional; secret không xuất hiện trong logs/Actuator public endpoints.
- [ ] Local development dùng IAM Identity Center/SSO profile hoặc cơ chế được phê duyệt; không dùng production access keys.
- [ ] Production sử dụng IAM roles/temporary credentials qua runtime credential provider chain.
- [ ] Không có AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY hoặc JVM static credentials ngoài ý muốn trong production container.
- [ ] ECS task role cấp quyền cho application; task execution role chỉ phục vụ ECS agent.
- [ ] EKS workload có service account/Pod Identity association hoặc IRSA trust policy đúng namespace và account.
- [ ] Lambda execution role và EC2 instance profile có quyền tối thiểu; EC2 IMDSv2 được bật.
- [ ] CI/CD deploy role tách khỏi runtime role; OIDC federation và iam:PassRole được giới hạn.
- [ ] Trust policy và permissions policy được review riêng; resource ARNs và conditions cụ thể.
- [ ] AWS_REGION, Spring Cloud AWS Region và app.aws.region không mâu thuẫn.
- [ ] Multi-Region/multi-account clients có endpoint, signing Region, resource ARN và KMS plan rõ ràng.
- [ ] VPC route, DNS, SG/NACL, NAT/VPC endpoints và endpoint policies được kiểm thử từ private runtime.
- [ ] Secret rotation có kế hoạch refresh/redeploy cho beans, DataSource và connection pools.
- [ ] Health/readiness phân biệt cấu hình bắt buộc, liveness và dependency availability.
- [ ] Logs ghi profile/Region/caller identity metadata đã duyệt, không ghi credential/token/SecretString.
- [ ] CloudTrail, application metrics và alarms đủ để audit IAM/secret/config changes và phát hiện AccessDenied.
- [ ] Staging smoke test xác nhận caller account/role, Region, S3/SQS/DynamoDB permissions và không truy cập tài nguyên production ngoài ý muốn.
- [ ] Đã thử rollback, secret rotation, task/pod replacement, failover và cross-account access.
- [ ] Đã có runbook xử lý sai profile, credentials chain, AccessDenied, KMS, VPC endpoint và config import failures.

## 24. Ghi nhớ

**Spring profile chọn cấu hình ứng dụng; IAM role xác định danh tính AWS của tiến trình.** Hai khái niệm độc lập. Một file JAR nên được triển khai qua nhiều môi trường bằng application defaults, profile-specific non-secret settings và externalized configuration. Secrets nằm trong Secrets Manager hoặc secret store phù hợp; AWS API permissions nằm trong IAM policies.

Trong local development, dùng IAM Identity Center/SSO profile. Trong production, để runtime cấp temporary credentials: **ECS task role** cho application container, **EKS Pod Identity/IRSA** cho Kubernetes service account, **Lambda execution role** cho function và **EC2 instance profile** cho EC2 workload. Nhớ phân biệt ECS task role với task execution role và kiểm tra thứ tự default credentials provider chain vì environment credentials có thể che runtime role.

Với Spring Boot, dùng **@ConfigurationProperties + validation**, chọn profile từ deployment environment, quản lý Region nhất quán và sử dụng Spring Cloud AWS Parameter Store/Secrets Manager Config Data imports khi cần. Import xảy ra ở bootstrap; secret rotation không tự bảo đảm mọi bean đang chạy được refresh. Cuối cùng, kiểm chứng **IAM, resource policies, KMS, VPC endpoints, health checks, logs, CI/CD identity và rollback** trong staging trước khi production nhận traffic.

### Tài liệu chính thức để đối chiếu

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — property sources, environment variables và config locations.
- [Spring Boot Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — active profiles và profile-specific configuration.
- [AWS SDK for Java 2.x Default Credentials Provider Chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — thứ tự credentials providers.
- [AWS SDK for Java 2.x Credentials Providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html) — profile, SSO, web identity và role credentials.
- [AWS SDK for Java 2.x IAM Identity Center setup](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html) — cấu hình SSO profile và modules sso/ssooidc.
- [AWS SDK for Java 2.x Troubleshooting](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html) — credentials chain, STS module và network errors.
- [Amazon ECS Task IAM Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) — application credentials trong container.
- [Amazon ECS Task Execution IAM Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) — quyền của ECS/Fargate agent.
- [Best Practices for IAM Roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) — tách roles và least privilege.
- [IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — OIDC và workload identity trên EKS.
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — associations, agent và credentials.
- [Spring Cloud AWS 3.4.2 Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html) — starters, Region/credentials auto-configuration và integrations.
- [Spring Cloud AWS Version Compatibility](https://github.com/awspring/spring-cloud-aws) — Spring Boot/Spring Cloud release matrix.
- [Spring Cloud AWS Parameter Store Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html#parameter-store-integration) — Config Data import.
- [Spring Cloud AWS Secrets Manager Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html#secrets-manager-integration) — secrets as Spring properties.
- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) — parameters, SecureString và IAM.
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) — secret lifecycle và rotation.
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — roles, temporary credentials và least privilege.
- [AWS STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — xác minh caller account/ARN.
