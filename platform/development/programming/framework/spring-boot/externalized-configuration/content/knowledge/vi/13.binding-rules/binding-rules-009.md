# Phân biệt liên kết thành công với cấu hình đáp ứng yêu cầu nghiệp vụ — Spring Boot 3.3

## 1. Vấn đề: “Spring Boot đã bind được” có nghĩa là hệ thống sẵn sàng chạy?

Trong Spring Boot, cấu hình có thể đến từ `application.properties`, `application.yaml`, tệp ngoài JAR, biến môi trường, thuộc tính hệ thống JVM và đối số dòng lệnh. Khi dùng `@ConfigurationProperties`, Spring Boot **liên kết** (bind) những giá trị này vào một đối tượng Java có kiểu. Đây là một khả năng rất hữu ích, nhưng việc liên kết không tự chứng minh rằng giá trị cấu hình **hợp lý, an toàn hoặc phù hợp với yêu cầu nghiệp vụ**.

Xét một ví dụ:

```yaml
app:
  payment:
    enabled: true
    retry-count: -3
    timeout: -2s
    endpoint: http://payments.example.test
```

Một Binder có thể đọc được các khóa và chuyển đổi các giá trị thành:

- `enabled`: `boolean` bằng `true`.
- `retryCount`: `int` bằng `-3`.
- `timeout`: `Duration` biểu diễn âm hai giây.
- `endpoint`: `URI` trỏ tới một địa chỉ `http`.

Nhưng có thể nghiệp vụ quy định:

- Không được thử lại số lần âm.
- Timeout phải **lớn hơn 0**.
- Khi bật thanh toán, endpoint phải sử dụng HTTPS.
- Một endpoint quan trọng phải được cấu hình và có host hợp lệ.

**Binding thành công chỉ chứng minh dữ liệu đã được ánh xạ/chuyển kiểu theo quy tắc của Binder; nó không có nghĩa các quy tắc nghiệp vụ trên đã được thỏa mãn.**

Đây là trọng tâm của bài “Phân biệt liên kết thành công với cấu hình đáp ứng yêu cầu nghiệp vụ”, thuộc chủ đề **Quy tắc liên kết** của **Spring Boot Externalized Configuration**. Ví dụ sử dụng Spring Boot **3.3.x**, Java **17+**, `@ConfigurationProperties` và Jakarta Bean Validation.

## 2. Tách bốn câu hỏi độc lập

Khi ứng dụng khởi động, có ít nhất bốn câu hỏi khác nhau:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| 1. Nguồn cấu hình | Ứng dụng có nhận đúng giá trị cuối cùng không? | `app.payment.timeout=5s` có bị biến môi trường ghi đè? |
| 2. Binding / chuyển kiểu | Dữ liệu có ánh xạ được vào kiểu Java không? | Chuỗi `5s` chuyển thành `Duration` được không? |
| 3. Validation / quy tắc cấu hình | Giá trị đã chuyển kiểu có thỏa ràng buộc không? | Timeout có lớn hơn 0 không? |
| 4. Nghiệp vụ / vận hành | Cấu hình hợp lệ trên giấy có thực sự dùng được không? | Endpoint HTTPS có chứng chỉ, quyền truy cập, kết nối và tài nguyên đáp ứng không? |

Bốn tầng không thể đánh đồng. Một ứng dụng có thể:

- **Đọc đúng nguồn nhưng bind thất bại** vì `max-workers=abc` không chuyển được sang `int`.
- **Bind thành công nhưng validation thất bại** vì `max-workers=0` vi phạm `@Min(1)`.
- **Bind và validation thành công nhưng chính sách nghiệp vụ không đạt** vì `endpoint=http://...` trong khi môi trường sản xuất bắt buộc HTTPS.
- **Qua các kiểm tra tĩnh nhưng vẫn không hoạt động** vì DNS, firewall, chứng chỉ TLS, dịch vụ từ xa hoặc thông tin xác thực không sẵn sàng.

Sơ đồ suy nghĩ:

```text
PropertySource / Config Data / Environment
                 |
                 v
      Chọn giá trị có hiệu lực
                 |
                 v
      Binder + ConversionService
           |              |
        thất bại       thành công
           |              |
    Lỗi chuyển kiểu        v
                   Bean Validation
                      |         |
                   vi phạm   hợp lệ
                      |         |
                  Lỗi khởi     v
                    động    Quy tắc nghiệp vụ
                              |        |
                           vi phạm    đạt
                              |        |
                          Từ chối     v
                                   Kiểm tra vận hành
                                        |
                                        v
                                Sẵn sàng phục vụ?
```

Không phải ứng dụng nào cũng cần thực hiện toàn bộ kiểm tra kết nối ngay khi tạo bean cấu hình. **Thời điểm và chính sách xử lý lỗi** của kiểm tra vận hành là một quyết định kiến trúc riêng.

## 3. Binding trong Spring Boot 3.3 thực sự làm gì?

Spring Boot Binder đọc các khóa cấu hình có tiền tố tương ứng và cố gắng xây dựng hoặc điền giá trị vào một đối tượng `@ConfigurationProperties`.

Ví dụ:

```yaml
app:
  worker:
    threads: 4
    shutdown-timeout: 30s
    endpoint: https://worker.example.test
```

Mô hình Java:

```java
package example.validationlab;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int threads,
        Duration shutdownTimeout,
        URI endpoint
) {
}
```

Với constructor binding của record, Binder có thể:

1. Nhận các khóa `app.worker.threads`, `app.worker.shutdown-timeout`, `app.worker.endpoint`.
2. Ánh xạ `shutdown-timeout` sang tham số Java `shutdownTimeout` theo **relaxed binding**.
3. Chuyển `4` thành số nguyên.
4. Chuyển `30s` thành `Duration`.
5. Chuyển URL dạng chuỗi thành `URI`.
6. Tạo `WorkerProperties` mang những giá trị đó.

Trong phạm vi đó, kết quả **bind thành công** là đáng tin cậy: Spring Boot đã nạp, nhận dạng tên và chuyển kiểu dữ liệu theo khả năng của Binder.

Nhưng `threads=-20` vẫn là một giá trị `int`; `shutdown-timeout=-3s` vẫn có thể là một `Duration`; và `URI.create("relative-path")` tạo một URI tương đối hợp lệ về cú pháp, dù nghiệp vụ muốn URL HTTPS tuyệt đối. Các ràng buộc đó không xuất hiện chỉ nhờ khai báo kiểu Java.

### 3.1. Kiểu dữ liệu bảo đảm điều gì?

| Kiểu đích | Binder/chuyển kiểu giúp được gì? | Điều chưa được bảo đảm |
| --- | --- | --- |
| `int` | Chuyển giá trị số nguyên hợp lệ | Số dương, không vượt giới hạn hệ thống |
| `long` | Nhận số nguyên trong phạm vi kiểu | Ý nghĩa đơn vị, giới hạn tài nguyên |
| `boolean` | Chuyển giá trị boolean được hỗ trợ | Bật tính năng có an toàn trong môi trường này không |
| `Duration` | Nhận thời lượng như `5s`, `250ms` | Dương, không quá lớn, phù hợp SLA |
| `DataSize` | Nhận kích thước dữ liệu như `10MB` | Có đủ RAM/đĩa, không vượt quota |
| `URI` | Nhận URI đúng cú pháp chuyển đổi | HTTPS, host hợp lệ, kết nối tới được |
| `String` | Nhận văn bản | Không rỗng, đúng mã định danh, không chứa giá trị cấm |
| `List<T>` | Liên kết các phần tử từ cấu hình | Không rỗng, không trùng, thứ tự phù hợp |
| `Map<K,V>` | Liên kết theo khóa và giá trị | Các khóa bắt buộc, quan hệ hợp lệ giữa các entry |

Đừng nhầm **type safety** với **business validity**. Kiểu `int` không thể thể hiện trực tiếp “từ 1 đến 16”; kiểu `URI` không tự thể hiện “phải là HTTPS và trỏ tới dịch vụ có quyền truy cập”.

### 3.2. Chuyển đổi thất bại là trường hợp khác

```properties
app.worker.threads=four
```

Nếu Binder không có converter tùy chỉnh phù hợp, nó không thể chuyển `four` sang `int` và có thể ném lỗi binding khi tạo bean cấu hình.

So sánh:

```properties
app.worker.threads=0
```

Giá trị `0` **chuyển được sang `int`**. Muốn từ chối số 0, ta cần ràng buộc như `@Min(1)` hoặc logic kiểm tra tương đương.

## 4. Bốn ví dụ “bind được nhưng không nên chạy”

### 4.1. Số worker bằng 0

```properties
app.worker.threads=0
```

`int threads` nhận 0 được. Tuy nhiên, một dịch vụ cần ít nhất một worker xử lý tác vụ sẽ không hoạt động đúng.

Một ràng buộc phù hợp:

```java
@Min(1)
int threads
```

Nếu cần giới hạn tài nguyên:

```java
@Min(1)
@Max(16)
int threads
```

Nó cho biết **miền cấu hình hợp lệ là 1–16**, khác với khả năng chuyển kiểu của Binder.

### 4.2. Timeout âm

```properties
app.worker.shutdown-timeout=-2s
```

`Duration` có thể biểu diễn giá trị âm. Nhiều API xử lý thời gian không chấp nhận timeout âm hoặc có hành vi đặc biệt khi nhận 0/âm.

Cần quy tắc “lớn hơn 0” thay vì chỉ dựa vào `Duration.class`. Có thể dùng validator tùy chỉnh hoặc một phương thức `@AssertTrue` kiểm tra:

```java
@AssertTrue(message = "shutdownTimeout must be positive")
public boolean isShutdownTimeoutPositive() {
    return shutdownTimeout != null
            && shutdownTimeout.compareTo(Duration.ZERO) > 0;
}
```

### 4.3. URI có cú pháp hợp lệ nhưng không đáp ứng chính sách bảo mật

```properties
app.payment.endpoint=http://payments.example.test
```

Chuỗi trên có thể chuyển thành `URI` thành công. Nhưng nếu dịch vụ thanh toán yêu cầu HTTPS, cấu hình vẫn không hợp lệ về nghiệp vụ.

Kiểm tra thêm:

- URI phải là **absolute URI**.
- Scheme phải là `https`.
- Host phải hiện diện.
- Nếu cần, host phải thuộc danh sách được cho phép.

Việc kiểm tra URI bằng quy tắc này vẫn **chưa** xác nhận DNS, chứng chỉ TLS, kết nối mạng hay quyền sử dụng dịch vụ.

### 4.4. Danh sách rỗng

```yaml
app:
  notification:
    recipients: []
```

Một danh sách rỗng có thể bind thành `List<String>` hợp lệ. Nhưng một chức năng gửi thông báo bắt buộc có người nhận sẽ không thể đạt mục tiêu.

Dùng `@NotEmpty` để yêu cầu ít nhất một phần tử; dùng `@NotBlank` trên phần tử nếu muốn cấm chuỗi rỗng hoặc chỉ có khoảng trắng.

Đây là hai ràng buộc khác nhau:

```java
@NotEmpty
List<@NotBlank String> recipients
```

- `@NotEmpty`: danh sách không được `null` hoặc rỗng.
- `@NotBlank` trên phần tử: mỗi địa chỉ biểu diễn bằng chuỗi không được trống.

Ngoài ra, “không trống” chưa đồng nghĩa với **email hợp lệ** hoặc **địa chỉ nhận tồn tại**. Có thể bổ sung `@Email` cho cú pháp email hoặc quy tắc nghiệp vụ tương ứng.

## 5. `@ConfigurationProperties` không tự kích hoạt Bean Validation cho mọi lớp

Để Spring Boot kiểm tra các constraint khi binding, thông thường cần:

1. Có implementation Jakarta Bean Validation trên classpath, ví dụ dependency `spring-boot-starter-validation`.
2. Gắn `@Validated` trên kiểu `@ConfigurationProperties` (hoặc cơ chế được tài liệu cho phép tương ứng).
3. Gắn các constraint như `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@NotEmpty`, `@Valid`, `@AssertTrue` đúng chỗ.
4. Đăng ký bean cấu hình theo cơ chế Spring Boot (`@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`).

**Chỉ khai báo kiểu record hoặc chỉ có annotation `@ConfigurationProperties` không tự tạo ra toàn bộ chính sách validation của doanh nghiệp.**

### 5.1. Dependency Maven

Nếu dự án dùng Spring Boot parent hoặc dependency management phù hợp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Dependency validation cần thiết bên cạnh `spring-boot-starter` hoặc starter khác mà ứng dụng đang dùng.

Spring Boot 3 sử dụng namespace Jakarta:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Không sao chép các import `javax.validation.*` của ví dụ Spring Boot 2.x vào ứng dụng Spring Boot 3.3 mà không xem xét khác biệt phiên bản.

### 5.2. `@Validated` và constraint có vai trò khác nhau

```java
@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @Min(1) int threads,
        @NotNull Duration timeout
) {
}
```

- `@ConfigurationProperties` nói rằng kiểu này đại diện một nhóm cấu hình.
- `@Validated` yêu cầu kiểm tra ràng buộc với cơ chế validation thích hợp.
- `@Min(1)` nói rõ quy tắc của `threads`.
- `@NotNull` nói rõ yêu cầu bắt buộc đối với `timeout`.

Thiếu `@Min(1)` không có quy tắc tự động “`threads` phải dương”. Thiếu `@NotNull` có thể cho phép `timeout=null` nếu không có giá trị và không có mặc định.

## 6. Các constraint thường dùng và ý nghĩa đúng của chúng

| Constraint | Dùng cho | Không tự bảo đảm |
| --- | --- | --- |
| `@NotNull` | Giá trị tham chiếu phải hiện diện | Chuỗi không rỗng, URI HTTPS |
| `@NotBlank` | Chuỗi có ký tự không phải whitespace | Đúng định dạng nghiệp vụ |
| `@NotEmpty` | Chuỗi/bộ sưu tập/map/mảng không rỗng | Từng phần tử hợp lệ |
| `@Min(n)` | Số không nhỏ hơn `n` | Số không vượt mức tối đa |
| `@Max(n)` | Số không lớn hơn `n` | Số đạt mức tối thiểu |
| `@Positive` | Số phải dương | Phù hợp hạn mức ngân sách |
| `@PositiveOrZero` | Số không âm | Không vượt hạn mức |
| `@Size(min,max)` | Độ dài hoặc số phần tử trong phạm vi | Không có phần tử trùng |
| `@Pattern` | Chuỗi khớp mẫu được cung cấp | Kết nối dịch vụ, tính hợp pháp của dữ liệu |
| `@Email` | Chuỗi phù hợp định dạng email theo validator | Hộp thư thực sự nhận được |
| `@Valid` | Kích hoạt validation lồng nhau | Tự tạo đối tượng nested đang thiếu |
| `@AssertTrue` | Giá trị boolean hoặc JavaBean property phải là `true` | Đủ mọi quy tắc nghiệp vụ chưa khai báo |

Ví dụ `@NotBlank` và `@NotNull` không tương đương:

```java
@NotNull String tenant;
```

có thể cho phép chuỗi rỗng `""`.

```java
@NotBlank String tenant;
```

từ chối `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng trong những trường hợp validator hỗ trợ.

Một `URI` đã chuyển kiểu nên dùng `@NotNull` cho tính bắt buộc, rồi kiểm tra thêm scheme/host bằng quy tắc phù hợp. Không nên giả định `@Pattern` có thể áp trực tiếp lên mọi kiểu Java bất kỳ như `URI`.

## 7. Thiết kế lớp cấu hình có đầy đủ binding và validation

Giả sử một ứng dụng gửi yêu cầu đến một gateway. Yêu cầu nghiệp vụ:

- Tính năng có thể bật hoặc tắt.
- Khi bật, endpoint phải là HTTPS tuyệt đối và có host.
- Số luồng xử lý trong khoảng 1–16.
- Timeout phải dương.
- Cấu hình retry phải tồn tại, số lần thử trong khoảng 0–10 và backoff không âm.
- Phải có ít nhất một target.
- Mỗi target có tên không rỗng và URI không được `null`.

### 7.1. YAML hợp lệ

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: config-business-validation-demo

app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test/api
    parallelism: 4
    timeout: 5s
    retry:
      attempts: 2
      backoff: 250ms
    targets:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
```

### 7.2. Java record `@ConfigurationProperties`

`src/main/java/example/validationlab/DeliveryProperties.java`:

```java
package example.validationlab;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        URI endpoint,
        @Min(1) @Max(16) int parallelism,
        @NotNull Duration timeout,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@Valid Target> targets
) {
    @AssertTrue(message = "timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout != null
                && timeout.compareTo(Duration.ZERO) > 0;
    }

    @AssertTrue(message = "enabled delivery requires an absolute HTTPS endpoint")
    public boolean isEndpointPolicyValid() {
        if (!enabled) {
            return true;
        }
        return endpoint != null
                && endpoint.isAbsolute()
                && "https".equalsIgnoreCase(endpoint.getScheme())
                && endpoint.getHost() != null;
    }

    public record Retry(
            @Min(0) @Max(10) int attempts,
            @NotNull Duration backoff
    ) {
        @AssertTrue(message = "retry backoff cannot be negative")
        public boolean isBackoffNonNegative() {
            return backoff != null && !backoff.isNegative();
        }
    }

    public record Target(
            @NotBlank String name,
            @NotNull URI url
    ) {
    }
}
```

Trong record này:

- Binder đọc dữ liệu theo prefix `app.delivery` và tạo đối tượng có kiểu.
- `@Min`/`@Max` ràng buộc các số nguyên.
- `@NotNull` bảo đảm nested `retry` và `timeout` tồn tại.
- `@Valid` trên `retry` và phần tử `Target` yêu cầu validation đi vào cấu trúc lồng.
- `@NotEmpty` cấm danh sách target rỗng.
- Hai phương thức `is...()` có `@AssertTrue` biểu diễn quy tắc khó thể hiện bằng một annotation số hoặc chuỗi.
- `enabled=false` cho phép endpoint không được cung cấp, theo chủ ý của quy tắc `isEndpointPolicyValid()`.

`@AssertTrue` áp lên những JavaBean boolean property có phương thức `is...`. Spring Boot Binder không tự suy luận những quy tắc `isTimeoutPositive()` và `isEndpointPolicyValid()`; việc kiểm tra là do **Bean Validation** thực hiện.

### 7.3. Có thể kết hợp nhiều constraint trên một thành phần

Ví dụ:

```java
@Min(1) @Max(16) int parallelism
```

Có nghĩa “số luồng tối thiểu 1, tối đa 16”, không phải “Java chỉ có thể bind được từ 1 đến 16”.

Số 0 và 100 vẫn chuyển thành `int` được. Chúng bị từ chối khi **validation** áp dụng các ràng buộc đã khai báo.

Tương tự:

```java
@NotEmpty List<@Valid Target> targets
```

- Danh sách phải có phần tử.
- Mỗi phần tử cần đi qua validation của `Target`.

Nếu cần cấm hai target trùng `name`, phải thêm quy tắc khác; `@NotEmpty` và `@NotBlank` không tự kiểm tra tính duy nhất.

## 8. Đăng ký bean cấu hình đúng cách

Ví dụ lớp ứng dụng:

`src/main/java/example/validationlab/ValidationLabApplication.java`:

```java
package example.validationlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ValidationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showSummary(DeliveryProperties properties) {
        return args -> {
            System.out.println("enabled=" + properties.enabled());
            System.out.println("parallelism=" + properties.parallelism());
            System.out.println("timeout=" + properties.timeout());
            System.out.println("targets=" + properties.targets().size());
        };
    }
}
```

`@ConfigurationPropertiesScan` đăng ký kiểu `DeliveryProperties` để Spring Boot có thể bind từ cấu hình. Với record có constructor canonical duy nhất, không cần thêm `@ConstructorBinding`.

Dùng `@EnableConfigurationProperties(DeliveryProperties.class)` cũng là lựa chọn khi muốn chỉ định kiểu rõ ràng, ví dụ trong module cấu hình riêng.

**Không gắn `@Component` tùy tiện vào record dùng constructor binding** để mong Spring container tự tạo nó bằng cơ chế autowiring. Constructor binding của `@ConfigurationProperties` cần đăng ký qua cơ chế phù hợp của Spring Boot.

Phương thức `ApplicationRunner` chỉ in các giá trị mẫu không nhạy cảm. Không in mật khẩu, token, API key hoặc giá trị có thể làm lộ hạ tầng thật.

## 9. Chạy ví dụ và hiểu kết quả

Với Maven wrapper ở hệ thống Unix:

```bash
./mvnw spring-boot:run
```

Hoặc đóng gói thành JAR rồi chạy:

```bash
java -jar app.jar
```

Thay `app.jar` bằng đường dẫn JAR thực tế của dự án. Với YAML hợp lệ, các dòng do `ApplicationRunner` in có dạng:

```text
enabled=true
parallelism=4
timeout=PT5S
targets=2
```

Kết quả này cho biết cấu hình được bind và validation cho những ràng buộc đã khai báo đã đi qua, không có nghĩa **gateway thật sự truy cập được**. Để biết dịch vụ từ xa có hoạt động hay không, cần cơ chế kiểm tra riêng trong ứng dụng hoặc trong hạ tầng.

### Thử 1 — lỗi chuyển kiểu

```bash
java -jar app.jar --app.delivery.parallelism=abc
```

`abc` không phải số nguyên. Lỗi thuộc nhóm **binding/conversion**, xảy ra trước khi có một giá trị `int` hợp lệ để so sánh `@Min` và `@Max`.

### Thử 2 — bind được nhưng vi phạm range

```bash
java -jar app.jar --app.delivery.parallelism=0
```

`0` là số nguyên hợp lệ, nên Binder có thể chuyển kiểu thành công. Nhưng `@Min(1)` bị vi phạm; ứng dụng có thể thất bại ở giai đoạn validation cấu hình.

### Thử 3 — Duration âm

```bash
java -jar app.jar --app.delivery.timeout=-2s
```

`-2s` là một thời lượng biểu diễn được. Ràng buộc `isTimeoutPositive()` trả về `false`, từ chối cấu hình này.

### Thử 4 — URI không phù hợp chính sách

```bash
java -jar app.jar --app.delivery.endpoint=http://gateway.example.test/api
```

URI có thể parse và bind bình thường. Nhưng khi `enabled=true`, quy tắc `isEndpointPolicyValid()` yêu cầu HTTPS, nên validation thất bại.

### Thử 5 — giảm concurrency xuống mức hợp lệ

```bash
java -jar app.jar --app.delivery.parallelism=2
```

Với các thuộc tính khác giữ như YAML hợp lệ, số 2 đạt giới hạn 1–16. Ứng dụng có thể qua phần validation tĩnh.

**Lưu ý:** các ví dụ không cho rằng mọi lỗi sẽ có cùng một class exception hoặc cùng format thông báo. Loại ngoại lệ bao ngoài có thể khác theo converter, loại bean và giai đoạn khởi tạo; hãy đọc chuỗi nguyên nhân trong startup log.

## 10. Một bảng chẩn đoán bốn trạng thái

| Giá trị cấu hình | Binding / chuyển kiểu | Validation | Nhận định |
| --- | --- | --- | --- |
| `parallelism=abc` | Thất bại | Chưa có giá trị hợp lệ để kiểm tra | Sai kiểu |
| `parallelism=0` | Thành công (`int`) | Thất bại `@Min(1)` | Sai giới hạn |
| `parallelism=4` | Thành công | Đạt các ràng buộc đã khai báo | Chưa bảo đảm đủ CPU |
| `timeout=-2s` | Có thể thành công (`Duration`) | Thất bại `@AssertTrue` | Sai chính sách timeout |
| `endpoint=http://...` | Có thể thành công (`URI`) | Thất bại policy HTTPS khi bật | Sai chính sách transport |
| `endpoint=https://...` | Thành công | Có thể đạt policy tĩnh | DNS/TLS/dịch vụ vẫn có thể lỗi |
| `targets=[]` | Có thể thành công (`List`) | Thất bại `@NotEmpty` | Không có target |
| `target.name="   "` | Thành công (`String`) | Thất bại `@NotBlank` | Tên không dùng được |
| `retry.attempts=2` | Thành công | Đạt `@Min(0) @Max(10)` | Chưa chứng minh chiến lược retry có ích |

Khi thấy một ứng dụng chạy thành công, câu hỏi tiếp theo không chỉ là **“Bind được chưa?”** mà là **“Những ràng buộc nào thực sự đã được kiểm tra?”**

## 11. Thiếu khóa không nhất thiết gây lỗi binding

Giả sử record:

```java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        int capacity,
        boolean enabled,
        String name
) {
}
```

Nếu thiếu một số khóa:

- `int` có thể nhận giá trị mặc định của kiểu nguyên thủy (`0`) trong binding phù hợp.
- `boolean` có thể nhận `false`.
- `String` có thể là `null`.
- Với nhiều kiểu tham chiếu khác, giá trị thiếu có thể thành `null` nếu không có default hoặc xử lý đặc biệt.

Đừng suy luận rằng constructor của record có tham số nên **mọi tham số là bắt buộc** và Spring Boot phải từ chối nếu thiếu khóa. Constructor binding quyết định cách cấp đối số, không tự suy ra tính bắt buộc của nghiệp vụ.

Nếu `capacity=0` gây nguy hiểm, hãy khai báo:

```java
@Min(1) int capacity
```

Nếu tên bắt buộc:

```java
@NotBlank String name
```

Nếu `enabled=false` là một giá trị mặc định được chấp nhận, nên thể hiện chủ đích bằng mô hình hoặc tài liệu cấu hình rõ ràng.

### 11.1. Giá trị mặc định có thể che lỗi thiếu cấu hình

Ví dụ:

```java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        @DefaultValue("100") int capacity
) {
}
```

Khi không có `app.queue.capacity`, Binder có thể cấp `100`. Điều này phù hợp nếu 100 là default đã được nghiệp vụ chấp nhận. Nhưng nếu production **bắt buộc** cung cấp capacity sau khi sizing, một default ngầm có thể làm hệ thống chạy với mức tài nguyên không mong muốn.

`@DefaultValue` trả lời “dùng gì khi khóa không có”, **không** trả lời “có được phép vắng khóa trong môi trường này hay không”.

### 11.2. Không dùng default như cách chữa mọi lỗi

Giá trị:

```properties
app.queue.capacity=-3
```

vẫn là một số nguyên cụ thể. `@DefaultValue("100")` không tự thay thế `-3` vì số này tồn tại. Nếu muốn từ chối số âm, vẫn cần `@Min(1)` hoặc quy tắc tương đương.

Nếu người dùng nhập:

```properties
app.queue.capacity=not-a-number
```

thì vấn đề là chuyển kiểu; default không làm chuỗi sai trở thành số hợp lệ.

## 12. Đừng bỏ qua các khóa cấu hình chưa được nhận diện

Spring Boot `@ConfigurationProperties` có tùy chọn quan trọng:

```java
@ConfigurationProperties(
        prefix = "app.delivery",
        ignoreUnknownFields = false
)
```

Mặc định, `ignoreUnknownFields` là `true`. Điều này giúp Binder dung nạp một số khóa không có property tương ứng trên kiểu đích, nhưng cũng có thể làm **sai chính tả** hoặc khóa thừa không được phát hiện theo cách bạn mong đợi.

Ví dụ:

```properties
app.delivery.paralellism=8
```

Khóa `paralellism` bị đánh máy sai. Nếu nó không tương ứng với trường `parallelism`, Binder có thể bỏ qua khóa không nhận diện, còn `parallelism` nhận giá trị mặc định/thiếu tùy kiểu.

Hai lớp lỗi xảy ra:

1. Cấu hình nguồn chứa một khóa **lạ**.
2. Trường mong muốn bị **thiếu**.

Khi mô hình cấu hình là một schema có quyền sở hữu rõ ràng, có thể cân nhắc `ignoreUnknownFields=false` để phát hiện khóa thừa. Tuy nhiên, hãy hiểu phạm vi prefix và các nguồn cấu hình được dùng trước khi bật chế độ nghiêm ngặt, nhất là nếu nhiều thành phần dùng các khóa dưới cùng một prefix.

Một tùy chọn khác:

```java
@ConfigurationProperties(ignoreInvalidFields = false, prefix = "app.delivery")
```

`ignoreInvalidFields` mặc định là `false`, nghĩa là lỗi binding/chuyển kiểu không bị lờ đi theo chế độ này. Nó **không thay thế validation nghiệp vụ**. Đặt `ignoreInvalidFields=true` bừa bãi có thể che lỗi dữ liệu sai kiểu, không phải cách để ứng dụng “ổn định” hơn.

Quyết định về unknown fields và invalid fields thuộc **chính sách cấu hình đầu vào**, còn quy tắc như “timeout > 0” vẫn cần lớp validation riêng.

## 13. Quy tắc liên trường (cross-field) không suy ra từ kiểu đơn lẻ

Nhiều yêu cầu nghiệp vụ có dạng “nếu A thì B”, chẳng hạn:

- Nếu bật tính năng gửi mail thì `from-address` và `smtp.host` phải có.
- Nếu `retry.attempts > 0` thì `retry.backoff > 0`.
- Nếu `enabled=true` thì endpoint phải là HTTPS.
- `min-size` không được lớn hơn `max-size`.
- Nếu `mode=EXTERNAL` thì `provider-id` là bắt buộc.
- Nếu có `primary` thì phải có một đường dự phòng phù hợp với chính sách.

`@NotNull`, `@Min` và `@Max` trên từng field không thể biểu đạt đầy đủ **quan hệ giữa các field**.

### 13.1. Dùng `@AssertTrue` cho một quy tắc nhỏ, dễ đọc

Giả sử:

```java
@Validated
@ConfigurationProperties(prefix = "app.pool")
public record PoolProperties(
        @Min(1) int minSize,
        @Min(1) int maxSize
) {
    @AssertTrue(message = "minSize must not exceed maxSize")
    public boolean isRangeConsistent() {
        return minSize <= maxSize;
    }
}
```

Cấu hình:

```properties
app.pool.min-size=10
app.pool.max-size=3
```

Cả hai số đều lớn hơn hoặc bằng 1, nhưng quan hệ `minSize <= maxSize` bị vi phạm.

Vì vậy:

- Validation từng field: **đạt**.
- Validation cross-field: **không đạt**.
- Binding: **thành công**.

Đó là minh họa điển hình về việc tách kết quả chuyển kiểu và tính đúng đắn nghiệp vụ.

### 13.2. Khi nào cần custom constraint?

Nếu quy tắc liên trường phức tạp, dùng một phương thức `@AssertTrue` quá dài sẽ làm record khó bảo trì. Có thể xây dựng **custom Jakarta Bean Validation constraint** ở cấp class với `ConstraintValidator` riêng.

Một custom validator thường nhận cả đối tượng cấu hình, so sánh các field và đưa ra thông báo vi phạm có ý nghĩa. Nó hữu ích khi:

- Quy tắc được dùng lại ở nhiều nhóm cấu hình.
- Quy tắc có nhiều trường và nhiều điều kiện.
- Muốn thông báo lỗi rõ ở property phù hợp.
- Cần tách logic nghiệp vụ cấu hình khỏi dữ liệu model.

**Không nên đưa I/O, gọi HTTP, kết nối database hay đọc bí mật từ nơi khác vào `ConstraintValidator` cho mọi trường hợp.** Validation cấu hình diễn ra rất sớm; kiểm tra bên ngoài nặng hoặc không ổn định có thể tạo startup failure khó lý giải.

## 14. Validation nested object phải được kích hoạt rõ ràng

Một ví dụ:

```java
@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull @Valid Smtp smtp
) {
    public record Smtp(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {
    }
}
```

`@NotNull` trên `smtp` bảo đảm object lồng không bị thiếu.

`@Valid` cho phép Bean Validation đi vào object `Smtp` để kiểm tra `host` và `port`.

**Nếu bỏ `@Valid`**, bạn không nên mặc định các constraint bên trong nested object luôn được kiểm tra theo cách mong muốn. Tài liệu Spring Boot nhấn mạnh `@Valid` cho validation thuộc tính lồng, đặc biệt khi muốn kiểm tra ngay cả lúc không tìm thấy các khóa con thích hợp.

### 14.1. Danh sách cấu trúc lồng nhau

```java
public record MailProperties(
        @NotEmpty List<@Valid Recipient> recipients
) {
    public record Recipient(
            @NotBlank String name,
            @NotBlank @Email String address
    ) {}
}
```

Cần các import:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
```

- `@NotEmpty` trên danh sách cấm thiếu toàn bộ người nhận.
- `@Valid` đi vào từng `Recipient`.
- `@NotBlank` cấm tên và địa chỉ trống.
- `@Email` hỗ trợ kiểm tra **định dạng**, không xác thực khả năng nhận mail thật.

Nếu doanh nghiệp yêu cầu các địa chỉ không trùng nhau, phải thêm ràng buộc khác; những annotation trong ví dụ không tự kiểm tra uniqueness.

### 14.2. Missing nested khác nested có giá trị invalid

Xét:

```yaml
app:
  mail:
    smtp:
      host: ""
      port: 0
```

Binder có thể tạo object `Smtp`, rồi các constraint trên `host`, `port` thất bại.

Nếu hoàn toàn không có `smtp`, với kiểu tham chiếu trong record có thể là `null`; `@NotNull` từ chối trạng thái ấy. `@Valid` không tự biến `null` thành một object mới. Hãy kết hợp yêu cầu bắt buộc và cascade validation đúng với mô hình.

## 15. `@Value` và `Environment` có tự bảo đảm validation nghiệp vụ không?

Không.

Ví dụ:

```java
@Component
public class BatchWorker {

    @Value("${app.worker.threads:0}")
    private int threads;
}
```

Một giá trị `0` có thể được chuyển thành `int` và tiêm thành công. Dùng `@Value` không tự có validation cấu hình tương đương với một `@Validated @ConfigurationProperties` được đăng ký và bind đúng cách.

Tương tự:

```java
int threads = environment.getProperty(
        "app.worker.threads", Integer.class, 0);
```

đọc được `0` không có nghĩa rằng `0` phù hợp cho một worker pool.

Với một hoặc hai giá trị scalar nhỏ, bạn có thể kiểm tra nghiệp vụ ở nơi sử dụng. Nhưng khi một nhóm cấu hình có nhiều trường, mối quan hệ và nhiều điểm tiêu thụ, `@ConfigurationProperties` + validation tập trung thường giúp tránh việc mỗi bean định nghĩa một quy tắc khác nhau.

Một điểm cần nhớ: `@Value` có cú pháp placeholder và có thể dùng SpEL, nhưng **relaxed binding của nó hạn chế hơn** so với `@ConfigurationProperties`. Khuyến nghị sử dụng tên khóa canonical dạng `kebab-case` trong placeholder; đây là vấn đề **ánh xạ tên**, khác hoàn toàn với yêu cầu nghiệp vụ.

## 16. Giá trị “đúng” còn phụ thuộc nguồn nào đã thắng

Giả sử:

`application.yaml`:

```yaml
app:
  delivery:
    parallelism: 4
```

Nhưng môi trường triển khai có:

```text
APP_DELIVERY_PARALLELISM=100
```

Hoặc lệnh chạy:

```bash
java -jar app.jar --app.delivery.parallelism=100
```

Với cấu hình ưu tiên thông thường, nguồn từ môi trường/đối số có thể ghi đè giá trị của tệp. Khi Binder liên kết, nó không “chọn” 4 chỉ vì trong YAML có 4; nó dùng **giá trị có hiệu lực** sau quy tắc ưu tiên của `Environment`.

Nếu có `@Max(16)`, validation có thể từ chối giá trị 100. Đây là điều tốt: validation cần được áp dụng với **cấu hình cuối cùng**, không chỉ các giá trị trong file mặc định.

Một hệ thống cấu hình có thể thay đổi giữa:

- `application.yaml` đóng gói trong JAR.
- `application-prod.yaml`.
- Tệp cấu hình bên ngoài.
- `spring.config.import`.
- Biến môi trường.
- Thuộc tính JVM.
- Đối số dòng lệnh.

Cách phát hiện “sai vì nguồn nào?” phải xét **nguồn ưu tiên**, không chỉ so sánh class Java với một tệp cụ thể.

### 16.1. Tên biến môi trường phải đúng

Tên canonical `app.delivery.parallelism` tương ứng với biến môi trường:

```text
APP_DELIVERY_PARALLELISM
```

Với `app.delivery.retry-count`, biến môi trường tương ứng là:

```text
APP_DELIVERY_RETRYCOUNT
```

Spring Boot có quy tắc relaxed binding: thay dấu `.` bằng `_`, bỏ dấu `-`, đổi chữ thành in hoa. Nếu khai báo sai tên biến môi trường, giá trị có thể không liên kết như kỳ vọng — đó là vấn đề **binding/name mapping** chứ chưa phải validation nghiệp vụ.

## 17. Không phải mọi ràng buộc đều nên áp dụng như nhau cho mọi môi trường

Có những giá trị chỉ hợp lệ trong một môi trường nhất định. Ví dụ:

- `http://localhost` có thể phù hợp khi chạy phát triển, nhưng production bắt buộc HTTPS.
- Một số worker không được vượt quá 2 trong môi trường test, nhưng có thể dùng đến 16 trong production.
- Một tính năng có thể được phép chạy khi thiếu endpoint nếu nó được tắt.
- Một profile dùng dịch vụ giả lập (stub) trong phát triển, còn production yêu cầu endpoint thật.

Có thể tổ chức giá trị theo profile:

```yaml
app:
  delivery:
    enabled: false
    parallelism: 2
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test/api
    parallelism: 8
```

Trong ví dụ này, tài liệu `prod` ghi đè `enabled`, `endpoint` và `parallelism`.

Nhưng **profile không tự tạo ràng buộc nghiệp vụ**. Nếu production bắt buộc HTTPS, có thể dùng chính sách chỉ áp dụng khi `enabled=true` như `isEndpointPolicyValid()` ở phần trước hoặc một cơ chế validation chuyên biệt.

Không nên dùng `spring.profiles.active` bên trong tài liệu vốn được kích hoạt bằng `spring.config.activate.on-profile` để điều khiển lại profile. Hãy chọn profile ở một nguồn hợp lệ và để tài liệu có điều kiện chỉ cung cấp phần giá trị cần thay đổi.

### Khi nào nên dùng default?

Nếu một giá trị có default an toàn và giống nhau cho mọi môi trường, có thể đặt trong cấu hình chung hoặc `@DefaultValue`.

Nếu một giá trị phải được cấp rõ ràng trong production, tránh đặt default vô tình giúp ứng dụng khởi động nhưng chạy với cấu hình sai. Quy tắc “thiếu là lỗi” cần được biểu đạt bằng validation hoặc kiểm tra khởi động tương ứng.

## 18. Một URI hợp lệ về cú pháp chưa chắc được phép theo bảo mật

Xét ba giá trị:

```properties
app.delivery.endpoint=relative/path
```

```properties
app.delivery.endpoint=http://gateway.example.test
```

```properties
app.delivery.endpoint=https://gateway.example.test
```

Với kiểu `URI`, chúng có thể là các URI được parse thành công theo những ngữ nghĩa khác nhau.

Nhưng một gateway cần HTTPS tuyệt đối:

- `relative/path`: thiếu scheme và host; không phù hợp.
- `http://gateway.example.test`: có scheme/host nhưng giao thức không phù hợp.
- `https://gateway.example.test`: đạt điều kiện hình thức được khai báo.

Ngay cả URI thứ ba vẫn có thể:

- Trỏ tới host không resolve DNS.
- Có chứng chỉ TLS hết hạn.
- Bị firewall chặn.
- Không có quyền xác thực đúng.
- Phản hồi sai giao thức hoặc không đáp ứng SLA.

**Kiểm tra hình thức** nên diễn ra trước khi sử dụng. **Kiểm tra phụ thuộc bên ngoài** nên có chính sách timeout, retry, circuit breaker, readiness và cách báo lỗi phù hợp.

Không nên đưa một cuộc gọi HTTP vô hạn hoặc nhiều phép thử kết nối vào constructor của `@ConfigurationProperties` chỉ để chứng minh URI “hợp lệ”.

## 19. Ba loại lỗi cần báo rõ trong log và vận hành

### Loại A — lỗi chuyển kiểu hoặc giải quyết khóa

Ví dụ:

```properties
app.delivery.timeout=tomorrow
```

Nếu Binder không có cách chuyển `"tomorrow"` sang `Duration`, cấu hình thất bại ở tầng **chuyển đổi kiểu**.

Thông báo hữu ích cần chỉ ra khóa cấu hình, kiểu cần nhận và nguyên nhân chuyển đổi. Không cố gắng “chữa” bằng `ignoreInvalidFields=true` nếu timeout là giá trị bắt buộc.

### Loại B — giá trị có kiểu nhưng vi phạm constraint

Ví dụ:

```properties
app.delivery.parallelism=0
```

Giá trị số nguyên hợp lệ nhưng vi phạm `@Min(1)`.

Thông báo nên chỉ rõ `parallelism` phải ở trong khoảng nào, tránh câu quá chung như “Configuration invalid” mà không biết sửa trường gì.

### Loại C — qua validation tĩnh nhưng phụ thuộc ngoài không sẵn sàng

Ví dụ HTTPS endpoint hợp lệ nhưng server trả lỗi 503.

Đây không phải lỗi parse URI và cũng không nhất thiết là cấu hình sai. Có thể là dịch vụ từ xa đang bảo trì hoặc mạng chưa sẵn sàng.

Cách xử lý phụ thuộc yêu cầu:

- Dịch vụ tối quan trọng có thể chọn **fail-fast** hoặc đánh dấu **not ready**.
- Tính năng tùy chọn có thể chạy ở chế độ suy giảm rõ ràng.
- Hệ thống có thể retry có giới hạn, có backoff và metrics để quan sát.

Nếu mọi lỗi đều được gom thành “bind failed”, người vận hành sẽ sửa nhầm cấu hình trong khi vấn đề thực là kết nối.

## 20. Quyết định fail-fast hay cho phép suy giảm dịch vụ

Không phải mọi sai lệch đều nên bị xử lý giống nhau.

| Tình huống | Gợi ý chính sách |
| --- | --- |
| Giá trị bắt buộc không chuyển được kiểu | Thường dừng khởi động |
| Giá trị vượt giới hạn nguy hiểm | Thường dừng khởi động |
| Thiếu thông tin quan trọng để bật tính năng | Từ chối bật hoặc dừng theo mức thiết yếu |
| Tính năng đã tắt và endpoint không cần dùng | Có thể không yêu cầu endpoint |
| Dịch vụ phụ trợ tạm thời không truy cập được | Dựa vào readiness, retry có giới hạn và chế độ suy giảm |
| Một giá trị ít quan trọng không có | Dùng default đã được chấp thuận |
| Cấu hình có thể làm rò rỉ dữ liệu | Không nên âm thầm tiếp tục với default thiếu an toàn |

Một nguyên tắc có ích: **fail fast với cấu hình sai rõ ràng**; với phụ thuộc động, xác định chính sách chịu lỗi và readiness có chủ đích. Không nên biến startup thành quá trình thử kết nối vô hạn với mọi dịch vụ.

Trong hệ thống có tính năng bật/tắt, validation nên thể hiện điều kiện nghiệp vụ. Ví dụ “`endpoint` bắt buộc khi `enabled=true`” chính xác hơn “`endpoint` luôn bắt buộc” nếu yêu cầu cho phép tắt tính năng.

## 21. Cấu hình biến đổi theo thời gian

Thông thường, `@ConfigurationProperties` được bind khi application context khởi tạo. Thay đổi một biến môi trường hoặc tệp cấu hình sau khi tiến trình Java đã chạy **không có nghĩa** mọi bean tự nhận dữ liệu mới.

Ví dụ:

1. Ứng dụng khởi động với `parallelism=4`.
2. Người vận hành chỉnh biến môi trường tại terminal thành `parallelism=16`.
3. Tiến trình đang chạy không nhất thiết tự thay đổi giá trị trong bean.

Nếu hệ thống cần **dynamic configuration**, phải có cơ chế làm mới riêng và xác định rõ:

- Những phần nào được phép làm mới.
- Validation được chạy lại khi nào.
- Giá trị cũ có tiếp tục được sử dụng nếu giá trị mới sai không.
- Tình trạng ứng dụng cần báo ra sao khi reload thất bại.
- Có cần khóa hoặc chuyển đổi nguyên tử khi nhiều bean cùng đọc cấu hình không.

**Một giá trị đã từng bind và validate thành công khi khởi động không chứng minh rằng tất cả cấu hình sẽ mãi đúng khi môi trường thay đổi.**

## 22. Kiểm thử tính đúng đắn của cấu hình

Một bài học dễ hiểu nên có các trường hợp thử tách biệt.

### 22.1. Ma trận thử tối thiểu

| Test | Giá trị thay đổi | Kỳ vọng |
| --- | --- | --- |
| Giá trị hợp lệ | `parallelism=4`, `timeout=5s`, HTTPS | Khởi động thành công |
| Không chuyển được kiểu | `parallelism=abc` | Lỗi binding |
| Dưới giới hạn | `parallelism=0` | Lỗi validation |
| Trên giới hạn | `parallelism=100` | Lỗi validation |
| Timeout âm | `timeout=-1s` | Lỗi validation nghiệp vụ |
| Thiếu retry | Bỏ cả nhóm `retry` | Lỗi `@NotNull` nếu yêu cầu |
| Target trống | `targets=[]` | Lỗi `@NotEmpty` |
| Tên target trống | `targets[0].name=""` | Lỗi `@NotBlank` của phần tử |
| HTTP khi bật | `enabled=true`, `endpoint=http://...` | Lỗi policy HTTPS |
| Tắt tính năng | `enabled=false`, endpoint có thể thiếu | Phụ thuộc chính sách đã khai báo |
| HTTPS nhưng server tắt | `endpoint=https://...` | Validation tĩnh có thể đạt, kiểm tra vận hành không đạt |

Các trường hợp này giúp kiểm tra **ba nhóm hành vi khác nhau**, không chỉ kiểm tra có tạo được bean hay không.

### 22.2. Kiểm thử unit đối với rule bằng Jakarta Validator

Có thể kiểm tra một đối tượng cấu hình bằng Bean Validation, không cần khởi động toàn bộ ứng dụng. Ví dụ JUnit 5/AssertJ, với dependency validation trong test:

```java
package example.validationlab;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

class DeliveryPropertiesValidationTest {

    @Test
    void rejectsHttpEndpointWhenEnabled() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            DeliveryProperties properties = new DeliveryProperties(
                    true,
                    URI.create("http://gateway.example.test"),
                    4,
                    Duration.ofSeconds(5),
                    new DeliveryProperties.Retry(
                            2, Duration.ofMillis(250)),
                    List.of(new DeliveryProperties.Target(
                            "primary",
                            URI.create("https://primary.example.test")))
            );

            var violations = validator.validate(properties);
            assertThat(violations)
                    .anyMatch(v -> v.getMessage()
                            .contains("absolute HTTPS endpoint"));
        }
    }
}
```

Test trên xây dựng object Java trực tiếp rồi gọi Bean Validation; nó **kiểm tra quy tắc validation**, không chứng minh quá trình Binding từ YAML hay biến môi trường đã hoạt động.

### 22.3. Kiểm thử tích hợp cho Binder

Một test riêng cần nạp nguồn cấu hình thực tế rồi xác nhận:

- Khóa được Binder nhận đúng dưới prefix.
- Các đơn vị `Duration` và các kiểu phức tạp chuyển đúng.
- Sai kiểu gây lỗi binding.
- Giá trị đã bind nhưng vi phạm constraint làm application context không khởi động hoặc cung cấp lỗi validation tương ứng.
- Profile hoặc đối số có ưu tiên hơn được xử lý đúng.

Trong Spring Boot, có thể dùng `ApplicationContextRunner` và `@EnableConfigurationProperties`/auto-configuration thích hợp, hoặc kiểm thử Spring Boot context với properties của test. Khi viết test, hãy bảo đảm validation infrastructure thực sự được cấu hình, thay vì chỉ kiểm tra bean được tạo.

**Unit test rule** và **integration test binding** bổ sung cho nhau; không dùng kết quả của một bài test để khẳng định cả hai cơ chế đều đúng.

### 22.4. Kiểm thử nghiệp vụ sau khi cấu hình hợp lệ

Nếu yêu cầu “endpoint phải hoạt động”, cần thử thêm tương tác với một dịch vụ giả lập hoặc test environment:

- Chấp nhận request theo giao thức mong muốn.
- Thất bại có kiểm soát khi endpoint trả lỗi.
- Timeout và retry thực sự được áp dụng.
- Không gửi dữ liệu nhạy cảm tới host ngoài phạm vi được cho phép.

Các kiểm thử này thuộc tầng **hành vi hệ thống**, không thuộc trách nhiệm tự động của Spring Boot Binder.

## 23. Tìm nguyên nhân khi cấu hình khởi động sai

Một quy trình chẩn đoán:

```text
Ứng dụng không khởi động / chạy sai
             |
             v
1. Xác định giá trị có hiệu lực
   - profile đang bật?
   - file mặc định / import / external config?
   - environment / JVM / CLI override?
             |
             v
2. Xác định trạng thái Binding
   - khóa được nhận đúng?
   - converter nhận đúng kiểu?
             |
             v
3. Đọc kết quả Validation
   - field nào vi phạm?
   - @Valid nested đã bật?
   - default có che dữ liệu thiếu?
             |
             v
4. Đọc chính sách nghiệp vụ
   - cross-field? HTTPS? min <= max?
   - tính năng bật hay tắt?
             |
             v
5. Kiểm tra trạng thái vận hành
   - DNS/TLS/network/credentials/remote service
             |
             v
Xử lý đúng nguyên nhân thay vì thay bừa cấu hình
```

Ví dụ đọc giá trị cuối trong môi trường phát triển:

```java
@Bean
ApplicationRunner showEffectiveConfiguration(Environment env) {
    return args -> {
        System.out.println(
                "parallelism="
                + env.getProperty("app.delivery.parallelism"));
    };
}
```

Đây là phương thức `@Bean` **đặt bên trong** một lớp `@Configuration` hoặc `@SpringBootApplication`, không phải một tệp Java độc lập chỉ chứa method.

Nếu dùng Spring Boot Actuator, các endpoint như `/actuator/configprops` và `/actuator/env` có thể giúp quan sát cấu hình, nhưng phải được bảo vệ và thiết lập xử lý dữ liệu nhạy cảm phù hợp. Không công khai các endpoint này chỉ để debug và không in mật khẩu, token, private key hoặc connection string chứa secret vào log.

### 23.1. Không chẩn đoán bằng giá trị trong một file duy nhất

Giả sử `application.properties` có:

```properties
app.delivery.parallelism=4
```

nhưng bean nhận `8`. Nguyên nhân có thể hoàn toàn hợp lệ: một profile hoặc biến môi trường cung cấp giá trị ưu tiên cao hơn. Binder đang làm đúng nhiệm vụ.

Trước khi sửa class cấu hình, hãy tìm **PropertySource cuối cùng đã thắng**. Việc sửa `@Min`, `@Max` để ép đúng một giá trị mà không hiểu nguồn ghi đè có thể che vấn đề cấu hình của môi trường.

### 23.2. Lỗi của Binder khác lỗi của validation

Đừng gọi mọi lỗi khởi động do properties là “binding error” theo nghĩa hẹp. Ví dụ:

```text
parallelism=abc
    -> không thể chuyển thành int

parallelism=0
    -> int hợp lệ nhưng vi phạm @Min(1)

endpoint=https://gateway.example.test
    -> URI và validation tĩnh có thể đúng, remote có thể không đáp ứng
```

Cùng xảy ra gần thời điểm khởi động nhưng nguyên nhân và hướng sửa khác nhau.

## 24. Các sai lầm thường gặp

| Hiểu nhầm | Thực tế | Hướng làm đúng |
| --- | --- | --- |
| “Có bean `@ConfigurationProperties` tức cấu hình đúng” | Bean có thể chứa giá trị vô nghĩa | Định nghĩa và áp dụng constraint |
| “Chuyển được sang `Duration` là timeout hợp lệ” | `Duration` có thể là 0 hoặc âm | Kiểm tra miền thời gian |
| “URI parse được thì gọi được dịch vụ” | URI chỉ là mô tả địa chỉ | Kiểm tra scheme, host; kiểm tra kết nối riêng |
| “`@NotNull` đủ cho mọi chuỗi” | Chuỗi rỗng vẫn không null | Dùng `@NotBlank` |
| “`@NotEmpty` kiểm tra từng phần tử” | Nó chỉ kiểm tra collection không rỗng | Dùng `@Valid` và constraint ở phần tử |
| “`@DefaultValue` sửa mọi cấu hình sai” | Chỉ xử lý thiếu giá trị theo cơ chế binding | Dùng validation cho giá trị sai |
| “Constructor có tham số tự làm field required” | Tham số có thể nhận giá trị mặc định/null | Khai báo yêu cầu bắt buộc |
| “Unknown field luôn gây lỗi” | Có tùy chọn mặc định cho phép bỏ qua | Cân nhắc schema strict có chủ đích |
| “Tắt feature cũng phải có endpoint” | Phụ thuộc quy tắc thật | Validation theo điều kiện `enabled` |
| “`@Value` có kiểm tra nghiệp vụ như Binder” | Không có lớp validation cấu trúc tương đương tự động | Tạo model `@ConfigurationProperties` |
| “Validation thành công thì downstream sống” | Dịch vụ ngoài có thể down hoặc lỗi TLS | Readiness và xử lý lỗi vận hành |
| “Sửa biến môi trường là bean tự đổi” | Tiến trình Java không tự nhận thay đổi | Restart hoặc cơ chế refresh được thiết kế |
| “Test tạo object trực tiếp chứng minh YAML bind đúng” | Test đó không kiểm tra đường đi của Binder | Thêm integration test |
| “Có @Validated là tất cả nested được kiểm tra” | Thiếu @Valid có thể bỏ qua nested validation | Đặt `@Valid` đúng mức |
| “Có default là yêu cầu đã được làm rõ” | Default có thể che giá trị bắt buộc | Phân loại required vs optional |

## 25. Quy ước thiết kế cấu hình cho dự án

Một nhóm cấu hình tốt nên có “hợp đồng” rõ ràng:

| Thành phần hợp đồng | Câu hỏi cần trả lời |
| --- | --- |
| Tên khóa | Prefix và dạng canonical `kebab-case` là gì? |
| Kiểu dữ liệu | `int`, `Duration`, `URI`, `List`, `Map` hay record lồng nhau? |
| Mặc định | Có default hợp lý và an toàn không? |
| Bắt buộc | Khi nào thiếu khóa phải báo lỗi? |
| Miền giá trị | Min/max, positive, không trống, danh sách không rỗng? |
| Quan hệ trường | Nếu bật feature thì cần các trường nào? |
| Khác biệt môi trường | Có profile nào yêu cầu chính sách nghiêm hơn? |
| Phụ thuộc ngoài | Có endpoint, DNS, chứng chỉ hoặc credentials phải kiểm tra không? |
| Phản ứng khi lỗi | Fail-fast, not-ready hay suy giảm có kiểm soát? |
| Kiểm thử | Test chuyển kiểu, validation, profile và hành vi vận hành nào? |

Có thể coi việc thiết kế config là viết một **giao diện đầu vào cho ứng dụng**, không chỉ là đặt vài khóa trong YAML.

Các khuyến nghị:

1. **Ưu tiên `@ConfigurationProperties`** cho nhóm cấu hình có cấu trúc.
2. **Dùng kiểu Java thích hợp**, đặc biệt `Duration`, `DataSize`, `URI` thay vì chuỗi bất kỳ khi có converter tương ứng.
3. **Bật validation có chủ đích** bằng `@Validated` và Jakarta Bean Validation.
4. **Đặt constraint ở đúng tầng:** field, phần tử collection, nested object và cross-field.
5. **Tránh dùng giá trị mặc định để che lỗi bắt buộc.**
6. **Tách validation tĩnh khỏi kiểm tra kết nối ngoài.**
7. **Xác định rõ fail-fast hoặc graceful degradation** theo mức quan trọng của tính năng.
8. **Xem xét unknown fields** nếu cấu hình cần schema nghiêm ngặt.
9. **Kiểm thử cả đường đi từ nguồn cấu hình đến model Java**, không chỉ tạo object thủ công.
10. **Không tiết lộ secret qua log/debug endpoint.**

## 26. Bài tập tự kiểm tra

### Bài 1 — số nguyên âm

```properties
app.worker.threads=-4
```

Record:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int threads) {}
```

**Hỏi:** Binder có thể tạo object không? Nếu ứng dụng cần ít nhất một worker, đã đủ an toàn chưa?

**Đáp án:** `-4` là `int` hợp lệ nên việc chuyển kiểu có thể thành công. Chưa đủ an toàn. Cần thêm ràng buộc như `@Min(1)` và kích hoạt validation.

### Bài 2 — một thời lượng không mong muốn

```properties
app.worker.timeout=-5s
```

**Hỏi:** Vì sao `Duration timeout` chưa đủ?

**Đáp án:** `Duration` có thể biểu diễn số âm. Nếu timeout phải dương, cần constraint/custom rule rõ ràng. Chuyển kiểu và tính đúng đắn nghiệp vụ là hai phép kiểm tra khác nhau.

### Bài 3 — thiếu trường bắt buộc

```yaml
app:
  worker:
    enabled: true
```

Record:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(boolean enabled, URI endpoint) {}
```

**Hỏi:** Có thể kết luận Binder tự từ chối vì `endpoint` là tham số constructor không?

**Đáp án:** Không nên. Cấu hình thiếu có thể khiến tham số tham chiếu là `null`. Nếu endpoint bắt buộc, hãy dùng `@NotNull` hoặc điều kiện cross-field phù hợp và bật validation.

### Bài 4 — hai số đều hợp lệ nhưng quan hệ sai

```properties
app.pool.min-size=10
app.pool.max-size=5
```

**Hỏi:** Nếu cả hai trường chỉ có `@Min(1)`, cấu hình đã đáp ứng nghiệp vụ chưa?

**Đáp án:** Chưa. Cả hai riêng lẻ đều từ 1 trở lên, nhưng `minSize > maxSize`. Cần kiểm tra quan hệ cross-field.

### Bài 5 — target rỗng

```yaml
app:
  delivery:
    targets: []
```

**Hỏi:** `List<Target>` bind thành công có chứng minh có endpoint gửi thông điệp không?

**Đáp án:** Không. Danh sách có thể rỗng; dùng `@NotEmpty` và `@Valid` trên phần tử nếu chức năng yêu cầu có ít nhất một target hợp lệ.

### Bài 6 — HTTPS chưa chứng minh sẵn sàng

```properties
app.delivery.endpoint=https://gateway.example.test
```

**Hỏi:** URI đã parse và qua policy HTTPS, vậy hệ thống đã chắc chắn kết nối thành công?

**Đáp án:** Không. DNS, TLS, network, authorization và dịch vụ ngoài có thể lỗi. Cần kiểm tra vận hành riêng, có timeout và cách xử lý lỗi phù hợp.

### Bài 7 — default và missing

```java
@DefaultValue("8") int parallelism
```

**Hỏi:** Nếu production phải có giá trị `parallelism` do hạ tầng cấp rõ ràng, default 8 có thay thế yêu cầu đó không?

**Đáp án:** Không. Default giúp tạo giá trị khi thiếu, nhưng có thể che việc thiếu cấu hình bắt buộc. Cần xác định chính sách required ở môi trường tương ứng.

### Bài 8 — nested validation

Một `Retry` nested có `@Min(0)` nhưng lớp cha chỉ có `@Validated`, không có `@Valid` trên thuộc tính nested. Có thể mặc định validation con luôn chạy đầy đủ không?

**Đáp án:** Không. Cần đánh dấu cascade validation thích hợp, đồng thời bảo đảm nested object hiện diện nếu bắt buộc.

### Bài 9 — cấu hình chạy ở môi trường khác

`application.yaml` đặt `parallelism=4` nhưng đối số `--app.delivery.parallelism=100` được truyền khi chạy.

**Hỏi:** Nếu bean có `@Max(16)`, ứng dụng nên nhận kết quả gì?

**Đáp án:** Theo ưu tiên thông thường, đối số dòng lệnh cung cấp giá trị hiệu lực 100; binding sang `int` thành công nhưng validation có thể từ chối vì vượt 16. Phải xét nguồn cuối cùng, không chỉ đọc YAML.

### Bài 10 — ba kiểu kiểm thử

Bạn có unit test xác nhận `isEndpointPolicyValid()` trả `false` cho URL HTTP. Vậy đã đủ chứng minh Spring Boot đọc đúng biến môi trường chưa?

**Đáp án:** Chưa. Unit test xác nhận quy tắc Java; cần test binding/integration để chứng minh nguồn cấu hình và relaxed binding, và cần test vận hành riêng nếu yêu cầu kết nối thật.

## 27. Checklist thiết kế trước khi đưa một nhóm cấu hình vào ứng dụng

Đây là danh sách câu hỏi dành cho kỹ sư thiết kế, không phải kết quả tự động của Binder:

- [ ] Xác định nhóm thuộc tính và prefix canonical.
- [ ] Chọn kiểu Java phù hợp với mỗi giá trị.
- [ ] Phân loại giá trị bắt buộc và có thể thiếu.
- [ ] Chỉ định default khi default thực sự an toàn.
- [ ] Khai báo range, positive, not blank và size theo yêu cầu.
- [ ] Kiểm tra cấu trúc nested và collection bằng `@Valid`.
- [ ] Kiểm tra các ràng buộc liên trường.
- [ ] Xác định điều kiện đặc thù của profile và tính năng bật/tắt.
- [ ] Xác định ranh giới kiểm tra tĩnh và kiểm tra hệ thống bên ngoài.
- [ ] Kiểm thử dữ liệu không chuyển kiểu, dữ liệu chuyển kiểu nhưng không hợp lệ, và dữ liệu hợp lệ.
- [ ] Kiểm tra nguồn cấu hình ưu tiên cuối cùng khi triển khai.
- [ ] Không đưa thông tin bí mật vào log hoặc thông báo lỗi công khai.

Việc trả lời các câu hỏi này tạo thành **hợp đồng cấu hình** của ứng dụng. Một hợp đồng tốt giúp đội vận hành phân biệt lỗi do người cấu hình, lỗi do mã ứng dụng và lỗi do phụ thuộc ngoài.

## 28. Tổng kết

Hãy ghi nhớ ba mệnh đề:

**Thứ nhất — Binding thành công:** Spring Boot tìm được giá trị phù hợp từ các nguồn, nhận tên thuộc tính và chuyển chúng sang kiểu Java theo khả năng Binder. Nó không tự hiểu mọi điều kiện nghiệp vụ.

**Thứ hai — Validation thành công:** Những constraint mà ứng dụng **đã khai báo và đã kích hoạt** được thỏa mãn. Kết quả này đáng giá hơn binding đơn thuần, nhưng không chứng minh những ràng buộc chưa khai báo cũng đúng.

**Thứ ba — Vận hành thành công:** Hệ thống sử dụng cấu hình trong bối cảnh thực tế, với dịch vụ ngoài, dữ liệu, quyền truy cập, tài nguyên và SLA. Đây là mức xác nhận khác, thường cần kiểm thử tích hợp, readiness và giám sát.

```text
“Đúng kiểu”
    không đồng nghĩa
“Đúng quy tắc”
    không đồng nghĩa
“Dùng được trong môi trường thật”
```

Với Spring Boot 3.3, thực hành phù hợp là dùng `@ConfigurationProperties` cho cấu hình có cấu trúc, khai báo validation bằng `@Validated` và Jakarta Bean Validation, bổ sung quy tắc liên trường nếu cần, rồi tách riêng kiểm tra phụ thuộc vận hành. **Không nên coi việc bean được tạo thành công là bằng chứng rằng cấu hình đáp ứng đầy đủ yêu cầu nghiệp vụ.**

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — **Externalized Configuration**, các phần *Type-safe Configuration Properties*, *Properties Conversion*, *@ConfigurationProperties Validation*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 Reference — **Actuator Endpoints**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Jakarta Validation specification — Bean Validation constraints và cascade validation: https://jakarta.ee/specifications/bean-validation/
