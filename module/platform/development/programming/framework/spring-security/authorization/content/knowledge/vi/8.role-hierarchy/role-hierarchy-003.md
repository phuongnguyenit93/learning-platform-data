# Mô tả ADMIN bao hàm MANAGER, USER mà không nhân bản quyền trong Spring Security

> **Chủ đề:** Spring Security — Role hierarchy. Bài này xây dựng mô hình **ADMIN bao hàm MANAGER, MANAGER bao hàm USER**, giải thích quan hệ kế thừa bắc cầu, cách cấu hình `RoleHierarchy` để không phải lưu/cấp lặp quyền trên từng tài khoản, và cách kiểm chứng bằng Java 17+, Spring Boot, phân quyền HTTP và method security.

## 1. Bài toán: role cao hơn nên dùng được chức năng của role thấp hơn

Giả sử ứng dụng quản lý công việc có ba vai trò:

| Role nghiệp vụ | Chức năng đặc trưng |
| --- | --- |
| `USER` | Xem trang cá nhân, đọc công việc được phép |
| `MANAGER` | Thực hiện chức năng của USER và phê duyệt công việc trong phạm vi quản lý |
| `ADMIN` | Thực hiện chức năng của MANAGER, USER và quản lý cấu hình hệ thống |

Nếu không có role hierarchy, ta thường phải chọn một trong hai hướng:

1. **Nhân bản role khi cấp cho tài khoản:** admin được lưu `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER`; manager được lưu `ROLE_MANAGER`, `ROLE_USER`. Điều này dễ gây dữ liệu dư thừa, khó thu hồi đồng bộ khi thay đổi cấu trúc.
2. **Lặp lại OR trong mọi chính sách:** endpoint dành cho USER kiểm `hasAnyRole("USER", "MANAGER", "ADMIN")`; endpoint MANAGER kiểm `hasAnyRole("MANAGER", "ADMIN")`. Khi thêm role mới hoặc đổi quyền, phải sửa nhiều vị trí.

**Role hierarchy** giải quyết vấn đề bằng cách lưu **vai trò được cấp trực tiếp** cho user, đồng thời khai báo **quan hệ bao hàm dùng khi kiểm quyền**:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER

Khai báo:
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

Dấu `>` được hiểu là **“bao hàm quyền/authority phía dưới”**. Vì quan hệ có tính bắc cầu:

- User chỉ có `ROLE_ADMIN` cũng được nhận diện là có `ROLE_MANAGER` và `ROLE_USER` khi thành phần authorization **áp dụng hierarchy**.
- User chỉ có `ROLE_MANAGER` được nhận diện là có `ROLE_USER`, **không** có `ROLE_ADMIN`.
- User chỉ có `ROLE_USER` **không** được nâng lên MANAGER hoặc ADMIN.

**Đây là kế thừa một chiều**, không phải ba role tương đương nhau.

## 2. Phân biệt role trực tiếp và role hiệu lực

Trong Spring Security, `Authentication#getAuthorities()` chứa các `GrantedAuthority` **được cấp trực tiếp** cho người dùng bởi quá trình xác thực. Thông thường `SimpleGrantedAuthority("ROLE_ADMIN")` có chuỗi chính xác `ROLE_ADMIN`.

`RoleHierarchy` là thành phần có thể suy ra thêm **authorities hiệu lực** khi kiểm quyền:

`effectiveAuthorities = getReachableGrantedAuthorities(directAuthorities)`.

Với cấu hình `ROLE_ADMIN > ROLE_MANAGER` và `ROLE_MANAGER > ROLE_USER`:

| Principal | Authority cấp trực tiếp | Authorities hiệu lực khi dùng hierarchy |
| --- | --- | --- |
| Alice | `ROLE_ADMIN` | `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER` |
| Bob | `ROLE_MANAGER` | `ROLE_MANAGER`, `ROLE_USER` |
| Carol | `ROLE_USER` | `ROLE_USER` |
| Dave | `report:read` | `report:read` (không có role nằm trong hierarchy) |

Bảng này thể hiện **quan hệ kiểm tra**, không nói rằng framework tự ghi `ROLE_MANAGER` và `ROLE_USER` vào database/session/token của Alice.

### Không nhân bản dữ liệu có nghĩa là gì?

Ví dụ trong cơ sở dữ liệu quan hệ, bảng user-role chỉ cần:

| user_id | role_code |
| --- | --- |
| alice | ADMIN |
| bob | MANAGER |
| carol | USER |

Không cần tự lưu thêm hai dòng MANAGER/USER cho Alice hoặc dòng USER cho Bob **chỉ để thực hiện kế thừa**. Ứng dụng ánh xạ `ADMIN` thành `ROLE_ADMIN` khi tải danh tính; `RoleHierarchy` sẽ suy diễn quyền ở những điểm authorization được cấu hình tương thích.

**Lưu ý:** nếu hệ thống thực sự muốn Alice đồng thời là thành viên của **hai nhóm tổ chức độc lập**, việc cấp nhiều role trực tiếp có thể hợp lệ. “Không nhân bản” ở đây nói về những role được thêm **chỉ vì quan hệ kế thừa**, không cấm nhiều role độc lập cho một user.

### Role hierarchy không làm thay đổi role trong token

- `Authentication#getAuthorities()` của Alice vẫn có thể chỉ chứa `ROLE_ADMIN`.
- `RoleHierarchy#getReachableGrantedAuthorities(...)` có thể trả thêm `ROLE_MANAGER` và `ROLE_USER`.
- Token JWT do IdP phát hành vẫn giữ claim gốc; role hierarchy không tự viết lại JWT.
- Một service riêng không được cung cấp cùng hierarchy có thể đánh giá quyền khác; cần kiểm chứng nhất quán ở tất cả điểm enforcement.

## 3. Role hierarchy là một đồ thị có hướng

Mỗi dòng `A > B` là một cạnh từ vai trò **cao hơn** đến vai trò **được bao hàm**. Kết quả phải xét **đường đi bắc cầu** (*transitive closure*).

~~~text
Các cạnh:
    ADMIN  --> MANAGER
    MANAGER --> USER

Đường đi:
    ADMIN  --> USER  (qua MANAGER)

Không tồn tại chiều ngược:
    USER   -X-> MANAGER
    MANAGER -X-> ADMIN
~~~

Bài toán kiểm tra:

`hasEffectiveRole(subject, requiredRole) = requiredRole ∈ reachable(directRoles(subject))`.

Ví dụ Alice có `ROLE_ADMIN`:

- `hasRole("ADMIN")`: ALLOW.
- `hasRole("MANAGER")`: ALLOW nhờ kế thừa.
- `hasRole("USER")`: ALLOW nhờ kế thừa bắc cầu.

Bob có `ROLE_MANAGER`:

- `hasRole("ADMIN")`: DENY.
- `hasRole("MANAGER")`: ALLOW.
- `hasRole("USER")`: ALLOW.

### Quan hệ không nên tạo chu trình

Định nghĩa:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
ROLE_USER > ROLE_ADMIN
~~~

là **sai mô hình**: role thấp có thể quay ngược và bao hàm role cao, làm mất phân cấp. `RoleHierarchyImpl` có cơ chế phát hiện chu trình trong lúc xây dựng quan hệ và có thể ném ngoại lệ; đừng thiết kế vòng kế thừa hoặc phụ thuộc vào việc thư viện tự “đoán” ý nghiệp vụ.

### Một role có thể bao hàm nhiều role?

Có. Ví dụ một role `ROLE_DIRECTOR` bao hàm cả `ROLE_MANAGER` và `ROLE_AUDITOR` nếu chính sách nghiệp vụ định nghĩa như vậy. Tuy nhiên, role hierarchy không nên biến thành “mọi role đều có mọi quyền” hoặc gom các trách nhiệm không liên quan. Phân tách nhiệm vụ (*separation of duties*) có thể đòi kiểm tra độc lập.

## 4. Cấu hình `RoleHierarchyImpl.fromHierarchy`

Spring Security hỗ trợ interface:

`org.springframework.security.access.hierarchicalroles.RoleHierarchy`

và implementation:

`org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl`.

Cách khai báo trực tiếp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class HierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\n"
          + "ROLE_MANAGER > ROLE_USER"
        );
    }
}
~~~

Đây là một **class cấu hình chạy trong Spring ApplicationContext**, không phải chương trình có `main` để chạy độc lập. Mỗi dòng `ROLE_X > ROLE_Y` mô tả **một quan hệ bao hàm**. Không cần khai báo thêm `ROLE_ADMIN > ROLE_USER` vì suy diễn bắc cầu đã có.

**Tại sao dùng `fromHierarchy`?** Ở Spring Security 6.5, đây là static factory tạo hierarchy từ các dòng văn bản. `setHierarchy(...)` là cách đặt cấu hình đời cũ và đã bị deprecated trong các API mới; dùng factory cho mã mới sẽ rõ ý hơn.

### Cách khai báo bằng builder

Từ Spring Security 6.3 có thể dùng builder với prefix mặc định `ROLE_`:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER")
        .build();
}
~~~

Đây là **phương án thay thế** cho bean `roleHierarchy()` ở trên: chỉ đăng ký **một** bean làm nguồn hierarchy, không sao chép cả hai đoạn `@Bean` vào cùng project. Builder tự thêm `ROLE_` theo prefix cấu hình khi xây dựng quan hệ; với `fromHierarchy`, ta chủ động viết tên authority hoàn chỉnh.

### Tránh thiếu hoặc nhân đôi prefix

- `hasRole("USER")` thường yêu cầu authority `ROLE_USER` khi dùng quy ước mặc định.
- `User.withUsername(...).roles("ADMIN")` tạo `ROLE_ADMIN`.
- `User.withUsername(...).authorities("ROLE_ADMIN")` tạo đúng authority literal `ROLE_ADMIN`.
- Nếu dùng prefix tùy chỉnh như `APP_` thông qua `GrantedAuthorityDefaults`, phải **đồng bộ** user authority mapping, builder hierarchy và từng consumer; một bean prefix không tự viết lại chuỗi `ROLE_ADMIN` có sẵn thành `APP_ADMIN`.
- Đừng dùng `roles("ROLE_ADMIN")`; builder `roles(...)` nhận tên role không có tiền tố và sẽ tự thêm `ROLE_`.

## 5. Java 17 thuần: chứng minh tính bắc cầu mà không nhân bản quyền

Chương trình này **không phụ thuộc Spring**; dùng đồ thị và breadth-first traversal để mô phỏng reachable authorities. Nó minh họa rõ vì sao không cần lưu `ROLE_USER` cho Alice.

Tạo tệp **`RoleGraphDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.HashSet;

public class RoleGraphDemo {

    private static final Map<String, List<String>> INCLUDES = Map.of(
        "ROLE_ADMIN", List.of("ROLE_MANAGER"),
        "ROLE_MANAGER", List.of("ROLE_USER")
    );

    static List<String> reachable(String directRole) {
        Queue<String> queue = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        queue.add(directRole);

        while (!queue.isEmpty()) {
            String role = queue.remove();
            if (visited.add(role)) {
                queue.addAll(INCLUDES.getOrDefault(role, List.of()));
            }
        }

        List<String> sorted = new ArrayList<>(visited);
        sorted.sort(String::compareTo);
        return sorted;
    }

    static boolean hasRole(String directRole, String requiredRole) {
        return reachable(directRole).contains(requiredRole);
    }

    public static void main(String[] args) {
        System.out.println("ADMIN reachable = "
            + reachable("ROLE_ADMIN"));
        System.out.println("MANAGER reachable = "
            + reachable("ROLE_MANAGER"));
        System.out.println("USER reachable = "
            + reachable("ROLE_USER"));
        System.out.println("ADMIN has USER = "
            + hasRole("ROLE_ADMIN", "ROLE_USER"));
        System.out.println("MANAGER has ADMIN = "
            + hasRole("ROLE_MANAGER", "ROLE_ADMIN"));
        System.out.println("USER has MANAGER = "
            + hasRole("ROLE_USER", "ROLE_MANAGER"));
    }
}
~~~

Chạy bằng **JDK 17+** trong thư mục chứa tệp:

~~~bash
javac RoleGraphDemo.java
java RoleGraphDemo
~~~

**Stdout xác định từ mã:**

~~~text
ADMIN reachable = [ROLE_ADMIN, ROLE_MANAGER, ROLE_USER]
MANAGER reachable = [ROLE_MANAGER, ROLE_USER]
USER reachable = [ROLE_USER]
ADMIN has USER = true
MANAGER has ADMIN = false
USER has MANAGER = false
~~~

Giải thích:

- Input của Alice có thể chỉ là `ROLE_ADMIN`. Chương trình duyệt ADMIN → MANAGER → USER và trả danh sách **hiệu lực**.
- Bob có `ROLE_MANAGER`, kết quả chỉ gồm MANAGER/USER; không có chiều kế thừa ngược lên ADMIN.
- Carol có `ROLE_USER`, không được tự nâng lên MANAGER.
- `HashSet` dùng để tránh duyệt cùng nút nhiều lần; danh sách được sắp xếp trước khi in nên output có thứ tự cố định.

Đây chỉ là mô phỏng đồ thị role, không thay thế `RoleHierarchyImpl`, `Authentication` hoặc cơ chế ra quyết định thực của Spring Security. Mục đích là hiểu đúng toán học của quan hệ.

## 6. Spring Security sử dụng hierarchy ở những đâu?

Một `RoleHierarchy` được tạo ra **không đồng nghĩa** mọi custom authorization check trong toàn ứng dụng sẽ tự sử dụng nó. Hãy phân biệt ít nhất các nơi:

| Nơi kiểm tra | Có thể sử dụng hierarchy? | Cách bảo đảm |
| --- | --- | --- |
| `authorizeHttpRequests(...).hasRole(...)` | Có, trong cấu hình Spring Security tích hợp `RoleHierarchy` | Đăng ký bean hierarchy và kiểm chứng bằng HTTP integration test theo phiên bản |
| `authorizeHttpRequests(...).hasAuthority(...)` | Có khi manager được cấu hình với hierarchy | Đọc contract / test đúng manager |
| `@PreAuthorize("hasRole(...)")` | Có | Bật `@EnableMethodSecurity` và đặt `RoleHierarchy` trong `DefaultMethodSecurityExpressionHandler` |
| `@PreAuthorize("hasAuthority(...)")` | Có khi expression handler dùng hierarchy | Cấu hình method expression handler và test |
| `@Secured(...)` | Có trong các phiên bản hỗ trợ | Bật `securedEnabled`, xác nhận manager/hierarchy |
| `@RolesAllowed(...)` | Có trong các phiên bản hỗ trợ | Bật `jsr250Enabled`, kiểm tra manager tương ứng |
| `AuthorityAuthorizationManager.hasRole(...)` tự tạo qua static factory | Không mặc định bảo đảm nhận bean hierarchy từ context | Nếu tự lắp manager, dùng `setRoleHierarchy(...)` và kiểm thử |
| Custom `AuthorizationManager` hoặc policy bean | **Không thể suy đoán** | Tiêm `RoleHierarchy` rồi dùng nó đúng contract, hoặc đánh giá role trực tiếp có chủ đích |
| `Authentication#getAuthorities()` | Không tự mở rộng danh sách | Dùng `getReachableGrantedAuthorities(...)` để xem hiệu lực |
| JWT converter / user repository | Không tự thay đổi dữ liệu gốc | Quản lý mapping/tokens riêng |

Theo tài liệu Spring Security 6.5, **HTTP request authorization** có hỗ trợ role hierarchy, còn **pre/post method security** cần kết nối hierarchy với `MethodSecurityExpressionHandler` cho cách dùng biểu thức trong bài.

### Vì sao phải nói rõ phạm vi?

Giả sử HTTP rule cho Alice ADMIN vào endpoint USER, nhưng controller gọi một service được kiểm bằng custom manager chỉ đọc `authentication.getAuthorities()` theo literal `ROLE_USER` mà không áp dụng hierarchy. Khi đó HTTP có thể ALLOW nhưng service vẫn DENY.

Kết luận đúng không phải “hierarchy bị hỏng”, mà là hai **điểm kiểm quyền khác nhau** chưa dùng cùng mô hình. Một ứng dụng có nhiều filter chain, method interceptors hoặc custom managers phải kiểm chứng từng tầng.

## 7. Cấu hình Spring Boot Java 17+ hoàn chỉnh: HTTP và method cùng hiểu hierarchy

Bài demo dùng **một SecurityFilterChain**, **bốn tài khoản** và một hierarchy. Các endpoint chỉ dùng GET để tập trung vào kế thừa role; không có thao tác thay đổi dữ liệu.

### 7.1. Tạo project

Dùng Spring Initializr hoặc Maven project Spring Boot **3.5.x**, Java **17+**, với:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` và `spring-security-test` cho test scope.

Nếu dùng Maven wrapper từ Initializr, có thể chạy `./mvnw spring-boot:run`. Không cần database. Project này không nên được dùng trực tiếp trong production vì có tài khoản/mật khẩu mẫu.

### 7.2. Main class và cấu hình security

Tạo tệp **`src/main/java/com/example/hierarchy/HierarchyApplication.java`**:

~~~java
package com.example.hierarchy;

import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
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
public class HierarchyApplication {

    public static void main(String[] args) {
        SpringApplication.run(HierarchyApplication.class, args);
    }

    // Chỉ khai báo một lần quan hệ ADMIN > MANAGER > USER.
    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\n"
          + "ROLE_MANAGER > ROLE_USER"
        );
    }

    // Method-security SpEL phải sử dụng cùng hierarchy.
    // static @Bean để đăng ký trước cấu hình method security.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/manager/**").hasRole("MANAGER")
                .requestMatchers("/api/user/**").hasRole("USER")
                .requestMatchers(
                    "/api/method/**", "/api/whoami", "/api/reachable"
                ).authenticated()
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
        // Không cấp lặp MANAGER và USER cho Alice.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();

        // Không cấp lặp USER cho Bob.
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("MANAGER")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("USER")
            .build();

        // Quyền không nằm trong đồ thị role:
        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .authorities("report:read")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    @RestController
    static class Api {
        private final TeamService service;
        private final RoleHierarchy hierarchy;

        Api(TeamService service, RoleHierarchy hierarchy) {
            this.service = service;
            this.hierarchy = hierarchy;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/admin/settings")
        String admin() {
            return "admin settings";
        }

        @GetMapping("/api/manager/review")
        String manager() {
            return "manager review";
        }

        @GetMapping("/api/user/dashboard")
        String user() {
            return "user dashboard";
        }

        @GetMapping("/api/method/admin")
        String methodAdmin() {
            return service.admin();
        }

        @GetMapping("/api/method/manager")
        String methodManager() {
            return service.manager();
        }

        @GetMapping("/api/method/user")
        String methodUser() {
            return service.user();
        }

        // Chỉ hiển thị authority cấp trực tiếp, không tự nhân bản.
        @GetMapping("/api/whoami")
        String whoami(Authentication authentication) {
            String direct = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + direct;
        }

        // Hiển thị tập hiệu lực do hierarchy suy diễn.
        @GetMapping("/api/reachable")
        String reachable(Authentication authentication) {
            String derived = hierarchy
                .getReachableGrantedAuthorities(
                    authentication.getAuthorities()
                )
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + derived;
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "must not be reached";
        }
    }

    @Service
    static class TeamService {

        @PreAuthorize("hasRole('ADMIN')")
        public String admin() {
            return "method admin";
        }

        @PreAuthorize("hasRole('MANAGER')")
        public String manager() {
            return "method manager";
        }

        @PreAuthorize("hasRole('USER')")
        public String user() {
            return "method user";
        }
    }
}
~~~

### 7.3. Đọc kỹ ba phần thiết yếu

**Thứ nhất — chỉ cấp role trực tiếp:** Alice được xây bằng `roles("ADMIN")`, nên danh sách `Authentication#getAuthorities()` của cô ấy chứa **`ROLE_ADMIN`**, không chứa ba dòng authority được nhân bản. Bob chỉ có `ROLE_MANAGER` và Carol chỉ có `ROLE_USER`.

**Thứ hai — một bean hierarchy làm nguồn:** `roleHierarchy()` dùng đúng hai cạnh, Spring Security suy diễn ADMIN → USER bắc cầu. Không phải xây từng dòng `ROLE_ADMIN > ROLE_USER`.

**Thứ ba — hai điểm enforcement khác nhau:**

- HTTP `authorizeHttpRequests(...).hasRole("MANAGER")` kiểm tra role trong request authorization, sử dụng hierarchy theo cấu hình tích hợp.
- Method `@PreAuthorize("hasRole('MANAGER')")` dùng `DefaultMethodSecurityExpressionHandler` đã được đặt `setRoleHierarchy(roleHierarchy)`.
- HTTP dành cho `/api/method/**` chỉ yêu cầu `authenticated()`, để kết quả 403 của role được chứng minh đến từ **method security**.

### 7.4. Vì sao gọi service từ controller thay vì gọi nội bộ?

Method security dựa trên Spring AOP proxy trong cấu hình phổ biến. Ở ví dụ, `Api` nhận Spring bean `TeamService` rồi gọi method public có `@PreAuthorize`. Nếu trong cùng class service dùng `this.manager()` (self-invocation), lời gọi nội bộ có thể **không đi qua proxy**, dẫn tới bỏ qua interceptor. Đừng dùng self-invocation để kết luận hierarchy hoặc `@PreAuthorize` đã hoạt động.

### 7.5. Vai trò ROLE_ADMIN không đồng nghĩa có mọi permission

`RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_USER")` chỉ định nghĩa bao hàm **hai role thấp hơn**. Nó không tự cấp `docs:read`, `report:write` hoặc quyền trên mọi document.

Một chức năng báo cáo đòi `hasAuthority("report:read")` sẽ cần authority đó được cấp hoặc được suy diễn qua hierarchy **được khai báo tường minh**. Mô hình không suy luận rằng `ADMIN` luôn tương đương “được làm bất cứ điều gì”.

## 8. Kiểm thử thủ công: so sánh trực tiếp và kế thừa

### 8.1. Khởi động

Tại thư mục root của project Maven:

~~~bash
# macOS / Linux:
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt:
mvnw.cmd spring-boot:run
~~~

Khi ứng dụng chạy ở cổng mặc định 8080:

~~~bash
# Public:
curl -i http://localhost:8080/public/ping

# Kiểm tra role gốc và role hiệu lực:
curl -i -u alice:demo123 http://localhost:8080/api/whoami
curl -i -u alice:demo123 http://localhost:8080/api/reachable
curl -i -u bob:demo456 http://localhost:8080/api/whoami
curl -i -u bob:demo456 http://localhost:8080/api/reachable

# HTTP role checks:
curl -i -u alice:demo123 http://localhost:8080/api/user/dashboard
curl -i -u alice:demo123 http://localhost:8080/api/manager/review
curl -i -u alice:demo123 http://localhost:8080/api/admin/settings
curl -i -u bob:demo456 http://localhost:8080/api/admin/settings
curl -i -u carol:demo789 http://localhost:8080/api/manager/review

# Method security:
curl -i -u alice:demo123 http://localhost:8080/api/method/user
curl -i -u bob:demo456 http://localhost:8080/api/method/manager
curl -i -u bob:demo456 http://localhost:8080/api/method/admin
curl -i -u dave:demo000 http://localhost:8080/api/method/user
~~~

**Kỳ vọng body của endpoint inspect:**

| Request | Body |
| --- | --- |
| Alice `GET /api/whoami` | `alice:ROLE_ADMIN` |
| Alice `GET /api/reachable` | `alice:ROLE_ADMIN,ROLE_MANAGER,ROLE_USER` |
| Bob `GET /api/whoami` | `bob:ROLE_MANAGER` |
| Bob `GET /api/reachable` | `bob:ROLE_MANAGER,ROLE_USER` |
| Carol `GET /api/reachable` | `carol:ROLE_USER` |
| Dave `GET /api/reachable` | `dave:report:read` |

Đây là minh chứng quan trọng: **Alice được kiểm như một MANAGER và USER dù authority trực tiếp của Alice vẫn chỉ là ROLE_ADMIN**. Kết quả `/api/reachable` được chính ứng dụng demo tính bằng `RoleHierarchy`; nó không phải một header do Spring Security tự phát hành.

### 8.2. Ma trận quyền HTTP

| User | `/api/admin/settings` | `/api/manager/review` | `/api/user/dashboard` |
| --- | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 |
| Alice — ADMIN | **200** | **200** | **200** |
| Bob — MANAGER | 403 | **200** | **200** |
| Carol — USER | 403 | 403 | **200** |
| Dave — chỉ `report:read` | 403 | 403 | 403 |

Ma trận dựa trên HTTP Basic trong ứng dụng mẫu. Khi chưa có credential trên route bảo vệ, kết quả thông thường là **401**; khi đã xác thực mà thiếu quyền là **403**. Với form login, anonymous có thể nhận redirect (302) thay vì 401.

### 8.3. Ma trận quyền method security

| User | `/api/method/admin` | `/api/method/manager` | `/api/method/user` |
| --- | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 |
| Alice — ADMIN | **200** | **200** | **200** |
| Bob — MANAGER | 403 | **200** | **200** |
| Carol — USER | 403 | 403 | **200** |
| Dave — chỉ `report:read` | 403 | 403 | 403 |

**Hai ma trận phải nhất quán.** Nếu HTTP cho Alice vào manager nhưng method lại trả 403, kiểm tra method expression handler có dùng `RoleHierarchy`, và request có thực sự gọi qua Spring-managed service proxy.

### 8.4. Những trường hợp không được lẫn lộn

- `ROLE_ADMIN > ROLE_MANAGER > ROLE_USER` không mang ý nghĩa `ROLE_USER > ROLE_ADMIN`.
- `authenticated()` không đồng nghĩa `hasRole("USER")`: Dave đã đăng nhập nên vào được `/api/whoami`, nhưng không vào được `/api/user/dashboard`.
- `hasRole("USER")` theo prefix mặc định không giống `hasAuthority("USER")`; nó kiểm authority `ROLE_USER` (có thể được kế thừa nếu consumer dùng hierarchy).
- `@PreAuthorize` chỉ có hiệu lực nếu method security được bật và lời gọi đi qua cơ chế interceptor phù hợp.
- Tầng HTTP ALLOW không có nghĩa bỏ qua domain policy; tài liệu thuộc tenant khác vẫn phải được chặn.

## 9. Tự động kiểm chứng bằng Spring Security Test + MockMvc

### 9.1. Dependencies test

Trong `pom.xml`, kiểm tra đã có hai dependency test (không thêm trùng):

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

Đây là fragment XML nằm bên trong `<dependencies>` của POM. Spring Boot BOM/parent quản lý các version tương thích.

### 9.2. Bộ test đầy đủ cho thứ tự vai trò

Tạo tệp **`src/test/java/com/example/hierarchy/HierarchyApplicationTests.java`**:

~~~java
package com.example.hierarchy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HierarchyApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // principal,password,path,expected HTTP status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/admin/settings,401",
        "anonymous,none,/api/manager/review,401",
        "anonymous,none,/api/user/dashboard,401",
        "anonymous,none,/api/method/user,401",

        "alice,demo123,/api/admin/settings,200",
        "alice,demo123,/api/manager/review,200",
        "alice,demo123,/api/user/dashboard,200",
        "alice,demo123,/api/method/admin,200",
        "alice,demo123,/api/method/manager,200",
        "alice,demo123,/api/method/user,200",

        "bob,demo456,/api/admin/settings,403",
        "bob,demo456,/api/manager/review,200",
        "bob,demo456,/api/user/dashboard,200",
        "bob,demo456,/api/method/admin,403",
        "bob,demo456,/api/method/manager,200",
        "bob,demo456,/api/method/user,200",

        "carol,demo789,/api/admin/settings,403",
        "carol,demo789,/api/manager/review,403",
        "carol,demo789,/api/user/dashboard,200",
        "carol,demo789,/api/method/admin,403",
        "carol,demo789,/api/method/manager,403",
        "carol,demo789,/api/method/user,200",

        "dave,demo000,/api/admin/settings,403",
        "dave,demo000,/api/manager/review,403",
        "dave,demo000,/api/user/dashboard,403",
        "dave,demo000,/api/method/admin,403",
        "dave,demo000,/api/method/manager,403",
        "dave,demo000,/api/method/user,403"
    })
    void roleMatrix(String principal, String password,
                    String path, int expectedStatus)
            throws Exception {
        MockHttpServletRequestBuilder request = get(path);

        if (!"anonymous".equals(principal)) {
            request.with(httpBasic(principal, password));
        }

        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void adminHasOnlyOneDirectAuthority() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_ADMIN"));
    }

    @Test
    void adminInheritsManagerAndUserTransitively() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "alice:ROLE_ADMIN,ROLE_MANAGER,ROLE_USER"
            ));
    }

    @Test
    void managerInheritsUserButNotAdmin() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "bob:ROLE_MANAGER,ROLE_USER"
            ));

        mvc.perform(get("/api/admin/settings")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void plainUserNeverGetsManagerRole() throws Exception {
        mvc.perform(get("/api/manager/review")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/user/dashboard")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());
    }

    @Test
    void unrelatedAuthorityDoesNotInheritAnyRole() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("dave:report:read"));

        mvc.perform(get("/api/method/user")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fallbackDeniesEvenAdmin() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/user/dashboard")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Vì sao test như vậy?**

- Kiểm **đủ cả hai chiều**: Alice vào manager/user được (kế thừa xuống) nhưng Bob không vào admin và Carol không vào manager (không kế thừa ngược).
- Kiểm **trực tiếp vs hiệu lực**: `/api/whoami` chỉ có `ROLE_ADMIN`, trong khi `/api/reachable` có ba role. Nếu code cấp lặp role cho Alice thay vì dùng hierarchy, test direct authority sẽ phát hiện.
- Kiểm **HTTP và method** cùng lúc: không giả định một nơi chạy đúng thì nơi khác tự chạy đúng.
- Kiểm **không liên quan**: Dave chỉ có `report:read`, không được role nào từ hierarchy.
- Kiểm **fallback**: endpoint không có allow rule không được mở, kể cả với ADMIN.
- Kiểm **mật khẩu sai**: tách authentication 401 với authorization 403.

`httpBasic(...)` thực sự đưa Basic credential vào MockMvc request, khác với `@WithMockUser` vốn dựng sẵn danh tính kiểm thử. Vì vậy test này còn đi qua `UserDetailsService` demo và cơ chế ánh xạ `roles(...)`. Nếu test role hierarchy riêng bằng `@WithMockUser(roles = "ADMIN")` cũng được, nhưng đừng dùng nó để khẳng định credential/mapper của ứng dụng đã đúng.

### 9.3. Chạy test

~~~bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

Kỳ vọng: các ca đều pass khi dùng đúng dependencies và cấu hình được trình bày. Log, thời gian test, version Maven/Surefire và tên báo cáo phụ thuộc môi trường; phải dựa vào kết quả chạy thật, không bịa trước output test.

**Không bỏ test âm tính.** Nếu cấu hình vô tình cho mọi user vào `/api/manager/**`, test Alice 200 sẽ vẫn pass, nhưng test Carol 403 sẽ phát hiện lỗi.

## 10. Chỉ dùng hierarchy ở HTTP hay method — có hệ quả gì?

### 10.1. Nếu chỉ tạo `RoleHierarchy` bean và bật HTTP rules

Trong Spring Security 6.5, tài liệu hướng dẫn dùng bean `RoleHierarchy` để hỗ trợ `authorizeHttpRequests`. Tuy nhiên, nếu ứng dụng còn dùng `@PreAuthorize`, cần xem `MethodSecurityExpressionHandler`. Vì thế ví dụ ở mục 7 cố ý đăng ký **cả hai**:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy(
        "ROLE_ADMIN > ROLE_MANAGER\n"
      + "ROLE_MANAGER > ROLE_USER"
    );
}

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy hierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(hierarchy);
    return handler;
}
~~~

Hai method ở trên là **fragment** đã xuất hiện trong app đầy đủ. Không khai báo thêm lần thứ hai nếu project đã có.

### 10.2. Nếu tự tạo `AuthorityAuthorizationManager`

Ví dụ một custom policy dùng static factory:

~~~java
import org.springframework.security.authorization.AuthorityAuthorizationManager;

// Fragment: manager do ứng dụng tự tạo.
var manager = AuthorityAuthorizationManager
    .<Object>hasRole("USER");

// Bảo đảm manager này dùng hierarchy đã được inject.
manager.setRoleHierarchy(roleHierarchy);
~~~

Đây là **fragment**, biến `roleHierarchy` cần là bean `RoleHierarchy` đang sử dụng trong app. `AuthorityAuthorizationManager` có `setRoleHierarchy(...)`; **một instance tự tạo** không được giả định tự nhận bean chỉ vì cùng ApplicationContext. Khi sử dụng custom `AuthorizationManager` của riêng bạn, phải thiết kế chính xác dữ liệu đầu vào và cách mở rộng effective authorities.

### 10.3. Với `@Secured` và `@RolesAllowed`

Spring Security 6.5 có thể kết hợp role hierarchy với các dạng method authorization khác, nhưng cần bật các interceptor tương ứng:

~~~java
// Fragment annotation thay thế @EnableMethodSecurity mặc định:
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

`@Secured("ROLE_USER")` dùng role/authority literal; `@RolesAllowed("USER")` theo JSR-250 có cơ chế prefix riêng. Không suy luận chỉ từ tên annotation rằng mọi cấu hình custom prefix hoặc manager đều giống `@PreAuthorize("hasRole('USER')")`. Kiểm thử từng nhóm, đặc biệt khi nâng phiên bản.

## 11. Khi có quyền nghiệp vụ riêng: role có thể bao hàm authority khác

Mô hình ADMIN > MANAGER > USER giải quyết việc **bao hàm role**. Nếu ứng dụng có quyền cụ thể `task:read` hoặc `task:approve`, có thể mở rộng đồ thị để role bao hàm các authority đó:

~~~java
RoleHierarchy hierarchy = RoleHierarchyImpl.fromHierarchy(
    "ROLE_ADMIN > ROLE_MANAGER\n"
  + "ROLE_MANAGER > ROLE_USER\n"
  + "ROLE_MANAGER > task:approve\n"
  + "ROLE_USER > task:read"
);
~~~

Đây là **fragment**, phù hợp khi chính sách yêu cầu:

- USER được phép `task:read`.
- MANAGER được phép cả `task:approve` và `task:read`.
- ADMIN kế thừa toàn bộ quyền này qua MANAGER.

**Lưu ý về mô hình:** `RoleHierarchy` làm việc trên chuỗi authorities, không phân biệt rằng `ROLE_MANAGER` là “role” còn `task:approve` là “permission” nếu bạn tự khai báo cạnh đó. Cần naming convention và quản trị thay đổi rõ ràng. Trong các hệ thống lớn, ánh xạ role → permission tại tầng quản lý identity/quyền hoặc database có thể phù hợp hơn để quản trị, nhưng phải tránh phát hành/đồng bộ dữ liệu dư thừa không kiểm soát.

Một hệ thống multi-tenant không nên coi `ROLE_MANAGER` toàn cục là quyền phê duyệt của **mọi tenant**. Có thể cần scoped authorities, policy theo tenant hoặc kiểm tra domain-level tùy yêu cầu.

## 12. Không nhầm kế thừa vai trò với quyền trên tài nguyên

Role hierarchy trả lời: **user có role/authority hiệu lực nào?** Nó **không** tự giải quyết:

- Người dùng chỉ được xem tài liệu thuộc tenant nào.
- Một manager có được duyệt công việc do chính mình tạo hay không.
- Bản ghi đang ở trạng thái cho phép sửa hay đã khóa.
- Tài liệu có được chia sẻ cho user cụ thể hay không.
- Người dùng có được phép thao tác với project có ID nhất định không.

Ví dụ cả Alice ADMIN và Bob MANAGER có thể thỏa `hasRole("MANAGER")`, nhưng nếu task 42 thuộc tenant khác, vẫn phải **DENY** theo policy tài nguyên. Khi viết service:

~~~java
// Fragment minh họa: cần kết hợp role và policy trên đối tượng.
@PreAuthorize("hasRole('MANAGER') and @taskPolicy.canApprove(authentication, #taskId)")
public void approveTask(Long taskId) {
    // Business logic: kiểm tra trạng thái, transaction, audit.
}
~~~

Đây là **fragment**, không phải code tự chạy độc lập: cần bean `taskPolicy` và implementation service tương ứng; nếu chỉ copy annotation mà không có bean đó, ứng dụng sẽ lỗi. Trong sản phẩm thật, đặt tên tham số cho SpEL rõ ràng hoặc dùng `@P` nếu môi trường biên dịch không giữ parameter names.

**Giữ nguyên tắc least privilege:** kế thừa role thấp không biến role cao thành “bypass mọi quy tắc” nếu chính sách dữ liệu hoặc phân tách nhiệm vụ nói khác.

## 13. Lỗi triển khai phổ biến và cách phát hiện

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Cấp Alice đồng thời `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER` chỉ để kế thừa | Dữ liệu cấp quyền dư thừa, khó sửa đồng bộ | Lưu role cao nhất cần thiết, dùng hierarchy tại authorization |
| Viết `ROLE_ADMIN > ROLE_USER` nhưng quên `ROLE_MANAGER > ROLE_USER` | Bob MANAGER không được nhận USER | Khai báo các cạnh thực tế, test tính bắc cầu |
| Viết cạnh ngược `ROLE_USER > ROLE_ADMIN` | USER có thể được nâng quyền | Rà soát hướng dấu `>` |
| Tạo vòng ADMIN → MANAGER → USER → ADMIN | Mô hình không hợp lệ, có thể lỗi lúc tạo hierarchy | Dùng đồ thị không chu trình |
| Chỉ tạo bean hierarchy, không cấu hình method expression handler | HTTP và method có thể cho kết quả khác | Dùng static bean handler với `setRoleHierarchy(...)` và test hai tầng |
| Tự tạo `AuthorityAuthorizationManager` rồi quên `setRoleHierarchy` | Custom manager không kế thừa role | Inject và cấu hình hierarchy |
| Dùng `roles("ROLE_ADMIN")` | Builder không chấp nhận tên role đã có tiền tố | Dùng `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")` |
| Dùng prefix custom nhưng hierarchy vẫn viết `ROLE_` | Authority dữ liệu không khớp policy | Đồng bộ cách cấp và cách kiểm |
| Coi role cao tự có quyền mọi bản ghi | Lỗ hổng tenant/ownership/IDOR | Bổ sung domain authorization |
| Chỉ test admin được ALLOW | Không phát hiện user thường được nâng quyền | Test manager/USER bị DENY trên rule cao hơn |
| Giả định hierarchy sửa JWT/Authentication | Debug sai và dữ liệu không như kỳ vọng | Phân biệt direct authorities và reachable authorities |
| Thay đổi hierarchy không đánh giá tác động | Phạm vi cấp quyền rộng hơn dự tính | Review đồ thị, test regression và audit |

### Một checklist trước khi đưa vào production

1. **Sơ đồ vai trò** đã được người phụ trách nghiệp vụ xác nhận chưa? Mỗi cạnh `A > B` là một **quyết định cấp quyền quan trọng**.
2. **Thứ tự và hướng** các cạnh đã đúng? Có vòng lặp hoặc quan hệ đặc biệt bị hiểu lầm không?
3. **Các điểm enforcement** (HTTP, method, custom manager) có dùng cùng hierarchy theo phiên bản framework đang chạy không?
4. **UserDetailsService/JWT converter** cấp authority trực tiếp đúng tên, đúng prefix, không trùng lặp vô ích?
5. **Bảng kiểm thử phủ định** có chứng minh USER không thành MANAGER và MANAGER không thành ADMIN không?
6. **Tài nguyên nhiều tenant/owner** có kiểm quyền theo object instance độc lập với role không?
7. **Khi thu hồi role hoặc đổi hierarchy**, cache/session/token được xử lý ra sao? Có dữ liệu quyền cũ cần cập nhật không?
8. **Theo dõi 403 và audit** sau khi triển khai thay đổi quyền đã được thiết kế chưa?

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Đồ thị `ROLE_ADMIN > ROLE_MANAGER` và `ROLE_MANAGER > ROLE_USER` cho ADMIN bao hàm gì?  
**Đáp án:** ADMIN, MANAGER và USER, nhờ quan hệ bao hàm bắc cầu.

**Câu 2.** Có cần thêm `ROLE_ADMIN > ROLE_USER` không?  
**Đáp án:** Không. Cạnh ADMIN → USER đã được suy diễn qua MANAGER.

**Câu 3.** Có nên lưu ba dòng role trực tiếp cho Alice ADMIN chỉ để truy cập màn hình USER?  
**Đáp án:** Không cần. Chỉ cấp `ROLE_ADMIN`, dùng hierarchy khi authorization.

**Câu 4.** `Authentication#getAuthorities()` của Alice tự tăng thành ba role không?  
**Đáp án:** Không mặc định. Hierarchy mở rộng **effective authorities khi kiểm quyền**, không nhất thiết sửa danh sách cấp trực tiếp.

**Câu 5.** MANAGER có được vào endpoint chỉ dành cho ADMIN không?  
**Đáp án:** Không, vì không có quan hệ kế thừa ngược.

**Câu 6.** Alice ADMIN gọi method `@PreAuthorize("hasRole('USER')")` bị 403 dù HTTP cho vào. Kiểm tra gì?  
**Đáp án:** `@EnableMethodSecurity`, method expression handler có `setRoleHierarchy(...)`, lời gọi có qua Spring bean/proxy không, và authority cấp trực tiếp có đúng `ROLE_ADMIN` không.

**Câu 7.** Dave chỉ có `report:read`, có tự trở thành USER không?  
**Đáp án:** Không, vì authority đó không có cạnh nối tới `ROLE_USER` trong đồ thị.

**Câu 8.** Có thể khai báo `ROLE_USER > task:read` không?  
**Đáp án:** Có, nếu chính sách muốn role USER bao hàm authority `task:read` và consumer dùng hierarchy. Cần thống nhất naming và phạm vi.

**Câu 9.** ADMIN bao hàm MANAGER có tự được duyệt task thuộc tenant khác không?  
**Đáp án:** Không. Cần domain-level policy kiểm tenant, owner, trạng thái và phạm vi thao tác.

**Câu 10.** Vì sao phải test Bob không được vào admin và Carol không được vào manager?  
**Đáp án:** Vì test ALLOW một chiều chưa chứng minh hệ thống không có lỗ hổng **nâng quyền ngược**.

**Ghi nhớ:** Hãy lưu **role trực tiếp**, khai báo `ROLE_ADMIN > ROLE_MANAGER` và `ROLE_MANAGER > ROLE_USER`, để `RoleHierarchy` suy ra quyền **bắc cầu** tại nơi kiểm tra. Cách này tránh nhân bản role và tránh lặp OR trong từng rule, nhưng vẫn phải cấu hình **đúng từng tầng authorization** và bảo vệ **quyền trên tài nguyên cụ thể**.

## Tài liệu chính thức

- Spring Security 6.5 — Authorization Architecture / Hierarchical Roles: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Method Security / Customizing Expression Handling: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — `RoleHierarchy` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchy.html
- Spring Security 6.5 — `RoleHierarchyImpl` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 6.5 — `AuthorityAuthorizationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 6.5 — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
