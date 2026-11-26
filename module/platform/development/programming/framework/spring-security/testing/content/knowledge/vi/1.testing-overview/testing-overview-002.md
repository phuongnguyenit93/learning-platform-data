# Phân biệt kiểm thử xác thực, phân quyền và các cơ chế bảo vệ

## Mục tiêu học tập

Trong một ứng dụng sử dụng Spring Security, cùng một phản hồi `403 Forbidden` có thể xuất hiện do thiếu quyền, thiếu CSRF token hoặc do chính sách khác. Nếu chỉ nhìn vào mã HTTP, bài kiểm thử rất dễ được đánh dấu “thành công” dù cơ chế cần kiểm chứng chưa từng chạy.

Sau bài học này, bạn có thể:

- Phân biệt ba nhóm mục tiêu: **xác thực (authentication)**, **phân quyền (authorization)** và **các cơ chế bảo vệ HTTP**.
- Chọn cách kiểm thử phù hợp cho ứng dụng Servlet với `MockMvc` và ứng dụng Reactive với `WebTestClient`.
- Xác định khi nào `@WithMockUser`, principal trong `SecurityContext`, `jwt()`, `oauth2Login()` hoặc `oidcLogin()` chỉ giả lập **kết quả** của xác thực.
- Thiết kế test có ca được phép, bị từ chối và phát hiện lỗi do nhầm lẫn giữa `401`, `403`, CSRF, CORS, cookie và security headers.
- Giải thích bằng chứng mà từng test cung cấp và những phần vẫn cần kiểm thử tích hợp thực tế.

Bài này thuộc phần tổng quan của **SPRING_SECURITY_TESTING**: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trong cả ứng dụng Servlet và Reactive, bao gồm các danh tính JWT/OAuth2/OIDC giả lập.

## 1. Ba câu hỏi khác nhau trong một request

Giả sử một ứng dụng bán hàng có các thao tác sau:

- `GET /api/me`: xem thông tin của tài khoản đang đăng nhập.
- `GET /api/admin/reports`: xem báo cáo quản trị.
- `POST /api/orders`: tạo đơn hàng.
- `GET /api/orders/{id}`: xem một đơn hàng cụ thể.

Với mỗi request, Spring Security có thể cần trả lời ba câu hỏi:

| Nhóm kiểm thử | Câu hỏi cần trả lời | Ví dụ yêu cầu |
| --- | --- | --- |
| **Xác thực** | “Người gửi request được nhận diện bằng cách nào, và bằng chứng danh tính có hợp lệ không?” | Sai mật khẩu hoặc JWT hết hạn phải bị từ chối. |
| **Phân quyền** | “Danh tính đã xác thực được phép thực hiện hành động này trên tài nguyên này không?” | `ROLE_USER` không được xem báo cáo quản trị; chủ đơn hàng không được xem đơn của người khác. |
| **Cơ chế bảo vệ HTTP** | “Request/response có tuân thủ các quy tắc bảo vệ bổ sung không?” | `POST` cần CSRF token nếu CSRF được bật; CORS chỉ cho phép origin hợp lệ; response có security headers theo cấu hình. |

Một chính sách bảo mật có thể trải trên cả ba nhóm. Ví dụ, một yêu cầu `POST /api/orders` đến từ người dùng đã xác thực nhưng thiếu CSRF token có thể bị chặn **trước** khi ứng dụng kiểm tra quyền truy cập đơn hàng. Do vậy, từng bài test cần nói rõ mình đang xác nhận điều gì.

### 1.1. Một luồng xử lý với nhiều điểm kiểm soát

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["Security Filter Chain / WebFilter Chain"]
    F --> P{"Bảo vệ HTTP hợp lệ?"}
    P -->|Không| PX["Từ chối hoặc phản hồi theo chính sách"]
    P -->|Có| A{"Thông tin xác thực hợp lệ?"}
    A -->|Không| AX["Authentication entry point / lỗi xác thực"]
    A -->|Có| Z{"Có quyền với URL và tài nguyên?"}
    Z -->|Không| ZX["Access denied"]
    Z -->|Có| H["Controller / Handler"]
    H --> M["Kiểm tra quyền ở method (nếu có)"]
    M --> O["Response và security headers"]
~~~

Sơ đồ trên mô tả **các trách nhiệm kiểm tra**, không phải thứ tự cố định của mọi filter. Thứ tự thực tế phụ thuộc cấu hình Spring Security và loại ứng dụng. Chẳng hạn, `CsrfFilter` có thể chặn request ngay cả khi bạn đã gắn một người dùng giả lập vào ngữ cảnh.

### 1.2. Các trạng thái HTTP cần đọc đúng ngữ cảnh

| Kết quả thường gặp | Cách hiểu | Không nên suy diễn |
| --- | --- | --- |
| `200 OK`, `201 Created`, `204 No Content` | Request được xử lý thành công theo hợp đồng API. | Không tự chứng minh chính sách đã chặn người không có quyền. |
| `401 Unauthorized` | Request chưa có xác thực hợp lệ, thường kèm cơ chế thách thức xác thực. | Không có nghĩa đây là trường hợp “đăng nhập rồi nhưng thiếu quyền”. |
| `403 Forbidden` | Server từ chối thực hiện request; có thể do phân quyền, CSRF hoặc điều kiện bảo mật khác. | Không tự chứng minh phép kiểm tra role/authority đã chạy. |
| `302 Found` | Có thể là chuyển hướng đến trang đăng nhập trong ứng dụng dùng form login. | Không phải mọi request chưa xác thực đều phải trả `401`. |
| `404 Not Found` | Tài nguyên không có hoặc ứng dụng cố ý ẩn sự tồn tại của nó. | Không thể tự suy ra nguyên nhân là thiếu quyền. |

Vì thế, **cùng một endpoint** có thể cần nhiều bài test, và status phải được chọn theo cấu hình thực tế thay vì áp dụng máy móc một bảng “401/403” cho mọi ứng dụng.

## 2. Kiểm thử xác thực: chứng minh bằng chứng danh tính được kiểm tra

Xác thực là quá trình chuyển từ **bằng chứng** (mật khẩu, session, bearer token, authorization code...) thành một `Authentication` đáng tin cậy. Một bài test xác thực cần kiểm tra đường đi mà server sử dụng để chấp nhận hoặc từ chối bằng chứng đó.

### 2.1. Phân biệt “đưa credential thật vào request” và “gắn sẵn người dùng đã xác thực”

Trong Spring Security Test, hai thao tác sau có ý nghĩa khác nhau:

~~~java
// Gửi thông tin HTTP Basic; server phải xử lý username/password.
mvc.perform(get("/api/me")
        .with(httpBasic("linh", "mat-khau-test")))
    .andExpect(status().isOk());

// Gắn trực tiếp một Authentication giả lập vào ngữ cảnh test.
mvc.perform(get("/api/me")
        .with(user("linh").roles("USER")))
    .andExpect(status().isOk());
~~~

Với điều kiện test context sử dụng `httpBasic()` và có tài khoản `linh` thích hợp, request đầu tiên có thể kiểm tra quy trình tiếp nhận và xác minh mật khẩu. Request thứ hai hữu ích khi chỉ cần một **đầu vào đã xác thực** để thử phân quyền; nó không xác minh mật khẩu.

Tương tự, `@WithMockUser` chuẩn bị `SecurityContext` cho test. Nó không tự gọi endpoint đăng nhập, không lấy token từ OAuth2 provider và không kiểm tra chữ ký JWT.

| Tiện ích/cách gửi request | Có đi qua bước kiểm tra credential thực? | Phù hợp với câu hỏi |
| --- | --- | --- |
| `@WithMockUser` | Không; tạo authentication giả lập. | Người có role/authority này có được truy cập không? |
| `user("linh")` với MockMvc | Không; giả lập authentication cho request. | Phân quyền khi principal là `linh`. |
| `httpBasic("linh", "sai")` | Có, nếu filter/provider thật được cấu hình trong context. | Mật khẩu sai có bị từ chối không? |
| Form login qua POST | Có, nếu test thực sự chạy filter login. | Username/password, login success/failure và session hoạt động đúng không? |
| `jwt()` / `mockJwt()` | Không; tạo token authentication đã được chấp nhận trong test. | Claims/scopes sau xác thực dẫn đến quyết định quyền nào? |
| HTTP `Authorization: Bearer ...` | Có thể, nếu resource server và decoder thực sự được chạy. | Token sai/hết hạn/không hợp lệ có bị từ chối không? |
| `oauth2Login()` / `oidcLogin()` | Không chạy toàn bộ quá trình trao đổi với identity provider. | Ứng dụng xử lý principal OAuth2/OIDC sau đăng nhập thế nào? |

### 2.2. Ví dụ xác thực HTTP Basic thực sự bằng MockMvc

Để thử hai trường hợp mật khẩu đúng và sai, hãy tạo một ứng dụng Servlet thử nghiệm với người dùng xác định. Cấu hình dưới đây chỉ nhằm minh họa và có thể đưa vào một ứng dụng Spring MVC nhỏ.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DemoSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .authenticated()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
            // CSRF vẫn bật theo cấu hình mặc định.
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("linh")
                .password(encoder.encode("mat-khau-test"))
                .roles("USER")
                .build(),
            User.withUsername("mai")
                .password(encoder.encode("mat-khau-admin"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Controller minh họa:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
class DemoController {

    @GetMapping("/api/public/status")
    String status() {
        return "up";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin/reports")
    String adminReports() {
        return "sensitive-report";
    }

    @PostMapping("/api/orders")
    ResponseEntity<String> createOrder() {
        return ResponseEntity.ok("created");
    }
}
~~~

Với `@SpringBootTest` và `@AutoConfigureMockMvc`, Spring Boot tạo `MockMvc` có tích hợp filter của ứng dụng. Các test dưới đây chạy trong context chứa `DemoSecurityConfig` và `DemoController`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("linh", "mat-khau-sai")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("linh", "mat-khau-test")))
            .andExpect(status().isOk())
            .andExpect(content().string("linh"));
    }

    @Test
    void publicStatusDoesNotNeedAuthentication() throws Exception {
        mvc.perform(get("/api/public/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("up"));
    }
}
~~~

Cặp test mật khẩu đúng/sai cung cấp bằng chứng về **nhánh xác thực HTTP Basic** trong context này. Nó chưa đủ để khẳng định cơ chế khóa tài khoản, quản lý mật khẩu, đăng nhập form, đăng nhập đa yếu tố hay OAuth2/OIDC đều đúng; những phần đó có đường xử lý khác và cần test riêng.

### 2.3. JWT/OAuth2/OIDC: tránh nhầm “fake principal” với “token đã được kiểm tra”

Một API resource server thường cần kiểm tra token theo nhiều chiều: định dạng, chữ ký (với JWT), thời hạn, issuer, audience và các điều kiện hệ thống đặt ra. Sau xác thực, `Authentication` chứa principal cùng `GrantedAuthority` dùng trong phân quyền.

Với Servlet, `.with(jwt())` hoặc `.with(opaqueToken())` tạo trạng thái đã xác thực cho request. `oauth2Login()` và `oidcLogin()` cũng giả lập người dùng đã hoàn tất đăng nhập OAuth2/OIDC. Các tiện ích này đặc biệt phù hợp để cô lập kiểm thử **chính sách quyền và logic sau đăng nhập**.

Ví dụ, đoạn sau mô tả principal JWT có scope `orders.read`:

~~~java
mvc.perform(get("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Test chỉ có ý nghĩa `200` khi ứng dụng thực sự có endpoint `/api/orders/123` và chính sách cho phép authority đó; phần mã là ví dụ cách **thiết lập danh tính**, không phải minh chứng về endpoint trong cấu hình demo phía trên.

Để thử trường hợp **JWT chữ ký sai hoặc hết hạn bị từ chối**, phải gửi bearer token qua pipeline xác thực thực tế của resource server và thiết lập `JwtDecoder`/cơ chế xác minh phù hợp. Nếu thay decoder bằng mock chỉ trả lỗi theo kịch bản, test xác minh cách ứng dụng **xử lý lỗi decoder**, còn chữ ký mật mã phải được kiểm tra ở một bài test có khóa/decoder hoạt động thật.

Với OIDC, `oidcLogin()` hữu ích để thử logic phụ thuộc ID token hoặc các thuộc tính user, nhưng không tự bao phủ authorization code flow, xác thực `state`/`nonce`, callback hay hành vi của bên cung cấp danh tính. Nếu các bước này thuộc phạm vi ứng dụng, cần thêm kiểm thử tích hợp hoặc end-to-end.

## 3. Kiểm thử phân quyền: giả định danh tính đúng và hỏi “được làm gì?”

Phân quyền bắt đầu **sau khi** đã biết danh tính. Có thể kiểm tra ở ba cấp độ bổ sung cho nhau:

1. **Quyền theo URL và HTTP method**: chẳng hạn `GET /api/admin/reports` chỉ dành cho quản trị viên.
2. **Quyền tại phương thức Java**: chẳng hạn `@PreAuthorize("hasRole('ADMIN')")` bảo vệ service dù được gọi từ nơi khác ngoài controller.
3. **Quyền theo đối tượng/quan hệ**: chẳng hạn một người chỉ được xem đơn hàng họ sở hữu.

### 3.1. Kiểm tra cả được phép và bị từ chối ở tầng HTTP

Trong cấu hình Servlet đã nêu, `/api/admin/**` yêu cầu `ROLE_ADMIN`. Bài kiểm thử quyền nên kiểm tra đủ hai mặt:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void regularUserCannotReadAdminReports() throws Exception {
        mvc.perform(get("/api/admin/reports")
                .with(user("linh").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminReports() throws Exception {
        mvc.perform(get("/api/admin/reports")
                .with(user("mai").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("sensitive-report"));
    }
}
~~~

Ở đây, `user()` chủ động bỏ qua bước xác minh mật khẩu để thử đúng câu hỏi phân quyền: một người đã đăng nhập có role như vậy sẽ được đối xử ra sao. Điều quan trọng là test **người dùng thường bị từ chối**; nếu quy tắc `hasRole("ADMIN")` bị xóa, test này cần thất bại.

### 3.2. Role, authority và scope không đồng nghĩa

Spring Security thường biểu diễn quyền bằng các chuỗi `GrantedAuthority`:

| Cấu hình/giả lập | Authority được đặt hoặc yêu cầu |
| --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` |
| `user("mai").roles("ADMIN")` | `ROLE_ADMIN` |
| `@WithMockUser(authorities = "orders:read")` | `orders:read` |
| `hasRole("ADMIN")` | Thông thường kiểm tra `ROLE_ADMIN` |
| `hasAuthority("SCOPE_orders.read")` | Kiểm tra đúng chuỗi `SCOPE_orders.read` |
| `jwt().authorities(...)` | Authorities được truyền trực tiếp; không bắt buộc do token claim tự ánh xạ. |

Khi cấu hình bảo vệ một API bằng `hasAuthority("SCOPE_orders.read")`, hai request thử sau sẽ dẫn đến hai kết quả khác nhau:

~~~java
mvc.perform(get("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
    .andExpect(status().isForbidden());
~~~

Điều kiện tiên quyết của ví dụ là endpoint và `SecurityFilterChain` tương ứng đã được khai báo. Cả hai request đều có principal JWT giả lập; điểm khác biệt **chỉ** là quyền. Khi dùng token thật, còn phải kiểm tra cách converter ánh xạ claims như `scope`, `scp` hoặc claims tùy chỉnh sang authorities.

### 3.3. Method security và quyền theo đối tượng

Ví dụ một service cần kiểm tra người gọi có phải chủ sở hữu đơn hàng hay không:

~~~java
@Service
class OrderService {

    private final OrderRepository orders;

    OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
    public OrderDetail viewOrder(long orderId) {
        return orders.findDetail(orderId);
    }
}
~~~

Đây là mã phác họa: dự án cần có các kiểu `OrderRepository`, `OrderDetail` và bean `orderAccess` với phương thức `canRead(...)`. Bật method security thích hợp, chẳng hạn `@EnableMethodSecurity` cho ứng dụng Servlet.

Kiểm thử có ý nghĩa phải gọi **bean được Spring quản lý** và tạo ít nhất hai dữ liệu: đơn của `linh` và đơn của người khác. Test phải cho thấy `linh` được xem đơn của mình nhưng bị từ chối khi gọi cùng phương thức với ID không thuộc mình. Gọi object bằng `new OrderService(...)` có thể bỏ qua proxy/interceptor của method security và khiến test không kiểm tra đúng cơ chế.

**Bài học then chốt:** một người có `ROLE_USER` có thể được phép gọi `GET /api/orders/{id}` theo URL nhưng vẫn không được xem **mọi** đơn hàng. Role/authority là điều kiện cần trong nhiều thiết kế; kiểm tra quyền sở hữu tài nguyên có thể là điều kiện bổ sung.

## 4. Kiểm thử các cơ chế bảo vệ HTTP

Phần bảo vệ HTTP không chỉ là hỏi ai đăng nhập và có vai trò nào. Nó còn kiểm soát cách request đến ứng dụng và cách phản hồi được trình duyệt xử lý.

### 4.1. CSRF: người dùng hợp lệ cũng có thể bị chặn khi đổi trạng thái

**Cross-Site Request Forgery** nhắm vào trường hợp trình duyệt tự gửi thông tin xác thực của người dùng (ví dụ cookie phiên) cho một yêu cầu do trang khác kích hoạt. Khi Spring Security bật CSRF, những phương thức làm thay đổi trạng thái thường phải mang token CSRF hợp lệ.

Dùng `MockMvc` để thử ba tình huống với cùng người dùng đã xác thực:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void authenticatedPostWithoutCsrfIsDenied() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("linh").roles("USER")))
        .andExpect(status().isForbidden());
}

@Test
void authenticatedPostWithInvalidCsrfIsDenied() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("linh").roles("USER"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}

@Test
void authenticatedPostWithValidCsrfIsAllowed() throws Exception {
    mvc.perform(post("/api/orders")
            .with(user("linh").roles("USER"))
            .with(csrf()))
        .andExpect(status().isOk());
}
~~~

Đây là **kiểm thử CSRF**, không phải kiểm thử “người dùng không được tạo đơn hàng”. Nếu muốn thử role/authority ở `POST /api/orders`, hãy cung cấp CSRF token hợp lệ trong tất cả request của nhóm test phân quyền để lỗi CSRF không che lỗi phân quyền.

CSRF phải được đối chiếu với mô hình xác thực thực tế. Một API chỉ sử dụng bearer token trong header, không dựa vào credential tự động của trình duyệt, có thể được cấu hình bỏ qua CSRF sau khi phân tích nguy cơ. Khi CSRF bị vô hiệu hóa có chủ đích, test cần xác minh **chính sách đang áp dụng**, không giữ nguyên kỳ vọng `403` cho mọi POST.

### 4.2. CORS: chính sách cho trình duyệt truy cập tài nguyên khác origin

**Cross-Origin Resource Sharing (CORS)** quy định origin nào được trình duyệt phép truy cập một response cross-origin. Đối với request cần preflight, trình duyệt gửi `OPTIONS` kèm `Origin` và `Access-Control-Request-Method`.

CORS không thay thế xác thực và phân quyền: một origin nằm trong danh sách cho phép vẫn phải gửi thông tin xác thực và tuân thủ quyền truy cập của endpoint. Tương tự, một client không phải trình duyệt có thể tự gửi HTTP request, nên CORS không phải hàng rào chặn mọi cuộc gọi trái phép từ bên ngoài.

Giả sử ứng dụng đã cấu hình CORS cho phép `https://app.example.test` truy cập `/api/**` với phương thức `POST`. Có thể thử preflight:

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@Test
void allowedOriginReceivesCorsApproval() throws Exception {
    mvc.perform(options("/api/orders")
            .header("Origin", "https://app.example.test")
            .header("Access-Control-Request-Method", "POST"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Access-Control-Allow-Origin", "https://app.example.test"));
}
~~~

Với origin không được cho phép, test có thể kiểm tra **không có** `Access-Control-Allow-Origin` tương ứng; mã HTTP chính xác phụ thuộc cấu hình CORS và filter đang chạy. Nếu ứng dụng Servlet tự thiết lập `MockMvc`, phải chắc chắn CORS filter và security filter chain của ứng dụng được đưa vào test context. Nếu không, bài test chỉ đang thử một cấu hình khác.

Đặc biệt, preflight thường **không mang cookie phiên**. Khi cấu hình CORS trong Spring Security, tích hợp CORS phải xử lý preflight phù hợp trước khi cơ chế xác thực yêu cầu một session mà request không có.

### 4.3. Security headers: kiểm tra thuộc tính của response

Một số lớp bảo vệ đến từ header để hướng dẫn trình duyệt xử lý nội dung an toàn hơn. Ví dụ thường gặp:

| Header | Ý nghĩa điển hình | Điều cần kiểm tra |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Hạn chế trình duyệt suy đoán kiểu nội dung. | Header có ở các response nằm trong phạm vi chính sách. |
| `X-Frame-Options` | Kiểm soát việc trang bị hiển thị trong frame ở các trình duyệt hỗ trợ. | Giá trị phản ánh chính sách, ví dụ `DENY` hoặc `SAMEORIGIN`. |
| `Content-Security-Policy` | Giới hạn nguồn nội dung/script theo chỉ thị CSP. | Đúng policy đã cấu hình; không mặc định giả định Spring bật CSP. |
| `Strict-Transport-Security` | Yêu cầu trình duyệt ưu tiên HTTPS sau khi nhận header hợp lệ. | Kiểm tra trên response HTTPS; HSTS thường không được thêm cho HTTP. |
| `Cache-Control` | Điều khiển cache để hạn chế lưu trữ nội dung nhạy cảm theo chính sách. | Cache headers phản ánh hợp đồng của API/trang nhạy cảm. |

Ví dụ đối với cấu hình Spring Security Servlet mặc định có bổ sung các header tương ứng:

~~~java
@Test
void responseContainsConfiguredProtectionHeaders() throws Exception {
    mvc.perform(get("/api/public/status"))
        .andExpect(status().isOk())
        .andExpect(header().string("X-Content-Type-Options", "nosniff"))
        .andExpect(header().string("X-Frame-Options", "DENY"));
}
~~~

Nếu ứng dụng đã tùy biến header, cần đổi kỳ vọng tương ứng. Ví dụ, CSP thường cần khai báo rõ trong cấu hình trước khi test mong đợi `Content-Security-Policy`.

Khi thử HSTS bằng `MockMvc`, cần tạo request bảo mật, chẳng hạn `get(...).secure(true)`. Nếu chạy qua reverse proxy, còn phải kiểm chứng cách ứng dụng xác định scheme HTTPS dựa trên cấu hình trusted forwarding headers của môi trường thật.

### 4.4. Session, cookie, đăng nhập và đăng xuất

Với ứng dụng có phiên đăng nhập, một nhóm kiểm thử độc lập nên kiểm tra:

- Session được tạo và lưu ngữ cảnh bảo mật đúng khi đăng nhập thành công.
- Đăng xuất làm cho trạng thái xác thực cũ không còn dùng được theo chính sách.
- Session fixation protection thay đổi session ID hoặc thực hiện chiến lược bảo vệ được cấu hình khi đăng nhập.
- Cookie có `Secure`, `HttpOnly`, `SameSite` phù hợp với cách hệ thống sử dụng HTTPS và cross-site requests.
- Tài nguyên riêng tư không vô tình bị cache hoặc tiết lộ nội dung cho người không có quyền.

Để kiểm tra vòng đời đăng nhập/đăng xuất, nên thực hiện luồng **form login thật** hoặc luồng xác thực thực tế trong test context, giữ session giữa các request và xác minh trạng thái trước/sau. Chỉ dùng `@WithMockUser` không chứng minh session được tạo, lưu, xoay vòng hoặc hủy đúng cách.

`SameSite` còn liên quan đến CSRF nhưng không thể thay thế mọi trường hợp cần kiểm tra CSRF token. Ngược lại, một số hệ thống cần cookie `SameSite=None; Secure` cho luồng đăng nhập liên quan nhiều origin; cần kiểm tra theo kiến trúc ứng dụng thay vì đặt một giá trị cố định cho mọi dự án.

## 5. Servlet và Reactive: cùng mục tiêu, khác cách mang SecurityContext

Trong ứng dụng **Servlet**, Spring Security tích hợp vào Servlet filter chain và thông tin xác thực thường được truy cập qua `SecurityContextHolder` theo ngữ cảnh xử lý request. Trong ứng dụng **Reactive/WebFlux**, thông tin xác thực được truyền theo Reactor context qua `ReactiveSecurityContextHolder` và WebFilter chain.

Vì vậy, cùng một bài toán “người dùng thường không được xem báo cáo quản trị” có thể được viết khác nhau.

### 5.1. Servlet: MockMvc và annotation

~~~java
@Test
@WithMockUser(username = "linh", roles = "USER")
void servletUserIsDenied() throws Exception {
    mvc.perform(get("/api/admin/reports"))
        .andExpect(status().isForbidden());
}
~~~

Import `@WithMockUser` từ `org.springframework.security.test.context.support.WithMockUser`. Khi dùng `@SpringBootTest` + `@AutoConfigureMockMvc`, test thường nhận cấu hình security từ application context. Nếu tự dựng client qua `MockMvcBuilders.webAppContextSetup(...)`, cần tích hợp đúng `springSecurity()` và filter chain.

### 5.2. Reactive: WebTestClient và mockUser

Với một ứng dụng **WebFlux riêng** có `SecurityWebFilterChain` bảo vệ `/api/admin/**` bằng `hasRole("ADMIN")`, có thể gắn `WebTestClient` vào application context:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveSecurityContractTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void userCannotReadAdminReports() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/admin/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdminReports() {
        client.mutateWith(mockUser("mai").roles("ADMIN"))
            .get().uri("/api/admin/reports")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void postRequiresCsrfToken() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("linh").roles("USER"))
            .mutateWith(csrf())
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Các đoạn code Reactive giả định application context có đủ handler cho hai đường dẫn, cấu hình cho phép user đã xác thực tạo đơn và CSRF đang bật. Nếu bạn dùng OAuth2 resource server WebFlux, `mockJwt()` cung cấp principal JWT giả lập; còn việc gửi bearer token thật sẽ kiểm tra đường xác thực của server.

**Giới hạn quan trọng:** `mutateWith(mockUser(...))` và `mockJwt()` dành cho `WebTestClient` gắn vào context/mock server của test. Khi client gọi server thật qua HTTP, không thể dùng trạng thái mock ở JVM test để “đăng nhập hộ” request bên server; phải gửi credential hoặc token phù hợp qua mạng.

### 5.3. Đừng bỏ sót kiểm thử method security của Reactive

Khi phương thức Reactive cần bảo vệ bằng `@PreAuthorize`, sử dụng cơ chế như `@EnableReactiveMethodSecurity` và gọi bean Spring đúng cách. Một test cho `Mono`/`Flux` cần **subscribe** thông qua bước xác minh (ví dụ `StepVerifier`), vì logic Reactive thường chỉ thực thi khi có subscriber. Việc tạo ra `Mono` mà không thực thi có thể khiến bài test không chạm tới kiểm tra bảo mật.

## 6. Ma trận kiểm thử: ghép đúng mục tiêu với ca thử

Bảng sau dùng cấu hình HTTP Basic + CSRF mặc định trong ứng dụng Servlet minh họa; riêng hai hàng cuối mô tả chính sách JWT/OAuth2 bổ sung khi hệ thống thực sự có các endpoint đó.

| Mục tiêu | Đầu vào | Kỳ vọng | Bằng chứng nên thu thập |
| --- | --- | --- | --- |
| Xác thực | `GET /api/me` không credential | `401` | Endpoint riêng tư không lộ thông tin. |
| Xác thực | HTTP Basic sai mật khẩu | `401` | Provider không chấp nhận credential sai. |
| Xác thực | HTTP Basic đúng mật khẩu | `200` | Principal sau xác thực trùng với tài khoản. |
| Phân quyền | `ROLE_USER` gọi `GET /api/admin/reports` | `403` | User được xác thực nhưng thiếu role. |
| Phân quyền | `ROLE_ADMIN` gọi cùng API | `200` | Có đúng quyền và nhận dữ liệu dự kiến. |
| CSRF | User hợp lệ `POST /api/orders` thiếu token | `403` | Chặn vì CSRF token không hợp lệ/không có. |
| CSRF | User hợp lệ, token hợp lệ | `200` | Cùng thao tác được xử lý khi đủ điều kiện CSRF. |
| CORS | Preflight từ origin được cho phép | Theo config, có CORS allow headers | Browser được cung cấp chính sách phù hợp. |
| CORS | Preflight từ origin không được phép | Không cấp quyền CORS | Không trả header cho phép origin trái chính sách. |
| Security headers | Gọi endpoint công khai | Theo security headers config | Response có các header yêu cầu. |
| Phân quyền theo tài nguyên | `linh` xem đơn của người khác | `403` hoặc `404` theo thiết kế | Không tiết lộ nội dung hay thay đổi dữ liệu. |
| JWT phân quyền | JWT mock thiếu `SCOPE_orders.read` | `403` | Chính sách authority được thực thi. |
| JWT xác thực | Bearer token thật hết hạn/chữ ký sai | `401` theo entry point | Decoder/validator thật từ chối token. |

Phải đối chiếu mã status với cấu hình cụ thể. Nếu ứng dụng chỉ dùng form login, anonymous request có thể dẫn tới `302`; nếu CSRF bị vô hiệu hóa có chủ đích, kết quả POST khác; nếu chính sách ẩn tài nguyên trả `404`, điều đó phải được ghi rõ trong hợp đồng bảo mật.

### 6.1. Cách thiết kế test để biết chính xác điều gì gây ra thất bại

Ví dụ bạn muốn chứng minh `ROLE_USER` bị chặn ở một endpoint `POST /api/admin/reports`. Nếu không gắn CSRF token, request có thể nhận `403` dù bạn **xóa sạch** quy tắc `hasRole("ADMIN")`.

Cách xây dựng nhóm test phân quyền:

1. Chuẩn bị **cùng một payload hợp lệ** và cùng CSRF token hợp lệ cho cả hai request.
2. Giữ nguyên mọi điều kiện khác, chỉ thay role/authority từ người không có quyền sang người có quyền.
3. Xác minh `403` cho người không có quyền và response thành công cho người có quyền.
4. Kiểm tra tác động nghiệp vụ khi thích hợp: người bị từ chối không làm thay đổi dữ liệu.
5. Tạm thời nới một quy tắc trong môi trường test để bảo đảm test từ chối sẽ thất bại (kiểm tra độ nhạy của bài test).

Với test CSRF, thao tác ngược lại: giữ nguyên user và quyền, chỉ thay token từ thiếu/sai sang hợp lệ. Với test xác thực, giữ nguyên endpoint và quyền cần thiết, chỉ thay credential.

Đây là cách **cô lập nguyên nhân**, giúp một phản hồi bị từ chối cung cấp bằng chứng rõ ràng thay vì tình cờ trùng status.

## 7. Chọn lớp kiểm thử theo rủi ro cần phát hiện

| Lớp kiểm thử | Công cụ điển hình | Phù hợp để chứng minh | Chưa đủ để chứng minh |
| --- | --- | --- | --- |
| Unit test quy tắc nghiệp vụ | JUnit, Mockito, assertions | Các quy tắc ownership, state và logic nghiệp vụ. | Chuỗi filter hoặc proxy bảo mật của Spring được chạy. |
| Test method security | Spring context + `@WithMockUser`, bean thật | Kiểm tra annotation/interceptor, quyền theo phương thức. | Login và xác thực bearer token thật. |
| MVC slice test | `@WebMvcTest` + security config phù hợp | Đường web đã được nạp trong slice. | Mọi cấu hình production nếu slice thiếu bean/filter. |
| HTTP test Servlet | `@SpringBootTest` + `@AutoConfigureMockMvc` | Filter chain, xác thực request, phân quyền URL, CSRF và headers. | Mọi tình huống hệ thống triển khai thật, proxy/cookie/browser. |
| HTTP test Reactive | `WebTestClient` gắn context + `springSecurity()` | SecurityWebFilterChain, reactive authz, CSRF và handler. | Hệ thống nhận bearer token từ server xa nếu dùng mock principal. |
| Integration/E2E | HTTP client, server thật, test identity provider/browser khi cần | Credential, decoder, redirect/callback, cookies, reverse proxy, trình duyệt. | Không tự bao phủ mọi tổ hợp vai trò và tài nguyên. |

Không có lớp nào thay thế hoàn toàn lớp còn lại. Mục tiêu là đặt test ở lớp **thấp nhất vẫn quan sát được cơ chế cần chứng minh**, rồi bổ sung một số đường kiểm thử tích hợp thực tế cho những rủi ro quan trọng.

## 8. Những nhầm lẫn dễ làm test “xanh giả”

### 8.1. Thấy 403 rồi kết luận role được bảo vệ

**Nguyên nhân có thể:** request POST thiếu CSRF token; exception khác được handler chuyển thành `403`; role check chưa chạy. **Khắc phục:** cung cấp CSRF hợp lệ và thử cặp role có/không có quyền trên cùng endpoint.

### 8.2. Dùng @WithMockUser để xác minh password hoặc JWT signature

**Nguyên nhân:** annotation tạo sẵn `Authentication`; không thực hiện kiểm tra credential. **Khắc phục:** gửi credential hoặc bearer token thật qua HTTP, giữ mock principal cho các test phân quyền.

### 8.3. Dùng WebTestClient mock principal với ứng dụng chạy ở cổng thật

**Nguyên nhân:** phần state giả lập chỉ áp dụng cho mock server trong process kiểm thử. **Khắc phục:** khi kiểm tra `RANDOM_PORT`, gửi thông tin xác thực thật qua HTTP và cấu hình đối tượng xác thực/decoder thích hợp.

### 8.4. Dùng @WebMvcTest rồi nghĩ đang chạy security production

**Nguyên nhân:** slice có thể không tải đầy đủ các bean hoặc `SecurityFilterChain` mong muốn. **Khắc phục:** xác định rõ security config trong test context; nếu cần quan sát cấu hình đầy đủ, dùng `@SpringBootTest`.

### 8.5. Cho rằng CORS có thể chặn client tùy ý

**Nguyên nhân:** CORS phần lớn là cơ chế mà trình duyệt thực thi. **Khắc phục:** xác minh CORS riêng và vẫn bắt buộc xác thực/phân quyền cho API nhạy cảm.

### 8.6. Cho rằng chỉ cần test 200

**Nguyên nhân:** endpoint có thể bị mở công khai mà test của admin vẫn nhận `200`. **Khắc phục:** mỗi quy tắc quan trọng cần một ca truy cập **được phép** và một ca truy cập **bị từ chối**.

### 8.7. Chỉ gọi service mới tạo thủ công khi muốn thử @PreAuthorize

**Nguyên nhân:** đối tượng tự tạo không đi qua proxy hoặc interceptor Spring method security. **Khắc phục:** gọi bean Spring đã được bảo vệ bằng annotation phù hợp, với method security được bật trong test context.

### 8.8. Không xác minh dữ liệu sau request bị từ chối

**Nguyên nhân:** trả `403` không luôn đủ chứng minh trạng thái hệ thống an toàn nếu có đoạn mã gây tác động trước khi exception xảy ra. **Khắc phục:** với thao tác ghi dữ liệu nhạy cảm, kiểm tra thêm rằng dữ liệu không bị sửa, ghi log nhạy cảm không bị lộ và response không trả thông tin riêng tư.

## 9. Bài thực hành tổng hợp

Bạn có thể thực hành với ứng dụng MVC minh họa ở mục 2, rồi mở rộng sang WebFlux:

1. **Xác thực:** viết các ca không credential, HTTP Basic sai mật khẩu và HTTP Basic đúng mật khẩu. Giải thích tại sao `@WithMockUser` không thay thế được ba ca này.
2. **Phân quyền URL:** viết test `ROLE_USER` bị từ chối còn `ROLE_ADMIN` được xem `/api/admin/reports`. Xóa tạm quy tắc role trong môi trường thử và quan sát test nào phát hiện lỗi.
3. **CSRF:** trên `POST /api/orders`, giữ nguyên user nhưng thay token thiếu, token sai và token đúng. Chỉ ra nguyên nhân của từng phản hồi.
4. **CORS và security headers:** cấu hình một origin được phép, một origin bị chặn và thêm ít nhất hai assertion header cho response.
5. **Phân quyền theo đối tượng:** bổ sung `GET /api/orders/{id}`; hai user có cùng role nhưng khác quyền sở hữu. Kiểm tra rằng người không sở hữu không nhìn thấy đơn hàng.
6. **JWT/OAuth2/OIDC:** dựng một nhánh dùng principal giả lập để thử quyền, rồi thiết kế bài test khác đi qua đường token thật nhằm kiểm tra token không hợp lệ.
7. **Reactive:** tái tạo hai trường hợp được phép/bị từ chối bằng `WebTestClient` trong WebFlux. Nếu chạy client qua mạng, thay mock principal bằng cơ chế gửi credential thật.

Để tự đánh giá, hãy đặt tên test theo ba thành phần **điều kiện – hành động – kết quả**. Ví dụ `wrongPasswordCannotReadProfile` khác rõ ràng với `regularUserCannotReadAdminReport` và `postWithoutCsrfIsRejected`. Khi một test thất bại, tên và phần setup sẽ giúp xác định đang có lỗi ở xác thực, phân quyền hay cơ chế bảo vệ HTTP.

## 10. Kết luận

**Kiểm thử xác thực** chứng minh server chấp nhận hoặc từ chối bằng chứng danh tính đúng cách. **Kiểm thử phân quyền** chứng minh một danh tính đã xác thực chỉ được thực hiện thao tác và truy cập tài nguyên theo chính sách. **Kiểm thử cơ chế bảo vệ HTTP** chứng minh request và response tuân thủ các ràng buộc như CSRF, CORS, session/cookie và security headers.

`spring-security-test` cung cấp các công cụ mạnh để thiết lập danh tính và thử chính sách trong cả Servlet/`MockMvc` và Reactive/`WebTestClient`. Giá trị của bài test nằm ở việc nó chạy **đúng cơ chế cần kiểm chứng**, có cặp ca cho phép/từ chối phù hợp và không nhầm trạng thái xác thực giả lập với quá trình kiểm tra credential hay token thực tế.
