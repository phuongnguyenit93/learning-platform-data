# AuthorityReactiveAuthorizationManager và kiểm tra role, authority

## 1. Mục tiêu của bài học

Trong ứng dụng **Spring WebFlux**, Spring Security cần quyết định request nào được phép đi tiếp dựa trên danh tính đã xác thực và các `GrantedAuthority` của người gọi. `AuthorityReactiveAuthorizationManager<T>` là một implementation sẵn có của `ReactiveAuthorizationManager<T>`, chuyên kiểm tra rằng `Authentication` có một hoặc nhiều authority được yêu cầu.

Sau bài này, bạn có thể:
- Phân biệt **role** với **authority** và hiểu prefix mặc định `ROLE_`.
- Chọn đúng `hasAuthority(...)`, `hasAnyAuthority(...)`, `hasRole(...)` và `hasAnyRole(...)`.
- Gắn các rule vào `ServerHttpSecurity.authorizeExchange(...)` và `SecurityWebFilterChain` của WebFlux.
- Hiểu `Mono<Authentication>`, authorization result, khác biệt API Spring Security 6.5 và 7.x.
- Kiểm tra authorities được tạo từ UserDetails, JWT scope hoặc converter, không nhầm claim với authority đã được mapping.
- Phối hợp HTTP authorization với reactive method security, tenant và object-level authorization.
- Tránh nhầm **OR của hasAny** thành **AND**, nhầm role của tenant A thành role toàn cục, và vô tình cho phép route không được bảo vệ.
- Kiểm thử bằng ma trận authority và WebTestClient; nhận biết lỗi 401/403 và những trường hợp chưa có authentication.

Bối cảnh cha là **HTTP trên WebFlux**: đây không phải hướng dẫn dành cho Spring MVC/Servlet. Các tên cần phân biệt:
- WebFlux: `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange`, `ReactiveAuthorizationManager`, `Mono`.
- Servlet: `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests`, `AuthorizationManager`, `Supplier<Authentication>`.

Dùng nhầm API Servlet trong cấu hình WebFlux thường dẫn đến lỗi compile hoặc một filter chain không bảo vệ đúng web stack.

## 2. AuthorityReactiveAuthorizationManager làm gì?

Tên class đầy đủ:

~~~text
org.springframework.security.authorization.AuthorityReactiveAuthorizationManager<T>
~~~

Nó triển khai:

~~~text
org.springframework.security.authorization.ReactiveAuthorizationManager<T>
~~~

Về mặt khái niệm, manager nhận **một luồng authentication** và **một đối tượng đang được authorize**:

~~~text
Mono<Authentication> ───────┐
                             ├── AuthorityReactiveAuthorizationManager
T securedObject ────────────┘            │
                                         v
                           AuthorizationResult / Decision
                                ALLOW hoặc DENY
~~~

Manager đọc tập `Authentication.getAuthorities()` rồi kiểm tra những authority được chỉ định. Nó **không tự**:
- Xác thực mật khẩu hoặc chữ ký JWT.
- Đọc database owner/ACL của một document theo ID.
- Chứng minh role có hiệu lực trong tenant đang truy cập.
- Kiểm tra dữ liệu body, số dư, trạng thái khóa, deadline nghiệp vụ.
- Đưa ra quyết định dựa trên nội dung của `T object` nếu chỉ dùng các factory authority có sẵn.

Điểm mạnh là kiểm tra **quyền chức năng/coarse-grained** nhanh và rõ. Khi rule còn phụ thuộc object hoặc ngữ cảnh, cần một custom `ReactiveAuthorizationManager`/service policy hoặc truy vấn có scope.

### Mối quan hệ với reactive execution

Trong WebFlux, authorization được kết hợp với Reactor publishers. `Mono<Authentication>` biểu diễn authentication có thể chưa được lấy ra ngay khi lắp pipeline; framework quyết định subscribe/evaluate theo request.

Đừng tự gọi `block()` trong Netty event loop để lấy authentication hay chờ ACL service. Nếu kiểm tra quyền cần I/O, phối hợp bằng `Mono`/`Flux`, bounded client timeout và cơ chế fail-closed phù hợp.

## 3. GrantedAuthority, role và tên chuỗi thực tế

`Authentication` chứa tập `Collection<? extends GrantedAuthority>`; mỗi `GrantedAuthority` thường trả về chuỗi từ `getAuthority()`.

Ví dụ dữ liệu:

~~~text
Authentication.getAuthorities() =
  "ROLE_ADMIN"
  "SCOPE_documents.read"
  "documents:write"
~~~

Cần đọc đúng từng chuỗi. `AuthorityReactiveAuthorizationManager.hasAuthority("documents:write")` tìm **đúng** `documents:write`. Nó không tự thêm prefix hoặc tự dịch sang `ROLE_...`.

Một **role** trong Spring Security thường được biểu diễn như một authority có prefix `ROLE_`. Ví dụ `ADMIN` là tên role dễ đọc, còn chuỗi authority thực có thể là `ROLE_ADMIN`.

Bảng diễn giải:

| Cách gọi | Authority được yêu cầu | Khi nào phù hợp? |
|---|---|---|
| `hasAuthority("ROLE_ADMIN")` | Chính xác `ROLE_ADMIN` | Khi bạn biết chuỗi role đã được ánh xạ đầy đủ |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Khi dùng quy ước role mặc định |
| `hasAuthority("ADMIN")` | Chính xác `ADMIN` | Chỉ khi thực sự đã cấp authority `ADMIN` |
| `hasAuthority("SCOPE_documents.read")` | Chính xác `SCOPE_documents.read` | JWT resource server map OAuth scope như vậy |
| `hasAuthority("documents:write")` | Chính xác `documents:write` | Authority nghiệp vụ được cấp nguyên văn |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | Khi user/issuer converter tạo role đúng |

**Quan trọng:** `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` thường kiểm tra cùng authority; `hasAuthority("ADMIN")` là điều kiện khác.

Với chính class `AuthorityReactiveAuthorizationManager`, Javadoc mô tả `hasRole` sẽ thêm prefix **`ROLE_`**; tránh giả định một bean cấu hình role prefix dùng cho method expression sẽ tự đổi hành vi static factory này. Nếu triển khai dùng naming khác, hãy dùng `hasAuthority("TENANT_ADMIN")` hoặc xây custom manager có convention được test.

## 4. Bốn factory static chủ đạo

Trong Spring Security 6.5 và 7.x, các factory được tài liệu hóa:

~~~java
AuthorityReactiveAuthorizationManager.hasAuthority("documents:read");
AuthorityReactiveAuthorizationManager.hasAnyAuthority(
        "documents:read", "documents:write");
AuthorityReactiveAuthorizationManager.hasRole("ADMIN");
AuthorityReactiveAuthorizationManager.hasAnyRole("ADMIN", "SUPPORT");
~~~

**Đây là snippet tạo manager**, không phải file Java độc lập: cần Spring Security classes, imports và bối cảnh generic `T` cụ thể.

| Factory | Điều kiện | Quan hệ logic |
|---|---|---|
| `hasAuthority(a)` | Actor có authority chính xác `a` | Một điều kiện |
| `hasAnyAuthority(a,b,...)` | Actor có **ít nhất một** authority trong tập | OR |
| `hasRole(r)` | Actor có `ROLE_r` | Một điều kiện với prefix |
| `hasAnyRole(r1,r2,...)` | Actor có ít nhất một `ROLE_r*` | OR |

**Không có nghĩa “any” là tất cả.**

Ví dụ actor chỉ có `documents:read`:
- `hasAnyAuthority("documents:read","documents:write")` → ALLOW.
- Yêu cầu **đồng thời** read và write → actor này phải bị DENY.

Nếu policy cần **AND**, không dùng `hasAnyAuthority` để thay thế. Bạn có thể tách coarse HTTP gate + kiểm tra bổ sung ở method service, hoặc dùng custom reactive manager có contract xác định. Trong một số phiên bản Spring Security mới có thêm manager cho all-of authorities, nhưng **không giả định nó tồn tại trên mọi version** của chính class `AuthorityReactiveAuthorizationManager`.

### Thứ tự và phân biệt chữ hoa/chữ thường

Các authority là chuỗi; đừng kỳ vọng `ROLE_admin` tự tương đương `ROLE_ADMIN`. Không tự uppercase client input để cấp quyền nếu policy chưa định nghĩa normalization. Role/authority nên xuất phát từ identity mapping đáng tin, có naming convention nhất quán và test chính xác cả chữ hoa/chữ thường.

## 5. Ma trận so khớp role/authority cơ bản

Giả sử có các authentication sau:

| Principal | Các GrantedAuthority |
|---|---|
| An | `ROLE_ADMIN`, `documents:read` |
| Bình | `ROLE_EDITOR`, `documents:write` |
| Chi | `ROLE_VIEWER`, `SCOPE_documents.read` |
| Dung | `ADMIN` (không có `ROLE_`) |
| Khách chưa xác thực | Không có authentication hợp lệ |

Kết quả mong muốn:

| Policy | An | Bình | Chi | Dung |
|---|---:|---:|---:|---:|
| `hasRole("ADMIN")` | ALLOW | DENY | DENY | DENY |
| `hasAuthority("ROLE_ADMIN")` | ALLOW | DENY | DENY | DENY |
| `hasAuthority("ADMIN")` | DENY | DENY | DENY | ALLOW |
| `hasAnyRole("ADMIN","EDITOR")` | ALLOW | ALLOW | DENY | DENY |
| `hasAuthority("documents:write")` | DENY | ALLOW | DENY | DENY |
| `hasAnyAuthority("documents:read","SCOPE_documents.read")` | ALLOW | DENY | ALLOW | DENY |

Ma trận cho thấy **authority thực tế quan trọng hơn tên gọi “admin” trong dữ liệu khác**. Chỉ đặt claim `role: ADMIN` trong JWT chưa đảm bảo Spring tạo `ROLE_ADMIN`. Auth converter/UserDetails phải chuyển claim thành `GrantedAuthority` phù hợp.

Trong HTTP stack, authentication chưa xác thực thường bị authentication entry point xử lý bằng 401/challenge hoặc redirect. Đừng coi một hàng “khách chưa xác thực” đơn giản tương đương authentication rỗng được tạo thủ công với authority tùy ý.

## 6. Khác biệt phiên bản: check và authorize

Đây là phần dễ tạo lỗi compile khi học bằng ví dụ cũ.

### Spring Security 6.5

Javadoc Spring Security 6.5 cho `AuthorityReactiveAuthorizationManager<T>` liệt kê:

~~~java
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication, T object);
~~~

Trong `ReactiveAuthorizationManager<T>` 6.5, `check(...)` đã được đánh dấu deprecated; `authorize(...)` là phương thức **default** giới thiệu từ 6.4, trả `Mono<AuthorizationResult>`. Nhưng class cụ thể 6.5 vẫn triển khai `check(...)`; vì vậy không được tưởng `check` đã bị loại khỏi 6.5.

### Spring Security 7.x

Javadoc Spring Security 7.1 liệt kê:

~~~java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);
~~~

Ở interface 7.x, `authorize(...)` là method cần hiện thực; `check(...)` không còn nằm trong API Javadoc hiện hành. Code gọi `manager.check(...)` từ blog hoặc tài liệu cũ có thể **không compile** trên 7.x.

| Nội dung | 6.5 | 7.x |
|---|---|---|
| Interface | `ReactiveAuthorizationManager<T>` | `ReactiveAuthorizationManager<T>` |
| Contract chính | `check` abstract/deprecated, `authorize` default | `authorize` abstract |
| Kết quả class cụ thể | `Mono<AuthorizationDecision>` từ `check` | `Mono<AuthorizationResult>` từ `authorize` |
| `hasRole/hasAuthority` static factories | Có | Có |
| `verify(...)` | Có | Có |

**Không nhầm reactive với nonreactive:** Servlet `AuthorizationManager<T>` nhận `Supplier<Authentication>`, còn reactive nhận `Mono<Authentication>`. Không copy class hoặc method signature giữa hai thế giới.

Tài liệu tham khảo phiên bản:
- [AuthorityReactiveAuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html).
- [ReactiveAuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html).
- [AuthorityReactiveAuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html).
- [ReactiveAuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html).

**Quy tắc khi nâng cấp:** kiểm tra dependency Spring Security đang chạy, không suy luận version từ Java 17 hay phiên bản Spring Boot không xác minh; biên dịch/test custom manager và các lệnh `.check/.authorize` theo version cụ thể.

## 7. Mono<AuthorizationResult> và semantics của DENY/empty

Một reactive authorization publisher có những tình huống khác nhau:

~~~text
Mono.just(AuthorizationResult granted)  -> ALLOW
Mono.just(AuthorizationResult denied)   -> DENY
Mono.empty()                            -> no decision / abstain
Mono.error(...)                         -> evaluation error
~~~

Ở Spring Security 6.5, signature cũ còn dùng `AuthorizationDecision`; class này thể hiện kết quả qua `isGranted()`. Spring Security 7.x dùng `AuthorizationResult` cho method chính, với property `isGranted()`.

**Một Mono trống không tự nghĩa là ALLOW.** Javadoc ghi nó biểu thị không tạo được quyết định. Với chính sách bắt buộc, cần thiết kế composition/adapter để no-decision **không mở quyền**. Tương tự, timeout đến remote policy backend không phải lý do để cho phép.

Method `verify(...)` của `ReactiveAuthorizationManager` mô tả contract: publisher hoàn tất bình thường khi quyền được cấp và phát lỗi khi bị từ chối. Nhưng nếu custom manager có semantics abstain, không nên viết một PEP tự tạo mặc định `true` khi kết quả trống.

Một đoạn dùng API 7.x để chủ động đánh giá (snippet tích hợp):

~~~java
Mono<AuthorizationResult> result =
        AuthorityReactiveAuthorizationManager
            .<String>hasAuthority("documents:read")
            .authorize(authenticationMono, "document:42");
~~~

Ở đây `"document:42"` chỉ là secured object generic minh họa; factory authority **không đọc owner của document từ string ấy**. Muốn authorization trên document thật cần custom policy ngoài check authority đơn thuần.

## 8. WebFlux SecurityWebFilterChain: ví dụ chuẩn theo route

Một cấu hình Spring WebFlux sử dụng HTTP Basic **chỉ để minh họa việc cấp role/authority**:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class WebFluxSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyAuthority("SCOPE_reports.read", "ROLE_AUDITOR")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .build();
    }
}
~~~

Đây là một **class cấu hình Spring**; để chạy cần Spring Boot WebFlux + Spring Security dependencies, Authentication user store/provider, controllers và cấu hình phù hợp. Không phải một chương trình chỉ chạy bằng `javac`.

Giải thích:
1. `ServerHttpSecurity` cấu hình WebFlux HTTP security.
2. `SecurityWebFilterChain` là WebFlux filter chain; khác `SecurityFilterChain` của Servlet.
3. `authorizeExchange(...)` định nghĩa các matcher theo thứ tự.
4. Public được permit trước những rule riêng.
5. GET reports cần **một trong hai** authority: scope READ hoặc role AUDITOR.
6. POST reports cần đúng `SCOPE_reports.write`.
7. Mọi đường admin cần authority `ROLE_ADMIN` do `hasRole("ADMIN")` thêm prefix.
8. Những exchange còn lại bị từ chối theo `denyAll`, hạn chế route mới mở nhầm.
9. `httpBasic(withDefaults())` là một cách xác thực demo; không tự động tạo user hoặc JWT.

**Cảnh báo CSRF:** WebFlux Spring Security thường bật CSRF protection theo cấu hình phù hợp. Với request POST dùng HTTP Basic/session/browser, POST có thể bị 403 do thiếu CSRF token **dù authority đúng**. Không tắt CSRF bừa bãi chỉ để test nhanh; nếu ứng dụng là stateless bearer-token API, cần threat model riêng và cấu hình CSRF theo kiến trúc.

### Matchers quyết định trước, authorities quyết định sau

Rule chỉ được dùng khi request khớp matcher. Một `GET /api/reports/3` đi vào GET reports; nó không tiếp tục thử rule admin sau khi bị deny bởi GET rule.

Thứ tự quan trọng. Nếu viết:
~~~java
.authorizeExchange(ex -> ex
    .anyExchange().authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
)
~~~

đây là cấu hình **sai ý định** vì fallback broad matcher xuất hiện trước; tùy phiên bản DSL có thể chặn ngay cấu hình/không cho thêm matcher sau anyExchange. Hãy đặt rule đặc thù trước fallback, với `denyAll` hoặc authenticated fallback được lựa chọn có chủ đích.

## 9. Path matcher, method matcher và thứ tự áp dụng

Giả sử:

~~~text
GET    /api/reports/5         -> cần read scope hoặc auditor
POST   /api/reports/5         -> cần write scope
DELETE /api/reports/5         -> denyAll nếu không có rule
GET    /api/admin/status      -> cần ROLE_ADMIN
GET    /public/version        -> permitAll
~~~

Điều này giúp tránh một lỗi phổ biến: dùng `.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")` cho **mọi method**, khiến POST/DELETE cũng chỉ cần READ scope.

Với WebFlux, có thể kết hợp `pathMatchers(HttpMethod.GET,...)`, `pathMatchers(HttpMethod.POST,...)` và các matcher bổ sung. Đừng xem URL path đủ để mô tả action nếu API có nhiều HTTP method.

**Ranh giới resource:** `hasAuthority("SCOPE_reports.read")` chỉ kiểm tra authority chức năng; nó **không kiểm tra report #5 thuộc tenant nào**. Service và repository vẫn phải áp predicate ID + tenant + owner/ACL trong data access.

### Khi viết nhiều SecurityWebFilterChain

Trong WebFlux có thể có nhiều chain với `securityMatcher(...)` và order ưu tiên. Mỗi request được chọn vào chain phù hợp, không nhất thiết toàn bộ rules nằm cùng một chain. Cần test chính xác:
- Public và protected paths.
- Actuator/internal endpoints.
- Paths gần giống nhau, trailing slash, encoded paths.
- Authentication khác nhau giữa route nếu có nhiều chain.
- Default rule của mỗi chain.

Đừng vô tình thêm một chain có matcher rộng và `permitAll` trước chain riêng cho API nhạy cảm.

## 10. Tạo GrantedAuthority từ in-memory user trong demo

Với HTTP Basic demo, Spring Security có thể lấy authentication từ `ReactiveUserDetailsService`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;

@Configuration
public class DemoUsersConfiguration {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo-password")
                .roles("ADMIN")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password("{noop}demo-password")
                .authorities("ROLE_AUDITOR", "SCOPE_reports.read")
                .build();

        UserDetails writer = User.withUsername("writer")
                .password("{noop}demo-password")
                .authorities("SCOPE_reports.write")
                .build();

        return new MapReactiveUserDetailsService(admin, auditor, writer);
    }
}
~~~

**Chỉ dành cho local/demo:** `{noop}` là password encoder không băm mật khẩu, **không dùng cho production**. Dùng `PasswordEncoder` phù hợp, lưu credentials/secret đúng cách, không hard-code.

Lưu ý quan trọng:
- `.roles("ADMIN")` tạo authority dạng `ROLE_ADMIN`.
- `.authorities("ROLE_AUDITOR", "SCOPE_reports.read")` đặt **đúng chuỗi đã khai**.
- `.authorities("SCOPE_reports.write")` không tự tạo `ROLE_WRITER`.
- User admin trong ví dụ **không có** `SCOPE_reports.write` chỉ vì là ADMIN.
- `hasAnyAuthority("SCOPE_reports.read","ROLE_AUDITOR")` cho auditor; writer cần rule khác cho GET nếu business muốn writer cũng đọc.

Đừng nghĩ `hasRole("ADMIN")` đọc trường tên `role` trong user database. Nó xem danh sách `GrantedAuthority` của `Authentication` được authentication provider cung cấp.

## 11. Role không tự bao hàm permission khác

Trong ma trận trên, admin có `ROLE_ADMIN` nhưng không tự có `SCOPE_reports.read` hoặc `SCOPE_reports.write`. Spring Security không mặc định “ADMIN được tất cả” cho mọi chuỗi authority do bạn phát minh.

Nếu policy muốn admin được WRITE reports, có thể cấu hình tường minh:

~~~java
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.write", "ROLE_ADMIN")
~~~

Đây là **OR** giữa write scope và role admin. Nhưng phải hỏi:
- Admin nào: system-wide hay chỉ một tenant?
- Role từ JWT/user store có đúng phạm vi không?
- POST còn cần object-level permission/trạng thái nghiệp vụ?
- Có ràng buộc audit/MFA/approval khi admin can thiệp không?

Không nối `ROLE_ADMIN` vào mọi rule chỉ để làm test pass. Nó có thể mở quyền xuyên tenant hoặc tạo đường vượt business restriction.

Nếu cần quyền READ+WRITE đồng thời, dùng policy AND rõ ràng. `hasAnyAuthority(a,b)` **không** đáp ứng yêu cầu đó.

## 12. Khi cần AND hoặc policy phức tạp

Authority manager cơ bản giỏi kiểm tra **một** hoặc **một trong nhiều** authority. Với một rule như:

~~~text
ALLOW only if:
    has authority ROLE_APPROVER
    AND has authority SCOPE_invoices.approve
    AND tenant membership active
    AND invoice is not locked
~~~

cần phối hợp nhiều lớp.

Một cách ở reactive method security:

~~~java
@PreAuthorize(
    "hasAuthority('ROLE_APPROVER') and " +
    "hasAuthority('SCOPE_invoices.approve')"
)
public Mono<InvoiceView> approve(String tenantId, Long invoiceId) {
    return invoiceService.approveInScope(tenantId, invoiceId);
}
~~~

Đây là **snippet tích hợp Spring Reactive Method Security**; method được Spring AOP proxy chặn trước khi Publisher được thực thi theo hỗ trợ method security. Nhưng hai authority vẫn **không** kiểm tra tenant hay invoice. Service `approveInScope` phải kiểm tra tenant membership, object owner/ACL, status và transaction consistency trước mutation.

Một hướng khác là custom `ReactiveAuthorizationManager<AuthorizationContext>` dùng API version phù hợp và nhận dữ liệu policy qua reactive service. Khi có `Mono<Boolean>` trả về từ policy bean, tuyệt đối không dùng `.block()` để ép kết quả trong event loop.

### Ví dụ khái niệm cho custom reactive manager trên 7.x

~~~java
ReactiveAuthorizationManager<AuthorizationContext> manager =
    (authentication, context) ->
        authentication
            .map(auth -> auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> a.getAuthority().equals("ROLE_APPROVER"))
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> a.getAuthority()
                           .equals("SCOPE_invoices.approve")))
            .map(granted -> (AuthorizationResult)
                    new AuthorizationDecision(granted));
~~~

Đây là **snippet API 7.x**, cần imports của `ReactiveAuthorizationManager`, `AuthorizationContext`, `AuthorizationResult`, `AuthorizationDecision` và `Authentication`, cùng các dependency WebFlux. Nó mô tả AND của hai authorities, chưa có tenant/resource policy, và có thể phát `Mono.empty()` nếu không có authentication. Khi dùng trong request authorization, phải đảm bảo anonymous/empty được chặn bởi rule toàn cục hoặc `switchIfEmpty(Mono.just(new AuthorizationDecision(false)))` theo contract version, không tự coi empty là ALLOW.

**Với 6.5**, interface custom vẫn yêu cầu method `check(...)` abstract/deprecated, nên không copy lambda signature 7.x rồi kỳ vọng chạy trên 6.5 mà không kiểm tra; nếu cần compatibility nên tách adapter theo version hoặc dùng DSL built-in phù hợp.

## 13. JWT Resource Server: scope thường thành SCOPE_

Đối với WebFlux OAuth 2.0 Resource Server, JWT có thể chứa:

~~~json
{
  "iss": "https://identity.example/issuer",
  "sub": "user-72",
  "scope": "reports.read reports.write"
}
~~~

Sau khi resource server **xác minh JWT**, mapping mặc định của scope thành authority có thể là:

~~~text
SCOPE_reports.read
SCOPE_reports.write
~~~

Khi đó:

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("SCOPE_reports.read")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("SCOPE_reports.write")
~~~

là đúng với hai scope đó. Nhưng `hasRole("reports.read")` sẽ tìm `ROLE_reports.read`, **không phải** `SCOPE_reports.read`, vì thế thường DENY.

Đừng nhầm:
- `scope`/`scp` trong token là claim ban đầu.
- `SCOPE_...` là GrantedAuthority được converter tạo ra.
- `ROLE_...` là convention role.
- `hasAuthority(...)` nhìn danh sách GrantedAuthority **sau conversion**, không tự đọc raw claims.

Config WebFlux resource server (snippet tích hợp):

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

Đoạn trên cần Spring Security OAuth2 Resource Server/Jose dependencies, cấu hình issuer/JWK cho token và imports. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example/issuer
~~~

URI là ví dụ; phải thay bằng issuer thật và xác minh claim `iss`, chữ ký, `exp`, `nbf`, audience, token purpose và các điều kiện bảo mật theo sản phẩm.

## 14. JWT roles không tự biến thành ROLE_

Một JWT có thể có:

~~~json
{
  "sub": "user-72",
  "roles": ["ADMIN", "AUDITOR"]
}
~~~

Đừng mặc định Spring reactive resource server chuyển `roles` thành `ROLE_ADMIN` và `ROLE_AUDITOR`. Mapping mặc định phổ biến tập trung vào scope/scp. Nếu authorization server của bạn phát roles trong custom claim, phải cấu hình một converter đáng tin để đưa chúng vào `Authentication.getAuthorities()`.

Với Spring Security, có các thành phần như `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter` và `ReactiveJwtAuthenticationConverterAdapter` để liên kết conversion trong reactive resource server theo version hỗ trợ. Khi chỉnh, cần giữ những kiểm tra:
- Chỉ dùng issuer đã được xác thực; không nhận role từ JSON body/header.
- Claim name/structure đúng với issuer và tenant.
- Không cấp role global nếu token chứa role cục bộ của tenant khác.
- Nếu kết hợp scope và role custom, không vô tình **thay mất** scope authorities.
- Không tin role text chưa được allowlist/normalized theo policy.
- Kiểm tra JWT expired/revoked theo SLA; role cũ có thể tồn tại đến token expiry.

**Kỹ năng debug quan trọng:** sau khi JWT được xác thực, kiểm tra (trong môi trường test có kiểm soát) tập authorities thực được converter tạo. Đừng log raw token hoặc toàn bộ Authentication vào production.

## 15. ReactiveSecurityContextHolder thay vì giả định ThreadLocal

Trong Spring WebFlux, security context của reactive flow được truyền qua **Reactor Context**. Khi cần access authentication trong một component reactive, một mẫu là:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Đây là **snippet tích hợp**, không có class wrapper; trong một component Spring/WebFlux phải gắn đúng lifecycle. Có thể trả `Mono.empty()` nếu không có security context; khi nghiệp vụ yêu cầu authentication phải xử lý thiếu danh tính bằng cách từ chối, không tạo user mặc định.

Không đưa authentication qua một `ThreadLocal` tự tạo rồi giả định nó được tự động kế thừa qua `publishOn`, async hoặc các thread khác. Nếu gọi blocking DB/API trong reactive chain, phải thiết kế threading phù hợp, không chặn Netty event loop và không lẫn context giữa request.

Một custom reactive authorization check thường không cần tự đọc `ReactiveSecurityContextHolder`; framework truyền `Mono<Authentication>` cho manager. Dùng parameter này thay vì lấy identity từ thread-local không đáng tin.

## 16. HTTP check khác reactive method security

HTTP authorization qua `authorizeExchange` chặn theo path/method trước khi controller/service chạy. Method authorization bảo vệ **use case** và có thể tái sử dụng khi service được gọi từ HTTP hoặc adapter khác.

Config method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
~~~

Trong một số tài liệu/version cũ dùng `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` để chọn hạ tầng mới. Xác minh option đúng với Spring Security version của project.

Service:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<ReportView> readReport(String tenantId, Long reportId) {
        return findReportWithVerifiedScope(tenantId, reportId);
    }
}
~~~

Mã là **Spring integration snippet**, cần hiện thực `ReportView` và `findReportWithVerifiedScope`. Method được chặn theo authority. Nhưng nếu `findReportWithVerifiedScope` là `repository.findById(reportId)` không scoped, actor có scope READ vẫn có thể xem report người khác. Cần kiểm tra tenant, owner/ACL, status đúng ở data-access boundary.

Trong reactive method security, return type nên là `Publisher` (như `Mono`/`Flux`) hoặc kiểu được phiên bản đang dùng hỗ trợ, để tích hợp Reactor Context. Method call qua Spring proxy trong proxy mode; self-invocation `this.readReport(...)` có thể bypass interceptor.

## 17. Role hierarchy: không suy luận ADMIN tự có mọi quyền

Một policy có thể muốn:
~~~text
ADMIN > EDITOR > VIEWER
~~~

Nhưng một authentication chỉ có `ROLE_ADMIN` **không tự chứa** `ROLE_EDITOR`, `ROLE_VIEWER`, `SCOPE_reports.read`. Spring Security có các tính năng role hierarchy trong những bối cảnh và version khác nhau; không được giả định manager static `hasAuthority("SCOPE_reports.read")` sẽ tự suy luận hierarchy tùy ý.

Lựa chọn:
1. Cấp những authorities cần thiết khi xây Authentication với nguồn dữ liệu đáng tin.
2. Dùng cơ chế role hierarchy được hỗ trợ và cấu hình rõ theo đúng Spring Security version và authorization path.
3. Xây policy service bao gồm hierarchy/domain action mapping, với test tích hợp.

**Không chỉ test `hasRole("ADMIN")` rồi kết luận admin cũng qua mọi `hasAuthority` route.**

Role hierarchy có thể hữu ích nhưng nếu cấu hình sai, quyền ADMIN của một tenant có thể bị dùng ở tenant khác. Role phải có phạm vi được xác minh, không chỉ nằm trong chuỗi authority.

## 18. Tenant, owner, ACL: giới hạn của AuthorityReactiveAuthorizationManager

Xét user An:
~~~text
tenant north: ROLE_EDITOR
tenant south: ROLE_VIEWER
document 42: tenant south, owner Binh, share READ
~~~

Nếu Authentication gộp mọi role của An thành `ROLE_EDITOR` toàn cục rồi WebFlux route dùng:
~~~java
.pathMatchers("/tenants/**/documents/**").hasRole("EDITOR")
~~~

thì `ROLE_EDITOR` từ north có thể mở request tới south. Đây là **lỗi mô hình authority**, không phải lỗi của `AuthorityReactiveAuthorizationManager`: class kiểm tra đúng authority mà ứng dụng đã cấp, nhưng dữ liệu authority thiếu tenant scope.

Quyết định đúng cần:
~~~text
authenticated(actor)
AND verifiedMembership(actor, requestedTenant)
AND roleAllows(actor, requestedTenant, action)
AND resource.tenant == requestedTenant
AND (owner OR validGrant OR verifiedProjectScope)
AND resourceStateAllows(action)
~~~

Một thiết kế thường phù hợp:
- HTTP WebFlux gate kiểm tra coarse scope/action qua `hasAuthority`.
- Service resolver lấy verified actor và tenant membership.
- Repository dùng `id AND tenant AND (owner OR ACL...)`.
- Write sử dụng guarded transaction/expected version/revocation protocol.

Không để user tự gửi `tenantId` hoặc `isAdmin` làm bằng chứng. Một grant READ trên document không tự cho phép DELETE. Nếu policy cần cross-tenant support, thiết kế capability riêng và audit thay vì bỏ mọi tenant filter.

## 19. Dùng hasAnyRole cho nhiều nhóm người được phép

Ví dụ:
~~~java
.pathMatchers("/api/operations/**")
    .hasAnyRole("OPERATOR", "SUPPORT")
~~~

Điều kiện này là:
~~~text
hasAuthority("ROLE_OPERATOR")
OR hasAuthority("ROLE_SUPPORT")
~~~

Nó không yêu cầu cả hai. Một user có `ROLE_SUPPORT` nhưng không có `ROLE_OPERATOR` vẫn được phép.

Một ví dụ khác:
~~~java
.pathMatchers("/api/invoices/**")
    .hasAnyAuthority("SCOPE_invoices.read", "ROLE_AUDITOR")
~~~

Cho phép actor có ít nhất một trong hai authority. Nếu business yêu cầu auditor **và** scope, không dùng `hasAnyAuthority`. Đặc biệt, nếu một endpoint DELETE vô tình dùng `hasAnyRole("VIEWER","ADMIN")` thì viewer cũng được DELETE — lỗi **least privilege** nghiêm trọng.

## 20. Deny-by-default và quyền truy cập chưa xác thực

Một thiết kế an toàn:
~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

Đây là cấu hình minh họa. Cân nhắc `authenticated()` cho API fallback: nó cho phép mọi authenticated user vào route API mới, nên nếu muốn chặn mọi route chưa khai báo thì dùng `denyAll()`.

Một lần nữa, thứ tự rule quan trọng: `/api/admin/**` phải đứng trước `/api/**` nếu rule sau có phạm vi rộng hơn. Các route GET/POST/DELETE cùng path nên được bảo vệ theo action.

Phân biệt:
- `permitAll()`: không yêu cầu authorization cho matcher này; vẫn có các filter/bảo vệ khác tùy cấu hình.
- `authenticated()`: yêu cầu authentication hợp lệ.
- `hasAuthority(...)`: cần authority cụ thể trong Authentication.
- `hasRole(...)`: cần authority `ROLE_<role>`.
- `denyAll()`: luôn từ chối cho matcher tương ứng.

Không dùng `permitAll()` để giải quyết lỗi mapping authority; hãy kiểm tra authentication conversion và route config.

## 21. 401, 403 và nguyên nhân khác nhau

Khi một request bị chặn:
- **401/challenge**: chưa có authentication hợp lệ trong API sử dụng HTTP Basic/Bearer, hoặc token không hợp lệ. Với form login có thể redirect thay vì trả 401 thẳng.
- **403**: đã xác thực nhưng thiếu authority/role hoặc bị policy từ chối.
- **403 do CSRF**: POST/DELETE dùng cookie/HTTP Basic và CSRF protection đang bật, thiếu CSRF token; không phải luôn do `hasAuthority`.
- **404**: resource không tồn tại trong tập được phép xem (nếu service áp scoped query và policy chọn 404 để chống enumeration).
- **5xx**: authz backend/DB không khả dụng hoặc cấu hình sai, không nên fail-open.

Không trả nguyên danh sách authorities hoặc token claims cho client để “giải thích thiếu role”. Không dùng authentication failure làm bằng chứng user không có quyền object. Trong audit, lưu mã nguyên nhân phù hợp, tránh log raw token/owner/ACL của tài nguyên không được phép.

## 22. Tại sao không nên dùng block() khi kiểm tra quyền WebFlux?

Một custom policy có thể cần reactive repository hoặc remote PDP:

~~~text
Mono<Authentication>
      |
      v
fetch verified membership (reactive DB)
      |
      v
fetch resource metadata/ACL
      |
      v
Mono<AuthorizationResult>
~~~

Dùng `.block()` trong reactive request thread có thể làm nghẽn Netty event loop, tăng latency và timeout dưới tải.

Thực hành:
- Composer dùng `flatMap`/`map` và publisher return type đúng.
- Không trả `Mono.just(true)` khi remote policy timeout.
- Dùng timeout/circuit breaker có phân biệt DENY và ERROR; cả hai đều không cấp quyền.
- Không tạo publisher chứa side effect rồi subscribe bằng tay trong authorization function; framework là subscriber.
- Đảm bảo Reactor Context của authentication không bị mất bởi async/task boundary tự chế.
- Test lỗi và cancel, không chỉ happy path.

Ví dụ snippet:
~~~java
return membershipService.hasRole(actor, tenant, "EDITOR")
    .flatMap(roleOk -> roleOk
        ? resourcePolicy.canWrite(actor, tenant, documentId)
        : Mono.just(false))
    .map(granted -> (AuthorizationResult)
        new AuthorizationDecision(granted));
~~~

Mã này **chỉ là đoạn pipeline tích hợp**; cần actor lấy từ authentication đã xác minh, các service trả `Mono<Boolean>` và code hoàn chỉnh theo Spring version. Kiểm tra authority chức năng vẫn không thay thế trạng thái resource hiện tại; với write cần transaction/guard chống TOCTOU.

## 23. Ghi chú khi viết custom manager và nâng cấp Spring Security

Khi chỉ cần role/authority, factory có sẵn thường đơn giản và ít lỗi hơn custom manager. Tự viết manager khi:
- Policy cần owner/tenant/ACL/object state.
- Cần AND/OR theo business condition phức tạp.
- Có remote PDP hoặc relationship authorization.
- Cần quyết định dựa trên request method, headers đã xác minh và domain context.
- Cần phân tách PEP/PDP và reason codes.

Nếu tự viết:
1. Xác định version Spring Security **trước** khi chọn method `check` hoặc `authorize`.
2. Xác định generic `T`: `AuthorizationContext` cho WebFlux HTTP, hay loại secured object khác.
3. Trả publisher lazy, không ép `block()`.
4. Với thiếu auth/input, chọn DENY/ERROR rõ thay vì vô tình abstain.
5. Xử lý timeout, cancellation, exception không trở thành ALLOW.
6. Không gọi `getAuthorities()` trên null authentication.
7. Ràng buộc quyết định với action/resource/tenant đã xác minh.
8. Không log raw Authentication, JWT hoặc resource payload.
9. Tách lỗi kỹ thuật khỏi DENY nghiệp vụ trong observability.
10. Test route, method security, reload chính sách và concurrency khi dữ liệu quyền thay đổi.

**Về quy ước ROLE_:** static factory `hasRole` của class này được document là thêm `ROLE_`. Khi hệ có role naming khác hoặc method security có custom prefix, dùng chính authority đã map và integration test, không dựa vào giả định rằng mọi layer cùng đọc một config prefix.

## 24. Java 17 độc lập: minh họa chính xác role và authority

Ví dụ này là **Java 17 thuần, không cần Spring**. Nó mô phỏng logic string matching của các factory, giúp chứng minh sự khác nhau giữa `hasRole`, `hasAuthority`, `hasAnyRole` và `hasAnyAuthority` trước khi kết nối WebFlux.

Tạo file `AuthorityMatchDemo.java`:

~~~java
import java.util.Set;

public class AuthorityMatchDemo {
    static boolean hasAuthority(Set<String> granted, String required) {
        return granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String role) {
        return granted.contains("ROLE_" + role);
    }

    static boolean hasAnyAuthority(
            Set<String> granted, String... options) {
        for (String authority : options) {
            if (granted.contains(authority)) {
                return true;
            }
        }
        return false;
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        for (String role : roles) {
            if (granted.contains("ROLE_" + role)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        Set<String> an = Set.of(
                "ROLE_ADMIN", "SCOPE_reports.read");
        Set<String> binh = Set.of(
                "ROLE_EDITOR", "SCOPE_reports.write");
        Set<String> chi = Set.of("ADMIN");

        System.out.println("an-role-admin="
                + hasRole(an, "ADMIN"));
        System.out.println("an-authority-admin="
                + hasAuthority(an, "ADMIN"));
        System.out.println("an-exact-role-authority="
                + hasAuthority(an, "ROLE_ADMIN"));
        System.out.println("an-report-read="
                + hasAuthority(an, "SCOPE_reports.read"));
        System.out.println("binh-any-role="
                + hasAnyRole(binh, "ADMIN", "EDITOR"));
        System.out.println("binh-any-authority="
                + hasAnyAuthority(
                    binh, "SCOPE_reports.read", "SCOPE_reports.write"));
        System.out.println("binh-read-only="
                + hasAuthority(binh, "SCOPE_reports.read"));
        System.out.println("chi-has-role-admin="
                + hasRole(chi, "ADMIN"));
        System.out.println("chi-has-authority-admin="
                + hasAuthority(chi, "ADMIN"));
        System.out.println("empty-no-role="
                + hasAnyRole(Set.of(), "ADMIN", "EDITOR"));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac AuthorityMatchDemo.java
java AuthorityMatchDemo
~~~

Stdout chính xác:

~~~text
an-role-admin=true
an-authority-admin=false
an-exact-role-authority=true
an-report-read=true
binh-any-role=true
binh-any-authority=true
binh-read-only=false
chi-has-role-admin=false
chi-has-authority-admin=true
empty-no-role=false
~~~

Giải thích:
- `ROLE_ADMIN` thỏa `hasRole("ADMIN")`, nhưng **không** thỏa `hasAuthority("ADMIN")`.
- `hasAuthority("ROLE_ADMIN")` yêu cầu chuỗi chính xác, nên An được.
- Bình được qua một trong hai role và một trong hai scope, dù không có READ scope.
- Chi có raw `ADMIN` nhưng không có `ROLE_ADMIN`.
- Tập authorities rỗng không thể đáp ứng any role trong ví dụ.

**Giới hạn:** chương trình không có `Mono`, Authentication providers, bearer token, filter chain hoặc permission object-level. Đây là mô hình cho **factory string matching**, không phải bản sao mọi chi tiết runtime/anonymous handling của Spring Security. Phần integration test bên dưới mới chứng minh matcher và authentication hoạt động trong WebFlux thật.

## 25. Integration test bằng WebTestClient

Spring Security Test hỗ trợ `WebTestClient` trong reactive stack. Ví dụ kiểm tra GET admin:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxAuthorizationTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void adminRoleCanAccessAdminPath() {
        webTestClient
            .mutateWith(mockUser().roles("ADMIN"))
            .get().uri("/api/admin/status")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rawAdminAuthorityDoesNotSatisfyHasRole() {
        webTestClient
            .mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("ADMIN")))
            .get().uri("/api/admin/status")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Snippet tích hợp test**: cần Spring Boot WebFlux Test/Spring Security Test/JUnit, endpoint `GET /api/admin/status` thực trả 200 khi được phép, cấu hình chain `hasRole("ADMIN")` và WebTestClient tích hợp security test đúng cách. Nếu application test chưa cấu hình các điều kiện trên, snippet không phải file test runnable độc lập.

Các phiên bản Boot/Security khác nhau có thể yêu cầu bind WebTestClient với `springSecurity()` trong test standalone; hãy tham khảo docs test WebFlux tương ứng. Với HTTP Basic request thật, test CSRF/401/403 khác với mock-user security context.

### Ma trận cần kiểm tra trong integration test

| Request | GrantedAuthority | Kỳ vọng từ rule minh họa |
|---|---|---|
| GET `/api/admin/status` | `ROLE_ADMIN` | Cho đi tiếp |
| GET `/api/admin/status` | `ADMIN` | 403 nếu đã xác thực |
| GET `/api/admin/status` | `ROLE_EDITOR` | 403 |
| GET `/api/reports/7` | `SCOPE_reports.read` | Cho đi tiếp |
| GET `/api/reports/7` | `ROLE_AUDITOR` | Cho đi tiếp |
| GET `/api/reports/7` | `SCOPE_reports.write` | 403 theo rule GET minh họa |
| POST `/api/reports/7` | `SCOPE_reports.write` + CSRF phù hợp | Cho đi tiếp tới handler; kết quả HTTP tùy handler |
| POST `/api/reports/7` | `SCOPE_reports.read` | 403 |
| DELETE `/api/reports/7` | Bất kỳ | Bị denyAll nếu không có rule DELETE |
| GET `/public/version` | Không authentication | Cho đi tiếp theo permitAll |
| GET `/api/admin/status` | Không authentication | Challenge/401 hoặc redirect theo authentication config |

Đừng chỉ kiểm tra status: cần đảm bảo denied request **không gọi service mutate dữ liệu**, và handler trả đúng status không lộ resource/owner ngoài quyền.

## 26. Mock user roles khác mock user authorities

Trong test:
~~~java
mockUser().roles("ADMIN")
~~~

thường tạo authority `ROLE_ADMIN`, tương tự user builder `.roles("ADMIN")`.

Còn:
~~~java
mockUser().authorities(
    new SimpleGrantedAuthority("ADMIN"))
~~~

tạo authority `ADMIN` nguyên văn. Nếu test của bạn dùng roles nhưng production JWT converter tạo raw `ADMIN`, test có thể PASS mà production bị 403.

Ngược lại, test set authorities quá rộng như `ROLE_ADMIN` + `SCOPE_reports.write` có thể che lỗi thiếu mapping của provider thật. Cần kiểm thử ít nhất một path thông qua authentication provider hoặc validated JWT test fixture đúng claim và converter đang dùng.

Không tạo role/scope fixture từ client-supplied JSON rồi coi là integration test của authentication security.

## 27. Unit test manager trực tiếp theo đúng version

Nếu muốn test chính manager thay vì HTTP route, ví dụ với authentication được dựng trong test:
~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "an", "unused",
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

Ở Spring Security **6.5**, có thể gọi (trong test tích hợp thư viện):

~~~java
Mono<AuthorizationDecision> decision =
    AuthorityReactiveAuthorizationManager
        .<String>hasRole("ADMIN")
        .check(Mono.just(authentication), "securedObject");
~~~

Ở Spring Security **7.x**:

~~~java
Mono<AuthorizationResult> decision =
    AuthorityReactiveAuthorizationManager
        .<String>hasRole("ADMIN")
        .authorize(Mono.just(authentication), "securedObject");
~~~

Đây là các snippet version-specific, cần imports và dependency. Dùng `StepVerifier` hoặc Reactor test subscriber kiểm chứng `decision.isGranted()`. **Không gọi `.block()` trong runtime WebFlux**; test standalone có thể dùng blocking theo công cụ test nếu phù hợp.

Đặc biệt nên assert:
- GrantedAuthority đúng thì ALLOW.
- Thiếu authority thì DENY.
- Role prefix sai thì DENY.
- Any factory dùng OR chứ không phải AND.
- Authentication publisher không có principal hoặc bị lỗi không tạo “default allow”.
- Custom manager lỗi/abstain không bị adapter của bạn chuyển thành ALLOW.

## 28. Lỗi phổ biến và cách xử lý

**1. Dùng `hasRole("ROLE_ADMIN")`.** Factory đã có logic thêm `ROLE_`; không truyền tên đã prefix theo cách nghĩ “chắc chắn hơn”. Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`.

**2. Dùng `hasAuthority("ADMIN")` khi user builder cấp `.roles("ADMIN")`.** User có `ROLE_ADMIN`, không có raw `ADMIN`. Đồng bộ tên chuỗi.

**3. Dùng `hasRole("reports.read")` cho JWT scope.** JWT scope thường map thành `SCOPE_reports.read`. Dùng `hasAuthority("SCOPE_reports.read")` hoặc manager scope chuyên biệt nếu phù hợp.

**4. Tưởng `hasAnyAuthority(a,b)` yêu cầu cả a và b.** Nó chỉ cần một. Với AND, sử dụng composite policy được test.

**5. Tưởng role ADMIN tự có mọi authority.** Không có phép suy luận đó nếu không cấu hình. Cấp quyền cụ thể hoặc policy hierarchy đúng.

**6. Đặt matcher broad trước matcher hẹp.** Route admin có thể rơi vào `authenticated()` hoặc rule không đúng. Đặt đặc thù trước fallback.

**7. Quên HTTP method.** Một rule READ cho mọi verb có thể vô tình bảo vệ DELETE bằng quyền đọc. Tách method-level action.

**8. Dùng HttpSecurity trong project WebFlux.** Sai stack. Với WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`.

**9. Dùng `check(...)` trong source project Spring Security 7.x.** API hiện hành dùng `authorize(...)`. Kiểm tra Javadoc đúng version.

**10. Tin JWT có claim `roles` nghĩa là có `ROLE_ADMIN`.** Cần converter để tạo GrantedAuthority thực.

**11. Test với mock role nhưng production converter tạo authority khác.** Test cả đường map claim/provider và route, không chỉ `@WithMockUser`.

**12. Dùng global role trên URL nhiều tenant.** Role north có thể mở resource south. Bổ sung membership và resource tenant guard.

**13. Dùng authority làm chứng minh owner/ACL.** `SCOPE_documents.read` không xác nhận được quyền trên document #42; kiểm tra object-level.

**14. Dùng `block()` khi policy cần I/O.** Có thể nghẽn event loop. Kết hợp publishers không blocking.

**15. Coi `Mono.empty()` là ALLOW.** Trống là no decision theo contract, không phải cấp quyền.

**16. Tắt CSRF để sửa mọi 403.** Có thể làm mất một lớp bảo vệ quan trọng. Xác định nguyên nhân, cân nhắc theo session/cookie/bearer threat model.

**17. Chỉ bảo vệ HTTP, quên method/worker.** Service nhạy cảm có thể được gọi qua message/scheduler. Đặt policy ở boundary dùng chung.

**18. Bắt exception từ PDP rồi trả true.** Fail-open. Với backend lỗi, không cho hành động và có observability.

## 29. Checklist trước khi merge code WebFlux authorization

- [ ] Xác định rõ project đang dùng WebFlux (không phải Servlet stack).
- [ ] Sử dụng đúng `ServerHttpSecurity`, `SecurityWebFilterChain` và `authorizeExchange`.
- [ ] Có thứ tự matcher từ hẹp đến rộng, fallback deny phù hợp.
- [ ] GET/POST/PUT/PATCH/DELETE được kiểm tra theo action phù hợp.
- [ ] Hiểu `hasRole("R")` so khớp `ROLE_R`; `hasAuthority("X")` so khớp đúng `X`.
- [ ] Không dùng `hasAnyRole/Authority` để biểu diễn AND.
- [ ] Role/authority naming convention và chữ hoa/chữ thường nhất quán.
- [ ] JWT scope và custom roles được map rõ thành GrantedAuthority.
- [ ] JWT được validate trước khi tin claims; issuer/audience/expiry và tenant scope được kiểm tra.
- [ ] Cùng subject có role ở nhiều tenant không bị gộp thành quyền global vô ý.
- [ ] Object/resource tenant, owner, ACL được kiểm tra riêng với chức năng.
- [ ] Reactive method security được bật nơi cần và hoạt động qua proxy.
- [ ] Không block event loop hoặc tự subscribe trong authorization rule.
- [ ] Các trạng thái no decision/error/timeout không biến thành ALLOW.
- [ ] Có test role đúng/sai prefix, authority thiếu, JWT scope, matcher order và HTTP verbs.
- [ ] Test 401/403/CSRF và đảm bảo mutation không chạy khi denied.
- [ ] Custom manager và method `check/authorize` đúng **phiên bản Spring Security**.
- [ ] Cấu hình nhiều WebFilterChain không làm route bảo vệ đi vào chain permissive.
- [ ] Khi migrate phiên bản, review Javadoc và test security integration trước release.

**Kết luận:** `AuthorityReactiveAuthorizationManager` là công cụ kiểm tra **GrantedAuthority** trong WebFlux: `hasAuthority` kiểm tra chuỗi chính xác, `hasRole` dùng prefix `ROLE_`, còn các factory `hasAny...` dùng logic OR. Đặt chúng đúng trong `authorizeExchange`, chuẩn hóa cách tạo authorities từ credentials/JWT, và luôn bảo vệ dữ liệu ở service/repository khi quyền còn phụ thuộc tenant hoặc object. Với custom reactive authorization, phải bám đúng API version và giữ nguyên tắc fail-closed.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain`, `ServerHttpSecurity.authorizeExchange`, thứ tự matcher.
- [Spring Security 6.5 — AuthorityReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html): factory và `check(...)` trong 6.5.
- [Spring Security 6.5 — ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `authorize` default từ 6.4, `check` deprecated.
- [Spring Security 7.x — AuthorityReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html): factory và `authorize(...)`.
- [Spring Security 7.x — ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): contract reactive và `verify`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, Reactor Context.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT verification, mapping scopes sang `SCOPE_` và cấu hình WebFlux.
- [Spring Security — WebFlux Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient`, authentication mocks và security test.
