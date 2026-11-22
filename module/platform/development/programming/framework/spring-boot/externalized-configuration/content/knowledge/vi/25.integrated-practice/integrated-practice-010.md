# Đóng gói một lần, chạy ở hai môi trường và tài liệu hóa hợp đồng cấu hình

## 1. Mục tiêu bài thực hành

Ứng dụng Spring Boot có thể sử dụng **cùng một JAR** tại nhiều môi trường mà không cần build lại mã nguồn. Điều kiện là tách biệt rõ:

- **Artifact**: mã Java đã biên dịch, dependencies, tài nguyên chung không nhạy cảm.
- **Cấu hình chung**: default hợp lý với nhiều môi trường.
- **Cấu hình môi trường**: profile, port, endpoint, timeout, logging level riêng.
- **Secret**: API key, password, token được cấp ngoài source/JAR/image vào lúc chạy.

Bài này tạo một ứng dụng **config-once-demo** với hai lần chạy:

| Thuộc tính | Development | Production-like |
| --- | --- | --- |
| Profile | dev | prod |
| External config | deploy/dev | deploy/prod |
| Port | 8081 | 8082 |
| Deployment label | development | production |
| Gateway | Disabled | Enabled |
| Request timeout | 12s | 6s |
| Connect timeout | 2s | 2s |
| API key | Không cần | Bắt buộc, cấp runtime |
| Executable JAR | Cùng một file | Cùng một file |

**Kết quả học tập:** build một JAR, lưu SHA-256, chạy cùng artifact ở hai môi trường với cấu hình ngoài JAR, kiểm chứng giá trị đã bind, xử lý secret đúng chỗ và viết được một **configuration contract**.

Ví dụ dùng **Java 21**, **Maven**, **Spring Boot 3.3.x**, Spring MVC và Jakarta Bean Validation. Các URL thuộc domain **example.invalid** hoàn toàn là giả và không có giao dịch thanh toán thật.

## 2. Tư duy build once, deploy many

Quy trình mong muốn:

~~~text
Source + tests
      |
      v
Build một lần với Maven
      |
      v
config-once-demo-0.0.1-SNAPSHOT.jar
      |
      | SHA-256 duy nhất
      |
      +------------------------+
      |                        |
      v                        v
Môi trường dev            Môi trường prod
profile=dev               profile=prod
config ngoài JAR          config ngoài JAR
port 8081                 port 8082
gateway disabled          gateway enabled
không cần secret          secret runtime
      |                        |
      +------------------------+
                   |
                   v
       Cùng binary, behavior khác nhau
~~~

Không nên build **app-dev.jar** và **app-prod.jar** chỉ để đổi endpoint hoặc timeout. Nếu hai artifacts khác bytes, staging có thể không kiểm thử đúng file sau đó chạy production.

**Build once** không có nghĩa config không đổi hoặc process không cần restart. Nó nghĩa những thay đổi môi trường không đòi hỏi build lại binary.

## 3. Chuẩn bị

Cần:

1. Java 21.
2. Maven 3.9 hoặc Maven Wrapper.
3. Hai port cục bộ 8081, 8082 còn khả dụng.
4. Terminal Bash/zsh hoặc PowerShell.
5. Chỉ sử dụng API key giả cho bài thực hành.
6. Không dùng endpoint hay credential production thật.

Kiểm tra:

~~~bash
java -version
mvn -version
~~~

Không cần chạy PostgreSQL hay gateway thật. Bài học tập trung vào externalized configuration, binding và validation.

## 4. Cấu trúc thư mục

~~~text
config-once-demo/
├── pom.xml
├── .gitignore
├── src/
│   ├── main/
│   │   ├── java/com/example/configonce/
│   │   │   ├── ConfigOnceApplication.java
│   │   │   ├── config/
│   │   │   │   ├── DeploymentProperties.java
│   │   │   │   └── GatewayProperties.java
│   │   │   └── web/
│   │   │       └── ConfigurationSummaryController.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/configonce/
│           ├── ConfigOnceApplicationTest.java
│           └── config/GatewayPropertiesRunnerTest.java
├── deploy/
│   ├── dev/application-dev.yml
│   ├── prod/application-prod.yml
│   └── config-contract.md
└── target/
    └── config-once-demo-0.0.1-SNAPSHOT.jar
~~~

**src/main/resources/application.yml** đi vào JAR. Các file trong **deploy/** được cấp ngoài artifact tại runtime.

Một dự án thực tế có thể đặt external config ở GitOps repository, Helm chart, ConfigMap hoặc file mount, không cần giữ trong cùng source tree. Quan trọng là secret thật không đi vào source hoặc artifact.

## 5. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
              https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>config-once-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Spring Boot 3.3.13** là bản minh họa của dòng 3.3.x; dự án thật cần lựa chọn phiên bản được duy trì/bảo mật theo chính sách của tổ chức.

- **starter-web**: Spring MVC và embedded server.
- **starter-validation**: Jakarta Bean Validation implementation.
- **starter-test**: JUnit, AssertJ, Spring Boot Test.
- **spring-boot-maven-plugin**: đóng gói executable JAR.

Không nhúng secrets vào resource filtering, Maven build variables hay Docker build arguments.

## 6. Main class và configuration registration

File **src/main/java/com/example/configonce/ConfigOnceApplication.java**:

~~~java
package com.example.configonce;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigOnceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigOnceApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** tìm những type có **@ConfigurationProperties** ở các package con của ứng dụng.

Chỉ khai báo annotation trên record chưa đủ để mọi context tự tạo bean. Có thể đăng ký bằng scan hoặc **@EnableConfigurationProperties**.

Không cần main class riêng cho dev và prod. Cùng SpringApplication khởi động với nguồn config khác nhau.

## 7. DeploymentProperties

File **src/main/java/com/example/configonce/config/DeploymentProperties.java**:

~~~java
package com.example.configonce.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.deployment")
public record DeploymentProperties(
        @NotBlank String label) {
}
~~~

Property:

~~~text
demo.deployment.label
~~~

Nó chỉ ra nhãn không nhạy cảm của deployment. Không có default chung; nếu thiếu label, startup nên fail vì cấu hình triển khai không đầy đủ.

Đây là lựa chọn nhằm minh họa **required runtime configuration**.

## 8. GatewayProperties

File **src/main/java/com/example/configonce/config/GatewayProperties.java**:

~~~java
package com.example.configonce.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.gateway")
public record GatewayProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        boolean enabled,
        String apiKey) {

    @AssertTrue(
        message = "request-timeout must exceed connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }

    @AssertTrue(
        message = "gateway api-key is required when enabled")
    public boolean isCredentialPresentWhenEnabled() {
        return !enabled ||
                (apiKey != null && !apiKey.isBlank());
    }

    @AssertTrue(
        message = "enabled gateway requires HTTPS base-url")
    public boolean isHttpsWhenEnabled() {
        return !enabled ||
                (baseUrl != null &&
                "https".equalsIgnoreCase(baseUrl.getScheme()));
    }
}
~~~

Canonical keys:

~~~text
demo.gateway.base-url
demo.gateway.connect-timeout
demo.gateway.request-timeout
demo.gateway.enabled
demo.gateway.api-key
~~~

### 8.1. Vì sao dùng kiểu URI và Duration?

Spring Boot Binder chuyển string sang type Java:

~~~text
https://sandbox.example.invalid -> URI
2s                              -> Duration.ofSeconds(2)
500ms                           -> Duration.ofMillis(500)
true                            -> boolean true
~~~

So sánh Duration đã được convert đáng tin hơn so sánh những chuỗi thời gian khác định dạng.

### 8.2. Ràng buộc thời gian

Hai timeout đều có thể parse được nhưng vi phạm hợp đồng nghiệp vụ minh họa:

~~~text
connect-timeout=8s
request-timeout=3s
~~~

Method **isTimeoutOrderValid()** yêu cầu request timeout lớn hơn connect timeout. Đây là một rule được ứng dụng demo chọn, không phải quy luật chung cho mọi HTTP client.

### 8.3. Secret theo mode

- Gateway disabled ở dev: không cần apiKey.
- Gateway enabled ở prod: apiKey bắt buộc có nội dung.
- Gateway enabled: URL cần dùng scheme HTTPS.

**@AssertTrue** là cách viết ràng buộc cross-field đơn giản. Nếu ứng dụng cần message gắn với trường cụ thể, có thể dùng custom class-level Bean Validation constraint.

### 8.4. Không log record chứa secret

Record tự sinh **toString()** bao gồm components, có thể làm lộ apiKey.

Không thực hiện:

~~~java
System.out.println(gatewayProperties);
~~~

Không log token trong exception, REST response hoặc metric labels. Tên property và trạng thái validation đã đủ cho nhiều tình huống chẩn đoán.

## 9. Endpoint xem cấu hình không nhạy cảm

File **src/main/java/com/example/configonce/web/ConfigurationSummaryController.java**:

~~~java
package com.example.configonce.web;

import java.util.Arrays;
import java.util.List;

import com.example.configonce.config.DeploymentProperties;
import com.example.configonce.config.GatewayProperties;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ConfigurationSummaryController {

    private final DeploymentProperties deployment;
    private final GatewayProperties gateway;
    private final Environment environment;

    public ConfigurationSummaryController(
            DeploymentProperties deployment,
            GatewayProperties gateway,
            Environment environment) {
        this.deployment = deployment;
        this.gateway = gateway;
        this.environment = environment;
    }

    @GetMapping("/configuration")
    public PublicSummary summary() {
        return new PublicSummary(
                deployment.label(),
                Arrays.asList(environment.getActiveProfiles()),
                gateway.enabled(),
                gateway.connectTimeout().toMillis(),
                gateway.requestTimeout().toMillis());
    }

    public record PublicSummary(
            String deployment,
            List<String> activeProfiles,
            boolean gatewayEnabled,
            long connectTimeoutMs,
            long requestTimeoutMs) {
    }
}
~~~

Endpoint demo chỉ công bố một số field không nhạy cảm; **không trả apiKey, không dump Environment**.

Trong production thật, ngay cả thông tin profile hoặc feature status cũng có thể là metadata nội bộ. Endpoint cần được bảo vệ hoặc loại bỏ sau bài học.

## 10. Base application.yml

File **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: config-once-demo

server:
  port: 8080

demo:
  gateway:
    connect-timeout: 2s
    request-timeout: 10s

logging:
  level:
    root: INFO
~~~

Cấu hình chung chứa:

- Tên ứng dụng.
- Cổng fallback 8080.
- Connect timeout mặc định 2s.
- Request timeout mặc định 10s.
- Log level INFO.

Không chứa:

~~~text
demo.deployment.label
demo.gateway.base-url
demo.gateway.api-key
~~~

Nhãn deployment, gateway endpoint được cấp theo môi trường; API key phải do runtime secret source cung cấp.

Nếu chạy không có external config, **@NotBlank** hoặc **@NotNull** có thể khiến startup fail. Đây là hành vi fail-fast có chủ đích.

## 11. File dev ở ngoài JAR

File **deploy/dev/application-dev.yml**:

~~~yaml
server:
  port: 8081

demo:
  deployment:
    label: "development"

  gateway:
    enabled: false
    base-url: "https://sandbox-gateway.example.invalid"
    request-timeout: 12s

logging:
  level:
    com.example.configonce: DEBUG
~~~

Dev behavior:

- Port 8081.
- Profile dev.
- Deployment label development.
- Gateway disabled.
- Request timeout 12s thay vì default 10s.
- Connect timeout 2s kế thừa từ common file.
- Không cần API key vì gateway disabled.

File không chứa **spring.profiles.active=dev**. Active profile sẽ được chọn từ launcher hoặc nguồn non-profile-specific.

## 12. File prod ở ngoài JAR

File **deploy/prod/application-prod.yml**:

~~~yaml
server:
  port: 8082

demo:
  deployment:
    label: "production"

  gateway:
    enabled: true
    base-url: "https://gateway.example.invalid"
    request-timeout: 6s

logging:
  level:
    root: WARN
    com.example.configonce: INFO
~~~

Prod behavior:

- Port 8082.
- Profile prod.
- Deployment label production.
- Gateway enabled.
- Request timeout 6s.
- Connect timeout 2s từ common file.
- Gateway URL có HTTPS scheme.
- API key **bắt buộc nhưng không có trong YAML**.

Khi enabled=true mà không có secret, validation phải từ chối startup.

## 13. Build đúng một lần

Tại project root:

~~~bash
mvn clean verify
~~~

Maven Spring Boot plugin tạo executable JAR:

~~~text
target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu có Maven Wrapper:

~~~bash
./mvnw clean verify
~~~

Maven **verify** chạy những kiểm tra đã được cấu hình trong lifecycle, bao gồm tests phù hợp. Với dự án đơn giản, **mvn clean package** cũng có thể tạo JAR.

**Sau build không chạy thêm một lượt package riêng cho prod.** Cả hai môi trường sử dụng chính artifact này.

## 14. Ghi nhận SHA-256

Linux:

~~~bash
sha256sum target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

macOS:

~~~bash
shasum -a 256 target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Path target/config-once-demo-0.0.1-SNAPSHOT.jar -Algorithm SHA256
~~~

Lưu checksum thực tế. Cuối bài chạy lại trên chính file đó. Không ghi sẵn một hash giả vào tài liệu vì hash phải được tính trên artifact thật.

**Hash giống nhau xác nhận bytes JAR không đổi**, nhưng không tự chứng minh config đúng; cần kết hợp smoke tests.

## 15. Chạy dev bằng chính JAR

Tại project root, terminal thứ nhất:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/
~~~

Hai tham số:

- **spring.profiles.active=dev** chọn profile dev.
- **spring.config.additional-location=file:./deploy/dev/** bổ sung thư mục Config Data ngoài JAR.

Trong file path kiểu directory, dấu **/** cuối giúp Boot ghép tên file dựa vào **spring.config.name**.

Dùng **additional-location** để vẫn giữ common application.yml trong JAR; **spring.config.location** có thể thay thế các search locations mặc định theo quy tắc Boot.

### 15.1. Kiểm tra response

~~~bash
curl -fsS http://localhost:8081/api/configuration
~~~

Kết quả minh họa:

~~~json
{
  "deployment": "development",
  "activeProfiles": ["dev"],
  "gatewayEnabled": false,
  "connectTimeoutMs": 2000,
  "requestTimeoutMs": 12000
}
~~~

**2000ms** đến từ common 2s, **12000ms** đến từ dev override 12s. URL sandbox không được gọi và secret không bị trả trong response.

### 15.2. Đổi timeout mà không rebuild

Dừng ứng dụng dev và chạy lại:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=20s
~~~

Response có **requestTimeoutMs=20000** vì CLI override có ưu tiên cao hơn Config Data thông thường.

JAR vẫn không đổi và không cần Maven build mới.

## 16. Cấp secret cho prod

Property canonical:

~~~text
demo.gateway.api-key
~~~

Environment variable theo Spring Boot relaxed binding:

~~~text
DEMO_GATEWAY_APIKEY
~~~

Secret nên đến từ secret manager, container runtime, Kubernetes Secret hoặc công cụ local secrets được phê duyệt.

**Không đặt literal production API key trong câu lệnh được lưu vào shell history.** Đối với bài thực hành, chỉ dùng một credential giả không có quyền vào hệ thống thật.

Nếu process chạy trong container hoặc CI, cần bảo đảm biến được inject **vào chính process Java**, không chỉ tồn tại trong một shell hoặc file .env chưa được công cụ xử lý.

## 17. Chạy prod bằng đúng JAR

Ở terminal khác, sau khi nền tảng đã cấp **DEMO_GATEWAY_APIKEY** an toàn:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:./deploy/prod/
~~~

Không chạy Maven lần hai.

Kiểm tra:

~~~bash
curl -fsS http://localhost:8082/api/configuration
~~~

Response minh họa:

~~~json
{
  "deployment": "production",
  "activeProfiles": ["prod"],
  "gatewayEnabled": true,
  "connectTimeoutMs": 2000,
  "requestTimeoutMs": 6000
}
~~~

So sánh:

| Giá trị | Dev | Prod |
| --- | --- | --- |
| deployment | development | production |
| profile | dev | prod |
| HTTP port | 8081 | 8082 |
| gatewayEnabled | false | true |
| connectTimeoutMs | 2000 | 2000 |
| requestTimeoutMs | 12000 | 6000 |
| secret | Không bắt buộc | Bắt buộc |

Cùng một Java class và artifact đã được sử dụng. Giá trị hiệu lực khác nhau do runtime sources.

### 17.1. Chạy hai process đồng thời

Vì khác port, dev và prod có thể cùng chạy trên localhost nếu hệ thống còn đủ tài nguyên và không có xung đột khác.

Mỗi process có Environment riêng. Không nên dùng một shell có secret prod để thử dev nếu không kiểm soát rõ những biến đang tồn tại.

## 18. Kiểm thử lỗi cấu hình prod

### 18.1. Thiếu API key

Chạy prod ở process không có **DEMO_GATEWAY_APIKEY**. Vì enabled=true, method **isCredentialPresentWhenEnabled()** trả false; nếu Validation infrastructure hoạt động đúng, application context startup fail.

Đây là behavior mong muốn để tránh integration được bật nhưng chưa có credential.

### 18.2. Sai Duration

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=not-a-duration
~~~

Binder không thể chuyển **not-a-duration** sang Duration, nên binding fail.

### 18.3. Sai quan hệ giữa hai Duration

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:./deploy/dev/ \
  --demo.gateway.request-timeout=1s
~~~

Nếu connect-timeout đang là 2s, thời gian 1s vẫn parse được nhưng vi phạm rule requestTimeout > connectTimeout.

### 18.4. Prod dùng HTTP

Nếu enabled=true mà base-url có scheme **http**, validation đã thiết kế yêu cầu HTTPS sẽ fail.

**Không bỏ validation để che lỗi deploy.** Cần sửa nguồn cấu hình.

## 19. Chạy với OS environment variables

Bash/zsh:

~~~bash
SPRING_PROFILES_ACTIVE=dev \
SPRING_CONFIG_ADDITIONALLOCATION=file:./deploy/dev/ \
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Prod, khi secret đã được inject vào Environment:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
SPRING_CONFIG_ADDITIONALLOCATION=file:./deploy/prod/ \
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell dev:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "file:./deploy/dev/"
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

PowerShell prod khi secret đã có:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
$env:SPRING_CONFIG_ADDITIONALLOCATION = "file:./deploy/prod/"
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Sau đó, có thể dọn các biến thử nghiệm trong PowerShell:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE -ErrorAction SilentlyContinue
Remove-Item Env:SPRING_CONFIG_ADDITIONALLOCATION -ErrorAction SilentlyContinue
Remove-Item Env:DEMO_GATEWAY_APIKEY -ErrorAction SilentlyContinue
~~~

Tùy platform, process environment có thể bị người/công cụ có quyền truy cập quan sát. Một biến môi trường là cơ chế **cấp runtime**, không tự thay thế secret management và phân quyền.

## 20. Tính lại checksum

Sau khi dev và prod đã chạy, **không build lại**, tính SHA-256 trên JAR:

~~~bash
sha256sum target/config-once-demo-0.0.1-SNAPSHOT.jar
~~~

Hoặc:

~~~powershell
Get-FileHash -Path target/config-once-demo-0.0.1-SNAPSHOT.jar -Algorithm SHA256
~~~

Giá trị phải giống checksum đã lưu ngay sau build.

Điều này chứng minh dev và prod không cần hai artifacts. Nhưng chỉ với checksum thì chưa đủ; các smoke responses ở mục 15 và 17 chứng minh behavior đã thay đổi.

## 21. Hợp đồng cấu hình là gì?

**Configuration contract** là thỏa thuận giữa code module và hệ thống triển khai:

1. Key canonical nào được hỗ trợ?
2. Key có type Java nào?
3. Đơn vị của giá trị là gì?
4. Default nằm ở đâu?
5. Key nào bắt buộc và trong điều kiện nào?
6. Nguồn nào được phép cấp giá trị?
7. Nếu nhiều nguồn cùng cấp, precedence thế nào?
8. Có phải secret không?
9. Ai sở hữu key/contract và ai cấp value?
10. Những ràng buộc hợp lệ là gì?
11. Khi đổi value có cần restart không?
12. Nếu rename key, migration diễn ra như thế nào?
13. Làm sao kiểm tra không lộ credential?

Hợp đồng cấu hình biến các string rải rác thành một API được tài liệu hóa và kiểm thử.

## 22. Configuration contract của demo

Một bảng có thể lưu trong **deploy/config-contract.md**:

| Canonical key | Type | Default | Dev | Prod | Nhạy cảm |
| --- | --- | --- | --- | --- | --- |
| spring.application.name | String | config-once-demo | Kế thừa | Kế thừa | Không |
| server.port | int | 8080 | 8081 | 8082 | Không |
| spring.profiles.active | Profile | Không hard-code | dev | prod | Không |
| spring.config.additional-location | Location | Không | deploy/dev/ | deploy/prod/ | Đường dẫn có thể nội bộ |
| demo.deployment.label | String | Không | development | production | Không |
| demo.gateway.enabled | boolean | false khi thiếu | false | true | Không |
| demo.gateway.base-url | URI | Không | Sandbox | HTTPS prod giả | Endpoint |
| demo.gateway.connect-timeout | Duration | 2s | 2s | 2s | Không |
| demo.gateway.request-timeout | Duration | 10s | 12s | 6s | Không |
| demo.gateway.api-key | String | Không | Không cần | Runtime Secret | **Có** |
| logging.level.root | Log level | INFO | INFO | WARN | Không |

### 22.1. Requiredness

| Key/ràng buộc | Yêu cầu |
| --- | --- |
| demo.deployment.label | Không null/trống, mọi môi trường |
| demo.gateway.base-url | Không null |
| demo.gateway.connect-timeout | Không null |
| demo.gateway.request-timeout | Không null |
| Thời gian gateway | requestTimeout > connectTimeout |
| demo.gateway.api-key | Không trống khi enabled=true |
| Gateway URL | Scheme HTTPS khi enabled=true |
| server.port | Integer hợp lệ, port khả dụng |
| spring.profiles.active | Quy trình deploy phải chọn dev/prod có chủ đích |

Không nên đặt default password **changeme** hoặc secret giả vào config chung rồi vô tình để ứng dụng production khởi động sai.

### 22.2. Owner

| Nhóm | Contract owner | Runtime owner |
| --- | --- | --- |
| demo.deployment | Service/Platform | Deployment pipeline |
| demo.gateway | Gateway integration module | Service owner |
| demo.gateway.api-key | Gateway integration định nghĩa key | Secret manager/Platform |
| server.port | Platform | Deployment |
| logging.level.* | SRE/Platform | Deployment |

Contract owner định nghĩa type/meaning/validation. Runtime owner cung cấp values. Secret owner quản lý rotation và quyền truy cập.

## 23. Quy tắc tên biến môi trường

Spring Boot quy định tên env cho canonical properties:

1. Dấu chấm **.** → underscore **_**.
2. Dấu gạch ngang **-** → bị bỏ.
3. Chuyển thành chữ hoa.

~~~text
demo.gateway.base-url
    -> DEMO_GATEWAY_BASEURL

demo.gateway.connect-timeout
    -> DEMO_GATEWAY_CONNECTTIMEOUT

demo.gateway.request-timeout
    -> DEMO_GATEWAY_REQUESTTIMEOUT

demo.gateway.api-key
    -> DEMO_GATEWAY_APIKEY

demo.deployment.label
    -> DEMO_DEPLOYMENT_LABEL

spring.profiles.active
    -> SPRING_PROFILES_ACTIVE

spring.config.additional-location
    -> SPRING_CONFIG_ADDITIONALLOCATION
~~~

**DEMO_GATEWAY_API_KEY** không phải phép chuyển canonical trực tiếp từ **demo.gateway.api-key**, vì dấu gạch ngang không biến thành một underscore mới.

Nên ghi cả tên canonical và tên env trong contract để tránh lỗi khi viết Helm, Compose, CI hoặc deployment manifests.

## 24. Precedence của các nguồn

Spring Boot định nghĩa thứ tự ưu tiên PropertySources. Một sơ đồ đơn giản gồm những nguồn thường dùng:

~~~text
Default properties
      |
Config Data trong JAR
      |
External Config Data/profile-specific
      |
OS environment variables
      |
Java system properties
      |
Command-line arguments
~~~

Đây chỉ là sơ đồ tương đối cho các nguồn đã chọn, không phải toàn bộ thứ tự của Spring Boot. Test-specific sources, SPRING_APPLICATION_JSON và các nguồn khác có vị trí riêng.

Ví dụ:

~~~text
application.yml:               request-timeout=10s
application-prod.yml:          request-timeout=6s
DEMO_GATEWAY_REQUESTTIMEOUT:   9s
CLI:                           --demo.gateway.request-timeout=4s

Kết quả minh họa: 4s
~~~

CLI có thể override giá trị Config Data. Tuy nhiên nếu override thành 1s trong khi connect-timeout=2s, validation vẫn từ chối. **Giá trị có ưu tiên cao không có nghĩa hợp lệ.**

### 24.1. Default ở Java khác default trong Environment

Nếu dùng Java record với **@DefaultValue**, default được áp dụng ở binding nhưng không nhất thiết viết ngược thành key trong Environment.

Trong ví dụ, default Duration nằm trong **application.yml**, nên có thể nhìn thấy như Config Data property.

Contract phải ghi nguồn default, không chỉ số cuối cùng.

## 25. Nạp secret qua configtree

Thay cho env, secret có thể được mount thành file:

~~~text
/run/secrets/
└── demo.gateway.api-key
~~~

Tên file tương ứng key; nội dung file là secret được platform cấp, không commit.

Có thể khai báo trong external prod configuration:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot Config Data infrastructure có thể import property **demo.gateway.api-key** từ file.

**configtree không tự mã hóa file**. Quyền filesystem, secret store, workload identity và container runtime phải bảo vệ secret.

Nếu secret bắt buộc, đừng tự thêm **optional:** rồi bỏ qua thiếu mount. Có thể dùng fail-fast và kiểm tra deployment.

### 25.1. Rotation không có nghĩa Java record tự đổi

Sau khi bean đã bind, thay giá trị secret file không tự làm GatewayProperties cập nhật. Nếu cần nhận secret mới, có thể cần restart/refresh theo cơ chế đã thiết kế.

Đối với env, process đang chạy thường không nhận giá trị mới khi deployment secret thay đổi. Trong Kubernetes, có thể cần thay Pod hoặc rolling restart.

## 26. Docker image dùng chung

Một Dockerfile đơn giản:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/config-once-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build image một lần:

~~~bash
docker build -t config-once-demo:1.0.0 .
~~~

Dev:

~~~bash
docker run --rm \
  -p 8081:8081 \
  -v "$PWD/deploy/dev:/config:ro" \
  config-once-demo:1.0.0 \
  --spring.profiles.active=dev \
  --spring.config.additional-location=file:/config/
~~~

Prod, khi host có env secret được cấp an toàn:

~~~bash
docker run --rm \
  -p 8082:8082 \
  -v "$PWD/deploy/prod:/config:ro" \
  --env DEMO_GATEWAY_APIKEY \
  config-once-demo:1.0.0 \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/config/
~~~

Image không chứa config dev/prod hay API key. Khác biệt được cung cấp lúc chạy thông qua mount, profile và secret.

**Tag không tự bất biến**: trong production nên pin image digest để bảo đảm cùng bytes image giữa deployments.

## 27. Kubernetes ConfigMap và Secret

Kubernetes có thể cấp non-secret values qua ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-once-prod
data:
  SPRING_PROFILES_ACTIVE: "prod"
  SERVER_PORT: "8082"
  DEMO_DEPLOYMENT_LABEL: "production"
  DEMO_GATEWAY_ENABLED: "true"
  DEMO_GATEWAY_BASEURL: "https://gateway.example.invalid"
  DEMO_GATEWAY_CONNECTTIMEOUT: "2s"
  DEMO_GATEWAY_REQUESTTIMEOUT: "6s"
~~~

Không đưa **DEMO_GATEWAY_APIKEY** vào ConfigMap.

Khi Secret đã được platform cấp, Deployment có thể tham chiếu:

~~~yaml
env:
  - name: DEMO_GATEWAY_APIKEY
    valueFrom:
      secretKeyRef:
        name: gateway-credentials
        key: apiKey
~~~

Đây chỉ là snippet container spec, không phải đầy đủ Deployment manifest.

**Base64 trong Kubernetes Secret không phải mã hóa.** Cluster cần RBAC, encryption at rest, audit và kiểm soát quyền workloads.

Nếu sử dụng ConfigMap env thay profile files, cần chọn một nguồn làm truth và ghi rõ precedence; không cấp nhiều nguồn mâu thuẫn mà thiếu chính sách.

## 28. Test cấu hình với ApplicationContextRunner

Dùng ApplicationContextRunner kiểm thử binding và validation mà không cần chạy web server.

File **src/test/java/com/example/configonce/config/GatewayPropertiesRunnerTest.java**:

~~~java
package com.example.configonce.config;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesRunnerTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class Config {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class)
                .withConfiguration(AutoConfigurations.of(
                        ValidationAutoConfiguration.class));

    @Test
    void devDoesNotRequireApiKey() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=12s",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(p.requestTimeout())
                    .isEqualTo(Duration.ofSeconds(12));
        });
    }

    @Test
    void prodRejectsMissingApiKey() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://gateway.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=6s",
                "demo.gateway.enabled=true"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void prodAcceptsTestOnlyCredential() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://gateway.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=6s",
                "demo.gateway.enabled=true",
                "demo.gateway.api-key=test-only-placeholder"
        ).run(context -> {
            assertThat(context).hasNotFailed();
        });
    }

    @Test
    void detectsInvalidTimeoutOrder() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=8s",
                "demo.gateway.request-timeout=3s",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void detectsInvalidDurationString() {
        runner.withPropertyValues(
                "demo.gateway.base-url=https://sandbox.example.invalid",
                "demo.gateway.connect-timeout=2s",
                "demo.gateway.request-timeout=invalid",
                "demo.gateway.enabled=false"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }
}
~~~

Test cho thấy:

- Disabled gateway không cần secret.
- Enabled gateway thiếu secret fail.
- Test-only credential giúp enabled gateway pass.
- Quan hệ Duration sai bị từ chối.
- Conversion Duration sai bị từ chối.

Đừng assert nguyên văn toàn bộ exception message vì wrapping/format có thể thay đổi giữa patch versions. Khi cần kiểm tra chính xác constraint, hãy tìm root cause với phạm vi thích hợp.

**ApplicationContextRunner** không mặc định chạy đầy đủ Config Data bootstrap của SpringApplication, nên muốn chứng minh file profile thật được nạp cần smoke/integration tests riêng.

## 29. Integration test với SpringBootTest

File **src/test/java/com/example/configonce/ConfigOnceApplicationTest.java**:

~~~java
package com.example.configonce;

import java.time.Duration;

import com.example.configonce.config.DeploymentProperties;
import com.example.configonce.config.GatewayProperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "demo.deployment.label=test",
    "demo.gateway.base-url=https://sandbox.example.invalid",
    "demo.gateway.connect-timeout=1s",
    "demo.gateway.request-timeout=3s",
    "demo.gateway.enabled=false"
})
class ConfigOnceApplicationTest {

    @Autowired
    DeploymentProperties deployment;

    @Autowired
    GatewayProperties gateway;

    @Test
    void bindsExpectedValues() {
        assertThat(deployment.label()).isEqualTo("test");
        assertThat(gateway.enabled()).isFalse();
        assertThat(gateway.connectTimeout())
                .isEqualTo(Duration.ofSeconds(1));
        assertThat(gateway.requestTimeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

Test này cấp config giả riêng nên không cần Secret production hay file ngoài JAR.

Nó kiểm tra wiring và binding trong ApplicationContext, **không tự chứng minh** external dev/prod config đã được mount đúng. Việc đó cần smoke test như các mục 15–17.

## 30. Smoke test hai môi trường

Quy trình:

1. Chạy **mvn clean verify**.
2. Ghi SHA-256 JAR.
3. Chạy dev với profile dev, additional-location dev.
4. Gọi **http://localhost:8081/api/configuration**.
5. Kiểm tra label development, gateway disabled, timeout 12s.
6. Dừng dev hoặc giữ port 8081.
7. Cấp token giả an toàn cho prod.
8. Chạy **cùng JAR** với profile prod, additional-location prod.
9. Gọi **http://localhost:8082/api/configuration**.
10. Kiểm tra label production, gateway enabled, timeout 6s.
11. Thử prod thiếu secret và xem fail-fast.
12. Tính lại SHA-256; giá trị phải giống sau build.

Bảng bằng chứng:

| Kiểm chứng | Dev | Prod |
| --- | --- | --- |
| JAR SHA-256 | Hash X | Hash X |
| Rebuild giữa lần chạy | Không | Không |
| Profile | dev | prod |
| Port | 8081 | 8082 |
| Label | development | production |
| Gateway enabled | false | true |
| Connect timeout | 2s | 2s |
| Request timeout | 12s | 6s |
| Secret | Không bắt buộc | Runtime secret |

Đừng chỉ xem log “Started” rồi kết luận tất cả đúng; hãy đối chiếu giá trị thực từ bean và kiểm tra fail-fast.

## 31. Mẫu nội dung deploy/config-contract.md

Ngoài bảng, ghi những thông tin vận hành:

~~~text
Service:
  config-once-demo

Artifact:
  config-once-demo-0.0.1-SNAPSHOT.jar
  Java 21
  Spring Boot 3.3.x

Base configuration:
  classpath:/application.yml

External configuration:
  dev:  deploy/dev/application-dev.yml
  prod: deploy/prod/application-prod.yml

Bootstrap:
  SPRING_PROFILES_ACTIVE
  SPRING_CONFIG_ADDITIONALLOCATION

Secret contract:
  canonical key: demo.gateway.api-key
  environment name: DEMO_GATEWAY_APIKEY
  required when: demo.gateway.enabled=true
  storage: secret manager/runtime source
  do not commit actual value

Validation:
  deployment.label not blank
  gateway.baseUrl not null
  requestTimeout greater than connectTimeout
  enabled gateway needs nonblank apiKey
  enabled gateway needs HTTPS baseUrl

Refresh:
  Record configuration does not auto-refresh.
  Restart/rotation procedure needed.

Observability:
  Demo endpoint must not be public in production.
  Never expose API key or full Environment.
~~~

Hợp đồng là tài liệu lâu dài, không phải bản dump values của một process. Cần cập nhật khi key, type, default, owner, nguồn hoặc security policy đổi.

## 32. Đổi tên key là thay đổi external API

Key như **demo.gateway.base-url** có thể được dùng trong YAML, CLI, ConfigMap, Helm, Terraform, CI variables và test fixtures.

Nếu đổi thành **demo.integration.gateway.endpoint**, Spring Boot relaxed binding không tự xem hai tên khác nghĩa này là alias.

Một migration plan nên có:

1. Old key và new key.
2. Khoảng thời gian hỗ trợ đồng thời.
3. Khi cả hai có mặt thì key nào được ưu tiên.
4. Runtime compatibility logic nếu cần.
5. Chuyển deployments theo thứ tự đã quyết định.
6. Test old-only, new-only, both và neither.
7. Warning deprecation không log secret.
8. Release loại bỏ key cũ có thông báo.

**Configuration metadata** và **@DeprecatedConfigurationProperty** có thể hỗ trợ tooling nhưng không tự tạo runtime alias.

## 33. Property đọc sớm cần nguồn sớm

Một số property như **logging.*** và **spring.main.*** được Spring Boot dùng khi khởi tạo ứng dụng, trước khi context refresh.

**@PropertySource** trên @Configuration class thường được xử lý khi refresh, quá muộn cho một số quyết định logging/SpringApplication.

Trong bài, logging level đặt trong **application.yml** và **application-prod.yml**, là Config Data phù hợp hơn cho nhóm property đọc sớm.

Tương tự, **spring.config.additional-location** cần được cấp đủ sớm để Boot biết tìm Config Data ở đâu, nên CLI/env là lựa chọn dễ hiểu.

## 34. Các lỗi thường gặp

### 34.1. Build hai JAR chỉ để đổi endpoint

Khác runtime values không cần khác binary. Sử dụng một artifact và external configuration.

### 34.2. Đặt secret thật trong application-prod.yml

Nó có thể vào Git, backup hoặc image. Dùng runtime secret source và validation.

### 34.3. Đặt spring.profiles.active trong application-prod.yml

File profile-specific không phải nơi phù hợp để kích hoạt chính profile đang chọn file. Dùng launcher hoặc non-profile-specific source.

### 34.4. Quên dấu / cuối directory location

Với directory location, dùng **file:./deploy/prod/** để Boot ghép tên file đúng.

### 34.5. Dùng spring.config.location thay additional-location

Có thể vô tình thay các default locations, mất common application.yml. Dùng additional-location khi chỉ muốn bổ sung.

### 34.6. Sai tên env

Dùng **DEMO_GATEWAY_APIKEY** theo canonical conversion. Không tự suy ra tên có thêm underscore cho kebab-case.

### 34.7. Thấy một property trong file nhưng runtime khác

Có thể bị nguồn ưu tiên cao hơn override. Kiểm tra Environment, profile, CLI, env và vị trí Config Data.

### 34.8. Parse Duration được nhưng validation fail

Một Duration như 1s vẫn đúng kiểu, nhưng có thể sai quan hệ request/connect. Phân biệt conversion và validation.

### 34.9. Gateway enabled mà không có key

Không tắt tính năng chỉ để che lỗi production; sửa Secret source.

### 34.10. Dùng file .env rồi mặc định Java tự đọc

Một file .env không tự động biến thành process environment nếu shell, IDE, Compose hoặc công cụ khác chưa xử lý nó.

### 34.11. Secret đã rotate nhưng bean vẫn giữ giá trị cũ

Standard configuration record không tự refresh. Dùng restart/reload có kiểm soát.

### 34.12. Log toString của record

Có thể lộ apiKey. Chỉ log các trường đã được phép.

### 34.13. Public endpoint dump config

Ngay cả metadata môi trường cũng có thể là dữ liệu nội bộ. Bảo vệ hoặc bỏ endpoint demo.

### 34.14. Coi base64 là encryption

Kubernetes Secret có thể dùng base64 encoding; cần RBAC, encryption at rest, audit và giới hạn workloads.

### 34.15. Chỉ so sánh SHA-256

Hash giống nhau chưa chứng minh config đúng; kết hợp smoke test và contract assertions.

## 35. Bài thực hành mở rộng A — thêm staging

Giữ JAR không đổi, tạo **deploy/staging/application-staging.yml**:

~~~yaml
server:
  port: 8083

demo:
  deployment:
    label: "staging"

  gateway:
    enabled: true
    base-url: "https://staging-gateway.example.invalid"
    request-timeout: 7s
~~~

Cấp secret giả runtime rồi chạy:

~~~bash
java -jar target/config-once-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=staging \
  --spring.config.additional-location=file:./deploy/staging/
~~~

Kiểm tra endpoint 8083, sau đó tính hash JAR. Nếu hash vẫn giống, bạn đã triển khai thêm môi trường mà không build variant mới.

## 36. Bài thực hành mở rộng B — precedence

1. Common file khai báo request-timeout 10s.
2. Dev file khai báo 12s.
3. Env cấp **DEMO_GATEWAY_REQUESTTIMEOUT=15s**.
4. CLI cấp **--demo.gateway.request-timeout=20s**.
5. Chạy rồi quan sát giá trị.
6. Bỏ CLI và chạy lại.
7. Bỏ env rồi chạy lại.

Không sửa hoặc rebuild JAR. Ghi lại giá trị ở từng lần để hiểu precedence.

## 37. Bài thực hành mở rộng C — Secret volume

1. Tạo một folder secrets local không được commit.
2. Tạo file **demo.gateway.api-key** chứa credential giả.
3. Giới hạn quyền đọc file.
4. Cấu hình **configtree:** từ folder đó.
5. Chạy prod với enabled=true.
6. Tạm bỏ file rồi chạy lại, xác nhận fail-fast.
7. Không in nội dung secret file trong log hoặc screenshot.

Bài này giúp phân biệt **tên property hợp đồng** với **nguồn cấp giá trị**.

## 38. Bài thực hành mở rộng D — image bất biến

1. Build JAR một lần.
2. Build Docker image một lần.
3. Mount dev config và chạy container dev.
4. Mount prod config/secret và chạy container prod.
5. Giữ cùng image digest.
6. Gọi HTTP endpoints và so sánh kết quả.
7. Không thay Dockerfile hoặc rebuild vì muốn đổi timeout.

Cách này mở rộng nguyên tắc build once sang container deployment.

## 39. Checklist hoàn thành

- [ ] Có một Maven project Java 21/Spring Boot 3.3.x.
- [ ] Tạo được một executable JAR.
- [ ] Ghi nhận SHA-256 ngay sau build.
- [ ] application.yml chỉ chứa common defaults không bí mật.
- [ ] Dev config ở ngoài JAR.
- [ ] Prod config ở ngoài JAR.
- [ ] Profile được chọn ở runtime.
- [ ] additional-location có đường dẫn hợp lệ và dấu / cuối cho directory.
- [ ] DeploymentProperties được đăng ký và bind.
- [ ] GatewayProperties được đăng ký và bind.
- [ ] URI, Duration và boolean chuyển kiểu đúng.
- [ ] Dev gateway disabled không cần secret.
- [ ] Prod gateway enabled yêu cầu secret.
- [ ] Prod thiếu secret bị fail-fast.
- [ ] Prod dùng HTTPS endpoint.
- [ ] Validation phát hiện timeout quan hệ sai.
- [ ] Dev chạy trên 8081 với label development.
- [ ] Prod chạy trên 8082 với label production.
- [ ] Connect timeout chung 2s ở cả hai.
- [ ] Request timeout dev/prod khác nhau.
- [ ] Không có API key thật trong Git/JAR/image.
- [ ] Endpoint demo không tiết lộ secret.
- [ ] Đã thực hiện smoke tests.
- [ ] Không rebuild giữa hai môi trường.
- [ ] SHA-256 cuối cùng giống SHA-256 ban đầu.
- [ ] Contract ghi key, type, unit, default, requiredness.
- [ ] Contract ghi env names và precedence.
- [ ] Contract ghi owner và secret policy.
- [ ] Contract có restart/rotation guidance.
- [ ] Có test cho missing/invalid/cross-field values.
- [ ] Có thể thêm staging mà không build lại.

## 40. Kết luận

Với Spring Boot Externalized Configuration, cùng một artifact có thể chạy ở nhiều môi trường nếu các lớp trách nhiệm được tách rõ:

1. **Một binary** được build, kiểm thử, phát hành và định danh bằng checksum/digest.
2. **Cấu hình chung** giữ những default không nhạy cảm.
3. **Cấu hình môi trường** đến từ profile-specific Config Data, env hoặc file ngoài JAR.
4. **Secret** đến từ nguồn runtime an toàn.
5. **@ConfigurationProperties** ánh xạ dữ liệu thành Java objects có kiểu.
6. **Validation** phát hiện cấu hình thiếu hoặc sai quan hệ.
7. **PropertySource precedence** giúp giải thích value hiệu lực.
8. **Smoke tests** chứng minh behavior khác nhau dù artifact giống.
9. **Configuration contract** giúp developer, vận hành và security có chung quy ước.
10. **Restart/rotation policy** giải quyết thay đổi secret sau startup.

Bài thực hành đạt mục tiêu khi dev và prod dùng đúng **cùng JAR**, nhận những giá trị riêng qua Environment, không chứa secret thật trong source và có hợp đồng cấu hình đầy đủ.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, PropertySource Order, Config Data và Configuration Trees: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Type-safe Configuration Properties và Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Framework — Environment: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Kubernetes — ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
