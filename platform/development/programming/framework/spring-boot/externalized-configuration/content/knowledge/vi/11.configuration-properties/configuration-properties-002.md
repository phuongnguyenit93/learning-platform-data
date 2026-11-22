# Thiết kế prefix theo miền chức năng và quy tắc đặt tên chuẩn

## 1. Vì sao phải thiết kế prefix có chủ đích?

Spring Boot cho phép tách cấu hình khỏi mã nguồn, đồng thời ánh xạ những property bên ngoài thành đối tượng Java thông qua **@ConfigurationProperties**. Tuy nhiên, việc ánh xạ đúng kiểu chỉ giải quyết một nửa vấn đề. Nửa còn lại là **thiết kế tên và ranh giới cấu hình sao cho dễ hiểu, ít xung đột và ổn định qua nhiều lần triển khai**.

Trong một ứng dụng nhỏ, các key như **app.url**, **app.timeout**, **app.enabled** có vẻ tiện lợi. Khi ứng dụng có thanh toán, vận chuyển, email, tìm kiếm và nhiều kết nối bên ngoài, những tên này trở nên mơ hồ: URL của dịch vụ nào? Timeout của request hay kết nối? Enabled của chức năng nào?

Một cấu trúc dễ quản lý hơn:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.provider-url
shop.checkout.shipping.request-timeout
shop.notifications.email.enabled
shop.catalog.search.default-page-size
~~~

Bài này giải thích:

- Prefix biểu diễn gì và liên hệ thế nào với các miền nghiệp vụ.
- Quy tắc **lowercase kebab-case**, dấu chấm **.**, dấu gạch ngang **-** và tên canonical.
- Khi nào tách một nhóm thành lớp **@ConfigurationProperties** riêng hoặc dùng nested object.
- Cách tên trong YAML, **.properties**, Java và biến môi trường ánh xạ vào nhau.
- Cách đăng ký type, validation, metadata, kiểm thử và quản lý tương thích khi đổi tên.
- Những lỗi thường gặp khi thiết kế prefix và cách phòng tránh.

Ví dụ dựa trên **Spring Boot 3.3.x** và Java 21. Các địa chỉ **example.invalid** chỉ để minh họa; không phải dịch vụ thật.

## 2. Prefix, segment và tên field

Ví dụ đường property:

~~~text
shop.checkout.payment.connect-timeout
|-------------------| |-------------|
        prefix          field name
~~~

Lớp cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(Duration connectTimeout) {
}
~~~

Khi lớp này được đăng ký đúng cách, Spring Boot bind key **shop.checkout.payment.connect-timeout** vào trường Java **connectTimeout**.

Các thành phần có ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| **shop** | Namespace gốc của ứng dụng hoặc hệ thống |
| **checkout** | Miền nghiệp vụ thanh toán đơn hàng |
| **payment** | Nhóm cấu hình tích hợp thanh toán |
| **connect-timeout** | Thuộc tính cụ thể, có thể bind sang kiểu **Duration** |

**Prefix** không bắt buộc phải trùng tên Java package, tên module Gradle hoặc tên class. Nó là một phần của **giao diện cấu hình bên ngoài** mà người vận hành, pipeline CI/CD và các manifest triển khai cùng sử dụng.

Nếu sau này chuyển package từ **com.example.shop.payment** sang **com.example.payments**, không nhất thiết phải đổi prefix; đổi tên cấu hình có thể làm hỏng những biến môi trường và file cấu hình đang sử dụng.

## 3. Quy tắc canonical: lowercase kebab-case

Spring Boot khuyến nghị viết các key trong file **.properties** và YAML theo **lowercase kebab-case**. Đối với giá trị **prefix** trong annotation **@ConfigurationProperties**, tên **phải** tuân theo kebab-case: chữ thường và dùng dấu **-** để ngăn cách các từ trong cùng segment.

Ví dụ prefix hợp lệ:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
@ConfigurationProperties(prefix = "shop.order-processing")
@ConfigurationProperties(prefix = "my.main-project.person")
~~~

Phân biệt:

- Dấu chấm **.** tách **các cấp** của đường property.
- Dấu gạch ngang **-** tách **các từ trong một cấp**.
- Chữ thường làm dạng canonical ổn định và dễ tra cứu.
- Cách viết Java camelCase vẫn phù hợp cho **tên field Java**, vì Binder có cơ chế relaxed binding.

Những tên không nên chọn làm prefix:

~~~text
Shop.Checkout.Payment       -- chữ hoa
shop.checkoutPayment       -- camelCase trong prefix
shop_checkout_payment      -- không phân cấp bằng dấu chấm
shop.PaymentGateway        -- chữ hoa và camelCase
~~~

Đổi sang một trong hai dạng sau tùy ý nghĩa:

~~~text
shop.checkout-payment      -- một segment là checkout-payment
shop.checkout.payment      -- hai segment checkout và payment
~~~

**Dấu chấm và dấu gạch ngang không hoán đổi tùy tiện.** **order-processing** là một khái niệm trong một segment, còn **order.processing** biểu diễn một cấu trúc phân cấp khác.

### 3.1. Bảng ví dụ tên chuẩn

| Nhu cầu | Property canonical | Java field |
| --- | --- | --- |
| URL thanh toán | **shop.checkout.payment.base-url** | **baseUrl** |
| Timeout kết nối | **shop.checkout.payment.connect-timeout** | **connectTimeout** |
| Số lần thử lại | **shop.checkout.payment.retry.max-attempts** | **maxAttempts** |
| Có bật giao hàng | **shop.checkout.shipping.enabled** | **enabled** |
| Timeout request | **shop.checkout.shipping.request-timeout** | **requestTimeout** |
| Cỡ trang tìm kiếm | **shop.catalog.search.default-page-size** | **defaultPageSize** |
| Địa chỉ email phản hồi | **shop.notifications.email.reply-to-address** | **replyToAddress** |

Nên dùng một cách viết chính thức trong tài liệu và file cấu hình. Relaxed binding giúp nhận các biến thể cú pháp; nó không có nghĩa mọi người nên viết một kiểu khác nhau.

## 4. Phân chia theo miền chức năng, không theo sự tiện tay

Một ví dụ cây cấu hình cho ứng dụng bán hàng:

~~~text
shop
├── checkout
│   ├── payment
│   │   ├── base-url
│   │   ├── connect-timeout
│   │   └── retry
│   │       ├── max-attempts
│   │       └── initial-delay
│   └── shipping
│       ├── provider-url
│       ├── enabled
│       └── request-timeout
├── catalog
│   ├── search
│   └── inventory
└── notifications
    ├── email
    └── sms
~~~

Một nhóm property nên cùng phục vụ **một trách nhiệm** hoặc một subsystem được quản lý như một đơn vị:

- Payment client sở hữu **shop.checkout.payment**.
- Shipping integration sở hữu **shop.checkout.shipping**.
- Search module sở hữu **shop.catalog.search**.
- Email notification sở hữu **shop.notifications.email**.

Nếu có hai tích hợp cùng dùng trường **timeout**, vẫn nên để chúng dưới hai nhánh riêng:

~~~text
shop.checkout.payment.connect-timeout
shop.checkout.shipping.request-timeout
~~~

Không đặt vào **app.timeout** chỉ vì cả hai có cùng kiểu dữ liệu.

### 4.1. Tránh prefix quá rộng

~~~text
app.url
app.timeout
app.enabled
app.mode
app.options
~~~

Những key trên không tự mô tả domain. Khi đổi một biến **APP_TIMEOUT** trong container, người triển khai không biết chức năng nào sẽ bị tác động.

### 4.2. Tránh prefix quá sâu

~~~text
shop.department.checkout.adapters.remote.payment.http-client.connection.settings.timeout
~~~

Đường tên quá dài, nhiều cấp không mang giá trị nghiệp vụ. Prefix cần diễn tả **API cấu hình**, không nhất thiết sao chép toàn bộ cây package hoặc lớp adapter trong code.

Một cấu trúc ngắn hơn:

~~~text
shop.checkout.payment.connect-timeout
~~~

Độ sâu bao nhiêu là hợp lý tùy quy mô dự án. Không có quy tắc Spring Boot bắt buộc đúng ba segment. Hãy ưu tiên **ý nghĩa rõ ràng**, ranh giới sở hữu và sự ổn định.

### 4.3. Không gắn chặt prefix với cơ cấu tổ chức

Một tên có chứa đầy đủ department/team có thể phải đổi khi tổ chức thay đổi. Domain như **payment**, **shipping**, **catalog** thường bền hơn tên nhóm nhân sự. Chỉ đưa tên tổ chức vào namespace nếu nó có ý nghĩa kỹ thuật/nhận diện lâu dài.

## 5. Giữ namespace ứng dụng khác namespace framework

Spring Boot và các thư viện đã có các prefix riêng:

~~~text
spring.*
server.*
management.*
logging.*
~~~

Ví dụ **spring.datasource.url**, **server.port** hoặc **management.endpoints.web.exposure.include** là các key có ý nghĩa framework.

Không nên tạo key nghiệp vụ như:

~~~properties
spring.payment-timeout=5s
server.checkout-mode=fast
management.shipping-enabled=true
~~~

vì dễ làm người đọc nhầm với property framework và tăng nguy cơ xung đột khi nâng cấp thư viện.

Dùng namespace riêng:

~~~properties
shop.checkout.payment.connect-timeout=5s
shop.checkout.mode=fast
shop.checkout.shipping.enabled=true
~~~

Một thư viện nội bộ có thể chọn prefix riêng, chẳng hạn **acme.notification-client**. Nếu cần dùng thư viện này trong nhiều ứng dụng, giữ prefix ổn định và không trùng với namespace của ứng dụng tiêu thụ.

Ngược lại, không cần copy các key tiêu chuẩn của Spring thành bản “tùy biến” trùng ý nghĩa. Ví dụ nếu chỉ muốn cấu hình Hikari pool, nên cân nhắc dùng trực tiếp **spring.datasource.hikari.maximum-pool-size** thay vì tạo một alias **shop.database.pool-size** không có giá trị bổ sung.

## 6. Ví dụ Java: hai @ConfigurationProperties theo hai domain

Giả sử dự án dùng Java 21, Spring Boot 3.3 và dependency **spring-boot-starter-web**.

Cấu trúc mã:

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   ├── PaymentProperties.java
│   └── ShippingProperties.java
└── api/
    └── SettingsController.java
~~~

### 6.1. PaymentProperties

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Tên được bind:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.payment.retry.initial-delay
~~~

**retry** thuộc group payment; ở ví dụ này chưa cần một **@ConfigurationProperties** class độc lập. Nested record là cách thể hiện cấu trúc phù hợp.

### 6.2. ShippingProperties

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.checkout.shipping")
public record ShippingProperties(
        URI providerUrl,
        boolean enabled,
        Duration requestTimeout) {
}
~~~

Tên được bind:

~~~text
shop.checkout.shipping.provider-url
shop.checkout.shipping.enabled
shop.checkout.shipping.request-timeout
~~~

Việc tách hai record giúp logic payment và shipping phụ thuộc vào đúng contract cấu hình của mình.

### 6.3. Đăng ký configuration properties scanning

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi **ShopApplication** ở package **com.example.shop**, scanning mặc định có thể tìm các class nằm trong các package con như **com.example.shop.config**.

Spring Boot có thể bind các **record** thông qua constructor khi chúng được đăng ký bởi **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**. Không thêm **@Component** vào record rồi cho rằng Spring sẽ tự suy ra cơ chế constructor binding cho các tham số cấu hình.

### 6.4. Đăng ký tường minh thay cho scanning

Một phương án khác, phù hợp với module thư viện hoặc auto-configuration, là:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({
    PaymentProperties.class,
    ShippingProperties.class
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Đây là **phương án thay thế** cho **@ConfigurationPropertiesScan** trong ví dụ, không phải yêu cầu dùng cả hai cùng lúc.

## 7. Cấu hình YAML tương ứng

**src/main/resources/application.yml**:

~~~yaml
shop:
  checkout:
    payment:
      base-url: "https://payments.example.invalid"
      connect-timeout: 3s
      retry:
        max-attempts: 3
        initial-delay: 250ms

    shipping:
      provider-url: "https://shipping.example.invalid"
      enabled: true
      request-timeout: 5s
~~~

Cấu trúc này khớp với các record Java:

- **shop.checkout.payment** nhận **baseUrl**, **connectTimeout**, **retry**.
- **shop.checkout.shipping** nhận **providerUrl**, **enabled**, **requestTimeout**.
- Các giá trị **3s**, **250ms** và **5s** có thể được binder chuyển thành **Duration**.
- Các URL là dữ liệu giả, không cần kết nối tới endpoint.

Phiên bản **application.properties** tương đương:

~~~properties
shop.checkout.payment.base-url=https://payments.example.invalid
shop.checkout.payment.connect-timeout=3s
shop.checkout.payment.retry.max-attempts=3
shop.checkout.payment.retry.initial-delay=250ms

shop.checkout.shipping.provider-url=https://shipping.example.invalid
shop.checkout.shipping.enabled=true
shop.checkout.shipping.request-timeout=5s
~~~

Khi YAML được Spring Boot flatten thành property paths, prefix và tên canonical không thay đổi. Hãy ưu tiên một định dạng cấu hình nhất quán trong ứng dụng để tránh xung đột không cần thiết giữa các file cùng tên khác định dạng.

## 8. Sử dụng hai group từ code nghiệp vụ

Một controller minh họa:

~~~java
package com.example.shop.api;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SettingsController {

    private final PaymentProperties payment;
    private final ShippingProperties shipping;

    public SettingsController(
            PaymentProperties payment,
            ShippingProperties shipping) {
        this.payment = payment;
        this.shipping = shipping;
    }

    @GetMapping("/demo/settings")
    public Map<String, Object> settings() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("paymentBaseUrl", payment.baseUrl().toString());
        result.put("paymentConnectTimeoutMs",
                payment.connectTimeout().toMillis());
        result.put("paymentRetryCount", payment.retry().maxAttempts());
        result.put("shippingEnabled", shipping.enabled());
        result.put("shippingTimeoutMs",
                shipping.requestTimeout().toMillis());
        return result;
    }
}
~~~

Khi ứng dụng chạy với YAML trên, response minh họa:

~~~json
{
  "paymentBaseUrl": "https://payments.example.invalid",
  "paymentConnectTimeoutMs": 3000,
  "paymentRetryCount": 3,
  "shippingEnabled": true,
  "shippingTimeoutMs": 5000
}
~~~

API này chỉ dùng các giá trị giả không nhạy cảm để minh họa. Trong ứng dụng thật, **không nên công khai endpoint hiển thị cấu hình nội bộ, token hoặc credential**.

Điều cần chú ý: controller không cần biết property đến từ YAML hay biến môi trường. Nó chỉ phụ thuộc vào các object cấu hình có tên và kiểu rõ ràng.

## 9. Relaxed binding và biến môi trường

Spring Boot hỗ trợ **relaxed binding**, vì tên Java field thường dùng camelCase nhưng tên property canonical dùng kebab-case.

Ví dụ ba dạng trong file properties có thể bind cùng trường Java **connectTimeout**:

~~~properties
shop.checkout.payment.connect-timeout=3s
shop.checkout.payment.connectTimeout=3s
shop.checkout.payment.connect_timeout=3s
~~~

Nên **chọn dạng canonical** đầu tiên trong mã, tài liệu và ví dụ.

### 9.1. Quy tắc đổi sang biến môi trường

Để đổi từ tên canonical sang env:

1. Thay dấu chấm **.** thành dấu gạch dưới **_**.
2. Bỏ dấu gạch ngang **-** trong từng segment.
3. Chuyển toàn bộ chữ cái thành chữ hoa.

| Canonical | Environment |
| --- | --- |
| **shop.checkout.payment.base-url** | **SHOP_CHECKOUT_PAYMENT_BASEURL** |
| **shop.checkout.payment.connect-timeout** | **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT** |
| **shop.checkout.payment.retry.max-attempts** | **SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS** |
| **shop.checkout.payment.retry.initial-delay** | **SHOP_CHECKOUT_PAYMENT_RETRY_INITIALDELAY** |
| **shop.checkout.shipping.provider-url** | **SHOP_CHECKOUT_SHIPPING_PROVIDERURL** |
| **shop.checkout.shipping.enabled** | **SHOP_CHECKOUT_SHIPPING_ENABLED** |
| **shop.checkout.shipping.request-timeout** | **SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT** |

Ví dụ **connect-timeout** chuyển thành **CONNECTTIMEOUT**, không phải tự động thành **CONNECT_TIMEOUT**. Đây là điểm dễ nhầm giữa cách viết key canonical với cách đặt tên env.

### 9.2. Ví dụ ghi đè khi chạy

Trong Bash:

~~~bash
SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT=8s java -jar shop.jar
~~~

Trong PowerShell:

~~~powershell
$env:SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT = "8s"
java -jar shop.jar
~~~

Khi ứng dụng được khởi động với env thích hợp và không có nguồn ưu tiên cao hơn ghi đè key, **PaymentProperties.connectTimeout()** nhận Duration 8 giây thay vì 3 giây trong YAML.

Prefix rõ ràng khiến operator dễ biết biến môi trường này thuộc nhóm payment; không cần sửa JAR để đổi giá trị theo môi trường.

### 9.3. Phát hiện tên có khả năng va chạm

Vì dấu gạch ngang bị xóa khi chuyển sang tên env, hai property sau cùng tạo ra một tên:

~~~text
app.rate-limit -> APP_RATELIMIT
app.ratelimit  -> APP_RATELIMIT
~~~

Tránh tạo hai key khác nhau chỉ khác vị trí dấu gạch ngang. Hãy quy định một tên canonical và giữ nhất quán ở tất cả các nguồn.

## 10. Nested object hay một @ConfigurationProperties mới?

Trong PaymentProperties, nhóm **retry** được khai báo thành nested record:

~~~java
public record Retry(int maxAttempts, Duration initialDelay) {
}
~~~

Nó phù hợp vì retry policy là một phần cấu hình riêng của payment client.

Nên **tách thành một configuration properties class riêng** khi:

- Một nhóm có trách nhiệm khác rõ ràng.
- Có owner hoặc chu kỳ thay đổi độc lập.
- Được nhiều component tham chiếu như một contract riêng.
- Có quy tắc validation, metadata hoặc default riêng đáng kể.

Nên **giữ nested object** khi:

- Các trường chỉ có ý nghĩa bên trong cùng một subsystem.
- Không có lý do vận hành cho một namespace độc lập.
- Việc tách sẽ sinh ra quá nhiều class nhỏ và prefix khó đọc.

Một cấu trúc như **shop.checkout.payment.retry.max-attempts** có thể hợp lý mà không cần thêm annotation prefix **shop.checkout.payment.retry** ở type riêng.

Nếu cùng khái niệm retry được nhiều integration dùng, cần quyết định có **chia sẻ một chính sách thật sự** hay chỉ là các field giống tên. Đừng tạo một **global.timeout** vì nhiều component tình cờ cùng cần timeout.

## 11. Kiểu giá trị và cách đặt tên

Một tên tốt thể hiện ý nghĩa, trong khi kiểu Java thể hiện hợp đồng của giá trị.

Ví dụ:

~~~yaml
shop:
  checkout:
    payment:
      connect-timeout: 3s
      retry:
        max-attempts: 3
        initial-delay: 250ms
~~~

Nên dùng **Duration** thay vì **String** nếu đây là thời gian. Có thể dùng **URI** cho endpoint hoặc **boolean** cho flag. Binder hỗ trợ chuyển đổi các giá trị phù hợp.

Các trường **timeout1**, **timeout2**, **option3** thiếu ý nghĩa. Đặt **connect-timeout**, **read-timeout**, **request-timeout** theo mục đích thực tế.

**Giá trị mặc định** có thể được cấu hình trong **application.yml** hoặc đặt bằng cơ chế constructor binding phù hợp, như **@DefaultValue**:

~~~java
package com.example.shop.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentTimeoutOnly(
        @DefaultValue("3s") Duration connectTimeout) {
}
~~~

Đây là **một type minh họa thay thế**, không phải yêu cầu đăng ký cùng lúc với PaymentProperties đầy đủ có cùng prefix.

Dùng default một cách rõ ràng: một timeout hợp lý có thể có default; URL bắt buộc hoặc secret không nên âm thầm lấy giá trị giả trong môi trường production.

## 12. Validation đi cùng một ranh giới prefix

Đối với cấu hình thiết yếu, Spring Boot hỗ trợ Bean Validation khi có **spring-boot-starter-validation**.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ví dụ phiên bản properties có validation:

~~~java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.checkout.payment")
public record ValidatedPaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration initialDelay) {
    }
}
~~~

**ValidatedPaymentProperties** là ví dụ thay thế cho **PaymentProperties**. Trong dự án bài tập, chỉ đăng ký một trong hai type có cùng prefix.

Với validation, thiếu **base-url** hoặc đặt **retry.max-attempts=0** có thể dẫn đến lỗi rõ ràng khi khởi tạo, thay vì lỗi muộn trong một request thực tế. Đường property đầy đủ như **shop.checkout.payment.retry.max-attempts** giúp người triển khai xác định đúng nhóm cần sửa.

**@Valid** chỉ ra rằng Bean Validation nên đi sâu vào nested object. Prefix tốt giúp thông báo lỗi mang ngữ cảnh, nhưng không thay thế quy tắc validation.

## 13. Configuration metadata và hỗ trợ IDE

Spring Boot có **configuration metadata** giúp IDE đề xuất tên property, kiểu dữ liệu và mô tả khi người dùng chỉnh **application.yml** hoặc **application.properties**.

Nếu muốn sinh metadata cho những type **@ConfigurationProperties** tự định nghĩa, thêm **spring-boot-configuration-processor** theo cơ chế annotation processing của dự án.

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Maven (một cách khai báo thông dụng):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Trong một build cấu hình annotation processor riêng, cần bảo đảm processor thật sự được compiler sử dụng.

Metadata thường nằm trong **META-INF/spring-configuration-metadata.json** của output, có thể mô tả các key:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.provider-url
shop.checkout.shipping.enabled
~~~

Nó có ích khi module hoặc starter được chia sẻ cho nhiều ứng dụng: người dùng có thể khám phá các key có sẵn theo prefix của module.

Metadata **không tự đăng ký bean** và **không thay thế runtime binding**. Vẫn phải dùng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties** phù hợp.

Trong tài liệu của từng nhóm, nên ghi rõ mục đích, kiểu, đơn vị, giá trị mặc định, mức độ bắt buộc và cách cấp trong environment.

## 14. Prefix là hợp đồng cấu hình với hệ thống triển khai

Một property không chỉ xuất hiện trong source code. Nó có thể được ghi trong:

- File Config Data bên ngoài JAR.
- Docker Compose và Docker run environment.
- Kubernetes ConfigMap, Secret, Deployment.
- Helm values và template.
- Pipeline CI/CD.
- Script PowerShell/Bash.
- Công cụ quản lý cấu hình và tài liệu vận hành.

Ví dụ Docker Compose:

~~~yaml
services:
  shop:
    image: example/shop:1.0.0
    environment:
      SHOP_CHECKOUT_PAYMENT_BASEURL: "https://payments.example.invalid"
      SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT: "7s"
      SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS: "4"
      SHOP_CHECKOUT_PAYMENT_RETRY_INITIALDELAY: "500ms"
      SHOP_CHECKOUT_SHIPPING_PROVIDERURL: "https://shipping.example.invalid"
      SHOP_CHECKOUT_SHIPPING_ENABLED: "true"
      SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT: "6s"
~~~

Các key trên là biến môi trường thực được truyền vào container. Spring Boot sử dụng chúng khi bind theo prefix. Cách nhóm theo tên giúp quan sát nhanh phần nào là payment, phần nào là shipping.

Đoạn Kubernetes trong Pod template có thể là:

~~~yaml
containers:
  - name: shop
    image: example/shop:1.0.0
    env:
      - name: SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT
        value: "7s"
      - name: SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS
        value: "4"
      - name: SHOP_CHECKOUT_SHIPPING_ENABLED
        value: "true"
~~~

Đây là đoạn minh họa, không phải một manifest Deployment đầy đủ.

**Không đặt credential thật vào ví dụ, repository công khai hoặc endpoint debug**. Nếu property chứa secret, hãy dùng cơ chế quản lý secret và giới hạn quyền truy cập của nền tảng triển khai.

## 15. Quản lý đổi tên và tương thích

Giả sử đã triển khai property:

~~~text
shop.checkout.payment.connect-timeout
~~~

Sau đó đổi thành:

~~~text
shop.payment.gateway.timeout
~~~

Đây **không chỉ là đổi tên class hoặc field**. Các công cụ triển khai vẫn có thể đang cấp **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT**. Nếu Java chỉ bind prefix mới, ứng dụng có thể nhận **null**, default hoặc lỗi validation.

Quy trình thay đổi hợp lý:

1. Xác định key cũ, key mới và lý do đổi.
2. Liệt kê môi trường có thể đang dùng key cũ.
3. Cập nhật tài liệu, metadata, manifest và test.
4. Nếu cần giai đoạn chuyển tiếp, triển khai cơ chế đọc key cũ và cảnh báo rõ ràng.
5. Sau khi mọi môi trường đã chuyển, mới loại bỏ cách cấu hình cũ theo kế hoạch.

**Relaxed binding không phải hệ thống alias giữa các namespace không liên quan.** Nó giúp hiểu **base-url** với **baseUrl** trong ngữ cảnh phù hợp, nhưng không tự hiểu **shop.payment.gateway** là tên mới của **shop.checkout.payment**.

**@DeprecatedConfigurationProperty** có thể đóng góp thông tin deprecated vào configuration metadata, nhưng riêng annotation này không tự chuyển các key cũ sang key mới ở runtime. Nếu cần backward compatibility, phải thiết kế cơ chế ánh xạ hoặc migration thực tế.

## 16. Kiểm thử binding theo domain

Một test Spring Boot có thể truyền trực tiếp các property theo đúng prefix:

~~~java
package com.example.shop;

import com.example.shop.config.PaymentProperties;
import com.example.shop.config.ShippingProperties;
import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(properties = {
    "shop.checkout.payment.base-url=https://test-pay.example.invalid",
    "shop.checkout.payment.connect-timeout=2s",
    "shop.checkout.payment.retry.max-attempts=2",
    "shop.checkout.payment.retry.initial-delay=100ms",
    "shop.checkout.shipping.provider-url=https://test-ship.example.invalid",
    "shop.checkout.shipping.enabled=false",
    "shop.checkout.shipping.request-timeout=4s"
})
class DomainPropertiesTest {
    @Autowired PaymentProperties payment;
    @Autowired ShippingProperties shipping;

    @Test
    void bindsSeparateFunctionalGroups() {
        assertEquals(
            URI.create("https://test-pay.example.invalid"),
            payment.baseUrl());
        assertEquals(Duration.ofSeconds(2), payment.connectTimeout());
        assertEquals(2, payment.retry().maxAttempts());
        assertEquals(
            URI.create("https://test-ship.example.invalid"),
            shipping.providerUrl());
        assertFalse(shipping.enabled());
        assertEquals(Duration.ofSeconds(4),
            shipping.requestTimeout());
    }
}
~~~

Ví dụ giả định ứng dụng được đăng ký hai type bằng scanning hoặc enable như phần trước, có **spring-boot-starter-test**, và controller/bean khác không yêu cầu hạ tầng thực để khởi tạo context.

**Điểm cần hiểu:** các property payment và shipping được bind tách biệt; một key shipping không bị lẫn vào bean payment do đường prefix khác nhau.

Nếu muốn thử riêng class cấu hình mà không khởi chạy toàn ứng dụng web, có thể dùng **ApplicationContextRunner** và đăng ký **@EnableConfigurationProperties** cho type cần kiểm tra.

## 17. Những lỗi hay gặp

### 17.1. Viết camelCase trong prefix

~~~java
@ConfigurationProperties(prefix = "shop.checkoutPayment")
~~~

Hãy đổi sang canonical **shop.checkout-payment** hoặc cấu trúc phân cấp **shop.checkout.payment** tùy ranh giới cần mô tả.

### 17.2. Một class AppProperties chứa mọi thứ

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
    String paymentUrl,
    String shippingUrl,
    String emailUrl,
    Duration paymentTimeout,
    Duration shippingTimeout) {
}
~~~

Cách này có thể chạy, nhưng với ứng dụng lớn nó khó sở hữu và test. Tách type theo subsystem khi các nhóm có vòng đời thay đổi độc lập.

### 17.3. Tưởng tên Java camelCase phải giữ nguyên trong YAML

Java **connectTimeout** nên có tên canonical **connect-timeout** trong file. Spring Boot relaxed binding xử lý việc ánh xạ.

### 17.4. Tự thêm dấu dưới vào env cho mỗi từ

**SHOP_CHECKOUT_PAYMENT_CONNECT_TIMEOUT** không phải phép biến đổi chuẩn của key canonical **shop.checkout.payment.connect-timeout**. Theo quy tắc của Spring Boot, tên chuẩn là **SHOP_CHECKOUT_PAYMENT_CONNECTTIMEOUT**.

### 17.5. Nhầm dấu chấm với dấu gạch ngang

**shop.checkout-payment** và **shop.checkout.payment** diễn tả cấu trúc khác nhau; đừng đổi qua lại chỉ vì thấy tên gần giống.

### 17.6. Dùng spring.* cho key nghiệp vụ

**spring.checkout.timeout** dễ bị hiểu là cấu hình framework. Dùng namespace riêng của ứng dụng.

### 17.7. Quên đăng ký type

Chỉ viết **@ConfigurationProperties** lên record chưa đủ nếu nó không được scanning hoặc **@EnableConfigurationProperties** đăng ký. Khi class nằm ngoài package scan, cần khai báo phạm vi quét hoặc đăng ký tường minh.

### 17.8. Dùng @Component cho constructor-bound record

Với kiểu immutable constructor binding như các record của bài này, nên đăng ký theo cách Spring Boot hỗ trợ cho **@ConfigurationProperties**, không dựa vào bean registration thông thường của **@Component**.

### 17.9. Đổi prefix mà không cập nhật deployment

Code sử dụng key mới nhưng Docker/Kubernetes/CI vẫn cấp key cũ sẽ khiến cấu hình không hoạt động như mong đợi. Cần migration rõ ràng.

### 17.10. Thiếu validation cho property quan trọng

Tên chuẩn giúp tìm key; nó không bảo đảm giá trị đúng. Dùng kiểu rõ ràng và ràng buộc phù hợp cho URL, số lần thử, timeout hoặc các trường bắt buộc.

## 18. Bài thực hành

### Bài A — chuyển cấu hình phẳng thành các nhóm theo domain

Cho cấu hình ban đầu:

~~~properties
app.payment-url=https://pay.example.invalid
app.shipping-url=https://ship.example.invalid
app.payment-timeout=3s
app.shipping-timeout=5s
~~~

Hãy đổi thành:

~~~properties
shop.checkout.payment.base-url=https://pay.example.invalid
shop.checkout.payment.connect-timeout=3s
shop.checkout.shipping.provider-url=https://ship.example.invalid
shop.checkout.shipping.request-timeout=5s
~~~

Tạo **PaymentProperties** và **ShippingProperties** riêng. Đăng ký chúng bằng **@ConfigurationPropertiesScan** và đọc giá trị qua constructor injection.

### Bài B — sinh tên biến môi trường

Với ba key canonical:

~~~text
shop.checkout.payment.base-url
shop.checkout.payment.retry.max-attempts
shop.checkout.shipping.request-timeout
~~~

Hãy đổi thành:

~~~text
SHOP_CHECKOUT_PAYMENT_BASEURL
SHOP_CHECKOUT_PAYMENT_RETRY_MAXATTEMPTS
SHOP_CHECKOUT_SHIPPING_REQUESTTIMEOUT
~~~

Chạy cùng JAR với giá trị env mới để quan sát từng object nhận đúng giá trị. Chú ý dấu gạch ngang đã bị **bỏ**.

### Bài C — thêm validation

1. Thêm **spring-boot-starter-validation**.
2. Dùng phiên bản properties có **@Validated**, **@NotNull**, **@Min**.
3. Thử bỏ **base-url** và đặt **retry.max-attempts=0**.
4. Quan sát lỗi khi khởi động và nhận diện đường property thuộc nhóm payment.

### Bài D — so sánh hai domain độc lập

1. Chỉ ghi đè **shop.checkout.payment.connect-timeout** qua env.
2. Giữ cấu hình **shop.checkout.shipping.request-timeout** từ YAML.
3. Dùng **PaymentProperties** và **ShippingProperties** để đọc các giá trị sau khi khởi động.

Kết quả cần hiểu: hai nhóm có nguồn giá trị và trách nhiệm riêng.

### Bài E — thử đổi prefix không tương thích

1. Giữ key **shop.checkout.payment.base-url** trong YAML.
2. Trong một nhánh thử nghiệm, đổi annotation thành **shop.payments.gateway** mà không sửa file.
3. Quan sát property không còn bind theo đường cũ.
4. Khôi phục tên hoặc cập nhật đầy đủ tài liệu, deployment và cấu hình thử nghiệm.

Kết quả cần hiểu: prefix là hợp đồng cấu hình, không chỉ là tên trong Java.

## 19. Checklist trước khi công bố một nhóm cấu hình

Một nhóm **@ConfigurationProperties** nên trả lời được những câu hỏi:

1. Domain/subsystem nào sở hữu nhóm này?
2. Prefix có tránh xung đột với namespace framework và thư viện không?
3. Tên annotation và key đã viết lowercase kebab-case chưa?
4. Độ sâu phân cấp có đủ rõ nhưng không rườm rà không?
5. Tên từng trường có mô tả chính xác mục đích không?
6. Kiểu dữ liệu đã phù hợp chưa, ví dụ Duration hay URI thay vì String chung?
7. Có validation cho giá trị bắt buộc hoặc giá trị giới hạn không?
8. Class đã được đăng ký bằng scanning hoặc enable đúng phạm vi chưa?
9. Tên env có dễ truy vết và không bị va chạm do xóa dấu gạch ngang không?
10. Có metadata/tài liệu giải thích các key cho người triển khai không?
11. Nếu đổi tên, có kế hoạch cập nhật các môi trường đang dùng prefix cũ không?
12. Có secret hoặc dữ liệu nhạy cảm cần nguồn runtime được bảo vệ không?

## 20. Ghi nhớ

- **Prefix là không gian tên công khai của cấu hình ứng dụng**; nên đặt theo miền chức năng.
- **@ConfigurationProperties(prefix = "...")** yêu cầu prefix viết lowercase kebab-case.
- Dấu **.** biểu diễn phân cấp; dấu **-** nối các từ trong cùng một segment.
- **shop.checkout.payment** và **shop.checkout.shipping** nên là hai nhóm độc lập khi có trách nhiệm và vòng đời khác nhau.
- Spring Boot relaxed binding ánh xạ canonical property với Java camelCase và biến môi trường chữ hoa.
- Tên env được sinh bằng quy tắc: **dấu chấm → _; dấu gạch ngang → bỏ; chữ cái → viết hoa**.
- Record immutable có thể dùng constructor binding khi type được đăng ký bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**.
- Nested object phù hợp cho những trường cùng trách nhiệm; class riêng phù hợp cho subsystem độc lập.
- Validation và configuration metadata giúp người dùng phát hiện cấu hình sai và tìm đúng key.
- Đổi prefix sau khi triển khai là thay đổi hợp đồng vận hành, cần được quản lý như một migration.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, *Type-safe Configuration Properties*, *Enabling @ConfigurationProperties Types*, *Relaxed Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- Spring Framework — Environment abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
