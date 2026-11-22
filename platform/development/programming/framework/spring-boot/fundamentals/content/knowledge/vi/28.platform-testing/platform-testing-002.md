# Kiểm thử bean qua Spring context và đối tượng tạo trực tiếp

Một class Java trong ứng dụng Spring Boot thường được đánh dấu `@Service`, `@Component`, `@Repository` hoặc được đăng ký bằng một method `@Bean`. Nhưng khi viết test, ta có hai cách tiếp cận rất khác nhau:

- **Tự tạo object bằng `new`** và truyền các dependency cần thiết. Đây là cách tập trung vào logic Java của class, không cần khởi động Spring.
- **Lấy bean từ một Spring `ApplicationContext`**. Cách này kiểm tra cơ chế đăng ký bean, dependency injection, cấu hình, lifecycle, bean post-processor hoặc AOP proxy khi những cơ chế đó có liên quan.

Cả hai đều đúng trong tình huống thích hợp. Một class có `@Service` vẫn là class Java thông thường và hoàn toàn có thể được tạo trực tiếp. Nhưng `new SomeService()` **không làm Spring tự chạy `@Autowired`, `@PostConstruct`, `@Transactional` hay `@ConfigurationProperties`**. Ngược lại, dùng `@SpringBootTest` cho một phép tính đơn giản có thể làm test chậm, khó cô lập và kéo theo nhiều thành phần không liên quan.

**Nguyên tắc trọng tâm:** hãy kiểm thử đối tượng trực tiếp khi cần xác minh thuật toán và business rules; dùng Spring context khi điều cần xác minh nằm ở cách **Spring tạo, cấu hình hoặc can thiệp vào bean**.

Bài học xây dựng một ví dụ xuyên suốt với service tính phí giao hàng, viết unit test bằng fake và Mockito, rồi đưa cùng service vào Spring context nhỏ, Spring Boot context và MVC slice. Sau đó, chúng ta phân tích những điểm dễ sai: constructor/field injection, bean lifecycle, transaction proxy, conditional beans, profile, caching, test isolation và lựa chọn mức test.

## 1. Một class @Service có thể là object thường hoặc Spring bean

Giả sử có contract lấy đơn giá:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

public interface ShippingRateClient {
    BigDecimal rateFor(String city);
}
~~~

Service:

~~~java
package com.example.shipping;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class ShippingQuoteService {

    private final ShippingRateClient rateClient;

    public ShippingQuoteService(ShippingRateClient rateClient) {
        this.rateClient = Objects.requireNonNull(rateClient);
    }

    public BigDecimal quote(String city) {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException(
                    "city must not be blank"
            );
        }

        return rateClient.rateFor(city)
                .add(new BigDecimal("2.00"));
    }
}
~~~

`ShippingQuoteService` vừa có ý nghĩa đối với Spring, vừa là một class Java độc lập:

- `@Service` cho phép component scan đăng ký class thành bean.
- Constructor công khai cho phép bất kỳ Java caller nào cung cấp `ShippingRateClient`.
- Method `quote` chỉ có logic Java, không trực tiếp gọi `ApplicationContext`.
- Một integration adapter thật có thể lấy rate qua HTTP; test có thể thay bằng fake hoặc mock.

Ta cần tách hai câu hỏi:

**Câu hỏi 1:** `quote("Hue")` có trả đúng giá khi client trả 10.00 không? Chỉ cần tạo object và gọi method.

**Câu hỏi 2:** Spring có tìm thấy service và cung cấp đúng một `ShippingRateClient` bean không? Cần test bằng context.

Một test đúng câu hỏi 1 không tự động chứng minh câu hỏi 2; một test context startup thành công cũng không chứng minh mọi nhánh tính phí đều đúng.

## 2. Bean Spring khác object Java trực tiếp ở đâu?

Một object thông thường:

~~~java
ShippingRateClient client = ...;

ShippingQuoteService subject =
        new ShippingQuoteService(client);
~~~

Bean được Spring quản lý:

~~~java
ApplicationContext context = ...;

ShippingQuoteService subject =
        context.getBean(ShippingQuoteService.class);
~~~

Khi làm việc với bean, Spring có thể thực hiện nhiều bước:

~~~text
@ComponentScan / @Bean / auto-configuration
                    |
                    v
             Bean definition
                    |
                    v
       Bean creation + dependency resolution
                    |
                    v
    Property binding / post-processors / lifecycle
                    |
                    v
          AOP proxy nếu cần thiết
                    |
                    v
          Bean được ứng dụng sử dụng
~~~

Những bước đó không tự xảy ra trong lời gọi `new`.

### 2.1. Khi tạo trực tiếp

~~~text
JUnit test
    |
    +--> new FakeRateClient()
    |
    +--> new ShippingQuoteService(fake)
    |
    +--> quote("Hue")
    |
    +--> assertEquals(...)
~~~

Test kiểm soát chính xác dependency nào được sử dụng. Không có component scan, bean selection hay Boot auto-configuration.

### 2.2. Khi tạo qua Spring context

~~~text
Spring Test bootstrap
        |
        v
ApplicationContext
        |
        +--> Bean definitions
        +--> Dependency injection
        +--> Lifecycle callbacks
        +--> Configuration and conditions
        +--> Possible proxies
        |
        v
ShippingQuoteService bean
        |
        v
Test gọi method và assertion
~~~

Điểm khác biệt lớn nhất là **container có tham gia** vào việc hình thành object và hành vi quan sát được hay không.

## 3. Bảng so sánh hai kiểu test

| Khía cạnh | Object tạo trực tiếp | Spring context |
| --- | --- | --- |
| Subject được tạo bằng | `new` / constructor / factory trong test | Spring `ApplicationContext` |
| Có phải khởi động Spring? | Không | Có |
| Kiểm tra business logic | Rất phù hợp | Có thể, nhưng đôi khi thừa |
| Constructor injection | Test truyền dependency thủ công | Spring resolve bean |
| `@Autowired` field/method | Không tự xử lý | Có nếu bean được quản lý phù hợp |
| `@PostConstruct` | Không tự chạy | Có khi lifecycle infrastructure xử lý |
| `@Transactional`, `@Cacheable` | Không tự có advice | Có thể có khi proxy/infrastructure được bật |
| `@ConfigurationProperties` | Không tự bind | Có khi class được đăng ký đúng |
| `@Profile` / bean conditions | Không tự đánh giá | Spring xét khi xử lý bean definitions |
| `@Primary` / `@Qualifier` | Test tự chọn object | Spring chọn bean theo quy tắc |
| Thời gian khởi động | Thường rất thấp | Tùy độ lớn context |
| External dependencies | Có thể fake/mock | Có thể có bean thật, cần kiểm soát |
| Lỗi chủ yếu bắt được | Logic của class và tương tác với test double | Wiring, conditions, lifecycle, proxy và hành vi thông qua bean |

Không nên biến bảng thành quy tắc máy móc “có Spring là integration test nặng”. Một Spring context có thể chỉ chứa hai bean; ngược lại, unit test trực tiếp cũng có thể vô tình gọi database nếu bạn truyền adapter thật.

## 4. Unit test trực tiếp bằng JUnit 5 và fake

Tạo fake client trả một rate cố định:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

final class FixedRateClient implements ShippingRateClient {

    private final BigDecimal rate;

    FixedRateClient(BigDecimal rate) {
        this.rate = rate;
    }

    @Override
    public BigDecimal rateFor(String city) {
        return rate;
    }
}
~~~

Viết test:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingQuoteServiceTest {

    @Test
    void addsHandlingFee() {
        ShippingRateClient fake =
                new FixedRateClient(new BigDecimal("10.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(fake);

        BigDecimal actual = subject.quote("Hue");

        assertEquals(new BigDecimal("12.00"), actual);
    }

    @Test
    void rejectsBlankCity() {
        ShippingRateClient fake =
                new FixedRateClient(new BigDecimal("10.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(fake);

        assertThrows(
                IllegalArgumentException.class,
                () -> subject.quote("  ")
        );
    }
}
~~~

### 4.1. Vì sao test này không cần @SpringBootTest?

Subject được tạo bằng constructor. Dependency là một fake có behavior do test kiểm soát. `quote` không cần Spring để thực hiện phép cộng.

Test không phải chờ application context, không cần database, HTTP server hoặc Spring Boot auto-configuration.

### 4.2. Test này chứng minh gì?

Nó kiểm tra:

- Service gọi dependency để lấy đơn giá.
- Phí xử lý được cộng đúng.
- Đầu vào rỗng bị từ chối theo contract.

### 4.3. Test này không chứng minh gì?

Nó chưa xác nhận:

- `@Service` được scan.
- Có bean `ShippingRateClient` hợp lệ trong ứng dụng.
- Spring chọn đúng implementation khi có nhiều candidate.
- Bean được áp dụng transaction, cache hay aspect.
- Cấu hình runtime được bind đúng.

Đây là ranh giới chủ ý, không phải khiếm khuyết của unit test.

## 5. Constructor injection giúp cả ứng dụng và test dễ viết

Một service phụ thuộc interface:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal total(BigDecimal subtotal) {
        return subtotal.add(taxCalculator.taxFor(subtotal));
    }
}
~~~

Trong production, Spring có thể resolve `TaxCalculator` bean. Trong unit test, bạn chỉ cần truyền một implementation:

~~~java
TaxCalculator fake =
        subtotal -> new BigDecimal("2.50");

InvoiceService subject = new InvoiceService(fake);
~~~

**Dependency injection là nguyên tắc thiết kế, không phải độc quyền của container.** Gọi constructor với dependency là một hình thức inject hoàn toàn hợp lệ.

### 5.1. Field injection gây khó cho direct test

~~~java
@Service
public class InvoiceService {

    @Autowired
    private TaxCalculator taxCalculator;

    public BigDecimal total(BigDecimal subtotal) {
        return subtotal.add(taxCalculator.taxFor(subtotal));
    }
}
~~~

Nếu test gọi:

~~~java
InvoiceService subject = new InvoiceService();
subject.total(new BigDecimal("100.00"));
~~~

field `taxCalculator` chưa được Spring inject và có thể `null`. Thêm `@Autowired` không khiến Java tự động tạo dependency.

Cách nên ưu tiên là constructor injection:

~~~java
public InvoiceService(TaxCalculator taxCalculator) {
    this.taxCalculator = taxCalculator;
}
~~~

### 5.2. Có nên dùng reflection để set private field trong unit test?

Thường không cần. Một test phụ thuộc nhiều vào reflective field injection có thể là dấu hiệu production class khó sử dụng độc lập. Nếu có quyền thiết kế class, constructor injection thường đơn giản, type-safe và rõ hơn.

### 5.3. @Service không ngăn new

Dù class có:

~~~java
@Service
public class ShippingQuoteService {
    // ...
}
~~~

test vẫn có thể gọi `new ShippingQuoteService(fake)`. Annotation có ý nghĩa với Spring khi Spring xử lý class đó; nó không biến class thành một kiểu Java không thể tạo trực tiếp.

## 6. Unit test bằng Mockito nhưng không khởi động Spring

Nếu không muốn viết fake class, Mockito có thể tạo dependency test double.

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ShippingQuoteMockitoTest {

    @Test
    void usesRateClientResult() {
        ShippingRateClient client =
                mock(ShippingRateClient.class);

        when(client.rateFor("Da Nang"))
                .thenReturn(new BigDecimal("15.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(client);

        assertEquals(
                new BigDecimal("17.00"),
                subject.quote("Da Nang")
        );

        verify(client).rateFor("Da Nang");
    }
}
~~~

Mockito không cần Spring container ở đây.

### 6.1. Fake và mock khác nhau

Fake là implementation nhỏ có hành vi thật nhưng đơn giản. Mock là test double có thể được stub và verify:

~~~java
when(client.rateFor("Hue"))
        .thenReturn(new BigDecimal("10.00"));

verify(client).rateFor("Hue");
~~~

Không cần verify mọi lời gọi implementation detail. Test tốt thường quan tâm đến contract và behavior có ý nghĩa, tránh bị hỏng vì refactor mà không đổi kết quả.

### 6.2. MockitoExtension

JUnit Jupiter có thể tích hợp với Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ShippingWithMockitoExtensionTest {

    @Mock
    ShippingRateClient client;

    @InjectMocks
    ShippingQuoteService subject;

    @Test
    void calculatesQuote() {
        when(client.rateFor("Hue"))
                .thenReturn(new BigDecimal("10.00"));

        assertEquals(
                new BigDecimal("12.00"),
                subject.quote("Hue")
        );
    }
}
~~~

`@Mock` tạo Mockito mock và `@InjectMocks` hỗ trợ lắp subject bằng các mock phù hợp. Chúng **không phải** cơ chế bean creation của Spring.

Nếu subject có constructor gọn, tự gọi constructor trong test đôi khi còn rõ ràng hơn `@InjectMocks`.

### 6.3. @Mock không phải Spring bean

Một field:

~~~java
@Mock
ShippingRateClient client;
~~~

không tự đăng ký bean `ShippingRateClient` vào ApplicationContext. Nếu một Spring context test cần thay một bean bằng mock, phải dùng Spring Test bean override phù hợp.

## 7. Khi nào phải dùng Spring context?

Dùng Spring context khi hành vi cần kiểm tra thực sự đến từ container:

- `@ComponentScan` tìm đúng component.
- `@Bean` factory method đăng ký đúng bean.
- Spring chọn bean theo type, `@Primary` hoặc `@Qualifier`.
- `@ConfigurationProperties` được bind và validate.
- `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` quyết định bean nào tồn tại.
- `@PostConstruct`, bean post-processors hoặc lifecycle callback chạy.
- Spring AOP proxy áp dụng transaction/cache/advice.
- Spring Data tạo repository implementation.
- Spring MVC tạo controller mapping và message converters.
- Spring Boot auto-configuration tạo beans theo dependency/properties.

Tuy nhiên, **dùng Spring context không đồng nghĩa bắt buộc phải nạp toàn bộ ứng dụng**. Có context nhỏ, test slice, application context runner và full Boot context.

## 8. Context nhỏ với @SpringJUnitConfig

`@SpringJUnitConfig` thuộc Spring Test và tích hợp Spring context với JUnit Jupiter. Nó có thể tải một cấu hình kiểm thử rất nhỏ.

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(ShippingContextTest.TestConfig.class)
class ShippingContextTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void springCreatesServiceAndInjectsDependency() {
        assertNotNull(service);

        assertEquals(
                new BigDecimal("12.00"),
                service.quote("Hue")
        );
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        ShippingRateClient rateClient() {
            return city -> new BigDecimal("10.00");
        }

        @Bean
        ShippingQuoteService shippingQuoteService(
                ShippingRateClient client) {
            return new ShippingQuoteService(client);
        }
    }
}
~~~

### 8.1. Spring thực hiện những bước nào?

Spring xử lý `TestConfig`, tạo bean `ShippingRateClient`, resolve dependency của factory method `shippingQuoteService`, tạo `ShippingQuoteService` và inject service vào test field có `@Autowired`.

Đây là test của **context cấu hình bởi test** cùng với hành vi của service qua bean.

### 8.2. Context nhỏ chưa chứng minh production scan

Ví dụ sử dụng `@Bean` tường minh thay vì component scan. Nó kiểm tra được hai bean đó liên kết đúng, nhưng **không chứng minh** component scan production tìm đúng `@Service` hoặc auto-configuration của ứng dụng đã sẵn sàng.

Mục tiêu nào cần kiểm tra thì hãy đưa đúng phần cấu hình đó vào test.

### 8.3. @SpringJUnitConfig so với @ContextConfiguration

Có thể khai báo tương đương theo cách tường minh:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ShippingContextTest {
}
~~~

`@SpringJUnitConfig` là annotation kết hợp tiện lợi. Với JUnit 5 cần Spring Test/JUnit Jupiter dependencies phù hợp.

### 8.4. Test context có thể inject vào parameter

~~~java
@SpringJUnitConfig(ShippingTestConfiguration.class)
class ShippingInjectionTest {

    @Test
    void canInjectTestMethodParameter(
            @Autowired ShippingQuoteService service) {
        assertNotNull(service);
    }
}
~~~

`ShippingTestConfiguration` là cấu hình test phải được định nghĩa trong dự án. SpringExtension resolve parameter từ test ApplicationContext.

## 9. @Autowired trong test không tự hoạt động với JUnit thuần

Test sau không đủ:

~~~java
class PlainJUnitTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void works() {
        service.quote("Hue");
    }
}
~~~

JUnit Jupiter không tự kích hoạt Spring dependency injection chỉ vì thấy `@Autowired`. Nếu test không dùng Spring Test extension/bootstrap tương ứng, field có thể `null`.

Hãy phân biệt:

- `@Autowired` trên bean Spring được Spring xử lý khi tạo bean.
- `@Autowired` trên test class được Spring Test infrastructure xử lý nếu test đã tích hợp với Spring.
- Không có Spring context thì hãy tự tạo subject và dependency bằng constructor.

### 9.1. Đừng coi autowire thành công là toàn bộ test

Test chỉ có:

~~~java
assertNotNull(service);
~~~

kiểm tra được sự hiện diện của bean, nhưng chưa chứng minh service trả đúng kết quả với input nghiệp vụ.

Test nên nêu câu hỏi và assertion tương ứng, không chỉ “context không lỗi”.

## 10. @SpringBootTest: khi cần ứng dụng Spring Boot thật hơn

`@SpringBootTest` thường tải một Boot application context dựa trên cấu hình ứng dụng chính.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ShippingApplicationTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void createsShippingService() {
        assertThat(service).isNotNull();
    }
}
~~~

Spring Boot Test thường tìm class có `@SpringBootApplication` hoặc `@SpringBootConfiguration` trong package hierarchy. Có thể chỉ định:

~~~java
@SpringBootTest(classes = ShippingApplication.class)
~~~

`ShippingApplication` là class cấu hình ứng dụng thực tế được cung cấp trong project.

### 10.1. @SpringBootTest có luôn mở HTTP server?

Không. Giá trị mặc định của `webEnvironment` là `MOCK`. Với web application phù hợp, test có thể dùng mock servlet environment mà **không khởi chạy HTTP server thật**.

Nếu muốn HTTP server thực sự trên cổng ngẫu nhiên:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShippingHttpIntegrationTest {
}
~~~

Test qua HTTP thật giúp xác minh các ranh giới networking/serialization/filter/transaction khác với việc chỉ gọi method Java.

### 10.2. Context loads không phải full functional test

~~~java
@SpringBootTest
class ContextLoadsTest {

    @Test
    void contextLoads() {
    }
}
~~~

Test này có thể xác nhận ứng dụng khởi động context thành công với cấu hình test đang dùng. Nó không chứng minh tất cả endpoint, database query, external integrations hoặc business rules đúng.

### 10.3. Vì sao không dùng @SpringBootTest cho mọi unit test?

Context lớn có thể nạp hàng trăm bean, auto-configurations, database connections, security filters, startup runners và integration adapters. Điều này làm tăng thời gian và độ phức tạp khi một test fail.

Hãy dùng full context khi thật sự cần kiểm tra sự kết nối của các thành phần trên.

## 11. Mô phỏng dependency ngoài khi test qua Spring context

Trong ứng dụng thật, `ShippingRateClient` có thể là HTTP adapter gọi dịch vụ tính giá.

Nếu test dùng full context nhưng không muốn gọi mạng ngoài, cần thay bean thực bằng fake hoặc mock **ở cấp context**.

Có ba cách tư duy:

1. Dùng mock bean override để thay Spring bean trong test.
2. Import test configuration chứa fake bean với lựa chọn override rõ ràng.
3. Chạy local test HTTP server hoặc Testcontainers khi muốn kiểm thử integration thật.

Không nên để một test vô tình gọi API production vì context đã scan adapter thật.

### 11.1. Spring Test @MockitoBean

Ở những phiên bản Spring Framework hỗ trợ, dùng:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

Ví dụ:

~~~java
@SpringBootTest
class ShippingWithMockBeanTest {

    @MockitoBean
    ShippingRateClient rateClient;

    @Autowired
    ShippingQuoteService service;

    @Test
    void usesClientMockFromContext() {
        when(rateClient.rateFor("Hue"))
                .thenReturn(new BigDecimal("10.00"));

        assertThat(service.quote("Hue"))
                .isEqualByComparingTo("12.00");
    }
}
~~~

`@MockitoBean` yêu cầu Spring Test thay hoặc tạo bean mock tương ứng trong test context theo quy tắc override của annotation. Khi Spring tạo `ShippingQuoteService`, dependency được inject là mock do test context cung cấp.

Tùy phiên bản và cấu hình, có thể yêu cầu strict replacement thay vì tự tạo nếu bean không tồn tại.

### 11.2. Spring Boot @MockBean trong các dự án cũ

Trong nhiều project Spring Boot cũ, bạn sẽ thấy:

~~~java
@MockBean
ShippingRateClient rateClient;
~~~

`@MockBean` của Spring Boot là cơ chế test context bean replacement, **không giống** `@Mock` của Mockito. Ở các dòng Boot mới, API này được đánh dấu deprecated và được định hướng chuyển sang `@MockitoBean` khi Spring Framework tương thích.

Kiểm tra version project trước khi thay đổi import/annotation. Đừng mặc định mọi project Boot đều hỗ trợ `@MockitoBean`.

### 11.3. Bảng phân biệt

| Annotation | Ai xử lý? | Có thay bean Spring không? |
| --- | --- | --- |
| `@Mock` | Mockito | Không tự thay |
| `@InjectMocks` | Mockito | Không, chỉ hỗ trợ lắp subject |
| `@MockitoBean` | Spring Test phiên bản hỗ trợ | Có |
| `@MockBean` | Spring Boot Test ở dòng hỗ trợ | Có |

**Một Mockito mock nằm trong test field không tự động trở thành Spring bean.** Nếu mục tiêu là xác minh service được Spring inject dependency mock, dùng đúng cơ chế bean override.

## 12. Test slices: không cần chọn chỉ giữa new và full context

Spring Boot có các test slice tập trung một framework layer:

- `@WebMvcTest`: controller và các thành phần Spring MVC liên quan.
- `@DataJpaTest`: JPA repository, entity mapping và persistence.
- `@JdbcTest`: JDBC.
- `@JsonTest`: Jackson/JSON mapping.
- `@RestClientTest`: kiểm thử HTTP client ở phạm vi phù hợp.

Một slice không nạp toàn bộ business service như full context, trừ những thành phần do test/auto-configuration đưa vào có chủ đích.

### 12.1. Ví dụ @WebMvcTest

Controller:

~~~java
@RestController
@RequestMapping("/api/shipping")
public class ShippingController {

    private final ShippingQuoteService service;

    public ShippingController(ShippingQuoteService service) {
        this.service = service;
    }

    @GetMapping
    public QuoteResponse quote(@RequestParam String city) {
        return new QuoteResponse(service.quote(city));
    }

    public record QuoteResponse(BigDecimal amount) {
    }
}
~~~

Test:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ShippingController.class)
class ShippingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ShippingQuoteService service;

    @Test
    void returnsQuoteAsJson() throws Exception {
        when(service.quote("Hue"))
                .thenReturn(new BigDecimal("12.00"));

        mockMvc.perform(
                get("/api/shipping").param("city", "Hue")
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.amount").value(12.0));
    }
}
~~~

Ví dụ giả định dòng Boot/Spring Test đã hỗ trợ annotation dùng trong test và có JSON conversion phù hợp.

### 12.2. Test này thực sự xác nhận gì?

Nó xác nhận mapping HTTP, query parameter, controller invocation và JSON response contract. Vì `ShippingQuoteService` đã được mock, test này **không xác nhận thuật toán tính phí**.

Đó là lý do cần unit test `ShippingQuoteService` riêng.

### 12.3. @DataJpaTest kiểm tra điều mà new không thể mô phỏng đầy đủ

Spring Data JPA repository thường là interface được framework tạo implementation/proxy ở runtime. Tự `new` một interface repository là không thể.

Một `@DataJpaTest` phù hợp giúp kiểm tra entity mapping, repository query và database behavior với môi trường test. Kết quả phụ thuộc loại database, transaction manager và cách cấu hình data slice.

### 12.4. @JsonTest

Nếu mục tiêu là Jackson serialization và các module/converter được Boot cấu hình, `@JsonTest` có ý nghĩa. Nếu chỉ muốn kiểm tra method nối chuỗi Java, không cần JSON test slice.

## 13. ApplicationContextRunner: kiểm thử bean conditions và auto-configuration

`ApplicationContextRunner` giúp dựng context nhỏ, cung cấp properties và bean definitions, sau đó kiểm tra kết quả.

Ví dụ cấu hình:

~~~java
import java.math.BigDecimal;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RateClientConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.shipping",
            name = "enabled",
            havingValue = "true"
    )
    ShippingRateClient shippingRateClient() {
        return city -> new BigDecimal("10.00");
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class RateClientConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            RateClientConfiguration.class
                    );

    @Test
    void registersBeanWhenEnabled() {
        runner.withPropertyValues("app.shipping.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(ShippingRateClient.class);
                });
    }

    @Test
    void omitsBeanWhenDisabled() {
        runner.withPropertyValues("app.shipping.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(ShippingRateClient.class);
                });
    }
}
~~~

### 13.1. Vì sao gọi method factory trực tiếp là sai mục tiêu?

~~~java
RateClientConfiguration config =
        new RateClientConfiguration();

ShippingRateClient client =
        config.shippingRateClient();
~~~

Lời gọi Java bình thường ở trên vẫn có thể trả client dù `app.shipping.enabled=false`, vì `@ConditionalOnProperty` không phải một câu lệnh `if` bên trong Java method. Spring chỉ xét condition khi xử lý bean definition.

### 13.2. Kiểm thử auto-configuration do thư viện cung cấp

Có thể đưa auto-configuration vào runner:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyAutoConfiguration.class)
        );
~~~

`MyAutoConfiguration` là class auto-configuration do project định nghĩa. Đây là cách tập trung để kiểm tra `@ConditionalOnMissingBean`, property conditions, back-off behavior mà không cần nạp toàn bộ ứng dụng.

## 14. Bean lifecycle: @PostConstruct và @PreDestroy

Một bean có thể có callback khởi tạo và hủy:

~~~java
@Component
public class CacheIndex {

    private boolean initialized;

    @PostConstruct
    public void initialize() {
        initialized = true;
    }

    @PreDestroy
    public void close() {
        initialized = false;
    }

    public boolean isInitialized() {
        return initialized;
    }
}
~~~

Ở Spring Boot 3+ các annotation thường import từ:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

### 14.1. Object tạo bằng new

~~~java
CacheIndex index = new CacheIndex();
assertFalse(index.isInitialized());
~~~

Method `initialize` không tự được gọi. Nếu unit test muốn xác minh logic method, có thể gọi method tường minh, nhưng đó không phải bằng chứng Spring đã thực thi lifecycle.

### 14.2. Bean tạo qua context

Trong Spring context có hạ tầng bean lifecycle phù hợp, sau khi bean được khởi tạo:

~~~java
CacheIndex index = context.getBean(CacheIndex.class);
assertTrue(index.isInitialized());
~~~

Khi context đóng, Spring có thể gọi destroy callback của bean theo scope và lifecycle semantics tương ứng.

### 14.3. Không mọi bean đều tạo ngay khi context startup

Bean lazy, prototype hay custom scope có thời điểm tạo/hủy riêng. Hãy kiểm tra đúng scope và thời điểm cần xác minh thay vì giả định mọi bean đều được tạo ngay lúc startup.

## 15. Spring AOP proxy: @Transactional và @Cacheable

Một method:

~~~java
@Service
public class PaymentService {

    @Transactional
    public void charge(String paymentId) {
        // ...
    }
}
~~~

không tự tạo transaction khi gọi:

~~~java
PaymentService service = new PaymentService();
service.charge("p-1");
~~~

Spring transaction thường được áp dụng qua infrastructure/proxy phù hợp. Tạo một object bằng `new` bỏ qua phần đó.

Tương tự:

~~~java
@Cacheable("products")
public Product findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

không tự được cache khi gọi trên object thường, trừ khi một cơ chế riêng đã được cấu hình và áp dụng.

### 15.1. Khi nào test qua context?

Muốn xác nhận transaction boundary, commit/rollback, caching hoặc aspect advice thực tế, cần context có infrastructure phù hợp và gọi method qua bean/proxy.

### 15.2. Self-invocation vẫn là giới hạn

Ngay cả khi subject là Spring bean:

~~~java
@Service
public class PaymentWorkflow {

    public void process() {
        save(); // this.save()
    }

    @Transactional
    public void save() {
        // ...
    }
}
~~~

lời gọi nội bộ `this.save()` thường không đi qua Spring AOP proxy nên có thể bỏ qua transaction advice cho method đó. Thêm `@SpringBootTest` không tự sửa thiết kế self-invocation.

### 15.3. Direct test vẫn hữu ích cho phần logic thuần

Nếu `PaymentService` có một method tính phí không cần transaction, bạn có thể test logic đó qua object trực tiếp. Không phải vì class có `@Transactional` ở một nơi mà mọi method đều cần integration test.

## 16. @ConfigurationProperties và @Value: new không thực hiện binding

Record:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(
        String region,
        Duration timeout
) {
}
~~~

Nếu test gọi:

~~~java
ShippingProperties properties =
        new ShippingProperties(
                "vn-central",
                Duration.ofSeconds(2)
        );
~~~

đây là object Java với giá trị **do test truyền**, không phải giá trị Binder đọc từ `Environment`.

Để kiểm tra `app.shipping.timeout=2s` được bind thành `Duration`, cần test dùng Spring Binder và đăng ký configuration properties bean phù hợp, chẳng hạn qua `@EnableConfigurationProperties`.

### 16.1. Tách hai mục tiêu

**Test consumer:** tạo một `ShippingProperties` trực tiếp rồi truyền cho service. Mục tiêu là service sử dụng config values như thế nào.

**Test binding:** cung cấp property source, tạo bean qua context, xác nhận conversion, default, nested fields và validation.

Cả hai có giá trị và không thay thế nhau.

### 16.2. @Value không tự inject khi new

~~~java
@Component
public class LegacyShippingClient {

    @Value("${app.shipping.region}")
    private String region;
}
~~~

Tạo `new LegacyShippingClient()` không tự làm `region` có giá trị. Đây là lý do constructor injection hoặc một typed configuration-properties object thường giúp unit test dễ viết hơn.

### 16.3. Cần đăng ký class properties

`@ConfigurationProperties` trên class chưa chắc đã đủ để có bean. Khi test qua context, cần `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc con đường bean registration tương ứng.

Nếu context không có bean properties, hãy kiểm tra cách đăng ký trước khi sửa tên property trong YAML.
## 17. @Profile và conditional bean registration

Giả sử ứng dụng có adapter dành cho môi trường phát triển:

~~~java
@Configuration(proxyBeanMethods = false)
public class ShippingConfiguration {

    @Bean
    @Profile("dev")
    ShippingRateClient developmentClient() {
        return city -> new BigDecimal("5.00");
    }
}
~~~

Trong một Spring context có profile `dev`, bean này có thể được đăng ký. Khi profile không phù hợp, Spring không đăng ký bean qua factory method đó.

Nhưng nếu test gọi:

~~~java
ShippingConfiguration config =
        new ShippingConfiguration();

ShippingRateClient client =
        config.developmentClient();
~~~

Java vẫn thực hiện method bình thường. `@Profile` không phải lệnh `if` bên trong Java method.

### 17.1. @ActiveProfiles

Khi test qua Spring Test context, có thể chọn profile:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ShippingTestProfileIntegrationTest {
}
~~~

Annotation `@ActiveProfiles` ảnh hưởng profile của Spring test context. Nếu chỉ viết JUnit thuần và không dùng Spring Test infrastructure, annotation đó không tự thay đổi cách object `new` hoạt động.

### 17.2. @ConditionalOnMissingBean

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(ShippingRateClient.class)
ShippingRateClient defaultRateClient() {
    return city -> new BigDecimal("8.00");
}
~~~

Spring Boot condition có thể khiến bean mặc định nhường chỗ khi một implementation khác đã được đăng ký đúng thời điểm.

Nếu gọi `defaultRateClient()` trực tiếp, Java không biết context đã có bean nào. Để kiểm tra back-off, hãy dùng `ApplicationContextRunner` hoặc context test phù hợp.

### 17.3. Không biến test thành production profile logic

Nên kiểm tra bean composition và config ở các ranh giới môi trường, nhưng không nên đưa logic kiểu:

~~~java
if (isRunningUnitTest) {
    // ...
}
~~~

vào business service. Tách external dependencies qua interface và truyền implementation phù hợp sẽ rõ ràng hơn.

## 18. Nhiều bean cùng interface: @Primary và @Qualifier

Giả sử hệ thống có hai implementation:

~~~java
@Component("standardRateClient")
public class StandardRateClient implements ShippingRateClient {
    // ...
}
~~~

~~~java
@Component("expressRateClient")
public class ExpressRateClient implements ShippingRateClient {
    // ...
}
~~~

Một constructor như:

~~~java
public ShippingQuoteService(ShippingRateClient client) {
    this.rateClient = client;
}
~~~

có thể trở nên mơ hồ nếu Spring thấy nhiều candidate không có quy tắc lựa chọn đủ rõ.

Spring có những cơ chế như:

- `@Primary` để ưu tiên một bean phù hợp.
- `@Qualifier` để chỉ định candidate theo qualifier.
- Các quy tắc resolve dependency khác của container.

### 18.1. Direct test chọn dependency bằng Java

~~~java
ShippingRateClient fake =
        city -> new BigDecimal("10.00");

ShippingQuoteService subject =
        new ShippingQuoteService(fake);
~~~

Ở đây không có vấn đề bean ambiguity. Test đã chỉ định object cần truyền.

### 18.2. Context test có thể bắt lỗi wiring thật

Nếu production context không khởi động vì có hai bean `ShippingRateClient` nhưng service cần đúng một, test chỉ dùng `new ShippingQuoteService(fake)` sẽ không phát hiện lỗi đó.

Hãy có một context test kiểm tra cấu hình thực tế hoặc một subset đại diện cho production bean definitions.

### 18.3. @Qualifier không phải cơ chế chọn object trong unit test

`@Qualifier` có ý nghĩa đối với Spring injection. Khi test tự gọi constructor với argument, không cần annotation đó để quyết định object nào được truyền.

## 19. Bean scope và việc chia sẻ state giữa các test

Spring bean có scope. Singleton là mặc định thông dụng; prototype tạo instance mới theo những lần bean được yêu cầu theo quy tắc scope.

### 19.1. Object tạo trực tiếp

~~~java
Counter first = new Counter();
Counter second = new Counter();
~~~

Đây là hai object khác nhau vì test gọi `new` hai lần. Điều đó không chứng minh bất kỳ Spring scope nào.

### 19.2. Bean lấy từ Spring context

~~~java
Counter first = context.getBean(Counter.class);
Counter second = context.getBean(Counter.class);

assertThat(first).isSameAs(second);
~~~

Nếu `Counter` được đăng ký như singleton, assertion thường đúng.

Nếu bean là prototype và được yêu cầu hai lần, có thể kỳ vọng hai object khác nhau.

### 19.3. Stateful singleton làm test nhiễu nhau

Ví dụ:

~~~java
@Service
public class CounterService {

    private int count;

    public int increment() {
        return ++count;
    }
}
~~~

Nếu context được tái sử dụng giữa test methods và counter không reset, test sau có thể nhận `count` khác dự kiến.

Direct unit test tạo `new CounterService()` mỗi method thường có state khởi tạo mới, nhưng vẫn có thể bị ảnh hưởng bởi static fields hoặc external storage.

**Tính độc lập giữa các test phụ thuộc state thực tế**, không chỉ phụ thuộc có/không có `ApplicationContext`.

### 19.4. Không dùng @DirtiesContext để che mọi shared-state issue

Nếu một bean có state phục vụ test, cân nhắc reset qua API test hoặc thay đổi thiết kế state. `@DirtiesContext` có thể cần thiết trong vài tình huống, nhưng làm mất lợi ích context cache nếu lạm dụng.

## 20. @Transactional trên test và rollback có những giới hạn gì?

Spring Test hỗ trợ chạy một số test trong transaction khi có Spring transaction infrastructure thích hợp.

Ví dụ một repository test:

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrder() {
        OrderEntity order = new OrderEntity();
        // Thiết lập entity rồi persist/assert...
    }
}
~~~

Trong những data test slices phù hợp, Spring Boot/Spring Test có thể tạo transaction cho test và rollback sau method. Nhưng không nên suy luận rằng **mọi** external side effect sẽ được rollback.

### 20.1. Transaction của test không bao phủ mọi thread

Nếu test chạy một HTTP server thật:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

thì request có thể được phục vụ trên thread khác và dùng transaction khác. Một transaction quanh method test không tự rollback mọi thay đổi do request server thực hiện.

### 20.2. Broker, email và HTTP call không rollback cùng database transaction

Ngay cả khi database có rollback, một email đã gửi hoặc message đã publish ra broker có thể vẫn tồn tại. Test cần kiểm soát các boundary này bằng fake, sandbox, transaction-aware pattern hoặc cleanup riêng.

### 20.3. new không tự bật transaction

Nếu một service được tạo bằng `new` rồi gọi method `@Transactional`, Spring transaction interceptor không tự xuất hiện. Test trực tiếp có thể xác minh logic trong method, nhưng không xác minh transaction boundary.

## 21. Spring TestContext caching: khởi động context không phải mỗi test method

Spring Test có **ApplicationContext cache** giúp nhiều test sử dụng lại context nếu cấu hình context tương đương theo những thành phần tạo cache key.

Điều này có nghĩa:

~~~text
10 test methods
    |
    +--> Không nhất thiết 10 lần startup context
    |
    +--> Có thể reuse context phù hợp
~~~

Những yếu tố như cấu hình test, profiles, property sources, mock bean overrides và customizers có thể ảnh hưởng việc các test dùng chung context hay không.

### 21.1. @DirtiesContext

~~~java
@DirtiesContext
@SpringBootTest
class MutatingContextTest {
}
~~~

`@DirtiesContext` yêu cầu Spring Test đánh dấu context bẩn, dẫn đến context đó không được reuse như trước trong cache.

Dùng khi test thực sự làm thay đổi trạng thái context theo cách không thể cleanup an toàn. Không nên đặt lên tất cả test classes chỉ để “cho chắc”, vì số lần khởi động lại context có thể tăng đáng kể.

### 21.2. Cô lập state bên ngoài

Context được cache hay không không quyết định:

- Database đã được cleanup chưa.
- Redis cache có dữ liệu từ test trước không.
- System properties đã được restore chưa.
- Test có dùng cùng một thư mục temp/file output không.
- Một external service stub đã reset interaction history chưa.

Một bộ test nhanh nhưng dễ bị ảnh hưởng bởi thứ tự chạy vẫn chưa đáng tin cậy.

### 21.3. Mock beans và việc tái sử dụng context

Mock bean definitions là một phần của test context configuration. Dùng những bộ mock override khác nhau có thể dẫn đến các context khác nhau, ảnh hưởng caching.

Vì vậy không cần mock mọi bean cho một test chỉ kiểm tra phép tính. Dùng direct unit test thường đơn giản hơn và tránh vô tình tạo nhiều context variants.

## 22. Chọn mức test theo chi phí và hành vi cần xác minh

Có thể hình dung một dải lựa chọn:

~~~text
                 Kiểm tra logic cô lập
                           |
                           v
                 JUnit + new + fake
                           |
                           v
                    JUnit + Mockito
                           |
                           v
            @SpringJUnitConfig (context nhỏ)
                           |
                           v
          ApplicationContextRunner (conditions)
                           |
                           v
              @WebMvcTest / @DataJpaTest ...
                           |
                           v
               @SpringBootTest (context)
                           |
                           v
    @SpringBootTest(RANDOM_PORT) + dependencies thật
                           |
                           v
            Kiểm tra tích hợp nhiều ranh giới
~~~

Thứ tự trong sơ đồ chỉ mang tính hướng dẫn. Thời gian thực tế phụ thuộc độ lớn context, caching, build, startup runners, database, container và hạ tầng CI. Không phải mọi test slice đều nặng hơn mọi ApplicationContextRunner test.

### 22.1. Vì sao test nhỏ thường cho phản hồi nhanh?

Một unit test tạo vài object không cần Spring bootstrap và ít chịu tác động từ dependency không liên quan. Khi phép tính sai, failure thường chỉ ra đúng nhánh logic.

### 22.2. Vì sao vẫn cần context tests?

Một service có thể đúng từng dòng Java nhưng app không chạy được vì:

- Thiếu bean candidate.
- Sai profile hoặc conditional property.
- Configuration properties không bind đúng.
- Entity mapping/JPA query sai.
- Transaction advice không được áp dụng.
- Security filter chain hoặc MVC mapping sai.

Không thể loại bỏ integration/context tests chỉ bằng cách tăng số lượng unit test.

### 22.3. Không để một test gánh mọi mục tiêu

Một full `@SpringBootTest` vừa tính phí, vừa gửi HTTP, vừa ghi database và xác minh email có thể bắt lỗi end-to-end, nhưng khi fail thường khó khoanh vùng.

Một thiết kế cân bằng thường có nhiều unit tests cho nhánh logic, context/slice tests cho wiring/framework behavior và một số integration tests cho những luồng chính.

## 23. Một chức năng, nhiều câu hỏi kiểm thử

Với `ShippingQuoteService`, có thể tổ chức:

~~~text
src/test/java/com/example/shipping/
├── ShippingQuoteServiceTest.java
├── ShippingQuoteMockitoTest.java
├── ShippingContextTest.java
├── ShippingControllerTest.java
├── RateClientConfigurationTest.java
└── ShippingApplicationSmokeTest.java
~~~

| Test class | Ranh giới | Điều đang xác minh |
| --- | --- | --- |
| `ShippingQuoteServiceTest` | Object trực tiếp + fake | Phép tính và validation |
| `ShippingQuoteMockitoTest` | Object trực tiếp + Mockito | Tương tác với client |
| `ShippingContextTest` | Spring context nhỏ | Bean definitions/wiring |
| `ShippingControllerTest` | MVC slice | URL mapping, parameter, JSON |
| `RateClientConfigurationTest` | Context runner | Conditional bean registration |
| `ShippingApplicationSmokeTest` | Boot context | Ứng dụng khởi động với test config |

Không phải project nào cũng cần đủ sáu loại test. Bảng chỉ cho thấy cách tách câu hỏi để tránh một test khó hiểu làm quá nhiều việc.

### 23.1. Đặt tên test theo behavior

Ví dụ:

~~~java
void rejectsBlankCity()
void registersRateClientOnlyWhenEnabled()
void returnsQuoteAsJson()
void startsWithTestProfile()
~~~

Tên mô tả câu hỏi rõ ràng hơn `test1` hoặc `everythingWorks`.

### 23.2. Không kiểm thử lại toàn bộ thuật toán ở controller slice

Nếu service logic đã có unit tests bao phủ nhiều nhánh, controller slice có thể mock service và chỉ xác minh HTTP contract. Đây không phải thiếu sót mà là cách tránh lặp lại kiểm thử ở sai tầng.

### 23.3. Một end-to-end test vẫn có giá trị

Với luồng nghiệp vụ quan trọng, một integration test đi từ HTTP qua service tới database giúp xác nhận các tầng kết nối được. Nhưng nó nên là sự bổ sung, không thay thế toàn bộ những test cô lập nhanh.

## 24. Kiểm tra bean registration thay vì chỉ assertNotNull

Nếu muốn xác nhận có **đúng một** bean cùng type:

~~~java
Map<String, ShippingRateClient> beans =
        context.getBeansOfType(ShippingRateClient.class);

assertThat(beans).hasSize(1);
~~~

Nếu muốn kiểm tra bean identity:

~~~java
ShippingQuoteService first =
        context.getBean(ShippingQuoteService.class);

ShippingQuoteService second =
        context.getBean(ShippingQuoteService.class);

assertThat(first).isSameAs(second);
~~~

Với một singleton bean, cùng một context thường trả cùng instance/proxy.

Nếu muốn kiểm tra proxy:

~~~java
boolean proxied = AopUtils.isAopProxy(
        context.getBean(PaymentService.class)
);
~~~

`AopUtils` giúp nhận biết Spring AOP proxy, nhưng **không chứng minh một advice cụ thể đã chạy**. Muốn kiểm tra advice, cần lời gọi thực tế và assertion về kết quả/side effect phù hợp.

### 24.1. Test bean name và qualifier khi thật sự quan trọng

Nếu consumer inject một bean theo qualifier, test nên dùng configuration có đúng số lượng candidate cần kiểm tra. Đừng tạo một context chỉ có một candidate rồi kết luận `@Qualifier` đã được xác minh.

### 24.2. Chú ý test-specific bean có thể che lỗi production

Nếu test luôn tự đăng ký:

~~~java
@Bean
ShippingRateClient rateClient() {
    return city -> BigDecimal.TEN;
}
~~~

thì test có thể pass dù production không có adapter thật. Khi cần xác minh production wiring, ít nhất một test phải dùng tập bean definitions đại diện cho production và kiểm soát external environment phù hợp.

## 25. Xử lý external dependencies trong integration test

Một context test có thể kích hoạt:

- Database connection pool.
- HTTP clients.
- Message consumers/producers.
- Cache và Redis connections.
- Scheduled tasks.
- Startup runners.
- Security-related initialization.

Để giữ test đáng tin cậy:

1. **Không dùng production endpoint hoặc credential thật** làm mặc định test.
2. Sử dụng test profile và cấu hình riêng.
3. Stub/mock những boundary ngoài phạm vi đang kiểm tra.
4. Với database/broker integration, dùng môi trường thử nghiệm cô lập, ví dụ test database hoặc Testcontainers nếu phù hợp.
5. Dọn dữ liệu sau test, kiểm soát transaction semantics.
6. Đặt timeout để test không treo vô hạn khi dependency ngoài không đáp ứng.
7. Tránh để test phụ thuộc vào thứ tự chạy.
8. Ghi rõ dependency nào thực, dependency nào giả.

### 25.1. Mock nhiều quá cũng có thể làm test mất ý nghĩa

Nếu mục tiêu là kiểm tra cấu hình HTTP client nhưng bạn mock luôn client đó, test không còn xác minh serialization, URL, headers hay network behavior.

Hãy mock **ngoài ranh giới đang kiểm tra**, không mock chính thành phần mà test cần chứng minh.

### 25.2. Không để startup runner tạo side effect khó kiểm soát

Full Boot context có thể gọi `ApplicationRunner` hoặc `CommandLineRunner`. Nếu runner nạp dữ liệu, tạo file hoặc gọi hệ thống ngoài, test có thể có side effect ngay trong startup.

Hãy thiết kế startup logic idempotent, configurable hoặc tách dependency để test context có thể kiểm soát.

## 26. Lỗi thường gặp trong direct tests

### 26.1. @Autowired field bị null

**Nguyên nhân:** object tạo bằng `new` không qua container.

**Cách xử lý:** dùng constructor injection và truyền fake/mock; nếu muốn kiểm tra injection, dùng context test.

### 26.2. @PostConstruct không chạy

**Nguyên nhân:** Java constructor không tự gọi lifecycle callback của Spring.

**Cách xử lý:** kiểm thử lifecycle qua context; unit test có thể gọi method khởi tạo tường minh nếu chỉ muốn kiểm tra logic của method.

### 26.3. @Transactional không mở transaction

**Nguyên nhân:** không có transaction interceptor/proxy.

**Cách xử lý:** dùng bean trong context có transaction manager phù hợp để kiểm thử transaction behavior.

### 26.4. @Cacheable không cache

**Nguyên nhân:** annotation đơn lẻ không thực thi cache advice trên object do `new` tạo.

**Cách xử lý:** test caching qua proxy và cache infrastructure phù hợp; test logic thuần tách riêng.

### 26.5. Conditional annotation không áp dụng

**Nguyên nhân:** `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và `@Profile` được container xét trong registration phase, không phải khi Java trực tiếp gọi method.

**Cách xử lý:** dùng context runner hoặc Spring context với input properties/profile tường minh.

### 26.6. Direct test pass nhưng ứng dụng vẫn không start

**Nguyên nhân:** logic Java đúng nhưng production bean wiring/properties/auto-configuration sai.

**Cách xử lý:** bổ sung context smoke test hoặc targeted configuration test. Không cần bỏ những unit tests đã có.

### 26.7. Fake không phản ánh đủ contract

**Nguyên nhân:** fake luôn trả một giá trị đẹp, trong khi adapter thật có lỗi, timeout, null/missing data hoặc định dạng phức tạp.

**Cách xử lý:** unit tests thêm những nhánh lỗi hợp lý; integration tests xác minh adapter thật tại boundary riêng.

## 27. Lỗi thường gặp trong Spring context tests

### 27.1. @SpringBootTest không tìm thấy application configuration

**Nguyên nhân:** test nằm ngoài package hierarchy phù hợp hoặc không chỉ định class cấu hình.

**Cách xử lý:** đặt test ở package thích hợp hoặc dùng `@SpringBootTest(classes = Application.class)`.

### 27.2. Nhiều bean cùng type, không resolve được dependency

**Nguyên nhân:** candidate ambiguous.

**Cách xử lý:** kiểm tra `@Primary`, `@Qualifier`, profile/conditional registration và cấu hình dự kiến của ứng dụng.

### 27.3. @WebMvcTest thiếu service bean

**Nguyên nhân:** MVC slice không nạp tất cả business services.

**Cách xử lý:** thay bằng mock bean trong test context hoặc import cấu hình cần thiết, không tự động đổi sang full `@SpringBootTest`.

### 27.4. @Mock không thay bean Spring

**Nguyên nhân:** mock chỉ nằm trong test instance, không phải BeanDefinition/bean override.

**Cách xử lý:** dùng `@MockitoBean` hoặc `@MockBean` theo phiên bản hỗ trợ, hoặc cấu hình fake bean rõ ràng.

### 27.5. Context khởi động quá lâu

**Nguyên nhân:** full context cho bài toán hẹp, dependency ngoài chậm hoặc startup runner không phù hợp với test.

**Cách xử lý:** dùng direct test, context nhỏ, slice hoặc runner tùy mục tiêu; tránh nạp những thành phần không cần thiết.

### 27.6. @DirtiesContext khiến toàn bộ suite chậm

**Nguyên nhân:** nhiều context bị evict khỏi cache và phải tạo lại.

**Cách xử lý:** cleanup state, tận dụng transaction rollback đúng ranh giới hoặc chỉ đánh dấu dirty khi thật cần.

### 27.7. Test pass nhưng deploy fail

**Nguyên nhân có thể:** test dùng properties/mock/profile khác production; infrastructure thật chưa được kiểm tra.

**Cách xử lý:** ghi rõ boundary trong tên và tài liệu test, bổ sung smoke/integration test với configuration đại diện cho deployment.

### 27.8. Test bị ảnh hưởng bởi thứ tự

**Nguyên nhân:** shared singleton state, static fields, database, cache hoặc external stub không được reset.

**Cách xử lý:** cô lập state và cleanup; đừng dựa vào test method execution order.

### 27.9. Có proxy nhưng advice vẫn không chạy

**Nguyên nhân:** pointcut không khớp, method `final`/`private`, self-invocation hoặc caller không đi qua proxy.

**Cách xử lý:** kiểm tra bean thực tế, `AopUtils`, pointcut và đường lời gọi; test advice bằng behavior quan sát được.

### 27.10. Test vô tình mở server thật

**Nguyên nhân:** dùng `RANDOM_PORT` hoặc `DEFINED_PORT` khi chỉ cần controller mapping.

**Cách xử lý:** sử dụng `@WebMvcTest` + `MockMvc` hoặc mock web context phù hợp.

## 28. Dependency test và lệnh chạy

Spring Boot project thường sử dụng test starter.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Tùy Spring Boot major version, tổ chức test starters và các annotation có thể thay đổi. Hãy dùng dependency/import tương ứng với phiên bản project.

### 28.1. Unit test thuần không phụ thuộc Spring Test runtime

Nếu một test chỉ gọi `new`, JUnit và Mockito có thể đủ. Project Boot có thể đã có Spring Test thông qua starter, nhưng test không bắt buộc khởi động Spring.

### 28.2. Chạy test

Với Maven:

~~~bash
mvn test
~~~

Với Gradle:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Đây là các lệnh người học có thể dùng trong project đã cấu hình đúng; bài học không yêu cầu chạy build để chứng minh từng snippet.

## 29. Quy trình chọn loại test theo mục tiêu

Trước khi viết annotation test, trả lời các câu hỏi sau:

1. **Behavior là gì?** Thuật toán, validation, HTTP mapping, wiring, transaction hay configuration?
2. **Behavior có cần container không?** Nếu không, ưu tiên JUnit + `new`.
3. **Dependency có thể truyền qua constructor không?** Nếu có, fake/mock dễ sử dụng.
4. **Cần xác minh bean definitions hoặc lifecycle không?** Dùng `@SpringJUnitConfig` hoặc context nhỏ phù hợp.
5. **Cần xác minh auto-configuration/conditions không?** Dùng `ApplicationContextRunner`.
6. **Cần xác minh một framework slice không?** Dùng `@WebMvcTest`, `@DataJpaTest` hoặc slice tương ứng.
7. **Cần xác minh Boot application startup không?** Dùng `@SpringBootTest`.
8. **Cần HTTP server thật hoặc database/broker thật không?** Dùng integration test và test infrastructure cô lập.
9. **Có state hoặc side effect không?** Thiết kế rollback/reset/cleanup.
10. **Assertion có bảo vệ đúng contract không?** Đừng coi `assertNotNull` là đủ cho mọi chức năng.

Sơ đồ quyết định:

~~~text
             Điều cần kiểm tra
                    |
                    v
     Có phụ thuộc Spring container?
              /           \
           Không          Có
             |             |
             v             v
       JUnit + new     Cần full Boot app?
       + fake/mock        /        \
                       Không       Có
                         |          |
                         v          v
                 Context nhỏ/   @SpringBootTest
                 runner/slice
                         \          /
                          \        /
                           v      v
                         Assertion đúng
                          mục tiêu
~~~

Không cần một quy tắc cố định cho mọi team, nhưng mỗi test nên làm rõ phần nào thuộc Java logic, phần nào thuộc Spring configuration và phần nào là integration với hệ thống ngoài.

## 30. Bài thực hành

### Bài A: Direct test cho một @Service

Tạo `DiscountService` có constructor nhận `DiscountPolicy` interface. Viết test tính discount qua một fake policy, không dùng `@SpringBootTest`.

Kiểm tra ba mức giá và một đầu vào không hợp lệ.

### Bài B: Thay fake bằng Mockito

Dùng `mock(DiscountPolicy.class)`, `when(...)` và `verify(...)`. So sánh fake với mock theo khả năng đọc, sử dụng lại và mức phụ thuộc vào interaction details.

### Bài C: @Autowired field null

Tạo service có field `@Autowired`, thử `new` rồi gọi method. Giải thích vì sao field chưa được inject.

Refactor sang constructor injection và viết lại test không cần Spring.

### Bài D: Spring context nhỏ

Tạo `@Configuration` có hai `@Bean`: một fake `DiscountPolicy` và một `DiscountService`.

Dùng `@SpringJUnitConfig` và `@Autowired` để gọi service từ Spring context. Mô tả Spring đã đăng ký và resolve những bean nào.

### Bài E: @Mock và @MockitoBean

Trong unit test, dùng Mockito `@Mock` và constructor của subject.

Trong Spring context test, dùng `@MockitoBean` hoặc cơ chế bean override phù hợp phiên bản. Quan sát sự khác nhau giữa test field mock và Spring bean mock.

### Bài F: Conditional bean

Tạo:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.discount",
        name = "enabled",
        havingValue = "true"
)
DiscountPolicy discountPolicy() {
    return amount -> amount.multiply(
            new BigDecimal("0.10")
    );
}
~~~

Dùng `ApplicationContextRunner` thử property `true`, `false` và missing. Sau đó gọi method trực tiếp bằng Java và giải thích sự khác biệt.

### Bài G: Lifecycle

Tạo bean có field `initialized` được set trong `@PostConstruct`. So sánh object được `new` với bean trong Spring context có lifecycle infrastructure phù hợp.

### Bài H: Proxy và transaction

Tạo một service có method `@Transactional` và repository test. Xác minh transaction behavior khi gọi qua bean Spring.

So sánh với một direct test chỉ kiểm tra logic, không mặc định annotation tạo transaction.

### Bài I: MVC slice

Viết controller `GET /api/discount` có dependency `DiscountService`. Dùng `@WebMvcTest`, mock bean service và xác nhận HTTP status cùng JSON response.

Giải thích vì sao controller slice không kiểm tra thuật toán discount.

### Bài J: Full context smoke test

Viết `@SpringBootTest` với test profile và dependencies được kiểm soát. Xác nhận context khởi động, sau đó liệt kê ba behavior nghiệp vụ quan trọng **chưa được chứng minh** bởi test rỗng `contextLoads()`.

### Bài K: Context cache

Chạy hai test classes có cấu hình context giống nhau, quan sát startup logs. Thử dùng `@DirtiesContext` trong môi trường thử nghiệm và giải thích tác động tới context caching.

### Bài L: Lập ma trận test cho một module

Một module có service tính toán, REST controller, JPA repository, conditional bean và HTTP API bên ngoài. Chọn loại test thích hợp cho từng boundary và giải thích vì sao không nên dùng full `@SpringBootTest` cho mọi phép tính.

## 31. Câu hỏi tự kiểm tra

**1. Class có `@Service` có thể tạo bằng `new` không?**

Có. Nó vẫn là class Java; annotation chỉ có ý nghĩa khi Spring xử lý class đó trong context.

**2. Constructor injection có bắt buộc Spring không?**

Không. Test có thể tự truyền object, fake hoặc mock vào constructor.

**3. Vì sao `@Autowired` field bị null trong direct test?**

Vì Spring không tham gia tạo object nên không thực hiện field injection.

**4. Mockito `@Mock` có tự trở thành Spring bean không?**

Không. Nó không tự thay một bean trong ApplicationContext.

**5. `@MockitoBean` dùng làm gì?**

Trong các phiên bản Spring Test hỗ trợ, nó giúp override hoặc cung cấp một bean Mockito mock trong test context theo quy tắc annotation.

**6. Khi nào dùng `@SpringJUnitConfig`?**

Khi cần một Spring context nhỏ với configuration/bean definitions được chỉ định, không cần toàn bộ Boot application.

**7. `@SpringBootTest` luôn mở HTTP server thật không?**

Không. Mặc định dùng mock web environment; `RANDOM_PORT` được sử dụng khi cần HTTP server thật theo cấu hình phù hợp.

**8. Vì sao `@WebMvcTest` thường thiếu business service bean?**

Vì MVC slice tập trung vào web layer. Test cần mock hoặc cung cấp dependency chủ đích.

**9. Vì sao gọi trực tiếp method `@Bean` không áp dụng `@ConditionalOnProperty`?**

Vì Spring đánh giá condition khi xử lý bean definition; Java method invocation không tự thực hiện điều đó.

**10. `@PostConstruct` có chạy tự động sau `new` không?**

Không. Nó là lifecycle callback được Spring xử lý với managed bean.

**11. `@Transactional` trên object tạo trực tiếp có tự mở transaction không?**

Không. Spring transaction thường cần interceptor/proxy và transaction manager phù hợp.

**12. Spring context có luôn khởi động lại cho mỗi test method không?**

Không. TestContext framework có thể cache và reuse context khi cấu hình tương ứng.

**13. Có nên dùng `@DirtiesContext` cho mọi context test?**

Không. Nó làm giảm reuse và tăng thời gian startup; chỉ dùng khi cần invalidate context thật.

**14. Direct test với fake HTTP client có chứng minh API ngoài thật hoạt động không?**

Không. Nó xác minh service logic với fake; HTTP integration cần test riêng.

**15. Khi nào `ApplicationContextRunner` đặc biệt phù hợp?**

Khi kiểm tra conditional bean registration, properties và auto-configuration trong context nhỏ.

**16. Một test `contextLoads()` có chứng minh mọi chức năng đúng không?**

Không. Nó chỉ xác minh khả năng khởi động context trong điều kiện test; các behavior khác cần assertions tương ứng.

## 32. Kết luận

Kiểm thử bean qua Spring context và kiểm thử đối tượng tạo trực tiếp **bổ sung cho nhau**. Chúng trả lời hai nhóm câu hỏi khác nhau:

- **Đối tượng tạo trực tiếp:** logic Java có đúng khi dependencies được cung cấp tường minh không?
- **Spring context:** container có đăng ký, lựa chọn, inject, cấu hình và áp dụng lifecycle/proxy cho bean như mong đợi không?

Với phép tính, validation và business rules thuần, bắt đầu bằng JUnit, `new` cùng fake/mock thường đem lại test nhanh, dễ đọc và dễ chẩn đoán. Constructor injection giúp điều này tự nhiên ngay cả khi class là `@Service` trong production.

Khi mục tiêu liên quan `@Autowired`, `@ConfigurationProperties`, bean conditions, `@PostConstruct`, Spring AOP, transaction, cache hoặc framework integration, hãy chọn context phù hợp. `@SpringJUnitConfig` và `ApplicationContextRunner` rất hữu ích cho cấu hình nhỏ; test slices như `@WebMvcTest` và `@DataJpaTest` tập trung vào từng tầng; `@SpringBootTest` dành cho tình huống cần Boot application context ở phạm vi rộng hơn.

Một bộ test đáng tin cậy không được quyết định bởi số lượng annotation Spring, mà bởi **ranh giới rõ ràng, dependencies được kiểm soát và assertions xác minh đúng behavior cần bảo vệ**. Kết hợp unit tests nhanh với context/integration tests có chủ đích sẽ giúp ứng dụng Spring Boot dễ thay đổi mà vẫn phát hiện được cả lỗi logic lẫn lỗi cấu hình container.


