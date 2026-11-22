# Quan hệ giữa Spring Security, Spring Boot và kho danh tính

## 1. Ba thành phần giải quyết ba trách nhiệm khác nhau

Khi xây dựng chức năng đăng nhập cho một ứng dụng Spring Boot, cần phân biệt **nền tảng chạy ứng dụng**, **cơ chế bảo mật** và **nguồn thông tin danh tính**:

| Thành phần | Trách nhiệm chính | Không tự làm thay phần còn lại |
| --- | --- | --- |
| **Spring Boot** | Khởi tạo ứng dụng, quản lý dependency, cấu hình và auto-configuration; kết nối các bean và đưa ứng dụng web vào chạy. | Không mặc nhiên biết người dùng thật được lưu trong bảng, LDAP hay nhà cung cấp danh tính nào. |
| **Spring Security** | Chặn/xử lý request ở lớp bảo mật; thực hiện xác thực (*authentication*), phân quyền (*authorization*), quản lý `SecurityContext`, tích hợp nhiều phương thức đăng nhập. | Không phải hệ quản trị người dùng hay cơ sở dữ liệu danh tính. |
| **Kho danh tính** (*identity store*) | Lưu hoặc cung cấp danh tính, trạng thái tài khoản, mật khẩu đã băm (nếu có), nhóm/quyền hoặc thuộc tính người dùng. Ví dụ: bộ nhớ thử nghiệm, cơ sở dữ liệu, LDAP/Active Directory. | Chỉ tồn tại dữ liệu không có nghĩa là request HTTP tự được xác thực hoặc cấp quyền. |
| **Identity Provider (IdP)**, nếu dùng | Một hệ thống độc lập thực hiện đăng nhập/liên kết danh tính, ví dụ hệ thống hỗ trợ OpenID Connect (OIDC) hoặc SAML. | Không đồng nghĩa với bảng `users` nội bộ; ứng dụng vẫn phải kiểm tra token/phiên và quyết định quyền truy cập tài nguyên của mình. |

**Quan hệ cốt lõi:** Spring Boot tạo và cấu hình ứng dụng; Spring Security thực thi chính sách an ninh khi request đi vào; kho danh tính hoặc IdP cung cấp bằng chứng và thông tin để cơ chế xác thực ra quyết định. Ứng dụng chịu trách nhiệm ánh xạ danh tính đã xác thực thành quyền truy cập cụ thể.

Ví dụ: dự án khai báo `spring-boot-starter-security` sẽ nhận các thành phần bảo mật từ Spring Security nhờ cơ chế cấu hình của Boot. Nếu ứng dụng muốn đăng nhập bằng tài khoản trong cơ sở dữ liệu, lập trình viên vẫn phải nối Spring Security với nguồn dữ liệu phù hợp; chỉ thêm Spring Data JPA và tạo bảng `users` là chưa đủ.

## 2. Xác thực, phân quyền và dữ liệu người dùng không phải một thao tác

- **Xác thực (authentication):** trả lời “request này đang đại diện cho ai?” bằng cách kiểm tra bằng chứng thích hợp: mật khẩu, phiên đăng nhập, token, hoặc phản hồi từ IdP.
- **Phân quyền (authorization):** trả lời “danh tính đó có được gọi tài nguyên/hành động này không?”. Ví dụ người mang quyền `ROLE_READER` được truy cập `/private`.
- **Kho danh tính:** nơi lấy dữ liệu cần thiết cho một hoặc cả hai bước, chẳng hạn tên đăng nhập, hash mật khẩu, tài khoản bị khóa, nhóm và quyền.
- **Thông tin đăng nhập khác thông tin danh tính:** một tên người dùng có thể tra được trong DB nhưng mật khẩu sai thì chưa được xác thực; đã đăng nhập thành công cũng không có nghĩa được phép truy cập mọi API.

Trong Spring Security, đối tượng `Authentication` biểu diễn yêu cầu xác thực hoặc kết quả đã xác thực; `principal` nói đến chủ thể, `credentials` là bằng chứng, `GrantedAuthority` biểu diễn các quyền. `SecurityContext` giữ `Authentication` hiện hành. Với ứng dụng servlet, `SecurityContextHolder` thường liên kết ngữ cảnh với luồng xử lý; việc nạp/lưu ngữ cảnh qua các request phụ thuộc cơ chế phiên, repository và bộ lọc đã cấu hình.

## 3. Luồng điển hình: HTTP Basic + tài khoản và mật khẩu

Sơ đồ sau mô tả **một trường hợp cụ thể** của ứng dụng Spring MVC/Servlet khi dùng username/password. OIDC, JWT hoặc đăng nhập theo biểu mẫu có chi tiết luồng riêng.

```text
HTTP client
    |
    v
Servlet container
    |
    v
Spring Security filter chain (FilterChainProxy / SecurityFilterChain)
    |
    +--> Bộ lọc nhận Basic credentials (username/password)
             |
             v
       AuthenticationManager (thường là ProviderManager)
             |
             v
       AuthenticationProvider (ví dụ DaoAuthenticationProvider)
             |                        |
             |                        +--> PasswordEncoder.matches(...)
             v
       UserDetailsService.loadUserByUsername(...)
             |
             v
       Adapter/Repository --> Kho danh tính (bộ nhớ, DB, LDAP...)
             |
             v
       UserDetails + authorities + password hash
             |
             v
       Xác thực thành công / thất bại
             |
             v
       SecurityContext chứa Authentication đã xác thực
             |
             v
       AuthorizationFilter / kiểm tra quyền truy cập
             |
             v
       Controller, service, tài nguyên được bảo vệ
```

Các điểm cần hiểu đúng:

1. **`SecurityFilterChain` quyết định đường đi của request** và các bộ lọc bảo vệ nó, ví dụ cấu hình `httpBasic()`, `formLogin()` hay `oauth2Login()`. Boot hỗ trợ đăng ký cấu hình vào ứng dụng, còn Spring Security cung cấp bộ lọc và quy tắc.
2. **`AuthenticationManager` điều phối xác thực**; `ProviderManager` có thể chọn một trong nhiều `AuthenticationProvider` theo kiểu bằng chứng. Không phải mọi request đều đi qua `DaoAuthenticationProvider`.
3. Với **username/password**, `DaoAuthenticationProvider` thường dùng `UserDetailsService` để tải tài khoản và `PasswordEncoder` để so mật khẩu gõ vào với mật khẩu **đã băm**. `UserDetailsService` chỉ tải dữ liệu; nó không tự kiểm tra mật khẩu và không mặc nhiên tạo tài khoản.
4. Sau xác thực thành công, Spring Security có thể dùng `Authentication` trong `SecurityContext` để kiểm tra quyền; cách ngữ cảnh được lưu qua request phụ thuộc hình thức xác thực. Với HTTP Basic, client thường gửi lại credentials cho các request tiếp theo; với đăng nhập biểu mẫu có thể sử dụng session.
5. Nếu chưa xác thực khi gọi tài nguyên được bảo vệ, cơ chế HTTP Basic thường trả **401 Unauthorized** kèm yêu cầu xác thực. Nếu đã xác thực nhưng thiếu quyền, thường trả **403 Forbidden**. Mã trả thực tế còn phụ thuộc cấu hình entry point/handler.

**Ranh giới quan trọng:** repository dữ liệu không được gọi trực tiếp từ mỗi controller để tự xác thực rồi tự lưu cờ `isLoggedIn`. Tạo cơ chế xác thực qua Spring Security để yêu cầu, ngữ cảnh và chính sách quyền được xử lý nhất quán.

## 4. Spring Boot tự cấu hình gì, và khi nào cần tự cấu hình?

Khi có Spring Security trên classpath của ứng dụng web servlet và chưa cung cấp cấu hình thay thế, Spring Boot áp dụng bảo mật mặc định: các request được bảo vệ và có hỗ trợ đăng nhập/HTTP Basic phù hợp với cấu hình mặc định. Trong cấu hình đơn giản có cơ chế user mặc định, Boot có thể tạo tài khoản `user` cùng mật khẩu sinh ngẫu nhiên và ghi mật khẩu ra log khởi động. **Đây là thiết lập thuận tiện khi phát triển, không phải thiết kế người dùng production.**

Hai loại cấu hình có thể thay đổi **độc lập**:

| Bạn khai báo | Ý nghĩa |
| --- | --- |
| Bean `SecurityFilterChain` | Bạn làm chủ các quy tắc URL, bộ lọc và cơ chế xác thực HTTP; cấu hình bảo mật web mặc định của Boot nhường chỗ. |
| Bean `UserDetailsService` | Bạn cung cấp nguồn tải tài khoản cho nhánh xác thực username/password. |
| Bean `AuthenticationProvider` hoặc `AuthenticationManager` | Bạn cung cấp cách xác thực hoặc bộ điều phối xác thực phù hợp ứng dụng. |
| Bean `PasswordEncoder` | Bạn quy định thuật toán/định dạng so khớp mật khẩu cho đường xác thực dùng mật khẩu; phải tương thích hash đã lưu. |

**Một nhầm lẫn phổ biến:** chỉ tạo bean `SecurityFilterChain` **không tự tắt** cơ chế Boot cấu hình `UserDetailsService` mặc định. Muốn kiểm soát user store của ứng dụng cần khai báo bean thích hợp, như `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager`. Một số module như OAuth2 Client/Resource Server/SAML2 cũng ảnh hưởng điều kiện Boot tự cấu hình user mặc định; vì vậy không nên dựa vào tài khoản sinh tự động cho môi trường thật.

Không có quy tắc “Spring Boot luôn tự tạo bảng users”. Boot có thể auto-configure `DataSource` hay JPA khi đủ dependency/configuration, nhưng **chức năng lưu trữ dữ liệu** và **chức năng xác thực bằng dữ liệu đó** vẫn là hai tầng khác nhau.

## 5. Ví dụ chạy được: Boot kết nối Spring Security với kho user trong bộ nhớ

Ví dụ dưới đây dùng **Spring Boot 3.3.x, Java 17+ và Gradle 8.5+**, một lớp ứng dụng Java hoàn chỉnh. Mục đích là chỉ ra rõ vị trí mỗi bên tham gia: Boot khởi chạy, Security bảo vệ URL, `InMemoryUserDetailsManager` đóng vai kho danh tính thử nghiệm. Ví dụ dùng mật khẩu demo cố định **chỉ để học**, không dùng trong production.

Cấu trúc:

```text
identity-demo/
├── build.gradle
└── src/main/java/demo/identity/IdentityDemoApplication.java
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `src/main/java/demo/identity/IdentityDemoApplication.java`:

```java
package demo.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").hasRole("READER")
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("minh")
                .password(encoder.encode("ChangeMe123!"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "Public OK";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello " + authentication.getName();
        }
    }
}
```

Trong terminal tại thư mục dự án, dùng JDK 17+ và Gradle tương thích:

```bash
gradle bootRun

# Terminal khác: endpoint công khai
curl -s http://localhost:8080/public

# Chỉ lấy HTTP status khi chưa gửi tài khoản
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private

# Gửi thông tin xác thực để truy cập endpoint được bảo vệ
curl -s -u 'minh:ChangeMe123!' http://localhost:8080/private
```

Kết quả phần response (không gồm log khởi động):

```text
Public OK
401
Hello minh
```

Giải thích theo đúng ba trách nhiệm:

- **Spring Boot** chạy lớp có `@SpringBootApplication`, thiết lập web server và tạo các bean.
- **Spring Security** lấy bean `SecurityFilterChain`: `/public` được phép gọi công khai; `/private` đòi `ROLE_READER`; endpoint khác bị từ chối. HTTP Basic cung cấp thông tin để xác thực.
- **Kho danh tính trong bộ nhớ** là `InMemoryUserDetailsManager`, chứa người dùng `minh` với BCrypt hash và role `READER`. `hasRole("READER")` tương ứng authority `ROLE_READER`.
- **PasswordEncoder** mã hóa mật khẩu demo trước khi đưa vào bộ nhớ và giúp cơ chế xác thực so khớp. Băm là hàm một chiều; không “giải mã” mật khẩu từ DB.
- Endpoint riêng nhận `Authentication` từ Spring Security, nên controller không cần tự kiểm tra mật khẩu.

Đây là ứng dụng nhỏ, không có chức năng đăng ký, reset mật khẩu, audit, rate limiting hay dữ liệu bền vững. HTTP Basic trên đường truyền thực phải đi cùng **HTTPS**; truyền credentials qua HTTP không an toàn. Giữ CSRF protection theo mặc định trong ví dụ; khi chuyển sang API khác, cần đánh giá cơ chế xác thực và CSRF cụ thể, không tắt bảo vệ chỉ để thử cho nhanh.

## 6. Đổi từ bộ nhớ sang kho danh tính thật: điểm cần thay là adapter

Giả sử bảng nội bộ có dữ liệu:

```text
users(id, username UNIQUE, password_hash, enabled)
user_roles(user_id, role_name)
```

Một thiết kế thông dụng khi dùng Spring Data JPA:

1. `UserRepository` đọc account từ cơ sở dữ liệu bằng username/ID.
2. Lớp triển khai `UserDetailsService` (hoặc bean phù hợp) chuyển account thành `UserDetails`: username, **hash** mật khẩu, cờ enabled/locked/expired và `GrantedAuthority`. Nếu không tìm thấy, ném `UsernameNotFoundException`.
3. `DaoAuthenticationProvider` sử dụng `UserDetailsService` và `PasswordEncoder` đã cấu hình để kiểm tra credentials.
4. Sau xác thực, `SecurityFilterChain` và lớp authorization tiếp tục áp dụng chính sách. Controller nghiệp vụ có thể dùng principal/ID người dùng đã xác thực.

Cách liên kết này chỉ mô tả username/password. Các quyền trong DB cần ánh xạ rõ ràng: `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo tiền tố mặc định, còn `hasAuthority("invoice:read")` kiểm tra chính xác chuỗi `invoice:read`. Tài khoản có trong DB không mặc nhiên có mọi quyền; quyền trên đối tượng cụ thể (ví dụ “chỉ xem hóa đơn của chính mình”) còn cần kiểm tra ở tầng nghiệp vụ/method security.

**Ví dụ mã minh họa adapter** (đây là đoạn trong một ứng dụng đã định nghĩa `AccountRepository`, `Account` và quan hệ vai trò; không phải chương trình Java độc lập):

```java
@Service
class AccountDetailsService implements UserDetailsService {
    private final AccountRepository accounts;

    AccountDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(username));

        String[] authorities = account.roleNames().stream()
            .map(role -> "ROLE_" + role)
            .toArray(String[]::new);

        return User.withUsername(account.username())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .authorities(authorities)
            .build();
    }
}
```

Phần mã cần có các import Spring Security và bean `AccountRepository` do ứng dụng triển khai. Không dùng đoạn này như chức năng tự tạo user hoặc tự lưu mật khẩu: luồng đăng ký/đổi mật khẩu phải băm bằng thuật toán phù hợp trước khi ghi vào DB; quản lý transaction, ràng buộc username duy nhất, disable/lock và quyền là các nghiệp vụ riêng.

## 7. Các lựa chọn kho danh tính thay đổi luồng tích hợp như thế nào?

| Nguồn danh tính | Cách kết nối thường gặp | Điểm phân biệt |
| --- | --- | --- |
| **Bộ nhớ** | `InMemoryUserDetailsManager` | Hữu ích cho demo/test; dữ liệu không bền qua restart nếu không tự nạp lại. |
| **CSDL SQL** | `JdbcUserDetailsManager` theo schema được hỗ trợ, hoặc `UserDetailsService` tùy biến qua JPA/repository | Ứng dụng chịu trách nhiệm thiết kế/lưu hash, enabled và quyền; Boot/JPA không tự “bật login từ bảng”. |
| **LDAP/Active Directory** | Các thành phần xác thực LDAP/AD thích hợp của Spring Security | Quy trình có thể bind/tra cứu directory; không nhất thiết tải hash mật khẩu về ứng dụng để so. |
| **IdP ngoài qua OpenID Connect** | `spring-security-oauth2-client` + cấu hình client, `oauth2Login()` | IdP đăng nhập người dùng; ứng dụng nhận và xác minh thông tin qua giao thức, rồi ánh xạ danh tính/quyền cục bộ nếu cần. |
| **API nhận JWT access token** | `spring-security-oauth2-resource-server` + cấu hình issuer/JWK hoặc cách kiểm tra token phù hợp | API xác thực chữ ký, issuer, audience/thời hạn và chuyển claims/scopes thành authorities theo cấu hình; thông thường không so mật khẩu người dùng với bảng `users` trên mỗi request. |

**Không đánh đồng IdP với kho tài khoản cục bộ.** Một IdP có thể dùng LDAP/DB phía sau nhưng ứng dụng Spring Boot chỉ thấy giao thức đăng nhập/token. Với OIDC, thuộc tính ổn định như `issuer` + `sub` thường đáng tin hơn email làm khóa liên kết tài khoản vì email có thể thay đổi. Còn nếu ứng dụng chỉ là resource server nhận JWT, nó không tự động trở thành OAuth2 Login Client và không nên tự lấy mật khẩu người dùng.

Khi thay `InMemoryUserDetailsManager` trong ví dụ bằng adapter đọc DB, **phần còn lại của chính sách endpoint có thể giữ nguyên**. Đây chính là lợi ích của việc tách riêng “cách tìm/xác minh danh tính” khỏi “điều kiện được gọi API”. Tuy nhiên chuyển sang OIDC hay JWT có thể đòi thay cả phương thức xác thực HTTP, chứ không chỉ đổi repository.

## 8. Những lỗi thiết kế hay gặp

1. **Nhầm Spring Boot với hệ thống identity.** Starter và auto-configuration tạo hạ tầng; ứng dụng vẫn cần lựa chọn đúng kho danh tính, chính sách quyền, lifecycle tài khoản và cấu hình production.
2. **Cho rằng thêm `SecurityFilterChain` sẽ tự bỏ user mặc định.** Đây là hai nhánh auto-configuration riêng; phải chủ động kiểm tra bean `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager`.
3. **Lưu mật khẩu dạng plaintext hoặc dùng so sánh chuỗi trực tiếp.** Lưu hash bằng thuật toán thích hợp (ví dụ BCrypt/Argon2 phù hợp chính sách), dùng `PasswordEncoder.matches(...)`, quản lý nâng cấp hash và giới hạn thử mật khẩu.
4. **Tự viết kiểm tra đăng nhập trong controller.** Điều này dễ bỏ sót endpoint, sai mã lỗi hoặc bỏ qua policy; nên tích hợp xác thực vào bộ lọc/provider.
5. **Nhầm authentication với authorization.** “Đăng nhập thành công” không thay thế kiểm tra role, permission và quyền trên đối tượng kinh doanh.
6. **Lẫn `role` và `authority`.** `hasRole("ADMIN")` thường thêm tiền tố `ROLE_`, `hasAuthority("ADMIN")` thì không. Quy ước chuỗi quyền phải thống nhất ở identity adapter và policy.
7. **Tưởng mọi request luôn đọc DB.** Với session hoặc token, đường xác thực và kiểm tra ngữ cảnh có thể khác; dữ liệu quyền có thể bị cache/lưu trong token nên cần chiến lược cập nhật/thu hồi khi quyền thay đổi.
8. **Tắt CSRF, mở `permitAll()` rộng hoặc bỏ HTTPS để sửa lỗi 401/403.** Hãy xác định chính xác request, authentication mechanism và chính sách cần thiết; phân biệt lỗi chưa xác thực với thiếu quyền.
9. **Tự tin rằng JWT hợp lệ đồng nghĩa có quyền.** Cần xác minh cấu hình token (issuer, audience, chữ ký, hạn dùng), map scopes/roles đúng và kiểm tra quyền từng tài nguyên.
10. **Tin rằng kho danh tính là nơi lưu toàn bộ hồ sơ nghiệp vụ.** Thông tin xác thực, profile, hồ sơ nhân sự/khách hàng và quyền sử dụng hệ thống có thể do các hệ thống khác nhau quản lý; liên kết chúng bằng định danh ổn định và hợp đồng dữ liệu rõ ràng.

## 9. Tự kiểm tra hiểu biết

**Tình huống A.** Thêm `spring-boot-starter-data-jpa` và entity `User` vào dự án có Spring Security. Đăng nhập bằng user trong DB có tự hoạt động không?

**Đáp án:** Không. Entity/repository mới giải quyết lưu trữ; cần kết nối qua `UserDetailsService`, provider hoặc cơ chế xác thực phù hợp, đồng thời thiết kế encoder và authorities.

**Tình huống B.** Đã khai báo `SecurityFilterChain` tùy biến. Có thể kết luận Boot không còn tài khoản demo mặc định không?

**Đáp án:** Không. Phải kiểm tra các điều kiện auto-configure `UserDetailsService` và bean xác thực mà ứng dụng cung cấp.

**Tình huống C.** API chỉ nhận bearer JWT từ IdP. Nó có cần tải mật khẩu người dùng từ bảng `users` trên mỗi request không?

**Đáp án:** Thông thường không. Resource server xác minh token và tính quyền theo cấu hình; ứng dụng có thể tra thêm profile/quyền nghiệp vụ nếu thiết kế cần.

## 10. Nguồn đọc thêm

- [Spring Boot – Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): cấu hình mặc định và điều kiện thay thế bằng các bean của ứng dụng.
- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContext`, `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`.
- [Spring Security – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): mối liên hệ `UserDetailsService` và `PasswordEncoder`.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/): đăng nhập qua provider ngoài.

**Ghi nhớ:** Boot phụ trách khởi tạo và cấu hình ứng dụng; Security phụ trách thực thi xác thực/phân quyền; kho danh tính/IdP cung cấp thông tin hoặc bằng chứng. Khi thiết kế rõ ba ranh giới này, bạn có thể thay nguồn người dùng, đổi cơ chế đăng nhập hoặc mở rộng quyền truy cập mà không phải viết lại toàn bộ controller.