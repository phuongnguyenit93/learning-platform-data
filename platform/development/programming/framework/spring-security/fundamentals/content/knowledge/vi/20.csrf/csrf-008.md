# Khi nào cân nhắc ngoại lệ và vì sao không tắt CSRF theo thói quen

> **Module:** Spring Security - fundamentals  
> **Chủ đề cha:** CSRF  
> **Nguyên tắc:** Không tắt CSRF chỉ vì một request `POST` trả `403 Forbidden`. Trước hết phải xác định trình duyệt có tự động gửi credential hay không. Nếu thật sự cần miễn CSRF, hãy giới hạn ngoại lệ theo **đúng endpoint, HTTP method và mô hình xác thực**, rồi kiểm thử các endpoint còn lại vẫn được bảo vệ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **Cross-Site Request Forgery (CSRF)** và lý do session cookie làm một hành động trái ý muốn có thể được gửi dưới danh nghĩa người đang đăng nhập.
- Phân biệt CSRF với **authentication**, **authorization**, CORS và XSS; hiểu tại sao `permitAll()` không làm request được miễn CSRF.
- Biết khi nào có cơ sở để **cân nhắc ngoại lệ**, chẳng hạn một webhook server-to-server có chữ ký đã xác minh, hoặc một API chỉ nhận bearer token qua header và không sử dụng credential mà trình duyệt tự gửi.
- Sử dụng Spring Security 6 với `csrf.ignoringRequestMatchers(...)` để miễn **một tuyến và một phương thức**, thay vì `csrf.disable()` trên toàn bộ ứng dụng.
- Hiểu các chi tiết thực tế của Spring Security: HTTP safe methods, `CsrfFilter`, `CsrfTokenRepository`, token trong form/header, login/logout, SPA và token rotation.
- Tạo ví dụ Spring Boot/Java 17 có endpoint trình duyệt cần CSRF và endpoint webhook không cần token CSRF nhưng được bảo vệ bằng **HMAC signature**.
- Viết kiểm thử khẳng định cả nhánh **cho phép** lẫn nhánh **từ chối**, để bảo đảm ngoại lệ không vô tình mở đường cho request trái quyền.

## 2. CSRF là lỗi gì?

Giả sử Alice đăng nhập một ứng dụng ngân hàng dùng cookie để duy trì phiên. Browser của Alice lưu cookie phiên; khi browser gửi request tới ngân hàng đúng phạm vi cookie, cookie có thể được tự động đính kèm.

Trong lúc vẫn đăng nhập, Alice mở một trang do kẻ tấn công kiểm soát. Trang đó cố khiến browser gửi một request thay đổi trạng thái đến ngân hàng:

~~~text
Alice đã login ngân hàng
         |
         | Browser có cookie session của ngân hàng
         v
Mở trang của kẻ tấn công
         |
         | HTML form hoặc request khác hướng tới ngân hàng
         v
Browser gửi request đến ngân hàng
         |
         | Cookie được browser tự gửi theo quy tắc cookie
         v
Ngân hàng nhìn thấy session của Alice
         |
         v
Nếu không có biện pháp ngăn CSRF, hành động có thể được xử lý
~~~

Ví dụ biểu mẫu độc hại minh họa ý tưởng:

~~~html
<form action="https://bank.example.invalid/transfer" method="post">
  <input name="recipient" value="attacker-account">
  <input name="amount" value="100">
  <button type="submit">Click to view photo</button>
</form>
~~~

Đây là **ví dụ giải thích mối đe dọa**, không phải URL ngân hàng thật. Kẻ tấn công không nhất thiết phải đọc được response. Nếu request có credential hợp lệ được browser tự đính kèm và server chỉ xác minh “Alice đã đăng nhập” mà không kiểm tra tính chủ động của Alice đối với thao tác, server có thể thực hiện hành động ngoài ý muốn.

**Authentication đúng không đồng nghĩa request hợp lệ theo ý muốn người dùng.** Chính vì trình duyệt hỗ trợ cookie, HTTP Basic hoặc một số cơ chế tự gửi credential, server cần một tín hiệu bổ sung mà trang của kẻ tấn công không thể tự tạo.

## 3. Cơ chế phòng vệ: synchronizer CSRF token

Spring Security áp dụng CSRF protection cho các thao tác cần bảo vệ. Mô hình synchronizer token:

1. Server tạo token ngẫu nhiên khó đoán, gắn nó với ngữ cảnh phù hợp của người dùng, ví dụ `HttpSession`.
2. Trang hợp lệ hoặc JavaScript client nhận token bằng kênh mà trang khác không thể tự ý tạo/cung cấp theo cùng điều kiện.
3. Khi gửi request làm thay đổi trạng thái, client gửi token trong **tham số form** hoặc **HTTP header**.
4. Server so sánh token nhận được với token dự kiến. Thiếu/sai token → request bị từ chối.

~~~text
CÙNG MỘT COOKIE SESSION

Request A:
  Cookie: JSESSIONID=...
  Header/form: _csrf=<correct-token>
    => Có thể đi qua CSRF check (vẫn phải kiểm tra quyền)

Request B:
  Cookie: JSESSIONID=...
  Không có CSRF token hoặc token sai
    => Bị từ chối trước khi chạy nghiệp vụ
~~~

**Quan trọng:** Nếu hệ thống chỉ yêu cầu “CSRF token có trong cookie”, yêu cầu này không giúp gì vì browser cũng tự gửi cookie trong một số tình huống cross-site. Cần **client đưa giá trị token ra tham số/header** theo quy tắc mà trang của attacker không thể tùy ý cung cấp.

### Spring Security Servlet xử lý những gì?

- `CsrfFilter` xác định request có cần kiểm tra CSRF không và đối chiếu token.
- `CsrfTokenRepository` lưu/tải token dự kiến. Trong cấu hình Servlet mặc định thường dùng `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` đưa token tới request và giải quyết token từ header/form parameter.
- `XorCsrfTokenRequestAttributeHandler` là handler mặc định ở Spring Security 6, hỗ trợ bảo vệ BREACH qua token representation được mask.
- Khi token thiếu hoặc sai, request có thể bị từ chối bởi `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException` và thường cho response `403`.

Đừng tự suy diễn rằng một HTTP `403` chắc chắn do CSRF. Nó cũng có thể đến từ rule authorization, method security hoặc một handler riêng. Cần xác định tầng từ chối trước khi sửa cấu hình.

## 4. Những HTTP method nào cần CSRF?

Theo mô hình mặc định, Spring Security bỏ qua CSRF check cho các **safe methods**:

- `GET`
- `HEAD`
- `OPTIONS`
- `TRACE`

Và mặc định kiểm tra các method khác, bao gồm `POST`, `PUT`, `PATCH` và `DELETE`.

| Request | Mặc định cần CSRF token? | Điều kiện nền tảng |
| --- | --- | --- |
| `GET /products` | Không | GET phải không tạo side effect nghiệp vụ |
| `HEAD /products` | Không | Đọc-only, không mutate state |
| `OPTIONS /products` | Không | Thăm dò khả năng endpoint, không ghi dữ liệu |
| `POST /transfer` | Có | Trình duyệt dùng cookie/session |
| `PUT /account/profile` | Có | Có thể sửa thông tin |
| `PATCH /account/settings` | Có | Có thể sửa cấu hình |
| `DELETE /account/saved-card` | Có | Có thể xóa dữ liệu |

**Không được đặt thao tác ghi trong GET rồi nói đã an toàn vì Spring không yêu cầu CSRF cho GET.** Cấu hình CSRF dựa trên giả định các safe methods thật sự read-only. Ví dụ `GET /delete-account?id=42` là sai về HTTP semantics và làm hỏng tiền đề bảo vệ.

### Login và logout cũng là thao tác có tác động trạng thái

Một form login thường thay đổi trạng thái xác thực và có thể tạo session mới. Một request logout làm mất phiên. Spring Security hỗ trợ CSRF cho `POST /login` và `POST /logout` khi CSRF bật; `GET /logout` có thể hiển thị trang xác nhận giúp gửi POST có CSRF token.

Đừng tắt CSRF “để nút logout khỏi bị 403” hoặc chuyển logout thành GET tùy tiện. Sửa form để gửi token đúng cách.

## 5. Tại sao không nên tắt CSRF theo thói quen?

Đoạn sau là một thay đổi **rộng**:

~~~java
// CẨN TRỌNG: tắt kiểm tra CSRF cho TOÀN BỘ SecurityFilterChain.
http.csrf(csrf -> csrf.disable());
~~~

Nó có thể làm request `POST` vốn thiếu token được phép đi tiếp. Nếu ứng dụng sử dụng cookie/session hoặc một credential khác mà browser tự gửi, một lớp bảo vệ quan trọng đã bị loại bỏ.

Những câu “nghe hợp lý nhưng sai”:

| Lập luận | Vấn đề |
| --- | --- |
| “API trả JSON nên không cần CSRF” | Response JSON không quyết định credential có được browser tự gửi hay không |
| “Dùng REST controller nên không có CSRF” | `@RestController` vẫn có thể nhận session cookie hoặc HTTP Basic |
| “Đã có authentication, kẻ lạ không đăng nhập được” | CSRF mượn chính browser của user đã đăng nhập |
| “Đã có role check nên an toàn” | Request bị giả mạo có thể mang role thật của nạn nhân |
| “Đã bật CORS nên đủ” | CORS chủ yếu kiểm soát đọc response/các cross-origin request nhất định, không thay CSRF token cho form request |
| “Đã có SameSite nên chắc chắn an toàn” | SameSite là lớp bổ trợ với giới hạn theo site, browser và nhu cầu tích hợp |
| “Dùng HTTPS nên không bị CSRF” | HTTPS bảo vệ đường truyền, không xác nhận user chủ động gửi hành động |
| “Test POST bị 403 thật bất tiện” | Cần sửa test gửi CSRF token hoặc chỉ định ngoại lệ đã được đánh giá |
| “Chỉ cần `permitAll()`” | Quyền truy cập endpoint và CSRF là hai kiểm tra độc lập |
| “API stateless nên luôn tắt CSRF” | Stateless chưa đủ nếu browser vẫn tự gửi credential hợp lệ, ví dụ HTTP Basic hoặc cookie |

**Câu hỏi quyết định không phải “Có phải REST hay không?” mà là “Một trang độc hại có thể làm trình duyệt gửi yêu cầu đã được xác thực mà không cần biết credential không?”**

## 6. Khi nào có thể cân nhắc ngoại lệ?

Không có quy tắc “hễ endpoint là webhook/API thì tắt CSRF”. Hãy phân tích **request origin, credential, browser behavior và biện pháp xác thực thay thế**.

### 6.1. Webhook server-to-server đã có xác thực mạnh

Một nhà cung cấp thanh toán gửi `POST /webhooks/provider` trực tiếp từ server của họ. Request không xuất phát từ browser đăng nhập bằng session cookie; client không có CSRF token của người dùng.

Trong mô hình này có thể hợp lý để **miễn CSRF cho đúng endpoint POST** và thay bằng cơ chế xác minh phù hợp như HMAC signature của raw payload, timestamp/chống replay, idempotency, rate limiting và kiểm tra event provider.

~~~text
Provider Server
    |
    | POST /webhooks/provider
    | X-Webhook-Signature: sha256=...
    v
Spring Boot
    |
    +-- Bỏ yêu cầu CSRF riêng cho POST /webhooks/provider
    |
    +-- XÁC MINH chữ ký provider và replay policy
            |
            +-- sai -> DENY
            +-- đúng -> xử lý theo policy
~~~

**Miễn CSRF không đồng nghĩa bỏ authentication/authorization.** Vì CSRF không giải quyết xác thực server-to-server, webhook cần biện pháp riêng. Không coi header tĩnh kiểu `X-Webhook: true` là bằng chứng xác thực đáng tin.

### 6.2. API machine-to-machine chỉ nhận bearer token qua HTTP Authorization header

Một resource server chỉ nhận:

~~~http
POST /machine/jobs HTTP/1.1
Host: api.example.invalid
Authorization: Bearer <access-token>
Content-Type: application/json

{"name":"job1"}
~~~

Nếu endpoint **thật sự không** chấp nhận session cookie/Basic authentication/cơ chế tự gửi credential và client chủ động đặt bearer token trong header, browser của một trang lạ không tự biết/token không tự gửi trong request như cookie.

Khi đó có thể cân nhắc không dùng CSRF token cho **đúng security chain phục vụ machine clients**. Nhưng vẫn phải kiểm tra:

- Chain đó có thật sự chỉ dùng bearer token?
- Session creation có bị vô hiệu hóa phù hợp?
- Có cookie-based fallback, proxy auto-auth, client certificate, HTTP Basic hoặc endpoint web nào dùng chung chain không?
- CORS policy có chặn site không tin cậy trong các luồng cần thiết?
- Access token có issuer, audience, expiry, scopes và policy phù hợp không?

**Token JWT được lưu trong cookie vẫn có nguy cơ CSRF**, vì browser gửi cookie tự động. Không suy luận “JWT” = “không CSRF”.

### 6.3. Native mobile/CLI không dùng browser cookie

Một API chỉ phục vụ mobile native hoặc CLI mà credential được client tự gắn vào header có thể không cần synchronizer CSRF token. Nhưng nếu **cùng backend** vẫn nhận browser traffic sử dụng cookie, không nên tắt CSRF trên toàn bộ backend chỉ vì một client mobile cần gọi POST.

Có thể thiết kế một đường xác thực riêng, chain riêng hoặc cơ chế lấy token CSRF cho browser để giữ đúng từng trust boundary.

### 6.4. Endpoint nhận sự kiện nội bộ có xác thực độc lập

Các đường gọi scheduler nội bộ, message-delivery callback hoặc health agent **không dựa credential browser** có thể cân nhắc ngoại lệ theo method/path, nếu chúng có authentication riêng thích hợp (mTLS, chữ ký, OAuth2 client credentials, network restrictions như lớp bổ trợ).

Chỉ vì endpoint “internal” hoặc “không có UI” chưa đủ. Nếu browser có thể gọi nó kèm cookie user hoặc mạng nội bộ bị truy cập từ một origin không tin cậy, phải đánh giá lại nguy cơ.

## 7. Hướng dẫn ra quyết định: loại nào bảo vệ, loại nào xét ngoại lệ?

| Loại request | Credential và môi trường | Khuyến nghị ban đầu |
| --- | --- | --- |
| Web MVC/Thymeleaf form POST | Session cookie | **Giữ CSRF** |
| SPA gửi cookie phiên | Cookie tự gắn | **Giữ CSRF**, tích hợp token qua header |
| REST API dùng session cookie | Cookie tự gắn | **Giữ CSRF** dù body JSON |
| REST API JWT lưu trong cookie | Cookie tự gắn | **Giữ CSRF** hoặc thiết kế lớp bảo vệ tương đương đã kiểm chứng |
| API chỉ bearer token trong `Authorization` header | Không có credential auto-sent | Có thể cân nhắc miễn, nếu chain/endpoint thật sự stateless |
| Webhook từ server đối tác | HMAC/mTLS/token server-to-server, không dùng cookie user | Có thể miễn đúng method/path và xác minh chữ ký |
| API HTTP Basic cho browser | Browser có thể tự gửi credential | **Không tự động miễn CSRF** |
| URL `permitAll()` nhưng làm thay đổi trạng thái | Có thể có cookie/credential auto-sent | **Không tự động miễn CSRF** |
| CORS preflight `OPTIONS` | Safe method | Mặc định không cần CSRF token; cấu hình CORS riêng |
| GET có side effect | Semantics HTTP sai | Sửa API thành unsafe method và bảo vệ phù hợp |

**Nếu không biết chắc cơ chế gửi credential**, mặc định giữ CSRF và khảo sát. Ngoại lệ là một quyết định thiết kế có trách nhiệm, không phải cách làm cho test “xanh” nhanh chóng.

## 8. Ngoại lệ có phạm vi hẹp: `ignoringRequestMatchers`

Với Spring Security 6 Servlet, có thể cấu hình:

~~~java
// Chỉ là đoạn minh họa trong SecurityFilterChain.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        new AntPathRequestMatcher("/webhooks/provider", "POST")
    )
);
~~~

Như vậy **chỉ** `POST /webhooks/provider` được miễn CSRF bởi matcher này; các tuyến POST khác vẫn cần token. `AntPathRequestMatcher` có trong Spring Security 6.x của ví dụ; các phiên bản mới hơn có thể ưu tiên matcher API khác, nên xem documentation tương ứng với phiên bản thực tế.

Đừng viết:

~~~java
// QUÁ RỘNG nếu /api/** có endpoint browser/session.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/**")
);
~~~

khi không có bằng chứng rằng mọi route trong `/api/**` đều không dùng browser auto-credentials. URL pattern càng rộng, càng dễ vô tình mở ngoại lệ cho endpoint mới mà người khác thêm sau này.

### `permitAll` khác `CSRF ignore`

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/webhooks/provider").permitAll()
)
.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        new AntPathRequestMatcher("/webhooks/provider", "POST")
    )
)
~~~

- `permitAll` nói rằng request **không cần principal đã đăng nhập** ở tầng authorization của Spring Security.
- `ignoringRequestMatchers` nói rằng request **không cần CSRF token**.
- Chúng **không tự tạo** một kiểm tra chữ ký webhook. Cần riêng một HMAC/mTLS/OAuth2 policy hợp lệ.

Ngược lại, một URL `/register` công khai có `permitAll` nhưng nhận POST từ browser vẫn có thể cần CSRF để ngăn thao tác giả mạo.

## 9. Ví dụ Java 17 chạy được: giữ CSRF cho trình duyệt, miễn POST webhook có chữ ký

Ví dụ dưới đây dùng:

- Java 17+.
- Spring Boot 3.3.5 / Spring Security 6.x.
- Gradle 8.x.
- Một endpoint `POST /settings` được bảo vệ bằng authentication **và CSRF**.
- Một endpoint `POST /webhooks/vendor` được miễn CSRF **riêng** nhưng kiểm tra HMAC SHA-256 trên raw request body.
- MockMvc tests xác minh request thiếu token bị từ chối, token hợp lệ được chấp nhận, ngoại lệ webhook chỉ hoạt động khi có chữ ký hợp lệ.

**Mục đích học tập:** HMAC trong ví dụ kiểm tra authenticity/integrity cơ bản của payload. Production webhook phải theo **đúng cách ký của provider**, thêm timestamp/replay window, idempotency, secret rotation và error handling. Một chữ ký hợp lệ có thể bị phát lại nếu thiếu anti-replay.

### 9.1. Cấu trúc project

~~~text
csrf-exception-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── SettingsController.java
    │   ├── WebhookVerifier.java
    │   └── WebhookController.java
    ├── main/resources/
    │   └── application.properties
    └── test/java/demo/csrf/
        └── CsrfPolicyTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'csrf-exception-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Khởi động ứng dụng

File `src/main/java/demo/csrf/CsrfDemoApplication.java`:

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityFilterChain: mặc định bảo vệ, chỉ miễn đúng POST webhook

File `src/main/java/demo/csrf/SecurityConfig.java`:

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(
                    HttpMethod.POST, "/webhooks/vendor"
                ).permitAll()
                .anyRequest().authenticated()
            )
            // CSRF vẫn BẬT ở mọi request khác.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                new AntPathRequestMatcher("/webhooks/vendor", "POST")
            ))
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
}
~~~

**Điểm then chốt:** Không hề có `csrf.disable()`. Default CSRF protection vẫn tồn tại. Matcher ghi rõ method `POST` và path cụ thể, không phải mọi URL bắt đầu bằng `/webhooks/`.

`formLogin` được giữ để ví dụ có một web-style authenticated flow. Trong tests, `@WithMockUser` đặt principal để tập trung kiểm tra CSRF mà không cần thao tác UI login.

### 9.4. Endpoint có tác dụng phụ được CSRF bảo vệ

File `src/main/java/demo/csrf/SettingsController.java`:

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SettingsController {

    private final AtomicInteger updates = new AtomicInteger();

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @PostMapping("/settings")
    public String update() {
        updates.incrementAndGet();
        return "updated";
    }

    public int updateCount() {
        return updates.get();
    }

    public void resetForTest() {
        updates.set(0);
    }
}
~~~

`AtomicInteger` là trạng thái mẫu, không phải database. Ta sẽ test rằng request thiếu/sai CSRF token **không vào được thân `update()`**; nó không được tăng. Nếu một request có token hợp lệ và đã authenticated, method có thể chạy và count tăng.

### 9.5. Kiểm tra chữ ký cho webhook

File `src/main/java/demo/csrf/WebhookVerifier.java`:

~~~java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WebhookVerifier {

    private final byte[] key;

    public WebhookVerifier(@Value("${demo.webhook.secret}") String secret) {
        this.key = secret.getBytes(StandardCharsets.UTF_8);
    }

    public boolean isValid(byte[] payload, String signatureHeader) {
        if (signatureHeader == null
                || !signatureHeader.startsWith("sha256=")) {
            return false;
        }

        String hex = signatureHeader.substring("sha256=".length());
        if (!hex.matches("[0-9a-fA-F]{64}")) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));

            byte[] expected = mac.doFinal(payload);
            byte[] provided = HexFormat.of().parseHex(hex);

            return MessageDigest.isEqual(expected, provided);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC is unavailable", e);
        }
    }
}
~~~

Điểm đáng chú ý:

- HMAC tính trên **raw request bytes**; không deserialize JSON rồi serialize lại trước khi xác minh vì có thể thay đổi canonical payload.
- `MessageDigest.isEqual` dùng để so sánh bytes tránh kiểu so sánh tuần tự quá đơn giản dễ rò rỉ thời gian.
- Mã kiểm tra định dạng chữ ký trước khi parse, từ chối header sai.
- Không đặt secret ngoài production dưới dạng literal trong source; ví dụ dùng secret local để test, production cần environment/secret manager.
- Code mẫu **chưa** chống replay. Phải thêm timestamp, giới hạn thời gian, event ID/idempotency và quy tắc ký chính xác của nhà cung cấp trước khi dùng cho giao dịch thật.

File `src/main/java/demo/csrf/WebhookController.java`:

~~~java
package demo.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WebhookController {

    private final WebhookVerifier verifier;

    public WebhookController(WebhookVerifier verifier) {
        this.verifier = verifier;
    }

    @PostMapping("/webhooks/vendor")
    public ResponseEntity<String> receive(
            @RequestBody byte[] payload,
            @RequestHeader(
                value = "X-Webhook-Signature", required = false
            ) String signature) {
        if (!verifier.isValid(payload, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("invalid signature");
        }

        return ResponseEntity.accepted().body("accepted");
    }
}
~~~

Cấu hình application cho **demo local**:

File `src/main/resources/application.properties`:

~~~properties
server.port=8080
demo.webhook.secret=local-demo-secret-change-before-production
~~~

Đây không phải production secret. Ở môi trường thật, hãy cấu hình giá trị từ secret store hoặc environment, ví dụ `demo.webhook.secret=${WEBHOOK_SECRET}`; bảo đảm không log raw secret.

### 9.6. MockMvc test toàn bộ ranh giới

File `src/test/java/demo/csrf/CsrfPolicyTest.java`:

~~~java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfPolicyTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SettingsController settings;

    @BeforeEach
    void resetCount() {
        settings.resetForTest();
    }

    @Test
    void getHealthIsSafeAndPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfCannotUpdate() throws Exception {
        mvc.perform(post("/settings"))
            .andExpect(status().isForbidden());

        assertEquals(0, settings.updateCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void invalidCsrfCannotUpdate() throws Exception {
        mvc.perform(post("/settings")
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertEquals(0, settings.updateCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void validCsrfCanUpdate() throws Exception {
        mvc.perform(post("/settings").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));

        assertEquals(1, settings.updateCount());
    }

    @Test
    void signedWebhookIsAcceptedWithoutCsrf() throws Exception {
        String body = "{\"event\":\"created\"}";
        String signature = sign(body);

        mvc.perform(post("/webhooks/vendor")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body)
                .header("X-Webhook-Signature", signature))
            .andExpect(status().isAccepted())
            .andExpect(content().string("accepted"));
    }

    @Test
    void unsignedWebhookIsRejectedWithoutCsrf() throws Exception {
        mvc.perform(post("/webhooks/vendor")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"event\":\"forged\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("invalid signature"));
    }

    @Test
    void otherPostEndpointStillRequiresCsrf() throws Exception {
        // Không có controller tại /webhooks/other;
        // CsrfFilter chặn POST thiếu token trước khi đến MVC.
        mvc.perform(post("/webhooks/other"))
            .andExpect(status().isForbidden());
    }

    private static String sign(String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
            "local-demo-secret-change-before-production"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256"
        ));
        byte[] digest = mac.doFinal(
            body.getBytes(StandardCharsets.UTF_8)
        );
        return "sha256=" + HexFormat.of().formatHex(digest);
    }
}
~~~

Chạy từ root project với JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

**Kết quả mong đợi:** cả **7 test pass**, với cấu hình ví dụ và dependencies đã khai báo. Đây là kỳ vọng từ mã nguồn, **không phải kết quả chạy được ghi nhận trong bài**.

### 9.7. Bảng kết quả và ý nghĩa

| Test | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| `GET /health` | Anonymous | `200 OK` |
| `POST /settings` | Alice, **không CSRF token** | `403 Forbidden`, counter 0 |
| `POST /settings` | Alice, **token sai** | `403 Forbidden`, counter 0 |
| `POST /settings` | Alice, **token đúng** | `200 OK`, counter 1 |
| `POST /webhooks/vendor` | Không CSRF, HMAC đúng | `202 Accepted` |
| `POST /webhooks/vendor` | Không CSRF, HMAC thiếu | `401 Unauthorized` |
| `POST /webhooks/other` | Không CSRF | `403 Forbidden` trước MVC |

Hai bài test đầu của nhóm `/settings` dùng `@WithMockUser` để cô lập CSRF khỏi login flow: **đã có user authenticated nhưng thiếu CSRF vẫn bị chặn**. Test webhook chứng minh một ngoại lệ hợp lý có cơ chế kiểm tra riêng. Test path khác chứng minh ngoại lệ không mở rộng toàn bộ `/webhooks/**`.

Nếu bỏ `.csrf(csrf -> csrf.ignoringRequestMatchers(...))`, webhook POST không có token sẽ bị CSRF filter chặn trước khi HMAC controller chạy. Nếu thay bằng `csrf.disable()`, các tests thiếu token của `/settings` sẽ không còn chứng minh lớp CSRF đang hoạt động.

### 9.8. Điều gì phải thêm trước production?

Demo chỉ minh họa authentication-by-HMAC cơ bản. Một webhook production thường phải có thêm:

1. Signature scheme **chính thức** của provider (định dạng header, thuật toán, canonical raw body).
2. Timestamp được ký và cửa sổ thời gian ngắn để chống phát lại; không chỉ kiểm tra HMAC payload.
3. Event ID hoặc idempotency key được lưu an toàn để request lặp không xử lý nghiệp vụ nhiều lần.
4. Secret rotation, không hardcode secret, phân quyền mạng phù hợp.
5. Giới hạn kích thước request, rate limit, kiểm tra schema và chính sách event type.
6. Không ghi full payload, secret hoặc raw signature vào log công khai.
7. Tách lối đi lỗi xác thực và lỗi xử lý nghiệp vụ, có audit/correlation ID.

Đừng copy HMAC demo thành production verifier cho Stripe/GitHub hoặc provider cụ thể mà chưa làm theo protocol ký của họ.

## 10. Một API hoàn toàn stateless có thể tách thành chain riêng

Nếu hệ thống có web UI dùng cookie **và** API machine-to-machine chỉ dùng bearer token, có thể thiết kế hai `SecurityFilterChain` với scope riêng. Ví dụ dưới đây là **đoạn định hướng tích hợp**, không phải application chạy độc lập (cần dependency OAuth2 Resource Server, JWT decoder, issuer trust và cấu hình token thực):

~~~java
// MINH HỌA: chain chỉ áp dụng /machine/**,
// xác thực OAuth2 JWT trong Authorization header.
// Chỉ cân nhắc disable CSRF nếu chain KHÔNG dùng cookie/auto-credentials.

@Bean
@Order(1)
SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/machine/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .csrf(csrf -> csrf.disable())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        // Không disable CSRF ở chain browser.
        .build();
}
~~~

Các import tương ứng gồm `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity`, `SessionCreationPolicy` và `Customizer`. Một ứng dụng tích hợp phải loại bỏ chain trùng và kiểm thử thứ tự `@Order`.

**Đừng áp dụng mẫu này nếu `/machine/**` vẫn chấp nhận browser cookies, Basic auth hoặc auto-sent credentials.** `STATELESS` chỉ nói về chiến lược session trong Spring Security; nó **không tự biến mọi cơ chế authentication thành CSRF-safe**.

Lợi ích của chain riêng là không để một thay đổi bảo mật của machine APIs vô tình làm mất CSRF protection ở UI. Nếu chỉ có một webhook cần ngoại lệ, `ignoringRequestMatchers` như phần 9 thường đơn giản và an toàn hơn.

## 11. SPA sử dụng cookie: sửa cách gửi token, không vội tắt CSRF

Một Single-Page Application thường gửi JSON thông qua `fetch`/Axios. Nếu user identity vẫn được duy trì bởi session cookie, browser có thể tự gắn cookie vào những request phù hợp. **SPA không tự miễn nhiễm với CSRF** chỉ vì không dùng HTML form truyền thống.

Hướng tiếp cận:

1. Server tạo/lưu CSRF token.
2. Frontend nhận token qua meta tag, response header hoặc cookie `XSRF-TOKEN` theo cấu hình.
3. Frontend gắn token vào header như `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` cho request POST/PUT/PATCH/DELETE.
4. Server kiểm tra token so với giá trị dự kiến.
5. Sau login/logout hoặc thay đổi session CSRF state, frontend lấy token mới khi cần.

Spring Security cung cấp `CookieCsrfTokenRepository`. Mặc định cookie tên `XSRF-TOKEN` và header tương ứng `X-XSRF-TOKEN`, nhưng cần biết **chỉ browser gửi cookie chưa đủ**; JavaScript client phải gửi token ở header. Trong một số SPA, `withHttpOnlyFalse()` cho phép JavaScript đọc CSRF token cookie, nhưng giảm bảo vệ của cookie đó trước JavaScript và cần cân nhắc XSS.

**Chi tiết Spring Security 6:** handler mặc định có BREACH masking (`XorCsrfTokenRequestAttributeHandler`) và deferred token loading. Khi SPA lấy raw token từ cookie và gửi trong header, cách resolve token cần được cấu hình cho đúng raw/masked value. Token cũ cũng bị dọn sau authentication/logout nên client phải lấy token mới. Hãy sử dụng hướng dẫn chính thức dành cho đúng Spring Security version thay vì copy một snippet cũ hoặc vô hiệu hóa BREACH bảo vệ mà không hiểu hệ quả.

Để đơn giản cho SSR với Thymeleaf, nhiều form được template engine tích hợp CSRF token tự động. Nếu POST thiếu token, kiểm tra HTML rendered form và request payload trước khi chỉnh security config.

## 12. CORS, SameSite, Fetch Metadata và Origin có thay CSRF được không?

### CORS

CORS điều chỉnh những cross-origin requests mà browser cho phép và việc trang ngoài có thể đọc responses. Một HTML form cross-site với kiểu content type phù hợp có thể **được gửi** dù attacker không đọc được response. Do đó, “CORS không cho đọc kết quả” **không** đảm bảo request không tạo side effect.

CORS là kiểm soát origin quan trọng khi UI và API ở các origin khác nhau, nhưng không được dùng như khẩu hiệu thay thế CSRF token cho mọi ứng dụng cookie-based.

### SameSite cookie

`SameSite=Lax` hoặc `Strict` có thể giảm một số kiểu cross-site cookie sending. Tuy nhiên:

- **Site** và **origin** không giống nhau; nhiều subdomain có thể cùng site nhưng khác origin.
- Ứng dụng có thể cần cross-site flows, iframe hoặc tích hợp bên thứ ba.
- Hành vi browser/compatibility và cách cookie được cấu hình ảnh hưởng kết quả.
- Cần kiểm tra các request nguy hiểm trong hệ thống thật, không suy luận rằng một giá trị SameSite chắc chắn thay thế CSRF token.

SameSite nên được xem là **defense in depth**. Kết hợp với `Secure`, `HttpOnly`, TLS và CSRF token theo mô hình browser session.

### Fetch Metadata và Origin/Referer

Kiểm tra `Sec-Fetch-Site`, `Origin` hoặc `Referer` có thể tăng khả năng chặn cross-site requests không đáng tin, nhưng cần cân nhắc header không hiện diện, proxy, redirect, privacy policies và legitimate integrations. Một cơ chế thêm không có nghĩa xóa token CSRF mặc định là an toàn. Nếu thiết kế dùng origin checks thay cho token ở một số endpoint, cần threat model, compatibility và tests thực tế.

### XSS

XSS khác CSRF: XSS cho phép mã độc chạy trong origin được tin cậy, thậm chí có thể đọc CSRF token mà JavaScript được phép tiếp cận. Vì vậy CSRF token **không thay thế** phòng vệ XSS như output encoding, CSP và kiểm soát các script không đáng tin.

## 13. Những trường hợp dễ nhầm khác

### `permitAll` và POST đăng ký tài khoản

~~~java
.requestMatchers(HttpMethod.POST, "/register").permitAll()
~~~

Rule trên không yêu cầu user đã đăng nhập, nhưng POST vẫn có thể là thao tác thay đổi trạng thái do browser gửi. Khi request cần CSRF protection, `permitAll` không làm mất yêu cầu token. Tùy threat model có thể bổ sung rate limit, chống spam, email verification — những cơ chế này cũng không đồng nghĩa với CSRF.

### JSON content type

Request JSON cần custom header hoặc content type không đủ để kết luận CSRF vô nghĩa. Xem toàn bộ entry points, accepted content types, CORS và credential behavior, không chỉ kiểu DTO của controller.

### File upload/multipart

Với multipart browser form, việc lấy CSRF token qua header có thể giúp tránh phân tích multipart body trước khi CSRF validation. Nếu đặt token trong body hoặc query string, phải đánh giá side effects của file parsing và nguy cơ lộ token qua URL/logs. Tránh đưa CSRF token lên query string nếu có giải pháp form/header phù hợp.

### Session timeout

Nếu `HttpSessionCsrfTokenRepository` lưu token trong session mà session hết hạn, POST form cũ có thể trả 403 do token không còn khớp. Xử lý bằng UX refresh/lấy token mới, hướng dẫn người dùng đăng nhập lại hoặc access-denied handling phù hợp. Đừng “sửa” lỗi timeout bằng cách tắt toàn bộ CSRF.

### CSRF token “không thấy” vì deferred loading

Spring Security 6 có thể trì hoãn tải/generate token cho tới khi cần. Nếu SPA phụ thuộc cookie token, phải bảo đảm token được khởi tạo/trả đúng thời điểm. Đây là vấn đề tích hợp, không chứng minh nên disable CSRF.

## 14. Debug HTTP 403 theo từng bước

Khi POST trả `403`:

1. **Xác nhận URL, method và SecurityFilterChain** áp dụng, tránh kiểm tra nhầm chain.
2. **Xác nhận authentication:** user có session cookie hay bearer token? Credential tự động được gửi hay client chủ động tạo header?
3. **Xem request có CSRF token không:** form field `_csrf` hoặc header `X-CSRF-TOKEN`/`X-XSRF-TOKEN` theo config.
4. **Kiểm tra token có khớp session không:** cookie/session có hết hạn, đổi ID, login/logout làm token cũ bị invalidated hay không?
5. **Kiểm tra frontend/SPA handler:** đang gửi raw hay masked token? Có lấy token mới sau login/logout chưa?
6. **Kiểm tra matcher ngoại lệ:** có đúng HTTP method và path không, có match ngoài dự kiến không?
7. **Kiểm tra endpoint có thực sự cần miễn CSRF:** request là webhook server-to-server thật hay browser vẫn có thể tự gửi cookie?
8. **Kiểm tra authorization và method security:** nếu CSRF pass mà vẫn 403, có thể do thiếu authority/role hoặc policy tầng service.
9. **Kiểm tra test cases:** MockMvc test phải thêm `with(csrf())` cho unsafe requests được kỳ vọng thành công khi CSRF bật.
10. **Không log secret/token thô:** nếu bật DEBUG cho security, chỉ dùng môi trường kiểm soát và redact session/CSRF/bearer credentials.

Một thao tác tốt để tìm lỗi tích hợp là so sánh hai requests cùng endpoint, cùng authenticated principal: request A thiếu token bị chặn, request B có token hợp lệ được xử lý. Sự khác nhau này cho thấy CSRF filter đang hoạt động, không phải lý do để tắt nó.

## 15. Checklist duyệt yêu cầu “tắt CSRF”

Trước khi chấp nhận một thay đổi:

- [ ] Đã viết rõ **threat model** của endpoint, biết browser có thể gửi credential tự động hay không.
- [ ] Không có UI/Browser flow sử dụng session cookie hoặc Basic/mTLS tự động trong phạm vi ngoại lệ.
- [ ] Đã kiểm tra method/path chính xác; không miễn `/api/**` nếu tồn tại endpoint session-based trong vùng đó.
- [ ] Nếu là webhook, có signature authentication theo đúng provider, timestamp/replay policy, idempotency và limit.
- [ ] Nếu là bearer-only API, đã cô lập security chain và bảo đảm không có cookie fallback.
- [ ] `permitAll` không được dùng như lời biện hộ rằng CSRF không cần.
- [ ] Login/logout, thay đổi hồ sơ, tiền và quyền vẫn được CSRF bảo vệ nếu là browser session flow.
- [ ] Đã thử CSRF token thiếu, sai, hợp lệ; cùng kiểm tra state **không thay đổi** khi bị từ chối.
- [ ] Đã thử scope ngoại lệ không lan sang endpoint khác.
- [ ] Đã kiểm tra CORS, SameSite, cookie attributes và CSRF frontend integration theo phiên bản Spring Security.
- [ ] Có tài liệu giải thích lý do ngoại lệ, owner review và regression test để người sau không vô tình mở rộng.
- [ ] Không tắt CSRF vì muốn làm một test nhanh hết 403.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một `@RestController` nhận POST và xác thực bằng session cookie. Có thể tắt CSRF vì nó trả JSON không?

**Đáp án:** Không. JSON không quyết định trình duyệt có tự gửi cookie hay không. Nếu một cross-site request có thể dùng session người dùng, vẫn cần bảo vệ CSRF phù hợp.

**Câu 2.** Webhook từ server đối tác không có browser session. Khi nào hợp lý để miễn CSRF?

**Đáp án:** Khi endpoint được giới hạn rõ ràng và dùng cơ chế xác thực độc lập đúng chuẩn (ví dụ HMAC signature, timestamp/anti-replay, idempotency); chỉ miễn đúng method/path cần thiết.

**Câu 3.** `permitAll()` cho `POST /register` có đồng nghĩa CSRF bị bỏ qua không?

**Đáp án:** Không. Request authorization và CSRF filter là các tầng khác nhau.

**Câu 4.** Nếu API dùng JWT nhưng JWT được đặt trong cookie, có thể chắc chắn miễn CSRF không?

**Đáp án:** Không. Browser có thể tự gửi cookie, kể cả cookie chứa JWT. Phải đánh giá credential behavior và biện pháp chống CSRF tương ứng.

**Câu 5.** `@WithMockUser` + POST trong MockMvc vẫn bị 403. Vì sao?

**Đáp án:** Test đã giả lập authentication nhưng chưa cung cấp CSRF token. Dùng `with(csrf())` cho request được phép, và thêm test thiếu token để kiểm tra bảo vệ.

**Câu 6.** Vì sao HMAC webhook trong demo chưa đầy đủ cho production?

**Đáp án:** Vì một chữ ký hợp lệ có thể bị phát lại nếu thiếu timestamp/replay window và idempotency. Cần tuân thủ signature protocol chính thức của provider và quản lý secret an toàn.

**Câu 7.** Nếu site dùng SameSite=Lax rồi, có thể xóa hết CSRF checks?

**Đáp án:** Không mặc định. SameSite bảo vệ một số cross-site contexts nhưng không thay threat assessment, không giải quyết hoàn toàn các tình huống same-site khác origin và các tích hợp đặc biệt.

## 17. Kết luận và tài liệu tham khảo

**Đừng tắt CSRF theo thói quen.** Đầu tiên hãy xác định request có dùng credential mà browser tự gắn hay không. Web app/session cookie và SPA cookie-based nên giữ CSRF. Webhook server-to-server có xác thực chữ ký hoặc API bearer-only thật sự stateless có thể xem xét ngoại lệ — nhưng cần **phạm vi nhỏ nhất**, bảo vệ độc lập, test cả nhánh thiếu token và khả năng ngoại lệ không lan sang nơi khác.

**Một ngoại lệ đúng là quyết định từ threat model và kiểm thử, không phải một cách bỏ qua lỗi 403.**

Tài liệu Spring Security chính thức:

- [Spring Security — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF Threat Model](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Servlet Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
