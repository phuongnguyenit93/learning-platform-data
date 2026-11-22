# Vì sao không nên dùng `Optional` làm trường cấu hình trong `@ConfigurationProperties`?

## 1. Mục tiêu và bối cảnh

Trong Spring Boot, `@ConfigurationProperties` liên kết các giá trị **externalized configuration** vào object Java có kiểu. Với mô hình constructor binding hoặc Java `record`, người viết ứng dụng thường muốn diễn tả rõ trường nào bắt buộc, trường nào có giá trị mặc định và trường nào có thể không xuất hiện trong `application.properties`, `application.yml` hoặc biến môi trường.

Một lựa chọn có vẻ tự nhiên là khai báo trường dưới dạng `Optional<T>`:

~~~java
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Optional<String> apiKey
) {}
~~~

Ý định là: nếu `app.client.api-key` không được cấu hình thì `apiKey` sẽ bằng `Optional.empty()`. **Đây không phải một giả định an toàn trong Spring Boot configuration properties binding.**

Tài liệu Spring Boot khuyến nghị **không dùng `java.util.Optional` làm property của `@ConfigurationProperties`**. `Optional` chủ yếu được thiết kế như **kiểu trả về** để thể hiện một kết quả có thể vắng mặt. Khi một property cấu hình `Optional` không có giá trị, Binder có thể gán **`null` thay vì `Optional.empty()`** để giữ cách xử lý nhất quán với những kiểu property khác.

Tài liệu này giải thích vì sao sự khác biệt nhỏ đó quan trọng, nhất là khi dùng constructor binding và `record`; đồng thời trình bày các cách thay thế để biểu diễn cấu hình tùy chọn hoặc bắt buộc một cách rõ ràng.

## 2. `Optional` được tạo ra để giải quyết vấn đề gì?

Trong Java, `Optional<T>` là một container đại diện cho khả năng một phép tính có thể trả về **giá trị kiểu `T` hoặc không có giá trị**:

~~~java
import java.util.Optional;

Optional<String> name = Optional.of("catalog");
Optional<String> absent = Optional.empty();

String a = name.orElse("unknown");    // "catalog"
String b = absent.orElse("unknown");  // "unknown"
~~~

`Optional` có các API như `map`, `filter`, `ifPresent` và `orElseGet`, hữu ích tại ranh giới của một phương thức truy vấn:

~~~java
public Optional<Customer> findCustomerById(long id) {
    return repository.findById(id);
}
~~~

Người gọi thấy ngay kết quả có thể vắng mặt và phải lựa chọn cách xử lý. Tuy nhiên, điều đó **không có nghĩa mọi thuộc tính dữ liệu tùy chọn đều nên được lưu trực tiếp dưới dạng `Optional`**.

Một object cấu hình phải đi qua nhiều bước: xác định property source, convert kiểu, gọi constructor hoặc setter, validation và injection. Việc một trường được khai báo là `Optional<T>` không tự động bảo đảm Binder sẽ khởi tạo một instance `Optional.empty()` khi không có giá trị.

**Phân biệt hai ý niệm:**

- **Dữ liệu tùy chọn:** một cấu hình có thể không được cung cấp.
- **Trường Java kiểu `Optional`:** một cách biểu diễn cụ thể của Java, có hành vi riêng.

Hai ý niệm này không luôn trùng nhau trong hệ thống binding của Spring Boot.

## 3. Khuyến nghị chính thức của Spring Boot

Phần *Type-safe Configuration Properties* trong tài liệu Spring Boot lưu ý rằng:

- Không nên dùng `java.util.Optional` với `@ConfigurationProperties`.
- `Optional` chủ yếu dành cho kiểu trả về của phương thức.
- Nếu một property khai báo kiểu `Optional` nhưng không có giá trị cấu hình, **`null` có thể được bind thay vì một `Optional.empty()`**.

Cốt lõi của cảnh báo là Spring Boot muốn xử lý sự vắng mặt của một property theo cách nhất quán, thay vì ép mọi kiểu cấu hình phải tạo ra một wrapper rỗng.

Ví dụ chưa nên dùng:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Optional<String> note) {
}
~~~

Giả sử không có `demo.note` trong tất cả các nguồn cấu hình. Đừng viết logic dựa trên kỳ vọng `note()` chắc chắn trả về `Optional.empty()`:

~~~java
String text = properties.note().orElse("not configured");
~~~

Nếu `note()` trả về `null`, đoạn trên gây `NullPointerException` trước khi `orElse` có cơ hội chạy. Đó là lỗi logic có thể khó nhận ra vì trường đã được khai báo là `Optional`.

Tương tự, không nên chỉ nhìn vào kiểu Java rồi tin rằng code không còn phải đối phó với `null`. Rủi ro chính là **một wrapper tự mô tả là “có hoặc không” lại có thể vắng mặt ở chính cấp wrapper**.

## 4. Tình huống cụ thể với constructor binding và record

### 4.1. Record tưởng như luôn trả về `Optional.empty()`

~~~java
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "billing.gateway")
public record GatewayProperties(
        String endpoint,
        Optional<String> tenantId
) {}
~~~

Cấu hình:

~~~yaml
billing:
  gateway:
    endpoint: https://gateway.example.test
  # Không khai báo tenant-id
~~~

Một service sử dụng bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class GatewayClient {

    private final GatewayProperties properties;

    public GatewayClient(GatewayProperties properties) {
        this.properties = properties;
    }

    public void callGateway() {
        String tenant = properties.tenantId().orElse("public");
        // ...
    }
}
~~~

Ý định là chọn `public` khi chưa cấu hình `tenant-id`. Nhưng nếu trường `tenantId` được Binder cung cấp dưới dạng `null`, lời gọi `orElse` không an toàn.

**Cách đúng không phải là thêm `Optional` vào mọi record component để “loại bỏ null”.** Cần quyết định một chính sách rõ ràng cho từng loại cấu hình: dùng giá trị mặc định, bắt buộc có giá trị, hoặc cho phép vắng mặt và chuyển thành `Optional` khi cần sử dụng.

### 4.2. Constructor binding có trách nhiệm riêng

Với record trong Spring Boot 3.x, một constructor phù hợp thường đủ để Boot thực hiện constructor binding khi class được đăng ký theo cơ chế configuration properties:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@ConfigurationProperties(prefix = "billing.gateway")
public record GatewayProperties(
        String endpoint,
        String tenantId
) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class BillingApplication {
}
~~~

Khi khóa `billing.gateway.tenant-id` thiếu, record component `String tenantId` có thể nhận `null`. Đây là trạng thái có thể xử lý tường minh và **không giả vờ rằng object đã có một container Optional hợp lệ**.

Nếu muốn buộc có `tenant-id`, hãy dùng validation hoặc logic kiểm tra trong constructor. Nếu muốn default, hãy định nghĩa default phù hợp. Nếu muốn trả về một API không có null cho consumer, thêm phương thức trả về `Optional` **tính từ giá trị đã bind**, như phần sau.

### 4.3. Một record vẫn có thể có phương thức tiện ích

~~~java
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "billing.gateway")
public record GatewayProperties(
        String endpoint,
        String tenantId
) {
    public Optional<String> optionalTenantId() {
        return Optional.ofNullable(tenantId);
    }
}
~~~

Khi `tenantId` vắng mặt, record component `tenantId` có thể là `null` nhưng `optionalTenantId()` trả về `Optional.empty()` thực sự:

~~~java
String tenant = properties.optionalTenantId().orElse("public");
~~~

Cách thiết kế này dùng `Optional` tại **ranh giới API của phương thức**, đúng vai trò mạnh nhất của `Optional`. Bản thân dữ liệu cấu hình vẫn là kiểu giá trị đơn giản mà Binder hỗ trợ tự nhiên.

## 5. Ba loại trường: bắt buộc, có mặc định và có thể vắng mặt

Trước khi chọn kiểu Java, cần xác định **ngữ nghĩa của cấu hình**.

| Loại | Ví dụ | Khi thiếu giá trị | Thiết kế nên cân nhắc |
| --- | --- | --- | --- |
| Bắt buộc | URL của dịch vụ thanh toán | Phải báo lỗi khởi động | `String`/`URI` + validation |
| Có mặc định | Timeout, retry count, chế độ log | Dùng giá trị hợp lý | `@DefaultValue` hoặc khởi tạo mặc định |
| Có thể vắng mặt | Tên tenant, mô tả, tag tùy chọn | Được phép không có | Kiểu tham chiếu nullable + API `Optional` khi cần |
| Cờ bật/tắt | `enabled` | Thường cần default rõ ràng | `boolean` với `@DefaultValue("false")` |
| Danh sách | Allowed hosts | Cần quyết định rỗng hay thiếu | Kiểu `List` cùng chính sách default phù hợp |

Việc chọn `Optional<String>` không trả lời ba câu hỏi vận hành quan trọng:

1. Thiếu property là **đúng thiết kế** hay là một lỗi triển khai?
2. Giá trị mặc định hợp lý là gì, nếu có?
3. Có cần kiểm tra tính hợp lệ của giá trị đã được cung cấp hay không?

Những quyết định này nên được biểu diễn qua metadata binding, validation và cấu trúc ứng dụng, thay vì chỉ bọc mọi trường trong `Optional`.

## 6. Lựa chọn 1: dùng `@DefaultValue` với constructor binding

Với Spring Boot 3.x, annotation `org.springframework.boot.context.properties.bind.DefaultValue` có thể cung cấp giá trị mặc định cho tham số constructor binding hoặc record component.

Ví dụ:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean tracingEnabled
) {}
~~~

Cấu hình:

~~~properties
app.client.base-url=https://catalog.example.test
~~~

Khi không có các khóa tương ứng, giá trị mặc định được chuyển đổi về đúng kiểu:

- `connectTimeout()` nhận `Duration.ofSeconds(3)`.
- `maxRetries()` nhận `2`.
- `tracingEnabled()` nhận `false`.

Điều quan trọng: `@DefaultValue` cung cấp **giá trị `T` cụ thể** cho trường, không yêu cầu dùng `Optional<T>`.

### 6.1. Phân biệt default của field và default của constructor

Trong JavaBean setter binding, có thể khai báo:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private Duration connectTimeout = Duration.ofSeconds(3);

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Object được tạo trước rồi Binder cập nhật các setter tương ứng. Khi khóa không có, field có thể giữ giá trị khởi tạo.

Ngược lại, record không có field instance mutable độc lập với component; default cần được cung cấp trong constructor binding (chẳng hạn `@DefaultValue`) hoặc qua constructor logic thích hợp. Không thể dựa vào lệnh gán field như JavaBean để tạo default cho record component.

### 6.2. Default khác với “không có giá trị”

Nếu `connectTimeout` mặc định là `3s`, người sử dụng `ClientProperties` không cần biết property có hiện diện trong file hay không. Họ nhận một `Duration` hợp lệ.

Nhưng nếu việc thiếu một khóa có ý nghĩa nghiệp vụ riêng (ví dụ “không gửi tenant header”), một default tự đặt có thể che đi trạng thái vắng mặt thật. Khi đó, không nên đặt mặc định giả để tránh `null` bằng mọi giá; hãy biểu diễn trạng thái tùy chọn qua API sử dụng.

## 7. Lựa chọn 2: nullable component + `Optional` tại ranh giới sử dụng

Giả sử API key là tùy chọn ở local nhưng một số môi trường chỉ dùng authentication theo cơ chế khác. Object cấu hình có thể chứa kiểu Java đơn giản:

~~~java
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        String endpoint,
        String apiKey
) {
    public Optional<String> apiKeyIfPresent() {
        return Optional.ofNullable(apiKey);
    }
}
~~~

Cấu hình:

~~~yaml
app:
  remote:
    endpoint: https://remote.example.test
    # api-key được phép vắng mặt.
~~~

Consumer:

~~~java
String endpoint = properties.endpoint();

properties.apiKeyIfPresent()
        .ifPresent(apiKey -> client.setApiKey(apiKey));
~~~

Cách này làm rõ hai tầng:

- `apiKey` là property được bind trực tiếp từ cấu hình, có thể là `null` nếu không có nguồn cung cấp.
- `apiKeyIfPresent()` là API trình bày giá trị có thể vắng mặt dưới dạng `Optional` khi code muốn sử dụng.

Không nên gọi `Optional.of(apiKey)` vì phương thức đó ném `NullPointerException` khi tham số là `null`. Dùng `Optional.ofNullable(apiKey)`.

### 7.1. Có nên đổi chuỗi rỗng thành Optional.empty?

Điều đó phụ thuộc nghiệp vụ. Ví dụ:

~~~java
public Optional<String> apiKeyIfPresent() {
    return Optional.ofNullable(apiKey);
}
~~~

Với `apiKey=""`, `Optional.ofNullable` trả về `Optional.of("")`, **không** phải `Optional.empty()`.

Nếu muốn cả giá trị rỗng hoặc chỉ chứa khoảng trắng đều được xem là thiếu, cần quy tắc rõ ràng:

~~~java
public Optional<String> apiKeyIfPresent() {
    return Optional.ofNullable(apiKey)
            .map(String::trim)
            .filter(value -> !value.isEmpty());
}
~~~

Tuy nhiên, **không nên tự trim hoặc bỏ chuỗi rỗng đối với mọi loại secret**: một số hệ thống coi khoảng trắng là dữ liệu có ý nghĩa. Nếu quy tắc nghiệp vụ yêu cầu giữ nguyên giá trị, chỉ dùng `ofNullable`.

### 7.2. Tránh biến nullable thành “mọi nơi tự kiểm tra null”

Nếu nhiều service cùng cần dùng trường tùy chọn, đặt phương thức helper có tên rõ trong configuration object giúp tập trung chính sách vắng mặt. Các consumer không cần lặp lại:

~~~java
if (properties.apiKey() != null) {
    // ...
}
~~~

Tuy vậy, chỉ tạo wrapper khi thực sự hữu ích; không cần mọi record component đều có thêm một phương thức trả `Optional`.

## 8. Lựa chọn 3: kiểm tra giá trị bắt buộc bằng validation

Nếu một thuộc tính **bắt buộc**, dùng `Optional` sẽ truyền sai thông điệp: nó làm người đọc nghĩ thiếu giá trị là một trạng thái hợp lệ.

Ví dụ endpoint bắt buộc:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "billing.gateway")
public record GatewayProperties(
        @NotBlank String endpoint,
        @Positive int connectTimeoutSeconds
) {}
~~~

Cấu hình:

~~~properties
billing.gateway.endpoint=https://gateway.example.test
billing.gateway.connect-timeout-seconds=5
~~~

Nếu `endpoint` vắng mặt hoặc rỗng, validation có thể từ chối tạo context với thông báo rõ về trường cấu hình. Để dùng Jakarta Bean Validation trong ứng dụng Boot 3.x, cần provider tương ứng, thông thường qua `spring-boot-starter-validation`.

Có thể dùng các annotation như `@NotNull`, `@NotBlank`, `@Min`, `@Max` hoặc `@Positive` tùy kiểu và yêu cầu. `@NotBlank` phù hợp cho `String`, không phải mọi kiểu dữ liệu.

### 8.1. Validation thể hiện hợp đồng cấu hình

Việc đặt `@NotBlank` trên `endpoint` nói rằng “ứng dụng không chấp nhận thiếu endpoint”. Ngược lại, `Optional<String> endpoint` nói mơ hồ rằng “endpoint có thể vắng mặt”, nhưng lại có thể nhận `null` ở chính wrapper.

Validation giúp lỗi xuất hiện gần startup thay vì khi một request đầu tiên sử dụng property. Với cấu hình quan trọng như database URL hoặc endpoint thanh toán, phát hiện sớm thường an toàn hơn.

### 8.2. Nested object và `@Valid`

Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Remote remote
) {
    public record Remote(@NotBlank String endpoint) {}
}
~~~

Ở đây `@Valid` yêu cầu validation đi vào nested object nếu object được tạo. Nếu bản thân `remote` cũng bắt buộc, cân nhắc thêm `@NotNull` trên component `remote` để thể hiện yêu cầu tồn tại.

Không dùng `Optional<Remote>` như cách né việc thiết kế rõ nested object có bắt buộc không.

## 9. Lựa chọn 4: default qua Config Data

Ngoài annotation, giá trị mặc định có thể được cung cấp ngay trong cấu hình:

~~~properties
app.client.timeout=${APP_CLIENT_TIMEOUT:3s}
app.client.max-retries=${APP_CLIENT_RETRIES:2}
~~~

Hoặc YAML:

~~~yaml
app:
  client:
    timeout: "${APP_CLIENT_TIMEOUT:3s}"
    max-retries: "${APP_CLIENT_RETRIES:2}"
~~~

Nếu các biến tham chiếu không được cung cấp và không có nguồn khác ghi đè, default trong placeholder có thể được sử dụng. Khi bind thành `Duration` hoặc `int`, Binder chuyển đổi kiểu.

Điều này khác với `@DefaultValue`:

| Cách default | Nơi định nghĩa | Đặc điểm |
| --- | --- | --- |
| `@DefaultValue("3s")` | Record component/constructor parameter | Hợp đồng mặc định nằm gần Java type |
| `timeout=3s` | File cấu hình cơ sở | Người vận hành nhìn thấy ngay trong Config Data |
| `timeout=${APP_TIMEOUT:3s}` | File Config Data | Cho phép tham chiếu property/biến môi trường khác cùng fallback |
| Field initializer | Mutable JavaBean | Được dùng trước bước setter binding |

Các cách này có thể cùng tồn tại trong hệ thống; cần thiết kế rõ nguồn nào được ưu tiên và tránh khai báo nhiều fallback mâu thuẫn gây khó debug.

### 9.1. Không dùng default để che cấu hình thiếu nghiêm trọng

Ví dụ:

~~~properties
spring.datasource.password=${DATABASE_PASSWORD:password123}
~~~

Đây là default dễ gây sai sót nếu artifact được dùng ở production. Một secret bắt buộc nên được quản lý bằng nguồn phù hợp và thất bại rõ khi thiếu, thay vì dùng mật khẩu mẫu.

`@DefaultValue` cũng không phải công cụ bảo mật; nó chỉ biểu diễn fallback được chuyển đổi kiểu.

## 10. Những hiểu lầm phổ biến về `Optional`

### 10.1. “Khai báo `Optional` là không còn `null`”

Không đúng trong bối cảnh `@ConfigurationProperties`. Khi property thiếu, Binder có thể gán `null` cho chính field `Optional`. Khi đó:

~~~java
properties.apiKey().isPresent()
~~~

có thể ném `NullPointerException`. Loại `Optional` khỏi cấu trúc binding không tự làm mọi property bất biến, nhưng tránh tạo sự bảo đảm giả.

### 10.2. “Dùng `Optional.empty()` làm default là đủ”

Một số người thử khai báo giá trị khởi tạo:

~~~java
private Optional<String> token = Optional.empty();
~~~

Sau đó kỳ vọng mọi đường đi binding sẽ giữ `Optional.empty()` khi thiếu property. Cách này làm code phụ thuộc hành vi cụ thể của binder, thời điểm khởi tạo và khả năng giá trị được thay thế. Không nên dựa vào nó như hợp đồng chuẩn của `@ConfigurationProperties`.

Với JavaBean, nếu muốn giá trị mặc định, dùng kiểu gốc và default tương ứng; với record, dùng `@DefaultValue` hoặc cách xử lý thiếu giá trị rõ ràng.

### 10.3. “`Optional` giúp tự động validation”

Không. `Optional<String>` không kiểm tra rằng chuỗi không rỗng, URL hợp lệ hay cổng nằm trong khoảng 1–65535. Các yêu cầu đó thuộc về Bean Validation, conversion hoặc logic ứng dụng.

### 10.4. “Dùng `Optional` sẽ dễ JSON serialization hơn”

Các thư viện serialization và metadata tooling có thể xử lý wrapper khác nhau. `Optional` là một abstraction dành cho API return value; không nên thêm nó vào configuration bean chỉ vì kỳ vọng mọi công cụ sẽ diễn giải “không có giá trị” giống nhau.

### 10.5. “`null` và chuỗi rỗng là một”

Không. Trong Config Data, có thể phân biệt property vắng mặt với property được định nghĩa bằng chuỗi rỗng hoặc chỉ có khoảng trắng. Với kiểu `String`, các trạng thái này có thể tạo ra hành vi khác nhau. Nếu muốn xem chuỗi rỗng là vắng mặt, hãy thể hiện chính sách đó qua validation hoặc logic tại nơi sử dụng.

## 11. Ví dụ chuyển từ record chứa `Optional` sang thiết kế rõ nghĩa

### 11.1. Thiết kế ban đầu nhiều rủi ro

~~~java
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        Optional<String> sender,
        Optional<Duration> retryDelay,
        Optional<Boolean> enabled
) {}
~~~

Nhìn qua có vẻ mọi trường đều “an toàn khi thiếu”, nhưng thực tế:

- `sender` thiếu có thể dẫn đến `null` wrapper.
- `retryDelay` không thể hiện rõ default hợp lý là bao nhiêu.
- `enabled` có ba trạng thái logic người dùng có thể hiểu nhầm: absent, true, false; trong khi ứng dụng có thể chỉ cần một boolean với default.
- Mỗi consumer phải phân biệt trạng thái của wrapper và giá trị bên trong, dễ gây lỗi hoặc code thừa.

### 11.2. Thiết kế thay thế

~~~java
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        String sender,
        @DefaultValue("5s") Duration retryDelay,
        @DefaultValue("false") boolean enabled
) {
    public Optional<String> senderIfPresent() {
        return Optional.ofNullable(sender);
    }
}
~~~

Cấu hình có thể chỉ cần:

~~~properties
notifications.enabled=true
~~~

Khi `sender` thiếu, `senderIfPresent()` trả về `Optional.empty()`. Khi `retry-delay` thiếu, record nhận `Duration.ofSeconds(5)`. Khi `enabled` thiếu, boolean nhận `false` theo annotation.

Consumer:

~~~java
public void sendIfEnabled(NotificationProperties properties) {
    if (!properties.enabled()) {
        return;
    }

    properties.senderIfPresent().ifPresent(sender -> {
        // Tùy nghiệp vụ, dùng sender nếu có.
    });

    Duration retryDelay = properties.retryDelay();
    // ...
}
~~~

Trách nhiệm được phân tách rõ:

1. Binding đọc kiểu cấu hình trực tiếp.
2. Default cung cấp giá trị hợp lệ khi thiếu.
3. `Optional` chỉ xuất hiện ở API tiện ích.
4. Consumer không cần dự đoán Binder tạo wrapper nào khi source vắng mặt.

**Lưu ý:** nếu `enabled=true` bắt buộc phải có `sender`, chỉ khai báo như trên chưa đủ. Cần validation hoặc một điều kiện kiểm tra tổng hợp.

### 11.3. Kiểm tra điều kiện giữa các trường

Ví dụ nghiệp vụ: khi notification được bật, địa chỉ người gửi phải được cung cấp.

~~~java
import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        String sender,
        @DefaultValue("false") boolean enabled
) {
    @AssertTrue(message = "sender is required when notifications are enabled")
    public boolean isSenderValid() {
        return !enabled || (sender != null && !sender.isBlank());
    }
}
~~~

Đây là cách ví dụ để thể hiện một invariant phụ thuộc nhiều property. Trong ứng dụng thực tế, có thể đặt validation ở một custom validator hoặc lớp logic phù hợp, tùy kiến trúc và cách khởi tạo bean.

Điểm chính: **sự tùy chọn là một quy tắc của domain/configuration**, không phải hệ quả tự động của việc bọc field bằng `Optional`.

## 12. Với cấu hình phức tạp, nên chọn record hay JavaBean?

`@ConfigurationProperties` hỗ trợ cả immutable constructor binding và mutable JavaBean binding. Việc tránh `Optional` như field áp dụng cho cả hai.

### 12.1. Record và constructor binding

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        String host,
        @DefaultValue("8080") int port
) {}
~~~

Cách đăng ký phù hợp:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

Hoặc:

~~~java
@Configuration
@EnableConfigurationProperties(HttpProperties.class)
public class HttpConfig {
}
~~~

Trong Spring Boot 3.x, record với một constructor phù hợp thường dùng constructor binding không cần đặt thêm `@ConstructorBinding`. Không nên gắn `@Component` lên record rồi kỳ vọng framework xử lý constructor như binder; `@Component` là cơ chế tạo bean thông thường của Spring.

### 12.2. Mutable JavaBean và setter binding

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.http")
public class HttpProperties {

    private String host;
    private int port = 8080;
    private Duration timeout = Duration.ofSeconds(3);

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }

    public Duration getTimeout() { return timeout; }
    public void setTimeout(Duration timeout) { this.timeout = timeout; }
}
~~~

Mô hình JavaBean cho phép default qua field initializer và Binder cập nhật qua setter. Đổi field `timeout` thành `Optional<Duration>` không có lợi rõ ràng, đồng thời làm người sử dụng phải mở wrapper ở nhiều nơi.

### 12.3. So sánh ngắn

| Tiêu chí | Record constructor binding | JavaBean setter binding |
| --- | --- | --- |
| Đặc trưng | Dữ liệu bất biến sau khi khởi tạo | Có setter, thường mutable |
| Default | `@DefaultValue` hoặc xử lý constructor phù hợp | Field initializer, setter/binding |
| Khi property thiếu | Tham số có thể là `null`/giá trị default | Field có thể giữ giá trị khởi tạo |
| Đăng ký phổ biến | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` | `@Component` + `@ConfigurationProperties` hoặc cơ chế Boot |
| `Optional` làm field | Không khuyến nghị | Không khuyến nghị |
| Optional ở API | Phương thức trả `Optional.ofNullable(component)` | Phương thức getter tiện ích nếu có nhu cầu |

## 13. Primitive, wrapper, String và kiểu domain nên chọn thế nào?

Không phải mọi property tùy chọn đều nên là `Optional<T>`. Nên chọn kiểu phản ánh miền giá trị và chính sách default.

### 13.1. `boolean` so với `Boolean`

- `boolean` nhận default Java `false` nếu không được đặt trong một số mô hình; có thể dùng `@DefaultValue("false")` để thể hiện chủ đích rõ trong record.
- `Boolean` cho phép phân biệt `null` (thiếu giá trị) với `false` và `true`, nếu ba trạng thái thật sự cần thiết.

Ví dụ khi trạng thái tự động khác với bật/tắt tường minh:

~~~java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(Boolean enabled) {
    public boolean isEnabledByDefault(boolean policyDefault) {
        return enabled != null ? enabled : policyDefault;
    }
}
~~~

Nếu không cần ba trạng thái, chọn `boolean` với default được mô tả rõ giúp đơn giản hơn.

### 13.2. `int` so với `Integer`

Một `int` thiếu giá trị có thể nhận `0` trong record nếu không có default khác. Nhưng `0` không hợp lệ cho một số miền dữ liệu như port hoặc số lần retry tối thiểu. Có thể dùng `@DefaultValue("8080") int port` hoặc `Integer` kết hợp `@NotNull`/`@Min` nếu bắt buộc.

Không chọn `Optional<Integer>` chỉ vì muốn tránh mặc định `0`; vấn đề thực chất là hợp đồng dữ liệu chưa được thiết kế.

### 13.3. `String`, `URI` và `Duration`

Nếu một endpoint phải là URI hợp lệ, có thể dùng `URI` hoặc `String` với validation phù hợp. Nếu timeout có đơn vị, `Duration` mô tả tốt hơn `String`. Binder hỗ trợ conversion cho các kiểu đó, nên không cần một `Optional<Duration>` để được lợi ích type safety.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        java.net.URI endpoint,
        @DefaultValue("2s") java.time.Duration timeout
) {}
~~~

Ở đây cần bổ sung validation cho `endpoint` nếu giá trị là bắt buộc; chỉ dùng `URI` không đồng nghĩa mọi URI đều có thể kết nối hoặc đáp ứng nghiệp vụ.

## 14. Các trường hợp “không có giá trị” trong externalized configuration

Một hệ thống có thể gặp những trường hợp nhìn giống nhau nhưng về ngữ nghĩa khác nhau.

### 14.1. Không có khóa trong tất cả nguồn

~~~properties
# Không khai báo app.client.api-key
~~~

Trong tình huống này, Binder không có giá trị phù hợp để gán cho trường tương ứng. Với record component `String apiKey`, `null` có thể là kết quả, trừ khi có default hoặc cơ chế binding khác.

### 14.2. Có khóa nhưng chuỗi rỗng

~~~properties
app.client.api-key=
~~~

Khóa đã được khai báo, nhưng giá trị là chuỗi rỗng. Một số bước binding hoặc conversion có thể xử lý khác với property không tồn tại. Không mặc định đồng nhất hai trường hợp.

### 14.3. Có giá trị chỉ chứa khoảng trắng

~~~properties
app.client.api-key=   
~~~

Khoảng trắng cuối dòng khó nhìn và cách parse của `.properties` có các quy tắc riêng. Nếu cần phân biệt whitespace với chuỗi không rỗng, hãy xác định rõ validation như `@NotBlank` hoặc chính sách của component sử dụng.

### 14.4. Có giá trị sai kiểu

~~~properties
app.client.timeout=tomorrow
~~~

Với trường `Duration`, Binder có thể không chuyển đổi được chuỗi này. `Optional<Duration>` không làm giá trị `tomorrow` trở thành hợp lệ; lỗi là conversion, không phải thiếu khóa.

### 14.5. Có giá trị từ source khác

~~~properties
# application.properties
app.client.timeout=3s
~~~

Một biến môi trường hoặc command-line argument có thể ghi đè:

~~~bash
java -jar app.jar --app.client.timeout=10s
~~~

Khi đó Binder nhận giá trị hiệu lực theo property-source precedence. Trạng thái “có cấu hình hay không” phải được xét trên **toàn bộ `Environment`** đã được nạp, không chỉ một file đang mở.

## 15. Tương tác với profile và cấu hình theo môi trường

Ví dụ:

~~~properties
# application.properties
app.mail.enabled=false
~~~

~~~properties
# application-prod.properties
app.mail.enabled=true
app.mail.sender=alerts@example.test
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @DefaultValue("false") boolean enabled,
        String sender
) {}
~~~

- Khi chạy không có profile `prod` và không có nguồn override, `enabled` là `false`, `sender` có thể `null`.
- Khi chạy với `prod`, `enabled` thành `true` và `sender` nhận địa chỉ cấu hình.
- Nếu môi trường ghi đè `app.mail.enabled=true` nhưng không cung cấp `sender`, cần validation liên trường để phát hiện cấu hình không nhất quán.

Đây là tình huống dễ phát sinh khi một giá trị bị lấy từ file profile, một giá trị khác từ biến môi trường. Dùng `Optional<String> sender` không giải quyết việc hai thuộc tính phải phù hợp nhau.

## 16. Kiểm thử với Spring Boot Test

Có thể kiểm tra binding trong test context. Giả sử class:

~~~java
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String apiKey,
        @DefaultValue("3s") Duration timeout
) {
    public Optional<String> optionalApiKey() {
        return Optional.ofNullable(apiKey);
    }
}
~~~

Bài test:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
    properties = {"app.client.timeout=5s"},
    classes = ClientPropertiesTest.TestConfig.class
)
class ClientPropertiesTest {

    @org.springframework.boot.SpringBootConfiguration
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {
    }

    @Autowired
    ClientProperties properties;

    @Test
    void optionalKeyIsRepresentedAtTheGetterBoundary() {
        assertFalse(properties.optionalApiKey().isPresent());
        assertEquals(Duration.ofSeconds(5), properties.timeout());
    }
}
~~~

Test này minh họa mô hình bind một trường `String` có thể thiếu và **chỉ** tạo `Optional` khi sử dụng. Trong dự án thực tế, kiểm soát cả property sources của test để chắc chắn `app.client.api-key` không bị thêm từ nơi khác.

### 16.1. Kiểm thử trường bắt buộc

Nếu `apiKey` là bắt buộc, thay vì test `Optional.empty()`, đặt validation và test việc context bị từ chối khi thiếu. Kết quả giúp biến giả định nghiệp vụ thành hợp đồng có thể xác minh.

### 16.2. Kiểm thử default

Với `@DefaultValue("3s") Duration timeout`, có thể tạo test không khai báo `app.client.timeout` để xác nhận default được dùng. Nếu test có giá trị từ nguồn ưu tiên cao hơn, kết quả phản ánh precedence chứ không phải hành vi default.

### 16.3. Kiểm thử từng nhánh sử dụng

Đối với trường được phép vắng mặt, cần test cả trạng thái có giá trị và không có giá trị. Ví dụ `apiKeyIfPresent()` phải trả `Optional.of("abc")` khi `app.client.api-key=abc`, và `Optional.empty()` khi property thiếu.

## 17. Lưu ý về cấu hình nhạy cảm

Các trường như API key hoặc token thường có thể vắng mặt ở local nhưng bắt buộc tại production. Điều này không tự biến `Optional<String>` thành lựa chọn tốt.

Một chính sách rõ ràng hơn:

- Bind thành `String apiKey`.
- Chỉ cho phép `null` ở chế độ hoặc môi trường được quy định.
- Khi bật chế độ authentication bắt buộc, kiểm tra `apiKey` có mặt và hợp lệ.
- Không đưa giá trị bí mật vào log hoặc thông báo lỗi.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        @DefaultValue("false") boolean authenticationRequired,
        String apiKey
) {
    public void checkConfiguration() {
        if (authenticationRequired && (apiKey == null || apiKey.isBlank())) {
            throw new IllegalStateException(
                    "app.remote.api-key is required when authentication is enabled");
        }
    }
}
~~~

Đây là một ví dụ về cách biểu diễn quy tắc; trong ứng dụng thật, nên tích hợp việc kiểm tra vào giai đoạn validation/lifecycle phù hợp để lỗi xuất hiện lúc startup, không phụ thuộc consumer có chủ động gọi `checkConfiguration()` hay không.

Không dùng `Optional` để che việc secret thiếu hoặc để tự quyết định có cần xác thực hay không.

## 18. Phân biệt annotation default và constructor tự viết

Với record, có thể viết constructor compact để tự kiểm tra một số điều kiện:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String host,
        int retries
) {
    public ClientProperties {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("app.client.host is required");
        }
        if (retries < 0) {
            throw new IllegalArgumentException("retries cannot be negative");
        }
    }
}
~~~

Cách này bảo đảm record không được tạo trong trạng thái không hợp lệ, nhưng lỗi sẽ được ném trong quá trình constructor binding và có thể được Spring Boot bọc trong ngoại lệ khởi động. Với nhóm cấu hình nhiều trường, Bean Validation thường biểu diễn lỗi dễ tổng hợp hơn.

Có thể dùng constructor để gán default nếu thật sự cần, nhưng `@DefaultValue` thường trực tiếp và minh bạch hơn cho một tham số cấu hình cụ thể. Không đặt logic phức tạp hoặc side effect trong constructor configuration properties; nó nên mô tả dữ liệu.

## 19. Điều gì xảy ra khi dùng `Optional` trong nhiều tầng object?

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Optional<SecurityProperties> security
) {
    public record SecurityProperties(String mode) {}
}
~~~

Ý định có thể là “nếu thiếu `app.security.*`, không cần cấu hình bảo mật”. Nhưng Binder phải xử lý cả wrapper `Optional`, nested object và các quy tắc tạo object. Dạng này càng khó dự đoán khi không có bất kỳ thuộc tính con nào.

Thay thế:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(SecurityProperties security) {
    public record SecurityProperties(String mode) {}

    public boolean hasSecurityConfiguration() {
        return security != null;
    }
}
~~~

Nếu muốn các trường con luôn có object mặc định, cân nhắc nested binding với `@DefaultValue` theo quy tắc của phiên bản Spring Boot đang dùng; nếu muốn nested object bắt buộc, dùng validation và thiết kế rõ.

**Không mặc định rằng một nested record thiếu hoàn toàn sẽ luôn tự sinh object rỗng.** Cần kiểm tra mô hình constructor binding và default dành cho nested object.

## 20. Khi nào `Optional` vẫn nên xuất hiện?

Khuyến nghị “không dùng Optional làm trường cấu hình” **không có nghĩa phải cấm `Optional` trong toàn bộ ứng dụng**. Nó vẫn hữu ích trong các API trả về khi muốn buộc người gọi nghĩ về trường hợp không tìm thấy dữ liệu.

Ví dụ:

~~~java
public Optional<URI> optionalFallbackEndpoint() {
    return Optional.ofNullable(fallbackEndpoint);
}
~~~

Hoặc một service dùng `Optional` trả về kết quả tra cứu:

~~~java
public Optional<Customer> findCustomer(String code) {
    return customerRepository.findByCode(code);
}
~~~

Khác biệt là container `Optional` được **mã Java chủ động tạo ra** tại ranh giới kết quả, thay vì hy vọng một binder khởi tạo wrapper khi không có property.

Một số thư viện có thể chủ động hỗ trợ `Optional` trong API riêng. Điều đó không phủ định khuyến nghị của Spring Boot cho **trường thuộc `@ConfigurationProperties`**.

## 21. Quy trình chẩn đoán khi configuration properties chứa `Optional` gặp lỗi

Nếu ứng dụng bị `NullPointerException` ở `properties.someField().orElse(...)` hoặc `isPresent()`:

1. **Kiểm tra class có `Optional<T>` là trường hoặc record component không.** Nếu có, xem lại thiết kế theo khuyến nghị của Boot.
2. **Kiểm tra khóa thật sự được bind.** Tên prefix, cấu trúc nested và quy tắc relaxed binding có đúng không?
3. **Kiểm tra source đang được nạp.** File, profile, external location và biến môi trường có hiện diện không?
4. **Phân biệt thiếu khóa với giá trị rỗng hoặc sai kiểu.** Các trường hợp có cách xử lý khác nhau.
5. **Kiểm tra default.** Nếu muốn một giá trị cụ thể, dùng `@DefaultValue` hoặc default rõ trong Config Data.
6. **Kiểm tra điều kiện bắt buộc.** Nếu value không được phép vắng mặt, dùng validation hoặc constructor invariant.
7. **Đổi field `Optional<T>` sang `T`.** Khi cần API tùy chọn, thêm phương thức trả `Optional.ofNullable(value)`.
8. **Kiểm tra constructor binding và đăng ký bean.** Record nên được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` theo mô hình hỗ trợ, không dùng `@Component` để ép constructor binding.
9. **Kiểm tra các consumer.** Không gọi `.orElse` trên wrapper do Binder có thể trả `null`; sau khi đổi thiết kế, dùng phương thức Optional do chính Java code tạo.
10. **Không log secret trong lúc debug.** Chỉ ghi tên property hoặc trạng thái cấu hình nếu cần.

Có thể sử dụng endpoint `/actuator/configprops` trong môi trường được bảo vệ để quan sát bean configuration properties, nhưng endpoint quản trị phải có xác thực và che giấu thông tin phù hợp. Với cấu hình nhạy cảm, hạn chế tối đa việc hiển thị giá trị.

## 22. So sánh phương án qua một tình huống

Đề bài: ứng dụng gọi dịch vụ bên ngoài. `baseUrl` bắt buộc; `timeout` mặc định 2 giây; `tenant` là metadata tùy chọn.

**Không nên:**

~~~java
@ConfigurationProperties(prefix = "app.external")
public record ExternalProperties(
        Optional<String> baseUrl,
        Optional<Duration> timeout,
        Optional<String> tenant
) {}
~~~

Thiết kế này không phân biệt trường bắt buộc với trường có default, và vẫn có nguy cơ wrapper `Optional` là `null` khi thiếu property.

**Nên:**

~~~java
import java.time.Duration;
import java.util.Optional;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.external")
public record ExternalProperties(
        @NotBlank String baseUrl,
        @DefaultValue("2s") Duration timeout,
        String tenant
) {
    public Optional<String> optionalTenant() {
        return Optional.ofNullable(tenant);
    }
}
~~~

Cấu hình tối thiểu:

~~~properties
app.external.base-url=https://external.example.test
~~~

Nếu property `tenant` vắng mặt, `optionalTenant()` trả `Optional.empty()`. Nếu `timeout` vắng mặt, nó nhận `Duration.ofSeconds(2)`. Nếu `base-url` thiếu hoặc rỗng, ứng dụng có thể báo lỗi validation khi khởi động.

Điều này tạo ra hợp đồng cấu hình rõ ràng:

| Property | Hợp đồng | Xử lý |
| --- | --- | --- |
| `base-url` | Bắt buộc, không rỗng | `@NotBlank String` |
| `timeout` | Có mặc định 2 giây | `@DefaultValue("2s") Duration` |
| `tenant` | Có thể vắng mặt | `String` nullable + phương thức `optionalTenant()` |

Đây là cách sử dụng kiểu Java phù hợp với mục đích thay vì một wrapper duy nhất cho mọi trường hợp.

## 23. Checklist khi thiết kế `@ConfigurationProperties`

- **Không mặc định rằng `Optional<T>` field thiếu sẽ thành `Optional.empty()`.** Spring Boot không khuyến nghị kiểu này trong properties class.
- Phân loại rõ field thành **bắt buộc**, **có giá trị mặc định** hoặc **có thể vắng mặt**.
- Với record/constructor binding, sử dụng `@DefaultValue` cho default hợp lý.
- Với field bắt buộc, sử dụng validation như `@NotNull`, `@NotBlank` và giới hạn thích hợp.
- Với giá trị tùy chọn thật sự, bind kiểu `T` rồi trả `Optional.ofNullable(value)` ở phương thức API khi cần.
- Phân biệt **missing**, **empty string**, **whitespace** và **giá trị sai kiểu**.
- Không sử dụng một fallback để âm thầm che thiếu secret hoặc endpoint production bắt buộc.
- Không coi `Optional` là công cụ validation, security hoặc conversion.
- Khi dùng nested record, xác định rõ object con có bắt buộc, có thể thiếu hay cần default không.
- Chọn đúng cơ chế đăng ký: `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` cho record constructor-bound trong Spring Boot hiện đại.
- Kiểm tra cả source ưu tiên cao hơn, profile và external Config Data khi một field nhận giá trị khác file đang xem.
- Chỉ tạo `Optional` tại API sử dụng khi cách biểu diễn “có/không” mang lại lợi ích cho người gọi.

## 24. Kết luận

`java.util.Optional` rất hữu ích để biểu diễn **một giá trị trả về có thể vắng mặt**, nhưng **không phải lựa chọn nên dùng cho trường trong `@ConfigurationProperties`**. Trong cơ chế Spring Boot binding, một property khai báo `Optional` mà thiếu giá trị có thể nhận `null`, không bảo đảm `Optional.empty()`. Điều này phá vỡ trực giác “đã dùng Optional thì sẽ không bao giờ có null” và dễ dẫn đến `NullPointerException`.

Thiết kế thay thế:

1. **Giữ trường cấu hình ở đúng kiểu dữ liệu thực** như `String`, `Duration`, `URI`, `int` hoặc nested record.
2. **Định nghĩa default rõ ràng** qua `@DefaultValue`, default hợp lý trong Config Data hoặc JavaBean initializer.
3. **Dùng validation cho trường bắt buộc** thay vì mặc nhiên cho phép thiếu.
4. **Dùng `Optional` làm kiểu trả về của một phương thức**, chẳng hạn `Optional.ofNullable(apiKey)`, nếu consumer cần biểu diễn trạng thái vắng mặt.

Cách tiếp cận này làm rõ hợp đồng cấu hình, phù hợp với constructor binding và record, giúp startup phát hiện lỗi sớm hơn và tránh phụ thuộc vào hành vi không được Spring Boot khuyến nghị.

### Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Constructor Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot Reference — Configuration Properties Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation)
- [Java API — Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html)
