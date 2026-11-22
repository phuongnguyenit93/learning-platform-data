# enabled, accountNonLocked, accountNonExpired và credentialsNonExpired trong Spring Security

## 1. Bốn cờ trạng thái tài khoản dùng để làm gì?

Trong **Spring Security Servlet**, nhiều ứng dụng xác thực người dùng bằng username/password thông qua một `UserDetailsService` và `AuthenticationProvider` phù hợp, thường là `DaoAuthenticationProvider`. Spring Security cần biết không chỉ **password có đúng** mà còn **tài khoản/credentials có còn đủ điều kiện đăng nhập hay không**.

Giao diện `org.springframework.security.core.userdetails.UserDetails` cung cấp bốn phép kiểm tra:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Tên dễ gây nhầm vì ba phương thức có dạng **phủ định kép**: `NonLocked` nghĩa là **không bị khóa**, `NonExpired` nghĩa là **chưa hết hạn**. Trong cả bốn trường hợp, giá trị **`true` thường biểu thị điều kiện đang hợp lệ**. `false` biểu thị điều kiện không đạt và thường khiến quy trình xác thực username/password của `DaoAuthenticationProvider` bị từ chối.

Bảng đọc nhanh:

| Thuộc tính của `UserDetails` | Khi `true` | Khi `false` | Ví dụ nghiệp vụ |
| --- | --- | --- | --- |
| `isEnabled()` | Tài khoản được bật | Tài khoản bị vô hiệu hóa | Chưa xác minh email, quản trị viên vô hiệu hóa account |
| `isAccountNonLocked()` | Tài khoản không bị khóa | Tài khoản đang bị khóa | Khóa bảo mật do nhiều lần login sai |
| `isAccountNonExpired()` | Tài khoản chưa hết hạn | Tài khoản đã hết hạn | Tài khoản hợp đồng/nhân viên hết hiệu lực |
| `isCredentialsNonExpired()` | Credentials chưa hết hạn | Credentials đã hết hạn | Mật khẩu phải được đổi theo chính sách |

**Quan trọng:** Đây là bốn điều kiện **đủ tư cách xác thực của tài khoản** theo mô hình `UserDetails`. Chúng **không** phải role/authority và không thay thế chính sách `hasRole`, `hasAuthority`, quyền sở hữu tài nguyên hoặc quyền trên tenant.

Ví dụ một user có `ROLE_ADMIN` nhưng `isEnabled() == false` vẫn có thể bị từ chối ngay ở bước authentication. Ngược lại, một tài khoản có cả bốn cờ `true` và xác thực thành công vẫn không được tự động truy cập endpoint chỉ dành cho admin.

## 2. Vì sao tên lại là NonLocked, NonExpired?

Có hai kiểu lưu dữ liệu thường gặp:

- Ở **cơ sở dữ liệu nghiệp vụ**, lập trình viên thích cột mang nghĩa “trạng thái xấu”: `locked`, `accountExpired`, `credentialsExpired` hoặc `disabled`. Khi giá trị bằng `true`, vấn đề đang tồn tại.
- Trong **`UserDetails`**, ba phương thức mang nghĩa “trạng thái tốt”: `isAccountNonLocked()`, `isAccountNonExpired()` và `isCredentialsNonExpired()`. Khi giá trị bằng `true`, điều kiện đó hợp lệ.

Do đó phép ánh xạ thường là:

~~~java
// Ví dụ ánh xạ từ mô hình lưu trạng thái "xấu" sang UserDetails.
boolean enabled = !account.disabled();
boolean accountNonLocked = !account.locked();
boolean accountNonExpired = !account.accountExpired();
boolean credentialsNonExpired = !account.credentialsExpired();
~~~

Đây là snippet minh họa: kiểu `account`/các accessor là mô hình giả định, chưa phải Java chạy độc lập.

**Lỗi đảo điều kiện rất nguy hiểm:** lưu `locked = true` rồi viết `isAccountNonLocked() { return locked; }` sẽ khiến tài khoản bị khóa lại được xem như **không khóa**. Hãy ghi rõ chiều nghĩa của tên cột và test cả trạng thái `true/false` khi xây một `UserDetails` tùy chỉnh.

### Cách đọc bốn biểu thức khi debug

~~~text
isEnabled()                  == true  -> được bật
isAccountNonLocked()         == true  -> không bị khóa
isAccountNonExpired()        == true  -> chưa hết hạn tài khoản
isCredentialsNonExpired()    == true  -> credentials chưa hết hạn

Nếu một điều kiện được provider áp dụng và trả về false:
quy trình username/password authentication thường không thành công.
~~~

Không nên gom bốn cờ thành một cột `active` duy nhất nếu nghiệp vụ cần phân biệt lý do và cách khắc phục. Một account bị khóa tạm thời có thể được mở lại; một account hết hạn hợp đồng cần xử lý khác; mật khẩu hết hạn có thể yêu cầu quy trình đổi mật khẩu an toàn.

## 3. Phân biệt từng cờ với tình huống thực tế

### 3.1. enabled: tài khoản có được phép đăng nhập hay không?

`isEnabled()` thường được dùng cho **kích hoạt/vô hiệu hóa tài khoản**. Các ví dụ:

- Tài khoản vừa đăng ký nhưng chưa hoàn thành xác minh được yêu cầu.
- Người dùng bị quản trị viên vô hiệu hóa.
- Tài khoản nhân sự không còn được phép sử dụng hệ thống.
- User test hoặc tài khoản dịch vụ bị tạm dừng theo chính sách nội bộ.

Nếu `enabled == false`, cơ chế kiểm tra trạng thái của `DaoAuthenticationProvider` thường ném `DisabledException` trong quá trình xác thực. Điều này khác **sai mật khẩu** và khác việc đã xác thực thành công nhưng thiếu role cho endpoint.

Tránh dùng duy nhất cờ `enabled` để biểu diễn cả trạng thái khóa do thử password sai, hết hạn mật khẩu và hết hạn hợp đồng. Các trạng thái này có ý nghĩa và quy trình phục hồi khác nhau.

### 3.2. accountNonLocked: tài khoản có đang bị khóa không?

`isAccountNonLocked()` bằng `false` nghĩa là **bị khóa**. Một mô hình khóa tạm thời có thể có:

~~~text
failedLoginAttempts = 5
lockUntil = 2026-11-06T12:00:00Z
accountNonLocked = currentTime >= lockUntil
~~~

Đây chỉ là ví dụ về cách thiết kế trạng thái; không phải thuật toán built-in tự động của Spring Security. **`UserDetails` và `DaoAuthenticationProvider` không tự triển khai toàn bộ chính sách đếm lần đăng nhập sai, tạo khóa tạm thời rồi tự mở khóa** chỉ vì bạn có phương thức `isAccountNonLocked()`. Ứng dụng cần tự quản lý sự kiện thất bại, cơ chế chống brute-force/rate-limit, lưu trạng thái khóa và điều kiện mở khóa.

Khi giá trị `false`, default account-status checker thường tạo `LockedException`. Khóa tài khoản chỉ là **một** biện pháp; login endpoint vẫn cần xem xét throttling, MFA và chống credential stuffing.

### 3.3. accountNonExpired: thời hạn sử dụng tài khoản

`isAccountNonExpired()` bằng `false` nghĩa là tài khoản đã hết hạn theo chính sách. Điều này thường gắn với ngày kết thúc hợp đồng, quyền truy cập có thời hạn, tài khoản tạm thời của đối tác hoặc quy định lifecycle của nhân sự.

Ví dụ một quy tắc tính từ thời điểm hiện tại:

~~~java
boolean accountNonExpired =
    expiresAt == null || expiresAt.isAfter(clock.instant());
~~~

Đây là snippet Java giả định có `Instant expiresAt` và `Clock clock`. Nó đặt quy ước `expiresAt == null` là không hết hạn và `expiresAt <= now` là hết hạn; ứng dụng thực tế cần thống nhất quy ước và test ranh giới thời gian. Nếu không hợp lệ, provider mặc định thường tạo `AccountExpiredException`.

**Tài khoản hết hạn không đồng nghĩa mật khẩu hết hạn.** Account có thể phải được gia hạn quyền sử dụng dù password vẫn đúng.

### 3.4. credentialsNonExpired: mật khẩu/credentials có còn hiệu lực?

`isCredentialsNonExpired()` bằng `false` nghĩa là thông tin xác thực được xem là **đã hết hạn** theo chính sách, thường vì mật khẩu cần đổi hoặc credential đã bị thu hồi.

Ví dụ:

~~~java
boolean credentialsNonExpired =
    passwordExpiresAt == null ||
    passwordExpiresAt.isAfter(clock.instant());
~~~

Đây là minh họa điều kiện thời gian, không phải tính năng tự động của `UserDetailsService`. Khi flag không đạt, `DaoAuthenticationProvider` mặc định có thể ném `CredentialsExpiredException`. Điểm quan trọng: **mật khẩu đúng** chưa đủ, vì credentials có thể đúng về mặt hash nhưng đã quá hạn.

Nếu hệ thống sử dụng API key, JWT, OAuth2 access token hoặc passkey thay vì username/password, đừng giả định flag này tự được áp dụng cho mọi lần kiểm tra token. Nó chỉ có tác dụng khi **authentication provider đang dùng thực sự kiểm tra `UserDetails` và các flag đó**.

## 4. Bốn cờ được kiểm tra ở đâu trong luồng xác thực?

Trong cấu hình Servlet username/password thông dụng:

~~~text
Client gửi username + password
          |
          v
Authentication filter (HTTP Basic hoặc form login)
          |
          v
AuthenticationManager (thường ProviderManager)
          |
          v
DaoAuthenticationProvider
          |
          +--> UserDetailsService.loadUserByUsername(username)
          |       -> UserDetails gồm password hash, authorities, 4 flags
          |
          +--> Kiểm tra trạng thái tài khoản trước xác thực mật khẩu
          |       accountNonLocked / enabled / accountNonExpired
          |
          +--> Xác minh mật khẩu qua PasswordEncoder
          |
          +--> Kiểm tra credentialsNonExpired
          |
          v
Authentication thành công
          |
          v
Spring Security authorization
          -> authenticated? role/authority có đủ? resource có được phép?
          |
          v
Controller và service nếu request được phép
~~~

**Thứ tự trên là mô hình tiêu biểu của `AbstractUserDetailsAuthenticationProvider`/`DaoAuthenticationProvider` trong Spring Security 6**, không phải một cam kết mọi `AuthenticationProvider` tùy chỉnh đều xử lý theo đúng thứ tự này.

Đối với provider mặc định dựa trên `UserDetails`, các bước kiểm tra trạng thái được triển khai bằng `UserDetailsChecker`. Kiểm tra trước mật khẩu thường gồm `isAccountNonLocked`, `isEnabled`, `isAccountNonExpired`; kiểm tra sau mật khẩu gồm `isCredentialsNonExpired`. Nếu nhiều flag cùng không hợp lệ, ngoại lệ cụ thể phát sinh phụ thuộc thứ tự kiểm tra; đừng suy từ một ngoại lệ rằng các trạng thái khác chắc chắn đều tốt.

### Các ngoại lệ thường gặp

| Điều kiện không đạt | Ngoại lệ thường gặp | Ý nghĩa |
| --- | --- | --- |
| `isEnabled() == false` | `DisabledException` | Tài khoản bị vô hiệu hóa |
| `isAccountNonLocked() == false` | `LockedException` | Tài khoản bị khóa |
| `isAccountNonExpired() == false` | `AccountExpiredException` | Tài khoản đã hết hạn |
| `isCredentialsNonExpired() == false` | `CredentialsExpiredException` | Credentials đã hết hạn |
| Password sai | `BadCredentialsException` | Không khớp thông tin xác thực |
| Username không tồn tại | Thường được che thành `BadCredentialsException` theo cấu hình mặc định của provider | Tránh tiết lộ quá dễ sự tồn tại user |

Những ngoại lệ trên thuộc nhóm `AuthenticationException`. Handler/entry point ở lớp HTTP quyết định response gửi ra. Với HTTP Basic trong ví dụ bên dưới, các lỗi đăng nhập thường dẫn tới **401 Unauthorized**. Với form login, thường là điều hướng về trang login với trạng thái lỗi; không suy ra mọi provider luôn trả 401 hoặc phơi chi tiết ngoại lệ cho client.

### Xác thực khác phân quyền

Tài khoản có tất cả các cờ hợp lệ và password đúng có thể được xác thực thành công. Sau đó `AuthorizationFilter` hoặc method security vẫn kiểm tra:

- `.authenticated()`: danh tính đã được xác thực theo policy.
- `.hasRole("ADMIN")`: phải có authority tương ứng (mặc định `ROLE_ADMIN`).
- Quyền theo tài nguyên: chỉ xem/sửa dữ liệu thuộc user hoặc tenant được phép.

Tương tự, `ROLE_ADMIN` trong một `UserDetails` bị disabled không làm provider bỏ qua `isEnabled()`. **Account status** quyết định user có thể xác thực theo cơ chế này; **authorities** quyết định user đã xác thực được làm gì.

## 5. Lớp User có sẵn và các builder flag đảo nghĩa

Spring Security cung cấp `org.springframework.security.core.userdetails.User`, một implementation `UserDetails` có sẵn, có thể tạo bằng builder:

~~~java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .roles("USER")
    .disabled(false)
    .accountLocked(false)
    .accountExpired(false)
    .credentialsExpired(false)
    .build();
~~~

Snippet này cần `UserDetails`, `User` và biến `encodedPassword` trong một class Java; xem ví dụ chạy đầy đủ bên dưới. Lưu ý **tên builder khác chiều với getter**:

| User builder setter | Khi gọi với `true` | Phương thức UserDetails tương ứng |
| --- | --- | --- |
| `disabled(true)` | Vô hiệu hóa account | `isEnabled() == false` |
| `accountLocked(true)` | Khóa account | `isAccountNonLocked() == false` |
| `accountExpired(true)` | Đánh dấu account hết hạn | `isAccountNonExpired() == false` |
| `credentialsExpired(true)` | Đánh dấu credentials hết hạn | `isCredentialsNonExpired() == false` |

Khi không đặt các flag trạng thái trong builder, đối tượng `User` bình thường được tạo ở trạng thái phù hợp để xác thực (các cờ trong `UserDetails` là `true`). Khi bạn gắn `accountLocked(true)`, đừng đọc thành `isAccountNonLocked() == true`.

Nếu tự xây `UserDetails` từ entity trong database, nên dùng các tên thuộc tính rõ ràng hoặc comment giải thích quan hệ phủ định. Không copy tên method rồi trả về thuộc tính `locked` mà quên dấu `!`.

## 6. Ví dụ Spring Boot 3 / Spring Security 6 chạy được

Ví dụ này tạo **năm tài khoản với cùng password hợp lệ** và chỉ khác các trạng thái. Nhờ đó, HTTP response cho thấy vì sao một password đúng chưa đủ nếu tài khoản bị khóa, bị tắt hoặc đã hết hạn.

Ứng dụng sử dụng **Java 17+, Maven, Spring MVC, HTTP Basic** và `InMemoryUserDetailsManager`. Các tài khoản mẫu chỉ dùng trong môi trường học tập local; mật khẩu được BCrypt encode lúc tạo bean. Khi dùng sản phẩm thật, mật khẩu phải được quản lý và lưu trữ an toàn, HTTP Basic cần HTTPS, và user thường đến từ nguồn danh tính/database phù hợp.

### 6.1. Cấu trúc project

~~~text
account-flags-demo/
├── pom.xml
└── src/main/java/com/example/accountflags/
    ├── AccountFlagsApplication.java
    ├── SecurityConfig.java
    └── AccountController.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>account-flags-demo</artifactId>
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
~~~

**`src/main/java/com/example/accountflags/AccountFlagsApplication.java`**

~~~java
package com.example.accountflags;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountFlagsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountFlagsApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/accountflags/SecurityConfig.java`**

~~~java
package com.example.accountflags;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encodedPassword = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("active")
                .password(encodedPassword)
                .roles("USER")
                .build(),

            User.withUsername("disabled")
                .password(encodedPassword)
                .roles("USER")
                .disabled(true)
                .build(),

            User.withUsername("locked")
                .password(encodedPassword)
                .roles("USER")
                .accountLocked(true)
                .build(),

            User.withUsername("accountExpired")
                .password(encodedPassword)
                .roles("USER")
                .accountExpired(true)
                .build(),

            User.withUsername("credentialsExpired")
                .password(encodedPassword)
                .roles("USER")
                .credentialsExpired(true)
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`src/main/java/com/example/accountflags/AccountController.java`**

~~~java
package com.example.accountflags;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
~~~

### 6.2. Cơ chế xảy ra trong ví dụ

1. Endpoint `/me` yêu cầu authentication vì `anyRequest().authenticated()`.
2. HTTP Basic đọc credentials từ header và chuyển cho authentication manager.
3. Provider tìm `UserDetails` thông qua `InMemoryUserDetailsManager`.
4. Provider kiểm tra account-state flags, BCrypt password và tình trạng credentials theo quy trình của provider.
5. Chỉ user `active` có đủ cả bốn điều kiện tốt và password đúng.
6. `disabled`, `locked`, `accountExpired` và `credentialsExpired` đều bị từ chối authentication dù đã cung cấp đúng password.
7. `/public` được `permitAll()` và không cần credentials; request vẫn có thể đi qua Spring Security filter chain.

Ở lớp HTTP, code không cố tình công khai tên `DisabledException`/`LockedException` cho client. Những lý do cụ thể có thể được ghi nhận trong hệ thống audit nội bộ với quyền truy cập phù hợp, còn phản hồi cho client nên nhất quán và tránh tiết lộ thông tin account.

### 6.3. Chạy thử

Cần JDK 17+ và Maven, lần đầu Maven cần tải dependency. Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Mặc định server chạy `http://localhost:8080`. Với Windows PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần. Các chú thích `# ...` dưới đây là **kết quả dự kiến từ cấu hình minh họa**, không phải kết quả đã được đo trong môi trường hiện tại.

~~~bash
curl -s http://localhost:8080/public
# public OK

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -u active:demo-pass http://localhost:8080/me
# hello active

curl -s -o /dev/null -w '%{http_code}\n' -u active:wrong-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u disabled:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u locked:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u accountExpired:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u credentialsExpired:demo-pass http://localhost:8080/me
# 401
~~~

Kết quả dự kiến:

| Username | Password | Trạng thái | `GET /me` |
| --- | --- | --- | --- |
| `active` | đúng | Bốn cờ hợp lệ | 200, body `hello active` |
| `active` | sai | Không khớp password hash | 401 |
| `disabled` | đúng | `enabled = false` | 401 |
| `locked` | đúng | `accountNonLocked = false` | 401 |
| `accountExpired` | đúng | `accountNonExpired = false` | 401 |
| `credentialsExpired` | đúng | `credentialsNonExpired = false` | 401 |

Giá trị 401 do ví dụ dùng HTTP Basic. Nếu đổi sang form login, endpoint xử lý login có thể redirect khi xác thực thất bại; không nên xem 401 là giá trị trả về bắt buộc của mỗi flag ở mọi ứng dụng.

### 6.4. Kiểm tra trạng thái trực tiếp qua UserDetails

Nếu muốn viết một bài test có kiểm soát, bạn có thể load từng `UserDetails` rồi kiểm tra:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("locked");
System.out.println(user.isEnabled());
System.out.println(user.isAccountNonLocked());
System.out.println(user.isAccountNonExpired());
System.out.println(user.isCredentialsNonExpired());
~~~

Đây là snippet cho lớp/test đã có `UserDetailsService userDetailsService` trong scope (cần import `UserDetails`). Với `locked` trong ví dụ, stdout lần lượt dự kiến là:

~~~text
true
false
true
true
~~~

Đọc cờ trực tiếp rất hữu ích khi kiểm tra code ánh xạ từ database sang `UserDetails`; tuy nhiên việc một flag đúng trong object **không tự chứng minh** mọi loại authentication provider hoặc mọi JWT request đang áp dụng quy tắc đó.

## 7. Cách triển khai với dữ liệu thật

### 7.1. Lưu trạng thái rõ ràng ở database

Một bảng user nghiệp vụ có thể lưu các trường sau (tên chỉ minh họa):

| Cột dữ liệu | Cách dùng |
| --- | --- |
| `enabled` | User được phép sử dụng tài khoản |
| `locked_until` | Mốc kết thúc thời gian khóa; null nghĩa là không có khóa |
| `account_expires_at` | Mốc hết hạn tài khoản, có thể null nếu vô thời hạn |
| `credentials_expires_at` | Mốc hết hạn password/credentials, có thể null |
| `password_hash` | Password đã mã hóa bằng một password encoder thích hợp |
| `roles` hoặc `authorities` | Quyền truy cập, tách biệt với bốn trạng thái |

Lập quy ước ranh giới thời gian: nếu `expiresAt == now` thì trạng thái đã hết hạn. Dùng `Instant`/UTC hoặc `Clock` được inject để viết test quyết định mà không phụ thuộc thời gian máy.

### 7.2. Ánh xạ flags trong UserDetailsService

Khi dùng entity riêng, bạn có thể ánh xạ vào `User` mặc định. Ví dụ dưới đây là **mảnh mã trình bày quy tắc**, không phải project độc lập vì `account` và `clock` phải lấy từ repository/dependency injection:

~~~java
Instant now = clock.instant();

boolean locked = account.lockedUntil() != null
    && account.lockedUntil().isAfter(now);

boolean accountExpired = account.accountExpiresAt() != null
    && !account.accountExpiresAt().isAfter(now);

boolean credentialsExpired = account.credentialsExpiresAt() != null
    && !account.credentialsExpiresAt().isAfter(now);

UserDetails details = User.withUsername(account.username())
    .password(account.passwordHash())
    .authorities(account.authorities())
    .disabled(!account.enabled())
    .accountLocked(locked)
    .accountExpired(accountExpired)
    .credentialsExpired(credentialsExpired)
    .build();
~~~

Nếu repository trả về quyền từ một entity không tin cậy hoặc client cung cấp, phải chuẩn hóa và xác minh quyền phía server; đừng cho client tự đặt `ROLE_ADMIN`. Các trường `lockedUntil` và `expiresAt` cũng cần một chính sách cập nhật an toàn, có audit phù hợp.

Khi account không tồn tại, `UserDetailsService` có thể ném `UsernameNotFoundException`; provider thường che lỗi này thành thông báo credentials chung khi cấu hình tương ứng. Không dùng lỗi public khác nhau cho từng username để giúp kẻ tấn công xác định tài khoản hợp lệ.

### 7.3. Không tự động hóa chính sách chỉ bằng getter

Bốn getter có thể **phản ánh** chính sách đã lưu, nhưng bản thân chúng không tự thực thi:

- **Số lần login sai:** cần hệ thống ghi nhận thất bại, giới hạn tốc độ, xác định khi nào khóa/mở.
- **Tự hết hạn tài khoản:** cần mốc thời gian/quy tắc được tính khi load hoặc nguồn trạng thái được cập nhật.
- **Hết hạn mật khẩu:** cần mốc thay mật khẩu, quy trình đổi/reset password bảo mật.
- **Kích hoạt account:** cần quy trình xác minh email/nhân sự, bảo đảm chỉ nguồn đáng tin cậy bật lại user.
- **Duy trì phiên:** nếu user đã đăng nhập và giữ session, việc đổi trạng thái trong database chưa chắc làm mọi session hiện tại bị hủy ngay.

Đặc biệt, với authentication theo session, ứng dụng thường **không gọi lại `UserDetailsService` và bốn getter ở mọi request** sau khi authentication đã có trong `SecurityContext`. Khi disable một account cần hiệu lực ngay, cân nhắc session revocation/force logout, kiểm tra phiên phía server hoặc một chính sách revalidation theo mức độ rủi ro của ứng dụng.

## 8. Các giới hạn và hiểu nhầm quan trọng

### 8.1. Không phải mọi AuthenticationProvider đều đọc UserDetails

`DaoAuthenticationProvider` dựa trên `UserDetailsService` nên sử dụng các trạng thái này. Nhưng một ứng dụng còn có thể dùng:

- JWT/Bearer token với `JwtDecoder` và chính sách kiểm tra token.
- OAuth2/OIDC login thông qua provider bên ngoài.
- AuthenticationProvider tự viết.
- API key, mTLS, passkey hoặc cơ chế khác.

Với các cơ chế này, **đừng giả định các phương thức của `UserDetails` tự được gọi** cho mỗi request. Nếu bạn muốn account đã bị disabled không còn dùng được JWT đã phát, cần có chính sách token/session revocation, thời hạn token, tra cứu trạng thái hoặc cơ chế kiểm soát phù hợp. Chỉ sửa cột `enabled` trong database không đảm bảo mọi bearer token lập tức mất hiệu lực.

### 8.2. User status và trạng thái HTTP là hai tầng khác nhau

Trong phương thức xác thực, bốn flag không hợp lệ thường gây `AuthenticationException`. Còn status HTTP phụ thuộc `AuthenticationEntryPoint`, failure handler và cơ chế login. Ví dụ:

- HTTP Basic thường trả **401** và có header `WWW-Authenticate`.
- Form login có thể **302** chuyển hướng đến trang login lỗi.
- REST API tùy chỉnh có thể trả JSON lỗi chung theo thiết kế.

**403 Forbidden** thường xuất hiện khi một principal đã xác thực nhưng không được phép truy cập tài nguyên hoặc do CSRF, không phải mã HTTP mặc định cố định cho `locked`/`disabled`. Không suy ngược `401 == disabled` hoặc `403 == hết hạn`.

### 8.3. Lỗi trạng thái cần được xử lý bảo mật

Ở bên trong, audit có thể lưu sự kiện khóa, hết hạn, vô hiệu hóa kèm mã lý do để hỗ trợ. Ở bên ngoài, nên hạn chế khác biệt phản hồi khiến người lạ dễ dò username, trạng thái khóa hoặc chính sách bảo mật. Không ghi plaintext password, HTTP Basic header hoặc access token vào log. Các luồng khôi phục tài khoản/reset password phải yêu cầu kiểm chứng danh tính và giới hạn tần suất.

Nếu business yêu cầu báo “mật khẩu đã hết hạn” để user đổi mật khẩu, hãy thiết kế **luồng đổi mật khẩu đã xác minh danh tính**. Đừng chỉ cho client biết chi tiết và mở một endpoint reset không kiểm soát.

### 8.4. Đừng thay trạng thái bằng quyền giả

Không nên tạo `ROLE_DISABLED` hoặc `ROLE_LOCKED` rồi kỳ vọng `DaoAuthenticationProvider` hiểu và tự chặn. Roles/authorities thuộc **authorization**; bốn flag thuộc **account state checks** cho provider đang dùng. Một hệ thống có thể cần thêm permission riêng cho nghiệp vụ, nhưng không nên hoán đổi ý nghĩa của các lớp này.

## 9. Các lỗi lập trình phổ biến

**Lỗi 1 — Đảo chiều boolean:**

~~~java
// Sai nếu field locked=true nghĩa là đang bị khóa.
@Override
public boolean isAccountNonLocked() {
    return locked;
}

// Đúng theo mô hình field trên.
@Override
public boolean isAccountNonLocked() {
    return !locked;
}
~~~

Đây là snippet của một class triển khai `UserDetails`, không phải chương trình standalone. Tương tự: `isAccountNonExpired()` phải trả về trạng thái **chưa** hết hạn, `isCredentialsNonExpired()` trả về credentials **chưa** hết hạn.

**Lỗi 2 — Để tất cả bốn getter luôn `true` khi entity có trạng thái:** cách làm này khiến provider không biết user đã khóa/expired/disabled. Nếu chỉ dùng `User` builder, cần truyền flag từ entity đúng chiều.

**Lỗi 3 — Nghĩ provider tự khóa user khi login sai nhiều lần:** getter chỉ đọc trạng thái; cần thiết kế thành phần theo dõi login failure, giới hạn tốc độ và cập nhật lock.

**Lỗi 4 — Chỉ đổi `enabled=false` và tưởng session/JWT hiện có lập tức bị thu hồi:** account status không tự động có hiệu lực trên mọi request của mọi mechanism; thêm chính sách revoke/revalidate phù hợp.

**Lỗi 5 — Nghĩ hết hạn mật khẩu đồng nghĩa sai mật khẩu:** password có thể đúng nhưng `isCredentialsNonExpired()` vẫn false; thường là hai kiểm tra khác nhau.

**Lỗi 6 — Dùng `isAuthenticated()` trên `Authentication` thay cho account status:** đó là thuộc tính của authentication object khi đã có kết quả xác thực, không phải bốn getter của `UserDetails` và không tự thay thế logic account state.

**Lỗi 7 — Gắn role ADMIN để “mở khóa”:** quyền truy cập không thay đổi kết quả `isAccountNonLocked()` của provider username/password.

**Lỗi 8 — Bỏ qua null/timezone ở mốc hết hạn:** cần quy ước null, UTC và kiểm tra ranh giới thời gian. Nếu áp dụng `isAfter(now)`, đúng tại mốc expiration là đã hết hạn.

**Lỗi 9 — Tiết lộ status account cho người chưa xác thực:** tránh phản hồi “username này tồn tại nhưng đang bị khóa” ở endpoint công khai nếu điều đó giúp enumeration. Sử dụng thông báo chung hoặc luồng phục hồi đã xác minh danh tính.

**Lỗi 10 — Chỉ test password đúng/sai:** cần test riêng từng flag false và tổ hợp nhiều flag, test sau khi update trạng thái, sau khi user đã login, và các loại authentication khác nếu có.

## 10. Checklist kiểm thử hữu ích

Khi triển khai các trạng thái trong database và tích hợp Spring Security, hãy kiểm tra:

1. **Bốn cờ true, password đúng** → authentication thành công.
2. **enabled false** → authentication thất bại theo provider đang dùng.
3. **accountNonLocked false** → authentication thất bại do khóa.
4. **accountNonExpired false** → authentication thất bại do hết hạn tài khoản.
5. **credentialsNonExpired false** → authentication thất bại do hết hạn credentials.
6. **Bốn cờ true, password sai** → authentication thất bại.
7. **Một user có nhiều trạng thái lỗi** → không dựa vào ngoại lệ đầu tiên để kết luận chỉ có một vấn đề; xử lý recovery theo dữ liệu thật.
8. **Thay đổi trạng thái khi session đang hoạt động** → xác nhận chính sách session revoke/re-authentication đã thiết kế.
9. **User dùng JWT/API key/OAuth2** → xác nhận liệu cơ chế đó có kiểm tra trạng thái account hay không; không phụ thuộc mù vào `UserDetails`.
10. **Đổi flags thành true lại** → chỉ những quyền và credentials hợp lệ mới được truy cập; không bỏ qua bước kiểm tra password và authorization.

Nếu có integration tests, dùng `MockMvc` hoặc một HTTP client gửi credentials thật trong môi trường test để kiểm tra status/behavior; đồng thời unit-test mã mapping trạng thái. Khi test status account, ưu tiên kết quả **được phép hay không được phép** và lý do nội bộ đã được quản lý đúng; không cố ràng buộc ngoại lệ chi tiết vào thông báo public trừ khi hợp đồng API thực sự yêu cầu.

## 11. Tự kiểm tra hiểu biết

**Câu 1.** `accountLocked = true` trong builder dẫn tới `isAccountNonLocked()` bằng bao nhiêu?

**Đáp:** `false`. Builder dùng chiều “đang bị khóa”, còn getter trả lời “không bị khóa”.

**Câu 2.** User có `ROLE_ADMIN`, password đúng, nhưng `enabled = false`; có được xác thực thành công bằng `DaoAuthenticationProvider` mặc định không?

**Đáp:** Thông thường không. Account status được kiểm tra trong authentication, trước khi policy quyền HTTP sử dụng authorities.

**Câu 3.** `isCredentialsNonExpired() == false` có nghĩa password hash không khớp không?

**Đáp:** Không. Password có thể đúng nhưng credentials đã hết hạn theo chính sách; `CredentialsExpiredException` khác `BadCredentialsException`.

**Câu 4.** Chỉ cần khai báo `isAccountNonLocked()` thì Spring Security tự khóa sau năm lần nhập sai không?

**Đáp:** Không. Ứng dụng phải thiết kế và cập nhật chính sách đếm lỗi/khóa; provider chỉ sử dụng trạng thái hiện có khi cơ chế xác thực phù hợp kiểm tra getter.

**Câu 5.** Vì sao vô hiệu hóa user trong database không đảm bảo JWT đã cấp lập tức không còn dùng được?

**Đáp:** Bearer token thường được xác minh qua token decoder và các rule riêng. Nếu request không load/check `UserDetails`, bốn flag không được áp dụng tự động; cần chính sách token lifetime, revoke hoặc revalidation.

**Câu 6.** Tại sao không nên cho client biết cụ thể tài khoản nào đang bị khóa ở màn hình login công khai?

**Đáp:** Thông báo chi tiết có thể giúp dò username và trạng thái tài khoản; nên tách audit nội bộ khỏi phản hồi public hoặc sử dụng luồng phục hồi đã xác minh danh tính.

**Câu 7.** Tài khoản đã xác thực, bốn cờ đều hợp lệ nhưng không có `ROLE_ADMIN`; có truy cập `hasRole("ADMIN")` được không?

**Đáp:** Không. Account-state flags và HTTP/resource authorization là hai lớp kiểm soát khác nhau.

**Nhớ nhanh:** **Bốn getter của `UserDetails` biểu thị trạng thái “được phép dùng để xác thực” khi trả về `true`: enabled, không khóa, không hết hạn account, không hết hạn credentials.** Chúng giúp provider kiểm tra tư cách đăng nhập; còn quyền thực hiện hành động được quyết định sau bởi authorities và chính sách nghiệp vụ.