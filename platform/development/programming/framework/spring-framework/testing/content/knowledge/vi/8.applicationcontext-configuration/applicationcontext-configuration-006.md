# Kết hợp component class, XML và `@Import`

Một ứng dụng Spring có thể chứa cấu hình được viết bằng Java, các class có stereotype như `@Component` hoặc `@Service`, và những bean được khai báo trong file XML. Điều này thường xuất hiện khi một hệ thống đang chuyển dần từ XML sang Java configuration, khi một thư viện cung cấp sẵn XML context, hoặc khi các module cần ghép cấu hình theo từng phần.

Spring không yêu cầu toàn bộ bean phải được khai báo bằng cùng một cách. `ApplicationContext` có thể nạp bean definition từ class, component scan và XML trong cùng một context. Các cơ chế quan trọng là đăng ký class trực tiếp, `@ComponentScan`, `@Import` và `@ImportResource`. Chọn đúng cơ chế giúp cấu hình dễ đọc, tránh quét trùng package và hạn chế lỗi do bean bị đăng ký hai lần hoặc dependency không rõ ràng.

## 1. Các nguồn tạo bean definition trong Spring

Trước khi ghép nhiều kiểu cấu hình, hãy phân biệt các nguồn bean definition:

| Nguồn | Cách khai báo | Khi phù hợp |
| --- | --- | --- |
| Component class đăng ký trực tiếp | `AnnotationConfigApplicationContext.register(...)` hoặc `@Import` | Biết rõ class cần đưa vào context |
| Component scanning | `@ComponentScan` hoặc `<context:component-scan>` | Muốn Spring tự tìm các class có stereotype trong package |
| Java configuration | `@Configuration` và các method `@Bean` | Muốn khai báo bean bằng Java, có thể dùng điều kiện và import module |
| XML bean definition | `<bean>` trong file XML, nạp bằng `@ImportResource` hoặc XML reader | Tích hợp cấu hình cũ hoặc thư viện cung cấp XML |
| Import configuration | `@Import` | Ghép các cấu hình Java hoặc component class theo module |

Các nguồn này cuối cùng đều đóng góp bean definition vào `BeanFactory` của `ApplicationContext`. Khi context được refresh, Spring tạo các bean theo dependency và lifecycle tương ứng.

Điểm quan trọng là **đăng ký class trực tiếp, quét package và import class là ba cách chọn nguồn cấu hình khác nhau**. Đăng ký trực tiếp phù hợp khi danh sách class đã biết; component scan phù hợp khi package là ranh giới khám phá; `@Import` phù hợp khi một cấu hình cần ghép rõ ràng các module khác.

## 2. Đăng ký component class trực tiếp

Với `AnnotationConfigApplicationContext`, có thể đăng ký các class ngay khi tạo context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (var context = new AnnotationConfigApplicationContext(
        AppConfig.class,
        OrderService.class,
        PricingService.class)) {

    OrderService orders = context.getBean(OrderService.class);
}
```

`AppConfig` có thể là class `@Configuration`; `OrderService` và `PricingService` có thể là các component class. Spring xử lý annotation trên các class đã đăng ký, tạo bean definition tương ứng và inject dependency theo constructor hoặc annotation phù hợp.

Ví dụ một component class:

```java
@Service
public class OrderService {

    private final PricingService pricingService;

    public OrderService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
```

Đăng ký trực tiếp không cần quét toàn bộ package. Cách này phù hợp cho ứng dụng nhỏ, test context tối giản hoặc cấu hình module mà danh sách thành phần đã được xác định rõ.

Có thể tạo context rỗng rồi đăng ký class và refresh sau:

```java
var context = new AnnotationConfigApplicationContext();
context.register(AppConfig.class, OrderService.class);
context.refresh();

try {
    OrderService service = context.getBean(OrderService.class);
} finally {
    context.close();
}
```

Việc gọi `refresh()` hoàn tất quá trình nạp và khởi tạo context. Trước thời điểm đó, không nên giả định các singleton bean đã sẵn sàng để sử dụng.

## 3. Khai báo Java configuration bằng `@Configuration` và `@Bean`

`@Configuration` đánh dấu class chứa cấu hình bean. Các method `@Bean` trả về đối tượng mà Spring quản lý:

```java
@Configuration
public class CoreConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public PricingService pricingService(Clock applicationClock) {
        return new PricingService(applicationClock);
    }
}
```

Spring nhận diện `CoreConfig` như một nguồn bean definition. Các tham số của method `@Bean` được giải quyết từ container, vì vậy `PricingService` nhận bean `Clock` do context quản lý.

Một class cấu hình có thể import cấu hình khác, khai báo component scan hoặc nạp XML. Cách tổ chức theo module giúp tách phần persistence, messaging, security và web thành các cấu hình có trách nhiệm riêng.

`@Configuration` có semantics đầy đủ cho các method `@Bean`, trong đó lời gọi giữa các method `@Bean` được container xử lý theo cơ chế proxy ở chế độ mặc định. `@Component` có thể dùng trên class có method `@Bean` như lite configuration, nhưng nếu class đóng vai trò cấu hình chính, nên dùng `@Configuration` để ý định rõ ràng.

## 4. Component scanning tìm class như thế nào?

Component scanning cho phép Spring dò tìm class có stereotype trong package và package con. Các annotation phổ biến gồm:

- `@Component`: component tổng quát.
- `@Service`: lớp xử lý nghiệp vụ.
- `@Repository`: lớp truy cập dữ liệu, đồng thời hỗ trợ cơ chế chuyển đổi exception persistence khi được áp dụng phù hợp.
- `@Controller` và `@RestController`: thành phần web.
- `@Configuration`: class cấu hình Java.

Ví dụ:

```java
@Configuration
@ComponentScan(basePackages = {
    "com.example.orders.application",
    "com.example.orders.adapter"
})
public class ApplicationConfig {
}
```

Spring quét các package được chỉ định và đăng ký component phù hợp. Việc giới hạn package giúp tránh vô tình đưa các bean của module không liên quan vào context.

Nếu ứng dụng có cấu trúc package chuẩn, có thể dùng class làm mốc:

```java
@ComponentScan(basePackageClasses = {
    OrderService.class,
    JpaOrderAdapter.class
})
```

`basePackageClasses` giúp tránh hard-code tên package dạng chuỗi. Spring dùng package chứa các class làm điểm bắt đầu quét.

### Component scan không giống đăng ký trực tiếp

Khi đăng ký `OrderService.class`, ta yêu cầu Spring xử lý đúng class đó. Khi dùng `@ComponentScan`, Spring tìm các candidate trong phạm vi package theo filter. Vì vậy:

- Dùng đăng ký trực tiếp khi muốn danh sách thành phần tường minh.
- Dùng scan khi module có quy ước stereotype và muốn tự phát hiện các thành phần mới.
- Dùng filter khi cần giới hạn loại component được phát hiện.

Tránh quét một package quá rộng như `com.example` nếu package đó chứa cả test fixture, cấu hình thử nghiệm, adapter không dùng trong runtime hoặc module có bean xung đột.

## 5. `@Import` ghép các Java configuration class

`@Import` cho phép một class cấu hình đưa cấu hình khác vào cùng context. Ví dụ:

```java
@Configuration
@Import({PersistenceConfig.class, MessagingConfig.class})
public class ApplicationConfig {
}
```

`PersistenceConfig` có thể khai báo `DataSource`, `EntityManagerFactory` hoặc repository adapter; `MessagingConfig` có thể khai báo producer và consumer. Khi Spring xử lý `ApplicationConfig`, các cấu hình được import cũng tham gia xây dựng bean definition.

Ví dụ module persistence:

```java
@Configuration
public class PersistenceConfig {

    @Bean
    public OrderRepository orderRepository(OrderJpaRepository jpaRepository) {
        return new JpaOrderRepositoryAdapter(jpaRepository);
    }
}
```

Module ứng dụng có thể ghép cấu hình:

```java
@Configuration
@Import(PersistenceConfig.class)
public class OrderModuleConfig {

    @Bean
    public PlaceOrderService placeOrderService(
            OrderRepository repository,
            PaymentPort paymentPort) {
        return new PlaceOrderService(repository, paymentPort);
    }
}
```

`@Import` hữu ích khi muốn thể hiện dependency giữa các module ở cấp cấu hình. Thay vì quét một package lớn, class gốc khai báo rõ module nào được ghép vào ứng dụng.

## 6. `@Import` cũng có thể đưa component class vào context

`@Import` không chỉ dành cho class `@Configuration`. Spring hỗ trợ import các regular component class. Ví dụ:

```java
@Component
public class OrderIdGenerator {
    public OrderId nextId() {
        return OrderId.random();
    }
}
```

Một cấu hình có thể import class đó:

```java
@Configuration
@Import(OrderIdGenerator.class)
public class OrderModuleConfig {
}
```

Spring đăng ký component class được import như một bean definition. Cách này phù hợp khi muốn module cấu hình tự khai báo một số component cụ thể mà không cần quét toàn bộ package chứa chúng.

Đối với một class đơn lẻ, có thể cân nhắc đăng ký trực tiếp trong context. `@Import` hữu ích hơn khi việc ghép class là một phần của cấu trúc module và muốn giữ cấu hình đó trong metadata của Java configuration.

## 7. Import selector và registrar

Ngoài danh sách class tĩnh, `@Import` còn hỗ trợ các extension point để quyết định cấu hình cần đăng ký.

### `ImportSelector`

`ImportSelector` trả về tên class cần import. Nó phù hợp khi tập cấu hình được chọn theo metadata hoặc điều kiện:

```java
public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
            S3StorageConfig.class.getName(),
            StorageHealthIndicatorConfig.class.getName()
        };
    }
}
```

Đăng ký selector:

```java
@Configuration
@Import(StorageImportSelector.class)
public class StorageModuleConfig {
}
```

Spring gọi selector trong quá trình phân tích cấu hình và import các class được trả về. Nếu cần đọc property hoặc điều kiện môi trường, có thể dùng các cơ chế condition phù hợp; không nên để selector thực hiện I/O hoặc tạo side effect.

### `ImportBeanDefinitionRegistrar`

`ImportBeanDefinitionRegistrar` cho phép đăng ký bean definition theo chương trình, khi cần kiểm soát tên bean, constructor argument hoặc metadata ở mức thấp hơn:

```java
public class ClientRegistrar implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
            new RootBeanDefinition(RemoteClient.class);

        registry.registerBeanDefinition("remoteClient", definition);
    }
}
```

Import registrar:

```java
@Configuration
@Import(ClientRegistrar.class)
public class RemoteClientConfig {
}
```

Registrar thường được dùng trong thư viện hoặc framework cần đăng ký bean dựa trên annotation tùy chỉnh. Với cấu hình ứng dụng thông thường, `@Bean`, `@Import` class tĩnh hoặc component scan dễ đọc và dễ bảo trì hơn.

## 8. Nạp XML bằng `@ImportResource`

`@ImportResource` cho phép một Java configuration class nạp thêm bean definition từ XML:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-services.xml")
public class ApplicationConfig {

    @Bean
    public OrderFacade orderFacade(OrderService orderService) {
        return new OrderFacade(orderService);
    }
}
```

File XML có thể khai báo bean:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyTaxCalculator"
          class="com.example.legacy.LegacyTaxCalculator"/>

</beans>
```

Bean `legacyTaxCalculator` được đăng ký vào cùng `ApplicationContext` với các bean Java configuration. Các bean có thể inject lẫn nhau nếu type và qualifier phù hợp.

`@ImportResource` chấp nhận một hoặc nhiều resource location. Có thể dùng classpath resource hoặc location được hỗ trợ bởi resource loader:

```java
@ImportResource({
    "classpath:/spring/legacy-datasource.xml",
    "classpath:/spring/legacy-services.xml"
})
```

Đường dẫn `classpath:` giúp cấu hình không phụ thuộc thư mục làm việc hiện tại. Hãy xác nhận file được đóng gói trong classpath của ứng dụng và tên resource đúng chữ hoa/chữ thường trên hệ thống file phân biệt hoa thường.

## 9. Kết hợp `@ComponentScan`, `@Import` và `@ImportResource`

Một cấu hình gốc có thể sử dụng đồng thời cả ba cơ chế:

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders.components")
@Import({PersistenceConfig.class, SecurityConfig.class})
@ImportResource("classpath:/spring/legacy-integration.xml")
public class ApplicationConfig {
}
```

Trong ví dụ:

- `@ComponentScan` tìm các component trong module orders.
- `@Import` ghép các cấu hình Java đã được tách theo trách nhiệm.
- `@ImportResource` nạp bean definition cũ từ XML.
- Các method `@Bean` trong `ApplicationConfig` có thể bổ sung bean đặc thù cho context.

Các cơ chế không loại trừ nhau. Chúng cùng đóng góp bean definition vào context. Tuy nhiên, cần có ranh giới rõ: package nào được scan, module nào được import, XML nào chứa bean cũ và bean nào được cấu hình bằng `@Bean`.

Một cấu trúc package có thể như sau:

```text
com.example.orders
├── ApplicationConfig.java
├── application
│   ├── PlaceOrderService.java
│   └── PricingService.java
├── adapter
│   ├── persistence
│   │   ├── PersistenceConfig.java
│   │   └── JpaOrderRepositoryAdapter.java
│   └── payment
│       └── HttpPaymentAdapter.java
└── security
    └── SecurityConfig.java

resources
└── spring
    └── legacy-integration.xml
```

Trong một ứng dụng module hóa, `ApplicationConfig` đóng vai trò composition root: nơi ghép các thành phần cần thiết để tạo context của ứng dụng.

## 10. Import Java configuration từ XML

Chiều kết hợp ngược lại cũng có thể thực hiện: XML có thể đăng ký một Java configuration class. Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean class="com.example.orders.PersistenceConfig"/>

    <bean id="legacyTaxCalculator"
          class="com.example.legacy.LegacyTaxCalculator"/>
</beans>
```

`<context:annotation-config/>` đăng ký các annotation processing infrastructure cần thiết, bao gồm cơ chế xử lý cấu hình Java. Class `PersistenceConfig` được đăng ký như bean definition và được xử lý để phát hiện các method `@Bean` cùng cấu hình liên quan.

Nếu XML đã dùng `<context:component-scan>`, cơ chế xử lý annotation cần thiết cũng được bật tự động. Không cần khai báo `annotation-config` lần nữa chỉ để phục vụ component scan.

XML cũng có thể import file XML khác bằng phần tử `<import>`:

```xml
<beans ...>
    <import resource="classpath:/spring/legacy-datasource.xml"/>
    <import resource="classpath:/spring/legacy-services.xml"/>
</beans>
```

Đây là cơ chế ghép XML với XML. Nếu muốn XML đưa Java configuration vào context, có thể khai báo class cấu hình như bean như ví dụ trên, hoặc dùng một context bootstrap bằng Java để đăng ký cả hai nguồn.

## 11. Dùng `XmlBeanDefinitionReader` để nạp XML và Java class trong cùng context

Khi muốn kiểm soát việc bootstrap bằng Java code, có thể dùng `XmlBeanDefinitionReader` cùng `AnnotationConfigApplicationContext`:

```java
var context = new AnnotationConfigApplicationContext();

var xmlReader = new XmlBeanDefinitionReader(context);
xmlReader.loadBeanDefinitions("classpath:/spring/legacy-context.xml");

context.register(ApplicationConfig.class);
context.refresh();

try {
    OrderService service = context.getBean(OrderService.class);
} finally {
    context.close();
}
```

Ví dụ này nạp bean definition XML vào context, đăng ký Java configuration class, rồi refresh một lần để hoàn tất quá trình khởi tạo. `AnnotationConfigApplicationContext` hỗ trợ cả annotation configuration và bean definition được nạp bằng reader.

Cách này hữu ích trong ứng dụng thuần Spring hoặc công cụ cần lựa chọn nguồn cấu hình theo runtime. Trong ứng dụng Spring Boot thông thường, đặt `@ImportResource` trên class cấu hình thường đơn giản hơn.

## 12. Kết hợp XML và Java config trong Spring Boot

Spring Boot ưu tiên Java configuration và auto-configuration, nhưng vẫn có thể nạp XML khi tích hợp hệ thống cũ. Ví dụ:

```java
@SpringBootApplication
@ImportResource("classpath:/spring/legacy-context.xml")
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Spring Boot khởi tạo context theo cấu hình ứng dụng, sau đó XML resource được xử lý cùng các bean definition từ component scan, auto-configuration và `@Bean` method.

Nếu cấu hình XML chỉ cần cho một module, có thể đặt `@ImportResource` trên một configuration class riêng và import class đó từ ứng dụng:

```java
@Configuration
@ImportResource("classpath:/spring/legacy-billing.xml")
public class LegacyBillingConfig {
}
```

```java
@SpringBootApplication
@Import(LegacyBillingConfig.class)
public class OrdersApplication {
}
```

Cách tổ chức này giúp module legacy có ranh giới riêng. Khi loại bỏ XML, có thể thay `LegacyBillingConfig` bằng Java configuration mới mà ít ảnh hưởng cấu hình gốc.

## 13. Bean được khai báo từ nhiều nguồn có thể inject lẫn nhau

Một bean khai báo trong XML có thể được inject vào Java configuration hoặc component class. Tương tự, bean tạo bằng `@Bean` có thể được tham chiếu trong XML thông qua `ref`.

Ví dụ XML khai báo adapter cũ:

```xml
<bean id="legacyTaxCalculator"
      class="com.example.legacy.LegacyTaxCalculator"/>
```

Java component inject bean đó:

```java
@Service
public class InvoiceService {

    private final LegacyTaxCalculator taxCalculator;

    public InvoiceService(LegacyTaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Hoặc XML tham chiếu bean được tạo bằng Java:

```java
@Configuration
public class ClientConfig {

    @Bean
    public RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
```

```xml
<bean id="legacyFacade"
      class="com.example.legacy.LegacyFacade">
    <constructor-arg ref="remoteClient"/>
</bean>
```

Điều kiện là cả hai bean definition phải thuộc cùng context hoặc có quan hệ parent-child cho phép tra cứu theo hướng phù hợp. Nếu nằm trong hai context độc lập, bean không tự động nhìn thấy nhau.

## 14. Xử lý tên bean và xung đột khi ghép cấu hình

Khi cùng một component được đăng ký từ nhiều nguồn, vấn đề có thể phát sinh ở tên bean hoặc ở việc inject theo type.

Ví dụ hai nguồn khai báo cùng tên:

```java
@Configuration
class PaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new SandboxPaymentAdapter();
    }
}
```

```xml
<bean id="paymentPort"
      class="com.example.payment.LivePaymentAdapter"/>
```

Hai bean definition cùng tên `paymentPort` có thể dẫn đến xung đột hoặc hành vi override tùy cấu hình container và môi trường. Spring Boot thường tắt bean definition overriding theo mặc định để phát hiện cấu hình trùng sớm; cấu hình Spring thuần và các phiên bản/cấu hình khác có thể có chính sách khác. Không nên dựa vào việc một bean tình cờ ghi đè bean khác.

Nếu hai implementation cùng tồn tại với tên khác nhau, injection theo type có thể bị mơ hồ:

```java
public OrderService(PaymentPort paymentPort) {
    this.paymentPort = paymentPort;
}
```

Khi có nhiều bean `PaymentPort`, có thể dùng `@Qualifier` hoặc `@Primary`:

```java
@Bean
@Primary
PaymentPort defaultPaymentPort() {
    return new SandboxPaymentAdapter();
}

@Bean
@Qualifier("livePayment")
PaymentPort livePaymentPort() {
    return new LivePaymentAdapter();
}
```

Và inject theo qualifier khi cần:

```java
public OrderService(@Qualifier("livePayment") PaymentPort paymentPort) {
    this.paymentPort = paymentPort;
}
```

`@Primary` và `@Qualifier` giải quyết lựa chọn bean khi inject theo type. Chúng không giải quyết việc hai bean definition cùng đăng ký một bean name. Hãy quản lý tên bean rõ ràng và tránh khai báo trùng cùng một class qua scan, import và XML nếu không có chủ đích.

## 15. Profile và condition khi kết hợp nhiều nguồn

Một cấu hình có thể chỉ được dùng trong một môi trường. `@Profile` có thể đặt trên configuration class hoặc bean method:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new LivePaymentAdapter();
    }
}
```

Trong khi đó, cấu hình phát triển có thể cung cấp adapter sandbox:

```java
@Configuration
@Profile("development")
public class DevelopmentPaymentConfig {

    @Bean
    PaymentPort paymentPort() {
        return new SandboxPaymentAdapter();
    }
}
```

Các class được import vẫn chịu sự xử lý của profile/condition. Nếu profile không active, bean hoặc cấu hình có điều kiện tương ứng sẽ không được đăng ký theo quy tắc của annotation đó.

XML cũng có thể dùng profile:

```xml
<beans profile="development">
    <bean id="paymentPort"
          class="com.example.payment.SandboxPaymentAdapter"/>
</beans>
```

Hãy đảm bảo profile được kích hoạt nhất quán giữa Java và XML. Một cấu hình Java có thể import XML chứa bean chỉ dành cho `production`; nếu test chạy profile `test`, bean đó sẽ không có mặt. Khi đó, cần cung cấp bean thay thế cho profile test hoặc điều chỉnh cấu hình theo ý định.

## 16. Thứ tự import và dependency giữa cấu hình

`@Import` thể hiện quan hệ ghép cấu hình, nhưng không nên dùng thứ tự trong mảng import như một cơ chế điều khiển thứ tự khởi tạo bean. Spring quản lý dependency và lifecycle dựa trên bean definition, dependency injection và các cơ chế ordering chuyên biệt.

Nếu `OrderService` cần `PaymentPort`, hãy khai báo dependency qua constructor. Không dựa vào việc `PaymentConfig` được viết trước `OrderConfig` hoặc xuất hiện trước trong danh sách import.

Khi có bean cần khởi tạo sau bean khác, ưu tiên dependency thực tế. `@DependsOn` có thể biểu đạt quan hệ khởi tạo theo tên bean trong trường hợp đặc biệt, nhưng không nên thay thế dependency injection bình thường.

Đối với XML và Java config, cùng nguyên tắc được áp dụng: bean được tạo khi container giải quyết dependency và lifecycle, không phải đơn giản theo thứ tự file được đọc. Tránh side effect trong quá trình parse cấu hình; việc đọc metadata và đăng ký definition nên tách khỏi thao tác kết nối hoặc ghi dữ liệu thực tế.

## 17. Kết hợp các nguồn cấu hình trong kiểm thử

TestContext Framework cho phép cung cấp nhiều class cấu hình hoặc resource XML cho một test context. Ví dụ với JUnit Jupiter:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = {TestSupportConfig.class, OrderTestConfig.class},
    locations = "classpath:/spring/legacy-test-beans.xml"
)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderUsingConfiguredAdapters() {
        // ...
    }
}
```

`classes` cung cấp Java configuration hoặc component class; `locations` cung cấp XML resource. Spring Test tạo context từ các nguồn đã khai báo. Với Spring Boot, có thể chọn cấu hình test bằng `@SpringBootTest(classes = ...)` và đặt `@ImportResource` trên class cấu hình được chọn.

Một cấu hình test Java có thể import module thật và thay thế một adapter:

```java
@TestConfiguration
@Import({OrderModuleConfig.class, PersistenceTestConfig.class})
class OrderTestConfig {

    @Bean
    @Primary
    PaymentPort paymentPort() {
        return new FakePaymentAdapter();
    }
}
```

Khi dùng `@TestConfiguration` với Spring Boot, class có thể bổ sung bean cho test mà không bị xem như cấu hình ứng dụng chính trong component scan thông thường. `@Primary` giúp chọn fake khi có nhiều bean cùng type, nhưng cần xác nhận không có bean trùng tên.

### Kiểm thử cấu hình ghép

Một test context nhỏ có thể xác nhận các bean quan trọng thực sự được đăng ký:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ApplicationConfig.class)
class ApplicationConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersJavaAndXmlBeans() {
        assertNotNull(context.getBean(OrderService.class));
        assertNotNull(context.getBean("legacyTaxCalculator"));
        assertNotNull(context.getBean(PaymentPort.class));
    }
}
```

Test này chỉ xác nhận context có thể cung cấp các bean cần thiết. Nếu cần kiểm tra bean nào được inject khi có nhiều implementation, hãy kiểm tra bean cụ thể hoặc hành vi của component sử dụng nó.

## 18. Parent context và child context

Trong ứng dụng web hoặc ứng dụng có nhiều vùng cấu hình, Spring có thể sử dụng parent-child `ApplicationContext`. Child context có thể tra cứu bean từ parent; parent không tra cứu ngược bean chỉ tồn tại trong child.

Ví dụ kiến trúc web truyền thống có thể đặt service và repository ở root context, còn controller và web-specific bean ở servlet context. Khi ghép XML và Java config, cần xác định mỗi nguồn được nạp vào context nào.

Nếu `PaymentPort` chỉ được khai báo trong child context nhưng service ở parent context cần nó, dependency có thể không được giải quyết vì parent không nhìn thấy bean của child. Hãy đặt bean ở context có phạm vi phù hợp hoặc điều chỉnh kiến trúc context.

Không cần tạo nhiều context chỉ để phân tách file XML và Java config. Nếu các bean cần inject lẫn nhau, thường nên nạp chúng vào cùng một context. Parent-child chỉ hữu ích khi có ranh giới lifecycle hoặc phạm vi thực sự khác nhau.

## 19. Tổ chức chuyển đổi từ XML sang Java configuration

Trong hệ thống legacy, chuyển đổi cấu hình nên diễn ra từng phần và có thể kiểm chứng. Một lộ trình thực tế:

1. **Lập danh sách bean XML:** ghi nhận bean id, class, constructor/property, alias, scope, init/destroy method và dependency.
2. **Xác định module:** nhóm bean theo persistence, integration, business service, web hoặc security.
3. **Tạo Java configuration tương ứng:** chuyển một nhóm bean sang `@Bean`, component class hoặc cấu hình chuyên biệt.
4. **Giữ XML cho phần chưa chuyển:** nạp qua `@ImportResource` hoặc XML reader.
5. **Tránh khai báo trùng:** mỗi bean có một nguồn sở hữu rõ ràng trong giai đoạn chuyển đổi.
6. **Kiểm tra wiring:** khởi tạo context và xác nhận dependency được inject đúng.
7. **Kiểm thử hành vi:** chạy integration test cho các luồng sử dụng bean đã chuyển đổi.
8. **Loại XML cũ khi không còn tham chiếu:** cập nhật cấu hình bootstrap và tài liệu để tránh nguồn cấu hình chết.

Không nên chuyển toàn bộ XML trong một thay đổi lớn nếu hệ thống có nhiều bean phụ thuộc lẫn nhau và thiếu kiểm thử. Chuyển theo module giúp khoanh vùng lỗi, dễ rollback và giảm thời gian điều tra khi context không khởi động.

## 20. Các lỗi thường gặp khi ghép component class, XML và `@Import`

- **Quên nạp XML resource:** `@ImportResource` trỏ sai đường dẫn hoặc file không nằm trong classpath, khiến bean XML không tồn tại.
- **Quét package quá rộng:** component ngoài phạm vi ứng dụng bị đăng ký và gây xung đột dependency.
- **Khai báo bean hai lần:** một component vừa được scan, vừa được import hoặc khai báo lại trong XML với tên trùng.
- **Nhầm `@Import` với `@ImportResource`:** `@Import` nhận class/selector/registrar; XML resource cần `@ImportResource` hoặc XML reader.
- **Nhầm tag component với component scan:** có `@Component` trên class chưa có nghĩa Spring tự tìm thấy nó; class phải được đăng ký trực tiếp, import hoặc nằm trong phạm vi scan.
- **Inject mơ hồ:** nhiều bean cùng type được đăng ký nhưng không có qualifier hoặc primary phù hợp.
- **Dùng `@Primary` để xử lý bean name trùng:** primary chỉ ảnh hưởng lựa chọn theo type, không giải quyết duplicate definition cùng tên.
- **Dựa vào thứ tự file:** cấu hình được đọc trước không có nghĩa bean đó luôn được tạo trước; hãy biểu đạt dependency thật.
- **Sai profile:** Java config và XML có điều kiện profile khác nhau khiến bean cần thiết không được đăng ký.
- **Đặt bean vào sai context:** parent và child không nhìn thấy bean theo hướng mong đợi.
- **Dùng `@DirtiesContext` thay cho sửa cấu hình:** context bị tạo lại nhưng lỗi wiring hoặc duplicate bean vẫn còn.

## 21. Cách chọn cơ chế phù hợp

| Nhu cầu | Cơ chế nên cân nhắc |
| --- | --- |
| Đăng ký một vài class đã biết | `AnnotationConfigApplicationContext.register(...)` |
| Tìm các service/repository/controller theo package | `@ComponentScan` hoặc `<context:component-scan>` |
| Ghép module Java configuration | `@Import` |
| Đưa một component class cụ thể vào module | `@Import(ComponentClass.class)` hoặc đăng ký trực tiếp |
| Chọn cấu hình theo metadata động | `ImportSelector` |
| Đăng ký bean definition ở mức thấp | `ImportBeanDefinitionRegistrar` |
| Nạp XML từ Java config | `@ImportResource` |
| Nạp Java configuration từ XML | Đăng ký class cấu hình trong XML với annotation processing được bật |
| Nạp cả XML và class bằng code | `XmlBeanDefinitionReader` kết hợp `AnnotationConfigApplicationContext` |
| Thêm cấu hình cho test | `@ContextConfiguration`, `@TestConfiguration`, `@ImportResource` |

Một cấu hình rõ ràng thường có một composition root chịu trách nhiệm ghép các module, mỗi module có class cấu hình riêng, component scan giới hạn theo package và XML chỉ được giữ ở nơi còn cần tích hợp. Cách tổ chức đó giúp biết bean đến từ đâu, vì sao nó được đăng ký và context nào sở hữu nó.

## 22. Quy trình chẩn đoán khi bean không xuất hiện hoặc bị inject sai

Khi context không khởi động hoặc inject nhầm bean, hãy lần lượt kiểm tra:

1. **Nguồn đăng ký:** class được register, import, scan hay khai báo trong XML?
2. **Đường dẫn resource:** XML có nằm trong classpath và `@ImportResource` có trỏ đúng không?
3. **Scan boundary:** package scan có bao gồm component class và có vô tình bao gồm module không mong muốn không?
4. **Annotation processing:** XML context đã bật các processor cần thiết để xử lý annotation/configuration chưa?
5. **Bean name:** component name, method `@Bean`, XML id và alias có trùng không?
6. **Bean type:** có nhiều implementation cùng type không; có cần `@Qualifier` hoặc `@Primary` không?
7. **Profile/condition:** profile và property hiện tại có cho phép bean được đăng ký không?
8. **Context hierarchy:** bean nằm trong parent hay child context, và consumer có nhìn thấy nó không?
9. **Lifecycle:** context đã được refresh và bean có được khởi tạo thành công không?
10. **Test configuration:** test có vô tình thay thế hoặc bổ sung cấu hình làm thay đổi tập bean so với runtime không?

Có thể dùng `ApplicationContext.getBeanDefinitionNames()` để xem tên bean definition, `getBeanNamesForType(...)` để kiểm tra các bean theo type, hoặc bật log phù hợp cho package cấu hình Spring để theo dõi quá trình parse và đăng ký. Các thao tác này hữu ích khi chẩn đoán, nhưng test nên xác nhận những bean và hành vi có ý nghĩa với ứng dụng thay vì phụ thuộc vào toàn bộ danh sách bean nội bộ.

## 23. Tổng kết

Spring có thể kết hợp component class, Java configuration và XML trong cùng `ApplicationContext`. Đăng ký class trực tiếp giúp chọn thành phần tường minh; component scan khám phá stereotype trong package; `@Import` ghép cấu hình Java hoặc component class; `@ImportResource` đưa XML bean definition vào context. XML cũng có thể đăng ký Java configuration khi annotation processing được bật, và `XmlBeanDefinitionReader` cho phép bootstrap cả hai nguồn bằng code.

Khi ghép nhiều nguồn, hãy xác định rõ ranh giới package, nguồn sở hữu từng bean, tên bean, qualifier, profile và context hierarchy. Trong kiểm thử Spring, cung cấp đúng các class và resource cần thiết để tạo context có thể lặp lại. Khi các nguồn cấu hình được tổ chức theo module và có test xác nhận wiring, quá trình duy trì hệ thống legacy hoặc chuyển dần từ XML sang Java configuration sẽ dễ kiểm soát hơn.
