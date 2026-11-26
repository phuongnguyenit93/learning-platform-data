# Ghi rõ giả thiết và kiểm thử hồi quy cho mỗi ngoại lệ

> **Chương:** Phạm vi kiểm tra CSRF  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session, trên cả Servlet lẫn Reactive.  
> **Trọng tâm:** Mọi ngoại lệ CSRF phải có **giả thiết an toàn kiểm chứng được**, **phạm vi chính xác**, **kiểm thử hồi quy âm và dương**, cùng **người chịu trách nhiệm đánh giá lại**. Không coi một ngoại lệ là đúng mãi mãi chỉ vì hiện tại request chạy thành công.

## 1. Mục tiêu học tập

Sau bài học này, người học có thể:

1. Viết **hồ sơ ngoại lệ CSRF** (exception record) mô tả endpoint, method, client, credential, giả thiết về trình duyệt, cơ chế bảo vệ thay thế và phạm vi cho phép.
2. Phân biệt **ngoại lệ CSRF**, **quyết định authorization** và **bỏ qua toàn bộ security chain**; tránh dùng `permitAll` hay `web.ignoring()` như một lời giải thích sai.
3. Thiết kế kiểm thử **âm/dương** để chứng minh ngoại lệ đúng URL, đúng method, đồng thời không làm endpoint dùng session/cookie mất bảo vệ.
4. Kiểm chứng API bearer-only không có cookie fallback, webhook có xác minh chữ ký/chống replay, và form browser vẫn bắt buộc CSRF token.
5. Tạo ví dụ Servlet/MockMvc và Reactive/WebTestClient cùng nguyên tắc, phân biệt security matcher với CSRF matcher.
6. Đưa regression test vào CI và quy định rõ thời điểm tái đánh giá ngoại lệ: thêm endpoint, đổi cách lưu token, thêm browser client, thay proxy hoặc security chain.
7. Chẩn đoán false positive khi test 401/403/404/405, CORS, CSP/security headers và session thay vì tuyên bố “đã kiểm thử CSRF” từ một status duy nhất.

**Thông điệp chính:** Ngoại lệ CSRF là **một quyết định có điều kiện**, không phải một đoạn cấu hình tĩnh. Khi điều kiện thay đổi mà ngoại lệ còn nguyên, lỗ hổng có thể xuất hiện dù không có ai sửa `csrf(...)`.

## 2. Bắt đầu từ nguyên tắc bảo vệ mặc định

CSRF (Cross-Site Request Forgery) là rủi ro khi một nguồn không đáng tin khiến **trình duyệt nạn nhân** gửi request làm thay đổi trạng thái tới server, kèm theo credential mà trình duyệt **tự động đính kèm**. Cookie session, JWT trong cookie và một số cơ chế browser tự gửi credential là các trường hợp phải đánh giá.

Trong Spring Security khi bật CSRF, matcher mặc định thường không yêu cầu token cho `GET`, `HEAD`, `OPTIONS`, `TRACE`; các method không an toàn như `POST`, `PUT`, `PATCH` và `DELETE` cần token hợp lệ trừ khi được miễn. Vì vậy, một ngoại lệ phải trả lời **tại sao request cụ thể không cần cơ chế chứng minh ý định của browser này**, chứ không chỉ nêu “client báo lỗi 403”.

### 2.1. Mô hình client quyết định nhu cầu CSRF

| Loại request | Credential server thật sự chấp nhận | Đánh giá CSRF |
|---|---|---|
| Browser form/SPA/BFF | Session cookie | **Giữ CSRF** cho method làm thay đổi trạng thái |
| SPA sử dụng JWT trong cookie | Cookie có JWT | **Vẫn có nguy cơ CSRF** |
| Native app/CLI | `Authorization: Bearer` do client chủ động gắn, không có cookie fallback | Có thể miễn/tắt CSRF trong chain bearer-only được kiểm chứng |
| Webhook máy–máy | HMAC/chữ ký hoặc mTLS độc lập, không có session/cookie fallback | Có thể miễn đúng method/path; bắt buộc xác minh nguồn và replay |
| Public form `POST /register` | Anonymous nhưng gửi từ browser | Thông thường **giữ CSRF**, dù authorization là `permitAll` |
| Endpoint dùng cả session và bearer | Server chấp nhận **hoặc** cookie **hoặc** bearer | Không miễn CSRF toàn route chỉ vì có một nhánh bearer |
| GET thật sự chỉ đọc | Không đổi trạng thái | Không cần CSRF theo matcher mặc định, nhưng vẫn cần quyền phù hợp |

**Hai điều không tương đương:** JWT là một định dạng token, không phải một bằng chứng request không có CSRF; `SessionCreationPolicy.STATELESS` không bảo đảm backend không nhận JWT từ cookie qua custom resolver.

### 2.2. Cấu hình nào được xem là ngoại lệ?

Với Servlet, một request có thể được miễn token qua `csrf.ignoringRequestMatchers(...)`. Với WebFlux, có thể định nghĩa `requireCsrfProtectionMatcher(...)` để giữ quy tắc mặc định và loại đúng request có hợp đồng độc lập. Một security chain bearer-only riêng có thể tắt CSRF **trong chain đó**.

Ngược lại:

- `permitAll` là quyết định **phân quyền**, không tự tắt CSRF.
- `authenticated`/`hasAuthority` không thay thế CSRF, vì cookie của người dùng hợp lệ có thể được browser tự gửi.
- `csrf.disable()` của chain hỗn hợp bỏ bảo vệ rộng hơn một ngoại lệ cụ thể.
- `web.ignoring()` trong Servlet bỏ qua những Spring Security filters bên trong chain đối với request được chọn, không chỉ CSRF; có thể làm mất authentication, authorization và security headers từ Spring Security.

Một request có thể vào đúng chain nhưng được miễn CSRF, hoặc được `permitAll` nhưng vẫn bắt buộc CSRF. **Phải kiểm thử cả hai chiều.**

## 3. Hồ sơ ngoại lệ: tài liệu tối thiểu cần có

Hãy lưu một bản ghi được review cùng mã cấu hình hoặc ADR/kiến trúc có liên kết tới test. Không cần tạo thêm YAML trong module bài học này; bảng sau là **mẫu nội dung cần tài liệu hóa**, không phải yêu cầu sinh file mới.

| Trường | Cần ghi gì? |
|---|---|
| Exception ID | Mã ổn định, ví dụ `CSRF-EX-014` |
| Chủ sở hữu | Team, người review, kênh liên hệ khi có thay đổi |
| Mục đích | Lý do nghiệp vụ phải nhận request không có CSRF token |
| Method + route | Ví dụ **chỉ** `POST /integrations/payment-events`, không ghi chung `/integrations/**` |
| Security chain | Chain đầu tiên khớp, `@Order`, matcher chọn chain, fallback |
| Client | Webhook bên thứ ba, native app, backend service... |
| Credential được chấp nhận | Chữ ký HMAC; bearer header; mTLS; có/không cookie/session |
| Giả thiết trình duyệt | Browser không có credential tự gửi được server chấp nhận ở endpoint này |
| Phòng vệ thay thế | HMAC đúng raw body; JWT signature/issuer/audience/scope; anti-replay/idempotency |
| Giới hạn quyền | Tenant, subject, resource, event type, ownership |
| Biến đầu vào phụ thuộc | Secret rotation, provider protocol, reverse proxy route, token storage |
| Kiểm thử dương | Request hợp lệ, không CSRF token, phải tới nghiệp vụ đúng một lần |
| Kiểm thử âm | Chữ ký sai; thiếu bearer; cookie-only; method/path gần giống; browser POST thiếu CSRF |
| Bằng chứng | Link test suite, review/ADR, trace/log kiểm soát và ngày xác minh |
| Ngày phê duyệt & rà soát | Thời điểm quyết định, ngày hoặc trigger cần xem lại |
| Điều kiện thu hồi | Thêm cookie auth, đổi client, thay chain, thay callback, thiếu kiểm thử |
| Trạng thái ngoại lệ | Proposed / Approved / Deprecated; không mặc định có hiệu lực mãi |

Hồ sơ không nên chứa secret, bearer token, raw session cookie, dữ liệu cá nhân hoặc payload nhạy cảm. **Mã ngoại lệ không thay cho test.** Nó giúp người review hiểu **điều gì phải còn đúng** để test và cấu hình vẫn có ý nghĩa.

### 3.1. Mẫu hồ sơ cụ thể: webhook thanh toán

```yaml
# Minh họa trong tài liệu, KHÔNG phải file metadata bài học.
exceptionId: CSRF-EX-PAY-001
owner: payment-platform
scope:
  methods: [POST]
  path: /integrations/payment-events
  chain: browser-fallback
client: payment-provider-server
acceptedCredential: "HMAC header; no cookie/session fallback"
assumptions:
  - "Không xác thực request bằng session/cookie của trình duyệt"
  - "Chữ ký bao phủ raw body theo đúng giao thức nhà cung cấp"
  - "Timestamp và event ID được kiểm tra chống replay"
  - "Route POST là duy nhất; PUT và path con không được miễn"
compensatingControls:
  - "Từ chối chữ ký sai hoặc thiếu trước mọi side effect"
  - "Kiểm tra tenant/order/amount và idempotency"
tests:
  positive: "signed request, no CSRF token -> processed exactly once"
  negative: "bad signature, expired timestamp, duplicate event, PUT, adjacent path"
reviewTriggers:
  - "Đổi webhook provider, contract chữ ký hoặc secret rotation"
  - "Thêm route /integrations/** hoặc đưa cookie auth vào chain"
  - "Thay đổi proxy rewrite hoặc cơ chế session"
```

**Giả thiết cần kiểm chứng ở runtime:** Không chỉ ghi “webhook không dùng cookie”; phải có test gửi request **có cookie session hợp lệ nhưng chữ ký thiếu/sai** và chứng minh handler vẫn từ chối. Nếu một future refactor cho phép session được dùng thay chữ ký, ngoại lệ cũ mất cơ sở.

### 3.2. Mẫu hồ sơ cụ thể: bearer-only API

```yaml
exceptionId: CSRF-EX-M2M-002
owner: api-security
scope:
  methods: [POST, PUT, PATCH, DELETE]
  pathPrefix: /api/m2m/
  chain: bearer-only
client: mobile-cli-service
acceptedCredential: "Authorization: Bearer access token only"
assumptions:
  - "Không dùng session cookie, cookie JWT, Basic hoặc remember-me fallback"
  - "JWT signature, issuer, audience, expiry, scopes được xác thực"
  - "Chain bearer-only được chọn trước browser fallback"
compensatingControls:
  - "Scope và quyền tài nguyên theo từng method/route"
  - "Rate limits/idempotency phù hợp nghiệp vụ"
tests:
  positive: "JWT đúng scope, không CSRF token -> được phép"
  negative: "session cookie hợp lệ không bearer -> từ chối"
  negative2: "bearer sai + session hợp lệ -> từ chối"
  negative3: "JWT thiếu scope -> từ chối"
reviewTriggers:
  - "Thêm browser client, BFF hoặc lưu token vào cookie"
  - "Thay đổi securityMatcher, JWT resolver hoặc session filter"
```

Hồ sơ thứ hai bao phủ một **chain bearer-only**, khác với một ngoại lệ webhook có method/path rất hẹp. Nếu vùng `/api/m2m/**` có thêm endpoint cho browser dùng cookie thì giả thiết “bearer only” bị phá vỡ, phải điều chỉnh cấu trúc route/chain trước khi bật.

## 4. Chuyển giả thiết thành bất biến có thể kiểm thử

Không chấp nhận những câu mơ hồ như “đây là internal API”, “webhook đã an toàn”, “stateless”, “REST trả JSON” hoặc “đã bật CORS”. Hãy chuyển sang các mệnh đề **có thể bác bỏ bằng request cụ thể**.

| Giả thiết | Phép thử có thể bác bỏ | Điều cần chứng minh |
|---|---|---|
| Chỉ POST webhook được miễn | Gửi PUT cùng path, POST path con, POST path tương tự | Không hưởng ngoại lệ CSRF |
| Webhook chỉ tin chữ ký | Gửi body bị sửa hoặc chữ ký giả | Từ chối trước thay đổi dữ liệu |
| Cookie không giúp qua webhook | Gửi session cookie hợp lệ và chữ ký sai | Không bypass verifier |
| Không replay webhook | Gửi lại event ID/chữ ký hợp lệ | Không lặp side effect |
| M2M chỉ chấp nhận bearer | Gửi session cookie hợp lệ nhưng không bearer | Từ chối authentication |
| Không fallback khi bearer sai | Bearer sai kèm session cookie hợp lệ | Từ chối, không dùng cookie |
| Scope được bắt buộc | JWT hợp lệ thiếu `orders.write` | Từ chối authorization |
| Browser POST cần CSRF | Session hợp lệ, POST không token hoặc token sai | Bị CSRF từ chối |
| Browser POST hợp lệ được xử lý | Session hợp lệ, token đúng, có quyền | Qua CSRF tới nghiệp vụ |
| Ngoại lệ không lan ra `/api/**` | POST web trong vùng `/api/web/**` không CSRF | Vẫn bị chặn |
| Mọi route có chain | Thêm route mới ngoài matcher chuyên dụng | Bị fallback chain điều tiết |
| Proxy không làm lệch matcher | Gửi URL qua proxy với path rewrite thật | Chính sách vẫn khớp đúng |
| Không vô ý bỏ headers | Kiểm tra header đã cấu hình ở public/ignored routes | Header bảo mật hiện diện theo thiết kế |

**Một test âm chưa đủ.** Nếu `POST /register` trả 403 không token nhưng cũng 403 với token đúng vì `denyAll`, không thể nói đã chứng minh CSRF. Cần **cặp test âm/dương cùng user/quyền và cùng payload**, chỉ thay token.

### 4.1. Ma trận request tối thiểu cho mỗi ngoại lệ

Giả sử route mới `POST /integrations/payment-events`:

| Request | CSRF theo thiết kế | Phản hồi/side effect đúng |
|---|---|---|
| POST webhook, chữ ký và timestamp đúng, **không token CSRF** | Được miễn | Verifier cho qua, xử lý hợp lệ một lần |
| POST webhook, chữ ký sai, **không token CSRF** | Được miễn | Verifier từ chối; không xử lý |
| POST webhook, chữ ký đúng nhưng timestamp hết hạn | Được miễn | Chống replay/tính mới từ chối |
| POST webhook, event ID trùng | Được miễn | Idempotent; không lặp side effect |
| POST webhook, chỉ session cookie hợp lệ | Được miễn CSRF nhưng **không được xác thực bằng session** | Từ chối vì thiếu chữ ký |
| PUT webhook path, không token | **Không miễn** | CSRF yêu cầu token trước các bước khác |
| POST path `/integrations/payment-events/test`, không token | **Không miễn** | Không lọt CSRF exemption |
| POST `/web/orders`, session hợp lệ, không token | **Không miễn** | CSRF từ chối |
| POST `/web/orders`, session hợp lệ, token đúng | **Không miễn** | Đi tiếp tới quyền và nghiệp vụ |

Các negative tests cho method/path chỉ có ý nghĩa khi **đường đó được thực sự kiểm soát bởi chain đang xét**. Request 404 hoặc 405 không tự chứng minh CSRF; security filter có thể chặn trước routing. Test nên kiểm tra nguồn từ chối, hoặc sử dụng fixture route phù hợp.

## 5. Ghi ngoại lệ thế nào trong Spring Security Servlet?

Với Servlet, nên biểu diễn ngoại lệ webhook bằng matcher **method AND path**, không miễn toàn bộ `/integrations/**` hay `/api/**`.

### 5.1. Cấu hình Servlet có bearer chain riêng và fallback CSRF

Ví dụ sau minh họa hai nhóm:

- `/api/m2m/**` chỉ nhận bearer header, đã được kiểm tra không có cookie fallback.
- Browser fallback yêu cầu CSRF cho unsafe methods, **chỉ miễn POST webhook chính xác**.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Bean
@Order(1)
SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/m2m/**")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(resource -> resource
            .jwt(Customizer.withDefaults()))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/api/m2m/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserAndWebhook(HttpSecurity http) throws Exception {
    // Contract CSRF-EX-PAY-001:
    // chỉ POST /integrations/payment-events, HMAC độc lập,
    // không cookie/session fallback; regression tests bắt buộc.
    RequestMatcher paymentWebhookPost = request ->
        "POST".equals(request.getMethod())
            && "/integrations/payment-events".equals(
                request.getServletPath());

    http
        .csrf(csrf -> csrf
            .ignoringRequestMatchers(paymentWebhookPost))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(paymentWebhookPost).permitAll()
            .requestMatchers(HttpMethod.GET, "/register").permitAll()
            .requestMatchers(HttpMethod.POST, "/register").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

**Đọc cấu hình theo hai tầng:**

1. `securityMatcher("/api/m2m/**")` của chain ưu tiên chọn vùng m2m; `csrf.disable()` chỉ áp dụng **trong chain đó**, không ở browser fallback.
2. Browser fallback không có `securityMatcher` riêng nên nhận các request còn lại, bao gồm webhook.
3. `ignoringRequestMatchers(paymentWebhookPost)` chỉ loại **POST đúng route** khỏi CSRF token check, không loại `PUT` hoặc path con.
4. `requestMatchers(paymentWebhookPost).permitAll()` chỉ cho phép webhook đến controller/filter xác minh chữ ký. **Không có chữ ký hợp lệ thì không được tác động dữ liệu**.
5. `POST /register` `permitAll` về authorization nhưng vẫn cần CSRF token theo matcher mặc định.
6. `getServletPath()` hoạt động theo servlet mapping. Nếu ứng dụng dùng context path hoặc reverse proxy rewrite, phải kiểm thử path nội bộ mà matcher thực sự nhìn thấy.
7. Cấu hình bean `JwtDecoder`/issuer và auth provider cho form login không được minh họa, phải bổ sung cho ứng dụng thực.

**Chú ý về CSRF token repository:** Nếu browser là SPA dùng cookie phiên, cần luồng cấp và gửi token tương thích `CsrfTokenRepository`/`CsrfTokenRequestHandler`, kể cả deferred token và masked/XOR token của Spring Security ở những cấu hình liên quan. Không tắt CSRF chỉ vì SPA chưa gửi đúng header.

### 5.2. Ghi chú ngắn cạnh matcher, hồ sơ đầy đủ ở nơi review được

Một comment như “`// ignore csrf for webhook`” là **thiếu thông tin**. Comment tốt nên chỉ tới exception ID, hợp đồng credential và test; bản ghi đầy đủ chứa chủ sở hữu, giả thiết và lý do.

Ví dụ:

```java
// CSRF-EX-PAY-001: HMAC trên raw body + timestamp/event ID;
// không chấp nhận cookie auth; tests: PaymentWebhookSecurityIT.
// Rà soát khi thêm callback hoặc thay đổi gateway path.
csrf.ignoringRequestMatchers(paymentWebhookPost);
```

Đoạn trên là **minh họa về cách ghi comment**, không phải lời khuyên dán một dòng DSL rời rạc vào vị trí không có biến `csrf`. Khi đưa vào code thật, đặt comment trong cấu hình lambda phù hợp.

## 6. Ghi ngoại lệ trong WebFlux Reactive

WebFlux sử dụng `SecurityWebFilterChain`, `ServerWebExchangeMatcher` và `CsrfWebFilter`. Không bê nguyên `RequestMatcher` của Servlet sang `ServerHttpSecurity`.

Ví dụ WebFlux giữ hai vùng bearer-only và browser fallback như Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/m2m/**"))
        .securityContextRepository(
            NoOpServerSecurityContextRepository.getInstance())
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .oauth2ResourceServer(resource -> resource
            .jwt(Customizer.withDefaults()))
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.POST, "/api/m2m/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyExchange().denyAll())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browserAndWebhook(ServerHttpSecurity http) {
    ServerWebExchangeMatcher requireCsrf = exchange -> {
        HttpMethod method = exchange.getRequest().getMethod();
        String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

        boolean safeMethod =
            method == HttpMethod.GET
                || method == HttpMethod.HEAD
                || method == HttpMethod.OPTIONS
                || method == HttpMethod.TRACE;

        // CSRF-EX-PAY-001: chỉ POST đúng callback.
        boolean paymentWebhookPost =
            method == HttpMethod.POST
                && "/integrations/payment-events".equals(path);

        return !safeMethod && !paymentWebhookPost
            ? ServerWebExchangeMatcher.MatchResult.match()
            : ServerWebExchangeMatcher.MatchResult.notMatch();
    };

    return http
        .csrf(csrf -> csrf
            .requireCsrfProtectionMatcher(requireCsrf))
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.POST, "/integrations/payment-events")
                .permitAll()
            .pathMatchers(HttpMethod.GET, "/register").permitAll()
            .pathMatchers(HttpMethod.POST, "/register").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Khi gọi `requireCsrfProtectionMatcher(...)`, ta **thay thế matcher yêu cầu CSRF**, vì vậy phải thể hiện đúng tập safe methods theo quy tắc dự kiến. Nếu nhầm logic boolean và vô tình trả `notMatch()` cho tất cả `POST`, ngoại lệ sẽ lan rộng; regression test phải phát hiện.

`NoOpServerSecurityContextRepository` làm chain bearer không tải/lưu security context từ WebSession theo chính sách đó, nhưng **không tự vô hiệu hóa mọi custom WebFilter có thể đọc cookie**. Test cookie-only bằng WebSession hợp lệ vẫn bắt buộc.

## 7. Kiểm thử Servlet với MockMvc: âm/dương và giới hạn ngoại lệ

Đối với mỗi ngoại lệ, test nên đi **qua Spring Security filter chain thật**. Một unit test gọi controller trực tiếp không chứng minh CSRF matcher đúng.

Các đoạn code dưới đây là **mẫu cấu trúc test**, giả định có bean `MockMvc` đã gắn Spring Security, controller và service test fixture tương ứng. Một số HTTP status dương phụ thuộc hợp đồng handler; hãy thay kỳ vọng 201/204 theo ứng dụng thực.

### 7.1. Browser form: chứng minh không bị ngoại lệ lan sang

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void browserOrderWithoutCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/orders")
            .with(user("alice").roles("USER"))
            .contentType("application/json")
            .content("{\"sku\":\"A42\",\"quantity\":1}"))
        .andExpect(status().isForbidden());
}

@Test
void browserOrderWithWrongCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/orders")
            .with(user("alice").roles("USER"))
            .with(csrf().useInvalidToken())
            .contentType("application/json")
            .content("{\"sku\":\"A42\",\"quantity\":1}"))
        .andExpect(status().isForbidden());
}

@Test
void browserOrderWithValidCsrfCanProceed() throws Exception {
    mockMvc.perform(post("/web/orders")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType("application/json")
            .content("{\"sku\":\"A42\",\"quantity\":1}"))
        .andExpect(status().isCreated());
}
```

Test dương chứng minh request có thể qua CSRF và đến nghiệp vụ khi principal có quyền. Nếu chỉ thấy cả ba request đều 403, đừng tuyên bố test đã bảo đảm CSRF: có thể `denyAll` hoặc controller trả 403.

### 7.2. Webhook: thiếu token phải đến verifier, không đến nghiệp vụ khi giả

Test dương phải tạo chữ ký HMAC hợp lệ **theo contract fixture**, dùng clock kiểm soát được và một event mới. Test âm phải cố ý làm sai **duy nhất** một điều kiện để xác định nguyên nhân.

```java
// Fixture giả định có signHook(body, timestamp, testSecret)
// và thời gian hiện tại dùng Clock cố định trong verifier.
@Test
void signedWebhookDoesNotRequireCsrfToken() throws Exception {
    byte[] rawBody =
        "{\"id\":\"evt_101\",\"type\":\"payment.completed\"}"
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);

    mockMvc.perform(post("/integrations/payment-events")
            .contentType("application/json")
            .content(rawBody)
            .header("X-Hook-Timestamp", testTimestamp)
            .header("X-Hook-Signature",
                signHook(rawBody, testTimestamp, testSecret)))
        .andExpect(status().isNoContent());

    // Ngoài response: assert event được ghi và side effect đúng 1 lần.
}

@Test
void forgedWebhookIsRejectedWithoutSideEffect() throws Exception {
    byte[] rawBody = "{}".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

    mockMvc.perform(post("/integrations/payment-events")
            .contentType("application/json")
            .content(rawBody)
            .header("X-Hook-Timestamp", testTimestamp)
            .header("X-Hook-Signature", "invalid"))
        .andExpect(status().isUnauthorized());

    // Assert service không áp dụng event chưa được xác minh.
}
```

`testTimestamp`, `testSecret`, `signHook` và handler là test fixtures giả định; chúng không có sẵn trong framework. Với provider thật, phải ký **raw bytes** theo chính xác đặc tả của nhà cung cấp. Đừng parse JSON rồi serialize lại trước khi ký nếu hợp đồng yêu cầu raw body.

Ngoài hai test trên, cần:

- POST cùng body nhưng chữ ký được tạo cho body khác; phải từ chối.
- Timestamp quá hạn hoặc tương lai bất thường; phải từ chối.
- Gửi lại event ID đã xử lý; không lặp side effect.
- Cookie session hợp lệ nhưng thiếu hoặc sai chữ ký; phải từ chối.
- PUT cùng path, POST đến path gần giống `/integrations/payment-events/test`: không được exempt.
- POST browser có cookie nhưng thiếu CSRF token: tiếp tục bị CSRF chặn.

**Một điểm thường bỏ sót:** Response 401 chữ ký sai không chứng minh CSRF exemption đúng; nếu request bị 403 từ `CsrfFilter` trước verifier thì test không đo đúng điều mong muốn. Cần test dương chữ ký đúng, không CSRF token, thực sự đi đến handler.

### 7.3. Bearer API: JWT hợp lệ và cookie fallback

Test bằng mock JWT có thể kiểm tra CSRF/authorization:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void bearerOnlyOrderWithJwtDoesNotNeedCsrfToken() throws Exception {
    mockMvc.perform(post("/api/m2m/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")))
            .contentType("application/json")
            .content("{\"sku\":\"A42\",\"quantity\":1}"))
        .andExpect(status().isCreated());
}
```

`jwt()` giả lập authentication; **không** chứng minh `JwtDecoder` đã kiểm tra chữ ký, issuer, audience và expiry. Cần thêm integration test với signed token thực và auth filter chain đầy đủ.

Để chứng minh không có cookie fallback, hãy:

1. Đăng nhập browser bằng luồng session thực trong test, tạo **session/cookie hợp lệ**.
2. Chứng minh session đó truy cập được endpoint browser cần đăng nhập.
3. Dùng chính cookie/session ấy gọi `POST /api/m2m/orders` không bearer; yêu cầu từ chối.
4. Gọi lại với bearer sai + cookie hợp lệ; yêu cầu từ chối.
5. Với JWT thật hợp lệ và đủ scope, request đi tiếp; JWT không đủ scope bị từ chối.

**Không dùng `with(user("alice"))` làm phép thử cookie fallback**: nó chèn authentication trực tiếp và có thể che khuất đường xác thực mà server dùng khi nhận cookie. Cũng không dùng cookie tự đặt ngẫu nhiên; cookie vô hiệu bị từ chối không chứng minh hệ thống an toàn với **cookie hợp lệ**.

### 7.4. Test method và path: không dựa vào 404

Nếu route không có handler PUT, `PUT /integrations/payment-events` không CSRF token có thể bị filter CSRF chặn trước routing hoặc cuối cùng trả 405 khi CSRF tắt. Chỉ thấy 405 không đủ để chứng minh matcher có hay không khớp.

Để kiểm tra đúng ranh giới, có thể tạo handler test-only phù hợp cho method/path gần giống trong integration test, bảo đảm toàn bộ filter chain được gọi, và kiểm tra 403 khi thiếu token, đi tiếp khi có token cùng authentication hợp lệ. Một test route không tồn tại chỉ kiểm tra routing, không xác nhận biên CSRF.

## 8. Kiểm thử Reactive với WebTestClient

Đối với `WebTestClient`, phải gắn `SecurityWebFilterChain` của ứng dụng thử nghiệm. Kiểm thử với `mockUser` hoặc `mockJwt` thuận tiện để cô lập CSRF/authorization, nhưng cần thêm test thực về token/cookie và auth resolver.

### 8.1. Browser POST vẫn cần token

```java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactiveBrowserPostWithoutCsrfIsForbidden() {
    webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/web/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"sku\":\"A42\",\"quantity\":1}")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void reactiveBrowserPostWithCsrfCanProceed() {
    webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/web/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"sku\":\"A42\",\"quantity\":1}")
        .exchange()
        .expectStatus().isCreated();
}
```

Một route browser POST mới thêm vào `/api/web/**` cũng phải có cặp test tương tự, đặc biệt khi trước đây hệ thống chỉ có API bearer-only.

### 8.2. Bearer-only Reactive: không yêu cầu CSRF nhưng cần JWT

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@Test
void reactiveBearerOnlyPostDoesNotNeedCsrf() {
    webTestClient.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")))
        .post().uri("/api/m2m/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"sku\":\"A42\",\"quantity\":1}")
        .exchange()
        .expectStatus().isCreated();
}
```

`mockJwt()` không thay thế test kiểm tra JWT decoder thật. Test **WebSession đã xác thực hợp lệ**, không bearer và bearer sai + cookie hợp lệ giúp chứng minh `NoOpServerSecurityContextRepository` và các custom WebFilters không tạo session fallback.

### 8.3. Webhook Reactive: từ CSRF matcher đến verifier

Với `POST /integrations/payment-events`, cần WebTestClient test chữ ký hợp lệ không CSRF token được đến verifier, chữ ký sai bị từ chối, event trùng không lặp tác động. Đặc biệt, đừng viết một filter đọc body Reactive để xác minh mà không bảo đảm controller còn đọc được body nếu không cache/propagate đúng: body của WebFlux là stream, và signer phải dùng **bytes chính xác theo hợp đồng**.

## 9. Từ test riêng lẻ thành ma trận hồi quy trong CI

Một exception record chỉ đáng tin khi test của nó được chạy **mỗi khi thay đổi làm giả thiết có thể sai**.

### 9.1. Phân tầng kiểm thử

| Tầng | Mục đích | Rủi ro nếu thiếu |
|---|---|---|
| Unit test matcher | Kiểm tra method/path boolean chính xác | Lỗi wildcard, phủ nhầm POST khác |
| Security integration test | Chạy qua các filter Spring Security thật | Không phát hiện chain sai, CSRF chưa chạy hoặc auth fallback |
| Controller/handler test | Đảm bảo từ chối trước side effect | Ngoại lệ đúng nhưng verifier thiếu/bypass |
| Token/crypto integration test | JWT decoder, HMAC raw body, timestamp, replay | Mock authentication che lỗi xác minh thực |
| E2E browser test | SameSite, CORS, cookie/session, CSRF header/token lifecycle | Test server qua mà browser thực không hoạt động hoặc bị yếu bảo mật |
| Deployment smoke test | Reverse proxy, context path, forwarded headers, TLS | Path internal khác dẫn đến matcher sai |

Không cần mọi ngoại lệ có cùng số lượng test nếu mô hình khác nhau, nhưng **không được thiếu test chứng minh chính giả thiết an toàn**.

### 9.2. Định nghĩa cổng CI

Một cổng CI thực dụng yêu cầu cho mỗi thay đổi matcher hoặc route:

- Có ngoại lệ với mã ID và người phụ trách.
- Method/path/chain trong hồ sơ khớp cấu hình và request thực tế.
- Có **positive test** chứng minh client được phép hoạt động không có CSRF token nếu exemption hợp lệ.
- Có **negative tests** chứng minh credential giả, route gần giống, method khác không lọt.
- Có test bảo vệ **endpoint browser lân cận** không mất CSRF.
- Không có route mới ngoài fallback security chain hoặc lọt `web.ignoring()`.
- Không có code đổi bearer-only sang cookie auth mà không đánh giá lại hồ sơ.
- Có kết quả test trên Servlet/WebFlux tương ứng với stack của module; nếu ứng dụng dùng cả hai, chạy cả hai bộ.
- Với thay đổi gateway/cookie/origin, có E2E hoặc smoke test phù hợp.

Chỉ “test suite xanh” không đủ nếu test thực tế không bao phủ giả thiết ngoại lệ. Cần kiểm tra **mối liên hệ exception ID ↔ test cases** trong review.

### 9.3. Ví dụ tên test dễ trace theo hồ sơ

```text
CSRF-EX-PAY-001
  signedWebhookWithoutCsrfIsAccepted
  webhookWithInvalidSignatureIsRejected
  webhookReplayedEventIsIdempotent
  webhookWithBrowserSessionButNoSignatureIsRejected
  putOnWebhookPathStillRequiresCsrf
  adjacentWebhookPathStillRequiresCsrf
  browserOrderStillRequiresCsrf

CSRF-EX-M2M-002
  bearerWithRequiredScopeDoesNotNeedCsrf
  bearerWithInvalidJwtIsRejected
  bearerWithMissingScopeIsRejected
  validBrowserSessionWithoutBearerIsRejected
  invalidBearerWithValidSessionIsRejected
  webRouteStillRequiresCsrf
```

Tên test nên nêu **nguyên nhân mong muốn**, không chỉ `returns403`. Ghi link test vào record và đánh dấu test bị xóa/đổi tên là tín hiệu yêu cầu review.

## 10. Những thay đổi buộc phải đánh giá lại ngoại lệ

Ngoại lệ có thể đúng ở thời điểm viết nhưng sai khi phạm vi sản phẩm mở rộng. Các trigger quan trọng:

| Thay đổi | Giả thiết có nguy cơ sai | Việc phải làm |
|---|---|---|
| Thêm SPA hoặc BFF gọi endpoint m2m | “Không có browser credential” | Kiểm tra có cookie auth không; tách browser route/chain |
| Chuyển JWT từ header sang cookie | “Bearer-only” | Bật CSRF trên đường cookie, test cookie-only và token |
| Thêm refresh token vào HttpOnly cookie | “Mọi API đều bearer” | Đánh giá `POST /auth/refresh` riêng, không miễn chung |
| Thêm endpoint dưới `/integrations/**` | “Tất cả routes là webhook ký số” | Kiểm tra path/method mới có bị exempt; thu hẹp matcher |
| Đổi provider webhook/giao thức ký | “HMAC ký raw body theo secret cũ” | Cập nhật verifier và test timestamp/replay |
| Thay thứ tự `@Order`, security matcher | “Request chọn đúng chain” | Test first-match, fallback, cookie bearer routes |
| Thêm custom authentication resolver/filter | “Không cookie fallback” | Test bearer sai + session hợp lệ |
| Thêm form login, logout hoặc OAuth2 Login | “Chain không dùng session” | Rà soát route login/logout, CSRF token lifecycle |
| Đổi reverse proxy, context path, servlet mapping | “Matcher nhìn thấy path cũ” | Test URL public và internal sau rewrite |
| Thêm GraphQL/RPC/multipart endpoint | “Tất cả unsafe routes đã được kiểm kê” | Đánh giá POST mutation/upload và session cookie |
| Đổi CORS origin/cookie SameSite | “Browser không gửi credential ngoài dự tính” | Browser tests, preflight và CSRF token |
| Đổi Spring Security version | “DSL, matcher, token repository hoạt động như cũ” | Review CSRF handler, deferred tokens, integration tests |
| Thay CSP/HSTS/security headers | “Các lớp bảo vệ browser vẫn áp dụng” | Test headers và luồng XSS/CORS; không thay CSRF |
| Dọn/xóa test | “Giả thiết luôn được kiểm chứng” | Chặn merge hoặc viết test thay thế |

Thêm ngày rà soát định kỳ theo quy trình của tổ chức, nhưng **event-driven review** quan trọng hơn: sự kiện thay đổi credential/chain không thể chờ đến kỳ review tiếp theo.

### 10.1. Điều kiện để rút ngoại lệ

Ngoại lệ cần được sửa hoặc thu hồi khi:

- Endpoint không còn phục vụ webhook/bearer-only như hồ sơ.
- Server chấp nhận session cookie/JWT cookie làm authentication ở route được miễn CSRF.
- Không còn chứng minh được xác thực HMAC/JWT hoặc chống replay phù hợp.
- Đường dẫn/method thay đổi làm matcher quá rộng hoặc sai.
- Owner hoặc regression tests không còn tồn tại; bằng chứng bảo vệ không được duy trì.

Khi thu hồi một exemption, không chỉ xóa rule mà bỏ mặc client lỗi. Cần thiết kế luồng cấp/gửi CSRF token cho browser hoặc tách lại route/chain cho server-to-server, rồi triển khai có kiểm soát.

## 11. Những false positive phổ biến khi kiểm thử CSRF

### 11.1. “POST bị 403, vậy CSRF hoạt động”

Không nhất thiết. `denyAll`, thiếu scope, thiếu session hoặc exception nghiệp vụ cũng có thể trả 403. **Test với token hợp lệ, cùng user/quyền và body hợp lệ** để chứng minh request tới handler khi vượt qua CSRF.

### 11.2. “PUT webhook trả 404, vậy đã giới hạn ngoại lệ đúng”

Không đủ. 404 chỉ có thể nghĩa là không có route. `CsrfFilter` có thể chặn trước routing hoặc không được gọi. Cần trace filter hoặc fixture route/test phù hợp để đánh giá đúng matcher.

### 11.3. “Có `permitAll`, webhook được phép không cần CSRF”

Sai. `permitAll` không tắt `CsrfFilter`/`CsrfWebFilter`. Nếu chỉ thêm authorization mà không miễn POST webhook, request có thể bị 403 vì thiếu token trước khi verifier chạy. Ngược lại, exemption CSRF không tự xác thực chữ ký.

### 11.4. “API stateless nên không cần CSRF”

Sai khi JWT được lấy từ cookie: browser vẫn tự gửi cookie dù backend không dùng HttpSession. CSRF phụ thuộc **credential transport và đường server chấp nhận**, không phải nhãn REST/stateless.

### 11.5. “CORS đã chặn cross-origin nên không cần CSRF”

CORS không ngăn mọi form POST cross-site và không xác thực máy chủ gửi webhook. Nếu server xác thực bằng cookie, vẫn cần CSRF token hoặc thiết kế bảo vệ phù hợp. CORS preflight OPTIONS thường không mang credential và mặc định không cần CSRF token; lỗi preflight không chứng minh CSRF sai.

### 11.6. “Có `X-Content-Type-Options` nghĩa là security chain đúng”

Header có thể được gateway thêm hoặc đến từ chain khác. Một header đơn lẻ không chứng minh CSRF/authorization đã chạy. Hãy xác nhận chain selection, token thiếu/sai/đúng và auth flow.

### 11.7. “`web.ignoring` là ngoại lệ CSRF tiết kiệm hơn”

Không đúng. Nó có thể bỏ các security filters của Spring Security cho request, bao gồm CSRF, authentication, authorization và headers trong chain. Nếu muốn endpoint public, thường dùng `permitAll`. Nếu cần bỏ CSRF cho webhook, dùng matcher hẹp và giữ những lớp khác.

### 11.8. “MockJwt và mockUser đủ kiểm tra cookie fallback”

Các test helper đó có thể chèn authentication trực tiếp. Phải có integration test sử dụng **cookie/session hợp lệ thực sự** qua filter chain của ứng dụng, không chỉ synthetic security context.

### 11.9. “Đã bảo vệ endpoint bằng CSRF token nên không cần kiểm tra nghiệp vụ”

CSRF không thay validation, rate limits, authentication, authorization hay quyền tài nguyên. Với webhook, chữ ký hợp lệ còn cần tenant/order, state machine, idempotency và replay prevention. Bằng chứng “CSRF pass” không thay thế chúng.

## 12. Bài tập tình huống: ngoại lệ mở rộng sau một lần refactor

Ban đầu đội phát triển có:

```java
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    "/integrations/**", "/api/**"));
```

Khi viết rule này, `/integrations/**` chỉ chứa webhook có HMAC, còn `/api/**` chỉ chứa backend clients dùng bearer header.

Sau ba tháng, nhóm khác thêm:

- `POST /integrations/admin/replay`: giao diện quản trị dùng session cookie.
- `POST /api/web/profile`: SPA dùng JWT trong `HttpOnly` cookie.
- `POST /api/m2m/orders`: native app vẫn dùng bearer header.
- `POST /auth/refresh`: browser dùng refresh token trong cookie.
- `POST /integrations/payment-events`: webhook thật có chữ ký.
- `GET /orders/42/cancel`: route GET mới có tác dụng hủy đơn.

**Yêu cầu:** Viết hồ sơ/điều kiện tái đánh giá, chỉ ra các ngoại lệ không còn cơ sở và lập ma trận test tối thiểu.

**Phân tích đáp án:**

1. `POST /integrations/admin/replay` bị wildcard `/integrations/**` miễn CSRF dù dùng cookie session. Phải rời khỏi vùng webhook exempt, giữ CSRF và quyền admin.
2. `POST /api/web/profile` bị wildcard `/api/**` miễn CSRF dù JWT nằm trong cookie. Phải vào browser chain có CSRF token và quyền đúng user.
3. `POST /api/m2m/orders` có thể ở bearer-only chain riêng tắt CSRF nếu không có cookie fallback; JWT, scope và phân quyền vẫn bắt buộc.
4. `POST /auth/refresh` không mặc nhiên cần ngoại lệ chỉ vì “API dùng JWT”; đây là endpoint dùng credential ambient, cần đánh giá CSRF và rotation/token lifecycle.
5. `POST /integrations/payment-events` được miễn đúng method/path **khi** HMAC, timestamp, replay, idempotency và quyền event đã được chứng minh.
6. `GET /orders/42/cancel` là lỗi thiết kế HTTP: phải chuyển hành động hủy đơn sang method không an toàn thích hợp rồi bảo vệ CSRF nếu dùng session.
7. Cập nhật exception record cho webhook và bearer-only: có owner, route/chain, giả thiết cookie, kiểm thử chữ ký, cookie-only và trigger review khi client/auth thay đổi.
8. Viết test browser POST thiếu/sai/đúng token, webhook signed/forged/replay, bearer JWT đúng/sai/thiếu scope và session-only, method/path gần giống; kiểm tra side effect để tránh false positive.

**Đề xuất thiết kế:** `/integrations/payment-events` có ngoại lệ chính xác; `/api/m2m/**` có bearer-only chain tách biệt; `/api/web/**` và các form browser đi qua fallback chain với CSRF. Không dùng các wildcard trên như lý do chung để tắt CSRF.

## 13. Checklist review ngoại lệ trước khi merge

- [ ] Mỗi ngoại lệ có **ID, owner, người review và nơi lưu hồ sơ**.
- [ ] Ghi rõ lý do nghiệp vụ, client, method, path, chain, credential server chấp nhận.
- [ ] Giả thiết “không cookie/session fallback” đã có test với **phiên browser hợp lệ**, không chỉ cookie giả.
- [ ] Nếu miễn webhook, đã xác minh chữ ký theo raw body/contract, timestamp, replay và idempotency.
- [ ] Nếu miễn bearer-only, JWT được kiểm tra chữ ký, issuer, audience, expiry, scope và quyền tài nguyên.
- [ ] Ngoại lệ có phạm vi đúng method/path; wildcard chỉ dùng khi có hợp đồng và test đủ rộng.
- [ ] Không có endpoint browser dùng session/JWT cookie lọt vào CSRF-off chain.
- [ ] CSRF vẫn bật cho browser form/login/logout, GraphQL mutation và các unsafe methods có credential ambient.
- [ ] `permitAll`, `csrf.disable()`, `ignoringRequestMatchers`, `requireCsrfProtectionMatcher` và `web.ignoring` không bị nhầm lẫn.
- [ ] Đã xác minh chain đầu tiên khớp, thứ tự `@Order` và fallback phù hợp.
- [ ] Có **positive test không CSRF** cho client được miễn có authentication/chữ ký hợp lệ.
- [ ] Có negative test credential sai/thiếu, timestamp/replay, method/path gần giống và cookie fallback.
- [ ] Có **negative + positive tests** cho browser POST token thiếu/sai/đúng.
- [ ] Test đi qua Spring Security filters, không chỉ test controller trực tiếp.
- [ ] Đã kiểm tra side effect: request giả không thay đổi dữ liệu, request hợp lệ được xử lý đúng một lần.
- [ ] Không dùng 403/404/405 đơn lẻ làm bằng chứng; có trace/fixture phân biệt nguồn từ chối.
- [ ] Đã thử URL sau reverse proxy/context path và preflight CORS khi cần.
- [ ] Security headers, CSP, HSTS, HTTP firewall và session được đánh giá đúng vai trò riêng.
- [ ] Test được gắn ID ngoại lệ, chạy trong CI và có người duy trì khi refactor.
- [ ] Hồ sơ có trigger thu hồi/tái đánh giá khi đổi token storage, thêm browser, đổi auth filter hoặc route.
- [ ] Có kế hoạch thay thế ngoại lệ nếu hợp đồng cũ không còn đúng; không chữa 403 bằng tắt CSRF rộng.
- [ ] Không ghi secret, raw bearer token, session cookie hoặc payload nhạy cảm vào hồ sơ/test log.

**Ghi nhớ:** **Một ngoại lệ CSRF chỉ an toàn khi các giả thiết của nó vẫn đúng và kiểm thử hồi quy liên tục chứng minh điều đó.** Hãy ghi rõ method, path, client, credential, chain, phòng vệ thay thế, owner và trigger review; kết hợp test dương/âm cho chính ngoại lệ với test bảo vệ browser endpoint lân cận. Cách làm này biến một quyết định cấu hình thành một cam kết bảo mật có thể kiểm toán và duy trì trên cả Servlet lẫn Reactive.
