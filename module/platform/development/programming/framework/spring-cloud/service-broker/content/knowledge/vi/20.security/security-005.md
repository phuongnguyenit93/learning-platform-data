# Lựa chọn chính sách CSRF phù hợp với API và giao diện trình duyệt

Service broker cung cấp API để platform gọi các thao tác provision, update, deprovision và binding. Một số hệ thống còn có giao diện quản trị chạy trong trình duyệt để nhân viên xem instance, kiểm tra operation hoặc thay đổi cấu hình. Hai loại client này có mô hình xác thực khác nhau, vì vậy chính sách chống Cross-Site Request Forgery (CSRF) cần được lựa chọn theo cách credentials được gửi và khả năng trình duyệt tự động đính kèm chúng.

CSRF xảy ra khi một trang web không đáng tin cậy khiến trình duyệt của người dùng gửi request tới một ứng dụng mà người dùng đã đăng nhập. Nếu trình duyệt tự động gửi cookie phiên hoặc thông tin xác thực khác, server có thể nhầm request do kẻ tấn công khởi tạo là hành động hợp lệ của người dùng. Kẻ tấn công thường không cần đọc response; chỉ cần khiến server thực hiện một hành động thay đổi trạng thái là đã có thể gây thiệt hại.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, API theo Open Service Broker API (OSB API) chủ yếu được platform gọi theo mô hình server-to-server, còn giao diện quản trị có thể dùng session cookie của trình duyệt. Bài học này giúp phân biệt hai threat model, giữ CSRF protection cho các luồng browser, và giới hạn việc bỏ qua CSRF ở đúng API route khi điều kiện xác thực thực sự phù hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích CSRF và điều kiện khiến một request bị khai thác.
- Phân biệt API server-to-server với giao diện trình duyệt dùng session cookie.
- Đánh giá rủi ro CSRF khi dùng cookie, HTTP Basic và Authorization header.
- Chọn chính sách CSRF riêng cho OSB endpoint và browser UI trong Spring Security.
- Sử dụng CSRF token cho form hoặc ứng dụng SPA.
- Hiểu vai trò và giới hạn của SameSite, CORS, Origin/Referer và Fetch Metadata.
- Kiểm thử request hợp lệ, thiếu token và token không hợp lệ.
- Tránh vô hiệu hóa CSRF trên toàn bộ ứng dụng chỉ vì có API.

## 1. CSRF là gì?

Giả sử người quản trị đã đăng nhập vào giao diện broker tại `https://broker.example.com`. Trình duyệt lưu session cookie `JSESSIONID`. Sau đó người quản trị mở một trang web độc hại trong tab khác. Trang đó có thể cố gửi request tới broker:

```html
<form action="https://broker.example.com/admin/instances/instance-123/deprovision"
      method="post">
  <input type="hidden" name="confirm" value="true">
</form>
<script>
  document.forms[0].submit();
</script>
```

Nếu trình duyệt tự động đính kèm session cookie và server không xác minh request có nguồn gốc từ giao diện hợp lệ, thao tác có thể được thực hiện dưới quyền người quản trị. Trang độc hại thường không đọc được response do Same-Origin Policy, nhưng việc đọc response không phải điều kiện bắt buộc để gây CSRF.

### 1.1. Điều kiện để CSRF có thể xảy ra

Một request thường có rủi ro CSRF khi đồng thời có các điều kiện:

1. Người dùng đã xác thực với ứng dụng.
2. Trình duyệt tự động gửi credentials kèm request, thường là cookie phiên hoặc HTTP authentication đã được trình duyệt lưu.
3. Kẻ tấn công có thể khiến trình duyệt gửi một request có tác dụng thay đổi trạng thái.
4. Server không có biện pháp đủ tin cậy để xác nhận request được tạo từ trang/ứng dụng hợp lệ.

Nếu request chỉ dùng một bearer token được JavaScript chủ động đặt vào header `Authorization` và token không nằm trong cookie hoặc cơ chế tự động gửi khác, website khác thường không thể tự lấy token đó để gửi request. Tuy nhiên, cần xem xét cách token được lưu, cách browser client hoạt động và nguy cơ XSS. Một ứng dụng stateless vẫn có thể bị CSRF nếu nó dùng cookie hoặc credentials tự động được trình duyệt gửi.

### 1.2. CSRF khác XSS và authentication

| Khái niệm | Vấn đề chính | Ví dụ |
|---|---|---|
| CSRF | Kẻ tấn công lợi dụng credentials mà trình duyệt tự gửi để thực hiện hành động | Trang ngoài gửi request xóa binding khi người quản trị đang đăng nhập. |
| XSS | Kẻ tấn công chạy script trong origin đáng tin cậy | Script độc hại đọc dữ liệu giao diện và thực hiện request cùng origin. |
| Authentication | Xác định client/người dùng là ai | Xác minh Basic credentials hoặc session. |
| Authorization | Xác định client/người dùng được phép làm gì | Tenant A không được deprovision instance của tenant B. |

CSRF token không thay thế authentication, authorization, input validation hoặc bảo vệ chống XSS. Nếu attacker đã thực thi JavaScript trong origin của giao diện quản trị qua XSS, script thường có thể đọc hoặc sử dụng CSRF token như ứng dụng hợp lệ.

## 2. Phân biệt OSB API và browser UI

Một service broker có thể phục vụ hai nhóm client:

| Client | Cách gọi | Credentials thường gặp | CSRF policy |
|---|---|---|---|
| Platform như Cloud Foundry hoặc một orchestrator | Server-to-server HTTP request tới OSB endpoint | `Authorization` header, HTTP Basic, mTLS hoặc cơ chế xác thực đã cấu hình | Có thể bỏ qua CSRF trên đúng API route nếu không dùng browser-ambient credentials và đáp ứng threat model. |
| Giao diện quản trị trong trình duyệt | Form submit hoặc JavaScript `fetch` | Session cookie hoặc cookie xác thực | Giữ CSRF protection cho mọi request thay đổi trạng thái. |
| Công cụ vận hành gọi API bằng script | Client chủ động đặt Authorization header | Token/API credential trong header | Thường không cần CSRF token nếu không dựa vào credentials tự động của browser; vẫn cần authn/authz. |
| Webhook từ hệ thống ngoài | Server-to-server callback | Chữ ký request, mTLS hoặc token trong header | Xác minh chữ ký/nguồn gửi; CSRF token trình duyệt thường không phù hợp. |

OSB API định nghĩa các thao tác có tác dụng thay đổi trạng thái, ví dụ:

- Provision: `PUT /v2/service_instances/{instance_id}`.
- Update: `PATCH /v2/service_instances/{instance_id}`.
- Deprovision: `DELETE /v2/service_instances/{instance_id}`.
- Bind: `PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}`.
- Unbind: `DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}`.

Đây là các thao tác mutation. Nếu chúng được gọi bằng browser session cookie, CSRF cần được xử lý. Trong triển khai OSB thông thường, platform gọi broker bằng thông tin xác thực được cấu hình trong platform và gửi request server-to-server. Broker có thể miễn CSRF cho đúng endpoint API nếu API không dựa vào session cookie hoặc credentials trình duyệt tự động gửi.

### 2.1. HTTP Basic cũng cần đánh giá theo cách browser gửi credentials

Không nên kết luận rằng chỉ cần dùng HTTP Basic là CSRF không thể xảy ra. Khi người dùng nhập Basic credentials vào browser, trình duyệt có thể lưu và tự động gửi chúng cho cùng origin trong các request sau. Nếu một browser được xác thực theo cách này có thể truy cập endpoint thay đổi trạng thái, request giả mạo vẫn cần được xem xét trong threat model.

Vì vậy, việc bỏ qua CSRF trên OSB API cần dựa trên ranh giới client thực tế: endpoint dành cho platform/service client, không dùng session cookie của browser, không cho người dùng quản trị duyệt bằng credentials được browser tự động gắn vào, và được bảo vệ bằng authentication, authorization, TLS cùng kiểm soát mạng phù hợp.

### 2.2. Không dùng một chính sách chung cho mọi route

Một cấu hình “API không cần CSRF” không có nghĩa toàn bộ ứng dụng không cần CSRF. Nếu cùng một ứng dụng có `/v2/**` cho platform và `/admin/**` cho browser, hãy tách rõ phạm vi. Một request tới `/admin/instances/...` không được miễn token chỉ vì ứng dụng cũng có endpoint API.

## 3. Chính sách cho API server-to-server

CSRF bảo vệ chống request giả mạo do browser tự gửi credentials. Với OSB endpoint chỉ nhận request từ platform/service client, xác thực bằng thông tin được client chủ động cung cấp qua header hoặc mTLS và không dùng cookie/session, broker có thể tắt CSRF cho đúng API route.

Các điều kiện nên được kiểm tra trước khi bỏ qua CSRF:

- API không xác thực bằng session cookie của browser.
- API không dựa trên cookie đăng nhập hoặc cookie “remember me”.
- Credentials được client server-to-server gửi chủ động qua `Authorization` header hoặc mTLS.
- API không được sử dụng như giao diện quản trị trong browser có credentials được cache.
- Các HTTP method thay đổi trạng thái vẫn được bảo vệ bằng authentication và authorization.
- API chỉ chấp nhận content type và request format theo hợp đồng; không có endpoint mutation ẩn qua GET.
- TLS được bật và credentials có thể được rotate/revoke.
- Network policy hoặc gateway giới hạn các client được phép kết nối khi phù hợp.

`SessionCreationPolicy.STATELESS` giúp ứng dụng không tạo session cho API chain, nhưng bản thân cấu hình stateless không chứng minh request miễn nhiễm CSRF. Nếu ứng dụng vẫn đọc cookie hoặc browser tự động gửi HTTP credentials, cần đánh giá lại.

## 4. Chính sách cho giao diện trình duyệt

Giao diện quản trị thường dùng session cookie để duy trì đăng nhập. Vì browser tự động gửi cookie tới cùng site, các request thay đổi trạng thái cần CSRF token.

Ví dụ các hành động cần bảo vệ:

- Tạo hoặc xóa service instance.
- Thay đổi plan hoặc parameters.
- Tạo binding hoặc thu hồi binding.
- Thay đổi provider configuration hoặc credential reference.
- Thay đổi quyền tenant, role hoặc user.

Các request chỉ đọc nên dùng phương thức an toàn như `GET` và không tạo side effect. Không dùng `GET` để deprovision, xóa binding hoặc cập nhật cấu hình. Spring Security mặc định bỏ qua CSRF cho các method an toàn như `GET`, `HEAD`, `TRACE`, `OPTIONS`; ứng dụng cần giữ đúng semantics này và không biến các request đọc thành thao tác thay đổi trạng thái.

### 4.1. Synchronizer token pattern

Với session-based UI, server tạo một CSRF token gắn với session. Trang/form hợp lệ nhận token và gửi lại trong request thay đổi trạng thái. Server so sánh token nhận được với token mong đợi.

Luồng cơ bản:

1. Người dùng tải trang quản trị và được cấp session.
2. Server cung cấp CSRF token trong form hoặc một cách an toàn cho frontend.
3. Khi người dùng gửi POST/PUT/PATCH/DELETE, form/JavaScript đính kèm token.
4. Spring Security kiểm tra token trước khi cho request đi tới controller.
5. Nếu token thiếu hoặc không hợp lệ, request bị từ chối, thường với `403 Forbidden`.

Token phải được giữ bí mật trong phạm vi phiên và không đưa vào URL, log hoặc analytics. Không dùng cùng một token tĩnh cho mọi người dùng.

### 4.2. HTML form với Spring Security

Với template engine như Thymeleaf, có thể đưa CSRF token vào form. Khi tích hợp Spring Security và Thymeleaf đúng cách, form POST có thể tự được bổ sung hidden input `_csrf`.

Ví dụ HTML minh họa:

```html
<form method="post" action="/admin/instances/instance-123/deprovision">
  <input type="hidden" name="_csrf" value="${_csrf.token}">
  <button type="submit">Thu hồi instance</button>
</form>
```

Tên biến và cách render token phụ thuộc template engine/cấu hình. Không copy nguyên chuỗi `${_csrf.token}` vào HTML tĩnh rồi kỳ vọng server tự thay thế; cần dùng integration của framework hoặc controller cung cấp token đúng cách.

### 4.3. SPA dùng cookie và request header

Một SPA có thể dùng `CookieCsrfTokenRepository` để server lưu token trong cookie `XSRF-TOKEN`, rồi JavaScript đọc token và gửi lại trong header `X-XSRF-TOKEN` cho các request mutation. Nếu JavaScript cần đọc cookie, cookie token thường phải được cấu hình `HttpOnly=false`; session cookie xác thực vẫn nên `HttpOnly=true`.

Ví dụ cấu hình repository:

```java
CookieCsrfTokenRepository repository =
        CookieCsrfTokenRepository.withHttpOnlyFalse();

http.csrf(csrf -> csrf
        .csrfTokenRepository(repository));
```

Đây chỉ là phần cấu hình repository. Với Spring Security 6, cách resolve token trong SPA có thể cần `CsrfTokenRequestHandler` phù hợp với cơ chế XOR/BREACH protection của phiên bản đang dùng. Hãy dùng hướng dẫn SPA hiện hành của Spring Security, không tự thay handler bằng một implementation đơn giản nếu chưa hiểu tác động bảo mật.

## 5. Cấu hình Spring Security theo từng nhóm endpoint

Một cách rõ ràng là tạo filter chain riêng cho OSB API và browser UI. Ví dụ dưới đây giả định:

- OSB API được mount tại `/v2/**`.
- API dùng HTTP Basic từ platform, không dùng session cookie hoặc cookie đăng nhập.
- Browser UI và các route còn lại dùng session/form login.
- Hai chain dùng cùng authentication/authorization infrastructure phù hợp với ứng dụng.

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain osbApiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/v2/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
        http
            // Chain này là fallback cho các route còn lại.
            // CSRF protection được giữ mặc định.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Trong cấu hình trên, chain đầu chỉ khớp `/v2/**` và bỏ qua CSRF trong phạm vi đó. Chain thứ hai là fallback và vẫn giữ CSRF mặc định cho giao diện trình duyệt. Nếu OSB endpoint được mount dưới context path hoặc prefix khác, matcher phải khớp đúng route thực tế. Không dùng matcher quá rộng như `/**` cho chain tắt CSRF.

Các import và cách cấu hình authentication provider đã được lược bớt để tập trung vào ranh giới CSRF. Cần cấu hình authorization theo platform identity, tenant và quyền thực tế. Không coi `authenticated()` là đủ nếu broker cần giới hạn service instance theo tenant.

### 5.1. Cách cấu hình đơn giản hơn trong một filter chain

Nếu ứng dụng chỉ có một chain, có thể bỏ qua CSRF cho đúng API matcher và giữ CSRF ở những route khác:

```java
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/v2/**"));
```

Chỉ dùng cách này khi các endpoint `/v2/**` thỏa điều kiện server-to-server đã nêu. Hãy kiểm tra thứ tự và phạm vi matcher trong toàn bộ cấu hình SecurityFilterChain. Một matcher sai có thể vô tình bỏ qua CSRF cho giao diện quản trị.

### 5.2. Vì sao không nên tắt CSRF toàn cục?

Không nên cấu hình:

```java
http.csrf(AbstractHttpConfigurer::disable);
```

cho toàn bộ ứng dụng chỉ vì broker có API. Cấu hình này cũng bỏ lớp bảo vệ của các form và endpoint browser dùng session cookie. Khi thêm giao diện quản trị về sau, developer có thể không nhận ra CSRF đã bị tắt từ trước.

## 6. SameSite cookie: lớp bảo vệ bổ sung

Thuộc tính `SameSite` hướng dẫn browser khi nào gửi cookie trong request cross-site:

| Giá trị | Hành vi khái quát | Lưu ý |
|---|---|---|
| `Strict` | Hạn chế gửi cookie trong hầu hết điều hướng/request cross-site. | Bảo vệ mạnh hơn nhưng có thể ảnh hưởng trải nghiệm khi người dùng đi vào từ liên kết ngoài. |
| `Lax` | Cho phép cookie trong một số điều hướng top-level an toàn, thường là GET; hạn chế nhiều request cross-site khác. | Là lựa chọn phổ biến, nhưng không thay thế CSRF token. |
| `None` | Cho phép cookie trong ngữ cảnh cross-site. | Browser yêu cầu `Secure`; cần lý do rõ ràng và CSRF token vẫn rất quan trọng. |

SameSite dựa trên khái niệm site, không hoàn toàn đồng nghĩa với origin. Các subdomain có thể cùng site nhưng khác origin. Nếu một subdomain không đáng tin cậy bị kiểm soát, chỉ dựa vào SameSite có thể chưa đủ.

Spring Boot có thể cấu hình session cookie qua `server.servlet.session.cookie.same-site` tùy phiên bản và môi trường. Ví dụ cấu hình `Lax`:

```yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Đảm bảo `secure: true` khi triển khai HTTPS và kiểm tra cấu hình proxy/load balancer để ứng dụng nhận biết đúng scheme. Không đặt `SameSite=None` chỉ để làm cho request cross-site hoạt động mà chưa đánh giá luồng xác thực và CSRF.

## 7. CORS không thay thế CSRF protection

Cross-Origin Resource Sharing (CORS) quyết định JavaScript từ origin khác có được phép đọc response hoặc thực hiện một số request cross-origin hay không. CORS không phải cơ chế xác thực người dùng và không bảo đảm mọi request cross-site đều bị chặn.

Một HTML form có thể gửi request đơn giản với content type như `application/x-www-form-urlencoded` mà không cần CORS preflight. Server có thể nhận và xử lý request dù trang tấn công không đọc được response. Vì vậy, chỉ cấu hình CORS không đủ để ngăn CSRF.

Với browser UI:

- Dùng CSRF token cho request mutation có cookie session.
- Chỉ cho phép origin cần thiết trong CORS.
- Không kết hợp `Access-Control-Allow-Credentials: true` với wildcard origin `*`.
- Chỉ cho phép method/header cần thiết.
- Không phản chiếu tùy tiện giá trị `Origin` từ request vào response.

Với OSB API server-to-server, thường không cần mở CORS cho mọi website. Nếu có một browser-based admin client gọi API cross-origin, phải thiết kế CORS, authentication và CSRF theo cách credentials được gửi; không áp dụng cấu hình CORS rộng chỉ để làm frontend chạy được.

## 8. Origin, Referer và Fetch Metadata

Server có thể kiểm tra `Origin` hoặc `Referer` của request mutation để xác định nguồn khởi tạo. Nếu header có mặt và không thuộc danh sách origin tin cậy, broker có thể từ chối request. Có một số request hợp lệ có thể thiếu `Referer` do chính sách privacy, vì vậy cần quyết định rõ cách xử lý trường hợp thiếu header.

Fetch Metadata headers như `Sec-Fetch-Site`, `Sec-Fetch-Mode` và `Sec-Fetch-Dest` cung cấp thêm ngữ cảnh về cách browser tạo request. Ví dụ, request có `Sec-Fetch-Site: cross-site` tới endpoint quản trị có thể bị từ chối. Đây là defense-in-depth; client không phải browser có thể không gửi các header này, nên không dùng chúng làm cơ chế xác thực duy nhất cho OSB API.

Một chính sách kiểm tra Origin nên:

1. Xác định danh sách origin chính xác của giao diện quản trị.
2. So sánh scheme, host và port theo origin, không chỉ so sánh chuỗi con.
3. Xử lý rõ request không có `Origin`/`Referer`.
4. Không tin header `Origin` như bằng chứng authentication; attacker có thể tự tạo header trong một HTTP client không phải browser.
5. Kết hợp với CSRF token và session authentication cho browser UI.

## 9. CSRF trong các endpoint của service broker

Các endpoint OSB mutation cần được xem xét riêng theo client và authentication:

| Endpoint | Side effect | Client thông thường | CSRF decision |
|---|---|---|---|
| `PUT /v2/service_instances/{id}` | Provision instance | Platform server | Có thể bỏ qua token nếu chỉ dùng server credentials chủ động gửi và không có browser cookie auth. |
| `PATCH /v2/service_instances/{id}` | Update instance | Platform server | Cùng điều kiện với provision; phải giữ authn/authz. |
| `DELETE /v2/service_instances/{id}` | Deprovision instance | Platform server | Cùng điều kiện; endpoint có tác động phá hủy cần authorization chặt. |
| `PUT .../service_bindings/{binding_id}` | Tạo binding/credentials | Platform server | Cùng điều kiện; không dùng cookie session cho API chain. |
| `DELETE .../service_bindings/{binding_id}` | Unbind | Platform server | Cùng điều kiện. |
| `/admin/**` mutation | Thay đổi qua giao diện | Browser session | Bắt buộc CSRF token và authorization. |

Nếu giao diện quản trị gọi trực tiếp OSB endpoint bằng session cookie, không được áp dụng ngoại lệ CSRF dành cho platform server. Hãy dùng một admin API route riêng có CSRF token hoặc một thiết kế xác thực không dựa vào credentials tự động của browser và đã được đánh giá đầy đủ.

### 9.1. Không cho phép mutation qua GET

Một số hệ thống cũ dùng `GET /admin/delete?id=...` hoặc `GET /action?deprovision=true`. Đây là thiết kế nguy hiểm vì GET có thể được kích hoạt bởi liên kết, ảnh, prefetch hoặc crawler. Hãy dùng POST/DELETE/PATCH phù hợp và bảo vệ bằng CSRF token nếu browser gửi session cookie.

### 9.2. Method override và content type

Nếu ứng dụng hỗ trợ `_method` để biến POST thành PUT/PATCH/DELETE, cần bảo đảm CSRF filter kiểm tra token trên request cuối cùng theo cấu hình filter chain. Không cho phép một request form không có token đi qua đường method override để thực hiện mutation.

API JSON có thể từ chối content type form không được hỗ trợ, nhưng kiểm tra content type chỉ là lớp phụ. Nếu browser vẫn có thể gửi credentials tự động và server chấp nhận một dạng request cross-site, cần CSRF protection phù hợp.

## 10. Xác thực và phân quyền vẫn là bắt buộc

Việc miễn CSRF cho một API route không làm route đó trở nên công khai. OSB API vẫn cần:

- Authentication cho platform hoặc client được cấp quyền.
- Authorization theo service, instance, tenant và thao tác.
- TLS để bảo vệ credentials trên đường truyền.
- Secret rotation và giới hạn quyền cho broker credentials.
- Rate limiting và audit cho thao tác nhạy cảm.
- Validation dữ liệu và idempotency cho request lặp.

Ví dụ, một request có Basic credentials hợp lệ vẫn không được phép deprovision instance thuộc tenant khác. CSRF bảo vệ nguồn gốc request browser; authorization bảo vệ phạm vi hành động. Hai lớp giải quyết hai câu hỏi khác nhau.

## 11. Kiểm thử CSRF với Spring Security

Kiểm thử nên xác nhận cả hai hướng: browser UI yêu cầu token, còn OSB API server-to-server hoạt động theo chính sách riêng đã định.

### 11.1. Browser mutation thiếu token phải bị từ chối

Ví dụ với MockMvc:

```java
@Test
void adminMutationWithoutCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/admin/instances/instance-123/deprovision")
            .with(user("operator").roles("ADMIN")))
        .andExpect(status().isForbidden());
}
```

### 11.2. Browser mutation có token hợp lệ được xử lý

```java
@Test
void adminMutationWithCsrfIsAccepted() throws Exception {
    mockMvc.perform(post("/admin/instances/instance-123/deprovision")
            .with(user("operator").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().is2xxSuccessful());
}
```

Test này giả định instance, quyền và service mock đã được cấu hình để thao tác thành công. Nếu authorization từ chối, status có thể khác; mục tiêu là xác minh request có CSRF token vượt qua CSRF filter.

### 11.3. Token không hợp lệ phải bị từ chối

```java
@Test
void adminMutationWithInvalidCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/admin/instances/instance-123/deprovision")
            .with(user("operator").roles("ADMIN"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}
```

### 11.4. OSB API không yêu cầu CSRF theo threat model server-to-server

Nếu API chain đã được cấu hình miễn CSRF và dùng Basic authentication, test cần xác minh request không có CSRF token vẫn có thể qua CSRF filter nhưng vẫn phải xác thực:

```java
@Test
void osbApiRequiresAuthenticationButNotBrowserCsrfToken() throws Exception {
    mockMvc.perform(put("/v2/service_instances/instance-123")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"service_id\":\"postgres\",\"plan_id\":\"standard\"}"))
        .andExpect(status().isUnauthorized());
}
```

Test trên xác minh request không có credentials bị từ chối vì authentication. Thêm test với Basic credentials hợp lệ để xác nhận request đi tiếp theo contract. Không chỉ kiểm tra rằng API trả 401; cần kiểm tra cả việc route API không bị chain browser áp dụng CSRF ngoài ý muốn.

### 11.5. Kiểm thử matcher và filter chain

Nên có test xác minh:

- `/v2/**` khớp API chain và không tạo session nếu cấu hình stateless.
- `/admin/**` khớp browser chain và yêu cầu CSRF token với mutation.
- Route không nằm trong API matcher không vô tình được miễn CSRF.
- POST/PUT/PATCH/DELETE bị bảo vệ; GET/HEAD không tạo side effect.
- Request form, JSON, method override và CORS preflight được xử lý đúng.
- Authentication và authorization vẫn được áp dụng sau khi CSRF filter cho request đi qua.

## 12. Xử lý lỗi và vận hành

Khi CSRF token thiếu hoặc không hợp lệ, Spring Security thường trả `403 Forbidden`. Không nên tự động retry request đó; client cần tải lại trang/token hoặc sửa cấu hình frontend. Retry không tạo token hợp lệ và có thể lặp cùng lỗi.

Log bảo mật nên ghi nhận route, method, user/client identity đã xác thực nếu có, correlation ID và loại lỗi CSRF. Không ghi token thực tế hoặc session cookie. Cần phân biệt CSRF rejection với authentication failure và authorization denial để đội vận hành chẩn đoán đúng.

Nếu browser UI chạy sau reverse proxy, cần cấu hình forwarded headers, HTTPS và cookie flags chính xác. Nếu scheme bị nhận sai, cookie `Secure`, redirect hoặc origin validation có thể hoạt động khác dự kiến.

Khi thay đổi filter chain, kiểm tra toàn bộ route thực tế sau context path, servlet mapping và API prefix. Việc chuyển endpoint từ `/v2/**` sang một prefix mới mà không cập nhật matcher có thể khiến API bị áp dụng CSRF ngoài ý muốn hoặc route browser bị bỏ qua bảo vệ.

## 13. Những lỗi cấu hình thường gặp

- **Tắt CSRF cho toàn bộ ứng dụng:** làm form quản trị dùng session cookie mất lớp bảo vệ.
- **Cho rằng stateless đồng nghĩa miễn CSRF:** stateless API vẫn có thể dùng cookie hoặc credentials browser tự gửi.
- **Cho rằng Basic Auth luôn an toàn trước CSRF:** browser có thể lưu và tự động gửi HTTP Basic credentials.
- **Dùng CORS thay CSRF token:** form cross-site vẫn có thể gửi request dù attacker không đọc được response.
- **Chỉ dựa vào SameSite:** đây là defense-in-depth và phụ thuộc ngữ cảnh site/browser.
- **Matcher quá rộng:** miễn CSRF cho cả route quản trị ngoài ý muốn.
- **Dùng GET để thay đổi trạng thái:** request có thể bị kích hoạt bởi liên kết hoặc prefetch.
- **Không kiểm thử request thiếu token:** cấu hình có thể vô tình cho mutation đi qua.
- **Để admin UI gọi API bằng session cookie nhưng API đã bị miễn CSRF:** ranh giới client không còn đúng như threat model ban đầu.
- **Không cấu hình fallback filter chain:** route không khớp chain API có thể thiếu chính sách bảo mật dự kiến.
- **Log CSRF token hoặc cookie:** tạo thêm đường rò rỉ thông tin xác thực.

## 14. Checklist lựa chọn chính sách CSRF

- [ ] Liệt kê OSB API routes, browser UI routes và webhook routes.
- [ ] Xác định credentials nào được gửi tự động bởi browser.
- [ ] Xác minh OSB API không dùng session cookie hoặc cookie đăng nhập.
- [ ] Đánh giá rủi ro HTTP Basic nếu endpoint có thể được truy cập bằng browser.
- [ ] Chỉ miễn CSRF cho matcher API server-to-server chính xác.
- [ ] Giữ CSRF token cho form/SPA dùng session cookie.
- [ ] Cấu hình SameSite, Secure và HttpOnly phù hợp.
- [ ] Không coi CORS, Origin hoặc Fetch Metadata là thay thế duy nhất cho token.
- [ ] Không có mutation qua GET.
- [ ] Authentication và authorization vẫn bảo vệ mọi API mutation.
- [ ] Kiểm tra method override và content type.
- [ ] Có test cho token hợp lệ, thiếu token, token sai và route matcher.
- [ ] Log rejection mà không ghi token/cookie.
- [ ] Kiểm tra filter chain sau context path và reverse proxy.

## Kết luận

Chính sách CSRF cần dựa trên cách client xác thực và cách trình duyệt gửi credentials. OSB API server-to-server có thể bỏ qua CSRF trên đúng route khi không dựa vào cookie/session hoặc credentials browser tự động gửi, nhưng vẫn phải xác thực và phân quyền. Giao diện quản trị dùng session cookie cần CSRF token cho mọi thao tác thay đổi trạng thái. Tách filter chain trong Spring Security, kết hợp token, SameSite và CORS đúng vai trò, rồi kiểm thử cả request hợp lệ lẫn giả mạo sẽ giúp broker bảo vệ giao diện trình duyệt mà vẫn giữ API platform hoạt động đúng.

## Tài liệu tham khảo

- [Spring Security Reference — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security Reference — CSRF and Single Page Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html#csrf-integration-javascript)
- [OWASP Cheat Sheet — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Set-Cookie: SameSite](https://developer.mozilla.org/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value)
