# Request từ server hoặc mobile không bị CORS giới hạn

Cross-Origin Resource Sharing (CORS) là cơ chế của trình duyệt web để kiểm soát JavaScript ở một origin có được đọc response từ origin khác hay không. CORS mở rộng hoặc giới hạn quyền đọc response theo chính sách do server công bố; nó không xác thực người gọi và không quyết định người gọi có quyền truy cập dữ liệu hay không.

Một API vẫn có thể được gọi trực tiếp bằng `curl`, Postman, backend service, script hoặc ứng dụng mobile native mà không chịu cơ chế CORS của trình duyệt. Vì vậy, nếu server chỉ dựa vào CORS để bảo vệ endpoint, dữ liệu vẫn có thể bị truy cập qua các client không phải browser. API Security phải thực thi authentication, function authorization, object authorization và tenant isolation ở server cho mọi request, bất kể request đến từ trình duyệt, mobile hay một service khác.

## 1. CORS giải quyết vấn đề gì?

Trình duyệt áp dụng Same-Origin Policy (SOP) để hạn chế một trang web đọc dữ liệu từ origin khác. Origin được xác định bởi bộ ba:

- Scheme, ví dụ `https`.
- Host, ví dụ `app.example.test`.
- Port, ví dụ `443`.

Do đó, `https://app.example.test` và `https://api.example.test` là hai origin khác nhau dù có cùng domain gốc. `http://app.example.test` cũng khác `https://app.example.test` vì scheme khác.

SOP ngăn một trang web tùy ý dùng JavaScript đọc response từ website khác. CORS cho phép server chỉ định origin nào được browser cho phép đọc response bằng các response header như:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Authorization, Content-Type
```

Browser đọc các header này và quyết định có cho JavaScript truy cập response hay không. Server vẫn nhận request theo cơ chế HTTP thông thường; CORS không phải một lớp authentication nằm trước controller.

## 2. Vì sao request từ server hoặc mobile không bị CORS giới hạn?

CORS là chính sách do user agent của trình duyệt thực thi. Một HTTP client thông thường không có nghĩa vụ thực thi CORS. Ví dụ:

| Client | Có bị browser CORS enforcement áp dụng không? | Cần bảo vệ API bằng gì? |
|---|---|---|
| JavaScript `fetch` trong browser | Có | CORS cho quyền đọc response; server vẫn cần authentication/authorization |
| `XMLHttpRequest` trong browser | Có | Tương tự `fetch` |
| HTML form hoặc navigation | Không giống cơ chế đọc response của `fetch`; browser có các hạn chế SOP riêng | CSRF protection và server-side authorization |
| `curl` hoặc Postman | Không | Authentication, authorization, rate limit và validation |
| Backend service gọi HTTP API | Không | Workload identity, mTLS/OAuth, permission và object policy |
| Mobile app dùng native HTTP stack | Thông thường không | Secure token storage, TLS, authentication và authorization |
| WebView chạy JavaScript | Có thể có, tùy engine và cách gọi mạng | CORS cho nội dung web trong WebView; API vẫn cần authorization |
| React Native hoặc framework hybrid | Phụ thuộc networking implementation | Không giả định CORS luôn được áp dụng; kiểm tra stack thực tế và bảo vệ server |

Ví dụ một người dùng có thể gọi API từ terminal:

```bash
curl -i https://api.example.test/api/invoices/INV-1001 \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`curl` không cần `Access-Control-Allow-Origin` để gửi request hoặc đọc response. Nếu token hợp lệ và server không kiểm tra quyền trên invoice, request vẫn có thể trả dữ liệu ngoài phạm vi.

Tương tự, một mobile app native có thể gọi API bằng networking library của hệ điều hành. Việc app không chạy trong browser không làm API tự an toàn hơn; server vẫn phải xác minh token, scope, tenant và object permission.

## 3. CORS không phải authentication hoặc authorization

Ba cơ chế này có mục tiêu khác nhau:

| Cơ chế | Câu hỏi được trả lời | Nơi thực thi |
|---|---|---|
| CORS | JavaScript từ origin này có được browser cho đọc response không? | Browser dựa trên response header của server |
| Authentication | Caller là ai? Credential có hợp lệ không? | Server hoặc identity-aware gateway/service |
| Function authorization | Caller có được gọi chức năng này không? | Server-side policy |
| Object authorization | Caller có được thao tác trên object cụ thể không? | Service/domain/data layer |
| Tenant isolation | Request có bị giới hạn trong tenant hợp lệ không? | Server-side context, query, cache và storage policy |
| CSRF protection | Request có bị một site khác lợi dụng browser credentials tự động gửi hay không? | Server và browser cookie/request controls |

Không được viết logic như “origin nằm trong allowlist thì cho phép đọc dữ liệu”. Một origin được phép CORS không chứng minh người dùng đang đăng nhập hoặc có quyền trên object. Một request từ origin hợp lệ vẫn có thể mang token của user không có quyền.

Ngược lại, request không có `Origin` header không có nghĩa là request đáng tin cậy. Server-to-server client, `curl` và nhiều mobile client không gửi `Origin`; client bất kỳ cũng có thể tự tạo header này.

## 4. Browser CORS hoạt động như thế nào?

Với một số cross-origin request đơn giản, browser có thể gửi request trực tiếp rồi chỉ cho JavaScript đọc response nếu CORS response header phù hợp. Với request cần preflight, browser gửi `OPTIONS` trước để hỏi server xem method và header dự kiến có được phép không.

```mermaid
sequenceDiagram
    participant JS as JavaScript ở app.example.test
    participant B as Browser
    participant API as api.example.test
    JS->>B: fetch cross-origin (PATCH + Authorization)
    B->>API: OPTIONS preflight + Origin + requested method/headers
    API-->>B: Access-Control-Allow-Origin/Methods/Headers
    alt Preflight được phép
        B->>API: PATCH request thực tế
        API->>API: Authentication + authorization + business logic
        API-->>B: Response
        B-->>JS: Cho phép đọc response nếu CORS hợp lệ
    else Preflight bị từ chối
        B-->>JS: CORS error; request thực tế không được gửi
    end
```

Preflight thường được kích hoạt bởi method như `PUT`, `PATCH`, `DELETE` hoặc các request có header không thuộc nhóm CORS-safelisted, ví dụ `Authorization` hoặc `Content-Type: application/json`. Chi tiết phụ thuộc method, header và content type thực tế.

Điểm quan trọng: preflight là một bước browser hỏi trước khi gửi một số loại request. Nó không thay thế việc server kiểm tra quyền trên request thực tế. Một client không phải browser có thể bỏ qua preflight hoàn toàn và gọi thẳng method.

## 5. Simple request vẫn có thể tới server dù JavaScript không đọc được response

Đây là điểm dễ gây hiểu nhầm. Với request thuộc nhóm simple request, browser có thể gửi request cross-origin mà không cần preflight. Nếu response không có CORS header phù hợp, JavaScript không được đọc response, nhưng request có thể đã được server xử lý.

Ví dụ, một trang độc hại có thể tạo form gửi request tới website mà người dùng đang đăng nhập. Browser có thể tự đính kèm cookie phù hợp theo chính sách cookie. CORS có thể ngăn trang độc hại đọc response, nhưng không nhất thiết ngăn request làm thay đổi trạng thái.

Vì vậy, không dùng CORS làm CSRF protection. Với endpoint thay đổi trạng thái dựa trên cookie/session, cần CSRF token hoặc cơ chế tương đương, kiểm tra `Origin`/`Referer` theo policy khi phù hợp, cấu hình `SameSite` đúng và tránh các thao tác thay đổi trạng thái qua `GET`.

## 6. `Origin` header không phải bằng chứng danh tính

Browser thường tự đặt `Origin` cho các request liên quan đến CORS. Tuy nhiên, HTTP client ngoài browser có thể gửi một header `Origin` tùy ý:

```http
GET /api/admin/users HTTP/1.1
Host: api.example.test
Origin: https://trusted-frontend.example.test
```

Attacker dùng `curl` có thể tự thêm `Origin` như trên. Do đó, server không được dùng `Origin` làm bằng chứng rằng request thực sự đến từ frontend được tin cậy hoặc người dùng có quyền quản trị.

`Origin` có ích cho CORS và có thể là một tín hiệu trong CSRF defense ở browser flow. Nó không thay thế credential, client identity, permission hoặc tenant context. Nếu request cần xác thực, server phải xác minh token/session/mTLS theo contract dù header `Origin` có hợp lệ hay không.

## 7. CORS sai cấu hình có thể tạo rủi ro cho browser

Dù CORS không phải authorization, cấu hình quá rộng vẫn có thể cho một website độc hại đọc response chứa dữ liệu của người dùng nếu browser gửi credential.

Một số cấu hình cần tránh:

- Phản chiếu mọi giá trị `Origin` vào `Access-Control-Allow-Origin` mà không kiểm tra allowlist.
- Dùng wildcard hoặc regex domain quá rộng, ví dụ chấp nhận mọi subdomain do bên thứ ba kiểm soát.
- Cho phép `Origin: null` mà không có nhu cầu và phân tích rủi ro rõ ràng.
- Kết hợp credentialed request với allow-origin wildcard không hợp lệ hoặc cơ chế workaround không an toàn.
- Cho phép method/header quá rộng mà không cần thiết.
- Bật credential cho origin staging, preview hoặc domain cũ đã không còn kiểm soát.
- Dùng suffix matching ngây thơ, ví dụ kiểm tra chuỗi kết thúc bằng `example.test` khiến `attackerexample.test` có thể lọt qua.

Với credentialed CORS, server phải trả origin cụ thể được phép thay vì `*`, và thường cần `Access-Control-Allow-Credentials: true`. Nếu response thay đổi theo `Origin`, cần phát `Vary: Origin` để cache không dùng response của origin này cho origin khác.

## 8. Cấu hình CORS theo allowlist chính xác

Chỉ cho phép các origin thật sự cần gọi API từ browser. Origin bao gồm scheme, host và port; không thêm path. Ví dụ:

```text
https://app.example.test
https://admin.example.test
https://localhost:3000
```

Origin development nên tách khỏi production. Không đưa `http://*`, mọi subdomain hoặc preview domain không được kiểm soát vào allowlist production.

Ví dụ response cho một request được phép:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Expose-Headers: X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin
```

`Access-Control-Allow-Headers` cho biết browser được phép gửi những request header nào trong cross-origin request cần preflight. `Access-Control-Expose-Headers` cho biết JavaScript được đọc những response header nào ngoài nhóm được expose mặc định. `Access-Control-Max-Age` cho browser cache kết quả preflight trong thời gian giới hạn.

Không thêm header chỉ vì “có thể cần sau này”. Allowlist method/header hẹp giúp policy dễ kiểm tra và giảm bề mặt cấu hình.

## 9. Credentialed CORS và cookie

Nếu frontend dùng cookie/session cho cross-origin request, browser cần được cấu hình gửi credential, ví dụ `fetch(..., { credentials: "include" })`. Server phải trả origin cụ thể và:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không thể dùng `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true` theo chuẩn CORS. Một số cấu hình workaround bằng cách phản chiếu origin sẽ tạo rủi ro nếu không kiểm tra allowlist nghiêm ngặt.

Cookie cross-site còn chịu các thuộc tính `SameSite`, `Secure`, domain/path và chính sách của browser. CORS không làm cookie tự được gửi; client phải yêu cầu credentials và cookie phải đủ điều kiện gửi. Ngược lại, CORS cũng không thay thế CSRF protection khi cookie được browser tự động đính kèm.

## 10. Ví dụ cấu hình CORS trong Spring Boot

Có thể cấu hình CORS tập trung bằng `CorsConfigurationSource` và bật CORS trong Spring Security:

```java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(
                "https://app.example.test",
                "https://admin.example.test"));
        config.setAllowedMethods(List.of(
                "GET", "POST", "PATCH", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(false);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**")
                            .hasAuthority("SCOPE_admin:access")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
```

Đây là ví dụ cấu hình minh họa. Cần bổ sung import, dependency và policy authentication/CSRF theo ứng dụng. Với bearer token trong Authorization header và API stateless, CSRF có thể được cấu hình khác so với ứng dụng dùng cookie; không tắt CSRF một cách máy móc nếu browser tự gửi credential.

Spring Security cần xử lý CORS trước bước authentication để preflight `OPTIONS` không bị từ chối như một request API thông thường. Bật `.cors()` với `CorsConfigurationSource` giúp framework tích hợp filter theo thứ tự phù hợp. Không dùng `permitAll()` cho mọi `OPTIONS` như cách thay thế CORS policy; cần để CORS filter xác minh origin, method và header preflight.

Đoạn `anyRequest().authenticated()` chỉ xác minh caller đã đăng nhập. Các endpoint nghiệp vụ vẫn cần permission cụ thể, object authorization và tenant filter ở service. CORS allowlist không thay thế những kiểm tra đó.

Nếu frontend thực sự cần cookie cross-origin, đặt `setAllowCredentials(true)` và giữ `allowedOrigins` là danh sách origin cụ thể. Không bật credential với wildcard. Đồng thời cấu hình cookie `Secure`, `HttpOnly`, `SameSite` phù hợp và CSRF defense.

## 11. Ví dụ service-to-service không cần CORS

Một backend service gọi API khác không cần CORS để gửi request:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://billing.internal.example.test")
        .defaultHeader(HttpHeaders.AUTHORIZATION,
                "Bearer " + serviceAccessToken)
        .build();

Mono<InvoiceResponse> response = client.get()
        .uri("/internal/invoices/{id}", invoiceId)
        .retrieve()
        .bodyToMono(InvoiceResponse.class);
```

Ví dụ chỉ minh họa HTTP call. Trong production, không hardcode token; lấy credential ngắn hạn từ workload identity/token exchange hoặc secret manager theo kiến trúc. Service nhận vẫn phải xác minh issuer, audience, scope và service identity, rồi kiểm tra tenant/object policy. Không tin rằng request đến từ mạng nội bộ hoặc không có `Origin` thì được phép.

## 12. Ví dụ mobile native không dựa vào CORS

Mobile app native có thể gửi request qua HTTP client của nền tảng:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <mobile-access-token>
Accept: application/json
```

Server không cần trả CORS header để native HTTP client đọc response. Nhưng API vẫn phải kiểm tra token, scope, account state và quyền trên dữ liệu. Mobile app nên lưu refresh token trong secure storage do hệ điều hành cung cấp, dùng TLS và có quy trình rotation/revocation.

Không nhúng client secret có đặc tính confidential vào binary mobile vì người dùng có thể trích xuất. Native public client nên dùng OAuth Authorization Code Flow với PKCE theo hướng dẫn của identity provider. Với WebView, JavaScript chạy trong browser engine có thể chịu CORS; cần phân biệt request do native networking stack thực hiện và request do WebView JavaScript thực hiện.

## 13. CORS và CSRF không giống nhau

CSRF xảy ra khi browser tự động gửi credential của người dùng tới một site mà người dùng không chủ ý tương tác, khiến site đó kích hoạt hành động ngoài ý muốn. Cookie session là trường hợp cần chú ý vì browser có thể tự đính kèm cookie.

| Tình huống | CORS | CSRF |
|---|---|---|
| JavaScript cross-origin đọc response | CORS quyết định browser có cho đọc không | Không phải mục tiêu chính của CSRF |
| HTML form gửi request thay đổi trạng thái | CORS không bảo đảm request không tới server | Có thể là vector CSRF nếu server dựa vào cookie |
| `curl` gọi API | Không áp dụng CORS enforcement | Không phải browser CSRF; vẫn cần authentication/authorization |
| Mobile native gọi API | Thông thường không áp dụng CORS | Không phải CSRF kiểu browser cookie, nhưng vẫn cần bảo vệ token và quyền |
| Cookie tự động được gửi cross-site | CORS không thay thế cookie policy | Cần SameSite, CSRF token và/hoặc kiểm tra Origin theo thiết kế |

Với cookie-authenticated application, có thể kết hợp:

- CSRF token cho request thay đổi trạng thái.
- `SameSite=Lax` hoặc `Strict` nếu luồng sản phẩm cho phép; `None` cần `Secure` và đánh giá rủi ro.
- Kiểm tra `Origin` hoặc `Referer` cho state-changing request theo policy.
- Không dùng `GET` để thay đổi trạng thái.
- Kiểm tra content type và custom header khi phù hợp, nhưng không xem riêng một custom header là giải pháp hoàn chỉnh.

Với bearer token chỉ được JavaScript gắn vào Authorization header và không được browser tự gửi, mô hình CSRF khác cookie session. Tuy nhiên, XSS vẫn có thể đánh cắp token hoặc gọi API trong origin bị kiểm soát. CORS không phải XSS defense.

## 14. Không dùng CORS để bảo vệ API nội bộ

Một endpoint nội bộ không trở nên an toàn chỉ vì không có CORS header. Server-to-server client không cần CORS để gửi request. Nếu endpoint được expose qua private network, attacker có thể khai thác qua một service bị xâm nhập, SSRF hoặc network path khác.

API nội bộ vẫn cần:

- Workload identity hoặc mTLS để xác minh service caller.
- Audience và scope riêng cho service.
- Function authorization và object/tenant authorization.
- Network segmentation và egress/ingress policy như lớp bổ sung.
- Rate limit, timeout và validation.
- Audit, monitoring và credential rotation.

Không cho phép mọi request không có `Origin` header. Đây là điều kiện dễ bị client giả mạo và có thể vô tình mở API cho script hoặc service không được phép.

## 15. Kiểm thử CORS và authorization bằng nhiều loại client

Để chứng minh API an toàn, cần tách test CORS browser khỏi test authorization server-side.

| Test | Kết quả mong đợi |
|---|---|
| Browser từ origin allowlist gọi API | JavaScript đọc được response nếu authentication/authorization thành công |
| Browser từ origin không allowlist gọi API | Browser không cho JavaScript đọc response; server vẫn áp dụng auth/policy bình thường |
| Preflight từ origin hợp lệ với method/header được phép | Server trả CORS preflight headers phù hợp |
| Preflight với origin/method/header không được phép | Browser không gửi actual request cho request cần preflight |
| Simple cross-origin request không được allow | Request có thể tới server; không có CORS permission để JavaScript đọc response |
| `curl` không có Origin | Kết quả dựa trên authentication/authorization, không dựa vào CORS |
| `curl` tự thêm Origin hợp lệ | Không được xem Origin là danh tính hoặc quyền |
| Mobile native client gọi API | Kết quả dựa trên token và policy server-side |
| User A đọc object của User B bằng curl | Bị từ chối bởi object authorization |
| Service account gọi chức năng ngoài scope | Bị từ chối bởi function authorization |
| Credentialed CORS với wildcard | Cấu hình không hợp lệ hoặc bị từ chối; không phản chiếu origin tùy ý |
| Origin `null` hoặc domain suffix giả mạo | Không được allow nếu không có policy rõ ràng |
| Cookie cross-site state-changing request | CSRF defense ngăn request trái phép |
| Request trực tiếp tới backend bypass gateway | Service vẫn xác minh identity và authorization |

### Ví dụ test server-side bằng curl

Gọi cùng endpoint với token Alice nhưng ID object thuộc Bob:

```bash
curl -i https://api.example.test/api/invoices/INV-BOB \
  -H "Authorization: Bearer $ALICE_ACCESS_TOKEN"
```

Kết quả phải bị từ chối theo object policy, bất kể có `Origin` hay không. Có thể thêm `-H "Origin: https://app.example.test"` để chứng minh header Origin không thay đổi quyết định authorization.

### Ví dụ test preflight

```bash
curl -i -X OPTIONS https://api.example.test/api/invoices/INV-BOB \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```

`curl` chỉ hiển thị response preflight; nó không tự thực thi quy tắc CORS như browser. Để kiểm tra JavaScript có được đọc response hay không, cần browser automation hoặc test chạy trong browser thật.

## 16. Những sai lầm thường gặp

- **“Chỉ cho phép frontend domain là API an toàn.”** Sai: client ngoài browser không bị CORS enforcement và có thể gọi API trực tiếp.
- **“Không có CORS header thì request không tới server.”** Sai: simple request có thể đã được gửi; browser chỉ chặn JavaScript đọc response.
- **“Origin hợp lệ chứng minh request đến từ frontend.”** Sai: client ngoài browser có thể tự đặt header `Origin`.
- **“Preflight bảo vệ mọi request cross-origin.”** Sai: không phải mọi request đều preflight; form/simple request có hành vi khác.
- **“CORS thay CSRF.”** Sai: CORS chủ yếu kiểm soát quyền đọc response, còn CSRF liên quan việc browser tự gửi credential.
- **“API mobile không cần authorization vì app đã cài từ store.”** Sai: API có thể được gọi bằng script hoặc client tự viết; binary không phải ranh giới tin cậy.
- **“API nội bộ không cần authentication.”** Sai: mạng nội bộ có thể bị xâm nhập hoặc bị truy cập qua SSRF/service khác.
- **“Đã bật CORS trong gateway thì backend không cần kiểm tra quyền.”** Sai: service phải bảo vệ object và nghiệp vụ ở mọi entry point.

## 17. Checklist thiết kế

- [ ] CORS chỉ được xem là browser response-sharing policy, không phải authentication/authorization.
- [ ] API kiểm tra token/session/workload identity cho mọi client theo contract.
- [ ] Function permission, object permission và tenant scope được thực thi ở server.
- [ ] Không tin `Origin` là bằng chứng danh tính; request không có Origin vẫn phải được bảo vệ.
- [ ] Allowlist origin chính xác theo scheme/host/port; không reflection tùy ý hoặc suffix matching yếu.
- [ ] Credentialed CORS dùng origin cụ thể, `Access-Control-Allow-Credentials` phù hợp và `Vary: Origin` khi cần.
- [ ] Method/header được allow ở mức tối thiểu cần thiết.
- [ ] Preflight được xử lý đúng thứ tự trước authentication filter nhưng không biến thành quyền truy cập API.
- [ ] Simple request và CSRF được đánh giá riêng; cookie flow có SameSite/CSRF controls phù hợp.
- [ ] Mobile native, server-to-server và direct backend access được test như client độc lập với browser.
- [ ] Có test browser thật cho CORS và test curl/integration cho server-side authorization.
- [ ] Không dùng CORS để bảo vệ API nội bộ hoặc endpoint quản trị.
- [ ] Log và telemetry không ghi token/cookie khi kiểm thử nhiều client.

## Kết luận

CORS là cơ chế browser kiểm soát JavaScript có được đọc response cross-origin hay không. `curl`, Postman, backend service và mobile native HTTP client không bị browser CORS enforcement giới hạn, nên chúng có thể gọi API trực tiếp. Vì vậy, CORS chỉ là cấu hình chia sẻ response cho frontend; authentication, function authorization, object authorization, tenant isolation và CSRF protection phải được thiết kế riêng ở server/browser flow tương ứng. Hãy kiểm thử bằng browser để xác minh CORS và bằng client ngoài browser để chứng minh API vẫn từ chối caller không có quyền.
