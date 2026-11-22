# Kiểm thử cấu hình bean và một hành vi đi qua proxy

Một Spring application có thể khởi động thành công nhưng vẫn chọn nhầm bean, bỏ sót một cấu hình theo profile hoặc không áp dụng một cơ chế được kích hoạt bằng proxy. Vì vậy, kiểm thử một class bằng cách gọi `new` trực tiếp chưa đủ để chứng minh ứng dụng hoạt động đúng khi được Spring quản lý.

Một bài kiểm thử tích hợp ở mức phù hợp cần xác nhận hai việc liên quan nhưng khác nhau:

1. **Cấu hình bean:** Spring tạo đúng bean, inject đúng dependency, chọn đúng implementation và áp dụng đúng cấu hình môi trường.
2. **Hành vi qua proxy:** lời gọi đi qua proxy do Spring tạo để interceptor như transaction, cache, retry, security hoặc async thực sự được áp dụng.

Bài này dùng `@Transactional` làm hành vi đại diện. Test sẽ nạp cấu hình Spring thật, lấy service từ `ApplicationContext`, xác nhận service được proxy và chứng minh một thao tác ghi database bị rollback khi phương thức ném runtime exception. Cách tiếp cận tương tự có thể áp dụng cho các hành vi dựa trên proxy khác.

## 1. Phân biệt kiểm thử object với kiểm thử bean Spring

Giả sử có một service:

```java
class OrderService {

    private final OrderRepository orderRepository;

    OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

Unit test có thể tạo service trực tiếp và truyền mock repository:

```java
OrderRepository repository = mock(OrderRepository.class);
OrderService service = new OrderService(repository);

service.createOrder(order);

verify(repository).save(order);
```

Test này hữu ích để xác nhận logic gọi repository. Nhưng object được tạo bằng `new` không đi qua Spring container, do đó annotation `@Transactional` không tự tạo transaction. Tương tự, `@Cacheable`, `@Async`, `@Retryable` hoặc `@PreAuthorize` cũng không tự hoạt động chỉ vì annotation có mặt trên method.

Khi cần kiểm tra bean wiring và hành vi do Spring áp dụng, phải lấy bean từ context:

```java
@Autowired
OrderService orderService;
```

Spring tạo target object, đăng ký bean và có thể bọc nó bằng proxy. Test gọi bean đã inject để đi qua cùng cơ chế mà ứng dụng sử dụng.

## 2. Nạp đúng cấu hình Spring trong test

Spring Test cung cấp một số cách dựng application context. Chọn cách phù hợp với phạm vi cần kiểm tra:

| Cách dựng context | Phạm vi | Khi nên dùng |
|---|---|---|
| `@SpringJUnitConfig(TestConfig.class)` | Spring TestContext với cấu hình Java/XML được chỉ định | Kiểm tra một nhóm bean và infrastructure có phạm vi rõ. |
| `@ContextConfiguration(classes = ...)` | Đăng ký cấu hình hoặc initializer cho context | Dùng khi cần kiểm soát cấu hình context chi tiết. |
| `@Import(TestConfig.class)` | Bổ sung cấu hình vào context test hiện có | Thêm bean hỗ trợ hoặc thay thế một phần cấu hình. |
| `@SpringBootTest` | Nạp application context của Spring Boot | Kiểm tra auto-configuration, component scan, profile và wiring toàn ứng dụng. |
| `ApplicationContextRunner` | Tạo context nhỏ theo từng lần chạy | Kiểm tra auto-configuration và điều kiện tạo bean nhanh, độc lập. |

### Dùng `@SpringJUnitConfig`

Khi mục tiêu là kiểm tra một cấu hình cụ thể, `@SpringJUnitConfig` giúp test ngắn và không cần khởi động toàn bộ ứng dụng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderConfigurationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void registersOrderService() {
        assertThat(applicationContext.getBean(OrderService.class))
                .isNotNull();
    }
}
```

`@SpringJUnitConfig` kết hợp hỗ trợ JUnit Jupiter với Spring TestContext. Context được tạo theo cấu hình đã chỉ định và có thể được tái sử dụng qua context cache nếu các test có cùng cấu hình.

### Dùng `@SpringBootTest`

Nếu điều cần xác nhận phụ thuộc vào component scan, auto-configuration, profile hoặc property của ứng dụng, nên nạp application context thực:

```java
@SpringBootTest
class ApplicationBeanConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void loadsRequiredApplicationBeans() {
        assertThat(context.getBean(OrderService.class)).isNotNull();
        assertThat(context.getBean(PlatformTransactionManager.class)).isNotNull();
    }
}
```

Không cần dùng `@SpringBootTest` cho mọi bài test bean. Full context có thể khởi tạo nhiều dịch vụ và tăng thời gian suite. Nếu một cấu hình nhỏ đã đủ chứng minh wiring cần thiết, dùng `@SpringJUnitConfig` sẽ làm phạm vi test dễ hiểu hơn.

## 3. Kiểm tra bean được đăng ký và inject đúng

Một context test nên xác nhận những hợp đồng cấu hình quan trọng, chẳng hạn:

- Bean bắt buộc có mặt.
- Chỉ có một bean phù hợp với kiểu dependency cần inject, hoặc bean được chọn theo `@Primary`/`@Qualifier`.
- Bean được tạo từ đúng profile hoặc property.
- Implementation đúng được sử dụng trong môi trường test.
- Bean phụ thuộc vào cùng một instance infrastructure khi điều đó quan trọng, ví dụ repository và transaction manager cùng dùng một `DataSource`.

Ví dụ có hai implementation của `PaymentGateway`:

```java
interface PaymentGateway {
    String providerName();
}

class CardPaymentGateway implements PaymentGateway {
    @Override
    public String providerName() {
        return "card";
    }
}

class SandboxPaymentGateway implements PaymentGateway {
    @Override
    public String providerName() {
        return "sandbox";
    }
}
```

Cấu hình chọn bean mặc định và bean có qualifier:

```java
@Configuration
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("sandbox")
    PaymentGateway sandboxPaymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Test có thể xác nhận cả lựa chọn mặc định lẫn lựa chọn có qualifier:

```java
@SpringJUnitConfig(PaymentConfiguration.class)
class PaymentConfigurationTest {

    @Autowired
    PaymentGateway defaultGateway;

    @Autowired
    @Qualifier("sandbox")
    PaymentGateway sandboxGateway;

    @Test
    void selectsTheExpectedPaymentImplementations() {
        assertThat(defaultGateway.providerName()).isEqualTo("card");
        assertThat(sandboxGateway.providerName()).isEqualTo("sandbox");
    }
}
```

Test này xác nhận quy tắc bean selection của Spring, không chỉ xác nhận hai class có thể được khởi tạo độc lập.

### Kiểm tra profile và property có điều kiện

Khi bean phụ thuộc vào profile:

```java
@Configuration
class NotificationConfiguration {

    @Bean
    @Profile("test")
    NotificationClient testNotificationClient() {
        return new StubNotificationClient();
    }
}
```

Test có thể kích hoạt profile bằng `@ActiveProfiles("test")` rồi xác nhận implementation được đăng ký. Với Spring Boot auto-configuration dùng `@ConditionalOnProperty`, `ApplicationContextRunner` giúp kiểm tra cả trường hợp bật và tắt property:

```java
new ApplicationContextRunner()
        .withUserConfiguration(AuditAutoConfiguration.class)
        .withPropertyValues("app.audit.enabled=true")
        .run(context -> assertThat(context).hasSingleBean(AuditPublisher.class));

new ApplicationContextRunner()
        .withUserConfiguration(AuditAutoConfiguration.class)
        .withPropertyValues("app.audit.enabled=false")
        .run(context -> assertThat(context).doesNotHaveBean(AuditPublisher.class));
```

`ApplicationContextRunner` phù hợp với test auto-configuration vì mỗi lần `run` tạo một context nhỏ với property riêng. Nó giúp xác nhận điều kiện đăng ký bean mà không phải khởi động toàn bộ ứng dụng.

## 4. Proxy của Spring hoạt động như thế nào?

Spring AOP thường áp dụng các hành vi cross-cutting bằng cách tạo một proxy bao quanh bean. Caller gọi proxy; proxy chạy interceptor/advice phù hợp rồi mới chuyển lời gọi đến target object.

```text
Caller
  |
  v
Spring-managed bean reference
  |
  v
Proxy
  |
  +--> Transaction interceptor
  |       - bắt đầu transaction
  |       - gọi target method
  |       - commit hoặc rollback
  |
  v
Target object
  |
  v
Repository / database
```

Với `@Transactional`, transaction interceptor lấy `PlatformTransactionManager` phù hợp, bắt đầu hoặc tham gia transaction, gọi method trên target, sau đó commit hoặc rollback theo kết quả.

Proxy có thể được tạo theo hai cách phổ biến:

- **JDK dynamic proxy:** proxy dựa trên interface mà bean triển khai. Caller thường inject qua interface.
- **Class-based proxy (CGLIB):** tạo subclass của class target để chặn lời gọi method.

Với cấu hình transaction mặc định, Spring thường dùng JDK proxy khi target triển khai interface và dùng class-based proxy khi không có interface phù hợp. Các tùy chọn như `proxyTargetClass` có thể thay đổi lựa chọn. Spring Boot cũng có thể đặt cấu hình proxy mặc định riêng.

Điều quan trọng với test là lấy bean từ context và gọi method qua reference được inject. Tự tạo target bằng `new`, gọi trực tiếp method nội bộ hoặc lấy target object phía sau proxy sẽ bỏ qua interceptor.

## 5. Chọn một hành vi proxy để kiểm thử: transaction rollback

`@Transactional` là ví dụ tốt vì có thể quan sát kết quả ở database. Nếu phương thức thực hiện một câu lệnh ghi rồi ném runtime exception, transaction interceptor mặc định rollback transaction. Test xác nhận bản ghi không tồn tại sau khi lời gọi thất bại.

Hành vi cần chứng minh:

```text
Test gọi Spring-managed OrderService proxy
                 |
                 v
        Transaction interceptor
                 |
          BEGIN transaction
                 |
                 v
          INSERT order row
                 |
                 v
          Runtime exception
                 |
                 v
          ROLLBACK transaction
                 |
                 v
       Query từ test: không có row
```

Để phép thử có ý nghĩa, test method không được tự mở transaction bao quanh lời gọi service. Nếu test đã có transaction bên ngoài, transaction của service có thể tham gia transaction đó và dữ liệu chưa bị rollback tại thời điểm assertion được chạy.

## 6. Tạo cấu hình test với DataSource và transaction manager thật

Ví dụ sau dùng H2 embedded database và `JdbcTemplate`. H2 cho phép kiểm tra transaction behavior mà không cần cài một database server bên ngoài.

Dependency test cần có Spring Test, Spring JDBC, H2 và JUnit Jupiter. Nếu dùng Spring Boot dependency management, nên để BOM quản lý version tương thích:

```groovy
testImplementation 'org.springframework:spring-test'
testImplementation 'org.springframework:spring-jdbc'
testImplementation 'com.h2database:h2'
testImplementation 'org.junit.jupiter:junit-jupiter'
```

Cấu hình Spring đăng ký DataSource, JdbcTemplate, transaction manager và service:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
class TransactionalTestConfiguration {

    @Bean
    EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
                .setType(EmbeddedDatabaseType.H2)
                .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    InitializingBean createSchema(JdbcTemplate jdbcTemplate) {
        return () -> jdbcTemplate.execute("""
                create table orders (
                    id varchar(100) primary key
                )
                """);
    }

    @Bean
    OrderService orderService(JdbcTemplate jdbcTemplate) {
        return new OrderService(jdbcTemplate);
    }
}
```

`@EnableTransactionManagement` đăng ký hạ tầng xử lý annotation transaction. `DataSourceTransactionManager` quản lý transaction JDBC trên chính DataSource được inject vào `JdbcTemplate`. Cả service và test đều dùng cùng database trong context.

`EmbeddedDatabase` là một `DataSource` có lifecycle shutdown. Vì nó được đăng ký như bean, Spring đóng nó khi context bị đóng.

## 7. Service có một phương thức thành công và một phương thức cố ý thất bại

Service dưới đây có hai public method đều được đánh dấu `@Transactional`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

class OrderService {

    private final JdbcTemplate jdbcTemplate;

    OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void create(String orderId) {
        jdbcTemplate.update(
                "insert into orders (id) values (?)",
                orderId);
    }

    @Transactional
    public void createThenFail(String orderId) {
        jdbcTemplate.update(
                "insert into orders (id) values (?)",
                orderId);

        throw new IllegalStateException("Simulated failure after insert");
    }
}
```

`createThenFail` ghi dữ liệu trước khi ném `IllegalStateException`. Theo mặc định, Spring rollback transaction khi method ném unchecked exception (`RuntimeException` hoặc `Error`). Vì vậy, câu lệnh insert phải bị rollback.

Nếu method ném checked exception, mặc định Spring không rollback chỉ vì exception đó. Khi nghiệp vụ yêu cầu rollback cho checked exception, cần khai báo `rollbackFor` hoặc quy tắc rollback phù hợp và viết test xác nhận chính sách đó.

## 8. Test lấy bean từ context và gọi qua proxy

Test dùng `@SpringJUnitConfig` để dựng context, inject service và JdbcTemplate. Test method không gắn `@Transactional`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TransactionalTestConfiguration.class)
class OrderServiceProxyTest {

    @Autowired
    OrderService orderService;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void cleanDatabase() {
        jdbcTemplate.update("delete from orders");
    }

    @Test
    void injectsAProxiedOrderService() {
        assertThat(AopUtils.isAopProxy(orderService)).isTrue();
        assertThat(AopUtils.getTargetClass(orderService))
                .isEqualTo(OrderService.class);
    }

    @Test
    void commitsWhenTransactionalMethodReturnsNormally() {
        orderService.create("order-100");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "order-100");

        assertThat(count).isEqualTo(1);
    }

    @Test
    void rollsBackInsertWhenTransactionalMethodThrowsRuntimeException() {
        assertThatThrownBy(() -> orderService.createThenFail("order-200"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated failure after insert");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "order-200");

        assertThat(count).isZero();
    }
}
```

Test trên xác nhận ba điều:

1. Bean được inject là một AOP proxy.
2. Lời gọi thành công commit dữ liệu.
3. Lời gọi ném runtime exception rollback dữ liệu đã ghi trong cùng transaction.

Assertion `AopUtils.isAopProxy(...)` giúp xác nhận proxy tồn tại, nhưng bằng chứng quan trọng hơn là kết quả database. Một proxy có thể tồn tại mà không áp dụng đúng interceptor mong muốn nếu cấu hình sai; kiểm tra hiệu ứng transaction chứng minh hành vi thực tế.

## 9. Vì sao test method không nên có `@Transactional` trong ví dụ rollback?

Spring Test có thể mở transaction cho chính test method khi gắn `@Transactional` trên class hoặc method. Transaction này thường được rollback sau khi test kết thúc.

Nếu service dùng propagation mặc định `REQUIRED`, transaction do service mở sẽ tham gia transaction đang tồn tại của test. Khi `createThenFail` ném exception, transaction có thể bị đánh dấu rollback-only, nhưng test vẫn đang ở bên trong transaction ngoài. Một query thực hiện ngay sau khi bắt exception có thể vẫn nhìn thấy row chưa được rollback cho đến khi transaction test kết thúc.

Do đó, test có thể cho kết quả sai nếu kiểm tra database trước khi transaction test được rollback. Trong bài kiểm thử này, để service sở hữu transaction của nó và kiểm tra trạng thái database sau khi proxy đã kết thúc lời gọi, không đánh dấu test method `@Transactional`.

Nếu test suite có chính sách transaction mặc định ở base class, hãy tách bài kiểm thử transaction proxy sang class không tham gia test-managed transaction hoặc cấu hình rõ cách kết thúc transaction trước khi assertion.

## 10. Kiểm tra cấu hình bean và proxy là hai lớp bằng chứng khác nhau

Một test có thể xác nhận bean tồn tại nhưng chưa chứng minh annotation hoạt động. Ngược lại, một test rollback có thể chứng minh transaction behavior nhưng chưa chắc xác nhận tất cả bean selection của ứng dụng.

Nên tách assertion theo mục tiêu:

| Điều cần chứng minh | Bằng chứng phù hợp |
|---|---|
| Configuration class được nạp | Context khởi động với cấu hình được chỉ định. |
| Bean tồn tại | `context.getBean(...)` hoặc assertion `hasSingleBean(...)`. |
| Đúng implementation được chọn | Kiểm tra bean theo type, qualifier, profile hoặc property. |
| Dependency được inject đúng | Gọi bean thực hoặc kiểm tra collaborator được chọn qua hành vi. |
| Bean có proxy | `AopUtils.isAopProxy(bean)` hoặc kiểm tra kiểu proxy khi cần. |
| Transaction thực sự hoạt động | Quan sát commit/rollback trên resource thật hoặc transaction state trong lời gọi. |
| Security/retry/cache/async thực sự hoạt động | Gọi qua bean proxy và xác nhận hiệu ứng tương ứng. |

Không nên chỉ kiểm tra `bean.getClass()` bằng tên class cụ thể. Tên lớp proxy có thể thay đổi theo JDK/CGLIB, phiên bản Spring và cấu hình. Dùng `AopUtils`, interface contract và hành vi quan sát được để assertion bền vững hơn.

## 11. Bẫy self-invocation: lời gọi nội bộ bỏ qua proxy

Proxy-based AOP chỉ chặn lời gọi đi qua proxy. Nếu một method trong target gọi method khác trên chính `this`, lời gọi nội bộ không quay lại proxy.

Ví dụ:

```java
@Service
class BillingService {

    public void processInvoice(String invoiceId) {
        saveInvoice(invoiceId);
    }

    @Transactional
    public void saveInvoice(String invoiceId) {
        // Ghi dữ liệu.
    }
}
```

Khi caller gọi `billingService.processInvoice(...)`, lời gọi `this.saveInvoice(...)` bên trong target không đi qua proxy lần nữa. Transaction annotation trên `saveInvoice` có thể không được áp dụng như mong đợi.

Cách giải quyết thường tốt hơn là đặt transaction boundary trên public method được gọi từ bên ngoài:

```java
@Transactional
public void processInvoice(String invoiceId) {
    saveInvoiceData(invoiceId);
}

private void saveInvoiceData(String invoiceId) {
    // Ghi dữ liệu trong transaction của processInvoice.
}
```

Hoặc tách phần cần transaction thành một bean collaborator riêng để lời gọi đi qua proxy của bean đó. Không nên đưa self-injection hoặc lấy proxy từ `AopContext` vào mọi class chỉ để né self-invocation; các cách đó tăng coupling và làm luồng gọi khó hiểu.

Một bài test proxy nên gọi đúng public entry point mà ứng dụng gọi. Nếu chỉ gọi trực tiếp method được đánh dấu annotation trên target object, test không xác nhận được đường đi của proxy.

## 12. Giới hạn method và class khi dùng proxy

Với JDK dynamic proxy, lời gọi thường phải đi qua interface mà bean expose. Caller nên inject interface thay vì cố cast sang class implementation.

Với class-based proxy (CGLIB):

- Class `final` không thể được subclass để tạo proxy.
- Method `final` không thể bị override để intercept.
- Method `private` không thể được intercept bằng proxy subclass.
- Public method là lựa chọn dễ dự đoán nhất cho các annotation dựa trên proxy.

Nếu một bean không được proxy như mong đợi, hãy kiểm tra kiểu proxy, interface, modifier của class/method và cách bean được tạo. Một object được khởi tạo thủ công, trả ra từ factory ngoài Spring hoặc bị unwrap khỏi proxy cũng có thể bỏ qua interception.

## 13. Có thể áp dụng cách kiểm thử này cho hành vi proxy nào khác?

`@Transactional` chỉ là một ví dụ. Nguyên tắc chung là: nạp bean thật, gọi qua reference từ context và xác nhận hiệu ứng mà interceptor tạo ra.

| Hành vi | Điều cần kiểm tra qua proxy |
|---|---|
| `@Cacheable` | Lần gọi thứ hai dùng cache theo key mong đợi; collaborator phía sau không bị gọi lại khi cache hit. |
| `@CacheEvict` | Cache entry bị xóa tại thời điểm và theo key được cấu hình. |
| `@Async` | Công việc chạy trên executor khác hoặc trả `CompletableFuture` hoàn tất đúng kết quả. |
| `@PreAuthorize` | Principal không đủ quyền bị từ chối trước khi method target thực hiện nghiệp vụ. |
| `@Retryable` | Lời gọi được thử lại đúng số lần và dừng khi thành công hoặc hết retry. |
| Custom Spring AOP advice | Advice được thực thi trước/sau target theo pointcut và thứ tự đã cấu hình. |

Với mỗi loại, cần có assertion hành vi cụ thể. Chỉ kiểm tra `AopUtils.isAopProxy(...)` không chứng minh cache hit, async dispatch, security denial hoặc retry policy đang hoạt động đúng.

### Ví dụ ngắn với `@Cacheable`

Giả sử service đọc giá sản phẩm và cache kết quả:

```java
@Service
class ProductPriceService {

    private final PriceRepository repository;

    ProductPriceService(PriceRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "prices", key = "#sku")
    public BigDecimal priceOf(String sku) {
        return repository.findPrice(sku);
    }
}
```

Test cần nạp `@EnableCaching`, cache manager và service bean từ context. Gọi cùng key hai lần, xác nhận kết quả giống nhau và repository chỉ được gọi một lần. Nếu tạo service bằng `new`, cache interceptor sẽ không chạy. Test cũng phải dọn cache giữa các test để không dùng lại dữ liệu từ context cache.

## 14. Khi nào dùng `@TestConfiguration`, `@Import` và bean override?

Trong integration test, đôi khi cần thay một dependency bên ngoài bằng stub hoặc mock trong khi giữ service thật và proxy thật.

`@TestConfiguration` có thể bổ sung bean chỉ dành cho test:

```java
@TestConfiguration
class TestGatewayConfiguration {

    @Bean
    @Primary
    PaymentGateway testPaymentGateway() {
        return new StubPaymentGateway();
    }
}
```

Nạp cấu hình bằng `@Import(TestGatewayConfiguration.class)` trong test. Cần chú ý nếu ứng dụng đã có bean cùng kiểu và có `@Primary` khác; hãy xác nhận bean thực sự được chọn.

Với Spring Boot, có thể dùng cơ chế mock bean phù hợp với phiên bản Spring Boot đang dùng. Một số API cũ như `@MockBean` được thay thế dần bởi cơ chế bean override mới ở các phiên bản Spring Framework/Boot mới. Dù dùng công cụ nào, test phải giữ bean cần kiểm tra (ví dụ service transactional) là bean thật do Spring quản lý, chỉ thay collaborator bên ngoài khi có chủ đích.

Đừng mock chính bean mà test muốn kiểm tra proxy. Nếu `OrderService` bị thay bằng mock, test không còn chứng minh `@Transactional` trên implementation thật.

## 15. Kiểm tra transaction bằng transaction manager hoặc database?

Có hai cách tiếp cận thường gặp:

**Quan sát transaction state:** trong một collaborator được gọi từ service, kiểm tra `TransactionSynchronizationManager.isActualTransactionActive()` hoặc ghi nhận transaction state. Cách này hữu ích khi muốn xác nhận lời gọi đang nằm trong transaction, nhưng nó không chứng minh dữ liệu thực sự rollback trên resource.

**Quan sát kết quả trên database:** ghi dữ liệu rồi ném exception, sau khi proxy kết thúc lời gọi, truy vấn lại database và xác nhận dữ liệu không tồn tại. Cách này kiểm tra cả transaction interceptor, transaction manager, DataSource và cách repository tham gia transaction.

Với hành vi transaction quan trọng, kiểm tra trên database thường cung cấp bằng chứng mạnh hơn. Dùng transaction manager thật của loại persistence đang chạy, chẳng hạn `DataSourceTransactionManager` cho JDBC hoặc `JpaTransactionManager` cho JPA. Không thay bằng mock transaction manager nếu mục tiêu là chứng minh commit/rollback của resource.

## 16. Những lỗi thường gặp khi kiểm thử bean và proxy

### Tạo service bằng `new`

Object tự tạo không được Spring bọc proxy. Annotation vẫn nằm trên class nhưng interceptor không được gọi. Inject bean từ context.

### Chỉ assert bean tồn tại

Bean có thể tồn tại nhưng sai implementation hoặc thiếu proxy. Kiểm tra qualifier/profile/property và hành vi quan sát được.

### Chỉ assert proxy tồn tại

Proxy có thể được tạo nhưng interceptor hoặc transaction manager cấu hình sai. Kiểm tra kết quả commit/rollback hoặc hiệu ứng của annotation.

### Test gọi method nội bộ

Self-invocation bỏ qua proxy. Gọi entry point công khai qua bean được inject hoặc tách collaborator thành bean riêng.

### Test method cũng được đánh dấu `@Transactional`

Transaction của service có thể tham gia transaction ngoài của test, làm assertion kiểm tra rollback trước khi rollback thật xảy ra. Dùng test không có transaction ngoài cho ví dụ rollback hoặc kết thúc transaction rõ ràng trước assertion.

### Ném checked exception nhưng mong rollback mặc định

Spring mặc định rollback với unchecked exception và `Error`. Nếu cần rollback với checked exception, cấu hình `rollbackFor` và kiểm tra bằng test.

### Dùng final/private method cho annotation proxy-based

Proxy subclass không thể override final class/method; private method không được intercept. Đặt annotation trên method phù hợp với proxy model và gọi từ bên ngoài bean.

### Dùng sai transaction manager hoặc DataSource

Nếu repository và transaction manager không dùng cùng resource, transaction có thể không bao quanh thao tác cần kiểm tra. Xác nhận wiring và qualifier của cả hai.

### Dọn database không đúng thời điểm

Nếu test chạy song song hoặc context dùng chung, dữ liệu có thể ảnh hưởng test khác. Dùng id duy nhất, cleanup theo fixture hoặc database riêng; không dựa vào thứ tự test.

## 17. Tổ chức test theo phạm vi

Không cần một bài test lớn để xác nhận tất cả cấu hình Spring. Có thể chia thành các nhóm:

| Nhóm test | Mục tiêu | Cấu hình phù hợp |
|---|---|---|
| Bean configuration test | Bean có mặt, qualifier/profile/condition chọn đúng implementation | `@SpringJUnitConfig` hoặc `ApplicationContextRunner`. |
| Proxy behavior test | Interceptor thực sự áp dụng khi gọi bean | Spring context thật và collaborator/resource có thể quan sát. |
| Persistence integration test | Transaction và repository cùng hoạt động trên database | Embedded DB hoặc Testcontainers với transaction manager thật. |
| Application context test | Component scan, auto-configuration và profile của ứng dụng | `@SpringBootTest` với property/profile cần thiết. |

Tách test giúp lỗi dễ định vị. Nếu bean selection sai, test configuration sẽ chỉ ra vấn đề. Nếu proxy tồn tại nhưng rollback không hoạt động, proxy behavior test sẽ thất bại tại assertion database.

## 18. Checklist cho bài kiểm thử cấu hình bean và proxy

- [ ] Test nạp đúng cấu hình Spring cần kiểm tra.
- [ ] Bean được lấy từ `ApplicationContext` hoặc inject bởi Spring, không tự `new` target cần proxy.
- [ ] Có xác nhận bean type, qualifier, primary, profile hoặc property theo hợp đồng cấu hình.
- [ ] Infrastructure liên quan được đăng ký đầy đủ, ví dụ transaction manager và DataSource.
- [ ] Hành vi proxy được gọi từ một entry point bên ngoài proxy.
- [ ] Có assertion hiệu ứng thực tế của interceptor, không chỉ kiểm tra annotation hoặc proxy class.
- [ ] Với transaction, test quan sát commit/rollback trên resource phù hợp.
- [ ] Test không vô tình mở transaction ngoài làm sai thời điểm assertion.
- [ ] Đã xét self-invocation, method visibility và final modifier.
- [ ] Mock chỉ thay collaborator không thuộc mục tiêu kiểm thử.
- [ ] Test dọn dữ liệu và cache để không rò trạng thái giữa các lần chạy.

Kiểm thử cấu hình bean xác nhận Spring dựng đúng đồ thị dependency; kiểm thử proxy xác nhận lời gọi thực sự đi qua interceptor mà ứng dụng dựa vào. Khi kết hợp context test với một hành vi có thể quan sát như transaction rollback, ta có bằng chứng rằng bean không chỉ được đăng ký đúng mà còn hoạt động đúng trong cơ chế runtime của Spring.
