# Chọn môi trường đích bằng cấu hình có thể kiểm chứng

Một CLI triển khai, đồng bộ hoặc quản trị hệ thống thường chạy ở nhiều môi trường: local, staging và production. Nếu URL đích, account hoặc tên môi trường được hard-code rải rác trong command, người vận hành khó biết command sẽ tác động vào hệ thống nào. Một lựa chọn sai có thể khiến dữ liệu thử nghiệm đi vào production hoặc ngược lại.

Spring Boot cung cấp externalized configuration và profiles để tách cấu hình khỏi mã nguồn. ConfigurationProperties gom các giá trị liên quan thành một kiểu dữ liệu có cấu trúc; Bean Validation có thể từ chối cấu hình thiếu hoặc mâu thuẫn ngay khi ứng dụng khởi động. Spring Shell có thể hiển thị target đang có hiệu lực và cung cấp command kiểm tra kết nối trước thao tác.

## 1. Xác định rõ target của một lần chạy

Target là đích mà command sẽ gọi hoặc thay đổi. Một target thường gồm:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Environment | Nhóm môi trường | STAGING |
| Base URI | Địa chỉ API gốc | https://api.staging.example.test |
| Account ID | Tài khoản hoặc tenant đích | staging-account |
| Project ID | Dự án hoặc workspace đích | orders-staging |

Trong bài này, mỗi tiến trình CLI sử dụng một target đã được cấu hình khi khởi động. Người vận hành chọn profile, ứng dụng bind các thuộc tính target, xác thực chúng rồi mới cho phép command sử dụng. Cách này giúp mọi command trong cùng tiến trình dùng chung một target rõ ràng.

Nếu sản phẩm cần chuyển qua lại nhiều target trong cùng một phiên, hãy dùng một catalog target có tên và option --target để chọn mục trong catalog. Không thay đổi spring.profiles.active giữa các command để giả lập chuyển môi trường; profiles được dùng để cấu hình ApplicationContext khi khởi động.

## 2. Tách cấu hình bằng Spring Profiles

Spring Boot hỗ trợ file cấu hình theo profile với quy ước application-{profile}.yml. File application.yml chứa thiết lập chung; file profile chứa giá trị riêng của môi trường.

Ví dụ cấu trúc:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-staging.yml
  application-production.yml
```

File application.yml có thể đặt chính sách không tự chọn một môi trường mặc định:

```yaml
spring:
  profiles:
    default: none
```

Khi không có profile được kích hoạt, target sẽ không được cấu hình và validation sẽ khiến ứng dụng dừng khởi động. Cách này tránh việc một bản CLI vô tình sử dụng một target mặc định mà người vận hành không nhận ra.

File application-staging.yml:

```yaml
deployment:
  target:
    environment: STAGING
    base-uri: https://api.staging.example.test
    account-id: staging-account
```

File application-local.yml:

```yaml
deployment:
  target:
    environment: LOCAL
    base-uri: https://api.local.example.test
    account-id: local-account
```

File application-production.yml:

```yaml
deployment:
  target:
    environment: PRODUCTION
    base-uri: https://api.production.example.test
    account-id: production-account
```

Các hostname .example.test chỉ là địa chỉ minh họa dành cho tài liệu; thay chúng bằng hostname được tổ chức phê duyệt.

## 3. Kích hoạt profile khi chạy CLI

Profile có thể được kích hoạt bằng property spring.profiles.active. Với ứng dụng CLI, biến môi trường là cách rõ ràng để chọn cấu hình trước khi tiến trình bắt đầu:

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=staging java -jar app.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar app.jar
```

Spring Boot cũng hỗ trợ kích hoạt nhiều profile, ví dụ staging,metrics. Nếu nhiều profile cùng định nghĩa một thuộc tính, thứ tự profile có ảnh hưởng đến giá trị cuối cùng: profile được xử lý sau có thể ghi đè giá trị trước. Vì vậy, chỉ nên dùng nhiều profile cho các nhóm cấu hình có chủ đích, chẳng hạn một profile môi trường và một profile bật metrics.

spring.profiles.active và spring.profiles.default phải được đặt trong tài liệu cấu hình không gắn profile. Không đặt chúng bên trong application-staging.yml hoặc application-production.yml; Spring Boot không cho phép kích hoạt profile từ một tài liệu vốn chỉ được nạp khi profile đã hoạt động. <Link url="https://docs.spring.io/spring-boot/3.4/reference/features/profiles.html" title="Profiles — Spring Boot 3.4"/>.

## 4. Hiểu thứ tự ưu tiên của cấu hình

Spring Boot có nhiều nguồn cấu hình. Giá trị đến từ nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trong nguồn thấp hơn.

Một số nguồn thường gặp, theo thứ tự ưu tiên tăng dần:

| Nguồn | Ví dụ |
| --- | --- |
| Giá trị mặc định trong ứng dụng | SpringApplication.setDefaultProperties(...) |
| File cấu hình trong JAR | application.yml |
| File cấu hình theo profile trong JAR | application-staging.yml |
| File cấu hình bên ngoài JAR | ./config/application.yml |
| File profile bên ngoài JAR | ./config/application-staging.yml |
| Biến môi trường hệ điều hành | DEPLOYMENT_TARGET_BASEURI |
| Java system properties | -Ddeployment.target.environment=STAGING |
| Command-line properties của Spring Boot | --deployment.target.environment=STAGING |

Command-line properties có độ ưu tiên cao hơn file cấu hình. Điều này tiện cho kiểm thử một lần chạy, nhưng cũng có nghĩa giá trị target thực tế có thể khác với file YAML mà người vận hành vừa xem. Hãy xác minh target sau khi Spring bind cấu hình thay vì chỉ đọc một file. <Link url="https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html" title="Externalized Configuration — Spring Boot 3.4"/>.

Các đối số dạng --deployment.target... trong bảng là property truyền lúc khởi động JVM. Sau khi Spring Shell đã mở prompt, chỉ dùng option mà command hiện tại khai báo; gõ một property của Spring Boot tại prompt không thay đổi Environment hoặc profile của tiến trình đang chạy.

Tên biến môi trường thường chuyển dấu chấm thành dấu gạch dưới và dùng chữ hoa. Ví dụ deployment.target.base-uri có thể được truyền dưới dạng DEPLOYMENT_TARGET_BASEURI theo quy tắc relaxed binding của Spring Boot. Hãy kiểm tra quy tắc chuyển tên property cho key cụ thể và thử trong môi trường triển khai thực tế.

## 5. Gom target thành kiểu dữ liệu với ConfigurationProperties

Không nên rải nhiều Value cho từng thuộc tính target. Dùng ConfigurationProperties để gom các giá trị có liên quan vào một đối tượng có kiểu dữ liệu.

Đầu tiên, định nghĩa enum môi trường:

```java
public enum TargetEnvironment {
    LOCAL,
    STAGING,
    PRODUCTION
}
```

Sau đó định nghĩa record cấu hình:

```java
import java.net.URI;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "deployment.target")
@Validated
public record DeploymentTargetProperties(
        @NotNull TargetEnvironment environment,
        @NotNull URI baseUri,
        @NotBlank String accountId) {

    @AssertTrue(message = "base-uri không khớp với environment đã chọn")
    public boolean isEndpointAllowedForEnvironment() {
        if (environment == null || baseUri == null || baseUri.getHost() == null) {
            return false;
        }

        String expectedHost = switch (environment) {
            case LOCAL -> "api.local.example.test";
            case STAGING -> "api.staging.example.test";
            case PRODUCTION -> "api.production.example.test";
        };

        return "https".equalsIgnoreCase(baseUri.getScheme())
                && expectedHost.equalsIgnoreCase(baseUri.getHost())
                && baseUri.getUserInfo() == null
                && baseUri.getQuery() == null
                && baseUri.getFragment() == null;
    }
}
```

Ví dụ dùng NotNull và NotBlank để kiểm tra trường bắt buộc. Phương thức isEndpointAllowedForEnvironment kiểm tra mối quan hệ giữa environment và hostname. Vì vậy, cấu hình environment STAGING đi cùng hostname production sẽ bị từ chối.

Đây là allow-list minh họa. Trong hệ thống thực tế, hãy lấy danh sách hostname từ cấu hình được quản lý hoặc một registry đáng tin cậy; không cho phép người vận hành truyền một URI bất kỳ rồi coi đó là target hợp lệ.

## 6. Đăng ký ConfigurationProperties

Có thể dùng ConfigurationPropertiesScan trên lớp ứng dụng để Spring Boot tìm các lớp cấu hình trong package của ứng dụng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SpringShellApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringShellApplication.class, args);
    }
}
```

Nếu không dùng scanning, có thể đăng ký class bằng EnableConfigurationProperties(DeploymentTargetProperties.class) trên một lớp Configuration.

Spring Boot bind giá trị từ Environment vào đối tượng có kiểu. Khi có Validated và implementation Jakarta Bean Validation trên classpath, constraint được kiểm tra khi cấu hình được tạo. Với cấu trúc lồng nhau, đánh dấu field bằng Valid để validation đi tiếp vào object con. <Link url="https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation" title="ConfigurationProperties Validation — Spring Boot 3.4"/>.

Với Maven và Spring Boot dependency management, thêm starter validation để có implementation Jakarta Bean Validation:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Nếu thiếu implementation validation trên classpath, các annotation constraint sẽ không được thực thi như mong đợi.

## 7. Validation lúc khởi động và kiểm tra trước thao tác

Hai lần kiểm tra có mục đích khác nhau:

| Thời điểm | Kiểm tra | Ví dụ |
| --- | --- | --- |
| Khi bind cấu hình | Cấu trúc và tính nhất quán của target | Environment hợp lệ, URI đúng hostname được phép |
| Trước khi thực hiện command | Target còn hoạt động và người dùng có quyền | Account còn hiệu lực, project được phép triển khai |

Validation lúc khởi động ngăn ứng dụng chạy với cấu hình thiếu hoặc mâu thuẫn. Nó không chứng minh API từ xa đang hoạt động và không chứng minh người dùng có quyền thực hiện hành động.

Ví dụ, URI có thể hợp lệ nhưng DNS không phân giải được, chứng chỉ TLS hết hạn hoặc dịch vụ từ xa đang bảo trì. Command target verify nên thực hiện một phép kiểm tra chỉ đọc để xác nhận kết nối thực tế.

## 8. Hiển thị target đang có hiệu lực trong Spring Shell

Người vận hành nên có cách xem target mà ứng dụng đã bind. Command chỉ hiển thị thông tin không nhạy cảm:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class TargetCommands {

    private final DeploymentTargetProperties target;
    private final TargetConnectionVerifier targetConnectionVerifier;

    public TargetCommands(
            DeploymentTargetProperties target,
            TargetConnectionVerifier targetConnectionVerifier) {
        this.target = target;
        this.targetConnectionVerifier = targetConnectionVerifier;
    }

    @ShellMethod(key = "target show", value = "Hiển thị môi trường đích hiện tại")
    public String showTarget() {
        return """
                Environment: %s
                Endpoint: %s
                Account: %s
                """.formatted(
                target.environment(),
                target.baseUri().getHost(),
                target.accountId());
    }
}
```

Chỉ in hostname thay vì toàn bộ URI nếu URI có thể chứa path nhạy cảm. Không in password, access token, API key hoặc header xác thực. target show giúp người vận hành kiểm tra target hiệu lực trước khi gọi command thay đổi dữ liệu.

## 9. Kiểm tra khả năng kết nối trước khi thao tác

Nếu API đích cung cấp endpoint health chỉ đọc và endpoint đó được phép truy cập, có thể dùng RestClient để kiểm tra:

```java
import java.net.URI;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class TargetConnectionVerifier {

    private final RestClient restClient;
    private final DeploymentTargetProperties target;

    public TargetConnectionVerifier(
            RestClient.Builder restClientBuilder,
            DeploymentTargetProperties target) {
        this.restClient = restClientBuilder.build();
        this.target = target;
    }

    public void verify() {
        URI healthUri = target.baseUri().resolve("/actuator/health");
        restClient.get()
                .uri(healthUri)
                .retrieve()
                .toBodilessEntity();
    }
}
```

RestClient.Builder được Spring Boot tự cấu hình khi ứng dụng có Spring Web trên classpath, chẳng hạn qua spring-boot-starter-web. Ví dụ giả định dịch vụ đích công bố /actuator/health và cho phép CLI gọi endpoint đó. Nếu hệ thống dùng endpoint kiểm tra riêng hoặc cơ chế xác thực khác, thay bằng client và probe phù hợp.

Gắn verifier vào command:

```java
@ShellMethod(key = "target verify", value = "Kiểm tra kết nối tới môi trường đích")
public String verifyTarget() {
    targetConnectionVerifier.verify();
    return "Đã kết nối tới " + target.baseUri().getHost();
}
```

Nếu probe thất bại, command phải báo lỗi và dừng trước thao tác ghi. Không biến một lỗi kết nối thành thông báo thành công hoặc tự động chuyển sang endpoint khác.

## 10. Profile chọn cấu hình, không cấp quyền

Profile xác định nhóm bean và cấu hình nào được nạp. Ví dụ production adapter có thể chỉ được đăng ký khi profile production hoạt động:

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class ProductionDeploymentAdapter implements DeploymentAdapter {
    // Implementation dành cho production.
}
```

Profile không phải cơ chế authorization. Người có thể đặt SPRING_PROFILES_ACTIVE=production chưa chắc được phép triển khai production. Service thực hiện thao tác vẫn cần xác minh danh tính, quyền trên account/project và chính sách phê duyệt.

Tương tự, hostname nằm trong allow-list chỉ xác nhận cấu hình trỏ tới một endpoint đã biết. Nó không thay thế xác thực TLS, credential management hoặc kiểm tra quyền ở phía hệ thống đích.

## 11. Tách một target mỗi tiến trình và catalog nhiều target

**Một target mỗi tiến trình** phù hợp với CLI vận hành theo môi trường. Profile chọn một cấu hình, mọi command trong tiến trình dùng cùng DeploymentTargetProperties. Cách này dễ kiểm tra và hạn chế nhầm lẫn khi script chạy nhiều bước.

Nếu cần thao tác với nhiều target trong cùng phiên, mô hình hóa chúng thành một map:

```yaml
deployment:
  targets:
    staging:
      base-uri: https://api.staging.example.test
      account-id: staging-account
    production:
      base-uri: https://api.production.example.test
      account-id: production-account
```

Command nhận --target staging, tra cứu key trong catalog rồi validate endpoint trước khi tạo client. Nếu key không tồn tại, command phải dừng với lỗi rõ ràng. Không nhận URI tùy ý từ người dùng khi chỉ cho phép chọn trong một danh sách target đã phê duyệt.

Hai mô hình có thể cùng tồn tại, nhưng nên chọn một cách nhất quán cho từng workflow. Không dùng profile để thay đổi target động giữa các command trong cùng ApplicationContext.

## 12. Kiểm chứng cấu hình cuối cùng

Khi target có giá trị bất ngờ, kiểm tra nguồn nào đã ghi đè giá trị ban đầu. Spring Boot Actuator cung cấp endpoint env và configprops để chẩn đoán Environment và các bean ConfigurationProperties. Các endpoint này có thể chứa thông tin nhạy cảm, vì vậy chỉ bật và cấp quyền truy cập trong môi trường vận hành phù hợp.

Một quy trình preflight có thể gồm:

1. Xác nhận profile đang hoạt động.
2. Chạy target show để xem environment, hostname và account.
3. Xác nhận hostname khớp với environment.
4. Chạy target verify để kiểm tra kết nối chỉ đọc.
5. Xác nhận project/account đích và quyền của người vận hành.
6. Sau đó mới chạy command thay đổi dữ liệu.

Với command có tác động lớn, hãy hiển thị lại target trong phần xác nhận trước khi thực thi. Nếu target không rõ hoặc không qua validation, dừng thao tác.

## 13. Bảo vệ bí mật trong cấu hình

Không commit password, token, private key hoặc client secret vào application-production.yml. Dùng secret manager, biến môi trường hoặc cơ chế cấp credential của nền tảng triển khai. Chỉ bind những giá trị cần thiết vào service; không in chúng ra target show, exception message hoặc log.

URI cũng có thể chứa user-info hoặc query string. Ví dụ trong bài kiểm tra và từ chối URI có user-info, query và fragment. Khi hiển thị target, ưu tiên getHost() hoặc một nhãn target đã được đăng ký thay vì in toàn bộ URI.

## 14. Kiểm thử cấu hình và chọn target

Nên có test cho cấu hình hợp lệ, cấu hình thiếu và cấu hình mâu thuẫn.

Test cấu hình hợp lệ với profile:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("staging")
class DeploymentTargetPropertiesTest {

    @Autowired
    DeploymentTargetProperties target;

    @Test
    void loadsStagingTarget() {
        assertThat(target.environment()).isEqualTo(TargetEnvironment.STAGING);
        assertThat(target.baseUri().getHost())
                .isEqualTo("api.staging.example.test");
    }
}
```

Với cấu hình sai, có thể dùng ApplicationContextRunner để xác nhận context không khởi động:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class InvalidTargetConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ConfigurationPropertiesAutoConfiguration.class,
                            ValidationAutoConfiguration.class))
                    .withUserConfiguration(TestConfig.class)
                    .withPropertyValues(
                            "deployment.target.environment=STAGING",
                            "deployment.target.base-uri=https://api.production.example.test",
                            "deployment.target.account-id=test-account");

    @Test
    void rejectsEndpointThatDoesNotMatchEnvironment() {
        contextRunner.run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeploymentTargetProperties.class)
    static class TestConfig {
    }
}
```

Các kiểm thử bổ sung:

- Không có profile và thiếu target phải làm ứng dụng dừng khởi động.
- URI không phải HTTPS hoặc hostname không nằm trong allow-list phải bị từ chối.
- Property command line ghi đè profile phải được phản ánh trong target show.
- Probe lỗi phải ngăn command triển khai tiếp tục.
- Người dùng không có quyền phải bị từ chối dù target hợp lệ.
- Log và output không chứa credential.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ứng dụng dùng nhầm môi trường mặc định | Profile mặc định hoặc file chung chứa target không mong muốn | Bỏ target mặc định và yêu cầu profile rõ ràng |
| Profile được chọn nhưng target không đổi | File application-{profile} sai tên hoặc không nằm trong config locations | Kiểm tra profile và vị trí file |
| spring.profiles.active không có tác dụng | Đặt trong file profile-specific | Đặt ở biến môi trường, system property hoặc tài liệu không gắn profile |
| Target hiển thị khác YAML | Biến môi trường hoặc command-line property ghi đè | Kiểm tra property source và chạy target show |
| Environment staging nhưng URL production | Cấu hình bị ghi đè một phần | Dùng cross-field validation và allow-list |
| Ứng dụng khởi động nhưng API không truy cập được | Validation chỉ kiểm tra hình dạng cấu hình | Chạy target verify và xử lý lỗi kết nối |
| Người dùng chọn production dù không có quyền | Nhầm profile với authorization | Kiểm tra quyền trong service và hệ thống đích |
| Bí mật xuất hiện trong log | In toàn bộ URI hoặc cấu hình | Chỉ hiển thị nhãn/hostname và che dữ liệu nhạy cảm |

## 16. Bài thực hành tổng hợp

Xây dựng CLI quản lý triển khai với ba môi trường:

1. Tạo application.yml và các file application-local.yml, application-staging.yml, application-production.yml.
2. Đặt default profile là none để yêu cầu người vận hành chọn môi trường.
3. Tạo TargetEnvironment enum và DeploymentTargetProperties dùng ConfigurationProperties.
4. Bật validation bằng Validated, Jakarta constraints và kiểm tra hostname theo environment.
5. Đăng ký properties bằng ConfigurationPropertiesScan.
6. Tạo command target show để hiển thị target hiệu lực mà không lộ bí mật.
7. Tạo command target verify dùng probe chỉ đọc tới endpoint được cấu hình.
8. Trong service triển khai, kiểm tra quyền account/project trước khi thực hiện thao tác ghi.
9. Thử ghi đè base-uri bằng biến môi trường hoặc command-line property; xác nhận cấu hình mâu thuẫn bị từ chối.
10. Viết test cho profile hợp lệ, target không hợp lệ, probe lỗi và quyền không đủ.

## 17. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Profiles | Chọn đúng file cấu hình theo profile và hiểu quy tắc active/default |
| Property precedence | Biết biến môi trường và command-line property có thể ghi đè file |
| Type-safe config | Gom target bằng ConfigurationProperties |
| Startup validation | Từ chối cấu hình thiếu, sai kiểu hoặc mâu thuẫn |
| Target visibility | Hiển thị đúng environment, hostname và account hiệu lực |
| Connectivity | Kiểm tra kết nối bằng probe chỉ đọc |
| Security | Không coi profile hoặc allow-list là authorization |
| Secrets | Không lưu hoặc in credential trong cấu hình/log |
| Multiple targets | Biết khi nào dùng một target mỗi process và khi nào dùng catalog |
| Testing | Kiểm tra profile, override, target sai và quyền truy cập |

## Tài liệu tham khảo

- [Spring Boot 3.4 — Profiles](https://docs.spring.io/spring-boot/3.4/reference/features/profiles.html)
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html)
- [Spring Boot 3.4 — ConfigurationProperties Validation](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Boot 3.4 — RestClient](https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html)
