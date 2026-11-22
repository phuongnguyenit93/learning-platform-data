# BeanDefinitionOverrideException và đụng tên bean

Khi Spring Boot khởi động, framework đọc cấu hình, quét component, xử lý các lớp configuration và đăng ký bean definition vào registry của ApplicationContext. Mỗi bean cần có một **bean name** để Spring tra cứu, inject dependency và quản lý lifecycle.

Nếu hai cấu hình cùng đăng ký một bean name trong cùng registry, ứng dụng có thể dừng lúc startup với lỗi:

```text
org.springframework.beans.factory.support.BeanDefinitionOverrideException:
Invalid bean definition with name 'paymentGateway' ...
Cannot register bean definition ... since there is already ...
```

Đây là `BeanDefinitionOverrideException`. Lỗi thường xuất hiện khi component scan phát hiện hai class có cùng tên bean mặc định, hai `@Bean` method cùng tên, hoặc bean của ứng dụng đụng tên bean từ thư viện/auto-configuration.

Cần phân biệt hai tình huống:

- **Trùng bean name:** hai bean definition muốn đăng ký dưới cùng một tên. Đây là nguyên nhân trực tiếp của `BeanDefinitionOverrideException` khi overriding bị tắt.
- **Trùng bean type:** nhiều bean có tên khác nhau nhưng cùng kiểu. Injection theo type có thể gây `NoUniqueBeanDefinitionException`.

Hai lỗi này có cách xử lý khác nhau. Bài học giúp bạn đọc thông báo lỗi, tìm nguồn đăng ký trùng, chọn cách sửa phù hợp và kiểm chứng ApplicationContext sau khi sửa.

## 1. Bean name dùng để làm gì?

Bean definition mô tả cách Spring tạo và cấu hình object, ví dụ:

- Bean class hoặc factory method.
- Scope như singleton hoặc prototype.
- Constructor arguments và property values.
- Dependency và qualifier.
- Init/destroy method.
- Các metadata khác phục vụ quá trình tạo bean.

Bean name là khóa định danh để registry lưu và tra cứu definition.

Ví dụ:

```java
@Service
public class PaymentService {
}
```

Với naming strategy mặc định, bean name thường là `paymentService`.

Có thể lấy bean bằng tên:

```java
PaymentService service =
        applicationContext.getBean("paymentService", PaymentService.class);
```

Hoặc inject theo type:

```java
@Service
public class CheckoutService {

    private final PaymentService paymentService;

    public CheckoutService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```

Trong business code, constructor injection thường là lựa chọn nên ưu tiên. Bean name vẫn quan trọng khi có nhiều implementation cùng type, khi dùng qualifier, khi khai báo alias hoặc khi framework đăng ký bean.

## 2. Spring tạo bean name mặc định như thế nào?

Hiểu quy tắc đặt tên giúp nhận ra xung đột trước khi chạy ứng dụng.

### 2.1. @Component, @Service, @Repository và @Controller

Nếu không khai báo tên tường minh, stereotype annotation thường dùng short class name với ký tự đầu được decapitalize theo quy tắc JavaBeans/Spring.

```java
@Service
public class CustomerService {
}

@Repository
public class CustomerRepository {
}

@Component
public class AuditPublisher {
}
```

Tên bean thường là:

| Class | Bean name mặc định |
|---|---|
| `CustomerService` | `customerService` |
| `CustomerRepository` | `customerRepository` |
| `AuditPublisher` | `auditPublisher` |

`@Service`, `@Repository` và `@Controller` là stereotype chuyên biệt của `@Component`, nên cũng tham gia cơ chế đặt tên component.

### 2.2. Hai class cùng simple name ở hai package

Đây là nguyên nhân thường gặp:

```java
package com.example.billing;

@Service
public class PaymentService {
}
```

```java
package com.example.reporting;

@Service
public class PaymentService {
}
```

Nếu component scan bao phủ cả hai package, cả hai class có thể nhận bean name mặc định `paymentService`.

Package khác nhau không tự làm tên bean mặc định trở thành duy nhất. Khi cả hai candidate được đăng ký trong cùng ApplicationContext, chúng có thể xung đột tên.

### 2.3. Đặt tên bean tường minh

Có thể gán tên riêng:

```java
@Service("billingPaymentService")
public class PaymentService {
}
```

```java
@Service("reportingPaymentService")
public class PaymentService {
}
```

Nếu cả hai implement cùng interface, caller có thể chọn implementation qua `@Qualifier` hoặc `@Primary`. Tên bean nên mô tả vai trò/domain, chẳng hạn `billingPaymentService` hoặc `reportingPaymentService`.

## 3. @Bean method cũng tạo bean name

Tên mặc định của bean khai báo bằng `@Bean` thường là tên method factory:

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
```

Bean name mặc định là `paymentGateway`.

Nếu một cấu hình khác cũng khai báo:

```java
@Configuration
public class TestPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Hai method cùng đăng ký bean name `paymentGateway`. Nếu cả hai configuration được import hoặc scan vào cùng context, registry sẽ gặp xung đột khi không cho phép overriding.

Có thể đặt tên riêng:

```java
@Bean("livePaymentGateway")
public PaymentGateway livePaymentGateway() {
    return new HttpPaymentGateway();
}
```

```java
@Bean("testPaymentGateway")
public PaymentGateway testPaymentGateway() {
    return new FakePaymentGateway();
}
```

Một `@Bean` cũng có thể khai báo nhiều tên; tên đầu tiên là bean name, các tên tiếp theo là alias. Alias cũng là tên tra cứu, vì vậy tránh dùng alias trùng tên bean khác.

## 4. Khi nào BeanDefinitionOverrideException xảy ra?

Trong cùng một bean registry, một bean definition mới muốn dùng tên đã được đăng ký bởi definition khác. Nếu registry không cho phép ghi đè, Spring từ chối đăng ký và ném exception.

Nguyên nhân phổ biến:

1. Hai component có cùng tên mặc định.
2. Hai `@Bean` method cùng tên.
3. Một configuration được import từ nhiều module và đăng ký bean cùng tên.
4. Bean ứng dụng trùng tên bean do thư viện hoặc auto-configuration cung cấp.
5. Component scan bao phủ package ngoài dự kiến.
6. Test configuration thêm bean trùng tên bean thật.
7. Hai module độc lập dùng tên chung như `client`, `mapper` hoặc `configuration`.

### 4.1. Ví dụ thông báo lỗi

```text
The bean 'paymentGateway', defined in
com.example.billing.PaymentConfiguration,
could not be registered.

A bean with that name has already been defined in
com.example.shared.SharedPaymentConfiguration
and overriding is disabled.
```

Thông báo thực tế phụ thuộc Spring Framework/Spring Boot version và nguồn bean definition. Hãy đọc cả hai phía:

- **Definition mới:** class configuration hoặc component đang muốn đăng ký.
- **Definition đã tồn tại:** bean name đã được registry sử dụng.

Không chỉ tìm chuỗi tên bean trong service đang báo lỗi. Nguồn xung đột có thể nằm ở module khác, starter hoặc test configuration.

### 4.2. Lỗi xuất hiện ở giai đoạn nào?

Lỗi thường xuất hiện trong lúc refresh ApplicationContext, trước khi ứng dụng sẵn sàng nhận request. Context có thể chưa khởi tạo xong nên endpoint Actuator không dùng được để điều tra.

Hãy bắt đầu từ stack trace, failure analysis và tên class/resource được nêu. Nếu context đã chạy thành công, các API introspection có thể hỗ trợ liệt kê bean definitions.

## 5. Phân biệt trùng bean name với trùng bean type

Đây là khác biệt quan trọng nhất khi chọn cách sửa.

### 5.1. Trùng bean name

```java
@Configuration
class FirstConfiguration {

    @Bean("paymentGateway")
    PaymentGateway firstGateway() {
        return new FirstPaymentGateway();
    }
}

@Configuration
class SecondConfiguration {

    @Bean("paymentGateway")
    PaymentGateway secondGateway() {
        return new SecondPaymentGateway();
    }
}
```

Cả hai definition dùng cùng tên `paymentGateway`. Nếu overriding bị tắt, context không thể đăng ký definition thứ hai.

Đây là vấn đề **registry naming**.

### 5.2. Trùng bean type nhưng tên khác nhau

```java
@Configuration
class GatewayConfiguration {

    @Bean("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Hai bean có cùng interface `PaymentGateway` nhưng tên khác nhau. Registry có thể lưu cả hai. Tuy nhiên, injection theo type:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

có thể gây `NoUniqueBeanDefinitionException` vì Spring tìm thấy nhiều candidate.

Đây là vấn đề **dependency selection**, không phải bean definition override.

### 5.3. Bảng phân biệt

| Tình huống | Lỗi thường gặp | Hướng xử lý |
|---|---|---|
| Hai definition cùng bean name | `BeanDefinitionOverrideException` | Đổi tên, bỏ đăng ký trùng hoặc dùng conditional |
| Nhiều bean khác tên nhưng cùng type, inject theo type | `NoUniqueBeanDefinitionException` | `@Qualifier`, `@Primary` hoặc chọn bean rõ ràng |
| Bean name có alias đụng tên khác | Lỗi đăng ký/alias tùy trường hợp | Đổi tên hoặc alias |
| Bean ở child context che bean cùng tên ở parent | Shadowing theo hierarchy | Xác định context lookup và chủ đích thiết kế |

`@Primary` và `@Qualifier` không giải quyết hai bean definition cùng tên. Chúng giúp chọn candidate trong số các bean đã được đăng ký hợp lệ.

## 6. @Qualifier và @Primary dùng khi nào?

Giả sử ứng dụng cần hai gateway có mục đích khác nhau:

```java
@Configuration
public class GatewayConfiguration {

    @Bean("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

### 6.1. Dùng @Qualifier để chọn rõ ràng

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("cardGateway") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
```

`@Qualifier` giới hạn candidate được inject. Trong ví dụ, qualifier trùng với bean name; qualifier cũng có thể là metadata riêng được gán cho bean.

### 6.2. Dùng @Primary cho implementation mặc định

Nếu phần lớn caller nên dùng bank gateway:

```java
@Bean("bankGateway")
@Primary
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Khi inject theo type mà không có qualifier, Spring ưu tiên bean được đánh dấu `@Primary`.

### 6.3. Kết hợp cả hai

Bean mặc định:

```java
@Bean("bankGateway")
@Primary
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Caller cần card gateway chỉ định `@Qualifier("cardGateway")`. Caller khác inject `PaymentGateway` theo type sẽ nhận bean primary.

Nếu hai method vẫn khai báo `@Bean("paymentGateway")`, thêm `@Primary` không làm tên registry trở nên duy nhất. Hãy giải quyết trùng tên trước.

## 7. Sửa lỗi bằng cách đặt tên bean duy nhất

Nếu hai implementation thực sự cần tồn tại cùng lúc, hãy đặt tên khác nhau.

```java
@Service("emailNotificationService")
public class EmailNotificationService
        implements NotificationService {

    @Override
    public void send(String recipient, String message) {
        // Gửi email.
    }
}
```

```java
@Service("smsNotificationService")
public class SmsNotificationService
        implements NotificationService {

    @Override
    public void send(String recipient, String message) {
        // Gửi SMS.
    }
}
```

Caller chọn bean cần dùng:

```java
@Service
public class AlertService {

    private final NotificationService emailService;

    public AlertService(
            @Qualifier("emailNotificationService")
            NotificationService emailService
    ) {
        this.emailService = emailService;
    }
}
```

Tên rõ ràng giúp giảm nguy cơ xung đột giữa module và làm dependency dễ đọc hơn.

## 8. Sửa lỗi do component scan quá rộng

Một nguyên nhân khác là `@SpringBootApplication` đặt ở package quá cao, khiến Spring scan cả class không thuộc ứng dụng hiện tại.

Ví dụ:

```text
com.example
├── application
│   └── Application.java
├── billing
│   └── PaymentService.java
├── reporting
│   └── PaymentService.java
└── legacy
    └── PaymentService.java
```

Nếu main application nằm ở `com.example`, component scan mặc định có thể phát hiện nhiều package con.

### 8.1. Chọn package scan cụ thể

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.application",
        "com.example.billing"
})
public class BillingApplication {
}
```

Cách này giới hạn component scan tới package cần thiết. Hãy bảo đảm các component cần thiết khác vẫn được đăng ký.

### 8.2. Dùng excludeFilters khi cần

Nếu cần scan package rộng nhưng loại một candidate cụ thể:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyPaymentService.class
    )
)
public class ApplicationComponents {
}
```

Đây là giải pháp có chủ đích khi biết chính xác class không nên được đăng ký. Đừng dùng filter rộng chỉ để che lỗi vì nó có thể loại bỏ bean cần thiết.

### 8.3. Tránh quét package của thư viện tùy tiện

Không nên đặt component scan ở root chung của nhiều ứng dụng hoặc package chứa thư viện bên thứ ba nếu không cần. Hãy tổ chức package theo ranh giới ứng dụng và đặt main class ở package gốc phù hợp.

## 9. Xử lý xung đột giữa application bean và auto-configuration

Spring Boot auto-configuration thường được thiết kế để lùi lại khi ứng dụng đã cung cấp bean tương ứng. Một pattern phổ biến là `@ConditionalOnMissingBean`.

Ví dụ auto-configuration:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    public PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
```

Ứng dụng cung cấp bean riêng:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new CustomPaymentGateway();
    }
}
```

Ý định là: nếu ứng dụng đã có một `PaymentGateway`, auto-configuration không tạo default bean.

### 9.1. Vì sao conditional back-off tốt hơn override?

- Ý định thay thế default được thể hiện rõ.
- Không phụ thuộc thứ tự đăng ký hai definition cùng tên.
- Ứng dụng có thể cung cấp implementation tên khác.
- Auto-configuration lùi lại theo contract dựa trên type hoặc bean name.

### 9.2. Conditional theo bean name

Có thể dùng `@ConditionalOnMissingBean(name = "paymentGateway")` khi contract yêu cầu kiểm tra một tên cụ thể.

Nếu điều bạn cần là “đã có implementation của interface này chưa?”, điều kiện theo type thường biểu đạt ý định tốt hơn.

### 9.3. Điều kiện phải được đánh giá đúng thời điểm

`@ConditionalOnMissingBean` được thiết kế chủ yếu cho auto-configuration. Nếu dùng trong cấu hình ứng dụng thông thường với thứ tự đăng ký khó dự đoán, kết quả có thể gây bất ngờ.

Khi xây dựng starter/library, hãy tuân theo cơ chế auto-configuration của Spring Boot và kiểm thử cả trường hợp default lẫn custom bean.

## 10. Loại bỏ auto-configuration không cần thiết

Nếu ứng dụng không muốn dùng một auto-configuration cụ thể, có thể exclude nó thay vì cho phép ghi đè bean toàn cục.

```java
@SpringBootApplication(
    exclude = SomeClientAutoConfiguration.class
)
public class Application {
}
```

Hoặc dùng property:

```properties
spring.autoconfigure.exclude=com.example.client.SomeClientAutoConfiguration
```

Tên class ở đây là ví dụ; hãy dùng auto-configuration thực tế từ dependency.

Chỉ exclude khi hiểu chức năng nào sẽ mất. Một auto-configuration có thể đăng ký nhiều bean phụ trợ, không chỉ bean đang gây xung đột.

### 10.1. Xem condition evaluation report

Chạy ứng dụng với `--debug` thường giúp in condition evaluation report:

```bash
java -jar app.jar --debug
```

Báo cáo cho biết auto-configuration nào match hoặc không match, và điều kiện nào dẫn tới kết quả. Nó hữu ích để tìm vì sao một auto-configuration được bật.

Nếu context thất bại ngay ở giai đoạn đăng ký bean, condition report không phải lúc nào cũng liệt kê trực tiếp cả hai definition theo cách đầy đủ. Hãy kết hợp stack trace và resource trong exception.

## 11. Profiles và property conditions

Nếu hai bean chỉ phù hợp với những môi trường khác nhau, có thể dùng profile:

```java
@Configuration
@Profile("dev")
public class DevelopmentGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

```java
@Configuration
@Profile("prod")
public class ProductionGatewayConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new LivePaymentGateway();
    }
}
```

Khi chỉ một profile được active, configuration tương ứng được áp dụng. Tuy nhiên, nếu nhiều profile cùng active, cả hai configuration có thể cùng được đăng ký và lại tạo xung đột.

Có thể dùng `@ConditionalOnProperty` khi bean phụ thuộc vào một property:

```java
@Bean
@ConditionalOnProperty(
    prefix = "payment",
    name = "provider",
    havingValue = "fake"
)
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
```

Điều kiện giúp lựa chọn implementation theo runtime configuration. Nếu hai điều kiện cùng match và hai bean vẫn dùng cùng tên, xung đột có thể tiếp tục xảy ra.

## 12. Khi nào cho phép bean definition overriding?

Spring Boot có property:

```properties
spring.main.allow-bean-definition-overriding=true
```

Hoặc cấu hình qua `SpringApplication`:

```java
SpringApplication application =
        new SpringApplication(Application.class);

application.setAllowBeanDefinitionOverriding(true);

application.run(args);
```

Khi cho phép overriding, một bean definition đăng ký sau có thể thay thế definition đã đăng ký trước dưới cùng tên trong cùng registry.

### 12.1. Vì sao không nên bật như giải pháp đầu tiên?

- Bean cuối cùng phụ thuộc thứ tự đăng ký.
- Thứ tự có thể thay đổi khi thêm dependency, config hoặc framework version.
- Bean ban đầu có thể biến mất mà không được chú ý.
- ApplicationContext vẫn khởi động nhưng dùng implementation không mong muốn.
- Lỗi wiring bị che khuất thay vì được sửa.

Điều này đặc biệt nguy hiểm nếu bean bị ghi đè là `DataSource`, `ObjectMapper`, `SecurityFilterChain`, transaction manager hoặc client kết nối hệ thống ngoài.

### 12.2. Default phụ thuộc Spring Boot version

Spring Boot 2.1 thay đổi mặc định để **không cho phép bean definition overriding**. Vì vậy, ứng dụng cũ và mới có thể có hành vi khác nhau dù source code không đổi.

Hãy kiểm tra version Spring Boot đang dùng và cấu hình thực tế. Không suy luận default của project từ hướng dẫn thuộc version khác.

### 12.3. Nếu thực sự cần override

Trong trường hợp đặc biệt cần thay definition cùng tên:

1. Xác định chính xác definition cũ và mới.
2. Xác nhận thứ tự đăng ký ổn định.
3. Chỉ bật ở scope cần thiết nếu có thể.
4. Viết integration test xác nhận bean cuối cùng là implementation mong đợi.
5. Ghi rõ lý do và phạm vi override.
6. Ưu tiên conditional back-off nếu có thể sửa thiết kế.

Trong ứng dụng thông thường, đổi tên hoặc cấu hình conditional dễ bảo trì hơn bật override toàn cục.

## 13. Đọc lỗi để tìm hai nguồn đăng ký

Khi gặp `BeanDefinitionOverrideException`, tách thông báo thành bốn thông tin:

- **Bean name:** tên bị trùng, ví dụ `paymentGateway`.
- **Definition đã có:** class/resource hoặc factory method đăng ký trước.
- **Definition mới:** class/resource hoặc factory method đang được đăng ký sau.
- **Context/registry:** ApplicationContext nào chứa hai definition.

Từ đó tìm trong source:

```text
paymentGateway
@Bean
@Component
@Service
@Repository
@ComponentScan
@Import
```

Tìm tất cả nơi có thể đăng ký tên đó, không chỉ nơi có method trùng chuỗi.

### 13.1. Xem resource description khi context đã chạy

```java
ConfigurableApplicationContext context = ...;

for (String beanName :
        context.getBeanFactory().getBeanDefinitionNames()) {

    BeanDefinition definition =
            context.getBeanFactory().getBeanDefinition(beanName);

    System.out.printf(
            "name=%s, class=%s, factoryBean=%s, factoryMethod=%s, source=%s%n",
            beanName,
            definition.getBeanClassName(),
            definition.getFactoryBeanName(),
            definition.getFactoryMethodName(),
            definition.getResourceDescription()
    );
}
```

Thông tin này giúp xác định bean đến từ class, `@Bean` factory method hay resource nào.

**Giới hạn:** nếu context thất bại trước khi refresh hoàn tất, đoạn code trên không thể chạy như một bean trong chính context đó. Khi ấy dùng stack trace, debug quá trình registration hoặc tạo context chẩn đoán tối giản có cùng cấu hình.

### 13.2. Actuator beans endpoint

Nếu ứng dụng khởi động thành công, Actuator endpoint `beans` có thể cung cấp danh sách bean và context liên quan. Endpoint này tiết lộ cấu trúc nội bộ, vì vậy cần giới hạn exposure và bảo vệ bằng security phù hợp.

Không thể dựa vào endpoint đó để chẩn đoán một context không khởi động được.

## 14. Ví dụ: hai @Configuration class đăng ký cùng tên

Module billing:

```java
@Configuration
public class BillingConfiguration {

    @Bean
    public PaymentClient paymentClient() {
        return new BillingPaymentClient();
    }
}
```

Module reporting:

```java
@Configuration
public class ReportingConfiguration {

    @Bean
    public PaymentClient paymentClient() {
        return new ReportingPaymentClient();
    }
}
```

Application import cả hai:

```java
@SpringBootApplication
@Import({
    BillingConfiguration.class,
    ReportingConfiguration.class
})
public class Application {
}
```

Hai method mặc định đăng ký bean name `paymentClient`. Nếu overriding bị tắt, context thất bại khi đăng ký definition trùng tên.

### 14.1. Nếu cả hai client đều cần tồn tại

Đổi tên theo vai trò:

```java
@Bean("billingPaymentClient")
public PaymentClient billingPaymentClient() {
    return new BillingPaymentClient();
}
```

```java
@Bean("reportingPaymentClient")
public PaymentClient reportingPaymentClient() {
    return new ReportingPaymentClient();
}
```

Sau đó inject đúng client:

```java
public BillingService(
        @Qualifier("billingPaymentClient") PaymentClient client
) {
    this.client = client;
}
```

### 14.2. Nếu chỉ một client được dùng

Nếu module reporting chỉ cung cấp default, hãy thiết kế auto-configuration để lùi lại khi ứng dụng đã có `PaymentClient`:

```java
@Bean
@ConditionalOnMissingBean(PaymentClient.class)
public PaymentClient paymentClient() {
    return new ReportingPaymentClient();
}
```

Không đăng ký hai definition cùng tên rồi dựa vào “bean nào được tạo sau” để chọn implementation.

## 15. Ví dụ: hai class cùng tên mặc định

```java
package com.example.legacy;

@Component
public class JsonMapper {
}
```

```java
package com.example.platform;

@Component
public class JsonMapper {
}
```

Cả hai class có thể nhận tên mặc định `jsonMapper`. Nếu hai package nằm trong scan path, registry gặp xung đột.

Sửa bằng tên riêng:

```java
@Component("legacyJsonMapper")
public class JsonMapper {
}
```

```java
@Component("platformJsonMapper")
public class JsonMapper {
}
```

Hoặc giới hạn component scan nếu một class không thuộc context của ứng dụng.

Nếu hai class có vai trò khác nhau, tên theo domain thường tốt hơn những tên chung như `jsonMapper`, `client`, `helper` hoặc `config`.

## 16. Bean name alias cũng cần xem xét

Một bean có thể có nhiều tên:

```java
@Bean(name = {"primaryObjectMapper", "jsonMapper"})
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
```

Tên đầu tiên là bean name; tên tiếp theo là alias cho cùng bean. Nếu cấu hình khác cố đăng ký bean tên `jsonMapper`, registry có thể gặp xung đột alias/name tùy cách đăng ký.

Khi điều tra, kiểm tra:

- `@Bean(name = {...})`.
- Alias đăng ký qua `BeanDefinitionRegistry`.
- `registerAlias(...)`.
- Cấu hình framework hoặc thư viện có tên bean tùy chỉnh.

Alias không tạo thêm instance; nó tạo thêm tên tra cứu cho cùng bean.

## 17. Bean trong parent và child ApplicationContext

Một hệ thống có thể có context hierarchy, ví dụ root context và web child context. Cùng bean name có thể tồn tại ở parent và child; child context có thể che/shadow bean cùng tên ở parent khi lookup.

Điều này khác với hai definition cùng tên trong **cùng một registry**.

Khi thấy hai bean cùng tên trong ứng dụng nhiều context:

1. Xác định bean thuộc context nào.
2. Xem caller lookup từ context nào.
3. Xem child có chủ đích shadow bean của parent không.
4. Phân biệt context hierarchy với component scan/import cùng registry.

Đừng áp dụng máy móc cách sửa cho single-context app vào hệ thống có hierarchy.

## 18. Xung đột trong test configuration

Test thường bổ sung bean thay thế để cô lập dependency:

```java
@TestConfiguration
public class TestGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Nếu test import thêm configuration thật cũng khai báo `paymentGateway`, test context có thể gặp lỗi trùng tên.

Cách xử lý tùy mục tiêu:

- Dùng cơ chế mock/replace bean được phiên bản Spring Boot/Spring Framework hỗ trợ.
- Đặt tên bean test riêng và inject bằng qualifier nếu cả hai cần tồn tại.
- Dùng profile/conditional để chỉ đăng ký một implementation.
- Không import configuration thật nếu test không cần nó.
- Dùng test slice hoặc context tối giản phù hợp.

Đừng bật overriding cho toàn bộ test suite chỉ để làm biến mất lỗi. Làm vậy có thể khiến test dùng nhầm bean thật hoặc bean giả mà không rõ.

## 19. Thiết kế starter/auto-configuration tránh xung đột

Nếu phát triển Spring Boot starter, bean mặc định nên cho phép ứng dụng tùy chỉnh.

```java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

Ứng dụng có thể cung cấp implementation riêng:

```java
@Configuration
public class ApplicationGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
```

Auto-configuration lùi lại theo điều kiện type nếu bean phù hợp đã tồn tại.

Khi xây dựng starter, nên:

- Dùng `@ConditionalOnClass` để chỉ bật khi dependency cần thiết có mặt.
- Dùng `@ConditionalOnProperty` khi feature cần được bật tường minh.
- Dùng `@ConditionalOnMissingBean` để back off.
- Xác định thứ tự auto-configuration nếu có dependency.
- Test cả trường hợp default và custom bean.

Mục tiêu là cho ứng dụng lựa chọn implementation rõ ràng, không để thứ tự scan quyết định bean cuối cùng.

## 20. Kiểm thử để bắt lỗi bean name collision

Có thể dùng `ApplicationContextRunner` trong test auto-configuration để xác nhận context khởi động hoặc thất bại theo kỳ vọng.

Ví dụ hai configuration cùng đăng ký tên:

```java
class BeanNameCollisionTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            FirstGatewayConfiguration.class,
                            SecondGatewayConfiguration.class
                    );

    @Test
    void failsWhenTwoDefinitionsUseSameName() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                            BeanDefinitionOverrideException.class
                    );
        });
    }
}
```

Đây là test minh họa; cần có hai configuration trong test source cùng đăng ký một bean name và dependency test tương ứng.

### 20.1. Test sau khi sửa

Sau khi đổi tên:

```java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasBean("billingPaymentClient");
    assertThat(context).hasBean("reportingPaymentClient");
});
```

Nếu chỉ một implementation được phép tồn tại theo điều kiện:

```java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasSingleBean(PaymentClient.class);
});
```

`ApplicationContextRunner` hữu ích cho test auto-configuration vì tạo context nhỏ, nhanh và kiểm soát được. Ứng dụng thực vẫn cần integration test phù hợp để xác nhận toàn bộ cấu hình runtime.

## 21. Quy trình điều tra lỗi từng bước

Khi ứng dụng báo `BeanDefinitionOverrideException`:

### Bước 1. Ghi lại bean name bị trùng

Ví dụ `paymentGateway`. Đây là khóa đầu tiên để tìm kiếm.

### Bước 2. Đọc cả definition mới và definition cũ

Stack trace/failure message thường chỉ ra class, factory method hoặc resource. Ghi nhận cả hai phía, không chỉ nơi được nhắc cuối cùng.

### Bước 3. Tìm toàn bộ nguồn đăng ký tên đó

Tìm trong project:

- `@Component("...")`, `@Service("...")`, `@Repository("...")`.
- `@Bean` method và `@Bean(name = ...)`.
- `@Import` và `@ComponentScan`.
- Custom `BeanDefinitionRegistryPostProcessor`.
- Alias registration.
- Test configuration.
- Auto-configuration từ dependency.

### Bước 4. Xác định có cần hai bean hay chỉ một bean

Nếu cần cả hai, đổi tên và dùng qualifier. Nếu chỉ muốn thay default, dùng conditional back-off hoặc exclude auto-configuration không cần thiết.

### Bước 5. Kiểm tra trùng type riêng biệt

Sau khi giải quyết bean name, ứng dụng có thể gặp `NoUniqueBeanDefinitionException` nếu nhiều bean cùng type. Khi đó dùng `@Qualifier`/`@Primary` theo hợp đồng dependency.

### Bước 6. Khởi động context và xác nhận bean thực tế

Kiểm tra bean name, type, resource description và implementation. Không dừng ở việc exception biến mất; xác nhận implementation mà service nhận là đúng.

### Bước 7. Thêm test để ngăn lỗi quay lại

Với starter hoặc module cấu hình dùng chung, test context nên bao phủ cả trường hợp default lẫn custom bean.

## 22. Các lựa chọn sửa lỗi và khi nào dùng

| Cách sửa | Dùng khi | Điều cần chú ý |
|---|---|---|
| Đổi tên `@Component`/`@Bean` | Cần nhiều bean cùng tồn tại | Caller phải chọn đúng bean |
| `@Qualifier` | Nhiều bean cùng type, tên khác nhau | Không giải quyết trùng bean name |
| `@Primary` | Có nhiều candidate và một default | Không giải quyết trùng bean name |
| `@ConditionalOnMissingBean` | Default auto-configuration cần nhường cho custom bean | Đặt đúng trong auto-configuration |
| `@Profile` | Chỉ một cấu hình phù hợp theo môi trường | Nhiều profile active có thể cùng đăng ký |
| `@ConditionalOnProperty` | Chọn implementation theo property | Điều kiện có thể cùng match nếu cấu hình không chặt |
| Giới hạn component scan | Scan phát hiện bean ngoài ý muốn | Đảm bảo không loại bean cần thiết |
| Exclude auto-configuration | Không cần tính năng từ starter | Kiểm tra side effect |
| Cho phép overriding | Trường hợp đặc biệt có chủ đích | Order-dependent, cần test chặt |

## 23. Các lỗi thường bị nhầm

### 23.1. NoUniqueBeanDefinitionException

Thông báo thường cho biết Spring tìm thấy nhiều bean phù hợp với một dependency type:

```text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2
```

Nếu bean names khác nhau, dùng `@Qualifier` hoặc `@Primary`. Không cần đổi tên chỉ vì hai bean cùng type, trừ khi tên hiện tại gây nhầm lẫn.

### 23.2. NoSuchBeanDefinitionException

Thông báo này cho biết không tìm thấy bean phù hợp. Nguyên nhân có thể là:

- Class không được scan/import.
- Profile hoặc condition không match.
- Dependency chưa được khai báo.
- Bean name/type được lookup sai.

Đây không phải lỗi trùng tên.

### 23.3. BeanCurrentlyInCreationException

Lỗi này thường liên quan circular dependency hoặc bean đang được tạo dở, không phải đơn thuần hai bean trùng tên. Cần kiểm tra dependency graph và constructor injection.

### 23.4. BeanDefinitionOverrideException

Đây là xung đột khi đăng ký definition với tên đã có trong cùng registry trong lúc overriding bị tắt. Hãy tập trung vào hai nguồn đăng ký và bean name.

## 24. Những hiểu lầm thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| Hai class ở package khác nhau luôn có bean name khác nhau | **Sai** | Tên mặc định thường dựa trên short class name |
| Hai bean cùng type luôn gây `BeanDefinitionOverrideException` | **Sai** | Nếu tên khác nhau, vấn đề thường là chọn dependency |
| `@Primary` sửa được hai bean cùng tên | **Sai** | Primary chọn candidate theo type sau khi bean đã đăng ký |
| `@Qualifier` ngăn registry đăng ký trùng tên | **Sai** | Qualifier chọn bean khi inject |
| Đổi tên `@Bean` method luôn vô hại | **Sai** | Code lookup theo bean name/qualifier có thể cần cập nhật |
| Bật overriding luôn là giải pháp tốt | **Sai** | Có thể che xung đột và khiến kết quả phụ thuộc thứ tự |
| Auto-configuration luôn ghi đè bean ứng dụng | **Sai** | Auto-configuration thường dùng điều kiện back-off |
| `@ConditionalOnMissingBean` giống `@Primary` | **Sai** | Conditional quyết định có đăng ký definition hay không; Primary chọn candidate |
| Hai context cha/con cùng tên luôn gây override exception | **Sai** | Context hierarchy có cơ chế lookup/shadowing riêng |
| Actuator beans endpoint luôn dùng được khi startup thất bại | **Sai** | Endpoint cần context đã khởi động và được expose |
| Cùng bean name trong hai file config chắc chắn gây lỗi | **Sai** | Phải xem chúng có vào cùng registry/context không |
| `@Profile("dev")` và `@Profile("prod")` luôn loại trừ nhau | **Sai** | Nhiều profile có thể cùng active |

## 25. Bài tập thực hành

### Bài 1. Hai component cùng tên mặc định

Tạo hai class `PaymentService` trong hai package:

```java
package com.example.billing;

@Service
public class PaymentService {
}
```

```java
package com.example.reporting;

@Service
public class PaymentService {
}
```

Đặt main application ở package cha để scan cả hai.

**Câu hỏi:** Vì sao context có thể gặp `BeanDefinitionOverrideException`?

**Đáp án:** Cả hai class có thể được đặt tên bean mặc định là `paymentService` trong cùng registry.

**Cách sửa:** Gán tên riêng như `billingPaymentService` và `reportingPaymentService`.

### Bài 2. Hai implementation cùng interface

```java
@Bean("cardGateway")
PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}

@Bean("bankGateway")
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
```

Inject `PaymentGateway` không qualifier.

**Câu hỏi:** Lỗi nào có thể xuất hiện?

**Đáp án:** `NoUniqueBeanDefinitionException` vì hai bean có tên khác nhau nhưng cùng type.

**Cách sửa:** Dùng `@Qualifier("cardGateway")` hoặc đánh dấu một bean `@Primary` nếu có default hợp lý.

### Bài 3. Auto-configuration back-off

Một starter tạo `PaymentGateway` mặc định. Ứng dụng cần dùng gateway riêng.

**Yêu cầu:** sửa starter để default bean chỉ được tạo khi chưa có `PaymentGateway` nào.

**Gợi ý:** Dùng `@ConditionalOnMissingBean(PaymentGateway.class)` trên bean method của auto-configuration.

### Bài 4. Xác định nguồn bean

Exception có hai nguồn:

```text
existing: SharedClientConfiguration#apiClient
new: ReportingConfiguration#apiClient
```

**Câu hỏi:** Cần kiểm tra gì trước khi bật overriding?

**Đáp án:** Xác định có cần cả hai client không, bean nào được caller sử dụng, configuration nào import cả hai class và có thể đổi tên/conditional hay không.

### Bài 5. Test context

Dùng `ApplicationContextRunner` để xác nhận hai configuration cùng đăng ký `paymentGateway` làm context thất bại khi override bị tắt. Sau đó đổi tên bean và kiểm tra context khởi động.

**Mục tiêu:** test cả lỗi registration lẫn cấu hình sau khi sửa.

## 26. Ghi nhớ

- Bean name là khóa định danh bean definition trong registry.
- `@Component`/`@Service` mặc định thường dùng short class name đã decapitalize; hai class cùng tên ở package khác nhau vẫn có thể đụng tên.
- `@Bean` method mặc định dùng tên method làm bean name; explicit names và aliases cũng có thể gây xung đột.
- `BeanDefinitionOverrideException` nói về **trùng tên đăng ký** trong cùng registry khi override không được phép.
- Nhiều bean cùng type nhưng tên khác nhau thường dẫn tới `NoUniqueBeanDefinitionException`.
- `@Qualifier` và `@Primary` giúp chọn candidate; chúng không sửa hai definition cùng bean name.
- Đổi tên bean khi cần nhiều implementation, hoặc giới hạn component scan nếu phát hiện bean ngoài ý muốn.
- Auto-configuration nên dùng `@ConditionalOnMissingBean` để nhường cho custom bean theo contract.
- Dùng profile/property condition khi chỉ một implementation nên được đăng ký trong runtime.
- Exclude auto-configuration khi ứng dụng không cần tính năng đó, sau khi hiểu các bean liên quan.
- `spring.main.allow-bean-definition-overriding=true` có thể che lỗi và làm kết quả phụ thuộc thứ tự đăng ký; chỉ dùng khi có chủ đích và test rõ ràng.
- Đọc cả definition cũ lẫn mới trong exception; kiểm tra component scan, `@Import`, `@Bean`, alias, test config và auto-configuration.
- Kiểm chứng context sau khi sửa và xác nhận đúng implementation được inject.

Khi gặp `BeanDefinitionOverrideException`, hãy tự hỏi: **“Tên bean nào đang bị đăng ký hai lần, hai nguồn đó đến từ đâu, tôi cần cả hai bean hay chỉ muốn thay một default, và caller phải nhận implementation nào?”** Trả lời được những câu hỏi này sẽ giúp bạn sửa đúng registry conflict thay vì che lỗi bằng một thiết lập override toàn cục.
