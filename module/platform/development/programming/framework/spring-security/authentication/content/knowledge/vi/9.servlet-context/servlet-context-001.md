# SecurityContext, SecurityContextHolder và danh tính của yêu cầu hiện tại

Trong một ứng dụng **Spring Security dùng Servlet**, câu hỏi “request này đang được thực hiện bởi ai?” được trả lời chủ yếu thông qua **`SecurityContext`** và **`SecurityContextHolder`**. Khi cơ chế xác thực đã kiểm chứng credentials, Spring Security đặt một đối tượng `Authentication` vào `SecurityContext`; `SecurityContextHolder` là điểm truy cập context gắn với luồng xử lý hiện tại. Từ đó, filter, controller và tầng service có thể biết danh tính mà framework đang công nhận, cùng các quyền được cấp.

Tuy nhiên, **SecurityContext không tự xác thực mật khẩu, không phải HttpSession, không phải token JWT và không phải hồ sơ tài khoản nghiệp vụ**. Nó là một nơi chứa trạng thái bảo mật được nạp/thiết lập trong quá trình xử lý. Nếu context chưa có `Authentication`, hoặc chỉ có anonymous authentication, bạn không được kết luận người gọi là một user đăng nhập thật. Nếu tự đặt một token `authenticated=true` từ dữ liệu client mà chưa qua `AuthenticationManager`, bạn đã bỏ qua ranh giới tin cậy.

Bài thuộc nhóm **Ngữ cảnh Servlet** trong Spring Security Authentication. Nội dung sẽ xây dựng mô hình từ `Authentication` → `SecurityContext` → `SecurityContextHolder`, giải thích vòng đời trong `SecurityFilterChain`, tính theo thread, persistence giữa request bằng `SecurityContextRepository`, trường hợp stateless/JWT, cách đọc danh tính an toàn, xử lý async và ví dụ Java 17 có thể chạy độc lập.

## 1. Bức tranh tổng thể: ai, được xác thực bằng gì và nằm ở đâu?

~~~text
HTTP request
   |
   v
Servlet FilterChainProxy / SecurityFilterChain
   |
   +--> SecurityContextRepository nạp context (nếu được cấu hình)
   |       |
   |       '--> SecurityContextHolder của luồng request
   |
   +--> Authentication filter (session/form/basic/bearer/...)
   |       |
   |       +--> Chưa có bằng chứng hợp lệ -> chưa xác thực / anonymous
   |       |
   |       '--> Credentials/token hợp lệ
   |               -> Authentication đã được xác thực
   |               -> SecurityContext.setAuthentication(...)
   |               -> SecurityContextHolder.setContext(...)
   |
   +--> Authorization filters / method security
   |       '--> Dùng Authentication/authorities để quyết định quyền
   |
   +--> Controller -> Service -> Repository
   |       '--> Đọc danh tính hiện tại nếu cần, kiểm tra quyền nghiệp vụ
   |
   '--> Kết thúc dispatch / request
           -> Clear SecurityContextHolder để tránh rò sang request kế
~~~

Đây là sơ đồ khái niệm. Với Spring Security 6, chi tiết nạp và lưu context phụ thuộc filter, repository và cơ chế xác thực đã cấu hình. Một request có thể chỉ có anonymous token; với resource server dùng JWT, context thường được tạo từ bearer token trên **từng request** chứ không khôi phục từ server-side login session.

### 1.1. Ba API cốt lõi

| API | Vai trò | Ví dụ |
|---|---|---|
| `Authentication` | Mang **principal**, credentials (nếu còn), authorities, details và trạng thái xác thực | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken`, `AnonymousAuthenticationToken` |
| `SecurityContext` | Đối tượng chứa `Authentication` hiện tại | `context.getAuthentication()` |
| `SecurityContextHolder` | Cơ chế giữ/truy xuất `SecurityContext` của môi trường thực thi hiện tại | `getContext()`, `setContext()`, `clearContext()` |

`SecurityContextHolder` có tên “Holder” vì **nó giữ context**, không phải chính context. `SecurityContext` có thể được khởi tạo rỗng. `Authentication` vừa là kiểu dữ liệu mô tả yêu cầu **chưa xác thực** đưa vào `AuthenticationManager`, vừa là kiểu dữ liệu mô tả principal **đã được xác thực** sau thành công; hãy phân biệt theo nguồn gốc và trạng thái.

### 1.2. Không phải ServletContext

`jakarta.servlet.ServletContext` là phạm vi toàn bộ ứng dụng web, không phải danh tính người dùng. `SecurityContext` của Spring Security lại chứa authentication phục vụ một luồng xử lý bảo mật. Đặt user hiện tại vào một attribute toàn cục của `ServletContext` là sai: nhiều người dùng/request chia sẻ servlet application, dễ gây rò danh tính xuyên request.

## 2. Authentication là thông tin cốt lõi bên trong SecurityContext

`org.springframework.security.core.Authentication` có những method quan trọng:

~~~java
Object getPrincipal();
Object getCredentials();
Object getDetails();
String getName();
Collection<? extends GrantedAuthority> getAuthorities();
boolean isAuthenticated();
~~~

Đây là những **chữ ký minh họa API**; không phải một class cần tạo thêm trong project.

### 2.1. Ý nghĩa của từng thành phần

- **Principal:** đối tượng biểu diễn danh tính: có thể là chuỗi username, `UserDetails`, `Jwt`, `OidcUser` hoặc custom principal. **Không mặc định ép sang `UserDetails`**.
- **Credentials:** bằng chứng như password/token khi còn được giữ. Sau xác thực, nhiều provider/framework **xóa credentials** để giảm lộ bí mật; không trông chờ lấy được raw password từ `SecurityContext`.
- **Authorities:** các `GrantedAuthority` mà hệ thống gán cho principal, ví dụ `ROLE_READER` hoặc `SCOPE_orders:read`. Authority chỉ có ý nghĩa theo policy ứng dụng; có role không đồng nghĩa được xem mọi bản ghi.
- **Details:** metadata phụ trợ về authentication, đôi khi chứa thông tin request. Không nên coi IP, user-agent hoặc details do client gợi ý là bằng chứng danh tính tự thân.
- **getName():** tên biểu diễn bởi `Authentication`, thường tiện cho UI/audit, nhưng **không chắc là accountId bất biến**.
- **isAuthenticated():** trạng thái nội bộ trên token, **không đủ làm phép kiểm tra “đăng nhập thật” trong mọi trường hợp**; anonymous token có thể trả true.

### 2.2. Ví dụ cùng một danh tính với principal khác nhau

~~~text
Form login:
  Authentication: UsernamePasswordAuthenticationToken
  principal:      UserDetails (hoặc custom)
  name:           "linh"

JWT resource server:
  Authentication: JwtAuthenticationToken
  principal:      Jwt
  name:           có thể là claim "sub" theo cấu hình
  authorities:    ví dụ SCOPE_orders:read

OIDC login:
  Authentication: OAuth2AuthenticationToken
  principal:      OidcUser
  name:           thông tin theo principal / name attribute
~~~

Do đó, code như `(User) authentication.getPrincipal()` dễ ném `ClassCastException` khi chuyển phương thức login. Đối với dữ liệu nghiệp vụ, nên có một bước mapping an toàn từ identity bên ngoài sang **accountId nội bộ**. Đừng lấy email hoặc display name tùy ý làm khóa sở hữu order.

### 2.3. Authentication chưa được xác thực và đã được xác thực

Một yêu cầu username/password ban đầu có thể được tạo:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);
Authentication verified = authenticationManager.authenticate(request);
~~~

Đoạn code **chỉ minh họa**, cần biến và dependencies phù hợp. Input `request` chưa được tin cậy; `AuthenticationManager` và provider phải kiểm tra password/account status. Chỉ **khi `authenticate` thành công** mới có căn cứ để đặt `verified` vào `SecurityContext` của request theo flow phù hợp.

**Tuyệt đối không làm như sau từ request JSON chưa xác minh:**

~~~java
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        inputUsername, null, userProvidedAuthorities);
SecurityContextHolder.getContext().setAuthentication(forged);
~~~

Đây là **mã phản ví dụ**, không phải hướng dẫn triển khai. Nó biến dữ liệu do client tự khai báo thành “đã xác thực”. Factory `authenticated(...)` nên xuất hiện trong framework/provider đã kiểm chứng hoặc trong test/demo được kiểm soát, không dùng làm đường tắt login.

## 3. SecurityContext và SecurityContextHolder hoạt động thế nào?

Đọc context:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

`getContext()` thường trả một object `SecurityContext` (có thể rỗng), nên **không được chỉ kiểm tra context != null** để suy ra đã login. `getAuthentication()` có thể null hoặc là anonymous authentication.

Đặt context khi một provider đã xác thực thành công:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

Ở đây `verifiedAuthentication` là kết quả **đã được xác minh** bởi framework/provider; ví dụ không thể tự biên dịch nếu thiếu context gọi. Cách dùng `createEmptyContext()` được Spring Security khuyến nghị hơn việc mutate trực tiếp:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

vì một instance `SecurityContext` có thể được tham chiếu/chia sẻ trong một số cơ chế persistence; mutate object dùng chung dễ gây **race condition** hoặc thay đổi ngoài phạm vi mong muốn.

### 3.1. Các method thường dùng

| Method | Tác dụng | Khi nào cần |
|---|---|---|
| `getContext()` | Lấy context gắn với holder hiện tại | Đọc principal/authorities |
| `createEmptyContext()` | Tạo context mới chưa có authentication | Thiết lập identity an toàn sau xác thực |
| `setContext(context)` | Gán context hiện tại | Trong code auth hoặc propagation được kiểm soát |
| `clearContext()` | Loại context khỏi holder hiện tại | Cleanup sau unit test, tác vụ custom hoặc xử lý ngoài filter |
| `getContextHolderStrategy()` | Lấy strategy quản lý context | Tích hợp chuyên biệt, khi cần thay strategy |

Ngoài ra các phiên bản hiện đại có API deferred context để hỗ trợ lazy loading; dùng chúng theo tài liệu phiên bản. Phần lớn business service không cần gọi trực tiếp mọi method này.

### 3.2. Bản chất mặc định: ThreadLocal

Trong Servlet stack thông thường, `SecurityContextHolder` mặc định dùng **`MODE_THREADLOCAL`**. Context được liên kết với **thread thực thi hiện tại**:

~~~text
Thread T1 xử lý request Alice:
  SecurityContextHolder(T1) -> Authentication(Alice)

Thread T2 xử lý request Bob:
  SecurityContextHolder(T2) -> Authentication(Bob)

Thread T3 không có context:
  SecurityContextHolder(T3) -> context rỗng
~~~

Đây không phải map toàn cục `requestId -> user` mà app tự xây; Spring Security filter setup/cleanup theo lifecycle request. Thread có thể được pool tái sử dụng cho request khác, nên **clear context là bất biến bảo mật quan trọng**. Nếu một worker thread giữ auth của request trước, request sau có thể nhìn thấy nhầm danh tính.

### 3.3. MODE_INHERITABLETHREADLOCAL và MODE_GLOBAL

Spring Security hỗ trợ nhiều chiến lược:

- **`MODE_THREADLOCAL` (mặc định):** context cho thread hiện tại, phù hợp đa số Servlet applications.
- **`MODE_INHERITABLETHREADLOCAL`:** thread con **mới tạo** có thể kế thừa context từ parent tại thời điểm tạo; **không có nghĩa tự động an toàn với thread pool** vì các worker tái sử dụng.
- **`MODE_GLOBAL`:** một context dùng chung phạm vi JVM, có thể hợp một số standalone desktop/test scenario, **không phù hợp web multi-user**.
- **Custom `SecurityContextHolderStrategy`:** cho các môi trường/tích hợp đặc biệt, cần thiết kế và kiểm thử chặt.

Đừng đổi strategy toàn cục chỉ để `@Async` “có thể đọc được user”. Trong ứng dụng web, việc đưa quyền cao của request A vào worker thread phục vụ request B có thể gây lỗi quyền nghiêm trọng. Dùng cơ chế propagation có scope rõ (phần 7).

## 4. Danh tính được nạp và xóa trong vòng đời một Servlet request

Một request đến controller không tự nhiên có `Authentication`. Nó đi qua **`FilterChainProxy`** và `SecurityFilterChain`, với các filter được cấu hình cho request đó. Về mặt khái niệm:

~~~text
HTTP GET /orders
    |
    v
SecurityContextHolderFilter / context loading
    |
    v
Cơ chế authentication phù hợp
    |
    +--> session cookie -> khôi phục context nếu có
    +--> Authorization: Basic ... -> xác minh theo request
    +--> Authorization: Bearer ... -> xác minh token theo request
    +--> chưa có auth -> có thể đặt anonymous token
    |
    v
AuthorizationFilter / các cơ chế kiểm tra quyền
    |
    v
DispatcherServlet -> Controller -> Service
    |
    v
Filter chain hoàn tất -> SecurityContextHolder được dọn
~~~

Thứ tự filter thực tế khác nhau theo version/config, không nên copy sơ đồ thành danh sách filter cố định. Điều quan trọng: **nạp** từ một repository khi cần, **thiết lập** authentication sau xác minh, **lưu** nếu muốn dùng ở request sau, và **clear** đúng lifecycle.

### 4.1. SecurityContextHolderFilter so với SecurityContextPersistenceFilter

Trong Spring Security 6, `SecurityContextHolderFilter` là cơ chế phổ biến cho việc **đọc** `SecurityContext` từ `SecurityContextRepository` rồi đặt vào holder. Nó **không mặc định tự lưu lại mọi thay đổi**. Nếu custom authentication tự tạo context và muốn context tồn tại ở request sau, ứng dụng cần gọi `SecurityContextRepository.saveContext(...)` theo flow thích hợp.

`SecurityContextPersistenceFilter` thuộc mô hình cũ có cơ chế tự lưu trước khi response được commit/chuỗi filter kết thúc. Một ứng dụng **không nên cấu hình đồng thời hai filter này**. Spring Security đã chuyển sang mô hình explicit save cho Servlet security; hãy đối chiếu phiên bản và cấu hình `requireExplicitSave` khi nâng cấp ứng dụng cũ.

**Chú ý:** các cơ chế login do framework cung cấp (ví dụ form login/filter tương ứng) đã có đường xử lý lưu authentication theo cấu hình. Không có nghĩa developer phải gọi `saveContext` thủ công ở mọi controller; vấn đề thường phát sinh khi **tự viết custom authentication flow**.

### 4.2. Clear khác với logout và invalidate session

`SecurityContextHolder.clearContext()` chỉ gỡ context khỏi holder của execution hiện tại; nó **không đồng nghĩa** đã xóa một authentication đang lưu trong `HttpSession`, đã vô hiệu hóa session cookie, đã revoke JWT hoặc đã log out khỏi IdP.

Với logout thật, framework cần thực hiện handler/session invalidation, xóa context khỏi repository khi thích hợp, clear authentication và các hành động token/remember-me/CSRF khác theo policy. Khi có JWT stateless, không có session để xóa; cần TTL, revocation/token version/introspection nếu chính sách muốn thu hồi trước `exp`.

### 4.3. Không tự lưu static Authentication toàn ứng dụng

Sai:

~~~java
static Authentication lastLoggedInUser;
~~~

Nếu request A đăng nhập rồi request B đến sau, biến trên phản ánh **người đăng nhập gần nhất toàn JVM**, không phải danh tính của request B. Cũng sai khi lưu authentication trong singleton service field:

~~~java
@Service
class UserService {
    private Authentication currentAuthentication; // sai cho multi-request
}
~~~

Hai snippet là phản ví dụ. Cách đúng là nhận `Authentication` per request hoặc đọc `SecurityContextHolder` trong scope phù hợp; không giữ nó như trạng thái mutable toàn cục của một bean singleton.

## 5. SecurityContextRepository: một request hay nhiều request?

`SecurityContextHolder` quản lý context **đang có trong luồng xử lý**; `SecurityContextRepository` quản lý cách context được **khôi phục/lưu qua boundary Servlet** theo cấu hình.

| Repository | Cơ chế lưu | Phạm vi sử dụng điển hình |
|---|---|---|
| `HttpSessionSecurityContextRepository` | Gắn context vào `HttpSession` | Form login/session-based authentication |
| `RequestAttributeSecurityContextRepository` | Gắn context vào thuộc tính của **request hiện tại** | Giữ context trong các dispatch như ERROR của cùng một request; không duy trì giữa HTTP requests |
| `DelegatingSecurityContextRepository` | Lưu/đọc qua nhiều repository theo thứ tự | Cấu hình Spring Security 6 thường dùng request attribute và session |
| `NullSecurityContextRepository` | Không lưu gì | Chế độ stateless hoặc cơ chế chỉ cần auth trong request, tùy cấu hình |

Trong Spring Security 6, repository mặc định cho nhiều Servlet cấu hình thường là `DelegatingSecurityContextRepository` gồm `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. Nhưng **không suy ra một ứng dụng đã bật stateful session** chỉ vì biết default repository: `sessionCreationPolicy`, loại authentication và custom security chain có thể thay đổi hành vi.

### 5.1. Một request login theo session có thể diễn tiến như thế nào?

~~~text
POST /login (credentials hợp lệ)
  -> AuthenticationManager xác minh
  -> SecurityContext chứa Authentication
  -> SecurityContextRepository lưu phù hợp vào session
  -> Response có session cookie (nếu session được tạo)

GET /profile (request mới)
  -> Cookie session hợp lệ
  -> Repository tìm SecurityContext
  -> SecurityContextHolder của thread mới được nạp
  -> Controller biết người đang đăng nhập
  -> Cuối request: holder được dọn, session có thể vẫn tồn tại
~~~

Cơ chế này không đảm bảo người dùng đã được cấp quyền với *mọi* profile; vẫn phải kiểm tra authorization và tenant/resource ownership. Session ID là một credential phải bảo vệ bằng HTTPS, cookie attributes, CSRF và chống session fixation theo framework.

### 5.2. Stateless JWT có “SecurityContext” không?

**Có.** Stateless không có nghĩa Spring Security bỏ `SecurityContext`. Một resource server có thể kiểm tra bearer JWT trên mỗi request:

~~~text
Authorization: Bearer <token>
    |
    v
BearerTokenAuthenticationFilter -> JwtAuthenticationProvider/Decoder
    |
    v
JwtAuthenticationToken (đã xác minh chữ ký/issuer/exp/audience theo config)
    |
    v
SecurityContextHolder của request hiện tại
    |
    v
Authorization -> Controller
    |
    v
Request kết thúc, context được clear, không dựa vào login session để nhận diện
~~~

Các điều kiện JWT cụ thể phải được cấu hình đúng. **Một JWT còn hạn không đảm bảo account nội bộ chưa bị khóa/xóa hoặc role/tenant membership vẫn đúng tại thời điểm hiện tại**; chính sách revoke và đồng bộ quyền cần được thiết kế riêng.

Ví dụ cấu hình mảnh cho API stateless:

~~~java
http
    .sessionManagement(s -> s.sessionCreationPolicy(
            SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
~~~

Đây là **đoạn cấu hình trong Spring Security**, không phải program độc lập; cần Spring Security OAuth2 resource server/JWT dependencies, imports và cấu hình issuer/JWK/decoder phù hợp. Không đơn thuần đặt `STATELESS` là đủ để xác minh bearer token.

## 6. Đọc danh tính hiện tại đúng cách

### 6.1. Truy xuất qua SecurityContextHolder

Trong service ở **cùng thread** và đúng scope:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    // Chưa có Authentication trong context.
} else {
    String name = authentication.getName();
}
~~~

Đoạn trên **chưa đủ để kết luận người dùng đã đăng nhập thật**: `authentication` có thể là anonymous token. Không trả nguyên object `Authentication`, principal hoặc credentials trong JSON API nếu chưa cân nhắc dữ liệu nhạy cảm.

Nếu cần kiểm tra user có được xác thực không, ưu tiên **để Spring Security authorization xử lý** bằng `.authenticated()`, `@PreAuthorize` và policy thích hợp. Chúng hiểu ngữ nghĩa anonymous tốt hơn câu lệnh `auth.isAuthenticated()` tự viết.

### 6.2. Một controller Spring MVC minh họa

~~~java
@RestController
class CurrentUserController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        if (authentication == null
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .toList()
        );
    }
}
~~~

Đoạn này là **mảnh tích hợp**, không biên dịch độc lập nếu thiếu imports, Spring MVC config và authorization. Trong ứng dụng thực, thường cấu hình `/me` là `authenticated()` ở security chain và dùng DTO thay vì `Map`, chỉ trả field được phép lộ. Không dùng logic controller đơn giản trên thay cho cơ chế authorization của framework khi có nhiều loại `Authentication` hoặc custom trust resolver.

### 6.3. Authentication, Principal, @AuthenticationPrincipal, @CurrentSecurityContext

Spring MVC có nhiều cách truy cập thông tin request:

~~~java
@GetMapping("/hello")
String hello(Authentication authentication) {
    return "Hello " + authentication.getName();
}
~~~

~~~java
@GetMapping("/profile")
String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

~~~java
@GetMapping("/current")
String current(@CurrentSecurityContext(
        expression = "authentication.name") String username) {
    return username;
}
~~~

Cả ba đều là **mảnh controller minh họa**, yêu cầu endpoint được bảo vệ và imports Spring. Không phải mọi authentication có `UserDetails`: ví dụ `@AuthenticationPrincipal UserDetails` có thể không phù hợp với JWT/OIDC và có thể inject null. Khi chỉ cần tên biểu diễn, tham số `Authentication` thường ít phụ thuộc vào kiểu principal hơn; khi cần claim JWT, dùng `Jwt`/`JwtAuthenticationToken` và cấu hình đúng.

Servlet API cũng có `HttpServletRequest.getUserPrincipal()` và `getRemoteUser()`; trong ứng dụng Spring Security, giá trị phản ánh wrapper/cấu hình filter và không đồng nhất vô điều kiện với kiểu principal của `Authentication`. Đối chiếu cơ chế thực tế khi tích hợp thư viện Servlet cũ.

### 6.4. Nếu cần accountId bền vững

`authentication.getName()` có thể là username, email, subject của IdP hoặc giá trị tên custom. Với ownership của order, nên làm:

~~~text
Authentication đã xác thực
   -> principal/issuer/subject được tin cậy
   -> identity mapping được xác minh
   -> localAccountId (UUID)
   -> repository query theo ownerAccountId + tenantId + quyền
~~~

Không thực hiện:

~~~java
orderRepository.findByOwnerEmail(authentication.getName());
~~~

nếu email có thể thay đổi, chưa xác minh hoặc không có uniqueness theo tenant. **Định danh xác thực** và **định danh nghiệp vụ** cần có mối liên kết server-side đáng tin. Một authenticated principal không mặc nhiên được truy cập mọi dữ liệu cùng username hoặc tenant.

## 7. Trường hợp anonymous: vì sao isAuthenticated() có thể gây hiểu lầm?

Spring Security có `AnonymousAuthenticationFilter`, khi cấu hình phù hợp, sẽ đặt `AnonymousAuthenticationToken` nếu context chưa có `Authentication`. Token này giúp authorization xử lý người dùng chưa đăng nhập theo cách nhất quán.

Bẫy:

~~~java
Authentication a =
        SecurityContextHolder.getContext().getAuthentication();

if (a != null && a.isAuthenticated()) {
    // Không chắc đã là user đăng nhập thật!
}
~~~

`AnonymousAuthenticationToken` thường trả `isAuthenticated() == true` theo hợp đồng token của nó. Vì vậy phép kiểm tra trên **không đủ** để phân biệt anonymous với user đã được xác minh. Với endpoint cần login thật, dùng `authorizeHttpRequests(...).authenticated()` hoặc những abstraction của Spring Security hiểu anonymous.

Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là một **mảnh cấu hình web**; cần imports, bean/security dependencies, trang login/default flow và cấu hình CSRF/session phù hợp. `permitAll()` vẫn cho phép public endpoint, còn `authenticated()` không chấp nhận anonymous chỉ vì token có `isAuthenticated=true`.

### 7.1. Anonymous khác null Authentication

| Trạng thái | `getAuthentication()` | Có thể xem là login thật? |
|---|---|---|
| Chưa xử lý auth và chưa đặt anonymous | `null` | Không |
| Anonymous filter đã đặt token | `AnonymousAuthenticationToken` | Không |
| Login thành công bằng provider hợp lệ | `Authentication` xác thực | Có, nhưng vẫn phải kiểm tra authorization |
| JWT hợp lệ đã được xác minh theo config | Thường là `JwtAuthenticationToken` | Có trong phạm vi token/claims và local policy |
| Một custom filter tự tạo authenticated token từ raw input chưa xác minh | Có thể có token `isAuthenticated=true` | **Không đáng tin; lỗ hổng** |

`SecurityContextHolder` là một **cơ chế truyền đạt quyết định xác thực**, không phải một bằng chứng tự thân rằng quyết định đó đúng. Mã tạo authentication/kiểm tra token phải bảo toàn trust boundary.

## 8. Tác vụ bất đồng bộ, thread pool và propagation

### 8.1. Context không tự đi theo mọi thread

Mặc định, `SecurityContextHolder` dùng `ThreadLocal`. Vì vậy:

~~~text
HTTP request thread T1:
  Authentication = Alice

new Thread(...) T2:
  Authentication = null (theo MODE_THREADLOCAL mặc định)

@Async / Executor T3:
  Authentication có thể null hoặc sai nếu code tái sử dụng context không đúng
~~~

Không nên “sửa” bằng biến global hoặc tự cho mọi background task chạy với quyền Alice. Thay vào đó:

- **Tác vụ chỉ cần accountId:** truyền một identifier/DTO tối thiểu đã xác thực lúc submit job, sau đó job kiểm tra lại quyền cần thiết theo policy.
- **Tác vụ cần method security trong đúng context:** dùng `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` với phạm vi rõ.
- **Scheduled job hệ thống:** không mặc nhiên mượn identity của request cuối cùng; nếu cần identity dịch vụ riêng, định nghĩa service principal và quyền tối thiểu.
- **Reactive WebFlux:** context propagation khác, thường dùng Reactor Context và `ReactiveSecurityContextHolder`; không áp dụng máy móc ThreadLocal Servlet.

### 8.2. DelegatingSecurityContextRunnable giải quyết gì?

Ví dụ mảnh tích hợp:

~~~java
SecurityContext snapshot = SecurityContextHolder.getContext();
Runnable work = () -> protectedService.perform();

Runnable wrapped =
        new DelegatingSecurityContextRunnable(work, snapshot);
executor.execute(wrapped);
~~~

Đây là **đoạn tích hợp**, chưa biên dịch độc lập; `protectedService` và `executor` cần có. Wrapper thiết lập context cho delegate trong lúc chạy và dọn/khôi phục context theo implementation. Tuy nhiên, việc giữ nguyên **tham chiếu mutable SecurityContext** có thể rủi ro nếu có request khác thay đổi nó; với job dài hạn nên truyền data tối thiểu hoặc tạo context snapshot được kiểm soát.

### 8.3. Tránh MODE_INHERITABLETHREADLOCAL cho thread pool web

`MODE_INHERITABLETHREADLOCAL` chỉ kế thừa khi một **thread con được tạo**, không tự đồng bộ chính xác context ở mỗi lần pool thread nhận job. Worker pool có thể sống qua nhiều request, nên nếu không dọn/đóng gói context an toàn, job của Bob có thể nhìn thấy Alice. Đây là lý do các wrapper `DelegatingSecurityContext...` được thiết kế để đặt và dọn identity **cho từng task**.

Với `@Async`, dùng executor được bọc bằng `DelegatingSecurityContextAsyncTaskExecutor` theo tài liệu phù hợp; đồng thời xác định task chạy sau request kết thúc có nên còn được phép dùng quyền của user hay không. Quyền tại thời điểm submit không nhất thiết còn hợp lệ tại thời điểm xử lý.

## 9. Ví dụ chạy được: Java 17 + Spring Security Core, không cần server

Ví dụ này tập trung vào những điều có thể kiểm chứng ngoài Servlet container:

1. Tạo một `SecurityContext` rỗng.
2. Đặt `Authentication` **mô phỏng đã xác thực** lên holder của main thread.
3. Thread con thông thường **không thấy** principal do ThreadLocal.
4. `DelegatingSecurityContextRunnable` cho thread con nhìn thấy principal trong scope của task.
5. `clearContext()` dọn authentication khỏi holder trong main thread.

**Đây là demo về truyền context**, không phải ví dụ login hợp lệ. Chương trình cố ý tạo token `authenticated(...)` từ dữ liệu cố định chỉ để mô phỏng trạng thái sau xác minh. Không dùng cách tạo token đó từ input HTTP chưa qua `AuthenticationManager` trong ứng dụng thật.

### 9.1. Cấu trúc project

~~~text
security-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecurityContextDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.SecurityContextDemo'
}
~~~

Cần JDK 17+, Gradle tương thích và khả năng tải thư viện từ Maven Central lần đầu. Trong dự án Spring Boot, các dependency/version thường do starter/BOM quản lý. Ví dụ chỉ dùng core API, không chạy servlet filter, HTTP session hoặc JWT decoder.

### 9.2. Mã Java hoàn chỉnh

Tạo `src/main/java/example/SecurityContextDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityContextDemo {

    public static void main(String[] args) throws InterruptedException {
        // Chỉ tạo token mô phỏng để học; KHÔNG làm thế này
        // từ input HTTP trước khi xác thực bằng provider.
        Authentication demoAuthenticated =
                UsernamePasswordAuthenticationToken.authenticated(
                        "linh",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(demoAuthenticated);
        SecurityContextHolder.setContext(context);

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        System.out.println("main user -> " + current.getName());
        System.out.println("main authenticated -> "
                + current.isAuthenticated());
        System.out.println("main authority -> "
                + current.getAuthorities().iterator().next()
                    .getAuthority());

        // MODE_THREADLOCAL mặc định: thread con không tự kế thừa.
        Thread plainChild = new Thread(() -> {
            Authentication childAuth =
                    SecurityContextHolder.getContext()
                        .getAuthentication();
            System.out.println("plain child auth is null -> "
                    + (childAuth == null));
        });
        plainChild.start();
        plainChild.join();

        // Context của task được chỉ định rõ; không dùng global mode.
        SecurityContext taskContext =
                SecurityContextHolder.createEmptyContext();
        taskContext.setAuthentication(demoAuthenticated);

        Runnable task = () -> {
            Authentication taskAuth =
                    SecurityContextHolder.getContext()
                        .getAuthentication();
            System.out.println("delegated child user -> "
                    + taskAuth.getName());
        };

        Thread delegatedChild = new Thread(
                new DelegatingSecurityContextRunnable(
                        task, taskContext));
        delegatedChild.start();
        delegatedChild.join();

        // Khi task con hoàn tất, main thread vẫn giữ context riêng.
        System.out.println("main after child -> "
                + SecurityContextHolder.getContext()
                    .getAuthentication().getName());

        // Demo chạy ngoài Servlet filter nên phải tự cleanup.
        SecurityContextHolder.clearContext();
        System.out.println("main after clear is null -> "
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));
    }
}
~~~

### 9.3. Cách chạy và output dự kiến

Trong thư mục `security-context-demo`, nếu đã có Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu không có wrapper nhưng đã cài Gradle phù hợp:

~~~bash
gradle run
~~~

Windows PowerShell với wrapper thường chạy `.\gradlew.bat run`.

Đầu ra của **các lệnh `System.out.println`** trong chương trình, bỏ qua log Gradle:

~~~text
main user -> linh
main authenticated -> true
main authority -> ROLE_READER
plain child auth is null -> true
delegated child user -> linh
main after child -> linh
main after clear is null -> true
~~~

Giải thích theo thứ tự:

1. Main thread gắn context chứa token mô phỏng và đọc được `linh`/`ROLE_READER`.
2. Thread con bình thường không thấy context main theo `MODE_THREADLOCAL` mặc định, nên `childAuth == null`.
3. `DelegatingSecurityContextRunnable` tạm đặt task context cho delegated thread, nên task in `linh`; wrapper cleanup/khôi phục context sau task.
4. Main thread không mất context khi child kết thúc vì holder theo thread.
5. `clearContext` khiến main thread lấy context rỗng trong lần đọc sau.

**Giới hạn:** demo không chứng minh credentials hợp lệ, không kiểm tra quyền truy cập order, không lưu session và không kết nối HttpServletRequest. Trong production, Authentication phải đến từ filter/provider đã xác minh; context nên được quản lý bởi filter chain, không tự tạo authenticated token từ username người dùng gửi.

## 10. Khi tự thiết lập authentication: setContext chưa đủ để duy trì phiên

Một số ứng dụng viết custom login filter hoặc controller thay vì dùng `formLogin()`, OAuth2 login hoặc cơ chế chuẩn. Sau khi xác minh credentials bằng `AuthenticationManager`:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginName, rawPassword));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Nếu muốn khôi phục authentication ở HTTP request sau:
securityContextRepository.saveContext(
        context, servletRequest, servletResponse);
~~~

Đây là **mảnh tích hợp Servlet**, không phải program Java độc lập: `authenticationManager`, `securityContextRepository`, request/response và inputs phải được khai báo từ flow thực tế. Để tránh lỗi, hãy chú ý:

1. **Xác thực trước:** chỉ dùng `verified` sau khi `AuthenticationManager.authenticate` thực sự thành công.
2. **Tạo context mới:** không mutate một context session có thể đang dùng chung giữa các requests.
3. **Set và save khác nhau:** `setContext` ảnh hưởng execution hiện tại; `saveContext` cho repository cơ hội lưu context để dùng ở request sau theo chính sách.
4. **Lưu trước khi response commit** khi cơ chế session/cookie yêu cầu; không chờ controller đã gửi xong body mới lưu.
5. **Quản lý login/session:** nếu viết custom login, phải quan tâm session fixation, concurrent sessions, CSRF, remember-me, logout, failure handler, sự kiện authentication và audit; tốt hơn tận dụng filter chuẩn khi khả thi.
6. **Chọn đúng repository:** `NullSecurityContextRepository` cố ý không lưu session; `RequestAttributeSecurityContextRepository` chỉ giúp trong cùng request/dispatch, không phải “persist login”.
7. **Không tiết lộ raw credentials:** provider/manager và các filter xử lý credential erasure theo thiết kế; không đưa raw password vào session hoặc log.

Khi authentication thất bại, không để context từ một request trước tồn tại trên thread được tái sử dụng. Với luồng request chuẩn, filter chain dọn context trong lifecycle; custom code chạy ngoài lifecycle phải có cleanup `finally` thích hợp.

### 10.1. Muốn giữ login qua nhiều request, cần những gì?

Với session login thông thường:

- Security chain phù hợp và `SecurityContextRepository` có khả năng lưu context vào `HttpSession`.
- Authentication thành công được lưu **đúng lúc**.
- Client nhận và gửi lại session cookie hợp lệ.
- Session không bị hết hạn, logout hoặc revoke.
- Browser/proxy config không chặn cookie cần thiết.
- Login session được bảo vệ bằng HTTPS/cookie flags/CSRF/session fixation và policy phù hợp.

Nếu server dùng session policy `STATELESS`, bạn cần một cơ chế xác thực mỗi request (ví dụ JWT) chứ không thể chỉ gọi `setContext` một lần rồi kỳ vọng request tiếp theo vẫn biết user.

## 11. Bảo mật khi dùng “danh tính của yêu cầu hiện tại”

### 11.1. Đã xác thực không đồng nghĩa được phép truy cập mọi dữ liệu

Một controller có `Authentication` hợp lệ chứng minh framework đã nhận dạng principal theo cơ chế cấu hình. Nhưng quyền truy cập một order cụ thể còn phụ thuộc:

- Quyền/role/scope cần cho hành động.
- Quan hệ **owner** hoặc membership giữa account và đối tượng.
- **Tenant** đang thao tác và quyền trong tenant đó.
- Trạng thái account/membership vừa thay đổi kể từ lúc token hoặc session được cấp.
- Chính sách step-up/MFA cho hành động nhạy cảm.

Ví dụ query nên ràng buộc cả ownership và tenant:

~~~java
Optional<Order> findByIdAndOwnerAccountIdAndTenantId(
        UUID orderId, UUID ownerAccountId, UUID tenantId);
~~~

Đây là **chữ ký repository minh họa** trong ứng dụng có `Order`, không phải code độc lập. Nguồn của `ownerAccountId`/`tenantId` phải được xác định/kiểm chứng từ principal và domain authorization, không tin arbitrary `accountId` do client gửi.

### 11.2. Context có thể stale sau thay đổi quyền

Nếu authorities được lấy vào authentication lúc 08:00, nhưng role của user bị thu hồi lúc 08:05, session/JWT đang có có thể vẫn mang danh sách cũ đến lúc refresh/revoke. `SecurityContext` không tự polling DB để cập nhật mọi quyền theo thời gian thực.

Ứng dụng cần chọn:

- Refresh authentication/authorities theo request hoặc tại thời điểm nhạy cảm.
- Session invalidation, token version/revocation, TTL hợp lý.
- Domain policy check trực tiếp đối với ownership/membership nếu cần quyết định tức thời.
- Audit các thao tác đặc quyền, tránh dựa hoàn toàn vào một `ROLE_ADMIN` đã cũ.

### 11.3. Không lạm dụng getDetails/getCredentials cho logging

Không trả nguyên `Authentication` ra response hoặc dump context vào logs. Những object này có thể chứa encoded password, claims, request details, principal attributes hoặc token, tùy provider. Chỉ xuất thông tin đã được lọc rõ ràng:

~~~text
requestId:     <correlation ID>
actorAccountId:<stable internal ID, nếu đã được xác minh>
authMethod:    <form / bearer / oidc, dạng phân loại>
action:        <orders.read>
decision:      <ALLOW / DENY>
~~~

Không log `Authorization` header, session cookie, password, reset token, raw JWT hoặc toàn bộ authorities/claims nếu không có nhu cầu và quyền truy cập tương ứng.

## 12. Các vấn đề thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| `SecurityContextHolder.getContext().getAuthentication() == null` trong service | Request chưa xác thực, filter không bao phủ URL, code chạy trước auth filter hoặc ngoài request | Kiểm tra security chain/matcher/filter order và entry point |
| Controller thấy `anonymousUser` | Không có login thật; anonymous filter đặt token | Bảo vệ endpoint bằng `authenticated()`; không dựa vào `isAuthenticated` đơn lẻ |
| Sau POST login, GET tiếp theo mất user | Chỉ gọi `setContext`; quên `saveContext` trong custom flow, session cookie không tới, repo stateless | Kiểm tra `SecurityContextRepository`, session policy, cookie và save timing |
| Request A nhìn thấy user B | Lưu global/static auth hoặc quên clear custom thread | Bỏ trạng thái singleton/global; dọn ThreadLocal mỗi task/request |
| `@Async` đọc auth null | ThreadLocal không tự propagate sang executor | Dùng wrapper executor hoặc truyền accountId/DTO tối thiểu |
| Thread pool giữ user của job trước | Dùng InheritableThreadLocal/propagation sai, không cleanup | Dùng `DelegatingSecurityContext...` đúng task và cleanup |
| Cast principal sang `UserDetails` gây lỗi | JWT/OIDC/custom principal có kiểu khác | Dùng type phù hợp hoặc identity abstraction |
| `authentication.getName()` là email thay vì UUID | Name do provider/principal quyết định | Map sang accountId nội bộ đã xác minh |
| `clearContext` không logout session | Chỉ xóa thread holder, session repository vẫn lưu auth | Dùng logout flow chính thức và invalidate/revoke |
| API JWT stateless “không có session nhưng có authentication” | Bearer token được xác minh trong request | Đây là hành vi đúng; phân biệt request context với session |
| Mọi request vẫn thấy quyền cũ sau revoke role | Authentication cache/session/token stale | Cache invalidation, session/token revocation hoặc domain check |
| `SecurityContext` tồn tại nhưng không có người dùng | Empty context được tạo mặc định | Kiểm tra `getAuthentication()` và trust resolver |
| Tự tạo authenticated token mà login vẫn thành công với password sai | Custom code bypass manager | Không tạo token tin cậy từ input, luôn qua provider |
| Context mất ở ERROR dispatch | Repository chỉ xử lý một số dispatch, context đã clear | Kiểm tra `RequestAttributeSecurityContextRepository` và filter dispatch |
| Nhiều security chains | Request matcher/chains được chọn khác kỳ vọng | Kiểm tra URL/method/ordering, không chỉ xem một filterChain |

### 12.1. Debug theo đúng thứ tự

1. **URL/method nào đang được xử lý?** Chọn đúng `SecurityFilterChain` chưa?
2. **Request mang credential nào?** Session cookie, Basic header, bearer token hay không gì cả?
3. **Filter/provider nào xác minh?** Có AuthenticationManager/decoder đạt yêu cầu không?
4. **SecurityContextRepository nào được dùng?** Có session hoặc chỉ request attribute/null?
5. **Controller chạy trên thread nào?** Có qua `@Async`, executor, custom scheduling hoặc dispatch khác không?
6. **Auth là null/anonymous/real type nào?** In **class + trạng thái đã lọc**, không dump password/claims.
7. **Cần giữ qua request sau không?** Nếu có, kiểm tra explicit save/session cookie.
8. **Có xung đột quyền/tenant không?** Danh tính đúng chưa đủ, kiểm tra authorization/domain.
9. **Kết thúc request đã clear chưa?** Không cho principal rò sang worker/request kế tiếp.

### 12.2. Những hiểu nhầm cần loại bỏ

**Nhầm 1:** “`SecurityContextHolder` là session.”  
**Đúng:** Holder giữ context trong execution hiện tại; session chỉ là *một trong những* cách lưu context giữa requests.

**Nhầm 2:** “Có `SecurityContext` nghĩa là login.”  
**Đúng:** Context có thể rỗng; còn anonymous token không đại diện user đã đăng nhập.

**Nhầm 3:** “`isAuthenticated()==true` luôn là user thật.”  
**Đúng:** AnonymousAuthenticationToken có thể trả true; dùng `authenticated()`/trust resolver của framework.

**Nhầm 4:** “Đặt `SecurityContextHolder.setContext` là xong cho mọi request sau.”  
**Đúng:** Cần repository/session hoặc bearer authentication mỗi request; custom login thường phải save rõ.

**Nhầm 5:** “`ThreadLocal` bảo đảm context đi theo mọi async task.”  
**Đúng:** Context gắn với thread, không tự theo pool tasks. Truyền đúng context hoặc domain ID cần thiết.

**Nhầm 6:** “`Authentication.getName()` là accountId của hệ thống.”  
**Đúng:** Nó do principal/provider quyết định; có thể là email/username/OIDC subject.

**Nhầm 7:** “`SecurityContextHolder.clearContext()` đã xóa mọi JWT/session.”  
**Đúng:** Nó chỉ dọn holder ở execution hiện tại; logout/revocation là cơ chế riêng.

**Nhầm 8:** “Dùng custom SecurityContext trong filter là có thể bỏ qua session fixation và CSRF.”  
**Đúng:** Tự viết login thì phải bảo vệ đầy đủ lifecycle bảo mật; nên tận dụng filter chuẩn nếu có thể.

## 13. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
|---|---|
| Empty context mới | `getAuthentication()==null` |
| Context chứa verified auth | `getName/getAuthorities` phù hợp provider |
| Anonymous filter chạy cho public request | Không coi anonymous là user login thật |
| `.authenticated()` trên protected endpoint | Anonymous bị từ chối/đi qua entry point theo config |
| Form login đúng + session repository | Request sau có context hợp lệ nếu session cookie còn |
| Form login sai | Không gắn authenticated principal |
| Custom login chỉ setContext không save | Trong explicit-save flow, request sau không tự khôi phục context |
| Custom login set và save đúng repository | Request sau khôi phục khi session chính sách cho phép |
| Stateless bearer JWT hợp lệ | Authentication tạo trong request, không đòi server session |
| Bearer JWT sai chữ ký/audience/expired | Không cấp authenticated context thành công |
| Thay `ThreadLocal` bằng global trong web | Test cảnh báo nguy cơ rò giữa users; không dùng production |
| Plain new Thread | Theo mặc định không kế thừa context |
| `DelegatingSecurityContextRunnable` | Có principal đúng trong task và cleanup sau |
| Executor pool nhận task từ Alice/Bob liên tiếp | Không rò context giữa các tasks |
| `@AuthenticationPrincipal UserDetails` với Jwt auth | Test kiểu principal khác; không giả định cast thành công |
| User đổi tên/email | Mapping accountId vẫn ổn định |
| User bị thu hồi role khi session còn sống | Đảm bảo domain/authorization policy phản ánh thay đổi đúng SLA |
| Logout session | Session invalidation và context repository không tự khôi phục user cũ |
| ERROR dispatch | Context được bảo toàn hoặc hạn chế theo đúng repository/config |
| Multi-tenant resource | Chặn truy cập chéo tenant dù principal hợp lệ |
| Request cookie đi qua proxy | Cookie Secure/SameSite/Path phù hợp, không leak session |
| Concurrent requests cùng session | Không mutate shared `SecurityContext` làm user này ảnh hưởng user kia |

### 13.1. Câu hỏi tự ôn tập

**Câu 1.** `SecurityContext` khác `SecurityContextHolder` thế nào?  
**Trả lời:** Context là container chứa Authentication; Holder quản lý cách lưu/truy xuất context của execution hiện tại.

**Câu 2.** `getContext() != null` có chứng minh đã đăng nhập không?  
**Trả lời:** Không. Có thể nhận context rỗng.

**Câu 3.** `authentication.isAuthenticated()==true` đã đủ để coi là user đăng nhập thật không?  
**Trả lời:** Không. Anonymous authentication là ví dụ ngoại lệ quan trọng; dùng authorization abstraction phù hợp.

**Câu 4.** Một custom controller vừa xác thực thành công, gọi `setContext` nhưng request mới không thấy user. Vì sao?  
**Trả lời:** Holder chỉ có context hiện tại; cần `SecurityContextRepository.saveContext` và cơ chế session/cookie phù hợp để lưu giữa requests, hoặc xác thực lại mỗi request nếu stateless.

**Câu 5.** Tại sao trong code mới nên gọi `createEmptyContext()`?  
**Trả lời:** Để tránh mutate context có thể đang được tham chiếu/chia sẻ, hạn chế race condition.

**Câu 6.** Vì sao `@Async` không nhìn thấy user trong controller?  
**Trả lời:** Mặc định holder dùng ThreadLocal, executor chạy thread khác. Cần propagation thích hợp hoặc truyền accountId đáng tin.

**Câu 7.** Với JWT resource server stateless, có cần `SecurityContext` không?  
**Trả lời:** Có; authentication thường được xác minh từ token rồi gắn vào context cho request đó. Không nhất thiết lưu session.

**Câu 8.** `clearContext()` có tự thu hồi JWT không?  
**Trả lời:** Không. JWT/session revocation là vấn đề riêng.

**Câu 9.** `getName()` có phải khóa sở hữu đơn hàng không?  
**Trả lời:** Không mặc định. Dùng identity mapping sang accountId nội bộ và authorization theo resource.

**Câu 10.** Tự tạo `authenticated(...)` từ username và role do client gửi có an toàn không?  
**Trả lời:** Không; đó là bypass xác thực. Framework/provider phải kiểm chứng bằng chứng trước khi tạo principal tin cậy.

## 14. Checklist áp dụng

- [ ] Biết rõ `Authentication`, `SecurityContext`, `SecurityContextHolder` khác nhau về vai trò.
- [ ] Không nhầm context rỗng hoặc anonymous với user đã được xác thực.
- [ ] Dùng `SecurityContextHolder` trong phạm vi request/thread phù hợp; không lưu auth vào singleton/static state.
- [ ] Giữ `MODE_THREADLOCAL` mặc định cho Servlet web trừ khi có lý do tích hợp đã kiểm định.
- [ ] Khi tạo context mới sau xác thực, dùng `createEmptyContext` và chỉ đặt **Authentication đã kiểm chứng**.
- [ ] Chọn đúng `SecurityContextRepository` và hiểu khác biệt request attribute/session/null.
- [ ] Nếu custom login cần duy trì session, gọi `saveContext` đúng thời điểm trong explicit-save flow.
- [ ] Đừng can thiệp tay vào filter chain/cleanup khi cơ chế Spring Security chuẩn đã giải quyết.
- [ ] Cấu hình endpoint authorization bằng `authenticated()`, roles/scopes và kiểm tra domain ownership.
- [ ] Dùng `Authentication`/`@AuthenticationPrincipal`/`@CurrentSecurityContext` đúng loại principal của từng phương thức login.
- [ ] Khi cần business user, map principal sang accountId và tenant context tin cậy.
- [ ] Đối với `@Async`/executor, truyền context có scope hoặc dữ liệu tối thiểu, không dùng global user.
- [ ] Bảo vệ session cookie, CSRF, session fixation, logout và token revocation theo phương thức authentication.
- [ ] Không trả nguyên Authentication/claims/hash/credentials trong API/log.
- [ ] Test null, anonymous, session, JWT, async, logout, stale roles và multi-tenant boundaries.
- [ ] Đối chiếu filter/repository và API của phiên bản Spring Security đang chạy trước khi thay đổi custom flow.

**Ghi nhớ:** `SecurityContext` là nơi chứa quyết định **Authentication đang được framework công nhận**; `SecurityContextHolder` đưa context tới code đang xử lý request (thường qua `ThreadLocal`). Nạp đúng ở đầu request, đặt chỉ sau xác minh, lưu nếu muốn duy trì qua request khác, kiểm tra quyền ở các tầng thích hợp, và dọn context sau khi hoàn tất là những nguyên tắc không thể tách rời.

### Tài liệu chính thức

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): vai trò của `SecurityContextHolder`, `SecurityContext`, `Authentication` và cách truy cập principal.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository`, session/request attributes và các filter persistence.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextHolderFilter`, `requireExplicitSave` và explicit save trong Spring Security 6.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, executor wrappers và context propagation.
- [Spring Security — SecurityContextHolder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `getContext`, `createEmptyContext`, `setContext`, `clearContext` và strategies.
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html): `AnonymousAuthenticationToken`, anonymous principal và authorization.
