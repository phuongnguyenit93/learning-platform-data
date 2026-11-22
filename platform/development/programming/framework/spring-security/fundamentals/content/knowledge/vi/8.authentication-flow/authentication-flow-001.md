# Các giai đoạn tiếp nhận thông tin, kiểm tra và thiết lập danh tính trong Spring Security

## 1. Bức tranh tổng thể

Một ứng dụng Spring Boot có endpoint cần đăng nhập không chỉ “so sánh username với password”. Spring Security chia quá trình xác thực thành các giai đoạn có trách nhiệm và vòng đời khác nhau:

1. **Tiếp nhận HTTP request:** servlet container và chuỗi security filter chọn cơ chế xử lý.
2. **Trích xuất thông tin xác thực:** HTTP Basic header, form login, Bearer token hoặc một loại credential khác.
3. **Tạo yêu cầu Authentication chưa được tin cậy:** chứa thông tin client khai và chứng cứ cần xác minh.
4. **Kiểm tra danh tính:** AuthenticationManager điều phối AuthenticationProvider, nguồn user, password encoder hoặc bộ xác minh token.
5. **Tạo kết quả Authentication đáng tin:** principal, authorities, trạng thái authenticated và xử lý credentials.
6. **Thiết lập SecurityContext cho request:** filter hoặc authentication mechanism sử dụng kết quả đã xác thực.
7. **Áp dụng authorization:** endpoint/method/resource được phép truy cập hay bị từ chối.
8. **Duy trì hoặc kết thúc ngữ cảnh:** SecurityContextRepository/session hay cơ chế stateless quyết định request sau có cần xác thực lại hay không.

Bài này đi sâu vào **từng giai đoạn của luồng xác thực**, sự phối hợp giữa các lớp và điểm phát sinh 401/403. Ví dụ thực hành dùng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet**, HTTP Basic và UserDetailsService trong bộ nhớ để có thể quan sát bằng curl.

**Điều phải nhớ:** Authentication trả lời “credential có chứng minh danh tính không?”, còn Authorization trả lời “danh tính đã xác thực có quyền thực hiện thao tác này không?”. Đăng nhập thành công không bảo đảm được truy cập mọi URL hoặc bản ghi.

### Mục tiêu sau bài học

Người học có thể:

- Giải thích rõ cơ chế filter nhận credential, Authentication chưa xác thực và kết quả đã xác thực.
- Vẽ được tuyến request đi qua FilterChainProxy, BasicAuthenticationFilter, ProviderManager và DaoAuthenticationProvider.
- Hiểu UserDetailsService, PasswordEncoder và kiểm tra trạng thái tài khoản phối hợp ra sao.
- Nêu chính xác ai đưa Authentication vào SecurityContext và khi nào context được lưu.
- Phân biệt các nhánh thành công, thiếu credential, credential sai, thiếu quyền và URL không tồn tại.
- Mô tả khác biệt giữa HTTP Basic, form login, session và Bearer token.
- Chạy ví dụ Spring Boot kiểm thử HTTP 200, 401, 403 và đọc danh tính tại Controller.
- Nhận diện lỗi khi tự viết login endpoint hoặc custom authentication filter.

## 2. Bản đồ trách nhiệm của các thành phần

| Thành phần | Vai trò trong luồng | Không phải trách nhiệm của nó |
| --- | --- | --- |
| Servlet container | Nhận HTTP request, gọi filter chain | Không xác minh password thay ứng dụng |
| DelegatingFilterProxy | Cầu nối Servlet Filter tới bean của Spring | Không tự quyết định user đúng/sai |
| FilterChainProxy | Chọn SecurityFilterChain phù hợp, quản lý security filters | Không tự tải user hay so password |
| SecurityFilterChain | Tập filter/policy áp dụng cho request | Không mặc nhiên là toàn bộ các chain cộng lại |
| BasicAuthenticationFilter | Đọc HTTP Basic header, tạo Authentication chưa xác thực, gọi manager | Không tự lưu kho tài khoản |
| UsernamePasswordAuthenticationFilter | Đọc form login và gọi manager, xử lý login thành công/thất bại | Không tự thay PasswordEncoder |
| Authentication | Mang principal, credentials, authorities, details, authenticated | Không tự kiểm tra thông tin client |
| AuthenticationManager | Interface authenticate(Authentication) | Không tự gửi HTTP response/cookie |
| ProviderManager | AuthenticationManager dùng danh sách AuthenticationProvider | Không biết cách kiểm tra mọi loại credential |
| AuthenticationProvider | Kiểm chứng một loại Authentication | Không tự đưa context vào HTTP request |
| DaoAuthenticationProvider | Kiểm tra username/password qua UserDetailsService và PasswordEncoder | Không tự quyết định quyền trên URL |
| UserDetailsService | Tìm UserDetails theo username | Không so raw password với hash |
| PasswordEncoder | Mã hóa băm và đối chiếu password | Không cấp vai trò hoặc phân quyền |
| SecurityContextHolder | Cung cấp SecurityContext đang được dùng | Không tự lưu context sang request sau |
| SecurityContextRepository | Đọc/lưu SecurityContext theo chính sách | Không thực hiện password authentication |
| AuthorizationFilter/AuthorizationManager | Kiểm tra policy HTTP bằng Authentication và rule | Không xác minh mật khẩu |
| AuthenticationEntryPoint/handlers | Chuyển lỗi bảo mật thành HTTP response/redirect | Không thay AuthenticationProvider |

Nên tưởng tượng **filter nhận và chuyển đổi**, **manager điều phối**, **provider kiểm chứng**, **context giữ kết quả**, **authorization ra quyết định**.

Một request public có thể không phải xác thực. Một request đã có session hợp lệ có thể được khôi phục SecurityContext mà không phải tải lại UserDetails mỗi lần. Vì vậy sơ đồ sau mô tả đường đi phổ biến của một request **thực sự mang credentials**, không khẳng định mọi HTTP request đều gọi DaoAuthenticationProvider.

## 3. Sơ đồ toàn bộ luồng HTTP Basic

Giả sử client gửi username alice và password learn123 tới GET /private. Cú pháp HTTP minh họa:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6bGVhcm4xMjM=
~~~

Chuỗi Base64 biểu diễn alice:learn123. **Base64 không phải mã hóa bảo mật**; chỉ dùng ví dụ trên localhost. Khi gửi credentials qua mạng thật cần HTTPS và cơ chế quản lý secret phù hợp.

~~~text
[1] HTTP request: GET /private + Authorization: Basic
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
SecurityFilterChain áp dụng cho URL
    |
    v
[2] BasicAuthenticationFilter
    |-- Parse Basic header -> username, raw password
    |-- Tạo UsernamePasswordAuthenticationToken chưa xác thực
    v
[3] AuthenticationManager.authenticate(attempt)
    |
    v
ProviderManager
    |-- Tìm AuthenticationProvider hỗ trợ loại token
    v
[4] DaoAuthenticationProvider
    |-- UserDetailsService.loadUserByUsername("alice")
    |-- PasswordEncoder.matches(rawPassword, storedHash)
    |-- Kiểm tra trạng thái account thích hợp
    |
    +-- FAIL -> AuthenticationException
    |            |
    |            +-> filter/handler xử lý, có thể trả HTTP 401
    |
    +-- SUCCESS -> Authentication đáng tin
                  (principal, authorities, authenticated=true)
                         |
                         v
[5] ProviderManager -> BasicAuthenticationFilter
    |
    v
[6] Filter đặt Authentication vào SecurityContext
    |
    v
[7] AuthorizationFilter kiểm tra authenticated()/role
    |
    +-- Đủ quyền -> DispatcherServlet -> Controller -> HTTP 200
    |
    +-- Thiếu quyền -> exception handling -> HTTP 403
    |
    v
[8] Kết thúc request: context được xử lý/clear theo lifecycle;
    request sau khôi phục hoặc xác thực lại theo repository/session/token
~~~

**Sơ đồ theo trách nhiệm**, lược bỏ nhiều filter (SecurityContextHolderFilter, AnonymousAuthenticationFilter, ExceptionTranslationFilter, CsrfFilter...) và chi tiết thứ tự thực tế. Thứ tự chính xác phụ thuộc Spring Security version và SecurityFilterChain đã cấu hình; không dùng sơ đồ làm danh sách filter tuyệt đối.

## 4. Giai đoạn 1 — HTTP request đi vào SecurityFilterChain

Servlet container như Tomcat nhận request và chuyển qua Servlet filters. Trong ứng dụng Spring Security, **DelegatingFilterProxy** dẫn request tới **FilterChainProxy**. FilterChainProxy chọn chuỗi bảo mật đầu tiên khớp request, rồi chạy các filter của chuỗi đó.

Điều này quyết định:

- Request có áp dụng Spring Security hay không.
- Authentication filter nào có mặt: Basic, form login, Bearer token...
- CSRF, session, exception handling và authorization rules nào có hiệu lực.
- URL nào cần authenticated, role cụ thể hay được permitAll.

**Phải phân biệt securityMatcher và requestMatchers:**

- **securityMatcher** ở HttpSecurity giới hạn phạm vi **cả SecurityFilterChain**.
- **requestMatchers** trong authorizeHttpRequests áp một rule authorization **sau khi chain đã được chọn**.

Nếu ứng dụng có nhiều chain mà không chain nào khớp URL, request **không được Spring Security bảo vệ**. Vì vậy kiến trúc nhiều chain cần một fallback có chính sách phù hợp.

Ở ứng dụng mẫu của bài, chỉ có một SecurityFilterChain và không đặt securityMatcher chuyên biệt; nó nhận các request Servlet bình thường rồi áp rule URL.

### 4.1. Endpoint public có bỏ qua tất cả filter không?

Không mặc nhiên. **permitAll** nói rằng request không cần Authentication để được authorization cho phép. Nó không xóa mọi filter khỏi chain. Nếu client chủ động gửi HTTP Basic header với credentials sai tới một endpoint permitAll, BasicAuthenticationFilter vẫn có thể thử xác thực và trả 401.

Đây là lý do phải phân biệt **có authentication filter trong chain** với **endpoint yêu cầu authentication**.

## 5. Giai đoạn 2 — Filter trích xuất credentials

Authentication filter đọc dữ liệu từ request theo giao thức đã cấu hình:

| Cơ chế | Nơi chứa credentials | Filter/cơ chế thường gặp |
| --- | --- | --- |
| HTTP Basic | Authorization: Basic Base64(username:password) | BasicAuthenticationFilter |
| Form login | Username/password trong form POST login | UsernamePasswordAuthenticationFilter |
| HTTP Bearer | Authorization: Bearer access_token | BearerTokenAuthenticationFilter |
| OAuth2/OIDC login | Authorization code/callback qua protocol | OAuth2LoginAuthenticationFilter và thành phần liên quan |
| Session login đã có | Cookie session trỏ tới context được lưu | SecurityContextRepository và filters ngữ cảnh |

Không phải mọi cơ chế tạo UsernamePasswordAuthenticationToken. HTTP Basic và form login thường dùng loại này; Bearer token và OIDC có các Authentication implementation riêng.

### 5.1. Token đầu vào phải ở trạng thái chưa xác thực

Ví dụ khi nhận username/password, filter có thể tạo:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

Đoạn code này là **snippet trong phương thức Java đã có imports**, chưa phải ứng dụng độc lập.

Ở thời điểm đó:

- principal đầu vào thường là username do client khai.
- credentials là password chưa được xác minh.
- authenticated=false.
- authorities đáng tin chưa được cấp.
- details có thể chứa metadata phụ trợ, nhưng không được coi là bằng chứng danh tính.

Client có thể khai tên “admin” nhưng chưa chứng minh mình là admin. **Không tạo Authentication authenticated=true chỉ dựa vào username, ID hoặc role do client truyền lên.**

### 5.2. Xử lý credentials khi nhận

- HTTP Basic gửi password dưới dạng Base64, dễ giải mã; phải dùng HTTPS qua mạng.
- Không log Authorization header, raw password, OTP, token hay cookie.
- Giới hạn kích thước request/header, chuẩn hóa đầu vào theo giao thức và tránh thông báo lỗi tiết lộ user có tồn tại.
- Không tự xử lý bằng cách so password plaintext trong Controller.
- Không dùng URL query parameter làm nơi gửi password.
- Với browser form login, CSRF và session lifecycle cần được đánh giá đầy đủ.

Authentication filter không cần biết database lưu user ra sao. Đây là lợi ích của việc tách **thu thập credentials** khỏi **kiểm chứng credentials**.

## 6. Giai đoạn 3 — AuthenticationManager nhận yêu cầu

AuthenticationManager định nghĩa hợp đồng:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Lời gọi nhận Authentication chưa đáng tin và trả về Authentication đã xác thực, hoặc ném AuthenticationException. Nó **không** trả HTTP 200/401/403, không trực tiếp chuyển hướng, không tự tạo cookie và không tự đặt context vào request.

Triển khai phổ biến là **ProviderManager**, được cấp một danh sách AuthenticationProvider.

### 6.1. ProviderManager chọn provider

Luồng khái quát:

1. Xét provider.supports(authentication.getClass()).
2. Provider không hỗ trợ loại token được bỏ qua.
3. Provider phù hợp được gọi authenticate(authentication).
4. Trả một Authentication hợp lệ khác null nghĩa là xác thực thành công theo provider.
5. Provider có thể trả null nếu không quyết định được và cho provider khác thử.
6. Khi ném AuthenticationException, ProviderManager xử lý theo loại lỗi; một số exception có thể dừng ngay, chẳng hạn AccountStatusException.
7. Nếu có parent AuthenticationManager, cấu hình có thể dùng parent khi phù hợp.
8. Nếu không provider nào hỗ trợ, có thể phát sinh ProviderNotFoundException.

**supports=true không đồng nghĩa password đúng.** Nó chỉ cho biết provider có thể thử xử lý kiểu token.

Không tạo một chuỗi fallback để provider thứ hai chấp nhận credentials mà provider thứ nhất đã từ chối vì lý do bảo mật. Hành vi retry giữa provider phải được thiết kế rõ và kiểm thử các exception.

### 6.2. AuthenticationManager không có HTTP response

Ví dụ:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

Lệnh trên chỉ cung cấp kết quả cho **bên gọi**. Nếu một custom Controller tự gọi lệnh này rồi trả JSON “login OK”, request sau chưa chắc đã được đăng nhập. Còn cần xử lý **SecurityContext**, cơ chế lưu context/session hoặc phát token thích hợp.

## 7. Giai đoạn 4 — Provider kiểm tra danh tính

Với username/password, Spring Security thường dùng **DaoAuthenticationProvider**, kết hợp:

- **UserDetailsService** tìm UserDetails theo username.
- **PasswordEncoder** thực hiện matches(raw, encoded).
- **UserDetails** mang username, encoded password, authorities và flags trạng thái account.
- Các kiểm tra enabled, accountNonLocked, accountNonExpired, credentialsNonExpired theo cấu hình.

~~~text
UsernamePasswordAuthenticationToken("alice", rawPassword)
                     |
                     v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername("alice")
    |           |
    |           +--> username=alice
    |           +--> password=<BCrypt hash>
    |           +--> authorities=[ROLE_USER]
    |           +--> flags enabled/nonLocked/...
    |
    +--> PasswordEncoder.matches(rawPassword, hash)
    |
    +--> account status checks
    |
    +--> SUCCESS: Authentication đã xác thực
    |
    +--> FAIL: AuthenticationException
~~~

### 7.1. Vì sao tìm được user vẫn chưa đủ?

UserDetailsService chỉ truy xuất bản ghi tài khoản; tìm được username **không chứng minh request được gửi bởi chủ tài khoản**. DaoAuthenticationProvider phải kiểm tra mật khẩu và các điều kiện trạng thái liên quan.

Với BCrypt, mỗi hash thường có salt, vì vậy không lấy raw password so trực tiếp với hash bằng String.equals. Dùng PasswordEncoder.matches để đối chiếu theo thuật toán được cấu hình.

### 7.2. Lỗi thường gặp

- **BadCredentialsException:** credentials sai hoặc hệ thống chọn không tiết lộ username tồn tại.
- **UsernameNotFoundException:** nguồn user không tìm thấy tên; provider có thể che thành lỗi bad credentials để giảm user enumeration.
- **LockedException / DisabledException:** trạng thái tài khoản ngăn đăng nhập.
- **ProviderNotFoundException:** không có provider phù hợp với Authentication.
- **Sự cố nguồn user/credential:** có thể là lỗi cấu hình hoặc hệ thống, không nên xem mọi HTTP 401 chỉ là sai password.

Khi debug, kiểm tra login mechanism, kiểu Authentication, manager/provider thực dùng, cách tải user và password encoder trước khi sửa authorization.

### 7.3. Các cơ chế không dùng password

Với Bearer JWT, provider/decoder thường kiểm tra chữ ký, issuer, audience, expiry và các claims/validators theo cấu hình. Với OIDC login, app còn kiểm tra protocol callback và identity provider. Không cố dùng DaoAuthenticationProvider để so password cho mọi loại token.

Cùng nguyên tắc, kết quả cuối cùng phải là **danh tính được chứng minh bởi nguồn tin cậy**, với authorities đã được ánh xạ và giới hạn đúng phạm vi.

## 8. Giai đoạn 5 — Kết quả Authentication sau thành công

Sau khi kiểm tra hợp lệ, Authentication có thể có:

| Trường | Dạng điển hình |
| --- | --- |
| principal | UserDetails đã xác minh, custom principal hoặc object theo cơ chế |
| credentials | Thường đã bị xóa/để null khi không còn cần |
| authorities | ROLE_USER, ROLE_ADMIN hoặc quyền theo nguồn tin cậy |
| authenticated | true |
| details | Metadata tối thiểu theo filter/cơ chế |

Ví dụ trong luồng DaoAuthenticationProvider:

~~~text
Authentication result
  principal = UserDetails(username=alice, ...)
  authorities = [ROLE_USER]
  authenticated = true
  credentials = có thể được xóa
~~~

**Authorities không phải thông tin mà client được tự chọn.** Nếu frontend gửi role=ADMIN, backend không được dùng role ấy để tạo Authentication thành công. Role phải lấy từ UserDetails, identity provider, JWT đã được xác minh hoặc nguồn quyền đáng tin.

### 8.1. Xóa credentials sau xác thực

ProviderManager mặc định cố xóa dữ liệu credentials khỏi Authentication trả về nếu object hỗ trợ **CredentialsContainer**. Điều này giảm thời gian tồn tại của password trong kết quả Authentication, nhưng không xóa tự động mọi bản sao trong Java String, request buffer, cache, log hoặc heap.

Nếu UserDetails có cache và được dùng chung tham chiếu với principal, việc xóa credential có thể ảnh hưởng object cache. Cần thiết kế cache/lifecycle đúng, không tắt credential erasure tùy tiện.

**Không trả nguyên Authentication/UserDetails ra API** chỉ vì Spring Security đã xóa credentials. Principal có thể chứa email, password hash hoặc thông tin nội bộ tùy implementation. Dùng response DTO chỉ chọn trường cần trả.

## 9. Giai đoạn 6 — Thiết lập SecurityContext

Đây là bước thường bị nhầm với AuthenticationManager.

**AuthenticationManager.authenticate() trả kết quả**; còn **filter/cơ chế xác thực** thường tạo hoặc cập nhật SecurityContext và đưa Authentication vào SecurityContextHolder của request.

Với HTTP Basic, **BasicAuthenticationFilter** kiểm tra Authorization header, gọi AuthenticationManager, nhận kết quả và đặt Authentication đã xác thực vào SecurityContext. Với form login, **UsernamePasswordAuthenticationFilter/AbstractAuthenticationProcessingFilter** xử lý thành công và failure theo pipeline riêng.

Sơ đồ:

~~~text
AuthenticationManager.authenticate(attempt)
            |
            v
Authentication verified
            |
            v
Authentication filter xử lý thành công
            |
            v
SecurityContext.setAuthentication(verified)
            |
            v
SecurityContextHolder.setContext(context)
            |
            v
Controller và AuthorizationFilter đọc Authentication hiện hành
~~~

### 9.1. SecurityContextHolder là gì?

SecurityContextHolder thường dùng ThreadLocal trong ứng dụng Servlet để cung cấp SecurityContext của execution hiện hành. Code có thể truy cập:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Đây là snippet minh họa đặt trong class có import cần thiết; trong Controller, việc inject Principal hoặc Authentication thường thuận tiện và giảm phụ thuộc trực tiếp vào holder.

**Đừng tự suy ra context tự đi qua các thread.** Với asynchronous work, executor hoặc reactive stack, phải dùng cơ chế lan truyền context phù hợp. Không giữ SecurityContextHolder trong static biến ứng dụng để “dùng chung user”.

### 9.2. Context trên request khác lưu cho request sau

Việc gọi:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

chỉ đưa Authentication vào ngữ cảnh **đang xử lý**. Trong Spring Security 6, việc custom code muốn context tồn tại qua request có thể cần **SecurityContextRepository.saveContext(context, request, response)** cùng repository, filter/session policy thích hợp.

Đoạn này là **snippet sau khi biến verified đã được xác thực**. Nó chưa phải custom login implementation đầy đủ. Nếu tự tạo login endpoint còn phải xử lý CSRF, session fixation, session lifecycle, failure/success handlers, persistence và cookie policy. Với đa số ứng dụng, nên dùng các authentication filters sẵn có.

### 9.3. Ai xóa context ở cuối request?

Các security filter quản lý vòng đời context, bao gồm việc tránh để Authentication của request trước rò sang request khác trên thread được tái sử dụng. Trong stack Servlet, hệ thống phải có đúng cơ chế context holder/filter/repository; không tự giữ context trong ThreadLocal tùy tiện mà quên clear.

Nếu tự thực hiện asynchronous hoặc custom filter, phải chú ý vòng đời và cách context được khôi phục/clear đúng framework version.

## 10. Giai đoạn 7 — Authorization được xét sau khi có danh tính

**Authorization** khác authentication. Request có thể:

- Không có Authentication đáng tin và bị yêu cầu đăng nhập.
- Có Authentication đúng nhưng thiếu ROLE_ADMIN.
- Có role phù hợp nhưng thiếu quyền sở hữu tài nguyên.
- Có Authentication và đủ quyền, được Controller xử lý.

Một SecurityFilterChain có thể khai báo:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/private").authenticated()
    .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

Đây là DSL trong method cấu hình, không phải file Java độc lập.

**authenticated()** sử dụng cơ chế trust resolver của Spring Security. Đừng kiểm tra thủ công mỗi isAuthenticated() rồi coi mọi Authentication đã đăng nhập: **AnonymousAuthenticationToken** có thể mang authenticated=true về mặt thuộc tính nhưng vẫn được framework nhận là anonymous cho các rule yêu cầu người dùng thật.

**hasRole("ADMIN")** thường kiểm tra authority **ROLE_ADMIN**. Người dùng có ROLE_USER mà không có ROLE_ADMIN đã xác thực thành công vẫn có thể bị HTTP 403 ở /admin.

Nếu API đọc /orders/42, chỉ kiểm tra ROLE_USER thường không đủ: cần kiểm tra **ownerId, tenantId, permission và trạng thái nghiệp vụ**. Spring Security không tự biết bản ghi nào thuộc user nào.

## 11. Giai đoạn 8 — Kết thúc request và duy trì danh tính

### 11.1. HTTP Basic

Client thường gửi Authorization: Basic ở các request tiếp theo. Khi header có mặt, filter có thể xác thực từ credentials; không nên mặc định một lần Basic thành công tự tạo session login lâu dài.

HTTP Basic có thể được cấu hình với SecurityContextRepository hoặc remember-me khác nhau. Nếu muốn stateless, cần thiết kế SessionCreationPolicy, repository, request cache và cookie/session behavior rõ ràng.

### 11.2. Form login với HTTP session

Browser gửi POST login, filter xác thực username/password, xử lý session authentication strategy và có thể lưu SecurityContext cho request sau. Cookie session giúp server truy xuất context/phiên đã được thiết lập.

Spring Security 6 dùng cơ chế **SecurityContextHolderFilter**/SecurityContextRepository theo mặc định và nhấn mạnh **explicit save** đối với custom code. Các authentication mechanisms tích hợp đã thực hiện những bước lifecycle cần thiết theo cấu hình của chúng; đừng tự viết controller login chỉ để giả lập một phần quy trình.

Cần quản lý session fixation, timeout, logout, CSRF token, cookie flags và invalidation khi quyền thay đổi. Không cho rằng kết quả AuthenticationManager tự phát cookie hoặc tự lưu user vào database.

### 11.3. Bearer token/stateless API

Client gửi Bearer token ở từng request. Hệ thống xác minh token, tạo Authentication và đặt vào SecurityContext của request hiện hành, rồi xử lý authorization. Khi kết thúc request, context thread-local được dọn; request sau lại dựa vào token nếu không có persistence khác.

JWT thông thường có payload đọc được; chữ ký nhằm kiểm tra tính toàn vẹn, **không mã hóa bí mật trong claims**. Không đưa password, password hash, refresh token hoặc thông tin cá nhân không cần thiết vào JWT.

### 11.4. Anonymous request

Khi không có người dùng xác thực, **AnonymousAuthenticationFilter** có thể đặt một AnonymousAuthenticationToken để các thành phần sau có danh tính guest theo policy. Điều này không chứng minh login thành công.

Nhờ đó endpoint permitAll có thể tiếp tục, còn endpoint authenticated sẽ bị xử lý theo luồng yêu cầu xác thực.

## 12. Phân biệt luồng HTTP Basic và form login

| Vấn đề | HTTP Basic | Form login |
| --- | --- | --- |
| Credential từ đâu? | Header Authorization: Basic | Form POST login |
| Filter chính | BasicAuthenticationFilter | UsernamePasswordAuthenticationFilter |
| Token đầu vào phổ biến | UsernamePasswordAuthenticationToken | UsernamePasswordAuthenticationToken |
| Manager/provider | Thường ProviderManager + DaoAuthenticationProvider | Có thể dùng chung manager/provider đó |
| Thiếu Authentication trên URL private | Thường 401 + challenge | Thường redirect 302 tới login page |
| Password sai | Filter/entry point có thể trả 401 | Failure handler xử lý, có thể redirect tới trang lỗi |
| Thành công | Tiếp tục filter chain/request | Success handler/redirect, session strategy |
| Duy trì request sau | Thường client gửi lại credentials | Thường session và context persistence |
| CSRF | Cần đánh giá với browser tự gửi Basic | Thường cần CSRF token với form/session |

Cả hai có thể dùng cùng DaoAuthenticationProvider vì chúng chỉ khác cách **nhận credential** và xử lý HTTP. Provider không cần biết password đến từ HTML form hay Authorization header.

Nếu ứng dụng tự cấu hình SecurityFilterChain, hãy bật đúng cơ chế mong muốn bằng httpBasic(...) hoặc formLogin(...), không mặc định rằng starter-security sẽ tự cung cấp mọi giao thức sau khi custom chain.

## 13. Ví dụ Spring Boot 3.3.x chạy được

Ví dụ dùng HTTP Basic để nhìn rõ luồng nhận credentials, xác thực, đưa danh tính vào SecurityContext và phân quyền. Không tự viết filter hoặc provider để tránh làm bài cơ bản trở thành demo cơ chế tự chế.

### 13.1. Tạo project và dependency

Tạo project Spring Boot 3.3.x, Java 17+ với Spring Initializr hoặc Gradle Wrapper đã có. Trong **build.gradle** (Groovy DSL), cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là phần dependencies của một dự án Boot có plugin/build tool đã thiết lập, không phải toàn bộ file build.gradle độc lập.

### 13.2. Một file Java hoàn chỉnh

Tạo file **src/main/java/com/example/authstages/AuthStagesApplication.java**:

~~~java
package com.example.authstages;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthStagesApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStagesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    Map<String, Object> privateEndpoint(Authentication authentication) {
        var authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "user", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authorities
        );
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **file Java hoàn chỉnh bên trong một project Boot**. Public class AuthStagesApplication trùng tên file, Controller là class package-private cùng package nên component scan tìm được. Java 17 hỗ trợ var và Stream.toList. Spring Security được cấu hình thông qua bean SecurityFilterChain.

**Các bean hoạt động thế nào?**

1. **PasswordEncoder** tạo BCryptPasswordEncoder.
2. **UserDetailsService** tạo hai tài khoản in-memory: alice có ROLE_USER, admin có ROLE_ADMIN. Password được hash trước khi lưu; dữ liệu hard-code chỉ dành cho học tập.
3. Spring Security có thể dùng UserDetailsService và PasswordEncoder để xây cơ chế xác thực username/password tiêu chuẩn, với DaoAuthenticationProvider/AuthenticationManager phù hợp theo cấu hình.
4. **SecurityFilterChain** yêu cầu GET /private authenticated, GET /admin ROLE_ADMIN và cho GET /public public; URL khác denyAll.
5. **httpBasic** bật filter HTTP Basic, **formLogin.disable** tránh redirect form trong bài kiểm thử.
6. Controller **không trả nguyên Authentication**; nó chỉ trả các trường được chọn để minh họa principal và authorities.

**Không tự tắt CSRF.** Ví dụ chỉ có các endpoint GET. Nếu thêm POST/PUT/DELETE, phải thiết kế CSRF dựa trên mô hình browser và cách truyền credentials; HTTP Basic do browser giữ vẫn có thể chịu rủi ro CSRF.

### 13.3. Chạy ứng dụng

Trong thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell dùng **.\gradlew.bat bootRun**. Khi server chạy trên localhost:8080, thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Trong PowerShell có thể dùng **curl.exe** nếu curl là alias. HTTP Basic chỉ dùng trên localhost cho demo; gửi credentials trên mạng cần HTTPS. Để tránh password nằm trong shell history, dùng **curl -i -u alice URL** và nhập password qua prompt.

### 13.4. Bảng status dự kiến

| Request | HTTP status | Giai đoạn quyết định |
| --- | --- | --- |
| GET /public không credentials | **200**, body public OK | Authorization permitAll; Controller chạy |
| GET /private không credentials | **401** | Không có Authentication hợp lệ; HTTP Basic entry point |
| GET /private với alice:wrong | **401** | DaoAuthenticationProvider không xác minh được password |
| GET /private với alice:learn123 | **200** | Authentication thành công; Authorization authenticated() |
| GET /admin với alice:learn123 | **403** | Authentication thành công, Authorization thiếu ROLE_ADMIN |
| GET /admin với admin:admin123 | **200**, body admin OK | Có ROLE_ADMIN, Controller chạy |

Với alice đăng nhập đúng, GET /private dự kiến có JSON:

~~~json
{
  "user": "alice",
  "authenticated": true,
  "authorities": ["ROLE_USER"]
}
~~~

Thứ tự key JSON không được đảm bảo. Bảng và JSON là **kết quả dự đoán theo cấu hình**, không phải log thực thi đã đo trong tài liệu. Nếu thêm filter, handler hoặc proxy, phải xác minh response thực tế.

### 13.5. Giải thích cùng một request qua từng bước

Với GET /private và alice:learn123:

1. Tomcat nhận request.
2. FilterChainProxy chọn SecurityFilterChain.
3. BasicAuthenticationFilter đọc Authorization header.
4. Tạo UsernamePasswordAuthenticationToken chưa xác thực.
5. Gọi AuthenticationManager; ProviderManager chuyển cho provider username/password.
6. DaoAuthenticationProvider tải alice, kiểm tra BCrypt matches, account flags.
7. Trả Authentication có principal alice, ROLE_USER, authenticated=true.
8. BasicAuthenticationFilter thiết lập Authentication vào SecurityContext.
9. AuthorizationFilter kiểm tra authenticated() và cho đi tiếp.
10. Controller đọc Authentication hiện hành, tạo response DTO/Map chỉ gồm user, authenticated và authorities.

Không có bước nào yêu cầu Controller tự đọc raw password hoặc gọi UserDetailsService để xác thực lại user.

## 14. Ba luồng thất bại cần phân biệt

### 14.1. Request không mang credentials

~~~text
GET /private, no Authorization
      |
      v
Authentication filter không tạo login thành công
      |
      v
AuthorizationFilter yêu cầu authenticated()
      |
      v
ExceptionTranslationFilter/AuthenticationEntryPoint
      |
      v
HTTP 401, thường kèm WWW-Authenticate khi dùng Basic
~~~

Không phải lúc nào UserDetailsService cũng được gọi trong nhánh này. Lỗi là không có danh tính đã xác thực để vào tài nguyên private, không nhất thiết có password sai.

### 14.2. Có credentials nhưng kiểm tra thất bại

~~~text
GET /private, Authorization: Basic alice:wrong
      |
      v
BasicAuthenticationFilter -> AuthenticationManager
      |
      v
DaoAuthenticationProvider -> PasswordEncoder.matches = false
      |
      v
AuthenticationException
      |
      v
Filter/AuthenticationEntryPoint xử lý
      |
      v
HTTP 401 (trong cấu hình demo)
~~~

Controller không chạy. Trên luồng Basic thông thường, filter xóa context thất bại và phát challenge; cách hiện thực còn tùy handler, ignoreFailure và cấu hình khác.

### 14.3. Đúng password, thiếu authority

~~~text
GET /admin, Authorization: Basic alice:learn123
      |
      v
AuthenticationManager xác thực thành công
      |
      v
SecurityContext chứa ROLE_USER
      |
      v
AuthorizationFilter cần ROLE_ADMIN
      |
      v
AccessDenied -> HTTP 403
~~~

Tầng authentication đã làm đúng nhiệm vụ. Không sửa lỗi này bằng cách tắt security, bỏ check password hay tự gắn ROLE_ADMIN cho mọi user. Phải xem lại quyền của tài khoản và policy nghiệp vụ.

### 14.4. URL chưa có Controller và HTTP 404

Nếu SecurityFilterChain đã cho request đi qua nhưng MVC không có mapping, có thể trả 404. Với anyRequest().denyAll, một URL chưa được permit có thể bị từ chối trước khi MVC xử lý, dẫn tới 401/403 thay vì 404. Không dùng status của URL chưa tồn tại như chứng cứ rằng policy bảo mật đã đầy đủ.

## 15. Tự tạo login endpoint: điểm khó là thiết lập và lưu context

Một custom Controller có thể gọi AuthenticationManager trực tiếp:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

Nhưng chỉ vậy **chưa thiết lập đăng nhập cho request hiện hành hoặc request tiếp theo**.

Nếu thiết kế session login, sau khi xác thực hợp lệ, custom code cần tạo SecurityContext, gắn Authentication và **lưu vào SecurityContextRepository** với request/response theo phiên bản Security 6:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Đây là **snippet thuộc một login mechanism có sẵn các biến/bean verified, securityContextRepository, request, response**, không phải chương trình độc lập. Không dán bốn dòng vào bất kỳ Controller nào rồi xem đó là đăng nhập hoàn chỉnh.

Custom login còn phải xét session fixation strategy, CSRF, cookie/session settings, success/failure handlers, logout, rate limiting, MFA, secret storage và quyền sau login. Vì vậy khi không có nhu cầu đặc biệt, ưu tiên **formLogin/httpBasic/oauth2Login/Resource Server** đã được framework hỗ trợ.

### 15.1. Tại sao Spring Security 6 nhấn mạnh explicit save?

SecurityContextHolderFilter nạp context từ repository nhưng không có nhiệm vụ tự lưu mọi sửa đổi của custom code sau khi request kết thúc. Nếu bạn tự gắn Authentication vào holder và muốn giữ cho request sau, cần saveContext đúng thời điểm và đúng repository.

Với filter đăng nhập tích hợp, Spring Security đã có lifecycle của cơ chế đó. Đừng tạo thêm filter tùy ý rồi dựa vào hành vi tự lưu ngầm của phiên bản cũ.

### 15.2. Authentication thành công nhưng request sau lại anonymous

Kiểm tra:

- Bạn chỉ gọi manager.authenticate() mà quên đặt kết quả vào SecurityContext?
- Bạn đã đặt context nhưng chưa saveContext dù muốn session persistence?
- SessionCreationPolicy có đang STATELESS?
- Cookie/session ID có được client gửi lại không?
- Session đã hết hạn hoặc bị rotate/logout chưa?
- Request sau có đi vào một SecurityFilterChain khác không?
- Bạn có đang cố dùng context từ thread khác mà không có context propagation?

Mỗi nguyên nhân nằm ở một giai đoạn khác nhau; không thể sửa tất cả bằng cách thay PasswordEncoder.

## 16. Các lỗi hiểu nhầm và cách debug

| Hiện tượng | Giai đoạn nghi vấn | Cách kiểm tra |
| --- | --- | --- |
| Header Authorization có nhưng filter không nhận | Tiếp nhận/trích xuất | Đúng SecurityFilterChain và cơ chế Basic/Bearer chưa? |
| supports() trả false | Provider selection | Loại Authentication filter tạo có khớp provider? |
| UserDetailsService tìm được user nhưng vẫn 401 | Xác minh | PasswordEncoder, account status, provider |
| Xác thực đúng nhưng Controller không thấy user | SecurityContext | Filter có đặt Authentication, request đi đúng chain? |
| Request sau mất login | Persistence | Repository, explicit save, session/cookie, policy |
| User đúng password nhưng /admin trả 403 | Authorization | ROLE_ADMIN, policy, owner/tenant |
| POST trả 403 dù đã login | CSRF/Authorization | Kiểm tra CSRF token và rights; không disable tùy tiện |
| URL public gửi credential sai nhận 401 | Authentication filter | Filter có thử xác thực credential được cung cấp trước permitAll? |
| Người dùng có role USER nhưng đọc dữ liệu user khác | Business authorization | Phải kiểm tra ownerId/resource |
| Controller trả nguyên Authentication ra JSON | Output boundary | Chỉ trả DTO allowlist, tránh credentials/details |
| UserDetails bị mất password sau auth, cache sai | Credential erasure/cache | Kiểm tra shared references và eraseCredentials |
| WebFlux code dùng HttpSecurity | Sai stack | Cần ServerHttpSecurity và reactive context |
| HTTP 401 biến thành 302 | Entry point | Có form login/redirect thay cho Basic không? |
| Async task không thấy context | Context propagation | Dùng wrapper/delegating context hỗ trợ phù hợp |

### 16.1. Quy trình debug theo thứ tự hợp lý

1. Ghi nhận request method, URL, Accept, Authorization scheme (không ghi secret), cookie/session ID có hay không.
2. Xác định FilterChainProxy chọn SecurityFilterChain nào.
3. Xác định authentication filter cụ thể có xử lý request không.
4. Xem loại Authentication được tạo trước xác thực.
5. Xem AuthenticationManager/AuthenticationProvider nào được dùng và exception nào được phát.
6. Kiểm tra UserDetailsService/PasswordEncoder hoặc token decoder.
7. Khi thành công, kiểm tra principal và authorities trong SecurityContext (chỉ log trường an toàn).
8. Phân biệt AuthorizationFilter từ chối, CSRF từ chối hay Controller không có mapping.
9. Nếu lỗi chỉ xuất hiện ở request sau, kiểm tra repository, session policy và cookie.
10. Viết integration test cho happy path lẫn các nhánh không có credentials, sai credentials, thiếu role và session hết hạn.

Có thể bật Spring Security DEBUG logging trong môi trường phát triển có kiểm soát, nhưng **không ghi raw password, token, Authorization header, cookie hoặc PII** vào log để debug.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Filter HTTP Basic hay DaoAuthenticationProvider là nơi đọc Authorization header?  
**Đáp:** BasicAuthenticationFilter đọc header; DaoAuthenticationProvider kiểm tra thông tin qua nguồn user và password encoder.

**Câu 2.** UsernamePasswordAuthenticationToken.unauthenticated nghĩa là login thành công chưa?  
**Đáp:** Chưa. Nó chỉ chứa dữ liệu client khai; manager/provider phải kiểm tra.

**Câu 3.** UserDetailsService tìm được user chứng minh password đúng chứ?  
**Đáp:** Không. DaoAuthenticationProvider dùng PasswordEncoder.matches và trạng thái tài khoản.

**Câu 4.** ProviderManager có trả HTTP 401 trực tiếp không?  
**Đáp:** Không. Nó trả Authentication hoặc ném AuthenticationException; filter/entry point chuyển sang HTTP response.

**Câu 5.** Sau manager.authenticate() thành công, controller tự gọi lệnh đó có tạo session login cho request sau không?  
**Đáp:** Không. Cần SecurityContext và cơ chế lưu context hoặc token/session tương ứng.

**Câu 6.** Đúng password nhưng không có ROLE_ADMIN gọi /admin sẽ ra sao?  
**Đáp:** Authentication thành công, Authorization từ chối, thường HTTP 403 trong HTTP Basic demo.

**Câu 7.** Tại sao một endpoint permitAll vẫn có thể trả 401 khi client gửi header Basic sai?  
**Đáp:** Authentication filter có thể thử credential được cung cấp và báo lỗi trước bước authorization permitAll.

**Câu 8.** HttpSecurity SessionCreationPolicy.STATELESS có nghĩa không bao giờ có Authentication trong request?  
**Đáp:** Không. Request vẫn có Authentication sau khi token/credentials được xác minh; chỉ chính sách duy trì session khác.

**Câu 9.** Vì sao AnonymousAuthenticationToken có isAuthenticated=true mà rule authenticated() vẫn không cho anonymous qua?  
**Đáp:** Authorization dùng cơ chế trust resolver để phân biệt anonymous với principal người dùng thật.

**Câu 10.** SecurityContextHolder trong Servlet có tự lan sang mọi thread async không?  
**Đáp:** Không mặc nhiên. Phải dùng cơ chế propagation của framework phù hợp.

**Câu 11.** HTTP 401 và 403 khác gì trong ví dụ?  
**Đáp:** 401 thường là thiếu/sai credentials; 403 là đã xác thực nhưng thiếu quyền hoặc bị policy khác từ chối.

**Câu 12.** Tại sao chỉ kiểm tra ROLE_USER không đủ cho GET /orders/42?  
**Đáp:** Cần xác minh user có quyền đối với order cụ thể, ownerId/tenantId và trạng thái nghiệp vụ.

## 18. Tài liệu Spring Security chính thức

- Servlet Authentication Architecture (ProviderManager, AuthenticationProvider, SecurityContextHolder): https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Servlet Basic Authentication: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/basic.html
- Servlet Form Login: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/form.html
- Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/session-management.html
- Servlet Architecture và FilterChainProxy: https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html
- Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/authorize-http-requests.html
- DaoAuthenticationProvider API Spring Security 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Authentication interface API Spring Security 6.3.4: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/Authentication.html
- Spring Boot 3.3 Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
