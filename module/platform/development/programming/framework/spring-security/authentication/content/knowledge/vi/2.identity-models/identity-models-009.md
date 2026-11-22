# AnonymousAuthenticationToken, người dùng đã đăng nhập và AuthenticationTrustResolver

## 1. Cùng có `Authentication`, nhưng không cùng mức độ tin cậy

Trong ứng dụng Spring Security sử dụng Servlet, một request công khai có thể đi qua bộ lọc bảo mật mà **không có tài khoản nào đăng nhập**. Tuy vậy, sau khi đi qua `AnonymousAuthenticationFilter`, `SecurityContext` vẫn có thể chứa một đối tượng `Authentication`: `AnonymousAuthenticationToken`.

Đây là chỗ dễ nhầm nhất:

- Một token anonymous **thường trả `true` khi gọi trực tiếp `authentication.isAuthenticated()`**.
- Người dùng anonymous **vẫn chưa đăng nhập theo nghĩa xác thực danh tính**.
- `AuthenticationTrustResolver` được dùng để phân biệt anonymous, remember-me và danh tính đã xác thực, thay vì suy luận chỉ từ cờ `isAuthenticated()` của token.

Một ví dụ ngắn:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

boolean naive = authentication != null && authentication.isAuthenticated();

AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();
boolean actuallyLoggedIn = resolver.isAuthenticated(authentication);
```

Nếu `authentication` là `AnonymousAuthenticationToken` mặc định, `naive` có thể là `true` trong khi `actuallyLoggedIn` là `false`. Tên `isAuthenticated` ở **hai nơi** giống nhau nhưng tiêu chí khác nhau.

Bài này thuộc nhóm **Mô hình danh tính**, tập trung vào cách biểu diễn trạng thái danh tính trong Spring Security và cách kiểm tra đúng trạng thái đó. Các khái niệm xác thực username/password, session và phân quyền chỉ được nhắc khi giúp làm rõ anonymous/trust resolver.

## 2. Anonymous authentication là gì?

**Anonymous authentication** trong Spring Security là một cơ chế **biểu diễn khách chưa đăng nhập bằng một token có cấu trúc**. Nó cho phép các thành phần xử lý authorization hoặc audit nhìn thấy một principal/authority thống nhất trong `SecurityContext` thay vì luôn phải xử lý giá trị `null`.

Trong cấu hình mặc định phổ biến:

| Thuộc tính | `AnonymousAuthenticationToken` |
| --- | --- |
| Class | `org.springframework.security.authentication.AnonymousAuthenticationToken` |
| Principal | `anonymousUser` |
| Authorities | Thường có `ROLE_ANONYMOUS` |
| `isAuthenticated()` trên token | `true` |
| Danh tính đã được chứng minh? | **Chưa**; anonymous vẫn là khách chưa đăng nhập |
| `AuthenticationTrustResolver.isAnonymous(token)` | `true` |
| `AuthenticationTrustResolver.isAuthenticated(token)` | `false` |
| `AuthenticationTrustResolver.isFullyAuthenticated(token)` | `false` |

`anonymousUser` và `ROLE_ANONYMOUS` là các **giá trị mặc định có thể cấu hình**, không phải một tài khoản bắt buộc trong database, và không phải mật khẩu/mã định danh có thể dùng để đăng nhập.

Cụm từ “anonymous **authentication**” là tên cơ chế/đối tượng trong framework, **không có nghĩa** khách đã vượt qua kiểm tra mật khẩu, OIDC hoặc JWT. Spring Security dùng token này để mô hình hóa một chủ thể anonymous cho việc đánh giá policy.

### Vì sao `AnonymousAuthenticationToken.isAuthenticated()` lại là `true`?

Giao diện `Authentication` không tự định nghĩa “đã đăng nhập tương tác” dưới dạng một taxonomy tin cậy đầy đủ. Với token anonymous, đối tượng được tạo bởi bộ lọc nội bộ như một token **đã được framework xác lập là đại diện anonymous**, nên cờ trên chính token có thể là `true`. Chính vì vậy Spring Security phải dùng **kiểm tra loại/mức tin cậy**, đặc biệt qua `AuthenticationTrustResolver`, để biết nó có đại diện người dùng đăng nhập thực hay không.

Không nên cố sửa `AnonymousAuthenticationToken` bằng cách gọi `setAuthenticated(false)` rồi kết luận đã giải quyết vấn đề. Cách đúng là đặt quy tắc authorization và kiểm tra loại danh tính phù hợp.

## 3. Cách `AnonymousAuthenticationFilter` tạo token

Trong chuỗi bảo mật Servlet thông thường, các cơ chế đăng nhập (ví dụ HTTP Basic, form login, bearer token, remember-me nếu cấu hình) được xử lý. **Khi tới `AnonymousAuthenticationFilter` mà `SecurityContext` chưa có `Authentication`**, bộ lọc đặt một `AnonymousAuthenticationToken` vào ngữ cảnh của request.

```text
HTTP request
    |
    v
Spring Security filter chain
    |
    +--> Cơ chế xác thực đã cấu hình
    |      |
    |      +--> Thành công: context có Authentication thật
    |      |
    |      +--> Chưa có Authentication được thiết lập
    |                 |
    |                 v
    |        AnonymousAuthenticationFilter
    |                 |
    |                 +--> tạo AnonymousAuthenticationToken
    |                       principal = "anonymousUser"
    |                       authorities = [ROLE_ANONYMOUS]
    |                       token.isAuthenticated() = true
    v
AuthorizationFilter / kiểm tra quyền
    |
    v
Controller hoặc phản hồi từ chối/chuyển tới login
```

Điểm cần lưu ý:

1. **Filter không đi tìm người dùng anonymous trong database.** Nó tạo một biểu diễn mặc định để toàn chuỗi có thể làm việc thống nhất với `Authentication`.
2. **Filter không thay thế người đã đăng nhập.** Nếu context đã có authentication thích hợp, bộ lọc không tự ghi đè thành anonymous.
3. **Cơ chế có thể tùy chỉnh hoặc tắt.** Nếu tắt anonymous, hoặc đang ở điểm xử lý khác ngoài chuỗi filter, `SecurityContext.getAuthentication()` vẫn có thể là `null`.
4. **Có `AnonymousAuthenticationProvider` tương ứng** trong cấu hình hỗ trợ anonymous để nhận diện token được tạo bởi cơ chế này. Giá trị `key` chung giữa filter và provider chỉ có mục đích quản lý nội bộ, **không được coi là bí mật hay biện pháp xác minh danh tính client**.
5. **Đừng tự tạo anonymous token từ input HTTP** hoặc coi `ROLE_ANONYMOUS` là quyền người dùng thực được cấp qua đăng nhập.

Ví dụ về sự khác biệt:

- `GET /landing` mở công khai: khách không gửi credentials; sau bộ lọc anonymous, context có thể chứa token anonymous; request được phép nếu policy cho phép.
- `GET /account` yêu cầu `authenticated()`: context anonymous **không đủ**; framework yêu cầu cơ chế đăng nhập phù hợp.
- `GET /account` sau đăng nhập hợp lệ: context chứa authentication đại diện principal thực, ví dụ `UsernamePasswordAuthenticationToken` đã được xác thực hoặc token tương ứng OIDC/JWT.

## 4. `AuthenticationTrustResolver`: hỏi đúng câu hỏi

`AuthenticationTrustResolver` là interface trong gói `org.springframework.security.authentication`. Triển khai tiêu chuẩn là `AuthenticationTrustResolverImpl`.

Bốn phép kiểm tra quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isAnonymous(authentication)` | Đối tượng có biểu diễn người dùng anonymous theo resolver không? |
| `isRememberMe(authentication)` | Đối tượng có biểu diễn đăng nhập khôi phục bằng remember-me theo resolver không? |
| `isAuthenticated(authentication)` | Đối tượng tồn tại, có cờ xác thực của token và **không phải anonymous** hay không? |
| `isFullyAuthenticated(authentication)` | Có được xác thực theo phép trên và **không phải remember-me** hay không? |

Ở Spring Security 6.5, hai phương thức cuối là các **default method** của interface; cách đánh giá thực tế dùng các phép kiểm tra `isAnonymous` và `isRememberMe`. `AuthenticationTrustResolverImpl` mặc định nhận diện các loại token thích hợp; nếu hệ thống dùng custom authentication token không theo phân loại này, cần xem lại chiến lược xác định mức tin cậy thay vì đoán từ tên principal.

### Ma trận kết quả cần nhớ

| Tình trạng trong ngữ cảnh | Token có thể gặp | `token.isAuthenticated()` | `resolver.isAnonymous` | `resolver.isRememberMe` | `resolver.isAuthenticated` | `resolver.isFullyAuthenticated` |
| --- | --- | --- | --- | --- | --- | --- |
| Chưa có token | `null` | Không gọi được | false | false | false | false |
| Yêu cầu username/password chưa kiểm chứng | `UsernamePasswordAuthenticationToken.unauthenticated(...)` | false | false | false | false | false |
| Khách anonymous | `AnonymousAuthenticationToken` | **true** | **true** | false | **false** | false |
| Được nhớ qua remember-me | `RememberMeAuthenticationToken` | true | false | **true** | **true** | false |
| Đăng nhập hợp lệ theo cơ chế bình thường | Token đã xác thực, không anonymous/remember-me | true | false | false | **true** | **true** |

Bảng này mô tả **các kiểu token chuẩn**; một lớp tùy biến có thể cần cấu hình resolver riêng. Token “yêu cầu username/password chưa kiểm chứng” là đối tượng dùng trong quá trình xác thực, không phải trạng thái mà ứng dụng nên lưu làm danh tính hiện hành.

Chú ý hai điều:

- `resolver.isAnonymous(null)` là `false`, nhưng không có nghĩa `null` đại diện cho người đã đăng nhập. `resolver.isAuthenticated(null)` và `isFullyAuthenticated(null)` vẫn là `false`.
- `resolver.isAuthenticated(rememberMeToken)` có thể là `true`. Khi yêu cầu chứng thực mạnh hơn, dùng `fullyAuthenticated()` theo policy. **Fully authenticated ở đây không đồng nghĩa đã bật MFA**; nó chỉ phân biệt anonymous và remember-me trong mô hình tin cậy của Spring Security.

## 5. Remember-me khác anonymous và đăng nhập đầy đủ

`RememberMeAuthenticationToken` thường xuất hiện khi ứng dụng bật remember-me và khôi phục danh tính người dùng từ cookie theo cơ chế đã cấu hình. Nó **không phải anonymous**: framework đã thực hiện một quá trình xác thực remember-me, và token thường chứa principal cùng authorities tương ứng.

Tuy nhiên, remember-me không tương đương một phiên xác thực mới bằng credentials đầy đủ. Với thao tác nhạy cảm (đổi mật khẩu, xác nhận thanh toán, thay khóa bảo mật), ứng dụng có thể yêu cầu **đăng nhập lại** hoặc bước xác minh mạnh hơn.

So sánh:

| Tình huống | `authenticated()` | `fullyAuthenticated()` |
| --- | --- | --- |
| Khách anonymous | Không đạt | Không đạt |
| Remember-me hợp lệ | Đạt | Không đạt |
| Danh tính đã xác thực bình thường | Đạt | Đạt |

Cần nhớ rằng việc một token được xem “fully authenticated” **không tự chứng minh** người dùng vừa nhập mật khẩu, đã vượt MFA hay đạt mức xác thực cao theo tiêu chuẩn nghiệp vụ. Ví dụ một `JwtAuthenticationToken` không được phân loại anonymous/remember-me có thể vượt qua `fullyAuthenticated()`; nếu API yêu cầu MFA/step-up phải có policy kiểm chứng claim, `acr`/`amr` hoặc cơ chế riêng phù hợp.

## 6. Chương trình Java 17+ chạy được: quan sát năm trạng thái

Đây là ví dụ **console độc lập**, dùng Spring Security 6.5.11 và Java 17+. Chương trình xây một tài khoản trong bộ nhớ và xác thực thật bằng `DaoAuthenticationProvider` cho trạng thái logged-in. Riêng hai token anonymous và remember-me được **tạo thủ công chỉ để minh họa cách resolver phân loại token**, không thực hiện quy trình HTTP/cookie/remember-me thật.

Cấu trúc:

```text
trust-resolver-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TrustResolverDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'trust-resolver-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.TrustResolverDemo'
}
```

`src/main/java/demo/TrustResolverDemo.java`:

```java
package demo;

import java.util.List;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class TrustResolverDemo {

    public static void main(String[] args) {
        AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

        // Không có Authentication (có thể gặp khi anonymous bị tắt).
        Authentication missing = null;

        // Lời yêu cầu xác thực: chưa có bằng chứng đã được xác minh.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        // Token giả lập để xem resolver phân loại, không phải HTTP login.
        Authentication anonymous = new AnonymousAuthenticationToken(
                "demo-key",
                "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

        // Token mô phỏng trạng thái remember-me đã được tạo bởi cơ chế tin cậy.
        // Không dùng constructor này để tự cấp quyền từ dữ liệu client.
        Authentication remembered = new RememberMeAuthenticationToken(
                "demo-key",
                "lan",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

        // Một lần xác thực username/password thật bằng provider.
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails user = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();
        UserDetailsService users = new InMemoryUserDetailsManager(user);
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        Authentication loggedIn = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        show("missing", missing, resolver);
        show("request", request, resolver);
        show("anonymous", anonymous, resolver);
        show("rememberMe", remembered, resolver);
        show("loggedIn", loggedIn, resolver);

        // Có Authentication trong SecurityContext != đã đăng nhập.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(anonymous);
        SecurityContextHolder.setContext(context);
        try {
            Authentication current = SecurityContextHolder.getContext()
                    .getAuthentication();
            System.out.println("context.hasToken=" + (current != null));
            System.out.println("context.loggedIn=" + resolver.isAuthenticated(current));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void show(
            String label,
            Authentication token,
            AuthenticationTrustResolver resolver) {

        boolean present = token != null;
        boolean raw = present && token.isAuthenticated();

        System.out.printf(
                "%s: present=%s raw=%s anonymous=%s rememberMe=%s authenticated=%s fully=%s%n",
                label,
                present,
                raw,
                resolver.isAnonymous(token),
                resolver.isRememberMe(token),
                resolver.isAuthenticated(token),
                resolver.isFullyAuthenticated(token));
    }
}
```

Chạy với JDK 17+ và Gradle hỗ trợ Java 17, tại thư mục chứa `build.gradle`:

```bash
gradle run --quiet
```

Đây là **stdout do chương trình in ra**, không bao gồm log có thể xuất hiện từ môi trường Gradle:

```text
missing: present=false raw=false anonymous=false rememberMe=false authenticated=false fully=false
request: present=true raw=false anonymous=false rememberMe=false authenticated=false fully=false
anonymous: present=true raw=true anonymous=true rememberMe=false authenticated=false fully=false
rememberMe: present=true raw=true anonymous=false rememberMe=true authenticated=true fully=false
loggedIn: present=true raw=true anonymous=false rememberMe=false authenticated=true fully=true
context.hasToken=true
context.loggedIn=false
```

### Giải thích chính xác kết quả

- **`missing`:** không có token. Không thể gọi `missing.isAuthenticated()`; chương trình có kiểm tra null trước. Resolver nhận `null` và trả false cho các kiểm tra trên.
- **`request`:** chứa username/password chưa được chứng minh. `raw=false` và không phải người dùng đã đăng nhập.
- **`anonymous`:** `raw=true` gây nhầm lẫn nếu chỉ nhìn cờ. Resolver nhận ra `AnonymousAuthenticationToken` và trả `authenticated=false`.
- **`rememberMe`:** hai giá trị `raw` và `authenticated` là true, nhưng `fully=false`. Trong chương trình này token được tạo thủ công để quan sát phân loại; nó **không chứng minh** cookie remember-me nào hợp lệ.
- **`loggedIn`:** được tạo từ kết quả `manager.authenticate(...)` qua provider có kiểm tra mật khẩu BCrypt hash, nên `authenticated=true` và `fully=true` theo phân loại mặc định.
- **`context.hasToken=true` nhưng `context.loggedIn=false`:** chứng minh sự tồn tại của `Authentication` trong `SecurityContext` không đồng nghĩa với xác thực tài khoản.

Đừng đưa đoạn tạo `RememberMeAuthenticationToken` thủ công vào luồng xác thực sản phẩm. Trong ứng dụng thật, chính remember-me filter/provider, cấu hình cookie, kiểm tra token và chính sách bảo mật phải quyết định khi nào được cấp một trạng thái remembered. Cũng không xây `UsernamePasswordAuthenticationToken.authenticated(...)` trực tiếp từ username/role do client gửi.

## 7. Phân biệt trong cấu hình bảo vệ URL

Trong Spring Security Servlet, các quy tắc dưới đây khác nhau dù đều liên quan tới “ai được vào”:

| Quy tắc | Ý nghĩa |
| --- | --- |
| `permitAll()` | Endpoint công khai, cho phép khách anonymous và người đã đăng nhập; không yêu cầu xác thực. |
| `anonymous()` | Chỉ cho phép đối tượng được nhận diện là anonymous; ví dụ trang đăng ký dành cho khách. |
| `authenticated()` | Yêu cầu danh tính đã xác thực, **không** nhận anonymous; remember-me có thể đạt điều kiện này. |
| `fullyAuthenticated()` | Yêu cầu danh tính xác thực, loại anonymous và remember-me. |
| `hasRole("READER")` / `hasAuthority("document:read")` | Kiểm tra quyền được cấp; **không thay thế** kiểm tra sở hữu tài nguyên nghiệp vụ. |
| `denyAll()` | Mặc định từ chối khi không có quy tắc cho phép phù hợp. |

Ví dụ **một trích đoạn cấu hình** trong ứng dụng Spring Boot Servlet đã khai báo web/security dependencies; đoạn này cần import `Bean`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`, không phải chương trình Java độc lập:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/register").anonymous()
            .requestMatchers("/profile/**").authenticated()
            .requestMatchers("/payments/confirm").fullyAuthenticated()
            .anyRequest().denyAll()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

Ứng dụng còn phải có chính sách user store, login và quyền phù hợp. Nếu chưa bật remember-me, rule `fullyAuthenticated()` vẫn hợp lệ nhưng chưa có dòng remember-me thực tế để so sánh. Việc một request bị 401/403 hay được redirect về trang đăng nhập còn tùy `AuthenticationEntryPoint` và `AccessDeniedHandler` đang cấu hình.

**Tình huống:** khách gọi `/profile/me`. `AnonymousAuthenticationFilter` có thể đã tạo token anonymous, nhưng `authenticated()` vẫn không cho qua. Khi `ExceptionTranslationFilter` xử lý trường hợp thiếu xác thực, nó có thể kích hoạt entry point để bắt đầu đăng nhập, thay vì coi token anonymous có `isAuthenticated=true` như một user thực và mặc định trả 403. Nếu user đã đăng nhập nhưng thiếu quyền khác, ứng dụng có thể trả 403 theo chính sách.

### Phân biệt `permitAll` và `anonymous`

`permitAll()` **không đồng nghĩa** “chỉ dành cho người chưa đăng nhập”: người có session hợp lệ vẫn truy cập được. Ngược lại, `anonymous()` là một chính sách chỉ cho khách, nên user đã đăng nhập có thể bị từ chối. Điều này hữu ích cho màn hình hướng dẫn đăng nhập/đăng ký, nhưng hãy cân nhắc UX: redirect user đã đăng nhập khỏi màn hình đăng ký thường là lựa chọn điều hướng của ứng dụng, không phải lý do tự nới lỏng policy endpoint nhạy cảm.

## 8. Đọc anonymous trong Spring MVC: một bẫy khác

Có sự khác nhau giữa **`SecurityContextHolder`** và **Servlet principal API** khi request là anonymous.

Trong Spring MVC, tham số handler kiểu `Authentication` hoặc `Principal` có thể được giải quyết qua `HttpServletRequest#getPrincipal()`. Với anonymous, Servlet API thường trả **`null`**, dù `SecurityContextHolder` đang chứa `AnonymousAuthenticationToken`. Vì vậy mẫu code sau **không đáng tin để phát hiện anonymous** trong Spring MVC:

```java
@GetMapping("/who-am-i")
String whoAmI(Authentication authentication) {
    return authentication instanceof AnonymousAuthenticationToken
        ? "anonymous"
        : "not anonymous";
}
```

Nó có thể trả `not anonymous` với request anonymous vì tham số `authentication` thực tế là `null`.

**Khi thực sự cần xem cả token anonymous trong controller**, Spring Security cung cấp `@CurrentSecurityContext`:

```java
// Trích đoạn trong @RestController có Spring Security MVC integration.
// Import: GetMapping, CurrentSecurityContext, SecurityContext,
// Authentication, AuthenticationTrustResolver, AuthenticationTrustResolverImpl.
@GetMapping("/who-am-i")
String whoAmI(@CurrentSecurityContext SecurityContext context) {
    Authentication token = context.getAuthentication();
    AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

    if (resolver.isAnonymous(token)) {
        return "anonymous";
    }
    if (!resolver.isAuthenticated(token)) {
        return "missing-or-unauthenticated";
    }
    return resolver.isFullyAuthenticated(token)
        ? "fully-authenticated"
        : "remember-me";
}
```

Đây là cách minh họa **quan sát trạng thái**, không phải lý do kiểm tra mọi request trong controller để phân quyền. Chính sách URL và method security nên xử lý truy cập. Trong hệ thống custom authentication, cách cuối cùng có thể phân loại remembered tùy resolver; câu trả lời `remember-me` ở ví dụ giả định cơ chế mặc định.

Khi chuyển sang asynchronous execution, thread pool hoặc reactive stack, đừng lấy context từ một thread tùy ý mà giả định nó mang danh tính của request ban đầu. Mô hình truyền context phụ thuộc runtime; đoạn controller trên nói về **Servlet/Spring MVC**.

## 9. Khi nào nên dùng `AuthenticationTrustResolver` trực tiếp?

Phần lớn ứng dụng chỉ cần **DSL authorization**: `permitAll()`, `authenticated()`, `fullyAuthenticated()`, `anonymous()`, `hasRole()`. Đây là nơi diễn đạt chính sách an ninh rõ ràng, thay vì rải điều kiện trong controller.

`AuthenticationTrustResolver` trực tiếp hữu ích khi:

1. Xây một thành phần **audit/logging** cần biết request hiện tại là anonymous, remembered hay authenticated mà không lưu secrets.
2. Phát triển một custom `AuthorizationManager` hoặc thành phần bảo mật cần phân biệt mức tin cậy.
3. Trả trạng thái người dùng trong endpoint kiểm tra phiên, với contract rõ ràng về anonymous/remember-me và khả năng context rỗng.
4. Đọc luồng xử lý lỗi 401/403 hoặc entry point, nơi việc nhận diện anonymous ảnh hưởng cách hệ thống đề nghị người dùng đăng nhập.

Ví dụ phân loại thuần Java:

```java
// Hàm minh họa, dùng cùng AuthenticationTrustResolver chuẩn.
String category(Authentication token, AuthenticationTrustResolver trust) {
    if (token == null) {
        return "missing";
    }
    if (trust.isAnonymous(token)) {
        return "anonymous";
    }
    if (trust.isRememberMe(token)) {
        return "remember-me";
    }
    if (trust.isFullyAuthenticated(token)) {
        return "fully-authenticated";
    }
    return "not-authenticated";
}
```

Không dùng `authentication.getName().equals("anonymousUser")` để phân biệt: tên có thể cấu hình hoặc trùng với một tên người dùng thực. Không dùng `getAuthorities().contains("ROLE_ANONYMOUS")` theo kiểu so chuỗi thô: authorities là các `GrantedAuthority`, role có thể cấu hình, và quyền do client tự khai không là bằng chứng. Resolver biểu đạt đúng mục đích phân loại trạng thái.

## 10. Những sai lầm dễ tạo lỗ hổng

**Sai lầm A — “Có `Authentication` nghĩa là đã login.”** Anonymous filter cố ý tạo token trong context. Thay kiểm tra tồn tại bằng resolver hoặc policy thích hợp.

**Sai lầm B — “Cờ `Authentication.isAuthenticated()` luôn đủ.”** Anonymous token có thể trả true. Dùng `AuthenticationTrustResolver.isAuthenticated(...)` hoặc DSL `authenticated()` cho nhu cầu nhận biết user đã được xác thực.

**Sai lầm C — “`anonymousUser` là tài khoản trong kho danh tính.”** Đây chỉ là principal mặc định của biểu diễn anonymous. Đừng tạo user thật `anonymousUser` để “sửa” hành vi hoặc dùng tên này làm khóa sở hữu dữ liệu.

**Sai lầm D — “`ROLE_ANONYMOUS` là bằng chứng client có thể gửi.”** Cơ chế phải do server quản lý; client không được tự định nghĩa authorities của mình. Không dùng key của anonymous provider làm ranh giới bảo mật.

**Sai lầm E — “Remember-me tương đương đăng nhập đầy đủ.”** `resolver.isAuthenticated(...)` có thể true cho remember-me, nhưng `isFullyAuthenticated(...)` false. Áp dụng step-up/re-login ở các hành động rủi ro.

**Sai lầm F — “`fullyAuthenticated()` tự bảo đảm MFA.”** Spring Security chỉ xác định không anonymous/remember-me theo resolver chuẩn; đừng đánh đồng nó với mức độ bảo đảm danh tính, MFA hoặc xác thực lại gần đây.

**Sai lầm G — “Một endpoint `permitAll()` là endpoint chỉ dành khách.”** `permitAll` chấp nhận cả người đăng nhập. Muốn hạn chế chỉ anonymous hãy diễn đạt riêng, và chú ý UX của người đã đăng nhập.

**Sai lầm H — “Có thể lấy token anonymous bằng tham số `Authentication` của Spring MVC.”** Do tích hợp Servlet principal, đối tượng ở tham số có thể null. Dùng `@CurrentSecurityContext` khi cần quan sát token anonymous thực sự.

**Sai lầm I — “Không có token thì `resolver.isAnonymous(null)` phải true.”** Resolver trả false cho null; không có token và token anonymous là hai trạng thái khác nhau. Cả hai **không** đại diện người dùng đã đăng nhập.

**Sai lầm J — tự sinh token `authenticated` từ JSON/form.** Dùng `AuthenticationManager` và provider phù hợp để kiểm chứng. Các constructor trong demo chỉ dùng để minh họa cách phân loại, không cấp đăng nhập sản phẩm.

## 11. Tự kiểm tra

**Câu 1.** Trên một request không gửi credential, context có `AnonymousAuthenticationToken` với `isAuthenticated()==true`. Người dùng đã đăng nhập chưa?

**Đáp án:** Chưa. `AuthenticationTrustResolver.isAnonymous(token)` trả true, `isAuthenticated(token)` của resolver trả false.

**Câu 2.** Tại sao trang `/public` vẫn có thể hoạt động khi không có user thật?

**Đáp án:** Policy `permitAll()` cho phép request công khai; anonymous filter có thể cung cấp representation cho context. Không cần tài khoản DB hay đăng nhập.

**Câu 3.** Token remember-me đi qua `authenticated()` được không? Còn `fullyAuthenticated()`?

**Đáp án:** Theo phân loại chuẩn, `authenticated()` cho phép remember-me; `fullyAuthenticated()` loại nó.

**Câu 4.** `isFullyAuthenticated(token) == true` đã chứng minh có MFA chưa?

**Đáp án:** Chưa. Nó chỉ loại trừ anonymous/remember-me theo resolver, không tự xác minh yếu tố MFA hay độ mới của lần xác thực.

**Câu 5.** Trong Spring MVC, muốn xem `AnonymousAuthenticationToken` hiện tại nên dùng tham số controller nào?

**Đáp án:** `@CurrentSecurityContext SecurityContext context` để lấy `context.getAuthentication()`; tham số `Authentication` do MVC resolve từ Servlet principal có thể null khi anonymous.

**Câu 6.** Khác biệt giữa `null` và token anonymous?

**Đáp án:** Null là không có authentication object. Token anonymous là một object do framework tạo để biểu diễn guest; resolver nhận ra loại anonymous. Trong cả hai trường hợp, `isAuthenticated(...)` của resolver trả false.

## 12. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html): lý do có token anonymous, filter, provider, trust resolver và chi tiết Spring MVC.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext` và luồng xác thực.
- [AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): contract của `isAnonymous`, `isRememberMe`, `isAuthenticated`, `isFullyAuthenticated`.
- [AuthenticationTrustResolverImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolverImpl.html): triển khai mặc định dựa trên loại token.
- [AnonymousAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AnonymousAuthenticationToken.html): constructor, principal, authorities và cờ trạng thái.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): các chính sách kiểm soát truy cập HTTP.

**Kết luận:** `AnonymousAuthenticationToken` giúp biểu diễn khách chưa đăng nhập trong `SecurityContext`, nhưng không chứng minh danh tính. Dùng `AuthenticationTrustResolver` để hỏi chính xác “đây có phải anonymous/remember-me/người dùng đã xác thực không?”, và dùng các quy tắc authorization để quyết định quyền truy cập. Một token tồn tại, hoặc cờ `isAuthenticated` trên token là true, chưa đủ để kết luận người dùng đã đăng nhập thật.