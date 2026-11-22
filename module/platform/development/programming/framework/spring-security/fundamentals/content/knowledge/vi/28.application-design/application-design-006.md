# Không coi việc ẩn nút trên giao diện là biện pháp phân quyền

> **Chủ đề:** Spring Security — fundamentals / Thiết kế ứng dụng. Bài học giải thích vì sao ẩn nút, vô hiệu hóa form hoặc chặn điều hướng trong frontend **chỉ là trải nghiệm người dùng (UX)**, không phải ranh giới bảo mật. Quyền phải được kiểm tra **trên server, đối với đúng thao tác và tài nguyên**, cho dù request được phát từ trình duyệt, script, ứng dụng di động hay HTTP client. Ví dụ dùng **Java 17+**, **Spring Boot 3.5.0**, Spring Security 6.x (Servlet), Maven và MockMvc.

## 1. Bản chất vấn đề: client điều khiển giao diện, không điều khiển quyền

Giả sử ứng dụng quản lý báo cáo có nút “Phê duyệt” (`Approve`). UI ẩn nút khi tài khoản không có `ROLE_MANAGER`:

~~~javascript
// Đoạn minh họa frontend; bản thân nó KHÔNG cấp hoặc thu hồi quyền.
const me = await fetch("/api/me", {
  credentials: "same-origin"
}).then(response => response.json());

document.querySelector("#approveButton").hidden =
    !me.authorities.includes("ROLE_MANAGER");
~~~

Người dùng thông thường có thể không nhìn thấy nút. Nhưng họ vẫn có thể:

- Mở DevTools rồi bỏ thuộc tính `hidden` hoặc `disabled` của phần tử.
- Tự gọi `fetch` trong console; viết script Python/JavaScript; dùng Postman, curl hoặc trình duyệt khác.
- Đổi URL, HTTP method, ID tài nguyên hoặc JSON body mà giao diện không cho nhập.
- Dùng phiên bản frontend cũ, ứng dụng mobile hoặc gọi API trực tiếp.
- Sửa dữ liệu trả về từ API `/api/me` trong client để hiện nút (dù việc này **không** làm thay đổi quyền server).

Một request tự gửi:

~~~http
POST /api/reports/51/approve HTTP/1.1
Host: example.test
Cookie: session=REDACTED
Content-Type: application/json
X-Role: MANAGER

{}
~~~

**Không có nút nào trong HTTP request để server dựa vào.** Nếu API chỉ xác minh người gọi đã đăng nhập, rồi phê duyệt báo cáo, việc ẩn nút ở frontend không ngăn thao tác trái phép.

`X-Role: MANAGER` ở ví dụ là **dữ liệu tự khai của client**, không được dùng để cấp quyền. Với ứng dụng dùng cookie session, request thay đổi trạng thái còn cần bảo vệ CSRF theo thiết kế; CSRF **không thay thế** kiểm tra role/owner. Header `Cookie` ở đây chỉ là placeholder đã ẩn giá trị, không phải bằng chứng session thật.

**Nguyên tắc:** frontend có thể **phản ánh** quyền; chỉ backend và policy/data layer mới được **thực thi** quyền.

## 2. Phân biệt UI visibility, authentication và authorization

| Câu hỏi | Thành phần giải quyết | Nó **không** bảo đảm điều gì? |
|---|---|---|
| Có nên hiển thị nút “Phê duyệt”? | Frontend dựa trên thông tin capability/permission từ server | Không chặn được request tự gửi |
| Người gọi là ai? | Authentication, session/Basic/Bearer token đã được xác minh | Chưa nói họ được thao tác trên đối tượng nào |
| Người gọi có role/scope để dùng chức năng không? | HTTP/method authorization của Spring Security | Chưa tự đảm bảo quyền trên tenant/owner của bản ghi |
| Có quyền với **tài nguyên ID 51** không? | Service/policy/ACL/repository với principal + resource + action | Không thể chỉ suy ra từ việc biết ID hoặc nhìn thấy nút |
| Dữ liệu được thay đổi an toàn không? | Transaction, query hạn chế theo tenant/owner, kiểm side effect | Không được bỏ qua chỉ vì frontend đã disable button |

**Authentication** tạo ra `Authentication` đáng tin trong `SecurityContext`. **Authorization** trả lời câu hỏi “principal này có được làm action A trên resource R lúc này không?”. Khi client gửi `role`, `ownerId`, `tenantId` hoặc `isAdmin` trong body/header, chúng là **input không tin cậy**, không được tự động trở thành thuộc tính phân quyền.

Ví dụ kiểm tra thô:

~~~java
// Sai: "đã đăng nhập" không đồng nghĩa được phê duyệt.
.requestMatchers("/api/reports/**").authenticated()
~~~

Nếu bất kỳ user đã đăng nhập nào có thể gọi `POST /api/reports/51/approve`, ẩn nút ở UI không thay đổi hành vi server.

Một rule tốt hơn ở **tầng HTTP** là:

~~~java
.requestMatchers(HttpMethod.POST, "/api/reports/{id}/approve")
    .hasRole("MANAGER")
~~~

Đây vẫn chỉ là bước đầu. Với SaaS nhiều tenant, `ROLE_MANAGER` ở tenant **west** không tự được phê duyệt báo cáo của tenant **east**. Service phải xác minh ranh giới dữ liệu.

## 3. Thiết kế chính sách từ nghiệp vụ, không từ trạng thái của nút

Xét hệ thống mẫu có:

| Tài nguyên | ID | Tenant | Chủ sở hữu | Trạng thái ban đầu |
|---|---|---|---|---|
| Order | 101 | east | alice | OPEN |
| Order | 202 | east | bob | OPEN |
| Order | 303 | west | mallory | OPEN |
| Report | 51 | east | — | PENDING |
| Report | 61 | west | — | PENDING |

Chủ thể:

| Principal | Role do server cấp | Tenant được server xác minh |
|---|---|---|
| alice | USER | east |
| bob | USER | east |
| manager | MANAGER | east |
| mallory | MANAGER | west |
| anonymous | không có | không có |

**Chính sách của ví dụ:**

1. **READ order:** chỉ **chủ sở hữu thuộc cùng tenant** được xem.
2. **CANCEL order:** chỉ **chủ sở hữu thuộc cùng tenant** được hủy.
3. **READ report:** chỉ **MANAGER của đúng tenant** được xem.
4. **APPROVE report:** chỉ **MANAGER của đúng tenant** được phê duyệt.
5. **Không tồn tại hoặc sai tenant/owner:** trả `404` theo lựa chọn che giấu sự tồn tại của tài nguyên trong demo.
6. **Đăng nhập nhưng thiếu role chức năng:** `403`; **anonymous** gọi API được bảo vệ: `401` khi dùng HTTP Basic trong demo.

### Ma trận kiểm chứng quyền

| Principal | GET order 101 | POST cancel order 101 | GET report 51 | POST approve report 51 |
|---|---|---|---|---|
| anonymous | 401 | 401* | 401 | 401* |
| alice (owner) | 200 | 200* | 403 | 403* |
| bob (không phải owner) | 404 | 404* | 403 | 403* |
| manager (east) | 404 | 404* | 200 | 200* |
| mallory (MANAGER, west) | 404 | 404* | 404 | 404* |

Dấu `*`: khi kiểm tra authorization của `POST` trong môi trường có CSRF protection, phải **gửi CSRF token hợp lệ**. Nếu token vắng mặt, `CsrfFilter` có thể trả `403` trước khi rule phân quyền được đánh giá. Bộ test MockMvc ở phần sau cố ý dùng `with(csrf())` để tránh kết luận sai.

Đáng chú ý:

- Alice được thấy nút “Hủy đơn 101” vì sở hữu đơn, nhưng Bob không được phép hủy dù tự bật nút.
- Manager west có thể **thấy nút Phê duyệt** do role MANAGER, nhưng **không thể phê duyệt report 51 của tenant east**. Trạng thái hiển thị nút chỉ phản ánh quyền chung, không nhất thiết biết đầy đủ chính sách tài nguyên.
- Server phải xác định role, tenant, owner và action trước khi sửa bản ghi. Không tin JavaScript đã quyết định đúng.

## 4. Tường ranh giới tin cậy của ứng dụng

~~~mermaid
flowchart LR
    U["Frontend: ẩn/hiện nút<br/>UX, không đáng tin"] -->|"HTTP request"| S["Spring Security FilterChain<br/>Authentication + route authz"]
    X["curl / Postman / script<br/>không cần UI"] -->|"HTTP request"| S
    S -->|"được vào service"| P["Policy/service: tenant,<br/>owner, resource, action"]
    P -->|"allow"| D["Query/mutation tài nguyên"]
    P -->|"deny"| E["401 / 403 / 404<br/>không có side effect"]
    D --> F["HTTP response"]
~~~

Trong ứng dụng Spring Security:

- `SecurityFilterChain` kiểm tra danh tính, route, method và các yêu cầu bảo mật như CSRF. Ví dụ `POST /api/reports/{id}/approve` cần `ROLE_MANAGER`.
- `Authentication` được cung cấp bởi cơ chế xác thực đáng tin (ví dụ `UserDetailsService`, OAuth2 Resource Server, session login), không phải JSON frontend tự gửi.
- **Service/policy** ràng buộc danh tính với đối tượng và hành động. Ví dụ `manager` ở tenant east không thể phê duyệt tài liệu thuộc west.
- Repository/database có thể áp dụng predicate theo `owner_id`, `tenant_id`, ACL hoặc Row-Level Security để giảm rủi ro bypass khi có nhiều đường truy cập.
- Frontend có thể dùng thông tin permission từ server để cải thiện UI. Dữ liệu đó **không thay thế** kiểm tra tại thời điểm request được thực thi.

Trong hệ thống có quyền thay đổi theo thời gian, “nút xuất hiện lúc 10:00” không chứng minh quyền vẫn tồn tại lúc 10:05. Server phải kiểm tra ở **thời điểm thao tác**, tránh *time-of-check to time-of-use* (TOCTOU) khi owner/tenant/membership thay đổi.

## 5. Ví dụ hoàn chỉnh với Spring Boot và Spring Security

Bài demo tạo API đơn giản, dùng HTTP Basic cho dễ tái hiện vai trò. `ActionsService` chứa chính sách owner và tenant, kho dữ liệu in-memory cho test. Đây là một ứng dụng học tập **có thể chạy bằng Maven**; mã trong phần 6 là frontend minh họa, không phải thành phần bắt buộc để chạy backend.

**Môi trường:** Java 17+, Maven 3.9+, Spring Boot **3.5.0** (Spring Security 6.x). Đặt dự án:

~~~text
ui-is-not-authorization-demo/
├── pom.xml
├── src/main/java/com/example/uiauth/
│   ├── UiAuthApplication.java
│   ├── SecurityConfig.java
│   ├── ActionsService.java
│   └── ActionsController.java
└── src/test/java/com/example/uiauth/
    └── UiAuthorizationTest.java
~~~

Các credentials `alice:pw`, `bob:pw`, `manager:pw`, `mallory:pw` chỉ dùng tại localhost. Mẫu chủ yếu kiểm tra **quyền server-side**, không phải kiến trúc lưu dữ liệu cho production.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ui-is-not-authorization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
~~~

### 5.2. UiAuthApplication.java

~~~java
package com.example.uiauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UiAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(UiAuthApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.uiauth;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/{id}/cancel")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports/{id}")
                    .hasRole("MANAGER")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports/{id}/approve")
                    .hasRole("MANAGER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Cố ý giữ CSRF protection mặc định: Basic có thể được
        // trình duyệt đính kèm tự động cho request thay đổi trạng thái.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            user("alice", "USER"),
            user("bob", "USER"),
            user("manager", "MANAGER"),
            user("mallory", "MANAGER")
        );
    }

    private static org.springframework.security.core.userdetails.UserDetails
            user(String username, String role) {
        return User.withUsername(username)
            .password("{noop}pw")
            .roles(role)
            .build();
    }
}
~~~

**Giải thích:**

1. `authenticated()` yêu cầu danh tính đã được xác minh; `hasRole("MANAGER")` kiểm quyền chức năng trong HTTP filter chain.
2. Những rule chỉ mở GET/POST cụ thể; các method khác hoặc endpoint không được khai báo rơi vào `anyRequest().denyAll()`.
3. `SessionCreationPolicy.STATELESS` nghĩa là không dựa vào session để nhớ HTTP Basic; client gửi credentials trên mỗi request. Điều này **không loại bỏ** nguy cơ CSRF nếu browser tự động đính kèm Basic credentials.
4. `DispatcherType.ERROR`/`FORWARD` được phép cho internal dispatch trong bài demo. Không mở rộng thành `permitAll("/**")`.
5. `{noop}` chỉ dành cho password mẫu. Production phải có password hashing phù hợp, TLS và quản lý secrets.
6. Role và tenant phải có nguồn server đáng tin. Trong ví dụ, role đến từ `InMemoryUserDetailsManager`; tenant được map ở service. Header `X-Role`/tham số `tenant` từ client **không ảnh hưởng** quyết định này.
7. HTTP route permission **không thay cho object-level permission**. Bởi vậy service phải tiếp tục kiểm tenant và owner sau khi request vượt qua filter.

### 5.4. ActionsService.java

~~~java
package com.example.uiauth;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ActionsService {

    private static final Map<String, String> TENANTS = Map.of(
        "alice", "east",
        "bob", "east",
        "manager", "east",
        "mallory", "west"
    );

    private final Map<Long, Order> orders = new ConcurrentHashMap<>();
    private final Map<Long, Report> reports = new ConcurrentHashMap<>();

    public ActionsService() {
        resetFixture();
    }

    // Dùng để cô lập test, không có endpoint HTTP nào gọi hàm này.
    public void resetFixture() {
        orders.clear();
        reports.clear();
        orders.put(101L,
            new Order(101L, "east", "alice", "OPEN"));
        orders.put(202L,
            new Order(202L, "east", "bob", "OPEN"));
        orders.put(303L,
            new Order(303L, "west", "mallory", "OPEN"));
        reports.put(51L,
            new Report(51L, "east", "PENDING"));
        reports.put(61L,
            new Report(61L, "west", "PENDING"));
    }

    public UserView whoAmI(Authentication auth) {
        String tenant = trustedTenant(auth);
        List<String> authorities = auth.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .sorted(Comparator.naturalOrder())
            .toList();
        return new UserView(auth.getName(), tenant, authorities);
    }

    public OrderView readOrder(long id, Authentication auth) {
        return view(ownedOrder(id, auth));
    }

    public OrderView cancelOrder(long id, Authentication auth) {
        Order order = ownedOrder(id, auth);
        Order changed = new Order(
            order.id(), order.tenant(), order.owner(), "CANCELLED");
        orders.put(id, changed);
        return view(changed);
    }

    public ReportView readReport(long id, Authentication auth) {
        return view(manageableReport(id, auth));
    }

    public ReportView approveReport(long id, Authentication auth) {
        Report report = manageableReport(id, auth);
        Report changed = new Report(
            report.id(), report.tenant(), "APPROVED");
        reports.put(id, changed);
        return view(changed);
    }

    private Order ownedOrder(long id, Authentication auth) {
        String tenant = trustedTenant(auth);
        Order order = orders.get(id);

        if (order == null
                || !order.tenant().equals(tenant)
                || !order.owner().equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return order;
    }

    private Report manageableReport(long id, Authentication auth) {
        String tenant = trustedTenant(auth);
        Report report = reports.get(id);

        // Che giấu resource thuộc tenant khác.
        if (report == null || !report.tenant().equals(tenant)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        // Defense in depth: check cả trong service,
        // tránh bypass khi được gọi từ đường vào không qua HTTP.
        if (!hasRole(auth, "MANAGER")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return report;
    }

    private static String trustedTenant(Authentication auth) {
        if (auth == null
                || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        String tenant = TENANTS.get(auth.getName());
        if (tenant == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return tenant;
    }

    private static boolean hasRole(Authentication auth, String role) {
        return auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_" + role));
    }

    private static OrderView view(Order order) {
        return new OrderView(order.id(), order.status());
    }

    private static ReportView view(Report report) {
        return new ReportView(report.id(), report.status());
    }

    private record Order(
        long id, String tenant, String owner, String status) {}

    private record Report(long id, String tenant, String status) {}

    public record OrderView(long id, String status) {}

    public record ReportView(long id, String status) {}

    public record UserView(
        String username, String tenant, List<String> authorities) {}
}
~~~

**Điểm quan trọng nhất:** `cancelOrder` không dựa vào `cancelButton.hidden`; nó gọi `ownedOrder` lấy **principal đã xác thực** rồi so với owner và tenant của bản ghi. `approveReport` không tin client tự gắn `X-Role: MANAGER`; nó bắt đầu từ authentication do Spring Security cung cấp, rồi kiểm report thuộc đúng tenant. Cả hai chỉ sửa trạng thái sau khi policy cho phép.

Các map in-memory đơn giản giúp thấy rõ nhánh phân quyền trong bài học. Đây **không phải** ví dụ về transaction/atomic update của database thật. Production cần dữ liệu owner/tenant đáng tin, truy vấn có predicate, giao dịch, kiểm tra quyền đúng thời điểm, concurrency/TOCTOU và kiểm tra trạng thái nghiệp vụ của order/report trước khi chuyển trạng thái.

### 5.5. ActionsController.java

~~~java
package com.example.uiauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ActionsController {

    private final ActionsService actions;

    public ActionsController(ActionsService actions) {
        this.actions = actions;
    }

    @GetMapping("/api/me")
    public ActionsService.UserView me(Authentication auth) {
        return actions.whoAmI(auth);
    }

    @GetMapping("/api/orders/{id}")
    public ActionsService.OrderView order(
            @PathVariable long id, Authentication auth) {
        return actions.readOrder(id, auth);
    }

    @PostMapping("/api/orders/{id}/cancel")
    public ActionsService.OrderView cancel(
            @PathVariable long id, Authentication auth) {
        return actions.cancelOrder(id, auth);
    }

    @GetMapping("/api/reports/{id}")
    public ActionsService.ReportView report(
            @PathVariable long id, Authentication auth) {
        return actions.readReport(id, auth);
    }

    @PostMapping("/api/reports/{id}/approve")
    public ActionsService.ReportView approve(
            @PathVariable long id, Authentication auth) {
        return actions.approveReport(id, auth);
    }
}
~~~

Controller chỉ chuyển `id` và `Authentication` do Spring Security thiết lập sang service. Không nhận `owner`, `tenant`, `role` từ query hoặc body để cấp quyền.

Không nên đặt policy quan trọng **chỉ** ở một callback click trong UI hoặc **chỉ** trong controller: code khác có thể gọi service qua batch job, message handler hoặc một endpoint mới. Ở demo, service tự bảo vệ quyền owner/tenant. Với Spring Method Security (`@EnableMethodSecurity`, `@PreAuthorize`), có thể thêm một lớp phòng thủ nữa, nhưng phải kiểm tra invocation qua proxy và policy đúng resource.

## 6. Frontend nên phản ánh quyền, không tạo ra quyền

Với React/Vue/Angular hoặc JavaScript thuần, có thể ẩn/disable một thao tác nếu user khó có khả năng được phép:

~~~javascript
// Đoạn giao diện minh họa; cần một trang có phần tử #approveButton.
async function refreshUiPermissions() {
  const response = await fetch("/api/me", {
    credentials: "same-origin"
  });

  if (!response.ok) {
    document.querySelector("#approveButton").hidden = true;
    return;
  }

  const me = await response.json();
  document.querySelector("#approveButton").hidden =
      !me.authorities.includes("ROLE_MANAGER");
}
~~~

**Đây là cải thiện UX, không phải security enforcement:**

- Nếu user không có role, giấu nút để tránh gợi ý hành động không thể làm.
- Nếu user có role MANAGER nhưng report thuộc tenant khác, nút vẫn có thể xuất hiện. Server phải trả 404/403 theo chính sách.
- Nếu quyền bị thu hồi sau khi UI render, backend phải từ chối request tiếp theo ngay cả khi nút còn hiển thị.
- Nếu user sửa DOM hoặc tự phát HTTP request, backend vẫn giữ nguyên chính sách.
- Nếu UI chờ thông tin permission, tránh hiển thị thoáng qua nút nhạy cảm gây nhầm lẫn; có thể mặc định hidden rồi mở khi dữ liệu đáng tin được tải, nhưng **an toàn thực sự vẫn do backend**.

Một API trả các **capabilities cho một resource cụ thể** có thể khiến UI chính xác hơn, ví dụ:

~~~json
{
  "reportId": 51,
  "capabilities": {
    "canRead": true,
    "canApprove": false
  }
}
~~~

Đây là định dạng response minh họa, không có trong backend mẫu ở mục 5. Capabilities giúp UI tránh hiện nút sai, nhưng backend phải **tính lại quyền khi nhận thao tác**, không tin client gửi lại `canApprove:true` như bằng chứng phân quyền.

Một mẫu frontend có lỗi:

~~~javascript
// SAI: kiểm tra duy nhất phía client.
if (currentUser.role === "MANAGER") {
  await fetch("/api/reports/51/approve", {method: "POST"});
}
// API backend vẫn có thể bị client khác gọi trực tiếp.
~~~

Nếu app dùng cookie session/HTTP Basic, POST thực còn phải gửi CSRF token đúng thiết kế. Bài demo giữ CSRF và test qua MockMvc; `fetch` trên chỉ minh họa logic không an toàn, **không phải request chạy được để phê duyệt**.

## 7. Kiểm thử tự động: bỏ qua nút nhưng vẫn không thể thao tác

Đặt file `src/test/java/com/example/uiauth/UiAuthorizationTest.java`. Phép thử đi trực tiếp qua MockMvc, **không nhấn nút giao diện**. Đây chính là điều bài học cần chứng minh: API phải an toàn ngay cả khi người gọi bỏ qua toàn bộ frontend.

~~~java
package com.example.uiauth;

import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UiAuthorizationTest {

    @Autowired MockMvc mvc;
    @Autowired ActionsService actions;

    @BeforeEach
    void reset() {
        actions.resetFixture();
    }

    static Stream<Arguments> authorizationCases() {
        return Stream.of(
            Arguments.of("anonymous me", null,
                "GET", "/api/me", 401),
            Arguments.of("alice me", "alice",
                "GET", "/api/me", 200),

            Arguments.of("alice reads own order", "alice",
                "GET", "/api/orders/101", 200),
            Arguments.of("bob cannot read Alice order", "bob",
                "GET", "/api/orders/101", 404),
            Arguments.of("manager cannot read Alice order", "manager",
                "GET", "/api/orders/101", 404),
            Arguments.of("west manager cannot read east order", "mallory",
                "GET", "/api/orders/101", 404),
            Arguments.of("unknown order", "alice",
                "GET", "/api/orders/999", 404),

            Arguments.of("Alice cancels own order", "alice",
                "POST", "/api/orders/101/cancel", 200),
            Arguments.of("Bob cannot cancel Alice order", "bob",
                "POST", "/api/orders/101/cancel", 404),
            Arguments.of("anonymous cannot cancel", null,
                "POST", "/api/orders/101/cancel", 401),
            Arguments.of("manager not owner cannot cancel", "manager",
                "POST", "/api/orders/101/cancel", 404),

            Arguments.of("east manager reads east report", "manager",
                "GET", "/api/reports/51", 200),
            Arguments.of("alice cannot read manager report", "alice",
                "GET", "/api/reports/51", 403),
            Arguments.of("west manager cannot read east report", "mallory",
                "GET", "/api/reports/51", 404),

            Arguments.of("east manager approves east report", "manager",
                "POST", "/api/reports/51/approve", 200),
            Arguments.of("alice cannot approve report", "alice",
                "POST", "/api/reports/51/approve", 403),
            Arguments.of("west manager cannot approve east report", "mallory",
                "POST", "/api/reports/51/approve", 404),
            Arguments.of("west manager approves west report", "mallory",
                "POST", "/api/reports/61/approve", 200),
            Arguments.of("anonymous cannot approve report", null,
                "POST", "/api/reports/51/approve", 401),
            Arguments.of("GET cannot approve report", "manager",
                "GET", "/api/reports/51/approve", 403)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("authorizationCases")
    void requestIsCheckedOnServer(
            String description, String username,
            String method, String path, int expectedStatus)
            throws Exception {
        MockHttpServletRequestBuilder request = switch (method) {
            case "GET" -> get(path);
            case "POST" -> post(path).with(csrf());
            default -> throw new IllegalArgumentException(method);
        };

        if (username != null) {
            request.with(httpBasic(username, "pw"));
        }
        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void forgedRoleHeaderCannotApproveReport() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("alice", "pw"))
                .with(csrf())
                .header("X-Role", "MANAGER")
                .param("role", "MANAGER")
                .param("tenant", "east"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void otherTenantManagerCannotApproveReport() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("mallory", "pw"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void unownedOrderCannotBeCancelled() throws Exception {
        mvc.perform(post("/api/orders/101/cancel")
                .with(httpBasic("bob", "pw"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(jsonPath("$.status").value("OPEN"));
    }

    @Test
    void allowedOperationsReallyChangeState() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("manager", "pw"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("APPROVED"));

        mvc.perform(post("/api/orders/101/cancel")
                .with(httpBasic("alice", "pw"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("CANCELLED"));
    }

    @Test
    void csrfStillProtectsUnsafeMethods() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("manager", "pw")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
~~~

**Những gì test chứng minh:**

1. **20 case HTTP** theo người gọi + resource + action. Không có test nào dựa vào `hidden`, `disabled` hay component React.
2. Alice gửi `X-Role: MANAGER`, `role=MANAGER` và `tenant=east` vẫn nhận 403 ở route approve. Các giá trị tự khai của client không nâng quyền.
3. Mallory có `ROLE_MANAGER` thực, nhưng thuộc tenant west nên bị từ chối với report east (404). **Role hợp lệ không đủ để vượt boundary dữ liệu**.
4. Bob không được hủy order của Alice dù cả hai đều thuộc tenant east và có `ROLE_USER`. Đây là object-level authorization chống IDOR/BOLA.
5. Sau request bị từ chối, test đọc lại trạng thái report/order và xác nhận **chưa có side effect**. Chỉ nhìn status 403/404 có thể bỏ sót việc service đã thay đổi dữ liệu trước khi trả lỗi.
6. Các request POST dùng `with(csrf())` để cô lập kết quả authorization. Một test riêng bỏ CSRF để chứng minh nó vẫn được bảo vệ.
7. Test chỉ một tài khoản hoặc chỉ case thành công thường không phát hiện được quyền bị thiếu. Quan trọng là có **cặp đối chiếu allowed/denied** cho cùng action/resource.

Trong demo, `resetFixture()` thiết lập lại các map trước từng test. Test dự kiến chạy tuần tự; khi bật parallel tests, fixture singleton có thể gây nhiễu. Trong hệ thống thật nên dùng transaction rollback hoặc dữ liệu test độc lập để bảo đảm tính lặp lại.

## 8. Chạy chương trình và đối chiếu kết quả

Trong thư mục `ui-is-not-authorization-demo`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Với dependencies sẵn có và mã đúng phiên bản, `mvn test` **được kỳ vọng** chạy thành công; đây là hướng dẫn thực thi, **không khẳng định lệnh đã chạy trong bài viết**. Sau khi khởi chạy, server mặc định ở `http://localhost:8080` nếu port còn trống.

Gọi các endpoint GET để thấy chính sách:

~~~bash
curl -i -u alice:pw http://localhost:8080/api/me
curl -i -u alice:pw http://localhost:8080/api/orders/101
curl -i -u bob:pw http://localhost:8080/api/orders/101
curl -i -u manager:pw http://localhost:8080/api/reports/51
curl -i -u alice:pw http://localhost:8080/api/reports/51
curl -i -u mallory:pw http://localhost:8080/api/reports/51
~~~

Kỳ vọng status theo thứ tự: `200`, `200`, `404`, `200`, `403`, `404`.

Ví dụ `GET /api/me` với tài khoản manager trả dữ liệu về mặt nội dung:

~~~json
{
  "username": "manager",
  "tenant": "east",
  "authorities": ["ROLE_MANAGER"]
}
~~~

Ví dụ report thành công:

~~~json
{"id":51,"status":"PENDING"}
~~~

**POST qua curl phải kèm CSRF token nếu dùng browser/Basic flow này.** Vì demo giữ CSRF protection, một lệnh `curl -X POST -u manager:pw ...` không có CSRF token có thể trả 403 **ngay cả cho manager có quyền**. Không dùng nó để chứng minh policy backend đã từ chối hay cho phép. Dùng `MockMvc` với `with(csrf())` ở mục 7 để kiểm authorization một cách tách biệt. Khi xây frontend thật, thiết kế endpoint/CSRF cookie/form token đúng theo client của ứng dụng, không tắt CSRF chỉ để demo POST chạy dễ.

Trên PowerShell, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`. Những phản hồi JSON/error headers cụ thể phụ thuộc cấu hình framework; test chính kiểm status và dữ liệu cần bảo vệ.

## 9. Những cách kiểm soát đúng ở backend

### 9.1. Ở route: quy định quyền theo HTTP method

~~~java
// Mảnh minh họa nằm trong authorizeHttpRequests(...).
.requestMatchers(HttpMethod.POST, "/api/reports/{id}/approve")
    .hasRole("MANAGER")
.anyRequest().denyAll()
~~~

Tách GET đọc báo cáo khỏi POST phê duyệt; tránh rule wildcard rộng như `.requestMatchers("/api/reports/**").authenticated()` khi một số thao tác yêu cầu role mạnh hơn. Một endpoint mới cần được phê duyệt và thêm rule cụ thể trước `denyAll`, không dựa vào frontend chưa có nút.

### 9.2. Ở service: kiểm principal, tenant và quan hệ với object

~~~java
// Pseudocode minh họa — không phải method độc lập chạy được.
if (!report.tenantId().equals(authenticatedTenantId)) {
    denyNotFound();
}
if (!hasPermission(authenticatedUser, "APPROVE", report)) {
    denyForbidden();
}
approve(report);
~~~

Không lấy `authenticatedTenantId` từ một header client chưa được kiểm chứng; nó phải đến từ session/JWT claims **đã xác thực và được kiểm tra**, hoặc mapping server-side. Khi sản phẩm có quyền chia sẻ/ACL, policy còn phải xét owner, membership, action và trạng thái bản ghi.

### 9.3. Ở database: ràng buộc quyền trong query/mutation

Với tài nguyên riêng tư:

~~~sql
SELECT id, status
FROM orders
WHERE id = :requestedId
  AND owner_user_id = :authenticatedUserId
  AND tenant_id = :authenticatedTenantId;
~~~

Cập nhật đồng thời kiểm tra quyền:

~~~sql
UPDATE reports
SET status = 'APPROVED'
WHERE id = :requestedReportId
  AND tenant_id = :authenticatedTenantId
  AND status = 'PENDING';
~~~

Câu UPDATE này **chưa tự kiểm role MANAGER** — role phải được xác thực tại service/policy hoặc được đưa vào một cơ chế kiểm quyền đáng tin trước khi mutation. Nó cũng nên kiểm số dòng ảnh hưởng, xử lý transaction/idempotency/audit và các điều kiện trạng thái nghiệp vụ. Tránh mô hình đọc `id` → kiểm quyền ở một thời điểm → cập nhật theo `id` mà không phòng trường hợp quyền thay đổi đồng thời.

### 9.4. Method Security là một lớp phòng thủ bổ sung

~~~java
// Cần @EnableMethodSecurity và bean "reportPolicy" được cung cấp.
// Đây chỉ là ý tưởng, KHÔNG thuộc sample Java có thể chạy ở mục 5.
@PreAuthorize("@reportPolicy.canApprove(authentication, #reportId)")
public void approve(Long reportId) {
    // Gọi service/repository với query/mutation ràng buộc policy.
}
~~~

`@PreAuthorize("hasRole('MANAGER')")` chỉ bảo vệ quyền chức năng, không tự xác minh report thuộc tenant. Method security thường chạy qua Spring AOP proxy, nên gọi trực tiếp `this.approve(...)` trong cùng bean có thể không đi qua interceptor. Policy cốt lõi nên vẫn có ranh giới ở service/data layer phù hợp.

## 10. Các kiểu giả mạo client thường gặp và vì sao thất bại khi backend đúng

### Bỏ hidden/disabled

Người dùng đổi `button.hidden = false` hoặc bỏ `disabled`. Điều này chỉ sửa DOM của browser; không nâng role server. Khi bấm, HTTP request phải được kiểm độc lập. Giao diện có thể phản hồi lỗi 403 bằng thông báo UX phù hợp, nhưng không chuyển lỗi đó thành thành công giả.

### Sửa URL hoặc ID

Đổi `/api/orders/101/cancel` thành `/api/orders/202/cancel`. Server phải so owner của **đúng order ID** với principal đã xác thực, không tin client đã dùng nút cho đơn của chính mình.

### Gửi role, user, tenant trong request

~~~http
POST /api/reports/51/approve?role=MANAGER&tenant=east HTTP/1.1
X-Role: MANAGER
X-User: manager
~~~

Các header/query này không được dùng để xác thực identity. Trong demo, người gửi vẫn là account mà Basic credentials thực xác minh. Với reverse proxy/gateway truyền danh tính qua header, chỉ tin header sau khi có **trust boundary và authentication giữa các service** đúng chuẩn; không cho client Internet tự đặt header đó.

### Sửa dữ liệu permission API

Client có thể thay `{"canApprove":false}` thành `{"canApprove":true}` trong bộ nhớ hoặc hiển thị UI; server không được dùng giá trị client gửi lại để cấp quyền. Khả năng hiện nút không phải security token.

### Gọi API qua client khác

API nhận HTTP độc lập với JavaScript của trang. Không thể trông đợi rằng mọi request đã đi qua `onClick`, kiểm tra route guard frontend hoặc confirmation modal. Backend phải xử lý **request bị cố ý gửi sai** theo chính sách.

### UI cũ hoặc cache lỗi thời

Nếu user từng là manager và UI vẫn thấy nút sau khi bị thu hồi quyền, backend vẫn phải từ chối tại thời điểm request. Vì vậy dữ liệu role/capability frontend chỉ có giá trị thông báo cho UI; quyết định quyền phải dựa trên nguồn hiện tại/đáng tin và chính sách cache/invalidation phù hợp.

## 11. Phân biệt 401, 403, 404 và CSRF

| Trạng thái | Ý nghĩa trong ví dụ | Có chứng minh đã kiểm object permission không? |
|---|---|---|
| `401` | Anonymous/credentials chưa hợp lệ trong HTTP Basic protected route | Không; request có thể dừng ở authentication |
| `403` | Principal đã xác thực nhưng thiếu role; hoặc POST thiếu CSRF token | Không nhất thiết; phải biết filter nào trả lỗi |
| `404` | ID không tồn tại hoặc bị che khỏi principal/tenant | Có thể là kết quả query/policy, nhưng cần test no-leak/no-side-effect |
| `200` | Thao tác được cho phép và xử lý | Phải kiểm dữ liệu đúng, không chỉ status thành công |

Với **CSRF**: kiểm tra dữ liệu `X-CSRF-TOKEN` hoặc form parameter tương ứng tùy app và đảm bảo `POST/PATCH/DELETE` không bị chặn bởi CSRF khi bạn đang muốn test authorization. Tuy nhiên không dùng `csrf().disable()` mặc định cho ứng dụng dùng browser credentials; thay vào đó MockMvc `with(csrf())` cho các case kiểm quyền và test CSRF riêng.

Với **404 để ẩn resource**, nên trả giống nhau cho ID không tồn tại và ID người khác. Nếu API intentionally trả 403 khi một người có quyền biết resource tồn tại nhưng thiếu quyền chỉnh sửa, cũng hợp lý; điều quan trọng là **chính sách nhất quán**, không lộ dữ liệu qua message/body/headers/caching.

## 12. Test plan đủ để chống "security by hiding buttons"

Đừng chỉ test component React/Vue render/hidden. Tạo ma trận theo ba trục:

| Tài nguyên | Hành động | Nhóm người gọi | Điều cần xác nhận |
|---|---|---|---|
| Order 101 | READ | Alice owner | 200 + dữ liệu đúng |
| Order 101 | READ | Bob cùng role USER | 404 + không lộ order |
| Order 101 | CANCEL | Bob không owner | 404 + trạng thái vẫn OPEN |
| Order 101 | CANCEL | Alice owner | 200 + trạng thái CANCELLED |
| Report 51 | READ | Alice USER | 403 |
| Report 51 | APPROVE | Alice USER, giả mạo X-Role | 403 + PENDING |
| Report 51 | APPROVE | Manager tenant east | 200 + APPROVED |
| Report 51 | APPROVE | Manager tenant west | 404 + PENDING |
| Bất kỳ protected API | READ/POST | Anonymous | 401 hoặc entry point phù hợp |
| API ngoài allowlist | Bất kỳ | Logged-in/manager | Bị chặn theo deny-all |
| POST nhạy cảm | Không CSRF token | User có quyền | 403, không side effect |
| Permissions đã bị thu hồi | Action cũ vẫn có nút | User vừa mất quyền | Backend từ chối ngay |

Test **cùng một resource qua nhiều principal** rất quan trọng; nếu chỉ dùng user có quyền, không phát hiện bypass. Với mutation cần kiểm trạng thái database sau khi request bị từ chối, không chỉ status. Với quyền multi-tenant cần ít nhất một user có role cao **ở tenant khác**.

Một E2E UI test có thể xác nhận nút không xuất hiện hoặc disabled khi user thiếu quyền, nhưng đó là **bài test UX**. Phải có backend integration test **gửi thẳng request** để chứng minh security.

### Hai tầng kiểm thử bổ trợ

- **Frontend/UI test:** phần tử không hiện; route guard hoạt động; thông báo lỗi 403/404 hợp lý; cập nhật quyền sau refresh. Không được dùng làm bằng chứng duy nhất của authorization.
- **Backend/HTTP test:** gọi API trực tiếp bằng credentials khác nhau, đúng/sai tenant, đổi ID, giả mạo header, gửi CSRF hợp lệ và kiểm no-side-effect.
- **Repository/database integration:** xác nhận predicate owner/tenant trong query và thao tác ghi/rollback. Có thể dùng Testcontainers/H2 theo đặc tính DB thật; fake map không chứng minh transaction/row isolation production.
- **Pen test/security review có quyền:** kiểm đường cũ, bulk endpoints, file URLs, export, GraphQL resolvers, admin paths và những nơi không đi qua UI chính.

## 13. Những sai lầm phổ biến trong thiết kế

1. **“Ẩn nút là đủ vì user không biết URL.”** Endpoint vẫn có thể được gọi bằng HTTP client; URL/ID là dữ liệu có thể bị đoán, đọc từ Network hoặc lấy qua API khác.
2. **“Frontend đã kiểm role trước khi gọi.”** Backend không có bằng chứng request đi qua frontend; role phải được kiểm server-side.
3. **Chỉ dùng `.authenticated()` trên endpoint nhạy cảm.** Đã đăng nhập không có nghĩa được APPROVE, DELETE hoặc SHARE.
4. **Kiểm role mà không kiểm owner/tenant.** MANAGER west không tự được phê duyệt report east.
5. **Tin `isAdmin`, `role`, `ownerId` trong JSON/body.** Đây là thông tin do client sửa được, phải được kiểm bằng identity/policy server.
6. **Trả entity trực tiếp.** Dễ lộ owner/tenant/internal fields không thuộc quyền đọc; dùng DTO theo contract.
7. **Quên GET/list/export/download và batch.** Quyền không chỉ áp dụng cho nút thao tác ghi; dữ liệu có thể rò qua endpoint đọc hoặc file.
8. **Kiểm quyền sau khi ghi.** Trả 403 nhưng DB đã đổi là lỗi nghiêm trọng; authorize trước mutation và dùng transaction phù hợp.
9. **Dùng một role ADMIN global không có trong policy.** Với multi-tenant cần xác định rõ admin của tenant hay admin toàn hệ thống, và audit quyền đặc biệt.
10. **Tắt CSRF để test POST cho dễ.** Status 403 từ CSRF khác 403 vì thiếu role; giữ các biện pháp đúng và tách test.
11. **Dựa vào UUID/ID khó đoán như quyền.** Biết ID không có nghĩa được truy cập; bảo vệ object-level.
12. **Bỏ policy khi backend được gọi từ cron/job/message queue.** Route guard ở controller không bảo vệ service được gọi qua entry point khác.
13. **Test UI render nhưng không test API.** UI ẩn được nút và vẫn có thể tồn tại BOLA/BFLA (broken function-level authorization).
14. **Cache response riêng tư chỉ theo ID.** Dễ trả dữ liệu của user khác khi quyền/tenant thay đổi; cache phải scoped theo policy hoặc được kiểm quyền trước khi trả.
15. **Tin client capability quá lâu.** User có thể bị revoke sau khi UI tải; quyết định server phải dùng dữ liệu còn hiệu lực.
16. **Cho phép wildcard path/method quá rộng.** Endpoint mới có thể bị cấp quyền ngoài ý định; dùng rule cụ thể và deny-all fallback nếu chính sách yêu cầu.

## 14. Cải tiến kiến trúc theo mức độ trưởng thành

### Mức 1 — Đủ đúng cho một ứng dụng nhỏ

- Spring Security xác thực request và bảo vệ các endpoint nhạy cảm theo method/role.
- Service lấy `Authentication` đáng tin, đối chiếu owner và tenant của tài nguyên.
- Frontend ẩn nút dựa trên thông tin role/capability để không gây nhầm lẫn, nhưng không là nơi quyết định quyền.
- MockMvc có case chặn trực tiếp API bằng tài khoản không được phép.

### Mức 2 — Có nhiều chức năng và resource

- Định nghĩa policy tập trung như `canReadOrder`, `canCancelOrder`, `canApproveReport`, không sao chép `if` rời rạc ở mỗi controller.
- Tách authorization cho từng **action**, tránh dùng `ROLE_MANAGER` như quyền mặc định cho mọi thao tác.
- Thêm method security theo nhu cầu, DTO, audit và test matrix; đảm bảo policy không bị bypass qua service invocation khác.
- Query dữ liệu theo owner/tenant ngay từ DB; bulk/read/write đều chung ranh giới.

### Mức 3 — Nhiều tenant, nhiều nguồn dữ liệu, nhiều service

- Xác định identity, membership, tenant và ACL từ nguồn đáng tin; token/claims phải được xác thực và có kế hoạch revoke/cache.
- Dùng policy decision component hoặc mô hình ABAC/ReBAC phù hợp, audit quyết định đặc quyền, kiểm tra cả service-to-service.
- Ràng buộc tenant trong truy vấn, transaction/mutation; với DB hỗ trợ RLS có thể thêm phòng thủ sâu.
- Kiểm quyền ở các đường background job, download URL, export, message consumer và API gateway; không ỷ lại UI hoặc gateway là nơi duy nhất.
- Đo coverage theo policy branch, endpoint và dữ liệu bị bảo vệ, không chỉ theo code coverage.

## 15. Câu hỏi tự kiểm tra và bài tập

1. Nếu user dùng DevTools bỏ `hidden` khỏi nút “Phê duyệt”, đâu là nơi duy nhất có thể thực thi việc từ chối request?
2. Sự khác biệt giữa `authenticated()`, `hasRole("MANAGER")` và việc kiểm tenant của report 51 là gì?
3. Vì sao Mallory có `ROLE_MANAGER` thực vẫn nhận 404 với report 51?
4. Nếu server tin `X-Role: MANAGER` do client gửi, kịch bản leo thang đặc quyền xảy ra thế nào?
5. Tại sao cần test “Bob hủy order của Alice” dù cả hai cùng `ROLE_USER` và cùng tenant?
6. Nếu frontend hiển thị `canApprove=true` lúc 10:00 nhưng user bị thu hồi quyền lúc 10:05, server phải quyết định dựa trên thông tin nào?
7. Vì sao status 403 trên POST không đủ chứng minh method authorization đúng khi CSRF đang bật?
8. Nếu POST bị từ chối nhưng dữ liệu đã thay đổi, test cần bổ sung assertion gì?
9. Phân quyền cho `DELETE /api/reports/{id}`, export file và bulk update nên được thiết kế theo action/resource như thế nào?
10. Khi tích hợp ứng dụng mobile không có nút HTML, API phải bảo vệ những điều kiện gì?
11. Frontend nhận `401`, `403`, `404` nên phản hồi UX khác nhau ra sao mà không làm lộ resource?
12. Vì sao policy tenant chỉ ở controller có thể không bảo vệ được job gọi trực tiếp repository?

**Kết luận:** Ẩn hoặc disable nút là cách thiết kế giao diện hợp lý nhưng **không phải biện pháp phân quyền**. Security boundary nằm ở backend: xác minh principal → kiểm role/scope theo hành động → kiểm owner/tenant/ACL của đối tượng → chỉ sau đó mới đọc/ghi dữ liệu. Kiểm thử phải **bỏ qua UI, gửi HTTP request trực tiếp và xác nhận dữ liệu không thay đổi khi bị từ chối**.

## Tài liệu chính thức để đọc thêm

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Testing MockMvc and Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API Security Top 10 — Broken Function Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/)
