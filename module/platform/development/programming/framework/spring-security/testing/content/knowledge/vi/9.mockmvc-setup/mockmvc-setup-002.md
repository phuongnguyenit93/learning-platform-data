# webAppContextSetup và standaloneSetup khác nhau về phạm vi cấu hình

## Mục tiêu bài học

Trong chương **Thiết lập MockMvc** của mô-đun **SPRING_SECURITY_TESTING**, ta học cách kiểm chứng xác thực, phân quyền và các cơ chế bảo vệ HTTP bằng `spring-security-test`. Với ứng dụng **Servlet/Spring MVC**, một quyết định ban đầu rất quan trọng là tạo `MockMvc` bằng `webAppContextSetup(...)` hay `standaloneSetup(...)`. Hai cách đều xử lý request giả lập trong JVM, nhưng chúng lấy **cấu hình MVC và Spring Security** từ những nguồn khác nhau.

Sau bài này, bạn sẽ:

1. Giải thích chính xác phạm vi của hai builder và mối quan hệ với `WebApplicationContext`.
2. Biết thành phần nào có mặt mặc định, thành phần nào phải đăng ký thủ công: controller, `@ControllerAdvice`, message converter, validator, interceptor và servlet filter.
3. Hiểu vì sao một phép thử `standaloneSetup` có thể cho **200 OK** ở route đáng lẽ cần xác thực.
4. Thiết lập `webAppContextSetup(...).apply(springSecurity())` để thử `SecurityFilterChain` thực sự của **test application context**.
5. Chọn mức kiểm thử phù hợp giữa `standaloneSetup`, `@WebMvcTest`, `@SpringBootTest` và kiểm thử có HTTP server thật.

## 1. Cùng là MockMvc, nhưng khác nguồn cấu hình

`MockMvcBuilders` có hai điểm vào thường dùng:

~~~java
// Sử dụng hạ tầng Spring MVC từ một WebApplicationContext đã khởi tạo:
MockMvc mvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .build();

// Dựng môi trường MVC thử nghiệm quanh controller được chỉ định:
MockMvc mvc = MockMvcBuilders.standaloneSetup(controller)
    .build();
~~~

Cả hai cách đều sử dụng đối tượng `MockHttpServletRequest` / `MockHttpServletResponse` để gọi pipeline Spring MVC **không qua cổng TCP**. Khác biệt là cách tạo `DispatcherServlet` và các thành phần MVC đi kèm:

~~~mermaid
flowchart TB
    A["MockMvcBuilders"] --> B["webAppContextSetup(context)"]
    A --> C["standaloneSetup(controller)"]
    B --> D["WebApplicationContext của test"]
    D --> E["MVC beans + cấu hình<br/>có mặt trong context"]
    C --> F["Controller được cung cấp<br/>+ MVC mặc định cơ bản"]
    C --> G["Các tùy biến được khai báo<br/>trực tiếp trên builder"]
    E --> H["MockMvc.perform(...)"]
    F --> H
    G --> H
~~~

**`webAppContextSetup`** dùng các bean và cấu hình MVC của `WebApplicationContext` đã tải: `HandlerMapping`, `HandlerAdapter`, `ViewResolver`, `@ControllerAdvice`, bộ chuyển đổi dữ liệu và các cấu hình liên quan mà context cung cấp. Phạm vi chính xác tùy loại context đã tải: một `@SpringBootTest` đầy đủ và một `@WebMvcTest` chỉ tải một phần ứng dụng.

**`standaloneSetup`** lấy controller được truyền trực tiếp và dựng một cấu hình MVC mặc định phục vụ kiểm thử. Nó vẫn nhận diện `@GetMapping`, `@PostMapping`, binding và nhiều hành vi MVC cơ bản. Nhưng nó **không tự quét toàn bộ bean của ứng dụng**, cũng không tự thừa hưởng những tùy biến MVC/Security đã khai báo trong application context. Muốn dùng phần nào, bạn phải cung cấp hoặc đăng ký phần đó rõ ràng.

Một ranh giới quan trọng: **`webAppContextSetup` không tự đồng nghĩa với việc Security Filter Chain đã được nối đúng vào MockMvc**. Khi dựng builder thủ công, hãy tích hợp Spring Security bằng `.apply(springSecurity())`; với `@AutoConfigureMockMvc`, Spring Boot thường đăng ký các filter từ test context theo cấu hình mặc định.

## 2. Bảng so sánh phạm vi cấu hình

| Khía cạnh | `webAppContextSetup(context)` | `standaloneSetup(controller)` |
| --- | --- | --- |
| Đầu vào | `WebApplicationContext` đã khởi tạo | Một hoặc nhiều instance controller |
| Quá trình khởi tạo | Cần Spring TestContext/web context | Có thể chạy mà không khởi động Spring context |
| Controller và dependency | Sử dụng bean/proxy đã được Spring tạo và inject | Dùng instance được truyền; phải tự cấp dependency nếu dựng bằng `new` |
| `@ControllerAdvice` / exception handler toàn cục | Lấy từ những bean có trong context | Cần `setControllerAdvice(...)` nếu muốn dùng riêng |
| Message converters / định dạng JSON | Theo cấu hình MVC trong test context | Bộ mặc định của standalone hoặc `setMessageConverters(...)` |
| Formatter, converter, validator, argument resolver | Theo cấu hình MVC trong test context | Chỉ các phần mặc định và những phần chủ động thêm bằng builder |
| Interceptors | Theo cấu hình MVC được nạp | Đăng ký thêm bằng `addInterceptors(...)` |
| Servlet filters | Có thể kết nối filter chain của context khi tích hợp đúng | Không tự lấy filters ứng dụng; phải thêm thủ công |
| Spring Security authorization ở HTTP layer | Kiểm thử được với `SecurityFilterChain` thực của test context khi được gắn vào MockMvc | Không có `SecurityFilterChain` trừ khi bạn chủ động tích hợp |
| Method security như `@PreAuthorize` | Có thể kiểm thử nếu proxy và method security được bật trong context | Không tự tạo proxy bảo mật cho controller/service do `new` dựng |
| Mục tiêu điển hình | Kiểm tra hành vi MVC + cấu hình bảo mật đã nối vào test context | Kiểm tra controller biệt lập, mapping, serialization, kết quả và lỗi |
| Phát hiện lỗi cấu hình ứng dụng | Tốt hơn trong phạm vi context thực sự tải | Hạn chế, vì có thể bỏ qua cấu hình ứng dụng |

Đừng suy luận rằng `standaloneSetup` có **zero** cấu hình MVC: nó dựng các thành phần mặc định cần thiết để vận hành controller. Khác biệt nằm ở việc **cấu hình riêng của ứng dụng có được thừa hưởng hay không**.

## 3. Ví dụ thực tế: cùng endpoint nhưng kết quả bảo mật khác nhau

Giả sử ứng dụng có endpoint công khai và một endpoint chỉ dành cho `ADMIN`. Ta sẽ tạo hai `MockMvc` trong cùng lớp kiểm thử, cùng hướng đến controller như nhau, để thấy rõ vai trò của filter chain.

### 3.1. Ứng dụng Servlet mẫu

Ví dụ sử dụng Spring Boot, Spring MVC và Spring Security hiện đại (cú pháp `SecurityFilterChain`). Tệp `src/main/java/example/DemoApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class AdminController {
    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/admin")
    String adminInfo() {
        return "admin";
    }
}

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Với cấu hình HTTP Basic này, `GET /api/admin` không có người dùng phải bị **401 Unauthorized**, người dùng đã xác thực nhưng thiếu `ROLE_ADMIN` phải bị **403 Forbidden**, còn người có quyền `ADMIN` được nhận **200 OK**. Các con số này gắn với **cấu hình trong ví dụ**, không phải luật cố định cho mọi ứng dụng (form login có thể redirect 302).

Các dependency kiểm thử Gradle thường dùng:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Ứng dụng cần `spring-boot-starter-web` và `spring-boot-starter-security` ở runtime. Nếu dùng Maven, thêm các phụ thuộc kiểm thử tương ứng với scope `test`.

### 3.2. Hai builder trong một lớp test

Tệp `src/test/java/example/MockMvcScopeTest.java`:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockMvcScopeTest {
    @Autowired
    WebApplicationContext context;

    @Autowired
    AdminController controller;

    MockMvc contextMvc;
    MockMvc standaloneMvc;

    @BeforeEach
    void setUp() {
        contextMvc = webAppContextSetup(context)
            .apply(springSecurity())
            .build();

        standaloneMvc = standaloneSetup(controller)
            .build();
    }

    @Test
    void standaloneDoesNotAutomaticallyLoadSecurityFilters() throws Exception {
        // Controller chạy được, nhưng không có lớp phân quyền HTTP.
        standaloneMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void contextWithSecurityRejectsAnonymous() throws Exception {
        contextMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void contextWithSecurityRejectsInsufficientRole() throws Exception {
        contextMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void contextWithSecurityAcceptsAdmin() throws Exception {
        contextMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void publicEndpointWorksInBoth() throws Exception {
        standaloneMvc.perform(get("/api/public"))
            .andExpect(status().isOk());
        contextMvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }
}
~~~

Test đầu tiên **cố ý minh họa một thiếu sót về phạm vi kiểm thử**: nó cho 200 ở `/api/admin` vì builder standalone đã đăng ký controller nhưng **chưa đăng ký servlet security filters**. Đó không phải lỗ hổng đã được chứng minh của ứng dụng đang chạy; nó là dấu hiệu bài test không kiểm chứng được phân quyền HTTP.

Ở các test dùng `contextMvc`, `springSecurity()` tích hợp `springSecurityFilterChain` từ `WebApplicationContext`, nhờ vậy chính sách `hasRole("ADMIN")` được áp dụng. `@WithMockUser` tạo danh tính trong `SecurityContext` để thử phân quyền; nó **không kiểm chứng mật khẩu hay luồng đăng nhập thật**.

> Trong ví dụ, `standaloneSetup(controller)` nhận controller đã được Spring inject vì cả lớp test được chạy với `@SpringBootTest`. Khi kiểm thử standalone đúng nghĩa để tiết kiệm chi phí khởi tạo context, bạn thường tự tạo controller bằng constructor cùng các mock dependency. Việc dùng cùng một Spring context ở đây chỉ nhằm so sánh hai builder trong điều kiện dễ quan sát.

### 3.3. Kết quả mong đợi

| Phép thử | Builder | Kết quả trong ví dụ | Vì sao |
| --- | --- | --- | --- |
| `GET /api/admin`, ẩn danh | `standaloneSetup` thuần | 200 | Không có filter kiểm tra vai trò |
| `GET /api/admin`, ẩn danh | `webAppContextSetup` + Security | 401 | HTTP Basic yêu cầu xác thực |
| `GET /api/admin`, `VIEWER` | `webAppContextSetup` + Security | 403 | Thiếu `ROLE_ADMIN` |
| `GET /api/admin`, `ADMIN` | `webAppContextSetup` + Security | 200 | Đã xác thực và đủ quyền |
| `GET /api/public`, ẩn danh | Cả hai | 200 | Controller hoạt động, route công khai |

Điểm mấu chốt là **cùng controller, cùng request, nhưng quy trình xử lý khác vì cấu hình filter khác**. Kết quả chỉ được xem là bằng chứng bảo vệ endpoint khi test thực sự đi qua các cơ chế bảo mật cần kiểm tra.

## 4. Nếu phải dùng standaloneSetup, thêm cấu hình thế nào?

`standaloneSetup` phù hợp với ca test nhỏ tập trung vào controller. Với controller có phụ thuộc, ưu tiên constructor injection để test dễ cung cấp mock:

~~~java
OrderService service = mock(OrderService.class);
OrderController controller = new OrderController(service);

MockMvc mvc = MockMvcBuilders.standaloneSetup(controller)
    .build();
~~~

Đây là **mẫu cấu trúc minh họa**, giả sử dự án đã định nghĩa `OrderService`, `OrderController` và dùng Mockito. Ví dụ nhấn mạnh rằng builder không tự tìm bean dịch vụ để cấp cho controller được tạo bằng `new`.

Những hook cấu hình hữu ích:

| API của `StandaloneMockMvcBuilder` | Mục đích |
| --- | --- |
| `setControllerAdvice(...)` | Đưa exception handler/controller advice cụ thể vào phép thử |
| `setMessageConverters(...)` | Cấu hình chuyển đổi JSON/XML/body cần thử |
| `setValidator(...)` | Dùng validator tùy biến cho `@Valid` / `@Validated` |
| `setConversionService(...)` | Dùng converter/formatter tự chọn |
| `setCustomArgumentResolvers(...)` | Thêm argument resolver của ứng dụng |
| `addInterceptors(...)` | Chèn `HandlerInterceptor` cần thử |
| `addFilters(...)` | Thêm một hoặc nhiều servlet filter |

Ví dụ khai báo một số phần MVC với các instance do test cung cấp:

~~~java
MockMvc mvc = MockMvcBuilders.standaloneSetup(controller)
    .setControllerAdvice(errorAdvice)
    .setMessageConverters(jsonConverter)
    .setValidator(validator)
    .addInterceptors(auditInterceptor)
    .build();
~~~

Ở đây `errorAdvice`, `jsonConverter`, `validator` và `auditInterceptor` là các object test phải tạo/cấp sẵn; mã nhằm minh họa API cấu hình. Chúng **không được tự động tải** từ Spring context.

### Bổ sung Spring Security vào standalone có đủ không?

Kỹ thuật có thể dùng là truyền chính `Filter` thuộc bean `springSecurityFilterChain` và tích hợp bằng phiên bản `springSecurity(filter)`:

~~~java
// Trong test có WebApplicationContext:
Filter securityFilterChain =
    context.getBean("springSecurityFilterChain", Filter.class);

MockMvc securedStandaloneMvc = MockMvcBuilders
    .standaloneSetup(controller)
    .apply(springSecurity(securityFilterChain))
    .build();
~~~

Các import tương ứng: `jakarta.servlet.Filter`; `MockMvcBuilders` và `SecurityMockMvcConfigurers.springSecurity`. `springSecurity(filter)` kết nối filter đã truyền cùng hỗ trợ Spring Security Test cho `MockMvc`. Cách làm này cần ứng dụng đã cung cấp đúng filter chain; nó **không tự mang theo toàn bộ cấu hình MVC** từ context, và nếu test cũng phải tải đầy đủ context chỉ để lấy filter thì lợi ích tốc độ của standalone giảm đi.

Đối với test chỉ nhằm kiểm tra mapping/JSON của một controller, cấu hình standalone gọn là hợp lý. Nhưng để chứng minh endpoint được bảo vệ đúng theo chính sách của ứng dụng, `webAppContextSetup` và security config từ test context thường là đường đi ít sai sót hơn.

## 5. Tác động tới các lớp bảo mật khác

### 5.1. SecurityContext và giả lập danh tính

Trong `spring-security-test`, các công cụ như `@WithMockUser`, `with(user("alice"))`, `with(jwt())`, `with(oauth2Login())` và `with(oidcLogin())` giúp tạo trạng thái xác thực **giả lập**. Chúng đặc biệt hữu ích cho test phân quyền vì không cần trải qua login flow hoặc nhà cung cấp danh tính bên ngoài.

Nhưng **tạo người dùng giả lập không thay thế việc gắn `SecurityFilterChain`**. Một ca dùng `@WithMockUser(roles = "ADMIN")` rồi gọi `standaloneSetup(controller)` không được tự động xem là phép thử role-based security. Khi filter chain vắng mặt, test có thể chỉ kiểm tra mã của controller.

Với JWT/OAuth2/OIDC, cần tách hai mục đích:

- **Authorization test:** giả lập principal/authorities để kiểm tra route, scope và role; sử dụng pipeline bảo mật đã tích hợp.
- **Authentication test:** gửi credentials hoặc token qua cơ chế xác thực thực sự của ứng dụng để kiểm tra decoder, validator, provider, error handling. `with(jwt())` không tự xác minh chữ ký, issuer, audience hoặc hạn sử dụng của token thật.

### 5.2. Method security khác servlet filter

`@PreAuthorize` và các annotation method security được Spring áp dụng qua proxy/interceptor khi method security được bật, chẳng hạn bằng `@EnableMethodSecurity`. Nếu bạn tự tạo một service/controller bằng `new` rồi đưa vào standalone, proxy đó không xuất hiện tự động, nên annotation có thể không được thực thi.

Ngược lại, nếu truyền vào standalone một **bean đã được proxy bảo mật** lấy từ context, một phần method security có thể vẫn hoạt động dù servlet filter chưa được nối. Vì thế không nên khẳng định “standalone luôn bỏ qua mọi bảo mật”; phải xác định **chính xác layer đang được thử** và cách object được tạo. Với kiểm chứng bảo vệ HTTP, hãy quan sát đường đi qua `SecurityFilterChain`.

### 5.3. CSRF, CORS và security headers

CSRF, CORS và nhiều security headers được xử lý ở tầng filter. Khi standalone chưa có filter thích hợp:

- `POST` không có CSRF token có thể đi thẳng vào controller.
- CORS preflight hoặc response header có thể khác ứng dụng đang chạy.
- Những header do Spring Security thêm, chẳng hạn `X-Content-Type-Options`, có thể không xuất hiện.

Ví dụ với `SecurityFilterChain` có CSRF đang bật, `POST` vào endpoint cần ghi thường phải có token phù hợp; trong MockMvc, có thể dùng `with(csrf())` để tạo request hợp lệ và `with(csrf().useInvalidToken())` để tạo ca từ chối. Chỉ kết luận cơ chế CSRF được kiểm tra khi security filter liên quan có mặt và test bao phủ cả trường hợp hợp lệ lẫn không hợp lệ.

## 6. So sánh với @WebMvcTest và @SpringBootTest

Hai builder là **cách dựng MockMvc**; hai annotation dưới đây lại là **cách tải Spring test context**. Chúng ở các tầng quyết định khác nhau.

| Lựa chọn | Spring context được tải | MockMvc dùng cấu hình ở đâu? | Phù hợp khi |
| --- | --- | --- | --- |
| `standaloneSetup(new Controller(...))` | Không bắt buộc | Các mặc định standalone + phần khai báo thủ công | Thử controller độc lập, phụ thuộc đã mock |
| `@WebMvcTest(SomeController.class)` + `@AutoConfigureMockMvc` (thường do Boot tự áp dụng) | Web/MVC slice; một số bean/cấu hình khác không được tải | Từ web context của slice | Thử controller và MVC/Security config thuộc slice |
| `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureMockMvc` | Application context rộng hơn, tùy cấu hình test | Từ web context đã tải | Thử tích hợp MVC/Security trong ứng dụng |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client | Ứng dụng và embedded web server chạy trên cổng thật | Request đi qua HTTP và servlet container | Thử behavior qua server, cookie, hạ tầng mạng/container |

Trong Spring Boot, `@WebMvcTest` thường tự cấu hình MockMvc và chỉ nạp các bean liên quan tới web layer, bao gồm cấu hình Spring Security được slice chọn/nạp. Tuy nhiên **slice có thể thiếu SecurityFilterChain, service hoặc những dependency/cấu hình cần cho hành vi production**. Hãy khai báo import hoặc mock các dependency cần thiết và xác minh bằng test truy cập bị từ chối.

Ví dụ với `@SpringBootTest`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class BootMvcTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`@AutoConfigureMockMvc` để Boot tạo `MockMvc` từ context; mặc định các filter đã đăng ký được đưa vào MockMvc (trừ khi bạn tắt, ví dụ `addFilters = false`). Khác với builder viết bằng tay, ở đây bạn không phải gọi `webAppContextSetup(...)` trong test. Không nên trộn `MockMvc` do Boot cấp với một `standaloneSetup` riêng rồi mặc nhiên cho rằng hai instance có cùng cấu hình.

**Với ứng dụng Reactive/WebFlux**, công cụ thích hợp là `WebTestClient` chứ không phải `MockMvc`. `WebTestClient.bindToController(...)` và `WebTestClient.bindToApplicationContext(...)` cũng thể hiện sự khác biệt giữa cấu hình cho controller riêng và cấu hình từ context, nhưng phải dùng cơ chế tích hợp reactive security tương ứng. `WebTestClient.bindToServer()` mới tạo client giao tiếp với HTTP server đang chạy.

Lưu ý: **`WebEnvironment.MOCK` vẫn không có HTTP server thật**. `webAppContextSetup` có thể kiểm tra logic Spring Security rất sát ứng dụng trong test context, nhưng không thực hiện TCP/TLS handshake, proxy forwarding hay trao đổi với một servlet container chạy thực tế. Khi cần kiểm chứng những phần này, chuyển sang `RANDOM_PORT` và gửi request bằng HTTP client thực.

## 7. Chọn builder theo câu hỏi cần trả lời

~~~mermaid
flowchart TD
    A["Bạn muốn kiểm chứng gì?"] --> B{"Chỉ logic controller,<br/>binding, JSON, error handling?"}
    B -->|Có| C["standaloneSetup<br/>+ cấu hình cần thiết"]
    B -->|Không| D{"Cần MVC config +<br/>Spring Security của test context?"}
    D -->|Có| E["webAppContextSetup(context)<br/>.apply(springSecurity())"]
    D -->|Không| F{"Cần server HTTP / TLS<br/>/ proxy hoặc network?"}
    F -->|Có| G["RANDOM_PORT + HTTP client<br/>và hạ tầng phù hợp"]
    F -->|Không| H["Unit test / method security test<br/>theo mục tiêu cụ thể"]
~~~

Trong một dự án có nhiều controller và các luật phân quyền, cách tổ chức hiệu quả thường là:

1. Dùng `standaloneSetup` cho những ca controller thuần túy, khi bạn kiểm soát chính xác dependency và MVC customization cần thiết.
2. Dùng `@WebMvcTest` hoặc `webAppContextSetup` để kiểm tra MVC configuration, advice, formatter và filter theo phạm vi context đã chọn.
3. Dùng `@SpringBootTest` + security filters cho các ca bảo mật quan trọng: ẩn danh bị chặn, sai role/scope bị chặn, đủ quyền được phép, CSRF hợp lệ/sai và lỗi xác thực.
4. Bổ sung phép thử HTTP thực khi yêu cầu phụ thuộc container, session cookie qua proxy, TLS hoặc tích hợp với bên ngoài.

### Tự kiểm tra một bài test bảo mật

Trước khi tin vào kết quả test, hãy trả lời:

- Test có tải đúng `SecurityFilterChain` cần dùng không?
- `MockMvc` đang được lấy từ context hay builder standalone? Filter có thực sự được nối vào instance đó không?
- Có ca ẩn danh hoặc người dùng thiếu quyền **bị từ chối** theo cơ chế xác thực đã chọn chưa?
- `@WithMockUser` hoặc `jwt()` đang được dùng để thử phân quyền, hay ta đang nhầm chúng với kiểm thử xác thực thật?
- Các bean `@ControllerAdvice`, converter, validation và method-security proxy cần thiết có mặt trong phạm vi test không?

Một test `status().isOk()` trên controller chạy standalone có thể rất hữu ích để xác nhận response. Nhưng chính test đó **không đủ làm bằng chứng** route được bảo vệ bởi Spring Security nếu pipeline bảo mật chưa được tích hợp.

## 8. Bài tập thực hành

**Bài 1 — Phát hiện kết quả dương tính giả.** Từ ứng dụng ở mục 3, viết thêm test `standaloneMvc.perform(get("/api/admin")).andExpect(status().isUnauthorized())`. Giải thích vì sao test thất bại và vì sao lỗi nằm ở giả định về phạm vi test, không nhất thiết ở cấu hình ứng dụng.

**Bài 2 — Kiểm tra phân quyền theo hai vai trò.** Thêm `GET /api/reports` chỉ cho `REPORT_VIEWER`. Viết một ca bị từ chối và một ca được phép bằng `contextMvc` cùng `@WithMockUser`.

**Bài 3 — Kiểm tra CSRF.** Thêm endpoint `POST /api/admin` cho `ADMIN`. Với `contextMvc`, phân biệt phản hồi của request có `with(csrf())`, thiếu token và token không hợp lệ. Giải thích tại sao test standalone chưa có filter không chứng minh được CSRF.

**Bài 4 — So sánh MVC configuration.** Thêm một `@RestControllerAdvice` chuyển exception thành JSON có cấu trúc. Kiểm tra response bằng `webAppContextSetup` và `standaloneSetup`; sau đó đăng ký advice thủ công cho standalone và so sánh lại.

**Bài 5 — Đánh giá phạm vi.** Thay `@SpringBootTest` bằng `@WebMvcTest(AdminController.class)` và bổ sung những dependency hoặc security configuration cần thiết cho slice. Xác định từng thay đổi trong phạm vi được tải và xác minh lại ca `401/403/200`.

## 9. Ghi nhớ

`webAppContextSetup` dùng **cấu hình MVC đã có trong WebApplicationContext của test**, vì vậy phù hợp để kiểm tra hành vi ứng dụng cùng các bean bảo mật thực sự được tải. `standaloneSetup` dựng **một môi trường MVC nhỏ quanh controller được cung cấp**, thuận tiện cho kiểm thử biệt lập nhưng dễ bỏ sót filter, advice, converter hoặc proxy nếu test không đăng ký chúng.

Với **SPRING_SECURITY_TESTING**, việc quan trọng nhất là xác định **request kiểm thử đã đi qua đúng `SecurityFilterChain` chưa**. Một endpoint trả 200 trong test chỉ chứng minh controller xử lý thành công tại **phạm vi cấu hình của test đó**; để kết luận luật xác thực/phân quyền hoạt động, phải kiểm tra cả các ca được phép và bị từ chối trên pipeline bảo mật tương ứng.
