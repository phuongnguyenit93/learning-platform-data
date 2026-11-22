# Authentication.getDetails và dữ liệu bổ sung của yêu cầu

## Mục tiêu và phạm vi

Trong Spring Security, sau khi biết **ai đang được xác thực** từ `Authentication.getPrincipal()`, đôi khi ta cần thêm thông tin về **lần xác thực ấy diễn ra trong bối cảnh nào**: địa chỉ kết nối gửi yêu cầu đăng nhập, session đã tồn tại khi xác thực, dấu thời gian phục vụ kiểm toán hoặc thông tin có tính chất phụ trợ. `Authentication.getDetails()` là điểm mở rộng dành cho dữ liệu đó.

Sau bài học, bạn có thể:

1. Phân biệt `principal`, `credentials`, `authorities` và `details` của `Authentication`.
2. Hiểu kiểu trả về `Object`, khả năng `null` và lý do phải kiểm tra kiểu thực tế trước khi sử dụng.
3. Đọc `WebAuthenticationDetails` trong Servlet, hiểu ý nghĩa và giới hạn của `remoteAddress` và `sessionId`.
4. Nắm được cách filter tạo details, `AuthenticationManager` xử lý authentication request và provider có thể giữ/chuyển tiếp details sang kết quả.
5. Tạo thêm thông tin bằng `AuthenticationDetailsSource` khi thật sự có yêu cầu nghiệp vụ, cùng giới hạn bảo mật và vòng đời.
6. Xử lý sự khác biệt với Spring WebFlux/reactive, nơi không thể mặc định mọi `Authentication` có `WebAuthenticationDetails`.

Bài sử dụng Spring Security 6.x với Spring Boot 3.x và Java 17+. Ví dụ tập trung vào authentication HTTP; đây không phải tài liệu thiết kế toàn bộ cơ chế đăng nhập, MFA, authorization hay audit logging.

## 1. `Authentication.getDetails()` thực sự chứa gì?

Giao diện `org.springframework.security.core.Authentication` đại diện cho thông tin xác thực đầu vào hoặc danh tính đã xác thực do `AuthenticationManager` trả về. Các thuộc tính chính khác nhau về ý nghĩa:

| API | Câu hỏi trả lời | Ví dụ | Ghi chú |
| --- | --- | --- | --- |
| `getPrincipal()` | Ai là người/ứng dụng đang được nhận diện? | username, `UserDetails`, `Jwt` | Có thể là kiểu khác nhau theo cơ chế |
| `getCredentials()` | Bằng chứng nào được gửi để chứng minh danh tính? | password, bearer token | Có thể được xóa sau khi xác thực; tuyệt đối không log |
| `getAuthorities()` | Những quyền nào được gán cho danh tính đã xác thực? | `ROLE_USER`, `SCOPE_read` | Dùng cho authorization |
| `getDetails()` | Thông tin phụ trợ nào gắn với **lần authentication**? | `WebAuthenticationDetails`, object tùy chỉnh | Không mặc nhiên là thuộc tính hồ sơ người dùng |
| `isAuthenticated()` | Token đã được đánh dấu xác thực chưa? | `true`/`false` | Không tự dùng cờ này để kết luận “người dùng thực” đã đăng nhập: anonymous token cũng có thể là `true` |

Khai báo API có dạng:

~~~java
Object details = authentication.getDetails();
~~~

Kiểu trả về là **`Object`**, có thể là **`null`**. Spring Security không cam kết một schema duy nhất cho mọi loại `Authentication`: form login, HTTP Basic, JWT bearer token, OAuth2 login, pre-authentication và custom provider có thể dùng các giá trị details khác nhau, hoặc không dùng.

**Không nhầm lẫn với `UserDetails`.** `UserDetails` là hợp đồng đại diện thông tin của account (username, password đã mã hóa, authorities và trạng thái account) trong cơ chế xác thực dùng `UserDetailsService`. `Authentication.getDetails()` là nơi gắn metadata phụ trợ của **authentication attempt hoặc authentication result**. Thông tin bền vững của account (ví dụ mã tenant đã được server xác minh) nên được mô hình hóa và kiểm soát ở principal/domain model thích hợp, thay vì vô tình phụ thuộc vào một object request-specific.

Ngoài ra, `getDetails()` **không phải** `HttpServletRequest.getAttribute(...)`, `ServerWebExchange.getAttributes()`, MDC/trace context hay thuộc tính session tùy ý. Các nơi lưu trữ đó có vòng đời khác nhau. Chỉ đưa một tập dữ liệu tối thiểu, có chủ đích vào `Authentication`.

## 2. Tại sao Servlet thường gặp `WebAuthenticationDetails`?

Trong một số luồng xác thực HTTP của Spring Security Servlet (đặc biệt form login tiêu chuẩn), object trả về bởi `getDetails()` có thể là:

~~~java
org.springframework.security.web.authentication.WebAuthenticationDetails
~~~

Lớp này là snapshot nhỏ của request tại **thời điểm xây dựng details**, gồm:

- `getRemoteAddress()`: địa chỉ kết nối mà `HttpServletRequest` nhìn thấy. Nếu có reverse proxy, đó có thể là địa chỉ proxy thay vì IP cuối của client; phụ thuộc cấu hình xử lý forwarded headers và trust boundary.
- `getSessionId()`: ID của `HttpSession` **nếu session đã tồn tại** tại thời điểm ghi nhận details. Lớp này **không tự tạo session** chỉ để lấy ID; kết quả có thể `null`.

Ví dụ đọc an toàn:

~~~java
Object raw = authentication.getDetails();
if (raw instanceof WebAuthenticationDetails details) {
    String remoteAddress = details.getRemoteAddress();
    String sessionId = details.getSessionId(); // Có thể null.
    boolean hadSessionWhenCaptured = sessionId != null;
    // Chỉ sử dụng ở nơi có quyền, không trả sessionId cho client.
}
~~~

Đây là **đoạn minh họa bên trong phương thức đã nhận `Authentication authentication`**. Import `org.springframework.security.web.authentication.WebAuthenticationDetails`. Dùng `instanceof` thay cho ép kiểu thẳng; các implementation khác không có nghĩa phải tuân theo kiểu Servlet này.

### 2.1. Snapshot của lúc xác thực, không phải request hiện tại

Giả sử browser đăng nhập bằng form lúc 09:00. Filter tạo `WebAuthenticationDetails` cho POST `/login`. Server lưu `SecurityContext` vào session; lúc 09:20 user gửi GET `/me`. Nếu `Authentication` được khôi phục từ session, `getDetails()` có thể **vẫn mang dữ liệu chụp từ POST /login lúc 09:00**. Nó không tự cập nhật mỗi lần có HTTP request mới.

Vì vậy, nếu muốn địa chỉ IP/correlation ID của **request hiện tại**, hãy đọc metadata từ request hiện tại thông qua giao diện web phù hợp hoặc bộ lọc/tracing của request, không hiểu nhầm `authentication.getDetails()` là hệ thống theo dõi từng request.

Một session có thể được tạo **sau** khi details đã được chụp; khi đó `WebAuthenticationDetails.getSessionId()` vẫn có thể `null` dù browser có session về sau. Các cơ chế session fixation protection có thể thay session ID tại thời điểm đăng nhập, nên không nên dùng session ID cũ trong details để xác minh session hiện tại.

### 2.2. Địa chỉ remote không phải chứng cứ xác thực

`getRemoteAddress()` mô tả peer theo quan sát của server. NAT, VPN, mobile network và reverse proxy đều ảnh hưởng giá trị này. Header `X-Forwarded-For` hoặc `Forwarded` có thể bị client giả mạo nếu proxy boundary không được cấu hình đúng. Không coi một IP, User-Agent hay giá trị header do client khai báo là bằng chứng đủ để đăng nhập hoặc gán quyền. Nếu cần risk scoring dựa trên địa chỉ client, phải có trusted proxy configuration, xác minh nguồn và đánh giá nhiều tín hiệu.

## 3. Details được tạo, truyền và lưu như thế nào?

Luồng form login Servlet phổ biến:

~~~text
POST /login (username, password)
  -> UsernamePasswordAuthenticationFilter.attemptAuthentication(...)
     -> tạo UsernamePasswordAuthenticationToken chưa xác thực
     -> AuthenticationDetailsSource.buildDetails(request)
     -> authRequest.setDetails(details)
  -> AuthenticationManager.authenticate(authRequest)
     -> AuthenticationProvider kiểm tra credentials
     -> trả Authentication đã xác thực
        (provider có thể chuyển details từ request sang kết quả)
  -> SecurityContext nhận Authentication thành công
     -> có thể được lưu bởi SecurityContextRepository
  -> handler/controller đọc authentication.getDetails()
~~~

`UsernamePasswordAuthenticationFilter`, lớp con của `AbstractAuthenticationProcessingFilter`, gọi `setDetails(request, authRequest)` để gắn details. Filter dùng `AuthenticationDetailsSource<HttpServletRequest, ?>` để tạo object. Mặc định của form login là `WebAuthenticationDetailsSource`.

Trong cơ chế username/password tiêu chuẩn dựa trên `AbstractUserDetailsAuthenticationProvider`/`DaoAuthenticationProvider`, details từ authentication request được chuyển sang token thành công. **Đây là hành vi của những implementation cụ thể**, không phải điều mọi `AuthenticationProvider` hoặc token custom bắt buộc làm. Nếu tự xây dựng provider tạo một token mới, bạn phải quyết định có cần sao chép metadata đã kiểm tra hay không.

Lưu ý hai phương thức khác nhau:

- `Authentication#getDetails()`: **đọc** thông tin phụ trợ, là phần giao diện chung.
- `AbstractAuthenticationToken#setDetails(Object)`: **gắn** details trên token kiểu `AbstractAuthenticationToken`; không có phương thức `setDetails` chung ở mọi implementation của `Authentication`.

Ví dụ tùy biến provider, **chỉ sau khi credentials được kiểm chứng thực sự**:

~~~java
// Mã minh họa bên trong AuthenticationProvider thành công.
UsernamePasswordAuthenticationToken success =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedPrincipal, null, verifiedAuthorities);
success.setDetails(incomingAuthentication.getDetails());
return success;
~~~

Đoạn này không phải provider hoàn chỉnh; `verifiedPrincipal` và `verifiedAuthorities` phải đến từ quá trình xác thực hợp lệ, không sao chép từ đầu vào chưa đáng tin rồi tự đặt `authenticated`. Không bao giờ gán authentication thành công chỉ vì details trông đúng.

### 3.1. Vì sao `getDetails()` đôi lúc là `null`?

Có nhiều nguyên nhân chính đáng:

- Authentication mechanism không thu thập metadata phụ trợ.
- Authentication token hoặc provider được viết riêng và không chuyển details.
- Một loại token được dựng từ JWT, OAuth2 hoặc pre-authentication có cấu trúc khác.
- Code đang quan sát `AnonymousAuthenticationToken` hoặc một authentication trong môi trường test.
- Authentication result mới được tạo/biến đổi mà không giữ lại object details ban đầu.

Một dịch vụ dùng chung không được giả định `getDetails() != null`, càng không được ép kiểu mọi token thành `WebAuthenticationDetails`.

## 4. Ví dụ hoàn chỉnh: Spring Boot Servlet đọc details của form login

Tạo một project bằng Spring Initializr với **Java 17+**, **Spring Boot 3.x**, **Spring Web**, **Spring Security** (Maven). Đặt file `src/main/java/com/example/demo/DetailsDemoApplication.java` như dưới đây. Ví dụ minh họa nguồn details mặc định từ form login, không cần tạo filter riêng.

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class DetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DetailsDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .formLogin(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @RestController
    static class DetailsController {

        @GetMapping("/")
        String home() {
            return "Open /me to log in and inspect authentication details.";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            Object raw = authentication.getDetails();
            WebAuthenticationDetails web =
                raw instanceof WebAuthenticationDetails details
                    ? details : null;

            return Map.of(
                "username", authentication.getName(),
                "detailsType", raw == null
                    ? "null" : raw.getClass().getSimpleName(),
                "remoteAddressAtLogin", web == null
                    ? "unavailable" : web.getRemoteAddress(),
                "hadSessionWhenCaptured", web != null
                    && web.getSessionId() != null
            );
        }
    }
}
~~~

### 4.1. Cách chạy

Tại thư mục project Maven do Spring Initializr tạo:

~~~bash
./mvnw spring-boot:run
~~~

Với Windows PowerShell, dùng `.\mvnw.cmd spring-boot:run`. Trong browser:

1. Mở `http://localhost:8080/`: được truy cập mà chưa đăng nhập.
2. Mở `http://localhost:8080/me`: Spring Security chuyển hướng tới trang đăng nhập mặc định (thường `/login`).
3. Đăng nhập `alice` với password demo `demo-pass`.
4. Sau khi đăng nhập, mở lại `http://localhost:8080/me` và xem JSON.

Ví dụ **hình dạng kết quả**, không khẳng định giá trị IP/session ở mọi máy:

~~~json
{
  "username": "alice",
  "detailsType": "WebAuthenticationDetails",
  "remoteAddressAtLogin": "127.0.0.1",
  "hadSessionWhenCaptured": true
}
~~~

`remoteAddressAtLogin` có thể là IPv6 loopback như `0:0:0:0:0:0:0:1`; trường `hadSessionWhenCaptured` có thể là `true` hoặc `false` tùy thời điểm session được tạo. HTTP status sau khi đăng nhập hợp lệ là `200`, còn request chưa đăng nhập với cấu hình form login mặc định thường nhận `302` redirect tới `/login`. Nếu đăng nhập sai, Spring Security chuyển tới trang lỗi login theo mặc định; nó không trả danh tính đã xác thực.

**Tại sao controller không trả raw session ID?** Session ID là thông tin nhạy cảm: nếu lộ, attacker có thể lợi dụng trong một số điều kiện. Ví dụ chỉ xuất boolean để cho thấy metadata tồn tại, không lộ giá trị. Dữ liệu password ở ví dụ cũng chỉ dùng trong local demo; môi trường thật phải có cơ chế quản lý secret, bảo mật credential và HTTPS phù hợp.

### 4.2. Theo dõi đúng vòng đời

- `formLogin(withDefaults())` cài các thành phần xử lý form login, trong đó filter tạo request token kèm details.
- `DaoAuthenticationProvider` kiểm tra password đã mã hóa bởi `BCryptPasswordEncoder` và tạo token đã xác thực.
- Đối với session-based form login mặc định, kết quả đăng nhập có thể được giữ trong `SecurityContext` qua `SecurityContextRepository`.
- Controller nhận tham số `Authentication` gắn với người dùng đã xác thực. `getDetails()` quan sát metadata của lần authentication ấy, không đọc lại mọi HTTP header của GET `/me`.
- `Map.of` không chấp nhận giá trị `null`; ví dụ chuyển `null` thành chuỗi và chỉ trả boolean cho thông tin session.

Bạn có thể mở trình duyệt ẩn danh, lặp lại đăng nhập và quan sát khác biệt. Nếu muốn kiểm tra request hiện tại, hãy so sánh `HttpServletRequest.getRemoteAddr()` trong một controller riêng với `WebAuthenticationDetails.getRemoteAddress()`, đồng thời hiểu rõ proxy boundary và privacy.

## 5. Tùy biến dữ liệu với `AuthenticationDetailsSource`

Chỉ tùy biến khi metadata đó thực sự hỗ trợ authentication flow hoặc auditing cụ thể. Ví dụ bạn muốn ghi nhận **thời điểm** và **địa chỉ peer** tại lần login, thay cho `WebAuthenticationDetails` mặc định. Lựa chọn tốt là object nhỏ, immutable, không chứa password, token, cookie hay `HttpServletRequest`.

Dưới đây là **các thay đổi áp dụng cho project ở mục 4**, không phải chương trình Java độc lập. Thêm các import vào file `DetailsDemoApplication.java`:

~~~java
import java.io.Serializable;
import java.time.Instant;
~~~

Trong `DetailsDemoApplication`, thêm nested record (nếu lưu qua session, object nên có thể serialize):

~~~java
record LoginRequestDetails(
    String remoteAddress,
    Instant capturedAt
) implements Serializable {}
~~~

Thay phương thức bean `security(...)` bằng:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form.authenticationDetailsSource(
            request -> new LoginRequestDetails(
                request.getRemoteAddr(),
                Instant.now()
            )
        ))
        .build();
}
~~~

Cấu hình `formLogin(...).authenticationDetailsSource(...)` cung cấp một `AuthenticationDetailsSource<HttpServletRequest, ?>` tùy chỉnh cho form login filter. Tại mỗi lần filter xử lý form authentication attempt, lambda tạo `LoginRequestDetails`. **Bằng việc đổi source, bạn đã thay thế kiểu details mặc định**, vì vậy `getDetails()` của lần login này có thể là `LoginRequestDetails`, không còn `WebAuthenticationDetails`.

Để controller hiển thị object tùy chỉnh, thay logic đọc `raw` trong `me(...)` thành:

~~~java
Object raw = authentication.getDetails();
LoginRequestDetails login =
    raw instanceof LoginRequestDetails details ? details : null;

return Map.of(
    "username", authentication.getName(),
    "detailsType", raw == null
        ? "null" : raw.getClass().getSimpleName(),
    "capturedAt", login == null
        ? "unavailable" : login.capturedAt().toString(),
    "hasRemoteAddress", login != null
        && login.remoteAddress() != null
);
~~~

Khi đăng nhập lại trong một phiên mới, `detailsType` sẽ là `LoginRequestDetails` trong luồng form login như đã cấu hình và `capturedAt` phản ánh lần tạo details. Không nên dùng `capturedAt` như kết quả kiểm tra thời gian sống session/token: đó chỉ là dữ liệu audit minh họa. Nếu cần giữ remote address và session ID của `WebAuthenticationDetails`, bạn có thể định nghĩa record chứa các trường tương ứng, hoặc chọn chiến lược bao gói rõ ràng; đừng ép kiểu object tùy chỉnh thành `WebAuthenticationDetails`.

### 5.1. Khi metadata sẽ ảnh hưởng quyết định bảo mật

Không xác thực hay cấp quyền chỉ vì client gửi `X-User-Role: admin`, `X-Tenant: foo`, `X-Trusted-IP` hoặc một header tự khai báo rồi gắn vào details. Mọi dữ liệu client có thể sửa đều phải coi là **untrusted input** cho tới khi có kiểm chứng độc lập. Chẳng hạn:

- Correlation/request ID có thể phục vụ trace nếu được xác lập hoặc chuẩn hóa bởi điểm tin cậy; không dùng làm bằng chứng người dùng.
- Địa chỉ IP chỉ phục vụ signal phụ trợ sau khi xác định nguồn forwarded header đáng tin cậy.
- Certificate metadata có thể có giá trị cho xác thực khi một TLS/mTLS boundary đã kiểm chứng certificate và truyền kết quả một cách chống giả mạo.
- Nếu metadata là OTP hay factor bảo mật, dùng mechanism authentication thích hợp để kiểm tra và **xóa** bí mật ngay; đừng giữ giá trị raw trong details hoặc session.

Một `AuthenticationProvider` có thể sử dụng metadata đã kiểm chứng làm input phụ trợ, nhưng kết quả tin cậy phải phát sinh từ chính bước xác thực. Không bao giờ dựa trên sự hiện diện của `details` để biến authentication request thành authenticated token.

### 5.2. Không giữ đối tượng request trong SecurityContext

`Authentication` có thể sống lâu hơn một HTTP request, được giữ trong session, cache hoặc chuyển qua một boundary khác. Không lưu trực tiếp `HttpServletRequest`, `HttpServletResponse`, stream, servlet container object, mutable map lớn, session/cookie/token raw hay dữ liệu cá nhân không cần thiết trong details. Tập metadata nên nhỏ, có kiểu rõ, có thể serialize khi cơ chế persistence cần, và có chính sách retention thích hợp.

`AbstractAuthenticationToken.eraseCredentials()` sẽ xét các object credentials/principal/details và gọi `eraseCredentials()` trên object nào thực thi `CredentialsContainer`. Điều đó **không có nghĩa** Spring Security tự scrub mọi field trong mọi custom details object. Hãy tránh nhét secret vào đó ngay từ đầu.

## 6. Với HTTP Basic, bearer token và WebFlux thì sao?

Đừng suy ra một object `Authentication` có details kiểu nào chỉ từ việc nhìn thấy request HTTP.

**HTTP Basic (Servlet):** một filter có thể tạo token xác thực và gắn metadata cho request hiện tại, tùy implementation. Không vì thấy `WebAuthenticationDetails` trong form login mà cam kết mọi cấu hình Basic đều duy trì đúng cấu trúc đó.

**JWT/bearer resource server:** token xác thực có thể dùng `JwtAuthenticationToken` hoặc implementation khác. Claims `iss`, `sub`, `aud`, `scope` thuộc token đã kiểm chứng; chúng không tự động là `Authentication.getDetails()`. Dùng API của `Jwt`/principal hoặc token phù hợp để đọc claim sau khi xác minh. Không lấy claim từ bearer string chưa được kiểm chứng hoặc coi `getDetails() == null` là xác thực thất bại.

**Pre-authentication, mTLS và custom mechanisms:** metadata có thể là loại riêng tùy filter/converter/provider. Phải kiểm tra contracts của cơ chế ấy. Chỉ có `Authentication#getDetails()` là API chung, không có quy định bắt buộc mọi provider phải điền cùng loại.

### 6.1. Reactive: có cùng `Authentication` nhưng không có Servlet request

Spring WebFlux dùng `ServerWebExchange` và security context trong Reactor Context. Nó không dùng Servlet `HttpServletRequest` hay mặc định tạo `WebAuthenticationDetails`. Nếu reactive mechanism cần details, `ServerAuthenticationConverter` và các thành phần xử lý auth tương ứng có thể tạo token và gắn dữ liệu phù hợp; provider reactive cần duy trì chúng nếu kết quả yêu cầu.

Ví dụ **đoạn method trong một `@RestController` thuộc project WebFlux**, nơi security chain đã xác thực:

~~~java
@GetMapping("/me")
Mono<Map<String, String>> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> Map.of(
            "username", auth.getName(),
            "detailsType", auth.getDetails() == null
                ? "null"
                : auth.getDetails().getClass().getSimpleName()
        ));
}
~~~

Đoạn minh họa cần import `java.util.Map`, `reactor.core.publisher.Mono`, `org.springframework.web.bind.annotation.GetMapping`, `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext` và `org.springframework.security.core.Authentication`. Đây là phương thức không độc lập: cần Spring WebFlux/Security, controller và cấu hình đăng nhập. Nó kiểm tra có details hay không mà không ép kiểu sang lớp Servlet.

Nếu phải lấy **địa chỉ/kết nối của request WebFlux hiện tại**, dùng `ServerWebExchange` hoặc `ServerHttpRequest` theo chính sách trusted proxy, độc lập với `Authentication.getDetails()`. `ReactiveSecurityContextHolder` dùng Reactor Context, không nên bị thay bằng `SecurityContextHolder.getContext()` từ Servlet/ThreadLocal.

## 7. Khi nào nên dùng details, và khi nào không?

| Nhu cầu | Vị trí thích hợp | Vì sao |
| --- | --- | --- |
| Biết username/account đã xác thực | `Authentication.getPrincipal()` / `getName()` | Dữ liệu danh tính |
| Kiểm tra role/scope/permission | `getAuthorities()` + authorization rules | Quyền được cơ chế xác thực cấp |
| Metadata của **lần đăng nhập**: peer IP, thời điểm capture | `getDetails()` nếu cơ chế có hỗ trợ | Phụ trợ, theo snapshot authentication |
| Đọc IP/header/trace ID của **request hiện tại** | Servlet request/WebFlux exchange/tracing | Không phụ thuộc thời điểm login |
| Lưu hồ sơ user/tenant bền vững | User/domain model đã xác minh | Vòng đời dài hơn một request/login |
| Lưu thông tin session và hết hạn | Session infrastructure/security context repository | Quản lý state và lifecycle |
| Ghi audit log của mọi request | Filter/interceptor/observability pipeline | Chỉ details của lần login là không đủ |
| Thông tin factor/password/token bí mật | Authentication mechanism chuyên trách | Secret phải được kiểm tra và bảo vệ riêng |

Trên các ứng dụng sử dụng session, details có thể được serialize hoặc xuất hiện trong `Authentication.toString()`, log, debug dump hoặc monitoring nếu bạn vô ý ghi toàn object. Không trả trực tiếp `authentication.getDetails()` trong JSON API để “dễ debug”. Thiết kế response chỉ chọn giá trị được phép tiết lộ, tránh thông tin định danh nhạy cảm, đặc biệt session ID, raw client token, địa chỉ nội bộ và header authentication.

## 8. Các lỗi thường gặp và cách sửa

### Lỗi 1: Ép kiểu thẳng

~~~java
WebAuthenticationDetails details =
    (WebAuthenticationDetails) authentication.getDetails();
~~~

Có thể ném `ClassCastException` hoặc thu được `null` nếu cơ chế khác được cấu hình. Hãy dùng kiểm tra kiểu và fallback theo hợp đồng dữ liệu:

~~~java
Object raw = authentication.getDetails();
if (raw instanceof WebAuthenticationDetails details) {
    // Sử dụng riêng thông tin Servlet đã biết kiểu.
} else {
    // Không có hoặc thuộc loại details khác.
}
~~~

### Lỗi 2: Hiểu sessionId trong details là session hiện tại

`getSessionId()` được chụp tại lúc tạo `WebAuthenticationDetails`; session có thể được tạo/đổi ID sau đó. Để làm logic hiện tại về session, dùng session management đúng cấp, không lấy details snapshot làm nguồn sự thật.

### Lỗi 3: Đọc địa chỉ IP rồi dùng làm quyền truy cập

IP không chứng minh danh tính. Đằng sau proxy, địa chỉ kết nối phụ thuộc cấu hình forwarded headers. Không dùng giá trị `X-Forwarded-For` chưa được xác minh để thay bằng principal/authority hoặc bỏ bước authentication.

### Lỗi 4: Custom provider tạo token mới nhưng làm mất details

Một provider tự viết có thể trả authentication result mới không có details. Nếu metadata thực sự cần giữ, provider phải chủ động bảo toàn dữ liệu phù hợp sau khi kiểm chứng credentials, với chính sách không lưu secret. Việc details biến mất không mặc định là lỗi ở `SecurityContextHolder`.

### Lỗi 5: Nhét đối tượng request hoặc secrets vào details

`HttpServletRequest` và request stream không phù hợp lưu trong session/context dài hạn. Raw password, OTP, cookie hay bearer token không phải metadata an toàn. Nên chọn object nhỏ, immutable và có thời hạn giữ dữ liệu hợp lý.

### Lỗi 6: Dùng details từ lần login để lập audit log từng request

Browser có thể gửi hàng trăm request sau một lần login; details được lưu vẫn là snapshot cũ. Dùng request filter/interceptor và trace/correlation ID được quản lý theo từng request nếu muốn theo dõi hoạt động.

### Lỗi 7: Dùng Servlet type trong reactive handler

`WebAuthenticationDetails` phụ thuộc `HttpServletRequest`. WebFlux có `ServerWebExchange`; details có thể null hoặc thuộc kiểu khác. Code dùng `ReactiveSecurityContextHolder` và kiểm tra data contract thực tế của converter/provider.

## 9. Bài tập suy luận

**Tình huống A.** User đăng nhập form lúc 08:00 từ một kết nối có remoteAddress `192.0.2.10`. Đến 08:30, họ truy cập `/profile` từ một mạng khác nhưng vẫn dùng cùng phiên. `authentication.getDetails()` có phản ánh IP mới không?

**Đáp án:** không được giả định. Nếu context và authentication cũ được khôi phục từ session, details có thể giữ địa chỉ chụp ở lần login. Muốn biết request hiện tại, đọc request hiện tại qua cơ chế tin cậy.

**Tình huống B.** `WebAuthenticationDetails.getSessionId()` là `null`, nhưng request sau vẫn đăng nhập được. Có mâu thuẫn không?

**Đáp án:** không. Khi details được xây dựng có thể chưa tồn tại session; session được tạo hoặc ID được đổi sau đó. Snapshot không đồng bộ ngược với session management.

**Tình huống C.** Một controller dùng JWT hợp lệ, `authentication.getPrincipal()` là `Jwt` nhưng `getDetails()` null. Đây có phải dấu hiệu JWT chưa được xác minh?

**Đáp án:** không. Trường details là tùy chọn. Kiểm tra authentication flow/resource server và các claim trên token đã được xác minh; đừng dùng details như chỉ báo mặc định của JWT validation.

**Tình huống D.** App muốn ghi HTTP request ID theo từng request. Có nên đặt nó vào session-stored details lúc login?

**Đáp án:** không phù hợp vì request ID thay đổi cho từng request. Hãy dùng request context và logging/observability; chỉ gắn dữ liệu với authentication nếu đó thật sự là thông tin của lần authentication.

**Tình huống E.** Một frontend gửi `X-Role: ADMIN` rồi backend đưa vào `authentication.getDetails()`. Có được xem đó là quyền của user?

**Đáp án:** không. Header client là untrusted input; role phải đến từ nguồn quyền đáng tin sau khi xác thực hoặc chính sách server, và được biểu diễn/kiểm tra đúng trong authorization pipeline.

## 10. Checklist áp dụng

1. Bạn đã xác định authentication mechanism hiện tại (form login, Basic, JWT, OAuth2, pre-auth, custom) và stack Servlet hay reactive chưa?
2. `getDetails()` có thể null hoặc kiểu khác không? Có `instanceof` và fallback hợp lý chưa?
3. Metadata được tạo **khi nào**? Có phải snapshot login, current HTTP request hay một dữ liệu bền vững?
4. Nguồn dữ liệu có đáng tin không? IP/header có bị proxy hoặc client làm sai lệch không?
5. Có secret, session ID, raw JWT, cookie hoặc dữ liệu cá nhân nào bị log/serialize/trả API không?
6. Nếu custom provider/converter tạo token mới, metadata cần giữ có được truyền đúng sau khi credentials được kiểm chứng không?
7. Có yêu cầu audit của từng request không? Nếu có, đã dùng request-scoped observability thay cho một snapshot cũ chưa?
8. Nếu làm việc trong WebFlux, bạn có dùng đúng Reactor Context và không ép kiểu sang đối tượng Servlet không?

**Ý chính cần nhớ:** `Authentication.getDetails()` là một trường **metadata tùy chọn của authentication**, không phải nơi lưu danh tính hay quyền mặc định. Trong Servlet form login, nó thường là `WebAuthenticationDetails` chứa địa chỉ peer và session ID có thể null tại thời điểm xác thực. Cần đọc theo đúng kiểu, vòng đời và mức độ tin cậy của cơ chế đang dùng.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 API — Authentication](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security 6.5 API — AbstractAuthenticationToken](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Spring Security 6.4 API — WebAuthenticationDetails](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/web/authentication/WebAuthenticationDetails.html)
- [Spring Security 6.5 API — FormLoginConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 API — AuthenticationWebFilter (WebFlux)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
