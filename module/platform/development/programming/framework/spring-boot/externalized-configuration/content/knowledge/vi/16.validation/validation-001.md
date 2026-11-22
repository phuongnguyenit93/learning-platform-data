# Vì sao cần kiểm tra cấu hình ngay khi khởi động

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Kiểm tra hợp lệ

## 1. Đặt vấn đề: ứng dụng chạy được chưa chắc đã sẵn sàng phục vụ

Một ứng dụng Spring Boot có thể biên dịch thành công, đóng gói JAR thành công và thậm chí mở cổng HTTP thành công, nhưng vẫn chứa **cấu hình thiếu hoặc không hợp lệ**. Ví dụ:

- URL của hệ thống thanh toán bị bỏ trống.
- Thời gian chờ kết nối được cấu hình thành chuỗi không chuyển được sang `Duration`.
- Số lần thử lại là `0` trong khi chính sách nghiệp vụ yêu cầu ít nhất một lần thực hiện.
- Một nhóm thuộc tính của đối tác bị thiếu, nhưng code chỉ truy cập tới nó khi có request đầu tiên.
- Tên key của biến môi trường bị gõ nhầm nên ứng dụng âm thầm dùng giá trị mặc định không phù hợp.
- Credential bắt buộc không được mount trong container, nhưng lỗi chỉ xuất hiện khi giao dịch đầu tiên đi qua chức năng đó.

Nếu không kiểm tra sớm, hệ thống có thể tạo một trạng thái nguy hiểm: **deployment báo thành công nhưng một phần chức năng đã hỏng**. Sự cố lúc đó chuyển từ một lỗi cấu hình rõ ràng thành timeout, HTTP 500, mất đơn hàng, xử lý sai dữ liệu hoặc rollback khó khăn trong giờ cao điểm.

**Kiểm tra cấu hình ngay khi khởi động (startup configuration validation)** là cách chuyển những lỗi có thể phát hiện tĩnh từ thời điểm người dùng bắt đầu sử dụng sang giai đoạn ứng dụng đang được khởi tạo. Đây là một nguyên tắc **fail fast**: nếu cấu hình bắt buộc sai, dừng sớm và thông báo nguyên nhân cụ thể thay vì tiếp tục chạy với giả định thiếu căn cứ.

Trong Spring Boot, hướng tiếp cận điển hình là khai báo cấu hình có kiểu bằng `@ConfigurationProperties`, sau đó kết hợp `@Validated`, Bean Validation, conversion của Binder và kiểm tra điều kiện nghiệp vụ khi cần.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích được chi phí và rủi ro của việc phát hiện sai cấu hình quá muộn.
2. Phân biệt **thiếu giá trị**, **sai kiểu**, **không đạt ràng buộc** và **không đáp ứng điều kiện môi trường thực tế**.
3. Thiết kế một Java record cấu hình có kiểu, bật validation và đăng ký bean đúng cách.
4. Áp dụng `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@NotEmpty`, `@Valid` và `@Validated` theo đúng ý nghĩa.
5. Nhận biết default, field primitive, nested object và các nguồn cấu hình có thể che giấu dữ liệu thiếu.
6. Viết bài test xác nhận ứng dụng từ chối khởi động với cấu hình không hợp lệ.
7. Phân biệt **startup validation**, **readiness/health checks** và việc giám sát dependency đang chạy.
8. Tránh làm lộ secret trong log và thông điệp lỗi validation.

## 2. Tại sao kiểm tra lúc startup tốt hơn kiểm tra khi có request?

### 2.1. Lỗi xuất hiện ở một nơi dễ quan sát

Nếu một bean cấu hình được validate trong lúc tạo ApplicationContext, ứng dụng có thể không khởi động được và ghi nhận thông tin về key sai. Công cụ triển khai có thể phát hiện tiến trình thoát, container không sẵn sàng hoặc rollout không tiến triển.

Ngược lại, nếu để tới request đầu tiên:

~~~java
@Service
public class OrderService {

    private final Environment environment;

    public OrderService(Environment environment) {
        this.environment = environment;
    }

    public String paymentEndpoint() {
        // Nếu chưa được cấu hình, giá trị có thể null.
        return environment.getProperty("payment.gateway.endpoint");
    }
}
~~~

thì lỗi chỉ lộ ra khi một nhánh nghiệp vụ gọi `paymentEndpoint()` và thực sự sử dụng giá trị. Ứng dụng có thể đã nhận nhiều traffic ở các route khác, tạo cảm giác triển khai thành công.

Kiểm tra ở startup giúp lỗi được phát hiện **trước khi đường xử lý nghiệp vụ phụ thuộc vào nó**.

### 2.2. Giảm độ mơ hồ khi chẩn đoán

Một lỗi binding như:

~~~text
Failed to bind properties under 'orders.client.retry.max-attempts'
~~~

thường trực tiếp hơn nhiều so với một `NullPointerException` hoặc lỗi remote call không đủ ngữ cảnh xuất hiện sau đó. Tên và cấu trúc lỗi thực tế phụ thuộc phiên bản Spring Boot, nhưng mục tiêu là chỉ rõ **prefix**, **property**, **kiểu dữ liệu** hoặc **constraint** liên quan.

Ví dụ, khi code gặp HTTP timeout, nguyên nhân có thể đến từ mạng, DNS, service ngoài hoặc một cấu hình timeout quá ngắn. Nếu giá trị timeout được kiểm tra và ràng buộc ngay lúc startup, ít nhất ta đã loại bỏ một lớp nguyên nhân cấu hình không hợp lệ.

### 2.3. Tránh trạng thái hoạt động một phần không được thiết kế

Một service có thể cung cấp REST endpoints, gửi email, xử lý sự kiện và chạy batch job. Nếu email credential thiếu nhưng chỉ tác động khi gửi thông báo, ứng dụng có thể xử lý đơn hàng thành công mà không thể gửi thông báo bắt buộc.

Khi email là một phần thiết yếu của hệ thống, thiếu credential nên là lỗi startup hoặc lỗi readiness theo một chính sách cụ thể. Khi email chỉ là tính năng tùy chọn, hệ thống có thể cho phép startup nhưng phải **tắt tính năng một cách tường minh** và quan sát được; không nên âm thầm tiếp tục với object cấu hình null.

### 2.4. Giúp rollback và vận hành có cơ sở

Trong một deployment dùng Kubernetes hoặc nền tảng orchestration khác, fail fast có thể giúp vòng triển khai phát hiện container mới không thể chạy theo cấu hình được cấp. Nhóm vận hành có thể xem lý do cấu hình, khôi phục manifest/secret hoặc rollback bản triển khai trước.

Điều này không tự đảm bảo rollout an toàn: chính sách restart, liveness/readiness probe, rollout strategy và năng lực phục hồi của nền tảng vẫn phải được thiết kế đúng. Nhưng từ chối startup với cấu hình bắt buộc sai thường là tín hiệu **chính xác hơn** việc giữ một tiến trình lỗi chờ nhận traffic.

## 3. Bốn lớp kiểm tra khác nhau

Không nên gộp mọi loại “cấu hình có vấn đề” thành một bài toán.

| Lớp | Ví dụ | Cơ chế thường dùng |
| --- | --- | --- |
| **Có tồn tại hay không** | Thiếu `orders.client.base-url` | `@NotNull`, `@NotBlank`, binding required contract |
| **Chuyển đổi kiểu** | `orders.client.timeout=fast` nhưng field là `Duration` | Spring Boot Binder và converters |
| **Ràng buộc giá trị** | `retry.max-attempts=0` nhưng phải ít nhất 1 | Jakarta Bean Validation hoặc custom validator |
| **Sẵn sàng của hạ tầng** | URL đúng định dạng nhưng đối tác đang mất kết nối | Health/readiness checks, connectivity checks theo chính sách |

Ba lớp đầu là nơi **startup validation** đặc biệt hữu ích. Lớp cuối phụ thuộc vào trạng thái hệ thống bên ngoài, có thể thay đổi ngay sau khi ứng dụng khởi động. Nó cần thêm cơ chế quan sát và ứng phó runtime.

### 3.1. Thiếu property không giống sai kiểu

Với record:

~~~java
public record RetryProperties(int maxAttempts) {}
~~~

nếu không có `max-attempts`, kiểu primitive `int` có thể nhận giá trị mặc định `0` khi object được tạo. Đó **không phải bằng chứng** người vận hành đã cố ý cấp số 0.

Nếu giá trị bắt buộc phải ít nhất 1, `@Min(1)` sẽ phát hiện số 0. Nếu cần phân biệt **vắng mặt** với **được cấp giá trị bằng 0**, cân nhắc dùng `Integer` với `@NotNull` và `@Min(1)`.

### 3.2. Sai định dạng không giống sai quy tắc nghiệp vụ

Ví dụ `connect-timeout=not-a-duration` có thể thất bại khi chuyển sang `Duration`. Trong khi `connect-timeout=0ms` có thể chuyển đổi được nhưng lại không đáp ứng yêu cầu timeout dương của ứng dụng.

Binder giải quyết **chuyển đổi kiểu**; validation hoặc kiểm tra nghiệp vụ giải quyết **ý nghĩa của giá trị**.

### 3.3. URL có thể đúng cú pháp nhưng không truy cập được

`https://partner.example.test` có thể là một URI hợp lệ, nhưng remote service có thể không tồn tại, DNS sai hoặc firewall chặn. `@NotNull URI` chỉ đảm bảo field không thiếu và cơ chế conversion chấp nhận giá trị; nó **không bảo đảm endpoint hoạt động**.

Với dependency bắt buộc, có thể thêm readiness/health checks hoặc kiểm tra kết nối sớm với timeout phù hợp. Tuy nhiên, cần tránh khóa cứng toàn bộ ứng dụng chỉ vì một dependency tùy chọn tạm thời không sẵn sàng.

## 4. Cấu hình có kiểu là nền tảng của kiểm tra sớm

### 4.1. File YAML ví dụ

Ứng dụng xử lý đơn hàng cần một HTTP client gọi đối tác. Trong `src/main/resources/application.yml`:

~~~yaml
orders:
  client:
    base-url: "https://orders.partner.example"
    connect-timeout: 2s
    request-timeout: 5s
    enabled: true
    allowed-regions:
      - "apac"
      - "eu"
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Chúng ta muốn một hợp đồng cấu hình:

- `base-url` bắt buộc.
- `connect-timeout`, `request-timeout` bắt buộc và phải có ý nghĩa hợp lý.
- `retry.max-attempts` ít nhất là 1 và không vượt giới hạn vận hành.
- `retry.backoff` bắt buộc khi có retry.
- `allowed-regions` phải có ít nhất một phần tử không rỗng.
- `enabled` là quyết định có chủ đích: nếu muốn yêu cầu khai báo tường minh, kiểu `Boolean` khác kiểu primitive `boolean`.

### 4.2. Dùng `@ConfigurationProperties` với record

Ví dụ cho Spring Boot 3.x và Java 17+:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "orders.client")
@Validated
public record OrderClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @NotNull Boolean enabled,
        @NotEmpty List<@NotBlank String> allowedRegions,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) @Max(10) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

Các thành phần làm việc như sau:

- `@ConfigurationProperties(prefix = "orders.client")` yêu cầu Binder lấy các key dưới nhóm `orders.client.*`.
- `@Validated` kích hoạt validation của bean properties khi cơ chế validator phù hợp có mặt.
- `@NotNull` trên field tham chiếu ngăn một giá trị bắt buộc bị bỏ trống.
- `@NotEmpty` trên list yêu cầu có phần tử; `@NotBlank` ở list elements yêu cầu mỗi vùng không chỉ gồm khoảng trắng khi container-element validation được hỗ trợ.
- `@Min(1)` và `@Max(10)` ràng buộc khoảng giá trị cho số lần thực hiện.
- `@Valid` trên nested `Retry` yêu cầu validation đi sâu vào các constraint bên trong.
- `@NotNull` trên `Retry retry` xử lý trường hợp cả nhóm nested bị thiếu.

Với class cụ thể, không cần đặt mọi rule trong YAML hay trong service. Hợp đồng cấu hình được biểu diễn gần nhau trong một Java type.

### 4.3. Thêm Bean Validation dependency

Trong ứng dụng Spring Boot dùng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Trong Spring Boot 3, các constraint Bean Validation thường nằm ở package `jakarta.validation.constraints`; `@Valid` nằm trong `jakarta.validation`.

Annotation riêng lẻ không phải một chương trình validation hoàn chỉnh. Cần có implementation và tích hợp validator tương ứng để chúng thực sự được đánh giá.

### 4.4. Đăng ký properties bean

Lớp ứng dụng:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Hoặc đăng ký tường minh bằng:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OrderClientProperties.class)
class OrderClientConfiguration {}
~~~

Dùng một cơ chế đăng ký thích hợp. Với record constructor-bound, đừng chỉ đặt `@Component` trên record rồi mong mọi constructor parameter được Spring tự diễn giải thành configuration properties; đó là hai mô hình khởi tạo bean khác nhau.

Khi Spring Boot bind và validate bean này trong quá trình dựng context, lỗi bắt buộc có thể khiến ứng dụng **không khởi động thành công**.

### 4.5. Service chỉ nhận cấu hình đã bind

~~~java
package com.example.orders.service;

import com.example.orders.config.OrderClientProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderClientService {

    private final OrderClientProperties properties;

    public OrderClientService(OrderClientProperties properties) {
        this.properties = properties;
    }

    public int retryLimit() {
        return properties.retry().maxAttempts();
    }
}
~~~

Service đọc các giá trị có kiểu đã được tạo và validate. Không cần lấy chuỗi `retry.max-attempts` rồi parse thủ công mỗi khi có request.

Điều này không có nghĩa service được miễn tất cả kiểm tra runtime. Một endpoint có thể mất kết nối sau startup, hoặc payload nhập từ người dùng có thể không hợp lệ; những trường hợp đó phải được xử lý ở lớp tương ứng.

## 5. Kết quả với các cấu hình đúng và sai

Xét record ở phần trước, với những nguồn cấu hình không bị ghi đè ngoài ý muốn.

| Tình huống | Ví dụ | Hành vi mong đợi |
| --- | --- | --- |
| Đúng toàn bộ | `max-attempts: 3`, timeout hợp lệ | Binder và validation thành công |
| Thiếu `base-url` | Không có property ở nguồn nào | `@NotNull` phát hiện thiếu |
| Sai kiểu timeout | `connect-timeout: abc` | Lỗi chuyển đổi thành `Duration` |
| Retry bằng 0 | `max-attempts: 0` | `@Min(1)` không đạt |
| Retry quá lớn | `max-attempts: 99` | `@Max(10)` không đạt |
| Không có `allowed-regions` | Thiếu list hoặc rỗng | `@NotEmpty` không đạt |
| List có chuỗi trống | `allowed-regions: [""]` | `@NotBlank` trên phần tử có thể phát hiện |
| Thiếu cả `retry` | Không có `orders.client.retry.*` | `@NotNull` trên nested object phát hiện |
| Thiếu `retry.backoff` | Chỉ có `max-attempts` | `@NotNull` trên field nested có thể phát hiện với `@Valid` |
| Chỉ URL hợp lệ nhưng host không phản hồi | `base-url` hợp lệ | Startup config validation chưa đủ để kiểm tra kết nối |

Trong báo cáo lỗi thực tế, có thể xuất hiện thông tin như `Failed to bind properties`, `BindException`, `BindValidationException` hoặc một lỗi bean creation được bọc bên ngoài. Đừng viết monitoring dựa vào đúng một câu tiếng Anh của exception; thông điệp có thể thay đổi giữa các phiên bản Spring Boot và Bean Validation provider.

## 6. Kiểm tra kiểu dữ liệu không thay thế ràng buộc nghiệp vụ

Spring Boot Binder chuyển nhiều giá trị từ text sang kiểu đích, chẳng hạn:

~~~yaml
service:
  client:
    timeout: 3s
  upload:
    max-size: 10MB
~~~

Có thể bind vào:

~~~java
import java.time.Duration;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Client client,
        Upload upload
) {
    public record Client(Duration timeout) {}
    public record Upload(DataSize maxSize) {}
}
~~~

Nếu `timeout` là `not-a-duration`, Binder có thể báo conversion error. Nhưng nếu người dùng nhập `0s`, conversion có thể thành công trong khi nghiệp vụ không cho phép timeout bằng 0.

### 6.1. Ràng buộc Duration lớn hơn 0

Một cách là dùng kiểm tra nghiệp vụ tùy chỉnh thay vì chỉ dựa vào `@NotNull`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sample.http")
public record HttpPolicy(Duration timeout) {

    public HttpPolicy {
        if (timeout == null ||
                timeout.isZero() ||
                timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "sample.http.timeout phải lớn hơn 0");
        }
    }
}
~~~

Với record compact constructor, phép kiểm tra xảy ra khi object được tạo. Đây là một **cách enforce invariant** rõ ràng, nhưng lỗi hiển thị có thể được bọc trong exception binding/bean creation và không cung cấp đầy đủ thông tin constraint như Bean Validation. Với nhiều validation rules, có thể chọn custom Jakarta constraint hoặc validator riêng.

Không log trực tiếp giá trị nhạy cảm trong exception. Với timeout hoặc số lượng không nhạy cảm, có thể đưa tên key và điều kiện hợp lệ vào thông báo.

### 6.2. Ràng buộc liên quan giữa nhiều field

Giả sử cấu hình có:

~~~yaml
network:
  connect-timeout: 2s
  request-timeout: 5s
~~~

Mỗi giá trị có thể hợp lệ riêng, nhưng policy yêu cầu `request-timeout >= connect-timeout`. Constraint kiểu `@NotNull` không thể tự kiểm tra quan hệ này.

Một record có thể có invariant:

~~~java
@ConfigurationProperties(prefix = "network")
public record NetworkProperties(
        Duration connectTimeout,
        Duration requestTimeout
) {
    public NetworkProperties {
        if (connectTimeout == null ||
                requestTimeout == null ||
                connectTimeout.isNegative() ||
                requestTimeout.compareTo(connectTimeout) < 0) {
            throw new IllegalArgumentException(
                    "network.request-timeout phải >= connect-timeout");
        }
    }
}
~~~

Trong ứng dụng lớn, nếu nhiều quy tắc liên trường phức tạp, cân nhắc constraint cấp class hoặc custom Validator để tập trung logic và cung cấp thông điệp lỗi rõ ràng.

### 6.3. Phạm vi kiểm tra

Validation lúc khởi động phù hợp nhất cho các điều kiện có thể quyết định **dựa trên cấu hình hiện có**, không đòi thực hiện giao dịch thật hoặc gọi mạng nhiều lần.

Ví dụ: `timeout > 0`, `retries >= 1`, URL không rỗng, tên môi trường thuộc tập cho phép, feature flag không xung đột nhau. Những kiểm tra không cần chờ người dùng gửi request.

## 7. Nested object: thiếu cả nhóm cũng cần một chính sách

Với record:

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(Gateway gateway) {
    public record Gateway(String endpoint, String token) {}
}
~~~

Nếu không có bất kỳ `payments.gateway.*` nào, field `gateway` có thể bằng `null` trong constructor binding. Đặt `@Valid` chỉ yêu cầu validation đi vào object **khi object tồn tại**, không buộc object phải xuất hiện.

Nếu gateway là bắt buộc:

~~~java
@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @Valid @NotNull Gateway gateway
) {
    public record Gateway(
            @NotBlank String endpoint,
            @NotBlank String token
    ) {}
}
~~~

Kết hợp:

- `@NotNull`: nhóm gateway không được vắng hoàn toàn.
- `@Valid`: kiểm tra tiếp các field bên trong.
- `@NotBlank`: không cho username/token dạng chuỗi rỗng hoặc chỉ khoảng trắng.

### 7.1. Empty `@DefaultValue` và lý do cần cân nhắc

Spring Boot hỗ trợ constructor binding tạo nested object khi cả nhóm vắng với empty `@DefaultValue`:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "scheduler")
public record SchedulerProperties(
        @DefaultValue Policy policy
) {
    public record Policy(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("500ms") Duration delay
    ) {}
}
~~~

Đây là phương án hợp lý khi nhóm scheduler policy **tùy chọn và có mặc định an toàn**. Nó giảm nhu cầu null-check trong code.

Nhưng nếu dùng empty `@DefaultValue` cho nhóm chứa credential bắt buộc, nested object có thể vẫn được tạo với field null. Điều đó không thay thế validation; thậm chí có thể che giấu sự thật rằng deployment không hề cấp nhóm config.

### 7.2. Optional feature cần được thể hiện tường minh

Ví dụ tính năng gửi SMS là tùy chọn:

~~~yaml
notifications:
  sms:
    enabled: false
~~~

Một thiết kế khả dĩ:

~~~java
@ConfigurationProperties(prefix = "notifications.sms")
@Validated
public record SmsProperties(
        boolean enabled,
        String endpoint,
        String apiKey
) {}
~~~

Nếu `enabled=false`, endpoint có thể được phép thiếu; nếu `enabled=true`, endpoint và apiKey phải có. Quy tắc này đòi **cross-field validation** hoặc logic cấu hình hóa tương ứng, không chỉ `@NotBlank` vô điều kiện trên hai field.

Điều quan trọng là startup thể hiện chính sách: **tính năng bật thì cấu hình bắt buộc**, tính năng tắt thì có thể bỏ qua; đừng kiểm tra mù mọi property khiến một tích hợp tùy chọn làm ứng dụng luôn không startup được.

## 8. Defaults: tiện lợi nhưng có thể che giấu cấu hình thiếu

Một property có default có thể giúp môi trường phát triển chạy dễ hơn:

~~~yaml
orders:
  client:
    connect-timeout: 3s
    retry:
      max-attempts: 3
~~~

Tuy nhiên, nếu một giá trị chỉ có ý nghĩa khi **được cấp tường minh tại production**, default có thể khiến việc quên biến môi trường không bị phát hiện.

### 8.1. Default thật sự an toàn

Một giá trị mặc định thường phù hợp khi nó đáp ứng chính sách nghiệp vụ ở mọi môi trường mà ứng dụng hỗ trợ, ví dụ thời gian chờ mặc định hợp lý cho demo hoặc cờ tính năng mặc định tắt.

Nhưng không nên tạo default cho:

- Secret ký token hoặc mật khẩu production.
- Địa chỉ ngân hàng/đối tác cụ thể của môi trường.
- Tenant ID hoặc namespace dữ liệu cần trỏ đúng nơi.
- Khóa mã hóa bền vững.
- Giá trị phải đồng bộ giữa mọi instance nhưng được tự tạo riêng ở startup.

Một default sai có thể tệ hơn một lỗi startup vì hệ thống vẫn chạy nhưng với behavior sai.

### 8.2. Primitive default và `@NotNull`

Với:

~~~java
public record PoolProperties(int size) {}
~~~

`int` là primitive và không thể null, nên `@NotNull` trên nó không giúp phát hiện property bị thiếu. Cần `@Min(1)` nếu yêu cầu kích thước ít nhất là 1, hoặc dùng `Integer` + `@NotNull` khi cần phân biệt vắng mặt với giá trị 0.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "pool")
@Validated
public record PoolProperties(
        @NotNull @Min(1) Integer size
) {}
~~~

Trong cấu hình này, cả trường hợp không được cấp `pool.size` và trường hợp `pool.size=0` đều bị xem là không hợp lệ, nhưng có thể dẫn đến những vi phạm constraint khác nhau.

### 8.3. Default của constructor-bound fields

Spring Boot hỗ trợ `@DefaultValue`:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportsProperties(
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("false") boolean enabled
) {}
~~~

`@DefaultValue` phục vụ trường hợp chưa có property tương ứng. Nó không có nghĩa “bỏ qua mọi giá trị đã cấp nhưng sai kiểu”. Nếu deployment đặt `reports.timeout=invalid`, Binder có thể báo lỗi thay vì dùng `10s`.

### 8.4. Tránh fallback âm thầm với required config

Trong code:

~~~java
String url = environment.getProperty(
        "payment.endpoint",
        "https://sandbox.example.test");
~~~

nếu production quên cấp endpoint, ứng dụng có thể dùng sandbox thay vì báo lỗi. Nếu đây là hệ thống thanh toán thật, default như vậy có thể dẫn đến lỗi dữ liệu hoặc giao dịch sai môi trường.

Với required config, lựa chọn rõ hơn là mô hình `@ConfigurationProperties` có validation và **không có fallback không an toàn**. Với optional config, fallback phải được thiết kế có chủ đích.

## 9. Thứ tự ưu tiên nguồn cấu hình: một giá trị có thể bị thay đổi ngoài YAML

`@ConfigurationProperties` bind từ `Environment`, không đọc riêng một tệp. Do đó, kiểm tra một file YAML rồi kết luận “cấu hình đúng” có thể sai nếu một nguồn có precedence cao hơn đang override key.

Ví dụ `application.yml`:

~~~yaml
orders:
  client:
    retry:
      max-attempts: 3
~~~

Nhưng khi chạy:

~~~bash
java -jar orders.jar \
  --orders.client.retry.max-attempts=0
~~~

thì command-line property thường có ưu tiên cao hơn config data. Binder nhận giá trị 0, và `@Min(1)` sẽ từ chối nếu class properties được đăng ký/validate đúng.

Tương tự, các nguồn có thể bao gồm:

| Nguồn | Ví dụ |
| --- | --- |
| Config data bên trong JAR | `classpath:/application.yml` |
| File profile-specific | `application-prod.yml` |
| File externalized ngoài JAR | `./config/application.yml` |
| Import config data | `spring.config.import` |
| OS environment | `ORDERS_CLIENT_RETRY_MAXATTEMPTS=5` |
| Java system property | `-Dorders.client.retry.max-attempts=5` |
| JSON application properties | `SPRING_APPLICATION_JSON` |
| Command line | `--orders.client.retry.max-attempts=5` |
| Test property source | `@SpringBootTest(properties = ...)` |

Hành vi nguồn thắng phụ thuộc mức ưu tiên và có thể bị thay đổi bởi custom configuration, test infrastructure hoặc việc tắt command-line properties.

**Startup validation cần kiểm tra object đã được Binder tạo từ các nguồn có hiệu lực**, không chỉ validate một file cấu hình tĩnh theo định dạng YAML.

### 9.1. Profile-specific configuration

Giả sử:

~~~yaml
# application.yml
service:
  enabled: false
  endpoint: ""
~~~

~~~yaml
# application-prod.yml
service:
  enabled: true
  endpoint: "https://prod.example.test"
~~~

Nếu profile `prod` active, bean có thể được bind từ giá trị profile-specific; nếu profile không active hoặc file không được tìm thấy, giá trị khác. Một validator phụ thuộc `enabled` giúp bảo đảm hệ thống không khởi động ở trạng thái “đã bật nhưng endpoint rỗng”.

Cũng cần phân biệt profile file với document kích hoạt bằng `spring.config.activate.on-profile` trong một file nhiều document. Điều kiện activation quyết định document nào tham gia vào nguồn cấu hình, sau đó mới áp dụng precedence.

### 9.2. Tên key sai hoặc dư thừa

Nếu code cần `orders.client.retry.max-attempts`, nhưng người triển khai viết:

~~~properties
orders.client.retry.max-atempt=5
~~~

thì `max-atempt` là key khác, có thể bị bỏ qua trong lúc bind vì nhiều `@ConfigurationProperties` mặc định cho phép unknown fields. Giá trị cần thiết vẫn có thể vắng hoặc nhận default, nên lỗi typo không nhất thiết được phát hiện.

Có thể cân nhắc strict unknown-field handling phù hợp với phiên bản Spring Boot:

~~~java
@ConfigurationProperties(
        prefix = "orders.client",
        ignoreUnknownFields = false
)
public record StrictClientProperties(
        String baseUrl
) {}
~~~

Tuy nhiên, strict binding cần được thiết kế cùng cấu trúc properties và môi trường thật; trong mô hình có nguồn chứa nhiều key lồng nhau hoặc tuỳ chọn, cần kiểm tra để tránh từ chối những trường hợp hợp lệ ngoài ý muốn. Quan trọng hơn, **validation yêu cầu các field bắt buộc** là lớp bảo vệ trực tiếp khi property gõ sai làm mất dữ liệu cần có.

### 9.3. Không tự động suy ra độ an toàn từ tên biến môi trường

Relaxed binding cho phép tên environment variable và tên property Java ánh xạ với nhau, ví dụ:

~~~text
orders.client.retry.max-attempts
ORDERS_CLIENT_RETRY_MAXATTEMPTS
~~~

Nếu hệ thống CI/CD dùng một tên sai theo quy tắc chuyển đổi, ứng dụng có thể không nhận value. Hãy ghi rõ tên biến canonical và thử một deployment tương đương production trong test/integration environment.

## 10. Kiểm tra sớm nhưng không được biến startup thành chuỗi thao tác mạng vô hạn

Một ranh giới quan trọng: **validation cấu hình** khác **verification tài nguyên ngoài**.

### 10.1. Kiểm tra nội tại: nên làm sớm

Các câu hỏi có thể trả lời chỉ từ property values:

- `endpoint` có được cung cấp không?
- `timeout` có đúng định dạng không?
- `max-attempts` có nằm trong [1,10] không?
- `mode` có thuộc enum hợp lệ không?
- Nếu `feature.enabled=true`, nhóm `feature.credentials` có đầy đủ không?
- Nếu `tls.enabled=true`, các đường dẫn certificate/key có được cung cấp không?

Đây là các kiểm tra tốt cho giai đoạn bind/validation hoặc bean initialization.

### 10.2. Kiểm tra ngoại tại: cần phân loại dependency

Các câu hỏi phụ thuộc môi trường vận hành:

- DNS của endpoint có phân giải được **ngay lúc này** không?
- Database có trả lời health query không?
- Remote API có đang bị rate limit không?
- Certificate đang được mount có tồn tại và còn hạn không?
- Queue/topic đã được cấp quyền chưa?

Một số kiểm tra có thể phù hợp lúc startup hoặc readiness nếu dependency là bắt buộc. Nhưng gọi mạng nhiều lần, không có timeout hoặc retry vô hạn trong constructor của `@ConfigurationProperties` có thể làm quá trình khởi động treo, tăng rủi ro cascade failure hoặc khiến hệ thống khó tự phục hồi.

**Nguyên tắc:** bắt lỗi tĩnh càng sớm càng tốt; với dependency động, dùng kết hợp timeout, policy retry, readiness/health và quan sát vận hành.

### 10.3. Liveness khác readiness

Trong môi trường orchestrated:

- **Liveness** trả lời đại ý tiến trình có còn khả năng hoạt động và cần được restart không.
- **Readiness** trả lời instance có sẵn sàng nhận traffic không.
- **Startup probe** (nếu được nền tảng hỗ trợ) cho phép giai đoạn khởi động có thời gian phù hợp trước khi liveness kiểm tra.

Không nên để một dependency bên ngoài tạm mất kết nối khiến liveness liên tục thất bại và gây restart loop nếu tiến trình có thể hồi phục mà không cần restart. Ngược lại, dependency bắt buộc cho mọi request có thể được phản ánh vào readiness theo chính sách vận hành.

Validation cấu hình và readiness bổ trợ nhau: một bên ngăn chạy với **dữ liệu cấu hình sai**, bên kia đánh giá **khả năng phục vụ hiện tại**.

## 11. Khi nào nên dừng khởi động, khi nào nên giảm chức năng?

Không phải mọi property đều bắt buộc. Một hệ thống có thể có nhiều tầng:

| Tình huống | Chiến lược gợi ý |
| --- | --- |
| Thiếu database URL của service lưu dữ liệu cốt lõi | Fail fast khi cấu hình bắt buộc thiếu |
| Mật khẩu ký token quan trọng bị thiếu | Fail fast; không tạo secret tạm mỗi lần startup |
| Optional email integration bị tắt | Cho phép thiếu thông tin SMTP, ghi trạng thái tắt rõ ràng |
| Optional email integration được bật nhưng không có credential | Fail fast hoặc chặn riêng chức năng theo chính sách |
| Timeout âm hoặc retry count vô lý | Fail fast qua binding/validation |
| Service ngoài tạm downtime nhưng có retry/degraded mode | Readiness hoặc degradation có kiểm soát |
| Feature flag không được cấp | Dùng default an toàn nếu được định nghĩa rõ |
| Secret volume chưa được mount | Fail fast nếu secret là required; kiểm tra lại deployment/volume |
| Cache không kết nối nhưng hệ thống có thể chạy không cache | Thiết kế fallback có giới hạn và quan sát |
| Tệp cấu hình sai định dạng | Fail startup với thông báo rõ |

Nguyên tắc thiết kế là **đặt chính sách theo mức độ quan trọng**. “Fail fast” không có nghĩa “bất kỳ optional config nào thiếu cũng làm toàn bộ hệ thống chết”. Nó có nghĩa hệ thống **không che giấu một lỗi khiến trạng thái hiện tại vi phạm hợp đồng hoạt động đã công bố**.

## 12. Đầu tư vào thông báo lỗi startup

Validation hiệu quả khi người triển khai có thể hiểu và sửa lỗi nhanh.

Một thông điệp tốt nêu:

1. **Tên property**: `orders.client.retry.max-attempts`.
2. **Yêu cầu**: phải nằm từ 1 đến 10.
3. **Nguồn ngữ cảnh**: nhóm `orders.client`, nếu có metadata origin phù hợp.
4. **Hành động sửa**: cập nhật file/profile/env var/CLI đúng.
5. **Không lộ bí mật**: không in password, token hoặc khóa riêng.

Ví dụ câu thông báo cho kiểm tra nghiệp vụ:

~~~text
Configuration invalid:
orders.client.retry.max-attempts must be between 1 and 10.
Review the effective value from active config sources.
~~~

Đừng giả định Spring Boot luôn tạo đúng đoạn text này. Đây là **mẫu diễn đạt mong muốn**, không phải transcript một stack trace cụ thể.

### 12.1. Thông báo không nên tiết lộ secret

Một config class chứa token:

~~~java
@ConfigurationProperties(prefix = "payments.credentials")
public record CredentialsProperties(String apiKey) {}
~~~

Record có `toString()` tự sinh, có thể bao gồm các field. Vì vậy, không log toàn bộ object cấu hình để chẩn đoán, cũng không tự tạo exception chứa giá trị `apiKey`.

Khi báo lỗi, ưu tiên:

~~~text
payments.credentials.api-key must be configured
~~~

thay vì:

~~~text
payments.credentials.api-key has invalid value: <actual secret>
~~~

Tương tự, cần bảo vệ Actuator `env` và `configprops`, kiểm soát quyền truy cập và cách che giấu thông tin nhạy cảm.

### 12.2. Lỗi hiện diện từ nguồn nào?

Trong Spring Boot, metadata origin của config data có thể giúp xác định một value đến từ file nào hoặc vị trí nào. Khi điều tra, có thể xem origin/PropertySource theo cơ chế chẩn đoán có kiểm soát thay vì in toàn bộ cấu hình.

Có những property sources không mang đầy đủ metadata nguồn hoặc được biểu diễn khác nhau qua các phiên bản, vì vậy công cụ chẩn đoán cần xử lý tình huống thiếu origin. Lỗi khởi động không phải lúc nào cũng chỉ ra đúng một file nếu nhiều nguồn được hợp nhất.

## 13. Test startup validation bằng ApplicationContextRunner

Với một properties class được đăng ký và Bean Validation có trong classpath, có thể dùng `ApplicationContextRunner` để kiểm tra context khởi tạo thành công hoặc thất bại.

### 13.1. Thiết lập test context

Ví dụ JUnit 5, AssertJ, Spring Boot test:

~~~java
package com.example.orders.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class OrderClientPropertiesValidationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(OrderClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ValidationAutoConfiguration.class))
                    .withUserConfiguration(TestConfig.class)
                    .withPropertyValues(
                            "orders.client.base-url=https://api.example.test",
                            "orders.client.connect-timeout=2s",
                            "orders.client.request-timeout=5s",
                            "orders.client.enabled=true",
                            "orders.client.allowed-regions[0]=apac",
                            "orders.client.retry.max-attempts=3",
                            "orders.client.retry.backoff=250ms"
                    );

    @Test
    void validConfigurationStarts() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getBean(OrderClientProperties.class)
                    .retry().maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void invalidRetryCountPreventsStartup() {
        runner.withPropertyValues(
                "orders.client.retry.max-attempts=0"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }
}
~~~

Ở đây:

- `ApplicationContextRunner` dựng một Spring context nhỏ.
- `@EnableConfigurationProperties` đăng ký bean cần test.
- `ValidationAutoConfiguration` hỗ trợ hạ tầng validation của test khi dependency validation có mặt.
- Giá trị mặc định cho test được cấp trong `withPropertyValues`.
- Case sai chỉ override `max-attempts=0` để kiểm tra rằng context không startup thành công.

Không cần đòi đúng tên exception hoặc toàn bộ lỗi hiển thị vì thông điệp có thể khác giữa các phiên bản.

### 13.2. Các case test cần có

| Case | Property thay đổi | Điều muốn xác nhận |
| --- | --- | --- |
| Happy path | Tất cả giá trị hợp lệ | Context startup thành công |
| Thiếu required | Bỏ `base-url` trong cấu hình test | Context thất bại do thiếu |
| Sai kiểu | `connect-timeout=abc` | Context thất bại khi bind |
| Sai ràng buộc | `max-attempts=0` | Context thất bại khi validate |
| Vượt giới hạn | `max-attempts=100` | `@Max(10)` được áp dụng |
| Thiếu nested group | Không cấp `retry.*` | `@NotNull` bảo vệ nhóm |
| Missing nested field | Cấp attempts nhưng bỏ backoff | `@Valid` + `@NotNull` bảo vệ field |
| Empty list | Không có regions hoặc list rỗng | `@NotEmpty` được áp dụng |
| Invalid list element | Vùng là chuỗi trống | Constraint của phần tử được áp dụng |
| Override source | Giá trị ở nguồn cao là 0 | Validation dùng giá trị cuối từ binder |

Khi dựng từng case, cần loại bỏ hoặc thay thế giá trị nền đúng cách. Chỉ gọi `withPropertyValues` thêm một property **không** tự loại bỏ những property khác đã cấp trong runner. Đối với test “thiếu hẳn property”, nên tạo runner riêng không đưa property đó từ đầu.

### 13.3. Không chỉ test annotation tồn tại

Một test dùng reflection để khẳng định `@NotNull` có trên field chỉ kiểm tra **metadata của code**, không chứng minh framework đã đăng ký bean, nạp source, bind và chạy validator đúng.

Test context thực tế giúp phát hiện những lỗi tích hợp phổ biến:

- Chưa bật scanning hoặc `@EnableConfigurationProperties`.
- Thiếu validation dependency.
- `@Valid` không được cascade như mong muốn.
- Prefix sai so với cấu hình triển khai.
- Một default vô tình che mất missing config.

### 13.4. Integration test trong profile gần production

Bên cạnh unit/context tests, có thể chạy một integration test hoặc smoke test với cấu hình gần production nhưng **không chứa secret thật**:

~~~bash
java -jar orders.jar \
  --spring.profiles.active=staging \
  --orders.client.retry.max-attempts=0
~~~

Nếu class validation yêu cầu ít nhất 1, startup nên không thành công. Đừng chạy mẫu sai cấu hình này trong production đang phục vụ người dùng. Mục tiêu là xác nhận artifact và cơ chế externalized configuration kết nối đúng ở môi trường thử nghiệm.

## 14. Validation và vòng đời khởi động Spring Boot

Để hiểu vì sao validation lúc startup hiệu quả, cần phân biệt các giai đoạn khái quát:

~~~text
Đọc command-line / environment / config data
                     |
                     v
      Chuẩn bị Spring Environment
                     |
                     v
           Khởi tạo ApplicationContext
                     |
                     v
     Đăng ký và tạo configuration-properties beans
                     |
                     v
         Binder chuyển kiểu và bind dữ liệu
                     |
                     v
           Chạy validation nếu được bật
                     |
          hợp lệ? ----+---- không ---> lỗi startup
             |
            có
             v
       Các bean phụ thuộc nhận typed config
             |
             v
       Ứng dụng tiếp tục khởi động
~~~

Đây là mô hình suy nghĩ, không phải sơ đồ chính xác cho mọi hook/framework extension. Spring Boot có nhiều giai đoạn và một số bean có thể được tạo theo thứ tự khác nhau tùy cấu hình. Nhưng với bean cấu hình được đăng ký và bind trong lúc dựng context, một lỗi binding hoặc validation có thể chặn startup.

### 14.1. Cấu hình cần được kiểm tra ở đúng thời điểm

Nếu properties class chỉ được tạo theo nhu cầu rất muộn hoặc cấu hình bị truy vấn trực tiếp tại runtime thay vì bind startup, không thể mặc định tất cả lỗi sẽ được phát hiện ngay khi mở ứng dụng.

Muốn fail fast cho cấu hình bắt buộc, hãy bảo đảm bean cấu hình được đăng ký và được khởi tạo trong giai đoạn startup thích hợp, không giấu việc đọc property ở một nhánh request hiếm khi chạy.

### 14.2. Validation không thay đổi sau startup một cách thần kỳ

Bean `@ConfigurationProperties` thường được bind khi tạo, và dữ liệu trong singleton bean không tự thay đổi chỉ vì file cấu hình, ConfigMap hoặc Kubernetes Secret được chỉnh sửa ở hạ tầng. Nếu sử dụng cơ chế refresh/rebind, cần xác định khi nào validation được chạy lại và xử lý trường hợp giá trị mới không hợp lệ.

Startup validation giải quyết lỗi **của lần khởi tạo cụ thể**, không thay thế chính sách cập nhật và bảo vệ dữ liệu trong cả vòng đời ứng dụng.

## 15. Kubernetes và container: nhận ra cấu hình sai trước khi nhận traffic

Trong môi trường container, cấu hình có thể được cấp bằng env vars, ConfigMaps, Secrets hoặc volume files. Việc image chạy tốt trên máy developer không chứng minh các key tương ứng có sẵn trong pod.

Ví dụ giả định deployment cấp:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:1.0
          env:
            - name: ORDERS_CLIENT_BASEURL
              value: "https://orders.partner.example"
            - name: ORDERS_CLIENT_RETRY_MAXATTEMPTS
              value: "0"
~~~

Nếu `orders.client.retry.max-attempts` được bind thành 0 và có `@Min(1)`, ứng dụng có thể thất bại trong giai đoạn khởi tạo context. Kubernetes sau đó quan sát container không hoạt động như kỳ vọng; không có nghĩa nó tự sửa sai giá trị hoặc tự rollback.

### 15.1. Đưa lỗi cấu hình vào quá trình release

Một pipeline triển khai có thể:

1. Validate định dạng Helm/chart/manifest.
2. Kiểm tra có biến và Secret reference cần thiết.
3. Khởi tạo phiên bản ứng dụng trong staging/test environment.
4. Quan sát việc bind và validation có thành công không.
5. Rollout theo chiến lược có readiness checks và theo dõi lỗi.
6. Nếu bản mới không sẵn sàng, điều tra config và rollback theo chính sách.

Startup validation giúp bổ sung **hợp đồng cấu hình ở chính ứng dụng** vào các lớp kiểm tra manifest. Nó phát hiện điều kiện mà chỉ JVM/Binder mới hiểu đầy đủ, ví dụ chuyển `250ms` thành `Duration` hay constraint nested.

### 15.2. Không chỉ nhìn trạng thái tiến trình

Một tiến trình có thể còn chạy nhưng không ready; một ứng dụng có thể bind config thành công nhưng không truy cập được DB. Các trạng thái cần được phân biệt rõ khi giám sát:

- **Startup failed**: cấu hình bắt buộc sai hoặc lỗi khởi tạo.
- **Started but not ready**: tiến trình đã khởi động nhưng một điều kiện phục vụ hiện tại chưa đạt.
- **Ready but degraded**: một tính năng tùy chọn đang được giới hạn theo thiết kế.
- **Healthy and ready**: đáp ứng các điều kiện vận hành mà hệ thống đã định nghĩa.

Không ép tất cả thành một boolean duy nhất nếu hệ thống có nhiều dependency và chính sách phục hồi khác nhau.

## 16. Phát hiện lỗi sai cấu hình do profile và environment

Ví dụ development có:

~~~yaml
# application-dev.yml
mail:
  enabled: false
~~~

Production có:

~~~yaml
# application-prod.yml
mail:
  enabled: true
  smtp:
    host: "smtp.internal"
    port: 587
~~~

Một ứng dụng có thể chạy được ở dev vì email bị tắt. Khi prod bật email, phải kiểm tra thêm `smtp.host`, `smtp.port` và credential tương ứng. Nếu chỉ test dev, lỗi production sẽ không lộ.

### 16.1. Thiết kế validation theo trạng thái tính năng

Một class có thể mô tả:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        boolean enabled,
        Smtp smtp
) {
    public record Smtp(String host, Integer port) {}
}
~~~

Các ràng buộc cần biểu diễn:

- Nếu `enabled=false`: `smtp` có thể vắng nếu mail là optional.
- Nếu `enabled=true`: `smtp` phải có, host không được trống, port hợp lệ.
- Các secret riêng của SMTP chỉ bắt buộc khi thực sự dùng authentication theo policy.

Đây là **conditional validation**. Có thể triển khai với constraint cấp class hoặc một validator/service initialization rõ ràng, thay vì đặt `@NotNull` vô điều kiện trên mọi field khiến cấu hình dev tùy chọn bị từ chối.

### 16.2. Kiểm tra profile cuối cùng

`spring.profiles.active` có thể đến từ CLI hoặc nguồn cấu hình khác; một document `spring.config.activate.on-profile` chỉ đóng góp key khi điều kiện khớp. Vì vậy, validation lúc startup cần thực thi sau khi các tài liệu có hiệu lực đã được xác định.

Khi một property có vẻ “bị thiếu”, hãy xem profile đang active, cấu hình đã được import, working directory, các external config locations và nguồn có ưu tiên cao hơn. Một file hiện diện trên ổ đĩa không tự chứng minh nó được Spring Boot nạp.

## 17. Không nhầm startup validation với @Valid trên request

Trong ứng dụng web, `@Valid` thường dùng cho request DTO:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @Min(1) int quantity
) {}
~~~

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody CreateOrderRequest request) {
    // Xử lý request.
}
~~~

Đây là validation **dữ liệu người dùng gửi ở runtime**, xảy ra khi một request đến. Nó rất quan trọng nhưng không tự đảm bảo `orders.client.base-url` hoặc `retry.max-attempts` được cấp đúng.

Ngược lại, `@Validated` trên `@ConfigurationProperties` hướng tới **bean cấu hình** được bind khi khởi tạo. Cùng là Jakarta Bean Validation nhưng **thời điểm và mục tiêu kiểm tra khác nhau**.

Một hệ thống tốt thường cần cả hai: startup validation cho cấu hình ứng dụng, request validation cho input của người dùng và domain invariants cho nghiệp vụ.

## 18. Chẩn đoán lỗi startup có hệ thống

Khi một ứng dụng không khởi động vì binding hoặc validation, kiểm tra theo thứ tự:

1. **Tên bean cấu hình:** class có `@ConfigurationProperties` chưa? Có được scan/enable không?
2. **Prefix:** code dùng `orders.client` nhưng file có thể viết `order.client`?
3. **File và location:** đúng `application.yml`, profile-specific file, file ngoài JAR hoặc `spring.config.import`?
4. **Precedence:** biến môi trường, Java system property, JSON hoặc CLI có override giá trị đúng thành giá trị sai không?
5. **Kiểu đích:** `Duration`, `URI`, `DataSize`, `int`, enum, list/map có conversion phù hợp không?
6. **Giá trị thiếu:** field bắt buộc có được cấp không? Primitive có đang bị mặc định 0/false?
7. **Nested fields:** cả nhóm con có vắng không? Có `@Valid` cascade và `@NotNull` ở cấp cha không?
8. **Default:** có default không an toàn đang che giấu lỗi môi trường không?
9. **Validator dependency:** có implementation Bean Validation, `@Validated` và wiring phù hợp không?
10. **Thông báo lỗi:** có đủ tên key và constraint để sửa không, có nguy cơ lộ secret không?
11. **Kết nối ngoài:** nếu cấu hình hợp lệ mà service vẫn không ready, kiểm tra health/DNS/network/credential thực tế theo chính sách vận hành.
12. **Test tái lập:** dùng một context test với nguồn cấu hình xác định thay vì phụ thuộc vào máy phát triển.

### 18.1. Lỗi thường gặp

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Startup thành công dù thiếu secret | Field chưa có constraint hoặc có default không an toàn | Bổ sung required validation, bỏ fallback sai |
| Lỗi chỉ xuất hiện khi request đầu tiên đến | Đọc property/khởi tạo client quá muộn | Bind và validate trong startup, tách logic runtime |
| Bean config không inject được | Chưa đăng ký class properties | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Giá trị không bind được | Sai kiểu hoặc sai format | Sửa source value, dùng đơn vị tường minh |
| `@NotNull` không bắt số primitive thiếu | Primitive không null, có thể nhận 0 | `@Min` hoặc wrapper `Integer` với `@NotNull` |
| Field nested không được kiểm tra | Thiếu `@Valid` hoặc bean validation | Thêm cascade và validator dependency |
| Map/list chứa entry sai | Collection binding và nguồn cao có semantics riêng | Xem precedence, tên key, validation phần tử |
| Cấu hình đúng ở dev nhưng fail prod | Active profile/import khác | Test profile gần production |
| Test không fail như mong đợi | Test properties vẫn có default | Dựng context không cấp key bắt buộc |
| Lỗi ghi đè bởi CLI | CLI thường ưu tiên cao hơn config data | Xem effective property sources |
| App fail khi remote API bị gián đoạn | Startup đang hard-fail vì kiểm tra mạng | Xem dependency criticality và readiness policy |
| Secret bị in trong lỗi | Log raw config hoặc exception kèm value | Chỉ log property name/constraint, bảo vệ Actuator |

## 19. Bài tập thực hành

### Bài tập A — Thiếu property bắt buộc

Tạo `application.yml` chỉ có:

~~~yaml
lesson:
  client:
    timeout: 3s
~~~

Tạo record:

~~~java
@ConfigurationProperties(prefix = "lesson.client")
@Validated
public record LessonClientProperties(
        @NotBlank String endpoint,
        @NotNull Duration timeout
) {}
~~~

Đăng ký bean bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, thêm starter validation và chạy ứng dụng. Dự đoán kết quả khi `endpoint` không tồn tại. Sau đó thêm một endpoint hợp lệ và thử lại.

### Bài tập B — Sai kiểu và sai ràng buộc

Dùng record:

~~~java
@ConfigurationProperties(prefix = "lesson.retry")
@Validated
public record LessonRetryProperties(
        @Min(1) @Max(5) int attempts,
        @NotNull Duration backoff
) {}
~~~

Thử `attempts=0` và `attempts=10`. Tiếp theo thử `backoff=not-a-duration`. Quan sát sự khác nhau giữa lỗi constraint và lỗi conversion.

### Bài tập C — Nested group thiếu toàn bộ

Tạo:

~~~java
@ConfigurationProperties(prefix = "lesson")
@Validated
public record LessonProperties(@Valid @NotNull Retry retry) {
    public record Retry(@Min(1) int attempts) {}
}
~~~

Chạy không có `lesson.retry.*`. Giải thích vì sao `@NotNull` trên object cha quan trọng, còn `@Valid` kiểm tra tiếp field khi nested object có mặt.

### Bài tập D — Default che giấu thiếu cấu hình

Tạo một property `lesson.partner.endpoint` có default trỏ đến sandbox trong `application.yml`. Chạy profile gần production nhưng quên override endpoint. Quan sát giá trị được bind, sau đó thiết kế lại để endpoint production là required và không còn default sandbox không an toàn.

### Bài tập E — Test startup failure

Dùng `ApplicationContextRunner` với một configuration-properties class có `@Validated` và constraint. Viết ít nhất ba case: hợp lệ, thiếu required property, sai constraint. Kiểm tra context không startup thành công ở hai case lỗi, thay vì chỉ so sánh reflection annotations.

### Bài tập F — Phân biệt startup và readiness

Một service có URL remote API hợp lệ, nhưng API bị shutdown trong năm phút. Hãy chọn kiểm tra nào nên nằm ở startup binding, kiểm tra nào nên nằm ở readiness và cách xử lý khi API hồi phục. Không để kết nối từ constructor chạy retry vô hạn.

### Bài tập G — Conditional validation

Một feature có `enabled=false` và không có `credentials`. Khi chuyển sang `enabled=true` mà vẫn thiếu `credentials`, ứng dụng cần báo lỗi. Thiết kế ràng buộc liên trường hoặc validator để phản ánh chính sách này.

## 20. Checklist cho cấu hình production

Trước khi triển khai một Spring Boot service có externalized configuration:

- [ ] Các nhóm cấu hình quan trọng có `@ConfigurationProperties` với prefix rõ ràng.
- [ ] Bean cấu hình được đăng ký và bind trong quá trình startup.
- [ ] Tất cả key bắt buộc có `@NotNull` hoặc `@NotBlank` phù hợp.
- [ ] Số lượng và phạm vi có `@Min`, `@Max` hoặc constraint tương đương.
- [ ] Nested object bắt buộc có `@NotNull` và `@Valid`.
- [ ] Validation dependency và `@Validated` đã được thiết lập.
- [ ] Các ràng buộc giữa nhiều field có một phương án kiểm tra rõ ràng.
- [ ] Không có default nguy hiểm cho secret hoặc endpoint production.
- [ ] Các profile, config imports, env vars và command-line overrides đã được kiểm tra.
- [ ] Test xác nhận startup thất bại khi thiếu hoặc sai cấu hình.
- [ ] Có readiness/health strategy cho dependency bên ngoài.
- [ ] Không log secret hoặc toàn bộ object có credential.
- [ ] Thông điệp lỗi cho phép người vận hành tìm đúng property và chính sách hợp lệ.
- [ ] Quy trình rollback/rollout xử lý được tình huống một bản mới không startup.

## 21. Ghi nhớ

1. **Startup configuration validation giúp biến lỗi cấu hình thành lỗi khởi động dễ thấy**, thay vì để nó ẩn cho tới khi traffic đi qua một nhánh nghiệp vụ.
2. `@ConfigurationProperties` + `@Validated` + Bean Validation là cách tập trung và có kiểu để kiểm tra phần lớn hợp đồng cấu hình Spring Boot.
3. **Binding, conversion, Bean Validation và kiểm tra dependency ngoài là các lớp khác nhau**; không nên dùng một cơ chế để thay thế tất cả.
4. `@NotNull` không có tác dụng như mong muốn với primitive; dùng constraint phạm vi hoặc wrapper type khi cần phân biệt field thiếu.
5. **Nested object có thể vắng hoàn toàn**; `@Valid` không thay thế `@NotNull` cho nhóm bắt buộc.
6. Một default không phù hợp có thể khiến cấu hình thiếu được che giấu; chỉ dùng default khi nó thật sự an toàn theo nghiệp vụ.
7. Validation phải xét **giá trị cuối cùng từ các nguồn đã được Spring Boot nạp**, bao gồm profile, environment, system properties, JSON và CLI.
8. **Fail fast không đồng nghĩa fail với mọi hệ thống ngoài đang downtime**; readiness, liveness, retry và degraded mode cần chính sách riêng.
9. Test context khởi động là một cách hữu ích để xác nhận validation **thực sự chạy**.
10. Lỗi cấu hình nên nêu tên key/constraint nhưng không làm lộ secret.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, profile-specific data và cấu hình bên ngoài JAR.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): định nghĩa, binding và registration của `@ConfigurationProperties`.
- [Spring Boot Reference — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, nested validation và constraints.
- [Spring Boot Reference — Configuration Properties Conversion](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion): chuyển đổi `Duration`, `DataSize` và các kiểu khác.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cấu hình endpoint, khả năng quan sát và bảo vệ dữ liệu nhạy cảm.
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness, liveness và triển khai trong orchestrated environments.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): cơ chế constraints và cascade validation.
