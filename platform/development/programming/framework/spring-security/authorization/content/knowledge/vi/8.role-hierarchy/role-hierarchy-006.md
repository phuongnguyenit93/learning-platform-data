# Kiểm tra hiệu lực Role hierarchy riêng ở mức HTTP và mức phương thức

Trong Spring Security, định nghĩa **`ROLE_ADMIN > ROLE_STAFF > ROLE_USER`** có nghĩa là khi một cơ chế phân quyền **được cấu hình để sử dụng `RoleHierarchy`**, người có `ROLE_ADMIN` có thể thỏa mãn những yêu cầu dành cho `ROLE_STAFF` và `ROLE_USER`. Tuy nhiên, một ứng dụng có thể kiểm tra quyền tại **hai ranh giới độc lập**: `authorizeHttpRequests` ở HTTP filter chain và `@PreAuthorize` ở method/service. Vì vậy, không được chỉ test một API thành công rồi kết luận rằng role hierarchy đã có hiệu lực **ở mọi nơi**.

Tình huống tiêu biểu: `GET /api/reports/summary` yêu cầu `STAFF` trong `SecurityFilterChain`; service xử lý cũng gắn `@PreAuthorize("hasRole('STAFF')")`. Khi login, principal chỉ có `ROLE_ADMIN`. Nếu HTTP manager hiểu quan hệ **ADMIN ⇒ STAFF** nhưng method expression handler không dùng hierarchy tương ứng, request sẽ vượt qua HTTP rồi nhận **403 ở service**. Ngược lại, nếu method security có hierarchy còn HTTP manager không có, request bị chặn từ filter và **không đến được service**.

Bài học tập trung vào cách **thiết lập, kiểm chứng và chẩn đoán hiệu lực tách biệt của role hierarchy** trong **Spring Security 6.5 / Spring Boot 3.x (Servlet)**, với lưu ý về Spring Security 7.x. Có cấu hình Java dùng trong Spring, ví dụ kiểm thử `MockMvc`/service và một chương trình **Java 17 độc lập** minh họa bốn trạng thái bật/tắt ở hai lớp.

## 1. Role hierarchy là phép bao hàm, không phải sao chép role vào Authentication

Giả sử khai báo:

~~~text
ROLE_ADMIN > ROLE_STAFF
ROLE_STAFF > ROLE_USER
~~~

Ký hiệu `>` nghĩa là **implies / bao hàm**:

~~~text
ROLE_ADMIN
    |
    v
ROLE_STAFF
    |
    v
ROLE_USER
~~~

Với một người được cấp duy nhất `ROLE_ADMIN`, một manager sử dụng role hierarchy có thể xét người đó là thỏa mãn `ROLE_STAFF` và `ROLE_USER` theo **đóng bắc cầu**. Ngược lại, `ROLE_USER` không suy lên `ROLE_STAFF` hoặc `ROLE_ADMIN`. Các quan hệ không có trong đồ thị không được tự suy diễn.

Trong Spring Security, role thông thường được biểu diễn bằng `GrantedAuthority` có tiền tố **`ROLE_`**. Do đó:

- `hasRole("STAFF")` theo quy ước mặc định kiểm tra authority `ROLE_STAFF`.
- `hasAuthority("ROLE_STAFF")` so khớp chuỗi **`ROLE_STAFF`** trực tiếp.
- `hasAuthority("ORDER_READ")` kiểm tra authority nghiệp vụ `ORDER_READ`, không tự thêm `ROLE_`.
- `@WithMockUser(roles = "ADMIN")` trong Spring Security Test thường tạo authority **`ROLE_ADMIN`**, khác `@WithMockUser(authorities = "ADMIN")`.

Khi có hierarchy, phép kiểm tra authority qua những component **đã kết nối `RoleHierarchy`** có thể tính thêm authority suy ra. `RoleHierarchy` **không bắt buộc sửa trực tiếp** danh sách `Authentication.getAuthorities()`; mã tự gọi `authentication.getAuthorities().contains(...)` hoặc so tên role bằng `Set.contains` **không tự thừa kế** quan hệ nếu bạn chưa áp dụng hàm reachable authorities tương ứng.

Ví dụ: source principal chỉ có `ROLE_ADMIN`, method `hasRole('STAFF')` có thể **true** khi method expression handler đã được cấu hình hierarchy; nhưng log `Authentication.getAuthorities()` vẫn có thể chỉ hiển thị `ROLE_ADMIN`. Đây không phải mâu thuẫn: một bên là **input được cấp**, một bên là **quyết định có tính bao hàm**.

## 2. Có hai cửa kiểm tra độc lập: HTTP và method/service

Đường đi thông thường của một HTTP request gọi service được mô tả như sau:

~~~text
HTTP GET /api/reports/summary
         |
         v
SecurityFilterChain
    AuthorizationFilter
    authorizeHttpRequests
    requestMatchers("/api/reports/**").hasRole("STAFF")
         |
         +-- DENY -> xử lý 401/403, controller chưa chạy
         |
         +-- ALLOW
              |
              v
          ReportController
              |
              v
          Spring AOP method interceptor
          @PreAuthorize("hasRole('STAFF')")
              |
              +-- DENY -> AccessDeniedException, service body không chạy
              |
              +-- ALLOW
                   |
                   v
                ReportService.summary()
                   |
                   v
                Kết quả HTTP
~~~

Hai lần kiểm tra có **đầu vào secure object và cơ chế cấu hình khác nhau**:

| Đặc điểm | HTTP authorization | Method authorization |
| --- | --- | --- |
| Hook chính | `SecurityFilterChain` / `authorizeHttpRequests`. | `@EnableMethodSecurity` + AOP interceptor. |
| Đối tượng bảo vệ | HTTP request / request authorization context. | `MethodInvocation`, tham số hoặc return value. |
| Rule tiêu biểu | `.requestMatchers("/api/reports/**").hasRole("STAFF")`. | `@PreAuthorize("hasRole('STAFF')")`. |
| Cách tiếp nhận hierarchy | Các manager dùng trong request authorization cần sử dụng `RoleHierarchy`; với DSL chuẩn 6.5, bean hierarchy được tích hợp theo hướng dẫn chính thức. | `DefaultMethodSecurityExpressionHandler` cần được cấu hình dùng `RoleHierarchy` cho các expression `@PreAuthorize`/`@PostAuthorize`. |
| Có được bật mặc định? | Spring Boot + Security tạo filter chain mặc định nếu app không thay thế bằng bean riêng; rule tùy chỉnh phải khai báo. | **Không**: Spring Boot Starter Security không tự bật method security. |
| Có thể kiểm tra ngoài HTTP không? | Không; cần HTTP request vào chain. | Có: gọi service qua Spring proxy từ job, consumer, controller khác hoặc test. |
| Fail có thể quan sát ở đâu? | Trước controller. | Sau khi đã qua HTTP (nếu bắt đầu từ HTTP), hoặc trực tiếp tại service khi gọi từ nơi khác. |

Nếu request bắt đầu từ HTTP rồi gọi method thật sự được proxy bảo vệ, **cả hai điều kiện đều phải cho phép** để tới logic nghiệp vụ. Điều này **không có nghĩa chỉ cần cấu hình hai lớp cho đúng một lần**: bật hierarchy ở một lớp chưa chứng minh lớp còn lại dùng nó.

Đặc biệt với `@PreAuthorize`, `hasRole` trong SpEL được đánh giá qua expression handler của **method security**, không được thay thế bằng HTTP matcher. Nếu gọi service từ message consumer không đi qua HTTP, chỉ các điều kiện **method/domain** thực sự được áp dụng.

## 3. Ma trận kết quả khi bật hierarchy ở một hoặc cả hai nơi

Xét cùng một người có `ROLE_ADMIN`, yêu cầu `ROLE_STAFF`, quan hệ `ROLE_ADMIN > ROLE_STAFF`:

| HTTP hiểu hierarchy? | Method hiểu hierarchy? | Request HTTP vượt filter? | Gọi service qua proxy được phép? | Kết quả request tổng hợp |
| --- | --- | --- | --- | --- |
| Có | Có | **ALLOW** | **ALLOW** | Đến service (nếu không có policy khác từ chối). |
| Có | Không | **ALLOW** | **DENY** | Có thể 403 ở method. |
| Không | Có | **DENY** | **ALLOW** nếu gọi service trực tiếp từ entry point hợp lệ | Request HTTP bị chặn trước controller. |
| Không | Không | **DENY** | **DENY** | Request bị chặn. |

Trong khi đó, người được cấp **trực tiếp `ROLE_STAFF`** có thể qua cả hai rule `hasRole("STAFF")` ngay cả khi hierarchy không được dùng. Vì vậy, **test bằng user STAFF không chứng minh inheritance hoạt động**. Phải có ca kiểm thử người chỉ có **ROLE_ADMIN** nhưng cần **STAFF**, và một ca **ROLE_USER** bị từ chối khi cần STAFF.

Để test sự bắc cầu, thử `ROLE_ADMIN > ROLE_STAFF > ROLE_USER`: người chỉ có ADMIN cần đạt yêu cầu USER ở lớp đã bật hierarchy. Để test chiều ngược, dùng USER gọi endpoint ADMIN và bảo đảm **DENY**.

Một response 200 cũng chưa đủ: có thể HTTP rule là `permitAll`, controller không hề gọi service được gắn `@PreAuthorize`, hoặc Spring AOP proxy bị bỏ qua. Test phải đánh trúng **cả hai điểm chặn**.

## 4. Định nghĩa chung một RoleHierarchy có thể tái sử dụng

Trong Spring Security 6.5, có thể khai báo bean `RoleHierarchy` bằng `RoleHierarchyImpl.fromHierarchy(...)`. Ví dụ tạo đồ thị rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class RoleHierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_STAFF
                ROLE_STAFF > ROLE_USER
                """);
    }
}
~~~

Đây là **cấu hình Spring**, cần Spring Security dependency và Java 17+. `RoleHierarchyImpl` tính các authority có thể đạt tới qua quan hệ trực tiếp và bắc cầu. Dùng **một bean thống nhất** giúp giảm rủi ro HTTP hiểu một hierarchy trong khi service hiểu một hierarchy khác.

Trong các phiên bản Spring Security có builder, cũng có thể khai báo theo kiểu:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
            .role("ADMIN").implies("STAFF")
            .role("STAFF").implies("USER")
            .build();
}
~~~

Hai ví dụ là **hai cách thay thế** để tạo bean `RoleHierarchy` cùng ngữ nghĩa; không khai báo cả hai bean mặc định có tên giống nhau. Ví dụ builder `withDefaultRolePrefix` có chủ đích dùng `ROLE_`. Nếu tổ chức dùng custom role prefix, hãy thống nhất `GrantedAuthorityDefaults`, raw authorities, hierarchy builder và cả HTTP/method tests. Không đổi prefix chỉ ở một trong hai lớp rồi suy rằng kết quả luôn đồng nhất.

**Kiểm tra chính đồ thị:** gọi `RoleHierarchy#getReachableGrantedAuthorities` với một input chứa `new SimpleGrantedAuthority("ROLE_ADMIN")`. Kết quả kỳ vọng bao gồm `ROLE_ADMIN`, `ROLE_STAFF`, `ROLE_USER`. Đây là **unit test của hierarchy**, chưa chứng minh web filter hoặc method expression handler đang thực sự dùng bean đó.

## 5. Kết nối hierarchy vào HTTP authorization

Trong Spring Security **6.5**, tài liệu Authorization Architecture hỗ trợ bean `RoleHierarchy` cho `HttpSecurity#authorizeHttpRequests`; với DSL chuẩn, có thể khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpRoleHierarchyConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasRole("STAFF")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/profile/**")
                    .hasRole("USER")
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **lớp cấu hình Spring Boot / Spring Security 6.5**, cần đặt cùng application context với bean `RoleHierarchy`, nguồn xác thực và controller thật. `httpBasic` được dùng để minh họa behavior khi chưa đăng nhập; ứng dụng JWT có thể dùng `oauth2ResourceServer` thay thế với mapping authorities phù hợp.

Với người chỉ có `ROLE_ADMIN`:

- `GET /api/reports/summary` yêu cầu `STAFF`; nếu HTTP manager dùng `RoleHierarchy`, **được đi tiếp** tới controller.
- `GET /api/profile/me` yêu cầu `USER`, quan hệ ADMIN ⇒ STAFF ⇒ USER cũng cho đi tiếp.
- `GET /api/admin/users` yêu cầu `ADMIN`, quyền trực tiếp đã đủ.
- `POST /api/reports/summary` **không tự được phép** từ rule GET; không có rule khác nên `denyAll`.
- Một user chỉ có `ROLE_USER` không tự đạt `ROLE_STAFF` hay `ROLE_ADMIN`.

Với `authorizeHttpRequests`, **matcher đầu tiên khớp** sẽ quyết định rule. Đặt một `requestMatchers("/api/**").authenticated()` rộng trước rule reports sẽ khiến reports không được kiểm tra STAFF ở HTTP, dù role hierarchy có được cấu hình đúng. Điều đó có thể làm test inheritance cho kết quả sai. Thứ tự matcher và HTTP method phải được kiểm tra riêng.

### Khi dùng manager tự tạo, đừng giả định bean được sử dụng

Ngoài DSL `.hasRole("STAFF")`, ứng dụng có thể tự tạo `AuthorityAuthorizationManager`:

~~~java
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

AuthorityAuthorizationManager<RequestAuthorizationContext> staffRequired =
        AuthorityAuthorizationManager.hasRole("STAFF");

staffRequired.setRoleHierarchy(roleHierarchy);

// Đặt vào authorizeHttpRequests DSL:
// .requestMatchers("/api/reports/**").access(staffRequired)
~~~

Đoạn này **không phải class đầy đủ**, giả định biến `roleHierarchy` đã được inject. Điểm quan trọng là `AuthorityAuthorizationManager` có `setRoleHierarchy(...)`; khi tự khởi tạo manager, bạn phải xác minh có truyền hierarchy thật hay không. Theo API 6.5, `AuthorityAuthorizationManager` có hierarchy mặc định `NullRoleHierarchy` nếu chưa cấu hình, nên manager tự tạo có thể chỉ so authority trực tiếp, ngay cả khi application context có một bean `RoleHierarchy`.

Các component tùy biến khác (custom `AuthorizationManager`, permission evaluator hoặc lambda tự duyệt `authentication.getAuthorities()`) cũng **không tự có tính bắc cầu** nếu implementation không áp dụng hierarchy. Một test dùng URL qua DSL chuẩn không bảo đảm custom manager ở URL khác cho kết quả giống nhau.

### Nhiều SecurityFilterChain cũng cần test riêng

Nếu ứng dụng có các bean chain cho `/api/**` và `/admin/**`, `FilterChainProxy` chọn **chain đầu tiên match request** theo `@Order`, rồi áp rule trong chain đó. Một chain dùng manager tự tạo có hierarchy, chain khác dùng manager raw authority không có hierarchy thì hai vùng URL có thể hành xử khác nhau. Hãy xác định **chain nào được chọn** và manager nào có role hierarchy; không chỉ nhìn bean `RoleHierarchy` toàn cục.

## 6. Kết nối hierarchy vào method security — bước hay bị thiếu

Spring Boot Starter Security **không tự bật method security**. Bật trong configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityEnabler {
}
~~~

Với `@PreAuthorize` và `@PostAuthorize`, Spring Security dùng `MethodSecurityExpressionHandler`. Tài liệu Spring Security 6.5 hướng dẫn công bố **bean expression handler dạng `static`**, gán cùng `RoleHierarchy` đã định nghĩa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class HierarchicalMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
~~~

**Vì sao là `static`?** Spring Security cần thấy handler trước khi khởi tạo những configuration class của method security. Đây là cách tài liệu chính thức trình bày để tránh bean được publish quá muộn. Đừng tạo handler bằng `new` bên trong service rồi mong `@PreAuthorize` tự chuyển sang dùng handler ấy.

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('STAFF')")
    public String summary() {
        return "summary";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String audit() {
        return "audit";
    }
}
~~~

Khi một Spring bean khác gọi `reportService.summary()` **qua proxy**, người chỉ có `ROLE_ADMIN` được phép nếu method handler có hierarchy ADMIN ⇒ STAFF; người chỉ có `ROLE_USER` bị chặn. Nếu gọi `reportService.audit()`, chỉ ADMIN hoặc một role được hierarchy khai báo bao hàm ADMIN mới được phép.

**Giới hạn AOP proxy:** gọi `this.summary()` từ method khác trong cùng instance, hoặc tạo service bằng `new ReportService()` ngoài Spring, có thể **không kích hoạt method-security interceptor**. Khi đó “method test PASS” có thể là false positive nếu bạn không kiểm tra proxy. Dùng bean do container quản lý và test với cả trường hợp thiếu quyền phải ném `AccessDeniedException`.

`@PreAuthorize` không phải giải pháp duy nhất cho mọi policy nghiệp vụ. Role hierarchy chỉ mô tả quan hệ giữa authorities; quyền trên **đúng báo cáo, chi nhánh, tenant, chủ sở hữu và trạng thái tài nguyên** vẫn cần policy domain.

## 7. Kết hợp cả hai lớp trong một endpoint thực tế

Ví dụ controller inject service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/reports/summary")
    public String summary() {
        return reportService.summary();
    }
}
~~~

Giả định ứng dụng đăng ký **cùng lúc** những thành phần:

1. `RoleHierarchy` bean có ADMIN ⇒ STAFF ⇒ USER.
2. `SecurityFilterChain` ở mục 5 có `GET /api/reports/**` yêu cầu `hasRole("STAFF")`.
3. `@EnableMethodSecurity` và `MethodSecurityExpressionHandler` ở mục 6.
4. `ReportService` được Spring quản lý, controller inject bean của nó.
5. Cơ chế authentication tạo `Authentication` chứa chính xác `ROLE_ADMIN` cho admin.

Khi ADMIN gọi endpoint:

~~~text
REQUEST GET /api/reports/summary
    |
    +-- HTTP: hasRole(STAFF) với hierarchy
    |           ROLE_ADMIN => ROLE_STAFF => ALLOW
    |
    +-- Controller gọi service bean qua proxy
                |
                +-- @PreAuthorize hasRole(STAFF) với method hierarchy
                           ROLE_ADMIN => ROLE_STAFF => ALLOW
                |
                +-- ReportService.summary() trả "summary"
~~~

Nếu bỏ **handler method** nhưng vẫn bật `@EnableMethodSecurity`, tùy cấu hình/version, request có thể vượt qua HTTP và bị từ chối ở `@PreAuthorize`. Nếu bỏ **`@EnableMethodSecurity`**, method annotation có thể **không được áp dụng**; khi đó request 200 không hề chứng minh method hierarchy hoạt động. Nếu đổi HTTP thành `permitAll`, test 200 cũng không chứng minh HTTP hierarchy có tác dụng.

Với Spring Security 6.5 và cấu hình nêu trên, role hierarchy có thể được dùng cho cả HTTP và pre/post method expressions. Tuy nhiên, việc tổng hợp “một bean tự động cho toàn bộ dự án” **không đúng** cho mọi API, phiên bản, custom manager hoặc interceptor. Hãy thực sự chạy kiểm thử các điểm chặn.

## 8. Kiểm thử riêng chính RoleHierarchy trước khi kiểm thử các lớp

Bắt đầu với đồ thị, kiểm tra input chỉ có `ROLE_ADMIN`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.beans.factory.annotation.Autowired;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RoleHierarchyGraphTest {

    @Autowired
    RoleHierarchy hierarchy;

    @Test
    void adminReachesStaffAndUser() {
        Set<String> actual = hierarchy.getReachableGrantedAuthorities(
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")))
            .stream().map(a -> a.getAuthority())
            .collect(Collectors.toSet());

        assertEquals(Set.of("ROLE_ADMIN", "ROLE_STAFF", "ROLE_USER"), actual);
    }
}
~~~

Đây là **minh họa phần test trong Spring/JUnit**, cần đặt trong một test class được Spring Test context quản lý (chẳng hạn thêm `@SpringBootTest`) mới inject được `@Autowired`. Đừng copy riêng class rồi kỳ vọng field `hierarchy` tự được inject ở JUnit thuần. Test này kiểm tra mapping chính xác của đồ thị **nhưng chưa kiểm tra manager HTTP/method có đang dùng nó không**.

Với nhiều quan hệ, cần test cả chiều đúng/chiều sai, ví dụ:

| Principal được cấp trực tiếp | Quyền/role yêu cầu | Reachable? |
| --- | --- | --- |
| `ROLE_ADMIN` | `ROLE_ADMIN` | Có: trực tiếp. |
| `ROLE_ADMIN` | `ROLE_STAFF` | Có: một bước. |
| `ROLE_ADMIN` | `ROLE_USER` | Có: bắc cầu. |
| `ROLE_STAFF` | `ROLE_USER` | Có: một bước. |
| `ROLE_STAFF` | `ROLE_ADMIN` | **Không**: không suy ngược. |
| `ROLE_USER` | `ROLE_STAFF` | **Không**. |
| Không xác thực | `ROLE_STAFF` | Không được tự cấp quyền. |

Đừng chỉ dùng role ADMIN trong mọi test: phải có ca STAFF, USER và anonymous để bảo đảm hierarchy không bị mở quá rộng, nhất là khi tổ chức bổ sung role mới.

## 9. Test HTTP hierarchy bằng MockMvc: chứng minh filter nhận vai trò kế thừa

Với controller/service ở mục 6–7 và `SecurityFilterChain` ở mục 5, test HTTP bằng `MockMvc` để kiểm tra **một user chỉ có ROLE_ADMIN** có thể vào endpoint yêu cầu STAFF. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpHierarchyIT {
    @Autowired MockMvc mvc;

    @Test
    void adminCanEnterStaffReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("summary"));
    }

    @Test
    void userCannotEnterStaffReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(user("user").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

Cần `spring-boot-starter-test` và `spring-security-test`, cùng controller/service và cấu hình đúng. Đây là **mã test trong một Spring Boot project**, không chạy bằng JDK thuần. Nếu `spring-security-test` không được tích hợp với MVC test context, mô phỏng principal có thể không đi qua filter đúng cách; hãy dùng `@SpringBootTest` và `@AutoConfigureMockMvc` hoặc cấu hình filter đúng với test slice.

**Quan trọng về phạm vi chứng minh:** bài test gọi endpoint thật, nên một 200 chứng minh **tổng hợp** các lớp đã cho phép. Để khẳng định riêng **HTTP hierarchy**:

- Dùng một endpoint test chỉ có HTTP rule và **không có method annotation**, hoặc
- Test trực tiếp `AuthorizationManager` mà rule HTTP đang dùng, hoặc
- Dùng instrumentation/spies để xác nhận controller có/không được gọi theo từng trường hợp, tránh chỉ dựa vào mã 403 không rõ nguồn.

Ví dụ endpoint fixture chỉ có HTTP rule `/api/reports/**` nhưng không gọi service phương thức được bảo vệ; nếu admin chỉ có ADMIN gọi thành công còn USER bị 403 **trước controller**, chứng minh HTTP manager nhìn thấy quan hệ ADMIN ⇒ STAFF.

Nếu `ROLE_STAFF` test 200, đây chỉ chứng minh direct match, **không** chứng minh `RoleHierarchy` hoạt động. Trong test `with(user(...).roles("ADMIN"))`, để chắc chắn không bị test fixture vô tình thêm role STAFF, kiểm tra/mock principal chỉ mang `ROLE_ADMIN` ban đầu.

## 10. Test method hierarchy trực tiếp: không đi qua HTTP

Để kiểm tra `@PreAuthorize` độc lập với filter chain, inject service **qua Spring proxy** và gọi trong test security context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodHierarchyIT {

    @Autowired ReportService reports;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminInheritsStaffAtMethod() {
        assertEquals("summary", reports.summary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallStaffMethod() {
        assertThrows(AccessDeniedException.class, reports::summary);
    }

    @Test
    @WithMockUser(roles = "STAFF")
    void staffCannotCallAdminMethod() {
        assertThrows(AccessDeniedException.class, reports::audit);
    }
}
~~~

Bộ test này **không có HTTP request**. Nếu test đầu pass và hai test negative đều từ chối đúng, bạn đã có bằng chứng method security đang thực thi và role hierarchy áp dụng theo mong muốn. Nếu `@EnableMethodSecurity` bị thiếu, các ca `assertThrows` là tín hiệu rõ ràng (method sẽ chạy thay vì ném lỗi). Tuy nhiên, nếu service bị kiểm tra bằng một custom interceptor khác hoặc `@PreAuthorize` bị override, vẫn cần rà soát bean thực và configuration.

Một lỗi rất khó thấy là gọi `reports.summary()` trên instance tự tạo bằng `new` trong unit test, thay vì bean từ Spring: annotation có thể không hoạt động, **không thể dùng test đó để xác nhận method security**. Với `@SpringBootTest` nên inject chính proxy Spring quản lý. `@WithMockUser` tạo context trong test thread, nhưng không tự truyền context sang mọi executor nếu service còn chạy `@Async`.

### Test phương thức có hiệu lực ở nhiều entry point

Method security đáng giá vì service có thể được gọi từ HTTP controller, message listener, batch job hoặc service khác. Khi một entry point không đi qua HTTP, rule `authorizeHttpRequests` không được áp dụng; `@PreAuthorize` vẫn là lớp chặn nếu lời gọi đi qua proxy và có `Authentication` tương ứng. Nếu job không có user context thì phải thiết kế service identity/ủy quyền rõ ràng, không dùng role hierarchy để cấp mặc định ADMIN.

## 11. Vì sao chỉ có một Bean RoleHierarchy vẫn có thể xảy ra lệch hiệu lực?

Có ít nhất bảy nhóm nguyên nhân độc lập:

1. **Method security chưa bật:** `@EnableMethodSecurity` bị quên. `@PreAuthorize` không được thực thi dù HTTP manager dùng hierarchy đúng.
2. **Thiếu custom MethodSecurityExpressionHandler:** `RoleHierarchy` bean có thể được HTTP sử dụng nhưng method SpEL không tự dùng đúng instance trong cấu hình/phiên bản đang chạy. Spring Security 6.5 hướng dẫn thêm `static MethodSecurityExpressionHandler` với `setRoleHierarchy`.
3. **Custom HTTP AuthorizationManager:** manager tự viết hoặc `AuthorityAuthorizationManager` tạo thủ công chưa gọi `setRoleHierarchy`, nên `hasRole("STAFF")` ở chỗ đó chỉ kiểm tra trực tiếp `ROLE_STAFF`.
4. **Sai matcher hoặc sai SecurityFilterChain:** request vào rule `authenticated()`/`permitAll()` rộng trước, hoặc chain khác được chọn. Test 200 có thể không hề chạm rule `STAFF`.
5. **Method call bỏ qua Spring proxy:** tự gọi `this.method()`, tạo object bằng `new`, hoặc reflection/kết nối framework không đi qua interceptor thích hợp.
6. **Authorities không đúng prefix:** principal có `ADMIN` nhưng rule `hasRole("ADMIN")` kỳ vọng `ROLE_ADMIN`; hoặc JWT scope chỉ tạo `SCOPE_admin`, không tự biến thành `ROLE_ADMIN`.
7. **Các loại method annotation dùng manager riêng:** `@Secured` và `@RolesAllowed` có các interceptor/manager khác với `@PreAuthorize`. Bật annotation nhưng không xác minh hierarchy ở chính manager đó có thể làm hành vi khác SpEL.

Trong hệ thống có nhiều application contexts/child context, bean `RoleHierarchy` và expression handler phải được tạo trong **context đúng nơi security configuration khởi tạo**. Nếu cấu hình bị giấu ở một package không được component scan, chỉ nhìn file source không chứng minh bean đã tồn tại.

**Cách chẩn đoán:** trước hết test reachable graph; kế đến test HTTP độc lập; rồi test method trực tiếp; cuối cùng test endpoint tích hợp. Trình tự này chỉ ra **chính xác lớp bị lệch** mà không cần nới lỏng bảo mật để đoán.

## 12. `@Secured` và `@RolesAllowed` cần kiểm tra riêng

`@PreAuthorize` và `@PostAuthorize` là **pre/post expressions**. Spring Security cũng hỗ trợ:

- `@Secured("ROLE_STAFF")`, cần `@EnableMethodSecurity(securedEnabled = true)`.
- `@RolesAllowed("STAFF")` thuộc JSR-250, dùng import `jakarta.annotation.security.RolesAllowed` trên Spring Boot 3, cần `@EnableMethodSecurity(jsr250Enabled = true)`.

Ví dụ:

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
class ExtraMethodAnnotationsConfig {
}
~~~

Đây là **một phương án cấu hình method-security** nếu ứng dụng thực sự dùng hai loại annotation đó. Nếu đã có `@EnableMethodSecurity` từ một configuration khác, không copy bừa một annotation nữa: hãy gom các cờ vào **một điểm cấu hình** thống nhất theo nhu cầu.

Các annotation không nhất thiết dùng cùng `MethodSecurityExpressionHandler`:

| Loại rule ở service | Thành phần cần quan sát | Cách xác nhận |
| --- | --- | --- |
| `@PreAuthorize("hasRole('STAFF')")` | `PreAuthorizeAuthorizationManager` + `MethodSecurityExpressionHandler`. | Test trực tiếp service, ADMIN pass STAFF, USER fail STAFF. |
| `@PostAuthorize(...)` | `PostAuthorizeAuthorizationManager` + expression handler. | Chỉ dùng hậu kiểm với thao tác phù hợp, không dựa vào nó để ngăn side effect đã xảy ra. |
| `@Secured("ROLE_STAFF")` | `SecuredAuthorizationManager` khi securedEnabled. | Test service annotated bằng `@Secured` riêng. |
| `@RolesAllowed("STAFF")` | `Jsr250AuthorizationManager` khi jsr250Enabled. | Test service annotated bằng `@RolesAllowed` riêng. |

Tài liệu Spring Security 6.5 Authorization Architecture mô tả hỗ trợ role hierarchy cho cả filter-based và các loại method-based này. Nhưng nếu app tùy biến interceptor, sử dụng code cũ hoặc manager riêng, không được suy rằng chúng dùng cùng hierarchy; phải **test từng loại annotation đang dùng**.

Đối với JSR-250, `@PermitAll` và `@DenyAll` là quy tắc riêng, không tương đương một role. Một hierarchy ADMIN ⇒ STAFF không thể làm `@DenyAll` trở thành ALLOW.

## 13. Phân biệt RoleHierarchy với các loại “quyền kế thừa” khác

`RoleHierarchy` giải quyết **authority reachability**, không tự sinh quy tắc nghiệp vụ hay bảo đảm rằng mọi điều kiện trong ứng dụng đều dùng hierarchy:

| Cơ chế | Ví dụ | Role hierarchy làm gì? |
| --- | --- | --- |
| `hasRole("STAFF")` trong HTTP DSL có hierarchy | ADMIN ⇒ STAFF | Có thể cho phép ADMIN qua rule STAFF. |
| `@PreAuthorize("hasRole('STAFF')")` có handler dùng hierarchy | ADMIN ⇒ STAFF | Có thể cho phép method chạy. |
| Raw `Authentication.getAuthorities()` | Chỉ chứa `ROLE_ADMIN` | **Không tự mutate** authorities gốc. |
| JWT `scope`/`scp` mapped thành `SCOPE_read` | Chỉ có `SCOPE_read` | Không tự chuyển sang `ROLE_STAFF`; cần mapping/relationship rõ ràng. |
| `hasPermission(order, 'write')` / custom policy | Order thuộc tenant A | Không tự kiểm tra owner/tenant/status. |
| Feature flag / plan subscription | Chỉ premium mới được export | Phải có rule riêng, không suy từ role. |
| UI menu hiển thị cho ADMIN | Nút “Export” hiện ra | Không bảo đảm server cấp quyền đúng. |
| Job chạy ngoài HTTP không có SecurityContext | Scheduler gọi service | Cần authentication/service identity và policy phù hợp. |

Nếu mô hình quyền là `ROLE_ADMIN > REPORT_READ`, `RoleHierarchyImpl` có thể mô tả quan hệ từ role tới authority permission và manager có hierarchy có thể xét `hasAuthority("REPORT_READ")`. Nhưng đây là **lựa chọn kiến trúc**, không phải mặc định. Hãy ghi rõ ý nghĩa permission và test đúng prefix. Đừng dùng role hierarchy để vô tình cho phép STAFF thực hiện hành động mà doanh nghiệp định chỉ ADMIN được làm.

Với hệ đa tenant, một admin của **shop-A** không vì `ROLE_ADMIN > ROLE_STAFF` mà được đọc report thuộc **shop-B**. Nếu role của họ có phạm vi tenant, cần bổ sung dữ liệu tenant vào policy hoặc biểu diễn authority có scope rõ ràng; đừng trộn quan hệ role toàn hệ thống với quyền trên từng tài nguyên.

## 14. Ví dụ Java 17 độc lập: bốn chế độ hierarchy của hai lớp

Ví dụ sau **không dùng thư viện Spring** và **không thay thế kiểm thử Spring Boot**. Nó mô phỏng một đồ thị role bằng `Map<String, Set<String>>`, duyệt quan hệ kế thừa theo BFS và hai cờ `httpHierarchy`/`methodHierarchy`. Mục đích là trực quan hóa **chính xác lý do phải kiểm tra HTTP và method riêng**.

Quy tắc:

- Principal trực tiếp có ADMIN, STAFF hoặc USER; không chèn tự động role kế thừa vào tập gốc.
- Nếu cờ hierarchy của một lớp bật, lớp đó xét role trực tiếp **hoặc** role đạt tới qua đồ thị.
- Nếu cờ tắt, lớp đó chỉ xét tập role trực tiếp.
- ADMIN ⇒ STAFF ⇒ USER một chiều; không suy ngược.
- Điều kiện tenant là policy độc lập; hierarchy không biến khác tenant thành hợp lệ.

Lưu đúng tệp **`RoleHierarchyLayersDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Set;

public class RoleHierarchyLayersDemo {
    private static final Map<String, Set<String>> INHERITS = Map.of(
            "ROLE_ADMIN", Set.of("ROLE_STAFF"),
            "ROLE_STAFF", Set.of("ROLE_USER"));

    static boolean allowed(Set<String> granted, String required,
                           boolean useHierarchy) {
        if (granted == null || granted.isEmpty()) return false;
        if (!useHierarchy) return granted.contains(required);
        Deque<String> queue = new ArrayDeque<>(granted);
        Set<String> visited = new java.util.HashSet<>();
        while (!queue.isEmpty()) {
            String role = queue.removeFirst();
            if (!visited.add(role)) continue;
            if (role.equals(required)) return true;
            queue.addAll(INHERITS.getOrDefault(role, Set.of()));
        }
        return false;
    }

    static String compare(Set<String> granted, String required,
                          boolean httpHierarchy, boolean methodHierarchy) {
        return "HTTP=" + allowed(granted, required, httpHierarchy)
                + ", METHOD=" + allowed(granted, required, methodHierarchy);
    }

    public static void main(String[] args) {
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> staff = Set.of("ROLE_STAFF");
        Set<String> user = Set.of("ROLE_USER");

        System.out.println("ADMIN -> STAFF, both on: "
                + compare(admin, "ROLE_STAFF", true, true));
        System.out.println("ADMIN -> STAFF, only HTTP: "
                + compare(admin, "ROLE_STAFF", true, false));
        System.out.println("ADMIN -> STAFF, only method: "
                + compare(admin, "ROLE_STAFF", false, true));
        System.out.println("ADMIN -> STAFF, both off: "
                + compare(admin, "ROLE_STAFF", false, false));
        System.out.println("ADMIN -> USER, both on: "
                + compare(admin, "ROLE_USER", true, true));
        System.out.println("STAFF -> ADMIN, both on: "
                + compare(staff, "ROLE_ADMIN", true, true));
        System.out.println("USER -> USER, both off: "
                + compare(user, "ROLE_USER", false, false));
        System.out.println("Anonymous -> STAFF, both on: "
                + compare(Set.of(), "ROLE_STAFF", true, true));
        System.out.println("Raw ADMIN authorities contain STAFF: "
                + admin.contains("ROLE_STAFF"));
        System.out.println("ADMIN -> STAFF across tenant? "
                + (allowed(admin, "ROLE_STAFF", true)
                        && "shop-a".equals("shop-b")));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 RoleHierarchyLayersDemo.java
java RoleHierarchyLayersDemo
~~~

Kết quả chính xác:

~~~text
ADMIN -> STAFF, both on: HTTP=true, METHOD=true
ADMIN -> STAFF, only HTTP: HTTP=true, METHOD=false
ADMIN -> STAFF, only method: HTTP=false, METHOD=true
ADMIN -> STAFF, both off: HTTP=false, METHOD=false
ADMIN -> USER, both on: HTTP=true, METHOD=true
STAFF -> ADMIN, both on: HTTP=false, METHOD=false
USER -> USER, both off: HTTP=true, METHOD=true
Anonymous -> STAFF, both on: HTTP=false, METHOD=false
Raw ADMIN authorities contain STAFF: false
ADMIN -> STAFF across tenant? false
~~~

**Giải thích:** hai dòng “only HTTP” và “only method” là hai dạng **cấu hình không đồng nhất**. Dòng “Raw ADMIN authorities contain STAFF: false” nhắc rằng không nhất thiết tồn tại `ROLE_STAFF` trong raw principal, dù policy tính inheritance đúng. Dòng tenant cho thấy riêng việc đạt role STAFF không đủ để đọc tài nguyên khác tenant.

`Set.of("ROLE_ADMIN")` là mẫu role giả lập, không phải Spring `Authentication`. Hàm BFS chỉ mô tả logic đồ thị; trong sản phẩm thật, **hãy dùng `RoleHierarchyImpl` và authorization managers của Spring Security**, không sao chép thuật toán demo vào security filter.

## 15. Đặt test ở đâu để tách được một lỗi HTTP khỏi một lỗi method?

Dưới đây là **ma trận kiểm thử theo điểm chặn**, tránh nhầm “một request pass” với “cả hai hệ thống hoạt động”:

| Ca thử | Test HTTP/MockMvc | Test method/service | Điều chứng minh |
| --- | --- | --- | --- |
| Admin chỉ có `ROLE_ADMIN`, yêu cầu STAFF | GET endpoint cần STAFF → qua filter | Gọi service `@PreAuthorize(STAFF)` → ALLOW | Kế thừa tại **từng** lớp. |
| STAFF yêu cầu STAFF | ALLOW | ALLOW | Direct authority match, **chưa chứng minh inheritance**. |
| USER yêu cầu STAFF | DENY | `AccessDeniedException` | Không mở rộng sai chiều. |
| Admin yêu cầu USER qua chuỗi ADMIN ⇒ STAFF ⇒ USER | ALLOW | ALLOW | Tính bắc cầu. |
| Anonymous yêu cầu STAFF | 401/redirect nếu có entry point thích hợp | DENY nếu thiếu auth | Không tự cấp quyền. |
| Admin yêu cầu một role không trong đồ thị | DENY | DENY | Không suy diễn role không khai báo. |
| Admin có ROLE_STAFF suy ra nhưng report khác tenant | HTTP có thể ALLOW theo role | Service/domain policy phải DENY | Hierarchy **không vượt qua điều kiện dữ liệu**. |
| Self-invocation gọi method được annotate | HTTP có thể ALLOW | Kiểm thử phát hiện bypass proxy | Không kết luận an toàn từ annotation trên method. |
| App dùng `@Secured` / `@RolesAllowed` | Không liên quan trực tiếp | Test riêng từng annotation | Mỗi manager phải được kiểm chứng. |
| API chain A, chain B hoặc route không match | Xác định đúng chain và rule | Không thay thế HTTP test | Không có vùng URL bỏ qua SecurityFilterChain. |

**Chiến lược mạnh nhất:** test một đường HTTP chỉ có rule web và fixture handler không có method annotation; test một service bảo vệ bằng method annotation gọi trực tiếp qua proxy; rồi test đường tích hợp HTTP→controller→service. Khi đó nếu test thất bại, biết ngay **vị trí cấu hình** cần sửa.

Một lỗi HTTP có thể trả **403 trước controller**, còn lỗi method thông thường ném **`AccessDeniedException`** từ AOP interceptor và có thể được web exception handler chuyển thành 403. Vì vậy **hai response 403 trông giống nhau không chứng minh nguyên nhân giống nhau**. Dùng test fixture/trace để phân biệt.

## 16. Khác biệt phiên bản Spring Security 6.5 và 7.x

Các đoạn chính của bài dùng **API và tài liệu Spring Security 6.5**. Ở dòng **Spring Security 7.x**, tài liệu giới thiệu thêm `AuthorizationManagerFactory<T>` và `DefaultAuthorizationManagerFactory<T>` để tạo/cấu hình các request- và method-based `AuthorizationManager` theo một cơ chế chung. Có thể cấu hình `RoleHierarchy`, `rolePrefix` và các thuộc tính liên quan của factory; đây là hướng mới phù hợp khi thiết kế ứng dụng 7.x.

Không lấy ví dụ `DefaultAuthorizationManagerFactory` của **7.x** rồi chép nguyên vào dự án Spring Security **6.5** nếu API đó chưa tồn tại. Ngược lại, không suy rằng cách dùng bean/custom manager của một codebase 6.x sẽ giống hệt khi nâng major version. Đặc biệt cần kiểm chứng:

- **Role hierarchy được đưa vào HTTP manager như thế nào** (DSL chuẩn, bean, custom manager hoặc factory).
- **Method `@PreAuthorize`/SpEL dùng expression handler nào**.
- `@Secured`, JSR-250 và các annotation khác có đang được bật không.
- Đường dẫn và matcher của HTTP chain, đặc biệt khi nâng cấp cùng lúc RequestMatcher API.
- Custom role prefix `ROLE_` và mapping authorities từ JWT/DB.
- Các custom `AuthorizationManager` tự khởi tạo có hiểu reachable authorities hay không.

Chính sách đúng phải được chứng minh bằng **integration tests chạy trên version mà dự án dùng**; không dựa vào một câu nói chung rằng Spring “tự nhận role hierarchy”.

## 17. Quy trình xử lý khi API trả 403 dù admin có role cao hơn

Ví dụ ADMIN bị từ chối ở `GET /api/reports/summary` khi dự kiến được quyền STAFF. Làm theo thứ tự:

1. **Xác nhận auth thật:** principal có `ROLE_ADMIN` đúng chính tả/tiền tố không? Hay chỉ có `ADMIN` hoặc `SCOPE_admin`?
2. **Xác nhận đồ thị:** `RoleHierarchy.getReachableGrantedAuthorities([ROLE_ADMIN])` có `ROLE_STAFF` không?
3. **Xác nhận HTTP chain:** URL match đúng `SecurityFilterChain` nào; `/api/reports/**` có bị `authenticated()`/rule rộng hoặc custom `access(...)` chiếm trước?
4. **Kiểm tra riêng HTTP rule:** dùng fixture hoặc manager test, giữ nguyên principal ADMIN chỉ có một role. Không vội mở `permitAll` để che lỗi.
5. **Kiểm tra method security:** `@EnableMethodSecurity` đã được bật chưa; `MethodSecurityExpressionHandler` có `setRoleHierarchy` và được Spring dùng đúng không?
6. **Kiểm tra lời gọi qua proxy:** controller có inject `ReportService` từ Spring không; có `this.summary()` bypass proxy không?
7. **Kiểm tra annotation:** `@PreAuthorize`, `@Secured` hay `@RolesAllowed`? Mỗi loại có interceptor/manager và cờ enable riêng.
8. **Kiểm tra domain policy:** service có thêm điều kiện tenant, owner, trạng thái report hoặc feature flag gây DENY hợp lệ không?
9. **Kiểm tra filter khác:** CSRF, JWT authentication, CORS hoặc custom filter có trả 403 trước AuthorizationFilter không? `permitAll` không phải cách chữa mọi 403.
10. **Lặp test cả ALLOW và DENY:** ADMIN cần STAFF phải được phép, USER cần STAFF vẫn từ chối; ADMIN khác tenant vẫn không được xem report riêng tư.

Trong môi trường dev/test, log/trace security có thể giúp xác định phase từ chối. Không log JWT, cookie, mật khẩu hoặc thông tin cá nhân chỉ để biết user có role gì. Dùng test fixture và request correlation ID khi cần phân tích request nhiều tầng.

### Checklist khi đưa role hierarchy vào production

- [ ] Hierarchy được định nghĩa thành **một quan hệ rõ ràng, kiểm toán được**, không có đường kế thừa vô tình mở quyền cao.
- [ ] `RoleHierarchy` bean tồn tại trong **application context** của security setup đang chạy.
- [ ] HTTP `authorizeHttpRequests` dùng hierarchy cho các rule phù hợp; custom managers được cấu hình riêng khi cần.
- [ ] `@EnableMethodSecurity` đã bật; `MethodSecurityExpressionHandler` dùng hierarchy phù hợp.
- [ ] `@Secured` và JSR-250 (nếu dùng) được bật/cấu hình/test độc lập.
- [ ] `ROLE_` và `hasRole`/`hasAuthority` được dùng nhất quán với JWT/DB/UserDetails.
- [ ] Có test role cao kế thừa role thấp và test role thấp **không** đạt role cao ở cả HTTP/method.
- [ ] Có test service trực tiếp qua proxy để ngăn annotation bị bỏ qua.
- [ ] Có test endpoint thực HTTP→service để phát hiện lệch hai lớp.
- [ ] Có test riêng điều kiện owner/tenant/permission ngoài role.
- [ ] Có regression tests khi nâng phiên bản Spring Security hoặc thay đổi role graph.

**Kết luận:** `RoleHierarchy` là một **cấu trúc quan hệ giữa authorities**, còn hiệu lực của nó phụ thuộc từng **điểm kiểm tra truy cập**. Đối với ứng dụng Servlet/Spring Boot, hãy xác minh riêng **HTTP `authorizeHttpRequests`** và **method `@PreAuthorize` qua Spring proxy**, rồi kiểm tra đường gọi tổng hợp. Một role ADMIN vượt HTTP nhưng bị chặn ở method (hoặc ngược lại) là dấu hiệu hai lớp đang dùng cấu hình khác nhau, không phải lý do để nới lỏng quyền. Luôn giữ kiểm tra phạm vi dữ liệu và tenant độc lập với role inheritance.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Authorization Architecture: Hierarchical Roles](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Method Security: RoleHierarchy và MethodSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — AuthorityAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security 7.1 — AuthorizationManagerFactory và Hierarchical Roles](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
