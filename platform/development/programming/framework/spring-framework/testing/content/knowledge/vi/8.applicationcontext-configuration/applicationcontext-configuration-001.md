# @ContextConfiguration với lớp cấu hình Java

Trong Spring Framework Test, annotation `@ContextConfiguration` cho TestContext Framework biết cần tạo `ApplicationContext` từ những cấu hình nào. Khi dự án dùng Java-based configuration, ta truyền các class cấu hình vào thuộc tính `classes`. Các class đó có thể khai báo bean bằng `@Configuration` và `@Bean`, import cấu hình khác hoặc kích hoạt component scanning.

Cách làm này cho phép test dựng một Spring context có phạm vi rõ ràng: chỉ những bean và cấu hình mà bài test cần. Nó phù hợp với ứng dụng Spring Framework thuần, không yêu cầu Spring Boot hay `@SpringBootTest`.

## 1. Vai trò của @ContextConfiguration

TestContext Framework tách việc quản lý vòng đời test khỏi cách test framework thực thi phương thức. Annotation `@ContextConfiguration` mô tả cấu hình dùng để tạo context; Spring TestContext đọc metadata đó, chọn context loader phù hợp, nạp bean và quản lý context trong suốt các lần chạy test.

Với Java configuration, cách khai báo cơ bản là:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // Gọi service và kiểm tra kết quả.
    }
}
```

Ở đây:

- `@ExtendWith(SpringExtension.class)` kết nối JUnit Jupiter với Spring TestContext Framework.
- `@ContextConfiguration(classes = OrderTestConfiguration.class)` chỉ định class Java dùng để tạo context.
- `@Autowired` yêu cầu Spring tiêm bean `OrderService` vào test instance.
- `@Test` vẫn là annotation của JUnit Jupiter, điều khiển lần chạy test.

`@ContextConfiguration` thuộc Spring Framework Test. Nó không tự khởi động ứng dụng Spring Boot và cũng không tự tạo một web server. Phạm vi context phụ thuộc các class cấu hình được chỉ định.

## 2. Khai báo Java configuration bằng @Configuration và @Bean

Một class cấu hình Java thường được đánh dấu `@Configuration`. Các phương thức `@Bean` bên trong mô tả cách tạo những object mà Spring sẽ quản lý.

Ví dụ, giả sử ứng dụng có service phụ thuộc vào repository và cổng gửi thông báo:

```java
public interface OrderRepository {
    Order save(Order order);
}

public interface NotificationGateway {
    void orderCreated(Order order);
}

public class OrderService {

    private final OrderRepository orderRepository;
    private final NotificationGateway notificationGateway;

    public OrderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        this.orderRepository = orderRepository;
        this.notificationGateway = notificationGateway;
    }

    public Order create(Order order) {
        Order saved = orderRepository.save(order);
        notificationGateway.orderCreated(saved);
        return saved;
    }
}
```

Ta có thể tạo cấu hình dành cho test:

```java
@Configuration
public class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }

    @Bean
    OrderService orderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        return new OrderService(orderRepository, notificationGateway);
    }
}
```

Ví dụ trên giả định `InMemoryOrderRepository` và `RecordingNotificationGateway` là các triển khai phù hợp đã được định nghĩa trong test source hoặc trong ứng dụng. Spring gọi các phương thức `@Bean` để tạo object, đăng ký chúng trong context và giải quyết tham số phương thức theo các bean tương ứng.

Khi context được nạp, test có thể nhận bean:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderUsingConfiguredCollaborators() {
        Order input = new Order("customer-1", "SKU-1", 2);

        Order result = orderService.create(input);

        assertThat(result).isEqualTo(input);
    }
}
```

Điểm quan trọng là test không tự gọi constructor của `OrderService`. Spring tạo bean từ cấu hình, sau đó Spring Test tiêm bean vào test instance. Bài test vì thế kiểm tra được cả việc context lắp ráp các dependency theo Java configuration.

### 2.1. Vai trò của @Configuration

`@Configuration` đánh dấu class là nguồn định nghĩa bean. Trong chế độ cấu hình đầy đủ mặc định, Spring có thể xử lý các lời gọi giữa những phương thức `@Bean` để bảo đảm chúng tham chiếu đến bean được quản lý trong context.

Với cấu hình không cần hành vi proxy giữa các phương thức `@Bean`, có thể dùng `@Configuration(proxyBeanMethods = false)` (thuộc tính này có từ Spring Framework 5.2). Khi đó, nếu một phương thức bean gọi trực tiếp phương thức bean khác bằng lời gọi Java thông thường, lời gọi đó không được intercept để lấy bean đã quản lý. Có thể truyền dependency qua tham số phương thức `@Bean` thay vì gọi chéo phương thức.

```java
@Configuration(proxyBeanMethods = false)
class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        return new OrderService(orderRepository, notificationGateway);
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }
}
```

Truyền dependency qua tham số phương thức `@Bean` giúp thể hiện rõ quan hệ giữa các bean và hoạt động tốt với cả cấu hình đầy đủ lẫn cấu hình lite.

### 2.2. Bean name và kiểu bean

Mặc định, tên bean do phương thức `@Bean` tạo ra chính là tên phương thức. Ví dụ `orderRepository()` tạo bean tên `orderRepository`. Có thể chỉ định tên khác:

```java
@Bean("primaryOrderRepository")
OrderRepository orderRepository() {
    return new InMemoryOrderRepository();
}
```

Spring thường resolve dependency theo kiểu. Khi có nhiều bean cùng kiểu, cần dùng `@Qualifier` hoặc đánh dấu bean ưu tiên bằng `@Primary` để loại bỏ sự mơ hồ:

```java
@Bean
@Primary
OrderRepository inMemoryOrderRepository() {
    return new InMemoryOrderRepository();
}

@Bean
@Qualifier("archive")
OrderRepository archiveOrderRepository() {
    return new ArchiveOrderRepository();
}
```

Khi test cần xác nhận bean cụ thể được chọn, hãy khai báo qualifier ở cả điểm tạo bean và điểm inject:

```java
@Bean
OrderService orderService(
        @Qualifier("archive") OrderRepository repository,
        NotificationGateway notificationGateway) {
    return new OrderService(repository, notificationGateway);
}
```

## 3. Kết hợp @ContextConfiguration với JUnit Jupiter

`@ContextConfiguration` mô tả context nhưng không tự đăng ký extension của JUnit Jupiter. Khi dùng trực tiếp annotation này với JUnit Jupiter, cần thêm:

```java
@ExtendWith(SpringExtension.class)
```

`SpringExtension` triển khai tích hợp JUnit Jupiter với Spring TestContext Framework. Extension phối hợp việc chuẩn bị test instance, dependency injection, quản lý transaction test và các callback vòng đời do Spring Test hỗ trợ.

### 3.1. Dùng @SpringJUnitConfig như cách viết gọn

Spring cung cấp annotation kết hợp `@SpringJUnitConfig`. Annotation này gộp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // Assertion trên orderService.
    }
}
```

Hai cách sau tương đương về ý định cấu hình:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class ExplicitConfigurationTest {
}

@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class ComposedAnnotationTest {
}
```

Dùng `@ContextConfiguration` khi muốn thấy rõ từng annotation hoặc cần kết hợp với các annotation khác. Dùng `@SpringJUnitConfig` khi muốn khai báo ngắn gọn cho test JUnit Jupiter.

### 3.2. Tiêm bean vào test instance

Spring Test có thể tiêm dependency vào field, setter hoặc constructor của test class. Field injection là ví dụ ngắn gọn:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void serviceBeanIsAvailable() {
        assertThat(orderService).isNotNull();
    }
}
```

Nếu muốn dùng constructor injection cho test class, có thể đánh dấu constructor bằng `@Autowired` hoặc cấu hình `@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)`. Với JUnit Jupiter, cũng có thể đặt chế độ autowire constructor toàn cục qua thuộc tính `spring.test.constructor.autowire.mode`. Hãy chọn một cách rõ ràng để tránh nhầm lẫn với cơ chế constructor của JUnit.

## 4. Truyền nhiều lớp cấu hình

Một ứng dụng thường chia cấu hình theo trách nhiệm: service, persistence, web, security hoặc tích hợp ngoài. Thuộc tính `classes` nhận một mảng class nên test có thể kết hợp nhiều nguồn Java configuration:

```java
@SpringJUnitConfig(classes = {
        ServiceTestConfiguration.class,
        PersistenceTestConfiguration.class,
        NotificationTestConfiguration.class
})
class OrderIntegrationTest {

    @Autowired
    private OrderService orderService;
}
```

Spring nạp các lớp cấu hình đã chỉ định trong cùng một context. Bean ở một cấu hình có thể nhận dependency được khai báo ở cấu hình khác nếu type và qualifier phù hợp.

Khi nhiều test dùng chung một tập cấu hình, nên đặt tên class phản ánh trách nhiệm và tái sử dụng chúng. Tránh đưa toàn bộ cấu hình ứng dụng vào mọi test nếu test chỉ cần một phần nhỏ; context càng lớn thì thời gian khởi tạo và số dependency liên quan càng tăng.

### 4.1. Kết hợp cấu hình bằng @Import

Thay vì liệt kê tất cả class trong từng test, một cấu hình gốc có thể import các cấu hình nhỏ hơn:

```java
@Configuration
@Import({
        RepositoryTestConfiguration.class,
        NotificationTestConfiguration.class
})
class OrderServiceTestConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            NotificationGateway notificationGateway) {
        return new OrderService(repository, notificationGateway);
    }
}
```

Test chỉ cần tham chiếu cấu hình gốc:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceTest {
    // Inject OrderService và thực hiện test.
}
```

`@Import` hữu ích khi một cấu hình tổng hợp cần tái sử dụng các module cấu hình độc lập. Nó cũng giúp tránh một test class phải biết quá nhiều chi tiết cấu hình nội bộ.

### 4.2. Component scanning trong Java configuration

Nếu muốn Spring tự phát hiện các component, có thể dùng `@ComponentScan`. Nên giới hạn package hoặc chỉ định class gốc để tránh quét quá rộng:

```java
@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
class ApplicationComponentTestConfiguration {
}
```

`basePackageClasses` cho phép chỉ định một class marker; Spring dùng package chứa class đó làm package cần scan. Đây là lựa chọn ít phụ thuộc vào chuỗi package viết tay hơn `basePackages`.

Khi dùng component scanning, cần tránh đăng ký cùng một bean hai lần bằng cả component scan và phương thức `@Bean`. Nếu có hai bean cùng kiểu, injection có thể trở nên mơ hồ hoặc ứng dụng dùng nhầm triển khai.

### 4.3. Static nested configuration trong test class

Với cấu hình chỉ dùng cho một test, có thể đặt class cấu hình tĩnh bên trong test class để gom phạm vi:

```java
@SpringJUnitConfig(classes = OrderServiceTest.Config.class)
class OrderServiceTest {

    @Configuration
    static class Config {

        @Bean
        OrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        NotificationGateway notificationGateway() {
            return new RecordingNotificationGateway();
        }

        @Bean
        OrderService orderService(
                OrderRepository repository,
                NotificationGateway notificationGateway) {
            return new OrderService(repository, notificationGateway);
        }
    }

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Nested configuration phải là `static` để Spring có thể khởi tạo độc lập với một instance của test class. Cách này thích hợp với cấu hình nhỏ và riêng biệt; nếu nhiều test dùng chung, hãy chuyển cấu hình thành class riêng để tái sử dụng.

## 5. Dùng profile và property trong test context

Java configuration có thể đọc property hoặc tạo bean theo profile. Spring Test cung cấp annotation để điều khiển môi trường khi nạp context.

### 5.1. Chọn profile bằng @ActiveProfiles

`@ActiveProfiles` kích hoạt một hoặc nhiều profile cho context của test:

```java
@Configuration
class OrderConfiguration {

    @Bean
    @Profile("test")
    NotificationGateway testNotificationGateway() {
        return new RecordingNotificationGateway();
    }

    @Bean
    @Profile("production")
    NotificationGateway productionNotificationGateway() {
        return new SmtpNotificationGateway();
    }
}

@SpringJUnitConfig(classes = OrderConfiguration.class)
@ActiveProfiles("test")
class OrderProfileTest {

    @Autowired
    private NotificationGateway notificationGateway;
}
```

Trong test này, Spring chỉ đăng ký bean có profile `test` đang active. `@ActiveProfiles` giúp cấu hình test độc lập với profile mặc định của môi trường chạy ứng dụng.

### 5.2. Nạp property bằng @TestPropertySource

`@TestPropertySource` bổ sung property source cho test context. Có thể chỉ định file hoặc property inline:

```java
@Configuration
class FeatureConfiguration {

    @Value("${orders.max-items:10}")
    private int maxItems;

    @Bean
    OrderLimit orderLimit() {
        return new OrderLimit(maxItems);
    }
}

@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(properties = "orders.max-items=25")
class OrderLimitTest {

    @Autowired
    private OrderLimit orderLimit;
}
```

Ví dụ giả định ứng dụng có class `OrderLimit` nhận giới hạn số lượng. Property inline giúp test kiểm soát giá trị đầu vào của cấu hình. Nếu cấu hình cần nhiều property hoặc được chia sẻ, có thể dùng file resource:

```java
@TestPropertySource(locations = "classpath:/order-test.properties")
```

Giá trị property có thể được đọc bằng `@Value` hoặc thông qua cơ chế binding phù hợp của Spring Framework. Với Java config thuần, test có thể dùng `Environment` trong phương thức `@Bean` nếu muốn đọc giá trị theo cách tường minh.

## 6. Initializer và context loader

Thông thường, chỉ cần truyền Java config qua `classes`. Spring Test sẽ chọn context loader mặc định phù hợp để nạp cấu hình. Không cần tự chỉ định loader trong trường hợp phổ biến.

### 6.1. ApplicationContextInitializer

Khi cần điều chỉnh context trước khi refresh, có thể dùng `ApplicationContextInitializer`. Initializer nhận context chưa refresh và có thể đăng ký property source hoặc bean definition bổ sung:

```java
public class TestPropertyInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of("feature.enabled", "true");
        MapPropertySource source = new MapPropertySource("testOverrides", values);
        context.getEnvironment().getPropertySources().addFirst(source);
    }
}
```

Khai báo initializer trong test:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = FeatureConfiguration.class,
        initializers = TestPropertyInitializer.class
)
class FeatureInitializerTest {
}
```

Initializer chạy trong giai đoạn chuẩn bị context. Chỉ nên dùng khi việc thiết lập môi trường cần diễn ra trước khi bean được tạo; với property đơn giản, `@TestPropertySource` thường dễ đọc hơn.

### 6.2. Khi nào cần chỉ định context loader?

Thuộc tính `loader` của `@ContextConfiguration` cho phép chỉ định một triển khai `ContextLoader` tùy chỉnh (các loader hiện đại thường triển khai hợp đồng mở rộng `SmartContextLoader`). Với Java configuration tiêu chuẩn, loader mặc định đã hỗ trợ nạp class cấu hình nên thường không cần thiết lập thuộc tính này.

Chỉ viết loader riêng khi có cơ chế nạp context đặc thù mà các loader tiêu chuẩn không đáp ứng. Việc chỉ định loader không đúng có thể làm Spring hiểu sai `locations` hoặc `classes`, dẫn đến context không được tạo như mong muốn.

## 7. Kế thừa cấu hình giữa các test class

Nếu một nhóm test dùng chung cấu hình, có thể đặt annotation trên lớp cha:

```java
@SpringJUnitConfig(classes = SharedServiceTestConfiguration.class)
abstract class BaseServiceTest {

    @Autowired
    protected OrderService orderService;
}

class CreateOrderTest extends BaseServiceTest {

    @Test
    void createsOrder() {
        // Dùng orderService đã được inject.
    }
}
```

Theo mặc định, cấu hình context được kế thừa. Test class con có thể bổ sung class cấu hình riêng:

```java
@ContextConfiguration(classes = SpecialCaseTestConfiguration.class)
class SpecialOrderTest extends BaseServiceTest {
}
```

Khi kế thừa, các class cấu hình cục bộ thường được kết hợp với cấu hình của lớp cha. Nếu muốn thay thế hoàn toàn cấu hình kế thừa, có thể đặt `inheritLocations = false`:

```java
@ContextConfiguration(
        classes = IsolatedTestConfiguration.class,
        inheritLocations = false
)
class IsolatedOrderTest extends BaseServiceTest {
}
```

Tên thuộc tính `inheritLocations` được giữ từ mô hình cấu hình test ban đầu và áp dụng cho tập `locations` hoặc `classes` được kế thừa. Hãy dùng nó khi lớp con thực sự cần một tập cấu hình độc lập; nếu chỉ cần bổ sung bean, kết hợp cấu hình thường dễ bảo trì hơn.

## 8. Context caching và @DirtiesContext

Spring TestContext Framework cache `ApplicationContext` để những test có cấu hình tương thích có thể dùng lại context đã tạo. Việc cache giúp giảm thời gian chạy khi một bộ test có nhiều class sử dụng cùng cấu hình.

Khóa cache được tạo từ metadata cấu hình, chẳng hạn:

- Class cấu hình hoặc resource location.
- Context initializer.
- Active profile.
- Property source và thuộc tính inline.
- Context loader và context customizer.
- Các cấu hình liên quan khác do Spring TestContext quản lý.

Nếu hai test dùng cùng metadata, Spring có thể tái sử dụng context. Nếu thay đổi cấu hình, context có thể có cache key khác và được tạo riêng.

### 8.1. Khi nào dùng @DirtiesContext?

`@DirtiesContext` đánh dấu context đã bị test làm thay đổi trạng thái đến mức không nên tái sử dụng. Spring Test sẽ loại context đó khỏi cache theo chế độ được chọn và tạo lại khi cần.

```java
@SpringJUnitConfig(classes = MutableStateTestConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // Test làm thay đổi trạng thái bean dùng chung và cần context mới sau class.
}
```

Không dùng `@DirtiesContext` như cách dọn mọi trạng thái sau mỗi test. Nếu vấn đề chỉ là dữ liệu trong repository hoặc collection, hãy reset dữ liệu bằng API phù hợp. Tạo lại context tốn thời gian và có thể che giấu việc test quản lý trạng thái chưa tốt.

## 9. Phân biệt @ContextConfiguration với các annotation khác

| Annotation | Vai trò | Khi nên dùng |
|---|---|---|
| `@ContextConfiguration` | Chỉ định cấu hình hoặc class để TestContext tạo ApplicationContext. | Khi test cần một Spring context được xác định rõ bằng Java config hoặc resource. |
| `@SpringJUnitConfig` | Kết hợp SpringExtension với ContextConfiguration cho JUnit Jupiter. | Khi viết Spring context test trên JUnit Jupiter. |
| `@ExtendWith(SpringExtension.class)` | Kết nối JUnit Jupiter với Spring TestContext Framework. | Khi muốn dùng trực tiếp annotation ContextConfiguration và các tiện ích Spring Test. |
| `@SpringBootTest` | Bootstrap ứng dụng Spring Boot bằng cơ chế của Boot. | Khi cần kiểm tra cấu hình, auto-configuration và tích hợp của ứng dụng Boot. |
| `@WebAppConfiguration` | Yêu cầu TestContext tạo web application context dựa trên Servlet API. | Khi test cần web application context trong môi trường Spring Framework Test. |

`@ContextConfiguration` không tự bật component scanning nếu cấu hình Java không khai báo `@ComponentScan` hoặc không import cấu hình có scanning. Nó cũng không tự tạo một servlet environment chỉ vì có class controller trong danh sách cấu hình.

Nếu mục tiêu là kiểm tra wiring của một vài bean Spring Framework, Java config kết hợp `@ContextConfiguration` là đủ. Nếu mục tiêu là kiểm tra ứng dụng Boot được bootstrap cùng auto-configuration, hãy dùng annotation và hạ tầng test của Boot.

## 10. Ví dụ hoàn chỉnh: test với nhiều Java configuration

Ví dụ dưới đây minh họa một cấu hình test tách thành hai class: một class khai báo repository và gateway, một class tạo service. Test dùng `@SpringJUnitConfig` để nạp cấu hình tổng hợp.

```java
@Configuration(proxyBeanMethods = false)
class RepositoryTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}

@Configuration(proxyBeanMethods = false)
class GatewayTestConfiguration {

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }
}

@Configuration(proxyBeanMethods = false)
@Import({
        RepositoryTestConfiguration.class,
        GatewayTestConfiguration.class
})
class OrderServiceTestConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            NotificationGateway notificationGateway) {
        return new OrderService(repository, notificationGateway);
    }
}

@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceContextTest {

    @Autowired
    private OrderService orderService;

    @Test
    void contextProvidesOrderService() {
        assertThat(orderService).isNotNull();
    }

    @Test
    void createsOrderUsingBeansFromImportedConfigurations() {
        Order order = new Order("customer-1", "SKU-1", 2);

        assertThat(orderService.create(order)).isEqualTo(order);
    }
}
```

Các triển khai `InMemoryOrderRepository` và `RecordingNotificationGateway` là ví dụ test fixture. Nếu dùng một repository thật hoặc kết nối database, bài test sẽ mở rộng phạm vi sang persistence integration test; khi đó cần bổ sung cấu hình database phù hợp.

## 11. Những lỗi thường gặp

### Dùng @ContextConfiguration mà quên SpringExtension

Với JUnit Jupiter, `@ContextConfiguration` chỉ mô tả metadata. Nếu test class không dùng `@ExtendWith(SpringExtension.class)` hoặc annotation tổng hợp như `@SpringJUnitConfig`, Spring Test không được tích hợp để chuẩn bị context và inject dependency theo vòng đời test.

### Đưa nhầm class vào thuộc tính classes

Các class trong `classes` phải là component/configuration class có thể dùng để nạp context. Nếu class không khai báo bean, không phải component và không import cấu hình khác, context có thể không chứa bean mà test mong đợi.

### Quên @Bean hoặc @ComponentScan

Một class Java tồn tại trong source code không có nghĩa Spring tự đăng ký nó thành bean. Hãy khai báo `@Bean`, dùng stereotype annotation kết hợp component scanning hoặc import một cấu hình có chứa bean.

### Có nhiều bean cùng kiểu

Nếu nhiều class cấu hình khai báo cùng một interface, Spring có thể không biết phải inject bean nào. Dùng `@Qualifier`, `@Primary` hoặc giới hạn cấu hình để lựa chọn rõ ràng.

### Trộn cấu hình Java và component scan gây trùng bean

Nếu một class đã được phát hiện qua `@ComponentScan` và cũng được khai báo bằng `@Bean`, context có thể có nhiều bean cùng trách nhiệm. Kiểm tra package scan và cách đăng ký bean để tránh xung đột.

### Kỳ vọng @Value hoạt động khi không có context

`@Value` được Spring xử lý trong quá trình tạo bean. Nếu test gọi `new` trực tiếp với class chứa field `@Value`, field không tự nhận property. Cần nạp bean qua context hoặc truyền giá trị qua constructor.

### Dùng @DirtiesContext quá thường xuyên

Đánh dấu context dirty sẽ làm giảm lợi ích cache và kéo dài thời gian test. Chỉ dùng khi trạng thái context thật sự bị thay đổi và không thể reset một cách an toàn ở phạm vi bean hoặc dữ liệu.

### Nhầm @ContextConfiguration với @SpringBootTest

`@ContextConfiguration` dùng cơ chế Spring TestContext để nạp các class hoặc resource đã chỉ định. `@SpringBootTest` yêu cầu Spring Boot bootstrap ứng dụng và áp dụng cơ chế auto-configuration của Boot. Chọn annotation dựa trên phạm vi context mà test cần.

## 12. Cách chọn cấu hình cho từng bài test

- Cần một vài bean từ Java configuration? Dùng `@ContextConfiguration(classes = ...)` cùng `SpringExtension`.
- Muốn khai báo gọn trên JUnit Jupiter? Dùng `@SpringJUnitConfig(classes = ...)`.
- Cần kết hợp nhiều cấu hình? Truyền nhiều class trong `classes` hoặc dùng `@Import`.
- Cần tự động phát hiện component? Khai báo `@ComponentScan` với phạm vi package rõ ràng.
- Cần profile hoặc property riêng? Kết hợp `@ActiveProfiles` và `@TestPropertySource`.
- Cần thay đổi môi trường trước khi context refresh? Dùng `ApplicationContextInitializer`.
- Cần bootstrap ứng dụng Boot và auto-configuration? Chọn `@SpringBootTest`.

Khi dùng Java configuration với `@ContextConfiguration`, hãy xem class cấu hình là bản mô tả object graph mà test cần. Khai báo rõ bean, import đúng module cấu hình và để Spring Test quản lý context cùng vòng đời test. Cách tổ chức đó giúp bài kiểm thử tập trung vào tích hợp giữa các bean Spring Framework mà không phụ thuộc vào cơ chế bootstrap của Spring Boot.
