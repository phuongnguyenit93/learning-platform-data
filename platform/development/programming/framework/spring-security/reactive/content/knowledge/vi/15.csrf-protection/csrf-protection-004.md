# WebSessionServerCsrfTokenRepository và lưu token trong phiên

## 1. Bài toán: vì sao token CSRF phải được liên kết với một phiên?

Trong một ứng dụng Spring WebFlux có giao diện trình duyệt, người dùng có thể đã được xác thực nhờ cookie đăng nhập, HTTP Basic credentials do browser nhớ hoặc một cơ chế khác mà browser tự đưa vào request. Khi người dùng truy cập một trang ngoài ý muốn, trang đó có thể khiến browser phát request tới ứng dụng. Nếu server chỉ kiểm tra credentials do browser tự gắn, một thao tác thay đổi dữ liệu có thể bị kích hoạt mà không do người dùng chủ động yêu cầu. Đó là **Cross-Site Request Forgery (CSRF)**.

Một cách phòng thủ phổ biến là **Synchronizer Token Pattern**:

1. Server tạo một token có giá trị khó đoán và giữ **giá trị kỳ vọng** ở phía server, thường gắn với phiên của browser.
2. Ứng dụng hợp lệ cung cấp token cho trang/form hoặc JavaScript trong origin tin cậy.
3. Khi gửi POST/PUT/PATCH/DELETE, client gửi token trong **header hoặc tham số form**, không chỉ dựa vào cookie được browser tự gửi.
4. Server tải token kỳ vọng và so sánh với token client trình bày. Nếu thiếu hoặc sai, request bị từ chối trước khi chạy thao tác nghiệp vụ.

Trong Spring Security Reactive, lớp **`WebSessionServerCsrfTokenRepository`** chính là implementation của `ServerCsrfTokenRepository` dùng **`WebSession`** để lưu/tải token CSRF kỳ vọng. Nó là lựa chọn lưu trữ **mặc định** cho CSRF trong cấu hình Spring Security WebFlux thông thường.

Điểm mấu chốt:

> `WebSessionServerCsrfTokenRepository` lưu **token chống CSRF**, không phải username/password hay “bản sao Authorization header”. Nó cũng không phải cơ chế tự đăng nhập hoặc tự cấp quyền cho request.

### Bạn sẽ học được

- Giải thích rõ CSRF token, token repository, `WebSession` và session ID cookie liên hệ với nhau thế nào.
- Đọc đúng hợp đồng `generateToken`, `saveToken`, `loadToken` và ý nghĩa của một `Mono` không phát giá trị.
- Hiểu mặc định Spring Security WebFlux, cơ chế tạo token khi cần và sự khác nhau giữa token kỳ vọng đã lưu với token đã được masking để render.
- Biết cấu hình `ServerHttpSecurity.csrf` với `WebSessionServerCsrfTokenRepository`, dùng `setSessionAttributeName` hoặc đặt tên header/form field khi cần.
- Tự chạy một project Java 17+, Spring Boot, Gradle, WebFlux + Basic + CSRF lưu WebSession, và kiểm thử HTTP 200/401/403.
- Chẩn đoán lỗi mất cookie, hết hạn phiên, CSRF token cũ sau logout, reverse proxy, nhiều instance và hành vi React/SPA.
- Phân biệt `WebSessionServerCsrfTokenRepository` với `CookieServerCsrfTokenRepository` và các vấn đề của API stateless.

Bài thuộc nhóm **Bảo vệ CSRF** của module Spring Security - reactive; ví dụ chỉ dùng credentials local để minh họa. Không dùng mật khẩu demo hay HTTP không TLS trên Internet.

## 2. Những khái niệm phải phân biệt

| Khái niệm | Bản chất | Vai trò trong việc bảo vệ CSRF |
| --- | --- | --- |
| `CsrfToken` | Dữ liệu gồm `headerName`, `parameterName`, `token` | Mô tả tên field và giá trị token |
| `ServerCsrfTokenRepository` | Giao diện Reactive | Tạo, lưu, tải **token kỳ vọng** |
| `WebSessionServerCsrfTokenRepository` | Repository dùng `WebSession` | Lưu token như một attribute trong session |
| `WebSession` | Đối tượng phiên của Spring WebFlux | Chứa dữ liệu phiên và có ID, timeout, lifecycle |
| Session ID cookie (thường `SESSION`) | Giá trị browser lưu để server tìm lại WebSession | Gắn request mới với đúng phiên đã giữ token |
| `CsrfWebFilter` | WebFilter của Spring Security | Phối hợp kiểm tra token khi request cần CSRF protection |
| `ServerCsrfTokenRequestHandler` | Chiến lược trình bày/đọc token ở request | Expose `Mono<CsrfToken>`, resolve token do client gửi |
| `XorServerCsrfTokenRequestAttributeHandler` | Request handler mặc định từ Spring Security 6 | Mask/unmask token để giảm rủi ro BREACH |
| `ServerSecurityContextRepository` | Lưu/tải `SecurityContext` | **Khác** repository CSRF; có thể dùng WebSession hoặc no-op |
| `ReactiveSecurityContextHolder` | Reactor Context của subscription hiện tại | Đọc authentication ở downstream, không phải kho token CSRF |

Một ứng dụng có thể cấu hình `NoOpServerSecurityContextRepository` để **không lưu authentication qua phiên** nhưng vẫn dùng `WebSessionServerCsrfTokenRepository` để giữ CSRF token trong phiên. Vì vậy, “HTTP Basic xác thực mỗi request” không kéo theo “không có WebSession nào được tạo”.

Ngược lại, nếu server lưu SecurityContext vào session mà bạn disable CSRF tùy tiện, browser dùng cookie đăng nhập có thể dễ bị request giả mạo. Hãy đánh giá **authentication persistence** và **CSRF protection** như hai phần khác nhau.

## 3. Cơ chế Synchronizer Token Pattern với WebSession

Hãy xem luồng đúng:

~~~text
Browser                                          Spring WebFlux + Security
   |                                                        |
   | 1. GET /csrf (đã xác thực hoặc theo chính sách)         |
   |------------------------------------------------------->|
   |                                                        |
   |     CsrfWebFilter + token request handler               |
   |           |                                            |
   |           +--> Repository.loadToken(exchange)           |
   |           |      (nếu chưa có token)                    |
   |           +--> Repository.generateToken(exchange)       |
   |           +--> Repository.saveToken(exchange, token)    |
   |                  |                                     |
   |                  v                                     |
   |           WebSession chứa expected token                |
   |                                                        |
   | 2. Response: token trình bày + Set-Cookie SESSION=...   |
   |<-------------------------------------------------------|
   |                                                        |
   | 3. POST /api/note                                      |
   |    Cookie: SESSION=<id>                                |
   |    X-CSRF-TOKEN: <token-đã-được-cấp>                   |
   |------------------------------------------------------->|
   |                                                        |
   |     WebSessionServerCsrfTokenRepository.loadToken       |
   |       --> expected token của cùng session               |
   |     Request handler resolve/unmask presented token       |
   |     Compare --> token hợp lệ?                           |
   |                                                        |
   | 4. Có --> qua authentication/authorization, chạy handler|
   |    Không --> chặn request, thường HTTP 403               |
   |<-------------------------------------------------------|
~~~

Đây là sơ đồ khái niệm. Thứ tự thực thi thực tế phụ thuộc WebFilter chain, authentication method và Spring Security version; **không phải mọi GET đều sinh session/token** vì framework có cơ chế tạo/đọc token khi cần.

### 3.1. Hai thứ phải đến từ cùng ngữ cảnh

Đối với repository này, một POST thành công thường cần **cả**:
- Cookie session ID để server tìm ra `WebSession` đang giữ expected token.
- Giá trị token CSRF đã được ứng dụng cấp để client gửi trong header hoặc form parameter.

Nếu chỉ gửi token nhưng bỏ cookie phiên, repository có thể tìm thấy **session khác hoặc session mới** không chứa expected token. Nếu chỉ gửi cookie mà bỏ token, server vẫn không có bằng chứng request được tạo từ ngữ cảnh hợp lệ. Cả hai trường hợp thường bị 403 trên method cần bảo vệ.

**CSRF token không phải session ID**. Không dùng giá trị SESSION cookie thay cho `X-CSRF-TOKEN`, và cũng không dùng token CSRF như Bearer token để xác thực danh tính.

### 3.2. Tại sao cần session ở server?

Synchronizer token đặt giá trị kỳ vọng ở phía server. Browser chỉ giữ một session identifier để server định vị đúng dữ liệu, còn ứng dụng hợp lệ truyền token theo cách website ngoài origin không thể tùy tiện biết.

Với nhiều instance:
- Nếu session chỉ ở bộ nhớ của một instance, request sau được đưa tới instance khác có thể không tìm thấy expected token.
- Có thể dùng sticky session theo thiết kế hoặc Spring Session với Redis/nguồn lưu chung để các instance tìm cùng WebSession.
- Cookie phiên và datastore phải có timeout, khóa truy cập, quản lý logout và tính nhất quán phù hợp.

**Không lưu toàn bộ token/session vào log hoặc URL.** Log có thể ghi loại lỗi, route, correlation ID và status, nhưng không ghi raw token.

## 4. API chính xác của WebSessionServerCsrfTokenRepository

Package:

~~~text
org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository
~~~

Lớp implements:

~~~java
// Chữ ký rút gọn để giải thích; không phải file Java độc lập.
public class WebSessionServerCsrfTokenRepository
        implements ServerCsrfTokenRepository {

    public Mono<CsrfToken> generateToken(ServerWebExchange exchange);
    public Mono<Void> saveToken(ServerWebExchange exchange,
                                CsrfToken token);
    public Mono<CsrfToken> loadToken(ServerWebExchange exchange);

    public void setParameterName(String parameterName);
    public void setHeaderName(String headerName);
    public void setSessionAttributeName(String sessionAttributeName);
}
~~~

Phương thức `saveToken` cho phép token bằng `null` để **xóa** giá trị đã lưu theo hợp đồng; đây là quy ước Java API, không phải giá trị phát ra từ một `Mono.just(null)`. Trong Reactor không dùng `Mono.just(null)` vì Publisher không chấp nhận một item null.

### 4.1. generateToken(exchange)

- Tạo một đối tượng `CsrfToken` mới với giá trị khó đoán.
- Chưa có nghĩa token đã được lưu bền vững.
- Không tự “xác nhận request đã được bảo vệ”.
- Trong Spring Security, request handler/repository được phối hợp qua `CsrfWebFilter`, không cần controller tự gọi generate cho mọi GET.

### 4.2. saveToken(exchange, token)

- Lưu một token được cung cấp vào WebSession của `ServerWebExchange`.
- Theo hợp đồng, `saveToken(exchange, null)` có nghĩa **xóa token** khỏi repository.
- Trả `Mono<Void>`: publisher hoàn thành sau khi thao tác reactive tương ứng được thực hiện.
- Để lưu thực sự, phải để framework subscribe vào publisher như một phần pipeline. Tự gọi method rồi bỏ qua Mono sẽ không đảm bảo hiệu ứng xảy ra.

### 4.3. loadToken(exchange)

- Tải token kỳ vọng từ WebSession đang gắn với exchange.
- Nếu session chưa có token được lưu, kết quả là **`Mono.empty()`** thay vì một đối tượng token giả.
- Trả token đã lưu; không có trách nhiệm đọc header token do client trình bày.
- Dùng để đối chiếu với token request handler đã đọc từ request trong luồng xử lý CSRF.

### 4.4. setParameterName, setHeaderName, setSessionAttributeName

Ba setter thay đổi **ba phần khác nhau**:

| API | Điều khiển | Ví dụ |
| --- | --- | --- |
| `setParameterName("_csrf")` | Tên field form mà client gửi | `_csrf=<token>` |
| `setHeaderName("X-CSRF-TOKEN")` | Tên HTTP request header dành cho token | `X-CSRF-TOKEN: ...` |
| `setSessionAttributeName("DEMO_CSRF_TOKEN")` | Key trong `WebSession.attributes` giữ expected token | Không phải tên cookie hoặc HTTP header |

Ví dụ:

~~~java
// Đoạn minh họa bên trong @Bean.
WebSessionServerCsrfTokenRepository repo =
        new WebSessionServerCsrfTokenRepository();

repo.setParameterName("_csrf");
repo.setHeaderName("X-CSRF-TOKEN");
repo.setSessionAttributeName("DEMO_CSRF_TOKEN");
~~~

Nếu đổi tên header/parameter, phải đồng bộ frontend, HTML forms và các test; nếu đổi key attribute trong phiên khi triển khai có người dùng đang hoạt động, có thể cần cấp lại token phù hợp vì dữ liệu cũ nằm dưới key cũ.

**Không thay tên thuộc tính session chỉ để “tăng bảo mật”.** Bảo mật phụ thuộc entropy token, giới hạn phân phối token, việc so sánh đúng, bảo vệ session và các lớp XSS/CSRF khác; giấu tên attribute không phải một cơ chế bảo mật đáng tin.

## 5. CSRF protection mặc định trong Spring Security WebFlux

Ở Spring Security WebFlux, **CSRF protection được bật mặc định** trong SecurityWebFilterChain thông thường. Repository mặc định là `WebSessionServerCsrfTokenRepository`.

Đa số ứng dụng **không cần** tự cấu hình repository nếu muốn giữ hành vi mặc định:

~~~java
@Bean
SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là snippet, cần đặt trong class `@Configuration` cùng imports Spring Security; nếu ứng dụng có form login hoặc Resource Server, authentication cần được cấu hình phù hợp.

Muốn thể hiện rõ repository sẽ dùng, bạn có thể viết:

~~~java
.csrf(csrf -> csrf
        .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
~~~

Đoạn trên thuộc `ServerHttpSecurity`, là cấu hình **reactive**. **Đừng** dùng `HttpSessionCsrfTokenRepository` (Servlet) hoặc `HttpSecurity` của Spring MVC để cấu hình WebFlux; hai môi trường có hợp đồng request/filter khác nhau.

### 5.1. Method nào cần CSRF?

Theo matcher mặc định của Spring Security:
- Thường **không cần token**: GET, HEAD, OPTIONS, TRACE.
- Thường **cần token**: POST, PUT, PATCH, DELETE và các method unsafe khác.

Thực tế route có dùng POST để **đọc** cũng không tự được miễn CSRF; ngược lại GET mà lại xóa dữ liệu là thiết kế sai vì framework tin GET là safe method. Hãy giữ GET/HEAD không có side effects.

### 5.2. CSRF và authentication là hai quyết định độc lập

Một request POST có username/password đúng nhưng thiếu CSRF token có thể nhận 403.
Một request POST thiếu credentials **và** CSRF token cũng có thể nhận 403 nếu `CsrfWebFilter` chặn trước tầng authentication.
Một GET thiếu credentials ở route bảo vệ thường bị authentication entry point trả 401.
Một POST có token hợp lệ và credentials đúng nhưng thiếu role vẫn có thể bị authorization từ chối 403.

Không suy luận nguồn lỗi chỉ từ HTTP status 403; cần kiểm tra policy CSRF, role và filter chain.

## 6. Deferred token, Reactor Mono và vòng đời subscribe

Một lý do Spring Security Reactive sử dụng `Mono<CsrfToken>` là token có thể được tạo/tải theo **nhu cầu thực sự**. Khi chỉ render một GET thông thường không cần token và không có code subscribe vào token, không nên giả định repository lập tức tạo WebSession và ghi token.

Trường hợp website cần biểu mẫu hoặc SPA cần lấy token:
1. Một page/template/endpoint đọc `Mono<CsrfToken>` từ exchange.
2. WebFlux subscribe vào publisher như một phần xử lý response.
3. Repository có thể tải token cũ hoặc tạo/lưu token mới.
4. Client nhận token được trình bày qua request handler.

**Điểm cần tránh:** `ServerWebExchange.getAttribute(CsrfToken.class.getName())` có thể trả **một Mono**, không phải `CsrfToken` đã sẵn ngay. Đừng cast attribute trực tiếp thành `CsrfToken` hay gọi `block()` trong controller.

Ví dụ đúng:

~~~java
// Trong một @RestController, trả Mono để WebFlux subscribe.
@GetMapping("/csrf")
Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
                "CSRF token attribute unavailable"));
    }

    return token.map(value -> Map.of(
            "headerName", value.getHeaderName(),
            "token", value.getToken()));
}
~~~

Đây là snippet của một controller, cần imports `CsrfToken`, `ServerWebExchange`, `Mono`, `Map` và các annotation. Phần demo sau đưa toàn bộ files để có thể chạy.

### 6.1. Vì sao không tự subscribe?

Anti-pattern:

~~~java
// SAI: subscription tách khỏi response lifecycle.
tokenMono.subscribe(token -> someSharedHolder.set(token.getToken()));
return Mono.just("done");
~~~

Đoạn này minh họa lỗi kiến trúc; `someSharedHolder` không phải class có thật. Subscription thủ công có thể tách error handling/cancellation khỏi request và tạo rủi ro state toàn cục. Hãy compose `tokenMono.map(...)`/`flatMap(...)` rồi trả Publisher.

**Reactor Context** là thứ khác với **WebSession**: một thứ gắn với reactive subscription, một thứ giữ dữ liệu phiên giữa request. Đừng dùng ThreadLocal Servlet hoặc một biến static để thay `ServerCsrfTokenRepository`.

## 7. Raw token trong session và token được hiển thị sau XOR masking

Spring Security 6.x thường dùng `XorServerCsrfTokenRequestAttributeHandler` theo mặc định để giảm nguy cơ **BREACH**. Đây là sự khác biệt quan trọng khi người học thấy token của endpoint `/csrf` không giống giá trị mà repository đang lưu.

Hãy phân biệt:

- **Expected/raw token:** giá trị `CsrfToken` repository giữ trong `WebSession` để kiểm tra.
- **Presented token:** giá trị request handler có thể đã masking khi được đưa vào HTML/form/header phía client.
- **Resolved token:** giá trị handler rút ra từ request (có thể unmask) để so sánh với raw expected token.

Một mô hình khái quát:

~~~text
WebSessionServerCsrfTokenRepository
          |
          +--> raw expected token trong WebSession
                      |
                      v
              XOR request handler
                      |
                      +--> token trình bày cho client
                                 |
                                 v
                       Form/JavaScript gửi lại
                                 |
                                 v
              Handler resolve/unmask token
                                 |
                                 v
             So sánh với expected token
~~~

Khi lấy token ở `exchange.getAttribute(CsrfToken.class.getName())` qua bộ xử lý mặc định, giá trị trả cho client có thể đã được masking; **client hãy gửi chính giá trị được cấp**, không tự “unmask” theo thuật toán tự chế, và không đi đọc thẳng session attribute để làm token request.

Trong nhiều trường hợp, cùng expected token trong session có thể được trình bày thành những chuỗi masked khác nhau giữa các response. Đừng so sánh chuỗi token cấp cho browser ở hai lần GET rồi kết luận session token đã thay đổi chỉ vì chúng không giống nhau.

### 7.1. Tại sao không vô hiệu XOR để đơn giản hóa?

Có API `ServerCsrfTokenRequestAttributeHandler` không masking. Tuy nhiên, đổi handler này chỉ để “làm chuỗi đẹp” có thể làm giảm lớp phòng vệ trước BREACH ở một số trường hợp. Nếu một SPA dùng cookie CSRF token raw với JS, cần thiết kế request handler phù hợp **cho đúng version và mô hình client**; không tùy tiện dùng recipe Servlet với API WebFlux.

### 7.2. CSRF token khác access token

CSRF token không cho phép client tự xưng là user. Một request có CSRF token hợp lệ nhưng credentials sai hoặc không đủ quyền vẫn không được chạy thao tác. Ngược lại Bearer token hợp lệ không tự chứng minh một browser không thể bị CSRF nếu browser có cơ chế tự gửi token/cookie theo thiết kế.

## 8. Lưu CSRF token trong WebSession tạo cookie nào?

Ở WebFlux mặc định, session ID thường được trao đổi qua cookie tên `SESSION` (tên có thể được cấu hình). Khi token được lưu và session được khởi tạo, response có thể chứa:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; HttpOnly; SameSite=Lax
~~~

Các thuộc tính/giá trị cụ thể của `Set-Cookie` thay đổi theo cấu hình `CookieWebSessionIdResolver`, Spring Boot, profile và môi trường HTTPS. Cookie session ID **không chứa raw CSRF token** theo cơ chế repository này.

Một vài hệ quả:
- Cookie session ID vẫn cần bảo vệ bằng `Secure` trên HTTPS production, `HttpOnly` và SameSite/Domain/Path hợp lý.
- Cookie mặc định của WebFlux **không nhất thiết** là `JSESSIONID` của Servlet.
- Mất cookie có thể dẫn tới repository không tìm được token đã lưu.
- Khi WebSession hết hạn hoặc invalidated, expected token gắn với session không còn.
- Browser gửi lại cookie không tự động đưa token vào header/form. Client phải gửi **hai kênh** phù hợp.

### 8.1. Đừng nhầm với CookieServerCsrfTokenRepository

| Tiêu chí | WebSessionServerCsrfTokenRepository | CookieServerCsrfTokenRepository |
| --- | --- | --- |
| Nơi giữ expected token | WebSession phía server | Cookie phía browser |
| Cần session ID cookie để tìm expected token | Thường có | Không vì riêng repository token này |
| Trường hợp sử dụng | Browser/form login, stateful session, ứng dụng có WebSession | Một số SPA/JavaScript clients cần giao tiếp cookie-token |
| Cookie liên quan | Thường `SESSION`/cấu hình resolver | Thường `XSRF-TOKEN` |
| Header client thường gửi | `X-CSRF-TOKEN` | `X-XSRF-TOKEN` theo mặc định cookie repo |
| Bảo mật XSS | Cần bảo vệ token endpoint/view và JS | Cookie token JS-readable (nếu bật) có trade-off |
| Timeout | Gắn lifecycle phiên server | Gắn chính sách cookie/token riêng |

`CookieServerCsrfTokenRepository.withHttpOnlyFalse()` có thể cần cho JS đọc cookie; **không** vì vậy mà tắt HttpOnly của **SESSION cookie**. Cả hai loại repository vẫn cần một request header/form field không được tự động thêm để chống CSRF; chỉ để browser tự gửi cookie token mà không thêm một giá trị do ứng dụng chủ động gửi **không tạo đủ synchronizer-token protection**.

### 8.2. Stateless API có nên dùng session token?

Một API chỉ nhận token do service-to-service/mobile client chủ động gửi, không có browser ambient credentials, có thể đánh giá xem CSRF có cần thiết không theo threat model. Nếu thật sự không có nguy cơ browser tự gửi thông tin xác thực, có thể có lý do để không tạo WebSession chỉ vì CSRF.

Tuy nhiên, **đừng tắt CSRF chỉ vì ứng dụng có chữ REST hoặc HTTP Basic**. Browser có thể nhớ Basic credentials và tự gửi chúng; form login/session cookie càng cần xem CSRF. Chọn token repository dựa trên mô hình client thực tế.

## 9. Dự án chạy được: Java 17 + Spring Boot WebFlux + WebSession CSRF

Ta xây một demo có:
- HTTP Basic để thử authentication ở mỗi request; không lưu SecurityContext vào session.
- `WebSessionServerCsrfTokenRepository` được cấu hình tường minh.
- Session attribute name `DEMO_CSRF_TOKEN` để dễ quan sát trong bài.
- GET `/csrf` cấp token và tạo/lưu expected token khi được request.
- GET `/session/csrf-stored` để biết **phiên hiện tại có token hay không**, nhưng không trả raw token.
- GET `/api/note` đọc state.
- POST `/api/note` thay đổi state, phải có CSRF token.
- POST `/session/end` invalidate WebSession hiện tại; khi client vẫn có Basic credentials, request kế tiếp vẫn có thể được xác thực nhưng token cũ mất hiệu lực.

**Không dùng demo password trong sản phẩm thật.** HTTP Basic chỉ an toàn qua HTTPS/TLS; Base64 không phải mã hóa. Repository WebSession giúp minh họa CSRF, không thay thế authentication/authorization.

### 9.1. Cấu trúc file

~~~text
webflux-session-csrf/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── WebSessionCsrfRepositoryTest.java
        └── WebFluxCsrfSecurityTest.java
~~~

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-session-csrf'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng JDK 17+, Gradle tương thích hoặc Gradle Wrapper của dự án. Spring Boot BOM cung cấp version tương thích cho Spring Security 6.x/Framework/Reactor theo phiên bản Boot đã chọn. Khi triển khai production, cập nhật bản vá và dùng nhánh còn được tổ chức hỗ trợ; version này dùng để mô tả một cấu hình cụ thể.

### 9.4. application.yml

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        http-only: true
        same-site: lax
        secure: false

spring:
  application:
    name: webflux-session-csrf
~~~

`secure: false` **chỉ dành cho demo HTTP localhost**. Trong production, phải dùng HTTPS, `secure: true`, kiểm soát CORS và không để session cookie đi qua kênh không được bảo vệ.

`server.reactive.session.timeout: 10m` là timeout không hoạt động của WebSession, **không tự có nghĩa token luôn sống đúng 10 phút từ thời điểm tạo** hoặc browser cookie luôn hết hạn sau 10 phút. Nếu session bị invalidated hoặc không còn đúng store, CSRF token cũ không dùng được.

### 9.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String CSRF_ATTRIBUTE = "DEMO_CSRF_TOKEN";

    @Bean
    WebSessionServerCsrfTokenRepository csrfTokenRepository() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();
        repository.setSessionAttributeName(CSRF_ATTRIBUTE);
        repository.setHeaderName("X-CSRF-TOKEN");
        repository.setParameterName("_csrf");
        return repository;
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            WebSessionServerCsrfTokenRepository csrfTokenRepository) {
        return http
                .authorizeExchange(ex -> ex
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(csrf -> csrf
                        .csrfTokenRepository(csrfTokenRepository))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

**Giải thích:**
1. `WebSessionServerCsrfTokenRepository` là **bean riêng** chỉ để minh họa repository, được chuyển vào `ServerHttpSecurity.csrf`, không cần gọi generate/save trong controller.
2. `setSessionAttributeName` đặt key của expected token bên trong WebSession; việc đổi key này không tự đổi tên cookie.
3. `anyExchange().authenticated()` yêu cầu Basic credentials cho mọi endpoint demo.
4. `NoOpServerSecurityContextRepository` không lưu authentication qua WebSession giữa request, dù CSRF token vẫn được lưu ở đó.
5. `csrfTokenRepository` là chiến lược lưu **expected CSRF token**, còn việc đọc masked token từ header/form do request handler mặc định quản lý.
6. `{noop}localpass` là password dạng rõ, chỉ để kiểm thử local. Production dùng PasswordEncoder thích nghi (BCrypt/Argon2 theo policy), HTTPS, rate limit và quản lý user an toàn.

**Không tắt CSRF để sửa 403** khi một client gửi POST thiếu token. Lỗi 403 trong trường hợp đó là phản hồi chủ động.

### 9.7. DemoController.java

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final AtomicReference<String> note =
            new AtomicReference<>("initial");

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is missing"));
        }

        return token.map(t -> Map.of(
                "headerName", t.getHeaderName(),
                "parameterName", t.getParameterName(),
                "token", t.getToken()));
    }

    @GetMapping("/session/csrf-stored")
    public Mono<Map<String, Boolean>> csrfStored(
            ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> Map.of(
                        "stored", session.getAttribute(
                                SecurityConfig.CSRF_ATTRIBUTE) != null));
    }

    @GetMapping(path = "/api/note",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> getNote() {
        return Mono.fromSupplier(note::get);
    }

    @PostMapping(path = "/api/note",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> setNote(@RequestBody Mono<String> text) {
        return text.map(value -> {
            note.set(value);
            return "saved:" + value;
        });
    }

    @PostMapping(path = "/session/end",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> endSession(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(WebSession::invalidate)
                .thenReturn("session-ended");
    }
}
~~~

**Ý nghĩa:**
- `/csrf` trả token do Spring Security phát ra qua request handler, không trực tiếp đọc attribute raw token trong WebSession.
- `/session/csrf-stored` chỉ trả boolean, không phơi bày giá trị token lưu trong session. Nó vẫn dùng `exchange.getSession()` để quan sát phiên hiện tại.
- `/api/note` GET là read-only; POST là thao tác unsafe được CSRF filter kiểm tra trước khi sửa `AtomicReference`.
- `/session/end` là POST, **cũng cần CSRF token** rồi mới thực hiện `WebSession.invalidate()`.
- Tất cả handler trả `Mono` và để WebFlux quản lý subscription; không tự `block()` hoặc `subscribe()`.

`AtomicReference` chỉ là mô hình dữ liệu bộ nhớ của một instance, không phải giải pháp persistence; trong hệ thống thật cần service/database và authorization theo đối tượng.

## 10. Chạy thử: token và cookie cùng đi qua nhiều request

Ở thư mục chứa `build.gradle`:

~~~bash
gradle bootRun
~~~

Với Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Mặc định app nghe `http://localhost:8080`, chỉ nên chạy local.

### 10.1. Lệnh GET đầu tiên

~~~bash
# Không credentials --> HTTP 401 ở route bảo vệ.
curl -i http://localhost:8080/api/note

# Có Basic credentials --> HTTP 200; body initial.
curl -i -u learner:localpass http://localhost:8080/api/note
~~~

GET không cần CSRF token theo policy mặc định; 401 trong ví dụ là do authentication, không phải CSRF.

### 10.2. Cấp token và lưu cookie WebSession

Các lệnh sau dùng Bash và cần `curl` cùng `jq`:

~~~bash
# Lấy token (có thể được masking) và lưu cookie session.
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# Kiểm tra JSON có các trường cần thiết (KHÔNG ghi log sản xuất).
jq '{headerName, parameterName}' csrf.json

# Lấy giá trị token do server cung cấp.
TOKEN="$(jq -r '.token' csrf.json)"
HEADER="$(jq -r '.headerName' csrf.json)"

# Xem session hiện tại có expected token hay không.
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  http://localhost:8080/session/csrf-stored
~~~

Đầu ra GET `/session/csrf-stored` kỳ vọng:

~~~json
{"stored":true}
~~~

**Không nên hard-code token** vào file trong source control. `csrf.json` và `csrf-cookies.txt` chỉ dành cho demo; với môi trường thật, đây là dữ liệu nhạy cảm cần quản lý an toàn và loại khỏi git, log và artifact chia sẻ.

### 10.3. POST thiếu token sẽ bị từ chối

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H 'Content-Type: text/plain' \
  --data 'unsafe-change' \
  http://localhost:8080/api/note
~~~

Kỳ vọng **HTTP 403 Forbidden**. Sau đó GET kiểm tra state:

~~~bash
curl -i -u learner:localpass http://localhost:8080/api/note
~~~

Kỳ vọng body vẫn `initial`. Đó là bằng chứng thao tác POST không được đi đến controller khi thiếu token.

### 10.4. POST đúng token và cookie

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'saved-with-csrf' \
  http://localhost:8080/api/note

curl -i -u learner:localpass http://localhost:8080/api/note
~~~

Nếu token/session còn hợp lệ, kết quả kỳ vọng:

~~~text
POST /api/note -> HTTP 200; body: saved:saved-with-csrf
GET  /api/note -> HTTP 200; body: saved-with-csrf
~~~

**Hai điều kiện độc lập:** token + cookie phục vụ kiểm tra CSRF; `-u learner:localpass` phục vụ authentication của request. Nếu bỏ Basic credentials nhưng giữ cookie/token, API vẫn phải áp dụng authentication rule.

### 10.5. Bỏ cookie nhưng vẫn gửi token

~~~bash
curl -i -u learner:localpass \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'token-without-session' \
  http://localhost:8080/api/note
~~~

Với WebSession repository và không có session đúng, kỳ vọng request bị từ chối **403**, vì server không tìm đúng expected token. Đừng diễn giải “token không hợp lệ” bằng cách lấy raw session attribute rồi tự so sánh khi đang sử dụng XOR handler mặc định.

### 10.6. Invalidate WebSession

Gọi POST kết thúc session khi cookie/token còn hợp lệ:

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt -c csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST \
  http://localhost:8080/session/end
~~~

Kỳ vọng `200` và body `session-ended`. Sau đó, token cũ không còn expected token cùng phiên để dùng cho POST mới; muốn tiếp tục thay đổi dữ liệu, client cần lấy CSRF token mới qua `GET /csrf` và giữ cookie session mới.

Đặc biệt, sau `invalidate()`, một GET vẫn có thể trả 200 nếu tiếp tục cung cấp HTTP Basic credentials; **không phải** vì session cũ còn hiệu lực mà do Basic là xác thực mới trên request hiện tại. Một hệ thống dùng form-login/session authentication sẽ có hành vi đăng xuất khác.

### 10.7. Tóm tắt ma trận HTTP

| Request | Auth | Cookie/session token | CSRF header | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| GET `/api/note` | Không | Không | Không | **401** |
| GET `/api/note` | Basic đúng | Không | Không | **200** |
| GET `/csrf` | Basic đúng | Browser nhận session | Không | **200** + token |
| GET `/session/csrf-stored` | Basic đúng | Cùng session | Không | **200** + stored=true |
| POST `/api/note` | Basic đúng | Cùng session | Thiếu | **403** |
| POST `/api/note` | Basic đúng | Cùng session | Đúng | **200** |
| POST `/api/note` | Basic đúng | Thiếu/sai session | Token của session trước | **403** |
| POST `/session/end` | Basic đúng | Cùng session | Đúng | **200**, invalidate |

Các body lỗi có thể thay đổi theo phiên bản; status được mô tả dựa trên cấu hình demo. Đừng kết luận POST thiếu cả auth và token chắc chắn trả 401, vì CSRF filter có thể trả 403 trước.

## 11. Unit test trực tiếp repository bằng Reactor StepVerifier

Các test HTTP trong phần kế tiếp cho thấy Spring Security sử dụng CSRF token. Nhưng cũng nên kiểm tra trực tiếp hợp đồng của repository:
- Chưa lưu token → `loadToken` không phát giá trị.
- `generateToken` → token có giá trị không rỗng.
- `saveToken` rồi `loadToken` trên cùng exchange → token khớp.
- `saveToken(exchange, null)` → xóa token đã lưu.

`src/test/java/demo/WebSessionCsrfRepositoryTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class WebSessionCsrfRepositoryTest {

    private WebSessionServerCsrfTokenRepository repository() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();
        repository.setSessionAttributeName("TEST_CSRF");
        return repository;
    }

    @Test
    void newSessionHasNoStoredToken() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        StepVerifier.create(repository().loadToken(exchange))
                .verifyComplete();
    }

    @Test
    void generateSaveAndLoadRoundTrip() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        var repository = repository();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .flatMap(token -> repository
                                .saveToken(exchange, token)
                                .then(repository.loadToken(exchange))
                                .map(loaded -> {
                                    assertFalse(loaded.getToken().isBlank());
                                    assertEquals(token.getToken(),
                                            loaded.getToken());
                                    return loaded;
                                })))
                .expectNextCount(1)
                .verifyComplete();
    }

    @Test
    void saveNullRemovesExpectedToken() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        var repository = repository();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .flatMap(token -> repository
                                .saveToken(exchange, token)
                                .then(repository.saveToken(exchange, null))
                                .then(repository.loadToken(exchange))))
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** cả ba test PASS nếu project tạo đúng như mô tả. Đây là kỳ vọng trên cơ sở API; không phải báo cáo Gradle đã thực sự chạy. `verifyComplete()` với `Mono<CsrfToken>` có nghĩa không có item `onNext`, phù hợp khi không tìm thấy expected token.

**Ranh giới test:** trực tiếp tạo repository không chứng minh một `SecurityWebFilterChain` đang sử dụng đúng bean. Cần test integration sau để xác nhận request thực bị CSRF filter kiểm tra.

## 12. Integration test WebFlux với WebTestClient

Spring Security Test cung cấp `SecurityMockServerConfigurers.csrf()` giúp gắn CSRF token hợp lệ trong test WebFlux; không dùng helper này để bypass CSRF ngoài production.

`src/test/java/demo/WebFluxCsrfSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class WebFluxCsrfSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousGetNeedsAuthentication() {
        client.get().uri("/api/note")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthenticatedGetNeedsNoCsrf() {
        client.get().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenWithBasic() {
        client.post().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-allowed")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithTestCsrfAndBasicIsAllowed() {
        client.mutateWith(csrf())
                .post().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }

    @Test
    void postSessionEndWithoutCsrfIsForbidden() {
        client.post().uri("/session/end")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Kỳ vọng:** 5 test integration PASS. Việc `csrf()` cho phép POST trong test không làm mất bảo vệ CSRF ở application thật. Test dùng mock exchange để xác minh security chain, còn lệnh `curl` ở phần 10 kiểm tra lifecycle token + WebSession cookie thực tế.

Nếu test có token hợp lệ nhưng vẫn 403, hãy xác minh `springSecurity()` đã được áp dụng, repo/CSRF handler đang dùng và test helper phù hợp với dependency version; đừng disable CSRF chỉ để khiến test xanh.

## 13. Khi token biến mất: session timeout, logout và token rotation

### 13.1. WebSession hết hạn

Expected token lưu trong WebSession sống theo vòng đời phiên. Khi idle timeout bị vượt quá:
- Browser có thể vẫn gửi session ID cookie cũ.
- Server không còn expected token của session cũ.
- Request unsafe với token cũ bị từ chối, thường 403.
- Client phải lấy token mới trong một phiên mới và gửi lại với cookie tương ứng.

Với Boot Reactive, `server.reactive.session.timeout` thường đặt **idle timeout**, không phải thời hạn tuyệt đối. Thời hạn cookie phía browser (Max-Age) và TTL session phía server là **hai đồng hồ khác nhau**.

### 13.2. Đăng xuất

Với session login, logout cần invalidation đúng của SecurityContext/session và token CSRF. Trong demo, `POST /session/end` gọi `WebSession.invalidate()` để minh họa token mất hiệu lực, nhưng **không khiến browser quên HTTP Basic credentials**.

Trong ứng dụng thật:
- Thực hiện logout qua HTTP method phù hợp, giữ CSRF cho các thao tác thay đổi trạng thái nếu client browser.
- Vô hiệu session phía server và xóa cookie đúng Name/Domain/Path nếu policy yêu cầu.
- Nếu có remember-me/OAuth2 refresh token, xử lý revocation và identity provider theo luồng tương ứng.
- Đừng chỉ xóa client cookie mà để session ID cũ còn hợp lệ trên shared store.

### 13.3. Login/logout làm token cũ mất hiệu lực

Việc thay SecurityContext/session hoặc các CSRF logout handlers có thể xóa/rotate token. Điều này là có chủ đích để hạn chế reuse ở ngữ cảnh không còn hợp lệ.

Một SPA muốn tiếp tục POST sau login/logout có thể cần:
1. Xác thực lại (nếu cần).
2. Gọi endpoint lấy CSRF token mới trong ngữ cảnh phiên mới.
3. Lưu session cookie mới theo chính sách browser.
4. Gắn token mới vào request unsafe.

Không giữ một token CSRF trong localStorage “vĩnh viễn” rồi giả định nó luôn hợp lệ sau khi session thay đổi. Không retry vô hạn các POST 403 bằng token cũ.

### 13.4. Có nên ép token mới ở mọi request?

Không bắt buộc. Repository giữ expected token trong session, còn request handler XOR có thể tạo một **masked presentation** mới trên mỗi lần cung cấp token. Điều đó khác với việc generate/saving một raw token mới mỗi GET.

Nếu ứng dụng có chính sách rotation riêng, cần thiết kế phía server, session store, concurrent tabs, logout và client synchronization. Việc tùy tiện rotate raw token mỗi GET có thể khiến các tab khác đang mở form bị 403.

## 14. Troubleshooting: POST 403 có thật sự do repository?

Khi gặp 403, đừng kết luận ngay “WebSessionServerCsrfTokenRepository hỏng”. Thử theo thứ tự:

1. **Method:** request là POST/PUT/PATCH/DELETE hay GET? Matcher CSRF có áp dụng?
2. **Security chain:** có nhiều `SecurityWebFilterChain` không? Route đang vào chain nào?
3. **Authentication:** với Basic, thử GET bảo vệ cùng credentials. GET 401 nghĩa chưa xác thực đúng.
4. **Token endpoint:** `GET /csrf` có trả token không, hay bị entry point từ chối?
5. **Cookie jar:** request POST có gửi đúng `SESSION` cookie vừa nhận khi GET token không?
6. **Token header:** có gửi `headerName` và `token` đúng như response không?
7. **XOR handler:** client có tự decode/mask/unmask token bằng logic riêng không? Nếu có, hãy ngừng và dùng giá trị được cấp.
8. **SameSite/CORS:** browser có chặn cookie trong cross-site request theo policy không? Origin có được phép đọc response token không?
9. **Session expiry:** timeout có qua, session invalidated/logout hay ID bị rotate không?
10. **Multiple instances:** có load balancer phát request sang instance khác mà session không shared không?
11. **Spring Session:** store Redis hoạt động không, TTL/cấu hình WebSession tương thích không?
12. **Proxy:** có reverse proxy đổi scheme, cookie Path/Domain, strip headers, hoặc rewrite URL không?
13. **Authorization:** nếu đã có token hợp lệ nhưng vẫn 403, role/scope/owner check có từ chối không?
14. **CSRF disabled?** Nếu POST thiếu token vẫn 200, xem policy/matcher của chain có disable CSRF không hoặc route thực không nằm trong chain dự định.
15. **Không log token:** dùng correlation ID, method, route, response status và loại lỗi; không in raw token, cookie hoặc Authorization header.

### 14.1. Phân biệt triệu chứng

| Triệu chứng | Khả năng | Cách xác nhận |
| --- | --- | --- |
| GET API bảo vệ trả 401 | Credentials sai/thiếu | Kiểm tra authentication entry point |
| POST thiếu token trả 403 | CSRF bảo vệ đang hoạt động | Thử POST tương đương có token hợp lệ |
| POST có token nhưng thiếu SESSION trả 403 | Không tìm expected token của phiên | Gửi đúng cookie jar |
| GET /csrf trả token nhưng session state false | Token chưa được lưu, token deferred chưa subscribe hoặc sai session | Kiểm tra pipeline/repository và request cookie |
| Session state true nhưng POST 403 | Header sai, masked/raw mismatch, token cũ hoặc thiếu quyền | Kiểm tra token cấp/handler và authorization |
| GET /csrf lại cho token chuỗi khác nhưng session vẫn đúng | Có thể do XOR masking | Không so sánh masked strings để suy token raw thay đổi |
| Khi scale 2 instance, POST lúc được lúc 403 | Session store không dùng chung hoặc proxy sai | Test sticky routing/Redis session |
| Sau logout, token cũ bị 403 | Token/session cũ đã mất hiệu lực | Lấy token mới và session mới |
| POST có token và cookie nhưng server trả 404 | Security có thể đã cho qua, handler không có | Kiểm tra route/method |
| POST có token, cookie, Basic đúng nhưng 403 | Có thể do authorization | Xem authorities và filter phát lỗi |

### 14.2. Đừng vô hiệu hóa CSRF để chữa lỗi integration

Anti-pattern:

~~~java
// Không dùng như "sửa lỗi" cho browser có cookie/Basic credentials.
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

Chỉ cân nhắc disable sau khi threat model chứng minh request không phụ thuộc browser-originated ambient authentication. Khi client là website browser với cookie login hoặc Basic authentication đã được nhớ, giữ một cơ chế chống CSRF phù hợp.

## 15. WebSession repository và các phương án thay thế

### 15.1. Khi nên giữ WebSessionServerCsrfTokenRepository

Phù hợp khi:
- Ứng dụng có WebSession sẵn cho browser/form login.
- CSRF token cần được gắn với lifecycle của một phiên phía server.
- Có thể quản lý session timeout/invalidation và shared session store.
- Frontend có một cơ chế an toàn để nhận và gửi token trong form/header.
- Không cần JavaScript đọc trực tiếp cookie chứa token.

**Ưu điểm:** expected token không cần nằm nguyên dạng trong cookie CSRF phía browser; lifecycle gắn chặt WebSession. **Đánh đổi:** phải quản lý session state, cookie ID, timeout, Redis/scale và lỗi client không gửi lại cookie.

### 15.2. Khi cân nhắc CookieServerCsrfTokenRepository

Một SPA có thể thuận tiện hơn nếu cookie token được đọc bởi JavaScript và đưa vào header. Tuy nhiên:
- Nếu dùng `withHttpOnlyFalse()`, cookie CSRF token có thể được JS đọc: XSS và exposure phải được đánh giá.
- Browser có thể tự gửi cookie, nên **đưa token vào header riêng** mới là phần chống CSRF quan trọng.
- Default XOR handler của Spring Security 6.x và JavaScript lấy raw token từ cookie có thể đòi hỏi custom request handler/flow phù hợp.
- Không nhất thiết phù hợp với mọi login/SSO/embedded app.

Không thay repo WebSession bằng cookie chỉ vì một lần gặp 403. Chẩn đoán cookie jar/timeout/header/matcher trước.

### 15.3. Khi API thực sự không có nguy cơ CSRF

Với service-to-service API dùng Bearer token mà browser không tự phát credentials theo cơ chế ambient, có thể đánh giá tắt CSRF cho namespace đó và không tạo server session chỉ vì token CSRF. Nhưng lựa chọn này cần xét toàn bộ hệ thống: API gateway, cookie authentication, SPA, browser Basic, OAuth2 login, CORS và những routes dùng chung.

## 16. Bảo mật khi triển khai production

**Cookie SESSION:**
- `Secure=true` trên HTTPS production.
- `HttpOnly=true` với session ID cookie.
- `SameSite=Lax/Strict/None` theo điều hướng/browser thật và CSRF threat model.
- Giới hạn `Domain` và `Path`; ưu tiên host-only cookie khi không cần chia sẻ.
- Không log session ID; không đặt vào URL.
- Chống session fixation/rotation ở ranh giới tăng quyền, kiểm tra logout và expiry.

**CSRF token:**
- Có entropy đủ cao, không đoán được, không tái sử dụng xuyên session một cách bất cẩn.
- Không hiển thị token cho origin ngoài ý muốn qua CORS/proxy.
- Token phải đi qua header/form field đúng tên, không chỉ cookie.
- Cập nhật token khi session/auth lifecycle thay đổi.
- Không log token, không lưu trong analytics hoặc file chia sẻ.
- Kiểm thử masked token của Spring Security 6.x và tính tương thích frontend.

**Ứng dụng và cơ sở hạ tầng:**
- Bảo vệ XSS bằng output encoding, CSP và kiểm soát template/JS dependencies. XSS trong origin hợp pháp có thể thao tác với CSRF token.
- Giữ authorization đúng quyền sở hữu tài nguyên; CSRF token không cho phép user xem dữ liệu người khác.
- Giới hạn CORS origins và methods/headers/credentials.
- Đặt rate limit và bảo vệ authentication mechanism.
- Dùng shared session store với TTL rõ ràng cho multi-instance khi cần.
- Không ép toàn bộ token vào request body multipart trước khi xử lý kích thước/tài nguyên; ưu tiên header trong ứng dụng JS.

### 16.1. Một câu hỏi về session fixation

Nếu login thành công sau một phiên anonymous, session ID có thể cần được rotate để giảm nguy cơ session fixation. Cơ chế nâng mức xác thực và session fixation protection thuộc security/session lifecycle, **không** được thay bằng việc tạo CSRF token mới một cách tùy tiện.

### 16.2. Không dùng CSRF token để xác thực người dùng

Một ứng dụng phải xác minh danh tính và quyền bằng authentication/authorization riêng. Nếu ai đó chỉ có CSRF token hợp lệ nhưng không có credentials, họ không tự nhiên được cấp quyền. CSRF token là một điều kiện bổ sung khi request cần bảo vệ, không phải thay thế account management.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Nhầm expected token với SESSION cookie | Cookie giữ ID phiên, không phải token | Gửi cả cookie session và token ở header/form |
| Chỉ gửi token, không gửi cookie | Repo không biết phiên nào chứa expected token | Dùng cùng session/cookie jar |
| Chỉ gửi SESSION cookie, không gửi token | Browser tự gửi cookie, không tạo bảo vệ CSRF | Client chủ động gửi token |
| Lấy raw token trong session rồi so với masked response token | XOR handler có thể biến đổi token trình bày | Dùng request handler mặc định, không tự unmask |
| Dùng `block()` trong WebFlux controller | Có thể chặn event loop | Trả `Mono`/compose publishers |
| Gọi `saveToken` nhưng không subscribe | Reactive operation có thể không chạy | Compose vào pipeline của framework |
| Nghĩ mọi GET đều phát CSRF token | CSRF token có thể được defer | Khi cần thì request/subscribe token |
| Nghĩ `NoOpServerSecurityContextRepository` tắt CSRF session | Hai repository riêng | Kiểm tra CSRF token repository độc lập |
| Xóa SESSION cookie nhưng không invalidate session server | Session ID bị đánh cắp vẫn có thể dùng | Invalidate/revoke phía server |
| Token hết hạn do WebSession nhưng frontend không refresh | POST liên tục 403 | Lấy token và session mới |
| Dùng một session store in-memory khi nhiều instance | Request khác instance mất token | Shared store/sticky routing có kiểm soát |
| Cho phép mọi CORS origin đọc `/csrf` | Token có thể bị lộ | Restrict trusted origins và credentials |
| Tắt CSRF trên browser Basic/form login | Tăng nguy cơ CSRF | Giữ CSRF khi browser có ambient credentials |
| Dùng `HttpSessionCsrfTokenRepository` trong WebFlux | Đây là Servlet API | Dùng `WebSessionServerCsrfTokenRepository` |
| Log raw token và cookie | Rò rỉ bí mật | Chỉ log safe status và correlation ID |
| Coi CSRF token là authority ADMIN | Sai tầng bảo mật | Authorization kiểm tra role/owner riêng |
| Dùng POST cho thao tác nhưng không kiểm thử âm tính | Dễ bỏ sót security chain | Test có/không token, có/không auth |
| GET gây side effect | CSRF mặc định không kiểm tra GET | Giữ GET read-only |
| Copy cấu hình cookie SPA Servlet sang WebFlux | Các API handler khác nhau | Đọc tài liệu Reactive và test version |

## 18. Checklist QA cho một tính năng mới

### Cấu hình
- [ ] Đã biết ứng dụng chạy WebFlux hay Servlet; chọn đúng loại token repository.
- [ ] `SecurityWebFilterChain` thực sự bao phủ route cần bảo vệ.
- [ ] CSRF được bật cho unsafe methods theo threat model.
- [ ] `WebSessionServerCsrfTokenRepository` được dùng mặc định hoặc cấu hình tường minh.
- [ ] Nếu custom header/parameter/session attribute, frontend và tests đã được cập nhật.
- [ ] SecurityContext repository độc lập; không suy luận session auth từ CSRF token.
- [ ] Không có route POST nhạy cảm bị `permitAll` ngoài chủ đích.

### Browser/front-end
- [ ] View/endpoint phát token từ `Mono<CsrfToken>` do request handler cung cấp.
- [ ] Token không lộ qua CORS, URL, referrer, log hay analytics.
- [ ] Browser gửi đúng SESSION cookie khi POST.
- [ ] Token đặt trong form field/header, không chỉ cookie.
- [ ] Frontend xử lý token hết hạn sau session timeout/logout.
- [ ] SPA hiểu token masking khi dùng Spring Security 6.x.
- [ ] CSRF token và authentication credentials không bị lẫn nhau.

### Server/operational
- [ ] WebSession timeout, cookie Max-Age, Redis TTL được kiểm chứng là các chính sách riêng.
- [ ] Sau logout/invalidate, token cũ không còn giá trị.
- [ ] Shared session store hoặc routing phù hợp khi nhiều instance.
- [ ] Request GET/HEAD không có side effects.
- [ ] Session cookie được bảo vệ bằng HTTPS, Secure/HttpOnly/SameSite phù hợp.
- [ ] Metrics phân biệt auth 401, csrf 403, authorization 403 và lỗi nghiệp vụ 4xx.
- [ ] Không log token/session ID trong tracing.

### Tests
- [ ] GET protected không credentials bị 401.
- [ ] GET với credentials đúng có thể đọc state.
- [ ] POST có credentials đúng nhưng thiếu CSRF token bị 403.
- [ ] POST đúng token nhưng sai session bị từ chối.
- [ ] POST đúng session + token + authentication thành công.
- [ ] `saveToken` rồi `loadToken` roundtrip đúng.
- [ ] `saveToken(exchange, null)` xóa token.
- [ ] Sau session invalidation, token cũ không còn hiệu lực.
- [ ] Test trên browser thật khi có CORS/SameSite/cross-site.
- [ ] Không dùng một status 403 để suy ra chính xác tầng từ chối mà chưa đối chiếu.

## 19. Câu hỏi tự kiểm tra và gợi ý trả lời

**1. `WebSessionServerCsrfTokenRepository` lưu gì và lưu ở đâu?**

> Lưu **expected CsrfToken** như attribute trong `WebSession`, để server có thể so sánh với token gửi từ client.

**2. Vì sao client cần gửi cả SESSION cookie và `X-CSRF-TOKEN`?**

> Cookie giúp server tìm đúng phiên chứa expected token; header/form chứng minh request có token do ứng dụng hợp lệ cấp, không chỉ một cookie tự gắn.

**3. `generateToken` có tự lưu vào WebSession không?**

> Không nên coi như vậy; có bước lưu riêng `saveToken` do filter/repository flow điều phối.

**4. `loadToken` khi session chưa có token trả gì?**

> `Mono.empty()`: không phát đối tượng token.

**5. `saveToken(exchange, null)` có nghĩa gì?**

> Theo hợp đồng repository, xóa token kỳ vọng đang lưu.

**6. Tại sao masked token trong HTML không nhất thiết giống raw token trong WebSession?**

> Spring Security 6.x thường dùng XOR request handler để masking token khi trình bày, giảm rủi ro BREACH.

**7. Vì sao một GET có thể không tạo WebSession dù CSRF bật?**

> Token có thể được defer/lazy; nếu request không cần token và không subscribe `Mono<CsrfToken>`, không nhất thiết phải sinh token/session.

**8. Browser lưu token trong header nhưng mất SESSION cookie; POST có qua không?**

> Thường không, vì repository không tìm được expected token của session cũ để đối chiếu.

**9. `NoOpServerSecurityContextRepository` có khiến repository CSRF không lưu được token không?**

> Không. Authentication persistence và CSRF token repository là hai cơ chế khác nhau.

**10. Vì sao sau `WebSession.invalidate()` mà GET có Basic credentials vẫn trả 200?**

> Basic credentials có thể được gửi lại và xác thực trên request mới; session bị invalidate không tự xóa credentials ở client.

**11. Với SPA, khi nào cân nhắc `CookieServerCsrfTokenRepository`?**

> Khi frontend cần tích hợp token qua cookie và có threat model phù hợp, đồng thời phải xử lý XOR/token handler, HttpOnly và XSS đúng version.

**12. CSRF token có thay `hasRole("ADMIN")` được không?**

> Không. CSRF bảo vệ request khỏi bị giả mạo, còn authorization cấp quyền cho user/tài nguyên.

## 20. Tổng kết

`WebSessionServerCsrfTokenRepository` là cách Spring Security Reactive **lưu expected CSRF token trong WebSession**. Nó có hợp đồng tạo/lưu/tải token bằng Reactive `Mono` và được `CsrfWebFilter` cùng request handler sử dụng để kiểm tra những request cần CSRF protection.

Để một POST có thể vượt qua CSRF đúng cách, client thường cần:
1. Có session cookie giúp server định vị WebSession.
2. Lấy token qua view/endpoint hợp lệ từ request handler.
3. Gửi token trong header/form parameter không được browser tự thêm.
4. Vẫn đáp ứng authentication và authorization độc lập.

Khi Spring Security 6.x dùng XOR handler, **masked token trình bày cho client có thể khác raw expected token lưu trong session**; không tự sửa token. Session timeout/logout, cookie scope, shared session store, HTTPS, CSRF/CORS/XSS là những phần cần kiểm chứng cùng nhau.

### Tài liệu tham khảo chính thức

- Spring Security Reference — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Javadoc — `WebSessionServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security Javadoc — `ServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security Javadoc — `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security Reference — Testing WebFlux with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security Reference — Reactive Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework Javadoc — `WebSession`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Session Reference — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html