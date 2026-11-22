# HTTP Basic trong trình duyệt và mối liên hệ với CSRF

## 1. Vấn đề: Basic stateless vẫn có rủi ro CSRF

HTTP Basic cho phép một client gửi username và password qua HTTP header `Authorization` để server xác thực từng request. Trong ứng dụng Spring WebFlux, điều đó có thể diễn ra mà không phải lưu thông tin đăng nhập vào session của server.

Tuy nhiên, **không lưu session đăng nhập không đồng nghĩa với miễn nhiễm CSRF**, đặc biệt khi client là trình duyệt. Browser có thể nhớ HTTP Basic credentials theo phạm vi xác thực (protection space), rồi tự đính kèm chúng vào những request sau tới đích phù hợp. Nếu một website khác khiến browser phát request làm thay đổi trạng thái ở ứng dụng đang được bảo vệ, server có thể nhìn thấy credentials hợp lệ dù người dùng không chủ động chọn hành động đó.

Spring Security nêu rõ trường hợp **browser sử dụng Basic authentication vẫn có thể dễ bị CSRF**, tương tự các cơ chế mà browser tự gửi credential. Điều này khác với một CLI hoặc backend service chỉ tự đặt Authorization header trong code do bạn kiểm soát.

**Lưu ý quan trọng:** không nên khẳng định mọi phiên bản browser luôn tự gửi Basic credentials với bất kỳ request cross-site nào. Kết quả phụ thuộc cache, origin, realm, kiểu điều hướng, `fetch` credentials mode và chính sách browser. Thiết kế bảo mật phải xét khả năng **ambient authentication** trong các kịch bản thực tế và kiểm thử trên những trình duyệt được hỗ trợ.

### Mục tiêu bài học

Sau khi học, bạn cần:

1. Hiểu HTTP Basic challenge/response, browser authentication cache và lý do Base64 không phải mã hóa.
2. Mô tả chính xác một request giả mạo có thể lợi dụng Basic credentials.
3. Phân biệt CSRF với CORS, SameSite, authentication, authorization và XSS.
4. Biết `CsrfWebFilter`, `ServerCsrfTokenRepository`, token handler và quy tắc phương thức HTTP của Spring Security Reactive.
5. Viết được cấu hình Spring WebFlux Basic + CSRF mặc định, và kiểm thử POST thiếu/có token.
6. Lấy và sử dụng CSRF token trong một ứng dụng Java 17+ chạy độc lập bằng Gradle.
7. Biết khi nào mới cân nhắc tắt CSRF và vì sao cấu hình stateless authentication riêng không đủ.

Đây là bài thuộc phần **HTTP Basic** của module Spring Security Reactive. Trọng tâm là browser: không biến nó thành một bài tổng quan tất cả authentication mechanisms.

## 2. HTTP Basic trong trình duyệt hoạt động thế nào?

HTTP Basic được mô tả tại RFC 7617. Request ví dụ:

~~~http
GET /api/memo HTTP/1.1
Host: example.test
Authorization: Basic bGVhcm5lcjpsb2NhbHBhc3M=
~~~

Payload Base64 ở ví dụ biểu diễn chuỗi `learner:localpass`, không phải chuỗi đã được mã hóa bí mật. Người có khả năng xem header có thể giải mã nó; **HTTPS/TLS là yêu cầu bắt buộc cho credentials thật**. Không đưa username/password vào URL, query string hoặc log.

Khi endpoint bảo vệ chưa nhận được credentials hợp lệ, server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="example"
~~~

`WWW-Authenticate` là HTTP authentication challenge. Trình duyệt có thể hiện hộp thoại yêu cầu username/password và tái sử dụng chúng theo chính sách cache. Dòng tương tác điển hình:

~~~text
Browser                                     WebFlux Security
   |                                                |
   | GET /api/memo                                  |
   |----------------------------------------------->|
   | 401 + WWW-Authenticate: Basic ...               |
   |<-----------------------------------------------|
   |                                                |
   | Người dùng nhập thông tin đăng nhập             |
   | GET /api/memo + Authorization: Basic ...        |
   |----------------------------------------------->|
   | 200 + dữ liệu                                  |
   |<-----------------------------------------------|
~~~

Khi browser giữ Basic credentials, những request sau có thể được xác thực mà người dùng không phải nhập lại. **Đó là tiện ích và cũng là yếu tố cần xem xét trong threat model CSRF.**

### 2.1. Realm, origin và phiên đăng nhập

Phân biệt:

- **Authentication cache của browser:** nơi trình duyệt quản lý thông tin HTTP authentication theo chính sách của nó.
- **Reactor Context:** context của một subscription request WebFlux; Spring Security đặt `Authentication` vào đó sau khi xác thực.
- **`ServerSecurityContextRepository`:** chiến lược lưu/tải `SecurityContext` giữa request; có thể cấu hình no-op.
- **`WebSession`:** đối tượng phiên trong WebFlux; có thể phục vụ mục đích CSRF hoặc mục đích khác, không nhất thiết là session login.
- **`realm`:** chỉ dẫn của Basic challenge, không phải một đối tượng Java hay một cookie.

Không có cookie login trên response **không chứng minh** browser không có credentials có thể được tái dùng. Ngược lại, browser gửi header Basic hợp lệ cũng không chứng minh server đã lưu authentication vào WebSession.

### 2.2. Logout khó xử lý hơn form login

Với form login/session, server có thể hủy session để kết thúc lần đăng nhập. Với HTTP Basic, browser có thể còn nhớ username/password và tự gửi lại; server không thể đảm bảo logout chỉ bằng xóa một server session. Hành vi quên credentials khác nhau giữa browser. Với ứng dụng browser production cần luồng login/logout UX mạnh, nên đánh giá phương thức authentication phù hợp thay vì chỉ dùng Basic.

## 3. CSRF là gì, và mối liên hệ với HTTP Basic

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công trong đó một nguồn không đáng tin khiến trình duyệt của người dùng gửi request có tác dụng phụ tới một ứng dụng mà người dùng đã có ngữ cảnh xác thực. Server có thể nhận dạng đúng user từ credential nhưng không biết người dùng thực sự có chủ ý yêu cầu hành động đó hay không.

Hãy tưởng tượng `https://account.example.test` cung cấp:

~~~http
POST /api/change-email
Content-Type: application/x-www-form-urlencoded

email=another@example.test
~~~

Một trang khác có thể chứa form:

~~~html
<!-- Chỉ minh họa cơ chế: không phải đoạn code cần đưa vào sản phẩm. -->
<form action="https://account.example.test/api/change-email"
      method="post">
  <input name="email" value="other@example.test">
  <button type="submit">Continue</button>
</form>
~~~

Form ở origin khác có thể kích hoạt request tới ứng dụng đích. Nếu browser tự đính kèm Basic credentials đã nhớ trong kịch bản đó, và server chỉ kiểm tra username/password, hành động có thể được thực hiện ngoài ý muốn. Attacker **không cần biết password và không cần đọc được body response**.

Rủi ro phụ thuộc từng browser/bối cảnh cụ thể; ví dụ nhằm giải thích **điều kiện tấn công** chứ không khẳng định mọi browser luôn gửi Basic trên tất cả cross-site forms.

### 3.1. Các điều kiện để CSRF gây tác hại

Một tình huống CSRF thường có:

1. **Có side effect** như đổi email, mua hàng, xóa tài nguyên, cập nhật cấu hình hoặc chuyển tiền.
2. **Browser có quyền được tự động gửi kèm** theo request tới ứng dụng đích: cookie, HTTP Basic credentials được nhớ hoặc cơ chế ambient authentication tương tự.
3. **Nguồn bên ngoài có khả năng khiến browser phát request** phù hợp.
4. **Server thiếu biện pháp kiểm tra tính hợp lệ của request** ngoài việc xác thực danh tính.

Nếu attacker đánh cắp password và tự gửi request từ máy của họ, đó là **credential compromise** chứ không phải CSRF. Trong CSRF, browser nạn nhân thực hiện request có context xác thực.

### 3.2. Authentication không chứng minh ý định của người dùng

- HTTP Basic hỏi: “Request có credentials đúng không?”
- Authorization hỏi: “Danh tính đó có được phép thay đổi tài nguyên này không?”
- CSRF bảo vệ: “Request thay đổi trạng thái này có được khởi tạo qua luồng tin cậy của ứng dụng không?”

Một request có thể vượt qua Basic **và** authorization nhưng vẫn là CSRF. Vì vậy, một POST có Basic credentials hợp lệ vẫn có thể phải bị chặn nếu thiếu CSRF token.

## 4. Stateless không đồng nghĩa miễn nhiễm CSRF

Một kiến trúc WebFlux có thể đặt:

~~~java
http.securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
~~~

Lệnh này yêu cầu Spring Security **không lưu/tải `SecurityContext` qua repository để tái dùng giữa những request**. Nó không xóa browser Basic authentication cache, không tắt CSRF và không tự vô hiệu việc lưu CSRF token trong WebSession.

Bảng phân biệt:

| Khái niệm | Chức năng | Có bị NoOpServerSecurityContextRepository tắt không? |
| --- | --- | --- |
| HTTP Basic credentials browser cache | Browser nhớ và có thể tái gửi username/password | **Không** |
| Reactive `SecurityContext` | Danh tính của subscription/request hiện tại | **Không** |
| Authentication persistence | Lưu context từ request trước | **Có**, với repository đã chọn |
| CSRF token | Kiểm chứng request unsafe | **Không** |
| `WebSessionServerCsrfTokenRepository` | Lưu expected CSRF token trong WebSession | **Không** |
| HTTP response cache | Cache response ở browser/proxy | **Không** |
| CORS | Quy định truy cập liên-origin của JavaScript | **Không** |

Đặc biệt, WebFlux CSRF mặc định lưu expected token trong `WebSession`. Một ứng dụng **không lưu authentication** vẫn có thể tạo cookie WebSession để lưu token CSRF. “Có session cookie” và “đã lưu đăng nhập” là hai điều khác nhau.

Nếu hệ thống yêu cầu không duy trì **bất kỳ server-side session** nào, cả authentication persistence **lẫn** CSRF repository/client integration phải được thiết kế phù hợp; tắt một thành phần không chứng minh yêu cầu tổng thể đã đạt.

## 5. Spring Security Reactive bảo vệ CSRF như thế nào?

Trong `SecurityWebFilterChain` của WebFlux, những thành phần chính là:

- `CsrfWebFilter`: tham gia chuỗi WebFilter, xác định request nào cần bảo vệ, nạp/xác minh token và từ chối request thiếu/sai.
- `ServerCsrfTokenRepository`: hợp đồng tạo, lưu và đọc expected token.
- `WebSessionServerCsrfTokenRepository`: implementation mặc định lưu token trong WebSession.
- `CookieServerCsrfTokenRepository`: lựa chọn lưu token qua cookie cho một số ứng dụng frontend.
- `ServerCsrfTokenRequestHandler`: cung cấp và trích xuất token từ request/attribute.
- `XorServerCsrfTokenRequestAttributeHandler`: request handler mặc định từ Spring Security 6.x, bổ sung cơ chế masking để giảm rủi ro BREACH trong tình huống thích hợp.

**CSRF protection mặc định được bật** trong Spring Security WebFlux. Theo quy tắc thường dùng, các HTTP method `GET`, `HEAD`, `TRACE`, `OPTIONS` được coi là an toàn và không yêu cầu CSRF token; các method unsafe như `POST`, `PUT`, `PATCH`, `DELETE` yêu cầu token.

Điều này đồng nghĩa developer **phải đảm bảo GET/HEAD không có side effect**. Spring Security không tự đọc logic controller để biết một GET có đang xóa đơn hàng hay không.

### 5.1. Luồng kiểm tra POST

~~~text
POST /api/memo
       |
       v
CsrfWebFilter: yêu cầu có cần CSRF không?
       |
       +--> Thiếu / token sai --> từ chối (thường HTTP 403)
       |
       +--> Token hợp lệ
                |
                v
           Authentication/Authorization
                |
                v
           Controller xử lý
~~~

Đây là sơ đồ khái niệm, không phải danh sách thứ tự tuyệt đối mọi filter. Một POST thiếu cả Basic credentials và CSRF token có thể nhận **403 trước khi authorization trả 401**, tùy filter order. Không sử dụng status code đơn lẻ để đoán toàn bộ quá trình.

### 5.2. CSRF token phải được gửi ở đâu?

Để phân biệt request hợp lệ với request bị giả mạo, client phải gửi token trong phần request **không được browser tự động thêm chỉ vì có credentials**:
- Hidden form parameter, thường là `_csrf`.
- HTTP header như `X-CSRF-TOKEN` hoặc tên do repository/handler cấu hình.
- Phương án phù hợp khác theo threat model.

Ví dụ request có đủ Basic và CSRF:

~~~http
POST /api/memo HTTP/1.1
Host: example.test
Authorization: Basic ...
X-CSRF-TOKEN: <csrf-token-duoc-cap>
Content-Type: text/plain

new-value
~~~

Header Basic **không thay thế** CSRF token. Bất kỳ origin nào không được phép đọc token cũng không được vô tình cấp quyền đọc endpoint token bằng CORS rộng.

### 5.3. Spring Security 6 và masking token

`CsrfWebFilter` có thể đặt `Mono<CsrfToken>` vào `ServerWebExchange` với key `CsrfToken.class.getName()`. Từ Spring Security 6, handler mặc định có masking để chống BREACH; ứng dụng frontend nên sử dụng **token được xuất ra qua request handler**, không cố tự lấy raw token từ repository rồi sửa token theo một thuật toán tự nghĩ.

Với HTML form, Thymeleaf có integration hiển thị token. Với SPA/AJAX, có thể dùng endpoint hoặc cookie repository theo cấu hình thích hợp. Luồng login/logout có thể làm token đổi; frontend cần lấy lại token hợp lệ khi ngữ cảnh thay đổi.

## 6. CSRF khác với CORS và SameSite

**CORS** chủ yếu điều khiển quyền của JavaScript ở một origin khác khi gửi các yêu cầu liên-origin hoặc đọc kết quả theo Fetch/XHR. **CSRF** là nguy cơ người dùng bị dụ gửi request có side effect; attacker **không cần đọc response**.

Một HTML form cross-site có thể gửi request thuộc loại đơn giản mà không dựa vào quyền đọc response của JavaScript. Do đó, **“CORS không cho phép attacker origin” không đủ để tuyên bố không có CSRF**.

| Câu hỏi | CORS | CSRF |
| --- | --- | --- |
| Script origin khác có thể đọc response? | Có kiểm soát | Không phải mục tiêu chính |
| Request thay đổi trạng thái có được gửi từ luồng tin cậy? | Không bảo đảm | Có cơ chế chống giả mạo |
| Có thay cho Basic authentication? | Không | Không |
| Có ngăn mọi HTML form cross-site gửi request? | Không phải bảo đảm | Token có thể ngăn server chấp nhận |
| Có thể cấu hình sai và làm lộ token? | Có | Token vẫn cần được bảo vệ |

### 6.1. SameSite chỉ xử lý cookie

Thuộc tính cookie `SameSite=Lax/Strict` có thể hạn chế gửi cookie cross-site trong những điều kiện nhất định. Nhưng cached HTTP Basic Authorization **không phải cookie**, nên không thể lấy SameSite của một cookie bất kỳ làm bằng chứng browser sẽ không gửi Basic credentials.

Nếu CSRF token được lưu trong WebSession/cookie, chính cookie ấy cũng cần cấu hình Secure/HttpOnly/SameSite đúng yêu cầu. Chú ý “same-site” không hoàn toàn giống “same-origin”; các subdomain cùng site vẫn có thể khác origin.

### 6.2. XSS là một mối nguy khác

Nếu attacker có thể chạy JavaScript trong **chính origin** hợp pháp (XSS), script đó có thể đọc CSRF token mà frontend được phép đọc và dùng nó để phát request. Vì thế CSRF token không thay cho phòng chống XSS, output encoding và Content Security Policy. Các biện pháp là lớp bảo vệ bổ trợ.

## 7. Ví dụ Java 17+ chạy được: Basic + CSRF trong WebFlux

Dự án dưới đây dùng Spring Boot **3.3.13**, Spring Security Reactive 6.x, Java 17 và Gradle. Mục tiêu là học cơ chế: có Basic credentials đúng **vẫn chưa đủ** để POST nếu thiếu CSRF token.

Một `AtomicReference<String>` mô phỏng dữ liệu trong bộ nhớ. Mật khẩu demo dùng `{noop}` chỉ để đơn giản hóa; **không sử dụng trong production**.

~~~text
webflux-basic-csrf/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── MemoController.java
    └── test/java/demo/
        └── BasicCsrfTest.java
~~~

### 7.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-csrf'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Application

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityWebFilterChain

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
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

Phân tích:
1. `authorizeExchange` yêu cầu xác thực cho mọi endpoint demo, gồm `/csrf`.
2. `httpBasic` bật cơ chế đọc Basic credentials.
3. `formLogin` bị tắt để tránh lẫn luồng form login với Basic.
4. `NoOpServerSecurityContextRepository` không lưu authentication để dùng lại giữa request. Nó **không tắt** CSRF.
5. `csrf(Customizer.withDefaults())` giữ bảo vệ CSRF, mặc dù đây đã là default. Viết tường minh để người học thấy sự khác biệt giữa chính sách CSRF và authentication persistence.
6. `{noop}localpass` chỉ chạy demo local. Production phải dùng HTTPS, băm mật khẩu mạnh, rate limiting, giám sát đăng nhập và chính sách quản lý account phù hợp.

Không tự thêm `CsrfWebFilter` bằng tay; Spring Security điều phối filter khi xây dựng security chain.

### 7.4. Controller

`src/main/java/demo/MemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class MemoController {

    private final AtomicReference<String> memo =
            new AtomicReference<>("initial");

    @GetMapping(path = "/api/memo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readMemo() {
        return Mono.fromSupplier(memo::get);
    }

    @PostMapping(path = "/api/memo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> updateMemo(@RequestBody Mono<String> body) {
        return body.map(value -> {
            memo.set(value);
            return "saved:" + value;
        });
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is not available"));
        }

        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "token", value.getToken()));
    }
}
~~~

Giải thích:
- `GET /api/memo` chỉ đọc dữ liệu, nên không phải request có side effect.
- `POST /api/memo` thay đổi dữ liệu; handler **không được chạy** nếu CSRF filter từ chối trước.
- `Mono<String>` trong `@RequestBody` cho phép đọc request body theo pipeline WebFlux, không tự `block()` hoặc `subscribe()`.
- `GET /csrf` đọc `Mono<CsrfToken>` do Spring Security đặt trong exchange attribute. Khi được subscribe, token có thể được tạo/lưu theo repository.
- Token trả về qua `getToken()` có thể đã masking theo Spring Security 6.x; client dùng **giá trị được cung cấp**, không tự unmask.
- JSON trả về hai trường `headerName`, `token`; thứ tự key không cố định.
- Endpoint cấp token phải được bảo vệ khỏi origin không đáng tin đọc response; trong demo nó yêu cầu Basic authentication.

**Giới hạn minh họa:** cập nhật `AtomicReference` không phải database persistence và không có ràng buộc quyền sở hữu đối tượng nghiệp vụ. Ứng dụng sản xuất cần xác thực, authorization và transaction theo domain riêng. CSRF không thay các bước đó.

## 8. Chạy thử HTTP: 401, 403 và 200

Trong thư mục dự án, chạy:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, có thể dùng `./gradlew bootRun`. Server mặc định chạy tại `http://localhost:8080` trên máy local; môi trường thật phải dùng HTTPS. Chạy `curl` ở terminal khác:

~~~bash
# A. GET bảo vệ khi không có credentials
curl -i http://localhost:8080/api/memo

# B. GET có Basic đúng, không cần CSRF token
curl -i -u learner:localpass http://localhost:8080/api/memo

# C. POST có Basic đúng nhưng thiếu CSRF token
curl -i -u learner:localpass \
  -H 'Content-Type: text/plain' \
  --data 'changed-without-token' \
  http://localhost:8080/api/memo

# D. Kiểm tra POST trước đã bị chặn, dữ liệu chưa đổi
curl -i -u learner:localpass http://localhost:8080/api/memo
~~~

Kết quả kỳ vọng khi server mới khởi động:

| Lệnh | HTTP status | Ý nghĩa |
| --- | --- | --- |
| A | **401 Unauthorized** | Chưa xác thực; Basic entry point có thể trả `WWW-Authenticate` |
| B | **200 OK**, body `initial` | GET được xác thực; GET không cần CSRF token |
| C | **403 Forbidden** | POST bị từ chối vì thiếu token dù Basic đúng |
| D | **200 OK**, body vẫn `initial` | Controller POST không được chạy |

Không được suy ra POST chưa authentication chắc chắn trả 401: `CsrfWebFilter` có thể chặn request thiếu token trước tầng authorization. Cũng không nên suy ra mọi 403 đều là CSRF; 403 có thể do role/permission không đủ.

### 8.1. Nhận token và gửi POST hợp lệ

Với shell có `curl` và `jq`:

~~~bash
# Bước 1: lấy token, lưu cookie WebSession cho CSRF
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# Bước 2: tách tên header và token được phát ra
HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# Bước 3: gửi Basic + cùng cookie + CSRF header
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'updated-safely' \
  http://localhost:8080/api/memo

# Bước 4: kiểm tra đã cập nhật dữ liệu
curl -i -u learner:localpass http://localhost:8080/api/memo
~~~

Khi token và WebSession cookie vẫn hợp lệ, kết quả đáng tin cậy:

~~~text
POST /api/memo --> HTTP 200; body: saved:updated-safely
GET  /api/memo --> HTTP 200; body: updated-safely
~~~

Không thể cung cấp **token cụ thể** làm stdout cố định: token có giá trị ngẫu nhiên và có thể được masking. Nếu POST nhận 403, kiểm tra cookie jar, tên header, session hết hạn, token rotation, path/proxy và security chain. Đừng sửa bằng cách disable CSRF.

**Đề phòng secrets:** `curl -u user:password` có thể lưu password trong shell history hoặc lộ ở một số môi trường xem command line. Dùng demo password ở local; production dùng giải pháp quản lý secrets phù hợp và HTTPS.

### 8.2. Vì sao lại có WebSession cookie nếu authentication stateless?

Ở ví dụ này, authentication repository là **no-op**, nhưng repository CSRF mặc định vẫn lưu expected token trong **WebSession**. Khi lấy token, ứng dụng có thể tạo session/cookie cho mục đích **CSRF**. Cookie này phải được gửi lại để server có thể đối chiếu expected token. Không coi đó là “session Basic login”; request vẫn cần Basic credentials hợp lệ.

Nếu kiến trúc yêu cầu tuyệt đối không có server session, cần thiết kế CSRF token storage và browser integration khác, không thể chỉ tắt security context repository.

## 9. WebTestClient: kiểm thử CSRF với Basic credentials

Thêm `spring-security-test` như cấu hình Gradle ở trên. Spring Security cung cấp `SecurityMockServerConfigurers.csrf()` để test có một CSRF token hợp lệ trong WebFlux. Kiểm thử sau dùng application context và `WebTestClient`.

`src/test/java/demo/BasicCsrfTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BasicCsrfTest {

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
    void anonymousGetIsUnauthorized() {
        client.get().uri("/api/memo")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicGetNeedsNoCsrfToken() {
        client.get().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void basicPostWithoutCsrfIsForbidden() {
        client.post().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("should-not-save")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void basicPostWithCsrfIsAccepted() {
        client.mutateWith(csrf())
                .post().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng về test:** sau khi tạo các file/dependency như trên, các trường hợp cần cho thấy 401, 200, 403, 200. Đây là dự đoán theo cấu hình/API, **không phải khẳng định đã chạy build thực tế**. Test `csrf()` là test helper Spring Security, không phải cách bypass CSRF trong production.

Nếu muốn xác minh toàn bộ giao diện browser, phải kiểm tra ngoài test giả lập: browser tự gửi Basic credentials khi nào, token có được phát ra đúng cách không, cookie có bảo toàn giữa request, CORS có hạn chế origin, và logout/session expiration được xử lý ra sao.

## 10. Giao diện trình duyệt nên gửi CSRF token thế nào?

### 10.1. HTML form

Với ứng dụng render HTML, token thường nằm trong hidden input:

~~~html
<form method="post" action="/some-action">
  <input type="hidden" name="_csrf" value="token-from-server">
  <input type="text" name="value">
  <button type="submit">Save</button>
</form>
~~~

Đây là mẫu cấu trúc; **không phải form tương thích trực tiếp** với controller `/api/memo` ở demo vì endpoint nhận `text/plain`, còn form này gửi dữ liệu form. Trong ứng dụng thật, dùng endpoint nhận form data và integration của Thymeleaf/Spring Security hoặc logic view tương ứng để cấp token.

Không hard-code token trong source HTML. Giá trị token do server tạo và được liên kết với expected token trong repository.

### 10.2. SPA/JavaScript

Một frontend cùng origin có thể đọc token từ endpoint rồi đưa vào request unsafe:

~~~javascript
const result = await fetch("/csrf", { credentials: "same-origin" });
if (!result.ok) throw new Error("CSRF token unavailable");
const csrf = await result.json();

const response = await fetch("/api/memo", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "text/plain",
    [csrf.headerName]: csrf.token
  },
  body: "new-value"
});

if (!response.ok) throw new Error("Update rejected");
~~~

Đoạn này là **minh họa frontend**, không có nghĩa `fetch` chắc chắn tự tạo Basic credentials trong mọi tình huống. Trình duyệt có credential cache, policies và chế độ credentials riêng; endpoint vẫn cần Authentication hợp lệ. Với frontend khác origin, phải thiết kế CORS, CSRF, cookie, trusted origins và authorization phù hợp; không cho phép tùy tiện mọi origin đọc token.

### 10.3. Cookie CSRF repository

`CookieServerCsrfTokenRepository` là một lựa chọn khi ứng dụng JS cần tích hợp CSRF token qua cookie. `withHttpOnlyFalse()` có thể cho JavaScript đọc cookie, nhưng đánh đổi là token dễ bị JS cùng origin truy cập hơn. Nếu frontend không cần đọc cookie trực tiếp, ưu tiên giữ HttpOnly. Trong Spring Security 6.x, cần kiểm tra kết hợp với XOR/BREACH token request handler và quá trình xoay vòng token; không sao chép cấu hình của Servlet vào WebFlux mà bỏ qua khác biệt API.

CSRF token **không phải mật khẩu hay access token**, nhưng vẫn phải tránh lộ cho origin không tin cậy. Nếu XSS có thể chạy JS trong origin hợp pháp, bảo vệ CSRF token có thể bị vượt qua.

## 11. Khi nào cân nhắc tắt CSRF?

Trường hợp phổ biến là API **không phục vụ browser với ambient credentials**; client backend/mobile/CLI tự gắn Bearer token đã được bảo vệ trong mỗi request và browser không tự gửi credentials tới endpoint. Sau security review, hệ thống có thể quyết định rằng CSRF không cần thiết cho tập route đó.

Ví dụ **chỉ là snippet** cho API Resource Server được đánh giá riêng, không phải chương trình chạy độc lập:

~~~java
return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
~~~

Để chạy cần các dependency Resource Server, issuer/JWK/cấu hình JWT hợp lệ, chính sách authorization và error handling. Đoạn này **không áp dụng mặc định cho browser dùng HTTP Basic**.

Trước khi tắt CSRF, cần trả lời:
1. Có browser nào có thể tự đính kèm Basic credentials/cookie/client certificate không?
2. Có route POST/PUT/PATCH/DELETE thay đổi dữ liệu không?
3. Ứng dụng có trang browser, form login, OAuth2 login, logout hoặc SPA dùng cookie không?
4. Có endpoint GET vô tình thay đổi trạng thái không?
5. CORS và security chain matcher có giới hạn đúng phạm vi?
6. Đã kiểm thử browser/CSRF thực tế chứ không chỉ `curl`?
7. Có chính sách Origin/Referer/Fetch Metadata hoặc token cần áp dụng để phòng thủ nhiều lớp không?

Nếu không rõ, **giữ CSRF protection** và thiết kế cơ chế cấp/gửi token thay vì chỉ tắt để request chạy.

### 11.1. Nhiều security chains

Khi hệ thống đồng thời có:
- Website/browser login hoặc Basic,
- API máy-máy dùng Bearer token,

có thể thiết kế các `SecurityWebFilterChain` khác nhau theo `securityMatcher` và `@Order`, mỗi chain có CSRF policy phù hợp. Cẩn thận tránh một chain match-all ở vị trí quá sớm lấy mất request dành cho chain browser. Không tự suy ra từ tên bean rằng route đã được bảo vệ bằng chain mong muốn.

## 12. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| “Basic không dùng session nên không có CSRF” | Browser có thể tự gửi cached credentials | Xét ambient authentication trên browser |
| Dùng GET cho thao tác thay đổi dữ liệu | CSRF mặc định bỏ qua safe methods | Dùng method phù hợp, giữ bảo vệ CSRF |
| Tắt `csrf()` để chữa POST 403 | Mất lớp bảo vệ request giả mạo | Lấy/gửi token hợp lệ |
| Dùng CORS để thay CSRF | HTML form/simple request không cần đọc response | Giữ biện pháp chống CSRF độc lập |
| Dùng SameSite cookie làm bằng chứng Basic an toàn | SameSite chỉ áp cho cookie | Kiểm tra cơ chế Authorization của browser |
| Cho origin ngoài ý muốn đọc `/csrf` | Có thể lộ token | Giới hạn CORS/origin của endpoint |
| Không lưu cookie giữa GET token và POST | Repository không tìm được expected token | Giữ cookie/session theo cùng ngữ cảnh |
| Tự “unmask” token từ Spring Security 6 | Token handler có thể không chấp nhận | Sử dụng token do API hiện hành cấp |
| Dùng `{noop}` trong sản phẩm | Password lưu dạng rõ | Dùng PasswordEncoder có thuật toán mạnh |
| Nghĩ Base64 là encryption | Lộ Basic credentials khi không dùng TLS | Bắt buộc HTTPS |
| Đọc CSRF token bằng `block()` trong WebFlux | Chặn event-loop, tạo subscription sai | Compose trong `Mono` |
| Tự `subscribe()` tạo tác vụ xác thực | Tách request context/lỗi/cancellation | Trả Publisher cho framework |
| Nhầm 401 và 403 | Chẩn đoán sai filter/role/token | Phân biệt authentication, CSRF, authorization |

Ví dụ sai nghiêm trọng:

~~~java
// SAI: GET lại thực hiện xóa dữ liệu.
@GetMapping("/account/delete")
public Mono<Void> deleteAccount() {
    return accountService.deleteCurrentAccount();
}
~~~

Đây là snippet minh họa, không chạy độc lập vì không định nghĩa `accountService`. Nếu một GET có side effect, CSRF token theo policy mặc định có thể không được yêu cầu. Hãy sửa HTTP semantics và authorization thay vì chỉ chỉnh CORS.

### 12.1. Đừng chỉ nhìn HTTP status

- `GET` thiếu Basic tới route bảo vệ thường trả **401**.
- `POST` có Basic hợp lệ nhưng thiếu token thường trả **403**.
- `POST` thiếu cả Basic lẫn token có thể bị CSRF chặn trước và trả **403**, không nhất thiết là 401.
- `POST` có token hợp lệ nhưng username/password sai vẫn bị authentication từ chối.
- `POST` có token và Basic đúng nhưng thiếu role vẫn bị authorization từ chối, thường **403**.

Cần xem filter chain, exception mapping và log kỹ thuật **không nhạy cảm** để xác định nguyên nhân thực, không nên “fix 403” bằng cách cấp thêm role cho người dùng hoặc tắt CSRF.

## 13. Checklist khi kiểm tra browser Basic + CSRF

1. Xác định route đang chạy trên `SecurityWebFilterChain` nào.
2. Kiểm tra `httpBasic` và entry point 401/`WWW-Authenticate`.
3. Kiểm tra request unsafe có cần CSRF theo matcher không.
4. Đảm bảo GET/HEAD thực sự read-only, không side effect.
5. Xác định CSRF token repository: WebSession, cookie hay tùy biến.
6. Kiểm tra ứng dụng có cấp `CsrfToken` cho frontend qua view/endpoint đáng tin cậy không.
7. Xác minh token gửi qua đúng header/form parameter và qua request handler phù hợp phiên bản.
8. Nếu token nằm WebSession, kiểm tra cookie phiên được giữ giữa GET cấp token và POST.
9. Kiểm tra expiry/rotation sau login, logout và session timeout.
10. Kiểm tra browser Basic cache, realm/protection space và phản ứng ở nhiều loại navigation/fetch.
11. Kiểm tra CORS chỉ cho phép origin thực sự tin cậy; attacker không đọc được token.
12. Kiểm tra HTTPS, password hashing, rate limit và thiếu sót khác ngoài CSRF.
13. Viết test cho 200/401/403 và ca user hợp lệ nhưng thiếu quyền.
14. Kiểm tra trực tiếp với browser được hỗ trợ, không chỉ dựa vào trạng thái của `curl`.
15. Tránh log Authorization header, CSRF token, session cookie và mật khẩu.

Nếu gặp 403, so sánh hai POST cùng credentials, một thiếu token và một có token đúng. Nếu GET Basic thành công nhưng POST thiếu token trả 403, đó là dấu hiệu **CSRF đang chặn theo chủ đích**, không phải “Basic hỏng”.

## 14. Câu hỏi tự kiểm tra

**1.** Browser đã nhớ Basic credentials nhưng server không lưu session đăng nhập. Có CSRF không?

> Có thể có. Browser có thể tự gửi credentials khi thực hiện request tới ứng dụng đích. Không lưu SecurityContext giữa request không loại bỏ rủi ro này.

**2.** Vì sao header Basic không đủ để chống CSRF?

> Basic chứng minh danh tính của request; CSRF bảo vệ ý định/ngữ cảnh tạo thao tác thay đổi trạng thái.

**3.** Vì sao POST có Basic đúng đôi khi trả 403?

> Thiếu/sai CSRF token hoặc không đủ quyền. Cần xác định tầng từ chối.

**4.** `NoOpServerSecurityContextRepository` có tắt WebSession CSRF repository không?

> Không. Chúng quản lý hai loại state khác nhau.

**5.** Spring Security WebFlux mặc định yêu cầu token CSRF cho GET không?

> Không. Vì vậy GET phải an toàn, không có side effects.

**6.** CORS có đảm bảo một HTML form từ origin khác không gửi POST được không?

> Không. CORS không thay thế biện pháp chống CSRF.

**7.** SameSite=Strict của cookie có đảm bảo không gửi HTTP Basic đã cache không?

> Không. SameSite là chính sách cookie, không phải chính sách cache HTTP Basic.

**8.** Tại sao phải mang cookie khi dùng WebSession CSRF token repository?

> Server cần tra được expected token gắn với cùng WebSession để so sánh với token client gửi.

**9.** Có nên disable CSRF cho mọi REST API không?

> Không. Xét client là browser hay machine, liệu browser tự gửi credentials không, và threat model của từng route.

**10.** Base64 có bảo vệ password Basic khỏi người đọc được đường truyền không?

> Không. Base64 giải mã được; phải dùng HTTPS.

## 15. Ghi nhớ và tài liệu tham khảo

**HTTP Basic trong browser không tự ngăn CSRF, kể cả khi server không có session đăng nhập.** CSRF liên quan đến khả năng browser tự mang thông tin xác thực tới một request thay đổi trạng thái; không chỉ liên quan đến cookie.

Trong Spring Security Reactive, cần giữ `CsrfWebFilter` cho trường hợp browser Basic, cấp token phù hợp và yêu cầu token ở các request unsafe. `NoOpServerSecurityContextRepository` chỉ quyết định persistence của authentication, không quyết định CSRF. CORS và SameSite là những lớp bảo vệ khác, không phải phép thay thế trực tiếp cho CSRF.

Để bảo vệ đúng, sử dụng HTTP methods đúng semantics, thực hiện HTTPS, xác minh CSRF token và authorization độc lập, rồi kiểm thử browser cùng WebTestClient.

### Tài liệu chính thức

- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — CSRF and Stateless Browser Applications: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security — Testing CSRF in WebFlux: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — WebFlux Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- MDN — HTTP Authentication: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS