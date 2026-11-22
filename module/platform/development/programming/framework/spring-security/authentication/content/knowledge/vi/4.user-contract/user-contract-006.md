# Ánh xạ quyền nghiệp vụ thành GrantedAuthority

> **Ngữ cảnh:** Spring Security – authentication, phần **Hợp đồng người dùng**. Bài học trình bày cách chuyển role và permission từ mô hình nghiệp vụ sang `GrantedAuthority` để Spring Security dùng trong `Authentication` và authorization. Trọng tâm là nơi phát sinh dữ liệu quyền, quy tắc chuyển đổi, điểm tích hợp với `UserDetailsService`, và kiểm chứng kết quả. Ví dụ Java 17+ sử dụng Spring Boot Servlet với username/password. Các nguyên tắc nguồn tin cậy, tối thiểu quyền và cập nhật quyền cũng áp dụng khi ứng dụng dùng JWT/OIDC, nhưng cách tích hợp sẽ khác.

## 1. Bài toán: hệ thống nghiệp vụ quản lý quyền, Spring Security cần authority

Ứng dụng quản lý báo cáo và hóa đơn có thể có ba nhóm chức năng:

- Xem báo cáo khi có quyền nghiệp vụ `report:read`.
- Thực hiện duyệt hóa đơn khi có `invoice:approve`.
- Xem trang quản trị khi mang role `ADMIN`.

Dữ liệu nghiệp vụ có thể lưu role theo mã `ANALYST`, `APPROVER`, `ADMIN`; mỗi role được cấu hình các permission tương ứng. Trong khi đó, Spring Security quyết định truy cập qua `Authentication.getAuthorities()` và những rule như `hasAuthority("report:read")` hoặc `hasRole("ADMIN")`.

Hai bên cần một **hợp đồng ánh xạ**:

```text
Nguồn quyền nghiệp vụ do server quản lý
    |
    +-- user_roles: USER, ANALYST
    +-- role_permissions: ANALYST -> report:read
    +-- user_permissions: một số quyền được cấp trực tiếp
    |
    v
Quy trình nạp tài khoản và ánh xạ có kiểm soát
    |
    +-- ROLE_USER
    +-- ROLE_ANALYST
    +-- report:read
    |
    v
Collection<GrantedAuthority> của UserDetails
    |
    v
AuthenticationProvider kiểm tra credential thành công
    |
    v
Authentication.getAuthorities() của request
    |
    v
AuthorizationManager / method security / policy nghiệp vụ
```

**`GrantedAuthority` không phải bảng quyền, không xác thực người dùng, cũng không tự quyết định toàn bộ quyền truy cập.** Nó là một cách biểu diễn quyền đã cấp mà Spring Security có thể so khớp với chính sách. Quyết định cuối cùng còn phụ thuộc vào rule, tài nguyên, tenant và ngữ cảnh.

Ví dụ, role `ANALYST` trong database không tự động trở thành `ROLE_ANALYST` trong `Authentication` chỉ vì tên giống nhau. Ứng dụng hoặc provider phải thực hiện mapping đúng. Tương tự, nếu `ANALYST` được cấp `report:read`, phải quyết định rõ có chuyển quyền này thành authority riêng hay triển khai role hierarchy/policy tương đương.

## 2. Phân biệt role, permission, authority và quyền trên đối tượng

| Khái niệm | Nơi quản lý điển hình | Ví dụ | Dùng để làm gì? |
| --- | --- | --- | --- |
| **Role** | Hệ thống người dùng/RBAC | `USER`, `ANALYST`, `ADMIN` | Nhóm trách nhiệm hoặc cách cấp quyền cho nhiều user |
| **Permission** | Chính sách nghiệp vụ | `report:read`, `invoice:approve` | Khả năng thao tác cụ thể |
| **GrantedAuthority** | `UserDetails` / `Authentication` sau mapping | `ROLE_ANALYST`, `report:read` | Giá trị mà Spring Security so với authorization rule |
| **Scope** | Authorization server/token | `orders.read` | Phạm vi được cấp cho token/client; có thể ánh xạ thành `SCOPE_orders.read` |
| **Quyền trên đối tượng** | Policy/service/DB query | “Được xem báo cáo thuộc tenant A” | Kiểm tra một bản ghi/tập dữ liệu cụ thể |

`GrantedAuthority` là interface có phương thức `String getAuthority()`. Implementation thường dùng là `SimpleGrantedAuthority`, giữ một chuỗi không rỗng, chẳng hạn:

```java
GrantedAuthority authority = new SimpleGrantedAuthority("report:read");
System.out.println(authority.getAuthority()); // report:read
```

Đây là **đoạn mã minh họa**, cần import `org.springframework.security.core.GrantedAuthority` và `org.springframework.security.core.authority.SimpleGrantedAuthority` trong project có Spring Security. Chưa đủ làm chương trình chạy độc lập.

### `hasAuthority` và `hasRole` khác nhau

Với quy ước role prefix mặc định:

| Rule | Chuỗi `GrantedAuthority.getAuthority()` mà rule tìm |
| --- | --- |
| `hasAuthority("report:read")` | Chính xác `report:read` |
| `hasAuthority("ROLE_ADMIN")` | Chính xác `ROLE_ADMIN` |
| `hasRole("ADMIN")` | `ROLE_ADMIN` theo tiền tố mặc định |
| `hasAuthority("ADMIN")` | Chính xác `ADMIN`, **khác** `ROLE_ADMIN` |

Spring Security cho phép tùy biến prefix/authorization conventions; khi đó hãy kiểm tra đồng bộ cấu hình trên web và method security. Trong bài này giữ `ROLE_` mặc định để tránh mơ hồ.

**Một role không tự động bao hàm mọi permission:** `ROLE_ADMIN` không mặc nhiên thỏa `hasAuthority("report:read")`; muốn vậy phải cấp thêm `report:read`, cấu hình role hierarchy phù hợp, hoặc dùng policy riêng. Không nên đoán rằng chữ “ADMIN” tự vượt qua mọi authorization rule.

## 3. Thiết kế một hợp đồng cấp quyền đủ rõ

Giả sử policy nghiệp vụ là:

| Role nội bộ | Authorities kết quả từ role |
| --- | --- |
| `USER` | `ROLE_USER` |
| `ANALYST` | `ROLE_ANALYST`, `report:read` |
| `APPROVER` | `ROLE_APPROVER`, `invoice:approve` |
| `ADMIN` | `ROLE_ADMIN` |

Ngoài quyền do role cấp, có thể có quyền cá nhân được cấp trực tiếp. Hệ thống cần thống nhất quy tắc:

1. **Role được cấp** tạo authority dạng `ROLE_<CODE>`, ví dụ `ANALYST` -> `ROLE_ANALYST`.
2. **Permission của role** được triển khai thành authority cụ thể, ví dụ `report:read`.
3. **Permission trực tiếp** được hợp nhất với permission từ role.
4. **Trùng quyền** được loại bỏ, tránh nhiều lần `report:read` nếu đến từ cả role và direct grant.
5. **Dữ liệu lạ hoặc sai contract** không được tự chuyển thành quyền có sức mạnh bất ngờ. Cần kiểm tra role/permission hợp lệ và xử lý “fail closed”.
6. **Thứ tự authority** nên ổn định khi log hoặc kiểm thử; permission thực chất là một tập, thứ tự hiển thị không mang ý nghĩa quyền cao/thấp.
7. **Không dùng trường request chưa tin cậy làm nguồn cấp quyền**, kể cả request mang `role`, `permissions` hoặc `X-Role`.
8. **Không tự thêm “ADMIN có mọi quyền”** nếu chính sách nội bộ chưa định nghĩa điều đó.

Một công thức khái niệm:

\[
Authorities(user) =
RoleAuthorities(userRoles)
\;\cup\;
RolePermissions(userRoles)
\;\cup\;
DirectPermissions(user)
\]

Phép hợp ở đây là hợp các chuỗi authority hợp lệ. Nó **không tự quyết định** hạn quyền theo tenant, đối tượng dữ liệu, trạng thái tài khoản, thời hạn hiệu lực hoặc điều kiện nghiệp vụ; các yếu tố ấy vẫn cần được kiểm tra đúng chỗ.

### “Deny” và điều kiện theo ngữ cảnh

Nếu hệ thống có explicit deny, deny phải có ưu tiên phù hợp trong policy. Chỉ hợp các quyền cho phép rồi đưa vào `GrantedAuthority` có thể **làm mất thông tin cấm**. Trường hợp chính sách có conflict/deny, nên tính hiệu lực quyền trong một policy service/authorization manager có thể hiểu đầy đủ điều kiện, hoặc dùng một hợp đồng mapping đã xử lý deny chính xác. Không tự biến deny thành một chuỗi `DENY_*` rồi kỳ vọng `hasAuthority` tự biết cách từ chối.

Tương tự, quyền “đọc báo cáo của phòng ban mình” không thể được quyết định hoàn chỉnh bằng `report:read` nếu thiếu thông tin phòng ban/báo cáo. Phần kiểm tra quyền đối tượng nên diễn ra sau khi có principal đáng tin và tài nguyên thật.

## 4. Vị trí mapping trong luồng username/password

Với `DaoAuthenticationProvider`, luồng điển hình:

1. Filter nhận username/password do client gửi; credential **chưa đáng tin**.
2. `AuthenticationManager` chọn provider phù hợp.
3. `DaoAuthenticationProvider` dùng `UserDetailsService.loadUserByUsername(...)` lấy dữ liệu user từ nguồn tin cậy. `UserDetails` được trả có password hash, trạng thái account và collection authorities.
4. `DaoAuthenticationProvider` kiểm tra điều kiện tài khoản và mật khẩu qua `PasswordEncoder`. Nếu thất bại, **không có** `Authentication` thành công cho request.
5. Nếu hợp lệ, provider tạo authenticated `Authentication` chứa principal và authorities thích hợp. Một số phiên bản Spring Security còn bổ sung authority nội bộ phục vụ chức năng framework như `FACTOR_PASSWORD`; không dùng danh sách raw một cách võ đoán để suy ra chỉ có các authority nghiệp vụ.
6. `SecurityContext` đưa kết quả đến authorization/controller/service theo vòng đời request và cơ chế session/token.

**Điểm tinh tế:** Việc tải/mapping quyền **có thể xảy ra trước bước so khớp password**, vì nó là một phần của việc tải `UserDetails`. Nhưng authority ấy **chỉ trở thành quyền của người gọi hiện tại sau khi xác thực thành công**. Không đọc quyền dựa trên một username tự khai rồi sử dụng ngay ở business service.

`UserDetailsService` không cần tự gọi `SecurityContextHolder.setContext(...)` hay tự đánh dấu token đã xác thực. Hãy để authentication mechanism chịu trách nhiệm đó.

### Vì sao nên tách domain model và `UserDetails`?

Domain model có thể chứa user ID, email, quan hệ database, nhiều role và permission, audit timestamps hoặc chính sách nghiệp vụ khác. `UserDetails` chỉ cần những phần phù hợp cho authentication contract, như username, password hash, account flags và authorities.

Một thiết kế thường dùng:

```text
DomainUser (persistence/domain)
   username, passwordHash, enabled, roleCodes, directPermissionCodes
                   |
                   v
AuthorityMapper (quy tắc nghiệp vụ -> tên authority hợp lệ)
                   |
                   v
UserDetailsAdapter
   username, passwordHash, enabled, Collection<GrantedAuthority>
                   |
                   v
DaoAuthenticationProvider
                   |
                   v
Authentication + SecurityContext
```

Không phải mọi hệ thống đều cần tự viết `UserDetails`; `User.withUsername(...)` đã đủ cho nhiều trường hợp. Tránh đưa nguyên JPA entity hoặc password thô vào principal và tránh để business layer phụ thuộc trực tiếp vào entity của authentication.

## 5. Thuật toán mapping thực tế

Dữ liệu đầu vào mà mapper được phép xử lý phải do server tải và kiểm soát. Trong ứng dụng thật có thể là bảng `user_roles`, `role_permissions`, `user_permissions`; trong ví dụ ta dùng in-memory repository để quan sát.

Thuật toán:

```text
Input: account.roles, account.directPermissions từ nguồn tin cậy
Output: List<GrantedAuthority> hợp lệ

names = một tập có thứ tự
FOR each roleCode:
    kiểm tra roleCode thuộc catalog role hiện hành
    names += "ROLE_" + roleCode
    names += mọi permission do roleCode cấp

FOR each directPermission:
    kiểm tra permission hợp lệ theo catalog
    names += directPermission

RETURN names đã loại trùng, chuyển thành SimpleGrantedAuthority
```

Khi một role không tồn tại trong catalog hoặc một permission không hợp lệ, có hai lựa chọn chính sách **được định nghĩa trước**: từ chối quá trình đăng nhập/đánh dấu lỗi dữ liệu, hoặc không cấp quyền không nhận diện nhưng vẫn cho tài khoản đăng nhập ở mức hạn chế. Với luồng minh họa, ta **fail closed** bằng lỗi rõ ràng để người vận hành phát hiện cấu hình sai. Không thay unknown role thành `ADMIN`, không mặc định cấp `report:read`, và không parse những chuỗi chưa xác minh.

### Cẩn thận với chuẩn hóa tên quyền

Việc tự động `trim()`, `toUpperCase()` hay thay dấu `-`/`:` dễ che một dữ liệu nguồn sai. Ví dụ:

- `roleCode = "ADMIN"` và `roleCode = "admin"` nên được xử lý theo hợp đồng rõ ràng, không tùy ý coi là giống nhau.
- `report:read` khác `REPORT:READ` khi dùng `hasAuthority` so sánh chuỗi.
- `ROLE_ADMIN` là **authority đã có prefix**, còn `ADMIN` là **role code nội bộ** trong mapping minh họa. Nếu mapper thêm prefix vào giá trị `ROLE_ADMIN` sẽ tạo `ROLE_ROLE_ADMIN`, không đúng.
- `SCOPE_orders.read` thuộc quy ước mapping token scope; không tự đổi role/permission doanh nghiệp sang `SCOPE_*` nếu ứng dụng không có quy ước ấy.

Đặt tên quyền theo mục tiêu nghiệp vụ và giữ một catalog/contract duy nhất. Với dữ liệu do người dùng nhập trong UI quản trị, cần validate trước khi lưu và kiểm tra quyền của **người cấp quyền**, không chờ đến lúc đăng nhập mới phát hiện mọi lỗi.

## 6. Ví dụ Spring Boot Java 17+ chạy được

Ví dụ tạo ba tài khoản:

| User | Role nguồn | Direct permission nguồn | Kết quả authority nghiệp vụ |
| --- | --- | --- | --- |
| `an` | `USER`, `ANALYST` | `report:read` (trùng quyền từ role) | `ROLE_USER`, `ROLE_ANALYST`, `report:read` |
| `binh` | `USER`, `APPROVER` | `report:read` | `ROLE_USER`, `ROLE_APPROVER`, `invoice:approve`, `report:read` |
| `chi` | `ADMIN` | không có | `ROLE_ADMIN` |

An có `report:read` từ role ANALYST lẫn quyền trực tiếp; mapper phải **loại trùng**. Bình có `invoice:approve` từ role APPROVER và `report:read` trực tiếp. Chi có role ADMIN, nhưng **không có `report:read`/`invoice:approve`** vì policy demo không định nghĩa ADMIN tự nhận mọi permission.

**Chuẩn bị:** dự án Spring Boot Servlet với Spring Web và Spring Security, Java 17+, Maven hoặc Gradle wrapper. Ví dụ minh họa Spring Security 7.x; các lớp dùng ở đây có trong API tương ứng. Tạo một file `src/main/java/com/example/authoritymap/AuthorityMappingApplication.java`:

```java
package com.example.authoritymap;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityMappingApplication.class, args);
    }
}

// Dữ liệu nghiệp vụ nội bộ do server quản lý.
// Password chỉ là hash; role code chưa có tiền tố ROLE_.
record DomainAccount(
        String username,
        String passwordHash,
        Set<String> roleCodes,
        Set<String> directPermissions,
        boolean enabled) {
}

// Demo repository. Trong thực tế thay bằng DB/identity service tin cậy.
final class DomainAccountStore {
    private final Map<String, DomainAccount> accounts;

    DomainAccountStore(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");
        this.accounts = Map.of(
                "an", new DomainAccount(
                        "an", hash,
                        Set.of("USER", "ANALYST"),
                        Set.of("report:read"), true),
                "binh", new DomainAccount(
                        "binh", hash,
                        Set.of("USER", "APPROVER"),
                        Set.of("report:read"), true),
                "chi", new DomainAccount(
                        "chi", hash,
                        Set.of("ADMIN"),
                        Set.of(), true));
    }

    DomainAccount findByUsername(String username) {
        return accounts.get(username);
    }
}

// Hợp đồng quyền do ứng dụng định nghĩa và kiểm soát.
final class DomainAuthorityMapper {

    private static final Map<String, Set<String>> ROLE_PERMISSIONS =
            Map.of(
                    "USER", Set.of(),
                    "ANALYST", Set.of("report:read"),
                    "APPROVER", Set.of("invoice:approve"),
                    "ADMIN", Set.of());

    private static final Set<String> ALLOWED_PERMISSIONS =
            Set.of("report:read", "invoice:approve");

    List<GrantedAuthority> toAuthorities(DomainAccount user) {
        TreeSet<String> names = new TreeSet<>();

        for (String role : user.roleCodes()) {
            Set<String> rolePermissions = ROLE_PERMISSIONS.get(role);
            if (rolePermissions == null) {
                throw new IllegalStateException(
                        "Unknown role code in trusted source");
            }

            names.add("ROLE_" + role);
            names.addAll(rolePermissions);
        }

        for (String permission : user.directPermissions()) {
            if (!ALLOWED_PERMISSIONS.contains(permission)) {
                throw new IllegalStateException(
                        "Unknown permission in trusted source");
            }
            names.add(permission);
        }

        return names.stream()
                .map(name -> (GrantedAuthority)
                        new SimpleGrantedAuthority(name))
                .toList();
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DomainAccountStore accounts(PasswordEncoder encoder) {
        return new DomainAccountStore(encoder);
    }

    @Bean
    DomainAuthorityMapper authorityMapper() {
        return new DomainAuthorityMapper();
    }

    @Bean
    UserDetailsService users(
            DomainAccountStore accounts,
            DomainAuthorityMapper authorityMapper) {

        return username -> {
            DomainAccount account = accounts.findByUsername(username);
            if (account == null) {
                throw new UsernameNotFoundException("User not found");
            }

            List<GrantedAuthority> authorities =
                    authorityMapper.toAuthorities(account);

            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .authorities(authorities)
                    .disabled(!account.enabled())
                    .build();
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return http
                .authenticationProvider(provider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/me").authenticated()
                        .requestMatchers("/reports")
                            .hasAuthority("report:read")
                        .requestMatchers("/invoices/approval-check")
                            .hasAuthority("invoice:approve")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        // Chỉ chọn authority thuộc contract nghiệp vụ để demo.
        // Một version Spring Security có thể cấp thêm FACTOR_PASSWORD.
        List<String> appAuthorities =
                authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .filter(name -> name != null
                                && (name.startsWith("ROLE_")
                                        || name.contains(":")))
                        .sorted()
                        .toList();
        return authentication.getName()
                + " -> " + String.join(",", appAuthorities);
    }

    @GetMapping("/reports")
    String reports() {
        return "reports visible";
    }

    @GetMapping("/invoices/approval-check")
    String approvalCheck() {
        // Endpoint chỉ kiểm tra quyền, không thực sự duyệt hóa đơn.
        return "may approve";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin only";
    }
}
```

### Giải thích từng tầng trong ví dụ

**`DomainAccountStore`:** đóng vai nguồn quyền nội bộ. Nó trả `roleCodes` và `directPermissions`, không đọc quyền từ body/request. Các role có tên chưa mang `ROLE_`; username/password là dữ liệu phục vụ xác thực. Dùng cùng hash BCrypt cho ba tài khoản chỉ nhằm ngắn gọn trong demo; hệ thống thật phải có credential được quản lý riêng cho từng user.

**`DomainAuthorityMapper`:** chuyển role code sang authority `ROLE_*`, mở rộng thành permission từ catalog, hợp thêm direct permission và dùng `TreeSet` để loại trùng/sắp thứ tự. Unknown role hoặc permission là lỗi dữ liệu **không được cấp thêm quyền**. Trong production, lỗi này cần được quan sát và xử lý qua cơ chế xác thực phù hợp, tránh để lộ chi tiết source qua response.

**`UserDetailsService`:** là adapter giữa nguồn domain và `UserDetails`; trả username, hash, trạng thái enabled và authority. Nó **không kiểm tra password** và không tự tạo authenticated token.

**`DaoAuthenticationProvider`:** dùng `UserDetailsService` và `PasswordEncoder`; khi credential hợp lệ và account đủ điều kiện, framework trả kết quả authentication. Các authority do mapper cung cấp chỉ được coi là quyền của caller **sau bước kiểm chứng**.

**`SecurityFilterChain`:** kiểm tra `report:read`, `invoice:approve` và `ROLE_ADMIN` bằng các rule độc lập. `anyRequest().denyAll()` giúp đường dẫn không khai báo không được mở vô ý. `/public/ping` mở cho anonymous; `/me` chỉ yêu cầu authentication.

**`DemoController.me`:** lọc các authority nghiệp vụ để in ví dụ ổn định. Một số bản Spring Security 7 có authority nội bộ như `FACTOR_PASSWORD`; việc lọc ở đây chỉ để **hiển thị**, không phải logic authorization, cũng không ngụ ý chúng không tồn tại trong `Authentication`.

### Chạy demo

Trong thư mục gốc project Gradle được Spring Initializr tạo:

```bash
./gradlew bootRun
```

Nếu project dùng Maven:

```bash
./mvnw spring-boot:run
```

Windows PowerShell dùng `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. Không biên dịch file trên bằng một lệnh `javac` đơn thuần khi không có classpath Spring; các dependency phải được build tool nạp đúng.

Sau khi ứng dụng chạy ở localhost cổng 8080, mở terminal khác:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-pass http://localhost:8080/me
curl -s -u binh:demo-pass http://localhost:8080/me
curl -s -u chi:demo-pass http://localhost:8080/me
curl -s -u an:demo-pass http://localhost:8080/reports
curl -s -u binh:demo-pass http://localhost:8080/invoices/approval-check
curl -s -u chi:demo-pass http://localhost:8080/admin
```

Trên Windows PowerShell, nếu `curl` là alias của cmdlet khác, dùng `curl.exe`. **Response body** của các request hợp lệ trên, theo thứ tự, là:

```text
pong
an -> ROLE_ANALYST,ROLE_USER,report:read
binh -> ROLE_APPROVER,ROLE_USER,invoice:approve,report:read
chi -> ROLE_ADMIN
reports visible
may approve
admin only
```

Để thử trường hợp không đủ quyền hoặc credential sai:

```bash
curl -i -u an:demo-pass http://localhost:8080/admin
curl -i -u an:demo-pass http://localhost:8080/invoices/approval-check
curl -i -u chi:demo-pass http://localhost:8080/reports
curl -i -u an:wrong http://localhost:8080/me
curl -i http://localhost:8080/reports
```

Trong demo HTTP Basic, ba lệnh đầu nhận **403 Forbidden** vì đã xác thực nhưng thiếu quyền cần thiết. Hai lệnh cuối nhận **401 Unauthorized** vì credential sai hoặc không có. Body/header lỗi có thể thay đổi theo version/cấu hình, nên không nên dựa vào một thông điệp lỗi cố định. HTTP Basic dùng Base64, **không phải mã hóa bí mật**; ở môi trường thực phải dùng HTTPS, không dùng mật khẩu demo.

**Nhận xét:** tài khoản Chi là ADMIN nên vào `/admin`, nhưng không tự có `report:read`. Tài khoản An có cả role ANALYST và direct grant `report:read`, nhưng `getAuthorities()` chỉ có **một** authority `report:read` theo phép hợp của mapper. Bình có permission `invoice:approve` do role APPROVER và `report:read` do direct grant.

## 7. Đem thuật toán này vào database thật

Một schema quan hệ phổ biến:

```text
users(id, username, password_hash, enabled, tenant_id)
roles(id, code)
permissions(id, code)
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id)
```

Mỗi tên bảng/cột là thiết kế minh họa, không phải cấu trúc bắt buộc của Spring Security. Cần quy định khóa, uniqueness, hiệu lực, audit, tenant scope và cách quản lý grant/revoke.

Quy trình trong `UserDetailsService`:

1. Tìm user theo định danh đăng nhập và tenant/identity store phù hợp; không tin tenant do caller tự khai nếu chưa được xác minh.
2. Đọc password hash và flags từ nguồn tin cậy; hạn chế tải dữ liệu profile không cần.
3. Tải role của user và permission tương ứng; hợp nhất với direct grants đúng chính sách.
4. Kiểm tra role/permission còn hiệu lực, không bị revoke, đúng tenant và điều kiện cấp quyền.
5. Chuẩn hóa theo catalog có quy ước; trả `List<GrantedAuthority>` được cấp phép.
6. Để provider kiểm tra credential rồi phát authenticated `Authentication`.

Với relational DB, cần chú ý **N+1 queries** và việc các quan hệ có thể thay đổi trong lúc tải. Có thể tải quyền qua join/query chuyên dụng hoặc domain service; phải tránh tạo cartesian product quá lớn, giữ tính nhất quán snapshot khi nghiệp vụ yêu cầu. Dùng unique constraints trong bảng grant để ngăn trùng, nhưng mapper vẫn nên loại trùng ở đầu ra.

### Vì sao không ánh xạ trực tiếp database role thành `ROLE_*` mà bỏ permission?

Làm vậy có thể phù hợp với ứng dụng chỉ có role-based access control (RBAC) đơn giản. Nhưng nếu policy yêu cầu `report:read`, việc chỉ cấp `ROLE_ANALYST` sẽ **không thỏa** rule `hasAuthority("report:read")` trừ khi hệ thống cấu hình một giải pháp khác như role hierarchy có cấu trúc phù hợp hoặc một `AuthorizationManager` hiểu mapping domain.

Chọn một nơi chịu trách nhiệm cho phép chuyển role thành permission để tránh hai cơ chế cạnh tranh. Nếu mapper đã mở rộng quyền thì không cần thêm một lớp khác lại tự động “ADMIN nhận mọi permission” một cách không nhất quán.

### Tiền tố role không phải nguồn dữ liệu gốc

Trong bảng `roles` có thể lưu code `ADMIN` để domain độc lập với Spring. Adapter thêm `ROLE_` khi tạo authority. Không lưu song song `ADMIN` và `ROLE_ADMIN` ở nhiều cột rồi cho phép chúng lệch nhau. Một định danh role bền vững và một hàm chuyển đổi được kiểm thử sẽ dễ quản lý hơn.

## 8. Mapping quyền theo tenant và theo tài nguyên

`GrantedAuthority` như `report:read` thường mô tả một **khả năng tổng quát**. Nó chưa khẳng định user được đọc báo cáo của bất kỳ tenant hoặc bất kỳ người sở hữu nào.

Giả sử An thuộc tenant A; dù mang `report:read`, An không được xem báo cáo tenant B. Chính sách hoàn chỉnh có thể là:

```text
Cho phép GET /reports/{reportId} nếu:
    Authentication đã xác thực
    VÀ có authority "report:read"
    VÀ report.tenant_id thuộc phạm vi tenant đã được xác minh của caller
    VÀ policy cho phép đọc reportId cụ thể
```

Trong service, ID actor và tenant phải đến từ **identity/authorization context đáng tin**, không từ `?userId=...` hoặc `?tenantId=...` tự khai. Endpoint trả danh sách báo cáo nên áp dụng tenant filter ngay ở query DB; endpoint xem một báo cáo nên kiểm tra quyền trên đúng đối tượng.

Không nên sinh hàng trăm nghìn authority `report:123:read` cho từng record nếu policy có thể kiểm tra object/tenant bằng domain service. Làm vậy khiến `Authentication` nặng, khó cache/revoke và dễ tạo lỗi khi quyền dữ liệu thay đổi. Với dữ liệu phạm vi nhỏ, một thiết kế authority theo resource có thể hợp lý, nhưng phải có giới hạn và chiến lược thu hồi rõ ràng.

### Nếu user có cả quyền cho phép và quyền cấm

Ví dụ role cấp `report:read` nhưng user bị cấm đọc một báo cáo nhạy cảm. Danh sách `GrantedAuthority` dạng tập “allow” không tự hiểu một deny riêng. Cần áp dụng **policy chặn** ở tầng thích hợp: điều kiện dữ liệu, tenant isolation, explicit deny rule hoặc authorization manager chuyên dụng. Không giả định “có role là luôn được” khi còn điều kiện nghiệp vụ.

## 9. JWT, OAuth2/OIDC và mapping authority từ token

Với username/password, ví dụ dùng `UserDetailsService`. Với OAuth2 Resource Server, framework thường lấy principal/authority từ token đã được xác minh, không gọi `UserDetailsService` theo đúng luồng DAO như trên.

Ví dụ JWT có scope:

```json
{
  "sub": "user-17",
  "scope": "reports.read invoices.approve"
}
```

Đây chỉ là phần **payload minh họa**, không phải token hợp lệ đã ký. Trong cấu hình JWT mặc định, scope được chuyển thành các authority thường có prefix `SCOPE_`:

```text
SCOPE_reports.read
SCOPE_invoices.approve
```

Nếu API của ứng dụng đòi `hasAuthority("report:read")`, những chuỗi `SCOPE_reports.read` **không tự động** tương đương `report:read`. Có hai cách thiết kế rõ ràng:

- Dùng rule tương ứng với scope được phát hành và đã xác minh, ví dụ `hasAuthority("SCOPE_reports.read")`, khi phạm vi token đúng là quyền API.
- Dùng một converter/policy mapping đã kiểm soát để ánh xạ claims/scope được tin cậy sang authority nghiệp vụ, khi hợp đồng giữa issuer và application được định nghĩa rõ.

**Không lấy `roles`, `permissions` hay `scope` từ JSON body/header client để tự tạo `SimpleGrantedAuthority`.** Với JWT phải xác minh chữ ký/issuer/expiration và audience theo cấu hình, cũng như hợp đồng claim. Với opaque token cần nguồn introspection đáng tin; với OIDC login phải phân biệt ID token, access token và quyền nội bộ.

Một claim `"roles": ["ADMIN"]` không tự động thành `ROLE_ADMIN` nếu converter không ánh xạ nó. Hãy ghi nhận rõ issuer, namespace của claim, tenant và loại principal (user, service account) trước khi cấp quyền; không lấy email làm khóa hợp nhất tài khoản một cách tự động.

## 10. Quyền thay đổi sau khi user đăng nhập: vấn đề snapshot và thu hồi

`Authentication.getAuthorities()` phản ánh một tập quyền tại thời điểm xác thực hoặc khi framework tạo/khôi phục context. Nếu quản trị viên thu hồi `invoice:approve` trong database, **không thể mặc định** mọi session hay JWT đã phát hành lập tức mất authority đó.

| Cơ chế | Nguồn quyền tại request | Điều cần kiểm tra khi revoke |
| --- | --- | --- |
| HTTP Basic (demo) | Thường xác thực lại credential, có thể tải lại `UserDetails` | Cần xét user cache và cách nạp quyền |
| Form login + session | Có thể khôi phục `Authentication` từ session | Session cũ có thể giữ tập authority cũ |
| JWT tự chứa claim | Authority chuyển từ token đã được xác minh | Token còn hiệu lực có thể giữ claim trước khi revoke |
| Opaque access token | Thường dựa vào kết quả introspection | Nguồn introspection và cache còn hiệu lực đến khi nào |
| Custom policy lookup | Tầng policy truy vấn dữ liệu hiện hành | Hiệu năng, failure behavior, consistency của nguồn policy |

Chính sách có thể dùng session invalidation, token TTL/revocation, quyền phiên bản hóa, authorization lookup thời gian thực cho thao tác nhạy cảm, hoặc kết hợp nhiều biện pháp. Độ trễ thu hồi được phép phải là yêu cầu thiết kế rõ ràng, nhất là với quyền tài chính/quản trị.

**Không dùng snapshot cũ của authorities để quyết định một giao dịch nhạy cảm khi chính sách yêu cầu quyền hiện thời.** Khi đó cần kiểm tra lại ở policy service có nguồn tin cậy và cơ chế xử lý lỗi hợp lý.

## 11. Lỗi phổ biến khi chuyển quyền nghiệp vụ

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đọc `role` từ request rồi tạo authority | Caller tự nâng quyền | Chỉ lấy quyền từ domain/issuer đã xác minh |
| Lấy được `UserDetails` là coi login thành công | Bỏ qua credential | Để `AuthenticationProvider` kiểm tra rồi phát kết quả |
| Lưu `ADMIN` nhưng rule dùng `hasRole("ADMIN")` | Rule cần `ROLE_ADMIN` theo mặc định | Mapper tạo tiền tố đúng, kiểm thử |
| Mapper thêm `ROLE_` vào `ROLE_ADMIN` đã có prefix | Tạo `ROLE_ROLE_ADMIN` | Định nghĩa role code nguồn chưa có prefix |
| Quyền `report.read` nhưng rule đòi `report:read` | Không khớp chuỗi | Dùng một catalog tên quyền |
| Tự cấp `ROLE_ADMIN` cho unknown role | Privilege escalation | Validate và fail closed |
| Chỉ cấp role, quên permission do role mang | Rule `hasAuthority` từ chối dù nghiệp vụ cho phép | Thiết kế mapping role → permission rõ |
| Có role ADMIN nên coi là mọi quyền | Bỏ qua policy chi tiết | Cấp đúng quyền hoặc cấu hình policy tường minh |
| Cấp `report:read` và bỏ kiểm tra tenant/owner | Có thể lộ dữ liệu giữa tài khoản/tenant | Kết hợp resource authorization |
| Cache `UserDetails` vô thời hạn | Quyền bị thu hồi vẫn tồn tại | Chính sách refresh/TTL/revoke |
| Dùng principal chứa JPA entity với lazy roles | Lỗi loading, serialization, mutation | Adapter immutable/tối thiểu |
| Log cả token, password, `Authentication` | Rò bí mật hoặc PII | Log actor ID, loại quyết định, correlation ID |
| Dùng `SCOPE_*` như `ROLE_*` không có mapping | Sai hợp đồng token/application | Converter và rule phù hợp |
| Thả `anyRequest().permitAll()` sau khi quên matcher | Mở đường dẫn nhạy cảm | Ưu tiên rule cụ thể, mặc định deny theo yêu cầu |

### Tại sao lỗi unknown role nên được phát hiện sớm?

Nếu database có role `FINANCE_SUPER` nhưng mapper không biết, âm thầm cấp một bộ quyền ngẫu nhiên có thể quá rộng. Một chính sách **fail closed** có thể ném exception nội bộ và chặn xác thực/authorization tới khi người quản trị sửa dữ liệu; không nên lộ nội dung database trong response công khai. Với hệ thống cần cho phép user vẫn đăng nhập khi thiếu role không nhạy cảm, có thể bỏ unknown role theo policy đã được duyệt, nhưng **không** suy đoán quyền thay thế và phải có telemetry phát hiện dữ liệu lỗi.

## 12. Kiểm thử mapping: kiểm tra cả dữ liệu và hành vi HTTP

Một bộ test tốt nên có hai lớp:

**Kiểm thử mapper bằng dữ liệu domain đã biết** để phân biệt lỗi chuyển đổi, loại trùng, prefix và unknown role. **Kiểm thử Spring Security bằng request đã xác thực** để biết quyền thật sự được enforcement.

Ma trận gợi ý:

| Case | Kết quả mong đợi |
| --- | --- |
| USER + ANALYST | `ROLE_USER`, `ROLE_ANALYST`, `report:read` |
| APPROVER + direct report:read | Có cả `invoice:approve` và `report:read` |
| Cùng permission từ role và direct | Chỉ một authority `report:read` |
| ADMIN không có permission đọc báo cáo | `/admin` được phép, `/reports` bị chặn |
| Unknown role từ DB | Fail closed, không được thêm quyền bất kỳ |
| Permission không thuộc catalog | Không được biến thành authority có sức mạnh ngoài contract |
| Username/password sai | Không có authenticated `Authentication` |
| Không có credential | Protected endpoint yêu cầu authentication |
| Có `report:read` nhưng khác tenant | Policy theo tenant từ chối |
| Thu hồi permission trong nguồn gốc | Quyền không còn hiệu lực theo chiến lược refresh/revoke đã định |
| Token chỉ có `SCOPE_orders.read` | Không tự thỏa rule `report:read` |
| User/service account dùng principal khác nhau | Không trao quyền user cho service khi chưa có chính sách |

### Test mapper bằng Java 17 (mảnh mã)

Đoạn dưới dùng `DomainAuthorityMapper`/`DomainAccount` từ ví dụ hoàn chỉnh ở phần 6, có thể đặt trong một test method hoặc `CommandLineRunner` riêng:

```java
DomainAccount demo = new DomainAccount(
        "an",
        "unused-hash-for-mapper-test",
        Set.of("USER", "ANALYST"),
        Set.of("report:read"),
        true);

List<String> names = new DomainAuthorityMapper()
        .toAuthorities(demo)
        .stream()
        .map(GrantedAuthority::getAuthority)
        .toList();

System.out.println(names);
```

Kết quả chính xác:

```text
[ROLE_ANALYST, ROLE_USER, report:read]
```

Đây là test **thuần mapping**: password hash ở đây không được dùng để xác thực và không nên sử dụng cho login. Để kiểm tra thật `DaoAuthenticationProvider` và các HTTP rule, dùng các `curl` của phần 6 hoặc test integration framework tương ứng.

### Kiểm tra dữ liệu đầu vào và quyền cấp quyền

Không chỉ test user thường. Hãy test chức năng **gán role/permission**: người dùng không có quyền quản trị không thể tự cấp `ADMIN`; danh sách role do API quản trị nhận vẫn phải được backend kiểm tra; các mutation cấp/thu hồi phải có audit, idempotency và constraint phù hợp. Mapper chỉ xử lý dữ liệu đã cấp, không thay thế cơ chế bảo vệ thao tác cấp quyền.

## 13. Tình huống mở rộng: role hierarchy, separation of duties và explicit deny

Một số ứng dụng có phân cấp role: `MANAGER` ngầm bao gồm khả năng của `USER`. Có hai cách biểu diễn chính:

- **Mở rộng khi nạp**: mapper cấp cả những permission được thừa kế. `Authentication` chứa tập quyền cuối cùng.
- **Khai báo hierarchy trong authorization**: một cấu hình role hierarchy/policy chuyển đổi ngữ nghĩa khi xét rule.

Hai cách có thể đạt cùng kết quả cho trường hợp đơn giản, nhưng cần chọn nguồn nhất quán để tránh cấp quá nhiều hoặc thiếu quyền khi hierarchy đổi. Đừng cấp `ROLE_ADMIN` chỉ vì user có nhiều permission; role và permission có vai trò khác nhau.

Với nghiệp vụ tài chính, đôi khi một user không được vừa lập vừa duyệt cùng giao dịch (separation of duties). Chỉ cấp `invoice:create` và `invoice:approve` rồi dùng `hasAuthority` có thể vẫn không ngăn việc user duyệt giao dịch chính họ tạo. Cần kiểm tra **quan hệ actor – resource – workflow** trong service/policy, kể cả khi cả hai authority có mặt.

Với deny tường minh, cần chính sách ưu tiên deny. Một `Collection<GrantedAuthority>` đơn giản thường chỉ chứa các granted ability; nó không tự diễn giải điều kiện cấm. Nếu chuyển sang một policy engine hoặc custom `AuthorizationManager`, vẫn giữ contract rõ về định danh, nguồn quyền, kết quả quyết định và failure behavior.

## 14. Checklist trước khi triển khai production

1. Catalog role, permission và prefix được chuẩn hóa, có người quản lý và phiên bản.
2. Nguồn cấp quyền đáng tin; API tự cấp quyền được bảo vệ và audit.
3. Role code và permission code được kiểm tra hợp lệ trước và trong quá trình mapping.
4. UserDetails chứa tập authority đúng, không dư quyền, không dựa vào input client.
5. Credential và trạng thái tài khoản được provider kiểm chứng; chỉ authentication thành công mới mang quyền vào request.
6. Rule `hasAuthority`, `hasRole`, method security và domain policy thống nhất tên quyền.
7. Multi-tenant và object ownership được kiểm tra ngoài authority tổng quát.
8. Session/token cache và thời gian thu hồi được định nghĩa; có phương án xử lý trạng thái cũ.
9. Lỗi nguồn quyền được phân loại, theo dõi và xử lý an toàn, không mở mặc định.
10. Thử quyền tối thiểu, unknown role, duplicate grant, role prefix, missing permission, revoke và account disable.
11. Không ghi secrets/PII không cần thiết trong log; không xuất `Authentication` thô ra client.
12. Có tài liệu chỉ rõ trường hợp ADMIN được hưởng quyền nào theo policy; không mặc định mọi quyền.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Database lưu role `ANALYST` nhưng endpoint dùng `hasAuthority("report:read")`. Chỉ cấp `ROLE_ANALYST` đã đủ chưa?  
**Đáp án:** Chưa, trừ khi ứng dụng có chính sách authorization đặc biệt hiểu role đó. Với mapping của bài, cần nạp thêm `report:read` từ role.

**Câu 2.** Một user có `report:read` từ role và direct grant. Có cần hai object `SimpleGrantedAuthority("report:read")` không?  
**Đáp án:** Không. Tập hợp theo tên quyền, loại trùng trước khi chuyển sang authority.

**Câu 3.** Caller gửi `X-Role: ADMIN`. Server có được tạo `ROLE_ADMIN` vì header ấy không?  
**Đáp án:** Không. Header client là dữ liệu chưa tin cậy; role phải đến từ nguồn đã được xác minh hoặc cơ chế proxy/issuer tin cậy với ranh giới bảo vệ rõ.

**Câu 4.** User mang `ROLE_ADMIN` có tự thỏa `hasAuthority("invoice:approve")` không?  
**Đáp án:** Không. Phải cấp `invoice:approve` hoặc cấu hình policy/hierarchy tường minh tương đương.

**Câu 5.** Vì sao mapping có thể được gọi trong `UserDetailsService` trước khi đối chiếu mật khẩu mà vẫn an toàn?  
**Đáp án:** Vì dữ liệu quyền mới chỉ là thông tin account; provider phải kiểm tra credential thành công trước khi phát authenticated `Authentication` cho caller.

**Câu 6.** User có `report:read` nhưng báo cáo thuộc tenant khác. Có được trả báo cáo không?  
**Đáp án:** Không nếu policy cấm truy cập cross-tenant. Phải kiểm tra quyền trên đối tượng/tenant bằng ngữ cảnh tin cậy.

**Câu 7.** Đổi quyền trong DB có làm một JWT đã phát hành lập tức thay đổi claim không?  
**Đáp án:** Không. Cần chính sách TTL, revoke hoặc lookup quyền hiện thời phù hợp.

**Câu 8.** Vì sao `SCOPE_orders.read` và `orders:read` không phải một?  
**Đáp án:** Đây là hai chuỗi authority khác nhau, có hợp đồng cấp quyền và cách tạo khác nhau; chỉ tương đương nếu converter/policy xác định rõ.

## Kết luận

Ánh xạ quyền nghiệp vụ thành `GrantedAuthority` là bước nối giữa **mô hình cấp quyền của ứng dụng** và **cơ chế authorization của Spring Security**. Dữ liệu role/permission phải đến từ nguồn tin cậy; mapper chuyển đổi theo quy tắc rõ ràng, loại trùng, không tự mở rộng ngoài chính sách và trả collection authorities cho `UserDetails` hoặc cơ chế token tương ứng. Sau khi authentication thành công, Spring Security mới dùng chúng như quyền của caller trong request.

**Một tập authority đúng không thay thế được việc đặt rule đúng và kiểm tra quyền trên tài nguyên cụ thể.** Thiết kế hoàn chỉnh cần cả ba: nguồn quyền chính xác, ánh xạ nhất quán và enforcement theo ngữ cảnh.

### Tài liệu tham khảo chính thức

- [Spring Security — Authorization Architecture và GrantedAuthority](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — User.UserBuilder API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/resource-server/jwt.html)