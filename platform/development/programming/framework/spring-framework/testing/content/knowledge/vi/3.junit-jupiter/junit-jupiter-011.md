# Extension và cách SpringExtension tham gia vòng đời

JUnit Jupiter mở rộng vòng đời kiểm thử thông qua cơ chế *Extension*. Một extension có thể tham gia vào những thời điểm xác định trước, trong và sau khi test chạy. Cơ chế này cho phép tích hợp framework, quản lý tài nguyên, bổ sung dữ liệu cho test hoặc tùy chỉnh cách thực thi mà không cần thay đổi engine của JUnit.

Trong Spring Framework Testing, `SpringExtension` là cầu nối giữa JUnit Jupiter và Spring TestContext Framework. Nó nhận các callback từ JUnit, chuyển tiếp những sự kiện vòng đời tương ứng đến `TestContextManager`, đồng thời hỗ trợ đưa dependency từ Spring `ApplicationContext` vào test instance và các tham số kiểm thử. Nhờ đó, một bài test JUnit Jupiter có thể sử dụng Spring context, bean, dependency injection và các tính năng kiểm thử của Spring.

## 1. Extension trong JUnit Jupiter là gì?

Trong JUnit Jupiter, `Extension` là cơ chế mở rộng do JUnit cung cấp. Thay vì yêu cầu một runner riêng điều khiển toàn bộ test class, JUnit cho phép đăng ký một hoặc nhiều extension. Mỗi extension có thể triển khai một hoặc nhiều extension API để tham gia vào một phần của vòng đời.

Các extension API thường gặp gồm:

| Extension API | Vai trò |
|---|---|
| `BeforeAllCallback` | Tham gia trước khi các test method trong class bắt đầu |
| `AfterAllCallback` | Tham gia sau khi các test method trong class kết thúc |
| `TestInstancePostProcessor` | Xử lý test instance sau khi JUnit tạo instance |
| `BeforeEachCallback` | Tham gia trước mỗi test method |
| `BeforeTestExecutionCallback` | Tham gia ngay trước khi test method được thực thi |
| `AfterTestExecutionCallback` | Tham gia ngay sau khi test method kết thúc |
| `AfterEachCallback` | Tham gia sau mỗi test method |
| `ParameterResolver` | Cung cấp giá trị cho tham số constructor hoặc method mà extension hỗ trợ |

Một extension có thể triển khai nhiều interface. JUnit gọi đúng callback tại thời điểm tương ứng và cung cấp `ExtensionContext` để extension truy cập thông tin về test đang chạy.

Extension không nhất thiết phải biết toàn bộ cấu trúc của test engine. Nó chỉ đăng ký vào những điểm mở rộng cần thiết. Điều này giúp các tích hợp như Spring, Mockito hoặc các extension do dự án tự viết có thể phối hợp với JUnit Jupiter.

## 2. SpringExtension làm nhiệm vụ gì?

`SpringExtension` nằm trong module `spring-test` của Spring Framework. Nó triển khai các extension API của JUnit Jupiter và kết nối chúng với Spring TestContext Framework.

Có thể hình dung mối quan hệ như sau:

```text
JUnit Jupiter
     |
     | gọi extension callbacks
     v
SpringExtension
     |
     | chuyển tiếp sự kiện
     v
TestContextManager
     |
     +---- TestContext
     |
     +---- TestExecutionListeners
     |
     v
Spring ApplicationContext
     |
     +---- Spring beans
     +---- dependency injection
     +---- test context và tài nguyên liên quan
```

Vai trò của từng thành phần:

- **JUnit Jupiter** quản lý việc khám phá và thực thi test, tạo test instance và gọi extension callbacks.
- **SpringExtension** nhận các callback của JUnit và thích nghi chúng với vòng đời kiểm thử của Spring.
- **TestContextManager** điều phối quá trình chuẩn bị test instance và các sự kiện trước/sau test class, test method, test execution.
- **TestContext** giữ ngữ cảnh của một lần kiểm thử, bao gồm thông tin về test class, method và application context liên quan.
- **TestExecutionListener** thực hiện những hành vi cụ thể trong vòng đời Spring test, chẳng hạn dependency injection, quản lý transaction hoặc xử lý các annotation kiểm thử.
- **ApplicationContext** chứa các bean và cấu hình Spring được nạp cho bài kiểm thử.

SpringExtension không tự định nghĩa cấu hình ứng dụng. Test vẫn cần khai báo cấu hình Spring phù hợp, chẳng hạn `@ContextConfiguration`, `@SpringJUnitConfig`, `@SpringBootTest` hoặc một test slice của Spring Boot.

## 3. Đăng ký SpringExtension với @ExtendWith

Cách trực tiếp để sử dụng SpringExtension là đặt `@ExtendWith(SpringExtension.class)` trên test class:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTest.TestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}
```

Ở ví dụ này:

1. `@ExtendWith(SpringExtension.class)` đăng ký SpringExtension với JUnit Jupiter.
2. `@ContextConfiguration` khai báo cấu hình dùng để tạo Spring test context.
3. Spring tạo `ApplicationContext` và đăng ký bean `GreetingService`.
4. SpringExtension phối hợp với TestContext Framework để đưa bean vào trường `greetingService` của test instance.
5. Khi test method chạy, test có thể gọi bean đã được inject.

Ví dụ giả định `GreetingService` là một lớp có phương thức `greet(String)` trả về lời chào. Các import và cấu hình được viết để thể hiện cơ chế tích hợp; dự án thực tế sẽ dùng các bean và cấu hình thuộc ứng dụng của mình.

Nếu chỉ đăng ký `SpringExtension` mà không cung cấp cấu hình context phù hợp, Spring không thể tự biết cần tạo những bean nào. Extension đảm nhiệm tích hợp vòng đời; cấu hình kiểm thử vẫn phải xác định nguồn tạo context.

## 4. Dùng @SpringJUnitConfig để viết ngắn gọn

Spring cung cấp annotation tổng hợp `@SpringJUnitConfig`. Annotation này kết hợp việc đăng ký `SpringExtension` với khai báo `@ContextConfiguration`.

Ví dụ tương đương:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(GreetingTest.TestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfig {

        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}
```

Dùng `@SpringJUnitConfig` giúp giảm số annotation phải khai báo khi test cần Spring context theo cách thông thường. Có thể truyền các lớp cấu hình hoặc cấu hình locations theo các thuộc tính mà `@ContextConfiguration` hỗ trợ.

Với ứng dụng Spring Boot, các annotation như `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` và các test slice tương ứng đã tích hợp SpringExtension. Khi dùng các annotation này, thông thường không cần đăng ký `@ExtendWith(SpringExtension.class)` thêm lần nữa.

## 5. SpringExtension tham gia những thời điểm nào?

SpringExtension ánh xạ các callback của JUnit Jupiter sang các sự kiện của `TestContextManager`. Các điểm chính gồm:

| Callback của JUnit Jupiter | Hành động được chuyển tiếp đến TestContextManager | Thời điểm trong vòng đời |
|---|---|---|
| `BeforeAllCallback` | `beforeTestClass()` | Trước các phương thức `@BeforeAll` |
| `TestInstancePostProcessor` | `prepareTestInstance()` | Sau khi JUnit tạo test instance |
| `BeforeEachCallback` | `beforeTestMethod()` | Trước các phương thức `@BeforeEach` |
| `BeforeTestExecutionCallback` | `beforeTestExecution()` | Sau `@BeforeEach`, ngay trước test method |
| `AfterTestExecutionCallback` | `afterTestExecution()` | Ngay sau test method, trước `@AfterEach` |
| `AfterEachCallback` | `afterTestMethod()` | Sau các phương thức `@AfterEach` |
| `AfterAllCallback` | `afterTestClass()` | Sau các phương thức `@AfterAll` |

Bảng này thể hiện các mốc callback chính. Mỗi sự kiện của TestContextManager có thể kích hoạt các TestExecutionListener đã được cấu hình để thực hiện hành vi tương ứng.

### Trước khi test instance được sử dụng

JUnit tạo test instance theo lifecycle của nó. Sau khi instance được tạo, JUnit gọi `TestInstancePostProcessor` đã đăng ký. SpringExtension chuyển sự kiện này thành `prepareTestInstance()` của TestContextManager.

Đây là giai đoạn Spring chuẩn bị test instance, ví dụ đưa các dependency được đánh dấu `@Autowired` vào trường của test class. Vì vậy, với field injection, dependency đã sẵn sàng trước khi các phương thức `@BeforeEach` và test method được gọi.

### Trước và sau từng test method

SpringExtension chuyển các callback trước/sau test method thành những sự kiện của Spring TestContext Framework. Các listener có thể sử dụng những mốc này để thiết lập trạng thái, quản lý transaction hoặc thực hiện hành vi được yêu cầu bởi annotation kiểm thử.

Đáng chú ý, `beforeTestMethod()` diễn ra trước các phương thức `@BeforeEach` của JUnit. Sự kiện `beforeTestExecution()` diễn ra sau `@BeforeEach` và ngay trước test method. Ở chiều ngược lại, `afterTestExecution()` diễn ra ngay sau test method, còn `afterTestMethod()` được gọi sau các phương thức `@AfterEach`.

Sự phân biệt này hữu ích khi cần hiểu một thao tác thuộc giai đoạn chuẩn bị test method hay thuộc khoảng thời gian thực thi chính test method.

### Trước và sau test class

SpringExtension cũng chuyển callback cấp class sang `beforeTestClass()` và `afterTestClass()`. Các sự kiện này cho phép Spring TestContext Framework và các listener thực hiện công việc ở phạm vi toàn bộ test class.

Không nên nhầm các callback cấp class với callback cho từng method. Một class có nhiều test method vẫn có nhiều chu kỳ before/after method, trong khi sự kiện cấp class được thực hiện theo vòng đời của class.

## 6. Quan hệ giữa callback của extension và @BeforeEach, @AfterEach

JUnit Jupiter có các phương thức lifecycle do người viết test khai báo, chẳng hạn `@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll`. Extension callbacks là các điểm tích hợp được gọi quanh những phương thức này.

Với một test method thông thường, có thể hình dung thứ tự chính như sau:

```text
JUnit tạo test instance
        |
        v
SpringExtension
  prepareTestInstance()
        |
        v
SpringExtension
  beforeEach()
        |
        v
TestContextManager
  beforeTestMethod()
        |
        v
JUnit @BeforeEach
        |
        v
SpringExtension
  beforeTestExecution()
        |
        v
TestContextManager
  beforeTestExecution()
        |
        v
JUnit @Test
        |
        v
SpringExtension
  afterTestExecution()
        |
        v
TestContextManager
  afterTestExecution()
        |
        v
JUnit @AfterEach
        |
        v
SpringExtension
  afterEach()
        |
        v
TestContextManager
  afterTestMethod()
```

Thứ tự trên mô tả luồng tích hợp cơ bản khi SpringExtension được đăng ký. Nếu test class còn đăng ký extension khác, thứ tự callback giữa các extension có thể chịu ảnh hưởng bởi thứ tự đăng ký và quy tắc của JUnit. Khi cần phối hợp nhiều extension, hãy xác định rõ thứ tự thay vì dựa vào giả định rằng mọi callback đều chạy theo một thứ tự tùy ý.

Ví dụ, field `@Autowired` được chuẩn bị trong giai đoạn `prepareTestInstance()`, do đó có thể sử dụng trong `@BeforeEach`:

```java
@SpringJUnitConfig(TestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    private String input;

    @BeforeEach
    void setUp() {
        input = "Lan";
        // greetingService đã được Spring inject
    }

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet(input));
    }
}
```

Nếu dependency chưa được inject như mong đợi, cần kiểm tra cấu hình Spring, annotation đăng ký extension và quá trình chuẩn bị test instance. Không nên cố khắc phục bằng cách gọi thủ công một callback của SpringExtension.

## 7. Dependency injection cho test instance

Một trong những lợi ích rõ ràng nhất của SpringExtension là hỗ trợ dependency injection vào chính test class. Spring TestContext Framework thực hiện việc chuẩn bị thông qua các TestExecutionListener phù hợp.

Ví dụ field injection:

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsAccount() {
        Account account = accountService.findById("ACC-01");

        assertEquals("ACC-01", account.getId());
    }
}
```

Trường `accountService` được Spring inject trước khi test method thực thi. Test không cần tự khởi tạo service hoặc tự nối các dependency của nó.

### Injection vào tham số của test method

SpringExtension cũng triển khai `ParameterResolver`. Vì vậy, Spring có thể cung cấp dependency cho tham số method khi tham số đó thuộc loại mà SpringExtension hỗ trợ, thường được đánh dấu bằng annotation injection phù hợp như `@Autowired`, `@Qualifier` hoặc `@Value`.

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Test
    void loadsAccount(@Autowired AccountService accountService) {
        Account account = accountService.findById("ACC-01");

        assertEquals("ACC-01", account.getId());
    }
}
```

Cách này có thể giúp dependency chỉ xuất hiện tại test method cần dùng, thay vì lưu thành field của cả class.

JUnit Jupiter cũng có các parameter resolver riêng cho những tham số như `TestInfo` hoặc `TestReporter`. Các resolver phối hợp thông qua cơ chế extension của JUnit. SpringExtension chỉ giải quyết những tham số mà nó xác định là có thể hỗ trợ; nó không tự động nhận mọi tham số bất kỳ.

### Constructor injection cho test class

Nếu muốn inject dependency qua constructor của test class, cần cấu hình chế độ autowire constructor của Spring TestContext Framework. Có thể dùng `@TestConstructor` để khai báo rõ chế độ:

```java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class AccountServiceTest {

    private final AccountService accountService;

    AccountServiceTest(AccountService accountService) {
        this.accountService = accountService;
    }

    @Test
    void loadsAccount() {
        assertEquals(
                "ACC-01",
                accountService.findById("ACC-01").getId()
        );
    }
}
```

Chế độ `ALL` yêu cầu Spring autowire tất cả tham số constructor. Dự án cũng có thể cấu hình chế độ mặc định bằng thuộc tính tương ứng của Spring Test. Khi constructor injection không được bật theo cấu hình hiện hành, JUnit hoặc Spring có thể không giải quyết được tham số như mong muốn.

Constructor injection giúp thể hiện dependency bắt buộc ngay tại cấu trúc class. Field hoặc method parameter injection có thể phù hợp hơn khi test cần cách tổ chức đơn giản hoặc dependency chỉ phục vụ một số method.

## 8. SpringExtension và TestExecutionListener

SpringExtension là lớp tích hợp giữa JUnit Jupiter và Spring TestContext Framework. Nhiều hành vi kiểm thử cụ thể được thực hiện bởi `TestExecutionListener`, không phải bởi từng dòng callback trong test class.

Một số ví dụ về công việc thuộc TestContext Framework và listener:

- Inject dependency vào test instance.
- Quản lý transaction dành cho test khi dùng cấu hình phù hợp.
- Xử lý các annotation kiểm thử như `@Sql` hoặc `@DirtiesContext`.
- Thực hiện các hành động trước/sau test method theo chính sách kiểm thử.
- Chuẩn bị và dọn dẹp trạng thái test theo những listener được đăng ký.

Điều này tạo ra ranh giới rõ ràng: JUnit điều khiển vòng đời test, SpringExtension chuyển tiếp các mốc vòng đời, còn TestContextManager và listener điều phối các tính năng Spring Testing.

Khi một tính năng Spring không hoạt động như kỳ vọng, hãy xem annotation có được khai báo đúng, listener tương ứng có tham gia và application context có cấu hình phù hợp hay không. Không nên cho rằng chỉ cần `@ExtendWith(SpringExtension.class)` là mọi tính năng Spring Testing đều tự động được kích hoạt mà không cần annotation hoặc cấu hình bổ sung.

## 9. SpringExtension phối hợp với Spring Boot Test

Trong ứng dụng Spring Boot, các annotation kiểm thử thường đã đăng ký SpringExtension và cung cấp bootstrapper để xây dựng application context theo cách của Spring Boot.

Ví dụ với `@SpringBootTest`:

```java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

Với test slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    // Test các hành vi MVC tại đây
}
```

Các annotation như `@SpringBootTest` và `@WebMvcTest` đảm nhận việc chọn kiểu context hoặc phạm vi thành phần cần nạp. SpringExtension đảm nhận tích hợp các sự kiện vòng đời của JUnit với Spring TestContext Framework. Đây là hai trách nhiệm liên quan nhưng khác nhau.

Với test slice, chỉ một phần cấu hình ứng dụng được nạp theo mục tiêu của slice. Nếu controller cần service mà slice không tự cung cấp, test có thể phải khai báo mock bean hoặc cấu hình phù hợp. SpringExtension không tự mở rộng slice để nạp mọi thành phần còn thiếu.

## 10. Context caching và vòng đời test

Spring TestContext Framework có cơ chế cache `ApplicationContext` dựa trên cấu hình kiểm thử. Khi nhiều test class dùng cùng cấu hình tương đương, Spring có thể tái sử dụng context đã tạo thay vì khởi động lại toàn bộ context cho từng test.

SpringExtension lấy và sử dụng TestContextManager gắn với test class; TestContext Framework quản lý việc truy cập context và cache. Điều này giúp giảm chi phí khởi tạo khi chạy nhiều bài kiểm thử Spring.

Tuy nhiên, việc tái sử dụng context có nghĩa các bean singleton trong context có thể tồn tại qua nhiều test method hoặc test class dùng chung context. Không nên để trạng thái mutable trong bean dùng chung bị thay đổi tùy tiện bởi test, trừ khi trạng thái đó được kiểm soát và dọn dẹp rõ ràng.

Annotation `@DirtiesContext` có thể đánh dấu context cần loại khỏi cache sau khi test làm thay đổi trạng thái context theo cách không thể khôi phục. Không nên dùng annotation này một cách mặc định cho mọi test vì việc tạo lại context có thể làm suite chạy chậm đáng kể.

Cũng cần phân biệt context caching với fixture dữ liệu của test. Cache giúp tái sử dụng ApplicationContext; nó không tự bảo đảm dữ liệu database hoặc trạng thái nghiệp vụ được làm sạch giữa các test. Fixture và chiến lược transaction/cleanup vẫn phải được thiết kế phù hợp.

## 11. Phân biệt SpringExtension với SpringRunner

Trong JUnit 4, Spring cung cấp `SpringRunner` (cũng có thể gặp tên `SpringJUnit4ClassRunner`) để tích hợp Spring TestContext Framework với cơ chế runner của JUnit 4.

Trong JUnit Jupiter, cơ chế mở rộng là `Extension`, vì vậy lớp tương ứng là `SpringExtension`.

| JUnit 4 | JUnit Jupiter |
|---|---|
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` |
| Runner tích hợp với JUnit 4 | Extension tích hợp với JUnit Jupiter |
| Vòng đời theo mô hình runner | Vòng đời theo callback và extension API |

Không dùng `@RunWith(SpringRunner.class)` để đăng ký tích hợp Spring cho một test class đang chạy bằng JUnit Jupiter. Với JUnit Jupiter, hãy dùng `@ExtendWith(SpringExtension.class)`, `@SpringJUnitConfig` hoặc annotation kiểm thử Spring Boot phù hợp.

## 12. Những lỗi thường gặp khi cấu hình SpringExtension

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Dependency trong test field là null | SpringExtension chưa được đăng ký hoặc test context không được cấu hình đúng | Kiểm tra `@ExtendWith`, `@SpringJUnitConfig` hoặc annotation Spring Boot |
| Không tạo được ApplicationContext | Thiếu cấu hình, bean không hợp lệ hoặc cấu hình môi trường sai | Đọc nguyên nhân gốc trong lỗi context loading và kiểm tra `@ContextConfiguration` |
| Tham số test method không được resolve | Tham số không thuộc loại SpringExtension hỗ trợ hoặc thiếu annotation injection | Kiểm tra `@Autowired`, `@Qualifier`, `@Value` và kiểu tham số |
| Constructor test không được inject | Chế độ constructor autowiring chưa được bật | Kiểm tra `@TestConstructor` hoặc thuộc tính cấu hình tương ứng |
| Test slice thiếu bean | Slice chỉ nạp một phạm vi thành phần nhất định | Khai báo mock hoặc cấu hình cần thiết cho slice |
| Trạng thái bean ảnh hưởng test khác | Context/bean được tái sử dụng và có trạng thái mutable | Làm test độc lập, reset trạng thái hoặc chọn chiến lược context phù hợp |
| Test JUnit 4 và Jupiter dùng nhầm annotation | Nhầm runner với extension | Dùng annotation đúng theo test engine |

Khi chẩn đoán, hãy tách ba câu hỏi: JUnit có thực sự chạy test bằng Jupiter không; SpringExtension có được đăng ký không; và Spring TestContext Framework có đủ cấu hình để tạo context và chuẩn bị test instance không. Ba điều kiện này liên quan với nhau nhưng không thể thay thế cho nhau.

## 13. Khi nào cần tự viết extension và khi nào dùng SpringExtension?

SpringExtension đã cung cấp tích hợp vòng đời cần thiết cho các bài kiểm thử dùng Spring TestContext Framework. Phần lớn test ứng dụng chỉ cần đăng ký extension thông qua annotation có sẵn.

Một extension tự viết có thể phù hợp khi dự án muốn bổ sung hành vi dùng chung cho test, chẳng hạn tạo dữ liệu theo một quy ước, ghi nhận metadata hoặc thiết lập tài nguyên kiểm thử. Extension nên triển khai đúng callback mà hành vi đó cần và có trách nhiệm dọn dẹp tài nguyên tương ứng.

Không nên tự viết extension để thay thế SpringExtension hoặc tự gọi các phương thức nội bộ của TestContextManager nếu mục tiêu chỉ là inject bean hay khởi tạo Spring context. Những chức năng đó đã được Spring TestContext Framework cung cấp.

Nếu dự án cần extension riêng phối hợp với SpringExtension, hãy hiểu rõ thứ tự đăng ký và thời điểm callback. Tránh để hai extension cùng thay đổi một trạng thái mà không có quy tắc phối hợp rõ ràng.

## 14. Cách lần theo vòng đời khi debug

Khi cần hiểu SpringExtension đang làm gì, có thể lần theo các mốc sau:

1. **Xác định test engine:** kiểm tra test đang chạy bằng JUnit Jupiter.
2. **Xác định extension registration:** tìm `@ExtendWith(SpringExtension.class)`, `@SpringJUnitConfig` hoặc annotation Spring Boot có tích hợp extension.
3. **Xác định nguồn cấu hình context:** đọc `@ContextConfiguration`, `@SpringBootTest`, test slice hoặc cấu hình bootstrap tương ứng.
4. **Kiểm tra test instance:** xác định field injection, method parameter hoặc constructor parameter được cấu hình ra sao.
5. **Theo dõi callback:** xác định lỗi xảy ra trong giai đoạn chuẩn bị instance, trước method, trước execution, sau execution hay sau method.
6. **Đọc listener và nguyên nhân gốc:** nếu lỗi đến từ Spring TestContext, xem listener hoặc cấu hình context liên quan thay vì chỉ nhìn dòng test method.
7. **Kiểm tra trạng thái dùng chung:** nếu test thất bại tùy thứ tự chạy, xem bean singleton, cache context, transaction và dữ liệu fixture.

Hiểu các mốc này giúp phân biệt lỗi trong chính logic được kiểm tra với lỗi xảy ra trong quá trình khởi tạo hoặc quản lý test context.

SpringExtension là adapter đưa Spring TestContext Framework vào vòng đời của JUnit Jupiter. Khi nắm được cách extension được đăng ký, callback được ánh xạ và dependency được chuẩn bị, người phát triển có thể sử dụng Spring bean trong test một cách có chủ đích, chọn đúng annotation kiểm thử và chẩn đoán rõ hơn các lỗi phát sinh quanh vòng đời test.

