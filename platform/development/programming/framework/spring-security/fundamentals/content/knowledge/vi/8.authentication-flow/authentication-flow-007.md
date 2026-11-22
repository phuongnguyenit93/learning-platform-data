# Xử lý sau xác thực thành công và trách nhiệm lưu ngữ cảnh

> **Cốt lõi:** `AuthenticationManager.authenticate(...)` xác minh credential và trả về một `Authentication` đã được chấp nhận. Nhưng một lần đăng nhập thành công còn nhiều việc ở **tầng web**: xử lý session fixation, đưa authentication vào `SecurityContext` hiện tại, **lưu context bằng `SecurityContextRepository` nếu muốn request sau khôi phục được**, kích hoạt xử lý remember-me/sự kiện khi áp dụng, rồi để `AuthenticationSuccessHandler` quyết định response hoặc redirect. Trong Spring Security 6.x, `SecurityContextHolderFilter` **nạp** context chứ **không tự lưu mọi thay đổi**. Các authentication filter chuẩn của framework xử lý việc lưu theo thiết kế; code tự làm login phải hiểu và thực hiện phần đó.

Bài thuộc nhóm **Luồng xác thực** của module **Spring Security – fundamentals**. Mô hình chính là **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, Servlet/Spring MVC**. Ví dụ đầy đủ ở cuối bài có session-based form login và kiểm thử HTTP bằng MockMvc. Với WebFlux, Spring Security dùng `SecurityWebFilterChain`, `ReactiveSecurityContextHolder` và cơ chế reactive context/repository tương ứng; không áp dụng mô hình `ThreadLocal` Servlet như một quy tắc chung.

## 1. Học xong cần nắm được gì?

1. Giải thích chính xác **authentication success**, **security context của request**, **persistence qua request** và **success handler** là bốn khái niệm riêng.
2. Theo dõi luồng đăng nhập bằng form: `UsernamePasswordAuthenticationFilter` → `AuthenticationManager` → `Authentication` thành công → `SessionAuthenticationStrategy` → `SecurityContextHolder`/`SecurityContextRepository` → `AuthenticationSuccessHandler`.
3. Biết `SecurityContextHolderFilter` và `SecurityContextRepository` làm gì trong Spring Security 6; phân biệt với cách tự động lưu ở Spring Security 5.
4. So sánh `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository` và `NullSecurityContextRepository`.
5. Hiểu tại sao session cookie thường là một **mã tham chiếu**, không phải chuỗi serialize toàn bộ `Authentication`.
6. Dùng `SavedRequestAwareAuthenticationSuccessHandler` để đưa user trở lại URL đã yêu cầu; không nhầm `RequestCache` với nơi lưu danh tính.
7. Biết khi nào phải gọi `saveContext(context, request, response)` trong custom login, và những việc phụ trợ phải thiết kế (CSRF, session fixation, concurrent sessions, failure handling, logout).
8. Kiểm tra bằng MockMvc rằng sau login, request tiếp theo có cùng session được chấp nhận, request mới không có session bị từ chối, login sai không cấp quyền, logout xóa quyền và role admin vẫn được áp dụng.

## 2. Một lần đăng nhập thành công xảy ra tại nhiều lớp

```text
Browser gửi POST /login
  username, password, _csrf, session cookie (nếu có)
          |
          v
Servlet Filter Chain / Spring Security
          |
          v
UsernamePasswordAuthenticationFilter
  tạo UsernamePasswordAuthenticationToken CHƯA xác thực
          |
          v
AuthenticationManager (thường ProviderManager)
          |
          v
AuthenticationProvider (ví dụ DaoAuthenticationProvider)
  UserDetailsService + PasswordEncoder + account checks
          |
       +--+-------------------------------------+
       |                                        |
   THẤT BẠI                                THÀNH CÔNG
       |                                        |
       v                                        v
AuthenticationFailureHandler              Authentication result
(clear context, response lỗi...)          principal + authorities đáng tin
                                               |
                                               v
                                    SessionAuthenticationStrategy
                                    (session fixation/concurrency ...)
                                               |
                                               v
                                    SecurityContext mới chứa result
                                               |
                           +-------------------+------------------+
                           |                                      |
                           v                                      v
                SecurityContextHolder                   SecurityContextRepository
                (request hiện tại)                    (lưu nếu cần request sau)
                           |                                      |
                           +-------------------+------------------+
                                               |
                                               v
                                  Remember-me / success event
                                  (khi được cấu hình/áp dụng)
                                               |
                                               v
                                  AuthenticationSuccessHandler
                                  (redirect, response/status, ...)
                                               |
                                               v
                                    Browser nhận response
                                               |
                 GET /me + session cookie ở request tiếp theo
                                               |
                                               v
                                    SecurityContextHolderFilter
                                    khôi phục context từ repository
                                               |
                                               v
                                    Authorization → Controller
```

Sơ đồ mô tả **đường xử lý form login Servlet** thông dụng, không phải danh sách filter/thứ tự bất biến cho mọi cơ chế hay phiên bản. Điểm chắc chắn cần hiểu: authentication provider xác minh danh tính; authentication filter chuẩn quản lý thành công ở HTTP boundary; success handler giải quyết **phản hồi sau thành công**.

**Không kết luận:** “Vì `AuthenticationManager` trả về true, Spring tự lưu session ở mọi trường hợp”. `AuthenticationManager` có nhiệm vụ trả result hoặc ném `AuthenticationException`, **không tự tạo response, set cookie, redirect hoặc lưu context** khi bạn gọi trực tiếp từ một service.

## 3. Sau authenticate() thành công, điều gì đã và chưa được thực hiện?

Ví dụ được gọi trong một custom flow:

```java
Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified =
    authenticationManager.authenticate(pending);
```

Đây là snippet, các biến đã được cung cấp bởi caller đáng tin. Nếu password đúng và provider hỗ trợ, `verified` là kết quả chứa principal/authorities đã kiểm chứng. Nhưng từ đúng hai dòng trên, **chưa thể suy ra**:

- `SecurityContextHolder.getContext().getAuthentication()` đang là `verified`.
- Browser đã nhận `JSESSIONID` hoặc session ID đã được đổi để chống session fixation.
- `SecurityContextRepository` đã ghi context để request sau truy xuất.
- `AuthenticationSuccessHandler` đã chạy và redirect đến trang đích.
- Remember-me cookie đã được thiết lập hoặc login audit event đã được phát.
- Ứng dụng đã kiểm tra quyền đọc/sửa từng object thuộc tenant nào.

Cần phân biệt:

| Bước | Thành phần chịu trách nhiệm | Điều tạo ra |
| --- | --- | --- |
| Xác minh credential | `AuthenticationManager`/`AuthenticationProvider` | `Authentication` thành công hoặc exception |
| Xử lý session khi vừa login | `SessionAuthenticationStrategy` được authentication mechanism gọi | Có thể đổi session ID, kiểm tra concurrent sessions |
| Danh tính trong request hiện tại | `SecurityContextHolderStrategy` và `SecurityContext` | Các filter/handler sau đó đọc được actor |
| Lưu danh tính để khôi phục | `SecurityContextRepository` | Ngữ cảnh gắn với session, request attribute hoặc storage khác |
| Nhớ URL người dùng đã định mở | `RequestCache` | `SavedRequest`, **không** phải authentication |
| Xử lý response khi login thành công | `AuthenticationSuccessHandler` | Redirect/status/header/body do ứng dụng chọn |
| Remember-me nếu cấu hình | `RememberMeServices` | Cơ chế đăng nhập tiếp nối riêng, thường qua cookie |
| Sự kiện authentication | `ApplicationEventPublisher` và các lớp hỗ trợ | Tín hiệu để audit/quan sát nếu được xử lý |
| Kiểm tra quyền | `AuthorizationFilter`, method/domain policy | Quyết định quyền gọi route/action/resource |

Việc gán một `Authentication` vào `SecurityContextHolder` chỉ làm thông tin đó sẵn có trong **luồng xử lý hiện tại**; không phải hành động lưu vĩnh viễn. Ngược lại, repository có thể đã lưu context của một request trước, nhưng vào request tiếp theo phải có cơ chế **nạp lại** rồi đặt nó vào holder.

## 4. AuthenticationSuccessHandler thực sự làm gì?

### 4.1. Giao diện

Trong Servlet:

```java
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
```

Interface này nhận `HttpServletRequest`, `HttpServletResponse` và `Authentication` đã xác thực để định nghĩa **hành vi sau khi login thành công**:

```java
// Chữ ký khái niệm của interface.
void onAuthenticationSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication
) throws IOException, ServletException;
```

Một handler có thể:

- Redirect đến URL người dùng đã định truy cập, ví dụ `GET /orders` trước khi login.
- Redirect đến trang mặc định như `/dashboard`.
- Trả HTTP `200`/`204` hoặc JSON tối thiểu cho frontend theo giao thức đăng nhập được thiết kế.
- Ghi nhận sự kiện audit **không chứa password/token** hoặc cập nhật dấu mốc user đã login theo cách không làm hỏng transaction.
- Áp chính sách redirect cùng origin/allowlist, không tin một `returnUrl` bên ngoài do client điều khiển.

Nó **không có hợp đồng mặc định là “đưa authentication vào HttpSession”**. Trong luồng `AbstractAuthenticationProcessingFilter`/form login chuẩn, filter đã xử lý việc tạo/gắn/lưu context trước khi gọi success handler theo cơ chế framework hiện hành. Khi bạn tự viết controller login, không có bảo đảm một success handler được gọi thủ công sẽ thay bạn lưu context.

### 4.2. SavedRequestAwareAuthenticationSuccessHandler

Một tình huống phổ biến:

```text
1. Anonymous: GET /reports/quarter
2. ExceptionTranslationFilter: yêu cầu đăng nhập
3. RequestCache: lưu URL gốc (SavedRequest) nếu chính sách cho phép
4. Browser -> /login
5. POST /login: credential hợp lệ
6. SavedRequestAwareAuthenticationSuccessHandler:
   redirect tới /reports/quarter (nếu request đã lưu hợp lệ)
7. Browser gửi GET /reports/quarter với session mới
8. Repository nạp context; route được kiểm tra quyền bình thường
```

`SavedRequestAwareAuthenticationSuccessHandler` thường ưu tiên request đã được `RequestCache` lưu, nếu có và hợp lệ; nếu không có thì dùng default target URL được cấu hình. Có thể lựa chọn cố định một đích bằng `setAlwaysUseDefaultTargetUrl(true)` nhưng sẽ bỏ cơ chế trở lại trang ban đầu.

**Phân biệt rõ:** `RequestCache` lưu **request cần làm lại**. `SecurityContextRepository` lưu **ngữ cảnh danh tính**. Session có thể chứa cả hai loại dữ liệu, nhưng mục đích và thời điểm sử dụng khác nhau. Nếu tắt request cache, login vẫn có thể tạo session/authenticated context; chỉ mất cơ chế trở về URL trước login.

### 4.3. Ví dụ success handler có delegate, không lộ dữ liệu

```java
@Bean
AuthenticationSuccessHandler loginSuccessHandler() {
    SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();
    delegate.setDefaultTargetUrl("/me");

    return (request, response, authentication) -> {
        // Header chỉ để test rằng callback chạy; không chứa user/secret.
        response.addHeader("X-Lab-Login-Processed", "1");

        // Giữ hành vi redirect an toàn từ framework.
        delegate.onAuthenticationSuccess(request, response, authentication);
    };
}
```

Đây là một method bean hoàn chỉnh nếu đặt trong class `@Configuration` có import thích hợp; ví dụ ứng dụng đầy đủ ở phần thực hành. Header `X-Lab-Login-Processed` là tín hiệu học tập, không phải yêu cầu của Spring Security hoặc header cần triển khai production. Trong ứng dụng thật, audit nên ghi user ID ổn định và thời gian thành công, giới hạn dữ liệu nhạy cảm, chống log injection và bảo đảm việc ghi audit không làm lộ password/token.

### 4.4. Login thành công không nhất thiết phải trả 200

Form login thường trả HTTP **302** sang trang đích. Request GET sau redirect mới trả **200** khi handler xử lý thành công. Đối với SPA/API có thể thiết kế response 200 hoặc 204, song phải quy định session cookie/CSRF/token contract rõ ràng. Không coi 302 là login thất bại; kiểm tra `Location` và request tiếp theo.

## 5. SecurityContextHolder, SecurityContext và SecurityContextRepository

### 5.1. Context hiện tại

`SecurityContextHolder` cung cấp API lấy/đặt `SecurityContext` hiện tại:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();
```

Ở Servlet, chiến lược mặc định thường là `ThreadLocal`; filter chain quản lý vòng đời ngữ cảnh cho request. Đừng lưu `Authentication` vào field mutable của singleton service hoặc biến static toàn cục. Khi servlet worker thread được tái sử dụng cho request khác, Spring Security dọn holder theo luồng chuẩn để không mang danh tính Alice sang request Bob.

### 5.2. Repository là cách khôi phục context

`SecurityContextRepository` là hợp đồng để tìm/lưu context theo request/response. Các method quan trọng gồm:

```java
SecurityContext context =
    securityContextRepository.loadContext(
        new HttpRequestResponseHolder(request, response));

securityContextRepository.saveContext(context, request, response);
```

Đây là snippet minh họa API; Spring Security 6 có cơ chế tải trì hoãn `loadDeferredContext(...)`, thường được `SecurityContextHolderFilter` sử dụng. Mã ứng dụng không nên tự gọi `loadContext(...)` một cách tùy tiện ở controller chỉ để biết user hiện tại; đọc từ `SecurityContextHolder` hoặc injection framework sẽ rõ và an toàn hơn.

### 5.3. Các repository phổ biến

| Implementation | Lưu ở đâu? | Tồn tại qua request mới? | Khi hữu ích |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Thuộc tính security context trong HTTP session | **Có**, nếu session hợp lệ và client gửi session ID | Form login/session-based apps |
| `RequestAttributeSecurityContextRepository` | Attribute của Servlet request | **Không** qua request HTTP mới; có thể dùng qua các dispatch trong cùng request | Giữ context khi chuyển ERROR/FORWARD tùy trường hợp |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository, mặc định thường gồm hai loại trên | Theo delegate thực sự lưu được | Spring Security 6 Servlet default |
| `NullSecurityContextRepository` | Không lưu | **Không** | API stateless được xác thực lại mỗi request |
| Repository tùy chỉnh | Cache/DB/storage theo hợp đồng riêng | Tùy thiết kế | Hạ tầng đặc biệt, audit/lifecycle/cluster cần quản lý |

Ở Spring Security 6, repository mặc định thường là `DelegatingSecurityContextRepository` kết hợp `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. Một context có thể được lưu trong request attributes để error dispatch còn truy cập được, và trong HTTP session để một **request sau** khôi phục identity.

### 5.4. Cookie JSESSIONID có chứa username và role không?

Thông thường **không**. Browser giữ cookie định danh session (thường `JSESSIONID`); server hoặc hệ thống session storage ánh xạ session ID đến dữ liệu session, trong đó có thể chứa `SPRING_SECURITY_CONTEXT`. Không serialize toàn bộ object `Authentication` vào cookie chỉ vì thấy browser đã login. Tuy vậy, giá trị session ID là **credential nhạy cảm** vì ai có nó có thể chiếm phiên nếu không có biện pháp bảo vệ.

```text
Browser:
  Cookie: JSESSIONID=<mã phiên, không hiển thị giá trị thật>
       |
       v
Server session storage:
  session ID -> SecurityContext(Authentication: alice, ROLE_USER)
       |
       v
SecurityContextRepository.load... -> SecurityContextHolder -> Controller
```

Thực tế tên cookie và nơi lưu session có thể thay đổi (Spring Session, custom session store). Không assume tất cả cơ chế xác thực dựa trên server session: API dùng Bearer JWT hoặc HTTP Basic stateless có thể tạo authentication mới ở mỗi request mà không dùng session.

## 6. “Explicit save” trong Spring Security 6: điểm dễ nhầm nhất

### 6.1. Spring Security 5 và 6 khác nhau thế nào?

Theo tài liệu Spring Security:

- Trước đây, `SecurityContextPersistenceFilter` thường nạp context đầu request và có cơ chế tự phát hiện/lưu lại context khi request/response hoàn tất.
- Ở **Spring Security 6**, mặc định dùng `SecurityContextHolderFilter`: nó **nạp** context từ `SecurityContextRepository` và làm cho context khả dụng cho xử lý request, rồi dọn đúng vòng đời. Nó **không tự phát hiện và ghi mọi lần thay đổi** vào session.
- Do đó, khi một **custom controller hoặc custom filter** tự xác thực và muốn đăng nhập tồn tại qua request, code phải **gọi `SecurityContextRepository.saveContext(...)`** có chủ đích.
- Các cơ chế authentication **có sẵn** như form login được thiết kế để quản lý bước lưu phù hợp. Không cần viết lại logic lưu session chỉ vì dùng `formLogin()` bình thường.

Cấu hình chuyển tiếp `requireExplicitSave(false)` có thể được gặp trong hệ thống cũ khi migrate, nhưng đó là phương án tương thích; với dự án mới, nên hiểu và dùng mặc định hiện đại thay vì dựa vào tự lưu ngầm định.

### 6.2. Lỗi thường gặp: chỉ set vào holder

```java
Authentication verified = authenticationManager.authenticate(pending);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// THIẾU nếu muốn duy trì login sang request sau:
// securityContextRepository.saveContext(context, request, response);
```

Trong request hiện tại, đoạn code phía sau có thể thấy Alice. Sau khi response hoàn tất và request mới tới, repository không có context được lưu, nên `GET /me` lại được coi chưa xác thực. Kết quả có thể là browser “đăng nhập thành công rồi lại bị chuyển về login”.

**Nhớ chính xác:** `setContext(...)` là thao tác trên **current holder**; `saveContext(...)` là thao tác trên **persistence strategy**. Hai việc không thể coi là một.

### 6.3. Quy trình lưu thủ công có trách nhiệm

Đoạn dưới chỉ là **khung kỹ thuật** cho một custom login handler đã được thiết kế đầy đủ; nó **chưa phải endpoint production độc lập**:

```java
// Các biến đầu vào được inject/cung cấp bởi cơ chế đáng tin:
// AuthenticationManager authenticationManager;
// SecurityContextHolderStrategy holderStrategy;
// SecurityContextRepository repository;
// SessionAuthenticationStrategy sessionStrategy;
// HttpServletRequest request; HttpServletResponse response;
// String username; String password;

Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified = authenticationManager.authenticate(pending);

// Nếu có session-based login, cơ chế custom phải gọi strategy thích hợp
// cho session fixation/concurrency trước khi hoàn tất đăng nhập.
sessionStrategy.onAuthentication(verified, request, response);

SecurityContext context = holderStrategy.createEmptyContext();
context.setAuthentication(verified);
holderStrategy.setContext(context);

// LƯU TRƯỚC khi response bị commit (trước redirect/body).
repository.saveContext(context, request, response);

// Sau đó mới thực hiện success response/redirect theo thiết kế.
```

**Không sao chép khung này thành API login tự chế** mà không tích hợp CSRF, exception/failure handler, session authentication strategy thực sự đúng, authentication events, rate limit, logout/remember-me, quản lý response và cleanup. Cơ chế sẵn có của Spring Security giải quyết nhiều góc khó; khi có thể, cấu hình `formLogin`/OAuth2/OIDC thay vì tự dựng toàn bộ.

### 6.4. Vì sao phải save trước khi trả redirect hoặc body?

Sau khi Servlet response đã **commit**, server có thể không còn khả năng thêm `Set-Cookie` cho session mới, đổi session ID hoặc lưu context theo cơ chế cần response wrapper. Nếu custom login chỉ gọi `saveContext` **sau** khi viết response/redirect, request tiếp theo có thể không tìm đúng session. Quy tắc triển khai là: hoàn tất authentication + session strategy + context setup + persistence **trước** khi commit response.

### 6.5. Tạo SecurityContext mới thay vì sửa context được chia sẻ

Trong custom authentication flow, nên dùng:

```java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);
SecurityContextHolder.setContext(fresh);
```

Tạo instance mới giúp tránh vô tình sửa một tham chiếu context có thể được chia sẻ qua session, một phần của hệ thống đang xử lý song song hoặc có vòng đời khác. Với authentication thành công chuẩn, filter của Spring Security thực hiện những bước tương ứng; snippet ở đây phục vụ hiểu trách nhiệm.

## 7. SessionAuthenticationStrategy xảy ra ở thời điểm nào?

`SessionAuthenticationStrategy` xử lý các mối quan tâm **khi một principal vừa được xác thực**, ví dụ đổi session ID để chống session fixation hoặc kiểm soát số session đồng thời. Trong Spring Security 6, authentication mechanism được kỳ vọng tự gọi strategy phù hợp; không nên trông đợi `SessionManagementFilter` mặc định phát hiện và chạy thay.

### 7.1. Session fixation protection

Nếu attacker có thể ép nạn nhân sử dụng một session ID đã biết trước login, attacker có cơ hội chiếm session khi nạn nhân đăng nhập. Spring Security Servlet thông thường đổi session ID khi login trên container hỗ trợ `HttpServletRequest.changeSessionId()`, giúp cắt khả năng tái sử dụng session ID trước xác thực.

```text
Trước login:  session ID = S1 (guest)
Login đúng:  xác thực Alice + session strategy đổi ID
Sau login:   session ID = S2 (authenticated)
              S1 không nên trở thành vé vào phiên Alice
```

Session fixation protection không thay cơ chế kiểm tra credential; nó bảo vệ **lifecycle session** sau khi authentication thành công. Với custom login controller, nếu chỉ gọi manager + save context mà quên strategy, hệ thống có thể thiếu phần bảo vệ này. Đừng tắt session fixation protection chỉ vì test thấy session ID thay đổi.

### 7.2. Concurrent session control

Một ứng dụng có thể giới hạn số phiên user đang dùng (ví dụ một phiên), vô hiệu phiên cũ hoặc từ chối login mới. Cần `SessionRegistry` và sự kiện lifecycle session/chiến lược tương ứng; đây là thiết kế **ngoài bản thân AuthenticationManager**. Tùy `maximumSessions`/`maxSessionsPreventsLogin`, login hợp lệ về password vẫn có thể bị từ chối ở chính sách session. Khi tự viết authentication filter, cần gọi đúng strategy và xử lý lỗi `SessionAuthenticationException` thích hợp.

### 7.3. Session policy IF_REQUIRED, NEVER, STATELESS

| Chính sách | Ý nghĩa vận hành chính |
| --- | --- |
| `SessionCreationPolicy.IF_REQUIRED` | Spring Security có thể tạo session khi thật sự cần, thường phù hợp form login |
| `SessionCreationPolicy.ALWAYS` | Chủ động tạo session theo cấu hình |
| `SessionCreationPolicy.NEVER` | Security không tự tạo session cho context nhưng có thể dùng session đã tồn tại; thành phần khác có thể tạo session |
| `SessionCreationPolicy.STATELESS` | Security không tạo/dùng session để khôi phục SecurityContext; phù hợp API credential từng request |

Khi dùng `STATELESS`, Spring Security thường cấu hình `NullSecurityContextRepository` cho việc khôi phục/ngăn lưu context vào session, đồng thời tránh dùng session để lưu request. Vì vậy **không được** kỳ vọng chỉ đổi `http.sessionManagement(...STATELESS)` rồi form login vẫn lưu user qua các request như ứng dụng session-based.

## 8. RequestCache, RememberMe và SecurityContextRepository khác nhau ra sao?

Ba cơ chế có thể cùng liên quan trong trải nghiệm “đăng nhập xong vẫn sử dụng ứng dụng”, nhưng mục đích khác nhau:

- **RequestCache** lưu URL/request định vào trước khi bị chặn; success handler có thể redirect để client gửi lại request. Không cấp quyền, không lưu principal.
- **SecurityContextRepository** lưu/khôi phục context chứa `Authentication` theo policy (request attribute/session/none). Đây là nơi trả lời “request sau biết ai đã đăng nhập bằng cách nào?”.
- **RememberMeServices** là cơ chế xác thực lại/truy cập tiếp theo qua cookie hoặc token remember-me theo cấu hình. Khi session hết, một remember-me token còn hợp lệ có thể giúp tái xác thực theo mức tin cậy khác; không đồng nghĩa giữ nguyên `SecurityContextHolder` mãi mãi.

Một trạng thái `remember-me authenticated` có thể không thỏa rule `fullyAuthenticated()`. Với thao tác nhạy cảm như đổi password, chuyển tiền, thay MFA, có thể cần step-up/re-authentication và policy mới. `getAuthentication().isAuthenticated()` đơn thuần chưa đủ cho mọi trường hợp, đặc biệt với anonymous authentication token có thể trả true.

## 9. Demo chạy được: Spring Boot form login + success handler + session repository

Demo này dùng **Java 17**, **Spring Boot 3.5.16**, **Spring Security 6.5.x** do Boot quản lý. Đây là bản cuối hỗ trợ OSS của dòng Boot 3.5 (phát hành năm 2026); khi tạo dự án production mới, hãy chọn dòng Boot đang được hỗ trợ và bản vá hiện hành, kiểm tra migration guide tương ứng.

Ứng dụng cố tình dùng **form login và HttpSession** vì chủ đề chính là lưu context qua nhiều request. Nếu bạn chỉ dùng API Basic/Bearer stateless, phải học cơ chế xác thực lại trên từng request như phần sau. Tài khoản và mật khẩu ví dụ chỉ dành cho môi trường local.

### 9.1. Cấu trúc tệp

```text
login-persistence-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/session/LoginPersistenceApplication.java
    └── test/
        └── java/demo/session/LoginPersistenceApplicationTests.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>login-persistence-demo</artifactId>
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
```

### 9.3. Ứng dụng hoàn chỉnh

Tạo `src/main/java/demo/session/LoginPersistenceApplication.java`:

```java
package demo.session;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginPersistenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginPersistenceApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    // Spring Security 6 thường có repository tương đương mặc định.
    // Khai báo ở đây để nhìn rõ vai trò của hai delegate.
    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    AuthenticationSuccessHandler loginSuccessHandler() {
        SavedRequestAwareAuthenticationSuccessHandler redirect =
            new SavedRequestAwareAuthenticationSuccessHandler();
        redirect.setDefaultTargetUrl("/me");

        return (request, response, authentication) -> {
            // Header minh họa callback, không phản hồi secret hoặc role.
            response.addHeader("X-Lab-Login-Processed", "1");
            redirect.onAuthenticationSuccess(
                request, response, authentication);
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            SecurityContextRepository repository,
            AuthenticationSuccessHandler loginSuccessHandler)
            throws Exception {

        return http
            .securityContext(securityContext ->
                securityContext.securityContextRepository(repository))
            .authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .formLogin(form -> form
                .successHandler(loginSuccessHandler)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .build();
    }
}

@RestController
class DemoRoutes {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }
}
```

**Vì sao các dòng trong demo quan trọng?**

1. `securityContextRepository()` tạo một `DelegatingSecurityContextRepository` với request-attribute và HTTP-session delegate, để thấy rõ cùng lúc **khôi phục trong request/error dispatch** và **khôi phục ở request HTTP sau**.
2. `.securityContext(...securityContextRepository(repository))` đặt repository vào security chain và các authentication filter có liên quan theo cấu hình Spring Security 6.
3. `IF_REQUIRED` cho phép session khi login cần. `sessionFixation(changeSessionId())` bảo vệ việc nâng một phiên anonymous lên authenticated.
4. `formLogin(...successHandler(...).permitAll())` bật cơ chế xử lý form login chuẩn. Filter của Spring Security chịu trách nhiệm authentication + context setup/persistence; handler chỉ thêm một header minh họa rồi nhờ `SavedRequestAwareAuthenticationSuccessHandler` redirect.
5. `redirect.setDefaultTargetUrl("/me")` chọn `/me` khi không có saved request; nếu người dùng trước đó yêu cầu một URL bảo vệ và request cache lưu URL đó, handler có thể trở về URL gốc.
6. `GET /public` mở, `GET /me` cần login, `GET /admin` cần ROLE_ADMIN. Đường còn lại bị `denyAll`, không mở vì đã có session.
7. `.logout(...)` dùng cơ chế logout sẵn có, nơi Spring Security xử lý invalidation/clear context. Khi CSRF bật, POST logout cần token hợp lệ.
8. User in-memory và mật khẩu mẫu chỉ dùng học tập; **không commit mật khẩu production** vào source. HTTP form login phải chạy qua **HTTPS** trên mạng thật.

### 9.4. Bộ integration test: chứng minh context được lưu qua request

Tạo `src/test/java/demo/session/LoginPersistenceApplicationTests.java`:

```java
package demo.session;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginSavesContextAndNextRequestRestoresIt() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(header().string(
                "X-Lab-Login-Processed", "1"))
            .andReturn();

        MockHttpSession resultingSession =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(resultingSession);

        // Đây là dữ liệu SESSION SERVER-SIDE, không phải cookie chứa user.
        Object saved = resultingSession.getAttribute(
            HttpSessionSecurityContextRepository
                .SPRING_SECURITY_CONTEXT_KEY);

        SecurityContext context =
            assertInstanceOf(SecurityContext.class, saved);

        assertNotNull(context.getAuthentication());
        assertEquals("alice", context.getAuthentication().getName());

        // MockMvc không tự mang session qua các request độc lập;
        // ta truyền đúng session để mô phỏng browser gửi cookie.
        mvc.perform(get("/me").session(resultingSession))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        // Request không có session được xác thực từ trước bị chuyển login.
        mvc.perform(get("/me").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void invalidPasswordNeverCreatesAuthenticatedSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

        mvc.perform(get("/me")
                .session(session)
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void adminAuthorizationStillAppliesAfterSessionRestored()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        MockHttpSession adminSession = new MockHttpSession();

        mvc.perform(post("/login")
                .session(adminSession)
                .with(csrf())
                .param("username", "admin")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void logoutInvalidatesSessionAndRemovesAuthentication()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Request mới không có session đã đăng nhập.
        mvc.perform(get("/me").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

**Điều test chứng minh:**

- Login dùng **username/password thật qua `UsernamePasswordAuthenticationFilter`** và `DaoAuthenticationProvider` do Spring Security thiết lập từ `UserDetailsService`; khác với `@WithMockUser` chỉ tạo principal giả lập.
- Session được lấy sau login và kiểm tra có `SPRING_SECURITY_CONTEXT` lưu `Authentication` của Alice. Điều này chứng minh **persistence** chứ không chỉ “request login nhận 302”.
- Request kế tiếp có **cùng session** đọc được Alice; request không session bị yêu cầu login. MockMvc truyền `MockHttpSession` giữa lời gọi để mô phỏng browser giữ session cookie.
- Custom `AuthenticationSuccessHandler` đã chạy vì response login có `X-Lab-Login-Processed: 1`, nhưng việc handler chạy **không thay thế** test context saved.
- Password sai không cấp session đã authenticated; role ADMIN vẫn kiểm soát request sau khi context khôi phục.
- Logout dùng filter hỗ trợ sẵn, invalidate session và không để một request khác tiếp tục dùng phiên cũ. Ở client browser thật còn phải kiểm chứng cookie/session behavior trên HTTP/TLS.
- Bài test dùng status/header/body ổn định thay vì assert toàn bộ list filter hoặc nội dung log; kết quả kỳ vọng còn phụ thuộc dependency/JDK/Maven được cài đặt phù hợp.

### 9.5. Chạy demo

Tại thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Khi chạy đúng, những test ở trên được kỳ vọng thành công. Bài này trình bày mã và assertion để học; không coi các kết quả dự kiến là bằng chứng đã chạy Maven trong môi trường hiện tại.

Trong browser, mở cửa sổ ẩn danh rồi truy cập:

```text
http://localhost:8080/public
http://localhost:8080/me
http://localhost:8080/admin
http://localhost:8080/login
```

- `/public` trả `public` mà không cần login.
- `/me` sẽ dẫn sang form login khi anonymous muốn HTML.
- Đăng nhập username `alice`, password `demo-pass`; sau login, trang `/me` trả `me:alice`.
- Đăng nhập `admin` ở phiên khác để thử `/admin` trả `admin-ok`. Alice không có ROLE_ADMIN nên bị từ chối.
- Dùng DevTools → Network để kiểm tra `POST /login` trả redirect, có thể có `Set-Cookie` cho session; request sau mang cookie và trả nội dung. Không chia sẻ ảnh/log chứa cookie session.

Với curl, **form login không tương đương HTTP Basic**. Để gửi `POST /login` bằng curl phải lấy/gửi CSRF token và cookie jar từ form/session; dùng browser và MockMvc để thực hành chính xác sẽ đơn giản hơn trong bài này. Nếu chỉ thử:

```bash
curl -i -H "Accept: text/html" http://localhost:8080/me
```

Bạn thường thấy redirect `302` tới `/login` mà không cần cookie. Đừng dùng `curl -L` rồi chỉ nhìn HTTP status cuối cùng của trang login (200) mà kết luận `/me` đã public.

**Production:** chạy HTTPS, thiết lập cookie Secure/HttpOnly/SameSite phù hợp, tránh ghi token/password/session ID vào URL hoặc log, và không dùng account mẫu.

## 10. Bằng chứng persistence qua trình duyệt là gì?

Hãy quan sát hai phiên độc lập:

### Trước đăng nhập

```text
GET /me                         -> 302 Location: /login
GET /login                      -> 200 trang form
Form có CSRF token theo cơ chế đang bật
```

### Khi đăng nhập thành công

```text
POST /login + credential đúng + CSRF token
  -> authentication provider trả result
  -> session strategy xử lý session
  -> context được gắn + lưu
  -> success handler redirect /me hoặc SavedRequest
Browser tiếp tục GET /me + Cookie session hiện tại
  -> repository load context
  -> AuthorizationFilter cho qua
  -> controller trả "me:alice"
```

### Khi mở một cửa sổ ẩn danh mới

```text
GET /me, không gửi session cookie cũ
  -> không khôi phục được Authentication của Alice
  -> lại được yêu cầu login
```

Điều này khác với **Browser Refresh** trong cùng phiên đã login: trình duyệt tự gửi cookie nên user vẫn được xác thực. Khi xem DevTools, không in ra secret cookie trong báo cáo; ghi trạng thái có/không có cookie là đủ. Với session ID, cần bảo vệ trước fixation và theft, rotate/invalidate theo policy.

## 11. Stateless: tại sao không cần lưu context vào session?

Một API dùng HTTP Basic hoặc Bearer token thường xác thực **ở từng request**. Ví dụ:

```text
GET /api/me
Authorization: Bearer <token hợp lệ>
      |
      v
BearerTokenAuthenticationFilter
      |
      v
JwtDecoder / AuthenticationManager / trust validation
      |
      v
Authentication trong SecurityContext cho request này
      |
      v
Controller đọc principal
      |
      v
Request kết thúc; holder được dọn
```

Request tiếp theo phải lại mang credential phù hợp. Với Spring Security Servlet:

```java
// Snippet của SecurityFilterChain builder cho API stateless.
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

Cấu hình đó có thể dẫn đến `NullSecurityContextRepository` theo mặc định cho mục tiêu không dùng session. **Không nên** ép flow này lưu đầy đủ token/authentication vào server session nếu threat model và kiến trúc API đã chọn stateless. Nếu cần lưu session có chủ đích cho một cơ chế vốn stateless, phải cấu hình repository của chính authentication filter và kiểm chứng behavior, thay vì giả định tính chất tự động.

Đối với JWT Resource Server, trước khi kết luận “login thành công”, còn phải kiểm tra chữ ký/thuật toán, issuer/audience, thời hạn và ánh xạ authorities đúng. Success handler dành cho form login **không tự chạy** sau mỗi request Bearer token; các filter có lifecycle khác nhau. Không copy handler/session strategy từ form login sang JWT nếu không có lý do.

## 12. Logout: trách nhiệm xóa ngữ cảnh cũng quan trọng như lưu

Nếu context đã được lưu ở session, “đăng xuất” phải làm cho session không còn cấp quyền. Trong Spring Security, `LogoutFilter` và `SecurityContextLogoutHandler` thường giúp:

- Invalidate HTTP session theo cấu hình.
- Xóa authentication khỏi `SecurityContextHolderStrategy`.
- Xóa context trong `SecurityContextRepository`.
- Xử lý remember-me/CSRF token và logout event nếu cơ chế đó được cấu hình.
- Sau đó chạy `LogoutSuccessHandler` hoặc redirect theo URL logout success.

Với CSRF protection bật, `POST /logout` thường yêu cầu CSRF token; `GET /logout` có thể hiển thị trang xác nhận. Không coi một GET đơn lẻ luôn là thao tác logout hoàn tất.

**Lỗi nguy hiểm của custom logout:**

```java
// Chỉ clear holder ở request hiện tại là CHƯA ĐỦ nếu session có context.
SecurityContextHolder.clearContext();
response.sendRedirect("/login");
```

Nếu session vẫn giữ authentication, request tiếp theo có thể nạp lại context và user vẫn được coi đã login. Nên dùng logout support sẵn hoặc thực hiện đầy đủ invalidate/clear repository/remember-me với đúng lifecycle, trước khi commit response.

Lưu ý với SSO/OIDC: “logout khỏi ứng dụng local” và “logout khỏi Identity Provider” là hai thao tác có thể khác nhau; khi có yêu cầu logout liên hệ IdP cần thực hiện đúng protocol, state và redirect policy tương ứng.

## 13. Những lỗi triển khai thường gặp

### 13.1. SuccessHandler trả JSON/redirect trước khi save context

**Triệu chứng:** POST /login trả success nhưng request sau bị 401 hoặc quay về /login.

**Nguyên nhân:** custom controller/login filter không gọi repository `saveContext` hoặc gọi quá muộn sau khi response đã commit.

**Sửa:** dùng authentication filter hỗ trợ sẵn khi có thể; nếu custom, hoàn thành session strategy + holder + `saveContext` **trước** response, test bằng request thứ hai có cùng cookie/session.

### 13.2. Tưởng AuthenticationManager tự đăng nhập cho browser

**Triệu chứng:** Test service gọi `authenticate()` nhận authenticated result; trình duyệt vẫn không có session.

**Nguyên nhân:** manager chỉ xác minh credential. Không có filter/controller nào gắn và lưu result trong security context để request tiếp theo tìm thấy.

**Sửa:** dùng form login/OIDC chuẩn hoặc custom flow đã được thiết kế đầy đủ. Test cả authentication và persistence/redirect.

### 13.3. Chỉ setContext, không saveContext

**Triệu chứng:** Ngay trong POST /login có thể đọc username, nhưng sau redirect request mới mất identity.

**Nguyên nhân:** `SecurityContextHolderFilter` mặc định Spring Security 6 không tự lưu thay đổi.

**Sửa:** dùng repository có khả năng lưu và gọi `saveContext(context, request, response)` cho custom login; xác minh repo của filter và repo của code custom **là cùng cơ chế phù hợp**.

### 13.4. Tưởng RequestCache chính là SecurityContextRepository

**Triệu chứng:** Sau login redirect đúng URL cũ nhưng vẫn bị yêu cầu login, hoặc login giữ được nhưng không về trang cũ.

**Nguyên nhân:** Hai cơ chế được điều khiển độc lập. RequestCache chỉ nhớ URL; repository mới giữ danh tính giữa requests.

**Sửa:** test riêng saved URL, test riêng authenticated session; kiểm tra session cookie, URL redirect và authorization.

### 13.5. Cấu hình STATELESS cho web app cần session

**Triệu chứng:** Form login thành công ở POST nhưng mọi GET sau vẫn anonymous.

**Nguyên nhân:** App dùng `SessionCreationPolicy.STATELESS`/`NullSecurityContextRepository` nên không persist context qua HTTP session.

**Sửa:** chọn policy phù hợp: session login dùng IF_REQUIRED/session repo; Bearer API dùng stateless và token ở từng request. Nếu có hai khu vực, có thể dùng chain riêng với matcher/fallback được kiểm soát.

### 13.6. Quên session fixation protection ở custom login

**Triệu chứng:** Session ID không đổi khi anonymous nâng thành authenticated, kẻ nắm ID cũ có nguy cơ chiếm phiên.

**Nguyên nhân:** Bỏ qua `SessionAuthenticationStrategy` hoặc tắt protection.

**Sửa:** để framework xử lý hoặc gọi đúng strategy; test ID rotation và xử lý session expiry/concurrent sessions theo yêu cầu.

### 13.7. Chỉ dựa vào success redirect để khẳng định user có quyền

**Triệu chứng:** Alice login được rồi truy cập report của Bob do backend chỉ kiểm tra authenticated.

**Nguyên nhân:** Login success và object authorization khác nhau. SuccessHandler không tự kiểm tra owner/tenant/resource.

**Sửa:** service/repository áp policy actor + action + resource + tenant/state. Test user A vào tài nguyên B, kể cả khi session A hợp lệ.

### 13.8. Lộ dữ liệu qua log trong success handler

**Triệu chứng:** Log lưu cả `Authentication`, password, refresh token, cookie hoặc claims nhạy cảm.

**Nguyên nhân:** Dùng `toString()` không kiểm soát hoặc log header/form đầy đủ khi debug.

**Sửa:** log user ID ổn định, thời gian, correlation ID và outcome theo mức tối thiểu; che secret, phân quyền truy cập audit và giới hạn retention. Không đưa session ID vào URL.

### 13.9. Tự redirect theo returnUrl từ client

**Triệu chứng:** Sau login, server redirect sang URL ngoài domain do attacker chỉ định.

**Nguyên nhân:** `AuthenticationSuccessHandler` lấy `returnUrl` từ query/cookie mà không giới hạn origin/path.

**Sửa:** dùng `SavedRequestAwareAuthenticationSuccessHandler` hoặc allowlist/same-origin validation với URL đích; tránh open redirect/phishing.

### 13.10. Dùng @WithMockUser để kết luận session login thật đã đúng

**Triệu chứng:** Test MockMvc được 200 với mock user, nhưng POST /login thực không lưu session.

**Nguyên nhân:** `@WithMockUser` tạo authentication giả lập **trước request**; nó không xác minh password hoặc đi qua login success handler.

**Sửa:** viết test **POST /login + CSRF + credential** rồi dùng session trả về trong **GET kế tiếp**, kiểm tra cả failure/logout.

### 13.11. Dùng @Async/ThreadLocal rồi tưởng context tự truyền

**Triệu chứng:** SuccessHandler chạy trong request thấy user, nhưng async task background không thấy hoặc thấy sai user.

**Nguyên nhân:** Servlet `SecurityContextHolder` mặc định dựa trên ThreadLocal; thread pool không tự kế thừa một cách an toàn.

**Sửa:** dùng các wrapper `DelegatingSecurityContextExecutor` phù hợp hoặc truyền actor ID đã xác thực tới task. Với job chạy trễ cần kiểm tra lại quyền/expiry, không giữ raw credential.

### 13.12. Quên xóa repository khi logout

**Triệu chứng:** Người dùng logout, redirect tới /login nhưng refresh trang cũ vẫn được vào.

**Nguyên nhân:** Chỉ clear ThreadLocal, session vẫn có authenticated context.

**Sửa:** dùng Spring Security logout handler, invalidate session và xóa repository/remember-me theo cấu hình. Test request tiếp theo sau logout.

## 14. Ma trận test nên có khi đưa login vào sản phẩm

| Tình huống | Điều cần kiểm tra | Công cụ |
| --- | --- | --- |
| Anonymous mở route private | 302 tới login hoặc 401 tùy client/entry point | Browser + MockMvc |
| Đúng username/password và CSRF | Login thành công; handler chạy | MockMvc POST /login |
| Sau login, request **cùng session** | Context được khôi phục; GET /me trả 200 | MockMvc 2 requests |
| Request mới **không session** | Không thừa hưởng identity user trước | MockMvc/bộ test integration |
| Sai password | Failure handler, không có authenticated context | MockMvc |
| User login hợp lệ, sai role | 403; login không thay authorization | MockMvc |
| Session fixation | Session ID được đổi khi login theo policy | MockMvc/brower integration |
| SavedRequest được ghi | Redirect đến URL hợp lệ ban đầu | Browser + MockMvc |
| Không có SavedRequest | Redirect URL mặc định | MockMvc |
| POST /logout có CSRF đúng | Session invalid, context được xóa | MockMvc |
| POST /logout thiếu CSRF | Không logout tùy CSRF policy | MockMvc |
| Session expired/invalid | Bị yêu cầu login/response đã cấu hình | Integration test |
| Concurrent logins | Giới hạn hoặc chiến lược được thực thi | Multi-session tests |
| Cookie Secure/HttpOnly/SameSite | Cờ cookie ở HTTPS thật | Browser/HTTP integration |
| Đăng nhập qua reverse proxy | Redirect scheme/host chính xác | Staging |
| Chỉ đổi thông tin user/role trong DB | Quyền ở session cache được cập nhật/thu hồi đúng policy | Domain/security tests |

Nếu có MFA/step-up authentication, login success ban đầu **không nhất thiết** là hoàn tất đăng nhập có quyền cao. Cần biểu diễn trạng thái challenge, không cấp authority nhạy cảm trước khi bước MFA được xác minh; sau khi hoàn tất, cập nhật authentication/session đúng cơ chế và tránh fixation/privilege escalation.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `authenticationManager.authenticate(...)` nhận token thành công. Tại sao GET /me ở request sau vẫn chuyển tới login?

**Đáp án:** Manager chỉ trả authentication đã xác minh. Custom flow có thể chưa đặt result vào context hoặc chưa gọi `SecurityContextRepository.saveContext(...)` trước response. Cần test cả login và request sau.

**Câu 2.** `AuthenticationSuccessHandler` có phải thành phần chịu trách nhiệm lưu toàn bộ SecurityContext vào session?

**Đáp án:** Không phải hợp đồng chính của nó. Handler quyết định response/redirect sau login. Authentication filter chuẩn quản lý context/persistence theo cấu hình; custom controller phải tự tích hợp repository và các chiến lược cần thiết.

**Câu 3.** `SecurityContextHolderFilter` của Spring Security 6 có tự lưu mọi `setContext(...)` không?

**Đáp án:** Không. Nó nạp context và quản lý phạm vi current context; muốn lưu thay đổi qua request bằng custom flow phải gọi repository `saveContext(...)`. Filter xác thực chuẩn có xử lý phù hợp.

**Câu 4.** `RequestCache` lưu URL /admin trước login. Có nghĩa user được tự động cấp ROLE_ADMIN sau login?

**Đáp án:** Không. Saved request chỉ giúp redirect. Authorization ở request sau vẫn kiểm tra role và resource. User thiếu role có thể được redirect đúng URL nhưng vẫn nhận 403.

**Câu 5.** Khi dùng `SessionCreationPolicy.STATELESS`, giữ session cookie từ lần trước có khiến Spring Security khôi phục Alice?

**Đáp án:** Không theo policy stateless thông thường: không dùng session để nạp context. Request cần credential riêng (ví dụ bearer token) theo cơ chế xác thực cấu hình.

**Câu 6.** Vì sao session ID thường thay đổi khi login thành công?

**Đáp án:** Bảo vệ trước session fixation: kẻ biết một session ID trước login không được tiếp tục dùng ID đó như phiên đã xác thực. `SessionAuthenticationStrategy` chịu trách nhiệm điều phối.

**Câu 7.** Sau logout, chỉ gọi `SecurityContextHolder.clearContext()` rồi redirect có đủ không?

**Đáp án:** Không nếu repository/session vẫn chứa authenticated context. Phải xóa/invalidate repository/session và xử lý remember-me theo cơ chế logout thích hợp.

**Câu 8.** MockMvc test có `@WithMockUser` được 200 có chứng minh login form lưu session không?

**Đáp án:** Không. Test tạo principal giả, bỏ qua POST /login và success/persistence. Cần test liên tiếp POST login hợp lệ và GET private bằng cùng session.

## 16. Checklist triển khai có thể dùng khi review PR

- [ ] Cơ chế login là form, Basic, Bearer, OIDC hay custom? Có dùng đúng filter/manager/provider của cơ chế đó?
- [ ] Xác thực credential/claim được thực hiện bởi nguồn tin cậy, không lấy role từ client?
- [ ] Sau thành công, có `SessionAuthenticationStrategy` phù hợp với session fixation/concurrency nếu dùng session?
- [ ] `SecurityContextHolderStrategy` được set trong request hiện tại và dọn đúng vòng đời?
- [ ] Với custom login cần persist, `SecurityContextRepository.saveContext` được gọi **trước khi response commit**?
- [ ] Repository trong filter chain và custom code có cùng semantics, tránh lưu vào một nơi và đọc từ nơi khác?
- [ ] Có tách `RequestCache` và `AuthenticationSuccessHandler` khỏi cơ chế lưu authentication?
- [ ] Redirect chỉ về URL được cho phép, không mở open redirect từ `returnUrl`?
- [ ] Browser cần session thì dùng IF_REQUIRED/HttpSession repository; API stateless thì dùng token mỗi request?
- [ ] Session cookie có Secure/HttpOnly/SameSite hợp lý, HTTPS, expiry và rotation?
- [ ] Login sai không tạo authenticated context, không thông báo quá mức về username tồn tại?
- [ ] Logout invalidate session/clear repository/remember-me; POST logout có CSRF policy đúng?
- [ ] Test HTTP thực qua security chain gồm 2 request cùng session, 1 request không session, failure, role và logout?
- [ ] Không xuất secret trong response, log, trace, URL hoặc test fixture chia sẻ?
- [ ] Domain service vẫn kiểm tra owner/tenant/ACL khi xử lý dữ liệu, không dừng ở login success?

## 17. Ghi nhớ

1. **AuthenticationManager trả kết quả xác thực**, không tự tạo session, redirect hay lưu context vào holder khi được gọi trực tiếp.
2. **AuthenticationSuccessHandler điều khiển phản hồi thành công**, có thể dùng `SavedRequestAwareAuthenticationSuccessHandler` để trở về URL ban đầu.
3. **SecurityContextHolder là ngữ cảnh hiện tại; SecurityContextRepository là cơ chế lưu/khôi phục qua request.** `RequestCache` là kho URL/request, không phải kho identity.
4. **Spring Security 6 ưu tiên explicit save.** `SecurityContextHolderFilter` không tự lưu mọi thay đổi; built-in filters lo phần persistence tương ứng, custom login cần `saveContext` rõ ràng.
5. **SessionAuthenticationStrategy xử lý các chính sách sau login** như session fixation/concurrent sessions; custom flow phải tính đến nó.
6. **Session-based và stateless có vòng đời khác nhau.** Form login thường duy trì context qua HttpSession; HTTP Basic/Bearer stateless xác thực lại trên từng request.
7. **Logout phải xóa cả context đã lưu**, không chỉ clear current holder; authorization theo resource vẫn cần sau mỗi lần khôi phục session.

## Tài liệu chính thức

- [Spring Security 6.5 — Form Login, luồng authentication success](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence Migration / Explicit Save](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — Logout Lifecycle](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 release, 25/06/2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
