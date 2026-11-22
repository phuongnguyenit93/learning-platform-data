# Kế thừa annotation và ảnh hưởng của lớp lồng

Trong Spring Framework Testing, annotation trên test class có thể ảnh hưởng đến cách Spring tạo ApplicationContext, chọn profile, nạp property và thực thi các tiện ích kiểm thử. Khi test class được kế thừa hoặc đặt bên trong một class khác bằng JUnit Jupiter @Nested, cần hiểu annotation được tìm thấy theo quy tắc nào và cấu hình nào được truyền sang test class con.

Có ba cơ chế liên quan nhưng không giống nhau:

- **Kế thừa của Java:** annotation có thể được kế thừa từ superclass nếu chính annotation được đánh dấu @Inherited.
- **Cơ chế merged annotation của Spring:** Spring có thể tìm annotation meta, annotation tổng hợp và alias của chúng theo quy tắc riêng.
- **Cấu hình cho nested test:** Spring TestContext Framework có @NestedTestConfiguration để quyết định annotation cấu hình test trên enclosing class có được áp dụng cho nested test class hay không.

Phân biệt ba cơ chế này giúp tránh các lỗi như nested test bất ngờ dùng chung profile hoặc property với class bên ngoài, test con không nhận cấu hình mong đợi, hoặc một annotation tùy chỉnh hoạt động ở superclass nhưng không hoạt động theo cách dự kiến ở lớp lồng.

## 1. Kế thừa annotation trong Java

Java không mặc định kế thừa mọi annotation từ superclass. Muốn một annotation cấp class được kế thừa qua quan hệ extends, kiểu annotation đó cần được khai báo với @Inherited.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface TestEnvironment {
    String value();
}
~~~

Khi annotation được đặt trên superclass:

~~~java
@TestEnvironment("integration")
class BaseIntegrationTest {
}

class OrderServiceTest extends BaseIntegrationTest {
}
~~~

OrderServiceTest có thể được xem là mang annotation TestEnvironment("integration") khi truy vấn bằng API reflection có hỗ trợ kế thừa, chẳng hạn getAnnotation.

Nếu subclass khai báo annotation cùng loại, giá trị trên subclass được dùng cho chính class đó:

~~~java
@TestEnvironment("integration")
class BaseIntegrationTest {
}

@TestEnvironment("staging")
class OrderServiceTest extends BaseIntegrationTest {
}
~~~

OrderServiceTest nhận giá trị staging. Annotation trên superclass vẫn còn hiệu lực đối với các subclass khác không ghi đè nó.

### @Inherited có những giới hạn nào?

@Inherited chỉ tác động đến annotation cấp class theo quan hệ kế thừa superclass. Nó không tự động áp dụng trong các trường hợp sau:

- Annotation đặt trên interface không được kế thừa qua interface.
- Annotation đặt trên method không được kế thừa bởi method ghi đè theo cơ chế @Inherited.
- Annotation đặt trên field, constructor hoặc package không được kế thừa.
- Một nested class không tự kế thừa annotation từ enclosing class chỉ vì nó được khai báo bên trong class đó.

Điểm cuối rất dễ nhầm. Trong Java, quan hệ bao quanh về mặt cú pháp không phải quan hệ kế thừa. Ví dụ:

~~~java
@TestEnvironment("integration")
class PaymentTests {

    class CardPaymentTests {
    }
}
~~~

CardPaymentTests không phải subclass của PaymentTests. @Inherited không làm cho annotation trên PaymentTests tự động trở thành annotation được kế thừa của CardPaymentTests.

JUnit @Nested cũng không thay đổi quy tắc ngôn ngữ Java này. Spring có một cơ chế riêng để xử lý cấu hình test từ enclosing class, được trình bày ở phần sau.

## 2. Spring tìm annotation rộng hơn Java reflection

Spring cung cấp cơ chế merged annotation để hỗ trợ annotation tổng hợp, meta-annotation, alias và tìm kiếm trên hierarchy. Vì vậy, kết quả tra cứu annotation bằng Spring có thể khác với việc chỉ gọi Java reflection.

Ví dụ, một annotation có thể được gắn lên một annotation khác:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles("integration")
public @interface IntegrationTest {
}
~~~

Khi test class dùng @IntegrationTest, Spring TestContext có thể nhận diện @ActiveProfiles thông qua meta-annotation:

~~~java
@IntegrationTest
@SpringJUnitConfig(IntegrationTestConfiguration.class)
class PaymentIntegrationTest {
}
~~~

Điều này cho phép nhóm cấu hình lặp lại thành một annotation có ý nghĩa. Test class chỉ cần thể hiện mục đích integration test; Spring đọc các annotation cấu hình nằm bên dưới.

### Meta-annotation và @Inherited là hai ý riêng

Một annotation có thể mang meta-annotation của Spring mà không nhất thiết được kế thừa từ superclass theo Java. Nếu muốn annotation tùy chỉnh được kế thừa qua class hierarchy theo quy tắc Java, có thể thêm @Inherited lên chính annotation tùy chỉnh:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@ActiveProfiles("integration")
public @interface IntegrationTest {
}
~~~

Khi đó, một subclass không khai báo @IntegrationTest có thể nhận annotation này qua superclass. Tuy nhiên, @Inherited vẫn không làm annotation tự lan từ enclosing class sang nested class.

### Alias trong annotation tổng hợp

Spring hỗ trợ @AliasFor để annotation tùy chỉnh phơi bày một thuộc tính của meta-annotation. Ví dụ, một annotation test chung có thể cho phép lớp sử dụng chọn web environment:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("integration")
public @interface IntegrationTest {

    @AliasFor(
            annotation = SpringBootTest.class,
            attribute = "webEnvironment"
    )
    SpringBootTest.WebEnvironment webEnvironment()
            default SpringBootTest.WebEnvironment.MOCK;
}
~~~

Sử dụng:

~~~java
@IntegrationTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PaymentApiIntegrationTest {
}
~~~

Spring merged annotation xử lý alias để thuộc tính trên annotation tổng hợp được ánh xạ tới thuộc tính của @SpringBootTest.

Khi tạo composed annotation, cần khai báo retention và target phù hợp, đồng thời bảo đảm alias có kiểu và giá trị mặc định tương thích với thuộc tính đích. Nếu annotation cần được kế thừa qua superclass, thêm @Inherited riêng.

Không nên giả định mọi API tra cứu annotation đều dùng cùng một search strategy. Java reflection, Spring AnnotationUtils, MergedAnnotations và TestContext bootstrap có mục tiêu khác nhau. Khi hành vi phụ thuộc vào một annotation cụ thể, cần hiểu quy tắc mà framework đó áp dụng.

## 3. Annotation cấu hình test có thể được kế thừa qua superclass

Spring TestContext Framework hỗ trợ kế thừa nhiều annotation cấu hình test từ superclass. Điều này hữu ích khi nhiều test class dùng chung một bộ cấu hình cơ bản.

Ví dụ:

~~~java
@SpringJUnitConfig(BaseTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
abstract class BaseServiceTest {
}

class OrderServiceTest extends BaseServiceTest {

    @Test
    void createsOrder() {
        // Test dùng cấu hình được kế thừa từ superclass.
    }
}
~~~

OrderServiceTest có thể nhận cấu hình context, active profile và property source từ BaseServiceTest theo quy tắc kế thừa tương ứng của các annotation.

Khi subclass bổ sung cấu hình, một số annotation sẽ hợp nhất giá trị của superclass và subclass theo mặc định. Một số annotation có thuộc tính cho phép thay thế cấu hình kế thừa.

### @ContextConfiguration: hợp nhất classes và locations

@ContextConfiguration có các thuộc tính inheritLocations và inheritInitializers. Mặc định, cấu hình từ superclass được kế thừa và hợp nhất.

~~~java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
abstract class BaseRepositoryTest {
}

@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderRepositoryTest extends BaseRepositoryTest {
}
~~~

Trong trường hợp này, cấu hình lớp con có thể được hợp nhất với cấu hình của lớp cha. Context loader sẽ sử dụng tập cấu hình đã hợp nhất theo quy tắc của @ContextConfiguration.

Nếu muốn cấu hình lớp con thay thế locations hoặc classes được kế thừa, đặt inheritLocations = false:

~~~java
@ContextConfiguration(
        classes = OrderTestConfiguration.class,
        inheritLocations = false
)
class OrderRepositoryIsolatedTest extends BaseRepositoryTest {
}
~~~

Tương tự, inheritInitializers điều khiển việc kế thừa các ApplicationContextInitializer. Mặc định là true; đặt false nếu lớp con cần dùng riêng danh sách initializer của nó.

### @ActiveProfiles: kế thừa profile

@ActiveProfiles mặc định kế thừa profile từ superclass. Ví dụ:

~~~java
@ActiveProfiles("test")
abstract class BaseServiceTest {
}

@ActiveProfiles("database")
class DatabaseServiceTest extends BaseServiceTest {
}
~~~

Với cấu hình mặc định, profile của lớp con được hợp nhất với profile kế thừa. Nếu muốn lớp con chỉ sử dụng profile database, đặt inheritProfiles = false:

~~~java
@ActiveProfiles(
        profiles = "database",
        inheritProfiles = false
)
class DatabaseServiceIsolatedTest extends BaseServiceTest {
}
~~~

Profile có thể ảnh hưởng đến bean được đăng ký, nên việc hợp nhất hay thay thế profile có thể làm ApplicationContext khác đi.

### @TestPropertySource: kế thừa file và inline properties

@TestPropertySource hỗ trợ hai thuộc tính kế thừa riêng:

- inheritLocations điều khiển việc kế thừa file property locations.
- inheritProperties điều khiển việc kế thừa inline properties.

Mặc định cả hai đều là true. Lớp con có thể bổ sung property:

~~~java
@TestPropertySource(properties = "service.mode=stub")
abstract class BaseServiceTest {
}

@TestPropertySource(properties = "service.region=test")
class RegionalServiceTest extends BaseServiceTest {
}
~~~

Nếu muốn loại bỏ inline properties từ lớp cha, dùng inheritProperties = false. Nếu muốn thay danh sách file cấu hình được kế thừa, dùng inheritLocations = false.

Khi cùng một key xuất hiện ở nhiều nguồn, thứ tự ưu tiên của property source vẫn quyết định giá trị cuối cùng. Kế thừa annotation và property precedence là hai bước liên quan nhưng khác nhau: bước đầu quyết định nguồn nào được đưa vào cấu hình, bước sau quyết định nguồn nào thắng khi tra cứu.

### @TestExecutionListeners: kế thừa listener

@TestExecutionListeners có thuộc tính inheritListeners. Mặc định, listener được khai báo ở superclass có thể được kế thừa và hợp nhất với listener ở lớp con theo merge mode tương ứng.

Nếu lớp con cần thay thế tập listener kế thừa, có thể đặt inheritListeners = false. Khi thay đổi listener, cần cân nhắc các listener mặc định của Spring như listener phục vụ dependency injection và transaction. Cấu hình thiếu listener cần thiết có thể làm @Autowired trên test instance hoặc test-managed transaction không hoạt động như mong đợi.

## 4. JUnit Jupiter @Nested là lớp lồng, không phải subclass

JUnit Jupiter dùng @Nested để nhóm các test class bên trong một test class khác. Một nested test class phải là inner class không static.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class WhenOrderIsValid {

        @Test
        void confirmsOrder() {
            // Test cho trường hợp đơn hàng hợp lệ.
        }
    }

    @Nested
    class WhenStockIsInsufficient {

        @Test
        void rejectsOrder() {
            // Test cho trường hợp thiếu hàng.
        }
    }
}
~~~

Các nested class giúp nhóm test theo bối cảnh hoặc trạng thái nghiệp vụ. JUnit chạy các test method trong nested class theo lifecycle của Jupiter và giữ quan hệ với enclosing test instance.

Tuy nhiên, nested class vẫn không phải subclass của enclosing class. Do đó, các quy tắc Java @Inherited không đủ để giải thích việc Spring có truyền cấu hình từ class ngoài vào class lồng hay không.

Spring TestContext Framework cung cấp @NestedTestConfiguration cho trường hợp này.

## 5. @NestedTestConfiguration điều khiển kế thừa cấu hình từ enclosing class

@NestedTestConfiguration cho phép quyết định các annotation cấu hình test trên enclosing class có được kế thừa bởi nested test class hay không.

Annotation nằm trong package:

~~~java
import org.springframework.test.context.NestedTestConfiguration;
~~~

Có hai chế độ:

| Chế độ | Hành vi |
|---|---|
| INHERIT | Nested test class kế thừa annotation cấu hình test từ enclosing class |
| OVERRIDE | Annotation cấu hình test trên enclosing class không được kế thừa vào nested test class |

Mặc định của Spring TestContext Framework là INHERIT. Tính năng này có từ Spring Framework 5.3.

### INHERIT: dùng cấu hình của lớp ngoài

Ví dụ:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
class OrderServiceTests {

    @Nested
    class WhenOrderIsValid {

        @Test
        void usesSharedTestConfiguration() {
            // Nested test sử dụng cấu hình của enclosing class.
        }
    }
}
~~~

Khi dùng chế độ INHERIT, nested class có thể nhận các annotation cấu hình test từ OrderServiceTests. Vì vậy, nested test sử dụng cùng cấu hình context, profile và property source đã được khai báo ở lớp ngoài, trừ khi nó bổ sung hoặc ghi đè theo quy tắc của annotation tương ứng.

Chế độ này phù hợp khi các nested class chỉ chia nhóm theo kịch bản nghiệp vụ và cần cùng một môi trường Spring.

### OVERRIDE: nested class dùng cấu hình riêng

Nếu nested test cần một context hoặc cấu hình khác, có thể đặt @NestedTestConfiguration trên nested class:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @SpringJUnitConfig(AlternativeOrderTestConfiguration.class)
    class WhenUsingAlternativeConfiguration {

        @Test
        void usesAlternativeContext() {
            // Test dùng cấu hình khai báo trên nested class.
        }
    }
}
~~~

OVERRIDE ngăn cấu hình test từ enclosing class được áp dụng cho nested class đó. Nested class có thể khai báo cấu hình riêng của mình bằng @SpringJUnitConfig hoặc annotation phù hợp.

Nếu nested class không khai báo cấu hình thay thế, Spring sẽ xử lý theo metadata và bootstrapper còn lại của test class; không nên kỳ vọng cấu hình của enclosing class vẫn được tự động áp dụng khi đã chọn OVERRIDE.

### Đặt chế độ trên enclosing class

Có thể đặt @NestedTestConfiguration trên enclosing class để áp dụng chính sách cho các nested class bên trong:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
)
class OrderServiceTests {

    @Nested
    class UsesOwnConfiguration {
        // Các nested class áp dụng chính sách OVERRIDE kế thừa.
    }
}
~~~

Khi cần một nested class quay lại chế độ khác, có thể khai báo @NestedTestConfiguration tường minh trên class đó. Việc đặt chính sách ở một nơi chung giúp các test lồng tuân theo cùng một quy ước.

### Thay đổi mặc định toàn cục

Có thể cấu hình chế độ mặc định cho toàn bộ test suite bằng system property:

~~~text
-Dspring.test.context.defaultEnclosingConfiguration=OVERRIDE
~~~

Giá trị có thể là INHERIT hoặc OVERRIDE. Property cần được truyền tới JVM thực thi test.

Ví dụ Gradle:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty(
        'spring.test.context.defaultEnclosingConfiguration',
        'OVERRIDE'
    )
}
~~~

Ví dụ Maven Surefire:

~~~xml
<systemPropertyVariables>
    <spring.test.context.defaultEnclosingConfiguration>
        OVERRIDE
    </spring.test.context.defaultEnclosingConfiguration>
</systemPropertyVariables>
~~~

Chỉ nên thay đổi mặc định toàn cục khi dự án có quy ước rõ ràng cho nested test. Nếu chỉ một vài test cần cấu hình riêng, đặt @NestedTestConfiguration ngay trên class liên quan giúp ý định dễ nhìn thấy hơn.

## 6. Cấu hình kế thừa được hợp nhất ra sao trong nested test?

Khi chế độ là INHERIT, Spring tìm annotation cấu hình test trên enclosing class và kết hợp chúng với annotation của nested class theo quy tắc của từng annotation.

Ví dụ:

~~~java
@SpringJUnitConfig(SharedConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "service.mode=stub")
class BaseOrderTests {

    @Nested
    @ActiveProfiles("database")
    @TestPropertySource(properties = "service.region=local")
    class DatabaseScenario {
    }
}
~~~

Ở đây, cấu hình context từ enclosing class được kế thừa. Profile và property cũng được xử lý theo chính sách kế thừa của annotation tương ứng. Profile của nested class có thể được hợp nhất với profile từ lớp ngoài vì @ActiveProfiles mặc định inheritProfiles = true.

Nếu nested class cần profile riêng hoàn toàn:

~~~java
@Nested
@ActiveProfiles(
        profiles = "database",
        inheritProfiles = false
)
class DatabaseScenario {
}
~~~

Tương tự, @TestPropertySource có thể đặt inheritProperties hoặc inheritLocations thành false để thay thế phần tương ứng.

Cần phân biệt hai cấp điều khiển:

1. @NestedTestConfiguration quyết định có tìm và kế thừa cấu hình test từ enclosing class hay không.
2. Các thuộc tính như inheritProfiles, inheritLocations và inheritProperties quyết định cách hợp nhất giá trị giữa các lớp trong phạm vi kế thừa được phép.

OVERRIDE ở cấp enclosing configuration không đồng nghĩa với mọi annotation trên superclass bị xóa. Kế thừa theo superclass và kế thừa từ enclosing class là hai quan hệ khác nhau. Hãy cấu hình đúng thuộc tính của annotation khi cần kiểm soát từng nguồn.

## 7. Ví dụ: chia nested test theo kịch bản nhưng dùng chung Spring context

Một class service có thể có nhiều kịch bản nghiệp vụ:

~~~java
@SpringJUnitConfig(OrderTestConfiguration.class)
@ActiveProfiles("test")
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class WithAvailableStock {

        @Test
        void acceptsOrder() {
            OrderResult result =
                    orderService.place(new OrderCommand("SKU-01", 2));

            assertEquals(OrderStatus.ACCEPTED, result.status());
        }
    }

    @Nested
    class WithInsufficientStock {

        @Test
        void rejectsOrder() {
            OrderResult result =
                    orderService.place(new OrderCommand("SKU-02", 20));

            assertEquals(OrderStatus.REJECTED, result.status());
        }
    }
}
~~~

Hai nested class chia nhóm theo điều kiện nghiệp vụ. Cả hai đều dùng cấu hình test ở enclosing class.

Nếu effective merged configuration của chúng tương đương, Spring TestContext có thể tái sử dụng cùng ApplicationContext cache entry. Việc chia test thành nested class không tự động buộc Spring tạo context mới cho từng class.

Tuy nhiên, nếu mỗi nested class thêm profile, property source, context customizer hoặc cấu hình bean khác nhau, cache key có thể khác và Spring cần context riêng.

### Dữ liệu test vẫn cần được cô lập

Dùng chung context không có nghĩa dùng chung trạng thái nghiệp vụ mà không kiểm soát. Nếu OrderService hoặc repository giữ dữ liệu thay đổi giữa các test, cần chuẩn bị và dọn dữ liệu theo từng method.

Có thể dùng @BeforeEach trong nested class hoặc transaction test tùy loại dependency. Với database test, transaction rollback có thể giúp cô lập thay đổi thuộc transaction. Side effect như message đã gửi hoặc HTTP request đã hoàn tất không tự được rollback cùng database.

Đừng dùng OVERRIDE chỉ để xử lý dữ liệu test còn sót nếu vấn đề có thể được giải quyết bằng fixture hoặc cleanup. OVERRIDE thay đổi cách chọn cấu hình context và có thể làm tăng số context phải khởi tạo.

## 8. Ví dụ: nested test cần context khác với lớp ngoài

Giả sử nhóm test mặc định dùng fake payment gateway, nhưng một nhóm nested test cần cấu hình database hoặc implementation khác.

~~~java
@SpringJUnitConfig(FakePaymentConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTests {

    @Nested
    class UsesFakeGateway {
        // Kế thừa FakePaymentConfiguration và profile test.
    }

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @SpringJUnitConfig(RealAdapterTestConfiguration.class)
    @ActiveProfiles("adapter-test")
    class UsesAdapterConfiguration {

        @Test
        void loadsAdapterContext() {
            // Kiểm tra bean trong context dành riêng cho adapter.
        }
    }
}
~~~

Nested class UsesAdapterConfiguration chọn OVERRIDE và khai báo cấu hình riêng. Cấu hình từ PaymentServiceTests không được kế thừa vào nested class này.

Nếu cấu hình riêng cần profile hoặc property khác, hãy khai báo chúng trực tiếp. Khi nested class dùng context khác, Spring sẽ tạo hoặc lấy cache entry tương ứng với cấu hình đã hợp nhất của nó.

Ví dụ này phù hợp khi hai nhóm test thực sự cần môi trường khác nhau. Nếu chỉ cần thay một dependency cho một test, bean override như @MockitoBean có thể gọn hơn việc tạo context hoàn toàn khác.

## 9. Annotation tổng hợp trong test class kế thừa và nested test

Composed annotation giúp đóng gói một nhóm cấu hình:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = "service.mode=remote")
public @interface FullIntegrationTest {
}
~~~

Sử dụng trên base class:

~~~java
@FullIntegrationTest
abstract class BaseIntegrationTest {
}

class PaymentIntegrationTest extends BaseIntegrationTest {
}
~~~

Nếu @FullIntegrationTest được đánh dấu @Inherited, subclass có thể nhận annotation qua superclass theo quy tắc Java. Spring merged annotation tiếp tục đọc các meta-annotation như @SpringBootTest, @ActiveProfiles và @TestPropertySource.

Với nested test:

~~~java
@FullIntegrationTest
class PaymentIntegrationTests {

    @Nested
    class CardPayments {
        // Spring Test có thể kế thừa cấu hình từ enclosing class
        // theo mặc định @NestedTestConfiguration(INHERIT).
    }
}
~~~

Việc kế thừa vào nested class ở ví dụ này được điều khiển bởi Spring @NestedTestConfiguration, không phải @Inherited của Java. Nếu chuyển sang OVERRIDE, cấu hình test từ enclosing class sẽ không được áp dụng theo cơ chế đó.

Khi tạo annotation tổng hợp, cần kiểm tra cả hai tình huống: subclass qua extends và nested class qua @Nested. Chúng có cơ chế khác nhau nên một annotation hoạt động trong tình huống này không đảm bảo tự động hoạt động trong tình huống kia.

## 10. Những điểm cần lưu ý với annotation ở cấp method

Annotation trên class và annotation trên method có phạm vi tìm kiếm khác nhau. @Inherited chỉ dành cho class annotation và không làm annotation method tự động truyền sang method ghi đè.

Spring Test có các quy tắc riêng cho annotation method-level. Ví dụ, @Sql có thể được đặt trên class hoặc method để xác định script chuẩn bị dữ liệu. @Transactional có thể được khai báo ở cấp class hoặc method để cấu hình transaction test. Việc hợp nhất class-level và method-level phụ thuộc annotation cụ thể.

Với JUnit @Nested, lifecycle method của enclosing class có thể tham gia vào vòng đời test lồng theo quy tắc Jupiter. Nhưng điều đó không có nghĩa mọi annotation trên method của enclosing class được coi như annotation trên method của nested class.

Khi test có hành vi bất ngờ, hãy xác định annotation nằm ở đâu:

- Trên superclass.
- Trên enclosing class.
- Trên nested class.
- Trên method của enclosing class.
- Trên method của nested class.
- Trên annotation tổng hợp.

Sau đó đối chiếu quy tắc của annotation cụ thể thay vì suy luận tất cả đều dùng cùng một cơ chế kế thừa.

## 11. Ảnh hưởng tới ApplicationContext cache

Cấu hình kế thừa ảnh hưởng trực tiếp đến cấu hình đã hợp nhất mà Spring dùng để tìm ApplicationContext trong cache.

Nếu hai nested class kế thừa cùng cấu hình và không bổ sung khác biệt làm thay đổi cache key, chúng có thể dùng chung context. Nếu một nested class đổi profile, property, initializer, configuration class hoặc context customizer, nó có thể cần context khác.

Ví dụ:

| Test class | Chế độ | Cấu hình hiệu lực | Khả năng dùng chung context |
|---|---|---|---|
| OrderServiceTests | Enclosing class | Config A, profile test | Có context nền |
| WhenOrderValid | INHERIT | Kế thừa Config A, profile test | Có thể dùng context nền |
| WhenStockMissing | INHERIT | Kế thừa Config A, profile test | Có thể dùng context nền |
| UsesDatabase | INHERIT, thêm profile database | Config A, profile test + database nếu được hợp nhất | Có thể cần context khác |
| UsesAlternativeConfig | OVERRIDE | Config B và cấu hình riêng | Cần context phù hợp với Config B |

Cache key không chỉ dựa vào tên test class. Nó dựa trên cấu hình đã hợp nhất và các thành phần liên quan. Vì vậy, hai test class khác tên vẫn có thể chia sẻ context, còn hai nested class trong cùng enclosing class vẫn có thể cần context riêng.

Nếu thấy nhiều context được khởi tạo, hãy kiểm tra profile, property, customizer và cách kế thừa trước khi tăng cache size. Nhiều biến thể cấu hình không cần thiết có thể làm cache phân mảnh.

## 12. Các lỗi thường gặp và cách xử lý

### Nghĩ @Inherited làm annotation truyền vào nested class

@Inherited chỉ xử lý quan hệ superclass. Nested class không phải subclass của enclosing class.

Với Spring Test, dùng @NestedTestConfiguration để điều khiển việc kế thừa annotation cấu hình từ enclosing class.

### Nhầm @Nested với extends

JUnit @Nested chỉ khai báo cấu trúc test lồng. Nó không tạo quan hệ kế thừa Java và không làm nested class trở thành subclass của outer class.

### Nested test bất ngờ nhận profile hoặc property từ lớp ngoài

Mặc định Spring TestContext dùng @NestedTestConfiguration(INHERIT). Nếu nested class cần cấu hình độc lập, khai báo OVERRIDE và cung cấp cấu hình riêng.

Nếu chỉ muốn thay một phần profile hoặc property trong quan hệ superclass, dùng các thuộc tính inheritProfiles, inheritProperties hoặc inheritLocations tương ứng.

### Đặt OVERRIDE nhưng quên cấu hình thay thế

OVERRIDE ngăn cấu hình test từ enclosing class được kế thừa. Nếu nested class cần Spring context, hãy khai báo cấu hình phù hợp trên nested class hoặc bảo đảm bootstrapper của nó có thể tìm cấu hình hợp lệ.

### Subclass không nhận property mong đợi

Kiểm tra @TestPropertySource có inheritProperties/inheritLocations bị tắt hay không. Kiểm tra property cùng key có xuất hiện trong nhiều nguồn và nguồn nào được ưu tiên.

### Profile bị cộng dồn ngoài dự kiến

@ActiveProfiles mặc định kế thừa profile từ superclass. Nếu cần danh sách profile riêng, đặt inheritProfiles = false. Với nested class, kiểm tra thêm chế độ @NestedTestConfiguration.

### Composed annotation không hoạt động như dự kiến

Kiểm tra @Retention(RUNTIME), @Target, meta-annotation và @AliasFor. Nếu cần kế thừa qua superclass, thêm @Inherited lên annotation tổng hợp. Nếu cần áp dụng từ enclosing class tới nested class, kiểm tra @NestedTestConfiguration.

### Context cache tăng nhanh khi dùng nhiều nested class

Các nested class có thể tạo nhiều cấu hình context nếu mỗi class khai báo profile, property hoặc customizer khác nhau. Chuẩn hóa cấu hình dùng chung và chỉ tạo context riêng khi hành vi cần kiểm tra thực sự đòi hỏi môi trường khác.

### Thay đổi annotation trên base class làm nhiều test thất bại

Base test class có thể là nguồn cấu hình chung cho nhiều subclass. Khi sửa profile, property hoặc context configuration, cần xem tác động tới toàn bộ hierarchy. Nếu một nhóm test cần môi trường riêng, hãy tách base class hoặc dùng thuộc tính kế thừa phù hợp.

## 13. Quy trình chẩn đoán khi annotation không được kế thừa đúng

Khi một test class nhận cấu hình khác mong đợi, hãy kiểm tra theo thứ tự:

1. Xác định quan hệ giữa hai class là extends hay enclosing/nested.
2. Nếu là superclass, kiểm tra annotation có hỗ trợ kế thừa và thuộc tính inherit tương ứng.
3. Nếu là nested test, kiểm tra @NestedTestConfiguration đang là INHERIT hay OVERRIDE.
4. Kiểm tra annotation tổng hợp có meta-annotation và alias đúng không.
5. Kiểm tra @ActiveProfiles, @ContextConfiguration và @TestPropertySource có đang hợp nhất hay thay thế giá trị kế thừa.
6. Kiểm tra method-level annotation theo quy tắc riêng của annotation đó.
7. Kiểm tra effective ApplicationContext configuration và cache key.
8. Chạy riêng nested class và chạy toàn bộ test class để xác nhận hành vi không phụ thuộc thứ tự.

Có thể bật log của Spring TestContext để quan sát quá trình bootstrap và cache:

~~~properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Log giúp nhận diện context được tải, tái sử dụng hoặc tạo mới. Nếu test dùng Spring Boot, có thể tăng mức log cho package cấu hình liên quan khi cần tìm property source hoặc bean condition.

## 14. Chọn cơ chế phù hợp theo mục tiêu

| Mục tiêu | Cơ chế nên dùng |
|---|---|
| Subclass nhận annotation cấp class từ superclass | @Inherited nếu annotation hỗ trợ, hoặc quy tắc merged annotation của Spring |
| Gộp cấu hình Spring vào annotation riêng | Meta-annotation và @AliasFor |
| Chia test thành nhóm nested dùng chung context | JUnit @Nested với mặc định @NestedTestConfiguration(INHERIT) |
| Nested class cần cấu hình Spring độc lập | @NestedTestConfiguration(OVERRIDE) và cấu hình riêng |
| Thay profile kế thừa từ superclass | @ActiveProfiles(inheritProfiles = false) |
| Thay property locations kế thừa | @TestPropertySource(inheritLocations = false) |
| Thay inline properties kế thừa | @TestPropertySource(inheritProperties = false) |
| Thay classes/locations của context kế thừa | @ContextConfiguration(inheritLocations = false) |
| Thay initializer kế thừa | @ContextConfiguration(inheritInitializers = false) |
| Thay listener kế thừa | @TestExecutionListeners(inheritListeners = false) |

Khi thiết kế test suite, hãy đặt cấu hình chung ở base class hoặc enclosing class nếu các test thực sự cần cùng môi trường. Dùng nested class để nhóm kịch bản nghiệp vụ. Khi một nhóm nested test cần context khác, chọn OVERRIDE và khai báo cấu hình riêng. Với annotation tổng hợp, phân biệt rõ kế thừa Java, meta-annotation của Spring và quy tắc nested test.

Spring hỗ trợ nhiều lớp kế thừa annotation vì test có thể được tổ chức theo superclass, annotation tổng hợp hoặc cấu trúc nested. Mỗi cơ chế giải quyết một nhu cầu riêng. Nắm rõ quan hệ giữa class và nguồn annotation giúp cấu hình Spring TestContext có thể dự đoán, giảm context không cần thiết và làm cho test suite dễ đọc khi số lượng kịch bản tăng lên.

