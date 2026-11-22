# Liên kết qua constructor và thiết kế cấu hình bất biến

## 1. Mục tiêu và bối cảnh

Một ứng dụng Spring Boot thường có nhiều giá trị cần thay đổi theo môi trường: địa chỉ dịch vụ bên ngoài, thời gian chờ, số lần thử lại, ngưỡng giới hạn, thông tin kết nối và các tùy chọn chức năng. Thay vì đọc từng chuỗi cấu hình ở nhiều lớp nghiệp vụ, chúng ta có thể tập hợp những khóa liên quan thành một **đối tượng cấu hình có kiểu rõ ràng**.

Spring Boot cung cấp `@ConfigurationProperties` để liên kết một nhóm thuộc tính bên ngoài với các thuộc tính của Java object. Có hai kiểu thiết kế quen thuộc:

- **JavaBean binding:** tạo đối tượng, rồi gán giá trị qua setter hoặc các thuộc tính có thể chỉnh sửa.
- **Constructor binding:** cung cấp giá trị cho các tham số của constructor ngay lúc tạo đối tượng.

Bài này tập trung vào **constructor binding** và cách dùng nó để thiết kế **cấu hình bất biến** (immutable configuration), bao gồm lớp Java `final`, trường `final` và Java `record`.

Một ví dụ cấu hình:

```yaml
# src/main/resources/application.yml
checkout:
  endpoint: "https://api.example.invalid"
  connection-timeout: 3s
  max-attempts: 4
  enabled: true
```

Thay vì có bốn `@Value` riêng trong lớp nghiệp vụ, ta có thể dùng:

```java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        URI endpoint,
        Duration connectionTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

Spring Boot đọc các khóa dưới tiền tố `checkout`, chuyển đổi kiểu và gọi constructor của `CheckoutProperties` để tạo đối tượng. Các thành phần khác chỉ cần tiêm `CheckoutProperties` qua dependency injection.

**Ý tưởng chính:** cấu hình nên được cung cấp đầy đủ khi đối tượng hình thành, thay vì tạo một “vỏ rỗng” rồi sửa dần các trường.

## 2. Constructor binding giải quyết vấn đề gì?

Xem cách liên kết theo JavaBean:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public class MutableCheckoutProperties {

    private String endpoint;
    private int maxAttempts;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

Đối tượng trên có thể được khởi tạo mà chưa có giá trị rồi thay đổi qua setter. Điều này không nhất thiết là sai, nhưng có những hạn chế:

1. Trạng thái chưa hoàn chỉnh có thể tồn tại trong giai đoạn tạo đối tượng.
2. Mã ứng dụng khác có thể vô tình gọi setter và thay đổi giá trị sau khi ứng dụng đã chạy.
3. Khó thể hiện rõ những thuộc tính nào bắt buộc cho constructor.
4. Một nhóm cấu hình lớn trở thành tập hợp các trường có thể gán lại.

Với constructor binding, thiết kế sẽ như sau:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final String endpoint;
    private final int maxAttempts;

    public CheckoutProperties(String endpoint, int maxAttempts) {
        this.endpoint = endpoint;
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Khi Spring Boot tạo đối tượng này từ nguồn cấu hình:

- Giá trị được giải quyết và chuyển đổi **trước khi gọi constructor**.
- Constructor nhận toàn bộ những giá trị cần thiết.
- Các trường `final` chỉ được gán lúc khởi tạo.
- Không cần setter để Spring Boot liên kết giá trị.

Cách làm này đặc biệt phù hợp khi cấu hình được xem là **trạng thái đầu vào cố định trong suốt vòng đời của một bean**.

## 3. Điều kiện để constructor binding hoạt động

Trong Spring Boot 3.x, một lớp có `@ConfigurationProperties` và **một constructor có tham số phù hợp** thường được sử dụng với constructor binding mà không cần gắn thêm `@ConstructorBinding`.

Ví dụ:

```java
@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final String endpoint;
    private final int maxAttempts;

    public CheckoutProperties(String endpoint, int maxAttempts) {
        this.endpoint = endpoint;
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Điều kiện quan trọng là **bean cấu hình phải được đăng ký thông qua cơ chế dành cho `@ConfigurationProperties`**, chẳng hạn:

- `@ConfigurationPropertiesScan`;
- `@EnableConfigurationProperties(CheckoutProperties.class)`.

Không nên tạo một lớp `@Component` thông thường rồi kỳ vọng constructor binding của `@ConfigurationProperties` sẽ tự động thay thế cơ chế autowiring của Spring. Các bean được tạo bằng cách `@Component`, `@Bean` thông thường hoặc `@Import` thuộc cơ chế đăng ký bean khác; constructor binding không áp dụng cho chúng theo cùng cách.

Constructor binding và **dependency injection qua constructor** không phải một khái niệm:

- Constructor binding của `@ConfigurationProperties`: tham số đến từ các **giá trị cấu hình** do binder xử lý.
- Constructor injection của `@Service`, `@Component`: tham số chủ yếu là **dependency/bean** được Spring container giải quyết.

Hai cơ chế thường được dùng liên tiếp: binder tạo bean `CheckoutProperties`, rồi Spring tiêm bean ấy vào service.

## 4. Bước 1: tạo tệp cấu hình

Giả sử xây dựng một dịch vụ xác nhận đơn hàng. Đặt trong `src/main/resources/application.yml`:

```yaml
checkout:
  endpoint: "https://checkout.example.invalid"
  connection-timeout: 5s
  max-attempts: 3
  enabled: true
```

Cấu hình chứa bốn khóa:

| Khóa YAML | Ý nghĩa | Kiểu Java mong muốn |
| --- | --- | --- |
| `checkout.endpoint` | Địa chỉ dịch vụ | `URI` |
| `checkout.connection-timeout` | Thời gian chờ kết nối | `Duration` |
| `checkout.max-attempts` | Số lần được thử | `int` |
| `checkout.enabled` | Bật/tắt chức năng | `boolean` |

Spring Boot có bộ chuyển đổi kiểu cho nhiều kiểu thông dụng như `String`, số nguyên, Boolean, `Duration`, `DataSize`, `URI` và một số kiểu liên quan. Điều này giúp tránh phải parse chuỗi cấu hình thủ công ở nhiều nơi.

Địa chỉ dùng trong ví dụ là địa chỉ minh họa, không phải máy chủ cần liên hệ khi chạy chương trình.

## 5. Bước 2: viết lớp cấu hình bất biến dùng constructor

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public final class CheckoutProperties {

    private final URI endpoint;
    private final Duration connectionTimeout;
    private final int maxAttempts;
    private final boolean enabled;

    public CheckoutProperties(
            URI endpoint,
            Duration connectionTimeout,
            int maxAttempts,
            boolean enabled) {
        this.endpoint = endpoint;
        this.connectionTimeout = connectionTimeout;
        this.maxAttempts = maxAttempts;
        this.enabled = enabled;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getConnectionTimeout() {
        return connectionTimeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

Ở đây:

1. `@ConfigurationProperties(prefix = "checkout")` giới hạn nhóm thuộc tính cần liên kết.
2. Tên tham số `connectionTimeout` tương ứng với khóa `connection-timeout` nhờ cơ chế **relaxed binding**.
3. Các tham số được binder chuyển thành kiểu Java tương ứng trước khi gọi constructor.
4. Mọi trường đều `private final` và không có setter.
5. Khi đối tượng đã được tạo, mã nghiệp vụ chỉ có thể đọc những giá trị này qua getter.

Trong Spring Boot 3.x, constructor duy nhất nói trên đủ để xác định constructor binding theo quy tắc thông thường.

Đối với lớp cấu hình dùng constructor binding, **tên tham số constructor** cần được giữ lại trong bytecode để binder biết khóa cấu hình tương ứng. Khi xây dựng bằng Spring Boot Gradle plugin hoặc Maven plugin với cấu hình phù hợp, tùy chọn biên dịch Java `-parameters` thường được thiết lập. Nếu dự án có quy trình build riêng, hãy kiểm tra tham số này thay vì bỏ qua khi xuất hiện lỗi liên quan đến tên tham số.

## 6. Bước 3: đăng ký ConfigurationProperties với Spring Boot

Chỉ khai báo annotation trên lớp chưa đủ nếu ứng dụng không có cơ chế phát hiện và đăng ký lớp ấy.

### 6.1. Dùng @ConfigurationPropertiesScan

Trong lớp khởi động:

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

Spring Boot quét các kiểu `@ConfigurationProperties` trong package thích hợp và đăng ký chúng thành bean. Để ví dụ hoạt động, đặt `CheckoutProperties` cùng package hoặc package con nằm trong phạm vi quét.

Nếu bạn bố trí lớp ở package nằm ngoài vùng quét mặc định, có thể cấu hình rõ `@ConfigurationPropertiesScan(basePackages = "...")`.

### 6.2. Dùng @EnableConfigurationProperties

Thay vì quét, có thể đăng ký trực tiếp kiểu cần bind:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CheckoutProperties.class)
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Cách này thích hợp khi số lớp cấu hình ít hoặc khi muốn khai báo tường minh những kiểu cấu hình cần kích hoạt.

**Chỉ cần chọn một cơ chế đăng ký phù hợp** cho ví dụ. Không cần gắn `@Component` lên lớp constructor-bound `CheckoutProperties`.

## 7. Bước 4: tiêm đối tượng cấu hình vào service

Sau khi bean `CheckoutProperties` được tạo, các service có thể dùng dependency injection thông thường.

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return "endpoint=" + properties.getEndpoint()
                + ", timeout=" + properties.getConnectionTimeout()
                + ", maxAttempts=" + properties.getMaxAttempts()
                + ", enabled=" + properties.isEnabled();
    }
}
```

Đây là **constructor injection của bean cấu hình vào service**. Lưu ý trình tự:

```text
application.yml / biến môi trường / đối số CLI
                 |
                 v
        ConfigurationProperties Binder
                 |
                 | tạo đối tượng bằng constructor
                 v
          CheckoutProperties bean
                 |
                 | Spring dependency injection
                 v
             CheckoutService
```

Một thành phần chạy khi khởi động:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CheckoutPrinter implements ApplicationRunner {

    private final CheckoutService service;

    public CheckoutPrinter(CheckoutService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.describe());
    }
}
```

Kết quả minh họa khi không có nguồn cấu hình khác ghi đè:

```text
endpoint=https://checkout.example.invalid, timeout=PT5S, maxAttempts=3, enabled=true
```

`Duration#toString()` biểu diễn 5 giây theo định dạng ISO-8601 là `PT5S`. Giá trị thực trong Java vẫn là một `Duration`, không phải chuỗi `"5s"`.

## 8. Dùng record để rút gọn thiết kế bất biến

Java `record` rất phù hợp với đối tượng cấu hình chỉ chứa dữ liệu. Record tự sinh constructor chính (canonical constructor), accessor, `equals`, `hashCode` và `toString`.

Với Java 17 và Spring Boot 3.x, lớp ở ví dụ trên có thể rút gọn thành:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        URI endpoint,
        Duration connectionTimeout,
        int maxAttempts,
        boolean enabled) {
}
```

Nếu đã đăng ký kiểu này bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Spring Boot có thể bind các thuộc tính bằng canonical constructor của record.

Truy cập giá trị của record thông qua accessor:

```java
properties.endpoint();
properties.connectionTimeout();
properties.maxAttempts();
properties.enabled();
```

Lưu ý record **không tự sinh** phương thức getter theo quy ước `getEndpoint()`. Nếu chuyển từ class sang record, mã sử dụng phải đổi sang accessor phù hợp.

Ví dụ service tương ứng:

```java
@Service
public class CheckoutService {

    private final CheckoutProperties properties;

    public CheckoutService(CheckoutProperties properties) {
        this.properties = properties;
    }

    public boolean canCheckout() {
        return properties.enabled() && properties.maxAttempts() > 0;
    }
}
```

Record là lựa chọn gọn gàng khi dữ liệu cấu hình có cấu trúc rõ, thành phần là các kiểu bất biến hoặc được bảo vệ khỏi sửa đổi, và không cần quan hệ kế thừa từ một lớp Java khác.

## 9. Bất biến ở mức nào?

**Trường `final` hoặc record chưa đủ để bảo đảm bất biến sâu (deep immutability).**

Ví dụ record:

```java
public record AccessProperties(List<String> allowedOrigins) {
}
```

Mặc dù trường tham chiếu `allowedOrigins` của record không thể gán lại, **danh sách mà nó tham chiếu có thể vẫn thay đổi** nếu là một `ArrayList` mutable và có người giữ tham chiếu.

Muốn đối tượng cấu hình ổn định hơn, có thể tạo bản sao phòng vệ:

```java
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "access")
public record AccessProperties(List<String> allowedOrigins) {

    public AccessProperties {
        allowedOrigins = allowedOrigins == null
                ? List.of()
                : List.copyOf(allowedOrigins);
    }
}
```

Đây là một **compact canonical constructor** của record. Java cho phép chuẩn hóa tham số trước khi thành phần của record được gán.

`List.copyOf` tạo danh sách không cho phép sửa đổi thông qua API thông thường và không dùng chung danh sách mutable của người gọi. Với kiểu phần tử là `String`, đây là một thiết kế đơn giản để cải thiện tính bất biến. Nếu các phần tử bên trong là đối tượng mutable, vẫn cần xem xét bất biến của từng phần tử.

Tương tự, với `Map` có thể cân nhắc `Map.copyOf`. Các phương thức này không nhận phần tử/giá trị `null`; cần chọn hợp đồng cấu hình rõ ràng trước khi áp dụng.

## 10. Giá trị mặc định với @DefaultValue

Một cấu hình bất biến thường phải đối mặt với câu hỏi: nếu khóa không xuất hiện trong nguồn cấu hình, constructor sẽ nhận gì?

Spring Boot cung cấp `@DefaultValue` cho tham số constructor binding hoặc thành phần record để cung cấp giá trị dự phòng tại bước binding.

Ví dụ:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("https://checkout.example.invalid") String endpoint,
        @DefaultValue("5s") Duration connectionTimeout,
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("true") boolean enabled) {
}
```

Nếu một khóa không có trong các nguồn được xét và binder sử dụng giá trị mặc định, nó sẽ chuyển đổi chuỗi trong `@DefaultValue` sang kiểu Java tương ứng.

Ví dụ tệp `application.yml` chỉ có:

```yaml
checkout:
  endpoint: "https://checkout.internal.invalid"
```

thì giá trị dự kiến là:

```text
endpoint          = https://checkout.internal.invalid
connectionTimeout = PT5S
maxAttempts       = 3
enabled           = true
```

Cần phân biệt:

- **Mặc định ở cấp cấu hình:** viết khóa trong `application.yml` chung để tất cả môi trường nhìn thấy.
- **Mặc định ở cấp binder:** dùng `@DefaultValue` khi giá trị không xuất hiện trong các nguồn mà binder đang liên kết.
- **Mặc định trong code nghiệp vụ:** tự rẽ nhánh khi xử lý; đôi khi cần thiết nhưng dễ làm quy tắc cấu hình bị phân tán.

Với cấu hình được dùng bởi người vận hành, thường nên công khai các giá trị mặc định quan trọng trong tài liệu của ứng dụng.

### 10.1. Phân biệt thiếu giá trị với giá trị rỗng

Một giá trị không được khai báo khác với giá trị được khai báo nhưng rỗng:

```properties
checkout.endpoint=
```

Nếu đã có giá trị rỗng, không nên mặc định rằng `@DefaultValue` luôn thay bằng chuỗi mặc định. Kết quả phụ thuộc nguồn cấu hình, kiểu mục tiêu và quy tắc chuyển đổi. Với các trường bắt buộc như URL, nên dùng validation để phát hiện dữ liệu không hợp lệ.

## 11. Cấu hình lồng nhau và constructor binding

Một ứng dụng thực tế có thể có nhiều mức:

```yaml
checkout:
  endpoint: "https://checkout.example.invalid"
  retry:
    attempts: 4
    delay: 2s
```

Với record lồng nhau:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        String endpoint,
        Retry retry) {

    public record Retry(
            int attempts,
            Duration delay) {
    }
}
```

Cơ chế liên kết:

```text
checkout.endpoint         -> CheckoutProperties.endpoint
checkout.retry.attempts   -> CheckoutProperties.Retry.attempts
checkout.retry.delay      -> CheckoutProperties.Retry.delay
```

Spring Boot có thể tạo `Retry` bằng constructor của nó, rồi truyền đối tượng `Retry` vào constructor của `CheckoutProperties`.

Cách truy cập:

```java
String endpoint = properties.endpoint();
int attempts = properties.retry().attempts();
Duration delay = properties.retry().delay();
```

Nếu **toàn bộ nhánh `retry` không có trong cấu hình**, binder có thể không tạo đối tượng lồng nhau và tham số `retry` có thể nhận `null`. Điều này quan trọng vì đoạn `properties.retry().attempts()` sẽ lỗi nếu `retry()` là `null`.

Có thể xử lý bằng một trong các hướng:

- Xem nhánh lồng nhau là **bắt buộc** và dùng validation.
- Đặt giá trị mặc định cho đối tượng lồng nhau.
- Dùng constructor xử lý trạng thái thiếu nhánh một cách tường minh.

## 12. Tạo đối tượng lồng nhau mặc định

Spring Boot hỗ trợ một cách viết hữu ích: `@DefaultValue` **không có tham số** trên thành phần lồng nhau để yêu cầu bind một đối tượng lồng nhau ngay cả khi không có thuộc tính thuộc nhánh đó.

Ví dụ:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("https://checkout.example.invalid") String endpoint,
        @DefaultValue Retry retry) {

    public record Retry(
            @DefaultValue("3") int attempts,
            @DefaultValue("1s") Duration delay) {
    }
}
```

Với cấu hình không khai báo `checkout.retry.*`, binder có thể tạo `Retry` từ các mặc định của những thành phần lồng nhau. Sau đó:

```java
properties.retry().attempts()  // 3
properties.retry().delay()     // PT1S
```

Lưu ý: các giá trị mặc định vẫn phải chuyển đổi được sang kiểu của constructor parameter. Khi cần kiểm soát chặt chẽ tính hợp lệ, hãy bổ sung validation.

Cách này phù hợp khi nhánh `retry` là một phần cấu hình logic luôn nên tồn tại, nhưng ứng dụng có bộ giá trị mặc định tốt.

## 13. Dùng validation để bảo vệ bất biến đúng nghĩa

Một đối tượng có trường `final` vẫn có thể được tạo với dữ liệu **không hợp lệ**, ví dụ `maxAttempts=-7` hoặc một URL bị thiếu.

Spring Boot có thể kết hợp `@ConfigurationProperties` với Bean Validation để kiểm tra đầu vào trong giai đoạn khởi tạo.

Ví dụ với record:

```java
package com.example.configdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @NotBlank String endpoint,
        @Min(1) @Max(20) int maxAttempts,
        @NotNull @Valid Retry retry) {

    public record Retry(
            @Min(1) int attempts,
            @NotNull java.time.Duration delay) {
    }
}
```

Các ràng buộc:

- `@NotBlank` yêu cầu `endpoint` không phải chuỗi chỉ chứa khoảng trắng.
- `@Min(1)` và `@Max(20)` giới hạn số lần thử.
- `@NotNull` trên `retry` yêu cầu đối tượng lồng nhau có mặt.
- `@Valid` yêu cầu kiểm tra cả các ràng buộc bên trong `Retry`.
- `@NotNull` trên `delay` yêu cầu có giá trị `Duration`.

Để ví dụ sử dụng Jakarta Validation trên một dự án Spring Boot thông thường, cần có dependency cung cấp validation, thường là `spring-boot-starter-validation`.

Ví dụ với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Khi Spring Boot liên kết và kiểm tra bean cấu hình, dữ liệu không hợp lệ có thể khiến ứng dụng **thất bại ngay lúc khởi động**. Đây thường là hành vi tốt hơn việc chạy một thời gian rồi mới phát hiện tham số cấu hình sai.

**Quan trọng:** tính bất biến nói rằng dữ liệu không bị sửa sau khi đối tượng được tạo. Validation nói rằng dữ liệu **đã hợp lệ khi được tạo**. Hai thuộc tính hỗ trợ nhau nhưng không thay thế nhau.

## 14. Dùng constructor để áp dụng bất biến nghiệp vụ

Ngoài Bean Validation, constructor có thể chứa logic kiểm tra miền dữ liệu.

Ví dụ lớp thường:

```java
@ConfigurationProperties(prefix = "retry")
public final class RetryProperties {

    private final int maxAttempts;

    public RetryProperties(int maxAttempts) {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "retry.max-attempts phải nằm trong khoảng 1..10");
        }
        this.maxAttempts = maxAttempts;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Constructor này bảo đảm không có `RetryProperties` hợp lệ nào được tạo với `maxAttempts` nằm ngoài phạm vi 1..10, kể cả khi đối tượng được tạo thủ công ngoài Spring.

Với record có thể dùng **compact constructor**:

```java
@ConfigurationProperties(prefix = "retry")
public record RetryProperties(int maxAttempts) {

    public RetryProperties {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "retry.max-attempts phải nằm trong khoảng 1..10");
        }
    }
}
```

Ở đây không cần tự gán `this.maxAttempts` trong compact constructor; Java thực hiện việc gán cho thành phần record sau phần thân constructor.

So sánh lựa chọn:

- **Bean Validation:** có annotation diễn đạt ràng buộc, thích hợp với nhiều thuộc tính và báo cáo lỗi cấu hình có cấu trúc.
- **Kiểm tra trong constructor:** hữu ích khi có bất biến liên quan nhiều tham số hoặc muốn bảo vệ cả các lần tạo đối tượng ngoài Spring.
- Có thể kết hợp cả hai khi có lý do rõ ràng.

Hãy giữ thông báo lỗi dễ hiểu và tránh in thông tin bí mật khi một ràng buộc thất bại.

## 15. Nếu có nhiều constructor thì sao?

Trong Spring Boot 3.x, trường hợp **một constructor có tham số** thường không cần `@ConstructorBinding`. Nhưng khi lớp `@ConfigurationProperties` có **nhiều constructor**, cần chỉ rõ constructor dùng để liên kết cấu hình.

Ví dụ:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "worker")
public final class WorkerProperties {

    private final String region;
    private final int threads;

    @ConstructorBinding
    public WorkerProperties(String region, int threads) {
        this.region = region;
        this.threads = threads;
    }

    public WorkerProperties() {
        this("local", 2);
    }

    public String getRegion() {
        return region;
    }

    public int getThreads() {
        return threads;
    }
}
```

Annotation `@ConstructorBinding` ở đây chỉ định constructor mong muốn cho **binder**. Đối với Spring Boot 3.x, import tương ứng là:

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

Cần chú ý **sự khác biệt phiên bản**. Một số tài liệu/mã Spring Boot 2.x cũ dùng cách đặt và package của `@ConstructorBinding` khác với Spring Boot 3.x. Khi nâng cấp, hãy đối chiếu theo phiên bản Spring Boot thực tế trong `pom.xml` hoặc `build.gradle`.

Đối với một `record` chỉ có canonical constructor thông thường, Spring Boot có thể tự sử dụng constructor đó; không cần gắn `@ConstructorBinding` chỉ để làm code có thêm annotation.

## 16. @ConfigurationProperties không phải @Value trên constructor

Hai ví dụ có điểm chung là đều nhận giá trị lúc tạo đối tượng, nhưng cơ chế khác nhau.

### 16.1. @Value trên constructor của bean thông thường

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SmsClient {

    private final String sender;

    public SmsClient(@Value("${sms.sender:system}") String sender) {
        this.sender = sender;
    }
}
```

Spring dùng cơ chế **dependency injection** để tạo `SmsClient`, đồng thời giải quyết placeholder `${sms.sender:system}`.

### 16.2. Constructor binding của ConfigurationProperties

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "sms")
public record SmsProperties(String sender, int retryCount) {
}
```

Ở đây, binder tra cứu các khóa `sms.sender` và `sms.retry-count`, chuyển đổi kiểu và tạo một **bean cấu hình chuyên biệt**. Constructor parameters không cần ghi từng `@Value`.

Một service thông thường sau đó có thể tiêm `SmsProperties`:

```java
@Service
public class SmsClient {

    private final SmsProperties properties;

    public SmsClient(SmsProperties properties) {
        this.properties = properties;
    }
}
```

**Không nên gắn `@Component` vào `SmsProperties` chỉ để “đăng ký bean cho chắc”** nếu đang muốn dùng constructor binding. Hãy dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Với một hoặc hai giá trị độc lập, `@Value` có thể đủ. Với một nhóm cấu hình có cấu trúc, cần validation hoặc bất biến, `@ConfigurationProperties` thường thể hiện thiết kế rõ ràng hơn.

## 17. Relaxed binding và quy tắc đặt tên

Tệp YAML thường dùng tên **kebab-case**:

```yaml
worker:
  max-threads: 8
  idle-timeout: 30s
```

Record có thể dùng camelCase:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        int maxThreads,
        java.time.Duration idleTimeout) {
}
```

Binder của Spring Boot hỗ trợ liên kết các dạng tên tương ứng theo quy tắc relaxed binding.

Điều này cũng giúp làm việc với biến môi trường. Ví dụ dạng biến hệ điều hành tiêu biểu:

```bash
WORKER_MAXTHREADS=12 WORKER_IDLETIMEOUT=45s java -jar app.jar
```

Trong cách chuyển tên chuẩn cho environment variables của Spring Boot, dấu chấm thành dấu gạch dưới, dấu gạch ngang bị bỏ và tên được chuyển thành chữ hoa. Vì vậy tên như `WORKER_MAXTHREADS` là dạng quen thuộc cho khóa `worker.max-threads`, thay vì tùy tiện đặt `WORKER_MAX_THREADS` rồi hy vọng binder hiểu mọi tình huống như nhau.

Khi giá trị không như mong đợi, hãy kiểm tra tên khóa ở nguồn thực tế, tên tham số constructor và kết quả từ Spring `Environment`.

## 18. Constructor binding vẫn tuân theo thứ tự ưu tiên nguồn

Thiết kế bất biến **không làm thay đổi** cách Spring Boot chọn cấu hình bên ngoài.

Ví dụ:

```yaml
# application.yml
worker:
  max-threads: 4
```

Một record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Khi chạy:

```bash
java -jar app.jar --worker.max-threads=16
```

binder nhận giá trị có hiệu lực của `worker.max-threads`, thường là `16` vì đối số dòng lệnh có mức ưu tiên cao hơn Config Data trong cấu hình Spring Boot thông thường.

Với profile:

```yaml
# application-prod.yml
worker:
  max-threads: 24
```

Khi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

nếu không có nguồn cao hơn ghi đè, record được tạo với `maxThreads=24`.

Điều này thể hiện nguyên tắc:

**Thứ tự ưu tiên nguồn quyết định giá trị đầu vào; constructor binding quyết định cách biến giá trị đầu vào ấy thành một đối tượng có kiểu và có thể bất biến.**

## 19. Bất biến và vòng đời cấu hình

Một bean `@ConfigurationProperties` dùng constructor binding thông thường được tạo trong quá trình khởi động Spring context.

Giả sử thời điểm khởi động có:

```text
worker.max-threads = 8
```

Binder tạo:

```java
new WorkerProperties(8)
```

Sau đó bạn sửa `application.yml` thành:

```yaml
worker:
  max-threads: 12
```

Một bean cấu hình bất biến đang tồn tại **không tự biến thành đối tượng mới** chỉ vì tệp trên đĩa thay đổi. Thường phải khởi động lại ứng dụng để các giá trị mới được nạp vào bean, trừ khi dự án có cơ chế refresh/rebind cụ thể được thiết kế bổ sung.

Điều này là hợp lý với cấu hình bất biến: các service nhìn thấy một ảnh chụp cấu hình ổn định thay vì các trường bị đổi giữa lúc đang xử lý yêu cầu.

Nếu ứng dụng cần cấu hình thay đổi ở thời gian chạy, hãy chọn kiến trúc riêng cho chức năng ấy, thay vì kỳ vọng constructor binding tự cung cấp khả năng hot reload.

## 20. Thiết kế cấu hình tập trung thay vì rải rác

Giả sử một dịch vụ gọi API bên ngoài cần:

```yaml
gateway:
  base-url: "https://gateway.example.invalid"
  connect-timeout: 2s
  read-timeout: 10s
  retry-count: 3
```

Nếu mỗi class nghiệp vụ dùng một vài `@Value`, cấu hình dễ bị phân tán:

```java
@Value("${gateway.base-url}")
private String url;

@Value("${gateway.retry-count}")
private int retries;
```

Một cách tốt hơn với nhóm thuộc tính liên quan:

```java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        java.net.URI baseUrl,
        java.time.Duration connectTimeout,
        java.time.Duration readTimeout,
        int retryCount) {
}
```

Các service sử dụng cùng một kiểu:

```java
@Service
public class GatewayClient {

    private final GatewayProperties config;

    public GatewayClient(GatewayProperties config) {
        this.config = config;
    }

    public String summary() {
        return "timeout=" + config.readTimeout()
                + ", retries=" + config.retryCount();
    }
}
```

Lợi ích:

1. Cấu hình có **một tên và một hợp đồng kiểu dữ liệu**.
2. Các thuộc tính liên quan được nhóm dưới tiền tố `gateway`.
3. Có thể thêm validation một lần tại lớp cấu hình.
4. Unit test có thể tạo record trực tiếp mà không cần Spring.
5. Các service không phải biết tên từng khóa chuỗi.
6. Khi thay đổi thiết kế cấu hình, compiler hỗ trợ phát hiện nơi dùng accessor.

Không nên gom tất cả thuộc tính của toàn ứng dụng vào một record khổng lồ. Hãy chia theo ranh giới trách nhiệm như `MailProperties`, `GatewayProperties`, `StorageProperties`.

## 21. Cấu hình danh sách và map bất biến

Một đối tượng cấu hình có thể chứa danh sách hoặc map.

Ví dụ:

```yaml
cors:
  allowed-origins:
    - "https://app.example.invalid"
    - "https://admin.example.invalid"
  headers:
    client-id: "X-Client-Id"
    trace-id: "X-Trace-Id"
```

Record:

```java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "cors")
public record CorsProperties(
        List<String> allowedOrigins,
        Map<String, String> headers) {

    public CorsProperties {
        allowedOrigins = allowedOrigins == null
                ? List.of()
                : List.copyOf(allowedOrigins);

        headers = headers == null
                ? Map.of()
                : Map.copyOf(headers);
    }
}
```

Cách này nhận dữ liệu từ binder rồi chuẩn hóa sang collection không thể sửa qua những phương thức thay đổi phổ biến.

Tuy nhiên, cần nhớ:

- `List.copyOf` và `Map.copyOf` không chấp nhận phần tử/giá trị null.
- Một collection bất biến **không làm các đối tượng phần tử mutable trở nên bất biến**.
- Nếu cấu hình cần thứ tự phần tử, hãy dùng kiểu dữ liệu và thao tác phù hợp; không giả định `Map.copyOf` bảo đảm thứ tự lặp mà ứng dụng dựa vào.
- Nếu bạn muốn phân biệt “không khai báo collection” với “có collection rỗng”, đừng vô tình chuẩn hóa cả hai thành cùng một giá trị.

Bất biến là **một quyết định thiết kế có ý nghĩa**, không chỉ là việc thêm từ khóa `final`.

## 22. Kiểm thử constructor-bound configuration

Với record hoặc lớp chỉ có constructor, có thể kiểm thử ở hai cấp độ khác nhau.

### 22.1. Unit test không cần Spring

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class WorkerPropertiesUnitTest {

    @Test
    void storesValues() {
        WorkerProperties properties = new WorkerProperties(6);

        assertEquals(6, properties.maxThreads());
    }
}
```

Test này kiểm tra **hợp đồng của Java object**. Nó không kiểm tra việc Spring đọc YAML và liên kết tên thuộc tính.

### 22.2. Test binding qua ApplicationContextRunner

Để kiểm tra chính cơ chế binding, Spring Boot Test có `ApplicationContextRunner`.

Giả sử record:

```java
package com.example.configdemo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        int maxThreads,
        Duration idleTimeout) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesBindingTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsThroughConstructor() {
        contextRunner
                .withPropertyValues(
                        "worker.max-threads=12",
                        "worker.idle-timeout=45s")
                .run(context -> {
                    WorkerProperties properties =
                            context.getBean(WorkerProperties.class);

                    assertThat(properties.maxThreads()).isEqualTo(12);
                    assertThat(properties.idleTimeout())
                            .isEqualTo(Duration.ofSeconds(45));
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {
    }
}
```

Lưu ý lớp `WorkerProperties` trong phần test này được đăng ký bằng `@EnableConfigurationProperties`, nhờ đó Spring Boot có thể sử dụng binder. Giá trị được cấp qua `withPropertyValues`, không phụ thuộc vào một tệp YAML cụ thể.

Test dạng này hữu ích khi muốn kiểm chứng:

- Đúng tên thuộc tính.
- Đúng chuyển đổi kiểu.
- Giá trị mặc định.
- Validation và lỗi khởi tạo.
- Các nhánh cấu hình lồng nhau.

### 22.3. Kiểm thử tích hợp với @SpringBootTest

Nếu cần xác nhận kết hợp của nhiều bean trong toàn ứng dụng, có thể dùng:

```java
@SpringBootTest(properties = {
        "worker.max-threads=16",
        "worker.idle-timeout=30s"
})
class WorkerIntegrationTest {

    @Autowired
    private WorkerProperties properties;

    @Test
    void usesTestProperties() {
        assertEquals(16, properties.maxThreads());
    }
}
```

Trong ví dụ này cần import các annotation tương ứng từ JUnit, Spring và Spring Boot Test. Ứng dụng phải có một cấu hình `@SpringBootApplication` phù hợp được Spring Boot tìm thấy hoặc được khai báo tường minh.

Không nhất thiết dùng `@SpringBootTest` cho mọi bài test; test binding có phạm vi nhỏ thường chạy nhanh và dễ xác định lỗi hơn.

## 23. Lỗi phổ biến và cách xử lý

### 23.1. Gắn @Component lên record và mong binder dùng constructor

Ví dụ không phù hợp cho constructor binding:

```java
@Component
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Vấn đề: `@Component` đưa lớp vào cơ chế đăng ký bean thông thường; constructor binding của `@ConfigurationProperties` không được áp dụng giống trường hợp tạo bean qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Cách đúng:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

và đăng ký kiểu bằng một trong hai cơ chế dành cho `@ConfigurationProperties`.

### 23.2. Quên đăng ký lớp cấu hình

Có `@ConfigurationProperties` nhưng không dùng scan hoặc enable: service có thể báo không tìm thấy bean `WorkerProperties`.

Hãy kiểm tra package quét, annotation trên ứng dụng và cách đăng ký, thay vì thêm `@Component` như một biện pháp vá khi đang dùng constructor binding.

### 23.3. Viết sai tiền tố hoặc tên khóa

Record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Tệp YAML:

```yaml
workers:
  max-threads: 8
```

Ở đây `workers` và `worker` khác nhau. Binder không thể tự suy luận rằng hai tiền tố là một.

Một lỗi khác là viết `worker.max-thread` số ít trong khi cấu hình mong đợi `maxThreads`. Nên thống nhất tên chuẩn ở nguồn và kiểu Java.

### 23.4. Thiếu -parameters khi dùng class constructor

Với class thông thường, tên tham số constructor có vai trò trong binding. Nếu quá trình biên dịch không giữ tên tham số, binder có thể không xác định được khóa tương ứng.

Hãy bảo đảm biên dịch với `-parameters`. Khi dùng plugin build chính thức của Spring Boot, kiểm tra cấu hình hiện tại trước khi thêm lại tùy chọn thủ công.

### 23.5. Dùng @ConstructorBinding sai package của phiên bản

Một dự án nâng cấp từ Spring Boot 2.x có thể còn import `@ConstructorBinding` theo package hoặc cách đặt cũ. Trong Spring Boot 3.x, khi cần chỉ rõ constructor thì dùng annotation trên constructor từ:

```java
org.springframework.boot.context.properties.bind.ConstructorBinding
```

Đừng sao chép mẫu mã cũ mà không xét phiên bản thực tế.

### 23.6. Trông chờ setter chạy với record

Record không có setter theo mô hình JavaBean. Spring Boot tạo record qua constructor và các thành phần record không thể bị gán lại sau đó theo cách setter binding thông thường.

Nếu bạn cần các bước cập nhật mutable thực sự, hãy xác định lại yêu cầu thay vì cố thêm setter không phù hợp vào record.

### 23.7. Quên nhánh cấu hình lồng nhau có thể null

Với record:

```java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(Retry retry) {
    public record Retry(int attempts) {
    }
}
```

nếu không khai báo `checkout.retry.*`, `retry()` có thể là `null`. Hãy dùng validation hoặc mặc định lồng nhau nếu nhánh đó phải luôn có mặt.

### 23.8. Cấu hình số sai kiểu

Ví dụ:

```yaml
worker:
  max-threads: many
```

Không thể chuyển `many` thành `int` theo quy tắc thông thường. Quá trình binding có thể khiến ứng dụng không khởi động.

Đặt giá trị có kiểu tương ứng, ví dụ `8`, rồi kiểm chứng nguồn nào đang cung cấp giá trị có hiệu lực.

### 23.9. Hiểu final là deep immutable

Một trường `final List<String>` không tự ngăn thay đổi danh sách. Với dữ liệu collection, cần bản sao phòng vệ và lựa chọn kiểu bất biến thích hợp nếu muốn bảo đảm tính ổn định.

### 23.10. Dùng record.toString() với secret

Record tự sinh `toString()` có thể hiển thị mọi component, bao gồm mật khẩu hoặc token nếu cấu hình chứa chúng.

**Không ghi toàn bộ bean cấu hình ra log** trong hệ thống thật khi nó có trường nhạy cảm. Việc dùng record giúp mã gọn hơn nhưng không tự bảo vệ secret.

## 24. Đối chiếu một thiết kế mutable và immutable

### Mutable JavaBean

```java
@ConfigurationProperties(prefix = "mail")
public class MailProperties {

    private String host;
    private int port;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
```

### Immutable class constructor

```java
@ConfigurationProperties(prefix = "mail")
public final class MailProperties {

    private final String host;
    private final int port;

    public MailProperties(String host, int port) {
        this.host = host;
        this.port = port;
    }

    public String getHost() {
        return host;
    }

    public int getPort() {
        return port;
    }
}
```

### Immutable record

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(String host, int port) {
}
```

Ba ví dụ trên diễn đạt cùng hai giá trị `host` và `port`, nhưng mỗi ví dụ cần được dùng **riêng lẻ** vì chúng cùng mang tên `MailProperties`. Khác biệt nằm ở hợp đồng thay đổi trạng thái:

| Thiết kế | Setter | Khởi tạo bằng constructor chứa giá trị | Tính bất biến sau tạo |
| --- | --- | --- | --- |
| Mutable JavaBean | Có | Không bắt buộc | Không |
| Class với trường final | Không | Có | Có với các thành phần bất biến |
| Record | Không | Có, qua canonical constructor | Bất biến nông; cần chú ý thành phần mutable |

Với ứng dụng coi cấu hình là ảnh chụp tại thời điểm khởi động, constructor-bound class hoặc record thường là mô hình rõ ràng. Với một bean mà mã cần cập nhật các thuộc tính trong vòng đời, nên cân nhắc yêu cầu thực sự thay vì chọn cấu hình mutable chỉ vì thuận tiện lúc đầu.

## 25. Bài tập thực hành

### Bài tập A: thiết kế record

Cho YAML:

```yaml
report:
  title: "Daily report"
  interval: 10m
  max-records: 500
  enabled: true
```

Hãy viết record được liên kết qua constructor.

Đáp án mẫu:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        String title,
        Duration interval,
        int maxRecords,
        boolean enabled) {
}
```

Đăng ký `ReportProperties` với `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### Bài tập B: thêm mặc định

Ứng dụng cần `report.max-records` mặc định là `100` khi không được khai báo.

Một cách làm:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "report")
public record ReportProperties(
        @DefaultValue("100") int maxRecords) {
}
```

Nếu tệp `application.yml` có `report.max-records=500`, giá trị cấu hình thực tế vẫn được dùng; mặc định chỉ áp dụng khi không có dữ liệu phù hợp.

### Bài tập C: nhánh lồng nhau

Cho YAML:

```yaml
storage:
  bucket: "reports"
  retry:
    attempts: 3
    delay: 2s
```

Viết record:

```java
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        String bucket,
        Retry retry) {

    public record Retry(
            int attempts,
            java.time.Duration delay) {
    }
}
```

Hãy mô tả giá trị của `properties.retry().attempts()`. Trong cấu hình đã cho, kết quả là `3`.

### Bài tập D: kiểm tra ý nghĩa bất biến

Xét:

```java
public record RegionProperties(List<String> regions) {
}
```

Câu hỏi: liệu caller có thể thay đổi nội dung một `ArrayList` đã truyền vào record không?

Có thể, vì record chỉ giữ tham chiếu tới danh sách. Hãy tạo bản sao phòng vệ bằng `List.copyOf` trong compact constructor và xét chính sách đối với `null`.

### Bài tập E: tìm lỗi đăng ký

Xem:

```java
@Component
@ConfigurationProperties(prefix = "report")
public record ReportProperties(int maxRecords) {
}
```

Câu hỏi: điều gì không phù hợp nếu mục đích là constructor binding?

`@Component` đăng ký bean bằng cơ chế thành phần thông thường. Hãy bỏ `@Component` và dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` để Spring Boot bind qua constructor theo cơ chế dành cho configuration properties.

### Bài tập F: xác định giá trị có hiệu lực

Tệp `application.yml`:

```yaml
worker:
  max-threads: 4
```

Tệp `application-prod.yml`:

```yaml
worker:
  max-threads: 10
```

Khởi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod --worker.max-threads=16
```

Record:

```java
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(int maxThreads) {
}
```

Giá trị cuối cùng là `16` trong tình huống thông thường: đối số dòng lệnh có độ ưu tiên cao hơn cấu hình từ file. Constructor binding không thay đổi quy tắc này.

## 26. Ghi nhớ

- **Constructor binding** dùng constructor để tạo đối tượng `@ConfigurationProperties` từ những thuộc tính đã được giải quyết, chuyển đổi kiểu.
- **Bất biến** giúp bean cấu hình giữ trạng thái ổn định sau khởi tạo; dùng trường `final`, không có setter hoặc Java `record`.
- Trong Spring Boot 3.x, lớp có một constructor có tham số hoặc record có canonical constructor thông thường thường **không cần khai báo `@ConstructorBinding`**. Nếu có nhiều constructor, dùng annotation trên constructor mong muốn.
- **Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`**. Không dùng `@Component` với kỳ vọng constructor binding sẽ chạy như cho một configuration-properties bean được đăng ký chuyên biệt.
- Các tham số constructor nhận giá trị cấu hình; service nhận **bean cấu hình** qua Spring dependency injection thông thường.
- `@DefaultValue` cung cấp giá trị dự phòng cho constructor binding, kể cả cách khai báo mặc định cho nhánh lồng nhau.
- Với cấu hình bắt buộc, nên dùng **Bean Validation** và/hoặc kiểm tra bất biến trong constructor để phát hiện lỗi ngay khi khởi động.
- Record là **bất biến nông**; collection hoặc đối tượng lồng nhau mutable vẫn cần được xử lý nếu muốn bất biến sâu.
- Việc liên kết bất biến không ảnh hưởng đến **thứ tự ưu tiên của nguồn** như YAML, profile, biến môi trường và đối số dòng lệnh.
- Bản thân constructor binding không tự làm mới bean khi tệp cấu hình thay đổi trong lúc chạy.
- Thiết kế nhóm cấu hình theo trách nhiệm và kiểm thử cả hợp đồng Java object lẫn hành vi binding sẽ giúp cấu hình dễ hiểu, an toàn và dễ bảo trì.
