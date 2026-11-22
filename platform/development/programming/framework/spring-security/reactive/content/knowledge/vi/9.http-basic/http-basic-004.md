# WWW-Authenticate, miền xác thực (realm) và phản hồi khi chưa xác thực

## 1. Mục tiêu và ngữ cảnh

Bài học thuộc chủ đề **HTTP Basic** trong **Spring Security reactive (WebFlux)**. Sau khi học, bạn có thể:

- Phân biệt header phản hồi `WWW-Authenticate` (server yêu cầu xác thực) với header yêu cầu `Authorization` (client gửi credential).
- Giải thích realm/protection space là gì, vì sao nó có trong Basic challenge và vì sao realm **không phải** role hay cơ chế phân quyền.
- Phân biệt HTTP **401 Unauthorized**, **403 Forbidden** và **407 Proxy Authentication Required**.
- Cấu hình realm với `HttpBasicServerAuthenticationEntryPoint` trong `ServerHttpSecurity`, dùng cùng entry point cho cả request thiếu credential và credential sai.
- Kiểm thử chính xác status/header bằng `curl` và `WebTestClient`; biết những sai lầm thường gặp khi trả JSON lỗi và khi API được gọi từ trình duyệt.
- Hiểu giới hạn bảo mật của HTTP Basic: Base64 không bảo mật credential, bắt buộc HTTPS ở môi trường thật, không lộ secret trong log.

> **Chỉ dùng API của WebFlux/reactive.** `HttpBasicServerAuthenticationEntryPoint`/`ServerAuthenticationEntryPoint`/`ServerWebExchange` không giống `BasicAuthenticationEntryPoint`/`AuthenticationEntryPoint`/`HttpServletRequest` của Servlet MVC. Một ví dụ Servlet có thể đúng trong hệ thống của nó nhưng không được dán nguyên vào cấu hình WebFlux.

## 2. Cơ chế challenge–response của HTTP Basic

Khi client yêu cầu tài nguyên mà chưa có thông tin xác thực hợp lệ, origin server có thể yêu cầu client cung cấp Basic credential thông qua phản hồi HTTP 401.

~~~text
Client                                            Spring Security WebFlux
  |                                                         |
  | GET /api/private                                        |
  | (chưa có Authorization)                                |
  |-------------------------------------------------------->|
  |                                                         |
  |                      authenticated() không thỏa         |
  |                                                         |
  |<--------------------------------------------------------|
  | HTTP/1.1 401 Unauthorized                               |
  | WWW-Authenticate: Basic realm="Learning API"            |
  |                                                         |
  | GET /api/private                                        |
  | Authorization: Basic <base64(username:password)>        |
  |-------------------------------------------------------->|
  |                                                         |
  |                   kiểm chứng username/password          |
  |                   và authorization                      |
  |<--------------------------------------------------------|
  | HTTP/1.1 200 OK (nếu hợp lệ và được phép)               |
~~~

Sơ đồ mô tả giao thức, không nhất thiết tất cả client đều chờ 401. Nhiều HTTP client gửi `Authorization` ngay ở request đầu tiên (preemptive authentication), ví dụ `curl -u`. Server vẫn phải xác thực credential được gửi.

Hai header rất khác nhau:

| Header | Hướng | Trách nhiệm | Ví dụ |
|---|---|---|---|
| `WWW-Authenticate` | Server → Client | Challenge: thông báo cơ chế xác thực và tham số cần thiết. | `WWW-Authenticate: Basic realm="Learning API"` |
| `Authorization` | Client → Server | Credential theo scheme để xác thực. | `Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==` |

Chuỗi Base64 ở ví dụ là của `Aladdin:open sesame` từ RFC 7617; không phải credential trong demo Java. Header `WWW-Authenticate` tự nó **không chứa mật khẩu**, còn `Authorization` có thể chứa dữ liệu nhạy cảm và không được ghi log nguyên văn.

### 2.1. Những điều không được suy ra từ tên “Unauthorized”

Dù status tên là “401 Unauthorized”, nó chủ yếu báo rằng tài nguyên **chưa có credential xác thực hợp lệ**. Nếu client đã authenticated hợp lệ nhưng thiếu quyền truy cập, status thường đúng hơn là **403 Forbidden**. Hai tình huống đòi cách xử lý khác nhau: 401 có thể khiến client thử đăng nhập/đổi credential, còn 403 thường yêu cầu thay đổi quyền hoặc policy.

## 3. Định dạng Basic challenge theo RFC

Ví dụ chỉ những dòng liên quan (không phải HTTP response đầy đủ):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
~~~

Theo **RFC 7617**:

- `Basic` là tên authentication scheme.
- `realm` **bắt buộc** trong Basic challenge; giá trị nằm trong dấu nháy kép, ví dụ `"Learning API"`.
- `charset` là tham số **tùy chọn**, giá trị được định nghĩa là `UTF-8`. Ví dụ chuẩn: `WWW-Authenticate: Basic realm="Learning API", charset="UTF-8"`. Không tự khẳng định Spring Security mặc định phát `charset` nếu chưa kiểm tra.
- Scheme và tên tham số được so khớp không phân biệt hoa/thường; giá trị realm nên được giữ nhất quán.
- Credential Basic hình thành từ `username + ":" + password`, đổi thành bytes rồi Base64. Dấu `:` **đầu tiên** là ký tự phân tách; username chứa dấu hai chấm không hợp lệ cho định dạng này.
- Về charset username/password ngoài ASCII, có vấn đề tương thích giữa các client nếu không có thỏa thuận encoding. `charset="UTF-8"` trong challenge là một tín hiệu mong muốn với client hỗ trợ, không phải “mã hóa mật khẩu”.

Ví dụ giá trị credential đã được định nghĩa trong RFC:

~~~http
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

Đó là Base64 của `Aladdin:open sesame`. **Base64 không phải encryption**; người đọc được header có thể giải ngược về username/password. Không gửi Basic trên HTTP không dùng TLS ở môi trường thật. Đặt TLS/HTTPS cho tất cả các hop có credential, kiểm soát proxy và tuyệt đối tránh log `Authorization`.

**RFC 9110, mục 11.6.1/15.5.2:** origin server tạo phản hồi **401 phải cung cấp ít nhất một `WWW-Authenticate` challenge áp dụng cho tài nguyên**. Một custom error handler trả JSON với status 401 nhưng bỏ header challenge có thể vi phạm semantics HTTP và làm client xử lý sai.

## 4. Realm thực chất là “miền xác thực” như thế nào?

Realm là một **nhãn do server chọn** giúp client phân biệt các protection space. Tên realm có thể xuất hiện trong trình duyệt khi người dùng được yêu cầu nhập Basic username/password và hỗ trợ client quyết định có thể tái sử dụng credential trong phạm vi phù hợp hay không.

Ví dụ:

~~~text
https://api.example.test                   origin A
  /courses/**     -> Basic realm="Learning API"
  /reports/**     -> Basic realm="Reports"

https://admin.example.test                 origin B
  /**            -> Basic realm="Reports"
~~~

Dù realm ở hai origin cùng tên `Reports`, **hai origin không mặc nhiên chia sẻ cùng một security boundary**. RFC cũng định nghĩa authentication scope theo URI path cho Basic, nhưng cách browser/cache áp dụng có thể phụ thuộc client. Không giả định browser sẽ luôn prompt đúng một lần cho mỗi group path.

### 4.1. Realm không phải role, tenant hay password store

| Quan niệm sai | Sự thật |
|---|---|
| `realm="admins"` buộc người dùng phải là admin. | Không. `hasRole("ADMIN")` hoặc policy authorization mới quyết định quyền. |
| Realm đại diện tenant đã được xác minh. | Không. Realm là challenge metadata; tenant cần xác thực/ràng buộc bằng cơ chế riêng. |
| Đổi realm là đổi tên user hoặc reset password. | Không. Không động chạm `ReactiveUserDetailsService`/`PasswordEncoder`. |
| Mỗi realm tự tạo `SecurityWebFilterChain` mới. | Không. Chọn security chain phụ thuộc `securityMatcher(...)` và thứ tự bean. |
| Realm giống JWT audience/OAuth2 scope. | Không. Đó là khái niệm token/giao thức khác. |
| Realm bảo vệ endpoint mà không cần authorization. | Không. Cần rule `authenticated()`, `hasRole(...)`, v.v. |
| Realm là thông tin principal đã xác thực. | Không. Nó là nhãn được server gửi trong response challenge. |

Chọn realm ngắn, ổn định, không nhạy cảm, thường là một chuỗi ASCII rõ nghĩa. Không chèn trực tiếp giá trị từ header/query do người dùng cung cấp vào realm vì dữ liệu này được phát trong HTTP header; khi cần realm động phải kiểm tra/escape và xét nguy cơ header injection.

### 4.2. Browser prompt và client API

Một browser có thể hiện popup Basic khi nhận `WWW-Authenticate: Basic realm="..."` cùng 401, rồi ghi nhớ username/password trong một khoảng/phạm vi tùy implementation. API client như curl, Postman, SDK có thể xử lý theo cách khác; thường người lập trình chủ động cung cấp credential.

- Không xem browser popup là trang login do Spring Security dựng.
- Không kết luận 401 sẽ luôn bật popup ở mọi browser, mọi loại AJAX/fetch hoặc proxy.
- Nếu muốn API trả JSON để SPA hiển thị màn hình đăng nhập riêng, việc thêm JSON body **không bảo đảm** ngăn browser prompt khi vẫn có Basic challenge.
- Không áp dụng nguyên xi ghi chú về `X-Requested-With: XMLHttpRequest` của Servlet Basic vào WebFlux; phải xác minh behavior của implementation reactive và test trên client thực tế.
- Không dùng “đổi realm liên tục” làm cơ chế logout; browser có thể vẫn cache Basic credential, còn backend cũng chưa chắc vô hiệu hóa bất kỳ session/token nào.

## 5. Các phản hồi khi chưa xác thực và chưa được cấp quyền

| Request/tình huống | Status thường gặp | Cách xử lý |
|---|---|---|
| `GET /api/private` không có credentials, rule `authenticated()` | **401** | Basic challenge `WWW-Authenticate` |
| `GET /api/private` có Basic credential sai | **401** | Authentication failure, có thể challenge lại |
| Tài khoản bị khóa/vô hiệu hóa/hết hạn trong username/password login | **401** | Authentication thất bại; chi tiết ở audit nội bộ |
| User hợp lệ nhưng thiếu role/scope | **403** | Access denied; không nên liên tục hỏi lại cùng password |
| `POST` bị CSRF filter từ chối | Thường **403** | Không nhất thiết do thiếu role |
| Tài nguyên public `permitAll()` không có credential | Có thể **200** | Không yêu cầu challenge |
| Proxy HTTP đòi xác thực client cho proxy | **407** | `Proxy-Authenticate`, không phải `WWW-Authenticate` |
| URL không tồn tại và được phép đi tới handler | **404** | Không phải lỗi login |

Không thể suy ra nguyên nhân chính xác chỉ dựa vào status. Một `AuthenticationException` có thể được chuyển thành 401 bởi authentication entry point; một `AccessDeniedException` từ authorization có thể thành 403 hoặc khởi động authentication nếu người dùng chưa xác thực.

### 5.1. 401: chưa có hoặc sai credentials

Khi bảo vệ một endpoint bằng `authenticated()`, request thiếu Authentication có thể bị authorization từ chối; cơ chế xử lý lỗi sẽ dùng `ServerAuthenticationEntryPoint` để bắt đầu xác thực. Nếu dùng HTTP Basic, phản hồi thông thường là status 401 và header Basic challenge.

Nếu client gửi Basic credential sai, authentication filter có thể thất bại **trước** bước authorization, và authentication failure handler/entry point có thể trả 401. Đây là hai luồng nguyên nhân khác nhau nhưng đều cần response nhất quán.

### 5.2. 403: đã xác thực nhưng thiếu quyền

Nếu user có `ROLE_READER` nhưng endpoint đòi `ROLE_ADMIN`, credential đã hợp lệ vẫn **không đủ quyền**. Trong cấu hình WebFlux thông thường, `ServerAccessDeniedHandler` trả 403; không nên trả 401 chỉ để browser hiện lại Basic prompt, vì nhập lại cùng credential không thay đổi authorities.

### 5.3. 407: xác thực với proxy

`407 Proxy Authentication Required` dùng `Proxy-Authenticate`, `Proxy-Authorization`. Đừng lấy logic này làm response login của origin server WebFlux. Proxy có thể đứng trước API, nhưng trách nhiệm xác thực proxy và trách nhiệm xác thực user của API là hai chuyện khác nhau.

### 5.4. permitAll không đồng nghĩa bỏ xác thực

Với URL `permitAll()`, authorization không yêu cầu logged-in principal. Tuy nhiên, nếu client **chủ động gửi header Basic sai**, authentication filter có thể kiểm tra rồi trả 401. Do đó “public GET không credential” và “public GET với Basic sai” là hai test khác nhau. Tương tự, `permitAll` không tự tắt CSRF hoặc các filter bảo mật khác.

## 6. Những lớp reactive nào thực hiện điều này?

Mô hình khái niệm:

~~~text
Spring Security WebFilterChainProxy
  |
  +-- HTTP Basic authentication filter
  |      |
  |      +-- đọc Authorization header theo Basic
  |      +-- ReactiveAuthenticationManager kiểm chứng
  |      +-- thành công: Authentication vào reactive security context
  |      +-- thất bại: failure handling / entry point
  |
  +-- AuthorizationWebFilter
         |
         +-- authenticated() khi thiếu Authentication
         |        -> ExceptionTranslationWebFilter
         |        -> ServerAuthenticationEntryPoint
         |        -> 401 + WWW-Authenticate
         |
         +-- đã authenticated nhưng thiếu role
                  -> ServerAccessDeniedHandler
                  -> thường 403
~~~

Sơ đồ chỉ thể hiện **chức năng và kết quả**, không đóng đinh thứ tự các filter. Thứ tự thực tế do `SecurityWebFiltersOrder`/cấu hình chain quy định.

### 6.1. ServerAuthenticationEntryPoint

Interface reactive `org.springframework.security.web.server.ServerAuthenticationEntryPoint` có method:

~~~java
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException exception);
~~~

Chữ ký trên rút gọn để học, không phải class độc lập. Nó yêu cầu tạo phản hồi bắt đầu authentication cho `ServerWebExchange`. Không dùng interface Servlet `org.springframework.security.web.AuthenticationEntryPoint` có tham số `HttpServletRequest`/`HttpServletResponse`.

### 6.2. HttpBasicServerAuthenticationEntryPoint

Class `org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint` là entry point có sẵn cho Basic:

- `new HttpBasicServerAuthenticationEntryPoint()` tạo instance.
- `setRealm(String)` đặt tên realm, mặc định `"Realm"`.
- `commence(...)` phát phản hồi 401 và Basic challenge.
- Có thể sử dụng cho cả trường hợp chưa gửi credential và đã gửi nhưng authentication thất bại.

### 6.3. Nên nối cùng entry point ở hai nhánh

Cấu hình minh họa bên trong bean `SecurityWebFilterChain`:

~~~java
HttpBasicServerAuthenticationEntryPoint entryPoint =
    new HttpBasicServerAuthenticationEntryPoint();
entryPoint.setRealm("Learning API");

http.httpBasic(basic ->
    basic.authenticationEntryPoint(entryPoint));

http.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(entryPoint));
~~~

Đây là **mảnh cấu hình**, không phải ứng dụng hoàn chỉnh. Mục đích:

- `httpBasic(...authenticationEntryPoint(...))` liên quan đến lỗi từ HTTP Basic authentication.
- `exceptionHandling(...authenticationEntryPoint(...))` liên quan tới yêu cầu authentication khi authorization thấy user chưa được xác thực.
- Dùng cùng instance giúp tránh lỗi “không gửi Basic thì realm A; gửi Basic sai thì realm B”.

Với nhiều authentication mechanism (Basic + Bearer, form login, OAuth2), global entry point có thể không phù hợp cho mọi URL. Khi đó cấu hình theo `SecurityWebFilterChain` và matcher, test đầy đủ từng nhánh thay vì dùng một Basic challenge cho mọi tình huống.

## 7. Demo Java 17: Basic realm tùy chỉnh trong Spring WebFlux

Ví dụ chạy độc lập sử dụng **Java 17**, **Spring Boot 3.5.16** và các dependency Spring Security/WebFlux do Boot quản lý:

- `GET /api/public`: công khai.
- `GET /api/private`: cần authenticated.
- `GET /api/admin`: cần `ROLE_ADMIN`.
- `reader:demo-pass` có `ROLE_READER`; `admin:admin-pass` có `ROLE_ADMIN`.
- Realm của Basic challenge là `Learning API`.

**Chỉ dành cho localhost.** Demo lưu password bằng `{noop}` và hardcode trong Java để quan sát HTTP; production phải dùng encoder/hash mạnh, secret management, HTTPS/TLS và rate limit.

### 7.1. Cấu trúc

~~~text
webflux-basic-challenge/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/BasicChallengeApplication.java
    └── test/java/example/BasicChallengeIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-challenge'
~~~

`build.gradle`:

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Boot 3.5.16 yêu cầu Java 17+ và Gradle phiên bản được hỗ trợ (7.6.4+ hoặc 8.4+ trong các dòng Gradle tương ứng). Nếu có wrapper, nên dùng wrapper để tránh khác version giữa máy.

### 7.2. Ứng dụng đầy đủ

`src/main/java/example/BasicChallengeApplication.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class BasicChallengeApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicChallengeApplication.class, args);
    }

    @Bean
    HttpBasicServerAuthenticationEntryPoint basicEntryPoint() {
        var entryPoint = new HttpBasicServerAuthenticationEntryPoint();
        entryPoint.setRealm("Learning API");
        return entryPoint;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop} chỉ cho demo local.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        HttpBasicServerAuthenticationEntryPoint entryPoint) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint))
            .exceptionHandling(exceptions ->
                exceptions.authenticationEntryPoint(entryPoint))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicRoute() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/private")
        Mono<Map<String, String>> privateRoute(
            ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "private",
                    "username", principal.getName()));
        }

        @GetMapping("/api/admin")
        Mono<Map<String, String>> adminRoute(
            ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "admin",
                    "username", principal.getName()));
        }
    }
}
~~~

**Giải thích mối liên hệ với đề bài:**

1. Bean `HttpBasicServerAuthenticationEntryPoint` đặt realm cố định; không cấu hình role, username hoặc password ở đây.
2. Bean `MapReactiveUserDetailsService` chứa hai user demo để reactive authentication manager xác thực.
3. `httpBasic` xử lý Basic credentials và dùng entry point đã chỉ định.
4. `exceptionHandling` dùng cùng entry point khi request chưa authenticated bị rule truy cập từ chối.
5. `pathMatchers("/api/admin").hasRole("ADMIN")` mới là quy tắc phân quyền; realm `Learning API` không cấp quyền admin.
6. `formLogin(...disable)` làm cho bài demo không bị chuyển hướng sang login form; ta muốn quan sát response HTTP Basic.
7. Controller xử lý request **sau** security filters. Nó không cần tự set `WWW-Authenticate`.

### 7.3. Chạy thử bằng curl

Trong thư mục `webflux-basic-challenge`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Ở terminal khác, khi server đã chạy trên port 8080:

~~~bash
# Không có Authorization: cần challenge Basic
curl -i http://localhost:8080/api/private

# Authorization Basic có password sai: vẫn cần challenge
curl -i -u reader:wrong-pass http://localhost:8080/api/private

# Authenticated user truy cập được private endpoint
curl -i -u reader:demo-pass http://localhost:8080/api/private

# Authenticated user nhưng không có ROLE_ADMIN
curl -i -u reader:demo-pass http://localhost:8080/api/admin

# Admin có role phù hợp
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Public endpoint không credential
curl -i http://localhost:8080/api/public

# Public endpoint với Basic credential cố ý sai
curl -i -u reader:wrong-pass http://localhost:8080/api/public
~~~

Trong PowerShell, dùng `curl.exe` nếu `curl` bị thay bằng alias. Cờ `-i` in HTTP response headers; `-u` yêu cầu curl tạo Basic header từ cặp username/password. Đừng đưa mật khẩu thật vào command line của máy dùng chung vì có thể lộ qua shell history hoặc process listing.

| Request | HTTP status kỳ vọng | Kết quả chính |
|---|---|---|
| `GET /api/private` không credential | **401** | `WWW-Authenticate: Basic realm="Learning API"` |
| `GET /api/private` Basic sai | **401** | Cùng Basic challenge do entry point đã cấu hình |
| `GET /api/private` Basic reader đúng | **200** | JSON có `"username":"reader"` |
| `GET /api/admin` Basic reader đúng | **403** | Không đủ quyền admin dù credential hợp lệ |
| `GET /api/admin` Basic admin đúng | **200** | JSON có `"username":"admin"` |
| `GET /api/public` không credential | **200** | Không cần Basic challenge |
| `GET /api/public` Basic sai | **Có thể 401** | Authentication filter có thể từ chối dù URL permitAll |

Trích đoạn **expected HTTP response**, không phải stdout cố định của chương trình Java:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
~~~

~~~http
HTTP/1.1 403 Forbidden
~~~

JSON thành công có thể có thứ tự field khác nhau; các header như `Date`, `Cache-Control`, `Content-Length` phụ thuộc môi trường. Không viết kiểm thử so sánh toàn bộ HTTP response theo byte khi chỉ cần xác nhận status và challenge.

### 7.4. Vì sao 403 không phải 401?

Request `reader:demo-pass` tới `/api/admin` đã qua authentication thành công. Authorization biết user thiếu `ROLE_ADMIN`. Bắt người dùng nhập lại cùng credential là sai mục đích; phản hồi thông thường là 403. Điều này cho thấy realm không thay thế role policy.

## 8. Integration test bằng WebTestClient

Tệp `src/test/java/example/BasicChallengeIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BasicChallengeIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String BASIC_CHALLENGE =
        "Basic realm=\"Learning API\"";

    @Test
    void missingCredentialGets401AndRealm() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE, BASIC_CHALLENGE);
    }

    @Test
    void wrongCredentialAlsoGets401AndRealm() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE, BASIC_CHALLENGE);
    }

    @Test
    void correctCredentialAllowsPrivateEndpoint() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("private")
            .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void missingAdminRoleIs403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectCredentialIsAllowed() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("admin")
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void publicRouteDoesNotRequireCredential() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test` nếu có wrapper. Sáu test kỳ vọng pass với dependency/configuration của demo. Các test cố ý xác minh **header challenge cả ở nhánh thiếu credential lẫn nhánh sai credential**; kiểm thử riêng 403 chứng minh logic authorization không bị ép vào entry point Basic.

Bài này cung cấp code có thể chạy độc lập khi bạn tạo đúng các file/dependency, nhưng log/status thực tế vẫn cần xác nhận trên môi trường chạy; không coi một trích đoạn HTTP bất biến là proof thay cho test.

## 9. Khi muốn trả JSON lỗi thay vì response mặc định

Nhiều API muốn response body như:

~~~json
{"error":"authentication_required"}
~~~

Có thể dùng custom `ServerAuthenticationEntryPoint` để tạo JSON body trong lúc vẫn giữ HTTP challenge. Ví dụ **mảnh code trong một class cấu hình**, không phải chương trình độc lập:

~~~java
ServerAuthenticationEntryPoint jsonBasicEntryPoint =
    (exchange, exception) -> {
        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().set(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"Learning API\"");
        response.getHeaders().setContentType(
            MediaType.APPLICATION_JSON);

        byte[] body = "{\"error\":\"authentication_required\"}"
            .getBytes(StandardCharsets.UTF_8);

        return response.writeWith(
            Mono.just(response.bufferFactory().wrap(body)));
    };
~~~

Các import tương ứng: `ServerAuthenticationEntryPoint` thuộc `org.springframework.security.web.server`, `ServerHttpResponse` thuộc `org.springframework.http.server.reactive`, `HttpStatus`/`HttpHeaders`/`MediaType` thuộc `org.springframework.http`, `StandardCharsets` thuộc `java.nio.charset` và `Mono` thuộc Reactor.

Gắn entry point này vào cả hai nơi khi cần nhất quán:

~~~java
http.httpBasic(basic ->
    basic.authenticationEntryPoint(jsonBasicEntryPoint));

http.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(jsonBasicEntryPoint));
~~~

**Không ghép mảnh code này đồng thời với bean entry point demo ở mục 7 nếu chưa có ý định thay thế rõ ràng.** Nó chỉ cho thấy một chiến lược custom.

Các nguyên tắc:

1. Không làm mất `WWW-Authenticate` khi đã trả 401.
2. Đặt status/header trước khi body khiến response commit.
3. Không dùng `exception.getMessage()` hay username/account status cụ thể làm JSON lỗi công khai; tránh dò tài khoản.
4. Không trả 401 cho mọi access denied; 403 cần nhánh xử lý riêng.
5. Không tự block hoặc subscribe trong handler reactive; trả `Mono<Void>` cho framework.
6. Chọn scheme đúng: nếu API chỉ dùng Bearer JWT, không phát Basic challenge một cách tùy tiện.
7. Kiểm tra browser UX: JSON body không chắc ngăn được popup nếu challenge Basic vẫn được gửi.

## 10. Multiple SecurityWebFilterChain và nhiều cơ chế xác thực

Trong ứng dụng hỗn hợp có `/legacy/**` dùng HTTP Basic và `/api/**` dùng Bearer JWT, cần chọn đúng **security chain và entry point** theo request. Không thể giải quyết bằng cách đổi realm từ `Legacy` thành `API`:

- `securityMatcher(...)` quyết định chain khớp URL.
- `@Order` quyết định ưu tiên giữa nhiều chain; chỉ chain khớp đầu tiên được chọn.
- `authorizeExchange(...)` quyết định quyền trong chain đã chọn.
- `httpBasic(...)` / `oauth2ResourceServer(...)` quyết định authentication scheme.
- `authenticationEntryPoint` và failure handler quyết định challenge/response.

Một `WWW-Authenticate` có thể chứa nhiều challenge hoặc xuất hiện qua nhiều header field; RFC cho phép điều đó nhưng parser có thể gặp vấn đề với dấu phẩy bên trong quoted-string. Nếu chỉ dùng Basic, nên giữ challenge rõ ràng; đừng lấy `split(",")` làm parser tổng quát cho WWW-Authenticate.

Đặc biệt tránh gắn Basic entry point toàn cục cho mọi URL của API Bearer: nó có thể khiến client nhận sai challenge và đưa password vào nơi không mong muốn.

## 11. Các lỗi phổ biến

**Lỗi 1 — Trả 401 nhưng bỏ `WWW-Authenticate`.** RFC 9110 yêu cầu 401 có challenge áp dụng. Với Basic nên dùng `HttpBasicServerAuthenticationEntryPoint` hoặc custom handler giữ header.

**Lỗi 2 — Coi realm là role hoặc tenant.** Realm là nhãn protection space, không xác nhận identity; chỉ authorization policy đã kiểm chứng mới cấp quyền.

**Lỗi 3 — Nhầm chiều header.** `WWW-Authenticate` là server → client, `Authorization` là client → server. Không đưa raw password vào challenge.

**Lỗi 4 — Chỉ custom `httpBasic.authenticationEntryPoint` nhưng quên `exceptionHandling.authenticationEntryPoint`.** Nhánh sai password và nhánh không credential có thể khác realm; test cả hai.

**Lỗi 5 — Dùng API Servlet.** WebFlux cần `ServerWebExchange` và `ServerAuthenticationEntryPoint`, không phải `HttpServletResponse`.

**Lỗi 6 — Dùng 401 cho người đã authenticated nhưng thiếu role.** Kết quả thường đúng là 403; không đẩy client vào vòng lặp Basic prompt không cần thiết.

**Lỗi 7 — Tưởng Base64 bảo mật password.** Basic cần HTTPS/TLS; cấm log credential và không truyền password trong URL.

**Lỗi 8 — Trả chi tiết “user không tồn tại/đã khóa” qua response công khai.** Điều này hỗ trợ user enumeration; dùng mã lỗi tổng quát, ghi chi tiết ở audit có kiểm soát.

**Lỗi 9 — Đổi realm để logout.** Realm không tự xóa cache credential của browser hoặc làm token/session vô hiệu; thiết kế logout theo auth scheme thật.

**Lỗi 10 — Cho rằng `permitAll` làm mọi request luôn 200.** Header Basic sai có thể bị authentication filter từ chối ngay cả ở endpoint public.

**Lỗi 11 — Cứ có Basic challenge thì browser sẽ luôn prompt.** Hành vi thay đổi theo client, request context và browser policy; phải test ứng dụng thật.

**Lỗi 12 — Dùng chung Basic challenge cho resource server JWT.** Các scheme khác cần challenge/entry point phù hợp, không thể thay bằng một realm.

**Lỗi 13 — So sánh nguyên response dump.** Header động và JSON property order có thể khác; kiểm thử status, WWW-Authenticate value và các field có ý nghĩa.

**Lỗi 14 — Không phân biệt proxy authentication với origin authentication.** 407/Proxy-Authenticate khác 401/WWW-Authenticate.

**Lỗi 15 — Tạo realm từ query/header không validate.** Realm là HTTP header value; có thể gây header injection hoặc dữ liệu nhạy cảm xuất hiện trong response.

## 12. Checklist review trước khi triển khai

1. Tài nguyên cần HTTP Basic thực sự hay phù hợp hơn với Bearer/OIDC/session login?
2. Kết nối có HTTPS và kiểm soát đủ các hop qua gateway/reverse proxy chưa?
3. `securityMatcher` và `authorizeExchange` bao phủ đúng tài nguyên cần bảo vệ?
4. Chưa credential → **401** cùng Basic realm challenge đúng?
5. Sai Basic password → **401** cùng realm/challenge phù hợp?
6. Authenticated nhưng thiếu role → **403**, không ép sang 401?
7. Public route → hoạt động không credential; hành vi khi gửi Basic sai đã xác nhận?
8. Realm có ngắn, ổn định, không chứa dữ liệu nhạy cảm hoặc input không tin cậy?
9. Có cấu hình entry point nhất quán cho nhánh thiếu credential và authentication failure?
10. Có test `WebTestClient` cho status và `WWW-Authenticate`?
11. Không log `Authorization`, Basic credential, cookie hoặc password?
12. Nếu response có JSON lỗi, đã giữ challenge khi 401 và không lộ account enumeration?
13. Nếu có nhiều chain/scheme, challenge được chọn đúng theo URL và mechanism?
14. Client chính (curl/browser/SPA/mobile) có hành vi khi 401 đúng UX, không loop vô hạn?
15. Có rate limiting, TLS, password hashing, credential rotation và incident response?
16. Không dựa vào realm để thực hiện logout, xác thực tenant hoặc cấp role.

## 13. Câu hỏi ôn tập

**1.** `WWW-Authenticate: Basic realm="Learning API"` có chứng minh user đã đăng nhập không?

**Đáp án:** Không. Đây là challenge do server gửi cho client, không phải Authentication hoặc principal.

**2.** Một endpoint được bảo vệ bởi `authenticated()` nhận request không credential, status và header hợp lý cho Basic là gì?

**Đáp án:** 401 Unauthorized cùng `WWW-Authenticate: Basic realm="..."` theo realm của ứng dụng.

**3.** User nhập đúng password nhưng thiếu `ROLE_ADMIN` truy cập `/api/admin`. Nên trả 401 hay 403?

**Đáp án:** Thường là 403 vì Authentication hợp lệ nhưng authorization thất bại.

**4.** Đặt `realm="ADMIN"` có tự chuyển `reader` thành admin không?

**Đáp án:** Không. Realm chỉ định nhãn protection space; role quyết định bằng policy dựa trên Authentication/authorities.

**5.** Điểm khác biệt giữa 401 và 407?

**Đáp án:** 401 dùng `WWW-Authenticate` cho origin server; 407 dùng `Proxy-Authenticate` cho proxy.

**6.** Vì sao 401 JSON thiếu `WWW-Authenticate` là vấn đề?

**Đáp án:** Nó có thể không tuân theo RFC 9110, khiến client không biết scheme cần dùng. Phải dùng entry point/challenge hợp lệ.

**7.** Client gửi Basic sai tới route `permitAll` có chắc nhận 200?

**Đáp án:** Không. Authentication filter có thể từ chối credential sai trước authorization.

**8.** Làm thế nào để kiểm tra realm đúng cho cả missing credentials và wrong credentials?

**Đáp án:** Cấu hình entry point thống nhất cho `httpBasic` và `exceptionHandling` khi cần; viết hai test riêng với WebTestClient xác nhận status 401 và header.

## Tài liệu chính thức

- RFC 7617 — The "Basic" HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 — HTTP Semantics, mục 11.6.1 và 15.5.2: https://www.rfc-editor.org/rfc/rfc9110.html
- Spring Security — HttpBasicServerAuthenticationEntryPoint (reactive): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html
- Spring Security — ServerHttpSecurity.HttpBasicSpec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — ServerHttpSecurity / exceptionHandling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5 — System Requirements (JDK/Gradle): https://docs.spring.io/spring-boot/3.5/system-requirements.html
