# @SpringJUnitConfig và cấu hình rút gọn

Spring TestContext Framework cung cấp cơ chế nạp và quản lý ApplicationContext cho các bài kiểm thử. Khi dùng JUnit Jupiter, một bài test có thể cần Spring tạo bean, inject phụ thuộc vào test class, quản lý vòng đời context và kích hoạt các khả năng kiểm thử như transaction. Nếu mỗi test phải khai báo riêng extension của JUnit và cấu hình context, phần thiết lập sẽ dài và dễ lặp lại.

**@SpringJUnitConfig** là annotation kết hợp hai thành phần thường dùng: **@ExtendWith(SpringExtension.class)** để tích hợp Spring TestContext với JUnit Jupiter và **@ContextConfiguration** để chỉ định cấu hình dùng tạo ApplicationContext. Nhờ vậy, test có thể khai báo cấu hình Spring bằng một annotation ngắn gọn.

Bài học này tập trung vào cách sử dụng **@SpringJUnitConfig**, cách tổ chức cấu hình rút gọn bằng Java hoặc XML, cách chọn bean cần nạp cho test và những điểm cần hiểu về context cache, dependency injection và các annotation bổ trợ.

## 1. @SpringJUnitConfig là gì?

Trong JUnit Jupiter, Spring cần một extension để kết nối vòng đời test với TestContext Framework. Extension này là **SpringExtension**. Cấu hình context thường được khai báo bằng **@ContextConfiguration**.

Nếu viết tường minh, một test class có thể trông như sau:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTest {
    // Test methods
}
~~~

Khi sử dụng **@SpringJUnitConfig**, hai annotation trên được kết hợp:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
    // Test methods
}
~~~

Hai cách khai báo thể hiện cùng mục tiêu: SpringExtension tham gia vào JUnit Jupiter và Spring TestContext nạp cấu hình được chỉ định để tạo ApplicationContext.

**@SpringJUnitConfig** là một composed annotation, được cung cấp trong package:

~~~java
org.springframework.test.context.junit.jupiter.SpringJUnitConfig
~~~

Các annotation liên quan nằm trong những package sau:

- **SpringJUnitConfig** và **SpringExtension** thuộc package JUnit Jupiter của Spring TestContext.
- **ContextConfiguration** thuộc package Spring TestContext.
- **Configuration**, **Bean**, **Import** và **ComponentScan** thuộc Spring Framework Core/Context.

### Vai trò của hai thành phần được kết hợp

| Thành phần | Trách nhiệm |
|---|---|
| SpringExtension | Kết nối JUnit Jupiter với Spring TestContext, tham gia các callback và hỗ trợ injection cho test |
| ContextConfiguration | Khai báo nguồn cấu hình để tạo ApplicationContext |
| SpringJUnitConfig | Kết hợp hai thành phần trên trong một annotation |

SpringExtension không phải một Spring bean và cũng không thay thế ApplicationContext. Nó đóng vai trò cầu nối giữa JUnit và cơ chế kiểm thử của Spring.

## 2. Cấu hình Java tối thiểu

Cách phổ biến nhất là tạo một class cấu hình bằng **@Configuration** và khai báo các bean mà test cần.

Giả sử ứng dụng có một service nhận repository và clock qua constructor:

~~~java
public class OrderService {

    private final OrderRepository repository;
    private final Clock clock;

    public OrderService(OrderRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Order create(String customerId) {
        var order = new Order(customerId, clock.instant());
        repository.save(order);
        return order;
    }
}
~~~

Test không cần nạp toàn bộ ứng dụng. Ta có thể khai báo một cấu hình nhỏ:

~~~java
@Configuration
class OrderTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-04-12T10:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock testClock) {
        return new OrderService(repository, testClock);
    }
}
~~~

Cấu hình này tạo ba bean:

- Repository trong bộ nhớ để test không cần database.
- Clock cố định để kết quả thời gian có thể dự đoán.
- OrderService sử dụng hai bean trên qua constructor injection.

Test class chỉ cần khai báo:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpringTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderWithConfiguredClock() {
        Order order = orderService.create("customer-18");

        assertEquals("customer-18", order.customerId());
        assertEquals(
                Instant.parse("2026-04-12T10:00:00Z"),
                order.createdAt()
        );
    }
}
~~~

Khi chạy test, Spring tạo ApplicationContext từ OrderTestConfig, khởi tạo các bean và inject OrderService vào trường được đánh dấu **@Autowired**.

Ví dụ này vẫn sử dụng implementation thật của OrderService. Repository là fake trong bộ nhớ và Clock là đối tượng thật được cấu hình với thời điểm cố định. Test kiểm tra việc tạo bean, constructor injection và hành vi của service trong context Spring.

## 3. Khai báo class cấu hình bằng nhiều cách

**@SpringJUnitConfig** hỗ trợ các nguồn cấu hình mà **@ContextConfiguration** cung cấp. Cách chọn nguồn phụ thuộc vào loại ứng dụng và cấu hình sẵn có.

### Truyền class cấu hình trực tiếp

Có thể truyền class cấu hình làm tham số:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
}
~~~

Đây là dạng ngắn gọn khi chỉ có một hoặc một vài class cấu hình.

### Dùng thuộc tính classes

Nếu muốn diễn đạt rõ thuộc tính, có thể viết:

~~~java
@SpringJUnitConfig(classes = {
        OrderTestConfig.class,
        AuditTestConfig.class
})
class OrderServiceTest {
}
~~~

Nhiều class cấu hình có thể được nạp cùng lúc. Spring xử lý các bean definition từ những nguồn cấu hình này trong cùng context, theo các quy tắc đăng ký bean của container.

### Dùng XML configuration

Với ứng dụng vẫn sử dụng XML, có thể khai báo đường dẫn tài nguyên:

~~~java
@SpringJUnitConfig(locations = "classpath:order-test-context.xml")
class OrderServiceXmlTest {
}
~~~

Ví dụ XML:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository"
          class="example.testing.InMemoryOrderRepository"/>

    <bean id="orderService"
          class="example.order.OrderService">
        <constructor-arg ref="orderRepository"/>
    </bean>
</beans>
~~~

Đường dẫn classpath phải trỏ đến tài nguyên có trong test runtime. Nếu file XML nằm trong thư mục test resources, build tool cần đưa thư mục đó vào classpath khi chạy test.

### Kết hợp Java và XML

Một ứng dụng chuyển đổi dần từ XML sang Java configuration có thể nạp cả hai nguồn:

~~~java
@SpringJUnitConfig(
        locations = "classpath:legacy-order-context.xml",
        classes = OrderTestConfig.class
)
class OrderMigrationTest {
}
~~~

Chỉ nên kết hợp khi các nguồn cấu hình thực sự cần thiết. Nhiều nguồn cấu hình có thể làm việc tìm bean và xử lý xung đột tên bean khó hiểu hơn.

## 4. Dùng cấu hình lồng bên trong test class

Với test chỉ cần một cấu hình nhỏ, có thể khai báo một static nested class được đánh dấu **@Configuration** ngay bên trong test class.

~~~java
@SpringJUnitConfig
class TaxServiceTest {

    @Autowired
    private TaxService taxService;

    @Configuration
    static class TestConfig {

        @Bean
        TaxService taxService() {
            return new TaxService(new BigDecimal("0.10"));
        }
    }

    @Test
    void calculatesTaxForKnownRate() {
        BigDecimal tax = taxService.calculate(new BigDecimal("100000"));

        assertEquals(
                0,
                tax.compareTo(new BigDecimal("10000"))
        );
    }
}
~~~

Khi không chỉ định class hoặc resource cấu hình, Spring TestContext có thể tìm một static nested class được đánh dấu **@Configuration** để dùng làm cấu hình mặc định.

Cách này có một số lợi ích:

- Cấu hình chỉ dùng cho một test nằm ngay cạnh test đó.
- Không cần tạo thêm file cấu hình nếu phần thiết lập rất nhỏ.
- Người đọc dễ nhận ra các bean đặc biệt dành riêng cho kịch bản test.

Nếu nhiều test cần dùng chung cấu hình, hãy chuyển cấu hình ra một class riêng. Cấu hình lồng cũng cần là static để Spring có thể khởi tạo độc lập với instance của test class.

## 5. Cấu hình rút gọn bằng @Import

Không phải lúc nào cũng cần khai báo lại từng bean production. Nếu ứng dụng đã có các class cấu hình hoặc component phù hợp, test có thể import chúng vào một cấu hình nhỏ.

~~~java
@Configuration
@Import(OrderService.class)
class OrderServiceTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-04-12T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

**@Import** đưa class được chỉ định vào quá trình cấu hình context. Trong ví dụ, OrderService được đăng ký như một bean component và các dependency constructor của nó được phân giải từ những bean trong context.

Nếu dự án có một class cấu hình production:

~~~java
@Configuration
class OrderModuleConfig {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

Test có thể import cấu hình này:

~~~java
@Configuration
@Import(OrderModuleConfig.class)
class OrderModuleTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}

@SpringJUnitConfig(OrderModuleTestConfig.class)
class OrderModuleTest {

    @Autowired
    private OrderService orderService;
}
~~~

OrderModuleTestConfig import cấu hình production và bổ sung các bean mà OrderModuleConfig yêu cầu, chẳng hạn OrderRepository và Clock. Nhờ đó, test có thể dùng wiring của module trong khi thay repository bằng implementation phù hợp với môi trường kiểm thử.

**@Import** giúp chọn một tập cấu hình cụ thể. Nó không tự động bật component scan cho toàn bộ package. Nếu muốn tìm các component theo package, hãy khai báo **@ComponentScan** trong class cấu hình.

## 6. Khi nào dùng @ComponentScan?

**@ComponentScan** yêu cầu Spring quét package để tìm các component được đánh dấu như **@Component**, **@Service**, **@Repository** hoặc **@Controller**.

Ví dụ:

~~~java
@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
class OrderComponentTestConfig {
}
~~~

Dùng class marker như OrderService.class giúp tránh hard-code tên package dưới dạng chuỗi và giảm nguy cơ đổi package nhưng quên sửa cấu hình.

Tuy nhiên, quét toàn bộ package có thể đưa nhiều bean vào context hơn mức test cần. Các bean đó có thể kéo theo database, HTTP client, message broker hoặc cấu hình bảo mật. Khi mục tiêu là kiểm tra một service, cấu hình tường minh bằng **@Import** hoặc các phương thức **@Bean** thường dễ kiểm soát hơn.

Hãy chọn phạm vi scan đủ nhỏ. Nếu cần loại trừ hoặc chỉ định một nhóm component, có thể cấu hình filter cho component scan. Không nên dùng component scan như cách mặc định cho mọi test chỉ vì nó ít dòng cấu hình hơn.

## 7. Spring inject phụ thuộc vào test class như thế nào?

Khi **SpringExtension** quản lý test, Spring TestContext có thể thực hiện dependency injection cho test instance. Điều này cho phép test nhận bean qua field hoặc setter được đánh dấu **@Autowired**.

Ví dụ dùng field injection:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository repository;

    @Test
    void createsOrder() {
        Order order = orderService.create("customer-18");

        assertNotNull(order);
        assertTrue(repository.findById(order.id()).isPresent());
    }
}
~~~

Có thể dùng constructor injection cho test class nếu cấu hình JUnit Jupiter và Spring TestContext cho phép autowire constructor. Một cách khai báo tường minh là:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceConstructorTest {

    private final OrderService orderService;

    OrderServiceConstructorTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        assertNotNull(orderService);
    }
}
~~~

Với constructor injection, tất cả tham số constructor được Spring phân giải từ ApplicationContext khi chế độ autowire được bật. Hãy bảo đảm phiên bản Spring TestContext và cấu hình JUnit Jupiter của dự án hỗ trợ cách sử dụng này.

Không nên nhầm injection vào test instance với injection giữa các bean production. **@Autowired** trên test field do Spring TestContext xử lý; còn constructor injection của OrderService được Spring container thực hiện khi tạo bean.

## 8. SpringExtension và vòng đời JUnit Jupiter

SpringExtension kết nối TestContext Framework với các callback của JUnit Jupiter. Nhờ đó, Spring có thể chuẩn bị test instance, inject dependency và thực hiện các hành động kiểm thử theo cấu hình TestContext.

Một số khả năng đáng chú ý:

- Chuẩn bị và inject bean vào test instance.
- Quản lý context thông qua TestContext Framework.
- Tích hợp các TestExecutionListener mặc định để hỗ trợ những chức năng như transaction test khi được cấu hình.
- Cho phép sử dụng các annotation Spring Test như **@DirtiesContext**, **@ActiveProfiles**, **@TestPropertySource** và **@Transactional** trong phạm vi tương ứng.

Ví dụ, nếu test cần một transaction được quản lý bởi Spring:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderTransactionTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesOrderInsideTestTransaction() {
        repository.save(new OrderEntity("order-25", "customer-9"));

        assertTrue(repository.findById("order-25").isPresent());
    }
}
~~~

Khi có transaction manager phù hợp và test được chạy với transaction support của Spring TestContext, test-managed transaction thường được rollback sau mỗi test method. Điều này giúp cô lập thay đổi dữ liệu trong nhiều bài kiểm thử persistence.

Không nên mặc định rằng mọi side effect đều được rollback. Message đã gửi ra broker, HTTP request đã gửi đến dịch vụ ngoài, thao tác ở thread khác hoặc transaction độc lập có thể tồn tại sau test. Hãy xác định rõ ranh giới transaction và cách dọn dữ liệu của từng phụ thuộc.

## 9. Cấu hình profile và thuộc tính dành cho test

Một context có thể cần profile hoặc property khác với môi trường chạy ứng dụng.

### Dùng @ActiveProfiles

**@ActiveProfiles** kích hoạt một hoặc nhiều profile khi Spring tạo context cho test:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@ActiveProfiles("test")
class OrderProfileTest {
}
~~~

Các bean được khai báo với **@Profile("test")** có thể được đăng ký khi profile tương ứng đang hoạt động.

### Dùng @TestPropertySource

**@TestPropertySource** thêm property source cho môi trường test:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(properties = {
        "orders.currency=VND",
        "orders.shipping.enabled=true"
})
class OrderPropertiesTest {
}
~~~

Có thể đọc các thuộc tính này qua **Environment**, **@Value** hoặc cơ chế cấu hình phù hợp trong bean.

Nếu dùng file property riêng, có thể chỉ định location:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(locations = "classpath:order-test.properties")
class OrderPropertiesFileTest {
}
~~~

Hãy dùng thuộc tính test để làm rõ những khác biệt có chủ đích như endpoint giả lập, feature flag hoặc cấu hình thời gian chờ. Không nên đưa thông tin bí mật hoặc thông tin xác thực production vào test resources.

### Dùng @DynamicPropertySource khi giá trị chỉ có lúc chạy

Với tài nguyên được khởi chạy động, chẳng hạn database container, **@DynamicPropertySource** cho phép đăng ký property từ giá trị chỉ biết được trong lúc test chạy.

~~~java
@SpringJUnitConfig(DatabaseTestConfig.class)
class DatabaseContextTest {

    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Ví dụ minh họa cách đăng ký thuộc tính động; dự án thực tế cần dependency Testcontainers, PostgreSQL JDBC driver và quản lý vòng đời container phù hợp. Với container, nên bảo đảm container được dừng sau khi test kết thúc hoặc dùng cơ chế quản lý vòng đời mà thư viện cung cấp.

## 10. Spring TestContext cache và cấu hình nhất quán

Việc tạo ApplicationContext có thể tốn thời gian vì Spring cần đọc cấu hình, đăng ký bean, thực hiện component scan, tạo đối tượng và chạy các bước khởi tạo. Spring TestContext có cơ chế cache context để các test có cấu hình tương thích có thể dùng lại context đã tạo.

Ví dụ, nhiều test cùng khai báo:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
}

@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepositoryCollaboratorTest {
}
~~~

Nếu các thuộc tính cấu hình context tương thích, Spring có thể tái sử dụng context đã được tạo. Điều này giảm chi phí khởi động giữa các test class.

Các yếu tố cấu hình như class hoặc resource, initializer, active profile, property source và customizer có thể ảnh hưởng đến khóa cache. Nếu mỗi test tạo một biến thể cấu hình khác nhau, khả năng tái sử dụng giảm xuống.

### Tránh làm bẩn context

Spring singleton bean được dùng chung trong một ApplicationContext. Nếu test sửa trạng thái mutable bên trong singleton và không khôi phục, test khác dùng cùng context có thể nhận trạng thái còn sót lại.

Một số cách hạn chế:

- Giữ bean dùng chung stateless khi có thể.
- Tạo dữ liệu test riêng cho từng phương thức.
- Reset trạng thái của fake hoặc collaborator sau test nếu cần.
- Tránh thay đổi trực tiếp cấu hình hoặc registry của context trong test.
- Chỉ dùng **@DirtiesContext** khi test thật sự làm thay đổi trạng thái context và cần loại context đó khỏi cache.

**@DirtiesContext** có thể khiến Spring đóng context hiện tại và tạo lại ở lần cần dùng tiếp theo. Dùng annotation này quá thường xuyên sẽ làm test suite chậm hơn đáng kể. Nó không phải cơ chế dọn dữ liệu database tổng quát và cũng không tự thu hồi side effect bên ngoài context.

## 11. Chọn cấu hình rút gọn hay nạp toàn bộ ứng dụng?

**@SpringJUnitConfig** cho phép chỉ định cấu hình Spring cần thiết. Đây là điểm khác biệt quan trọng so với việc luôn nạp toàn bộ ứng dụng.

| Cách tiếp cận | Phạm vi | Phù hợp khi |
|---|---|---|
| @SpringJUnitConfig với cấu hình nhỏ | Một nhóm bean được chọn | Kiểm tra wiring và hành vi của module |
| @SpringJUnitConfig với component scan | Các component trong package được quét | Package có ranh giới rõ và cần nhiều component thật |
| @SpringJUnitConfig với cấu hình XML | Bean từ tài nguyên XML | Ứng dụng hoặc module còn dùng XML |
| @SpringBootTest | Cấu hình ứng dụng Spring Boot rộng hơn | Cần xác minh bootstrap và tích hợp của ứng dụng Boot |
| @WebMvcTest hoặc @DataJpaTest | Lát cắt theo loại kiểm thử của Spring Boot | Kiểm tra một phần web hoặc persistence |

**@SpringJUnitConfig** thuộc Spring TestContext Framework. Nó không tự bật Spring Boot auto-configuration, không tự chạy component scan cho toàn bộ ứng dụng và không tự tạo môi trường web của Spring Boot.

Nếu test cần hành vi bootstrap đặc thù của Spring Boot như auto-configuration, cấu hình theo application properties hoặc các thành phần được Boot tự động đăng ký, hãy cân nhắc **@SpringBootTest** hoặc annotation slice phù hợp. Có thể sử dụng cấu hình Java của ứng dụng Boot trong Spring TestContext, nhưng việc nạp một class cấu hình đơn lẻ không tương đương với quá trình bootstrap đầy đủ của Boot.

### Ví dụ chọn phạm vi

- Test constructor injection và một service: cấu hình nhỏ với **@SpringJUnitConfig**.
- Test controller mapping và validation trong ứng dụng Boot: **@WebMvcTest** thường phù hợp hơn.
- Test repository với cấu hình JPA của Boot: **@DataJpaTest** có thể cung cấp lát cắt thích hợp.
- Test nhiều module, auto-configuration và cấu hình triển khai: cân nhắc **@SpringBootTest**.

Chọn phạm vi dựa trên điều cần chứng minh. Nạp nhiều bean hơn không tự động làm test tốt hơn; nó làm tăng thời gian khởi tạo và số nguyên nhân có thể khiến test thất bại.

## 12. Các lỗi cấu hình thường gặp

### Thiếu bean cần inject

Nếu test yêu cầu **@Autowired OrderService** nhưng context không có bean tương ứng, Spring sẽ báo lỗi khi tạo test instance hoặc khởi tạo context.

Cách xử lý là đăng ký bean bằng **@Bean**, import class phù hợp bằng **@Import**, hoặc cấu hình component scan có phạm vi đúng. Không nên thêm scan toàn bộ ứng dụng chỉ để che lỗi thiếu một bean.

### Component scan quá rộng

Một test service nhỏ có thể vô tình nạp database, HTTP client hoặc broker do scan toàn package. Hãy dùng cấu hình tường minh hoặc giới hạn scan theo package marker và filter.

### Nhầm @SpringJUnitConfig với @SpringBootTest

**@SpringJUnitConfig** không tự chạy Spring Boot auto-configuration. Nếu test dựa vào datasource, configuration properties hoặc auto-configured client do Boot tạo, hãy dùng cấu hình Boot thích hợp hoặc khai báo rõ bean cần thiết.

### Khai báo SpringExtension hai lần

**@SpringJUnitConfig** đã bao gồm **@ExtendWith(SpringExtension.class)**. Không cần lặp lại annotation extension trên cùng test class nếu không có lý do đặc biệt.

### Dùng cấu hình không tương thích giữa các test

Các test dùng profile, property source hoặc bean override khác nhau có thể tạo nhiều context cache entry. Hãy chia sẻ cấu hình khi các test thực sự có cùng yêu cầu và chỉ tạo biến thể khi cần.

### Để trạng thái singleton tồn tại giữa các test

Một bean mutable hoặc fake dùng chung trong context có thể giữ dữ liệu từ test trước. Hãy cô lập dữ liệu, reset trạng thái có chủ đích hoặc tạo context riêng khi cần thiết.

### Dùng @DirtiesContext như cách dọn mọi thứ

Annotation này quản lý vòng đời ApplicationContext. Nó không thay thế transaction rollback, xóa dữ liệu database, dừng container hoặc thu hồi request đã gửi ra ngoài.

## 13. Quy trình tạo một test class với @SpringJUnitConfig

Khi bắt đầu một bài test mới, có thể thực hiện theo trình tự sau:

1. Xác định lớp hoặc module cần kiểm tra và các bean thực sự cần có.
2. Chọn cấu hình Java, XML hoặc nested configuration.
3. Đăng ký production bean cần kiểm tra và thay thế phụ thuộc bên ngoài bằng fake/stub khi mục tiêu test cho phép.
4. Dùng **@SpringJUnitConfig** để nạp cấu hình và tích hợp SpringExtension với JUnit Jupiter.
5. Inject bean cần kiểm tra vào test class.
6. Viết test theo hành vi quan sát được, sử dụng dữ liệu độc lập và có thể tái tạo.
7. Xem xét transaction, profile, property và context cache nếu test cần những tính năng đó.
8. Chỉ mở rộng phạm vi context khi test cần xác minh thêm một ranh giới tích hợp.

Ví dụ tổng hợp:

~~~java
@Configuration
class InventoryTestConfig {

    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-05-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository repository,
            Clock clock) {
        return new InventoryService(repository, clock);
    }
}
~~~

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {

    @Autowired
    private InventoryService inventoryService;

    @Test
    void recordsStockWithDeterministicTime() {
        StockRecord record =
                inventoryService.receive("SKU-100", 12);

        assertEquals("SKU-100", record.sku());
        assertEquals(12, record.quantity());
        assertEquals(
                Instant.parse("2026-05-01T00:00:00Z"),
                record.receivedAt()
        );
    }
}
~~~

Test này dùng Spring để tạo InventoryService và inject các phụ thuộc. Repository trong bộ nhớ giúp test chạy không cần database; Clock cố định làm thời gian có thể dự đoán. Nếu mục tiêu chuyển sang xác minh mapping JPA, transaction hoặc SQL, hãy bổ sung một test dùng repository thật và database kiểm thử.

## 14. Checklist khi dùng @SpringJUnitConfig

Trước khi hoàn tất cấu hình, hãy tự xác nhận:

- Test dùng JUnit Jupiter và có SpringExtension thông qua **@SpringJUnitConfig**.
- Cấu hình class hoặc resource được chỉ định đúng.
- Context chỉ chứa những bean cần thiết cho mục tiêu test.
- Các phụ thuộc của bean được đăng ký đầy đủ.
- Component scan có phạm vi có chủ đích.
- Profile và property source phản ánh đúng kịch bản test.
- Test data và trạng thái singleton được cô lập.
- Transaction rollback chỉ được kỳ vọng ở phạm vi mà Spring quản lý.
- Cấu hình tương thích giữa các test để tận dụng context cache.
- Nếu cần Boot auto-configuration hoặc một lát cắt chuyên biệt, đã chọn cơ chế bootstrap tương ứng.

**@SpringJUnitConfig** giúp rút gọn phần khai báo bằng cách kết hợp SpringExtension và ContextConfiguration. Giá trị chính của nó nằm ở việc tạo một ApplicationContext Spring có phạm vi rõ ràng cho JUnit Jupiter. Khi kết hợp cấu hình Java hoặc XML nhỏ, import có chọn lọc, dependency injection và các annotation bổ trợ, test có thể kiểm tra đúng module cần thiết mà vẫn tận dụng được TestContext Framework.

