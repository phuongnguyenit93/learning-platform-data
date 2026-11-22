# Tách cấu hình hạ tầng khỏi tham số nghiệp vụ

## 1. Vì sao cần tách hai nhóm cấu hình?

Một ứng dụng Spring Boot/Spring Cloud thường có nhiều loại giá trị thay đổi theo môi trường hoặc theo chính sách vận hành. Chúng có thể cùng xuất hiện trong `application.yml`, nhưng mục đích và người chịu trách nhiệm thay đổi chúng khác nhau.

**Cấu hình hạ tầng (infrastructure configuration)** mô tả ứng dụng kết nối và vận hành với môi trường bên ngoài như thế nào: địa chỉ dịch vụ, cổng, timeout, connection pool, registry, TLS, database, message broker và các giới hạn tài nguyên.

**Tham số nghiệp vụ (business parameters)** mô tả chính sách hoặc giới hạn mà nghiệp vụ áp dụng: ngưỡng miễn phí vận chuyển, tỷ lệ giảm giá tối đa, hạn mức giao dịch, số sản phẩm tối đa trong đơn hàng, thời gian giữ chỗ hoặc ngưỡng phê duyệt.

Ví dụ trong một ứng dụng thương mại điện tử:

| Nhóm | Ví dụ | Ai thường sở hữu thay đổi? | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| Hạ tầng | URL của pricing service, connect timeout, pool size, database endpoint | Platform/operations hoặc đội tích hợp | Ứng dụng kết nối và chịu tải ra sao? |
| Nghiệp vụ | Ngưỡng miễn phí giao hàng, giới hạn giảm giá, số lượng tối đa mỗi đơn | Product/business owner hoặc đội domain | Chính sách bán hàng hiện áp dụng thế nào? |
| Bí mật vận hành | Database password, API token, private key | Security/platform và hệ thống secret manager | Ai được cấp quyền đọc credential? |

Cả hai nhóm đều có thể được đưa vào Spring `Environment` và bind thành object có kiểu dữ liệu. Tuy nhiên, nếu đặt tất cả trong một class `AppProperties` hoặc rải `@Value` khắp service, ứng dụng sẽ khó xác định ai được phép đổi giá trị, thay đổi nào cần khởi động lại, và giá trị nào phải được kiểm tra theo quy tắc nghiệp vụ.

Mục tiêu của bài học trong **SPRING_CLOUD_CORE** là thiết kế cấu hình có cấu trúc, phân tách rõ trách nhiệm hạ tầng và chính sách nghiệp vụ, sau đó sử dụng Spring Boot `@ConfigurationProperties` cùng các cơ chế external configuration của Spring Cloud để quản lý chúng an toàn.

## 2. Nguyên tắc phân loại

Không nên phân loại chỉ dựa trên việc giá trị nằm trong file nào. Hãy xem **ý nghĩa của giá trị, người sở hữu, nhịp thay đổi và tác động khi thay đổi**.

### 2.1. Cấu hình hạ tầng

Các giá trị thường thuộc nhóm này:

- Hostname, URI và port của database, message broker, registry hoặc dịch vụ bên ngoài.
- Connect/read timeout, retry limit, connection pool size, thread pool size.
- Cấu hình TLS, đường dẫn certificate, proxy và network behavior.
- Service discovery, instance registration, load balancer và health check.
- Management endpoint, log level, metric export và giới hạn tài nguyên.

Nhóm này chủ yếu quyết định cách ứng dụng tích hợp với nền tảng. Thay đổi `server.port`, địa chỉ database hoặc discovery registry có thể yêu cầu restart, rollout hoặc tái tạo client. Không nên mặc định mọi thuộc tính hạ tầng đều an toàn để refresh khi ứng dụng đang chạy.

### 2.2. Tham số nghiệp vụ

Các giá trị thường thuộc nhóm này:

- Ngưỡng giá trị đơn hàng để được miễn phí vận chuyển.
- Tỷ lệ chiết khấu tối đa hoặc số tiền giảm tối đa.
- Số lượng mặt hàng tối đa cho một đơn.
- Thời gian giữ chỗ hoặc thời gian cho phép xác nhận đơn.
- Hạn mức giao dịch, số lần thử thao tác nghiệp vụ hoặc ngưỡng cần phê duyệt.

Chúng thể hiện chính sách có thể thay đổi theo thị trường, chiến dịch hoặc quyết định kinh doanh. Nên có tên rõ nghĩa, kiểu dữ liệu chính xác, validation và cơ chế kiểm soát thay đổi. Với các chính sách ảnh hưởng đến tính đúng đắn hoặc tài chính, có thể cần version, effective date, audit log và quy trình phê duyệt.

### 2.3. Bí mật không phải một nhóm nghiệp vụ

Password, token và private key là **secret**. Chúng có thể phục vụ hạ tầng hoặc tích hợp nghiệp vụ, nhưng cách lưu trữ và phân quyền phải được quản lý riêng. Không commit secret vào Git, không đưa vào Docker image, không ghi giá trị ra log và không expose chúng qua endpoint quản trị không được bảo vệ.

Các nguồn phù hợp có thể là Kubernetes Secret volume, Docker secrets, secret manager của nền tảng hoặc config tree của Spring Boot. Secret vẫn có thể bind vào typed configuration, nhưng quyền đọc và vòng đời xoay vòng cần được quản lý theo chính sách bảo mật.

## 3. Tổ chức namespace cấu hình

Dùng prefix rõ ràng giúp phân biệt cấu hình hạ tầng với tham số nghiệp vụ. Ví dụ:

```yaml
spring:
  application:
    name: order-service

  datasource:
    url: jdbc:postgresql://postgres:5432/orders
    username: order_app
    # Password được cấp từ secret store, không ghi ở đây.

  cloud:
    discovery:
      enabled: true

app:
  infrastructure:
    pricing-client:
      base-url: https://pricing.internal
      connect-timeout: 2s
      read-timeout: 5s
      max-connections: 40

  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 500000
      maximum-discount-rate: 0.20
      maximum-items-per-order: 30
```

Trong ví dụ:

- `spring.*` là namespace dành cho các tích hợp Spring Boot/Spring Cloud đã định nghĩa.
- `app.infrastructure.*` chứa các tham số kết nối và vận hành riêng của ứng dụng.
- `app.business.*` chứa các tham số chính sách nghiệp vụ của ứng dụng.
- Password database được cấp từ secret source riêng.

Không nên tự tạo property dưới `spring.*` nếu đó không phải namespace được Spring Boot hoặc Spring Cloud định nghĩa. Với cấu hình riêng của ứng dụng, dùng prefix do ứng dụng sở hữu, ví dụ `app.*`, `order.*` hoặc tên miền cụ thể.

Cấu trúc namespace không tự đảm bảo ranh giới kiến trúc. Điều quan trọng là class nhận cấu hình, người thay đổi, nguồn cung cấp và cách ứng dụng sử dụng giá trị phải phản ánh đúng ý nghĩa của prefix.

## 4. Dùng `@ConfigurationProperties` để bind cấu hình có kiểu dữ liệu

Spring Boot hỗ trợ hai cách phổ biến để đọc property:

- `@Value` phù hợp với một vài giá trị đơn giản tại một điểm sử dụng.
- `@ConfigurationProperties` phù hợp với một nhóm property có cấu trúc, cần relaxed binding, metadata và validation.

Với cấu hình hạ tầng và tham số nghiệp vụ, nên gom các key liên quan vào những class riêng thay vì inject từng key bằng `@Value` ở nhiều service.

### 4.1. Typed configuration cho hạ tầng

Ví dụ cấu hình client gọi pricing service:

```java
package com.example.order.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.infrastructure.pricing-client")
@Validated
public record PricingClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Positive int maxConnections
) {
}
```

Các trường có kiểu cụ thể:

- `URI` giúp phân tích địa chỉ và tránh xử lý URL như chuỗi tùy ý.
- `Duration` giúp biểu diễn timeout như `2s`, `500ms` hoặc `1m`.
- `int` cùng `@Positive` buộc số kết nối phải lớn hơn 0.
- `@NotNull` buộc địa chỉ và timeout phải được cung cấp.

Record phù hợp khi muốn object cấu hình bất biến sau khi khởi tạo. Với một constructor duy nhất, Spring Boot hiện đại có thể sử dụng constructor binding mà không cần thêm `@ConstructorBinding`. Loại cấu hình này phải được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, không dùng `@Component` để tự tạo record theo cơ chế component thông thường.

### 4.2. Typed configuration cho tham số nghiệp vụ

Ví dụ chính sách checkout:

```java
package com.example.order.config;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.business.checkout")
@Validated
public record CheckoutPolicyProperties(
        @NotBlank
        @Pattern(regexp = "[A-Z]{3}")
        String currencyCode,

        @NotNull
        @PositiveOrZero
        BigDecimal freeShippingThreshold,

        @NotNull
        @DecimalMin("0.0")
        @DecimalMax("1.0")
        BigDecimal maximumDiscountRate,

        @Positive
        int maximumItemsPerOrder
) {
}
```

Ví dụ này cho thấy cách validation bảo vệ chính sách:

- `currencyCode` phải có giá trị và có dạng mã tiền tệ ba chữ cái viết hoa.
- `freeShippingThreshold` không được âm.
- `maximumDiscountRate` nằm trong khoảng từ 0 đến 1.
- `maximumItemsPerOrder` phải lớn hơn 0.

Dùng `BigDecimal` cho tiền và tỷ lệ cần độ chính xác thập phân; tránh dùng `double` cho phép tính tài chính. Nếu cần bảo đảm mã tiền tệ tồn tại thực sự, có thể kiểm tra thêm bằng `Currency.getInstance(currencyCode)` trong factory hoặc custom validator. Regex chỉ kiểm tra hình dạng, không chứng minh mã đó được ISO công nhận.

### 4.3. Đăng ký typed configuration

Trên application class:

```java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Spring Boot quét các class `@ConfigurationProperties` trong package được chỉ định hoặc từ package của application class trở xuống. Nếu không muốn quét, có thể đăng ký tường minh:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
        PricingClientProperties.class,
        CheckoutPolicyProperties.class
})
public class PropertiesConfiguration {
}
```

Cần có implementation Jakarta Bean Validation trên classpath để các constraint như `@NotBlank`, `@Positive` và `@DecimalMax` được thực thi. Với Spring Boot, có thể thêm starter validation phù hợp với dòng phiên bản đang dùng. Ví dụ dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

## 5. Đưa cấu hình nghiệp vụ vào domain mà không kéo Spring vào domain

Một ranh giới quan trọng: class `@ConfigurationProperties` là adapter nhận dữ liệu từ môi trường triển khai. Domain model không nên phụ thuộc trực tiếp vào annotation Spring hoặc cách property được nạp.

Có thể chuyển typed configuration sang một đối tượng chính sách của domain:

```java
package com.example.order.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record CheckoutPolicy(
        Currency currency,
        BigDecimal freeShippingThreshold,
        BigDecimal maximumDiscountRate,
        int maximumItemsPerOrder
) {
    public CheckoutPolicy {
        Objects.requireNonNull(currency, "Currency is required");
        Objects.requireNonNull(freeShippingThreshold,
                "Free shipping threshold is required");
        Objects.requireNonNull(maximumDiscountRate,
                "Maximum discount rate is required");
        if (freeShippingThreshold.signum() < 0) {
            throw new IllegalArgumentException(
                    "Free shipping threshold must not be negative");
        }
        if (maximumDiscountRate.signum() < 0
                || maximumDiscountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "Maximum discount rate must be between 0 and 1");
        }
        if (maximumItemsPerOrder <= 0) {
            throw new IllegalArgumentException(
                    "Maximum items per order must be positive");
        }
    }
}
```

Tạo bean chuyển đổi ở lớp cấu hình/adapter:

```java
package com.example.order.config;

import java.util.Currency;

import com.example.order.domain.CheckoutPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutPolicyConfiguration {

    @Bean
    CheckoutPolicy checkoutPolicy(CheckoutPolicyProperties properties) {
        return new CheckoutPolicy(
                Currency.getInstance(properties.currencyCode()),
                properties.freeShippingThreshold(),
                properties.maximumDiscountRate(),
                properties.maximumItemsPerOrder()
        );
    }
}
```

Domain nhận một `CheckoutPolicy` đã được chuyển đổi, không cần biết giá trị đến từ YAML, biến môi trường, Config Server hay secret store. Điều này giúp kiểm thử domain độc lập và tránh làm các lớp nghiệp vụ phụ thuộc vào Spring Boot.

Nếu chính sách có nhiều phiên bản hoặc thời điểm hiệu lực, hãy mô hình hóa các thông tin đó trong domain policy thay vì chỉ thêm nhiều cờ boolean vào file YAML.

## 6. Cấu hình hạ tầng được sử dụng tại adapter

Typed infrastructure properties thường được inject vào component có trách nhiệm tạo client hoặc kết nối:

```java
package com.example.order.infrastructure.pricing;

import com.example.order.config.PricingClientProperties;
import org.springframework.stereotype.Component;

@Component
public class PricingEndpoint {

    private final PricingClientProperties properties;

    public PricingEndpoint(PricingClientProperties properties) {
        this.properties = properties;
    }

    public String baseUrl() {
        return properties.baseUrl().toString();
    }
}
```

Trong ứng dụng thực tế, bean cấu hình HTTP client sẽ dùng `connectTimeout`, `readTimeout` và `maxConnections` để tạo request factory hoặc connection pool phù hợp với HTTP client được chọn. Không nên đưa logic tính giá, miễn phí vận chuyển hoặc kiểm tra hạn mức vào class cấu hình HTTP này.

Tương tự, các thuộc tính như `spring.datasource.*`, `spring.cloud.discovery.*`, `management.*` thuộc cấu hình của các tích hợp hạ tầng. Hãy để Spring Boot/Spring Cloud auto-configuration tiêu thụ các property chuẩn đó; chỉ tạo prefix riêng khi ứng dụng có tham số đặc thù.

## 7. Nguồn cấu hình và cách override theo môi trường

Spring Boot cho phép externalize cấu hình để cùng một artifact chạy ở local, test, staging và production. Property có thể đến từ:

- File `application.yml` và file theo profile như `application-prod.yml`.
- File cấu hình bên ngoài image hoặc JAR.
- Biến môi trường của hệ điều hành.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Tham số command line.

Các nguồn có thứ tự ưu tiên. Trong các nguồn phổ biến, config data được nạp trước OS environment variables, Java system properties và command-line arguments; nguồn có ưu tiên cao hơn có thể ghi đè giá trị từ nguồn thấp hơn. Profile-specific config data ghi đè file cấu hình không gắn profile theo quy tắc của Spring Boot.

Ví dụ `application.yml` có giá trị mặc định:

```yaml
app:
  infrastructure:
    pricing-client:
      base-url: http://localhost:9090
      connect-timeout: 1s
      read-timeout: 3s
      max-connections: 10

  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 300000
      maximum-discount-rate: 0.15
      maximum-items-per-order: 20
```

`application-prod.yml` có thể thay cấu hình hạ tầng theo môi trường:

```yaml
app:
  infrastructure:
    pricing-client:
      base-url: https://pricing.internal
      connect-timeout: 2s
      read-timeout: 5s
      max-connections: 80
```

Tham số nghiệp vụ production có thể được cấp từ nguồn riêng có quy trình phê duyệt:

```yaml
app:
  business:
    checkout:
      currency-code: VND
      free-shipping-threshold: 500000
      maximum-discount-rate: 0.20
      maximum-items-per-order: 30
```

Trong production, không nhất thiết phải commit file chứa giá trị thật vào repository. Có thể dùng external config location, Config Server hoặc nguồn cấu hình được nền tảng quản lý. Điều quan trọng là biết source nào sở hữu từng key và kiểm tra giá trị cuối cùng sau khi áp dụng precedence.

### 7.1. Biến môi trường

Spring Boot relaxed binding hỗ trợ ánh xạ key dạng kebab-case sang tên biến môi trường. Ví dụ:

```bash
APP_INFRASTRUCTURE_PRICINGCLIENT_BASEURL=https://pricing.internal
APP_INFRASTRUCTURE_PRICINGCLIENT_CONNECTTIMEOUT=2s
APP_INFRASTRUCTURE_PRICINGCLIENT_READTIMEOUT=5s
APP_BUSINESS_CHECKOUT_CURRENCYCODE=VND
APP_BUSINESS_CHECKOUT_FREESHIPPINGTHRESHOLD=500000
APP_BUSINESS_CHECKOUT_MAXIMUMDISCOUNTRATE=0.20
APP_BUSINESS_CHECKOUT_MAXIMUMITEMSPERORDER=30
```

Quy tắc chuyển tên biến môi trường của Spring Boot thay dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa. Khi dùng danh sách hoặc map phức tạp, cần đối chiếu quy tắc relaxed binding chính thức; không tự suy đoán cách đặt tên.

### 7.2. Profile không nên trở thành nơi nhân bản chính sách

Profile phù hợp cho khác biệt môi trường, chẳng hạn endpoint, timeout, pool size và log level. Nếu một chính sách nghiệp vụ khác nhau theo quốc gia hoặc tenant, hãy cân nhắc nguồn policy riêng và mô hình hóa phạm vi áp dụng rõ ràng. Tránh tạo nhiều file profile gần như giống nhau chỉ để thay vài con số nghiệp vụ mà không có quy tắc sở hữu hoặc hiệu lực.

## 8. Kết hợp Spring Cloud Config và nguồn cấu hình ngoài

Khi nhiều service cần cùng một chính sách hoặc cấu hình theo môi trường, Spring Cloud Config Server có thể cung cấp property source tập trung. Client sử dụng dependency Config Client và Config Data import, ví dụ:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
```

Trong mô hình này, Config Server có thể quản lý các nhóm key riêng:

- `app.infrastructure.*` cho endpoint, timeout hoặc thông số kết nối.
- `app.business.*` cho chính sách checkout, giới hạn và ngưỡng nghiệp vụ.

Không nên gom cấu hình của nhiều service vào một file không phân biệt chủ sở hữu. Sử dụng application name, profile và label/version của Config Server để xác định service nào nhận bộ cấu hình nào.

Với secret, cân nhắc config tree hoặc secret manager thay vì lưu password và token trực tiếp trong Git-backed repository cấu hình. Config Server hỗ trợ nhiều cách backend và mã hóa, nhưng quyền truy cập, key management và quy trình rotation vẫn phải được thiết kế.

### 8.1. Phân tách theo nguồn cũng cần có quy tắc

Một property có thể được định nghĩa đồng thời trong `application.yml`, Config Server và biến môi trường. Hãy lập quy ước, ví dụ:

| Prefix | Nguồn mặc định | Nguồn override được phép | Người phê duyệt |
| --- | --- | --- | --- |
| `app.infrastructure.*` | Profile/config theo môi trường | Platform deployment variables hoặc Config Server | Platform/operations |
| `app.business.*` | Config Server hoặc policy repository | Quy trình thay đổi chính sách có audit | Product/domain owner |
| `spring.datasource.password` | Secret manager / mounted secret | Secret rotation workflow | Security/platform |

Bảng là ví dụ về governance, không phải quy tắc mặc định của Spring. Cần quyết định rõ giá trị nào được phép override và ở cấp nào. Khi một biến môi trường vô tình ghi đè tham số nghiệp vụ, ứng dụng có thể chạy với chính sách không được phê duyệt.

## 9. Validation: chặn cấu hình sai ngay khi khởi động

Validation không chỉ kiểm tra kiểu dữ liệu có parse được hay không. Nó còn kiểm tra **giá trị có nằm trong miền hợp lệ** hay không.

Ví dụ:

| Property | Kiểu | Validation gợi ý |
| --- | --- | --- |
| `connect-timeout` | `Duration` | `@NotNull`, custom constraint nếu cần phải dương |
| `max-connections` | `int` | `@Positive` |
| `currency-code` | `String` | `@NotBlank`, `@Pattern`, sau đó xác minh mã tiền tệ |
| `free-shipping-threshold` | `BigDecimal` | `@PositiveOrZero` |
| `maximum-discount-rate` | `BigDecimal` | `@DecimalMin("0.0")`, `@DecimalMax("1.0")` |
| `maximum-items-per-order` | `int` | `@Positive` |

Nếu có object lồng nhau, dùng `@Valid` để validation tiếp tục đi xuống object con. Các property bắt buộc nên có `@NotNull` hoặc `@NotBlank`; đừng cho rằng `@Valid` tự biến một object null thành object hợp lệ.

Khi một giá trị không hợp lệ, ứng dụng nên fail fast trong quá trình khởi tạo thay vì chạy một phần rồi phát sinh lỗi ở request đầu tiên. Ví dụ tỷ lệ giảm giá bằng `1.5` có thể tạo chính sách giảm 150% nếu không được kiểm tra.

Đối với quy tắc liên trường, ví dụ `minimum-order-value` không được lớn hơn `maximum-order-value`, có thể dùng class-level custom constraint hoặc kiểm tra trong constructor/factory tạo domain policy. Validation ở lớp cấu hình bảo vệ đầu vào; domain model vẫn nên bảo vệ invariant quan trọng của chính nó.

## 10. Chọn kiểu mutable hay immutable khi cần refresh runtime

Không phải mọi tham số đều cần đổi khi ứng dụng đang chạy. Hãy xác định vòng đời trước khi chọn kiểu cấu hình.

### 10.1. Immutable record cho cấu hình khởi tạo

Record constructor-bound phù hợp với cấu hình chỉ cần đọc khi khởi tạo, chẳng hạn:

- Endpoint và timeout của HTTP client.
- Port, TLS hoặc kết nối hạ tầng cần tạo lại client.
- Thông số pool hoặc datasource cần restart/rollout để thay đổi an toàn.

Ưu điểm là object bất biến, dễ truyền vào constructor và ít có trạng thái nửa cập nhật. Tuy nhiên, Spring Cloud Context không thể rebind các object dùng constructor binding, bao gồm Java record được annotate `@ConfigurationProperties`. Không chọn record nếu yêu cầu là cập nhật trực tiếp bean bằng cơ chế rebind `EnvironmentChangeEvent`.

### 10.2. Mutable JavaBean cho cấu hình cần rebind

Với nhóm tham số nghiệp vụ được phép thay đổi runtime, có thể dùng JavaBean-style `@ConfigurationProperties`:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.business.dynamic-checkout")
@Validated
public class DynamicCheckoutProperties {

    @DecimalMin("0.0")
    private BigDecimal freeShippingThreshold = BigDecimal.ZERO;

    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private BigDecimal maximumDiscountRate = BigDecimal.ZERO;

    @Positive
    private int maximumItemsPerOrder = 20;

    public BigDecimal getFreeShippingThreshold() {
        return freeShippingThreshold;
    }

    public void setFreeShippingThreshold(BigDecimal value) {
        this.freeShippingThreshold = value;
    }

    public BigDecimal getMaximumDiscountRate() {
        return maximumDiscountRate;
    }

    public void setMaximumDiscountRate(BigDecimal value) {
        this.maximumDiscountRate = value;
    }

    public int getMaximumItemsPerOrder() {
        return maximumItemsPerOrder;
    }

    public void setMaximumItemsPerOrder(int value) {
        this.maximumItemsPerOrder = value;
    }
}
```

Khi ứng dụng nhận `EnvironmentChangeEvent` với các key đã thay đổi, Spring Cloud Context có thể rebind các bean `@ConfigurationProperties` trong context. Các giá trị bị xóa khỏi Environment được reset về default của class trước khi rebind theo cơ chế được tài liệu mô tả.

Rebind mutable bean cập nhật field trên cùng instance. Nếu thread khác đọc object trong lúc rebind, nó có thể nhìn thấy trạng thái trung gian. Khi cần một góc nhìn nhất quán trong suốt refresh, cân nhắc `@RefreshScope` cho bean sử dụng policy hoặc thiết kế thay thế policy theo một lần swap nguyên tử.

### 10.3. `@RefreshScope` không phải giải pháp cho mọi cấu hình

`@RefreshScope` vô hiệu hóa cached target bean để target được tạo lại ở lần sử dụng tiếp theo sau refresh. Cơ chế này phù hợp với bean cần khởi tạo lại từ cấu hình mới, nhưng cần xem xét lifecycle và tài nguyên mà bean đang giữ.

Không nên giả định mọi bean phụ thuộc vào một bean `@RefreshScope` đều tự được tạo lại. Nếu một service đã giữ giá trị hoặc object được tạo từ policy cũ, nó có thể tiếp tục sử dụng object đó. Cần đặt scope ở đúng bean và kiểm thử luồng phụ thuộc.

Các giá trị như server port, database endpoint, certificate hoặc discovery client có thể không an toàn khi chỉ rebind field. Có trường hợp cần tạo lại connection pool, đóng connection cũ, cập nhật registration hoặc rollout process. Hãy xác định cách thay đổi thực tế thay vì coi refresh là thao tác thay YAML.

## 11. Phát tán thay đổi đến các instance

Spring Cloud Config Client không tự polling Config Server để phát hiện mọi thay đổi theo mặc định. Khi một ứng dụng có nhiều instance, chỉ thay đổi cấu hình ở server không đảm bảo mọi JVM đã nhận giá trị mới.

Một quy trình thay đổi tham số nghiệp vụ có thể gồm:

1. Product/domain owner duyệt policy mới.
2. Cập nhật cấu hình có version hoặc audit record trong nguồn được quản lý.
3. Client nhận tín hiệu refresh hoặc được rollout theo chiến lược triển khai.
4. Mỗi instance cập nhật Environment và phát sự kiện cần thiết.
5. Typed configuration được rebind hoặc bean refresh target được tạo lại.
6. Metrics/log không nhạy cảm xác nhận version policy đã áp dụng trên từng instance.

Spring Cloud Bus có thể broadcast sự kiện thay đổi môi trường đến nhiều instance. Nếu không dùng Bus, có thể điều phối refresh qua deployment platform hoặc một cơ chế sự kiện khác. Điều quan trọng là xác nhận tất cả instance đã áp dụng cùng policy version trước khi kết thúc rollout.

Đối với chính sách tài chính hoặc giới hạn giao dịch, cân nhắc lưu `policy-version` và thời điểm hiệu lực. Nếu request đang xử lý khi policy đổi, cần quyết định request đó dùng version cũ hay mới. `@RefreshScope` không tự giải quyết yêu cầu nhất quán nghiệp vụ giữa nhiều request hoặc nhiều service.

## 12. Kiểm thử cấu hình theo hai nhóm

Kiểm thử cần chứng minh cả việc bind đúng lẫn validation và hành vi thay đổi.

### 12.1. Kiểm tra binding

Ví dụ dùng Spring Boot test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.business.checkout.currency-code=VND",
        "app.business.checkout.free-shipping-threshold=500000",
        "app.business.checkout.maximum-discount-rate=0.20",
        "app.business.checkout.maximum-items-per-order=30"
})
class CheckoutPolicyPropertiesTest {

    @Autowired
    CheckoutPolicyProperties properties;

    @Test
    void bindsBusinessPolicyWithExpectedTypes() {
        assertThat(properties.currencyCode()).isEqualTo("VND");
        assertThat(properties.freeShippingThreshold())
                .isEqualByComparingTo("500000");
        assertThat(properties.maximumDiscountRate())
                .isEqualByComparingTo("0.20");
        assertThat(properties.maximumItemsPerOrder()).isEqualTo(30);
    }
}
```

Test trên xác nhận property được bind thành đúng kiểu và giá trị. Cần có dependency test phù hợp, ví dụ `spring-boot-starter-test`.

### 12.2. Kiểm tra validation

Tạo test với giá trị không hợp lệ, chẳng hạn `maximum-discount-rate=1.5` hoặc `maximum-items-per-order=0`, rồi xác nhận application context không khởi động thành công. Việc này giúp phát hiện sai cấu hình ngay trong CI thay vì đợi đến production.

### 12.3. Kiểm tra ranh giới trách nhiệm

Ngoài kiểm thử binding, nên xác minh:

- Thay `pricing-client.base-url` không làm thay đổi policy giảm giá.
- Thay `free-shipping-threshold` không tạo lại HTTP connection pool.
- Domain policy có thể được unit test mà không cần Spring context.
- Secret không xuất hiện trong log, assertion message hoặc test report.
- Nếu policy được refresh, mọi instance cần có cùng policy version sau khi rollout/broadcast hoàn tất.

## 13. Quan sát và vận hành

Actuator `configprops` có thể giúp xem các bean `@ConfigurationProperties`; endpoint `env` có thể giúp xác định nguồn của property. Các endpoint này cần được bảo vệ bằng authentication, authorization và exposure policy phù hợp vì metadata hoặc giá trị cấu hình có thể nhạy cảm.

Một số nguyên tắc vận hành:

- Ghi log tên property source, profile và policy version; không ghi password/token.
- Phân biệt cấu hình mong muốn trong Config Server với cấu hình thực tế đã được từng instance resolve.
- Có alert khi validation hoặc bind thất bại khiến instance không khởi động.
- Theo dõi lỗi kết nối hạ tầng riêng với lỗi vi phạm chính sách nghiệp vụ.
- Với tham số nghiệp vụ, lưu dấu thay đổi và người phê duyệt ở hệ thống quản lý policy.
- Với hạ tầng, ghi nhận rollout/restart và kiểm tra kết nối sau khi cấu hình mới được áp dụng.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Đưa endpoint, timeout và mức giảm giá vào một class `AppProperties` | Trách nhiệm và quyền thay đổi bị trộn lẫn | Tách prefix và typed configuration theo nhóm |
| Rải `@Value` trong nhiều service | Khó kiểm tra đầy đủ cấu hình, thiếu metadata và validation tập trung | Gom nhóm property bằng `@ConfigurationProperties` |
| Dùng `double` cho tiền hoặc tỷ lệ tài chính | Sai số thập phân | Dùng `BigDecimal` và quy tắc làm tròn rõ ràng |
| Không validation tham số nghiệp vụ | Chính sách sai vẫn được nạp và sử dụng | Dùng Jakarta Validation và kiểm tra invariant trong domain |
| Đặt password trong `application-prod.yml` commit vào Git | Rò rỉ secret và khó rotation | Dùng secret manager hoặc config tree |
| Nghĩ mọi thay đổi Config Server tự đến mọi instance | Các instance chạy với policy khác nhau | Dùng refresh event, Bus hoặc rollout có xác nhận |
| Dùng record cho property cần Spring Cloud rebind | Record constructor-bound không được refresh/rebind theo cơ chế đó | Dùng mutable JavaBean hoặc thiết kế refresh bean phù hợp |
| Refresh mọi thuộc tính hạ tầng mà không kiểm tra lifecycle | Client, pool hoặc registration có thể giữ tài nguyên cũ | Phân loại restart-required và runtime-refreshable |
| Để domain phụ thuộc trực tiếp `@ConfigurationProperties` | Domain bị gắn với framework và nguồn cấu hình | Chuyển đổi sang domain policy/value object ở lớp adapter |

## 15. Quy trình thiết kế áp dụng cho một service mới

1. Liệt kê các property service đang sử dụng.
2. Phân loại từng key thành hạ tầng, nghiệp vụ hoặc secret.
3. Chọn prefix theo trách nhiệm và thống nhất tên canonical dạng kebab-case.
4. Chọn kiểu dữ liệu phù hợp: `Duration`, `URI`, `BigDecimal`, `int`, enum hoặc value object.
5. Gom nhóm thành các `@ConfigurationProperties` class độc lập.
6. Thêm validation cho required fields, miền giá trị và invariant liên trường.
7. Chọn record immutable cho cấu hình khởi tạo; chọn mutable bean khi có yêu cầu rebind được hỗ trợ.
8. Quy định nguồn cấu hình, precedence, owner, quyền override và audit.
9. Tách domain policy khỏi Spring configuration adapter.
10. Kiểm thử binding, validation, refresh/restart và xác nhận cấu hình trên từng instance.

## 16. Câu hỏi tự kiểm tra

1. Vì sao URL của pricing service thuộc cấu hình hạ tầng nhưng ngưỡng miễn phí vận chuyển thuộc tham số nghiệp vụ?
2. Khi nào nên dùng `@Value`, khi nào nên dùng `@ConfigurationProperties`?
3. Vì sao nên dùng `BigDecimal` cho tiền và tỷ lệ chiết khấu?
4. `@Validated` và các constraint Jakarta Validation giúp phát hiện lỗi cấu hình ở thời điểm nào?
5. Vì sao domain model không nên phụ thuộc trực tiếp vào annotation Spring?
6. Record constructor-bound khác JavaBean-style configuration properties ở khả năng rebind ra sao?
7. Vì sao thay đổi Config Server không đảm bảo mọi instance đã nhận policy mới?
8. Khi nào nên restart/rollout thay vì dùng `@RefreshScope`?
9. Cần quản lý version và audit như thế nào với tham số ảnh hưởng đến giao dịch?

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — nguồn cấu hình, `@ConfigurationProperties`, constructor binding, validation và property precedence.
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html) — metadata và hỗ trợ IDE cho cấu hình tùy chỉnh.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html) — `EnvironmentChangeEvent`, rebind `@ConfigurationProperties`, `@RefreshScope` và giới hạn refresh.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html) — nạp cấu hình từ Config Server bằng Config Data.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html) — tích hợp Jakarta Bean Validation.

*Tài liệu tập trung vào ranh giới giữa cấu hình hạ tầng và tham số nghiệp vụ. Các quyết định refresh, restart, phân quyền và audit phải được xác định theo yêu cầu của từng service và phiên bản Spring Boot/Spring Cloud thực tế.*
