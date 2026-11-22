# Tác động của profile lên danh sách và phần tử có thuộc tính thiếu

Trong Spring Boot Externalized Configuration, profile cho phép chọn thêm cấu hình theo môi trường: `application-dev.yml`, `application-prod.yml` hoặc một tài liệu YAML được kích hoạt bởi `spring.config.activate.on-profile`. Một khó khăn thường gặp là **danh sách (List) không được merge từng phần tử giữa các nguồn cấu hình**. Nếu profile ưu tiên cao hơn khai báo lại một list, list đó có thể thay thế toàn bộ list ở nguồn thấp hơn. Khi phần tử trong list mới thiếu một thuộc tính, Spring Boot không tự lấy thuộc tính ấy từ phần tử có cùng chỉ số hoặc cùng tên ở list cũ.

Điều này khác với **Map**: khi bind Map, các key và thuộc tính lồng nhau có thể được kết hợp từ nhiều property sources theo mức ưu tiên. Hiểu rõ sự khác biệt giúp tránh các lỗi khó thấy như mất phần tử, mất timeout, boolean chuyển sang mặc định `false`, hoặc bean khởi tạo với giá trị `null`.

## 1. Ba tầng cần phân biệt

Spring Boot thực hiện các bước liên quan nhưng không đồng nhất:

1. **Nạp nguồn cấu hình:** application chung, tài liệu profile, Config Data Import, environment và command line.
2. **Xác định mức ưu tiên:** nguồn nào có quyền cung cấp một property khi key trùng nhau.
3. **Binding vào kiểu Java:** scalar, List, Map, nested object có quy tắc kết hợp khác nhau.

Với scalar:

~~~yaml
# application.yml
client:
  timeout: 3s
~~~

~~~yaml
# application-dev.yml
client:
  timeout: 1s
~~~

Khi dev hoạt động và không có nguồn cao hơn ghi đè, timeout hiệu lực là 1 giây. Từ đây không thể suy ra rằng cùng quy tắc “ghi đè một field, giữ field khác” cũng áp dụng cho từng phần tử của List.

Bảng tư duy ban đầu:

| Kiểu dữ liệu cần bind | Hành vi ưu tiên điển hình |
| --- | --- |
| `String`, `int`, `Duration` | Giá trị từ nguồn có độ ưu tiên thắng |
| `List<T>` | List từ nguồn ưu tiên thắng thay List ở nguồn thấp hơn |
| `Map<String, T>` | Các map key có thể được kết hợp; field con giải quyết theo ưu tiên |
| Nested object trong Map | Có thể lấy các field từ nhiều nguồn |
| Nested object trong List bị override | Không tự kế thừa field từ phần tử List của nguồn thấp |

## 2. Ví dụ cơ bản: List trong application.yml

Giả sử ứng dụng cấu hình hai backend:

~~~yaml
# application.yml
routing:
  backends:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
      enabled: true
    - name: "secondary"
      url: "https://secondary.example.invalid"
      timeout: 7s
      enabled: true
~~~

Typed configuration:

~~~java
package example.routing;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Backend> backends) {

    public record Backend(
            String name,
            URI url,
            Duration timeout,
            boolean enabled
    ) {}
}
~~~

Đăng ký properties type:

~~~java
package example.routing;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {
}
~~~

Khi không có nguồn ghi đè, `RoutingProperties.backends()` nhận hai phần tử theo thứ tự được khai báo. Mỗi phần tử có đủ bốn thuộc tính.

| Index | name | timeout | enabled |
| --- | --- | --- | --- |
| 0 | primary | 3 giây | true |
| 1 | secondary | 7 giây | true |

## 3. Profile chỉ định một phần tử: List bị thay nguyên vẹn

Developer muốn đổi URL của primary khi chạy local và viết:

~~~yaml
# application-dev.yml
routing:
  backends:
    - name: "primary"
      url: "http://localhost:9080"
~~~

Chạy với:

~~~bash
java -jar routing-app.jar --spring.profiles.active=dev
~~~

Một suy luận **sai** là: phần tử primary vẫn có `timeout=3s` và `enabled=true` từ file chung, secondary còn nguyên.

Thực tế, với quy tắc List binding của Spring Boot khi profile dev thắng cho `routing.backends`:

~~~text
backends.size() = 1

backends[0]:
  name    = "primary"
  url     = http://localhost:9080
  timeout = null nếu không có default khác
  enabled = false nếu dùng primitive boolean và không có default khác

backends[1]: không còn trong danh sách hiệu lực
~~~

Đây là **replacement**, không phải “patch theo chỉ số”. Nguồn dev được dùng để bind list, không lấy các giá trị con của list từ file chung để lấp phần còn thiếu.

Nếu field `timeout` được code sử dụng ngay:

~~~java
long timeoutMillis =
    properties.backends().get(0).timeout().toMillis();
~~~

thì có thể gặp `NullPointerException` vì timeout thiếu. Nếu ứng dụng có validation phù hợp, lỗi có thể xuất hiện ngay ở startup, đây thường là hành vi tốt hơn.

## 4. Trùng name hoặc id không làm List tự merge

Ví dụ:

~~~yaml
# application.yml
workers:
  entries:
    - id: "invoice"
      threads: 4
      queue-size: 100
    - id: "email"
      threads: 2
      queue-size: 50
~~~

~~~yaml
# application-staging.yml
workers:
  entries:
    - id: "invoice"
      threads: 1
~~~

Không có quy tắc mặc định trong Binder rằng phần tử có `id=invoice` ở hai nguồn là cùng object để merge. `id` là một field do ứng dụng đặt ra. Khi staging list thắng, kết quả thường chỉ có một entry invoice; `queue-size` không tự lấy 100 từ base và entry email biến mất.

Tương tự, dùng cùng chỉ số `[0]` ở hai nguồn **không** định nghĩa identity của phần tử. List có ngữ nghĩa thứ tự, không phải cơ chế cập nhật bản ghi theo primary key.

## 5. Hai kiểu thiếu dữ liệu cần tách riêng

**Trường hợp A: thiếu cả phần tử.**

~~~yaml
# chung
jobs:
  entries:
    - name: "validate"
    - name: "enrich"
    - name: "publish"
~~~

~~~yaml
# profile
jobs:
  entries:
    - name: "validate"
~~~

List ở profile chỉ có `validate`. Hai phần tử `enrich` và `publish` không tự được giữ lại.

**Trường hợp B: còn phần tử nhưng thiếu thuộc tính.**

~~~yaml
# chung
jobs:
  entries:
    - name: "validate"
      timeout: 2s
      enabled: true
~~~

~~~yaml
# profile
jobs:
  entries:
    - name: "validate"
~~~

Phần tử `validate` vẫn có mặt, nhưng `timeout` và `enabled` **không tự kế thừa** từ phần tử ở nguồn thấp. Kết quả phụ thuộc kiểu Java, default, constructor, setter và validation.

| Field bị thiếu | Kiểu Java | Giá trị điển hình nếu không có default khác |
| --- | --- | --- |
| `timeout` | `Duration` | `null` |
| `enabled` | `boolean` | `false` |
| `retryCount` | `Integer` | `null` |
| `name` | `String` | `null` |

Đừng chỉ kiểm tra kích thước List. Cần kiểm tra cả các trường bắt buộc trên từng phần tử.

## 6. YAML nhiều tài liệu có on-profile cũng theo quy tắc này

Không bắt buộc dùng hai file. Có thể tách các tài liệu ngay trong `application.yml`:

~~~yaml
app:
  processors:
    - name: "alpha"
      timeout: 4s
      description: "Base Alpha"
    - name: "beta"
      timeout: 6s
      description: "Base Beta"

---
spring:
  config:
    activate:
      on-profile: "dev"

app:
  processors:
    - name: "alpha-dev"
~~~

Khi dev active và tài liệu dev thắng đối với list, `app.processors` chỉ gồm một phần tử, `name=alpha-dev`; `timeout` và `description` không được tự lấy từ phần tử đầu của tài liệu chung.

`spring.config.activate.on-profile` chỉ quyết định tài liệu nào được kích hoạt. Nó **không bật chức năng deep merge cho List**.

Tương tự, file cấu hình được import bằng `spring.config.import` có thể tạo nguồn ưu tiên cao và thay List của nguồn khác. Tiền tố `optional:` ở import chỉ nói về việc cho phép không tìm thấy location, không có nghĩa List bên trong được merge.

## 7. So sánh với Map: kết hợp theo key

Đổi cấu hình backend từ sequence sang map:

~~~yaml
# application.yml
routing:
  backends:
    primary:
      url: "https://primary.example.invalid"
      timeout: 3s
      enabled: true
    secondary:
      url: "https://secondary.example.invalid"
      timeout: 7s
      enabled: true
~~~

Java:

~~~java
package example.routing;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        Map<String, Backend> backends
) {
    public record Backend(
            URI url,
            Duration timeout,
            boolean enabled
    ) {}
}
~~~

Profile dev chỉ cần:

~~~yaml
# application-dev.yml
routing:
  backends:
    primary:
      url: "http://localhost:9080"
~~~

Map binding có thể kết hợp các key từ nhiều nguồn. Kết quả điển hình:

~~~text
backends["primary"]:
  url     = http://localhost:9080     # dev
  timeout = 3s                        # base
  enabled = true                      # base

backends["secondary"]:
  url     = https://secondary.example.invalid
  timeout = 7s
  enabled = true
~~~

Field con của Map entry có **tên property rõ ràng** như `routing.backends.primary.timeout` nên có thể được phân giải qua các property sources.

Đây là hành vi phù hợp khi cần ghi đè một backend theo ID mà không lặp lại toàn bộ danh sách.

## 8. Bảng List và Map

| Tiêu chí | `List<Backend>` | `Map<String, Backend>` |
| --- | --- | --- |
| Định danh entry | Vị trí `0,1,2...` | Key như `primary` |
| Profile override | List mới thay List cũ | Các map key và field có thể được kết hợp |
| Sửa một URL | Khai báo lại List đầy đủ hoặc thiết kế khác | Override field trong key tương ứng |
| Entry không được nhắc trong profile mới | Không tự được giữ lại khi List thay | Có thể còn từ nguồn thấp |
| Field thiếu của phần tử | Không tự lấy từ phần tử ở List thấp hơn | Có thể lấy từ Map entry thấp hơn |
| Thứ tự có ý nghĩa | Có | Không nên coi thứ tự Map là logic nghiệp vụ |
| Phù hợp | Pipeline có thứ tự, tập danh sách cần thay nguyên vẹn | Catalog có ID, client và integration theo tên |

**Map không phải phép merge mọi thứ ở mọi tầng.** Nếu Map chứa một field kiểu List và profile override field List đó, tầng List vẫn chịu quy tắc replacement.

## 9. List lồng bên trong Map cũng không tự nối

Cấu hình chung:

~~~yaml
clients:
  pricing:
    timeout: 3s
    retry-codes:
      - 429
      - 503
~~~

Profile dev:

~~~yaml
clients:
  pricing:
    timeout: 1s
    retry-codes:
      - 500
~~~

Nếu typed properties là `Map<String, Client>`, timeout của entry pricing có thể đổi thành 1 giây, nhưng `retry-codes` là List: kết quả có thể chỉ có mã `500`, không được nối cùng 429 và 503.

Khi xem một cấu trúc phức tạp, phải xét **kiểu Java ở từng tầng**, không chỉ root là Map hay List.

## 10. Cách an toàn thứ nhất: khai báo trọn vẹn List của từng profile

Nếu list thực sự cần giữ thứ tự và mỗi môi trường có một sequence rõ ràng, khai báo **đầy đủ mọi phần tử và field cần thiết** trong file profile.

~~~yaml
# application.yml
pipeline:
  stages:
    - name: "validate"
      timeout: 2s
      enabled: true
    - name: "publish"
      timeout: 10s
      enabled: true
~~~

~~~yaml
# application-dev.yml
pipeline:
  stages:
    - name: "validate"
      timeout: 1s
      enabled: true
    - name: "publish"
      timeout: 10s
      enabled: true
~~~

Ở đây dev định nghĩa list hiệu lực gồm hai stage hoàn chỉnh. Không cần đoán gì về thừa kế theo index.

Ưu điểm: dễ đọc chính xác sequence, phù hợp các pipeline hoặc danh sách điểm đến mà profile có chủ đích muốn thay nguyên bộ.

Nhược điểm: cấu hình trùng lặp; khi thêm stage mới vào base phải nhớ cập nhật file profile. Nên bổ sung integration test/validation giúp phát hiện chênh lệch không mong muốn.

## 11. Cách an toàn thứ hai: dùng Map có key ổn định

Nếu nhu cầu là “sửa một vài thuộc tính của phần tử được nhận diện bằng tên”, Map thể hiện hợp đồng tốt hơn:

~~~yaml
# application.yml
integrations:
  clients:
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 3s
      max-retries: 2
    pricing:
      base-url: "https://pricing.example.invalid"
      timeout: 5s
      max-retries: 3
~~~

Dev chỉ sửa một URL:

~~~yaml
# application-dev.yml
integrations:
  clients:
    pricing:
      base-url: "http://localhost:9090"
~~~

Nếu bind Map như ở phần trước, các key và field khác được kết hợp theo ưu tiên, không phải copy toàn bộ danh sách client. Đây là giải pháp hữu ích cho configuration catalog, service endpoints và các định nghĩa có ID.

Nhưng nếu ứng dụng bắt buộc gọi inventory trước pricing thì đừng dựa vào thứ tự duyệt Map; hãy mô hình hóa thứ tự riêng.

## 12. Cách kết hợp: definitions Map và execution-order List

Khi cần cả override theo ID và thứ tự:

~~~yaml
# application.yml
pipeline:
  definitions:
    validate:
      timeout: 2s
      enabled: true
    enrich:
      timeout: 5s
      enabled: true
    publish:
      timeout: 10s
      enabled: true
  execution-order:
    - "validate"
    - "enrich"
    - "publish"
~~~

File dev:

~~~yaml
pipeline:
  definitions:
    enrich:
      timeout: 1s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pipeline")
public record PipelineProperties(
        Map<String, Stage> definitions,
        List<String> executionOrder
) {
    public record Stage(Duration timeout, boolean enabled) {}
}
~~~

Khi dev active, `definitions.enrich.timeout` có thể thành 1s trong khi `definitions.validate` và `publish` được giữ. `execution-order` đến từ file chung nếu profile không khai báo List mới.

Code sử dụng phải xác minh mọi stage name trong `executionOrder` tồn tại trong `definitions`:

~~~java
for (String name : properties.executionOrder()) {
    if (!properties.definitions().containsKey(name)) {
        throw new IllegalStateException(
            "Unknown stage in execution order: " + name);
    }
}
~~~

Đây là validation nghiệp vụ của ứng dụng, không phải một kiểm tra tự động do Spring Boot thực hiện.

## 13. Cách khác: đưa các thuộc tính chung ra ngoài List

Nếu nhiều phần tử cùng dùng timeout/retry, tách mặc định ra một object cấp cao:

~~~yaml
# application.yml
remote:
  defaults:
    timeout: 3s
    max-retries: 2
  targets:
    - name: "inventory"
      url: "https://inventory.example.invalid"
    - name: "pricing"
      url: "https://pricing.example.invalid"
~~~

Dev:

~~~yaml
remote:
  defaults:
    timeout: 1s
  targets:
    - name: "inventory"
      url: "http://localhost:9091"
    - name: "pricing"
      url: "http://localhost:9092"
~~~

Kiểu Java:

~~~java
@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(
        Defaults defaults,
        java.util.List<Target> targets
) {
    public record Defaults(
            java.time.Duration timeout,
            int maxRetries
    ) {}
    public record Target(String name, java.net.URI url) {}
}
~~~

Ứng dụng dùng `defaults.timeout()` cho các target. Như vậy list không cần mang field timeout lặp lại; khi profile thay cả list, ít có khả năng làm mất field chung.

**Lưu ý:** việc áp dụng `defaults` cho từng target là logic do ứng dụng định nghĩa, không phải Spring Boot tự kế thừa cho phần tử.

## 14. @DefaultValue hỗ trợ trường thiếu nhưng không merge profile

Với Spring Boot 3.x, typed properties constructor binding có thể dùng `@DefaultValue`:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Backend> backends) {

    public record Backend(
            String name,
            URI url,
            @DefaultValue("3s") Duration timeout,
            @DefaultValue("true") boolean enabled
    ) {}
}
~~~

Với list mới của profile:

~~~yaml
routing:
  backends:
    - name: "local"
      url: "http://localhost:9080"
~~~

các field timeout và enabled có thể nhận default được khai báo ở constructor. Nhưng đó là **giá trị default trong Java**, không phải copy `timeout` hoặc `enabled` từ phần tử có cùng index ở file chung.

Nếu file profile có `timeout: "later"` mà Java cần `Duration`, default không phải cơ chế bỏ qua dữ liệu sai kiểu. Cần sửa cấu hình hoặc converter.

Không nên sử dụng default chỉ để che một cấu hình production bắt buộc nhưng bị thiếu.

## 15. Validation cho phần tử của List

Khi thiếu một field quan trọng, startup fail-fast thường tốt hơn để bean nhận null rồi lỗi muộn.

~~~java
package example.routing;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty @Valid List<Backend> backends
) {
    public record Backend(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

Nếu profile thắng định nghĩa:

~~~yaml
routing:
  backends:
    - name: "local"
      url: "http://localhost:9080"
~~~

thì `timeout` không được cung cấp. Với Bean Validation dependency phù hợp (thường `spring-boot-starter-validation`) và registration của `RoutingProperties`, ràng buộc `@NotNull` có thể làm context fail ngay khi binding/validation.

Phân biệt rõ:

- **List replacement:** chọn cấu hình danh sách hiệu lực.
- **Binding/conversion:** tạo object Java và chuyển kiểu từng field.
- **Validation:** bảo đảm object đáp ứng hợp đồng cấu hình.

`@NotNull Duration timeout` chưa đảm bảo timeout phải lớn hơn 0; nếu cần, bổ sung ràng buộc hoặc kiểm tra riêng. `URI` được convert thành công cũng chưa bảo đảm endpoint được phép truy cập.

## 16. List scalar cũng được thay thế

Không chỉ List object có hành vi này:

~~~yaml
# application.yml
security:
  allowed-hosts:
    - "internal.example.invalid"
    - "partner.example.invalid"
~~~

~~~yaml
# application-dev.yml
security:
  allowed-hosts:
    - "localhost"
~~~

Khi dev thắng cho list, kết quả có thể chỉ là `["localhost"]`. Spring Boot không tự append localhost vào hai host ở base.

Đối với allowlist, denylist, CORS origins, routing targets hoặc topic subscriptions, thay List có thể ảnh hưởng vận hành và bảo mật. Đây không phải vấn đề hình thức của YAML; nó là **ngữ nghĩa binding của externalized configuration**.

Nếu mục đích là thật sự đổi toàn bộ tập host trong dev, replacement là phù hợp. Nếu muốn giữ list chung và chỉ thêm một entry, phải thiết kế cách kết hợp riêng thay vì giả định profile có phép append.

## 17. Nhiều profile cùng active

Spring Boot cho phép:

~~~bash
java -jar app.jar --spring.profiles.active=staging,metrics
~~~

Hai file:

~~~yaml
# application-staging.yml
app:
  collectors:
    - "staging-request"
    - "staging-error"
~~~

~~~yaml
# application-metrics.yml
app:
  collectors:
    - "jvm"
    - "http"
~~~

Nếu cả hai cùng hoạt động, list không tự là bốn phần tử. Với các nguồn profile ở cùng mức ưu tiên, quy tắc **profile sau có thể thắng** được áp dụng khi cấu hình được nạp, nên list hiệu lực có thể là `["jvm","http"]`. Giá trị cuối cùng còn tùy Config Data imports và các nguồn cao hơn như command line.

Thói quen nguy hiểm là bật cùng lúc hai profile xung đột và dựa vào thứ tự ngẫu nhiên để được một list mong muốn. Tốt hơn:

- Quy định profile nào sở hữu collection.
- Tránh một profile monitoring ghi đè list nghiệp vụ của staging.
- Dùng cấu hình tường minh cho list thực sự cần thay.
- Kiểm tra kết quả bind bằng test cho tập profile triển khai thật.

## 18. Override list bằng biến môi trường

Đối với danh sách indexed, Spring Boot hỗ trợ mapping từ môi trường theo quy tắc relaxed binding. Một key như:

~~~text
routing.backends[0].url
~~~

có thể tương ứng với tên biến môi trường dạng:

~~~text
ROUTING_BACKENDS_0_URL
~~~

Nếu nguồn biến môi trường ưu tiên cao chỉ cung cấp URL của phần tử 0, đừng mặc định các trường `name`, `timeout` và phần tử 1 sẽ tự được ghép từ YAML thấp hơn. Với list replacement, override từng item qua nhiều biến môi trường có thể làm cấu hình thiếu hoặc thay toàn danh sách.

Cách an toàn hơn khi list có nhiều field là dùng profile-specific file hoàn chỉnh, hoặc chuyển sang Map nếu muốn override theo key ổn định. Luôn xác minh tên biến thực sự được Binder nhận trên phiên bản Spring Boot đang triển khai.

## 19. Kiểm thử bằng profile thật

Có thể tạo test resources:

~~~yaml
# src/test/resources/application.yml
demo:
  endpoints:
    - name: "base"
      description: "From base"
      timeout: 3s
    - name: "second"
      description: "Second endpoint"
      timeout: 5s
~~~

~~~yaml
# src/test/resources/application-dev.yml
demo:
  endpoints:
    - name: "dev"
~~~

Properties record:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(List<Endpoint> endpoints) {
    public record Endpoint(
            String name,
            String description,
            Duration timeout
    ) {}
}
~~~

Đăng ký `DemoProperties` qua `@EnableConfigurationProperties` hoặc scan ở application context.

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class ListProfileBindingTest {

    @Autowired
    DemoProperties properties;

    @Test
    void devListReplacesBaseList() {
        assertThat(properties.endpoints()).hasSize(1);

        DemoProperties.Endpoint entry =
            properties.endpoints().get(0);

        assertThat(entry.name()).isEqualTo("dev");
        assertThat(entry.description()).isNull();
        assertThat(entry.timeout()).isNull();
    }
}
~~~

Test chỉ minh họa khi context có registration và không có default/validator khác; nếu bạn dùng `@NotNull`, context có thể thất bại sớm thay vì có bean với timeout null. Đó là một kết quả khác nhưng cũng minh họa hậu quả của field thiếu.

Test không nên chỉ dùng `new DemoProperties(...)`, vì cách đó không gọi Spring Binder và không chứng minh được cách xử lý các property sources.

## 20. Đối chiếu bằng Map trong test

Thay mô hình thành:

~~~yaml
# application.yml
demo:
  endpoints:
    alpha:
      description: "From base"
      timeout: 3s
    beta:
      description: "Second endpoint"
      timeout: 5s
~~~

~~~yaml
# application-dev.yml
demo:
  endpoints:
    alpha:
      description: "From dev"
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        java.util.Map<String, Endpoint> endpoints
) {
    public record Endpoint(
            String description,
            java.time.Duration timeout
    ) {}
}
~~~

Khi dev active, map có thể giữ `alpha` và `beta`. Entry `alpha.description` lấy từ dev, `alpha.timeout` từ base; entry `beta` từ base.

Test cần xác minh:

~~~java
assertThat(properties.endpoints())
    .containsKeys("alpha", "beta");

assertThat(properties.endpoints().get("alpha").description())
    .isEqualTo("From dev");

assertThat(properties.endpoints().get("alpha").timeout())
    .isEqualTo(java.time.Duration.ofSeconds(3));
~~~

Cách này diễn đạt mục đích override field của entry có tên tốt hơn list.

## 21. Những lỗi thường gặp

**Lỗi 1 — Nghĩ List sẽ merge theo index.** File dev chỉ có phần tử 0, nhưng người viết kỳ vọng phần tử 1 từ file gốc còn nguyên. Phải định nghĩa list đầy đủ nếu muốn replacement hoặc dùng Map nếu muốn merge theo tên.

**Lỗi 2 — Nghĩ field `id` là merge key.** Spring Boot không tự nối các phần tử dựa trên `name`/`id`. Những trường đó chỉ là dữ liệu của ứng dụng.

**Lỗi 3 — Không validate field của nested item.** Thiếu `timeout`, `url` hoặc `enabled` có thể dẫn tới null/default bất ngờ. Dùng `@Valid` và constraint hoặc default có ý nghĩa.

**Lỗi 4 — Tạo quá nhiều profile để vá list.** Chẳng hạn `dev-with-backend-a`, `dev-with-backend-b`, `prod-with-both`. Nên xem lại mô hình Map và property thông thường trước khi thêm profile.

**Lỗi 5 — Nghĩ Map merge nghĩa là list nested cũng merge.** Nếu Map entry chứa `List<String> retryCodes`, trường đó vẫn chịu list replacement.

**Lỗi 6 — Dùng Optional Config Data Import và nghĩ sẽ có partial merge.** `optional:` chỉ cho phép thiếu vị trí import. Nội dung file import có list vẫn tuân theo Binder.

**Lỗi 7 — Nhầm thiếu field với lỗi parser.** YAML hoàn toàn hợp lệ vẫn có thể bind ra object thiếu field. Nếu property required thì validation phải thể hiện yêu cầu ấy.

**Lỗi 8 — Không xác nhận nguồn thắng.** Khi nhiều profile, biến môi trường và tham số dòng lệnh cùng tác động, giá trị hiệu lực có thể không đến từ file mà developer đang đọc.

## 22. Quy trình chẩn đoán khi list bị thiếu dữ liệu

Khi thấy list ít phần tử hơn hoặc một entry có null:

1. Xác định profile đang active.
2. Tìm tất cả nguồn đang cung cấp **cùng list prefix**, gồm YAML chung, file profile, import, environment và CLI.
3. Xác định nguồn ưu tiên cao nhất đang định nghĩa list.
4. Quan sát **kích thước list đã bind**, không chỉ so sánh YAML bằng mắt.
5. Kiểm tra từng phần tử: index, name/ID, field bắt buộc, default và validation.
6. Kiểm tra có khai báo index rời rạc hoặc tên biến môi trường sai quy ước không.
7. Nếu mong merge theo ID, xác định Map có thể mô tả ý định rõ hơn không.
8. Nếu list cần giữ thứ tự, cân nhắc định nghĩa toàn bộ sequence trong một nguồn hoặc tách Map definitions + List order.
9. Thêm integration test cho cấu hình/profile thực tế.
10. Không in secret ra log hoặc expose tùy tiện các Actuator endpoint cấu hình.

Các công cụ quan sát property như `Environment`, `@ConfigurationProperties` và Actuator `/actuator/configprops` có thể hữu ích khi bảo vệ quyền truy cập phù hợp, nhưng nguồn chân lý cuối cùng vẫn là giá trị đã bind trong context của bản triển khai.

## 23. Bài tập dự đoán kết quả

Cấu hình chung:

~~~yaml
catalog:
  targets:
    - id: "alpha"
      base-url: "https://alpha.example.invalid"
      timeout: 4s
      enabled: true
    - id: "beta"
      base-url: "https://beta.example.invalid"
      timeout: 6s
      enabled: true
  providers:
    alpha:
      region: "apac"
      retries: 3
    beta:
      region: "eu"
      retries: 2
~~~

Profile staging:

~~~yaml
catalog:
  targets:
    - id: "alpha"
      base-url: "https://staging-alpha.example.invalid"
  providers:
    alpha:
      retries: 1
~~~

Binding:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        java.util.List<Target> targets,
        java.util.Map<String, Provider> providers
) {
    public record Target(
            String id,
            java.net.URI baseUrl,
            java.time.Duration timeout,
            boolean enabled
    ) {}

    public record Provider(
            String region,
            int retries
    ) {}
}
~~~

Dự đoán khi staging active và không có nguồn ưu tiên cao hơn:

| Câu hỏi | Kết quả |
| --- | --- |
| `targets.size()` | 1 |
| `targets[0].id` | alpha |
| `targets[0].baseUrl` | URL staging |
| `targets[0].timeout` | Không tự lấy 4s; có thể null |
| `targets[0].enabled` | Không tự lấy true; thường false |
| `targets[1]` | Không tồn tại |
| `providers["alpha"].region` | apac từ base |
| `providers["alpha"].retries` | 1 từ staging |
| `providers["beta"]` | Có thể còn từ base |

Bảng này chỉ rõ: **List replacement** không giống **Map merging** ngay trong cùng một nhóm configuration properties.

## 24. Checklist thiết kế trước khi triển khai

- Collection đó có thứ tự nghiệp vụ không? Nếu không, xem xét Map.
- File profile có đang vô tình khai báo lại List chỉ để sửa một field không?
- Nếu khai báo List mới, tất cả phần tử cần thiết đã được liệt kê chưa?
- Mỗi phần tử có đầy đủ các field quan trọng không?
- Primitive default như `false` hoặc `0` có phù hợp về mặt vận hành không?
- Có quy tắc default rõ nghĩa qua code hoặc `@DefaultValue` không?
- Có validation để fail-fast khi thiếu URL, timeout, tên hoặc ràng buộc khác không?
- Có nhiều profile có thể cùng khai báo list này không?
- Có list nested dưới một Map entry không?
- Có test đọc cấu hình với đúng tập profile và property sources dùng ở deployment không?
- Nếu cần vừa override theo ID vừa giữ order, đã cân nhắc definitions Map + order List chưa?

## 25. Ghi nhớ

**Spring Boot không tự deep merge List giữa các nguồn cấu hình khác nhau.** Khi một profile định nghĩa lại danh sách ở nguồn ưu tiên cao, danh sách đó có thể thay toàn bộ bản gốc. Phần tử mới bị thiếu field không tự lấy giá trị từ phần tử cùng chỉ số hoặc cùng tên ở nguồn thấp. Kết quả có thể là mất phần tử, null, default của kiểu Java hoặc lỗi validation.

**Map có khả năng kết hợp các key/field từ nhiều nguồn** theo thứ tự ưu tiên. Dùng Map khi mỗi entry có tên định danh ổn định và thường cần override một field riêng; dùng List khi sequence và thứ tự thực sự có ý nghĩa. Với cấu hình quan trọng, luôn xác minh giá trị bind trong profile triển khai thực tế và kiểm tra tính đầy đủ của từng entry.
