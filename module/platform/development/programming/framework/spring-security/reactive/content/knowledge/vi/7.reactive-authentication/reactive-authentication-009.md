# Xử lý tài khoản khóa, vô hiệu hóa, hết hạn và hết hạn mật khẩu

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **tài khoản bị khóa (locked)**, **bị vô hiệu hóa (disabled)**, **hết hạn tài khoản (account expired)** và **hết hạn thông tin xác thực/mật khẩu (credentials expired)** trong Spring Security reactive.
- Ánh xạ đúng bốn trạng thái vào các phương thức `UserDetails` và các cờ của `User.UserBuilder`, tránh đảo ngược nghĩa của chữ `Non`.
- Hiểu `ReactiveUserDetailsService`, `UserDetailsRepositoryReactiveAuthenticationManager`, `PasswordEncoder` và lỗi `AuthenticationException` phối hợp thế nào khi login.
- Phân biệt **lỗi xác thực (thường HTTP 401)** với **lỗi phân quyền (thường HTTP 403)**, xử lý phản hồi không làm lộ trạng thái tài khoản cho người lạ.
- Chạy ví dụ Java 17 + Spring WebFlux cho năm người dùng (hoạt động, khóa, vô hiệu hóa, hết hạn tài khoản, hết hạn mật khẩu), kiểm tra kết quả bằng HTTP và Reactor `StepVerifier`.
- Thiết kế quy trình khóa/mở khóa, vô hiệu hóa/kích hoạt, hết hạn/đổi mật khẩu, xử lý cache/session/token, kiểm tra thời gian, audit và kiểm thử trạng thái.

> **Phạm vi:** Spring Security **reactive/WebFlux**, đặc biệt là xác thực **username/password** dựa trên `UserDetails`. Các cờ này không mặc nhiên được mọi OAuth2 Resource Server/JWT, pre-auth hay custom `ReactiveAuthenticationManager` kiểm tra; với mô hình khác, phải kiểm tra policy và implementation thực tế. Không nhầm `HttpSecurity` của Servlet với `ServerHttpSecurity` của WebFlux.

## 1. Bốn trạng thái là bốn quy tắc khác nhau

Giả sử ứng dụng có tài khoản `alice`. Biết mật khẩu đúng **chưa đủ** để được đăng nhập: tài khoản còn phải đáp ứng policy về hoạt động, khóa và thời hạn.

| Trạng thái | Ý nghĩa nghiệp vụ | API của `UserDetails` khi **đang không hợp lệ** | Lỗi xác thực tương ứng |
|---|---|---|---|
| **Locked** (tài khoản khóa) | Tạm/chủ động chặn đăng nhập, ví dụ sau tín hiệu lạm dụng hoặc quyết định của quản trị viên. | `isAccountNonLocked() == false` | `LockedException` |
| **Disabled** (tài khoản bị vô hiệu hóa) | Tài khoản không được phép hoạt động, ví dụ chưa kích hoạt hoặc bị ngừng sử dụng. | `isEnabled() == false` | `DisabledException` |
| **Account expired** (tài khoản hết hạn) | Thời hạn sử dụng tài khoản đã kết thúc, dù mật khẩu có thể vẫn đúng. | `isAccountNonExpired() == false` | `AccountExpiredException` |
| **Credentials expired** (thông tin xác thực/mật khẩu hết hạn) | Mật khẩu/credential không còn được chấp nhận cho đăng nhập thông thường, có thể cần quy trình đổi mật khẩu. | `isCredentialsNonExpired() == false` | `CredentialsExpiredException` |

Các exception trên nằm trong package `org.springframework.security.authentication` và là các dạng `AuthenticationException`. Chúng biểu thị **lỗi authentication**, không phải thiếu quyền truy cập một tài nguyên sau khi đã xác thực.

**Khác biệt quan trọng:** Một tài khoản có thể đồng thời bị khóa **và** vô hiệu hóa. Bốn flag độc lập ở mô hình dữ liệu; nếu nhiều trạng thái sai, ngoại lệ nào xuất hiện trước tùy trình tự kiểm tra của authentication manager. Không dùng loại exception đầu tiên làm biểu diễn đầy đủ mọi nguyên nhân đang lưu trong database.

### 1.1. Những định nghĩa dễ nhầm

- **Khóa** thường có cơ chế mở lại (admin review hoặc `lockedUntil`) và có thể liên quan đến chống brute-force. Không đồng nhất với account disabled do chính sách doanh nghiệp.
- **Vô hiệu hóa** thường mang nghĩa tài khoản không được sử dụng cho đến khi có hành động kích hoạt lại; có thể là quản trị viên tắt hoặc bước xác minh chưa hoàn tất.
- **Hết hạn tài khoản** nói về vòng đời **tài khoản** (ví dụ hợp đồng hoặc đăng ký hết hiệu lực), không đồng nghĩa với tài khoản bị xóa.
- **Hết hạn mật khẩu** nói về **credential**. Sau khi đổi mật khẩu an toàn và cập nhật state, người dùng có thể hoạt động tiếp nếu account vẫn enabled, unlocked và non-expired.
- **Sai mật khẩu** không thuộc bốn trạng thái trên: nó thường tạo `BadCredentialsException`. Người dùng còn hợp lệ vẫn có thể nhập sai mật khẩu.
- **Không tìm thấy user** cũng khác disabled/locked; ứng dụng nên tránh tạo dấu hiệu công khai giúp dò user tồn tại.

## 2. Dấu boolean của UserDetails: đọc đúng chiều

Hợp đồng `org.springframework.security.core.userdetails.UserDetails` bao gồm bốn phương thức liên quan đến trạng thái:

~~~java
boolean isEnabled();                 // true = tài khoản được phép hoạt động
boolean isAccountNonLocked();        // true = KHÔNG bị khóa
boolean isAccountNonExpired();       // true = tài khoản CHƯA hết hạn
boolean isCredentialsNonExpired();   // true = mật khẩu/credential CHƯA hết hạn
~~~

Đoạn trên trích các chữ ký phương thức để giải thích, **không phải class Java độc lập**.

**Đọc chậm phần tên hàm:** ba phương thức có tiền tố `Non` trả `true` khi trạng thái **đang hợp lệ**. Chỉ `isEnabled()` là khẳng định trực tiếp trạng thái enabled. Đừng viết sai kiểu:

~~~java
// SAI nếu locked = true có nghĩa tài khoản đang bị khóa:
@Override
public boolean isAccountNonLocked() {
    return locked;
}

// ĐÚNG đối với mô hình boolean locked:
@Override
public boolean isAccountNonLocked() {
    return !locked;
}
~~~

Hai method minh họa trên thuộc **hai phiên bản class UserDetails khác nhau**, không đặt đồng thời trong một class; biến `locked` là field của domain. Sai một dấu `!` có thể dẫn đến cho người dùng bị khóa đăng nhập, đồng thời chặn người dùng hợp lệ.

### 2.1. User.UserBuilder có flag theo hướng ngược lại

Với implementation tiện dụng `org.springframework.security.core.userdetails.User`:

~~~java
UserDetails active = User.withUsername("active")
    .password("{noop}demo-pass")
    .roles("READER")
    .build();

UserDetails locked = User.withUsername("locked")
    .password("{noop}demo-pass")
    .roles("READER")
    .accountLocked(true)
    .build();

UserDetails disabled = User.withUsername("disabled")
    .password("{noop}demo-pass")
    .roles("READER")
    .disabled(true)
    .build();

UserDetails expiredAccount = User.withUsername("account-expired")
    .password("{noop}demo-pass")
    .roles("READER")
    .accountExpired(true)
    .build();

UserDetails expiredPassword = User.withUsername("password-expired")
    .password("{noop}demo-pass")
    .roles("READER")
    .credentialsExpired(true)
    .build();
~~~

Đây là **đoạn Java trong class** có import `User` và `UserDetails`; phần thực hành phía dưới cung cấp chương trình đầy đủ. Giá trị mặc định của các builder flag `disabled/accountLocked/accountExpired/credentialsExpired` là `false`, vì vậy user mặc định không bị chặn bởi bốn trạng thái. Những builder flag có nghĩa **tiêu cực**, ngược với một số getter `isAccountNon...` có nghĩa **tích cực**.

Dùng `{noop}` ở đây **chỉ để demo local**; production phải lưu mật khẩu đã hash bằng encoder phù hợp, không hardcode mật khẩu hay đưa plaintext vào source.

### 2.2. Không nhầm thời gian lưu trong database với boolean hiện tại

Nếu dữ liệu lưu `accountExpiresAt`, `passwordExpiresAt`, `lockedUntil`, `disabledAt` hoặc `adminLocked`, cần chuyển chúng thành các getter tại thời điểm xác thực. `UserDetails` mặc định không tự đọc timestamp trong database, không có cron job tự khóa, cũng không triển khai chính sách ngày hết hạn giúp bạn.

Ví dụ chính sách có thể là:

- `now >= accountExpiresAt` ⇒ `isAccountNonExpired() == false`.
- `now >= passwordExpiresAt` ⇒ `isCredentialsNonExpired() == false`.
- `adminLocked == true` hoặc `now < lockedUntil` ⇒ `isAccountNonLocked() == false`.
- `status != ACTIVE` ⇒ `isEnabled() == false`, nếu `status` được quy định là nguồn truth của trạng thái kích hoạt.

Các điều kiện trên là **quy tắc thiết kế mẫu**, phải được xác nhận theo chính sách nghiệp vụ, thời điểm biên và dữ liệu thực tế. Khi dùng thời gian, lưu `Instant`/UTC và inject `Clock` để có test xác định, tránh so sánh `LocalDateTime` không timezone hoặc dựa vào đồng hồ lệch giữa các node.

## 3. Chúng được kiểm tra ở đâu trong Reactive Authentication?

Flow điển hình với HTTP Basic username/password trong WebFlux:

~~~text
HTTP Authorization: Basic ...
  |
  v
AuthenticationWebFilter / ServerAuthenticationConverter
  |
  v
ReactiveAuthenticationManager
  |
  +--> ReactiveUserDetailsService.findByUsername(username)
  |       |
  |       +--> Mono<UserDetails> hoặc rỗng/lỗi
  |
  +--> kiểm tra trạng thái account (locked, disabled, account expired)
  +--> đối chiếu password bằng PasswordEncoder
  +--> kiểm tra credentials/password expired
  |
  +--> THÀNH CÔNG: Authentication được xác thực
  |       +--> Reactor SecurityContext / filter success handler
  |       +--> authorization / handler
  |
  +--> THẤT BẠI: Mono.error(AuthenticationException)
          +--> Authentication failure handling
          +--> thông thường HTTP 401 với HTTP Basic challenge
~~~

Hình trên áp dụng cho tuyến xác thực username/password với `UserDetailsRepositoryReactiveAuthenticationManager` mặc định; **mô hình khác hoặc manager tự viết có thể kiểm tra khác**. Một điểm nữa: kiểm tra account status **không xác minh mật khẩu**, và việc so sánh mật khẩu **không thay thế** kiểm tra trạng thái account.

### 3.1. Thành phần và trách nhiệm

**`ReactiveUserDetailsService`** chịu trách nhiệm tìm user và dựng `UserDetails`; method chủ chốt:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

Đây là chữ ký rút gọn của interface. Nếu không có user, service nên phát `Mono.empty()` theo hợp đồng phù hợp; kết quả authentication manager sẽ xử lý thất bại. Không tự kết luận rằng `Mono.empty()` đồng nghĩa tài khoản disabled.

**`UserDetailsRepositoryReactiveAuthenticationManager`** dùng `ReactiveUserDetailsService` để kiểm tra username/password. Nó nhận `Authentication` đầu vào và trả `Mono<Authentication>` đã xác thực hoặc lỗi. Với default checks của dòng Spring Security 6.x, manager kiểm tra account bị khóa, bị disabled và account expired ở giai đoạn trước xác thực mật khẩu; credential expired được kiểm tra sau bước mật khẩu. Những tình trạng này phát exception phù hợp khi có dữ liệu user. Thứ tự chi tiết có thể được tùy biến và có thể thay đổi theo phiên bản; khi một user vi phạm nhiều trạng thái, test behavior của manager đang dùng.

**`PasswordEncoder`** kiểm tra credential bằng `matches(rawPassword, encodedPassword)`; thường dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` hoặc encoder có chính sách hash mạnh tương ứng. Băm mật khẩu có chi phí CPU; cấu hình scheduler/throughput hợp lý và không tự gọi hàm blocking database trên Netty event loop.

**`SecurityWebFilterChain`** kiểm soát filter, authentication mechanism, exception handling và authorization cho URL. Khi authentication manager báo lỗi trạng thái, handler failure trả response theo cơ chế đã cấu hình. Đừng tự để ngoại lệ từ manager biến thành 500 bằng cách thiếu xử lý tại authentication boundary.

### 3.2. Phân biệt 401 với 403

| Tình huống | Bản chất | HTTP thường gặp với cấu hình Basic demo |
|---|---|---|
| Username không tồn tại | Authentication thất bại | `401 Unauthorized` |
| Sai password | Authentication thất bại | `401 Unauthorized` |
| Locked/disabled/account expired/password expired | Authentication thất bại do account status | `401 Unauthorized` |
| Đã authenticated nhưng thiếu role/scope cho URL | Authorization từ chối | `403 Forbidden` |
| Route `permitAll()` | Authorization không đòi đăng nhập | Có thể thành công; lỗi authentication/filter khác vẫn có thể chặn |

**`401` và `403` là cách xử lý HTTP, không phải mã cứng của từng exception.** Trong HTTP Basic, entry point có thể thêm `WWW-Authenticate`. Với form login có thể redirect; với API có custom failure handler có thể trả payload khác. Không khẳng định mỗi exception luôn có một HTTP code độc lập.

### 3.3. Cảnh báo account enumeration

Nếu endpoint login trả công khai `"alice bị khóa"`, `"bob chưa tồn tại"` hay `"charlie hết hạn mật khẩu"`, kẻ tấn công có thể suy đoán trạng thái tài khoản. Chính sách sản phẩm có thể hướng dẫn người dùng khôi phục tài khoản qua kênh đã xác minh, nhưng **đừng làm lộ trạng thái chi tiết cho bên chưa chứng minh quyền sở hữu**.

Một chiến lược thường dùng:

- Phản hồi bên ngoài cho login thất bại có thông điệp chung và mã HTTP phù hợp, ví dụ `401` và `"Không thể xác thực. Kiểm tra thông tin hoặc sử dụng quy trình khôi phục."`.
- Trong hệ thống audit nội bộ có kiểm soát, phân biệt `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException` để hỗ trợ vận hành.
- Giới hạn tốc độ/đếm thất bại chống đoán password nhưng không tạo cơ chế cho kẻ tấn công khóa hàng loạt account chỉ bằng cách gửi username của người khác.
- Không ghi password, bearer token, cookie session, credential Basic, hoặc toàn bộ `Authentication` vào log.

## 4. Ví dụ Java 17 chạy được: năm trạng thái người dùng trên WebFlux

Ví dụ dưới dùng **Java 17**, **Spring Boot 3.5.16** và Spring Security phiên bản do Boot quản lý, qua WebFlux và HTTP Basic. Chỉ có một API `GET /me` cần authenticated, một API public, và năm user in-memory có cùng mật khẩu demo nhưng trạng thái khác nhau.

Cấu hình dependency/Gradle dưới đây hoàn chỉnh cho bài thực hành local. Khi triển khai thật, hãy sử dụng bản phát hành bảo trì có bản vá mới nhất phù hợp với phiên bản Spring Boot/Spring Security của dự án; không xem bản demo và account hardcode là cấu hình production.

### 4.1. Cấu trúc dự án

~~~text
reactive-account-status-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ReactiveAccountStatusDemo.java
    └── test/java/example/AccountStatusAuthenticationTest.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-account-status-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản Spring Security, Reactor, JUnit và Reactor Test; không cần tự chọn ngẫu nhiên những version phụ thuộc. Dự án có thể chạy bằng Gradle phù hợp hoặc Gradle Wrapper được tạo cho dự án.

### 4.2. Ứng dụng đầy đủ

Tệp `src/main/java/example/ReactiveAccountStatusDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAccountStatusDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAccountStatusDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop}: chỉ để quan sát trạng thái trên máy local.
        String demoPassword = "{noop}demo-pass";

        UserDetails active = User.withUsername("active")
            .password(demoPassword)
            .roles("READER")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(demoPassword)
            .roles("READER")
            .accountLocked(true)
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(demoPassword)
            .roles("READER")
            .disabled(true)
            .build();

        UserDetails accountExpired = User.withUsername("account-expired")
            .password(demoPassword)
            .roles("READER")
            .accountExpired(true)
            .build();

        UserDetails passwordExpired = User.withUsername("password-expired")
            .password(demoPassword)
            .roles("READER")
            .credentialsExpired(true)
            .build();

        return new MapReactiveUserDetailsService(
            active, locked, disabled, accountExpired, passwordExpired);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }
    }
}
~~~

**Điểm đọc code quan trọng:**

- `MapReactiveUserDetailsService` trả `Mono<UserDetails>` theo username, đủ để demo default reactive authentication manager của Spring Security.
- User `active` giữ nguyên bốn flag hợp lệ.
- User `locked` có `isAccountNonLocked() == false` do `accountLocked(true)`.
- User `disabled` có `isEnabled() == false` do `disabled(true)`.
- User `account-expired` có `isAccountNonExpired() == false`.
- User `password-expired` có `isCredentialsNonExpired() == false`.
- `anyExchange().authenticated()` chỉ cho request đến `/me` đi tiếp sau khi authentication hợp lệ; `/public` không yêu cầu login.
- Controller lấy principal từ `ServerWebExchange.getPrincipal()`, không tin một header `X-User` do client tự khai báo.
- Không có logic tự catch `LockedException` trong controller; authentication filter/entry point xử lý trước khi controller protected chạy.

### 4.3. Chạy và kiểm tra HTTP

Trong thư mục `reactive-account-status-demo`, với JDK 17+ và Gradle đã cài:

~~~bash
gradle bootRun
~~~

Nếu đã có Gradle Wrapper thì dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Từ terminal khác:

~~~bash
# A. Public route không gửi credentials
curl -i http://localhost:8080/public

# B. Account hoạt động, mật khẩu đúng
curl -i -u active:demo-pass http://localhost:8080/me

# C. Account bị khóa
curl -i -u locked:demo-pass http://localhost:8080/me

# D. Account bị vô hiệu hóa
curl -i -u disabled:demo-pass http://localhost:8080/me

# E. Hết hạn account
curl -i -u account-expired:demo-pass http://localhost:8080/me

# F. Hết hạn credential/password
curl -i -u password-expired:demo-pass http://localhost:8080/me

# G. User hợp lệ nhưng sai password
curl -i -u active:wrong-password http://localhost:8080/me

# H. Username không tồn tại
curl -i -u unknown:demo-pass http://localhost:8080/me
~~~

Nếu dùng PowerShell mà `curl` là alias khác, hãy dùng `curl.exe`. HTTP status kỳ vọng của **demo**:

| Request | HTTP status | Giải thích |
|---|---|---|
| `GET /public`, không credential | 200 | Route được permitAll. |
| `GET /me`, Basic `active:demo-pass` | 200 | Xác thực thành công; body có `{"username":"active"}`. |
| `GET /me`, Basic `locked:demo-pass` | 401 | Account bị khóa, authentication thất bại. |
| `GET /me`, Basic `disabled:demo-pass` | 401 | Account disabled, authentication thất bại. |
| `GET /me`, Basic `account-expired:demo-pass` | 401 | Account hết hạn, authentication thất bại. |
| `GET /me`, Basic `password-expired:demo-pass` | 401 | Credential hết hạn, authentication thất bại. |
| `GET /me`, Basic `active:wrong-password` | 401 | Mật khẩu không khớp. |
| `GET /me`, Basic `unknown:demo-pass` | 401 | Không tìm thấy user. |

Những status trên là kỳ vọng với filter, entry point và username/password manager của cấu hình demo. HTTP response header (đặc biệt `WWW-Authenticate`) có thể phụ thuộc version và cấu hình; không nên dựa vào message lỗi thô để phân biệt trạng thái tài khoản từ client. Đây là **HTTP output**, không phải stdout cố định của chương trình Java.

**Không dùng demo ngoài local:** `{noop}` lưu plaintext, password hardcode, và HTTP Basic chỉ an toàn khi đi qua HTTPS/TLS. Trong production, dùng encoder mạnh, quản lý secret, TLS, session/token policy phù hợp và rate limiting.

## 5. Kiểm thử nội bộ chính xác exception bằng StepVerifier

Trên HTTP, các lỗi thường cùng trả 401 để không lộ lý do chi tiết. Ở **tầng unit test của authentication manager**, bạn vẫn cần xác minh rằng chính các flag dẫn đến exception đúng. Không nên bắt đầu bằng việc “sửa” Basic failure handler để trả công khai bốn loại lỗi cho client.

Tệp `src/test/java/example/AccountStatusAuthenticationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

import reactor.test.StepVerifier;

class AccountStatusAuthenticationTest {

    @Test
    void lockedAccountFails() {
        assertFailure(
            user("locked").accountLocked(true).build(),
            LockedException.class);
    }

    @Test
    void disabledAccountFails() {
        assertFailure(
            user("disabled").disabled(true).build(),
            DisabledException.class);
    }

    @Test
    void accountExpirationFails() {
        assertFailure(
            user("account-expired").accountExpired(true).build(),
            AccountExpiredException.class);
    }

    @Test
    void passwordExpirationFails() {
        assertFailure(
            user("password-expired").credentialsExpired(true).build(),
            CredentialsExpiredException.class);
    }

    @Test
    void badPasswordFails() {
        var details = user("active").build();
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            "active", "wrong-password");

        StepVerifier.create(manager.authenticate(attempt))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void validAccountSucceeds() {
        var details = user("active").build();
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            "active", "demo-pass");

        StepVerifier.create(manager.authenticate(attempt))
            .expectNextMatches(authentication ->
                authentication.isAuthenticated()
                    && authentication.getName().equals("active"))
            .verifyComplete();
    }

    private static User.UserBuilder user(String username) {
        return User.withUsername(username)
            .password("{noop}demo-pass")
            .roles("READER");
    }

    private static void assertFailure(
        UserDetails details, Class<? extends Throwable> errorType) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            details.getUsername(), "demo-pass");

        StepVerifier.create(manager.authenticate(attempt))
            .expectError(errorType)
            .verify();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test` với wrapper. Kỳ vọng sáu test pass và không có exception chưa được bắt. Đoạn test cố tình kiểm tra **exception ở tầng manager**, trong khi HTTP client chỉ được thấy response an toàn. Nếu xây custom `ReactiveAuthenticationManager`, hãy bổ sung test riêng vì các check mặc định có thể không được custom manager triển khai.

### 5.1. Vì sao nên test cả HTTP lẫn manager?

- **Manager test** chứng minh trạng thái UserDetails được đánh giá đúng, loại exception đúng, case password sai được phân biệt trong nội bộ.
- **HTTP test** chứng minh security filters chặn request trước handler, status bên ngoài phù hợp và không tiết lộ trạng thái nhạy cảm.
- **Integration test với database thật** chứng minh việc chuyển timestamp/flag thành UserDetails và cache/invalidation hoạt động đúng.
- Không thể kết luận behavior của bộ lọc WebFlux chỉ bằng việc test getter `isAccountNonLocked()` mà chưa chạy authentication pipeline.

## 6. Đưa trạng thái từ database lên UserDetails trong ứng dụng reactive

Ví dụ thực tế có thể lưu record:

| Cột mẫu | Kiểu khái niệm | Ý nghĩa |
|---|---|---|
| `username` | String unique/canonical | Tên người dùng xác thực. |
| `password_hash` | String | Hash đã mã hóa kèm ID encoder phù hợp. |
| `status` | `ACTIVE / DISABLED / PENDING_ACTIVATION` | Trạng thái kích hoạt. |
| `admin_locked` | boolean | Khóa thủ công/điều tra. |
| `locked_until` | `Instant` nullable | Thời điểm khóa tạm thời kết thúc. |
| `account_expires_at` | `Instant` nullable | Thời điểm hết hạn account. |
| `password_expires_at` | `Instant` nullable | Thời điểm hết hạn credential. |
| `failed_attempts` | integer | Bộ đếm cho chính sách chống đoán password. |
| `version` | integer | Hỗ trợ optimistic locking khi cập nhật đồng thời. |

Một ánh xạ sang `UserDetails` có thể được viết bằng logic như sau; đây là **đoạn minh họa trong service**, với `record` là entity đã được repository trả về, `clock` là `java.time.Clock` và `Instant` là `java.time.Instant`:

~~~java
Instant now = clock.instant();

boolean enabled = record.status() == Status.ACTIVE;

boolean accountNonLocked =
    !record.adminLocked()
    && (record.lockedUntil() == null
        || !now.isBefore(record.lockedUntil()));

boolean accountNonExpired =
    record.accountExpiresAt() == null
    || now.isBefore(record.accountExpiresAt());

boolean credentialsNonExpired =
    record.passwordExpiresAt() == null
    || now.isBefore(record.passwordExpiresAt());

UserDetails details = User.withUsername(record.username())
    .password(record.passwordHash()) // Hash từ kho dữ liệu đáng tin.
    .authorities(record.authorities())
    .disabled(!enabled)
    .accountLocked(!accountNonLocked)
    .accountExpired(!accountNonExpired)
    .credentialsExpired(!credentialsNonExpired)
    .build();
~~~

Không coi đoạn này là class độc lập: `Status`, `record`, `clock` và storage backend tùy ứng dụng. Logic ví dụ dùng cận **[start, expiresAt)**: tại đúng thời điểm `expiresAt`, tài khoản/credential đã hết hạn. `lockedUntil` chỉ khóa khi `now < lockedUntil`; nếu có `adminLocked` thì vẫn bị khóa dù time lock đã kết thúc. Bạn phải xác nhận policy thật trước khi áp dụng.

### 6.1. ReactiveUserDetailsService với kho dữ liệu không blocking

Với Spring Data R2DBC, service nên trả `Mono<UserDetails>` bằng cách mapping publisher từ repository reactive:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return accountRepository.findByUsername(username)
        .map(this::toUserDetails);
}
~~~

Đây là đoạn minh họa **bên trong class implement ReactiveUserDetailsService** với `accountRepository` và `toUserDetails` đã định nghĩa. Không dùng JDBC blocking bên trong `Mono.just(jdbcCall())` vì lệnh blocking vẫn được thực hiện ngay khi tạo publisher.

Với kho dữ liệu bắt buộc blocking, hãy tách tác vụ đúng scheduler theo quy tắc WebFlux, ví dụ `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và thiết lập timeout/resource limits. Chuyển scheduler không khiến blocking I/O tự trở thành non-blocking thực sự.

### 6.2. Chuyển đổi trạng thái phải nhất quán

Nếu đổi mật khẩu thành công, cập nhật hash và `passwordExpiresAt`/flag sao cho getter `isCredentialsNonExpired()` sau đó trả `true`. Nếu chỉ đổi hash nhưng quên reset expiry, login vẫn thất bại.

Nếu admin kích hoạt tài khoản, cập nhật `status=ACTIVE` nhưng **đừng vô tình mở khóa** một account vẫn đang bị điều tra. Nếu hết thời hạn khóa tạm, getter có thể trả `true` nhưng cập nhật bộ đếm thất bại và log theo policy để tránh lock lại ngay lập tức.

Khi hai request đăng nhập sai đến cùng lúc, thao tác tăng `failed_attempts`, đặt `lockedUntil` và kiểm tra version nên được thực hiện **atomic** trong database/Redis bằng transaction/optimistic locking thích hợp. Không để nhiều request ghi đè bộ đếm khiến khóa không kích hoạt hoặc bị nới lỏng ngoài ý muốn.

## 7. Chính sách khóa/mở khóa tài khoản

### 7.1. Lý do khóa

- Khóa tạm khi có đủ bằng chứng về nhiều lần đoán password sau khi xem xét giới hạn truy cập.
- Khóa thủ công khi có cảnh báo lộ credential, gian lận hoặc quyết định của quản trị viên.
- Khóa do chính sách doanh nghiệp như rủi ro đăng nhập bất thường, có thể kèm bước xác minh mạnh hơn.

Khóa tài khoản không nên là biện pháp duy nhất chống brute-force: kẻ tấn công có thể **cố tình khóa hàng loạt user** chỉ với username nếu hệ thống tự động lock quá dễ. Kết hợp rate limiting theo IP/thiết bị/tài khoản, delay phù hợp, MFA, quan sát hành vi bất thường và đường hỗ trợ khôi phục đáng tin cậy.

### 7.2. Mở khóa

Một chính sách tốt nêu rõ:

1. Ai được mở khóa (admin, người dùng qua proof-of-possession, hay hệ thống theo thời hạn)?
2. Điều kiện gì chứng minh đã đủ an toàn?
3. Có yêu cầu reset mật khẩu hoặc thu hồi session/token cũ hay không?
4. Audit cần lưu gì (actor, thời gian, lý do, correlation ID) mà không log secret?
5. `lockedUntil` và `adminLocked` có tương tác như thế nào?

Không đặt `isAccountNonLocked() == true` cho mọi user chỉ để vượt qua lỗi login. Cần cập nhật đúng record và bảo đảm chính sách rủi ro được đáp ứng.

## 8. Vô hiệu hóa và hết hạn tài khoản

**Disabled** và **expired** đều chặn xác thực trong manager mặc định nhưng khác tác động nghiệp vụ:

- `disabled`: tắt chức năng sử dụng tài khoản dù chưa đến ngày hết hạn; có thể dùng khi người dùng chưa xác minh email hoặc bị ban.
- `account expired`: thời hạn sử dụng đã kết thúc, ví dụ hết kỳ cấp quyền truy cập của hợp đồng; có thể gia hạn bằng thao tác quản trị.
- Một user có `isEnabled()==true` nhưng `isAccountNonExpired()==false` vẫn không được login.
- Một user có `isEnabled()==false` nhưng hạn account còn xa vẫn bị từ chối.

Đừng xóa user khỏi database để mô phỏng disabled nếu hệ thống cần audit, quyền sở hữu dữ liệu hoặc quy trình khôi phục. Ngược lại, đừng dùng disabled như một cách vĩnh viễn giữ tài khoản khi chính sách yêu cầu xóa dữ liệu riêng tư. Cần ràng buộc với quy định retention và xử lý xóa thật.

Khi hệ thống dùng OAuth2/SSO bên ngoài, local user `isEnabled` có thể không được đánh giá bởi authentication provider của IdP. Nếu cần chặn người dùng bị disabled tại ứng dụng, áp dụng policy ở điểm kiểm tra identity/authority hoặc authorization thích hợp và kiểm thử mọi cơ chế đăng nhập, không chỉ Basic.

## 9. Hết hạn mật khẩu: luồng phục hồi cần thiết

`CredentialsExpiredException` không tự hiển thị màn hình đổi mật khẩu hoặc cấp quyền tạm. Nếu authentication thông thường từ chối người dùng vì password expired, bạn cần thiết kế **luồng đổi mật khẩu độc lập và có kiểm chứng**.

Một quy trình an toàn điển hình:

1. Khi cần đổi mật khẩu, hiển thị hướng dẫn chung hoặc đưa người dùng đến luồng xác minh danh tính thích hợp (session đặc biệt, email verification link, MFA hoặc bước xác thực theo chính sách).
2. Kiểm tra token reset/đổi mật khẩu một lần, có hạn, gắn đúng tài khoản, lưu an toàn; tránh endpoint đổi password chỉ tin username tự khai.
3. Kiểm tra mật khẩu mới theo chính sách, so sánh với lịch sử nếu cần, hash bằng `PasswordEncoder` phù hợp; không lưu/ghi log raw password.
4. Trong một đơn vị cập nhật nhất quán: lưu hash mới, cập nhật `passwordChangedAt/passwordExpiresAt`, gỡ trạng thái credentials-expired, có thể thu hồi session/refresh token cũ theo threat model.
5. Thông báo cho user qua kênh đã xác minh; ghi audit và rate-limit endpoint reset.
6. Yêu cầu đăng nhập lại hoặc cấp phiên mới qua luồng kiểm chứng đầy đủ theo policy; không cấp `ROLE_ADMIN` hay toàn bộ API chỉ vì user đang trong luồng “đổi password”.

Phân biệt **password hết hạn** với **password sai**. Với account đã hết hạn password, manager có thể chặn login dù password được nhập đúng; trả lý do cụ thể cho người không xác minh được danh tính là rủi ro account enumeration. Sử dụng luồng khôi phục bảo vệ danh tính và giới hạn thông tin trả về.

Nếu dùng passkey/OIDC/passwordless, `isCredentialsNonExpired` của local `UserDetails` có thể không điều khiển cơ chế xác thực thực tế; cần kiểm soát trạng thái credential trong hệ thống tương ứng.

## 10. Trạng thái thay đổi trong khi người dùng đã đăng nhập

**Bốn flag thường được kiểm tra trong một lần authentication theo username/password.** Không mặc định rằng khi admin chuyển `enabled=false` hoặc `locked=true`, mọi session/JWT đã phát sẽ lập tức mất hiệu lực.

Ví dụ:

- Website đã lưu `SecurityContext` vào WebSession: request sau có thể khôi phục Authentication cũ nếu không revalidate user. Bật disabled trong database **không chắc** xóa ngay session.
- Resource server xác thực JWT chữ ký/expiry/scopes: nếu chỉ kiểm tra token mà không truy vấn local account status, token hợp lệ có thể tiếp tục được chấp nhận cho đến khi hết hạn/thu hồi theo thiết kế.
- Custom `ReactiveAuthenticationManager` dùng LDAP/OIDC có thể có semantics account trạng thái khác với `UserDetailsRepositoryReactiveAuthenticationManager`.

Nếu yêu cầu khóa/vô hiệu hóa **có tác dụng ngay**, cần thiết kế:

- Thu hồi session WebFlux/Spring Session phù hợp, làm hết hiệu lực refresh token hoặc token phiên.
- Token ngắn hạn hoặc cơ chế token introspection/revocation/version check.
- Kiểm tra trạng thái user trong authorization nhạy cảm khi cần, với cache có TTL/invalidation hợp lý.
- Cập nhật nhiều instance và kiểm thử concurrent requests; không giả định cache sẽ đồng bộ tức thì nếu chưa cấu hình.

Chi phí truy vấn trạng thái trên mỗi request cần cân đối với độ nhạy tài nguyên và thời hạn hiệu lực được phép. Đừng chỉ đổi boolean trong database rồi tuyên bố “đã chặn mọi truy cập”.

## 11. Lưu ý về PasswordEncoder và các lỗi riêng

Một ví dụ password hash có thể có tiền tố `{bcrypt}...` khi dùng DelegatingPasswordEncoder. `{noop}demo-pass` chỉ cho demo; nếu lưu plaintext trong production, việc có các account status flags không bù được rủi ro lộ password.

Các tình huống cần phân biệt:

| Hiện tượng | Khả năng nguyên nhân | Cách điều tra |
|---|---|---|
| Người dùng hoạt động nhưng luôn 401 | Sai password, encoder không khớp hash hoặc username lookup sai. | Kiểm tra encoder ID, migration hash, canonical username và audit nội bộ. |
| User bị locked dù hết `lockedUntil` | Mapping `isAccountNonLocked` sai; `adminLocked` còn true; cache stale. | Test với injected Clock, inspect record và cache. |
| User đã đổi mật khẩu nhưng vẫn “expired” | Chưa cập nhật trạng thái hoặc timestamp hết hạn, cache user details cũ. | Review transaction đổi password và invalidation. |
| User disabled nhưng token cũ vẫn truy cập | SecurityContext/session/JWT chưa revalidate/revoke. | Kiểm tra token/session revocation và authorization. |
| Lỗi credential expired hiển thị thành 500 | AuthenticationException bị chuyển sai trong custom filter/handler. | Test failure handler và entry point của WebFlux. |
| Có nhiều status sai, nhận exception “không mong đợi” | Các check có thứ tự ưu tiên; manager tùy biến. | Test trực tiếp manager với từng flag độc lập trước. |

Đừng đồng nhất `CredentialsExpiredException` với `BadCredentialsException` trong audit nội bộ, nhưng phản hồi công khai cần hạn chế lộ thông tin. Cũng đừng vô hiệu hóa kiểm tra account status để “fix” user login: đó là policy an ninh, không phải validation gây phiền.

## 12. Review bảo mật và kiểm thử cạnh tranh

### Checklist cấu hình

1. **Đúng stack:** `ReactiveUserDetailsService` + `ReactiveAuthenticationManager` + `ServerHttpSecurity`, không lấy ví dụ Servlet gắn sang reactive.
2. **Nguồn dữ liệu:** status, lock time, password expiry có nguồn truth thống nhất; database lookup non-blocking hoặc được đưa đúng scheduler.
3. **Boolean mapping:** test trường hợp `true/false` của từng getter, nhất là các tên `is...Non...`.
4. **Authentication:** test password đúng/sai, user không tồn tại và từng account state; không bỏ bước so sánh password.
5. **HTTP behavior:** API login trả response thích hợp, tránh lộ username/status; phân biệt 401 với 403.
6. **Rate limiting:** chống brute-force và lockout-as-DoS; có chính sách mở khóa có kiểm chứng.
7. **Time boundary:** test `now < expiresAt`, `now == expiresAt`, `now > expiresAt`, timezone/clock skew.
8. **Concurrency:** cập nhật `failedAttempts` và `lockedUntil` atomic; không để race khiến mất lần thất bại.
9. **Phiên/token:** test sau khi disabled/locked user có session/JWT đang tồn tại; nếu yêu cầu chặn ngay phải revoke/revalidate.
10. **Logging:** log sự kiện và actor/correlation ID, không ghi plaintext password hoặc token; kiểm soát quyền đọc audit.
11. **Recovery:** reset password/enable/unlock qua luồng xác minh, token reset một lần và expiry rõ ràng.
12. **Test mọi cơ chế:** HTTP Basic, form login, JWT/OIDC và custom manager có thể đi qua các đường khác nhau; không suy luận từ một test pass.

### Tình huống tự đánh giá

**1.** User có `isEnabled()=true` và `isAccountNonLocked()=false`. Password nhập đúng. Có được login không?

**Đáp án:** Không, authentication manager username/password có check trạng thái sẽ từ chối vì khóa account. Exception thường là `LockedException`.

**2.** Với builder `.credentialsExpired(true)`, `isCredentialsNonExpired()` trả giá trị gì?

**Đáp án:** `false`. Cờ builder thể hiện “đã hết hạn”, trong khi getter thể hiện “chưa hết hạn”.

**3.** Password đã hết hạn nhưng user đã xác thực từ một WebSession còn sống trước đó. Việc đặt flag expired có tự hủy session đang mở không?

**Đáp án:** Không nhất thiết. Cần chính sách thu hồi session/revalidate theo yêu cầu bảo mật.

**4.** Vì sao không trả chi tiết `LockedException`, `DisabledException` cho tất cả client chưa xác minh?

**Đáp án:** Dữ liệu này có thể giúp dò trạng thái và sự tồn tại của tài khoản. Có thể ghi lý do cụ thể trong audit được bảo vệ, còn response công khai dùng thông điệp phù hợp chung và quy trình recovery được xác minh.

**5.** Một `ReactiveAuthenticationManager` xử lý JWT có tự gọi `UserDetails.isCredentialsNonExpired()` không?

**Đáp án:** Không thể giả định. JWT resource server có thể xác thực signature/expiry/scope mà không dùng `UserDetails` local; nếu cần local status, phải thiết kế rõ.

**6.** Tài khoản vừa hết hạn, đồng thời bị khóa và disabled. Vì sao exception đầu tiên có thể là locked?

**Đáp án:** Manager username/password mặc định kiểm tra các điều kiện theo thứ tự; nhiều trạng thái bất hợp lệ có thể cùng tồn tại. Trình tự kiểm tra chỉ quyết định exception được phát ra trước, không thay đổi dữ liệu thực tế.

**7.** Tài khoản bị locked có nên được mở khóa chỉ bằng cách nhập đúng password nhiều lần không?

**Đáp án:** Không. Mở khóa phải tuân thủ policy có xác minh, có thể đòi MFA/admin review/thời hạn khóa. Việc nhập đúng password không thay thế quyết định quản trị hoặc policy chống lạm dụng.

## Tài liệu chính thức

- Spring Security — `UserDetails`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html
- Spring Security — `User.UserBuilder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security — `ReactiveUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — `AbstractUserDetailsReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security — các exception `LockedException` / `DisabledException` / `AccountExpiredException` / `CredentialsExpiredException`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/package-summary.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/basic.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
