# Đổi tên thuộc tính mà vẫn quản lý tương thích và lộ trình loại bỏ trong Spring Boot

## 1. Vì sao đổi tên property là một thay đổi có thể phá vỡ triển khai?

Spring Boot đọc cấu hình từ `application.yaml`, `application.properties`, Config Data ngoài JAR, profile, biến môi trường, Java System properties, dòng lệnh và các nguồn cấu hình khác. Một tên như `app.client.request-timeout` không chỉ nằm trong Java code mà còn có thể xuất hiện trong:

- Tệp theo profile như `application-prod.yaml`.
- Helm values, ConfigMap hoặc Kubernetes Deployment.
- Docker Compose và biến môi trường của runtime.
- CI/CD variables hoặc các script khởi chạy.
- Secret/configuration tree được mount thành file.
- Các bài kiểm thử, tài liệu vận hành, template triển khai.
- Một module hoặc hệ thống khác cùng đọc hợp đồng cấu hình.

Giả sử phiên bản cũ dùng:

~~~properties
app.client.request-timeout=5s
~~~

Đội phát triển muốn đổi thành:

~~~properties
app.client.timeout=5s
~~~

Nếu chỉ đổi tên thành viên Java từ `requestTimeout` sang `timeout` và phát hành ngay, hệ thống production vẫn dùng tên cũ có thể không bind được giá trị. Tùy default và validation, ứng dụng có thể khởi động với timeout sai, báo lỗi muộn, hoặc thất bại ngay trong startup.

**Mục tiêu của bài:** thiết kế migration có thời hạn, hỗ trợ tên cũ và mới trong giai đoạn chuyển tiếp, thông báo deprecated, quyết định ưu tiên khi hai tên đồng thời tồn tại, kiểm thử tính tương thích, lập kế hoạch loại bỏ và tránh làm lộ secret.

Ví dụ dùng Spring Boot 3.x, Java 17+, Jakarta Validation và JUnit 5. Mốc version chỉ minh họa, không phải chính sách cụ thể của một dự án.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| Legacy key | Tên property cũ mà deployment hiện tại có thể vẫn sử dụng. |
| Canonical key | Tên mới được khuyến nghị. |
| Alias hoặc compatibility layer | Logic liên kết tên cũ với giá trị mà app cần. |
| Deprecation | Thông báo một tên chưa bị xóa ngay nhưng không nên dùng tiếp. |
| Replacement | Tên mới được khuyến nghị thay thế. |
| Migration | Chuyển code, config, tooling, tài liệu và môi trường runtime. |
| Sunset | Mốc hoặc điều kiện kết thúc hỗ trợ tên cũ. |
| Removal | Loại bỏ hỗ trợ runtime, không chỉ xóa chữ trong tài liệu. |
| PropertySource precedence | Thứ tự ưu tiên giữa những nguồn cùng cung cấp một property. |

**Deprecation metadata không đồng nghĩa runtime alias.** IDE biết tên cũ đã deprecated không bảo đảm Binder tự chuyển `request-timeout` thành `timeout`.

**Relaxed binding cũng không phải alias tùy ý.** Nó cho phép những cách viết liên quan của cùng một tên, nhưng không tự hiểu hai tên khác nghĩa là tương đương.

## 3. Ví dụ xuyên suốt: request-timeout chuyển thành timeout

Phiên bản cũ:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration requestTimeout) {
}
~~~

YAML cũ:

~~~yaml
app:
  client:
    request-timeout: 10s
~~~

Phiên bản mới muốn YAML:

~~~yaml
app:
  client:
    timeout: 10s
~~~

Một hợp đồng chuyển tiếp có thể quy định:

1. Chỉ có `app.client.timeout`: dùng khóa mới.
2. Chỉ có `app.client.request-timeout`: tạm chấp nhận, log warning tên khóa cũ.
3. Cả hai: khóa mới thắng; thông báo cấu hình trùng.
4. Không có cả hai: fail fast nếu timeout bắt buộc; nếu optional, dùng default có tài liệu.
5. Giá trị sai kiểu: báo lỗi rõ ràng, không âm thầm thay bằng một key khác.
6. Sau một giai đoạn chuyển đổi đã công bố: ngừng nhận khóa cũ.

Đây là **chính sách chủ động thiết kế**, không phải hành vi mặc định mà Spring Boot tự chọn cho hai property khác nhau.

## 4. Đổi tên thật khác với thay kiểu chữ

Spring Boot relaxed binding có thể ánh xạ từ tên canonical:

~~~text
app.client.request-timeout
~~~

sang tên Java:

~~~text
requestTimeout
~~~

và từ environment thích hợp:

~~~text
APP_CLIENT_REQUESTTIMEOUT
~~~

Nhưng `app.client.timeout` được bind vào thành viên `timeout`, không phải `requestTimeout`.

Bảng ví dụ:

| Legacy | New | Có cần compatibility logic? |
| --- | --- | --- |
| `app.client.request-timeout` | `app.client.requestTimeout` | Có thể chỉ khác cách viết relaxed binding; phải xác minh ngữ cảnh. |
| `app.client.request-timeout` | `app.client.timeout` | Có, vì tên khác nghĩa. |
| `app.retries` | `app.max-attempts` | Có, đồng thời phải làm rõ ý nghĩa giá trị. |
| `APP_CLIENT_REQUESTTIMEOUT` | `APP_CLIENT_TIMEOUT` | Có khi đổi biến environment thực sự. |

Đừng phát hành alias mới khi chỉ sửa định dạng gạch ngang thành camelCase và Binder đã hỗ trợ đúng cùng một property. Ngược lại, đừng dựa vào relaxed binding để xử lý một đổi tên có nghĩa khác.

## 5. Lập bản đồ mọi hình thức của một property

Khi đổi tên `app.client.request-timeout` thành `app.client.timeout`, cần tìm ở các dạng:

~~~text
application.yaml:
    app.client.request-timeout -> app.client.timeout

environment:
    APP_CLIENT_REQUESTTIMEOUT -> APP_CLIENT_TIMEOUT

JVM system property:
    -Dapp.client.request-timeout=5s
    -> -Dapp.client.timeout=5s

Command line:
    --app.client.request-timeout=5s
    -> --app.client.timeout=5s

Configuration tree filename:
    /run/secrets/app.client.request-timeout
    -> /run/secrets/app.client.timeout
~~~

Quy tắc environment cho canonical `@ConfigurationProperties` thường là chuyển dấu chấm thành `_`, bỏ dấu gạch ngang, viết hoa.

Khi đổi tên một key, hãy kiểm tra:

- Java class và configuration metadata.
- Config Data ở trong và ngoài artifact.
- Profile-specific files.
- Docker/Compose, Kubernetes/Helm.
- ConfigMap key, Secret key, `env.name` và `volume.items.path`.
- CI/CD, systemd, launcher scripts.
- Integration test fixtures.
- Runbook và tài liệu do người vận hành sử dụng.

Không tìm thấy tên cũ trong repository **không chứng minh** deployment runtime đã bỏ nó. Nhiều biến môi trường hoặc Secret được quản lý ở hệ thống khác.

## 6. Thiết kế lớp đầu vào nhận cả hai tên

Một cách đơn giản cho property do ứng dụng sở hữu: tách **raw configuration input** khỏi **settings đã chuẩn hóa**.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientInputProperties(
        Duration timeout,
        Duration requestTimeout) {
}
~~~

Ý nghĩa:

~~~text
timeout         ← app.client.timeout
requestTimeout  ← app.client.request-timeout
~~~

Hai field được bind bằng cơ chế Spring Boot. Trong giai đoạn chuyển tiếp, đừng đặt default lên field mới nếu default sẽ khiến logic bỏ qua giá trị legacy.

Tạo một kiểu chỉ chứa giá trị hợp lệ:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record ClientSettings(Duration timeout) {
}
~~~

Business service chỉ sử dụng `ClientSettings`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteClientService {

    private final ClientSettings settings;

    public RemoteClientService(ClientSettings settings) {
        this.settings = settings;
    }

    public Duration timeout() {
        return settings.timeout();
    }
}
~~~

Nhờ vậy, service không phải biết hai alias, không tự đưa ra lựa chọn khác nhau và không cần thay đổi khi loại bỏ legacy sau này.

## 7. Ví dụ Java hoàn chỉnh: ưu tiên khóa mới

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientInputProperties.class)
public class ClientSettingsConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ClientSettingsConfiguration.class);

    @Bean
    ClientSettings clientSettings(ClientInputProperties input) {

        if (input.requestTimeout() != null) {
            log.warn(
                "Property 'app.client.request-timeout' is deprecated; "
                + "use 'app.client.timeout'");
        }

        if (input.timeout() != null
                && input.requestTimeout() != null) {
            log.warn(
                "Both legacy and canonical timeout properties are set; "
                + "'app.client.timeout' takes precedence");
        }

        Duration selected = input.timeout() != null
                ? input.timeout()
                : input.requestTimeout();

        if (selected == null) {
            throw new IllegalStateException(
                "Missing app.client.timeout "
                + "(legacy app.client.request-timeout still supported)");
        }

        if (selected.isZero() || selected.isNegative()) {
            throw new IllegalStateException(
                "app.client.timeout must be positive");
        }

        return new ClientSettings(selected);
    }
}
~~~

Cơ chế:

1. Khi class input được đăng ký, Binder tạo object chứa `timeout` và `requestTimeout` tương ứng với các key có mặt.
2. Nếu có legacy field, log warning về **tên khóa**, không in giá trị.
3. Nếu có cả hai, log conflict và chọn canonical field.
4. Nếu chỉ old có mặt, tạm sử dụng old.
5. Nếu cả hai thiếu, chặn startup.
6. Nếu Duration bằng 0 hoặc âm, từ chối.

### Không đăng ký trùng bean

Ví dụ dùng `@EnableConfigurationProperties(ClientInputProperties.class)` ở configuration class. Nếu dự án đã có `@ConfigurationPropertiesScan`, cần chọn cách đăng ký rõ ràng để tránh vô tình tạo nhiều bean cùng mục đích.

### Không làm business layer phụ thuộc legacy

Code nghiệp vụ không nên tự viết:

~~~java
Duration timeout = old != null ? old : newer;
~~~

ở nhiều nơi. Làm vậy có thể khiến service A chọn old, service B chọn new khi cả hai tồn tại. Chỉ nên có **một compatibility resolver** làm nguồn quyết định.

## 8. Sai lầm lớn: đặt @DefaultValue quá sớm

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientInputProperties(
        @DefaultValue("5s") Duration timeout,
        Duration requestTimeout) {
}
~~~

Giả sử môi trường cũ khai báo:

~~~properties
app.client.request-timeout=30s
~~~

Khi Binder tạo record, `timeout` có thể nhận mặc định 5 giây vì khóa mới thiếu. Resolver thấy `timeout != null` rồi chọn 5 giây, bỏ qua 30 giây từ legacy.

Đây là **thay đổi ngữ nghĩa ngoài ý muốn** ngay trong giai đoạn hứa tương thích.

Nếu muốn có default khi cả hai tên thiếu, chọn alias trước:

~~~java
Duration chosen = input.timeout() != null
        ? input.timeout()
        : input.requestTimeout();

if (chosen == null) {
    chosen = Duration.ofSeconds(5);
}
~~~

Hoặc báo lỗi nếu không được dùng default.

**Nguyên tắc:** default thuộc hợp đồng của **giá trị sau chuẩn hóa**, không nên khiến field canonical bị coi là “có giá trị do người triển khai cấp” trước khi xét legacy.

## 9. Thứ tự nguồn và thứ tự tên là hai khái niệm khác nhau

Spring Boot có thứ tự ưu tiên `PropertySource`. Nhưng hai tên:

~~~text
app.client.timeout
app.client.request-timeout
~~~

là hai property riêng biệt.

Ví dụ:

~~~yaml
# application.yaml
app:
  client:
    timeout: 3s
~~~

Container environment:

~~~text
APP_CLIENT_REQUESTTIMEOUT=20s
~~~

Nếu resolver của bài chọn **canonical luôn thắng**, kết quả là **3s**, dù legacy value đến từ environment có ưu tiên cao hơn YAML.

Vì sao? Binder xác định giá trị từng property, rồi code mới quyết định ưu tiên giữa **hai tên**.

### Ba chính sách có thể chọn

**A. New name always wins**

- Dễ giải thích, thuận lợi cho migration.
- Cần cảnh báo nếu old và new cùng xuất hiện.
- Có thể vượt thứ tự PropertySource giữa hai tên.

**B. Source precedence wins**

- Alias từ nguồn ưu tiên cao được chọn trước alias từ nguồn thấp.
- Cần resolver chuyên biệt duyệt các nguồn và xử lý relaxed binding đúng cách.
- Phức tạp hơn nhiều, phải test CLI/env/YAML/configtree.

**C. Both names is an error**

- Không cho phép mâu thuẫn khi cả hai có mặt.
- Hợp lý cho endpoint bảo mật, secret hoặc cấu hình rất quan trọng.
- Cần kế hoạch rollout cẩn thận để tránh startup fail trong thời gian quá độ.

Không có quy tắc mặc định “alias mới luôn thắng” do Spring Boot tự suy ra. Hãy chọn một chính sách và **ghi thành test**.

## 10. Conversion của cả hai field có thể làm app thất bại

Ví dụ:

~~~properties
app.client.timeout=3s
app.client.request-timeout=not-a-duration
~~~

Class input sử dụng:

~~~java
public record ClientInputProperties(
        Duration timeout,
        Duration requestTimeout) {
}
~~~

Binder thường cố bind **cả hai Duration** khi tạo record. Legacy field sai kiểu có thể làm bước binding thất bại **trước khi** bean method chọn 3s.

Nếu hợp đồng yêu cầu “có canonical thì legacy sai cũng phải được bỏ qua”, cần thay đổi kiến trúc:

1. Xác định tên được chọn ở tầng nguồn trước khi convert.
2. Chỉ convert giá trị đã chọn theo conversion service/Binder phù hợp.
3. Ghi warning nhưng không buộc convert legacy không dùng.
4. Kiểm thử các tình huống old-bad/new-good và old-good/new-bad.

Đừng chỉ thêm `if (timeout != null)` rồi giả định lỗi conversion từ một field khác sẽ biến mất.

### Chính sách chặt chẽ

Trong nhiều ứng dụng, thất bại khi **bất kỳ khóa đã khai báo nào có giá trị sai kiểu** cũng là lựa chọn hợp lý: cấu hình cũ bị bỏ quên phải được dọn sạch thay vì vô tình che lỗi.

Quan trọng là **công bố và kiểm thử**, không phải mặc định một cách xử lý áp dụng cho mọi sản phẩm.

## 11. @Value nested fallback là một lựa chọn giới hạn

Một cách gọn cho scalar:

~~~java
@Value("${app.client.timeout:${app.client.request-timeout:5s}}")
private Duration timeout;
~~~

Ý tưởng: thử new, nếu không tồn tại thử old, cuối cùng dùng 5s.

Nhưng cách này có những giới hạn:

- Không thông báo deprecated tự động.
- Không có báo xung đột khi cả hai tên được cấp.
- Dễ dùng ngược thứ tự nếu viết legacy trước.
- Giá trị String rỗng có mặt có thể khác thiếu key.
- Khó tái sử dụng với nhiều field, nested object và List/Map.
- Không mang metadata migration và lộ trình removal.
- Đường conversion có thể phụ thuộc cấu hình conversion service.

Nếu app có một hệ thống cấu hình lớn, nên ưu tiên `@ConfigurationProperties` và normalizer có test.

## 12. Metadata deprecation hỗ trợ IDE, không tự tạo alias

Spring Boot có cấu hình metadata để công cụ biết:

- Tên property canonical.
- Kiểu Java.
- Mô tả, default và hints.
- Tên nào đã deprecated, vì sao và thay bằng key gì.

Khi metadata đánh dấu:

~~~text
app.client.request-timeout
    deprecated
    replacement = app.client.timeout
~~~

IDE có thể hiển thị cảnh báo. Nhưng Spring Boot Binder không mặc nhiên lấy metadata đó làm quy tắc đổi tên runtime cho property tự định nghĩa.

Phải phân biệt ba lớp:

| Lớp | Vai trò |
| --- | --- |
| Runtime compatibility | Code thực sự nhận old key và new key. |
| IDE metadata | Tooling biết old key deprecated và replacement. |
| Documentation + rollout | Người vận hành biết khi nào phải đổi, và ai chịu trách nhiệm. |

Migration hoàn chỉnh cần cả ba.

## 13. @DeprecatedConfigurationProperty với JavaBean getter

Spring Boot có annotation:

~~~java
org.springframework.boot.context.properties.DeprecatedConfigurationProperty
~~~

Một ví dụ JavaBean:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private Duration requestTimeout;

    @Deprecated
    @DeprecatedConfigurationProperty(
            reason = "Use app.client.timeout",
            replacement = "app.client.timeout")
    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

Annotation `@DeprecatedConfigurationProperty` được dùng trên getter để sinh thông tin deprecated trong metadata qua configuration processor. `@Deprecated` của Java là một thông điệp khác hướng tới API Java.

**Không tự động:**

- Chuyển `request-timeout` thành `timeout` khi binding.
- Đưa cảnh báo deprecation ra startup log theo mọi trường hợp.
- Ngăn property bị dùng khi đến mốc sunset.

Metadata và enforcement cần được xử lý riêng.

### Record thì sao?

Record component có accessor như `requestTimeout()` chứ không phải getter JavaBean `getRequestTimeout()`. Khi muốn deprecation metadata rõ ràng cho record hoặc property không thuận tiện đặt annotation, có thể cung cấp **additional metadata** trực tiếp.

## 14. additional-spring-configuration-metadata.json

Tệp:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "app.client.request-timeout",
      "type": "java.time.Duration",
      "description": "Legacy client timeout; use app.client.timeout.",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed to simplify the client configuration API.",
        "replacement": "app.client.timeout"
      }
    }
  ]
}
~~~

Trong metadata Spring Boot:

- `name` là key cũ canonical.
- `type` mô tả kiểu dữ liệu.
- `deprecation.level` mô tả mức cảnh báo cho tooling.
- `deprecation.reason` nói rõ lý do.
- `deprecation.replacement` chỉ tên mới.

Mức `warning` hoặc `error` trong metadata dành cho công cụ. Nó **không tự chuyển thành Java exception lúc runtime**. Nếu muốn cấm key cũ sau khi hết hỗ trợ, phải xây guard/validation ở runtime hoặc một cơ chế migration có kiểm thử.

### Configuration processor

Gradle Groovy:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven có thể cấu hình dependency và annotation processing phù hợp với plugin hiện tại:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Cần xác nhận build thật sự chạy annotation processor và tạo metadata:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Tooling không nhất thiết đọc file additional nằm trong repository nếu nó chưa được đưa vào artifact/classpath phù hợp. Test hoặc kiểm tra build output là bước tách biệt với kiểm thử runtime alias.

## 15. Không nhầm spring-boot-properties-migrator với alias tùy chỉnh

Trong một số quá trình nâng cấp phiên bản Spring Boot, công cụ:

~~~text
org.springframework.boot:spring-boot-properties-migrator
~~~

có thể hỗ trợ tìm những property Boot đã được đổi tên/loại bỏ theo metadata tương ứng và tạm hỗ trợ một số tình huống migration.

Ví dụ Maven dependency tạm thời:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Không nên suy luận rằng công cụ này sẽ **tự nhận mọi cặp tên ứng dụng tự đặt**, ví dụ `app.client.request-timeout` → `app.client.timeout`. Phải kiểm chứng đúng phiên bản và cặp key cụ thể.

Công cụ migrator không thay thế:

- Runtime compatibility code của ứng dụng.
- Metadata deprecation cho property tự định nghĩa.
- Việc cập nhật các file deployment ngoài repository.
- Unit/integration tests cho nguồn cấu hình.
- Kế hoạch gỡ hỗ trợ legacy.

Khi hoàn tất nâng cấp Boot, nên tháo dependency migrator tạm theo hướng dẫn phiên bản đang dùng, không biến nó thành một cơ chế tương thích vĩnh viễn không được theo dõi.

## 16. @Name không phải danh sách legacy alias

Annotation `@Name` trong binding API có thể chỉ định tên một parameter/property khi tên Java không phù hợp:

~~~java
import org.springframework.boot.context.properties.bind.Name;

public record ImportOptions(
        @Name("import") String importLocation) {
}
~~~

Điều đó không có nghĩa một field có thể nhận đồng thời vô số tên cũ và mới kèm deprecation, ưu tiên và sunset. `@Name` chủ yếu chỉ định tên binding cho vị trí sử dụng, không phải một cơ chế migration tổng thể.

Đừng dùng `@Name("timeout")` rồi giả định `request-timeout` tự được hỗ trợ tiếp.

## 17. EnvironmentPostProcessor: chỉ dùng khi thật sự cần

`EnvironmentPostProcessor` là điểm mở rộng Spring Boot cho phép can thiệp `Environment` trong quá trình startup, hữu ích nếu cần một lớp alias chung cho nhiều cấu hình.

Tuy nhiên, nó phải xử lý nhiều chi tiết:

1. Chạy vào thời điểm phù hợp với Config Data.
2. Đọc property từ YAML/env/CLI/system property.
3. Hiểu thứ tự nguồn và canonical names.
4. Phân giải khi old/new cùng tồn tại.
5. Không làm property mới bị một alias nguồn thấp ghi đè.
6. Không lộ secret khi log.
7. Không đụng vào cấu hình không liên quan.

**Anti-pattern:** đọc legacy value rồi đưa một alias MapPropertySource ưu tiên cao nhất mà không kiểm tra new key. Cách đó có thể làm giá trị mới bị ghi đè ngay cả khi người vận hành chủ động đặt canonical key.

Với chỉ một key do ứng dụng kiểm soát, dual binding và normalizer như phần 6–7 thường dễ bảo trì và dễ test hơn.

### Khi cần preserve source precedence

Có thể phải duyệt từng `PropertySource` theo thứ tự ưu tiên, kiểm tra tên old/new và chuyển canonical name theo chính sách. Đây là một thuật toán riêng; nên có test phủ:

- New key ở YAML, old key ở env.
- Old key ở YAML, new key ở env.
- New key ở CLI, old key ở config tree.
- Hai tên trong cùng một nguồn.
- Value rỗng, value sai kiểu, duplicate.

Không chỉ dùng một test cùng file properties rồi kết luận logic tương thích với mọi môi trường.

## 18. Cẩn thận khi đổi cả kiểu và đơn vị

Đổi tên thuần túy:

~~~text
app.client.request-timeout = 5s
    ->
app.client.timeout = 5s
~~~

khác với đổi đồng thời biểu diễn dữ liệu:

~~~text
app.client.timeout-ms = 5000
    ->
app.client.timeout = 5s
~~~

Nếu người vận hành copy `5000` sang tên mới, họ có thể nhận kết quả khác nếu parser hoặc đơn vị mặc định thay đổi.

Khi đổi đơn vị:

- Ghi rõ giá trị cũ diễn đạt theo milliseconds hay seconds.
- Ghi rõ cú pháp mới: `500ms`, `5s`, `PT5S`.
- Tránh dùng số trần mơ hồ.
- Tạo conversion cho dữ liệu legacy nếu cần.
- Test những giá trị biên, 0, âm, lớn bất thường và overflow.
- Cập nhật sample config và runbook.

Một migration đúng phải bảo toàn **ý nghĩa**, không chỉ thay tên property.

## 19. Đổi tên List, Map hoặc prefix lớn

Ví dụ:

~~~text
app.targets
    ->
app.client.endpoints
~~~

Cả hai là List. Khi muốn hỗ trợ song song, bạn có thể bind hai property riêng rồi chọn:

~~~text
new list có dữ liệu -> dùng new list
ngược lại old list -> dùng old list
không có cả hai -> chính sách missing
~~~

Đừng tự nối hai list nếu không có hợp đồng merge rõ ràng. Bản thân Spring Boot thường **thay thế List** từ nguồn ưu tiên cao, không merge phần tử giữa nguồn.

Với Map hoặc nested object, gộp một phần field từ old prefix và một phần từ new prefix có thể tạo cấu hình “lai” nguy hiểm, nhất là endpoints, TLS và credentials. Cân nhắc chọn toàn bộ object mới/cũ hoặc từ chối cấu hình một phần.

### Khi đổi cả prefix

~~~text
legacy.billing.endpoint   -> payments.billing.endpoint
legacy.billing.timeout    -> payments.billing.timeout
legacy.billing.client-id  -> payments.billing.client-id
legacy.billing.secret     -> payments.billing.secret
~~~

Lập bảng từng trường:

| Old key | New key | Type | Default | Required | Lưu ý |
| --- | --- | --- | --- | --- | --- |
| `legacy.billing.endpoint` | `payments.billing.endpoint` | URI | Không | Có | Đừng đổi host ngoài ý muốn |
| `legacy.billing.timeout` | `payments.billing.timeout` | Duration | 5s nếu hợp lệ | Không | Đơn vị rõ ràng |
| `legacy.billing.client-id` | `payments.billing.client-id` | String | Không | Có | Không log giá trị |
| `legacy.billing.secret` | `payments.billing.secret` | String/secret | Không | Có | Rotation/permissions riêng |

Một prefix rename có thể ảnh hưởng nhiều nhóm không cùng vòng phát hành; càng cần compatibility window.

## 20. Test migration với ApplicationContextRunner

Dùng các class `ClientInputProperties`, `ClientSettings` và `ClientSettingsConfiguration` ở phần trước.

~~~java
package com.example.demo.config;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ClientSettingsMigrationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    ClientSettingsConfiguration.class);

    @Test
    void usesCanonicalProperty() {
        runner.withPropertyValues(
                "app.client.timeout=3s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
    }

    @Test
    void temporarilyAcceptsLegacyProperty() {
        runner.withPropertyValues(
                "app.client.request-timeout=7s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(7));
            });
    }

    @Test
    void canonicalWinsWhenBothPresent() {
        runner.withPropertyValues(
                "app.client.timeout=3s",
                "app.client.request-timeout=7s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
    }

    @Test
    void missingBothFails() {
        runner.run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void rejectsZeroValue() {
        runner.withPropertyValues(
                "app.client.timeout=0ms")
            .run(context ->
                assertThat(context).hasFailed());
    }
}
~~~

Bộ test này chứng minh runtime compatibility cho một context nhỏ; không tự chứng minh file profile hoặc Kubernetes env được nạp đúng. Cần thêm test đúng nguồn thực tế.

### Test không nên chỉ kiểm tra bean tồn tại

~~~java
assertThat(context).hasSingleBean(ClientSettings.class);
~~~

chưa chứng minh app chọn đúng timeout. Luôn kiểm tra **giá trị cuối**.

## 21. Test các trường hợp sai kiểu và thiếu

Bổ sung ma trận:

| New | Old | Kỳ vọng cho resolver ví dụ |
| --- | --- | --- |
| `3s` | Missing | 3s |
| Missing | `7s` | 7s và warning |
| `3s` | `7s` | 3s và conflict warning |
| Missing | Missing | Startup failure |
| `0ms` | `7s` | Startup failure, không fallback |
| `bad` | `7s` | Lỗi binding/conversion |
| `3s` | `bad` | Có thể lỗi binding legacy, vì cả hai field được bind |
| `3s` (YAML) | `20s` (env) | 3s theo new-wins policy |
| `3s` (env) | `20s` (YAML) | 3s |

Nếu chính sách muốn bỏ qua lỗi legacy khi new tồn tại, code ví dụ hiện tại phải được thay; test trường hợp old=bad/new=3s sẽ giúp phát hiện sự khác biệt.

Với String, chuỗi rỗng `""` có thể được xem là giá trị được cung cấp nhưng không hợp lệ. Không tự biến nó thành Missing trừ khi chính sách nêu rõ.

## 22. Test cảnh báo mà không in giá trị bí mật

Trong migration, có thể kiểm tra startup log chứa tên legacy và tên replacement nhưng không chứa các giá trị.

Thông báo an toàn:

~~~text
Property app.client.request-timeout is deprecated.
Use app.client.timeout instead.
~~~

Với key bí mật:

~~~text
Deprecated property app.auth.legacy-token is set.
Use app.auth.token.
~~~

**Không** log:

~~~text
Deprecated token=REAL_TOKEN_HERE
~~~

Cần nhớ record Java có `toString()` tự sinh. Không ghi toàn bộ bean `@ConfigurationProperties` vào log nếu chứa password/token.

Khi xây metric quan sát adoption, chỉ dùng tên key hoặc trạng thái Boolean, tránh ghi value và tránh label cardinality quá lớn.

## 23. Test profile và file thật với @SpringBootTest

Giả sử:

~~~yaml
# application.yaml
app:
  client:
    request-timeout: 10s
~~~

~~~yaml
# application-prod.yaml
app:
  client:
    timeout: 3s
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ClientProdConfigTest {

    @Autowired
    ClientSettings settings;

    @Test
    void readsCanonicalPropertyFromProdProfile() {
        assertThat(settings.timeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

Class `ClientSettingsConfiguration` phải được phát hiện/đăng ký trong application context.

Không thêm:

~~~java
@SpringBootTest(properties = "app.client.timeout=3s")
~~~

vào chính bài test muốn xác minh `application-prod.yaml`, vì test property có thể ghi đè file và làm test pass dù file bị sai.

## 24. Kubernetes, ConfigMap, Secret và environment

Deployment cũ:

~~~yaml
env:
  - name: APP_CLIENT_REQUESTTIMEOUT
    value: "7s"
~~~

Deployment mới:

~~~yaml
env:
  - name: APP_CLIENT_TIMEOUT
    value: "3s"
~~~

Nếu dùng `configMapKeyRef`, phải xem xét riêng `env.name` và `configMapKeyRef.key`:

~~~yaml
env:
  - name: APP_CLIENT_TIMEOUT
    valueFrom:
      configMapKeyRef:
        name: client-settings
        key: timeout
~~~

Key trong ConfigMap không nhất thiết tự đổi khi bạn đổi tên env. Nếu dùng `envFrom`, tên key hợp lệ trong ConfigMap/Secret được dùng làm tên biến, nên cần cập nhật tên nguồn.

Với Secret, không viết credential literal vào Deployment. Chỉ dùng `secretKeyRef` hoặc volume phù hợp, kiểm soát quyền và rotation.

### Env của Pod đang chạy không tự đổi

Khi ConfigMap hoặc Secret dùng để cấp environment variable được cập nhật, biến môi trường của container đã chạy thường không tự thay. Cần recreate/rolling restart Pod để nhận giá trị mới. Vì vậy trong một rollout có thể có nhiều thế hệ Pod dùng tên property khác nhau cùng lúc.

Điều này khiến compatibility window quan trọng hơn việc chỉ chạy test với một instance local.

## 25. Configtree import cần đổi filename hoặc path mapping

Giả sử runtime mount:

~~~text
/run/secrets/app.client.request-timeout
~~~

và app import:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Thì file tạo property `app.client.request-timeout`. Đổi Java field không tự đổi filename.

Migration mới có thể đổi thành:

~~~text
/run/secrets/app.client.timeout
~~~

Nếu cả hai file cùng hiện diện, resolver phải áp dụng policy new-vs-old đã định. Không trông chờ Spring Boot `configtree:` tự hiểu alias.

Kubernetes có thể cập nhật secret volume file sau độ trễ, nhưng bean Spring Boot đã bind lúc startup **không tự được bảo đảm refresh** vì file thay đổi. Với mount qua `subPath`, việc file tự cập nhật còn có giới hạn riêng.

### Cách triển khai an toàn

1. Deploy app chấp nhận cả hai key.
2. Chờ những Pod cũ được thay thế.
3. Chuyển mount/config sang key mới.
4. Xác minh kết nối và giá trị logic đã được sử dụng, không in secret.
5. Thu hồi/loại file cũ khi không cần rollback.
6. Chỉ loại bỏ alias trong phiên bản tiếp theo theo lịch.

## 26. Quy trình sunset theo các giai đoạn

### Giai đoạn A — giới thiệu và cảnh báo

- Thêm canonical key.
- Thêm dual binding hoặc alias resolver.
- Xác định chính sách khi cả hai key cùng có.
- Thêm deprecation metadata.
- Cập nhật example config để dùng key mới.
- Viết test old-only, new-only, both, missing, invalid.
- Ghi vào changelog và migration guide.

### Giai đoạn B — quan sát adoption

- Cảnh báo một lần khi startup dùng legacy key.
- Kiểm kê môi trường còn dùng old key mà không log giá trị.
- Cập nhật ConfigMap, Secret references, Helm values, CI/CD.
- Đồng bộ với người vận hành và các nhóm consumer.
- Duy trì khả năng rollback.
- Tạo dashboard hoặc báo cáo adoption nếu hệ thống có nhu cầu.

### Giai đoạn C — siết tương thích

- Công bố deadline rõ.
- Có thể chuyển từ warning sang fail-on-conflict khi đã thông báo.
- Test release candidate không có alias trong staging.
- Bảo đảm không còn deployment dùng old key.
- Rà soát những hệ thống ít triển khai như batch jobs hoặc disaster recovery.

### Giai đoạn D — removal

- Xóa field legacy và logic resolver.
- Chỉnh metadata/tài liệu cho đúng trạng thái mới.
- Thêm startup guard hoặc test để phát hiện key cũ.
- Cập nhật release notes với breaking change.
- Xác minh production và các môi trường khôi phục.

**Quan trọng:** chỉ xóa field legacy khỏi `@ConfigurationProperties` có thể khiến Binder **bỏ qua** key cũ một cách im lặng. Nếu muốn ngừng hỗ trợ với lỗi minh bạch, cần một kiểm tra hiện diện key phù hợp với các nguồn cấu hình thực tế.

## 27. Startup guard sau khi loại bỏ alias

Có thể xây một guard để từ chối legacy key.

Ví dụ ý tưởng:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class LegacyPropertyGuard {

    public LegacyPropertyGuard(Environment environment) {
        if (environment.containsProperty(
                "app.client.request-timeout")) {
            throw new IllegalStateException(
                "app.client.request-timeout was removed; "
                + "use app.client.timeout");
        }
    }
}
~~~

Đoạn này minh họa fail-fast theo key, nhưng `Environment.containsProperty` không nhất thiết thay thế đầy đủ relaxed binding từ tất cả dạng OS env, CLI hay configtree. Cần kiểm thử từng nguồn mà production dùng, hoặc xây guard ở tầng configuration property source tương thích.

### Vì sao phải có guard?

Một field cũ không còn tồn tại trong Java không đồng nghĩa property old bị từ chối. Nếu key bị bỏ qua và field mới không có giá trị, ứng dụng có thể chạy với default sai.

Tình huống removal tốt nên có lỗi:

~~~text
Legacy property app.client.request-timeout is no longer supported.
Set app.client.timeout instead.
~~~

thay vì im lặng bỏ qua.

## 28. Rollout và rollback cần thiết kế song song

Trong hệ thống phân tán, có các tổ hợp:

| Phiên bản app | Tên config | Kỳ vọng |
| --- | --- | --- |
| Old app | Old key | Hoạt động như trước. |
| New app có compatibility | Old key | Hoạt động và cảnh báo. |
| New app có compatibility | New key | Hoạt động. |
| Old app | New key | Có thể không hiểu; rollback có rủi ro. |

Nếu muốn rollback về ứng dụng cũ sau khi đổi config mới, phải bảo đảm old app vẫn có cấu hình mà nó hiểu, hoặc rollback cấu hình cùng lúc.

Một thứ tự thực tế:

1. **Code first:** deploy phiên bản biết cả old/new.
2. **Config second:** đổi sang new trong config-as-code và runtime.
3. **Observe:** kiểm tra startup, health, hành vi nghiệp vụ, cảnh báo.
4. **Remove old:** sau khi rollback window kết thúc.
5. **Sunset:** phát hành phiên bản không chấp nhận legacy key với quy trình thông báo.

Không xóa old secret/file quá sớm khi còn instance cũ phụ thuộc.

## 29. Tạo migration guide có thể thực hiện

Một thông báo tốt cần đủ thông tin:

~~~text
Deprecated since: 1.8 (ví dụ)
Legacy: app.client.request-timeout
Replacement: app.client.timeout

Old:
  app.client.request-timeout=5s

New:
  app.client.timeout=5s

During transition:
  - Both names accepted.
  - New name takes precedence.
  - Legacy name produces a startup warning.
  - Missing both is an error.

Removal target:
  2.0, subject to rollout completion.

Actions:
  - Update YAML/Properties.
  - Update APP_CLIENT_REQUESTTIMEOUT to APP_CLIENT_TIMEOUT.
  - Update Helm/ConfigMap/secret filenames as necessary.
  - Run compatibility tests.
~~~

Mốc version chỉ là minh họa; tổ chức phải công bố mốc thực tế và trách nhiệm của các nhóm dùng cấu hình.

Nếu có thay đổi kiểu/đơn vị, migration guide phải nêu cách chuyển giá trị thay vì chỉ ghi một phép rename.

## 30. CI/CD có thể giúp phát hiện legacy keys

Đối với các deployment configs có version control, pipeline có thể quét:

~~~text
app.client.request-timeout
APP_CLIENT_REQUESTTIMEOUT
--app.client.request-timeout
~~~

Tuy nhiên cần tránh false positive ở:

- Tài liệu hướng dẫn migration.
- Tests cố ý kiểm tra alias cũ.
- Compatibility code đang trong thời gian hỗ trợ.
- Release notes lịch sử.

Nên quét theo phạm vi file triển khai thực, có ngoại lệ được quản lý, thay vì cấm mọi lần xuất hiện trong toàn repo.

Một pipeline chỉ kiểm tra Git cũng không bảo đảm runtime đã sạch old key: Secret manager, thủ công systemd settings, CI variables hoặc cluster environments có thể nằm ngoài repo.

## 31. Bảng kiểm thử đầy đủ

| Nhóm | Case | Kết quả cần kiểm |
| --- | --- | --- |
| Basic | Chỉ new | Dùng new |
| Compatibility | Chỉ old | Dùng old, cảnh báo |
| Conflict | Cả old và new | Chính sách ưu tiên được áp dụng |
| Missing | Cả hai thiếu | Default hợp lệ hoặc fail |
| Validation | New=0/âm | Fail |
| Conversion | New=bad | Fail rõ |
| Conversion | Old=bad, new tốt | Theo chính sách binder của implementation |
| Precedence | Old env, new YAML | Đúng policy liên-tên |
| Precedence | Old YAML, new env | Đúng policy liên-tên |
| Profiles | File theo profile | Nạp đúng Config Data |
| Environment | Tên env cũ/mới | Binding hoạt động |
| Mounted files | File old/new | Configtree root và tên property đúng |
| Metadata | Old deprecated | IDE metadata có replacement |
| Logging | Old present | Cảnh báo không lộ value |
| Removal | Old sau sunset | Bị từ chối rõ ràng |
| Rollback | App cũ + config mới | Đã có phương án tương thích/rollback |

Nếu chỉ test new=3s và old=7s trong **cùng một property source**, vẫn thiếu các tình huống cross-source vốn thường gây bất ngờ ở production.

## 32. Các lỗi phổ biến

### Lỗi 1 — Chỉ đổi tên Java field
Deployment cũ không tự cập nhật. Cần compatibility layer hoặc breaking release có kế hoạch.

### Lỗi 2 — Nghĩ relaxed binding hỗ trợ mọi alias
`request-timeout` và `timeout` khác ý nghĩa, không được tự ánh xạ.

### Lỗi 3 — Nghĩ @DeprecatedConfigurationProperty tự remap
Metadata chỉ thông báo cho tooling, không thay runtime logic.

### Lỗi 4 — Đặt @DefaultValue trên new field trước migration logic
Có thể che mất giá trị old đang được cung cấp.

### Lỗi 5 — Không quy định cả hai tên cùng có
Business service có thể chọn khác nhau hoặc phụ thuộc vào một thứ tự không được định nghĩa.

### Lỗi 6 — Bỏ qua source precedence
New ở YAML và old ở env cho kết quả khác nhau tùy chính sách new-wins hay highest-source-wins.

### Lỗi 7 — Bỏ qua conversion của khóa không được chọn
Nếu bind cả hai typed fields, legacy sai kiểu vẫn có thể khiến startup fail.

### Lỗi 8 — Đổi tên và đổi đơn vị cùng lúc không có conversion
Người vận hành copy giá trị số cũ sang key mới rồi nhận timeout khác mong đợi.

### Lỗi 9 — Chỉ đổi YAML trong repo
Helm chart, ConfigMap, Secret, env, CLI và production runtime còn old key.

### Lỗi 10 — Dùng properties-migrator vĩnh viễn
Công cụ hỗ trợ nâng cấp không phải alias general-purpose cho mọi property tự định nghĩa.

### Lỗi 11 — Log giá trị secret khi cảnh báo
Chỉ log old/new property names và trạng thái, không log token/password.

### Lỗi 12 — Bỏ qua rollback
App cũ có thể không hiểu config new, cần đổi code trước và config sau.

### Lỗi 13 — Xóa field mà không có removal guard
Old key có thể bị bỏ qua im lặng; cần kiểm tra để fail rõ khi hết hỗ trợ.

### Lỗi 14 — Đặt removal date nhưng không đo adoption
Những workload ít chạy như batch, staging, disaster recovery vẫn có thể dùng key cũ.

## 33. Bài tập có đáp án

### Bài 1 — Phân biệt relaxed binding và rename
`app.client.requestTimeout` vs `app.client.request-timeout` có thể là biến thể tên cùng property; `app.client.timeout` là tên khác cần migration. **Đáp án:** đúng.

### Bài 2 — Chỉ legacy
`app.client.request-timeout=7s`, new vắng. **Đáp án:** trong transition, chọn 7s và cảnh báo.

### Bài 3 — Cả hai tên
Old=7s, new=3s. **Đáp án:** theo new-wins policy, dùng 3s và log conflict.

### Bài 4 — Thiếu cả hai
Timeout bắt buộc. **Đáp án:** fail fast, không tạo default tùy tiện.

### Bài 5 — @DefaultValue gây lỗi
Legacy=20s, new field có default 5s. **Đáp án:** default new có thể che legacy; đặt default sau bước chọn.

### Bài 6 — New key trong YAML, old trong env
New=3s, old=20s. **Đáp án:** với policy name-first new-wins, chọn 3s dù old ở nguồn ưu tiên cao.

### Bài 7 — Khóa cũ sai kiểu
New=3s, old=not-a-duration, raw class dùng hai Duration. **Đáp án:** có thể fail tại Binder trước resolver; nếu muốn khác phải thiết kế convert chỉ giá trị được chọn.

### Bài 8 — Annotation deprecated
Có `@DeprecatedConfigurationProperty(replacement="app.client.timeout")`. **Đáp án:** không tự tạo runtime alias.

### Bài 9 — Environment
Old `APP_CLIENT_REQUESTTIMEOUT`, new `APP_CLIENT_TIMEOUT`. **Đáp án:** cập nhật tên biến và test runtime.

### Bài 10 — File configtree
File old `/run/secrets/app.client.request-timeout`. **Đáp án:** đổi filename/path mapping hoặc giữ alias runtime; Java rename không thay file.

### Bài 11 — Rollback
App old chỉ biết legacy, config đã chuyển new. **Đáp án:** rollback app có thể hỏng; cần rollback config song song hoặc giữ old key trong rollback window.

### Bài 12 — Removal
Xóa old field khỏi record. **Đáp án:** chưa chắc key cũ bị từ chối; viết guard và test.

### Bài 13 — Prefix migration
`legacy.billing.*` → `payments.billing.*`. **Đáp án:** lập map từng key, type/default/secret policy, không chỉ đổi prefix annotation.

### Bài 14 — Log deprecation token
**Đáp án:** chỉ log tên legacy/replacement, không log giá trị.

### Bài 15 — CI scan
Có tên old trong tài liệu và test migration. **Đáp án:** cần phân biệt occurrence hợp lệ với deployment còn dùng old; không chặn search-and-replace một cách mù.

## 34. Checklist khi phát hành

- [ ] Có bảng old → new, type, đơn vị, default, required.
- [ ] Đã xác định policy old-only/new-only/both/neither.
- [ ] Đã test lỗi conversion và zero/blank.
- [ ] Đã kiểm thử old/new ở nguồn ưu tiên khác nhau.
- [ ] Business code chỉ dùng cấu hình đã normalize.
- [ ] Metadata deprecation chỉ ra replacement.
- [ ] Runtime warning chỉ log key names, không log secrets.
- [ ] YAML/Properties/Helm/ConfigMap/Secret/env/CLI/CI được kiểm kê.
- [ ] Sample config và runbook đã chuyển new.
- [ ] Rollback giữa hai thế hệ app/config đã được tính đến.
- [ ] Có mốc sunset và cách quan sát adoption.
- [ ] Sau removal, old key bị phát hiện thay vì im lặng bỏ qua.
- [ ] Không duy trì compatibility code không có owner hoặc deadline.

## 35. Tổng kết

Đổi tên property trong Spring Boot là một **thay đổi hợp đồng vận hành**. Cách tiếp cận có kiểm soát:

1. Giới thiệu canonical name nhưng giữ legacy trong một giai đoạn công bố.
2. Bind hai tên và chuẩn hóa về một đối tượng duy nhất để business code chỉ biết tên mới.
3. Xác định rõ chính sách ưu tiên và xử lý giá trị sai, rỗng hoặc thiếu.
4. Dùng configuration metadata để thông báo deprecation cho tooling, **không nhầm metadata với alias runtime**.
5. Kiểm thử đầy đủ Binder, application context, profile, environment và mounted files khi phù hợp.
6. Cập nhật deployment và tài liệu theo thứ tự có khả năng rollback.
7. Quan sát nơi còn dùng old key, sau đó loại bỏ vào thời điểm đã công bố với fail-fast rõ ràng.

Tương thích tốt không có nghĩa giữ alias vô thời hạn. Nó có nghĩa người sử dụng có đủ thời gian và công cụ để chuyển đổi, còn ứng dụng cuối cùng có một hợp đồng cấu hình gọn, rõ và được kiểm thử.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html).
- [Spring Boot — Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html).
- [Spring Boot — DeprecatedConfigurationProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html).
- [Spring Boot — Binder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot — ApplicationContextRunner API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).