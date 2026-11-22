# ServerLogoutHandler, ServerLogoutSuccessHandler và xóa ngữ cảnh trong Spring Security WebFlux

## Mục tiêu bài học

Sau khi học xong, bạn có thể:

1. Giải thích cách `LogoutWebFilter` nhận yêu cầu logout ở **Spring Security reactive/WebFlux**, tách hai trách nhiệm: **dọn dẹp trạng thái** bằng `ServerLogoutHandler` và **phản hồi thành công** bằng `ServerLogoutSuccessHandler`.
2. Hiểu sự khác nhau giữa xóa `SecurityContext` khỏi `ServerSecurityContextRepository`, vô hiệu hóa toàn bộ `WebSession`, xử lý CSRF token, làm hết hạn cookie trình duyệt và thu hồi token/phiên từ identity provider.
3. Dùng `SecurityContextServerLogoutHandler`, `WebSessionServerLogoutHandler` và `DelegatingServerLogoutHandler` đúng cách; tránh thay thế handler mặc định rồi bỏ quên công đoạn xóa ngữ cảnh.
4. Chọn `RedirectServerLogoutSuccessHandler` cho trình duyệt, hoặc `HttpStatusReturningServerLogoutSuccessHandler` cho API chỉ muốn mã HTTP; phân biệt handler cleanup với handler tạo response.
5. Cấu hình `POST /logout` an toàn cùng CSRF, minh họa bằng Java 17+ / Spring Boot 3.x, và kiểm chứng qua `WebTestClient` và trình duyệt thật.
6. Nhận diện lỗi logout giả: response báo "thành công" nhưng session, SecurityContext, token hoặc dữ liệu client vẫn sử dụng được.

> Bài này nói về **Spring Security reactive**. Các interface `LogoutHandler`, `LogoutSuccessHandler`, `SecurityContextLogoutHandler` của Servlet có tên giống nhưng chữ ký và API khác. Trong WebFlux, phải dùng **`ServerLogoutHandler`**, **`ServerLogoutSuccessHandler`**, `ServerHttpSecurity` và `SecurityWebFilterChain`.

## 1. Logout không đơn thuần là chuyển tới một trang HTML

Đối với ứng dụng đăng nhập bằng session, mục tiêu của logout là đảm bảo **request tiếp theo không còn truy cập được tài nguyên cần xác thực** bằng trạng thái phiên vừa bị đăng xuất. Trả trang "Bạn đã đăng xuất" hoặc redirect về login chỉ là phần **giao diện**; nếu `SecurityContext` vẫn nằm trong repository, request sau có thể vẫn authenticated.

Một luồng logout thường cần các lớp sau:

| Lớp | Câu hỏi cần giải quyết | Công cụ reactive liên quan |
| --- | --- | --- |
| HTTP request | Request nào thực sự yêu cầu logout? | `LogoutWebFilter`, `logoutUrl`/`requiresLogout` |
| CSRF | Có phải POST được người dùng thực sự khởi tạo? | `CsrfWebFilter`, `ServerCsrfTokenRepository` |
| Security context | Còn `Authentication` lưu ở repository không? | `SecurityContextServerLogoutHandler` |
| WebSession | Có phải vô hiệu hóa **toàn bộ** session server-side không? | `WebSessionServerLogoutHandler` |
| Tác vụ phụ | Cần ghi audit hoặc dọn trạng thái ứng dụng nào? | Custom `ServerLogoutHandler` |
| HTTP response | Chuyển người dùng về login hay trả 204? | `ServerLogoutSuccessHandler` |
| Client/IdP | Cookie/token phiên hoặc SSO ngoài hệ thống còn sống? | Cookie policy, token revocation, OIDC logout theo kiến trúc |

**Định nghĩa cốt lõi:** thành công của logout phía ứng dụng là trạng thái xác thực đã được loại bỏ theo chính sách; thành công của HTTP redirect không tự chứng minh điều đó. Sau logout, kiểm chứng bằng một **request mới**, dùng lại cookie cũ và truy cập resource được bảo vệ.

## 2. Luồng xử lý của LogoutWebFilter

Spring Security WebFlux sắp các WebFilter theo `SecurityWebFiltersOrder`. Trong các cấu hình thường gặp, logout được xử lý bởi `LogoutWebFilter` trước bước authorization cuối của exchange. Khi request phù hợp với logout matcher, filter thực thi handler thay vì gọi controller logout bình thường.

```text
Browser / client
    |
    | POST /logout + Cookie phiên + CSRF token hợp lệ
    v
Security WebFilter chain
    |
    +--> CsrfWebFilter: kiểm tra token cho POST
    |       |
    |       +--> Thiếu/sai: thường 403; chưa thực hiện logout
    |
    +--> LogoutWebFilter: matcher khớp POST /logout?
            |
            +--> Không: tiếp tục chain -> authorization/controller
            |
            +--> Có: lấy Authentication theo context hiện tại
                    |
                    v
            ServerLogoutHandler.logout(exchange, authentication)
                    |
                    +--> Xóa SecurityContext khỏi repository
                    +--> Tùy cấu hình: invalidate WebSession
                    +--> Tùy cấu hình: audit/cleanup khác
                    |
                    v
            ServerLogoutSuccessHandler.onLogoutSuccess(...)
                    |
                    +--> 302/303 redirect tới trang đích
                    |    hoặc
                    +--> 200/204 cho API
                    |
                    v
            Request hoàn tất
```

Bản đồ này là mô hình học tập, không phải cam kết mọi filter luôn chạy: chain, matcher, CSRF repository, authentication mechanism và các handler có thể được tùy chỉnh. Nếu handler cleanup trả `Mono.error(...)`, không nên cho rằng success handler vẫn được gọi; phải quan sát và xử lý lỗi phù hợp.

### Ba method chính

```java
// Chữ ký của các API Spring Security WebFlux, chỉ minh họa:

Mono<Void> ServerLogoutHandler.logout(
        WebFilterExchange exchange,
        Authentication authentication);

Mono<Void> ServerLogoutSuccessHandler.onLogoutSuccess(
        WebFilterExchange exchange,
        Authentication authentication);

// Cấu hình:
http.logout(logout -> logout
        .logoutHandler(myCleanupHandler)
        .logoutSuccessHandler(myResponseHandler));
```

- `WebFilterExchange` mang `ServerWebExchange` và chuỗi xử lý filter tương ứng.
- `Authentication` có thể có hoặc không tùy bối cảnh. Code audit không được `getName()` khi `authentication == null`.
- `Mono<Void>` biểu thị **hoàn thành hoặc lỗi** của thao tác không có giá trị dữ liệu; phải **return publisher**, không gọi `subscribe()` để chạy "ngầm" rồi báo thành công sớm.
- `ServerLogoutHandler` chịu trách nhiệm xử lý **state**. `ServerLogoutSuccessHandler` chịu trách nhiệm phản hồi HTTP khi cleanup xong.
- `ServerLogoutSuccessHandler` không có nghĩa "đã xóa mọi cookie/token của hệ sinh thái"; chỉ phản ánh kết quả của các công việc mà application logout flow thực sự thực hiện.

**Không viết nhầm Servlet API:**

```java
// Sai phạm vi trong WebFlux, chỉ minh họa anti-pattern:
// void logout(HttpServletRequest req, HttpServletResponse res, Authentication auth)
// void onLogoutSuccess(HttpServletRequest req, HttpServletResponse res, Authentication auth)
```

Các chữ ký Servlet dùng `HttpServletRequest` và `HttpServletResponse` không phải hợp đồng của `ServerLogoutHandler` trong WebFlux.

## 3. Mặc định của WebFlux: xóa SecurityContext nhưng không suy ra cả WebSession đã bị hủy

Tài liệu Spring Security 6.5 về logout reactive mô tả:

- Spring Security có endpoint logout mặc định. Khi đã login, `GET /logout` có thể hiển thị **trang xác nhận**; `POST /logout` thực hiện logout.
- Default flow xóa trạng thái trong `ServerCsrfTokenRepository` và `ServerSecurityContextRepository` rồi redirect trở lại trang login.
- Nếu ứng dụng muốn **vô hiệu hóa toàn bộ WebSession**, hãy thêm `WebSessionServerLogoutHandler` vào logout configuration.

Điểm cuối rất quan trọng: **xóa security context không tự đồng nghĩa invalidation toàn bộ session**. Hãy phân biệt các thao tác, thay vì lấy hành vi `SecurityContextLogoutHandler` của Servlet rồi áp sang WebFlux.

| Thao tác | Đối tượng bị ảnh hưởng | Không tự đảm bảo |
| --- | --- | --- |
| `SecurityContextServerLogoutHandler` | `SecurityContext` lưu trong `ServerSecurityContextRepository` | Hủy mọi attribute của WebSession; thu hồi JWT/refresh token |
| `WebSessionServerLogoutHandler` | `WebSession` hiện tại phía server | Thu hồi token ở identity provider; xóa dữ liệu localStorage |
| CSRF cleanup của logout flow mặc định | Token trong `ServerCsrfTokenRepository` | Xóa mọi cookie/tài nguyên client tùy ý |
| Browser cookie hết hạn | Cookie browser mang session ID (nếu response cấu hình đúng) | Vô hiệu hóa server-side session nếu server không dọn |
| Success redirect | Thông điệp/đích HTTP | Thực thi cleanup còn thiếu |

### Tại sao xóa SecurityContext là bắt buộc?

Giả sử WebSession có thuộc tính chứa `SecurityContext` đã đăng nhập. Nếu chỉ redirect `/login?logout` nhưng repository vẫn trả lại Authentication khi trình duyệt gửi cookie cũ, request tiếp theo vẫn có thể authenticated. `SecurityContextServerLogoutHandler` gọi phương thức của `ServerSecurityContextRepository` để xóa trạng thái đã lưu; mặc định handler sử dụng `WebSessionServerSecurityContextRepository`. Nếu ứng dụng đổi context repository, phải đảm bảo logout sử dụng repository **cùng semantics** với nơi lưu authentication.

### Tại sao còn cần vô hiệu hóa WebSession?

Một WebSession có thể chứa dữ liệu khác ngoài SecurityContext: giỏ hàng, tùy chọn UI, saved request, CSRF token hoặc các attributes do ứng dụng lưu. Khi chính sách yêu cầu không giữ lại session sau khi logout, `WebSessionServerLogoutHandler` gọi invalidation của session. Điều này làm session cũ không còn hợp lệ ở phía server và các session attributes bị loại bỏ theo cơ chế session store.

Không phải mọi ứng dụng đều muốn xóa tất cả dữ liệu session phụ trợ, nên việc **thêm session invalidation** là quyết định thiết kế. Nhưng nếu yêu cầu security policy là "logout xóa toàn bộ phiên", đừng chỉ gọi `SecurityContextServerLogoutHandler` rồi giả định đã đủ.

### Dọn Session ≠ xóa cookie trong trình duyệt

`WebSession.invalidate()` vô hiệu hóa trạng thái ở server; trình duyệt vẫn có thể gửi lại cookie session ID cũ nếu response chưa làm hết hạn cookie. Khi session phía server không còn hợp lệ, cookie cũ không được coi là bằng chứng đăng nhập. Nếu yêu cầu UX/privacy cần xóa cookie ngay, cấu hình Set-Cookie hết hạn với **đúng tên, path, domain, Secure, SameSite** theo hạ tầng; kiểm chứng trên browser. WebFlux thường dùng cookie `SESSION`, nhưng tên/path có thể tùy chỉnh, không mặc định `JSESSIONID` của Servlet.

### Reactor Context khác SecurityContext repository

`ReactiveSecurityContextHolder` mang authentication trong Reactor Context của **subscription hiện tại**. `ServerSecurityContextRepository` quyết định security context có thể được nạp trong **request sau**. Vì vậy:

- Không "logout" bằng cách gọi `SecurityContextHolder.clearContext()` kiểu thread-local của Servlet.
- Không chỉ viết `ReactiveSecurityContextHolder.clearContext()` vào một pipeline bất kỳ rồi coi như xóa session; operator này xử lý context của pipeline, **không thay cho việc loại bỏ dữ liệu bền hơn** khỏi repository.
- Sau khi logout, tiêu chí quan trọng nhất là request mới sử dụng cookie cũ không còn thấy Authentication được cấp quyền.

## 4. Ba handler cần nhớ

### 4.1. SecurityContextServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler`.

Nó triển khai `ServerLogoutHandler`, chủ yếu loại bỏ `SecurityContext` qua `ServerSecurityContextRepository`. Constructor mặc định làm việc với `WebSessionServerSecurityContextRepository`. Khi sử dụng một repository tùy biến, phải gắn repo tương ứng:

```java
// Đoạn minh họa khi đã có ServerSecurityContextRepository repository:
SecurityContextServerLogoutHandler clear =
        new SecurityContextServerLogoutHandler();
clear.setSecurityContextRepository(repository);
```

Không cần tùy chỉnh repo cho ví dụ demo dùng form login với mặc định. Tránh xóa mỗi `Authentication` trong local variable: state của request sau có thể vẫn nằm trong repository.

### 4.2. WebSessionServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler`.

Nó triển khai `ServerLogoutHandler` và invalidates WebSession hiện tại. Dùng khi logout yêu cầu xóa toàn bộ phiên, đặc biệt với ứng dụng browser/session-based. Không dùng để thu hồi JWT stateless, refresh token ở database hoặc SSO phiên phía Identity Provider; các tác vụ đó cần cơ chế riêng.

### 4.3. DelegatingServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler`.

Nó cho phép kết hợp nhiều `ServerLogoutHandler` thành một handler được gắn vào DSL:

```java
ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
);
```

Đây chính là cấu trúc được Spring Security sử dụng trong **ví dụ chính thức cho reactive logout** khi cần invalidate session.

**Cẩn thận:** `logout.logoutHandler(custom)` ở Spring Security 6.5 **thay thế handler logout được cấu hình trước đó**, không phải bảo đảm chỉ thêm một side effect vào default. Nếu tự gán một custom handler để ghi log mà bỏ `SecurityContextServerLogoutHandler`, bạn có thể khiến HTTP redirect "thành công" dù không xóa context đúng cách. Khi cần nhiều công việc, hãy compose chúng và test.

Ngoài ra, nếu có yêu cầu thứ tự nghiêm ngặt giữa các thao tác nghiệp vụ, **đừng tự suy luận thứ tự hoàn tất chỉ từ danh sách delegates**. Đọc behavior của implementation đúng phiên bản hoặc chủ động tạo một handler trả publisher có `then(...)` để diễn đạt thứ tự mong muốn. Security cleanup phải là trọng tâm, không bị side effect ngoại vi cản trở.

## 5. ServerLogoutSuccessHandler: response sau cleanup

Giao diện `ServerLogoutSuccessHandler` nhận `WebFilterExchange` và `Authentication`, trả `Mono<Void>`. Nó chạy **sau khi logout handler hoàn tất thành công** trong flow của `LogoutWebFilter`; nó không thay thế việc xóa session/context.

Hai implementation thường gặp:

| Handler | Phản hồi | Khi nào phù hợp |
| --- | --- | --- |
| `RedirectServerLogoutSuccessHandler` | Chuyển hướng browser đến URL đã chọn; mặc định thường `/login?logout` | Ứng dụng form login có giao diện |
| `HttpStatusReturningServerLogoutSuccessHandler` | Trả HTTP status; mặc định 200, có thể cấu hình 204 | API/SPA muốn xử lý điều hướng ở client |

Chuyển hướng tới URL **cố định và nội bộ**:

```java
RedirectServerLogoutSuccessHandler success =
        new RedirectServerLogoutSuccessHandler();
success.setLogoutSuccessUrl(URI.create("/signed-out"));

// Dùng trong cấu hình ServerHttpSecurity:
http.logout(logout -> logout.logoutSuccessHandler(success));
```

Phần trên là đoạn minh họa ở vị trí đã có import `java.net.URI` và cấu hình `http`. Không đưa URL redirect lấy trực tiếp từ query string không được kiểm tra allowlist (rủi ro open redirect).

API không muốn redirect có thể dùng:

```java
new HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)
```

Đoạn này yêu cầu import `org.springframework.http.HttpStatus` và class success handler reactive. 204 không có response body; muốn client xóa dữ liệu UI cục bộ, client vẫn phải thực hiện bước đó. Không dùng `LogoutSuccessHandler` của Servlet nhầm với `ServerLogoutSuccessHandler` reactive.

### Handler audit nên là cleanup side effect, không phải success giả

Có thể dùng custom `ServerLogoutHandler` để ghi audit/metric sau khi yêu cầu logout hợp lệ; nên log ít dữ liệu (ví dụ kiểu sự kiện, correlation ID), không log cookie, access token, session ID, CSRF token hay password. Nếu audit là hệ thống phụ không tin cậy, cần cân nhắc timeout/failure policy để nó không làm logout bị treo hoặc gây race. Khi gắn handler audit, phải **giữ nguyên context cleanup**.

## 6. Ví dụ WebFlux Java 17+ chạy được: xóa SecurityContext và vô hiệu hóa WebSession

Ví dụ Spring Boot 3.x này dùng form login mặc định, một user local, một URL protected, và khi logout:

1. `SecurityContextServerLogoutHandler` xóa ngữ cảnh xác thực đã lưu.
2. `WebSessionServerLogoutHandler` vô hiệu hóa session server-side.
3. `RedirectServerLogoutSuccessHandler` chuyển người dùng tới trang `/signed-out` công khai.

### 6.1. Dependencies

Trong project Gradle đã cấu hình Spring Boot plugin và dependency management:

**`build.gradle`** (phần dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không thêm `spring-boot-starter-web` cho demo này: khi cả MVC và WebFlux có mặt, Spring Boot thường chọn Servlet theo mặc định.

Cấu trúc file:

```text
src/
  main/
    java/example/logout/
      LogoutDemoApplication.java
      ReactiveLogoutSecurityConfig.java
      SiteController.java
  test/
    java/example/logout/
      LogoutFlowTest.java
```

### 6.2. Main class

**`src/main/java/example/logout/LogoutDemoApplication.java`**:

```java
package example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 6.3. SecurityWebFilterChain và logout handlers

**`src/main/java/example/logout/ReactiveLogoutSecurityConfig.java`**:

```java
package example.logout;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.RedirectServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveLogoutSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails member = User.withUsername("member")
                .password(encoder.encode("local-demo-pass"))
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(member);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler()
        );

        RedirectServerLogoutSuccessHandler success =
                new RedirectServerLogoutSuccessHandler();
        success.setLogoutSuccessUrl(URI.create("/signed-out"));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/signed-out", "/favicon.ico")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                .logout(logout -> logout
                        .logoutHandler(cleanup)
                        .logoutSuccessHandler(success)
                )
                .build();
    }
}
```

### 6.4. Protected endpoint và trang đích sau logout

**`src/main/java/example/logout/SiteController.java`**:

```java
package example.logout;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SiteController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Welcome");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "Hello " +
                        context.getAuthentication().getName());
    }

    @GetMapping("/signed-out")
    public Mono<String> signedOutPage() {
        return Mono.just("Signed out");
    }
}
```

**Lưu ý quan trọng:** `/signed-out` là route **công khai**. Nếu không `permitAll()` cho URL này, handler logout có thể redirect đến một URL bắt buộc đăng nhập và lập tức bị redirect tiếp đến `/login`. Controller chỉ trả chuỗi demo, còn page xác nhận logout thực tế có thể là HTML/template.

### 6.5. Từng bước trong ví dụ

1. User `member` có password đã được băm bằng `DelegatingPasswordEncoder`. Password mẫu cứng chỉ dùng trong demo local; tuyệt đối không dùng tài khoản này khi triển khai public.
2. `formLogin(Customizer.withDefaults())` bật trang login mặc định do Spring Security render ở `GET /login`, xử lý POST form và lưu trạng thái xác thực theo session.
3. `httpBasic(...disable())` chỉ tắt HTTP Basic để tránh nhầm entry point; không tắt CSRF hoặc logout.
4. `POST /logout` khớp matcher mặc định và được bảo vệ bởi CSRF. Không có controller `@PostMapping("/logout")` vì `LogoutWebFilter` xử lý trực tiếp.
5. `DelegatingServerLogoutHandler` kết hợp cả xóa `SecurityContext` và invalidate WebSession. **Phải giữ `SecurityContextServerLogoutHandler` khi dùng custom logoutHandler**, tránh thay thế bằng một side effect audit đơn thuần.
6. `RedirectServerLogoutSuccessHandler` chạy sau cleanup, gửi trình duyệt đến `/signed-out`; không tự kiểm tra password hay thực thi session cleanup.
7. Controller `/private` đọc principal qua `ReactiveSecurityContextHolder`. Sau logout, một **request mới** không còn được truy cập controller bằng session cũ.

Không có `block()` hoặc `subscribe()` thủ công trong WebFilter/controller. Mọi xử lý reactive trả `Mono` để framework quản lý subscription.

### 6.6. Chạy và thử bằng browser

Trong project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trên localhost, cổng mặc định 8080:

1. Mở `http://localhost:8080/`: body `Welcome`.
2. Mở `http://localhost:8080/private` khi chưa đăng nhập: trình duyệt chuyển hướng đến `/login`.
3. Nhập user `member` và password `local-demo-pass` vào form mặc định, giữ cookie session do ứng dụng trả.
4. Mở `/private`: thấy `Hello member`.
5. Mở `/logout` trong browser khi đang đăng nhập: nếu dùng trang xác nhận mặc định, gửi **POST** từ form có CSRF. Không nhầm GET trang xác nhận với thao tác logout.
6. Theo redirect đến `/signed-out`: thấy `Signed out`.
7. Mở lại `/private` **trong cùng browser**: bị yêu cầu đăng nhập lại, vì context/session trước đó đã không còn hợp lệ.

Điểm quan trọng là **bước 7**. Chỉ thấy `Signed out` ở bước 6 chưa chứng minh cleanup đúng.

Nếu bạn tự POST qua `curl`, trước hết cần GET trang có token, lưu cookie jar rồi gửi form-encoded `_csrf` đúng; đừng dùng chuỗi token trong tài liệu. Với WebFlux session, tên cookie thường là `SESSION`, nhưng có thể cấu hình khác.

## 7. CSRF và method logout: vì sao dùng POST?

Spring Security WebFlux mặc định bật CSRF, và `LogoutWebFilter` mặc định xử lý **POST /logout**. Điều này giúp ngăn người ngoài kích hoạt logout chỉ bằng cách đặt một link/image GET trên website khác. `GET /logout` có thể chỉ hiển thị trang xác nhận, cung cấp form POST kèm CSRF token.

Ví dụ form trong template Thymeleaf (giả định CSRF token đã được expose trong model hoặc tích hợp với Thymeleaf theo cấu hình ứng dụng):

```html
<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng xuất</button>
</form>
```

Đây là fragment cho template, **không phải HTML độc lập có token tự sinh**. Trong các template có `th:action`, tích hợp Spring/Thymeleaf có thể tự thêm hidden CSRF; nếu đã tự sinh, tránh cố tạo trùng input thủ công. Cần kiểm tra HTML render thực tế và xác thực token với cookie/session tương ứng.

**Không biến GET thành logout thật** chỉ vì muốn dùng liên kết `<a href="/logout">`. Nếu custom `requiresLogout(...)` nhận mọi HTTP method, browser có thể bị logout bằng cross-site GET và vi phạm nguyên tắc phương thức an toàn không thay đổi trạng thái. Dùng nút/form POST hoặc JS kích hoạt POST với token hợp lệ.

### Thiếu CSRF khác logout handler thất bại

| Tình huống | Kết quả điển hình | Giai đoạn |
| --- | --- | --- |
| GET `/logout` | 200 HTML xác nhận (khi trang mặc định có mặt) | Chưa cleanup |
| POST `/logout` thiếu CSRF | Thường 403 | CSRF filter chặn, logout chưa chạy |
| POST `/logout` có CSRF hợp lệ | 3xx redirect trong demo | Cleanup xong, success handler |
| POST custom `/signout` với URL chưa cấu hình | Không khớp logout matcher | Có thể đi tiếp tới authorization/404 |
| Logout handler phát lỗi | Success handler không nên được coi là đã chạy thành công | Cần xử lý/quan sát lỗi |
| GET `/private` cùng browser sau logout | Redirect tới login | Phiên cũ không còn authenticated |

Tài liệu Spring Security 6.5 cho WebFlux ghi rõ default `ServerCsrfTokenRepository` lưu token trong WebSession. Với frontend khác origin, cookie/header và SameSite có thể yêu cầu cấu hình riêng; CORS không thay thế CSRF.

## 8. Kiểm thử bằng WebTestClient

Kiểm thử nên xác nhận ba mức: (1) matcher và CSRF, (2) success handler có response phù hợp, (3) request mới không còn authenticated sau logout thật.

### 8.1. Test matcher/CSRF/success redirect

Dùng Spring Security Test để đặt một mock Authentication cho request và chèn CSRF hợp lệ. Các test này **không thay thế** test browser/session vòng đời đầy đủ.

**`src/test/java/example/logout/LogoutFlowTest.java`**:

```java
package example.logout;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LogoutFlowTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void signedOutPageIsPublic() {
        client.get().uri("/signed-out")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Signed out");
    }

    @Test
    void anonymousPrivatePageRedirectsToLogin() {
        client.get().uri("/private")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches("Location", ".*login.*");
    }

    @Test
    void postLogoutWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("member"))
                .post().uri("/logout")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postLogoutWithCsrfRedirectsToCustomPage() {
        client.mutateWith(mockUser("member"))
                .mutateWith(csrf())
                .post().uri("/logout")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueEquals("Location", "/signed-out");
    }
}
```

Chạy bằng Gradle Wrapper:

```bash
./gradlew test --tests example.logout.LogoutFlowTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.logout.LogoutFlowTest
```

**Kết quả kỳ vọng:** cả bốn test PASS khi ứng dụng đúng như các file demo và các dependency tương thích. Đây là kết quả dự kiến, **không phải** một lần biên dịch/chạy test đã thực hiện ở dự án của bạn.

Giải thích:

- `springSecurity()` đưa security filter vào mock WebTestClient.
- `mockUser("member")` giả lập Authentication cho **một request test**. Nó không tạo một browser session thật, do đó không được lấy test redirect này làm bằng chứng phiên cũ đã bị xóa.
- `csrf()` tạo CSRF token hợp lệ cho test POST. Test không có token nhận 403, chứng minh yêu cầu logout phải qua lớp CSRF.
- `Location: /signed-out` xác nhận custom `ServerLogoutSuccessHandler` đã tạo redirect sau khi logout pipeline chạy.
- Test `anonymousPrivatePageRedirectsToLogin` chỉ chứng minh policy anonymous; để khẳng định logout thực sự xóa session cần test **cùng cookie đã đăng nhập** trước và sau.

### 8.2. Bài test session thực sự cần như thế nào?

Một test integration đầy đủ nên thực hiện các bước theo đúng cookie jar:

```text
1. GET /private anonymous                  -> redirect /login
2. GET /login                              -> lấy CSRF + session cookie
3. POST /login với username/password/CSRF   -> redirect thành công
4. GET /private với cùng cookie             -> 200; principal == member
5. GET /logout (nếu dùng form xác nhận)     -> CSRF mới/hợp lệ
6. POST /logout với cookie + CSRF           -> redirect /signed-out
7. GET /private bằng cookie của phiên cũ    -> redirect /login
```

Khi làm test tự động, có thể dùng `WebTestClient` với một exchange filter/cookie jar, hoặc test qua server thật bằng client theo dõi `Set-Cookie` và cookie qua mỗi request. Cần tính CSRF token được cấp phát hay đổi mới qua login/logout. **Không** lấy token của phiên trước rồi giả định luôn dùng được sau login/logout. Với HTTP Basic hoặc JWT stateless, bạn phải thiết kế phép kiểm chứng khác: có thể client vẫn đăng nhập lại bằng credential/token cũ nếu token chưa bị thu hồi.

### 8.3. Kiểm chứng session đã invalidated

Ngoài status, quan sát ở môi trường test/diagnostics có kiểm soát:

- Cookie cũ không truy cập được endpoint bảo vệ sau logout.
- Nếu dùng Spring Session với Redis, record session cũ không còn hợp lệ theo cơ chế session store.
- Nếu có thuộc tính session nhạy cảm, chúng không bị tái sử dụng sau invalidation.
- Audit logout ghi đúng số sự kiện, không ghi password/token/session ID raw.
- Không lộ stack trace/cookie security context trong response lỗi.

Dùng test server thật để phát hiện khác biệt cookie path/domain, TLS proxy, browser SameSite và session store phân tán; mock test không thể đại diện hết.

## 9. Tùy biến logout URL và response cho ứng dụng khác

### 9.1. Đổi endpoint từ /logout sang /signout

DSL WebFlux 6.5 cho phép:

```java
.logout(logout -> logout
        .logoutUrl("/signout")
        .logoutHandler(cleanup)
        .logoutSuccessHandler(success))
```

Đây là **đoạn trong cấu hình chain**, giả sử `cleanup` và `success` đã được tạo như ví dụ mục 6. `logoutUrl("/signout")` thay đổi URL POST kích hoạt logout theo mặc định, không tự tạo GET form HTML xác nhận custom có trải nghiệm giống trang /logout cũ. Nếu có link/menu "Đăng xuất", đổi form action sang `/signout` và bảo đảm gửi CSRF.

### 9.2. API chỉ cần 204 No Content

Nếu phía client là ứng dụng web/SPA tự điều hướng:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authentication.logout
        .HttpStatusReturningServerLogoutSuccessHandler;

// Một dòng bên trong logout DSL:
.logoutSuccessHandler(
        new HttpStatusReturningServerLogoutSuccessHandler(
                HttpStatus.NO_CONTENT))
```

Đây là **mẫu minh họa**, không phải một file Java độc lập; import thứ hai trong mã thực phải nằm **trên một dòng** hoặc được IDE định dạng lại đúng Java import. Handler trả 204 thay vì redirect. Các công đoạn xóa security context và invalidation session **không tự đổi theo response handler**; vẫn phải cấu hình `ServerLogoutHandler`.

Khi client nhận 204, nó thường cần chủ động bỏ UI state, token trong bộ nhớ và cache dữ liệu nhạy cảm. Nếu refresh token còn hoạt động ở server, 204 không tự thu hồi nó.

### 9.3. Thêm audit handler nhưng giữ cleanup

Một side effect audit reactive có thể được triển khai:

```java
// Mẫu minh họa nằm trong một lớp cấu hình đã có Logger log:
ServerLogoutHandler audit = (exchange, authentication) ->
        Mono.fromRunnable(() -> log.info(
                "Logout accepted; principalPresent={}",
                authentication != null
        ));

ServerLogoutHandler combined = new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler(),
        audit
);
```

Ở đây `Mono.fromRunnable(...)` sẽ chỉ thực thi khi publisher được subscribe trong chuỗi logout. `log` là logger bạn cần khai báo (chẳng hạn SLF4J), các class logout và Reactor cũng phải import; đây là **đoạn mở rộng, không phải chương trình độc lập**. Không log username, token, cookie ID hoặc toàn bộ object Authentication nếu không có chính sách và lọc dữ liệu phù hợp. Không gắn `audit` một mình qua `logoutHandler(audit)` rồi làm mất context cleanup.

Nếu audit cần đúng thứ tự so với các side effect khác, xác định rõ ở một publisher compose có trình tự bằng `then(...)`; không dựa vào vị trí trong constructor nếu semantics của delegate không đảm bảo điều bạn muốn.

## 10. Lỗi logout phổ biến

| Triệu chứng / lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hiện "Đã đăng xuất" nhưng GET /private vẫn truy cập | Chỉ redirect hoặc xóa một local flag, không xóa repository | Dùng `SecurityContextServerLogoutHandler` và kiểm tra request mới với cookie cũ |
| Đã xóa context nhưng session attributes còn | Chưa invalidate WebSession | Compose thêm `WebSessionServerLogoutHandler` khi policy yêu cầu |
| Gắn `logoutHandler(customAudit)` làm mất cleanup | Setter thay thế default handlers trong WebFlux 6.5 | Compose default cleanup + audit, kiểm thử |
| POST /logout nhận 403 | Thiếu/sai CSRF token hoặc cookie session không khớp | Lấy token hợp lệ từ form/session; giữ CSRF |
| GET /logout không đăng xuất | GET thường chỉ là confirmation page | Gửi POST + CSRF; không đổi matcher thành GET tùy tiện |
| Redirect sau logout gây vòng lặp | URL success yêu cầu authenticated | `permitAll()` cho trang công khai sau logout |
| Status 204 nhưng client vẫn thấy tên người dùng | Client cache/local UI không xóa | Client xóa state, reload resource đã bảo vệ để kiểm chứng |
| Xóa cookie browser nhưng vẫn có session server | Chỉ expire cookie, không invalidate server | Xóa session/context ở server và bảo vệ các đường tái sử dụng ID |
| Session đã invalidated nhưng JWT bearer vẫn dùng được | Token stateless không được thu hồi | Tính TTL, revoke/denylist/refresh token rotation theo thiết kế |
| Chỉ logout app, IdP OIDC vẫn logged in | Application logout khác SSO single logout | Dùng OIDC RP-initiated logout hoặc giao thức tương ứng khi cần |
| Dùng `SecurityContextHolder.clearContext()` Servlet | Không xóa SecurityContext repository reactive | Dùng handler reactive phù hợp |
| Custom handler gọi `subscribe()` rồi return empty | Logout response có thể trả trước cleanup | Return đúng `Mono<Void>` của cleanup, không fire-and-forget |
| Cleanup phụ trợ gây exception, redirect không xuất hiện | Publisher lỗi và flow chưa hoàn thành | Theo dõi/thiết kế failure policy; không tuyên bố đã logout khi state không sạch |
| Logout không có audit | Thiếu sự kiện vận hành | Ghi audit tối thiểu, loại bỏ dữ liệu bí mật |
| Test dùng `mockUser()` rồi tuyên bố đã xóa session | Mock user không đại diện cookie/session thật | Thêm integration test login/logout với cookie thật |
| Session nhiều instance không chia sẻ | Request đổi node làm hành vi không nhất quán | Dùng store chia sẻ/chiến lược session phù hợp |

### Checklist trước khi đưa vào production

1. Cấu hình đúng **WebFlux**: `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerLogoutHandler`, `ServerLogoutSuccessHandler`.
2. Logout chỉ xảy ra ở POST với CSRF hợp lệ hoặc cơ chế bảo vệ tương đương được đánh giá. Không để GET xóa session nếu không có lý do mạnh.
3. Sau logout, `ServerSecurityContextRepository` không còn cung cấp security context đã đăng nhập cho session cũ.
4. Nếu chính sách yêu cầu, toàn bộ `WebSession` bị invalidated; kiểm tra attributes và session store.
5. Response handler chỉ chạy sau cleanup thành công; redirect hoặc 204 đã được test.
6. Cookie có Secure/HttpOnly/SameSite/path/domain phù hợp; proxy TLS và session store được cấu hình đúng.
7. Sau logout, request dùng lại cookie cũ không thể vào tài nguyên bảo vệ.
8. Với JWT, OIDC hay OAuth2, xác định rõ logout local, refresh token revocation và IdP logout là **ba ranh giới khác nhau**.
9. Audit có correlation ID, không log mật khẩu, token, cookie raw, principal object đầy đủ.
10. Test cả CSRF fail, cleanup success, redirect success, session invalidation và lỗi trong handler tùy chỉnh.

## 11. Câu hỏi luyện tập

1. Vì sao gắn `logoutSuccessHandler(...)` mà bỏ `logoutHandler(...)` có thể tạo "logout giả"? Phân biệt trách nhiệm từng interface.
2. Một app chỉ dùng `SecurityContextServerLogoutHandler` nhưng giỏ hàng vẫn nằm trong `WebSession`. Điều đó là lỗi trong mọi ứng dụng hay phụ thuộc chính sách? Khi nào phải thêm `WebSessionServerLogoutHandler`?
3. Tạo một custom `ServerLogoutHandler` ghi audit (không chứa dữ liệu nhạy cảm), compose với hai cleanup handlers, và kiểm thử response.
4. Đổi logout URL sang `/signout`. Viết form HTML/Thymeleaf đúng `method="post"`, CSRF và thử thiếu token để xác nhận 403.
5. Thay redirect bằng `HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)`. Giải thích các công việc còn lại ở client SPA.
6. Thực hiện integration test đầy đủ: login form thật, lưu cookie, POST logout, dùng cookie cũ gọi `/private`. Kết quả nào chứng minh đã logout?
7. Giả sử session bị invalidated nhưng access token JWT không hết hạn. Vì sao request mang JWT cũ vẫn có thể được xác thực? Thiết kế cách giới hạn rủi ro.
8. Nếu dùng custom `ServerSecurityContextRepository`, giải thích vì sao handler xóa context phải cấu hình cùng repository và test điều gì.

**Kết luận:** trong WebFlux, **`ServerLogoutHandler` thực hiện việc dọn trạng thái**, **`ServerLogoutSuccessHandler` quyết định phản hồi HTTP**. `SecurityContextServerLogoutHandler` xóa context, `WebSessionServerLogoutHandler` invalidates toàn bộ session khi cần, `DelegatingServerLogoutHandler` kết hợp các công đoạn. Cần POST + CSRF và kiểm chứng lại bằng request mới; redirect đẹp không thay cho logout thực sự.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive Logout](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html)
- [Spring Security 6.5 — WebFlux CSRF (bao gồm logout)](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — ServerHttpSecurity.LogoutSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html)
- [Spring Security 6.5 — SecurityContextServerLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/logout/SecurityContextServerLogoutHandler.html)
- [Spring Security 6.5 — DelegatingServerLogoutHandler API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/logout/DelegatingServerLogoutHandler.html)
- [Spring Security 6.5 — RedirectServerLogoutSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/logout/RedirectServerLogoutSuccessHandler.html)
- [Spring Security — WebFlux Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
