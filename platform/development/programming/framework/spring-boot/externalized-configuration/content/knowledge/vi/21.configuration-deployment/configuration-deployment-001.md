# Tổ chức cấu hình chung, cấu hình môi trường và bí mật riêng

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot thường phải chạy ở nhiều môi trường: máy lập trình viên, môi trường kiểm thử, staging và production. Cùng mã nguồn nhưng những nơi này có thể dùng **database**, **endpoint API**, **log level**, **timeout**, **cấu hình hiệu năng** và **credentials** khác nhau.

Một thiết kế thiếu phân tách có thể đưa tất cả cấu hình vào một file:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://prod-db.internal:5432/shop
    username: admin
    password: "real-password"
app:
  payment:
    base-url: "https://production-payments.example.invalid"
~~~

Các vấn đề xuất hiện ngay:

- File chứa **mật khẩu production** dễ bị commit vào Git hoặc đưa vào JAR.
- Muốn chạy local phải sửa file, tạo những thay đổi chưa commit hoặc vô tình đẩy giá trị local lên repository.
- Muốn thay endpoint theo môi trường phải build lại hoặc sửa artifact.
- Staging và production có thể dùng hai JAR khác nhau dù cùng source commit, khó chứng minh bản production chính là bản đã được kiểm thử.
- Khó xác định giá trị hiệu lực đến từ file nào, biến môi trường nào hoặc nguồn cấu hình nào.
- Không có quy trình rõ cho rotation secrets và kiểm soát quyền truy cập.

Cách tổ chức nên tách **ba tầng**:

1. **Cấu hình chung (common/base configuration)**: những giá trị dùng được cho mọi môi trường hoặc là mặc định không nhạy cảm, ví dụ tên ứng dụng, timeout mặc định, giới hạn request, tên feature.
2. **Cấu hình môi trường (environment-specific configuration)**: những khác biệt giữa local/dev/test/staging/prod, ví dụ URL tích hợp, log level, kích thước pool, chế độ mô phỏng, độ trễ.
3. **Bí mật riêng (secrets)**: mật khẩu, API token, private key, credential database hoặc dữ liệu xác thực. Chúng được cấp lúc chạy bằng nguồn có kiểm soát, **không phải là một application-prod.yml chứa secret thật trong Git**.

Mục tiêu là **build once, deploy many**: cùng một artifact có thể được triển khai nhiều lần với cấu hình và secret phù hợp, không phải rebuild mỗi môi trường.

Bài học này sử dụng **Spring Boot 3.3.x**, Java 21, Spring Config Data, profiles, OS environment, Docker Compose, Kubernetes ConfigMap/Secret và **configtree:**. Tất cả URL dưới **example.invalid** và thông số tên tài khoản minh họa đều là dữ liệu giả.

## 2. Ba tầng cấu hình là ba loại thông tin khác nhau

| Tầng | Ví dụ | Nguồn đề xuất | Có chứa secret không? |
| --- | --- | --- | --- |
| **Chung** | application name, endpoint actuator được phép, timeout mặc định, business limit | application.yml đóng gói | Không |
| **Theo môi trường** | URL database không nhạy cảm, API base URL, log level, pool size, profile | application-dev.yml, application-prod.yml, file ngoài JAR, ConfigMap, env | Thông thường không |
| **Bí mật** | password, API key, OAuth client secret, private key | Secret manager, Secret volume, process env được kiểm soát | Có |
| **Thông tin build** | version, commit SHA, build timestamp | Build metadata/CI | Không chứa runtime secret |

Cần phân biệt **cấu hình theo môi trường** với **secret**. Một database URL hoặc tên host có thể là thông tin nội bộ cần giới hạn công bố, nhưng nó không tự động là credential. Ngược lại, **spring.datasource.password** vẫn là secret dù chỉ dùng ở môi trường development.

Ví dụ phân tầng:

~~~text
Common:
  spring.application.name=shop-api
  app.http.connect-timeout=2s
  app.http.read-timeout=10s

Development:
  app.payment.base-url=https://sandbox-pay.example.invalid
  logging.level.com.example.shop=DEBUG

Production:
  app.payment.base-url=https://payments.example.invalid
  logging.level.com.example.shop=INFO

Secret riêng cho mỗi deployment:
  spring.datasource.password
  app.payment.api-key
~~~

Điều quan trọng không phải chỉ là vị trí file, mà là **quyền sở hữu và vòng đời** của từng giá trị.

## 3. Cây thư mục đề xuất

Một ứng dụng có thể tổ chức như sau:

~~~text
shop-api/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/shop/
│       │   ├── ShopApplication.java
│       │   ├── config/ShopProperties.java
│       │   └── payment/PaymentService.java
│       └── resources/
│           ├── application.yml
│           ├── application-dev.yml
│           ├── application-staging.yml
│           └── application-prod.yml
├── deploy/
│   ├── docker-compose.yml
│   ├── k8s/
│   │   ├── configmap.yaml
│   │   └── deployment.yaml
│   └── env.example
├── .gitignore
└── README.md
~~~

**Ý nghĩa:**

- **application.yml** đặt các default không nhạy cảm.
- **application-dev.yml**, **application-staging.yml**, **application-prod.yml** ghi sự khác biệt *không bí mật* theo profile.
- **deploy/** chứa template triển khai, ConfigMap, manifest tham chiếu Secret nhưng **không có nội dung bí mật thật**.
- **env.example** chỉ ghi tên biến và giá trị giả/hướng dẫn, không chứa token/password thật.
- File riêng trên máy như **.env.local** hoặc thư mục **.local-secrets/** không được commit.

Không bắt buộc phải đóng gói file **application-prod.yml** trong JAR. Tổ chức có thể giữ cấu hình production không nhạy cảm ở repository vận hành riêng và mount khi deploy. Điều cốt lõi là Spring Boot có thể lấy chúng **từ bên ngoài artifact**.

## 4. Tầng chung: application.yml

Ví dụ file **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: shop-api

server:
  port: 8080

app:
  payment:
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      max-attempts: 3
      initial-delay: 250ms

  catalog:
    default-page-size: 25

logging:
  level:
    root: INFO
~~~

Đây là các giá trị mà ứng dụng có thể dùng trong nhiều môi trường:

- Tên ứng dụng **shop-api**.
- Port mặc định **8080**.
- Timeout và retry policy cơ bản của payment client.
- Giới hạn phân trang mặc định.
- Log level gốc INFO.

**Không đưa vào đây password, token hoặc private key thật.** Những giá trị chung trong file này có thể đóng gói cùng source và artifact; mọi người có quyền đọc repository hoặc JAR có thể xem được.

### 4.1. Cấu hình chung có thể gồm placeholder?

Có thể. Ví dụ:

~~~yaml
app:
  payment:
    base-url: "${payment.base-url:https://sandbox-pay.example.invalid}"
    connect-timeout: "${payment.connect-timeout:2s}"
~~~

Khi Spring Boot sử dụng giá trị, placeholder **${...}** được giải quyết qua **Environment**. Một nguồn khác có thể cấp **payment.base-url** hoặc **payment.connect-timeout**.

Tuy nhiên, không cần tạo thêm một tầng alias nếu nền tảng đã cấp trực tiếp **APP_PAYMENT_BASEURL** và **APP_PAYMENT_CONNECTTIMEOUT**. Nên giữ số lượng tên công khai vừa đủ để tránh nhầm lẫn.

### 4.2. Mặc định không đồng nghĩa production-ready

Một default phù hợp local có thể nguy hiểm khi dùng ở production. Ví dụ một URL sandbox có thể khiến ứng dụng production gửi dữ liệu đến sai hệ thống nếu operator quên override.

Đối với cấu hình bắt buộc ở production, có thể **không đặt fallback** và dùng validation để khởi động thất bại nếu thiếu. Điều này áp dụng đặc biệt cho endpoint quan trọng, credential và các quy tắc bảo mật.

## 5. Tầng môi trường: application-{profile}.yml

Spring Boot tự tìm các file cấu hình theo profile, chẳng hạn:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
~~~

Nếu active profile là **dev**, Spring Boot xét cả **application.yml** và **application-dev.yml** trong các location phù hợp. Với profile-specific configuration, giá trị của file tương ứng có thể **override** giá trị chung của cùng key.

### 5.1. application-dev.yml

~~~yaml
app:
  payment:
    base-url: "https://sandbox-pay.example.invalid"
    request-timeout: 30s

logging:
  level:
    com.example.shop: DEBUG

spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/shop_dev"
    username: shop_dev
~~~

Đây là giá trị **không bí mật** minh họa. Nếu database development vẫn yêu cầu password, password phải được cấp riêng. Tên tài khoản không nhất thiết là secret nhưng vẫn cần xem chính sách công bố thông tin nội bộ.

### 5.2. application-staging.yml

~~~yaml
app:
  payment:
    base-url: "https://staging-pay.example.invalid"
    request-timeout: 15s

logging:
  level:
    com.example.shop: INFO

spring:
  datasource:
    url: "jdbc:postgresql://staging-db.example.invalid:5432/shop"
    username: shop_app
~~~

### 5.3. application-prod.yml

~~~yaml
app:
  payment:
    base-url: "https://payments.example.invalid"
    request-timeout: 8s
    retry:
      max-attempts: 2

logging:
  level:
    root: WARN
    com.example.shop: INFO

spring:
  datasource:
    url: "jdbc:postgresql://prod-db.example.invalid:5432/shop"
    username: shop_app
~~~

Không có trường password hoặc API key thật trong những file profile này. Secret được cung cấp độc lập ở bước triển khai.

Một quy tắc kiểm soát thay đổi hữu ích: **file cấu hình theo môi trường có thể được review như code**, nhưng **nội dung secret không xuất hiện trong pull request, commit, log CI hoặc artifact**.

## 6. Chọn profile bằng nguồn runtime

Có thể bật profile qua command line:

~~~bash
java -jar shop-api.jar --spring.profiles.active=dev
~~~

Hoặc production:

~~~bash
java -jar shop-api.jar --spring.profiles.active=prod
~~~

Biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar shop-api.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar shop-api.jar
~~~

Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar shop-api.jar
~~~

Một số lưu ý:

- **spring.profiles.active** quyết định các profile đang active theo quy tắc ưu tiên của nguồn.
- Nên chọn profile **từ môi trường deploy hoặc cơ chế launch**, thay vì hard-code profile production vào Java source.
- Spring Boot có profile mặc định **default** nếu không kích hoạt profile cụ thể; có thể thay bằng **spring.profiles.default** ở nguồn được phép.
- Nếu dùng nhiều profile, thứ tự active profile có thể ảnh hưởng ưu tiên của file profile; trong trường hợp điển hình, profile sau có thể override profile trước.
- **spring.profiles.active**, **spring.profiles.default** và **spring.profiles.include** không được khai báo bên trong profile-specific document hoặc một YAML document đã được kích hoạt bằng **spring.config.activate.on-profile**.

### 6.1. Vì sao không đặt spring.profiles.active trong application-prod.yml?

Nếu file **application-prod.yml** chỉ được xét khi profile prod active, việc đặt:

~~~yaml
spring:
  profiles:
    active: prod
~~~

vào chính file đó tạo ra một quyết định sai tầng và vi phạm ràng buộc Spring Boot đối với profile-specific configuration. Profile phải được chọn từ **nguồn không profile-specific** hoặc thông qua runtime launcher.

## 7. Thứ tự ưu tiên: nguồn nào thắng?

Chỉ đặt các file đúng tên là chưa đủ; cần hiểu **PropertySource precedence**.

Một bảng khái quát cho những nguồn thông dụng:

| Nguồn | Ưu tiên tương đối |
| --- | --- |
| Default properties của SpringApplication | Thấp |
| Cấu hình trong JAR, application.yml | Thấp trong nhóm Config Data |
| Cấu hình profile trong JAR | Cao hơn bản chung trong JAR |
| Cấu hình ngoài JAR | Thường cao hơn Config Data cùng loại trong JAR |
| Cấu hình ngoài JAR theo profile | Thường cao trong nhóm Config Data |
| OS environment variables | Cao hơn Config Data trong thứ tự thông thường |
| Java system properties | Cao hơn OS environment variables trong thứ tự thông thường |
| SPRING_APPLICATION_JSON | Có vị trí riêng, cao hơn system properties trong danh sách tiêu biểu |
| Command-line arguments | Cao hơn các nguồn trên trong cấu hình Boot thông thường |

Đây là **tóm tắt các nguồn tiêu biểu**, không phải toàn bộ thứ tự trong Spring Boot: test properties, servlet init parameters, Devtools và một số nguồn đặc thù có vị trí khác.

Ví dụ:

~~~text
application.yml:           app.payment.request-timeout=10s
application-prod.yml:      app.payment.request-timeout=8s
environment:               APP_PAYMENT_REQUESTTIMEOUT=12s
command-line:              --app.payment.request-timeout=6s
------------------------------------------------------------
Kết quả minh họa:           6s
~~~

Nếu bỏ tham số command-line, biến môi trường có thể quyết định giá trị là 12s.

**Điểm quan trọng:** không cần tạo JAR mới để thay request timeout. Cùng JAR được chạy với bộ runtime configuration khác nhau.

### 7.1. Profile không tự bảo vệ bí mật

Một file tên **application-prod.yml** không được mã hóa và không có bảo vệ bí mật chỉ vì nó mang chữ **prod**. Nếu chứa password thật rồi commit vào Git, password vẫn có thể bị lộ.

Profile là cơ chế **chọn nhóm cấu hình**, không phải hệ thống secret management.

## 8. Tầng bí mật: cấp từ nguồn riêng

Bí mật gồm các giá trị như:

- **spring.datasource.password**.
- **app.payment.api-key**.
- OAuth client secret hoặc private key.
- Signing key, encryption key, credential của message broker.
- Token truy cập hệ thống ngoài.

Yêu cầu vận hành cơ bản:

1. Không commit secret thật vào repository.
2. Không build secret vào JAR, image, resources đã filter hoặc layer Docker.
3. Cấp secret ở runtime từ hệ thống được kiểm soát.
4. Giới hạn quyền đọc theo nguyên tắc **least privilege**.
5. Không log giá trị secret.
6. Có quy trình **rotation**, thu hồi và xử lý sự cố lộ secret.
7. Phân biệt quyền của dev, staging và production; không dùng chung một password chỉ vì tiện.

Một ứng dụng có thể nhận password qua env:

~~~bash
SPRING_DATASOURCE_PASSWORD="<được cấp bởi môi trường triển khai>" \
java -jar shop-api.jar --spring.profiles.active=prod
~~~

Đây chỉ là **mẫu minh họa cú pháp**. Trong quy trình thật, tránh gõ secret trực tiếp vào command line hoặc lịch sử shell nếu hạ tầng có cơ chế cấp secret an toàn hơn.

Một lựa chọn khác là file secret được mount từ hệ thống triển khai rồi nạp bằng **configtree:**.

### 8.1. Secret không phải “chuỗi bí mật trong .env đã gitignore” là đủ

Thêm **.env** vào **.gitignore** giảm nguy cơ commit nhầm, nhưng không đảm bảo secret an toàn tuyệt đối. Secret vẫn có thể bị lộ qua:

- Terminal history và process environment.
- Output của CI, debug logs, crash dumps.
- File backup hoặc artifact upload.
- Quyền đọc không hạn chế trên máy chủ.
- Docker image layer nếu vô tình dùng **COPY**.
- Biến in ra bởi công cụ chẩn đoán.
- Manifest Kubernetes Secret được commit với dữ liệu base64.

Cần kết hợp bảo vệ Git, runtime, storage, quyền truy cập và vòng đời secret.

## 9. Bind cấu hình có kiểu bằng @ConfigurationProperties

Tách ba tầng nguồn không có nghĩa code phải biết property xuất phát từ file nào. Spring Boot có thể bind **giá trị hiệu lực cuối cùng** vào một Java object.

Ví dụ:

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        Retry retry,
        String apiKey) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Trong class này:

- **baseUrl**, **connectTimeout**, **requestTimeout** có thể lấy từ chung hoặc profile-specific Config Data.
- **retry.maxAttempts**, **retry.initialDelay** có thể kế thừa default hoặc override theo môi trường.
- **apiKey** là dữ liệu nhạy cảm và cần được cấp riêng từ secret source.

**Không log toàn bộ PaymentProperties bằng toString()**, vì record chứa apiKey và toString có thể in tất cả record components. Nếu cần log thông tin chẩn đoán, chỉ log tên property hoặc các trường không nhạy cảm đã được phép công bố.

### 9.1. Đăng ký bean cấu hình

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** giúp Boot tìm type ở các package phù hợp. Với record immutable/constructor binding, đây là một cách đăng ký thích hợp; một lựa chọn khác là **@EnableConfigurationProperties(PaymentProperties.class)**.

Cấu hình được bind từ **Environment**, bất kể nguồn giá trị cuối đến từ YAML, env, CLI hay configtree. Code nghiệp vụ không cần xây nhiều trường hợp đọc từng file.

## 10. Validation để thiếu bí mật không trở thành lỗi muộn

Một cấu hình secret bắt buộc không nên có fallback là chuỗi **dummy** hoặc **changeme** ở production. Nếu operator quên cấp secret, ứng dụng nên thất bại sớm với thông báo cho biết **key nào thiếu**, nhưng không in giá trị.

Ví dụ type có validation:

~~~java
package com.example.shop.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentValidatedProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @NotBlank String apiKey) {
}
~~~

Dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

**PaymentValidatedProperties** là type minh họa thay thế cho PaymentProperties đầy đủ ở mục trước. Trong ứng dụng thật, hợp nhất validation vào một model được lựa chọn, không cần đăng ký đồng thời nhiều model cùng prefix.

Khi thiếu apiKey, constraint **@NotBlank** có thể giúp fail startup. Nhưng cần bảo đảm log exception không in secret thật; tránh tùy biến thông báo theo kiểu nối toàn bộ giá trị property vào string.

### 10.1. Điều kiện bắt buộc theo profile

Trong development, có thể ứng dụng dùng mock payment service và không cần API key. Trong production, key bắt buộc.

Không tự động đặt **@NotBlank** vô điều kiện nếu các chế độ có hợp đồng khác nhau. Có thể:

- Tách cấu hình mock/live thành hai subsystem với bean/profile phù hợp.
- Dùng constraint cấp class theo cờ **enabled** hoặc **mode**.
- Viết startup guard kiểm tra secret khi integration live thực sự được kích hoạt.

Mục tiêu không phải ép mọi môi trường dùng cùng bộ credential, mà là không cho production chạy thiếu giá trị cần thiết.

## 11. Định danh nguồn cấu hình chung với placeholder

Một mẫu phổ biến là khai báo **hợp đồng cấu hình chung**, còn giá trị được cấp bên ngoài:

~~~yaml
app:
  payment:
    base-url: "${payment.endpoint:https://sandbox-pay.example.invalid}"
    connect-timeout: "${payment.connect-timeout:2s}"
    api-key: "${payment.api-key:}"
~~~

Trong cách này, **payment.endpoint**, **payment.connect-timeout** và **payment.api-key** là các key đầu vào khác. Nếu để trống api-key, code nên validation theo chế độ hoạt động.

Tuy nhiên, không nên đặt một giá trị mặc định rỗng rồi vô tình cho phép production tiếp tục hoạt động không có secret. Nếu đây là khóa bắt buộc, có thể bỏ placeholder alias, bind trực tiếp **app.payment.api-key** từ secret env/configtree, và dùng validation.

Với profile:

~~~yaml
app:
  payment:
    base-url: "https://payments.example.invalid"
~~~

có thể override base URL từ file profile, còn API key được cấp bằng nguồn riêng. Ba tầng không bắt buộc tương ứng với ba lớp placeholder; chúng là **ba nhóm trách nhiệm cấu hình**.

## 12. Config Data bên ngoài JAR

Spring Boot 3.3 tự tìm Config Data ở một số vị trí mặc định, bao gồm nơi đóng gói trong classpath và những location ngoài JAR như working directory hoặc **config/**.

Ví dụ cách tổ chức khi triển khai:

~~~text
/opt/shop/
├── shop-api.jar
└── config/
    ├── application.yml
    └── application-prod.yml
~~~

File **/opt/shop/config/application-prod.yml** có thể chứa giá trị production không bí mật và được đọc khi profile **prod** active.

Điều này giúp cùng artifact **shop-api.jar** hoạt động với cấu hình không nhạy cảm riêng của từng môi trường.

### 12.1. Thêm location ngoài mặc định

Nếu muốn bổ sung một directory, có thể chạy:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./ops-config/
~~~

**spring.config.additional-location** bổ sung location mà vẫn giữ các location mặc định, còn **spring.config.location** dùng để thay thế tập location mặc định theo quy tắc Boot.

Khi location là **directory**, dấu gạch chéo cuối **/** quan trọng vì Spring Boot ghép tên file được sinh từ **spring.config.name** vào đường dẫn.

### 12.2. Bootstrap property cần được cấp sớm

Những key như:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
~~~

được Spring Boot sử dụng từ rất sớm để quyết định cần tìm cấu hình ở đâu. Chúng thường được cấp qua command-line, OS env hoặc Java system properties.

Đừng đặt **spring.config.location** trong một file mà chỉ có thể tìm thấy sau khi location ấy đã được quyết định.

### 12.3. Khi nào chọn file ngoài JAR thay vì profile file đóng gói?

Cân nhắc file ngoài JAR khi:

- Đội vận hành sở hữu các giá trị triển khai.
- Endpoint/timeout thay đổi mà không cần phát hành source mới.
- Sử dụng một artifact giữa nhiều cluster/tenant.
- Muốn tổ chức quy trình review triển khai riêng.

Cân nhắc profile file đóng gói khi các giá trị môi trường không nhạy cảm, ổn định và được quản lý chung với source. Cả hai cách đều tương thích với Spring Boot; điều quan trọng là không nhúng secret và nắm thứ tự ưu tiên.

## 13. spring.config.import cho cấu hình bổ sung

Spring Boot hỗ trợ khai báo Config Data import:

~~~yaml
spring:
  config:
    import: "optional:file:./ops-config/extra.properties"
~~~

Nếu file tồn tại:

~~~properties
app.payment.request-timeout=15s
app.catalog.default-page-size=40
~~~

nó được nhập vào quá trình Config Data processing. Giá trị import có thể **override** giá trị trong document đã khai báo import, theo quy tắc của Boot.

Đây là cơ chế khác với **@PropertySource** trên một @Configuration class, vốn được thêm muộn khi context refresh.

### 13.1. optional có nghĩa gì?

~~~text
optional:file:./ops-config/extra.properties
~~~

cho phép app tiếp tục khi location không tồn tại.

Nếu cấu hình đó **thực sự bắt buộc ở production**, không dùng **optional** chỉ để che lỗi deploy. Hãy bảo đảm có file, hoặc validation/fail-fast phù hợp.

### 13.2. Thứ tự imports không phải vấn đề trang trí

Nếu nhiều import khai báo cùng key, thứ tự/precedence của imports ảnh hưởng giá trị cuối. Nên thiết kế số lượng tầng import vừa đủ và ghi rõ contract override; tránh biến application.yml thành một chuỗi import sâu khó truy vết.

## 14. Configtree: đọc bí mật từ file được mount

Nhiều môi trường cloud cấp secret dưới dạng **mỗi key là một file**, với nội dung file là giá trị. Spring Boot hỗ trợ **configtree:** cho kiểu này.

Giả sử runtime mount:

~~~text
/etc/shop-secrets/
├── spring.datasource.password
└── app.payment.api-key
~~~

Trong đó **tên file** là tên property cần cung cấp, còn **nội dung file** là secret thật. Ta không đưa nội dung ấy vào README/Git.

Có thể cấp import khi chạy:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod \
  --spring.config.import=configtree:/etc/shop-secrets/
~~~

Spring Boot dùng cơ chế config tree để tạo property:

~~~text
spring.datasource.password
app.payment.api-key
~~~

Có thể inject qua **Environment**, **@Value** hoặc **@ConfigurationProperties** theo quy tắc thông thường.

Nếu thư mục không tồn tại và location không có **optional:**, quá trình nạp Config Data có thể thất bại; đây thường là hành vi mong muốn nếu secret là bắt buộc. Nếu bí mật chỉ là tùy chọn cho một feature, có thể dùng import optional và validation có điều kiện.

### 14.1. Cấu trúc thư mục con tạo tên property phân cấp

Giả sử:

~~~text
/etc/shop-secrets/
└── app/
    └── payment/
        └── api-key
~~~

với import **configtree:/etc/shop-secrets/**, các thành phần folder/file được dùng để hình thành tên property như **app.payment.api-key**.

Với cách mount file trực tiếp như **app.payment.api-key**, dấu chấm trong tên file cũng được Spring Boot nhận diện thành property name.

### 14.2. Cách import qua application.yml

Một cấu hình chung có thể thêm:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/shop-secrets/"
~~~

Cách này hữu ích nếu production có mount thư mục và local không có. Tuy nhiên, nếu production bắt buộc có secret, dùng **optional** phải đi cùng validation/guard để không chạy với secret trống.

Một lựa chọn có trách nhiệm rõ hơn là **không đặt import secrets trong base file**, mà cấu hình môi trường triển khai cấp **SPRING_CONFIG_IMPORT=configtree:/etc/shop-secrets/**. Khi đó hệ thống triển khai quyết định secret location.

### 14.3. Quyền đọc file secret

Configtree không tự mã hóa hay bảo vệ file. Nền tảng phải:

- Mount vào đúng container/process.
- Cấp quyền đọc cho danh tính chạy ứng dụng.
- Không cấp quyền cho container không cần secret.
- Không copy file vào image khi build.
- Bảo vệ hệ thống lưu trữ cấp secret và quyền xem log/backup.

**Configtree là cơ chế nạp dữ liệu**, không phải Secret Manager.

## 15. Local development: không lưu mật khẩu thật trong application-dev.yml

Với môi trường local, có một số lựa chọn:

1. Dùng tài khoản database local không nhạy cảm hoặc database giả lập.
2. Dùng env được công cụ phát triển cấp cho process.
3. Dùng file riêng bị gitignore, chẳng hạn **.local-secrets/**, và import theo lệnh startup local.
4. Dùng secret manager/dev vault nếu tổ chức cung cấp.

Ví dụ file **.gitignore**:

~~~gitignore
.env
.env.*
!.env.example
.local-secrets/
ops-config/local-only/
*.key
*.p12
~~~

Đây chỉ là **gợi ý**. Không tự động ignore mọi file **.p12** nếu dự án cần theo dõi certificate công khai/fixture trong test. Hãy điều chỉnh danh sách theo policy dự án.

File **.env.example** chỉ là hướng dẫn:

~~~dotenv
SPRING_PROFILES_ACTIVE=dev
SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/shop_dev
SPRING_DATASOURCE_USERNAME=shop_dev
SPRING_DATASOURCE_PASSWORD=<set-locally>
APP_PAYMENT_APIKEY=<set-locally>
~~~

**.env.example không được coi là file có thể nạp trực tiếp**, vì các placeholder **<set-locally>** không phải credential. Người phát triển tạo file local riêng hoặc dùng trình quản lý secret được phép.

### 15.1. .env không tự động trở thành Environment của Java

Một file tên **.env** trong repository không phải lúc nào cũng được Spring Boot tự đọc. Docker Compose, IDE hoặc công cụ launch khác có thể dùng file này để cấp biến, nhưng phải hiểu rõ cơ chế của từng công cụ.

Đừng mặc định “đã tạo .env” đồng nghĩa process Java nhận **SPRING_DATASOURCE_PASSWORD**. Cần kiểm tra cách biến được chuyển vào process.

## 16. Ví dụ Docker Compose tách cấu hình và secret

Một ví dụ Docker Compose với PostgreSQL bên ngoài (không tạo database service trong ví dụ):

~~~yaml
services:
  shop-api:
    image: example/shop-api:1.0.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db.example.invalid:5432/shop"
      SPRING_DATASOURCE_USERNAME: "shop_app"
      APP_PAYMENT_BASEURL: "https://payments.example.invalid"
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - source: db_password
        target: spring.datasource.password
      - source: payment_api_key
        target: app.payment.api-key

secrets:
  db_password:
    file: ./.local-secrets/db-password.txt
  payment_api_key:
    file: ./.local-secrets/payment-api-key.txt
~~~

Ví dụ này minh họa Compose **secrets** với tên file mount đích khớp property Spring Boot. Nó giả định các file nguồn local đã được tạo ngoài Git và runtime Compose đang hỗ trợ cú pháp secret target tương ứng.

Các secret được mount tại:

~~~text
/run/secrets/spring.datasource.password
/run/secrets/app.payment.api-key
~~~

**configtree:/run/secrets/** khiến Spring Boot nhận property theo tên file.

Lợi ích:

- Image **example/shop-api:1.0.0** không chứa mật khẩu.
- Các endpoint và profile được chọn khi chạy.
- File secret được mount vào container thay vì được ghi trong application-prod.yml.
- Cùng image có thể được dùng cho staging/production nếu bộ cấu hình được cấp khác nhau.

### 16.1. Không dùng Docker ARG/ENV để nhúng secret khi build

Ví dụ **không nên làm**:

~~~dockerfile
ARG DB_PASSWORD
ENV SPRING_DATASOURCE_PASSWORD=$DB_PASSWORD
~~~

Khi tạo image, các giá trị build-time có thể rơi vào metadata, layer hoặc cache tùy quy trình và công cụ. Thay vì đó, cấp secret qua cơ chế runtime/secret store phù hợp.

### 16.2. Cẩn trọng với môi trường và log

Ngay cả khi secret chỉ được cấp ở runtime, process khác có quyền phù hợp hoặc công cụ chẩn đoán vẫn có thể tiếp cận nó. Hãy giới hạn quyền, kiểm soát log, tránh dump Environment và không công bố các endpoint trả config values.

## 17. Kubernetes: ConfigMap cho giá trị không mật

Kubernetes có hai loại tài nguyên thường gặp:

- **ConfigMap**: dành cho dữ liệu cấu hình **không nhạy cảm**.
- **Secret**: dành cho dữ liệu nhạy cảm như password, token, key.

Ví dụ ConfigMap không chứa secret thật:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: shop-api-config
data:
  SPRING_PROFILES_ACTIVE: "prod"
  SPRING_DATASOURCE_URL: "jdbc:postgresql://db.example.invalid:5432/shop"
  SPRING_DATASOURCE_USERNAME: "shop_app"
  APP_PAYMENT_BASEURL: "https://payments.example.invalid"
  APP_PAYMENT_REQUESTTIMEOUT: "8s"
  LOGGING_LEVEL_ROOT: "WARN"
~~~

Tài nguyên này có thể được review và quản lý cùng manifest triển khai tùy policy của tổ chức.

**Không đặt password hoặc API key vào ConfigMap**, vì ConfigMap không cung cấp cơ chế bảo mật dành cho dữ liệu bí mật. Một giá trị mã hóa base64 trong ConfigMap cũng không trở thành secret.

### 17.1. Secret phải tồn tại riêng

Giả sử namespace đã có Secret tên **shop-api-credentials** với hai key:

~~~text
spring.datasource.password
app.payment.api-key
~~~

Secret có thể được tạo qua external secret operator, secret manager integration hoặc quy trình cấp dữ liệu được tổ chức phê duyệt. Không cần ghi một manifest Secret chứa password thật vào repository.

Bản thân **Kubernetes Secret** cũng không phải mã hóa an toàn tuyệt đối: dữ liệu base64 chỉ là encoding, và cluster cần được cấu hình **encryption at rest**, **RBAC tối thiểu** và giới hạn quyền đọc đúng pod/container.

## 18. Kubernetes: mount Secret như config tree

Đoạn Deployment minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: shop-api
          image: example/shop-api:1.0.0
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: shop-api-config
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/shop-secrets/"
          volumeMounts:
            - name: app-credentials
              mountPath: /etc/shop-secrets
              readOnly: true
      volumes:
        - name: app-credentials
          secret:
            secretName: shop-api-credentials
~~~

Trong ví dụ:

- **ConfigMap** cung cấp biến môi trường không nhạy cảm.
- **Secret** được mount thành file trong volume.
- **SPRING_CONFIG_IMPORT** yêu cầu Boot import config tree từ đường dẫn đã mount.
- Tên file **spring.datasource.password** và **app.payment.api-key** tạo đúng property cần dùng.
- Không cần ghi giá trị password/API key trong Deployment.

Đây là manifest minh họa về **phân tách cấu hình**, không bao gồm readiness probe, liveness probe, securityContext, resource limits, Service hay network policy. Khi triển khai production cần bổ sung các phần tương ứng với nền tảng.

### 18.1. Secret mount không đồng nghĩa app tự nhận thay đổi ngay

Kubernetes có thể cập nhật Secret volume theo cơ chế eventual consistency. Nhưng Spring Boot thông thường không tự rebind mọi **@ConfigurationProperties** bean hay tự mở lại datasource connection chỉ vì nội dung file mount đã đổi.

Khi rotation secret, cần xác định:

- Secret volume/agent có cập nhật nội dung hay không.
- Ứng dụng có cơ chế reload Config Data không.
- Connection pool hoặc HTTP client có cần khởi tạo lại không.
- Có cần rolling restart hoặc một chiến lược rotation hai bước không.

Nếu dùng Secret làm **environment variable**, container đang chạy thường **không tự có env mới** sau khi Secret được cập nhật; cần thay pod/restart phù hợp.

### 18.2. Tránh lộ secret qua manifest và RBAC

Người có quyền đọc hoặc tạo Pod ở namespace có thể có khả năng truy cập Secret theo nhiều con đường. Bảo vệ không chỉ dừng ở việc mount thay vì env. Cần RBAC least-privilege, encryption at rest, hạn chế quyền pod, audit và kiểm soát hệ thống backup.

## 19. Kubernetes: khi nào dùng env thay vì volume?

| Cách cấp | Ưu điểm | Giới hạn cần lưu ý |
| --- | --- | --- |
| **Secret qua env** | Đơn giản khi ứng dụng đã đọc từ environment variables | Có thể xuất hiện trong process environment; cập nhật Secret không tự sửa env của process |
| **Secret volume** | Không cần đưa secret vào env; phù hợp với file key/certificate | Cần mount và quyền file; app không tự động refresh khi file đổi |
| **External secret manager** | Có cơ chế quản lý vòng đời/rotation và quyền tập trung | Cần integration và chiến lược lỗi/refresh rõ ràng |
| **ConfigMap qua env** | Dễ cấp các key không nhạy cảm | Không bảo mật secret; thay ConfigMap không tự đổi env đang chạy |
| **ConfigMap volume** | Phù hợp cấu hình file lớn và config tree không mật | Phải xác định cách app reload hoặc restart |

Không có một lựa chọn đúng cho mọi dự án. Với password và API key, hãy ưu tiên nguồn secret phù hợp khả năng kiểm soát của nền tảng, sau đó **để Spring Boot nhận giá trị qua một property key ổn định**.

## 20. Quy tắc đặt tên giữa YAML và environment variable

Giả sử Java:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration requestTimeout,
        String apiKey) {
}
~~~

Key canonical:

~~~text
app.payment.base-url
app.payment.request-timeout
app.payment.api-key
~~~

Khi chuyển sang biến môi trường theo Spring Boot relaxed binding:

~~~text
APP_PAYMENT_BASEURL
APP_PAYMENT_REQUESTTIMEOUT
APP_PAYMENT_APIKEY
~~~

Quy tắc:

1. Dấu chấm **.** → dấu gạch dưới **_**.
2. Dấu gạch ngang **-** → **bỏ**, không đổi thành gạch dưới.
3. Chữ cái → viết hoa.

Không mặc nhiên dùng:

~~~text
APP_PAYMENT_BASE_URL
APP_PAYMENT_REQUEST_TIMEOUT
APP_PAYMENT_API_KEY
~~~

như phép chuyển canonical. Một số hạ tầng có thể hỗ trợ các biến thể tên, nhưng tài liệu và manifest nên sử dụng dạng thống nhất đã được Spring Boot mô tả.

**Cùng tên property Java** có thể nhận giá trị từ YAML hoặc env; đó là lý do nên định nghĩa namespace rõ và nhất quán.

## 21. Tổ chức multi-document YAML thay cho nhiều file profile

Ngoài **application-dev.yml**, Spring Boot có thể dùng nhiều YAML documents trong cùng file, phân tách bằng **---**:

~~~yaml
spring:
  application:
    name: shop-api

app:
  payment:
    connect-timeout: 2s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  payment:
    base-url: "https://sandbox-pay.example.invalid"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    base-url: "https://payments.example.invalid"
~~~

Document đầu áp dụng chung; các document còn lại chỉ được kích hoạt khi điều kiện profile phù hợp.

Ưu điểm: có thể xem cấu hình chung và các nhánh profile trong một file nhỏ.

Hạn chế: nếu quá nhiều môi trường, file dễ dài và khó review. Với hệ thống phức tạp, các file profile riêng hoặc cấu hình ngoài JAR thường dễ sở hữu hơn.

**Không khai báo spring.profiles.active bên trong một document có spring.config.activate.on-profile.** Spring Boot giới hạn cách khai báo profile activation để tránh cấu hình vòng và thứ tự không rõ.

### 21.1. on-cloud-platform

Ngoài on-profile, Config Data còn có điều kiện **spring.config.activate.on-cloud-platform**. Nó có thể phù hợp khi một số giá trị chỉ liên quan đến runtime cloud platform.

Nhưng platform detection không thay thế secret management, và không nên dùng nó để ngầm bật cấu hình production nhạy cảm. Production vẫn cần cơ chế deploy xác định rõ profile và nguồn secret.

## 22. Nhiều profile và nguyên tắc last-wins

Có thể bật nhiều profile:

~~~bash
java -jar shop-api.jar \
  --spring.profiles.active=prod,observability
~~~

Mục đích có thể là:

- **prod**: giá trị môi trường production.
- **observability**: các tùy chọn monitoring/logging riêng.

Nếu hai file profile cùng khai báo một key, Spring Boot áp dụng cơ chế ưu tiên, trong trường hợp thông thường profile sau có thể override profile trước.

Điều này hữu ích nhưng cũng dễ gây mơ hồ. Không nên định nghĩa **spring.datasource.password** ở mỗi profile để dùng last-wins như một cơ chế quản lý bí mật.

### 22.1. Profile group

Spring Boot hỗ trợ **spring.profiles.group** để kích hoạt một nhóm profile liên quan, ví dụ:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod
        - observability
~~~

Những group definitions phải được đặt trong cấu hình **không profile-specific** theo quy tắc của Spring Boot, không nằm bên trong document được kích hoạt bằng **on-profile**.

Group giúp tổ chức lựa chọn behavior nhưng **không cung cấp cơ chế bảo vệ secrets**. Việc một profile được kích hoạt không làm credential tự xuất hiện nếu secret source chưa được cấp.

## 23. Tránh hard-code môi trường vào mã nguồn Java

Một cách có thể gây khó bảo trì:

~~~java
String url;
if (isProduction()) {
    url = "https://payments.example.invalid";
} else {
    url = "https://sandbox-pay.example.invalid";
}
~~~

Hoặc:

~~~java
String password = "production-password";
~~~

Cách đúng thường là **service sử dụng một configuration object**, còn giá trị được lựa chọn qua Environment/Config Data.

~~~java
package com.example.shop.payment;

import com.example.shop.config.PaymentProperties;
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI endpoint() {
        return properties.baseUrl();
    }
}
~~~

Như vậy:

- Code không phải tự đoán đang chạy production hay staging chỉ để chọn URL.
- Testing có thể cấp property riêng cho từng test.
- Không cần rebuild khi đổi endpoint.
- Một artifact đủ khả năng chạy qua nhiều môi trường.

**Lưu ý:** có thể vẫn dùng **@Profile** để chọn implementation khác nhau, ví dụ mock payment client trong dev. Nhưng việc chọn implementation và việc cấp credential là hai mối quan tâm riêng.

## 24. Một artifact cho nhiều môi trường

Quy trình lý tưởng:

~~~text
Source + tests
      |
      v
Build một lần
      |
      v
shop-api.jar / container image có checksum xác định
      |
      +--------------------+
      |                    |
      v                    v
Staging                Production
      |                    |
      v                    v
Profile staging         Profile prod
Staging config          Production config
Staging secret          Production secret
      |                    |
      v                    v
Cùng artifact, cấu hình hiệu lực khác nhau
~~~

Lợi ích:

- Staging có thể kiểm thử **cùng bytes artifact** sẽ deploy production.
- Có thể rollback bằng cách triển khai lại artifact đã phát hành với bộ cấu hình phù hợp.
- Giảm số lượng binary build theo môi trường.
- Lịch sử thay đổi source và lịch sử thay đổi deploy config được kiểm soát riêng.
- Secret không cần có mặt trong pipeline tạo JAR, trừ các nhu cầu test được kiểm soát.

### 24.1. Khi nào môi trường vẫn cần behavior khác?

Có thể dùng profile để bật một số bean hoặc lựa chọn cấu hình riêng. Điều đó không phủ nhận nguyên tắc build once. Cùng binary vẫn chứa các bean/classes cần thiết và sẽ chọn theo môi trường khi chạy.

Tuy nhiên, tránh dùng profile để vô tình đưa code thử nghiệm hoặc đường kiểm soát bảo mật yếu vào production. Cần kiểm thử profile behavior và các ràng buộc deploy cụ thể.

## 25. Cập nhật secret không đồng nghĩa tất cả bean tự refresh

Một câu hỏi quan trọng: “Secret đã được xoay vòng, Spring Boot có nhận ngay không?”

Không thể trả lời có một cách tổng quát.

- **Environment** chứa các PropertySource đã được nạp trong một lượt chạy.
- **@ConfigurationProperties** thường được bind khi ApplicationContext tạo bean.
- Biến môi trường của process thường được xác lập khi process khởi động.
- File secret mount có thể được cập nhật bởi platform, nhưng Spring Boot thông thường không tự nạp lại toàn bộ Config Data và tái tạo connection pool.
- Một số starter/integration có hỗ trợ refresh riêng, nhưng phải được cấu hình và kiểm thử cụ thể.

Vì vậy, rotation nên có quy trình:

1. Cấp secret mới và bảo đảm hệ thống đích chấp nhận nó.
2. Cập nhật nguồn secret an toàn.
3. Rolling restart/reload những ứng dụng cần thiết theo cơ chế đã thiết kế.
4. Xác minh kết nối/tác vụ hoạt động với secret mới.
5. Thu hồi secret cũ khi các consumer đã chuyển xong.
6. Kiểm tra logs/audit không ghi lộ giá trị.

Không tự động hứa “Secret volume đổi thì bean Java tự nhận” nếu hệ thống chưa có cơ chế refresh.

## 26. Tránh đưa bí mật vào logs, lỗi và Actuator

Spring Boot Actuator có các endpoint chẩn đoán như **env** và **configprops** khi dependency và exposure được cấu hình phù hợp. Những endpoint này có thể liên quan đến dữ liệu cấu hình nhạy cảm.

Nguyên tắc:

- Không mở endpoint chẩn đoán đầy đủ ra Internet.
- Kiểm tra cơ chế masking/sanitization, authorization và exposure của đúng phiên bản.
- Không log nguyên bản Map của Environment hoặc **toString()** của record chứa password/token.
- Không đưa secret vào exception message tự xây dựng.
- Không in secret trong CI command hoặc script set -x/verbose.
- Không trả secret trong endpoint health/custom debug.
- Không gửi giá trị thực lên issue tracker, ảnh chụp màn hình hoặc log chat.

Ví dụ **không nên làm**:

~~~java
System.out.println(paymentProperties);
~~~

nếu object có trường **apiKey**.

Một cách log an toàn hơn:

~~~java
log.info("Payment endpoint configured: {}",
        paymentProperties.baseUrl());
~~~

Nhưng ngay cả URL nội bộ cũng có thể nhạy cảm theo chính sách. Chỉ log thông tin đủ cho vận hành và không chứa credential.

### 26.1. Base64 không phải mã hóa

Kubernetes Secret thường biểu diễn data bằng base64. Bất kỳ ai đọc được giá trị đều có thể giải mã. Bảo mật đến từ cơ chế quyền truy cập, bảo vệ storage/transport, encryption at rest và quy trình cấp quyền, không đến từ base64.

## 27. Mẫu cấu hình khi chạy local, staging và production

Một bảng vận hành dễ dùng:

| Nội dung | Local | Staging | Production |
| --- | --- | --- | --- |
| Profile | dev | staging | prod |
| Config chung | Trong JAR | Trong JAR | Trong JAR |
| Config riêng | application-dev.yml + local override | file/ConfigMap staging | file/ConfigMap production |
| Database URL | localhost/dev DB | staging DB | prod DB |
| Payment endpoint | Sandbox | Sandbox/staging endpoint | Production endpoint |
| Password/token | Local secret hoặc dev credential | Staging Secret | Production Secret |
| Log level | DEBUG có kiểm soát | INFO | INFO/WARN theo nhu cầu |
| Rotation | Theo môi trường dev | Theo quy trình staging | Theo quy trình production |
| Artifact | Cùng build nếu phù hợp | Artifact đã kiểm thử | Chính artifact đã được phê duyệt |

**Đừng dùng production secret ở môi trường local** chỉ để “chạy giống production”. Nếu cần kiểm thử tích hợp gần thực tế, dùng tài khoản và môi trường test riêng với quyền hạn tối thiểu.

## 28. Tổ chức cấu hình khi có nhiều nhóm chức năng

Một ứng dụng lớn có thể có:

~~~text
app.catalog.*
app.checkout.payment.*
app.checkout.shipping.*
app.notifications.email.*
app.integrations.crm.*
~~~

Không nên gom tất cả secret vào một property chung:

~~~text
app.secret
~~~

vì khó biết nó thuộc subsystem nào, ai được quyền đọc và cần rotate những consumer nào.

Có thể đặt secret keys theo chính namespace chức năng:

~~~text
app.checkout.payment.api-key
app.notifications.email.provider-token
app.integrations.crm.client-secret
~~~

Nên thiết kế quyền truy cập tương ứng:

- Payment component chỉ dùng payment credential.
- Email component chỉ dùng provider token.
- CRM integration chỉ dùng client secret liên quan.

Nếu tất cả chạy trong cùng process, quyền đọc ở mức process có thể rộng; giới hạn này cần được hiểu khi thiết kế an toàn. Tách process/service hoặc danh tính runtime đôi khi cần thiết để đạt least privilege nghiêm ngặt.

### 28.1. Đừng nhầm property prefix với boundary bảo mật

**@ConfigurationProperties(prefix = "app.checkout.payment")** giúp tổ chức Java model, nhưng không tự ngăn một bean khác đọc Environment hoặc một file secret có thể truy cập bởi cùng process. Boundary bảo mật thực sự cần được thực thi ở hệ điều hành, container, service account hoặc secret management infrastructure.

## 29. Cách thay đổi cấu hình mà không làm phát sinh khác biệt không kiểm soát

Một quy trình change management:

1. Xác định giá trị là **common**, **environment-specific** hay **secret**.
2. Chọn owner: developer, platform team, security team hoặc service owner.
3. Ghi tên canonical key và ý nghĩa.
4. Ghi đơn vị, mặc định, phạm vi giá trị cho phép.
5. Đặt non-secret default vào code repository hoặc nguồn vận hành được phê duyệt.
6. Đặt giá trị khác biệt môi trường trong profile Config Data, ConfigMap hoặc file ngoài JAR.
7. Cấp secret qua hệ thống riêng.
8. Kiểm thử môi trường liên quan trước production.
9. Rollout có kiểm soát, dùng health/readiness và metric phù hợp.
10. Theo dõi thay đổi và khả năng rollback cả artifact lẫn config.
11. Không xem secret value như dữ liệu có thể lưu trong lịch sử pull request.
12. Thực hiện rotation và thu hồi đúng quy trình.

### 29.1. Có nên lưu ConfigMap trong Git?

Vì ConfigMap dành cho dữ liệu không bí mật, lưu manifest ở Git có thể phù hợp với GitOps. Tuy nhiên, URL nội bộ, domain hoặc thông tin topology vẫn có thể nhạy cảm ở mức tổ chức. Phân loại và giới hạn repository theo chính sách.

Không commit **Kubernetes Secret** có mật khẩu thật dưới dạng base64 rồi cho rằng đã được bảo vệ.

## 30. Kiểm thử cấu hình theo môi trường

Có thể kiểm thử một nhóm property bằng **@SpringBootTest(properties = ...)** mà không cần kết nối production.

Ví dụ type:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        String apiKey) {
}
~~~

Một integration test:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.payment.base-url=https://test-pay.example.invalid",
    "app.payment.connect-timeout=500ms",
    "app.payment.request-timeout=5s",
    "app.payment.api-key=test-only-placeholder"
})
class PaymentConfigurationTest {

    @Autowired
    PaymentProperties properties;

    @Test
    void bindsRuntimeConfiguration() {
        assertEquals(
                URI.create("https://test-pay.example.invalid"),
                properties.baseUrl());
        assertEquals(
                Duration.ofMillis(500),
                properties.connectTimeout());
        assertEquals(
                Duration.ofSeconds(5),
                properties.requestTimeout());
    }
}
~~~

Test giả định project có **spring-boot-starter-test**, đã đăng ký configuration properties phù hợp và các bean khác không bắt buộc kết nối tới database thật trong quá trình tạo test context. Giá trị **test-only-placeholder** không phải secret thật.

### 30.1. Test không đồng nghĩa đã kiểm tra deploy secret

Một test với placeholder chứng minh rằng Java model được bind. Nó **không chứng minh** Kubernetes Secret đã tồn tại đúng namespace, mount vào đúng path, hoặc process có quyền đọc.

Cần thêm deploy smoke tests và readiness checks để kiểm tra nguồn secret thật trong môi trường test được kiểm soát, không in nội dung secret.

## 31. Dùng ApplicationContextRunner cho cấu hình nhẹ

**ApplicationContextRunner** có thể tạo một context nhỏ và cung cấp property values:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfig {
    }

    @Test
    void usesValuesFromProvidedPropertySource() {
        runner.withPropertyValues(
                "app.payment.base-url=https://test-pay.example.invalid",
                "app.payment.connect-timeout=2s",
                "app.payment.request-timeout=10s",
                "app.payment.api-key=test-only-placeholder"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            PaymentProperties p =
                    context.getBean(PaymentProperties.class);
            assertThat(p.requestTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
        });
    }
}
~~~

Loại test này hữu ích cho configuration model. Có thể bổ sung test failure khi thiếu key bắt buộc hoặc khi Duration không chuyển kiểu được.

### 31.1. Test precedence trong phạm vi phù hợp

Một **ApplicationContextRunner** không phải lúc nào cũng mô phỏng toàn bộ quá trình SpringApplication nạp Config Data/profiles như runtime thật. Khi cần kiểm chứng thứ tự profile-specific files hoặc import location, sử dụng integration test với Spring Boot startup đúng cơ chế, không chỉ thêm vài property vào một test context nhỏ.

## 32. Các lỗi phổ biến khi tách ba tầng

### Lỗi 1: Đặt password trong application-prod.yml

**Vấn đề:** file thường được commit hoặc đóng gói; ai có quyền đọc Git/JAR có thể xem giá trị.

**Cách xử lý:** đưa secret sang Secret Manager, Kubernetes Secret/volume, env được bảo vệ hoặc một runtime secret source có chính sách truy cập phù hợp.

### Lỗi 2: Dùng mỗi môi trường một JAR chỉ để đổi URL

**Vấn đề:** staging có thể kiểm thử artifact khác production.

**Cách xử lý:** build một lần, cấp runtime configuration khác nhau qua profiles và external sources.

### Lỗi 3: Tưởng profile là cơ chế mã hóa

**Vấn đề:** application-prod.yml là file text, không bảo vệ password.

**Cách xử lý:** tách bí mật khỏi các file profile dù file profile nằm trong repository riêng.

### Lỗi 4: Chỉ có một application.yml chung nhưng chứa mọi URL production

**Vấn đề:** local/dev vô tình dùng hệ thống thật hoặc phải sửa file thủ công.

**Cách xử lý:** chỉ giữ default an toàn, dùng profile-specific config hoặc file ngoài JAR.

### Lỗi 5: Đặt spring.profiles.active trong application-prod.yml

**Vấn đề:** sai vị trí profile activation và không phù hợp quy tắc Boot.

**Cách xử lý:** bật profile từ launcher/nguồn non-profile-specific.

### Lỗi 6: Sai tên env

**Vấn đề:** ghi **APP_PAYMENT_API_KEY** cho key canonical **app.payment.api-key** rồi mong Binder luôn hiểu giống dạng chuẩn.

**Cách xử lý:** dùng **APP_PAYMENT_APIKEY** theo quy tắc dots → underscore, hyphens → bỏ, uppercase.

### Lỗi 7: Nghĩ có .env thì Java tự nhận

**Vấn đề:** file chưa được công cụ launch đưa vào process.

**Cách xử lý:** kiểm tra Docker Compose, IDE, shell hoặc secret manager integration đang thực sự cấp những biến nào.

### Lỗi 8: Dùng ConfigMap để lưu secret

**Vấn đề:** ConfigMap không thiết kế cho bí mật; không có secrecy/encryption bảo đảm.

**Cách xử lý:** dùng Secret hoặc external secret store và kiểm soát RBAC.

### Lỗi 9: Cho rằng base64 là mã hóa

**Vấn đề:** dữ liệu Kubernetes Secret có thể giải mã khi có quyền đọc.

**Cách xử lý:** bảo vệ API access, etcd encryption at rest, workload identity, audit và secret lifecycle.

### Lỗi 10: Import optional secret location ở production rồi bỏ qua kết quả trống

**Vấn đề:** app có thể khởi động mà không có credential cần thiết.

**Cách xử lý:** dùng required location hoặc validation/startup guard theo hợp đồng.

### Lỗi 11: Rotation file secret nhưng không reload app

**Vấn đề:** mount đã đổi nhưng object/config bean hoặc connection pool có thể đang dùng giá trị cũ.

**Cách xử lý:** thiết kế restart/reload và kiểm chứng cả consumer.

### Lỗi 12: Logging toàn bộ Environment

**Vấn đề:** lộ token/password trong log hoặc endpoint debug.

**Cách xử lý:** chỉ log tên key và giá trị không nhạy cảm; kiểm soát Actuator exposure.

### Lỗi 13: Nhầm spring.config.location với additional-location

**Vấn đề:** dùng location thay thế làm mất những default search locations.

**Cách xử lý:** chọn **additional-location** khi chỉ muốn bổ sung.

### Lỗi 14: Không hiểu override của nhiều profile

**Vấn đề:** hai profile khai báo cùng key và profile sau có thể thắng theo thứ tự profile.

**Cách xử lý:** hạn chế key mâu thuẫn, ghi rõ thứ tự và test tổ hợp thực tế.

### Lỗi 15: Tưởng secret prefix tự tạo boundary bảo mật

**Vấn đề:** một process có quyền đọc secret source có thể đọc nhiều giá trị bất kể annotation prefix.

**Cách xử lý:** thực thi quyền tại secret store, filesystem, Pod/service account và hạ tầng runtime.

## 33. Bài thực hành

### Bài A — phân loại common, environment và secret

Cho các key:

~~~text
spring.application.name
app.payment.connect-timeout
app.payment.base-url
spring.datasource.url
spring.datasource.password
app.payment.api-key
logging.level.com.example.shop
~~~

Hãy phân loại:

- **Common**: spring.application.name, app.payment.connect-timeout (nếu mọi môi trường dùng chung default).
- **Environment-specific**: app.payment.base-url, datasource URL, logging level.
- **Secret**: datasource password, payment API key.

Thảo luận: username hoặc endpoint nội bộ có cần hạn chế công bố không? Phân loại “không phải password” không tự động có nghĩa được phép công khai.

### Bài B — tạo cấu hình chung và profile

1. Tạo **application.yml** với timeout, tên ứng dụng và page size.
2. Tạo **application-dev.yml** dùng sandbox endpoint.
3. Tạo **application-prod.yml** dùng production endpoint không nhạy cảm.
4. Chạy cùng JAR với **--spring.profiles.active=dev** và **prod**.
5. Gọi một endpoint demo chỉ hiển thị URL giả, timeout không nhạy cảm.

**Mục tiêu:** nhận biết một artifact dùng nhiều bộ Config Data.

### Bài C — cấp secret từ environment

1. Thêm property **app.payment.api-key** vào Java configuration model.
2. Không ghi secret trong source.
3. Cấp **APP_PAYMENT_APIKEY** qua cơ chế runtime được phép (dùng token giả cho bài tập).
4. Thử không cấp key nếu tính năng yêu cầu nó.
5. Xác nhận validation/startup guard từ chối cấu hình thiếu.

**Mục tiêu:** secret tách khỏi JAR và được kiểm tra khi cần.

### Bài D — configtree từ local directory

1. Tạo thư mục **.local-secrets/** không theo dõi bởi Git.
2. Tạo file **app.payment.api-key** chứa chuỗi test giả.
3. Chạy với **--spring.config.import=configtree:./.local-secrets/** (nếu location resolution của môi trường chạy hỗ trợ; có thể dùng đường file tuyệt đối phù hợp).
4. Đọc giá trị vào configuration object nhưng không in secret.
5. Xóa/tạm di chuyển file và kiểm tra failure behavior.

**Mục tiêu:** biết một file mount có thể ánh xạ thành Spring property.

### Bài E — cấu hình Kubernetes

1. Tạo ConfigMap với profile, datasource URL và non-secret settings.
2. Chuẩn bị Secret qua quy trình test của cluster, không commit giá trị thật.
3. Mount Secret vào **/etc/shop-secrets/**.
4. Cấp **SPRING_CONFIG_IMPORT=configtree:/etc/shop-secrets/**.
5. Kiểm tra app khởi động và health endpoint mà không hiển thị secret.

**Mục tiêu:** phân tách cấu hình và quyền ở cấp runtime platform.

### Bài F — thử override và precedence

1. Trong base file đặt **app.payment.request-timeout=10s**.
2. Trong prod file đặt **8s**.
3. Cấp env **APP_PAYMENT_REQUESTTIMEOUT=12s**.
4. Chạy thêm argument **--app.payment.request-timeout=6s**.
5. Quan sát giá trị cuối.
6. Bỏ từng nguồn để hiểu vai trò precedence.

**Mục tiêu:** phân biệt giá trị “trong file” và giá trị có hiệu lực khi app chạy.

### Bài G — diễn tập rotation

1. Cấp một secret giả **version-A**.
2. Khởi chạy ứng dụng trong test environment.
3. Thay secret source thành **version-B**.
4. Kiểm tra xem process thực sự có thấy bản mới hay chưa.
5. Thực hiện rolling restart nếu kiến trúc yêu cầu.
6. Xác minh chức năng hoạt động với bản mới, sau đó thu hồi bản cũ trong mô hình thử nghiệm.

**Mục tiêu:** hiểu rotation không chỉ là sửa file secret.

## 34. Checklist trước khi deploy

- Artifact có được build một lần và dùng lại cho các môi trường không?
- Các property common có thực sự không nhạy cảm và an toàn khi đóng gói không?
- File profile có chỉ chứa khác biệt môi trường không mật không?
- Production profile được chọn bằng launcher/nguồn phù hợp chưa?
- Có password/token/private key thật trong Git, JAR hoặc Docker image không?
- Secret source có đúng namespace, mount path, file name và property prefix không?
- Nếu dùng configtree, tên file có khớp canonical key không?
- Nếu dùng env, tên đã theo quy tắc relaxed binding chưa?
- Những secret bắt buộc có validation/fail-fast không?
- Có dùng optional import sai ở production không?
- ConfigMap có vô tình chứa dữ liệu bí mật không?
- Secret store/Kubernetes đã có RBAC least privilege và encryption at rest phù hợp chưa?
- Các container không cần secret có bị cấp quyền đọc không?
- Log, Actuator và debug endpoint có bị lộ giá trị không?
- Thay file/Secret có yêu cầu restart hoặc refresh không?
- Có kế hoạch rotation và thu hồi secret cũ không?
- Có biết property cuối cùng từ nguồn nào và profile nào không?
- Có test cấu hình staging trước rollout production không?
- Đội vận hành có hướng dẫn rollback cả artifact và config không?
- Các nguồn cấu hình có owner, change log và quyền sửa rõ ràng không?

## 35. Kết luận

Một kiến trúc cấu hình Spring Boot dễ triển khai và an toàn nên tách **giá trị chung**, **khác biệt môi trường** và **bí mật riêng**:

- **application.yml** chứa những default và quy ước chung không bí mật.
- **application-{profile}.yml** hoặc Config Data ngoài JAR chứa giá trị thay đổi theo môi trường.
- **Secret manager**, Kubernetes Secret, runtime env hoặc volume/configtree cấp password/token/key riêng.
- Spring Boot kết hợp các nguồn vào Environment theo **quy tắc ưu tiên**, rồi bind chúng sang **@ConfigurationProperties**.
- Profile chọn bộ cấu hình, **không mã hóa bí mật**.
- ConfigMap phù hợp cho dữ liệu không mật; Secret dùng cho dữ liệu nhạy cảm nhưng vẫn cần quyền truy cập và mã hóa lưu trữ.
- **configtree:** là cơ chế đọc file theo key, không thay thế chính sách quản lý secret.
- Một JAR/image nên được build một lần rồi deploy sang nhiều môi trường bằng những bộ runtime config khác nhau.
- Secret rotation và thay đổi runtime cần quy trình reload/restart, kiểm chứng và thu hồi rõ ràng.
- Hãy coi cấu hình là **hợp đồng vận hành** có tên chuẩn, owner, validation, kiểm thử, tài liệu và audit.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, *PropertySource Order*, *Config Data*, *Profile Specific Files*, *Using Configuration Trees*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Kubernetes — ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes — Good Practices for Kubernetes Secrets: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
