# Lỗi cấu hình bắt buộc, kiểm tra hợp lệ và dịch vụ bên ngoài khi khởi động Spring Boot

## 1. Phân biệt lỗi cấu hình với lỗi kết nối bên ngoài

Một JAR Spring Boot có thể được build thành công nhưng vẫn không khởi động được. Những nguyên nhân thường gặp gồm:

- **Không nạp được nguồn cấu hình:** thiếu file bắt buộc được chỉ định trong spring.config.import, YAML không hợp lệ hoặc Config Server không truy cập được.
- **Thiếu giá trị bắt buộc:** địa chỉ database, health URL, tên bucket hoặc cấu hình bảo mật không có trong Environment.
- **Giá trị không hợp lệ:** timeout âm, chuỗi rỗng, kiểu số không bind được, enum sai hoặc URL không đúng hợp đồng.
- **Dịch vụ bên ngoài mất khả dụng:** DNS, TCP, TLS, authentication hoặc HTTP check thất bại khi ứng dụng chủ động kết nối.
- **Chính sách startup chưa phù hợp:** ứng dụng vẫn báo ready khi dependency cốt lõi không hoạt động, hoặc làm cả hệ thống fail startup vì một service tùy chọn bị lỗi tạm thời.

Ba nhóm đầu thường là **lỗi cấu hình tĩnh**. Nhóm thứ tư là **tình trạng động của remote dependency**: backend có thể online lúc startup nhưng offline năm phút sau. Cần kiểm tra và khắc phục theo đúng lớp lỗi.

~~~text
java -jar app.jar
      |
      v
[1] Prepare Environment / Config Data
      |  import file bắt buộc không tồn tại
      |  cú pháp YAML sai
      +----> Startup failure sớm
      |
      v
[2] Build ApplicationContext, BeanDefinitions
      |
      v
[3] Bind & validate @ConfigurationProperties
      |  required property null/blank
      |  kiểu dữ liệu sai
      |  @Validated constraints bị vi phạm
      +----> Bean/binding/validation failure
      |
      v
[4] Context refresh hoàn tất
      |
      v
[5] ApplicationRunner / CommandLineRunner
      |  tùy chính sách: probe remote với timeout
      |  network/TLS/HTTP check thất bại
      +----> Runner failure -> run() thất bại
      |
      v
[6] ApplicationReadyEvent
      |
      v
[7] Runtime traffic / jobs
      |  remote có thể lỗi bất cứ lúc nào
      +----> Timeout, retry, circuit breaker, fallback
~~~

**Mục tiêu của bài:** biết cách định nghĩa cấu hình bắt buộc, bind và validate sớm, quyết định có nên kiểm tra remote khi startup, phân biệt lỗi startup với lỗi runtime và xây dựng kiểm thử có thể tái hiện.

Bài viết theo **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+**. Các ví dụ command-line sử dụng **Maven**, không yêu cầu một dịch vụ Internet thật.

## 2. Bảng phân loại lỗi và nơi cần kiểm tra

| Nhóm | Ví dụ | Giai đoạn thường gặp | Hướng giải quyết |
| --- | --- | --- | --- |
| Config Data | Thiếu file import bắt buộc | Chuẩn bị Environment | Kiểm tra location, mount, optional policy |
| Missing property | Thiếu demo.remote.health-url | Binding/bean creation | Đặt cấu hình đúng nguồn và profile |
| Type conversion | timeout-ms=abc cho long | Binder | Sửa kiểu và cách biểu diễn |
| Constraint validation | timeout-ms=50 vi phạm @Min(100) | Bean validation | Sửa giá trị hoặc constraint |
| Bean dependency | Constructor thiếu bean | Dependency injection | Kiểm tra component scan, @Bean, conditions |
| Remote unreachable | Connection refused, DNS lỗi | Startup probe hoặc runtime call | Timeout, bounded retry, policy critical/optional |
| TLS/auth failure | Certificate không tin cậy, HTTP 401/403 | Khi gọi remote | Certificate/credential/permission |
| Runtime outage | Remote đã online rồi lỗi sau ready | Runtime | Retry có giới hạn, circuit breaker, monitoring |

**Không chỉ nhìn dòng APPLICATION FAILED TO START để kết luận.** Hãy xem exception gốc, tên bean/property, thời điểm lỗi và trạng thái service bên ngoài.

Một lỗi fail khi parse Config Data **khác** lỗi sau khi ApplicationRunner bắt đầu. Nếu cần khắc phục nhanh, biết đúng mốc sẽ giúp bạn kiểm tra đúng nguyên nhân.

### 2.1. Ba câu hỏi chẩn đoán

1. **Nguồn cấu hình có tồn tại và được nạp không?** Kiểm tra spring.config.import, application properties, active profile, file mount.
2. **Giá trị đã bind và validate thành kiểu đúng chưa?** Kiểm tra @ConfigurationProperties, Jakarta constraints và default values.
3. **Ứng dụng có thật sự cần remote online trước khi chấp nhận traffic không?** Nếu có, kiểm tra fail-fast có deadline. Nếu không, chấp nhận degraded mode có quan sát và cơ chế runtime an toàn.

Đừng dùng một giải pháp cho cả ba: thêm placeholder default để che missing key hoặc retry network vô hạn trong constructor thường làm sự cố khó xử lý hơn.

## 3. Nguồn cấu hình, active profile và thứ tự ưu tiên

Spring Boot hỗ trợ nhiều nguồn configuration:

- application.properties và application.yaml trong JAR hoặc từ nguồn ngoài.
- Config Data được import bằng spring.config.import.
- OS environment variables và Kubernetes/Docker config mounts.
- Java system properties qua -D.
- Program arguments dạng --name=value.
- Configuration trees để đọc file-based secrets.
- Các integration như Spring Cloud Config khi đã thêm client và cấu hình tương ứng.

Một key có thể có ở nhiều nguồn. **Environment áp dụng thứ tự ưu tiên (precedence)**, nên chỉ thấy đúng key trong file chưa chứng minh đó là giá trị effective.

Ví dụ file:

~~~properties
demo.remote.timeout-ms=2000
~~~

nhưng lệnh chạy:

~~~bash
java -jar app.jar --demo.remote.timeout-ms=5000
~~~

Với Boot mặc định, command-line property source có thể override giá trị trong Config Data, nên timeout thực tế là **5000**. Nếu code đã dùng SpringApplication.setAddCommandLineProperties(false), quy tắc đưa CLI vào Environment thay đổi.

### 3.1. Thiếu key khác key có giá trị rỗng

~~~properties
demo.remote.health-url=
~~~

Ở đây key tồn tại nhưng giá trị rỗng. Nếu property được bind thành String:

- **@NotNull** không chấp nhận null, nhưng vẫn có thể chấp nhận chuỗi rỗng hoặc whitespace.
- **@NotBlank** không chấp nhận null, rỗng hay chuỗi chỉ có khoảng trắng.
- **@NotEmpty** không chấp nhận rỗng nhưng không cấm mọi chuỗi whitespace.

Vì vậy với địa chỉ URL bắt buộc, **@NotBlank** thường đúng hơn **@NotNull** đơn lẻ. Nhưng @NotBlank **chưa chứng minh chuỗi là một URI hợp lệ**; cần thêm kiểm tra syntax/semantics.

### 3.2. Config Data import bắt buộc

~~~properties
spring.config.import=file:./runtime/remote.properties
~~~

Nếu file bắt buộc không có, Spring Boot thường báo **ConfigDataLocationNotFoundException** khi nạp Config Data. Lỗi này có thể xuất hiện trước khi bean ứng dụng được tạo.

Nếu chính location đó thực sự optional:

~~~properties
spring.config.import=optional:file:./runtime/remote.properties
~~~

Tiền tố **optional:** bỏ yêu cầu location phải tồn tại. Nó **không** miễn trừ các property bắt buộc trong @ConfigurationProperties. Nếu ứng dụng vẫn cần một key từ file đã mất, validation sẽ còn phát hiện lỗi ở giai đoạn tạo bean.

**Không đặt optional chỉ để che lỗi mount secret/config** vốn là điều kiện deploy bắt buộc.

### 3.3. Profile và cấu hình môi trường

Nếu cấu hình ở:

~~~properties
# application-dev.properties
demo.remote.health-url=http://127.0.0.1:8765/health
~~~

thì một deployment chỉ bật profile **prod** không nhất thiết nhận được key đó. Phải kiểm tra **spring.profiles.active** và các nguồn bổ sung theo môi trường, không tự cho rằng mọi application-*.properties đều được nạp.

Một môi trường dev có thể chạy được vì có profile local, trong khi production fail vì thiếu ConfigMap/Secret tương ứng. Đây là một failure của **deployment configuration**, không phải lý do để bỏ ràng buộc bắt buộc.

### 3.4. Spring Cloud Config là integration riêng

Spring Cloud Config có thể dùng dạng:

~~~properties
spring.config.import=configserver:
~~~

nhưng **Spring Boot core không tự cung cấp Config Server integration** nếu dự án chưa có Spring Cloud Config Client tương thích. Spring Cloud có chính sách fail-fast và retry riêng; phân biệt lỗi **Config Server không truy cập được trong lúc chuẩn bị cấu hình** với lỗi **remote business API** ở runtime.

## 4. @Value và @ConfigurationProperties

### 4.1. @Value phù hợp với giá trị ít và đơn giản

Một bean có thể lấy property qua **@Value**. Nếu placeholder bắt buộc không resolve được, bean có thể không được tạo thành công.

Tuy nhiên:

- Các key dễ nằm rải rác khắp nhiều constructor.
- Validation nhóm nhiều trường khó tập trung.
- Một default rỗng che lỗi missing key.
- Nếu bean lazy, lỗi placeholder có thể bị dời đến lần đầu tạo bean.

Vì vậy với một nhóm cấu hình có hợp đồng rõ, **@ConfigurationProperties** thường là lựa chọn dễ kiểm thử và bảo trì hơn.

### 4.2. Record @ConfigurationProperties cho Java 17+

~~~java
@ConfigurationProperties(prefix = "demo.remote")
@Validated
public record RemoteSettings(
        @NotBlank String healthUrl,
        @Min(100) @Max(30_000) long timeoutMs,
        boolean verifyOnStartup) {
}
~~~

Đây là snippet, cần imports và cơ chế đăng ký bean cấu hình. Ý nghĩa:

- **healthUrl** là chuỗi bắt buộc, không blank.
- **timeoutMs** là số long trong khoảng 100 đến 30.000.
- **verifyOnStartup** quyết định có gửi network probe khi startup hay không.
- Boot 3.3 có thể constructor-bind record khi được đăng ký đúng bằng **@EnableConfigurationProperties** hoặc **@ConfigurationPropertiesScan**.

Đừng nhầm **@ConfigurationProperties** là một lệnh tự gọi remote: binder chỉ nhận và chuyển giá trị từ Environment thành đối tượng Java.

### 4.3. Jakarta Validation là thành phần cần có

Spring Boot 3 dùng namespace **jakarta.validation**, không dùng namespace **javax.validation** cũ của nhiều ví dụ Boot 2.

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

**@Validated** làm Boot cố validate bean configuration properties. Cần một Jakarta Bean Validation provider trên classpath; starter validation cung cấp một implementation thích hợp.

### 4.4. Constraint đúng loại dữ liệu

| Constraint | Công dụng | Dễ nhầm |
| --- | --- | --- |
| **@NotNull** | Không chấp nhận null | String rỗng vẫn có thể lọt |
| **@NotBlank** | String có nội dung khác khoảng trắng | Không tự validate URL syntax |
| **@NotEmpty** | String/collection/map/array không rỗng | Chuỗi chỉ có space có thể lọt |
| **@Min/@Max** | Số nằm trong khoảng | Không thay thế type conversion |
| **@Positive** | Số phải lớn hơn 0 | Giá trị 0 không hợp lệ |
| **@Pattern** | Regex cho String | Không thay cho URI parser đầy đủ |
| **@Valid** | Cascade validate nested object | Cần sử dụng đúng ở nested properties |
| **Custom Validator** | Quy tắc ngữ nghĩa riêng | Không nên làm network I/O trong validator thuần |

Ví dụ nested object:

~~~java
@ConfigurationProperties("demo")
@Validated
record DemoProperties(@Valid Security security) {
    record Security(@NotBlank String audience) {
    }
}
~~~

Đây là snippet cần imports **@Valid**, **@NotBlank**, **@Validated** và cơ chế đăng ký bean. Với nested groups, có thể cần tạo object nested mặc định hoặc @Valid phù hợp để validation được kích hoạt ngay cả khi không có properties trong nhóm, theo hợp đồng của loại class.

**Đừng chỉ nhìn có @NotBlank trong nested class mà tin chắc nó đã được cascade validate**; hãy có test missing nested config.

### 4.5. Type conversion khác validation

~~~properties
demo.remote.timeout-ms=abc
~~~

là lỗi binder không chuyển được String thành long.

~~~properties
demo.remote.timeout-ms=50
~~~

bind thành long được, nhưng vi phạm **@Min(100)**.

Nếu một property wrapper **Long** có thể null, dùng thêm **@NotNull** khi bắt buộc có mặt. Một constraint như @Min không nhất thiết tự phát hiện null.

### 4.6. Cẩn trọng với lazy initialization

Bean có @Lazy hoặc khi bật:

~~~properties
spring.main.lazy-initialization=true
~~~

có thể được tạo muộn. Validation gắn với binding/initialization của bean ấy cũng có thể bị trì hoãn nếu không ai yêu cầu bean trước ready.

Với cấu hình cốt lõi, có thể dùng một eager bean, **@Lazy(false)** hoặc startup validator nhỏ để bảo đảm lỗi được phát hiện trước readiness. Không nên biến người dùng đầu tiên gọi endpoint thành người phát hiện một lỗi cấu hình bắt buộc.

**Lazy không trì hoãn mọi lỗi:** parse Config Data, BeanDefinition registration và nhiều infrastructure component vẫn hoạt động ở startup.

## 5. External dependency: cấu hình hợp lệ không đồng nghĩa reachable

Một chuỗi:

~~~properties
demo.remote.health-url=https://service.example.internal/health
demo.remote.timeout-ms=2000
~~~

có thể được bind/validate thành công trong khi dịch vụ vẫn:

- Không phân giải được DNS.
- Không mở TCP port.
- Bị firewall/service mesh chặn.
- TLS certificate sai hoặc hết hạn.
- Từ chối credential với 401/403.
- Trả HTTP 503 vì chưa ready.
- Trả HTTP 200 cho health cơ bản nhưng không đáp ứng một operation nghiệp vụ.
- Hoạt động lúc startup và ngừng hoạt động ít phút sau.

**Cấu hình tĩnh** và **trạng thái mạng động** cần hai cơ chế kiểm tra riêng. Không đưa một HTTP GET vào Jakarta Validator hoặc getter của record chỉ vì muốn “tự động validate”.

### 5.1. Mức kiểm tra bên ngoài

| Loại probe | Cho biết | Không cho biết |
| --- | --- | --- |
| DNS lookup | Có thể phân giải hostname | Remote API đã sẵn sàng |
| TCP connect | Port có thể tiếp nhận kết nối | Auth/API business hoạt động |
| TLS handshake | Kết nối TLS được thiết lập/tin cậy | Response HTTP thành công |
| HTTP GET health | Endpoint trả status đã định nghĩa | Toàn bộ nghiệp vụ hoàn hảo |
| Authenticated read | Credential được phép đọc | Có quyền với mọi operation |
| Business transaction | Một operation cụ thể chạy được | Tính an toàn nếu probe gây side effects |

**Health probe không nên tạo side effects** như charge tiền, tạo order hoặc thực thi transaction ghi dữ liệu thật. Chọn GET/HEAD hoặc operation chỉ đọc có semantics được remote provider công nhận.

### 5.2. Khi nào fail-fast là hợp lý?

Fail-fast nếu thiếu remote nghĩa là **ứng dụng hoàn toàn không thể phục vụ chức năng cốt lõi** và việc nhận traffic sẽ gây nhiều lỗi hơn. Startup check có timeout hữu hạn giúp rollout phát hiện instance không đạt điều kiện.

Không nhất thiết fail-fast nếu remote chỉ là một **feature tùy chọn** hoặc sự cố là transient mà ứng dụng vẫn phục vụ được nhiều endpoint khác. Khi ấy degraded startup + runtime resilience có thể hợp lý hơn.

**Hệ quả cần cân nhắc:** hàng chục replicas cùng khởi động và cùng probe một backend đang quá tải có thể làm outage nghiêm trọng hơn. Không có một lựa chọn fail-fast/degraded đúng cho mọi sản phẩm.

## 6. Nên thực hiện check ở lifecycle nào?

### 6.1. Constructor và @PostConstruct

Code khởi tạo bean là chỗ phù hợp để validate **giá trị tĩnh**, nhưng network trong constructor hoặc @PostConstruct dễ tạo các vấn đề:

- Bean creation chậm và khó phân biệt lỗi remote với lỗi DI.
- Network timeout kéo dài toàn bộ context refresh.
- Bean lazy có thể dời việc kết nối đến request đầu tiên.
- Callback khó retry có kiểm soát hoặc đo riêng.
- Một external outage có thể khiến tất cả bean creation thất bại.

Nếu cần network check sớm, nên tách thành component có trách nhiệm rõ.

### 6.2. ApplicationRunner/CommandLineRunner

Spring Boot chạy các runner sau context refresh, nhưng trước **ApplicationReadyEvent**. Runner có thể gọi health endpoint, yêu cầu HTTP 2xx và ném exception nếu dependency critical không sẵn sàng.

Ưu điểm:

- Cấu hình đã được bind và inject.
- Có thể tách một RemoteHealthProbe độc lập.
- Có timeout/retry deadline rõ.
- Exception không bị nuốt làm **SpringApplication.run(...)** thất bại.
- Không phát ApplicationReadyEvent theo đường startup thành công khi runner fail.

**Giới hạn:** đối với web app, embedded server có thể đã mở cổng trong refresh trước khi runner chạy. Do đó cần readiness/load balancer để tránh đưa traffic quá sớm; runner không phải firewall.

### 6.3. Readiness và liveness

**Liveness** nên phản ánh tiến trình còn hoạt động, không bị kẹt. Không nên buộc liveness phụ thuộc mọi external backend; shared outage có thể làm tất cả pods bị restart vô ích.

**Readiness** là khả năng nhận traffic hiện tại. Có thể phụ thuộc một critical backend nếu toàn bộ workload không hoạt động được khi thiếu nó. Với tính năng tùy chọn, không nên đưa nó vào readiness của toàn service mà không xem tác động.

Health checks nên có:

- Timeout và giới hạn chi phí.
- Tần suất phù hợp, có thể cache trạng thái.
- Phân biệt critical và optional.
- Tín hiệu monitoring rõ khi service degraded.
- Chính sách tránh đồng loạt unready nếu chỉ một feature phụ bị lỗi.

### 6.4. Runtime vẫn phải xử lý lỗi

Remote có thể lỗi **sau** startup. Vì vậy runtime còn cần connection/request timeout, bounded retry, exponential backoff, jitter, circuit breaker/bulkhead, idempotency và fallback khi nghiệp vụ cho phép.

Một startup-only probe thành công **không bao giờ là bảo đảm remote sẽ sống mãi**.

## 7. Demo Java 17+ chạy được: validation trước, remote check sau

Ví dụ xây dựng một Spring Boot CLI nhỏ để quan sát bốn tình huống:

1. Thiếu health-url → binding/validation failure.
2. timeout-ms=50 → @Min validation failure.
3. Cấu hình hợp lệ và verify-on-startup=false → startup thành công dù remote không online.
4. verify-on-startup=true → HTTP check; 2xx thành công, network error hoặc non-2xx làm runner fail.

Ứng dụng **WebApplicationType.NONE** để quan sát startup mà không cần mở embedded HTTP server. Đối với web service, nguyên tắc validation/probe tương tự nhưng còn có readiness/routing.

### 7.1. Cấu trúc dự án

~~~text
startup-config-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/startup/StartupFailureDemo.java
  src/test/java/com/example/startup/RemoteSettingsTest.java
  LocalHealthServer.java
~~~

**LocalHealthServer.java** là chương trình Java độc lập ở root, không đặt trong src/main/java của Maven app để không tạo một main thứ hai trong executable JAR.

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>startup-config-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

Starter validation cần thiết để các Jakarta constraints chạy thực sự. Starter test dùng cho JUnit 5 và AssertJ.

### 7.3. application.properties

~~~properties
demo.remote.timeout-ms=2000
demo.remote.verify-on-startup=false

# Không đặt demo.remote.health-url.
# Mỗi scenario sẽ truyền qua command line.
~~~

Không đặt health-url là có chủ đích để thử fail-fast khi không truyền tham số bắt buộc.

### 7.4. Java application hoàn chỉnh

**src/main/java/com/example/startup/StartupFailureDemo.java**:

~~~java
package com.example.startup;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication(proxyBeanMethods = false)
@EnableConfigurationProperties(StartupFailureDemo.RemoteSettings.class)
public class StartupFailureDemo {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupFailureDemo.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.run(args);
    }

    @Bean
    RemoteHealthProbe remoteHealthProbe() {
        return new RemoteHealthProbe();
    }

    @Bean
    ApplicationRunner startupProbe(
            RemoteSettings settings,
            RemoteHealthProbe probe) {

        return args -> {
            System.out.println("RUNNER | configuration valid");

            if (!settings.verifyOnStartup()) {
                System.out.println("RUNNER | remote probe skipped");
                return;
            }

            int status = probe.getHttpStatus(settings);

            if (status < 200 || status >= 300) {
                throw new IllegalStateException(
                        "Remote health returned HTTP " + status);
            }

            System.out.println(
                    "RUNNER | remote healthy, HTTP " + status);
        };
    }

    @Validated
    @ConfigurationProperties(prefix = "demo.remote")
    public record RemoteSettings(
            @NotBlank String healthUrl,
            @Min(100) @Max(30_000) long timeoutMs,
            boolean verifyOnStartup) {
    }

    static final class RemoteHealthProbe {

        int getHttpStatus(RemoteSettings settings)
                throws Exception {

            URI uri = URI.create(settings.healthUrl());
            String scheme = uri.getScheme();

            boolean supported =
                    "http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme);

            if (!supported || uri.getHost() == null) {
                throw new IllegalArgumentException(
                        "demo.remote.health-url must be an absolute HTTP URL");
            }

            Duration timeout =
                    Duration.ofMillis(settings.timeoutMs());

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(timeout)
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(timeout)
                    .GET()
                    .build();

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding());

                return response.statusCode();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }
        }
    }
}
~~~

**Những điểm cần hiểu:**

- **@EnableConfigurationProperties** đăng ký RemoteSettings. Runner nhận RemoteSettings nên bean được bind và validate trước khi runner chạy trong ví dụ.
- **@Validated/@NotBlank/@Min/@Max** chỉ validate giá trị cấu hình, không gửi HTTP.
- **RemoteHealthProbe** tạo HttpClient và gửi request **chỉ khi được gọi từ runner**.
- Khi verifyOnStartup=false, runner không gửi mạng nhưng vẫn bắt buộc healthUrl hợp lệ ở mức **không blank**.
- Khi bật check, URI phải có scheme **http/https** và host. Đây là kiểm tra syntax sơ bộ trong probe; nếu cần áp đặt URI syntax bất kể check có bật hay không, chuyển nó vào validator tĩnh độc lập.
- **connectTimeout** và **request.timeout** giới hạn lần thử network, tránh để startup chờ vô hạn.
- HTTP 2xx là định nghĩa **health success của demo**. Một remote API thực có thể cần contract khác; không tự coi mọi HTTP 3xx hoặc một body bất kỳ là healthy.
- Nếu HTTP request lỗi, exception truyền qua ApplicationRunner và lần SpringApplication.run thất bại.
- Khi thread bị interrupt, code khôi phục interrupt flag trước khi ném exception.
- Non-web mode giúp runner kiểm thử rõ. Với web app, server có thể đã mở cổng trước runner nên cần readiness gate.

### 7.5. LocalHealthServer.java: stub HTTP độc lập bằng JDK

Để kiểm tra HTTP 200 và HTTP 503 mà không phụ thuộc mạng Internet, tạo **LocalHealthServer.java** ở root:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;

public class LocalHealthServer {

    public static void main(String[] args) throws Exception {
        int status = args.length == 0
                ? 200
                : Integer.parseInt(args[0]);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8765),
                0);

        server.createContext("/health", exchange -> {
            byte[] body =
                    "local-health".getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, body.length);

            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println("STUB | HTTP " + status + " on port 8765");

        new CountDownLatch(1).await();
    }
}
~~~

Server này dùng module **jdk.httpserver** đi kèm JDK 17+. Chạy Java source-file mode:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java
~~~

Expected stdout từ stub:

~~~text
STUB | HTTP 200 on port 8765
~~~

Hoặc khởi động lại với:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java 503
~~~

Expected stdout:

~~~text
STUB | HTTP 503 on port 8765
~~~

Stub cần port 8765 còn trống; nếu bị chiếm, đổi port trong mã và URL cấu hình cho khớp. Process stub sẽ chờ cho tới khi bạn dừng, chỉ dùng cho thực hành.

### 7.6. Build demo

~~~bash
java -version
mvn -q -DskipTests package
~~~

Yêu cầu Java 17+ và Maven 3.9+. JAR sau build:

~~~text
target/startup-config-demo-1.0.0.jar
~~~

### 7.7. Case A: thiếu health-url bắt buộc

~~~bash
java -jar target/startup-config-demo-1.0.0.jar
~~~

**Kỳ vọng:** Spring Boot fail lúc bind/validate RemoteSettings do @NotBlank trên healthUrl. Chương trình **không in**:

~~~text
RUNNER | configuration valid
~~~

vì runner chưa thực thi. Boot có thể hiển thị failure analysis hoặc exception chain; không nên gán một stack trace nguyên văn cho mọi lần chạy.

### 7.8. Case B: cấu hình hợp lệ, tắt probe

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health
~~~

Các dòng **do code demo tự in**:

~~~text
RUNNER | configuration valid
RUNNER | remote probe skipped
~~~

**Không cần stub đang chạy** vì verify-on-startup mặc định false. Cấu hình tĩnh hợp lệ, nhưng không có kết luận nào về khả năng kết nối remote.

### 7.9. Case C: timeout sai

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.timeout-ms=50
~~~

**Kỳ vọng:** validation thất bại bởi @Min(100) trước runner. Nếu đổi 50 thành **abc**, lỗi là **binding/type conversion** của long, khác @Min failure.

### 7.10. Case D: remote offline, bắt buộc probe

Đảm bảo không có service nghe tại port 8765, rồi chạy:

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.verify-on-startup=true
~~~

App in:

~~~text
RUNNER | configuration valid
~~~

Sau đó network connect lỗi nếu không có service trên port này; **SpringApplication.run** thất bại từ ApplicationRunner, không in dòng remote healthy.

### 7.11. Case E: remote HTTP 200

Terminal A:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java
~~~

Terminal B:

~~~bash
java -jar target/startup-config-demo-1.0.0.jar \
  --demo.remote.health-url=http://127.0.0.1:8765/health \
  --demo.remote.verify-on-startup=true
~~~

Các dòng code demo tự in:

~~~text
RUNNER | configuration valid
RUNNER | remote healthy, HTTP 200
~~~

Startup probe thành công, nhưng remote vẫn có thể lỗi trong tương lai; không biến một lần GET thành bảo đảm availability trọn đời.

### 7.12. Case F: remote HTTP 503

Dừng stub cũ, chạy:

~~~bash
java --add-modules jdk.httpserver LocalHealthServer.java 503
~~~

Chạy lại lệnh app verify-on-startup=true. Runner in dòng cấu hình hợp lệ, sau đó **ném IllegalStateException** với message:

~~~text
Remote health returned HTTP 503
~~~

Boot coi lần khởi động thất bại. Không khẳng định chính xác toàn bộ stack trace hoặc log order.

## 8. Unit test cấu hình bằng ApplicationContextRunner

**ApplicationContextRunner** giúp tạo một Spring context nhỏ để kiểm tra binding/validation, không cần web server hay remote network.

Tạo **src/test/java/com/example/startup/RemoteSettingsTest.java**:

~~~java
package com.example.startup;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RemoteSettingsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesOnly.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(
            StartupFailureDemo.RemoteSettings.class)
    static class PropertiesOnly {
    }

    @Test
    void missingRequiredUrlFailsValidation() {
        runner.withPropertyValues(
                "demo.remote.timeout-ms=2000")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void outOfRangeTimeoutFailsValidation() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=50")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void invalidNumberFailsBinding() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=abc")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void validConfigurationBindsWithoutNetwork() {
        runner.withPropertyValues(
                "demo.remote.health-url=http://127.0.0.1:8765/health",
                "demo.remote.timeout-ms=2000",
                "demo.remote.verify-on-startup=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    var settings = context.getBean(
                            StartupFailureDemo.RemoteSettings.class);

                    assertThat(settings.healthUrl()).isEqualTo(
                            "http://127.0.0.1:8765/health");
                    assertThat(settings.timeoutMs()).isEqualTo(2000);
                    assertThat(settings.verifyOnStartup()).isFalse();
                });
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test này chứng minh:

- Missing required key gây lỗi validation.
- Timeout sai phạm vi gây lỗi constraint.
- Chuỗi không chuyển được sang long gây binding failure.
- Properties hợp lệ bind được mà không cần remote online.

**Giới hạn kiểm thử:** ApplicationContextRunner ở trên chỉ đăng ký RemoteSettings, không đăng ký runner hoặc RemoteHealthProbe. Vì vậy **chưa kiểm thử startup check HTTP**. Để kiểm thử probe, dùng local HTTP stub trên cổng ngẫu nhiên hoặc fake client; để kiểm thử cả lifecycle, chạy SpringApplication thực bằng integration test.

### 8.1. Tại sao không nên phụ thuộc Internet trong unit test?

Một API công cộng có thể đổi behavior, bị rate limit hoặc mất kết nối, khiến CI đỏ dù mã ứng dụng đúng. Test binding/validation nên tách khỏi network; test remote dùng stub có kiểm soát và timeout.

## 9. Khi ApplicationRunner thất bại, chuyện gì xảy ra?

Trong trình tự SpringApplication thông thường:

~~~text
Context refresh success
        |
ApplicationStartedEvent
        |
ApplicationRunner / CommandLineRunner
        |-- FAIL --> startup failure
        |            ApplicationFailedEvent
        |            context cleanup
        |
        +-- PASS --> ApplicationReadyEvent
                       readiness chuyển sang accepting
                       theo lifecycle thông thường
~~~

**Runner exception không xử lý** khiến **SpringApplication.run(...) thất bại**, dù context đã refresh trước đó.

**Điểm tinh tế:** ở ứng dụng web, embedded server có thể đã mở socket trước runner. Không coi runner check là cách tuyệt đối chặn request khi startup; readiness và load balancer phải giúp định tuyến chỉ tới instance sẵn sàng.

### 9.1. Không được nuốt lỗi của critical dependency

Đoạn sau là anti-pattern nếu remote thật sự bắt buộc:

~~~java
try {
    remoteProbe.verify();
} catch (Exception ignored) {
    // Startup tiếp tục và có thể báo ready giả.
}
~~~

Đây là snippet minh họa, không phải chương trình chạy độc lập. Nếu dependency critical không hoạt động, server vẫn nhận traffic và trả lỗi nghiệp vụ. Với dependency optional, startup degraded có thể đúng, nhưng **cần log/metrics/status rõ và xử lý runtime**; không dùng catch-all im lặng.

### 9.2. Retry startup phải có giới hạn

Không làm:

~~~java
while (true) {
    tryConnect();
}
~~~

Đây là snippet anti-pattern. Infinite retry có thể làm startup kẹt mãi, ngăn ApplicationReadyEvent và tạo rollout không hoàn tất.

Thay vào đó:

- Mỗi lần probe có connect/request timeout.
- Tổng thời gian thử lại có deadline.
- Backoff có giới hạn và jitter khi cần.
- Phân biệt retryable 5xx/network và lỗi cấu hình/401/403 có thể không retry.
- Sau deadline, quyết định fail startup hoặc degraded dựa trên contract.
- Tôn trọng interrupt signal và quy trình shutdown.

## 10. Readiness và liveness không nên bị đánh đồng

| Cơ chế | Trả lời câu hỏi | Gợi ý |
| --- | --- | --- |
| **Liveness** | Process có còn hoạt động đúng ở mức tiến trình? | Không gắn bừa với remote outage |
| **Readiness** | Instance có thể nhận workload hiện tại? | Có thể xét critical dependency |
| **Startup validation** | Config tĩnh có đúng không? | Fail-fast cho missing/invalid |
| **Startup remote probe** | Remote có đáp ứng lúc khởi động? | Chọn rõ critical vs optional |
| **Runtime resilience** | Remote hỏng sau ready thì sao? | Timeout/retry/circuit breaker/fallback |

Một shared backend lỗi không nhất thiết nên khiến mọi pod API bị restart. Nếu liveness phụ thuộc backend đó, toàn cụm có thể vào restart storm.

Ngược lại, nếu toàn bộ API không thể thực thi chức năng chính khi remote lỗi, readiness cần phản ánh tình trạng đó theo cách có kiểm soát.

### 10.1. Chi phí của một readiness probe

Nếu mỗi pod probe remote mỗi vài giây và hệ thống có hàng trăm pods, việc kiểm tra có thể tự tạo tải lớn lên backend. Cần cân nhắc:

- Cache/interval và thời gian có hiệu lực của kết quả.
- Giới hạn concurrent probes.
- Sử dụng state từ background monitor thay vì network call trên mọi probe HTTP.
- Phân biệt remote optional với critical.
- Tránh cả cụm đồng loạt unready khi lỗi chỉ ảnh hưởng một tuyến phụ.

## 11. Cấu hình trong container và secrets

### 11.1. Environment variables và relaxed binding

Spring Boot có cơ chế relaxed binding. Đối với canonical property names, quy tắc environment variable thường **đổi dấu chấm thành underscore, bỏ dấu gạch nối và uppercase**.

Ví dụ **demo.remote.timeout-ms** tương ứng dạng environment variable như **DEMO_REMOTE_TIMEOUTMS**. Đừng tự suy diễn mọi biến thể thêm underscore đều có cùng nghĩa; kiểm tra tài liệu Boot và effective values.

### 11.2. Config trees

Nếu hệ thống mount secrets thành file:

~~~text
/etc/secrets/
    remote.username
    remote.password
~~~

có thể dùng:

~~~properties
spring.config.import=configtree:/etc/secrets/
~~~

Nếu directory bắt buộc, đừng đặt optional:. Nếu một secret không được mount, fail-fast là tín hiệu deploy cần được sửa.

**Không in Environment đầy đủ hoặc password/token vào logs** để phân tích lỗi. Chỉ log tên key, loại constraint, bean name và một thông báo không chứa bí mật.

### 11.3. Actuator /env và /configprops

Những endpoint này có thể hỗ trợ quan sát properties, nhưng có nguy cơ lộ thông tin nhạy cảm nếu mở công khai. Cần authentication/authorization, masking và hạn chế exposed endpoints. Không công khai endpoint quản lý chỉ để debug startup.

## 12. @Lazy có thể dời lỗi cấu hình sang first use

Ví dụ:

~~~java
@Bean
@Lazy
RemoteClient remoteClient(Environment environment) {
    String url = environment.getRequiredProperty(
            "demo.remote.health-url");
    return new RemoteClient(url);
}
~~~

Đây là snippet cần imports và class RemoteClient. Nếu bean chưa được yêu cầu, việc chạy factory method có thể bị trì hoãn. Lỗi property có thể xuất hiện khi **getBean(...)** lần đầu, không phải khi context refresh.

Bật:

~~~properties
spring.main.lazy-initialization=true
~~~

cũng có thể trì hoãn tạo nhiều bean. Với cấu hình critical nên cân nhắc:

- Bean validator eager hoặc **@Lazy(false)** cho thành phần quan trọng.
- ApplicationRunner kiểm tra tĩnh trước ready.
- Test xác minh missing/invalid key làm startup fail.
- Không đưa mọi network check vào constructor chỉ để fail-fast.

**Không phải mọi lỗi đều lazy:** Config Data, bean registry và infrastructure vẫn có thể fail ở startup.

## 13. Đọc exception chain và FailureAnalyzer

Lỗi configuration properties có thể biểu hiện qua:

~~~text
ConfigurationPropertiesBindException
    |
    +-- BindException / BindValidationException
            |
            +-- healthUrl must not be blank
            +-- timeoutMs must be >= 100
~~~

Lỗi remote probe có thể biểu hiện:

~~~text
ApplicationRunner invocation
    |
    +-- ConnectException / HttpTimeoutException
         hoặc IllegalStateException: HTTP 503
    |
    +-- SpringApplication startup failure
~~~

Đây là **sơ đồ điển hình**, không phải stack trace chính xác của mọi lần chạy. Exception wrappers thay đổi theo implementation/phiên bản.

Để debug có hệ thống:

1. Xác định mốc lỗi: Config Data, bean creation, runner hay runtime.
2. Đọc root cause và tên property/bean.
3. Với binding: kiểm tra expected type, source, active profile và rejected value đã được che secrets.
4. Với remote: phân biệt DNS, TCP, TLS, HTTP auth, status, timeout.
5. So sánh cấu hình effective giữa dev và deploy.
6. Nếu có **FailureAnalyzer** của Boot, đọc phần Description/Action.
7. Khi cần, dùng debug/conditions report trong môi trường chẩn đoán có kiểm soát.

**Không khắc phục bằng cách tắt mọi validation hoặc ghi password ra log.**

## 14. Lỗi thiết kế thường gặp

### 14.1. Dùng @NotNull cho String bắt buộc

String rỗng vẫn có thể qua @NotNull. Dùng @NotBlank nếu không được để trắng.

### 14.2. Quên validation starter

@Validated và Jakarta constraints cần provider. Thêm spring-boot-starter-validation và test lỗi thực.

### 14.3. Nhầm javax với jakarta ở Boot 3

Boot 3 dùng jakarta.validation. Kiểm tra imports và dependencies.

### 14.4. Che missing key bằng default rỗng

Nếu một endpoint bắt buộc, default rỗng chỉ dời lỗi sang runtime.

### 14.5. Gọi network trong constructor hoặc getter

Tạo bean chậm và khó phân loại; dùng component probe riêng có timeout.

### 14.6. Tưởng URL hợp lệ đồng nghĩa remote online

URL là dữ liệu tĩnh; network là trạng thái động. Phải kiểm tra riêng.

### 14.7. Gọi POST có side effect làm health check

Có thể tạo giao dịch thật, đặc biệt khi retry. Chọn read-only health endpoint.

### 14.8. Infinite retry trong runner

Startup có thể treo vĩnh viễn. Retry có deadline và failure policy rõ.

### 14.9. Nuốt lỗi critical dependency nhưng vẫn báo ready

Làm traffic thật trở thành công cụ phát hiện lỗi. Dùng fail-fast hoặc readiness gate.

### 14.10. Fail mọi instance vì một remote optional

Làm giảm availability của các feature không liên quan. Thiết kế degraded mode đúng phạm vi.

### 14.11. Đặt remote health vào liveness

Có thể tạo restart storm khi backend outage. Liveness chỉ nên phản ánh sức khỏe process.

### 14.12. Tin startup probe thành công là đủ

Remote có thể lỗi sau đó. Runtime cần resilience và observability.

### 14.13. Không test profile/secret mounting

Dev có property, production thiếu file hoặc secret. Cần test deploy/config contract.

### 14.14. Lazy critical bean chỉ fail ở request đầu

Giữ validation tĩnh trước ready cho critical path.

### 14.15. Log toàn bộ Environment và secrets

Lộ credential qua logs và monitoring. Che giá trị, chỉ log thông tin chẩn đoán an toàn.

## 15. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Missing health-url | Binding/validation fail trước runner |
| health-url rỗng hoặc whitespace | @NotBlank fail |
| timeout-ms=abc | Type conversion/binding fail |
| timeout-ms=50 | @Min fail |
| Valid config, probe false | App startup được, không cần backend |
| Probe true, port không lắng nghe | Runner fail với network cause |
| Probe true, stub HTTP 200 | Runner thành công |
| Probe true, stub HTTP 503 | Runner fail với HTTP status |
| Invalid URI scheme, probe true | Probe preflight fail rõ |
| Sai active profile | Missing config được phát hiện |
| Required import location bị thiếu | Config Data failure |
| Optional import location bị thiếu | Không fail chỉ vì location thiếu |
| Remote outage sau ready | Runtime timeout/retry/degraded |
| Global lazy bật | Critical validation vẫn được bảo đảm trước ready bằng test |
| Nhiều replicas khởi động | Không tạo retry/probe storm |

Không bắt buộc mọi hệ thống đều hard fail khi remote offline. Ma trận cần phản ánh chính sách critical/optional thật.

## 16. Checklist trước khi deploy

- [ ] Phân loại lỗi Config Data, binding, validation và remote availability.
- [ ] Document rõ property bắt buộc và nguồn cung cấp.
- [ ] Đúng namespace jakarta.validation và có starter validation.
- [ ] Bean @ConfigurationProperties được đăng ký đúng.
- [ ] Constraint đúng kiểu: @NotBlank, @NotNull, @Min, @Valid.
- [ ] Test missing, blank, wrong type, out-of-range values.
- [ ] Kiểm tra active profile, CLI overrides và environment variables.
- [ ] Không dùng optional: cho config/secret bắt buộc.
- [ ] Không log secrets hoặc công khai /env, /configprops.
- [ ] Tách static config validation khỏi HTTP/TCP I/O.
- [ ] Remote critical hay optional đã được xác định rõ.
- [ ] Startup probe có connect/request timeout và bounded retry.
- [ ] Runner fail không bị nuốt cho critical dependency.
- [ ] Readiness phản ánh workload, liveness không gắn bừa remote.
- [ ] Có runtime retry/circuit breaker/fallback khi cần.
- [ ] Có integration test cho HTTP 200/503/unreachable.
- [ ] Không dựa vào một public Internet API trong unit tests.
- [ ] Nếu bật lazy, critical config vẫn được validate trước ready.
- [ ] Có metric/log theo phase, bean/property key và root cause.
- [ ] Không gọi health check gây side effects nghiệp vụ.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Missing Config Data import khác missing @NotBlank property như thế nào?

**Đáp án:** Missing import có thể fail khi chuẩn bị Environment; @NotBlank được kiểm tra khi configuration properties bean bind/validate.

**Câu 2.** Vì sao @NotNull không đủ với URL String?

**Đáp án:** Không ngăn chuỗi rỗng/whitespace. Cần @NotBlank và kiểm tra syntax khi cần.

**Câu 3.** Spring Boot 3 dùng javax.validation hay jakarta.validation?

**Đáp án:** jakarta.validation.

**Câu 4.** timeout-ms=abc và timeout-ms=50 với @Min(100) cùng loại lỗi?

**Đáp án:** Không. abc không chuyển được thành số; 50 bind được nhưng vi phạm constraint.

**Câu 5.** @ConfigurationProperties tự kết nối tới service bên ngoài?

**Đáp án:** Không, nó bind/validate dữ liệu; network check là logic riêng.

**Câu 6.** ApplicationRunner ném exception thì mốc ready có được phát thành công?

**Đáp án:** Không theo startup thông thường; run thất bại và đi qua xử lý startup failure.

**Câu 7.** Runner fail có chắc web server chưa mở cổng?

**Đáp án:** Không. Context có thể đã refresh và server đã mở socket; readiness/routing còn quan trọng.

**Câu 8.** Startup check HTTP 200 có bảo đảm remote hoạt động mãi không?

**Đáp án:** Không. Remote có thể lỗi ngay sau đó; runtime cần resilience.

**Câu 9.** Tại sao không đưa mọi remote dependency vào liveness?

**Đáp án:** Shared outage có thể làm toàn cụm restart không cần thiết.

**Câu 10.** Vì sao health check không nên thực hiện POST tạo giao dịch?

**Đáp án:** Có thể thay đổi dữ liệu và gây duplicate side effects khi retry.

**Câu 11.** Global lazy có ảnh hưởng đến lúc validate bean không?

**Đáp án:** Có thể, nếu bean bị tạo muộn. Critical config cần validator eager hoặc bước startup có chủ đích.

**Câu 12.** Remote optional đang offline thì lựa chọn hợp lý nào?

**Đáp án:** Degraded startup có quan sát và runtime timeout/retry/fallback, nếu nghiệp vụ vẫn hoạt động được mà không có remote.

## 18. Tổng kết

Để xử lý lỗi khởi động chính xác, chia ba lớp:

1. **Nguồn cấu hình:** file, profile, environment variable, import có tồn tại và được nạp đúng không?
2. **Binding và validation:** dữ liệu có đúng kiểu, không thiếu và thỏa các ràng buộc bắt buộc không?
3. **Remote dependency:** có cần kiểm tra trạng thái bên ngoài trước khi nhận traffic không, và kiểm tra bằng cách nào có timeout, không side effect?

**@ConfigurationProperties + @Validated + Jakarta Validation** phù hợp để fail-fast với lỗi cấu hình tĩnh. **ApplicationRunner** có thể thực hiện remote fail-fast probe có chủ đích trước ApplicationReadyEvent. Khi remote không critical, cần degraded mode rõ ràng thay vì bắt mọi instance thất bại.

Một lần startup thành công không thay thế runtime resilience. Đừng che lỗi bằng default rỗng, infinite retry, lazy validation ngoài ý muốn hoặc logging secrets; hãy phân loại đúng phase, đo root cause và test từng loại failure độc lập.

## 19. Tài liệu chính thức

- Spring Boot 3.3 — Externalized Configuration, Config Data và @ConfigurationProperties Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — SpringApplication, startup failure và runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — ConfigurationProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — Actuator Health and Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Cloud Config — Config Data Import, Fail Fast: https://docs.spring.io/spring-cloud-config/reference/client.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/