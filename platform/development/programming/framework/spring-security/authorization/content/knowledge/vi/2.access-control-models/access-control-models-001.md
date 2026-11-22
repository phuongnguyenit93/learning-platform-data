# RBAC: Tổ chức quyền theo vai trò người dùng trong Spring Security

> **Chủ đề:** Mô hình kiểm soát truy cập (access control). Bài này trình bày **Role-Based Access Control — RBAC**: thiết kế vai trò, gắn quyền vào vai trò, gán vai trò cho người dùng và thực thi chính sách trong ứng dụng Java/Spring Security.

## 1. RBAC giải quyết vấn đề gì?

Giả sử hệ thống quản lý báo cáo có 1.000 người dùng và ba thao tác chính: **xem báo cáo**, **sửa báo cáo**, **quản lý tài khoản**. Nếu ứng dụng lưu riêng một danh sách quyền cho từng người, đội phát triển phải sửa các danh sách ấy khi tuyển dụng, điều chuyển nhân sự hoặc thay đổi trách nhiệm. Số lượng người dùng và loại hành động càng tăng, quyền càng dễ bị cấp sai hoặc bỏ sót.

**RBAC** giải quyết bằng cách đặt **vai trò (role)** ở giữa người dùng và quyền:

- **User (người dùng/chủ thể):** tài khoản hoặc danh tính cần truy cập tài nguyên; một người có thể có nhiều role.
- **Role (vai trò):** tập trách nhiệm được định nghĩa trong hệ thống, như `REPORT_VIEWER`, `REPORT_EDITOR`, `ADMIN`.
- **Permission (quyền thao tác):** một khả năng cụ thể như `report:read`, `report:write`, `users:manage`. Mỗi permission thường đại diện cho một **hành động trên một loại tài nguyên**.
- **Role assignment:** quan hệ gán người dùng vào role. **Permission assignment:** quan hệ gán permission vào role.
- **Policy/enforcement:** mã phía server xác định role/authority của người gọi và chặn thao tác khi thiếu permission cần thiết.

~~~text
                         GÁN VAI TRÒ              GÁN QUYỀN
User ────────────────────► Role ──────────────────► Permission
alice ───────────────────► VIEWER ─────────────────► report:read
bob   ───────────────────► EDITOR ─────────────────► report:read
                           EDITOR ─────────────────► report:write
carol ───────────────────► ADMIN ──────────────────► report:read
                           ADMIN ──────────────────► report:write
                           ADMIN ──────────────────► users:manage

Request: (principal, action, resource)
        └─► xác minh danh tính
             └─► lấy role được gán và quyền hiệu lực
                  └─► kiểm tra permission / điều kiện bổ sung
                       ├─► ALLOW: xử lý yêu cầu
                       └─► DENY: chặn ở server
~~~

**Cốt lõi:** quản trị viên không phải gán từng `report:read` cho mọi nhân viên. Họ gán `VIEWER`; hệ thống ánh xạ role ấy sang các permission đã được định nghĩa. Khi cần đổi chính sách của cả nhóm, chỉnh ánh xạ **role → permission** theo quy trình kiểm soát.

RBAC là **authorization** (quyết định cấp quyền), không phải quy trình xác minh mật khẩu/token. Spring Security thường xác thực danh tính trước, sau đó lấy các `GrantedAuthority` đáng tin để kiểm tra chính sách.

## 2. Thiết kế ma trận role–permission

Với hệ thống báo cáo ví dụ, có thể thống nhất ba role:

| Permission | `VIEWER` | `EDITOR` | `ADMIN` |
| --- | :---: | :---: | :---: |
| `report:read` — xem báo cáo | Có | Có | Có |
| `report:write` — sửa nội dung báo cáo | Không | Có | Có |
| `users:manage` — quản lý tài khoản | Không | Không | Có |

Người dùng được gán role; **quyền hiệu lực** là hợp của các permission mà những role đó cấp (nếu hệ thống không định nghĩa thêm quy tắc từ chối).

Ví dụ:
- Alice có `VIEWER` → đọc được báo cáo, không được sửa.
- Bob có `EDITOR` → đọc và sửa báo cáo, không được quản lý tài khoản.
- Carol có `ADMIN` → được cả ba quyền đã liệt kê.
- Nếu một người có đồng thời `VIEWER` và `EDITOR`, các quyền hợp lại; đừng giả định hệ thống tự hiểu role nào “cao hơn” role nào.

**Không tự suy ra quan hệ kế thừa chỉ từ tên role:** `ADMIN` không mặc nhiên bao gồm `EDITOR` trong Spring Security. Trong ma trận trên, `ADMIN` có `report:read` và `report:write` vì **ta đã gán tường minh**. Nếu muốn vai trò cấp trên kế thừa vai trò cấp dưới, cần cấu hình *role hierarchy* hoặc chủ động mở rộng permission lúc tạo danh tính.

### Nguyên tắc thiết kế role

1. **Đi từ hành động và tài nguyên:** xác định `report:read`, `report:write`, `users:manage` trước khi tạo role; tránh role mô tả mơ hồ như “quyền cao”.
2. **Gắn role với trách nhiệm nghiệp vụ:** `EDITOR` nói rõ nhiệm vụ, còn những role tùy tiện theo từng người sẽ làm mất lợi ích RBAC.
3. **Least privilege (đặc quyền tối thiểu):** mặc định chỉ cấp quyền cần thiết. Người chỉ xem báo cáo không cần quyền sửa.
4. **Deny by default:** endpoint hoặc tác vụ chưa được cấp quyền rõ ràng phải bị từ chối.
5. **Phân tách trách nhiệm (Separation of Duties):** có nghiệp vụ yêu cầu hai vai trò không được cùng nằm trên một người (ví dụ người đề nghị thanh toán và người duyệt). Đây là **ràng buộc bổ sung** của chính sách RBAC, không tự phát sinh chỉ vì có role.
6. **Tên quyền ổn định, ít phụ thuộc giao diện:** quyền `report:write` tốt hơn tên như `clickSaveButton` vì một quyền nghiệp vụ có thể được gọi qua web, API, batch job.
7. **Quản trị vòng đời role:** mỗi role nên có mô tả, người sở hữu, danh sách permission, quy trình phê duyệt, kiểm tra định kỳ và cơ chế thu hồi.

## 3. Role, authority và permission trong Spring Security

Spring Security kiểm tra quyền qua tập `GrantedAuthority` trong đối tượng `Authentication`. Framework không áp đặt một bảng SQL “role–permission” duy nhất; ứng dụng có thể cung cấp authorities từ `UserDetailsService`, SSO/OIDC, token đã được xác minh, database hoặc nguồn tin cậy khác.

**Cách Spring Security hiểu các chuỗi:**

| Cách viết | Điều được kiểm tra trong `Authentication#getAuthorities()` |
| --- | --- |
| `hasRole("ADMIN")` | Authority `ROLE_ADMIN` theo tiền tố role mặc định |
| `hasAuthority("ROLE_ADMIN")` | So khớp chính xác `ROLE_ADMIN` |
| `hasAuthority("report:read")` | So khớp chính xác `report:read` |
| `hasAnyRole("EDITOR", "ADMIN")` | Có ít nhất một role tương ứng |
| `authenticated()` | Đã xác thực theo quy tắc của framework; chưa yêu cầu permission cụ thể |
| `permitAll()` / `denyAll()` | Luôn cho phép / luôn từ chối theo quy tắc đó |

**Role** cũng được biểu diễn như một authority, thường có tiền tố `ROLE_`. Một **permission** như `report:write` có thể được lưu dưới dạng authority thường, không có tiền tố. Vì vậy:

- `User.withUsername("bob").roles("EDITOR")` tạo `ROLE_EDITOR`, **không tự tạo** `report:read` hoặc `report:write`.
- `User.withUsername("bob").authorities("ROLE_EDITOR", "report:read", "report:write")` cung cấp cả nhãn role và các quyền cụ thể.
- Builder `roles(...)` và `authorities(...)` đều thiết lập danh sách authority; đừng gọi nối tiếp hai cách rồi mặc định rằng chúng tự cộng dồn. Hãy tự tạo **một danh sách authority hoàn chỉnh** nếu cần cả hai.

Trong kiến trúc RBAC ứng dụng, một cách thông dụng là nạp role của user rồi **mở rộng** chúng thành authorities tương ứng với permission; khi đó controller/service có thể yêu cầu `hasAuthority("report:write")` thay vì phải nhớ role nào sở hữu quyền ấy. Cách khác là kiểm tra `hasRole(...)` trực tiếp ở những endpoint thực sự chỉ dành cho một vai trò. Cả hai cách đều hợp lệ khi chính sách thống nhất.

## 4. Ví dụ Spring Boot Java 17+: ánh xạ role → permission ở một chỗ

Ví dụ này có ba tài khoản và ba role theo ma trận ở mục 2. Nó cho thấy cách xây dựng một **bảng ánh xạ trung tâm** `ROLE_PERMISSIONS`, cấp authorities từ role, bảo vệ request và tái kiểm tra tại tầng service.

**Chuẩn bị:** tạo dự án Maven qua Spring Initializr với **Java 17+**, dependency **Spring Web** và **Spring Security**. Các class bên dưới thuộc Spring Boot + Spring Security; ví dụ được chạy bằng Maven Wrapper của dự án, không phải chỉ với `javac` của JDK trần. Tạo tệp:

`src/main/java/com/example/rbac/RbacApplication.java`

~~~java
package com.example.rbac;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class RbacApplication {

    private static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
        "VIEWER", Set.of("report:read"),
        "EDITOR", Set.of("report:read", "report:write"),
        "ADMIN", Set.of("report:read", "report:write", "users:manage")
    );

    public static void main(String[] args) {
        SpringApplication.run(RbacApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/reports/view").hasAuthority("report:read")
                .requestMatchers("/reports/editor").hasAuthority("report:write")
                .requestMatchers("/admin/users").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = account("alice", "demo123", encoder, "VIEWER");
        UserDetails bob = account("bob", "demo456", encoder, "EDITOR");
        UserDetails carol = account("carol", "demo789", encoder, "ADMIN");
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    private static UserDetails account(
            String name, String password, PasswordEncoder encoder, String... roles) {

        Set<String> authorities = new LinkedHashSet<>();

        for (String role : roles) {
            Set<String> permissions = ROLE_PERMISSIONS.get(role);
            if (permissions == null) {
                throw new IllegalArgumentException("Unknown role: " + role);
            }

            authorities.add("ROLE_" + role);
            authorities.addAll(permissions);
        }

        return User.withUsername(name)
            .password(encoder.encode(password))
            .authorities(authorities.toArray(String[]::new))
            .build();
    }

    @RestController
    static class RbacController {
        private final ReportService reports;

        RbacController(ReportService reports) {
            this.reports = reports;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/reports/view")
        String view() {
            return reports.readReport();
        }

        @GetMapping("/reports/editor")
        String editor() {
            return reports.openEditor();
        }

        @GetMapping("/admin/users")
        String users() {
            return "user administration";
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasAuthority('report:read')")
        public String readReport() {
            return "report data";
        }

        @PreAuthorize("hasAuthority('report:write')")
        public String openEditor() {
            return "report editor";
        }
    }
}
~~~

**Các chi tiết đáng chú ý trong ví dụ:**

1. `ROLE_PERMISSIONS` là **nguồn cấu hình role → permission** của ví dụ, tránh lặp bảng quyền cho từng account. Trong môi trường thật, nguồn này có thể đến từ cấu hình đã kiểm soát hoặc các bảng role/permission trong database.
2. `account(...)` thêm cả authority `ROLE_...` và các authority permission. Với Bob, kết quả bao gồm `ROLE_EDITOR`, `report:read` và `report:write`.
3. `/reports/view` kiểm tra `report:read` tại HTTP; `/reports/editor` kiểm tra `report:write`. `/admin/users` minh họa kiểm tra trực tiếp `hasRole("ADMIN")`.
4. `@EnableMethodSecurity` kích hoạt `@PreAuthorize` trên service. Bởi controller gọi **bean `ReportService` khác** qua Spring proxy, kiểm tra method-level thực thi khi gọi. Không nên trông cậy vào `@PreAuthorize` khi một phương thức trong cùng bean gọi một phương thức khác qua `this` theo cơ chế proxy thông thường.
5. `GET /reports/editor` chỉ trả về thông điệp “report editor”, **không thay đổi dữ liệu**; nó là ví dụ truy cập trang soạn thảo. Với thao tác ghi thật, hãy bảo vệ `POST`/`PUT`/`PATCH` và xử lý CSRF thích hợp cho cơ chế xác thực của ứng dụng.
6. `anyRequest().denyAll()` đóng các tuyến chưa được khai báo. `requestMatchers` được xét theo thứ tự; đặt quy tắc cụ thể trước quy tắc bao quát.
7. Mật khẩu demo được mã hóa bằng BCrypt để Spring Security kiểm tra; **không hardcode tài khoản/mật khẩu mẫu trong sản phẩm thật**. HTTP Basic chỉ an toàn khi chạy qua HTTPS trong môi trường thực tế.

### Chạy và thử kết quả

Tại thư mục dự án, chạy:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Trong một terminal khác:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/reports/view
curl -i -u alice:demo123 http://localhost:8080/reports/view
curl -i -u alice:demo123 http://localhost:8080/reports/editor
curl -i -u bob:demo456 http://localhost:8080/reports/editor
curl -i -u bob:demo456 http://localhost:8080/admin/users
curl -i -u carol:demo789 http://localhost:8080/admin/users
~~~

| Request | Kết quả HTTP kỳ vọng | Vì sao |
| --- | --- | --- |
| `GET /public/ping` không credential | `200`, `pong` | `permitAll()` |
| `GET /reports/view` không credential | `401` | Chưa xác thực cho tài nguyên yêu cầu authority |
| `GET /reports/view` với Alice | `200`, `report data` | `VIEWER` có `report:read` |
| `GET /reports/editor` với Alice | `403` | Thiếu `report:write` |
| `GET /reports/editor` với Bob | `200`, `report editor` | `EDITOR` có `report:write` |
| `GET /admin/users` với Bob | `403` | Thiếu `ROLE_ADMIN` |
| `GET /admin/users` với Carol | `200`, `user administration` | Có `ROLE_ADMIN` |

Các status 401/403 trong bảng giả định **cấu hình HTTP Basic của ví dụ**: không cung cấp credential cho endpoint được bảo vệ thường dẫn đến 401; danh tính hợp lệ nhưng thiếu authority dẫn đến 403. Với form login, trường hợp chưa đăng nhập có thể nhận chuyển hướng đến trang đăng nhập thay vì 401.

**Điểm học được:** route nào cũng nhận request từ client, nhưng **server** kiểm tra chính sách. Ẩn nút “Sửa” trên frontend chỉ cải thiện giao diện; người dùng vẫn có thể gọi API trực tiếp, nên quy tắc RBAC phải nằm tại backend.

## 5. Lưu role và permission trong database

Với tổ chức có nhiều tài khoản, ánh xạ in-memory ở mục 4 có thể được thay bằng mô hình dữ liệu quan hệ. Cấu trúc tối thiểu thường gồm:

| Bảng | Vai trò |
| --- | --- |
| `app_users` | Danh sách tài khoản/định danh nội bộ |
| `roles` | Danh mục role, khóa duy nhất theo mã role |
| `permissions` | Danh mục permission, khóa duy nhất theo mã permission |
| `user_roles` | Bảng nối nhiều-nhiều giữa user và role |
| `role_permissions` | Bảng nối nhiều-nhiều giữa role và permission |

Ví dụ DDL theo **PostgreSQL** (minh họa cấu trúc phân quyền; chưa phải schema hoàn chỉnh cho mọi nghiệp vụ):

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE roles (
    id BIGINT PRIMARY KEY,
    role_code VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE permissions (
    id BIGINT PRIMARY KEY,
    permission_code VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES app_users(id),
    role_id BIGINT NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id),
    permission_id BIGINT NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);
~~~

Để lấy permission **được cấp qua role** của một user:

~~~sql
SELECT DISTINCT p.permission_code
FROM user_roles ur
JOIN role_permissions rp ON rp.role_id = ur.role_id
JOIN permissions p ON p.id = rp.permission_id
WHERE ur.user_id = :user_id;
~~~

`:user_id` là tham số liên kết của truy vấn do tầng truy cập dữ liệu truyền vào, không phải cú pháp SQL PostgreSQL chạy độc lập trong console. Trong ứng dụng thực tế, dùng prepared statement/parameter binding.

**Khi tích hợp với Spring Security:** quá trình authentication có thể đọc role người dùng, nạp permission tương ứng rồi dựng một `Authentication`/`UserDetails` với authorities thích hợp. Spring Security **không tự tạo database RBAC hoặc tự đồng bộ bảng `role_permissions`** chỉ vì ứng dụng gọi `hasRole`.

Với hệ thống multi-tenant, role assignment thường còn gắn với **tenant** hoặc phạm vi tổ chức. Không được lấy role `ADMIN` của tenant A rồi áp dụng cho dữ liệu tenant B nếu quyền quản trị chỉ có hiệu lực trong tenant A. Có thể cần khóa/phạm vi như `tenant_id` trong mô hình quan hệ và trong kiểm tra quyền.

## 6. Vai trò phân cấp (role hierarchy) và cách tránh hiểu sai

RBAC có thể gồm nhiều cấp độ:

- **RBAC cơ bản:** user được gán role, role được gán permission, hệ thống đánh giá quyền hiệu lực.
- **Hierarchical RBAC:** role có quan hệ kế thừa rõ ràng, ví dụ `ADMIN > EDITOR > VIEWER`.
- **Constrained RBAC:** giới hạn việc gán/kích hoạt role, ví dụ hai role “Tạo lệnh chi” và “Duyệt lệnh chi” không được gán cùng một user.

Trong Spring Security, có thể khai báo role hierarchy như đoạn sau (đây là **fragment cấu hình** cần đặt trong lớp `@Configuration` cùng imports tương ứng, không phải chương trình Java độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy(
        "ROLE_ADMIN > ROLE_EDITOR\nROLE_EDITOR > ROLE_VIEWER");
}
~~~

Với cấu hình trên, role cấp cao có thể được coi là mang các authority của role thấp hơn **ở các cơ chế authorization được cấu hình dùng hierarchy**. Không nhầm lẫn điều này với dữ liệu gốc trong `Authentication#getAuthorities()`: hierarchy tính các quyền reachable tại bước kiểm tra, không nhất thiết ghi lại authorities mới vào user.

Khi dùng biểu thức `@PreAuthorize`/`@PostAuthorize`, cấu hình `MethodSecurityExpressionHandler` để áp dụng hierarchy, chẳng hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

Đoạn này cũng là **fragment**; tài liệu chính thức khuyến nghị đăng ký handler theo cách Spring xử lý kịp lúc khởi tạo method security (thường dùng `static @Bean`). Trong hệ thống sử dụng hierarchy, phải cấu hình/thử nghiệm sự nhất quán giữa kiểm tra HTTP và method. Đừng kết hợp tùy tiện role hierarchy với danh sách permission đã mở rộng tường minh thành hai nguồn chính sách mâu thuẫn.

**Lựa chọn thực tế:** ma trận mục 2 phù hợp cả khi không dùng hierarchy. Nếu `ADMIN` đã được gán các permission cần thiết, không cần thêm hierarchy chỉ để “ADMIN tự có mọi quyền”. Ngược lại, khi nhiều role cấp cao kế thừa role cấp thấp một cách ổn định, hierarchy có thể giảm lặp.

## 7. Giới hạn của RBAC và lúc cần điều kiện khác

RBAC trả lời rất tốt câu hỏi **“role này có thể thực hiện loại hành động nào?”**. Nhưng nhiều ứng dụng cần quyết định dựa trên **đối tượng cụ thể** hoặc bối cảnh:

- Bob có `report:read` nhưng chỉ được xem báo cáo thuộc phòng ban của Bob.
- Alice có `invoice:approve` nhưng không được duyệt hóa đơn do chính Alice tạo.
- User là `ADMIN` trong một tenant, không có quyền quản trị tenant khác.
- Tác vụ chỉ được phép trong trạng thái `DRAFT` hoặc khi quy mô giao dịch nằm dưới hạn mức được duyệt.

Đây là nơi RBAC thường kết hợp kiểm tra **ownership**, scope/tenant, trạng thái đối tượng và các điều kiện thuộc tính theo nghiệp vụ (ABAC hoặc policy chuyên biệt).

Ví dụ minh họa ý tưởng kiểm tra ở service:

~~~java
// Fragment minh họa, không phải class chạy độc lập:
@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long reportId, Authentication auth) {
    Report report = repository.findById(reportId).orElseThrow();
    if (!report.getTenantId().equals(currentTenantId(auth))) {
        throw new AccessDeniedException("No access to this tenant");
    }
    return mapper.toDto(report);
}
~~~

Permission `report:read` là **điều kiện cần**; quyền trên chính report cũng phải được xét trước khi trả dữ liệu. Các tên `ReportDto`, `repository`, `mapper` và `currentTenantId` trong đoạn fragment là thành phần nghiệp vụ cần có trong dự án thật. Ví dụ không thể biên dịch độc lập; mục đích là chỉ ra **vị trí áp dụng điều kiện đối tượng**.

Đối với hệ thống phức tạp, nên đặt chính sách vào service/policy component dùng chung hoặc custom `AuthorizationManager` để không sao chép những đoạn điều kiện khác nhau ở nhiều controller.

## 8. Các rủi ro triển khai cần kiểm soát

### Quyền thay đổi khi session/token đang còn hiệu lực

Nếu role của Bob đổi từ `EDITOR` sang `VIEWER`, việc sửa bảng `user_roles` **không đảm bảo** mọi phiên/JWT đang tồn tại mất quyền ngay lập tức. Tùy cơ chế xác thực, danh sách authority có thể đã được lưu trong session, token hoặc cache. Cần chọn chiến lược phù hợp: thu hồi session, làm mới token, token thời hạn ngắn, kiểm tra quyền từ server hoặc cơ chế versioning/invalidation. Với quyền nhạy cảm, xác định độ trễ thu hồi tối đa được chấp nhận.

### Không giao quyền từ đầu vào không đáng tin

Role do frontend gửi lên, query parameter, hoặc claim token chưa được xác minh **không được tự động tin cậy**. Chỉ chuyển chúng thành `GrantedAuthority` sau khi nguồn danh tính và chính sách ánh xạ đã được xác minh. Với OAuth2/OIDC, phân biệt role của client/realm/resource server với permission có hiệu lực ở ứng dụng này.

### Ghi log và kiểm thử

- Ghi nhận thay đổi **ai cấp/thu hồi role nào, cho ai, lúc nào, vì lý do gì**.
- Viết ma trận kiểm thử **role × endpoint × hành động × tenant/ownership**.
- Có test âm tính: tài khoản đúng nhưng thiếu quyền phải bị chặn; route mới chưa có rule phải bị chặn; user thuộc tenant khác không được vượt phạm vi.
- Đối với thao tác POST/PUT/DELETE, kiểm tra cả authorization lẫn bảo vệ CSRF phù hợp. CSRF 403 không được nhầm với 403 do thiếu role.
- Không log mật khẩu, access token hoặc thông tin nhạy cảm của credential.

### Những sai lầm phổ biến

1. **Role explosion:** tạo role cho từng biến thể người dùng/tài nguyên; hãy tách permission nền tảng và điều kiện đối tượng.
2. **Role tự động kế thừa:** mặc định gán `ROLE_ADMIN` không làm Spring hiểu có `ROLE_EDITOR`; cần ánh xạ rõ hoặc hierarchy được cấu hình.
3. **Nhầm `hasRole` với `hasAuthority`:** `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`, trong khi `hasAuthority("ADMIN")` yêu cầu authority đúng chuỗi `ADMIN`.
4. **Chỉ chặn ở frontend:** giao diện không phải điểm thực thi bảo mật; backend bắt buộc xác minh quyền.
5. **Kiểm tra “đã đăng nhập” thay cho permission:** `authenticated()` không tương đương `hasAuthority("report:write")`.
6. **Hardcode kiểm tra theo username:** `if (name.equals("alice"))` khó quản trị và tạo đặc quyền ẩn; role/permission nên được định nghĩa có cấu trúc.
7. **Gán `ROLE_ADMIN` toàn hệ thống cho mọi quản trị viên bộ phận:** thiếu ngữ cảnh tenant, phạm vi tổ chức và nguyên tắc ít quyền nhất.
8. **Bỏ quên kiểm tra method/service:** các luồng gọi service từ endpoint/job khác vẫn cần enforcement phù hợp.
9. **Tin rằng token/phiên tự cập nhật:** cần quản lý việc thu hồi quyền và vòng đời nguồn authority.
10. **Thêm `anyRequest().permitAll()` để sửa nhanh lỗi 403:** điều này có thể mở endpoint mới ngoài ý muốn; hãy xác định quy tắc cần thiết thay vì mở mặc định.

## 9. Checklist thiết kế và tự kiểm tra

Trước khi đưa RBAC vào dự án, trả lời được các câu hỏi sau:

- Danh sách **action/resource** nào cần bảo vệ? Permission code có rõ ràng và nhất quán không?
- Mỗi role phục vụ trách nhiệm gì? Role nào có permission nào, ai phê duyệt thay đổi?
- User có thể giữ nhiều role không? Nếu có, quy tắc hợp quyền là gì? Có role xung đột cần chặn không?
- Chính sách được thực thi ở HTTP, method/service và mức bản ghi/tenant ra sao?
- Authorities được nạp từ đâu? Khi role bị thu hồi, session/token/cache hết hiệu lực lúc nào?
- Endpoint mới có mặc định từ chối? Có test cho user thiếu quyền và tenant khác?
- Log quản trị role có đủ để truy vết và kiểm toán không?

**Câu hỏi nhanh:**

1. Alice có `VIEWER`, API yêu cầu `report:write`. **Kết quả:** từ chối; việc đã xác thực không thay quyền.
2. Bob có `EDITOR`. Có được gọi endpoint yêu cầu `hasAuthority("report:read")` không? **Có**, nếu role mapping thực sự cấp permission đó như ma trận mục 2.
3. Carol có `ROLE_ADMIN` nhưng **không** có `report:read` và hệ thống **không** bật hierarchy/mở rộng permission. `hasAuthority("report:read")` có cho phép không? **Không**; role name không tự sinh quyền con.
4. Hai nhân viên cùng role `VIEWER`; một người muốn xem tài liệu riêng của người kia. Chỉ kiểm tra `report:read` có đủ không? **Không**; phải kiểm tra quyền đối tượng/scope.
5. Role bị thu hồi trong database, access token cũ còn hạn. Quyền có biến mất ngay không? **Phụ thuộc vào cơ chế nạp/cập nhật quyền**, không thể mặc định là có.

**Ghi nhớ:** **User → Role → Permission** giúp quản trị quyền nhất quán và dễ kiểm soát. Spring Security kiểm tra các `GrantedAuthority`/role theo chính sách đã khai báo; quyền thực tế còn phụ thuộc tài nguyên và ngữ cảnh. Thiết kế tốt là role rõ trách nhiệm, permission rõ hành động, ít quyền nhất, mặc định từ chối và có cơ chế thu hồi quyền.

## Tài liệu chính thức để đọc thêm

- Spring Security — Authorization Architecture (role hierarchy): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — RoleHierarchyImpl API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
