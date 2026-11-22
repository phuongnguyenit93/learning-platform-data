# Ràng buộc chuỗi, số, địa chỉ và giá trị bắt buộc

## 1. Vì sao cấu hình cần được kiểm tra hợp lệ?

Trong Spring Boot, dữ liệu cấu hình có thể đến từ `application.yml`, `application.properties`, tài liệu theo profile, biến môi trường, Java system properties, đối số dòng lệnh hoặc nguồn Config Data bên ngoài. Spring Boot có thể **liên kết** các giá trị này vào một đối tượng Java bằng `@ConfigurationProperties`, nhưng việc chuyển dữ liệu sang kiểu Java thành công **chưa bảo đảm giá trị phù hợp với quy định của ứng dụng**.

Ví dụ, xét cấu hình:

```yaml
delivery:
  sender-name: "Order Service"
  sender-email: ""
  callback-uri: "http://example.invalid/callback"
  max-attempts: -4
  retry-ratio: 1.8
```

Các giá trị trên đều có thể được đọc như chuỗi, URI, số nguyên hoặc số thập phân. Tuy nhiên, ứng dụng có thể yêu cầu:

- Tên người gửi không được thiếu hoặc chỉ chứa khoảng trắng.
- Email người gửi phải có dạng email hợp lệ.
- Địa chỉ callback phải là một URI HTTPS có hostname.
- Số lần thử phải nằm trong khoảng từ 1 đến 20.
- Hệ số retry phải nằm trong khoảng từ 0 đến 1.

Nếu không kiểm tra, ứng dụng có thể khởi động rồi mới gặp lỗi gửi thông báo, định tuyến sai hoặc thực hiện một số lần thử ngoài dự kiến.

**Bean Validation kết hợp với `@ConfigurationProperties`** giúp phát hiện những cấu hình không phù hợp ngay trong quá trình khởi động Spring context. Mục tiêu không chỉ là “đọc được cấu hình” mà còn là “chỉ tạo bean cấu hình khi dữ liệu đáp ứng hợp đồng đã công bố”.

## 2. Phân biệt bốn giai đoạn xử lý cấu hình

Một lỗi liên quan tới cấu hình có thể xảy ra ở các tầng khác nhau:

```text
Tệp YAML / Properties / environment / CLI
                     |
                     v
       Spring Environment và Config Data
                     |
          chọn giá trị có hiệu lực
                     |
                     v
       ConfigurationProperties Binder
                     |
          khớp tên khóa / prefix
                     |
                     v
              Type conversion
                     |
          "5" -> int; "3s" -> Duration
                     |
                     v
              Bean Validation
                     |
          maxAttempts >= 1?
          email hợp lệ?
          URI có đúng yêu cầu?
                     |
                +----+----+
                |         |
               Đúng      Sai
                |         |
                v         v
          Tạo bean     Dừng khởi tạo,
          hợp lệ       thông báo lỗi cấu hình
```

Bốn khái niệm quan trọng:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Chọn nguồn | Giá trị nào có hiệu lực? | CLI ghi đè YAML |
| Binding tên | Khóa nào ứng với thành phần Java? | `max-attempts` ↔ `maxAttempts` |
| Chuyển đổi kiểu | Chuỗi có thể đổi sang kiểu đích không? | `"4"` → `int 4` |
| Validation | Giá trị đúng kiểu có đáp ứng quy tắc không? | `4` nằm trong khoảng `1..20` |

Ví dụ `max-attempts=many` không thể chuyển thành số nguyên là một **lỗi chuyển đổi kiểu**. Ví dụ `max-attempts=-4` chuyển thành `int` được nhưng vi phạm `@Min(1)` là một **lỗi validation**.

Hai loại lỗi có thể dẫn đến việc khởi động thất bại, nhưng nguyên nhân và cách sửa khác nhau.

## 3. Chuẩn bị thư viện Bean Validation

Các ví dụ sử dụng **Spring Boot 3.x**, Java 17 trở lên và Jakarta Validation. Với Spring Boot 3.x, những constraint phổ biến được import từ package `jakarta.validation.constraints`.

Nếu dự án chưa có thư viện validation phù hợp, thêm starter:

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

**Gradle (Groovy DSL):**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Starter thông thường mang theo một Jakarta Bean Validation provider, phổ biến là Hibernate Validator, cùng các thành phần cần thiết cho việc thực thi constraint.

Nếu chỉ thêm annotation của Jakarta Validation API mà không có provider thực thi, việc gắn `@NotBlank`, `@Min`... **không có nghĩa** các ràng buộc đã chắc chắn được thực thi trong mọi cấu hình ứng dụng.

Một số dự án Spring Boot 2.x cũ dùng `javax.validation.*`. Không nên sao chép nguyên import này sang Spring Boot 3.x mà bỏ qua thay đổi từ Java EE sang Jakarta EE.

## 4. Bật validation cho @ConfigurationProperties

Xem record cấu hình đơn giản:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) @Max(20) int maxAttempts) {
}
```

Từng phần có vai trò riêng:

- `@ConfigurationProperties(prefix = "delivery")`: chỉ định nhóm khóa đầu vào mà binder liên kết.
- `@Validated`: yêu cầu cơ chế validation được áp dụng cho bean cấu hình khi Spring Boot bind nó.
- `@NotBlank`: ràng buộc chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng.
- `@Min(1)`: yêu cầu giá trị số ít nhất là 1.
- `@Max(20)`: yêu cầu giá trị số không vượt quá 20.

Tệp `application.yml`:

```yaml
delivery:
  sender-name: "Order Service"
  max-attempts: 4
```

Khi bean cấu hình được đăng ký đúng cách, binder chuyển hai thuộc tính thành tham số constructor của record, rồi validation áp dụng những điều kiện khai báo.

Nếu đổi `max-attempts` thành `-2`, dữ liệu số vẫn chuyển đổi được nhưng không thỏa `@Min(1)`. Quá trình khởi tạo bean có thể thất bại với báo cáo lỗi liên kết cấu hình/validation.

**Lưu ý:** gắn annotation trên một lớp mà Spring không đăng ký thành bean `@ConfigurationProperties` không tự khiến việc kiểm tra diễn ra.

## 5. Đăng ký bean cấu hình trước khi mong đợi validation

Với record `DeliveryProperties` dùng constructor binding, một cách thông dụng là đặt `@ConfigurationPropertiesScan` trên lớp ứng dụng.

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Hãy đặt `DeliveryProperties` cùng package hoặc package con được quét.

Nếu muốn đăng ký tường minh, có thể chọn:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Hai ví dụ trên là **hai phương án thay thế**, không phải hai lớp khởi động cùng tồn tại trong một dự án.

Đối với constructor-bound configuration properties trong Spring Boot 3.x, không nên gắn `@Component` lên record chỉ để “được scan”, vì việc đăng ký component thông thường khác cơ chế đăng ký bean cấu hình dùng constructor binding.

## 6. Các ràng buộc cho chuỗi

Chuỗi cấu hình thường là tên hiển thị, tên tenant, mã vùng, đường dẫn logic, tên queue hoặc identifier.

Có ba nhóm constraint rất thường gặp:

| Constraint | Ý nghĩa cơ bản | Đối tượng áp dụng phổ biến |
| --- | --- | --- |
| `@NotNull` | Không được `null` | Nhiều kiểu tham chiếu |
| `@NotEmpty` | Không được null hoặc rỗng | `String`, collection, map, array |
| `@NotBlank` | Chuỗi không null, không rỗng hoặc chỉ chứa khoảng trắng | `CharSequence` |
| `@Size(min, max)` | Độ dài chuỗi hoặc kích thước collection nằm trong giới hạn | `String`, collection... |
| `@Pattern(regexp = "...")` | Chuỗi phải khớp biểu thức chính quy | `CharSequence` |

Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record IdentificationProperties(
        @NotBlank
        @Size(max = 80)
        String displayName,

        @NotBlank
        @Pattern(regexp = "^[A-Z]{2}-[0-9]{4}$")
        String locationCode) {
}
```

Các annotation này chỉ có tác dụng validation khi đối tượng được đưa vào quy trình kiểm tra thích hợp. Đoạn record trên minh họa constraint; để binding thực tế, đặt nó trong lớp `@ConfigurationProperties` đã được đăng ký và có `@Validated` như các ví dụ chính.

Ví dụ giá trị:

```yaml
identification:
  display-name: "Payment Gateway"
  location-code: "VN-0024"
```

Với `@Pattern(regexp = "^[A-Z]{2}-[0-9]{4}$")`, những mã như `VN-0024` phù hợp, còn `vn-0024` hoặc `VN-24` không phù hợp.

**Không nhầm validation với chuẩn hóa dữ liệu.** Constraint `@Pattern` không tự biến `vn-0024` thành `VN-0024`. Nếu hệ thống muốn chấp nhận chữ thường và chuẩn hóa, hãy thiết kế chuyển đổi riêng hoặc quy tắc đầu vào nhất quán.

## 7. Khác nhau giữa @NotNull, @NotEmpty và @NotBlank

Ba constraint này dễ bị xem là tương đương, nhưng khác nhau đáng kể.

Giả sử kiểm tra một giá trị kiểu `String`:

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `null` | Không đạt | Không đạt | Không đạt |
| `""` | Đạt | Không đạt | Không đạt |
| `"   "` | Đạt | Đạt | Không đạt |
| `"abc"` | Đạt | Đạt | Đạt |

Vì vậy:

- Nếu chỉ yêu cầu một đối tượng tồn tại, dùng `@NotNull`.
- Nếu muốn chuỗi có ít nhất một ký tự, `@NotEmpty` có thể đủ nhưng **không loại bỏ chuỗi toàn khoảng trắng**.
- Nếu muốn một tên/nhãn/email không trống về ý nghĩa, `@NotBlank` thường phù hợp hơn.

Ví dụ:

```java
@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @NotBlank String name) {
}
```

Các cấu hình không hợp lệ theo constraint này:

```yaml
service:
  name: ""
```

Hoặc:

```yaml
service:
  name: "   "
```

**Chi tiết quan trọng:** việc đặt giá trị mặc định trong `@DefaultValue` hoặc trong YAML không thay thế nhu cầu validation. Một giá trị mặc định vô nghĩa như chuỗi rỗng vẫn có thể vi phạm `@NotBlank`.

## 8. Giới hạn độ dài với @Size

Có những cấu hình cần giới hạn độ dài:

- Tên service không dài quá 80 ký tự.
- Mã định danh dài từ 3 đến 16 ký tự.
- Danh sách người nhận có từ 1 đến 10 phần tử.

Ví dụ:

```java
@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotBlank
        @Size(min = 3, max = 16)
        String regionCode) {
}
```

Với:

```properties
routing.region-code=VN
```

chuỗi có hai ký tự nên không đạt `@Size(min = 3)`.

Với:

```properties
routing.region-code=VN-SG
```

độ dài thỏa giới hạn.

**Lưu ý:** `@Size` không phải constraint dành cho giá trị số. Nếu muốn bảo đảm `retry-count` từ 1 đến 20, dùng `@Min` và `@Max` thay vì `@Size`.

Một giá trị chuỗi không tồn tại có thể được xử lý theo cơ chế mặc định hoặc null; nếu trường là bắt buộc, kết hợp `@Size` với `@NotBlank` hoặc constraint null phù hợp, bởi `@Size` tự nó không thay thế việc cấm null.

## 9. Ràng buộc số nguyên bằng @Min và @Max

Nhiều thông số vận hành là số nguyên: số luồng, số kết nối, số lần retry, số bản ghi tối đa, cổng mạng.

Ví dụ:

```yaml
worker:
  min-threads: 2
  max-threads: 16
  max-attempts: 4
```

Record:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int minThreads,
        @Min(1) @Max(256) int maxThreads,
        @Min(1) @Max(20) int maxAttempts) {
}
```

Nếu người vận hành khai báo:

```yaml
worker:
  min-threads: 0
  max-threads: 500
  max-attempts: -3
```

thì các số vẫn có thể chuyển thành `int`, nhưng đều vi phạm ràng buộc tương ứng.

Giới hạn được khai báo gần mô hình cấu hình, giúp những người đọc lớp Java biết hợp đồng đầu vào ngay lập tức.

### 9.1. @Positive và @PositiveOrZero

Hai constraint khác hữu ích:

```java
@Positive int threadCount;
@PositiveOrZero int backlogSize;
```

- `@Positive`: lớn hơn 0.
- `@PositiveOrZero`: lớn hơn hoặc bằng 0.

Tương tự có `@Negative` và `@NegativeOrZero` cho những tình huống phù hợp.

Với ràng buộc “số lần thử từ 1 đến 20”, `@Min(1) @Max(20)` diễn đạt rõ hơn việc chỉ dùng `@Positive`.

### 9.2. Primitive có thể che giấu giá trị bị thiếu

Xét:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Nếu không có `worker.max-threads`, một `int` nguyên thủy có thể nhận giá trị mặc định `0` trong quá trình tạo đối tượng. Nó không biểu diễn được trạng thái null.

Đặt `@NotNull` lên `int` không giúp kiểm tra thiếu như khi dùng kiểu tham chiếu, bởi `int` không thể là null.

Nếu muốn buộc phải khai báo một giá trị số ngay cả khi số 0 có thể là giá trị hợp lệ, cân nhắc:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Integer maxThreads) {
}
```

Với `Integer`, thiếu giá trị có thể được biểu diễn bằng null để `@NotNull` phát hiện. Nếu nghiệp vụ đòi hỏi dương, có thể thêm `@Min(1)`.

## 10. Số thập phân, tỷ lệ và BigDecimal

Các tỷ lệ, ngưỡng hoặc hệ số thường cần một phạm vi như `0..1`.

Ví dụ:

```yaml
fraud:
  risk-threshold: 0.75
```

Nên dùng `BigDecimal` nếu muốn xử lý chính xác giá trị thập phân phục vụ tính toán nghiệp vụ.

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "fraud")
public record FraudProperties(
        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal riskThreshold) {
}
```

Các tình huống:

| `risk-threshold` | Kết quả mong đợi |
| --- | --- |
| `0.0` | Hợp lệ |
| `0.75` | Hợp lệ |
| `1.0` | Hợp lệ |
| `-0.1` | Không hợp lệ |
| `1.5` | Không hợp lệ |
| Thiếu | Không hợp lệ vì `@NotNull` |

`@DecimalMin` và `@DecimalMax` nhận giá trị giới hạn dưới dạng chuỗi để biểu diễn chính xác. Có thể sử dụng tùy chọn `inclusive = false` khi cần giới hạn mở, ví dụ điều kiện lớn hơn 0 thay vì lớn hơn hoặc bằng 0.

Đừng dùng `@Min(0) @Max(1)` trên một `double` hoặc `float` theo giả định mọi provider đều kiểm tra đúng các giá trị thực. Với số thập phân, `@DecimalMin` và `@DecimalMax` cùng kiểu `BigDecimal` thường dễ hiểu và phù hợp hơn.

## 11. Ràng buộc địa chỉ email bằng @Email

Địa chỉ email là ví dụ điển hình của một chuỗi có yêu cầu định dạng riêng.

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record MailProperties(
        @NotBlank @Email String fromAddress) {
}
```

Với dữ liệu:

```yaml
mail:
  from-address: "ops@example.invalid"
```

Một bean `@ConfigurationProperties(prefix = "mail")` có thể liên kết `fromAddress` rồi áp dụng constraint.

Các trạng thái cần phân biệt:

- `""`: `@NotBlank` không chấp nhận.
- `"   "`: `@NotBlank` không chấp nhận.
- `"not-an-email"`: `@Email` có thể từ chối vì không đúng dạng email.
- `"ops@example.invalid"`: có dạng email để minh họa nhưng **không bảo đảm mailbox tồn tại**.

**`@Email` kiểm tra cú pháp theo quy tắc của Bean Validation provider, không kiểm chứng tài khoản email có hoạt động, domain có MX record hay người dùng có quyền sở hữu địa chỉ.** Việc xác minh địa chỉ thật cần quy trình riêng, không thuộc giai đoạn binding.

Ngoài ra, một số constraint như `@Email` xem null là hợp lệ theo quy ước Bean Validation; khi địa chỉ là bắt buộc, hãy kết hợp `@NotBlank` hoặc `@NotNull` thay vì dùng `@Email` đơn lẻ.

## 12. Ràng buộc địa chỉ URL, URI và callback endpoint

Trong Java, các địa chỉ mạng thường nên có kiểu `URI` thay vì được truyền qua nhiều lớp dưới dạng `String`.

Ví dụ:

```yaml
webhook:
  callback-uri: "https://hooks.example.invalid/events"
```

Record:

```java
import java.net.URI;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(
        @NotNull URI callbackUri) {
}
```

Spring Boot có thể chuyển một chuỗi URI hợp lệ về mặt cú pháp thành `java.net.URI`.

Nhưng một URI **không nhất thiết** là URL HTTPS tuyệt đối. Ví dụ những giá trị như `file:/tmp/example` hoặc `/relative/path` có thể là các URI hợp lệ về mặt cú pháp, nhưng không phù hợp nếu ứng dụng bắt buộc callback qua HTTPS.

Cần kiểm tra thêm hợp đồng nghiệp vụ:

- `callbackUri` không được null.
- Scheme phải là `https`.
- Địa chỉ phải có hostname.
- Nếu nghiệp vụ yêu cầu, port và path phải thỏa giới hạn cụ thể.

### 12.1. Kiểm tra một URI HTTPS trong record

Có thể dùng compact constructor của record để bảo vệ bất biến:

```java
package com.example.configdemo;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(URI callbackUri) {

    public WebhookProperties {
        if (callbackUri == null
                || !"https".equalsIgnoreCase(callbackUri.getScheme())
                || callbackUri.getHost() == null) {
            throw new IllegalArgumentException(
                    "webhook.callback-uri phải là URI HTTPS có hostname");
        }
    }
}
```

Khi Spring Boot constructor-bind record này, constructor kiểm tra giá trị đã được chuyển sang `URI`. Nếu không đạt, việc tạo đối tượng thất bại và lỗi được phản ánh trong quá trình khởi tạo.

Cách kiểm tra qua constructor là một **phương án bổ sung** bên cạnh Jakarta Bean Validation; nó không phải một constraint annotation chuẩn.

Trong hệ thống thực tế, kiểm tra `https` và hostname vẫn chưa đủ để bảo đảm an toàn kết nối: nếu endpoint đến từ nguồn không đáng tin, cần cân nhắc SSRF, redirect, allowlist host, DNS và chính sách mạng. Kiểm tra cấu hình không thay thế các biện pháp bảo mật khi thực hiện HTTP request.

### 12.2. @Pattern cho chuỗi URL có đủ không?

Có thể viết:

```java
@Pattern(regexp = "^https://.+")
String callbackUrl;
```

nhưng biểu thức này chỉ chứng minh chuỗi bắt đầu bằng một tiền tố, không xác nhận toàn bộ tính đúng đắn của URI, hostname, port hoặc yêu cầu bảo mật.

Với địa chỉ phục vụ kết nối, ưu tiên **chuyển kiểu sang URI** và xác thực các thành phần có ý nghĩa. Chỉ dùng regex đơn giản nếu yêu cầu thật sự chỉ là quy ước văn bản đơn giản.

### 12.3. Địa chỉ IP và hostname

Một cấu hình có thể chứa `server-host` hoặc một địa chỉ IP nội bộ.

- `@NotBlank` chỉ bảo đảm chuỗi có nội dung.
- `@Pattern` có thể kiểm soát một dạng tên ký tự, nhưng regex tự viết để xác nhận mọi địa chỉ IPv4/IPv6 thường rất dễ thiếu trường hợp.
- Việc phân giải DNS và kiểm tra một host có thể kết nối hay không là một thao tác khác với validation cú pháp.

Đối với dữ liệu mạng, hãy xác định rõ nhu cầu: tên miền, URI tuyệt đối, IP literal hay hostname nội bộ. Chọn kiểu, validator hoặc thư viện phù hợp, tránh dùng một regex chung cho tất cả.

## 13. Ràng buộc giá trị bắt buộc

Trong một hệ thống, có những khóa không có mặc định an toàn: địa chỉ hệ thống thanh toán, mã tenant, email gửi thông báo, tên bucket lưu trữ, thông tin xác thực.

Ví dụ:

```yaml
payment:
  provider-id: "gateway-a"
  callback-uri: "https://pay.example.invalid/callback"
```

Khai báo:

```java
import java.net.URI;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        @NotBlank String providerId,
        @NotNull URI callbackUri) {
}
```

Nếu thiếu `provider-id`, giá trị `String` có thể trở thành null khi bind; `@NotBlank` giúp phát hiện.

Nếu thiếu `callback-uri`, `@NotNull` giúp phát hiện trường hợp không có đối tượng URI.

**Bắt buộc không có nghĩa là chỉ kiểm tra khóa có xuất hiện trong file hay không.** Điều cần kiểm tra là giá trị hiệu lực cuối cùng đáp ứng yêu cầu. Một thuộc tính có thể đến từ biến môi trường hoặc CLI thay vì YAML, và vẫn là đầu vào hợp lệ.

Đối với mật khẩu hoặc token, không nên in giá trị bí mật trong các thông báo chẩn đoán tùy chỉnh. Bean Validation chỉ là một phần của việc bảo vệ cấu hình nhạy cảm.

## 14. Giá trị mặc định và ràng buộc bắt buộc

Spring Boot hỗ trợ `@DefaultValue` cho constructor binding. Chẳng hạn:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "job")
public record JobProperties(
        @NotBlank String queueName,
        @DefaultValue("3") @Min(1) int maxAttempts) {
}
```

Nếu `job.max-attempts` không có trong cấu hình, binder có thể dùng `3`. Ràng buộc `@Min(1)` vẫn có ý nghĩa vì những nguồn khác có thể cung cấp `0` hoặc giá trị âm.

Nếu `job.queue-name` bắt buộc và không có giá trị mặc định, `@NotBlank` khiến ứng dụng từ chối khi thiếu hoặc rỗng.

Nên phân loại cấu hình:

1. **Bắt buộc phải do người triển khai cung cấp:** `queueName`, một endpoint cụ thể, định danh tenant.
2. **Có mặc định hợp lý:** số retry, batch size, một số timeout.
3. **Tùy chọn đúng nghĩa:** một số thuộc tính có thể null hoặc không được khai báo mà ứng dụng vẫn hoạt động.

Không nên thêm mặc định giả cho những thuộc tính bắt buộc chỉ để ứng dụng khởi động; ví dụ `payment.api-key=placeholder` có thể khiến lỗi cấu hình bị phát hiện muộn hơn và khó hiểu hơn.

### 14.1. Thiếu và rỗng là hai tình huống khác nhau

Với `String`, ba tình huống:

```properties
# Không khai báo key
```

```properties
job.queue-name=
```

```properties
job.queue-name=   
```

có thể đi qua những cơ chế chuyển đổi/binding khác nhau, nhưng nếu cuối cùng nhận null, chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng thì `@NotBlank` đều giúp phát hiện.

Đối với `Integer`, `@NotNull` giúp phát hiện thiếu; đối với `int` nguyên thủy, cần xét giá trị 0 mặc định hoặc ràng buộc số phù hợp.

## 15. Ví dụ hoàn chỉnh: một nhóm cấu hình nhiều loại dữ liệu

Bây giờ tạo một ví dụ tổng hợp gồm chuỗi, email, URI, số nguyên, số thập phân và đối tượng lồng nhau.

### 15.1. application.yml

```yaml
delivery:
  sender-name: "Order Service"
  sender-email: "ops@example.invalid"
  callback-uri: "https://hooks.example.invalid/delivery"
  max-attempts: 4
  retry-ratio: 0.50
  recipients:
    - billing
    - operations
  proxy:
    host: "proxy.internal"
    port: 8080
```

### 15.2. Record dùng Bean Validation

```java
package com.example.configdemo;

import java.math.BigDecimal;
import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank @Size(max = 80) String senderName,
        @NotBlank @Email String senderEmail,
        @NotNull URI callbackUri,
        @Min(1) @Max(20) int maxAttempts,
        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal retryRatio,
        @NotEmpty
        List<@NotBlank String> recipients,
        @NotNull @Valid Proxy proxy) {

    public record Proxy(
            @NotBlank String host,
            @Min(1) @Max(65535) int port) {
    }
}
```

Các điểm nổi bật:

- `senderName` phải có nội dung và không quá 80 ký tự.
- `senderEmail` phải có nội dung và đúng dạng email theo provider.
- `callbackUri` phải tồn tại và có thể liên kết thành `URI`.
- `maxAttempts` phải từ 1 đến 20.
- `retryRatio` phải tồn tại và nằm trong `[0,1]`.
- `recipients` không được rỗng; mỗi phần tử chuỗi có ràng buộc `@NotBlank`.
- `proxy` phải tồn tại, còn các trường bên trong được kiểm tra nhờ `@Valid`.

Dấu `@Valid` trên đối tượng lồng nhau rất quan trọng: nó yêu cầu Bean Validation kiểm tra tiếp các constraint bên trong `Proxy`. `@NotNull` bổ sung yêu cầu chính đối tượng lồng nhau không được thiếu.

**Lưu ý:** `@NotNull URI callbackUri` chưa kiểm tra scheme HTTPS; có thể bổ sung một constraint riêng hoặc logic constructor như phần trước nếu đó là yêu cầu nghiệp vụ.

### 15.3. Đăng ký và sử dụng

Trong lớp ứng dụng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Với imports:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
```

Một service sử dụng cấu hình:

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties properties;

    public DeliveryService(DeliveryProperties properties) {
        this.properties = properties;
    }

    public boolean canRetry(int currentAttempt) {
        return currentAttempt < properties.maxAttempts();
    }

    public String senderName() {
        return properties.senderName();
    }
}
```

Bean cấu hình đã được chuyển đổi kiểu và kiểm tra hợp lệ trước khi service dùng các giá trị của nó trong mô hình khởi tạo Spring thông thường.

Không cần gọi Bean Validation thủ công bên trong mỗi lần xử lý yêu cầu chỉ để kiểm tra lại cùng dữ liệu cấu hình bất biến.

## 16. Validation trên đối tượng cấu hình lồng nhau

Cấu hình lồng nhau rất thường gặp:

```yaml
gateway:
  endpoint: "https://gateway.example.invalid"
  retry:
    attempts: 3
    delay: 2s
```

Java:

```java
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull String endpoint,
        @NotNull @Valid Retry retry) {

    public record Retry(
            @Min(1) int attempts,
            @NotNull Duration delay) {
    }
}
```

Khi `gateway.retry.attempts=0`, constraint trên record lồng nhau cần được kiểm tra. `@Valid` yêu cầu validation đi sâu vào `Retry`.

Nếu toàn bộ nhánh `gateway.retry` không tồn tại, binder có thể tạo record cha với `retry=null`. Lúc này:

- `@Valid` riêng lẻ không buộc một giá trị null phải xuất hiện.
- `@NotNull` trên `retry` là cách yêu cầu nhánh đó tồn tại.

Đây là một nhầm lẫn rất phổ biến: có validation ở lớp con nhưng **không yêu cầu và không cascade validation từ đối tượng cha**.

Với những nhánh tùy chọn, có thể bỏ `@NotNull` nhưng giữ `@Valid` để kiểm tra khi nhánh tồn tại. Cách thiết kế đúng phụ thuộc vào ý nghĩa nghiệp vụ.

## 17. Ràng buộc danh sách và phần tử

Một collection có thể thỏa ràng buộc kích thước, nhưng các phần tử bên trong vẫn không hợp lệ.

Ví dụ:

```yaml
access:
  allowed-groups:
    - billing
    - ""
    - audit
```

Record:

```java
import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "access")
public record AccessProperties(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank String> allowedGroups) {
}
```

Ràng buộc:

- `@NotEmpty`: danh sách phải tồn tại và có ít nhất một phần tử.
- `@Size(max = 10)`: danh sách không vượt quá 10 phần tử.
- `List<@NotBlank String>`: mỗi giá trị chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng.

Sự kết hợp này kiểm tra cả **hình dạng tập hợp** lẫn **giá trị từng phần tử**.

Nếu phần tử là object phức tạp, có thể dùng cascade validation `List<@Valid Entry>` để kiểm tra các constraint của từng object.

Các quy tắc như “không trùng nhóm” hoặc “phần tử phải có trong danh mục quyền được phép” không mặc nhiên được giải quyết bởi `@NotBlank` và `@Size`; cần constraint hoặc logic nghiệp vụ bổ sung.

## 18. Chuyển đổi kiểu khác với validation địa chỉ và thời lượng

Xem:

```yaml
gateway:
  timeout: -5s
  endpoint: "/relative/path"
```

Java:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.time.Duration timeout,
        java.net.URI endpoint) {
}
```

Bộ chuyển đổi kiểu của Spring Boot có thể tạo được `Duration` âm và URI tương đối; chúng **đúng kiểu** nhưng có thể sai mục đích sử dụng.

Nếu nghiệp vụ yêu cầu:

- Timeout phải lớn hơn 0.
- Endpoint phải dùng HTTPS và có host.

thì hãy kiểm tra rõ ràng các điều kiện này, chẳng hạn trong compact constructor:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.time.Duration timeout,
        java.net.URI endpoint) {

    public GatewayProperties {
        if (timeout == null
                || timeout.isZero()
                || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "gateway.timeout phải là thời lượng dương");
        }
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null) {
            throw new IllegalArgumentException(
                    "gateway.endpoint phải là URI HTTPS có host");
        }
    }
}
```

Cách làm bằng constructor bảo vệ **bất biến của Java object**, kể cả khi record được tạo thủ công trong unit test. Nếu muốn các lỗi được báo dưới dạng Bean Validation constraint, có thể viết custom constraint hoặc getter dùng `@AssertTrue` theo cấu trúc phù hợp.

Lựa chọn nào cũng cần có thông báo dễ hiểu và không tiết lộ dữ liệu bí mật.

## 19. Kiểm tra điều kiện liên quan nhiều thuộc tính

Một số quy tắc không thể biểu diễn chỉ bằng `@Min` hoặc `@NotBlank` trên một field:

- `minThreads` phải nhỏ hơn hoặc bằng `maxThreads`.
- Nếu bật proxy, `proxyHost` phải được khai báo.
- Nếu bật OAuth, client ID và secret đều phải có.
- Nếu retry được bật, delay phải dương.

Ví dụ:

```java
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        @Min(1) int minThreads,
        @Min(1) int maxThreads) {

    public PoolProperties {
        if (minThreads > maxThreads) {
            throw new IllegalArgumentException(
                    "pool.min-threads phải <= pool.max-threads");
        }
    }
}
```

Ràng buộc trên từng field ngăn các số nhỏ hơn 1, còn constructor ngăn một cặp giá trị không nhất quán.

Trong dự án lớn, có thể tạo **custom Bean Validation constraint ở cấp class** để diễn đạt quan hệ giữa nhiều thuộc tính. Điều đó có thể phù hợp khi muốn lỗi cấu hình được xử lý thống nhất cùng các constraint Jakarta Validation khác.

Không nên tự ép một quan hệ đa trường thành regex phức tạp trên một trường đơn; cách làm sẽ khó đọc và dễ sai.

## 20. Phân biệt giá trị null, mặc định primitive và giá trị rỗng

Xét ba khai báo:

```java
int maxAttempts;
Integer maxAttemptsBoxed;
String senderName;
```

Với `int`, không có giá trị null; nếu thiếu thuộc tính, binding có thể tạo giá trị mặc định 0 trong một số trường hợp.

Với `Integer`, có thể có null; `@NotNull` là công cụ thích hợp khi muốn bắt buộc phải có giá trị:

```java
@NotNull
@Min(1)
Integer maxAttempts;
```

Với `String`, cần quyết định muốn ngăn null, chuỗi rỗng hay chuỗi toàn khoảng trắng:

```java
@NotBlank
String senderName;
```

**Nếu cần phân biệt “không khai báo giá trị” với “đã khai báo 0”, hãy dùng kiểu tham chiếu `Integer` và ràng buộc null phù hợp**, thay vì chỉ nhìn một `int` primitive.

Nhưng nếu `0` vốn không hợp lệ, `@Min(1)` trên `int` cũng có thể khiến cấu hình thiếu giá trị bị từ chối khi giá trị cuối là 0. Thiết kế này thể hiện yêu cầu miền số hơn là trạng thái có/không có khóa.

## 21. Những constraint cho phép null khi đứng một mình

Một nguyên tắc của Bean Validation: **nhiều constraint chuyên biệt chấp nhận null**, bởi trách nhiệm phát hiện thiếu giá trị thường được giao cho `@NotNull`, `@NotBlank` hoặc `@NotEmpty`.

Ví dụ:

```java
@Email String contactEmail;
@Size(max = 30) String label;
@Pattern(regexp = "[A-Z]+") String code;
@Min(1) Integer retryCount;
```

Trong những trường hợp này, chỉ dùng các constraint chuyên biệt không nhất thiết làm null trở thành lỗi.

Muốn yêu cầu bắt buộc, kết hợp:

```java
@NotBlank @Email String contactEmail;
@NotBlank @Size(max = 30) String label;
@NotBlank @Pattern(regexp = "[A-Z]+") String code;
@NotNull @Min(1) Integer retryCount;
```

Hãy coi “bắt buộc phải có” và “nếu có thì phải đúng dạng” là hai điều kiện khác nhau. Cách tách này giúp cấu hình có các giá trị tùy chọn được biểu diễn rõ ràng.

## 22. Lỗi sai tên khóa không phải lỗi validation của giá trị đã bind

Giả sử bean mong đợi:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(int maxAttempts) {
}
```

Nhưng YAML:

```yaml
delivery:
  max-attempst: 4
```

Đây là lỗi **tên khóa**. Binder không thể tự hiểu `max-attempst` là `max-attempts`.

Nếu trường là `int`, giá trị cuối của `maxAttempts` có thể là 0. `@Min(1)` có thể gián tiếp phát hiện giá trị không hợp lệ, nhưng lỗi được báo là “giá trị không đạt ràng buộc”, chứ không nhất thiết nêu đúng tên khóa viết sai.

Spring Boot có tùy chọn:

```java
@ConfigurationProperties(
        prefix = "delivery",
        ignoreUnknownFields = false)
```

cho phép binder không bỏ qua một số khóa chưa được liên kết trong phạm vi bean.

Tuy nhiên, **`ignoreUnknownFields = false` không phải công cụ quét toàn bộ thuộc tính của mọi nguồn hoặc mọi prefix**. Nếu người vận hành viết nhầm cả prefix `delivery` thành `delivary`, bean mang prefix `delivery` có thể không nhìn thấy nhóm mới đó. Validation giá trị bắt buộc và kiểm thử cấu hình vẫn cần thiết.

Một thiết kế hợp lý kết hợp:

- Prefix rõ ràng, dùng kebab-case.
- Kiểm tra các khóa lạ trong nhóm cần nghiêm ngặt.
- Validation cho thuộc tính bắt buộc.
- Test khởi tạo cấu hình đúng và sai có chủ đích.

## 23. Lỗi chuyển đổi kiểu và lỗi ràng buộc số

Đây là hai tình huống khác nhau.

**Trường hợp A — sai kiểu:**

```yaml
delivery:
  max-attempts: many
```

Bean yêu cầu:

```java
int maxAttempts
```

Chuỗi `many` không thể được chuyển thành `int` theo quy tắc thông thường. Lỗi có thể xuất hiện trong tầng conversion/binding trước khi validation của giá trị số thực sự có cơ hội đánh giá.

**Trường hợp B — đúng kiểu, sai ràng buộc:**

```yaml
delivery:
  max-attempts: -2
```

Giá trị `-2` có thể chuyển thành `int`, sau đó `@Min(1)` từ chối.

Các giải pháp khác nhau:

- Với A: sửa kiểu/dạng đầu vào, hoặc cung cấp converter phù hợp nếu kiểu miền riêng thực sự cần thiết.
- Với B: sửa giá trị theo hợp đồng hoặc điều chỉnh ràng buộc nếu yêu cầu nghiệp vụ đã thay đổi.

Không khắc phục lỗi chuyển đổi bằng cách bật `ignoreInvalidFields = true` cho cấu hình quan trọng chỉ để ứng dụng vượt qua lỗi khởi động, vì việc bỏ qua giá trị không hợp lệ có thể khiến ứng dụng hoạt động với trạng thái ngoài ý muốn.

## 24. Spring Boot báo lỗi validation như thế nào?

Khi Spring Boot bind một bean `@ConfigurationProperties` được validation và dữ liệu không hợp lệ, quá trình tạo ApplicationContext thường thất bại. Log có thể nêu:

- Prefix hoặc tên bean cấu hình đang được liên kết.
- Khóa cấu hình có vấn đề.
- Giá trị hoặc nguyên nhân sai.
- Constraint bị vi phạm và thông báo tương ứng.
- Thông tin về PropertySource, khi có thể xác định.

Ví dụ cấu hình:

```yaml
delivery:
  sender-name: "   "
  max-attempts: -1
```

Bean:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) int maxAttempts) {
}
```

Một lần khởi động có thể báo lỗi với ý nghĩa:

```text
delivery.sender-name: must not be blank
delivery.max-attempts: must be greater than or equal to 1
```

Đây là **mô tả ý nghĩa lỗi**, không phải cam kết nguyên văn log của mọi phiên bản Spring Boot hay mọi Bean Validation provider. Ngoại lệ bên ngoài có thể là `ConfigurationPropertiesBindException` hoặc một lỗi khởi tạo bean chứa nguyên nhân validation bên trong.

Nếu lỗi chỉ xuất hiện khi bật profile production, cần kiểm tra nguồn giá trị của profile đó thay vì sửa một tệp YAML mặc định không được dùng trong lần chạy.

## 25. Giá trị hiệu lực quyết định kết quả validation

Giả sử `application.yml` chứa:

```yaml
delivery:
  max-attempts: 3
```

và bean yêu cầu:

```java
@Min(1) @Max(20) int maxAttempts
```

Chạy thông thường:

```bash
java -jar app.jar
```

giá trị 3 hợp lệ nếu không có nguồn cấu hình khác ghi đè.

Nhưng nếu chạy:

```bash
java -jar app.jar --delivery.max-attempts=-10
```

đối số CLI có ưu tiên cao hơn Config Data trong cấu hình Spring Boot thông thường. Binder nhận `-10` làm giá trị có hiệu lực, rồi validation từ chối.

Điều đó cho thấy **một tệp application.yml đúng chưa bảo đảm toàn bộ lần chạy đúng**: biến môi trường, Java system properties, đối số dòng lệnh và cấu hình bên ngoài đều có thể thay đổi giá trị được bind.

Khi chẩn đoán, hãy hỏi “giá trị nào được Spring dùng trong lần chạy này?” thay vì chỉ đọc một tệp bất kỳ.

## 26. Đặt thông báo lỗi dễ hiểu

Jakarta Validation cho phép thêm thuộc tính `message`:

```java
@Min(value = 1, message = "Số lần thử phải ít nhất là 1")
@Max(value = 20, message = "Số lần thử không vượt quá 20")
int maxAttempts;
```

Với chuỗi:

```java
@NotBlank(message = "Tên người gửi không được trống")
String senderName;
```

Thông báo nên nói rõ:

1. Thuộc tính có ý nghĩa gì.
2. Vì sao giá trị không hợp lệ.
3. Giới hạn hoặc dạng giá trị được phép.

Ví dụ thông báo “Số lần thử phải từ 1 đến 20” hữu ích hơn “invalid property”.

Không nên đưa **giá trị token, mật khẩu hoặc khóa truy cập** vào thông báo lỗi tùy chỉnh. Nếu một framework tự log giá trị thuộc tính, cần kiểm soát mức log và cách quản lý secret ở môi trường thật.

## 27. Kiểm thử validation bằng ApplicationContextRunner

Kiểm thử cấu hình ngay ở mức ApplicationContext nhỏ giúp phát hiện lỗi trước khi chạy cả ứng dụng.

Giả sử record:

```java
package com.example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotBlank String senderName,
        @Min(1) @Max(20) int maxAttempts) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class DeliveryPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "delivery.sender-name=Order Service",
                "delivery.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.maxAttempts()).isEqualTo(4);
            assertThat(properties.senderName()).isEqualTo("Order Service");
        });
    }

    @Test
    void rejectsBlankSender() {
        runner.withPropertyValues(
                "delivery.sender-name=   ",
                "delivery.max-attempts=4"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsOutOfRangeAttempts() {
        runner.withPropertyValues(
                "delivery.sender-name=Order Service",
                "delivery.max-attempts=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfig {
    }
}
```

Những bài test này kiểm tra:

- Dữ liệu hợp lệ tạo được bean.
- Chuỗi chỉ gồm khoảng trắng bị từ chối.
- Số nhỏ hơn giới hạn bị từ chối.

Cần bảo đảm test có Bean Validation provider phù hợp; nếu thiếu dependency validation, các trường hợp được kỳ vọng thất bại có thể không được kiểm tra như mong muốn.

`ApplicationContextRunner` tập trung vào việc bind và tạo context, thường gọn hơn `@SpringBootTest` khi chỉ muốn kiểm tra một lớp cấu hình.

### 27.1. Kiểm thử URI HTTPS

Với record có kiểm tra URI trong constructor:

```java
@ConfigurationProperties(prefix = "webhook")
public record WebhookProperties(URI callbackUri) {

    public WebhookProperties {
        if (callbackUri == null
                || !"https".equalsIgnoreCase(callbackUri.getScheme())
                || callbackUri.getHost() == null) {
            throw new IllegalArgumentException(
                    "Callback phải là URI HTTPS có host");
        }
    }
}
```

Tạo context với `webhook.callback-uri=https://hooks.example.invalid/events` sẽ phù hợp với điều kiện trong constructor. Còn `webhook.callback-uri=http://hooks.example.invalid/events` sẽ không đạt yêu cầu HTTPS.

Với constructor validation, lỗi có thể xuất hiện khi tạo đối tượng trước khi các constraint Jakarta khác được đánh giá. Hãy xác định rõ bạn muốn kiểm tra bằng **Bean Validation** hay **bất biến của constructor**, rồi viết test cho cơ chế ấy.

## 28. Kiểm thử cấu hình theo nhiều profile

Giả sử:

```yaml
# application.yml
delivery:
  max-attempts: 3
```

và:

```yaml
# application-prod.yml
delivery:
  max-attempts: 50
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @Min(1) @Max(20) int maxAttempts) {
}
```

Nếu chỉ chạy test với profile `dev`, ứng dụng có thể hợp lệ. Khi bật `prod`, giá trị `50` vi phạm `@Max(20)`.

Một test ứng dụng đầy đủ có thể kích hoạt profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Test
    void contextStartsWithProductionConfiguration() {
        // Nếu cấu hình production không hợp lệ, context có thể
        // thất bại ngay trước khi phương thức test được chạy.
    }
}
```

Nếu mục đích là xác minh cấu hình sai **phải làm context thất bại** và kiểm tra nguyên nhân, `ApplicationContextRunner` với những property phù hợp thường dễ kiểm soát hơn một `@SpringBootTest` cố tình gây lỗi lúc khởi tạo.

Bài học: validation phải được kiểm chứng với những profile và nguồn cấu hình thực sự tham gia triển khai, không chỉ với giá trị trong tệp chung.

## 29. Khi nào nên dùng custom Bean Validation constraint?

Những annotation có sẵn không thể diễn đạt mọi quy tắc, đặc biệt với:

- Địa chỉ HTTPS thuộc một allowlist cụ thể.
- Mã tenant theo danh mục nghiệp vụ.
- Quan hệ giữa `minThreads` và `maxThreads`.
- Tính nhất quán giữa một nhóm tùy chọn.
- Quy tắc về tên queue, bucket hoặc region do hệ thống nội bộ quy định.

Có thể tạo một annotation custom, ví dụ `@HttpsEndpoint`, và một `ConstraintValidator` dùng URI parsing để kiểm tra scheme/host.

Khung khái niệm:

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

import java.net.URI;

public class HttpsEndpointValidator
        implements ConstraintValidator<HttpsEndpoint, URI> {

    @Override
    public boolean isValid(
            URI value, ConstraintValidatorContext context) {
        if (value == null) {
            return true; // @NotNull chịu trách nhiệm kiểm tra thiếu.
        }
        return "https".equalsIgnoreCase(value.getScheme())
                && value.getHost() != null;
    }
}
```

Để dùng trong dự án, phải định nghĩa annotation `@HttpsEndpoint` với `@Constraint(validatedBy = HttpsEndpointValidator.class)`, cùng `@Target`, `@Retention(RUNTIME)` và các thành phần `message`, `groups`, `payload` theo hợp đồng Jakarta Validation.

Ví dụ trên minh họa **logic của validator**, chưa phải một bộ annotation hoàn chỉnh để copy nguyên và biên dịch độc lập.

Chỉ tạo custom constraint khi quy tắc có giá trị tái sử dụng hoặc cần tích hợp thống nhất với validation. Nếu quy tắc chỉ là bất biến đơn giản của một record nhỏ, kiểm tra trong constructor có thể là lựa chọn dễ đọc hơn.

## 30. Cấu hình bất biến và validation

Constructor binding với Java record hoặc class dùng trường `final` là lựa chọn thường gặp cho cấu hình.

Ví dụ:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int threadCount,
        @NotBlank String queueName) {
}
```

Các giá trị được giải quyết, chuyển đổi kiểu và dùng để tạo đối tượng. Validation bảo đảm record được chấp nhận chỉ khi giá trị đáp ứng constraint.

Cần phân biệt:

- **Bất biến:** không sửa các component của record sau khi tạo.
- **Validation:** dữ liệu phải đáp ứng quy định của ứng dụng.
- **Bắt buộc:** khóa phải cung cấp giá trị khác null/rỗng theo yêu cầu.
- **Thứ tự ưu tiên nguồn:** quyết định giá trị nào binder nhìn thấy.

Record bất biến không tự kiểm tra `queueName` không rỗng. Constraint `@NotBlank` thực hiện phần đó.

Ngược lại, một JavaBean mutable vẫn có thể được validation nếu nó là bean cấu hình được Spring Boot bind đúng cơ chế. Bất biến và validation không bắt buộc phải đi cùng, dù kết hợp chúng thường cho mô hình dễ hiểu.

## 31. Những nhầm lẫn thường gặp

### 31.1. Cho rằng @NotNull chặn chuỗi rỗng

`@NotNull` chấp nhận `""`. Nếu cần một chuỗi có nội dung, dùng `@NotBlank`.

### 31.2. Dùng @Size cho số nguyên

`@Size(min=1, max=20) int maxAttempts` không phải cách hợp lệ để giới hạn số nguyên. Dùng `@Min(1) @Max(20)`.

### 31.3. Dùng @Email để xác minh email tồn tại

`@Email` kiểm tra định dạng theo provider; nó không thực hiện xác minh tài khoản, domain hay quyền sở hữu địa chỉ.

### 31.4. Dùng @NotNull URI để chắc chắn địa chỉ HTTPS

`@NotNull` chỉ chặn null. Một URI có thể dùng `http`, `file` hoặc là URI tương đối. Cần thêm ràng buộc scheme và hostname khi nghiệp vụ yêu cầu.

### 31.5. Bỏ @Validated rồi mặc định mọi constraint sẽ chạy

Đối với validation của `@ConfigurationProperties`, `@Validated` và sự hiện diện của provider là phần cấu hình quan trọng. Đừng dựa vào việc chỉ có annotation `@NotBlank` trên một POJO tự tạo bằng `new`.

### 31.6. Quên @Valid cho đối tượng lồng nhau

Nếu `GatewayProperties` chứa `Retry` với constraint bên trong, nhưng không cascade validation, những constraint bên trong có thể không được đánh giá như mong muốn. Thêm `@Valid` ở điểm lồng nhau phù hợp.

### 31.7. Nghĩ @Valid khiến đối tượng lồng nhau bắt buộc tồn tại

`@Valid` không tự thay thế `@NotNull`. Nếu nhánh lồng nhau phải có mặt, dùng cả hai theo yêu cầu.

### 31.8. Nhầm lỗi sai kiểu với sai miền giá trị

`retry-count=many` là vấn đề chuyển đổi sang `int`. `retry-count=-3` là số nguyên đúng kiểu nhưng có thể vi phạm `@Min`.

### 31.9. Dùng primitive và @NotNull để phát hiện thiếu

`@NotNull int maxAttempts` không có tác dụng biểu đạt “thiếu” theo cách `@NotNull Integer maxAttempts` có thể làm. `int` không nhận null.

### 31.10. Chỉ kiểm tra application.yml mà bỏ qua nguồn khác

Validation áp dụng trên giá trị được bind từ các nguồn có hiệu lực. Biến môi trường hoặc CLI có thể ghi đè giá trị mặc định hợp lệ bằng một giá trị không hợp lệ.

### 31.11. Coi kiểm tra regex là xác minh an ninh

Một URL bắt đầu với `https://` vẫn có thể trỏ tới nơi không được phép. Kiểm soát truy cập mạng, allowlist, DNS và các quy tắc tránh SSRF là trách nhiệm ngoài việc kiểm tra định dạng chuỗi.

### 31.12. Log toàn bộ bean cấu hình để chẩn đoán

Một record chứa token hoặc mật khẩu có thể tự sinh `toString()` hiển thị nội dung nhạy cảm. Không log toàn bộ bean nếu chứa secret.

## 32. Quy trình chẩn đoán khi ứng dụng không khởi động vì cấu hình

Khi gặp lỗi liên kết hoặc validation, có thể xử lý tuần tự:

1. **Xác định prefix của bean** `@ConfigurationProperties` đang lỗi.
2. **Xác định nguồn cung cấp giá trị có hiệu lực:** CLI, biến môi trường, profile-specific Config Data, YAML/Properties, import.
3. **Đọc khóa chính xác:** kiểm tra lỗi chính tả, dấu gạch ngang, camelCase và sự khác nhau giữa tiền tố.
4. **Xem kiểu Java đích:** `int`, `Integer`, `BigDecimal`, `URI`, `Duration`, `String`...
5. **Phân biệt conversion và validation:** giá trị không chuyển được hay đã chuyển được nhưng vi phạm `@Min`, `@NotBlank`...?
6. **Xem constraint bắt buộc:** null, chuỗi rỗng, nhánh lồng nhau không tồn tại.
7. **Xác nhận cơ chế validation:** `@Validated`, provider và `@Valid` cho object lồng nhau.
8. **Chạy test binding phạm vi nhỏ:** giá trị hợp lệ, giá trị bị thiếu, giá trị sai định dạng và giá trị ngoài miền.
9. **Sửa nguồn gây lỗi và khởi động lại:** tránh tắt constraint để vượt qua lỗi mà chưa hiểu hậu quả.
10. **Tránh làm lộ secret:** kiểm tra sự hiện diện hoặc metadata thay vì in giá trị nhạy cảm.

Một lỗi cấu hình càng được phát hiện gần bước khởi động, phạm vi ảnh hưởng càng dễ kiểm soát so với lỗi chỉ bộc lộ sau khi hệ thống đã xử lý dữ liệu thật.

## 33. Bài tập A: chuỗi rỗng, khoảng trắng và quá dài

Record:

```java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank @Size(max = 12) String displayName) {
}
```

Hãy dự đoán các giá trị:

| `app.display-name` | Kết quả |
| --- | --- |
| `"Inventory"` | Hợp lệ |
| `""` | Không hợp lệ vì `@NotBlank` |
| `"   "` | Không hợp lệ vì `@NotBlank` |
| `"Inventory Service Platform"` | Không hợp lệ vì vượt `@Size(max=12)` |

Câu hỏi bổ sung: nếu chỉ dùng `@NotNull`, trường hợp `""` có bị từ chối không?

Đáp án: không. `@NotNull` chỉ kiểm tra null.

## 34. Bài tập B: ràng buộc số

Record:

```java
@Validated
@ConfigurationProperties(prefix = "pool")
public record PoolProperties(
        @Min(1) @Max(64) int maxConnections) {
}
```

Các cấu hình:

```properties
pool.max-connections=8
```

```properties
pool.max-connections=0
```

```properties
pool.max-connections=100
```

```properties
pool.max-connections=many
```

Đáp án:

- `8`: đúng kiểu, nằm trong giới hạn.
- `0`: đúng kiểu nhưng vi phạm `@Min(1)`.
- `100`: đúng kiểu nhưng vi phạm `@Max(64)`.
- `many`: không chuyển thành `int` theo quy tắc thông thường, lỗi conversion/binding.

## 35. Bài tập C: email bắt buộc

Cấu hình:

```yaml
mail:
  from-address: ""
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        @NotBlank @Email String fromAddress) {
}
```

**Câu hỏi:** điều gì khiến cấu hình bị từ chối?

`@NotBlank` từ chối chuỗi rỗng. Nếu một địa chỉ có nội dung nhưng sai cú pháp email, `@Email` có thể từ chối theo quy tắc của provider.

Nếu bỏ `@NotBlank` và chỉ giữ `@Email`, không nên mặc định null/rỗng luôn bị từ chối theo cùng cách.

## 36. Bài tập D: URI đúng kiểu nhưng sai yêu cầu

Record:

```java
@ConfigurationProperties(prefix = "hook")
public record HookProperties(java.net.URI callback) {
}
```

Cấu hình:

```yaml
hook:
  callback: "http://hooks.example.invalid/events"
```

**Câu hỏi:** vì sao chỉ dùng `URI` chưa chắc ngăn địa chỉ này, dù hệ thống yêu cầu HTTPS?

Vì chuỗi trên là một URI hợp lệ về cú pháp. Cần bổ sung quy tắc scheme phải bằng `https`, hostname khác null và những điều kiện bảo mật liên quan.

## 37. Bài tập E: cấu hình lồng nhau bị thiếu

Record:

```java
@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull @Valid Retry retry) {

    public record Retry(@Min(1) int attempts) {
    }
}
```

Cấu hình:

```yaml
gateway:
  enabled: true
```

**Câu hỏi:** nếu binder không tạo `retry` vì nhánh không tồn tại, constraint nào từ chối?

`@NotNull` trên `retry`. `@Valid` có nhiệm vụ yêu cầu kiểm tra các constraint **bên trong** khi đối tượng `Retry` tồn tại.

## 38. Bài tập F: đối số dòng lệnh ghi đè dữ liệu hợp lệ

Tệp `application.yml`:

```yaml
worker:
  thread-count: 8
```

Record:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) @Max(32) int threadCount) {
}
```

Chạy:

```bash
java -jar app.jar --worker.thread-count=64
```

**Câu hỏi:** liệu ứng dụng chắc chắn hợp lệ vì YAML ghi `8` không?

Không. Với thứ tự ưu tiên Spring Boot thông thường, CLI có thể ghi đè YAML bằng `64`, và `@Max(32)` từ chối giá trị có hiệu lực đó.

## 39. Ghi nhớ

- `@ConfigurationProperties` giúp liên kết cấu hình có cấu trúc; `@Validated` phối hợp Bean Validation để kiểm tra dữ liệu ngay khi tạo bean.
- Trong Spring Boot 3.x, dùng các constraint từ `jakarta.validation.constraints` cùng một Bean Validation provider, thường qua `spring-boot-starter-validation`.
- Với **chuỗi**, phân biệt `@NotNull`, `@NotEmpty`, `@NotBlank`; dùng `@Size` và `@Pattern` để kiểm soát độ dài, định dạng.
- Với **số**, dùng `@Min`, `@Max`, `@Positive` hoặc `@DecimalMin`/`@DecimalMax` tùy kiểu và yêu cầu.
- Với **email**, `@Email` kiểm tra cú pháp chứ không xác minh mailbox thực; kết hợp `@NotBlank` nếu bắt buộc.
- Với **URI/địa chỉ**, chuyển thành kiểu Java phù hợp và bổ sung quy tắc scheme, hostname, port hoặc allowlist theo nghiệp vụ. `@NotNull URI` không bảo đảm HTTPS.
- Với **giá trị bắt buộc**, dùng `@NotBlank`, `@NotNull`, `@NotEmpty` phù hợp; lưu ý kiểu primitive không có null.
- Với **đối tượng lồng nhau**, `@Valid` yêu cầu cascade validation; `@NotNull` yêu cầu đối tượng thực sự tồn tại.
- **Binding, conversion và validation là ba trách nhiệm khác nhau.** Đúng kiểu chưa chắc đúng nghiệp vụ; tên khóa sai cũng không tự được constraint sửa lại.
- Giá trị có hiệu lực có thể đến từ profile, biến môi trường hoặc CLI; validation cần được kiểm thử trên các tình huống triển khai thực.
- Viết test `ApplicationContextRunner` cho các trường hợp hợp lệ, rỗng, thiếu, sai định dạng, ngoài giới hạn và cấu hình lồng nhau để phát hiện sớm lỗi cấu hình.
