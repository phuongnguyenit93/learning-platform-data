# Cấu hình ứng dụng theo môi trường Azure

Một dịch vụ Spring Boot hoạt động tốt trên laptop có thể không khởi động được khi triển khai lên Azure App Service, Azure Container Apps hoặc Azure Kubernetes Service (AKS). Nguyên nhân thường không nằm ở Java code: sai kết nối database, kích hoạt nhầm profile, biến môi trường thiếu, bí mật hết hạn, DNS Private Endpoint không đúng, hoặc một cấu hình production bị ghi đè bởi giá trị dùng để thử nghiệm. **Cấu hình ứng dụng theo môi trường Azure** là cách quản lý các khác biệt này có chủ đích, có thể kiểm chứng và có khả năng rollback.

Trong chương **Spring Boot trên Azure**, ta sẽ kết hợp cơ chế **Spring Boot externalized configuration** với những dịch vụ Azure như Microsoft Entra ID, Managed Identity, Azure App Configuration, Azure Key Vault, App Service, Container Apps, AKS, Azure SQL, Storage và các thành phần quan sát hệ thống. Bài thuộc mô-đun **CLOUD_PROVIDERS_AZURE**: khám phá Azure từ subscription, resource group, Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu, đồng thời triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng.

**Nguyên tắc chính:** cùng một phiên bản ứng dụng/container image nên có khả năng chạy ở nhiều môi trường; những khác biệt về endpoint, feature flags, giới hạn tài nguyên, quyền và bí mật được cung cấp **bên ngoài mã nguồn**. Không đóng gói password production, không sửa source rồi build lại chỉ để thay một hostname, và không giả định profile tên **prod** tự tạo ra bảo mật production.

> **Lưu ý phiên bản:** Ví dụ dùng tư duy của **Spring Boot 3.x** và Java hiện đại. Cơ chế Config Data, tên properties của Spring Cloud Azure, cách cấp bí mật, Azure CLI, network capabilities và giao diện Portal có thể khác theo phiên bản/tier/nền tảng. Hãy kiểm tra tài liệu tương ứng với phiên bản Spring Boot, Spring Cloud Azure và dịch vụ Azure đang chạy. Các giá trị tên resource/host/path là **minh họa**; các lệnh có thể thay tài nguyên sẽ được chỉ rõ và chỉ thực hiện trong môi trường lab được cấp phép.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại **cấu hình không nhạy cảm, bí mật, thông tin kết nối và trạng thái nghiệp vụ**.
2. Sử dụng **application.yml**, **application-{profile}.yml**, **SPRING_PROFILES_ACTIVE**, biến môi trường và command-line arguments đúng mục đích.
3. Giải thích các nguyên tắc **Spring PropertySource / Config Data precedence** và tránh nhầm thứ tự ghi đè cấu hình.
4. Gắn cấu hình vào Java code bằng **@ConfigurationProperties**, áp validation và fail fast khi thiếu giá trị quan trọng.
5. So sánh cách cấp cấu hình trong **Azure App Service, Azure Container Apps và AKS**.
6. Chọn **Azure App Configuration** cho cấu hình tập trung, labels/feature flags và **Azure Key Vault** cho secrets.
7. Hiểu **Microsoft Entra managed identity**, RBAC, secret rotation, DNS, TLS và private endpoints.
8. Thiết kế startup/readiness/liveness, retry/timeout, observability và rollback an toàn theo môi trường.
9. Tránh cấu hình nhầm dev/staging/prod, secret leaks và configuration drift qua CI/CD/IaC.
10. Xây dựng bài thực hành cấu hình Spring Boot và checklist production có thể kiểm chứng.

## 1. Cấu hình ứng dụng là gì?

**Configuration** là dữ liệu điều chỉnh hành vi ứng dụng mà không cần sửa logic chương trình. Ví dụ:

- Base URL của một dịch vụ nội bộ.
- JDBC URL, database pool size và connection timeout.
- Azure Blob container name hoặc Storage endpoint.
- Tỷ lệ bật một feature theo môi trường.
- Logging level, sampling và timeout.
- Redis hostname, Service Bus namespace, queue name.
- Giới hạn số requests đồng thời và batch size.

**Secret** là thông tin cần bảo vệ mạnh hơn: database password, signing key, Storage account key, client secret, API key hoặc access token. **Runtime data** như đơn hàng, số dư và session người dùng không phải configuration dù có thể được lưu trong một database/config-like store.

### Tách ba nhóm dữ liệu

| Nhóm | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| **Cấu hình thường** | app.client.timeout, API URL, enabled modules | application.yml, environment variables, Azure App Configuration |
| **Bí mật** | Password, API key, private key, secret token | Azure Key Vault hoặc secret facility được nền tảng cho phép |
| **Dữ liệu nghiệp vụ** | Orders, inventory, customer records | Azure SQL, Cosmos DB, Storage theo yêu cầu |

**Không coi Azure App Configuration là nơi lưu password plaintext** chỉ vì có thể tạo key-value; dùng Key Vault và tham chiếu/bí mật theo integration được hỗ trợ.

## 2. Những môi trường ứng dụng cần phân biệt

Một hệ thống có thể có nhiều môi trường:

~~~text
Developer laptop
      |
      v
DEV -> TEST -> STAGING -> PRODUCTION
      |       |          |
      |       |          +-- Azure production resources
      |       +------------- Pre-production validation
      +--------------------- Synthetic/sample resources
~~~

| Môi trường | Nhiệm vụ | Hướng cấu hình |
|---|---|---|
| **local** | Developer chạy/debug | Endpoints dev, credentials của developer được cấp hạn chế |
| **dev** | Tích hợp tính năng mới | Resources dev, verbose diagnostics có kiểm soát |
| **test** | Automated/integration tests | Dữ liệu tổng hợp, fixtures, deterministic settings |
| **staging** | Kiểm thử trước phát hành | Càng giống prod về cách cấp config/auth/network càng tốt |
| **prod** | Phục vụ người dùng thật | Least privilege, TLS, high availability, bounded retries, cảnh báo |

Spring **profiles** là một cơ chế bật/tắt tập cấu hình/beans; tên profile không tự thay thế **resource separation, network policy, RBAC, change management** hoặc hạ tầng production.

### Không dùng cùng một database cho dev và prod

Nếu API dev vô tình dùng JDBC URL production, một integration test DELETE có thể xóa dữ liệu thật. Nên tách subscription/resource group/identity/data sources theo chính sách, đồng thời kiểm tra endpoint và principal trước khi cho phép job hoặc migrations.

## 3. Mục tiêu: build một lần, deploy nhiều nơi

~~~text
Git commit abc123
        |
        v
CI: build + test + scan
        |
        v
Container image digest: sha256:...
        |
        +--> DEV      + env vars + dev identity/Key Vault
        |
        +--> STAGING  + env vars + staging identity/Key Vault
        |
        +--> PROD     + env vars + prod identity/Key Vault
~~~

**Cùng image digest** giúp giảm sai lệch do biên dịch lại với dependencies khác nhau. Configuration của mỗi môi trường được gắn lúc triển khai hoặc runtime, không đóng gói vào binary. Cần version hóa cấu hình không nhạy cảm và quản lý secrets riêng.

### Một artifact cho nhiều môi trường có những giới hạn?

- Có thể phải dùng những feature flags/endpoint khác nhau.
- Một số thay đổi cấu hình đòi restart hoặc rollout.
- Nếu schema DB prod khác staging, artifact giống nhau không bảo đảm chạy giống nhau.
- Cấu hình bị cấp sai vẫn có thể gây sự cố lớn.

**Build once** là phương pháp giảm biến số, không phải lời hứa rằng cùng binary chắc chắn hoạt động trên mọi môi trường.

## 4. Cơ chế externalized configuration của Spring Boot

Spring Boot có thể lấy properties từ nhiều nguồn:

- Default properties và các file cấu hình đóng gói cùng ứng dụng.
- **application.properties** hoặc **application.yml**.
- Profile-specific files như **application-dev.yml**.
- Các nguồn **Config Data import**.
- **Environment variables** từ process/container.
- Java system properties.
- Command-line arguments.
- Các nguồn tùy chỉnh thông qua Spring integration.

Từ góc nhìn Java code, chúng được hợp nhất vào **Environment** và **PropertySources** có thứ tự ưu tiên.

~~~text
application.yml        application-prod.yml
        |                       |
        +----------+------------+
                   |
          External Config Data
                   |
       OS environment variables
                   |
     JVM system / CLI args and others
                   |
                   v
         Spring Environment
                   |
                   v
        @ConfigurationProperties
                   |
                   v
               Beans / SDK clients
~~~

Sơ đồ **không phải bảng precedence tuyệt đối**. Spring Boot có thứ tự chi tiết cho mỗi loại nguồn; vị trí file, import order, document activation, property source do framework thêm và command-line handling ảnh hưởng kết quả. Phải xem documentation/version thật và quan sát effective value an toàn khi điều tra.

## 5. Nguyên tắc precedence và ghi đè giá trị

Giả sử file **application.yml** khai báo:

~~~yaml
app:
  client:
    timeout: 3s
~~~

Và trong process có biến:

~~~text
APP_CLIENT_TIMEOUT=500ms
~~~

Trong một cấu hình Spring Boot thông thường, environment variable được bind thành **app.client.timeout** và có thể ghi đè giá trị trong file. Nếu command-line lại có **--app.client.timeout=200ms**, giá trị từ CLI thường có ưu tiên cao hơn OS env vars theo thứ tự mặc định.

### Bảng quy tắc khái quát

| Nguồn | Ghi chú |
|---|---|
| application.yml | Giá trị nền; không nên có secret |
| application-prod.yml | Override khi profile prod được kích hoạt |
| External config file | Có thể được tải từ ngoài jar và override theo vị trí |
| Environment variables | Hay dùng khi triển khai Azure app/container |
| JVM system properties | Các tùy chọn **-Dkey=value** |
| Command-line arguments | **--key=value**, thường có mức ưu tiên cao |
| Imported Config Data | Vị trí ưu tiên phụ thuộc import và Spring Boot version |

**Không chỉ dựa vào bảng này để phán đoán kết quả phức tạp**. Thứ tự đầy đủ được Spring Boot quy định; đối với các config imports/providers, hãy kiểm tra precedence, refresh và fail-on-missing theo đúng phiên bản.

### Vì sao override nguy hiểm?

Một startup script thêm **--spring.datasource.url** có thể ghi đè URL production đã được cấp đúng qua environment. Vì vậy môi trường production cần quản lý arguments/config sources như thay đổi hạ tầng, không để từng developer chỉnh tự do.

## 6. application.yml: các giá trị mặc định an toàn

Ví dụ cấu hình nền trong repository:

~~~yaml
spring:
  application:
    name: catalog-api

server:
  port: 8080

app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
  features:
    recommendations: false

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

Đây là giá trị minh họa. **connect-timeout**, **read-timeout** và **max-retries** là custom application properties; chúng **không tự cấu hình mọi HTTP/Azure SDK client** nếu không có Java bean/code nhận và áp dụng.

### Những thứ không nên đặt trong file này

- Database password hoặc Redis access key.
- Key Vault secret values.
- Connection string chứa account keys hoặc SAS.
- Production-only credentials hoặc token.
- Private keys và certificates chưa được quản lý phù hợp.

Các giá trị có tính mặc định nên an toàn: ví dụ feature mới chưa kiểm chứng được tắt, mức retry hữu hạn và log level không thu payload nhạy cảm.

## 7. Profile-specific files: application-dev.yml và application-prod.yml

Spring Boot có thể sử dụng các file theo profile:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

Ví dụ **application-dev.yml**:

~~~yaml
logging:
  level:
    com.example.catalog: DEBUG

app:
  features:
    recommendations: true
  client:
    read-timeout: 10s
~~~

Ví dụ **application-prod.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO

app:
  features:
    recommendations: false
  client:
    read-timeout: 3s
~~~

### Hai điều cần nhớ

1. **application-prod.yml** không tự hoạt động vì đang chạy trên Azure: phải có active profile **prod** hoặc cơ chế tương ứng.
2. Những file profile có thể chứa cấu hình **không nhạy cảm**, nhưng không nên commit production passwords. Dùng Key Vault/secret injection cho giá trị nhạy cảm.

Không đặt **spring.profiles.active** trong profile-specific document/file rồi kỳ vọng Spring tự kích hoạt nó: Spring Boot hạn chế sử dụng các thuộc tính kích hoạt profile trong tài liệu profile-activated. Chọn active profile từ môi trường triển khai hoặc một nguồn không phụ thuộc vào chính profile ấy.

## 8. Kích hoạt profile và kiểm tra hiệu lực

Trong môi trường CLI/lab:

~~~bash
# Linux/macOS, chỉ ảnh hưởng shell/process hiện tại.
export SPRING_PROFILES_ACTIVE=dev
java -jar catalog-api.jar
~~~

Hoặc:

~~~bash
java -jar catalog-api.jar --spring.profiles.active=staging
~~~

Khi ứng dụng chạy trên Azure, phổ biến hơn là cấu hình **SPRING_PROFILES_ACTIVE** trong application settings/Container App environment variables/Kubernetes environment.

### Cẩn thận với nhiều profile cùng lúc

~~~text
SPRING_PROFILES_ACTIVE=staging,metrics
~~~

Spring có thể kích hoạt nhiều profile; nếu cùng property xuất hiện ở nhiều nguồn/profile document, **thứ tự** và cơ chế Config Data ảnh hưởng giá trị cuối. Đừng coi profile như một túi nhãn không có ưu tiên.

### Profile mặc định

Nếu không cấu hình active profiles, Spring dùng default profile theo quy tắc framework, không tự suy ra dev. Một ứng dụng thiếu profile có thể vẫn chạy với application.yml; vì vậy **các biến cấu hình quan trọng cần validation** thay vì mặc định kết nối nhầm nơi.

## 9. spring.config.activate.on-profile và multi-document YAML

Spring Boot Config Data có thể khai báo nhiều tài liệu YAML trong một file:

~~~yaml
app:
  features:
    recommendations: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  features:
    recommendations: true

---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    connect-timeout: 1s
~~~

Các tài liệu sau dấu **---** chỉ áp dụng khi điều kiện profile phù hợp. Đây là cách thay thế file application-dev.yml/application-prod.yml nếu dự án muốn tập trung các override.

### Những bẫy

- Không đặt bí mật trong bất kỳ tài liệu YAML nào commit Git.
- Không khai báo **spring.profiles.active** hoặc cấu hình nhóm profile trong tài liệu đã bị giới hạn bởi on-profile.
- Không giả định YAML document order luôn thay thế mọi quy tắc property source.
- Khi cấu hình trở nên phức tạp, tách file/nguồn config có thể dễ review hơn.

## 10. Profile groups và tránh bùng nổ profiles

Một ứng dụng có thể cần nhóm cấu hình: database, observability và feature flags. Spring Boot hỗ trợ **profile groups** ở nguồn cấu hình hợp lệ.

~~~yaml
spring:
  profiles:
    group:
      prod:
        - database-prod
        - observability-prod
~~~

Khi kích hoạt **prod**, các profiles thuộc group có thể được kích hoạt theo cơ chế Spring Boot.

**Chỉ khai báo profile group trong nguồn không thuộc profile-specific/activated document** theo giới hạn Spring Boot. Đồng thời đừng biến profile groups thành một ma trận 50 combinations khó kiểm thử.

### Cách thiết kế hợp lý

- **Environment profiles:** local, dev, staging, prod.
- **Feature switches:** dùng feature flags thay vì tạo một profile cho mỗi tính năng.
- **Secrets/config values:** dùng external config/Key Vault.
- **Bean implementations thực sự khác nhau:** khi cần dùng @Profile.

## 11. Mapping environment variables sang Spring properties

Spring Boot sử dụng cơ chế **relaxed binding**, giúp ánh xạ tên environment variable sang property names.

| Spring property | Environment variable thường dùng |
|---|---|
| spring.profiles.active | **SPRING_PROFILES_ACTIVE** |
| server.port | **SERVER_PORT** |
| spring.datasource.url | **SPRING_DATASOURCE_URL** |
| spring.datasource.username | **SPRING_DATASOURCE_USERNAME** |
| spring.datasource.password | **SPRING_DATASOURCE_PASSWORD** |
| app.client.connect-timeout | **APP_CLIENT_CONNECTTIMEOUT** |
| app.features.recommendations | **APP_FEATURES_RECOMMENDATIONS** |

### Quy tắc cần biết

Với binding environment theo quy tắc chuẩn của Spring Boot: **dấu chấm thành dấu gạch dưới, dấu gạch ngang bị loại bỏ, chuyển sang chữ hoa**. Vì vậy **app.client.connect-timeout** tương ứng **APP_CLIENT_CONNECTTIMEOUT**, không nên mặc định **APP_CLIENT_CONNECT_TIMEOUT** có cùng hiệu lực trong mọi tình huống.

**Có sự khác biệt** giữa tra cứu property bằng Environment.getProperty, relaxed binding của @ConfigurationProperties và cơ chế placeholder cụ thể. Khi dùng các khóa custom quan trọng, kiểm thử mapping bằng ứng dụng thật thay vì đoán từ tên.

### Vì sao đây là lỗi production thường gặp?

Operator đặt một biến trông hợp lý như **APP_CLIENT_CONNECT_TIMEOUT**, nhưng Java record vẫn nhận default value. Log không báo rõ vì không có validation. Giải pháp: đặt tên canonical, sử dụng @ConfigurationProperties có validate và kiểm tra effective configuration bằng test không tiết lộ secrets.

## 12. Spring config.import và external config files

Khi config nằm ngoài JAR, Spring Boot có cơ chế **Config Data** và **spring.config.import**:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/catalog/overrides.yml"
~~~

**optional:** cho phép ứng dụng tiếp tục nếu file không tồn tại; chỉ dùng khi sự vắng mặt là hợp lệ. Với cấu hình quan trọng, dùng import bắt buộc hoặc validation fail fast.

### Các thuật ngữ cần phân biệt

- **spring.config.location:** điều khiển vị trí config được tìm; có thể **thay thế** vị trí mặc định tùy cú pháp.
- **spring.config.additional-location:** thêm vị trí bên cạnh vị trí mặc định.
- **spring.config.import:** import additional config data trong một tài liệu config; precedence theo Spring Config Data semantics.
- **spring.config.name:** đổi tên base config files được tìm kiếm.

Không dùng lẫn các thuộc tính mà chưa kiểm tra precedence/version Spring Boot. Đặc biệt đừng làm mất application.yml mặc định khi truyền **spring.config.location** không đúng.

### Mount directory và configtree

Với configuration tree (các file tên property và nội dung value), Spring Boot hỗ trợ kiểu import **configtree:** ở những bản phù hợp:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/catalog/secrets/"
~~~

Đây là cách tiêu thụ một thư mục file do nền tảng mount, không tự tạo bí mật và không tự mã hóa secrets.

## 13. Không dùng @Value cho mọi thuộc tính

Spring hỗ trợ **@Value**:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogFeature {
    public CatalogFeature(
            @Value("${app.features.recommendations:false}")
            boolean enabled) {
        // Giá trị được inject lúc bean được tạo.
    }
}
~~~

@Value phù hợp cho một số giá trị đơn giản, nhưng nếu có 20 thuộc tính rải trên nhiều classes thì khó validate, khó document và kiểm tra consistency.

**@ConfigurationProperties** nên được cân nhắc cho một nhóm settings có cấu trúc, type safety và validation.

## 14. @ConfigurationProperties: binding có kiểu

Giả sử:

~~~yaml
app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
~~~

Với Spring Boot 3.x, Java record có thể được bind qua constructor theo quy tắc framework:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(0) int maxRetries) {
}
~~~

Spring Boot application:

~~~java
package com.example.catalog;

import com.example.catalog.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### Điều kiện

- Dự án có **spring-boot-starter-validation** (hoặc validator phù hợp) để xử lý Jakarta Bean Validation.
- Spring Boot version hỗ trợ record constructor binding như ví dụ.
- Properties thực sự tồn tại và bind được sang Duration/int.
- Java code dùng **ClientProperties** để cấu hình HTTP SDK/client; record một mình không thay timeout của bất kỳ API nào.

### Kiểm tra tính hợp lệ ở mức nghiệp vụ

@NotNull bảo vệ Duration không null, @Min(0) bảo vệ số retries không âm. Tuy nhiên timeout **-1s**, timeout quá dài hoặc read-timeout nhỏ hơn connect-timeout có thể cần validation bổ sung bằng Jakarta constraints/custom validator, tùy thiết kế.

## 15. Fail fast: cấu hình quan trọng thiếu thì không chạy

Ví dụ production API cần URL tới catalog backend. Nếu URL thiếu mà ứng dụng rơi về **http://localhost:8081**, pod trong AKS có thể báo Running nhưng gửi request vào chính nó/địa chỉ sai.

### Nguyên tắc

1. Cấu hình bắt buộc không được có default trỏ nhầm localhost/prod.
2. Bật validation cho @ConfigurationProperties.
3. Kiểm tra URL scheme (HTTPS nếu yêu cầu), hostname và giới hạn timeout.
4. Kiểm tra sự tồn tại của các credentials/identity theo giai đoạn startup thích hợp.
5. Đảm bảo logs báo **tên key bị thiếu**, không in secret values.
6. Không bắt mọi lỗi rồi tiếp tục chạy bằng default insecure.

### Ví dụ không nên dùng

~~~yaml
spring:
  datasource:
    password: "${DB_PASSWORD:admin123}"
~~~

Nếu **DB_PASSWORD** thiếu, ứng dụng có thể dùng password hard-code. Với secret production, không có fallback mặc định là lựa chọn an toàn hơn:

~~~yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
~~~

Tuy nhiên **DB_PASSWORD** vẫn là bí mật trong process environment; ưu tiên secret reference/managed identity và đánh giá chính sách truy cập process/container.

## 16. Local development không nên bắt chước production bằng secrets thật

Ở laptop:

- Dùng local services/emulators khi phù hợp.
- Dùng resources **dev** có scope hẹp.
- Dùng Azure CLI/developer identity đã được cấp quyền tối thiểu.
- Có sample dataset tổng hợp.
- Không tải bản dump production chứa PII chỉ vì dễ test.
- Dùng .gitignore và local secret management/IDE run configuration được tổ chức phê duyệt.

~~~text
Laptop Spring Boot (profile local)
        |
        +--> Local test DB / dev Azure SQL
        +--> Dev Blob container
        +--> Dev App Configuration
        +--> Dev Key Vault (nếu cần)
        |
        v
Không có quyền truy cập dữ liệu prod mặc định
~~~

### Không sử dụng Azure production principal cho local profile

Nếu developer dùng cùng managed identity/service principal được cấp quyền production, một lỗi command/test có thể thay đổi dữ liệu thật. Dev identity nên bị chặn bởi RBAC và network ngay cả khi code cấu hình nhầm.

## 17. Azure App Service: Application Settings

Với **Azure App Service**, nhiều cấu hình được cấp qua **Application Settings**. Chúng có thể xuất hiện dưới dạng process environment variables phù hợp với runtime/hosting mode. Một web app Spring Boot có thể nhận:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:sqlserver://<sql-fqdn>:1433;databaseName=catalog
APP_CLIENT_CONNECTTIMEOUT=2s
APP_FEATURES_RECOMMENDATIONS=false
~~~

Đây là tên/giá trị minh họa. JDBC URL và cấu hình mã hóa SQL Server phải dùng đúng driver và chính sách TLS của tổ chức, không chỉ dựa vào FQDN.

### Luồng triển khai

~~~text
Git/CI -> Spring Boot JAR/container image
              |
              v
          Azure App Service
              |
              +-- App Settings (env-specific)
              +-- Managed Identity
              +-- Key Vault references nếu được cấu hình
              +-- VNet Integration + private routes
              |
              v
         Spring Environment
              |
              v
         Application beans
~~~

### Những điểm cần quan tâm

1. **App Service config changes** có thể kích hoạt restart hoặc yêu cầu reload tùy loại setting; không xem thay đổi là zero-downtime tự động.
2. Không log toàn bộ process environment hoặc app settings.
3. Xác định identity gắn vào từng slot và quyền riêng.
4. Nếu App Service kết nối tới database/private endpoint, cần VNet integration/DNS và firewall phù hợp.
5. Một số thiết lập runtime được platform quản lý như cổng/health probes có tương tác với Spring configuration; không override tùy tiện.

## 18. App Service Deployment Slots: config nào được hoán đổi?

Deployment slots có thể hỗ trợ triển khai staging rồi swap sang production theo plan/tính năng. Nhưng nếu cấu hình không được gắn đúng slot, một lần swap có thể khiến production dùng endpoint staging hoặc ngược lại.

~~~text
App Service: catalog-api
      |
      +-- Slot production
      |      SPRING_PROFILES_ACTIVE=prod
      |      PROD_SQL_ENDPOINT=...
      |      PROD_KEYVAULT_REFERENCE=...
      |
      +-- Slot staging
             SPRING_PROFILES_ACTIVE=staging
             STAGING_SQL_ENDPOINT=...
             STAGING_KEYVAULT_REFERENCE=...
~~~

### Slot setting là gì?

Một số application settings có thể được đánh dấu **deployment slot setting** (sticky): giá trị bám theo slot, không đổi cùng phần nội dung ứng dụng khi swap theo semantics của App Service.

### Checklist trước swap

- Profile **prod** và connection target production phải được giữ đúng.
- Secret references, endpoint/callback URL và config service connection đã được phân loại sticky/non-sticky.
- Managed identities/roles của slot đủ quyền với tài nguyên tương ứng.
- Health/readiness probe và warm-up phù hợp.
- Không có job migration/background task chạy sai slot hoặc chạy trùng.
- Có khả năng rollback swap và theo dõi error rate.

**Đừng giả định mọi setting đều tự là sticky**. Cần kiểm tra cụ thể loại setting, slot flags, nền tảng và workflow swap đang dùng.

## 19. App Service: thông tin từ Azure CLI

Các lệnh sau **đọc metadata** và nên chạy trong môi trường quản trị được cấp quyền:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId}" \
  --output json

az webapp show \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<LAB_WEBAPP>" \
  --query "{name:name,state:state,kind:kind,hostNames:hostNames}" \
  --output json
~~~

**Không mặc định chạy az webapp config appsettings list và chia sẻ output**, vì một số settings có thể chứa secret values. Khi cần điều tra cấu hình, dùng phương pháp chỉ hiển thị **key names hoặc giá trị đã redacted** theo quy trình kiểm toán.

### Thao tác cấu hình phải qua change control

Thay application settings bằng Portal, CLI hoặc IaC là **ghi thay đổi runtime**. Trong bài lab có thể minh họa, nhưng không có lý do để chạy update lên production chỉ để thử profile. Dùng staging và cơ chế approval.

## 20. Azure Container Apps: environment variables và secrets

**Azure Container Apps** phù hợp vận hành container ứng dụng với revisions, scale và những khả năng networking theo môi trường Container Apps. App có thể nhận cấu hình từ:

- Container environment variables.
- Container Apps secrets và secret references.
- Managed identity.
- Service discovery/ingress settings.
- Nguồn cấu hình bên ngoài như App Configuration/Key Vault theo integration.

~~~text
Container Apps Environment
          |
          v
Container App: catalog-api
  Revision R1
    Image digest: sha256:...
    SPRING_PROFILES_ACTIVE=prod
    APP_CLIENT_CONNECTTIMEOUT=2s
    DB_PASSWORD=<secret reference, not raw source>
          |
          v
Spring Boot starts with effective config
~~~

### Revisions và thay cấu hình

Thay container image hoặc những revision-scope properties có thể tạo revision mới; một số cấu hình ở application scope có hành vi khác. **Không giả định sửa secret là mọi revision đã tự reload ngay**: phải xác định secret injection/restart/rollout semantics, rồi kiểm chứng.

### Những câu hỏi cần trả lời

1. Secrets được tạo ở đâu và ai có thể xem/sửa?
2. Reference tới Key Vault có được hỗ trợ và identity đã có quyền chưa?
3. Các biến environment có xuất hiện khi process startup không?
4. Revision mới đã nhận giá trị config mới chưa?
5. Nếu dùng scale-to-zero, startup có phụ thuộc nguồn cấu hình/network và có timeout đủ không?
6. Có thể rollback sang revision trước mà vẫn đọc được secrets/config phù hợp không?

**Container Apps secret store không tự làm application-level authorization tốt hơn**; quyền đọc dữ liệu Azure SQL/Storage phải tách biệt.

## 21. AKS: ConfigMap, Secret và Pod environment

Trên **Azure Kubernetes Service (AKS)**, Kubernetes có các cơ chế:

- **ConfigMap:** dữ liệu cấu hình không nhạy cảm.
- **Secret:** dữ liệu cần quản lý bí mật; mặc định dạng manifest/base64 không đồng nghĩa được mã hóa an toàn khi lưu trong Git.
- **Pod env/envFrom:** đưa key vào process environment.
- **Mounted volumes:** cấp file-based config/secret.
- **Secrets Store CSI Driver và Azure Key Vault provider:** đọc bí mật từ Key Vault theo khả năng và cấu hình.
- **AKS Workload Identity:** dùng federated identity để truy cập dịch vụ Azure theo quyền được cấp.

~~~text
Kubernetes Deployment
       |
       +-- ConfigMap -> APP_CLIENT_CONNECTTIMEOUT
       +-- Secret / CSI -> DB_PASSWORD or mounted file
       +-- ServiceAccount -> Workload Identity
       |
       v
Spring Boot container
       |
       v
Database / Key Vault / Storage over approved network
~~~

### ConfigMap không dành cho password

Không đặt API key, database password hoặc private key trong ConfigMap chỉ vì có thể mount dưới dạng file. Kubernetes Secret cũng cần **RBAC, encryption at rest/etcd policy, audit, cluster access restrictions** và integration phù hợp; Base64 là encoding chứ không phải encryption.

## 22. AKS: ví dụ Deployment cấu hình Spring Boot

Ví dụ YAML **rút gọn** cho namespace lab, chỉ minh họa env names và secret references; không phải manifest production hoàn chỉnh:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: catalog-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: myregistry.example/catalog-api:lab-image-digest-placeholder
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "staging"
            - name: APP_CLIENT_CONNECTTIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: catalog-config
                  key: client-connect-timeout
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: catalog-secrets
                  key: db-password
~~~

### Điều kiện để manifest hoạt động

- Namespace, ConfigMap và Secret tồn tại trong cluster/namespace phù hợp.
- Container image thực được xây và có quyền pull.
- Kubernetes admission, Pod Security và resource limits phù hợp.
- Service/ingress/probes/volumes phải được bổ sung theo kiến trúc.
- Nếu dùng AKS Workload Identity, cần ServiceAccount annotation/federation configuration theo tài liệu, không tự có từ ví dụ này.

**Không dùng kubectl apply trên production** chỉ để thử cấu hình từ bài học; tạo resource ở cluster lab và có owner/cleanup plan.

### Thay ConfigMap/Secret có tự reload?

Kubernetes env vars thường được cung cấp lúc **container start**. Thay ConfigMap/Secret sau khi Pod đã chạy **không tự cập nhật giá trị environment đang nằm trong process**. Volume mount có semantics cập nhật khác tùy cấu hình; Spring Boot cũng không tự refresh bean values nếu không có cơ chế phù hợp.

Vì vậy cần **rollout/restart hoặc dynamic refresh integration** đã được kiểm thử, không chỉ cập nhật Secret rồi giả định tất cả Pod đã nhận giá trị mới.

## 23. App Service, Container Apps và AKS: so sánh

| Khía cạnh | App Service | Container Apps | AKS |
|---|---|---|---|
| Mức trừu tượng | Web app platform | Managed container app/revisions | Managed Kubernetes control plane, tự quản Pods |
| Config thường | Application Settings | Env vars/config revision | ConfigMap, env, files |
| Secrets | App settings/Key Vault references | Secrets/Key Vault refs theo hỗ trợ | Kubernetes Secrets/Key Vault CSI |
| Identity | Managed identity | Managed identity | Workload Identity/managed identities theo thiết kế |
| Release | Slots/continuous deployment | Revisions/traffic split | Deployments/rollouts, GitOps |
| Network | VNet Integration và private access theo plan | Container Apps environment networking | VNet/CNI/NetworkPolicy/egress |
| Refresh config | Restart/app behavior | Revision/restart/integration | Rollout or supported reload |
| Độ phức tạp | Thấp hơn với web APIs đơn giản | Trung bình, container-oriented | Cao hơn, linh hoạt nhất về Kubernetes |

**Không có nền tảng luôn tốt nhất**. Chọn theo nhu cầu platform, traffic/scale, network, compliance, đội vận hành và chi phí. Cách truyền cấu hình phải khớp nền tảng được chọn.

## 24. Azure App Configuration: cấu hình tập trung

**Azure App Configuration** cung cấp nơi quản lý **key-values, labels, feature flags** và những tích hợp để ứng dụng đọc cấu hình.

~~~text
Azure App Configuration
    Keys / labels / feature flags
       |
       | Authentication via managed identity
       v
Spring Boot application
       |
       +-- Binding to Environment/properties
       +-- Feature management integration
       +-- Refresh behavior (when configured)
       |
       v
Application behavior
~~~

### Khi nào dùng?

- Nhiều Spring Boot services cùng cần một tập config.
- Muốn theo dõi version/labels và kiểm soát rollout cấu hình.
- Có feature flags/kill switches cho tính năng.
- Cần quản lý config theo nhiều môi trường không build lại application.
- Có team/platform owner chịu trách nhiệm chuẩn hóa keys.

### Khi nào chưa cần?

Một ứng dụng nhỏ có vài biến không nhạy cảm có thể đủ với application.yml và platform environment variables. Thêm App Configuration tạo thêm **network dependency, identity, billing và quy trình vận hành**, nên phải có giá trị rõ ràng.

## 25. Keys và labels: quản lý nhiều môi trường

Một App Configuration store có thể lưu các settings với key và label:

| Key | Label | Value minh họa |
|---|---|---|
| catalog:client:timeout | dev | 10s |
| catalog:client:timeout | staging | 4s |
| catalog:client:timeout | prod | 2s |
| catalog:features:recommendations | dev | true |
| catalog:features:recommendations | prod | false |
| catalog:checkout:max-retries | prod | 1 |

**Label** là metadata của App Configuration, không tự là Spring profile. Spring profile **prod** và App Configuration label **prod** chỉ có quan hệ khi integration được cấu hình chọn đúng label.

### Chiến lược thiết kế keys

- Chọn namespace nhất quán: **service:component:property**.
- Phân biệt global defaults với environment-specific values.
- Có owner và ý nghĩa của mỗi key.
- Không nhập secrets vào plaintext config value.
- Hạn chế nhầm lẫn giữa **key** và **label**.
- Định nghĩa behavior khi key/label không tồn tại.

### Nhiều nguồn có thể xung đột

Nếu application.yml nói timeout=5s, App Configuration label prod nói 2s và environment variable nói 1s, giá trị cuối phụ thuộc **cách integration nạp PropertySources và precedence của Spring Boot**. Phải kiểm thử thực tế và ghi rõ nguồn nào là authority.

## 26. Đọc Azure App Configuration bằng Java SDK

Ví dụ **chỉ đọc một key/value không nhạy cảm** với Azure SDK for Java:

~~~java
import com.azure.data.appconfiguration.ConfigurationClient;
import com.azure.data.appconfiguration.ConfigurationClientBuilder;
import com.azure.data.appconfiguration.models.ConfigurationSetting;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class AppConfigurationReadLab {
    public static void main(String[] args) {
        String endpoint = System.getenv("APP_CONFIG_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalStateException(
                "Missing APP_CONFIG_ENDPOINT");
        }

        ConfigurationClient client =
            new ConfigurationClientBuilder()
                .endpoint(endpoint)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        ConfigurationSetting setting = client
            .getConfigurationSetting(
                "catalog:client:timeout", "dev");

        // Chỉ in key/label cho phép; không log values nhạy cảm.
        System.out.println("Read key: " + setting.getKey());
    }
}
~~~

### Điều kiện

1. Cần artifact **com.azure:azure-data-appconfiguration** và **com.azure:azure-identity** phiên bản tương thích.
2. App Configuration store/endpoint thực có tồn tại.
3. Identity được cấp quyền **App Configuration Data Reader** hoặc quyền tương đương theo tính năng.
4. Firewall/private endpoint/network đúng.
5. Key **catalog:client:timeout**, label **dev** đã có.
6. SDK/API signature phải được kiểm tra với version sử dụng.

**Đây là mã SDK để đọc cấu hình**, chưa tự gắn value vào Spring Environment. Muốn ứng dụng Spring tự nạp, chọn Spring Cloud Azure App Configuration integration hoặc cấu hình PropertySource phù hợp.

## 27. Spring Cloud Azure và Spring Boot

**Spring Cloud Azure** cung cấp starters/integration để kết nối các dịch vụ Azure theo cơ chế Spring. Các phiên bản cần tương thích với **Spring Boot** (không lấy version từ blog cũ).

Một số module hỗ trợ:

- Azure App Configuration như nguồn cấu hình.
- Azure Key Vault secrets theo cơ chế cấu hình được hỗ trợ.
- Managed identity/credentials thông qua Azure Identity.
- Các starters cho Storage, Service Bus và những dịch vụ khác.

### Cấu hình nào được chọn?

Một tích hợp App Configuration thường cần:

1. Endpoint của store.
2. Credential/managed identity.
3. Key selectors và labels.
4. Quy tắc optional vs fail startup.
5. Refresh behavior nếu cần.
6. Retry, cache, network/timeouts.

Tên properties và **spring.config.import** protocol của starter có thể thay đổi giữa các phiên bản. **Không copy một YAML fragment của Spring Cloud Azure 4.x vào 5.x/6.x mà không đọc reference documentation tương ứng**.

### Đừng import hai BOM tùy tiện

Spring Boot và Spring Cloud Azure dùng dependency management để chọn versions. Nếu ứng dụng cũng dùng Azure SDK BOM độc lập, cần kiểm tra resolved versions của **azure-core, azure-identity, Reactor/Netty** và compatibility. Không thêm explicit overrides mù quáng để sửa một lỗi runtime.

## 28. Azure App Configuration và dynamic refresh

Một số tích hợp hỗ trợ làm mới cấu hình mà không deploy image mới. Nhưng **refresh không đồng nghĩa mọi bean Java tự thay đổi**.

~~~text
Operator updates App Configuration key
          |
          v
Store version/ETag changes
          |
          v
Spring integration checks refresh (if configured)
          |
          v
PropertySource / refresh-aware bean updates
          |
          v
Effective application behavior
~~~

### Cần xác nhận

- Cơ chế refresh là polling, sentinel key hay event-driven theo integration?
- Interval và thời gian tối đa có thể trả stale?
- Bean nào được **refresh/rebind** và bean nào cần recreate/restart?
- Secret/key rotation có refresh cùng config không?
- Khi App Configuration unavailable, app dùng giá trị đã cache, fail startup, hay fallback?
- Có cách kiểm tra rollout giữa 100 replicas không?

### Những giá trị không nên đổi động tùy tiện

- Database connection URL/username hoặc credentials trong connection pool.
- TLS truststore, certificates hoặc socket settings.
- Cấu hình bean graph lớn có dependency initialization.
- Security policy cần thay đồng bộ.

Nếu thay các giá trị đó, rollout/restart có kiểm soát thường đáng tin hơn việc kỳ vọng bean đang chạy tự tái kết nối.

## 29. Feature flags khác Spring profiles

Spring profile thích hợp khi cần **cấu hình môi trường hoặc beans**. **Feature flag** phù hợp khi cần bật/tắt một hành vi mà không nhất thiết thay môi trường.

~~~text
Profile: prod
   |
   +-- Database prod
   +-- Secure logging
   +-- Retry policy prod

Feature flag: recommendations-enabled
   |
   +-- Disabled for most users
   +-- Enabled for an approved test segment
   +-- Roll back when latency/errors exceed threshold
~~~

### Feature management không tự tạo A/B test chuẩn

Những thay đổi theo segment/percentage cần thiết kế identity, consistency của assignment, monitoring và business metrics. Một user không nên thấy behavior ngẫu nhiên thay đổi giữa requests nếu bài toán đòi assignment ổn định.

**Không dùng feature flag làm cách duy nhất bảo vệ dữ liệu nhạy cảm**. Server-side authorization, RBAC và input validation vẫn bắt buộc.

### Kill switch

Một feature flag có thể tắt tạm tác vụ nặng khi backend gặp sự cố, nhưng nếu App Configuration đang unreachable, kill switch có thể không tới được ứng dụng. Cần có cache/rollout/fail-safe behavior đã kiểm thử.

## 30. Azure Key Vault: nơi lưu bí mật

Azure Key Vault quản lý những đối tượng nhạy cảm như **secrets, keys và certificates**, với quyền, audit và khả năng quản lý vòng đời phù hợp.

~~~text
App Service / Container App / AKS Pod
        |
        | Managed/Workload Identity
        v
Microsoft Entra ID
        |
        v
Azure Key Vault
        |
        +-- db-password
        +-- api-key
        +-- certificate reference
        |
        v
Spring Boot runtime (secret injected when needed)
~~~

### Không nhầm Key Vault với App Configuration

| Azure App Configuration | Azure Key Vault |
|---|---|
| Config key-values, labels, feature flags | Secrets, keys, certificates |
| Chọn theo environment/service | Giữ bí mật theo phân quyền |
| Có cơ chế refresh config theo tích hợp | Có secret versions và rotation workflows |
| Không nên lưu password plaintext | Phù hợp bảo quản password/API key khi bắt buộc |
| Cần App Configuration Data Reader role | Cần Key Vault data-plane permissions phù hợp |

### Thay secret là một workflow

1. Tạo/cập nhật secret version mới.
2. Bảo đảm runtime identity có quyền đọc.
3. Quy định cách lấy version (latest/pin) và cache TTL.
4. Đảm bảo application refresh/restart/reconnect nếu cần.
5. Xác minh auth với hệ thống đích.
6. Thu hồi secret cũ đúng thời điểm.

**Key Vault secret version đổi không tự làm database connection pool đang dùng password cũ trở nên hợp lệ**.

## 31. Đọc Key Vault secret bằng Java SDK

Ví dụ Java sau cho thấy cách tạo **SecretClient**, nhưng không in secret ra console:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class KeyVaultReadLab {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("Missing KEY_VAULT_URL");
        }

        SecretClient client =
            new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        KeyVaultSecret secret = client.getSecret("lab-service-key");
        // Trong ví dụ chỉ xác nhận metadata, không log getValue().
        System.out.println("Secret name: " + secret.getName());
    }
}
~~~

### Phân tích bảo mật

- SDK cần **com.azure:azure-security-keyvault-secrets** và **azure-identity**.
- Identity phải có quyền **get secret** trong Key Vault scope; Azure resource Reader không đủ.
- Dùng Key Vault URL HTTPS FQDN; kiểm tra DNS/private endpoint/TLS.
- **getSecret** là thao tác đọc có thể tạo audit logs và chi phí service.
- Không đặt secret value vào application logs, tracing attributes, exceptions hay test snapshots.
- Không dùng đoạn này để lấy secret production chỉ nhằm xác nhận một bài học.

Trong ứng dụng thực, integration có thể đưa secret vào Spring properties hoặc injected environment. Dù dùng cách nào, phải xác định **thời gian tồn tại của secret trong memory**, cơ chế reload và access boundaries.

## 32. Key Vault references: bản chất là tham chiếu

Một số nền tảng Azure như App Service hỗ trợ **Key Vault references** trong cấu hình ứng dụng, để nền tảng lấy secret cho app thay vì developer dán giá trị secret trực tiếp vào configuration.

~~~text
App setting DB_PASSWORD
     |
     | Key Vault reference syntax của nền tảng
     v
App Service runtime resolves reference
     |
     | Managed identity với quyền get secret
     v
Key Vault
     |
     v
Runtime receives resolved setting
~~~

### Hiểu đúng

- Reference không phải chuỗi placeholder tự hoạt động ở mọi host.
- Nền tảng phải hỗ trợ loại reference và cấu hình identity.
- **Refresh/cache semantics** khác nhau; không giả định secret đổi sẽ lập tức cập nhật process.
- Network đến Key Vault phải đúng, đặc biệt khi vault có private endpoint/firewall.
- Nếu secret URI pin một version, rotation qua version mới có thể không tự chuyển.

Trên AKS, Kubernetes Secret/CSI volume và Workload Identity là cách tiếp cận khác. Không đặt cú pháp App Service Key Vault reference vào ConfigMap rồi kỳ vọng AKS tự giải quyết.

## 33. Managed identity và workload identity

Mục tiêu của managed identity là ứng dụng Azure có thể nhận Entra access token mà không lưu client secret dài hạn trong image/repository.

~~~text
Spring Boot service chạy trên Azure
       |
       v
Managed Identity / AKS Workload Identity
       |
       v
Microsoft Entra token
       |
       +--> Azure Key Vault
       +--> Azure App Configuration
       +--> Azure Storage (SDK)
       +--> Azure SQL passwordless (khi stack hỗ trợ)
~~~

### Ba bước không được thiếu

1. Tạo/attach identity vào compute đúng cách.
2. Cấp **data-plane roles/permissions** tại Key Vault/App Configuration/Storage/SQL.
3. Đảm bảo network/DNS và SDK/driver đúng cơ chế auth.

**Identity đã attach không tự cấp quyền**. Một HTTP 403 có thể do thiếu App Configuration Data Reader, Key Vault Secrets User hay Storage Blob Data Reader tùy resource và RBAC mode.

### User-assigned managed identity

Khi ứng dụng có nhiều identities, cần chỉ rõ identity mong muốn (thường bằng client ID) theo Azure Identity SDK/integration được sử dụng. Không nên để DefaultAzureCredential vô tình chọn identity khác rồi âm thầm truy cập nhầm môi trường.

## 34. DefaultAzureCredential: local và production khác nhau

Trong Java:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

Ở laptop, credential chain có thể dùng công cụ developer đã đăng nhập; ở Azure runtime có thể dùng managed/workload identity. **Cùng dòng Java code nhưng principal thực khác nhau**.

### Không suy đoán khi gặp 403

Một developer có quyền đọc Key Vault dev nhưng pod production bị 403. Điều đó không chứng minh SDK lỗi: production identity có thể chưa được gán role, hoặc đang truy cập vault/tenant khác.

### Production security

- Sử dụng identity gắn với workload và giới hạn quyền.
- Kiểm tra tenant ID và client ID khi cần.
- Hạn chế developer credentials lọt vào production environment.
- Không set **AZURE_CLIENT_SECRET** trong container chỉ để sửa lỗi tạm mà không có kế hoạch rotation.
- Log principal identifier theo quy định audit; **không log access token**.

## 35. External secrets không giải quyết mọi security requirement

Một secret ở Key Vault vẫn có thể bị lộ nếu:

- Process dump hoặc startup logs in toàn bộ Spring Environment.
- Ứng dụng expose Actuator endpoints nhạy cảm.
- Tester đưa secret vào CI artifact hoặc report.
- Container có quyền exec/debug không được kiểm soát.
- Service identity có quyền rộng hơn mức cần thiết.
- TLS verification bị tắt để vượt Private Endpoint/DNS lỗi.

### Defense in depth

1. Key Vault data-plane RBAC tối thiểu.
2. Entra identities tách theo môi trường.
3. Private networking và TLS nếu yêu cầu.
4. Log redaction, minimal actuator exposure.
5. Rotation/expiry alert và incident response.
6. Kiểm tra effective data authorization trong ứng dụng.

Không có một “secret store” nào làm cho giá trị nhạy cảm vô hại khi đã được ứng dụng đọc vào memory.

## 36. Kết nối Azure SQL theo từng môi trường

Một Spring Boot service thường dùng DataSource/JDBC connection pool. Tách JDBC URL, username, authentication và pool settings theo môi trường:

~~~yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USER}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

Ví dụ này dành cho **password-based JDBC flow** khi được tổ chức cho phép; có thể chọn Microsoft Entra passwordless authentication theo tính năng JDBC driver/Cloud Azure integration và Azure SQL configuration tương ứng.

### Không nhầm database URL với secret

JDBC URL và hostname thường là configuration, nhưng có thể chứa username/password hoặc token trong query parameters; khi đó cả chuỗi phải được coi là nhạy cảm. Đừng đưa full JDBC URL vào error logs mà không xem thành phần credentials.

### Các điểm cần kiểm tra khi triển khai

1. Database server FQDN, region và database name.
2. Azure SQL firewall/Private Endpoint/DNS/VNet route.
3. TLS và JDBC driver certificate validation.
4. Database login/Entra principal và quyền **schema/table**.
5. Hikari max pool size theo tổng số replicas.
6. Timeout/retry theo request deadline.
7. Schema migrations có được triển khai đúng một lần với approval không?

### Connection pool và autoscaling

~~~text
30 replicas
  x 10 connections/replica
  = 300 connections tiềm năng
~~~

Nếu database tier không phù hợp, autoscale thêm pods có thể làm tăng connection pressure. Thiết kế pool size và max replicas cùng với database connection limits; không xem “mỗi pod pool 100” là an toàn vì Java memory còn đủ.

## 37. Passwordless connection với Microsoft Entra

Một kiến trúc có thể thay database password bằng Entra authentication:

~~~text
Spring Boot trên Azure
       |
       v
Managed/Workload Identity
       |
       v
Microsoft Entra access token
       |
       v
JDBC driver / integration hỗ trợ token
       |
       v
Azure SQL database principal + permissions
~~~

### Có cần spring.datasource.password?

Không nếu sử dụng flow passwordless đúng cách, nhưng **điều này phụ thuộc driver, integration, authentication properties, database principal và token refresh support**. Không áp file cấu hình password-based lên flow passwordless rồi thay password bằng một token tĩnh lấy một lần khi khởi động.

### Trước khi chuyển đổi

- Xác minh Microsoft JDBC Driver for SQL Server và authentication mode được hỗ trợ.
- Tạo/cấp database principal và permissions đúng cho managed identity.
- Kiểm tra cơ chế refresh token cho long-lived connection pools.
- Thử reconnect, failover, network outage và token expiry.
- Có rollback không đặt secret production vào source/CI logs.

**Passwordless giảm gánh nặng quản lý secret tĩnh**, không loại bỏ yêu cầu IAM, TLS, firewall và kiểm toán.

## 38. Redis, Service Bus và Storage: config cũng cần tách

Một microservice có thể nói chuyện với nhiều Azure resources:

~~~text
catalog-api (profile prod)
    |
    +-- Azure SQL:  prod SQL server/database
    +-- Redis:      prod Redis FQDN/TLS port
    +-- Service Bus: prod namespace/queue
    +-- Blob:       prod storage endpoint/container
    +-- Key Vault:  prod vault URL
    +-- App Config: prod store endpoint/label
~~~

### Ví dụ custom keys

~~~yaml
app:
  azure:
    blob-container: "${AZURE_BLOB_CONTAINER}"
    service-bus-queue: "${AZURE_SERVICEBUS_QUEUE}"
    redis-host: "${REDIS_HOST}"
    redis-tls-port: "${REDIS_PORT}"
~~~

Đây là custom properties; để tạo SDK client cần code hoặc Spring Cloud Azure integration tương ứng. Không dùng một biến **AZURE_CONNECTION_STRING** chung chứa toàn bộ secrets cho nhiều services chỉ để giảm số biến.

### Tách namespace ở mọi tầng

Khác profile không đủ nếu env vars vẫn trỏ tới một production resource. Hãy dùng **resource identifiers/names, separate identities, RBAC and network policies** để ngăn kết nối nhầm môi trường.

## 39. Private Endpoint và DNS: lỗi cấu hình hay lỗi hạ tầng?

~~~text
Java pod/App Service
       |
       | resolve storage/database FQDN
       v
DNS resolver + Private DNS zone
       |
       v
Private IP / approved endpoint route
       |
       v
Azure resource with firewall and identity checks
~~~

### Một request có thể thất bại ở nhiều tầng

| Lỗi | Nguyên nhân thường gặp | Thao tác kiểm tra |
|---|---|---|
| UnknownHostException | Hostname sai hoặc private DNS chưa liên kết | Resolve từ workload runtime |
| Connect timeout | Route, firewall, NSG, cổng hoặc endpoint chặn | Kiểm tra TCP path |
| SSLHandshakeException | CA, hostname, SNI hoặc truststore | Kiểm tra TLS chain, FQDN |
| HTTP 401 | Credential/token/audience | Entra auth logs, identity |
| HTTP 403 | Data-plane role hoặc service firewall | Principal, RBAC, firewall diagnostics |
| SQL login failed | Database principal/auth mode/permissions | SQL logs, JDBC config |
| Connection pool exhausted | Quá nhiều replicas/connection hoặc network chậm | Pool metrics/DB limits |

**Không bật public network access cho mọi địa chỉ hay tắt TLS verification để làm ứng dụng vượt lỗi**. Private Endpoint phải phối hợp DNS, route, service firewall và identity.

### Profile không điều khiển VNet

Đặt **SPRING_PROFILES_ACTIVE=prod** không tự chuyển traffic qua Private Endpoint. Network setup nằm ở Azure infrastructure/container environment, cần được quản lý bằng IaC và kiểm chứng riêng.

## 40. Actuator: sức khỏe ứng dụng và thông tin cấu hình

**Spring Boot Actuator** có thể cung cấp health/metrics và các management endpoints tùy dependency/configuration:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Đường dẫn có thể khác nếu ứng dụng thay management base path/port hoặc sử dụng actuator probes paths khác. Chỉ bật endpoint và probes được tổ chức cho phép.

### Ba loại tín hiệu

| Tín hiệu | Ý nghĩa | Cần tránh |
|---|---|---|
| **Liveness** | Process/ứng dụng có còn sống để phục vụ không? | Không phụ thuộc DB bên ngoài một cách không cần thiết |
| **Readiness** | Pod/instance hiện có thể nhận traffic không? | Không xem readiness là minh chứng mọi external services đều khỏe tuyệt đối |
| **Startup** | Ứng dụng có đủ thời gian khởi động không? | Restart loop khi Java warm-up/JIT/config fetch chậm |

### Một bẫy gây cascade failures

Nếu liveness probe kiểm tra Redis/SQL availability, một lỗi Redis tạm thời có thể làm Kubernetes restart hàng trăm pods cùng lúc, khiến connection storm trầm trọng hơn.

Tách liveness khỏi dependencies bên ngoài; kiểm tra readiness theo nhu cầu phục vụ traffic, có timeout và fallback phù hợp. Cần thử trên nền tảng thật, không chỉ xem HTTP 200 một lần.

## 41. Actuator /env và /configprops: rủi ro tiết lộ secrets

Spring Boot Actuator có các endpoint như **/actuator/env** và **/actuator/configprops** khi được bật. Chúng phục vụ chẩn đoán nhưng có nguy cơ lộ thông tin cấu hình nhạy cảm nếu exposure/sanitization sai.

### Chính sách an toàn

- Không expose toàn bộ management endpoints ra Internet.
- Chỉ bật **health/info** hoặc endpoint cần thiết và được review.
- Bảo vệ management port/path bằng authentication/network policy khi có.
- Không dựa hoàn toàn vào giá trị mặc định sanitization.
- Đừng in toàn bộ Spring Environment khi startup.
- Giới hạn quyền xem logs, heap dumps, thread dumps và process environment.

**Dữ liệu nhạy cảm có thể lộ qua cả exception messages hoặc connection URL**, không chỉ Actuator. Trước khi bật debug config, cần biết nội dung sẽ được ghi.

## 42. Log levels, sampling và cấu hình theo môi trường

~~~yaml
# application.yml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

~~~yaml
# application-dev.yml
logging:
  level:
    com.example.catalog: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

### Debug trong production cần gì?

Khi xảy ra sự cố, có thể tăng log level cho một package trong thời gian ngắn theo change control, nhưng:

- Không bật payload/header logging chứa tokens/passwords.
- Có thời hạn tự hoàn nguyên và owner.
- Giới hạn retention/truy cập dữ liệu log.
- Đo log ingestion volume và chi phí Log Analytics/Application Insights.
- Không dùng DEBUG lâu dài như cấu hình mặc định của prod.

### Correlation IDs

Log nên có **traceId/correlationId, service, environment, application version**, operation outcome và latency. Không cho environment name trở thành PII và không đưa secrets vào tags.

## 43. Retry, timeout và circuit breaker theo môi trường

Một API chạy trong Azure có thể phụ thuộc SQL, Redis, Service Bus hoặc REST service. Những timeout/retry policies có thể khác theo network/SLO:

~~~yaml
app:
  remote:
    connect-timeout: 1s
    read-timeout: 3s
    max-retries: 2
    circuit-breaker-enabled: true
~~~

### Giới hạn quan trọng

- Nếu HTTP SLO là 300 ms, read timeout 3s sẽ không đáp ứng được trong request path; con số trên **chỉ minh họa cấu trúc config**.
- Retry cần **deadline chung**, bounded attempts, backoff/jitter.
- Không retry vô hạn 401/403 khi principal thiếu quyền.
- Ghi có tác dụng phụ cần idempotency.
- Circuit breaker fallback phải phù hợp nghiệp vụ, không bỏ qua authorization hoặc giới hạn tài chính.

### Config không tự kích hoạt hành vi

Nếu code không bind **app.remote.max-retries** vào RestClient/WebClient/Resilience4j/SDK client, đổi YAML không làm retry thực tế thay đổi. Cần **integration tests** chứng minh cấu hình đi đến đúng bean.

## 44. Startup khi config service đang lỗi

Một ứng dụng đọc App Configuration/Key Vault lúc startup sẽ phụ thuộc:

~~~text
Spring Boot startup
      |
      +--> Resolve App Configuration
      +--> Resolve Key Vault secret/reference
      +--> Build database/DataSource clients
      +--> Start web server / readiness
~~~

### Hai chính sách

**Fail fast:** nếu config bắt buộc thiếu, ứng dụng không ready. Phù hợp khi chạy tiếp có thể gây kết nối nhầm hoặc lỗ hổng bảo mật.

**Graceful fallback:** nếu config tùy chọn thiếu, sử dụng giá trị local/cache được phê duyệt và báo cảnh báo. Phù hợp feature không quan trọng khi không gây thay đổi rủi ro.

### Khi App Configuration unreachable

Không luôn tiếp tục với defaults. Nếu flag **disable-payments** không đọc được mà ứng dụng tự bật thanh toán, có thể sai business safety. Chọn fallback behavior theo criticality, có stale TTL/owner và test mạng bị ngắt.

### Configuration cache

SDK/integration có thể cache config theo cách riêng. **Độ cũ của config** là một thuộc tính vận hành phải được đo/ghi rõ, nhất là khi flag dùng cho incident response.

## 45. Configuration drift và một nguồn sự thật

**Configuration drift** xảy ra khi trạng thái runtime thực khác trạng thái mong muốn:

~~~text
IaC (desired):
   APP_FEATURES_RECOMMENDATIONS=false

Portal hotfix:
   APP_FEATURES_RECOMMENDATIONS=true

Actual production:
   true

Next IaC deployment:
   có thể đưa về false hoặc thất bại vì conflict
~~~

### Phòng ngừa

1. Quản lý cấu hình không nhạy cảm qua Git/IaC có review.
2. Dùng Key Vault cho bí mật với audit/rotation.
3. Hạn chế quyền sửa Portal trực tiếp trên production.
4. Gắn owner và lý do cho emergency override.
5. Sau hotfix, cập nhật **desired state** hoặc rollback có chủ đích.
6. Dùng deployment verification để phát hiện cấu hình không khớp.

**Không xuất toàn bộ effective configuration chứa secrets ra artifact để so diff**. So sánh key names, hashes hợp lệ, version IDs hoặc redacted values theo chính sách.

## 46. IaC và quản lý cấu hình theo vòng đời ứng dụng

Các công cụ như **Bicep, ARM templates, Terraform, Helm và GitOps** giúp mô tả:

- Azure resources và network.
- App Service settings/slot flags.
- Container Apps environment variables/secret references.
- Kubernetes ConfigMaps/Secret references và rollout behavior.
- Identity assignments và RBAC.
- App Configuration keys/labels theo quy trình phù hợp.

### Không đưa secrets vào IaC state/logs

Một template có trường password vẫn có thể làm lộ qua source, pipeline variables, plan/state hoặc outputs. Dùng **Key Vault references, identity-based integration và secret handling** của công cụ thay vì nhúng giá trị thực.

### Một quy trình đề xuất

~~~text
Pull Request:
  code change
  + config schema/defaults
  + infra config change
      |
      v
CI:
  compile/unit tests
  + config validation
  + IaC plan/policy scan
      |
      v
Approve DEV -> TEST -> STAGING
      |
      v
Canary/slot/revision rollout PROD
      |
      v
Smoke tests + monitor + rollback plan
~~~

Không cần tạo một container image mới chỉ để đổi một feature flag, nhưng **một thay đổi config quan trọng vẫn cần quy trình kiểm soát tương đương deployment**.

## 47. Kiểm tra cấu hình trong CI trước khi deploy

Những validation có ích:

| Nhóm | Ví dụ |
|---|---|
| **Schema** | app.client.read-timeout có kiểu Duration hợp lệ |
| **Required** | PROD_SQL_ENDPOINT được cấp ở prod |
| **Range** | max-retries không âm và không quá giới hạn |
| **Profiles** | prod không vô tình bật local-only bean |
| **Secrets** | Không có password/API key trong Git |
| **Identity** | Runtime managed identity đã được cấp quyền cần thiết |
| **Endpoint** | Không trỏ production sang localhost/dev FQDN |
| **Networking** | Private endpoint/DNS/port và TLS test đạt |
| **Security** | Actuator endpoints được giới hạn |
| **Observability** | Health, traceId, environment, log redaction |

### Phân biệt test config và test production secrets

CI không nên cần quyền đọc toàn bộ secrets production để biên dịch. Schema/config binding tests có thể dùng dummy values. **Smoke tests** tại staging/prod dùng workload identity/secret reference của chính môi trường, theo quyền tối thiểu.

## 48. Kiểm thử Spring Boot profiles

Một integration test có thể dùng active profile:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertTrue(environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("test")
        ));
    }
}
~~~

### Test này chứng minh gì?

Nó chứng minh Spring Environment có active profile **test** trong context test. Nó **không chứng minh** database URL, HTTP timeouts, Key Vault permission hoặc Azure Private Endpoint đã đúng.

### Test tốt hơn

Thêm assertion trên **ClientProperties** đã bind và validate, chẳng hạn timeout và maxRetries theo application-test.yml; dùng dummy external services hoặc container test environment, không gọi Azure production.

**Không chỉ dùng @ActiveProfiles("prod") để chứng minh cấu hình Azure production đúng** nếu pipeline test không cấp cùng external config sources/identity/network.

## 49. Đo effective config không làm lộ secret

Một lỗi deployment xảy ra khi application.yml nói timeout=5s, nhưng biến môi trường ở App Service override thành 50s. Để điều tra:

1. Xác minh profile được chọn từ **SPRING_PROFILES_ACTIVE**.
2. Ghi lại application version và environment name.
3. Xem nguồn property theo công cụ quản trị an toàn.
4. Với key không nhạy cảm, so sánh giá trị dự kiến và giá trị bind vào bean.
5. Với secret, chỉ kiểm tra **có/không**, secret version ID/metadata được cho phép, hoặc kết quả auth; không in giá trị.
6. Kiểm tra configuration refresh/restart đã diễn ra chưa.

### Ví dụ log tốt

~~~json
{
  "service": "catalog-api",
  "environment": "staging",
  "version": "1.8.0",
  "profiles": ["staging"],
  "configSource": "App Configuration",
  "configRevision": "approved-revision-42",
  "dbCredentialPresent": true,
  "startup": "success"
}
~~~

Tên **configRevision** là ví dụ metadata có kiểm soát, không mặc định là property có sẵn trong Spring Boot hay App Configuration. Không ghi giá trị **dbCredential** hoặc full URI có secret.

## 50. Configuration change có cần restart?

Không có một quy tắc duy nhất:

| Loại thay đổi | Điều cần kiểm tra |
|---|---|
| application.yml bên trong JAR | Thường cần artifact mới/restart để nạp nội dung mới |
| App Service application setting | Restart/config semantics theo nền tảng |
| Container Apps revision env var | Revision/rollout semantics |
| Kubernetes Pod env từ ConfigMap/Secret | Thường cần Pod restart/rollout để nạp vào process |
| Mounted file config | Volume refresh và Spring reload mechanism |
| App Configuration key | Integration refresh, cache interval và bean rebinding |
| Key Vault new secret version | Secret reference cache/refresh và client reconnect |
| JDBC URL/credentials | Pool recreation/re-auth và tính liên tục nghiệp vụ |

### Khi nào nên restart có chủ đích?

- Database endpoint/authentication đổi.
- TLS certificate/truststore cần cập nhật.
- Bean graph hoặc connection pools cần khởi tạo lại.
- Thay cấu hình không có cơ chế dynamic refresh đã kiểm thử.

**Dynamic refresh** phù hợp một số feature flags, timeouts hoặc settings được thiết kế để refresh; đừng áp nó bừa bãi cho mọi Spring bean.

## 51. Canary, slot swap và rollback cấu hình

Một cấu hình mới có thể gây lỗi dù không đổi Java code:

~~~text
Production: config revision C1
      |
      v
Staging tests: config revision C2
      |
      v
Deploy canary/slot/revision C2
      |
      +-- Error rate/latency OK -> promote C2
      |
      +-- Threshold exceeded -> rollback C1
~~~

### Cần rollback những gì?

- Config key/label version được thay.
- Secret reference/version/identity quyền tương ứng.
- Container image/Java artifact nếu code phụ thuộc config schema mới.
- DNS/network/Private Endpoint/IaC changes.
- Database schema hoặc migrations nếu có.

**Rollback config không đồng nghĩa rollback dữ liệu**. Ví dụ bật một feature đã tạo dữ liệu schema mới; quay lại flag false có thể vẫn để lại dữ liệu mới mà code cũ không hiểu. Cần quy trình backward-compatible migrations và feature rollout.

### Các chỉ số quan sát sau rollout

1. Startup failures, readiness failures, crash loops.
2. 401/403 do identity/secret và 5xx do backend.
3. API p95/p99 latency, timeout/retry count.
4. Database connections và throughput.
5. Feature-level business metrics.
6. Log/telemetry volume và chi phí.

## 52. Tối ưu chi phí cấu hình trên Azure

Quản lý config cũng có chi phí:

| Thành phần | Chi phí cần đánh giá |
|---|---|
| **Azure App Configuration** | Tier, requests, storage/replicas theo tính năng và pricing |
| **Azure Key Vault** | Secret/key operations, networking, service tier theo giá |
| **App Service/Container Apps/AKS** | Compute, networking, scaling, log volume |
| **Private Endpoints** | Endpoint/network charges tùy Azure pricing |
| **Azure Monitor/Log Analytics** | Ingestion, retention, queries |
| **Azure SQL/Redis/Storage** | Connection/load, transactions, data transfer |

### Quá nhiều reads cũng tạo tải

Nếu mỗi Java request HTTP đều gọi Key Vault lấy cùng một secret, ứng dụng tăng latency, chi phí và nguy cơ throttling. Thông thường cần **cơ chế caching/refresh đã được thư viện/nền tảng hỗ trợ** thay vì fetch secret trên mọi business request.

### Không cache bí mật vô thời hạn

Cache quá lâu khiến rotation không có hiệu lực kịp. Cần cân bằng **cost, rate limits, security policy và secret refresh SLA**.

### Cách đo

- Số requests tới App Configuration/Key Vault theo dịch vụ.
- Configuration refresh/error rate.
- Startup duration và instance scale events.
- Key Vault 429/authorization failures.
- Log volume.
- Total Azure Cost Management theo resources/tags.

Không đưa một đơn giá USD cố định vào thiết kế vì region/tier/mức giá thay đổi. Tính dự toán với **Azure Pricing Calculator** và bill thực.

## 53. Lab A: kiểm chứng profile và environment precedence

**Mục tiêu:** kiểm tra Spring Boot có lấy đúng values theo local, dev và prod hay không, không gọi tài nguyên Azure thật.

### Chuẩn bị

- Một Spring Boot 3.x Java project riêng trong môi trường học.
- application.yml, application-dev.yml, application-prod.yml theo mục 6–7.
- ClientProperties và registration theo mục 14.
- JDK và Spring Boot dependencies phù hợp.
- Không cần database/secret production.

### Các bước

1. Đặt **app.client.connect-timeout=2s** trong application.yml.
2. Trong application-dev.yml override thành **5s**.
3. Khởi động với **SPRING_PROFILES_ACTIVE=dev**.
4. Test ClientProperties.connectTimeout() trả **5s**.
5. Thêm biến môi trường **APP_CLIENT_CONNECTTIMEOUT=900ms**.
6. Khởi động lại và kiểm tra bind trả **900ms**.
7. Xóa biến override, khởi động với profile **prod**.
8. Kiểm tra timeout trở về giá trị nền hoặc giá trị prod đã khai báo.
9. Thử truyền một Duration không hợp lệ trong môi trường test và xác minh **startup fail**, không dùng default insecure.
10. Dừng ứng dụng và xóa test env variables khỏi shell/session.

### Nghiệm thu

| Trường hợp | Giá trị mong đợi |
|---|---|
| Không active profile, không override | 2s |
| Profile dev | 5s |
| Dev + APP_CLIENT_CONNECTTIMEOUT=900ms | 900ms |
| Profile prod, không có override cùng key | Giá trị nền/prod theo file |
| Giá trị sai kiểu hoặc validation fail | Startup báo lỗi có tên key, không lộ secret |

**Không in toàn bộ Spring Environment** để xác minh. Có thể viết assertion trong unit/integration test để tránh log nhầm bí mật.

## 54. Lab B: Spring Boot trên Azure App Service staging

**Mục tiêu:** cấp cấu hình từ platform mà không sửa JAR. Chỉ thực hiện trên **App Service lab**, không thay đổi production.

### Điều kiện

1. Có resource group và App Service lab được cấp phép.
2. Đã xây JAR/container image test; không dùng tài nguyên người dùng thật.
3. Có quyền thay application settings trong scope lab.
4. Có endpoint/Key Vault dev phù hợp nếu bài thực hành cần.
5. Đã kiểm tra tier có hỗ trợ deployment slots nếu muốn thử swap.

### Quy trình

1. Deploy artifact vào lab Web App hoặc staging slot.
2. Đặt **SPRING_PROFILES_ACTIVE=staging** từ App Settings.
3. Đặt **APP_CLIENT_CONNECTTIMEOUT=1s**, không hard-code trong JAR.
4. Thêm một config không nhạy cảm khác như **APP_FEATURES_RECOMMENDATIONS=false**.
5. Khởi động/restart theo platform behavior, kiểm tra health/readiness.
6. Kiểm thử endpoint chức năng đã bind timeout.
7. Gắn managed identity và cấp App Configuration Data Reader hoặc Key Vault data access **chỉ nếu scope lab được phê duyệt**.
8. Nếu dùng Key Vault reference, kiểm tra reference resolution mà không in secret value.
9. Kiểm tra app logs không có raw env vars, access tokens hoặc connection strings.
10. Nếu thử slot swap, xác nhận **slot-sticky settings** và có rollback; không thử swap trên production.

### Kết quả PASS

- Không rebuild ứng dụng để thay một timeout.
- Profile staging được kích hoạt.
- App Health báo đúng trạng thái.
- Identity và network chỉ truy cập được tài nguyên lab.
- Không có secret trong source hoặc log.
- Có dấu vết thay đổi cấu hình và phương án rollback.

## 55. Lab C: AKS ConfigMap/Secret và restart semantics

**Mục tiêu:** hiểu khác biệt giữa cấu hình file/runtime và giá trị environment đã nạp vào process.

### Chuẩn bị

- AKS namespace lab với RBAC giới hạn.
- Image Spring Boot thử nghiệm, không chứa secrets.
- ConfigMap và Secret lab **không phải production**.
- Pod security và network policy phù hợp.

### Quy trình

1. Tạo ConfigMap chứa **client-connect-timeout=2s** theo quy trình lab.
2. Tạo Secret lab chứa một chuỗi giả được phê duyệt, không dùng password thật.
3. Deploy cấu hình minh họa ở mục 22 vào namespace lab.
4. Xác minh Pod Ready và Spring binding đúng.
5. Thay ConfigMap thành **5s**, nhưng **chưa restart Pod**.
6. Quan sát: giá trị được đưa qua Pod environment **không tự thay đổi** trong process đang chạy.
7. Thực hiện rollout restart theo hướng dẫn vận hành lab.
8. Xác minh Pod mới nhận giá trị **5s**.
9. Kiểm tra Secret không xuất hiện trong logs/ConfigMap.
10. Cleanup resources lab theo owner.

### Bài học quan trọng

Kubernetes ConfigMap và Secret là một phần của platform configuration. Spring Boot không tự theo dõi mọi thay đổi resource Kubernetes rồi refresh beans. Muốn dynamic config cần **reloader/refresh mechanism** được thiết kế và kiểm chứng, còn không hãy rollout có chủ đích.

## 56. Lab D: App Configuration và Key Vault với quyền đọc tối thiểu

**Mục tiêu:** phân biệt config thường và secret, đồng thời xác nhận data-plane identity.

### Chuẩn bị

- App Configuration store lab.
- Key Vault lab.
- Managed identity hoặc developer identity được cấp quyền hẹp.
- Java project đã có Azure SDK dependency phù hợp.
- Lab key/value và secret **giả**.

### Các bước

1. Tạo key **catalog:client:timeout** với label **dev**, value **2s** trong App Configuration lab.
2. Tạo secret **lab-service-key** trong Key Vault lab bằng chuỗi thử nghiệm không nhạy cảm.
3. Cấp App Configuration Data Reader cho identity tương ứng.
4. Cấp quyền **get** secret theo Key Vault authorization model hiện dùng.
5. Chạy đoạn Java read-only ở mục 26/31.
6. Xác minh chỉ tên key/secret được log, không in secret value.
7. Thử identity thiếu quyền **chỉ trong lab** để hiểu lỗi 403.
8. Đánh giá private DNS, TLS và network khi truy cập có firewall.
9. Kiểm tra khả năng secret refresh/rotation mà không thay production secret.
10. Xóa hoặc thu hồi những quyền lab được cấp riêng cho bài theo quy trình.

### PASS khi

- Cấu hình thường đọc từ App Configuration.
- Bí mật được giữ trong Key Vault, chỉ identity được phép đọc.
- Java authentication dùng Entra/managed identity thay client secret hard-code.
- Logs không chứa secret values hoặc access tokens.
- Network và RBAC errors được phân biệt.

## 57. Case study: nền tảng bán hàng Spring Boot đa môi trường

Một công ty có hệ thống catalog, checkout và notification:

- **Spring Boot 3.x** chạy trên Azure Container Apps ở dev/staging.
- **AKS** chạy một phần production Java services.
- **Azure SQL Database** lưu đơn hàng và inventory.
- **Azure Redis** làm cache catalog.
- **Azure Service Bus** xử lý sự kiện xác nhận đơn.
- **Azure Blob Storage** lưu ảnh sản phẩm.
- **Azure App Configuration** quản lý feature flags và timeouts.
- **Azure Key Vault** giữ những secrets chưa chuyển sang passwordless.
- **Microsoft Entra Workload Identity/managed identity** để truy cập dịch vụ.
- Private Endpoints cho một số data services.
- API p95 yêu cầu 250 ms; mỗi deployment có thể scale 3–50 replicas.

### Bài toán

Trong một đợt triển khai, staging chạy ổn nhưng production gặp ba vấn đề:

1. Container Apps revision mới bị restart loop vì biến **APP_CLIENT_CONNECT_TIMEOUT** không bind vào **app.client.connect-timeout**; cấu hình fallback sai khiến client timeout quá dài.
2. AKS Pod đọc được App Configuration nhưng không lấy được Key Vault secret do Workload Identity chưa có data-plane permission.
3. API production dùng JDBC pool 30 connections mỗi Pod; khi scale lên 50 Pods, database quá tải.

### Nhiệm vụ phân tích

1. Lập bảng config ownership: image/default, App Configuration, Key Vault, platform env.
2. Đặt tên canonical cho timeout env var và tạo startup validation.
3. Giải thích cách chọn profile **prod** nhưng vẫn không bảo đảm endpoints/resource đúng.
4. Phân tách identity và Key Vault data-plane role cho từng service.
5. Kiểm tra Private Endpoint/DNS/TLS từ AKS Pod thay vì laptop.
6. Tính tổng số database connections tiềm năng.
7. Điều chỉnh pool size/max replicas dựa trên Azure SQL tier và đo tải.
8. Thiết kế retry deadline phù hợp p95 250 ms.
9. Chọn config nào nên refresh động, config nào nên rollout restart.
10. Thiết kế App Service slot hoặc Container Apps revision/AKS rolling update để canary.
11. Đề xuất cách rollback config không gây sai dữ liệu.
12. Thiết kế alerts cho auth failures, startup readiness, DB connection exhaustion.
13. Đưa emergency config override vào IaC desired state sau incident.
14. Nêu metrics để chứng minh feature rollout thành công.

### Hướng giải

**Timeout:** Dùng **APP_CLIENT_CONNECTTIMEOUT** theo mapping chuẩn cho **app.client.connect-timeout**, bind vào ClientProperties có validation; test production-like effective config trước rollout.

**Key Vault:** Xác định ServiceAccount/workload identity hoặc managed identity thật của Pod, cấp quyền đọc secret phù hợp trong scope vault lab/prod tương ứng, kiểm tra federation, Key Vault network và logs 403. Không dùng access key trong source để né lỗi.

**Database:** **50 pods × 30 connections = 1.500 connections tiềm năng**, chưa tính background jobs/rollout. Sizing pool phải dựa trên workload, max replicas và DB capacity; không scale pod vô hạn nếu SQL không chịu được.

**Rollout:** Giữ image digest cố định, canary config theo revision/Deployment, kiểm tra readiness, p95/5xx/auth error, sau đó mới tăng traffic. Quay lại cấu hình được phê duyệt nếu metrics xấu; schema/data changes cần rollback plan riêng.

## 58. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Thay thế |
|---|---|---|
| Lưu password prod trong application.yml | Có thể commit Git/image | Key Vault hoặc nền tảng secrets |
| Kích hoạt prod profile là đủ bảo mật | Không quản lý IAM/network | Tách resource, identity, RBAC, private routes |
| Dùng APP_CLIENT_CONNECT_TIMEOUT và giả định luôn bind | Relaxed binding có quy tắc | Dùng canonical env names và test |
| Đặt spring.profiles.active trong application-prod.yml | Profile activation cấu hình không hợp lệ/khó đoán | Đặt từ deployment environment |
| Dùng một secret chung cho dev/prod | Blast radius lớn | Tách secrets và identities |
| In /actuator/env để debug | Có thể lộ cấu hình nhạy cảm | Redacted config metadata và scoped access |
| Key Vault đổi secret thì mọi pool tự refresh | Caching/connection lifecycle | Refresh/restart/reconnect có kiểm thử |
| Thay ConfigMap là Pod env tự đổi | Environment được snapshot khi start | Rollout hoặc supported refresh |
| Dùng App Configuration lưu token plaintext | Sai mục tiêu secret management | Key Vault/managed identity |
| Lỗi 403 thì cấp Owner subscription | Quá rộng và có thể không sửa data plane | Xác định principal/scope/role cụ thể |
| Private Endpoint nghĩa là không cần TLS | Mạng riêng và TLS phục vụ mục đích khác nhau | Giữ HTTPS/TLS verification |
| Tăng replicas mà không xem connection pools | Có thể làm SQL/Redis quá tải | Total connection budget |
| Liveness kiểm tra SQL/Redis rồi restart Pod | Gây cascading failures | Liveness độc lập, readiness/fallback phù hợp |
| Feature flag có thể thay authorization | Sai security boundary | Server-side authorization/RBAC |
| Canaries dùng secrets production trên dev | Rò rỉ dữ liệu và tăng blast radius | Identity/secrets tách môi trường |
| Chỉ rollback image mà không xem config/data | Có thể vẫn lỗi | Rollback kế hoạch cả config/schema/identity |
| Test profile thành công là network prod đã đúng | Không có private DNS/roles thật | Integration/smoke tests tại Azure |
| Log mọi env var để kiểm chứng precedence | Secret leakage | Log key names/redacted values và config revision |

## 59. Checklist triển khai production

| Nhóm | Điều kiện nghiệm thu |
|---|---|
| **Artifact** | Một image/JAR version có thể deploy nhiều môi trường |
| **Profiles** | Active profile explicit, có test precedence và không nhầm môi trường |
| **Config schema** | @ConfigurationProperties + validation cho settings quan trọng |
| **Secrets** | Không hard-code, Key Vault/secret reference được quản lý |
| **Identity** | Managed/Workload Identity và quyền tối thiểu |
| **Endpoint** | Không trỏ prod về dev/localhost |
| **App Configuration** | Key/label namespace, authority, refresh SLA, owner |
| **Key Vault** | Secret rotation/reload/reconnect workflow đã thử |
| **Networking** | Private DNS/TLS/NSG/firewall/Private Endpoint hoạt động |
| **Database** | JDBC auth, pool size × max replicas trong capacity |
| **Redis/Messaging** | Endpoint, port, auth mode và retry/idempotency phù hợp |
| **Platform** | App Service slots, Container Apps revisions hoặc AKS rollouts được quản trị |
| **Kubernetes** | Không chứa secrets trong ConfigMap/Git; Pod restart semantics rõ |
| **Health** | Startup/liveness/readiness probes không gây cascade failures |
| **Actuator** | Chỉ expose endpoints cần thiết, có bảo vệ |
| **Logging** | Redaction và tránh PII/secrets; log volume trong budget |
| **Reliability** | Timeout/retry/circuit breaker trong request deadline |
| **CI/CD** | Config validation, policy scan, IaC reviews và smoke tests |
| **Drift** | Có desired state và audit các thay đổi Portal/hotfix |
| **Rollout** | Canary/slot/revision, traffic controls và rollback |
| **Monitoring** | Startup, 401/403/5xx, latency, refresh và pool metrics |
| **Cost** | App Configuration/Key Vault calls, platform, network và logs được đo |
| **Runbook** | Owner/incident steps, secret rotation và rollback rõ |

## 60. Câu hỏi tự kiểm tra

1. Configuration, secret và business data khác nhau thế nào?
2. Vì sao nên build một image dùng ở nhiều Azure environments?
3. Spring Boot profile có tự tạo RBAC và VNet isolation không?
4. application.yml và application-prod.yml được nạp trong tình huống nào?
5. Có nên đặt spring.profiles.active trong profile-specific file không?
6. spring.config.activate.on-profile giúp giải quyết nhu cầu gì?
7. Vì sao nhiều active profiles có thể tạo ghi đè khó đoán?
8. Phân biệt spring.config.location, additional-location và import.
9. Environment variable tương ứng của app.client.connect-timeout là gì?
10. @Value và @ConfigurationProperties khác nhau về type safety/validation?
11. Nếu key bắt buộc thiếu, vì sao fail fast an toàn hơn default trỏ localhost?
12. App Service Application Settings được Spring nhận thế nào?
13. Vì sao cần slot-sticky settings khi swap App Service slots?
14. Container Apps revision và secret refresh có luôn đồng nghĩa không?
15. ConfigMap và Kubernetes Secret khác nhau thế nào?
16. Base64 trong Kubernetes Secret có phải encryption không?
17. Thay Kubernetes ConfigMap có tự cập nhật env var của Pod đang chạy không?
18. AKS Workload Identity cần cấu hình nào ngoài Java code?
19. Azure App Configuration phù hợp với thông tin gì?
20. App Configuration labels có tự kích hoạt Spring profiles không?
21. Dynamic refresh có tự thay tất cả Spring beans không?
22. Feature flag khác profile và authorization ở điểm nào?
23. Key Vault secret version đổi có tự cập nhật JDBC connection pool không?
24. Managed identity có tự được quyền đọc Key Vault không?
25. DefaultAzureCredential ở laptop và AKS có luôn chọn cùng principal không?
26. App Configuration Data Reader và Key Vault data-plane permission khác nhau ra sao?
27. Private Endpoint có thay TLS không?
28. Vì sao JDBC pool size phải nhân với số replicas tối đa?
29. Liveness và readiness checks nên phụ thuộc database khác nhau thế nào?
30. Vì sao không nên expose /actuator/env ra Internet?
31. Các retry/timeout config có tự tác động lên SDK client chưa được bind không?
32. Khi App Configuration unavailable, khi nào cần fail fast?
33. Configuration drift là gì?
34. Bicep/Terraform có thể làm lộ bí mật ở đâu?
35. Khi nào dynamic refresh thích hợp hơn rollout restart?
36. Vì sao cần kiểm thử effective config mà không log secret values?
37. Một lỗi HTTP 403 có thể đến từ identity, RBAC hay firewall?
38. Một lần rollback image có tự rollback schema/data changes không?
39. Những metric nào nên xem sau khi canary đổi config?
40. Ba bước thiết yếu để quản lý môi trường production một cách an toàn là gì?

## Tài liệu tham khảo

- Spring Boot — *Externalized Configuration*: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — *Profiles*: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — *Type-safe Configuration Properties*: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — *Actuator Health/Probes*: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — *Configuration Properties Validation*: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Microsoft Learn — *Configure App Service settings*: https://learn.microsoft.com/azure/app-service/configure-common
- Microsoft Learn — *App Service deployment slots*: https://learn.microsoft.com/azure/app-service/deploy-staging-slots
- Microsoft Learn — *App Service Key Vault references*: https://learn.microsoft.com/azure/app-service/app-service-key-vault-references
- Microsoft Learn — *Azure Container Apps secrets*: https://learn.microsoft.com/azure/container-apps/manage-secrets
- Microsoft Learn — *Azure Container Apps revisions*: https://learn.microsoft.com/azure/container-apps/revisions
- Microsoft Learn — *AKS Workload Identity*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Kubernetes — *ConfigMaps*: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — *Secrets*: https://kubernetes.io/docs/concepts/configuration/secret/
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Azure App Configuration overview*: https://learn.microsoft.com/azure/azure-app-configuration/overview
- Microsoft Learn — *Azure App Configuration key-values and labels*: https://learn.microsoft.com/azure/azure-app-configuration/concept-key-value
- Microsoft Learn — *Azure App Configuration feature management*: https://learn.microsoft.com/azure/azure-app-configuration/concept-feature-management
- Microsoft Learn — *Spring Cloud Azure documentation*: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Microsoft Learn — *Azure SDK for Java authentication*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview
- Microsoft Learn — *Azure SQL authentication with Microsoft Entra*: https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview
- Microsoft Learn — *Azure Private Endpoint overview*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Azure Monitor/Application Insights for Java*: https://learn.microsoft.com/azure/azure-monitor/app/java-in-process-agent
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
