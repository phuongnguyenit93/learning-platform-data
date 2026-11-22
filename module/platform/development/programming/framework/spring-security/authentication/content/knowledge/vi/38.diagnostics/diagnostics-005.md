# Đăng nhập thành công nhưng yêu cầu sau vẫn chưa được xác thực — chẩn đoán Spring Security

Một lỗi rất thường gặp trong ứng dụng Spring Security là: **POST /login báo thành công, hoặc log cho thấy Authentication đã được xác thực, nhưng request GET tiếp theo lại nhận 401, 403 hoặc redirect về /login**. Vấn đề không nhất thiết nằm ở mật khẩu. Nhiều lần xác thực thành công **chỉ chứng minh một request hoặc một bước của flow đã có Authentication**, trong khi request kế tiếp cần thêm cơ chế duy trì danh tính: session cookie được gửi lại, `SecurityContext` được lưu trong `SecurityContextRepository`, hoặc một Bearer token hợp lệ được gửi cho request stateless.

Bài học này hướng dẫn chẩn đoán có thứ tự trong Spring Security Servlet: phân biệt triệu chứng, kiểm request/response và session, hiểu `SecurityContextHolderFilter`, sửa custom login chưa lưu context, xử lý cookie/CORS/proxy/cluster, tránh lẫn nhiều `SecurityFilterChain`, kiểm OAuth2/OIDC/SAML và viết integration test. Có ví dụ Java 17+ độc lập mô phỏng persistence và các mảnh Spring Boot được ghi rõ phạm vi.

**Nguyên tắc đầu tiên:** `SecurityContextHolder.clearContext()` ở cuối Servlet request thường là hành vi **đúng** để bảo vệ thread pool. Cách sửa không phải giữ ThreadLocal sống qua requests; cách sửa là chọn đúng cơ chế **persist hoặc re-authenticate** theo kiến trúc.

## 1. Xác định chính xác “đăng nhập thành công” và “chưa xác thực”

Những kết quả dưới đây có thể có nguyên nhân khác nhau:

| Quan sát | Chưa thể kết luận | Điều cần kiểm |
| --- | --- | --- |
| Login POST trả 200 | Chưa chắc Spring Security đã tạo Authentication | Response contract, AuthenticationManager và success handler |
| Login POST trả 302 | Chưa chắc session đã được lưu | Header Location, Set-Cookie, repository |
| Có `AuthenticationSuccessEvent` | Chưa chắc browser đã có session/cookie/token | Bước lưu context và bước hoàn tất flow |
| Request sau trả 302 tới `/login` | Có thể là unauthenticated với form login | Cookie, saved context, filter chain |
| Request sau trả 401 | Có thể thiếu credentials/token hoặc session | WWW-Authenticate, Authorization header, cookie |
| Request sau trả 403 | Có thể **đã authenticated** nhưng thiếu quyền hoặc CSRF | Principal, authorities, CsrfFilter, AccessDeniedHandler |
| API trả 200 nhưng UI tự đưa về login | Có thể do frontend state/route guard | Request nào thất bại và component nào redirect |
| Đăng nhập lần đầu được, refresh trang mất login | Persistence/session cookie/token storage hoặc frontend hydration | Network tab, cookie jar, session repository |
| Chỉ một node/tenant bị lỗi | Session sharing/filter matcher/proxy hoặc tenant scope | Node, host, context path, cookie, chain |

**Đừng bắt đầu bằng việc tắt CSRF, tạo session thủ công hoặc đổi mọi route thành `permitAll()`.** Các thao tác đó có thể che triệu chứng và mở lỗ hổng. Trước hết phải xác định **request nào thất bại**, mã HTTP thực tế và Authentication được khôi phục ở đâu.

## 2. Mental model: xác thực trong request A không tự lan sang request B

Một login stateful chuẩn:

~~~text
Browser                        Spring Security Servlet
   |                                      |
   |-- POST /login + credentials -------->|
   |                                      | AuthenticationManager xác minh
   |                                      | SecurityContext có Authentication
   |                                      | SAVE vào SecurityContextRepository
   |<-- 302 /dashboard + Set-Cookie ------|
   |                                      |
   |-- GET /dashboard + Cookie ---------->|
   |                                      | LOAD SecurityContext từ repository
   |                                      | Authorization kiểm quyền
   |<-- 200 trang protected --------------|
   |                                      |
~~~

Một login stateless chuẩn:

~~~text
Client -> POST /token + credentials
Server -> token được cấp sau xác minh

Client -> GET /api/me
          Authorization: Bearer <access-token>
Server -> xác minh token MỖI REQUEST và tạo Authentication

Client -> GET /api/me không có Bearer
Server -> 401 là hành vi mong đợi
~~~

**Không trộn hai hợp đồng.** Nếu chọn `SessionCreationPolicy.STATELESS` cho một API, việc request sau không tự nhớ user là đúng; client phải mang credential/token trên từng lần gọi. Nếu chọn session-based form login, client phải giữ cookie session và server phải lưu context.

## 3. Chu trình Servlet và SecurityContextHolderFilter

Trong Spring Security 6.x và phiên bản hiện đại, mặc định `SecurityContextHolderFilter` đọc context từ `SecurityContextRepository` vào `SecurityContextHolder` ở đầu request. Khi filter chain hoàn tất, holder được dọn khỏi thread:

~~~text
Request B
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request)
     -> SecurityContextHolder chứa Authentication nếu có
  -> authentication/authorization filters
  -> controller
  -> SecurityContextHolder được clear khi hoàn tất
~~~

**Điểm mấu chốt:** `SecurityContextHolderFilter` **không tự lưu context thay đổi** ở cuối request. Nếu bạn tự xây login trong controller hoặc filter, việc chỉ gọi:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

có thể khiến request A thấy user, nhưng **request B không có gì để nạp lại**. Trong Spring Security 6 với explicit-save semantics, bạn phải gọi `SecurityContextRepository.saveContext(...)` nếu muốn giữ session.

Tài liệu Spring Security phân biệt:

- `SecurityContextPersistenceFilter` của các cấu hình đời trước có thể tự lưu context khi request kết thúc/response commit.
- `SecurityContextHolderFilter` (mặc định Spring Security 6+) chỉ làm **read**, yêu cầu explicit save khi muốn persistence.
- Authentication filters được Spring Security cấu hình sẵn thường có logic cần thiết cho việc lưu context theo cơ chế của chúng; lỗi explicit-save nổi bật ở custom/manual authentication.
- Khi dùng Spring Security 7 hoặc cấu hình thay thế, hãy đọc chain thực và API phiên bản cụ thể, không dựa vào ký ức từ bản Spring Security cũ.

**Không đề xuất “tắt SecurityContextHolderFilter” để giữ user**; filter này dọn ThreadLocal để tránh danh tính Alice rò sang request của Bob khi container tái sử dụng thread.

## 4. Phân biệt “context có ở request A” với “context đã được save”

Ba trạng thái phải được kiểm riêng:

| Trạng thái | Lệnh kiểm | Ý nghĩa |
| --- | --- | --- |
| Authentication được provider xác minh | `authenticationManager.authenticate(...)` trả Authentication hợp lệ | Credential/policy đã qua xác minh |
| Context được set cho request hiện tại | `SecurityContextHolder.setContext(context)` | Logic cùng request có thể đọc principal |
| Context được lưu để request sau tải | `securityContextRepository.saveContext(context, req, resp)` | Session repository có bản ghi liên kết với client |

**Ghi vào holder ≠ ghi vào session.** Tương tự, gọi `saveContext` chưa bảo đảm request B được xác thực nếu cookie không được gửi lại, session hết hạn hoặc request B dùng một repository/filter chain khác.

Một sơ đồ nguyên nhân:

~~~text
Login A xác thực thật?
  |
  +-- NO --> sửa AuthenticationManager/provider/flow
  |
  +-- YES
       |
       v
Lưu context vào repository chưa?
  |
  +-- NO --> explicit save hoặc dùng filter auth chuẩn
  |
  +-- YES
       |
       v
Browser có nhận và gửi lại cookie / token?
  |
  +-- NO --> điều tra Set-Cookie, credentials, Domain/Path/SameSite/Secure
  |
  +-- YES
       |
       v
Request B đến đúng service/chain và repository?
  |
  +-- NO --> cấu hình chain/proxy/session store
  |
  +-- YES
       |
       v
Authentication đã được nạp nhưng bị từ chối?
  |
  +-- YES --> authorization/CSRF/role/tenant, không phải mất login
  |
  +-- NO --> kiểm session invalidation, expiry, repository load
~~~

Đây là thứ tự chẩn đoán, **không phải** một thuật toán thay thế kiểm tra bảo mật của Spring Security.

## 5. Kiểm HTTP thật trước khi sửa code

Mở Browser DevTools → Network và so sánh request A (login) với request B (protected resource). Trong môi trường test, ghi lại **metadata không nhạy cảm**:

- URL, method, status code, redirect chain và `Location`;
- Login response có `Set-Cookie` không? Cookie tên gì (thường `JSESSIONID` hoặc `SESSION` khi dùng Spring Session), Domain/Path/SameSite/Secure/HttpOnly;
- Browser lưu cookie vào đúng cookie jar hay đánh dấu bị chặn? Tại sao?
- Request B có header `Cookie` cho đúng host/path không?
- Nếu API dùng Bearer, request B có header `Authorization` không?
- Login và request B có cùng scheme (HTTPS), origin, base path và môi trường?
- Response B là 401, 403, 302 hay 200 rồi frontend tự chuyển trang?

**Chỉ kiểm sự hiện diện, tên cookie và các thuộc tính; không đưa giá trị session cookie, password, access token hoặc raw Authorization header vào log/ticket.**

Bảng kết luận nhanh:

| Login response | Request B | Nhận định ưu tiên |
| --- | --- | --- |
| 302, không có session cookie và server không có session | Có thể chưa save / session policy stateless |
| 302, có Set-Cookie nhưng B không gửi Cookie | Browser/proxy cookie policy |
| 302, cookie B có gửi, server không tìm thấy session | Session store/expiry/lifecycle/cluster |
| 302, session có, Authentication null | Repository chưa save, sai repository hoặc clear trước save |
| 302, Authentication đúng nhưng 403 | Authorization hoặc CSRF, không phải mất context |
| 302, Auth OK ở domain A nhưng request B đi domain B | Cookie Domain/Path/SameSite/CORS hoặc architecture |
| API token response 200, request B không có Bearer | Client thiếu token trong stateless flow |
| Login OIDC/SAML redirect xong, state/session lỗi | Callback cookie, state correlation, proxy host hoặc flow chưa hoàn tất |

## 6. Custom login chưa gọi saveContext: lỗi rất phổ biến

Ví dụ **sai** trong custom login handler:

~~~java
// Đây chỉ là mảnh code; authentication được manager xác minh trước.
Authentication authentication =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Thiếu repository.saveContext(...)
// Request hiện tại đọc được user; request mới có thể anonymous.
response.sendRedirect("/account");
~~~

Sửa theo mô hình Spring Security 6+:

~~~java
// Mảnh trong Servlet login controller/filter, không phải main độc lập.
Authentication loginToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword);

// Đừng tự tạo token authenticated=true từ dữ liệu client.
Authentication verified =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Dùng đúng repository mà SecurityFilterChain tương ứng dùng.
securityContextRepository.saveContext(context, request, response);

// Chỉ redirect hoặc commit response SAU khi lưu thành công.
response.sendRedirect(request.getContextPath() + "/account");
~~~

**Đặc biệt quan trọng:** đoạn này giả định các biến `submittedUsername`, `submittedPassword`, `authenticationManager`, `securityContextRepository`, `request` và `response` được cung cấp qua một Servlet component đã được cấu hình đúng. Nó là **mảnh mã framework**, không thể biên dịch/chạy chỉ với `javac`.

Trong login custom, việc tự gọi `AuthenticationManager.authenticate()` rồi lưu context **không tự thay thế** toàn bộ session lifecycle do filter đăng nhập tiêu chuẩn quản lý. Kiểm thêm:

1. `SessionAuthenticationStrategy` có được gọi đúng không để xử lý session fixation/concurrency policy (nếu flow custom tự sở hữu)?
2. Session ID có đổi hợp lệ sau login không?
3. Context được lưu vào repository của chain dùng ở request B?
4. Save diễn ra trước redirect/response commit?
5. Account status/authorities có đúng, không tự biến username từ input thành Authentication “đã xác thực”?
6. Không ghi credential trong HTTP response hoặc log?

**Ưu tiên dùng authentication filter/flow chuẩn** của Spring Security khi có thể. Một custom login endpoint có thể bỏ sót session fixation protection, concurrent session control, saved requests hoặc failure handling nếu chỉ copy vài dòng tạo context.

## 7. SecurityContextRepository phải tương thích với mục đích

Spring Security Servlet có các repository thường gặp:

| Repository | Dùng để làm gì | Hệ quả với request kế |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu context trong `HttpSession` | Request cùng session hợp lệ có thể load Authentication |
| `RequestAttributeSecurityContextRepository` | Dùng context trong phạm vi một request/dispatch | Không làm session login qua requests |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repositories | Spring Security mặc định hiện đại thường gồm request attributes + HTTP session |
| `NullSecurityContextRepository` | Không lưu auth cho request sau | Thích hợp với một số cơ chế stateless |

Một lỗi hay gặp:

~~~text
Login custom lưu vào RequestAttributeSecurityContextRepository
    -> redirect /dashboard tạo HTTP request mới
    -> context từ request trước không còn
    -> /dashboard anonymous
~~~

Nếu app cần session, phải có repository lưu vào session. Nếu app chủ đích stateless, đừng chuyển sang session chỉ để làm cho test “giữ login” xanh.

Khi custom controller tự inject `new HttpSessionSecurityContextRepository()` nhưng web chain lại dùng `NullSecurityContextRepository` hoặc custom repository khác, bạn có thể “save thành công” nhưng chain của request B **không đọc đúng nơi**. Hãy cấu hình **cùng instance hoặc cùng storage contract** cho authentication component và SecurityFilterChain.

Ví dụ cấu hình một repository được dùng thống nhất (Spring Security Servlet):

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain webChain(
        HttpSecurity http,
        SecurityContextRepository securityContextRepository)
        throws Exception {

    return http
            .securityContext(context -> context
                    .securityContextRepository(securityContextRepository))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Đoạn trên phải nằm trong `@Configuration` có imports và các beans/service cần thiết. Nó **không phải ứng dụng chạy độc lập**. Trong nhiều ứng dụng, repository mặc định của Spring Security đã đúng; **không thay mặc định chỉ để “thử”** nếu chưa có bằng chứng về repository mismatch.

## 8. SessionCreationPolicy không có nghĩa giống nhau

Spring Security có các chính sách session:

| Policy | Ý nghĩa thực hành | Triệu chứng |
| --- | --- | --- |
| `ALWAYS` | Spring Security chủ động tạo session | Thường giữ context stateful nếu repository hỗ trợ |
| `IF_REQUIRED` | Tạo session khi cần | Phù hợp nhiều form-login apps |
| `NEVER` | Spring Security không tự tạo session để lưu auth, nhưng có thể dùng session đã tồn tại | Không tương đương STATELESS |
| `STATELESS` | Không tạo/không dùng HTTP session để lấy SecurityContext cho auth | Request sau phải mang auth material |

Ví dụ một API dùng Bearer token:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

Đây là **mảnh cấu hình Spring Security Servlet**, yêu cầu resource-server dependency, JwtDecoder cấu hình đúng, @Configuration/imports. Nó không biến form login ở một chain khác thành stateless nếu matcher được tách đúng. Với JWT resource server, client phải gửi `Authorization: Bearer ...` trên mỗi API request.

Cần nhớ:

- `STATELESS` thường đi kèm `NullSecurityContextRepository` cho việc persist auth; không mong request B được xác thực nhờ cookie session.
- `NEVER` vẫn có thể dùng session tồn tại; RequestCache trong một số cấu hình có thể tạo session, nên đừng suy chính xác hành vi chỉ từ tên enum.
- Nếu cấu hình SessionCreationPolicy ở chain quá rộng, cả form login có thể không lưu authentication như bạn nghĩ.
- Trong một app hỗn hợp web + API, thiết kế ranh giới giữa session-based browser routes và token-based API routes rõ ràng.

**Đừng đổi STATELESS → ALWAYS chỉ để hết 401** nếu hợp đồng API ban đầu dựa trên Bearer token; điều đó đổi security architecture và có thể tăng CSRF/session fixation risk.

## 9. Cookie bị thiếu: Domain, Path, Secure, SameSite và trình duyệt

Một session stateful chỉ hoạt động khi browser **giữ và gửi lại đúng session identifier**. Các thuộc tính cookie cần đối chiếu trong DevTools:

| Thuộc tính | Lỗi có thể xảy ra |
| --- | --- |
| `Domain` | Cookie chỉ thuộc host A, request B tới host B |
| `Path` | Cookie cấp dưới `/auth`, nhưng request B nằm `/app` |
| `Secure` | Cookie không được gửi trên HTTP; cần HTTPS |
| `HttpOnly` | JavaScript không đọc cookie; **đây là thuộc tính an toàn, không phải lỗi** |
| `SameSite=Lax/Strict/None` | Ảnh hưởng gửi cookie trên các ngữ cảnh cross-site |
| `Expires/Max-Age` | Cookie đã hết hạn hoặc bị browser xóa |
| Session cookie không có Expires | Có thể hết cùng phiên browser, tùy browser policy |
| Tên cookie `JSESSIONID` vs `SESSION` | Ứng dụng/server store khác nhau |

**Đừng tắt HttpOnly để JavaScript “nhìn thấy cookie”.** Cookie session HTTP-only vẫn được browser tự gửi kèm request hợp lệ; JS không cần đọc nó.

Đối với web app cùng origin, `SameSite=Lax` hoặc cấu hình chặt hơn thường đủ. Với **cross-site cookie thực sự**, có thể cần `SameSite=None; Secure`, HTTPS và CORS credentials; nhưng trình duyệt vẫn có thể chặn **third-party cookies**. Không áp `SameSite=None` cho mọi cookie mà không hiểu threat model và CSRF.

**Cross-origin khác cross-site:** `https://app.example.org` và `https://api.example.org` là **khác origin**, nhưng có thể là **cùng site** theo quy tắc schemeful site/eTLD+1. CORS vẫn áp dụng với cross-origin fetch, còn SameSite có cách phân loại khác. Hãy kiểm thực tế thay vì mặc định “khác subdomain = SameSite=None”.

## 10. SPA/fetch: credentials và CORS

Với frontend ở `https://app.example.org` gọi backend `https://api.example.org`, mặc định `fetch()` dùng `credentials: "same-origin"`. Do hai origin khác nhau, browser sẽ không tự gửi cookie cross-origin nếu client không yêu cầu.

Ví dụ:

~~~javascript
const response = await fetch("https://api.example.org/account/me", {
    method: "GET",
    credentials: "include"
});
if (!response.ok) {
    throw new Error("Request failed");
}
const me = await response.json();
~~~

Login request từ SPA cũng cần `credentials: "include"` khi cơ chế dùng cookie cross-origin, nếu không browser có thể không xử lý Set-Cookie như mong đợi. Kể cả khi request đăng nhập trả 200, bạn vẫn phải xác nhận cookie thực sự được lưu và gửi trong request kế.

Server CORS cho credentialed requests phải:

- Trả `Access-Control-Allow-Credentials: true` khi phù hợp.
- Chỉ allow **origin cụ thể** được phê duyệt, không dùng `*` với credentials.
- Chỉ allow methods/headers cần thiết.
- Xử lý preflight `OPTIONS` trước security authentication logic, vì preflight thường **không có cookie**.
- Giữ CSRF policy đúng với session cookie; CORS không thay CSRF.

Ví dụ cấu hình Spring Security 6.x Servlet:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.org"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http.cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
~~~

Đây là **mảnh cấu hình**, không phải một application đầy đủ; cần imports `java.util.List`, Spring Web CORS types, Spring Security và các route/login settings. Khi ứng dụng có nhiều SecurityFilterChain hoặc nhiều CorsConfigurationSource, hãy xác định đúng bean/source được chain sử dụng. Không cấu hình origin bừa dựa vào header `Origin` do client tự gửi.

**CORS error có thể che lỗi auth.** Browser báo “blocked by CORS” nhưng network thực tế là OPTIONS bị 401, hoặc response 302 tới /login bị chặn. Kiểm status và headers của preflight lẫn request chính, không vội đổi password encoder.

## 11. CSRF 403 khác với chưa xác thực

Trong session-based web app, `POST /login` và các POST thay đổi trạng thái có thể chịu CSRF protection. Một số tình huống:

- GET `/me` không có cookie → 401/302 do chưa xác thực.
- POST `/orders` có cookie nhưng không có CSRF token hợp lệ → 403 **dù session vẫn authenticated**.
- Fetch cross-origin thiếu CSRF header → 403, dễ bị frontend hiểu nhầm thành “hết login”.
- Endpoint chỉ yêu cầu role ADMIN → 403 vì authorization, không phải do cookie.

**Không vô hiệu hóa CSRF toàn ứng dụng để giải quyết 403**. Kiểm form/SPA có nhận và gửi token đúng khi dùng cookie-based authentication, session ID có bị rotate làm token cũ mất hợp lệ không, và request có qua đúng chain.

Ở stateless Bearer token API không dùng cookie session, CSRF policy có thể khác; cần quyết định dựa trên client model chứ không đơn giản “REST API là an toàn nên tắt”.

## 12. Filter chain khác nhau: login qua chain A, resource qua chain B

Ứng dụng có nhiều `SecurityFilterChain` có thể gắn policy khác nhau:

~~~text
Chain 1: securityMatcher("/api/**")
         STATELESS + JWT resource server

Chain 2: securityMatcher("/**") hoặc fallback
         Session-based formLogin()
~~~

Nếu login response đến từ chain session-based nhưng request B là `/api/me` thuộc chain stateless, thì cookie session **có thể không có tác dụng** cho API route. Bài toán không phải user bị mất ngẫu nhiên, mà do hai chains có mô hình identity khác nhau.

Trong Spring Security, thứ tự `@Order` và `securityMatcher` quyết định chain nào chọn request; thường chain cụ thể phải đứng trước chain tổng quát. Một chain matcher quá rộng có thể “nuốt” request của chain còn lại.

Các tình huống cần kiểm:

| Sai lệch | Hệ quả |
| --- | --- |
| `/api/**` dùng STATELESS nhưng UI gửi cookie | API request vẫn unauthenticated |
| Login route `/login` không nằm trong chain form login | Filter formLogin không xử lý POST như mong đợi |
| `securityMatcher` vô tình loại `/oauth2/**` callback | OIDC callback không đi qua filter đúng |
| `web.ignoring()` dùng cho protected endpoint | Security filters không chạy |
| Custom filter được add hai lần hoặc thứ tự sai | Context bị set/clear không đúng |
| Custom AuthenticationSuccessHandler trả redirect trước save | Request sau mất auth |
| Hai repositories khác nhau ở chain A/B | Save thành công nhưng B load sai nơi |

Bật logging có kiểm soát để thấy FilterChainProxy chọn chain nào và filter nào chạy, nhưng **không bật dump credential/header/body**. Kiểm cấu hình route/matcher ngay từ runtime thay vì suy theo tên method cấu hình.

## 13. Proxy, HTTPS termination và load balancer

Khi triển khai sau ingress, Nginx, API gateway hoặc load balancer:

~~~text
Browser -> https://app.example.org
            |
            v
         Reverse proxy (TLS termination)
            |
            v
         http://service:8080
~~~

Backend có thể thấy scheme/host/path khác public URL. Điều này ảnh hưởng `Secure` cookie, redirect URL, callback URL, context path và session stickiness.

Kiểm:

1. Public Host, forwarded scheme và path có đúng cấu hình không?
2. Proxy có strip/overwrite `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` đến từ Internet không?
3. Backend chỉ tin forwarded headers từ trusted proxy?
4. Response `Set-Cookie` có Domain/Path/Secure/SameSite đúng public deployment?
5. Session có nằm trên một node hay shared store?
6. Requests A/B có đi tới cùng app deployment/namespace, đúng session serializer và signing/encryption keys?
7. Proxy có loại bỏ cookie headers hoặc thay path khi rewrite URL không?

**Không tùy tiện tin X-Forwarded-* để “sửa login”.** Nếu browser điều khiển header, attacker có thể gây host spoofing, redirect sai domain hoặc sai audit.

### Cluster nhiều node

Giả sử:

~~~text
Login A -> node-1 -> HttpSession local chứa SecurityContext
GET B   -> node-2 -> không có cùng HttpSession
            -> unauthenticated
~~~

Giải pháp production là **shared session store** (ví dụ Spring Session với Redis/database theo policy) hoặc hạ tầng sticky-session được hiểu rõ, có kế hoạch failover. Sticky session chỉ che một số vấn đề và không thay thế durable/session lifecycle khi cần HA.

Kiểm tất cả nodes dùng cùng cookie/session naming, serialization/security context model, version và tenancy. Nếu dùng Spring Session và cookie `SESSION`, đừng nhầm sự khác tên với `JSESSIONID` là lỗi.

## 14. Session fixation, expiry, logout và concurrent session control

Spring Security thường đổi session identifier khi xác thực thành công để bảo vệ **session fixation**. Vì vậy:

~~~text
Trước login: JSESSIONID=old-session
Sau login:   JSESSIONID=new-session
~~~

Đây có thể là hành vi **đúng**. Nếu client test/cURL/SPA vô tình tiếp tục dùng cookie cũ, request sau sẽ không có context của phiên mới. Hãy quan sát cookie **cuối cùng** sau các redirects và xem browser có chấp nhận Set-Cookie mới không.

Những nguyên nhân khác:

- Session timeout quá ngắn hoặc clock/TTL sai.
- User logout ở tab khác, session bị invalidate.
- Đăng nhập thứ hai bị policy maximumSessions/expired session control làm phiên đầu hết hiệu lực.
- Session store Redis bị restart/evict/mất dữ liệu.
- Custom logout handler hoặc success handler xóa session/context sau login.
- Session attribute bị thay bằng context trống do filter/custom code.
- Ứng dụng chuyển domain/tenant, tạo session mới không liên quan.

Nếu dùng Spring Security concurrent-session support, kiểm `SessionRegistry`/session event listener hoặc cấu hình Spring Session theo thực tế. Một request bị chặn do expired session policy không đồng nghĩa password vừa xác minh sai.

**Dọn SecurityContextHolder ở cuối request là đúng, còn logout phải xóa hoặc vô hiệu hóa state ở repository/session.** Không gọi `clearContext()` một mình rồi cho rằng browser đã logout, và không trì hoãn việc cleanup để giữ user “còn login”.

## 15. OAuth2/OIDC và SAML: redirect callback không đồng nghĩa session đã persist

Với `oauth2Login()` hoặc `saml2Login()`, flow bao gồm nhiều redirects, correlation state và endpoint callback. Các điểm cần kiểm:

- Browser có giữ session/correlation cookie qua IdP redirect/callback không?
- HTTP callback tới đúng public origin/path và đúng Spring Security filter chain không?
- Origin/SameSite/cookie có khiến callback không có session và state/nonce bị mất không?
- Provider login thành công nhưng RP application có hoàn tất xác thực, gọi success handler và save context không?
- Custom success handler có đổi redirect quá sớm, logout/invalidate session hoặc tạo context mới sai không?
- Request B nằm trong web session chain hay một stateless API chain yêu cầu Bearer?

Một flow có thể trông “IdP login success” trong log của nhà cung cấp nhưng callback của RP thất bại vì state/issuer/audience/signature/metadata. Lúc đó **RP chưa có Authentication hợp lệ**; không nên cố save session từ thông tin IdP chưa xác minh.

Ở OAuth2/OIDC, `redirect_uri` là callback giao thức, còn post-login target là route ứng dụng. Không tùy ý dùng `next` làm callback hay sao chép token vào URL để tránh mất context.

Với SAML, xử lý SAMLResponse/RelayState phải qua verifier trước khi tạo Authentication. Đừng giải quyết callback không thành công bằng cách tắt kiểm chữ ký/origin/issuer/audience.

## 16. Khác biệt giữa SecurityContext và frontend auth state

Một SPA có thể hiển thị “Đăng nhập thành công” chỉ vì:

~~~javascript
if (loginResponse.status === 200) {
    uiState.loggedIn = true;
}
~~~

Nhưng backend chưa chắc đã persist auth hay token. Một frontend route guard cũng có thể tự xóa auth state khi refresh vì state nằm trong memory, dù cookie/session backend vẫn còn.

Hãy test độc lập:

1. Browser thực hiện login thật.
2. Gửi request `GET /me` từ **chính browser cùng cookie/token**.
3. Nếu backend trả user đúng mà UI vẫn login screen → frontend state/hydration/router issue.
4. Nếu backend trả 401/302 → investigate cookie/repository/chain/auth material.
5. Nếu backend trả 403 → kiểm authorization/CSRF.

Không đưa mật khẩu hoặc access token vào localStorage chỉ để “cho refresh trang khỏi mất login” mà không đánh giá XSS/CSRF threat model. Chọn cookie-based session hoặc token-based client storage theo kiến trúc và policy riêng.

## 17. ThreadLocal cleanup và async propagation

`SecurityContextHolder` trong Servlet thường lưu context theo thread. Request B không nhất thiết chạy trên cùng thread A, và nếu cùng thread thì framework vẫn **phải clear** để không rò principal.

Với `@Async`, executor hoặc `CompletableFuture`:

~~~text
Request thread: SecurityContext = Alice
       |
       +--> executor worker thread
               |
               +--> SecurityContext thường KHÔNG tự có Alice
~~~

Đừng nhầm “task async không thấy principal” với “request B bị mất session”. Đây là hai ranh giới riêng. Spring Security hỗ trợ `DelegatingSecurityContextRunnable/Callable/Executor` để propagate context với cleanup. Không dùng `MODE_INHERITABLETHREADLOCAL` làm cách sửa chung cho thread pools vì worker threads tái sử dụng có thể mang danh tính cũ.

Một callback async đọc SecurityContext trên thread khác và thấy null không chứng minh session không lưu; để test persistence cần gửi **HTTP request mới** với cookie/token đúng.

## 18. Java 17+ độc lập: mô hình vì sao phải lưu session

Tạo file **LoginPersistenceBoundaryDemo.java**. Nó mô phỏng holder theo thread và session store bằng Java Collections, không dùng Spring Security. Đây là **mô hình học thuật**, không phải trình xác thực credential, không thay cho `SecurityContextRepository` hoặc HTTP session store thật.

~~~java
import java.util.HashMap;
import java.util.Map;

public class LoginPersistenceBoundaryDemo {

    private final Map<String, String> sessionStore = new HashMap<>();
    private final ThreadLocal<String> currentPrincipal = new ThreadLocal<>();

    void login(String sessionId, String principal, boolean save) {
        try {
            // Giả định principal đã được xác minh ở nơi khác.
            currentPrincipal.set(principal);
            System.out.println("Login handler = " + currentPrincipal.get());

            if (save) {
                sessionStore.put(sessionId, principal);
            }
        } finally {
            currentPrincipal.remove();
        }
    }

    String nextRequest(String sessionId) {
        try {
            String saved = sessionStore.get(sessionId);
            if (saved != null) {
                currentPrincipal.set(saved);
            }

            String principal = currentPrincipal.get();
            return principal == null ? "anonymous" : principal;
        } finally {
            currentPrincipal.remove();
        }
    }

    void logout(String sessionId) {
        sessionStore.remove(sessionId);
    }

    public static void main(String[] args) {
        LoginPersistenceBoundaryDemo demo =
                new LoginPersistenceBoundaryDemo();

        demo.login("not-saved", "alice", false);
        System.out.println("Without save = "
                + demo.nextRequest("not-saved"));

        demo.login("saved-session", "alice", true);
        System.out.println("With same session = "
                + demo.nextRequest("saved-session"));
        System.out.println("With other session = "
                + demo.nextRequest("different-session"));

        demo.logout("saved-session");
        System.out.println("After logout = "
                + demo.nextRequest("saved-session"));

        System.out.println("Thread context clear = "
                + (demo.currentPrincipal.get() == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LoginPersistenceBoundaryDemo.java
java LoginPersistenceBoundaryDemo
~~~

Stdout chính xác:

~~~text
Login handler = alice
Without save = anonymous
Login handler = alice
With same session = alice
With other session = anonymous
After logout = anonymous
Thread context clear = true
~~~

Giải thích:

- `login("not-saved", ...)` set principal đúng trong request A, nhưng không lưu ⇒ request mới anonymous.
- `login("saved-session", ...)` lưu vào session store ⇒ request mang cùng session ID có thể đọc Alice.
- Session khác không được lấy Alice.
- Logout xóa session record ⇒ request sau anonymous.
- `finally` dọn ThreadLocal của thread hiện tại; đó là hành vi đúng, không làm mất state đã được lưu trong repository.

**Không dùng code này cho production.** Nó không xác thực mật khẩu, không tạo/kiểm cookie an toàn, không mã hóa session, không có TTL, không đồng bộ đa node và không dùng Spring Security. Nó chỉ giúp phân biệt **holder lifecycle** với **persistence lifecycle** trong một ví dụ Java chạy được.

## 19. MockMvc: test hai request thật, không dùng mockUser để che lỗi

Một bẫy trong test:

~~~java
mvc.perform(get("/private").with(user("alice")))
        .andExpect(status().isOk());
~~~

RequestPostProcessor `with(user("alice"))` **tự đặt Authentication cho request**. Nó không chứng minh form login đã lưu context. `@WithMockUser` ở cấp test cũng có thể che lỗi tương tự nếu mọi request tự có mock user.

Muốn test persistence đúng, cần:

1. Gửi POST login thật qua Spring Security filter chain.
2. Lấy `MockHttpSession` từ **login result**.
3. Gửi GET protected với **chính session đó**, không kèm `with(user(...))`.
4. Gửi GET khác không session, phải anonymous/không được phép.
5. Có thể thêm logout rồi kiểm session cũ không còn quyền.

Ví dụ test class hướng dẫn cho app Spring Boot có form login, user test “alice”/“correct-password” và endpoint `/private` protected:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistsSecurityContextTest {

    @Autowired MockMvc mvc;

    @Test
    void secondRequestUsesSavedLoginSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin("/login")
                        .user("alice")
                        .password("correct-password"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session(session))
                .andExpect(authenticated().withUsername("alice"));

        mvc.perform(get("/private"))
                .andExpect(unauthenticated());
    }
}
~~~

Test này **có thể biên dịch/chạy trong một project Spring Boot Servlet đã cấu hình đúng** với Spring Security Test, JUnit 5, user fixture và SecurityFilterChain. Cần test setup tương ứng với version Spring Boot; import trong ví dụ dùng cấu trúc phổ biến của Spring Boot 3.x. Nó không chạy độc lập bằng `javac`.

**Đặc biệt:** expected session chỉ đúng nếu đây là **stateful form login** và app tạo session. Đừng dùng test này làm tiêu chí cho API Bearer token stateless. Nếu `@WithMockUser` đặt trên cả test class, hãy bỏ annotation đó khi kiểm login persistence thật.

Nếu dùng custom JSON login, thay request đầu bằng `post("/auth/login")` có CSRF token/content type đúng và cùng repository; không tự tạo authenticated fixture để làm test “login succeeded”.

## 20. Test thực qua browser hoặc HTTP client

MockMvc không kiểm hết cookie policy của trình duyệt, proxy HTTPS, domain và SameSite. Vì vậy sau khi test ứng dụng xanh, cần kiểm E2E:

~~~text
1. Browser mở trang login dưới đúng public HTTPS hostname.
2. Login bằng account test hợp lệ.
3. Quan sát response Set-Cookie: session cookie được nhận không?
4. Quan sát cookie storage: có block reason?
5. Refresh một protected page.
6. Kiểm request GET có Cookie hoặc Authorization phù hợp.
7. Kiểm backend principal trên /me.
8. Logout; request mới với session cũ không còn quyền.
9. Lặp lại qua mỗi gateway/node quan trọng.
~~~

Với `curl` để chẩn đoán cookie jar, nguyên tắc là `-c cookie-jar` ở request login và `-b cookie-jar` ở request sau. Nhưng form login Spring Security thường có **CSRF token cần lấy từ form/cookie trước khi POST**; không đưa một lệnh cURL bỏ token rồi kết luận login thất bại là do persistence. Dùng HTTPS và account test, bảo vệ cookie jar như secret và xóa nó sau test.

Trong browser, theo dõi redirect chain đầy đủ; final response 200 của trang login có thể che một 302 từ protected page về `/login`.

## 21. Diagnostic logging không làm lộ credential

Khi phải chẩn đoán production, chỉ ghi những trường **được phép**:

| Log field | Ví dụ an toàn | Không log |
| --- | --- | --- |
| requestId/traceId | Opaque generated identifier | Raw session ID |
| request path template | `GET /private` | Full URL chứa token/query secrets |
| auth state | authenticated/anonymous | Password, JWT text |
| authentication type | Form/OIDC/Bearer | Raw Authentication object |
| repo state | loaded/missing/saved | Toàn bộ serialized SecurityContext |
| selected chain | web/api chain label | Request headers chứa secrets |
| session observed | exists/absent, cookie present/absent | JSESSIONID/SESSION value |
| denial category | CSRF / authorization / authentication | Exception message chứa PII |
| node identity | service instance label | Credentials/config secrets |

Có thể bật logger Spring Security trong môi trường test hoặc trong một cửa sổ sự cố kiểm soát, nhưng không dump `Authorization`, `Cookie`, password hoặc session attributes.

**Một event AUTH_SUCCESS không chứng minh session persistence.** Hãy log tách biệt auth verification result, repository save, response commit, request B repository load và authorization result.

Mã tương quan có ích để ghép A/B, nhưng **hai HTTP requests có hai request IDs khác nhau**. Nếu muốn liên kết flow, dùng một opaque flow ID bảo vệ riêng, không public raw session ID hoặc username.

## 22. Cây chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra ưu tiên | Sửa có cơ sở |
| --- | --- | --- |
| Login handler in principal đúng, request sau null | saveContext và repository | Explicit save sau authenticate |
| Session cookie không có trong response | Session policy, response commit, login flow | Dùng session-aware flow hoặc kiểm cookie config |
| Cookie được set nhưng browser từ chối | Secure, Domain, Path, SameSite, third-party policy | Sửa deployment/cookie thuộc tính đúng |
| SPA login 200 nhưng API tiếp theo 401 | `credentials:"include"`, CORS, API chain | Gửi credentials đúng hoặc Bearer token |
| Preflight OPTIONS 401 | CORS xử lý sau security | Tích hợp CORS trước auth |
| Protected POST 403, GET cùng session OK | CSRF | Sửa CSRF token flow, không tắt bừa |
| GET protected 403, Authentication đúng | Role/authority/tenant | Sửa authorization policy |
| Local OK, production load balancer fail | Session store/stickiness | Shared sessions, nhất quán node |
| Sau login session ID đổi | Session fixation rotation | Client dùng cookie mới, không tái dùng session cũ |
| Refresh trang API mất auth | Frontend mất token/session hoặc API stateless | Kiểm storage và Bearer per request |
| OIDC callback thành công tại IdP, RP không login | State/session callback/filter | Kiểm RP callback và cookie trước khi save |
| Nhiều SecurityFilterChain | Matcher/order/repository mismatch | Kiểm chain được chọn ở A/B |
| Chỉ một account bị lỗi | Status, authorities, concurrent session policy | Không suy chung là cookie bug |
| Request B chưa authentic nhưng A vừa thành công | Có thể B chạy trước save/redirect hoàn tất | Kiểm race và response commit order |
| Session bị mất sau logout ở tab khác | Session invalidation đúng | Cập nhật frontend UX, không “hồi sinh” session |

## 23. Ma trận kiểm thử regression

| Test | Kỳ vọng |
| --- | --- |
| Custom login valid credentials | Provider trả verified Authentication |
| Custom login invalid credentials | Không tạo/lưu authenticated context |
| Login session mode | saveContext trước response commit |
| Request B cùng session | User đúng principal và authorities |
| Request B không session | Không lấy user của A |
| Request B session khác | Không lấy user của A |
| ContextHolder clear cuối request | Không rò user giữa threads/requests |
| Cookie Secure/Path/Domain | Browser gửi đúng public route |
| Cookie SameSite cross-site flow | Hoạt động theo policy và browser support |
| SPA fetch cross-origin thiếu credentials | 401/redirect theo policy, không nhầm service outage |
| SPA fetch credentials include | Session cookie hợp lệ được gửi |
| OPTIONS preflight | Không bị auth filter từ chối sai |
| Protected POST thiếu CSRF | 403 CSRF nhưng không được kết luận auth mất |
| Protected GET thiếu role | 403 authorization |
| API STATELESS request không Bearer | 401 mong đợi |
| API STATELESS request Bearer valid | 200 với principal từ token |
| Multi-chain login/web vs API | Đúng chain và mô hình identity |
| Proxy spoofed headers | Không thay host/cookie/redirect trái policy |
| Request đi qua node-1 rồi node-2 | Shared session hoạt động |
| Session rotation sau login | Cookie mới hợp lệ, cookie cũ không tự cấp quyền |
| Logout/session expiry | Authentication không được hồi sinh |
| OAuth2/SAML callback thành công | RP Authentication hoàn tất và session/token đúng |
| MockMvc không `with(user(...))` ở request B | Thực sự kiểm persistence |
| Login success event trước khi save thất bại | Không coi event đủ để khẳng định login persisted |

Nên test riêng **unit cho custom authentication component**, **MockMvc cho filter/repository**, **E2E browser cho cookie/CORS**, và **integration dưới load balancer** cho session sharing. Một unit test chỉ gọi `SecurityContextHolder.getContext()` không thay thế được E2E.

## 24. Các anti-pattern cần tránh

- Đặt `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` để “giữ Authentication” cho mọi requests: gây nguy cơ chia sẻ principal giữa người dùng.
- Bật `MODE_INHERITABLETHREADLOCAL` để chữa mọi async/pooled-thread problems: pooled threads có thể giữ principal cũ.
- Tắt `SecurityContextHolderFilter` hoặc không clear context để request sau nhìn thấy user: phá isolation.
- Tắt `csrf()`/CORS hoặc đặt `anyRequest().permitAll()` để HTTP 403 biến mất.
- Dùng `UsernamePasswordAuthenticationToken.authenticated(...)` trực tiếp từ username/password client gửi, bỏ qua AuthenticationManager.
- Tự thêm `HttpSession` trong một API STATELESS mà chưa thay đổi threat model.
- Lưu access token/refresh token/session ID vào URL query hoặc application logs.
- Trust mọi `X-Forwarded-*` header từ Internet để tạo cookie/redirect.
- Chỉ test một request có `@WithMockUser` và kết luận session đã lưu.
- Cố cho Browser đọc HttpOnly cookie bằng JavaScript.
- Đổi `SameSite=None` hoặc `allowCredentials=true` + wildcard origin mà không xét CSRF/cross-site threats.
- Đọc raw SecurityContext từ session store rồi sửa mutable object chia sẻ giữa các requests.
- Coi login event, redirect 302 hoặc UI “success” là bằng chứng user đã auth ở mọi routes.

**Bảo mật đòi hỏi đúng ranh giới:** mỗi request chỉ được nhận Authentication từ session/token đã xác thực; không giữ thread state tình cờ.

## 25. Checklist điều tra 10 phút đầu

1. Login request thật có thành công qua Spring Security authentication filter/manager không?
2. Request B trả 401, 403 hay 302? Trình duyệt có bị redirect loop không?
3. App dự kiến **session-based** hay **stateless Bearer**?
4. Nếu session-based, Authentication được `saveContext` vào đúng repository trước commit chưa?
5. Response login có Set-Cookie, browser có lưu và gửi lại cookie cho B không?
6. Session ID có đổi do session fixation protection không?
7. Cookie Domain/Path/Secure/SameSite, origin/CORS và Fetch credentials có phù hợp không?
8. SecurityFilterChain của A và B có cùng identity contract/repository không?
9. Proxy/cluster/session store có đưa B tới nơi đọc được session không?
10. Request B có Authentication đúng nhưng bị 403 do quyền/CSRF không?
11. OAuth2/SAML callback có hoàn tất RP authentication và correlation state không?
12. MockMvc test đã có request thứ hai cùng session **không dùng mock user** chưa?
13. Logs có giữ kín cookie, token, password và PII không?
14. Đã sửa nguyên nhân gốc, kiểm logout/expiry/concurrent session và test lại qua browser chưa?

**Kết luận:** “Đăng nhập thành công nhưng request sau chưa xác thực” phải được chẩn đoán như một vấn đề **lưu và khôi phục trạng thái qua ranh giới request**, không phải mặc định là sai mật khẩu hay Spring Security “xóa nhầm user”. Trong Servlet stateful, xác thực → tạo SecurityContext → **save vào SecurityContextRepository** → browser giữ/gửi cookie → request mới load context. Trong stateless API, client phải gửi Bearer token mỗi lần. Nếu session và principal đúng mà vẫn 403, hãy điều tra authorization hoặc CSRF. Bảo vệ các ranh giới này giúp sửa lỗi mà không đánh đổi tính cô lập giữa người dùng.

### Tài liệu tham khảo chính thức

- Spring Security — Authentication Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Servlet CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — MockMvc RequestPostProcessors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html
- Spring Session — HTTP Session with Redis: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- MDN — Request credentials mode: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — Set-Cookie header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
