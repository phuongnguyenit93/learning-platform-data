# MockMvcTester và tích hợp AssertJ theo phiên bản Spring hỗ trợ

`MockMvc` là công cụ kiểm thử Spring MVC bằng request và response mô phỏng. Từ Spring Framework 6.2, Spring Test cung cấp thêm `MockMvcTester`, một API xây dựng trên MockMvc nhưng sử dụng phong cách assertion của AssertJ.

Với API truyền thống, test thường gọi `mockMvc.perform(...)` rồi nối các matcher qua `andExpect(...)`. Với `MockMvcTester`, test có thể tạo request bằng các phương thức như `get()` và xác nhận kết quả bằng `assertThat(...)`, ví dụ `hasStatusOk()`, `bodyText()` hoặc `bodyJson()`.

`MockMvcTester` giúp cách viết test thống nhất hơn với những test đang dùng AssertJ. Nó vẫn dùng hạ tầng MockMvc bên dưới, vì vậy request không đi qua socket HTTP và không khởi động Servlet container thật.

## 1. MockMvcTester là gì?

`MockMvcTester` thuộc module `spring-test`, trong package:

```java
org.springframework.test.web.servlet.assertj
```

Nó cung cấp một facade theo phong cách AssertJ cho các request được thực thi bằng MockMvc. Test vẫn kiểm tra các thành phần Spring MVC như `DispatcherServlet`, handler mapping, controller, argument resolver, message converter, exception resolver và các filter đã được đăng ký trong môi trường test.

Điểm thay đổi chính nằm ở cách tạo request và xác nhận kết quả:

```java
// API MockMvc truyền thống
mockMvc.perform(get("/greetings/Lan"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.message").value("Hello, Lan"));

// API MockMvcTester theo phong cách AssertJ
assertThat(mockMvcTester.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

Hai cách có thể kiểm tra cùng một request. `MockMvcTester` không thay thế MockMvc engine; nó cung cấp API tiện dụng hơn để diễn đạt request và assertion.

### MockMvcTester phù hợp với mục tiêu nào?

- Viết assertion theo phong cách AssertJ mà không phải nối nhiều `ResultMatcher`.
- Kiểm tra status HTTP bằng các assertion dễ đọc như `hasStatusOk()`.
- Kiểm tra response body dạng text hoặc JSON bằng các assertion chuyên biệt.
- Dùng cùng một phong cách assertion với unit test và integration test khác trong dự án.
- Tạo một API test MVC nhất quán khi nhóm phát triển đã sử dụng AssertJ rộng rãi.

Nếu dự án đã có nhiều test MockMvc truyền thống, không bắt buộc phải chuyển toàn bộ. Hai API có thể cùng tồn tại và lựa chọn phụ thuộc vào mức độ dễ đọc, tính nhất quán và nhu cầu của từng test.

## 2. Phiên bản Spring và dependency cần có

Khả năng sử dụng `MockMvcTester` phụ thuộc vào phiên bản Spring Test, không chỉ phụ thuộc vào việc dự án có AssertJ hay không.

| Thành phần | Điều kiện hỗ trợ |
| --- | --- |
| Spring Framework | `MockMvcTester` được giới thiệu từ Spring Framework 6.2 |
| Spring Boot | Spring Boot 3.4 trở lên quản lý Spring Framework 6.2 trở lên và có thể tự cấu hình `MockMvcTester` khi AssertJ có trên test classpath |
| AssertJ | Cần có AssertJ tương thích trên test classpath để dùng API assertion và để cơ chế auto-configuration của Boot nhận diện |
| Spring Test | Cần module `spring-test` tương ứng với phiên bản Spring Framework đang dùng |

Với Spring Boot, dependency `spring-boot-starter-test` thường cung cấp Spring Test, AssertJ và các thư viện kiểm thử phổ biến khác. Trong một dự án Spring Boot 3.4+, khi dùng `@WebMvcTest` hoặc `@AutoConfigureMockMvc` và AssertJ có mặt, có thể inject `MockMvcTester` do Boot cấu hình.

Ví dụ Gradle cho Spring Boot:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu dự án dùng Spring Framework trực tiếp, cần khai báo `spring-test` 6.2 trở lên và AssertJ ở scope test. Hãy dùng dependency management hoặc BOM để bảo đảm phiên bản `spring-test` tương thích với các module Spring khác:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

Đoạn cấu hình trên giả định phiên bản được quản lý bởi BOM hoặc dependency constraints của dự án. Nếu không dùng dependency management, phải khai báo phiên bản cụ thể tương thích cho từng thư viện.

### Nếu dự án đang dùng Spring Framework 6.1 hoặc Spring Boot 3.3 trở xuống

Các phiên bản Spring Framework trước 6.2 chưa có lớp `MockMvcTester`. Chỉ thêm `assertj-core` vào một dự án dùng Spring Test cũ không làm cho lớp này xuất hiện. Khi chưa thể nâng cấp Spring, tiếp tục dùng API MockMvc truyền thống.

Nếu muốn dùng `MockMvcTester`, hãy nâng Spring Boot hoặc Spring Framework theo một bộ phiên bản tương thích. Không nâng riêng `spring-test` lên 6.2 trong khi các module Spring khác vẫn ở một dòng cũ không tương thích.

## 3. Tạo MockMvcTester trong Spring Boot

Trong ứng dụng Spring Boot, có thể inject `MockMvcTester` trực tiếp khi Boot đã auto-configure MockMvc và AssertJ có trên classpath.

Ví dụ controller:

```java
@RestController
public class GreetingController {

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Collections.singletonMap("message", "Hello, " + name);
    }
}
```

Test dùng `@WebMvcTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void returnsGreetingAsJson() {
        assertThat(mvc.get().uri("/greetings/{name}", "Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

`@WebMvcTest` tạo một Spring MVC test slice. Boot cấu hình MockMvc và, khi các điều kiện cần thiết được đáp ứng, cung cấp bean `MockMvcTester`. Test không cần tự tạo `MockMvc` hoặc gọi `MockMvcTester.create(...)` trong trường hợp này.

Nếu controller phụ thuộc service hoặc bean khác không thuộc MVC slice, hãy cung cấp chúng bằng mock bean hoặc cấu hình test phù hợp với phiên bản Spring Boot đang dùng. `MockMvcTester` chỉ thay đổi API thực hiện request và assertion; nó không tự tạo các dependency nghiệp vụ còn thiếu.

### Dùng với toàn bộ application context

Nếu mục tiêu là kiểm tra nhiều tầng của ứng dụng cùng cấu hình thực tế, có thể dùng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApplicationMvcTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void servesConfiguredEndpoint() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

Test này nạp application context rộng hơn `@WebMvcTest`, nhưng vẫn sử dụng MockMvc. Nó không mở cổng mạng để nhận HTTP request thật.

## 4. Tạo MockMvcTester thủ công

Nếu không dùng Spring Boot auto-configuration, có thể tạo MockMvc trước rồi bọc nó bằng `MockMvcTester.create(...)`.

Ví dụ dùng standalone setup:

```java
class GreetingControllerStandaloneTest {

    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .build();

        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void returnsGreeting() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

`MockMvcTester.create(mockMvc)` dùng chính đối tượng MockMvc đã được cấu hình. Vì vậy, nếu MockMvc được tạo bằng `standaloneSetup`, test có phạm vi độc lập tương ứng. Nếu MockMvc được tạo bằng `webAppContextSetup`, tester sử dụng hạ tầng MVC của web application context đó.

Ví dụ dùng web application context:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcConfig.class)
class GreetingControllerContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void usesMvcConfigurationFromContext() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

Nếu Spring Security filter chain cần tham gia, hãy tích hợp security vào MockMvc trước khi tạo tester:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

`MockMvcTester` không tự thêm filter hoặc cấu hình bảo mật mà MockMvc ban đầu chưa có. Nó kế thừa phạm vi và hành vi của MockMvc được truyền vào.

## 5. Tạo request và xác nhận status

MockMvcTester cung cấp các phương thức tạo request theo HTTP method. Ví dụ:

```java
mvc.get().uri("/products");
mvc.post().uri("/products");
mvc.put().uri("/products/{id}", 12);
mvc.patch().uri("/products/{id}", 12);
mvc.delete().uri("/products/{id}", 12);
```

Các request builder cho phép cấu hình URI và các thuộc tính request cần thiết trước khi thực thi. Có thể dùng URI template với biến để tránh tự nối chuỗi đường dẫn.

Sau khi request được thực thi, dùng AssertJ để xác nhận status:

```java
assertThat(mvc.get().uri("/health"))
        .hasStatusOk();
```

Đối với endpoint trả về lỗi theo hợp đồng API, có thể kiểm tra status tương ứng và body lỗi bằng các assertion dành cho kết quả MockMvcTester. Cú pháp assertion cụ thể nên được tra theo Javadoc của đúng phiên bản Spring Test mà dự án đang dùng, vì API có thể mở rộng theo từng dòng phát hành.

### Kết hợp nhiều assertion

Các assertion có thể nối tiếp nhau để mô tả response mong đợi:

```java
assertThat(mvc.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

Đọc theo thứ tự: gửi GET, xác nhận HTTP 200, đọc response body dạng JSON, trích xuất trường `message`, rồi so sánh giá trị. Cách viết này tận dụng khả năng chain assertion của AssertJ.

## 6. Kiểm tra response body dạng text và JSON

MockMvcTester cung cấp các assertion body phù hợp với kiểu nội dung response.

### Body dạng text

Với endpoint trả chuỗi thuần:

```java
@RestController
class StatusController {

    @GetMapping(value = "/status-text", produces = MediaType.TEXT_PLAIN_VALUE)
    String statusText() {
        return "service-ready";
    }
}
```

Test:

```java
assertThat(mvc.get().uri("/status-text"))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("service-ready");
```

`bodyText()` trả về assertion dành cho nội dung dạng văn bản. Test có thể so sánh toàn bộ chuỗi hoặc sử dụng các assertion chuỗi của AssertJ như `contains`, `startsWith` và `isEqualTo`.

### Body dạng JSON

Với response JSON, `bodyJson()` cung cấp API assertion theo cấu trúc JSON. Có thể trích xuất một giá trị bằng JSONPath:

```java
assertThat(mvc.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

Với JSON có mảng hoặc object lồng nhau, JSONPath giúp kiểm tra trường cần quan tâm mà không phải so sánh toàn bộ chuỗi JSON theo thứ tự ký tự.

Ví dụ response:

```json
{
  "id": 12,
  "owner": {
    "username": "alice"
  },
  "tags": ["spring", "testing"]
}
```

Các biểu thức JSONPath có thể trỏ đến:

| Trường | JSONPath |
| --- | --- |
| ID | `$.id` |
| Username của owner | `$.owner.username` |
| Phần tử đầu tiên của tags | `$.tags[0]` |

Nếu cần xác nhận toàn bộ JSON, có thể dùng assertion JSON phù hợp của phiên bản Spring Test đang dùng. Khi chỉ cần kiểm tra một vài thuộc tính của response, `extractingPath(...)` thường làm test ít phụ thuộc vào thứ tự field và những dữ liệu không liên quan.

## 7. Dùng MockMvcTester với response lỗi

Một endpoint có thể trả lỗi thông qua `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseStatusException` hoặc resolver mặc định. MockMvcTester vẫn kiểm tra kết quả HTTP qua cùng luồng xử lý Spring MVC.

Ví dụ controller ném exception:

```java
@RestController
class OrderController {

    @GetMapping("/orders/{id}")
    Map<String, String> find(@PathVariable long id) {
        throw new OrderNotFoundException(id);
    }
}
```

Advice ánh xạ exception thành response:

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> handle(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

Test có thể tập trung vào status và nội dung lỗi:

```java
assertThat(mvc.get().uri("/orders/{id}", 77))
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.error")
        .isEqualTo("Order 77 was not found");
```

Ví dụ giả định `OrderNotFoundException` trả thông điệp `Order 77 was not found` và advice đã được đăng ký trong MVC context. Khi test một exception chưa được xử lý, cần phân biệt lỗi được Spring MVC ánh xạ thành response với lỗi thực sự thoát khỏi quá trình dispatch. API assertion dành cho failure và exception có thể khác theo phiên bản; hãy tham khảo Javadoc tương ứng nếu cần kiểm tra nguyên nhân gốc thay vì response.

## 8. Kết hợp MockMvcTester với Spring Security

MockMvcTester dùng MockMvc bên dưới, nên các postprocessor và filter đã tích hợp với MockMvc vẫn là nền tảng của test. Khi endpoint yêu cầu đăng nhập, cần cấu hình security filter chain và tạo trạng thái xác thực cho request.

Ví dụ với Spring Security Test:

```java
assertThat(mvc.get().uri("/profile")
        .with(user("alice").roles("USER")))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("alice");
```

Request postprocessor `user(...)` tạo Authentication cho người dùng mô phỏng. Nếu dùng `MockMvcTester` được Boot auto-configure, hãy bảo đảm cấu hình security thực sự được nạp và filter chain được gắn vào MockMvc. Nếu tự tạo MockMvc, dùng `.apply(springSecurity())` trước khi gọi `MockMvcTester.create(...)`.

Tương tự, có thể dùng các postprocessor phù hợp với HTTP Basic, JWT hoặc CSRF nếu dự án đã khai báo module Spring Security Test tương ứng. `MockMvcTester` không thay thế cơ chế thiết lập authentication; nó chỉ cung cấp một cách assertion khác trên kết quả MockMvc.

## 9. So sánh MockMvcTester và MockMvc truyền thống

| Tiêu chí | MockMvc truyền thống | MockMvcTester |
| --- | --- | --- |
| Cách thực thi | `mockMvc.perform(RequestBuilder)` | `mvc.get()`, `mvc.post()` hoặc request builder tương ứng |
| Assertion | `andExpect(ResultMatcher)` | AssertJ `assertThat(...)` và fluent assertions |
| Kiểm tra status | `status().isOk()` | `hasStatusOk()` |
| Kiểm tra JSON | `jsonPath(...)` | `bodyJson().extractingPath(...)` |
| Kiểm tra text | `content().string(...)` | `bodyText().isEqualTo(...)` |
| Hạ tầng bên dưới | Spring MVC Test | Spring MVC Test/MockMvc |
| Yêu cầu phiên bản | Có từ các dòng Spring cũ hơn | Spring Framework 6.2 trở lên |
| AssertJ | Không bắt buộc | Cần có trên classpath |
| Khởi chạy HTTP server thật | Không | Không |

MockMvc truyền thống có hệ sinh thái matcher phong phú và vẫn là API ổn định. MockMvcTester tạo trải nghiệm AssertJ tự nhiên hơn, đặc biệt khi nhóm đã quen với `assertThat`, `isEqualTo`, `contains` và các assertion chain.

Hai API không loại trừ nhau. Một dự án có thể giữ các test cũ dùng `MockMvc`, viết test mới bằng `MockMvcTester`, hoặc dùng trực tiếp `MockMvc` trong những trường hợp cần một matcher đặc thù chưa được biểu diễn thuận tiện bằng AssertJ.

## 10. Giới hạn của MockMvcTester

Tên mới và API fluent không làm thay đổi phạm vi kiểm thử của MockMvc. MockMvcTester vẫn dùng Servlet request/response mô phỏng trong tiến trình test.

Nó không xác nhận:

- Embedded Tomcat, Jetty hoặc Undertow có khởi động thành công hay không.
- Connector có mở cổng và nhận request qua TCP hay không.
- TLS, reverse proxy, load balancer hoặc network routing có hoạt động đúng không.
- WAR có deploy đúng trên Servlet container bên ngoài không.
- Cấu hình container như context path, session cookie, error page hoặc multipart limit có vận hành đúng trong production không.

Nếu cần kiểm tra HTTP thực, hãy dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc triển khai ứng dụng vào container mục tiêu rồi gửi request qua HTTP client. MockMvcTester phù hợp cho kiểm thử Spring MVC trong môi trường mock, còn kiểm thử server runtime cần một cấp test khác.

## 11. Các lỗi thường gặp khi áp dụng

### Lớp MockMvcTester không được tìm thấy

Nguyên nhân phổ biến là dự án đang dùng Spring Framework trước 6.2. Kiểm tra phiên bản Spring Test thực tế trên test classpath. Thêm AssertJ không thể bổ sung một lớp chưa tồn tại trong phiên bản Spring Test đó.

### Spring Boot không inject được MockMvcTester

Kiểm tra các điều kiện:

- Dự án đang dùng Spring Boot 3.4 trở lên hoặc phiên bản Boot mới hơn có hỗ trợ.
- `spring-boot-starter-test` hoặc dependency tương ứng cung cấp Spring Test và AssertJ.
- Test đã kích hoạt cấu hình MockMvc, chẳng hạn `@WebMvcTest` hoặc `@AutoConfigureMockMvc`.
- Auto-configuration không bị loại trừ hoặc thay thế theo cách làm bean không được tạo.

Nếu không dùng Boot auto-configuration, tạo `MockMvc` rồi gọi `MockMvcTester.create(mockMvc)`.

### Lệch phiên bản Spring Test và Spring Framework

Không trộn `spring-test` 6.2 với các module Spring 6.1 trong cùng một ứng dụng. Dùng Spring Boot dependency management hoặc một BOM phù hợp để các module Spring được căn chỉnh phiên bản.

### AssertJ không có trên test classpath

MockMvcTester dựa vào AssertJ. Với Spring Boot, `spring-boot-starter-test` thường đã đưa AssertJ vào. Với Spring Framework thuần, cần thêm `assertj-core` trong `testImplementation` hoặc scope test tương đương.

### Mong đợi MockMvcTester khởi động server

MockMvcTester không tạo server. Nếu cần test request qua cổng HTTP, dùng embedded server hoặc container thật.

### Chuyển mọi assertion sang API mới dù không cần thiết

Không cần đổi toàn bộ test cũ. Hãy chọn API làm test dễ đọc và phù hợp với phiên bản hiện tại. MockMvc truyền thống vẫn hữu ích khi nhóm đang có nhiều matcher hoặc helper dựa trên `ResultMatcher`.

## 12. Quy trình áp dụng trong dự án

1. Kiểm tra Spring Framework/Spring Boot version đang được quản lý trong build.
2. Xác nhận Spring Test là 6.2 trở lên và AssertJ có trên test classpath.
3. Nếu dùng Spring Boot 3.4 trở lên, thử inject `MockMvcTester` trong một `@WebMvcTest` hoặc test có `@AutoConfigureMockMvc`.
4. Nếu dùng Spring Framework trực tiếp, cấu hình MockMvc theo nhu cầu rồi tạo tester bằng `MockMvcTester.create(mockMvc)`.
5. Viết một test nhỏ kiểm tra status và body để xác nhận dependency và API hoạt động.
6. Chọn `bodyText()` cho text, `bodyJson()` và JSONPath cho JSON, cùng các assertion status phù hợp.
7. Giữ lại MockMvc truyền thống khi test đang dùng matcher chuyên biệt hoặc khi dự án chưa thể nâng phiên bản.
8. Dùng embedded server hoặc container thật cho yêu cầu kiểm thử network và Servlet runtime.

## 13. Kết luận

`MockMvcTester` là API AssertJ dành cho MockMvc, được giới thiệu từ Spring Framework 6.2. Spring Boot 3.4 trở lên có thể tự cấu hình bean này khi AssertJ có trên test classpath và MockMvc được bật. Với Spring Framework thuần, có thể tạo tester từ MockMvc đã cấu hình bằng `MockMvcTester.create(mockMvc)`.

API mới giúp request và assertion dễ đọc theo phong cách AssertJ, ví dụ `hasStatusOk()`, `bodyText()` và `bodyJson().extractingPath(...)`. Nó vẫn dùng môi trường mock của Spring MVC Test. Hãy chọn MockMvcTester khi phiên bản hỗ trợ và phong cách fluent giúp test rõ ràng hơn; giữ MockMvc truyền thống khi cần tương thích hoặc matcher hiện có. Cả hai đều cần embedded server hay container thật nếu mục tiêu là kiểm tra HTTP runtime.
