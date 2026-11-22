# ServerRequestCache và khôi phục yêu cầu ban đầu sau đăng nhập biểu mẫu

**Chủ đề:** Spring Security – reactive / Spring WebFlux  
**Phần:** Đăng nhập biểu mẫu (*form login*)  
**Mục tiêu:** Hiểu vì sao người dùng truy cập một trang cần đăng nhập được đưa đến trang login rồi quay về đúng URL ban đầu; biết cấu hình `ServerRequestCache`, kiểm tra session và CSRF, phân biệt *khôi phục URL bằng redirect* với *phát lại toàn bộ HTTP request*, và nhận ra các rủi ro bảo mật.

Tình huống: người dùng chưa đăng nhập mở `GET /members/report?period=Q1`. Ứng dụng yêu cầu authentication và đưa người đó đến `/login`. Sau khi nhập đúng username/password, trải nghiệm mong đợi là quay về `/members/report?period=Q1`, chứ không phải lúc nào cũng tới trang chủ. Trong Spring Security WebFlux, **`ServerRequestCache` lưu yêu cầu bị gián đoạn**, còn **`RedirectServerAuthenticationSuccessHandler` chọn địa chỉ chuyển hướng sau khi authentication thành công**. Hai thành phần này phối hợp với filter bảo mật, WebSession và security context.

Điểm đặc biệt của WebFlux: triển khai mặc định thông dụng `WebSessionServerRequestCache` **chỉ lưu URL của request**, không giữ và chạy lại nguyên body, headers hoặc thao tác ghi dữ liệu. Trình duyệt thường phát **một GET mới** khi theo redirect sau login. Cần hiểu giới hạn đó trước khi thiết kế trang checkout, tải tệp, POST thanh toán hoặc ứng dụng SPA.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích hành trình *anonymous GET → lưu saved URL trong WebSession → redirect login → POST username/password + CSRF → xác thực → redirect URL đã lưu → GET mới có session đã đăng nhập*.
2. Phân biệt `ServerRequestCache`, `WebSessionServerRequestCache`, `ServerRequestCacheWebFilter`, `RedirectServerAuthenticationSuccessHandler` và `ServerSecurityContextRepository`.
3. Kết nối **cùng một instance** `ServerRequestCache` vào `ServerHttpSecurity.requestCache(...)` và success handler khi tùy biến, để tránh sai lệch chính sách.
4. Biết vì sao request mặc định chỉ lưu **GET**, vì sao POST không được khôi phục body hoặc tự thực thi lại, và ý nghĩa tham số tương ứng như `continue`.
5. Kiểm thử flow bằng trình duyệt, `curl` có cookie jar và `WebTestClient`, giữ nguyên CSRF protection.
6. Xử lý các tình huống login trực tiếp không có request chờ, nhiều tab cùng session, session hết hạn, proxy rewrite và phòng tránh open redirect.

## 2. Các vai trò trong chu trình saved request

| Thành phần WebFlux | Trách nhiệm chính | Không nên hiểu nhầm |
| --- | --- | --- |
| `SecurityWebFilterChain` | Chứa các WebFilter của Spring Security áp dụng cho request | Không tự suy ra mọi URL đều được phép |
| `ServerHttpSecurity.authorizeExchange(...)` | Xác định URL nào đòi xác thực/quyền | Không tự lưu request body |
| `ServerRequestCache` | Hợp đồng lưu/đọc một request để hỗ trợ redirect sau auth | Không phải database message queue hay cache response |
| `WebSessionServerRequestCache` | Lưu thông tin URL yêu cầu vào `WebSession`; mặc định xem xét GET | Không lưu nguyên POST body để tái thực thi |
| `ServerRequestCacheWebFilter` | Đối chiếu một request trở lại với saved request theo chính sách cache | Không thay thế authentication filter |
| `RedirectServerAuthenticationSuccessHandler` | Khi login thành công, ưu tiên saved redirect URL; nếu không có dùng fallback, mặc định `/` | Không tự xác minh password |
| `WebSessionServerSecurityContextRepository` | Lưu và nạp `SecurityContext` cho request tiếp theo | Không đồng nhất với `ServerRequestCache` |
| `CsrfWebFilter` | Bảo vệ các thao tác thay đổi trạng thái, gồm POST login | Không phải cơ chế lưu URL trước đăng nhập |

Không nhầm API **WebFlux** này với nhóm Servlet: `HttpSessionRequestCache`, `RequestCacheAwareFilter`, `SavedRequestAwareAuthenticationSuccessHandler`, `HttpSecurity`, `SecurityFilterChain`. Những tên gần giống thuộc một stack khác và không thể copy trực tiếp vào mã reactive.

### 2.1. Một đường đi điển hình

```text
[1] Anonymous browser
    GET /members/report?period=Q1
       |
       v
[2] Spring Security: URL yêu cầu authenticated()
       |
       +--> WebSessionServerRequestCache.saveRequest(exchange)
       |       lưu URI vào WebSession thuộc trình duyệt A
       |
       +--> RedirectServerAuthenticationEntryPoint
               HTTP 302 Location: /login
               Set-Cookie: SESSION=...  (nếu session được tạo)
       |
       v
[3] Browser GET /login cùng SESSION cookie
       |
       +--> trang login hiển thị form + hidden CSRF token
       |
       v
[4] Browser POST /login:
        username=reader&password=reader123&_csrf=<token>
        Cookie: SESSION=...
       |
       +--> CSRF được kiểm tra
       +--> ReactiveAuthenticationManager xác minh credential
       +--> SecurityContext được lưu theo cơ chế cấu hình
       |
       +--> RedirectServerAuthenticationSuccessHandler
               hỏi requestCache.getRedirectUri(exchange)
               HTTP 302 Location: /members/report?period=Q1[&continue...]
       |
       v
[5] Browser GET đường đích cùng session đã authenticated
       |
       +--> ServerRequestCacheWebFilter kiểm tra request khớp
       +--> SecurityContext của session được nạp
       +--> authorizeExchange cho phép
       |
       v
[6] 200: report:Q1:reader
```

Các con số, đường URL và header trong sơ đồ là **diễn giải**, không phải byte-for-byte HTTP transcript: `Location` có thể là relative/absolute URI, mã chuyển hướng có thể là 302 hoặc một biến thể theo redirect strategy, cookie có thể được cấp lại hoặc đổi ID, và cache có thể thêm marker `continue`. Tuy nhiên, quy tắc cốt lõi là **địa chỉ đích phản ánh URL ban đầu** khi saved request còn hợp lệ và cùng session.

## 3. WebSessionServerRequestCache thực sự lưu gì?

Interface `ServerRequestCache` thuộc package `org.springframework.security.web.server.savedrequest` và cung cấp:

```java
Mono<Void> saveRequest(ServerWebExchange exchange);
Mono<URI> getRedirectUri(ServerWebExchange exchange);
Mono<ServerHttpRequest> removeMatchingRequest(ServerWebExchange exchange);
```

Đây là **chữ ký rút gọn để học**, không phải interface cần tự tạo lại. Ý nghĩa:

- `saveRequest(exchange)`: lưu request cần xác thực để khôi phục khi người dùng login. Mono chỉ có hiệu lực khi được **subscribe** trong pipeline; gọi method rồi bỏ qua `Mono` có thể không lưu gì.
- `getRedirectUri(exchange)`: đọc URI được đề xuất làm redirect. Với `WebSessionServerRequestCache`, URI thường có marker truy vấn dùng để phát hiện request đích khi người dùng đi theo redirect.
- `removeMatchingRequest(exchange)`: khi request hiện tại khớp saved request theo quy tắc của cache, lấy request đã lưu và bỏ entry đã dùng. Nó **không** là hành động “phát lại request POST”.

`WebSessionServerRequestCache` dùng `WebSession` để lưu URL. Theo tài liệu API, triển khai này hiện **chỉ lưu requested URL** và mặc định `setSaveRequestMatcher` khớp các request **GET**. Điều đó tránh tái chạy ngoài ý muốn các method có thể thay đổi trạng thái; nó cũng có nghĩa nội dung form POST, multipart upload, bearer token hoặc request body cũ **không được bảo toàn** để gửi lại.

### 3.1. Vì sao có tham số `continue`?

Một số phiên bản Spring Security thêm marker truy vấn mặc định tên `continue` trong URI redirect. Nó giúp `removeMatchingRequest` biết rằng request GET tiếp theo là bước trở lại từ saved request, thay vì truy vấn session cache trên **mọi** HTTP request. Dấu marker có thể được thêm theo kiểu `?continue` hoặc `&continue` tùy URL đã có query.

Ví dụ:

```text
URL ban đầu:
  /members/report?period=Q1

Location sau login có thể là:
  /members/report?period=Q1&continue

GET mới từ browser:
  /members/report?period=Q1&continue
```

Đừng viết test bắt buộc `Location` phải **bằng chính xác chuỗi gốc** nếu cache đã thêm marker. Hãy so URI path và query nghiệp vụ cần bảo toàn, đồng thời kiểm tra final response. Marker không phải authentication token, CSRF token hay quyền truy cập: người chưa login không được xem resource chỉ vì tự thêm `?continue`.

**Một session thường chỉ giữ một saved target cho một cache tại thời điểm cụ thể.** Nếu người dùng mở nhiều tab cần login rồi mới đăng nhập ở tab khác, URL được khôi phục có thể là yêu cầu lưu gần nhất tùy thời điểm. Đừng dùng cơ chế này thay cho bảng workflow/transaction tách từng tab.

### 3.2. Session cookie đóng vai trò gì?

Browser A cần mang theo **cùng WebSession** giữa request protected ban đầu, trang login, POST login và redirect trở lại. Nếu cookie `SESSION` bị xóa, bị chặn bởi trình duyệt, thuộc domain/path khác, đã hết hạn hoặc bị proxy làm sai thuộc tính, success handler có thể không tìm được saved URL và rơi về trang mặc định. Nếu session ID được thay đổi/luân chuyển sau login để chống session fixation, browser phải sử dụng cookie mới được phát.

Trong demo WebFlux/Boot ở phần dưới, `WebSession` thường được nhận diện bằng cookie tên `SESSION`. Hệ thống thực có thể tùy biến tên cookie, session store (ví dụ Spring Session Redis), SameSite/Secure/HttpOnly, domain và timeout. Không được giữ session ID trong URL để “sửa” lỗi redirect.

## 4. Phân biệt ba kết quả sau login

| Tình huống | Saved request | Sau login thành công |
| --- | --- | --- |
| Người dùng mở URL protected trước, sau đó login trong cùng session | Có và còn hợp lệ | Redirect tới URL protected (có thể thêm marker `continue`) |
| Người dùng tự mở `/login` rồi đăng nhập | Không có | Redirect về fallback do success handler cấu hình; mặc định `/` |
| Session/cookie bị thay đổi hoặc hết hạn trước POST login | Không tìm thấy URL cũ | Login cần CSRF/session hợp lệ; nếu xác thực thành công nhưng cache mất thì dùng fallback |
| Mật khẩu sai | Request cũ có thể vẫn chờ | Thường redirect tới `/login?error`; **chưa** được xem resource |
| POST tới protected endpoint trước login | Mặc định không được save theo GET matcher | Không tự phát lại POST hoặc body; cần ứng dụng thiết kế lại luồng |
| Login thành công nhưng role không đủ cho URL ban đầu | Saved URL vẫn có thể dùng | Sau redirect, request có thể nhận **403**, không phải mặc nhiên được cấp quyền |

Đây là khác biệt giữa **authentication** và **authorization**: success handler chỉ biết login thành công, nó không thể đảm bảo mọi tài nguyên người dùng đã định xem đều phù hợp quyền. Controller/service vẫn phải kiểm tra phân quyền đúng lúc request trở lại.

## 5. Cấu hình mẫu Spring Boot WebFlux, Java 17+

Ta tạo một ứng dụng có:

- `GET /welcome` công khai: trang sau đăng nhập trực tiếp, trả `welcome`.
- `GET /members/report?period=Q1` dành cho người đã login, trả `report:Q1:reader`.
- `GET /admin/overview` chỉ dành cho admin, để kiểm tra 403 sau login đúng mật khẩu nhưng sai role.
- Trang login mặc định `GET /login` và xử lý `POST /login` của Spring Security.
- `WebSessionServerRequestCache` dùng **chung instance** trong request-cache policy và success handler, với fallback `/welcome`.
- CSRF **giữ nguyên mặc định được bật**; browser/form phải gửi token hợp lệ. Không tắt CSRF chỉ để test dễ hơn.

Tài khoản demo: `reader / reader123` (role `USER`), `admin / admin123` (role `ADMIN`). Chỉ dùng trên **localhost**, không dùng mật khẩu rõ trong ứng dụng thật.

### 5.1. Cấu trúc dự án

```text
reactive-saved-request/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/saved/
    │   │   ├── SavedRequestApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── PageController.java
    │   └── resources/application.properties
    └── test/java/demo/saved/
        └── SavedRequestTests.java
```

Ví dụ dùng **JDK 17+** và **Spring Boot 3.5.7** làm mốc dependency để tái hiện cú pháp. Phiên bản dùng cho học tập; với sản phẩm thực cần chọn bản vá Spring Boot/Spring Security được hỗ trợ và không còn lỗi bảo mật đã biết.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-saved-request</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Không thêm `spring-boot-starter-web` (Spring MVC Servlet) vào bài WebFlux. Đây là điều kiện để ví dụ tập trung vào `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession` và các WebFilter reactive.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-saved-request
server.port=8080
```

### 5.2. Application entry point

`src/main/java/demo/saved/SavedRequestApplication.java`:

```java
package demo.saved;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SavedRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: dùng cùng ServerRequestCache cho hai phía

`src/main/java/demo/saved/SecurityConfig.java`:

```java
package demo.saved;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.security.web.server.savedrequest.WebSessionServerRequestCache;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerRequestCache serverRequestCache() {
        WebSessionServerRequestCache cache = new WebSessionServerRequestCache();
        // Để nguyên GET matcher mặc định, không tự lưu POST/PUT/DELETE.
        return cache;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ServerRequestCache serverRequestCache) {

        RedirectServerAuthenticationSuccessHandler success =
            new RedirectServerAuthenticationSuccessHandler();

        // Không có URL đang chờ thì tới /welcome thay vì /.
        success.setLocation(URI.create("/welcome"));

        // Cùng cache instance với phần requestCache của chain.
        success.setRequestCache(serverRequestCache);

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/welcome").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/admin/overview")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/members/report")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .requestCache(cache -> cache.requestCache(serverRequestCache))
            .formLogin(form -> form.authenticationSuccessHandler(success))
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
```

Đọc config theo từng quyết định:

1. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash mật khẩu, thay cho `{noop}`. `MapReactiveUserDetailsService` chỉ phục vụ demo; production dùng user store và encoding thực tế.
2. `@EnableWebFluxSecurity` cài security cho WebFlux, `formLogin` bật đăng nhập biểu mẫu cùng login page generated. Vì **không gọi `form.loginPage(...)`**, trang `/login` mặc định được Spring Security tạo; nếu tùy biến loginPage, bạn phải tự render trang/form và error page.
3. `@Bean ServerRequestCache` cung cấp một instance `WebSessionServerRequestCache`. Đây là request cache, không phải cache của database hay `SecurityContext`.
4. `.requestCache(cache -> cache.requestCache(serverRequestCache))` nối cache vào phần phát hiện request cần login và saved-request WebFilter của chain.
5. `RedirectServerAuthenticationSuccessHandler` dùng **cùng cache** khi login thành công và có fallback là `/welcome`. Nếu không cấu hình riêng, handler cũng có default saved-request handling với fallback `/`, nhưng chia sẻ instance làm chính sách tùy biến rõ ràng.
6. `httpBasic(...disable())` chỉ để browser demo dễ thấy form login thay vì HTTP Basic challenge. Ứng dụng thật có thể hỗ trợ nhiều scheme nhưng phải thiết kế entry point/matcher rõ.
7. `.anyExchange().denyAll()` bảo vệ các đường chưa cấp quyền; form login do Spring Security xử lý ở filter phù hợp. CSRF không bị disable, vì **POST login cần chống CSRF**.

**Lưu ý về trạng thái:** Request cache lưu saved target, trong khi authentication được lưu/khôi phục bằng **security context repository** (mặc định phù hợp với form login/WebSession trong Spring Security WebFlux). Hai nhiệm vụ khác nhau. Xóa request cache không đồng nghĩa logout; xóa SecurityContext không tự có nghĩa URL saved sẽ bị xóa ngay nếu cache vẫn còn.

### 5.4. Controller nhìn thấy user sau khi browser quay trở lại

`src/main/java/demo/saved/PageController.java`:

```java
package demo.saved;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(value = "/welcome",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> welcome() {
        return Mono.just("welcome");
    }

    @GetMapping(value = "/members/report",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> report(
            @RequestParam(defaultValue = "Q1") String period) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(username -> "report:" + period + ":" + username);
    }

    @GetMapping(value = "/admin/overview",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

`/members/report` đọc principal từ Reactor Context của request đang được WebFlux xử lý; không dựa vào `ThreadLocal currentUser` hay một trường singleton. Query `period` được dùng để thấy rõ việc URL đích giữ được query parameter. Đây là body plain text cho bài thực hành; ứng dụng thật còn phải validate input, kiểm tra quyền từng báo cáo, nội dung trang, tenant và quyền theo dữ liệu.

## 6. Thử hành trình bằng trình duyệt

Chạy:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Đợi ứng dụng khởi động và có server trên cổng `8080`; nếu port bị chiếm, đổi `server.port` rồi sửa URL tương ứng.

Trong cửa sổ **ẩn danh mới** của browser:

1. Mở `http://localhost:8080/members/report?period=Q1`. Vì chưa đăng nhập, browser phải chuyển tới `/login`. Trong **DevTools → Network**, quan sát request tới `/members/report?period=Q1` trả redirect, response `Location` và `Set-Cookie` nếu session được tạo.
2. Ở trang login, xem form `username`/`password`. Spring Security generated login page thêm CSRF hidden input; không cần tự paste token khi dùng form của trang.
3. Nhập `reader` / `reader123`. Sau đăng nhập, browser phải chuyển về đường protected đã mở; URL có thể được bổ sung marker `continue`. Nội dung trả về là `report:Q1:reader`.
4. Tải lại URL vừa mở trong cùng phiên; browser có session đã đăng nhập nên nhận `200` mà không phải nhập lại password. Quan sát cookie, không suy ra credentials đang được lưu trong URL.
5. Đóng phiên ẩn danh, mở phiên **mới không có saved request**, truy cập trực tiếp `http://localhost:8080/login` rồi đăng nhập. Kết quả fallback mong đợi là `/welcome` với body `welcome`.
6. Với tài khoản `reader`, thử `/admin/overview`: sau khi login đúng vẫn bị `403` vì thiếu role ADMIN. Redirect không tự nâng quyền.

**Đừng chỉ nhìn URL cuối.** Một số browser tự follow redirect, nên Network sẽ có nhiều request với các status khác nhau. Kiểm tra cả response đầu tiên, POST login và GET sau redirect. Cache của browser, extension, cookie policy hoặc tab đang mở có thể làm test “tưởng như không lưu request” dù phía server hoạt động đúng.

## 7. Thử request-cache bằng curl, cookie jar và CSRF

`curl` **không** mặc định giữ cookie giữa các lệnh; đồng thời cũng không tự follow redirect nếu thiếu `-L`. Để mô phỏng cùng một browser session, dùng `-c` (ghi cookies) và `-b` (đọc cookies). Ví dụ:

```bash
# Bước 1: anonymous request; xem 302 và lưu SESSION cookie
curl -i -c cookies.txt \
  'http://localhost:8080/members/report?period=Q1'

# Bước 2: dùng cùng cookie mở login page và đọc hidden CSRF token
curl -i -b cookies.txt -c cookies.txt \
  'http://localhost:8080/login'
```

Kết quả quan trọng: request đầu được redirect tới `/login`. Trong HTML trang login, tìm input hidden tên `_csrf` và **lấy token đúng của session hiện tại**. Token dưới đây là **ký hiệu trình bày**, phải thay bằng giá trị thật mà trang vừa cấp:

```bash
# Bước 3: thay TOKEN_FROM_LOGIN_FORM bằng token thật
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=reader' \
  --data-urlencode 'password=reader123' \
  --data-urlencode '_csrf=TOKEN_FROM_LOGIN_FORM' \
  'http://localhost:8080/login'
```

Đây là *lệnh hướng dẫn có chỗ cần điền token thời gian chạy*, không phải một lệnh có thể chạy thành công nếu dán nguyên tên TOKEN_FROM_LOGIN_FORM. Dùng token từ form thực, không hard-code token trong tài liệu hoặc tái sử dụng giữa hai session. Response thành công thường có redirect tới URL `/members/report?period=Q1` (có thể thêm marker) và có thể phát cookie mới.

Sau đó, theo đúng `Location` mà server trả (dùng cookie jar đã cập nhật):

```bash
curl -i -b cookies.txt \
  'http://localhost:8080/members/report?period=Q1'
```

Mong đợi body `report:Q1:reader` nếu `cookies.txt` giữ được security session sau login. Bước cuối cố ý dùng URL gốc để kiểm chứng authentication; để kiểm tra **xử lý matching saved request**, hãy gọi đúng URL `Location` từ response login. Không dùng `curl -L` một cách mù quáng khi debug form POST: cần quan sát từng redirect và không để tool chuyển method/body ngoài ý định.

**Dọn file cookie demo** sau thực hành vì session cookie là credential có thể sử dụng được. Trên Windows PowerShell, `curl` có thể là alias của lệnh khác; hãy gọi `curl.exe`. Với HTTP Basic người ta thường gửi `-u`, nhưng **form login ở bài này dùng POST form + CSRF + SESSION cookie**, không phải tự gửi Basic trên mỗi request.

## 8. Bộ kiểm thử WebTestClient + StepVerifier có thể chạy

Ta kiểm tra hai mức:

- **RequestCache độc lập:** `saveRequest` và `getRedirectUri` lưu/đọc đúng URL, và matcher mặc định không lưu POST. `MockServerWebExchange` cho phép test không mở cổng.
- **HTTP integration:** `@SpringBootTest(RANDOM_PORT)` chạy server thật và kiểm tra anonymous redirect, browser session cookie, CSRF token từ trang `/login`, thành công rồi trở lại saved target, và login trực tiếp dùng fallback. Dùng `WebTestClient` gửi request như client thật, không mock user để che giấu bước authentication qua HTTP.

`src/test/java/demo/saved/SavedRequestTests.java`:

```java
package demo.saved;

import java.net.URI;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.security.web.server.savedrequest.WebSessionServerRequestCache;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SavedRequestTests {

    @Autowired
    WebTestClient client;

    private static String sessionCookie(
            EntityExchangeResult<?> response, String previous) {
        ResponseCookie cookie = response.getResponseCookies()
            .getFirst("SESSION");
        return cookie == null ? previous : cookie.getValue();
    }

    private static String csrfFromLoginPage(String html) {
        assertNotNull(html, "Không thấy HTML trang login");

        // Tìm hidden input _csrf mà không phụ thuộc thứ tự thuộc tính.
        Pattern input = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>");
        Matcher tag = input.matcher(html);
        assertTrue(tag.find(), "Không thấy input tên _csrf");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "Không thấy value của CSRF input");
        return value.group(1);
    }

    @Test
    void cacheSavesGetUrlAndReturnsRedirectUri() {
        WebSessionServerRequestCache cache =
            new WebSessionServerRequestCache();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/members/report?period=Q1"));

        StepVerifier.create(
                cache.saveRequest(exchange)
                    .then(cache.getRedirectUri(exchange)))
            .assertNext(uri -> {
                assertEquals("/members/report", uri.getPath());
                assertTrue(uri.getRawQuery().contains("period=Q1"));
            })
            .verifyComplete();
    }

    @Test
    void defaultCacheDoesNotSavePostRequest() {
        WebSessionServerRequestCache cache =
            new WebSessionServerRequestCache();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.post("/members/submit"));

        StepVerifier.create(
                cache.saveRequest(exchange)
                    .then(cache.getRedirectUri(exchange)))
            .verifyComplete();
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() {
        client.get().uri("/members/report?period=Q1")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void anonymousVisitorCanOpenGeneratedLoginPage() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> assertTrue(html.contains("username")));
    }

    @Test
    void loginWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void savedGetIsRestoredAfterValidFormLogin() {
        // 1: Saved URL được tạo trong session ẩn danh.
        EntityExchangeResult<byte[]> initial =
            client.get().uri("/members/report?period=Q1")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String session = sessionCookie(initial, null);
        assertNotNull(session, "Chưa có WebSession cookie");

        // 2: Mở form login trong CHÍNH session này.
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .cookie("SESSION", session)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        session = sessionCookie(page, session);
        String csrf = csrfFromLoginPage(page.getResponseBody());

        // 3: POST credential + CSRF token + cookie cùng session.
        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "reader")
                    .with("password", "reader123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location, "Không có Location sau login");

        URI destination = URI.create(location);
        assertEquals("/members/report", destination.getPath());
        assertNotNull(destination.getRawQuery());
        assertTrue(destination.getRawQuery().contains("period=Q1"));

        // 4: Session ID có thể thay đổi khi login; dùng bản mới nếu có.
        String loggedInSession = sessionCookie(login, session);

        // Theo Location của Spring để kiểm tra matching saved request.
        client.get().uri(destination)
            .cookie("SESSION", loggedInSession)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:Q1:reader");
    }

    @Test
    void directLoginWithoutSavedRequestUsesFallback() {
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String session = sessionCookie(page, null);
        assertNotNull(session);
        String csrf = csrfFromLoginPage(page.getResponseBody());

        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "reader")
                    .with("password", "reader123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertEquals("/welcome", URI.create(location).getPath());
    }
}
```

Chạy từ thư mục dự án:

```bash
mvn test
```

Nếu chỉ có class trên, mục tiêu là **7 test pass**. Bộ test được trình bày để chạy trong project học tập; tài liệu **không khẳng định đã thực thi** trên máy của bạn. Thời gian và nội dung log Maven phụ thuộc runtime. Test có các assertion về status và giá trị body/Location, không chép cứng toàn bộ raw HTTP headers.

### 8.1. Vì sao test HTTP cần cookie và token thật?

`RANDOM_PORT` dùng server HTTP riêng; test client phải gửi **cùng session cookie** để truy vấn saved request và nhận security context. CSRF protection mặc định đòi form POST mang token phù hợp với session. Không dùng `mockUser` hoặc `mutateWith(csrf())` trên một client chạy qua mạng thật rồi giả định chúng được truyền thành thông tin tin cậy vào server; các helper kiểu mock phù hợp hơn cho WebTestClient bound to application context với `springSecurity()`.

Đoạn `csrfFromLoginPage` đọc HTML do Spring Security generated login page tạo ra. Regex đang phục vụ **test cho trang demo**, không phải HTML parser nên dùng lâu dài ở production; nếu thay login page bằng template tùy chỉnh, cần đổi test selector/token field cho phù hợp. Có thể dùng parser HTML phù hợp với dự án khi cần độ bền cao.

Test `cacheSavesGetUrlAndReturnsRedirectUri` kiểm tra cache trực tiếp mà không phụ thuộc login hoặc browser. Test `savedGetIsRestoredAfterValidFormLogin` mới chứng minh **trọn hành trình**: session, CSRF, authentication, redirect đúng path/query và nội dung controller với principal thật. Chỉ test redirect tới `/login` chưa đủ xác nhận saved request được đọc lại sau khi đăng nhập.

### 8.2. Thử sai mật khẩu với request đang chờ

Khi người dùng đã có saved URL mà nhập sai mật khẩu, mặc định form login thường redirect tới `/login?error`; không được cho xem resource, và saved request chỉ có ý nghĩa khi vẫn thuộc cùng session và chính sách cache còn giữ nó. Hãy test:

- POST login có CSRF token đúng nhưng password sai: phải không nhận `200` của tài nguyên protected.
- Sau đó nhập lại đúng password bằng CSRF token hợp lệ/cookie hiện tại: kiểm tra URL được giữ lại nếu cache còn entry.
- Nếu session bị hết hạn giữa hai lần, token CSRF có thể cũ và POST trả 403. Đừng hiểu 403 này là thiếu role ở saved target.

**Không** bỏ CSRF để viết một “happy path” sai chuẩn. Spring Security WebFlux mặc định bảo vệ POST login khỏi login CSRF; dùng token từ form hoặc API token được thiết kế rõ.

## 9. Chỉ redirect URL, không tự phát lại POST, DELETE hay body

Đây là ranh giới bảo mật và nghiệp vụ quan trọng nhất.

Giả sử người dùng chưa đăng nhập gửi:

```http
POST /checkout/confirm HTTP/1.1
Content-Type: application/json

{"orderId":"A123","amount":999}
```

`WebSessionServerRequestCache` mặc định xem xét GET và **không tự lưu POST này**, nên sau login sẽ không nhận một bản replay của POST cùng body. Nếu bạn viết custom cache cho POST, browser theo 302 có thể phát GET thay vì POST và body bị mất; quan trọng hơn, tự phát lại thao tác đặt hàng/thanh toán có thể tạo **side effect trùng lặp** hoặc vượt qua kiểm tra CSRF.

Đối với form nhập liệu dài hoặc checkout, hướng thiết kế an toàn thường là:

1. Cho người dùng login **trước khi** gửi lệnh thay đổi trạng thái; hoặc giữ dữ liệu draft trên client theo cách an toàn rồi gửi lại sau khi login.
2. Nếu cần giữ một bước nghiệp vụ, tạo **draft ID** phía server có ràng buộc session/user/tenant, TTL, quyền truy cập và chống replay; sau login yêu cầu người dùng xác nhận lại trước khi POST.
3. Dùng **idempotency key** cho lệnh nhạy cảm, kiểm tra server-side và transaction phù hợp để tránh xử lý hai lần.
4. Không serialize raw body/PII hoặc request Authorization header vào saved request cache.
5. Với các method không GET, phải thiết kế riêng cách khôi phục UI/business state; **không thay đổi mặc định GET matcher chỉ vì muốn “đỡ mất form”**.

## 10. Nếu không muốn lưu yêu cầu trước login

Có ứng dụng là API stateless, không có browser session, hoặc không muốn lưu lịch sử URL cần đăng nhập. Khi đó dùng `NoOpServerRequestCache` trong WebFlux, và điều chỉnh success handler/failure behavior nhất quán.

**Fragment cấu hình minh họa** (không phải file Java tự chạy; cần import và bean của chuỗi):

```java
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

ServerRequestCache noSavedRequests = NoOpServerRequestCache.getInstance();

RedirectServerAuthenticationSuccessHandler success =
    new RedirectServerAuthenticationSuccessHandler("/welcome");
success.setRequestCache(noSavedRequests);

http
    .requestCache(cache -> cache.requestCache(noSavedRequests))
    .formLogin(form -> form.authenticationSuccessHandler(success));
```

`NoOpServerRequestCache` là implementation không lưu/lấy saved request. Khi không có saved URL, login thành công luôn dùng location mặc định của handler (theo policy). API JSON thực sự stateless thường nên dùng **401/403 thích hợp** thay vì form redirect, đồng thời lựa chọn cơ chế token/HTTP Basic tương ứng; không cho browser login form vào mọi API chỉ do framework mặc định.

Nếu một ứng dụng vừa có HTML browser vừa có API JSON, có thể tách `SecurityWebFilterChain` theo matcher và `@Order` phù hợp. Tránh cấu hình cache/redirect của browser làm API client nhận HTML/302 bất ngờ, hoặc một catch-all chain che mất đường login.

## 11. Bảo mật saved redirect: open redirect, cookie, proxy, query

**Không tin bất kỳ URL redirect nào từ client mà chưa kiểm tra.** Nếu ứng dụng cho phép `?returnTo=https://example-attacker.test` và success handler dùng nó trực tiếp, kẻ xấu có thể đưa người dùng tới domain của chúng sau khi đăng nhập. Chỉ cho redirect trong allowlist cụ thể hoặc relative path thuộc ứng dụng, ràng buộc host/scheme và chính sách proxy. Đừng gọi một `Location` lạ là an toàn chỉ vì user vừa xác thực.

**CookieServerRequestCache không giống WebSessionServerRequestCache.** Có bản triển khai lưu saved URI trong cookie ở phía client. Spring Security đã công bố **CVE-2026-41706** cho một số phiên bản `CookieServerRequestCache`/`CookieRequestCache` do nguy cơ open redirect khi giá trị cookie bị kiểm soát. Nếu sử dụng cookie-backed request cache, đối chiếu advisory và nâng lên bản đã sửa; cấu hình demo này dùng `WebSessionServerRequestCache` và không minh họa cookie-backed saved redirect. Tham khảo: https://spring.io/security/cve-2026-41706/.

**Proxy và HTTPS:** Load balancer có thể chấm dứt TLS, rewrite path hoặc đưa thông tin `Forwarded`/`X-Forwarded-*`. Nếu cấu hình không tin cậy, redirect có thể dùng sai scheme/host/port, gây vòng lặp hoặc chuyển hướng tới domain không mong muốn. Chỉ chấp nhận forwarded headers từ proxy đáng tin, kiểm tra host allowlist, bật HTTPS ngoài localhost và kiểm thử URL từ browser thực qua đường ingress thật.

**Session:** Bảo vệ `SESSION` cookie với `HttpOnly`, `Secure` khi HTTPS và `SameSite` phù hợp với login flow, quản lý session fixation, timeout và logout. Spring Session/Redis thay đổi nơi lưu dữ liệu nhưng không thay đổi ý nghĩa “saved URL thuộc session cụ thể”. Sau logout, không giữ một saved URL nguy hiểm để tự động trả lại cho người khác dùng chung trình duyệt.

**Query parameters:** URL đã lưu có thể chứa query business như `?period=Q1` và có thể xuất hiện trong history, Referer, proxy/access logs. Không đặt token truy cập, password, reset secret hoặc dữ liệu riêng tư vào query chỉ vì cache sẽ giữ URL. Tránh log full saved URL nếu query có dữ liệu nhạy cảm.

## 12. Các tình huống thực tế dễ nhầm

| Hiện tượng | Khả năng cần kiểm tra | Cách kiểm chứng đúng |
| --- | --- | --- |
| Login thành công nhưng luôn về `/welcome` | Không có saved URL, khác session, cookie thiếu, saved request bị thay | Quan sát request protected đầu tiên, session cookie, login POST và `Location` |
| Redirect tới URL của tab khác | Hai tab cùng WebSession, saved URL mới ghi đè URL cũ | Tái hiện bằng từng tab/cửa sổ, cân nhắc workflow-specific state |
| Trang login hiện nhưng POST 403 | Thiếu/sai CSRF token, session đã đổi/hết hạn | GET lại login với cùng cookie, lấy token mới và kiểm tra form action |
| Password đúng nhưng POST quay lại `/login?error` | Lỗi xác thực, user store, password encoder | Kiểm tra server log an toàn, username/password hash và response flow |
| Login thành công rồi GET URL cũ trả 403 | User không có role/quyền trên saved resource | Đối chiếu `hasRole`, quyền dữ liệu, không mở rộng `permitAll` |
| Login thành công rồi GET URL cũ trả 404 | URL/resource không tồn tại hoặc rewrite route | Đối chiếu routing/path/query; saved request không bảo đảm resource vẫn tồn tại |
| Browser nhận 302 nhưng API client mong JSON | Form-login entry point được áp cho API | Tách chain hoặc negotiation rõ cho API và web |
| URL redirect có `continue` | Cache dùng marker matching saved request | So path + query nghiệp vụ, kiểm tra response đích; không coi marker là credential |
| Form POST trước login không được phát lại | Cache mặc định chỉ lưu GET URI | Thiết kế draft/idempotency và submit lại có chủ đích |
| Redirect về HTTP thay vì HTTPS | Reverse proxy/Forwarded headers cấu hình sai | Kiểm tra forwarded headers trusted, TLS và reverse-proxy config |
| Người khác mở `?returnTo=...` dẫn ra ngoài | Unvalidated redirect parameter/cookie | Chặn external origins, vá bản Security liên quan |
| Trang đích là 200 nhưng user sai | SecurityContext/session isolation hoặc cache dữ liệu nghiệp vụ | Test body/user/tenant thật, không chỉ assert status |

### 12.1. Khi test chỉ thấy một mã 302

Một response 302 có thể là “đi tới login”, “login thành công tới saved URL”, “login thất bại tới `/login?error`”, hoặc chuyển hướng HTTPS ở proxy. **Status giống nhau không có nghĩa thành công như nhau.** Luôn kiểm tra `Location`, cookie, request method và response cuối.

### 12.2. Vì sao trang login mặc định của Spring Security đủ dùng cho demo?

Form login mặc định sinh trang GET `/login`, post credential vào `/login` và bảo vệ bằng CSRF khi security config bật. Đây là cách cô lập chủ đề saved-request, không cần Thymeleaf hay HTML custom. Khi dự án dùng trang login của chính mình, cần đảm bảo **form action và field names đúng**, render CSRF token, công khai URL login và error, rồi test lại redirect sau auth.

### 12.3. Tại sao không xóa session hoặc disable CSRF để sửa lỗi redirect?

Vì session chứa cơ chế nhận biết trình duyệt và security context, còn CSRF bảo vệ POST login. Bỏ các lớp này làm hỏng tính đúng đắn hoặc bảo mật thay vì sửa lỗi. Nếu cần stateless auth, đó là một kiến trúc khác: bearer token/API 401 và không dùng saved browser request theo cách này.

## 13. Checklist vận hành và kiểm thử khi thay đổi cấu hình

1. Chỉ rõ **route nào được save**: mặc định GET là nền tảng hợp lý; hạn chế URL chứa PII hoặc phương thức có side effect.
2. Xác định `ServerRequestCache` dùng WebSession hay cơ chế khác; nếu custom, dùng chung instance với `RedirectServerAuthenticationSuccessHandler`.
3. Giữ generated/custom login page và `POST /login` hoạt động với CSRF; kiểm tra fallback path hợp lệ, ví dụ `/welcome`.
4. Dùng browser ẩn danh mở protected GET, xem `302 Location: /login` và session cookie.
5. Đăng nhập trong **cùng cookie/session**, nhận redirect về path/query đã lưu; test cả marker và response cuối.
6. Đăng nhập trực tiếp không có saved URL, chắc chắn đi về default target như thiết kế.
7. Test mật khẩu sai, thiếu/sai CSRF, session hết hạn, logout, role không đủ và URL bị đổi/trang đã xóa.
8. Test nhiều tab và proxy ngoài môi trường dev; phân biệt last-saved behavior và session affinity.
9. Kiểm tra open redirect, cookie security, HTTPS, Forwarded headers, query secrets và bản vá bảo mật liên quan.
10. Không coi saved request là công cụ giữ POST body; thiết kế riêng draft/idempotency cho workflow giao dịch.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ServerRequestCache` có lưu password trong POST login không?  
**Không** theo cách `WebSessionServerRequestCache` dùng ở đây. Cache lưu URL request trước khi authentication; CSRF/login form xử lý credential riêng.

**Câu 2.** Người dùng bấm nút login trực tiếp, không có URL protected trước đó. Sau login đi đâu?  
Đến **fallback location** của `RedirectServerAuthenticationSuccessHandler`: mặc định `/`, ở ví dụ là `/welcome`.

**Câu 3.** Vì sao URL trả về sau login có thể mang `continue`?  
Đó là marker giúp kiểm tra request mới có khớp saved request và tránh lookup session trên mọi request, **không phải token xác thực**.

**Câu 4.** Sau login đúng, URL ban đầu trả 403. Request cache đã lỗi chưa?  
**Không nhất thiết.** Saved URL có thể đúng, nhưng user thiếu role/quyền với trang; authentication và authorization là hai bước khác nhau.

**Câu 5.** Có thể dùng request cache để gửi lại lệnh chuyển tiền POST với body cũ không?  
**Không nên.** Mặc định cache lưu GET URL; POST cần thiết kế workflow/state/idempotency phù hợp và xác nhận người dùng, không replay tự động.

**Câu 6.** Hai tab chia sẻ session lưu hai target khác nhau; kết quả redirect có luôn đúng tab đầu không?  
**Không đảm bảo.** Một session có thể có saved entry mới ghi đè entry cũ, tùy thời điểm; cần mô hình workflow riêng nếu đòi hỏi per-tab.

**Câu 7.** Khi viết WebTestClient integration test, có thể chỉ gửi username/password mà không gửi CSRF token không?  
**Không** với default CSRF. Phải lấy token hợp lệ từ login page và gửi kèm cookie tương ứng, hoặc dùng helper mock đúng loại test.

**Câu 8.** Có thể để client cung cấp `returnTo=https://outside.example` rồi redirect nguyên xi sau login không?  
**Không.** Đây là nguy cơ open redirect/phishing; chỉ cho trusted relative URLs/allowlist và kiểm tra proxy headers.

**Câu 9.** `WebSessionServerRequestCache` và `WebSessionServerSecurityContextRepository` có cùng chức năng không?  
**Không.** Một bên giữ URL đang chờ; một bên giữ Authentication/SecurityContext cho các request sau.

**Câu 10.** Chỉ cần test 302 là chứng minh đã khôi phục request chưa?  
**Chưa.** Cần xác nhận `Location` đúng URL/path/query đã lưu và thực hiện GET mới với session đã login, thấy response body/principal đúng.

### Tài liệu đối chiếu chính thức

- Spring Security, `ServerRequestCache` API (WebFlux): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/ServerRequestCache.html
- Spring Security, `WebSessionServerRequestCache` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/WebSessionServerRequestCache.html
- Spring Security, `RedirectServerAuthenticationSuccessHandler` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Security, `ServerHttpSecurity` / requestCache: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security, `FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security advisory, *CVE-2026-41706* (CookieServerRequestCache): https://spring.io/security/cve-2026-41706/

**Ghi nhớ:** Khi một **GET** cần xác thực bị gián đoạn, `WebSessionServerRequestCache` giữ **URL** gắn với WebSession; form login xác thực và lưu SecurityContext; `RedirectServerAuthenticationSuccessHandler` ưu tiên saved target rồi chuyển trình duyệt trở lại **bằng một HTTP request mới**. Tính năng này cải thiện trải nghiệm điều hướng, **không tự phát lại body của POST**, không bỏ qua CSRF và không cấp quyền vượt chính sách của trang đích.