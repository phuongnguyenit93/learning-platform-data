# Chọn ranh giới nhóm cấu hình theo trách nhiệm chức năng

## 1. Tại sao cấu hình cần ranh giới kiến trúc?

Một hệ thống Spring Boot có thể bắt đầu với vài property như **app.url**, **app.timeout** và **app.enabled**. Khi có thêm payment gateway, inventory, email, search, fulfillment và nhiều môi trường triển khai, những tên chung chung sẽ khó quản lý.

Ví dụ:

~~~yaml
app:
  url: "https://gateway.example.invalid"
  timeout: 5s
  enabled: true
  retry-count: 3
  stock-threshold: 10
  email-host: "smtp.example.invalid"
  payment-api-key: ""
~~~

Những câu hỏi rất khó trả lời:

- **timeout** dùng cho payment, email hay inventory?
- **enabled** bật chức năng nào?
- Ai được phép sửa timeout mà không làm hỏng chức năng khác?
- Bí mật của payment có nên được truyền cùng object chứa cấu hình inventory?
- Nếu tách payment thành module độc lập, những key nào chuyển theo?
- Vì sao thay đổi provider email lại cần chạy lại test của payment?
- Default của môi trường dev có thể vô tình tác động đến production không?

Spring Boot cung cấp **@ConfigurationProperties** để nhóm các key có prefix chung thành Java object có kiểu, thay vì rải nhiều **@Value** trên các service.

Vì thế, cách chọn **prefix**, **class cấu hình** và **nested object** ảnh hưởng trực tiếp đến cohesion, coupling, validation, security, testability và khả năng nâng cấp.

Bài học này hướng dẫn thiết kế nhóm cấu hình **theo trách nhiệm chức năng**: mỗi nhóm có mục đích, consumer, owner và quy tắc thay đổi rõ ràng.

Bối cảnh: **Spring Boot 3.3.x**, **Java 21**, **Config Data**, **@ConfigurationProperties**, **Bean Validation** và **Spring Boot Test**. Các domain **example.invalid** chỉ dùng để minh họa.

## 2. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt ranh giới theo **chức năng** với ranh giới **file**, **profile**, **môi trường**.
2. Chọn prefix canonical có ngữ cảnh và ổn định.
3. Gom các property cùng consumer và trách nhiệm.
4. Tách nhóm payment, inventory, notification thành các configuration beans độc lập.
5. Quyết định khi nào nên dùng nested record, khi nào nên dùng class riêng.
6. Dùng Duration, URI, DataSize, enum, List/Map phù hợp với contract.
7. Phân biệt shared policy thật với tình cờ hai subsystem có cùng default.
8. Đưa validation và secret ownership vào đúng nhóm.
9. Đổi prefix mà không phá vỡ deployment hiện có.
10. Kiểm thử các nhóm độc lập và kiểm tra các quan hệ chéo ở tầng sở hữu.
11. Tránh AppProperties quá lớn và chia nhỏ cấu hình vô nghĩa.
12. Thiết kế một configuration API thuận tiện cho người phát triển và vận hành.

## 3. Nguyên tắc: nhóm có cùng một lý do thay đổi

Một nhóm cấu hình tốt thường chứa những giá trị:

- Điều khiển **cùng một khả năng** của ứng dụng.
- Được đọc bởi một subsystem hoặc một nhóm consumer gần nhau.
- Có cùng chủ sở hữu về tài liệu và thay đổi.
- Được review cùng nhau khi triển khai một tính năng.
- Có thể cần kiểm tra ràng buộc quan hệ với nhau.
- Có thể di chuyển cùng module nếu hệ thống được tách nhỏ.

Ví dụ:

~~~text
shop.checkout.payment.*
    Cấu hình gateway, retry, timeout, xác thực thanh toán.

shop.inventory.*
    Cấu hình ngưỡng tồn kho, cache và đồng bộ tồn kho.

shop.notification.email.*
    Cấu hình nhà cung cấp email, sender, timeout, token.

shop.search.*
    Cấu hình search engine, index, batch, cache.
~~~

Các field trong nhóm payment có sự liên quan chức năng rõ, còn email provider và stock threshold không có lý do nằm chung với payment.

### 3.1. Cohesion

Cohesion cao nghĩa là những field trong cùng object phục vụ một mục tiêu tương đối thống nhất:

~~~yaml
shop:
  checkout:
    payment:
      gateway-url: "https://gateway.example.invalid"
      connect-timeout: 2s
      request-timeout: 8s
      retry:
        max-attempts: 3
        initial-delay: 200ms
~~~

### 3.2. Coupling

Coupling thấp nghĩa là InventoryService không phải phụ thuộc object chứa API key, URL hoặc retry policy của payment.

Thay vì:

~~~java
public InventoryService(AppProperties everything) {
    this.everything = everything;
}
~~~

nên có:

~~~java
public InventoryService(InventoryProperties properties) {
    this.properties = properties;
}
~~~

Tác dụng: giảm diện tích phụ thuộc và giảm nguy cơ một module vô tình truy cập dữ liệu không liên quan.

### 3.3. Câu hỏi quyết định

Hãy hỏi: *Nếu thay thế toàn bộ chức năng này bằng cách triển khai khác, những property nào nên đi cùng nó mà không ảnh hưởng các chức năng khác?*

Đó thường là tập hợp hợp lý cho một configuration boundary.

## 4. Cây YAML không phải bản đồ ownership

Một file **application.yml** có thể chứa nhiều nhóm:

~~~yaml
spring:
  application:
    name: shop-api

shop:
  checkout:
    payment:
      request-timeout: 8s

  inventory:
    cache-ttl: 45s

  notification:
    email:
      enabled: false
~~~

Dù tất cả cùng ở một file, ta vẫn có thể tạo ba class độc lập:

~~~text
PaymentProperties
InventoryProperties
EmailProperties
~~~

Ngược lại, những key của một nhóm có thể đến từ nhiều nguồn:

~~~text
application.yml                       -> payment timeout default
application-prod.yml                  -> payment gateway production
Kubernetes Secret/configtree volume  -> payment api-key
command-line                          -> payment retry override
~~~

Khi Spring Boot bind **@ConfigurationProperties**, nó dùng các giá trị có hiệu lực trong **Environment** theo thứ tự ưu tiên nguồn, không chỉ một file riêng.

**Ranh giới file là cách đóng gói và triển khai. Ranh giới chức năng là hợp đồng của module với ứng dụng.**

## 5. Mô hình ví dụ: shop-api

Giả sử một ứng dụng có các capability:

| Capability | Chức năng chính | Configuration owner |
| --- | --- | --- |
| Checkout/payment | Gửi yêu cầu tới payment gateway | Payment integration |
| Inventory | Đọc và đồng bộ tồn kho | Inventory module |
| Notification/email | Gửi email cho khách hàng | Notification module |
| Search | Index và truy vấn sản phẩm | Search module |
| Platform HTTP | Cung cấp HTTP client factory chung | Platform/infrastructure |

Một namespace đề xuất:

~~~text
shop.checkout.payment.gateway-url
shop.checkout.payment.connect-timeout
shop.checkout.payment.request-timeout
shop.checkout.payment.retry.max-attempts
shop.checkout.payment.retry.initial-delay
shop.checkout.payment.api-key

shop.inventory.cache-ttl
shop.inventory.low-stock-threshold
shop.inventory.sync.batch-size
shop.inventory.sync.interval

shop.notification.email.enabled
shop.notification.email.provider-url
shop.notification.email.sender-address
shop.notification.email.request-timeout
shop.notification.email.api-token

shop.search.index-name
shop.search.batch-size
shop.search.cache-ttl
~~~

Không có yêu cầu mọi capability phải có cùng độ sâu prefix. Nhưng **tên đầy đủ phải làm rõ property thuộc subsystem nào**.

### 5.1. shop.checkout.payment hay shop.payment?

Nếu payment chỉ phục vụ checkout và chịu ownership của checkout, **shop.checkout.payment** diễn đạt điều đó.

Nếu payment cũng dùng cho refund, subscription và nhiều sản phẩm khác, **shop.payment** có thể là ranh giới bền vững hơn.

Chọn tên theo **ngôn ngữ nghiệp vụ và trách nhiệm thực**, không theo package Java hiện tại một cách máy móc.

## 6. Bảy tiêu chí đánh giá một ranh giới

### 6.1. Mục đích

Các key có cùng điều khiển một chức năng được giải thích bằng một câu ngắn không? Nếu phải nói “đây là nhóm những gì chưa biết để đâu”, đó có thể là một nhóm kém.

### 6.2. Consumer

Các key có được một component hoặc subsystem tiêu thụ phần lớn không? Nếu chỉ một service cần timeout và API key của payment, hãy giữ chúng gần payment.

### 6.3. Quyền sở hữu thay đổi

Ai cần phê duyệt khi chỉnh cấu hình? Nếu payment team sửa một field khiến email module cũng phải review, object có thể đang chứa quá nhiều trách nhiệm.

### 6.4. Vòng đời triển khai

Những field nào thường thay đổi cùng một feature release hoặc vận hành cùng một integration? Chúng có thể thích hợp ở chung nhóm.

### 6.5. Validation

Các field cần so sánh với nhau như **request-timeout > connect-timeout** thường có lợi khi nằm cùng object.

### 6.6. Security

Các giá trị có cùng mức độ nhạy cảm/consumer không? Payment API key không nên đi cùng mọi cấu hình khác rồi được inject vào các module không cần nó.

### 6.7. Khả năng di chuyển

Nếu tách module thành library hoặc microservice, có thể chuyển configuration model và namespace tương đối độc lập không?

Một thiết kế hiếm khi tối ưu tuyệt đối cả bảy tiêu chí. Hãy ưu tiên tiêu chí gắn với thay đổi và ownership thực tế.

## 7. Anti-pattern 1: AppProperties chứa mọi thứ

Ví dụ:

~~~java
package com.example.shop.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String paymentUrl,
        Duration paymentTimeout,
        String paymentApiKey,
        Duration inventoryCacheTtl,
        int inventoryThreshold,
        String emailProviderUrl,
        boolean emailEnabled,
        String emailToken,
        String searchIndex,
        int searchBatchSize) {
}
~~~

Class này vẫn có thể bind được, nhưng dễ gây vấn đề:

1. Chỉ cần một field cũng phải inject toàn bộ object.
2. Thêm chức năng làm constructor ngày càng dài.
3. Validation giữa nhiều module dễ bị lẫn.
4. Một default sai của email có thể làm test inventory thất bại.
5. Secret có thể bị log bởi **toString()** của record.
6. Một module không thể tách ra mà không kéo theo cả class chung.
7. Thông tin ownership biến mất dưới prefix mơ hồ **app**.
8. Metadata và tài liệu khó tra cứu khi số lượng field lớn.

**Cách sửa:** tách PaymentProperties, InventoryProperties, EmailProperties và SearchProperties với prefix của từng capability.

## 8. Anti-pattern 2: một configuration bean cho từng primitive

Một cực đoan khác là tách quá nhỏ:

~~~text
ConnectTimeoutProperties
ReadTimeoutProperties
RetryEnabledProperties
RetryMaxAttemptsProperties
RetryDelayProperties
~~~

Nếu tất cả đều thuộc một payment client, việc chia nhỏ khiến:

- Nhiều beans và constructor parameters không cần thiết.
- Khó validate quan hệ giữa các field.
- Khó biết nhóm nào đại diện cho một capability hoàn chỉnh.
- Metadata bị phân tán không có cấu trúc rõ.
- Người vận hành phải tra nhiều class để hiểu một client.

Thường tốt hơn là:

~~~text
PaymentProperties
  gatewayUrl
  connectTimeout
  requestTimeout
  Retry retry
    enabled
    maxAttempts
    initialDelay
    maxDelay
~~~

**Nhóm tốt không phải nhóm nhỏ nhất**. Nó đủ hẹp để có một trách nhiệm, đủ rộng để chứa các field cùng logic.

## 9. PaymentProperties: ranh giới của payment integration

Sử dụng Java record bất biến:

~~~java
package com.example.shop.payment;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.checkout.payment")
public record PaymentProperties(
        @NotNull URI gatewayUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry,
        String apiKey) {

    public record Retry(
            boolean enabled,
            @Min(1) int maxAttempts,
            @DefaultValue("250ms") Duration initialDelay,
            @DefaultValue("3s") Duration maxDelay) {
    }
}
~~~

Tương ứng:

~~~yaml
shop:
  checkout:
    payment:
      gateway-url: "https://gateway.example.invalid"
      connect-timeout: 2s
      request-timeout: 8s
      retry:
        enabled: true
        max-attempts: 3
        initial-delay: 250ms
        max-delay: 3s
~~~

### 9.1. Tại sao retry là nested object?

Các field retry đều thuộc một policy của **payment gateway client**, dùng cùng consumer và thường cần validation với nhau.

Không phải vì tên **retry** xuất hiện ở nhiều module mà phải tạo một global **shop.retry**. Retry của payment và retry của inventory có thể có nhu cầu khác nhau.

### 9.2. Tại sao kiểu dữ liệu quan trọng?

- **URI** cho gatewayUrl giúp tránh xử lý URL bằng string rời rạc.
- **Duration** cho timeout/delay làm rõ thời lượng; cấu hình có thể dùng **2s**, **250ms**.
- **int** cho maxAttempts phù hợp khi luôn có giá trị, nhưng có thể dùng **Integer @NotNull @Min(1)** nếu phải phân biệt giá trị thiếu với 0.
- **boolean** cho enabled mặc định false nếu không được cấp; cần mô tả rõ quy tắc mặc định.

### 9.3. API key thuộc payment, không nằm trong mã nguồn

Property:

~~~text
shop.checkout.payment.api-key
~~~

là tên của secret được PaymentClient sử dụng. Không đặt secret thật trong application.yml hoặc Java class. Runtime có thể cấp từ biến môi trường:

~~~text
SHOP_CHECKOUT_PAYMENT_APIKEY
~~~

hoặc file config tree dưới secret volume.

**Lưu ý:** record mặc định có toString chứa các components. Không log toàn bộ PaymentProperties khi có apiKey.

## 10. InventoryProperties: ownership độc lập

~~~java
package com.example.shop.inventory;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryProperties(
        @NotNull Duration cacheTtl,
        @Min(0) int lowStockThreshold,
        @Valid @NotNull Sync sync) {

    public record Sync(
            @Min(1) int batchSize,
            @DefaultValue("5m") Duration interval) {
    }
}
~~~

Config:

~~~yaml
shop:
  inventory:
    cache-ttl: 45s
    low-stock-threshold: 10
    sync:
      batch-size: 200
      interval: 5m
~~~

Inventory có các quy tắc riêng:

- TTL phải phù hợp với độ mới dữ liệu tồn kho.
- Batch size phải dương.
- Low-stock threshold không được âm.
- Sync interval thể hiện thời gian giữa các lượt đồng bộ.

Inventory không cần biết payment gateway URL, token hoặc retry policy. Đó là bằng chứng ranh giới phù hợp.

### 10.1. Sync nên là nested hay một bean khác?

Nếu đồng bộ tồn kho chỉ là một cơ chế nội bộ của Inventory, nested **InventoryProperties.Sync** là đủ.

Nếu nó trở thành subsystem có queue, worker, lifecycle và operator riêng, có thể cân nhắc tách thành **InventorySyncProperties** với prefix riêng, chẳng hạn **shop.inventory.sync**.

Quyết định dựa trên **quyền sở hữu/lifecycle**, không chỉ số lượng fields.

## 11. EmailProperties: ranh giới của chức năng thông báo

~~~java
package com.example.shop.notification.email;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Email;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.notification.email")
public record EmailProperties(
        boolean enabled,
        URI providerUrl,
        @Email String senderAddress,
        @DefaultValue("5s") Duration requestTimeout,
        String apiToken) {
}
~~~

Config:

~~~yaml
shop:
  notification:
    email:
      enabled: false
      sender-address: "noreply@example.invalid"
      request-timeout: 5s
~~~

Nếu email disabled, có thể không cần providerUrl hoặc apiToken. Nếu enabled, những field đó có thể bắt buộc. Ràng buộc phụ thuộc enabled cần custom class-level validator hoặc phương thức thích hợp.

**Không tự gắn @NotNull vô điều kiện vào token rồi gây lỗi cho mọi môi trường chỉ vì feature tắt.** Contract phải mô tả điều kiện.

### 11.1. Secret và quyền sở hữu

Email provider token thuộc cấu hình **shop.notification.email.api-token**, nhưng bảo mật thật sự đến từ secret manager, quyền đọc runtime và chính sách không log. Prefix không phải security boundary ở cấp hệ điều hành.

## 12. Đăng ký configuration properties theo Spring Boot 3.3

Với record dùng constructor binding, có thể bật scanning:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan("com.example.shop")
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Hoặc module chủ động đăng ký:

~~~java
package com.example.shop.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

### 12.1. Khi nào chọn scan?

**@ConfigurationPropertiesScan** thích hợp khi ứng dụng kiểm soát toàn bộ packages và muốn tự phát hiện các configuration properties classes.

### 12.2. Khi nào chọn EnableConfigurationProperties?

**@EnableConfigurationProperties** thích hợp với module configuration hoặc auto-configuration muốn kích hoạt đúng những type cụ thể. Nó cho phép module khai báo rõ config contract mình sở hữu.

### 12.3. Không chỉ dùng @Component cho record

Một record được khai báo **@ConfigurationProperties** không tự trở thành bean nếu chưa đăng ký. Constructor binding không nên bị trộn với cách tạo bean component thông thường và Spring bean injection parameters.

## 13. Service chỉ inject nhóm mình dùng

Payment:

~~~java
package com.example.shop.payment;

import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI gateway() {
        return properties.gatewayUrl();
    }
}
~~~

Inventory:

~~~java
package com.example.shop.inventory;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryProperties properties;

    public InventoryService(InventoryProperties properties) {
        this.properties = properties;
    }

    public Duration cacheTtl() {
        return properties.cacheTtl();
    }
}
~~~

Notification:

~~~java
package com.example.shop.notification.email;

import org.springframework.stereotype.Service;

@Service
public class EmailSender {

    private final EmailProperties properties;

    public EmailSender(EmailProperties properties) {
        this.properties = properties;
    }

    public boolean enabled() {
        return properties.enabled();
    }
}
~~~

Không cần inject **AppProperties everything**. Nếu checkout orchestration dùng cả payment và inventory, thường nó nên inject **PaymentService** và **InventoryService**, không tự truy cập cấu hình nội bộ của hai module rồi làm nghiệp vụ thay cho chúng.

## 14. Configuration model không phải service

Một anti-pattern:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
public class PaymentProperties {
    private final PaymentClient client;

    public PaymentProperties(PaymentClient client) {
        this.client = client;
    }
}
~~~

Class cấu hình đang yêu cầu một runtime service làm dependency; đó là hai trách nhiệm khác nhau.

Nên phân tầng:

~~~text
Environment và PropertySources
            |
            v
       PaymentProperties
            |
            v
     @Bean PaymentClient
            |
            v
       PaymentService
~~~

Theo hướng dẫn Spring Boot, configuration properties classes nên chủ yếu làm việc với Environment, tránh inject các beans khác.

Ví dụ factory:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentClientConfiguration {

    @Bean
    public PaymentClient paymentClient(
            PaymentProperties properties) {

        return new PaymentClient(
                properties.gatewayUrl(),
                properties.connectTimeout(),
                properties.requestTimeout());
    }
}
~~~

**PaymentClient ở đây là type do ứng dụng giả định định nghĩa**, không phải API sẵn có của Spring Boot. Ví dụ chỉ thể hiện vị trí wiring thích hợp.

## 15. Framework properties khác custom properties

Spring Boot đã có các namespace chuẩn:

~~~text
spring.datasource.*
spring.kafka.*
spring.mail.*
server.*
management.*
logging.*
~~~

Nếu framework đã hỗ trợ property bạn cần, thường hãy dùng chính key chuẩn.

Ví dụ:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
~~~

được DataSource auto-configuration của Spring Boot hiểu. Tự đổi thành:

~~~properties
shop.database.url=jdbc:postgresql://localhost:5432/shop
~~~

không làm Spring Boot tự chuyển nó về **spring.datasource.url** nếu chưa có bridging logic.

Ngược lại, URL retry policy của custom payment SDK có thể không có key framework tương ứng; namespace **shop.checkout.payment** là hợp lý.

### 15.1. Không wrap toàn bộ key framework một cách vô cớ

Nếu tạo **shop.platform.database.url** chỉ để chuyển sang **spring.datasource.url**, bạn thêm một contract thứ hai cần tài liệu, kiểm thử và migration.

Một abstraction như vậy chỉ nên tồn tại khi có yêu cầu thật, ví dụ platform cần một API cấu hình ổn định chung cho nhiều runtime khác nhau.

## 16. Nested group hay bean riêng?

Một nested group phù hợp nếu:

- Chỉ tồn tại để phục vụ parent.
- Có cùng consumer và cùng owner.
- Thường được cấu hình/validate cùng parent.
- Không cần được inject trực tiếp ở nhiều nơi.
- Có tên nhóm nội bộ rõ: retry, pool, tls, circuit-breaker.

Ví dụ:

~~~text
shop.checkout.payment.retry.*
~~~

là nested **PaymentProperties.Retry**.

Một bean riêng phù hợp nếu:

- Subsystem có owner hoặc lifecycle độc lập.
- Nhiều consumers cần đúng nhóm đó, không phải parent.
- Có thể triển khai/tách module riêng.
- Có validation, config API và tài liệu riêng.
- Nó được sử dụng ở nhiều use cases hơn parent.

Ví dụ **shop.notification.email** hoàn toàn có thể là **EmailProperties** riêng, dù cây prefix có nhiều cấp.

### 16.1. @NestedConfigurationProperty

Spring Boot có annotation **@NestedConfigurationProperty** để hỗ trợ **configuration metadata processor** nhận diện một field/record component là nested type trong những trường hợp cần hint.

**Annotation này không thay đổi quá trình binding**. Đừng kỳ vọng thêm nó sẽ tạo bean, chạy nested validation hoặc sửa lỗi prefix.

Với nested validation dùng **@Valid** theo Jakarta Bean Validation; với registration dùng scan/enable phù hợp.

## 17. Shared defaults không đồng nghĩa shared ownership

Giả sử payment và inventory đều dùng timeout mặc định 10s.

Một thiết kế vội:

~~~yaml
shop:
  common:
    timeout: 10s
~~~

rồi cả hai cùng đọc **shop.common.timeout**.

Vấn đề: nếu payment cần giảm timeout còn inventory cần tăng, một thay đổi sẽ tác động cả hai.

**Trùng giá trị hiện tại không chứng minh hai subsystem cùng chia sẻ một policy.**

Tách:

~~~yaml
shop:
  checkout:
    payment:
      request-timeout: 10s

  inventory:
    remote-request-timeout: 10s
~~~

Nếu sau này giá trị khác nhau, hai modules vẫn độc lập.

### 17.1. Khi nào nhóm shared là đúng?

Nếu platform cung cấp **một HTTP client factory chung** mà mọi subsystem thực sự dùng cùng một policy:

~~~text
shop.platform.outbound-http.default-connect-timeout
shop.platform.outbound-http.default-max-connections
~~~

thì đây là một ranh giới có owner thật: **platform HTTP infrastructure**.

Các nhóm chức năng có thể chọn dùng default chung và override cục bộ khi cần.

### 17.2. Placeholder để chia sẻ default

Ví dụ:

~~~yaml
shop:
  platform:
    outbound-http:
      default-connect-timeout: 2s

  checkout:
    payment:
      connect-timeout: "${shop.platform.outbound-http.default-connect-timeout:2s}"

  inventory:
    remote-connect-timeout: "${shop.platform.outbound-http.default-connect-timeout:2s}"
~~~

Từng subsystem vẫn có key riêng, nhưng có thể tham chiếu default platform.

Tuy nhiên, tránh lồng nhiều tầng placeholder khó tìm nguồn. Chỉ dùng khi shared policy được quản lý rõ ràng.

### 17.3. Tái sử dụng Java type không buộc dùng chung giá trị

Có thể tái sử dụng:

~~~java
public record RetryOptions(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay) {
}
~~~

ở nhiều module, nhưng mỗi module vẫn nhận giá trị từ prefix riêng.

**Shared structure** khác **shared configuration instance**.

## 18. Secret đi theo chức năng, nhưng phải bảo vệ ở runtime

Ví dụ các tên property:

~~~text
shop.checkout.payment.api-key
shop.notification.email.api-token
shop.inventory.supplier.password
~~~

chỉ ra consumer của từng secret. Tuy nhiên, **prefix không phải security boundary**: nếu mọi object sống trong cùng process và đều đọc được Environment, module khác có thể truy xuất secret.

Cần bảo vệ bằng:

- Secret manager hoặc container secret volume.
- Least-privilege workload identity.
- RBAC và filesystem permissions.
- Không commit giá trị bí mật vào Git/JAR/image.
- Không log Environment hay toString của record chứa token.
- Rotation và thu hồi.
- Tách service identity/process nếu cần isolation mạnh.

Ví dụ runtime env:

~~~text
SHOP_CHECKOUT_PAYMENT_APIKEY=<runtime-secret>
~~~

Hoặc configtree:

~~~text
/etc/shop-secrets/shop.checkout.payment.api-key
~~~

và:

~~~properties
spring.config.import=configtree:/etc/shop-secrets/
~~~

**configtree** là cơ chế nạp dữ liệu từ file theo tên property; nó không tự mã hóa hoặc quản lý vòng đời secret.

## 19. Validation nên gắn với module sở hữu quy tắc

Payment có thể cần:

~~~text
request-timeout > connect-timeout
retry.max-attempts >= 1
retry.initial-delay <= retry.max-delay
api-key bắt buộc khi live-mode được bật
~~~

Inventory:

~~~text
cache-ttl > 0
low-stock-threshold >= 0
sync.batch-size >= 1
sync.interval > 0
~~~

Email:

~~~text
enabled=false -> có thể thiếu provider-url và api-token
enabled=true  -> cần provider-url và api-token
~~~

Đây là các hợp đồng khác nhau; không cần một **GlobalPropertiesValidator** khổng lồ biết mọi subsystem.

### 19.1. @Validated và @Valid

Spring Boot có thể kích hoạt Jakarta Bean Validation trên **@ConfigurationProperties** được đánh dấu **@Validated** khi implementation phù hợp có mặt.

~~~java
@Validated
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryProperties(
        @NotNull Duration cacheTtl,
        @Valid @NotNull Sync sync) {

    public record Sync(
            @Min(1) int batchSize) {
    }
}
~~~

Khi cần validation, thêm **spring-boot-starter-validation**.

### 19.2. Cross-field validation

Hai Duration hợp lệ riêng lẻ chưa chứng minh quan hệ đúng. Ví dụ:

~~~text
connect-timeout=8s
request-timeout=3s
~~~

Nếu payment client thật có rule **requestTimeout > connectTimeout**, có thể viết class-level constraint qua **@Constraint** và **ConstraintValidator**, hoặc **@AssertTrue** trên boolean getter phù hợp.

Chỉ áp dụng rule khi contract của thư viện thực sự đòi hỏi; không phải mọi HTTP client có cùng ý nghĩa request/connect timeout.

## 20. Quan hệ giữa nhiều module thuộc orchestration layer

Giả sử checkout có tổng thời gian xử lý:

~~~text
shop.checkout.total-timeout
shop.checkout.payment.request-timeout
shop.inventory.remote-request-timeout
~~~

Một quy tắc có thể yêu cầu **checkout total timeout** đủ cho các bước tuần tự trong luồng đơn hàng.

Ai sở hữu rule này? Không hoàn toàn là payment hay inventory. Nó là **checkout orchestration**.

Có thể có startup guard:

~~~java
@Component
public class CheckoutConfigurationGuard {

    public CheckoutConfigurationGuard(
            CheckoutProperties checkout,
            PaymentProperties payment,
            InventoryProperties inventory) {

        // So sánh các Duration đã được bind.
        // Nếu tổng thời gian không phù hợp, báo lỗi startup.
    }
}
~~~

Đây là bản phác thảo, không phải một validator hoàn chỉnh. CheckoutProperties cần được định nghĩa/đăng ký phù hợp.

Điểm thiết kế: **đừng để PaymentProperties inject InventoryProperties** chỉ để kiểm tra một quan hệ bên ngoài trách nhiệm payment.

Guard hoặc orchestration validation cần chạy ở lifecycle đảm bảo component phụ thuộc chưa hoạt động với cấu hình sai. Không dựa vào thứ tự singleton initialization ngẫu nhiên.

## 21. Quy tắc đặt tên prefix và field

Nên dùng:

- **lowercase kebab-case** cho tên canonical.
- Prefix thể hiện domain/capability, không chỉ “config”.
- Tên field diễn đạt ý nghĩa, đơn vị và consumer.
- Không gắn tên môi trường vào key nếu có thể dùng profile/source override.
- Tránh tên team/cá nhân làm namespace nếu tổ chức có thể thay đổi.
- Giữ từ vựng nghiệp vụ nhất quán.
- Xem prefix như API cho developer, operator, deployment scripts.

Tên hợp lý:

~~~text
shop.checkout.payment.request-timeout
shop.checkout.payment.retry.max-attempts
shop.inventory.low-stock-threshold
shop.notification.email.sender-address
~~~

Tên dễ hiểu nhầm:

~~~text
app.timeout
app.flag1
app.common.password
app.config.settings.value
app.prod.gateway-host
~~~

### 21.1. Biến môi trường

Theo quy tắc Spring Boot cho environment variables:

1. Dấu chấm **.** → dấu dưới **_**.
2. Dấu gạch ngang **-** → bỏ.
3. Tên → viết hoa.

Ví dụ:

~~~text
shop.checkout.payment.gateway-url
    -> SHOP_CHECKOUT_PAYMENT_GATEWAYURL

shop.inventory.low-stock-threshold
    -> SHOP_INVENTORY_LOWSTOCKTHRESHOLD

shop.notification.email.sender-address
    -> SHOP_NOTIFICATION_EMAIL_SENDERADDRESS
~~~

Không tự nghĩ mọi kebab-case segment đều cần thêm underscore giữa các từ. Quy tắc chuẩn là **loại bỏ dấu gạch ngang**.

### 21.2. Tên root không nên quá chung

Nếu ứng dụng hoặc library được nhúng trong một host lớn, prefix **app** quá chung có thể gây xung đột. Một namespace như **shop** hoặc **acme.payment** ổn định hơn khi có nhiều modules/starter.

## 22. List, Map và cấu trúc config cũng là quyết định trách nhiệm

Payment có routing theo vùng.

Nếu thứ tự quan trọng:

~~~yaml
shop:
  checkout:
    payment:
      gateways:
        - region: asia
          url: "https://asia.example.invalid"
        - region: europe
          url: "https://europe.example.invalid"
~~~

**List<Gateway>** phù hợp.

Nếu tên vùng là key định danh và tra cứu:

~~~yaml
shop:
  checkout:
    payment:
      gateways:
        asia:
          url: "https://asia.example.invalid"
        europe:
          url: "https://europe.example.invalid"
~~~

**Map<String, Gateway>** có thể tốt hơn.

Câu hỏi:

- Thứ tự có ảnh hưởng xử lý không?
- Key có ổn định không?
- Có cần override từng entry theo môi trường không?
- Có cần ràng buộc uniqueness không?
- Có nhiều entry động và không biết trước số lượng không?

Trong Spring Boot, **List được nguồn ưu tiên cao hơn thay toàn danh sách** thay vì merge từng phần tử theo kiểu đan xen tùy ý. Map có quy tắc binding khác. Vì thế lựa chọn dữ liệu ảnh hưởng cách operator triển khai override.

Dù List hay Map, payment gateway routes vẫn thuộc trách nhiệm **payment**, không phải một nhóm toàn cục.

## 23. Property prefix là external configuration API

Key:

~~~text
shop.checkout.payment.gateway-url
~~~

có thể xuất hiện ở:

- application.yml/application-prod.yml.
- Docker Compose environment.
- Kubernetes ConfigMap và Secret file names.
- Helm templates/values.
- Terraform/deployment scripts.
- CI/CD variables.
- Test fixtures.
- Tài liệu vận hành.

Đổi prefix ảnh hưởng nhiều nơi ngoài Java source. **Một compile thành công không chứng minh deploy đã được migrate.**

### 23.1. Đổi class name khác đổi prefix

Đổi Java class:

~~~text
PaymentProperties -> PaymentGatewayProperties
~~~

mà vẫn giữ:

~~~java
@ConfigurationProperties(prefix = "shop.checkout.payment")
~~~

thường ít tác động đến external config hơn đổi prefix thành **shop.integrations.gateway**.

Tên class là Java API; prefix là API của quá trình triển khai. Cả hai cần quản lý theo consumers tương ứng.

## 24. Tái cấu trúc một nhóm cấu hình cũ

Giả sử phiên bản cũ:

~~~properties
app.payment-url=https://gateway.example.invalid
app.payment-timeout=8s
app.payment-retry-count=3
app.inventory-ttl=45s
app.email-enabled=true
~~~

Muốn chuyển sang:

~~~properties
shop.checkout.payment.gateway-url=https://gateway.example.invalid
shop.checkout.payment.request-timeout=8s
shop.checkout.payment.retry.max-attempts=3
shop.inventory.cache-ttl=45s
shop.notification.email.enabled=true
~~~

Đây là refactor hữu ích nhưng có nguy cơ mất backward compatibility.

### 24.1. Relaxed binding không tự tạo semantic alias

Spring Boot hỗ trợ các dạng viết tương đương trong relaxed binding, nhưng **app.payment-timeout** không tự động là alias của **shop.checkout.payment.request-timeout**.

Hai key có namespace/nghĩa khác nhau. Cần migration thật.

### 24.2. Kế hoạch migration

1. Kiểm kê mọi chỗ dùng key cũ trong deployment và test.
2. Công bố key mới và mapping old → new.
3. Quy định thời gian hỗ trợ key cũ.
4. Nếu phải hỗ trợ đồng thời, thiết kế compatibility adapter hoặc migration layer.
5. Quy định **nếu old và new cùng có thì key nào thắng**.
6. Tạo warning deprecation không lộ giá trị bí mật.
7. Cập nhật ConfigMap, Helm, env và docs.
8. Test old-only, new-only, both và neither.
9. Sau thời hạn, loại bỏ old key có thông báo phù hợp.

### 24.3. Ví dụ compatibility helper

~~~java
package com.example.shop.migration;

import java.time.Duration;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class TimeoutCompatibility {

    private TimeoutCompatibility() {
    }

    public static Duration resolve(Environment env) {
        Binder binder = Binder.get(env);

        Duration modern = binder.bind(
                "shop.checkout.payment.request-timeout",
                Duration.class).orElse(null);

        if (modern != null) {
            return modern;
        }

        return binder.bind(
                "app.payment-timeout",
                Duration.class).orElse(Duration.ofSeconds(8));
    }
}
~~~

Helper này là một **ý tưởng migration**, không tự thay đổi object PaymentProperties đã được bind. Cần tích hợp rõ với bước tạo client hoặc một configuration factory phù hợp.

### 24.4. @DeprecatedConfigurationProperty không phải runtime alias

Spring Boot có **@DeprecatedConfigurationProperty** và configuration metadata giúp tooling biết property cũ đã deprecated.

**Metadata không tự chuyển key cũ thành key mới** khi Binder chạy. Nếu vẫn cần hỗ trợ runtime cho tên cũ, phải xây cơ chế compatibility riêng.

## 25. Một default có thể thuộc framework, platform hoặc module

Hãy phân ba tầng:

**Framework default:** Spring Boot đã có giá trị mặc định cho một số key **server.***, **spring.***.

**Platform policy:** tổ chức định nghĩa timeout default cho HTTP client factory chung.

**Module default:** payment tự định nghĩa retry/backoff, inventory tự định nghĩa cache TTL.

Đừng copy các defaults của framework vào một **GlobalApplicationDefaults** nếu không có lý do thực tế.

### 25.1. @DefaultValue

Với constructor binding/record, có thể dùng:

~~~java
@ConfigurationProperties(prefix = "shop.inventory")
public record InventoryOptions(
        @DefaultValue("30s") Duration cacheTtl,
        @DefaultValue("10") int lowStockThreshold) {
}
~~~

Giá trị default này thuộc **configuration object**, không tự trở thành một property mới bên trong Environment.

Nếu muốn người vận hành có thể nhìn thấy default ngay trong Config Data, có thể ghi trong application.yml. Chọn một chiến lược rõ ràng và tránh hai default mâu thuẫn.

### 25.2. Tránh default nguy hiểm

Nếu payment live mode cần API key, không đặt **api-key=changeme** để mọi environment khởi động. Nên fail-fast nếu thông tin bắt buộc thiếu.

## 26. Feature flags thuộc capability nào?

Ví dụ:

~~~text
shop.notification.email.enabled
shop.checkout.payment.retry.enabled
shop.search.indexing.enabled
~~~

Một field **enabled** có ý nghĩa trong nhóm của nó.

Không nên gom thành:

~~~text
app.flags.email
app.flags.payment-retry
app.flags.indexing
~~~

chỉ vì tất cả đều là boolean, trừ khi ứng dụng thực sự có một **feature flag platform** độc lập quản lý lifecycle/audit/rollout của toàn bộ flags.

**Giống kiểu dữ liệu không phải một trách nhiệm chức năng.**

### 26.1. @ConditionalOnProperty

~~~java
@ConditionalOnProperty(
        prefix = "shop.notification.email",
        name = "enabled",
        havingValue = "true")
~~~

được dùng để tạo bean có điều kiện.

Lưu ý: condition này đọc Environment, không tự biết default bên trong Java record. Nếu cần enabled mặc định, dùng **matchIfMissing** phù hợp hoặc khai báo default trong Config Data.

## 27. Configuration metadata giúp khám phá ranh giới

Spring Boot có thể tạo metadata cho các **@ConfigurationProperties** types, giúp IDE completion và mô tả các property.

Gradle:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Ví dụ tooling có thể thấy:

~~~text
shop.checkout.payment.gateway-url     URI
shop.checkout.payment.request-timeout  Duration
shop.inventory.cache-ttl               Duration
shop.notification.email.enabled        boolean
~~~

Khi nhóm được thiết kế đúng theo capability, metadata dễ hiểu hơn.

**@NestedConfigurationProperty** có thể cung cấp hint cho metadata processor trong một số trường hợp nested types không được suy luận tự động; nó không thay đổi binding.

Metadata cũng không thay validation, runtime alias hoặc secret management.

## 28. Kiểm thử độc lập bằng ApplicationContextRunner

Ranh giới tốt giúp kiểm thử một nhóm mà không khởi chạy cả ứng dụng.

Ví dụ cho InventoryProperties:

~~~java
package com.example.shop.inventory;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(InventoryProperties.class)
    static class TestConfig {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void bindsInventoryGroup() {
        runner.withPropertyValues(
                "shop.inventory.cache-ttl=30s",
                "shop.inventory.low-stock-threshold=5",
                "shop.inventory.sync.batch-size=100",
                "shop.inventory.sync.interval=2m"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            InventoryProperties p =
                    context.getBean(InventoryProperties.class);

            assertThat(p.cacheTtl())
                    .isEqualTo(Duration.ofSeconds(30));
            assertThat(p.lowStockThreshold()).isEqualTo(5);
            assertThat(p.sync().batchSize()).isEqualTo(100);
            assertThat(p.sync().interval())
                    .isEqualTo(Duration.ofMinutes(2));
        });
    }
}
~~~

Test này không cần payment token hoặc email provider, không cần kết nối dịch vụ ngoài. Nó chỉ chứng minh binding của InventoryProperties.

### 28.1. Test PaymentProperties riêng

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
static class PaymentTestConfig {
}
~~~

Runner:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(PaymentTestConfig.class)
    .withPropertyValues(
        "shop.checkout.payment.gateway-url=https://test.example.invalid",
        "shop.checkout.payment.connect-timeout=1s",
        "shop.checkout.payment.request-timeout=4s",
        "shop.checkout.payment.retry.enabled=true",
        "shop.checkout.payment.retry.max-attempts=2",
        "shop.checkout.payment.retry.initial-delay=100ms",
        "shop.checkout.payment.retry.max-delay=1s")
    .run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(PaymentProperties.class);
    });
~~~

Điều này kiểm tra group mà không gọi gateway thật.

### 28.2. Validation test

Nếu group gắn **@Validated** và Jakarta constraints, cần **spring-boot-starter-validation** và infrastructure phù hợp trong test context.

Nên test:

- Thiếu field bắt buộc.
- Duration hoặc integer không convert được.
- Constraint như maxAttempts >= 1.
- Nested validation qua **@Valid**.
- Điều kiện enabled=true cần credentials.
- Quan hệ timeout/delay nếu đã thiết kế validator.
- Nguồn env/profile ở integration test khi cần chứng minh runtime override.

ApplicationContextRunner kiểm tra rất tốt binding với **withPropertyValues**, nhưng không mặc định thay thế toàn bộ Config Data bootstrap của SpringApplication.

## 29. Kiểm thử tác động giữa các nhóm

Một vài assertion kiến trúc hữu ích:

~~~text
Payment:
  request-timeout = 3s

Inventory:
  remote-request-timeout = 20s

Kỳ vọng:
  PaymentClient dùng 3s
  InventoryClient dùng 20s
~~~

Nếu thay timeout của payment khiến InventoryClient đổi timeout, có thể đã tạo coupling qua một global default, binding nhầm key hoặc client factory áp dụng sai policy.

Có thể bổ sung:

- Architecture test về package dependencies.
- Integration test cho configuration wiring.
- Test khi đổi một prefix.
- Test migration old/new key.
- Test profile and env override.
- Test không log secret.

**Test xanh chứng minh hành vi đã mô tả**, không tự kết luận ranh giới kiến trúc là hoàn hảo. Các quyết định ownership vẫn cần trao đổi giữa team.

## 30. Khi module trở thành library/starter

Một public library có thể dùng namespace:

~~~text
acme.payments.gateway-url
acme.payments.request-timeout
acme.payments.retry.max-attempts
~~~

Prefix mang tên capability hoặc vendor giúp tránh xung đột giữa nhiều libraries cùng nằm trong một app.

Module có thể đăng ký type qua:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AcmePaymentProperties.class)
public class AcmePaymentConfiguration {
}
~~~

Trong một Spring Boot starter, auto-configuration đúng chuẩn Spring Boot 3.x cần **@AutoConfiguration** và đăng ký class trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ @Configuration trên chỉ thể hiện registration, không phải toàn bộ code auto-configuration của starter.

### 30.1. Public config là API cần ổn định

Một prefix mà hàng chục ứng dụng dùng sẽ khó thay đổi hơn một prefix internal. Nên công bố deprecation, default, units, validation và migration khi thay tên.

### 30.2. Đừng expose implementation details

Tên:

~~~text
acme.payment.okhttp3.internal-worker-threads
~~~

có thể khóa public API vào một thư viện HTTP cụ thể. Tốt hơn nên expose behavior có ý nghĩa với người vận hành, ví dụ **max-connections** nếu đó thực sự là tham số người dùng cần.

## 31. Khi một capability có nhiều providers

Ví dụ payment có primary và backup:

~~~yaml
shop:
  checkout:
    payment:
      providers:
        primary:
          base-url: "https://primary.example.invalid"
          connect-timeout: 2s
        backup:
          base-url: "https://backup.example.invalid"
          connect-timeout: 3s
      failover:
        enabled: true
        max-switches: 1
~~~

Có thể giữ nested dưới payment nếu:

- Cùng team payment quản lý.
- Failover policy cần biết cả hai providers.
- Chúng cùng phục vụ một payment capability.
- Không cần inject provider configs vào các module không liên quan.

Nếu providers là integrations độc lập dùng cho nhiều domains, có thể cân nhắc nhóm riêng.

Nếu danh sách providers thay đổi, Map theo tên provider có thể phù hợp hơn hai field fixed primary/backup, nhưng phải xác định thứ tự fallback và ràng buộc cụ thể.

## 32. Tên field có thể lặp giữa các nhóm

Hoàn toàn bình thường:

~~~text
shop.checkout.payment.enabled
shop.notification.email.enabled

shop.checkout.payment.request-timeout
shop.notification.email.request-timeout
~~~

Không có xung đột vì prefix cung cấp ngữ cảnh.

Bên trong EmailProperties, field **enabled** rõ hơn **shopNotificationEmailEnabled**. Nhưng nếu một group có nhiều loại timeout, cần đặt tên rõ:

~~~text
connect-timeout
read-timeout
request-timeout
idle-timeout
~~~

Tên quá chung **timeout** ở một nhóm có nhiều giai đoạn dễ gây nhầm.

## 33. Dấu hiệu cần điều chỉnh ranh giới

Nên cân nhắc refactor khi:

1. Một config bean bị inject ở nhiều module không liên quan.
2. Class chứa hàng chục fields của nhiều capability.
3. Một team sửa property khiến test của team khác fail thường xuyên.
4. Secret của payment được truyền rộng chỉ vì object chứa mọi settings.
5. Một nested group có owner, consumer và lifecycle riêng.
6. Một module sắp được tách thành service/library độc lập.
7. Provider-specific rules làm object hiện tại quá phức tạp.
8. Prefix không phản ánh domain language nữa.
9. Deployment scripts khó xác định key thuộc chức năng nào.
10. Không ai chịu trách nhiệm rõ cho một nhóm cấu hình.
11. Validation cần đọc một lượng lớn field không liên quan.
12. Việc rollback một tính năng đòi hỏi rollback cả config của các tính năng khác.

Đừng refactor chỉ vì một class có nhiều hơn một con số fields tùy ý. Nếu tất cả cùng một trách nhiệm và có contract rõ, class tương đối lớn vẫn có thể hợp lý.

## 34. Mẫu tài liệu cho một configuration boundary

**Tên nhóm:** shop.checkout.payment

**Owner:** Payment Integration

**Mục tiêu:** điều khiển cách ứng dụng gọi payment gateway.

**Contract:**

| Key | Type | Default gợi ý | Có bắt buộc? |
| --- | --- | --- | --- |
| gateway-url | URI | Không | Có khi live |
| connect-timeout | Duration | 2s | Có/default |
| request-timeout | Duration | 8s | Có/default |
| retry.enabled | boolean | true | Có/default |
| retry.max-attempts | int | 3 | Có/default |
| retry.initial-delay | Duration | 250ms | Có/default |
| retry.max-delay | Duration | 3s | Có/default |
| api-key | secret/String | Không | Có khi live |

**Nguồn override:** Config Data, profile, OS env, system properties và CLI theo quy tắc Spring Boot.

**Validation:** timeout và retry hợp lệ; cần endpoint/key khi live.

**Security:** token đến từ secret source runtime, không ghi log.

**Versioning:** danh sách key cũ và kế hoạch migration nếu có.

Bảng như vậy giúp người vận hành sử dụng contract mà không cần hiểu toàn bộ implementation class.

## 35. Bài thực hành A — phân loại key theo trách nhiệm

Cho:

~~~text
app.url
app.payment-timeout
app.payment-api-key
app.inventory-cache-ttl
app.inventory-batch
app.email-enabled
app.email-token
app.low-stock-threshold
~~~

Hãy:

1. Xác định consumer của từng key.
2. Xác định owner và tần suất thay đổi.
3. Nhóm payment, inventory, email.
4. Đề xuất prefix mới.
5. Đánh dấu secret.
6. Chỉ định type và đơn vị.
7. Giải thích vì sao không dùng một AppProperties.

Ví dụ kết quả:

~~~text
shop.checkout.payment.gateway-url
shop.checkout.payment.request-timeout
shop.checkout.payment.api-key

shop.inventory.cache-ttl
shop.inventory.sync.batch-size
shop.inventory.low-stock-threshold

shop.notification.email.enabled
shop.notification.email.api-token
~~~

## 36. Bài thực hành B — tách một AppProperties lớn

1. Tạo AppProperties chứa các key ví dụ.
2. Tạo PaymentProperties, InventoryProperties, EmailProperties.
3. Chuyển field vào type phù hợp.
4. Đăng ký qua @ConfigurationPropertiesScan.
5. Chuyển constructor của service sang nhóm cần thiết.
6. Thêm Bean Validation cho ràng buộc độc lập.
7. Test binding từng nhóm.
8. Kiểm tra không log record có secret.

**Mục tiêu:** thấy lợi ích kiến trúc vượt qua việc sắp lại YAML.

## 37. Bài thực hành C — nested hay bean độc lập?

Đánh giá:

~~~text
payment.retry.*
payment.fraud-detection.*
notification.email.*
~~~

Hãy xác định:

- Retry chỉ là một phần payment client?
- Fraud detection có owner và lifecycle độc lập không?
- Email có được dùng ở nhiều luồng khác checkout không?
- Những giá trị nào thường deploy thay đổi cùng nhau?

Một kết quả hợp lý:

- **payment.retry** nested trong PaymentProperties.
- **payment.fraud-detection** tách bean nếu thật sự là subsystem độc lập.
- **notification.email** là EmailProperties riêng.

## 38. Bài thực hành D — shared default và override riêng

1. Tạo một default connect timeout thuộc platform HTTP factory.
2. Payment và Inventory vẫn giữ key timeout riêng.
3. Cho phép lấy default platform nếu thiếu override.
4. Đổi timeout payment và giữ inventory không đổi.
5. Test cả hai client cùng lúc.

**Mục tiêu:** không biến giống giá trị mặc định thành phụ thuộc buộc chặt.

## 39. Bài thực hành E — migration prefix

1. Chuyển **app.payment-timeout** sang **shop.checkout.payment.request-timeout**.
2. Liệt kê các file/manifest liên quan.
3. Định nghĩa precedence old/new.
4. Viết compatibility layer nếu phải hỗ trợ cả hai.
5. Test old-only, new-only, both và neither.
6. Ghi metadata deprecation khi phù hợp.
7. Ghi lịch ngừng hỗ trợ key cũ.

**Mục tiêu:** quản lý property name như một public external contract.

## 40. Bài thực hành F — test theo module

1. Dùng ApplicationContextRunner cho InventoryProperties.
2. Chỉ cấp key inventory.
3. Assert conversion Duration và int.
4. Tạo runner riêng cho PaymentProperties.
5. Thử thiếu required property/vi phạm constraint.
6. Đảm bảo inventory tests không cần payment token.
7. Bổ sung integration test wiring nếu cần.

**Mục tiêu:** giảm test setup khi các module thật sự độc lập.

## 41. Checklist thiết kế ranh giới mới

Trước khi thêm hoặc đổi một configuration group:

- Group có capability/technical responsibility rõ ràng không?
- Ai là owner của các key?
- Những consumers nào cần group này?
- Các field có thay đổi cùng nhau không?
- Các field có cross-field validation không?
- Có field không liên quan bị nhét vì cùng file không?
- Có tạo một bean quá nhỏ chỉ cho một primitive không?
- Nested group có cùng lifecycle với parent không?
- Prefix có phản ánh domain vocabulary ổn định không?
- Có cần dùng key framework thay vì custom key không?
- Các field Duration/URI/DataSize/enum đã có type chính xác chưa?
- Tên key có mô tả unit và ý nghĩa timeout không?
- Default có an toàn cho các môi trường không?
- Feature disabled có được phép thiếu một số field không?
- Có secret không và nó được cấp qua nguồn runtime nào?
- Có module nào đang inject object chứa secret không cần thiết không?
- Validation có nằm ở owner thích hợp không?
- Quan hệ liên module có được kiểm tra ở orchestration layer không?
- Có AppProperties toàn cục quá lớn không?
- Có shared default nào chỉ là sự trùng hợp hiện tại không?
- Có List/Map cần cân nhắc override behavior không?
- Key có bị dùng trong Helm, CI, Terraform hoặc ConfigMap không?
- Nếu đổi key, đã có migration plan chưa?
- Configuration metadata/documentation có đầy đủ không?
- Có test binding/validation độc lập cho từng group không?
- Có test tích hợp cho giá trị từ profile/env/runtime secret không?

## 42. Tổng kết

- Chọn **ranh giới nhóm cấu hình theo trách nhiệm chức năng** giúp cohesion cao, coupling thấp và ownership rõ.
- **@ConfigurationProperties** phù hợp để bind một namespace thành Java object có kiểu và validation.
- **File và môi trường không phải ranh giới chức năng**; cùng một group có thể nhận giá trị từ nhiều PropertySources.
- Tránh một **AppProperties** chứa mọi thứ và tránh chia một primitive thành một bean riêng nếu không cần.
- Nested record phù hợp với nhóm con chỉ tồn tại trong parent, còn capability độc lập nên có configuration bean riêng.
- Giống default không có nghĩa nên chia sẻ cùng property key; chỉ chia sẻ khi có policy owner thực.
- Secret key nằm dưới namespace của consumer nhưng security thực sự ở runtime/secret infrastructure.
- Validation nên được thực hiện trong module sở hữu quy tắc; quy tắc cross-module thuộc orchestration layer.
- Prefix là **external configuration API** được deployment sử dụng; đổi tên cần kế hoạch migration và test.
- Relaxed binding hỗ trợ các biến thể cách viết, **không tự alias hai key khác nghĩa**.
- Configuration metadata hỗ trợ IDE và docs, không thay runtime validation/compatibility.
- Một group được thiết kế tốt có thể được kiểm thử và di chuyển cùng module, thuận tiện cho phát triển lâu dài.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, Type-safe Configuration Properties, Relaxed Binding và Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Boot 3.3 API — NestedConfigurationProperty: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/NestedConfigurationProperty.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Framework — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
