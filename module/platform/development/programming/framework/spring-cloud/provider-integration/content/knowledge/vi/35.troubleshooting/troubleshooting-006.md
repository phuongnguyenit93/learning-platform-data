# Nguồn cấu hình không nạp hoặc bí mật xoay vòng chưa có hiệu lực

Spring Boot có thể khởi động thành công nhưng vẫn dùng endpoint, feature flag, database password hoặc API key cũ. Một trường hợp khác là ứng dụng báo thiếu property dù giá trị đã tồn tại trong AWS Systems Manager Parameter Store, AWS Secrets Manager, Azure Key Vault hoặc Google Cloud Secret Manager.

Để chẩn đoán đúng, hãy tách ba giai đoạn:

1. **Nạp nguồn cấu hình:** Spring Boot có tìm thấy file, profile, import hoặc remote PropertySource hay không?
2. **Chọn giá trị hiệu lực:** khi nhiều PropertySource cùng khai báo một key, nguồn nào có độ ưu tiên cao hơn?
3. **Áp dụng giá trị mới:** bean, SDK client, connection pool và các replica có thực sự nhận cấu hình sau khi secret được cập nhật hay không?

Việc tạo secret version mới ở secret store chỉ hoàn tất bước cập nhật phía nhà cung cấp. Nó không tự bảo đảm Spring Environment đã đọc lại, singleton bean đã được tạo lại hoặc connection pool đã mở kết nối bằng thông tin mới.

Bài này hướng dẫn kiểm tra externalized configuration của Spring Boot, cách nạp Parameter Store/Secrets Manager/Key Vault/Secret Manager, cơ chế refresh theo từng provider, và quy trình xoay vòng credentials có thể kiểm chứng trong production. Phạm vi ví dụ là ứng dụng Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud.

## 1. Nhận diện lỗi nằm ở giai đoạn nào

| Triệu chứng | Giai đoạn cần kiểm tra trước | Nguyên nhân thường gặp |
| --- | --- | --- |
| Placeholder không resolve được khi startup | Nạp nguồn cấu hình | Thiếu starter, sai spring.config.import, sai profile, path hoặc endpoint |
| Ứng dụng dùng giá trị trong application.yml thay vì secret store | Chọn giá trị hiệu lực | PropertySource ưu tiên cao hơn đang ghi đè key |
| Secret store có version mới nhưng log nghiệp vụ vẫn cho thấy kết nối cũ | Áp dụng giá trị | Reload bị tắt, polling chưa tới kỳ, bean không refresh hoặc cache cũ |
| Một số pod dùng secret mới, số khác dùng secret cũ | Đồng bộ replica | Rolling update chưa xong, cache theo process hoặc một số pod không đọc được nguồn |
| Refresh báo thành công nhưng kết nối DB vẫn lỗi | Tài nguyên giữ state | DataSource/connection pool/SDK client đã được tạo với credential cũ |
| Secret bị thiếu và ứng dụng vẫn chạy với mật khẩu mặc định | Nạp nguồn cấu hình | Dùng optional import cho secret bắt buộc hoặc placeholder có default |
| Secret vừa rotate xong thì toàn bộ instance mất kết nối | Quy trình rotation | Credential cũ bị vô hiệu hóa trước khi workload chuyển sang credential mới |
| Giá trị Key Vault/Secret Manager đúng nhưng ứng dụng đọc sai | Mapping và binding | Tên secret không ánh xạ thành property key mong muốn, profile hoặc project sai |

Không bắt đầu bằng việc ghi lại secret để so sánh. Trước tiên xác định tên PropertySource, property origin, profile, version ID và thời điểm cập nhật. Giá trị bí mật chỉ được đọc trong luồng xử lý cần thiết và không xuất hiện trong log.

## 2. Spring Boot nạp và chọn cấu hình như thế nào?

### 2.1. Các nguồn cấu hình phổ biến

Spring Boot có thể lấy property từ:

- Default properties do ứng dụng khai báo.
- application.properties hoặc application.yml trong classpath.
- File cấu hình bên ngoài JAR.
- File theo profile như application-prod.yml.
- spring.config.import từ file, configuration tree hoặc integration được thư viện bổ sung.
- OS environment variables.
- JVM system properties.
- SPRING_APPLICATION_JSON.
- Command-line arguments.
- Các PropertySource được thêm bởi framework hoặc thư viện tích hợp.

Thứ tự cụ thể được Spring Boot định nghĩa; các nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn. Trong các môi trường triển khai thông dụng, environment variable, system property và command-line argument có thể ghi đè property lấy từ config data hoặc secret store.

Ví dụ secret store trả về:

- spring.datasource.username=orders_app
- spring.datasource.password=<secret value>

Nhưng container vẫn có biến SPRING_DATASOURCE_PASSWORD cũ. Spring Environment có thể tiếp tục chọn biến môi trường. Secret store đã cập nhật đúng nhưng ứng dụng vẫn dùng giá trị cũ vì nguồn cấu hình ưu tiên cao hơn.

### 2.2. Profile quyết định file và nguồn nào được nạp

Kiểm tra profile mà process thực sự đang chạy:

```bash
printenv SPRING_PROFILES_ACTIVE
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE
```

Nếu cấu hình theo profile:

```yaml
spring:
  profiles:
    active: prod
```

Spring Boot có thể nạp application-prod.yml và các biến thể profile của config locations/import. Kiểm tra profile của từng pod hoặc từng deployment revision; không dựa vào profile trong máy local.

Một file có thể được nạp đúng nhưng document bên trong có điều kiện spring.config.activate.on-profile không khớp. Khi đó phần cấu hình được mong đợi không xuất hiện trong Environment.

### 2.3. spring.config.import và optional

Spring Boot hỗ trợ import thêm config data:

```yaml
spring:
  config:
    import:
      - optional:file:/etc/orders/application-secrets.yml
      - configtree:/run/secrets/
```

- file: đọc file cấu hình cụ thể.
- configtree: ánh xạ tên file trong thư mục thành property key; nội dung file là giá trị.
- optional: cho phép ứng dụng tiếp tục khởi động nếu location không tồn tại.

optional phù hợp với cấu hình thực sự không bắt buộc. Nếu database password hoặc signing key là bắt buộc, không đánh dấu import đó là optional. Nếu secret store không truy cập được, startup nên thất bại rõ ràng thay vì dùng giá trị mặc định không còn hợp lệ.

Ví dụ mount secret thành các file:

```text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
```

Nạp vào Spring Environment:

```yaml
spring:
  config:
    import: configtree:/run/secrets/
```

Giá trị trong file có thể được bind theo property name tương ứng. Cách này hữu ích với Kubernetes Secret volume, Docker Secret hoặc volume mount do nền tảng triển khai quản lý.

### 2.4. Phân biệt spring.config.location và spring.config.additional-location

Đây là nguyên nhân phổ biến khiến file cấu hình mặc định biến mất:

- spring.config.location thay thế các location mặc định mà Spring Boot tìm kiếm.
- spring.config.additional-location bổ sung location mới vào các location mặc định.

Nếu deployment đặt SPRING_CONFIG_LOCATION=/etc/orders/, ứng dụng có thể không còn nạp file mặc định trong classpath như nhóm phát triển dự kiến. Nếu chỉ muốn thêm file cấu hình bên ngoài, kiểm tra có nên dùng spring.config.additional-location hay không.

Hai property này được đọc rất sớm trong quá trình bootstrap; cần truyền qua environment variable, system property hoặc command-line argument.

### 2.5. Property name và environment variable

Spring Boot hỗ trợ relaxed binding. Ví dụ:

| Property key | Environment variable |
| --- | --- |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.datasource.username | SPRING_DATASOURCE_USERNAME |
| spring.datasource.password | SPRING_DATASOURCE_PASSWORD |
| app.cloud.api-key | APP_CLOUD_APIKEY theo quy tắc chuẩn hóa tên biến môi trường |

Khi secret store có key dạng dấu chấm nhưng deployment lại khai báo biến môi trường với cách viết khác, cần kiểm tra quy tắc binding và PropertySource thực tế. Đừng giả định tên trong Key Vault, Parameter Store hoặc Secret Manager luôn được ánh xạ giống nhau giữa các integration.

### 2.6. Giá trị được nạp không có nghĩa bean tự thay đổi

Ví dụ:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentGateway {

    private final String apiKey;

    public PaymentGateway(@Value("${app.payment.api-key}") String apiKey) {
        this.apiKey = apiKey;
    }
}
```

Trong ứng dụng thực tế, apiKey có thể được bind từ cấu hình khi bean được tạo. Nếu secret store thay đổi sau đó, field của singleton bean không tự được gán lại chỉ vì Spring Environment có giá trị mới.

Với cấu hình nhiều trường, dùng ConfigurationProperties:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;
    private String apiKey;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
```

Đảm bảo lớp này được đăng ký bằng ConfigurationPropertiesScan hoặc EnableConfigurationProperties. Chỉ thêm annotation trên class mà không scan/enable class không làm bean tự xuất hiện trong application context.

Để bean nhận thay đổi sau refresh, cần cơ chế refresh/rebind phù hợp. Nếu bean tạo SDK client hoặc connection pool từ các property này, bản thân tài nguyên đó cũng phải được tái tạo hoặc cập nhật an toàn.

## 3. Quy trình kiểm tra nguồn cấu hình hiệu lực

Thực hiện theo thứ tự sau trong đúng container, pod hoặc VM đang có lỗi.

### Bước 1 — Xác nhận deployment revision và profile

Ghi nhận:

- Tên service, namespace, pod/container và image version.
- Active profile.
- Thời điểm process khởi động.
- Các biến SPRING_CONFIG_* và SPRING_PROFILES_ACTIVE có tên liên quan.
- Secret reference/version ID mà deployment dự kiến sử dụng.

Không in toàn bộ environment của process vì có thể chứa token, password hoặc connection string.

### Bước 2 — Kiểm tra dependency và config import

Xác nhận starter tương ứng có trong runtime classpath và đúng release line. Một dependency chỉ có trong test scope không giúp ứng dụng production nạp remote configuration.

Đọc spring.config.import từ file cấu hình và xác minh scheme, path, region/project/endpoint. Nếu import không tồn tại, ứng dụng có thể không nạp PropertySource dù SDK client khác trong ứng dụng vẫn hoạt động.

### Bước 3 — Xác minh tên PropertySource và property origin

Dùng Spring Environment để kiểm tra property có được tìm thấy và nguồn nào cung cấp key. Ví dụ sau chỉ in tên nguồn và trạng thái có/không; không in giá trị:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationOriginProbe implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigurationOriginProbe.class);

    private final ConfigurableEnvironment environment;

    public ConfigurationOriginProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "spring.datasource.password";

        for (PropertySource<?> source : environment.getPropertySources()) {
            if (source.containsProperty(key)) {
                log.info("Property {} is present in source {}",
                        key, source.getName());
            }
        }

        log.info("Property {} resolved={}",
                key, environment.containsProperty(key));
    }
}
```

Đoạn code trên có thể hiển thị nhiều nguồn cùng chứa một key. Nguồn được duyệt trước theo thứ tự của Environment có ưu tiên cao hơn. Nếu cần biết origin của một giá trị cấu hình do Spring Boot quản lý, có thể dùng metadata/origin support tương ứng với phiên bản Boot.

Không log environment.getProperty(key) với key là secret. Không bật chế độ hiển thị toàn bộ giá trị của Actuator env hoặc configprops trên endpoint công khai.

### Bước 4 — Kiểm tra binding và bean lifecycle

Kiểm tra:

- ConfigurationProperties có được scan/enable hay không.
- Prefix và tên field có khớp property key không.
- Bean đã được tạo trước khi remote PropertySource nạp chưa.
- Bean có thuộc RefreshScope hoặc cơ chế rebind không.
- Bean phụ thuộc có được tạo lại khi dependency thay đổi không.
- SDK client, DataSource, connection pool hoặc HTTP client có cache credential riêng không.

Một property xuất hiện trong Environment nhưng field của bean vẫn cũ thường là vấn đề lifecycle/refresh, không phải lỗi tải secret.

### Bước 5 — So sánh tất cả replica

Với deployment nhiều replica, kiểm tra từng instance:

- Pod có cùng image/config revision không?
- Secret version được đọc có giống nhau không?
- Polling/reload đã chạy trên tất cả replica chưa?
- Một pod có biến môi trường override khác không?
- Có pod nào không có quyền đọc secret hoặc không tới được private endpoint không?

Chỉ kết luận rotation thành công khi tất cả replica phục vụ traffic đều dùng cấu hình mới và thao tác thật tới dịch vụ đích thành công.

## 4. AWS: Parameter Store và Secrets Manager

### 4.1. Chọn đúng integration và starter

Spring Cloud AWS 3.x cung cấp các starter riêng:

```xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-parameter-store</artifactId>
</dependency>

<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
</dependency>
```

Quản lý version bằng Spring Cloud AWS BOM. Kiểm tra dependency nằm trong runtime classpath và không trộn property cũ của Spring Cloud AWS 2.x với scheme/configuration của 3.x.

### 4.2. Nạp cấu hình từ Parameter Store

Giả sử Parameter Store có path:

```text
/config/orders-api/database/username
/config/orders-api/database/password
/config/orders-api/payment/timeout
```

Nạp path vào Spring Environment:

```yaml
spring:
  application:
    name: orders-api
  config:
    import: aws-parameterstore:/config/orders-api/
```

Parameter Store integration lấy các parameter trong path được chỉ định và thêm chúng vào Environment. Nếu path bắt buộc không tồn tại hoặc SDK không đọc được path, ứng dụng có thể thất bại khi startup.

Chỉ dùng optional:aws-parameterstore: khi path thực sự không bắt buộc. Nếu password là bắt buộc, bỏ optional để lỗi cấu hình không bị che khuất.

Đối với dữ liệu nhạy cảm, dùng Parameter Store SecureString. Giá trị được mã hóa bằng AWS KMS; nếu dùng customer managed key, principal đọc parameter còn cần quyền decrypt phù hợp trên key. Không lưu secret trong String hoặc StringList.

### 4.3. Nạp cấu hình từ Secrets Manager

Giả sử secret JSON có các key url, username, password. Có thể thêm prefix để tránh xung đột:

```yaml
spring:
  config:
    import: "aws-secretsmanager:/secrets/prod/orders-db?prefix=spring.datasource."
```

Các property được ánh xạ thành:

- spring.datasource.url
- spring.datasource.username
- spring.datasource.password

Nếu key trong JSON không khớp property mong muốn, kiểm tra secret structure, prefix và import URI. Nếu secret là plain text, integration cũng có thể nạp giá trị theo tên secret; cần đối chiếu định dạng secret và cách mapping trong release đang dùng.

SecretsManagerClient do starter auto-configure có thể được dùng để đọc secret theo cách imperative. Khi tự gọi client, hãy xác định rõ secret ARN/name, region và credential provider.

### 4.4. Kiểm tra IAM và KMS

Quyền thường cần:

| Nguồn | Permission cần kiểm tra |
| --- | --- |
| Secrets Manager | secretsmanager:GetSecretValue |
| Parameter Store | ssm:GetParametersByPath hoặc action đọc parameter tương ứng với cách gọi |
| SecureString dùng customer managed KMS key | kms:Decrypt trên key phù hợp |

Kiểm tra resource ARN, account, region, path và key policy. Có thể ứng dụng đọc được một parameter nhưng không đọc được parameter khác do IAM path restriction hoặc KMS key khác nhau.

Xác minh bằng AWS CLI trong cùng profile/role với ứng dụng:

```bash
aws sts get-caller-identity
aws ssm get-parameter --name /config/orders-api/database/username
aws secretsmanager describe-secret --secret-id /secrets/prod/orders-db
```

Không dùng lệnh get-secret-value theo cách đưa payload ra terminal/log trong ticket. Khi cần xác minh giá trị, hãy kiểm tra version ID, timestamp, trạng thái hoặc checksum được thiết kế riêng mà không tiết lộ nội dung bí mật.

### 4.5. PropertySource reload của Spring Cloud AWS

Reload cho Secrets Manager và Parameter Store **tắt mặc định**. Chỉ có spring.config.import thì ứng dụng nạp giá trị khi bootstrap; nó không có nghĩa secret sẽ được poll liên tục.

Để bật reload, cấu hình strategy và thêm các dependency mà Spring Cloud AWS yêu cầu:

```xml
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
```

Ví dụ cho Secrets Manager:

```yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: refresh
          period: 30s
```

Ví dụ cho Parameter Store:

```yaml
spring:
  cloud:
    aws:
      parameterstore:
        reload:
          strategy: refresh
          period: 30s
```

Các strategy:

- refresh: làm mới configuration bean có ConfigurationProperties hoặc RefreshScope theo Spring Cloud Context.
- restart_context: khởi động lại Spring ApplicationContext một cách graceful và tạo lại bean.

Với restart_context, phải bật và expose Actuator restart endpoint theo tài liệu phiên bản đang dùng. Endpoint này cần được giới hạn ở management network và bảo vệ bằng xác thực/ủy quyền; không đưa endpoint restart ra public ingress.

Đặt period tường minh theo yêu cầu vận hành và kiểm tra đúng property của release line. Polling nhanh làm tăng số lần gọi API và chi phí; polling chậm làm tăng thời gian ứng dụng giữ giá trị cũ.

### 4.6. AWS Secrets Manager Java cache

Nếu ứng dụng dùng AWS Secrets Manager Java caching component thay vì chỉ dùng Spring PropertySource, cache có chu kỳ refresh riêng. Tài liệu cache Java mô tả mặc định refresh mỗi giờ; cache không có cơ chế invalidation tức thời.

Vì vậy, sau khi đổi secret:

- Kiểm tra cache TTL/refresh interval.
- Kiểm tra ứng dụng có giữ reference tới giá trị cache cũ không.
- Kiểm tra provider/client có đọc lại cache hay không.
- Nếu cần đổi ngay, dùng cơ chế cập nhật cache/client được hỗ trợ hoặc rollout process có kiểm soát.

Không nhầm polling của Spring Cloud AWS PropertySource với TTL của một cache Secrets Manager tự thêm trong service.

## 5. Azure: Spring Cloud Azure và Key Vault PropertySource

### 5.1. Nạp secret từ Key Vault

Thêm starter:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
</dependency>
```

Ví dụ khai báo Key Vault PropertySource:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: orders-key-vault
              endpoint: https://orders-prod.vault.azure.net/
              secret-keys:
                - spring-datasource-url
                - spring-datasource-username
                - spring-datasource-password
              refresh-interval: 5m
```

Tên secret của Key Vault chỉ hỗ trợ một số ký tự, vì vậy dấu chấm trong property key thường được biểu diễn bằng dấu gạch nối. Ví dụ spring-datasource-password được ánh xạ thành property spring.datasource.password.

Dùng secret-keys để chỉ lấy các secret ứng dụng cần thay vì tải toàn bộ secret trong vault. Kiểm tra tên secret, case sensitivity và mapping trước khi kết luận Key Vault không trả dữ liệu.

### 5.2. Kiểm tra PropertySource priority

Spring Cloud Azure Key Vault PropertySource có thứ tự ưu tiên riêng. Theo tài liệu hiện hành:

- Nếu có SystemEnvironmentPropertySource, environment variable có ưu tiên cao hơn Key Vault PropertySource.
- Nếu có nhiều Key Vault PropertySource, thứ tự khai báo quyết định nguồn ưu tiên.

Ví dụ Key Vault đã cập nhật password mới nhưng deployment vẫn có SPRING_DATASOURCE_PASSWORD cũ. Spring có thể tiếp tục dùng environment variable. Hãy kiểm tra cấu hình của Deployment/Helm/Container App/App Service và xóa override cũ nếu không còn cần thiết.

Không in giá trị biến môi trường để điều tra. Chỉ kiểm tra biến có tồn tại, nguồn cấu hình và thời điểm deployment đã thay đổi.

### 5.3. Refresh interval của Key Vault

KeyVaultPropertySource mặc định refresh mỗi 30 phút. Có thể thay bằng property:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: orders-key-vault
              endpoint: https://orders-prod.vault.azure.net/
              refresh-interval: 5m
```

Đặt refresh-interval: 0 sẽ tắt auto refresh. Nếu ứng dụng vẫn dùng giá trị cũ, kiểm tra:

1. Property source có được enable không?
2. Refresh interval có bị đặt bằng 0 hoặc quá dài không?
3. Process có quyền đọc secret version mới không?
4. Environment variable có ghi đè không?
5. Bean/client dùng property có được cập nhật không?

Refresh PropertySource và refresh tài nguyên đang giữ state là hai việc cần xác minh riêng. Không giả định rằng field Value, SDK client, DataSource hoặc connection pool đã tự thay đổi chỉ vì Key Vault PropertySource đọc được version mới.

### 5.4. Kiểm tra quyền và trạng thái secret

Với Microsoft Entra ID, xác minh:

- Principal thực tế của workload (managed identity/service principal).
- Quyền đọc secret trên đúng Key Vault.
- Key Vault đang dùng mô hình Azure RBAC hay access policy.
- Secret version mới có được enable không.
- Secret có hết hạn, bị disabled hoặc đang ở vault khác không.
- Endpoint và tenant của ứng dụng có đúng không.

Role data-plane thường dùng là Key Vault Secrets User hoặc quyền hẹp hơn đáp ứng thao tác đọc. Quyền Contributor ở subscription không thay thế quyền đọc secret data-plane.

Nếu dùng Azure CLI để kiểm tra, bảo đảm CLI identity là principal phù hợp. CLI user có quyền không chứng minh managed identity của Java process cũng có quyền.

### 5.5. Khi dùng SecretClient trực tiếp

Nếu ứng dụng gọi Azure Key Vault SDK trực tiếp, kiểm tra rõ tên và version secret. SecretClient có thể đọc phiên bản hiện hành bằng tên secret; nếu code truyền version cụ thể, nó sẽ tiếp tục đọc đúng version đó dù đã tạo version mới.

Khi secret thay đổi, kiểm tra client có gọi lại getSecret hay chỉ giữ KeyVaultSecret/giá trị đã đọc trong singleton bean hoặc cache nội bộ.

## 6. Google Cloud: Secret Manager và Secret Version

### 6.1. Secret Manager lưu version bất biến

Google Cloud Secret Manager không ghi đè payload của một version đã tồn tại. Khi xoay vòng, tạo secret version mới. Secret có thể có nhiều version với trạng thái enabled, disabled hoặc destroyed.

Alias latest trỏ tới version mới nhất được tạo. Nó thuận tiện cho phát triển nhưng có thể rollout một giá trị lỗi tới toàn bộ workload. Tài liệu Google khuyến nghị production cân nhắc pin version ID và triển khai qua release process để có thể rollout/rollback có kiểm soát.

### 6.2. Xác minh project, identity và IAM

Kiểm tra project đang được Java client sử dụng, service account/Workload Identity của workload và API Secret Manager đã enable.

Permission đọc version thường cần là secretmanager.versions.access. Role có sẵn thường dùng là roles/secretmanager.secretAccessor, nên cấp ở scope secret nếu có thể thay vì cấp toàn project.

Với Compute Engine hoặc GKE, kiểm tra OAuth access scope của VM/node nếu môi trường còn áp dụng scope; Secret Manager cần cloud-platform scope. Với GKE Workload Identity hoặc external workload identity, xác minh federation binding và principal đúng.

### 6.3. Đọc secret version bằng Java

Ví dụ dùng Google Cloud Secret Manager Java Client:

```java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public byte[] loadSecret(
        SecretManagerServiceClient client,
        String projectId,
        String secretId,
        String versionId) {

    SecretVersionName name =
            SecretVersionName.of(projectId, secretId, versionId);

    AccessSecretVersionResponse response =
            client.accessSecretVersion(name);

    return response.getPayload().getData().toByteArray();
}
```

Truyền version ID cụ thể, ví dụ 12, khi muốn triển khai theo version đã được phê duyệt. Dùng latest chỉ khi chính sách ứng dụng chấp nhận nhận version mới nhất mỗi lần đọc. Không in payload ra log hoặc console.

Tạo SecretManagerServiceClient một lần trong lifecycle của ứng dụng và tái sử dụng cho các lần truy cập; đóng client khi ứng dụng dừng. Không tạo client mới cho mỗi request.

Nếu code chỉ đọc secret một lần lúc startup rồi giữ byte array/string trong bean, việc thêm version mới không thay nội dung đã nạp. Cần đọc lại theo lịch/event hoặc triển khai lại process.

### 6.4. Dùng Pub/Sub notification để điều phối rotation

Secret Manager có thể publish event tới Pub/Sub topic khi secret hoặc version thay đổi. Một số event:

- SECRET_VERSION_ADD
- SECRET_VERSION_ENABLE
- SECRET_VERSION_DISABLE
- SECRET_VERSION_DESTROY
- SECRET_ROTATE

Notification không tự cập nhật Spring bean. Ứng dụng hoặc workflow subscriber phải nhận event, xác định secret/version bị thay đổi, kiểm tra trạng thái và quyết định refresh, restart hoặc rollout deployment.

Đối với rotation schedule, SECRET_ROTATE là tín hiệu để workflow thực hiện các bước xoay vòng. Nó không tự tạo credential mới ở database/API đích và không tự cập nhật tất cả ứng dụng đang dùng secret.

Một workflow có thể thực hiện:

1. Nhận event từ Pub/Sub.
2. Tạo credential mới ở hệ thống đích trong khi credential cũ vẫn còn hiệu lực.
3. Thêm version mới vào Secret Manager.
4. Triển khai version mới theo rollout strategy hoặc phát tín hiệu refresh có kiểm soát.
5. Kiểm tra mọi replica đã dùng version mới và kết nối thành công.
6. Thu hồi credential cũ sau khi không còn workload dùng nó.

### 6.5. Spring Cloud Config Server backend cho Google Secret Manager

Nếu kiến trúc đã dùng Spring Cloud Config Server, có thể cấu hình backend Google Secret Manager của Config Server. Backend này cần Spring profile secret-manager và thư viện google-cloud-secretmanager trên classpath của Config Server.

Đây là integration ở **Config Server**, khác với việc chỉ thêm Google Cloud Secret Manager Java Client vào một ứng dụng Spring Boot thông thường. Khi dùng backend này, Config Server tạo PropertySource từ secret payload theo application/profile labels. Tài liệu hiện hành mô tả việc chọn version enabled mới nhất theo số version; không nên suy luận rằng ứng dụng client tự polling Secret Manager nếu chưa cấu hình cơ chế refresh của Spring Cloud Config.

Nếu ứng dụng không dùng Config Server, dùng Secret Manager Java Client hoặc một workflow cấu hình riêng. Không giả định có scheme spring.config.import native cho Google Secret Manager giống aws-secretsmanager: nếu dependency/release line không cung cấp scheme đó.

## 7. Vì sao secret đã đổi nhưng kết nối vẫn dùng thông tin cũ?

### 7.1. Singleton bean giữ giá trị lúc khởi tạo

Một bean dùng Value thường nhận giá trị lúc Spring tạo bean. PropertySource thay đổi không tự cập nhật field đó.

Cách xử lý:

- Dùng ConfigurationProperties cho nhóm cấu hình có thể refresh.
- Kết hợp Spring Cloud Context refresh với RefreshScope cho bean phù hợp.
- Tạo lại bean/client phụ thuộc secret khi refresh.
- Nếu không thể refresh an toàn, rollout/restart instance theo quy trình.

### 7.2. RefreshScope không áp dụng tự động cho mọi bean phụ thuộc

Một factory/configuration bean được đánh dấu RefreshScope không có nghĩa mọi bean do factory tạo ra đều tự refresh. Các bean giữ reference tới client cũ cũng có thể tiếp tục dùng credential cũ.

Đối với SDK client, HTTP client hoặc database connection pool, xác định rõ đối tượng nào cần được tái tạo và ai sở hữu lifecycle của nó.

Spring Cloud có một số hạn chế với loại bean cụ thể. Ví dụ HikariDataSource được liệt kê trong nhóm mặc định không refreshable của Spring Cloud Refresh Scope. Với datasource đang dùng Hikari, cần thiết kế rotation/restart phù hợp, không chỉ thêm RefreshScope rồi kỳ vọng pool tự thay credential.

### 7.3. Connection pool vẫn giữ kết nối cũ

Database có thể cho phép session hiện tại tiếp tục hoạt động dù password cũ đã bị thay đổi. Nhưng khi pool tạo connection mới, authentication có thể thất bại.

Kiểm tra:

- Pool đã đóng connection cũ và mở connection mới chưa?
- Connection lifetime/idle timeout có khiến pool tái sử dụng session cũ không?
- Credential mới có quyền và database user tồn tại chưa?
- Database có cho phép hai credential hoạt động đồng thời trong giai đoạn chuyển tiếp không?
- Pool có được đóng/recreate sau khi cấu hình mới được bind không?

Không thu hồi password cũ ngay khi vừa ghi password mới vào secret store. Chờ workload chuyển đổi và xác minh trước.

### 7.4. SDK client hoặc secret cache giữ giá trị cũ

Một số client/cache giữ credentials hoặc payload đã đọc trong bộ nhớ. Hãy kiểm tra:

- Cache TTL và refresh policy.
- Client có nhận provider động hay provider tĩnh.
- Client có được build bằng StaticCredentialsProvider chứa giá trị cũ không.
- Bean nào giữ reference tới secret string/byte array.
- Có nhiều cache layer (Spring, SDK, ứng dụng, sidecar) hay không.

Nếu SDK hỗ trợ credential provider có khả năng tự refresh token/credentials, dùng provider đó thay cho việc tự giữ static credentials khi phù hợp. Tuy nhiên, provider refresh token không đồng nghĩa tự đọc lại password/API key trong secret store.

### 7.5. Các replica không đồng bộ

Trong Kubernetes hoặc nhiều instance, mỗi process có cache, timer và thời điểm khởi động riêng. Một số pod có thể đã refresh, số khác chưa tới kỳ poll hoặc đang bị lỗi quyền/network.

So sánh secret version metadata và reload timestamp của từng replica. Không log payload để xác định replica đang dùng version nào.

## 8. Ma trận troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Could not resolve placeholder | Import/profile/property key thiếu | Kiểm tra active profile, config import, tên property và startup log |
| AWS không nạp Parameter Store | Thiếu starter, sai scheme/path, region hoặc IAM | Kiểm tra aws-parameterstore import, SSM endpoint/region và ssm:GetParametersByPath |
| AWS không nạp Secrets Manager | Sai secret name/region, thiếu GetSecretValue, KMS decrypt bị từ chối | Kiểm tra secret ARN, account/region, IAM và KMS key policy |
| Secret đã đổi nhưng AWS không reload | Reload mặc định tắt hoặc dependency refresh thiếu | Bật reload strategy, thêm Actuator/Spring Cloud Context dependencies và kiểm tra polling |
| AWS reload có chạy nhưng bean không đổi | Bean không thuộc ConfigurationProperties/RefreshScope | Kiểm tra bean lifecycle hoặc chọn restart_context |
| Parameter Store trả giá trị cũ | Sai path, version/label hoặc property bị override | Kiểm tra parameter path, profile và PropertySource priority |
| Key Vault không được nạp | Starter/property source chưa enable, endpoint hoặc credential sai | Kiểm tra property-source-enabled, endpoint, managed identity và Key Vault role |
| Key Vault đã có version mới nhưng app vẫn cũ | Refresh interval dài/0 hoặc bean giữ giá trị cũ | Kiểm tra refresh-interval, bean scope và thời điểm refresh |
| Key Vault secret thay đổi nhưng không có hiệu lực | Environment variable có độ ưu tiên cao hơn Key Vault | Kiểm tra tên biến SPRING_* trong deployment, không in giá trị |
| Key Vault secret key không ánh xạ thành property | Dấu chấm/hoa thường/tên key không đúng | Dùng quy tắc ánh xạ dấu gạch nối, kiểm tra case-sensitive và secret-keys |
| GCP đọc nhầm secret version | Code pin version cũ hoặc dùng alias latest ngoài dự kiến | Kiểm tra version ID truyền vào SecretVersionName |
| GCP không đọc được secret | Sai project/principal, thiếu secretmanager.versions.access hoặc API chưa enable | Kiểm tra ADC/runtime service account, IAM và API |
| GCP tạo version mới nhưng app không đổi | App chỉ đọc một lần lúc startup | Bổ sung polling/event subscriber hoặc rollout deployment |
| GCP notification đến nhưng app không refresh | Pub/Sub subscriber chỉ nhận event, chưa có handler cập nhật | Kiểm tra subscription, event type, retry/DLQ và workflow |
| Refresh thành công nhưng DB vẫn lỗi | Connection pool giữ connection/credential cũ | Tạo lại pool theo lifecycle hoặc rollout instance |
| Một số pod dùng secret cũ | Poll/cache/restart không đồng bộ hoặc pod không đọc được store | Kiểm tra version metadata, logs và rollout status từng pod |
| Ứng dụng vẫn chạy với default password | Secret import bị đánh dấu optional hoặc placeholder có default | Bỏ optional/default với secret bắt buộc và fail fast |
| Secret store đọc thành công nhưng giá trị sai | PropertySource khác ghi đè | Kiểm tra origin và precedence, đặc biệt environment/system/CLI |
| Sau rotation tăng lỗi 401/403 | Credential mới chưa được cấp quyền hoặc credential cũ đã bị revoke quá sớm | Kiểm tra trạng thái credential ở hệ thống đích và thời điểm rollout |
| Sau refresh có nhiều kết nối lỗi | Bean phụ thuộc bị recreate không đúng lifecycle | Kiểm tra graceful shutdown, connection pool và in-flight requests |

## 9. Quy trình xoay vòng secret an toàn

Xoay vòng secret nên là một quy trình có trạng thái, không phải một lệnh ghi đè payload.

### Bước 1 — Xác định mọi consumer

Liệt kê:

- Ứng dụng và deployment dùng secret.
- Region/project/subscription/vault chứa secret.
- Secret version hiện hành.
- Cache, sidecar, connection pool và SDK client có giữ secret.
- Các consumer ngoài Spring Boot như batch job, migration, worker hoặc scheduled task.

### Bước 2 — Tạo credential mới ở hệ thống đích

Nếu hệ thống đích hỗ trợ hai credential song song, tạo credential mới và giữ credential cũ hoạt động trong thời gian chuyển đổi. Với database, có thể dùng user luân phiên hoặc quy trình cấp quyền cho user mới trước khi chuyển workload.

Nếu hệ thống chỉ cho phép một credential tại một thời điểm, cần lên kế hoạch downtime/rollout và cơ chế rollback riêng.

### Bước 3 — Lưu version mới vào secret store

Tạo version mới ở AWS Secrets Manager, cập nhật Parameter Store, tạo secret version mới ở Azure Key Vault hoặc Google Secret Manager. Ghi lại version ID, timestamp và trạng thái; không đưa payload vào ticket.

### Bước 4 — Kích hoạt cập nhật ứng dụng

Chọn cơ chế phù hợp:

- Spring Cloud AWS: PropertySource reload với strategy phù hợp hoặc rolling restart.
- Azure Key Vault: refresh interval và cơ chế tái tạo bean/client; nếu không có refresh lifecycle phù hợp, rolling restart.
- Google Secret Manager: subscriber/polling workflow hoặc cập nhật version trong deployment rồi rollout.
- Kubernetes Secret volume/config tree: kiểm tra cách volume cập nhật và có cần restart process hay không.

### Bước 5 — Xác minh tất cả replica

Kiểm tra:

- Version ID hoặc metadata được nạp.
- Kết nối tới database/API đích thành công.
- Error rate không tăng.
- Các worker/background job cũng dùng credential mới.
- Không còn request được ký hoặc xác thực bằng credential cũ.

Dùng một health check có khả năng xác minh kết nối thực tế, nhưng không trả secret hoặc thông tin nhạy cảm ra endpoint health công khai.

### Bước 6 — Thu hồi credential cũ

Chỉ thu hồi sau khi tất cả consumer đã chuyển sang credential mới và thời gian drain của connection/session cũ đã kết thúc. Nếu phát hiện lỗi, rollback sang version tốt đã được lưu và khôi phục quyền của credential cũ theo quy trình khẩn cấp.

## 10. Bài thực hành: cập nhật database password cho Orders API

Mục tiêu: Orders API dùng password trong secret store để kết nối PostgreSQL. Sau khi rotate, tất cả replica phải kết nối bằng password mới.

### Bước 1 — Khai báo nguồn cấu hình

Chọn một trong các cơ chế phù hợp với môi trường:

AWS Secrets Manager:

```yaml
spring:
  config:
    import: aws-secretsmanager:/secrets/prod/orders-db?prefix=spring.datasource.
```

Azure Key Vault:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: orders-db
              endpoint: https://orders-prod.vault.azure.net/
              secret-keys:
                - spring-datasource-url
                - spring-datasource-username
                - spring-datasource-password
              refresh-interval: 5m
```

Google Secret Manager dùng Java client hoặc Config Server backend đã được cấu hình. Nếu dùng version pin, đặt version ID trong deployment configuration.

### Bước 2 — Bind property vào cấu hình datasource

```yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal:5432/orders
    username: orders_app
    password: REQUIRED_FROM_SECRET_STORE
```

Giá trị minh họa trong file không được dùng làm password mặc định ở production. Cấu hình thực tế phải bảo đảm secret store cung cấp property bắt buộc và startup thất bại nếu thiếu.

### Bước 3 — Tạo credential mới và lưu version mới

Tạo password mới cho user database hoặc user luân phiên. Cập nhật secret store và ghi lại version ID/timestamp.

Giữ credential cũ còn hiệu lực trong giai đoạn rollout nếu database hỗ trợ hai user hoặc hai password song song.

### Bước 4 — Refresh hoặc rollout

Nếu dùng Spring Cloud AWS reload, kiểm tra reload strategy và bean scope. Nếu dùng Azure Key Vault, chờ refresh interval hoặc kích hoạt rollout có kiểm soát. Nếu dùng GCP Secret Manager, gửi event/triển khai version mới theo workflow.

Với HikariDataSource, lên kế hoạch tạo lại pool hoặc rolling restart vì pool hiện tại có thể không được refresh scope hỗ trợ.

### Bước 5 — Xác minh

Mỗi replica cần báo cáo an toàn:

- Secret version ID/metadata đang dùng.
- Datasource health check.
- Kết quả mở connection mới.
- Số lần authentication failure.
- Deployment revision và thời điểm refresh.

Không in URL có embedded credentials, password hoặc secret payload.

### Bước 6 — Thu hồi password cũ

Sau khi toàn bộ replica và job đã chuyển sang credential mới, thu hồi user/password cũ và theo dõi lỗi kết nối trong khoảng thời gian phù hợp với workload.

## 11. Bảo vệ secret trong quá trình troubleshooting

- Không log secret payload, access token, API key, private key, SAS token hoặc connection string đầy đủ.
- Không đưa secret vào command-line argument vì có thể xuất hiện trong process list hoặc shell history.
- Không bật Actuator endpoint hiển thị toàn bộ giá trị cấu hình trên public ingress.
- Nếu cần dùng /refresh hoặc /restart, chỉ expose trên management interface có xác thực và phân quyền.
- Không cấp quyền đọc toàn bộ vault/project/account chỉ để kiểm tra một secret.
- Ghi lại secret name, version ID, timestamp và provider request ID thay cho payload.
- Dùng secret version có thể rollback và giữ credential cũ trong giai đoạn chuyển đổi nếu hệ thống đích hỗ trợ.
- Tắt/disable version cũ trước khi destroy nếu nền tảng hỗ trợ trạng thái trung gian và cần thời gian xác minh.
- Không đặt secret bắt buộc thành optional hoặc cung cấp default password trong production.
- Kiểm tra các bản log/trace đã được masking trước khi gửi cho nhóm hỗ trợ.

## 12. Ghi nhớ

- Nạp config, chọn PropertySource và áp dụng config vào bean là ba giai đoạn riêng.
- spring.config.import nạp remote config trong bootstrap; optional có thể che lỗi thiếu secret bắt buộc.
- spring.config.location thay thế location mặc định; spring.config.additional-location bổ sung location.
- Environment variable, system property hoặc command-line argument có thể ghi đè giá trị từ secret store.
- Value được resolve khi bean được tạo; singleton bean không tự thay field khi secret store đổi.
- Spring Cloud AWS Secrets Manager/Parameter Store reload tắt mặc định. Cần bật strategy, dependency refresh và bean scope phù hợp.
- Azure Key Vault PropertySource mặc định refresh mỗi 30 phút; environment variable có thể có ưu tiên cao hơn.
- Google Secret Manager tạo version bất biến. latest tiện lợi nhưng production thường nên pin version và rollout có kiểm soát.
- Secret Manager Pub/Sub notifications chỉ khởi động workflow; ứng dụng phải tự refresh/restart/rollout.
- RefreshScope không tự làm mới mọi bean phụ thuộc. Connection pool và SDK client cần lifecycle riêng.
- Hãy giữ credential cũ trong thời gian chuyển đổi nếu hệ thống đích hỗ trợ, xác minh mọi replica rồi mới thu hồi.
- Chỉ đánh dấu rotation hoàn tất khi request thật tới database/API đích thành công trên tất cả replica.

## Tài liệu tham khảo chính thức

1. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Cloud — Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
3. [Spring Cloud AWS 3.4.2 — Secrets Manager integration and PropertySource reload](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
4. [Spring Cloud AWS 3.4.2 — Parameter Store integration and PropertySource reload](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
5. [AWS Systems Manager — Parameter Store and SecureString](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-a-parameter.html)
6. [AWS Secrets Manager — Java client-side caching](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html)
7. [AWS Secrets Manager — Rotation schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
8. [Spring Cloud Azure — Secret Management with Key Vault](https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html)
9. [Spring Cloud Azure — KeyVaultPropertySource refresh interval and priority](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management)
10. [Google Cloud Secret Manager — Access a secret version](https://docs.cloud.google.com/secret-manager/docs/access-secret-version)
11. [Google Cloud Secret Manager — Rotation recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations)
12. [Google Cloud Secret Manager — Event notifications](https://docs.cloud.google.com/secret-manager/docs/event-notifications)
13. [Google Cloud Secret Manager — Rotation schedules](https://docs.cloud.google.com/secret-manager/docs/secret-rotation)
14. [Spring Cloud Config — Google Secret Manager backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/gcp-secret-manager-backend.html)

Tên property, thời gian refresh và khả năng reload phụ thuộc phiên bản starter/SDK. Đối chiếu BOM và release line đang chạy; sau mỗi lần rotation, xác minh property origin, bean lifecycle, connection mới và trạng thái của từng replica thay vì chỉ dựa vào việc secret store đã ghi version mới.
