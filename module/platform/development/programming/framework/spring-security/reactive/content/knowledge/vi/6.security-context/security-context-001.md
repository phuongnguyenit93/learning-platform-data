# Authentication, principal, credentials và GrantedAuthority trong SecurityContext

## 1. Mục tiêu và bức tranh tổng thể

Trong Spring Security reactive (Spring WebFlux), ứng dụng cần trả lời hai câu hỏi cho mỗi request:

1. **Xác thực (authentication):** người đang gửi request là ai, và bằng chứng đăng nhập đã được kiểm tra chưa?
2. **Phân quyền (authorization):** danh tính đã được xác thực có được phép truy cập tài nguyên hoặc thao tác này không?

Các đối tượng trong tiêu đề có mối quan hệ sau:

~~~text
Reactor Context của luồng xử lý request/subscription
└── Mono<SecurityContext> (do Spring Security quản lý)
    └── SecurityContext
        └── Authentication
            ├── principal           Ai đang đăng nhập? (UserDetails, Jwt, ...)
            ├── credentials         Bằng chứng: mật khẩu/token/... (có thể bị xóa)
            ├── authorities         Các GrantedAuthority đã được cấp
            ├── authenticated       Trạng thái tin cậy của authentication token
            └── details             Chi tiết bổ sung, không phải quyền
~~~

**`SecurityContext` chứa một `Authentication`**, còn `Authentication` gom thông tin danh tính, bằng chứng và quyền. `GrantedAuthority` không tự xác minh danh tính; nó diễn tả các quyền đã được nguồn xác thực đáng tin cậy gán cho người dùng.

Ở WebFlux, một khác biệt quyết định so với Servlet là ngữ cảnh bảo mật được truy cập qua **`ReactiveSecurityContextHolder` và Reactor Context** theo chuỗi reactive; không dựa vào việc mọi thao tác của request luôn chạy trên một ThreadLocal.

Sau bài học, bạn có thể:
- Phân biệt `SecurityContext`, `Authentication` và `java.security.Principal`.
- Hiểu `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `isAuthenticated()`, `getName()` và `getDetails()`.
- Giải thích vòng đời authentication token trước/sau khi xác minh, hành vi xóa credentials và ngữ nghĩa của anonymous.
- Lấy danh tính bên trong một `Mono`/`Flux` mà không `block()` trong WebFlux handler.
- Viết và kiểm thử endpoint có `ROLE_READER` / `ROLE_ADMIN` bằng Spring Boot WebFlux.

## 2. `SecurityContext` là gì?

`org.springframework.security.core.context.SecurityContext` là interface có nhiệm vụ giữ thông tin `Authentication` hiện tại. Hai phương thức chính:

~~~java
Authentication getAuthentication();
void setAuthentication(Authentication authentication);
~~~

`SecurityContextImpl` là implementation phổ biến. `getAuthentication()` có thể trả `null` khi context chưa có thông tin xác thực; ngoài ra, ở reactive, việc đọc `ReactiveSecurityContextHolder.getContext()` có thể trả `Mono.empty()` nếu không có context trong Reactor Context.

**Không đồng nhất “có `SecurityContext`” với “đã đăng nhập”.** Một context có thể chưa chứa authentication, hoặc chứa một authentication đại diện người dùng ẩn danh. Quyết định access phải được thực hiện bởi Spring Security authorization, theo rule và chính sách ứng dụng.

Một ví dụ thuần API (để minh họa cấu trúc, **chưa phải thao tác đăng nhập**) là:

~~~java
SecurityContext context = new SecurityContextImpl();
Authentication token = UsernamePasswordAuthenticationToken.unauthenticated(
    "linh", "mat-khau-chua-xac-minh"
);
context.setAuthentication(token);
~~~

Ở đây `token.isAuthenticated() == false`: token chỉ là **yêu cầu xác thực**, không phải bằng chứng đã đăng nhập. Việc tạo và đặt một object vào context không tự xác minh mật khẩu. Trong request WebFlux bình thường, hãy để security filters và authentication manager quản lý context.

## 3. `Authentication`: đối tượng trung tâm của xác thực

`org.springframework.security.core.Authentication` mở rộng `java.security.Principal`. Nó có hai vai trò theo giai đoạn:

- **Trước xác thực:** biểu diễn một yêu cầu để `ReactiveAuthenticationManager` kiểm tra; có thể chứa username/password/token do client cung cấp, `isAuthenticated() == false`.
- **Sau xác thực thành công:** biểu diễn danh tính đáng tin cậy cùng các authorities đã được xác định; một implementation phù hợp có `isAuthenticated() == true`. Spring Security đưa kết quả này vào `SecurityContext` theo cơ chế của filter/context repository.

Các API cốt lõi:

| API | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| `getPrincipal()` | Danh tính được xác minh hoặc đối tượng định danh trong yêu cầu | Ép mọi principal thành `String` hoặc `UserDetails` |
| `getCredentials()` | Bằng chứng như password, token; có thể là `null` sau xác thực | Trả về API, log, hoặc giữ mật khẩu lâu trong bộ nhớ |
| `getAuthorities()` | Các `GrantedAuthority` được cấp | Tin các quyền tự khai báo từ client |
| `isAuthenticated()` | Trạng thái authentication token được framework tin cậy; không đủ làm mọi quyết định quyền | Tự dùng boolean này làm kiểm tra phân quyền duy nhất |
| `getName()` | Tên định danh ở cấp `Principal`, phù hợp cho nhu cầu tên người dùng chung | Giả định tên là ID bất biến hoặc địa chỉ email |
| `getDetails()` | Metadata tùy cơ chế xác thực (ví dụ thông tin web authentication) | Nhầm metadata với quyền hoặc dữ liệu đã được kiểm chứng |

`Authentication` **không phải** một JSON record có cấu trúc cố định. Tùy phương thức đăng nhập, loại token và loại principal rất khác nhau. Khi viết code tái sử dụng, làm việc với interface trước, chỉ cast khi đã kiểm tra kiểu.

### 3.1. Principal là danh tính, không phải “mật khẩu”

Một số dạng `getPrincipal()` thực tế:

- Username/password: thường là `UserDetails` sau xác thực thành công.
- Bearer JWT: có thể là đối tượng `Jwt` bên trong `JwtAuthenticationToken`; `getName()` thường liên quan đến `sub` hoặc cấu hình claim name.
- OAuth2 login: có thể là `OAuth2User` hoặc `OidcUser`.
- Một custom authentication: có thể là kiểu principal do ứng dụng định nghĩa.

Do đó:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof UserDetails userDetails) {
    String username = userDetails.getUsername();
    // Chỉ sử dụng các trường đã được nguồn xác thực tin cậy xác minh.
}

String displayName = authentication.getName(); // API chung.
~~~

`getName()` thường thuận tiện hơn khi chỉ cần tên danh tính. Nhưng tên có thể được tái sử dụng hoặc thay đổi; nếu hệ thống cần khóa danh tính ổn định, hãy chọn định danh đáng tin cậy từ loại principal đã xác minh, ví dụ subject và issuer của token, hoặc user ID nội bộ.

**Không** giả định `principal.toString()` là an toàn để log hoặc trả ra client; nhiều implementation có thể chứa thêm thuộc tính không cần công bố.

### 3.2. Credentials là bằng chứng, không phải danh tính

Trước xác thực, `credentials` có thể là raw password; trong cơ chế bearer, có thể là token hoặc một dạng bằng chứng khác. Sau khi xác thực, nhiều implementation xóa thông tin nhạy cảm qua `eraseCredentials()`; `getCredentials()` lúc đó có thể trả `null`. **Không có bảo đảm mọi implementation/cơ chế đều xóa hết mọi credential**.

Luồng điển hình:

~~~text
Client gửi username/password
   ↓
UsernamePasswordAuthenticationToken chưa xác thực
   principal = username
   credentials = raw password
   authenticated = false
   ↓ ReactiveAuthenticationManager kiểm tra
Authentication đã xác thực
   principal = UserDetails hoặc domain principal
   credentials = thường đã xóa / null
   authorities = quyền đã được cấp
   authenticated = true
   ↓
SecurityContext lưu Authentication để authorization sử dụng
~~~

Cần phân biệt giữa:
- **Password hash** trong database: dữ liệu để kiểm chứng mật khẩu, không phải password plaintext.
- **Raw password/secret** nhập từ client: không lưu/log/serialize hoặc dùng làm thông tin người dùng.
- **Credentials trong `Authentication`**: giá trị tùy cơ chế và giai đoạn; có thể `null`.
- **Session ID/JWT**: có cách lưu, truyền và kiểm tra khác; không tự gán vào response/debug chỉ vì `getCredentials()` trả dữ liệu.

### 3.3. `isAuthenticated()` không tương đương `authenticated()` trong mọi trường hợp

`isAuthenticated()` là cờ trạng thái trên authentication token. Ví dụ `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` về mặt implementation, nhưng Spring Security **không** xem anonymous là người dùng đã đăng nhập khi đánh giá `authenticated()` qua cơ chế authorization mặc định.

Vì vậy, một bộ lọc phân quyền tự viết theo kiểu:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Tự cho phép dữ liệu nhạy cảm: KHÔNG NÊN.
}
~~~

là thiếu: nó có thể xử lý anonymous không đúng ý định. Hãy sử dụng `authorizeExchange(...).authenticated()` / `hasRole(...)`, method security (`@PreAuthorize`) hoặc API trust/authorization tương ứng thay cho kiểm tra boolean đơn lẻ.

## 4. `GrantedAuthority` là gì? Role, permission và scope

`GrantedAuthority` là interface biểu diễn quyền đã cấp. Phương thức cốt lõi:

~~~java
String getAuthority();
~~~

`SimpleGrantedAuthority` là implementation thường gặp, chứa một chuỗi tên authority. Ví dụ:

~~~java
new SimpleGrantedAuthority("ROLE_READER");
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("SCOPE_orders.read");
~~~

Đây là **ba giá trị string khác nhau**, không tự động mang cùng nghĩa. Một số implementation phức tạp có thể trả `null` từ `getAuthority()`; những implementation như vậy cần cơ chế xử lý riêng, thay vì giả định mọi quyền đều là string.

### 4.1. Role và authority khác nhau ra sao?

Theo quy ước mặc định trong Spring Security:

- `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`; lập trình viên **không truyền sẵn `ROLE_`** khi gọi `hasRole("ADMIN")`.
- `hasAuthority("ROLE_ADMIN")` kiểm tra chuỗi đúng bằng `ROLE_ADMIN`.
- `hasAuthority("orders:read")` kiểm tra chính xác `orders:read`; không tự thêm prefix.
- `hasAuthority("SCOPE_orders.read")` kiểm tra quyền với tiền tố `SCOPE_`, thường thấy trong cơ chế OAuth2 resource server khi scopes được chuyển đổi theo cấu hình mặc định tương ứng.

| Authorities trong `Authentication` | Quy tắc | Kết quả |
| --- | --- | --- |
| `["ROLE_READER"]` | `hasRole("READER")` | Được phép |
| `["ROLE_READER"]` | `hasRole("ADMIN")` | Bị từ chối |
| `["ROLE_ADMIN"]` | `hasAuthority("ROLE_ADMIN")` | Được phép |
| `["SCOPE_orders.read"]` | `hasAuthority("SCOPE_orders.read")` | Được phép |
| `["ROLE_ADMIN"]` | `hasAuthority("ADMIN")` | Bị từ chối (khác chuỗi) |

Ví dụ dùng JWT chỉ mang tính minh họa: không phải mọi claim scope/role đều tự trở thành `GrantedAuthority`. Việc chuyển `scope`/`scp` thành `SCOPE_*`, hoặc claim riêng thành `ROLE_*`, phụ thuộc converter/config và cơ chế xác thực được chọn. Người học phải xác minh **danh sách authorities thực tế** của authentication đã xác minh.

### 4.2. Không chấp nhận authorities do client tự tuyên bố

Ví dụ client gửi JSON `{"username":"linh","roles":["ROLE_ADMIN"]}` **không** chứng minh người đó có quyền admin. Chỉ cấp quyền sau khi backend xác minh danh tính và tra chính sách/nguồn quyền đáng tin cậy hoặc xác minh claims chữ ký hợp lệ theo cấu hình.

Thông thường `Authentication` chứa quyền đã được đưa vào bởi manager/provider đã xác minh. Authorization dùng các quyền ấy để ra quyết định. Đừng dùng mã như:

~~~java
UsernamePasswordAuthenticationToken.authenticated(
    request.username(), request.password(), request.authorities()
);
~~~

trên input chưa xác thực. Static factory `authenticated(...)` là API để tạo token **đã được tin cậy**; gọi nó trên input không kiểm tra là lỗi bảo mật. Hãy đưa token chưa xác thực cho manager, hoặc để framework tự xử lý request.

## 5. `SecurityContext` trong WebFlux sống ở đâu?

### 5.1. So sánh Servlet và reactive

| Mô hình | Nơi thường lấy context | Điều cần chú ý |
| --- | --- | --- |
| Spring MVC/Servlet | `SecurityContextHolder.getContext()` với chiến lược ThreadLocal mặc định | Các filter servlet quản lý context trên luồng xử lý |
| Spring WebFlux/Reactor | `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` | Reactor Context gắn với subscriber, chạy xuyên các toán tử reactive tương thích |

Trong WebFlux, đừng đọc `SecurityContextHolder.getContext()` bằng giả định ThreadLocal sẽ luôn đúng khi request chuyển luồng qua `flatMap`, `publishOn`, async I/O. Cũng không nên tự `subscribe()` trong handler để “lấy authentication” rồi chạy logic ngoài vòng đời request.

API đúng:

~~~java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(context -> Mono.justOrEmpty(context.getAuthentication()));
~~~

Điểm cần hiểu:
- `ReactiveSecurityContextHolder.getContext()` trả **publisher**; nó chưa buộc phải có giá trị khi bạn mới tạo chuỗi.
- Khi context không tồn tại, publisher có thể hoàn tất rỗng; nếu `context.getAuthentication() == null`, `Mono.justOrEmpty(...)` cũng rỗng.
- Khi có authentication, bạn dùng `map` / `flatMap` trên `Mono` để làm tiếp, **không chặn luồng**.
- Spring Security WebFlux thường điền context cho request thông qua các security filter/repository khi cơ chế xác thực thành công.
- Reactor Context là phần của chuỗi đăng ký; nó không đồng nghĩa với một session lưu trên server qua nhiều HTTP request. HTTP Basic, session login và Bearer JWT có cách duy trì/tái tạo danh tính giữa request khác nhau.

### 5.2. Đọc danh tính đúng trong một chuỗi reactive

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context -> Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authentication in Reactor Context")));
}
~~~

Đoạn trên là một phương thức minh họa trong ứng dụng có dependency `reactor-core` và Spring Security; nó phát lỗi nếu không có authentication. Trong web handler thực tế, nên để `SecurityWebFilterChain` từ chối request thiếu xác thực ở tầng HTTP, còn business logic xử lý danh tính hợp lệ đã được giao.

**Không** làm thế này trong reactive handler:

~~~java
// Sai ngữ cảnh trong WebFlux: ThreadLocal có thể không chứa danh tính request.
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

// Sai vòng đời: block() bên trong event loop có thể gây lỗi/chặn request.
String username = currentUsername().block();
~~~

Các đoạn trên được đưa vào để nhận diện anti-pattern, không dùng trong chương trình hoàn chỉnh.

### 5.3. Gắn context tạm thời bằng `contextWrite`

Khi cần viết test hoặc một pipeline minh họa, `ReactiveSecurityContextHolder.withAuthentication(authentication)` trả một Reactor `Context` để gắn vào subscription:

~~~java
Mono<String> lookup = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("<none>");

Authentication trusted = UsernamePasswordAuthenticationToken.authenticated(
    "linh",
    null,
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> withIdentity = lookup.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(trusted)
);
~~~

`lookup` không có context sẽ phát `"<none>"`, còn `withIdentity` có thể phát `"linh"`. Đặt `contextWrite` ở cuối đoạn pipeline có tác dụng với các toán tử **upstream** cùng subscription. `withAuthentication(...)` không xác minh mật khẩu; ở đây `trusted` là fixture dành cho test. Không tạo fixture như thế từ request client rồi coi là đăng nhập thành công.

Ngữ cảnh có thể tiếp tục đi qua `flatMap`/`publishOn` khi vẫn ở cùng pipeline Reactor được quản lý. Nó **không tự đảm bảo** lan truyền qua các chuỗi detached do bạn tự `subscribe()`, thread tự tạo, hoặc mọi callback của thư viện bên ngoài không tham gia Reactor; các ranh giới này cần giải pháp context propagation đúng thiết kế.

## 6. Dự án minh họa hoàn chỉnh: Java 17+, WebFlux, Spring Security

Ví dụ sau dùng **Spring Boot 3.3.13**, Spring Security do Boot quản lý phiên bản, Java 17+ và Gradle. Nó hiển thị **name, kiểu principal và authorities** của người dùng đã được xác thực, đồng thời **không bao giờ trả credentials**.

### 6.1. Cấu trúc

~~~text
reactive-security-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── SecurityContextDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    └── test/java/demo/
        ├── IdentityControllerTests.java
        └── ReactorContextScopeTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-security-context-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
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

Nếu dự án có Gradle Wrapper, dùng wrapper; ví dụ này chỉ liệt kê các tệp cần thiết để học và dùng Gradle đã được cài. Boot quản lý phiên bản Spring Security và Reactor nên không gắn phiên bản thủ công cho các dependency này.

### 6.2. Khởi tạo ứng dụng

`src/main/java/demo/SecurityContextDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }
}
~~~

### 6.3. Cấu hình xác thực và phân quyền

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

Trong demo:
- Basic authentication tiếp nhận username/password và dùng user store để xác minh; sau khi thành công, Spring Security có `Authentication` với principal phù hợp và các authorities.
- `reader` nhận `ROLE_READER`; `admin` nhận `ROLE_ADMIN` do `roles(...)` áp dụng quy ước tiền tố `ROLE_`.
- `/admin` yêu cầu `ROLE_ADMIN`. `/public` chỉ cần đi qua rule `permitAll()`; `/me` và mọi URL còn lại yêu cầu đăng nhập.
- Tắt form login để response của API chưa đăng nhập dễ quan sát là HTTP 401 khi dùng Basic.
- Mật khẩu trong ví dụ là giá trị cục bộ để kiểm thử; BCrypt mã hóa mật khẩu trong user store. Trong production, không hard-code thông tin xác thực và dùng HTTPS.

**Chú ý:** `@EnableWebFluxSecurity` làm rõ điểm bật WebFlux security; trong Spring Boot có starter phù hợp, auto-configuration thường đã đảm nhiệm phần này. Vai trò của `SecurityWebFilterChain` là luật HTTP; vai trò của `MapReactiveUserDetailsService` là nguồn danh tính demo. Không nhầm hai trách nhiệm.

### 6.4. Handler chỉ đọc dữ liệu an toàn từ `SecurityContext`

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class IdentityController {

    public record IdentityView(
        String name,
        String principalType,
        boolean authenticated,
        List<String> authorities
    ) {}

    @GetMapping("/public")
    Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<IdentityView> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(this::safeView)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)
            ));
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin");
    }

    private IdentityView safeView(Authentication authentication) {
        String principalType = authentication.getPrincipal() == null
            ? "<none>"
            : authentication.getPrincipal().getClass().getSimpleName();

        List<String> granted = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return new IdentityView(
            authentication.getName(),
            principalType,
            authentication.isAuthenticated(),
            granted
        );
    }
}
~~~

Đọc luồng `/me`:
1. `getContext()` lấy `Mono<SecurityContext>` **từ Reactor Context** của request.
2. `flatMap(... Mono.justOrEmpty(...))` chuyển context thành `Mono<Authentication>`, không phát phần tử nếu thiếu.
3. `map(this::safeView)` chuyển Authentication thành DTO với tên, kiểu principal, cờ trạng thái và danh sách authority.
4. `switchIfEmpty` là biện pháp phòng vệ trong controller; phần lớn request thiếu xác thực bị security filter từ chối **trước khi vào controller**.
5. Controller **không đọc `getCredentials()`**, không trả `UserDetails` toàn bộ và không log raw token/password.

`IdentityView.authenticated` có ích để quan sát ví dụ, **không phải** API quyết định quyền độc lập. Phân quyền thật được cấu hình tại `SecurityWebFilterChain` qua `authenticated()`, `hasRole("ADMIN")`.

Khi xác thực bằng Basic với `MapReactiveUserDetailsService` trong ví dụ, `principalType` thường là `"User"` (lớp `org.springframework.security.core.userdetails.User`). Nếu thay cơ chế bằng JWT/OIDC hoặc custom principal, trường này thay đổi; đó là lý do code chỉ đọc tên kiểu, không cast cứng.

### 6.5. Chạy và quan sát response

Từ thư mục dự án, yêu cầu JDK 17+ và Gradle tương thích:

~~~bash
gradle bootRun
~~~

Nếu có wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Trong shell bash/Git Bash, chạy:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
curl -s -u reader:reader-pass http://localhost:8080/me
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
~~~

Kết quả HTTP status của các lệnh 1, 2, 4, 5 theo thứ tự là:

~~~text
200
401
403
200
~~~

Lệnh 3 trả JSON có dữ liệu tương ứng như sau (dấu cách và thứ tự thuộc tính JSON có thể thay đổi):

~~~json
{
  "name": "reader",
  "principalType": "User",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
~~~

Lệnh 4 trả **403** vì `reader` đã đăng nhập nhưng thiếu `ROLE_ADMIN`. Lệnh 2 trả **401** vì chưa có credentials và demo bật HTTP Basic nhưng tắt form login. Các con số này là kỳ vọng của cấu hình mẫu, không nên suy rộng thành mọi deployment (exception handler, authentication entry point, CORS và các cơ chế khác có thể thay đổi biểu hiện HTTP).

Không tìm mật khẩu trong JSON: credential cần được kiểm tra rồi giảm thời gian tồn tại, không công bố cho client. Nếu chạy trên Windows PowerShell, nên dùng `curl.exe` thay vì alias `curl`; tùy hệ có thể cần đổi `/dev/null` thành `NUL`.

## 7. Kiểm thử ngữ cảnh và phân quyền

### 7.1. Kiểm thử HTTP với `WebTestClient`

`src/test/java/demo/IdentityControllerTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class IdentityControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void unauthenticatedCannotReadIdentity() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanInspectTrustedIdentityAndAuthorities() {
        client.get().uri("/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("reader")
            .jsonPath("$.principalType").isEqualTo("User")
            .jsonPath("$.authenticated").isEqualTo(true)
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER")
            .jsonPath("$.credentials").doesNotExist();
    }

    @Test
    void roleBasedAccessIsEnforcedBySecurityFilters() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }

    @Test
    void publicEndpointNeedsNoLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }
}
~~~

Các test kiểm tra một danh tính được xác minh bởi HTTP Basic trong request thật, rồi Spring Security dựng `Authentication`, gán authorities và dùng rule HTTP. Không giả lập “đã đăng nhập” bằng cách tự set boolean lên object client.

### 7.2. Kiểm thử Reactor Context có phạm vi theo subscription

`src/test/java/demo/ReactorContextScopeTests.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import static org.assertj.core.api.Assertions.assertThat;

class ReactorContextScopeTests {

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("<none>");
    }

    @Test
    void contextIsScopedToEachSubscription() {
        // Fixture đã được tin cậy CHỈ cho test, không được dựng từ input client.
        Authentication fixture = UsernamePasswordAuthenticationToken.authenticated(
            "linh",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        Mono<String> read = currentName();

        assertThat(read.block()).isEqualTo("<none>");
        assertThat(read.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(fixture)
        ).block()).isEqualTo("linh");
        assertThat(read.block()).isEqualTo("<none>");
    }

    @Test
    void contextSurvivesAReactorSchedulerChange() {
        Authentication fixture = UsernamePasswordAuthenticationToken.authenticated(
            "mai",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        Mono<String> readOnOtherScheduler = Mono.just(1)
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentName())
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(fixture));

        assertThat(readOnOtherScheduler.block()).isEqualTo("mai");
    }
}
~~~

Trong các test, `block()` là thao tác chờ tại biên kiểm thử đồng bộ; không sao chép `block()` vào handler WebFlux. Hai phép kiểm tra làm rõ:
- **Có context** hay **không có context** được quyết định theo subscription; cùng một publisher có thể cho kết quả khác nếu ngữ cảnh của lần subscribe khác nhau.
- `publishOn` thay scheduler nhưng không tự làm mất Reactor Context trong một chuỗi Reactor hợp lệ. Ngược lại, tự mở luồng/subscribe detached hoặc đi qua thư viện không hỗ trợ propagation có thể đòi hỏi cầu nối ngữ cảnh riêng.

Chạy tất cả test:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test` nếu dùng wrapper. Kỳ vọng sáu bài test trong hai class đều PASS, Gradle trả exit code 0. Log cụ thể thay đổi theo máy nên không ghi một dòng output Gradle cố định.

## 8. Xác thực JWT và principal khác username/password

Với Resource Server reactive, Spring Security có thể tạo `JwtAuthenticationToken` sau khi xác minh chữ ký, thời hạn và các điều kiện của JWT decoder. Khi đó:
- `getPrincipal()` thường là `Jwt` chứ không phải `UserDetails`.
- `getName()` thường gắn với subject hoặc claim đã cấu hình.
- `getAuthorities()` phụ thuộc cơ chế chuyển claims/scopes thành `GrantedAuthority`; ví dụ `SCOPE_read`.
- `getCredentials()` tùy loại authentication; đừng mặc định `null` hay cố đọc token rồi trả ra API.

**Ví dụ truy xuất type-safe minh họa** (chỉ hợp lệ khi resource server đã được cấu hình và có JWT authentication):

~~~java
if (authentication instanceof JwtAuthenticationToken jwtAuth) {
    String subject = jwtAuth.getToken().getSubject();
    // Dùng subject + issuer/tenant hoặc ID đã kiểm chứng
    // theo chính sách ứng dụng; không đưa raw JWT vào log.
}
~~~

Đoạn này cần import `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken` và dependency Spring Security OAuth2 Resource Server; **không nằm trong dự án mẫu Basic ở mục 6**. Nó minh họa vì sao cần kiểm tra kiểu trước khi truy cập thông tin riêng của một cơ chế xác thực.

Đừng cấp quyền admin chỉ vì token có một claim văn bản do client tự khai báo: JWT phải được xác minh đầy đủ, claim mapping phải do backend quy định, và phân quyền phải dựa vào authorities đáng tin cậy.

## 9. Những lỗi dễ gặp khi làm việc với `SecurityContext`

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `SecurityContextHolder.getContext()` như ThreadLocal cố định trong WebFlux | Có thể rỗng, lấy sai context hoặc thất lạc danh tính khi đổi luồng | Dùng `ReactiveSecurityContextHolder.getContext()` trong pipeline Reactor |
| Gọi `.block()` / tự `subscribe()` trong handler để lấy username | Chặn event loop, tách logic khỏi vòng đời request | Trả `Mono`/`Flux` và tiếp tục bằng `map`/`flatMap` |
| `(UserDetails) auth.getPrincipal()` không kiểm tra kiểu | `ClassCastException` khi đổi sang JWT/OIDC/custom auth | `getName()` hoặc `instanceof` theo cơ chế |
| Đọc và trả `getCredentials()` trong DTO/log | Lộ raw password, bearer token hoặc secret | Không trả credentials; chỉ dùng dữ liệu public được kiểm soát |
| Coi `isAuthenticated()` luôn là “user thật đăng nhập” | Anonymous có thể bị nhận sai | Dùng rule `authenticated()` và framework authorization |
| Tin roles/authorities gửi trong JSON từ client | Leo thang đặc quyền | Chỉ nhận authority từ manager, user store hoặc claims đã xác minh |
| Dùng `hasRole("ADMIN")` nhưng cấp `"ADMIN"` thay vì `"ROLE_ADMIN"` | Không khớp quyền | Nhất quán với quy ước prefix hoặc dùng `hasAuthority` đúng chuỗi |
| Tạo authentication đã xác thực bằng `authenticated(...)` từ input chưa xác minh | Vượt qua bước xác thực | Chỉ dùng sau khi xác minh đáng tin cậy; trong test dùng fixture rõ ràng |
| Cho rằng Reactor Context tự tồn tại qua request mới | Nhầm cơ chế duy trì đăng nhập | Session hoặc token phải được cơ chế bảo mật tải/xác thực ở từng request |
| Coi `getDetails()` hay `principal.toString()` luôn an toàn để log | Có thể làm lộ metadata/secret | Chỉ log thông tin tối thiểu, không nhạy cảm |
| Dựa vào danh tính từ một publisher đã được subscribe độc lập | Ngữ cảnh có thể không được truyền sang chuỗi detached | Duy trì cùng pipeline hoặc dùng phương án context propagation được hỗ trợ |
| Đưa `SecurityContext` có `Authentication` `null` vào authorization và coi đó là thành công | Bỏ qua điều kiện danh tính | Kiểm tra tín hiệu rỗng/anonymous; dùng web security filter để quyết định |

### 9.1. Vì sao không nên cache `Authentication` toàn cục?

`Authentication` mang danh tính và quyền **theo request/user**. Lưu nó vào static field, singleton state hoặc cache chia sẻ mà không ràng buộc đúng principal/session sẽ có nguy cơ trộn quyền giữa người dùng. Nếu cần cache dữ liệu người dùng, cache theo khóa danh tính và chính sách phù hợp; không lấy một object SecurityContext hiện tại áp cho mọi request.

### 9.2. Phân biệt `SecurityContext` với HTTP session

- `SecurityContext` là đối tượng chứa authentication ở thời điểm thực thi.
- **Reactor Context** là cơ chế lan truyền dữ liệu theo subscription reactive.
- **HTTP session** là cơ chế có thể lưu trạng thái qua nhiều request, tùy cấu hình security.
- **Bearer token/JWT** thường được gửi theo từng request để phía server xác thực và xây lại `Authentication`; cách tổ chức có thể stateless.

Một hệ thống có thể dùng Reactor Context **đồng thời** với session, hoặc Reactor Context với bearer token; không nên đánh đồng chúng.

## 10. Câu hỏi kiểm tra và lời giải

1. **`SecurityContext` thường giữ đối tượng nào?** `Authentication`; có thể chưa có authentication.
2. **`principal` có luôn là chuỗi username không?** Không. Có thể là `UserDetails`, `Jwt`, `OAuth2User` hoặc domain principal.
3. **`getCredentials() == null` có nghĩa xác thực thất bại không?** Không. Credentials có thể đã được xóa sau khi xác thực thành công.
4. **`getAuthorities()` có làm authentication tự hợp lệ không?** Không. Quyền cần đến từ nguồn đáng tin cậy sau xác thực.
5. **`hasRole("ADMIN")` thường cần chuỗi authority nào?** `ROLE_ADMIN`.
6. **Một `AnonymousAuthenticationToken` có thể `isAuthenticated() == true` không?** Có; đừng dùng cờ ấy làm kiểm tra phân quyền đơn lẻ.
7. **Trong WebFlux, đọc context qua đâu?** `ReactiveSecurityContextHolder.getContext()`, trả `Mono<SecurityContext>`.
8. **Vì sao không dùng `SecurityContextHolder` ThreadLocal như Servlet?** WebFlux có thể đổi thread trong cùng pipeline; Reactor Context gắn theo subscription.
9. **`contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` có tự kiểm tra password không?** Không; nó chỉ gắn fixture/context. Chỉ dùng với authentication đã được tin cậy.
10. **Tại sao request `/me` với reader được 200 nhưng `/admin` được 403?** Reader được xác thực, nhưng thiếu `ROLE_ADMIN`.
11. **`@EnableReactiveMethodSecurity` có thay `SecurityWebFilterChain` không?** Không; bảo mật phương thức là lớp bổ sung, có thể dựa trên authentication trong Reactor Context.
12. **Có nên trả nguyên object `Authentication` ra HTTP response không?** Không. Hãy tạo DTO công bố ít nhất thông tin cần thiết, bỏ credentials và dữ liệu nhạy cảm.

## 11. Tài liệu chính thức

- Spring Security, API `Authentication`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/Authentication.html
- Spring Security, API `SecurityContext`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/SecurityContext.html
- Spring Security, API `GrantedAuthority`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html
- Spring Security, API `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security, reactive method security và Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security, WebFlux security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Ghi nhớ:** `SecurityContext` là vỏ chứa `Authentication`; `principal` trả lời “ai?”, `credentials` là bằng chứng cần bảo mật, `GrantedAuthority` trả lời “được cấp những quyền gì?”, và reactive authorization dùng những thông tin **đã xác minh** ấy thông qua ngữ cảnh Reactor của request.
