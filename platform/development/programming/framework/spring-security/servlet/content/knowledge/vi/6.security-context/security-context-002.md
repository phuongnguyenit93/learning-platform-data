# Authentication trước và sau xác thực: principal, credentials, authorities

Trong Spring Security Servlet, `Authentication` là đối tượng mô tả **một yêu cầu chứng minh danh tính** hoặc **kết quả chứng minh danh tính**. Cùng một interface, nhưng ý nghĩa dữ liệu trước khi kiểm chứng và sau khi kiểm chứng rất khác nhau. Nếu không phân biệt hai trạng thái này, bạn có thể nhầm username do client tự khai là người dùng đã đăng nhập, nhầm credentials với quyền truy cập, hoặc tin rằng `isAuthenticated() == true` luôn bảo đảm người dùng thật đã đăng nhập.

Bài này tập trung vào ba thành phần **principal – credentials – authorities** và sự chuyển đổi của chúng trong luồng xác thực Spring Security trên Servlet stack. Ví dụ áp dụng Java 17+, Spring Boot 3.x và Spring Security 6.x; phần mã chạy được dùng Spring Boot 3.3.5. Những tài khoản và mật khẩu cố định chỉ phục vụ chạy thử cục bộ.

Sau bài học, bạn có thể:

- Nêu chính xác `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `getDetails()`, `getName()` và `isAuthenticated()` cung cấp thông tin gì.
- So sánh `UsernamePasswordAuthenticationToken` **chưa xác thực** và `Authentication` **đã xác thực** mà `AuthenticationManager` trả về.
- Giải thích vì sao phải để một `AuthenticationProvider` có thẩm quyền kiểm chứng credentials trước khi xem kết quả là đáng tin cậy.
- Nhận diện khác biệt giữa anonymous, remember-me và xác thực đầy đủ; tránh kiểm tra quyền bằng một cờ boolean đơn giản.
- Dùng `SecurityContextHolder`, HTTP Basic và MockMvc để quan sát principal/authorities an toàn mà không tiết lộ password.

## 1. Interface Authentication chứa thông tin gì?

`org.springframework.security.core.Authentication` vừa là một `Principal` của Java, vừa mang các thông tin liên quan đến xác thực và quyền. Các thành phần cốt lõi:

| Phương thức | Ý nghĩa | Ví dụ trước xác thực | Ví dụ sau xác thực |
| --- | --- | --- | --- |
| `getPrincipal()` | Chủ thể mà authentication đại diện; kiểu dữ liệu tùy cơ chế | Chuỗi `"reader"` do request cung cấp | Thường là `UserDetails` đã được nạp và kiểm chứng trong username/password flow |
| `getCredentials()` | Bằng chứng sử dụng để chứng minh danh tính | Raw password, token hoặc credential tương ứng | Có thể là `null` sau khi được xóa để giảm rủi ro rò rỉ |
| `getAuthorities()` | Các `GrantedAuthority` được gắn với authentication | Với token login chưa kiểm chứng thường rỗng | Ví dụ `ROLE_READER`, `REPORT_READ` do nguồn đáng tin cấp |
| `getDetails()` | Thông tin bổ sung về request/nguồn xác thực | Có thể là metadata về request | Có thể giữ metadata phù hợp; không mặc định là quyền |
| `isAuthenticated()` | Cờ trạng thái của object authentication | `false` đối với login token chưa kiểm chứng | `true` với kết quả xác thực thông thường |
| `getName()` | Tên đại diện được rút ra từ principal | Thường là username đã được cung cấp | Thường là username trong principal đã được kiểm chứng |

**Không có contract chung rằng principal luôn là String hoặc UserDetails.** Trong một cơ chế khác, principal có thể là kiểu `Jwt`, `OAuth2User`, một đối tượng custom hoặc dữ liệu khác. Khi dùng code production, hãy kiểm tra kiểu thực tế hoặc dùng API trừu tượng như `getName()` nếu chỉ cần tên.

**Không có contract rằng credentials luôn là password**. Với HTTP Basic, credentials thường là mật khẩu. Với bearer authentication, credentials có thể là token hoặc đã được loại bỏ. Credentials là *bằng chứng*, còn authorities là *quyền đã được xác định*; chúng giải quyết hai vấn đề khác nhau.

`getDetails()` cũng không phải authorities. Ví dụ IP, session id hoặc metadata thiết bị không tự cấp role. Tùy dự án, details có thể vắng mặt hoặc do application tự thêm; không nên dùng chúng làm bằng chứng xác thực nếu chưa được kiểm chứng theo thiết kế.

## 2. Trước xác thực: identity claim chưa phải identity được tin cậy

Khi người gọi nhập username/password, ứng dụng mới chỉ có **thông tin người gọi tự khai**. Ở tầng Spring Security, một biểu diễn phổ biến là:

~~~java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    "reader",
    "reader-pass"
);
~~~

Đây là mảnh mã đặt trong một method, cần import `org.springframework.security.core.Authentication` và `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`. Factory `unauthenticated` tạo một token có:

- `getPrincipal()` là `"reader"`: một **claim** do phía gọi cung cấp, chưa được chứng minh.
- `getCredentials()` là `"reader-pass"`: raw credential cần được kiểm chứng; giữ nó lâu hoặc ghi log đều có rủi ro.
- `getAuthorities()` thường là tập rỗng: chưa thể tự cấp `ROLE_READER` chỉ từ username.
- `isAuthenticated()` là `false`.

Không lấy giá trị `request.getName()` rồi lập tức ghi “reader đã đăng nhập”. Tên xuất hiện trước xác thực là dữ liệu đầu vào chưa đáng tin. Tương tự, client gửi chuỗi role trong JSON/body/header **không** có nghĩa server phải gắn role đó vào `Authentication`.

### Phân biệt ba câu hỏi

1. **Ai được khai báo?** `principal` trong token request.
2. **Có bằng chứng nào?** `credentials` trong token request.
3. **Bằng chứng có được chấp nhận?** Chỉ biết sau khi một cơ chế authentication đáng tin xử lý thành công.

Giả sử attacker gửi `username=admin` và một password sai: trước xác thực, token vẫn có principal `admin`, nhưng điều đó tuyệt đối không có nghĩa attacker là admin. Cờ `isAuthenticated()==false` và việc chưa có authorities đáng tin thể hiện trạng thái chưa được kiểm chứng.

### Tại sao token request không nên được đưa thẳng vào SecurityContext?

`SecurityContext` được các thành phần bảo mật dùng để xác định danh tính hiện tại. Nếu application đặt một authentication tự dựng vào context rồi coi là trusted mà không kiểm chứng, nó đã phá vỡ ranh giới tin cậy. Trong luồng chuẩn, filter nhận credentials → gọi `AuthenticationManager` → provider kiểm chứng → nhận authentication kết quả → đưa kết quả vào context theo cơ chế phù hợp.

**Quy tắc an toàn:** token được xây dựng từ dữ liệu request phải là *yêu cầu xác thực*, không được biến thành object “đã xác thực” chỉ vì client khai tên hoặc authority.

## 3. AuthenticationManager và AuthenticationProvider chuyển trạng thái như thế nào?

`AuthenticationManager` là điểm vào trừu tượng để kiểm chứng một `Authentication` chưa xác thực. Với ứng dụng username/password thông dụng, Spring Security có thể sử dụng `ProviderManager`, gọi `AuthenticationProvider` phù hợp với loại token. `DaoAuthenticationProvider` là một provider quen thuộc, có thể dùng `UserDetailsService` để tải user và `PasswordEncoder` để so sánh raw password với password hash được lưu.

Luồng khái niệm khi gọi HTTP Basic:

~~~text
HTTP request
  Authorization: Basic <base64(username:password)>
        |
        v
BasicAuthenticationFilter
  -> nhận username/password
  -> Authentication request (unauthenticated)
        |
        v
AuthenticationManager / ProviderManager
  -> tìm AuthenticationProvider hỗ trợ token
  -> tìm UserDetails từ UserDetailsService
  -> PasswordEncoder.matches(rawPassword, encodedPassword)
        |
        +---- sai / user không hợp lệ ----> AuthenticationException
        |                                  -> entry point, thường 401 cho Basic
        |
        +---- đúng ----> Authentication kết quả (authenticated)
                         principal đã được xác định
                         authorities từ nguồn đáng tin
                         credentials có thể bị xóa
                               |
                               v
                         SecurityContext của request
                               |
                               v
                         authorization
                               |
                          +----+----+
                          |         |
                        cho qua   từ chối
                          |         |
                       controller  403/...
~~~

Header Basic chỉ là Base64 của username/password, **không phải mã hóa bảo mật dữ liệu**. Luôn dùng HTTPS khi truyền credentials thực tế. Filter, manager và provider có thể khác khi bạn dùng form login, JWT, OAuth2 hoặc authentication custom; nhưng ranh giới giữa *dữ liệu tự khai* và *kết quả đã được xác minh* vẫn phải tồn tại.

Một contract quan trọng:

~~~java
Authentication verified = authenticationManager.authenticate(request);
~~~

Đây là **mảnh mã minh họa**; `authenticationManager` là một instance có provider được cấu hình phù hợp. `authenticate(...)` hoặc trả kết quả đáng tin theo provider, hoặc ném `AuthenticationException`; không nên lấy `request` ban đầu làm kết quả chỉ vì đã gọi phương thức. Kết quả có thể là **object mới** với principal và authorities khác dữ liệu đầu vào; code không nên dựa vào `request == verified`.

Đừng bắt tất cả exception rồi tự dựng authentication thành công để “cho người dùng vào”. Exception xác thực phải được xử lý bởi cơ chế HTTP/entry point hoặc một luồng failure đã thiết kế, và không được dẫn tới cấp quyền trái phép.

## 4. Sau xác thực: principal được xác nhận, authorities trở nên có ý nghĩa

Với tài khoản `reader` mà server có dữ liệu như:

~~~text
username:    reader
password:    <BCrypt hash được lưu>
authorities: [ROLE_READER]
~~~

khi password đúng, provider thường trả một `UsernamePasswordAuthenticationToken` ở trạng thái đã xác thực. Với Spring Security 6.x và `DaoAuthenticationProvider` thông dụng:

| Thuộc tính | Token chưa xác thực | Token sau xác thực thành công |
| --- | --- | --- |
| Principal | Username do client gửi, ví dụ `"reader"` | Thường là `UserDetails` chứa username từ server |
| Credentials | Raw password trong request | Có thể tạm tồn tại trong provider, sau đó thường bị xóa bởi `ProviderManager` |
| Authorities | Rỗng hoặc chưa được tin cậy | `ROLE_READER` lấy từ `UserDetails` đáng tin |
| `isAuthenticated()` | `false` | `true` |
| Ý nghĩa | Đề nghị xác thực | Kết quả được provider xác thực |
| Có nên đặt vào context như authenticated principal? | Không, nếu chưa kiểm chứng | Có, thông qua luồng security phù hợp |

`DaoAuthenticationProvider` thường dùng username đã được kiểm chứng để xác định principal; loại principal có thể cấu hình, vì vậy đừng giả định mọi provider luôn trả `UserDetails`. Kết quả còn có thể chứa details hoặc custom information tùy ứng dụng.

### Vì sao không dùng lại password để chứng minh đã đăng nhập?

Sau authentication, authorization **không cần nhìn vào raw password**. Nó cần authentication đã được xác thực cùng authorities cần thiết. Trong cơ chế thông dụng, `ProviderManager` bật `eraseCredentialsAfterAuthentication` và gọi việc xóa credentials ở kết quả hỗ trợ `CredentialsContainer`. Vì vậy:

- `getCredentials() == null` sau khi login là hành vi có thể hoàn toàn bình thường.
- Không dùng điều kiện “credentials khác null” để xác định người dùng đã login.
- Không coi việc credentials đã bị xóa là dấu hiệu xác thực thất bại.
- Không lưu/serialize toàn bộ `Authentication` vào response hay log, vì tùy provider và cấu hình, một số phần nhạy cảm có thể vẫn còn.

Việc xóa credentials phụ thuộc loại token, manager và cấu hình thực tế; không có cam kết rằng **mọi implementation** đều luôn xóa mọi secret. Nếu ứng dụng dùng custom provider, cần audit việc xóa dữ liệu nhạy cảm riêng. Nếu cache dùng chung một object user có password mà sau xác thực lại bị erase trên chính object đó, có thể gây vấn đề cho các lần authenticate sau; cần thiết kế cache/user object phù hợp, không giải quyết bằng cách vô hiệu xóa credentials một cách tùy tiện.

## 5. Authorities: role, permission và các trường hợp gây nhầm lẫn

`Authentication.getAuthorities()` trả về `Collection<? extends GrantedAuthority>`. Mỗi authority biểu diễn một quyền đã được xác định, thường được đặt tên bằng chuỗi, nhưng ý nghĩa cụ thể thuộc về cơ chế phân quyền của ứng dụng.

Ví dụ:

~~~text
principal: reader
authorities:
  ROLE_READER
  ARTICLE_READ
  REPORT_EXPORT
~~~

Khi dùng Spring Security với quy ước mặc định:

- `hasRole("READER")` thường kiểm tra authority `ROLE_READER`.
- `hasAuthority("ROLE_READER")` kiểm tra đúng authority `ROLE_READER`.
- `hasAuthority("ARTICLE_READ")` kiểm tra đúng chuỗi `ARTICLE_READ`.
- `hasRole("ARTICLE_READ")` thường tìm `ROLE_ARTICLE_READ`, tức **khác** quyền `ARTICLE_READ`.

Factory `User.withUsername("reader").roles("READER")` tạo authority `ROLE_READER`; còn `authorities("ARTICLE_READ")` dùng đúng authority string khai báo. Tiền tố role có thể tùy chỉnh ở ứng dụng, do đó luôn kiểm tra cách cấp và cách so sánh quyền.

Một user **đăng nhập thành công** chưa chắc **được phép** gọi endpoint cụ thể. Đã xác thực là bước chứng minh danh tính; authorization là bước so authorities của danh tính đó với yêu cầu của resource.

| Authentication | Cần truy cập | Kết luận |
| --- | --- | --- |
| Reader có `ROLE_READER` | `authenticated()` | Cho qua |
| Reader có `ROLE_READER` | `hasRole("ADMIN")` | Từ chối, thường 403 |
| Reader có `ROLE_READER` | `hasAuthority("ARTICLE_READ")` | Từ chối nếu không có `ARTICLE_READ` |
| Admin có `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho qua |
| Chưa có login hợp lệ | `authenticated()` | Với HTTP Basic thường nhận 401/challenge |

Đừng gắn authorities lấy thẳng từ HTTP body/query/header chưa tin cậy. Nguồn authority nên là user store, claim token **đã được xác thực chữ ký và ràng buộc phù hợp**, dịch vụ phân quyền đáng tin hoặc provider custom có kiểm chứng.

## 6. Cảnh báo quan trọng: isAuthenticated() chưa đủ để nói “người dùng đã đăng nhập”

Ở Spring Security, `AnonymousAuthenticationFilter` có thể tạo một `AnonymousAuthenticationToken` với principal như `anonymousUser`. Đáng chú ý: token anonymous thường có **`isAuthenticated() == true`** theo trạng thái nội bộ của object, nhưng **nó vẫn là anonymous**, không được `authenticated()` xem như một user đã đăng nhập thật.

Điều này nghe mâu thuẫn nếu chỉ nhìn boolean. Lý do là framework sử dụng những khái niệm như `AuthenticationTrustResolver` để phân biệt anonymous/remember-me/fully authenticated khi thực thi chính sách authorization.

Cũng cần phân biệt:

- **Anonymous:** chưa có identity thực đã được xác thực, dù context có một `Authentication` anonymous.
- **Remember-me:** có thể được khôi phục qua cookie đã được xử lý theo cơ chế remember-me; trạng thái này có thể được cho phép bởi `authenticated()` nhưng không thỏa `fullyAuthenticated()`.
- **Fully authenticated:** thường là kết quả xác thực thông qua cơ chế yêu cầu credentials đầy đủ, theo định nghĩa policy của Spring Security.
- **Pre-authenticated:** một provider/filter có thể tin danh tính do hệ thống upstream đã xác thực; cách xác minh và contract tin cậy khác username/password.
- **Bearer/JWT:** principal và authorities có thể sinh từ token đã kiểm chứng, không nhất thiết là `UserDetails` hoặc password.

Trong code business, kiểm tra một cách ngây thơ:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

boolean accepted = authentication != null && authentication.isAuthenticated();
~~~

là **chưa đủ** để kết luận người gọi không phải anonymous. Đây là đoạn minh họa anti-pattern, không nên dùng làm guard cho dữ liệu nhạy cảm.

**Ưu tiên** khai báo policy bằng `authorizeHttpRequests(auth -> auth.anyRequest().authenticated())`, `fullyAuthenticated()` hoặc authority rule phù hợp. Với kiểm tra thủ công đặc biệt, cần sử dụng cơ chế trust resolver/policy nhất quán, đồng thời kiểm tra boundary phù hợp. Tránh tự tạo logic authorization dựa vào một cờ khi framework đã cung cấp authorization API.

## 7. SecurityContext: Authentication sau xác thực xuất hiện ở đâu?

Trong Servlet flow thông dụng, security filters tải/tạo `SecurityContext` phù hợp, thiết lập authentication sau khi kiểm chứng credentials, rồi cho các filter phía sau và controller quan sát trạng thái đó.

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String name = current.getName();
    Collection<? extends GrantedAuthority> authorities =
        current.getAuthorities();
}
~~~

Đây là code minh họa cần import `SecurityContextHolder`, `Authentication`, `GrantedAuthority` và `Collection`. Nó có ích trong controller/service chạy trong cùng ngữ cảnh security, nhưng **không** được lấy context để suy luận rằng mọi request lúc nào cũng có logged-in user: context có thể không có Authentication hoặc chỉ có anonymous token.

Trong ứng dụng Servlet, `SecurityContextHolder` mặc định thường sử dụng `ThreadLocal` để giữ context đang xử lý. Spring Security có filter chịu trách nhiệm thiết lập/dọn context theo vòng đời request. Không tự dùng `SecurityContextHolder.getContext().setAuthentication(...)` từ controller với dữ liệu chưa kiểm chứng; thao tác đó có thể làm ứng dụng tin sai danh tính.

### Context không đồng nghĩa với session

`SecurityContext` mô tả trạng thái danh tính hiện tại; `SecurityContextRepository`/session policy quyết định cách context được tải/lưu giữa các request khi áp dụng. Việc Authentication được thấy trong controller của **một** request không chứng minh nó được persist sang request tiếp theo.

Với HTTP Basic, client thường gửi lại credentials trên mỗi request. Với session login, cookie và session có thể giúp tải lại context. Với bearer token, client gửi token tương ứng mỗi request. Các cơ chế đó quyết định dữ liệu được thiết lập và độ tin cậy, nhưng code đọc context ở điểm sau authentication vẫn dùng cùng contract.

Khi code chạy trong executor, `@Async` hoặc thread mới, context không tự động được chuyển đúng sang mọi thread chỉ vì request gốc đã có danh tính. Cần dùng cơ chế propagation phù hợp của Spring Security và xóa context đúng vòng đời, không dùng static field giữ Authentication theo người dùng.

## 8. Ví dụ Java 17+/Spring Boot: quan sát trạng thái trên Servlet request

Ví dụ gồm một ứng dụng Spring MVC với HTTP Basic, hai tài khoản in-memory và các endpoint để quan sát danh tính đã xác thực. Mục đích là phân biệt rõ **token yêu cầu trước xác thực** trong unit test với **kết quả đã xác thực** trong controller, đồng thời thử authorization.

### 8.1. Cấu trúc tệp

~~~text
authentication-states-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authstate/
    │   ├── AuthenticationStatesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── IdentityController.java
    └── test/java/example/authstate/
        └── AuthenticationStatesTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'authentication-states-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý phiên bản các module Spring Security thông qua dependency management phù hợp. Không ép một phiên bản riêng của `spring-security-core` trong khi các artifact khác vẫn theo Boot BOM.

### 8.2. Class khởi động

Tệp `src/main/java/example/authstate/AuthenticationStatesApplication.java`:

~~~java
package example.authstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationStatesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationStatesApplication.class, args);
    }
}
~~~

### 8.3. Authentication và authorization configuration

Tệp `src/main/java/example/authstate/SecurityConfiguration.java`:

~~~java
package example.authstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

Ở đây `UserDetailsService` lưu user và authorities được server định nghĩa. HTTP Basic nhận username/password, provider đối chiếu hash với encoder; sau khi thành công, authorities mới được đưa vào kết quả trusted Authentication.

Các chuỗi `reader-pass` và `admin-pass` chỉ dành cho ví dụ học tập chạy cục bộ. Trong triển khai thật, dùng nguồn user phù hợp và cơ chế quản lý bí mật an toàn.

### 8.4. Quan sát principal và authorities trong controller

Tệp `src/main/java/example/authstate/IdentityController.java`:

~~~java
package example.authstate;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public String currentIdentity() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return "name=" + authentication.getName()
            + ";authenticated=" + authentication.isAuthenticated()
            + ";authorities=" + authorities;
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }
}
~~~

`/api/me` yêu cầu `authenticated()` theo rule fallback, nên khi controller được gọi theo cấu hình này, Authentication thực thông thường đã qua quy trình xác thực. Endpoint chỉ hiển thị **name, cờ authenticated và authorities**, không hiển thị principal object, credentials, details hay toàn bộ token. Trong ứng dụng thật, ngay cả danh sách authorities cũng cần xem có nên công khai cho client không; ở đây chỉ để học.

Phần `authentication.isAuthenticated()` trong response là một **giá trị quan sát**, không phải guard kiểm tra quyền của controller. Chính Spring Security filter chain đã áp dụng `authenticated()` trước khi cho request đến handler. Điều này tránh nhầm boolean với tính chất "không phải anonymous".

### 8.5. Test hai trạng thái và các nhánh HTTP

Tệp `src/test/java/example/authstate/AuthenticationStatesTests.java`:

~~~java
package example.authstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationStatesTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginRequestTokenIsNotYetAuthenticated() {
        Authentication before = UsernamePasswordAuthenticationToken
            .unauthenticated("reader", "reader-pass");

        assertFalse(before.isAuthenticated());
        assertEquals("reader", before.getPrincipal());
        assertEquals("reader-pass", before.getCredentials());
        assertTrue(before.getAuthorities().isEmpty());
    }

    @Test
    void publicRequestWorksWithoutLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void missingCredentialsReturnBasicChallenge() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void badCredentialsAreRejected() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validReaderCredentialsCreateTrustedIdentity() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=reader;authenticated=true;authorities=ROLE_READER"));
    }

    @Test
    void validAdminCredentialsCarryAdminRole() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=admin;authenticated=true;authorities=ROLE_ADMIN"));
    }

    @Test
    void verifiedReaderStillLacksAdminAuthority() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void verifiedAdminMayAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    @WithMockUser(username = "synthetic", roles = "READER")
    void testIdentityIsNotProofOfPasswordAuthentication() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "name=synthetic;authenticated=true;authorities=ROLE_READER"));
    }
}
~~~

Test đầu tiên chứng minh đối tượng mới được tạo từ username/password chỉ mang trạng thái **chưa xác thực**. Các test MockMvc dùng `httpBasic(...)` gửi credentials qua filter rồi xác minh controller chỉ nhận request hợp lệ; kết quả body quan sát được principal name, cờ authenticated và authority.

Test `@WithMockUser` cố tình dùng tên `synthetic` **không tồn tại trong UserDetailsService**. Nó chứng minh Spring Security Test có thể gắn trusted test identity để kiểm tra controller/authorization mà **không chạy kiểm tra password thật**. Vì vậy, đừng dùng một mình `@WithMockUser` để tuyên bố password encoder hay provider hoạt động đúng.

### 8.6. Chạy test và gọi HTTP thủ công

Trong thư mục project với Gradle tương thích đã cài:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có Gradle wrapper, ưu tiên `./gradlew test` / `./gradlew bootRun`; trên Windows dùng `gradlew.bat test` / `gradlew.bat bootRun`. Tệp Java có dependency Spring nên không thể chạy chỉ bằng `javac`/`java` mà không thiết lập classpath tương ứng.

Terminal khác:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:wrong http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
~~~

Với cấu hình trên, kết quả chính cần quan sát:

| Request | Status dự kiến | Body khi thành công |
| --- | --- | --- |
| GET `/public/ping` không credentials | 200 | `pong` |
| GET `/api/me` không credentials | 401 | Không ràng buộc body lỗi |
| GET `/api/me` với reader đúng password | 200 | `name=reader;authenticated=true;authorities=ROLE_READER` |
| GET `/api/me` với reader sai password | 401 | Không ràng buộc body lỗi |
| GET `/api/admin` với reader đúng password | 403 | Không ràng buộc body lỗi |
| GET `/api/admin` với admin đúng password | 200 | `admin-only` |

Header `WWW-Authenticate` thường xuất hiện trong nhánh HTTP Basic cần challenge; các header và body lỗi còn phụ thuộc cấu hình/phiên bản. Mật khẩu không xuất hiện trong response thành công. Nếu muốn quan sát việc credentials bị xóa sau xác thực, hãy dùng debugger trong môi trường học tại code bảo mật thích hợp, thay vì in chúng ra log hoặc trả cho client.

## 9. Từ Authentication tới authorization: 401/403 phát sinh ở đâu?

Đường đi với request thành công:

1. `BasicAuthenticationFilter` (khi HTTP Basic được cấu hình) đọc thông tin username/password.
2. Tạo authentication request chưa xác thực, thường có principal String và credentials dạng raw.
3. `AuthenticationManager` chọn provider; provider kiểm tra user/password.
4. Provider trả authentication đã xác thực với principal/authorities đáng tin.
5. SecurityContext chứa authentication kết quả trong request hiện hành.
6. Authorization rule đánh giá `authenticated()` hoặc `hasRole(...)`.
7. Nếu được phép, request đi đến controller; nếu bị từ chối, security xử lý nhánh denial.

Sự khác nhau giữa **401** và **403** trong ví dụ:

- **401**: không có hoặc không chấp nhận credentials để vào URL cần authentication. HTTP Basic entry point thường trả challenge.
- **403**: reader đã được xác thực nhưng authorities không chứa `ROLE_ADMIN`. Authentication hợp lệ không đồng nghĩa có mọi quyền.

Trong một ứng dụng khác, 403 cũng có thể do CSRF, còn chưa đăng nhập có thể được redirect 302 tới login page thay vì 401 nếu dùng form login. Phải xem authentication mechanism và policy thực tế trước khi suy luận từ một status.

**Không nhầm 401 với “principal null”.** Token trước xác thực có thể đã có principal `reader` do client khai; nó vẫn không đủ quyền. Cũng không nhầm 403 với “credentials sai”: credentials có thể hoàn toàn đúng nhưng authorities không thỏa rule.

## 10. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nhầm lẫn thường gặp | Cách kiểm tra đúng |
| --- | --- | --- |
| Thấy username trong authentication trước login | Nghĩ người dùng đã đăng nhập | Xem nguồn username, trạng thái token và provider đã xác thực chưa |
| `isAuthenticated()` trả true cho anonymous token | Nghĩ có logged-in user | Dùng policy `authenticated()`/trust resolver; phân biệt anonymous và full auth |
| Sau login `getCredentials() == null` | Nghĩ authentication bị lỗi | Kiểm tra credential erasure của provider/manager; dùng authorities và trạng thái trusted |
| Gửi username `admin` nhưng vẫn 401 | Nghĩ principal phải được tin vì có tên | Kiểm tra password/provider, không tin identity claim từ client |
| Reader login được nhưng `/api/admin` trả 403 | Nghĩ auth không thành công | Xem `ROLE_READER` so với `ROLE_ADMIN` |
| `ROLE_READER` và `READER` không khớp | Nhầm role với authority string | Kiểm tra `hasRole`, `hasAuthority` và prefix mặc định |
| Log không hiện raw password | Nghĩ không thể debug | Dùng status, username, provider type, mã lỗi an toàn; không log secret |
| `@WithMockUser` test pass nhưng HTTP Basic thật 401 | Nhầm mock identity với xác thực thật | Test thêm `httpBasic(...)` để đi qua provider/password encoder |
| Request có authentication nhưng service khác thread không thấy | Tưởng context tự truyền mọi thread | Kiểm tra SecurityContext propagation và lifecycle |
| Có authentication trong request hiện tại, request sau bị 401 | Tưởng context luôn persist | Kiểm tra session/repository và việc client gửi credentials |
| Custom filter tự set authenticated token cho dữ liệu client | Bỏ qua ranh giới trust | Đưa credentials qua manager/provider và chỉ dùng kết quả kiểm chứng |
| Đọc toàn bộ Authentication vào response | Rò rỉ credentials/details/principal nhạy cảm | Chỉ xuất dữ liệu tối thiểu được phép công khai |

Một lưu ý với log và hỗ trợ vận hành: ghi nhận **request path, auth mechanism, trạng thái kết quả và loại lỗi** có thể đủ để chẩn đoán. Đừng log `Authorization` header, password, credential, token nguyên vẹn hoặc `Authentication.toString()` một cách mù quáng. Dù một implementation che password trong chuỗi log, implementation khác hoặc details custom chưa chắc an toàn.

## 11. Bài tập kiểm chứng nhận thức

1. Tạo `UsernamePasswordAuthenticationToken.unauthenticated("admin","wrong")`. Ghi lại principal, credentials, authorities, authenticated flag. Vì sao không thể kết luận đây là admin?
2. Với một user có `ROLE_READER` và `ARTICLE_READ`, dự đoán kết quả cho `authenticated()`, `hasRole("READER")`, `hasRole("ADMIN")` và `hasAuthority("ARTICLE_READ")`.
3. Giải thích đường đi từ raw password qua `PasswordEncoder.matches` đến Authentication kết quả. Provider có bắt buộc dùng lại cùng object token request không?
4. Kiểm tra code gọi `getCredentials()` sau khi xác thực. Tại sao không nên dựa vào credentials khác null để suy luận trạng thái login?
5. Nếu trong một request public, context chứa `AnonymousAuthenticationToken` có `isAuthenticated()==true`, vì sao rule `authenticated()` vẫn có thể từ chối anonymous?
6. Viết MockMvc test riêng cho HTTP Basic sai password, đúng password nhưng thiếu role, đúng password đủ role. Những status nào bạn dự kiến?
7. Dùng `@WithMockUser(username="ghost", roles="ADMIN")` cho endpoint admin. Vì sao test này không chứng minh `ghost` có tài khoản thật trong hệ thống?
8. Trong controller, đổi từ `authentication.getName()` sang ép `(String) authentication.getPrincipal()`. Trường hợp nào có thể ném `ClassCastException`, và cách viết đúng hơn là gì?
9. So sánh một request có cookie session với request có Basic header. Chúng có thể khôi phục hoặc tạo Authentication bằng những cơ chế nào, và điều gì vẫn được đưa vào SecurityContext?
10. Khi thêm filter custom, xác định chỗ thích hợp để gọi AuthenticationManager, xử lý thất bại và lưu trusted result. Vì sao không được tạo `authenticated(...)` dựa trên role được người gọi tự gửi?

**Mô hình cần ghi nhớ:** trước xác thực, `principal` là **danh tính được khai**, `credentials` là **bằng chứng chưa được kiểm chứng** và authorities chưa đáng tin. Sau xác thực thành công, provider/manager tạo kết quả đáng tin, principal được xác định, authorities dùng để phân quyền và credentials thường được xóa khi không còn cần thiết. SecurityContext mang kết quả đó đến phần xử lý request; authorization vẫn phải kiểm tra đúng policy. Một object `Authentication` xuất hiện, hoặc một cờ `isAuthenticated()` bật, không tự thay thế các bước xác minh và kiểm tra quyền.
