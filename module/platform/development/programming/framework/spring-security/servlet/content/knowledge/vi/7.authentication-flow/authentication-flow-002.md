# AuthenticationManager và hợp đồng đầu vào, đầu ra trong Spring Security Servlet

> **Phạm vi:** Spring Security Servlet (ví dụ Spring Security 6.x, Spring Framework 6 và Java 17+). Bài giải thích chính xác `AuthenticationManager` nhận gì, trả về gì hoặc báo lỗi thế nào; cách `ProviderManager` cộng tác với `AuthenticationProvider`; và cách kết quả này được các security filter đưa vào `SecurityContext`. Phần thực hành dùng Spring Boot 3.x để dễ chạy, nhưng các interface được giải thích là của Spring Security, không phụ thuộc Spring Boot.

## 1. Vị trí của AuthenticationManager trong luồng xác thực

Một hệ thống bảo mật phải phân biệt hai câu hỏi:

- **Authentication (xác thực):** Bạn là ai? Bằng chứng cung cấp có hợp lệ không?
- **Authorization (phân quyền):** Danh tính đã xác thực này có được phép thực hiện hành động cụ thể không?

`AuthenticationManager` giải quyết phần **xác thực**. Nó không trực tiếp nhận `HttpServletRequest`, không tự tạo HTTP response, không tự quyết định quyền của một URL, cũng không mặc nhiên lưu người dùng vào session. Những việc này được các bộ phận khác của Spring Security thực hiện.

Hình dung luồng HTTP Basic hoặc form login:

```text
Client gửi HTTP request
        |
        v
Servlet container + Spring Security filter chain
        |
        v
Authentication filter
  - Lấy credentials từ request (form, Basic, token...)
  - Tạo Authentication chưa xác thực
        |
        | authenticate(input)
        v
AuthenticationManager
        |
        v
ProviderManager (một triển khai phổ biến)
  - Chọn AuthenticationProvider hỗ trợ loại token
  - Kiểm tra tài khoản, mật khẩu, token hoặc bằng chứng khác
        |
        +------------------------------+
        |                              |
     THÀNH CÔNG                     THẤT BẠI
        |                              |
   Authentication                 AuthenticationException
   đã xác thực                        |
        |                              v
        |                      Filter xử lý thất bại
        |                      (401 / redirect / handler)
        v
Filter cập nhật SecurityContext
+ lưu context nếu chính sách yêu cầu
        |
        v
AuthorizationFilter / method security
        |
        v
Controller hoặc 403 nếu không đủ quyền
```

Trong Servlet stack, `FilterChainProxy` điều phối các security filter; `AuthenticationManager` là **điểm gọi xác thực**, còn `AuthenticationProvider` thực hiện logic kiểm tra loại credentials cụ thể. Các khái niệm này liên quan nhau nhưng không thay thế nhau.

## 2. Hợp đồng chính thức: `authenticate(Authentication)`

Interface trọng tâm có dạng rút gọn:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

Mã trên trình bày chữ ký interface để học, **không phải file cần tạo thêm trong project**: Spring Security đã cung cấp interface này.

Diễn giải:

1. **Đầu vào:** một đối tượng `Authentication` đại diện cho **yêu cầu xác thực**. Thông thường nó mới chứa username/credential hoặc một token chưa kiểm chứng, vì vậy `isAuthenticated() == false`. Đầu vào cũng có thể là một loại `Authentication` khác, tùy cơ chế tích hợp.
2. **Thành công:** trả về một `Authentication` **đã được xác thực**, được điền thông tin principal và granted authorities theo kết quả kiểm chứng. Đối tượng kết quả **không nhất thiết là cùng instance hoặc cùng class** với đầu vào.
3. **Thất bại:** ném một exception kế thừa `AuthenticationException`, ví dụ `BadCredentialsException`, `DisabledException`, `LockedException` hay `ProviderNotFoundException`. Bên gọi cần xử lý thất bại này.
4. **Không có quyền bảo đảm:** method không tự đặt kết quả vào `SecurityContextHolder`, không tự lưu session, không tự làm người dùng “đăng nhập mãi mãi”, không trả response HTTP 200/401/403, và không có nghĩa là mọi endpoint đều được phép.
5. **Không xem `null` là xác thực thành công.** Một `AuthenticationProvider` có thể trả `null` để nhường cho provider khác; nhưng `AuthenticationManager` thành công phải trả về đối tượng kết quả phù hợp với hợp đồng.

Điểm rất quan trọng: **đầu vào và đầu ra cùng có kiểu `Authentication`, nhưng mang ý nghĩa tin cậy khác nhau**. Không được xem một username, role hoặc `isAuthenticated` do phía client cung cấp như bằng chứng đã xác thực.

## 3. `Authentication` chứa những thông tin gì?

`org.springframework.security.core.Authentication` biểu diễn đồng thời **yêu cầu xác thực** và **danh tính đã xác thực**. Các accessor thường dùng:

| Thuộc tính / method | Ở đầu vào chưa xác thực | Ở đầu ra thành công |
| --- | --- | --- |
| `getPrincipal()` | Thường là username (chuỗi) hoặc token/định danh ban đầu | `UserDetails`, đối tượng principal hoặc danh tính đã được tin cậy |
| `getCredentials()` | Mật khẩu, secret, token hoặc bằng chứng cần kiểm tra | Có thể đã bị xóa để giảm nguy cơ lộ; **không bảo đảm luôn `null`** |
| `getDetails()` | Có thể là metadata của request (IP, session ID), nếu filter thêm | Tùy provider/filter; không nên giả định luôn có hoặc luôn được sao chép |
| `getAuthorities()` | Thường rỗng, hoặc không đáng tin cậy nếu chưa xác thực | Các `GrantedAuthority` đã được provider/nguồn tin cậy xác định |
| `isAuthenticated()` | Thường `false` | Thường `true` đối với token người dùng xác thực thành công |
| `getName()` | Có thể suy ra tên từ principal ban đầu | Tên danh tính để hiển thị/log theo chính sách thích hợp |

Ví dụ cho username/password:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "secret123"
        );
// request.isAuthenticated() == false
// request.getPrincipal().equals("linh")
// request.getCredentials() chứa mật khẩu đầu vào
```

Đây là **fragment Java**, cần import `Authentication` và `UsernamePasswordAuthenticationToken`; không phải chương trình chạy độc lập. Dùng factory `unauthenticated` giúp diễn đạt chính xác đây là thông tin **chưa được kiểm chứng**.

Sau khi `AuthenticationManager` xác minh thành công, result của cơ chế `DaoAuthenticationProvider` thường là `UsernamePasswordAuthenticationToken` đã xác thực, principal là `UserDetails` và có authorities (ví dụ `ROLE_USER`). `ProviderManager` mặc định cố gắng xóa credentials khỏi result nếu đối tượng hỗ trợ `CredentialsContainer`.

### `isAuthenticated()` không có nghĩa là “được phép truy cập”

- `true` cho biết token tự biểu diễn trạng thái được xác thực; **authorization** vẫn phải kiểm tra role/authority, các điều kiện khác và chính sách của endpoint.
- Không tự gọi `setAuthenticated(true)` trên token do người dùng gửi để “bỏ qua đăng nhập”. Với `UsernamePasswordAuthenticationToken`, factory `authenticated(principal, credentials, authorities)` hoặc constructor nhận authorities được dành cho logic **đã có nguồn tin cậy kiểm chứng**, chẳng hạn provider.
- Một số loại authentication đặc biệt (ví dụ `AnonymousAuthenticationToken`) cũng có thể báo `isAuthenticated() == true`; Spring Security dùng cơ chế nhận biết anonymous khi áp dụng rule `authenticated()`. Vì thế không thay policy của framework bằng việc kiểm tra mỗi boolean `isAuthenticated()` tự viết.
- `getAuthorities()` ở **đầu vào chưa xác thực** không phải danh sách quyền được phép tin. Quyền phải đến từ nguồn người dùng/IdP/token đã xác minh, không từ JSON role client tự khai.

### Principal không phải lúc nào cũng là chuỗi username

Với username/password qua `DaoAuthenticationProvider`, principal có thể là `UserDetails`. Với JWT Resource Server, principal thường là đối tượng JWT/claim phù hợp với token; với OAuth2 login hay pre-auth, nó có thể có kiểu khác. Nếu cần tên ở nhiều cơ chế, ưu tiên `authentication.getName()` hoặc xử lý loại principal rõ ràng, không cast mù thành `UserDetails`.

## 4. `ProviderManager`: triển khai phổ biến của AuthenticationManager

`ProviderManager` triển khai `AuthenticationManager` bằng cách thử danh sách các `AuthenticationProvider`. Mỗi provider có hai phương thức trọng tâm:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

Đây là chữ ký rút gọn để giải thích contract, không cần tạo file riêng.

- `supports(Class<?>)` cho biết provider **có thể xử lý loại token** đó, không bảo đảm credentials sẽ hợp lệ.
- Nếu hỗ trợ, `authenticate(...)` có thể trả về `Authentication` đã xác thực.
- Nếu provider **không thể quyết định**, nó có thể trả `null` để `ProviderManager` tiếp tục thử provider tiếp theo.
- Nếu provider kết luận xác thực thất bại, nó thường ném `AuthenticationException`. Tùy loại lỗi và cách cấu hình, `ProviderManager` có thể thử provider khác, ưu tiên lỗi trạng thái tài khoản, hoặc chuyển sang parent manager.
- Nếu không có provider phù hợp và không có parent xử lý, `ProviderManager` có thể ném `ProviderNotFoundException`.

```text
ProviderManager.authenticate(request)
    |
    +-- provider A.supports(request.class)?
    |      +-- không -> thử provider B
    |      +-- có -> authenticate(request)
    |              +-- kết quả hợp lệ -> thành công
    |              +-- null -> thử provider B
    |              +-- exception -> xử lý theo loại lỗi / chính sách
    |
    +-- provider B ...
    |
    +-- parent AuthenticationManager (nếu được cấu hình và cần dùng)
    |
    +-- kết quả đã xác thực HOẶC AuthenticationException
```

Đặc biệt, `ProviderManager` không phải là một `AuthenticationProvider`; nó là manager **điều phối** providers. Một triển khai phổ biến cho form/Basic là `DaoAuthenticationProvider`, nơi việc xác thực được chia thành:

1. Tra cứu `UserDetails` theo username qua `UserDetailsService`.
2. Kiểm tra tình trạng tài khoản (khóa, disabled, hết hạn... tùy provider/checker).
3. So khớp mật khẩu qua `PasswordEncoder.matches(rawPassword, encodedPassword)`.
4. Tạo `Authentication` thành công với principal và authorities đã được xác minh.
5. Quản lý thất bại bằng `AuthenticationException` phù hợp.

Một `ProviderManager` có thể chứa các provider khác nhau cho password, pre-auth hoặc loại token riêng. **Một provider phải xử lý đúng loại `Authentication` mà filter tạo ra**; ví dụ tự đưa JWT string vào `UsernamePasswordAuthenticationToken` rồi kỳ vọng provider password tự xác minh chữ ký JWT là sai mô hình.

### Xóa credentials sau thành công

Mặc định, `ProviderManager` cố gắng gọi `eraseCredentials()` trên đối tượng result nếu nó hỗ trợ `CredentialsContainer` (`eraseCredentialsAfterAuthentication` mặc định là `true`). Mục đích là không giữ plaintext password/secret quá lâu trong memory hoặc context. Điều này cũng có thể ảnh hưởng đối tượng lồng bên trong principal nếu chúng chia sẻ cùng instance, nên khi dùng **cache `UserDetails`**, cần lưu ý tránh để thao tác xóa credentials phá dữ liệu mà cache dự kiến sẽ dùng cho các lần xác thực sau.

Không log `getCredentials()` hoặc toàn bộ đối tượng `Authentication` theo cách làm lộ secret, kể cả khi nghĩ rằng result đã được xóa credentials. Token bearer và dữ liệu `details` cũng có thể nhạy cảm.

## 5. Một vòng đời xác thực trong Servlet

Ví dụ browser gửi form đến `POST /login`:

1. `UsernamePasswordAuthenticationFilter` (khi form login được bật) đọc username/password và tạo `UsernamePasswordAuthenticationToken` **chưa xác thực**.
2. Filter chuyển token này tới `AuthenticationManager.authenticate(...)`.
3. `ProviderManager` thử provider phù hợp; `DaoAuthenticationProvider` lấy `UserDetails`, so mật khẩu, kiểm tra tài khoản.
4. Nếu thành công, manager trả `Authentication` đã xác thực; filter xử lý các bước thành công như session authentication strategy và tạo `SecurityContext` chứa result.
5. Filter lưu `SecurityContext` qua `SecurityContextRepository` theo chiến lược phù hợp, rồi gọi success handler (ví dụ redirect).
6. Những request tiếp theo có thể tải context từ session; `AuthorizationFilter` và/hoặc method security kiểm tra quyền trước khi cho phép nghiệp vụ.
7. Nếu thất bại, filter gọi failure handler hoặc cơ chế entry point tương ứng; xác thực **không thành công** và không cấp các quyền của người dùng mong muốn.

Đây là đường đi **mang tính khái niệm**; thứ tự filter và lớp cụ thể có thể thay đổi theo cấu hình/phiên bản. HTTP Basic dùng `BasicAuthenticationFilter` thay vì form login filter; Bearer token dùng bộ lọc/token/provider thích hợp của Resource Server. Nguyên lý `Authentication` đầu vào → `AuthenticationManager` → kết quả/exception vẫn giữ nguyên.

### `SecurityContextHolder` là chuyện khác

`SecurityContextHolder` cho phép truy cập context của luồng xử lý hiện tại. **Gọi trực tiếp `manager.authenticate(input)` từ một service hoặc chương trình Java không tự đặt result vào `SecurityContextHolder`**. Trong HTTP flow thông thường, filter thành công là nơi thực hiện việc đó và cấu hình nơi lưu context.

Ví dụ minh họa **khi đã có `Authentication result` hợp lệ**:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

try {
    System.out.println(SecurityContextHolder.getContext()
            .getAuthentication().getName());
} finally {
    SecurityContextHolder.clearContext();
}
```

Đây là fragment, cần import `SecurityContext`, `SecurityContextHolder`; không phải quy trình đăng nhập web hoàn chỉnh. Đặt ThreadLocal context **không tự đảm bảo context được lưu qua nhiều HTTP request**: ứng dụng phải dùng `SecurityContextRepository` và các biện pháp session/CSRF cần thiết. Tránh tự viết login controller bỏ qua framework filter/handler khi chưa hiểu rõ cơ chế lưu context, session fixation protection và failure handling.

## 6. Ví dụ chạy được: AuthenticationManager + ProviderManager + HTTP Basic

Ta xây một ứng dụng Spring Boot MVC/Servlet nhỏ dùng **Spring Boot 3.3.5** (phiên bản minh họa), **Java 17+**. Có hai tài khoản trong bộ nhớ:

| Username | Mật khẩu demo | Authorities |
| --- | --- | --- |
| `linh` | `secret123` | `ROLE_USER` |
| `quan` | `admin123` | `ROLE_ADMIN` |

Để minh họa rõ đầu vào/đầu ra, ứng dụng sẽ:

- Chủ động tạo `ProviderManager` với một `DaoAuthenticationProvider`.
- Gọi `authenticate(...)` ngay sau khi khởi động để in dữ liệu trước/sau.
- Cấu hình HTTP Basic dùng **cùng** `AuthenticationManager` cho endpoint `/profile` và `/admin`.
- Kiểm tra khác biệt giữa xác thực thành công và quyền truy cập URL.

Cấu trúc thư mục:

```text
authentication-contract/
├── pom.xml
└── src/main/java/example/authcontract/
    ├── AuthenticationContractApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authentication-contract</artifactId>
    <version>1.0.0</version>

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
```

### 6.2. `AuthenticationContractApplication.java`

```java
package example.authcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationContractApplication.class, args);
    }
}
```

### 6.3. `SecurityConfig.java`

```java
package example.authcontract;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("secret123"))
                .roles("USER")
                .build();
        UserDetails quan = User.withUsername("quan")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(linh, quan);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http, AuthenticationManager manager) throws Exception {

        // Đảm bảo security filters dùng đúng manager được khai báo.
        http.authenticationManager(manager);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/profile").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    ApplicationRunner authenticationProbe(AuthenticationManager manager) {
        return args -> {
            // Tạo yêu cầu chưa xác thực.
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "linh", "secret123");

            System.out.println("input.authenticated=" + input.isAuthenticated());

            // Cùng một interface Authentication nhưng đã được xác minh.
            Authentication output = manager.authenticate(input);
            System.out.println("output.authenticated=" + output.isAuthenticated());
            System.out.println("output.name=" + output.getName());
            System.out.println("output.authorities=" + output.getAuthorities());
            System.out.println("output.credentialsErased="
                    + (output.getCredentials() == null));
            System.out.println("context.autoFilled="
                    + (SecurityContextHolder.getContext()
                            .getAuthentication() != null));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "linh", "wrong-password"));
            } catch (BadCredentialsException ex) {
                System.out.println("failure=" + ex.getClass().getSimpleName());
            }
        };
    }
}
```

**Giải thích chính xác từng phần:**

- `UserDetailsService` trả về user đã cấu hình; `PasswordEncoder` dùng BCrypt. Lưu mật khẩu đã hash, không so trực tiếp `rawPassword.equals(encodedPassword)`.
- `DaoAuthenticationProvider` có nhiệm vụ tra user và so mật khẩu, là một `AuthenticationProvider`.
- `new ProviderManager(List.of(provider))` tạo `AuthenticationManager` dùng provider cụ thể; không cần tự triển khai interface cho password login thông thường.
- `Authentication input` được tạo với trạng thái **unauthenticated**, chỉ có username/mật khẩu demo; người gọi không tự gắn `ROLE_USER` vào đó.
- `manager.authenticate(input)` xác minh và trả `Authentication output` có authorities theo user trong store.
- `ProviderManager` mặc định xóa credentials khỏi result khi khả thi; ví dụ thành công này dùng token hỗ trợ xóa credential.
- `SecurityContextHolder` vẫn trống trong phần probe (chạy bên ngoài request/filter). Điều này chứng minh manager **không tự “login” vào một HTTP session**.
- HTTP Basic filter của `SecurityFilterChain` được trỏ về chính manager qua `http.authenticationManager(manager)`. Phần HTTP được filter xử lý khác với phần gọi trực tiếp ở `ApplicationRunner`.

**Lưu ý:** `http.authenticationManager(manager)` đặt một manager cho chain đang xây dựng. Trong dự án thực tế, cũng có thể để Spring Security xây manager từ các provider/bean hiện có, hoặc lấy global manager qua `AuthenticationConfiguration`. Khi có nhiều `SecurityFilterChain`, cần xác định chain nào dùng manager/provider nào; đừng vô tình tạo manager thiếu provider cho loại credentials mà filter của chain phát ra.

### 6.4. `DemoController.java`

```java
package example.authcontract;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

Controller nhận `Authentication` **đã được filter đưa vào context của request**. Điều đó không có nghĩa `AuthenticationManager` tự chèn vào context. Cả hai endpoint đều có authentication hợp lệ trước khi method chạy; `/admin` còn phải thỏa authority `ROLE_ADMIN`.

### 6.5. Build, chạy và kết quả mong đợi

Từ thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Khi khởi động thành công, ngoài các log thông thường của Spring Boot, phần `ApplicationRunner` in các dòng dưới đây theo thứ tự:

```text
input.authenticated=false
output.authenticated=true
output.name=linh
output.authorities=[ROLE_USER]
output.credentialsErased=true
context.autoFilled=false
failure=BadCredentialsException
```

Kết quả này minh họa: input là **lời yêu cầu**, output là **danh tính đã xác minh**, credentials có thể bị xóa, thất bại được thể hiện bằng exception và manager không tự set context.

Test HTTP với Tomcat nhúng ở `localhost:8080` (cú pháp `curl` dành cho shell POSIX):

```bash
# Chưa gửi bằng chứng xác thực:
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/profile
# 401

# Mật khẩu sai:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:wrong-password http://localhost:8080/profile
# 401

# User hợp lệ, endpoint chỉ yêu cầu xác thực:
curl -s -u linh:secret123 http://localhost:8080/profile
# profile:linh

# User đã xác thực, nhưng không có ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:secret123 http://localhost:8080/admin
# 403

# Tài khoản có ROLE_ADMIN:
curl -s -u quan:admin123 http://localhost:8080/admin
# admin:quan
```

Các dòng comment là **kết quả kỳ vọng** với cấu hình nguyên vẹn. HTTP Basic gửi credentials ở mỗi request, vì vậy chỉ thử trong môi trường cục bộ hoặc qua **HTTPS**; không truyền mật khẩu thật trên HTTP không mã hóa.

### Phân biệt lỗi xác thực và lỗi phân quyền

- `/profile` không có credential hoặc mật khẩu sai: filter gọi manager, kết quả không tạo authenticated principal → **401** (Basic challenge).
- `/admin` với `linh` và mật khẩu đúng: manager đã xác thực thành công, nhưng `AuthorizationFilter` thấy thiếu `ROLE_ADMIN` → **403**.
- `/admin` với `quan`: xác thực và kiểm tra quyền đều đạt → **200**.

`AuthenticationManager` **không trực tiếp trả 401 hay 403**. Nó trả `Authentication` hoặc ném `AuthenticationException`; chính các filter, authentication entry point và access-denied handling chuyển kết quả thành HTTP response.

## 7. Những lỗi thường gặp của AuthenticationManager

| Hiện tượng | Nguyên nhân khả dĩ | Cách xem xét |
| --- | --- | --- |
| `ProviderNotFoundException` | Không có provider hỗ trợ class của input token | Kiểm tra `supports()`, cách tạo token và danh sách providers |
| `BadCredentialsException` | Mật khẩu/token không hợp lệ; hoặc user không tồn tại nhưng provider che chi tiết để tránh lộ tài khoản | Kiểm tra encoder, dạng hash, tên user và nguồn credentials; không trả lỗi chi tiết cho client |
| `DisabledException` / `LockedException` | User bị vô hiệu hóa hoặc khóa theo chính sách provider | Kiểm tra `UserDetails` và account status; không mở quyền để “sửa nhanh” |
| `CredentialsExpiredException` / `AccountExpiredException` | Credentials hoặc tài khoản đã hết hạn theo source/checker | Thiết kế flow đổi credentials/kích hoạt lại phù hợp |
| Gọi `authenticate` thành công nhưng request sau vẫn anonymous | Không có filter lưu context/session, hoặc code gọi manager ngoài HTTP filter mà không xử lý context | Dùng cơ chế đăng nhập/filter chuẩn, kiểm tra `SecurityContextRepository` |
| Nhận `Authentication` nhưng `getCredentials()==null` | ProviderManager đã xóa secret như thiết kế | Không dùng result để đọc lại mật khẩu/token ban đầu |
| `getPrincipal()` ép kiểu `String` thất bại | Provider trả `UserDetails` hoặc principal khác | Dùng `getName()` hoặc xử lý theo loại authentication |
| Client tự gửi role rồi vào được API | Ứng dụng tin quyền từ đầu vào chưa xác minh | Chỉ cấp authorities sau khi kiểm chứng bằng provider/nguồn tin cậy |
| Login thành công nhưng vẫn 403 | Authentication hợp lệ nhưng authorities không thỏa rule | Xem `hasRole` / `hasAuthority`, scope và role prefix |
| Không rõ manager nào được gọi trong nhiều chain | Có nhiều `AuthenticationManager`, provider hoặc `SecurityFilterChain` | Rà soát wiring, `http.authenticationManager`, `@Order` và matcher |
| SecurityContext mất khi xử lý async/thread khác | Context mặc định gắn với thread/strategy, không tự truyền theo mọi kiểu thực thi | Dùng cơ chế context propagation của Spring Security, không chia sẻ ThreadLocal sai cách |

### Ba lỗi thiết kế nghiêm trọng cần tránh

**1. Tạo token “đã authenticated” từ dữ liệu client khi chưa kiểm tra.**

```java
// SAI: role lấy từ dữ liệu chưa tin cậy, không qua manager/provider.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
        userNameFromRequest, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

Đây là **fragment mô tả antipattern**, không phải code hợp lệ về mặt nghiệp vụ. Nó bỏ qua hợp đồng xác thực. Factory tạo authenticated token chỉ được dùng trong code phía server **sau khi đã có kết quả kiểm chứng từ nguồn tin cậy**.

**2. Gọi manager rồi tưởng rằng đã có session login.**

`manager.authenticate(input)` không bảo đảm result được đưa vào `SecurityContextRepository` hoặc lưu sang request sau. Đối với form login, ưu tiên dùng `formLogin`/filter của Spring Security thay vì tự viết controller xử lý mật khẩu, session, CSRF và handler.

**3. Chuyển mọi `AuthenticationException` thành “lỗi hệ thống 500” hoặc trả thông báo quá chi tiết.**

Sai mật khẩu là xác thực thất bại bình thường, không phải lỗi hệ thống. Filter/cơ chế entry point nên trả response phù hợp với client; nhưng đừng công khai user có tồn tại, bị khóa vì lý do gì hoặc secret nào sai nếu chính sách bảo mật không cho phép. Log để điều tra theo cách không lộ thông tin nhạy cảm.

## 8. Đi sâu vào exception và xử lý trạng thái tài khoản

Một số loại lỗi điển hình đều là `AuthenticationException`:

| Exception | Ý nghĩa khái quát |
| --- | --- |
| `BadCredentialsException` | Bằng chứng xác thực không hợp lệ |
| `UsernameNotFoundException` | Nguồn người dùng không tìm thấy username; thường được `DaoAuthenticationProvider` che thành `BadCredentialsException` theo cấu hình mặc định |
| `DisabledException` | Tài khoản không được phép đăng nhập vì disabled |
| `LockedException` | Tài khoản bị khóa |
| `AccountExpiredException` | Tài khoản đã hết hạn |
| `CredentialsExpiredException` | Credential đã hết hạn |
| `ProviderNotFoundException` | Không tìm được provider hỗ trợ kiểu authentication |
| `AuthenticationServiceException` | Sự cố dịch vụ xác thực/hạ tầng cần được phân biệt với mật khẩu sai |

Theo contract của `AuthenticationManager`, các lỗi về tài khoản bị disabled/locked và kiểm tra credentials có thứ tự kiểm tra thích hợp; provider thường dừng ngay ở các lỗi trạng thái nghiêm trọng. Tuy nhiên thứ tự thực tế và chi tiết lỗi vẫn phụ thuộc provider, nguồn user và cấu hình.

**Không suy luận rằng một HTTP status ánh xạ 1:1 tới một exception class.** Filter, handler, session state và cơ chế đăng nhập quyết định cách phản hồi. Form login thất bại có thể redirect về trang login có thông báo; Basic/Bearer thường dùng response 401 với challenge thích hợp. 403 thường thuộc **authorization/CSRF** hơn là một giá trị return của manager.

## 9. Quản lý manager trong ứng dụng có nhiều phương thức xác thực

Một ứng dụng có thể phục vụ đồng thời form login, Basic, JWT/OAuth2 Resource Server hoặc các cơ chế xác thực khác. Có vài cấu hình hợp lệ:

- Một `ProviderManager` chứa nhiều `AuthenticationProvider`, mỗi provider hỗ trợ những authentication token riêng.
- Nhiều `SecurityFilterChain`, mỗi chain cấu hình security filters và `AuthenticationManager` phù hợp.
- Trường hợp nâng cao, dùng `AuthenticationManagerResolver<HttpServletRequest>` khi cần chọn manager động theo request (chẳng hạn nhiều issuer/tenant có trust boundary rõ).

Không nên tự xây một manager “đại trà” trả token authenticated chỉ vì request có username. Với JWT, provider/decoder phải xác minh chữ ký, issuer, audience, thời hạn và các claims liên quan theo thiết kế. Với password, phải có `PasswordEncoder.matches` và account checks.

**Phân biệt `AuthenticationManager` và `UserDetailsService`:** `UserDetailsService` chỉ cung cấp thông tin người dùng theo username, **không tự chứng minh** mật khẩu hợp lệ. `DaoAuthenticationProvider` phối hợp nó với `PasswordEncoder` và các bước kiểm tra để xác thực. `AuthenticationManager` là hợp đồng điều phối bên ngoài.

**Phân biệt AuthenticationManager và AuthorizationManager:** tên gần giống nhau nhưng nhiệm vụ khác. `AuthenticationManager` biến bằng chứng hợp lệ thành `Authentication` đáng tin cậy; `AuthorizationManager` (trong cơ chế authorization hiện đại) ra quyết định quyền truy cập dựa trên authentication và tài nguyên. Không dùng chúng thay thế nhau.

## 10. Kiểm tra bằng test: mô tả các case tối thiểu

Trong test unit hoặc integration, cần xác minh cả hợp đồng của manager lẫn HTTP flow. Bộ trường hợp cơ bản:

| Trường hợp | Kỳ vọng ở manager | Kỳ vọng ở ứng dụng HTTP Basic mẫu |
| --- | --- | --- |
| Username/mật khẩu hợp lệ `linh/secret123` | `Authentication` thành công, `getName()=="linh"`, authority `ROLE_USER` | `GET /profile` → 200 |
| Mật khẩu sai | Ném `BadCredentialsException` | `GET /profile` → 401 |
| Không có Basic credentials | Filter chưa có credential đủ để xác thực user | `GET /profile` → 401 |
| `linh` truy cập admin | Manager xác thực thành công | `GET /admin` → 403 do rule role |
| `quan` truy cập admin | Manager xác thực thành công, `ROLE_ADMIN` | `GET /admin` → 200 |
| Token đầu vào không provider nào hỗ trợ | Ném `ProviderNotFoundException` nếu không có parent giải quyết | Tùy filter/entry point của cơ chế |
| Gọi manager trực tiếp ngoài request | Trả output nhưng không tự set context | Không tạo phiên đăng nhập browser tự động |

Có thể viết test HTTP bằng Spring Security Test (`spring-security-test`), MockMvc hoặc test thật bằng HTTP client. Khi dùng `@WithMockUser`, cần hiểu đây là **mô phỏng authentication**, không chạy password validation của provider. Muốn test hợp đồng của `DaoAuthenticationProvider`/`AuthenticationManager`, phải thực sự gọi manager với credentials và kiểm tra exception/result.

## 11. Câu hỏi tự ôn

1. **Đầu vào của `AuthenticationManager.authenticate` là gì?** Một `Authentication` biểu diễn yêu cầu xác thực và bằng chứng cần kiểm tra, thường chưa được xác thực.
2. **Manager thành công trả về gì?** Một `Authentication` chứa danh tính, trạng thái xác thực và authorities dựa trên kết quả kiểm chứng.
3. **Manager thất bại trả về `false` hay HTTP 401?** Không. Nó ném `AuthenticationException`; filter/handler quyết định HTTP response.
4. **`AuthenticationProvider.authenticate` có thể trả `null` không?** Có, khi provider không thể quyết định và muốn nhường cho provider khác; không được xem `null` là đăng nhập thành công.
5. **`supports()` trả true có nghĩa credentials hợp lệ?** Không. Chỉ nghĩa provider có thể xử lý loại token đó.
6. **Sau `manager.authenticate`, `SecurityContextHolder` tự có user?** Không khi bạn gọi manager trực tiếp; security filter hoặc code tích hợp phù hợp phải xử lý context.
7. **Sau khi xác thực, `getCredentials()` còn mật khẩu không?** Không nên phụ thuộc vào điều đó; `ProviderManager` thường xóa credentials ở token hỗ trợ cơ chế xóa.
8. **Vì sao `linh` đúng mật khẩu nhưng vào `/admin` bị 403?** Đúng mật khẩu là authentication; quyền `ROLE_ADMIN` là authorization riêng.
9. **Có nên gửi role từ request vào `UsernamePasswordAuthenticationToken.authenticated(...)`?** Không, nếu role chưa được nguồn tin cậy kiểm chứng.
10. **`UserDetailsService` có phải là `AuthenticationManager` không?** Không; nó tìm user, còn manager/provider kiểm chứng credentials và cấp kết quả xác thực.

## 12. Checklist ghi nhớ khi triển khai

- [ ] Tạo **authentication request token** đúng loại và để trạng thái chưa xác thực.
- [ ] Provider hỗ trợ token qua `supports()` và kiểm chứng bằng nguồn tin cậy.
- [ ] Nhận `Authentication` đầu ra đáng tin cậy hoặc xử lý `AuthenticationException`; không tự cấp quyền từ input.
- [ ] Không log mật khẩu, credentials, token hoặc dữ liệu nhạy cảm trong `details`.
- [ ] Đừng giả định principal luôn là `String` hoặc `UserDetails`; kiểm tra contract theo cơ chế đang dùng.
- [ ] Dùng filter/handler/context repository phù hợp cho việc đăng nhập HTTP; manager không tự tạo session.
- [ ] Kiểm tra phân quyền riêng sau authentication; có authenticated user chưa chắc được vào tài nguyên.
- [ ] Với nhiều provider/chain, xác minh chính xác manager và provider được chọn, tránh mismatch.
- [ ] Viết test cho đầu ra thành công, mật khẩu sai, tài khoản không hợp lệ, không có provider và quyền bị từ chối.

**Kết luận:** Hợp đồng của `AuthenticationManager` là **`Authentication` đầu vào chưa tin cậy → kiểm chứng qua provider → `Authentication` đầu ra đáng tin cậy, hoặc `AuthenticationException`**. Các filter Servlet đảm nhận phần lấy dữ liệu từ HTTP, lưu `SecurityContext` và chuyển thất bại thành HTTP response; authorization xử lý câu hỏi người dùng đã xác thực **được làm gì**.