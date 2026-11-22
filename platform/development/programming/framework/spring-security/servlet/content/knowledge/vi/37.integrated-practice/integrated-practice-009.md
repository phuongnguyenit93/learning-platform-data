# Điều tra lỗi bộ lọc, matcher và SecurityContext từ dấu vết yêu cầu trong Spring Security Servlet

## 1. Bài toán thực hành: “cùng API, sao lại 401, 403 hoặc vào sai handler?”

Giả sử một ứng dụng Spring Boot sử dụng Spring Security Servlet có các tình huống sau:

- `GET /api/me` khi đã gửi thông tin đăng nhập hợp lệ vẫn trả **401 Unauthorized**.
- `POST /api/notes` của người có `ROLE_EDITOR` lại trả **403 Forbidden**.
- `GET /api/admin/audit` của người bình thường trả 403 như dự kiến, nhưng một số URL tương tự được cho qua vì **request matcher rộng** hoặc filter chain khác đang được chọn.
- Một controller nhìn thấy `SecurityContextHolder.getContext().getAuthentication() == null` dù trước đó một filter từng xác thực thành công.
- Hai request liên tiếp hoặc một tác vụ `@Async` có kết quả principal khác nhau.
- Log ghi “Securing ...” nhưng không nói rõ **chain nào**, filter nào hoặc rule nào là nguyên nhân.

Đây là bài **thực hành tổng hợp**: thay vì sửa 403 bằng cách thêm `permitAll()`, ta xây một phương pháp điều tra dựa trên **dấu vết request có thứ tự và dữ liệu kiểm chứng được**.

Mục tiêu cụ thể:

1. Xác định đúng **HTTP method, đường dẫn bên trong ứng dụng, Servlet dispatcher type, authentication mechanism, correlation ID**.
2. Tìm **`SecurityFilterChain` được chọn** và hiểu sự khác nhau giữa `securityMatcher` (chọn chain) và `requestMatchers` (phân quyền bên trong chain).
3. Theo dõi những filter quan trọng: `SecurityContextHolderFilter`, `CsrfFilter`, `BasicAuthenticationFilter` hoặc filter đăng nhập, `AnonymousAuthenticationFilter`, `ExceptionTranslationFilter`, `AuthorizationFilter`.
4. Phân biệt lỗi **authentication**, **authorization**, **CSRF**, lỗi cấu hình MVC, **method security** và lỗi **SecurityContext lifecycle/propagation**.
5. Dựng một ứng dụng **Java 17, Spring Boot 3.3.5, Spring Security 6 Servlet** có hai chain, filter chẩn đoán an toàn, endpoint theo vai trò và `@PreAuthorize`.
6. Tái hiện bằng **MockMvc/JUnit 5** và kiểm kết quả trước khi thay cấu hình, không mở rộng quyền vô ý.

**Ranh giới:** ví dụ dùng password `{noop}` và HTTP Basic **chỉ để học tập trên máy cục bộ**. Bản Boot 3.3.5 là baseline có chủ đích, **không** được coi là bản mới nhất hoặc đã được xác minh hết CVE khi phát hành. Muốn chạy production cần dependency/security advisory hiện hành, HTTPS, PasswordEncoder, nguồn danh tính thực, kiểm ACL trên dữ liệu và quan sát có bảo vệ thông tin nhạy cảm.

## 2. Bản đồ đường đi của request

Trong một ứng dụng Servlet thông thường, browser hoặc HTTP client gửi request vào Servlet container. Spring Security thường được tích hợp qua `DelegatingFilterProxy`, chuyển tiếp sang `FilterChainProxy`. Proxy này so khớp lần lượt các `SecurityFilterChain` đã được khai báo, sau đó gọi các security filters của **chain phù hợp đầu tiên**. Cuối cùng mới đến `DispatcherServlet` và handler của Spring MVC nếu các filter cho phép request đi tiếp.

~~~text
Client: GET /api/me
        |
        v
Servlet container filters
        |
        v
DelegatingFilterProxy("springSecurityFilterChain")
        |
        v
FilterChainProxy
        |
        +-- Chain #1 securityMatcher("/api/**")? ------ YES
        |                                               |
        |                                         Security filters
        |                                               |
        |                                  SecurityContextHolderFilter
        |                                  HeaderWriterFilter
        |                                  [TraceFilter của demo]
        |                                  CsrfFilter
        |                                  BasicAuthenticationFilter
        |                                  AnonymousAuthenticationFilter
        |                                  ExceptionTranslationFilter
        |                                  AuthorizationFilter
        |                                               |
        |                                               v
        |                                        DispatcherServlet
        |                                               |
        |                                               v
        |                                       @RestController / service
        |
        +-- Chain #2 fallback? ---------------- Chỉ nếu #1 không match

Sau khi xử lý: response đi ngược qua các filter;
SecurityContext được dọn theo lifecycle của security chain.
~~~

Đây là **sơ đồ giản lược**, không phải danh sách đầy đủ hay thứ tự bất biến cho mọi ứng dụng. Filter order có thể khác khi bật form login, OAuth2/OIDC, resource server JWT, CORS, logout, request cache, session management, custom filters hoặc cấu hình Spring Security khác.

Ba câu hỏi **phải trả lời theo thứ tự**:

1. **Request có thực sự đi qua Spring Security không?** Kiểm filter registration, servlet path, `securityMatcher`, proxy/gateway route, static resource handler và trường hợp không chain nào khớp.
2. **Nó dừng ở đâu?** Authentication thất bại, CSRF không hợp lệ, authorization filter chặn, method security chặn, hay controller ném một lỗi không liên quan?
3. **Tại thời điểm quyết định, Authentication là gì?** Không có, anonymous, authenticated Basic/session/JWT, principal sai loại, hoặc authorities thiếu/sai tên?

Chỉ xem status HTTP không đủ: **403** có thể do `CsrfFilter`, `AuthorizationFilter`, `@PreAuthorize`, hoặc custom `AccessDeniedHandler`. Không sửa đến khi có bằng chứng của tầng gây lỗi.

## 3. Thu thập “hồ sơ sự cố” từ dấu vết yêu cầu

Trước khi thay code, nên ghi một record tái hiện tối thiểu:

| Trường | Ví dụ | Dùng để |
| --- | --- | --- |
| Request ID | `7f3e...` do server tạo | Ghép log nhiều thành phần của cùng request |
| HTTP method | `GET`, `POST`, `PUT`, `DELETE` | So matcher và CSRF policy |
| Request path | `/api/notes` | Xác định path/servlet mapping sau proxy |
| Dispatcher type | `REQUEST`, `FORWARD`, `ERROR`, `ASYNC` | Biết filter có được đăng ký cho dispatch hiện tại không |
| Authentication source | Basic, session, bearer JWT, OAuth2 Login | Biết filter/provider nào có trách nhiệm |
| Authentication state | absent / anonymous / verified | Phân biệt 401 và 403 |
| Authorities | `ROLE_EDITOR`, `ROLE_ADMIN` (ẩn/giới hạn theo quyền khi log) | Kiểm hasRole/hasAuthority |
| Expected rule | `POST /api/notes -> ROLE_EDITOR` | Đối chiếu hợp đồng quyền |
| CSRF state | required + missing/invalid/valid | Giải thích 403 ở unsafe request |
| Status + response headers | 401/403/200/201 + `WWW-Authenticate` | Kiểm entry point/handler |
| Runtime config version | commit, artifact digest, profile | Điều tra vì sao staging khác production |
| Chain/filter signal | FilterChainProxy logs, trace ID | Gắn lỗi vào chain/filter cụ thể |

**Không thu thập bản thân mật khẩu, `Authorization` header, bearer token, CSRF token, session cookie, reset link, OIDC ID token hoặc raw request body nhạy cảm** vào report/debug logs. Khi path có tài khoản, email, document ID hoặc secret query, chỉ ghi route template (`/api/files/{id}`) hoặc bản đã được làm mờ.

Một ví dụ record an toàn:

~~~text
incident=INC-42
trace=7f3e...
method=POST route=/api/notes dispatcher=REQUEST
identity_state=authenticated principal_kind=User
expected=ROLE_EDITOR csrf_required=true csrf_present=false
status=403
hypothesis=CSRF_FILTER_REJECTED_BEFORE_BASIC_AUTH
verification=repeat request with valid CSRF in an isolated test
~~~

**Hypothesis không phải kết luận**: phải đối chiếu với chain/filter logs và test có kiểm soát. Nếu ứng dụng chuyển sang bearer-only API với session policy khác, CSRF policy cần được đánh giá theo threat model; không suy ra chỉ từ việc endpoint trả JSON.

### 3.1. So sánh request trên browser và curl

Đôi khi “cùng URL” nhưng thực tế khác:

- Browser gửi cookie phiên; curl không có cookie hoặc không giữ cookie giữa hai request.
- Browser dùng `Origin`, `Referer`, CORS preflight OPTIONS; curl có thể không gửi.
- Browser submit form/JSON bằng POST kèm CSRF token; curl bỏ token.
- Proxy rewrite `/app/api/me` thành `/api/me`; log bên ngoài và bên trong có path khác.
- Browser làm redirect 302 tới `/login`; curl mặc định có thể không theo redirect hoặc `-L` làm che response đầu tiên.
- Browser retry, prefetch hoặc request song song; một thao tác UI có thể tạo nhiều HTTP requests khác nhau.

Vì vậy lưu **request method, normalized internal path, status đầu tiên và cookie/header presence**, không chỉ câu mô tả “đăng nhập rồi không vào được”.

## 4. FilterChainProxy chọn chain trước khi xét quyền

Mỗi `SecurityFilterChain` có một `RequestMatcher` dùng để xác định chain đó có xử lý request không. Với cấu hình nhiều chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/healthcheck").permitAll()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là **mảnh cấu hình**, chưa đầy đủ imports/ứng dụng; project chạy được có ở mục 10.

- `securityMatcher("/api/**")` quyết định **chain 1 áp dụng cho request nào**. Nó không cho phép request; quyền được xét **sau đó** trong `authorizeHttpRequests`.
- Chain 2 không đặt `securityMatcher`, nên có thể là **fallback** cho request không khớp chain 1.
- Trong một chain, các `requestMatchers(...)` được xét theo thứ tự khai báo: rule match trước áp dụng trước.
- `@Order(1)`, `@Order(2)` ảnh hưởng thứ tự xét **chain**; thứ tự các rule bên trong chain là vấn đề khác.
- **`anyRequest().denyAll()` của chain 1 không bảo vệ URL nằm ngoài `/api/**`**. Nếu không có fallback/chain khác và URL không khớp chain nào, request có thể không được Spring Security bảo vệ.

### 4.1. Lỗi điển hình: securityMatcher sai phạm vi

~~~java
// Có vấn đề nếu API thật nằm ở /api/**.
http.securityMatcher("/web/**")
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated());
~~~

Rule `/api/admin/**` bên trong chain này có thể **không bao giờ được đánh giá** cho request `/api/admin/report` vì chain không chọn request đó. Việc nhìn thấy `hasRole("ADMIN")` trong source không chứng minh endpoint được bảo vệ.

Để điều tra, tìm trong `FilterChainProxy` logs xem request match chain nào, rồi kiểm các filter được kích hoạt. Nếu không chain nào khớp, không chữa bằng cách sửa `hasRole` bên trong chain không được chọn.

### 4.2. Lỗi điển hình: matcher rộng “nuốt” matcher hẹp

~~~java
// Nguy hiểm: /api/admin/** cũng khớp /api/**.
auth.requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN");
~~~

Người chỉ được xác thực có thể vượt qua rule rộng trước. Chuyển rule cụ thể lên đầu:

~~~java
auth.requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll();
~~~

**Rule order và chain order là hai trục khác nhau**. Đừng đổi cả hai cùng lúc khi đang điều tra, vì sẽ khó xác định thay đổi nào giải quyết lỗi và liệu có mở đường vòng khác hay không.

### 4.3. Path matching không chỉ là dấu sao

Kiểm sự khác nhau giữa `requestURI`, `contextPath`, `servletPath`, `pathInfo`, prefix ở reverse proxy và đường dẫn được MVC decode/normalize. Với nhiều `DispatcherServlet` hoặc servlet path riêng, lựa chọn matcher có thể cần cấu hình tường minh (ví dụ `MvcRequestMatcher.Builder` và `HandlerMappingIntrospector` ở những dòng phù hợp).

Không tự ghép `server.servlet.context-path` vào mọi matcher; phải xác minh semantics của matcher và request bên trong container. Test cả encoded slash, trailing slash, path params và method khi ứng dụng thực sự chấp nhận chúng.

## 5. Thứ tự filter quyết định loại bằng chứng bạn nhìn thấy

Một chuỗi xử lý thường có các ý nghĩa sau:

| Thành phần | Vai trò trong điều tra | Dấu hiệu quan trọng |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Cung cấp context cho request, dọn khi kết thúc | Context có được load/clear theo lifecycle? |
| `HeaderWriterFilter` | Gắn security headers | Chỉ test status chưa đủ, kiểm headers |
| `CorsFilter` (khi bật) | Xử lý CORS/preflight | OPTIONS có thể bị xử lý trước auth |
| `CsrfFilter` | Kiểm token cho unsafe methods theo policy | POST bị 403 **trước** bước authenticate |
| `LogoutFilter` | Xử lý logout endpoint | Logout path/method/CSRF |
| `UsernamePasswordAuthenticationFilter` | Thực hiện form login khi được bật | POST login, failure/success handler |
| `BasicAuthenticationFilter` | Phân tích Basic credentials và xác thực | 401 do credential sai/thiếu theo entry point |
| `BearerTokenAuthenticationFilter` | Phân tích bearer token nếu resource server được bật | Decoder/introspection lỗi, signature/issuer/audience |
| `AnonymousAuthenticationFilter` | Đặt anonymous token khi chưa có authentication | Anonymous token có thể tồn tại nhưng không phải user đã login |
| `ExceptionTranslationFilter` | Chuyển security exceptions thành entry point/denied response | 401/redirect/403 |
| `AuthorizationFilter` | Áp dụng URL authorization | Deny rule, method/path/role mismatch |
| Method security interceptor | Kiểm `@PreAuthorize` khi service proxy được gọi | URL đã cho qua nhưng service vẫn từ chối |

**Không giả định filter nào cũng chạy ở mỗi request.** Ví dụ request POST thiếu CSRF token có thể dừng tại `CsrfFilter`, nên filter xác thực Basic phía sau chưa được gọi. Nếu bạn đặt trace filter **sau CsrfFilter** rồi nói “không thấy trace = request không đến Spring Security”, kết luận đó sai.

Một kỹ thuật hữu ích trong demo: chèn filter chẩn đoán **trước `CsrfFilter` nhưng sau phần thiết lập SecurityContext**. Nó ghi dấu request khi request sẽ đi vào CsrfFilter và có thể ghi lại status sau chuỗi downstream. Tuy vậy log ở filter đầu **không** thay thế trace chi tiết để phân biệt chính xác `BasicAuthenticationFilter`, `ExceptionTranslationFilter` hay method security đã từ chối.

### 5.1. Vì sao exception có thể biến thành 401 hoặc 403?

Đường đi giản lược:

~~~text
Authorization / Method security throws AccessDeniedException
                         |
                         v
               ExceptionTranslationFilter
                         |
            +------------+-------------+
            |                          |
       Anonymous /                  Authenticated
       no login                     without permission
            |                          |
            v                          v
      AuthenticationEntryPoint    AccessDeniedHandler
      401 hoặc redirect 302             403

AuthenticationException từ authentication flow
            |
            v
      AuthenticationEntryPoint
      401 hoặc redirect /login
~~~

`ExceptionTranslationFilter` không phải filter tự xác thực. Nó dịch exceptions thuộc security thành response/redirect phù hợp. Các filter authentication có thể tự xử lý failure. Một `@ControllerAdvice` hoặc custom exception handler cũng có thể thay status, vì vậy phải nhìn **cả filter chain lẫn MVC exception handling**.

**401 vs 403 trong demo HTTP Basic:**

- Anonymous/Basic password sai trên protected GET → **401**.
- Basic hợp lệ nhưng thiếu role → **403**.
- POST thiếu/sai CSRF → **403** kể cả role đúng; status này chưa chứng minh authorization rule đã chạy.
- URL không match controller nhưng bị default deny từ Security → có thể **401/403 thay vì 404/405**.
- Nếu dùng form login, một anonymous request có thể nhận **302 redirect** tới login, không phải 401.

## 6. SecurityContext: danh tính sống ở đâu, bị mất khi nào?

`SecurityContextHolder` cung cấp quyền truy cập context của **luồng thực thi hiện tại** theo strategy được cấu hình. Trong nhiều ứng dụng Servlet, strategy mặc định dựa trên `ThreadLocal`.

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Mảnh Java này cần các imports `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`.

Các trạng thái thường gặp:

| `Authentication` | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| `null` | Chưa được set hoặc không có context authenticated ở thời điểm đọc | Không chứng minh filter Basic luôn không tồn tại; có thể đọc quá sớm/quá muộn |
| `AnonymousAuthenticationToken` | Authentication đại diện anonymous do filter đặt | `isAuthenticated()` có thể là true, **không** được coi là login thành công |
| `UsernamePasswordAuthenticationToken` | Có thể đại diện auth qua form/Basic/provider hoặc request khởi tạo chưa authenticated | Phải kiểm trạng thái `isAuthenticated`, authorities và provider flow |
| `JwtAuthenticationToken` | Identity từ JWT resource server đã xác minh | Cần kiểm issuer/audience/scopes/authority mapping, không tin raw claims |
| `OAuth2AuthenticationToken` | Identity sau OAuth2 Login | Phân biệt external ID và local user/role |
| Principal của domain riêng | Identity sau mapping từ IdP/DB | Test đúng class, tenant, account ID và quyền |

**Đặc biệt:** Spring Security có cơ chế phân biệt anonymous với người đã authenticated; đừng tự kiểm `authentication != null && authentication.isAuthenticated()` rồi cấp quyền cho một `AnonymousAuthenticationToken`. Dùng `authenticated()`, `fullyAuthenticated()` hoặc cơ chế `AuthenticationTrustResolver` tương ứng khi chính sách cần.

### 6.1. SecurityContextHolderFilter và persistence

Trong các cấu hình Spring Security 6 phổ biến, `SecurityContextHolderFilter` làm nhiệm vụ **đưa SecurityContext từ `SecurityContextRepository` vào context holder theo lifecycle request** và dọn context ở cuối. Khác với một số cách cấu hình legacy dùng `SecurityContextPersistenceFilter`, không nên giả định **tự set context** trong custom authentication code sẽ tự lưu nó vào HTTP session.

Nếu chính bạn xây luồng đăng nhập thủ công thay vì để authentication filter đã được framework quản lý thực hiện, cần thiết kế `SecurityContextRepository` phù hợp và **gọi `saveContext` tại thời điểm thích hợp** nếu muốn duy trì authentication qua request sau. Việc này phụ thuộc dòng/config thực tế; không tự chép một snippet legacy dùng session mà không kiểm semantics.

Các dấu hiệu:

- Authenticated thành công trong **request A** nhưng request **B** không có principal: kiểm cookie/session, `SecurityContextRepository`, session creation policy, logout, save semantics và liệu request B có gửi credential lại không.
- `SessionCreationPolicy.STATELESS`: không kỳ vọng Basic/JWT auth từ request A tự tạo phiên login cho request B; token/credentials thường phải được cung cấp trên từng request.
- `SecurityContextHolder.getContext()` ở một **thread bên ngoài request** rỗng không chứng minh request ban đầu không được xác thực.
- Khi response đã committed hoặc session đã invalidated, việc lưu context thủ công có thể không còn tác dụng như mong đợi; cần dùng integration test cookie/session thực.

### 6.2. Khi nào context được gắn và xóa?

Mô hình khái quát:

~~~text
Request A begins, thread T1
  -> SecurityContextHolderFilter supplies context
  -> BasicAuthenticationFilter authenticates
  -> AuthorizationFilter permits
  -> Controller sees authenticated principal
  -> response completes
  -> SecurityContextHolderFilter clears holder on T1

Request B begins, thread T2 (could reuse a pooled thread)
  -> New request lifecycle loads its own context
  -> If no saved session/credential, it may be anonymous
~~~

Thread có thể được tái sử dụng bởi servlet container. **Không lưu Authentication trong một static field** rồi dùng lại cho mọi request. Không gọi `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` để “sửa mất login” — đó có thể trở thành rò rỉ principal giữa nhiều người dùng.

### 6.3. Async, executor và context propagation

Nếu controller gọi `@Async`, `CompletableFuture`, tự tạo thread hoặc gửi message sang một worker khác, context dựa trên ThreadLocal **không mặc định được sao chép sang luồng đó**. Dùng các cơ chế được Spring Security hỗ trợ như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` hoặc integration với executor/context propagation phù hợp. Đưa identity có chủ đích qua boundary; với job dài hạn cần kiểm lại quyền theo chính sách hiện hành, không mang security context cũ vô thời hạn.

Trong luồng async/error/forward dispatch, kiểm `DispatcherType`, filter registration, lifecycle và handler bảo mật. Không giả định `OncePerRequestFilter` luôn chạy đúng một lần ở mọi redispatch: `shouldNotFilterAsyncDispatch` và `shouldNotFilterErrorDispatch` cùng cách container dispatch ảnh hưởng hành vi.

## 7. Suy luận từ status và log: cây quyết định an toàn

~~~text
BẮT ĐẦU: Request trả 401/403/404/302 hoặc principal null
 |
 +-- (A) Có dấu request tới đúng app/servlet?
 |      Không -> proxy, port, DNS, ingress, servlet filter registration
 |      Có
 |       |
 |       +-- (B) FilterChainProxy chọn chain nào?
 |              Không chain -> securityMatcher/fallback hoặc bypass filter
 |              Có chain
 |               |
 |               +-- (C) Unsafe method và CSRF áp dụng?
 |               |      Thiếu/sai token -> CsrfFilter -> 403
 |               |      Hợp lệ/không yêu cầu
 |               |
 |               +-- (D) Authentication có hợp lệ?
 |               |      Missing/bad credentials -> 401 hoặc login redirect
 |               |      Valid (hoặc anonymous ở public route)
 |               |
 |               +-- (E) AuthorizationFilter chọn rule nào?
 |               |      Wrong method/path/role -> 403 (hoặc 401 với anon)
 |               |      Permit
 |               |
 |               +-- (F) Controller/service/method security?
 |               |      @PreAuthorize/ACL từ chối -> 403/404 policy
 |               |      Handler không match -> 404/405
 |               |
 |               +-- (G) Context ở thread khác / sau request?
 |                      Missing -> repository/save/session/async propagation
 |
 KẾT THÚC: Có giả thuyết đã tái hiện và regression test âm tính.
~~~

**Đừng kết luận chỉ dựa vào một thông báo log.** Log `FilterChainProxy: Securing GET /api/me` cho thấy request đi vào phần bảo mật, **không chứng minh** Basic credentials đã được xác minh. Log `Authenticated user` cho thấy một bước xác thực, **không chứng minh** request cuối cùng được phép đọc đối tượng. Một 403 sau login có thể là role, CSRF hoặc ownership.

### 7.1. Tại sao trace đôi lúc thấy Authentication “none” ở filter trước?

Một filter chẩn đoán được đặt trước Basic auth thường log `auth=none` ở đầu request vì authentication **chưa chạy**. Sau `chain.doFilter`, cùng filter có thể quan sát principal nếu downstream xác thực thành công. Nếu CsrfFilter chặn trước Basic auth, cả hai thời điểm có thể đều `none`.

Vì vậy log cần chứa ít nhất **phase=before/after** và vị trí filter, không chỉ một câu “SecurityContext null” thiếu thời gian.

### 7.2. Vì sao thấy AnonymousAuthenticationToken nhưng vẫn 401?

`AnonymousAuthenticationFilter` có thể cung cấp một token đại diện anonymous cho các thành phần sau. Khi protected route yêu cầu `authenticated()`, access decision vẫn từ chối anonymous; entry point HTTP Basic có thể gửi 401. **Anonymous token không tương đương login thành công**.

## 8. Bật logging có chọn lọc, không lộ thông tin nhạy cảm

Trong môi trường **test/staging cô lập**, có thể bật log ở package cụ thể. Ví dụ trong `application-debug.properties` hoặc tham số runtime:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept.AuthorizationFilter=TRACE
logging.level.org.springframework.security.web.csrf.CsrfFilter=DEBUG
logging.level.example.tracelab=DEBUG
~~~

Đây là **ví dụ cấu hình chẩn đoán**, không được bật TRACE rộng rãi và vô thời hạn trong production. Tên logger/độ chi tiết có thể thay đổi theo phiên bản; nếu không thấy event ở đúng logger, kiểm filter chain thực tế và mức log hiện hành thay vì đoán chắc chức năng không chạy.

Khi cần bật `org.springframework.security=DEBUG/TRACE`, hãy:

- Giới hạn thời gian, môi trường, traffic hoặc sampling; có người duyệt nếu log chứa dữ liệu nhạy cảm.
- Cấu hình redaction cho Authorization, Cookie, Set-Cookie, CSRF token, password, query string chứa reset/magic link, OIDC code/state, private path.
- Không bật `spring.security.debug=true` trên production mà không đánh giá vì debug filter có thể ghi request/header hoặc dữ liệu nhạy cảm.
- Đảm bảo log storage có ACL, retention và audit phù hợp; không đẩy raw logs vào ticket/chat công khai.
- Xem **correlation ID** nhưng không coi ID do client gửi là tin cậy nếu chưa validate/normalize; tránh log injection hoặc header response splitting.
- Nếu cần phân tán tracing qua proxy/ứng dụng/IdP, dùng chuẩn trace context với trust boundary rõ ràng; không đồng nhất một trace ID với một identity đã xác thực.

### 8.1. Điều gì là một “đoạn log đủ dùng”?

~~~text
trace=example-01 phase=before method=POST route=/api/notes
dispatcher=REQUEST authKind=none

trace=example-01 phase=after status=403 authKind=none

Security diagnostics: CSRF rejected request before Basic auth
~~~

Đây là **dấu vết minh họa** hợp lý cho một POST thiếu CSRF trong cấu hình demo, **không phải nguyên văn log do Spring Security bắt buộc xuất ra**. Phần kết luận “CSRF rejected” chỉ nên ghi sau khi đối chiếu log CsrfFilter hoặc test so sánh cùng request với CSRF hợp lệ. Không log giá trị token để chứng minh lỗi.

Với một lỗi phân quyền khác:

~~~text
trace=example-02 method=GET route=/api/admin/audit
authentication=verified role_group=EDITOR
url_authorization=denied
status=403
~~~

Trong sản phẩm, trường `role_group` nên được kiểm tra chính sách riêng tư/thu thập dữ liệu; thường chỉ cần một mã quyết định như `wrong_authority`, không nhất thiết log toàn bộ authorities.

## 9. Lab chính: các trạng thái cần tái hiện

Ứng dụng ví dụ sẽ có **hai SecurityFilterChain** và sáu endpoint. Có hai tài khoản demo:

- `editor` với `ROLE_EDITOR`.
- `admin` với `ROLE_ADMIN`, **không tự có `ROLE_EDITOR`**.

| Method | URL | Chain | Rule ở URL | Extra checks |
| --- | --- | --- | --- | --- |
| GET | `/api/public/ping` | API | `permitAll()` | Không có |
| GET | `/api/me` | API | `authenticated()` | Không có |
| POST | `/api/notes` | API | `hasRole("EDITOR")` | CsrfFilter |
| GET | `/api/admin/audit` | API | `hasRole("ADMIN")` | Không có |
| GET | `/api/reports/internal` | API | `authenticated()` | `@PreAuthorize("hasRole('ADMIN')")` ở service |
| GET | `/healthcheck` | Fallback | `permitAll()` | Không có |
| URL/method khác | Bất kỳ | API hoặc fallback | `denyAll()` | Tùy method/CSRF |

Mục đích bố trí `/api/reports/internal` khác `/api/admin/audit`:

- Ở `/api/admin/audit`, `ROLE_EDITOR` bị từ chối tại **URL authorization**.
- Ở `/api/reports/internal`, `ROLE_EDITOR` **vượt qua URL rule `authenticated()`**, vào MVC, nhưng bị từ chối khi gọi Spring-managed service có **method security**. Cả hai có thể là 403, vì vậy nếu chỉ nhìn HTTP status sẽ không biết tầng nào quyết định.

Ma trận kỳ vọng khi POST có **CSRF hợp lệ**:

| Tình huống | Anonymous | EDITOR | ADMIN |
| --- | ---: | ---: | ---: |
| GET `/api/public/ping` | 200 | 200 | 200 |
| GET `/api/me` | 401 | 200 | 200 |
| POST `/api/notes` + CSRF | 401 | 201 | 403 |
| GET `/api/admin/audit` | 401 | 403 | 200 |
| GET `/api/reports/internal` | 401 | 403 | 200 |
| GET `/healthcheck` | 200 | 200 | 200 |
| GET `/api/unlisted` | 401 | 403 | 403 |
| GET `/outside` | 401 | 403 | 403 |

**CSRF phải được cấp hợp lệ cho POST trước khi diễn giải kết quả role.** Nếu thiếu CSRF, editor cũng nhận 403, nhưng do `CsrfFilter` chứ chưa chắc do `AuthorizationFilter`.

## 10. Dự án chạy được: Java 17, Spring Boot 3.3.5, Spring Security 6

### 10.1. Cấu trúc project

~~~text
security-trace-lab/
├── pom.xml
├── src/main/java/example/tracelab/TraceLabApplication.java
└── src/test/java/example/tracelab/TraceLabTests.java
~~~

Không cần LDAP/IdP/database/email hoặc container bên ngoài. Một cấu hình HTTP Basic cố ý dùng `{noop}` để học cách nhìn trace authentication. **Không** để thông tin này trong release artifact production.

### 10.2. Maven dependencies

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>security-trace-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-security-test` cấp các MockMvc request post-processor như `httpBasic()` và `csrf()`. `spring-boot-starter-security` cung cấp các filter/configurers cần thiết và `@EnableMethodSecurity` dùng cho method security. Không cần tự pin từng module Spring Security khi Spring Boot BOM đã quản lý phiên bản phù hợp với baseline.

### 10.3. File Java đầy đủ: hai chain, trace filter và method security

**src/main/java/example/tracelab/TraceLabApplication.java:**

~~~java
package example.tracelab;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
@EnableMethodSecurity
public class TraceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(TraceLabApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // Chỉ dùng trong lab, không dùng {noop} cho production.
        return new InMemoryUserDetailsManager(
                User.withUsername("editor")
                        .password("{noop}demo-pass")
                        .roles("EDITOR")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}demo-pass")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("EDITOR")
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin/audit")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports/internal")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                // Filter trước CsrfFilter: thấy cả trường hợp CSRF bị chặn.
                .addFilterBefore(
                        new DiagnosticTraceFilter(), CsrfFilter.class)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                // Không có securityMatcher: fallback cho URL ngoài /api/**.
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/healthcheck")
                            .permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .addFilterBefore(
                        new DiagnosticTraceFilter(), CsrfFilter.class)
                .build();
    }

    @Bean
    ReportService reportService() {
        return new ReportService();
    }

    public static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public String loadInternalReport() {
            return "restricted";
        }
    }

    @RestController
    static class ApiController {

        private final ReportService reports;

        ApiController(ReportService reports) {
            this.reports = reports;
        }

        @GetMapping("/api/public/ping")
        Map<String, String> publicPing() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication auth) {
            return Map.of("username", auth.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            // Không ghi DB: endpoint học tập về role + CSRF.
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/api/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "admin-only");
        }

        @GetMapping("/api/reports/internal")
        Map<String, String> report() {
            return Map.of("report", reports.loadInternalReport());
        }

        @GetMapping("/healthcheck")
        Map<String, String> health() {
            return Map.of("status", "up");
        }
    }

    static final class DiagnosticTraceFilter
            extends OncePerRequestFilter {

        private static final Logger log =
                LoggerFactory.getLogger(DiagnosticTraceFilter.class);

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            // ID ngẫu nhiên do server tạo; không sử dụng header untrusted.
            String trace = UUID.randomUUID().toString();
            response.setHeader("X-Demo-Trace", trace);

            log.debug(
                    "trace={} phase=before method={} path={} " +
                    "dispatch={} authKind={}",
                    trace, request.getMethod(), request.getServletPath(),
                    request.getDispatcherType(), authKind());

            try {
                chain.doFilter(request, response);
            } finally {
                log.debug(
                        "trace={} phase=after status={} authKind={}",
                        trace, response.getStatus(), authKind());
            }
        }

        private static String authKind() {
            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
            return auth == null
                    ? "none"
                    : auth.getClass().getSimpleName();
        }
    }
}
~~~

**Vì sao `DiagnosticTraceFilter` được tạo trực tiếp trong chain mà không đặt `@Component`?** Nếu khai báo một `Filter` như Spring bean và đồng thời thêm nó vào SecurityFilterChain, Spring Boot có thể tự đăng ký nó làm **Servlet container filter** và nó lại được gọi trong Spring Security chain, dẫn tới lọc/log hai lần với thứ tự không như mong đợi. Ở demo, mỗi chain tạo instance chỉ dùng trong **Security chain**.

Filter này log **loại Authentication**, không log username, token, password, request body hay toàn bộ authorities. Nó vẫn log `servletPath` để học: trong production, nếu path chứa PII/ID bí mật, phải biến nó thành **route template đã được chuẩn hóa** hoặc bỏ trường đó. Bật DEBUG ở phạm vi lab; không thu thập log chi tiết vô hạn trên production.

**Vị trí `addFilterBefore(..., CsrfFilter.class)` quan trọng:** khi POST thiếu CSRF, trace filter vẫn có thể ghi request trước/sau vì đứng **trước** CsrfFilter. Nếu đặt sau `CsrfFilter`, request bị CSRF từ chối có thể không đi đến trace filter, gây hiểu nhầm rằng request không đến ứng dụng. Tuy nhiên nếu request bị xử lý **trước vị trí custom filter** (ví dụ bởi một filter đứng trước nó), trace có thể vẫn không xuất hiện.

Lưu ý Java import `DispatcherType` ở ví dụ này được dùng để minh họa Servlet dispatch semantics ở phần giải thích; ứng dụng không cần điều kiện `DispatcherType` trong filter vì log gọi `request.getDispatcherType()`. Import không dùng không phải lỗi compile trong Java, nhưng có thể được IDE/linter cảnh báo; có thể bỏ import nếu muốn lint sạch.

### 10.4. Ý nghĩa của hai chain trong lúc debug

- `GET /api/me` → chain #1 vì `/api/**`; kiểm Basic, rồi `authenticated()`.
- `POST /api/notes` → chain #1; `CsrfFilter` có thể từ chối trước Basic auth.
- `GET /api/reports/internal` với EDITOR → URL `authenticated()` cho qua; sau đó `ReportService.loadInternalReport()` bị `@PreAuthorize` từ chối.
- `GET /healthcheck` → chain #2, anonymous được phép.
- `GET /outside` → chain #2, rơi vào deny-all. Anonymous thường nhận 401 với Basic entry point; đã authenticated nhưng thiếu quyền nhận 403.
- Khi bật method security, Spring quản lý `ReportService` bean và có thể tạo AOP proxy. Nếu gọi `new ReportService()` trực tiếp hoặc self-invocation trong cùng object, lời gọi có thể không đi qua interceptor và không kiểm `@PreAuthorize`; test cần gọi bean do Spring quản lý.

## 11. Bộ MockMvc tests để chứng minh nguyên nhân thay vì đoán

**src/test/java/example/tracelab/TraceLabTests.java:**

~~~java
package example.tracelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TraceLabTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiPathIsAvailableToAnonymous() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void fallbackHealthPathIsAvailableToAnonymous() throws Exception {
        mvc.perform(get("/healthcheck"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("up"))
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void anonymousProtectedPathUsesBasicEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validAndInvalidBasicCredentialsBehaveDifferently()
            throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("editor"));

        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void editorCannotCallAdminUrl() throws Exception {
        mvc.perform(get("/api/admin/audit")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminUrl() throws Exception {
        mvc.perform(get("/api/admin/audit")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("admin-only"));
    }

    @Test
    void editorIsDeniedByMethodSecurityAfterUrlPermits()
            throws Exception {
        mvc.perform(get("/api/reports/internal")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/internal")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.report").value("restricted"));
    }

    @Test
    void editorCanCreateNoteWithValidCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("note-1"));
    }

    @Test
    void missingCsrfStopsRequestBeforeBasicAuthentication()
            throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden())
                .andExpect(header().exists("X-Demo-Trace"));
    }

    @Test
    void invalidCsrfAlsoReturnsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("editor", "demo-pass"))
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillDoesNotGrantMissingRole()
            throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("admin", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiUnknownRouteIsDeniedBeforeMvc404()
            throws Exception {
        mvc.perform(get("/api/unlisted")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void fallbackUnknownRouteIsAlsoDenied()
            throws Exception {
        mvc.perform(get("/outside")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void distinctRequestsDoNotAutomaticallyShareBasicIdentity()
            throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("editor", "demo-pass")))
                .andExpect(status().isOk());

        // Request mới không mang header/cookie đăng nhập:
        // không được thừa hưởng principal từ request trước.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

**Các test dự kiến kiểm được:** public ở hai chain, 401 do không/không đúng Basic credentials, 403 do URL role, 403 do method security, 403 do CSRF, 201 khi editor + CSRF hợp lệ, fallback deny-all, và không vô ý mang identity Basic từ request trước vào request sau.

Phân tích những test dễ nhầm:

1. **`missingCsrfStopsRequestBeforeBasicAuthentication`** chỉ assertion status/header. Việc quy CSRF là nguyên nhân đến từ chính cấu hình `CsrfFilter` và đối chiếu với test cùng POST có `.with(csrf())`; không suy diễn từ 403 một mình.
2. **`editorIsDeniedByMethodSecurityAfterUrlPermits`** có ý nghĩa vì rule URL là `authenticated()` và service đã có `@PreAuthorize("hasRole('ADMIN')")`; giả thuyết được xác định từ code path. Nếu đổi rule URL thành admin-only, test 403 vẫn xanh nhưng **nguyên nhân sẽ đổi**. Muốn khẳng định tầng cụ thể trong dự án lớn, bổ sung unit test trực tiếp service proxy và event/trace đã được kiểm.
3. **`distinctRequestsDoNotAutomaticallyShareBasicIdentity`** gửi hai request MockMvc khác nhau, không chia sẻ cookie hay session có login. Đây không phải test cho mọi `SecurityContextRepository`; nếu dùng form login/session, phải test login + cookie persistence riêng.
4. **`apiUnknownRouteIsDeniedBeforeMvc404`** cho biết Security rule `denyAll()` xử lý trước khi MVC tìm handler, nên 403 là expected cho authenticated user; status này không chứng minh controller tồn tại.
5. **`X-Demo-Trace`** là header do filter chẩn đoán tạo, không phải một header chuẩn của Spring Security. Nó giúp liên kết log trong lab, nhưng không nên dùng làm proof of authentication hoặc tiết lộ dữ liệu cá nhân.

**Mã là ví dụ được rà soát tĩnh, chưa được biên dịch/chạy trong bài này.** Muốn khẳng định test pass cần chạy `mvn test` hoặc `mvn verify` trên project đúng file và dependency đã trình bày. Tham số Servlet/matcher có thể thay đổi theo ứng dụng thực; không bê nguyên expected statuses sang form login/OIDC/Bearer mà không kiểm entry point.

## 12. Cách tái hiện và đọc log an toàn

Chạy demo bằng Maven:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments=--logging.level.example.tracelab=DEBUG
~~~

Lệnh dành cho Bash/Git Bash với Maven plugin và một application argument; trên shell khác có thể cần quote argument chứa dấu chấm/dấu bằng. Bật thêm các logger ở mục 8 trong môi trường test nếu cần xem chi tiết Spring Security.

Thử GET từ terminal khác:

~~~bash
# Public route, chain #1.
curl -i http://localhost:8080/api/public/ping

# Protected route, không có Basic credentials -> 401.
curl -i http://localhost:8080/api/me

# Basic hợp lệ -> 200.
curl -i -u editor:demo-pass http://localhost:8080/api/me

# URL-level denial -> 403.
curl -i -u editor:demo-pass \
  http://localhost:8080/api/admin/audit

# Method-level denial -> 403 (URL authenticated vẫn cho qua).
curl -i -u editor:demo-pass \
  http://localhost:8080/api/reports/internal

# Fallback chain -> 200 cho healthcheck.
curl -i http://localhost:8080/healthcheck

# Fallback deny-all -> 403 sau authenticated.
curl -i -u editor:demo-pass http://localhost:8080/outside

# CSRF thiếu -> 403, không dùng test này để đo quyền EDITOR.
curl -i -u editor:demo-pass -X POST \
  http://localhost:8080/api/notes
~~~

Bài dùng **mật khẩu lab**: HTTP Basic qua `http://localhost` không phù hợp production vì credential có thể bị lộ trên mạng. Khi triển khai thật phải dùng HTTPS và secret/password handling đúng.

### 12.1. Chuỗi log minh họa và cách diễn giải

Nếu filter chẩn đoán đứng trước CsrfFilter, một request POST không có CSRF token có thể tạo dấu vết cùng cấu trúc:

~~~text
trace=2f1a... phase=before method=POST path=/api/notes
dispatch=REQUEST authKind=none

trace=2f1a... phase=after status=403 authKind=none
~~~

**ID ở đây được rút gọn chỉ để trình bày**, không phải UUID thật sinh ra trong một lần chạy. Hai sự kiện trước/sau cùng một ID, cho biết request đã đến filter chẩn đoán và kết thúc 403, nhưng **không** tự khẳng định filter nào tạo 403. Đối chiếu thêm:

- POST có CSRF hợp lệ + editor nhận **201**.
- POST thiếu CSRF + editor nhận **403**.
- POST có CSRF hợp lệ + admin nhận **403** vì thiếu ROLE_EDITOR.

Khi quan sát đủ các thí nghiệm và `CsrfFilter` debug event, có thể phân biệt CSRF denial khỏi role denial. Không log giá trị token thật.

### 12.2. AuthKind trong log không phải source of truth về quyền

Một `authKind=UsernamePasswordAuthenticationToken` có thể là token chưa authenticated hoặc đã authenticated tùy constructor/provider; log demo chỉ ghi class để **giảm dữ liệu**. Muốn kiểm chính xác phải xem `isAuthenticated`, trust resolver, authorities và quyết định AuthorizationManager **trong một test an toàn**, không đưa mọi thông tin vào production log.

Nếu custom filter đứng **trước** BasicAuthenticationFilter thì `phase=before authKind=none` là bình thường. Nếu ở `phase=after` cũng none khi response 403 do CSRF, đó cũng phù hợp vì Basic auth chưa chạy. Không nói `SecurityContextHolder` “bị mất” chỉ dựa trên hai log đó.

### 12.3. Tìm log FilterChainProxy có hệ thống

Với logger phù hợp, trước tiên quan sát request được “Securing ...” và filter chain processing. Nếu một request không hiện trong log:

- Kiểm liệu nó đến đúng ứng dụng/port/instance.
- Kiểm servlet filter registration, `spring.security.filter.dispatcher-types` và đường dẫn được proxy rewrite.
- Kiểm request có đi qua một static resource handler/CDN trước app hay không.
- Kiểm path/chain matching; log không xuất hiện có thể vì logger chưa bật hoặc sampling, **không** tự suy ra chain bị bỏ qua.

Đừng bật TRACE mọi package rồi đổ toàn bộ log chứa credential vào issue tracker. Dùng trace ID, một test request tối giản và các logger cụ thể trước.

## 13. Sáu cuộc điều tra mẫu từ dấu vết yêu cầu

### Ca A — “POST của EDITOR có role đúng nhưng trả 403”

**Dấu vết:** `method=POST`, `path=/api/notes`, Basic header có gửi, status 403, log `phase=before authKind=none`.

**Giả thuyết:** CSRF chưa hợp lệ, Basic auth có thể chưa chạy. **Thử nghiệm:** request tương tự qua MockMvc, trước tiên `.with(httpBasic(...))`, sau đó thêm `.with(csrf())`. Nếu lần sau 201, tìm lỗi CSRF token repository/form/header/cookie session trên client thật.

**Không sửa bằng:** `csrf.disable()` trên toàn chain, `permitAll("/api/notes")`, hoặc gán role ADMIN cho user.

### Ca B — “GET đã xác thực nhưng trả 401”

**Dấu vết:** `GET /api/me`, không thấy principal ở handler, nhận 401 và `WWW-Authenticate`.

**Giả thuyết:** không có Basic header, password sai, header bị proxy gỡ, app chạy chain khác hoặc BasicAuthenticationFilter chưa được bật ở chain được chọn. **Thử nghiệm:** chạy cặp request credential đúng/sai theo cùng một route, xác nhận chain #1, kiểm provider và entry point.

**Không sửa bằng:** bỏ `authenticated()`; kiểm **authentication mechanism** trước. Nếu browser dùng form login/OIDC, kỳ vọng có thể khác HTTP Basic.

### Ca C — “Editor xem được /api/me nhưng admin route trả 403”

**Dấu vết:** cùng credentials hợp lệ, `/api/me` = 200, `/api/admin/audit` = 403.

**Giả thuyết:** auth thành công, authority không khớp `ROLE_ADMIN`. **Thử nghiệm:** kiểm `UserDetailsService`/mapping và rule. Nhớ `hasRole("ADMIN")` tương đương tìm authority `ROLE_ADMIN` theo prefix mặc định; `hasAuthority("ADMIN")` có nghĩa khác.

**Không sửa bằng:** gán `ROLE_ADMIN` cho mọi user chỉ để làm test pass. 403 có thể chính là hành vi đúng.

### Ca D — “URL check cho qua nhưng service vẫn ném AccessDeniedException”

**Dấu vết:** `GET /api/reports/internal` với editor, authenticated, URL rule `authenticated()`, controller gọi `ReportService` có `@PreAuthorize("hasRole('ADMIN')")`.

**Giả thuyết:** **method security** chặn sau URL authorization. **Thử nghiệm:** test chính Spring-managed `ReportService` với editor/admin; inspect `@EnableMethodSecurity`, proxy, self-invocation và SpEL. Một response 403 đơn lẻ không xác minh chặn tại URL hay method; cần đối chiếu code/log/test.

**Không sửa bằng:** bỏ `@PreAuthorize` mà không kiểm business policy. URL-level authentication chỉ chứng minh user là ai, không cấp quyền quản trị.

### Ca E — “Một URL mới bypass security chain”

**Dấu vết:** `/api/**` được bảo vệ, nhưng `/preview/**` hoặc servlet khác không xuất hiện trong logs của API chain và vẫn trả dữ liệu.

**Giả thuyết:** `securityMatcher("/api/**")` không bao phủ URL mới và không có fallback chain; request có thể không đi qua Spring Security. **Thử nghiệm:** thêm test anonymous/role sai ở URL đó và kiểm tổng số chain, chain order/filter registration.

**Không sửa bằng:** đặt `anyRequest().denyAll()` **bên trong chain /api** rồi nghĩ nó áp dụng ngoài /api. Phải có chain phù hợp/catch-all hoặc policy khác cho route đó.

### Ca F — “Request A đã login, request B lại anonymous”

**Dấu vết:** A có authentication, B trên thread khác không thấy context, hoặc session cookie không tồn tại.

**Giả thuyết:** không gửi cookie/credentials, `STATELESS`/repository không lưu, manual authentication không gọi save, session bị invalidated, async thread không propagate context. **Thử nghiệm:** kiểm cookie jar, SecurityContextRepository, session policy, logout và trace ID riêng cho mỗi request; test login → request với cookie → request không cookie.

**Không sửa bằng:** lưu Authentication trong static field hoặc bật `MODE_GLOBAL`. Làm vậy có thể trộn danh tính giữa những người dùng khác nhau.

## 14. Các trường hợp dễ tạo kết luận sai

### 14.1. “Có response 403 nghĩa là AuthorizationFilter chạy”

Sai. `CsrfFilter` có thể dừng request **trước** authentication/authorization; `@PreAuthorize` hoặc controller advice cũng có thể tạo 403. Cần test nguyên nhân qua các biến được kiểm soát.

### 14.2. “`SecurityContextHolder.getContext()` có object nghĩa là đã đăng nhập”

Sai. Context holder thường có context object ngay cả khi `getAuthentication()` là null; anonymous token có thể có `isAuthenticated() == true` nhưng không tương đương authenticated user. Dùng những predicate mà Spring Security hỗ trợ, không tự suy luận từ existence.

### 14.3. “Không thấy filter log nghĩa là request không đi qua filter chain”

Chưa chắc. Filter có thể nằm sau một filter đã chặn request, logger chưa bật, request được dispatch dưới dispatcher type khác hoặc custom `OncePerRequestFilter` skip async/error. Bật tín hiệu từ chain selection và đặt probe đúng vị trí.

### 14.4. “`permitAll()` nghĩa là bỏ qua mọi security filters”

Sai. `permitAll()` thường cho phép request sau khi vẫn đi qua SecurityFilterChain. `web.ignoring()` hoặc excluded filter registration mới có thể bỏ qua security chain; vì vậy với public assets thông thường nên cân nhắc `permitAll` để giữ security headers.

### 14.5. “Cùng đường dẫn nghĩa là cùng request”

Sai. Method, context path, servlet path, forwarded URI, URL decoding, query string, cookies, `Origin`, CSRF header, `DispatcherType` và chain selection có thể khác. Ghi đủ metadata, nhưng có redaction.

### 14.6. “`@WithMockUser` xác minh login provider”

Sai. `@WithMockUser` hoặc `with(user(...))` đặt mock Authentication, phù hợp kiểm authorization. Để kiểm Basic credentials, use `with(httpBasic(...))`; để kiểm OIDC/JWT/LDAP, cần integration tests đúng giao thức/decoder/provider, không chỉ mock principal.

### 14.7. “Test `forwardedUrl` chứng minh container chạy lại SecurityFilterChain”

Không. `MockMvc.forwardedUrl(...)` có thể chỉ chứng minh MVC quyết định forward. Nếu quyền phụ thuộc FORWARD redispatch/filter registration, cần embedded servlet container integration test qua HTTP thật. Bảo vệ URL nguồn/đích và method/service policy cho dữ liệu nhạy cảm.

### 14.8. “Một status test pass nghĩa là không có data leak”

Sai. Test 200 trên `/api/files/123` chỉ nói request được xử lý; có thể trả tài liệu của người khác. Cần kiểm object owner/tenant ACL, body, cache headers, CORS và mọi đường download/preview.

## 15. Kỹ thuật điều tra nâng cao

### 15.1. SecurityContextRepository và manual authentication

Khi một custom filter xác thực request thủ công và set:

~~~java
SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Đây chỉ là **mảnh cấu hình authentication custom**, chưa lưu context sang request tương lai. Nếu ứng dụng cần phiên đăng nhập, xem lại repository/explicit save semantics và session strategy tương ứng:

~~~java
// Mảnh ý tưởng (cần repository, request, response
// và thiết lập session/security config phù hợp):
securityContextRepository.saveContext(
        context, request, response);
~~~

Đừng copy đoạn này vào mọi custom filter mà không đánh giá session fixation, concurrency và thời điểm response committed. Với API bearer token stateless, **cố ý không giữ session** có thể là chính sách đúng.

### 15.2. Multi-chain + AuthenticationProvider riêng

Một app có chain dành cho `/api/**` dùng JWT và chain browser dùng form login. Khi request vào sai chain, filter đúng cho loại credential có thể **không tồn tại** ở đó; một API nhận Bearer token có thể trả 401 như không đăng nhập dù token hợp lệ nếu JWT resource-server configurer chỉ bật trên chain khác.

Kiểm đầy đủ:

- `@Order` và `securityMatcher` của **từng chain**.
- Authentication filter được enable trong chain đúng.
- Provider/decoder, token format, issuer/audience và principal/authority conversion.
- Entry point và access denied handling khác nhau theo chain.
- CSRF policy của browser vs bearer-only API theo threat model.
- `/login`, OAuth callback, error/actuator/static resources thuộc chain nào.

Trong ví dụ lab, cả hai chain cùng bật HTTP Basic để giảm số biến; production có thể khác.

### 15.3. Distributed tracing và log correlation

Một request có thể đi `gateway → BFF → service`. Mỗi hop có SecurityContext riêng, authentication ở BFF không tự chứng minh service phía sau nhận được user identity đã xác thực. Không forwarding raw principal/role headers do client tự tạo trừ khi có cơ chế tin cậy giữa các services và verification.

Dùng OpenTelemetry/Micrometer tracing phù hợp để gắn trace/span IDs, nhưng **trace ID là công cụ quan sát, không phải bằng chứng danh tính**. Với distributed systems, cần phân biệt `401 từ gateway`, `403 từ downstream service`, `403 từ CSRF ở BFF`; log hop nào trả status và các biến tương ứng.

### 15.4. Kiểm thứ tự custom filters

Một filter xử lý custom token nên có vị trí nhất quán tương ứng các filter authentication/context. Nếu đặt filter **trước `SecurityContextHolderFilter`** rồi cố set context, context sau đó có thể bị thay thế hoặc không được duy trì như mong đợi. Nếu đặt filter chẩn đoán quá muộn, nó bỏ lỡ request bị CSRF/authentication filter chặn.

Dùng `addFilterBefore`/`addFilterAfter` với lớp anchor rõ ràng, nhưng vẫn kiểm **filter order thực tế** và có nhiều chains hay không. Không đoán thứ tự chỉ bằng thứ tự các lệnh `.addFilterBefore()` trong source.

### 15.5. AuthenticationTrustResolver và anonymous

Khi viết business logic có nhánh “user đã login?”, không chỉ dựa vào `isAuthenticated()` trên token. Spring Security có `AuthenticationTrustResolver` và các authorization expressions tương ứng để phân biệt anonymous/remember-me/fully-authenticated khi phù hợp. Một request anonymous trên public endpoint có thể có một object Authentication, nhưng không được dùng object đó để cấp quyền trên tài liệu riêng.

## 16. Phương pháp tổ chức test và quan sát khi sửa lỗi

Một quy trình “từ trace đến regression test”:

1. **Tái hiện tối thiểu** với đúng method, path và credential presence; tạo một trace ID server-side.
2. **Chụp baseline**: status, response headers, selected chain, filter phase, authentication kind và policy expected.
3. **Đặt một giả thuyết** về filter, chain matcher, CSRF, entry point, role, method security hoặc context lifecycle.
4. **Thay một biến mỗi lần**: có/không CSRF, đúng/sai password, admin/editor, `/api`/fallback, request mới với cookie/no cookie.
5. **Viết test âm tính và dương tính** cho cùng policy: user đúng được, user sai bị từ chối. Không chỉ test status thất bại.
6. **Kiểm service/proxy riêng** nếu nghi ngờ method security và kiểm controller/HTTP chain nếu nghi ngờ URL auth.
7. **Sửa cấu hình hẹp nhất**: không tắt CSRF, không bỏ auth, không chuyển mọi URL thành public chỉ để xử lý một lỗi.
8. **Chạy toàn bộ regression**: login, logout, session, CSRF, roles, CORS, error/forward dispatch, object ACL và data response khi liên quan.
9. **Kiểm staging qua proxy thật** để phát hiện headers/cookies/servlet mapping khác MockMvc.
10. **Dọn debug logging** sau khi có kết luận; lưu report đã redacted với link test và artifact version.

### 16.1. Một mẫu báo cáo điều tra có thể kiểm chứng

~~~text
Title: POST /api/notes rejects EDITOR with 403
Environment: staging, artifact <approved-release-id>
Observed: POST /api/notes, Basic credential supplied, CSRF absent
Selected chain: API chain (securityMatcher /api/**)
Evidence: trace before/after; CsrfFilter rejection in isolated test
Controlled test A: EDITOR + no CSRF -> 403
Controlled test B: EDITOR + valid CSRF -> 201
Controlled test C: ADMIN + valid CSRF -> 403
Cause: request lacked CSRF token; not a missing ROLE_EDITOR
Fix: frontend obtains/submits the configured CSRF token with session
Regression: MockMvc tests for valid/missing/invalid CSRF, wrong role
Sensitive data: omitted from ticket/log
~~~

Đây là **mẫu kết luận giả định**; thay bằng dữ liệu thật sau điều tra. Đặc biệt, không chép raw HTTP Authorization header/CSRF token vào ticket để “chứng minh”.

### 16.2. Khi nào cần integration test ngoài MockMvc?

- Filter registration theo `DispatcherType.FORWARD`, `ASYNC`, `ERROR` hoặc embedded container khác.
- Session cookie/SameSite/Secure qua HTTPS ingress/reverse proxy.
- OAuth2 Login redirect/callback, OIDC state/nonce, real JWT decoder/JWKS, LDAP bind.
- Multiple servlet paths, gateway rewrite, forwarded headers trust boundary.
- Distributed session store, security-context propagation across executor/thread.
- Cache/CDN, file download, user ownership và security headers sau proxy.

MockMvc giúp cô lập lỗi Spring MVC/Security, nhưng không thay tất cả hành vi container, browser và upstream/downstream systems.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `securityMatcher("/api/**")` và `requestMatchers("/api/**")` giống nhau không?  
**Không.** Cái đầu chọn SecurityFilterChain; cái sau áp dụng authorization trong chain đã chọn.

**Câu 2.** Một request POST có ROLE_EDITOR nhưng trả 403. Nên tăng quyền cho user ngay không?  
**Không.** Kiểm CSRF trước; chạy cùng request với CSRF hợp lệ để phân biệt CSRF và role.

**Câu 3.** `Authentication` null ở filter đứng trước BasicAuthenticationFilter có chứng minh Basic auth không hoạt động không?  
**Không.** Authentication chưa được thực hiện ở thời điểm đó.

**Câu 4.** `AnonymousAuthenticationToken.isAuthenticated()` có thể true. Nó có tương đương login thành công không?  
**Không.** Spring Security dùng trust resolver/authorization semantics để phân biệt anonymous.

**Câu 5.** Một URL vào API chain, nhưng `anyRequest().denyAll()` trong fallback chain có áp dụng cho nó không?  
**Không.** Chỉ chain đầu tiên được chọn áp dụng.

**Câu 6.** Vì sao `GET /api/reports/internal` có thể 403 dù URL rule là `authenticated()`?  
**Vì** service sau đó có `@PreAuthorize("hasRole('ADMIN')")`.

**Câu 7.** `@WithMockUser` test 200 đã chứng minh Basic password hoặc JWT signature đúng chưa?  
**Chưa.** Mock identity không đi qua authentication provider/decoder thật.

**Câu 8.** Thấy `FilterChainProxy` log “Securing ...” có chắc AuthorizationFilter cho phép không?  
**Không.** Đó chỉ là bằng chứng đi vào security processing, không phải quyết định cuối.

**Câu 9.** Vì sao một request trên thread `@Async` không thấy SecurityContext?  
**Vì** ThreadLocal context không tự propagate. Phải dùng mechanism propagation đúng hoặc truyền identity/policy có kiểm soát.

**Câu 10.** `denyAll()` của một chain chỉ match `/api/**` có bảo vệ `/preview/**` không?  
**Không.** Cần chain khác/fallback bảo vệ URL ngoài phạm vi.

**Câu 11.** POST thiếu CSRF nhận 403, POST có CSRF nhận 201. Có thể kết luận nguyên nhân mạnh hơn chưa?  
**Có**, nếu các điều kiện khác giữ nguyên và filter logs/config xác nhận `CsrfFilter` xử lý như policy. Vẫn cần xác định vì sao client không gửi token đúng.

**Câu 12.** Request ID có chứng minh user đã authenticated không?  
**Không.** Nó chỉ là công cụ correlation/logging.

## 18. Checklist kết thúc điều tra và ghi nhớ

- [ ] Xác nhận **method, normalized internal path, context/servlet path, dispatcher, selected instance và trace ID**.
- [ ] Xác định **SecurityFilterChain** được chọn (theo `@Order` + `securityMatcher`) và có fallback bảo vệ các URL ngoài phạm vi.
- [ ] Kiểm đúng thứ tự request matchers, method, role/authority prefix, URL có owner/tenant rule hay không.
- [ ] Phân biệt **authentication failure (401/redirect)**, **authorization denial (403)**, **CSRF denial (403)** và MVC 404/405.
- [ ] Theo dõi `SecurityContextHolderFilter`, filter xác thực, `AnonymousAuthenticationFilter`, `AuthorizationFilter` và method-security proxy tại điểm quyết định.
- [ ] Đừng coi principal null **trước authentication** hoặc **sau request** là bằng chứng mất context trong suốt request.
- [ ] Kiểm `SecurityContextRepository`, session save semantics và cookie khi một login cần kéo dài nhiều requests.
- [ ] Kiểm context propagation cho `@Async`, executor, message worker khi luồng bị đổi.
- [ ] Đặt trace filter đúng chỗ, có correlation ID an toàn, không log credentials/token/PII; tắt TRACE sau khi hoàn thành.
- [ ] Viết **positive + negative regression tests**: anonymous, wrong password, wrong role, CSRF, multi-chain, service `@PreAuthorize`, request mới không mang credentials.
- [ ] Khi có proxy/OIDC/LDAP/JWT, kiểm thêm integration ở đúng môi trường, không chỉ MockMvc.
- [ ] Chỉ sửa cấu hình sau khi giả thuyết được tái hiện; không dùng `permitAll()`/`csrf.disable()` để che nguyên nhân.

**Kết luận:** điều tra lỗi Spring Security Servlet hiệu quả cần đi từ **dấu vết request → chain selection → thứ tự filter → authentication/context → URL và method authorization → kết quả MVC/service**. Một response 401/403 không nói hết nguyên nhân. Khi mỗi giả thuyết được kiểm bằng request đối chứng và regression test, ta có thể sửa chính xác mà không vô tình mở thêm quyền hoặc làm rò danh tính giữa các phiên.
