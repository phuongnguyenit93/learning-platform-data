# Thu hẹp lỗi bằng phiên bản, cấu hình hiệu lực và ca tái hiện tối thiểu

Khi một command Spring Shell hoạt động ở máy này nhưng lỗi ở máy khác, hoặc chỉ lỗi khi chạy bằng profile/launcher nhất định, việc đọc riêng `application.yml` thường không đủ để tìm nguyên nhân. Ứng dụng có thể đang chạy một phiên bản dependency khác, nạp thêm file cấu hình bên ngoài, nhận giá trị ghi đè từ environment hoặc chọn một shell runner khác với điều bạn nghĩ.

Cách chẩn đoán hiệu quả là thu hẹp ba yếu tố theo thứ tự: xác định chính xác phiên bản và cách khởi chạy; tìm giá trị cấu hình thực sự có hiệu lực cùng nguồn cung cấp; sau đó tạo một ca tái hiện nhỏ nhất vẫn giữ được lỗi. Mỗi lần chỉ thay đổi một yếu tố để biết điều gì làm lỗi xuất hiện hoặc biến mất.

## 1. Ghi lại triệu chứng trước khi thay đổi cấu hình

Hãy mô tả lỗi bằng thông tin có thể kiểm tra lại:

- Command nào được gọi và câu lệnh đầy đủ là gì?
- Kết quả mong đợi và kết quả thực tế khác nhau ở đâu?
- Lỗi xảy ra lúc khởi động, lúc đăng ký command, khi parse input hay trong lúc thực thi?
- Ứng dụng chạy interactive, non-interactive hay từ script?
- Lỗi có xảy ra ở mọi profile, hay chỉ ở `dev`, `test`, `staging` hoặc `prod`?
- Lỗi có phụ thuộc thư mục làm việc, biến môi trường, launcher, OS hoặc JDK không?
- Lần cuối command hoạt động là khi nào và thay đổi gần nhất là gì?

Phân biệt lỗi cấu hình với lỗi logic bằng một ví dụ cụ thể. Ví dụ: command `report export` luôn dùng endpoint sandbox dù profile production đã bật; hoặc command không xuất hiện khi chạy từ service nhưng xuất hiện khi chạy từ IDE.

Đừng thay nhiều property cùng lúc trước khi ghi nhận trạng thái ban đầu. Nếu thay đồng thời profile, config location, dependency và runner mode, bạn sẽ khó biết thay đổi nào đã sửa lỗi.

## 2. Xác định chính xác phiên bản runtime

Tên version trong `pom.xml` hoặc `build.gradle` chỉ cho biết version được khai báo. Dependency management, version catalog và dependency bắc cầu có thể khiến runtime resolve ra một version khác.

Ghi nhận ít nhất:

| Thành phần | Cần ghi lại |
|---|---|
| Java runtime | Vendor, phiên bản và kiến trúc JVM |
| Spring Boot | Version thực sự được resolve |
| Spring Framework | Version thực sự được resolve |
| Spring Shell | Version thực sự được resolve |
| JLine | Version thực sự được resolve nếu dùng terminal tương tác |
| Build tool | Maven/Gradle wrapper và version |
| Artifact | JAR đang chạy, thời điểm build và commit tương ứng |
| Hệ điều hành | OS, architecture và cách khởi chạy |

Lấy thông tin Java:

```bash
java -version
```

Kiểm tra dependency Spring Shell bằng Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
./mvnw dependency:tree -Dincludes=org.springframework.boot
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-shell --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
```

Nếu dùng Windows PowerShell, thay `./mvnw` bằng `.\mvnw.cmd` và `./gradlew` bằng `.\gradlew.bat` theo wrapper có trong dự án.

Đối chiếu version thực tế với yêu cầu tương thích của Spring Shell. Chẳng hạn Spring Shell 4.x đi cùng hệ Spring Boot 4/Spring Framework 7; dự án 3.x có ma trận tương thích khác. Không kết luận lỗi là do code command trước khi xác nhận classpath runtime không trộn các major version.

Nếu có thể, ghi cả version hiển thị trong startup log và version trong dependency tree. Một JAR cũ được launcher chạy từ thư mục khác có thể không phải artifact bạn vừa build.

## 3. Ghi lại cách khởi chạy và thư mục làm việc

Hai lần chạy cùng một JAR có thể nhận cấu hình khác nhau do thư mục làm việc, environment variables, JVM arguments hoặc launcher.

Ghi lại:

- Lệnh đầy đủ dùng để chạy JAR hoặc executable.
- Thư mục hiện tại tại thời điểm chạy.
- Các JVM arguments bắt đầu bằng `-D`.
- Các Spring Boot arguments bắt đầu bằng `--`.
- Các biến môi trường liên quan đến `SPRING_` và prefix cấu hình của ứng dụng.
- Profile đang hoạt động.
- Config file bên ngoài, volume mount hoặc secret/config tree được import.
- Chế độ shell và runner được chọn.

Kiểm tra thư mục làm việc:

```bash
pwd
```

PowerShell:

```powershell
Get-Location
```

Spring Boot tìm file cấu hình bên ngoài JAR dựa trên các vị trí mặc định có liên quan đến current working directory. Vì vậy, chạy từ IDE, terminal, systemd hoặc CI runner có thể nạp các file `application.yml` khác nhau dù cùng một JAR.

Không gửi toàn bộ environment hoặc JVM arguments lên issue tracker nếu chúng chứa password, token, private key hay URL có credential. Chỉ thu thập các key liên quan và che giá trị nhạy cảm.

## 4. Phân biệt file cấu hình với cấu hình hiệu lực

`application.yml` chỉ là một nguồn cấu hình. Spring Boot hợp nhất nhiều `PropertySource` vào `Environment`; nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị từ nguồn thấp hơn.

Các nguồn thường gặp, từ ưu tiên thấp lên cao:

| Thứ tự | Nguồn | Ví dụ |
|---:|---|---|
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | Property file được khai báo trên configuration class |
| 3 | Config data | `application.yml`, file profile và file import |
| 4 | Random property source | Các key `random.*` |
| 5 | OS environment variables | `APP_REMOTE_URL`, `SPRING_PROFILES_ACTIVE` |
| 6 | JVM system properties | `-Dapp.remote-url=...` |
| 7 | JNDI/servlet properties | Giá trị từ application server nếu có |
| 8 | `SPRING_APPLICATION_JSON` | JSON cấu hình được đưa vào environment |
| 9 | Command-line properties | `--app.remote-url=...` |
| 10 | Test property sources | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource` |

Đây là danh sách rút gọn các nguồn thường gặp trong ứng dụng CLI. Spring Boot có thể bổ sung nguồn khác tùy môi trường và test framework. Khi hai nguồn cùng khai báo một key, nguồn có ưu tiên cao hơn sẽ quyết định giá trị được bind.

Ví dụ `application.yml` có:

```yaml
app:
  remote:
    base-url: https://sandbox.example.test
```

Nhưng shell được khởi chạy với:

```bash
APP_REMOTE_BASEURL=https://api.example.com \
java -jar catalog-cli.jar
```

Environment variable có thể ghi đè giá trị trong config data. Nếu chỉ đọc YAML, bạn có thể kết luận nhầm rằng ứng dụng đang gọi sandbox trong khi runtime thực tế gọi endpoint production.

Một điểm dễ nhầm: `@PropertySource` được thêm vào `Environment` khi context refresh. Nó quá muộn để cấu hình một số thuộc tính được đọc trước refresh, chẳng hạn `logging.*` và `spring.main.*`. Với các thuộc tính bootstrap, hãy đặt chúng ở environment variable, system property hoặc command-line argument phù hợp.

## 5. Kiểm tra thứ tự nạp file và profile

Spring Boot tìm `application.properties`, `application.yaml` hoặc `application.yml` trong các vị trí mặc định như classpath root, classpath `/config`, current directory, thư mục `config/` và các thư mục con trực tiếp của `config/`.

Trong nhóm config data, các file thường được xét theo thứ tự:

1. `application.yml` đóng gói bên trong JAR.
2. `application-{profile}.yml` đóng gói bên trong JAR.
3. `application.yml` nằm bên ngoài JAR.
4. `application-{profile}.yml` nằm bên ngoài JAR.

Nếu cùng một vị trí có cả `application.properties` và `application.yml`, file `.properties` được ưu tiên. Khi tìm giá trị bất ngờ, kiểm tra cả hai định dạng thay vì chỉ mở file YAML.

Các file profile-specific ghi đè file không gắn profile. Nếu bật nhiều profile, profile đứng sau có thể ghi đè profile đứng trước. Ví dụ `spring.profiles.active=prod,region-eu` cho phép `application-region-eu.yml` ghi đè giá trị tương ứng từ `application-prod.yml`.

Kiểm tra profile bằng startup log hoặc `Environment.getActiveProfiles()`. Đừng chỉ nhìn file `application-prod.yml` rồi giả định profile `prod` đang hoạt động.

### `spring.config.location` và `spring.config.additional-location`

Hai property này có hành vi khác nhau:

- `spring.config.location` thay thế các vị trí tìm kiếm mặc định.
- `spring.config.additional-location` bổ sung vị trí mới vào danh sách mặc định; file ở vị trí bổ sung có thể ghi đè file mặc định.

Ví dụ:

```bash
java \
  -Dspring.config.additional-location=file:./deploy-config/ \
  -Dspring.profiles.active=prod \
  -jar catalog-cli.jar
```

Nếu dùng `spring.config.location` mà quên thêm một vị trí mặc định cần thiết, ứng dụng có thể không nạp file cấu hình bạn nghĩ nó đang dùng. Các thuộc tính `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được đọc rất sớm; đặt chúng qua environment, system property hoặc command-line argument trước khi context khởi tạo.

### Kiểm tra `spring.config.import`

File cấu hình có thể import thêm file khác hoặc config tree:

```yaml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
```

Giá trị từ file import có thể ghi đè giá trị trong file khai báo import. Khi một property có giá trị bất ngờ, lần theo cả chuỗi import thay vì chỉ mở file gốc.

## 6. Tìm nguồn của một property cụ thể

Đừng dump toàn bộ `Environment`. Hãy chọn đúng key đang nghi ngờ và xác định:

1. Giá trị runtime hiện tại là gì?
2. Property source nào cung cấp giá trị đó?
3. File hoặc dòng nào khai báo nó nếu có origin metadata?
4. Có nguồn ưu tiên cao hơn ghi đè không?

Trong môi trường có Spring Boot Actuator, endpoint `env` có thể cho biết property source và origin của một key; `configprops` cho biết các giá trị đã bind vào `@ConfigurationProperties`. Ví dụ endpoint `env` có thể truy vấn một property cụ thể như `app.remote.base-url`.

Actuator chỉ hữu ích nếu ứng dụng có management endpoint phù hợp. Với CLI không mở HTTP management server, có thể kiểm tra `Environment` trong một diagnostic command hoặc integration test. Chỉ in những key không nhạy cảm và không hiển thị giá trị secret.

Các endpoint `/actuator/env`, `/actuator/configprops` và `/actuator/conditions` có thể chứa thông tin cấu hình nhạy cảm hoặc cấu trúc nội bộ. Chúng được sanitize mặc định ở các phiên bản Boot hiện hành; vẫn cần giữ endpoint sau authentication, chỉ expose trong môi trường cần thiết và không bật `show-values=always` trong production.

Ví dụ một diagnostic component chỉ hiển thị profile và một số thuộc tính không nhạy cảm:

```java
import java.util.Arrays;

import org.springframework.core.env.Environment;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class RuntimeDiagnostics {

    private final Environment environment;

    public RuntimeDiagnostics(Environment environment) {
        this.environment = environment;
    }

    @Command(name = "diagnostic runtime", description = "Show safe runtime settings")
    public String runtime() {
        return "profiles=" + Arrays.toString(environment.getActiveProfiles())
                + ", shellInteractive="
                + environment.getProperty("spring.shell.interactive.enabled")
                + ", configName="
                + environment.getProperty("spring.config.name", "application");
    }
}
```

Ví dụ dùng API command annotation của Spring Shell 4. Nếu dự án đang dùng 3.x, đổi import theo package và command model của phiên bản đó. Không thêm password, token hoặc secret vào output diagnostic.

## 7. Kiểm tra cấu hình đã bind vào `@ConfigurationProperties`

Một property có thể tồn tại trong `Environment` nhưng object cấu hình vẫn nhận giá trị sai do binding, tên prefix, kiểu dữ liệu hoặc validation.

Ví dụ cấu hình có kiểu rõ ràng:

```java
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        @NotBlank String baseUrl,
        int timeoutSeconds) {
}
```

Kiểm tra các điểm sau:

- Prefix trong `@ConfigurationProperties` có khớp YAML không?
- Property name có đúng relaxed binding không?
- Giá trị có chuyển đổi được sang kiểu Java không?
- Có default value trong constructor hoặc field đang che mất cấu hình không?
- Bean properties đã được bật bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` chưa?
- Có `@Validated` và validation provider khi cần kiểm tra ràng buộc không?
- List, map hoặc nested object có bị ghi đè/merge theo quy tắc binding không?

Khi cấu hình sai, ưu tiên fail sớm với thông báo chỉ ra property và constraint. Tránh để endpoint rỗng hoặc timeout bằng `0` chạy sâu vào command rồi mới tạo lỗi khó hiểu.

## 8. Kiểm tra điều kiện tạo bean và auto-configuration

Nếu một bean hoặc command chỉ xuất hiện ở một profile, hãy xem các điều kiện tạo bean:

- `@Profile`.
- `@ConditionalOnProperty`.
- `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass`.
- `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`.
- `@ConditionalOnResource`.
- Condition tùy chỉnh của ứng dụng hoặc starter.

Chạy Spring Boot với `--debug` để in condition evaluation report:

```bash
java -jar catalog-cli.jar --debug
```

Report cho biết auto-configuration nào match, không match và lý do. `--debug` của Spring Boot không có nghĩa là bật toàn bộ logger ở mức DEBUG.

Với Actuator, endpoint `conditions` cho biết các điều kiện đã được đánh giá trên configuration và auto-configuration class. Endpoint này hữu ích khi một auto-configured bean không được tạo.

Nếu đang phát triển một auto-configuration hoặc starter riêng, có thể dùng `ApplicationContextRunner` để thử từng điều kiện với property/classpath khác nhau:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FeatureAutoConfiguration.class);

    @Test
    void createsFeatureWhenEnabled() {
        contextRunner.withPropertyValues("app.feature.enabled=true")
                .run(context -> assertThat(context)
                        .hasSingleBean(FeatureService.class));
    }

    @Test
    void backsOffWhenDisabled() {
        contextRunner.withPropertyValues("app.feature.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }
}
```

Đây là cách cô lập điều kiện Spring Boot mà không cần khởi chạy toàn bộ CLI, database hoặc terminal.

## 9. Kiểm tra riêng execution mode của Spring Shell

Một số lỗi tưởng là cấu hình command nhưng thực tế do runner mode khác với cách gọi.

Trong Spring Shell 4.0.4:

- Interactive mode được bật mặc định, kể cả khi truyền command-line arguments.
- Để chạy command từ process arguments, đặt `spring.shell.interactive.enabled=false`.
- Khi tắt interactive mode, shell chuyển sang `NonInteractiveShellRunner`.
- Nếu dùng Spring Shell starter, interactive mode dùng `JLineShellRunner`; khi không có JLine trên classpath, shell dùng `SystemShellRunner`.
- Mỗi application context chỉ có một `ShellRunner`.

Ví dụ chạy command non-interactive:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar catalog-cli.jar project list --format=json
```

PowerShell:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\catalog-cli.jar project list --format=json
```

Nếu ứng dụng vẫn vào REPL thay vì chạy command từ process arguments, kiểm tra giá trị hiệu lực của `spring.shell.interactive.enabled`, launcher và profile. Đừng kết luận command registration bị lỗi khi runner chưa chuyển sang chế độ mong muốn.

Spring Shell có debug mode riêng:

```yaml
spring:
  shell:
    debug:
      enabled: true
```

`spring.shell.debug.enabled=true` in stack trace của lỗi command trong interactive mode. Nó khác với Boot `--debug`, vốn tập trung vào logging và condition report.

## 10. Thu thập log có mục tiêu

Không bật TRACE cho mọi package ngay từ đầu. Bật log theo lớp đang điều tra:

| Mục tiêu | Cách bật |
|---|---|
| Condition report của Spring Boot | `--debug` |
| Một số logger Spring/Boot ở mức TRACE | `--trace` |
| Theo dõi file config được nạp | `logging.level.org.springframework.boot.context.config=TRACE` |
| Stack trace lỗi command trong interactive shell | `spring.shell.debug.enabled=true` |
| Logger của ứng dụng | `logging.level.com.acme=DEBUG` |

Ví dụ:

```bash
java -jar catalog-cli.jar \
  --debug \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Nếu chỉ cần xem file cấu hình được nạp, logger `org.springframework.boot.context.config` ở TRACE thường hữu ích hơn việc bật log toàn bộ Spring.

Đối với lỗi startup, đọc phần đầu log để biết version, active profile và config location; sau đó đọc exception đầu tiên cùng root cause. Stack trace dài có thể chứa nhiều lỗi được wrap, nhưng exception cuối cùng không phải lúc nào cũng là nguyên nhân đầu tiên.

## 11. Tạo ca tái hiện tối thiểu (Minimal Reproducible Example)

Một ca tái hiện tối thiểu phải giữ lại mọi điều kiện cần để lỗi xảy ra và loại bỏ phần không liên quan. Mục tiêu là để người khác chạy được bằng một lệnh, với kết quả có thể dự đoán.

Giữ lại:

1. Một build file có dependency version chính xác.
2. Một application class và cấu hình Spring cần thiết.
3. Một command nhỏ nhất vẫn tái hiện lỗi.
4. Một service giả hoặc bean stub thay cho database/API thật nếu không cần chúng.
5. Một config file và đúng profile gây lỗi.
6. Một invocation đầy đủ cùng working directory và runner mode.
7. Kết quả thực tế và kết quả mong đợi.

Loại bỏ:

- Command không liên quan.
- Module không cần thiết.
- Kết nối production, dữ liệu thật và secret.
- Custom starter hoặc auto-configuration không liên quan.
- Các profile không tham gia tái hiện.
- Build plugin hoặc logging customization không cần thiết.

Không đổi version hoặc property trước khi đã chứng minh lỗi trong bản tái hiện ban đầu. Nếu thay đổi dependency ngay khi tạo MRE, bạn có thể vô tình xóa điều kiện làm lỗi xảy ra.

## 12. Ví dụ cấu trúc một dự án tái hiện nhỏ

Một dự án Spring Shell tối thiểu có thể chỉ cần:

```text
shell-repro/
  pom.xml
  src/
    main/
      java/
        com/acme/repro/
          ReproApplication.java
          ProbeCommands.java
      resources/
        application.yml
        application-prod.yml
```

`ReproApplication`:

```java
package com.acme.repro;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReproApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
    }
}
```

`ProbeCommands`:

```java
package com.acme.repro;

import org.springframework.core.env.Environment;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProbeCommands {

    private final Environment environment;

    public ProbeCommands(Environment environment) {
        this.environment = environment;
    }

    @Command(name = "probe config", description = "Show the active diagnostic profile")
    public String config() {
        return "profile=" + String.join(",", environment.getActiveProfiles())
                + ", feature=" + environment.getProperty("app.feature.enabled")
                + ", shellInteractive="
                + environment.getProperty("spring.shell.interactive.enabled");
    }
}
```

`application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false

app:
  feature:
    enabled: false
```

`application-prod.yml`:

```yaml
app:
  feature:
    enabled: true
```

Chạy thử profile:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar target/shell-repro.jar probe config
```

Nếu muốn command chạy từ process arguments trên Spring Shell 4, property `spring.shell.interactive.enabled=false` đã được đặt trong `application.yml`. Kết quả cho biết profile và property có hiệu lực. Ví dụ này minh họa cách tạo điểm quan sát nhỏ; hãy thay command/property bằng đúng yếu tố gây lỗi trong ứng dụng thật.

## 13. Kiểm tra một biến mỗi lần

Sau khi có MRE, chạy một chuỗi thử nghiệm có kiểm soát:

| Lần chạy | Thay đổi duy nhất | Câu hỏi cần trả lời |
|---|---|---|
| A | Cấu hình gốc, profile mặc định | Lỗi có xuất hiện không? |
| B | Chỉ bật profile gây lỗi | Profile có làm thay đổi kết quả không? |
| C | Chỉ bỏ environment variable nghi ngờ | Giá trị ghi đè có phải nguyên nhân không? |
| D | Chỉ bỏ file external config | Lỗi có phụ thuộc file bên ngoài không? |
| E | Chỉ đổi runner mode | Lỗi có phải do interactive/non-interactive không? |
| F | Chỉ đổi dependency về version đã biết hoạt động | Có phải regression theo version không? |

Ghi kết quả sau mỗi lần chạy. Khi một thay đổi làm lỗi biến mất, chạy lại bản gốc để xác nhận lỗi quay lại; sau đó áp dụng lại thay đổi để xác nhận kết quả ổn định.

Nếu nhiều thay đổi cần thiết cùng lúc, tiếp tục chia nhỏ cho đến khi xác định được tập điều kiện nhỏ nhất gây lỗi.

## 14. So sánh môi trường hoạt động và môi trường lỗi

Tạo bảng so sánh thay vì gửi hai file cấu hình dài không có ngữ cảnh:

| Dữ liệu | Máy hoạt động | Máy lỗi |
|---|---|---|
| Java | JDK/version | JDK/version |
| Spring Boot/Shell | Resolved versions | Resolved versions |
| Active profiles | `dev` | `prod` |
| Working directory | `./workspace` | `/opt/app` |
| External config | Không có | `/etc/catalog-cli/` |
| Environment override | Không có | `APP_FEATURE_ENABLED=false` |
| Runner mode | Interactive | Non-interactive |
| Command invocation | `project list` trong REPL | Process arguments |
| Artifact | Build mới nhất | JAR được copy từ release trước |

So sánh từng hàng và chỉ điều tra các điểm khác biệt có liên quan đến triệu chứng. Nếu hai môi trường có cùng version nhưng khác active profile và config location, hãy xác minh effective property trước khi điều tra code.

## 15. Đóng gói thông tin tái hiện để gửi báo lỗi

Một báo cáo hữu ích nên có:

- Phiên bản Java, Spring Boot, Spring Framework và Spring Shell.
- Dependency tree đã rút gọn cho các thư viện liên quan.
- OS/architecture và build tool.
- Câu lệnh khởi chạy đầy đủ, đã loại bỏ secret.
- Working directory và active profiles.
- Tên các config file/location đã nạp.
- Giá trị và nguồn của các property không nhạy cảm có liên quan.
- Log từ lúc bắt đầu đến exception/root cause.
- Source code tối thiểu và file cấu hình đã được làm sạch.
- Kết quả mong đợi, kết quả thực tế và các bước tái hiện.
- Kết quả khi thay đổi một yếu tố để khoanh vùng.

Không đính kèm file `.env`, credential, private key, access token, database dump hoặc log chưa rà soát. Thay secret bằng placeholder như `<REDACTED>` nhưng giữ nguyên tên property và cấu trúc cấu hình để người khác vẫn tái hiện được binding.

## 16. Các lỗi thường gặp khi chẩn đoán

| Hiện tượng | Giả định sai thường gặp | Hướng kiểm tra |
|---|---|---|
| YAML ghi `false` nhưng code nhận `true` | Nghĩ file YAML là nguồn duy nhất | Kiểm tra environment, system property, JSON và CLI args |
| Chạy từ IDE được nhưng service lỗi | Nghĩ cùng JAR luôn có cùng cấu hình | So sánh working directory, env, JVM args và external config |
| Profile đúng nhưng endpoint sai | Nghĩ `application-prod.yml` luôn thắng | Kiểm tra external profile file, active profile order và environment override |
| Thêm `spring.config.location` rồi mất property | Nghĩ nó chỉ bổ sung đường dẫn | Dùng `additional-location` nếu muốn giữ default locations |
| Command không chạy khi truyền process args | Nghĩ Spring Shell tự chuyển sang non-interactive | Kiểm tra `spring.shell.interactive.enabled=false` |
| Chỉ lỗi khi chạy một JAR đã phát hành | Nghĩ JAR chắc chắn mới nhất | Xác minh artifact path, checksum/build metadata và dependency tree |
| Bean chỉ được tạo trong test | Nghĩ test context giống production | So sánh test properties, active profile, `@DynamicPropertySource` và component scan |
| Auto-configuration không tạo bean | Nghĩ dependency có mặt là đủ | Xem `--debug`, condition report và endpoint `conditions` |
| Property có trong Environment nhưng object nhận giá trị khác | Nghĩ binding luôn đúng | Kiểm tra prefix, kiểu, default, nested binding và validation |
| Log không cho thấy file config | Chỉ bật root DEBUG | Bật TRACE cho `org.springframework.boot.context.config` |
| Bản tái hiện không còn lỗi | Đã thay nhiều dependency/config khi thu gọn | Khôi phục version và thay đổi từng yếu tố một |
| Báo lỗi nhưng không ai tái hiện được | Thiếu invocation/profile/version | Cung cấp MRE và câu lệnh đầy đủ đã làm sạch secret |

## 17. Quy trình chẩn đoán đề xuất

Thực hiện theo thứ tự:

1. **Ghi lại lỗi.** Nêu command, input, expected/actual và thời điểm lỗi.
2. **Ghi version.** Lấy Java và resolved Spring Shell/Boot/Framework từ runtime dependency tree.
3. **Ghi invocation.** Thu thập working directory, process arguments, JVM arguments và runner mode.
4. **Ghi profile.** Xác nhận active profiles từ log hoặc `Environment`.
5. **Tìm effective property.** Chọn key liên quan, tìm giá trị và nguồn ghi đè.
6. **Kiểm tra config loading.** Rà soát file external, `spring.config.location`, `additional-location` và import.
7. **Kiểm tra binding/condition.** Xác nhận `@ConfigurationProperties`, validation và điều kiện tạo bean.
8. **Bật log có mục tiêu.** Dùng Boot `--debug`, config TRACE hoặc Spring Shell debug khi phù hợp.
9. **Tạo MRE.** Giữ đúng dependency, một command, một profile và cấu hình cần thiết.
10. **Thay một yếu tố mỗi lần.** Ghi lại kết quả để tìm điều kiện tối thiểu gây lỗi.
11. **Xác nhận lại.** Chạy lại bản gốc và bản đã sửa để chứng minh quan hệ nguyên nhân/kết quả.
12. **Đóng gói báo cáo.** Gửi MRE, version, lệnh chạy, config đã làm sạch và log liên quan.

## 18. Checklist hoàn tất

- [ ] Đã ghi triệu chứng, command, input và expected/actual.
- [ ] Đã xác nhận Java và version dependency thực sự được resolve.
- [ ] Đã ghi lại artifact path, build và working directory.
- [ ] Đã ghi process arguments, JVM arguments và environment keys liên quan.
- [ ] Đã xác nhận active profiles.
- [ ] Đã tìm property hiệu lực và nguồn cung cấp/ghi đè.
- [ ] Đã kiểm tra external config locations và `spring.config.import`.
- [ ] Đã phân biệt `spring.config.location` với `spring.config.additional-location`.
- [ ] Đã kiểm tra binding và validation của `@ConfigurationProperties`.
- [ ] Đã kiểm tra condition report nếu bean/auto-configuration không được tạo.
- [ ] Đã xác nhận Spring Shell runner mode.
- [ ] Đã bật logger có mục tiêu và thu thập root cause.
- [ ] Đã tạo ca tái hiện tối thiểu với version và cấu hình cần thiết.
- [ ] Đã thay đổi một yếu tố mỗi lần và ghi kết quả.
- [ ] Đã loại bỏ secret khỏi log, config và gói tái hiện.
- [ ] Đã xác nhận lỗi xuất hiện lại ở bản gốc và biến mất sau thay đổi sửa lỗi.

## Tài liệu tham khảo

1. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) – thứ tự `PropertySource`, profile-specific files, external config locations và import.
2. [Spring Boot – Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html) – cách thay đổi config locations và bật TRACE cho config loading.
3. [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) – `--debug`, `--trace` và cấu hình logger theo package.
4. [Spring Boot – SpringApplication](https://docs.spring.io/spring-boot/reference/features/spring-application.html) – FailureAnalyzer và condition report khi startup thất bại.
5. [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html) – condition annotations, `ApplicationContextRunner` và `ConditionEvaluationReport`.
6. [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) – `env`, `configprops`, `conditions` và bảo vệ endpoint.
7. [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html) – interactive/non-interactive mode, `ShellRunner` và Spring Shell debug mode.
8. [Spring Shell – Releases](https://github.com/spring-projects/spring-shell/releases) – kiểm tra bug fix và thay đổi theo version cụ thể.

Thu hẹp lỗi bằng cách xác nhận phiên bản đang chạy, tìm giá trị cấu hình thực sự được dùng và giữ lại ca tái hiện nhỏ nhất có thể. Khi mỗi lần thử chỉ thay đổi một yếu tố, bạn sẽ biết chính xác lỗi phụ thuộc vào dependency, profile, property source, runner mode hay logic command.
