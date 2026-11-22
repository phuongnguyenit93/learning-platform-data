# DelegatingFilterProxy, FilterChainProxy và vị trí tiếp nhận thông tin xác thực

Spring Security trong ứng dụng **Servlet** bảo vệ các HTTP request trước khi request đến `DispatcherServlet` và controller. Điểm vào của hệ thống này là một chuỗi **Servlet Filter**. Trong chuỗi đó, **`DelegatingFilterProxy`** làm cầu nối từ servlet container sang một bean Spring; bean thường mang tên **`springSecurityFilterChain`** và là một **`FilterChainProxy`**. `FilterChainProxy` xem request hiện tại khớp **`SecurityFilterChain` nào đầu tiên**, rồi chạy các security filter của chain được chọn, theo đúng thứ tự. **Filter xác thực** tại vị trí phù hợp mới tiếp nhận password, HTTP Basic header, Bearer token hoặc callback từ nhà cung cấp danh tính — **không phải `DelegatingFilterProxy` tự giải mã hay tự xác thực credentials**.

Đây là một kiến thức nền tảng khi học Spring Security Authentication: nếu một endpoint đi vào **sai security chain**, nếu authentication filter chạy **sau authorization filter**, hoặc nếu custom filter được container đăng ký **thêm một lần ngoài `FilterChainProxy`**, ứng dụng có thể mất xác thực, trả 401/403 khó hiểu, hoặc thậm chí bypass một phần kiểm soát.

Bài thuộc nhóm **Tích hợp bộ lọc**. Mục tiêu là hiểu chính xác trách nhiệm và vị trí của `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain` và các authentication filters; nắm cách chọn chain, cấu hình nhiều chain, cách thêm filter custom, vòng đời `SecurityContext`, các tình huống session/JWT, cách gỡ lỗi, cùng ví dụ **Java 17** chạy được để quan sát việc chọn chain và thực thi filter.

## 1. Kiến trúc từ HTTP request đến controller

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty/Undertow...)
    |
    +-- Container Filter A (nếu có)
    |
    +-- DelegatingFilterProxy
    |       Spring bean name: "springSecurityFilterChain"
    |       |
    |       '--> FilterChainProxy (Spring Security)
    |                 |
    |                 +-- Chọn SecurityFilterChain đầu tiên có matcher khớp
    |                 |
    |                 +-- SecurityContextHolderFilter (nạp context)
    |                 +-- Các filter bảo vệ: headers / CORS / CSRF...
    |                 +-- Authentication filter tương ứng
    |                 |     form / HTTP Basic / bearer JWT / custom
    |                 |     -> AuthenticationManager / AuthenticationProvider
    |                 |     -> Authentication được tin cậy
    |                 +-- AnonymousAuthenticationFilter (nếu cần)
    |                 +-- ExceptionTranslationFilter
    |                 '--> AuthorizationFilter
    |
    +-- Container Filter B (nếu có)
    |
    v
DispatcherServlet -> Controller -> Service
~~~

Sơ đồ là **luồng khái niệm**, không phải danh sách filter cố định. Spring Security tạo danh sách filter thực tế tùy `HttpSecurity`, authentication mechanism, phiên bản và cấu hình. Một endpoint không dùng form login sẽ không cần `UsernamePasswordAuthenticationFilter`. Một bearer resource server thường có `BearerTokenAuthenticationFilter`. Các filter container ở ngoài Spring Security có thể xuất hiện trước hoặc sau proxy theo thứ tự container, nhưng **không tự động được `FilterChainProxy` kiểm soát vị trí**.

### 1.1. Ba lớp thường bị gọi lẫn tên

| Thành phần | Ai đăng ký/quản lý? | Trách nhiệm chính | Có trực tiếp kiểm tra password/JWT không? |
|---|---|---|---|
| `DelegatingFilterProxy` | Servlet container gọi; bean delegate thuộc Spring context | Chuyển `doFilter` đến một bean `Filter` do Spring quản lý | **Không** |
| `FilterChainProxy` | Spring Security, thường là bean `springSecurityFilterChain` | Chọn `SecurityFilterChain`, thực thi các security filter, phối hợp firewall/cleanup | **Không tự kiểm tra credential**; điều phối filters |
| `SecurityFilterChain` | Cấu hình Spring Security, thường từ `HttpSecurity.build()` | Giữ `RequestMatcher` và **danh sách Filter có thứ tự** của một vùng request | Bản thân chain không; các filter bên trong có thể |
| `UsernamePasswordAuthenticationFilter` và tương tự | Security filter bên trong chain | Đọc credential/token từ request, gọi cơ chế authentication | **Có xử lý bước tiếp nhận**, giao kiểm chứng cho provider/manager |
| `AuthenticationManager` và `AuthenticationProvider` | Spring Security authentication subsystem | Kiểm tra bằng chứng và trả `Authentication` đáng tin hoặc ném lỗi | **Có**, tùy provider |

**Không đồng nhất hai chữ “chain”**: container `FilterChain` là toàn bộ đường đi của request qua servlet filters tới servlet; `SecurityFilterChain` là một danh sách **security filters** được `FilterChainProxy` chọn theo matcher.

### 1.2. Vì sao cần một proxy thay vì đăng ký mọi filter vào container?

Servlet container hiểu đối tượng tuân theo `jakarta.servlet.Filter` và thứ tự đăng ký, nhưng nó không mặc nhiên hiểu Spring `ApplicationContext`, DI, transaction/security beans. `DelegatingFilterProxy` giúp **container gọi một bean Spring** đã được tạo/cấu hình bởi hệ sinh thái Spring.

`FilterChainProxy` còn hỗ trợ điều mà URL filter mapping đơn giản khó diễn đạt: nhiều chuỗi filter áp dụng theo matcher tùy path, HTTP method hoặc điều kiện trên `HttpServletRequest`. Nó cũng là điểm tích hợp cho `HttpFirewall` và vòng đời dọn `SecurityContext` để giảm rò state giữa các request.

## 2. DelegatingFilterProxy: cầu nối Servlet ↔ Spring

Class nằm trong Spring Framework:

~~~java
org.springframework.web.filter.DelegatingFilterProxy
~~~

Nó **không thuộc** package `org.springframework.security...`, nhưng thường được dùng để đưa bộ lọc Spring Security vào Servlet container.

### 2.1. Tên bean springSecurityFilterChain

Trong cấu hình Spring Security Servlet tiêu chuẩn, có một Spring bean hạ tầng tên:

~~~text
springSecurityFilterChain
~~~

Bean này thường là `FilterChainProxy`. `DelegatingFilterProxy` tìm bean `Filter` đó theo tên, rồi ủy quyền lời gọi. Pseudo code diễn giải:

~~~java
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain containerChain)
        throws IOException, ServletException {

    Filter springBean = lookupBean("springSecurityFilterChain");
    springBean.doFilter(request, response, containerChain);
}
~~~

**Đây là pseudo code**, vì `lookupBean` chỉ minh họa thao tác tìm Spring bean, không phải API có thể gọi trực tiếp. `DelegatingFilterProxy` còn xử lý chi tiết lifecycle, initialization và bean lookup theo Spring Framework.

Nếu container chỉ gọi proxy nhưng không tìm thấy bean đích, ứng dụng có thể lỗi lúc khởi động/nhận request. Đừng tự tạo bean khác trùng tên `springSecurityFilterChain` mà chưa hiểu Spring Security đang quản lý nó ra sao.

### 2.2. Đăng ký trong ứng dụng web kiểu truyền thống

Với triển khai **WAR/web.xml** (không phải Spring Boot tự cấu hình), một cách đăng ký thường gặp:

~~~xml
<filter>
    <filter-name>springSecurityFilterChain</filter-name>
    <filter-class>org.springframework.web.filter.DelegatingFilterProxy</filter-class>
</filter>

<filter-mapping>
    <filter-name>springSecurityFilterChain</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

Container đăng ký **một filter tên `springSecurityFilterChain`**, có class `DelegatingFilterProxy`. Khi chạy, proxy chuyển đến **Spring bean cùng tên**, không phải đến một servlet/controller có tên ấy.

Trong Servlet 3+ có thể đăng ký bằng Java initializer tương ứng, ví dụ kế thừa `AbstractSecurityWebApplicationInitializer`. **Trong Spring Boot với auto-configuration chuẩn, filter proxy thường đã được đăng ký tự động**: không copy `web.xml`/tự thêm `FilterRegistrationBean` thứ hai chỉ vì muốn “bật Spring Security”.

### 2.3. Vòng đời và Dependency Injection

Delegating proxy giải quyết chênh lệch thời điểm khởi tạo giữa container và Spring context, giúp các security filters sống trong IoC container. Filter beans vì thế có thể dùng Spring DI và các lifecycle callback của Spring. `FilterChainProxy` không gọi `init`/`destroy` của từng delegate security filter theo cách container làm với mỗi filter đăng ký trực tiếp; nếu một filter custom cần khởi tạo/dọn tài nguyên, hãy thiết kế theo lifecycle của Spring bean.

**Ghi nhớ:** `DelegatingFilterProxy` là **cầu nối**, không phải vị trí đặt logic xác minh mật khẩu, xử lý JWT hay truy vấn user.

## 3. FilterChainProxy: cổng điều phối trung tâm

`org.springframework.security.web.FilterChainProxy` triển khai `jakarta.servlet.Filter` và quản lý **một danh sách `SecurityFilterChain`**. Một `SecurityFilterChain` có matcher và các security filters của riêng nó.

### 3.1. Chọn chain nào cho request?

Ví dụ ứng dụng có ba chain theo thứ tự:

~~~text
Chain 1: /api/admin/**  -> JWT + policy admin
Chain 2: /api/**        -> JWT + scope API
Chain 3: /**            -> Form login + session

Request GET /api/admin/users:
  Chain 1 khớp -> CHỈ Chain 1 chạy

Request GET /api/orders:
  Chain 1 không khớp
  Chain 2 khớp -> CHỈ Chain 2 chạy

Request GET /home:
  Chain 1 không khớp
  Chain 2 không khớp
  Chain 3 khớp -> CHỈ Chain 3 chạy
~~~

**Quy tắc quan trọng: `FilterChainProxy` chọn security chain khớp **đầu tiên**.** Nó **không gộp** các filter của tất cả chain cùng khớp, cũng không “chạy chain 1 rồi tiếp tục chain 2” sau khi chain 1 xong. Vì vậy, chain cụ thể phải có thứ tự ưu tiên phù hợp so với chain tổng quát.

Nếu cấu hình `/**` đứng đầu, request `/api/admin/users` cũng khớp chain tổng quát và **các chain API bên dưới không được chọn**. Đây là lỗi cấu hình rất hay gặp.

### 3.2. Nếu không SecurityFilterChain nào khớp?

Request có thể tiếp tục xuống Servlet/container mà **không được Spring Security bảo vệ** bởi bất kỳ chain nào. Điều này khác với việc có một chain khớp nhưng quy tắc authorization của chain đó là `permitAll()`.

- **Không chain nào khớp:** không có authentication, authorization, security headers và những protection filters mà app kỳ vọng từ Spring Security chain.
- **Chain khớp + `permitAll()`:** request vẫn đi qua các filter của chain, có thể được áp dụng bảo vệ khác (headers, CSRF policy, logging, SecurityContext, v.v.) dù endpoint không đòi login.

Nên có một fallback chain phù hợp nếu yêu cầu mọi endpoint đều được Spring Security bao phủ. Kiểm thử bằng route thực tế, không chỉ nhìn thấy bean được tạo rồi cho rằng mọi URL đã an toàn.

### 3.3. HttpFirewall ở vị trí nào?

`FilterChainProxy` phối hợp với `HttpFirewall` để kiểm tra/chuẩn hóa cách nhìn request path khi chọn matcher và khi xử lý bảo mật. Spring Security mặc định cung cấp cơ chế firewall phù hợp với cấu hình, giúp giảm rủi ro path không hợp lệ/không nhất quán giữa container và security matcher.

Không tự bỏ firewall hoặc tùy tiện cho phép encoded slash, duplicate slashes, path traversal hay delimiter bất thường chỉ để một URL lỗi “chạy được”. Thay đổi firewall phải đi kèm kiểm thử request mapping, reverse proxy, normalization và authorization; một URL mà container hiểu khác security matcher có thể dẫn tới **bypass**.

### 3.4. SecurityContext và cleanup

Spring Security filter infrastructure quản lý `SecurityContext` cho từng request, thường dùng `ThreadLocal` thông qua `SecurityContextHolder` và filter phù hợp. Context được nạp hoặc tạo khi request bắt đầu, có thể được cập nhật sau xác thực, và được dọn khi execution kết thúc để thread của servlet pool không mang identity của người dùng cũ sang request khác.

Không viết một singleton/static field tên `currentUser` để dùng chung. Cũng đừng tự `setContext` từ raw username trước khi provider xác thực: holder là nơi **lưu kết quả authentication đã được xác minh**, không phải công cụ biến input thành user đáng tin.

## 4. SecurityFilterChain: ranh giới chọn filter, không phải chỉ là luật URL

Một `SecurityFilterChain` gồm:

1. **`RequestMatcher`** quyết định chuỗi có áp dụng cho request hay không.
2. **Danh sách `Filter` có thứ tự** chạy cho request đã chọn.

Trong Spring Boot/Spring Security 6.x, thường cấu hình qua `@Bean SecurityFilterChain` và `HttpSecurity`:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **mảnh cấu hình** cần imports và Spring Boot/Spring Security runtime phù hợp. Nó tạo một chain áp dụng mặc định trên mọi request còn lại, có authn/authz filters theo DSL. `requestMatchers("/", "/assets/**").permitAll()` chỉ định quyền **trong chain đã chọn**, không thay matcher tổng thể của chain.

### 4.1. securityMatcher khác requestMatchers thế nào?

Đây là một trong những điểm quan trọng nhất khi làm nhiều chain:

| Cách viết | Tác dụng | Hậu quả |
|---|---|---|
| `http.securityMatcher("/api/**")` | Chọn **request nào đi vào chain này** | Request khác không dùng những filters của chain đó |
| `http.authorizeHttpRequests(a -> a.requestMatchers("/api/public/**").permitAll())` | Định luật **ủy quyền bên trong chain** | Request vẫn đi qua chain; chỉ không yêu cầu login ở matcher đó |
| `http.authorizeHttpRequests(a -> a.anyRequest().authenticated())` | Luật mặc định bên trong chain đã được chọn | Không tự khiến chain áp dụng cho mọi URL nếu `securityMatcher` hẹp |
| `web.ignoring()` hoặc loại request khỏi security chain | **Bypass security filters** đối với request đó | Có thể mất security headers và các cơ chế bảo vệ khác |

Ví dụ nếu đặt:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

`/api/public/info` vẫn đi vào **API chain**, nhận các filters được cấu hình cho API; authorization cho phép anonymous tại endpoint đó. `/home` không đi vào API chain; có thể được một chain khác xử lý.

### 4.2. @Order là ưu tiên chain, không phải thứ tự filter bên trong

Dùng `@Order(1)`, `@Order(2)` hoặc thứ tự đã được Spring xác định để điều phối **các bean SecurityFilterChain**:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    // API chain
    return http.securityMatcher("/api/**").build();
}
~~~

Đây là ví dụ ngắn minh họa. Đừng nghĩ `@Order(1)` trên bean này có nghĩa custom authentication filter đứng trước `BasicAuthenticationFilter` trong **nội bộ** chain. Thứ tự các filter bên trong do DSL Spring Security, filter order registration và `addFilterBefore/After/At` quyết định.

## 5. Authentication được tiếp nhận ở vị trí nào?

**Điểm tiếp nhận credentials nằm tại authentication filter tương ứng** — thường nằm trong `SecurityFilterChain` sau các thành phần hạ tầng cần thiết và trước giai đoạn authorization. Các filter này đọc một dạng credential cụ thể, tạo một yêu cầu `Authentication` chưa được xác minh hoặc tương đương, rồi chuyển tới `AuthenticationManager`/`AuthenticationProvider` hoặc verifier phù hợp.

### 5.1. Bảng các cơ chế phổ biến

| Dạng request | Filter thường gặp | Lấy gì từ request? | Ai kiểm chứng? |
|---|---|---|---|
| Form login | `UsernamePasswordAuthenticationFilter` | Username/password từ form POST login | `AuthenticationManager` → provider, ví dụ `DaoAuthenticationProvider` |
| HTTP Basic | `BasicAuthenticationFilter` | `Authorization: Basic ...` | `AuthenticationManager` → provider |
| Bearer JWT/OAuth2 access token | `BearerTokenAuthenticationFilter` | `Authorization: Bearer ...` | `AuthenticationManager`/`JwtAuthenticationProvider` + `JwtDecoder` hoặc opaque token introspector |
| OAuth2/OIDC login | `OAuth2LoginAuthenticationFilter` | Authorization response ở callback đã cấu hình | OAuth2/OIDC components và provider tương ứng |
| Remember-me (nếu bật) | `RememberMeAuthenticationFilter` | Cookie remember-me | RememberMeServices/authentication manager theo policy |
| Custom API key | Filter do ứng dụng thiết kế | Header/token theo giao thức ứng dụng | Verifier/provider custom đã được thẩm định |

Filter **tiếp nhận** thông tin không phải luôn là thành phần **tự kiểm chứng** mọi chi tiết. Ví dụ `UsernamePasswordAuthenticationFilter` không trực tiếp so bcrypt hash trong database. Nó tạo `UsernamePasswordAuthenticationToken` chưa xác thực, gọi `AuthenticationManager`; provider tải `UserDetails` và gọi `PasswordEncoder.matches(...)`.

### 5.2. Luồng Form Login cụ thể

~~~text
POST /login
  |
  v
UsernamePasswordAuthenticationFilter
  |
  +--> Lấy username/password từ HttpServletRequest
  +--> UsernamePasswordAuthenticationToken (unauthenticated)
  +--> AuthenticationManager.authenticate(request)
  |      |
  |      +--> DaoAuthenticationProvider
  |               +--> UserDetailsService.loadUserByUsername
  |               +--> PasswordEncoder.matches
  |               +--> account status checks
  |
  +-- THẤT BẠI -> AuthenticationFailureHandler, response theo cấu hình
  |
  '-- THÀNH CÔNG
         -> Authentication đã xác minh
         -> SecurityContextHolder / SecurityContextRepository
         -> SessionAuthenticationStrategy / remember-me nếu có
         -> AuthenticationSuccessHandler
~~~

Thứ tự chính xác của callback và cơ chế lưu context tùy Spring Security version/filter, nhưng **nội dung cốt lõi bất biến** là credentials được kiểm chứng **trước khi** request được coi là principal đáng tin. Nếu viết custom authentication controller/filter, đừng tạo `UsernamePasswordAuthenticationToken.authenticated(...)` từ username và roles do client tự gửi.

### 5.3. HTTP Basic và bearer JWT khác gì về nơi kiểm chứng?

~~~text
GET /api/orders
Authorization: Basic <base64 username:password>
  -> BasicAuthenticationFilter
  -> AuthenticationManager / username-password provider
  -> Authentication trong SecurityContext của request

GET /api/orders
Authorization: Bearer <access-token>
  -> BearerTokenAuthenticationFilter
  -> JwtDecoder/JwtAuthenticationProvider hoặc opaque token introspection
  -> Authentication trong SecurityContext của request
~~~

Base64 trong Basic **chỉ là encoding, không bảo mật**; phải bảo vệ request bằng TLS. Với JWT, validator phải kiểm tra chữ ký/thuật toán, issuer, audience, exp/nbf và các policy cần thiết; **đừng chỉ Base64-decode payload rồi tạo authenticated principal**. Một token tự có claim `roles` không đồng nghĩa có quyền truy cập account hay tenant nếu backend chưa xác minh identity/claims/authorization.

### 5.4. Authentication thành công khác authorization thành công

Sau khi filter đã xác minh identity, **`AuthorizationFilter`** hoặc method security còn cần quyết định người dùng có được truy cập URL/resource không. Tình huống:

~~~text
Alice: credentials đúng -> Authentication thành công
Alice: gọi GET /admin -> không có ROLE_ADMIN
=> Authorization từ chối, không phải “password sai”
~~~

`ExceptionTranslationFilter` là cầu nối **xử lý `AuthenticationException`/`AccessDeniedException` từ phần downstream** và gọi `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` phù hợp. Nó không tự xác thực password; một số authentication filters có failure handler riêng và có thể xử lý lỗi trước khi authorization filter chạy.

**Không suy mọi HTTP 401 hay 403 là do cùng một filter.** 401 thường chỉ cần authentication/challenge; 403 thường là bị từ chối quyền hoặc một chính sách khác như CSRF. Phải xem filter chain và exception source thực tế.

## 6. Thứ tự filter: trước khi authentication, trong lúc authentication và sau đó

Spring Security bảo đảm thứ tự filter cụ thể trong chain được xây bằng `HttpSecurity`. Mặc dù version/config làm danh sách khác nhau, các mốc khái niệm thường là:

~~~text
Nạp SecurityContext / thiết lập request context
          |
          v
Bảo vệ trước khi xác thực:
CORS, CSRF, header/security policies theo cấu hình
          |
          v
Authentication filters:
Basic / form / bearer / custom...
          |
          v
AnonymousAuthenticationFilter (nếu vẫn chưa có auth)
          |
          v
ExceptionTranslationFilter (chuyển exceptions downstream)
          |
          v
AuthorizationFilter / các kiểm tra quyền
          |
          v
Controller / Servlet
~~~

Không dùng một sơ đồ rút gọn làm “full list” cố định; một số filters như logout, request cache, remember-me, session management hay security context persistence có vị trí riêng. Muốn biết **thứ tự thực tế**, xem DEBUG log lúc startup và TRACE log khi request chạy trong môi trường test.

### 6.1. Vì sao authentication phải trước authorization?

Giả sử authorization kiểm tra `hasRole("READER")`, nhưng authentication filter chưa đọc bearer token. Khi authorization chạy, context có thể null/anonymous, nên request hợp lệ bị 401/403. Ngược lại, nếu tự gắn role trước khi kiểm chứng token, bạn mở đường bypass.

**Quy tắc:** đặt custom filter ở vị trí đủ sớm để tạo Authentication cho các filter cần sử dụng nó, nhưng không bỏ qua các protection filters cần thiết (CSRF/CORS/header/context initialization).

### 6.2. Các method bổ sung filter

~~~java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(myFilter, BasicAuthenticationFilter.class);
http.addFilterAt(myFilter, UsernamePasswordAuthenticationFilter.class);
~~~

Ba dòng là **các ví dụ API độc lập**, không được dùng đồng thời cho cùng một filter như một cấu hình có nghĩa. Các method:

- `addFilterBefore(Filter, Class<?>)`: đặt custom filter **trước** vị trí filter tham chiếu.
- `addFilterAfter(Filter, Class<?>)`: đặt **sau** vị trí filter tham chiếu.
- `addFilterAt(Filter, Class<?>)`: đăng ký tại **vị trí** filter tham chiếu. Cần hiểu cách DSL đăng ký: nếu filter mặc định vẫn tồn tại cùng slot, không nên dựa vào thứ tự không được bảo đảm như thể đây là phép “thay thế” an toàn. Muốn thay đổi cơ chế auth, hãy tắt/cấu hình lại filter mặc định rõ ràng.
- Vị trí tham chiếu cần là filter được Spring Security biết thứ tự. Đặt filter trước một class không có order được đăng ký có thể gây lỗi hoặc hành vi bất ngờ.
- Đặt custom filter theo loại **chức năng**: request logging, authentication, authorization hay post-processing; đừng luôn neo mọi thứ vào `UsernamePasswordAuthenticationFilter` vì ứng dụng có thể không dùng form login.

### 6.3. Gợi ý chọn vị trí custom authentication filter

Một nguyên tắc từ kiến trúc Spring Security: filter xác thực custom thường nên nằm **sau `LogoutFilter`**, tức là sau phần khởi tạo context/protection ban đầu, nhưng trước anonymous/authorization. Vị trí chính xác phụ thuộc filter loại gì, policy CSRF/CORS, các cơ chế auth khác và yêu cầu dừng chain khi thiếu credential.

Nếu filter của bạn chỉ kiểm tra quota đã biết sau authentication, vị trí sau `AnonymousAuthenticationFilter` có thể hợp hơn; nếu nó cần hoàn tất trước authorization thì không được đặt sau `AuthorizationFilter`. Trong mọi trường hợp, dùng security integration test chứng minh filter **chạy đúng một lần, chọn đúng chain và có Authentication đáng tin khi cần**.

## 7. Cấu hình nhiều SecurityFilterChain trong Spring Security 6

Ví dụ ứng dụng có API dùng HTTP Basic ở namespace `/api/**` (chỉ minh họa) và website dùng form login/session ở các URL còn lại:

~~~java
@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain websiteChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **một ví dụ cấu hình Spring** (cần imports, beans xác thực và Spring Boot/web app), không phải file Java 17 standalone. Tùy phiên bản Spring Security/Boot, hãy dùng DSL tương ứng. **Không copy ví dụ này để chạy production mà chưa xác định provider/user store, CSRF, CORS, HTTPS, session policies và endpoint behavior.**

Phân tích:

- `apiChain` có `@Order(1)` nên được xét trước `websiteChain`.
- `securityMatcher("/api/**")` khiến API chain chỉ áp dụng URL API.
- `/api/health` có `permitAll()` nhưng vẫn **đi qua API chain**; các filter khác còn hoạt động theo cấu hình.
- API chain minh họa `STATELESS`; không mặc nhiên tạo session lưu authentication cho request sau. HTTP Basic credentials được gửi và kiểm chứng lại theo request tùy cấu hình.
- Website chain không có `securityMatcher` tùy biến nên khớp các request còn lại, đóng vai trò fallback.
- Form login dùng những filter/session mechanisms khác API. Cả hai chain có thể dùng chung `AuthenticationManager`/provider/user store nếu cấu hình thích hợp.

**Lưu ý về CSRF:** Ví dụ giữ nguyên thiết lập CSRF mặc định; một số request thay đổi trạng thái (POST/PUT/DELETE) qua cookie/browser có thể bị 403 khi thiếu CSRF token, kể cả khi password đúng. Không tắt CSRF toàn ứng dụng chỉ vì API đang trả 403; xác định cơ chế auth và nguy cơ browser tự gửi credential trước khi quyết định phạm vi CSRF.

### 7.1. Những lỗi matcher dễ gặp

~~~text
/api/**          match path API, ví dụ /api/orders
/api/admin/**    vùng hẹp hơn /api/**
/**             fallback rộng
~~~

Matcher thực tế có thể phụ thuộc đến Servlet path, cấu hình MVC/path matching, HTTP method và phiên bản Spring Security. Đừng suy toàn bộ semantics chỉ từ một biểu thức string khi ứng dụng có multiple servlets, context path hoặc dispatcher đặc biệt. Test bằng request URL thật qua `MockMvc` hoặc integration test và kiểm tra chain được chọn.

### 7.2. Login endpoint có nằm trong chain đúng không?

Ví dụ bạn viết:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(Customizer.withDefaults());
~~~

Nếu default login endpoint `POST /login` và trang `GET /login` không nằm trong matcher `/secured/**`, các endpoint do Spring Security cung cấp có thể **không tồn tại trong security chain này**. Kết quả là 404 hoặc login không được xử lý, dù filter bean đã được tạo.

Để tránh, đặt login URL vào phạm vi security matcher hợp lý, cấu hình `loginProcessingUrl` phù hợp, hoặc dùng một fallback chain đúng với login endpoint. **Vị trí filter trong chain không cứu được URL bị loại ngay từ matcher của chain.**

### 7.3. PermitAll hay bỏ qua Spring Security?

Với một endpoint được phép truy cập công khai, thường nên cân nhắc `permitAll()` thay vì bỏ qua toàn bộ Spring Security qua `web.ignoring()`. `permitAll()` giữ các security filters liên quan như header protection và các hành vi cần cho context/observability tùy cấu hình.

Nếu ứng dụng có một số static assets được bỏ qua với lý do hiệu năng, phải hiểu đầy đủ tác động: URL đó không có filter security, có thể không nhận response headers do Spring Security thêm. Không coi “asset” là lý do cho phép client truy cập data API quan trọng mà không qua security chain.

## 8. Custom Filter trong Spring Boot: tránh thực thi hai lần

Nếu bạn khai báo một `Filter` như Spring bean (ví dụ `@Component` hoặc `@Bean`), **Spring Boot có thể tự động đăng ký nó với Servlet container**. Nếu cùng instance đó lại được thêm bằng `http.addFilterBefore(...)` vào `SecurityFilterChain`, nó có thể được gọi **hai lần**:

~~~text
Servlet container filter registration
    -> CustomTokenFilter (lần 1)
    -> DelegatingFilterProxy
        -> FilterChainProxy
            -> CustomTokenFilter (lần 2)
            -> AuthorizationFilter
~~~

Tác hại:

- Đọc token/DB hai lần, tăng latency.
- Đặt authentication ở lần chạy không đúng scope/timing.
- Logic tiêu thụ request body hoặc token dùng một lần bị kích hoạt lại.
- Logging, audit và rate limit bị đếm đôi.
- Filter nằm ngoài `FilterChainProxy` có thể chạy trước khi context được nạp hoặc sau khi đã clear.

### 8.1. Cách khắc phục trong Spring Boot

Nếu cần custom filter là Spring bean để dependency injection, có thể **tắt đăng ký tự động ở Servlet container**:

~~~java
@Bean
FilterRegistrationBean<CustomTokenFilter> customTokenFilterRegistration(
        CustomTokenFilter filter) {
    FilterRegistrationBean<CustomTokenFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Đây là **mảnh cấu hình**, cần `CustomTokenFilter`, imports và Boot dependencies; nó không bỏ filter khỏi Spring Security chain, mà chỉ ngăn container tự đăng ký thêm một bản. Sau đó, bạn vẫn đưa filter vào `HttpSecurity` đúng chain/vị trí.

Một hướng khác là tạo custom filter instance trong cấu hình security và **không khai báo nó là Servlet Filter bean** để Boot tự scan/đăng ký. Dù chọn cách nào, tích hợp test phải kiểm tra **mỗi request cần filter đi qua đúng một lần**, không chỉ nhìn code bean.

### 8.2. OncePerRequestFilter có giải quyết hoàn toàn không?

`OncePerRequestFilter` là tiện ích Spring Web cho việc kiểm soát thực thi theo phạm vi dispatch/request nhất định, nhưng **không thay thế** việc đăng ký filter ở đúng chain/vị trí. Nó có thể tránh chạy lặp trong một số lần dispatch, nhưng không làm một filter ngoài security chain bỗng có đầy đủ Spring Security lifecycle, cũng không đảm bảo mọi cấu hình Servlet async/error dispatch đều hành xử như bạn tưởng.

Cần cân nhắc `shouldNotFilter`, `shouldNotFilterAsyncDispatch`, `shouldNotFilterErrorDispatch` khi phù hợp. Cấu hình loại `ASYNC`/`ERROR` ở container và security dispatcher type có thể ảnh hưởng đến thời điểm filter chạy lại; đừng tự suy “Once” nghĩa chính xác một lần trên toàn bộ mọi request lifecycle.

### 8.3. Đừng đọc và tiêu thụ request body bừa bãi

Nếu một custom filter đọc toàn bộ `HttpServletRequest.getInputStream()` để tìm password/token trong JSON rồi không cung cấp body wrapper phù hợp, controller sau đó có thể không đọc được payload. Đối với JWT/API key, ưu tiên header theo giao thức; đối với login JSON custom, dùng authentication filter/converter được thiết kế rõ, có giới hạn body size và bảo vệ logs.

Filter chứa authentication nên có failure behavior được xác định: khi token sai, không tiếp tục chain với `Authentication` giả mạo; khi token vắng mặt ở public endpoint, có thể cho downstream authorization quyết định. Sự khác biệt cần được mô tả và test.

## 9. Ví dụ Java 17 chạy được: FilterChainProxy chọn chain đầu tiên

Ví dụ này dùng **Spring Security Web** và **Spring Test Mock Servlet** để minh họa trực tiếp cơ chế định tuyến của `FilterChainProxy`. Chúng ta tạo:

- Chain API với matcher `/api/**`, chứa hai filter demo tên `api.authentication` và `api.authorization`.
- Chain Web làm fallback với `AnyRequestMatcher.INSTANCE`, chứa filter demo `web.authentication` và `web.authorization`.
- Các `Filter` demo **chỉ in tên và gọi `chain.doFilter(...)`**, không kiểm chứng password hay cấp Authentication; chúng giúp quan sát rõ thứ tự.
- Một `FilterChainProxy` chứa API chain trước Web chain.
- Một lần chạy bổ sung với **chỉ có API chain** để chứng minh request `/public` không khớp chain nào vẫn xuống Servlet.

**Phân biệt:** chương trình gọi trực tiếp `FilterChainProxy` với mock request nên **không dựng `DelegatingFilterProxy`/container thật**. Các phần 1–2 giải thích layer cầu nối trong web server; demo tập trung xác nhận chính xác **selection and execution** của filter chain thực, không giả mạo việc login.

### 9.1. Cấu trúc project

~~~text
filter-chain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/FilterChainDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'filter-chain-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FilterChainDemo'
}
~~~

Để chạy cần Java 17+, Gradle phiên bản tương thích và Maven Central ở lần tải đầu. Mẫu pin Spring Security Web 6.3.8, Spring Framework Test 6.1.18 và Servlet 6 API cho demo console. Một dự án Spring Boot thực nên dùng Spring Boot dependency management/BOM để các version Spring đồng bộ.

### 9.2. Toàn bộ tệp Java

Tạo `src/main/java/example/FilterChainDemo.java`:

~~~java
package example;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.DefaultSecurityFilterChain;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.AnyRequestMatcher;

public final class FilterChainDemo {

    static final class NamedFilter implements Filter {
        private final String name;

        NamedFilter(String name) {
            this.name = name;
        }

        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {
            System.out.println(name);
            chain.doFilter(request, response);
        }
    }

    private static SecurityFilterChain apiChain() {
        return new DefaultSecurityFilterChain(
                new AntPathRequestMatcher("/api/**"),
                new NamedFilter("api.authentication"),
                new NamedFilter("api.authorization"));
    }

    private static SecurityFilterChain webChain() {
        return new DefaultSecurityFilterChain(
                AnyRequestMatcher.INSTANCE,
                new NamedFilter("web.authentication"),
                new NamedFilter("web.authorization"));
    }

    private static void run(
            FilterChainProxy proxy, String path)
            throws IOException, ServletException {

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        request.setServletPath(path);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        FilterChain servlet = (req, res) -> {
            String uri = ((HttpServletRequest) req).getRequestURI();
            System.out.println("servlet -> " + uri);
        };

        System.out.println("== " + path + " ==");
        proxy.doFilter(request, response, servlet);
    }

    public static void main(String[] args) throws Exception {
        SecurityFilterChain api = apiChain();
        SecurityFilterChain web = webChain();

        FilterChainProxy both =
                new FilterChainProxy(List.of(api, web));

        run(both, "/api/orders");
        run(both, "/home");

        // Không có fallback: /public không khớp /api/**.
        FilterChainProxy apiOnly =
                new FilterChainProxy(List.of(api));
        run(apiOnly, "/public");
    }
}
~~~

### 9.3. Chạy và đọc kết quả

Nếu đã tạo Gradle Wrapper trong project:

~~~bash
./gradlew run
~~~

Nếu chỉ cài Gradle, dùng `gradle run`. Trên Windows PowerShell với wrapper, lệnh thường là `.\gradlew.bat run`.

Các dòng `System.out.println` của chương trình (bỏ qua log Gradle):

~~~text
== /api/orders ==
api.authentication
api.authorization
servlet -> /api/orders
== /home ==
web.authentication
web.authorization
servlet -> /home
== /public ==
servlet -> /public
~~~

Phân tích:

1. Request `/api/orders` match `AntPathRequestMatcher("/api/**")` đầu tiên. `FilterChainProxy` chạy **chỉ** hai filter API, rồi Servlet; nó không chạy hai filter Web dù fallback cũng có thể match.
2. Request `/home` không match API, nhưng match `AnyRequestMatcher.INSTANCE`. Proxy chạy Web chain.
3. Với proxy chỉ chứa API chain, request `/public` không match chain nào nên chuyển tiếp xuống Servlet **không qua bất kỳ security filter nào** trong proxy này. Nó **không có nghĩa** Servlet container hoàn toàn không có filter khác, mà chỉ là Spring Security chain đã không áp dụng.

**Cảnh báo:** `NamedFilter` là marker quan sát thứ tự; nó **không xác thực hoặc phân quyền thật**, dù tên chứa `authentication`/`authorization`. Để bảo vệ endpoint production, dùng cấu hình `HttpSecurity` có authentication provider, authorization policy, exception handling và các protection filters tiêu chuẩn.

### 9.4. Thử thay đổi thứ tự để hiểu first-match

Đổi:

~~~java
new FilterChainProxy(List.of(api, web))
~~~

thành:

~~~java
new FilterChainProxy(List.of(web, api))
~~~

Khi request `/api/orders` được xét, `AnyRequestMatcher.INSTANCE` ở đầu tiên sẽ khớp ngay; **Web chain** được chọn và API chain **không chạy**. Đây là lý do chain fallback phải đứng sau chain chuyên biệt.

Thử thêm một chain chỉ khớp `/api/admin/**` và đặt nó trước `/api/**`. Test `/api/admin/users` để xác nhận chain chuyên biệt đứng đầu, đồng thời `/api/orders` vẫn đi vào API chain chung.

### 9.5. Giới hạn và khả năng mở rộng của demo

- Demo dùng trực tiếp `FilterChainProxy`, không khởi động Spring `ApplicationContext` hay Servlet container; bridge `DelegatingFilterProxy` được trình bày riêng.
- Không có thật `AuthenticationManager`/`Provider`, `SecurityContextHolderFilter`, `CsrfFilter` hoặc `AuthorizationFilter`; tên marker không tạo quyền.
- `MockHttpServletRequest.setServletPath(path)` giúp matcher đọc Servlet path trong mô phỏng. Với container thật, giá trị servlet path, context path, proxy prefix và MVC mapping phải được kiểm thử theo cấu hình.
- Không có session, TLS, JWT decoder hay redirect login. Sau khi hiểu selection, hãy tiếp tục bằng integration test một app Spring Boot có filter chain thực, không dựa vào demo để đánh giá bảo mật production.
- Một số phiên bản thư viện sau này có thể thay đổi API matcher được khuyến nghị. Đoạn code pin Spring Security 6.3.x để phản ánh chính xác bài học.

## 10. Cấu hình một custom authentication filter an toàn

Nếu muốn tiếp nhận một API key/JWT tự thiết kế, đừng đặt logic ấy trong `DelegatingFilterProxy` hay viết một Servlet filter nằm ngoài mọi Spring Security chain rồi tự coi request an toàn. Chọn chain và cơ chế phù hợp, lý tưởng là dùng **các filter/provider có sẵn** trước khi xây custom.

Ví dụ *phác thảo luồng* một filter xác thực theo header:

~~~text
doFilterInternal(request, response, chain):
    nếu request không thuộc matcher được bảo vệ:
        chain.doFilter; return

    lấy credential theo header được định nghĩa
    nếu thiếu:
        để authorization/filter phù hợp quyết định hoặc trả 401
        KHÔNG tạo authenticated token tùy tiện

    nếu có:
        tạo Authentication request CHƯA authenticated
        gọi AuthenticationManager / provider đã được kiểm chứng
        nếu failure:
            xử lý response theo AuthenticationEntryPoint/FailureHandler
            KHÔNG tiếp tục như đã đăng nhập

        nếu success:
            newContext = SecurityContextHolder.createEmptyContext()
            newContext.setAuthentication(verified)
            SecurityContextHolder.setContext(newContext)
            nếu stateful và cần tiếp tục qua request sau:
                SecurityContextRepository.saveContext(...)
            chain.doFilter(...)
~~~

Đây là **pseudo code** chứ không phải implementation Java có thể chạy. Trong production còn phải thiết kế xử lý exception, cleanup, async dispatch, invalid token, rate limiting, account status, error masking, clock skew, credential erasure, bearer-token revocation và logging an toàn.

### 10.1. Vì sao nên dùng cơ chế tiêu chuẩn nếu phù hợp?

Với OAuth2 access token/JWT, Spring Security resource server đã hỗ trợ `BearerTokenAuthenticationFilter`, `JwtDecoder`, issuer validation, authorities conversion và error handling có cấu hình. Tự parse base64 JWT rồi đặt `Authentication` có thể bỏ qua chữ ký, audience, expiry hoặc key rotation.

Với form username/password, `UsernamePasswordAuthenticationFilter` cùng `AuthenticationManager`/`DaoAuthenticationProvider` giải quyết nhiều chi tiết: failure handler, credential comparison, context persistence, session strategy và security events. Custom filter nên có **lý do kiến trúc rõ** thay vì vì “đặt code ở Filter sớm hơn Controller thì an toàn hơn”.

### 10.2. Vị trí của custom filter so với SecurityContextHolderFilter

Một filter chạy trước khi context được nạp có thể không nhìn thấy authentication từ session, hoặc tự tạo context rồi bị filter phía sau thay thế/clear theo lifecycle. Một filter chạy sau authorization sẽ quá muộn để cung cấp identity cho kiểm tra quyền.

Điều này giải thích vì sao **filter order là một phần của security design**. Test phải chứng minh thời điểm context hiện diện và authentication được thiết lập đủ sớm, cùng việc credentials không được giữ ngoài vòng đời cần thiết.

## 11. Thất bại xác thực, exception handling và HTTP status

Có nhiều nơi có thể chặn request trước controller:

| Giai đoạn | Ví dụ lỗi | Phản ứng phổ biến |
|---|---|---|
| Servlet container filter | Request quá lớn, encoding không hợp lệ, upstream policy | Container/filter trả lỗi |
| `HttpFirewall` của `FilterChainProxy` | URL/path bị từ chối | RequestRejectedException và response theo configured handler |
| `CorsFilter`/CORS processing | Origin/header/method không được phép | CORS bị từ chối hoặc preflight không hợp lệ |
| `CsrfFilter` | Request state-changing thiếu CSRF token | Thường 403 |
| `UsernamePasswordAuthenticationFilter` | Username/password không khớp | Authentication failure handler, redirect hoặc lỗi theo config |
| `BasicAuthenticationFilter` | Basic credentials không hợp lệ | Entry point, thường 401/challenge theo cấu hình |
| `BearerTokenAuthenticationFilter` | Bearer token sai/hết hạn | Authentication entry point, thường 401 theo protocol |
| `AuthorizationFilter` | Không đủ quyền hoặc anonymous | `ExceptionTranslationFilter` + entry point/AccessDeniedHandler, 401 hoặc 403 tùy trường hợp |

**Không lấy status code làm bằng chứng filter nào đã chạy.** Ví dụ 403 có thể đến từ CSRF chứ không phải phân quyền business; 404 ở login có thể là login processing URL không nằm trong chain; 401 có thể do không có credential hoặc token không được chấp nhận.

Khi custom filter xử lý exception, đừng ném/nuốt mọi RuntimeException rồi chuyển thành `BadCredentialsException`: sự cố hạ tầng (DB down, JWK endpoint lỗi) cần được nhận diện và xử lý fail-closed/observability riêng. Đồng thời, response công khai không nên lộ cụ thể username có tồn tại, token string, secret, stacktrace hoặc cấu hình nội bộ.

## 12. Spring Security DEBUG/TRACE: tìm filter nào thực sự chạy

### 12.1. Xem filter list lúc startup

Có thể bật logging trong môi trường dev/test:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Spring Security thường ghi thông tin `DefaultSecurityFilterChain` lúc khởi động, ví dụ:

~~~text
Will secure any request with [
  SecurityContextHolderFilter,
  HeaderWriterFilter,
  CsrfFilter,
  UsernamePasswordAuthenticationFilter,
  BasicAuthenticationFilter,
  AnonymousAuthenticationFilter,
  ExceptionTranslationFilter,
  AuthorizationFilter
]
~~~

Đây là **ví dụ rút gọn**, không phải output đầy đủ/cố định. Danh sách thật phụ thuộc DSL và version, có thể chứa nhiều filter khác. Kiểm tra **đúng chain** theo matcher chứ không chỉ đếm số filter.

Khi cần xem từng filter được gọi trong test, có thể bật TRACE phù hợp:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Hoặc tăng mức log security cụ thể theo nhu cầu. **Không bật TRACE vô hạn ở production** nếu sẽ ghi nhiều metadata request/identity, tăng chi phí và rủi ro lộ dữ liệu nhạy cảm. Dùng log có kiểm soát, thời hạn ngắn và bảo vệ truy cập.

### 12.2. Trình tự chẩn đoán đề xuất

1. **Request cụ thể là gì?** Ghi method/path và correlation ID, loại bỏ token/password.
2. **Servlet container có đăng ký `DelegatingFilterProxy` không?** Trong Boot, kiểm tra auto registration, đừng tự thêm hai lần.
3. **Proxy tìm được Spring bean `springSecurityFilterChain` không?** Nếu thiếu bean, xử lý context/bootstrap.
4. **`FilterChainProxy` chọn chain nào?** Xem `@Order`/matcher và debug log.
5. **URL authentication endpoint có nằm trong chain không?** Đặc biệt với form login và custom callback.
6. **Các filter xác thực có được tạo/bật trong chain đã chọn không?** Không mong form login filter xuất hiện nếu DSL không bật.
7. **Filter order đúng chưa?** Authentication phải trước authorization, sau context setup cần thiết.
8. **Provider/decoder có chấp nhận credential không?** UserDetailsService, PasswordEncoder, issuer/audience/JWK, account status.
9. **Context có Authentication chưa?** Null, anonymous, real; không dump token/password.
10. **Đã save context đúng không nếu cần session?** Spring Security 6 thường yêu cầu explicit save cho custom flow.
11. **Request tiếp theo vào chain nào?** Session cookie/JWT, stateless policy, path matcher có thể khác login.
12. **Có filter custom chạy hai lần không?** Check bean auto-registration/`addFilterBefore`/`OncePerRequestFilter`.
13. **Nếu controller chạy @Async?** ThreadLocal và context propagation cần xử lý riêng.

### 12.3. Hướng xử lý cho các lỗi thường thấy

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
|---|---|---|
| Login endpoint trả 404 | `securityMatcher` bỏ ngoài `/login` hoặc filter login chưa bật | Đặt login path trong chain phù hợp, kiểm tra matcher |
| API yêu cầu JWT nhưng hiện form login | Fallback `/**` đứng trước API chain | Đặt API chain ưu tiên cao hơn |
| Public endpoint vẫn 401 | `requestMatchers` không match hoặc chain khác được chọn | Debug matcher/method, phân biệt chain vs authorization |
| Endpoint không có security headers | Không chain match / sử dụng bypass ignoring | Dùng fallback/permitAll và cấu hình headers |
| Custom auth filter không bao giờ chạy | Thêm vào chain khác hoặc sai `securityMatcher` | Kiểm tra chain/registration/order |
| Custom filter chạy hai lần | Boot container auto registration + Security DSL | Tắt một registration bằng `FilterRegistrationBean` |
| JWT hợp lệ vẫn 403 | Token thiếu authority, CSRF ở write endpoint hoặc policy tenant | Xem source exception, không chỉ nhìn status |
| Request có auth trước login filter | Session cũ được nạp hoặc filter custom set sớm | Kiểm tra context load/flow, không kết luận bypass ngay |
| Filter tự đọc body khiến controller lỗi | InputStream đã bị tiêu thụ | Dùng converter hoặc wrapper đúng cách |
| Sau custom login, request tiếp mất auth | Chỉ set context, chưa save/session cookie | Kiểm tra repository/session strategy |
| Account A xuất hiện ở request B | ThreadLocal không được clear hoặc singleton auth state | Dùng filter lifecycle chuẩn, dọn context |
| Tắt CSRF làm POST “hết 403” | Có thể mở nguy cơ CSRF nếu browser gửi cookie/Basic auth | Phân tích credential transport và threat model |
| Filter nào đó không có @Order nhưng chạy lạ | Lẫn Servlet Filter order và SecurityFilterChain order | Cấu hình đúng layer, kiểm thử actual chain |
| URL path khác dưới reverse proxy | Context/servlet path, encoded path hay rewrite không nhất quán | Cấu hình forwarding/firewall/matcher đồng bộ |

## 13. Kiểm thử nên có ở ba tầng

### 13.1. Unit test matcher và custom filter

- Matcher `/api/**` nhận `/api/orders` và không nhận `/home`.
- Chain `/api/admin/**` được xét trước `/api/**`.
- Custom filter không gọi verifier khi request ngoài phạm vi được định nghĩa.
- Credential bị thiếu/sai không trở thành authenticated principal.
- Filter không leak raw password/JWT trong logs hoặc response.
- Gọi `chain.doFilter` theo contract khi request được phép đi tiếp; dừng có chủ đích khi authentication failure.

### 13.2. Integration test Spring Security / MockMvc

| Request | Kỳ vọng |
|---|---|
| `GET /api/orders` thiếu credential | API chain xử lý, 401/entry point theo policy |
| `GET /api/orders` Basic/JWT hợp lệ | Authentication đúng cơ chế, đi tới authorization |
| `GET /home` chưa login | Website chain, redirect login hoặc entry point đúng |
| `GET /assets/app.js` | Chain có `permitAll`, vẫn nhận security headers nếu config bật |
| `POST /login` đúng/sai credential | Đúng filter login và handler, không 404 |
| `POST /api/orders` thiếu CSRF (nếu policy yêu cầu) | 403 do CSRF, không nhầm AuthorizationFilter |
| `GET /api/admin/users` với token chỉ có quyền thường | Bị authorization từ chối |
| URL không match chain nào trong bản cấu hình thử | Phát hiện nguy cơ bypass, không deployment production |
| Một custom token filter là bean Boot | Không chạy hai lần khi đã add vào security chain |
| Logout hoặc request tiếp theo dùng session | Context persistence/invalidation đúng policy |
| `ASYNC` và `ERROR` dispatch | Không double-auth hoặc leak context |
| Request URL encoded/path bất thường | `HttpFirewall`/matcher thống nhất, không bypass |
| Multiple servlets hoặc context-path | Matcher kiểm tra đúng servletPath/pathInfo |

`MockMvc` giúp kiểm thử security chain nhưng không mô phỏng hoàn toàn firewall/reverse proxy/session container production. Với điểm nhạy cảm về proxy rewrite/HTTP parser, cần integration test qua container thật.

### 13.3. E2E và security regression

- Chạy hệ thống sau load balancer/reverse proxy như production, xác minh Authorization/header/cookies không bị proxy làm thay đổi sai.
- Thử các cách truy cập endpoint theo slash, encoded URL, HTTP method và context path theo threat model.
- Rate limit login và API key verification để tránh brute-force/DoS; cost `PasswordEncoder` không được áp đặt bừa.
- Test đăng nhập nhiều users đồng thời để phát hiện context/thread reuse leak.
- Test rollout có cả website session và API stateless: chain không bị đảo thứ tự khi thêm filter mới.
- Kiểm tra thay đổi logout, account locking, role change có tác dụng trong yêu cầu bảo mật tương ứng.
- Giữ danh sách các chain và matcher ở test như một **contract**: thêm endpoint/namespace mới phải có quyết định security explicit.

## 14. Những hiểu nhầm cốt lõi

**1. “DelegatingFilterProxy xác thực mật khẩu.”**  
Sai. Nó cầu nối Servlet sang bean Spring. Authentication filter/provider mới xử lý credential.

**2. “Có một SecurityFilterChain cho mỗi request và Spring chạy tất cả các chain khớp.”**  
Sai. `FilterChainProxy` chọn **chain khớp đầu tiên**, không hợp nhất filter lists.

**3. “securityMatcher và requestMatchers là một.”**  
Sai. `securityMatcher` xác định phạm vi áp dụng toàn bộ chain; `requestMatchers` trong authorize DSL là luật quyền bên trong chain.

**4. “Thứ tự @Order quyết định thứ tự filter authentication so với authorization.”**  
Sai. `@Order` trên `SecurityFilterChain` quyết định ưu tiên giữa chains, còn thứ tự filter nội bộ do Security DSL/`addFilter...`.

**5. “Filter chạy là chứng tỏ đã login.”**  
Sai. Filter có thể kiểm tra request chưa đăng nhập, tạo anonymous context hoặc trả 401. Chỉ Authentication đã được verify theo trust boundary mới đáng tin.

**6. “Bật STATELESS nghĩa là không có SecurityContext.”**  
Sai. Request stateless vẫn có thể tạo SecurityContext từ Basic/Bearer token mỗi lần.

**7. “permitAll và ignoring giống nhau.”**  
Sai. `permitAll` vẫn dùng security filters của chain; ignoring/bỏ matcher có thể bypass hẳn filters.

**8. “Tạo @Component Filter rồi addFilterBefore luôn an toàn.”**  
Sai. Spring Boot có thể tự đăng ký ở container rồi filter chạy thêm trong Spring Security, gây double invocation.

**9. “Nếu Basic credentials sai sẽ luôn là 403.”**  
Sai. Failure thường qua entry point/challenge (thường 401); 403 còn có thể đến từ CSRF/authorization.

**10. “Có thể tự tạo Authentication authenticated từ username/roles trong request.”**  
Sai. Đó là bypass authentication. Phải có provider/verifier đã kiểm chứng credential/token.

**11. “Nhiều filter hơn nghĩa là bảo mật hơn.”**  
Sai. Lọc nhầm thứ tự, không match URL, hoặc double-register có thể tạo lỗi/side effect và tăng bề mặt tấn công.

**12. “Custom login set SecurityContextHolder là đủ duy trì đến hôm sau.”**  
Sai. Cần `SecurityContextRepository`/session hoặc cơ chế xác thực stateless theo request, tùy policy.

## 15. Checklist áp dụng trước production

- [ ] Xác nhận một điểm vào `DelegatingFilterProxy`/`springSecurityFilterChain` đúng cách; không đăng ký trùng trong Boot.
- [ ] Phân biệt Servlet `FilterChain`, `FilterChainProxy` và `SecurityFilterChain` về vai trò.
- [ ] Ghi rõ thứ tự `@Order` và matcher của từng chain; chain hẹp trước fallback rộng.
- [ ] Kiểm tra toàn bộ endpoint quan trọng đều match một chain có bảo vệ phù hợp.
- [ ] Phân biệt `securityMatcher` với authorization `requestMatchers(...).permitAll/hasRole...`.
- [ ] Biết rõ authentication filter nào đọc loại credential nào: form, Basic, Bearer, OIDC, custom.
- [ ] Không đặt raw username/token trực tiếp thành authenticated principal; dùng `AuthenticationManager`/provider/decoder.
- [ ] Kiểm tra filter auth chạy trước authorization và sau context/protection cần thiết.
- [ ] Khi thêm custom filter, đặt vị trí bằng `addFilterBefore/After/At` có mục đích rõ và test thứ tự thực.
- [ ] Ngăn custom Filter bean bị đăng ký hai lần ở container + Spring Security chain.
- [ ] Chỉ dùng `OncePerRequestFilter` đúng phạm vi dispatch; không coi nó là giải pháp thay thế cấu hình chain.
- [ ] Bảo vệ `HttpFirewall`, URL normalization, reverse proxy và path matching nhất quán.
- [ ] Duy trì CSRF/CORS/headers theo threat model; không tắt toàn bộ chỉ vì lỗi 403.
- [ ] Nếu dùng session login, bảo đảm authentication được save/restore đúng với Spring Security 6 và login endpoint trong chain.
- [ ] Nếu stateless, yêu cầu credential được verify trên từng request; không dựa vào session holder.
- [ ] Không leak credentials, JWT, user secrets, session cookie, toàn bộ Authentication/claims qua logs.
- [ ] Debug bằng log Spring Security và integration test route thật; hạn chế TRACE trong production.
- [ ] Test empty/missing chain, first-match behavior, form + API chains, custom filter count, anonymous, error/async dispatch và logout.
- [ ] Sau cập nhật filter chain, chạy lại regression test security và đo latency/login errors.

**Ghi nhớ:** `DelegatingFilterProxy` **đưa Spring Security vào Servlet container**; `FilterChainProxy` **chọn đúng một `SecurityFilterChain` đầu tiên khớp request**; **authentication filter trong chain được chọn** mới đọc credentials và chuyển chúng cho verifier/provider đáng tin; các filters khác nạp context, bảo vệ request, chuyển exception và kiểm tra quyền. Hiểu đúng tầng, đúng vị trí và đúng thứ tự giúp tránh cả lỗi login lẫn lỗ hổng bypass.

### Tài liệu chính thức

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, matcher, firewall và thêm filters.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `@Order`, nhiều `SecurityFilterChain` và `securityMatcher` so với `requestMatchers`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder`, `AuthenticationManager` và provider.
- [Spring Security — Username and Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): form login, HTTP Basic và `DaoAuthenticationProvider`.
- [Spring Security — Authentication Persistence / Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit save và session state.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer authentication và token verification.
- [Spring Boot — Disable Servlet Filter Registration](https://docs.spring.io/spring-boot/how-to/webserver.html): `FilterRegistrationBean` và ngăn filter bean được auto-register.
- [Spring Security — FilterChainProxy JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html): first-matching `SecurityFilterChain`, `HttpFirewall` và lifecycle.
