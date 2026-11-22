# Đóng gói SpringExtension và cấu hình context chung

Nhiều test trong một dự án Spring thường lặp lại cùng một nhóm annotation: kết nối JUnit Jupiter với Spring, nạp một bộ cấu hình dùng chung, bật profile kiểm thử, khai báo property và gắn tag cho pipeline. Nếu mỗi test class tự khai báo toàn bộ cấu hình đó, các thay đổi về môi trường hoặc cách khởi tạo context phải được sửa ở nhiều nơi. Một test có thể vô tình thiếu `SpringExtension`, dùng sai profile hoặc nạp một tập bean khác với các test còn lại.

Spring cho phép đóng gói các annotation thành **composed annotation** để tái sử dụng. Với JUnit Jupiter, annotation có sẵn `@SpringJUnitConfig` đã kết hợp `SpringExtension` và `@ContextConfiguration`. Khi dự án cần một quy ước riêng, có thể tạo annotation mới đặt các annotation Spring ở dạng meta-annotation, sau đó dùng `@AliasFor` để mở những thuộc tính mà từng test cần thay đổi.

Mục tiêu là tạo một cấu hình chung dễ đọc, có thể mở rộng và vẫn giữ được khả năng tùy chỉnh của từng test class. Bài học này tập trung vào việc đóng gói `SpringExtension`, cấu hình context, profile, property, tag và cách tái sử dụng cấu hình mà không làm mất khả năng cache `ApplicationContext`.

## 1. Vì sao cần đóng gói annotation?

Một test Spring cơ bản có thể cần nhiều annotation:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:/order-test.properties")
@Tag("integration")
class OrderServiceIntegrationTest {
    // ...
}
```

Nếu nhiều class cùng dùng cấu hình này, phần khai báo bị lặp lại. Khi profile đổi tên, property file được thay hoặc cấu hình context được tách module, nhóm phải cập nhật từng class. Việc lặp annotation cũng khiến test dễ lệch nhau: một class có `@ActiveProfiles("test")`, class khác quên profile và vô tình đọc cấu hình mặc định.

Composed annotation gom các metadata liên quan thành một annotation có ý nghĩa ở cấp dự án:

```java
@OrderIntegrationTest(classes = OrderTestConfig.class)
class OrderServiceIntegrationTest {
    // ...
}
```

Người đọc nhận ra ngay nhóm test đang dùng cấu hình tích hợp chung. Khi cần, annotation có thể mở một số thuộc tính như danh sách cấu hình hoặc property riêng cho test class.

Đóng gói annotation phù hợp khi nhiều test có cùng một chính sách. Không cần tạo annotation riêng chỉ để thay một annotation đơn giản xuất hiện ở một hoặc hai nơi. Hãy chọn một nhóm cấu hình có ý nghĩa ổn định và được nhiều test sử dụng.

## 2. `SpringExtension` làm nhiệm vụ gì?

JUnit Jupiter có extension model để framework bên ngoài tham gia vòng đời test. `SpringExtension` là cầu nối giữa JUnit Jupiter và Spring TestContext Framework.

Khi đăng ký:

```java
@ExtendWith(SpringExtension.class)
class CustomerServiceTest {
}
```

JUnit gọi các callback của `SpringExtension`. Extension chuyển các mốc vòng đời tới `TestContextManager`, nhờ đó Spring có thể:

- Tạo hoặc lấy `ApplicationContext` từ context cache.
- Inject dependency vào test instance qua `@Autowired`.
- Chuẩn bị transaction kiểm thử khi test dùng `@Transactional`.
- Xử lý các annotation như `@Sql`, `@DirtiesContext` và `@ActiveProfiles`.
- Hỗ trợ lấy tham số từ Spring context trong các lifecycle method hoặc test method khi phù hợp.

`SpringExtension` không tự xác định toàn bộ bean của ứng dụng. Cấu hình context vẫn cần được cung cấp qua `@ContextConfiguration`, `@SpringBootTest`, test slice hoặc cơ chế bootstrap tương ứng.

## 3. Dùng trực tiếp `@ExtendWith` và `@ContextConfiguration`

Trong Spring Framework thuần, cách khai báo rõ ràng là kết hợp hai annotation:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`@ExtendWith(SpringExtension.class)` bật tích hợp JUnit Jupiter. `@ContextConfiguration` chỉ ra cấu hình dùng để xây dựng `ApplicationContext`, ví dụ Java configuration class, XML resource hoặc initializer.

Với cấu hình Java:

```java
@Configuration
@ComponentScan(basePackageClasses = CustomerService.class)
class TestConfig {
}
```

Với XML:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/spring/customer-test-context.xml")
class CustomerServiceXmlTest {
}
```

`@ContextConfiguration` có thể nhận cả `classes` và `locations` nếu context cần phối hợp Java configuration với XML. Không nên khai báo nhiều nguồn cấu hình giống nhau ở cả class và superclass nếu không hiểu cách Spring hợp nhất metadata.

## 4. `@SpringJUnitConfig` là composed annotation có sẵn

Spring cung cấp `@SpringJUnitConfig` trong package `org.springframework.test.context.junit.jupiter`. Annotation này kết hợp:

- `@ExtendWith(SpringExtension.class)` để tích hợp JUnit Jupiter.
- `@ContextConfiguration` để chỉ định cách tạo Spring `ApplicationContext`.

Vì vậy, có thể viết ngắn gọn:

```java
@SpringJUnitConfig(classes = CustomerTestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`@SpringJUnitConfig` cung cấp các thuộc tính `classes` và `locations` làm alias cho thuộc tính tương ứng của `@ContextConfiguration`.

Ví dụ nạp Java config và XML cùng lúc:

```java
@SpringJUnitConfig(
    classes = CustomerTestConfig.class,
    locations = "classpath:/spring/legacy-customer-beans.xml"
)
class CustomerMigrationTest {
}
```

Nếu chỉ cần `SpringExtension` cộng với `@ContextConfiguration`, hãy ưu tiên `@SpringJUnitConfig`. Annotation này đã thể hiện đúng ý định và không cần tự viết một composed annotation mới.

## 5. Spring Boot test annotations đã tích hợp SpringExtension

Trong Spring Boot, các annotation kiểm thử phổ biến đã kết nối với Spring Test. Ví dụ:

- `@SpringBootTest` khởi tạo context theo cơ chế bootstrap của Spring Boot.
- `@WebMvcTest` tạo web slice để kiểm tra MVC.
- `@DataJpaTest` tạo JPA slice để kiểm tra persistence.
- Các slice khác như `@JsonTest` hoặc `@RestClientTest` cũng tích hợp Spring Test theo mục đích riêng.

Do đó, test dùng các annotation này thường không cần thêm `@ExtendWith(SpringExtension.class)` hoặc `@SpringJUnitConfig` lần nữa.

Ví dụ:

```java
@SpringBootTest
class ApplicationIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void startsApplicationContext() {
        assertNotNull(context);
    }
}
```

`@SpringBootTest` đã cung cấp bootstrapper và extension phù hợp. Nếu thêm `@SpringJUnitConfig` lên cùng class, ta có thể tạo ra hai bộ metadata về context không cần thiết hoặc xung đột với cách Spring Boot chọn cấu hình. Hãy chọn annotation bootstrap phù hợp với loại test.

## 6. Composed annotation là gì?

Một annotation có thể được đặt trên định nghĩa annotation khác. Annotation bên trong được gọi là meta-annotation. Spring đọc metadata này bằng cơ chế merged annotations để tìm các annotation trực tiếp và gián tiếp trên test class.

Ví dụ, một annotation tùy chỉnh có thể chứa `@SpringJUnitConfig`, `@ActiveProfiles` và `@Tag`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface IntegrationSpringTest {
}
```

Sau đó test class chỉ cần:

```java
@IntegrationSpringTest
class OrderServiceIntegrationTest {
}
```

Annotation này đóng gói một chính sách: dùng SpringExtension, tạo context theo Spring Test, bật profile `integration` và gắn JUnit tag `integration`.

Để annotation hoạt động đúng trong runtime, cần giữ `@Retention(RetentionPolicy.RUNTIME)`. Spring và JUnit phải đọc được metadata khi test được phát hiện và chạy.

## 7. `@AliasFor` mở thuộc tính cấu hình cho từng test class

Một composed annotation thường cần cho phép từng test chỉ định class cấu hình riêng. Spring cung cấp `@AliasFor` để thuộc tính của annotation tùy chỉnh ghi đè thuộc tính của meta-annotation.

Ví dụ:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
public @interface IntegrationSpringTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};
}
```

Sử dụng:

```java
@IntegrationSpringTest(classes = OrderTestConfig.class)
class OrderServiceIntegrationTest {
}
```

Spring chuyển giá trị `classes` của `@IntegrationSpringTest` tới thuộc tính `classes` của `@SpringJUnitConfig`, rồi tới `@ContextConfiguration`. Test class không cần khai báo riêng `@ContextConfiguration`.

`@AliasFor` giúp giữ cấu hình chung trong một annotation nhưng vẫn cho phép test cung cấp phần biến thiên. Nếu không cần thay đổi một thuộc tính, không nhất thiết phải mở nó ra.

## 8. Đóng gói cấu hình context và property thành một annotation dùng lại

Một annotation thực tế có thể gộp SpringExtension, context class, profile và tag. Property source có thể được khai báo riêng trên test class nếu mỗi test cần file hoặc giá trị khác nhau:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface OrderIntegrationTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "locations")
    String[] locations() default {};
}
```

Test class có thể chọn cấu hình cần thiết:

```java
@OrderIntegrationTest(
    classes = {OrderTestConfig.class, SharedTestConfig.class}
)
@TestPropertySource(
    locations = "classpath:/order-test.properties",
    properties = "feature.audit.enabled=false"
)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;
}
```

Trong ví dụ:

- `@SpringJUnitConfig` đóng gói `SpringExtension` và `@ContextConfiguration`.
- `@ActiveProfiles("integration")` bật profile dùng chung.
- `@TestPropertySource` cho phép nạp file và property riêng.
- `@Tag("integration")` cho phép build tool lọc nhóm test.
- `@AliasFor` chuyển các thuộc tính do test class cung cấp tới meta-annotation tương ứng.

Property source được đặt trực tiếp trên test class để annotation chung không ép mọi test dùng cùng một file hoặc cùng một giá trị. Nếu một nhóm thực sự chia sẻ property cố định, có thể thêm `@TestPropertySource` làm meta-annotation không mở alias hoặc tạo một composed annotation chuyên biệt cho nhóm đó.

Đây là ví dụ cấu trúc. Trong dự án thực tế, hãy chỉ đưa những chính sách thật sự dùng chung vào annotation. Nếu mỗi test class có bộ property và context hoàn toàn khác nhau, annotation có thể trở thành một lớp cấu hình khó hiểu.

## 9. Quy tắc quan trọng khi khai báo `@AliasFor`

`@AliasFor` có một số quy tắc cần tuân thủ:

- Annotation tùy chỉnh phải được giữ ở runtime để Spring đọc metadata.
- Meta-annotation được tham chiếu phải thực sự có mặt trong annotation composition.
- Kiểu dữ liệu của thuộc tính alias phải tương thích với thuộc tính đích.
- Khi alias hai thuộc tính trong cùng annotation, chúng phải có kiểu và giá trị mặc định tương thích.
- Với alias ghi đè thuộc tính của meta-annotation, giá trị mặc định cần tuân thủ quy tắc của Spring để merged annotation có thể xác định giá trị nhất quán.
- Không tạo nhiều đường alias chồng chéo khiến một thuộc tính có thể ghi đè nhiều nguồn khác nhau.

Ví dụ đơn giản và an toàn là alias `classes` với default rỗng để tương ứng thuộc tính `classes` của `@SpringJUnitConfig`:

```java
@AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
Class<?>[] classes() default {};
```

Nếu muốn hỗ trợ cả `value` và `classes` như hai tên đồng nghĩa trong annotation tùy chỉnh, cần khai báo alias trong cùng annotation:

```java
@AliasFor("classes")
Class<?>[] value() default {};

@AliasFor("value")
Class<?>[] classes() default {};
```

Không nên thêm cặp alias này nếu nhóm chỉ cần một tên `classes`. Mỗi alias bổ sung là một quy tắc metadata cần duy trì.

Khi Spring báo lỗi về alias, hãy kiểm tra annotation composition, tên thuộc tính, kiểu và default value trước khi thay đổi cách bootstrap context.

## 10. Tái sử dụng cấu hình context bằng class cấu hình chung

Composed annotation quyết định cách test kích hoạt Spring. Còn `@ContextConfiguration` xác định cấu hình context. Để nhiều test dùng cùng một context, nên gom bean dùng chung vào một hoặc một số configuration class.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
@Import({PersistenceTestConfig.class, SharedTestBeans.class})
class SharedIntegrationTestConfig {
}
```

Các test có thể cùng tham chiếu cấu hình này:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
class OrderServiceIntegrationTest {
}

@SpringJUnitConfig(SharedIntegrationTestConfig.class)
class CustomerServiceIntegrationTest {
}
```

Nếu merged context configuration của hai test tương đương, Spring Test có thể tái sử dụng cùng `ApplicationContext` từ cache. Điều này giảm thời gian tạo datasource, service, repository và các singleton bean.

Hãy đặt cấu hình chung ở một module test-support hoặc package test phù hợp. Không đưa bean chỉ phục vụ một test đơn lẻ vào cấu hình chung nếu nó làm thay đổi context của tất cả test khác.

## 11. Tách cấu hình dùng chung và cấu hình riêng của từng test

Một cấu hình test dễ bảo trì thường có hai lớp:

- **Cấu hình chung:** bean nền tảng, profile, datasource test, clock cố định, fake hoặc adapter test được nhiều class sử dụng.
- **Cấu hình riêng:** bean override, property hoặc import chỉ cần cho một nhóm test cụ thể.

Ví dụ cấu hình chung:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
class SharedTestConfig {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Cấu hình riêng cho test thanh toán:

```java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfig {

    @Bean
    PaymentPort paymentPort() {
        return new FakePaymentAdapter();
    }
}
```

Test ghép hai cấu hình:

```java
@SpringJUnitConfig(classes = {
    SharedTestConfig.class,
    PaymentTestConfig.class
})
class PaymentWorkflowTest {
}
```

Với Spring Boot, `@TestConfiguration` được thiết kế cho cấu hình bổ sung trong test. Có thể import bằng `@Import(PaymentTestConfig.class)` hoặc đưa vào danh sách class phù hợp. Nếu dùng Spring Framework thuần, một class `@Configuration` trong test source set cũng có thể làm nhiệm vụ cấu hình test.

## 12. Dùng `@Import` để mở rộng context chung

Khi một test cần thêm module cụ thể, `@Import` giúp ghép cấu hình mà không phải tạo một cấu hình lớn cho tất cả test:

```java
@Configuration(proxyBeanMethods = false)
class MessagingTestConfig {

    @Bean
    OrderEventPort orderEventPort() {
        return new InMemoryOrderEventPort();
    }
}
```

Test cần kiểm tra event:

```java
@SpringJUnitConfig(classes = {
    SharedIntegrationTestConfig.class,
    MessagingTestConfig.class
})
class OrderEventIntegrationTest {
}
```

`@Import` có thể đưa configuration class hoặc component class vào context. Nếu một test cần XML resource, có thể đặt `@ImportResource` trên cấu hình test. Cần giữ nguồn cấu hình rõ ràng để người đọc biết bean đến từ module nào.

Không nên dùng component scan quá rộng chỉ để tìm một bean test. `@Import` class cụ thể giúp phạm vi context rõ ràng hơn và giảm nguy cơ đăng ký nhầm bean.

## 13. Đóng gói Spring Boot test configuration

Nếu dự án chủ yếu dùng Spring Boot, composed annotation có thể dựa trên `@SpringBootTest` thay vì `@SpringJUnitConfig`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("integration")
@Tag("integration")
public @interface IntegrationBootTest {

    @AliasFor(annotation = SpringBootTest.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Sử dụng:

```java
@IntegrationBootTest(
    classes = OrdersApplication.class,
    properties = "feature.external-notifications=false"
)
class OrderApplicationIntegrationTest {
}
```

Annotation này đóng gói `@SpringBootTest`, nên không cần thêm `@SpringExtension` hoặc `@SpringJUnitConfig`. `@SpringBootTest` đã sử dụng Spring Boot test bootstrapper và tích hợp SpringExtension.

Nếu test cần web environment thật, hãy quyết định đó có phải chính sách chung hay chỉ là lựa chọn của một test class. Có thể mở thuộc tính `webEnvironment` qua `@AliasFor` nếu nhóm thực sự cần nhiều chế độ. Đừng cố định `RANDOM_PORT` trong một annotation được dùng cả cho test service không cần server.

## 14. Đóng gói test slice riêng

Các slice có mục tiêu khác nhau. Có thể tạo composed annotation cho một nhóm MVC test:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Tag("web")
public @interface WebLayerTest {

    @AliasFor(annotation = WebMvcTest.class, attribute = "controllers")
    Class<?>[] controllers() default {};
}
```

Sử dụng:

```java
@WebLayerTest(controllers = OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
```

`@WebMvcTest` đã tích hợp Spring Test. Composed annotation chỉ bổ sung profile, tag và một API tên ngắn hơn cho controller list.

Tương tự, có thể tạo annotation cho `@DataJpaTest` hoặc `@JsonTest` nếu nhóm có cấu hình dùng chung thật sự. Không tạo một annotation chung bao gồm nhiều slice loại trừ nhau; một test nên chọn rõ phạm vi cần kiểm tra.

## 15. Dùng `@ActiveProfiles` và property trong cấu hình dùng lại

Profile giúp chọn bean/configuration theo môi trường. Một composed annotation có thể cố định profile chung:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = {
    "feature.notifications.enabled=false",
    "feature.audit.enabled=true"
})
@Tag("integration")
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SharedIntegrationTest {
}
```

Các test dùng annotation sẽ nhận cùng profile và property mặc định. Nếu một test cần property khác, có thể mở thuộc tính qua `@AliasFor` hoặc đặt một composed annotation chuyên biệt cho nhóm đó.

Không nên thêm mọi property test vào annotation chung. Một property liên quan tới một tính năng cụ thể có thể khiến tất cả test dùng annotation nhận cấu hình không cần thiết. Hãy giữ phần chung ở mức thực sự ổn định.

### Property inline và property file

`@TestPropertySource(properties = ...)` phù hợp với một số giá trị nhỏ, rõ ràng. `locations` phù hợp khi có nhiều property hoặc muốn dùng lại file. Có thể cung cấp cả hai; property inline có độ ưu tiên cao hơn property từ resource được nạp bằng cùng annotation.

Khi dùng composed annotation, đặt alias rõ ràng để người dùng phân biệt:

```java
@AliasFor(annotation = TestPropertySource.class, attribute = "locations")
String[] propertyLocations() default {};

@AliasFor(annotation = TestPropertySource.class, attribute = "properties")
String[] properties() default {};
```

## 16. Kế thừa cấu hình qua test superclass

Ngoài composed annotation, Java class inheritance có thể chia sẻ cấu hình giữa nhiều test class:

```java
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractIntegrationTest {

    @Autowired
    protected OrderRepository orderRepository;
}
```

Test con kế thừa:

```java
class OrderRepositoryTest extends AbstractIntegrationTest {

    @Test
    void findsOrderById() {
        // Dùng orderRepository được inject từ context chung
    }
}
```

Spring Test hỗ trợ kế thừa metadata context từ superclass. `@ContextConfiguration` mặc định kế thừa locations/classes và initializers theo các thuộc tính inheritance tương ứng. `@ActiveProfiles` cũng hỗ trợ kế thừa profile theo mặc định.

Tuy nhiên, inheritance làm cấu hình ít hiển thị tại test class. Nếu một test con khai báo cấu hình riêng, cần hiểu cách metadata được hợp nhất và liệu `inheritLocations` hoặc `inheritProfiles` có được bật hay không.

Base class cũng dễ trở thành nơi tập trung quá nhiều dependency và setup. Hãy giữ nó nhỏ, chỉ chứa cấu hình hoặc fixture thực sự dùng chung. Composed annotation thường thể hiện ý định trực tiếp hơn khi mục tiêu chỉ là tái sử dụng metadata mà không cần kế thừa hành vi Java.

## 17. Kết hợp composed annotation với superclass

Hai cách có thể phối hợp. Ví dụ, annotation định nghĩa chính sách context; base class cung cấp helper hoặc fixture:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@ActiveProfiles("integration")
@Tag("integration")
public @interface SharedIntegrationTest {
}
```

```java
abstract class AbstractOrderTest {

    @Autowired
    protected OrderRepository orderRepository;

    protected Order createTestOrder(String customerId) {
        return new Order(customerId);
    }
}
```

```java
@SharedIntegrationTest
class OrderRepositoryTest extends AbstractOrderTest {
}
```

Annotation xử lý cấu hình; superclass cung cấp helper. Sự phân chia này giúp test class không phải kế thừa một base class chỉ để nhận `@ExtendWith` hoặc `@ContextConfiguration`.

## 18. `@TestExecutionListeners` và cấu hình dùng chung

Một composed annotation cũng có thể đóng gói listener tùy chỉnh nếu mọi test trong nhóm cần cùng hành vi:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@TestExecutionListeners(
    listeners = TestTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
public @interface TimedIntegrationTest {
}
```

`MERGE_WITH_DEFAULTS` giữ các listener mặc định của Spring như dependency injection, transaction và SQL scripts, đồng thời thêm listener tùy chỉnh. Nếu dùng `REPLACE_DEFAULTS`, các listener mặc định có thể bị thay thế và các tính năng quen thuộc ngừng hoạt động.

Chỉ đóng gói listener khi nó là một phần của chính sách chung. Một listener đặc thù chỉ phục vụ một test class nên được khai báo ở test đó để tránh làm mọi test chịu thêm callback hoặc side effect.

## 19. Tag JUnit có thể được đóng gói cùng annotation

JUnit Jupiter cho phép dùng `@Tag` như meta-annotation. Điều này giúp một composed annotation vừa cấu hình Spring vừa phân loại test:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(SharedIntegrationTestConfig.class)
@Tag("integration")
@Tag("database")
public @interface DatabaseIntegrationTest {
}
```

Build tool có thể lọc tag `integration` hoặc `database` để tạo nhóm chạy phù hợp. Tag không tự bật profile Spring và không tự tạo database. `@ActiveProfiles`, datasource configuration hoặc Testcontainers vẫn phải được khai báo riêng.

Nếu một test có nhiều tag khác nhau theo mục đích, có thể giữ `@Tag` trực tiếp trên test class hoặc method thay vì nhồi tất cả vào annotation chung.

## 20. Composed annotation và context cache

Spring Test cache `ApplicationContext` dựa trên merged context configuration. Các thành phần cấu hình như class/location, initializer, active profile, property source, context loader, parent context và context customizer có thể ảnh hưởng việc hai test dùng chung một cache entry hay không.

Composed annotation giúp các test dùng cùng metadata một cách nhất quán. Ví dụ, nếu mười test đều dùng `@SharedIntegrationTest`, chúng có cùng cấu hình cơ sở và có cơ hội tái sử dụng context.

Những thay đổi sau có thể khiến context khác nhau:

- Một test cung cấp thêm configuration class hoặc XML location.
- Test dùng profile khác.
- Property inline hoặc property resource khác nhau.
- Test thêm bean override như `@MockitoBean` hoặc `@MockitoSpyBean`.
- Context initializer, loader hoặc parent context khác.
- Một test đánh dấu context dirty và yêu cầu loại khỏi cache.

Không nên cố ép mọi test dùng cùng context bằng cách đưa tất cả bean vào một cấu hình khổng lồ. Hãy nhóm test theo cấu hình thực sự giống nhau. Cache giúp tái sử dụng context khi metadata tương đương; nó không phải lý do để trộn các môi trường hoặc dependency không liên quan.

## 21. Tránh `@DirtiesContext` trong annotation dùng chung

Không nên đặt `@DirtiesContext` mặc định trong annotation dùng chung cho mọi integration test. Annotation này đánh dấu context cần loại khỏi cache. Nếu được áp dụng cho mỗi test class hoặc method, các test có thể liên tục tạo context mới và thời gian pipeline tăng mạnh.

Chỉ dùng `@DirtiesContext` cho nhóm test thật sự làm thay đổi trạng thái của context hoặc singleton bean theo cách không thể khôi phục. Dữ liệu nghiệp vụ trong database, cache hoặc message broker cần cleanup tại chính nguồn dữ liệu đó.

Nếu một nhóm test đặc biệt cần context mới, tạo annotation chuyên biệt có tên thể hiện rõ chính sách đó, hoặc khai báo `@DirtiesContext` trực tiếp tại class liên quan. Không đưa hành vi hiếm vào annotation cơ sở của toàn bộ suite.

## 22. Tổ chức annotation dùng lại trong test-support module

Khi dự án có nhiều module, có thể tạo một module test-support chứa:

- Composed annotations như `@SharedIntegrationTest`, `@WebLayerTest` hoặc `@DatabaseIntegrationTest`.
- Configuration class dùng chung như `SharedIntegrationTestConfig`.
- Fixture factory và test data builder.
- Fake adapter hoặc test-specific bean.
- Listener và JUnit extension dùng chung.

Các module ứng dụng thêm dependency test-support ở test scope. Nhờ đó, annotation và cấu hình dùng chung không bị đóng gói vào artifact production.

Ví dụ dependency Maven:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>application-test-support</artifactId>
    <version>${project.version}</version>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```kotlin
testImplementation(project(":application-test-support"))
```

Đảm bảo module test-support có dependency Spring Test và JUnit Jupiter cần thiết. Nếu annotation chỉ được dùng ở test compile/runtime, các dependency này nên nằm ở scope phù hợp để không kéo framework kiểm thử vào runtime production.

## 23. Kiểm tra composed annotation có thực sự hoạt động

Một annotation dùng lại nên có ít nhất một test nhỏ xác nhận context được tạo và metadata được áp dụng. Ví dụ:

```java
@SharedIntegrationTest
class SharedIntegrationAnnotationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void loadsSharedContextAndActivatesIntegrationProfile() {
        assertNotNull(context.getBean(OrderService.class));
        assertTrue(environment.acceptsProfiles(Profiles.of("integration")));
    }
}
```

Test này xác nhận cấu hình class và profile. Nếu annotation có alias `classes`, `locations` hoặc `properties`, hãy có test sử dụng giá trị override để chứng minh alias truyền đúng tới meta-annotation.

Ví dụ kiểm tra property:

```java
@OrderIntegrationTest(
    classes = OrderTestConfig.class,
    properties = "feature.audit.enabled=false"
)
class OrderTestPropertyAliasTest {

    @Value("${feature.audit.enabled}")
    boolean auditEnabled;

    @Test
    void appliesPropertyDeclaredThroughComposedAnnotation() {
        assertFalse(auditEnabled);
    }
}
```

Nếu alias sai, Spring có thể báo lỗi khi phân tích annotation hoặc không áp dụng giá trị như mong đợi. Kiểm thử một lần cho annotation dùng chung giúp phát hiện lỗi trước khi nhiều test class phụ thuộc vào nó.

## 24. Các lỗi thường gặp khi đóng gói annotation

- **Quên `@Retention(RUNTIME)`:** Spring/JUnit không đọc được metadata ở runtime.
- **Quên `@Target(TYPE)`:** annotation không thể đặt lên test class nếu target không cho phép.
- **Đăng ký `SpringExtension` lặp lại:** thêm `@SpringJUnitConfig` lên test vốn đã dùng `@SpringBootTest` hoặc một slice annotation đã tích hợp extension.
- **Nhầm `@SpringJUnitConfig` với `@SpringBootTest`:** một bên nạp context theo `@ContextConfiguration`, bên kia dùng Spring Boot bootstrapper và auto-configuration.
- **Không khai báo `@AliasFor`:** thuộc tính trên annotation tùy chỉnh không truyền tới meta-annotation.
- **Alias sai tên hoặc kiểu:** Spring không thể hợp nhất metadata hoặc báo lỗi khi đọc annotation.
- **Đưa property đặc thù vào annotation cơ sở:** mọi test nhận cấu hình không cần thiết.
- **Dùng một annotation cho nhiều loại slice:** test không rõ phạm vi và cấu hình có thể xung đột.
- **Kế thừa quá nhiều base class:** cấu hình và fixture bị ẩn sâu trong hierarchy.
- **Đặt `@DirtiesContext` trong annotation chung:** context cache bị vô hiệu hóa quá thường xuyên.
- **Dùng chung context nhưng chia sẻ dữ liệu mutable:** test phụ thuộc thứ tự hoặc thất bại khi chạy song song.
- **Không kiểm tra alias:** một thay đổi annotation có thể làm cấu hình của nhiều module sai cùng lúc.

## 25. Quy trình thiết kế annotation dùng lại

Khi nhóm muốn chuẩn hóa test Spring, hãy thực hiện theo trình tự:

1. **Tìm phần metadata thật sự lặp lại:** extension, context classes, profile, property, tag hoặc listener.
2. **Chọn annotation nền:** dùng `@SpringJUnitConfig` cho Spring Framework thuần; dùng `@SpringBootTest` hoặc test slice tương ứng cho Spring Boot.
3. **Tạo composed annotation:** đặt các meta-annotation trên annotation mới với target và retention phù hợp.
4. **Mở thuộc tính cần tùy chỉnh:** dùng `@AliasFor` cho class cấu hình, location hoặc property mà test class cần cung cấp.
5. **Giữ cấu hình bean ở class riêng:** gom bean chung vào `@Configuration` hoặc `@TestConfiguration`, mở rộng bằng `@Import` khi cần.
6. **Tách nhóm test khác mục tiêu:** web slice, JPA slice và full integration test nên có annotation riêng nếu chính sách khác nhau.
7. **Kiểm tra context cache:** dùng cùng metadata cho các test có thể chia sẻ context; tránh property hoặc bean override khác nhau không cần thiết.
8. **Viết test cho chính annotation:** xác nhận context, profile, property và alias hoạt động đúng.
9. **Đưa vào test-support module:** nếu nhiều module cùng sử dụng, đóng gói annotation và cấu hình ở test scope.

## 26. Ví dụ hoàn chỉnh: annotation tích hợp cho module đơn hàng

Giả sử module đơn hàng có nhiều integration test cùng dùng cấu hình persistence, profile `integration` và tag `integration`. Mỗi test có thể khai báo property riêng khi cần.

Cấu hình chung:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrderService.class)
@Import(PersistenceTestConfig.class)
class OrderIntegrationConfig {
}
```

Composed annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig
@ActiveProfiles("integration")
@Tag("integration")
public @interface OrderIntegrationTest {

    @AliasFor(annotation = SpringJUnitConfig.class, attribute = "classes")
    Class<?>[] classes() default {};
}
```

Test sử dụng:

```java
@OrderIntegrationTest(classes = OrderIntegrationConfig.class)
@TestPropertySource(properties = "feature.notifications.enabled=false")
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void createsOrderAndPersistsIt() {
        OrderId orderId = orderService.place(validCommand());

        assertTrue(orderRepository.findById(orderId).isPresent());
    }
}
```

Một test khác có thể mở rộng cấu hình:

```java
@OrderIntegrationTest(classes = {
    OrderIntegrationConfig.class,
    PaymentTestConfig.class
})
@TestPropertySource(properties = {
    "feature.notifications.enabled=false",
    "payment.mode=sandbox"
})
class PaymentWorkflowIntegrationTest {
}
```

Trong ví dụ thực tế, khi một thuộc tính meta-annotation có giá trị mặc định cố định, hãy thiết kế alias và default value sao cho đúng quy tắc `@AliasFor` của Spring. Nếu việc mở alias khiến default khó hiểu, có thể giữ profile/property cố định trong annotation và tạo annotation chuyên biệt cho nhóm test có nhu cầu khác.

## 27. Chọn giữa composed annotation và base test class

Hai cách đều giúp tái sử dụng, nhưng giải quyết nhu cầu khác nhau:

| Tiêu chí | Composed annotation | Base test class |
| --- | --- | --- |
| Chia sẻ metadata Spring/JUnit | Rất phù hợp | Có thể, thông qua annotation kế thừa |
| Chia sẻ helper method và fixture | Không | Phù hợp |
| Cho phép test class kế thừa từ class khác | Có | Không chiếm vị trí superclass |
| Hiển thị cấu hình tại test class | Rõ qua một annotation có tên | Một phần có thể nằm trong superclass |
| Mở thuộc tính cấu hình | Dùng `@AliasFor` | Dùng annotation trực tiếp hoặc override cấu hình theo quy tắc Spring |
| Phạm vi phù hợp | Chính sách test có thể tái sử dụng độc lập | Hành vi Java hoặc fixture cần kế thừa |

Nếu chỉ cần gom `SpringExtension`, profile và context config, composed annotation thường gọn. Nếu cần helper, dữ liệu mẫu hoặc setup/teardown dùng chung, base class có thể hữu ích. Có thể kết hợp cả hai nhưng giữ mỗi cơ chế một trách nhiệm rõ ràng.

## 28. Tổng kết

`SpringExtension` kết nối JUnit Jupiter với Spring TestContext Framework. `@SpringJUnitConfig` đã đóng gói extension này cùng `@ContextConfiguration`, còn các annotation Spring Boot như `@SpringBootTest` và test slice đã tích hợp Spring Test theo bootstrap riêng của chúng.

Khi nhiều test cần cùng một profile, property, tag và tập cấu hình, có thể tạo composed annotation. `@AliasFor` cho phép test class tùy chỉnh các thuộc tính như configuration class, XML location hoặc property. Cấu hình bean nên được gom trong class riêng và mở rộng bằng `@Import` khi cần. Giữ metadata nhất quán giúp Spring Test tái sử dụng `ApplicationContext` hiệu quả và giúp test class thể hiện rõ chính sách cấu hình đang áp dụng.
