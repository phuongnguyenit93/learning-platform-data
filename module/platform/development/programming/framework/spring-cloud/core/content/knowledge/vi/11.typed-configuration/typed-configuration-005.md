# Validation cấu hình và phát hiện giá trị không hợp lệ

Trong một ứng dụng Spring Cloud, cấu hình có thể đến từ file trong JAR, file bên ngoài, biến môi trường, command line hoặc Config Server. Việc một giá trị được nạp thành công vào `Environment` chưa có nghĩa giá trị đó hợp lệ về mặt nghiệp vụ. Ví dụ, `inventory.timeout=0ms` có thể chuyển đổi thành `Duration` hợp lệ nhưng không phù hợp với chính sách gọi dịch vụ; `inventory.max-attempts=-2` là số nguyên nhưng không phải số lần thử hợp lệ.

**Validation cấu hình** giúp phát hiện những lỗi này ngay tại ranh giới khởi động hoặc khi cấu hình được bind, trước khi chúng gây lỗi khó chẩn đoán trong quá trình xử lý request. Với **SPRING_CLOUD_CORE**, đây là năng lực quan trọng khi sử dụng `@ConfigurationProperties`, Spring Cloud Config, discovery, service registry, giao tiếp dịch vụ và refresh scope.

Bài học thuộc chương **Cấu hình kiểu dữ liệu**, tập trung vào cách kiểm tra cấu hình có kiểu, cách phân biệt lỗi chuyển đổi với lỗi validation, cách kiểm thử và cách vận hành khi cấu hình từ xa không hợp lệ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa lỗi thiếu property, lỗi chuyển đổi kiểu và lỗi validation.
- Sử dụng Bean Validation với `@ConfigurationProperties`.
- Chọn constraint phù hợp như `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Positive`, `@Pattern` và `@Valid`.
- Kiểm tra cấu hình lồng nhau, phần tử collection và quan hệ giữa nhiều thuộc tính.
- Hiểu vai trò của `@Validated`, `@ConfigurationPropertiesScan` và `@EnableConfigurationProperties`.
- Thiết kế giá trị mặc định, trường bắt buộc và trường tùy chọn rõ ràng.
- Phát hiện typo hoặc property không được bind bằng các tùy chọn phù hợp.
- Kiểm thử cả cấu hình hợp lệ và không hợp lệ.
- Xử lý cấu hình sai từ Config Server hoặc nguồn bên ngoài theo chính sách fail-fast.
- Xem xét validation khi cấu hình được refresh trong ứng dụng đang chạy.

## 2. Vì sao cần validation cấu hình?

Giả sử `checkout-service` gọi `inventory-service` với ba thuộc tính:

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
```

Nếu không kiểm tra, các giá trị sau vẫn có thể được nạp hoặc chuyển đổi:

```yaml
inventory:
  base-url: ""
  timeout: 0ms
  max-attempts: -3
```

Một số giá trị có thể gây lỗi khi gọi HTTP; một số khác khiến retry vô nghĩa hoặc làm ứng dụng hoạt động sai mà không có lỗi lúc khởi động.

Validation cấu hình có ba lợi ích:

1. **Phát hiện sớm:** lỗi được báo khi bind cấu hình thay vì đợi đến lúc request thực tế sử dụng giá trị.
2. **Thông báo rõ:** lỗi chỉ ra property và điều kiện bị vi phạm.
3. **Bảo vệ hợp đồng cấu hình:** mỗi service có thể định nghĩa giới hạn và quan hệ giữa các thuộc tính mà nó chấp nhận.

Validation không thay thế việc kiểm tra kết nối tới dịch vụ bên ngoài. Một URI đúng định dạng vẫn có thể trỏ tới host không tồn tại; validation kiểm tra hình dạng và quy tắc dữ liệu, còn health check/integration test kiểm tra khả năng kết nối thực tế.

## 3. Ba loại lỗi cần phân biệt

| Loại lỗi | Ví dụ | Thời điểm phát hiện | Cách xử lý |
| --- | --- | --- | --- |
| Thiếu property bắt buộc | Không có `inventory.base-url` | Khi bind hoặc validation | Dùng constraint như `@NotNull`/`@NotBlank`, không giả định có default |
| Lỗi chuyển đổi kiểu | `inventory.timeout=abc` trong khi field là `Duration` | Trong quá trình binding/conversion | Kiểm tra định dạng và kiểu dữ liệu |
| Lỗi validation ngữ nghĩa | `inventory.timeout=0ms`, `max-attempts=-1` | Sau khi giá trị đã được bind | Dùng Bean Validation hoặc validator nghiệp vụ |

### 3.1. Lỗi chuyển đổi không phải lỗi validation

Ví dụ:

```yaml
inventory:
  timeout: abc
  max-attempts: three
```

Nếu thuộc tính được khai báo là `Duration` và `int`, Binder không thể chuyển đổi các chuỗi này sang kiểu đích. Quá trình binding thất bại trước khi Bean Validation có thể kiểm tra các điều kiện như timeout phải dương.

Ngược lại:

```yaml
inventory:
  timeout: 0ms
  max-attempts: 0
```

Hai giá trị có thể được chuyển đổi thành kiểu `Duration` và `int`, nhưng vi phạm quy tắc nghiệp vụ. Đây là trường hợp validation có ích.

### 3.2. Thiếu property và giá trị mặc định

Với kiểu tham chiếu như `URI`, `Duration` hoặc `String`, property không được cung cấp có thể trở thành `null` nếu không có default. Với kiểu nguyên thủy như `int` hoặc `boolean`, giá trị Java mặc định lần lượt là `0` và `false`.

Điều này ảnh hưởng đến constraint:

- `@NotNull` phù hợp với kiểu tham chiếu.
- `@NotBlank` phù hợp với chuỗi bắt buộc có nội dung.
- `@Min(1)` có thể phát hiện `int` bằng `0` nếu giá trị bị bỏ quên.
- Nếu `false` là một giá trị hợp lệ, không dùng validation để coi nó là “thiếu”.

Hãy quyết định rõ thuộc tính nào bắt buộc, thuộc tính nào có default và thuộc tính nào được phép vắng mặt.

## 4. Bean Validation cho @ConfigurationProperties

Spring Boot hỗ trợ tích hợp Bean Validation vào quá trình bind `@ConfigurationProperties`. Với Spring Boot 3 trở lên, API validation sử dụng namespace `jakarta.validation`.

Để sử dụng, thêm implementation Bean Validation vào classpath. Trong dự án Spring Boot, starter thường dùng là:

**Maven**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

**Gradle**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Để phiên bản starter do Spring Boot BOM quản lý, không tự gán một version độc lập nếu dự án đã dùng dependency management của Boot.

### 4.1. Constraint thường dùng

| Annotation | Điều kiện | Ví dụ phù hợp |
| --- | --- | --- |
| `@NotNull` | Giá trị không được là `null` | URI, Duration, object cấu hình |
| `@NotBlank` | Chuỗi không null, không rỗng và có ký tự không phải khoảng trắng | Tên service, username |
| `@NotEmpty` | Chuỗi/collection/map không null và không rỗng | Danh sách endpoint hoặc vùng được phép |
| `@Min(n)` | Số phải lớn hơn hoặc bằng `n` | Số lần thử tối thiểu |
| `@Max(n)` | Số phải nhỏ hơn hoặc bằng `n` | Giới hạn kết nối |
| `@Positive` | Số phải lớn hơn 0 | Port, số lượng, hệ số |
| `@PositiveOrZero` | Số phải lớn hơn hoặc bằng 0 | Số lần retry bổ sung |
| `@Pattern` | Chuỗi phải khớp regular expression | Mã vùng, tên profile nội bộ |
| `@Email` | Chuỗi có định dạng email theo validator | Email liên hệ |
| `@Valid` | Tiếp tục kiểm tra object lồng nhau | Nhóm cấu hình con |
| `@AssertTrue` | Biểu thức boolean phải đúng | Kiểm tra quan hệ nhiều trường |

Các constraint có ý nghĩa riêng. Ví dụ `@NotEmpty` không thay thế `@NotBlank`: chuỗi `"   "` không rỗng nhưng không có nội dung hữu ích.

### 4.2. Kích hoạt validation bằng @Validated

Ví dụ:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    @NotBlank
    private String serviceName;

    @Min(1)
    @Max(100)
    private int maxItems;

    // getters and setters
}
```

`@Validated` yêu cầu Spring thực hiện validation trên bean cấu hình. Các constraint mô tả hợp đồng của từng thuộc tính. Khi giá trị không đạt yêu cầu, quá trình tạo bean cấu hình thất bại và ứng dụng thường không khởi động thành công.

Để bean được đăng ký, có thể dùng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(CheckoutProperties.class)` trong một lớp cấu hình.

## 5. Ví dụ đầy đủ: cấu hình Inventory có kiểu dữ liệu

Một client gọi `inventory-service` cần URL, timeout, số lần thử, giới hạn retry và danh sách region được hỗ trợ.

### 5.1. Khai báo record bất biến

```java
package com.example.checkout.config;

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
@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) @Max(10) int maxAttempts,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@NotBlank String> allowedRegions) {

    @AssertTrue(message = "inventory.base-url must be an absolute HTTP(S) URI")
    public boolean isBaseUrlHttp() {
        if (baseUrl == null) {
            return true;
        }
        String scheme = baseUrl.getScheme();
        return baseUrl.isAbsolute()
                && baseUrl.getHost() != null
                && ("http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme));
    }

    @AssertTrue(message = "inventory.timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout == null || (!timeout.isNegative() && !timeout.isZero());
    }

    @AssertTrue(message = "inventory.retry.min-attempts must not exceed max-attempts")
    public boolean isRetryRangeValid() {
        return retry == null || retry.minAttempts() <= retry.maxAttempts();
    }

    public record Retry(
            @Min(0) int minAttempts,
            @Min(1) @Max(10) int maxAttempts) {
    }
}
```

Ví dụ dùng Java record để có object cấu hình bất biến. Với một constructor duy nhất của record, Spring Boot hỗ trợ constructor binding theo quy ước của các dòng hiện đại; không cần setter cho từng trường. Với class thông thường, có thể dùng constructor binding hoặc JavaBean binding tùy thiết kế.

Các constraint trong ví dụ có ý nghĩa:

- `baseUrl` phải có giá trị; phương thức `isBaseUrlHttp()` kiểm tra URI tuyệt đối và scheme HTTP/HTTPS.
- `timeout` phải có giá trị và lớn hơn 0.
- `maxAttempts` phải từ 1 đến 10.
- `retry` là object bắt buộc và `@Valid` kích hoạt validation cho các trường bên trong.
- `allowedRegions` không được rỗng; mỗi phần tử phải có nội dung.
- `isRetryRangeValid()` kiểm tra quan hệ giữa hai trường trong object con.

Các phương thức `@AssertTrue` trả về `true` khi object chưa có trường tham chiếu (để constraint `@NotNull` báo lỗi tương ứng), hoặc khi điều kiện ngữ nghĩa được đáp ứng. Cách này tránh tạo thêm lỗi phụ gây nhiễu khi một giá trị bắt buộc đang thiếu.

### 5.2. Bật scan cấu hình

```java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` tìm các lớp được đánh dấu `@ConfigurationProperties` trong phạm vi scan. Một lựa chọn khác là khai báo rõ:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
class InventoryConfiguration {
}
```

Không cần dùng cả hai cách cho cùng một bean cấu hình nếu chúng khiến bean được đăng ký trùng.

### 5.3. application.yaml hợp lệ

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
    - ap-southeast-2
```

Spring Boot chuyển đổi chuỗi `800ms` thành `Duration`, URI thành `java.net.URI`, bind danh sách và object lồng nhau. Sau khi bind, Bean Validation kiểm tra các điều kiện.

### 5.4. Các ví dụ cấu hình không hợp lệ

**Thiếu URL:**

```yaml
inventory:
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
```

`baseUrl` là `null`, vi phạm `@NotNull`.

**Timeout bằng 0:**

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 0ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
```

Giá trị chuyển đổi thành `Duration` thành công nhưng vi phạm `isTimeoutPositive()`.

**Khoảng retry không hợp lệ:**

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 5
    max-attempts: 2
  allowed-regions:
    - ap-southeast-1
```

Hai trường riêng lẻ có thể thỏa constraint số, nhưng quan hệ `minAttempts <= maxAttempts` không đúng. Đây là lý do cần kiểm tra cấp object hoặc class.

## 6. Validation cho cấu hình lồng nhau và collection

### 6.1. @Valid cần thiết cho object lồng nhau

Khai báo `@Valid` ở thuộc tính object để Bean Validation đi sâu vào các constraint của object con:

```java
public record Retry(
        @Min(0) int minAttempts,
        @Min(1) int maxAttempts) {
}

public record InventoryProperties(
        @NotNull @Valid Retry retry) {
}
```

Nếu thiếu `@Valid`, constraint đặt trên `Retry` có thể không được thực thi khi validation chỉ bắt đầu từ `InventoryProperties`. `@NotNull` và `@Valid` làm hai việc khác nhau: một annotation yêu cầu object tồn tại, annotation còn lại kích hoạt validation bên trong.

### 6.2. Validation phần tử collection

Bean Validation hỗ trợ constraint trên phần tử của collection:

```java
@NotEmpty
List<@NotBlank String> allowedRegions
```

Điều này kiểm tra cả collection lẫn từng phần tử:

```yaml
inventory:
  allowed-regions:
    - ap-southeast-1
    - ""
```

Collection không rỗng nhưng có phần tử rỗng, vì vậy validation vẫn thất bại. Nếu chỉ đặt `@NotEmpty` trên list, phần tử rỗng có thể không bị phát hiện.

### 6.3. Kiểm tra quan hệ giữa các trường

Một số quy tắc không thể mô tả bằng constraint đơn trường:

- `min-pool-size` không được lớn hơn `max-pool-size`.
- `connect-timeout` phải nhỏ hơn `read-timeout`.
- Nếu bật TLS thì truststore phải được khai báo.
- Nếu bật retry thì số lần thử phải lớn hơn 0.

Với quy tắc đơn giản, có thể dùng `@AssertTrue` trên method. Với quy tắc phức tạp, dùng custom class-level constraint (`@Constraint`) và `ConstraintValidator` để tái sử dụng, viết message rõ và kiểm thử riêng.

Không nên đặt mọi logic nghiệp vụ vào một phương thức `@AssertTrue` lớn. Khi quy tắc tăng lên, tách thành constraint có tên phản ánh đúng ý nghĩa để lỗi dễ đọc và dễ bảo trì.

## 7. Chọn giá trị mặc định và trường bắt buộc

Validation chỉ hữu ích khi hợp đồng cấu hình rõ ràng. Trước khi thêm annotation, cần quyết định property nào phải có và property nào được phép dùng default.

| Loại thuộc tính | Ví dụ | Cách thiết kế |
| --- | --- | --- |
| Bắt buộc | URL registry, tên tenant, credential reference | Không gán default giả; dùng `@NotNull`/`@NotBlank` |
| Có default an toàn | Timeout nội bộ, số lượng batch nhỏ | Khai báo default có chủ đích, vẫn kiểm tra giới hạn |
| Tùy chọn | Proxy URL, feature flag phụ | Cho phép `null` hoặc giá trị default phù hợp |
| Phụ thuộc thuộc tính khác | Truststore khi TLS bật | Kiểm tra bằng cross-field validation |

### 7.1. Default trong YAML

```yaml
inventory:
  timeout: 2s
  max-attempts: 3
```

Khi giá trị mặc định được khai báo trong file, mọi môi trường có thể dùng chung default và override từ nguồn ưu tiên cao hơn.

### 7.2. Default trong Java

Với JavaBean binding, có thể khởi tạo field:

```java
@ConfigurationProperties("checkout")
@Validated
public class CheckoutProperties {

    @Min(1)
    private int maxItems = 20;

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
```

Nếu property không có mặt, giá trị `20` được giữ. Nếu cấu hình ghi `0`, validation phát hiện lỗi.

Với constructor-bound record, có thể dùng cơ chế default value được Spring Boot hỗ trợ cho constructor parameter, hoặc cung cấp giá trị mặc định trong constructor/thiết kế cấu hình phù hợp với phiên bản Boot. Hãy kiểm tra đúng API của release train đang dùng thay vì sao chép annotation giữa các thế hệ.

### 7.3. Không che giấu cấu hình bắt buộc bằng default giả

Ví dụ không nên dùng:

```java
String configServer = environment.getProperty(
        "spring.cloud.config.uri", "http://localhost:8888");
```

cho một ứng dụng production mà Config Server là bắt buộc. Default `localhost` có thể làm ứng dụng khởi động với nguồn cấu hình sai. Khi property trọng yếu bị thiếu, fail-fast với thông báo rõ thường an toàn hơn.

## 8. Phát hiện typo và property không được bind

Một lỗi phổ biến là viết sai tên property:

```yaml
inventory:
  max-attemp: 3
```

Trong khi lớp cấu hình khai báo `maxAttempts`. Nếu unknown property bị bỏ qua, ứng dụng có thể giữ default `0` và chỉ phát hiện lỗi qua `@Min(1)`, hoặc tệ hơn là dùng một default không an toàn.

### 8.1. ignoreUnknownFields

`@ConfigurationProperties` có thuộc tính `ignoreUnknownFields`, mặc định là `true`. Khi đặt thành `false`, những property không ánh xạ được vào bean cấu hình có thể làm quá trình binding thất bại.

```java
@ConfigurationProperties(
        prefix = "inventory",
        ignoreUnknownFields = false)
@Validated
public record InventoryProperties(
        @NotNull URI baseUrl,
        @Min(1) int maxAttempts) {
}
```

Tùy chọn này hữu ích với nhóm cấu hình có schema chặt chẽ. Tuy nhiên, cần kiểm tra cấu trúc YAML và prefix để không coi những key được chủ đích dùng bởi một component khác là lỗi của bean này.

### 8.2. ignoreInvalidFields

`ignoreInvalidFields` mặc định là `false`. Nếu bật `true`, một số lỗi binding không hợp lệ có thể bị bỏ qua thay vì làm ứng dụng dừng.

Không nên bật tùy chọn này cho cấu hình trọng yếu chỉ để ứng dụng khởi động được. Một giá trị timeout sai định dạng hoặc số lần thử không chuyển đổi được thường nên làm startup thất bại, vì dùng giá trị mặc định ngoài dự kiến có thể gây hành vi không an toàn.

### 8.3. Unknown property và invalid property khác nhau

| Tình huống | Phân loại |
| --- | --- |
| `inventory.max-attemp` không có field tương ứng | Unknown property |
| `inventory.max-attempts=three` trong khi field là `int` | Invalid conversion |
| `inventory.max-attempts=0` với `@Min(1)` | Validation failure |
| `inventory.timeout` không được cung cấp với `@NotNull` | Missing/validation failure |

Không dùng một cờ duy nhất để giải quyết cả ba nhóm. Hãy xác định đúng loại lỗi từ thông báo Binder và validation.

## 9. Validation với cấu hình từ xa

Trong ứng dụng Spring Cloud, cấu hình có thể đến từ Spring Cloud Config, Consul Config hoặc nguồn riêng. Sau khi dữ liệu được nạp vào Environment và bind vào `@ConfigurationProperties`, validation vẫn áp dụng như với cấu hình local.

Ví dụ Config Server trả về:

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 0ms
  max-attempts: 3
```

Nếu `timeout` không hợp lệ, ứng dụng có thể thất bại khi khởi tạo bean cấu hình. Việc Config Server phản hồi thành công chỉ chứng minh nguồn đã trả dữ liệu; nó không chứng minh dữ liệu đáp ứng hợp đồng của service.

### 9.1. Optional import không bỏ qua validation

```yaml
spring:
  config:
    import: optional:configserver:http://config-server:8888
```

`optional:` điều chỉnh hành vi khi nguồn Config Server không thể được nạp theo cơ chế Config Data. Nếu nguồn được nạp thành công nhưng chứa giá trị không hợp lệ, validation của bean cấu hình vẫn có thể làm ứng dụng thất bại.

Đây là hai quyết định riêng:

- **Nguồn có sẵn không?** Quyết định bởi import, fail-fast và retry.
- **Dữ liệu có hợp lệ không?** Quyết định bởi binding, conversion và validation.

### 9.2. Hợp đồng cấu hình giữa các service

Nếu Config Server dùng chung repository cho nhiều service, cần phân tách prefix và profile rõ ràng:

```yaml
checkout:
  timeout: 2s

inventory:
  timeout: 800ms
```

Mỗi service chỉ bind phần cấu hình thuộc trách nhiệm của mình. Khi schema thay đổi, cần kiểm tra tất cả service tiêu thụ cấu hình đó; một property mới hoặc bị đổi kiểu có thể làm một phiên bản service cũ không còn bind được.

### 9.3. Triển khai fail-fast

Với cấu hình bắt buộc như URL dịch vụ, credential reference, timeout và chính sách retry, nên để startup thất bại khi dữ liệu không hợp lệ. Điều này giúp orchestration không đưa instance sai cấu hình vào trạng thái Ready.

Với cấu hình tùy chọn, hãy đặt default an toàn và mô tả rõ hành vi khi thiếu. Không nên dùng `optional:` hoặc `ignoreInvalidFields=true` như một cách che giấu lỗi schema.

## 10. Validation và refresh khi ứng dụng đang chạy

Validation thường được thực hiện khi `@ConfigurationProperties` được bind trong quá trình khởi tạo context. Khi cấu hình thay đổi sau startup, cần phân biệt:

1. Property source đã thay đổi trong `Environment`.
2. Bean cấu hình đã được bind lại hoặc target của refresh scope được tạo lại.
3. Validation đã được thực hiện trên object mới.
4. Các thành phần sử dụng cấu hình mới đã chuyển sang trạng thái hoạt động an toàn.

`@RefreshScope` không tự phát hiện thay đổi từ Config Server hoặc file bên ngoài. Cần một cơ chế refresh được hỗ trợ, chẳng hạn endpoint/event hoặc Spring Cloud Bus cho nhiều instance.

### 10.1. Khi refresh một bean cấu hình

Nếu một bean `@ConfigurationProperties` được quản lý theo cơ chế refresh/rebind, giá trị mới cần được bind và kiểm tra theo cấu hình validation. Nếu dùng `@RefreshScope`, target mới sẽ được tạo khi proxy cần truy cập sau khi scope bị invalidate; quá trình tạo target mới có thể thất bại nếu cấu hình mới không hợp lệ.

Không giả định rằng một refresh thất bại luôn tự động rollback toàn bộ Environment về phiên bản trước. Cần kiểm tra hành vi của release Spring Cloud, thiết kế quy trình triển khai và có phương án khôi phục nguồn cấu hình.

### 10.2. Cập nhật cấu hình nhiều replica

Trong cluster có nhiều instance:

- Một instance có thể nhận refresh trước instance khác.
- Một instance có thể bind thành công trong khi instance khác thất bại do profile hoặc nguồn cấu hình khác nhau.
- Nếu cấu hình mới không hợp lệ, readiness và metrics cần phản ánh trạng thái lỗi.
- Cần có quy trình rollback hoặc sửa nguồn cấu hình trước khi tiếp tục rollout.

Với các giá trị ảnh hưởng đến giao tiếp dịch vụ, chẳng hạn timeout, TLS, registry endpoint hoặc retry policy, nên kiểm thử bản cấu hình mới trên staging trước khi phát tán tới toàn bộ replica.

## 11. Kiểm thử validation

Một bộ test tốt cần bao gồm cấu hình hợp lệ, thiếu property, sai kiểu, sai giới hạn, object lồng nhau và quan hệ giữa các trường.

### 11.1. ApplicationContextRunner

`ApplicationContextRunner` cho phép khởi tạo một context nhỏ với property riêng cho từng test:

```java
class InventoryPropertiesTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(InventoryProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsValidProperties() {
        contextRunner
                .withPropertyValues(
                        "inventory.base-url=https://inventory.internal",
                        "inventory.timeout=800ms",
                        "inventory.max-attempts=3",
                        "inventory.retry.min-attempts=1",
                        "inventory.retry.max-attempts=4",
                        "inventory.allowed-regions[0]=ap-southeast-1")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    InventoryProperties properties =
                            context.getBean(InventoryProperties.class);
                    assertThat(properties.timeout())
                            .isEqualTo(Duration.ofMillis(800));
                    assertThat(properties.maxAttempts()).isEqualTo(3);
                });
    }
}
```

Test kiểm tra binding và validation mà không cần khởi động web server hay kết nối registry thật.

### 11.2. Cấu hình không hợp lệ phải làm context thất bại

```java
@Test
void rejectsZeroTimeout() {
    contextRunner
            .withPropertyValues(
                    "inventory.base-url=https://inventory.internal",
                    "inventory.timeout=0ms",
                    "inventory.max-attempts=3",
                    "inventory.retry.min-attempts=1",
                    "inventory.retry.max-attempts=4",
                    "inventory.allowed-regions[0]=ap-southeast-1")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("inventory.timeout");
            });
}
```

Thông báo lỗi cụ thể phụ thuộc phiên bản Spring Boot và validation provider. Trong test ổn định, nên kiểm tra rằng context thất bại và lỗi chứa property/constraint cần thiết, thay vì so sánh toàn bộ stack trace.

### 11.3. Kiểm thử lỗi chuyển đổi

```java
@Test
void rejectsInvalidDurationFormat() {
    contextRunner
            .withPropertyValues(
                    "inventory.base-url=https://inventory.internal",
                    "inventory.timeout=not-a-duration",
                    "inventory.max-attempts=3",
                    "inventory.retry.min-attempts=1",
                    "inventory.retry.max-attempts=4",
                    "inventory.allowed-regions[0]=ap-southeast-1")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("inventory.timeout");
            });
}
```

Test này xác minh lỗi conversion. Nó khác test timeout bằng `0ms`, vốn là lỗi validation sau khi conversion thành công.

### 11.4. Kiểm thử object lồng nhau

Đặt `inventory.retry.max-attempts=0` phải làm validation thất bại vì constraint `@Min(1)` trên object con. Test này giúp phát hiện việc quên `@Valid` ở thuộc tính `retry`.

Đặt `inventory.retry.min-attempts=5` và `inventory.retry.max-attempts=2` phải làm cross-field validation thất bại dù từng số riêng lẻ đều hợp lệ.

### 11.5. Kiểm thử validation độc lập

Nếu cần kiểm tra riêng constraint, có thể dùng Jakarta Validator:

```java
Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();

Set<ConstraintViolation<InventoryProperties>> violations =
        validator.validate(properties);

assertThat(violations).isNotEmpty();
```

Test độc lập cần tạo object đầu vào rõ ràng. Nó kiểm tra Bean Validation nhưng không kiểm tra Spring Boot Binder có chuyển đổi property từ YAML/environment đúng hay không; vì vậy vẫn cần test context cho đường binding thực tế.

## 12. Đọc và xử lý thông báo lỗi

Một lỗi validation thường cho biết:

- Bean cấu hình nào không tạo được.
- Property path nào vi phạm.
- Constraint hoặc message nào không đạt.
- Quá trình binding/validation thất bại trong giai đoạn khởi động.

Ví dụ thông báo minh họa:

```text
Binding to target InventoryProperties failed:
  Property: inventory.timeout
  Value: 0ms
  Reason: inventory.timeout must be greater than zero
```

Đây là dạng diễn giải, không phải định dạng log cố định của mọi phiên bản Boot. Lỗi thực tế có thể được bọc trong `ConfigurationPropertiesBindException`, `BindException` hoặc exception từ validation provider.

### 12.1. Phân tích theo tầng

| Tầng | Câu hỏi |
| --- | --- |
| Nguồn | Property đến từ file, biến môi trường hay Config Server? |
| Binding | Key có được ánh xạ vào field đúng không? |
| Conversion | Chuỗi có chuyển được sang URI, Duration, int hoặc DataSize không? |
| Validation | Giá trị có đáp ứng constraint không? |
| Khởi tạo | Bean cấu hình có được đăng ký và tạo đúng cách không? |
| Vận hành | Ứng dụng có dùng đúng profile và nguồn cấu hình cho replica này không? |

Không sửa lỗi validation bằng cách tắt validation ngay lập tức. Trước tiên, xác định property sai vì nguồn dữ liệu, tên key, conversion hay hợp đồng nghiệp vụ.

### 12.2. Actuator và quan sát cấu hình

Spring Boot Actuator có thể hỗ trợ chẩn đoán qua các endpoint như `configprops` và `env`, tùy dependency và cấu hình exposure. Chúng có thể cho biết cấu hình đã bind và nguồn property liên quan.

Các endpoint này có thể tiết lộ URL nội bộ, tên người dùng hoặc dữ liệu nhạy cảm nếu cấu hình che dữ liệu không phù hợp. Chỉ expose khi cần, bảo vệ bằng authentication/authorization và không đưa toàn bộ nội dung cấu hình vào log.

## 13. Validation tùy chỉnh

Các constraint chuẩn đáp ứng phần lớn nhu cầu. Khi cần quy tắc dùng lại ở nhiều lớp cấu hình, có thể tạo custom constraint.

Ví dụ về thiết kế:

1. Tạo annotation `@HttpEndpoint`.
2. Đánh dấu annotation bằng `@Constraint(validatedBy = HttpEndpointValidator.class)`.
3. Triển khai `ConstraintValidator<HttpEndpoint, URI>`.
4. Kiểm tra URI tuyệt đối, host và scheme được cho phép.
5. Trả message không chứa giá trị nhạy cảm.

Custom constraint phù hợp khi quy tắc có tên miền rõ ràng và được dùng ở nhiều nơi. Nếu chỉ có một điều kiện đơn giản, `@AssertTrue` hoặc constraint chuẩn thường dễ hiểu hơn.

### 13.1. Cross-field validator

Với quy tắc như `connectTimeout < readTimeout`, có thể tạo annotation ở cấp class:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = TimeoutRangeValidator.class)
public @interface ValidTimeoutRange {
    String message() default "connect-timeout must be less than read-timeout";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator đọc cả hai trường và tạo violation gắn vào property phù hợp. Khi viết custom validator, cần xử lý `null` có chủ đích để constraint `@NotNull` riêng chịu trách nhiệm cho giá trị bắt buộc bị thiếu.

Không nên viết một custom validator truy cập mạng để kiểm tra endpoint có reachable hay không. Validation cấu hình nên nhanh, xác định và không phụ thuộc dịch vụ ngoài; kiểm tra kết nối nên nằm trong health check hoặc integration test.

## 14. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ kiểm tra kiểu dữ liệu | `0ms` hoặc số âm vẫn có thể bind thành công | Bổ sung constraint nghiệp vụ |
| Dùng `@NotEmpty` cho chuỗi cần nội dung | Chuỗi chỉ có khoảng trắng vẫn được chấp nhận | Dùng `@NotBlank` |
| Quên `@Valid` ở object lồng nhau | Constraint của object con không được chạy từ bean cha | Thêm `@Valid` |
| Dùng primitive cho trường bắt buộc mà không có constraint phù hợp | `0` hoặc `false` có thể bị hiểu nhầm là default hợp lệ | Dùng `@Min`, `@AssertTrue` hoặc kiểu tham chiếu với `@NotNull` |
| Bật `ignoreInvalidFields=true` để ứng dụng không fail | Cấu hình sai có thể bị bỏ qua và chạy với giá trị ngoài dự kiến | Giữ fail-fast cho cấu hình quan trọng |
| Cho mọi property default bằng localhost | Production có thể kết nối nhầm endpoint | Chỉ default giá trị thực sự an toàn |
| Dùng `optional:` để che cấu hình sai | Nguồn không có và nguồn có dữ liệu sai bị nhầm lẫn | Phân biệt lỗi nạp với lỗi validation |
| Chỉ unit test validator | Không phát hiện lỗi Binder hoặc profile | Thêm `ApplicationContextRunner`/integration test |
| Custom validator gọi HTTP | Startup phụ thuộc dịch vụ ngoài, dễ timeout | Tách validation khỏi connectivity check |
| Log toàn bộ giá trị cấu hình khi lỗi | Có thể lộ credential hoặc secret | Log key, nguồn và message an toàn |

## 15. Tình huống thực tế: cấu hình retry sai từ Config Server

`checkout-service` sử dụng Config Server. Một thay đổi cấu hình mới được triển khai:

```yaml
inventory:
  timeout: 500ms
  max-attempts: 0
  retry:
    min-attempts: 2
    max-attempts: 5
```

Config Server phản hồi thành công, Config Client lấy được dữ liệu và Binder chuyển đổi `500ms` thành `Duration`. Tuy nhiên, `max-attempts=0` vi phạm `@Min(1)`.

Quy trình xử lý:

1. Xác nhận ứng dụng đã lấy đúng application name, profile và label từ Config Server.
2. Kiểm tra lỗi binding để xác định property `inventory.max-attempts`.
3. Xác nhận đây là validation failure, không phải lỗi kết nối Config Server hoặc lỗi conversion.
4. Sửa giá trị ở nguồn cấu hình thành số trong khoảng 1–10.
5. Chạy test cấu hình trước khi phát tán.
6. Triển khai/refresh theo quy trình của hệ thống và xác nhận tất cả replica đã nhận cấu hình hợp lệ.

Không nên tắt `@Validated` hoặc bỏ `@Min` để ứng dụng khởi động. Constraint đang bảo vệ hợp đồng của client; sửa dữ liệu nguồn là cách xử lý đúng.

## 16. Checklist trước khi đưa cấu hình vào production

- [ ] Mỗi thuộc tính có mô tả kiểu, bắt buộc/tùy chọn và default rõ ràng.
- [ ] Các giá trị giới hạn có constraint tương ứng.
- [ ] Object lồng nhau có `@Valid` khi cần kiểm tra sâu.
- [ ] Collection có constraint cho cả collection và phần tử.
- [ ] Quy tắc liên thuộc tính được kiểm tra bằng class-level validator hoặc phương thức phù hợp.
- [ ] Validation provider có mặt trên classpath.
- [ ] `@ConfigurationProperties` được đăng ký đúng bằng scan hoặc enable.
- [ ] Unknown/invalid field được xử lý theo chính sách rõ ràng.
- [ ] Cấu hình từ xa được kiểm tra trước khi rollout.
- [ ] Có test cho valid, missing, conversion failure, validation failure và cross-field failure.
- [ ] Cấu hình refresh có kiểm tra lỗi và phương án rollback.
- [ ] Log và endpoint quản trị không làm lộ secret.

## 17. Tổng kết

Validation cấu hình là lớp bảo vệ hợp đồng giữa ứng dụng và môi trường triển khai. Spring Boot bind dữ liệu vào `@ConfigurationProperties`; Bean Validation kiểm tra các điều kiện trên object đã bind; Binder và conversion xử lý lỗi kiểu dữ liệu trước hoặc trong quá trình validation.

Hãy phân biệt rõ **thiếu property**, **không chuyển đổi được kiểu** và **giá trị chuyển đổi được nhưng không hợp lệ**. Dùng `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid`, `@AssertTrue` và custom constraint đúng mục đích. Kiểm thử bằng `ApplicationContextRunner` giúp xác nhận cả binding và hành vi fail-fast của context.

Trong Spring Cloud, Config Server có thể cung cấp dữ liệu đúng định dạng nhưng sai quy tắc của service. Validation cần tiếp tục được áp dụng khi cấu hình được nạp từ xa hoặc refresh. Một ứng dụng chỉ nên nhận cấu hình mới khi dữ liệu đã đáp ứng hợp đồng và các thành phần sử dụng nó có thể chuyển sang trạng thái mới an toàn.

## 18. Tài liệu tham khảo

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot API — ConfigurationPropertiesScan](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesScan.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config — Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
