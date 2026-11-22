# Xử lý profile không được kích hoạt và cấu hình đặt sai tài liệu

Trong Spring Boot Externalized Configuration, profile dùng để lựa chọn cấu hình theo môi trường hoặc chức năng: `dev`, `test`, `staging`, `prod`. Một ứng dụng có thể đọc `application.yml` chung, `application-prod.yml` dành cho production, các document YAML có điều kiện `spring.config.activate.on-profile`, tệp Config Data được import và các PropertySource do runtime cấp.

Khi người phát triển thấy giá trị không đúng với một file profile, điều đó **không chứng minh profile đã bị tắt**. Có nhiều nguyên nhân: profile không active, file không nằm trong đường tìm Config Data, activation nằm sai YAML document, key điều khiển profile được đặt ở tài liệu không hợp lệ, một nguồn có ưu tiên cao hơn ghi đè, hay bean có `@Profile` và `@ConditionalOnProperty` không được đăng ký.

Bài học này đưa ra quy trình chẩn đoán từ **profile thực tế → document được nạp → thứ tự PropertySource → giá trị đã bind → điều kiện tạo bean**. Các ví dụ giả định Spring Boot 3.x và Java 17+, nhưng cần đối chiếu với phiên bản dùng trong dự án khi triển khai.

## 1. Bốn câu hỏi cần trả lời trước khi sửa YAML

1. **Ứng dụng nào đang chạy?** Kiểm tra process, JAR/image, pod revision và thời điểm khởi động.
2. **Profile nào active?** Đọc startup log, lệnh chạy hoặc `Environment#getActiveProfiles()`.
3. **Tài liệu nào được nạp?** Kiểm tra tên file, locations, import và `on-profile` của từng document.
4. **Nguồn nào thắng cho key cụ thể?** Kiểm tra precedence của CLI, environment, Config Data và binding.

Chỉ sau khi trả lời được bốn câu này mới xem thêm `@Profile`, component scan, validation hoặc List/Map binding. Một giá trị “sai” có thể là hành vi hoàn toàn đúng theo thứ tự ưu tiên.

## 2. Ví dụ application.yml và các tệp theo profile

Cấu trúc:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

Cấu hình chung:

~~~yaml
# application.yml
catalog:
  endpoint: "https://catalog.example.invalid"
  timeout: 5s
  diagnostic-mode: false
~~~

Dev:

~~~yaml
# application-dev.yml
catalog:
  endpoint: "http://localhost:9090"
  timeout: 1s
  diagnostic-mode: true
~~~

Prod:

~~~yaml
# application-prod.yml
catalog:
  endpoint: "https://prod-catalog.example.invalid"
  timeout: 3s
  diagnostic-mode: false
~~~

Nếu active `dev` và không có nguồn khác ghi đè, endpoint là localhost, timeout là 1s. Với `prod`, endpoint production và timeout 3s có thể được dùng. Nếu không có active profile tương ứng, giá trị từ file chung có thể được dùng.

| Profiles | Timeout dự kiến | Diagnostic mode |
| --- | --- | --- |
| Không active dev/prod | 5s | false |
| dev | 1s | true |
| prod | 3s | false |

Đây là **kỳ vọng cho bộ nguồn đơn giản**, không phải bảo đảm nếu còn Config Data imports, environment, CLI hoặc system properties có cùng key.

## 3. Kích hoạt profile bằng tham số dòng lệnh

Khi chạy executable JAR:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Production:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Nhiều profile:

~~~bash
java -jar app.jar --spring.profiles.active=staging,metrics
~~~

Cú pháp `--spring.profiles.active=dev` là application argument của Spring Boot, được đặt **sau** tên JAR. Java system property là cú pháp khác:

~~~bash
java -Dspring.profiles.active=dev -jar app.jar
~~~

`-Dspring.profiles.active=dev` là JVM argument, đặt **trước** `-jar`. Đặt nhầm vào trường VM options/Program arguments của IDE hoặc đặt sai thứ tự có thể khiến process không nhận profile như dự đoán.

Không nên suy ra profile từ tên Git branch, tên thư mục hoặc container image: Spring chỉ biết những giá trị runtime/configuration mà nó thực sự nhận.

## 4. Kích hoạt bằng biến môi trường

Trong POSIX shell:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
~~~

Nếu chạy qua Docker, Kubernetes, CI hoặc service manager, hãy kiểm tra biến được truyền tới **đúng process Java**, không chỉ có mặt trong manifest hay pipeline editor.

Các lỗi thường gặp:

- Gõ sai `SPRING_PROFILES_ACTIVE`.
- Giá trị có whitespace hoặc dấu nháy không mong muốn.
- Biến chỉ được cấp cho container/job khác.
- Command line hoặc system property ghi đè.
- Pod chưa restart sau khi thay environment.
- Ứng dụng thực tế chạy artifact cũ.
- Có nhiều replica và log đang đọc thuộc replica khác.

Lựa chọn profile nên được quản lý bởi deployment khi artifact dùng chung cho nhiều môi trường.

## 5. Active và default profiles khác nhau

Spring Environment có:

~~~java
environment.getActiveProfiles();
environment.getDefaultProfiles();
~~~

`getActiveProfiles()` trả về các profile active, có thể là mảng rỗng. `getDefaultProfiles()` trả về default profiles được dùng trong tình huống không có active profiles; mặc định thường chứa `default`.

Vì vậy, thông báo có nghĩa tương tự:

~~~text
No active profile set, falling back to default profile...
~~~

không nhất thiết là lỗi. Nó không có nghĩa `application.yml` không được nạp.

Có thể đặt default profile trong tài liệu không profile-specific:

~~~yaml
# application.yml, tài liệu chung
spring:
  profiles:
    default: "local"
~~~

Khi `prod` được active tường minh, default profile không thay nó. Không nhầm “không active profile” với “không có cấu hình”.

## 6. Tên file theo profile phải khớp chính xác

Spring Boot thường tìm những tài liệu theo convention:

~~~text
application-{profile}.properties
application-{profile}.yml
application-{profile}.yaml
~~~

Nếu active `prod`, tên `application-production.yml` không tự trở thành `application-prod.yml`. Những dạng khác như `application_prod.yml`, `Application-prod.yml` hoặc `application-prod.yml.txt` cũng không thể mặc định là tương đương.

Cần kiểm tra:

- Basename có phải `application` không.
- Profile suffix có khớp tên active không.
- Phần mở rộng và chữ hoa/chữ thường.
- Tệp ở classpath, filesystem hay một Config Data location khác.
- Artifact thực sự chứa file.
- Có cùng basename ở cả `.properties` và `.yml` không.

Chỉ vì IDE hiển thị file không có nghĩa JAR/container đang chạy tìm được nó.

## 7. Multi-document YAML và dấu ---

Một `application.yml` có thể chứa nhiều document:

~~~yaml
app:
  greeting: "base"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "dev"

app:
  greeting: "development"
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  greeting: "production"
  timeout: 3s
~~~

Mỗi đoạn ngăn bởi `---` là một YAML document riêng. Document chung không có điều kiện, document dev chỉ có hiệu lực khi profile expression phù hợp, document prod tương tự.

Lỗi thường gặp:

- Thiếu `---` khiến các key nằm không đúng document.
- Tài liệu chung đặt sau tài liệu profile làm thay đổi precedence dự kiến.
- Nhầm activation của một document với điều kiện áp dụng cho cả file.
- Đặt activation dưới prefix nghiệp vụ thay vì root.
- Viết sai `spring.config.activate.on-profile`.

Nên dùng một quy ước dễ đọc: document chung trước, các document có điều kiện sau, rồi test giá trị hiệu lực.

## 8. on-profile không tự bật profile

Ví dụ:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
~~~

Ý nghĩa: **tài liệu này chỉ được sử dụng nếu profile phù hợp đã được chọn**. Nó không tự biến prod thành active.

Phân biệt ba khái niệm:

| Cơ chế | Trách nhiệm |
| --- | --- |
| `spring.profiles.active` | Chọn profile đang active |
| `spring.config.activate.on-profile` | Quyết định YAML document nào có hiệu lực |
| `@Profile("prod")` | Quyết định bean/configuration class nào được đăng ký |

Muốn prod active, truyền profile từ nguồn bootstrap phù hợp:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Không cố gắn `on-profile: prod` vào document rồi kỳ vọng điều đó tự nạp `application-prod.yml`.

## 9. spring.profiles.active không được đặt trong file profile-specific

Cấu hình **sai**:

~~~yaml
# application-prod.yml
spring:
  profiles:
    active: "prod"

app:
  mode: "production"
~~~

Trong Spring Boot Config Data hiện đại, `spring.profiles.active` cần ở nguồn/tài liệu hợp lệ **không profile-specific**. Một file đã mang hậu tố prod không phải nơi để tự bật prod.

Cấu hình đúng hơn:

~~~yaml
# application-prod.yml
app:
  mode: "production"
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Một lỗi tương tự xuất hiện khi `spring.profiles.active` nằm trong tài liệu có `spring.config.activate.on-profile`:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
  profiles:
    active: "staging"
~~~

Boot có thể từ chối khi xử lý Config Data vì property điều khiển active profiles xuất hiện ở document không hợp lệ. Không sửa bằng cách tắt Bean Validation hoặc thay `ignoreUnknownFields`.

## 10. Include, default và group cũng có giới hạn vị trí

Các key điều khiển tập profile như:

- `spring.profiles.active`
- `spring.profiles.include`
- `spring.profiles.default`
- `spring.profiles.group`

cần được khai báo ở những tài liệu được phép, không phải profile-specific document hoặc document bị điều kiện hóa bởi `spring.config.activate.on-profile`.

Ví dụ không nên làm:

~~~yaml
# application-dev.yml
spring:
  profiles:
    include: "metrics"
~~~

Nếu có chủ đích include profile, đặt trong tài liệu chung phù hợp:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - "metrics"
~~~

Nhưng include làm thay đổi tập profile toàn ứng dụng. Nếu mục đích chỉ bật một bean monitoring, cân nhắc điều kiện property riêng thay vì kéo thêm profile có thể ảnh hưởng datasource hoặc security configuration.

## 11. Profile groups

Có thể khai báo nhóm profile:

~~~yaml
# application.yml, tài liệu chung
spring:
  profiles:
    group:
      production:
        - "database-prod"
        - "observability-prod"
~~~

Khi chạy:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot có thể mở rộng group `production` để các profile thành viên cùng hoạt động.

Cần nhớ:

- Group definition phải đặt ở vị trí hợp lệ.
- Group không tự tìm mọi file trong repository.
- Nếu hai profile thành viên ghi cùng key, precedence vẫn cần được xác định.
- Tên file như `application-database-prod.yml` vẫn phải nằm trong Config Data locations được hỗ trợ.
- Test tập profile cuối cùng và các giá trị quan trọng, đặc biệt sau khi thay group membership.

Đừng đặt group bên trong document mà chỉ được nạp khi chính group ấy đã active.

## 12. Biểu thức on-profile

Spring hỗ trợ biểu thức profile:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & eu"

app:
  region-policy: "eu-production"
~~~

Hoặc:

~~~yaml
spring:
  config:
    activate:
      on-profile: "dev | staging"

app:
  diagnostics: true
~~~

Các toán tử và dấu ngoặc cần dùng theo cú pháp profile expression của phiên bản Spring đang dùng. Nếu điều kiện đơn giản, ưu tiên `on-profile: "prod"` để tránh khó hiểu.

Nếu tài liệu không hoạt động, xác minh toàn bộ tập profile, không chỉ tên đầu tiên trong `spring.profiles.active`. Đừng giả định `production` khớp `prod` theo tiền tố.

## 13. Đừng nhầm tên file trong resources với file được nạp

Giả sử:

~~~text
src/main/resources/
  application.yml
  integrations/
    billing-prod.yml
~~~

Spring Boot không mặc định nạp `billing-prod.yml` chỉ vì prod active. Một tệp tên tùy ý phải được đưa vào Config Data theo cách phù hợp, chẳng hạn bằng `spring.config.import`:

~~~yaml
# application.yml
app:
  mode: "base"

---
spring:
  config:
    activate:
      on-profile: "prod"
    import: "classpath:integrations/billing-prod.yml"
~~~

Nếu document prod không active, import nằm trong document đó không tự được áp dụng cho môi trường khác. Import cũng có precedence riêng: tài liệu được import có thể ưu tiên cao hơn tài liệu khai báo import khi key trùng nhau.

Đừng thêm import mà không hiểu ai sở hữu giá trị cuối cùng.

## 14. spring.config.name có thể thay basename

Spring Boot mặc định tìm tên `application`. Nhưng process có thể chạy:

~~~bash
java -jar app.jar --spring.config.name=catalog
~~~

Khi đó file cấu hình được tìm có thể theo basename `catalog` thay vì những file `application-*.yml` mà developer đang sửa.

Khi profile có vẻ không tác dụng:

1. Kiểm tra `spring.config.name` có được cấp không.
2. Kiểm tra các basename thực tế trong Config Data locations.
3. Xác định profile suffix.
4. Kiểm tra file trong artifact và external directories.
5. Xem các nguồn cao hơn có ghi đè key không.

Không nên kết luận Binder lỗi chỉ vì file `application-prod.yml` không được dùng trong một ứng dụng đã đổi config name.

## 15. location và additional-location khác nhau

`spring.config.location` chỉ định vị trí tìm Config Data, có thể thay tập locations mặc định theo cơ chế Boot. `spring.config.additional-location` thêm locations ngoài các vị trí mặc định.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment-config/
~~~

Nếu một hệ thống cấp `spring.config.location` chỉ trỏ tới external directory, các file classpath mặc định có thể không còn được tìm như bạn tưởng.

Lưu ý:

- Những property điều khiển search locations cần được cấp sớm khi Spring Boot bootstrap.
- `file:./...` là đường dẫn phụ thuộc working directory.
- `classpath:` là resource trên classpath.
- `optional:` cho phép location thiếu trong những trường hợp hỗ trợ, không làm giá trị bắt buộc trở thành optional về mặt nghiệp vụ.
- Một location khác có thể kéo theo profile-specific variants với precedence riêng.

Nếu chuyển cơ chế nạp, hãy test cả các trường hợp key trùng; không chỉ test file có tồn tại.

## 16. @PropertySource không đáng tin cậy để chọn profile

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:profiles.properties")
class ProfileSelectorConfiguration {}
~~~

Trong resource:

~~~properties
spring.profiles.active=prod
~~~

`@PropertySource` được xử lý trong giai đoạn ApplicationContext refresh, thường **quá muộn** để tác động đáng tin cậy tới những quyết định Boot đã đưa ra khi tìm Config Data và profile-specific documents.

Muốn chọn profile cần cung cấp từ nguồn bootstrap phù hợp như CLI, environment, Java system property hoặc tài liệu chung hợp lệ.

Việc cuối cùng Environment có một key `spring.profiles.active` không nhất thiết chứng minh profile-specific files đã được Boot nạp từ đầu. Cần kiểm tra thứ tự lifecycle chứ không chỉ nhìn một property.

## 17. Có profile active nhưng giá trị vẫn sai do precedence

Ví dụ file prod:

~~~yaml
# application-prod.yml
app:
  timeout: 3s
~~~

Nhưng chạy:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.timeout=1s
~~~

Command-line argument `--app.timeout=1s` thường ưu tiên hơn Config Data nên giá trị cuối có thể là 1s. Profile prod đã được kích hoạt và file prod có thể đã được nạp đúng.

Các nguồn có thể ảnh hưởng:

- Command line.
- Java system properties.
- OS environment variables.
- `SPRING_APPLICATION_JSON`.
- Config Data imports.
- File theo profile khác đang cùng active.
- Tệp ở search location ưu tiên cao hơn.
- Test property sources.

Khi giá trị không khớp, hãy truy tìm **một key cụ thể** thay vì khẳng định toàn bộ profile không chạy.

## 18. Nhiều profile và last-wins

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=dev,metrics
~~~

Có thể nạp cả `application-dev.yml` và `application-metrics.yml`.

Ví dụ:

~~~yaml
# application-dev.yml
app:
  mode: "development"
~~~

~~~yaml
# application-metrics.yml
app:
  mode: "metrics"
~~~

Trong những tình huống profile-specific Config Data cùng location group, profile đứng sau có thể có precedence cao hơn theo quy tắc last-wins. Nhưng imports, location groups và nguồn CLI/env có thể thay đổi giá trị cuối.

Không dựa vào thứ tự file trong IDE, timestamp hoặc thứ tự chữ cái. Kiểm tra thứ tự PropertySources thực và typed bean.

## 19. List bị thay thế có thể bị nhầm với “profile không nạp”

File chung:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: "backup"
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

File dev:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9090"
~~~

Với `List<Endpoint>`, khi list dev thắng, List mới thường thay toàn bộ List chung. Nó có thể chỉ còn một phần tử; `timeout` của local **không tự kế thừa** từ phần tử primary.

Đây có thể là dấu hiệu **profile hoạt động đúng**, nhưng cấu hình mới chưa đầy đủ. Nếu có `@NotNull Duration timeout` và nested validation, startup có thể thất bại.

Nếu muốn override theo tên/ID mà vẫn giữ các field của nguồn thấp, cân nhắc `Map<String, Endpoint>` thay vì List. Nhưng với List có thứ tự nghiệp vụ, cần khai báo toàn bộ sequence có hiệu lực ở profile mới.

## 20. Map có thể kết hợp key từ nhiều nguồn

Ví dụ:

~~~yaml
# application.yml
clients:
  endpoints:
    billing:
      url: "https://billing.example.invalid"
      timeout: 3s
    inventory:
      url: "https://inventory.example.invalid"
      timeout: 5s
~~~

Dev:

~~~yaml
# application-dev.yml
clients:
  endpoints:
    billing:
      url: "http://localhost:9090"
~~~

Nếu Java bind Map nested objects, entry billing có thể nhận URL dev, timeout từ common và entry inventory còn lại từ common.

Một property thiếu trong YAML dev **không tự chứng minh field sẽ null**; phải xét kiểu Java, map merge, defaults và các property sources. Quy tắc này khác List replacement. Vì thế, việc đọc một file đơn lẻ không đủ để dự đoán cấu hình đã bind.

## 21. @Profile điều khiển bean, không nạp YAML

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
class ProductionClientConfiguration {
}
~~~

Nếu prod không active, configuration class này không được đăng ký theo condition. Nhưng nếu prod active mà bean vẫn thiếu, cần kiểm tra:

- Class có được component scan/import không?
- Module/JAR có nằm trên classpath không?
- Có `@ConditionalOnProperty` hoặc điều kiện khác không?
- Có auto-configuration hoặc `@ConditionalOnMissingBean` liên quan không?
- Có lỗi tạo bean trước đó không?
- Bean được định nghĩa ở config class cha bị condition loại không?

Đừng chỉ sửa file `application-prod.yml` khi lỗi là class không được scan.

## 22. @ConditionalOnProperty không phải @Profile

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "billing",
    name = "enabled",
    havingValue = "true"
)
BillingClient billingClient() {
    return new BillingClient();
}
~~~

Bean phụ thuộc giá trị hiệu lực của `billing.enabled`. Dù prod active, nếu có CLI:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --billing.enabled=false
~~~

thì bean có thể không xuất hiện. Hãy xác minh source thắng cho `billing.enabled` thay vì khẳng định prod không active.

## 23. Sai prefix hoặc indent

YAML:

~~~yaml
billing:
  client:
    endpoint: "https://billing.example.invalid"
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(URI endpoint) {}
~~~

Java tìm `billing.endpoint`, YAML cung cấp `billing.client.endpoint`. Profile có thể đã active nhưng Binder không có giá trị đúng key.

Sửa thành:

~~~java
@ConfigurationProperties(prefix = "billing.client")
public record BillingProperties(URI endpoint) {}
~~~

hoặc đổi cấu trúc YAML theo schema thật.

Đặt `@Validated` và constraint required như `@NotNull` giúp phát hiện thiếu property lúc startup. Cần đăng ký typed configuration bean bằng `@EnableConfigurationProperties` hoặc scanning phù hợp.

## 24. Khi có cả .properties và .yml cùng basename

Nếu cùng một location có:

~~~text
application-prod.properties
application-prod.yml
~~~

Spring Boot có thứ tự ưu tiên giữa những định dạng này; trong tình huống cùng location, `.properties` thường được ưu tiên hơn YAML. Một key tồn tại trong properties có thể che key developer vừa sửa trong YAML.

Không nên giữ hai định dạng cùng chức năng nếu không có lý do. Nếu phải giữ, xác định ownership từng key, test giá trị cuối và xem cả nội dung trong JAR.

Timestamp sửa file không xác định thứ tự nguồn trong Spring Boot.

## 25. Kiểm tra resource thật trong JAR

Dùng:

~~~bash
jar tf build/libs/application.jar
~~~

hoặc:

~~~bash
jar tf target/application.jar
~~~

Trong Spring Boot executable JAR, resource thường xuất hiện theo dạng:

~~~text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-prod.yml
~~~

Nếu file thiếu:

- Có thể chỉ nằm trong `src/test/resources`.
- Build có exclude/resource filtering.
- Ứng dụng chạy module/JAR khác.
- Container image chưa rebuild.
- Path/classpath không như IDE.
- File có tên khác hoặc case khác.

Nếu file do deployment mount ngoài JAR, cần kiểm tra volume và filesystem runtime thay vì tìm nó trong artifact.

## 26. Quan sát active/default profiles trong ứng dụng

Một cách chẩn đoán đơn giản:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ProfileDiagnostics {

    @Bean
    ApplicationRunner printProfiles(Environment environment) {
        return args -> {
            System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
            );
            System.out.println(
                "Default profiles: " +
                Arrays.toString(environment.getDefaultProfiles())
            );
        };
    }
}
~~~

Không đưa secret vào log. Code chạy sau khi context được tạo nên không giúp trực tiếp khi ứng dụng fail trong Config Data bootstrap. Trường hợp startup sớm cần đọc exception, location diagnostics hoặc viết test bootstrap.

## 27. Tìm nguồn nào chứa key nhưng không in giá trị

Với `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

String key = "catalog.timeout";

for (PropertySource<?> source :
        environment.getPropertySources()) {
    if (source.containsProperty(key)) {
        System.out.println(source.getName());
    }
}
~~~

Đoạn code giả định `environment` được inject là `ConfigurableEnvironment`. Thứ tự sources trong Environment giúp phân tích key nào có thể thắng. Đối với OS environment và relaxed property binding, việc tra cứu trực tiếp key canonical có thể khác Binder; cần dùng công cụ phù hợp nếu key không được nhìn thấy như mong đợi.

Không in raw values hoặc toàn bộ Environment vì có thể chứa password, token, đường dẫn nhạy cảm. Tên PropertySource cũng có thể lộ thông tin hệ thống; chỉ bật diagnostics ở nơi được kiểm soát.

## 28. Actuator và log chẩn đoán

Với Actuator đã được bảo vệ, `/actuator/env` có thể giúp xem property sources, `/actuator/configprops` giúp xem typed configuration bean đã bind. Không public chúng hoặc bật show-values rộng ở production để debug.

Để quan sát Config Data loading trong local/test, có thể dùng:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Logger này có thể ghi hoạt động liên quan Config Data theo phiên bản Boot. Cờ `--debug` hữu ích cho condition evaluation report nhưng **không tương đương** bật TRACE toàn bộ Config Data.

Chỉ bật log trong thời gian cần, tránh dump secret và đưa về mức bình thường sau khi xác định sự cố.

## 29. InvalidConfigDataPropertyException

Đặt `spring.profiles.active` trong `application-prod.yml` hoặc `spring.profiles.include` trong tài liệu có `on-profile` có thể bị Spring Boot từ chối với lỗi thuộc nhóm:

~~~text
InvalidConfigDataPropertyException
~~~

Khi nhìn thấy lỗi này, xem document và source location được framework báo. Sửa **vị trí các key điều khiển profile**, không tắt Bean Validation.

Nếu project đã nâng cấp từ phiên bản Boot cũ, những tài liệu dùng cách kích hoạt profile lịch sử như `spring.profiles: dev` cần được xem lại, chuyển sang `spring.config.activate.on-profile` theo cơ chế Config Data hiện đại.

## 30. Kiểm thử profile bằng @ActiveProfiles

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class CatalogDevTest {

    @Autowired
    CatalogProperties properties;

    @Test
    void loadsDevConfiguration() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofSeconds(1));
        assertThat(properties.diagnosticMode())
            .isTrue();
    }
}
~~~

Typed properties:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        URI endpoint,
        Duration timeout,
        boolean diagnosticMode
) {}
~~~

Để test hoạt động, CatalogProperties phải được đăng ký; test/application resources phải tương ứng với ví dụ. Có thể cần imports JUnit/AssertJ/Spring Test như trong dự án.

Nhớ rằng `@ActiveProfiles("dev")` trong test không chứng minh pod production active dev. Test còn có những nguồn như `@TestPropertySource`, `@SpringBootTest(properties=...)` và `@DynamicPropertySource` có thể override Config Data. Assert bean value để xác định kết quả, không chỉ assert tên active profile.

## 31. Test lỗi sai tài liệu phải chạy Config Data bootstrap thật

Nếu muốn chứng minh Spring Boot từ chối file:

~~~yaml
# application-prod.yml — fixture cố tình sai
spring:
  profiles:
    active: "prod"
~~~

thì test phải **nạp file này thông qua cơ chế Config Data bootstrap** với prod active từ nguồn hợp lệ.

Một `ApplicationContextRunner.withPropertyValues(...)` chỉ cấp raw properties và không tự kiểm tra cách Boot parse/activate một YAML document. Dùng integration/bootstrap test với fixture tách biệt, xác minh startup failure thuộc nhóm Config Data error. Test đúng phải pass ở mức JUnit khi xác nhận failure dự kiến.

Không đưa file cố tình sai vào resources chính làm những test khác vô tình fail.

## 32. @SpringBootTest và ApplicationContextRunner phục vụ mục tiêu khác nhau

`@SpringBootTest` phù hợp để chạy context tích hợp với profile và file thực, sau đó assert giá trị bind.

`ApplicationContextRunner` phù hợp để test Binder, validation và conditions trong context nhỏ. Nếu chỉ viết:

~~~java
new ApplicationContextRunner()
    .withPropertyValues(
        "catalog.timeout=2s"
    )
    .run(context -> {
        // assert
    });
~~~

thì chưa chứng minh `application-dev.yml` đã được tìm và nạp đúng.

Với một lỗi bootstrap như missing Config Data import hoặc invalid profile property location, nên tạo bootstrap fixture thực, không dựa vào một runner cấp property values trực tiếp.

## 33. Docker/Kubernetes: thay file không tự đổi profile của process cũ

Ví dụ một phần Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: registry.example.invalid/catalog:release
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
~~~

Đây chỉ là ví dụ cấu trúc, không phải manifest production đầy đủ.

Nếu sửa manifest nhưng pod cũ vẫn chạy, process Java không tự nhận biến mới. Kiểm tra apply/rollout, Deployment revision, pod template, image digest, runtime environment và startup logs.

Tương tự, cập nhật file ConfigMap hoặc Secret được mount không bảo đảm Spring Boot tự chọn lại profile hay rebind toàn bộ beans. Với quyết định bootstrap, restart/rollout có kiểm soát thường dễ kiểm chứng hơn.

## 34. Bảng triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| No active profile | Chưa cấp active profile | CLI, env, JVM args |
| File prod không tác dụng | Prod không active hoặc file không được tìm | Tên file, JAR, locations |
| Invalid Config Data property | active/include đặt sai document | Chuyển sang common/runtime |
| on-profile không hoạt động | Sai expression/document/indent | Kiểm tra root key, --- |
| Profile active nhưng value khác | Nguồn khác override | PropertySources |
| List bị mất phần tử | List replacement | Kiểm tra type và list sau binding |
| Bean @Profile vắng mặt | Điều kiện hoặc registration sai | Scan, auto-config conditions |
| @ConfigurationProperties field null | Wrong prefix/field thiếu | Binding và validation |
| Chỉ IDE chạy sai | VM/program args, cwd khác | Run configuration |
| Cluster dùng profile cũ | Process/revision cũ | Rollout/pod inspection |
| Import file không tồn tại | Wrong path/cwd hoặc optional | Config Data locations |
| Sửa YAML không thay value | .properties cùng location hoặc import thắng | Precedence theo key |

## 35. Quy trình chẩn đoán gợi ý

1. Xác định đúng process/JAR/pod/revision.
2. Đọc active/default profiles tại runtime nếu context khởi động được.
3. Kiểm tra command line, environment và JVM system properties.
4. Xem `spring.config.name/location/additional-location`.
5. Kiểm tra đúng file/profile suffix và nội dung artifact.
6. Kiểm tra `---` và `spring.config.activate.on-profile` ở từng document.
7. Di chuyển các profile-control keys khỏi profile-specific documents.
8. Xem `spring.config.import`, `optional:` và đường dẫn file.
9. Xác định PropertySource thắng key đang có vấn đề.
10. Xác minh typed bean đã bind, nhất là List/Map và defaults.
11. Kiểm tra `@Profile`/`@ConditionalOnProperty`/component scan.
12. Bổ sung integration hoặc bootstrap regression test.
13. Triển khai lại và xác minh process mới nhận đúng giá trị.
14. Không log secret hay mở Actuator cho người không có quyền.

## 36. Bài tập tổng hợp

Có ba file:

~~~yaml
# application.yml
app:
  mode: "base"
  retry-count: 2
~~~

~~~yaml
# application-dev.yml
app:
  mode: "development"
  retry-count: 1
~~~

~~~yaml
# application-prod.yml — cố tình sai
spring:
  profiles:
    active: "prod"

app:
  mode: "production"
  retry-count: 3
~~~

**Câu hỏi 1:** Chạy `--spring.profiles.active=dev` có tự nạp prod không?

**Đáp:** Không. File prod không được chọn chỉ vì tồn tại.

**Câu hỏi 2:** Vì sao file prod sai?

**Đáp:** `spring.profiles.active` nằm trong profile-specific file; phải chuyển sang nguồn chung hợp lệ hoặc cấp từ runtime.

**Câu hỏi 3:** Sau khi sửa, active prod và thêm `--app.retry-count=9` thì retryCount có thể là gì?

**Đáp:** 9 từ command-line override theo precedence thông thường.

**Câu hỏi 4:** Đổi tên file prod thành `application-production.yml` nhưng chỉ active `prod` thì sao?

**Đáp:** Boot không tự coi hai suffix là giống nhau.

**Câu hỏi 5:** Bean `@Profile("prod")` không xuất hiện dù prod active, cần kiểm tra gì?

**Đáp:** Component scan, registration, other conditions, classpath và startup errors.

**Câu hỏi 6:** Dev List ghi một phần tử thay List chung hai phần tử. Có chắc profile không hoạt động không?

**Đáp:** Không. Đây có thể là hành vi List replacement của Binder khi profile hoạt động đúng.

**Bài tập thực hành:** sửa file prod, viết `AppProperties` typed bean, test dev/prod, test CLI override và tạo một bootstrap fixture chứa key activation ở sai document để xác nhận lỗi startup được xử lý có kiểm soát.

## 37. Tổng kết

Chẩn đoán “profile không được kích hoạt” trong Spring Boot không chỉ là kiểm tra dòng `spring.profiles.active`. Phải phân biệt:

- **Kích hoạt profile:** `spring.profiles.active/default/include/group` từ nguồn hợp lệ.
- **Chọn YAML document:** `spring.config.activate.on-profile`, với dấu phân tách `---` và biểu thức đúng.
- **Tìm Config Data:** basename, profile suffix, locations, imports và artifact thật.
- **Thứ tự ưu tiên:** CLI/env/system properties và các tài liệu có thể che giá trị của nhau.
- **Binding:** prefix, kiểu dữ liệu, List replacement, Map merging và validation.
- **Bean creation:** `@Profile`, `@ConditionalOnProperty`, classpath và scanning.

Không đặt profile-control properties trong profile-specific document hoặc document được kích hoạt có điều kiện. Không kết luận file không được nạp chỉ vì một key nhận giá trị khác. Hãy xác minh profile thực, file thực, source thắng và bean hiệu lực; cuối cùng dùng regression test để giữ hành vi ổn định.

**Ghi nhớ:** profile là quyết định ở **bootstrap**, tài liệu được chọn theo **Config Data**, và giá trị cuối phụ thuộc **PropertySource precedence**. Chẩn đoán đúng từng tầng sẽ tránh việc sửa cấu hình mù và giảm rủi ro triển khai nhầm môi trường.
