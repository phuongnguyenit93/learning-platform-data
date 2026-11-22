# Spring Test cung cấp cơ chế nào, thư viện assertion cung cấp gì

## 1. Phân biệt hạ tầng kiểm thử và cách kiểm tra kết quả

Trong một dự án Spring, nhiều thành phần cùng tham gia vào một bài test nhưng chúng không có cùng trách nhiệm.

**Spring Test** cung cấp hạ tầng để nạp và quản lý Spring ApplicationContext trong test, inject dependency, thiết lập môi trường web mô phỏng, chạy test trong transaction, tạo mock servlet request/response và cung cấp các client hỗ trợ kiểm tra tầng web. Nó giúp bài test chạy ứng dụng hoặc một phần ứng dụng trong môi trường có kiểm soát.

**Thư viện assertion** cung cấp các biểu thức để so sánh kết quả thực tế với kết quả mong đợi. Chúng trả lời những câu hỏi như: giá trị có bằng nhau không, collection có phần tử này không, exception có được ném ra không, JSON có field đúng không, hoặc một điều kiện có đúng sau một khoảng thời gian không.

Có thể hình dung một bài test theo luồng:

~~~text
JUnit / TestNG
   |
   | khám phá và chạy test method
   v
Spring Test
   |
   | nạp context, inject bean, tạo test fixture,
   | quản lý transaction, mock web environment
   v
Ứng dụng / Controller / Service / Repository
   |
   | kết quả thực tế
   v
Assertion và verification libraries
   |
   | so sánh, mô tả lỗi, xác nhận tương tác
   v
PASS / FAIL
~~~

JUnit thường là test framework và test engine. Spring Test tích hợp Spring vào vòng đời của framework đó. AssertJ, Hamcrest hoặc JUnit Assertions diễn đạt điều kiện cần đúng. Mockito tạo mock và xác nhận tương tác; nó có một API verification nhưng không thay thế toàn bộ assertion library.

Việc phân biệt các vai trò giúp chọn dependency đúng và tránh kỳ vọng rằng chỉ thêm Spring Test là đã có đủ mọi công cụ kiểm tra.

## 2. Spring Test là gì và nằm ở đâu?

Spring Test là module **spring-test** của Spring Framework. Đây là module dùng trong test, cung cấp các API và hạ tầng hỗ trợ kiểm thử ứng dụng Spring.

Một số package quan trọng:

| Package | Vai trò |
|---|---|
| **org.springframework.test.context** | TestContext Framework, nạp ApplicationContext, quản lý lifecycle và listeners |
| **org.springframework.test.context.junit.jupiter** | Tích hợp Spring Test với JUnit Jupiter |
| **org.springframework.test.context.transaction** | Hỗ trợ transaction do test quản lý |
| **org.springframework.test.web.servlet** | MockMvc và API kiểm thử Spring MVC |
| **org.springframework.test.web.reactive.server** | WebTestClient cho WebFlux và một số MVC scenario |
| **org.springframework.test.web.client** | MockRestServiceServer cho REST client đồng bộ |
| **org.springframework.mock.web** | Mock Servlet API như request, response, session và servlet context |
| **org.springframework.test.util** | Utility phục vụ test như ReflectionTestUtils và AopTestUtils |

Spring Test không phải một test runner độc lập. Nó không tự khám phá và chạy test method. Với JUnit Jupiter, test engine của JUnit chạy method, còn **SpringExtension** kết nối vòng đời test với Spring TestContext Framework.

Spring Test cũng không mặc định cung cấp một thư viện assertion tổng quát như AssertJ. Một số API của Spring Test có DSL expectation riêng, chẳng hạn MockMvc và WebTestClient, nhưng các DSL đó có phạm vi tập trung vào HTTP response và thường tích hợp với matcher hoặc thư viện assertion khác.

## 3. TestContext Framework làm gì?

TestContext Framework là phần hạ tầng trung tâm của Spring Test. Nó quản lý cách test lấy Spring context và cách các extension/listener tham gia vào vòng đời test.

Một test có thể cần:

- Nạp cấu hình Java hoặc XML để tạo ApplicationContext.
- Inject service, repository hoặc controller vào test class.
- Dùng profile và property riêng cho test.
- Chạy setup trước test method và cleanup sau test.
- Quản lý transaction và rollback dữ liệu.
- Đánh dấu context cần được tạo lại khi test làm thay đổi trạng thái context.
- Tích hợp các listener để quản lý dependency injection, transaction, SQL script hoặc application event.

Ví dụ với JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(AppConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void shouldCalculateDiscountedPrice() {
        Money result = pricingService.priceFor(
                new Product("book", new Money("100.00")),
                true
        );

        assertThat(result.amount()).isEqualByComparingTo("90.00");
    }
}
~~~

**@SpringJUnitConfig** là annotation kết hợp giữa việc đăng ký **SpringExtension** cho JUnit Jupiter và **@ContextConfiguration** để xác định cấu hình context. Nó giúp test dùng Spring bean mà không cần tự tạo ApplicationContext trong mỗi method.

Với test cần web application context, có thể dùng **@SpringJUnitWebConfig**. Annotation này kết hợp tích hợp JUnit Jupiter, cấu hình context và **@WebAppConfiguration**.

### SpringExtension

**SpringExtension** triển khai extension API của JUnit Jupiter. Nó phối hợp với TestContextManager để thực hiện các bước như:

- Chuẩn bị test instance và inject dependency.
- Gọi các TestExecutionListener theo lifecycle.
- Quản lý callback trước/sau test method.
- Hỗ trợ test-managed transaction khi được cấu hình.
- Cung cấp context cho các annotation kiểm thử của Spring.

Ví dụ khai báo tường minh:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = AppConfig.class)
class InventoryServiceTest {
}
~~~

Cách này tương đương về ý định với việc dùng **@SpringJUnitConfig(AppConfig.class)**. Chỉ nên chọn một cách khai báo phù hợp với style của dự án.

## 4. Các annotation Spring Test thường dùng

Spring Test cung cấp nhiều annotation để điều khiển context và hành vi của test.

| Annotation | Mục đích |
|---|---|
| **@ContextConfiguration** | Chỉ định class cấu hình hoặc resource để nạp ApplicationContext |
| **@SpringJUnitConfig** | Kết hợp SpringExtension và ContextConfiguration cho JUnit Jupiter |
| **@SpringJUnitWebConfig** | Cấu hình test với WebApplicationContext |
| **@WebAppConfiguration** | Yêu cầu tạo WebApplicationContext thay vì context thông thường |
| **@ActiveProfiles** | Chọn profile được kích hoạt trong test |
| **@TestPropertySource** | Thêm property source dành riêng cho test |
| **@DirtiesContext** | Đánh dấu context đã bị thay đổi và cần loại khỏi cache |
| **@Transactional** | Chạy test method trong transaction do Spring Test quản lý nếu có transaction manager |
| **@Commit** | Commit transaction của test thay vì rollback mặc định |
| **@Rollback** | Chọn có rollback transaction sau test hay không |
| **@Sql** | Chạy SQL script trước hoặc sau test |
| **@TestExecutionListeners** | Đăng ký hoặc tùy chỉnh TestExecutionListener |

Ví dụ chọn profile và property:

~~~java
@SpringJUnitConfig(AppConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "catalog.endpoint=http://localhost:9001",
        "feature.discount.enabled=false"
})
class CatalogServiceTest {
}
~~~

Các property trên có thể được inject vào bean qua **@Value** hoặc Environment. Điều này giúp test dùng cấu hình xác định thay vì phụ thuộc file cấu hình của máy lập trình viên.

### Context caching

Spring Test có thể cache ApplicationContext giữa các test có cấu hình tương thích. Việc này giảm thời gian khởi động test suite.

Nếu một test làm thay đổi singleton bean hoặc cấu hình context theo cách ảnh hưởng test khác, có thể cần **@DirtiesContext** để Spring loại context đó khỏi cache. Không nên thêm annotation này theo thói quen vì việc tạo lại context có thể làm test suite chậm đáng kể.

Context caching không tự reset database, Redis, message broker hoặc file bên ngoài Spring context. Những tài nguyên đó cần fixture và cleanup riêng.

## 5. Spring Test cung cấp những mock và công cụ web nào?

Spring Test có các đối tượng mock giúp test web mà không cần khởi chạy servlet container thật.

### Mock Servlet API

Trong package **org.springframework.mock.web**, có thể gặp:

- **MockHttpServletRequest** và **MockHttpServletResponse**: mô phỏng request/response servlet.
- **MockHttpSession**: mô phỏng HTTP session.
- **MockServletContext**: mô phỏng ServletContext.
- **MockMultipartFile**: tạo file upload giả lập trong test.

Chúng hữu ích khi cần tạo request, đặt header, parameter, session attribute hoặc file upload trong bộ nhớ.

Các mock này không mở socket và không mô phỏng đầy đủ hành vi của một servlet container như Tomcat hay Jetty. Chúng tạo môi trường kiểm thử để Spring MVC xử lý request trong phạm vi test.

### MockMvc

**MockMvc** cho phép gửi request qua Spring MVC infrastructure mà không cần HTTP server đang lắng nghe trên port. Request được dispatch qua các thành phần MVC như DispatcherServlet, handler mapping, controller, argument resolver, message converter và exception resolver.

Ví dụ:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42));
~~~

MockMvc cung cấp các nhóm API như:

- Request builders để tạo GET, POST, PUT, DELETE, multipart request.
- Request post-processors để thêm user, session, cookie hoặc thuộc tính.
- Result matchers để kiểm tra status, header, content, view, model và JSONPath.
- Result handlers để in hoặc ghi lại request/response khi test thất bại.

MockMvc phù hợp để kiểm tra MVC contract và logic controller. Nếu cần xác nhận TCP, cổng server, TLS hoặc hành vi connector, cần HTTP integration test với server thật.

### WebTestClient

**WebTestClient** là client kiểm thử có API fluent, thường dùng với WebFlux và cũng có thể dùng trong một số kịch bản Spring MVC.

Nó có thể bind tới controller, router function, application context hoặc server đang chạy. Khi bind vào mock infrastructure, nó không mở socket; khi bind tới server, nó gửi HTTP thật.

Ví dụ expectation:

~~~java
webTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

WebTestClient hỗ trợ kiểm tra status, header, body, JSONPath và response bất đồng bộ. Với endpoint reactive, có thể kết hợp Reactor Test để kiểm tra publisher và event.

### MockRestServiceServer

**MockRestServiceServer** giúp kiểm tra một HTTP client đồng bộ của ứng dụng như RestClient hoặc RestTemplate bằng cách giả lập server mà client gọi tới.

Nó có thể xác nhận URI, method, header, body và response được trả về cho client. Nó không phải một server TCP thật; request được xử lý qua request factory được bind vào cơ chế mock của Spring.

Điều này hữu ích khi kiểm tra integration giữa service và REST client mà không gọi dịch vụ bên ngoài.

## 6. Spring Test và Spring Boot Test không phải cùng một module

Spring Framework cung cấp **spring-test**. Spring Boot bổ sung các module kiểm thử riêng như **spring-boot-test**, **spring-boot-test-autoconfigure** và starter tổng hợp **spring-boot-starter-test**.

Một số annotation quen thuộc thuộc Spring Boot chứ không phải Spring Framework Test:

| Annotation / API | Nguồn |
|---|---|
| **@SpringBootTest** | Spring Boot Test |
| **@WebMvcTest** | Spring Boot Test AutoConfigure |
| **@WebFluxTest** | Spring Boot Test AutoConfigure |
| **@AutoConfigureMockMvc** | Spring Boot Test AutoConfigure |
| **@AutoConfigureWebTestClient** | Spring Boot Test AutoConfigure |
| **@MockBean** (các phiên bản Boot cũ) | Spring Boot Test |
| **@MockitoBean** / **@MockitoSpyBean** | Spring Framework Test trong các phiên bản Spring Framework hỗ trợ |

Spring Boot Test dùng nền tảng Spring Test và tự động cấu hình thêm theo convention của Boot. Ví dụ, **@SpringBootTest** tìm cấu hình ứng dụng Boot và tạo context theo cách Boot quản lý.

Vì vậy, khi đọc một test, cần biết annotation đến từ package nào. Không nên nói **@WebMvcTest** là annotation của Spring Framework chỉ vì nó sử dụng MockMvc và Spring Test phía dưới.

### @SpringBootTest

Dùng khi cần nạp phần lớn hoặc toàn bộ ứng dụng Spring Boot:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {
}
~~~

Có thể chọn web environment:

- **MOCK**: tạo web application context mock, không mở cổng server.
- **RANDOM_PORT**: khởi động server thật trên port ngẫu nhiên.
- **DEFINED_PORT**: khởi động server thật trên port cấu hình.
- **NONE**: không tạo web environment.

### @WebMvcTest và @WebFluxTest

Đây là các slice test. Chúng chỉ nạp phần cấu hình liên quan đến MVC hoặc WebFlux và các bean được chọn, giúp test controller nhanh hơn so với khởi động toàn bộ ứng dụng.

Nếu controller phụ thuộc service, thường mock service trong slice test. Với Spring Framework 6.2 trở lên có thể dùng **@MockitoBean**; các phiên bản Spring Boot cũ thường dùng **@MockBean**.

## 7. Spring Test có hỗ trợ transaction và SQL fixture

Spring Test có tích hợp với transaction management. Khi test method được đánh dấu **@Transactional** và context có transaction manager phù hợp, Spring Test có thể bắt đầu transaction trước test và rollback sau test theo mặc định.

~~~java
@SpringJUnitConfig(DataConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository repository;

    @Test
    void shouldPersistAnAccountInsideTestTransaction() {
        repository.save(new Account("A-100"));

        assertThat(repository.findByNumber("A-100")).isPresent();
    }
}
~~~

Cơ chế này hữu ích cho test gọi repository/service trong cùng transaction được quản lý bởi test framework.

Có thể dùng **@Commit** để commit hoặc **@Rollback(false)** để tắt rollback. Chỉ nên làm vậy khi test thật sự cần dữ liệu được commit và đã có kế hoạch cleanup.

### @Sql

**@Sql** chạy SQL script để chuẩn bị dữ liệu hoặc dọn dữ liệu:

~~~java
@Test
@Sql("/sql/accounts-before.sql")
@Sql(
        scripts = "/sql/accounts-after.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void shouldFindAnAccount() {
    assertThat(repository.findByNumber("A-100")).isPresent();
}
~~~

Spring Test cũng có transaction test listeners và callback như **@BeforeTransaction** hoặc **@AfterTransaction** khi cần setup/cleanup ngoài transaction của test.

Lưu ý: transaction của test method không tự bao bọc request HTTP được xử lý bởi server trên thread hoặc reactive pipeline riêng. Với **RANDOM_PORT**, endpoint có transaction riêng. Trong trường hợp đó, cần cleanup fixture rõ ràng hoặc dùng database/schema riêng.

## 8. Các tiện ích hỗ trợ test trong Spring Test

Spring Test cung cấp một số utility hữu ích khi kiểm thử thành phần Spring.

### ReflectionTestUtils

**ReflectionTestUtils** cho phép đọc hoặc ghi field, gọi method không public và truy cập một số thành phần qua reflection.

~~~java
ReflectionTestUtils.setField(service, "clock", fixedClock);

Object value = ReflectionTestUtils.getField(service, "clock");
~~~

Nó có thể hữu ích với legacy code hoặc test cần thay dependency trong thành phần không được thiết kế để inject qua constructor. Tuy nhiên, test phụ thuộc private field thường dễ gãy khi implementation thay đổi. Nên ưu tiên constructor injection và API công khai khi có thể.

### AopTestUtils

**AopTestUtils** giúp truy cập target object bên trong một Spring AOP proxy:

~~~java
Object target = AopTestUtils.getTargetObject(proxiedBean);
~~~

Nó hữu ích khi cần kiểm tra một object được bọc bởi proxy, chẳng hạn proxy transaction hoặc scoped proxy. Cần thận trọng vì gọi trực tiếp target có thể bỏ qua hành vi của proxy mà test đang muốn xác nhận.

### ApplicationEvents

Spring Test hỗ trợ ghi nhận application event trong test bằng **@RecordApplicationEvents** và inject **ApplicationEvents**:

~~~java
@SpringJUnitConfig(AppConfig.class)
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    private ApplicationEvents events;

    @Test
    void shouldPublishOrderCreatedEvent() {
        orderService.createOrder(command);

        assertThat(events.stream(OrderCreatedEvent.class))
                .hasSize(1);
    }
}
~~~

Cơ chế này hữu ích khi xác nhận một bean đã publish event trong application context. Nếu cần kiểm tra xử lý event bất đồng bộ hoặc qua message broker bên ngoài, cần chờ và xác nhận ở đúng ranh giới tương ứng.

## 9. JUnit Jupiter Assertions kiểm tra điều gì?

JUnit Jupiter cung cấp assertion cơ bản trong package **org.junit.jupiter.api.Assertions**. Đây là lựa chọn mặc định khi dự án dùng JUnit 5 và muốn tránh thêm một thư viện assertion khác.

Một số API thường dùng:

| API | Mục đích |
|---|---|
| **assertEquals(expected, actual)** | So sánh hai giá trị |
| **assertNotNull(value)** | Xác nhận giá trị khác null |
| **assertTrue(condition)** / **assertFalse(condition)** | Xác nhận điều kiện boolean |
| **assertThrows(type, executable)** | Xác nhận đoạn code ném exception đúng kiểu |
| **assertDoesNotThrow(executable)** | Xác nhận đoạn code không ném exception |
| **assertAll(...)** | Chạy nhiều assertion và báo các lỗi cùng lúc |
| **assertTimeout(...)** | Xác nhận một đoạn code hoàn tất trong giới hạn thời gian |

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DiscountServiceTest {

    @Test
    void shouldApplyDiscount() {
        Money result = service.applyDiscount(new Money("100.00"), 10);

        assertEquals(new Money("90.00"), result);
    }

    @Test
    void shouldRejectNegativeDiscount() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.applyDiscount(new Money("100.00"), -5)
        );

        assertTrue(error.getMessage().contains("discount"));
    }
}
~~~

JUnit assertion đơn giản, có sẵn và phù hợp với nhiều test. Khi cần kiểm tra object lồng nhau, collection, chuỗi hoặc domain object với biểu thức dễ đọc hơn, AssertJ thường tiện hơn.

JUnit Assertions không phải toàn bộ JUnit. JUnit còn cung cấp annotation lifecycle, parameterized tests, assumptions, extensions và test engine.

## 10. AssertJ cung cấp fluent assertions

**AssertJ** là thư viện assertion độc lập, tập trung vào API fluent dễ đọc và thông báo lỗi có ngữ cảnh.

Ví dụ so sánh số:

~~~java
assertThat(actualPrice)
        .isEqualByComparingTo("90.00");
~~~

Kiểm tra collection:

~~~java
assertThat(products)
        .hasSize(2)
        .extracting(Product::name)
        .containsExactly("Keyboard", "Mouse");
~~~

Kiểm tra exception:

~~~java
assertThatThrownBy(() -> service.findById("missing"))
        .isInstanceOf(ProductNotFoundException.class)
        .hasMessageContaining("missing");
~~~

So sánh object theo thuộc tính:

~~~java
assertThat(actual)
        .usingRecursiveComparison()
        .isEqualTo(expected);
~~~

AssertJ có assertion cho primitive, object, collection, map, stream, file, exception và nhiều kiểu dữ liệu khác. Nó cũng có **SoftAssertions** để gom nhiều lỗi assertion trong một test thay vì dừng ngay ở lỗi đầu tiên.

Không nên dùng recursive comparison cho mọi object. Với entity có quan hệ hai chiều, field kỹ thuật hoặc dữ liệu không thuộc hợp đồng cần kiểm tra, nên chọn các property có ý nghĩa thay vì so sánh toàn bộ object graph.

## 11. Hamcrest và matcher trong MockMvc

**Hamcrest** cung cấp matcher để diễn đạt điều kiện trên giá trị. Matcher có thể kết hợp thành biểu thức như **equalTo**, **containsString**, **hasSize**, **hasItem**, **allOf** hoặc **not**.

Ví dụ:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;

mockMvc.perform(get("/api/products"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name", equalTo("Keyboard")))
        .andExpect(jsonPath("$.description", containsString("wireless")))
        .andExpect(jsonPath("$.items", hasSize(2)));
~~~

MockMvc có DSL **ResultMatcher** riêng trong Spring Test. Các matcher như **status()**, **header()**, **content()**, **view()**, **model()** và **jsonPath()** là API Spring Test. Khi truyền matcher vào overload của JSONPath, Hamcrest có thể cung cấp điều kiện so sánh giá trị đó.

Do đó, hai thành phần hợp tác với nhau:

- Spring Test biết cách lấy status, header, model hoặc JSON property từ MVC result.
- Hamcrest diễn đạt điều kiện mà giá trị đó phải thỏa mãn.

Không phải mọi assertion trong MockMvc đều yêu cầu Hamcrest. Nhiều matcher có phương thức trực tiếp như **isOk()**, **exists()**, **isArray()** hoặc **doesNotExist()**.

## 12. JSONPath và JSONAssert kiểm tra cấu trúc JSON

JSON có cấu trúc object, array, string, number, boolean và null. Assertion trên JSON nên kiểm tra đúng cấu trúc đó thay vì dùng **String.contains(...)** trên toàn bộ response.

### JSONPath

JSONPath chọn một node trong JSON bằng biểu thức. Ví dụ:

- **$.id**: property id ở root.
- **$.customer.name**: tên khách hàng lồng nhau.
- **$.items[0].sku**: SKU của phần tử đầu tiên.
- **$.items.length()**: số phần tử trong array theo cú pháp hỗ trợ của implementation.

Trong MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.customer.name").value("Linh"))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(2));
~~~

Trong WebTestClient, có thể dùng JSONPath expectation tương ứng:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.customer.name").isEqualTo("Linh");
~~~

JSONPath đặc biệt hữu ích khi chỉ cần kiểm tra một số property mà không muốn khóa test vào toàn bộ response.

### JSONAssert và content().json(...)

JSONAssert so sánh hai JSON document theo cấu trúc. Nó có chế độ strict và non-strict tùy việc test có yêu cầu property bổ sung hoặc thứ tự array hay không.

Trong MockMvc, có thể dùng:

~~~java
mockMvc.perform(get("/api/products/42"))
        .andExpect(content().json("""
                {
                  "id": 42,
                  "name": "Keyboard"
                }
                """));
~~~

**content().json(...)** là matcher của Spring Test; thư viện JSONAssert có thể được dùng bên dưới để so sánh JSON. Với body lớn, nên chọn strictness phù hợp với API contract. JSON object thường không cần phụ thuộc thứ tự property, nhưng thứ tự phần tử trong array thường có ý nghĩa.

Nếu chỉ cần kiểm tra field bị thiếu, null hoặc có kiểu dữ liệu cụ thể, JSONPath hoặc parse response thành JsonNode có thể diễn đạt rõ hơn.


## 13. Mockito là mock framework, không phải assertion library tổng quát

**Mockito** tạo mock, stub hành vi dependency và xác nhận tương tác giữa các object.

Stub một service:

~~~java
when(productService.findById(42L))
        .thenReturn(new Product(42L, "Keyboard"));
~~~

Xác nhận service được gọi:

~~~java
verify(productService).findById(42L);
~~~

Dùng ArgumentCaptor để kiểm tra dữ liệu được truyền:

~~~java
ArgumentCaptor<CreateOrderCommand> captor =
        ArgumentCaptor.forClass(CreateOrderCommand.class);

verify(orderService).create(captor.capture());

assertThat(captor.getValue().customerId()).isEqualTo("C-42");
~~~

**verify(...)** là behavioral verification: nó xác nhận một tương tác đã xảy ra. AssertJ hoặc JUnit tiếp tục kiểm tra giá trị được capture. Hai công cụ bổ sung cho nhau.

Không nên verify mọi lời gọi nội bộ của service. Hãy xác nhận những tương tác quan trọng đối với hợp đồng của component, chẳng hạn service gọi gateway một lần với đúng command hoặc không gọi repository khi request không hợp lệ.

## 14. Reactor Test và Awaitility cho kết quả bất đồng bộ

### StepVerifier

Với Reactor, kết quả thường là **Mono** hoặc **Flux**. Không nên gọi block chỉ để kiểm tra mọi luồng reactive. **StepVerifier** thuộc module **reactor-test** và cho phép kiểm tra chuỗi signal: next, complete, error và cancellation.

~~~java
StepVerifier.create(service.findProducts())
        .expectNextMatches(product ->
                product.name().equals("Keyboard"))
        .expectNextMatches(product ->
                product.name().equals("Mouse"))
        .verifyComplete();
~~~

Kiểm tra lỗi:

~~~java
StepVerifier.create(service.findById("missing"))
        .expectError(ProductNotFoundException.class)
        .verify();
~~~

StepVerifier không thuộc Spring Test hoặc AssertJ. Nó là công cụ kiểm tra reactive stream của Project Reactor. Có thể dùng AssertJ bên trong **expectNextMatches(...)** nếu cần assertion phức tạp hơn.

### Awaitility

Một số hệ thống xử lý công việc bất đồng bộ qua executor, event listener hoặc message broker. Kết quả có thể xuất hiện sau một khoảng thời gian không xác định. **Awaitility** cho phép đợi một điều kiện đạt được trong một khoảng thời gian tối đa:

~~~java
await()
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(repository.findById(orderId)).isPresent()
        );
~~~

Awaitility phù hợp với eventual consistency và tác vụ nền. Không nên thay mọi assertion đồng bộ bằng await. Chỉ dùng khi hành vi của hệ thống thực sự bất đồng bộ và có một điều kiện cuối cùng rõ ràng.

## 15. Dependency nào cần thêm?

### Dự án Spring Framework không dùng Spring Boot

Một dự án Spring thuần thường cần thêm Spring Test và test framework/assertion mà nhóm chọn.

Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.hamcrest:hamcrest")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.assertj</groupId>
        <artifactId>assertj-core</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.hamcrest</groupId>
        <artifactId>hamcrest</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các phiên bản nên được quản lý bằng Spring Framework BOM, Spring Boot dependency management hoặc một dependency management strategy thống nhất của dự án. Không nên ghim các phiên bản khác nhau tùy tiện nếu chúng có thể xung đột.

### Dự án Spring Boot

Với Spring Boot, dependency thường dùng là:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Starter này tập hợp Spring Boot Test, Spring Test và các thư viện test phổ biến như JUnit Jupiter, AssertJ, Hamcrest, Mockito, JSONassert và JsonPath theo phiên bản Spring Boot đang dùng.

Nếu cần kiểm tra Reactor publisher bằng StepVerifier, thêm **reactor-test**:

~~~groovy
dependencies {
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Nếu cần Awaitility, thêm dependency test riêng theo phiên bản được dự án quản lý. Không cần thêm tất cả thư viện assertion nếu dự án chỉ sử dụng một phong cách assertion.


## 16. Kết hợp Spring Test và assertion trong cùng một bài test

Một bài test thường dùng nhiều lớp API cùng lúc. Spring Test tạo môi trường và thực hiện request; assertion library kiểm tra dữ liệu; mock framework xác nhận tương tác nếu cần.

Ví dụ controller slice với Spring Boot:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private ProductService productService;

    @Test
    void shouldReturnAProduct() throws Exception {
        given(productService.findById(42L))
                .willReturn(new ProductResponse(42L, "Keyboard"));

        mockMvc.perform(get("/api/products/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Keyboard"));

        then(productService).should().findById(42L);
    }
}
~~~

Trong ví dụ:

- **@WebMvcTest** là cơ chế slice test của Spring Boot.
- **MockMvc** và **jsonPath/status()** là API của Spring Test để dispatch request và kiểm tra MVC result.
- **@MockitoBean** thay bean ProductService trong context bằng Mockito mock trên các phiên bản Spring Framework có hỗ trợ.
- **given(...).willReturn(...)** và **then(...).should()** thuộc Mockito BDD API.
- Các assertion trong MockMvc matcher được thực hiện thông qua expectation DSL của Spring Test; JSONPath matcher có thể dùng Hamcrest khi cần matcher tùy chỉnh.

Nếu dự án Spring Boot cũ chưa có **@MockitoBean**, dùng annotation mock bean tương ứng mà phiên bản Boot đang hỗ trợ, thường là **@MockBean**. Khi nâng cấp Spring, kiểm tra package và hướng dẫn migration của phiên bản đang dùng.

Ví dụ test service thuần với Spring context:

~~~java
@SpringJUnitConfig(AppConfig.class)
class ProductServiceTest {

    @Autowired
    private ProductService service;

    @Test
    void shouldReturnTheExpectedProduct() {
        Product result = service.findById(42L);

        assertThat(result)
                .extracting(Product::name)
                .isEqualTo("Keyboard");
    }
}
~~~

Ở đây Spring Test chỉ lo nạp context và inject service. AssertJ thực hiện so sánh kết quả. Không cần MockMvc nếu test không kiểm tra HTTP.

## 17. Chọn assertion theo dữ liệu cần kiểm tra

| Dữ liệu hoặc hành vi | Công cụ phù hợp |
|---|---|
| Giá trị primitive, boolean, exception cơ bản | JUnit Assertions |
| Object, collection, map và domain value | AssertJ |
| Matcher có thể kết hợp hoặc diễn đạt điều kiện | Hamcrest |
| Status, header, content và MVC model | MockMvc ResultMatchers |
| JSON property cụ thể | JSONPath qua MockMvc hoặc WebTestClient |
| So sánh hai JSON document | JSONAssert hoặc content().json(...) |
| Tương tác với dependency | Mockito verify và ArgumentCaptor |
| Mono/Flux signals, completion và error | Reactor StepVerifier |
| Kết quả xuất hiện cuối cùng sau xử lý bất đồng bộ | Awaitility |
| XML structure | XMLUnit hoặc matcher XML phù hợp |

Không có một thư viện duy nhất cần dùng cho mọi test. Chọn công cụ làm cho ý định của assertion rõ nhất và tránh trộn nhiều phong cách trong cùng một test nếu không cần thiết.

Một quy ước thường dễ duy trì là dùng AssertJ cho assertion Java tổng quát, Spring Test matcher cho HTTP/MVC, StepVerifier cho Reactor và Mockito cho stubbing/verification.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách hiểu đúng |
|---|---|---|
| Spring Test là test runner | Spring Test tích hợp Spring vào test framework | Dùng JUnit Jupiter hoặc test framework tương ứng để chạy test |
| Spring Test là assertion library | Spring Test cung cấp hạ tầng và một số expectation DSL theo miền | Dùng JUnit Assertions, AssertJ, Hamcrest hoặc thư viện chuyên biệt cho điều kiện |
| MockMvc khởi chạy web server thật | MockMvc dispatch request trong mock servlet environment | Dùng RANDOM_PORT và HTTP client khi cần socket thật |
| WebTestClient luôn dùng socket | WebTestClient có thể bind mock context hoặc server | Xác định bind mode trước khi kết luận test đang kiểm tra transport |
| Mockito là thư viện assertion | Mockito tạo mock, stub và verify tương tác | Dùng AssertJ/JUnit để kiểm tra giá trị đã capture |
| @SpringBootTest thuộc Spring Framework | Đây là annotation của Spring Boot Test | Phân biệt spring-test với spring-boot-test |
| @Transactional trên test luôn rollback dữ liệu endpoint | Transaction test không tự truyền qua HTTP tới server | Cleanup dữ liệu được tạo bởi request HTTP |
| @DirtiesContext xóa mọi dữ liệu test | Nó loại Spring context khỏi cache | Cleanup database, queue, file và resource ngoài context riêng |
| Assertion status 200 chứng minh response body đúng | Status chỉ xác nhận mã HTTP | Kiểm tra thêm content type, header và body theo contract |
| assertTimeoutPreemptively an toàn với mọi Spring test | Nó chạy code ở thread khác và có thể làm lệch ThreadLocal context | Cẩn thận với transaction, security và request context gắn với thread |

### Lưu ý về assertTimeout và assertTimeoutPreemptively

JUnit có hai dạng timeout thường gặp. **assertTimeout(...)** đo thời gian thực thi nhưng chạy đoạn code trên thread hiện tại; nếu quá hạn, assertion thất bại sau khi đoạn code kết thúc. **assertTimeoutPreemptively(...)** chạy đoạn code trên thread khác để có thể dừng sớm khi quá hạn.

Trong test dùng Spring transaction, security context hoặc request context dựa vào ThreadLocal, chạy đoạn code trên thread khác có thể làm code không nhìn thấy context mà Spring đã thiết lập cho test method. Không nên dùng preemptive timeout một cách máy móc quanh đoạn code phụ thuộc thread-bound context. Dùng timeout phù hợp ở tầng HTTP client, Reactor hoặc test framework theo yêu cầu cụ thể.

## 19. Một cấu trúc test dễ đọc

Một test tốt thường có ba phần:

1. **Arrange:** chuẩn bị context, fixture, mock và dữ liệu đầu vào.
2. **Act:** gọi service hoặc gửi request qua MockMvc/WebTestClient.
3. **Assert:** kiểm tra kết quả bằng assertion phù hợp và verify tương tác cần thiết.

Ví dụ service test:

~~~java
@Test
void shouldCalculateTheOrderTotal() {
    // Arrange
    List<OrderLine> lines = List.of(
            new OrderLine("book", new BigDecimal("20.00"), 2),
            new OrderLine("pen", new BigDecimal("5.00"), 1)
    );

    // Act
    BigDecimal total = calculator.total(lines);

    // Assert
    assertThat(total).isEqualByComparingTo("45.00");
}
~~~

Ví dụ HTTP test:

~~~java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customerId": "C-42",
                          "items": [{"sku": "book", "quantity": 1}]
                        }
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andExpect(jsonPath("$.status").value("PENDING"));
~~~

Arrange/Act/Assert không phải quy tắc bắt buộc của Spring. Đây là cách tổ chức giúp người đọc nhận ra test đang chuẩn bị gì, gọi hành vi nào và xác nhận điều gì.

## 20. Tổng hợp ranh giới trách nhiệm

| Thành phần | Cung cấp gì? | Không nên kỳ vọng gì? |
|---|---|---|
| JUnit Jupiter | Test engine, lifecycle, parameterized test, assertions cơ bản | Không tự nạp Spring context nếu không tích hợp extension |
| Spring Test | TestContext, SpringExtension, mock web API, MockMvc, WebTestClient, transaction test support và utilities | Không thay thế test runner hoặc mọi assertion library |
| Spring Boot Test | Boot application context test, slice test và auto-configuration cho test | Không phải toàn bộ API thuộc Spring Framework |
| AssertJ / Hamcrest | Cách diễn đạt điều kiện và so sánh kết quả | Không khởi động ứng dụng hoặc inject Spring bean |
| Mockito | Tạo mock, stub dependency và verify tương tác | Không thay thế assertion trên response hoặc domain value |
| JSONPath / JSONAssert | Truy vấn và so sánh cấu trúc JSON | Không kiểm tra toàn bộ HTTP transport |
| Reactor Test | Kiểm tra signal và thời gian của Mono/Flux | Không thay thế HTTP server integration test |
| Awaitility | Chờ điều kiện bất đồng bộ đạt được trong thời hạn | Không làm cho một tác vụ không có điều kiện kết thúc trở nên an toàn |

Khi thiết kế test suite, hãy chọn từng thành phần theo trách nhiệm: Spring Test chuẩn bị và tích hợp môi trường Spring; JUnit điều phối test; assertion library kiểm tra kết quả; mock framework xác nhận tương tác; công cụ chuyên biệt kiểm tra JSON hoặc reactive stream. Phân chia rõ vai trò giúp dependency gọn hơn và làm cho lỗi test dễ xác định hơn.

