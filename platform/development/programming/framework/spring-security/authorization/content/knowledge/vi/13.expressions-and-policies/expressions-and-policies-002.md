# WebSecurityExpressionRoot khác với ngữ cảnh method security

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Biểu thức và chính sách. Bài này tập trung vào Spring Security **Servlet**: biểu thức cấp HTTP request được đánh giá trong ngữ cảnh web, còn biểu thức `@PreAuthorize`/`@PostAuthorize` được đánh giá trong ngữ cảnh lời gọi phương thức. Các ví dụ Java dùng Java 17+ và API thông dụng của Spring Security 6.x/7.x.

## 1. Vì sao cùng một biểu thức mà khác kết quả?

Spring Security dùng Spring Expression Language (SpEL) cho một số quy tắc quyền. Biểu thức như `hasAuthority('report:read')` có thể xuất hiện ở cả web và method security vì hai nơi đều có thông tin `Authentication`. Nhưng **đối tượng gốc (expression root)** và **đối tượng đang được ủy quyền** khác nhau:

- **Web security:** câu hỏi là “HTTP request này có được đi qua filter chain vào ứng dụng không?”. Biểu thức có thông tin về `HttpServletRequest`; `WebSecurityExpressionRoot` có `request` và `hasIpAddress(...)`.
- **Method security:** câu hỏi là “lời gọi method này, với tham số và/hoặc kết quả này, có được phép không?”. Biểu thức được xây từ `MethodInvocation`, có biến tham số như `#p0`, các đối tượng `returnObject`/`filterObject` ở giai đoạn phù hợp.

Ví dụ: Bob có authority `report:read`, nhưng báo cáo ID 1 thuộc Alice. Quy tắc URL cho phép người có `report:read` gọi `GET /api/reports/1`; quy tắc trên service lại từ chối Bob xem báo cáo không thuộc mình. **Web cho qua không đồng nghĩa method cho qua.** Đây là hai lần kiểm tra độc lập, phục vụ hai loại dữ liệu khác nhau.

## 2. Expression root và EvaluationContext là gì?

Khi Spring Security đánh giá SpEL, framework tạo một **EvaluationContext** chứa root, biến, hàm, bean resolver và thông tin liên quan đến điểm cần bảo vệ. Trong biểu thức:

- `hasAuthority('report:read')`: gọi một phương thức trên root; không cần viết `#root.hasAuthority(...)`.
- `authentication.name`: truy cập `Authentication` mà ngữ cảnh bảo mật cung cấp.
- `#p0`: lấy tham số thứ nhất của **method invocation** khi dùng method security.
- `request.method`: truy cập HTTP method thông qua thuộc tính `request` của **web root** trong ngữ cảnh web SpEL.
- `@reportAccess.canRead(authentication, #p0)`: gọi một Spring bean tên `reportAccess`, với dữ liệu người dùng và tham số method.

Đừng đồng nhất **root** với `Authentication`: `Authentication` là danh tính/quyền được sử dụng trong quyết định, còn root đóng gói các phép toán bảo mật cộng với dữ liệu ngữ cảnh của điểm chặn.

Về kiến trúc, lớp nền `SecurityExpressionRoot` cung cấp các phép như `hasRole`, `hasAuthority`, `isAuthenticated`, `permitAll`, `denyAll`. Spring Security mở rộng ngữ nghĩa đó cho web và method, nhưng không tự tạo cùng một bộ biến ở mọi chỗ.

~~~text
                          Authentication
                                |
                Các phép kiểm tra bảo mật chung
                  (SecurityExpressionRoot)
                         /             \
      HTTP Servlet request               Method invocation
               |                                  |
  WebSecurityExpressionRoot          MethodSecurityExpressionRoot
  - request                          - tham số #p0/#p1, #name
  - hasIpAddress(...)                 - returnObject (post)
  - authentication, hasRole...        - filterObject (filter)
               |                                  |
 Web expression evaluation             Method expression evaluation
 (WebExpressionAuthorizationManager)  (@PreAuthorize/@PostAuthorize/...)
~~~

Đây là sơ đồ khái niệm, không phải yêu cầu người viết ứng dụng tự khởi tạo các lớp root. Với các bản Spring Security hiện đại, framework dùng handler/authorization manager để tạo evaluation context. API nội bộ và constructor của root có thể thay đổi giữa các phiên bản; hãy cấu hình qua DSL, annotation hoặc SPI phù hợp.

## 3. WebSecurityExpressionRoot: ngữ cảnh HTTP Servlet

`WebSecurityExpressionRoot` nằm ở package `org.springframework.security.web.access.expression`. Trong web SpEL, nó cung cấp:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `authentication`, `principal` | Đối tượng xác thực/người dùng hiện tại | `authentication.name == 'alice'` |
| `hasAuthority(...)`, `hasRole(...)` | Kiểm tra authority/role | `hasAuthority('report:read')` |
| `request` | `HttpServletRequest` đang được bảo vệ | `request.method == 'GET'` |
| `hasIpAddress(...)` | Kiểm tra IP/CIDR của yêu cầu | `hasIpAddress('192.0.2.0/24')` |
| `permitAll`, `denyAll` | Cho phép/từ chối không phụ thuộc tài nguyên cụ thể | `permitAll` |

`request` là servlet request đang được filter chain xử lý; nó không phải một tham số ngầm định của service method. `hasIpAddress` xét địa chỉ của request theo triển khai của framework; phía sau reverse proxy/load balancer, cần cấu hình nguồn IP đáng tin cậy, không tùy tiện tin header do client tự gửi. Không dùng IP là bằng chứng danh tính duy nhất.

### 3.1. Cấu hình web hiện đại: ưu tiên AuthorizationManager

Với Servlet, dùng `SecurityFilterChain` và `authorizeHttpRequests`:

~~~java
// Trích đoạn trong một @Configuration của ứng dụng Spring Boot.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/*")
                        .hasAuthority("report:read")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Các import chính: `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.http.HttpMethod`, `org.springframework.security.config.Customizer` và `org.springframework.context.annotation.Bean`.

**Điểm rất dễ nhầm:** `.hasAuthority("report:read")` trong DSL này sử dụng `AuthorizationManager` có kiểu rõ ràng; nó **không nhất thiết parse chuỗi SpEL và không nhất thiết tạo `WebSecurityExpressionRoot`**. Sự tồn tại của lớp web root không có nghĩa mọi cấu hình web đều đi qua expression root.

Khi thực sự cần **web SpEL**, có thể dùng `WebExpressionAuthorizationManager`:

~~~java
// Trích đoạn thêm vào authorizeHttpRequests(...), đặt trước anyRequest().
.requestMatchers("/internal/**")
    .access(new WebExpressionAuthorizationManager(
        "hasAuthority('internal:read') and hasIpAddress('192.0.2.0/24')"))
~~~

Import: `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager`. Đây là ví dụ cấu hình **HTTP request**, không phải annotation trên service. Khối IP là địa chỉ dành cho tài liệu minh họa; thay bằng chính sách mạng thật nếu áp dụng. Spring Security khuyến nghị dùng các `AuthorizationManager` có kiểu rõ ràng khi quy tắc có thể diễn đạt bằng API, và dùng expression manager khi cần di chuyển hoặc diễn đạt quy tắc SpEL.

Lược đồ đời mới:

~~~text
HTTP request
 -> SecurityFilterChain / AuthorizationFilter
 -> requestMatchers chọn quy tắc
 -> AuthorizationManager<RequestAuthorizationContext>
    -> hasAuthority(...) qua manager trực tiếp, HOẶC
    -> WebExpressionAuthorizationManager đánh giá web SpEL
 -> cho qua hoặc từ chối trước khi tới controller
~~~

Không dùng `@EnableMethodSecurity` để thay thế `SecurityFilterChain`. Và không cấu hình `WebSecurityExpressionRoot` bằng cách tự tạo một đối tượng rồi truyền vào `@PreAuthorize`; đó không phải đường tích hợp chính thức.

## 4. Method security: ngữ cảnh MethodInvocation

Method security áp dụng khi lời gọi đi qua Spring AOP proxy (hoặc cơ chế interception đã cấu hình), không phụ thuộc việc method được gọi từ controller, scheduled job, message listener hay bean khác. Kích hoạt bằng `@EnableMethodSecurity`.

Handler chuẩn thường là `DefaultMethodSecurityExpressionHandler`; nó tạo context từ `MethodInvocation` và root có các phép chung cùng thông tin gắn với phương thức. Biến được sử dụng theo giai đoạn:

| Biểu thức trong method security | Có ý nghĩa khi nào? | Ví dụ |
| --- | --- | --- |
| `authentication`, `principal` | Khi có `Authentication` trong security context | `authentication.name` |
| `hasAuthority(...)`, `hasRole(...)` | Các biểu thức quyền chung | `hasAuthority('report:read')` |
| `#p0`, `#a0` | Tham số thứ nhất của method được chặn | `#p0 > 0` |
| `#reportId` | Tham số theo tên nếu tên được khám phá hợp lệ | `#reportId == 1` |
| `returnObject` | Kết quả sau khi method chạy, chẳng hạn `@PostAuthorize` | `returnObject.owner() == authentication.name` |
| `filterObject` | Phần tử hiện tại với `@PreFilter` hoặc `@PostFilter` | `filterObject.owner() == authentication.name` |
| `this` | Đối tượng được bảo vệ trong method context | Biểu thức có thể tham chiếu service |
| `@bean.method(...)` | Gọi bean policy để kiểm tra nghiệp vụ | `@reportAccess.canRead(authentication, #p0)` |

**Phân biệt giai đoạn:** trong `@PreAuthorize` chưa có `returnObject` của lời gọi đang chặn; `@PostAuthorize` có thể xét kết quả nhưng thân method đã chạy. `filterObject` chỉ có ý nghĩa khi framework đang lọc phần tử. Đừng dùng một biểu thức có `returnObject` trong `@PreAuthorize` rồi kỳ vọng Spring “biết trước” kết quả.

Ví dụ:

~~~java
// Trích đoạn trong một @Service.
@PreAuthorize("hasAuthority('report:read') and "
        + "@reportAccess.canRead(authentication, #p0)")
public Report findReport(long id) {
    return store.find(id).orElseThrow();
}

@PostAuthorize("returnObject.owner() == authentication.name")
public Report findReportAndCheckAfter(long id) {
    return store.find(id).orElseThrow();
}

@PostFilter("filterObject.owner() == authentication.name")
public List<Report> listVisibleReports() {
    return new ArrayList<>(store.findAll());
}
~~~

Các trích đoạn giả định đã có `Report`, `store`, `reportAccess` trong một Spring service; đây **không phải các file Java chạy độc lập**. `@PostAuthorize` và `@PostFilter` hậu kiểm nên không bảo vệ trước các side effect của phương thức. Với thao tác ghi/xóa, ưu tiên kiểm tra trước, đồng thời bảo vệ tại tầng dữ liệu/giao dịch.

Tên `#reportId` tùy cơ chế khám phá tên tham số (chẳng hạn biên dịch với `-parameters` hoặc annotation hỗ trợ). Dùng `#p0` trong bài này để tránh phụ thuộc tên biến Java. Biểu thức quyền có thể gọi bean Spring bằng cú pháp `@beanName.method(...)`.

### 4.1. Những thứ không “mang theo” từ web root

Trong `@PreAuthorize` trên service, các biểu thức sau **không có ý nghĩa mặc định như ở web SpEL**:

~~~text
hasIpAddress('192.0.2.0/24')   // hàm riêng của web root
request.method == 'POST'        // request không phải biến tự động của method root
request.requestURI              // không tự truyền HttpServletRequest tới method
~~~

Ngược lại, web root không tự có `#p0` của `ReportService.findReport(id)`, `returnObject` hay `filterObject` của service. Dữ liệu path của request có thể được một HTTP authorization manager/matcher cung cấp theo cách riêng, nhưng nó không đồng nghĩa với tham số Java của method đã chạy sau đó.

Nếu policy service cần một thuộc tính bổ sung, hãy truyền dữ liệu được chuẩn hóa rõ ràng qua tham số method hoặc một bean policy (và kiểm tra tính tin cậy của dữ liệu). Không bắt service luôn phụ thuộc vào `HttpServletRequest` chỉ để dùng lại biểu thức URL; background job sẽ không có request tương ứng.

## 5. Ví dụ đầy đủ: cả web lẫn method cùng bảo vệ báo cáo

Ví dụ sau tạo endpoint `GET /api/reports/{id}`. **Lớp web** chỉ xét authority `report:read`; **lớp method** còn yêu cầu người gọi là owner của báo cáo. Đó là hai quyết định khác nhau.

Trong một dự án Spring Boot Servlet đã cấu hình Java 17+ và dependency `spring-boot-starter-web`, `spring-boot-starter-security`, lưu nội dung sau thành `src/main/java/demo/security/AuthorizationExampleApplication.java`. Đây là **một file Java hoàn chỉnh** (một lớp `public` và các kiểu cùng package), không cần database. Demo sử dụng mật khẩu rõ dạng `{noop}` **chỉ cho môi trường học tập**, không dùng cho production.

~~~java
package demo.security;

import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.expression.WebExpressionAuthorizationManager;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationExampleApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/reports/*")
                            .hasAuthority("report:read")
                        .requestMatchers("/internal/**")
                            .access(new WebExpressionAuthorizationManager(
                                    "hasAuthority('internal:read') and "
                                    + "hasIpAddress('192.0.2.0/24')"))
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}demo")
                        .authorities("report:read").build(),
                User.withUsername("bob").password("{noop}demo")
                        .authorities("report:read").build(),
                User.withUsername("visitor").password("{noop}demo")
                        .authorities("profile:read").build());
    }
}

record Report(long id, String owner, String title) {
}

@Component
class ReportStore {
    private final Map<Long, Report> data = Map.of(
            1L, new Report(1L, "alice", "Report A"),
            2L, new Report(2L, "bob", "Report B"));

    Optional<Report> find(long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component("reportAccess")
class ReportAccess {
    private final ReportStore store;

    ReportAccess(ReportStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        return authentication != null
                && store.find(id)
                        .map(r -> r.owner().equals(authentication.getName()))
                        .orElse(false);
    }
}

@Service
class ReportService {
    private final ReportStore store;

    ReportService(ReportStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('report:read') and "
            + "@reportAccess.canRead(authentication, #p0)")
    public Report findReport(long id) {
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Report not found"));
    }
}

@RestController
@RequestMapping("/api/reports")
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Report findReport(@PathVariable long id) {
        return service.findReport(id);
    }
}
~~~

Nếu ứng dụng Boot có cấu hình Gradle chuẩn, dependencies cần thiết là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **khối dependencies cho một dự án đã có Spring Boot plugin và dependency management**, không phải file `build.gradle` độc lập. Khởi động bằng cơ chế dự án đang dùng (ví dụ `./gradlew bootRun` với Gradle wrapper trên Unix; Windows dùng `gradlew.bat bootRun`).

Gửi request (sau khi ứng dụng đang chạy tại `localhost:8080`):

~~~bash
curl -i -u alice:demo http://localhost:8080/api/reports/1
curl -i -u bob:demo http://localhost:8080/api/reports/1
curl -i -u bob:demo http://localhost:8080/api/reports/2
curl -i -u visitor:demo http://localhost:8080/api/reports/1
curl -i http://localhost:8080/api/reports/1
~~~

| Người gọi và URL | Web authorization | Method authorization | Kết quả HTTP kỳ vọng |
| --- | --- | --- | --- |
| Alice → `/api/reports/1` | PASS: có `report:read` | PASS: owner Alice | 200 và JSON báo cáo ID 1 |
| Bob → `/api/reports/1` | PASS: có `report:read` | DENY: owner Alice | 403 |
| Bob → `/api/reports/2` | PASS: có `report:read` | PASS: owner Bob | 200 và JSON báo cáo ID 2 |
| Visitor → `/api/reports/1` | DENY: thiếu `report:read` | Không được gọi | 403 |
| Không đăng nhập → `/api/reports/1` | Không được xác thực | Không được gọi | 401 với HTTP Basic thông thường |

Điểm cần đọc thật kỹ: Bob nhận 403 với báo cáo Alice **dù URL rule đã cho qua**. Do đó, nếu kiểm thử chỉ kiểm tra HTTP matcher và bỏ qua service, kiểm thử chưa chứng minh quyền truy cập dữ liệu. Ngược lại, nếu gọi `ReportService.findReport(...)` qua một bean Spring từ một job, web filter không chạy nhưng `@PreAuthorize` vẫn có thể chạy khi method security đã bật và có security context phù hợp.

Trong ví dụ, báo cáo không tồn tại cũng bị `ReportAccess.canRead` từ chối trước khi thân method chạy. Đây là quyết định policy của bản demo, **không phải quy tắc Spring Security bắt buộc phải trả 403 thay vì 404**. Khi triển khai thật, thiết kế cách xử lý không tồn tại/không có quyền nhất quán để tránh rò rỉ thông tin và phù hợp hợp đồng API.

## 6. Minh họa Java 17 độc lập để kiểm tra thứ tự quyết định

Đoạn sau **không giả lập Spring Security hay SpEL**; nó chỉ diễn tả đúng ý nghĩa phối hợp hai lớp kiểm tra, có thể biên dịch trực tiếp bằng JDK 17. Lưu file `ContextDecisionDemo.java`:

~~~java
public class ContextDecisionDemo {
    record HttpContext(String path, boolean hasReadAuthority) {}
    record MethodContext(long reportId, String user, String owner) {}

    static boolean webAllows(HttpContext request) {
        return request.path().startsWith("/api/reports/")
                && request.hasReadAuthority();
    }

    static boolean methodAllows(MethodContext call) {
        return call.user().equals(call.owner());
    }

    public static void main(String[] args) {
        boolean web = webAllows(
                new HttpContext("/api/reports/1", true));
        boolean method = methodAllows(
                new MethodContext(1L, "bob", "alice"));

        System.out.println("web=" + web);
        System.out.println("method=" + method);
        System.out.println("final=" + (web && method));
    }
}
~~~

~~~bash
javac --release 17 ContextDecisionDemo.java
java ContextDecisionDemo
~~~

stdout chính xác:

~~~text
web=true
method=false
final=false
~~~

Đó là khác biệt giữa **quyền vào tuyến HTTP** và **quyền thực thi nghiệp vụ trên tài nguyên cụ thể**. Spring Boot ví dụ ở phần 5 hiện thực nguyên tắc này bằng filter chain và AOP method security.

## 7. Kiểm thử hai tầng đúng cách

Khi có `spring-security-test` và `spring-boot-starter-test`, một ví dụ integration test (lưu thành `src/test/java/demo/security/AuthorizationFlowTest.java`) là:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFlowTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void sameAuthorityAndOwnerPassesBothLayers() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:read")
    void webPassesButMethodDeniesOtherOwner() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "visitor", authorities = "profile:read")
    void webDeniesMissingAuthority() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithAnonymousUser
    void unauthenticatedRequestRequiresLogin() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là integration test dùng Spring context và MockMvc, không phải unit test của một method gọi trực tiếp bằng `new ReportService(...)`. Với Spring AOP, **lời gọi nội bộ qua `this.securedMethod()` thường không đi qua proxy**, vì vậy annotation có thể không được áp dụng; hãy viết test qua đúng bean và đường gọi sản phẩm thực tế.

Một ma trận QA hữu ích còn phải bao gồm: người dùng có quyền URL nhưng không có quyền trên bản ghi; URL khác chạm cùng service; lệnh gọi từ job/listener không qua HTTP; quyền bị thu hồi; thread async không được truyền security context; response 401/403/404 theo cấu hình; và bảo vệ thao tác ghi trước side effect.

## 8. Những nhầm lẫn phổ biến và cách sửa

### Nhầm 1: “Cùng có `hasRole` nên root ở đâu cũng giống nhau”

Sai. `hasRole` và `hasAuthority` thuộc các phép chung, nhưng web root được gắn `request` còn method root gắn invocation. `hasRole('ADMIN')` theo cấu hình mặc định kiểm tra authority `ROLE_ADMIN`; `hasAuthority('ADMIN')` lại so khớp đúng chuỗi `ADMIN`. Điều này cần hiểu ở cả hai nơi, không phải dấu hiệu root giống nhau.

### Nhầm 2: “Method security tự có `request`”

Sai trong ngữ cảnh mặc định. Đặc biệt nếu service chạy qua queue hoặc scheduled task, không có servlet request. Hãy đưa dữ liệu policy cần thiết vào các tham số service hoặc bean policy được quản lý rõ; tránh phụ thuộc thread-local HTTP request như một điều kiện bắt buộc của nghiệp vụ.

### Nhầm 3: “Đã bảo vệ URL nên service luôn an toàn”

Chưa đủ. Cùng service có thể được gọi từ nhiều endpoint hoặc không qua HTTP. Thêm `@PreAuthorize`/policy tại ranh giới nghiệp vụ cho quyền trên tài nguyên, nhất là multi-tenant/ownership. Ngược lại, method security không thay thế bảo vệ endpoint, CORS/CSRF, xác thực, filter chain và quy tắc URL của ứng dụng Servlet.

### Nhầm 4: “`@PostAuthorize` chạy trước khi service thay đổi dữ liệu”

Sai. `@PostAuthorize` xét kết quả sau lời gọi; nếu thân method gửi email, tạo giao dịch ngoài, cập nhật bản ghi, các side effect đó có thể đã xảy ra. Với cập nhật/xóa, đánh giá quyền trước khi thực thi, đồng thời bảo vệ tính nguyên tử và điều kiện tại data layer.

### Nhầm 5: “Chuyển nguyên chuỗi SpEL web sang `@PreAuthorize`”

Không có phép chuyển chung như vậy. `request.method` và `hasIpAddress(...)` thuộc web; `#p0`, `returnObject`, `filterObject` thuộc method. Viết lại policy dựa trên dữ liệu mà tầng đích thực sự có. Có thể tái sử dụng **bean policy nghiệp vụ** được thiết kế với tham số rõ ràng, không tái sử dụng mù quáng mọi chuỗi SpEL.

### Nhầm 6: “Mọi `authorizeHttpRequests` đều dùng WebSecurityExpressionRoot”

Sai. `.hasRole(...)`, `.hasAuthority(...)`, `.authenticated()` trong DSL thường được thực thi bởi `AuthorizationManager` cụ thể. Chỉ khi chọn API biểu thức (ví dụ `WebExpressionAuthorizationManager`) mới có bối cảnh đánh giá web SpEL. Hướng đi hiện đại là dùng manager có kiểu rõ ràng cho phần lớn web rule.

### Nhầm 7: “HTTP 403 được đảm bảo ở mọi nơi khi method từ chối”

Ở service, thất bại quyền phát sinh exception/kết quả từ chối tùy API. HTTP 401/403/404 phụ thuộc cơ chế xác thực, filter chain, exception translation và handler của ứng dụng. Lệnh gọi background không có mã HTTP. Kiểm thử status ở HTTP layer và kiểm thử exception ở service layer một cách tách biệt.

### Nhầm 8: “WebSecurityExpressionRoot cũng áp dụng cho WebFlux”

Bài này đang nói về **Servlet** với `HttpServletRequest`. Spring Security WebFlux có pipeline và request context dạng reactive (`ServerWebExchange`), cùng API bảo vệ riêng. Không lấy `WebSecurityExpressionRoot` của Servlet để suy ra trực tiếp reactive authorization hoặc đồng nhất `@EnableMethodSecurity` với `@EnableReactiveMethodSecurity`.

## 9. Checklist thiết kế chính sách

1. **Đang bảo vệ request hay method?** Nếu là URL, dùng `SecurityFilterChain`/`AuthorizationManager`. Nếu là quyền thao tác trên dữ liệu, dùng method security và/hoặc policy trong service/repository.
2. **Biểu thức lấy dữ liệu từ đâu?** `request`/IP ở web; `#p0` và thuộc tính đối tượng kết quả ở method. Các phép authentication chung không xóa khác biệt về ngữ cảnh.
3. **Phương thức có thể được gọi từ nơi khác không?** Bảo vệ ở ranh giới service khi nghiệp vụ phải luôn có quyền, kể cả không qua HTTP.
4. **Chính sách phụ thuộc vào owner/tenant/ACL?** Đặt kiểm tra ở nơi có dữ liệu đáng tin; với truy vấn lớn, kết hợp predicate quyền tại data layer, tránh chỉ dựa vào UI hay URL.
5. **Thao tác có side effect không?** Kiểm tra trước khi ghi; không kỳ vọng hậu kiểm tự rollback.
6. **Đã test luồng kết hợp chưa?** Phải có case web cho qua nhưng method từ chối, và case web từ chối trước method. Xác minh đúng proxy, authentication và trạng thái HTTP.

**Tự kiểm tra kiến thức:**

- `hasAuthority('report:read')` chạy được cả trong web và method: vì sao? → Vì cả hai có thông tin `Authentication` và phép security chung.
- `hasIpAddress('192.0.2.0/24')` trong `@PreAuthorize` có chắc hoạt động không? → Không; đây là phép gắn với web root, method root mặc định không có phép đó.
- Tại sao Bob vào được `/api/reports/1` ở web nhưng vẫn bị 403? → Web chỉ xét authority tuyến HTTP, method còn xét owner của ID 1.
- Nếu job gọi bean service và không đi qua filter chain, quyền nào vẫn có thể được áp dụng? → Method authorization trên lời gọi đi qua Spring proxy, với security context hợp lệ.

## Tài liệu chính thức

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `AuthorizationManager`, di chuyển từ biểu thức SpEL.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, các annotation method, biểu thức và phương thức chặn.
- [WebSecurityExpressionRoot API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/expression/WebSecurityExpressionRoot.html): `request` và `hasIpAddress`.
- [DefaultHttpSecurityExpressionHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/expression/DefaultHttpSecurityExpressionHandler.html): tạo web evaluation context từ `RequestAuthorizationContext`.
- [DefaultMethodSecurityExpressionHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html): tạo method evaluation context từ `MethodInvocation`.
