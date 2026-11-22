# UserDetailsService chỉ tải người dùng, không tự thực hiện toàn bộ việc đăng nhập

## Mục tiêu của bài học

Trong Spring Security, `UserDetailsService` là hợp đồng **đọc thông tin người dùng theo username**. Nó đóng vai trò nguồn dữ liệu phục vụ xác thực username/password, nhưng bản thân việc trả về một `UserDetails` **chưa chứng minh người gọi đã đăng nhập thành công**.

Sau bài học, bạn cần giải thích được:

1. `UserDetailsService.loadUserByUsername(...)` nhận gì, trả gì, và xử lý thế nào khi không tìm thấy account.
2. `UserDetails` khác gì `Authentication`, và tại sao dữ liệu account chưa phải danh tính đã được kiểm chứng.
3. Những thành phần nào thực sự nhận credentials, so sánh mật khẩu, kiểm tra trạng thái tài khoản, tạo kết quả xác thực và gắn kết quả vào `SecurityContext`.
4. Một service tự triển khai để đọc từ database được sử dụng như thế nào trong Spring Security 6.x / Spring Boot 3.x.
5. Tại sao **gọi trực tiếp `loadUserByUsername` không đăng nhập được**, và vì sao không phải mọi cơ chế xác thực đều sử dụng `UserDetailsService`.
6. Những lỗi thường gặp về password hash, account status, caching, lỗi cơ sở dữ liệu và tích hợp Servlet với reactive.

Bài nằm trong phần **Hợp đồng người dùng** của module Spring Security Authentication. Ví dụ chính dùng Java 17+, Spring Boot 3.x, Spring Security 6.x và Spring MVC/Servlet. Những trường hợp JWT, OIDC, reactive được dùng để làm rõ giới hạn hợp đồng, không thay thế chuyên đề riêng của từng cơ chế.

## 1. Hợp đồng UserDetailsService chính xác là gì?

Giao diện `org.springframework.security.core.userdetails.UserDetailsService` rất nhỏ:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

Đây là **chữ ký giản lược để hiểu API**, không phải file source cần tạo trong project. Interface chỉ có một tác vụ đọc: từ `username` tìm bản ghi người dùng đầy đủ ở dạng `UserDetails`.

- **Đầu vào:** tên đăng nhập mà phía xác thực muốn tra cứu. Giá trị này chưa tự chứng minh tính hợp lệ của account hay mật khẩu.
- **Đầu ra:** đối tượng `UserDetails` chứa username, password đã lưu (thường là hash), các `GrantedAuthority` và cờ trạng thái tài khoản. Kết quả **không được là `null`**.
- **Không tìm thấy:** ném `UsernameNotFoundException`; không trả `null` hay một `UserDetails` giả được đánh dấu enabled để “tránh lỗi”.
- **Không có tham số mật khẩu:** phương thức không nhận raw password do người dùng vừa nhập, nên không thể thực hiện đầy đủ bước so sánh mật khẩu theo hợp đồng này.
- **Read-only contract:** interface không quy định tạo tài khoản, đổi password, đăng xuất, lưu session hoặc cấp token. Các thao tác quản lý tài khoản thuộc tầng nghiệp vụ hoặc `UserDetailsManager`, một interface mở rộng có thêm CRUD.

Các implementation thường gặp: `InMemoryUserDetailsManager`, `JdbcUserDetailsManager`, `JdbcDaoImpl`, một adapter JDBC/JPA tùy chỉnh, hoặc dịch vụ lấy thông tin từ kho tài khoản đáng tin cậy. Chúng khác **nguồn dữ liệu**, không thay thế vai trò của authentication provider.

> **Nguyên tắc:** “Tải được Alice” chỉ có nghĩa hệ thống tìm thấy hồ sơ của Alice. Để “đăng nhập thành Alice”, hệ thống vẫn phải kiểm tra bằng chứng và các điều kiện xác thực rồi tạo `Authentication` đã được tin cậy.

### 1.1. Phân biệt UserDetails, Authentication và SecurityContext

| Đối tượng | Trả lời câu hỏi | Được tạo hoặc sử dụng bởi |
| --- | --- | --- |
| `UserDetails` | Hồ sơ account: username, password hash, authorities, flags | `UserDetailsService` trả về; provider dùng làm input |
| `Authentication` chưa xác thực | Người gọi **khai báo** danh tính gì và đưa credentials gì? | Filter/controller tạo authentication request |
| `Authentication` đã xác thực | Bằng chứng đã được kiểm tra, principal và authorities tin cậy là gì? | `AuthenticationManager` / `AuthenticationProvider` trả về |
| `SecurityContext` | Danh tính hiện hành của hoạt động xử lý là gì? | Security filters/điểm tích hợp ghi và đọc context |
| `SecurityContextHolder` | Cách truy cập context trong ứng dụng Servlet hiện hành | Thường lưu theo thread trong request |

Một `UserDetails` có thể tồn tại trong database nhiều tháng mà chưa từng có request đăng nhập. Một `Authentication` khác có thể được tạo sau khi JWT đã được kiểm chứng dù không hề gọi `UserDetailsService`. Đừng đồng nhất việc tạo `UserDetails` với việc đưa một người dùng vào `SecurityContextHolder`.

### 1.2. Những trường trên UserDetails được dùng thế nào?

Hợp đồng `UserDetails` cung cấp:

- `getUsername()`: username của hồ sơ đã tải; có thể được chuẩn hóa khác kiểu chữ hoa/thường của đầu vào.
- `getPassword()`: chuỗi đã lưu, thông thường là **password hash/encoded password**, không phải raw password.
- `getAuthorities()`: quyền/role gắn với account, dùng ở bước authorization khi authentication thành công.
- `isAccountNonExpired()`: account chưa hết hạn.
- `isAccountNonLocked()`: account chưa bị khóa.
- `isCredentialsNonExpired()`: credentials của account chưa hết hạn.
- `isEnabled()`: account đang được kích hoạt.

Chính `DaoAuthenticationProvider` (và lớp cha kiểm tra trạng thái) mới đọc các cờ và đưa ra kết quả xác thực phù hợp. `UserDetailsService` chỉ có nhiệm vụ tải và trả dữ liệu chính xác. Một implementation **có thể** thực hiện các ràng buộc đọc dữ liệu (như không tiết lộ account ngoài tenant được phép), nhưng không nên tự ý cấp trạng thái `authenticated`, trả access token hay viết HTTP response.

## 2. Toàn bộ luồng đăng nhập: service chỉ là một bước

Với Servlet và cách xác thực username/password qua HTTP Basic hoặc form login, luồng khái quát là:

~~~text
(1) Client gửi username + password
         |
         v
(2) Security filter phù hợp (BasicAuthenticationFilter,
    UsernamePasswordAuthenticationFilter, ...)
         |
         | tạo UsernamePasswordAuthenticationToken
         | chưa được xác thực
         v
(3) AuthenticationManager (thường là ProviderManager)
         |
         v
(4) DaoAuthenticationProvider
         |
         +----> (5) UserDetailsService.loadUserByUsername(username)
         |             |
         |             +--> trả UserDetails có hash, authorities, flags
         |
         +----> (6) kiểm tra account status và credentials
         |             |
         |             +--> PasswordEncoder.matches(rawPassword, storedHash)
         |
         +----> (7) thành công: tạo Authentication đã xác thực
         |             thất bại: ném AuthenticationException
         v
(8) Security filter xử lý kết quả
         |
         +--> thành công: đặt Authentication vào SecurityContext
         |    và lưu/khôi phục context qua cơ chế đã cấu hình
         |
         +--> thất bại: HTTP 401 hoặc luồng lỗi login phù hợp
         v
(9) Authorization kiểm tra quyền truy cập trước khi vào controller
~~~

Mô hình trên là để hiểu các trách nhiệm, thứ tự check chi tiết có thể khác theo provider và cấu hình cache. Điều quan trọng là **service tải dữ liệu**, còn **provider/manager xác thực** và **filter xử lý request, kết quả, context**.

### 2.1. AuthenticationManager và ProviderManager

`AuthenticationManager.authenticate(Authentication request)` là hợp đồng kiểm tra authentication request và trả `Authentication` kết quả, hoặc ném `AuthenticationException`. `ProviderManager` thường chọn một `AuthenticationProvider` phù hợp loại token. Với username/password lưu trong nguồn dữ liệu thông thường, provider là `DaoAuthenticationProvider`.

Một hệ thống có thể có nhiều provider (password, pre-auth, token tùy chỉnh). Việc tồn tại bean `UserDetailsService` không tự khiến mọi authentication request đi qua nó: chỉ những provider được cấu hình để dùng service đó và được chọn cho request mới gọi `loadUserByUsername`.

### 2.2. DaoAuthenticationProvider làm những việc mà service không làm

`DaoAuthenticationProvider` dùng `UserDetailsService` và `PasswordEncoder`. Với username/password phù hợp, nó:

1. Tải account tương ứng theo username (hoặc sử dụng UserDetails từ cache nếu có và hợp lệ theo cấu hình).
2. Kiểm tra các cờ account như locked/disabled/expired.
3. Dùng `PasswordEncoder.matches(rawPassword, userDetails.getPassword())` để so sánh mật khẩu người gọi đưa với hash được lưu.
4. Khi cần, kiểm tra trạng thái credentials và áp dụng các kiểm tra bổ sung của provider.
5. Nếu hợp lệ, tạo một `UsernamePasswordAuthenticationToken` đã xác thực, có principal và authorities phù hợp.
6. Nếu không hợp lệ, phát sinh một `AuthenticationException` thích hợp (ví dụ `BadCredentialsException`, `DisabledException` hoặc `LockedException`).

`PasswordEncoder` thực hiện việc so sánh/encode bí mật; nó **không** thuộc trách nhiệm `UserDetailsService`. Đừng lấy `getPassword()` từ account rồi so sánh chuỗi bằng `equals(rawPassword)`: cách đó sai với hash an toàn và dẫn đến lưu mật khẩu dạng rõ.

### 2.3. Filter và SecurityContext tiếp tục công việc

Sau khi nhận `Authentication` thành công, filter tương ứng đặt kết quả vào `SecurityContextHolder` (Servlet) và thực hiện các hành động thành công phù hợp. Với form login dựa session, context có thể được lưu qua `SecurityContextRepository`. Với HTTP Basic, browser/client thường gửi credentials ở mỗi request; không cần người dùng viết endpoint “login” riêng.

`UserDetailsService` không tạo cookie, không redirect tới trang login, không trả `401`/`302` và không quyết định quyền của endpoint. Các việc này thuộc security filter chain, authentication entry point, success/failure handlers, session management và authorization.

## 3. Đọc được UserDetails không phải là đăng nhập thành công

Giả sử bạn tự gọi:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("alice");
String name = user.getUsername();
boolean enabled = user.isEnabled();
~~~

Đây là **mã minh họa trong một phương thức đã được inject `UserDetailsService userDetailsService`**, không phải chương trình độc lập. Sau ba dòng này:

- Account có thể đã được tải thành công.
- Raw password người gọi **chưa được kiểm tra**.
- `AuthenticationManager.authenticate(...)` **chưa được gọi**.
- `SecurityContext` **chưa được cập nhật**.
- Người gọi **chưa có** danh tính tin cậy để truy cập endpoint được bảo vệ.

Tuyệt đối không tạo authenticated token chỉ vì load được user:

~~~java
// SAI: đoạn nguy hiểm, không bao giờ dùng để đăng nhập thật.
UserDetails user = userDetailsService.loadUserByUsername(username);
// Username do client nhập không chứng minh người gọi sở hữu account.
// Không tự gán authenticated=true hoặc gắn token vào context tại đây.
~~~

Nếu xây cơ chế đăng nhập tùy chỉnh, hãy chuyển credentials vào `AuthenticationManager`/provider đã được cấu hình và chỉ xử lý **kết quả thành công**. Trường hợp tự làm login ngoài filter dựng sẵn, còn phải thiết lập/lưu context, xử lý session fixation, CSRF và các bước liên quan đúng với Spring Security; chỉ gọi manager thôi cũng chưa tự hoàn thành toàn bộ HTTP login lifecycle.

## 4. Ví dụ Java 17+ có thể chạy: Spring Boot chỉ dùng UserDetailsService để tra cứu

Ví dụ dưới đây tạo một web application Spring MVC với HTTP Basic và ba endpoint `/public`, `/me`, `/admin`. Chúng ta chủ động cung cấp một bean `UserDetailsService` nhận dữ liệu từ `Map`, và bean `PasswordEncoder`. Spring Security sử dụng service qua cơ chế authentication username/password khi có cấu hình hỗ trợ; chúng ta **không viết code so sánh mật khẩu trong service**.

### 4.1. Khởi tạo project

Tạo Maven project trên Spring Initializr với:

- Java 17 (hoặc Java 21), Spring Boot 3.x.
- Dependencies: **Spring Web** (`spring-boot-starter-web`) và **Spring Security** (`spring-boot-starter-security`).
- Package: `com.example.demo`.

Tạo file **`src/main/java/com/example/demo/UserDetailsLookupApplication.java`**:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class UserDetailsLookupApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsLookupApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .disabled(true)
            .build();

        Map<String, UserDetails> records = Map.of(
            "alice", alice,
            "disabled", disabled
        );

        return username -> {
            UserDetails account = records.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Account not found");
            }
            return account;
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "Hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin only";
        }
    }
}
~~~

Các thành phần đã được chia vai trò rõ ràng:

- Bean `userDetailsService(...)` chỉ tra cứu `Map`, trả `UserDetails` hoặc ném `UsernameNotFoundException`.
- Bean `passwordEncoder()` định nghĩa cách hash/so khớp password; demo dùng BCrypt.
- `SecurityFilterChain` cấu hình vùng được phép truy cập và bật HTTP Basic để Spring Security có điểm nhận credentials.
- Provider username/password do cơ chế Spring Security lắp ghép sẽ sử dụng service và encoder để kiểm tra credentials.
- Controller `/me` nhận `Authentication` **sau khi** authentication filter xử lý thành công; nó không gọi service để tự coi client đã đăng nhập.
- `/admin` yêu cầu role `ADMIN`; `alice` chỉ có `ROLE_READER` nên sẽ bị từ chối dù password đúng.
- Account `disabled` có password đúng nhưng `isEnabled() == false`, vì vậy provider sẽ từ chối khi kiểm tra trạng thái account.

Lưu ý phiên bản: ví dụ hướng tới Spring Boot 3.x và Spring Security 6.x. Nếu bạn chủ động đăng ký một `AuthenticationManager` hoặc `AuthenticationProvider` khác, cách service được nối vào manager có thể thay đổi; lúc đó phải kiểm tra cấu hình của chính ứng dụng. Không coi việc chỉ có bean `UserDetailsService` là đảm bảo mọi loại authentication đều sử dụng nó.

### 4.2. Chạy thử và đối chiếu kết quả

Trong thư mục Maven project:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell dùng `.\mvnw.cmd spring-boot:run`. Mở terminal khác và gọi:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong-password http://localhost:8080/me
curl -i -u nobody:demo-pass http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/admin
~~~

Nếu `curl` trong PowerShell là alias, dùng `curl.exe`. Kết quả chính:

| Request | HTTP status kỳ vọng | Nội dung cần quan sát |
| --- | --- | --- |
| `GET /public` không credentials | `200 OK` | Body `public` |
| `GET /me` không credentials | `401 Unauthorized` | HTTP Basic challenge; không có body `Hello alice` |
| `GET /me` với `alice:demo-pass` | `200 OK` | Body chính xác: `Hello alice` |
| `GET /me` với `alice:wrong-password` | `401 Unauthorized` | Mật khẩu sai bị từ chối |
| `GET /me` với `nobody:demo-pass` | `401 Unauthorized` | Account không tìm thấy |
| `GET /me` với `disabled:demo-pass` | `401 Unauthorized` | Account bị vô hiệu hóa dù password đúng |
| `GET /admin` với `alice:demo-pass` | `403 Forbidden` | Đã xác thực nhưng thiếu `ROLE_ADMIN` |

Header, response body của lỗi và thứ tự header có thể khác theo servlet container, config và client. Không giả định `UsernameNotFoundException` sẽ lộ ra cho HTTP client; provider thường chuyển sai username và sai mật khẩu thành lỗi chung để tránh dò tìm account.

**Điều bài thử chứng minh:** có `UserDetailsService` thì account `alice` được tải; nhưng phải có đường đi qua authentication filter, manager, provider và encoder thì HTTP request mới nhận `200`. Account `disabled` cho thấy “đọc thành công” không đồng nghĩa “xác thực hợp lệ”. Endpoint `/admin` cho thấy “xác thực hợp lệ” vẫn khác “được cấp quyền”.

### 4.3. Nếu chỉ gọi service mà không đi qua filter thì sao?

Bạn có thể gọi trực tiếp bean trong một `CommandLineRunner` hoặc test:

~~~java
// Mã minh họa nằm trong method đã inject UserDetailsService.
UserDetails alice = userDetailsService.loadUserByUsername("alice");
System.out.println(alice.getUsername());
System.out.println(alice.isEnabled());
~~~

Khi service dùng dữ liệu ở ví dụ trên, hai dòng in sẽ là:

~~~text
alice
true
~~~

Hai dòng đó chỉ chứng minh dữ liệu lookup. Chúng **không** tạo session, không phát token, không đảm bảo `SecurityContextHolder.getContext().getAuthentication()` chứa Alice và không tạo một request đã đăng nhập. Nếu bạn có sẵn một HTTP request của user khác, đọc dữ liệu Alice cũng không có quyền “chuyển” request ấy thành Alice.

## 5. Đổi nguồn dữ liệu: repository/database không thay đổi hợp đồng

Trong ứng dụng thật, `UserDetailsService` thường chuyển một account entity sang `UserDetails`, ví dụ:

~~~text
POST /login / Authorization header
         |
         v
DaoAuthenticationProvider
         |
         +--> AccountRepository.findByUsername(username)
                 |
                 +--> AccountEntity
                        username
                        passwordHash
                        enabled
                        locked
                        authorities
                 |
                 v
              UserDetails
         |
         +--> PasswordEncoder.matches(...)
         +--> account status checks
         |
         v
     Authentication đã xác thực
~~~

Tầng repository không nên biết filter hoặc HTTP session; tầng `UserDetailsService` đóng vai trò **adapter** giữa domain user và Spring Security. Cách chia việc thường hợp lý:

| Thành phần | Nên chịu trách nhiệm |
| --- | --- |
| `AccountRepository` | Truy vấn domain account từ database |
| `UserDetailsService` | Tra cứu bằng username và chuyển dữ liệu account sang `UserDetails` |
| `PasswordEncoder` | Hash và so khớp password |
| `DaoAuthenticationProvider` | Kiểm tra raw credentials với hash và trạng thái account |
| `AuthenticationManager` | Điều phối các provider và trả kết quả xác thực |
| Filter + `SecurityContext` | Tiếp nhận HTTP request và giữ kết quả xác thực trong phạm vi thích hợp |
| Authorization layer | Kiểm tra role/authority để bảo vệ endpoint/method |

Không lấy raw password từ HTTP request rồi chuyển vào `loadUserByUsername` qua một chuỗi lắp ghép như `username + ":" + password`. Hợp đồng chỉ yêu cầu username; đưa mật khẩu vào lookup có thể khiến secrets lộ trong log, query hoặc cache key. Với hệ thống có tenant, khóa lookup có thể cần được cấu trúc lại bằng một cách xác thực phù hợp, không tự ý tin header tenant chưa kiểm chứng.

### 5.1. Một adapter minh họa có nguồn database

Ví dụ sau **không phải file độc lập**: nó giả định ứng dụng đã có domain types `AccountRepository`, `Account`, cùng các method được liệt kê trong comment. Mục đích là mô tả ranh giới adapter mà không gắn bài với JPA/JDBC cụ thể.

~~~java
@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        // Domain contract giả định:
        // repository.findByUsername(username) -> Optional<Account>
        Account account = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!account.enabled())
            .build();
    }
}
~~~

Các import của đoạn minh họa gồm `org.springframework.stereotype.Service`, `UserDetailsService`, `UserDetails`, `User` và `UsernameNotFoundException` từ Spring Security. Giả định `account.authorities()` trả `Collection<? extends GrantedAuthority>`, phù hợp overload của `User.UserBuilder.authorities(...)`; `account.passwordHash()` là hash đã lưu. Các trường lock/expiry khác nếu domain quản lý cần được ánh xạ đúng, không mặc định tất cả luôn hợp lệ.

Để đoạn này biên dịch/chạy, phải cung cấp `AccountRepository`/`Account` thực tế và adapter persistence của project. Không đặt nó cạnh bean `userDetailsService(...)` ở ví dụ chạy mà không chọn rõ một implementation; nhiều bean cùng kiểu có thể làm cấu hình xác thực trở nên không xác định.

**Nguyên tắc ánh xạ role:** `roles("ADMIN")` của builder tự sinh authority `ROLE_ADMIN`; trong khi `authorities(...)` dùng tên quyền được đưa vào. Nếu domain đã lưu `ROLE_ADMIN` thì dùng `authorities(...)` phù hợp, tránh vô tình thành `ROLE_ROLE_ADMIN` do thêm tiền tố hai lần.

## 6. Các trường hợp lỗi: service báo gì, provider báo gì?

### 6.1. Username không tồn tại

`UserDetailsService.loadUserByUsername("nobody")` phải ném `UsernameNotFoundException`. Nhưng `DaoAuthenticationProvider` theo cấu hình mặc định của `AbstractUserDetailsAuthenticationProvider` thường ẩn chi tiết này thành `BadCredentialsException`, cùng nhóm với mật khẩu sai. Điều đó giảm khả năng attacker dựa vào nội dung lỗi để liệt kê username hợp lệ.

Không nên trả `null`, tạo user trống với password bất kỳ hoặc cho phép caller đoán account có tồn tại từ response public. Nếu backend có audit riêng, nó có thể ghi một mã lỗi nội bộ đã được chuẩn hóa mà không lộ danh tính hoặc bí mật.

### 6.2. Password sai dù tài khoản tồn tại

Service vẫn có thể trả `UserDetails` hoàn toàn hợp lệ. Provider so sánh mật khẩu thông qua `PasswordEncoder` và báo lỗi khi không khớp. Vì vậy, **kết quả lookup thành công không bảo đảm kết quả login thành công**.

Không so sánh password bằng `String.equals` với hash. Nếu service trả sai định dạng hash, hoặc encoder không tương thích định dạng, authentication thất bại dù người dùng nhập đúng raw password.

### 6.3. Tài khoản bị khóa, hết hạn hoặc disabled

Service trả dữ liệu trạng thái (thường trong `UserDetails`), còn provider sẽ đánh giá. `DisabledException`, `LockedException`, `AccountExpiredException` và `CredentialsExpiredException` là những failure phù hợp với các cờ tương ứng.

Không bỏ qua flag bằng cách luôn tạo `UserDetails` có `enabled(true)` chỉ để login thử thành công. Nếu hệ thống quản trị account cho phép unlock, flow đổi trạng thái thuộc nghiệp vụ quản lý account có thẩm quyền, không nằm trong phương thức `loadUserByUsername`.

### 6.4. Database/identity store lỗi

Không đánh đồng sự cố database với “user không tồn tại”. Một lỗi kết nối hoặc timeout có thể cần được chuyển thành lỗi hạ tầng xác thực phù hợp và quan sát trong monitoring. Không nên trả một tài khoản đặc biệt hay bỏ kiểm tra mật khẩu khi repository lỗi (fail-open). Cũng không nên công bố thông tin connection string, SQL hoặc danh sách username trong HTTP error.

### 6.5. Không có GrantedAuthority

Hợp đồng JavaDoc yêu cầu record được tải đầy đủ và nêu `UsernameNotFoundException` khi không thể tìm thấy user hoặc không có `GrantedAuthority`. Với ứng dụng có user không có role, bạn cần quyết định policy representation phù hợp, tránh ngầm cấp quyền để “cho tải được”. Đừng biến quyền của request thành dữ liệu tùy ý trong service.

## 7. Thời điểm load và câu chuyện cache/session

Một hiểu nhầm phổ biến là “mỗi request bảo vệ sẽ chạy `loadUserByUsername` đúng một lần”. Thực tế còn phụ thuộc cơ chế xác thực và cấu hình:

- Với **form login + session**, lần đăng nhập có thể load user, sau đó request khác khôi phục `SecurityContext` đã được lưu trong session. Không nhất thiết gọi lại service ở mọi trang.
- Với **HTTP Basic**, client thường gửi credentials lại ở mỗi request; security filter/provider có thể kiểm tra lại, nhưng không nên viết logic nghiệp vụ dựa vào giả định số lần lookup cố định.
- `AbstractUserDetailsAuthenticationProvider` có hỗ trợ `UserCache`; mặc định `NullUserCache` trong những cấu hình tiêu chuẩn. Nếu dùng cache, provider vẫn phải xử lý password check và quy tắc cập nhật; không coi lookup cache như bằng chứng xác thực.
- Khi đổi password, lock/unlock hoặc thu hồi quyền, bạn phải thiết kế tính nhất quán của cache, session và token. Thay dữ liệu ở repository không luôn tự lập tức xóa mọi `Authentication` đã được lưu trước đó.

**Điểm bảo mật quan trọng:** `ProviderManager` thường xóa credentials nhạy cảm trên authentication thành công nếu object hỗ trợ `CredentialsContainer`. Nếu `Authentication` giữ tham chiếu tới đúng object `UserDetails` đang được cache, việc xóa credentials có thể ảnh hưởng tới dữ liệu cache nếu không sao chép thích hợp. Hãy quản lý cache và credential erasure có chủ đích; không tắt việc xóa bí mật chỉ để chữa triệu chứng khi có thể sửa cách lưu cache.

Không để service tự giữ biến “người đang đăng nhập” toàn cục hoặc một `SecurityContext` static. Spring singleton bean phục vụ nhiều request/người dùng; trạng thái đăng nhập thuộc context phù hợp từng request/session/token.

## 8. Không phải mọi Authentication đều dùng UserDetailsService

`UserDetailsService` gắn đặc biệt với xác thực username/password kiểu account lookup. Một số cơ chế khác có nguồn danh tính hoặc cách xác thực riêng:

| Cơ chế | Có bắt buộc gọi `UserDetailsService` không? | Vì sao |
| --- | --- | --- |
| Form login với `DaoAuthenticationProvider` | Có, trong đường lookup thường gặp (trừ những tối ưu/cache hợp lệ) | Cần user record và password hash |
| HTTP Basic dùng `DaoAuthenticationProvider` | Có, theo cấu hình provider hỗ trợ Basic username/password | Credentials được đưa vào provider |
| JWT resource server | **Không** mặc định | Token được giải mã/kiểm tra chữ ký, issuer, hạn và claims theo resource server |
| OAuth2 login / OpenID Connect | **Không** mặc định | Danh tính đến từ luồng OAuth2/OIDC và principal/token tương ứng |
| SAML2 login | **Không** mặc định | Danh tính dựa trên SAML assertion đã được xác minh |
| mTLS / X.509 hoặc pre-auth | **Không** mặc định | Chứng cứ có thể là certificate hoặc nguồn được tin cậy |
| Custom API key provider | **Không** bắt buộc | Provider có thể tra cứu API key theo mô hình riêng |

Có thể kết hợp thêm `UserDetailsService` để *bổ sung dữ liệu account* sau khi một cơ chế khác đã xác thực, nhưng đó là **tích hợp được thiết kế riêng**: hãy xác minh mapping giữa token principal và account nội bộ, không tự tin username/claims chưa qua kiểm chứng. Không nên biến tất cả các cơ chế thành lời gọi giả tới `loadUserByUsername` để “giống form login”.

### 8.1. Reactive WebFlux dùng hợp đồng khác

Với Spring WebFlux, biến thể thường dùng là `ReactiveUserDetailsService`:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

Đây là chữ ký giản lược của giao diện reactive; `Mono<UserDetails>` đại diện kết quả bất đồng bộ. `MapReactiveUserDetailsService` là implementation in-memory. `UserDetailsRepositoryReactiveAuthenticationManager` dùng `ReactiveUserDetailsService` và `PasswordEncoder` để xác thực username/password trong reactive stack.

Tương tự Servlet, **reactive service cũng chỉ tìm account**, không tự kiểm chứng toàn bộ authentication HTTP. Đừng gọi JDBC blocking `loadUserByUsername` trực tiếp trên WebFlux event loop rồi nghĩ rằng API đó đã non-blocking. Chọn repository/reactive bridge thích hợp; gắn authentication vào Reactor Context thông qua Spring Security reactive pipeline, không dùng mặc định `SecurityContextHolder` gắn với thread như Servlet.

## 9. Cấu hình Spring Boot: tại sao bean UserDetailsService chưa phải toàn bộ security?

Trong Spring Boot có Spring Security starter, khi chưa có tùy chỉnh phù hợp, Boot có thể cung cấp một in-memory user dùng cho mục đích phát triển. Khi bạn đăng ký bean `UserDetailsService` riêng, auto-configuration user mặc định thường nhường cho bean đó. Tuy nhiên:

- **Bean `UserDetailsService`** quyết định nguồn account lookup.
- **Bean `SecurityFilterChain`** quyết định request nào được bảo vệ, bật Basic/form login/resource server và luật authorization.
- **`AuthenticationManager` và `AuthenticationProvider`** quyết định cơ chế credentials nào được chấp nhận; custom manager/provider có thể làm thay đổi wiring mặc định.
- **Bean `PasswordEncoder`** quyết định cách so khớp password hash; hash trong database phải khớp loại encoder/cấu hình.
- **Success/failure handlers, session management, CSRF, CORS** và các chính sách khác vẫn là trách nhiệm của các thành phần tương ứng.

Cấu hình ví dụ ở mục 4 chủ động bật `httpBasic(withDefaults())`. Nếu bạn bỏ HTTP Basic và form login mà không bật cơ chế xác thực nào khác, chỉ tạo bean `UserDetailsService` **không tự tạo một endpoint login có chức năng**. Ngược lại, nếu bạn sử dụng một custom `AuthenticationProvider` không gọi service, bean service có thể tồn tại nhưng không tham gia flow.

Tài liệu Spring Boot cũng nêu rằng khi các module như OAuth2 Client, Resource Server hoặc SAML2 Service Provider xuất hiện, cơ chế auto-configuration user có những điều kiện nhường riêng. Vì thế, hãy kiểm tra các bean và provider thực tế của ứng dụng, không dựa trên “đã định nghĩa service là xong”.

### 9.1. Nếu cần tự ghép manager và provider

Trong một cấu hình thủ công phục vụ username/password, quan hệ cơ bản có thể viết như sau:

~~~java
DaoAuthenticationProvider dao =
    new DaoAuthenticationProvider(userDetailsService);
dao.setPasswordEncoder(passwordEncoder);

AuthenticationManager manager =
    new ProviderManager(java.util.List.of(dao));
~~~

Đây là **đoạn minh họa trong cấu hình đã có `UserDetailsService userDetailsService` và `PasswordEncoder passwordEncoder`**, không phải file Java độc lập và không cần thêm vào ví dụ mục 4. Với Spring Security 6.x, constructor `DaoAuthenticationProvider(UserDetailsService)` là lựa chọn rõ ràng; đặt encoder bằng `setPasswordEncoder(...)`. `ProviderManager` điều phối provider.

Muốn triển khai custom login endpoint bên ngoài cơ chế dựng sẵn, bạn phải nhận credentials, gọi `manager.authenticate(...)` và chỉ sau kết quả thành công mới gắn context, lưu session hoặc phát token theo contract phù hợp. Gọi `loadUserByUsername(...)` ở controller rồi tự trả “login success” bỏ qua phần cốt lõi của xác thực.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Có user trong database nhưng đăng nhập luôn `401` | Hash sai định dạng, encoder không khớp, sai password, provider không được cấu hình | Kiểm tra provider, `PasswordEncoder.matches`, mapping `UserDetails` |
| Gọi `loadUserByUsername` thành công nhưng request vẫn anonymous | Gọi service đơn thuần không xác thực hoặc cập nhật context | Dùng authentication filter/manager, không tự “đăng nhập” từ lookup |
| `ClassCastException` khi ép principal | Principal không phải luôn là loại `UserDetails` custom dự kiến | Kiểm tra `Authentication.getPrincipal()` và cơ chế authentication thực tế |
| Account bị disabled nhưng vẫn được vào ứng dụng | Mapping cờ trạng thái sai hoặc provider không kiểm tra theo kỳ vọng | Trả đúng `isEnabled()`; kiểm tra provider và test account disabled |
| Sai username trả lỗi chi tiết, giúp dò account | Cấu hình lộ `UsernameNotFoundException` hoặc response công khai thông tin | Trả lỗi auth chung; log nội bộ có kiểm soát |
| Trả `null` khi không thấy account | Vi phạm contract `loadUserByUsername` | Ném `UsernameNotFoundException` |
| Hash BCrypt trong DB nhưng dùng `NoOpPasswordEncoder` | So sánh sai hoặc cấu hình không an toàn | Dùng encoder phù hợp; không lưu cleartext |
| Thêm bean UserDetailsService mà không có hiệu lực | Custom AuthenticationProvider/Manager khác đã được ưu tiên | Kiểm tra wiring, thứ tự providers và actual filter chain |
| Mỗi request tải DB quá nhiều | HTTP Basic hoặc provider/cache/session làm phát sinh lookup nhiều lần | Đo/trace, tối ưu repository và cache phù hợp, không vô hiệu hóa security checks |
| Mật khẩu hash bị thay đổi trong UserDetails cache | Erase-credentials có thể tác động object cache tham chiếu chung | Dùng bản sao/thiết kế cache phù hợp, tránh lưu credentials lâu |
| Code WebFlux bị block hoặc principal không thấy | Dùng blocking `UserDetailsService` hoặc ThreadLocal sai mô hình | Dùng `ReactiveUserDetailsService` và reactive security context |

**Giữ bí mật khi debug:** không log raw password, Basic Authorization header, session cookie, raw JWT hoặc chuỗi hash đầy đủ. Chỉ nên log metadata tối thiểu (request ID, cơ chế auth, mã trạng thái), với quyền đọc và retention phù hợp. HTTP Basic cần HTTPS trong môi trường thật.

## 11. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Code gọi `UserDetailsService.loadUserByUsername("alice")` rồi nhận một `UserDetails` hợp lệ. Có thể đặt ngay `SecurityContextHolder` thành Alice không?

**Đáp án:** không. Chưa có bước xác minh credentials và account policy. Phải sử dụng cơ chế authentication hợp lệ và chỉ ghi context từ kết quả thành công có thể tin cậy.

**Câu 2.** Alice có trong database, nhưng nhập sai password. Method của service có nhất thiết ném `UsernameNotFoundException` không?

**Đáp án:** không. Service vẫn có thể trả Alice; `DaoAuthenticationProvider` gọi `PasswordEncoder.matches(...)` và từ chối credentials không đúng.

**Câu 3.** Account disabled nhưng mật khẩu đúng. Service nên trả record hay tự coi là đăng nhập thành công?

**Đáp án:** service trả record với `isEnabled() == false`. Provider kiểm tra status và không cấp authentication thành công. Service không tạo `SecurityContext`.

**Câu 4.** Có JWT Resource Server mà không đăng ký `UserDetailsService`. Có thể xác thực bearer token không?

**Đáp án:** có, nếu resource server và decoder/introspector được cấu hình đúng. Cơ chế JWT không bắt buộc thực hiện username/password account lookup theo hợp đồng này.

**Câu 5.** User đổi password trong database, nhưng có một session đã đăng nhập. Vì sao user có thể vẫn được xem là authenticated?

**Đáp án:** request có thể khôi phục `Authentication` đã lưu từ session, không bắt buộc so sánh password lại mọi request. Nếu yêu cầu đăng xuất toàn bộ phiên sau đổi mật khẩu, đó là chính sách thu hồi session/token phải triển khai riêng.

**Câu 6.** `getUsername()`, `getPassword()` và `getAuthorities()` cùng tồn tại trong `UserDetails`. Có nghĩa `UserDetailsService` đã kiểm tra role và tự quyết định vào `/admin`?

**Đáp án:** không. Service cung cấp dữ liệu; provider kiểm tra xác thực; authorization dùng authorities để quyết định truy cập endpoint.

**Câu 7.** Bạn triển khai `loadUserByUsername` rồi trong đó gọi `PasswordEncoder.matches(...)`, tự phát JWT và ghi session. Vấn đề là gì?

**Đáp án:** đã trộn ba trách nhiệm vào một read-only lookup contract, không nhận raw password theo API, dễ bỏ qua authentication lifecycle, error handling và security hooks. Tách lookup, authentication và token/session handling về đúng thành phần.

## 12. Checklist khi triển khai thực tế

1. `loadUserByUsername` chỉ tra cứu username, trả một `UserDetails` đầy đủ hoặc ném `UsernameNotFoundException`, không trả null.
2. Password trong `UserDetails` là hash hợp lệ; cách encode khi tạo/đổi password tương thích `PasswordEncoder` dùng lúc đăng nhập.
3. Mapping authorities đúng quy ước `ROLE_` và mapping account status đúng dữ liệu domain.
4. `SecurityFilterChain` bật cơ chế authentication cần thiết, bảo vệ đúng URL và không cấu hình quá rộng.
5. `AuthenticationManager` thực sự dùng provider có sử dụng service đã khai báo; kiểm tra khi có custom provider/manager khác.
6. Đã thử account không tồn tại, password sai, disabled/locked, password đúng, và role không đủ.
7. Không log credentials hoặc trả lỗi chi tiết cho người dùng chưa xác thực; có monitoring cho lỗi hạ tầng kho tài khoản.
8. Cache/session có chiến lược phù hợp khi tài khoản bị khóa, đổi password, đổi quyền hoặc bị vô hiệu hóa.
9. Với WebFlux, chọn đúng reactive API và tránh blocking database trên event loop.
10. Không tự nhận diện người dùng là đã đăng nhập chỉ nhờ `UserDetailsService` trả kết quả.

**Ghi nhớ:** `UserDetailsService` là **bộ phận tải dữ liệu account**, không phải toàn bộ hệ thống login. `DaoAuthenticationProvider` cùng `PasswordEncoder` kiểm chứng credentials và trạng thái tài khoản; `AuthenticationManager` điều phối kết quả; security filter đặt danh tính thành công vào `SecurityContext` và bảo vệ HTTP request. Giữ đúng ranh giới này giúp code dễ kiểm thử, an toàn và thay đổi được nguồn dữ liệu mà không phá vỡ authentication flow.

## Tài liệu tham khảo

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 API — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)
- [Spring Security 6.5 API — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Boot — Spring Security auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security 6.5 API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html)
