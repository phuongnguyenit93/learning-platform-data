# AbstractAuthenticationProcessingFilter và các bước xử lý cốt lõi

## 1. Vai trò của bộ lọc xử lý đăng nhập trong Spring Security Servlet

Trong một ứng dụng web dùng Spring Security, request không trở thành “đã đăng nhập” chỉ vì nó có các trường `username` và `password`. Framework phải nhận ra **request nào là yêu cầu xác thực**, chuyển dữ liệu chưa được tin cậy thành một `Authentication` *chưa xác thực*, nhờ `AuthenticationManager` kiểm chứng, xử lý kết quả và quyết định trạng thái `SecurityContext` cùng phản hồi HTTP.

**`AbstractAuthenticationProcessingFilter`** là lớp nền trừu tượng cho nhóm **Servlet filter xử lý yêu cầu authentication tương tác**, đặc biệt các cơ chế có một endpoint đăng nhập cụ thể. Ví dụ điển hình là `UsernamePasswordAuthenticationFilter`, cũng như một số filter đăng nhập bằng OAuth2/SAML/WebAuthn có vòng đời xử lý phù hợp. Lớp này nằm trong gói:

```java
org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter
```

Nó kế thừa `GenericFilterBean` và triển khai Servlet `Filter`; **không** phải `AuthenticationProvider`, `UserDetailsService`, controller hay cơ chế băm mật khẩu.

Cốt lõi có thể ghi nhớ bằng bốn câu hỏi:

1. **Đây có phải request đăng nhập cần xử lý không?** — `requiresAuthentication(...)` và `RequestMatcher`.
2. **Có thể xác thực request này chưa?** — `attemptAuthentication(...)`, được subclass định nghĩa; có thể trả kết quả, ném lỗi hoặc trả `null`.
3. **Sau khi xác thực thành công, cần làm gì?** — session strategy, tạo/lưu `SecurityContext`, remember-me, sự kiện thành công và success handler.
4. **Khi thất bại, cần làm gì?** — xóa context hiện hành, xử lý remember-me, failure handler và phản hồi HTTP phù hợp.

**Tư duy đúng:** filter này **điều phối lifecycle của request xác thực**, còn bằng chứng password/OTP/token có hợp lệ hay không được kiểm tra bởi `AuthenticationManager` và provider chuyên trách. Một custom filter tự đặt `authenticated=true` từ dữ liệu client mà không kiểm chứng credentials là **lỗ hổng**, không phải một cách tối ưu.

## 2. Những thành phần phối hợp và phạm vi trách nhiệm

| Thành phần | Được gọi ở đâu? | Công việc chính |
| --- | --- | --- |
| `RequestMatcher` | Trước xác thực | Chọn method/path/request nào phải đi qua filter đăng nhập. |
| `AbstractAuthenticationProcessingFilter` | Trong `SecurityFilterChain` | Điều phối matching → attempt → session → success/failure. |
| `attemptAuthentication` của subclass | Khi matcher khớp | Đọc request, tạo `Authentication` đầu vào, gửi tới manager hoặc bắt đầu cơ chế nhiều bước. |
| `AuthenticationManager` | Trong attempt | Kiểm chứng `Authentication` qua provider phù hợp. |
| `AuthenticationProvider` | Do manager chọn | Kiểm tra password/hash, status user hoặc credential chuyên biệt. |
| `SessionAuthenticationStrategy` | Sau attempt thành công, trước success handler | Xử lý đăng nhập mới, ví dụ chống session fixation/giới hạn session khi được cấu hình. |
| `SecurityContextHolder` | Trong success/failure | Giữ `Authentication` hiện hành ở ngữ cảnh xử lý. |
| `SecurityContextRepository` | Khi thành công nếu được cấu hình | Lưu context vào request attribute/HttpSession hoặc cơ chế khác để khôi phục theo scope. |
| `RememberMeServices` | Sau thành công/thất bại | Quản lý lựa chọn remember-me nếu ứng dụng bật. |
| `AuthenticationSuccessHandler` | Cuối nhánh thành công | Redirect hoặc viết HTTP response thành công. |
| `AuthenticationFailureHandler` | Cuối nhánh thất bại | Redirect lỗi hoặc viết HTTP response lỗi. |
| `AuthenticationEntryPoint` | Thường trong `ExceptionTranslationFilter` | Yêu cầu người dùng **bắt đầu xác thực** khi truy cập tài nguyên bảo vệ chưa có identity hợp lệ. |

**Điểm phân biệt quan trọng:** `AuthenticationEntryPoint` dùng để mời/đòi xác thực khi cần; `AuthenticationFailureHandler` xử lý **một yêu cầu đăng nhập đã được thử và thất bại**. Hai vai trò khác nhau dù đều có thể tạo HTTP 401 hoặc redirect.

### Liên hệ với `UsernamePasswordAuthenticationFilter`

`UsernamePasswordAuthenticationFilter` là subclass cụ thể đọc form parameters `username` và `password`, tạo `UsernamePasswordAuthenticationToken` rồi gửi manager. Mặc định nó thường xử lý **POST `/login`**; tên tham số có thể cấu hình.

```text
POST /login
Content-Type: application/x-www-form-urlencoded

username=lan&password=...
```

Đây là ví dụ giao thức, không phải một request mẫu để đưa mật khẩu thật vào log. Filter gốc **không tự biết** JSON body, tên trường `email`, OTP hay signature: muốn cơ chế tùy biến, cần chọn converter/subclass/provider hoặc authentication filter hiện có phù hợp.

## 3. Sơ đồ điều khiển chính của `doFilter`

Quy trình khái niệm theo Spring Security **6.5.11**:

```text
Servlet FilterChain
       |
       v
AbstractAuthenticationProcessingFilter.doFilter(req, res, chain)
       |
       +--> requiresAuthentication(req, res)?
       |           |
       |           +-- false --> chain.doFilter(...) --> không thử login
       |
       v  true
attemptAuthentication(req, res)
       |
       +-- return null --------> quy trình chưa hoàn tất;
       |                         filter RETURN ngay, không success/failure
       |
       +-- throw AuthenticationException
       |           |
       |           v
       |     unsuccessfulAuthentication(...)
       |       clear SecurityContextHolder
       |       rememberMeServices.loginFail(...)
       |       failureHandler.onAuthenticationFailure(...)
       |           |
       |          RETURN
       |
       +-- return Authentication
                   |
                   v
       sessionAuthenticationStrategy.onAuthentication(...)
                   |
                   v
       (nếu continueChainBeforeSuccessfulAuthentication = true,
        chain.doFilter(...) chạy TẠI ĐÂY)
                   |
                   v
       successfulAuthentication(...)
         tạo SecurityContext / đặt Authentication
         save qua SecurityContextRepository đã cấu hình
         rememberMeServices.loginSuccess(...)
         publish InteractiveAuthenticationSuccessEvent nếu có publisher
         successHandler.onAuthenticationSuccess(...)
                   |
                 RETURN
```

**Lưu ý:** sơ đồ là mô tả đường đi cơ bản, không áp đặt success handler phải redirect hay mọi hệ thống phải tạo session. Các ngoại lệ phát sinh ở session strategy và các thành phần callback có ảnh hưởng riêng, được trình bày bên dưới.

### Vì sao request không khớp vẫn đi tiếp?

Khi `requiresAuthentication(...) == false`, bộ lọc gọi `chain.doFilter(request,response)`. Điều này là bình thường: một custom login filter chỉ nên nhận request thuộc **login endpoint**, còn các endpoint như `/orders`, `/me` hay `/css/style.css` đi qua filter khác và phần ứng dụng theo cấu hình.

Đừng giải thích `requiresAuthentication=false` là “user đã được xác thực”. Nó chỉ nói **request này không phải nỗ lực đăng nhập mà filter hiện tại chịu trách nhiệm**.

## 4. Chọn đúng request bằng `RequestMatcher`

`AbstractAuthenticationProcessingFilter` có `setRequiresAuthenticationRequestMatcher(RequestMatcher)` và các constructor nhận matcher. Matcher có thể xét đường dẫn, HTTP method hoặc điều kiện có kiểm soát khác.

Một lựa chọn đơn giản trong demo Spring Security 6.5:

```java
RequestMatcher loginPost =
        new AntPathRequestMatcher("/login-demo", "POST");
```

API `AntPathRequestMatcher` trong nhánh Spring Security 6.5 đã được đánh dấu deprecated để hướng sang matcher mới; demo dùng nó vì dễ quan sát với mock Servlet request. Trong sản phẩm mới hãy chọn RequestMatcher hiện hành được Spring Security khuyên dùng và test đường dẫn đúng theo Servlet context/application router.

**Chỉ khớp URL mà bỏ HTTP method là một lỗi dễ gặp:** nếu filter nhận cả `GET /login`, credentials có thể bị đưa qua query string hoặc endpoint bị kích hoạt ngoài ý muốn. Với form login, Spring Security `UsernamePasswordAuthenticationFilter` mặc định yêu cầu POST; ứng dụng nên giữ giới hạn này và có biện pháp CSRF tương ứng.

### Path trong Servlet không luôn bằng nguyên URL được gửi

`getRequestURI()` có thể bao gồm context path; `getServletPath()` và `getPathInfo()` có các ngữ nghĩa khác. Request matcher do framework cung cấp xử lý theo các trường phù hợp, nhưng **đừng tự ghép request URI và so bằng `equals`** nếu có context path, path parameter `;jsessionid`, proxy rewrite hay trailing slash.

Mẫu kiểm thử cần bao phủ:

| Request | Matcher `/login-demo` + POST | Hành vi |
| --- | --- | --- |
| `POST /login-demo` | Khớp | Thử xác thực. |
| `GET /login-demo` | Không khớp | Tiếp tục filter chain. |
| `POST /login-demo/extra` | Không khớp theo matcher chính xác | Tiếp tục chain. |
| `POST /private` | Không khớp | Tiếp tục chain. |
| Một login path sau reverse proxy/context path | Phụ thuộc Servlet path đã được giải quyết | Test integration thật, không đoán. |

Một filter matcher sai có thể làm **bỏ qua login**, hoặc tệ hơn là chặn nhầm request không phải login; điều đó thường bị nhầm với lỗi của `AuthenticationManager`.

## 5. `attemptAuthentication`: nơi chuyển request thành Authentication đầu vào

Đây là **phương thức trừu tượng trọng tâm** mà subclass phải triển khai:

```java
public abstract Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response)
        throws AuthenticationException, IOException, ServletException;
```

Chữ ký ở trên minh họa API hiện hành; imports thuộc `jakarta.servlet` và Spring Security. Trong lớp kế thừa, thường làm:

1. Lấy dữ liệu authentication theo format cho phép (form fields, header chuyên biệt, token callback...).
2. Validate những điều kiện đầu vào cần thiết, giới hạn kích thước và xử lý missing fields.
3. Tạo `Authentication` **chưa xác thực**. Ví dụ `UsernamePasswordAuthenticationToken.unauthenticated(username,password)`.
4. Có thể đặt `details` từ một `AuthenticationDetailsSource` phù hợp nếu cần metadata của request.
5. Gọi `getAuthenticationManager().authenticate(candidate)` và trả kết quả được xác thực nếu thành công.

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) {

    String username = request.getParameter("username");
    String password = request.getParameter("password");

    UsernamePasswordAuthenticationToken candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password);

    return getAuthenticationManager().authenticate(candidate);
}
```

Đây là **trích đoạn**, chưa gồm class/filter/exception handling/config đầy đủ. Trong sản phẩm, không nên để `null`/chuỗi quá dài/format sai đi xuyên qua không kiểm soát; cách validate cần bảo toàn chính sách password và không tiết lộ thông tin người dùng. Đừng tự lower-case/trim password.

### Ba kết quả chính xác của `attemptAuthentication`

| Kết quả | Ý nghĩa | Bộ lọc sẽ làm gì? |
| --- | --- | --- |
| Trả một `Authentication` đã được manager kiểm chứng | Thử xác thực hoàn tất thành công | Chạy session strategy và success path. |
| Ném `AuthenticationException` | Thử xác thực thất bại | Chạy `unsuccessfulAuthentication` và failure handler. |
| Trả `null` | Xử lý authentication **chưa hoàn tất** | Trả về ngay; subclass đã phải thực hiện công việc cần thiết, ví dụ redirect/chờ request tiếp theo. |

**Trả `null` không có nghĩa thất bại và không có nghĩa thành công.** Nó chỉ là tín hiệu dừng nhánh hiện tại vì còn giai đoạn sau. Nếu một subclass trả `null` mà không gửi phản hồi có ý nghĩa, client có thể nhận HTTP status mặc định khó hiểu; ví dụ demo sẽ đặt rõ `202` để thấy nhánh này.

**Không dùng `return null` để nuốt password sai.** Khi credential không hợp lệ và phải từ chối login, ném một `AuthenticationException` thích hợp để framework gọi failure handler.

### Vì sao không trả token tự đánh dấu authenticated?

`UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` dành cho code **đã có căn cứ tin cậy** để tạo authentication. Nếu filter lấy `username`/`roles` từ JSON body rồi gọi factory này, attacker có thể tự nhận quyền `ROLE_ADMIN` mà không cần password. Cách đúng là token **unauthenticated** được đưa qua `AuthenticationManager` hoặc cơ chế provider chứng thực tương đương.

### Xử lý nhiều bước có giới hạn

Cơ chế OAuth2 callback, SAML hoặc MFA có vòng đời riêng. Đối với một lớp kế thừa custom, `return null` có thể biểu diễn “đã redirect sang bước kế” hoặc “đang chờ chứng cứ”, nhưng **không tự triển khai MFA an toàn**. Cần có transaction/state/nonce/expiry, ràng buộc người dùng–thiết bị và chống replay, đồng thời sử dụng cơ chế framework hiện có khi phù hợp.

## 6. AuthenticationManager và AuthenticationProvider: xác thực thật nằm ở đâu?

`AbstractAuthenticationProcessingFilter` không tự tra database hoặc kiểm tra password hash. Nó cần một `AuthenticationManager`:

```text
Filter đọc request
   |
   +--> UsernamePasswordAuthenticationToken(authenticated=false)
   |
   v
AuthenticationManager (thường ProviderManager)
   |
   +--> AuthenticationProvider.supports(token type)?
   |
   +--> UserDetailsService.loadUserByUsername(...)
   |
   +--> PasswordEncoder.matches(raw, storedHash)
   |
   +--> account status / credential expiry / custom checks
   |
   v
Authentication kết quả đã được kiểm chứng
   principal + authorities + authenticated=true
```

Không phải mọi provider đều là `DaoAuthenticationProvider`: với token hoặc giao thức khác, manager chọn provider tương ứng. Nếu manager không có provider hỗ trợ kiểu `Authentication`, việc đăng nhập có thể thất bại bằng `ProviderNotFoundException`, không phải vì matcher URL.

**Quyền truy cập** sau xác thực đến từ `GrantedAuthority` được hệ thống tin cậy xác lập, không nên được chép nguyên từ một trường `role=ADMIN` mà client gửi.

Một lỗi vận hành đáng chú ý là giữ tham chiếu `UserDetails`/JPA entity còn lazy trong principal: authentication có thể hoàn tất nhưng code đọc quyền sau transaction ném `LazyInitializationException`. Adapter kho tài khoản nên ánh xạ thành `UserDetails` độc lập với ORM session ngay trong giao dịch đọc.

## 7. SessionAuthenticationStrategy: nằm giữa attempt và success

Khi `attemptAuthentication` trả về một `Authentication`, bộ lọc gọi `SessionAuthenticationStrategy.onAuthentication(authentication,request,response)` **trước `successfulAuthentication`**.

Mục đích của strategy có thể gồm:

- Chống **session fixation**, ví dụ đổi session ID khi login.
- Giới hạn số phiên đồng thời theo policy.
- Đăng ký phiên vào session registry.
- Xử lý một số cơ chế session khác liên quan đến đăng nhập mới.

**Quan trọng:** lớp nền có một chiến lược mặc định không thao tác nếu bạn không cấu hình. Không vì thấy method được gọi mà kết luận mọi **filter custom** đã được bảo vệ session fixation. Khi dùng `formLogin(...)`/security DSL chuẩn, framework có cơ chế wiring session management phù hợp; khi tự new filter thủ công, bạn phải cung cấp strategy đúng cho security policy.

### Khi SessionAuthenticationStrategy thất bại

Một strategy có thể ném `SessionAuthenticationException` (subclass của `AuthenticationException`), ví dụ khi vi phạm giới hạn phiên. Trong đường xử lý Spring Security 6.5, lỗi đó được đưa vào failure path. **Đã kiểm chứng password đúng vẫn chưa có nghĩa sẽ có login thành công** nếu policy session không cho phép.

Không đặt thao tác không idempotent trong session strategy tùy tiện hoặc bắt exception rồi tiếp tục như thành công. Việc chuyển/đổi session ID cũng cần phối hợp với `SecurityContextRepository`, response cookie và cơ chế logout.

## 8. `successfulAuthentication`: công việc khi một yêu cầu đăng nhập thành công

Khi manager và session strategy đã hoàn tất, lớp nền thực hiện nhánh thành công. Với Spring Security 6.5.11, hành vi chính gồm:

1. Tạo một `SecurityContext` cho request hiện hành, đặt `Authentication` vừa được xác minh.
2. Đặt context vào `SecurityContextHolderStrategy` tương ứng, để code trong ngữ cảnh hiện tại truy cập.
3. **Lưu** context qua `SecurityContextRepository` **đã được cấu hình** cho filter.
4. Thông báo `RememberMeServices.loginSuccess(...)`.
5. Phát `InteractiveAuthenticationSuccessEvent` khi có `ApplicationEventPublisher`.
6. Gọi `AuthenticationSuccessHandler.onAuthenticationSuccess(...)` để quyết định redirect/status/body.

**Thứ tự cụ thể** quan trọng nếu success handler gọi `sendRedirect(...)` hoặc commit body: lưu session/context đúng thời điểm trước khi response commit giúp request kế tiếp có thể khôi phục identity.

### Context hiện hành khác với persistence

`SecurityContextHolder.getContext().setAuthentication(...)` (hoặc set một context mới) chỉ làm authentication hiện diện trong phạm vi xử lý hiện tại. Nó **không tự tạo một phiên đăng nhập liên tục giữa các request** nếu context không được lưu vào repository có persistence phù hợp.

`AbstractAuthenticationProcessingFilter.setSecurityContextRepository(...)` cho phép đặt repository. Tài liệu API 6.5.11 nêu rõ **mặc định của riêng filter nền không phải tự lưu vào kho bền vững** nếu chưa có cấu hình. Khi dùng filter được `formLogin`/DSL tạo ra, cấu hình có thể bổ sung repository cho bạn. Khi **khởi tạo một custom filter bằng `new`**, nên đặt repository rõ ràng theo kiến trúc.

Ví dụ:

```java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());

filter.setSecurityContextRepository(repository);
```

Đoạn này là **trích đoạn cấu hình**, cần imports và filter object. Delegating repository lưu vào request attribute để hỗ trợ dispatch nội bộ và vào HttpSession để giữ login giữa các request, nếu policy cho phép.

**Nếu bạn chọn `RequestAttributeSecurityContextRepository` duy nhất**, request đăng nhập có context nhưng request HTTP **tiếp theo** không tự có identity đó. Ví dụ console ở mục 12 cố tình dùng request-only repository để kiểm tra hành vi mà **không tạo HTTP session**.

### Remember-me: chức năng riêng

`RememberMeServices.loginSuccess` có thể tạo/xử lý remember-me token hoặc cookie nếu được cấu hình và điều kiện policy thỏa mãn. Nó **không đồng nghĩa** với session cookie và không mặc định tạo cookie remember-me trên mọi login. Một cấu hình không có remember-me thường dùng no-op.

Không bật remember-me bằng cách tự nhét tên user vào cookie. Các token phải có cơ chế ký/chuỗi random, ràng buộc, expiry, xử lý thu hồi và bảo vệ khi bị đánh cắp.

### InteractiveAuthenticationSuccessEvent

Event này đại diện một lần đăng nhập tương tác thành công. Nó không phải bằng chứng rằng **mọi request đã xác thực** đều phát event mới; một request đến với session hiện hữu không bắt buộc đi qua filter login.

Audit thành công có thể dùng event/handler phù hợp, nhưng đừng chỉ dựa vào event để cấp quyền nghiệp vụ hoặc cập nhật số dư. Event delivery và transaction của nghiệp vụ không được tự động xem là nguyên tử.

### Success handler mặc định có thể redirect

`SavedRequestAwareAuthenticationSuccessHandler` là lựa chọn mặc định của filter nền. Nó có thể ưu tiên URL người dùng đang cố truy cập trước khi login (saved request), hoặc dùng URL đích được cấu hình. Vì vậy nhiều login form thành công trả **302 redirect**, chứ không phải JSON 200.

Muốn endpoint REST trả `204` hoặc JSON có cấu trúc, bạn có thể cấu hình một `AuthenticationSuccessHandler` riêng. Nó **xử lý response**, không nên tự quyết định credential đã hợp lệ trước khi provider kiểm chứng.

## 9. `unsuccessfulAuthentication`: thất bại là một nhánh có kiểm soát

Khi `attemptAuthentication` ném `AuthenticationException`, hoặc các bước authentication/session liên quan thất bại theo hợp đồng, filter gọi nhánh thất bại:

1. **Clear `SecurityContextHolder`** cho ngữ cảnh xử lý hiện tại.
2. Gọi `RememberMeServices.loginFail(...)` để hủy/điều chỉnh remember-me theo policy.
3. Gọi `AuthenticationFailureHandler.onAuthenticationFailure(request,response,exception)`.
4. Trả lại quyền điều khiển theo lifecycle filter; không cấp `Authentication` đã xác thực từ lần thử thất bại.

Ở một số API/configuration cũ, thông tin lỗi được đưa vào session để hiển thị lại trên form. Chi tiết **phụ thuộc failure handler và chính sách cho phép tạo session**; không nên nghĩ mọi thất bại đều ghi một thuộc tính session hoặc tạo session mới.

### Mặc định trả 401 hay redirect?

Với `SimpleUrlAuthenticationFailureHandler`:

- Không cấu hình failure URL: có thể gửi HTTP **401**.
- Nếu cấu hình failure URL: có thể redirect tới trang đăng nhập kèm thông báo lỗi chung.

Cấu hình `formLogin` chuẩn có thể chọn URL xử lý riêng. Một lỗi Java là `BadCredentialsException` không tự suy ra status HTTP 401/403 trong mọi ứng dụng; **failure handler** quyết định cách trình bày response.

**Không lộ sự tồn tại của tài khoản** chỉ vì muốn hiển thị “username sai” khác “password sai”; các API công khai thường nên dùng thông báo xác thực thất bại nhất quán. Log nội bộ có thể phân loại an toàn theo policy nhưng không ghi mật khẩu gốc, token hay toàn bộ `Authentication`.

### Thất bại không có nghĩa ứng dụng đã logout toàn bộ sessions

`SecurityContextHolder.clearContext()` chỉ xóa context tại luồng/chiến lược hiện hành. Một HTTP session khác của cùng người dùng có thể vẫn hợp lệ. Nếu yêu cầu khóa tài khoản hoặc nghi ngờ tấn công credential stuffing, cần cơ chế session invalidation/token revocation riêng.

Nếu user **đã có session đăng nhập cũ** nhưng thử login lại sai trên cùng browser, cách xử lý session/context tùy policy và filter configuration; đừng tự suy luận chỉ nhìn tên exception.

## 10. Ba kết quả của attempt và FilterChain: bảng nhìn nhanh

| Trường hợp | Gọi manager? | Session strategy? | Context mới được lưu? | Handler? | `chain.doFilter` mặc định? |
| --- | --- | --- | --- | --- | --- |
| Matcher không khớp | Không | Không | Không do filter này | Không | **Có** |
| Trả `Authentication` | Có, nếu subclass gọi manager | Có | Có nếu repository cấu hình lưu | Success | **Không** |
| Ném `AuthenticationException` | Thường có, nhưng có thể validate fail trước | Không, trừ lỗi ở chính strategy | Không từ success path | Failure | **Không** |
| Trả `null` (đang chờ) | Phụ thuộc subclass | Không | Không từ success path | Không success/failure | **Không** |
| Session strategy ném `SessionAuthenticationException` | Đã có kết quả manager | Đang chạy và lỗi | Không từ success path | Failure | **Không** |

**Đây là behavior thông thường với `continueChainBeforeSuccessfulAuthentication=false`.** Nếu bật cờ đặc biệt này, đường thành công sẽ chạy chain **trước** `successfulAuthentication`. Việc đó có thể khiến downstream xử lý trước khi holder chứa kết quả đăng nhập mới và trước success handler, không phải cấu hình phổ biến cho login endpoint.

### `setContinueChainBeforeSuccessfulAuthentication(true)` là gì?

Option này phục vụ một số môi trường tích hợp đặc thù. Nếu bật:

```text
attemptAuthentication -> session strategy -> chain.doFilter
                                         -> successfulAuthentication
                                         -> successHandler
```

Downstream trong chain **có thể chưa thấy authentication mới** tại thời điểm nó chạy, rồi success handler lại tiếp tục điều khiển response; nếu response đã commit, redirect/save có thể gặp rắc rối. Không bật chỉ để “request thành công phải chạy tiếp tới controller”. Với form login, việc **filter tiêu thụ request đăng nhập** và chuyển tới success handler là thiết kế bình thường.

Nếu bạn cần một API nhận JWT mỗi request rồi cho controller xử lý, thường dùng mô hình filter authentication phù hợp, ví dụ `AuthenticationFilter` hoặc filter token theo kiến trúc resource server, chứ không đơn giản bật cờ chain này.

## 11. Một ví dụ config Spring Boot Servlet và nơi custom filter được gắn

### 11.1. Dùng form login chuẩn khi phù hợp

Nếu yêu cầu chỉ là username/password form, **ưu tiên `formLogin(...)`** thay vì tự viết subclass mới:

```java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .usernameParameter("username")
                .passwordParameter("password")
                .defaultSuccessUrl("/home", false)
                .failureUrl("/login?error"))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **trích đoạn cấu hình**, chưa có login page/controller, `UserDetailsService`, `PasswordEncoder`, database hoặc CSRF token form. `loginProcessingUrl` là endpoint **do filter xử lý**, còn `loginPage` là trang/form người dùng nhìn thấy. Không nên tạo controller `@PostMapping("/login")` trùng một endpoint mà `UsernamePasswordAuthenticationFilter` đã tiêu thụ nếu không có mục tiêu và thứ tự rõ ràng.

Form login dựa trên session thường cần bảo vệ **CSRF**: HTML form POST phải gửi token đúng, và session cookie cần `Secure`/`HttpOnly`/`SameSite` theo kiến trúc. Đừng bỏ `csrf().disable()` toàn cục chỉ vì một form demo không submit được.

### 11.2. Khi nào tự viết subclass?

Có thể cần custom `AbstractAuthenticationProcessingFilter` nếu cơ chế authentication có **endpoint/format tương tác riêng** và không được một filter hiện có hỗ trợ thuận tiện, ví dụ một login protocol nhiều bước, payload/credential đặc thù đã được thiết kế và kiểm toán.

Trước khi quyết định tạo subclass, cân nhắc:

- `UsernamePasswordAuthenticationFilter` với tên parameter/custom `AuthenticationConverter` nếu chỉ thay đổi dữ liệu form nhỏ.
- `AuthenticationFilter` cùng `AuthenticationConverter` và handlers cho cơ chế request-to-authentication chung, ít phụ thuộc subclass.
- Các filter chuyên dụng OAuth2/OIDC/SAML/WebAuthn/token của framework khi phù hợp giao thức; tránh tự viết verifier mật mã hoặc callback.
- Việc authentication có thực sự cần state/session hay phải stateless theo mỗi request.

**Không nên sao chép code của filter có sẵn chỉ để đổi URL**, vì `formLogin().loginProcessingUrl(...)` đã có khả năng này.

### 11.3. Đăng ký filter đúng một lần

Một custom filter phải nằm đúng **`SecurityFilterChain`**, đúng thứ tự so với các filter khác, dùng manager/repository/handlers phù hợp. Nếu bạn vừa đánh dấu filter là `@Component` (Servlet container auto-register) **vừa** gọi `http.addFilterBefore/After`, nó có thể bị chạy **hai lần**, bên trong và bên ngoài Spring Security chain.

Với Spring Boot, cần chú ý cách đăng ký `FilterRegistrationBean`/`@Bean` và Spring Security DSL. **Đừng** vô tình làm một filter đã có manager/handler bị apply ngoài security context, bỏ qua CSRF hoặc session strategy.

Nếu có nhiều `SecurityFilterChain` cho `/api/**` và `/**`, phải xác định filter thuộc chain nào và URL nào là login endpoint. Filter nằm trong một chain khác có thể không được gọi dù URL matcher bên trong nó khớp.

## 12. Ví dụ Java 17 chạy được: bốn nhánh của filter thật

Chương trình console này dùng **Spring Security Web 6.5.11 + Spring Framework Mock Servlet** để chạy `AbstractAuthenticationProcessingFilter` thật mà không cần khởi động web server. Nó xác minh:

1. `GET /login-demo` không khớp matcher POST nên chuyển tiếp chain.
2. `POST /login-demo` với password đúng gọi manager, session strategy, success handler và lưu `SecurityContext` vào **request attribute**.
3. `POST /login-demo` với password sai gọi manager, failure handler, không lưu authentication mới.
4. `POST /login-demo` với username đặc biệt `pending` mô phỏng `attemptAuthentication` trả `null`, tự trả `202`; không gọi manager/handler/session strategy.
5. Một `POST` tới URL khác không khớp matcher và đi qua chain.

**Giới hạn bảo mật:** manager demo chỉ so hai chuỗi hard-coded để minh họa **control flow**, không phải password storage production. Đừng tái sử dụng cách kiểm tra này cho người dùng thật. Trong production, manager phải dùng provider và `PasswordEncoder` phù hợp, tài khoản lấy từ user store tin cậy và đầy đủ status checks.

### 12.1. Cấu trúc dự án

```text
authentication-filter-flow-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    └── FilterFlowDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authentication-filter-flow-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.FilterFlowDemo'
}
```

Ở một Spring Boot project thật, nên để BOM/dependency management của phiên bản Boot được hỗ trợ quản lý các thư viện Spring/Spring Security tương thích. Các version trên là cấu hình xác định **dành cho demo console** để giải thích API Spring Security 6.5.11.

### 12.2. File `src/main/java/demo/FilterFlowDemo.java`

```java
package demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class FilterFlowDemo {

    static final class DemoFilter extends AbstractAuthenticationProcessingFilter {

        DemoFilter(AuthenticationManager manager) {
            // AntPathRequestMatcher chỉ để minh họa API 6.5;
            // với dự án mới dùng matcher hiện hành được khuyên dùng.
            super(new AntPathRequestMatcher("/login-demo", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response)
                throws AuthenticationException, IOException, ServletException {

            String username = request.getParameter("username");

            // Giả lập một flow nhiều bước đã tự gửi response.
            // Đây KHÔNG phải một implementation MFA.
            if ("pending".equals(username)) {
                response.setStatus(202);
                return null;
            }

            String password = request.getParameter("password");
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);

            return getAuthenticationManager().authenticate(input);
        }
    }

    private static void runCase(
            String label,
            DemoFilter filter,
            RequestAttributeSecurityContextRepository repository,
            AtomicInteger managerCalls,
            AtomicInteger sessionCalls,
            String method,
            String path,
            String username,
            String password) throws IOException, ServletException {

        SecurityContextHolder.clearContext();

        MockHttpServletRequest request =
                new MockHttpServletRequest(method, path);
        request.setServletPath(path);
        request.setParameter("username", username);
        request.setParameter("password", password);

        MockHttpServletResponse response = new MockHttpServletResponse();

        int[] chainCalls = {0};
        FilterChain chain = (servletRequest, servletResponse) ->
                chainCalls[0]++;

        int managerBefore = managerCalls.get();
        int sessionBefore = sessionCalls.get();

        filter.doFilter(request, response, chain);

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        String principal = current == null
                ? "(none)" : current.getName();

        System.out.println(label
                + ": http=" + response.getStatus()
                + ", chain=" + chainCalls[0]
                + ", manager=" + (managerCalls.get() - managerBefore)
                + ", session=" + (sessionCalls.get() - sessionBefore)
                + ", saved=" + repository.containsContext(request)
                + ", principal=" + principal);

        SecurityContextHolder.clearContext();
    }

    public static void main(String[] args)
            throws IOException, ServletException {

        AtomicInteger managerCalls = new AtomicInteger();
        AtomicInteger sessionCalls = new AtomicInteger();

        // Chỉ là manager mô phỏng cho demo. KHÔNG lưu hoặc so plaintext
        // bằng String.equals trong ứng dụng thật.
        AuthenticationManager manager = input -> {
            managerCalls.incrementAndGet();

            if ("lan".equals(input.getName())
                    && "DemoPass123!".equals(input.getCredentials())) {
                return UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null,
                        AuthorityUtils.createAuthorityList("ROLE_READER"));
            }

            throw new BadCredentialsException("Invalid credentials");
        };

        DemoFilter filter = new DemoFilter(manager);

        RequestAttributeSecurityContextRepository repository =
                new RequestAttributeSecurityContextRepository();

        filter.setSecurityContextRepository(repository);

        // Chỉ đếm callback; KHÔNG phải session fixation protection thật.
        filter.setSessionAuthenticationStrategy(
                (authentication, request, response) ->
                        sessionCalls.incrementAndGet());

        filter.setAuthenticationSuccessHandler(
                (request, response, authentication) ->
                        response.setStatus(204));

        filter.setAuthenticationFailureHandler(
                (request, response, exception) ->
                        response.setStatus(401));

        // Filter tự tạo không do Spring quản lý: xác nhận manager có mặt.
        filter.afterPropertiesSet();

        runCase("notMatchedMethod", filter, repository,
                managerCalls, sessionCalls,
                "GET", "/login-demo", "lan", "DemoPass123!");

        runCase("success", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "lan", "DemoPass123!");

        runCase("failure", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "lan", "wrong-password");

        runCase("pending", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "pending", "unused");

        runCase("notMatchedPath", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/another-path", "lan", "DemoPass123!");
    }
}
```

### 12.3. Lệnh chạy

Tại thư mục có `build.gradle`, sử dụng JDK 17+ và Gradle/Gradle Wrapper tương thích:

```bash
gradle run --quiet
```

**Stdout dự kiến của chương trình**, bỏ qua warning deprecation hoặc log từ Gradle/framework:

```text
notMatchedMethod: http=200, chain=1, manager=0, session=0, saved=false, principal=(none)
success: http=204, chain=0, manager=1, session=1, saved=true, principal=lan
failure: http=401, chain=0, manager=1, session=0, saved=false, principal=(none)
pending: http=202, chain=0, manager=0, session=0, saved=false, principal=(none)
notMatchedPath: http=200, chain=1, manager=0, session=0, saved=false, principal=(none)
```

Các dòng phản ánh **một filter chạy với mock Servlet request và handlers đã cấu hình**, không phải toàn bộ ứng dụng web. Mỗi case tạo request mới nên repository request attribute không dùng dữ liệu từ case trước. Trạng thái 200 khi matcher không khớp là mặc định của `MockHttpServletResponse` trong demo vì downstream chain chỉ đếm lời gọi, không ghi body/status.

### 12.4. Đọc từng nhánh trong stdout

**`notMatchedMethod`:** matcher yêu cầu POST, nên GET không gọi `attemptAuthentication`; manager và session strategy đều không chạy. Bộ lọc chuyển tiếp `FilterChain` một lần.

**`success`:** filter đọc form parameters, manager trả `Authentication` đáng tin cậy (giả lập), session strategy được gọi một lần, `successfulAuthentication` đặt holder và lưu context vào request attribute, success handler trả HTTP 204. Chain không chạy vì đây là login endpoint đã được filter xử lý.

**`failure`:** manager ném `BadCredentialsException`. Failure path xóa `SecurityContextHolder`, gọi handler trả HTTP 401 và không có context được lưu vào request repository. Demo không cài remember-me service hoạt động.

**`pending`:** subclass chủ động trả 202 và `null` trước khi gọi manager. Bộ lọc không gọi session strategy, success/failure handler hoặc chain. Nó đang mô phỏng hợp đồng “chưa hoàn tất”, **không phải quy trình MFA an toàn**.

**`notMatchedPath`:** method POST nhưng path khác `/login-demo`. Filter tiếp tục chain mà không xác thực, không tạo context.

### 12.5. Những điều demo không thể chứng minh

- **Không** chứng minh BCrypt/PBKDF2/Argon2, vì manager mock dùng chuỗi giả để kiểm soát nhánh. Trong hệ thống thật phải dùng `ProviderManager` + `AuthenticationProvider`, chẳng hạn `DaoAuthenticationProvider` và `PasswordEncoder`.
- **Không** chứng minh HttpSession persisting login: demo cố ý chọn request attribute repository.
- **Không** mô phỏng cookie `JSESSIONID`, thay session ID, CSRF, remember-me token, servlet dispatch `ERROR`, redirect hoặc logout.
- **Không** bảo đảm behavior của một filter đã đăng ký trong Spring Boot chain nếu cấu hình khác thứ tự/matcher/strategy/repository.
- **Không** phải mẫu MFA hay custom login protocol hoàn chỉnh; không dùng `pending` theo cách này để bảo vệ tài khoản thật.
- **Không** đo timing attacks, exception message exposure hay tính đồng thời của phiên.

Muốn đưa kiến thức vào sản phẩm, phải triển khai và kiểm thử filter chain thực cùng dependency injection, Servlet container và cấu hình bảo mật đầy đủ.

## 13. AuthenticationSuccessHandler/FailureHandler: phản hồi không thay thế bảo mật

### 13.1. Với browser/form login

Các handler thường dùng:

- `SavedRequestAwareAuthenticationSuccessHandler`: có thể chuyển user về tài nguyên đã muốn truy cập trước login.
- `SimpleUrlAuthenticationSuccessHandler`: redirect tới URL phù hợp.
- `SimpleUrlAuthenticationFailureHandler`: redirect tới trang lỗi hoặc gửi 401 khi không có URL lỗi.

Khi sử dụng saved requests, cần xem xét URL đích có đáng tin không, không tự đọc `redirectUrl` từ client rồi redirect tới domain bất kỳ (open redirect). `RequestCache` và handler mặc định có quy tắc riêng, nhưng code tùy biến không được bỏ qua validation.

### 13.2. Với JSON API

Một handler JSON có thể:

- Trả HTTP status rõ ràng và JSON body có format ổn định.
- Không chèn credentials/hash/stacktrace vào response.
- Dùng thông báo lỗi chung cho sai username/password để tránh enumeration.
- Giới hạn kích thước response và tránh ghi hai lần sau response commit.

Không chỉ thay success handler bằng JSON rồi tuyên bố authentication trở nên stateless. Nếu repository vẫn ghi `HttpSession`, ứng dụng có thể **vẫn dùng session**. Mô hình token issuance, refresh, expiry và revocation cần được thiết kế riêng.

### 13.3. Khi nào lỗi là 401, 403 hay 302?

| Tình huống | Hành vi thường gặp | Thành phần quyết định |
| --- | --- | --- |
| Chưa login mà truy cập URL protected | 302 tới login hoặc HTTP 401 | `AuthenticationEntryPoint`/exception handling |
| POST login sai password | 302 tới login?error hoặc HTTP 401 | `AuthenticationFailureHandler` |
| Login đúng, form browser | 302 tới saved request/URL thành công | `AuthenticationSuccessHandler` |
| Login đúng, API custom | 200/204/JSON theo thiết kế | Success handler |
| Đã authenticated nhưng thiếu quyền | Thường HTTP 403 | Authorization/`AccessDeniedHandler` |

Không gắn cứng `BadCredentialsException` với 403, cũng không nghĩ HTTP 204 tự chứng minh credential đúng nếu handler bị gọi sai thứ tự từ custom code.

## 14. Bảo mật cốt lõi khi tùy biến filter

### 14.1. Chỉ đánh dấu authenticated sau khi đã xác minh

**Sai:**

```java
// NGUY HIỂM: client tự chọn tên và authority rồi được tin.
return UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
```

**Đúng về nguyên tắc:**

```java
Authentication candidate =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, submittedPassword);

return authenticationManager.authenticate(candidate);
```

Client là nguồn **credential claim**, không phải nguồn quyết định quyền. Dữ liệu authority phải đến từ provider/store tin cậy sau kiểm chứng.

### 14.2. Không tự băm hoặc normalize mật khẩu trong filter

Filter nên lấy password theo format của giao thức và đưa raw password đến provider/encoder theo contract. Không:

- `strip()`, `trim()`, lower-case hoặc tự normalize password tùy tiện.
- Ghi password vào audit log, MDC, exception, tracing hoặc request dump.
- Gọi `encoder.encode(raw).equals(storedHash)` để so BCrypt hoặc salted KDF.
- Đưa password vào query string/redirect URL.

Thao tác lookup username có thể cần canonicalization theo policy, nhưng phải thống nhất với registration và user store; không áp dụng các phép biến đổi username cho password.

### 14.3. CSRF, brute force, session fixation và remember-me

Một filter xử lý login **không thay thế**:

- **CSRF protection** cho endpoint dùng cookie/session, đặc biệt form POST và các endpoint đổi trạng thái.
- **Rate limiting / credential stuffing defense** tại gateway/service theo user/IP/devices và chính sách không làm lộ tài khoản.
- **Session fixation protection** sau authentication thành công; cần session strategy đúng, không chỉ tạo một session bất kỳ.
- **HTTPS và cookie policy**: `Secure`, `HttpOnly`, `SameSite` theo kiến trúc.
- **MFA/step-up**, reset password và account recovery có flow riêng.
- **Logout và session revocation** khi đổi password, khóa account hoặc kết thúc phiên theo yêu cầu.

Nếu tự dựng filter trong test mà `SessionAuthenticationStrategy` chỉ là lambda đếm, **đừng** dùng nó làm cơ chế session production. Phải nối với strategy chuẩn được cấu hình phù hợp.

### 14.4. Ngăn leak SecurityContext và credentials

Sau khi request hoàn tất, Spring Security filter chain quản lý vòng đời `SecurityContextHolder`, bao gồm clear context khi phù hợp. Nhưng nếu custom code tự mở thread/async task, không được giữ ThreadLocal của user trước cho request sau. Dùng cơ chế context propagation chuẩn và cleanup rõ ràng.

`ProviderManager` theo mặc định có cơ chế xóa credentials sau xác thực thành công đối với các object hỗ trợ; đừng phụ thuộc vào việc custom principal sẽ tự xóa mọi password hash. Không cất JPA entity/lazy proxy hoặc toàn bộ request object vào session principal.

## 15. Bảo trì và kiểm thử trong ứng dụng Spring Security thật

### 15.1. Ma trận test cần có

| Test | Thiết lập | Điều phải xác nhận |
| --- | --- | --- |
| Matcher không khớp method | GET tới POST login URL | Filter không gọi manager; chain tiếp tục. |
| Matcher không khớp path | POST tới URL khác | Không bắt nhầm request; chain tiếp tục. |
| Login đúng | Valid credentials qua provider thật | Session strategy, success handler, context save theo policy. |
| Login sai | Sai password | Failure handler; không tạo authentication tin cậy. |
| Không tìm thấy user | Username không tồn tại | Phản hồi an toàn, không lộ enumeration chi tiết. |
| User disabled/locked/expired | Password đúng nhưng status không hợp lệ | Provider từ chối; không có success context. |
| `attemptAuthentication == null` | Multi-step giả lập có response | Không success/failure sớm; có cơ chế tiếp tục hợp lệ. |
| Session strategy từ chối | Vượt số phiên/vi phạm policy | Failure path, không cấp phiên. |
| `continueChainBeforeSuccessfulAuthentication` | Dùng tùy biến có chủ đích | Thứ tự downstream/holder/response đúng mong đợi. |
| Context session | Repository session/delegating | Request kế với cùng cookie khôi phục authentication. |
| Context request-only | RequestAttribute repository | Request mới không tự giữ login. |
| Redirect thành công | Form login và RequestCache | Đúng saved request hoặc URL fallback, không open redirect. |
| Session fixation | Có session cũ trước login | Session ID thay theo policy và state vẫn hợp lệ. |
| CSRF login | Cookie/session form | Token thiếu/sai bị từ chối ở nơi cần CSRF. |
| Failure UI | Browser/REST | Status/redirect và thông báo chung an toàn. |
| Nhiều filter chain | Một URL thuộc đúng chain | Chỉ filter dự kiến chạy; không double-register. |

### 15.2. Dùng `@WithMockUser` thế nào?

`@WithMockUser` tạo security context cho test authorization. Nó **không chứng minh**:

- `requiresAuthentication` match đúng.
- `attemptAuthentication` đã gọi manager.
- `PasswordEncoder.matches` đã chạy.
- Session strategy hoặc success/failure handlers đã được gọi.
- `SecurityContextRepository` đã lưu phiên qua request khác.

Muốn kiểm tra đăng nhập thật, dùng `MockMvc` với Spring Security filter chain, WebEnvironment test hoặc gọi filter/provider như ví dụ console. Với ứng dụng session-backed, test phải mang cùng `MockHttpSession`/cookie qua requests và xác nhận persistence/invalidations.

### 15.3. Quan sát lỗi trong production mà không lộ mật khẩu

Có thể log/metric các tín hiệu:

- Số login attempts/success/failure theo endpoint và loại thất bại ở mức tổng hợp.
- Latency của AuthenticationManager/provider và failure handler.
- Tỷ lệ status account locked/disabled, rate limiter trigger và CSRF failures.
- Session strategy exceptions, session creation/rotation và replay anomalies.
- Số lần custom filter bị gọi trên cùng một HTTP request, giúp phát hiện đăng ký hai lần.

**Tuyệt đối tránh:** raw password, header Authorization, reset token, TOTP secret, toàn bộ `Authentication.credentials`, chuỗi hash nguyên vẹn hoặc stacktrace chứa dữ liệu nhạy cảm. Nếu audit cần user identifier, áp dụng chính sách giảm nhạy cảm và quyền truy cập audit.

## 16. Những sai lầm phổ biến

1. **Đánh đồng `AbstractAuthenticationProcessingFilter` với `AuthenticationProvider`.** Filter điều phối HTTP; provider kiểm chứng credential.
2. **Cho rằng mọi request đi qua filter đều là login.** Matcher chọn request; URL khác phải tiếp tục chain.
3. **Bỏ qua HTTP method khi match login URL.** Dễ nhận cả GET và lộ credentials qua query/url.
4. **Trả `UsernamePasswordAuthenticationToken.authenticated(...)` từ giá trị client.** Bỏ qua xác minh, có nguy cơ cấp quyền tùy ý.
5. **Trả `null` khi password sai.** `null` báo quy trình chưa hoàn tất; thất bại phải ném `AuthenticationException` đúng.
6. **Đã gọi AuthenticationManager nhưng bỏ qua session strategy.** Custom filter có thể thiếu session fixation protection hoặc giới hạn phiên.
7. **Tưởng `SessionAuthenticationStrategy` mặc định luôn chống fixation khi tự new filter.** Default có thể là no-op; phải wiring đúng.
8. **Chỉ gọi `SecurityContextHolder.setContext` rồi mong request sau đã login.** Phải lưu context vào repository có persistence phù hợp.
9. **Cho rằng mọi filter nền tự lưu session.** API có cấu hình `setSecurityContextRepository`, default không bảo đảm lưu bền.
10. **Dùng RequestAttribute repo duy nhất cho login phải giữ qua request mới.** Request mới không mang request attribute cũ.
11. **Chạy `chain.doFilter` thủ công sau khi success handler đã commit.** Có thể trả body hai lần hoặc bỏ qua semantics của filter.
12. **Bật `setContinueChainBeforeSuccessfulAuthentication(true)` vì tưởng tương đương filter pass-through.** Nó đổi thứ tự xuống chain trước khi auth success được set/save, thường không đúng.
13. **Cho rằng `AuthenticationSuccessHandler` tự kiểm chứng password.** Handler chỉ nhận kết quả đã xác thực do upstream cung cấp.
14. **Trộn `AuthenticationEntryPoint` và `AuthenticationFailureHandler`.** Một bên yêu cầu bắt đầu login, bên kia báo kết quả login thất bại.
15. **Tin rằng HTTP 401 luôn là logout.** Status/handler không tự invalidate mọi session/token.
16. **Không xử lý failure handler an toàn.** Có thể lộ account tồn tại, internal exception hoặc stacktrace.
17. **Tắt CSRF toàn cục vì login POST không chạy.** Cần gửi CSRF token đúng hoặc thiết kế token/cookie policy hợp lệ.
18. **Không kiểm tra cookie và session ID sau login.** Authentication thành công nhưng session không được ghi/nhận có thể tạo UX “đăng nhập lại”.
19. **Đăng ký filter cả bằng `@Component` lẫn Spring Security DSL.** Filter có thể chạy hai lần hoặc ngoài đúng context.
20. **Dùng `@WithMockUser` như bằng chứng kiểm thử login.** Nó thường bỏ qua matcher, provider và handlers.
21. **Ghi raw password vào audit/error log để debug.** Dữ liệu xác thực bị rò ra hệ thống log.
22. **Tưởng Filter có quyền admin chỉ vì client gửi roles.** Authorities phải được provider/store tin cậy cấp.
23. **Không kiểm tra behavior khi session strategy ném exception.** Password đúng vẫn có thể bị từ chối theo session policy.
24. **Trộn login theo session với API stateless mà không định nghĩa rõ repository.** Hệ thống có thể vừa phát token vừa vô tình giữ session.
25. **Override `successfulAuthentication` rồi quên gọi super/lưu context.** Mất remember-me, event, context save hoặc handler behavior cần thiết.
26. **Override `unsuccessfulAuthentication` mà quên clear holder.** Có nguy cơ để sót authentication cũ trong request/thread.
27. **Sửa username bằng normalization khác nhau ở filter và store.** Tạo lỗi lookup, trùng identity hoặc account confusion.
28. **Để user principal tham chiếu JPA lazy entity sau transaction.** Context trong session không giúp ORM Session kéo dài.
29. **Giả định event interactive success tự cấp quyền nghiệp vụ.** Event/audit là thông tin, không thay authorization domain.
30. **Chỉ test đường thành công mà bỏ qua null/failure/non-matching.** Filter có nhiều nhánh quan trọng cần được bảo vệ khi refactor.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `AbstractAuthenticationProcessingFilter` khác `DaoAuthenticationProvider` như thế nào?

**Đáp án:** Filter nhận/chọn HTTP request, gọi AuthenticationManager và điều phối session/context/handlers. `DaoAuthenticationProvider` là provider kiểm tra username/password hash và trạng thái tài khoản thông qua `UserDetailsService`, `PasswordEncoder`.

**Câu 2.** `requiresAuthentication` trả false có nghĩa request đã authenticated không?

**Đáp án:** Không. Nó chỉ cho biết filter này không xử lý request như một login attempt và thường chuyển request cho filter chain.

**Câu 3.** `attemptAuthentication` có những cách kết thúc hợp lệ nào?

**Đáp án:** Trả `Authentication` thành công, ném `AuthenticationException` khi thất bại, hoặc trả `null` nếu quá trình chưa hoàn tất và subclass đã xử lý phản hồi/chuyển sang bước sau.

**Câu 4.** Nếu `attemptAuthentication` trả `null`, success/failure handlers có chạy không?

**Đáp án:** Không theo đường mặc định. Filter trả về ngay, không chạy session strategy hoặc lưu success context.

**Câu 5.** Chạy `sessionAuthenticationStrategy.onAuthentication` trước hay sau `successfulAuthentication`?

**Đáp án:** Sau khi attempt trả `Authentication` thành công, **trước** `successfulAuthentication`. Lỗi session policy có thể đưa login vào failure path.

**Câu 6.** Tại sao custom filter dùng `SecurityContextHolder.setContext` vẫn có thể làm request sau anonymous?

**Đáp án:** Holder chỉ giữ context hiện hành; cần save vào `SecurityContextRepository` phù hợp (ví dụ session/delegating) và có cookie/session hợp lệ để request sau khôi phục.

**Câu 7.** `setContinueChainBeforeSuccessfulAuthentication(true)` có nên bật để controller nhận một POST login sau khi đăng nhập không?

**Đáp án:** Thường không. Nó chạy chain trước success processing, có thể khiến downstream chưa thấy authentication mới và xử lý response sai thứ tự. Dùng success handler/endpoint architecture phù hợp.

**Câu 8.** Vì sao failure handler không phải là authentication entry point?

**Đáp án:** Failure handler báo kết quả một login attempt đã thất bại; entry point yêu cầu user bắt đầu authentication khi bị yêu cầu truy cập tài nguyên bảo vệ.

**Câu 9.** `UsernamePasswordAuthenticationFilter` mặc định đọc những parameter nào?

**Đáp án:** `username` và `password` từ form, với login processing URL mặc định `/login`; có thể cấu hình tên tham số và URL qua formLogin/filter API.

**Câu 10.** Tạo một filter mới bằng `new` rồi chỉ set manager đủ chống session fixation chưa?

**Đáp án:** Chưa. Cần `SessionAuthenticationStrategy` đúng, context repository, cookie/session policy, CSRF, handlers và integration test. Manager chỉ kiểm chứng credentials.

**Câu 11.** Vì sao `@WithMockUser` không chứng minh login filter đúng?

**Đáp án:** Test mock thường đặt sẵn `SecurityContext` mà không gọi matcher, attemptAuthentication, manager, session strategy hay handlers.

**Câu 12.** Khi login thất bại, `unsuccessfulAuthentication` nên làm gì?

**Đáp án:** Dọn context hiện hành, thông báo remember-me thất bại và để failure handler trả response phù hợp; không cấp Authentication tin cậy.

**Câu 13.** Một POST hợp lệ, manager thành công, nhưng filter chưa cấu hình repository bền vững. Kết quả thế nào?

**Đáp án:** User có thể authenticated trong request login hiện tại và success handler vẫn chạy, nhưng request mới không nhất thiết khôi phục được context. Cần repository persistence phù hợp với mô hình session-backed.

**Câu 14.** Vì sao một API JSON 204 thành công chưa đủ để chứng minh cơ chế login thật an toàn?

**Đáp án:** Handler có thể trả 204 trong demo mà provider/security policy chưa được test. Phải xác minh mật khẩu thực, status user, session/CSRF, chống brute force, lưu context và policy token theo toàn bộ filter chain.

## 18. Tài liệu tham khảo chính thức

- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `requiresAuthentication`, ba kết quả `attemptAuthentication`, session strategy, handlers, repository và filter chain behavior.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): tương quan giữa `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, entry point và `AbstractAuthenticationProcessingFilter`.
- [Spring Security 6.5.11 — UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): form fields, POST, `/login`, subclass behavior.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextHolderFilter`, explicit context save, các chiến lược session và migration.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository`, HttpSession/RequestAttribute/Delegating repositories và persistence.
- [Spring Security 6.5.11 — SessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html): callback sau authentication mới, các chiến lược quản lý session.
- [Spring Security 6.5.11 — AuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html): hợp đồng xử lý response sau login thành công.
- [Spring Security 6.5.11 — AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): hợp đồng xử lý lỗi xác thực.
- [Spring Security 6.5.11 — RememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html): `loginSuccess`, `loginFail` và token/cookie remember-me.
- [Spring Framework 6.2 — MockHttpServletRequest API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/mock/web/MockHttpServletRequest.html): mock Servlet request cho ví dụ Java 17.

**Kết luận:** `AbstractAuthenticationProcessingFilter` là **bộ điều phối login request trong Servlet filter chain**. Nó xác định request bằng `RequestMatcher`, giao kiểm chứng thực tế cho `AuthenticationManager` qua `attemptAuthentication` và xử lý chính xác ba kết quả: authenticated, failed hoặc pending. Khi thành công, cần quan tâm **session strategy → SecurityContext/Repository → remember-me/event → success handler**; khi thất bại phải dọn context và chuyển quyền phản hồi cho failure handler. Với code tùy biến, trách nhiệm lớn nhất là **không tự cấp danh tính từ client**, không bỏ bảo vệ session/CSRF và không quên persistence của authentication khi cần sử dụng qua nhiều HTTP requests.