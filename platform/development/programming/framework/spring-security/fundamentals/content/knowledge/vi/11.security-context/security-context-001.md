# SecurityContext và vòng đời danh tính trong một yêu cầu

> **Chủ đề cha:** Ngữ cảnh bảo mật. Bài học tập trung vào Spring Security 6.x trên Servlet/Spring MVC, Java 17+ và Spring Boot 3.x. Mục tiêu: hiểu danh tính được **nạp, thiết lập, sử dụng, lưu và dọn** thế nào trong một HTTP request; phân biệt `SecurityContext`, `SecurityContextHolder`, `Authentication`, `SecurityContextRepository`; đồng thời so sánh form-login session với HTTP Basic stateless, anonymous authentication, request dispatch và async. Ví dụ có source code Spring Boot và kiểm thử MockMvc.

## 1. SecurityContext là gì?

Trong ứng dụng web, khi Alice truy cập `GET /me`, controller thường cần biết người gọi là ai. Ta không thể lấy “current user” bằng một biến static toàn cục: nhiều HTTP requests từ nhiều users được xử lý đồng thời và thread pool có thể tái sử dụng thread.

Spring Security giải quyết điều đó bằng **ngữ cảnh bảo mật (security context)**. Đây là object chứa một `Authentication` đại diện cho thông tin danh tính hiện tại.

~~~text
SecurityContextHolder
    |
    v
SecurityContext
    |
    v
Authentication
    +-- principal: ai được đại diện
    +-- credentials: bằng chứng xác thực (có thể đã xóa)
    +-- authorities: ROLE_USER, ROLE_ADMIN, scope, permission...
    +-- authenticated: trạng thái của authentication object
~~~

Bốn khái niệm khác nhau:

| Khái niệm | Trách nhiệm | Không phải |
| --- | --- | --- |
| `Authentication` | Object mô tả yêu cầu xác thực hoặc danh tính kết quả | Một cơ chế tự kiểm tra quyền mọi tài nguyên |
| `SecurityContext` | Bao chứa Authentication hiện tại | Database user hoặc một phiên HTTP |
| `SecurityContextHolder` | API/strategy cho code đang chạy truy cập SecurityContext | Kho lưu context bền vững giữa các requests |
| `SecurityContextRepository` | Nạp và lưu SecurityContext theo chính sách | Một `UserDetailsService` hay `AuthenticationProvider` |

Ví dụ đọc ngữ cảnh:

~~~java
SecurityContext context =
    SecurityContextHolder.getContext();

Authentication authentication =
    context.getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    boolean authenticatedFlag =
        authentication.isAuthenticated();
}
~~~

Đây là snippet, cần imports và phương thức bao quanh. **`getContext()` khác null không có nghĩa user đã đăng nhập**. Một context có thể chưa có Authentication hoặc có `AnonymousAuthenticationToken`.

## 2. Một HTTP request đi qua những bước nào?

Xét một trình duyệt đã đăng nhập Alice bằng form login. Browser gửi cookie session:

~~~http
GET /me HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

Luồng Servlet thông dụng:

~~~text
HTTP request từ browser
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy (springSecurityFilterChain)
    |
    +--> Chọn SecurityFilterChain theo URL/request
    |
    v
SecurityContextHolderFilter
    |
    +--> SecurityContextRepository
    |       +--> Tìm context đã được lưu (nếu có)
    |       +--> Hoặc cung cấp context rỗng
    |
    v
Authentication filters, nếu request mang credential
    |
    +--> Basic / Form / Bearer / cơ chế khác
    +--> AuthenticationManager + providers
    +--> Nếu thành công: đặt Authentication đáng tin vào context
    |
    v
AnonymousAuthenticationFilter
    |
    +--> Nếu chưa có Authentication, tạo anonymous token
    |
    v
ExceptionTranslationFilter / AuthorizationFilter
    |
    +--> `.authenticated()`, `.hasRole()`, policy khác
    +--> Cho phép hoặc từ chối request
    |
    v
DispatcherServlet -> Controller -> Service
    |
    +--> Đọc context của request hiện tại
    |
    v
HTTP response / exception
    |
    v
Filter lifecycle kết thúc
    |
    +--> SecurityContextHolder được dọn khỏi thread
    |
    v
Thread sẵn sàng phục vụ request khác
~~~

Sơ đồ này là **mô hình khái niệm**, không khẳng định mọi SecurityFilterChain đều có mọi filter hoặc trình tự bên trên là danh sách đầy đủ. Trình tự cụ thể phụ thuộc authentication mechanism, version, custom filters và servlet dispatcher type.

Điểm đáng nhớ: một request có thể **không đăng nhập mới** nhưng vẫn được nhận diện là Alice, vì context từ **HttpSession của lần login trước** được phục hồi.

### 2.1. `SecurityFilterChain` được chọn trước tiên

Trong một ứng dụng có thể có nhiều chain:

~~~text
SecurityFilterChain #1: /api/**
  - HTTP Basic
  - STATELESS
  - không lưu identity qua HttpSession

SecurityFilterChain #2: các URL còn lại
  - Form login
  - lưu context vào HttpSession khi đăng nhập
~~~

`FilterChainProxy` chọn chain theo matcher và thứ tự. Security context được xử lý theo chính sách của chain đã chọn. Đừng cấu hình `/api/**` rồi quên fallback chain khiến URL khác có thể nằm ngoài Spring Security.

### 2.2. `permitAll()` không xóa SecurityContext

Một endpoint `/public` có thể cấu hình `permitAll()`, nhưng nó vẫn nằm trong Spring Security chain. Do đó `AnonymousAuthenticationFilter` có thể gắn AnonymousAuthenticationToken và Controller có thể quan sát context.

Phân biệt:
- `.permitAll()`: filter chain vẫn chạy, chỉ authorization cho phép request.
- `web.ignoring()`/request không match chain: có thể bỏ qua cả security filters và những bảo vệ liên quan.

Khi public endpoint vẫn cần security headers/anonymous/CSRF behavior, thường ưu tiên `permitAll` thay vì bypass chain.

## 3. Bước nạp context đầu request

### 3.1. Vai trò của `SecurityContextHolderFilter`

Trong Spring Security 6, `SecurityContextHolderFilter` được dùng theo cơ chế explicit-save. Nó tương tác với một `SecurityContextRepository` để security context sẵn có khi request cần dùng, và dọn holder sau khi request hoàn tất.

**Nó không tự lưu mọi thay đổi Authentication từ code custom.** Đây là khác biệt quan trọng so với mô hình Spring Security 5 dùng `SecurityContextPersistenceFilter` có thể tự lưu context cuối request. Framework authentication filters đã được tích hợp logic persistence phù hợp; nếu tự viết login filter/controller thì phải đặc biệt chú ý bước save.

### 3.2. `SecurityContextRepository` có những implementation nào?

| Implementation | Ý nghĩa | Tồn tại bao lâu? |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu context trong HttpSession để request sau có thể khôi phục | Theo vòng đời session và chính sách logout/invalidation |
| `RequestAttributeSecurityContextRepository` | Giữ context qua request attributes, hữu ích với một số ERROR dispatch | Trong cùng logical request, không persist sang HTTP request mới |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository, thông dụng là request attribute + HttpSession | Theo hành vi từng delegate |
| `NullSecurityContextRepository` | Không lưu hoặc khôi phục state qua repository | Không có persistence giữa requests |

Cấu hình mặc định thông dụng của Spring Security 6 dùng `DelegatingSecurityContextRepository`, kết hợp HttpSession và request attribute. Không nên đoán `getContext()` là “query database” — nó lấy context framework đã thiết lập hoặc khôi phục.

### 3.3. Tại sao có RequestAttributeSecurityContextRepository?

Trong Servlet, `REQUEST` và `ERROR` dispatch có thể xảy ra trong cùng một logical request. Một controller xác thực Alice rồi ném exception; container có thể chạy một ERROR dispatch và holder ban đầu đã bị clear.

Request attribute repository giúp context đã được lưu đúng cách có thể xuất hiện trở lại trong một số dispatch thuộc **cùng request**, tùy container và cấu hình. Nó **không phải session store**: request HTTP mới của browser không thể dùng request attribute của request cũ để nhận diện Alice.

### 3.4. Deferred loading

Spring Security hỗ trợ deferred context để tránh đọc session/context không cần thiết trên một số request. Bạn không nên suy đoán một `getContext()` luôn tạo database query hoặc một request luôn nạp context đúng một lần. Tương tác thực tế tùy repository và thời điểm authentication được yêu cầu.

## 4. SessionCreationPolicy và vòng đời danh tính

| Giá trị | Hành vi liên quan đến HttpSession |
| --- | --- |
| `ALWAYS` | Spring Security có thể chủ động tạo HttpSession |
| `IF_REQUIRED` | Tạo session khi cần, ví dụ lưu login thành công |
| `NEVER` | Không chủ động tạo session nhưng **có thể dùng session hiện có** |
| `STATELESS` | Không dùng HttpSession để lấy SecurityContext hoặc tạo session cho mục đích đó |

**`NEVER` khác `STATELESS`.** Hai policy không thể thay lẫn cho nhau. `STATELESS` cũng không đồng nghĩa “không có Authentication”: mỗi request Bearer/Basic vẫn có thể xác thực thành công và có Authentication trong chính request đó.

### 4.1. Ví dụ có session

~~~text
POST /login: Alice cung cấp username/password
   |
   v
Provider xác thực thành công
   |
   v
Context(Alice) được lưu vào HttpSession S1

GET /me + Cookie S1
   |
   v
Repository khôi phục context(Alice)
   |
   v
/me cho phép
   |
   v
Holder của thread được clear cuối request

GET /me + Cookie S1 lần nữa
   |
   v
Context(Alice) lại được khôi phục
~~~

Việc **clear holder cuối mỗi request** không làm mất `HttpSession` và không tự logout Alice.

### 4.2. Ví dụ stateless Basic

~~~text
Request #1:
  GET /api/me
  Authorization: Basic alice:...
  -> filter xác minh -> Authentication(Alice)
  -> Controller trả 200
  -> clear context của thread

Request #2:
  GET /api/me
  không có Authorization header
  -> không phục hồi Alice từ HttpSession
  -> endpoint yêu cầu authenticated
  -> 401 theo Basic entry point
~~~

Request #1 có đầy đủ context/authentication, dù ứng dụng không persist nó sang request #2. Khi user cung cấp Basic mỗi request, provider có thể xác minh lại; với JWT, decoder/validator kiểm tra token mỗi request và tạo Authentication mới theo policy.

### 4.3. Stateless không phải token revocation

Một JWT đã được phát có thể vẫn chứa role/scope cũ sau khi DB thay đổi. Việc không lưu session chỉ tránh server-side identity persistence, **không thu hồi access token**; cần TTL, revocation, introspection hoặc live authorization nếu nghiệp vụ đòi hiệu lực ngay.

## 5. Authentication được tạo và cập nhật giữa request

Một HTTP Basic filter có thể tạo token **chưa được xác thực**:

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "example-password"
    );

boolean before = attempt.isAuthenticated(); // false
~~~

Đây là snippet minh họa. `AuthenticationManager`/`AuthenticationProvider` sẽ xác minh credential, kiểm tra account status và tạo Authentication kết quả.

Với username/password:
- `UserDetailsService` tìm username và hash từ nguồn tài khoản.
- `PasswordEncoder.matches(rawPassword, storedHash)` kiểm tra credential.
- `DaoAuthenticationProvider` kiểm tra trạng thái disabled/locked/expired và cấp kết quả.
- Filter đặt Authentication được xác minh vào context theo cơ chế tin cậy.

**Không dùng `UsernamePasswordAuthenticationToken.authenticated(...)` cùng authorities do client gửi để “đăng nhập nhanh”.** Code tự tạo Authentication trusted khi chưa kiểm tra credentials là một bypass bảo mật.

### 5.1. Principal, credentials, authorities

Sau authentication thành công, Authentication thường chứa:
- **Principal:** `UserDetails`, `Jwt`, `OAuth2User` hoặc custom principal, tùy mechanism.
- **Credentials:** có thể bị xóa bởi `ProviderManager` và `CredentialsContainer`. Không dùng `null` để suy ra login thất bại.
- **Authorities:** những quyền được cấp bởi provider/converter đáng tin cậy.
- **isAuthenticated():** flag của object; **không tự chứng minh quyền đối với mọi resource**.

### 5.2. Chuyện gì xảy ra nếu không ai đăng nhập?

`AnonymousAuthenticationFilter` thường điền một `AnonymousAuthenticationToken` vào context nếu chưa có Authentication:

~~~text
principal = "anonymousUser"
authorities = [ROLE_ANONYMOUS]
isAuthenticated() có thể là true
~~~

Điều này tạo một representation thống nhất cho anonymous requests. Tuy nhiên Spring Security dùng `AuthenticationTrustResolver` để phân biệt anonymous với người dùng thực sự; `.authenticated()` **không cho anonymous đi qua** chỉ vì raw flag true.

Trong Spring MVC, tham số `Authentication` hoặc `Principal` được resolve qua Servlet principal đôi khi **null đối với anonymous**, dù `SecurityContextHolder` đã có AnonymousAuthenticationToken. Nếu muốn khảo sát anonymous, dùng `@CurrentSecurityContext SecurityContext context`.

### 5.3. Authentication và authorization

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/me").authenticated()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

- Alice có `ROLE_USER` có thể vào `/me`, nhưng thường bị 403 tại `/admin`.
- Anonymous vào `/me` được authentication entry point yêu cầu đăng nhập.
- `ROLE_ADMIN` không tự cho phép thao tác với dữ liệu mọi tenant/owner; domain policy phải kiểm tra resource cụ thể.
- Quyền trong Authentication có thể là snapshot tại login, không luôn là role mới nhất trong database.

## 6. Cuối request: dọn ThreadLocal, không làm lộ Alice sang Bob

`SecurityContextHolder` trong Servlet mặc định dùng `MODE_THREADLOCAL`: code trên cùng thread có thể truy cập context mà không truyền tham số qua mọi method.

~~~text
Thread 1: GET /me của Alice
    |
    +--> context=Alice
    +--> authorization, controller
    +--> clear context

Thread 1 được tái sử dụng: GET /me của Bob
    |
    +--> context=Bob hoặc anonymous
    +--> không được còn context của Alice
    +--> clear context
~~~

Nếu quên cleanup, server có nguy cơ **identity leakage giữa các requests** do thread pool tái sử dụng thread. Spring Security xử lý clear trong filter-chain lifecycle của request do nó quản lý. Code tự chạy ngoài chain phải có trách nhiệm tương ứng.

### 6.1. `clearContext()` không phải logout

~~~java
SecurityContextHolder.clearContext();
~~~

Dòng này dọn current execution context theo strategy. Nó **không trực tiếp invalidate HttpSession**, revoke JWT, xóa refresh token hay thay account database. Request mới có cùng cookie session hợp lệ vẫn có thể khôi phục context đã lưu.

**Logout thật sự** ở session-based app cần logout mechanism phù hợp: xóa SecurityContext, invalidate session và xử lý repository/cookie/response. Với token stateless, cần chính sách thu hồi nếu logout phải có hiệu lực trước khi token hết hạn.

### 6.2. Không lưu Authentication vào static field

Phản ví dụ:

~~~java
// SAI: có thể chia sẻ danh tính Alice cho request của Bob.
static Authentication currentUser;
~~~

Nếu cần định danh trong một service đồng bộ đang xử lý request, đọc context hiện tại qua Spring Security hoặc truyền account ID tin cậy. Nếu cần dữ liệu cho một job kéo dài, truyền dữ liệu nghiệp vụ tối thiểu và thiết kế reauthorization.

## 7. Spring Security 6 và `requireExplicitSave`

Ở Spring Security 5, `SecurityContextPersistenceFilter` có thể tự lưu thay đổi context khi request kết thúc/response commit. Ở Spring Security 6, mô hình mặc định dựa trên `SecurityContextHolderFilter` **chỉ nạp**, còn việc lưu context mới cần được thực hiện **tường minh** bởi authentication mechanism hoặc custom code.

Mô tả:

~~~text
Context ban đầu từ repository
    |
    v
SecurityContextHolderFilter đưa context vào holder
    |
    v
Authentication filter/provider xác thực thành công
    |
    v
Đặt Authentication mới vào SecurityContext
    |
    +--> Nếu muốn persist sang request khác:
    |       SecurityContextRepository.saveContext(...)
    |
    v
Controller/response
    |
    v
Holder được dọn
~~~

Framework form login tiêu chuẩn đã xử lý persistence cần thiết. Nhưng nếu bạn tự viết login flow và chỉ gọi `SecurityContextHolder.setContext(context)` mà **không save**, request sau có thể mất identity.

### 7.1. Custom authentication snippet đúng ranh giới

~~~java
// Snippet sau khi có authenticationManager và repository đáng tin.
// Chạy trong code authentication custom có HttpServletRequest/Response.

Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        usernameFromLogin, rawPasswordFromLogin
    );

Authentication verified =
    authenticationManager.authenticate(attempt);

SecurityContext freshContext =
    SecurityContextHolder.createEmptyContext();

freshContext.setAuthentication(verified);
SecurityContextHolder.setContext(freshContext);

// Chỉ cần nếu flow được thiết kế persist context sang request sau.
securityContextRepository.saveContext(
    freshContext, request, response
);
~~~

**Không đặt quyền ADMIN vào một token do request tự khai rồi gọi save.** Bước xác minh bởi AuthenticationManager/Provider là bắt buộc trước khi biến token thành trusted Authentication. Lưu context ở đúng thời điểm trước khi response committed nếu ứng dụng cần tạo session/cookie.

### 7.2. Vì sao khuyến cáo `createEmptyContext()`?

~~~java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

Một SecurityContext thường là mutable; nếu sửa trực tiếp Authentication của context đã được share giữa nhiều threads/session concurrent requests, có thể tạo race/unexpected state. Tạo context mới khi set một Authentication mới giúp tránh lỗi chia sẻ không mong muốn.

### 7.3. Không gọi save ở mọi controller

Nếu dùng form login chuẩn, không cần thêm `saveContext` vào mọi controller chỉ để giữ login. Nếu dùng HTTP Basic stateless, bạn **không nên** cố save vào HttpSession trái với architecture. Hãy phân biệt authentication flow và persistence policy.

## 8. Spring MVC: ba cách đọc danh tính

### 8.1. Tham số `Authentication`

Trong endpoint chỉ dành cho user đăng nhập:

~~~java
@GetMapping("/me")
public String me(Authentication authentication) {
    return authentication.getName();
}
~~~

Đây là snippet trong @RestController đã bảo vệ endpoint. Spring MVC có thể dựa vào Servlet principal resolver, nên anonymous có thể nhận null; tránh dereference trong endpoint public.

### 8.2. `@CurrentSecurityContext`

~~~java
@GetMapping("/public/context")
public String publicContext(
        @CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth == null ? "none" : auth.getName();
}
~~~

Cách này đọc context hiện tại của Spring Security, có thể thấy anonymous Authentication khi filter anonymous hoạt động.

### 8.3. `@AuthenticationPrincipal`

~~~java
@GetMapping("/profile")
public String profile(
        @AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Chỉ dùng type `UserDetails` nếu provider thực sự cấp principal loại đó. Với JWT Resource Server có thể là Jwt, với OAuth2 Login có thể là OidcUser/OAuth2User. Không cast cứng mọi principal sang UserDetails.

### 8.4. DTO an toàn

Không trả thẳng `Authentication`, `SecurityContext`, `UserDetails` hoặc `Jwt` ra JSON. Chúng có thể chứa password hash, tokens, claims và metadata không dành cho client. Demo bên dưới trả DTO tối thiểu: name, loại principal, authorities, anonymous và authenticated flag — chỉ phục vụ học tập.

## 9. Demo Spring Boot 3: hai filter chains để thấy vòng đời khác nhau

Demo có:
- `/public` và `/public/context`: công khai; endpoint thứ hai quan sát anonymous Authentication.
- `/me`: form login + session, request sau có cookie vẫn thấy Alice.
- `/admin`: yêu cầu ROLE_ADMIN; Alice không đủ quyền.
- `/api/me`: HTTP Basic + stateless, request kế tiếp phải có credential của chính nó.
- `/api/public`: public qua API chain, không dùng form-login session.

### 9.1. Dependencies và cấu trúc

Tạo một project Spring Boot **3.x**, Spring Security **6.x**, Java **17+**, Gradle Wrapper đã cấu hình plugin và repositories. Trong `build.gradle` hiện hữu thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây chỉ là block dependencies, không phải build.gradle độc lập. Các file:

~~~text
src/main/java/com/example/contextlife/
  ContextLifeApplication.java
  SecurityConfig.java
  ContextController.java

src/test/java/com/example/contextlife/
  ContextLifecycleTest.java
~~~

### 9.2. ContextLifeApplication.java

~~~java
package com.example.contextlife;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextLifeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextLifeApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig.java

~~~java
package com.example.contextlife;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
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
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(ctx -> ctx
                .securityContextRepository(
                    new NullSecurityContextRepository()
                )
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/public", "/public/context")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/public")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }
}
~~~

Phân tích:

1. **Hai filter chains:** `/api/**` được xử lý trước (`@Order(1)`), các URL khác dùng fallback (`@Order(2)`).
2. **API:** bật HTTP Basic, không dùng HttpSession làm SecurityContextRepository, request cache không giữ saved requests. Một request API đã xác thực không làm request tiếp theo không credential trở thành Alice.
3. **Web:** bật form login chuẩn và cho phép login page/login processing URL. Form login tạo session khi cần và có thể persist Authentication qua repository của framework.
4. **Phân quyền:** `/me` đòi authenticated; `/admin` đòi ROLE_ADMIN; các path khác deny-by-default.
5. **CSRF:** không tắt CSRF cho web chain. POST `/login`/`logout` phải gửi CSRF token nếu protection đang bật.
6. **Demo credentials:** `alice123`/`admin123` chỉ để học trên localhost; ngoài thực tế dùng database với hashed passwords, HTTPS, session-cookie security và rate-limit.

### 9.4. ContextController.java

~~~java
package com.example.contextlife;

import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ContextController {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/public/context")
    public ContextView publicContext(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/me")
    public ContextView me(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/api/me")
    public ContextView apiMe(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-only";
    }

    private ContextView describe(SecurityContext context) {
        Authentication authentication = context.getAuthentication();
        if (authentication == null) {
            return new ContextView(
                "none", "none", false, true, List.of()
            );
        }

        List<String> authorities =
            authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

        String type = authentication.getPrincipal() == null
            ? "null"
            : authentication.getPrincipal()
                .getClass().getSimpleName();

        return new ContextView(
            authentication.getName(),
            type,
            authentication.isAuthenticated(),
            trustResolver.isAnonymous(authentication),
            authorities
        );
    }

    public record ContextView(
        String name,
        String principalType,
        boolean authenticatedFlag,
        boolean anonymous,
        List<String> authorities
    ) {}
}
~~~

Demo dùng `@CurrentSecurityContext` vì có endpoint public cần đọc anonymous. `AuthenticationTrustResolver` phân biệt anonymous; `isAuthenticated()` một mình chưa đủ. DTO cố ý **không chứa credentials, password hash hoặc session ID**.

### 9.5. Chạy và quan sát

Từ root project đã có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Thử API Basic và anonymous:

~~~bash
curl -i http://localhost:8080/public/context
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/public
~~~

Kết quả dự kiến:

| Request | HTTP | Điều cần nhìn |
| --- | --- | --- |
| `/public/context` chưa login | **200** | `name=anonymousUser`, `anonymous=true`, authenticated flag có thể true |
| `/api/me` không Basic | **401** | API chain yêu cầu authentication |
| `/api/me` Basic Alice đúng | **200** | `name=alice`, `anonymous=false`, ROLE_USER |
| `/api/me` không Basic ngay sau request đúng | **401** | Không có session-based identity persistence |
| `/api/public` không Basic | **200** | `api-public` |
| `/me` sau form login với session | **200** | Alice được khôi phục từ HttpSession |
| `/admin` sau form login Alice | **403** | Có login nhưng thiếu ROLE_ADMIN |

Browser form login cần CSRF token trong POST `/login`; sử dụng trang login mặc định hoặc test MockMvc phần kế tiếp. Không thử bỏ CSRF để “cho dễ chạy”. Những status ở đây là **kỳ vọng theo source**, không phải HTTP response đã đo từ một server thật.

### 9.6. Ví dụ JSON

Anonymous request trong `/public/context` có thể trả:

~~~json
{
  "name": "anonymousUser",
  "principalType": "String",
  "authenticatedFlag": true,
  "anonymous": true,
  "authorities": ["ROLE_ANONYMOUS"]
}
~~~

Request Basic hợp lệ vào `/api/me`:

~~~json
{
  "name": "alice",
  "principalType": "User",
  "authenticatedFlag": true,
  "anonymous": false,
  "authorities": ["ROLE_USER"]
}
~~~

Cả hai object đều có `authenticatedFlag=true` trong demo, nhưng **chỉ Alice** là user đã được xác thực thật. Đó là lý do không làm custom authorization bằng `auth != null && auth.isAuthenticated()`.

## 10. Kiểm thử MockMvc về danh tính giữa các requests

Tạo `src/test/java/com/example/contextlife/ContextLifecycleTest.java`:

~~~java
package com.example.contextlife;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextLifecycleTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        assertNotNull(
            session.getAttribute("SPRING_SECURITY_CONTEXT")
        );
        return session;
    }

    @Test
    void anonymousIsPresentOnlyInsideRequest() throws Exception {
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("anonymousUser"))
            .andExpect(jsonPath("$.anonymous").value(true));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void formLoginPersistsIdentityIntoLaterSessionRequest()
            throws Exception {
        MockHttpSession session = login("alice", "alice123");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));

        // Sau MockMvc filter execution, holder của test thread được clear.
        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );

        // Request khác có cùng session vẫn khôi phục Alice.
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void twoSessionsAreIsolatedFromEachOther() throws Exception {
        MockHttpSession alice = login("alice", "alice123");
        MockHttpSession admin = login("admin", "admin123");

        mvc.perform(get("/me").session(alice))
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/me").session(admin))
            .andExpect(jsonPath("$.name").value("admin"));

        mvc.perform(get("/public/context"))
            .andExpect(jsonPath("$.anonymous").value(true));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void basicAuthenticationIsNotPersistedForNextRequest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void newWebRequestWithoutSessionMustLogInAgain()
            throws Exception {
        login("alice", "alice123");

        // Không gắn MockHttpSession của login vào request này.
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void publicRoutesAreInTheirRespectiveChains() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Giải thích bộ test:

1. Public handler thấy anonymous context **trong request**, còn khi filter chain kết thúc, test thread không còn Authentication.
2. Form login lưu SecurityContext vào HttpSession; browser gửi lại session nhận cùng identity.
3. Dùng hai session Alice và admin lần lượt trên test thread không làm lẫn danh tính.
4. Request Basic với credential đúng trả Alice; request Basic kế tiếp thiếu credential không thừa kế context.
5. Login bằng form không đủ để một request mới **không có session cookie** tự được nhận diện.
6. Alice có Authentication hợp lệ nhưng `/admin` vẫn bị từ chối bởi authority rule.

**Không dùng `@WithMockUser` để chứng minh session persistence.** `@WithMockUser` dựng fake Authentication để test authorization, không đi qua login filter/DaoAuthenticationProvider và không chứng minh SecurityContextRepository đã lưu context từ POST `/login`.

Những kết quả là **assertions kỳ vọng theo code**, không phải bằng chứng Gradle test đã chạy. Nếu dùng custom login flow, request cache, entry point hoặc Spring Security version khác, redirect/status có thể cần điều chỉnh trong test đúng theo ứng dụng.

## 11. Async và thread pool: bẫy quan trọng

Mặc định Servlet dùng `SecurityContextHolder.MODE_THREADLOCAL`. Một task trong thread pool khác **không tự có** Authentication của thread xử lý request.

Phản ví dụ:

~~~java
new Thread(() -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // Có thể null: đây là thread khác.
}).start();
~~~

Đừng chữa bằng cách đặt `MODE_GLOBAL` cho server nhiều users. `MODE_INHERITABLETHREADLOCAL` cũng cần cẩn trọng, nhất là thread pool tái sử dụng và quyền bị stale.

### 11.1. Propagation qua executor của Spring Security

Ví dụ snippet với executor đã tồn tại trong ứng dụng:

~~~java
DelegatingSecurityContextExecutor secureExecutor =
    new DelegatingSecurityContextExecutor(delegateExecutor);

secureExecutor.execute(() -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    // Chỉ thực hiện công việc trong phạm vi quyền hợp lệ.
});
~~~

`delegateExecutor` là `Executor` đã quản lý lifecycle; snippet cần imports. Helper của Spring Security giúp truyền context vào task được giao và phục hồi/dọn ngữ cảnh quanh execution. Nhưng **propagation không phải xác thực lại**, và context snapshot có thể trở nên stale khi job chạy lâu.

Với tác vụ kéo dài, thường nên truyền immutable account ID, yêu cầu ủy quyền hợp lệ rồi kiểm tra policy tại thời điểm thực thi, hoặc dùng **service identity** riêng. Không giữ raw credentials hay entire mutable Authentication trong một queue lâu dài.

### 11.2. WebFlux không dùng mô hình Servlet này

Spring WebFlux reactive dùng Reactor Context và `ReactiveSecurityContextHolder`; không áp dụng trực tiếp `ThreadLocal` Servlet cho mọi operator/thread. Nếu migrate MVC sang WebFlux, cần học lại context propagation và `SecurityWebFilterChain`.

## 12. Request dispatch, error, logout và account thay đổi

### 12.1. ERROR dispatch

Trong Servlet, một controller có thể ném exception, container chuyển sang ERROR dispatch. Context Holder của dispatch ban đầu có thể đã được dọn. `RequestAttributeSecurityContextRepository` có thể hỗ trợ khôi phục context cho cùng logical request nếu được lưu phù hợp. Không đảm bảo mọi error handler tự đọc được user; kiểm tra dispatcher configuration và repository.

### 12.2. Session timeout

Session hết hạn nghĩa request mới không còn nạp được Authentication đã lưu trong session. Nếu endpoint yêu cầu login, framework thường redirect `/login` với form login hoặc trả 401 với Basic. **Session timeout** khác với `SecurityContextHolder.clearContext()` sau từng request.

### 12.3. Logout

Logout trong web form thường gồm dọn SecurityContext, invalidate HttpSession và xử lý repository/cookies. `GET /logout` không phải cách logout production mặc định khi CSRF protection đang bật; framework dùng POST và CSRF token cho logout state-changing action.

### 12.4. Lock user và stale authorities

Nếu admin disabled account hoặc thu hồi ROLE_ADMIN trong database, session cũ có thể vẫn chứa Authentication đã tạo trước đó. `UserDetailsService` không tự được gọi trên mọi request khôi phục session. Cần session revocation, security-version checks, reauthentication hoặc resource-level live authorization nếu nghiệp vụ yêu cầu quyền cập nhật ngay.

### 12.5. JWT và state khác HttpSession

Mỗi Bearer request có thể tạo một Authentication mới từ JWT, nhưng JWT đã phát giữ nguyên claims. `clearContext()` cuối request **không revoke JWT**; muốn thu hồi cần TTL ngắn, denylist, introspection, version check hoặc policy khác theo hệ thống.

## 13. Những lỗi hay gặp và cách tránh

| Lỗi | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Lưu Authentication vào static field | Trộn danh tính giữa requests/threads | Đọc SecurityContext đúng lifecycle |
| Kiểm tra `getContext()!=null` để coi đã login | Context có thể rỗng/anonymous | Dùng `.authenticated()` và policy |
| Chỉ kiểm tra `isAuthenticated()==true` | Anonymous token có thể true | Dùng trust resolver và authorization |
| Chỉ gọi `setContext` trong custom login | Spring Security 6 explicit-save không tự persist | Gọi `saveContext` đúng thời điểm |
| Gọi `clearContext` và nghĩ đã logout | Chỉ dọn current holder | Dùng logout/session/token revocation |
| Dùng `NEVER` và nghĩ bằng `STATELESS` | NEVER có thể dùng session có sẵn | Chọn policy đúng |
| Cố ghi HttpSession trong API stateless | Đánh mất ranh giới stateless | Xác thực theo từng request |
| Trả nguyên SecurityContext JSON | Có thể lộ principal/credentials | Trả DTO tối thiểu |
| Copy context sang `@Async` vô điều kiện | Context có thể không được propagate hoặc stale | Dùng supported executor strategy |
| Không cấu hình fallback chain | Có URL không được bảo vệ | Bao phủ URL, deny-by-default |
| Quên CSRF ở POST login/logout | CSRF filter có thể từ chối | Giữ CSRF và gửi token hợp lệ |
| Nghĩ role session luôn mới nhất | Snapshot có thể cũ | Revoke/refresh/live authorization |

Một test chỉ assert `GET /me == 200` không chứng minh mọi ranh giới đúng. Hãy test **request liên tiếp khác user**, **request stateless thiếu credentials**, **request anonymous** và **context cleanup**.

## 14. Debug theo vòng đời một request

Khi user sai hoặc một endpoint bất ngờ trả 401/403, điều tra có thứ tự:

1. Request có đi qua `springSecurityFilterChain` không?
2. Chain nào match URL, HTTP method và dispatcher type? Có `@Order` và fallback không?
3. Repository của chain là HttpSession, RequestAttribute, Delegating hay Null?
4. Client có session cookie, Basic header, Bearer token hoặc form credentials?
5. Authentication filter nào chạy? Provider nào xác minh? Có exception không?
6. Context được nạp từ session cũ hay tạo mới từ credential?
7. Anonymous filter có tạo AnonymousAuthenticationToken không?
8. Principal type và `getName()` là gì? Có đúng user/workload không?
9. Authorities có role/scope đúng prefix không?
10. Authorization rule nào trả allow/deny? Có owner/tenant policy khác không?
11. Nếu login custom, `saveContext` đã gọi trước khi response committed chưa?
12. Session đã hết hạn, cookie có gửi lại, logout/revocation có chạy chưa?
13. Có code trên thread/executor khác không propagate/clear context đúng cách?
14. Có ERROR/ASYNC dispatch và context repository phù hợp không?
15. Sau response, context có được dọn khỏi request thread không?

Có thể bật log trong môi trường dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Chỉ ghi correlation ID, endpoint, filter decision và account ID được cho phép ghi. **Không log raw password, Authorization header, session cookie, access token, JWT claims nhạy cảm, credentials hoặc nguyên Authentication**.

### 14.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| `/me` sau login vẫn redirect | Cookie/session không gửi; custom flow quên saveContext |
| `/api/me` không Basic mà vẫn thấy Alice | Chain/stateless/repository hoặc credential truyền ngầm |
| Public endpoint có `anonymousUser` | Bình thường nếu anonymous filter chạy |
| Một request Bob thấy Alice | Static/shared context hoặc thread cleanup/propagation lỗi |
| `@Async` không thấy current user | Không có context propagation phù hợp |
| `getCredentials()==null` sau login | ProviderManager có thể đã xóa credentials |
| JWT token hợp lệ nhưng role cũ | Claims stale; cần revoke/live authorization |
| Login được nhưng `/admin` 403 | Thiếu ROLE_ADMIN, authorization độc lập với authentication |
| Error controller không thấy principal | ERROR dispatch/repository/request attribute config |
| SecurityContextHolder đọc null trong custom job | Job không thuộc request Servlet được bảo vệ |

## 15. Bài tập tự kiểm tra

**Câu 1.** `SecurityContextHolder` khác `SecurityContext` thế nào?

**Đáp:** Holder là API/strategy cho current execution; SecurityContext là object giữ Authentication.

**Câu 2.** `getContext()` luôn trả object thì user đã login chắc chưa?

**Đáp:** Chưa. Context có thể rỗng hoặc anonymous.

**Câu 3.** Vì sao cần dọn holder cuối request?

**Đáp:** Vì Servlet threads được tái sử dụng; nếu không dọn có thể làm rò identity sang request của người khác.

**Câu 4.** Dọn holder có xóa session đăng nhập không?

**Đáp:** Không. Session context có thể được repository khôi phục ở request kế tiếp.

**Câu 5.** `SecurityContextHolderFilter` trong Spring Security 6 có tự save context custom vừa set không?

**Đáp:** Không theo explicit-save model. Custom login muốn persist phải save vào SecurityContextRepository phù hợp.

**Câu 6.** `RequestAttributeSecurityContextRepository` có giữ login giữa hai HTTP requests không?

**Đáp:** Không. Nó phục vụ cùng logical request/dispatch; HttpSession repository hoặc cách khác mới giữ qua requests.

**Câu 7.** API stateless có Authentication được không?

**Đáp:** Có. Với Basic/Bearer hợp lệ, Authentication tồn tại cho chính request đó.

**Câu 8.** `SessionCreationPolicy.NEVER` có giống STATELESS không?

**Đáp:** Không. NEVER vẫn có thể dùng session có sẵn.

**Câu 9.** AnonymousAuthenticationToken có flag true. `.authenticated()` có cho vào không?

**Đáp:** Không. Framework phân biệt anonymous qua AuthenticationTrustResolver.

**Câu 10.** User login được nhưng `/admin` bị 403 vì sao?

**Đáp:** Authentication thành công nhưng thiếu ROLE_ADMIN hoặc điều kiện authorization khác.

**Câu 11.** Có thể dùng `@WithMockUser` để chứng minh HttpSession persistence không?

**Đáp:** Không. Nó mock Authentication; cần test POST login thật và request sau dùng cùng session.

**Câu 12.** Có nên lưu Authentication trong biến static dùng chung cho controller?

**Đáp:** Không, vì rò identity giữa users và threads.

**Câu 13.** Tác vụ async không thấy user, nên chuyển sang MODE_GLOBAL không?

**Đáp:** Không. Dùng context propagation được hỗ trợ hoặc truyền identity tối thiểu với reauthorization.

**Câu 14.** Khóa account trong DB có tự hủy mọi HttpSession/JWT không?

**Đáp:** Không mặc định. Cần revocation/live status/version checks theo yêu cầu hệ thống.

**Câu 15.** Tại sao public endpoint vẫn có anonymous token khi dùng permitAll?

**Đáp:** Vì permitAll là authorization, còn anonymous filter vẫn có thể hoạt động trong chain.

## 16. Tài liệu tham khảo

- Spring Security — **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 — **Persisting Authentication**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
- Spring Security 6.5 — **Session Management**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — **Explicit Save Migration**: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security — **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Spring MVC and Servlet API**: https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html
- Spring Security — **Concurrency Support**: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html

**Ghi nhớ:** Trong mỗi request, Spring Security **nạp hoặc tạo SecurityContext**, đặt Authentication hợp lệ, dùng context để ra quyết định authorization và **dọn context khỏi thread cuối request**. `SecurityContextHolder` chỉ là điểm truy cập hiện tại; nếu cần giữ login sang request sau phải có `SecurityContextRepository` và persistence flow đúng. Session-based login và stateless Basic có vòng đời danh tính khác nhau, nhưng cả hai đều phải ngăn việc rò Authentication giữa requests.
