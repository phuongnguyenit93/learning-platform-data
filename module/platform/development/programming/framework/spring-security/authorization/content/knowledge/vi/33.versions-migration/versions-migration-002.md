# authorizeRequests so với authorizeHttpRequests và thay đổi cơ chế thực thi

## 1. Tổng quan và mục tiêu học tập

Trong Spring Security dùng Servlet, `authorizeRequests` và `authorizeHttpRequests` đều cấu hình **quyền truy cập HTTP** theo đường dẫn, HTTP method và Authentication. Hai DSL có nhiều quy tắc bề ngoài giống nhau, nhưng **khác cơ chế thực thi**. Việc đổi một tên method không đủ để chứng minh migration an toàn.

Bài học giải thích sự chuyển dịch từ `FilterSecurityInterceptor`, `AccessDecisionManager` và `AccessDecisionVoter` sang `AuthorizationFilter` và `AuthorizationManager`, qua đó hiểu các thay đổi về thời điểm lấy Authentication, thứ tự rule và servlet dispatch. Các ví dụ tập trung Spring Security **Servlet**, nhất là chuyển code Spring Security 5.x sang 6.x/7.x. WebFlux sử dụng `ServerHttpSecurity.authorizeExchange` và `SecurityWebFilterChain`, không dùng nguyên code dưới đây.

Kết thúc bài, bạn có thể:
- Phân biệt các đối tượng thực thi ủy quyền ở cấu hình cũ và mới.
- Chuyển `antMatchers`/`authorizeRequests` sang `requestMatchers`/`authorizeHttpRequests` phù hợp phiên bản.
- Hiểu first-match wins, `hasRole`/`hasAuthority`, `securityMatcher` và nhiều filter chain.
- Giải thích deferred Authentication lookup và việc `AuthorizationFilter` kiểm tra từng servlet dispatch.
- Chuyển biểu thức SpEL và custom voter sang API mới mà không vô tình đổi quyết định ALLOW/DENY.
- Viết security regression test để xác minh hành vi, thay vì chỉ tin rằng code biên dịch.

## 2. So sánh hai cách cấu hình

| Chủ đề | `authorizeRequests` (legacy) | `authorizeHttpRequests` (mới) |
|---|---|---|
| DSL | `HttpSecurity.authorizeRequests(...)` | `HttpSecurity.authorizeHttpRequests(...)` |
| Filter authorization | `FilterSecurityInterceptor` | `AuthorizationFilter` |
| Ra quyết định | Metadata source + `ConfigAttribute` + `AccessDecisionManager` + `AccessDecisionVoter` | `AuthorizationManager` và các request matcher |
| Authentication | Cơ chế interceptor cũ thường cần tra Authentication trong xử lý quyết định | `Supplier<Authentication>`, chỉ truy xuất khi rule cần |
| Rule URL | `antMatchers`/`mvcMatchers` trong các bản 5.x | `requestMatchers`/`dispatcherTypeMatchers`, semantics matcher tùy phiên bản |
| Tùy biến | Expression handler, voter, decision manager | `AuthorizationManager<RequestAuthorizationContext>`, manager tạo từ bean, expression manager |
| Servlet dispatch | Hành vi gắn với `FilterSecurityInterceptor` và cấu hình once-per-request | `AuthorizationFilter` thực thi authorization trên các dispatch được filter chain xử lý |
| Xu hướng phiên bản | API deprecated/legacy | Lựa chọn chuẩn cho cấu hình Spring Security 6/7 mới |

**Điểm quan trọng:** khi dùng `authorizeHttpRequests`, Spring Security chọn `AuthorizationFilter` thay cho `FilterSecurityInterceptor` trong nhánh request authorization tương ứng. Điều này khác việc chỉ đổi cách gọi DSL. Custom policy được triển khai qua voter/decision manager cũ **không tự động** trở thành một `AuthorizationManager`.

### 2.1. Quy trình cũ

~~~text
HTTP request
  -> FilterChainProxy chọn SecurityFilterChain
  -> security-context và authentication filters
  -> FilterSecurityInterceptor
       -> SecurityMetadataSource lấy ConfigAttributes
       -> AccessDecisionManager tập hợp kết quả voters
       -> quyết định cho phép / từ chối
  -> DispatcherServlet nếu ALLOW
~~~

Trong mô hình này, `AccessDecisionManager` có thể dùng các chiến lược như affirmative, consensus, unanimous. Một `AccessDecisionVoter` có thể trả GRANT/DENY/ABSTAIN. Cách hợp nhất quyết định của manager rất quan trọng khi migration: thay một nhóm voter bằng phép OR/AND tùy ý dễ làm thay đổi chính sách.

### 2.2. Quy trình mới

~~~text
HTTP request / servlet dispatch
  -> FilterChainProxy chọn SecurityFilterChain
  -> security-context / authentication filters
  -> ExceptionTranslationFilter
  -> AuthorizationFilter
       -> chuẩn bị Supplier<Authentication>
       -> AuthorizationManager nhận request + supplier
       -> áp dụng rule khớp đầu tiên theo thứ tự DSL
       -> ALLOW: tiếp tục filter chain
       -> DENY: ném AccessDeniedException
  -> DispatcherServlet nếu ALLOW
~~~

Tài liệu Spring Security mô tả `AuthorizationFilter` nằm gần cuối security filter chain theo cấu hình mặc định. Authentication và các filter bảo vệ khác được thực hiện trước đó; bản thân `AuthorizationFilter` chịu trách nhiệm **quyết định HTTP authorization**, không tạo user mới, xác minh chữ ký JWT hay triển khai authentication provider.

Nếu bị từ chối, `ExceptionTranslationFilter` xử lý `AccessDeniedException` theo cấu hình `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`. Vì vậy, 401/403/302 phụ thuộc cơ chế đăng nhập và trạng thái client: HTTP Basic hoặc Bearer API thường trả **401** khi chưa đăng nhập và **403** khi user đã xác thực nhưng thiếu quyền; form login có thể redirect, CSRF có thể gây 403 độc lập với rule URL.

## 3. Deferred Authentication: tại sao permitAll có thể nhanh hơn?

`AuthorizationManager` nhận Authentication dưới dạng `Supplier<Authentication>`. Khi rule là `permitAll` hoặc `denyAll`, manager đã có kết quả cố định nên **không cần truy cập Authentication supplier** cho quyết định authorization đó. Nếu rule là `authenticated`, `hasRole`, `hasAuthority` hoặc custom policy phụ thuộc user, manager mới truy cập supplier.

~~~text
GET /public/help
  -> matching permitAll
  -> ALLOW mà không cần lấy Authentication vì authorization

GET /admin/report
  -> matching hasRole("ADMIN")
  -> supplier.get() để lấy Authentication
  -> kiểm tra GrantedAuthority
  -> ALLOW hoặc DENY
~~~

Lợi ích là tránh công việc tải Authentication/session không cần thiết ở một số request public. Tuy nhiên, `permitAll` **không loại URL khỏi filter chain**: custom authentication filter vẫn có thể xử lý header/token trước authorization; token sai có thể bị authentication layer từ chối. Ngược lại, `web.ignoring()` loại hẳn request khỏi Spring Security filter chain và có thể bỏ cả security headers. Với static resource, tài liệu Spring Security ưu tiên `permitAll` hơn `ignoring` khi không có lý do đặc biệt.

Đừng hiểu “trì hoãn Authentication” là “bỏ xác thực” hoặc “tự cache quyền”: manager tùy biến vẫn có thể tạo query DB/network nếu gọi dữ liệu khi đánh giá.

## 4. Cấu hình cũ: minh họa Spring Security 5.7

Ví dụ theo cách viết lịch sử của Spring Security 5.7 (mã **chỉ dành cho baseline 5.x**; `antMatchers` đã bị loại khỏi DSL thường dùng ở 6.x):

~~~java
@Configuration
@EnableWebSecurity
class LegacySecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeRequests(auth -> auth
                .antMatchers("/public/**", "/actuator/health").permitAll()
                .antMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Quy tắc: public và health được phép không yêu cầu role; GET reports cần ANALYST/ADMIN; /admin cần ADMIN; phần còn lại yêu cầu login. `hasRole("ADMIN")` mặc định so sánh với authority `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` đòi chuỗi `ADMIN` chính xác. Đây là cách dễ nhất để làm sai policy khi di chuyển từ role-based sang authority-based code.

Snippet trên là class cấu hình trong ứng dụng có Spring Security dependency và các import tương ứng; không thể chạy bằng một lệnh `java` của JDK thuần.

## 5. Cấu hình mới: Spring Security 6.x

Class sau minh họa bản chuyển đổi trên Java 17+ có các import cần thiết. Có thể đưa vào ứng dụng Spring Boot 3.x có Spring Security; route/Authentication nguồn dữ liệu phải được cấu hình thực tế trong project.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Thay đổi tối thiểu gồm `authorizeRequests` → `authorizeHttpRequests` và `antMatchers` → `requestMatchers` theo API version tương ứng. Đây là **đích tương đương về ý định chính sách** nhưng vẫn cần test URL matching/dispatcher/chain selection. Không tự thêm `csrf().disable()` để demo dễ chạy: với ứng dụng browser/session cần CSRF, với stateless API cần đánh giá riêng cơ chế token và threat model.

Không mặc nhiên chuyển `.anyRequest().authenticated()` thành `permitAll()`, hoặc chuyển toàn bộ endpoint thành ADMIN chỉ để test xanh; những thay đổi đó phải có yêu cầu nghiệp vụ riêng.

### 5.1. Phiên bản 7.x và Access API legacy

Theo tài liệu migration Spring Security 7, các thành phần Access API cũ như `AccessDecisionManager` và `AccessDecisionVoter` được chuyển sang module tùy chọn `spring-security-access`. Dự án còn dùng trực tiếp API legacy có thể cần khai báo:

~~~groovy
dependencies {
    implementation("org.springframework.security:spring-security-access")
}
~~~

Đây là đường tương thích khi nâng cấp dependency, **không** phải cách biến `authorizeRequests` thành API khuyến nghị cho mã mới. Nếu đã chuyển sang `AuthorizationManager`, không cần thêm legacy module chỉ vì application có HTTP authorization. Đối chiếu đúng tài liệu cho version/BOM đang chạy vì behavior matcher và API tiếp tục phát triển trong 6.x/7.x.

## 6. First-match wins và lỗ hổng do thứ tự rule

`authorizeHttpRequests` xét rule theo **thứ tự khai báo**. Rule khớp đầu tiên quyết định; framework không tự tìm rule có đường dẫn “cụ thể nhất” trong các rule phía sau.

**Đúng:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

**Sai và nguy hiểm:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").authenticated()
    .requestMatchers("/admin/**").hasRole("ADMIN")
)
~~~

Ở bản sai, request /admin/report có thể khớp `/**` trước nên rule ADMIN không còn tác dụng; một user thường đã đăng nhập cũng được phép. Dùng `requestMatchers("/**")` làm ví dụ lỗi thứ tự; nhiều bản DSL còn chặn cấu hình rule sau `anyRequest()` ngay khi build.

| Request | Principal | Rule đúng | Rule sai |
|---|---|---|---|
| GET /public/help | Anonymous | ALLOW | Yêu cầu xác thực |
| GET /admin/report | ROLE_USER | DENY | ALLOW — lỗi bảo mật |
| GET /admin/report | ROLE_ADMIN | ALLOW | ALLOW |
| GET /profile | ROLE_USER | ALLOW | ALLOW |

Đặt matcher cụ thể trước, fallback cuối; `anyRequest().denyAll()` có thể phù hợp chính sách “chưa khai báo thì chặn”, còn `authenticated()` phù hợp nếu hệ thống cho phép user đăng nhập truy cập mọi URL còn lại. Đây là lựa chọn policy, không phải mặc định bắt buộc một phía.

### 6.1. Thứ tự HTTP method

Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyRole("ANALYST", "ADMIN")
.requestMatchers("/api/reports/**")
    .hasRole("ADMIN")
.anyRequest().authenticated()
~~~

GET reports cho ANALYST/ADMIN, còn POST/PATCH/DELETE nếu khớp rule thứ hai yêu cầu ADMIN. Không suy rằng GET rule tự áp dụng cho POST. Đối với CORS, cần cấu hình preflight `OPTIONS` đúng kiến trúc; không giải quyết mọi lỗi preflight bằng việc mở `permitAll("/**")`.

## 7. AuthorizationFilter kiểm tra nhiều servlet dispatch

Điểm quan trọng của migration là `AuthorizationFilter` xét **mỗi dispatch** mà Spring Security filter chain xử lý, gồm `REQUEST`, `FORWARD`, `ERROR` và `INCLUDE`. Một HTTP request có thể sinh nhiều dispatch:

~~~text
GET /report          REQUEST -> authorization -> Controller
    forward /view    FORWARD -> authorization -> View rendering

GET /fails           REQUEST -> authorization -> Controller throws
    dispatch /error  ERROR   -> authorization -> Error rendering
~~~

Nếu rule chặn /error hoặc view path ở FORWARD, sau migration có thể xuất hiện 403 bất ngờ, che luôn lỗi thực ban đầu. Tùy cấu trúc MVC và threat model, có thể cân nhắc cho phép những dispatcher type cần thiết:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
            DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Đây là fragment nằm trong cấu hình Servlet 6.x, chưa phải class độc lập. **Đừng thêm permitAll cho mọi dispatch không suy xét.** `dispatcherTypeMatchers(ERROR, FORWARD).permitAll()` có phạm vi theo **loại dispatch**, rộng hơn chỉ một URL; nếu ứng dụng có nội dung nhạy cảm trong dispatch phụ, cần policy cụ thể và test riêng. Kiểm tra cả dispatcher mapping/registration thực tế: rule không thể bảo vệ một dispatch bị loại ngoài filter chain.

`permitAll` cho ERROR/FORWARD không có nghĩa mở public URL gốc; REQUEST ban đầu vẫn cần qua chính sách của nó khi đi vào security chain đúng cách.

## 8. securityMatcher, requestMatchers và nhiều filter chain

Ba khái niệm dễ nhầm:
- `http.securityMatcher("/api/**")`: **SecurityFilterChain này có áp dụng** cho request không?
- `authorizeHttpRequests(...).requestMatchers("/api/admin/**")`: **rule trong chain đã được chọn** có khớp request không?
- `anyRequest()`: fallback cho các request **thuộc chain hiện tại**, không tự bảo vệ URL ở ngoài phạm vi chain.

Với nhiều `SecurityFilterChain`, Spring Security chọn **chain khớp đầu tiên** theo thứ tự ưu tiên. Nếu không chain nào match, request có thể không được Spring Security bảo vệ; vì thế nên có fallback chain khi hệ thống cần bảo vệ mọi URL.

Ví dụ (hai method trong một class cấu hình, import Spring liên quan):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

Mẫu fallback `denyAll` chủ động chặn URL chưa khai báo; không phù hợp nguyên trạng với ứng dụng còn trang public ngoài /api. Trong ứng dụng thực, cần thiết lập login/CSRF/session/CORS theo từng chain; nhiều cấu hình `HttpSecurity` có thể tạo khác biệt về security context và entry point.

### 8.1. Path matcher phụ thuộc phiên bản

Không coi `antMatchers` 5.x và `requestMatchers(String)` 6/7 là cơ chế xử lý path hoàn toàn giống nhau. Cơ chế matcher có thể phụ thuộc version, classpath, Spring MVC/servlet mapping và matcher builder. Các bản Spring Security mới hỗ trợ matcher dựa trên `PathPatternRequestMatcher`. Phải test ít nhất:
- /admin, /admin/, /admin/a và nested path.
- URL có path variable, servlet path hoặc context path riêng.
- HTTP method GET/POST/OPTIONS/HEAD.
- Encoded/normalized path trong giới hạn server/proxy cho phép.
- Nhiều servlet, nhất là khi MVC và servlet khác cùng một ứng dụng.

Đừng dùng chuỗi URL “trông giống nhau” như bằng chứng không có regression.

## 9. Expression và custom AccessDecisionVoter

### 9.1. Chuyển SpEL khi cần

Cấu hình legacy có thể dùng biểu thức kết hợp role/authority:

~~~java
// Spring Security 5.x minh họa
.antMatchers("/finance/**")
    .access("hasRole('FINANCE') and hasAuthority('reports:read')")
~~~

Trong DSL mới, có thể sử dụng `WebExpressionAuthorizationManager`:

~~~java
.requestMatchers("/finance/**")
    .access(new WebExpressionAuthorizationManager(
            "hasRole('FINANCE') and hasAuthority('reports:read')"))
~~~

Đây là fragment trong cấu hình Spring có import phù hợp, không phải file chạy độc lập. Khi expression phức tạp hoặc phụ thuộc bean, xem xét chuyển sang `AuthorizationManager<RequestAuthorizationContext>` type-safe để dễ kiểm thử, tái sử dụng. Đặc biệt, **custom expression handler/bean resolver cũ không nhất thiết được gắn tự động** khi chuyển DSL.

### 9.2. Không ánh xạ custom voters theo tên

Trước khi chuyển một voter, hãy trả lời:
1. Nó kiểm tra role, IP, header, tenant, owner hay business policy nào?
2. Nó trả GRANT/DENY/ABSTAIN trong từng tình huống nào?
3. Decision manager cũ kết hợp nhiều voter ra sao?
4. Có policy phụ thuộc thứ tự, Authentication hoặc dữ liệu repository không?
5. Manager mới cần quyết định ALLOW/DENY ra sao để tương đương chính xác?

Nếu chuyển “chỉ một voter GRANT là đủ” thành “mọi điều kiện phải true” sẽ chặn nhầm; ngược lại, OR mọi điều kiện có thể mở quyền không mong muốn. Viết authorization matrix của logic cũ **trước khi sửa**. Manager mới phải fail closed khi thiếu dữ liệu, membership, tenant hoặc policy lookup không thành công.

Request authorization không tự thay thế **object-level authorization**. Ví dụ ADMIN tenant B không có quyền đọc tài liệu tenant A chỉ vì `/api/admin/**` đã pass. Kiểm tra owner, membership, tenant và object action tại service/domain vẫn bắt buộc.

## 10. Java 17 chạy độc lập: first-match và deferred lookup

Chương trình sau mô phỏng **nguyên lý rule khớp đầu tiên** và `Supplier<Principal>`; nó **không sử dụng internals của Spring Security**, không mở server và không giả lập các servlet filter. Ví dụ phù hợp để kiểm tra logic trước khi viết MockMvc test.

~~~java
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class AuthorizationDslMigrationDemo {
    record Principal(Set<String> authorities) {}
    record Request(String method, String path) {}
    record Rule(Predicate<Request> matches,
                Predicate<Supplier<Principal>> permits) {}

    static boolean hasRole(Supplier<Principal> supplier, String role) {
        Principal principal = supplier.get();
        return principal != null
                && principal.authorities().contains("ROLE_" + role);
    }

    static boolean authorize(Request request, Supplier<Principal> supplier,
                             List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches().test(request)) {
                return rule.permits().test(supplier);
            }
        }
        return false;
    }

    static void check(String label, Request request, Principal principal,
                      List<Rule> rules, boolean expected, int expectedReads) {
        AtomicInteger reads = new AtomicInteger();
        Supplier<Principal> supplier = () -> {
            reads.incrementAndGet();
            return principal;
        };
        boolean actual = authorize(request, supplier, rules);
        if (actual != expected || reads.get() != expectedReads) {
            throw new AssertionError(label + ": actual=" + actual
                    + ", reads=" + reads.get());
        }
        System.out.println(label + ": " + (actual ? "ALLOW" : "DENY")
                + ", authenticationReads=" + reads.get());
    }

    public static void main(String[] args) {
        Rule publicPages = new Rule(
                r -> r.path().startsWith("/public/"), supplier -> true);
        Rule internal = new Rule(
                r -> r.path().startsWith("/internal/"), supplier -> false);
        Rule admin = new Rule(
                r -> r.path().startsWith("/admin/"),
                supplier -> hasRole(supplier, "ADMIN"));
        Rule authenticated = new Rule(
                r -> true, supplier -> supplier.get() != null);
        List<Rule> correctOrder = List.of(
                publicPages, internal, admin, authenticated);
        Principal user = new Principal(Set.of("ROLE_USER"));
        Principal administrator = new Principal(Set.of("ROLE_ADMIN"));

        check("public", new Request("GET", "/public/info"),
                null, correctOrder, true, 0);
        check("internal", new Request("GET", "/internal/status"),
                user, correctOrder, false, 0);
        check("admin denied", new Request("GET", "/admin/reports"),
                user, correctOrder, false, 1);
        check("member", new Request("GET", "/profile"),
                user, correctOrder, true, 1);
        check("admin allowed", new Request("GET", "/admin/reports"),
                administrator, correctOrder, true, 1);
        check("wrong ordering", new Request("GET", "/admin/reports"),
                user, List.of(authenticated, admin), true, 1);
    }
}
~~~

Lưu vào file `AuthorizationDslMigrationDemo.java` và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 AuthorizationDslMigrationDemo.java
java AuthorizationDslMigrationDemo
~~~

Stdout chính xác (đã thực sự biên dịch bằng `javac --release 17` và chạy thành công):

~~~text
public: ALLOW, authenticationReads=0
internal: DENY, authenticationReads=0
admin denied: DENY, authenticationReads=1
member: ALLOW, authenticationReads=1
admin allowed: ALLOW, authenticationReads=1
wrong ordering: ALLOW, authenticationReads=1
~~~

`public` và `internal` quyết định mà không gọi supplier; `admin denied`/`admin allowed` dùng quyền ROLE_ sau khi lấy principal. `wrong ordering` cố tình đặt fallback authenticated đầu danh sách, dẫn đến **ALLOW sai** với /admin/reports của ROLE_USER. Đây là tình huống phải phát hiện trong regression test.

Trong production, Authentication có nhiều trạng thái (anonymous, remember-me, authenticated), JWT và filter chain khác mô hình Java SE. Mã mô phỏng không thay thế security integration test.

## 11. Kiểm thử HTTP để chứng minh migration an toàn

Sử dụng Spring Security test + MockMvc hoặc integration test tương đương để kiểm tra **kết quả thực tế** trên endpoint có tồn tại. Ví dụ sau là **fragment trong test class** đã có `MockMvc mvc`, import và controller mapping tương ứng:

~~~java
@Test
void publicEndpointIsOpen() throws Exception {
    mvc.perform(get("/public/help"))
       .andExpect(status().isOk());
}

@Test
void userCannotAccessAdmin() throws Exception {
    mvc.perform(get("/admin/reports").with(user("alice").roles("USER")))
       .andExpect(status().isForbidden());
}

@Test
void adminCanAccessAdmin() throws Exception {
    mvc.perform(get("/admin/reports").with(user("operator").roles("ADMIN")))
       .andExpect(status().isOk());
}

@Test
void anonymousMustAuthenticateForProfile() throws Exception {
    mvc.perform(get("/profile"))
       .andExpect(status().isUnauthorized()); // giả định API HTTP Basic
}
~~~

Test 200 phụ thuộc controller có thực và trả thành công; nếu route không tồn tại, có thể nhận 404 dù filter cho qua. Test 401 chỉ phù hợp entry point như HTTP Basic/Bearer; form login thường redirect 302. Với POST/PUT/DELETE trong app dùng CSRF, test cần CSRF token hợp lệ để tách việc CsrfFilter từ chối khỏi việc authorization từ chối.

### 11.1. Ma trận regression quan trọng

| Tình huống | Expected |
|---|---|
| Anonymous GET public URL | ALLOW |
| Anonymous GET protected URL | Authentication entry point |
| ROLE_USER GET /admin/reports | DENY |
| ROLE_ADMIN GET /admin/reports | ALLOW |
| ROLE_ANALYST GET /api/reports/1 | ALLOW nếu đúng rule GET |
| ROLE_ANALYST POST /api/reports/1 | Theo rule POST; không suy ra từ GET |
| User có literal authority ADMIN nhưng thiếu ROLE_ADMIN | DENY với `hasRole("ADMIN")` |
| /admin và /admin/ | Theo hợp đồng URL matcher đã kiểm tra |
| FORWARD tới view | Không bị DENY ngoài ý muốn, hoặc DENY nếu đó là policy |
| ERROR dispatch sau exception | Trả lỗi gốc theo contract, không tự biến thành lỗi 403 |
| Multiple chains: /api/** và /web/** | Chọn chain đúng và không bỏ lọt request |
| URL ngoài mọi chain | Bị bảo vệ theo fallback đã định |
| Voter/manager tùy biến | Kết quả ALLOW/DENY tương đương phiên bản trước |
| ADMIN tenant B truy cập document tenant A | DENY ở tầng object/service |
| POST bị từ chối | Không có side effect database, kiểm tra cả CSRF |

Khi test phát hiện 403, xem nguyên nhân: AuthorizationFilter, `CsrfFilter`, method security hay business exception. Không dùng mỗi status 403 làm bằng chứng chắc chắn rằng role policy hoạt động đúng.

### 11.2. Các chỉ số vận hành cần so sánh

Với cùng request dataset, đo số request bị DENY, số lần load SecurityContext/Authentication khi vào URL public, số request lặp trên ERROR/FORWARD, latency và query phát sinh từ manager tùy biến. Deferred Authentication không bảo đảm mọi custom manager đều tiết kiệm I/O. Nếu custom policy gọi database cho từng request/tenant, kiểm tra index, cache invalidation và quyền theo service.

## 12. Sai lầm thường gặp và cách sửa

- **Chỉ thay tên method:** bỏ qua thay đổi FilterSecurityInterceptor → AuthorizationFilter. Cần kiểm tra filter chain thực tế, custom voters và dispatcher types.
- **Quên xóa hoặc chuyển voter tùy biến:** chính sách từng bảo vệ tenant/IP biến mất. Chuyển nó sang AuthorizationManager hoặc dùng lộ trình legacy có kiểm soát.
- **Rule rộng đặt trước rule hẹp:** `/**` authenticated trước `/admin/**` làm người dùng thường vào admin. Đặt rule đặc thù trước và test negative cases.
- **Nhầm securityMatcher với requestMatchers:** tưởng `anyRequest` trong chain /api bảo vệ cả /web. Có fallback chain nếu cần.
- **Tưởng permitAll bỏ filter:** nó chỉ bỏ điều kiện quyền tại authorization; một authentication filter vẫn có thể từ chối input sai.
- **Dùng web.ignoring cho mọi static:** bỏ security headers/các filter khác; xem xét permitAll.
- **Thấy /error 403 liền mở /**:** cần xem dispatch ERROR và policy phù hợp, không public toàn bộ URL.
- **Role prefix sai:** `hasRole("ADMIN")` mặc định tra ROLE_ADMIN, `hasAuthority("ADMIN")` tra ADMIN.
- **Không test method/servlet path:** matcher semantics có thể khác khi đổi version; test boundary, HTTP verb và multi-servlet.
- **Đồng nhất authorization HTTP với object permission:** pass /api/** chưa đủ để xem resource tenant khác.
- **Giải quyết 403 do CSRF bằng tắt CSRF toàn cục:** tách test CSRF và authorization, quyết định theo auth architecture.
- **Dùng API 5.x trong project 6.x hoặc bỏ legacy module lúc lên 7.x:** kiểm tra version/BOM và thay thế thật sự; không trộn code snippet các major.

## 13. Quy trình chuyển đổi thực tế

1. **Inventory:** ghi Spring Security/Boot version, các SecurityFilterChain, role prefix, authentication entry points, custom voters/expressions, filter ordering, servlet/dispatcher mapping.
2. **Chốt baseline:** lập matrix URL + HTTP method + principal + expected decision/status, bao gồm public/admin/error/view/tenant và tình huống bị từ chối.
3. **Migrate tối thiểu:** chuyển DSL sang `authorizeHttpRequests`/`requestMatchers`, giữ ý định policy, thứ tự và fallback; nâng API theo chính xác version.
4. **Xử lý đặc biệt:** chuyển custom voters sang AuthorizationManager; kiểm tra SpEL manager, dispatcherTypeMatchers, securityMatcher, URL matcher và custom filter.
5. **Regression:** chạy integration tests của 401/403/302, dispatch, CSRF, path/method boundary, multiple chains, object/tenant policy và side effects.
6. **Quan sát:** bật logging/metrics an toàn để xác định chain nào match, vì sao bị DENY, số lần nạp Authentication và tác động latency.
7. **Loại bỏ legacy:** sau khi mọi test đạt và chính sách tương đương, xóa dependencies/bean legacy không còn được gọi; nếu dùng Spring Security 7 không còn API Access cũ thì không cần `spring-security-access`.

## 14. Tài liệu chính thức

- Spring Security 6.5 — Authorize HTTP Servlet Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorize HTTP Servlet Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Java Configuration / SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet Authorization Migration 7.x: https://docs.spring.io/spring-security/reference/migration/servlet/authorization.html
- Spring Blog — Access API Moves to Spring Security Access: https://spring.io/blog/2025/09/09/access-api-moves-to-spring-security-access/

**Ghi nhớ:** `authorizeHttpRequests` mang theo mô hình thực thi dựa trên `AuthorizationFilter` và `AuthorizationManager`, có thể trì hoãn Authentication lookup nhưng cũng kiểm tra nhiều servlet dispatch. Một migration đúng cần xác minh **ý nghĩa authorization không đổi** trên request, chain, method, tenant và tài nguyên, đặc biệt là các trường hợp DENY.