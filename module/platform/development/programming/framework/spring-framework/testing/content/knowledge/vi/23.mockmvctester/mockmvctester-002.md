# Khởi tạo MockMvcTester từ controller hoặc MockMvc có sẵn

`MockMvcTester` là API kiểm thử Spring MVC theo phong cách AssertJ, được giới thiệu trong Spring Framework 6.2. Nó sử dụng `MockMvc` ở bên dưới để chạy request qua `DispatcherServlet` với Servlet request/response giả lập, không cần khởi động HTTP server thật.

Có hai điểm khởi tạo chính tương ứng với hai tình huống:

- `MockMvcTester.of(...)`: đưa trực tiếp controller vào tester để dựng cấu hình MVC standalone.
- `MockMvcTester.create(mockMvc)`: bọc một `MockMvc` đã được tạo và cấu hình từ trước.

Ngoài ra, khi đang có `WebApplicationContext`, có thể dùng `MockMvcTester.from(...)` để tester tự tạo `MockMvc` từ application context. Bài này tập trung vào khởi tạo từ controller và từ `MockMvc` có sẵn, đồng thời đặt hai cách đó vào đúng ngữ cảnh sử dụng.

## 1. Điều kiện sử dụng

`MockMvcTester` có từ Spring Framework 6.2 và nằm trong package:

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
```

Tester dùng AssertJ để viết assertion, vì vậy cần có AssertJ trong test classpath. Nếu dùng Spring Boot 3.4 trở lên, `spring-boot-starter-test` thường đã cung cấp các thư viện test cần thiết, bao gồm AssertJ. Với dự án Spring Framework thuần, cần khai báo `spring-test` và `assertj-core` trong dependency test, đồng thời quản lý version tương thích qua BOM hoặc dependency management của dự án.

Ví dụ Gradle khi dự án tự quản lý version:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
}
```

Các ví dụ dùng JUnit Jupiter. Với Spring Framework trước 6.2, `MockMvcTester` chưa có; có thể tiếp tục dùng `MockMvc` cùng `MockMvcResultMatchers` hoặc nâng cấp Spring Framework.

## 2. Khởi tạo trực tiếp từ controller bằng of(...)

Khi chỉ muốn kiểm thử một hoặc một vài controller với cấu hình MVC tối thiểu, dùng `MockMvcTester.of(...)`:

```java
MockMvcTester mvc = MockMvcTester.of(new GreetingController());
```

Phương thức này tạo cấu hình standalone tương tự `MockMvcBuilders.standaloneSetup(...)`. Spring dựng phần hạ tầng MVC tối thiểu cần thiết để `DispatcherServlet` phục vụ annotated controller. Không cần tạo `MockMvc` riêng trước.

Ví dụ controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    String greeting(@RequestParam(defaultValue = "World") String name) {
        return "Hello, " + name;
    }
}
```

Test khởi tạo tester và gửi request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingControllerTests {

    private final MockMvcTester mvc =
            MockMvcTester.of(new GreetingController());

    @Test
    void returnsGreeting() {
        assertThat(mvc.get().uri("/greeting").param("name", "Ada"))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello, Ada");
    }
}
```

`mvc.get()` tạo request GET theo API của tester; `.uri(...)` đặt đường dẫn; `.param(...)` bổ sung query parameter. `assertThat(...)` bọc kết quả request để gọi các assertion AssertJ như `hasStatusOk()` và `hasBodyTextEqualTo(...)`.

### Truyền controller instance hay class?

`of(Object... controllers)` chấp nhận một hoặc nhiều controller instance; API cũng cho phép truyền controller type (`Class`) để Spring tạo instance. Ví dụ:

```java
MockMvcTester mvc = MockMvcTester.of(
        new GreetingController(),
        new HealthController());
```

Khi controller có dependency, thường nên tạo instance và truyền dependency tường minh:

```java
GreetingService service = name -> "Welcome, " + name;
GreetingController controller = new GreetingController(service);
MockMvcTester mvc = MockMvcTester.of(controller);
```

Cách này làm rõ dependency của controller và không phụ thuộc vào component scanning hay dependency injection của application context. Nếu truyền class để Spring tự tạo instance, không nên giả định các dependency của ứng dụng sẽ tự được inject như khi controller được quản lý bởi container.

## 3. Tùy chỉnh cấu hình khi khởi tạo từ controller

`of(Object... controllers)` chỉ tạo hạ tầng MVC tối thiểu. Nếu cần controller advice, filter, converter, argument resolver hoặc cấu hình MVC khác, dùng overload nhận collection controller và hàm tùy chỉnh builder:

```java
MockMvcTester mvc = MockMvcTester.of(
        List.of(new GreetingController()),
        builder -> builder
                .setControllerAdvice(new ApiExceptionHandler())
                .addFilters(new RequestAuditFilter())
                .build());
```

Hàm tùy chỉnh nhận `StandaloneMockMvcBuilder` và phải trả về `MockMvc` bằng `.build()`. Điều này tương đương với việc cấu hình `MockMvcBuilders.standaloneSetup(...)` trước, sau đó truyền MockMvc đã dựng cho tester.

Ví dụ khi muốn đăng ký converter cụ thể hoặc validator:

```java
MockMvcTester mvc = MockMvcTester.of(
        List.of(controller),
        builder -> builder
                .setValidator(validator)
                .setControllerAdvice(exceptionHandler)
                .build());
```

Chỉ thêm các thành phần mà kịch bản test cần. Cấu hình standalone không tự nạp toàn bộ Spring MVC configuration của ứng dụng, do đó các cấu hình như interceptor, formatter, converter tùy chỉnh hoặc security filter chain cần được đăng ký rõ ràng nếu test phụ thuộc vào chúng.

## 4. Khởi tạo từ MockMvc đã có bằng create(...)

Nếu dự án đã dựng `MockMvc` và muốn chuyển sang API AssertJ, dùng `MockMvcTester.create(mockMvc)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(new RequestAuditFilter())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

`create(...)` tạo tester ủy quyền request cho đúng `MockMvc` được truyền vào. Nó không tự dựng lại controller hoặc thay thế cấu hình của MockMvc. Những thiết lập đã có như filter, interceptor, controller advice, message converter và exception resolver tiếp tục thuộc về instance MockMvc đó.

Điều này hữu ích khi:

- Test suite đã có helper hoặc fixture tạo MockMvc.
- MockMvc được cấu hình bằng `webAppContextSetup(...)` hoặc `standaloneSetup(...)` với nhiều tùy chỉnh.
- Một số test cũ dùng MockMvc và muốn dùng AssertJ trong test mới.
- MockMvc được cung cấp bởi Spring Boot test configuration hoặc được inject vào test class.

Ví dụ đầy đủ với MockMvc đã cấu hình:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;

class ExistingMockMvcTests {

    private MockMvc mockMvc;
    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .build();
        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void reusesExistingMockMvc() {
        assertThat(mvc.get().uri("/greeting"))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello, World");
    }
}
```

Trong ví dụ, việc tạo `MockMvc` và việc tạo `MockMvcTester` là hai bước riêng. Nếu `mockMvc` đã được tạo ở nơi khác, chỉ cần gọi `create(mockMvc)`; không phải dựng lại.

## 5. Khi có WebApplicationContext: from(...)

`MockMvcTester.from(applicationContext)` là lựa chọn thuận tiện khi muốn tester tự dựng MockMvc từ một `WebApplicationContext` đã được refresh:

```java
@SpringJUnitConfig(WebConfig.class)
class WebLayerTests {

    @Autowired
    private WebApplicationContext applicationContext;

    @Test
    void usesApplicationMvcConfiguration() {
        MockMvcTester mvc = MockMvcTester.from(applicationContext);

        assertThat(mvc.get().uri("/greeting"))
                .hasStatusOk();
    }
}
```

`from(...)` đọc cấu hình Spring MVC và controller từ application context. Nếu cần tùy chỉnh builder trước khi tạo MockMvc, có overload nhận function:

```java
MockMvcTester mvc = MockMvcTester.from(
        applicationContext,
        builder -> builder.addFilters(new RequestAuditFilter()).build());
```

Phân biệt ba factory method:

| Phương thức | Đầu vào | Ai tạo MockMvc? | Trường hợp dùng |
|---|---|---|---|
| `of(controllers...)` | Controller instance hoặc type | `MockMvcTester` dựng standalone MockMvc | Test controller với hạ tầng MVC tối thiểu |
| `create(mockMvc)` | MockMvc đã tồn tại | Bạn hoặc test configuration đã tạo MockMvc | Tái sử dụng cấu hình MockMvc có sẵn |
| `from(applicationContext)` | WebApplicationContext đã refresh | `MockMvcTester` dựng MockMvc từ context | Test với cấu hình Spring MVC trong application context |

## 6. Dùng MockMvcTester trong Spring Boot test

Trong Spring Boot, nếu đã dùng `@AutoConfigureMockMvc`, có thể inject `MockMvc` rồi bọc nó:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() {
        MockMvcTester mvc = MockMvcTester.create(mockMvc);

        assertThat(mvc.get().uri("/api/orders/42"))
                .hasStatusOk();
    }
}
```

Đây là cách phù hợp khi muốn giữ nguyên cấu hình MockMvc do Spring Boot tạo, bao gồm các filter và thành phần web được đăng ký trong test context. Nếu dự án và phiên bản Spring Boot tự cấu hình sẵn `MockMvcTester`, có thể inject tester trực tiếp theo cấu hình đó; còn ví dụ trên cho thấy cách chuyển đổi rõ ràng từ một MockMvc đang có.

## 7. Thực hiện request và viết assertion

Sau khi khởi tạo tester theo một trong các cách trên, API gửi request có thể dùng builder của `MockMvcTester`:

```java
assertThat(mvc.get().uri("/api/orders/42"))
        .hasStatusOk();

assertThat(mvc.post().uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}"))
        .hasStatus(HttpStatus.CREATED);
```

Có thể dùng `exchange()` khi cần giữ kết quả và thực hiện nhiều assertion riêng:

```java
MvcTestResult result = mvc.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}")
        .exchange();

assertThat(result).hasStatus(HttpStatus.CREATED);
assertThat(result).body().isNotEmpty();
```

`MockMvcTester` cũng hỗ trợ cách dùng request builder tĩnh giống MockMvc, phù hợp khi đã có custom `RequestBuilder`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

assertThat(mvc.perform(get("/greeting")))
        .hasStatusOk()
        .hasBodyTextEqualTo("Hello, World");
```

Với trường hợp thông thường, nên dùng request builder của tester như `mvc.get().uri(...)`. Khi dùng `perform(RequestBuilder)`, tester nhận request builder đã tạo sẵn và thực thi nó; luồng này không tự xử lý thêm async request như API builder chuyên dụng của tester.

## 8. Chọn cách khởi tạo nào?

Chọn `of(...)` khi test tập trung vào controller cụ thể, muốn tạo dependency tường minh và không cần nạp toàn bộ cấu hình ứng dụng. Cách này nhanh, rõ phạm vi và phù hợp với test controller độc lập.

Chọn `create(...)` khi MockMvc đã tồn tại và có cấu hình mà test cần giữ nguyên. Đây là lựa chọn tự nhiên khi chuyển dần từ assertion kiểu `MockMvcResultMatchers` sang AssertJ.

Chọn `from(...)` khi muốn dùng application context đã khởi tạo và để tester tạo MockMvc từ cấu hình MVC thật. Nếu cần giữ một MockMvc được cấu hình đặc biệt từ trước, tạo MockMvc bằng builder rồi bọc bằng `create(...)`.

Không nên dùng standalone test để kết luận rằng toàn bộ cấu hình MVC của ứng dụng đã hoạt động đúng. Nếu ứng dụng có cấu hình quan trọng như Spring Security, custom converter, interceptor hoặc controller advice được đăng ký trong context, cần có test tích hợp dùng context hoặc MockMvc được cấu hình tương ứng.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `MockMvcTester` | Spring Framework cũ hơn 6.2 hoặc thiếu `spring-test` | Dùng Spring Framework 6.2+ và khai báo dependency test phù hợp |
| Không resolve được `assertThat` | Thiếu AssertJ trong test classpath | Thêm `assertj-core` hoặc dùng starter test có AssertJ |
| Controller không có dependency | Dùng `of(...)` như thể nó tạo application context và inject bean | Tạo controller instance với dependency tường minh hoặc dùng context-based setup |
| Filter hoặc advice không chạy | Dùng `of(controller)` với cấu hình standalone tối thiểu | Dùng overload tùy chỉnh, `from(context)` hoặc `create(mockMvc)` đã cấu hình đầy đủ |
| Cấu hình MockMvc bị mất khi chuyển sang tester | Dựng một MockMvc mới thay vì bọc instance cũ | Truyền đúng instance vào `MockMvcTester.create(mockMvc)` |
| JSON body không được chuyển đổi như mong muốn | Tester không có message converter phù hợp cho assertion body có cấu trúc | Cấu hình converter MVC hoặc dùng `withHttpMessageConverters(...)` phù hợp |
| Test không phản ánh security configuration | Standalone setup không đăng ký security filter chain | Dùng MockMvc từ context hoặc thêm security config/filter chain khi dựng standalone |

## 10. Ghi nhớ

`MockMvcTester.of(controller...)` tạo tester ở chế độ standalone từ controller; dùng overload tùy chỉnh khi cần cấu hình thêm MVC. `MockMvcTester.create(mockMvc)` bọc một MockMvc đã tồn tại và giữ nguyên cấu hình của instance đó. Nếu có `WebApplicationContext` và muốn tester tự tạo MockMvc từ context, dùng `MockMvcTester.from(context)`. Chọn factory method theo nguồn cấu hình mà test cần, rồi dùng builder của tester và AssertJ để thực hiện request và xác nhận kết quả.

