# MockMvc và giới hạn của việc không chạy máy chủ HTTP thật

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và các cơ chế bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào nhánh **Servlet/Spring MVC**: hiểu `MockMvc` đi qua những thành phần nào, thiết lập bộ lọc Spring Security đúng cách và xác định khi nào phải kiểm thử qua một máy chủ HTTP thật. `WebTestClient` dành cho ứng dụng Reactive hoặc cho các phép thử HTTP tương ứng sẽ được nhắc đến để phân biệt phạm vi.

Sau bài học, bạn có thể:

1. Giải thích vì sao `MockMvc` kiểm thử được `DispatcherServlet` và chuỗi lọc bảo mật mà không cần mở cổng HTTP.
2. Thiết lập `MockMvc` để Spring Security thực sự tham gia xử lý yêu cầu.
3. Viết ca kiểm thử khách ẩn danh, người dùng có/không có quyền và yêu cầu thiếu CSRF token.
4. Phân biệt **giả lập danh tính** với **kiểm chứng quy trình đăng nhập hoặc xác thực token thật**.
5. Chọn đúng mức kiểm thử khi cần xác minh TLS, servlet container, reverse proxy, cookie và đường truyền mạng.

## 1. MockMvc thực sự chạy những gì?

`MockMvc` là công cụ kiểm thử Spring MVC ở **trong cùng tiến trình JVM**. Lệnh `mockMvc.perform(...)` tạo các đối tượng `MockHttpServletRequest` và `MockHttpServletResponse`, cho yêu cầu đi qua các thành phần MVC trong ứng dụng thử nghiệm và cung cấp kết quả để đối chiếu. Nó **không khởi động máy chủ đang lắng nghe trên một cổng TCP** và **không truyền request qua mạng**.

Với cấu hình đầy đủ, hành trình điển hình là:

~~~mermaid
flowchart LR
    A["JUnit / MockMvc.perform"] --> B["MockHttpServletRequest"]
    B --> C["Servlet Filter Chain<br/>Spring Security"]
    C --> D["DispatcherServlet"]
    D --> E["Controller / MVC"]
    E --> F["MockHttpServletResponse"]
    F --> G["andExpect(...)"]
~~~

Đây là mô hình của một lần xử lý yêu cầu trong bộ kiểm thử, không phải một sơ đồ triển khai HTTP ngoài đời. `MockMvc` có thể thực thi logic ánh xạ endpoint, binding, validation, xử lý ngoại lệ, serialization, `HandlerInterceptor` và các `Filter` **đã được đăng ký với bản dựng MockMvc**. Đặc biệt, nếu có `springSecurityFilterChain`, các luật trong `SecurityFilterChain` có thể chặn yêu cầu *trước khi* controller được gọi.

Trên máy chủ thật, phía trước chuỗi lọc còn các bước khác:

~~~text
HTTP client
  -> DNS / kết nối TCP / TLS / HTTP framing
  -> máy chủ hoặc servlet container (Tomcat, Jetty, ...)
  -> servlet filters, Spring Security
  -> DispatcherServlet -> controller
  -> phản hồi qua kết nối mạng
~~~

`MockMvc` bỏ qua phần mạng và hạ tầng máy chủ ở đầu/cuối luồng nhưng vẫn kiểm tra được nhiều quy tắc bảo mật thuộc tầng ứng dụng. Vì thế, phát biểu “MockMvc không kiểm thử được Spring Security vì không có máy chủ HTTP” là **sai**; điều cần kiểm tra là **chuỗi lọc bảo mật có thực sự được nối vào MockMvc hay chưa**.

## 2. Thiết lập MockMvc có Spring Security

### 2.1. Với Spring Boot

Trong ứng dụng Servlet dùng Spring Boot, cách phổ biến là tải application context và yêu cầu Boot cấu hình `MockMvc`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class SecurityMvcTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`WebEnvironment.MOCK` dựng một môi trường web giả lập; không có server socket được mở. `@AutoConfigureMockMvc` đăng ký `MockMvc` và mặc định đưa các bộ lọc từ context vào pipeline, bao gồm Spring Security nếu ứng dụng cấu hình bảo mật phù hợp. Giữ mặc định này khi kiểm thử bảo mật; `@AutoConfigureMockMvc(addFilters = false)` sẽ bỏ qua filters và có thể làm kết quả kiểm thử phân quyền sai lệch.

Nếu chỉ muốn tải phần MVC, có thể cân nhắc `@WebMvcTest`. Đây là *slice test*: chỉ một phần bean được tải, nên cần bảo đảm cấu hình `SecurityFilterChain` liên quan có mặt trong context và những phụ thuộc của controller được cung cấp trong test. Không nên suy ra từ một ca `@WebMvcTest` thành công rằng toàn bộ cấu hình bảo mật production đã được kiểm thử.

Phụ thuộc kiểm thử thường dùng với Spring Boot và Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Ứng dụng còn cần các starter runtime phù hợp, ví dụ `spring-boot-starter-web` và `spring-boot-starter-security`. Với Maven, thêm `spring-security-test` ở phạm vi `test` cùng Spring Boot Starter Test.

### 2.2. Tự dựng MockMvc với WebApplicationContext

Nếu tự tạo `MockMvc` bằng builder, hãy gắn tích hợp Spring Security:

~~~java
@Autowired
WebApplicationContext webApplicationContext;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

`springSecurity()` là bộ cấu hình từ `SecurityMockMvcConfigurers`; nó kết nối `springSecurityFilterChain` với `MockMvc` và hỗ trợ tích hợp `SecurityContext` trong kiểm thử. Cần import tĩnh:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
~~~

`MockMvcBuilders.standaloneSetup(controller)` hữu ích khi chỉ cần thử một controller, nhưng không tự mang vào toàn bộ cấu hình bảo mật của ứng dụng. Nếu dùng nó để khẳng định một route “an toàn”, kết quả có thể là **dương tính giả** vì request chưa đi qua `SecurityFilterChain`. Với ca kiểm thử quy tắc bảo mật, ưu tiên `webAppContextSetup(...).apply(springSecurity())` hoặc cấu hình Boot có filters.

## 3. Ví dụ hoàn chỉnh: quyền truy cập và CSRF

Giả sử ứng dụng có API đọc công khai, API đọc hồ sơ yêu cầu đăng nhập và API tạo đơn hàng yêu cầu quyền `EDITOR`. Ví dụ cố ý giữ **CSRF bật** (mặc định trong Spring Security), nên một request `POST` phải có CSRF token hợp lệ ngay cả khi người dùng đã được giả lập đăng nhập.

Trong một dự án Spring Boot Servlet, tệp `src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/orders").hasRole("EDITOR")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    String publicData() {
        return "public";
    }

    @GetMapping("/api/profile")
    String profile() {
        return "private";
    }

    @PostMapping("/api/orders")
    ResponseEntity<Void> createOrder() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Tệp `src/test/java/demo/DemoSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class DemoSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCannotCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders").with(csrf()))
            .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void missingCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/orders"))
            .andExpect(status().isForbidden());
    }
}
~~~

Những điểm cần quan sát:

- `permitAll()` cho phép `GET /api/public` khi không có danh tính.
- `anyRequest().authenticated()` yêu cầu xác thực đối với `GET /api/profile`. Vì cấu hình ví dụ bật HTTP Basic, người dùng ẩn danh nhận **401 Unauthorized**.
- `hasRole("EDITOR")` kiểm tra authority `ROLE_EDITOR`. `@WithMockUser(roles = "EDITOR")` tạo authority này; `VIEWER` không đủ quyền nên nhận **403 Forbidden**.
- `with(csrf())` cung cấp CSRF token hợp lệ cho mock request. Một người có quyền `EDITOR` nhưng thiếu CSRF token vẫn bị chặn **403** trước khi logic controller chạy.
- Mỗi `andExpect(...)` kiểm tra **kết quả bảo mật quan sát được ở tầng HTTP**, không đơn thuần gọi trực tiếp phương thức controller.

> **Lưu ý về mã trạng thái:** 401, 403 hay 302 phụ thuộc cơ chế đăng nhập, `AuthenticationEntryPoint`, `AccessDeniedHandler` và vị trí request bị chặn. Trong ứng dụng bật form login, một request chưa xác thực có thể nhận **302 redirect** đến trang đăng nhập thay vì 401. Ví dụ trên bật HTTP Basic để kỳ vọng 401 rõ ràng.

## 4. Giả lập người dùng không đồng nghĩa với kiểm thử xác thực thật

`spring-security-test` cung cấp nhiều cách thiết lập trạng thái bảo mật cho một request. Mỗi cách trả lời một câu hỏi khác nhau:

| Cách dùng | Điều được kiểm chứng tốt | Điều **chưa** được kiểm chứng |
| --- | --- | --- |
| `@WithMockUser(username = "alice", roles = "EDITOR")` | Phân quyền, xử lý request với một `SecurityContext` đã có người dùng | Password encoder, lookup người dùng, quy trình login |
| `with(user("alice").roles("EDITOR"))` | Phân quyền theo người dùng riêng cho từng request | Xác thực username/password thật |
| `with(httpBasic("alice", "secret"))` | Đường đi HTTP Basic qua filter và cơ chế xác thực **được cấu hình trong test** | TLS hoặc vận chuyển HTTP thật |
| `with(jwt())` | Quy tắc resource server dựa trên claims/authorities của JWT giả lập | Xác minh chữ ký, issuer, audience, expiry của bearer token thật |
| `with(oauth2Login())` / `with(oidcLogin())` | Quyền truy cập sau khi đã có OAuth2/OIDC principal | Redirect/callback với nhà cung cấp danh tính, trao đổi authorization code |

Ví dụ đặt danh tính trên từng request (đã cấu hình `MockMvc` có Security):

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/api/profile")
        .with(user("alice").roles("VIEWER")))
    .andExpect(status().isOk());
~~~

Với ứng dụng **OAuth2 Resource Server** đã bật JWT, có thể dựng một principal mang scope tùy ý để kiểm tra luật phân quyền:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Đoạn JWT trên **chỉ là ví dụ cho một route `/api/reports` và cấu hình resource server tương ứng**, không thuộc `DemoApplication` của mục 3; cần thêm import `org.springframework.security.core.authority.SimpleGrantedAuthority`. Với `jwt()`, Spring Security Test gắn một `JwtAuthenticationToken` giả lập; request không chứng minh được một JWT được ký đúng hoặc bộ giải mã (`JwtDecoder`) chấp nhận token.

Ngược lại, vẫn có thể dùng **MockMvc** để kiểm tra validation token thật **ở tầng ứng dụng**: gửi header `Authorization: Bearer <token>`, để chuỗi filter thật gọi `JwtDecoder` đã cấu hình và assert kết quả. Điểm giới hạn ở đây nằm ở **cách giả lập `jwt()`**, không phải bản thân MockMvc bắt buộc phải bỏ qua JWT validation. Tương tự, `httpBasic(...)` có thể kiểm tra thông tin đăng nhập thực tế qua `AuthenticationProvider` nếu provider và kho người dùng thật/kiểm thử được cấu hình trong context.

## 5. Những giới hạn khi không chạy máy chủ HTTP thật

| Vấn đề cần kiểm chứng | MockMvc làm được đến đâu? | Khi nào cần phép thử qua HTTP thật? |
| --- | --- | --- |
| Security filters, endpoint rules, `@PreAuthorize`, CSRF | Chạy và kiểm tra được khi filter chain và method security được cấu hình đúng | Khi cần thêm bằng chứng về toàn tuyến triển khai |
| Status, header, cookie theo logic Spring MVC | Kiểm tra response được tạo trong mock Servlet API | Khi quan tâm cách container/proxy/browser nhận và xử lý header, cookie |
| TLS, HTTP/2, TCP, socket timeout, connection reuse | Không tạo kết nối mạng hoặc thực hiện TLS handshake | Khi yêu cầu phụ thuộc giao thức hoặc cấu hình web server |
| Servlet container và cấu hình triển khai | Không tái hiện đầy đủ hành vi thực của Tomcat/Jetty hay các tùy chọn connector | Khi lỗi chỉ xuất hiện sau deploy hoặc do container |
| Reverse proxy, gateway, forwarded headers | Có thể giả lập header đầu vào để kiểm thử logic ứng dụng | Khi phải xác minh proxy thực sự chuẩn hóa/chuyển tiếp header đúng |
| CORS và CSRF | Có thể thử logic CORS filter, `OPTIONS` preflight giả lập và CSRF trong Spring Security | Khi muốn xác minh luồng browser → proxy → server thực sự |
| Streaming, SSE, WebSocket, backpressure và tải cao | Không mô phỏng đầy đủ đường truyền, tốc độ mạng hoặc hành vi nhiều kết nối thực | Khi đánh giá streaming, nâng cấp giao thức, hiệu năng/độ ổn định |
| OAuth2/OIDC với nhà cung cấp ngoài | Có thể thử phân quyền bằng principal giả lập hoặc mock các thành phần tích hợp | Khi cần xác minh redirect URI, cookie, callback và trao đổi token qua các bên |

Hai ranh giới thường bị hiểu sai:

**Thứ nhất, không có server không có nghĩa là không có filter.** Nếu cấu hình MockMvc đúng, Spring Security vẫn có thể thực thi xác thực, từ chối truy cập, kiểm tra CSRF, ghi security headers và chuyển request tới controller. Việc filter chạy hay không là đặc tính **của cấu hình test**.

**Thứ hai, một MockMvc test “xanh” không bảo đảm đường truyền thật an toàn.** Ví dụ, một test có thể xác nhận ứng dụng đặt `Secure` cho session cookie nhưng không thể xác minh reverse proxy ngoài production thực sự dùng HTTPS hoặc chuyển tiếp `X-Forwarded-Proto` đúng. Có thể viết thêm bài kiểm tra cấu hình proxy ở môi trường tích hợp.

### Lựa chọn mức kiểm thử

~~~mermaid
flowchart TD
    A["Cần kiểm chứng điều gì?"] --> B{"Luật MVC / SecurityFilterChain<br/>trong ứng dụng?"}
    B -->|Có| C["MockMvc + spring-security-test"]
    B -->|Không| D{"Cần giao tiếp HTTP thật<br/>với container?"}
    D -->|Có| E["@SpringBootTest(RANDOM_PORT)<br/>+ HTTP client"]
    D -->|Không| F["Chọn test nhỏ hơn:<br/>unit test / method security test"]
    C --> G["Bổ sung integration test khi<br/>có rủi ro hạ tầng hoặc cấu hình deploy"]
~~~

Để thật sự mở cổng HTTP, có thể dùng:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void publicEndpointIsReachableOverHttp() {
        ResponseEntity<String> response =
            http.getForEntity("/api/public", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }
}
~~~

Đoạn ví dụ giả định các import tương ứng của JUnit, Spring Boot, `ResponseEntity`, `HttpStatus` và AssertJ; `TestRestTemplate` thuộc `org.springframework.boot.test.web.client.TestRestTemplate`. Khác với `MockMvc`, client trong ví dụ này gửi request tới server ở cổng ngẫu nhiên do Spring Boot khởi động. Cũng có thể dùng `WebTestClient.bindToServer()`; cần phân biệt với `WebTestClient` gắn vào application context hoặc `MockMvcWebTestClient`, vì các cách gắn context đó cũng **không thực hiện HTTP qua mạng**.

Nếu đang kiểm thử ứng dụng **Reactive/WebFlux**, không dùng `MockMvc` để giả lập pipeline WebFlux: hãy sử dụng `WebTestClient` cùng công cụ `spring-security-test` phù hợp cho reactive security. Nguyên tắc phân biệt “được bind vào context” và “được bind vào server” vẫn tương tự.

## 6. Những lỗi làm kiểm thử bảo mật mất ý nghĩa

**Bỏ filter rồi kết luận endpoint đã được bảo vệ.** Ví dụ `@AutoConfigureMockMvc(addFilters = false)` hay `standaloneSetup(...)` không tích hợp Spring Security có thể trả 200/201 khi user ẩn danh. Kiểm tra việc filters được nạp và viết ít nhất một ca truy cập **bị từ chối** cho cùng endpoint.

**Nhầm 401 với 403.** 401 thường biểu thị chưa xác thực và cần cơ chế đăng nhập; 403 thường biểu thị đã xác thực nhưng không đủ quyền, hoặc bị chặn bởi CSRF. Tuy vậy, thứ tự filter và entry point quyết định kết quả cụ thể; không gán cứng một status cho mọi kiểu login.

**Quên CSRF rồi đổ lỗi cho phân quyền.** Một `POST` với `@WithMockUser(roles = "EDITOR")` vẫn có thể nhận 403 nếu thiếu CSRF token. Thêm `with(csrf())` để cô lập quy tắc phân quyền; làm riêng một ca thiếu/CSRF token không hợp lệ để kiểm tra cơ chế bảo vệ.

**Dùng `@WithMockUser` để chứng minh mật khẩu đúng.** Annotation này cấp một danh tính đã được xác thực trong context; nó không đi qua login endpoint, password encoder hoặc user lookup. Muốn thử xác thực, gửi credentials thực sự qua cơ chế đã cấu hình.

**Dùng `with(jwt())` để chứng minh JWT có chữ ký hợp lệ.** Processor này được thiết kế cho phép thử phân quyền nhanh với một authentication giả lập. Muốn thử bảo vệ chữ ký/expiry/issuer/audience, gửi bearer token thật và cấu hình decoder, hoặc tạo ca kiểm thử chuyên biệt cho decoder.

**Đồng nhất `@SpringBootTest` với “đang chạy HTTP thật”.** `WebEnvironment.MOCK` không mở HTTP port. Ngay cả trong test dùng `RANDOM_PORT`, một request gửi qua đối tượng `MockMvc` vẫn không đi qua cổng; chỉ request từ HTTP client hướng đến cổng server mới thực sự làm điều đó.

## 7. Bảng ca kiểm thử tối thiểu nên có

Với endpoint cần xác thực, phân quyền và CSRF, một bộ ca có giá trị nên bao phủ cả thành công và thất bại:

| Tình huống | Request / danh tính | Kỳ vọng trong cấu hình ở mục 3 |
| --- | --- | --- |
| Public | `GET /api/public`, ẩn danh | 200 |
| Đường dẫn riêng tư | `GET /api/profile`, ẩn danh | 401 (HTTP Basic) |
| Đủ quyền, CSRF hợp lệ | `POST /api/orders`, `EDITOR` và `csrf()` | 201 |
| Sai quyền, CSRF hợp lệ | `POST /api/orders`, `VIEWER` và `csrf()` | 403 |
| Đủ quyền, thiếu CSRF | `POST /api/orders`, `EDITOR` nhưng không có `csrf()` | 403 |

Khi hệ thống có JWT/OIDC, bổ sung các phép thử tương ứng cho thiếu scope, token hết hạn, chữ ký sai, sai issuer/audience và callback không hợp lệ. Phân tách rõ nhóm dùng **authentication giả lập** để thử *authorization* với nhóm gửi **credentials/token thực** để thử *authentication*.

## 8. Tự luyện tập

1. Thêm endpoint `DELETE /api/orders/{id}` chỉ cho `ADMIN`. Viết ba test: `EDITOR` bị 403, `ADMIN` có CSRF token thành công, `ADMIN` thiếu CSRF token bị 403.
2. Bỏ tích hợp security filters khỏi cấu hình test, chạy lại các phép thử từ chối truy cập và giải thích vì sao kết quả thay đổi. Khôi phục filters trước khi hoàn thành.
3. Đổi cấu hình từ HTTP Basic sang form login và quan sát trạng thái của request ẩn danh. Giải thích khi nào nhận 302 thay vì 401.
4. Bổ sung một integration test chạy trên `RANDOM_PORT`, gửi request bằng HTTP client thật và so sánh phạm vi kiểm thử với test `MockMvc` tương ứng.

**Điểm cần nhớ:** `MockMvc` là công cụ rất phù hợp để kiểm chứng các quy tắc Spring MVC/Spring Security trong tiến trình test, miễn là bộ lọc và context được thiết lập chính xác. Nó không thay thế các phép thử có máy chủ và đường truyền HTTP thật khi yêu cầu bảo mật phụ thuộc container, TLS, proxy hay luồng giao tiếp với hệ thống bên ngoài.
