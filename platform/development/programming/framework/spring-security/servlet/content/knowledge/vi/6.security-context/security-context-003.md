# AnonymousAuthenticationToken và cách nhận biết người dùng chưa đăng nhập trong Spring Security Servlet

## 1. Mục tiêu của bài học

Trong ứng dụng Spring MVC sử dụng Spring Security, một request không mang thông tin đăng nhập **không nhất thiết** khiến `SecurityContextHolder.getContext().getAuthentication()` trả về `null`. Theo cấu hình mặc định, Spring Security có thể đặt một `AnonymousAuthenticationToken` vào ngữ cảnh bảo mật để biểu diễn người gọi **chưa đăng nhập**.

Chi tiết dễ gây nhầm lẫn nhất là: **`AnonymousAuthenticationToken.isAuthenticated()` thường trả về `true`, nhưng người gọi vẫn được xem là anonymous, không phải người dùng đã đăng nhập**. Đọc sai cờ này có thể khiến controller, filter tùy biến hoặc code nghiệp vụ mở đường cho khách truy cập vào chức năng dành cho tài khoản.

Bài học tập trung vào phạm vi **Spring Security trên Servlet stack** (Spring Boot, Spring MVC, `SecurityFilterChain`, `SecurityContextHolder`), trả lời các câu hỏi:

1. Anonymous authentication là gì và vì sao Spring Security tạo token cho người chưa đăng nhập?
2. `AnonymousAuthenticationFilter` điền gì vào `SecurityContext`? Principal, authorities, credentials và cờ `authenticated` có ý nghĩa nào?
3. Làm sao phân biệt **không có authentication**, **anonymous**, **người dùng được xác thực** và **remember-me**?
4. Vì sao các quy tắc `permitAll()`, `anonymous()`, `authenticated()`, `fullyAuthenticated()` cho kết quả khác nhau?
5. Cách quan sát, kiểm thử và tránh các lỗi phân quyền trong ứng dụng Servlet thực tế.

## 2. Authentication không đồng nghĩa với "đã đăng nhập"

Spring Security dùng interface `Authentication` để biểu diễn thông tin về chủ thể của một request. Một `Authentication` có thể chứa:

- **`principal`**: danh tính được biểu diễn, chẳng hạn một user, username hoặc đại diện cho anonymous;
- **`credentials`**: thông tin xác thực, có thể đã bị xóa/ẩn sau khi xác thực;
- **`authorities`**: danh sách `GrantedAuthority` phục vụ quyết định phân quyền;
- **`details`**: metadata bổ sung về request/cơ chế xác thực;
- **`isAuthenticated()`**: cờ trạng thái của đối tượng authentication theo hợp đồng triển khai cụ thể.

`SecurityContext` chứa `Authentication` hiện hành; `SecurityContextHolder` cho code đang chạy truy cập vào context đó. Theo mô hình Servlet thông dụng, context được gắn với luồng thực thi request và được quản lý/giải phóng ở ranh giới request. Không nên lưu `Authentication` vào static field hay giả định nó tự lan sang mọi thread bất đồng bộ.

**Điểm mấu chốt:** có đối tượng `Authentication` trong context là điều kiện về **trạng thái nội bộ**, không tự chứng minh có người dùng đăng nhập. Spring Security cố ý tạo một đối tượng `AnonymousAuthenticationToken` để nhiều thành phần có thể xử lý request theo cùng một abstraction `Authentication`.

### Bốn trạng thái cần phân biệt

| Trạng thái | `SecurityContext.getAuthentication()` | Cách hiểu đúng |
| --- | --- | --- |
| Context chưa được điền / bên ngoài filter | Có thể là `null` | Chưa có `Authentication`; không tự kết luận request đã đi qua toàn bộ Spring Security |
| Anonymous mặc định | Thường là `AnonymousAuthenticationToken` | Người gọi **chưa đăng nhập**, dù token có cờ `authenticated=true` |
| Đăng nhập bằng Basic/form/token hợp lệ | Một `Authentication` thể hiện kết quả xác thực thật, tùy cơ chế | Có người dùng hoặc client đã xác thực, nhưng vẫn phải kiểm tra **quyền** |
| Remember-me | Một kiểu `Authentication` được nhận diện là remember-me khi tính năng được cấu hình | Có danh tính được nhớ lại; một số chức năng nhạy cảm vẫn yêu cầu **full authentication** |

Không phải mọi request đều đi qua anonymous filter: có thể có cấu hình vô hiệu hóa anonymous, chain bảo mật khác nhau, code gọi trực tiếp ngoài request hoặc các điểm truy cập context không đúng vòng đời. Vì vậy code nên xử lý được cả `null` và token anonymous.

## 3. `AnonymousAuthenticationFilter` hoạt động như thế nào?

Trong một `SecurityFilterChain` Servlet có anonymous authentication được bật (mặc định khi dùng cấu hình chuẩn), `AnonymousAuthenticationFilter` tham gia xử lý ngữ cảnh bảo mật. Khi đi tới filter này mà context **chưa có** `Authentication`, filter cung cấp một `AnonymousAuthenticationToken`.

Luồng khái quát:

```text
HTTP GET /public không có credential
    |
Servlet Filter Chain
    |
Spring Security tạo/đọc SecurityContext
    |
Các cơ chế xác thực được cấu hình
    |  (không nhận được credential hợp lệ)
    v
AnonymousAuthenticationFilter
    |-- context chưa có Authentication?
    |       |-- CÓ -> cung cấp AnonymousAuthenticationToken
    |       |-- KHÔNG -> giữ Authentication đang có
    v
AuthorizationFilter
    |-- áp dụng permitAll / anonymous / authenticated / ...
    v
Controller (nếu được phép)
```

Cụ thể với cấu hình anonymous thông dụng:

- Principal mặc định là chuỗi `"anonymousUser"`.
- Authority mặc định là `ROLE_ANONYMOUS`.
- Loại đối tượng thường là `AnonymousAuthenticationToken`.
- Thuộc tính `isAuthenticated()` của token anonymous có thể là `true`.
- Một `key` nội bộ được dùng trong cơ chế tạo/kiểm tra token anonymous của Spring Security; **key này không phải mật khẩu người dùng, không phải session ID và không biến token thành bằng chứng đăng nhập**.

Các giá trị mặc định có thể được tùy biến; không dùng chuỗi `anonymousUser`, `ROLE_ANONYMOUS` hoặc cấu hình key làm tiêu chuẩn duy nhất để xác định user đã đăng nhập.

### Vì sao token anonymous đánh dấu `authenticated=true`?

Đây là cách triển khai giúp Spring Security làm việc với abstraction `Authentication` thống nhất: token anonymous là đối tượng trạng thái nội bộ được framework xây dựng và nhận diện. Cờ `authenticated=true` ở đối tượng này **không mang nghĩa** "đã kiểm tra mật khẩu/token của một tài khoản thật".

Do đó, hai phép kiểm tra sau **không đủ** để xác định người dùng đã đăng nhập:

```java
Authentication auth = SecurityContextHolder.getContext().getAuthentication();

boolean wrongA = auth != null;
boolean wrongB = auth != null && auth.isAuthenticated();
```

Đây là **đoạn minh họa đặt trong code chạy trong request**, không phải chương trình Java hoàn chỉnh. Với một request anonymous thông dụng, cả `wrongA` và `wrongB` đều có thể là `true`. Nếu dùng chúng để tự mở tính năng chỉ dành cho user, ứng dụng có nguy cơ đưa ra quyết định phân quyền sai.

## 4. Cách nhận biết anonymous: dùng `AuthenticationTrustResolver`

Spring Security có interface `AuthenticationTrustResolver` để phân loại `Authentication`. Triển khai thường dùng là `AuthenticationTrustResolverImpl`:

```java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth = SecurityContextHolder.getContext().getAuthentication();
AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

boolean anonymous = auth != null && resolver.isAnonymous(auth);
boolean rememberMe = auth != null && resolver.isRememberMe(auth);

boolean recognizedUser = auth != null
    && auth.isAuthenticated()
    && !anonymous;

boolean fullyAuthenticated = recognizedUser && !rememberMe;
```

Đoạn trên cũng là **mã minh họa trong phương thức hoặc code thực thi**, không phải một tệp Java có `main`. Các biểu thức cần hiểu như sau:

- `resolver.isAnonymous(auth)` nhận diện kiểu xác thực anonymous, thay vì kiểm tra username bằng chuỗi.
- `resolver.isRememberMe(auth)` nhận diện remember-me khi cơ chế đó được sử dụng.
- `recognizedUser` ở đây diễn giải thực dụng cho các token tiêu chuẩn: có authentication hợp lệ theo cờ, **không** phải anonymous. Đây vẫn không phải là lệnh cấp quyền.
- `fullyAuthenticated` ở minh họa loại bỏ cả anonymous và remember-me. Đối với chính sách bảo mật, ưu tiên rule `fullyAuthenticated()` do Spring Security cung cấp thay vì tự dựng chính sách phân quyền từ boolean trong controller.

**`AuthenticationTrustResolver` là cơ chế phân loại**, không phải một hệ thống xác thực mới. Với custom `Authentication`, hãy làm rõ hợp đồng xác thực và tích hợp phù hợp để Spring Security không nhận diện sai trạng thái.

### Khi nào nên dùng `instanceof AnonymousAuthenticationToken`?

Code như sau có thể hoạt động trong một hệ thống chỉ sử dụng anonymous token mặc định:

```java
boolean anonymous = auth instanceof AnonymousAuthenticationToken;
```

Tuy nhiên, `AuthenticationTrustResolver` truyền đạt ý định rõ hơn và thống nhất với cách Spring Security phân biệt anonymous/remember-me trong hệ thống authorization. Không xây logic dựa vào `auth.getName().equals("anonymousUser")`, bởi một user thực có thể có tên giống chuỗi mặc định, và principal anonymous có thể được đổi tên.

### `HttpServletRequest.getUserPrincipal()` thì sao?

Trong servlet integration của Spring Security, `HttpServletRequest.getUserPrincipal()` thường trả `null` với người dùng anonymous, dù `SecurityContextHolder` chứa `AnonymousAuthenticationToken`. Đây là hai **cách nhìn** khác nhau:

- `SecurityContextHolder` cho thấy `Authentication` mà các security filters đang xử lý, kể cả placeholder anonymous.
- Servlet principal API biểu diễn principal của caller theo hợp đồng servlet wrapper, không nhất thiết trả token placeholder anonymous.

Vì các kiểu injection như `Principal`, `Authentication` hoặc `@AuthenticationPrincipal` có cơ chế resolve riêng, **không giả định** chúng luôn trả cùng một đối tượng hoặc cùng một giá trị với `SecurityContextHolder` trong mọi cấu hình. Khi cần phân tích trạng thái anonymous ở runtime, lấy `Authentication` từ `SecurityContextHolder` và dùng trust resolver là lựa chọn rõ ràng cho bài học này.

## 5. `permitAll()`, `anonymous()`, `authenticated()`, `fullyAuthenticated()`

Với Spring Security 6 trên Servlet, `authorizeHttpRequests` có các quy tắc mô tả ý định rất sát nghiệp vụ:

| Quy tắc | Anonymous | User đã đăng nhập bằng Basic/form | Remember-me được chấp nhận | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `permitAll()` | Cho phép | Cho phép | Cho phép | Endpoint mở đối với mọi trạng thái authentication |
| `anonymous()` | Cho phép | Từ chối | Thường từ chối | Chỉ cho người được xem là anonymous |
| `authenticated()` | Từ chối | Cho phép | Cho phép | Cần danh tính được Spring Security coi là đã xác thực, không phải anonymous |
| `fullyAuthenticated()` | Từ chối | Cho phép | Từ chối | Yêu cầu xác thực đầy đủ, loại remember-me |
| `hasRole("ADMIN")` | Thường từ chối | Cho phép nếu có `ROLE_ADMIN` | Phụ thuộc authority và chính sách | Cần một quyền cụ thể; xác thực không tự sinh quyền |
| `denyAll()` | Từ chối | Từ chối | Từ chối | Chặn mọi request khớp rule |

Cột remember-me giả định ứng dụng **đã cấu hình** cơ chế này; Spring Security không tự bật remember-me cho mọi ứng dụng. Bảng mô tả kết quả của **authorization**; request còn có thể bị các filter khác chặn trước đó (ví dụ CSRF) hoặc kết thúc vì không có handler phù hợp.

Ví dụ về ý định cấu hình:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/guest-only/**").anonymous()
    .requestMatchers("/account/**").authenticated()
    .requestMatchers("/sensitive/**").fullyAuthenticated()
    .anyRequest().denyAll()
)
```

Đây là đoạn lệnh **nằm trong cấu hình `HttpSecurity`**, không biên dịch độc lập. Spring Security không đánh giá `authenticated()` chỉ bằng cách gọi trực tiếp `auth.isAuthenticated()` rồi tin kết quả đó; authorization logic sử dụng ngữ nghĩa trust resolver để loại anonymous.

**Phân biệt quan trọng:** `permitAll()` vẫn cho request đi qua security filter chain nếu chain khớp. `anonymous()` không có nghĩa "cho tất cả người dùng, kể cả người đã đăng nhập"; nó cố ý giới hạn cho khách. Còn `fullyAuthenticated()` không nói lên người dùng có quyền admin hay được sở hữu đối tượng dữ liệu cụ thể.

## 6. Ví dụ đầy đủ: quan sát token anonymous trong Spring Boot Servlet

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x**, Spring MVC và HTTP Basic để tạo các trạng thái có thể quan sát. Chỉ dùng trên môi trường phát triển; HTTP Basic gửi credentials ở mỗi request nên production phải dùng HTTPS.

Một dự án Spring Boot đã cấu hình plugin build và dependency management cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp `src/main/java/example/anonymous/AnonymousDemoApplication.java` với nội dung:

```java
package example.anonymous;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AnonymousDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnonymousDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/whoami").permitAll()
                .requestMatchers(HttpMethod.GET, "/guest").anonymous()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/strong").fullyAuthenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class IdentityController {

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/whoami")
    Map<String, Object> whoami() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        boolean anonymous =
            auth != null && resolver.isAnonymous(auth);
        boolean rememberMe =
            auth != null && resolver.isRememberMe(auth);
        boolean loggedIn =
            auth != null && auth.isAuthenticated() && !anonymous;

        return Map.of(
            "type", auth == null ? "none" :
                auth.getClass().getSimpleName(),
            "name", auth == null ? "none" : auth.getName(),
            "tokenFlag", auth != null && auth.isAuthenticated(),
            "anonymous", anonymous,
            "loggedIn", loggedIn,
            "fullyAuthenticated", loggedIn && !rememberMe
        );
    }

    @GetMapping("/guest")
    String guest() {
        return "guest only";
    }

    @GetMapping("/me")
    String me() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return "hello " + auth.getName();
    }

    @GetMapping("/strong")
    String strong() {
        return "fully authenticated";
    }
}
```

Trong cùng một tệp Java, chỉ class `AnonymousDemoApplication` là `public`; hai class còn lại là package-private. Cấu trúc này hợp lệ với Java 17. `@SpringBootApplication` quét package `example.anonymous`, do đó phát hiện cả cấu hình lẫn controller.

Các điểm đáng chú ý:

- Không khai báo `.anonymous(...)` trên `HttpSecurity` để bật tính năng: anonymous authentication **được bật mặc định** trong cấu hình Spring Security thông thường.
- `/whoami` được `permitAll`, nên có thể quan sát trạng thái anonymous và đăng nhập; controller đọc token từ `SecurityContextHolder`.
- `/guest` dùng `anonymous()`, chỉ cho anonymous vào; người đã đăng nhập bị từ chối ở authorization.
- `/me` dùng `authenticated()`, vì vậy anonymous không được phép vào dù token có `isAuthenticated() == true`.
- `/strong` dùng `fullyAuthenticated()`; Basic authentication đủ điều kiện. Demo không cấu hình remember-me, nên chưa thể trực tiếp trình diễn khác biệt với một remember-me token.
- `anyRequest().denyAll()` thể hiện nguyên tắc chặn đường dẫn chưa khai báo; nó áp dụng trong chain này, vốn không có `securityMatcher` nên mặc định khớp mọi request.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder có tiền tố thuật toán phù hợp khi lưu mật khẩu demo; không lưu mật khẩu plaintext trong user store.
- Ví dụ toàn bộ là GET. CSRF protection mặc định vẫn bật theo phạm vi áp dụng; không nên tắt CSRF chỉ để làm POST từ browser chạy được.

### Chạy và quan sát

Trong dự án Spring Boot có Gradle wrapper, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell có thể chạy `./gradlew.bat bootRun`. Khi server local chạy trên cổng mặc định 8080, gửi:

```bash
# Không gửi credential: xem anonymous token.
curl -i http://localhost:8080/whoami

# Cũng URL trên nhưng có tài khoản hợp lệ.
curl -i -u learner:demo-pass http://localhost:8080/whoami

# Đối chiếu quy tắc cho khách và user thật.
curl -i http://localhost:8080/guest
curl -i -u learner:demo-pass http://localhost:8080/guest
curl -i http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/strong
```

**Kết quả kỳ vọng**, nếu không có cấu hình tùy biến khác, là:

| Request | HTTP status | Ý nghĩa |
| --- | --- | --- |
| `GET /whoami`, anonymous | 200 | Có thể thấy token loại `AnonymousAuthenticationToken`, `anonymous=true`, `loggedIn=false`, `tokenFlag=true` |
| `GET /whoami`, learner | 200 | Authentication từ HTTP Basic, `anonymous=false`, `loggedIn=true`, `fullyAuthenticated=true` |
| `GET /guest`, anonymous | 200 | Body `guest only` |
| `GET /guest`, learner | 403 | User đã đăng nhập không thuộc trạng thái anonymous |
| `GET /me`, anonymous | 401 | HTTP Basic yêu cầu xác thực; không chạy `me()` |
| `GET /me`, learner | 200 | Body `hello learner` |
| `GET /strong`, learner | 200 | Body `fully authenticated` |

Với `GET /whoami` anonymous, JSON thường có nội dung **tương đương**:

```json
{
  "type": "AnonymousAuthenticationToken",
  "name": "anonymousUser",
  "tokenFlag": true,
  "anonymous": true,
  "loggedIn": false,
  "fullyAuthenticated": false
}
```

Thứ tự các key JSON không được đảm bảo vì ví dụ trả `Map.of(...)`. Đây là kết quả **dự kiến**, không phải log/stdout đã chạy trong tài liệu; khi thay đổi cấu hình anonymous, principal/type mặc định có thể khác.

## 7. Tại sao `authenticated()` vẫn chặn anonymous khi token báo true?

Xem phần quan trọng nhất của bảng trước:

```text
AnonymousAuthenticationToken:
  auth != null                -> true
  auth.isAuthenticated()      -> true
  trustResolver.isAnonymous() -> true

Authorization rule authenticated():
  yêu cầu "đã xác thực" theo ngữ nghĩa Spring Security,
  không chấp nhận AnonymousAuthenticationToken
```

Bước authorization trên Servlet không nên viết dưới dạng `auth.isAuthenticated() ? allow : deny` nếu mục đích là bảo vệ endpoint cho user thật. Các bộ `AuthorizationManager`/quy tắc `authenticated()`, `fullyAuthenticated()` của Spring Security hiểu anonymous/remember-me theo trust resolver.

Khi anonymous gọi `/me`, rule `authenticated()` từ chối. `ExceptionTranslationFilter` phân biệt caller anonymous với caller đã xác thực nhưng thiếu quyền để kích hoạt `AuthenticationEntryPoint` thích hợp (HTTP Basic thường trả **401** kèm challenge, còn form login có thể redirect tới login page). Với user đã xác thực nhưng không đủ role/quyền, thông thường nhận **403**.

Không đồng nhất mọi mã 403 với "thiếu role": CSRF token không hợp lệ cũng có thể gây 403, và custom authentication entry point có thể thay đổi phản hồi.

## 8. So sánh bốn cách kiểm tra trong nghiệp vụ

Hãy giả sử một controller cần biết người gọi có đang đăng nhập hay không để hiển thị một khối giao diện tùy chọn.

### Cách không nên dùng: kiểm tra null

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null) {
    // SAI nếu coi đây là bằng chứng có người dùng đăng nhập.
}
```

Với anonymous filter, `auth` hoàn toàn có thể là token anonymous không null.

### Cách không nên dùng: chỉ kiểm tra flag

```java
if (auth != null && auth.isAuthenticated()) {
    // Vẫn có thể đi vào nhánh này khi caller là anonymous.
}
```

`AnonymousAuthenticationToken` thường có `isAuthenticated() == true`, nên đây là lỗi khó thấy khi chỉ test bằng tài khoản có login.

### Cách dễ hỏng: so sánh username

```java
boolean guest = auth == null ||
    "anonymousUser".equals(auth.getName());
```

Chuỗi này có thể bị tùy biến và có thể trùng tên account thật. Không dựa vào name hoặc authority string để định nghĩa trạng thái trust.

### Cách phù hợp: nhận diện bằng trust resolver

```java
AuthenticationTrustResolver resolver =
    new AuthenticationTrustResolverImpl();

boolean signedIn = auth != null
    && auth.isAuthenticated()
    && !resolver.isAnonymous(auth);
```

Dùng kết quả để **điều chỉnh hiển thị**, logging có kiểm soát hoặc code ứng dụng cần biết trạng thái. Khi cần **bắt buộc xác thực hoặc phân quyền**, hãy đặt quy tắc `authenticated()`, `fullyAuthenticated()`, `hasRole(...)`, `hasAuthority(...)` tại cấu hình security và kiểm tra sở hữu tài nguyên tại service/domain khi cần. Đừng dùng một cờ tự tính để thay thế authorization.

## 9. Unit test và MockMvc để chứng minh ý nghĩa anonymous

Để kiểm thử luồng Servlet security thật trong ví dụ, dự án cần thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/test/java/example/anonymous/AnonymousSecurityTest.java`:

```java
package example.anonymous;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousTokenHasTrueFlagButCallerIsNotLoggedIn() throws Exception {
        mvc.perform(get("/whoami"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.type").value("AnonymousAuthenticationToken"))
            .andExpect(jsonPath("$.tokenFlag").value(true))
            .andExpect(jsonPath("$.anonymous").value(true))
            .andExpect(jsonPath("$.loggedIn").value(false));
    }

    @Test
    void basicAuthenticationChangesCallerClassification() throws Exception {
        mvc.perform(get("/whoami").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"))
            .andExpect(jsonPath("$.anonymous").value(false))
            .andExpect(jsonPath("$.loggedIn").value(true))
            .andExpect(jsonPath("$.fullyAuthenticated").value(true));
    }

    @Test
    void guestRuleAcceptsOnlyAnonymousCaller() throws Exception {
        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest only"));

        mvc.perform(get("/guest").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedRuleRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void fullyAuthenticatedRuleAcceptsBasicLogin() throws Exception {
        mvc.perform(get("/strong").with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("fully authenticated"));
    }
}
```

Chạy test:

```bash
./gradlew test
```

Đây là các bài test có khả năng chạy trên dự án đáp ứng dependency/version đã nêu; nội dung tài liệu **không khẳng định đã chạy test thực tế**. Test đầu cố ý chứng minh nghịch lý apparent: `tokenFlag=true` cùng lúc với `anonymous=true` và `loggedIn=false`.

Để kiểm thử thêm remember-me, phải thiết lập cơ chế remember-me thực và một authentication được restore từ cơ chế đó. Đừng tạo một request test chứa `UsernamePasswordAuthenticationToken` rồi kết luận đã kiểm thử được `fullyAuthenticated()` với remember-me.

## 10. Các tình huống ngoài request thông thường

### 10.1. Anonymous filter không chạy hoặc bị tắt

Nếu `AnonymousAuthenticationFilter` bị tắt (ví dụ cấu hình `http.anonymous(...disable...)`) hoặc code chạy ngoài Servlet filter chain, `SecurityContextHolder.getContext().getAuthentication()` có thể bằng `null`. Đừng **tắt anonymous** chỉ để biến check `auth != null` thành một biểu thức "đã đăng nhập"; giải pháp đúng là sử dụng rule và trust resolver phù hợp.

Một ứng dụng nhiều `SecurityFilterChain` có thể bật/tắt hoặc thay đổi cơ chế anonymous theo từng chain. Trước khi kiểm tra context, cần biết request thực sự được chain nào xử lý. `permitAll()` không đồng nghĩa bỏ qua toàn bộ filter chain.

### 10.2. Request có credential sai tới endpoint public

`permitAll()` cho phép **về mặt authorization** khi không có yêu cầu xác thực, nhưng không có nghĩa một credential cố ý gửi lên mà sai sẽ luôn được bỏ qua. Chẳng hạn `BasicAuthenticationFilter` có thể xử lý header Basic sai và trả 401 trước khi `AuthorizationFilter` áp dụng `permitAll`. Lưu ý điều này khi debug "tại sao trang public lại 401".

### 10.3. Authentication sai trạng thái trong custom filter

Nếu tự viết filter và gọi `SecurityContextHolder.getContext().setAuthentication(...)`, bạn chịu trách nhiệm bảo đảm token đặt vào đã được xác minh theo cơ chế thích hợp. Không đặt một `UsernamePasswordAuthenticationToken` có cờ `authenticated=true` chỉ vì nhận được username từ header do client tự gửi. `AnonymousAuthenticationToken` cũng **không phải** chứng cứ đáng tin để cấp đặc quyền.

### 10.4. Background thread, async và unit test

`SecurityContextHolder` thường sử dụng chiến lược dựa trên thread. Một tác vụ chuyển sang thread khác, một unit test gọi service trực tiếp hoặc một listener chạy ngoài web request có thể không có context giống Servlet request. Khi cần truyền security context, dùng cơ chế propagation được Spring Security hỗ trợ và làm rõ vòng đời; luôn xử lý trường hợp `Authentication == null`. Không lưu context của user A vào biến global khiến request của user B đọc nhầm.

### 10.5. Remember-me và tài nguyên nhạy cảm

`authenticated()` thường chấp nhận remember-me như một dạng đã xác thực; `fullyAuthenticated()` loại trừ remember-me để yêu cầu xác thực trực tiếp mới hơn. Với các thao tác như đổi mật khẩu, chuyển tiền hoặc sửa phương thức khôi phục tài khoản, cần thêm chính sách xác minh lại/step-up đúng mức rủi ro, thay vì tin rằng `fullyAuthenticated()` tự động cung cấp MFA hoặc luôn bảo đảm thời gian đăng nhập vừa mới.

### 10.6. Principal và authority có thể thay đổi theo cơ chế đăng nhập

Sau form login, Basic, OAuth2 login hoặc resource server, principal có thể là `UserDetails`, chuỗi, `OAuth2User`, `Jwt` hay kiểu tùy biến. Vì vậy, việc kiểm tra `instanceof UserDetails` hoặc so sánh `principal.toString()` không phải cách đáng tin cậy để xác định một request có authentication hợp lệ trên mọi cơ chế. Authorization nên dựa vào trạng thái và quyền do Spring Security đánh giá.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| `auth != null` tức đã login | Anonymous filter thường tạo token không null | Dùng `AuthenticationTrustResolver` hoặc rule `authenticated()` |
| `auth.isAuthenticated() == true` tức đã login | `AnonymousAuthenticationToken` có thể trả true | Loại anonymous bằng trust resolver |
| Kiểm tra name đúng `anonymousUser` | Principal anonymous có thể tùy biến, user thật có thể cùng tên | Nhận diện trạng thái bằng loại/trust resolver |
| Dựa vào `ROLE_ANONYMOUS` như bằng chứng login/guest duy nhất | Authorities có thể tùy biến | Dựa vào semantics `anonymous()` / trust resolver |
| Mở controller dựa trên tự kiểm tra boolean | Dễ bỏ quên endpoint, thiếu quyền đối tượng | Dùng rule URL/method và domain authorization |
| Gọi `permitAll()` rồi nghĩ request không có security filter | Filter authentication, CSRF, headers vẫn có thể chạy | Hiểu chain và filter trước authorization |
| Coi `anonymous()` là synonym của `permitAll()` | Anonymous-only từ chối người đã login | Chọn rule theo đối tượng thực sự được phép |
| Thấy 401 và kết luận không có token anonymous | 401 có thể xuất phát từ entry point khi anonymous bị chặn | Xem filter, trust resolver và rule đang chạy |
| Tự tắt anonymous để null check dễ viết | Thay đổi hành vi framework và che lỗi thiết kế | Giữ default hợp lý, viết check đúng |
| Coi `fullyAuthenticated()` tương đương MFA | Rule chủ yếu phân biệt remember-me với full auth | Thiết kế step-up/re-auth/MFA riêng nếu cần |
| Giả định mọi thread có cùng context | Context mặc định gắn với request thread | Truyền context đúng cách và dọn sau xử lý |

## 12. Bài tập tự kiểm tra

**Câu 1.** Trong một controller có `Authentication auth = SecurityContextHolder.getContext().getAuthentication();`, `auth != null`, `auth.isAuthenticated() == true`, nhưng `auth.getClass().getSimpleName()` là `AnonymousAuthenticationToken`. Người gọi đã đăng nhập chưa?

**Đáp án:** Chưa. Đây là token đại diện anonymous. Dùng `AuthenticationTrustResolver.isAnonymous(auth)` hoặc chính sách `authenticated()` để nhận diện đúng.

**Câu 2.** Một endpoint được cấu hình `requestMatchers("/docs").permitAll()`. Anonymous truy cập `/docs` có còn đi qua security filters không?

**Đáp án:** Có, nếu request được `SecurityFilterChain` bao phủ. `permitAll()` chỉ là kết quả ở bước authorization; nó không tự bỏ qua filter chain.

**Câu 3.** Tại sao `anonymous()` có thể từ chối một người đang đăng nhập dù cùng endpoint trả 200 cho khách?

**Đáp án:** `anonymous()` có nghĩa "chỉ cho người được nhận diện là anonymous", khác với `permitAll()` vốn cho mọi trạng thái.

**Câu 4.** Một chức năng cho phép cả remember-me nhưng một chức năng nhạy cảm yêu cầu xác thực đầy đủ. Hai quy tắc nào phù hợp?

**Đáp án:** `authenticated()` cho trường hợp đầu, `fullyAuthenticated()` cho trường hợp sau; nếu cần MFA/step-up còn phải thiết kế thêm.

**Câu 5.** `HttpServletRequest.getUserPrincipal()` trả `null`, còn `SecurityContextHolder` có token anonymous. Đây có nhất thiết là lỗi không?

**Đáp án:** Không. Servlet principal wrapper có thể ẩn anonymous principal, trong khi context vẫn dùng anonymous token nội bộ để thực thi các rule.

**Câu 6.** Một custom filter tự đặt một `Authentication` với `isAuthenticated=true` dựa trên header `X-User: admin` mà không xác minh nguồn gửi. Có an toàn không?

**Đáp án:** Không. Client có thể giả header; phải xác thực danh tính và thiết lập ranh giới tin cậy đúng cách trước khi đưa `Authentication` vào context.

## Kết luận

`AnonymousAuthenticationToken` giúp Spring Security Servlet biểu diễn người chưa đăng nhập bằng cùng abstraction `Authentication` được dùng cho các cơ chế xác thực khác. Điều này hữu ích cho filter chain và authorization, nhưng tạo ra bẫy: **token tồn tại hoặc có `isAuthenticated() == true` không đủ để khẳng định caller đã login**.

Trong code cần đọc trạng thái, hãy xử lý cả `null` và anonymous bằng `AuthenticationTrustResolver`. Trong chính sách bảo mật, ưu tiên `anonymous()`, `authenticated()`, `fullyAuthenticated()` và các rule quyền được Spring Security quản lý; đồng thời tiếp tục kiểm tra quyền đối với từng tài nguyên nghiệp vụ.
