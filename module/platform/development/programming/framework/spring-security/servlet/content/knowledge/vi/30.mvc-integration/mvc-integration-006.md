# Hiển thị hoặc ẩn chức năng ở giao diện không thay thế phân quyền máy chủ

> **Phạm vi:** Spring Security trên Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x và Java 17+). Bài giải thích mối quan hệ giữa việc **hiển thị/ẩn chức năng trên giao diện** và việc **kiểm soát quyền truy cập bắt buộc ở server**. Ví dụ dùng Thymeleaf, Servlet `SecurityFilterChain`, method security, kiểm tra quyền theo từng tài nguyên và MockMvc. Người đọc cần phân biệt rõ **UX (giao diện)** với **security boundary (ranh giới bảo mật)**.

## 1. Quy tắc quan trọng nhất

**Ẩn một nút, menu, đường dẫn hoặc thành phần HTML không làm cho endpoint phía server an toàn.** Giao diện có thể hỗ trợ trải nghiệm bằng cách chỉ hiển thị những hành động người dùng có khả năng thực hiện, nhưng quyền thực sự phải được **xác minh ở backend trên mỗi yêu cầu có tác động tới dữ liệu**.

Giả sử ứng dụng có chức năng xuất báo cáo quản trị:

- Tài khoản thường không thấy nút **Xuất tất cả báo cáo**.
- Người dùng có thể tự gõ URL, sửa HTML/CSS trong Developer Tools, gửi HTTP request bằng script, curl hoặc Postman, hoặc gọi API trực tiếp.
- Nếu backend không kiểm tra quyền ở `POST /admin/export`, request vẫn có thể chạy dù nút không bao giờ được render.

Sự khác nhau nằm ở nơi thực thi:

| Hành động | Mục tiêu | Có thể xem là kiểm soát bảo mật? |
| --- | --- | --- |
| Ẩn bằng CSS `display: none`, thuộc tính `hidden` | Không cho người dùng thấy một phần tử. | **Không**. DOM và API vẫn có thể bị truy cập. |
| Tắt nút bằng `disabled` | Ngăn thao tác trong UI thông thường. | **Không**. HTTP client khác không tuân theo trạng thái nút. |
| Không render phần tử bằng `th:if` hoặc `sec:authorize` | Cải thiện UX, tránh hiển thị lựa chọn không phù hợp. | **Không đủ**. Chỉ kiểm soát HTML response hiện tại. |
| React/Vue điều kiện hóa giao diện theo `role` hoặc `canExport` | UX, giúp ứng dụng nhất quán với server. | **Không**. Client state sửa được. |
| `authorizeHttpRequests(...)` trong Spring Security | Bảo vệ request theo URL/method và authorities. | **Có**, ở điểm vào HTTP; phải thiết kế matcher đúng. |
| `@PreAuthorize` tại service | Bảo vệ thao tác nghiệp vụ trước khi gọi method. | **Có**, khi method security được bật và lời gọi đi qua Spring proxy/interceptor. |
| Kiểm tra ownership/tenant tại dữ liệu | Xác minh user có quyền trên đúng bản ghi/tài nguyên. | **Có**, nếu được thực thi ở server và mọi code path đều áp dụng. |

**Nguyên tắc thực tế:** giao diện có thể hỏi “nút này có nên xuất hiện không?”, nhưng server **phải tự trả lời lại** “request này có được phép thực hiện không?” trên danh tính, quyền và tài nguyên thực tế của request đó.

## 2. Vì sao ẩn giao diện không ngăn tấn công?

### 2.1 Client là môi trường không đáng tin

Browser thuộc quyền điều khiển của người dùng. Bất kỳ điều kiện nào chỉ chạy ở client đều có thể bị bỏ qua hoặc sửa:

~~~javascript
// Chỉ phục vụ trải nghiệm người dùng, KHÔNG phải kiểm soát truy cập.
const canExport = currentUser.roles.includes("ADMIN");

if (canExport) {
  document.querySelector("#export-button").hidden = false;
}
~~~

Một người không có quyền có thể bỏ qua JavaScript và gửi request thẳng tới API. Thậm chí browser extension, script tự động hoặc thiết bị khác không dùng UI này. Vì vậy `canExport` trong JavaScript chỉ là một **gợi ý hiển thị**, không phải quyền mà server được tin.

Một ví dụ HTTP trực tiếp, mang tính minh họa:

~~~http
POST /admin/export HTTP/1.1
Host: app.example.org
Cookie: JSESSIONID=example-session-cookie
Content-Type: application/x-www-form-urlencoded

format=csv
~~~

Endpoint phải kiểm tra cả **authentication** (ai đang gọi), **authorization** (được phép xuất hay không), các điều kiện nghiệp vụ và CSRF (nếu dùng credential tự động gửi như cookie). Không dựa vào việc người gọi có thấy nút hay không.

### 2.2 Ẩn khác với không gửi dữ liệu

Có hai việc khác nhau:

1. Server **vẫn gửi dữ liệu nhạy cảm** vào HTML/JSON nhưng dùng CSS để giấu: dữ liệu đã tới client, có thể bị đọc trong source/DOM/Network. Đây là **rò rỉ dữ liệu**, không chỉ là UX sai.
2. Server kiểm tra quyền trước khi truy vấn/trả dữ liệu và chỉ render nội dung được phép: đây mới là kiểm soát truy cập phù hợp.

Không đưa password, token, thông tin người dùng khác, giá nội bộ hay báo cáo quản trị vào HTML/JSON của người không có quyền rồi kỳ vọng `display:none` sẽ bảo vệ. Quyền phải được thực thi **trước khi trả nội dung nhạy cảm**.

### 2.3 Không phải chỉ có nút “admin”

Ngay cả chức năng xem tài nguyên bình thường cũng cần kiểm tra quyền theo **đối tượng cụ thể**. Ví dụ:

~~~text
GET /reports/11  -> báo cáo của alice
GET /reports/12  -> báo cáo của bob
~~~

Cả alice và bob đều có role USER; vì thế `hasRole("USER")` **không đủ** để quyết định alice có được đọc báo cáo 12. Nếu server chỉ xác thực và cho user tự đổi ID trong URL, ứng dụng mắc lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Quy tắc chính xác là: người dùng phải có role/chức năng phù hợp **và** được phép xem chính bản ghi đó (theo owner, tenant, ACL hoặc policy). Không tin `ownerId` do client gửi.

## 3. Ba tầng trách nhiệm trong ứng dụng Spring MVC

Một thiết kế rõ ràng tách các lớp:

~~~text
                         Trải nghiệm người dùng
[Thymeleaf / JSP / SPA]
  - sec:authorize, th:if, canExport...
  - ẩn/hiện menu, thông báo trạng thái
                    |
                    v HTTP request
                         Ranh giới server
[Spring Security Servlet Filter Chain]
  - authentication: ai đang gọi?
  - authorizeHttpRequests: URL/method nào được phép?
  - CSRF protection (khi phù hợp)
                    |
                    v Controller
[Service / Method Security]
  - @PreAuthorize: thao tác nghiệp vụ nào được phép?
  - policy theo quyền, owner, tenant, trạng thái
                    |
                    v
[Repository / Data Access]
  - giới hạn truy vấn theo account/tenant
  - tránh đọc/chỉnh sửa dữ liệu ngoài phạm vi
~~~

Tầng UI **không thay** cho bất kỳ tầng server nào. Trong các hệ thống có nhiều điểm vào (REST, MVC, job, message consumer), kiểm tra ở **service/business layer** có giá trị vì không phụ thuộc một URL/controller duy nhất. Tuy nhiên URL authorization vẫn là lớp phòng vệ hữu ích; không nên để mọi endpoint mở rồi hy vọng controller nào cũng nhớ kiểm tra.

## 4. Hiển thị theo quyền bằng Thymeleaf và Spring Security

Thymeleaf có dialect `thymeleaf-extras-springsecurity6`, cung cấp thuộc tính `sec:authorize` để điều kiện hóa phần HTML theo `Authentication` của Spring Security.

### 4.1 Các dependency cần thiết

Trong một dự án Maven Spring Boot 3.x dùng Spring MVC, thêm các dependency sau vào phần `<dependencies>` của `pom.xml`. Đây là **đoạn cấu hình**, không phải một POM hoàn chỉnh:

~~~xml
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
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
        <groupId>org.thymeleaf.extras</groupId>
        <artifactId>thymeleaf-extras-springsecurity6</artifactId>
    </dependency>
</dependencies>
~~~

Khi dùng Spring Boot dependency management/BOM, các phiên bản tương thích thường được quản lý tập trung. Không tự chọn artifact Spring Security 5 cho Boot 3/Security 6. Đảm bảo ứng dụng đã có `Authentication` hợp lệ trong Spring Security context.

### 4.2 Template Thymeleaf

File `src/main/resources/templates/dashboard.html`:

~~~html
<!DOCTYPE html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org"
      xmlns:sec="http://www.thymeleaf.org/extras/spring-security">
<head>
    <meta charset="UTF-8">
    <title>Bảng điều khiển</title>
</head>
<body>
    <h1>Bảng điều khiển</h1>

    <p sec:authorize="isAnonymous()">
        Vui lòng đăng nhập để xem các báo cáo của bạn.
    </p>

    <div sec:authorize="isAuthenticated()">
        <p>Đăng nhập với tên:
            <strong sec:authentication="name">Người dùng</strong>
        </p>
        <a th:href="@{/reports/11}">Ví dụ: xem báo cáo số 11</a>
    </div>

    <section sec:authorize="hasRole('ADMIN')">
        <h2>Chức năng quản trị</h2>
        <form th:action="@{/admin/export}" method="post">
            <button type="submit">Xuất tất cả báo cáo</button>
        </form>
    </section>

    <p sec:authorize="!hasRole('ADMIN')">
        Chức năng xuất báo cáo quản trị không có trong tài khoản này.
    </p>
</body>
</html>
~~~

Giải thích:

- `sec:authorize="hasRole('ADMIN')"` chỉ render form nếu current Spring Authentication có authority `ROLE_ADMIN` theo quy ước mặc định. **Nó không tự bảo vệ `/admin/export`**.
- `sec:authorize="isAuthenticated()"` dùng để hiển thị phần dành cho user đã đăng nhập. Điều này **không đảm bảo user sở hữu báo cáo 11**; đường dẫn demo phía trên cần policy kiểm tra ownership ở server.
- `sec:authentication="name"` đọc tên từ Spring Security Authentication, không lấy tên tùy ý từ client.
- Với form POST và `th:action`, tích hợp Spring MVC/Thymeleaf với `RequestDataValueProcessor` của Spring Security thường thêm hidden CSRF input. **Phải kiểm tra HTML đã render** và bảo đảm token CSRF được gửi nếu ứng dụng dùng CSRF; đừng vì lỗi 403 mà tắt CSRF toàn cục.
- Các biểu thức hiển thị không thực thi lại khi HTML đã tới browser; quyền thay đổi trong một phiên cần refresh/reload UI hoặc cập nhật state. Ngay cả khi UI cũ, server vẫn phải kiểm tra quyền hiện hành.
- Mã chỉ minh họa display logic. Những URL tồn tại và khả năng truy cập phải được cấu hình tại server.

**Không nhầm `sec:authorize` với `@PreAuthorize`**: biểu thức đầu tiên quyết định **render HTML**; annotation thứ hai có thể quyết định **một lời gọi method được thực thi hay bị từ chối** khi method security hoạt động.

### 4.3 JSP và frontend SPA

Nếu dự án cũ dùng JSP, Spring Security taglibs cũng cung cấp tag `<sec:authorize access="hasRole('ADMIN')">` (cần dependency/taglib phù hợp). Ví dụ **mảnh JSP**:

~~~jsp
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>

<sec:authorize access="hasRole('ADMIN')">
    <a href="/admin">Quản trị</a>
</sec:authorize>
~~~

Việc không render link **không** bảo vệ `GET /admin`. Mặt khác, ứng dụng React/Vue/Angular có thể gọi endpoint `GET /api/me/capabilities` do server tính toán để biết các hành động có thể hiển thị. JSON như `{"canExport":false}` là **gợi ý UX**; API xuất báo cáo vẫn phải thực thi authorization bằng principal/authority/policy tại thời điểm nhận POST.

## 5. Phân quyền thực sự bằng SecurityFilterChain

Đây là class cấu hình **Java 17+ chạy trong một dự án Spring Boot** đã có các starter ở phần trước. Ví dụ minh họa URL authentication/authorization bằng Spring Security 6 Servlet.

File `src/main/java/com/example/ui/SecurityConfig.java`:

~~~java
package com.example.ui;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/css/**")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Điểm cần nắm:**

1. `authorizeHttpRequests` áp dụng **ở server** qua Servlet Security Filter Chain; không phụ thuộc việc nút có được render hay không.
2. `requestMatchers("/admin/**").hasRole("ADMIN")` buộc mọi HTTP request match phạm vi `/admin/**` có `ROLE_ADMIN`. Một người không có quyền vẫn bị chặn nếu họ gửi POST thủ công.
3. `requestMatchers("/reports/**").authenticated()` chỉ đảm bảo đã đăng nhập. Nó **chưa** giới hạn user vào báo cáo của chính mình; ví dụ ownership ở phần tiếp theo giải quyết việc đó.
4. **Thứ tự matcher quan trọng.** Rule hẹp/bảo mật hơn cần đặt trước rule rộng có thể match cùng URL.
5. `anyRequest().denyAll()` thiết lập fail-closed cho các endpoint chưa khai báo; đây là một lựa chọn bảo mật chủ động. Khi thêm endpoint hợp lệ khác, hãy bổ sung matcher rõ ràng. Đừng dùng `anyRequest().permitAll()` vì muốn UI “dễ chạy”.
6. `formLogin(...)` trong ví dụ sử dụng login page mặc định của Spring Security. Trong ứng dụng thực, thay bằng cơ chế xác thực đang dùng (OIDC, SAML2, session, v.v.) nhưng **giữ phân quyền tương ứng ở server**.
7. `@EnableMethodSecurity` bật xử lý các annotation như `@PreAuthorize`. Không thể chỉ gắn annotation lên method rồi giả định nó sẽ hoạt động khi chưa bật method security.
8. CSRF protection mặc định của Spring Security vẫn được bật. Request POST dựa vào cookie cần CSRF token khi áp dụng; **403 có thể do thiếu token hoặc thiếu quyền**, phải phân biệt.

### hasRole và hasAuthority có khác nhau?

Trong cấu hình mặc định, `hasRole("ADMIN")` kiểm tra granted authority `ROLE_ADMIN`. Còn `hasAuthority("EXPORT_REPORTS")` kiểm tra authority có tên **chính xác** `EXPORT_REPORTS`. Chúng không phải cùng một chuỗi tùy ý. Chọn convention rõ ràng và nhất quán với user directory/IdP/authority mapper.

Ví dụ hệ thống có thể chọn role tổng hợp `ROLE_ADMIN` nhưng permission hẹp hơn `EXPORT_REPORTS`. Khi đó UI và server có thể hỏi các biểu thức giống nhau để thống nhất UX, nhưng **chỉ server** có quyền quyết định thực thi. Không tự động coi mọi người đăng nhập đều có khả năng export.

## 6. Ví dụ Spring Boot end-to-end tối giản

Đoạn dưới là cấu trúc minh họa có thể đặt trong một ứng dụng Spring Boot 3.x. Dùng tài khoản **demo trong bộ nhớ**, không nên triển khai nguyên trạng ra production. Các class đặt trong package `com.example.ui` để Spring Boot quét bean.

### 6.1 Điểm khởi động ứng dụng

File `src/main/java/com/example/ui/UiAuthorizationDemoApplication.java`:

~~~java
package com.example.ui;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UiAuthorizationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UiAuthorizationDemoApplication.class, args);
    }
}
~~~

### 6.2 Tài khoản demo cho việc thử quyền

File `src/main/java/com/example/ui/DemoUsersConfig.java`:

~~~java
package com.example.ui;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-user-password"))
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(encoder.encode("demo-admin-password"))
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
~~~

Tài khoản `alice` chỉ có `ROLE_USER`; `manager` có thêm `ROLE_ADMIN`. Mật khẩu trong code chỉ để **chạy thử local** và được hash khi xây user; không bao giờ để mật khẩu production hard-code trong source. Ứng dụng thật tích hợp user store/SSO và quy trình quản lý credential phù hợp.

### 6.3 Controller render trang chủ

File `src/main/java/com/example/ui/DashboardController.java`:

~~~java
package com.example.ui;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DashboardController {

    @GetMapping("/")
    public String dashboard() {
        return "dashboard";
    }
}
~~~

Spring MVC sẽ render file `templates/dashboard.html` đã trình bày ở phần 4 nếu Thymeleaf starter được cấu hình bình thường.

### 6.4 Endpoint admin: luôn kiểm tra ở server

File `src/main/java/com/example/ui/AdminController.java`:

~~~java
package com.example.ui;

import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    @PostMapping(value = "/admin/export",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    @PreAuthorize("hasRole('ADMIN')")
    public String export() {
        return "Export accepted";
    }
}
~~~

Ở đây có **hai lớp bảo vệ** cho demo:

- `SecurityFilterChain` bắt mọi `/admin/**` yêu cầu role ADMIN, kể cả gọi trực tiếp không thông qua UI.
- `@PreAuthorize("hasRole('ADMIN')")` bảo vệ lời gọi method khi Spring Method Security đã bật, giúp giảm rủi ro nếu sau này có thêm code path dùng method này. Với nghiệp vụ phức tạp, thường đặt method security ở service thay vì chỉ trên controller.
- Demo trả chuỗi ngắn, không thật sự xuất dữ liệu. Khi viết export thật, phải kiểm tra phạm vi dữ liệu mà admin được xuất, log audit đúng cách và tránh trả dữ liệu nhạy cảm vượt quyền.

**Đường POST vẫn cần CSRF token khi dùng form/session**. Một user có `ROLE_ADMIN` có thể bị HTTP 403 nếu gửi POST thiếu CSRF token. Đó là lớp bảo vệ khác, không có nghĩa role sai.

## 7. Quyền theo tài nguyên: role USER không đủ

### 7.1 Ví dụ lỗi IDOR/BOLA

Một API không an toàn nếu chỉ làm thế này:

~~~java
@GetMapping("/reports/{id}")
public Report get(@PathVariable Long id) {
    return reportRepository.findById(id).orElseThrow();
}
~~~

Đoạn trên **chỉ minh họa anti-pattern**, không thể biên dịch độc lập vì `Report` và `reportRepository` là thành phần dự án. Nếu matcher `/reports/**` chỉ yêu cầu authenticated, alice có thể thử ID của bob. Việc UI chỉ hiển thị báo cáo của alice **không ngăn** HTTP GET trực tiếp tới ID của bob.

Cần kiểm tra server-side **owner, tenant, ACL hoặc policy nghiệp vụ** trên ID mà request yêu cầu. Ví dụ đặt kiểm tra ở service/method security để không phụ thuộc controller.

### 7.2 Policy ownership minh họa, fail-closed

File `src/main/java/com/example/ui/ReportAccess.java`:

~~~java
package com.example.ui;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportAccess")
public class ReportAccess {

    // Dữ liệu local minh họa; ứng dụng thực dùng DB/ACL/tenant.
    private final Map<Long, String> owners =
            Map.of(11L, "alice", 12L, "bob");

    public boolean canRead(Authentication authentication, long reportId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        String owner = owners.get(reportId);
        if (owner == null) {
            return false;
        }

        boolean isAdmin = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return isAdmin || owner.equals(authentication.getName());
    }
}
~~~

Quy tắc demo: báo cáo 11 do alice sở hữu, báo cáo 12 do bob sở hữu; admin có thể đọc cả hai nếu bản ghi tồn tại. Một ID không tồn tại trả false, không cấp quyền theo mặc định. Trong hệ thống thật cần quyết định trả 403 hay 404 theo policy và dùng repository/truy vấn có kiểm soát; không dùng Map giả để vận hành production.

**Quan trọng:** role admin được quyết định dựa trên `Authentication.getAuthorities()` do Spring Security xác lập, **không** lấy từ query parameter hoặc request body `isAdmin=true`. Nếu có multi-tenant, kiểm tra cả tenant của user và tenant của báo cáo; “cùng role” giữa hai tenant không mặc nhiên cấp quyền chéo.

### 7.3 Service áp dụng @PreAuthorize

File `src/main/java/com/example/ui/ReportService.java`:

~~~java
package com.example.ui;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("@reportAccess.canRead(authentication, #p0)")
    public String readReport(long reportId) {
        return "Report " + reportId;
    }
}
~~~

`#p0` là tham số method đầu tiên trong SpEL method security, giúp ví dụ không lệ thuộc việc compiler giữ parameter names. `authentication` là Spring Authentication hiện tại. Khi method security hoạt động, Spring gọi bean `reportAccess` để xác định user có thể xem báo cáo hay không. Tên bean được chỉ rõ bằng `@Component("reportAccess")`.

Đây là logic **tối giản để minh họa quyền**: trong ứng dụng thật, service phải đọc tài nguyên từ data store, áp dụng tenant/owner filter khi query, tránh TOCTOU nếu quyền hoặc dữ liệu có thể thay đổi giữa kiểm tra và sử dụng. Có thể dùng repository query ràng buộc theo `ownerId`/`tenantId` thay vì lấy mọi dữ liệu rồi lọc ở UI.

### 7.4 Controller gọi service đã bảo vệ

File `src/main/java/com/example/ui/ReportController.java`:

~~~java
package com.example.ui;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping(value = "/reports/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String read(@PathVariable long id) {
        return reportService.readReport(id);
    }
}
~~~

Vì `ReportController` gọi một **Spring-managed service bean** được method-security proxy/interceptor xử lý, `@PreAuthorize` ở service có cơ hội từ chối trước khi thực hiện `readReport`.

**Cảnh báo về self-invocation:** nếu một method trong cùng service gọi trực tiếp method có `@PreAuthorize` thông qua `this.`, lời gọi có thể không đi qua proxy, tùy chế độ AOP. Không dựa vào annotation tại một điểm gọi không được intercept; thiết kế service boundary và kiểm thử đường gọi thực tế. Không biến mỗi check thành thao tác client tự báo “đã được phép”.

## 8. Kiểm thử server-side authorization với MockMvc

Một kiểm thử đúng phải **gửi request trực tiếp**, không phụ thuộc việc có/không có nút trong template. Spring Security Test cho phép mô phỏng principal, CSRF và kiểm tra status.

Thêm dependency test vào phần `<dependencies>` của `pom.xml`, trong dự án đã dùng Boot dependency management:

~~~xml
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
~~~

File `src/test/java/com/example/ui/AuthorizationIntegrationTest.java`:

~~~java
package com.example.ui;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void normalUserCannotCallHiddenAdminEndpoint() throws Exception {
        mvc.perform(post("/admin/export").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void adminCanExportWithCsrf() throws Exception {
        mvc.perform(post("/admin/export").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("Export accepted"));
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void missingCsrfBlocksEvenAdmin() throws Exception {
        mvc.perform(post("/admin/export"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnReport() throws Exception {
        mvc.perform(get("/reports/11"))
                .andExpect(status().isOk())
                .andExpect(content().string("Report 11"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void cannotReadAnotherUsersReport() throws Exception {
        mvc.perform(get("/reports/12"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "manager", roles = {"USER", "ADMIN"})
    void adminCanReadExistingReport() throws Exception {
        mvc.perform(get("/reports/12"))
                .andExpect(status().isOk())
                .andExpect(content().string("Report 12"));
    }
}
~~~

**Giải thích kiểm thử:**

- Test POST cho USER thêm `csrf()` để loại bỏ yếu tố thiếu token, nhờ đó kết quả 403 thực sự kiểm tra **quyền admin**, không vô tình pass vì CSRF.
- Test admin hợp lệ gửi token nên có thể vào controller và nhận `Export accepted`.
- Test admin không có CSRF minh họa CSRF và authorization là **hai phép kiểm tra độc lập**.
- Test alice không xem được `reports/12` chứng minh backend kiểm tra owner, ngay cả khi người dùng tự nhập URL.
- `@WithMockUser` tạo Spring Security Authentication giả lập cho test; nó **không xác nhận** tích hợp production IdP/SSO hoặc policy từ database thực tế. Khi dùng production user store/tenant, cần thêm integration tests kiểm chứng mappings và dữ liệu thật.

Với Maven dự án đã cấu hình đúng, chạy:

~~~bash
mvn test
~~~

Các test trên phải được chạy trong một dự án chứa đầy đủ class và dependencies của ví dụ. Không cung cấp một “stdout cố định” cho Maven vì số lượng test, phiên bản plugin và các module khác có thể thay đổi. Kỳ vọng sáu test này thành công trong cấu hình mẫu tương thích; nếu phát sinh 401/302/403 không mong đợi, kiểm tra security chain, CSRF, method security và principal của test.

## 9. Trạng thái HTTP: 401, 403 và redirect không giống nhau

Khi kiểm tra URL server-side, hãy phân biệt:

- **Chưa đăng nhập**: request có thể nhận **401 Unauthorized**, hoặc **302 redirect** tới login page nếu ứng dụng dùng form login. Tùy AuthenticationEntryPoint, không nên khẳng định mọi endpoint đều trả 401.
- **Đã đăng nhập nhưng không đủ quyền**: thường nhận **403 Forbidden** bởi AccessDeniedHandler.
- **Thiếu CSRF token hoặc token sai**: một request POST/PUT/PATCH/DELETE dùng cookie có thể nhận **403** dù user có role đúng.
- **Tài nguyên không tồn tại hoặc không được lộ tồn tại**: ứng dụng có thể chọn 404 theo chính sách. Không để mã status hoặc thông báo lỗi lộ dữ liệu mà người gọi không nên biết.

Nếu frontend thấy 403, **đừng sửa bằng cách hiện nút hoặc tắt CSRF**. Kiểm tra: principal đang là ai, authorities thực tế, matcher/method nào được gọi, token CSRF có hợp lệ không, và policy quyền theo tài nguyên đã trả lời gì.

## 10. Những kiểm tra cần có ngoài việc ẩn menu

### 10.1 Phân biệt authentication, authorization, CSRF

Một request có thể vượt qua authentication nhưng không được authorization. Một request có quyền đầy đủ vẫn có thể bị CSRF chặn; đó là hành vi chính xác khi browser tự đính kèm session cookie nhưng yêu cầu thay đổi trạng thái không có bằng chứng ý định hợp lệ.

Đừng biến ứng dụng thành “secure” bằng cách:
- `http.csrf(csrf -> csrf.disable())` chỉ để form POST khỏi 403.
- `anyRequest().permitAll()` chỉ để JavaScript không bị chặn.
- Chỉ kiểm tra `role` phía React/Thymeleaf mà bỏ `authorizeHttpRequests` hoặc business policy.
- Dùng GET để thực hiện thao tác thay đổi trạng thái như xóa/export có side effect, nhằm tránh form CSRF.

CSRF protection không thay thế quyền; authorization không thay thế CSRF. CORS và SameSite cookie cũng không phải phép kiểm tra quyền của một user trên báo cáo cụ thể.

### 10.2 Tách menu permission và data permission

Người dùng có thể có quyền xem menu “Báo cáo” nhưng chỉ được xem báo cáo của phòng ban hoặc tenant mình. Dữ liệu có thể còn phụ thuộc:

- `tenantId` của user và báo cáo.
- Owner, team, organization hoặc project membership.
- Trạng thái của tài nguyên (draft, locked, published).
- Permission chi tiết (VIEW_REPORT, EDIT_REPORT, EXPORT_REPORT).
- Mức nhạy cảm hoặc quy tắc phân tách nhiệm vụ (separation of duties).

Khi tính “nút sửa có xuất hiện không?”, server có thể cung cấp boolean được tính theo **cùng policy domain** đang thực thi hành động thật. Nhưng đừng cho client gửi lại `canEdit=true` rồi tin: request update phải gọi policy lần nữa dựa trên principal/tài nguyên hiện tại.

### 10.3 Các đường vào khác MVC controller

Một business operation có thể được gọi từ REST controller, GraphQL resolver, message consumer, scheduled job hoặc một service nội bộ. Nếu quyền chỉ được kiểm tra trong một MVC controller, đường khác có thể bypass. Tổ chức một **authorization service/policy** rõ ràng và đặt kiểm soát tại ranh giới nghiệp vụ, ngoài URL checks.

Đối với background jobs không có user HTTP session, cần xác định **service identity** và cơ chế phân quyền riêng; không giả mạo `ROLE_ADMIN` hoặc dùng một tài khoản “super user” chung cho mọi tác vụ. Audit log phải phản ánh principal/service thật, action và tài nguyên bị ảnh hưởng.

### 10.4 Tránh lộ dữ liệu trong template

Không render nội dung admin rồi chỉ ẩn bằng CSS. Không gửi toàn bộ JSON báo cáo và lọc ở JavaScript. Hãy áp dụng filtering/authorization trước khi lấy và trả dữ liệu. Với trang có nhiều thành phần nhạy cảm, nên thiết kế model chỉ chứa các trường được phép, hạn chế đưa object entity đầy đủ ra view.

### 10.5 Không để authorization phụ thuộc UI framework

Thymeleaf `sec:authorize`, JSP `sec:authorize` và React conditional rendering là ba cách thể hiện UX khác nhau. Chúng đều không thay thế quy tắc phía server. Nếu bạn chuyển giao diện từ Thymeleaf sang SPA, **backend security policy phải tiếp tục hoạt động** mà không cần sao chép lại quyền trong JavaScript.

## 11. Checklist bảo mật trước khi triển khai

1. **Mọi endpoint nhạy cảm** có rule server-side rõ ràng (URL authorization và/hoặc service authorization), kể cả GET đọc dữ liệu nhạy cảm.
2. **Quyền đối tượng** được kiểm tra theo owner/tenant/ACL, không chỉ role tổng quát.
3. **Method security** thực sự được bật và được gọi qua proxy/interceptor; có test cho cả đường vào HTTP và lời gọi service.
4. **UI** chỉ dùng thông tin capability để hỗ trợ trải nghiệm, không được giữ bí mật dưới dạng hidden DOM/JSON.
5. **Dữ liệu** chỉ được truy vấn/trả về khi policy cho phép, có cơ chế chống enumeration/IDOR.
6. **POST/PUT/PATCH/DELETE** được bảo vệ phù hợp với CSRF khi dùng cookie/session; không xem CSRF 403 là lỗi role một cách máy móc.
7. **Phân quyền tối thiểu**: không cấp `ROLE_ADMIN` hoặc `permitAll` chỉ để màn hình hoạt động.
8. **Authentication từ IdP/DB** được map sang authorities đáng tin; không lấy role từ header/query/body của client mà không kiểm chứng.
9. **Kiểm thử tiêu cực**: user thường tự POST endpoint admin, thay URL ID, truy cập khác tenant, gọi API không qua UI, token CSRF thiếu, user đã logout/role bị thu hồi.
10. **Audit và lỗi**: server ghi đủ hành động bị từ chối trong log kiểm soát, không tiết lộ bí mật trong response.
11. **Nguyên tắc phòng thủ nhiều lớp**: URL/method layer + domain policy + data access filters áp dụng nhất quán.

## 12. Những hiểu lầm phổ biến và cách sửa

| Hiểu lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Không có nút admin thì user không gọi được chức năng.” | HTTP endpoint độc lập với HTML được render. | Bảo vệ `/admin/**` và service ở server. |
| “Nút disabled sẽ ngăn thay đổi dữ liệu.” | Client có thể gửi POST trực tiếp. | Luôn kiểm tra server-side authorization và validation. |
| “Có `sec:authorize` là đủ.” | Dialect chỉ điều khiển output template. | Dùng `authorizeHttpRequests`, `@PreAuthorize` và resource policy. |
| “Ai có ROLE_USER đều xem được mọi báo cáo.” | Role không chứng minh owner/tenant. | Kiểm tra object-level authorization. |
| “Frontend gửi `isAdmin=true` thì server làm theo.” | Dữ liệu client kiểm soát được. | Quyền lấy từ Authentication/permission store đáng tin. |
| “API trả 403, cứ tắt CSRF để sửa.” | 403 có thể là đúng vì token thiếu hoặc quyền không đủ. | Chẩn đoán CSRF và authorization riêng. |
| “Chỉ cần bảo vệ controller.” | Method có thể được gọi từ đường khác. | Đặt security tại business boundary; dùng method security đúng. |
| “Ẩn dữ liệu bằng CSS thì không lộ.” | Dữ liệu đã ở DOM/Network. | Không gửi dữ liệu không được phép. |
| “Admin ở tenant A có quyền ở tenant B.” | Role không tự bao gồm tenant scope. | Ràng buộc user, resource và tenant trong policy. |
| “Test HTML không hiện nút nghĩa là backend an toàn.” | Kiểm thử UI bỏ qua HTTP direct access. | Test status/response của endpoint với roles và resource IDs. |

## 13. Tóm tắt

**UI visibility là quyết định trải nghiệm**, còn **authorization là quyết định bảo mật phía server**. Spring MVC/Thymeleaf có thể dùng `sec:authorize` để hiển thị đúng menu; Spring Security Servlet dùng `SecurityFilterChain` để chặn URL/method; `@PreAuthorize` và policy nghiệp vụ kiểm tra quyền trên thao tác và tài nguyên; data access layer giới hạn dữ liệu có thể đọc/sửa. Tất cả phải hoạt động kể cả khi người dùng **không bao giờ mở giao diện**, tự gọi API hoặc thay đổi request.

**Quy tắc cần nhớ:** *Đừng bảo vệ một chức năng bằng cách giấu chỗ bấm; hãy bảo vệ chính hành động mà chỗ bấm đó kích hoạt.*

## Tài liệu tham khảo

- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Thymeleaf Extras Spring Security: https://github.com/thymeleaf/thymeleaf-extras-springsecurity
