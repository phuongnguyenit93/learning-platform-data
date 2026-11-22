# Request cache, redirect và các hành vi không phù hợp với API máy gọi

## 1. Vấn đề: cơ chế đăng nhập web không luôn phù hợp với Resource Server

Một ứng dụng Spring Security có thể phục vụ **trang web tương tác với người dùng** hoặc **API được gọi bằng máy**. Hai loại client có trải nghiệm xác thực rất khác nhau:

- **Browser web app** có thể chuyển người dùng tới trang đăng nhập, giữ lại URL ban đầu trong session và đưa người dùng quay về sau khi đăng nhập.
- **API machine-to-machine**, mobile app, CLI, batch job, service mesh hoặc backend khác thường không có người dùng đang chờ nhập mật khẩu. Chúng gửi một **OAuth 2.0 access token** qua `Authorization: Bearer ...` và mong chờ một HTTP response có status, headers, body phù hợp giao thức.

Trong module **Spring Security OAuth 2.0 OIDC Resource Server**, chương **Trạng thái và bảo vệ web**, bài này tập trung vào câu hỏi: **Khi cấu hình API Bearer token, cần xử lý request cache, redirect và những tính năng phục vụ browser login như thế nào để không phá vỡ hợp đồng API?**

Một tình huống không mong muốn:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Accept: application/json
~~~

Resource Server thiếu cấu hình phân biệt API và browser, dẫn tới:

~~~http
HTTP/1.1 302 Found
Location: /login
Set-Cookie: JSESSIONID=<SESSION_ID>
~~~

Client HTTP tự theo redirect rồi nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<!doctype html>
<html><body><form action="/login" method="post">...</form></body></html>
~~~

**API không thực sự trả dữ liệu đơn hàng.** Nhưng client có thể thấy HTTP 200 sau redirect, cố parse HTML thành JSON hoặc ghi nhận sai rằng thao tác thành công. Ngoài vấn đề giao thức, session và request cache có thể tạo trạng thái server không cần thiết.

Với một **Resource Server chỉ nhận Bearer token**, phản hồi thông dụng khi thiếu token là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

Không có trang login, không có redirect đến Identity Provider và không cần lưu URL để khôi phục sau đăng nhập tương tác. Với token hợp lệ nhưng thiếu quyền, phản hồi thường là **403 Forbidden**.

> Phạm vi bài: **Resource Server API**. OAuth 2.0 Authorization Code/OIDC login dành cho browser **đúng là có redirect theo giao thức**. Không phải mọi redirect đều xấu; lỗi nằm ở việc áp workflow browser-login cho API chỉ phục vụ machine clients.

## 2. Request cache là gì?

Trong Spring Security Servlet, **`RequestCache`** là abstraction giữ lại một request ban đầu để có thể khôi phục hoặc điều hướng trở lại sau khi người dùng được xác thực. Cơ chế này thường gắn với ứng dụng web có **form login** hoặc OAuth 2.0 login tương tác.

Luồng browser điển hình:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    participant W as Login page / Identity Provider
    B->>S: GET /account/profile (chưa đăng nhập)
    S->>S: Lưu saved request theo RequestCache
    S-->>B: 302 Location: /login
    B->>W: Hiển thị/đi tới trang login
    W-->>S: Login thành công theo flow phù hợp
    S->>S: Tìm request đã lưu
    S-->>B: Redirect tới /account/profile
    B->>S: GET /account/profile (đã đăng nhập)
    S-->>B: Trả nội dung
~~~

Cơ chế này hữu ích khi browser có người dùng và **trạng thái phiên** hỗ trợ workflow. Nhưng một API client đang chờ JSON không có khả năng “đăng nhập rồi quay lại” theo cùng cách; lưu request và trả 302 có thể chỉ gây lỗi.

### 2.1. Các thành phần Servlet thường gặp

| Thành phần | Vai trò |
|---|---|
| `RequestCache` | Hợp đồng lưu và truy xuất request đã yêu cầu xác thực |
| `HttpSessionRequestCache` | Implementation lưu saved request vào HTTP session |
| `SavedRequest` / `DefaultSavedRequest` | Biểu diễn metadata của request được lưu |
| `NullRequestCache` | Implementation không lưu request; phù hợp API stateless |
| `RequestCacheAwareFilter` | Hỗ trợ khôi phục request đã lưu khi cần |
| `ExceptionTranslationFilter` | Kết nối một số lỗi authentication/authorization tới entry point và request cache |
| `AuthenticationEntryPoint` | Xác định cách phản hồi khi cần xác thực |
| `LoginUrlAuthenticationEntryPoint` | Entry point dành cho browser, thường redirect đến login URL |
| `SavedRequestAwareAuthenticationSuccessHandler` | Sau browser login có thể dùng saved request để redirect |
| `BearerTokenAuthenticationEntryPoint` | Trả Bearer challenge kiểu RFC 6750 khi authentication thất bại |
| `BearerTokenAccessDeniedHandler` | Trả response khi Bearer-authenticated principal thiếu quyền |

Không có thành phần nào ở đây có nhiệm vụ xác minh JWT signature hay introspection token. Những bước đó thuộc **`JwtDecoder`** hoặc **`OpaqueTokenIntrospector`**. Request cache là **workflow HTTP/navigation**, không phải hệ thống lưu access token hoặc cơ chế cấp quyền.

### 2.2. Request cache lưu thông tin gì?

Với `HttpSessionRequestCache`, một saved request có thể mang URL, method và những metadata request cần để khôi phục điều hướng. Các chi tiết cụ thể phụ thuộc framework và configuration.

**Không coi saved request là nơi lưu payload nghiệp vụ**, không tự ghi Bearer token/Authorization header vào đó và không dựa vào request cache để replay một POST thay đổi trạng thái một cách tùy tiện. Một browser redirect mới thường tạo request HTTP mới; điều đó khác việc bảo đảm mọi dữ liệu của request cũ sẽ được khôi phục an toàn.

Đối với API chứa thông tin nhạy cảm trong URL query, việc lưu URL không cần thiết vào session còn tạo thêm bề mặt dữ liệu. Nên tránh đưa access token vào query string ngay từ đầu, và với pure Bearer API, thường **không cần saved request**.

### 2.3. Request cache có phải HTTP response cache không?

**Không.** Đây là ba khái niệm khác nhau:

| Tên | Lưu gì? | Mục đích |
|---|---|---|
| **Spring Security RequestCache** | Request chưa hoàn tất authentication để khôi phục flow browser | Redirect sau đăng nhập |
| **HTTP response cache** | Representation của HTTP response theo `Cache-Control`/ETag | Hiệu năng trình duyệt, CDN, proxy |
| **Token/introspection cache** | Kết quả đã xác minh của access token hoặc JWKS/state | Giảm chi phí kiểm tra authentication |

`NullRequestCache` **không tự tắt HTTP caching**, không xóa JWT cache và không bảo vệ mọi response khỏi CDN. Ngược lại, `Cache-Control: no-store` của response cũng **không thay thế** việc vô hiệu hóa saved request.

## 3. Điều gì xảy ra khi request chưa được xác thực?

Để hiểu redirect phát sinh từ đâu, cần phân biệt các nhánh xử lý trong Spring Security:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityFilterChain được chọn"]
    B --> C{"Có Bearer token?"}
    C -->|Có| D["BearerTokenAuthenticationFilter"]
    D --> E{"Token được xác minh?"}
    E -->|Không| F["Bearer authentication failure / entry point"]
    E -->|Có| G["Authentication đã xác thực"]
    C -->|Không| H["Anonymous hoặc chưa xác thực"]
    H --> I["HTTP authorization"]
    G --> I
    I --> J{"Rule có được thỏa?"}
    J -->|Có| K["Controller / service"]
    J -->|"Không, chưa xác thực"| L["Exception translation / authentication entry point"]
    J -->|"Không, đã xác thực"| M["AccessDeniedHandler"]
    F --> N["Thường 401 + WWW-Authenticate: Bearer"]
    L --> O["401 Bearer hoặc 302 login tùy chain/entry point"]
    M --> P["Thường 403"]
~~~

Lưu ý: **Không phải mọi lỗi đều được phát ra từ cùng filter.** `BearerTokenAuthenticationFilter` có thể tự xử lý lỗi xác thực token thông qua entry point của nó. `ExceptionTranslationFilter` chủ yếu xử lý các `AuthenticationException` và `AccessDeniedException` phát sinh ở các filter phía sau. Sự khác biệt này quan trọng khi tự viết handler và thấy một handler không được gọi như mong đợi.

### 3.1. Browser entry point và API entry point khác nhau

Giả sử cùng một yêu cầu chưa xác thực `GET /api/orders`:

| Cấu hình chain | Hành vi có thể xảy ra |
|---|---|
| Form login browser + `LoginUrlAuthenticationEntryPoint` | 302 redirect tới `/login` |
| OAuth 2.0/OIDC login browser | Redirect tới điểm bắt đầu authorization/login flow phù hợp |
| HTTP Basic | 401 với `WWW-Authenticate: Basic ...` |
| Bearer Resource Server | 401 với `WWW-Authenticate: Bearer` |
| Handler tùy chỉnh không phù hợp | Có thể trả 200, HTML hoặc redirect sai hợp đồng |

Spring Security có thể chọn entry point theo matcher/content negotiation khi nhiều cơ chế cùng tồn tại. Vì vậy không nên suy luận rằng chỉ cần thêm một dòng `oauth2ResourceServer()` là **mọi URL trong mọi chain** chắc chắn không còn chuyển hướng login.

### 3.2. Khi request có Bearer token sai

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <EXPIRED_OR_INVALID_TOKEN>
~~~

Đáp ứng theo Bearer challenge thường gồm:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Đừng redirect sang form login để “sửa” token hết hạn của máy gọi. API client phải tự xử lý lifecycle credential theo OAuth 2.0: dùng quy trình token acquisition/refresh hợp lệ ở phía client nếu được phép, hoặc báo lỗi cho người vận hành. Resource Server không phải nơi tự động bắt đầu login tương tác mỗi khi token invalid.

### 3.3. Token hợp lệ nhưng không đủ scope

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITHOUT_ORDERS_READ>
~~~

Phản hồi thường là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Hành vi/header cụ thể tùy `AccessDeniedHandler`, trạng thái principal và cấu hình authorities. **Không biến thiếu scope thành redirect login** với kỳ vọng người dùng đăng nhập lại; việc cấp thêm permission phải qua luồng ủy quyền/quản trị hợp lệ, không phải ngầm vượt security policy.

## 4. Vì sao redirect làm hỏng API máy gọi?

### 4.1. Client tự theo redirect rồi nhận HTML thay JSON

Nhiều HTTP clients tự động theo `Location` khi gặp 301/302/303/307/308 theo cấu hình. Một client gọi API có thể thấy:

~~~text
GET /api/orders/42
  → 302 /login
  → GET /login
  → 200 text/html
  → JSON parser error
~~~

Một client khác **không theo redirect** và trả ra 302 để ứng dụng xử lý. Hai client gặp cùng API có thể biểu hiện lỗi khác nhau, khiến sự cố khó chẩn đoán.

### 4.2. Redirect làm sai semantics của request

Đối với POST/PUT/PATCH/DELETE, các mã redirect có semantics khác nhau về method và body. Một số clients có thể chuyển POST sang GET với 302/303; 307/308 có xu hướng giữ method/body. Không thể kỳ vọng “đăng nhập xong tự động gọi lại request ghi dữ liệu” là an toàn.

Đối với API machine clients, giải pháp là **trả status xác thực rõ ràng ngay trên request gốc**, không dựa vào redirect navigation.

### 4.3. Redirect có thể gây rủi ro tiết lộ thông tin

Một `Location` không được thiết kế đúng có thể:

- Dẫn client tới host không mong muốn.
- Đẩy query parameters hoặc URL nhạy cảm sang login page hay logs.
- Kích hoạt redirect chain khó kiểm soát.
- Tạo các kết quả khác nhau tùy HTTP client có chuyển tiếp `Authorization` qua redirect hay không.

**Không tự thiết kế redirect với nguyên Bearer token trong query string.** Dù HTTP client thư viện có cơ chế bỏ Authorization khi chuyển host, không nên dựa vào hành vi đó như lớp bảo vệ chính.

### 4.4. Redirect không phải lỗi trong OIDC Authorization Code

Một **OIDC client** tương tác với browser có thể thực hiện:

~~~text
Browser → Client app → Authorization Server login
        → Authorization Code callback
        → Client app xử lý code + token endpoint
~~~

Đó là một **luồng OAuth 2.0/OIDC được thiết kế trước**, có `state`, PKCE/nonce theo bối cảnh và các kiểm tra chống tấn công. Nó không có nghĩa mọi Bearer Resource Server API nên redirect client bất kỳ đến IdP khi request thiếu token.

**OAuth2 Client/Login** và **OAuth2 Resource Server** là các vai trò bảo mật khác nhau, dù cùng được Spring Security hỗ trợ trong một hệ thống.

## 5. Thiết kế một Resource Server API không lưu saved request

Giả sử Orders API có các yêu cầu:

| Endpoint | Điều kiện |
|---|---|
| `GET /api/orders/**` | Access token có `SCOPE_orders.read` |
| `POST /api/orders` | Access token có `SCOPE_orders.create` |
| `GET /api/me` | Principal được xác thực |
| `GET /api/public/status` | Công khai |
| Những URL chưa phân loại | Từ chối |

Chính sách HTTP mong muốn:

1. Không redirect client tới `/login` hoặc Identity Provider.
2. Không lưu request vào HTTP session để redirect sau login.
3. Không dùng cookie/session làm cơ chế duy trì authentication Bearer giữa các requests.
4. Khi thiếu/sai token, trả Bearer challenge thích hợp.
5. Khi đã xác thực nhưng thiếu authority, trả lỗi phân quyền.
6. Mỗi request protected phải được xác thực bằng token/bằng chứng hợp lệ của chính request đó.

### 5.1. Dependencies

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Để dùng JWT, Resource Server cần implementation JOSE tương ứng; Spring Boot starter hiện đại thường kéo theo dependency phù hợp. Nếu tự quản dependency, cần kiểm tra module Spring Security OAuth 2.0 JOSE theo phiên bản dự án.

### 5.2. Cấu hình issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

`issuer-uri` là nguồn tin cậy được cấu hình trước. API cần thêm kiểm tra `aud` dành cho `orders-api` nếu hợp đồng yêu cầu; chỉ kiểm tra issuer và chữ ký không tự chứng minh token đúng resource audience. Nếu dùng opaque token, cấu hình introspection endpoint thay thế được trình bày ở phần sau.

### 5.3. Cấu hình Servlet `SecurityFilterChain` cho Bearer API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/status")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Đây là cấu hình minh họa dành cho **API Servlet chỉ nhận Bearer token**, không dùng browser session/cookie làm credential. Những quyết định quan trọng:

- `SessionCreationPolicy.STATELESS`: Spring Security không dùng HTTP session để duy trì security context giữa các requests.
- `NullRequestCache`: không lưu request đang đợi authentication để redirect sau login.
- `formLogin(...disable)`, `oauth2Login(...disable)`: không kích hoạt login tương tác trong chain API này.
- `httpBasic(...disable)`: không yêu cầu Basic login của browser cho API.
- `csrf(...disable)`: chỉ phù hợp trong giả định API không sử dụng cơ chế credential được trình duyệt tự gửi như cookie-based session authentication. **Không sao chép quyết định này sang ứng dụng browser dùng cookies**.
- `oauth2ResourceServer(...jwt(...))`: Spring Security xử lý Bearer JWT và phản hồi authentication theo Resource Server.
- `anyRequest().denyAll()`: URL/method chưa phân loại không tự được chấp nhận.

Ví dụ chưa bao gồm controller, audience validator, quyền trên từng đơn hàng hoặc CORS source nếu browser JavaScript là một trong các API consumers. Các phần đó phải được cấu hình theo hợp đồng hệ thống.

**Không cần tự viết một `AuthenticationEntryPoint` trả 302.** Spring Security Resource Server có entry point cho Bearer token; khi tự override exception handling, phải bảo toàn semantics đó.

### 5.4. Lưu ý về `csrf(...disable)`

Trong pure Bearer API:

~~~text
Client chủ động gửi Authorization: Bearer <token>
Không dùng session cookie làm credential
Không dựa vào browser tự gửi cookie để xác thực
~~~

CSRF thường không phải rủi ro theo cơ chế browser tự gắn credential của ứng dụng cookie-based. Nhưng nếu cùng server còn:

- Session-based authentication với cookie.
- HTTP Basic được browser cache và tự gửi.
- Refresh/session cookie trên những endpoint ghi dữ liệu.
- Form-based login hoặc những POST được xác thực bằng browser cookie.

thì **không thể kết luận an toàn chỉ bằng “đã bật Resource Server”**. Cần CSRF protection ở đúng chain/endpoint hoặc tách chain rõ ràng. Tắt CSRF ở chain API không được làm vô hiệu hóa bảo vệ của các browser routes.

### 5.5. Nếu muốn chính sách Bearer entry point tường minh

Có thể đặt hai handler do Spring Security cung cấp:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(new BearerTokenAuthenticationEntryPoint())
    .accessDeniedHandler(new BearerTokenAccessDeniedHandler())
);
~~~

Đoạn trên là một **phần cấu hình bổ sung** bên trong phương án Servlet `HttpSecurity`, không phải một bean SecurityFilterChain thứ hai. `BearerTokenAuthenticationEntryPoint` trả challenge phù hợp cho authentication failure; `BearerTokenAccessDeniedHandler` xử lý access denied theo semantics Bearer.

Trong ứng dụng không custom entry point, Resource Server configuration thường đã cung cấp handler Bearer phù hợp. Chỉ override khi thực sự có yêu cầu nhất quán nhiều mechanisms/chains và hiểu thứ tự đăng ký entry points.

### 5.6. Thay JWT bằng opaque token có đổi yêu cầu stateless không?

Không. Một Resource Server có thể dùng:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

với cấu hình introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Những property này dùng biến môi trường/secret manager phù hợp. Khi đó authentication kiểm tra token qua introspection; **request cache và redirect login vẫn không cần thiết** nếu API chỉ phục vụ machine clients. Không nhầm **introspection cache** (giảm chi phí kiểm tra token) với **saved request cache** (khôi phục URL sau browser login).

## 6. `NullRequestCache` và `SessionCreationPolicy.STATELESS` giải quyết hai câu hỏi khác nhau

Một lỗi thiết kế thường gặp là nghĩ chỉ cần một trong hai là hệ thống đã “hoàn toàn không có state”.

| Cấu hình | Điều chỉnh điều gì? | Không bảo đảm điều gì? |
|---|---|---|
| `requestCache(new NullRequestCache())` | Không lưu/khôi phục saved requests qua RequestCache | Không ngăn mọi filter/controller khác tạo HTTP session |
| `sessionCreationPolicy(STATELESS)` | Spring Security không dùng HTTP session để lấy/lưu security context theo chính sách này | Không cấm code ứng dụng hoặc library khác tự gọi `request.getSession()` |
| `formLogin(disable)` | Không dùng browser form authentication trong chain | Không tự tắt OAuth2 Login hoặc Basic nếu chúng được bật ở nơi khác |
| `oauth2Login(disable)` | Không bắt đầu OIDC/OAuth2 browser login trong chain | Không tự thiết lập Bearer authentication |
| `NullSecurityContextRepository` | Không persist security context qua repository đó | Không cấm mọi session, không thay JWT signature validation |
| `csrf(disable)` | Vô hiệu CSRF filter protection trong phạm vi chain | Không phải cơ chế stateless; có thể tạo rủi ro nếu cookie auth còn hoạt động |

### 6.1. Tại sao nên nêu cả session policy và request cache?

Hai nhu cầu độc lập:

~~~text
Authentication continuity giữa các request:
    SessionCreationPolicy / SecurityContextRepository

Khôi phục URL sau browser login:
    RequestCache / SavedRequest
~~~

Một app có thể không persist authentication trong session nhưng vẫn có library tạo session để lưu OAuth 2.0 authorization request. Ngược lại, có thể vô hiệu request cache nhưng vẫn dùng session cookie để giữ login browser. Không nên trộn hai trường hợp.

### 6.2. `SecurityContextRepository` và request-scoped context

Spring Security giữ `Authentication` trong security context trong quá trình xử lý request. Một số implementation repository có thể lưu context qua HTTP session; implementation khác có thể chỉ dùng request attributes hoặc không persist qua requests.

Đối với Bearer Resource Server:

~~~text
Request A mang Bearer token A
  → xác thực A
  → dùng principal A trong request A
  → không cần session để request B sử dụng lại A

Request B mang Bearer token B
  → xác thực B độc lập
~~~

`SessionCreationPolicy.STATELESS` thể hiện ý định không dùng session để tạo liên kết authentication giữa A và B. Điều này không đồng nghĩa security context phải “biến mất” trước khi service/controller xử lý **trong cùng request**; context vẫn cần hiện diện trong vòng đời request.

### 6.3. Có nên buộc `NullSecurityContextRepository`?

Spring Security có thể dùng repository theo request attribute để duy trì context trong một số dispatch/error handling, hoặc repository khác tùy cấu hình. Khi muốn tùy biến cách persist, API:

~~~java
import org.springframework.security.web.context.NullSecurityContextRepository;

http.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository())
);
~~~

Đây là **phương án tùy chỉnh có chủ đích**, không phải bắt buộc thêm vào mọi API đã đặt `STATELESS`. Nếu sử dụng `NullSecurityContextRepository`, cần kiểm tra hành vi trên `ERROR`/`ASYNC` dispatch, filters và exception handling đang dựa vào request-scoped security context. Không vô tình xóa context mà những bước xử lý hợp lệ trong cùng request cần dùng.

Nếu mục tiêu chỉ là **không lưu saved request và không duy trì authentication qua session**, cấu hình `NullRequestCache` + `STATELESS` cùng Resource Server thường là điểm khởi đầu rõ ràng hơn.

### 6.4. Cookie `JSESSIONID` vẫn xuất hiện có chứng minh Spring Security sai không?

Không thể kết luận chỉ từ một header:

~~~http
Set-Cookie: JSESSIONID=<SESSION_ID>
~~~

Session có thể do controller, view engine, CSRF token repository, OAuth2 Login chain, monitoring library hoặc một thành phần khác tạo. Cần xác định **chain đã chọn** và nguồn nào gọi `getSession()`. `STATELESS` chỉ nêu chính sách của Spring Security trong phạm vi tương ứng; nó không vô hiệu hóa mọi API tạo session của Servlet container.

Để kiểm chứng pure API:

- Request không có cookie/session trước đó.
- Gọi endpoint thành công và thất bại.
- Quan sát API có tạo `Set-Cookie: JSESSIONID` không.
- Xem liệu có component nào thực sự cần tạo session hay không.
- Với yêu cầu hoàn toàn không session, cấu hình riêng component đó thay vì chỉ bổ sung nhiều lựa chọn security không liên quan.

### 6.5. Lưu token vào session để tránh xác minh lại có phù hợp không?

Bearer Resource Server thường không cần biến request có token thành “login session” của server. Nếu nhận token một lần rồi lưu `Authentication` vào session để bỏ qua kiểm tra các requests sau, hệ thống đã thay đổi mô hình trust:

- Client bắt đầu dựa vào cookie/session như credential mới.
- Revocation/expiry/audience có thể không được đánh giá lại theo policy.
- CSRF và session fixation trở nên liên quan hơn.
- API không còn rõ ràng là stateless Bearer authentication.

Nếu sản phẩm có yêu cầu duy trì session browser, cần thiết kế một **web login/BFF architecture** riêng với quản lý session, CSRF, cookie flags, refresh và logout; không nên tạo session ngầm chỉ để làm Bearer API “đỡ gọi decoder/introspection”.

## 7. Browser login và Bearer Resource Server có thể sống cùng một ứng dụng

Một sản phẩm có thể vừa có:

~~~text
/web/**        Browser UI, OAuth2 Login + session cookie
/api/**        Machine API, Bearer JWT/opaque, stateless
/public/**     Public files/pages
~~~

Hai nhóm không nhất thiết dùng cùng `AuthenticationEntryPoint`, `RequestCache`, CSRF policy hoặc session strategy.

**Phân tách `SecurityFilterChain` theo phạm vi URL thường dễ kiểm soát hơn** cố đoán client có phải browser chỉ bằng `Accept: text/html`.

### 7.1. Thứ tự chọn chain

Trong Servlet, `FilterChainProxy` duyệt nhiều `SecurityFilterChain` và chọn **chain đầu tiên khớp request**. `@Order` quyết định thứ tự, còn `securityMatcher(...)` xác định phạm vi một chain.

~~~mermaid
flowchart TD
    R["HTTP request"] --> P["FilterChainProxy"]
    P --> A{"Khớp API chain đầu tiên?"}
    A -->|Có| B["/api/**: Bearer + stateless + NullRequestCache"]
    A -->|Không| C{"Khớp Browser chain?"}
    C -->|Có| D["/web/**: OAuth2 Login + session + saved request"]
    C -->|Không| E["Fallback: default deny / public allowlist"]
    B --> F["API: 401/403 hoặc dữ liệu nghiệp vụ"]
    D --> G["Browser: có thể redirect login"]
    E --> H["Response theo fallback policy"]
~~~

Một `anyRequest().denyAll()` bên trong API chain chỉ áp cho các request **đã khớp `securityMatcher("/api/**")`**. Nó không bảo vệ các URL hoàn toàn nằm ngoài mọi chain. Cần có fallback chain hoặc một cơ chế bảo vệ tương đương.

### 7.2. Ví dụ hai chain với policies khác nhau

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class MixedApplicationSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/oauth2/**", "/login/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/web/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

**Đây là mẫu cấu trúc**, cần điều chỉnh để chạy với route login/callback thực tế của OIDC provider:

- Browser `oauth2Login()` cần **OAuth2 client registration**, redirect URI/callback và authorization-request repository phù hợp.
- Default OAuth2 authorization-request endpoint thường thuộc `/oauth2/authorization/{registrationId}`; OAuth2 login callback mặc định thường thuộc `/login/oauth2/code/{registrationId}`. Phạm vi `securityMatcher` của browser chain phải bao phủ đúng những endpoints thực tế đang dùng.
- Một browser login có thể cần GET `/login` public hoặc trang login riêng; trong mẫu trên, các URL đó chưa được trình bày thành policy hoàn chỉnh. Hãy cấu hình public entrypoints đúng để không tạo redirect loop.
- Không tắt CSRF cho browser chain chỉ vì API chain đã tắt. Browser có cookie/session cần CSRF policy phù hợp.
- Saved request trong browser chain có thể có ích để đưa user về trang ban đầu, nhưng không phải bắt buộc cho mọi thiết kế OIDC.
- Các chain là **phương án thay thế** cho chain toàn cục ở phần 5; không nên copy tất cả các bean SecurityFilterChain minh họa vào cùng dự án.

### 7.3. Tại sao không phân nhánh chỉ bằng `Accept`?

Máy gọi có thể gửi:

~~~http
Accept: */*
~~~

Browser JavaScript cũng có thể gửi:

~~~http
Accept: application/json
~~~

Và một browser tab có thể tải trực tiếp một API JSON. Header `Accept` nói về **representation được mong muốn**, không phải bằng chứng client có phải browser, được phép login, hay đã sở hữu session. Phân loại chính sách bảo mật nên dựa trên **phạm vi endpoint/chain và hợp đồng client**, không chỉ user agent hoặc content negotiation.

### 7.4. Tách subdomain/port có lợi ích gì?

Một hệ thống có thể tách:

~~~text
https://app.example.test         → OIDC browser client/session
https://api.example.test         → Bearer Resource Server
~~~

Điều này làm rõ trust boundary và cookie scope, nhưng không tự bảo đảm an toàn. DNS, TLS, CORS, cookie domain/path, gateway routing và fallback chain vẫn phải được thiết kế đúng. Nếu cùng deployment, kiểm tra security matcher nhìn thấy path/host thực tế sau reverse proxy.

### 7.5. BFF và máy gọi API là hai kiến trúc khác nhau

**Backend for Frontend (BFF)** phục vụ browser có thể giữ access token **server-side**, trao đổi với browser qua session cookie được bảo vệ và gọi backend Resource Server bằng Bearer token. BFF có thể cần login redirect, request cache, cookies, CSRF, logout.

**Backend Resource Server** phía sau BFF chỉ thấy token từ BFF và thường không cần redirect/login. Trộn role của BFF và backend API có thể khiến một lớp vô tình giữ session hoặc trả HTML sai hợp đồng.

Nếu ứng dụng vừa là BFF vừa là API, hãy phân định rõ **request nào có credential tự gửi qua cookie** và request nào được bảo vệ bằng Bearer header, để áp CSRF, session và entry point đúng phạm vi.

## 8. HTTP response chính xác cho máy gọi

Một API client không chỉ quan tâm có nội dung JSON hay không. Nó cần **HTTP status đúng**, Bearer challenge theo chuẩn, response body ổn định và không bị redirect bất ngờ.

### 8.1. Những trường hợp cần phân biệt

| Request | Kết quả authentication | Kết quả authorization | Response thường gặp |
|---|---|---|---|
| Thiếu Bearer token, endpoint protected | Chưa xác thực | Chưa có principal phù hợp | 401 + `WWW-Authenticate: Bearer` |
| Bearer JWT sai chữ ký | Thất bại | Không xét như principal hợp lệ | 401, thường `invalid_token` |
| Bearer JWT hết hạn | Thất bại | Không xét như principal hợp lệ | 401, thường `invalid_token` |
| Opaque token introspection `active=false` | Thất bại | Không xét như principal hợp lệ | 401, thường `invalid_token` |
| Bearer token hợp lệ nhưng thiếu scope | Thành công | Không đạt HTTP rule | 403, có thể `insufficient_scope` |
| Bearer token hợp lệ, đủ scope | Thành công | Đạt HTTP rule | Chuyển tới controller/service |
| Bearer token hợp lệ nhưng không sở hữu bản ghi | Thành công | HTTP rule đạt, domain policy không đạt | 403 hoặc 404 theo hợp đồng |
| Public endpoint, không gửi token | Không yêu cầu auth | `permitAll()` | Response public bình thường |
| Public endpoint, gửi token sai vào chain Bearer | Bearer filter có thể từ chối token sai | Chưa tới `permitAll` | Có thể 401, không bảo đảm 200 |
| Introspection endpoint timeout | Không có kết quả xác minh đáng tin | Không được tạo principal | Lỗi auth/service theo policy; **không 302 login** |

**Từ chối một request** không luôn đồng nghĩa lỗi 401: 401 thường liên quan nhu cầu authentication, còn 403 liên quan quyền truy cập sau authentication. `ExceptionTranslationFilter`, entry point và access-denied handler có thể quyết định status khác theo ngữ cảnh.

### 8.2. `WWW-Authenticate` là một phần hợp đồng Bearer

Theo RFC 6750, Resource Server dùng HTTP `WWW-Authenticate` challenge để truyền yêu cầu Bearer authentication. Các ví dụ:

Thiếu credential:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Credential sai:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Credential hợp lệ nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Một số response có thể có `realm`, `error_description` hoặc `scope` khi phù hợp, nhưng không bắt buộc mọi response đều có tất cả các tham số. **Không đưa token value, raw JWT claims, secret hoặc stacktrace** vào error description.

### 8.3. Không biến lỗi xác thực thành HTTP 200

Một phản ví dụ khác với redirect:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": false,
  "error": "NOT_AUTHENTICATED"
}
~~~

Đây là response **sai tầng HTTP** cho một API chuẩn có contract status codes. API gateway, monitor và HTTP clients sẽ thấy 200 và có thể coi request thành công. Khi authentication thất bại, nên giữ 401; khi thiếu quyền sau authentication, nên giữ 403.

### 8.4. Tránh rò rỉ nguyên nhân nội bộ trong JSON lỗi

Đừng trả:

~~~json
{
  "error": "JWT verification failed using https://internal-jwks...",
  "authorization": "Bearer <RAW_TOKEN>",
  "stackTrace": "...",
  "introspectionClientSecret": "..."
}
~~~

Một DTO lỗi an toàn:

~~~java
public record ApiError(
    String code,
    String message,
    String requestId
) {}
~~~

Ví dụ JSON khi authentication không hoàn tất:

~~~json
{
  "code": "UNAUTHENTICATED",
  "message": "An access token is required or invalid.",
  "requestId": "36d58f3e-d3b9-4c4c-9767-8b2c88f55375"
}
~~~

Một request ID được hệ thống tạo giúp correlation mà không cần đưa raw token vào logs. Nếu tùy biến JSON body, **phải giữ HTTP status và Bearer challenge**; tránh handler kiểu “có body JSON nhưng vô tình bỏ `WWW-Authenticate`” hoặc trả status 200.

### 8.5. `Cache-Control` và API cá nhân hóa

Với response mang identity hoặc dữ liệu riêng tư, có thể áp:

~~~http
Cache-Control: private, no-store
~~~

Đây là chính sách **HTTP response cache**, không phải request cache. Nó không loại bỏ saved request trong session. Ngược lại, `NullRequestCache` không tự viết `Cache-Control` phù hợp cho response nghiệp vụ.

Không bắt buộc mọi response public phải `no-store`; hãy đánh giá theo độ nhạy cảm, CDN, proxy, ETag và contract API. Nhưng phản hồi lỗi chứa chi tiết xác thực hoặc dữ liệu cá nhân không nên bị cache/hiển thị ngoài phạm vi thiết kế.

## 9. Tùy biến JSON error mà không phá Bearer challenge

Nhiều API yêu cầu body JSON cố định như:

~~~json
{
  "code": "TOKEN_INVALID",
  "message": "Authentication failed."
}
~~~

Nhu cầu đó hợp lý, nhưng chỉ thay `AuthenticationEntryPoint` thành handler trả JSON có thể làm mất thông tin giao thức. Một thiết kế an toàn cần:

1. Giữ **status 401** đối với lỗi authentication.
2. Giữ `WWW-Authenticate: Bearer` với parameters được framework cung cấp khi phù hợp.
3. Chỉ viết body với field được allowlist.
4. Không tự echo exception message chưa kiểm soát.
5. Với lỗi đã commit response, không cố ghi body thêm.
6. Giữ riêng xử lý **403 access denied**.

### 9.1. Dùng entry point Bearer có sẵn là cách đơn giản nhất

Nếu API không bắt buộc custom JSON body, có thể để Spring Security xử lý:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(withDefaults())
);
~~~

Trong trường hợp nhiều authentication mechanisms/exception handlers, có thể cấu hình tường minh `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` ở `exceptionHandling` như mục 5.5.

### 9.2. Handler tùy chỉnh cần hiểu response đã commit chưa

Một strategy là **ủy quyền cho handler Bearer mặc định để thiết lập status/challenge trước**, sau đó chỉ ghi một body JSON ngắn nếu response chưa commit. Tuy nhiên, implementation cụ thể phải phù hợp lifecycle Servlet và exception handling của Spring Security.

Pseudo-code:

~~~text
on AuthenticationException:
  call BearerTokenAuthenticationEntryPoint
  if response is not committed:
      set Content-Type application/json
      write public ApiError with fixed code/message
  do not redirect
~~~

Không tự tạo header bằng cách nối chuỗi không escaped từ exception, token hoặc `scope` tùy ý. Cũng không catch mọi runtime exception rồi trả 401: một database outage hoặc bug JSON serialization là lỗi server, không phải bằng chứng token invalid.

### 9.3. `@RestControllerAdvice` không thay thế filter entry point

Một `@RestControllerAdvice` xử lý exception từ MVC controllers nhưng authentication failure có thể xảy ra **trong Spring Security filter chain trước khi vào DispatcherServlet**. Vì vậy:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {
    // ... handlers cho lỗi nghiệp vụ từ controller
}
~~~

không đảm bảo bắt được mọi `AuthenticationException`/`AccessDeniedException` từ filter. Cần tùy biến đúng security boundary qua `AuthenticationEntryPoint` và `AccessDeniedHandler` khi muốn kiểm soát lỗi authentication/authorization của Resource Server.

### 9.4. Khi lỗi upstream introspection xảy ra

Với opaque token, timeout/503 từ introspection là tình huống **không thể xác minh**. Không được tạo principal “tạm” hoặc redirect người dùng tới login. Hệ thống có thể áp policy 503 cho lỗi service nếu được thiết kế và exception mapping phù hợp; các lỗi `active=false` vẫn là token invalid.

Điều quan trọng:

~~~text
Introspection result active=false → invalid token
Introspection unavailable          → unknown token status, fail closed
JWT signature invalid              → invalid token
Bearer valid but no authority      → authenticated, forbidden
~~~

Một handler chung gộp mọi tình huống vào 302 login hoặc 200 HTML sẽ làm mất phân biệt giữa authentication, authorization và availability.

## 10. CSRF, CORS và request cache không thay thế lẫn nhau

Ba cơ chế có tên gần nhau trong cấu hình web nhưng bảo vệ những vấn đề khác nhau.

| Cơ chế | Bài toán | Liên quan redirect/login? |
|---|---|---|
| **RequestCache** | Giữ saved request cho browser login | Có, liên quan navigation/redirect |
| **CSRF protection** | Chống yêu cầu thay đổi trạng thái lợi dụng credential được browser tự gửi | Liên quan browser cookies/session |
| **CORS** | Quy định origin browser nào có thể đọc response cross-origin và gửi request dạng nhất định | Liên quan browser network policy, không phải token validation |
| **Bearer authentication** | Xác minh access token của caller | Không cần redirect login tương tác |
| **HTTP response cache** | Cho phép/ngăn lưu response ở browser/proxy/CDN | Độc lập saved request |

### 10.1. CORS preflight không mang Bearer token như request thật

Browser JavaScript muốn gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

có thể gửi preflight trước:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thông thường **không mang Bearer token**, nên cần được CORS processor xử lý phù hợp trước khi bị security authentication từ chối như một request API bình thường.

Trong Servlet:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

http.cors(withDefaults());
~~~

Và một nguồn CORS:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type")
    );

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Ví dụ này chỉ là policy minh họa; origin/method/header thực tế phải theo hợp đồng client. Không mở `allowedOrigins("*")` với credential-bearing browser requests mà không đánh giá browser CORS semantics và rủi ro.

### 10.2. `OPTIONS /** → permitAll` không đủ thay CORS

Một rule:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

không tự tạo các `Access-Control-Allow-*` headers phù hợp. Nó cũng cho phép cả những OPTIONS requests không phải preflight ở tầng authorization. Nên ưu tiên **CORS config chính xác** thay vì mở toàn bộ OPTIONS để tránh lỗi trình duyệt.

### 10.3. `permitAll` không có nghĩa bỏ qua xác thực Bearer token sai

Một endpoint public được cho phép:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

không có nghĩa một client gửi `Authorization: Bearer invalid-token` tới endpoint đó chắc chắn được trả 200. Nếu Bearer authentication filter cố xác thực header rồi phát hiện token sai, nó có thể từ chối request trước khi `permitAll` được áp. Muốn tách public khỏi Bearer authentication phải thiết kế chain/filter rõ, không chỉ đổi rule authorization.

### 10.4. CSRF có thể gây 403 ngay cả với token hợp lệ

Nếu một ứng dụng vẫn bật CSRF protection trên POST, request:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN>
Content-Type: application/json

{"productId":"sku-123"}
~~~

có thể bị `403 Forbidden` vì thiếu CSRF token, ngay cả khi JWT hợp lệ và có `SCOPE_orders.create`. Điều đó **không nhất thiết do thiếu scope**. Nếu đây là pure header-based Bearer API, cân nhắc CSRF policy theo threat model; nếu browser session/cookie auth hiện diện, giữ cơ chế bảo vệ tương ứng.

### 10.5. Security headers vẫn quan trọng

Một API không dùng session/redirect login vẫn có thể hưởng lợi từ các security headers do Spring Security hỗ trợ, như chống cache dữ liệu nhạy cảm, ngăn một số loại sniffing, HSTS trên HTTPS và các headers khác tùy sản phẩm.

Không nên dùng `web.ignoring()` cho toàn bộ API chỉ vì muốn bỏ request cache hoặc form login: cách đó có thể bỏ qua các Spring Security filters bảo vệ khác. Thay vào đó, cấu hình security chain với Bearer authentication và `NullRequestCache`.

## 11. WebFlux: không dùng web session request cache cho pure Bearer API

Trong Spring WebFlux, các thành phần được đặt tên khác Servlet:

| Nhiệm vụ | Servlet | WebFlux |
|---|---|---|
| HTTP security | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Saved request cache có state | `HttpSessionRequestCache` | `WebSessionServerRequestCache` |
| Request cache không lưu | `NullRequestCache` | `NoOpServerRequestCache` |
| Security context không lưu giữa requests | `NullSecurityContextRepository` / stateless policy | `NoOpServerSecurityContextRepository` |
| Resource Server JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque token introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Authorization | `authorizeHttpRequests` | `authorizeExchange` |
| Rule mặc định | `anyRequest()` | `anyExchange()` |

WebFlux dùng reactive `WebSession` thay cho Servlet `HttpSession`, nhưng vẫn có khả năng phát sinh cookie/session và redirect khi browser login được kích hoạt. Chuyển từ Spring MVC sang WebFlux **không tự động biến mọi ứng dụng thành stateless**.

### 11.1. Reactive Resource Server không lưu saved request

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .requestCache(cache -> cache
                .requestCache(NoOpServerRequestCache.getInstance()))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/status")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Đây là **phương án WebFlux thay thế** cho Servlet, không phải một bean cài cùng application stack một cách tùy tiện. Nó thể hiện:

- `NoOpServerRequestCache` để không lưu request phục vụ login redirect.
- `NoOpServerSecurityContextRepository` để không persist security context thành web session qua repository này.
- Form login và HTTP Basic không hoạt động ở chain API theo cấu hình.
- JWT Resource Server xác minh Bearer token.
- CSRF disable chỉ trong giả định API thuần header-based Bearer, không dùng cookie-based auth.

Nếu dùng `oauth2Login()` ở một reactive browser chain khác, cần một policy session/CSRF/login thích hợp; không dùng `NoOpServerRequestCache` ở mọi chain mà không cân nhắc mục đích login.

### 11.2. Reactive opaque token

Nếu API xác thực qua introspection:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(withDefaults()))
~~~

Phần request cache và session repository vẫn có thể giữ nguyên chính sách API. Trong WebFlux, introspection được thực hiện qua `ReactiveOpaqueTokenIntrospector`. Đừng dùng Servlet `OpaqueTokenIntrospector` làm bằng chứng một application reactive đã được cấu hình đúng; hai stacks dùng interface khác nhau.

### 11.3. Không suy ra “không blocking = không session”

Reactor không tự loại bỏ các trạng thái như:

- `WebSession` dùng cho browser authentication.
- Cookies do service/gateway tạo.
- Request cache dành cho login interactive.
- OAuth2 Authorization Request/State repository.
- Backend session store cho BFF.

Phải xác định chính sách **theo request path và client contract**. Một ứng dụng reactive vẫn có thể là web application dùng session đúng thiết kế, trong khi một API machine-to-machine cần không dùng session.

### 11.4. Reactive entry point và WebFlux security chain

Spring Security Reactive Resource Server có các handler/entry point cho Bearer authentication, phân biệt 401/403 theo Bearer semantics. Nếu tự cấu hình `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler` để trả body JSON:

1. Không trả 302 login cho API.
2. Không bỏ Bearer challenge khi phải có.
3. Không viết response body nhạy cảm.
4. Không trả authenticated principal khi token invalid/introspection unavailable.
5. Không dùng blocking operation khi xử lý error trên event loop.

Lỗi xảy ra trong `WebFilter` security chain cũng không tự được giải quyết chỉ bằng `@RestControllerAdvice` vốn phục vụ tầng controller.

## 12. Client thực tế: cURL, backend service, mobile và browser

### 12.1. cURL gọi API machine-to-machine

Với token giả lập:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  https://orders-api.example.test/api/orders/42
~~~

Điểm cần quan sát:

- Token đúng, đủ scope → response nghiệp vụ theo hợp đồng.
- Không token → 401 Bearer challenge.
- Token sai → 401 invalid_token.
- Token đủ auth nhưng thiếu scope → 403.
- Không nhận 302 login trong những lỗi authentication nói trên.

Trong shell thật, **đừng lưu token production trong history, ticket hoặc logs**. Chọn cơ chế bảo vệ credential phù hợp. Mẫu dùng placeholder không phải câu lệnh mang token có thể chạy trực tiếp.

### 12.2. Tránh bật tự theo redirect khi chẩn đoán

Để nhìn rõ 302 gốc:

~~~bash
curl -i https://orders-api.example.test/api/orders/42
~~~

Không thêm `-L` khi mục đích là xác định API có trả redirect không, vì `-L` khiến cURL theo redirect và có thể chỉ cho thấy response cuối. Với HTTP client khác cũng cần phân biệt **response ban đầu** và **response sau redirect chain**.

Nếu một test chỉ assert “cuối cùng nhận HTTP 200” trong khi HTTP client tự theo 302 đến trang login, nó không kiểm tra đúng hợp đồng Resource Server.

### 12.3. Backend `RestClient` hoặc `WebClient`

Một backend gọi Orders API thường:

~~~text
1. Lấy access token từ OAuth 2.0 client credentials/token management hợp lệ.
2. Gọi API với Authorization: Bearer <token>.
3. 401 → xử lý token invalid/expired theo policy, không mở browser login.
4. 403 → thiếu permission; không tự cấp thêm scope.
5. 503 → lỗi service/upstream authentication nếu được phân loại, retry có giới hạn theo contract.
~~~

Đối với 302 không mong muốn, HTTP client nên có policy redirect rõ ràng: không tự chuyển tiếp Bearer credential đến origin ngoài trust boundary và không coi HTML login response là JSON thành công. Tốt nhất là **Resource Server trả 401/403 đúng ngay từ đầu**, thay vì buộc mọi clients tự vá lỗi của server.

### 12.4. Mobile/desktop client

Mobile app có thể hỗ trợ **system-browser OAuth 2.0 Authorization Code + PKCE** để người dùng đăng nhập và nhận token. Nhưng đó là trách nhiệm của **OAuth2 client trong app**, không phải Resource Server tự trả 302 đến form login khi nhận Bearer invalid.

Mobile client cần phân biệt:

~~~text
Login/token acquisition flow  ≠  protected resource request
~~~

Một 401 từ protected resource có thể kích hoạt client token management hoặc yêu cầu người dùng đăng nhập lại **qua flow được thiết kế**, không phải tự động follow Location bất kỳ.

### 12.5. API được gọi từ browser JavaScript

Browser có thể là client API, nhưng “gọi từ browser” không tự biến endpoint thành browser-login route. Nếu JavaScript gửi access token qua Authorization header theo kiến trúc đã chọn, API vẫn nên có Bearer response semantics 401/403. Frontend tự quyết định có điều hướng người dùng tới login hay hiển thị lỗi.

Nếu dùng BFF/session cookie thay vì JavaScript giữ token, cần một contract khác: browser ↔ BFF dùng cookie/session và CSRF; BFF ↔ Resource Server dùng Bearer token. Cấu hình không thể sao chép giống nhau cho hai hop.

### 12.6. Proxy/gateway xử lý 401/302 sai

Một gateway có thể cấu hình **auth redirect plugin** hoặc rewrite lỗi 401 thành 302 tới SSO portal. Điều này phù hợp với web UI nhưng gây rủi ro cho API machine clients. Dù Spring Security đã trả Bearer 401, client vẫn có thể nhận 302 **do gateway sửa response**.

Phải xác định rõ:

- Route API nào không dùng interactive SSO redirect.
- Gateway có giữ `WWW-Authenticate` và status 401/403 không.
- Ingress có rewrite `Location` hoặc Set-Cookie không.
- API host/path có được phân biệt khỏi web login host/path không.
- Lỗi authentication do upstream IdP có bị chuyển thành trang HTML “Service Unavailable” với status 200 không.

Một test chỉ gọi localhost không đủ chứng minh production gateway trả đúng response. Cần test từ vị trí network tương tự machine client thật.

## 13. HTTP method, saved request và nguy cơ replay thao tác ghi

Một browser login workflow thường hình thành khi user cố vào một trang **GET** được bảo vệ; sau login, browser quay lại trang đó để tải nội dung. Nhưng API có thể dùng:

~~~http
POST /api/payments/transfer
PUT /api/orders/42
DELETE /api/orders/42
~~~

Không nên coi saved request + 302 là cơ chế retry/replay bảo đảm đúng cho những thao tác này.

### 13.1. Không bảo đảm body POST được giữ nguyên

`HttpSessionRequestCache` lưu thông tin request phục vụ khôi phục navigation, không nên được xem là **hàng đợi transactional HTTP requests**. Nếu client POST JSON, có thể xảy ra:

~~~text
POST /api/orders    → redirect login
GET /login          → login
GET /api/orders     → không có JSON body POST ban đầu
~~~

Ngay cả khi một loại redirect hoặc HTTP client giữ method/body, việc tự replay side effects có thể tạo giao dịch trùng nếu hệ thống không có idempotency semantics riêng.

### 13.2. Idempotency là bài toán độc lập

Đối với các endpoint thanh toán/đặt hàng, nếu client cần retry HTTP request sau timeout, API có thể dùng **idempotency key** hoặc cơ chế xác định danh tính transaction, tùy contract. Điều đó **không liên quan** đến việc lưu saved request cho browser login.

Giữ rõ:

~~~text
Bearer authentication:
  Token có hợp lệ và được quyền gọi API không?

RequestCache:
  Sau interactive login browser sẽ quay về URL nào?

Idempotency:
  Nếu request mutation được gọi lại, có tạo side effect trùng không?
~~~

Tách ba câu hỏi này giúp tránh việc “dùng redirect login để xử lý token hết hạn cho POST” và vô tình làm thay đổi thao tác nghiệp vụ.

### 13.3. Redirect với Bearer credentials có thể làm sai trust boundary

Nếu HTTP client tự forward Bearer header sang redirect target khác domain, credential có thể rò rỉ. Không đưa response `Location` chưa kiểm soát làm nơi gửi access token. API server cũng không nên dựa vào việc client giữ Bearer header khi follow redirect để tiếp tục authentication.

Đối với machine clients, phương án đúng nhất là một **response xác thực rõ ràng (401/403)** và chính sách token acquisition/retry nằm ở client theo hợp đồng.

## 14. Kiểm thử API không trả login redirect

Một bài test `authorizeHttpRequests` chỉ kiểm tra scope là chưa đủ. Cần chứng minh **không token, token sai hoặc thiếu scope không làm API chuyển sang browser login**.

### 14.1. Thêm Spring Security Test

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ Spring MVC:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiWithoutRedirectTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingBearerTokenReturns401WithoutLoginRedirect()
            throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", containsString("Bearer")))
            .andExpect(header().doesNotExist("Location"));
    }
}
~~~

Đoạn test giả định application context có security chain Bearer cho `/api/orders/**` và có cấu hình decoder/introspector phù hợp để khởi động. **Không cần controller tồn tại** để một request chưa xác thực bị chặn ở security filter; nếu endpoint được `permitAll` thì test phải chọn endpoint protected khác.

### 14.2. Kiểm tra principal hợp lệ nhưng thiếu scope

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void missingScopeReturns403WithoutLoginRedirect() throws Exception {
    mvc.perform(
            get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile")
                ))
        )
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist("Location"));
}
~~~

Đây là **method test minh họa**, đặt trong class có `MockMvc mvc` và các import phù hợp như ở ví dụ trước. `jwt()` từ Spring Security Test dựng một authentication giả lập và **bỏ qua JWT cryptographic verification thực**. Nó hữu ích để kiểm tra HTTP authorization, không chứng minh decoder đã xác minh issuer/audience/signature.

Nếu SecurityFilterChain của API dùng opaque token, có thể dùng `opaqueToken()` test helper tương ứng để mô phỏng principal/authorities, còn test introspection thực phải làm riêng.

### 14.3. Kiểm tra không có saved session trong pure API

Một test bổ sung:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void missingBearerDoesNotCreateHttpSession() throws Exception {
    var result = mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andReturn();

    assertThat(result.getRequest().getSession(false)).isNull();
}
~~~

Đây là kiểm tra phù hợp với **mục tiêu pure stateless API**. Nó có thể thất bại nếu một filter/controller/library khác cố ý tạo HTTP session; khi đó phải xác định thành phần tạo session, không chỉ kết luận `STATELESS` của Spring Security “không hoạt động”.

Không nên đánh giá một browser chain bằng test “session phải null”; browser login có thể cần session để quản lý login/authorization request theo thiết kế.

### 14.4. Kiểm tra không có `Set-Cookie` ngoài ý muốn

~~~java
@Test
void missingBearerDoesNotIssueSessionCookie() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().doesNotExist("Set-Cookie"));
}
~~~

Mục tiêu là phát hiện một API được định nghĩa **không dùng cookie/session** bỗng tạo cookie. Nếu sản phẩm cố ý phát hành một cookie khác không liên quan authentication, test nên kiểm tra cụ thể `JSESSIONID` hoặc session cookie policy thay vì cấm mọi cookie vô điều kiện.

### 14.5. Một test chỉ nhìn 302 là chưa đủ

Một test hữu ích kiểm tra:

~~~text
Request:
  GET /api/orders/42
  Accept: application/json
  Authorization: missing

Expected:
  status = 401
  WWW-Authenticate begins with Bearer
  no Location: /login
  no HTML login body
  no saved request in HttpSession
~~~

Nếu HTTP client tự follow redirects, phải cấu hình **không follow** khi kiểm tra response gốc. Trường hợp production còn gateway/ingress cần test qua cả gateway vì gateway có thể tự rewrite 401 thành 302.

### 14.6. Test WebFlux bằng `WebTestClient`

Với Spring WebFlux, ví dụ test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveApiWithoutRedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void missingBearerReturns401Not302() {
        client.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                "WWW-Authenticate", "^Bearer.*")
            .expectHeader().doesNotExist("Location");
    }
}
~~~

Đây là mẫu test dùng application context WebFlux có Resource Server configuration/decoder phù hợp. Khi chạy qua `WebTestClient` trên server thật, không nên tự cho client follow redirect trong trường hợp cần kiểm tra 302 gốc.

### 14.7. Với token sai, cần test decoder thật

Mock `jwt()` giúp kiểm tra HTTP scope policy, nhưng để chứng minh Bearer filter trả 401 cho token sai:

1. Dùng JWT test-only với chữ ký thật bằng test private key, cấu hình decoder tin đúng test public key.
2. Gửi token qua header `Authorization: Bearer ...` thay vì post processor mock.
3. Thử token sai chữ ký, hết hạn, sai issuer/audience.
4. Kiểm tra 401 + challenge phù hợp; không redirect.
5. Không dùng production signing keys hoặc access token thật trong test fixture/CI.

Với opaque token, dùng introspection stub/Authorization Server test environment cho `active=true/false` và lỗi kết nối, đồng thời kiểm tra không redirect.

## 15. Ma trận kiểm thử đầy đủ cho API máy gọi

| Bối cảnh | Request | Kỳ vọng theo hợp đồng API |
|---|---|---|
| Không gửi token | GET protected URL | 401 Bearer, không 302 |
| Header Bearer rỗng/sai format | GET protected URL | Từ chối authentication, không HTML login |
| JWT sai chữ ký | GET protected URL | 401 invalid_token, không 302 |
| JWT hết hạn | GET protected URL | 401, không lưu saved request |
| JWT đúng, thiếu scope | GET protected URL | 403, không redirect |
| JWT đúng, đủ scope | GET protected URL | Controller/service, không cần session |
| Opaque token `active=false` | GET protected URL | 401, không redirect |
| Introspection timeout | GET protected URL | Không xác thực; lỗi theo policy, không 302 |
| Public URL không token | GET `/api/public/status` | 200 nếu endpoint được triển khai, không yêu cầu login |
| Public URL gửi token sai | GET `/api/public/status` | Bearer filter có thể trả 401; test theo chain cụ thể |
| CORS preflight hợp lệ | OPTIONS API cross-origin | CORS headers phù hợp, không bị login redirect |
| POST protected thiếu token | POST API | 401 khi CSRF policy phù hợp, không replay sau login |
| POST có token hợp lệ nhưng thiếu scope | POST API | 403, không tự login |
| URL ngoài API chain | GET `/internal/secret` | Fallback chain bảo vệ, không unprotected |
| Browser web URL chưa login | GET `/web/dashboard` | Có thể 302 login theo browser contract |
| Browser callback OAuth2 login | GET `/login/oauth2/code/...` | Được browser chain xử lý, không bị API Bearer chain chặn |
| API qua gateway | GET protected URL | Giữ 401/403, không bị rewrite thành SSO redirect |
| API yêu cầu response JSON | GET protected URL sai token | Không trả HTML `/login` với status 200 |
| Kết thúc request không xác thực | GET protected URL | Không tạo HTTP session nếu yêu cầu pure stateless |

Không có cách suy ra tất cả những kỳ vọng trên chỉ từ một dòng `sessionCreationPolicy(STATELESS)`. Cần kiểm tra **endpoint matcher, filter chain, entry point, request cache, gateway behavior và HTTP clients**.

## 16. Các lỗi cấu hình thường gặp và cách chẩn đoán

### 16.1. Nhận 302 tới `/login` thay vì 401

Nguyên nhân có thể:

- `formLogin()` được bật trong security chain xử lý URL API.
- `LoginUrlAuthenticationEntryPoint` được đăng ký cho matcher quá rộng.
- Một chain form login không giới hạn `securityMatcher` đứng trước chain Resource Server.
- Gateway/SSO middleware rewrite 401 thành 302.
- Custom entry point tự gọi `sendRedirect(...)`.

Hướng xử lý:

1. Xác định **chain nào được chọn cho request API**.
2. Kiểm tra form/OAuth2 login và exception handling của chain đó.
3. Đặt chain Bearer API cụ thể trước chain browser theo `@Order` khi dùng nhiều chains.
4. Đặt `NullRequestCache` và Bearer entry point trong chain API.
5. Kiểm tra response trước và sau gateway để xác định chỗ phát sinh 302.

**Không** sửa bằng cách đổi mọi URL thành `permitAll()`, vì đó là bỏ authorization chứ không phải sửa entry point.

### 16.2. Nhận HTTP 200 nhưng body là HTML login

Nguyên nhân thường là HTTP client đã **follow 302** và response cuối từ trang login là 200. Đừng chỉ debug controller API; kiểm tra redirect chain:

~~~text
API request → 302 /login
GET /login → 200 text/html
~~~

Tắt auto-follow redirects trong công cụ test hoặc bật khả năng xem toàn bộ response history, rồi sửa server/gateway để API trả Bearer 401/403.

### 16.3. `JSESSIONID` xuất hiện dù đã đặt `STATELESS`

Kiểm tra:

- Có browser login/CSRF filter nào thuộc chain đó không?
- `RequestCache` có còn dùng HTTP session ở chain nào không?
- Controller/view engine/service có tạo session không?
- Spring Session hoặc một middleware có phát cookie không?
- Reverse proxy có thêm cookie/session riêng không?

`STATELESS` là chính sách persistence của Spring Security, **không phải một tính năng cấm Servlet session trên toàn JVM**. Nếu pure API yêu cầu không session, cần xác định component gây ra session.

### 16.4. Thay `NullRequestCache` nhưng API vẫn redirect

`NullRequestCache` chỉ ngăn saved request. Nếu `formLogin()` hoặc `oauth2Login()` vẫn kích hoạt cho API, authentication entry point vẫn có thể trả **302 tới login**. Cần cả **đúng entry point/login mechanism** lẫn request cache policy.

~~~text
NullRequestCache:
    Không lưu saved request

BearerTokenAuthenticationEntryPoint:
    Dùng 401 Bearer challenge

Không thể thay cái thứ hai bằng cái thứ nhất.
~~~

### 16.5. Tắt `formLogin` rồi API vẫn trả `WWW-Authenticate: Basic`

Có thể `httpBasic()` vẫn được bật hoặc một security chain khác đã chọn. Kiểm tra Basic mechanism và phạm vi chain. Với API Bearer, nên trả Bearer challenge phù hợp, không để browser tự bật Basic credential prompt không mong muốn.

### 16.6. Lỗi 403 trên POST dù Bearer token có scope

Một số nguyên nhân:

- CSRF protection đang yêu cầu CSRF token.
- Token đủ authentication nhưng thiếu authority đúng method.
- HTTP matcher không khớp path/method do thứ tự rule.
- Business authorization từ chối owner/tenant.

Không nên xem mọi 403 là lỗi CSRF rồi tắt CSRF toàn ứng dụng. Phải xác định **tầng nào từ chối**. Nếu ứng dụng có cookie/session auth, tắt CSRF có thể mở lỗ hổng nghiêm trọng.

### 16.7. Không token trên URL public vẫn bị 401

Kiểm tra `permitAll()` có đúng path/method không, security matcher có khớp không, một chain khác có đứng trước không, hoặc gateway có yêu cầu auth riêng không. Nếu request public **gửi token invalid**, Bearer filter vẫn có thể trả 401; đó là tình huống khác với request không mang credential.

### 16.8. Có `anyRequest().denyAll()` nhưng một URL vẫn không được bảo vệ

Nếu URL không khớp **bất kỳ `SecurityFilterChain` nào**, catch-all trong chain API không áp dụng. Cần một fallback chain hoặc cơ chế bảo vệ được thiết kế. Phân biệt rõ:

~~~text
securityMatcher("/api/**")   → chọn chain cho /api/**
anyRequest().denyAll()       → catch-all trong chain đã chọn
~~~

`anyRequest()` không phải “toàn bộ mạng/ứng dụng” khi chỉ một chain có matcher giới hạn.

### 16.9. OAuth2 Login callback bị chặn bởi Bearer chain

Nếu chain API có matcher quá rộng như `/**` và đứng trước browser chain, nó có thể bắt các route `/oauth2/authorization/**` hoặc `/login/oauth2/code/**` và trả 401 thay vì xử lý callback OIDC. Đặt `securityMatcher` và `@Order` đúng để phân biệt interactive login flow.

### 16.10. Một API dùng đồng thời cookie và Bearer header

Nếu endpoint vừa chấp nhận session cookie vừa chấp nhận Bearer token, câu hỏi **authentication mechanism nào được ưu tiên** và **CSRF policy nào áp dụng** trở nên quan trọng. Không chỉ thêm `STATELESS` rồi giả định cookie không còn có tác dụng. Đôi khi nên tách endpoint/host/chain hoặc chỉ chấp nhận một cơ chế authentication tại API boundary.

### 16.11. Redirect khác origin và Authorization header

Không dựa vào hành vi mặc định của HTTP client để bảo vệ credential khi server trả redirect tới origin khác. Một số clients bỏ header Authorization, một số có policy khác tùy thư viện/version/configuration. Thiết kế đúng là API **không redirect login** và client không tự chuyển tiếp token đến origin ngoài allowlist.

### 16.12. 404/405 sau authentication bị nhầm với lỗi Bearer

Nếu token đã xác thực đúng và Spring MVC/WebFlux không tìm được route/method, ứng dụng có thể trả 404 hoặc 405. Đừng sửa bằng cách bật form login hoặc đổi request cache; xác định trước authentication/authorization đã thành công hay chưa, sau đó kiểm tra controller mapping. Khi thiết kế rule `anyRequest().denyAll()`, URL chưa phân loại còn có thể nhận 403 trước khi vào controller.

### 16.13. `Accept: text/html` khiến API redirect dù token thiếu

Nếu một ứng dụng dùng nhiều entry points dựa trên content negotiation, Accept header có thể ảnh hưởng lựa chọn. Nhưng API máy gọi vẫn cần **contract Bearer theo phạm vi endpoint**, không được cấp policy login khác chỉ vì client gửi Accept lạ. Nên cấu hình chain riêng hoặc matcher được thiết kế cho API thay vì chỉ kiểm tra Accept.

### 16.14. Tắt request cache nhưng vẫn có `SavedRequestAwareAuthenticationSuccessHandler`

Một handler dành cho browser login có thể còn được gắn trong chain, nhưng khi request cache không lưu gì, nó có thể dùng default target URL hoặc fallback khác. Nếu API không có login interactive, **không cần success handler browser**. Hãy giữ saved request/success handler trong browser chain, tránh mang sang Resource Server.

### 16.15. Tắt `RequestCacheAwareFilter` bằng cách bỏ toàn bộ Spring Security

Không nên dùng `web.ignoring("/api/**")` hoặc bỏ security filter chain để tránh lưu saved request. Làm vậy có thể vô hiệu cả token authentication, authorization, headers và cơ chế bảo vệ khác. Dùng `NullRequestCache` là cách **chuyên biệt** hơn.

## 17. Quy trình chẩn đoán 302 từ API

Khi máy gọi báo “API trả trang đăng nhập”, có thể dùng sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Machine client nhận HTML/302"] --> B{"Response ban đầu có 302?"}
    B -->|Không| C["Xem gateway rewrite, content type, custom error handler"]
    B -->|Có| D{"Location trỏ đến đâu?"}
    D -->|"/login"| E["Form login / LoginUrlAuthenticationEntryPoint / gateway"]
    D -->|"IdP authorization endpoint"| F["OAuth2 Login / SSO middleware"]
    D -->|"Other host"| G["Custom redirect / gateway / proxy"]
    E --> H["Xác định SecurityFilterChain đã chọn"]
    F --> H
    G --> H
    H --> I{"API chain có Bearer entry point và NullRequestCache?"}
    I -->|Không| J["Cấu hình riêng API chain, không dùng interactive login"]
    I -->|Có| K["Kiểm tra custom filters/exception handling và upstream"]
    J --> L["Kiểm thử 401/403 không Location, không session"]
    K --> L
~~~

### 17.1. Bước 1: quan sát raw response

Gọi request protected **không Bearer token** và **không follow redirect**, ghi lại:

~~~text
HTTP status
WWW-Authenticate
Location
Content-Type
Set-Cookie
Cache-Control
~~~

Không ghi raw token vào ticket/log. Nếu muốn test với credential sai, dùng token giả lập từ test issuer hoặc giá trị invalid không thể dùng thật.

### 17.2. Bước 2: xác định nơi phát sinh redirect

Nếu gọi trực tiếp ứng dụng trả 401 nhưng qua gateway trả 302, lỗi nằm ở gateway/SSO middleware. Nếu ứng dụng đã trả 302 trước gateway, kiểm tra Spring Security chains, entry point và login mechanism.

### 17.3. Bước 3: xác định chain được chọn

Với nhiều chains:

~~~text
@Order(1) /api/**  → Bearer API
@Order(2) /web/**  → Browser login
@Order(3) fallback
~~~

Kiểm tra request path thực tế tại servlet sau reverse proxy, context path và servlet path, không chỉ URL công khai ở gateway. Một matcher API sai có thể khiến request rơi vào browser fallback.

### 17.4. Bước 4: kiểm tra RequestCache và session

API chain cần `NullRequestCache` nếu không có saved-request workflow. `STATELESS` thể hiện chủ đích không persist security context qua HTTP session. Nếu vẫn xuất hiện session, tìm filter/library tạo session; không suy ra nguyên nhân chỉ từ status 302.

### 17.5. Bước 5: kiểm tra lại các trường hợp 401/403 và POST

Sau khi cấu hình:

- GET protected không token → 401 Bearer.
- GET protected token sai → 401, không redirect.
- GET protected thiếu scope → 403.
- POST protected không token → lỗi xác thực phù hợp, không login/replay.
- Browser web route chưa đăng nhập → vẫn có thể redirect theo browser contract.
- Gateway giữ nguyên status/headers của API.

Không kết luận thành công chỉ vì một request có token hợp lệ trả HTTP 200; vấn đề request cache/redirect thường chỉ bộc lộ ở **đường thất bại**.

## 18. Những lựa chọn thiết kế khi API và web không tách được đường dẫn

Một số hệ thống cũ dùng chung URL cho cả browser session và machine client:

~~~text
GET /orders/{id}

Browser:
  cookie session → HTML page

Machine:
  Authorization Bearer → JSON representation
~~~

Kiến trúc này có thể vận hành, nhưng yêu cầu phân biệt cơ chế bảo mật **có chủ đích**, không chỉ dựa vào việc request có `Accept: application/json`.

### 18.1. Có thể dùng nhiều `AuthenticationEntryPoint` theo matcher

Spring Security hỗ trợ exception handling có thể chọn authentication entry point theo `RequestMatcher`. Tuy nhiên, khi API và browser chia sẻ path, các điều kiện chọn entry point cần được định nghĩa rõ:

- Host/subdomain hoặc port.
- Một URL prefix do ứng dụng quản lý.
- Endpoint contract xác định rõ response là API hay trang web.
- Loại security chain và authentication mechanisms được phép.

**Không nên coi User-Agent, Accept header hoặc “không có cookie” là bằng chứng bảo mật**. Những giá trị này do caller điều khiển hoặc không ổn định.

### 18.2. Ưu tiên tách API boundary khi có thể

Một lộ trình refactor:

~~~text
Trước:
  /orders/{id} + session/form login hoặc bearer

Sau:
  /web/orders/{id} → browser login/session
  /api/orders/{id} → Bearer API/stateless
~~~

Cần cập nhật routing, session cookie scope, CORS, CSRF, reverse proxy và clients, nhưng kết quả là security policy dễ đọc và ít cơ hội phát sinh redirect không mong muốn.

### 18.3. Nếu buộc phải dùng cả hai credential types

Hãy viết contract trả lời các câu hỏi:

1. Nếu request đồng thời mang session cookie và Bearer header, **credential nào được ưu tiên**?
2. Nếu Bearer token invalid nhưng cookie hợp lệ, API có được phép fallback sang cookie không?
3. Nếu session login thành công nhưng thiếu Bearer authority, có cho request vào không?
4. CSRF filter áp cho các HTTP methods nào?
5. Header `WWW-Authenticate` có được bảo toàn cho máy gọi không?
6. Có thể phát session cookie từ Bearer request không?
7. Có thể tạo saved request từ Bearer request không?
8. Domain authorization có dùng principal đúng nguồn không?

Một policy thiếu câu trả lời rõ ràng có nguy cơ **credential confusion**: API tin một principal từ cơ chế khác với cơ chế mà client tưởng mình đang sử dụng. Tách security chains hoặc giao diện API thường giúp tránh lỗi này.

### 18.4. Đừng chuyển mọi lỗi về trang login thống nhất

Một hệ thống có trang lỗi SSO chung có thể muốn xử lý mọi 401/403 bằng redirect. Với API machine clients, điều này phá hợp đồng HTTP và có thể làm tăng tải IdP khi client tự follow/retry.

Nên phân biệt:

~~~text
Browser web:
  unauthenticated → interactive login redirect được phê duyệt

Bearer API:
  unauthenticated → 401 Bearer challenge
  authenticated but unauthorized → 403
  upstream auth unavailable → fail closed, lỗi dịch vụ theo policy
~~~

## 19. Những câu hỏi tự kiểm tra

**Câu 1.** `HttpSessionRequestCache` được thiết kế cho vấn đề gì?

Nó giữ một saved request để browser có thể quay lại sau interactive login. Nó **không phải** token cache, không phải API retry queue và không phải HTTP response cache.

**Câu 2.** Tại sao `NullRequestCache` phù hợp cho pure Bearer API?

Vì machine client không cần lưu URL chờ browser login rồi redirect lại. Với `NullRequestCache`, Spring Security không lưu/khôi phục saved request qua thành phần đó.

**Câu 3.** Chỉ đặt `NullRequestCache` có bảo đảm API trả 401 thay vì 302 không?

**Không.** Nếu form login/OAuth2 Login entry point vẫn áp cho API, server có thể redirect dù không lưu request. Cần Bearer entry point và chain policy đúng.

**Câu 4.** Chỉ đặt `SessionCreationPolicy.STATELESS` có ngăn mọi component tạo session không?

**Không.** Nó điều chỉnh cách Spring Security dùng session cho security context, không cấm code ứng dụng, controller, view engine hoặc library khác tạo Servlet session.

**Câu 5.** Khi API thiếu Bearer token, mã trạng thái thường là gì?

**401 Unauthorized** với `WWW-Authenticate: Bearer`. Không redirect tới login page của browser chỉ vì API chưa xác thực.

**Câu 6.** JWT hợp lệ nhưng thiếu `SCOPE_orders.read` nên được xử lý thế nào?

Thường là **403 Forbidden**, không bắt người dùng login lại để thử thay thế authority. Client cần xin/quản lý permission đúng luồng OAuth/ứng dụng.

**Câu 7.** OIDC browser Authorization Code dùng redirect có sai không?

Không. Redirect là một phần chủ ý của luồng interactive login. Vấn đề là đưa luồng đó vào protected Resource Server API được máy gọi bằng Bearer token.

**Câu 8.** Tại sao một client báo HTTP 200 nhưng JSON parser lỗi vì ký tự `<`?

Có thể client đã follow 302 tới trang login rồi nhận HTML 200. Cần kiểm tra response ban đầu, `Location` và `Content-Type` thay vì chỉ status cuối.

**Câu 9.** Khi API dùng CORS, có bắt buộc mở mọi OPTIONS bằng `permitAll` không?

Không. Cần cấu hình CORS processor và nguồn origin/method/header phù hợp; rule OPTIONS rộng không tự tạo CORS headers và có thể mở quá nhiều requests.

**Câu 10.** Vì sao không tắt CSRF trên mọi chain trong ứng dụng hỗn hợp?

Browser session/cookie authentication có thể bị CSRF vì browser tự gửi credential. Tắt CSRF có thể phù hợp cho pure header-based Bearer API nhưng không mặc định an toàn cho web login/BFF.

**Câu 11.** Khi nào nên dùng nhiều `SecurityFilterChain`?

Khi ứng dụng có các vùng URL cần authentication mechanisms/entry points/session policies khác nhau, ví dụ `/api/**` với Bearer và `/web/**` với OIDC browser login. Phải kiểm soát `@Order` và `securityMatcher`.

**Câu 12.** Một `anyRequest().denyAll()` trong API chain có bảo vệ mọi URL ứng dụng không?

Không. Nó chỉ áp cho các requests đã chọn chain đó. Nếu có nhiều chain, cần fallback phù hợp để không có route nằm ngoài phạm vi bảo vệ.

**Câu 13.** POST thiếu token có nên được lưu rồi tự replay sau login không?

Không đối với API machine clients. Request cache không phải hàng đợi transactional; replay thao tác ghi có thể sai method/body hoặc tạo side effect trùng. API cần trả lỗi authentication, còn retry/idempotency thuộc contract nghiệp vụ và client.

**Câu 14.** Nếu Resource Server trả 401 nhưng gateway trả 302 thì sửa ở đâu?

Cần sửa gateway/SSO rewrite policy cho API, đồng thời kiểm tra rằng upstream Spring Security đang trả Bearer challenge đúng. Test phải đi qua gateway thực tế.

**Câu 15.** Khi introspection timeout, redirect login có giúp Resource Server xác minh token không?

Không. Lỗi hạ tầng introspection nghĩa là chưa có bằng chứng token hợp lệ, nên không tạo principal. Việc điều hướng login không thay thế kiểm tra token và chỉ làm máy gọi khó xử lý lỗi.

## 20. Checklist cấu hình API máy gọi

### 20.1. Phạm vi và authentication

- [ ] Đã xác định endpoint nào là **Bearer Resource Server API** và endpoint nào phục vụ browser login.
- [ ] API chain có `securityMatcher` phù hợp khi nhiều chains cùng tồn tại.
- [ ] Thứ tự `@Order` bảo đảm browser login chain không chiếm API trước.
- [ ] Có một fallback chain cho URL không thuộc các khu vực đã phân loại.
- [ ] JWT decoder/introspection source được cấu hình với issuer, audience và token profile đáng tin.
- [ ] Đã phân quyền HTTP theo method/scope, không chỉ `anyRequest().authenticated()` với mọi endpoint.
- [ ] Quyền sở hữu tài nguyên/tenant được kiểm tra thêm ở service khi cần.

### 20.2. Trạng thái, saved request và login

- [ ] API chain không dùng form login/OAuth2 interactive login nếu chỉ phục vụ máy gọi.
- [ ] API chain dùng `NullRequestCache` hoặc `NoOpServerRequestCache` theo stack.
- [ ] Đã quyết định chính sách session/context persistence: `STATELESS` hoặc reactive no-op repository theo kiến trúc.
- [ ] Không có filter/controller ngoài ý muốn tạo `JSESSIONID`/web session cho pure API.
- [ ] Không đưa raw Bearer token, Authorization header hoặc JSON POST body vào saved request/session.
- [ ] Browser chain được giữ login redirect/CSRF/session đúng mục đích, không bị API policy làm hỏng.
- [ ] OAuth2 authorization endpoint và callback login nằm trong browser chain thích hợp.

### 20.3. HTTP behavior và bảo vệ web

- [ ] Missing Bearer → 401, không 302.
- [ ] Invalid token → 401 invalid_token (khi phù hợp), không 302 hoặc 200 HTML.
- [ ] Valid token thiếu authority → 403, không redirect.
- [ ] `WWW-Authenticate: Bearer` không bị custom handler/gateway làm mất.
- [ ] Không trả raw token/claims/exception stacktrace trong error body.
- [ ] CORS preflight được xử lý theo origin/method/header policy.
- [ ] CSRF được bảo vệ ở browser/cookie flows, chỉ tắt khi threat model của API cho phép.
- [ ] Headers liên quan response cache và dữ liệu nhạy cảm được quyết định riêng.
- [ ] Không có open redirect hoặc redirect cross-origin mang Bearer token.
- [ ] Gateway không rewrite API 401 thành SSO login redirect.

### 20.4. Kiểm thử và quan sát

- [ ] Có test thiếu token, token sai, thiếu scope, token hợp lệ.
- [ ] Có test không `Location: /login` và không HTML login sau lỗi authentication.
- [ ] Có test không phát hành session cookie/saved request trong phạm vi API stateless.
- [ ] Có test browser route vẫn login/callback đúng contract.
- [ ] Có test CORS preflight và POST theo CSRF policy thực tế.
- [ ] Có test URL nằm ngoài API chain để xác nhận fallback policy.
- [ ] Có test qua gateway với chế độ không auto-follow redirect.
- [ ] Có test JWT signature/introspection **thật** riêng, không chỉ `jwt()`/`opaqueToken()` post processors.
- [ ] Logging/tracing không chứa raw access token, session ID hoặc secrets.
- [ ] Error/redirect metrics phân biệt 401/403/302 theo route/chain để phát hiện regression.

Một endpoint công khai bằng `permitAll` không đồng nghĩa toàn bộ request bỏ qua filters. Một API stateless không đồng nghĩa toàn bộ ứng dụng không có session. Và một API dùng OAuth 2.0 không đồng nghĩa nó phải tự thực hiện **OAuth2 Login redirect**: phải giữ đúng vai trò **Resource Server**.

## 21. Tổng kết

Sơ đồ quyết định cho API machine-to-machine:

~~~text
                Machine client gọi protected API
                               |
                               v
               SecurityFilterChain dành cho API
                               |
         +---------------------+---------------------+
         |                     |                     |
     No Bearer            Bearer invalid         Bearer valid
         |                     |                     |
         v                     v                     v
    401 + Bearer           401 invalid_token     HTTP authorization
    challenge              (no login redirect)       |
         |                     |               +-----+------+
         |                     |               |            |
         |                     |           Missing scope   Scope OK
         |                     |               |            |
         v                     v               v            v
    No saved request     No saved request      403       Controller
    No login redirect    No login redirect  forbidden    + domain auth

    Session policy:    stateless Bearer handling
    Request cache:     NullRequestCache / NoOpServerRequestCache
    Browser login:     một chain khác, chỉ nếu sản phẩm cần
~~~

**Những điều cần nhớ nhất:**

1. **Request cache phục vụ browser navigation**, không phải cơ chế xác minh, retry hoặc lưu Bearer token của API. Với pure API machine clients, thường chọn `NullRequestCache` hoặc `NoOpServerRequestCache`.
2. **Redirect login là hành vi dành cho client tương tác**. Resource Server API phải giữ Bearer challenge và lỗi HTTP rõ ràng; không đổi 401/403 thành 302 hoặc 200 HTML.
3. **Stateless không có nghĩa toàn bộ server tuyệt đối không thể tạo session**. `SessionCreationPolicy.STATELESS` điều chỉnh cách Spring Security dùng session, còn request cache và thành phần ứng dụng khác cần cấu hình riêng.
4. **Tách security policies theo phạm vi** khi ứng dụng có cả browser OIDC login và API Bearer token. Mỗi `SecurityFilterChain` có entry point, CSRF/CORS/session/request-cache policy riêng theo hợp đồng.
5. **Bảo vệ web không chỉ gồm request cache**. CSRF cho cookie-based browser flows, CORS cho browser cross-origin, HTTP security headers, token validation và domain authorization vẫn là những nhiệm vụ riêng.
6. **Kiểm thử đường thất bại quan trọng như đường thành công**: thiếu token, token sai, thiếu scope, introspection outage, gateway redirect, session cookie và preflight đều phải có kỳ vọng rõ.

Đích cuối cùng không phải “tắt mọi thành phần của Spring Security”, mà là dùng **đúng cơ chế cho đúng loại client**: browser có thể cần login redirect và saved request; Resource Server phục vụ máy gọi cần **Bearer authentication, trạng thái phù hợp và response HTTP dự đoán được**, không biến lỗi token thành một hành trình qua trang đăng nhập.

## Tài liệu tham khảo

- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Servlet Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Security — Reactive Session Management](https://docs.spring.io/spring-security/reference/reactive/authentication/session-management.html)
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9110 — HTTP Semantics (Status Codes and Redirection)](https://www.rfc-editor.org/rfc/rfc9110)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
