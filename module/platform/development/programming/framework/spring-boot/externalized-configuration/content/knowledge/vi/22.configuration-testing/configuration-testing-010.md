# Kiểm thử collection, đối tượng lồng nhau, giá trị trống và cấu hình thiếu trong Spring Boot

## 1. Mục tiêu bài học

Cấu hình Spring Boot không chỉ là vài khóa String hoặc Integer. Trong ứng dụng thực tế, `@ConfigurationProperties` có thể chứa:

- `List<String>`, `List<Server>` hoặc `Set<String>`.
- `Map<String, String>` và Map chứa object phức tạp.
- Record hoặc JavaBean lồng nhau nhiều cấp.
- Field không bắt buộc, field có mặc định và field bắt buộc.
- Chuỗi rỗng, chuỗi chỉ có khoảng trắng, List rỗng, Map rỗng.
- Giá trị kiểu Boolean false, số 0 hoặc một Duration bằng 0.
- Những cấu hình có mặt trong file gốc nhưng bị profile hoặc nguồn ưu tiên cao ghi đè.

Bài học này hướng dẫn kiểm thử **kết quả sau binding**, thay vì chỉ kiểm tra một file YAML có chứa dòng cần thiết.

Những câu hỏi cần trả lời rõ:

1. Khi có một List, thứ tự và số phần tử có được giữ nguyên?
2. Khi profile mới ghi đè List, kết quả được nối thêm hay thay thế?
3. Map có key đặc biệt như `/admin` hoặc `api.v2` có giữ đúng key?
4. Một object nested không có nhóm cấu hình có bị null không?
5. Khác biệt giữa `retry: {}` và không có `retry` là gì?
6. `@DefaultValue` hoạt động ở mức field và mức nested object thế nào?
7. `@NotEmpty`, `@NotBlank`, `@NotNull` và `@Valid` khác nhau ra sao?
8. Làm sao test “thiếu khóa” khác “có khóa nhưng sai kiểu”?
9. Khi nào dùng `Binder`, `ApplicationContextRunner` hoặc `@SpringBootTest`?

Các ví dụ hướng đến Spring Boot 3.x, Java 17+, JUnit 5 và AssertJ. Tất cả dữ liệu là giả, không chứa credential production.

## 2. Phân biệt bốn giai đoạn cần kiểm thử

Một thuộc tính cấu hình đi qua các bước:

~~~text
application.yaml / application-{profile}.yaml
OS environment / System properties / CLI / test properties
                         |
                         v
                   Environment
                  PropertySources
                         |
                         v
                 Binder + Conversion
                         |
                 +-------+-------+
                 |               |
                 v               v
          Bind được object   Lỗi conversion
                 |
                 v
         @ConfigurationProperties
                 |
                 v
          @Validated + @Valid
                 |
           +-----+-----+
           |           |
           v           v
         Hợp lệ     Lỗi validation
~~~

Một test thành công cần biết nó đang kiểm tra tầng nào:

- **Nạp nguồn:** file hoặc profile có được tham gia `Environment`?
- **Binding:** tên thuộc tính có khớp Java member và kiểu đích?
- **Conversion:** giá trị `5s` có thành `Duration.ofSeconds(5)`?
- **Validation:** List và nested object có đúng chính sách nghiệp vụ?

Ví dụ `retry-count=abc` cho field `int retryCount` là **lỗi conversion**, không phải “không khai báo”. Ngược lại `retry-count=0` chuyển kiểu thành công nhưng có thể vi phạm `@Min(1)`.

Đừng gom các trường hợp ấy thành một nhánh “cấu hình lỗi” mà không có kiểm thử riêng.

## 3. Mô hình cấu hình làm ví dụ xuyên suốt

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        List<String> regions,
        List<Endpoint> endpoints,
        Map<String, String> headers,
        Retry retry) {

    public record Endpoint(
            String name,
            String url) {
    }

    public record Retry(
            Integer maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Một `application.yaml` hợp lệ:

~~~yaml
app:
  delivery:
    enabled: true
    regions:
      - apac
      - emea
    endpoints:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
    headers:
      client: demo-app
      region: apac
    retry:
      max-attempts: 3
      initial-delay: 500ms
~~~

Kết quả kỳ vọng:

| Thành viên | Kiểu Java | Giá trị |
| --- | --- | --- |
| `enabled` | `boolean` | `true` |
| `regions` | `List<String>` | `["apac","emea"]` |
| `endpoints` | `List<Endpoint>` | Hai record có name và url |
| `headers` | `Map<String,String>` | client và region |
| `retry` | `Retry` | Object không null |
| `retry.maxAttempts` | `Integer` | 3 |
| `retry.initialDelay` | `Duration` | 500 ms |

Nhắc lại: `@ConfigurationProperties` chưa tự bảo đảm class trở thành bean. Trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Trong test context nhỏ, có thể đăng ký tường minh bằng `@EnableConfigurationProperties(DeliveryProperties.class)`.

## 4. Chọn công cụ kiểm thử phù hợp

| Cần kiểm tra | Công cụ | Điều cần nhớ |
| --- | --- | --- |
| Một property hoặc object từ tập key giả lập | `Binder` + `MapConfigurationPropertySource` | Không cần Spring context |
| Collection có đúng kiểu phần tử không | `Bindable.listOf`, `Bindable.mapOf` | Bảo toàn generic type |
| Bean có được bind và tạo trong context | `ApplicationContextRunner` | Đăng ký class qua `@EnableConfigurationProperties` |
| Validation khiến startup thất bại | `ApplicationContextRunner` với validation provider | Cần `@Validated` và constraints |
| File profile thật được nạp và override | `@SpringBootTest` + `@ActiveProfiles` | Tránh nguồn test ghi đè khóa đang kiểm tra |
| Biến môi trường OS có đúng tên | Test môi trường đã chuẩn bị | Map property source không luôn tương đương OS env |
| Full startup cùng config file production | Integration test có chọn file/profile | Có thể cần hạ tầng giả cho các bean khác |

`spring-boot-starter-test` thường cung cấp JUnit Jupiter, AssertJ và `ApplicationContextRunner`. Nếu dùng Jakarta Bean Validation, cần provider như `spring-boot-starter-validation`.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

## 5. Test List<String>: không chỉ kiểm tra một phần tử

YAML:

~~~yaml
app:
  delivery:
    regions:
      - apac
      - emea
      - americas
~~~

Assertion:

~~~java
assertThat(properties.regions())
        .containsExactly("apac", "emea", "americas");
~~~

`containsExactly` kiểm tra **đủ số phần tử và đúng thứ tự**. Khi thứ tự có ý nghĩa nghiệp vụ, đây là lựa chọn phù hợp.

Nếu thứ tự không quan trọng:

~~~java
assertThat(properties.regions())
        .containsExactlyInAnyOrder(
                "apac", "emea", "americas");
~~~

Không nên chỉ kiểm tra:

~~~java
assertThat(properties.regions())
        .contains("apac");
~~~

vì một List bị mất phần tử `emea` vẫn qua test.

Dạng tương ứng trong `application.properties`:

~~~properties
app.delivery.regions[0]=apac
app.delivery.regions[1]=emea
app.delivery.regions[2]=americas
~~~

Với List scalar đơn giản cũng có thể dùng dạng dấu phẩy:

~~~properties
app.delivery.regions=apac,emea,americas
~~~

Khi dùng List object, indexed syntax hoặc YAML sequence thường dễ hiểu hơn.

## 6. Unit test List bằng Binder

Đây là ví dụ JUnit 5 đầy đủ, không phải khởi động Spring context.

~~~java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class ListBindingTest {

    @Test
    void bindsIndexedStringsInOrder() {
        var source = new MapConfigurationPropertySource(
                Map.of(
                        "app.regions[0]", "apac",
                        "app.regions[1]", "emea"));

        Binder binder = new Binder(source);

        BindResult<List<String>> result =
                binder.bind(
                        "app.regions",
                        Bindable.listOf(String.class));

        assertThat(result.isBound()).isTrue();
        assertThat(result.get())
                .containsExactly("apac", "emea");
    }
}
~~~

`Bindable.listOf(String.class)` giúp Binder biết kiểu phần tử. Đừng truyền `List.class` nếu test phải khẳng định đúng phép chuyển từng phần tử sang `Duration`, `Integer` hoặc record phức tạp.

Ví dụ với `List<Duration>`:

~~~properties
app.delays[0]=100ms
app.delays[1]=2s
~~~

Kỳ vọng:

~~~java
assertThat(delays)
        .containsExactly(
                Duration.ofMillis(100),
                Duration.ofSeconds(2));
~~~

Nếu một phần tử ghi `not-a-duration`, Binder có thể ném lỗi conversion; đó là test riêng, không phải một List mặc định rỗng.

## 7. List object: kiểm tra phần tử và field con

Nguồn:

~~~properties
app.delivery.endpoints[0].name=primary
app.delivery.endpoints[0].url=https://primary.example.test
app.delivery.endpoints[1].name=backup
app.delivery.endpoints[1].url=https://backup.example.test
~~~

Với `List<Endpoint>` trong `DeliveryProperties`:

~~~java
assertThat(properties.endpoints())
        .containsExactly(
                new DeliveryProperties.Endpoint(
                        "primary", "https://primary.example.test"),
                new DeliveryProperties.Endpoint(
                        "backup", "https://backup.example.test"));
~~~

Record có `equals` theo các thành viên, nên test kiểm tra đồng thời số lượng, thứ tự và mọi field của phần tử.

Trường hợp ranh giới:

~~~properties
app.delivery.endpoints[0].name=primary
~~~

Có dữ liệu đủ để Binder cố tạo một phần tử, nhưng `url` có thể null nếu không có default.

**Sai lầm phổ biến:** chỉ `assertThat(endpoints).hasSize(1)` rồi coi config đầy đủ. List có phần tử không đồng nghĩa nội dung phần tử đã đáp ứng nghiệp vụ. Nếu URL bắt buộc, cần thêm validation và test trường hợp missing/blank URL.

## 8. Quy tắc cực quan trọng: List giữa nhiều nguồn không tự merge

Spring Boot có quy tắc khi các `PropertySource` hoặc profile khác nhau cùng cung cấp một List: **List có ưu tiên cao nhất thay thế toàn bộ List**, không tự kết hợp các phần tử.

Ví dụ `application.yaml`:

~~~yaml
app:
  delivery:
    endpoints:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
~~~

Trong `application-dev.yaml`:

~~~yaml
app:
  delivery:
    endpoints:
      - name: local
        url: http://localhost:8089
~~~

Khi profile dev có hiệu lực, kết quả thường là:

~~~text
endpoints:
  - name=local, url=http://localhost:8089
~~~

Không phải ba phần tử.

### List object partial override

Nguồn gốc:

~~~properties
app.delivery.endpoints[0].name=primary
app.delivery.endpoints[0].url=https://primary.example.test
~~~

Nguồn ưu tiên cao:

~~~properties
app.delivery.endpoints[0].name=local
~~~

Theo quy tắc merge complex types của Spring Boot, phần tử ở nguồn cao có thể mang:

~~~text
name = local
url  = null
~~~

**Không tự lấy URL của nguồn thấp** để điền vào phần tử List của nguồn cao.

Test phù hợp khi cần phát hiện điều đó:

~~~java
assertThat(properties.endpoints()).hasSize(1);
assertThat(properties.endpoints().get(0).name())
        .isEqualTo("local");
assertThat(properties.endpoints().get(0).url())
        .isNull();
~~~

Khi muốn luôn có URL, hãy khai báo đầy đủ ở nguồn ưu tiên cao và dùng `@NotBlank` cho field URL.

## 9. Map: kiểm tra key và value, không chỉ size

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        Map<String, String> headers) {
}
~~~

Properties:

~~~properties
app.gateway.headers.client=demo
app.gateway.headers.region=apac
~~~

Assertion:

~~~java
assertThat(properties.headers())
        .containsEntry("client", "demo")
        .containsEntry("region", "apac");
~~~

Chỉ kiểm tra `map.size()==2` là chưa đủ; Map có thể chứa hai key **sai tên** và vẫn có kích thước đúng.

### Key chứa ký tự đặc biệt

Với Map key `/admin`:

~~~properties
app.gateway.routes[/admin]=https://admin.example.test
~~~

Trong YAML:

~~~yaml
app:
  gateway:
    routes:
      "[/admin]": https://admin.example.test
~~~

Dấu ngoặc vuông yêu cầu bảo toàn ký tự đặc biệt. Nếu bỏ bracket, Binder có thể loại dấu `/` khỏi Map key.

Test cần xác nhận chính key:

~~~java
assertThat(properties.routes())
        .containsKey("/admin");
~~~

### Key có dấu chấm

Với `Map<String,String>`, key chứa dấu chấm có thể được giữ vì value là scalar. Với `Map<String,Object>` hoặc value cấu trúc, dấu chấm có thể được hiểu là cấp nested. Nếu cần key literal `api.v2`, dùng bracket:

~~~yaml
app:
  gateway:
    routes:
      "[api.v2]": https://api-v2.example.test
~~~

Kiểm tra rõ `containsKey("api.v2")`.

## 10. Map merge khác List replacement

Nguồn gốc:

~~~properties
app.gateway.headers.client=demo
app.gateway.headers.region=apac
~~~

Nguồn ưu tiên cao:

~~~properties
app.gateway.headers.region=emea
app.gateway.headers.trace=true
~~~

Khi bind Map, các entry có thể được gộp từ nhiều nguồn; cùng key/property thì nguồn cao thắng:

~~~text
client=demo
region=emea
trace=true
~~~

Bộ test nên kiểm tra cả key không bị mất và key được ghi đè:

~~~java
assertThat(headers)
        .containsEntry("client", "demo")
        .containsEntry("region", "emea")
        .containsEntry("trace", "true");
~~~

Với `Map<String, SomePojo>`, các field của object có thể đến từ nhiều nguồn theo quy tắc Binder. Nếu yêu cầu tất cả field của một entry phải thuộc cùng nguồn, đừng mặc định Map binding đảm bảo điều đó; hãy kiểm thử và thiết kế chính sách riêng.

**So sánh ngắn:**

| Loại | Khi nguồn ưu tiên cao cùng khai báo |
| --- | --- |
| `List<T>` | Thường thay thế toàn bộ danh sách. |
| `Map<K,V>` | Có thể gộp key và field con; cùng property thì nguồn cao thắng. |

## 11. Nested record: kiểm tra object con có thực sự được tạo

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            Integer attempts,
            Duration backoff) {
    }
}
~~~

YAML:

~~~yaml
app:
  storage:
    bucket: demo-bucket
    retry:
      attempts: 3
      backoff: 2s
~~~

Test:

~~~java
assertThat(properties.bucket())
        .isEqualTo("demo-bucket");

assertThat(properties.retry()).isNotNull();

assertThat(properties.retry().attempts())
        .isEqualTo(3);

assertThat(properties.retry().backoff())
        .isEqualTo(Duration.ofSeconds(2));
~~~

Tên khóa đầy đủ gồm:

~~~text
app.storage.bucket
app.storage.retry.attempts
app.storage.retry.backoff
~~~

`app.storage` là prefix; `retry` là thành viên object con; các field bên trong thuộc đường dẫn nested.

Không cần đặt `@ConfigurationProperties` lên từng record con khi chúng chỉ là thành viên của một configuration properties object.

## 12. Thiếu cả nested group: điều khác với thiếu một field

Giữ record ở phần trước, nhưng nguồn chỉ có:

~~~properties
app.storage.bucket=demo-bucket
~~~

Không có khóa:

~~~text
app.storage.retry.*
~~~

Với constructor binding của nested record không có default riêng, `properties.retry()` có thể là **null**.

Test phải xác định chính sách:

~~~java
assertThat(properties.retry()).isNull();
~~~

nếu retry tùy chọn.

Hoặc nếu retry bắt buộc, cần validation chặn cấu hình thiếu. Không nên gọi:

~~~java
properties.retry().attempts();
~~~

mà chưa xác định retry có thể null hay không.

Nếu chỉ có:

~~~properties
app.storage.retry.attempts=3
~~~

Binder có thể tạo object `Retry`, nhưng `backoff` vẫn null vì thiếu giá trị. Đây là một trường hợp khác, cần test riêng.

### Hai mức thiếu

1. **Thiếu cả nhóm:** `retry` có thể null.
2. **Nhóm có một số field:** `retry` có thể không null, nhưng có member null.

Một test chỉ xác minh `retry != null` chưa chứng minh các field bên trong hợp lệ.

## 13. @DefaultValue ở field khác với @DefaultValue trên object con

Spring Boot hỗ trợ default value cho constructor parameter hoặc record component:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("2s") Duration backoff) {
    }
}
~~~

Nếu nguồn có:

~~~properties
app.storage.bucket=demo
app.storage.retry.attempts=5
~~~

thì nested `Retry` có thể được tạo với attempts=5, backoff=2s.

Nhưng nếu không có **bất kỳ** `app.storage.retry.*` nào, các default bên trong `Retry` không tự buộc `retry` của class cha trở thành non-null.

### Dùng @DefaultValue rỗng cho nested member

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        String bucket,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("2s") Duration backoff) {
    }
}
~~~

`@DefaultValue` không truyền đối số trên `Retry retry` thể hiện yêu cầu tạo nested object với các giá trị mặc định ngay cả khi không có dữ liệu con, khi object cha được bind theo constructor binding phù hợp.

Test:

~~~java
assertThat(properties.retry()).isNotNull();
assertThat(properties.retry().attempts()).isEqualTo(3);
assertThat(properties.retry().backoff())
        .isEqualTo(Duration.ofSeconds(2));
~~~

Chú ý: default cấp member không đồng nghĩa `Binder.bind("app.storage",...)` luôn tạo cả object cha nếu **toàn bộ prefix** vắng mặt. Trường hợp không có dữ liệu cho target vẫn cần kiểm thử bằng `BindResult` hoặc context phù hợp.

## 14. Nested mapping rỗng trong YAML

Hai nguồn trông tương tự nhưng có thể khác nhau.

**A — thiếu hẳn retry:**

~~~yaml
app:
  storage:
    bucket: demo
~~~

**B — khai báo retry rỗng:**

~~~yaml
app:
  storage:
    bucket: demo
    retry: {}
~~~

Tài liệu Spring Boot về constructor binding cho thấy nested mapping rỗng có thể kích hoạt binding đối tượng con với default của các tham số, trong khi nhóm hoàn toàn không có mặt có thể để nested member null.

Khi cần phân biệt A và B, viết test tích hợp với YAML thật vì kết quả phụ thuộc vào cách Config Data biểu diễn dữ liệu vào Binder.

Không nên buộc người vận hành viết `retry: {}` chỉ để tránh null trong một thiết kế mới. Nếu yêu cầu luôn có object, `@DefaultValue` rỗng ở nested member là cách khai báo rõ ý định hơn.

Một ví dụ Properties cho nested object rỗng trong tài liệu:

~~~properties
app.storage.bucket=demo
app.storage.retry=
~~~

Không suy rộng rằng mọi `key=` đều tạo object. Với String, kiểu số, Map và List, giá trị rỗng có thể mang ý nghĩa khác.

## 15. JavaBean mutable có default nội bộ khác record

Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {

    @Valid
    private final Eviction eviction = new Eviction();

    public Eviction getEviction() {
        return eviction;
    }

    public static class Eviction {

        @NotBlank
        private String strategy;

        @Min(1)
        private int batchSize = 10;

        public String getStrategy() {
            return strategy;
        }

        public void setStrategy(String strategy) {
            this.strategy = strategy;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }
    }
}
~~~

`CacheProperties` tự tạo `Eviction`, nên object con có thể tồn tại dù không có nguồn `app.cache.eviction.*`. Khác với record nested không có default, nó không nhất thiết null.

`@Valid` trên thành viên con cho phép validation đi sâu. Nếu `strategy` không được cấu hình, `@NotBlank` có thể làm context khởi động thất bại.

Đây là một test cần có khi refactor JavaBean thành record: cùng một YAML nhưng **chiến lược tạo default khác** có thể làm kết quả khác đi.

## 16. Missing, empty, blank, YAML null là bốn trường hợp

**Missing key:**

~~~properties
# Không có app.display-name
~~~

Đối với String hoặc wrapper, field có thể null nếu không có default.

**Empty string:**

~~~properties
app.display-name=
~~~

Đối với String, Binder có thể nhận chuỗi `""`. Đây là giá trị có mặt nhưng rỗng.

**Whitespace-only string:**

~~~properties
app.display-name=   
~~~

Chuỗi có ký tự nhưng không có nội dung thực theo `@NotBlank`.

**YAML null:**

~~~yaml
app:
  display-name: null
~~~

Đây không phải String literal `"null"`. Việc flatten YAML và conversion có thể khiến null không hiện diện như một String giá trị; cần test đường nạp cụ thể.

**Empty collection:**

~~~yaml
app:
  regions: []
  headers: {}
~~~

Không tự giả định every target nhận `List.of()` hoặc `Map.of()` trong mọi đường binding; khác biệt giữa nguồn YAML, Properties, field default và constructor binding cần được test.

### Ma trận trạng thái

| Nguồn | Target | Điều cần kiểm tra |
| --- | --- | --- |
| Không có key | `String` | null/default |
| `name=` | `String` | empty string và validation |
| `name=   ` | `String` | whitespace-only và `@NotBlank` |
| Không có count | `Integer` | null nếu không có default |
| Không có count | `int` | giá trị primitive mặc định theo binding |
| `count=0` | `Integer` | zero là giá trị có mặt |
| `count=abc` | `Integer` | conversion exception |
| `regions: []` | `List<String>` | kết quả và `@NotEmpty` |
| `retry: {}` | nested record | có tạo object mặc định không |
| Không có retry | nested record | null/default |

## 17. @NotNull, @NotEmpty, @NotBlank: test đúng ý nghĩa

Jakarta Bean Validation phân biệt:

- `@NotNull`: giá trị không được null.
- `@NotEmpty`: không null và không empty, phù hợp với String, collection, map, array được hỗ trợ.
- `@NotBlank`: áp dụng với CharSequence, yêu cầu có ký tự không phải khoảng trắng.

| Dữ liệu | @NotNull | @NotEmpty | @NotBlank |
| --- | --- | --- | --- |
| null | Fail | Fail | Fail |
| String `""` | Pass | Fail | Fail |
| String `"   "` | Pass | Pass vì có độ dài | Fail |
| List rỗng | Pass | Fail | Không áp dụng |
| List một phần tử | Pass | Pass | Không áp dụng |

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record RulesProperties(
        @NotBlank String policyName,
        @NotEmpty List<String> regions,
        @NotEmpty Map<String, String> headers) {
}
~~~

Không đặt `@NotBlank` trên List/Map; đó là loại target không phù hợp.

### Khi bắt buộc có cấu hình tường minh

Một primitive `int attempts` có thể nhận 0 khi không có nguồn. Nếu constraint là `@Min(0)`, giá trị mặc định 0 vẫn được chấp nhận. Khi cần phân biệt thiếu và 0, dùng `Integer` + `@NotNull` hoặc một chính sách kiểm tra sự tồn tại của key.

## 18. @Valid: kiểm tra sâu vào List object

Một List có thể không rỗng nhưng chứa phần tử thiếu field:

~~~yaml
app:
  delivery:
    endpoints:
      - name: primary
        url: ""
~~~

Dùng Bean Validation cho phần tử:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record ValidatedDeliveryProperties(
        @NotEmpty List<@Valid Endpoint> endpoints) {

    public record Endpoint(
            @NotBlank String name,
            @NotBlank String url) {
    }
}
~~~

- `@NotEmpty`: List phải có ít nhất một phần tử.
- `@Valid`: validation đi vào từng `Endpoint`.
- `@NotBlank`: name và url không được thiếu/rỗng/trắng.

Nếu chỉ kiểm tra `@NotEmpty` trên List, phần tử có `url=""` vẫn có thể qua bước kiểm tra collection. Test cần đánh vào từng lớp validation.

### Với nested object đơn

~~~java
@Validated
@ConfigurationProperties(prefix = "app.connection")
public record ConnectionProperties(
        @NotNull @Valid Security security) {

    public record Security(
            @NotBlank String username,
            @NotBlank String password) {
    }
}
~~~

- `@NotNull security` chặn object con bị thiếu.
- `@Valid security` cho phép kiểm tra field của Security.
- `@NotBlank` trên String phát hiện giá trị rỗng.

Đừng dùng chỉ `@Valid` để bắt buộc nested object không null; đối với null, cascading validation thường không đi sâu.

## 19. ApplicationContextRunner: test bean và validation

`ApplicationContextRunner` tạo một context nhỏ, giúp kiểm tra binding và lỗi startup không cần chạy cả hệ thống.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoragePropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ConfigurationPropertiesAutoConfiguration.class,
                        ValidationAutoConfiguration.class))
                .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfig {
    }

    @Test
    void bindsNestedProperties() {
        runner.withPropertyValues(
                "app.storage.bucket=demo",
                "app.storage.retry.attempts=3",
                "app.storage.retry.backoff=2s")
            .run(context -> {
                assertThat(context).hasNotFailed();

                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.retry()).isNotNull();
                assertThat(props.retry().attempts())
                        .isEqualTo(3);
                assertThat(props.retry().backoff())
                        .isEqualTo(Duration.ofSeconds(2));
            });
    }
}
~~~

`@EnableConfigurationProperties` đăng ký đúng class cần kiểm thử. Không nên dựa vào component scanning không có trong context runner rồi kết luận bean binding sai.

### Test không có nested group

~~~java
@Test
void nestedRetryAbsentWithoutDefault() {
    runner.withPropertyValues(
            "app.storage.bucket=demo")
        .run(context -> {
            StorageProperties props =
                    context.getBean(StorageProperties.class);

            assertThat(props.retry()).isNull();
        });
}
~~~

Test này phù hợp với phiên bản `StorageProperties` không có `@DefaultValue` rỗng. Nếu dùng phiên bản có annotation ở nested member, expected phải là object với default.

## 20. ApplicationContextRunner với collection và Map

Class:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        List<String> labels,
        Map<String, Integer> quotas) {
}
~~~

Test:

~~~java
@Test
void bindsListAndMap() {
    runner.withPropertyValues(
            "app.catalog.labels[0]=new",
            "app.catalog.labels[1]=popular",
            "app.catalog.quotas.free=10",
            "app.catalog.quotas.premium=100")
        .run(context -> {
            assertThat(context).hasNotFailed();

            CatalogProperties props =
                    context.getBean(CatalogProperties.class);

            assertThat(props.labels())
                    .containsExactly("new", "popular");

            assertThat(props.quotas())
                    .containsEntry("free", 10)
                    .containsEntry("premium", 100);
        });
}
~~~

Trong test thực, `runner` cần đăng ký `CatalogProperties` bằng:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
static class TestConfig {
}
~~~

Chú ý khi copy các đoạn: một test runner đăng ký `StorageProperties` sẽ không tự tạo `CatalogProperties`. Hãy dùng test config tương ứng với kiểu đang kiểm tra.

### Test thiếu collection

~~~java
@Test
void absentCollectionHasNoValueInRecordWithoutDefault() {
    runner.withPropertyValues(
            "app.catalog.some-other-key=demo")
        .run(context -> {
            CatalogProperties props =
                    context.getBean(CatalogProperties.class);

            assertThat(props.labels()).isNull();
            assertThat(props.quotas()).isNull();
        });
}
~~~

Với JavaBean có `new ArrayList<>()` và `new HashMap<>()` ban đầu, expected có thể là empty collection thay vì null. Test phải phù hợp đúng mô hình class.

## 21. Test @NotEmpty và @NotBlank trong context

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.rules")
public record RulesProperties(
        @NotBlank String policyName,
        @NotEmpty List<String> allowedRegions) {
}
~~~

Test thiếu List:

~~~java
@Test
void requiredListMustBeConfigured() {
    runner.withPropertyValues(
            "app.rules.policy-name=demo")
        .run(context ->
                assertThat(context).hasFailed());
}
~~~

Test chuỗi trống:

~~~java
@Test
void blankNameIsRejected() {
    runner.withPropertyValues(
            "app.rules.policy-name=   ",
            "app.rules.allowed-regions[0]=apac")
        .run(context ->
                assertThat(context).hasFailed());
}
~~~

Test hợp lệ:

~~~java
@Test
void validRulesCanBeBound() {
    runner.withPropertyValues(
            "app.rules.policy-name=demo",
            "app.rules.allowed-regions[0]=apac")
        .run(context -> {
            assertThat(context).hasNotFailed();
            RulesProperties props =
                    context.getBean(RulesProperties.class);
            assertThat(props.allowedRegions())
                    .containsExactly("apac");
        });
}
~~~

Ở đây runner phải được cấu hình:

~~~java
@EnableConfigurationProperties(RulesProperties.class)
~~~

và có Jakarta Validation provider. Nếu không có provider, các constraint có thể không chạy như mong đợi.

## 22. Binder.bind và BindResult: test “không có dữ liệu”

Có thể test ở mức Binder thuần:

~~~java
import java.util.Map;

import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

Binder binder = new Binder(
        new MapConfigurationPropertySource(Map.of()));

BindResult<String> result =
        binder.bind("app.title", String.class);

assertThat(result.isBound()).isFalse();

String title = result.orElse("Untitled");

assertThat(title).isEqualTo("Untitled");
~~~

Một giá trị false hoặc zero vẫn có thể **bound**:

~~~properties
app.enabled=false
app.retry-count=0
~~~

Test:

~~~java
assertThat(
        binder.bind("app.enabled", Boolean.class).get())
        .isFalse();

assertThat(
        binder.bind("app.retry-count", Integer.class).get())
        .isZero();
~~~

### Không nhầm conversion error với absent

~~~properties
app.retry-count=abc
~~~

Binder không thể chuyển thành `Integer`. Lời gọi có thể ném `BindException` trước khi `orElse(3)` có cơ hội cung cấp default.

Một test tốt phải có ba nhánh:

1. Không có `app.retry-count` → unbound.
2. `app.retry-count=0` → bound và bằng 0.
3. `app.retry-count=abc` → lỗi binding.

## 23. Object bind một phần và giới hạn của orElseGet

~~~java
public record ConnectionOptions(
        String host,
        Integer port,
        Duration timeout) {
}
~~~

Nguồn chỉ có:

~~~properties
app.connection.host=api.example.test
~~~

Binder có thể tạo `ConnectionOptions` với host có giá trị, port và timeout null.

~~~java
BindResult<ConnectionOptions> result =
        binder.bind("app.connection", ConnectionOptions.class);
~~~

Nếu `result.isBound()` là true, đoạn:

~~~java
ConnectionOptions options = result.orElseGet(() ->
        new ConnectionOptions(
                "localhost", 8080, Duration.ofSeconds(5)));
~~~

**không tự điền** giá trị mặc định vào port và timeout. `orElseGet` chỉ fallback cho **toàn bộ kết quả unbound**.

Muốn default theo từng field:

- Dùng `@DefaultValue` khi constructor binding.
- Dùng field initializer khi JavaBean mutable.
- Hoặc dùng logic hợp nhất có chủ đích sau binding.

Muốn bắt buộc đủ trường, dùng `@NotNull`/`@NotBlank` và validation. Không lấy `isBound()==true` làm bằng chứng object hoàn chỉnh.

## 24. Test List replacement và Map merge qua nhiều nguồn

Có thể mô phỏng hai `ConfigurationPropertySource` theo thứ tự ưu tiên.

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

var highPriority =
        new MapConfigurationPropertySource(Map.of(
                "app.regions[0]", "local"));

var lowPriority =
        new MapConfigurationPropertySource(Map.of(
                "app.regions[0]", "apac",
                "app.regions[1]", "emea"));

Binder binder = new Binder(
        List.of(highPriority, lowPriority));

List<String> result =
        binder.bind(
                "app.regions",
                Bindable.listOf(String.class))
              .get();

assertThat(result).containsExactly("local");
~~~

Kết quả chứng minh List từ nguồn ưu tiên cao thay List thấp, không nối chúng.

### Map test

Nguồn thấp:

~~~text
app.headers.client=demo
app.headers.region=apac
~~~

Nguồn cao:

~~~text
app.headers.region=emea
~~~

Với target `Map<String,String>`, expected là:

~~~text
client=demo
region=emea
~~~

Khi dựng Binder trong test, phải đưa các nguồn theo đúng **thứ tự ưu tiên mà test định mô phỏng**. Nếu đảo thứ tự, test có thể cho kết quả khác mà không phải lỗi thư viện.

## 25. Test profile bằng @SpringBootTest và @ActiveProfiles

Để kiểm tra file Config Data thật, tạo:

~~~yaml
# application.yaml
app:
  delivery:
    regions: [apac, emea]
~~~

~~~yaml
# application-dev.yaml
app:
  delivery:
    regions: [local]
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class DeliveryProfileTest {

    @Autowired
    DeliveryProperties properties;

    @Test
    void devListReplacesBaseList() {
        assertThat(properties.regions())
                .containsExactly("local");
    }
}
~~~

Class `DeliveryProperties` phải được đăng ký trong ứng dụng test. Test này khác Binder unit test: nó kiểm tra cả giai đoạn nạp `application-dev.yaml` và kết quả khi profile hoạt động.

### Không để test property che lỗi file

Nếu file có:

~~~properties
app.worker.threads=abc
~~~

mà test ghi đè:

~~~java
@SpringBootTest(properties = "app.worker.threads=4")
~~~

thì test có thể pass vì nguồn test ưu tiên cao hơn. Không được xem đó là bằng chứng YAML/Properties gốc hợp lệ.

Khi mục tiêu là kiểm tra đúng file, tránh dùng `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` trên những key cần kiểm tra.

## 26. Biến môi trường cho List index

Tên canonical:

~~~text
app.delivery.endpoints[0].url
~~~

Dạng environment được Spring Boot hỗ trợ:

~~~text
APP_DELIVERY_ENDPOINTS_0_URL
~~~

Chỉ số 0 được bao bằng dấu gạch dưới.

Nhưng một `MapConfigurationPropertySource` đơn giản trong unit test **không nhất thiết có cùng quy tắc đặt tên với system environment source**. Muốn kiểm tra tình huống Kubernetes hoặc Docker thực:

- Chuẩn bị biến môi trường tương ứng trong tiến trình test hoặc môi trường launcher.
- Hoặc sử dụng nguồn `SystemEnvironmentPropertySource` phù hợp.
- Kiểm tra sau khi Spring Boot đã xây `Environment`.
- Không dùng credential thật trong test.

Giữ phân biệt giữa **test Binder nhận canonical key** và **test runtime biến environment thành canonical key**.

## 27. Test “cấu hình thiếu” không nên dùng giá trị mặc định thiếu an toàn

Một cấu hình tùy chọn như `app.display-name` có thể dùng default `"Untitled"`. Nhưng một URL thanh toán hoặc khóa bí mật không nên dùng default giả rồi tiếp tục chạy production.

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String endpoint,
        @NotBlank String clientSecret) {
}
~~~

Test tối thiểu:

1. Thiếu endpoint → context thất bại.
2. Endpoint rỗng → context thất bại.
3. Thiếu client secret → context thất bại.
4. Secret chỉ có khoảng trắng → context thất bại.
5. Có dữ liệu giả hợp lệ → context khởi động.

Trong fixture chỉ dùng `DEMO_ONLY_NOT_A_REAL_SECRET`. Không in record hoặc `Environment` trong test vì `toString()` của record có thể chứa secret.

## 28. Khi nào nên tạo custom validator cấp class?

Có những điều kiện không thể kiểm tra chỉ bằng một field.

Ví dụ: nếu `tls.enabled=true` thì `tls.certificate-path` bắt buộc, nhưng khi TLS tắt thì có thể vắng.

Dùng custom Jakarta `@Constraint` với `ConstraintValidator` ở cấp class để kiểm tra quan hệ giữa hai field.

Test ma trận:

| enabled | certificate-path | Kỳ vọng |
| --- | --- | --- |
| false | missing | Pass nếu chính sách cho phép |
| true | missing | Fail |
| true | blank | Fail |
| true | đường dẫn hợp lệ về mặt định dạng | Pass về mặt config |

Điều này chỉ kiểm tra **hợp lệ của cấu hình**. Nó không chứng minh file chứng chỉ thực sự tồn tại hoặc thư viện TLS đã đọc được, trừ khi test tích hợp bổ sung kiểm tra tầng hệ thống.

## 29. Bảng test cases theo kiểu dữ liệu

### List

| Case | Input | Expected |
| --- | --- | --- |
| Một phần tử | `[apac]` | size=1 |
| Nhiều phần tử | `[apac,emea]` | đúng thứ tự |
| Thiếu | không có key | null/default theo design |
| Empty | `[]` | kiểm tra kết quả và `@NotEmpty` |
| Phần tử thiếu URL | chỉ name | fail nếu có nested validation |
| Ghi đè bởi profile | base 2, dev 1 | List có 1 phần tử từ dev |

### Map

| Case | Input | Expected |
| --- | --- | --- |
| Một key | region=apac | có entry |
| Key đặc biệt | `[/admin]` | giữ dấu / |
| Key có dấu chấm | `[api.v2]` | giữ key literal |
| Nguồn cao thay một key | region=emea | giữ các key không bị ghi đè |
| Empty map | `{}` | expected theo policy |

### Nested object

| Case | Input | Expected |
| --- | --- | --- |
| Đủ field | retry.attempts và retry.backoff | object hợp lệ |
| Thiếu toàn bộ retry | không có retry | null/default/fail tùy thiết kế |
| Empty mapping | retry: {} | kiểm tra constructor default |
| Thiếu một field | có attempts, thiếu backoff | default hoặc validation |
| Sai kiểu | backoff=bad | conversion failure |

### Scalar rỗng và thiếu

| Case | Input | Expected |
| --- | --- | --- |
| Không có String | missing | null/default |
| Chuỗi rỗng | name= | fail nếu `@NotBlank` |
| Khoảng trắng | name=   | fail nếu `@NotBlank` |
| Boolean false | enabled=false | có giá trị false |
| Integer 0 | count=0 | có giá trị 0 |
| Integer không hợp lệ | count=abc | lỗi conversion |

## 30. Các lỗi thường gặp khi kiểm thử

### Lỗi 1 — chỉ xác minh bean tồn tại

~~~java
assertThat(context)
        .hasSingleBean(DeliveryProperties.class);
~~~

Chưa đủ; bean có thể chứa List rỗng, nested object null hoặc giá trị sai. Cần kiểm tra các thành viên theo hợp đồng.

### Lỗi 2 — List bị hiểu là merge

Profile có một phần tử, test kỳ vọng hai phần tử gốc vẫn còn. Quy tắc Spring Boot thường là replacement cho List.

### Lỗi 3 — Map bị hiểu là replacement toàn bộ

Map có thể gộp key từ nhiều nguồn và cùng property thì nguồn ưu tiên cao thắng.

### Lỗi 4 — chỉ kiểm tra Map size

Số lượng key đúng không bảo đảm key literal đúng. Nhất là với dấu `/` và dấu chấm.

### Lỗi 5 — không phân biệt thiếu nhóm và thiếu field

Nested object null khác nested object tồn tại nhưng thiếu thành viên.

### Lỗi 6 — dùng @NotNull thay @NotEmpty cho List bắt buộc có phần tử

List rỗng khác null; `@NotNull` không chặn empty List.

### Lỗi 7 — dùng @NotBlank trên collection

`@NotBlank` phù hợp với String/CharSequence, không phải List/Map.

### Lỗi 8 — thiếu @Valid ở object con

Validation không tự đi sâu vào mọi nested member nếu không có cascading validation phù hợp.

### Lỗi 9 — @DefaultValue cấp field bị coi là tạo cả group

Default ở field con không luôn làm object cha hoặc nested object xuất hiện khi thiếu toàn bộ prefix.

### Lỗi 10 — chuỗi rỗng bị coi là không có key

`app.name=` có thể là String rỗng và cần validation riêng.

### Lỗi 11 — coi Boolean false hoặc Integer 0 là unbound

Đây có thể là dữ liệu được cấu hình rõ, không phải thiếu giá trị.

### Lỗi 12 — fallback che lỗi conversion

`orElse(...)` không nên thay thế trường hợp `retry-count=abc` bằng giá trị mặc định; Binder có thể ném lỗi.

### Lỗi 13 — Test đã override YAML đang cần xác minh

Một `@SpringBootTest(properties=...)` nguồn cao có thể che một file cấu hình hỏng.

### Lỗi 14 — Không đăng ký class trong ApplicationContextRunner

Cần `@EnableConfigurationProperties(Target.class)` hoặc cấu hình tương đương để binder tạo bean.

### Lỗi 15 — Test validation thiếu provider

`@Validated` và constraint không đảm bảo có hành vi mong muốn nếu thiếu Jakarta Bean Validation provider tương thích.

### Lỗi 16 — Test phụ thuộc thứ tự hoặc trạng thái chung

Test A thay đổi một Map mutable và test B dùng lại nó. Nên tạo context và nguồn dữ liệu độc lập.

### Lỗi 17 — So sánh toString của collection

`toString()` không phải hợp đồng binding. Kiểm tra phần tử trực tiếp.

### Lỗi 18 — In dữ liệu bí mật vào log test

Không log toàn bộ properties record chứa API token/password hoặc toàn bộ `Environment`.

## 31. Bài thực hành có đáp án

### Bài 1 — List có thứ tự

Nguồn:

~~~properties
app.regions[0]=apac
app.regions[1]=emea
~~~

**Đáp án:** List có hai phần tử đúng thứ tự. Test với `containsExactly("apac","emea")`.

### Bài 2 — Profile ghi đè List

Base regions=[apac,emea]; dev regions=[local].

**Đáp án:** khi dev là nguồn ưu tiên cao, List có `local`, không tự nối ba phần tử.

### Bài 3 — Map merge

Base headers.client=demo, headers.region=apac. Nguồn cao headers.region=emea.

**Đáp án:** client=demo vẫn còn, region=emea thắng.

### Bài 4 — Map key có dấu /

Nguồn:

~~~properties
app.routes[/admin]=https://admin.example.test
~~~

**Đáp án:** dùng bracket notation và test `containsKey("/admin")`.

### Bài 5 — Nested record thiếu toàn nhóm

Record có `Retry retry`, nhưng chỉ có key `app.storage.bucket`.

**Đáp án:** retry có thể null nếu không có default cấp nested member; cần test và xử lý.

### Bài 6 — Nested record có default rỗng

`@DefaultValue Retry retry` và Retry có `@DefaultValue("3") int attempts`.

**Đáp án:** khi object cha được bind, nested Retry có thể được tạo với attempts=3 dù không có dữ liệu retry riêng.

### Bài 7 — Chuỗi rỗng

~~~properties
app.name=
~~~

**Đáp án:** với String có thể là `""`; `@NotBlank` từ chối.

### Bài 8 — Chuỗi whitespace

~~~properties
app.name=   
~~~

**Đáp án:** `@NotBlank` từ chối, `@NotNull` không tự từ chối.

### Bài 9 — int và Integer

Không có key `app.retry-count`.

**Đáp án:** `int` có thể nhận 0, `Integer` có thể null. Nếu cần phát hiện thiếu rõ ràng, dùng wrapper + `@NotNull`.

### Bài 10 — List có phần tử thiếu field

~~~yaml
app:
  endpoints:
    - name: primary
~~~

**Đáp án:** phải test URL của phần tử. Với `List<@Valid Endpoint>` và `@NotBlank url`, validation có thể chặn.

### Bài 11 — List rỗng và @NotEmpty

Nguồn `allowed-regions: []`.

**Đáp án:** `@NotEmpty` phải từ chối một List rỗng; `@NotNull` không đủ.

### Bài 12 — Dữ liệu không chuyển kiểu

`count=abc` với target Integer.

**Đáp án:** lỗi conversion, không phải missing.

### Bài 13 — Ngữ cảnh test profile

Muốn kiểm tra `application-dev.yaml` ghi đè `application.yaml`.

**Đáp án:** dùng integration test có `@ActiveProfiles("dev")` hoặc startup tương đương.

### Bài 14 — Chỉ số List trong environment

Tên canonical `app.delivery.endpoints[0].url`.

**Đáp án:** `APP_DELIVERY_ENDPOINTS_0_URL` là dạng environment theo quy tắc Spring Boot.

### Bài 15 — Test override che lỗi

File chứa `app.worker.threads=abc`, test thêm `@SpringBootTest(properties="app.worker.threads=4")`.

**Đáp án:** test có thể pass vì đã ghi đè bằng property của test. Không khẳng định file gốc hợp lệ.

## 32. Checklist hoàn tất bộ kiểm thử

**Collection:** Test một/nhiều phần tử, đúng thứ tự, rỗng, thiếu key, phần tử sai, Map special keys, List replacement và Map merge.

**Nested object:** Test đủ field, thiếu toàn nhóm, mapping rỗng, thiếu một field, default cấp thành viên và cấp object, `@Valid`/`@NotNull` đúng vị trí.

**Scalar:** Test missing, empty string, whitespace, null, false, 0, sai kiểu và override.

**Spring Boot:** Đăng ký bean đúng, test context có validation provider, test dùng đúng profile/file thực khi cần, không để test properties che lỗi, không phụ thuộc trạng thái chung, không in secrets.

## 33. Kết luận

Kiểm thử `@ConfigurationProperties` không nên dừng ở một ví dụ YAML hợp lệ. Phải xác định hành vi của từng loại dữ liệu khi **đủ giá trị, thiếu giá trị, rỗng, sai kiểu hoặc bị nguồn khác ghi đè**.

Những nguyên tắc quan trọng:

1. `List` giữa các nguồn thường được **thay thế toàn bộ**, không ghép phần tử.
2. `Map` có thể **gộp các key** từ nhiều nguồn; key trùng được quyết định theo ưu tiên.
3. Nested record có thể là **null** khi không có nhóm con; `@DefaultValue` rỗng trên nested member có thể yêu cầu tạo object với các mặc định.
4. Empty string, whitespace-only, empty List, empty mapping và missing key **không đồng nghĩa**.
5. `@NotNull`, `@NotEmpty`, `@NotBlank` và `@Valid` phục vụ những mục đích khác nhau.
6. `BindResult.isBound()` không chứng minh mọi field đã đủ hoặc đã qua validation.
7. `Binder` phù hợp unit test; `ApplicationContextRunner` phù hợp kiểm tra bean/binding/validation; `@SpringBootTest` phù hợp xác minh file và profile thật.

Một bộ test có ma trận ranh giới rõ ràng sẽ phát hiện sớm cấu hình hỏng trước khi ứng dụng gặp `NullPointerException`, hành vi ghi đè khó hiểu hoặc sự cố production.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — Binder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot — BindResult API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/BindResult.html).
- [Spring Boot — ApplicationContextRunner API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0).
- [Spring Framework — TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html).