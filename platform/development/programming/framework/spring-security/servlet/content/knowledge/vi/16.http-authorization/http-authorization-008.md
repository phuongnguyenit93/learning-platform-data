# AuthorizationManager cho quy tắc truy cập tùy chỉnh

Trong **Spring Security dành cho Servlet**, việc xác thực trả lời câu hỏi “request này do ai gửi?”; **phân quyền HTTP** trả lời câu hỏi khác: “danh tính đó có được phép truy cập tài nguyên tại URL và phương thức HTTP này không?”. Các quy tắc thông dụng như `authenticated()`, `hasRole("ADMIN")` hoặc `hasAuthority("project:read")` rất hữu ích, nhưng đôi khi chưa đủ: một người chỉ được xem dự án của **chính mình**, quản trị viên chỉ được quản lý dự án **trong tenant của mình**, hoặc request chỉ được chấp nhận nếu một điều kiện nghiệp vụ đáng tin cậy đang thỏa mãn.

`AuthorizationManager<T>` là abstraction của Spring Security để đưa những quyết định đó vào luồng kiểm tra quyền. Ở tầng HTTP Servlet, kiểu ngữ cảnh thường dùng là `RequestAuthorizationContext`; nó cung cấp request cùng những biến đường dẫn lấy từ `RequestMatcher` phù hợp. Ta có thể cung cấp một `AuthorizationManager<RequestAuthorizationContext>` cho `authorizeHttpRequests(...).requestMatchers(...).access(customManager)` để thực hiện quy tắc tùy chỉnh mà vẫn giữ authorization trong Security Filter Chain.

Mục tiêu của bài học:

- Hiểu `AuthorizationFilter`, `RequestMatcher`, `AuthorizationManager` và `Authentication` phối hợp thế nào.
- Biết khi nào dùng rule dựng sẵn và khi nào nên viết manager riêng.
- Viết quy tắc HTTP cho **chủ sở hữu dự án + tenant + quyền quản trị**, từ dữ liệu ở server chứ không tin khai báo của client.
- Sử dụng `RequestAuthorizationContext.getVariables()` một cách an toàn; **thiếu hoặc sai biến thì deny**, không tự suy luận.
- Phân biệt kết quả 401, 403 và 404, thứ tự các matcher, nhiều SecurityFilterChain và CSRF.
- Thiết kế kiểm thử bằng Spring Security Test/MockMvc và chương trình Java 17 độc lập có stdout xác định.
- Nhận diện giới hạn của việc chỉ kiểm tra HTTP: service/method security, tình huống TOCTOU, dữ liệu thay đổi và các đường thực thi không đi qua HTTP.

Phạm vi ví dụ: **Java 17+, Spring Boot 3.x, Spring Security 6.x với Servlet/MVC**. Một số phiên bản Spring Security 6.x đã chuyển hướng API từ `check(...)` tới `authorize(...)` và đánh dấu `check` là deprecated; bài sử dụng `check(...)` cho khả năng đối chiếu rộng với nhiều phiên bản 6.x, đồng thời giải thích cách kiểm tra chữ ký theo version. Các đoạn Spring cần đầy đủ dependencies; chỉ chương trình Java thuần ở mục 12 chạy trực tiếp bằng JDK 17 không có thư viện ngoài.

## 1. Xác thực khác phân quyền như thế nào?

Một request GET tài nguyên dự án có thể đi qua các bước:

~~~text
GET /api/projects/101
Authorization: Basic <credentials>
           |
           v
FilterChainProxy chọn SecurityFilterChain đầu tiên khớp
           |
           v
Authentication filter (ví dụ BasicAuthenticationFilter)
           |-- AuthenticationManager + AuthenticationProvider
           |-- kiểm tra password
           |-- Authentication đã xác thực, có authorities
           |
           v
AuthorizationFilter
           |-- RequestMatcher: GET /api/projects/{projectId}
           |-- AuthorizationManager<RequestAuthorizationContext>
           |       |
           |       +-- principal do provider xác thực?
           |       +-- projectId từ matcher?
           |       +-- dự án thuộc tenant được phép?
           |       +-- user sở hữu dự án HOẶC là admin trong tenant?
           |       |
           |       +-- ALLOW -> request tới controller
           |       +-- DENY  -> AccessDeniedException
           |
           v
ExceptionTranslationFilter / exception handling
           |-- thiếu authentication -> authentication entry point (thường 401)
           |-- đã authenticated nhưng thiếu quyền -> thường 403
~~~

Sơ đồ thể hiện quan hệ logic, không cam kết thứ tự bất biến của mọi filter khi framework được custom. Khi gặp `AuthorizationFilter`, Spring Security có thể cung cấp `Supplier<Authentication>` để truy xuất authentication **khi cần**, thay vì luôn buộc đọc nó từ đầu.

### Các đối tượng khác nhau

| Thành phần | Vai trò trong quyết định |
| --- | --- |
| `Authentication` | Danh tính được xác thực, authorities, trạng thái; kết quả từ provider |
| `HttpServletRequest` | Method/path/headers và các thông tin request có thể chứa dữ liệu từ client |
| `RequestMatcher` | Định nghĩa request nào thuộc rule, có thể trả cả biến URI template |
| `RequestAuthorizationContext` | Đóng gói request và biến matcher cho HTTP authorization manager |
| `AuthorizationManager<T>` | Đưa ra quyết định quyền dựa trên `Authentication` và context của đối tượng được bảo vệ |
| `AuthorizationDecision` / `AuthorizationResult` | Kết quả grant/deny tùy API version |
| `AuthorizationFilter` | Gọi manager tương ứng, cho request tiếp tục hoặc chặn |
| `ExceptionTranslationFilter` | Chuyển exception bảo mật thành 401/302/403 phù hợp authentication entry point và access denied handler |
| `SecurityFilterChain` | Phạm vi các security filters áp dụng cho request, được chọn dựa trên security matcher |

**Quan trọng:** có `ROLE_ADMIN` hoặc đã login không tự động cho phép truy cập tất cả resources. Authorization vẫn phải xét **mối quan hệ giữa principal, resource và tenant** theo policy sản phẩm.

## 2. Từ authorizeHttpRequests đến AuthorizationManager

Các quy tắc đơn giản:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("reports:read")
    .anyRequest().authenticated());
~~~

DSL `authorizeHttpRequests` dựa vào `AuthorizationManager` cho các quyết định. Khi muốn rule tùy chỉnh:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/projects/{projectId}")
        .access(projectReadAuthorizationManager)
    .anyRequest().denyAll());
~~~

Đây là **fragment cấu hình**, với `HttpMethod` và bean `projectReadAuthorizationManager` đã có sẵn; mục 6 sẽ có phiên bản hoàn chỉnh, dùng matcher MVC tường minh để minh họa việc lấy biến `projectId`.

### Vì sao access(manager) thay vì permitAll?

`permitAll()` bỏ kiểm tra authority tại rule đó. Nếu ứng dụng gắn `permitAll()` cho endpoint dự án chỉ để controller tự quyết định quyền, mọi request có thể đi sâu vào code trước khi được kiểm tra đúng, và rất dễ bỏ sót một nhánh. `access(manager)` cho phép ta thực hiện kiểm tra quyền **trước controller** ở URL được chọn.

Tuy nhiên, kiểm tra HTTP **không thay thế hoàn toàn** phân quyền ở tầng dịch vụ trong những ứng dụng có nhiều đường gọi service (scheduled job, messaging, GraphQL, gRPC hay API khác). Phải chọn nơi đặt business authorization đủ gần dữ liệu để tránh bypass.

### Dùng rule dựng sẵn khi có thể

Đừng viết manager chỉ để kiểm tra `authentication.get().isAuthenticated()` hoặc một role cố định nếu DSL đã có `authenticated()`/`hasRole(...)`. Custom manager có thêm chi phí thiết kế, test, vận hành và có thể cần truy xuất dữ liệu. Dùng nó khi quyết định thực sự phụ thuộc nhiều yếu tố hoặc cần tái sử dụng policy.

## 3. Hợp đồng AuthorizationManager<RequestAuthorizationContext>

Với nhiều phiên bản Spring Security 6.x, một implementation HTTP manager có thể theo hình dạng:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Phần cốt lõi của class implements AuthorizationManager<RequestAuthorizationContext>
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        RequestAuthorizationContext context) {

    // Decision phải được tính theo danh tính đã xác thực
    // và tài nguyên/thuộc tính server thực tế.
    boolean granted = false;
    return new AuthorizationDecision(granted);
}
~~~

Đây là **fragment** để giải thích chữ ký, không phải file biên dịch riêng. Class đầy đủ được viết ở mục 6.5. Trên các bản Spring Security 6.x mới hơn, `AuthorizationManager.authorize(...)` trả `AuthorizationResult` và `check(...)` có thể deprecated. Khi cập nhật thư viện, đối chiếu JavaDoc đúng version, điều chỉnh method override và test; không suy luận tất cả 6.x có chữ ký giống hệt nhau.

### Tại sao dùng Supplier<Authentication>?

`Supplier<Authentication>` cho phép framework trì hoãn việc tìm Authentication khi rule không cần nó. Với một số rule dựng sẵn, điều này tránh truy cập SecurityContext không cần thiết. Trong custom manager, gọi `authentication.get()` khi cần xác thực/authority, và coi nội dung nhận được theo hợp đồng SecurityContext.

**Không** dùng `request.getParameter("role")` hoặc một header `X-User-Role` do client tự gửi làm kết quả authentication. Thông tin quyền phải đến từ provider/identity đã được server xác thực. Nếu ứng dụng có identity được gắn bởi reverse proxy đáng tin, việc tin headers cũng cần một cơ chế authentication của hệ thống đó, không phải trực tiếp tin client header.

### Đừng coi isAuthenticated() một mình là đủ

Trong Spring Security, `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` theo semantics của token. Nếu tự code rule đặc thù, cần **phân biệt anonymous với authenticated user thật**, hoặc dùng `AuthenticatedAuthorizationManager.authenticated()` / manager dựng sẵn khi phù hợp.

Ví dụ cho rule tự viết:

~~~java
if (auth == null ||
        !auth.isAuthenticated() ||
        auth instanceof AnonymousAuthenticationToken) {
    return new AuthorizationDecision(false);
}
~~~

Đây là fragment trong method đã có biến `auth`. Với các phương thức authentication khác (remember-me, fully authenticated, MFA), cần quyết định mức bảo đảm danh tính phù hợp. Một quyền nhạy cảm có thể yêu cầu **fully authenticated** chứ không chỉ remembered principal.

### Allow, deny và abstain

Một `AuthorizationDecision(true)` biểu diễn grant; `AuthorizationDecision(false)` là deny. Một số giao diện/manager có thể trả `null` theo hợp đồng tương ứng để biểu diễn không có quyết định, nhất là khi kết hợp nhiều manager. Trong custom rule thuộc endpoint bảo vệ, lựa chọn an toàn là **deny rõ ràng** khi thiếu authentication, biến path, record hoặc policy data, thay vì `null` với hy vọng manager khác sẽ chặn giúp.

**Fail closed** là nguyên tắc: nếu dữ liệu ủy quyền không đủ hoặc không đáng tin, không cấp quyền. Với lỗi hệ thống có thể trả failure thay vì biến mọi lỗi thành “không tồn tại”, nhưng tuyệt đối không `catch (Exception) { return allow; }`.

## 4. RequestAuthorizationContext và biến đường dẫn

Một endpoint điển hình:

~~~text
GET /api/projects/101
GET /api/projects/102
GET /api/projects/201
~~~

Rule được khai báo với URL template:

~~~java
"/api/projects/{projectId}"
~~~

Khi `RequestMatcher` hỗ trợ trích biến, `RequestAuthorizationContext.getVariables()` có thể trả map như:

~~~text
{projectId=101}
~~~

Đây là **kết quả minh họa** cho request `/api/projects/101`, không phải dữ liệu từ HTTP header client gửi. Giá trị `101` vẫn là **đầu vào không đáng tin cậy**: phải parse/validate, rồi dùng nó làm khóa tìm record trong dữ liệu phía server. Không cho phép client tự xác nhận “dự án này thuộc về tôi”.

### Vì sao cần matcher tường minh?

Trong Spring Security Servlet với Spring MVC, `MvcRequestMatcher` có thể sử dụng `HandlerMappingIntrospector` để khớp đường dẫn theo cách của MVC, bao gồm URI template variables. Một số hệ thống dùng `AntPathRequestMatcher`, `PathPatternRequestMatcher` hoặc matcher tự xây; **không phải matcher nào cũng trả variables đúng tên**. Không nên viết code phụ thuộc `context.getVariables().get("projectId")` rồi dùng matcher không có biến.

Ví dụ trong cấu hình Spring MVC:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(handlerMappingIntrospector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        mvc.pattern(HttpMethod.GET, "/api/projects/{projectId}"))
        .access(projectReadAuthorizationManager)
    .anyRequest().denyAll());
~~~

`handlerMappingIntrospector` là bean `HandlerMappingIntrospector` được Spring MVC tạo, dùng ở đúng web application context. Cấu hình Spring Security 6.5+ còn có các matcher API mới; cần xem phiên bản và servlet mapping của ứng dụng. Nếu `DispatcherServlet` có servlet path riêng, phải cấu hình matcher phù hợp để không khớp lệch route.

### Không nên parse số tùy tiện

Input `projectId` có thể vắng mặt, rỗng, sai định dạng, âm, quá lớn đối với `long`, hoặc bị encode bất thường. Quy tắc an toàn:

1. Kiểm tra có biến đúng tên không.
2. Kiểm tra định dạng với độ dài hợp lý.
3. Parse trong `try/catch(NumberFormatException)`.
4. Kiểm tra resource tồn tại và thuộc tenant từ server data.
5. Deny nếu không có đủ dữ kiện; không fallback sang một ID mặc định.

**Không** parse ID từ một query parameter khác nếu route đã được matcher coi là không có ID. Fallback mơ hồ làm xuất hiện những con đường vào tài nguyên khác với policy đã được review.

## 5. Bài toán mẫu: owner + tenant + admin trong tenant

Ta xây quy tắc đọc dự án:

- Alice thuộc tenant `north` và sở hữu dự án 101.
- Bob thuộc tenant `north` và sở hữu dự án 102.
- Carol thuộc tenant `south` và sở hữu dự án 201.
- Admin thuộc tenant `north`, có `ROLE_ADMIN`.
- User thường chỉ xem được dự án **của mình** trong tenant mình.
- Admin có thể xem mọi dự án **của tenant mình**, không được vượt tenant.
- Dự án không tồn tại và dữ liệu policy không đầy đủ **không được cho qua**.
- User/tenant/role do server xác thực hoặc nạp từ store đáng tin, **không** lấy từ `X-Tenant`/`role` trong request.

### Bảng quyết định

| User | Tenant của user | Resource | Tenant / owner của resource | Kỳ vọng |
| --- | --- | --- | --- | --- |
| alice | north | 101 | north / alice | **Allow** |
| alice | north | 102 | north / bob | **Deny** |
| bob | north | 102 | north / bob | **Allow** |
| admin (ROLE_ADMIN) | north | 101 | north / alice | **Allow** |
| admin (ROLE_ADMIN) | north | 201 | south / carol | **Deny** |
| carol | south | 201 | south / carol | **Allow** |
| alice | north | 999 | Không tồn tại | **Deny** |
| Anonymous | không xác định | 101 | north / alice | **Deny** |

Quy tắc Boolean trung tâm:

~~~text
ALLOW = authenticatedRealUser
        AND projectExists
        AND trustedUserTenant == projectTenant
        AND (trustedUsername == projectOwner OR has ROLE_ADMIN)
~~~

Các dấu `AND/OR` thể hiện điều kiện logic. **Đặt điều kiện tenant bao ngoài nhánh admin** là rất quan trọng: nếu viết sai thành `(sameTenant AND owner) OR admin`, admin có thể đọc mọi tenant — một lỗ hổng phổ biến khi phối hợp nhiều điều kiện.

### Vì sao chọn GET /api/projects/{projectId}?

Đây là request cần kiểm soát truy cập trước controller, có URI variable rõ ràng. Các method POST/PUT/DELETE có thể cần policy khác; **không tự suy ra quyền GET là quyền sửa hoặc xóa**. Trong ví dụ, chỉ GET match rule custom; những request khác `denyAll()`.

## 6. Triển khai Spring Boot 3 + Security 6

Đây là một ví dụ **ứng dụng minh họa đầy đủ về cấu trúc**, sử dụng authentication HTTP Basic để test dễ và dữ liệu dự án in-memory bất biến để tập trung vào AuthorizationManager. Nó không nhằm thiết kế hệ thống production lưu user hoặc project. Tất cả file thuộc package `com.example.authz`.

### 6.1. Maven dependencies

Với một project Spring Boot 3.x đã có parent/BOM và build plugin tương thích, `pom.xml` cần:

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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các dependency này dùng phiên bản qua BOM Spring Boot. Không tự trộn các bản Spring Security khác. Java 17 hoặc mới hơn phải là toolchain phù hợp. API `MvcRequestMatcher`, `AuthorizationManager.check(...)` và test imports dưới đây viết cho họ Spring Security 6.x; kiểm tra thay đổi/deprecation với minor version thực tế.

### 6.2. Lớp khởi động

Tạo `src/main/java/com/example/authz/AuthorizationDemoApplication.java`:

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

### 6.3. Data/policy service đáng tin cậy

Tạo `src/main/java/com/example/authz/ProjectAccessService.java`:

~~~java
package com.example.authz;

import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;

public final class ProjectAccessService {

    public record Project(long id, String tenant, String owner) {}

    // Dữ liệu BẤT BIẾN để demo; thực tế tải từ DB có phân vùng tenant.
    private final Map<Long, Project> projects = Map.of(
        101L, new Project(101L, "north", "alice"),
        102L, new Project(102L, "north", "bob"),
        201L, new Project(201L, "south", "carol")
    );

    // Trong production, tenant đến từ principal đã xác thực
    // và kho identity/tenancy đáng tin, không từ header bất kỳ.
    private final Map<String, String> userTenants = Map.of(
        "alice", "north",
        "bob", "north",
        "carol", "south",
        "admin", "north"
    );

    public Project find(long id) {
        return projects.get(id);
    }

    public boolean mayRead(Authentication authentication, long id) {
        if (authentication == null ||
                !authentication.isAuthenticated() ||
                authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        Project project = projects.get(id);
        if (project == null) {
            return false; // Không cho qua tài nguyên không tồn tại.
        }

        String trustedTenant = userTenants.get(authentication.getName());
        if (trustedTenant == null ||
                !trustedTenant.equals(project.tenant())) {
            return false; // Admin cũng không vượt tenant.
        }

        boolean isOwner = project.owner().equals(authentication.getName());
        boolean isAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return isOwner || isAdmin;
    }
}
~~~

Tại sao đặt logic trong service thay vì viết tất cả ở manager? Vì cùng business policy có thể cần kiểm thử riêng, tái sử dụng ở các điểm gọi khác và dễ thay nguồn dữ liệu về database. Nhưng **quyền ở tầng service cũng phải được áp dụng cho mọi code path cần bảo vệ**, không chỉ tồn tại như helper mà không được gọi.

Chú ý: `userTenants` trong ví dụ là map server-side để minh họa quan hệ. Trong production, tenant thường có trong principal đã được xác thực, membership store hoặc hệ thống identity; cần xử lý username trùng giữa tenant bằng khóa định danh bất biến/multi-tenant ID, không dùng `getName()` làm primary key nếu nó không duy nhất toàn hệ thống.

### 6.4. Quy tắc HTTP riêng: ProjectReadAuthorizationManager

Tạo `src/main/java/com/example/authz/ProjectReadAuthorizationManager.java`:

~~~java
package com.example.authz;

import java.util.Map;
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ProjectReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ProjectAccessService projects;

    public ProjectReadAuthorizationManager(ProjectAccessService projects) {
        this.projects = projects;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        // Matchers không cung cấp URI variable -> fail closed.
        Map<String, String> variables = context.getVariables();
        String rawId = variables == null ? null :
                variables.get("projectId");

        // Chỉ chấp nhận số dương dạng thập phân, độ dài giới hạn.
        if (rawId == null ||
                !rawId.matches("[1-9][0-9]{0,17}")) {
            return new AuthorizationDecision(false);
        }

        final long id;
        try {
            id = Long.parseLong(rawId);
        } catch (NumberFormatException exception) {
            return new AuthorizationDecision(false);
        }

        Authentication user = authentication.get();
        boolean allow = projects.mayRead(user, id);
        return new AuthorizationDecision(allow);
    }
}
~~~

Các điểm phải hiểu:

1. `RequestAuthorizationContext.getVariables()` phụ thuộc matcher. Nếu không tìm thấy `projectId` thì deny, **không** cho phép tất cả.
2. Định dạng `[1-9][0-9]{0,17}` chỉ minh họa ID số dương không có zero ở đầu, dài tối đa 18 chữ số. Với UUID, điều chỉnh parser/validation. Đừng dùng regex làm biện pháp authorization duy nhất.
3. `authentication.get()` lấy Authentication theo Spring Security context; manager không tự gọi login hay PasswordEncoder.
4. `ProjectAccessService.mayRead(...)` nhìn vào record và tenant **phía server**.
5. `AuthorizationDecision(false)` khiến `AuthorizationFilter` chặn trước khi controller chạy. Nó không gửi `response.sendError(403)` trực tiếp từ manager; exception translation và entry point quyết định response HTTP.
6. Manager là một object có thể dùng đồng thời giữa requests. Nó không ghi “currentUser/currentProject” vào field của singleton, tránh rò dữ liệu giữa threads.
7. Nếu database lỗi, cần chính sách **fail closed**. Đừng bắt mọi exception để trả `true`. Đối với lỗi kho dữ liệu, có thể chọn phản hồi lỗi dịch vụ phù hợp qua error handling, nhưng **không** tự cho qua.

Đây là class phù hợp kiểu API `check(...)` thường gặp ở Spring Security 6.x. Nếu bản thư viện mới có `authorize(Supplier<? extends Authentication>, T)` và thông báo deprecation, cập nhật theo chữ ký được JavaDoc hỗ trợ rồi chạy test; không đổi bản chất điều kiện.

### 6.5. SecurityFilterChain và HTTP matcher

Tạo `src/main/java/com/example/authz/SecurityConfig.java`:

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-demo-only"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-demo-only"))
                .roles("USER").build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-demo-only"))
                .roles("USER").build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .roles("ADMIN").build()
        );
    }

    @Bean
    ProjectAccessService projectAccessService() {
        return new ProjectAccessService();
    }

    @Bean
    ProjectReadAuthorizationManager projectReadAuthorizationManager(
            ProjectAccessService projects) {
        return new ProjectReadAuthorizationManager(projects);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector,
            ProjectReadAuthorizationManager projectRead) throws Exception {

        // Matcher MVC trả được biến {projectId} cho request khớp.
        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern(
                    HttpMethod.GET, "/api/projects/{projectId}"))
                    .access(projectRead)
                // Không mở thêm URL ngoài yêu cầu minh họa.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // GET chỉ đọc không cần CSRF token.
        // Không tắt CSRF toàn cục: POST/PUT/DELETE vẫn cần policy riêng.
        return http.build();
    }
}
~~~

Trong ví dụ:

- HTTP Basic được sử dụng **chỉ để test**, không phải lời khuyên dùng Basic auth với credentials dài hạn cho mọi SPA. Production cần HTTPS, giới hạn login, MFA/identity architecture phù hợp và không lưu credential ở client không an toàn.
- Chỉ `GET /api/projects/{projectId}` tới custom manager. `GET /api/projects` hoặc `DELETE /api/projects/101` không tự được phép.
- `anyRequest().denyAll()` bảo đảm đường dẫn chưa khai báo không bị cấp quyền nhầm.
- Cấu hình giữ CSRF mặc định. GET không phải thao tác thay đổi trạng thái; nếu controller GET thực hiện side effect thì chính thiết kế HTTP đã có vấn đề.
- `MvcRequestMatcher.Builder` dùng MVC infrastructure; nếu dự án không có Spring MVC, dùng matcher tương thích Servlet stack và xác minh hỗ trợ path variables.
- Trong app dùng DispatcherServlet dưới servlet path khác, cần xử lý servlet path/lookup path rõ ràng, không ghép chuỗi URL theo cảm tính.

**Không có `permitAll("/api/projects/**")`** ở trước custom rule. Nếu một matcher rộng hơn được đặt trước và khớp request, rule chi tiết có thể không được dùng vì quá trình chọn match thường ưu tiên quy tắc khớp đầu tiên trong danh sách.

### 6.6. Controller không cấp quyền bổ sung

Tạo `src/main/java/com/example/authz/ProjectController.java`:

~~~java
package com.example.authz;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProjectController {
    private final ProjectAccessService projects;

    public ProjectController(ProjectAccessService projects) {
        this.projects = projects;
    }

    @GetMapping("/api/projects/{projectId}")
    public Map<String, Object> getProject(@PathVariable long projectId) {
        ProjectAccessService.Project p = projects.find(projectId);
        if (p == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Project not found");
        }

        return Map.of(
            "id", p.id(),
            "tenant", p.tenant(),
            "owner", p.owner());
    }
}
~~~

Nếu request GET tới dự án 101 của Alice thì manager allow, controller trả record từ bộ nhớ. Nếu Alice cố đọc dự án 102 của Bob thì manager deny **trước khi controller chạy**. Với dữ liệu in-memory bất biến, service và controller thấy cùng record.

**Giới hạn quan trọng:** trong database production, record có thể đổi chủ sở hữu/tenant **giữa** lần kiểm tra ở manager và lần controller tải dữ liệu. Đây là vấn đề time-of-check/time-of-use (TOCTOU). Không coi code trên là ví dụ đầy đủ về consistency của hệ thống đa người cập nhật. Với dữ liệu mutable, cân nhắc kiểm tra quyền tại cùng query/transaction đọc dữ liệu hoặc service authorization có transaction và isolation phù hợp.

### 6.7. Chạy demo và quan sát kết quả

Với Spring Boot project đã được tạo đúng version, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Sử dụng máy local thử nghiệm; có thể dùng curl HTTP Basic với prompt password thay vì ghi password trong shell history:

~~~bash
# curl hỏi nhập password; chỉ dùng tài khoản demo.
curl -i -u alice http://localhost:8080/api/projects/101
curl -i -u alice http://localhost:8080/api/projects/102
curl -i -u admin http://localhost:8080/api/projects/201
~~~

Kỳ vọng nếu nhập đúng password tương ứng:

- Alice → project 101: HTTP **200**, JSON chứa `id=101`, `tenant=north`, `owner=alice`.
- Alice → project 102: HTTP **403** vì cùng tenant nhưng không phải owner và không có ROLE_ADMIN.
- Admin (north) → project 201 (south): HTTP **403** dù có ROLE_ADMIN, do tenant boundary chặn.
- Một request không có credentials tới project 101 thường nhận **401** với HTTP Basic challenge, thay vì tự suy ra user là Alice.
- GET project 999 đã xác thực nhưng không tồn tại: rule demo trả deny, thường 403; sản phẩm thật có thể chọn 404 để ẩn existence, nhưng không nên đoán response từ controller vì controller có thể không được chạy.

Chú ý: trong production, Basic credentials luôn phải được truyền qua **HTTPS**, không gửi password qua mạng HTTP thường. Các lệnh localhost chỉ là demo môi trường tin cậy.

## 7. Kiểm thử bằng MockMvc và Spring Security Test

Một bài test authorization không nên chỉ unit test method `mayRead(...)`. Cần bảo đảm rule được gắn vào **đúng SecurityFilterChain, đúng method, đúng URL variable** và dẫn tới 200/403/401 chính xác. Với `spring-security-test` có thể gửi HTTP Basic thật qua `MockMvc`.

Tạo `src/test/java/com/example/authz/ProjectAuthorizationIntegrationTest.java`:

~~~java
package com.example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProjectAuthorizationIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void ownerCanReadOwnProject() throws Exception {
        mvc.perform(get("/api/projects/101")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void sameTenantButNotOwnerIsDenied() throws Exception {
        mvc.perform(get("/api/projects/102")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadWithinOwnTenantOnly() throws Exception {
        mvc.perform(get("/api/projects/102")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/projects/201")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void southTenantOwnerCanReadSouthProject() throws Exception {
        mvc.perform(get("/api/projects/201")
                .with(httpBasic("carol", "carol-demo-only")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/projects/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownProjectNeverGetsAllowed() throws Exception {
        mvc.perform(get("/api/projects/999")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void malformedIdNeverGetsAllowed() throws Exception {
        mvc.perform(get("/api/projects/not-a-number")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unmatchedUrlIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Các assertions kỳ vọng với đúng cấu hình, version matcher và test classpath ở mục 6. Một số hệ thống có custom entry point, API error handler hoặc container mapping có thể trả status khác; khi đó kiểm tra luồng thực tế thay vì coi status cố định là hợp đồng chung.

**Chú ý:** test `malformedIdNeverGetsAllowed` phụ thuộc `MvcRequestMatcher` có match một path segment chứa chuỗi và đưa biến vào context trước khi MVC bind `@PathVariable long`. Nếu manager fail closed, nó deny ngay trước controller. Nếu custom matcher không match, `anyRequest().denyAll()` cũng deny; cả hai đều ngăn request, nhưng test riêng manager sẽ giúp xác nhận branch nào xảy ra.

### Test quan trọng hơn: xác minh manager thực sự chạy

Một status 403 có thể đến từ `anyRequest().denyAll()` hoặc từ CSRF/exception khác, **không tự chứng minh** rule custom đã nhận biến `projectId`. Để test wiring chặt hơn:

- Trực tiếp unit test `ProjectReadAuthorizationManager.check(...)` với `RequestAuthorizationContext(request, Map.of("projectId","101"))` và Authentication hợp lệ.
- Trong integration test, trường hợp Alice **được allow** tới 101 có ý nghĩa vì nếu matcher/manager không chạy, `denyAll()` sẽ từ chối.
- Test path biến 101, 102, 201 và method/route khác.
- Kiểm tra một request authenticated nhưng thiếu quyền nhận 403, một request không authenticated đi tới authentication entry point.
- Nếu dùng `@WithMockUser` để test authorization, chú ý annotation **không kiểm thử HTTP Basic/PasswordEncoder**. Với test policy chỉ cần authenticated principal giả thì phù hợp; để test luồng thực, dùng httpBasic/formLogin credential như ví dụ.

### Unit test cho manager

Một fragment độc lập với server có thể tạo context:

~~~java
// Fragment trong JUnit test đã có ProjectReadAuthorizationManager manager.
MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/projects/101");
RequestAuthorizationContext context =
        new RequestAuthorizationContext(
            request, java.util.Map.of("projectId", "101"));

Authentication user = new UsernamePasswordAuthenticationToken(
    "alice", "ignored", java.util.List.of(
        new SimpleGrantedAuthority("ROLE_USER")));

AuthorizationDecision decision = manager.check(() -> user, context);
assertTrue(decision != null && decision.isGranted());
~~~

Các import Spring Test, Spring Security và JUnit phải được bổ sung; đây là fragment, không phải file test hoàn chỉnh. `UsernamePasswordAuthenticationToken` 3-argument trong ví dụ unit test biểu diễn Authentication **đã được xác thực giả lập** cho việc test riêng rule, không phải token được tạo từ request thực trong production. Không sao chép cách tạo trusted token này vào HTTP converter.

## 8. HTTP rule ordering: chi tiết trước, rộng sau

Một lỗi cấu hình nghiêm trọng:

~~~java
// SAI: matcher chung có thể khớp trước matcher chi tiết.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/projects/{projectId}").access(projectRead)
    .anyRequest().denyAll());
~~~

Khi `/api/**` khớp trước, request dự án có thể không đi tới manager tùy cơ chế chọn rule đầu tiên. Việc đặt một matcher hẹp phía sau **không khắc phục** rule rộng đã allow trước.

Cách tổ chức:

~~~java
// Rule chi tiết trước, fallback deny.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/projects/{projectId}")
        .access(projectRead)
    .anyRequest().denyAll());
~~~

Các đoạn trên là fragments, không phải thứ tự áp dụng cho mọi loại security matcher. Spring Security còn có tầng **chọn SecurityFilterChain** độc lập:

~~~text
FilterChainProxy
  |-- chain #1 securityMatcher("/api/**")  -> API filters/rules
  |-- chain #2 securityMatcher("/**")      -> Web filters/rules
  |
  +-- Request chỉ được xử lý bởi SecurityFilterChain khớp đầu tiên
~~~

Nếu request vào chain #1, các rule authorizeHttpRequests trong chain #2 sẽ **không chạy**. Do đó quản lý hai cấp matcher riêng:

1. **securityMatcher** / `@Order` chọn chain.
2. **requestMatchers** trong `authorizeHttpRequests` chọn rule thuộc chain đó.

Kiểm tra danh sách filter chain và nguyên tắc fallback toàn ứng dụng. Đừng nhầm `securityMatcher("/api/**")` với việc mặc định bảo vệ mọi endpoint ngoài API: nếu không có chain nào khớp, request có thể không được Spring Security bảo vệ như bạn tưởng.

### HTTP method và dispatcher type

- Quyền **GET** không tự cho phép **POST/PUT/PATCH/DELETE**.
- CSRF là cơ chế phòng chống cross-site request trong các kiến trúc cần CSRF; nó **khác authorization**. Request POST có token CSRF đúng vẫn có thể bị deny quyền nghiệp vụ.
- Servlet request có thể có dispatcher types như `REQUEST`, `FORWARD` và `ERROR`. Nếu ứng dụng gặp lỗi 403 trên error dispatch, kiểm tra cấu hình dispatcher và policy, không bật permitAll bừa bãi cho mọi đường nội bộ.
- Một controller có thể được map nhiều URL hoặc alias. Policy phải bao phủ **tất cả routes** dẫn tới thao tác bảo vệ.

## 9. 401, 403 và 404: lựa chọn phản hồi có ý nghĩa

Với policy GET project:

| Kịch bản | Quyết định chính | HTTP thường gặp |
| --- | --- | --- |
| Không có credentials với endpoint bảo vệ | Chưa authenticated | 401 HTTP Basic; form login có thể redirect 302 |
| Password Basic sai | Authentication thất bại | 401 theo entry point |
| Alice authenticated đọc project Bob | Authorization deny | 403 |
| Admin north đọc project south | Authorization deny do tenant | 403 |
| Project 999 không tồn tại | Rule demo deny trước controller | 403 trong ví dụ, không tự thành 404 |
| Controller tìm thấy entity rồi không cho phép theo policy khác | Phụ thuộc nơi enforcement | 403/404 theo hợp đồng app |
| Request vi phạm CSRF trước authorization | Bị CSRF filter chặn | 403, không chứng minh custom manager đã chạy |

Một số sản phẩm cố ý trả 404 thay vì 403 cho resource ngoài phạm vi nhằm tránh tiết lộ sự tồn tại. Không nên đơn giản ném `ResponseStatusException(404)` trong custom manager rồi tin rằng ExceptionTranslationFilter xử lý giống authorization failure. Hãy định nghĩa contract và nơi chuyển đổi lỗi rõ ràng, test ẩn existence ở cả controller/service và các API routes khác.

**Deny đúng không đồng nghĩa UX tốt.** Một manager có thể trả false khi service dữ liệu tạm lỗi; người dùng thấy 403 gây hiểu nhầm “không có quyền”. Trong production, cần phân biệt lỗi hệ thống với quyết định policy, nhưng **không fail open** để tránh mất availability.

### Role prefix và authorities

Với Spring Security, `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`. Trong service ví dụ, ta so sánh chuỗi `"ROLE_ADMIN"` từ `getAuthorities()`. Nếu dự án có role prefix riêng, user mapper riêng hoặc OAuth scopes như `SCOPE_project.read`, không thể tự suy ra chuỗi cố định. Khẳng định danh tính dựa trên Authentication do provider xác thực, sau đó áp chính sách server.

## 10. Ranh giới tin cậy: đừng lấy quyền từ input client

Một lỗi điển hình:

~~~java
// KHÔNG BAO GIỜ: Client có thể tự sửa headers và khai báo quyền.
boolean allow = "ADMIN".equals(
    context.getRequest().getHeader("X-Role"));
return new AuthorizationDecision(allow);
~~~

Vấn đề không nằm ở `RequestAuthorizationContext` mà ở nguồn dữ liệu. HTTP headers, query parameters, JSON body, path variable và cookies đều có thể do client gửi. Chúng có thể **chỉ định resource muốn xem**, nhưng không thể là nguồn tin cậy để xác nhận user sở hữu resource đó hoặc thuộc tenant đó.

### Đúng: dùng thông tin server đã xác thực

Một manager có thể đọc:

- `authentication.get().getName()` hoặc principal ID bất biến được provider xác thực.
- `authentication.get().getAuthorities()` từ identity source tin cậy.
- Tenant membership đã xác nhận từ principal/DB server-side.
- Owner/ACL/organization của resource được tải từ database.
- Policy thời gian, trạng thái tài khoản hoặc điều kiện nghiệp vụ server biết (nếu đáng tin và được thiết kế rõ).

### Tenant boundary phải đặt bên ngoài quyền admin

Biểu thức nguy hiểm:

~~~text
(sameTenant AND isOwner) OR isAdmin
~~~

Nó cho admin bất kỳ vượt qua kiểm tra tenant. Với ví dụ, quy tắc đúng:

~~~text
sameTenant AND (isOwner OR isAdmin)
~~~

Nếu một resource có nhiều owner, group membership hoặc shared access, mở rộng mệnh đề quyền bằng dữ liệu server-side; không sửa tenant boundary theo sự tiện lợi của một màn hình UI.

### Bảo vệ khỏi IDOR/BOLA

**Insecure Direct Object Reference** / **Broken Object Level Authorization** xuất hiện khi API nhận ID của object rồi trả dữ liệu mà không kiểm tra đối tượng thuộc phạm vi user. Chỉ yêu cầu `authenticated()` tại `GET /api/projects/{id}` là **chưa đủ** cho object-level authorization. `AuthorizationManager` có thể là nơi thực thi kiểm tra trước controller, song service cũng cần bảo vệ nếu được gọi từ nơi khác.

## 11. Performance, database access và consistency

### 11.1. Manager nên nhỏ, không chứa mutable per-request state

Bean AuthorizationManager thường được tạo một lần và dùng cho nhiều request đồng thời. Không đặt:

~~~java
// KHÔNG NÊN: shared mutable fields mang dữ liệu request.
private String currentUser;
private Long currentProjectId;
~~~

Nếu handler dùng field rồi nhiều thread cùng ghi/đọc, có thể rò dữ liệu quyền và ra quyết định sai. Dùng **local variables** trong `check(...)`, service stateless và repository thread-safe.

### 11.2. Tải resource bao nhiêu lần?

Trong ví dụ, manager tải record để authorize, controller tải lại record để trả response. Với map bất biến thì không đáng kể; với database thì tăng truy vấn và tạo cửa sổ TOCTOU. Một số cách thiết kế:

- Service method tải object theo điều kiện tenant/owner trong cùng query, ví dụ `WHERE id = ? AND tenant_id = ? AND owner_id = ?`, sau đó chỉ trả dữ liệu khi tìm thấy. Admin có query riêng vẫn phải ràng buộc tenant.
- Kiểm tra quyền trong một service application theo transaction/isolation thích hợp, không chỉ ở tầng filter.
- Khi manager tải metadata, dùng projection chỉ chứa field cần cho quyền, tránh N+1 query.
- Có thể cache policy/resource metadata nếu quyền thay đổi hiếm và cache invalidation được thiết kế; không để cache trả quyền stale nguy hiểm.
- Với external PDP (policy decision point), cần timeout/circuit breaker và **fail closed** khi không thể xác định quyền.

**Đừng chuyển nguyên entity chứa trường nhạy cảm vào request attribute** chỉ để controller tái sử dụng nếu điều đó có thể lộ qua logs/tracing/filter. Nếu cần reuse, dùng object scoping rõ và xem xét transaction boundaries.

### 11.3. Data consistency và thay đổi quyền đồng thời

Kịch bản:

1. Alice GET /api/projects/101, manager xác định Alice là owner.
2. Admin đổi owner của 101 sang Bob.
3. Controller tải 101 và trả dữ liệu dù Alice không còn owner.

Đây là TOCTOU. Với bản ghi mutable và yêu cầu bảo mật chặt, nên đặt check và data access trong cùng phạm vi kiểm soát consistency, hoặc dùng query chỉ trả record hợp quyền ở thời điểm đọc, policy version/optimistic locking hay transaction thích hợp. Chỉ kiểm tra ở filter không tự giải quyết vấn đề.

### 11.4. Remote authorization latency

Nếu mỗi GET gọi một external policy service, độ trễ và availability của endpoint phụ thuộc service đó. Cần cân nhắc caching có giới hạn, tracing không lộ PII, timeout, retries có kiểm soát, circuit breaker và fallback **deny** hoặc service unavailable theo contract. Không trả allow để “không làm gián đoạn UX” khi không kiểm tra được quyền.

## 12. Java 17 độc lập: mô hình policy chủ sở hữu + tenant

Trước khi làm việc với Spring Security, ta có thể tự kiểm chứng **logic nghiệp vụ** bằng một chương trình JDK 17 chỉ sử dụng record và map. Nó **không** xác thực password, không tạo SecurityContext, không đọc Servlet request, và không thể thay thế filter của framework. Nó chỉ mô phỏng Boolean policy.

Lưu file `ProjectAccessPolicyDemo.java`:

~~~java
import java.util.Map;

public class ProjectAccessPolicyDemo {
    record User(String name, String tenant, boolean admin) {}
    record Project(long id, String tenant, String owner) {}

    static boolean canRead(User user, Project project) {
        if (user == null || project == null) {
            return false;
        }
        if (!user.tenant().equals(project.tenant())) {
            return false;
        }
        return user.admin() || user.name().equals(project.owner());
    }

    static String decision(User user, long projectId,
                           Map<Long, Project> projects) {
        return canRead(user, projects.get(projectId)) ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Map<Long, Project> projects = Map.of(
            101L, new Project(101L, "north", "alice"),
            102L, new Project(102L, "north", "bob"),
            201L, new Project(201L, "south", "carol")
        );

        User alice = new User("alice", "north", false);
        User admin = new User("admin", "north", true);
        User carol = new User("carol", "south", false);

        System.out.println("alice 101 -> " +
            decision(alice, 101L, projects));
        System.out.println("alice 102 -> " +
            decision(alice, 102L, projects));
        System.out.println("admin 102 -> " +
            decision(admin, 102L, projects));
        System.out.println("admin 201 -> " +
            decision(admin, 201L, projects));
        System.out.println("carol 201 -> " +
            decision(carol, 201L, projects));
        System.out.println("alice 999 -> " +
            decision(alice, 999L, projects));
    }
}
~~~

Chạy bằng **JDK 17+** từ thư mục chứa file:

~~~bash
javac ProjectAccessPolicyDemo.java
java ProjectAccessPolicyDemo
~~~

Stdout **chính xác**:

~~~text
alice 101 -> ALLOW
alice 102 -> DENY
admin 102 -> ALLOW
admin 201 -> DENY
carol 201 -> ALLOW
alice 999 -> DENY
~~~

Điều chương trình chứng minh:

- Alice không xem được project 102 dù cùng tenant vì không phải owner.
- Admin xem được project 102 trong tenant north.
- Admin không vượt sang tenant south.
- Carol được xem dữ liệu chính mình sở hữu.
- Project không tồn tại dẫn tới deny.
- Không có dòng code nào “cấp quyền” dựa trên project ID do client tự khai báo.

**Giới hạn:** chương trình chỉ là test policy thuần Java; trong hệ thống thực, đối tượng `User` phải đến từ provider identity đáng tin, `Project` từ dữ liệu server và HTTP rule phải được gắn đúng route/chain. Không dùng `new User("admin",...,true)` từ JSON request rồi cho phép truy cập.

## 13. AuthorizationManager HTTP so với method security

HTTP authorization phù hợp khi:

- Quy tắc phụ thuộc method/path của HTTP.
- Cần chặn trước controller.
- URL template đã chỉ định tài nguyên và metadata đủ để check.
- Tập trung các quy tắc truy cập mạng vào `SecurityFilterChain`.

Method security phù hợp khi:

- Service được gọi từ nhiều con đường, không chỉ HTTP.
- Cần kiểm tra đối tượng domain sau khi đã tải.
- Chính sách đọc/ghi phụ thuộc tham số nghiệp vụ mà URL không biểu diễn đầy đủ.
- Muốn đảm bảo mọi caller của service phải tuân thủ cùng policy.

Spring Security có thể bật method security qua `@EnableMethodSecurity` và các annotation như `@PreAuthorize`. Một fragment ý tưởng:

~~~java
// Ví dụ khái niệm: cần bean projectPolicy, tên tham số và method security.
@PreAuthorize("@projectPolicy.mayRead(authentication, #projectId)")
public Project findForUser(long projectId) {
    // Service phải bảo đảm consistency với dữ liệu trả về.
    return repository.findById(projectId)
        .orElseThrow();
}
~~~

Đây **không** phải class runnable: `projectPolicy`, `repository`, import, bean wiring và method-security configuration phải do dự án cung cấp. Ký hiệu `#projectId` cần có parameter name metadata hoặc khai báo tên tham số theo cơ chế framework. Việc bật `@PreAuthorize` cũng phụ thuộc proxy interception; self-invocation không nhất thiết đi qua proxy.

Hai lớp security **có thể bổ sung cho nhau**. Không vì đã có manager ở HTTP mà bỏ kiểm tra ở service nếu service có các đường gọi khác; và không vì có method security mà để toàn bộ API HTTP rơi vào `permitAll()`.

### So sánh với AuthorizationManager<MethodInvocation>

`AuthorizationManager` là generic; `RequestAuthorizationContext` chỉ là kiểu context **của HTTP request**. Spring Security cũng có authorization managers cho method invocation và method return object. Không thể tùy tiện truyền một `AuthorizationManager<RequestAuthorizationContext>` vào nơi cần `AuthorizationManager<MethodInvocation>` nếu không có adapter thích hợp.

### Chọn một nguồn business policy thống nhất

Một cách tổ chức dễ duy trì:

~~~text
ProjectPolicyService (business authorization)
       |
       +-- HTTP ProjectReadAuthorizationManager -> chặn endpoint
       |
       +-- Method security adapter / service-level check
       |
       +-- Unit tests của chính policy
~~~

Với hệ thống lớn, tránh copy cùng biểu thức tenant/owner ở nhiều class rồi để chúng lệch nhau. Chính sách nên có một nơi định nghĩa dữ liệu/quy tắc đáng tin, các adapter chỉ chuyển context và hiển thị failure theo giao thức.

## 14. Kết hợp quy tắc: allOf, anyOf và abstain

Spring Security có những authorization manager dựng sẵn cho role, authenticated status và khả năng kết hợp nhiều điều kiện; API cụ thể phụ thuộc version. Ý nghĩa logic:

~~~text
Tất cả điều kiện bắt buộc: allOf(A, B, C)
Chỉ cần một điều kiện:     anyOf(A, B, C)
~~~

Không nhầm `allOf` với `anyOf` trong bối cảnh multi-tenant. Ví dụ:

~~~text
ALLOWED = sameTenant AND (owner OR tenantAdmin)
~~~

Không được biến thành:

~~~text
ALLOWED = (sameTenant AND owner) OR globalAdmin
~~~

trừ khi sản phẩm thật sự có vai trò **global admin** và đã phân biệt rõ scope. Nếu dự án dùng `AuthorizationManagers.allOf(...)`/`anyOf(...)`, kiểm tra type generic và semantics khi manager trả null/abstain ở version cụ thể. Trong policy nhạy cảm, nên trả quyết định rõ ràng và test từng kết hợp, tránh để nhánh null dẫn tới cấp quyền ngoài dự kiến.

Một rule có thể được viết bằng lambda ngắn cho điều kiện đơn giản:

~~~java
// Fragment: chỉ thích hợp nếu bạn thực sự không cần service/logic lớn.
.access((authentication, context) -> {
    boolean allow = authentication.get().getAuthorities().stream()
        .anyMatch(a -> "project:read".equals(a.getAuthority()));
    return new AuthorizationDecision(allow);
})
~~~

Đoạn này phụ thuộc generic manager API tương ứng và nằm trong builder `requestMatchers(...).access(...)`. Nó kiểm tra một authority global; **không** xử lý ownership/tenant như ví dụ chính. Nếu rule phức tạp, đặt logic vào class/service riêng để test thay vì lambda dài hàng trăm dòng.

## 15. Những lỗi phổ biến khi viết HTTP AuthorizationManager

| Lỗi | Vì sao nguy hiểm hoặc sai | Cách xử lý |
| --- | --- | --- |
| Manager tạo Authentication mới từ request | Client có thể giả danh, bỏ qua provider | Dùng `Supplier<Authentication>` do framework cung cấp |
| Tin `role=ADMIN` hoặc `X-Tenant` từ client | Tự cấp quyền qua input không tin cậy | Dùng principal và store phía server |
| Dùng `isAuthenticated()` nhưng quên anonymous token | Có thể nhận anonymous là authenticated về mặt object | Dùng rule dựng sẵn hoặc phân biệt token phù hợp |
| Trả `true` khi DB gặp lỗi | Fail-open, lộ dữ liệu | Fail closed/service unavailable theo policy |
| Trả `null` vì không tìm thấy project | Có thể gây semantics abstain không như mong muốn | Deny rõ ràng khi dữ liệu thiếu |
| Matcher không cung cấp `projectId`, manager mặc định allow | Bypass điều kiện object-level | Kiểm tra `getVariables()`, thiếu thì deny |
| Đặt `permitAll("/api/**")` trước custom access | Rule chi tiết có thể không chạy | Rule hẹp trước, fallback `denyAll()` |
| Chỉ check `hasRole("ADMIN")`, bỏ tenant | Admin vượt tenant ngoài ý muốn | Tenant boundary bao ngoài nhánh quyền |
| Tưởng GET rule bảo vệ PUT/DELETE | Write endpoint có thể bị mở | Khai báo theo method và scope riêng |
| Chỉ test 403 cho mọi URL | Có thể chỉ đang chạy `denyAll()` | Test ít nhất một case allow và biến path chính xác |
| Tự viết `response.sendError(403)` bên trong manager | Trộn decision và HTTP response | Trả AuthorizationDecision; để exception handling xử lý |
| Lưu currentUser/currentId trong singleton manager | Race condition giữa concurrent requests | Dùng local variables và stateless service |
| Manager/query và controller/query có dữ liệu đổi giữa chừng | TOCTOU và authorization stale | Enforce tại data access/transaction thích hợp |
| Tin rằng /api có đúng một chain | Một chain khác có thể match trước | Kiểm tra `securityMatcher`, `@Order` và filter list |
| Cho rằng 403 luôn do manager deny | Có thể CSRF, access denied khác, error dispatch | Test nguồn response và rule wiring |
| Dùng Bearer JWT nhưng suy ra role từ JSON request | Identity/claims không được verify | Resource server phải xác thực token/signature/claims |
| Bỏ các public endpoints không khai báo | App hoạt động sai khi denyAll toàn bộ | Khai báo chính xác public routes trước fallback |
| Bỏ method-level checks dù service có nhiều caller | Có thể bypass HTTP gate | Phòng vệ ở service / method security |

## 16. Bài tập thực hành

**Bài 1.** Alice có `ROLE_USER` và sở hữu project 101; Bob cũng có `ROLE_USER` nhưng sở hữu project 102. Vì sao `hasRole("USER")` không đủ cho GET /api/projects/{id}?

**Đáp án:** Role USER chỉ nói Alice/Bob có một quyền chung, không xác định object nào thuộc ai. Cần object-level authorization dựa trên resource ID/owner/tenant từ server.

**Bài 2.** Manager nhận `context.getVariables().get("projectId") == null`. Có nên cho phép request vì matcher “chắc đã khớp” không?

**Đáp án:** Không. Không đủ dữ liệu để xác định tài nguyên; deny hoặc xử lý lỗi cấu hình fail closed. Kiểm tra matcher hỗ trợ trích URI variables và tên biến khớp.

**Bài 3.** Manager lấy `request.getHeader("X-Role")` và cho phép nếu bằng ADMIN. Kẻ tấn công có thể làm gì?

**Đáp án:** Tự gửi header ADMIN và vượt qua kiểm tra. Role phải đến từ Authentication/identity store tin cậy, không phải header client có thể sửa.

**Bài 4.** Admin thuộc tenant north, project 201 thuộc south. Biểu thức `(sameTenant AND owner) OR isAdmin` có an toàn không?

**Đáp án:** Không nếu admin chỉ được hoạt động trong tenant. Nó cho admin bỏ qua sameTenant. Quy tắc đúng của ví dụ là `sameTenant AND (owner OR isAdmin)`.

**Bài 5.** Người dùng thiếu credentials truy cập GET project 101 và nhận 401; Alice đã xác thực truy cập project Bob và nhận 403. Hai trường hợp khác gì?

**Đáp án:** Trường hợp đầu chưa authentication hợp lệ và có thể kích hoạt entry point; trường hợp sau đã có identity nhưng authorization deny. Cấu hình HTTP Basic/form login/custom entry point quyết định status hoặc redirect cụ thể.

**Bài 6.** Developer đặt `requestMatchers("/api/**").permitAll()` trước rule `GET /api/projects/{projectId}.access(projectRead)`. Rủi ro?

**Đáp án:** Matcher rộng khớp trước có thể allow request mà không gọi custom manager. Đưa rule cụ thể trước và fallback deny theo thiết kế.

**Bài 7.** User có quyền GET /api/projects/101. Có đồng nghĩa được DELETE cùng URL không?

**Đáp án:** Không. Quyền phải ràng buộc method và nghiệp vụ. Rule chỉ GET trong ví dụ; DELETE không match và bị denyAll.

**Bài 8.** Test `GET /api/projects/999` trả 403. Có chứng minh `ProjectReadAuthorizationManager` hoạt động đúng không?

**Đáp án:** Chưa đủ; `denyAll()` cũng có thể trả 403. Test case Alice đọc 101 nhận 200 và test manager trực tiếp với variables giúp chứng minh wiring.

**Bài 9.** Sau khi manager check owner, một request khác thay đổi owner trong database trước khi controller đọc. Đây là vấn đề gì?

**Đáp án:** TOCTOU. Cần đảm bảo authorization phù hợp với dữ liệu thực được trả về tại thời điểm đọc, dùng query có điều kiện hoặc transaction/service-level enforcement.

**Bài 10.** Một background job gọi `ProjectService.read(101)` mà không đi qua Servlet filters. HTTP AuthorizationManager có tự chạy không?

**Đáp án:** Không. Nếu policy cần áp dụng cả ngoài HTTP, phải bảo vệ ở service/method security hoặc adapter phù hợp; HTTP manager chỉ là một cổng trong kiến trúc.

**Bài 11.** Trong Spring Security 6 mới, IDE báo `AuthorizationManager.check(...)` deprecated. Có phải mọi custom AuthorizationManager cần xóa ngay không?

**Đáp án:** Không. Cần kiểm tra JavaDoc/version chính xác, chuyển sang `authorize(...)`/`AuthorizationResult` theo API được hỗ trợ, duy trì semantics grant/deny, và chạy test. Deprecation không có nghĩa code tự động trở nên không an toàn, nhưng phải lập kế hoạch migration.

**Bài 12.** Một manager gọi DB policy service thất bại, developer trả `new AuthorizationDecision(true)` để endpoint không gián đoạn. Có ổn không?

**Đáp án:** Không. Không xác minh được quyền thì không thể grant. Xử lý lỗi hệ thống qua failure policy phù hợp, nhưng phải fail closed.

## 17. Checklist áp dụng cho dự án thật

- [ ] Xác định **request matcher, HTTP method, URL và SecurityFilterChain** cần bảo vệ; không đọc nhầm chain.
- [ ] Bắt đầu từ `authenticated/hasRole/hasAuthority`; chỉ thêm custom manager khi policy thực sự cần.
- [ ] Chọn `AuthorizationManager<RequestAuthorizationContext>` cho HTTP Servlet và type context thích hợp ở tầng khác.
- [ ] Dùng `RequestMatcher` có hỗ trợ URI variables nếu manager cần `getVariables()`; thiếu/sai biến thì deny.
- [ ] Principal/authorities/tenant membership phải từ nguồn đã xác thực và dữ liệu server tin cậy.
- [ ] Đặt điều kiện tenant **bao ngoài** owner/admin nếu admin không được vượt tenant.
- [ ] Deny khi resource không tồn tại, user anonymous, sai ID hoặc policy data không đầy đủ.
- [ ] Manager stateless, thread-safe; không lưu dữ liệu request vào singleton fields.
- [ ] Đặt rule cụ thể trước matcher rộng; kết thúc bằng fallback `denyAll()` phù hợp.
- [ ] Kiểm thử 200 allow, 403 authenticated deny, 401/302 unauthenticated và method/path không hợp lệ.
- [ ] Test ít nhất một case allow qua HTTP để chứng minh rule không bị denyAll ngầm che mất.
- [ ] Tách authorization khỏi CSRF, login, URL route binding và exception translation.
- [ ] Với dữ liệu mutable, đặt authorization gần điểm truy xuất/ghi dữ liệu, xử lý TOCTOU và transaction.
- [ ] Bảo vệ những service được gọi ngoài HTTP bằng method/service-level checks phù hợp.
- [ ] Kiểm tra API `check/authorize` và matcher behavior theo Spring Security 6.x version đang chạy.
- [ ] Quan sát metric/audit quyền an toàn, không log passwords, bearer tokens, session ID hoặc dữ liệu nhạy cảm.
- [ ] Chỉ grant khi có bằng chứng đủ; không fallback allow khi dữ liệu hoặc auth service lỗi.

**Kết luận:** `AuthorizationManager<RequestAuthorizationContext>` là cách gắn **quy tắc phân quyền HTTP tùy chỉnh** vào `authorizeHttpRequests(...).access(...)` trong Spring Security Servlet. Sức mạnh của nó nằm ở việc kết hợp danh tính đã xác thực, request/path đã được matcher phân loại và dữ liệu tài nguyên **đáng tin cậy phía server**. Hãy đặt tenant/owner boundary rõ ràng, fail closed, kiểm tra thứ tự matchers và filter chains, và bổ sung kiểm tra ở service khi dữ liệu có thể thay đổi hoặc được gọi từ những con đường khác ngoài HTTP.