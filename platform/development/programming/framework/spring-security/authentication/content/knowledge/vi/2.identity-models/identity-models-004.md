# GrantedAuthority: quyền được nạp sau khi nhận diện danh tính

> **Chủ đề:** Mô hình danh tính trong Spring Security — cách những quyền (authorities) được lấy từ nguồn tin cậy, gắn với `Authentication` sau khi xác thực, và được sử dụng để quyết định truy cập. Bài này tập trung vào ý nghĩa, nguồn gốc, vòng đời và cách dùng `GrantedAuthority`; ví dụ Java 17+ chạy trên Spring Boot Servlet.

## 1. Vì sao nhận diện được người gọi vẫn chưa đủ?

Giả sử ứng dụng có ba API:

- `GET /me`: trả thông tin về tài khoản đang đăng nhập.
- `GET /reports`: chỉ dành cho người được quyền đọc báo cáo.
- `GET /admin`: chỉ dành cho tài khoản có vai trò quản trị.

Khi An nhập đúng thông tin đăng nhập, hệ thống đã **xác thực** được danh tính An. Nhưng từ kết quả "người gọi là An", ứng dụng chưa thể tự suy ra An có quyền đọc báo cáo hoặc quản trị. Hệ thống cần một biểu diễn các quyền **được cấp cho chủ thể ấy** và một chính sách để đối chiếu quyền với hành động.

Trong Spring Security, một biểu diễn phổ biến là `GrantedAuthority`. Các giá trị như `ROLE_ADMIN`, `report:read` hoặc `SCOPE_orders.read` trở thành thành phần của `Authentication` đáng tin sau quá trình xác thực thích hợp; chúng được đọc ở bước **authorization**.

Hãy xem ba câu hỏi riêng:

1. **Identity:** chủ thể là ai? Ví dụ: tài khoản `an`, định danh nội bộ `user-17`.
2. **Authentication:** bằng chứng nào giúp server tin rằng request hiện tại thực sự gắn với tài khoản đó?
3. **Authorization:** những quyền nào đã được cấp và quyền nào cần có để thực hiện một thao tác?

**Không có quy tắc "cứ đăng nhập thành công là được mọi quyền".** Ngược lại, client cũng không thể tự chọn vai trò bằng cách gửi `?role=ADMIN` hay `X-Role: ADMIN` rồi yêu cầu server tin theo.

## 2. `GrantedAuthority` thực sự là gì?

`GrantedAuthority` là interface của Spring Security, khai báo phương thức:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Đây là **trích hình dạng API để giải thích**, không phải file nguồn cần tự tạo trong ứng dụng. `getAuthority()` cho biết chuỗi đại diện quyền; Spring Security thường dùng chuỗi đó để so sánh với quy tắc authorization. Ví dụ:

```text
ROLE_USER
ROLE_ADMIN
report:read
report:write
SCOPE_orders.read
```

`SimpleGrantedAuthority` là implementation đơn giản và thường gặp:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority permission = new SimpleGrantedAuthority("report:read");
System.out.println(permission.getAuthority()); // report:read
```

Đoạn trên là **mảnh mã minh họa** (cần dependency Spring Security và đặt trong phương thức hoặc JShell), không phải một chương trình Java có `main` độc lập. `SimpleGrantedAuthority` chỉ bọc một chuỗi; bản thân đối tượng này **không kiểm tra** mật khẩu, danh tính hay quyền truy cập tài nguyên.

### Một authority biểu diễn những gì?

| Ví dụ | Ý nghĩa do ứng dụng/quy ước xác định | Cách kiểm tra |
| --- | --- | --- |
| `ROLE_USER` | Người dùng có vai trò `USER` theo quy ước `ROLE_` | `hasRole("USER")` hoặc `hasAuthority("ROLE_USER")` trong cấu hình mặc định |
| `ROLE_ADMIN` | Vai trò quản trị | `hasRole("ADMIN")` |
| `report:read` | Quyền đọc báo cáo của ứng dụng | `hasAuthority("report:read")` |
| `invoice:approve` | Quyền duyệt hóa đơn | `hasAuthority("invoice:approve")` |
| `SCOPE_orders.read` | Scope OAuth2 được ánh xạ thành authority | `hasAuthority("SCOPE_orders.read")` |

Chuỗi quyền **không có phép thuật bên trong**: `report:read` không tự chặn bất kỳ endpoint nào cho đến khi ứng dụng đặt quy tắc yêu cầu chuỗi ấy. `ROLE_ADMIN` cũng không tự bao hàm `ROLE_USER` trong mọi ứng dụng; quan hệ kế thừa chỉ tồn tại nếu được cấp rõ ràng hoặc có cấu hình role hierarchy thích hợp.

Với một `GrantedAuthority` phức tạp không thể biểu diễn chính xác bằng một chuỗi, `getAuthority()` có thể trả `null`; khi đó cần một thành phần authorization thực sự hiểu loại quyền đặc biệt đó. Với đa số ứng dụng web, `SimpleGrantedAuthority` cùng các quyền có tên rõ ràng là lựa chọn dễ quản lý.

### `Authentication` chứa authority ở đâu?

Sau khi chứng thực hợp lệ, Spring Security cung cấp `Authentication` với các thành phần quan trọng:

- `getPrincipal()`: ai là chủ thể được biểu diễn, chẳng hạn `UserDetails` hoặc một `Jwt`.
- `getName()`: tên chủ thể theo implementation.
- `getAuthorities()`: `Collection<? extends GrantedAuthority>` các quyền được gắn với kết quả xác thực.
- `getCredentials()`: bằng chứng liên quan, có thể đã bị loại bỏ sau khi xác thực.
- `isAuthenticated()`: trạng thái của token xác thực. Cần phân biệt anonymous token; chỉ kiểm tra cờ này không đủ để suy ra người dùng đã đăng nhập.

Vì thế, `Authentication` không đơn thuần là một username. Nó là đối tượng framework dùng để chuyển **danh tính + trạng thái xác thực + tập quyền đã cấp** sang bước quyết định truy cập.

## 3. Quyền được "nạp sau khi nhận diện" nghĩa là gì trong thực tế?

Cách nói "nạp quyền sau khi nhận diện danh tính" diễn tả **quan hệ tin cậy và kết quả sử dụng**: trước hết hệ thống phải xác lập danh tính đáng tin; những authority được dùng ở bước authorization phải gắn với kết quả xác thực tương ứng. Tuy nhiên, **thứ tự đọc database không nhất thiết là đợi kiểm tra mật khẩu xong mới đọc quyền**.

Với username/password và `DaoAuthenticationProvider`, một luồng điển hình là:

1. Client gửi username/password; đó vẫn là dữ liệu **chưa đáng tin**.
2. `AuthenticationManager` chuyển yêu cầu đến `AuthenticationProvider` thích hợp.
3. `DaoAuthenticationProvider` dùng `UserDetailsService.loadUserByUsername(...)` để tải tài khoản. `UserDetails` có thể **đã chứa authorities khi được tải**, cùng với mật khẩu băm và trạng thái tài khoản.
4. Provider kiểm tra credential với `PasswordEncoder` và các điều kiện tài khoản. Nếu thất bại, **không được phát hành** một kết quả đăng nhập thành công cùng những quyền vừa đọc.
5. Nếu thành công, provider trả một `Authentication` đã xác thực, có principal và authority thích hợp.
6. Framework làm cho kết quả này sẵn có trong `SecurityContext` của request, theo cơ chế tương ứng.
7. `AuthorizationManager` hoặc cơ chế method security đối chiếu `Authentication.getAuthorities()` với chính sách để cho phép hoặc từ chối.

```text
Request: username/password (chưa tin cậy)
       |
       v
AuthenticationManager
       |
       v
DaoAuthenticationProvider
       |
       +--> UserDetailsService --> UserDetails
       |                          |-- username
       |                          |-- password hash
       |                          +-- authorities từ nguồn tin cậy
       |
       +--> PasswordEncoder kiểm tra credential
                |          |
              SAI         ĐÚNG
                |          |
            Từ chối       v
                         Authentication đã xác thực
                         + principal
                         + authorities
                                |
                                v
                         SecurityContext
                                |
                                v
                         AuthorizationManager
                         hasAuthority / hasRole
                                |
                          Cho phép / Từ chối
```

**Mấu chốt:** Query lấy quyền có thể xảy ra trước kiểm tra mật khẩu như một phần của `loadUserByUsername`, nhưng tập quyền ấy **chỉ có ý nghĩa như quyền của người gọi hiện tại khi authentication hoàn tất hợp lệ**. Không bao giờ lấy quyền của một username tự khai rồi sử dụng ngay để thông qua authorization.

### Nguồn authority có thể đến từ đâu?

- **Database nội bộ:** bảng vai trò, quyền, quan hệ user–role / role–permission.
- **Directory/identity store:** các group hoặc thuộc tính tài khoản được ánh xạ sang authority của ứng dụng.
- **Access token đã xác minh:** scope/claim đáng tin được converter chuyển sang authority.
- **Provider hoặc service tin cậy:** quyền trả về bởi hệ thống nhận diện/ủy quyền khác theo hợp đồng và ranh giới tin cậy đã thiết lập.

`GrantedAuthority` là **kết quả biểu diễn**, không phải nơi lưu dữ liệu gốc. Ứng dụng phải tự định nghĩa quyền nào tồn tại, ai cấp, ai thu hồi, cách ánh xạ và chính sách kiểm tra.

## 4. Vai trò (role), quyền (permission) và scope có giống nhau không?

Ba khái niệm này liên quan nhưng có thể mang ý nghĩa khác nhau trong hệ thống nghiệp vụ.

- **Role:** nhóm trách nhiệm, thường biểu diễn bằng `ROLE_*` như `ROLE_MANAGER`. Một role có thể tập hợp nhiều quyền.
- **Permission:** khả năng thực hiện thao tác như `report:read`, `report:export`, `invoice:approve`.
- **Scope:** giới hạn quyền được cấp cho một client/token trong giao thức ủy quyền, thường biểu diễn trong Spring Resource Server thành `SCOPE_*` theo cấu hình mặc định.

Spring Security thường đọc chúng như các **chuỗi `GrantedAuthority`** khi kiểm tra quyền. Quy trình gán role ra nhiều permission **không tự xuất hiện** chỉ vì có `ROLE_MANAGER` trong `Authentication`.

Ví dụ chính sách một ứng dụng:

| Tài khoản | Role/permission được cấp | Truy cập báo cáo | Truy cập quản trị |
| --- | --- | --- | --- |
| An | `ROLE_USER`, `report:read` | Có | Không |
| Bình | `ROLE_ADMIN` | Không, nếu thiếu `report:read` | Có |
| Chi | `ROLE_ADMIN`, `report:read` | Có | Có |

Bảng trên là **chính sách minh họa**, không phải quy tắc mặc định của Spring Security. Nó cố tình cho thấy người có role ADMIN không được đọc báo cáo nếu endpoint đòi riêng `report:read` và hệ thống không cấu hình kế thừa/tự mở rộng quyền.

### Phân biệt `hasAuthority` và `hasRole`

Với tiền tố role mặc định `ROLE_`:

```java
.hasAuthority("report:read") // tìm đúng chuỗi report:read
.hasAuthority("ROLE_ADMIN")  // tìm đúng chuỗi ROLE_ADMIN
.hasRole("ADMIN")            // thông thường tìm ROLE_ADMIN
```

Các dòng này là **mảnh cấu hình minh họa** trong DSL của `HttpSecurity`, không phải chương trình Java độc lập.

- `hasAuthority("ADMIN")` tìm chuỗi `ADMIN` chính xác, **khác** `ROLE_ADMIN`.
- `hasRole("ADMIN")` thêm tiền tố role mặc định; không truyền `ROLE_ADMIN` vào `hasRole` trong cấu hình mặc định.
- Nếu dự án tùy biến `GrantedAuthorityDefaults`, `AuthorizationManagerFactory` hoặc hệ thống phân quyền, phải kiểm tra quy ước thực tế và tính nhất quán giữa web security và method security.
- Chuỗi authority thường được so khớp chính xác; thống nhất chữ hoa/thường, dấu phân cách, tên miền nghiệp vụ và prefix.

Không trộn nhiều cách đặt tên (`READ_REPORT`, `report.read`, `report:read`) nếu chưa có bước ánh xạ rõ ràng.

## 5. Ví dụ Spring Boot chạy được: cùng danh tính, khác tập quyền

Ví dụ dưới đây dùng Java 17+, **Spring Boot Servlet** với starter **Spring Web** và **Spring Security**. Có hai tài khoản in-memory để quan sát `Authentication.getAuthorities()` và cách `hasRole`/`hasAuthority` phân quyền. Dùng wrapper Gradle/Maven từ dự án Spring Initializr; đây là môi trường học tập, không dùng mật khẩu demo cho production.

Tạo file `src/main/java/com/example/authoritydemo/AuthorityDemoApplication.java`:

```java
package com.example.authoritydemo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails an = User.withUsername("an")
                .password(passwordEncoder.encode("demo-password"))
                .authorities("ROLE_USER", "report:read")
                .build();

        UserDetails binh = User.withUsername("binh")
                .password(passwordEncoder.encode("demo-password"))
                .authorities("ROLE_ADMIN")
                .build();

        return new InMemoryUserDetailsManager(an, binh);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/reports").hasAuthority("report:read")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
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
        List<String> names = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return "principal=" + authentication.getName()
                + "; authorities=" + String.join(",", names);
    }

    @GetMapping("/reports")
    String reports() {
        return "report ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

Giải thích cấu hình:

1. `UserDetailsService` chứa hai hồ sơ đáng tin do server thiết lập. Khi được tải, `UserDetails` đã có tên, hash mật khẩu và authority. Trong thực tế, hồ sơ có thể đến từ DB thay vì in-memory.
2. `PasswordEncoder` dùng BCrypt để tạo/kiểm tra hash. Quyền được cấp **không thay thế** việc kiểm tra password.
3. `/me` yêu cầu đã xác thực, trả principal và danh sách authority đã được đưa vào `Authentication`. `sorted()` giúp thứ tự trong output ổn định.
4. `/reports` yêu cầu chính xác `report:read`, còn `/admin` yêu cầu role `ADMIN`, tương ứng `ROLE_ADMIN` theo mặc định.
5. Với HTTP Basic, mỗi request phải gửi credential thích hợp. Với session hoặc token, cách duy trì/kết xuất `Authentication` sẽ khác.

### Chạy và quan sát

Dùng một trong các lệnh sau từ thư mục gốc dự án (chọn theo build tool):

```bash
./gradlew bootRun
# Hoặc:
./mvnw spring-boot:run
```

Trên Windows PowerShell, chạy `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. Không dùng `javac` trực tiếp để biên dịch file Spring Boot vì cần các dependency được build tool cung cấp.

Trong terminal khác, dùng `curl` (trên PowerShell có thể dùng `curl.exe`):

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -s -u binh:demo-password http://localhost:8080/me
curl -s -u an:demo-password http://localhost:8080/reports
curl -s -u binh:demo-password http://localhost:8080/admin
curl -i http://localhost:8080/reports
curl -i -u an:demo-password http://localhost:8080/admin
curl -i -u binh:demo-password http://localhost:8080/reports
```

Với cấu hình và dữ liệu demo trên, **body** của năm lệnh đầu lần lượt là:

```text
pong
principal=an; authorities=ROLE_USER,report:read
principal=binh; authorities=ROLE_ADMIN
report ok
admin ok
```

Ba lệnh cuối trả mã trạng thái theo cấu hình HTTP Basic này: **401**, **403**, **403**. Header/body lỗi có thể khác nhau theo phiên bản và cấu hình nên không giả định một chuỗi lỗi cố định. Hai lệnh `/me` chứng minh hai principal đã được nhận diện và mang các tập quyền khác nhau. Hai lệnh bị 403 chứng minh **đăng nhập đúng không đồng nghĩa đủ quyền**.

HTTP Basic gửi username/password dưới dạng Base64, **không phải mã hóa bảo mật**. Chỉ triển khai thực tế qua HTTPS; demo dùng localhost nhằm quan sát cơ chế.

### Thay đổi một quyền sẽ ảnh hưởng thế nào?

Nếu khi tạo `UserDetails` cho Bình, server cấp thêm `"report:read"`, một lần xác thực mới với dữ liệu người dùng đã cập nhật có thể tạo `Authentication` chứa quyền đó; request `GET /reports` khi ấy sẽ được phép theo rule hiện tại. Chỉnh một query parameter `?role=...` sẽ không có tác dụng vì không có bước nào tin client để cấp authority.

Ví dụ sử dụng `.roles("USER")` trong `User.withUsername(...)` có thể tiện hơn `.authorities("ROLE_USER")`: builder thêm tiền tố `ROLE_` cho role. Tránh truyền tên đã có prefix vào `.roles(...)`. Khi cần cả role lẫn permission đặt tên tự do, ví dụ cố ý dùng `.authorities(...)` để thấy rõ chuỗi thực sự được lưu.

## 6. Quyền đi từ cơ sở dữ liệu đến `Authentication` như thế nào?

Trong ứng dụng thực tế, một cách thiết kế nguồn quyền phổ biến là:

```text
users
  id, username, password_hash, enabled
       |
       v
user_roles(user_id, role_id) --> roles(id, code)
                                     |
                                     v
                         role_permissions(role_id, permission_id)
                                     |
                                     v
                            permissions(id, code)
```

Giả sử người dùng `an` có role `USER`, và role này gắn permission `report:read`. Khi tải `UserDetails`, tầng service có thể thực hiện:

- Tìm user dựa trên username/email theo quy tắc nội bộ.
- Tải role và permission từ nguồn tin cậy bằng query/JPA/LDAP phù hợp.
- Kiểm tra trạng thái tài khoản, phạm vi tenant và chính sách cấp quyền.
- Chuẩn hóa role `USER` thành `ROLE_USER`, giữ permission `report:read` theo quy ước.
- Loại trùng và trả tập `GrantedAuthority` trong `UserDetails`.

Dưới đây là **mảnh mã minh họa phép ánh xạ**, giả sử `roleCodes` và `permissionCodes` đã được tải từ nguồn tin cậy; không phải repository/service độc lập:

```java
import java.util.Collection;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

static Collection<? extends GrantedAuthority> mapAuthorities(
        Set<String> roleCodes,
        Set<String> permissionCodes) {
    Set<String> names = new TreeSet<>();
    for (String role : roleCodes) {
        names.add("ROLE_" + role);
    }
    names.addAll(permissionCodes);
    return names.stream()
            .map(SimpleGrantedAuthority::new)
            .toList();
}
```

Mã này chỉ minh họa bước chuyển các **tên quyền đã được hệ thống kiểm soát** thành object, không xác thực dữ liệu đầu vào hay thay thế bước kiểm tra quyền kinh doanh. Nếu quyền có thể lấy từ nhiều role, hợp nhất có loại trùng giúp giảm dữ liệu dư thừa.

Cẩn thận với **quyền mặc định**: ứng dụng không nên cấp `ROLE_ADMIN` hoặc một quyền nhạy cảm chỉ vì thiếu hàng dữ liệu role, tải lỗi hoặc không tìm thấy quyền. Chính sách an toàn là **không tự suy đoán quyền cấp thêm**; với dữ liệu bắt buộc bị lỗi, thường phải từ chối xác thực/truy cập theo hợp đồng của hệ thống.

### Chọn nơi ánh xạ quyền

- Với username/password, `UserDetailsService` là nơi thường tải authority gắn với user; một `AuthenticationProvider` tùy biến có thể xây dựng kết quả nếu cơ chế xác thực khác.
- Với OAuth2/JWT, dùng converter phù hợp để chuyển claim đã được xác minh sang authority, thay vì giả vờ JWT đã đi qua `UserDetailsService`.
- Với API lấy quyền bên ngoài, phải xử lý độ tin cậy của nguồn, lỗi mạng, tính nhất quán và thời hạn cache trước khi đưa dữ liệu vào `Authentication`.

Tầng ánh xạ nên rõ chủ sở hữu. Quyền của user và quyền của client/service có thể là hai loại khác nhau; không mặc nhiên biến scope của service thành quyền người dùng cuối.

## 7. Authorities được dùng để quyết định truy cập như thế nào?

Sau khi có `Authentication`, Spring Security có thể bảo vệ tài nguyên ở nhiều lớp.

### Request-level authorization

Ví dụ DSL trong `SecurityFilterChain`:

```java
.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/reports/**").hasAuthority("report:read")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
```

Mỗi rule được áp dụng cho request phù hợp; việc khai báo thứ tự matcher rõ ràng giúp tránh rule tổng quát nuốt rule cụ thể. Đây là **mảnh DSL minh họa**, không phải toàn bộ cấu hình runnable.

### Method-level authorization

Nếu bật `@EnableMethodSecurity` và cấu hình method security thích hợp, có thể yêu cầu quyền ngay trên service:

```java
@PreAuthorize("hasAuthority('report:read')")
public Report readReport(long reportId) {
    // Tải báo cáo và kiểm tra các điều kiện nghiệp vụ khác.
}
```

Đây là **mảnh mã minh họa**, cần `Report`, service thực tế, import và cấu hình method security để biên dịch. Đặt kiểm tra trên service có giá trị khi nghiệp vụ còn được gọi từ entry point khác ngoài HTTP controller.

### Quyền tổng quát chưa đủ cho quyền trên từng đối tượng

Giả sử An có `report:read` nhưng chỉ được xem báo cáo thuộc phòng ban của An. Một `hasAuthority("report:read")` chỉ đáp ứng điều kiện **quyền tổng quát**, không tự đảm bảo `report.departmentId` khớp phòng ban được phép.

Ví dụ logic nghiệp vụ cần cả hai:

```text
Cho phép đọc báo cáo R nếu:
  (1) Authentication có authority "report:read"
  VÀ
  (2) Quy tắc dữ liệu xác nhận chủ thể được truy cập R
      (ownerId, departmentId, tenantId hoặc policy tương đương)
```

Không nên nạp hàng chục nghìn authority dạng `report:501:read`, `report:502:read` chỉ để mô phỏng sở hữu từng bản ghi, vì số lượng lớn gây tốn bộ nhớ, chi phí xác thực và khó thu hồi. Dùng domain-object authorization, policy service, query lọc theo quyền hoặc cơ chế phù hợp với hệ thống.

### `Authentication.getAuthorities()` và kiểm tra quyền không đồng nhất

Việc quan sát tập quyền chỉ cho thấy **dữ liệu đã được cấp**; nó không nói tất cả đường đi authorization có đúng hay chưa. Endpoint phải thật sự có rule bảo vệ; method security phải bật khi dùng; object-level check phải được viết. Một user có nhiều authority không có nghĩa các authority đó được dùng tự động ở mọi thao tác.

## 8. Phiên đăng nhập, token và chuyện thay đổi quyền

Đây là nguồn lỗi quan trọng: **quyền thay đổi trong dữ liệu gốc không có nghĩa mọi `Authentication` đang tồn tại lập tức thay đổi**.

### Session-based login

Sau đăng nhập, `Authentication` có thể được lưu trong `SecurityContext` gắn với HTTP session, tùy cấu hình `SecurityContextRepository`. Nếu quyền của An thay đổi trong DB nhưng session vẫn chứa tập quyền trước đó, request tiếp theo có thể tiếp tục sử dụng quyền cũ cho tới khi session/ngữ cảnh được cập nhật, hết hạn hoặc người dùng đăng nhập lại.

Những lựa chọn thường gặp tùy yêu cầu:

- Session ngắn hơn hoặc đăng nhập lại sau thay đổi nhạy cảm.
- Chủ động vô hiệu hóa/thu hồi session liên quan.
- Có cơ chế cập nhật hoặc kiểm tra phiên bản quyền khi xử lý request.
- Kiểm tra quyền hiện thời ở policy/domain service cho thao tác nhạy cảm.

Không có một chính sách làm mới quyền mặc định phù hợp cho mọi hệ thống.

### HTTP Basic

Khi mỗi request mang username/password và ứng dụng xác thực lại qua provider, việc tải quyền có thể diễn ra trong từng lần xác thực. Tuy nhiên, cache, repository và kiến trúc cụ thể vẫn có thể khiến quyền không cập nhật ngay. Không coi Basic là cam kết đồng bộ thời gian thực với DB.

### JWT bearer token

Trong Spring Security OAuth2 Resource Server, một luồng điển hình là:

1. Nhận bearer token do client trình bày.
2. Xác minh JWT bằng `JwtDecoder`, bao gồm chữ ký và điều kiện xác thực liên quan theo cấu hình (ví dụ issuer, thời hạn; audience phải cấu hình kiểm tra phù hợp với API).
3. `JwtAuthenticationConverter` xây `Authentication` và ánh xạ scope/claim đã được tin cậy sang authorities.
4. Authorization dùng tập authority kết quả.

Với quy ước mặc định, JWT có claim:

```json
{
  "sub": "user-17",
  "scope": "orders.read orders.write"
}
```

thường ánh xạ hai scope thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Đây là **payload claim minh họa** chứ không phải JWT hoàn chỉnh hoặc bằng chứng đã ký. Không đọc `scope` từ JSON client tự gửi rồi tự dựng trusted `Authentication`. Đối với claim `roles` hoặc tên tùy biến, cần cấu hình converter tương ứng; **không tự động có `ROLE_ADMIN` chỉ vì token chứa `"roles": ["ADMIN"]`** nếu converter chưa được cấu hình để đọc và ánh xạ nó.

Nếu token tự chứa quyền và có thời hạn dài, thu hồi quyền trong DB không tự xóa claim trên token đã phát hành. Cần TTL, chiến lược thu hồi/rotation, introspection hoặc kiểm tra bổ sung phù hợp với nguy cơ nghiệp vụ.

### Opaque token và OIDC

- **Opaque token:** một nguồn introspection/verification tin cậy thường quyết định token đang hợp lệ và quyền/scopes được trả về, sau đó cấu hình ánh xạ chúng vào `Authentication`.
- **OIDC login:** danh tính từ Identity Provider và quyền ứng dụng là hai khái niệm khác nhau. ID token trả lời về kết quả đăng nhập và một số claim nhận diện; access token, userinfo và dữ liệu nội bộ có mục đích khác. Không dùng claim bất kỳ từ ID token để cho quyền quản trị mà thiếu hợp đồng tin cậy/mapping rõ ràng.

## 9. Lỗi thường gặp khi nạp và sử dụng `GrantedAuthority`

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Đọc `role` từ query, body hoặc header client rồi tạo `SimpleGrantedAuthority` | Người gọi tự nâng quyền | Chỉ ánh xạ từ nguồn đã được xác minh |
| Lấy được `UserDetails` là coi đã đăng nhập | Tìm thấy tài khoản không chứng minh credential hợp lệ | Để `AuthenticationProvider` kiểm tra và phát kết quả |
| Lưu `ADMIN` nhưng gọi `hasRole("ADMIN")` với prefix mặc định | Rule đang tìm `ROLE_ADMIN` | Đồng bộ tên authority hoặc mapping/prefix |
| Token có scope nhưng rule đòi role | `SCOPE_orders.read` không phải `ROLE_USER` | Thiết kế rõ mapping và yêu cầu rule đúng loại quyền |
| Gán role `ADMIN` rồi mặc nhiên cho mọi permission | Không có kế thừa quyền ngầm định | Cấp permission cụ thể hoặc cấu hình hierarchy/policy rõ |
| Đổi quyền trong DB và tin session cũ tự cập nhật | Context đang lưu snapshot quyền | Thiết kế làm mới/thu hồi phiên hoặc kiểm tra quyền hiện thời |
| Tin JWT vì decode được Base64URL | Decode không xác minh chữ ký, issuer, thời hạn, audience | Dùng resource server/decoder và validator đúng cấu hình |
| Chỉ có `authenticated()` trên API dữ liệu nhạy cảm | Xác thực không cho biết người đó có quyền gì | Bổ sung authorization theo authority và đối tượng |
| Chỉ kiểm tra `isAuthenticated()` | Anonymous authentication có thể mang cờ này | Dùng cơ chế trust/authorization của Spring Security |
| Log đầy đủ `Authentication` hoặc token | Có thể rò credential/PII/claim nhạy cảm | Ghi log tối thiểu, che bí mật, phân quyền truy cập log |

Một lỗi nữa là gọi `getAuthorities()` từ biến `Authentication` có thể `null` trên endpoint công khai rồi mặc định sẽ luôn có user thực. Với trang public, hãy xử lý trạng thái anonymous/unauthenticated đúng cách hoặc dùng cơ chế injection/authorization hợp lệ; không lấy danh tính từ `SecurityContextHolder` mà thiếu kiểm tra ngữ cảnh.

## 10. Checklist thiết kế và kiểm thử

Khi xây một chức năng mới, xác định **nguồn quyền**, **đường ánh xạ** và **nơi thực thi chính sách**:

1. Liệt kê các quyền nguyên tử cần thiết (chẳng hạn `report:read`, `report:write`), quy ước đặt tên và vai trò quản trị/cấp quyền.
2. Chỉ rõ ai là nguồn sự thật: DB nội bộ, IDP, claims của access token, dịch vụ policy hay nguồn phối hợp.
3. Nêu cách chuyển dữ liệu nguồn thành `GrantedAuthority`, cách xử lý trùng, quyền không còn hiệu lực, account disabled và lỗi nguồn quyền.
4. Xác minh rằng chỉ kết quả `Authentication` thành công mới được coi là danh tính/quyền của người gọi.
5. Áp rule `hasAuthority`/`hasRole` ở endpoint hoặc method thích hợp; có kiểm tra đối tượng/tenant khi cần.
6. Chọn cách cập nhật/thu hồi quyền đối với session, cache và token còn hiệu lực.
7. Thử ca cho phép, thiếu authority, credential sai, unauthenticated, role-prefix sai, quyền bị thu hồi và truy cập tài nguyên của người khác.
8. Đảm bảo log và endpoint hiển thị dữ liệu không lộ credential, token hay chi tiết quyền nhạy cảm không cần thiết.

### Các câu tự kiểm tra

**Câu 1.** `loadUserByUsername("an")` trả `UserDetails` có `ROLE_ADMIN`. Như vậy request mang username "an" đã có quyền admin chưa?  
**Trả lời:** Chưa. Cần kiểm tra bằng chứng xác thực thành công và tạo trusted `Authentication`; việc tải hồ sơ/quyền không tự xác thực người gọi.

**Câu 2.** Trong cấu hình mặc định, user có `ROLE_MANAGER` nhưng endpoint yêu cầu `hasAuthority("MANAGER")`. Có đạt điều kiện không?  
**Trả lời:** Không. Hai chuỗi không trùng; nếu muốn kiểm tra role có thể dùng `hasRole("MANAGER")` hoặc `hasAuthority("ROLE_MANAGER")`.

**Câu 3.** Token hợp lệ có `scope = "orders.read"`. Vì sao rule `hasAuthority("orders.read")` có thể từ chối?  
**Trả lời:** Resource Server mặc định thường chuyển thành `SCOPE_orders.read`. Cần dùng chuỗi authority thực tế hoặc tùy chỉnh converter.

**Câu 4.** An đã xác thực và có `report:read`, nhưng cố đọc báo cáo của tenant khác. Có chắc được phép không?  
**Trả lời:** Không. Cần kiểm tra phạm vi đối tượng/tenant, ngoài authority tổng quát.

**Câu 5.** Sau khi thu hồi `ROLE_ADMIN` trong DB, session cũ vẫn mở. Có được giả định quyền tự biến mất ở request tiếp theo?  
**Trả lời:** Không. Cần xem `Authentication` được lưu/khôi phục thế nào và thiết kế cơ chế làm mới, thu hồi hoặc kiểm tra quyền hiện thời.

## Kết luận

`GrantedAuthority` biểu diễn **quyền đã được cấp cho principal** dưới dạng mà Spring Security có thể dùng khi đưa ra quyết định truy cập. Với username/password, authorities thường được tải cùng `UserDetails` trong quá trình authentication rồi gắn với `Authentication` thành công; với JWT/opaque token hoặc cơ chế khác, chúng được ánh xạ từ bằng chứng **đã xác minh**. `SecurityContext` cung cấp kết quả đó cho request, còn `AuthorizationManager` hoặc method/domain security quyết định hành động có được phép hay không.

**Nhận diện đúng chủ thể là điều kiện đầu; nạp đúng authority từ nguồn tin cậy và thực thi chính sách đúng chỗ mới tạo thành kiểm soát truy cập hoàn chỉnh.**

### Tài liệu chính thức để đối chiếu

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture / Authorities](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)