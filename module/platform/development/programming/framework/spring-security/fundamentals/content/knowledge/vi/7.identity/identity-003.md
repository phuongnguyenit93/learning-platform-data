# Ý nghĩa của getPrincipal, getCredentials, getAuthorities và isAuthenticated

> **Ngữ cảnh:** Spring Security cho Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học tập trung vào bốn phương thức của interface `Authentication`: giá trị và kiểu dữ liệu của chúng, sự khác biệt trước/sau khi xác thực, anonymous authentication, mối liên hệ với phân quyền và cách sử dụng đúng trong code/test. Ví dụ chính dùng HTTP Basic để thấy rõ luồng xác thực; các cơ chế JWT/OAuth2 được so sánh khi cần.

## 1. Authentication vừa là yêu cầu, vừa là kết quả xác thực

Một đối tượng `Authentication` có thể biểu diễn **yêu cầu xác thực chưa được kiểm tra** hoặc **kết quả đã được một provider tin cậy xác minh**. Đây là lý do ta không thể chỉ thấy một `Authentication` rồi kết luận người gọi đã đăng nhập.

Với HTTP Basic, luồng điển hình:

~~~text
HTTP request:
    Authorization: Basic <Base64(username:password)>
                      |
                      v
          BasicAuthenticationFilter
                      |
                      v
    UsernamePasswordAuthenticationToken (request)
    principal       = "alice"
    credentials     = mật khẩu do client gửi
    authorities     = []
    isAuthenticated = false
                      |
                      v
            AuthenticationManager
                      |
                      v
            DaoAuthenticationProvider
            + UserDetailsService
            + PasswordEncoder
            + account status checks
                      |
                      v
      UsernamePasswordAuthenticationToken (result)
    principal       = UserDetails của alice
    credentials     = thường được xóa sau xác thực
    authorities     = [ROLE_USER, report:read]
    isAuthenticated = true
                      |
                      v
             SecurityContextHolder
                      |
                      v
          AuthorizationFilter / method security
                      |
                 ALLOW / DENY
~~~

AuthenticationManager thường điều phối việc xác thực đến provider phù hợp; provider đọc dữ liệu tài khoản và kiểm tra credential. Sau khi thành công, **SecurityContext** của request được cập nhật để filter, controller và service có thể đọc thông tin chủ thể hiện tại.

Các khái niệm cần phân biệt:

- **Authentication:** ai đang yêu cầu xác thực, hoặc một kết quả xác thực đã được framework thiết lập.
- **Principal:** danh tính được đại diện bằng object nào.
- **Credentials:** bằng chứng được dùng để xác minh danh tính, có thể nhạy cảm.
- **Authorities:** những quyền cấp cao được gắn với Authentication.
- **Authorization:** có được phép thực hiện một action trên một resource cụ thể hay không.

**Đã được xác thực không tự có nghĩa được phép truy cập mọi endpoint.** Một tài khoản có `ROLE_USER` không tự vượt qua rule `hasRole("ADMIN")`.

## 2. Bảng tổng quan bốn phương thức

| Phương thức | Câu hỏi chính | Giá trị điển hình | Không nên suy diễn |
| --- | --- | --- | --- |
| `getPrincipal()` | Ai được nhận diện? | String, UserDetails, Jwt, OAuth2User, principal của dự án | Luôn là username String hoặc UserDetails |
| `getCredentials()` | Bằng chứng xác thực là gì? | Password, access token, object credential; có thể null | Luôn chứa password ngay cả sau khi đăng nhập |
| `getAuthorities()` | Những quyền đã được cấp cho authentication? | Collection của GrantedAuthority: ROLE_USER, report:read, SCOPE_orders.read | Có quyền đối với mọi tài nguyên có cùng loại |
| `isAuthenticated()` | Implementation đánh dấu authentication đã được xác thực chưa? | true/false | true tương đương user thật, đủ quyền và đã làm MFA |

`Authentication` thuộc `org.springframework.security.core` và kế thừa `java.security.Principal`. Trích các chữ ký quan trọng:

~~~java
// Chỉ là chữ ký minh họa; không phải interface đầy đủ để biên dịch.
Object getPrincipal();
Object getCredentials();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isAuthenticated();
void setAuthenticated(boolean authenticated);

String getName();      // từ java.security.Principal
Object getDetails();
~~~

Hai điểm từ contract:

1. `getPrincipal()` và `getCredentials()` trả `Object`, nên kiểu thực tế thay đổi theo Authentication implementation. Không cast cố định nếu API có thể dùng nhiều loại xác thực.
2. `getAuthorities()` trả collection (không nên là null). Với token username/password **chưa được xác thực**, collection thường rỗng. Một Authentication đáng tin cậy có authorities được provider hoặc converter phù hợp thiết lập.

`getDetails()` có thể chứa thông tin phụ như địa chỉ từ xa hoặc session ID. Nó không phải danh sách quyền, không thay thế principal và không nên được tự động trả nguyên dạng ra HTTP response.

## 3. getPrincipal(): object đại diện danh tính

### 3.1. Trước khi xác thực

Khi client gửi username/password, filter thường dựng một token dạng:

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice",
        "alice123"
    );

Object principal = attempt.getPrincipal(); // String "alice"
~~~

Đây là **snippet** trong chương trình có Spring Security dependency/import. Nó cho thấy tên người dùng được client khai báo, **chưa chứng minh client là alice**.

### 3.2. Sau khi xác thực

Với `DaoAuthenticationProvider`, `UserDetailsService` tìm tài khoản và provider xác minh credential. Authentication trả về thường có principal là `UserDetails`, ví dụ implementation `org.springframework.security.core.userdetails.User`. Khi đó `getPrincipal()` không còn chỉ là String.

~~~text
Trước xác thực:
    type = UsernamePasswordAuthenticationToken
    principal = String "alice"
    isAuthenticated() = false

Sau xác thực:
    type = UsernamePasswordAuthenticationToken
    principal = UserDetails(alice)
    isAuthenticated() = true
~~~

Không có quy tắc rằng mọi provider đều phải trả UserDetails; một provider có thể dùng `String` hoặc principal tự định nghĩa.

### 3.3. Principal thay đổi theo authentication mechanism

| Kiến trúc | Authentication thường gặp | Principal thường gặp |
| --- | --- | --- |
| HTTP Basic/form login + DaoAuthenticationProvider | UsernamePasswordAuthenticationToken | UserDetails hoặc String |
| Anonymous authentication | AnonymousAuthenticationToken | Chuỗi `"anonymousUser"` theo mặc định |
| OAuth2 Resource Server JWT | JwtAuthenticationToken | Jwt đã qua decoder/validator |
| OAuth2 Login / OIDC | OAuth2AuthenticationToken | OAuth2User hoặc OidcUser |
| Opaque access token | Authentication phù hợp Resource Server | OAuth2AuthenticatedPrincipal |
| Custom authentication | Class của hệ thống | Principal riêng do provider xác minh |

Đoạn sau có thể gây lỗi khi đổi từ username/password sang JWT:

~~~java
// Chỉ dùng nếu biết chắc principal là UserDetails:
UserDetails user = (UserDetails) authentication.getPrincipal();
~~~

Với code chỉ cần định danh:

~~~java
String name = authentication.getName();
~~~

`getName()` tiện dụng, nhưng trong hệ thống thật **tên đăng nhập chưa chắc là ID bền vững**. Username/email có thể đổi; JWT subject có thể phụ thuộc issuer; nhiều tenant có thể có user trùng tên. Nếu kiểm tra chủ sở hữu tài nguyên, hãy ánh xạ principal đã được xác minh thành **accountId/tenantId đáng tin cậy** theo policy của ứng dụng.

### 3.4. @AuthenticationPrincipal

Trong Spring MVC, có thể nhận principal trực tiếp:

~~~java
@GetMapping("/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Đoạn trích phù hợp nếu cơ chế xác thực bảo đảm principal là `UserDetails`. Với Resource Server JWT, kiểu tham số có thể là `Jwt`:

~~~java
@GetMapping("/jwt-subject")
public String jwtSubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

Đây là hai **snippet thuộc hai kiến trúc khác nhau**; không đưa controller JWT vào demo HTTP Basic rồi mong Spring tự cấp Jwt.

**Không trả nguyên `UserDetails` hoặc `Jwt` thành JSON** vì có thể lộ password hash, claim nhạy cảm hoặc metadata nội bộ. Nên tạo DTO chỉ gồm những trường API thực sự cần.

## 4. getCredentials(): bằng chứng xác thực

`getCredentials()` cho biết dữ liệu chứng minh principal là ai. Với Basic/form login, đó thường là raw password trước khi xác thực. Với Bearer hoặc phương thức khác, credentials có thể chứa token hoặc object chuyên biệt.

### 4.1. Credential trước xác thực

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "demo-password"
    );

Object principal = attempt.getPrincipal();        // "alice"
Object credentials = attempt.getCredentials();    // "demo-password"
boolean authenticated = attempt.isAuthenticated();// false
~~~

Snippet dùng credential giả chỉ để học. **Không in password hoặc access token thật vào log, response, test report hoặc hệ thống analytics**.

Raw password từ client phải đi qua **HTTPS/TLS** trên mạng không tin cậy. HTTP Basic trình bày username/password dưới dạng Base64, **Base64 không bảo mật bí mật**.

### 4.2. PasswordEncoder khác getCredentials

`UserDetails.getPassword()` thường trả **encoded password/hash đã lưu trong database**. Provider so khớp raw password với hash:

~~~java
boolean valid = passwordEncoder.matches(
    rawPasswordFromRequest,
    userDetails.getPassword()
);
~~~

Đây là snippet để giải thích cơ chế provider, không phải code nên viết trong controller. `Authentication.getCredentials()` nói về credential của request, **không đồng nghĩa hash lưu trong DB**. Không dùng `raw.equals(storedHash)` và không mã hóa lại hash sau mỗi lần đọc account.

### 4.3. Sau xác thực, credentials thường được xóa

`ProviderManager` điển hình bật `eraseCredentialsAfterAuthentication`. Khi xác thực thành công, nó cố xóa bí mật trên Authentication và những object liên quan triển khai `CredentialsContainer` để giảm thời gian tồn tại của password.

Bởi vậy khi Controller đọc:

~~~java
Object credentials = authentication.getCredentials();
~~~

kết quả **có thể là null** hoặc đã được xóa/biến đổi tùy implementation. **Null không chứng minh login thất bại.** Ngược lại, cũng không được khẳng định mọi loại Authentication sau login đều có credentials null.

Không xây logic như “nếu credentials null thì chưa đăng nhập”. Hãy dùng cơ chế xác thực và authorization của Spring Security. Việc xóa credentials chỉ ảnh hưởng object bộ nhớ, không xóa password hash bền vững trong database.

### 4.4. Tình huống cache UserDetails

Một số `UserDetails` triển khai `CredentialsContainer`. Nếu cùng một object được dùng trong cache và làm principal Authentication, việc xóa password trên principal có thể ảnh hưởng object đang nằm trong cache.

Khi dùng UserCache hoặc cache tùy chỉnh, phải hiểu vòng đời/reference, có thể cần copy object phù hợp trước khi đưa qua provider. Không tắt cơ chế xóa credential chỉ để chữa lỗi cache mà chưa cân nhắc an toàn thông tin.

### 4.5. Vì sao không trả Authentication trực tiếp?

Phản ví dụ:

~~~java
// Không dùng trong production:
log.info("credentials={}", authentication.getCredentials());
return authentication; // Serialize nguyên object
~~~

Nó có thể làm lộ password/token hoặc metadata không cần thiết. Ngay cả khi credentials đã bị xóa, principal/authorities/details có thể mang thông tin không dành cho client. Hãy chọn DTO với trường công khai đã được phê duyệt.

## 5. getAuthorities(): quyền được gắn với Authentication

`getAuthorities()` trả `Collection<? extends GrantedAuthority>`. Các giá trị phổ biến:

~~~text
ROLE_USER
ROLE_ADMIN
report:read
invoice:approve
SCOPE_orders.read
~~~

Với authority đơn giản, `GrantedAuthority.getAuthority()` trả chuỗi thể hiện quyền. Ví dụ:

~~~java
List<String> authorities = authentication.getAuthorities().stream()
    .map(GrantedAuthority::getAuthority)
    .sorted()
    .toList();
~~~

Đoạn trích cần biến Authentication và import `List`, `GrantedAuthority`. Một authority phức tạp có thể trả null từ `getAuthority()`, nên code xử lý mọi implementation cần lưu ý. Demo chỉ dùng `SimpleGrantedAuthority` có chuỗi không null.

### 5.1. Role và authority

| Policy của Spring Security | Yêu cầu theo convention mặc định |
| --- | --- |
| `hasRole("ADMIN")` | Authority `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Authority chính xác `ROLE_ADMIN` |
| `hasAuthority("report:read")` | Authority chính xác `report:read` |
| `hasAuthority("SCOPE_orders.read")` | Authority chính xác `SCOPE_orders.read` |

Builder `User.withUsername(...).roles("USER")` tự thêm prefix `ROLE_`. Builder `.authorities("report:read")` dùng chuỗi đúng như truyền. Với JWT, scopes thường được ánh xạ sang authority có tiền tố `SCOPE_` theo converter.

**Role là một kiểu biểu diễn authority**, không phải username. Tài khoản có tên “admin” không tự có `ROLE_ADMIN`.

### 5.2. Authorities của request token chưa xác thực

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "not-verified-yet"
    );

// attempt.getAuthorities().isEmpty() == true
// attempt.isAuthenticated() == false
~~~

Quyền phải đến từ nguồn đã được kiểm tra, chẳng hạn UserDetailsService đáng tin cậy hoặc token đã được validator xử lý. Không lấy role do request body tự khai rồi gắn vào một Authentication được coi đã xác thực.

Đoạn phản ví dụ sau **không được dùng để đăng nhập**:

~~~java
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        usernameFromClient,
        passwordFromClient,
        List.of(new SimpleGrantedAuthority(roleFromClient))
    );
~~~

Factory `authenticated(...)` tạo một object đã đánh dấu tin cậy. Chỉ code/provider đủ thẩm quyền sau khi xác minh credential và quyền mới được tạo kết quả như thế, **không tạo từ claims/roles do client tự gửi mà chưa xác minh**.

### 5.3. Authorities chưa thay policy theo resource

Có `report:read` chưa chứng minh user được đọc một báo cáo của tenant khác. Một rule domain thường phải kiểm tra:

~~~text
ALLOW khi và chỉ khi:
    identity đã được xác minh theo yêu cầu
    AND được cấp authority cho action
    AND resource thuộc phạm vi owner/tenant được cho phép
    AND trạng thái nghiệp vụ/các điều kiện bắt buộc thỏa mãn
~~~

Kiểm tra URL chung và kiểm tra bản ghi cụ thể là hai việc khác nhau. BOLA/IDOR có thể xuất hiện nếu API chỉ kiểm tra role rồi tin ID tài nguyên trong URL.

### 5.4. Quyền có thể bị cũ trong session/JWT

`getAuthorities()` không tự luôn truy vấn database. Với session, Authentication có thể giữ quyền từ lần login; với JWT, quyền có thể được phát vào token và giữ nguyên cho đến khi token hết hạn/thu hồi; provider/cache cũng có thể giữ dữ liệu cũ.

Nếu khóa user hoặc đổi role cần có hiệu lực tức thì, thiết kế session invalidation, token revocation, revalidation và domain policy tương ứng.

## 6. isAuthenticated(): cờ trạng thái dễ gây hiểu nhầm

Với username/password:

~~~text
UsernamePasswordAuthenticationToken.unauthenticated(...)
    -> isAuthenticated() == false

Authentication do provider xác minh thành công
    -> isAuthenticated() == true
~~~

Tuy vậy, **raw flag true không tự tương đương đã đăng nhập bằng một tài khoản thật, không đồng nghĩa MFA và không có nghĩa có quyền vào endpoint**.

### 6.1. AnonymousAuthenticationToken cũng có thể có flag true

`AnonymousAuthenticationFilter` trong Spring Security thường đặt một `AnonymousAuthenticationToken` vào SecurityContext khi request chưa có authentication user thực sự. Điều này cho framework một object đại diện anonymous nhất quán.

Với AnonymousAuthenticationToken mặc định, `isAuthenticated()` có thể **trả true**, nhưng Spring Security vẫn nhận diện được nó là anonymous bằng `AuthenticationTrustResolver`.

Ví dụ kiểm chứng bằng code:

~~~java
Authentication anonymous = new AnonymousAuthenticationToken(
    "test-key",
    "anonymousUser",
    AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS")
);

boolean rawFlag = anonymous.isAuthenticated(); // true
boolean anonymousState =
    new AuthenticationTrustResolverImpl().isAnonymous(anonymous); // true
~~~

Đây là snippet trong project có Spring Security. Không tự tạo anonymous token trong production để thay framework; chỉ dùng để thấy rõ raw flag và trạng thái truy cập khác nhau.

### 6.2. authenticated() không tương đương raw flag

Trong HttpSecurity:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/private").authenticated()
    .anyRequest().denyAll()
)
~~~

Spring Security áp dụng chính sách `.authenticated()` có phân biệt anonymous. Vì vậy một request chỉ có AnonymousAuthenticationToken vẫn **bị từ chối** ở `/private`, dù flag của token có thể true.

Sai lầm thường gặp trong custom code:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Tự cho phép đọc dữ liệu nhạy cảm
}
~~~

Điều kiện trên chưa đủ: anonymous token có thể thỏa; user đã đăng nhập vẫn có thể thiếu quyền resource. Dùng `.authenticated()`, `.hasRole()`, `.hasAuthority()`, `.fullyAuthenticated()` và kiểm tra owner/tenant phù hợp thay cho việc tự rút gọn bảo mật vào một boolean.

### 6.3. Remember-me và fullyAuthenticated()

Một số cơ chế remember-me có thể tạo Authentication với flag true mà không phải lần đăng nhập tương tác đầy đủ. Trong authorization có thể cần phân biệt:

- **anonymous()**: chưa có user authentication thật.
- **rememberMe()**: nhận diện qua cơ chế remember-me.
- **authenticated()**: đã được xác thực theo tiêu chí framework, không là anonymous.
- **fullyAuthenticated()**: thông thường loại trừ anonymous và remember-me.

**fullyAuthenticated() không tự chứng minh đã hoàn thành MFA**. Nếu nghiệp vụ có step-up authentication, MFA hoặc mức độ tin cậy riêng, phải áp dụng policy tương ứng.

### 6.4. Đăng nhập thành công không đồng nghĩa được quyền quản trị

~~~text
authentication.isAuthenticated() -> true
authentication.getName()        -> "alice"
authentication.getAuthorities() -> [ROLE_USER]

GET /api/profile -> có thể ALLOW
GET /api/admin   -> DENY khi rule yêu cầu ROLE_ADMIN
~~~

Nếu policy cần quyền xem hóa đơn của tenant, còn phải kiểm tra ownership và tenant tại điểm truy xuất dữ liệu. Authentication chỉ là đầu vào cho authorization.

### 6.5. Đừng tự gọi setAuthenticated(true)

Token yêu cầu xác thực có thể từ chối `setAuthenticated(true)`. Với `UsernamePasswordAuthenticationToken.unauthenticated(...)`, việc ép flag này có thể ném `IllegalArgumentException`.

Đừng thay bằng cách dùng factory authenticated(...) với role do client khai. Cách đúng là để filter gửi request token đến `AuthenticationManager.authenticate(...)`, provider xác minh credential và cấp authorities đã kiểm tra.

## 7. SecurityContextHolder và việc đọc Authentication

Trong một request Servlet:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

Đây là snippet. Context mặc định được giữ theo thread xử lý request; Spring Security dọn context khi hoàn tất. Không lưu Authentication trong biến static dùng chung vì có thể rò thông tin người dùng qua request khác.

`authentication` **có thể null**, ví dụ trong công việc background, test không khởi tạo context, request nằm ngoài SecurityFilterChain hoặc trước khi anonymous filter chạy.

### 7.1. Spring MVC và anonymous

Với endpoint chỉ dành cho user đăng nhập:

~~~java
@GetMapping("/profile")
public String profile(Authentication authentication) {
    return authentication.getName();
}
~~~

Tuy nhiên Spring MVC argument resolver cho `Principal`/`Authentication` có thể đọc từ `HttpServletRequest.getPrincipal()`, và giá trị đó thường **null với anonymous**, dù SecurityContext đã có AnonymousAuthenticationToken.

Khi muốn quan sát **cả anonymous Authentication**, dùng:

~~~java
@GetMapping("/public")
public String publicView(@CurrentSecurityContext SecurityContext context) {
    Authentication authentication = context.getAuthentication();
    return authentication == null
        ? "none"
        : authentication.getName();
}
~~~

Các đoạn trên là snippet cần lớp/controller/import phù hợp. `@CurrentSecurityContext` đọc context của Spring Security. Không suy ra context chắc chắn trống chỉ vì tham số `Authentication` trong một anonymous MVC handler nhận null.

### 7.2. @AuthenticationPrincipal và công việc bất đồng bộ

`@AuthenticationPrincipal` đưa principal hiện tại vào tham số method, không phải toàn bộ Authentication. Kiểu principal phụ thuộc provider. Khi dùng `@Async`, Executor hoặc thread mới, `SecurityContextHolder` không mặc định tự truyền qua mọi thread: dùng cơ chế propagation được hỗ trợ (ví dụ DelegatingSecurityContextExecutor) nếu nghiệp vụ cần.

Ứng dụng WebFlux reactive dùng Reactor Context và SecurityWebFilterChain, khác các API Servlet và MockMvc đang dùng trong bài này.

## 8. Ví dụ hoàn chỉnh Spring Boot 3: xem identity mà không lộ credentials

Ta xây dựng API nhỏ:

- **GET /api/public**: công khai và cho phép quan sát anonymous authentication.
- **GET /api/me**: chỉ cho account đã xác thực; trả name, principalType, authenticatedFlag, anonymous và authorities.
- **GET /api/admin**: cần ROLE_ADMIN.
- **GET /api/unlisted**: có controller nhưng bị fallback deny.
- Không có endpoint nào trả credentials hoặc serialize nguyên Authentication.

### 8.1. Dependencies và cấu trúc project

Dùng Spring Boot 3.x, Java 17+ và Gradle project đã có plugin/dependency management phù hợp. Thêm vào build.gradle hiện hữu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các file:

~~~text
src/main/java/com/example/authidentity/
  AuthIdentityApplication.java
  SecurityConfig.java
  IdentityController.java

src/test/java/com/example/authidentity/
  AuthenticationIdentityTest.java
~~~

### 8.2. AuthIdentityApplication.java

~~~java
package com.example.authidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthIdentityApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfig.java

~~~java
package com.example.authidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
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
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Đọc cấu hình:**

1. `httpBasic` cho filter nhận Basic header và provider xác thực username/password.
2. `UserDetailsService` tải hash, authorities và trạng thái tài khoản; `PasswordEncoder` dùng BCrypt.
3. `SessionCreationPolicy.STATELESS` làm Spring Security không dựa vào HttpSession để lấy SecurityContext cho request kế tiếp. Đây là lựa chọn demo, không phải yêu cầu của interface Authentication.
4. `/api/public` permitAll vẫn đi qua chain và anonymous filter có thể tạo anonymous token.
5. `/api/me` authenticated() sử dụng chính sách có phân biệt anonymous.
6. `/api/admin` yêu cầu ROLE_ADMIN, không phải username “admin”.
7. `anyRequest().denyAll()` chặn các path/method chưa liệt kê.
8. Demo chỉ có GET; không cần tắt CSRF. Nếu bổ sung POST/PUT/DELETE, phải thiết kế CSRF theo client/credential transport.

Mật khẩu demo chỉ dành cho localhost. HTTP Basic dùng Base64, cần HTTPS khi gửi qua mạng và không dùng hard-code credentials trong production.

### 8.4. IdentityController.java

~~~java
package com.example.authidentity;

import java.util.List;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/api/public")
    public AuthenticationView publicInfo(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context.getAuthentication());
    }

    @GetMapping("/api/me")
    public AuthenticationView me(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context.getAuthentication());
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }

    @GetMapping("/api/unlisted")
    public String unlisted() {
        return "must-not-be-exposed";
    }

    private AuthenticationView describe(Authentication authentication) {
        if (authentication == null) {
            return new AuthenticationView(
                "none", "none", false, true, List.of()
            );
        }

        String principalType = authentication.getPrincipal() == null
            ? "null"
            : authentication.getPrincipal().getClass().getSimpleName();

        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new AuthenticationView(
            authentication.getName(),
            principalType,
            authentication.isAuthenticated(),
            trustResolver.isAnonymous(authentication),
            authorities
        );
    }

    public record AuthenticationView(
        String name,
        String principalType,
        boolean authenticatedFlag,
        boolean anonymous,
        List<String> authorities
    ) {}
}
~~~

Vì đây là demo học tập, DTO trả **principalType** để xem kiểu object, nhưng API production thường không cần công khai tên class. **Không đưa `getCredentials()` vào DTO**, không serialize UserDetails, Authentication hoặc SecurityContext.

### 8.5. Chạy và quan sát

Từ thư mục có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/unlisted
curl -i -u alice:wrong http://localhost:8080/api/me
~~~

**Dự kiến** với đúng demo:

| Request | HTTP | Ý nghĩa |
| --- | --- | --- |
| GET /api/public anonymous | **200** | DTO thường có name=anonymousUser, authenticatedFlag=true và anonymous=true |
| GET /api/me anonymous | **401** | Spring Security không coi anonymous là authenticated cho rule này |
| GET /api/me alice đúng password | **200** | name=alice, principalType=User, authorities ROLE_USER và report:read |
| GET /api/admin alice | **403** | Đăng nhập thành công nhưng không có ROLE_ADMIN |
| GET /api/admin admin | **200** | Body `admin-only` |
| GET /api/unlisted admin | **403** | Fallback denyAll vẫn chặn |
| GET /api/me alice sai password | **401** | Credential sai |

Ví dụ JSON của `/api/me` với Alice (thứ tự keys tùy serializer):

~~~json
{
  "name": "alice",
  "principalType": "User",
  "authenticatedFlag": true,
  "anonymous": false,
  "authorities": ["ROLE_USER", "report:read"]
}
~~~

Không có credential, raw password hoặc token trong response.

## 9. Kiểm thử MockMvc: phân biệt các trạng thái

Tạo `src/test/java/com/example/authidentity/AuthenticationIdentityTest.java`:

~~~java
package com.example.authidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationIdentityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestTokenIsNotTrustedYet() {
        UsernamePasswordAuthenticationToken token =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-secret"
            );

        assertEquals("alice", token.getPrincipal());
        assertEquals("demo-secret", token.getCredentials());
        assertTrue(token.getAuthorities().isEmpty());
        assertFalse(token.isAuthenticated());

        assertThrows(IllegalArgumentException.class,
            () -> token.setAuthenticated(true));
    }

    @Test
    void anonymousFlagCanBeTrueWithoutActualLogin() {
        Authentication anonymous = new AnonymousAuthenticationToken(
            "test-key",
            "anonymousUser",
            AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS")
        );

        assertTrue(anonymous.isAuthenticated());
        assertTrue(
            new AuthenticationTrustResolverImpl().isAnonymous(anonymous)
        );
    }

    @Test
    void anonymousCanVisitPublicButNotProtected() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.anonymous").value(true));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordProducesPrincipalAndAuthorities() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authenticatedFlag").value(true))
            .andExpect(jsonPath("$.anonymous").value(false))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void loggedInUserCanStillLackRole() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void evenAdminCannotOverrideDenyAll() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Các test kiểm tra:
- Token chưa xác thực có principal/credentials, nhưng authorities rỗng và flag false.
- Anonymous token có thể flag true, đồng thời `AuthenticationTrustResolver` nhận diện anonymous.
- Public endpoint không cần login; protected endpoint không chấp nhận anonymous.
- Provider xác minh password, tạo principal và authorities tin cậy.
- Đã xác thực vẫn có thể thiếu role và bị 403.
- Rule denyAll vẫn có hiệu lực với cả admin.

**MockMvc với Spring Security Test gửi HTTP Basic qua filter**, không tự tạo một principal đã xác thực để bỏ qua việc kiểm tra password. Đây là code và kết quả kỳ vọng của một dự án Spring Boot 3.x; muốn khẳng định test thực tế đã pass phải chạy `gradlew test` trên project có đúng dependencies.

## 10. Với OAuth2 Resource Server, giá trị có thể khác

Một Resource Server nhận:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Sau khi token được decoder/provider xác minh đúng khóa, issuer, audience, thời hạn và validator phù hợp:

- `getPrincipal()` thường là Jwt trong JwtAuthenticationToken, không phải UserDetails.
- `getName()` thường dùng claim sub theo converter mặc định hoặc custom name attribute.
- `getCredentials()` tùy Authentication implementation; không nên log/serialize token.
- `getAuthorities()` có thể là các chuỗi `SCOPE_...` từ scope/claims.
- `isAuthenticated()` thường true ở kết quả hợp lệ, nhưng request vẫn cần đủ scope và quyền với resource.

Snippet trong Controller JWT Resource Server:

~~~java
@GetMapping("/jwt-subject")
public String subject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

Đoạn này **không thuộc demo HTTP Basic** và chỉ chạy khi cấu hình JWT Resource Server phù hợp. Một JWT đọc được payload bằng Base64URL **chưa chứng minh token được xác minh chữ ký và claims**.

Nếu scope là `reports.read` và converter ánh xạ sang `SCOPE_reports.read`, policy `hasAuthority("SCOPE_reports.read")` mới khớp. Không coi `SCOPE_reports.read`, `report:read` và `ROLE_USER` là cùng một quyền.

## 11. Các sai lầm phổ biến

### 11.1. Dùng isAuthenticated() như toàn bộ authorization

Anonymous token có thể có flag true, và user thực sự vẫn có thể thiếu quyền đối với tài nguyên. Dùng policy của Spring Security kết hợp kiểm tra role, scope, ownership và tenant.

### 11.2. Giả định principal luôn là UserDetails

Principal phụ thuộc provider. Chỉ cast khi kiểm soát kiểu; dùng `getName()` hoặc CurrentUser abstraction khi chỉ cần định danh đã xác minh.

### 11.3. Log getCredentials để debug

Có nguy cơ lộ raw password hoặc token. Chỉ ghi metadata an toàn như request ID, account ID đã xác minh và decision, không ghi Authorization header.

### 11.4. Cho phép client gửi roles và tự tạo authenticated token

Provider/manager phải xác minh credential và authority source. Không xây login bằng cách gọi authenticated(...) với role client tự gửi.

### 11.5. Coi getAuthorities là quyền đọc mọi resource

Một authority cấp cao không thay kiểm tra owner, tenant hoặc trạng thái đối tượng. Tránh lỗi IDOR/BOLA.

### 11.6. Coi credentials null sau login là thất bại

ProviderManager thường xóa credential sau authentication. Đó là cơ chế bảo vệ, không phải tín hiệu user chưa login.

### 11.7. Giữ Authentication trong static field

Authentication gắn với security context/request, không phải biến toàn cục. Khi làm async phải dùng context propagation đúng cách.

### 11.8. Nhầm anonymous với SecurityContext null

MVC resolver có thể trả null cho anonymous, dù context của Spring Security chứa AnonymousAuthenticationToken. Đọc đúng nơi bằng `@CurrentSecurityContext` khi cần.

### 11.9. Nghĩ flag true đồng nghĩa fully authenticated hoặc hoàn thành MFA

Remember-me, anonymous và các mức tin cậy khác cần policy phù hợp. MFA phải được diễn tả và kiểm tra riêng.

### 11.10. Coi authorities đã cấp là luôn mới nhất

Session, JWT và UserDetails cache có thể giữ dữ liệu trước khi role đổi. Cần chính sách thu hồi/revalidation.

### 11.11. Trả nguyên Authentication thành JSON

Có thể làm lộ principal nội bộ, hash, token, request details. DTO công khai nên chỉ có các trường phục vụ client.

## 12. Debug một request bằng bốn phương thức

| Quan sát | Cần kiểm tra |
| --- | --- |
| Principal là String thay vì UserDetails | Có phải request token chưa qua provider? |
| Credentials null sau login | Có phải credentials đã được xóa theo thiết kế? |
| Authorities rỗng | Đã có result từ provider? UserDetailsService/converter đã tải quyền chưa? |
| isAuthenticated false | Có phải authentication request chưa được xác minh? |
| isAuthenticated true nhưng vẫn 401 | Có phải anonymous token và entry point yêu cầu login? |
| isAuthenticated true nhưng 403 | Thiếu role/scope, quyền theo resource hoặc CSRF token? |
| Principal là Jwt | Resource Server đang dùng JWT, không thể cast UserDetails? |
| Role đã đổi nhưng vẫn có quyền cũ | Authentication trong session/token/cache có được refresh? |
| Controller public nhận Authentication null | Có đang dùng servlet principal resolver thay vì SecurityContext không? |

Bật log ở môi trường phát triển khi cần:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

**Không ghi password, token, cookie, Authorization header hoặc raw credentials vào log.** HTTP 401 thường liên quan authentication, 403 thường là authorization/CSRF và 302 có thể do form login; status cụ thể tùy entry point, handler và chain.

## 13. Bài tập tự kiểm tra

**Câu 1.** Mới tạo `UsernamePasswordAuthenticationToken.unauthenticated("alice", "abc")`, getPrincipal và isAuthenticated là gì?

**Đáp án:** Principal là String `"alice"`; flag là **false**, vì credential chưa được provider xác minh.

**Câu 2.** getCredentials() sau login trả null có chứng minh login thất bại?

**Đáp án:** Không. ProviderManager thường xóa credentials sau xác thực thành công.

**Câu 3.** AnonymousAuthenticationToken có flag true. Có đi qua rule `.authenticated()` được không?

**Đáp án:** Không. Spring Security phân biệt anonymous bằng trust resolver và không coi đó là user đăng nhập thật.

**Câu 4.** User có ROLE_USER, isAuthenticated=true nhưng endpoint yêu cầu ROLE_ADMIN?

**Đáp án:** Thường nhận 403 sau khi xác thực thành công, vì thiếu authority tương ứng.

**Câu 5.** getPrincipal() luôn là UserDetails?

**Đáp án:** Sai. Nó có thể là String, UserDetails, Jwt, OAuth2User hoặc principal riêng tùy provider.

**Câu 6.** Vì sao không nên trả nguyên Authentication cho browser?

**Đáp án:** Có thể chứa credentials hoặc metadata/claims nội bộ; trả DTO giới hạn trường.

**Câu 7.** Authority report:read có cho phép đọc báo cáo của tenant khác không?

**Đáp án:** Không tự động. Phải kiểm tra chính sách owner/tenant/resource.

**Câu 8.** Role đổi trong database, getAuthorities trong session/JWT có đổi ngay?

**Đáp án:** Không mặc định. Cần token/session/cache invalidation hoặc revalidation.

**Câu 9.** Vì sao SCOPE_reports.read không bằng report:read?

**Đáp án:** Hai chuỗi authority khác nhau; policy phải khớp converter và convention.

**Câu 10.** Có thể cấp authenticated=true bằng tay từ role client gửi để tránh AuthenticationManager?

**Đáp án:** Không. Đó là bypass xác thực; provider đáng tin cậy phải xác minh credential và quyền.

**Câu 11.** Vì sao @CurrentSecurityContext hữu ích khi cần quan sát anonymous?

**Đáp án:** Nó đọc SecurityContext của Spring Security, trong khi servlet principal resolver của MVC có thể trả null cho anonymous.

**Câu 12.** isAuthenticated() == true có tự chứng minh MFA đã hoàn thành?

**Đáp án:** Không. Cần chính sách mức độ xác thực và authorization phù hợp.

## Tài liệu chính thức

- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security API — **Authentication**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/core/Authentication.html
- Spring Security API — **UsernamePasswordAuthenticationToken**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html
- Spring Security — **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html

**Ghi nhớ:** `getPrincipal()` đại diện danh tính; `getCredentials()` giữ bằng chứng và thường bị xóa sau xác thực; `getAuthorities()` giữ quyền đã cấp; `isAuthenticated()` chỉ phản ánh trạng thái Authentication object. **Quyết định cấp quyền phải được đưa ra bằng policy đúng với loại authentication và resource, không bằng việc kiểm tra một boolean đơn lẻ.**
