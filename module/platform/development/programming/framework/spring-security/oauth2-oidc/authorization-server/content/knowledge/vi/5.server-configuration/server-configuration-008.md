# Cấu hình login entry point và xử lý request chưa xác thực

> **Chương:** Cấu hình máy chủ  
> **Phạm vi:** Thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Trọng tâm:** Quyết định lúc nào chuyển trình duyệt đến trang đăng nhập, lúc nào trả lỗi giao thức OAuth2/OIDC hoặc HTTP 401/403, và cấu hình các `SecurityFilterChain` sao cho request chưa xác thực được xử lý đúng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chức năng của `AuthenticationEntryPoint`, `ExceptionTranslationFilter` và `AccessDeniedHandler` trong Spring Security.
2. Phân biệt tình huống **người dùng chưa đăng nhập** ở authorization endpoint với tình huống **client xác thực thất bại** ở token endpoint.
3. Cấu hình một `SecurityFilterChain` cho endpoint của Spring Authorization Server và một chain khác cho form login.
4. Chọn chuyển hướng `302 /login` cho request HTML tương tác, nhưng giữ phản hồi lỗi phù hợp cho API, token endpoint và Bearer token.
5. Hiểu mối quan hệ giữa `SavedRequest`, HTTP session, request cache, CSRF, cookie và luồng Authorization Code + PKCE.
6. Kiểm thử các tình huống chưa xác thực, thiếu quyền, lỗi OAuth2 và lỗi cấu hình dẫn đến vòng lặp redirect.

Bài dùng ví dụ Servlet stack của Spring Boot, Spring Security 6.x và Spring Authorization Server 1.x, với API cấu hình `HttpSecurity.with(...)`. Khi sử dụng thế hệ Spring Security 7.x có Authorization Server tích hợp, hãy đối chiếu tên dependency, package và API trong tài liệu đúng phiên bản; nguyên tắc về entry point và ranh giới request vẫn có giá trị.

## 2. Vấn đề: “chưa xác thực” không luôn có cùng cách phản hồi

Một Authorization Server phải tiếp nhận nhiều loại request có kỳ vọng khác nhau:

- Người dùng truy cập `GET /oauth2/authorize` bằng trình duyệt. Nếu chưa đăng nhập, thường **chuyển hướng đến trang login** rồi quay lại tiếp tục yêu cầu ủy quyền.
- OAuth2 client gọi `POST /oauth2/token` bằng HTTP. Nếu thông tin xác thực client sai, cần **lỗi OAuth2 rõ ràng**; không thể trả một trang HTML login và coi là thành công.
- Resource Server nhận `GET /api/orders` mà thiếu Bearer token. Câu trả lời thông thường là **HTTP 401** cùng challenge `WWW-Authenticate: Bearer`, không phải redirect đến trang đăng nhập của Authorization Server.
- Người dùng đã đăng nhập nhưng bị từ chối truy cập chức năng quản trị. Đó thường là **HTTP 403** hoặc giao diện từ chối phù hợp; yêu cầu đăng nhập lại không giải quyết việc thiếu quyền.
- Người dùng từ chối consent ở authorization endpoint. Đó là **lỗi authorization của OAuth2** cần xử lý theo quy tắc redirect/error response của giao thức, không đơn giản là “user chưa đăng nhập”.

Vì vậy, kiến trúc cần tách rõ **nơi xác thực**, **nơi cấp quyền** và **định dạng phản hồi**.

| Tình huống | Chủ thể liên quan | Phản hồi kỳ vọng thường gặp |
| --- | --- | --- |
| Authorization request hợp lệ, user chưa có session đăng nhập | Resource Owner | `302` chuyển đến `/login` ở luồng trình duyệt |
| User gửi credential sai vào form login | Resource Owner | Chuyển về `/login?error` hoặc giao diện báo lỗi đã cấu hình |
| Client authentication không hợp lệ tại token endpoint | OAuth2 Client | Lỗi `invalid_client` theo giao thức; thường HTTP `401` và challenge thích hợp |
| Authorization code sai/hết hạn/PKCE không khớp | OAuth2 Client | Lỗi `invalid_grant`, thường HTTP `400` |
| Authorization request không hợp lệ | OAuth2 Client | Lỗi `invalid_request` hoặc lỗi OAuth2 tương ứng; redirect chỉ khi an toàn và hợp lệ theo giao thức |
| API thiếu Bearer token | API caller | HTTP `401` với Bearer challenge theo Resource Server |
| Chủ thể đã xác thực nhưng không đủ quyền | User hoặc Client | HTTP `403` hoặc phản hồi lỗi đúng giao thức/ngữ cảnh |
| Resource Owner không chấp thuận consent | Resource Owner | Lỗi OAuth2 `access_denied` được xử lý theo quy tắc authorization response |

Các mã trong bảng là hành vi **theo ngữ cảnh thông thường**; filter cụ thể, handler tùy biến và yêu cầu của RFC quyết định phản hồi cuối cùng. Đặc biệt, **không tự động redirect đến `redirect_uri` do request không hợp lệ cung cấp** nếu client/redirect URI chưa được kiểm tra.

## 3. `AuthenticationEntryPoint` làm gì?

Trong Spring Security Servlet, `AuthenticationEntryPoint` là giao diện xác định cách **bắt đầu quá trình xác thực** khi request cần đăng nhập nhưng hiện chưa có Authentication phù hợp.

~~~java
public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
~~~

Các tham số mang ý nghĩa:

- `request`: HTTP request đang bị chặn.
- `response`: đối tượng để trả redirect, status hoặc challenge.
- `authException`: nguyên nhân yêu cầu bắt đầu authentication.

Một số implementation cần nhớ:

| Entry point | Hành vi | Khi nào phù hợp |
| --- | --- | --- |
| `LoginUrlAuthenticationEntryPoint` | Trả redirect đến URL login cấu hình | Trang HTML và authorization endpoint cần user tương tác |
| `HttpStatusEntryPoint` | Trả mã HTTP cố định, ví dụ 401 | API không sử dụng cơ chế Bearer challenge, tùy chính sách |
| `BearerTokenAuthenticationEntryPoint` | Phản hồi Bearer authentication challenge | OAuth2 Resource Server nhận request thiếu/không có Bearer authentication hợp lệ |
| `BasicAuthenticationEntryPoint` | Trả challenge HTTP Basic | API thực sự dùng HTTP Basic; không phải mặc định phù hợp với mọi token endpoint |
| `RequestMatcherDelegatingAuthenticationEntryPoint` | Chọn entry point dựa trên matcher | Phân biệt request HTML với các nhóm request khác trong cùng ngữ cảnh |

**Entry point không phải một trang HTML.** Nó là **hành vi phản hồi HTTP**. `LoginUrlAuthenticationEntryPoint("/login")` chỉ đưa trình duyệt đến `/login`; việc phục vụ trang và xử lý POST login còn cần cấu hình ở filter chain thích hợp.

### 3.1. Entry point khác authentication filter như thế nào?

Ví dụ:

- `UsernamePasswordAuthenticationFilter` nhận POST username/password và cố gắng xác thực.
- `ExceptionTranslationFilter` bắt một số ngoại lệ authentication/authorization ở phần chain mà nó bao quanh rồi quyết định cần bắt đầu authentication hay xử lý bị từ chối.
- `AuthenticationEntryPoint` thực hiện bước “bắt đầu xác thực” mà `ExceptionTranslationFilter` yêu cầu.
- `AuthenticationFailureHandler` của form login xử lý **lần đăng nhập đã được gửi nhưng thất bại**.
- `AccessDeniedHandler` xử lý **truy cập bị từ chối** khi không nên khởi động lại login.

Vì vậy:

- `GET /oauth2/authorize` chưa đăng nhập → thường gọi entry point dẫn về login.
- `POST /login` sai password → thường gọi **failure handler** của form login.
- User đã đăng nhập nhưng thiếu quyền trang admin → thường do **access denied handler** xử lý.

### 3.2. `AuthenticationException` và `AccessDeniedException`

Sơ đồ quyết định đơn giản hóa:

~~~mermaid
flowchart TD
    A["Request đi qua SecurityFilterChain"]
    B{"Có lỗi cần dịch sang phản hồi security?"}
    C["Tiếp tục tới handler / endpoint"]
    D{"AuthenticationException?"}
    E["AuthenticationEntryPoint"]
    F{"AccessDeniedException?"}
    G{"Anonymous hoặc remember-me<br/>chưa đủ mức tin cậy?"}
    H["AuthenticationEntryPoint"]
    I["AccessDeniedHandler"]
    J["Phản hồi do bộ lọc/giao thức khác xử lý"]

    A --> B
    B -->|"Không"| C
    B -->|"Có"| D
    D -->|"Có"| E
    D -->|"Không"| F
    F -->|"Có"| G
    F -->|"Không"| J
    G -->|"Có"| H
    G -->|"Không"| I
~~~

Trong thực tế, `ExceptionTranslationFilter` sử dụng `AuthenticationTrustResolver` để nhận diện anonymous/remember-me và có thể sử dụng `RequestCache` khi bắt đầu xác thực. Từng endpoint của Spring Authorization Server cũng có filter và exception handler **chuyên cho OAuth2/OIDC**; không phải mọi lỗi đều đi qua sơ đồ trên.

Không viết kiểm tra thủ công chỉ dựa vào `authentication.isAuthenticated()` để thay thế các cơ chế này: `AnonymousAuthenticationToken` có thể báo trạng thái authenticated ở tầng đối tượng mặc dù người dùng thực tế chưa đăng nhập.

## 4. Thiết kế hai SecurityFilterChain cho Authorization Server

Cấu hình thường gặp của Spring Authorization Server tách:

1. **Authorization Server chain**: chỉ áp dụng cho các endpoint OAuth2/OIDC như `/oauth2/authorize`, `/oauth2/token`, metadata, JWK Set và các endpoint được bật.
2. **Application/login chain**: phục vụ `/login` và những request web ứng dụng khác, thiết lập form login hoặc phương thức đăng nhập của Resource Owner.

Chúng được lựa chọn theo `securityMatcher` và `@Order`. **Một request được xử lý bởi filter chain đầu tiên khớp nó**, thay vì đi qua lần lượt mọi chain.

~~~mermaid
flowchart TD
    R["HTTP request đến Spring Boot"]
    S{"Khớp endpointsMatcher của<br/>Authorization Server?"}
    AS["Chain @Order(1)<br/>OAuth2/OIDC endpoint filters"]
    W["Chain @Order(2)<br/>Form login và web app"]
    U{"Request /oauth2/authorize<br/>cần user login?"}
    L["LoginUrlAuthenticationEntryPoint<br/>Redirect /login"]
    T["Token / metadata / OAuth2 endpoint<br/>Xử lý theo filter và RFC tương ứng"]
    LF["GET /login<br/>Trang form login"]
    AUTH["POST /login<br/>Thực hiện authentication"]
    X["Authorization Code/consent tiếp tục"]

    R --> S
    S -->|"Có"| AS
    S -->|"Không"| W
    AS --> U
    U -->|"Có, request HTML"| L
    U -->|"Không hoặc endpoint khác"| T
    L --> LF
    LF --> AUTH
    AUTH --> X
~~~

### 4.1. Cấu hình mẫu cho Spring Security 6 và Spring Authorization Server 1.x

Giả định dự án Spring Boot đã có dependency Authorization Server, Spring Security, Spring Web và các bean cần thiết của AS (registered clients, authorization/consent service, key management, user authentication). Đoạn sau **tập trung vào hai filter chain**; nó chưa đủ để khởi động một Authorization Server production hoàn chỉnh.

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            )
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Những import quan trọng (IDE có thể tự bổ sung):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
~~~

Giải thích từng dòng cấu hình có ý nghĩa:

| Thành phần | Mục đích |
| --- | --- |
| `@Order(1)` | Ưu tiên chain chuyên cho AS trước chain tổng quát |
| `authorizationServer.getEndpointsMatcher()` | Khoanh request đến các endpoint giao thức do AS cấu hình |
| `with(authorizationServer, ...)` | Áp dụng các filter/handler của Spring Authorization Server |
| `server.oidc(Customizer.withDefaults())` | Bật phần hỗ trợ OIDC theo cấu hình tương ứng |
| `anyRequest().authenticated()` | Yêu cầu xác thực đối với endpoint được match, với các filter OAuth2 xử lý chi tiết theo giao thức |
| `defaultAuthenticationEntryPointFor(...)` | Chỉ định redirect login cho request có media type HTML được matcher chọn |
| `new LoginUrlAuthenticationEntryPoint("/login")` | Địa chỉ bắt đầu tương tác đăng nhập Resource Owner |
| `@Order(2)` + `formLogin(...)` | Cấu hình đăng nhập trên chain chung, trong đó `/login` không thuộc AS endpoints matcher |

Khi không cấu hình trang login riêng, `formLogin(Customizer.withDefaults())` có thể cung cấp **trang login mặc định do Spring Security tạo**. Nếu muốn dùng trang custom, cần tạo trang và cấu hình `loginPage("/login")` ở application chain như phần sau.

**Điểm giới hạn của ví dụ:** việc dùng `MediaTypeRequestMatcher(MediaType.TEXT_HTML)` là chiến lược chọn entry point cho luồng browser HTML, không phải định nghĩa cho mọi OAuth2 error. `/oauth2/token`, token introspection, revocation, metadata và OIDC endpoint có xử lý riêng; không nên thêm một redirect login toàn cục vào tất cả request chỉ vì có trạng thái chưa xác thực.

### 4.2. Vì sao `/login` không đặt ở Authorization Server chain?

`authorizationServer.getEndpointsMatcher()` nhằm bắt các endpoint giao thức, trong khi trang `/login` dành cho thao tác đăng nhập của người dùng trong ứng dụng.

Đặt cả hai trên một filter chain duy nhất hoặc dùng matcher quá rộng có thể dẫn đến:

- `GET /login` cũng bị yêu cầu đăng nhập, rồi redirect quay lại `/login` liên tục.
- OAuth2 token endpoint trả HTML login thay cho lỗi OAuth2.
- Tương tác trình duyệt và HTTP API bị trộn chính sách session, CSRF và phản hồi lỗi.
- Khó xác định filter nào có quyền xử lý request ở từng endpoint.

Vì vậy cần kiểm tra **matcher chính xác** cùng **thứ tự chain**, không chỉ nhìn vào dòng `formLogin()`.

## 5. Luồng request chưa đăng nhập tại authorization endpoint

Một Client dùng Authorization Code + PKCE gửi trình duyệt đến AS:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-web&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20profile&state=state-random&code_challenge=valid-pkce-challenge&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

Các giá trị `state` và `code_challenge` ở ví dụ là **minh họa định dạng**, không phải những giá trị ngẫu nhiên/PKCE hợp lệ để dùng trực tiếp. Trong ứng dụng thật, client phải tạo `state` khó đoán, `code_verifier` đủ entropy rồi tính `code_challenge` theo S256; AS phải đăng ký và kiểm tra `redirect_uri` chính xác.

### 5.1. Các bước xử lý

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant AS as Authorization Server chain
    participant RC as RequestCache/Session
    participant LOGIN as Login chain
    participant STORE as Authorization/Consent services
    participant C as OAuth2 Client

    U->>B: Chọn "Đăng nhập để cấp quyền"
    C-->>B: Redirect tới /oauth2/authorize
    B->>AS: GET /oauth2/authorize (Accept: text/html)
    AS->>AS: Kiểm tra yêu cầu OAuth2, thấy user chưa xác thực
    AS->>RC: Lưu request ban đầu khi cơ chế cache được bật
    AS-->>B: 302 Location: /login
    B->>LOGIN: GET /login
    LOGIN-->>B: 200 trang login
    U->>B: Nhập username/password
    B->>LOGIN: POST /login + CSRF token
    LOGIN->>LOGIN: Authentication thành công
    LOGIN->>RC: Lưu SecurityContext/session theo cấu hình
    LOGIN-->>B: Redirect tới request đã lưu
    B->>AS: GET /oauth2/authorize (đã có session)
    AS->>STORE: Kiểm tra client, consent, grant
    opt Cần consent
        AS-->>B: Hiển thị consent
        U->>B: Chấp thuận
        B->>AS: Gửi quyết định consent
    end
    AS-->>B: Redirect về redirect_uri hợp lệ + code + state
    B->>C: Callback với authorization code
~~~

Sơ đồ là **mô hình logic**. Request cache và success handler chỉ khôi phục URL ban đầu nếu đã được cấu hình và hoạt động phù hợp; các luồng tùy biến có thể sử dụng cơ chế lưu request hoặc hoàn thành authorization khác. AS không được phát hành code khi chưa đáp ứng yêu cầu xác thực/consent của luồng.

### 5.2. `RequestCache` và `SavedRequest` hỗ trợ điều gì?

Khi request đến tài nguyên cần login, `ExceptionTranslationFilter` có thể lưu request gốc thông qua `RequestCache` (ví dụ `HttpSessionRequestCache`) trước khi gọi entry point. Sau khi login thành công, một success handler phù hợp có thể đưa browser quay lại request đã lưu.

Các thành phần liên quan:

- `RequestCache`: trừu tượng để lưu/tìm lại HTTP request cần tiếp tục.
- `HttpSessionRequestCache`: triển khai thường lưu trong session.
- `SavedRequest`: bản ghi request gốc (URL, tham số và một số thông tin cần thiết).
- `SavedRequestAwareAuthenticationSuccessHandler`: có thể ưu tiên redirect về request đã lưu sau khi login thành công.

Điều này giúp tránh tình trạng người dùng đăng nhập xong lại ở trang chủ, bỏ dở authorization request chứa `client_id`, `scope`, `state`, `redirect_uri` và PKCE challenge.

**Không coi `SavedRequest` là authorization grant.** Nó chỉ hỗ trợ điều hướng browser, khác với trạng thái OAuth2 được lưu qua `OAuth2AuthorizationService`. Request cache cũng không thay thế các kiểm tra client, redirect URI, scope, state hoặc PKCE.

### 5.3. Không tự tin cậy URL callback từ tham số do client gửi

`LoginUrlAuthenticationEntryPoint("/login")` chuyển người dùng tới trang đăng nhập **nội bộ**. Đường dẫn callback OAuth2 là `redirect_uri` do Client đăng ký và AS xác minh; hai URL không đồng nghĩa.

Không triển khai kiểu:

~~~java
// KHÔNG AN TOÀN: trực tiếp redirect đến URL do request cung cấp.
response.sendRedirect(request.getParameter("redirect_uri"));
~~~

Thay vào đó, để Spring Authorization Server kiểm tra đăng ký client, redirect URI và tạo authorization response đúng chuẩn. Nếu yêu cầu không hợp lệ, AS phải từ chối hoặc trả lỗi theo trường hợp tương ứng; không để request chưa xác thực biến thành lỗ hổng **open redirect**.

## 6. Tùy biến trang đăng nhập và entry point

### 6.1. Trang login mặc định và login tùy biến

Với `formLogin(Customizer.withDefaults())`, Spring Security có thể sinh một trang login đơn giản để phát triển. Khi muốn giao diện thương hiệu riêng, ví dụ Thymeleaf, cần tự triển khai GET `/login` và khai báo cho form login filter biết URL đăng nhập.

~~~java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .permitAll()
        );

    return http.build();
}
~~~

Một controller để trả trang `login.html`:

~~~java
@Controller
class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

Đối với view Thymeleaf có thể dùng form minh họa:

~~~html
<form th:action="@{/login}" method="post">
    <label>
        Tên đăng nhập
        <input name="username" autocomplete="username" required>
    </label>
    <label>
        Mật khẩu
        <input type="password" name="password"
               autocomplete="current-password" required>
    </label>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng nhập</button>
</form>
~~~

Trong form, hidden field `_csrf` được dựng từ token do server cung cấp. Tùy integration Thymeleaf/Spring Security, framework cũng có cơ chế tự chèn CSRF token khi render form. Điều quan trọng là request POST login phải mang token phù hợp **khi CSRF protection được bật**.

**Phân biệt URL:**

| URL | Ai xử lý? | Vai trò |
| --- | --- | --- |
| `GET /login` | Controller hoặc default login page | Hiển thị giao diện |
| `POST /login` | `UsernamePasswordAuthenticationFilter` với cấu hình mặc định | Xác thực credential |
| `GET /oauth2/authorize` | AS authorization endpoint | Nhận authorization request và yêu cầu user đăng nhập nếu cần |
| `POST /oauth2/token` | AS token endpoint + client authentication | Nhận grant để phát token, không hiển thị form login |

Nếu đổi `loginPage("/sign-in")` hoặc `loginProcessingUrl("/sign-in")`, phải cập nhật đồng bộ entry point, GET controller, HTML form action, exception handling và quy tắc permit-all.

### 6.2. Chỉ chuyển hướng request HTML, giữ đúng semantics cho giao thức

Trong AS chain đã có:

~~~java
.exceptionHandling(exceptions ->
    exceptions.defaultAuthenticationEntryPointFor(
        new LoginUrlAuthenticationEntryPoint("/login"),
        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
    )
)
~~~

Điểm then chốt là **matcher**. Nó giúp chọn login entry point cho loại request có thể tương tác với người dùng. Cần hiểu các giới hạn:

- `Accept: text/html` là tín hiệu HTTP về content negotiation; không bảo đảm mọi request đều đến từ browser thật.
- Một số client gửi `Accept: */*`; hãy kiểm thử behavior của phiên bản Spring Security đang dùng, thay vì mặc nhiên coi mọi client là HTML.
- `Content-Type` mô tả body request và **không thay cho `Accept`** khi lựa chọn định dạng phản hồi.
- Không nên ép mọi request đến AS redirect login. Các filter OAuth2/OIDC phải có cơ hội tạo response đúng chuẩn cho `invalid_client`, `invalid_grant` và các lỗi giao thức.
- Nếu yêu cầu sự phân biệt chặt hơn giữa browser flow và API flow, hãy thiết kế matcher theo đường dẫn, phương thức, media type, và chọn entry point theo chính sách; kiểm thử trên endpoint thật.

Trên Spring Security, `defaultAuthenticationEntryPointFor` đăng ký một lựa chọn theo matcher. Nó không biến tất cả exception thành HTTP 302 và cũng không bảo đảm phản hồi fallback cho những request không match là 401. Hành vi còn lại phụ thuộc configurer và các filter xử lý request; phải xác minh bằng test.

### 6.3. Xử lý API riêng nếu cùng ứng dụng có REST endpoint

Nếu cùng ứng dụng vừa là AS vừa có protected API, nên khai báo một chain cho API **trước** chain web mặc định. Ví dụ một API dùng JWT Resource Server:

~~~java
@Bean
@Order(2)
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .securityMatcher("/api/**")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Đoạn này **thay thế** chain application `@Order(2)` của ví dụ trước bằng hai chain API `@Order(2)` và web `@Order(3)`. Không khai báo trùng hai bean ở cùng vị trí từ hai ví dụ. Cần bổ sung import cho `SessionCreationPolicy` và cấu hình JWT decoder/issuer, đồng thời bảo đảm AS phát access token dành cho API tương ứng.

Khi thiếu token trên `/api/**`, Resource Server dùng cơ chế Bearer authentication để trả 401/challenge phù hợp. Không nên để REST API vô tình match vào chain có `formLogin()` rồi nhận HTML redirect.

## 7. 401, 403, redirect và lỗi giao thức: chọn đúng điểm xử lý

### 7.1. HTTP 401 thường có nghĩa cần xác thực

`401 Unauthorized` có tên dễ gây nhầm, nhưng ý nghĩa thực tế là **thiếu/không có thông tin xác thực hợp lệ** cho tài nguyên, thường đi cùng `WWW-Authenticate`.

Ví dụ Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Cần phân biệt:

- Bearer access token thiếu/sai → Resource Server trả Bearer challenge.
- HTTP Basic client authentication tại token endpoint sai → AS tạo lỗi `invalid_client`, có thể kèm HTTP authentication challenge phù hợp.
- Browser chưa đăng nhập tại authorization endpoint → thường redirect `302` đến form login để tương tác.

### 7.2. HTTP 403 thường có nghĩa đã xác thực nhưng bị từ chối

Ví dụ người dùng đăng nhập hợp lệ nhưng cố mở endpoint quản trị bị hạn chế:

~~~http
HTTP/1.1 403 Forbidden
~~~

Ở Resource Server, nếu Bearer token hợp lệ nhưng thiếu scope, có thể trả `403` với lỗi `insufficient_scope` tùy cấu hình và thông tin chuẩn. Nếu người dùng từ chối consent, AS xử lý bằng **authorization error response**, không nhất thiết phản hồi 403 trực tiếp.

### 7.3. Token endpoint cần phản hồi OAuth2 đúng chuẩn

Các ví dụ phổ biến:

| Lỗi tại token endpoint | OAuth2 error | HTTP thường gặp | Cách xử lý |
| --- | --- | --- | --- |
| Client authentication thất bại | `invalid_client` | 401 hoặc theo quy tắc RFC áp dụng | Bộ lọc/client authentication và error response của AS |
| Authorization code sai/hết hạn/dùng lại | `invalid_grant` | 400 | Token endpoint từ chối grant |
| PKCE `code_verifier` không khớp | `invalid_grant` | 400 | Kiểm tra ràng buộc PKCE của code |
| Grant type không được hỗ trợ | `unsupported_grant_type` | 400 | Token endpoint |
| Tham số grant thiếu hoặc sai định dạng | `invalid_request` | 400 | Token endpoint |

Một HTTP request programmatic gặp lỗi tại token endpoint **không được cứu bằng cách mở /login**. OAuth2 client cần đọc HTTP status và response JSON lỗi để quyết định dừng, điều chỉnh cấu hình, hoặc khởi tạo authorization flow mới nếu hợp lệ.

### 7.4. Đừng viết một handler chung chuyển mọi exception tới login

Mẫu sai:

~~~java
// Sai mục đích: biến mọi lỗi authentication/authorization thành redirect.
.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(
        new LoginUrlAuthenticationEntryPoint("/login")
    )
)
~~~

Đặt cấu hình này bừa bãi lên một chain vừa xử lý browser, token endpoint và API có thể làm client máy nhận HTML/302 ngoài dự kiến. Phải xác định rõ nhóm request được phép redirect. Trên OAuth2 endpoint, giữ các handler và semantics giao thức của Spring Authorization Server.

## 8. Request cache, session và CSRF trong luồng đăng nhập

### 8.1. Session là một phần hợp lý của browser login

Ở authorization endpoint, người dùng thường cần đăng nhập qua trình duyệt, xác thực rồi tiếp tục consent. HTTP session có thể lưu trạng thái đăng nhập và request ban đầu; cookie session đưa browser trở lại flow.

Ở token endpoint, client xác thực bằng phương thức đã đăng ký và dùng authorization code/PKCE hoặc grant khác. Nó **không cần phải có cookie đăng nhập của Resource Owner** để đổi code. Thông tin cần thiết về authorization grant đã được lưu ở phía AS.

Không bật `SessionCreationPolicy.STATELESS` một cách máy móc cho toàn bộ ứng dụng AS nếu browser login/consent còn dựa vào session. Ngược lại, REST Resource Server dùng Bearer token có thể giữ stateless như ví dụ API chain.

### 8.2. CSRF cần được xử lý theo endpoint

Browser gửi cookie session tự động, vì thế các request thay đổi trạng thái như `POST /login` và hành động consent cần chính sách chống CSRF phù hợp. Spring Authorization Server có cấu hình endpoint theo ngữ nghĩa giao thức; application chain vẫn cần chú ý CSRF cho form login và các thao tác web.

**Không giải quyết lỗi 403 lúc POST login bằng cách tắt CSRF cho toàn bộ ứng dụng**:

~~~java
// Tránh áp dụng tùy tiện cho cả trang đăng nhập và consent:
http.csrf(csrf -> csrf.disable());
~~~

Thay vào đó:

1. Kiểm tra form thực sự gửi token `_csrf` hoặc token được framework tích hợp đúng.
2. Xác nhận tên field/header, session/cookie và thời hạn CSRF token theo cơ chế đã chọn.
3. Chỉ loại trừ CSRF cho endpoint mà giao thức/cơ chế xác thực cho phép, trong phạm vi matcher hẹp và đã được đánh giá.
4. Chạy test POST login/consent thành công và thất bại khi thiếu token.

### 8.3. Bảo vệ session và redirect sau reverse proxy

Ở môi trường production:

- Sử dụng HTTPS trên endpoint công khai; cookie session nên có `Secure` và `HttpOnly`, chính sách `SameSite` phù hợp với luồng redirect/browser.
- Định cấu hình issuer URL ổn định (thường HTTPS) và xử lý forwarded headers **chỉ từ reverse proxy đáng tin cậy**, tránh việc client tự giả mạo host/proto.
- Kiểm soát `redirect_uri` bằng đăng ký chặt chẽ; không dùng wildcard hoặc biến redirect do người dùng cung cấp.
- Bảo vệ chống session fixation bằng cơ chế Spring Security phù hợp và kiểm thử chuyển đổi session khi login.
- Xác định timeout cho session, authorization request, authorization code và chính sách đăng nhập lại.
- Với nhiều instance, thiết kế session affinity hoặc session store phân tán tương thích với cách lưu context và request cache.
- Không ghi raw authorization code, password, client secret, session cookie hoặc access token vào log và URL theo cách có thể làm lộ bí mật.

Một sai sót reverse proxy phổ biến: server thấy scheme nội bộ là HTTP nên sinh URL redirect sai dù client truy cập HTTPS. Phải kiểm tra cấu hình proxy, forwarded-header handling và allowlist proxy, không sửa bằng cách tin toàn bộ `X-Forwarded-*` từ Internet.

## 9. Quan sát và xử lý lỗi thường gặp

### 9.1. Vòng lặp `/login → /login`

**Dấu hiệu:** trình duyệt báo quá nhiều redirect hoặc URL lặp lại.

**Khả năng:** route login bị yêu cầu authenticated, custom login page chưa `permitAll()`, hoặc `/login` bị match sai chain.

**Kiểm tra:** chain nào xử lý `GET /login`; custom page đã có controller/template chưa; form login có cùng login URL và processing URL dự kiến không.

### 9.2. Đăng nhập thành công nhưng không quay lại `/oauth2/authorize`

**Dấu hiệu:** form login xác thực đúng nhưng client không nhận authorization code, người dùng ở trang chủ.

**Khả năng:** request gốc không được cache, success handler override, session mất cookie, hoặc redirect ban đầu không hợp lệ.

**Kiểm tra:** `RequestCache` và `SavedRequestAwareAuthenticationSuccessHandler`, session ID/cookie, cookie policy, load balancer và các handler login custom. Không ép redirect về URL do query parameter tùy ý cung cấp.

### 9.3. Token endpoint trả trang HTML thay vì JSON

**Dấu hiệu:** SDK OAuth2 gặp 302 hoặc trả HTML trong khi đang đổi code.

**Khả năng:** global login entry point, thứ tự/matcher chain sai hoặc reverse proxy chuyển nhầm route.

**Kiểm tra:** AS endpoints matcher, filter chain ưu tiên, `Accept`, lỗi OAuth2 dự kiến, và việc cấu hình `authenticationEntryPoint` toàn cục. Khôi phục error handling đúng giao thức.

### 9.4. `POST /login` trả 403

**Dấu hiệu:** GET login hiển thị bình thường, nhưng POST trả 403.

**Khả năng:** thiếu/sai CSRF token, cookie session không được gửi, security matcher không khớp hoặc rule bảo mật đang từ chối.

**Kiểm tra:** CSRF token trong form, cookie, header, form action và filter chain. Phân biệt 403 do CSRF với login failure do sai mật khẩu (thường do failure handler xử lý).

### 9.5. Login thành công nhưng authorization endpoint vẫn xem là anonymous

**Dấu hiệu:** sau khi POST login thành công, `GET /oauth2/authorize` lại redirect đến login.

**Khả năng:** `SecurityContext` không được lưu, session/cookie không giữ, host/domain thay đổi, hoặc chain stateless đã bị áp dụng sai.

**Kiểm tra:** session creation policy, `SecurityContextRepository`, session cookie domain/path, proxy, success handler và login flow custom. Với cơ chế explicit-save, tự viết authentication logic có thể cần gọi `SecurityContextRepository.saveContext(...)` để lưu authentication cho request sau.

### 9.6. API của cùng ứng dụng trả `/login` cho mọi lỗi

**Dấu hiệu:** REST client nhận HTML.

**Khả năng:** API đang match vào web chain có form login.

**Cách xử lý:** tách `/api/**` vào Resource Server chain có Bearer authentication; yêu cầu HTTP 401/403 phù hợp. Nếu API là endpoint nội bộ không dùng OAuth2, vẫn phải chọn entry point API theo định dạng contract của nó.

## 10. Kiểm thử entry point và hành vi chưa xác thực

### 10.1. Ma trận kiểm thử có thể áp dụng

| Ca kiểm thử | Điều kiện | Kết quả cần xác minh |
| --- | --- | --- |
| Trình duyệt chưa login gọi authorization endpoint hợp lệ | `Accept: text/html`, client/redirect URI đã đăng ký | Redirect đến `/login`, có cơ chế tiếp tục request sau login |
| Truy cập `GET /login` khi chưa login | Application/login chain | Trang login trả được, không redirect loop |
| POST login credential sai, CSRF hợp lệ | Form login | Failure handler hoạt động, không phát code/token |
| POST login credential đúng, CSRF hợp lệ | Form login | User được xác thực và quay lại authorization request phù hợp |
| POST login thiếu CSRF | Cookie/session + form login | Bị từ chối theo CSRF policy |
| Client xác thực sai ở token endpoint | HTTP client | Phản hồi lỗi OAuth2 `invalid_client`, không nhận trang HTML login |
| Token endpoint nhận code sai hoặc PKCE verifier sai | Authorization code grant | `invalid_grant`, không cấp token |
| Authorization request có redirect URI không đăng ký | Browser | AS từ chối; không redirect đến URL nguy hiểm |
| API thiếu Bearer token | Resource Server chain | 401/challenge, không redirect login |
| API có Bearer token hợp lệ nhưng thiếu scope | Resource Server chain | Truy cập bị từ chối theo authorization policy |

### 10.2. MockMvc kiểm tra browser redirect

Đây là mẫu kiểm thử cho cấu hình có AS, client đăng ký và một authorization request được tạo hợp lệ. Phải dùng `client_id`, `redirect_uri`, scope và PKCE challenge đúng với fixture thực tế.

~~~java
@Test
void unauthenticatedBrowserIsSentToLogin() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
            .param("response_type", "code")
            .param("client_id", "booking-web")
            .param("redirect_uri", "https://client.example.test/callback")
            .param("scope", "openid", "profile")
            .param("state", "fixture-state")
            .param("code_challenge", "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
            .param("code_challenge_method", "S256")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location", org.hamcrest.Matchers.containsString("/login")));
}
~~~

`code_challenge` trong ví dụ có thể khớp một `code_verifier` hợp lệ khi tạo theo PKCE; `state` chỉ là fixture, không dùng làm giá trị cố định trong production. Để assertion không thất bại do redirect hoặc yêu cầu đăng ký, cần chuẩn bị `RegisteredClient` đúng với endpoint và scope, user chưa login, và cơ chế cookie/session như app thật.

### 10.3. MockMvc kiểm tra login được mở công khai

~~~java
@Test
void loginPageIsAvailableToAnonymousUser() throws Exception {
    mockMvc.perform(get("/login").accept(MediaType.TEXT_HTML))
        .andExpect(status().isOk());
}
~~~

Nếu dùng custom login page, test còn phải kiểm tra template được render và field CSRF được cung cấp. Nếu dùng default generated page, có thể kiểm tra response HTML nhưng tránh ràng buộc quá cứng vào markup nội bộ của Spring Security.

### 10.4. Test phân biệt authentication và authorization

Không chỉ test HTTP status; cần chứng minh hệ thống không phát token hoặc lộ thông tin khi request sai:

~~~text
[1] Người dùng chưa login + authorization request hợp lệ:
    -> browser redirect login.

[2] Người dùng đã login + client yêu cầu scope không được phép:
    -> AS từ chối hoặc xử lý consent/authorization theo chính sách,
       không tự động cấp scope vượt đăng ký.

[3] Client gửi client_secret sai tới token endpoint:
    -> OAuth2 error, không HTML login.

[4] Authorization code đã sử dụng một lần:
    -> không đổi tiếp thành token mới.

[5] Resource Server không có Bearer token:
    -> 401, challenge đúng loại token.

[6] Resource Server có Bearer token nhưng thiếu scope:
    -> 403 hoặc lỗi quyền theo contract, không đưa sang login.
~~~

Một số test `MockMvc` có `@WithMockUser` hoặc `oauth2Login()` chỉ giả lập Authentication; chúng không xác nhận login/session thực sự, redirect sau consent hay xác minh PKCE. Đối với hệ AS, phải bổ sung test tích hợp hoàn chỉnh với registration, session, authorization code, token endpoint và client thực tế.

### 10.5. Quan sát filter chain mà không làm lộ thông tin nhạy cảm

Khi lỗi khó tái hiện, có thể bật logging tạm thời cho Spring Security ở môi trường test, xác định:

1. Request khớp `SecurityFilterChain` nào.
2. `Authentication` hiện tại đang anonymous, authenticated user hay authenticated client.
3. Handler nào tạo redirect hoặc status.
4. `RequestCache` có lưu request không và success handler chọn URL nào.
5. OAuth2 endpoint filter đã trả lỗi giao thức gì.
6. Session/CSRF có nhất quán sau login không.

Tránh lưu nguyên HTTP `Authorization`, cookie, body chứa password/client secret, code, refresh token, ID token hay access token. Chỉ ghi request ID, endpoint, loại principal, mã lỗi, loại handler và metadata không nhạy cảm cần thiết.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `GET /oauth2/authorize` thiếu session thường redirect đến login, nhưng `POST /oauth2/token` với client secret sai không nên redirect?

**Đáp án:** Authorization endpoint có luồng browser với Resource Owner cần xác thực tương tác. Token endpoint là request máy với giao thức OAuth2; lỗi client authentication phải trả `invalid_client` theo chuẩn để OAuth2 client xử lý.

**Câu 2.** `LoginUrlAuthenticationEntryPoint("/login")` có tự tạo trang HTML `/login` và xác thực username/password không?

**Đáp án:** Không. Nó xác định phản hồi redirect. Trang và xử lý form được cung cấp bởi chain login, filter form login, controller/template tùy cấu hình.

**Câu 3.** Điều gì xảy ra nếu chain `anyRequest().authenticated()` không cho anonymous truy cập trang custom `/login`?

**Đáp án:** Có thể tạo vòng lặp redirect `/login`. Cần định vị đúng chain và cấu hình trang login là công khai trong phạm vi cần thiết.

**Câu 4.** `AuthenticationEntryPoint` và `AccessDeniedHandler` khác nhau thế nào?

**Đáp án:** Entry point bắt đầu xác thực khi request chưa có mức xác thực phù hợp. Access denied handler xử lý request bị từ chối khi đã xác thực đủ để không cần bắt đầu login lại. Với anonymous, `AccessDeniedException` cũng có thể dẫn đến entry point.

**Câu 5.** Vì sao sau login cần `RequestCache` hoặc chiến lược tiếp tục authorization request?

**Đáp án:** Browser cần quay lại request OAuth2 ban đầu với client ID, scope, state, redirect URI và PKCE challenge hợp lệ. Nếu bị đưa tới trang chủ, luồng cấp code có thể bị bỏ dở.

**Câu 6.** Vì sao không nên tắt CSRF toàn cục chỉ để POST form login thành công?

**Đáp án:** Form login và consent qua session/cookie có bề mặt CSRF. Phải cung cấp/kiểm tra CSRF token phù hợp và chỉ ngoại lệ những endpoint có cơ sở giao thức, không loại bỏ bảo vệ toàn bộ.

**Câu 7.** Một ứng dụng có cả AS và REST API. Làm sao tránh để API thiếu token nhận HTML login?

**Đáp án:** Cấu hình riêng API `SecurityFilterChain` với matcher và Resource Server/Bearer entry point thích hợp, đặt thứ tự trước web chain, để API trả HTTP 401/403 và challenge đúng contract.

## 12. Checklist cấu hình trước khi triển khai

- [ ] Authorization Server endpoints được match bởi chain riêng với độ ưu tiên cao.
- [ ] Browser authorization request chưa login được chuyển đến login page đúng URL.
- [ ] `GET /login` được truy cập khi anonymous, không có redirect loop.
- [ ] `POST /login` xác thực và xử lý CSRF thành công, thất bại theo đúng chính sách.
- [ ] Sau login, trình duyệt tiếp tục authorization request gốc khi cần.
- [ ] OAuth2 token endpoint trả lỗi OAuth2 đúng định dạng, không xuất HTML login.
- [ ] API/Resource Server trả 401/403 phù hợp và không bị web chain chiếm matcher.
- [ ] Không redirect đến `redirect_uri` chưa được xác minh.
- [ ] Session/cookie, HTTPS, proxy headers và issuer URL tương thích môi trường triển khai.
- [ ] Test các tình huống HTML/JSON, client credential sai, PKCE sai, không đủ quyền và consent từ chối.
- [ ] Có cơ chế log chẩn đoán nhưng không làm lộ secret, cookie hoặc token.

## 13. Tổng kết và tài liệu tham khảo

Trong Authorization Server, **login entry point là cơ chế bắt đầu xác thực tương tác**, thường được dùng khi Resource Owner chưa đăng nhập vào authorization endpoint. Cấu hình đúng phải xét **SecurityFilterChain được chọn, loại endpoint, loại chủ thể cần xác thực và kiểu phản hồi HTTP**. Spring Security có `AuthenticationEntryPoint` và `ExceptionTranslationFilter` để xử lý yêu cầu bắt đầu authentication, còn Spring Authorization Server có các filter và response riêng để thực thi OAuth 2.0/OIDC.

Hai nguyên tắc hữu ích nhất khi thiết kế là: **request HTML vào authorization endpoint có thể redirect đến `/login`; request token/API phải nhận kết quả đúng giao thức của nó**, và **không được bỏ qua ranh giới bảo mật chỉ để làm login flow thuận tiện hơn**. Kết hợp cấu hình chain, request cache, session/CSRF, kiểm tra redirect URI và test tích hợp giúp luồng Authorization Code + PKCE hoạt động chính xác từ lúc chưa xác thực tới lúc cấp token.

Nguồn tham khảo chính thức, cần chọn phiên bản tài liệu tương ứng với dự án:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)

Các mẫu code minh họa nguyên tắc trên nhánh Spring Security 6/Spring Authorization Server 1.x, và giả định phần đăng ký client, xác thực người dùng, khóa ký, lưu authorization/consent đã được cấu hình ở những phần khác của ứng dụng. Nếu dùng phiên bản Spring Security mới hơn, hãy đối chiếu thay đổi package/API trước khi sao chép code.

