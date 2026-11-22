# UsernamePasswordAuthenticationToken trước và sau xác thực

> **Ý chính:** `UsernamePasswordAuthenticationToken` có thể biểu diễn **yêu cầu đăng nhập chưa được xác minh** hoặc **kết quả xác thực thành công**. Trước xác thực, token thường mang username/password do người dùng cung cấp, `isAuthenticated() == false` và chưa có quyền được tin cậy. Sau khi `AuthenticationManager` và `AuthenticationProvider` kiểm tra credential, kết quả thường mang principal `UserDetails`, tập `GrantedAuthority` được lấy từ nguồn đáng tin và `isAuthenticated() == true`. `ProviderManager` mặc định cố gắng xóa thông tin credential nhạy cảm khỏi kết quả. Quan trọng nhất: **việc tự tạo một token có cờ true không đồng nghĩa mật khẩu đã được kiểm chứng**.

Bài nằm trong nhóm **Danh tính** của module **Spring Security – fundamentals**, trình bày Spring Security 6.5 trên ứng dụng **Servlet/Spring MVC**, Java 17 và Spring Boot 3.5.16. Ở WebFlux và ở OAuth2/JWT, ý tưởng “yêu cầu → xác minh → danh tính hiện tại” vẫn có giá trị, nhưng loại `Authentication`, API reactive và cơ chế chuyển context khác. Ví dụ tài khoản/mật khẩu chỉ phục vụ bài thực hành local.

## 1. Mục tiêu sau bài học

Bạn sẽ có thể:

1. Phân biệt token **đang yêu cầu xác thực** với token **đã xác thực**, dựa trên `principal`, `credentials`, `authorities` và `isAuthenticated()`.
2. Biết khi nào dùng `UsernamePasswordAuthenticationToken.unauthenticated(...)` và hiểu vì sao `authenticated(...)` chỉ dành cho mã đã có bằng chứng xác thực đáng tin.
3. Mô tả luồng từ `UsernamePasswordAuthenticationFilter`/`BasicAuthenticationFilter` đến `AuthenticationManager`, `ProviderManager`, `DaoAuthenticationProvider`, `UserDetailsService` và `PasswordEncoder`.
4. Hiểu tại sao `AuthenticationManager.authenticate(...)` **trả về** authentication đã xác minh nhưng **không tự lưu kết quả vào `SecurityContextHolder`** nếu bạn gọi manager trực tiếp ngoài filter.
5. Giải thích chức năng `CredentialsContainer.eraseCredentials()`, vì sao `getCredentials()` có thể thành `null` và vì sao không được log credential.
6. Chạy demo Spring Boot có user in-memory được hash bằng BCrypt và bộ test kiểm tra token, password đúng/sai, HTTP status, role và CSRF.
7. Nhận diện cách dùng token gây leo thang quyền: copy authorities từ request body, dùng constructor ba tham số chưa xác minh hoặc tự đặt authentication trong context rồi bỏ qua provider.

## 2. Bản đồ nhỏ: Authentication là một interface với hai vai trò

Trong Spring Security, `Authentication` không chỉ là “người dùng đã login”. Nó còn là **đối tượng mang yêu cầu xác thực đến một `AuthenticationManager`**.

```text
Người dùng/client gửi username + password
                |
                v
UsernamePasswordAuthenticationToken.unauthenticated(...)
  - principal    = "alice" (String do client cung cấp)
  - credentials  = password được gửi tới
  - authorities  = [] (chưa được cấp quyền tin cậy)
  - authenticated = false
                |
                v
AuthenticationManager.authenticate(request)
                |
                v
ProviderManager chọn AuthenticationProvider phù hợp
                |
                v
DaoAuthenticationProvider
  -> UserDetailsService.loadUserByUsername("alice")
  -> PasswordEncoder.matches(rawPassword, storedHash)
  -> kiểm tra tài khoản theo provider (enabled, locked, ...)
                |
           +----+----+
           |         |
      THẤT BẠI   THÀNH CÔNG
           |         |
      Exception      v
      (không cấp   UsernamePasswordAuthenticationToken kết quả
       quyền)        - principal    = UserDetails của Alice
                     - authorities  = [ROLE_USER, NOTES_WRITE]
                     - authenticated = true
                     - credentials  = thường null sau erase
                           |
                           v
                  Filter gắn kết quả vào SecurityContext
                           |
                           v
                 Authorization + Controller/Service
```

Đây là luồng **username/password với `DaoAuthenticationProvider`**. Không phải mọi hệ thống đều dùng provider này. Ứng dụng dùng JWT có thể nhận `JwtAuthenticationToken`; dùng OIDC có thể nhận `OAuth2AuthenticationToken`. Vì vậy, kiểu token phải được hiểu theo **authentication mechanism thực tế**.

Điểm phân biệt quan trọng:

- **Authentication request:** “Tôi nói mình là Alice, đây là credential tôi đưa ra để kiểm tra”.
- **Authenticated result:** “Hệ thống đã kiểm tra bằng provider đáng tin, đây là danh tính và quyền mà policy cho phép sử dụng”.
- **SecurityContext:** nơi luồng xử lý hiện tại giữ authentication mà filter/controller/service truy cập.
- **Authorization:** hành động tiếp theo quyết định Alice có được xem/sửa đối tượng cụ thể hay không; login thành công chưa đủ để vượt mọi rule.

## 3. UsernamePasswordAuthenticationToken là class gì?

`UsernamePasswordAuthenticationToken` thuộc:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
```

Nó kế thừa `AbstractAuthenticationToken`, triển khai `Authentication` và `CredentialsContainer`. Những thuộc tính quan trọng qua API:

| Thuộc tính/method | Trước khi xác thực | Sau khi provider xác thực thành công |
| --- | --- | --- |
| `getPrincipal()` | Thường là `String` username, chưa được chứng minh | Với `DaoAuthenticationProvider` thường là `UserDetails` đã được tải |
| `getName()` | Có thể đã trả username do client khai | Thường là username/identity từ authenticated principal |
| `getCredentials()` | Password người dùng nhập, có thể là raw password | Có thể là `null` sau khi manager xóa credentials |
| `getAuthorities()` | Thông thường rỗng | Authority/role đã được provider xác minh và trả về |
| `isAuthenticated()` | `false` | `true` |
| `getDetails()` | Metadata tùy filter/request, có thể null | Có thể được chuyển tiếp tùy provider/filter |
| `eraseCredentials()` | Có thể xóa thông tin nhạy cảm trong token | Dùng để giảm thời gian sống của credential trong bộ nhớ |

**Phải hiểu chữ “thường”.** API cho phép principal và credentials có kiểu `Object`; provider tùy chỉnh có thể trả kiểu khác, thuộc tính khác hoặc không xóa credentials. Một kết quả từ `DaoAuthenticationProvider` qua `ProviderManager` với mặc định erase credentials sẽ khác một token do developer tự gán. Đừng dựa vào việc `getCredentials()` luôn null như một điều kiện an ninh; điều kiện an ninh là **đường xác thực đáng tin** tạo ra kết quả.

### 3.1. Hai factory method dễ đọc nhất

Spring Security 6.x cung cấp:

```java
UsernamePasswordAuthenticationToken request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-submitted-by-user");
```

Token trên có `isAuthenticated() == false` và chưa được coi là quyền truy cập hợp lệ. Nó là **dữ liệu đầu vào** để gửi cho `AuthenticationManager`. Không đưa object này thẳng vào `SecurityContextHolder` rồi cấp quyền.

Sau khi provider thực sự kiểm tra mật khẩu, code đáng tin có thể tạo kết quả thông qua một constructor/factory khác:

```java
// CHỈ LÀ MINH HỌA BÊN TRONG MỘT AUTHENTICATION PROVIDER TIN CẬY.
// Không gọi theo input role do client gửi.
UsernamePasswordAuthenticationToken trusted =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedUserDetails,
        null,
        verifiedAuthorities
    );
```

Trong snippet thứ hai, `verifiedUserDetails` và `verifiedAuthorities` là các biến đã có **trong phạm vi provider**, được tạo từ bằng chứng đã xác minh. Factory `authenticated(...)` **không gọi PasswordEncoder hoặc tra cứu database**; nó chỉ tạo một object với cờ authenticated true. Nếu một controller lấy `authorities` từ JSON rồi gọi factory này, backend có thể tự cấp quyền giả cho attacker.

**Hai constructor tương ứng:**

```java
// Đầu vào chưa xác thực: cờ false.
new UsernamePasswordAuthenticationToken(username, password);

// Kết quả tin cậy: cờ true. Chỉ dùng trong code đã xác minh.
new UsernamePasswordAuthenticationToken(
    verifiedPrincipal, null, trustedAuthorities);
```

Factory method thể hiện ý định rõ hơn: `unauthenticated(...)` cho request, `authenticated(...)` cho kết quả do hệ thống tin cậy quyết định. Cả hai cách được Spring Security hỗ trợ; bản thân tên method không thể thay thế quy trình xác thực thật.

### 3.2. Vì sao không gọi setAuthenticated(true)?

`UsernamePasswordAuthenticationToken` có API `setAuthenticated(boolean)` kế thừa từ interface `Authentication`. Implementation này **không cho phép** đơn giản chuyển token chưa xác thực thành trusted bằng `setAuthenticated(true)`; việc đó sẽ ném `IllegalArgumentException`. Nó cho phép đặt `false` để đánh dấu không còn đáng tin.

```java
UsernamePasswordAuthenticationToken pending =
    UsernamePasswordAuthenticationToken.unauthenticated("alice", "pw");

// pending.setAuthenticated(true) => IllegalArgumentException.
pending.setAuthenticated(false); // được hỗ trợ, vẫn không được tin cậy
```

Tuy nhiên, điều này **không ngăn** code ứng dụng tự gọi constructor ba tham số hoặc `authenticated(...)` để tạo object mang cờ true. Security không thể tự kiểm chứng tính hợp lệ của code được chạy với quyền của chính server; developers phải bảo vệ ranh giới tin cậy và chỉ tạo trusted result sau khi provider xác minh.

### 3.3. getName() trước xác thực chưa phải danh tính được tin

Ngay khi chỉ có request token:

```java
UsernamePasswordAuthenticationToken pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "admin", "wrong-password");

// pending.getName() có thể đã là "admin".
// pending.isAuthenticated() là false.
```

Nếu code log `pending.getName()` và bảo “admin đã đăng nhập”, đó là lỗi **nhầm tên do client khai với danh tính đã xác thực**. Để biết user có được phép hành động, policy phải dùng authentication đã được framework/provider xác minh, không dùng token thô từ form.

## 4. AuthenticationManager và DaoAuthenticationProvider biến input thành result

### 4.1. AuthenticationManager làm gì?

`AuthenticationManager` có hợp đồng cốt lõi:

```java
Authentication verified = authenticationManager.authenticate(pending);
```

Khi thành công, nó trả một `Authentication` đáng tin. Nếu credential sai, tài khoản không hợp lệ, nhà cung cấp không hỗ trợ token hoặc có lỗi xác thực, nó ném `AuthenticationException` tương ứng. **Không có quy tắc rằng luôn trả null khi đăng nhập sai.** Trên đường lỗi, không được tự xây “kết quả tạm được” để cho request đi tiếp.

Trong nhiều cấu hình, manager là `ProviderManager`. Nó lần lượt tham vấn các `AuthenticationProvider` được cấu hình, xác định provider có thể xử lý loại token, và dùng kết quả được chấp nhận. Provider không hỗ trợ loại token có thể từ chối bằng cách trả null để provider khác xét tiếp. Cách hoạt động này cho phép một ứng dụng có nhiều cơ chế xác thực, nhưng phải thiết kế thứ tự và phạm vi nhà cung cấp cẩn thận.

### 4.2. DaoAuthenticationProvider làm gì?

Với username/password truyền thống:

1. `DaoAuthenticationProvider` nhận `UsernamePasswordAuthenticationToken` chưa được xác thực.
2. Gọi `UserDetailsService.loadUserByUsername(username)` để tìm tài khoản từ nguồn đáng tin (memory/database/service).
3. `UserDetails` chứa username, password hash, authorities và cờ trạng thái tài khoản.
4. Dùng `PasswordEncoder.matches(rawPassword, encodedPassword)` để so khớp, **không giải mã hash ra plaintext**.
5. Kiểm tra các trạng thái account phù hợp (khóa, vô hiệu hóa, hết hạn...), theo thiết kế provider.
6. Nếu hợp lệ, provider tạo authentication thành công với principal/authorities đáng tin và trả về manager.
7. `ProviderManager` mặc định xóa credentials trên kết quả khi có thể rồi trả result cho caller.

**Không nhầm `UserDetailsService` với bộ kiểm tra mật khẩu.** UserDetailsService chủ yếu tải user; `PasswordEncoder`/provider mới kiểm chứng password. Cũng không lấy authorities từ input token do client gửi: hệ thống phải lấy quyền từ nguồn đáng tin hoặc một cơ chế claim đã xác minh.

### 4.3. Ví dụ bảng before/after của cùng username

| Bước | Principal | Credentials | Authorities | Authenticated |
| --- | --- | --- | --- | --- |
| Client gửi form/Basic | `"alice"` (lời khai) | Password được gửi | Không có quyền tin cậy | Chưa xác thực |
| Filter tạo request token | `"alice"` | Raw password ở trong input token | `[]` | `false` |
| Manager/provider tra user | `UserDetails("alice")` được tải | So khớp password với BCrypt hash | Quyền lấy từ user store | Đang xử lý |
| Manager trả kết quả | `UserDetails("alice")` | Thường bị erase, thành `null` | Ví dụ `ROLE_USER`, `NOTES_WRITE` | `true` |
| Filter đưa vào context | Authentication kết quả | Không cần giữ raw password | Quyền sẵn cho rule HTTP/method | Truy cập theo request hiện tại |
| Request kết thúc | Tùy session/repository hoặc xác thực lại ở request sau | Không nên lưu plaintext | Quyền có chính sách hiệu lực/thu hồi riêng | Context của thread được dọn đúng vòng đời |

Chuyển đổi không phải thao tác “đổi bit false thành true” trên một object theo cách bất kỳ. Trong flow tiêu chuẩn với `DaoAuthenticationProvider`, manager **trả một result object** đã xây theo nguồn tin cậy. Không phụ thuộc vào việc `pending == verified`; hãy dùng giá trị manager trả về.

## 5. Filter tạo token trước, còn ai đưa token sau vào SecurityContext?

### 5.1. Với form login

```text
POST /login (username, password, csrf...)
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
UsernamePasswordAuthenticationToken.unauthenticated(...)
      |
      v
AuthenticationManager / ProviderManager
      |
      v
DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
      |
      +-- Sai credential -> failure handler / clear context / reject
      |
      +-- Hợp lệ -> authenticated Authentication
                          |
                          v
                Filter gắn vào SecurityContext
                và xử lý persistence nếu dùng session
                          |
                          v
                   Success handler / redirect
```

`UsernamePasswordAuthenticationFilter` thường dùng trong form login Servlet. Nó lấy username/password từ HTTP request, tạo token ban đầu, nhờ manager xác thực rồi xử lý success/failure. Tùy cấu hình, session authentication strategy, remember-me, CSRF, login success handler và `SecurityContextRepository` có thể tham gia. **Method `AuthenticationManager.authenticate(...)` tự nó không thực hiện tất cả những bước HTTP này**.

### 5.2. Với HTTP Basic

```text
Authorization: Basic <base64(username:password)>
      |
      v
BasicAuthenticationFilter
      |
      v
UsernamePasswordAuthenticationToken request
      |
      v
AuthenticationManager -> provider -> Authentication result
      |
      v
SecurityContext của request
      |
      v
AuthorizationFilter -> Controller / Service
```

Basic Auth chỉ mã hóa Base64 để biểu diễn credential trong header, **không mã hóa bí mật trên mạng**. Với client ngoài localhost phải dùng HTTPS. Ở ứng dụng API stateless, mỗi request thường mang credential riêng; context được tạo và dọn theo request, không có “token Java” sống vĩnh viễn giữa mọi request.

### 5.3. Nếu tự gọi manager.authenticate ngoài filter

Giả sử một service test gọi:

```java
Authentication verified =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "demo-pass"));
```

Kết quả `verified` là authentication đã kiểm chứng, **nhưng `SecurityContextHolder` không tự được điền** chỉ do bạn gọi manager. Nếu mã do bạn quản lý thật sự cần dùng result làm current authentication, phải thiết lập context ở phạm vi phù hợp, ví dụ một snippet minh họa **bên trong flow đã được thiết kế an toàn**:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
```

Chỉ đặt vào holder phục vụ code đang chạy và chưa tự tạo persistence giữa các request. Trong Spring Security 6, custom login cần sử dụng `SecurityContextRepository.saveContext(context, request, response)` khi yêu cầu lưu authentication vào session; đồng thời phải thiết kế session fixation protection, CSRF, logout, failure handling và vòng đời context. **Không dùng snippet này làm endpoint login tự chế** nếu chưa xử lý đầy đủ các bước ấy. Nếu tự quản context ngoài filter, dọn nó trong `finally`.

### 5.4. SecurityContextHolder không phải nơi “lưu password”

`SecurityContextHolder` thông thường truy cập `SecurityContext` của luồng Servlet hiện tại (mặc định `ThreadLocal`). Nó cho phép rule/controller/service đọc authenticated principal. Nó **không** phải user database, password vault hay HTTP session. Session có thể lưu security context thông qua repository; ở một API stateless, request mới thường xác thực lại credential/token.

Đừng gắn `UsernamePasswordAuthenticationToken` với raw password vào session chỉ để “đỡ đăng nhập lại”. Hãy dùng cơ chế login/session đã được Spring Security hỗ trợ hoặc identity protocol chuẩn với chính sách tồn tại credential phù hợp.

## 6. Credential được xóa thế nào?

`UsernamePasswordAuthenticationToken` triển khai `CredentialsContainer`. Khi `eraseCredentials()` chạy:

- Credential trực tiếp trên token có thể được xóa (đặt null).
- `AbstractAuthenticationToken` cũng gọi `eraseCredentials()` trên principal và details nếu những object đó triển khai `CredentialsContainer`.
- `ProviderManager` mặc định bật `eraseCredentialsAfterAuthentication` và gọi phương thức xóa trên authentication thành công khi có thể.

Vì vậy, trong ví dụ dùng `DaoAuthenticationProvider` và `ProviderManager` mặc định, sau khi xác thực bạn thường thấy `verified.getCredentials() == null`. Đây là **dấu hiệu xóa dữ liệu nhạy cảm**, không phải “mật khẩu sai” hoặc “token mất danh tính”: principal và authorities vẫn có thể sử dụng để phân quyền.

**Một lưu ý sâu hơn về cache:** Nếu result chứa đúng tham chiếu đến một `UserDetails` được cache và thực hiện erase trên principal, password field bên trong đối tượng cache cũng có thể bị xóa. Lần đăng nhập sau không so khớp được password nếu cache giữ nguyên object đã bị sửa. Cần thiết kế cache bằng bản sao thích hợp hoặc cơ chế lưu password hash đúng, thay vì tắt erase credentials một cách vội vàng.

**Không bao giờ:**

- Trả `getCredentials()` hoặc nguyên `Authentication` thành JSON cho client.
- Ghi plaintext password, Basic header, token, refresh token, cookie session vào log hoặc metric label.
- Thêm raw password vào `getDetails()`, custom principal hoặc exception message.
- Coi “credentials đã erase” là bằng chứng chắc chắn rằng authentication provider được dùng đúng; mã tự tạo token có thể đặt null credentials mà chưa hề kiểm tra password.

Cách quan sát đúng là assert cờ, loại principal, authorities và `getCredentials()` trong **test**, không log bí mật ở server.

## 7. Demo đầy đủ: Java 17, Spring Boot 3.5.16, xác thực thật bằng provider

Demo cung cấp **một Spring Boot Servlet app** có cấu hình tường minh:

- `AuthenticationManager` là `ProviderManager` chứa `DaoAuthenticationProvider`.
- `UserDetailsService` in-memory với password mã hóa bằng BCrypt.
- `UsernamePasswordAuthenticationToken.unauthenticated(...)` được dùng trong test cho giai đoạn trước xác thực.
- `AuthenticationManager.authenticate(...)` trả token kết quả có principal/authorities đáng tin.
- HTTP Basic filter dùng cùng manager để bảo vệ `/me`, `/admin` và `POST /notes`.
- `SessionCreationPolicy.STATELESS` minh họa không duy trì login giữa request; CSRF vẫn bật để test riêng trường hợp POST.

**Phiên bản:** Java 17+, Spring Boot `3.5.16`, Spring Security 6.5.x từ Boot BOM. Spring Boot 3.5.16 đã được phát hành ngày 25/06/2026 và là bản OSS cuối dòng 3.5; ứng dụng mới triển khai production năm 2026 cần chọn dòng Boot 4.x còn được hỗ trợ, áp bản vá và dùng tài liệu API tương ứng. Dữ liệu người dùng/mật khẩu trong bài chỉ phục vụ local.

### 7.1. Cấu trúc

```text
username-password-token-demo/
├── pom.xml
└── src/
    ├── main/java/demo/token/PasswordTokenApplication.java
    └── test/java/demo/token/PasswordTokenApplicationTests.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>username-password-token-demo</artifactId>
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
```

### 7.3. Mã Java ứng dụng

Tạo file `src/main/java/demo/token/PasswordTokenApplication.java`:

```java
package demo.token;

import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasswordTokenApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordTokenApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class PasswordTokenSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // ProviderManager xóa credentials sau thành công theo mặc định.
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            AuthenticationManager authenticationManager)
            throws Exception {

        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            // CSRF giữ bật, tách biệt với authentication.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    MeView me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        // Không đưa raw Authentication, principal hoặc credential ra JSON.
        return new MeView(auth.getName(), authorities);
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }

    @PostMapping("/notes")
    String createNote(Authentication auth) {
        // Demo: không ghi DB; chỉ minh họa quyền thao tác.
        return "created:" + auth.getName();
    }
}

record MeView(String name, List<String> authorities) {}
```

**Đọc code theo đường đi:**

1. `UserDetailsService` cung cấp hai tài khoản thử nghiệm từ nguồn server. `encoder.encode("demo-pass")` tạo hash BCrypt; provider kiểm tra bằng `matches`, không so sánh plaintext trực tiếp với hash.
2. `DaoAuthenticationProvider` chuyên xử lý username/password. `ProviderManager` là manager nhận request token và trả kết quả thành công hoặc ném authentication exception.
3. `HttpSecurity.authenticationManager(authenticationManager)` gắn rõ manager này vào chain, để HTTP Basic filter và các test trực tiếp cùng sử dụng một đường xác thực. Điều này giúp tránh hiểu lầm rằng mình chỉ “mô phỏng” token trong test mà HTTP filter không liên hệ.
4. `SecurityFilterChain` là ranh giới request; `GET /me` yêu cầu authenticated, `GET /admin` yêu cầu `ROLE_ADMIN`, `POST /notes` yêu cầu `NOTES_WRITE` và CSRF token hợp lệ.
5. `SessionCreationPolicy.STATELESS` khiến ứng dụng không dùng HTTP session để lưu security context giữa các request theo chính sách stateless. Mỗi request Basic phải mang credential để được xác minh.
6. Endpoint `/me` chỉ serialize name và authority. Nó không cho biết raw password, hash hay credentials đã bị erase.
7. `DispatcherType.ERROR` cho phép error dispatch của servlet container tạo response khi cần; request ban đầu vẫn chịu rule của chain.

**Ghi chú bảo mật:** Không dùng user in-memory/password hard-coded như vậy ở production. Basic Auth không mã hóa password nếu không có HTTPS. Ở API thực, hãy chọn identity provider/credential policy phù hợp, bảo vệ credential trong kho bí mật, giới hạn đăng nhập, rate limit và audit khi cần.

### 7.4. Test trước và sau xác thực, cùng HTTP request thật qua filter

Tạo file `src/test/java/demo/token/PasswordTokenApplicationTests.java`:

```java
package demo.token;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordTokenApplicationTests {

    @Autowired
    AuthenticationManager authenticationManager;

    @Autowired
    MockMvc mvc;

    @BeforeEach
    void clearBeforeTest() {
        SecurityContextHolder.clearContext();
    }

    @AfterEach
    void clearAfterTest() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void requestTokenIsNotYetAuthenticated() {
        UsernamePasswordAuthenticationToken pending =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");

        assertFalse(pending.isAuthenticated());
        assertEquals("alice", pending.getPrincipal());
        assertEquals("alice", pending.getName());
        assertEquals("demo-pass", pending.getCredentials());
        assertTrue(pending.getAuthorities().isEmpty());

        // Không được biến token đầu vào thành trusted bằng setter.
        assertThrows(IllegalArgumentException.class,
            () -> pending.setAuthenticated(true));

        // Chưa có ai đặt authentication vào current context.
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void providerReturnsVerifiedTokenWithTrustedAuthorities() {
        UsernamePasswordAuthenticationToken pending =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-pass");

        Authentication verified =
            authenticationManager.authenticate(pending);

        assertTrue(verified.isAuthenticated());
        assertInstanceOf(
            UsernamePasswordAuthenticationToken.class, verified);

        // DaoAuthenticationProvider lấy UserDetails từ user store.
        UserDetails principal =
            assertInstanceOf(UserDetails.class, verified.getPrincipal());

        assertEquals("alice", principal.getUsername());
        assertEquals("alice", verified.getName());

        List<String> authorities = verified.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("NOTES_WRITE", "ROLE_USER"), authorities);

        // ProviderManager mặc định xóa credentials trên result.
        assertNull(verified.getCredentials());

        // Manager.authenticate trả result; không tự install vào holder.
        assertNull(SecurityContextHolder.getContext().getAuthentication());

        // Nếu chủ động gắn vào current context, identity mới xuất hiện.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        assertEquals("alice",
            SecurityContextHolder.getContext()
                .getAuthentication().getName());
    }

    @Test
    void wrongPasswordNeverCreatesAnAuthenticatedResult() {
        UsernamePasswordAuthenticationToken wrong =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "not-the-password");

        assertThrows(BadCredentialsException.class,
            () -> authenticationManager.authenticate(wrong));

        assertFalse(wrong.isAuthenticated());
        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }

    @Test
    void basicFilterUsesVerifiedPrincipalOnEveryRequest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("NOTES_WRITE"))
            .andExpect(jsonPath("$.authorities[1]")
                .value("ROLE_USER"));

        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        // Admin có role, Alice không có role.
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Authentication thành công không thay thế CSRF protection.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:alice"));

        // Admin thiếu NOTES_WRITE dù CSRF token hợp lệ.
        mvc.perform(post("/notes")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Stateless: request tiếp theo không có credential không dùng lại Alice.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Ý nghĩa của từng nhóm test:**

- `requestTokenIsNotYetAuthenticated` khẳng định token input chỉ mang lời khai; `getName()` có thể là “alice” ngay cả khi chưa kiểm chứng, còn `isAuthenticated` false.
- `providerReturnsVerifiedTokenWithTrustedAuthorities` dùng **manager/provider thật**, kiểm tra principal UserDetails, authority từ user store, xóa credential và tính chất “manager không tự set context”.
- `wrongPasswordNeverCreatesAnAuthenticatedResult` xác nhận credential sai gây `BadCredentialsException`; không được trả token authenticated để “tiếp tục”.
- `basicFilterUsesVerifiedPrincipalOnEveryRequest` đi qua Spring Security HTTP Basic filter bằng MockMvc, kiểm tra 200/401/403, role và CSRF, đồng thời chứng minh request sau không được kế thừa identity từ request trước.
- `httpBasic("alice", "demo-pass")` gửi credential như một client thật trong test; ngược lại `@WithMockUser`/`user()` tạo principal giả lập để test authorization mà **không kiểm tra password**.
- `@BeforeEach` và `@AfterEach` dọn `SecurityContextHolder` vì test cố ý thiết lập context thủ công; production nên để Spring Security filter quản lý vòng đời theo request.

### 7.5. Chạy test và chạy server

Trong thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Kỳ vọng của test:** `mvn test` hoàn thành khi các assertion khớp Spring Security 6.5/Boot 3.5 và dependency đã tải thành công. Demo mô tả kết quả kỳ vọng, không tuyên bố đây là log đã chạy trên máy của bạn. Không lấy text stdout hay thứ tự dòng log làm một phần bắt buộc của test.

Ở terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u admin http://localhost:8080/admin
curl -i -u alice http://localhost:8080/admin
```

Khi curl hỏi password cho tài khoản local, nhập `demo-pass`. Kết quả dự kiến:

| Lệnh | HTTP status | Mô tả |
| --- | --- | --- |
| `GET /public` không credential | 200 | Public |
| `GET /me` không credential | 401 | Cần Basic authentication |
| `GET /me` với Alice đúng | 200 | JSON name `alice` và authorities |
| `GET /admin` với admin đúng | 200 | Body `admin-ok` |
| `GET /admin` với Alice đúng | 403 | Đã xác thực nhưng thiếu `ROLE_ADMIN` |

**Không thử Basic Auth qua HTTP trên mạng thật**: những URL `localhost` trong lab chỉ nhằm minh họa. Ở staging/production cần HTTPS và không hard-code password. POST `/notes` sẽ cần CSRF token hợp lệ trong cấu hình hiện tại; để chứng minh positive POST, dùng test `MockMvc.with(csrf())` đã định nghĩa, không tắt CSRF một cách tùy tiện.

## 8. Đọc kết quả thí nghiệm: vì sao hai token có thể khác object và dữ liệu?

Sau khi chạy test, có thể hình dung:

```text
INPUT
  class         = UsernamePasswordAuthenticationToken
  principal     = String("alice")
  credentials   = raw password (KHÔNG LOG GIÁ TRỊ THẬT)
  authorities   = []
  authenticated = false

OUTPUT qua ProviderManager/DaoAuthenticationProvider
  class         = UsernamePasswordAuthenticationToken
  principal     = UserDetails(username="alice", ...)
  credentials   = null [với eraseCredentialsAfterAuthentication mặc định]
  authorities   = [NOTES_WRITE, ROLE_USER]
  authenticated = true
```

Các dòng trên là **mô tả trạng thái để học**, không phải gợi ý in cả object ra log. Những điểm cần hiểu:

1. Class có thể **không đổi** trong đường username/password; thứ thay đổi là nguồn xác thực, loại principal, tập quyền, credential và cờ.
2. `principal` từ String sang UserDetails là kết quả của `DaoAuthenticationProvider`; custom provider có thể trả principal khác.
3. `getName()` có thể trùng ở cả hai trạng thái, vì vậy không thể lấy mỗi username làm bằng chứng đã xác thực.
4. `authorities` là nguồn để rule như `hasAuthority("NOTES_WRITE")` hay `hasRole("ADMIN")` xét quyền. Chúng thường đến từ user store, không phải trường `roles` trong HTTP body.
5. `credentials == null` trên result không cản trở authorization vì quyền dùng principal và authorities, không cần so password trên từng dòng service.
6. Manager không quyết định chủ sở hữu tài nguyên: nếu Alice có `NOTES_WRITE`, vẫn cần bảo vệ việc sửa note của Bob bằng owner/tenant/ACL trong service hoặc repository.

## 9. Trường hợp authentication thất bại

### 9.1. Password sai

`AuthenticationManager.authenticate(pending)` ném exception, ví dụ `BadCredentialsException`. Ở ứng dụng HTTP Basic, Spring Security trả response challenge `401` tùy entry point. Không tạo authentication `true` với authorities rỗng rồi coi đó là “đăng nhập thành công giới hạn quyền”. Một account bị khóa/hết hạn có thể tạo exception khác theo policy provider.

### 9.2. Username không tồn tại

`UserDetailsService` có thể ném `UsernameNotFoundException`. `DaoAuthenticationProvider` mặc định thường che bớt khác biệt để không giúp đối tượng ngoài hệ thống đoán username tồn tại; thông điệp HTTP nên tránh tiết lộ tài khoản nào hợp lệ. Không ghi raw password vào exception hoặc trả stack trace có dữ liệu nhạy cảm.

### 9.3. Không có provider xử lý token

`ProviderManager` cần `AuthenticationProvider` hỗ trợ loại `Authentication`. Nếu đưa `JwtAuthenticationToken` tới manager chỉ có provider username/password, request có thể không được xác thực và gặp lỗi kiểu `ProviderNotFoundException`. Đó không phải “password sai”; đó là cấu hình cơ chế xác thực không khớp. Chọn provider/decoder đúng cho mỗi SecurityFilterChain.

### 9.4. Cờ true nhưng không có bằng chứng kiểm chứng

Đây là rủi ro nghiêm trọng:

```java
// PHẢN VÍ DỤ NGUY HIỂM — KHÔNG SỬ DỤNG.
Authentication fake =
    UsernamePasswordAuthenticationToken.authenticated(
        requestBody.getUsername(),
        null,
        List.of(new SimpleGrantedAuthority(
            requestBody.getRequestedRole())));
SecurityContextHolder.getContext().setAuthentication(fake);
```

Đoạn này là snippet cảnh báo, các biến `requestBody`, import và class bao quanh được lược bỏ có chủ đích. Nó **không xác thực password**; role được tin từ client. Nếu đặt token vào context trước authorization, ứng dụng có thể cấp quyền ngoài ý định. Luôn nhờ authentication mechanism tin cậy kiểm tra credential hoặc chữ ký/claim, rồi mới chấp nhận authorities.

## 10. Authentication với Authorization: token đã đăng nhập chưa đủ để sửa dữ liệu

Giả sử Alice đăng nhập đúng và result có:

```text
principal.name = alice
authorities    = [ROLE_USER, NOTES_WRITE]
authenticated  = true
```

Alice gọi `PATCH /api/notes/42`, trong database note 42 có `owner=bob`. `NOTES_WRITE` cho phép **chức năng ghi note**, nhưng chưa chứng minh Alice có quyền sửa **note 42**. Domain service phải kiểm tra owner/tenant/tình trạng note trước thao tác; có thể cần transaction và update có điều kiện để tránh race condition.

```java
// Snippet ở service, chưa phải chương trình hoàn chỉnh.
public Note updateNote(long id, EditNoteRequest request) {
    String actorId = currentUserProvider.currentUserId(); // từ identity tin cậy
    Note note = repository.findByIdAndOwnerId(id, actorId)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));

    note.applyAllowedFields(request); // không cho tự sửa owner/role
    return repository.save(note);
}
```

Điểm áp dụng:

- **Authentication** xác định ai đang gọi, dựa trên kết quả provider/decoder đã kiểm chứng.
- **HTTP authorization** xác định role/authority cần cho method/path.
- **Object authorization** quyết định actor được thao tác trên resource này hay không.
- **State validation** kiểm tra có thể thực hiện hành động tại thời điểm hiện tại không.

Không dùng `getName()` chưa xác thực để lập ownerId; không dùng authority từ body; không cập nhật dữ liệu trước rồi mới xét quyền.

## 11. Session, stateless và việc tái sử dụng Authentication

### 11.1. Form login dùng session

Sau khi xác thực username/password, filter có thể lưu `SecurityContext` qua `SecurityContextRepository`/HTTP session theo cấu hình. Request sau dùng session cookie để khôi phục authenticated identity, không cần gửi lại password trong từng URL. Token `UsernamePasswordAuthenticationToken` lưu trong context có thể đã bị xóa credentials để giảm dữ liệu nhạy cảm trong session.

Đừng nhầm việc session khôi phục `Authentication` với việc lưu **một object Java trong ThreadLocal mãi mãi**. Request khác có thread khác; Spring Security nạp/dọn holder theo vòng đời. Việc thu hồi session, logout, change password và đổi role cần policy hiệu lực/refresh phù hợp.

### 11.2. HTTP Basic stateless

Trong demo, `SessionCreationPolicy.STATELESS` có chủ đích. Mỗi request Basic mới cần credential; filter tạo token request mới, provider xác minh, tạo result cho request đó. Nếu request tiếp theo không gửi header Basic, nó không được dùng lại Alice chỉ vì request trước đã trả 200. Đây là hành vi cần kiểm thử, vì rò rỉ SecurityContext giữa thread/user có thể gây lỗ hổng nghiêm trọng.

### 11.3. JWT và OAuth2 không nhất thiết tạo UsernamePasswordAuthenticationToken

Bearer JWT đã được xác minh thường tạo `JwtAuthenticationToken`; OIDC login có thể sử dụng `OAuth2AuthenticationToken`, SAML cũng có kiểu riêng. `getPrincipal()` không phải lúc nào là `UserDetails`; nó có thể là `Jwt` hoặc `OAuth2User`. Áp các ví dụ `UsernamePasswordAuthenticationToken` cho tất cả cơ chế xác thực sẽ dẫn tới `ClassCastException` và policy sai.

### 11.4. Chạy background job không tự giữ current Authentication

`SecurityContextHolder` trong Servlet mặc định dùng `ThreadLocal`. Khi chuyển sang `@Async` hoặc thread pool, context không tự an toàn truyền theo mọi trường hợp. Dùng `DelegatingSecurityContextExecutor`/cơ chế propagation phù hợp hoặc truyền actor đã kiểm chứng thành dữ liệu rõ ràng; với job chạy muộn phải xét quyền bị thu hồi. Đừng bật `MODE_GLOBAL` để mọi thread nhìn chung một user.

## 12. Các lỗi thường gặp khi làm việc với UsernamePasswordAuthenticationToken

| Lỗi | Vì sao nguy hiểm/sai | Hướng xử lý |
| --- | --- | --- |
| Xem `getName() == "admin"` là đã xác thực | Trước auth cũng có thể là chuỗi client khai | Kiểm tra qua manager/provider và trust boundary |
| Gọi `authenticated(username, null, clientRoles)` ngay trong controller | Tự cấp quyền theo dữ liệu client, không xác minh | Chỉ provider tin cậy tạo trusted result sau xác thực |
| Gọi `setAuthenticated(true)` trên pending | Implementation từ chối bằng exception; sai luồng | Dùng `AuthenticationManager.authenticate(...)` |
| Tự đưa pending token vào `SecurityContext` | Có identity chưa kiểm chứng ở current context | Chỉ dùng authenticated result tin cậy |
| Xem `getCredentials() == null` là password đúng | Null có thể do bạn tự đặt, không chứng minh provider đã chạy | Xác minh flow qua provider/test |
| Log toàn bộ `Authentication` hoặc raw password | Lộ secret/principal details | Log tối thiểu, mask credential |
| So sánh raw password với BCrypt hash bằng `equals` | Không thể xác thực đúng và làm sai bảo mật | `PasswordEncoder.matches(raw, hash)` |
| Cho phép client gửi `ROLE_ADMIN` trong token input | Leo thang đặc quyền | Authorities chỉ lấy từ dữ liệu/claims đã xác minh |
| Cho rằng `authenticate()` luôn gắn context | Manager chỉ trả kết quả | Filter/custom login flow quản lý holder và repository |
| Cho rằng `isAuthenticated()==true` chứng minh human login | Anonymous token cũng có thể true; trusted token có thể bị code giả tạo | Dùng authorization policies và trust resolver phù hợp |
| Xem role có nghĩa sở hữu mọi record | BOLA/IDOR | Policy theo actor + action + resource/tenant |
| Tắt credential erasure vì cache hỏng | Tăng nguy cơ lộ password | Thiết kế cache copy và vòng đời hash đúng |
| Lấy `(UserDetails) auth.getPrincipal()` cho mọi auth scheme | JWT/OIDC có principal kiểu khác | Xử lý principal theo mechanism đã cấu hình |
| Đặt authentication ở field của singleton service | Lẫn identity giữa các request | Dùng scoped context hoặc explicit actor |
| Gắn context trong thread pool rồi quên dọn | Rò rỉ identity sang tác vụ khác | Context propagation có cleanup rõ ràng |

### 12.1. Cái bẫy của isAuthenticated()

Trong Spring Security Servlet với anonymous authentication được bật, `AnonymousAuthenticationToken` thường trả `isAuthenticated() == true` dù không đại diện user đã login. Vì thế code:

```java
if (auth != null && auth.isAuthenticated()) {
    allowSensitiveOperation();
}
```

là **không đủ** để bảo vệ chức năng nhạy cảm. Ví dụ trên là phản ví dụ (các biến/method được lược bỏ). Spring Security cung cấp rule `authenticated()`, `fullyAuthenticated()` và `AuthenticationTrustResolver` để phân biệt anonymous/remember-me; đồng thời vẫn phải xét authority và resource. Trong demo, `HttpSecurity.authorizeHttpRequests(...authenticated())` là cách để Spring Security thực thi đúng ở HTTP boundary.

### 12.2. Đừng cố “đọc token trước auth” ở controller sau filter

Khi request đã tới controller `GET /me` trong demo, authentication được truyền vào method là **kết quả đã được filter xác thực**, không phải token input thô. Để quan sát **before**, viết test trực tiếp tạo `unauthenticated(...)` và gọi manager; để quan sát **after** trong request, nhận `Authentication` trong controller hoặc đọc `SecurityContextHolder`. Không tự đặt breakpoint rồi kết luận token luôn dùng chung một object suốt pipeline.

## 13. Bài tập tự đánh giá

**Bài 1.** Token được tạo bằng `unauthenticated("alice", "pw")`. `getName()` trả `alice`. Đã biết mật khẩu đúng chưa?

**Đáp án:** Chưa. Username là lời khai đầu vào; `isAuthenticated()` là false. Cần gửi token vào manager/provider và xử lý result.

**Bài 2.** `AuthenticationManager.authenticate(...)` trả result có `isAuthenticated()==true` nhưng `getCredentials()==null`. Có phải login thất bại?

**Đáp án:** Không. `ProviderManager` mặc định xóa credential nhạy cảm sau khi xác thực thành công. Phân quyền dựa vào principal/authorities đã được kiểm chứng.

**Bài 3.** Developer gọi `UsernamePasswordAuthenticationToken.authenticated("admin", null, List.of(ROLE_ADMIN))` trong controller mà không kiểm tra password, rồi set vào SecurityContext. Người đó có thể vượt rule admin không?

**Đáp án:** Có nguy cơ rất cao. Factory chỉ tạo object mang trạng thái trusted, không xác thực credential. Không đưa dữ liệu quyền do client kiểm soát vào token; chỉ dùng kết quả từ cơ chế xác thực tin cậy.

**Bài 4.** Vì sao provider trả principal là `UserDetails` thay vì chuỗi username?

**Đáp án:** Với `DaoAuthenticationProvider`, user được tải từ `UserDetailsService` và kết quả thường giữ UserDetails đã xác minh, gồm username/authority/account state. Provider khác có thể chọn principal khác.

**Bài 5.** Nếu test gọi manager trực tiếp thành công, tại sao `SecurityContextHolder.getContext().getAuthentication()` vẫn null?

**Đáp án:** Manager chỉ trả result. Việc thiết lập context là trách nhiệm của filter hoặc custom login flow. Nếu cần lưu session qua request, còn có `SecurityContextRepository` và bảo vệ session tương ứng.

**Bài 6.** Alice có `NOTES_WRITE`. Có đủ cơ sở để sửa note của Bob?

**Đáp án:** Không. Authority là quyền mức chức năng; service cần kiểm tra owner/tenant/ACL và trạng thái dữ liệu.

**Bài 7.** Test `@WithMockUser("alice")` thành công; có thể kết luận password “demo-pass” đã được BCrypt kiểm tra không?

**Đáp án:** Không. `@WithMockUser` tạo authentication giả lập. Test dùng `AuthenticationManager.authenticate(...)` hoặc `httpBasic("alice", "demo-pass")` mới đi qua đường password provider trong ví dụ.

**Bài 8.** Có nên luôn serialize `Authentication` về client để frontend biết mọi quyền?

**Đáp án:** Không. Nó có thể chứa principal/metadata/claims không nên công khai. Hãy thiết kế DTO tối thiểu từ dữ liệu cho phép lộ; server luôn là nơi quyết định quyền.

## 14. Checklist áp dụng cho code thật

Trước khi dùng `UsernamePasswordAuthenticationToken` trong ứng dụng:

1. **Token đang là input hay result?** Có tạo qua `unauthenticated(...)` rồi dùng `AuthenticationManager.authenticate(...)` không?
2. **Credential được kiểm chứng bởi ai?** Provider/decoder có nguồn dữ liệu, hash, trạng thái tài khoản và trust boundary rõ không?
3. **Quyền lấy từ đâu?** Authorities có được lấy từ user store/claims đã xác minh hay từ JSON/header client?
4. **Sau auth, principal kiểu gì?** `UserDetails`, String, Jwt, OAuth2User? Domain dùng user ID ổn định thế nào?
5. **Credentials có được xóa và che khỏi log?** Không trả password, raw token, Basic header, cookie trong response/trace.
6. **Manager có tự đặt context không?** Nếu tự viết login, đã thiết lập context, persistence, session fixation, CSRF, failure handling và cleanup đúng chưa?
7. **Session hay stateless?** Ai chịu trách nhiệm xác thực ở request sau? Token/session đã hết hạn hoặc quyền bị thu hồi thì sao?
8. **HTTP policy có explicit?** Anonymous, sai password, sai role, sai method và CSRF có bị từ chối?
9. **Resource policy có explicit?** User được thao tác chức năng nhưng không được truy cập dữ liệu user/tenant khác?
10. **Test đi qua provider thật?** Có test before/after, credential wrong, chính xác authorities và credential erasure?
11. **Test đi qua filter thật?** Có integration test MockMvc/HTTP Basic cùng status 401, 403, 200 và cleanup giữa request?
12. **Mã tùy chỉnh có dùng đúng API/version?** Boot, Security, Servlet vs WebFlux, các bean/provider có tương thích không?

## 15. Tóm tắt để ghi nhớ

- `UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)` biểu diễn **yêu cầu xác thực**. `principal` có thể chỉ là chuỗi client khai, `authorities` rỗng và `isAuthenticated` false.
- `AuthenticationManager` và `DaoAuthenticationProvider` **kiểm tra credential thật** bằng nguồn user và `PasswordEncoder`, rồi trả `Authentication` kết quả với authorities đáng tin và cờ true.
- `ProviderManager` mặc định cố gắng **erase credentials** trên result; `getCredentials()==null` không làm mất identity/authorities.
- `UsernamePasswordAuthenticationToken.authenticated(...)` và constructor ba tham số **không tự xác minh password**; chỉ dùng từ code provider tin cậy.
- `AuthenticationManager.authenticate(...)` **không tự set SecurityContextHolder** khi bạn gọi trực tiếp; filter hoặc flow đăng nhập đúng phải quản lý context và persistence.
- Xác thực thành công là điều kiện đầu; **role, permission, owner/tenant và trạng thái nghiệp vụ** vẫn phải được phân quyền riêng.
- Test đầy đủ cần cả **before/after token**, password đúng/sai, status HTTP, CSRF và request độc lập.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — UsernamePasswordAuthenticationToken Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 — Release, 25/06/2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
