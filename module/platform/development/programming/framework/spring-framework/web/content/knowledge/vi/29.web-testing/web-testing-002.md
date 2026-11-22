# MockMvc: `standaloneSetup` và `webAppContextSetup`

## 1. MockMvc kiểm thử điều gì?

`MockMvc` là công cụ Spring MVC Test (`spring-test`) dùng để tạo HTTP request mô phỏng, đưa request qua `DispatcherServlet`, rồi kiểm tra response **mà không khởi chạy server HTTP thật trên một cổng mạng**. Nó tạo `MockHttpServletRequest` và `MockHttpServletResponse`, vận hành handler mapping, data binding, message conversion, exception resolution và các thành phần MVC được cấu hình.

```text
MockMvc.perform(GET/POST/PUT/...)
    │
    ▼
MockHttpServletRequest
    │
    ▼
[Filter nếu được thêm vào MockMvc]
    │
    ▼
DispatcherServlet
    ├─ HandlerMapping
    ├─ HandlerAdapter / argument resolvers
    ├─ Controller → service hoặc mock service
    ├─ HandlerExceptionResolver / @ControllerAdvice
    └─ HttpMessageConverter
    │
    ▼
MockHttpServletResponse
    │
    ▼
andExpect(status, headers, JSON, model, view...)
```

Ví dụ cơ bản (chỉ minh họa; các class xuất hiện trong chương trình hoàn chỉnh phía dưới):

```java
mockMvc.perform(get("/api/greetings/{name}", "Ada"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.message").value("Xin chào, Ada"));
```

- `perform(...)` gửi request mock.
- `get(...)` / `post(...)` / `put(...)` / `delete(...)` mô tả method, path, query, headers, cookies, body.
- `andExpect(...)` kiểm tra status, JSONPath, content type, headers, forwarded/redirected URL hoặc model/view.
- `andDo(print())` giúp chẩn đoán request và response; đừng in payload/headers nhạy cảm.
- `andReturn()` trả `MvcResult` để kiểm tra chuyên sâu.

**Hai đường dựng MockMvc cần hiểu rõ**:

```text
MockMvcBuilders.standaloneSetup(controllerInstance)
    → MVC infrastructure tối thiểu, cấu hình thủ công
    → không load application context thật

MockMvcBuilders.webAppContextSetup(webApplicationContext)
    → dùng các bean/cấu hình MVC trong Spring web context
    → context được Spring TestContext/Boot khởi tạo trước
```

Cả hai dùng cùng DSL thực thi request, nhưng kiểm thử phạm vi khác nhau. Đó là nội dung trọng tâm của bài.

## 2. `standaloneSetup` — kiểm thử controller cô lập

`MockMvcBuilders.standaloneSetup(Object... controllers)` nhận trực tiếp instance controller (hoặc class để tạo instance trong các trường hợp phù hợp), tự khởi tạo hạ tầng Spring MVC cần thiết để chạy những controller này.

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

GreetingService service = new GreetingService();
GreetingController controller = new GreetingController(service);

MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(controller)
    .setControllerAdvice(new ApiErrorAdvice())
    .build();
```

Các class được định nghĩa ở ví dụ runnable phần 7. Với cách này:

1. **Không tải Spring application context** để component scan toàn bộ `@Service`, `@Repository`, `@Configuration` hay tự wiring controller. Dependencies do test cung cấp thông qua constructor/setter, thường dùng fake hoặc Mockito mock.
2. Builder tạo cấu hình Spring MVC cơ bản, gồm khả năng dispatch, request mapping, binding và convert response, nên bài test vẫn kiểm tra cơ chế MVC thật thay vì chỉ gọi `controller.greet("Ada")`.
3. `@ControllerAdvice` toàn cục **không được auto-discover qua component scan**; phải dùng `.setControllerAdvice(adviceInstance)` nếu muốn kiểm tra handler tương ứng.
4. MVC configuration riêng của production (converter tự tùy biến, global validator, interceptor, locale resolver, custom argument resolver, filter/Security) có thể **không hiện diện**. Khi chúng tác động đến test, thiết lập tương ứng trên builder.
5. Khởi tạo ít tài nguyên, thích hợp nhiều biến thể input, status và body của controller.

Ví dụ dùng Mockito để cô lập tầng service:

```java
GreetingService mockService = Mockito.mock(GreetingService.class);
Mockito.when(mockService.greetingFor("Ada"))
    .thenReturn("Xin chào, Ada");

MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new GreetingController(mockService))
    .build();

mvc.perform(get("/api/greetings/{name}", "Ada"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.message").value("Xin chào, Ada"));

Mockito.verify(mockService).greetingFor("Ada");
```

Đây là **snippet minh họa**, cần import `Mockito` và các static helper MockMvc/JUnit như ở ví dụ hoàn chỉnh. Việc mock service giúp kiểm tra controller độc lập với database; không xác nhận implementation/wiring của service thật.

### Cấu hình thêm với `StandaloneMockMvcBuilder`

Các hook có ích:

- `setControllerAdvice(...)`: đăng ký các exception handlers, binding advice cần kiểm thử.
- `setMessageConverters(...)`: chỉ định converter HTTP, ví dụ cấu hình Jackson khác mặc định.
- `setValidator(...)`: validator sử dụng khi kiểm tra `@Valid`/binding.
- `setConversionService(...)`: conversion rules cho path/query/body.
- `setCustomArgumentResolvers(...)` / `setCustomReturnValueHandlers(...)`: những cơ chế method arguments/return tùy biến.
- `addInterceptors(...)`: chạy những MVC interceptors đã chọn.
- `defaultRequest(...)`: request properties áp dụng mặc định.
- `alwaysExpect(...)` / `alwaysDo(...)`: expectation/hook chung của test suite.

Ví dụ:

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new GreetingController(new GreetingService()))
    .setControllerAdvice(new ApiErrorAdvice())
    .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
    .build();
```

Đoạn này **minh họa builder**, phải import `MediaType` và static `get`. Khi dùng `alwaysExpect(status().isOk())` sẽ làm test HTTP 404 cố ý thất bại, vì vậy chỉ đặt global expectation khi tất cả case có chung điều kiện.

**Không nhầm:** `standaloneSetup` vẫn dùng MVC infrastructure được dựng cho test. Nó gần với unit test về phạm vi/controller dependencies, nhưng không phải pure unit test của một Java method.

## 3. `webAppContextSetup` — kiểm tra Spring MVC configuration trong context

`MockMvcBuilders.webAppContextSetup(WebApplicationContext)` dùng một Spring **web application context đã khởi tạo** (có `ServletContext`). `DispatcherServlet` khám phá controllers, handler mappings, converters, validators, exception resolvers, `@ControllerAdvice` và những bean MVC có trong context. Việc này giúp phát hiện lỗi component scan, bean injection và cấu hình mà standalone có thể không nhìn thấy.

Ví dụ với Spring Boot:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class GreetingWebContextTest {
    @Autowired
    WebApplicationContext webContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(webContext).build();
    }

    @Test
    void responds() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Xin chào, Ada"));
    }
}
```

Đây là **mã minh họa ngắn**, chưa gồm imports và model; phần 7 có chương trình đầy đủ. `@SpringBootTest(webEnvironment=MOCK)` trong Spring Boot Servlet/MVC khởi động application context thích hợp nhưng **không mở cổng server thật**. Khi test class nằm dưới package gốc có `@SpringBootApplication`, Boot tìm cấu hình khởi tạo tương ứng.

Khác với standalone:

- Controller/service/advice được Spring dựng và inject như bean. Nếu bean thiếu, context có thể không khởi động.
- Spring MVC configuration thực được áp dụng (ví dụ `WebMvcConfigurer`, exception resolvers, message converters do context cấu hình).
- Chi phí load context thường cao hơn, có thể kích hoạt database/messaging/application startup logic nếu ứng dụng khai báo.
- Spring TestContext **cache application context** giữa các test có cấu hình tương thích. Tránh `@DirtiesContext` hoặc đổi profile/property mỗi lớp một cách không cần thiết, vì dễ vô hiệu cache.

### TestContext thuần Spring Framework

Không dùng Boot cũng có thể kết hợp JUnit 5 và Spring:

```java
@SpringJUnitWebConfig(classes = TestWebConfig.class)
class MvcContextTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }
}
```

Đây là **mẫu minh họa, không phải file độc lập**: `TestWebConfig` phải được tạo với `@EnableWebMvc`, controller và dependencies cần thiết. `@SpringJUnitWebConfig` gộp `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration` và `@WebAppConfiguration`. Nếu dùng các annotation rời, cần cấu hình đầy đủ cả context và web environment, không chỉ `@ContextConfiguration`.

## 4. Bảng so sánh lựa chọn

| Tiêu chí | `standaloneSetup` | `webAppContextSetup` |
| --- | --- | --- |
| Đầu vào | Controller instance/class cụ thể | `WebApplicationContext` đã khởi tạo |
| ApplicationContext | Không tải application context | Dùng context từ Spring TestContext/Boot |
| DI service/repository | Test chủ động tạo/mock dependency | Bean do Spring quản lý và inject |
| `@ControllerAdvice` | Cần đăng ký khi áp dụng qua `setControllerAdvice` | Khám phá các advice bean trong context |
| Converter/validator/interceptor | MVC mặc định, tùy chỉnh trên builder | Dùng các MVC bean/cấu hình được khai báo |
| Security/filters | Phải lắp đúng khi cần | Cũng cần đảm bảo filter chain thực sự vào MockMvc |
| Khả năng phát hiện wiring lỗi | Hạn chế | Tốt hơn, tùy mức độ của context được load |
| Thời gian chạy | Thường nhanh, setup gọn | Có chi phí khởi động context, được cache |
| Network/server port thật | Không | Không |
| Mục tiêu chính | Contract controller, edge cases | MVC configuration và collaboration giữa beans |

**Lựa chọn thực tế:**

- Nếu kiểm thử nhiều dạng request của một controller và cần service mock: `standaloneSetup` rất phù hợp, vì kiểm soát rõ dependency và chạy nhanh.
- Nếu muốn xác nhận `@ControllerAdvice`/`WebMvcConfigurer`, custom converters, filters, wiring và behavior theo cấu hình app: `webAppContextSetup` phù hợp hơn.
- Trong dự án lớn, kết hợp standalone cho phần lớn test controller và context tests đại diện để bảo vệ MVC configuration.
- Spring Boot `@WebMvcTest` tạo **MVC slice context** và thường auto-inject `MockMvc`. Nó có phạm vi ít hơn `@SpringBootTest` full context và **không đồng nghĩa** bản thân builder `webAppContextSetup`, dù có thể dùng Spring MVC Test infrastructure.

## 5. Các matcher và cách kiểm thử chính xác

Lời gọi thường dùng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/api/greetings/{name}", "Ada")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "test-1"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.message").value("Xin chào, Ada"));

mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Spring\"}"))
    .andExpect(status().isCreated());

mockMvc.perform(get("/absent"))
    .andExpect(status().isNotFound());
```

Hai request cuối **chỉ minh họa API matcher**: cần có endpoints tương ứng mới chạy được. `contentType(MediaType.APPLICATION_JSON)` xác định kiểu body của request; `accept(MediaType.APPLICATION_JSON)` là media type response mong muốn. Với POST JSON, chỉ gọi `.content(...)` chưa chắc đủ để framework chọn converter phù hợp.

Các expectation khác:

- `header().string("Location", "...")`: response headers.
- `content().json("{\"message\":\"...\"}")`: JSON structure theo phương pháp matcher.
- `handler().handlerType(GreetingController.class)` và `handler().methodName("greet")`: mapping có trúng controller/method dự kiến không.
- `model().attributeExists("product")` / `view().name("products")`: MVC render view.
- `redirectedUrl("/login")` / `forwardedUrl("/...")`: redirect/forward.
- `request().asyncStarted()`, `asyncDispatch(...)`: controller với Spring MVC async types.

**MockMvc không kiểm thử HTTP network thật:** request đi thẳng vào Servlet MVC infrastructure. Nếu muốn xác minh TCP, TLS, reverse proxy, servlet container, HTTP keepalive hay browser behavior, cần test end-to-end qua server thật, ví dụ `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client.

## 6. Security, filter và giới hạn của mock servlet

**Điểm dễ gây false positive:** `webAppContextSetup(context).build()` có context MVC nhưng không mặc định đảm bảo *mọi servlet filter runtime* đã được thêm vào mock chain. Với custom filters, có thể cần:

```java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .addFilters(auditFilter)
    .build();
```

Đoạn là **mã minh họa**: `auditFilter` là bean `Filter` có trong context. Với Spring Security, khi phụ thuộc `spring-security-test`, có thể dùng `.apply(springSecurity())` (tùy ứng dụng cần `springSecurityFilterChain` thích hợp). Khi Spring Boot dùng `@AutoConfigureMockMvc`, Boot có logic cấu hình thêm filters phù hợp; cần xác nhận config đang chạy theo test.

`@WithMockUser` tạo security context phục vụ test, không thay thế việc bảo đảm security filter chain hợp lệ khi test thực sự muốn xác minh authorization và CSRF. Một GET trả 200 khi filter bị bỏ qua không chứng minh endpoint được bảo vệ.

Tương tự, MockMvc không tự mô phỏng việc gateway cắt kết nối, TLS handshake, HTTP/2 multiplexing, proxy header rewriting, socket timeout, hay các mức giới hạn tải thực. Hãy lựa chọn test theo rủi ro muốn kiểm tra.

## 7. Ví dụ Java 17+ hoàn chỉnh, chạy hai cách setup

Bài thực hành dùng **Java 17+, Spring Boot 3.3.13, Spring MVC, JUnit Jupiter**. Cả hai test class cùng kiểm tra một controller và exception advice: standalone tự dựng collaborator/advice; web context lấy từ Spring. Chạy `gradle test` mà không mở HTTP server hoặc cần database.

Cấu trúc:

```text
mockmvc-two-setups/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── GreetingStandaloneTest.java
        └── GreetingWebContextTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'mockmvc-two-setups'
```

**`build.gradle`** — JDK 17+, Gradle 8.x (không cần plugin Spring Boot khi chỉ chạy test):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

Các starter mang tới Spring MVC/Jackson và Spring Test/JUnit/Mockito; không cần tạo `bootJar` để học hai builder.

**`src/main/java/demo/GreetingApplication.java`**

```java
package demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {
}
```

Lớp cấu hình gốc đủ để `@SpringBootTest` tìm và khởi tạo application context trong package `demo`. Không cần phương thức `main` vì ví dụ này chỉ chạy test.

**`src/main/java/demo/GreetingService.java`**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greetingFor(String name) {
        if ("missing".equals(name)) {
            throw new MissingNameException(name);
        }
        return "Xin chào, " + name;
    }
}

class MissingNameException extends RuntimeException {
    MissingNameException(String name) {
        super("Không tìm thấy tên: " + name);
    }
}
```

Service không có DB và có hai hành vi: trả greeting, hoặc ném lỗi nghiệp vụ khi name là `missing`.

**`src/main/java/demo/GreetingController.java`**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable("name") String name) {
        return new GreetingResponse(greetingService.greetingFor(name));
    }
}

record GreetingResponse(String message) {}
```

Response dùng record, Jackson chuyển thành JSON với property `message`.

**`src/main/java/demo/ApiErrorAdvice.java`**

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(MissingNameException.class)
    public ResponseEntity<ErrorResponse> handleMissing(MissingNameException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ErrorResponse(ex.getMessage()));
    }
}

record ErrorResponse(String error) {}
```

Handler ánh xạ lỗi `MissingNameException` thành HTTP 404 với body JSON `{"error":"Không tìm thấy tên: missing"}`.

**`src/test/java/demo/GreetingStandaloneTest.java`**

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingStandaloneTest {
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        GreetingController controller =
            new GreetingController(new GreetingService());

        mvc = MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new ApiErrorAdvice())
            .build();
    }

    @Test
    void returnsGreeting() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Xin chào, Ada"));
    }

    @Test
    void mapsBusinessErrorWithExplicitAdvice() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error").value("Không tìm thấy tên: missing"));
    }
}
```

Lớp này **không dùng `@SpringBootTest`**. `new GreetingService()` và `new ApiErrorAdvice()` do test trực tiếp tạo, giúp nhìn thấy rõ controller dependencies và exception handler được thiết lập ở đâu.

**`src/test/java/demo/GreetingWebContextTest.java`**

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class GreetingWebContextTest {
    @Autowired
    private WebApplicationContext context;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void usesSpringManagedControllerAndService() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Xin chào, Ada"));
    }

    @Test
    void discoversAdviceInSpringContext() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error").value("Không tìm thấy tên: missing"));
    }
}
```

Ở web context setup, Spring tìm `GreetingController`, `GreetingService`, `ApiErrorAdvice` bằng component scanning từ package `demo`, sau đó inject constructor. Test xác nhận cả HTTP contract **và** thành phần Spring được nối đúng.

Từ thư mục dự án, dùng JDK 17+ và Gradle 8.x:

```bash
gradle test
```

Lệnh chạy **4 phương thức `@Test`** (hai standalone và hai web context). Khi pass, Gradle báo `BUILD SUCCESSFUL` và tạo báo cáo tại `build/reports/tests/test/index.html`. Các dòng log chi tiết có thể khác nhau theo Gradle, hệ điều hành và test runner; không cần dự đoán toàn bộ stdout.

Nếu muốn chạy qua Gradle Wrapper, có thể tạo wrapper bằng Gradle cài sẵn rồi chạy `./gradlew test` (Linux/macOS) hoặc `gradlew.bat test` (Windows).

## 8. Mở rộng kiểm thử theo mục tiêu

**Controller cần validation thật:** Nếu code dùng `@Valid`, Jakarta Bean Validation và custom validator, standalone cần đảm bảo validator/converter tương đương runtime. Web context test giúp phát hiện `Validator`/`@ControllerAdvice` bean bị cấu hình sai. Spring Boot application có thể cần dependency `spring-boot-starter-validation`; `spring-boot-starter-web` không phải bảo đảm toàn bộ Bean Validation API/implementation.

**Controller cần Security:** Với `spring-security-test`, cấu hình MockMvc đúng filter chain và user/CSRF phù hợp. `@WithMockUser` không tự làm filter xuất hiện nếu MockMvc builder không gắn bảo mật. Controller advice có thể xử lý domain exception nhưng authentication failure chủ yếu được xử lý tại filter chain; đừng nhầm hai tầng.

**Kiểm thử MVC async:** Với `Callable`, `DeferredResult` hay Spring MVC async return types, có thể assert `request().asyncStarted()` rồi gọi `asyncDispatch`:

```java
MvcResult pending = mvc.perform(get("/async"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(pending))
    .andExpect(status().isOk());
```

Đây là **snippet minh họa**, cần endpoint `/async` phù hợp. Không dùng API trên để suy đoán mọi Reactor `Flux` tương đương servlet async.

**Boot MVC test slice:** `@WebMvcTest(GreetingController.class)` thường giúp load web slice nhanh hơn full `@SpringBootTest` và inject `MockMvc` qua `@AutoConfigureMockMvc`. Dependency service của controller cần mock hoặc test bean tương ứng (Boot 3.3 dùng `@MockBean`; các version mới có `@MockitoBean`). Đây là lựa chọn trung gian giữa standalone và full context, khác nhiệm vụ trực tiếp của hai builder đang học.

**Test database/external API:** Standalone thích hợp mock collaborator; full context cũng có thể cần fake/embedded DB hoặc stub external service để ổn định. Đừng dùng request mock để xác nhận DB migration, network retry, cookie bảo mật tại proxy hoặc TLS handshake thành công.

## 9. Lỗi thường gặp khi lựa chọn và viết test

1. **Tưởng `standaloneSetup` tự component scan mọi bean.** Hãy tự truyền controller dependencies, advice và MVC customizations.
2. **Quên `setControllerAdvice`** trong standalone khiến service ném exception nhưng test nhận lỗi không được convert như runtime.
3. **Tự tạo controller bằng `new` trong web-context test.** Như vậy bỏ qua cơ chế dependency injection muốn kiểm chứng; hãy dùng các bean trong context.
4. **Quên `@WebAppConfiguration`/`@SpringJUnitWebConfig`** khi dùng Spring TestContext thuần, dẫn đến không có `WebApplicationContext` có `ServletContext`.
5. **Nghĩ `webAppContextSetup` chạy HTTP server thật.** Cả hai builder đều dùng mock servlet; cần `RANDOM_PORT` cho network integration.
6. **Không gắn filters/Security chain** khi test authorization, khiến assertion 200/403 mang nghĩa sai.
7. **Chỉ assert status 200** mà bỏ qua JSON, headers, content-type, xử lý exception.
8. **Đặt `alwaysExpect(status().isOk())`** trên builder dùng cả trường hợp muốn test 404/400.
9. **Gửi JSON request nhưng thiếu `Content-Type: application/json`**, dẫn đến 415 hoặc behavior khác runtime.
10. **Nhầm `@WebMvcTest` với full context**, rồi kỳ vọng service/repository được component scan tự động.
11. **Mock cả lớp đang cần kiểm chứng**, chẳng hạn mock `GreetingController` rồi coi như đã kiểm thử request mapping và serialization.
12. **Dùng `@DirtiesContext` tùy tiện** hoặc cấu hình mỗi lớp khác nhau làm context cache kém hiệu quả.
13. **So sánh toàn bộ JSON string cứng nhắc** khi có khác biệt thứ tự key/escaping; ưu tiên JSONPath hoặc JSON structural matching.
14. **Giả định MockMvc tái hiện network/Servlet container production**, trong khi các giới hạn TLS/proxy, connection, sockets nằm ngoài phạm vi test.

Khi case fail, xem `andDo(print())` và phân tích thứ tự: path/method → handler mapping → argument binding → controller/service exception → advice → converters → filters/Security → response assertions.

## 10. Câu hỏi tự kiểm tra

1. **`standaloneSetup(new Controller(...))` có tải `@Service` bằng Spring không?** → Không. Test tự tạo hoặc mock collaborator, rồi truyền vào controller.
2. **Standalone có tự thấy `@RestControllerAdvice` của production không?** → Không; cần `setControllerAdvice` hoặc cấu hình thủ công.
3. **`webAppContextSetup(context)` có dùng server socket?** → Không; nó dùng `DispatcherServlet` trên request/response giả lập.
4. **Phát hiện controller thiếu bean injection nên chọn gì?** → Web-context test có khả năng phát hiện hơn vì Spring thực sự tạo và wiring bean.
5. **Tại sao context test thường chậm hơn standalone?** → Cần load context, nhưng TestContext cache các context cùng cấu hình.
6. **Có `@SpringBootTest(MOCK)` mà quên Security filter trong MockMvc có nguy cơ gì?** → Authorization tests có thể cho kết quả sai; cần xác nhận filter chain được áp dụng.
7. **Khi nào nên dùng `@WebMvcTest`?** → Khi muốn MVC slice với một số controller/advice/converter, nhanh hơn load cả application.
8. **Muốn kiểm tra HTTPS/cổng thật, MockMvc có đủ không?** → Không; cần HTTP client tới server thật cùng môi trường phù hợp.
9. **Muốn kiểm tra JSON error 404 của controller, phải assert gì?** → HTTP 404 và body lỗi (ví dụ `$.error`), đồng thời bảo đảm advice được đăng ký đúng.

## 11. Tài liệu tham khảo

- Spring Framework — MockMvc configuring/setup: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html
- Spring Framework — Setup options: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup-options.html
- Spring Framework — MockMvc requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html
- Spring Framework — MockMvc expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework 6.1 — `MockMvcBuilders` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/web/servlet/setup/MockMvcBuilders.html
- Spring Framework 6.1 — `StandaloneMockMvcBuilder` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/web/servlet/setup/StandaloneMockMvcBuilder.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/docs/3.3.13/reference/html/features.html#features.testing
