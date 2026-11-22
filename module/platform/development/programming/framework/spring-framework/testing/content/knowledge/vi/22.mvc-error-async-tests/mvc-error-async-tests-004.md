# Kiểm thử Filter chain và các nhánh từ chối yêu cầu

Trong một ứng dụng Spring MVC, request có thể bị từ chối trước khi `DispatcherServlet` gọi controller. Servlet filter, Spring Security và các thành phần bảo vệ request có thể kiểm tra thông tin xác thực, quyền truy cập, CSRF token, CORS hoặc quy tắc riêng của ứng dụng. Vì vậy, kiểm thử controller riêng lẻ chưa đủ để chứng minh những request không hợp lệ sẽ bị chặn đúng cách.

`MockMvc` có thể chạy request qua các filter được đăng ký trong môi trường kiểm thử. Khi cấu hình đầy đủ, bài test có thể xác nhận filter nào được thực thi, nhánh nào cho phép request đi tiếp, nhánh nào trả response từ chối và controller có bị gọi ngoài ý muốn hay không.

## 1. Request đi qua Filter chain như thế nào?

Trong Servlet application, filter được gọi trước servlet đích. Một request đi qua chuỗi filter theo thứ tự đã đăng ký; mỗi filter có thể xử lý request, thay đổi response, chuyển request sang filter kế tiếp hoặc kết thúc chuỗi.

```text
HTTP request
    |
    v
Servlet container
    |
    v
Servlet Filter A
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
SecurityFilterChain phù hợp
    |
    +--> Security filters
    |       - SecurityContext
    |       - Authentication
    |       - CSRF
    |       - Authorization
    |
    v
DispatcherServlet
    |
    v
Controller
```

Đây là sơ đồ khái quát. Ứng dụng có thể có nhiều filter Servlet ở trước hoặc sau Spring Security; vị trí chính xác phụ thuộc cách đăng ký và thứ tự cấu hình. `DelegatingFilterProxy` là cầu nối từ Servlet container đến bean filter do Spring quản lý. Trong Spring Security, bean thường được dùng là `FilterChainProxy`.

`FilterChainProxy` có thể chứa nhiều `SecurityFilterChain`. Với mỗi request, nó chọn chain đầu tiên có `securityMatcher` phù hợp. Bên trong chain đó, các filter bảo mật chạy theo thứ tự đã được Spring Security sắp xếp. Nếu một filter từ chối request, các filter phía sau và controller có thể không được gọi.

Điều này tạo ra hai tầng lựa chọn cần phân biệt:

- `securityMatcher(...)` xác định request thuộc `SecurityFilterChain` nào.
- `requestMatchers(...)` bên trong `authorizeHttpRequests(...)` xác định quy tắc phân quyền áp dụng trong chain đã chọn.

Thứ tự khai báo các quy tắc authorization có ý nghĩa: Spring áp dụng quy tắc phù hợp đầu tiên. Quy tắc tổng quát như `anyRequest()` thường được đặt cuối cùng.

## 2. Các nhánh từ chối thường gặp

Một request có thể bị chặn vì nhiều nguyên nhân. Mỗi nguyên nhân có thể tạo status khác nhau và nên được kiểm thử riêng.

| Tình huống | Kết quả thường gặp | Thành phần xử lý |
|---|---:|---|
| Chưa xác thực khi truy cập endpoint được bảo vệ | `401 Unauthorized` hoặc redirect đăng nhập `302` tùy cấu hình | Authentication entry point |
| Đã xác thực nhưng thiếu quyền | `403 Forbidden` | Access denied handler |
| Thiếu hoặc sai CSRF token với request cần bảo vệ | `403 Forbidden` | `CsrfFilter` |
| Origin không được phép trong CORS preflight | Thường là `403 Forbidden` | CORS processing/filter |
| API key, tenant hoặc chữ ký request không hợp lệ | Theo hợp đồng, thường `401` hoặc `403` | Custom filter |
| Vượt giới hạn request | Có thể là `429 Too Many Requests` | Rate limiting filter hoặc gateway |

Không nên gom tất cả các trường hợp thành một assertion chung như `is4xxClientError()`. Một endpoint cần trả đúng `401` khi chưa xác thực và `403` khi người dùng đã xác thực nhưng không đủ quyền. Nếu cấu hình form login, request chưa đăng nhập có thể được redirect đến trang login thay vì nhận `401`; test phải phản ánh authentication entry point của ứng dụng.

## 3. Cấu hình Spring Security cho các nhánh kiểm thử

Ví dụ dưới đây bảo vệ các endpoint `/api/**`. Endpoint public cho phép truy cập ẩn danh, endpoint admin yêu cầu role `ADMIN`, các endpoint còn lại yêu cầu người dùng đăng nhập. HTTP Basic được bật để request không có thông tin xác thực nhận response `401` trong ví dụ API này.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

CSRF vẫn được bật theo mặc định. Đây là chủ ý để bài test có thể kiểm tra nhánh từ chối request thay đổi trạng thái khi thiếu token. Với ứng dụng browser/session, không nên tắt CSRF chỉ để làm test dễ chạy. Nếu API dùng bearer token không dựa trên cookie và có chính sách CSRF phù hợp, việc cấu hình CSRF có thể khác; cần căn cứ vào cách credential được trình duyệt tự động gửi.

Ví dụ controller có các endpoint tương ứng:

```java
@RestController
@RequestMapping("/api")
class ApiController {

    private final OrderService orderService;

    ApiController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin/report")
    String report() {
        return "admin report";
    }

    @PostMapping("/orders")
    ResponseEntity<Void> createOrder() {
        orderService.create();
        return ResponseEntity.created(URI.create("/api/orders/42")).build();
    }
}
```

Các bài test bên dưới tập trung vào việc filter chain cho phép hoặc từ chối request trước khi controller thực hiện nghiệp vụ.

## 4. Kiểm thử SecurityFilterChain bằng MockMvc

Với Spring Boot, `@AutoConfigureMockMvc` mặc định thêm các filter từ application context vào MockMvc. Vì thế, nếu ứng dụng có Spring Security filter chain, request MockMvc có thể đi qua chuỗi bảo mật đó.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityFilterChainTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void permitsPublicEndpointWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }

    @Test
    void rejectsAnonymousRequestToProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void rejectsAuthenticatedUserWithoutAdminRole() throws Exception {
        mockMvc.perform(get("/api/admin/report"))
                .andExpect(status().isForbidden())
                .andExpect(authenticated());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void permitsUserWithAdminRole() throws Exception {
        mockMvc.perform(get("/api/admin/report"))
                .andExpect(status().isOk())
                .andExpect(authenticated());
    }

    @Test
    @WithMockUser
    void rejectsStateChangingRequestWithoutCsrfToken() throws Exception {
        mockMvc.perform(post("/api/orders"))
                .andExpect(status().isForbidden());

        verify(orderService, never()).create();
    }

    @Test
    @WithMockUser
    void acceptsStateChangingRequestWithValidCsrfToken() throws Exception {
        mockMvc.perform(post("/api/orders").with(csrf()))
                .andExpect(status().isCreated());

        verify(orderService).create();
    }
}
```

Các test trên chứng minh những nhánh khác nhau:

1. Request public đi qua security chain và được cho phép.
2. Request protected không có authentication bị từ chối bằng `401`.
3. Người dùng đã đăng nhập nhưng thiếu role bị từ chối bằng `403`.
4. Người dùng có role phù hợp được phép truy cập.
5. Request POST thiếu CSRF token bị chặn trước khi gọi service.
6. Request POST có CSRF token hợp lệ được chuyển đến controller và service.

`@WithMockUser` tạo một `Authentication` cho test. Nó phù hợp để kiểm tra nhánh authorization, nhưng không kiểm tra quá trình xác minh password, giải mã JWT hoặc parsing HTTP Basic credential. Nếu mục tiêu là kiểm tra authentication thực tế, hãy gửi credential qua request, ví dụ dùng `.with(httpBasic("alice", "secret"))`, và cấu hình `UserDetailsService` hoặc `AuthenticationProvider` tương ứng.

Dependency `spring-security-test` cần có trong test runtime để dùng `@WithMockUser`, `csrf()`, `httpBasic()` và các request/result postprocessor của Spring Security Test:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

## 5. Kiểm thử custom Servlet filter

Ngoài Spring Security, ứng dụng có thể có filter riêng để kiểm tra tenant, API key, correlation id hoặc giới hạn request. Một filter có quyền kết thúc request mà không gọi `FilterChain.doFilter`.

Ví dụ filter yêu cầu header `X-Tenant` phải có giá trị `acme`:

```java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

class TenantHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        if (!"acme".equals(request.getHeader("X-Tenant"))) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Unknown tenant");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
```

Khi header không hợp lệ, filter tạo response `403` rồi `return`. Nếu vẫn gọi `filterChain.doFilter`, controller phía sau có thể tiếp tục chạy và request không còn bị chặn đúng cách.

### Kiểm thử filter độc lập

Có thể kiểm tra hai nhánh bằng Servlet mock objects và một `FilterChain` ghi nhận filter có chuyển tiếp hay không:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class TenantHeaderFilterTest {

    private final TenantHeaderFilter filter = new TenantHeaderFilter();

    @Test
    void stopsChainWhenTenantHeaderIsMissing() throws Exception {
        var request = new MockHttpServletRequest("GET", "/tenant/data");
        var response = new MockHttpServletResponse();
        var chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response,
                (servletRequest, servletResponse) -> chainCalled.set(true));

        assertEquals(403, response.getStatus());
        assertFalse(chainCalled.get());
    }

    @Test
    void continuesChainWhenTenantHeaderIsValid() throws Exception {
        var request = new MockHttpServletRequest("GET", "/tenant/data");
        request.addHeader("X-Tenant", "acme");
        var response = new MockHttpServletResponse();
        var chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response,
                (servletRequest, servletResponse) -> chainCalled.set(true));

        assertTrue(chainCalled.get());
    }
}
```

Đây là unit test cho logic filter. Nó xác nhận filter gọi hoặc không gọi chain tiếp theo, nhưng không chứng minh filter đã được đăng ký đúng URL pattern, dispatcher type hoặc thứ tự trong ứng dụng. Để kiểm tra việc filter tham gia vào request MVC, có thể gắn nó vào MockMvc:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new TenantController())
        .addFilters(new TenantHeaderFilter())
        .build();

mockMvc.perform(get("/tenant/data"))
        .andExpect(status().isForbidden());
```

`standaloneSetup` không tự nạp toàn bộ filter trong application context. Những filter cần kiểm tra phải được thêm rõ ràng bằng `addFilters(...)`. Với ứng dụng chạy thật, hãy xác nhận filter được đăng ký với đúng URL mapping và thứ tự.

## 6. Bảo đảm filter thực sự được chạy trong MockMvc

Một nguyên nhân phổ biến khiến test bảo mật cho kết quả sai là filter không được đưa vào MockMvc.

Với Spring Boot:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FilterIntegrationTest {
    // MockMvc nhận các Filter từ application context theo cấu hình mặc định.
}
```

`@AutoConfigureMockMvc` có thuộc tính `addFilters`, mặc định là `true`. Nếu đặt `@AutoConfigureMockMvc(addFilters = false)`, filter trong application context sẽ không được thêm vào chuỗi MockMvc. Khi đó test có thể gọi thẳng đến controller và bỏ qua Spring Security hoặc custom filter.

Với MockMvc được tạo thủ công từ `WebApplicationContext`, có thể áp dụng Spring Security configurer:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` tích hợp `FilterChainProxy` và hỗ trợ các tiện ích kiểm thử bảo mật. Nếu tự tạo `standaloneSetup`, phải thêm filter hoặc security chain bằng cấu hình thích hợp; chỉ inject `MockMvc` không có nghĩa filter bảo mật luôn tự xuất hiện.

Trong `@WebMvcTest`, nếu cấu hình `SecurityFilterChain` nằm ngoài phạm vi component scan của slice, hãy import cấu hình đó bằng `@Import(...)`. Nếu test cố tình tắt filter, cần hiểu rằng test đó chỉ kiểm tra MVC handler, không kiểm tra các nhánh từ chối của filter.

## 7. Kiểm thử nhiều SecurityFilterChain

Một ứng dụng có thể tách security policy theo đường dẫn, chẳng hạn API dùng bearer token còn trang quản trị dùng form login. Khi có nhiều `SecurityFilterChain`, `@Order` và `securityMatcher` quyết định chain nào được xét trước và chain nào phù hợp với request.

Ví dụ cấu hình hai chain:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/api/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Request `/api/orders` được xử lý bởi API chain đầu tiên. Request `/dashboard` không khớp API chain nên được xét tiếp và xử lý bởi web chain. Nếu đặt chain tổng quát `/**` lên trước, chain API có thể không bao giờ được chọn.

Khi kiểm thử nhiều chain, nên tạo ít nhất một request đặc trưng cho từng vùng và xác nhận hành vi riêng của chain đó. Ví dụ API request ẩn danh phải nhận `401`, trong khi web request ẩn danh có thể nhận redirect `302` đến trang login. Nếu cả hai đều nhận cùng kết quả, cần kiểm tra lại matcher và thứ tự chain.

## 8. Kiểm tra thứ tự filter và nhánh short-circuit

Thứ tự filter ảnh hưởng đến việc request được xác thực, ghi log, kiểm tra CSRF hoặc từ chối ở thời điểm nào. Spring Security cung cấp các phương thức như `addFilterBefore`, `addFilterAfter` và `addFilterAt` để đặt custom filter tương quan với filter bảo mật có sẵn.

Ví dụ:

```java
http.addFilterBefore(apiKeyFilter, UsernamePasswordAuthenticationFilter.class);
```

Khi filter phụ thuộc vào một giá trị do filter trước tạo ra, bài test cần xác nhận thứ tự đó. Có thể ghi nhận một header hoặc một event test-only để quan sát filter đã chạy; tránh phụ thuộc vào chi tiết nội bộ không phải hợp đồng của ứng dụng.

Một nhánh từ chối đúng thường có hai đặc điểm:

1. Response được tạo với status/header/body theo hợp đồng.
2. Các thành phần phía sau không được chạy.

Với controller gọi service, có thể xác nhận service không bị gọi:

```java
mockMvc.perform(post("/api/orders"))
        .andExpect(status().isForbidden());

verify(orderService, never()).create();
```

Đây là assertion quan trọng vì chỉ kiểm tra `403` chưa chứng minh nghiệp vụ đã bị chặn. Một filter có thể ghi status sai nhưng vẫn gọi tiếp chain; verify giúp phát hiện tình huống đó.

## 9. CORS, CSRF và các request bị từ chối trước controller

### CSRF

Khi CSRF được bật, request thay đổi trạng thái như POST, PUT, PATCH hoặc DELETE thường cần token hợp lệ. Test nên có cả trường hợp thiếu token và trường hợp có token:

```java
mockMvc.perform(post("/api/orders"))
        .andExpect(status().isForbidden());

mockMvc.perform(post("/api/orders").with(csrf()))
        .andExpect(status().isCreated());
```

Đoạn mã giả định request đã có authentication hợp lệ và endpoint được phép về mặt authorization. Nếu request chưa xác thực, kết quả có thể phụ thuộc thứ tự filter và cách cấu hình exception handling; hãy cô lập từng điều kiện để xác định đúng nguyên nhân bị từ chối.

Có thể kiểm tra token không hợp lệ bằng `.with(csrf().useInvalidToken())`. Bài test này giúp xác nhận cả token thiếu và token sai đều không được chấp nhận.

### CORS preflight

Browser có thể gửi request `OPTIONS` trước request thực để hỏi server có cho phép origin, method và header dự kiến hay không. Test preflight cần gửi các header tương ứng:

```java
mockMvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, "https://client.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS));
```

Nếu origin hoặc method không được cho phép, test cần xác nhận response bị từ chối theo cấu hình CORS. Đảm bảo CORS được xử lý trước Spring Security authorization khi cấu hình ứng dụng; nếu preflight bị yêu cầu đăng nhập trước, browser có thể không thực hiện được request thực.

## 10. Dispatcher type, async và error dispatch

Servlet filter có thể được ánh xạ cho các dispatcher type như `REQUEST`, `ASYNC`, `ERROR`, `FORWARD` và `INCLUDE`. Một filter chỉ được đăng ký cho `REQUEST` có thể không chạy trong một lần dispatch khác.

`OncePerRequestFilter` có cơ chế kiểm soát việc chạy một lần cho một request và mặc định bỏ qua async dispatch cũng như error dispatch trong các phương thức kiểm tra tương ứng. Nếu filter cần chạy trong các nhánh này, hãy xem xét override `shouldNotFilterAsyncDispatch()` hoặc `shouldNotFilterErrorDispatch()` và bảo đảm registration bao gồm dispatcher type cần thiết.

Khi endpoint MVC trả kết quả bất đồng bộ, MockMvc có thể dùng `asyncDispatch(...)` để kiểm tra kết quả cuối. Nếu mục tiêu là xác nhận filter được gọi trong `ASYNC` dispatch, hãy ghi nhận số lần chạy hoặc trạng thái dispatch trong test và cấu hình filter tương ứng. Không nên suy luận rằng test async thành công đồng nghĩa mọi filter đã chạy trên tất cả dispatcher type.

Tương tự, error dispatch có thể đi qua một đường filter khác request ban đầu. Khi ứng dụng có custom error filter, hãy kiểm tra riêng đường xử lý lỗi và tránh vô tình xử lý một lỗi hai lần.

## 11. Những lỗi thường gặp khi kiểm thử Filter chain

### Tắt toàn bộ filter trong test

`@AutoConfigureMockMvc(addFilters = false)` làm test bỏ qua filter. Điều này có thể phù hợp cho một test tập trung vào controller, nhưng không phù hợp khi mục tiêu là kiểm thử authorization, CSRF hoặc custom filter. Dùng cấu hình mặc định hoặc thêm filter cần thiết.

### Dùng standalone MockMvc rồi kỳ vọng Spring Security tự chạy

`MockMvcBuilders.standaloneSetup(...)` không tự nạp toàn bộ application context và security chain. Hãy thêm filter bằng `addFilters(...)` hoặc dùng `webAppContextSetup(...)` với `springSecurity()` khi cần kiểm tra security context thật của ứng dụng.

### Chỉ kiểm tra status mà không kiểm tra chain đã dừng

Một response `403` chưa chắc chứng minh controller không được gọi. Xác nhận service/controller không có tương tác khi request bị từ chối, đặc biệt với POST/PUT/DELETE.

### Nhầm lẫn 401 và 403

`401` liên quan đến authentication; `403` liên quan đến quyền truy cập của principal đã được xác thực hoặc một chính sách từ chối khác như CSRF. Tuy nhiên, form login có thể redirect `302`, còn custom entry point có thể thay đổi response. Hãy viết assertion theo cấu hình thực tế.

### Dùng `@WithMockUser` để kết luận password hoặc token hợp lệ

`@WithMockUser` thiết lập principal cho test và bỏ qua quá trình kiểm tra credential. Muốn kiểm tra Basic authentication, JWT decoder hoặc API key, hãy gửi credential thật theo cơ chế ứng dụng và xác nhận authentication provider/filter xử lý chúng.

### Đăng ký custom filter hai lần

Một filter được đăng ký trực tiếp với Servlet container và đồng thời thêm vào `SecurityFilterChain` có thể chạy hai lần. Điều này có thể tạo log trùng, đọc body nhiều lần hoặc từ chối request không đúng lúc. Chọn một nơi sở hữu registration và kiểm thử số lần filter chạy. Nếu filter chỉ thuộc Spring Security chain, cấu hình để container không đăng ký nó thêm lần nữa.

### Không kiểm tra nhiều SecurityFilterChain

Một test chỉ kiểm tra endpoint trong chain đầu tiên có thể bỏ sót chain tổng quát đang bắt nhầm request. Với nhiều chain, cần test các đường dẫn đại diện cho từng chain và các nhánh từ chối đặc trưng của chúng.

### Giả định `@ControllerAdvice` xử lý mọi lỗi từ filter

Filter chạy trước `DispatcherServlet`, vì vậy exception phát sinh trong filter không mặc nhiên đi qua `@ControllerAdvice`. Spring Security có các filter chuyên xử lý authentication và access denied exception trong security chain. Với custom filter, hãy chủ động chuyển lỗi thành response hoặc dùng cơ chế xử lý lỗi phù hợp với tầng Servlet.

## 12. Chiến lược kiểm thử theo từng tầng

Không phải mọi filter đều cần cùng một kiểu test. Có thể chia thành ba tầng:

| Tầng | Công cụ | Điều được xác nhận |
|---|---|---|
| Unit test cho filter | `MockHttpServletRequest`, `MockHttpServletResponse`, `FilterChain` giả | Điều kiện cho phép/từ chối, status, header và việc có gọi chain tiếp theo hay không. |
| MVC/security integration test | `MockMvc` với filter chain thật trong application context | Registration trong test context, matcher, thứ tự bảo mật, authentication, authorization, CSRF và response trước controller. |
| Server/container test | `@SpringBootTest(RANDOM_PORT)` và HTTP client | Registration và mapping trong embedded container, dispatcher behavior và tương tác qua HTTP thật. |

Unit test giúp kiểm tra logic filter nhanh. MockMvc xác nhận filter phối hợp với Spring MVC và Spring Security. Server test bổ sung bằng chứng về Servlet container và HTTP transport khi những hành vi đó có rủi ro đáng kể.

## 13. Checklist cho bài kiểm thử filter và nhánh từ chối

- [ ] Filter cần kiểm tra đã được đưa vào MockMvc chưa?
- [ ] Test dùng đúng `SecurityFilterChain` cho URL đang gọi chưa?
- [ ] Thứ tự các `SecurityFilterChain` và request matcher có đúng không?
- [ ] Có test request public và request protected không?
- [ ] Có phân biệt request ẩn danh với user đã xác thực nhưng thiếu quyền không?
- [ ] Có test CSRF token thiếu, sai và hợp lệ khi CSRF được bật không?
- [ ] Có xác nhận custom filter dừng chain khi từ chối không?
- [ ] Có xác nhận controller/service không bị gọi trong nhánh từ chối không?
- [ ] Nếu dùng `@WithMockUser`, test có tránh tuyên bố rằng nó đã kiểm tra credential thực không?
- [ ] Nếu có nhiều chain, mỗi chain có request đại diện được kiểm tra không?
- [ ] Nếu filter phụ thuộc async/error dispatch, dispatcher type và chính sách `OncePerRequestFilter` có được kiểm tra không?
- [ ] Nếu cần xác nhận Servlet container, có bài test server thật phù hợp không?

Kiểm thử Filter chain cần chứng minh cả hai phía của quyết định: request hợp lệ được chuyển tiếp đúng cách và request không hợp lệ bị chặn trước khi nghiệp vụ chạy. Kết hợp unit test cho custom filter với MockMvc integration test cho Spring Security giúp phát hiện lỗi matcher, thứ tự filter, authentication, authorization và CSRF ngay trong pipeline của ứng dụng.
