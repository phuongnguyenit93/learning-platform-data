# NoSuchBeanDefinitionException: bean thiếu hoặc nằm ngoài phạm vi đăng ký

> **Spring Boot Fundamentals · Chẩn đoán lỗi**  
> `NoSuchBeanDefinitionException` xuất hiện khi Spring cần tìm một bean theo tên hoặc kiểu nhưng không tìm thấy bean phù hợp trong `BeanFactory`/`ApplicationContext` đang được truy vấn. Trong ứng dụng Spring Boot, nguyên nhân thường không phải “Spring bị lỗi”, mà là bean chưa được đăng ký, cấu hình tạo bean không được kích hoạt, component nằm ngoài phạm vi scan, dependency không có trên classpath, hoặc code đang tìm bean bằng sai tên/kiểu. Muốn sửa đúng, hãy xác định **ai đang yêu cầu bean, context nào đang được hỏi, bean đáng lẽ được tạo bởi cơ chế nào và điều kiện đăng ký đó có thực sự thỏa mãn không**.

## 1. Ý nghĩa của NoSuchBeanDefinitionException

Spring quản lý object thông qua container. Một object được đăng ký vào container có thể được gọi là **bean**. Khi một component cần dependency, Spring tìm bean tương thích để inject. Nếu không có bean phù hợp, quá trình khởi tạo hoặc tra cứu có thể thất bại.

Ví dụ:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Nếu không có bean nào implement `PaymentGateway` và được đăng ký trong context, Spring không thể tạo `CheckoutService`. Lỗi có thể hiển thị dưới dạng `UnsatisfiedDependencyException` ở lớp ngoài và có `NoSuchBeanDefinitionException` ở cause chain.

Một trường hợp khác là code tự tra cứu:

```java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
```

Nếu context không có bean tương ứng, thao tác này có thể ném `NoSuchBeanDefinitionException` trực tiếp.

### 1.1. Thông báo lỗi thường gặp

Ví dụ:

```text
No qualifying bean of type
'com.example.payment.PaymentGateway' available
```

Hoặc:

```text
No bean named 'paymentGateway' available
```

Hai thông báo chỉ ra hai kiểu lookup khác nhau:

- **Lookup theo type:** Spring cần một bean có kiểu tương thích với `PaymentGateway`.
- **Lookup theo name:** Spring cần một bean có tên chính xác `paymentGateway`.

Nếu lookup theo type không có bean, có thể do bean chưa tồn tại hoặc không tương thích. Nếu lookup theo name thất bại, bean có thể tồn tại nhưng tên khác.

### 1.2. Lỗi thường xuất hiện ở đâu?

`NoSuchBeanDefinitionException` có thể xuất hiện khi:

- Spring khởi tạo một bean và không tìm được constructor dependency.
- Một `@Bean` method yêu cầu bean khác nhưng context không có bean đó.
- Code gọi `ApplicationContext.getBean(...)`.
- Một component dùng `@Autowired` hoặc `@Resource` nhưng dependency không được đăng ký phù hợp.
- Auto-configuration hoặc test configuration kỳ vọng một bean nhưng điều kiện không được thỏa.
- Một context con tìm bean không có trong phạm vi mà nó nhìn thấy.

Không nên chỉ đọc dòng đầu stack trace. Thường cần xem **bean nào đang được tạo**, **dependency nào đang thiếu** và **context nào thực hiện lookup**.

## 2. Phân biệt các exception gần giống nhau

Các lỗi liên quan bean có tên khá giống nhưng nguyên nhân khác nhau.

| Exception | Ý nghĩa |
| --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với yêu cầu lookup |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng Spring không thể chọn duy nhất |
| `UnsatisfiedDependencyException` | Một dependency không thể được thỏa mãn khi tạo bean; có thể bọc nguyên nhân sâu hơn |
| `BeanCreationException` | Bean không thể được tạo; nguyên nhân có thể là dependency, constructor, init method, binding hoặc lỗi khác |
| `BeanCurrentlyInCreationException` | Thường liên quan dependency cycle hoặc truy cập bean đang tạo |
| `NoSuchBeanDefinitionException: No bean named ...` | Không tìm thấy bean theo tên được yêu cầu |

### 2.1. Không có bean và có quá nhiều bean là hai tình huống ngược nhau

Giả sử:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
```

Nếu không có implementation nào được đăng ký, Spring có thể báo thiếu bean.

Nếu có hai implementation:

```java
@Component
class StripeGateway implements PaymentGateway {
    // ...
}

@Component
class SandboxGateway implements PaymentGateway {
    // ...
}
```

và một service inject `PaymentGateway` mà không có lựa chọn rõ ràng, lỗi thường là `NoUniqueBeanDefinitionException` chứ không phải `NoSuchBeanDefinitionException`.

### 2.2. Đọc root cause, không chỉ exception ngoài cùng

Ví dụ:

```text
UnsatisfiedDependencyException
  └── NoSuchBeanDefinitionException:
      No qualifying bean of type 'PaymentGateway'
```

Thông tin quan trọng nằm ở cause: thiếu `PaymentGateway`.

Nhưng cũng có trường hợp:

```text
BeanCreationException
  └── IllegalStateException:
      Could not resolve placeholder 'payment.endpoint'
```

Đây không phải lỗi thiếu bean. Bean đã được Spring tìm thấy, nhưng quá trình tạo bean thất bại vì property cấu hình thiếu.

**Hãy phân biệt lỗi tìm bean với lỗi khởi tạo bean.**

## 3. Spring biết một bean từ đâu?

Spring có nhiều cách đăng ký bean. Những cơ chế thường gặp:

1. Component scanning tìm class có stereotype annotation.
2. Configuration class khai báo method `@Bean`.
3. `@Import` đưa configuration hoặc component vào context.
4. Spring Boot auto-configuration tạo bean theo điều kiện.
5. Spring Test thêm hoặc thay thế bean cho test.
6. Code đăng ký bean lập trình qua registry/context trong những trường hợp chuyên biệt.

### 3.1. Component stereotype

Các annotation phổ biến:

| Annotation | Ý nghĩa |
| --- | --- |
| `@Component` | Đánh dấu class là Spring-managed component |
| `@Service` | Stereotype thường dùng cho service |
| `@Repository` | Stereotype cho persistence component, có thể tham gia exception translation |
| `@Controller` | Spring MVC controller |
| `@RestController` | Controller trả response body theo mặc định |
| `@Configuration` | Class định nghĩa bean/configuration |
| `@ControllerAdvice` | Advice component cho controller |
| `@ConfigurationProperties` | Đánh dấu class mô hình cấu hình; cần đăng ký qua scan hoặc enable mechanism |

Ví dụ:

```java
@Repository
public class JdbcOrderRepository implements OrderRepository {
    // ...
}
```

Annotation stereotype giúp component scan nhận diện class, nhưng **chỉ có annotation chưa đảm bảo bean được tạo**. Package của class phải nằm trong vùng scan hoặc class phải được đăng ký bằng cách khác.

### 3.2. Bean method với `@Bean`

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxGateway();
    }
}
```

Khi `PaymentConfiguration` được import/scan vào context, method `@Bean` có thể đăng ký bean theo tên mặc định `paymentGateway`.

Nếu configuration class không được phát hiện hoặc import, bean method không được xử lý trong context đó.

### 3.3. Đăng ký qua `@Import`

```java
@Configuration(proxyBeanMethods = false)
@Import(PaymentConfiguration.class)
public class ApplicationIntegrationConfiguration {
}
```

`@Import` có thể đưa configuration class hoặc một số loại component phù hợp vào context. Cách này hữu ích khi muốn module cung cấp một cấu hình rõ ràng thay vì dựa hoàn toàn vào package scan.

### 3.4. Spring Boot auto-configuration

Một starter có thể cung cấp auto-configuration tạo bean:

```java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnMissingBean(PaymentGateway.class)
public class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentClient client) {
        return new RemotePaymentGateway(client);
    }
}
```

Bean chỉ được tạo nếu điều kiện phù hợp. Nếu class `PaymentClient` không có trên classpath, hoặc người dùng đã cung cấp bean khác, auto-configuration có thể không tạo bean mặc định.

Spring Boot 3 dùng file đăng ký auto-configuration:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu auto-configuration class không được liệt kê hoặc import đúng, nó có thể không được phát hiện khi ứng dụng khởi động.

## 4. Nguyên nhân phổ biến nhất: component nằm ngoài phạm vi scan

Đây là lỗi thường gặp khi cấu trúc package không được tổ chức theo root application.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── order
│   └── OrderService.java
└── payment
    └── PaymentGatewayImpl.java
```

Application root:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Theo mặc định, `@SpringBootApplication` thực hiện component scan từ package của class được đánh dấu và các package con. Vì `com.example.shop.order` và `com.example.shop.payment` là package con, các component phù hợp có thể được phát hiện.

### 4.1. Đặt application class quá sâu

Ví dụ:

```text
com.example.shop
└── bootstrap
    └── ShopApplication.java
com.example.shop.payment
    └── PaymentGatewayImpl.java
```

Nếu `ShopApplication` ở `com.example.shop.bootstrap`, component scan mặc định bắt đầu từ package này và các package con, không tự động quét ngược lên `com.example.shop.payment`.

Bean `PaymentGatewayImpl` nằm ngoài phạm vi scan.

### 4.2. Cách sửa: đặt root application ở package cha

Cách thường dễ duy trì nhất:

```text
com.example.shop
├── ShopApplication.java
├── bootstrap/
├── order/
├── payment/
└── customer/
```

Đặt class `@SpringBootApplication` ở package gốc của ứng dụng giúp scan các module con theo quy ước rõ ràng.

### 4.3. Cách sửa: chỉ định `scanBasePackages`

Nếu cấu trúc package cần giữ:

```java
@SpringBootApplication(
        scanBasePackages = {
            "com.example.shop.bootstrap",
            "com.example.shop.order",
            "com.example.shop.payment"
        }
)
public class ShopApplication {
}
```

Cách này có thể giải quyết component scan, nhưng cần cẩn thận vì mở rộng phạm vi scan có thể phát hiện thêm bean ngoài dự kiến.

### 4.4. `scanBasePackages` không thay thế mọi cơ chế scan khác

Một chi tiết quan trọng: thuộc tính `scanBasePackages` của `@SpringBootApplication` chủ yếu cấu hình component scan. Nó không tự động điều khiển mọi cơ chế scan khác, ví dụ JPA entity scanning hoặc Spring Data repository scanning trong mọi cấu hình.

Nếu thiếu JPA repository hoặc entity, có thể cần `@EnableJpaRepositories`, `@EntityScan` hoặc cấu hình package phù hợp tùy kiến trúc. Đừng giả định một thay đổi component scan luôn giải quyết toàn bộ các loại registry.

## 5. Class có annotation nhưng bean vẫn không tồn tại

Hãy kiểm tra từng điều kiện:

### 5.1. Annotation có đúng không?

Ví dụ class:

```java
public class PaymentGatewayImpl implements PaymentGateway {
}
```

Class không có stereotype, không được khai báo qua `@Bean`, không được import và không có cơ chế đăng ký khác. Vì vậy, Spring không tự biết cần tạo bean này.

Có thể sửa:

```java
@Component
public class PaymentGatewayImpl implements PaymentGateway {
}
```

hoặc khai báo bằng `@Bean` trong configuration.

### 5.2. Class có phải class mà Spring có thể quản lý không?

Một số kiểu khai báo có thể không phù hợp với component scanning hoặc proxying theo cách mong đợi:

- Class nằm trong package không được scan.
- Class không có stereotype và không được import.
- Class là inner class không static hoặc cấu trúc đặc biệt không phù hợp với cách tạo bean.
- Class abstract không có implementation cụ thể để instantiate.
- Constructor cần dependency khác cũng đang thiếu.
- Class bị loại bởi filter của component scan.

Spring không tự tạo bean cho mọi class có trong classpath. Classpath chứa bytecode; container chỉ quản lý bean được đăng ký theo cơ chế của nó.

### 5.3. Constructor dependency tiếp tục thiếu

Ví dụ:

```java
@Component
public class PaymentGatewayImpl implements PaymentGateway {

    public PaymentGatewayImpl(PaymentClient client) {
        // ...
    }
}
```

Dù `PaymentGatewayImpl` đã được scan, Spring vẫn không thể tạo nó nếu `PaymentClient` không có bean tương ứng.

Stack trace có thể nói bean `paymentGatewayImpl` không được tạo vì dependency `PaymentClient` thiếu. Đừng chỉ thêm annotation vào implementation đầu tiên; hãy lần theo dependency chain đến bean thiếu đầu tiên.

## 6. Bean bị loại bởi profile

`@Profile` giới hạn bean theo profile đang active.

Ví dụ:

```java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Nếu ứng dụng chạy với profile `test` hoặc không active `prod`, configuration này không được áp dụng. Khi đó bean `PaymentGateway` có thể không tồn tại.

### 6.1. Kiểm tra profile active

Trong code:

```java
@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                Arrays.toString(environment.getActiveProfiles()));
    }
}
```

Trong test:

```java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {
}
```

Nếu chỉ có configuration `@Profile("prod")`, test profile không tạo bean đó.

### 6.2. Profile mặc định và profile active

Nếu không khai báo profile active, Spring có thể dùng default profile. Không nên giả định `default` và `prod` giống nhau.

Kiểm tra các nguồn:

- `spring.profiles.active`.
- `spring.profiles.default`.
- `@ActiveProfiles` trong test.
- Biến môi trường `SPRING_PROFILES_ACTIVE`.
- Command-line argument.
- Profile group hoặc include configuration nếu có.

### 6.3. Một bean cho mỗi môi trường

Có thể định nghĩa implementation riêng:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("test")
    PaymentGateway testPaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway productionPaymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Khi profile là `test` hoặc `prod`, bean tương ứng mới được đăng ký. Nếu không active profile nào phù hợp, có thể không có bean nào.

Có thể cung cấp fallback cho profile mặc định hoặc dùng condition khác nếu yêu cầu ứng dụng cần bean ở mọi môi trường.

## 7. Bean bị loại bởi conditional annotations

Spring Boot auto-configuration và cấu hình ứng dụng thường dùng conditions để chỉ tạo bean khi điều kiện đúng.

### 7.1. `@ConditionalOnProperty`

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Nếu `app.payment.enabled` thiếu hoặc không có giá trị phù hợp, configuration có thể không được kích hoạt.

Kiểm tra file config:

```yaml
app:
  payment:
    enabled: true
```

Cũng kiểm tra nguồn ưu tiên cao hơn có ghi đè giá trị thành false không.

### 7.2. `matchIfMissing`

```java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

Với `matchIfMissing=true`, condition có thể khớp khi property không tồn tại, theo semantics của annotation. Không dùng thuộc tính này nếu thiếu cấu hình phải được coi là lỗi hoặc tính năng mặc định phải tắt.

### 7.3. `@ConditionalOnClass`

```java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
public class PaymentAutoConfiguration {
    // ...
}
```

Nếu class được yêu cầu không có trên classpath runtime, auto-configuration không được kích hoạt.

Có thể kiểm tra bằng dependency tree hoặc inspect artifact. Một dependency chỉ có ở compile/test nhưng thiếu runtime cũng có thể dẫn đến tình huống tương tự.

### 7.4. `@ConditionalOnMissingBean`

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new SandboxPaymentGateway();
}
```

Bean mặc định chỉ được tạo nếu chưa có bean phù hợp. Nếu ứng dụng đã đăng ký một implementation khác, việc bean mặc định vắng mặt là **hành vi đúng**.

Nếu một component lại tìm bean theo tên `paymentGateway` cụ thể trong khi bean tùy chỉnh mang tên khác, lookup theo tên có thể thất bại dù một `PaymentGateway` khác đang tồn tại.

### 7.5. Condition khác

Một số annotation khác:

- `@ConditionalOnBean`.
- `@ConditionalOnMissingBean`.
- `@ConditionalOnClass`.
- `@ConditionalOnMissingClass`.
- `@ConditionalOnResource`.
- `@ConditionalOnExpression`.
- `@ConditionalOnWebApplication`.
- `@ConditionalOnNotWebApplication`.
- `@ConditionalOnSingleCandidate`.

Khi bean không xuất hiện, đừng chỉ tìm `@Component`. Hãy tìm toàn bộ configuration class, import và condition có thể quyết định việc đăng ký bean.

## 8. Configuration class chưa được import hoặc phát hiện

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    MessagePublisher messagePublisher() {
        return new InMemoryMessagePublisher();
    }
}
```

Nếu class `MessagingConfiguration` nằm ngoài component scan và không được import, `messagePublisher` sẽ không tồn tại.

### 8.1. Dùng `@Import`

```java
@SpringBootApplication
@Import(MessagingConfiguration.class)
public class ShopApplication {
}
```

Hoặc import trong một configuration khác đã được đăng ký.

### 8.2. Kiểm tra cấu hình module

Trong multi-module project:

```text
shop-app
├── ShopApplication
└── dependencies:
    ├── shop-core
    └── shop-messaging
```

Chỉ thêm dependency `shop-messaging` vào build chưa chắc các configuration của module tự được phát hiện. Nếu module được thiết kế như library thông thường, nó có thể cần:

- Component scan phù hợp.
- `@Import` từ application.
- Auto-configuration được đăng ký theo cơ chế Spring Boot.
- Một starter kéo module auto-configuration vào classpath.

Đừng nhầm **có JAR trong dependency graph** với **configuration trong JAR đã được import**.

### 8.3. Library auto-configuration cần khai báo entry

Trong Spring Boot 3, auto-configuration class thường được đăng ký trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung:

```text
com.acme.messaging.autoconfigure.MessagingAutoConfiguration
```

Nếu file bị thiếu, sai tên class, không được đóng gói hoặc dependency không có trên runtime classpath, Boot có thể không load auto-configuration như mong muốn.

## 9. `@ConfigurationProperties` chưa được đăng ký thành bean

Đây là một nguyên nhân riêng thường bị bỏ sót.

Ví dụ:

```java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;
    // getters/setters
}
```

`@ConfigurationProperties` mô tả cách bind external properties vào class. Nó **không phải một stereotype tương đương `@Component`** trong cách sử dụng thông thường.

Cần đăng ký class bằng một cơ chế phù hợp.

### 9.1. `@ConfigurationPropertiesScan`

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
```

Boot scan các lớp configuration properties theo phạm vi scan phù hợp.

### 9.2. `@EnableConfigurationProperties`

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
```

Cách này đăng ký rõ một hoặc nhiều properties class.

### 9.3. Thiếu registration dẫn tới bean không tồn tại

Nếu một service inject `PaymentProperties` mà class chỉ có `@ConfigurationProperties`, chưa được scan/enable, Spring có thể báo không tìm thấy bean.

Không nên giải quyết bằng cách gắn thêm `@Component` một cách tùy tiện cho mọi properties class. Hãy dùng cơ chế registration nhất quán với kiến trúc cấu hình của project.

## 10. Sai tên bean hoặc sai kiểu lookup

Một bean có thể tồn tại nhưng code đang tìm bằng định danh khác.

### 10.1. Tên mặc định của bean

Ví dụ:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {
}
```

Tên bean mặc định theo quy tắc component naming thường là tên class với chữ cái đầu viết thường:

```text
remotePaymentGateway
```

Không mặc định bean này tên là `paymentGateway` chỉ vì class implement interface `PaymentGateway`.

### 10.2. Đặt tên rõ ràng

```java
@Component("paymentGateway")
public class RemotePaymentGateway implements PaymentGateway {
}
```

Hoặc:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway remotePaymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Nếu code cần lookup theo name, tên phải khớp với bean definition thực tế.

### 10.3. Ưu tiên inject theo type

Thông thường:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

dễ refactor hơn:

```java
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Lookup theo name chỉ nên dùng khi tên bean có ý nghĩa thực sự, ví dụ registry chọn implementation theo key. Nếu chỉ cần dependency interface, constructor injection theo type thường phù hợp hơn.

### 10.4. Generic type có thể ảnh hưởng matching

Một số bean có generic type hoặc factory type phức tạp. Spring có thể dùng generic metadata để phân biệt các candidate.

Ví dụ:

```java
public interface Handler<T> {
    void handle(T value);
}

@Component
class OrderHandler implements Handler<Order> {
    public void handle(Order value) {
    }
}

@Component
class InvoiceHandler implements Handler<Invoice> {
    public void handle(Invoice value) {
    }
```

Khi yêu cầu `Handler<Order>`, generic metadata có thể tham gia xác định candidate. Nhưng khi code làm mất generic type hoặc lookup raw `Handler.class`, kết quả có thể rộng hơn mong đợi và dẫn đến ambiguity hoặc không tìm được bean theo type cụ thể.

## 11. Bean có tồn tại trong context khác

Một ứng dụng có thể có nhiều `ApplicationContext`, chẳng hạn parent/child context, servlet web context, test context hierarchy hoặc context được tạo thủ công.

Bean ở context này không nhất thiết nhìn thấy từ context khác.

### 11.1. Parent và child context

Trong hierarchy:

```text
Parent ApplicationContext
    ├── shared infrastructure beans
    └── Child WebApplicationContext
            ├── controllers
            └── web-specific beans
```

Child context thường có thể tra cứu bean từ parent. Parent không tự nhìn thấy bean chỉ được đăng ký ở child.

Nếu code truy vấn parent để tìm một controller chỉ tồn tại trong web child, lookup có thể thất bại.

### 11.2. Servlet context và root context

Một số cấu hình web truyền thống dùng root WebApplicationContext và child context cho servlet. Khi migration hoặc tích hợp framework cũ, cần xác định bean được đăng ký ở context nào và request đang sử dụng context nào.

Đừng giả định mọi bean của toàn bộ web application đều nằm trong một registry phẳng duy nhất.

### 11.3. Test context hierarchy

Spring Test hỗ trợ context hierarchy trong những test đặc biệt. Nếu bean nằm ở một context child nhưng test inject từ parent, hoặc cấu hình test tạo hierarchy không như mong muốn, lỗi lookup có thể xuất hiện.

Khi dùng `@ContextHierarchy`, hãy xem rõ từng configuration class thuộc level nào.

### 11.4. Context tự tạo thủ công

Nếu code tự tạo:

```java
ApplicationContext context =
        new AnnotationConfigApplicationContext(
                SomeConfiguration.class);
```

đó là một container độc lập. Nó không tự có mọi bean của Spring Boot application context đang chạy.

Nếu cần bean từ ứng dụng, nên inject context/bean phù hợp từ container hiện tại thay vì tự tạo một context thứ hai không có cùng configuration.

## 12. Test slice không tải toàn bộ application beans

Một lỗi phổ biến trong test:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    OrderService orderService;
}
```

`@WebMvcTest` là slice test tập trung vào Spring MVC. Nó không tự động tạo toàn bộ service/repository graph như full application context. Vì vậy, `OrderService` có thể không tồn tại trong test context.

### 12.1. Mock dependency của controller

Nếu mục tiêu là kiểm tra controller:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
```

`@MockitoBean` phù hợp với Spring Framework mới có bean override support. Với Spring Boot 3.x cũ hơn, project thường dùng `@MockBean`; cần chọn theo version đang chạy.

### 12.2. Dùng `@SpringBootTest` khi cần toàn bộ wiring

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    MockMvc mockMvc;
}
```

Cách này dựng context rộng hơn và có thể tạo service thật cùng các dependency cần thiết theo test configuration.

Không nên biến mọi `@WebMvcTest` thành `@SpringBootTest` chỉ để làm mất lỗi bean thiếu. Nếu slice test được thiết kế đúng, mock dependency ngoài slice là hành vi mong đợi.

### 12.3. `@DataJpaTest` cũng là slice

`@DataJpaTest` tập trung vào JPA/repository infrastructure. Một service business thông thường có thể không được scan vào context này.

Nếu repository test cần một helper, hãy import cấu hình cần thiết hoặc giữ test đúng phạm vi. Đừng kỳ vọng mọi bean từ `@SpringBootApplication` tự động có mặt trong mọi test slice.

### 12.4. Test bean overrides có thể thay đổi graph

`@MockBean`/`@MockitoBean` có thể thêm hoặc thay thế bean trong test context. Nếu dùng qualifier hoặc tên cụ thể, phải bảo đảm override khớp bean mà code đang yêu cầu.

## 13. Auto-configuration bị loại hoặc không được import

Spring Boot tạo nhiều bean dựa trên dependency và điều kiện.

Ví dụ application có:

```java
@Autowired
ObjectMapper objectMapper;
```

Nếu Jackson không có trên classpath hoặc auto-configuration liên quan không được kích hoạt, bean có thể thiếu trong một context tùy biến.

### 13.1. Kiểm tra dependency runtime

Kiểm tra Maven:

```bash
./mvnw dependency:tree
```

Hoặc Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Nếu dependency chỉ ở `testImplementation` hoặc Maven `test` scope, ứng dụng runtime không có class cần thiết để kích hoạt auto-configuration.

### 13.2. Kiểm tra auto-configuration report

Có thể bật debug:

```properties
debug=true
```

Hoặc chạy ứng dụng với tùy chọn debug phù hợp để Spring Boot in Condition Evaluation Report.

Report cho biết auto-configuration nào match hoặc không match, thường kèm lý do như:

- Class không có trên classpath.
- Property không khớp.
- Bean khác đã tồn tại.
- Web application type không phù hợp.
- Configuration bị exclude.

Đây là một trong những công cụ hữu ích nhất khi bean mặc định của Spring Boot không xuất hiện.

### 13.3. Kiểm tra exclusions

Ứng dụng có thể loại auto-configuration qua:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ShopApplication {
}
```

Hoặc property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Nếu bean bạn đang cần do auto-configuration bị exclude tạo ra, việc thiếu bean là hệ quả trực tiếp của cấu hình.

### 13.4. `@ConditionalOnMissingBean` có thể khiến bean mặc định không tạo

Đừng coi một auto-configuration “không tạo bean” là lỗi ngay lập tức. Có thể ứng dụng đã cung cấp custom bean thay thế. Hãy kiểm tra danh sách bean theo type và tên trước khi sửa.

## 14. Bean factory, factory method và bean product

Không phải mọi bean đều được tạo trực tiếp từ class có stereotype.

### 14.1. Factory method

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    PaymentClient paymentClient() {
        return new PaymentClient("https://payments.example.test");
    }
}
```

Bean được đăng ký từ method `@Bean`. Nếu configuration không được load, bean không xuất hiện.

### 14.2. `FactoryBean`

Spring có abstraction `FactoryBean<T>` để một factory tạo object mà container quản lý như bean product.

```java
public class ClientFactoryBean
        implements FactoryBean<PaymentClient> {

    @Override
    public PaymentClient getObject() {
        return new PaymentClient("https://payments.example.test");
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentClient.class;
    }
}
```

Nếu đăng ký `ClientFactoryBean` với tên `paymentClient`, tra cứu `paymentClient` thông thường trả factory product; tra cứu `&paymentClient` trả factory itself.

Nếu code lookup sai tên hoặc nhầm factory với product, có thể gặp lỗi lookup/type không như mong muốn.

### 14.3. Bean có thể được tạo trễ

Một bean `@Lazy` hoặc singleton lazy có thể chưa được khởi tạo trước khi được yêu cầu. Nhưng lazy initialization không đồng nghĩa bean definition không tồn tại.

Phân biệt:

- **Bean definition missing:** container chưa có định nghĩa bean.
- **Bean instance chưa được tạo:** definition tồn tại nhưng instance được tạo trễ.
- **Bean creation failed:** definition tồn tại nhưng tạo instance gặp lỗi.

`NoSuchBeanDefinitionException` thường hướng về lookup không tìm thấy definition/candidate, trong khi lỗi tạo instance có exception khác.

## 15. Optional dependency và cách xử lý khi bean không bắt buộc

Không phải dependency nào cũng bắt buộc phải tồn tại trong mọi môi trường.

### 15.1. `Optional<T>`

```java
@Service
public class ReportService {

    private final Optional<ExportClient> exportClient;

    public ReportService(Optional<ExportClient> exportClient) {
        this.exportClient = exportClient;
    }

    public void exportIfAvailable() {
        exportClient.ifPresent(ExportClient::export);
    }
}
```

Nếu không có `ExportClient`, Spring có thể inject `Optional.empty()`.

### 15.2. `ObjectProvider<T>`

```java
@Service
public class ReportService {

    private final ObjectProvider<ExportClient> exportClientProvider;

    public ReportService(
            ObjectProvider<ExportClient> exportClientProvider) {
        this.exportClientProvider = exportClientProvider;
    }

    public void exportIfAvailable() {
        ExportClient client = exportClientProvider.getIfAvailable();

        if (client != null) {
            client.export();
        }
    }
}
```

`ObjectProvider` hỗ trợ tra cứu theo nhu cầu, có thể phù hợp với dependency tùy chọn hoặc lazy lookup.

Các method khác nhau có semantics khác nhau:

- `getObject()` yêu cầu bean tồn tại; nếu không có sẽ lỗi.
- `getIfAvailable()` trả null khi không có bean, nhưng vẫn có thể báo lỗi nếu có nhiều candidate không thể chọn.
- `getIfUnique()` trả bean khi có một candidate rõ ràng; hành vi khi không unique khác với getIfAvailable.

Đừng dùng provider chỉ để che một dependency đáng lẽ bắt buộc. Nếu service không thể hoạt động khi thiếu dependency, constructor injection trực tiếp thường giúp fail fast và rõ ràng hơn.

### 15.3. `@Autowired(required = false)`

```java
@Autowired(required = false)
private ExportClient exportClient;
```

Có thể dùng injection tùy chọn trong một số trường hợp, nhưng field injection làm dependency khó nhìn thấy và test hơn. Constructor injection với `Optional<T>` hoặc `ObjectProvider<T>` thường diễn đạt rõ ý định hơn.

### 15.4. Optional không sửa lỗi cấu hình sai

Nếu `PaymentGateway` là bắt buộc để xử lý thanh toán, biến nó thành optional chỉ khiến ứng dụng khởi động trong trạng thái không thể thực hiện nghiệp vụ. Hãy phân loại dependency:

- Bắt buộc: inject trực tiếp và fail fast.
- Tùy chọn: biểu diễn optional và xác định behavior khi vắng mặt.
- Theo môi trường: cung cấp bean theo profile/condition và kiểm tra mỗi môi trường có implementation phù hợp.

## 16. Qualifier, Primary và tên bean: khi bean có nhưng không được chọn

Mặc dù lỗi nhiều candidate thường là `NoUniqueBeanDefinitionException`, cấu hình sai qualifier hoặc tên có thể làm Spring không tìm được bean theo tiêu chí đã chỉ định.

### 16.1. `@Qualifier`

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("remotePaymentGateway")
            PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Bean phải có qualifier/name phù hợp. Nếu implementation được đăng ký với tên khác, hoặc qualifier không khớp, Spring có thể không tìm được candidate thỏa điều kiện.

### 16.2. `@Primary`

```java
@Component
@Primary
class RemotePaymentGateway implements PaymentGateway {
}
```

`@Primary` đánh dấu candidate ưu tiên khi có nhiều bean cùng type. Nó không tạo bean mới và không sửa một bean chưa được đăng ký.

### 16.3. Custom qualifier annotation

```java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RemotePayment {
}
```

Dùng:

```java
@Component
@RemotePayment
class RemotePaymentGateway implements PaymentGateway {
}
```

```java
public CheckoutService(@RemotePayment PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Nếu custom qualifier đặt sai vị trí hoặc không có bean nào mang qualifier đó, Spring không thể resolve dependency.

## 17. Phạm vi đăng ký của repository và entity khác component scan

Một số người sửa component scan nhưng vẫn thiếu repository hoặc entity vì chúng được quản lý bởi cơ chế chuyên biệt.

### 17.1. Spring Data repository

Ví dụ:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
```

Spring Data tạo proxy bean cho repository interface khi repository scanning được cấu hình phù hợp.

Trong Spring Boot app thông thường, auto-configuration và package của application root có thể giúp phát hiện repository theo quy ước. Nhưng khi repository nằm ở module/package khác, có thể cần:

```java
@EnableJpaRepositories(
        basePackages = "com.example.shared.persistence"
)
```

Nếu repository không được tạo, hãy kiểm tra:

- Spring Data dependency có trên classpath không?
- JPA repositories có được enable không?
- Package scan có bao phủ interface không?
- Interface có đúng dạng repository không?
- Có profile/condition hoặc configuration exclude không?

### 17.2. JPA entity

Entity không phải Spring bean thông thường. `@Entity` đánh dấu type được persistence provider quản lý, không đồng nghĩa class đó có thể được inject bằng `@Autowired`.

Nếu cần entity metadata, JPA scan phải phát hiện entity. Nếu inject một entity class trực tiếp như Spring service, đó thường là nhầm lẫn về lifecycle.

Dùng `@EntityScan` khi cần điều chỉnh package tìm entity theo cấu hình phù hợp.

### 17.3. Repository bean và entity type là hai khái niệm

Repository thường là Spring bean được tạo bởi Spring Data. Entity được quản lý bởi JPA persistence context/EntityManager. Đừng tìm entity qua `ApplicationContext.getBean(Order.class)` trừ khi bạn thật sự có một Spring bean riêng của kiểu đó.

## 18. Component scan filters và điều kiện loại bean

Ngay cả khi package đúng, component scan vẫn có thể bỏ qua class do filter.

Ví dụ:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = DeprecatedComponent.class
    )
)
@Configuration
class CustomScanConfiguration {
}
```

Class có `@Component` nhưng mang annotation bị exclude sẽ không được đăng ký qua scan đó.

Một số tình huống khác:

- `useDefaultFilters=false` làm tắt default stereotype filters.
- Exclude filter theo assignable type.
- Custom include filter không match.
- Nhiều `@ComponentScan` với phạm vi khác nhau.
- Cấu hình scan bị thay thế trong test context.

Nếu một component không xuất hiện, tìm các khai báo `@ComponentScan` và filter trong toàn bộ configuration có liên quan.

## 19. Chẩn đoán bằng ApplicationContext

Khi ứng dụng khởi động thành công nhưng một lookup cụ thể vẫn lỗi, có thể quan sát các bean đang tồn tại.

### 19.1. Liệt kê bean theo type

```java
@Component
public class BeanReporter implements ApplicationRunner {

    private final ApplicationContext context;

    public BeanReporter(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names =
                context.getBeanNamesForType(PaymentGateway.class);

        System.out.println(
                "PaymentGateway beans: "
                        + Arrays.toString(names));
    }
}
```

Nếu array rỗng, context hiện tại không tìm thấy bean theo type đó trong phạm vi truy vấn.

Nếu có một hoặc nhiều tên, tiếp tục kiểm tra:

- Tên bean có khớp lookup theo name không?
- Bean có đúng type không?
- Có qualifier phù hợp không?
- Bean thuộc context nào?
- Bean có phải FactoryBean product không?

### 19.2. Kiểm tra tên bean

```java
for (String name : context.getBeanDefinitionNames()) {
    if (name.toLowerCase(Locale.ROOT).contains("payment")) {
        System.out.println(name);
    }
}
```

Cách này hữu ích khi biết bean có thể được đăng ký dưới tên khác.

Không dump toàn bộ bean list ra log production thường xuyên; output có thể rất lớn và lộ thông tin nội bộ.

### 19.3. Kiểm tra class của bean

```java
Map<String, PaymentGateway> gateways =
        context.getBeansOfType(PaymentGateway.class);

gateways.forEach((name, bean) -> {
    System.out.println(
            name + " -> " + bean.getClass().getName());
});
```

Nếu bean được bọc bởi proxy, class thực tế có thể là proxy class. Khi cần biết target type, dùng Spring AOP utilities phù hợp và tránh giả định `bean.getClass()` luôn là class implementation ban đầu.

### 19.4. Quan sát bean definitions

Với `ConfigurableApplicationContext`, có thể truy cập `BeanDefinition` registry để xem metadata đăng ký. Ví dụ:

```java
ConfigurableApplicationContext configurable =
        (ConfigurableApplicationContext) context;

String[] names =
        configurable.getBeanFactory().getBeanDefinitionNames();

System.out.println(Arrays.toString(names));
```

Đây là công cụ debug; không nên thay đổi registry tùy tiện sau khi context đã refresh chỉ để ép một bean xuất hiện.

### 19.5. Dùng Actuator `beans`

Nếu ứng dụng có Spring Boot Actuator và endpoint được expose/bảo vệ phù hợp, endpoint `/actuator/beans` có thể cung cấp thông tin bean và dependency.

Chỉ expose endpoint này ở môi trường kiểm soát. Nó tiết lộ cấu trúc nội bộ ứng dụng và không nên mở công khai không cần thiết.

## 20. Condition Evaluation Report: vì sao auto-configuration không tạo bean?

Khi bean được kỳ vọng từ Spring Boot starter, condition report là một trong những điểm điều tra đầu tiên.

### 20.1. Bật debug

Trong file test hoặc local:

```properties
debug=true
```

Hoặc command line:

```bash
java -jar shop.jar --debug
```

Boot in report về auto-configuration conditions đã match và không match.

### 20.2. Đọc lý do không match

Ví dụ có thể thấy:

```text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        'com.acme.payment.PaymentClient'
```

Hoặc:

```text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty (app.payment.enabled=true)
        found different value
```

Thông tin này giúp xác định thiếu dependency hay property condition không khớp.

### 20.3. Phân biệt condition của configuration và bean method

Một class configuration có thể được load nhưng một bean method cụ thể bị condition loại. Ngược lại, toàn bộ configuration class có thể không được import.

Hãy xác định chính xác condition nằm ở đâu:

- Trên auto-configuration class.
- Trên nested configuration.
- Trên từng `@Bean` method.
- Trên component class.
- Trên một configuration được import có điều kiện.

Đừng chỉ tìm class name trong report rồi kết luận mọi bean method của class đều được tạo.

## 21. Quy trình chẩn đoán có hệ thống

Khi gặp `NoSuchBeanDefinitionException`, thực hiện theo thứ tự:

### Bước 1 — Xác định bean đang thiếu

Đọc phần:

```text
No qualifying bean of type '...'
No bean named '...'
```

Ghi lại type hoặc name mà Spring đang tìm.

### Bước 2 — Tìm nơi yêu cầu dependency

Tìm constructor parameter, `@Autowired`, `@Resource`, `@Bean` method parameter hoặc `getBean(...)` call tạo ra lookup.

Xác định bean cha đang được khởi tạo và dependency nào bị thiếu.

### Bước 3 — Xác định context được hỏi

Ứng dụng có parent/child context không? Test có context hierarchy không? Code có tự tạo ApplicationContext thứ hai không?

Bean tồn tại trong context khác chưa chắc được nhìn thấy từ context hiện tại.

### Bước 4 — Kiểm tra bean registration mechanism

Bean đáng lẽ đến từ:

- `@Component` scan?
- `@Bean` method?
- `@Import`?
- Spring Boot auto-configuration?
- Spring Data repository scan?
- `@ConfigurationPropertiesScan`?
- Test bean override?
- Registry code?

Nếu không xác định được cơ chế tạo bean, bạn chưa có cơ sở sửa lỗi.

### Bước 5 — Kiểm tra package và classpath

Nếu là component scan, xác nhận package nằm trong vùng scan. Nếu là auto-configuration, xác nhận dependency có trên runtime classpath và imports metadata được đóng gói.

### Bước 6 — Kiểm tra profiles và conditions

Đọc active profiles, property values và Condition Evaluation Report. Tìm condition không match hoặc configuration bị exclude.

### Bước 7 — Kiểm tra tên, type, qualifier

Bean có tồn tại dưới tên khác không? Có đúng interface không? Qualifier có khớp? Generic type có khác? Có FactoryBean không?

### Bước 8 — Kiểm tra loại test context

Nếu lỗi trong test, xác định test dùng full context hay slice. Bean thiếu có thể nằm ngoài scope chủ đích của slice.

### Bước 9 — Kiểm tra dependency chain

Một bean có thể không xuất hiện vì chính configuration của nó phụ thuộc một bean khác thiếu. Lần theo root cause đầu tiên, không chỉ class bị ảnh hưởng cuối cùng.

### Bước 10 — Sửa tại đúng ranh giới và kiểm chứng

Đăng ký/import/scan/configure bean theo thiết kế. Sau đó chạy test khởi tạo context hoặc test behavior liên quan. Không thêm annotation hàng loạt chỉ để làm biến mất exception.

## 22. Ví dụ hoàn chỉnh: sửa lỗi thiếu PaymentGateway

### 22.1. Cấu trúc ban đầu

```text
com.example.shop
├── ShopApplication.java
├── checkout/
│   └── CheckoutService.java
└── infrastructure/
    └── payment/
        └── RemotePaymentGateway.java
```

Nhưng application class thực tế đặt ở:

```text
com.example.shop.bootstrap.ShopApplication
```

Code service:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Implementation:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {
    // ...
}
```

Nếu component scan chỉ bắt đầu từ `com.example.shop.bootstrap`, package `com.example.shop.infrastructure.payment` nằm ngoài vùng scan.

### 22.2. Sửa bằng root package

Chuyển `ShopApplication` lên `com.example.shop`:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Khi đó các package con `checkout` và `infrastructure.payment` có thể được scan.

### 22.3. Hoặc import cấu hình rõ ràng

Nếu không thể đổi package root, tạo:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

và import:

```java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
```

Đảm bảo class configuration được import và các dependency của nó có sẵn.

### 22.4. Viết test xác nhận bean graph

```java
@SpringBootTest(classes = ShopApplication.class)
class PaymentWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void paymentGatewayIsRegistered() {
        assertThat(context.getBean(PaymentGateway.class))
                .isNotNull();
    }
}
```

Test này xác nhận có một bean phù hợp với type trong full test context. Nếu có nhiều implementation, cần kiểm tra lựa chọn hoặc dùng qualifier/primary phù hợp.

### 22.5. Test behavior thay vì chỉ kiểm tra tồn tại

Một integration test có thể gọi service và xác nhận nó dùng gateway phù hợp. Nếu gateway gọi hệ thống ngoài, có thể thay bằng fake/test implementation trong test configuration để không tạo side effect.

Mục tiêu là kiểm tra wiring đúng với contract của test, không nhất thiết gọi payment provider production.

## 23. Các trường hợp đặc biệt cần chú ý

### 23.1. Bean có scope request/session

Một bean có scope web như `request` hoặc `session` có thể không truy cập được trong non-web context nếu scope chưa được đăng ký. Tình huống này thường tạo lỗi scope/context khác, không nên đánh đồng với bean singleton đơn giản.

Nếu test dùng `webEnvironment=NONE` nhưng bean cần request scope, hãy dùng web test environment phù hợp hoặc mock boundary tương ứng.

### 23.2. Bean lazy

`@Lazy` có thể trì hoãn khởi tạo instance, nhưng bean definition vẫn có thể tồn tại. Nếu lookup theo type không thấy bean, kiểm tra registration/condition thay vì mặc định đổ lỗi cho lazy initialization.

### 23.3. Bean được tạo theo generic type

Một bean factory có thể trả type quá tổng quát hoặc không khai báo product type rõ, khiến Spring không dự đoán được type trước khi khởi tạo. Đảm bảo `@Bean` method khai báo return type cụ thể phù hợp, nhất là khi auto-configuration dùng `@ConditionalOnBean` hoặc injection theo generic.

Ví dụ:

```java
@Bean
PaymentGateway paymentGateway() {
    return new RemotePaymentGateway();
}
```

rõ ràng hơn việc khai báo return type `Object` nếu bean thực sự là PaymentGateway.

### 23.4. Classloader và duplicate class

Trong môi trường DevTools restart hoặc plugin/container classloader, cùng tên class có thể được nạp bởi loader khác nhau. Khi đó bean có thể tồn tại nhưng không assignable với type mà consumer đang dùng, tùy cách Spring tìm candidate.

Lỗi thường thấy là `ClassCastException` hoặc không có candidate theo type. Kiểm tra classloader và class identity nếu package/type giống nhau nhưng lookup vẫn bất thường.

### 23.5. Bean bị override hoặc thay thế trong test

Test có thể đăng ký mock hoặc fake với cùng type/name. Nếu override không khớp qualifier hoặc bean name, dependency vẫn có thể thiếu hoặc chọn nhầm bean.

Kiểm tra annotations bean override theo đúng version Spring Boot/Spring Framework.

## 24. Những cách sửa sai nên tránh

| Cách làm | Vì sao không tốt | Hướng đúng hơn |
| --- | --- | --- |
| Gắn `@Component` lên mọi class | Tạo nhiều bean không cần thiết, không xử lý configuration boundary | Đăng ký bean có chủ đích |
| Mở component scan toàn bộ package gốc quá rộng | Có thể phát hiện bean ngoài dự kiến, tăng startup coupling | Chọn package/module boundary rõ |
| Đổi dependency bắt buộc thành `Optional` để app khởi động | Che lỗi wiring và tạo behavior thiếu chức năng | Sửa bean registration hoặc cung cấp implementation |
| Thêm `@Primary` khi chưa có bean | `@Primary` không tạo bean | Đảm bảo ít nhất một candidate tồn tại |
| Tạo context mới bằng `new AnnotationConfigApplicationContext` trong service | Tạo container tách biệt, không có cùng graph | Inject bean từ context đang quản lý |
| Dùng `@SpringBootTest` thay mọi slice test | Test chậm và mất ranh giới | Dùng đúng loại test |
| Exclude auto-configuration để tránh lỗi | Có thể làm mất bean cần thiết và tạo lỗi khác | Đọc condition report |
| Thêm JAR vào compile classpath nhưng thiếu runtime | Auto-configuration có thể không thấy class lúc chạy | Kiểm tra runtime dependency |
| Lookup bean theo tên suy đoán | Bean name có thể khác | Inject theo type hoặc đặt tên rõ |
| Bỏ qua root cause | Exception ngoài cùng có thể chỉ là wrapper | Đọc cause chain |
| Bắt exception rồi tiếp tục với null | Lỗi wiring biến thành lỗi runtime khó tìm | Fail fast hoặc biểu diễn optional có chủ đích |

## 25. Bài thực hành: tìm và sửa bean thiếu

### Mục tiêu

Tạo một Spring Boot application có `CheckoutService` cần `PaymentGateway`. Cố ý tạo các tình huống bean thiếu để học cách chẩn đoán.

### Bước 1 — Tạo interface và service

```java
public interface PaymentGateway {
    String charge(int amount);
}
```

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(int amount) {
        return gateway.charge(amount);
    }
}
```

### Bước 2 — Cố ý bỏ implementation

Khởi động ứng dụng. Quan sát exception chain và ghi lại bean đang được tạo cùng dependency thiếu.

### Bước 3 — Thêm implementation nhưng đặt ngoài scan

Đặt `PaymentGatewayImpl` trong package nằm ngoài package root của application. Giữ `@Component` rồi khởi động lại.

Quan sát vì sao annotation có mặt nhưng bean vẫn không được phát hiện.

### Bước 4 — Sửa component scan

Đặt application class lên package gốc hoặc khai báo phạm vi scan phù hợp. Khởi động lại và xác nhận bean được tạo.

### Bước 5 — Thử profile

Đưa implementation vào configuration có `@Profile("prod")`, sau đó chạy test profile. Quan sát bean vắng mặt.

Thêm implementation cho test profile hoặc chọn active profile phù hợp theo mục tiêu kiểm thử.

### Bước 6 — Thử property condition

Thêm `@ConditionalOnProperty` cho configuration. Chạy với property thiếu, false và true. Đọc Condition Evaluation Report để hiểu kết quả.

### Bước 7 — Thử tên bean

Đăng ký bean với tên `remoteGateway` nhưng cố ý lookup `paymentGateway`. Quan sát lỗi lookup theo name dù type bean tồn tại. Sửa bằng type injection hoặc đặt tên phù hợp.

### Bước 8 — Thử test slice

Viết `@WebMvcTest` cho controller cần `CheckoutService`. Quan sát service không tự xuất hiện trong slice. Thêm mock bean hoặc chuyển sang full-context test tùy mục tiêu.

### Bước 9 — Quan sát ApplicationContext

Dùng `getBeanNamesForType(PaymentGateway.class)` và `getBeanDefinitionNames()` để kiểm tra registry. So sánh khi profile/condition thay đổi.

### Bước 10 — Viết test regression

Tạo `@SpringBootTest` xác nhận bean graph quan trọng tồn tại và một test behavior cho checkout. Nếu test dùng fake gateway, ghi rõ external payment integration chưa được kiểm thử thật.

### Câu hỏi tự kiểm tra

1. `NoSuchBeanDefinitionException` có nghĩa gì?
2. Nó khác `NoUniqueBeanDefinitionException` như thế nào?
3. Vì sao `UnsatisfiedDependencyException` có thể chứa `NoSuchBeanDefinitionException`?
4. `@Component` có tự bảo đảm class trở thành bean trong mọi package không?
5. Component scan mặc định của `@SpringBootApplication` bắt đầu từ đâu?
6. Vì sao đặt application class trong package con có thể làm mất bean ở package sibling?
7. `scanBasePackages` có điều khiển tất cả JPA repository/entity scanning không?
8. `@Bean` method chỉ được xử lý khi configuration class được đăng ký như thế nào?
9. `@Import` giải quyết trường hợp nào?
10. Spring Boot 3 đăng ký auto-configuration qua file nào?
11. `@ConditionalOnProperty` có thể làm bean biến mất khi nào?
12. `@ConditionalOnMissingBean` có thể làm bean mặc định không được tạo vì lý do gì?
13. `@Profile("prod")` có tạo bean trong test profile không?
14. Vì sao `@ConfigurationProperties` thường cần scan hoặc enable registration?
15. Nếu bean tồn tại nhưng lookup theo tên thất bại, cần kiểm tra gì?
16. `@Primary` có tạo bean mới không?
17. Vì sao `@WebMvcTest` có thể không có service bean?
18. `@DataJpaTest` có tự scan toàn bộ service layer không?
19. Parent context có nhìn thấy bean chỉ được đăng ký ở child không?
20. `ObjectProvider<T>` khác constructor injection trực tiếp như thế nào?
21. Khi nào optional dependency là thiết kế đúng?
22. `FactoryBean` có khác bean product được tạo ra không?
23. Entity JPA có phải Spring bean để inject trực tiếp không?
24. Condition Evaluation Report giúp chẩn đoán điều gì?
25. Nếu application chạy được nhưng một lookup vẫn lỗi, cần xác định context nào đang được hỏi như thế nào?

## 26. Bảng ghi nhớ nhanh

| Dấu hiệu | Hướng kiểm tra đầu tiên |
| --- | --- |
| `No qualifying bean of type ...` | Có bean nào assignable với type không? |
| `No bean named ...` | Tên bean có khớp không? |
| `UnsatisfiedDependencyException` | Đọc cause chain và dependency đầu tiên bị thiếu |
| Class có `@Component` nhưng không thấy | Package scan, filter, active context |
| Bean từ `@Bean` không xuất hiện | Configuration class đã được import/scan chưa? |
| Bean theo profile không xuất hiện | `Environment.getActiveProfiles()` |
| Auto-configuration không tạo bean | Condition Evaluation Report |
| Property condition không match | Property source và giá trị hiệu lực |
| Classpath condition không match | Runtime dependency graph |
| `@ConfigurationProperties` không inject được | `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` |
| Repository không được tạo | Spring Data dependency và repository scanning |
| Entity không được nhận diện | JPA entity scan; entity không phải Spring bean thông thường |
| Bean có nhưng lookup theo tên lỗi | Bean name, FactoryBean prefix và context |
| Có nhiều candidate | `@Primary`, `@Qualifier` hoặc thiết kế chọn implementation |
| Chỉ lỗi trong `@WebMvcTest` | Slice scope và mock/import dependencies |
| Chỉ lỗi trong context con | Parent/child context hierarchy |
| Optional integration | `Optional<T>` hoặc `ObjectProvider<T>` |
| Bean thiếu sau DevTools restart | Kiểm tra classloader, class identity và lifecycle |
| Startup fail vì bean init | Phân biệt missing definition với creation exception |
| Muốn xem registry | `getBeanNamesForType`, `getBeanDefinitionNames` |
| Muốn kiểm tra wiring | `@SpringBootTest` hoặc test phù hợp với scope |

**Kết luận:** `NoSuchBeanDefinitionException` là tín hiệu cho biết Spring không tìm được bean phù hợp trong context đang được hỏi. Hãy xác định lookup theo **type hay name**, lần theo nơi yêu cầu dependency, rồi kiểm tra cơ chế đăng ký, phạm vi component scan, configuration import, classpath, profile, conditional annotations, qualifier và context hierarchy. Khi bean chỉ tùy chọn, biểu diễn tính tùy chọn bằng API phù hợp; khi bean bắt buộc, sửa registration để ứng dụng fail fast nếu dependency không có. Một quy trình chẩn đoán dựa trên bean graph và Condition Evaluation Report sẽ giải quyết nguyên nhân gốc nhanh hơn việc thêm annotation hoặc dependency một cách thử-sai.
