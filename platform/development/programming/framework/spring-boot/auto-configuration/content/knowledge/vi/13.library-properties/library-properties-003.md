# Chọn kiểu dữ liệu, giá trị mặc định và nhóm thuộc tính theo chức năng trong thư viện Spring Boot

## Mục tiêu bài học

Khi xây dựng **thư viện hoặc Spring Boot starter**, các khóa cấu hình công khai là một phần của API mà ứng dụng sử dụng thư viện phải hiểu và duy trì. Ví dụ, một thư viện gửi thông điệp có thể cho phép người dùng cấu hình `enabled`, `timeout`, `max-payload`, `mode` và chính sách `retry`. Nếu khai báo mọi giá trị là `String`, đặt mặc định rải rác hoặc gom các khóa không liên quan vào một nhóm, việc sử dụng và bảo trì thư viện sẽ khó hơn.

Bài này tập trung vào ba quyết định thiết kế gắn chặt với nhau:

1. **Kiểu dữ liệu:** chọn kiểu Java thể hiện chính xác ý nghĩa của giá trị cấu hình.
2. **Giá trị mặc định:** định nghĩa trạng thái hợp lý và nhất quán khi người dùng không khai báo khóa.
3. **Nhóm thuộc tính:** sắp xếp các khóa theo chức năng với namespace và đối tượng cấu hình rõ ràng.

Sau bài học, bạn có thể thiết kế một API cấu hình có kiểu với `@ConfigurationProperties`, chọn mặc định bằng `@DefaultValue` cho Java record, xử lý nhóm lồng nhau, đưa properties vào auto-configuration bằng `@EnableConfigurationProperties`, kiểm tra binding bằng `ApplicationContextRunner` và nhận biết các lỗi thường gặp.

## 1. Vì sao cấu hình thư viện cần được thiết kế như API công khai?

Giả sử thư viện có chức năng gửi thông điệp. Một cách khai báo thiếu cấu trúc có thể là:

~~~properties
enabled=true
timeout=5000
size=2097152
retries=3
mode=1
~~~

Các vấn đề:

- Tên `enabled` hoặc `timeout` quá chung, dễ va chạm với cấu hình của thư viện khác.
- `timeout=5000` không nói rõ đơn vị là millisecond hay second.
- `size=2097152` buộc người dùng tự tính đơn vị.
- `mode=1` cần tài liệu riêng để biết giá trị `1` nghĩa là gì.
- `retries` không cho thấy đây là số lần thử lại hay tổng số lần thực hiện.
- Một sai giá trị có thể chỉ được phát hiện rất muộn nếu mã thư viện tự parse chuỗi.

Với Spring Boot, thay vì đọc từng chuỗi bằng `@Value`, thư viện có thể khai báo một **mô hình cấu hình có kiểu**:

~~~text
acme.delivery.enabled
acme.delivery.mode
acme.delivery.timeout
acme.delivery.max-payload
acme.delivery.max-attempts
acme.delivery.retry.max-retries
acme.delivery.retry.backoff
~~~

Lúc này, namespace `acme` là phần riêng do thư viện sở hữu; `delivery` là chức năng; `retry` là nhóm con. Các kiểu Java như `Duration`, `DataSize` và `enum` diễn đạt trực tiếp nghiệp vụ. Đây là API của thư viện dù nó được cấu hình qua YAML, properties, biến môi trường hoặc tham số command line.

## 2. Chọn đúng kiểu dữ liệu thay vì dùng `String` cho mọi thứ

`@ConfigurationProperties` kết hợp với Spring Boot Binder giúp ánh xạ giá trị cấu hình vào trường hoặc constructor parameter của một class/record. Hãy chọn kiểu theo **nghĩa của thông tin**, sau đó xác định phạm vi hợp lệ và mặc định.

| Loại dữ liệu cấu hình | Kiểu Java gợi ý | Ví dụ thuộc tính | Lý do |
| --- | --- | --- | --- |
| Bật/tắt một tính năng hai trạng thái | `boolean` | `enabled: true` | Rõ trạng thái bật/tắt; primitive có giá trị mặc định Java là `false` nếu không khai báo default riêng |
| Cần phân biệt “không khai báo” với `false` | `Boolean` | `feature-enabled` | `null` có thể biểu thị vắng mặt; chỉ dùng khi nghiệp vụ thực sự cần trạng thái thứ ba |
| Số lần thử, số luồng, giới hạn đếm | `int`/`Integer` hoặc `long` | `max-attempts: 3` | Cho phép bind sang số và áp dụng ràng buộc như `@Min(1)` |
| Thời gian chờ/khoảng trễ/TTL | `java.time.Duration` | `timeout: 5s` | Diễn đạt đơn vị, tránh `long` không rõ millisecond/second |
| Kích thước payload/cache/buffer | `org.springframework.util.unit.DataSize` | `max-payload: 2MB` | Dễ đọc hơn số byte thô |
| Tập lựa chọn hữu hạn | Java `enum` | `mode: HTTP` | Giảm giá trị tự do hoặc mã số khó hiểu |
| Tên hiển thị, định danh, token | `String` | `client-name: app-a` | Hợp lý khi thật sự là văn bản, có thể kèm `@NotBlank` |
| Địa chỉ tài nguyên hoặc endpoint | `URI`/URL (khi phù hợp) | `endpoint: https://...` | Tránh tự phân tích và kiểm tra đường dẫn bằng chuỗi thủ công |
| Danh sách các mục cùng loại | `List<T>` | `allowed-topics: [a, b]` | Khai báo tập giá trị có thứ tự |
| Từ khóa tới giá trị | `Map<K,V>` | `headers: {x-app: demo}` | Hợp với tập key linh hoạt, có quy tắc riêng khi bind key chứa ký tự đặc biệt |
| Nhóm tùy chọn liên quan | Record/class lồng | `retry.backoff: 200ms` | Gom thuộc tính thuộc cùng một chức năng |

**Quy tắc chọn kiểu:** hãy ưu tiên kiểu Java phản ánh đúng miền giá trị. Nếu người dùng nhập `max-attempts=abc`, binding số thường thất bại lúc khởi động, dễ phát hiện hơn việc giữ `"abc"` rồi lỗi khi chạy nghiệp vụ.

### 2.1. Số thuần, thời gian và dung lượng khác nhau

Tránh thiết kế:

~~~java
String timeout;       // Ai parse? Đơn vị nào?
long payloadSize;     // Bytes hay kilobytes?
String transportMode; // Cho phép mọi chuỗi, dễ gõ sai.
~~~

Nên sử dụng:

~~~java
Duration timeout;
DataSize maxPayload;
Mode mode;
~~~

Khi cấu hình:

~~~yaml
acme:
  delivery:
    timeout: 1500ms
    max-payload: 2MB
    mode: HTTP
~~~

Spring Boot có thể chuyển đổi các giá trị trên thành đúng kiểu. `Duration` hỗ trợ các hậu tố đơn vị như `ms`, `s`, `m`; `DataSize` hỗ trợ `B`, `KB`, `MB`, `GB` theo cơ chế chuyển đổi của Boot. Khi dùng số không ghi hậu tố, đơn vị mặc định phụ thuộc quy tắc converter và annotation như `@DurationUnit`/`@DataSizeUnit`; với API công khai, **khuyến khích người dùng ghi rõ đơn vị**.

`DataSize.ofMegabytes(2)` biểu diễn 2 MiB theo đơn vị nhị phân (2 × 1024 × 1024 byte). Cần ghi rõ khi thông số có liên quan đến giới hạn thực tế của hệ thống ngoài.

### 2.2. `enum` thích hợp cho tập lựa chọn đóng

~~~java
enum Mode {
    HTTP,
    QUEUE
}
~~~

Người dùng chọn `HTTP` hoặc `QUEUE`. Giá trị lạ như `BANANA` thường gây lỗi binding, giúp phát hiện cấu hình sai. Chỉ chọn `enum` nếu tập giá trị thực sự được thư viện kiểm soát; đừng dùng enum cho danh sách có thể được plugin hoặc đối tác mở rộng động.

### 2.3. Cần phân biệt primitive và kiểu wrapper

`boolean` không mang giá trị `null`; `int` nếu thiếu cấu hình và không có mặc định riêng có thể nhận `0`. Đây là mặc định của kiểu Java, **không nhất thiết là mặc định nghiệp vụ đúng**. Với `Boolean` hoặc `Integer`, `null` có thể biểu thị người dùng không khai báo, nhưng đòi mã sử dụng xử lý trạng thái đó.

Ví dụ: `max-attempts=0` có thể là vô nghĩa, còn `enabled=false` lại là một trạng thái hợp lệ. Hãy quyết định giá trị mặc định theo hợp đồng của thư viện, không để mặc định primitive ngẫu nhiên quyết định nghiệp vụ.

## 3. Nhóm thuộc tính theo chức năng và namespace sở hữu

Một thư viện nên chọn namespace riêng, ví dụ `acme`, thay vì thêm khóa dưới `spring`, `server` hoặc `management` vốn do Spring Boot quản lý. Với nhiều chức năng độc lập, mỗi chức năng có nhánh rõ ràng:

~~~text
acme.delivery.*           # Cấu hình gửi thông điệp
acme.delivery.retry.*     # Nhánh policy retry của delivery
acme.audit.*              # Chức năng audit độc lập
acme.metrics.*            # Chức năng metrics độc lập
~~~

Một cấu hình có thể viết:

~~~yaml
acme:
  delivery:
    enabled: true
    mode: QUEUE
    timeout: 5s
    max-payload: 2MB
    max-attempts: 3
    retry:
      max-retries: 2
      backoff: 200ms
~~~

Cấu trúc này giúp người dùng thấy rõ:

- `enabled`, `mode`, `timeout`, `max-payload`, `max-attempts` điều khiển chức năng **delivery**.
- `retry.max-retries` và `retry.backoff` điều khiển **một chính sách con**.
- `audit` và `metrics` là chức năng có thể được cấu hình, bật/tắt và duy trì độc lập.

### Khi nào lồng một nhóm, khi nào tách thành properties class riêng?

Nên **lồng nhóm con** khi thuộc tính chỉ có ý nghĩa trong vòng đời hoặc trách nhiệm của chức năng cha. Ví dụ `acme.delivery.retry.*` là chính sách thử lại dành riêng cho gửi thông điệp.

Nên **tách prefix và properties class** khi chức năng có lifecycle, chủ sở hữu và API độc lập. Ví dụ `acme.audit.*` có thể được bật hoặc tắt mà không cần dịch vụ delivery. Không nên tạo một `AcmeProperties` khổng lồ chứa cả chục module độc lập chỉ để “gom cho tiện”.

Hạn chế độ sâu không cần thiết. Key `acme.delivery.retry.backoff` dễ hiểu hơn một cây sáu đến tám cấp nếu không có khái niệm nghiệp vụ phân tầng thực sự.

### Quy tắc đặt tên

- Dùng **lowercase kebab-case** cho segment nhiều từ: `max-attempts`, `request-timeout`, `max-payload`.
- Dùng dấu chấm giữa các nhóm: `acme.delivery.retry.backoff`.
- Tên mô tả ý nghĩa, không ràng buộc chi tiết triển khai: `max-attempts` rõ hơn `count1`; `timeout` rõ hơn `t`.
- Không lặp nghĩa dư thừa: trong namespace `acme.delivery`, key `delivery-timeout` thường không cần thiết; `timeout` là đủ.
- Duy trì tên key ổn định. Đổi tên sau khi phát hành có thể làm hỏng cấu hình ứng dụng sử dụng thư viện; nếu bắt buộc đổi, hãy có lộ trình tương thích, deprecation và tài liệu migration.

Spring Boot hỗ trợ **relaxed binding**, nên key chuẩn `max-attempts` có thể bind vào thành phần Java `maxAttempts`. Nhưng tài liệu thư viện nên nhất quán dùng dạng key chuẩn, đặc biệt khi người dùng cấu hình từ nhiều nguồn.

## 4. Định nghĩa giá trị mặc định một cách có chủ đích

Một giá trị mặc định tốt nên:

1. Có hành vi **an toàn**, có thể giải thích được khi ứng dụng không khai báo gì.
2. Đủ thực dụng để bắt đầu sử dụng thư viện nhưng không gây tác động bất ngờ.
3. Nhất quán giữa binding, điều kiện auto-configuration, tài liệu và test.
4. Được gắn với **đúng trường cấu hình** và có test khi thuộc tính vắng mặt.
5. Không chứa credential, secret, endpoint riêng của môi trường hoặc các thông số nguy hiểm cần quyết định rõ ràng từ người dùng.

Ví dụ một contract khả dĩ cho thư viện giả định:

| Key | Kiểu | Mặc định | Giải thích thiết kế |
| --- | --- | --- | --- |
| `acme.delivery.enabled` | `boolean` | `true` | Chức năng chính mặc định bật nếu đó là hợp đồng của starter |
| `acme.delivery.timeout` | `Duration` | `5s` | Không chờ vô thời hạn |
| `acme.delivery.max-payload` | `DataSize` | `2MB` | Có giới hạn rõ ràng |
| `acme.delivery.max-attempts` | `int` | `3` | Tổng số lần thực hiện, gồm lần đầu tiên |
| `acme.delivery.mode` | `Mode` | `HTTP` | Chọn một mode được hỗ trợ |
| `acme.delivery.retry.max-retries` | `int` | `2` | Số lần **thử lại**, không tính lần thực hiện ban đầu |
| `acme.delivery.retry.backoff` | `Duration` | `200ms` | Khoảng chờ giữa các lần retry |

**Chú ý sự khác nhau giữa `max-attempts` và `max-retries`:** với thuật ngữ thông dụng, `max-attempts=3` bao gồm lần gửi đầu và tối đa hai lần thử lại; `max-retries=2` là tối đa hai lần *sau* lần gửi đầu. Nếu dùng cả hai khóa trong cùng một thư viện thật, phải nói rõ cách phối hợp/ưu tiên, tránh hai giới hạn gây hiểu nhầm. Trong ví dụ học tập bên dưới, chúng đại diện cho thông số nhóm chính và chính sách retry để thực hành binding; chưa triển khai thuật toán retry.

### 4.1. Record và `@DefaultValue` trong Spring Boot 3.3

Java 17 record kết hợp constructor binding là một cách phù hợp để mô hình hóa **snapshot cấu hình bất biến**:

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("2MB") DataSize maxPayload,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("HTTP") Mode mode,
        @DefaultValue Retry retry
) {
    public enum Mode { HTTP, QUEUE }

    public record Retry(
            @DefaultValue("2") int maxRetries,
            @DefaultValue("200ms") Duration backoff
    ) {
    }
}
~~~

Đây là **đoạn minh họa phần thân model**, cần `import` cho `ConfigurationProperties`, `DefaultValue`, `Duration`, `DataSize` và phải được Spring Boot đăng ký qua cơ chế configuration properties. Ví dụ test hoàn chỉnh với import ở phần sau.

`@DefaultValue("5s")` áp dụng khi khóa `timeout` không được cung cấp và chuyển chuỗi `5s` thành `Duration`. Tương tự, `@DefaultValue("2MB")` thành `DataSize`, `@DefaultValue("HTTP")` thành `Mode.HTTP`.

**Điểm quan trọng của nested group:** `@DefaultValue` **không đối số** trên thành phần `Retry retry` yêu cầu Binder tạo cả đối tượng nhóm con ngay khi không có khóa `retry.*` nào. Nếu bỏ annotation trống này, với constructor-bound nested object và hoàn toàn không có thuộc tính nhóm con, thành phần `retry` có thể là `null`. Từng trường của `Retry` cũng có `@DefaultValue` riêng để nhận giá trị khi key tương ứng thiếu.

Nếu người dùng đặt `acme.delivery.retry.max-retries=4` nhưng bỏ `retry.backoff`, Binder tạo `Retry` với `maxRetries=4` và `backoff=200ms`.

### 4.2. Default khi binding khác với key tồn tại trong `Environment`

Một ngộ nhận đặc biệt dễ gây lỗi auto-configuration là: “Đã khai báo `@DefaultValue("true")` thì `Environment` chắc chắn chứa `acme.delivery.enabled=true`.”

**Không đúng.** Mặc định của `@ConfigurationProperties` dùng khi **binding vào đối tượng**, không tự thêm một property source mới vào `Environment`. Với ứng dụng không khai báo `acme.delivery.enabled`:

- `DeliveryProperties.enabled()` có thể là `true` do `@DefaultValue`.
- `Environment.containsProperty("acme.delivery.enabled")` vẫn có thể là `false`.
- Một `@ConditionalOnProperty(prefix="acme.delivery", name="enabled")` đơn thuần, với `matchIfMissing=false` mặc định, **không khớp** nếu key không hiện diện, dù properties record có default true.

Nếu muốn bean được tạo khi không khai báo khóa, hãy cho điều kiện cùng hợp đồng mặc định:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
DeliveryClient deliveryClient(DeliveryProperties properties) {
    return new DeliveryClient(properties);
}
~~~

Đây là **minh họa**, giả sử `DeliveryClient` là class có constructor phù hợp. Trong ví dụ chạy được bên dưới, `DeliveryClient` được định nghĩa cụ thể bằng interface đơn giản.

Ngược lại, nếu tính năng yêu cầu opt-in, nên chọn **`enabled=false` mặc định** ở model và `matchIfMissing=false` tại điều kiện. Hai nơi phải nhất quán.

### 4.3. Mặc định trong code hay trong `application.yml` của thư viện?

Với config API do starter cung cấp, nên đặt mặc định chủ đạo trong properties class/record, kèm tài liệu và test. Tránh cố ép cấu hình mặc định bằng file `application.yml` nằm trong JAR thư viện: một thư viện không nên bất ngờ can thiệp vào nguồn cấu hình ứng dụng host.

Ví dụ khi dùng mutable JavaBean thay vì record, mặc định có thể được khai báo tại field:

~~~java
@ConfigurationProperties("acme.delivery")
public class MutableDeliveryProperties {
    private Duration timeout = Duration.ofSeconds(5);

    public Duration getTimeout() { return timeout; }

    public void setTimeout(Duration timeout) { this.timeout = timeout; }
}
~~~

Đây là **đoạn code đầy đủ cho class** nếu import hai kiểu tương ứng, nhưng cần đăng ký bean configuration properties. Với record, mặc định phù hợp hơn nằm ở các constructor parameter/record component thông qua `@DefaultValue`.

Không nên kết hợp nhiều lớp mặc định mâu thuẫn (mặc định field, `@DefaultValue`, mặc định trong điều kiện và mặc định bên trong service) mà không có quy tắc giải quyết minh bạch.

## 5. Kết nối properties với auto-configuration của thư viện

Trong Spring Boot 3.x, một auto-configuration có thể đăng ký typed configuration properties bằng `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(DeliveryProperties.class)
class DeliveryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DeliveryClient.class)
    DeliveryClient deliveryClient(DeliveryProperties properties) {
        return new DeliveryClient(properties);
    }
}
~~~

Đoạn này chỉ minh họa cách wiring; class `DeliveryClient` có constructor tương ứng là giả định. Khi dùng record/constructor binding, **không** tự tạo record qua phương thức `@Bean` hoặc gắn `@Component` rồi mong Spring Boot áp dụng constructor binding như một `@ConfigurationProperties` bean chuẩn. Với auto-configuration, `@EnableConfigurationProperties(DeliveryProperties.class)` là cơ chế rõ ràng.

Một thư viện được phân phối dưới dạng starter thông thường cần liệt kê class auto-configuration trong:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ một dòng là tên class thật:

~~~text
example.library.autoconfigure.DeliveryAutoConfiguration
~~~

File imports **không** liệt kê `DeliveryProperties`; properties class được `@EnableConfigurationProperties` đăng ký. Tổ chức code production thường có:

~~~text
src/main/java/example/library/autoconfigure/
  DeliveryAutoConfiguration.java
  DeliveryProperties.java
  DeliveryClient.java
src/main/resources/META-INF/spring/
  org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đây là cấu trúc minh họa. Tên package/module cụ thể do thư viện sở hữu.

### Quan hệ với `@ConditionalOnMissingBean`

Properties chỉ chứa **dữ liệu cấu hình**. Điều kiện `@ConditionalOnMissingBean` chỉ đăng ký một bean mặc định nếu ứng dụng chưa cung cấp bean cùng kiểu. Hai cơ chế có trách nhiệm khác nhau:

- `@ConfigurationProperties` trả lời “Ứng dụng muốn cấu hình gì?”.
- `@ConditionalOnProperty` trả lời “Khi nào chức năng nên bật?”.
- `@ConditionalOnMissingBean` trả lời “Có cần tạo implementation mặc định không?”.

Không đặt logic nghiệp vụ hoặc kết nối mạng trong constructor của properties record. Hãy để service/client dùng các giá trị đã bind và được kiểm tra hợp lệ.

## 6. Ví dụ chạy được: record có mặc định, nested group và test với `ApplicationContextRunner`

Ví dụ hoàn chỉnh dưới đây tập trung vào binding và default, không gửi request mạng hay chạy thuật toán retry. Nó tạo một `DeliveryClient` đơn giản để quan sát mode và tổng attempts, đồng thời kiểm tra trường hợp tắt chức năng.

**Điều kiện:** Java 17+; Spring Boot 3.3.x; JUnit Jupiter, AssertJ và `ApplicationContextRunner` từ `spring-boot-starter-test`.

**Tệp:** `src/test/java/example/library/DeliveryPropertiesBindingTest.java`

~~~java
package example.library;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.util.unit.DataSize;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DeliveryAutoConfiguration.class));

    @Test
    void usesTypedDefaultsWhenNoKeysAreConfigured() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DeliveryProperties.class);
            assertThat(context).hasSingleBean(DeliveryClient.class);

            DeliveryProperties p = context.getBean(DeliveryProperties.class);
            assertThat(p.enabled()).isTrue();
            assertThat(p.timeout()).isEqualTo(Duration.ofSeconds(5));
            assertThat(p.maxPayload()).isEqualTo(DataSize.ofMegabytes(2));
            assertThat(p.maxAttempts()).isEqualTo(3);
            assertThat(p.mode()).isEqualTo(DeliveryProperties.Mode.HTTP);

            assertThat(p.retry()).isNotNull();
            assertThat(p.retry().maxRetries()).isEqualTo(2);
            assertThat(p.retry().backoff()).isEqualTo(Duration.ofMillis(200));

            assertThat(context.getBean(DeliveryClient.class).profile())
                    .isEqualTo("HTTP/3");

            // Giá trị default của model không tự bổ sung một property source.
            assertThat(context.getEnvironment()
                    .containsProperty("acme.delivery.enabled")).isFalse();
        });
    }

    @Test
    void bindsOverridesAndKeepsMissingNestedDefaults() {
        runner.withPropertyValues(
                    "acme.delivery.timeout=1500ms",
                    "acme.delivery.max-payload=512KB",
                    "acme.delivery.max-attempts=6",
                    "acme.delivery.mode=QUEUE",
                    "acme.delivery.retry.max-retries=4")
                .run(context -> {
                    DeliveryProperties p = context.getBean(DeliveryProperties.class);

                    assertThat(p.enabled()).isTrue();
                    assertThat(p.timeout()).isEqualTo(Duration.ofMillis(1500));
                    assertThat(p.maxPayload()).isEqualTo(
                            DataSize.ofKilobytes(512));
                    assertThat(p.maxAttempts()).isEqualTo(6);
                    assertThat(p.mode()).isEqualTo(DeliveryProperties.Mode.QUEUE);
                    assertThat(p.retry().maxRetries()).isEqualTo(4);
                    assertThat(p.retry().backoff()).isEqualTo(
                            Duration.ofMillis(200));
                    assertThat(context.getBean(DeliveryClient.class).profile())
                            .isEqualTo("QUEUE/6");
                });
    }

    @Test
    void disabledPropertyStopsOnlyTheDefaultClientBean() {
        runner.withPropertyValues("acme.delivery.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(DeliveryProperties.class);
                    assertThat(context).doesNotHaveBean(DeliveryClient.class);
                    assertThat(context.getBean(DeliveryProperties.class)
                            .enabled()).isFalse();
                });
    }

    @Test
    void invalidNumericValueFailsDuringBinding() {
        runner.withPropertyValues("acme.delivery.max-attempts=not-a-number")
                .run(context -> assertThat(context).hasFailed());
    }

    interface DeliveryClient {
        String profile();
    }

    @ConfigurationProperties(prefix = "acme.delivery")
    record DeliveryProperties(
            @DefaultValue("true") boolean enabled,
            @DefaultValue("5s") Duration timeout,
            @DefaultValue("2MB") DataSize maxPayload,
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("HTTP") Mode mode,
            @DefaultValue Retry retry
    ) {
        enum Mode { HTTP, QUEUE }

        record Retry(
                @DefaultValue("2") int maxRetries,
                @DefaultValue("200ms") Duration backoff
        ) {
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class DeliveryAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.delivery",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true)
        @ConditionalOnMissingBean(DeliveryClient.class)
        DeliveryClient deliveryClient(DeliveryProperties properties) {
            return () -> properties.mode().name()
                    + "/" + properties.maxAttempts();
        }
    }
}
~~~

### Vì sao ví dụ này kiểm tra đủ ba quyết định?

1. **Chọn kiểu:** `Duration`, `DataSize`, `enum` và `int` được bind thành đúng kiểu; số vô nghĩa `not-a-number` làm context khởi động thất bại.
2. **Mặc định:** khi không khai báo key, các `@DefaultValue` vẫn hoạt động, và `@DefaultValue` trống tạo được nested `Retry`.
3. **Nhóm:** các key `acme.delivery.retry.*` bind vào `Retry` tách biệt; ghi đè `max-retries` không làm mất default `backoff`.

Test về `enabled=false` minh họa cách phối hợp default của model với điều kiện đăng ký client. Khi tắt, **properties bean vẫn tồn tại** để chứa giá trị cấu hình, còn client mặc định không được tạo.

Nếu class `DeliveryProperties` được đưa ra file production riêng thì record nên được khai báo `public` và đặt trong file `DeliveryProperties.java`; các lớp nested trong test được dùng để giữ ví dụ **chạy được trong một tệp test**.

### Dependency Gradle và lệnh chạy

Trong dự án Gradle **đã có Spring Boot plugin hoặc BOM quản lý version** (Spring Boot 3.3.x), các dependency chính cho ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Tạo metadata để IDE gợi ý khóa cấu hình của thư viện:
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy trong module có test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.library.DeliveryPropertiesBindingTest"

# Windows
gradlew.bat test --tests "example.library.DeliveryPropertiesBindingTest"
~~~

**Kết quả kỳ vọng:** bốn test PASS. Trong test 1, `DeliveryClient.profile()` trả về `HTTP/3`; trong test 2 trả về `QUEUE/6`; trong test 3 client không tồn tại; trong test 4 binding sai kiểu khiến context startup thất bại và phép assert `hasFailed()` thành công. Test không có lệnh `System.out.println`, vì vậy không có stdout cố định của ứng dụng; kết quả hiển thị phụ thuộc Gradle test logging. Các kết quả này là **kỳ vọng theo mã**, không phải log đã thực thi trong bài.

## 7. Kiểm tra ràng buộc giá trị với Bean Validation

Chọn đúng kiểu dữ liệu mới chỉ là bước đầu. Ví dụ `max-attempts=-10` **vẫn là một số nguyên hợp lệ khi binding**, nhưng có thể là giá trị nghiệp vụ không hợp lệ. Tương tự, `timeout=-5s` có thể bind thành `Duration` âm; nên quyết định rõ có cho phép hay không.

Đối với properties class/record, Spring Boot có thể áp dụng Jakarta Bean Validation khi:

1. Có implementation Bean Validation trên classpath (ví dụ starter `spring-boot-starter-validation`).
2. Properties class được chú thích `@Validated`.
3. Các giá trị có constraint như `@Min(1)`, `@NotBlank`, `@NotNull`; sử dụng `@Valid` để cascade xuống nhóm nested.

Ví dụ **minh họa các annotation** (không phải tệp độc lập; cần import `@Validated`, `@Min`, `@Valid` và các kiểu liên quan):

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
@Validated
record ValidatedDeliveryProperties(
        @Min(1) int maxAttempts,
        @Valid @DefaultValue Retry retry
) {
    record Retry(@Min(0) int maxRetries) {
    }
}
~~~

Nếu không khai báo `max-attempts`, giá trị nguyên mặc định của `int` là `0`, nên constraint `@Min(1)` giúp phát hiện rằng thư viện đã quên cung cấp mặc định hoặc đánh dấu khóa bắt buộc. Nếu muốn có default 3, thêm `@DefaultValue("3")` vào thành phần `maxAttempts`.

**Quyết định thiết kế:** cần phân biệt lỗi **không chuyển đổi được kiểu** (ví dụ `max-attempts=abc`) và lỗi **vi phạm quy tắc nghiệp vụ** (ví dụ `max-attempts=-1`). Binder giúp xử lý loại đầu; Bean Validation giúp xử lý loại sau. Chúng bổ sung cho nhau.

Nếu nested object cần có ngay cả khi không cấu hình key nào, `@DefaultValue` trống giúp nó được tạo trong constructor binding; đồng thời `@Valid` giúp kiểm tra constraint bên trong khi validation được bật.

Đừng chọn một giá trị mặc định chỉ để “qua validation” nếu nó không thể dùng an toàn. Với secret hoặc endpoint bắt buộc, có thể tốt hơn khi **không có default** và fail fast bằng ràng buộc phù hợp.

## 8. Metadata và tài liệu: giúp người dùng thấy kiểu, default và nhóm

Với thư viện/starter, người dùng thường gõ cấu hình trong IDE. Spring Boot cung cấp **configuration metadata processor** để sinh:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Annotation processor của Spring Boot có thể thu thập tên khóa, kiểu, mô tả và mặc định từ `@ConfigurationProperties`. Đây là công cụ giúp IDE gợi ý đúng key, nhóm và giá trị, đồng thời giúp reviewer kiểm tra API cấu hình.

Khi viết class thường có field, đặt Javadoc mô tả cho từng thuộc tính. Với **record**, mô tả record component qua tag `@param` trong Javadoc của record; ví dụ:

~~~java
/**
 * Configuration for the delivery feature.
 *
 * @param enabled whether delivery is enabled
 * @param timeout maximum wait time for a delivery operation
 * @param maxPayload maximum accepted payload size
 */
@ConfigurationProperties(prefix = "acme.delivery")
public record BriefDeliveryProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("2MB") DataSize maxPayload
) {
}
~~~

Đoạn trên minh họa cách viết metadata Javadoc; cần import các kiểu như ở ví dụ test. Với metadata sinh ra, kiểm tra tên key thật và type/default của chúng. Đừng tự cho rằng IDE sẽ hiểu nhóm con đúng nếu class không được compiler/annotation processor nhận diện.

Tài liệu cho mỗi key nên thể hiện ít nhất: **tên key**, **kiểu**, **đơn vị**, **default**, **phạm vi hợp lệ**, **ảnh hưởng khi đổi giá trị** và **mối quan hệ với các key khác**. Đặc biệt, một default có thể thay đổi cách ứng dụng hoạt động ngay khi nâng phiên bản starter; thay đổi default cần được xem như thay đổi hành vi công khai.

## 9. Phân biệt thiết kế mặc định với nguồn cấu hình thật

Giả sử `@DefaultValue("5s") Duration timeout` là default của thư viện. Ứng dụng sử dụng thư viện có thể đặt:

~~~properties
acme.delivery.timeout=2s
acme.delivery.mode=QUEUE
~~~

Hoặc cùng ý nghĩa ở YAML:

~~~yaml
acme:
  delivery:
    timeout: 2s
    mode: QUEUE
~~~

Giá trị người dùng cung cấp (theo nguồn cấu hình có hiệu lực trong `Environment`) sẽ được Binder dùng thay cho default của component. Trong ứng dụng thực tế, giá trị có hiệu lực có thể đến từ file profile, environment variable hoặc command-line argument tùy cơ chế ưu tiên nguồn cấu hình của Boot.

**Nguyên tắc:** default từ `@DefaultValue` chỉ được dùng cho thành phần **không có giá trị để bind**; nó không nên ghi đè quyết định hợp lệ của người dùng. Điều kiện và hành vi runtime cũng phải đọc từ cùng contract, tránh một nơi dùng `timeout=5s` nhưng service khác tự mặc định `30s`.

Với danh sách/collection, hãy thận trọng khi chọn mặc định và cách ghép nguồn cấu hình: danh sách không phải lúc nào cũng được cộng dồn giữa các nguồn; Spring Boot có quy tắc override/binding riêng. Tránh giả định danh sách từ profile A và profile B sẽ tự động nối nhau.

## 10. Lỗi phổ biến khi thiết kế properties cho thư viện

1. **Dùng `String` cho số, thời gian hoặc dung lượng.** Khi đó mã phải tự parse; nên chọn `int`, `Duration`, `DataSize` theo ý nghĩa dữ liệu.
2. **Ghi số thời gian trần không giải thích đơn vị.** `timeout=5000` có thể bị hiểu sai; khuyến khích `timeout=5s` hoặc `5000ms`.
3. **Để mặc định primitive quyết định nghiệp vụ.** `max-attempts=0` vì chưa có default có thể làm chức năng không chạy; hãy đặt `@DefaultValue("3")` hoặc dùng validation nếu cần cấu hình bắt buộc.
4. **Dùng `Boolean` khi chỉ cần hai trạng thái**, rồi để `null` lan vào service. `Boolean` chỉ có giá trị thiết kế khi thật sự có ý nghĩa “chưa chỉ định”.
5. **Đặt các khóa vào namespace `spring`, `server`, `management`.** Các prefix đó do Spring Boot quản lý; dùng namespace mà thư viện sở hữu.
6. **Gom mọi thứ vào một nhóm phẳng.** `retry-backoff`, `audit-enabled`, `metrics-port` rải trong cùng class làm mất ranh giới chức năng; nên dùng nhóm riêng.
7. **Tạo quá nhiều lớp nested cho một ý tưởng đơn giản.** Cây cấu hình sâu và không ổn định gây khó đọc, khó duy trì backward compatibility.
8. **Thiếu default cho nested constructor-bound object.** Nếu không có khóa nhóm con, nested record có thể `null`; dùng `@DefaultValue` trống và default component khi muốn nhóm luôn tồn tại.
9. **Cho rằng default của `@ConfigurationProperties` là một key đã được thêm vào `Environment`.** Điều kiện `@ConditionalOnProperty` có thể xử lý key thiếu khác với record default; dùng `matchIfMissing` nhất quán.
10. **Nhầm hợp lệ về kiểu với hợp lệ về nghiệp vụ.** `-10` là số nguyên nhưng có thể sai cho `max-attempts`; thêm Bean Validation cho khoảng giá trị.
11. **Không ghi tài liệu về default hoặc âm thầm đổi default.** Ứng dụng có thể đổi hành vi sau khi nâng version thư viện dù file cấu hình không thay đổi.
12. **Không tạo metadata cấu hình.** Người dùng thiếu gợi ý key, type và description trong IDE; thêm `spring-boot-configuration-processor` khi phát hành starter.
13. **Gắn `@Component` lên constructor-bound record.** Với record configuration properties, dùng `@EnableConfigurationProperties` hoặc properties scan thay vì đăng ký như một bean thường.
14. **Lưu API token/password mặc định trong source.** Secret nên được cung cấp bằng cơ chế cấu hình/secret manager phù hợp; không hard-code giá trị bảo mật vào starter.
15. **Chỉ test khi người dùng cấu hình đầy đủ.** Bỏ sót nhánh tất cả key vắng mặt, ghi đè một vài key, key sai kiểu và giá trị bị tắt.

## 11. Checklist thiết kế trước khi phát hành starter

Đọc từng mục như một câu hỏi review:

- Namespace và nhóm thuộc tính đã thể hiện **chủ sở hữu và chức năng** chưa?
- Mỗi key có **kiểu Java đúng**, đặc biệt với `Duration`, `DataSize` và enum?
- Những khóa có đơn vị đã dùng kiểu/giá trị dễ hiểu chưa?
- Default của mỗi key có được **quy định và test** khi người dùng không khai báo?
- Nested group vắng mặt có gây `null` ngoài dự kiến không?
- Có giá trị nào cần validation nhưng mới chỉ kiểm tra đúng kiểu không?
- Các điều kiện auto-configuration có nhất quán với default trong properties record không?
- Metadata IDE có mô tả key, kiểu, mặc định và Javadoc đầy đủ không?
- Thư viện có vô tình phụ thuộc hoặc ghi đè namespace của Spring Boot không?
- Có test với default, override từng phần, explicit `false` và input sai kiểu không?

## 12. Bài tập tự kiểm tra

**Câu 1.** Thư viện nhận `upload-timeout=3000`. Vì sao `Duration` tốt hơn `int`?

**Đáp án:** `Duration` biểu đạt bản chất thời gian, hỗ trợ đơn vị minh bạch như `3s` hoặc `3000ms`, và giảm việc tự quy đổi đơn vị trong code.

**Câu 2.** Một record có `@DefaultValue("true") boolean enabled`, nhưng người dùng không có key `enabled`. `@ConditionalOnProperty(name="enabled")` với `matchIfMissing=false` có tự khớp không?

**Đáp án:** Không. Default của record khi bind không tự tạo key trong `Environment`. Điều kiện được đánh giá trên giá trị có hiệu lực của `Environment`.

**Câu 3.** Người dùng chỉ khai báo `acme.delivery.retry.max-retries=4`; các field còn lại có `@DefaultValue`. Cần chú ý gì với nhóm `retry`?

**Đáp án:** Binder có thể tạo nested record khi có key nhóm con, và dùng `@DefaultValue` cho các component thiếu. Nếu toàn bộ `retry.*` vắng mặt và muốn object luôn non-null, đánh dấu thành phần nhóm con bằng `@DefaultValue` trống.

**Câu 4.** Key `acme.delivery.max-attempts=-4` có kiểu số hợp lệ. Chỉ dùng binder đã đủ bảo vệ logic chưa?

**Đáp án:** Chưa. Thêm ràng buộc nghiệp vụ, ví dụ `@Min(1)` với `@Validated` và Bean Validation provider phù hợp.

**Câu 5.** Một thư viện có cả delivery và audit, nên để cả hai trong `acme.properties.*` hay tách nhóm?

**Đáp án:** Nếu là hai chức năng độc lập, nên có nhánh rõ nghĩa như `acme.delivery.*` và `acme.audit.*`. Các cấu trúc con như `acme.delivery.retry.*` chỉ lồng dưới chức năng sở hữu chúng.

## 13. Kết luận áp dụng

**Kiểu dữ liệu**, **giá trị mặc định** và **nhóm thuộc tính** phải được thiết kế cùng nhau. Hãy chọn `@ConfigurationProperties` cho API cấu hình của thư viện; dùng `Duration`, `DataSize`, enum và số có ràng buộc thay cho chuỗi mơ hồ; nhóm các key dưới prefix riêng và theo chức năng; đặt default có chủ đích (ví dụ `@DefaultValue` với record); sau đó kiểm tra cả trường hợp **không có key**, **ghi đè một phần** và **cấu hình sai**.

Chú ý nhất ở auto-configuration: default của đối tượng properties **không đồng nghĩa** với property có sẵn trong `Environment`; điều kiện `@ConditionalOnProperty` phải được cấu hình phù hợp với chính sách default của thư viện.

### Tài liệu Spring Boot chính thức

- [Spring Boot 3.3 — Externalized Configuration: Type-safe Configuration Properties, DefaultValue, Conversion, Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration: Configuration Keys](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 Javadoc — @ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot 3.3 Javadoc — @DefaultValue](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html)
