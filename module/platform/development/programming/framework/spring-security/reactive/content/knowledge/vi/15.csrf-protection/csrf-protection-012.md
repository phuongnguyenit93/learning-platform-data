# Giới hạn phạm vi bỏ qua CSRF bằng matcher và kiểm chứng bằng kiểm thử

## 1. Vấn đề cần giải quyết

Trong Spring Security reactive (Spring WebFlux), bảo vệ CSRF thường được bật mặc định cho các HTTP request có khả năng thay đổi trạng thái. Một ứng dụng dùng session cookie hoặc HTTP Basic trong trình duyệt có thể cần CSRF token cho POST, PUT, PATCH và DELETE. Đồng thời, cùng ứng dụng đôi khi phải nhận webhook của nhà cung cấp dịch vụ khác, không dùng cookie phiên của người dùng và thay vào đó xác minh chữ ký HMAC trên raw request body.

Ví dụ có hai request:

~~~text
POST /api/notes
  Trình duyệt của người đã đăng nhập
  Browser có thể tự gửi session cookie / Basic credentials
  → Phải giữ CSRF token và authentication.

POST /integrations/webhook/receive
  Server của đối tác gửi webhook
  Không dùng cookie phiên user
  Có chữ ký HMAC riêng và replay policy
  → Có cơ sở miễn CSRF nếu phạm vi được giới hạn chính xác.
~~~

**Sai lầm nguy hiểm** là tắt CSRF trên toàn bộ security chain chỉ vì webhook bị 403:

~~~java
// PHẢN VÍ DỤ. Không sao chép vào ứng dụng có browser session!
http.csrf(csrf -> csrf.disable());
~~~

Lệnh trên làm mất CSRF protection cho cả login/logout, form và API dùng ambient credentials trong cùng chain. Cách làm đúng là thiết kế một matcher theo điều kiện:

~~~text
CSRF_REQUIRED = UNSAFE_HTTP_METHOD AND NOT(EXACT_WEBHOOK_POST)
~~~

Tức là **chỉ miễn đúng POST tới đúng URL webhook**, còn mọi request khác giữ chính sách CSRF mặc định.

### Mục tiêu bài học

Sau bài này bạn có thể:

1. Giải thích ranh giới giữa CSRF, authentication, authorization và xác minh chữ ký webhook.
2. Dùng `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` trong WebFlux thay vì tắt CSRF toàn cục.
3. Kết hợp `CsrfWebFilter.DEFAULT_CSRF_MATCHER`, `AndServerWebExchangeMatcher`, `NegatedServerWebExchangeMatcher` và `ServerWebExchangeMatchers.pathMatchers(...)` chính xác.
4. Giới hạn ngoại lệ theo cả HTTP method lẫn path, không lan sang path con hay PUT/PATCH/DELETE.
5. Kiểm chứng trực tiếp kết quả matcher bằng `StepVerifier` và kiểm chứng hành vi HTTP bằng `WebTestClient`.
6. Giữ CSRF cho Browser POST, login, logout; đồng thời xác thực webhook riêng bằng HMAC.
7. Nhận diện lỗi cấu hình nhiều security chains, matcher quá rộng, kết quả test 403 sai nguyên nhân và các yêu cầu bảo mật production.

## 2. Khi nào thực sự cần CSRF?

CSRF (Cross-Site Request Forgery) xảy ra khi một trang ngoài khiến trình duyệt của nạn nhân gửi một request có tác động lên ứng dụng mà nạn nhân đã đăng nhập. Nếu browser có thể tự mang credential (ví dụ cookie/session hoặc HTTP Basic được lưu), server chỉ dựa vào credential có thể nhầm request giả mạo là hành động có ý định của nạn nhân.

~~~text
Nạn nhân đã đăng nhập app.example
    │
    ▼
Browser giữ session cookie của app.example
    │
    ▼
Nạn nhân mở attacker.example
    │
    ▼
Trang attacker gửi form POST tới app.example/update-email
    │
    ▼
Browser có thể tự gửi cookie theo SameSite và cookie policy
    │
    ▼
Backend chỉ kiểm tra "có session hợp lệ" → tác động trái ý muốn
~~~

Để phòng vệ, ứng dụng session-based có thể yêu cầu CSRF token bí mật, không được browser tự đính kèm vào request cross-site đơn giản, cùng SameSite, origin checks và các lớp phòng vệ hỗ trợ.

**Điểm quyết định không phải tên “REST API” hay “JSON API” mà là cách xác thực được gửi.**

| Tình huống | Cơ sở đánh giá CSRF |
| --- | --- |
| Trang HTML login bằng session cookie | Thường phải giữ CSRF trên thao tác không an toàn |
| SPA gọi API bằng cookie phiên | Browser có thể tự đính kèm cookie; cần CSRF hoặc thiết kế phòng vệ tương đương |
| HTTP Basic trong trình duyệt | Browser có thể tự gửi Basic credentials; không mặc định vô hiệu CSRF |
| API chỉ dùng Bearer token do JS/app chủ động gắn header | Rủi ro CSRF cổ điển có thể khác; vẫn phải kiểm token, XSS và mọi endpoint cookie |
| Webhook server-to-server dùng HMAC/mTLS, không dùng ambient browser auth | Có thể miễn CSRF theo endpoint cụ thể, nhưng phải có xác minh riêng và chống replay |
| Public POST với `permitAll()` | Không tự động miễn CSRF; authorization và CSRF là hai việc khác nhau |

CSRF token **không thay thế** authentication/authorization, và cũng không tự chống XSS. Nếu attacker có XSS trong origin ứng dụng, script có thể đọc token được render cho trang hoặc gửi request cùng origin. Cần chống XSS độc lập, không vì có CSRF token mà bỏ qua output encoding.

### 2.1. HTTP safe methods và nguyên tắc GET không được tạo side effect

Mặc định `CsrfWebFilter.DEFAULT_CSRF_MATCHER` xem GET, HEAD, OPTIONS và TRACE là các phương thức không yêu cầu CSRF token. Những phương thức khác, bao gồm POST, PUT, PATCH và DELETE, thuộc diện được kiểm tra.

Điều đó dựa vào giả định rằng GET/HEAD không thay đổi trạng thái nghiệp vụ. Nếu viết `GET /delete-account`, việc GET đó có thể bị kích hoạt bởi link/image/navigation mà không có token. Cách sửa là đổi thiết kế endpoint sang phương thức phù hợp, **không phải** bổ sung một ngoại lệ matcher để né lỗi.

## 3. Đừng nhầm bốn loại matcher và điều kiện

Spring Security WebFlux có một số API sử dụng `ServerWebExchangeMatcher`, nhưng chức năng khác nhau:

| API | Câu hỏi thực sự |
| --- | --- |
| `ServerHttpSecurity.securityMatcher(...)` | SecurityWebFilterChain này có được chọn cho request không? |
| `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` | Với request đã vào chain, có bắt buộc CSRF token không? |
| `AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)` | Filter authentication cụ thể có thử xác thực request không? |
| `authorizeExchange(...).pathMatchers(...).permitAll()/authenticated()/hasAuthority(...)` | Request có quyền truy cập route theo authentication/authorities không? |

Một endpoint có `permitAll()` có thể vẫn bị CSRF filter chặn POST vì thiếu token. Một endpoint được miễn CSRF vẫn có thể bị AuthenticationWebFilter chặn 401 hoặc authorization chặn 403. Một webhook `permitAll()` để không yêu cầu user login vẫn phải có HMAC verifier riêng trước bất kỳ side effect nào.

### 3.1. WebFlux API khác Servlet API

Reactive WebFlux dùng:

~~~java
org.springframework.security.config.web.server.ServerHttpSecurity
org.springframework.security.web.server.SecurityWebFilterChain
org.springframework.security.web.server.csrf.CsrfWebFilter
org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher
~~~

Servlet Spring MVC thường dùng `HttpSecurity`, `CsrfFilter` và `RequestMatcher`. Không sao chép API `ignoringRequestMatchers(...)` của Servlet vào `ServerHttpSecurity.CsrfSpec` rồi giả định nó tồn tại tương tự trong reactive DSL. Với Spring Security WebFlux 6.x, dùng `requireCsrfProtectionMatcher(...)` để cung cấp matcher cần bảo vệ.

## 4. Biểu thức đúng bằng hai điều kiện độc lập

Định nghĩa:

- `U(r)`: request `r` có method không an toàn theo `CsrfWebFilter.DEFAULT_CSRF_MATCHER`.
- `W(r)`: request `r` là chính xác `POST /integrations/webhook/receive`.
- `C(r)`: request `r` phải có CSRF token.

Ta cần:

~~~text
C(r) = U(r) AND NOT W(r)

Nếu GET/HEAD/OPTIONS/TRACE:
  U(r) = false
  → C(r) = false cho mọi URL.

Nếu POST/PUT/PATCH/DELETE:
  U(r) = true
  → C(r) = false duy nhất khi W(r) = true.
~~~

Trong Spring Security WebFlux:

~~~java
ServerWebExchangeMatcher webhookPost =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.POST, "/integrations/webhook/receive");

ServerWebExchangeMatcher csrfRequired =
    new AndServerWebExchangeMatcher(
        CsrfWebFilter.DEFAULT_CSRF_MATCHER,
        new NegatedServerWebExchangeMatcher(webhookPost)
    );

return http
    .csrf(csrf -> csrf.requireCsrfProtectionMatcher(csrfRequired))
    .build();
~~~

Đây là **đoạn cấu hình trích**, không phải class độc lập. Full project ở phần sau cung cấp imports và các beans.

Ý nghĩa từng phần:

1. `ServerWebExchangeMatchers.pathMatchers(HttpMethod.POST, "...")` chỉ match **một method + một path** đã chỉ định.
2. `NegatedServerWebExchangeMatcher(webhookPost)` có kết quả false chính tại request được miễn.
3. `AndServerWebExchangeMatcher` cho CSRF bắt buộc nếu vừa là unsafe method vừa **không** thuộc ngoại lệ.
4. `requireCsrfProtectionMatcher(...)` thiết lập **toàn bộ predicate** quyết định bắt CSRF, không phải append một ngoại lệ vào default. Vì vậy phải đưa `DEFAULT_CSRF_MATCHER` vào biểu thức AND.
5. Safe methods vẫn có CSRF result false bởi U=false.
6. Các POST khác vẫn yêu cầu token, kể cả khi user đã authenticated hoặc route `permitAll()`.

### 4.1. Tại sao không dùng OR?

~~~java
// PHẢN VÍ DỤ: cú pháp hợp lệ nhưng logic sai.
new OrServerWebExchangeMatcher(
    CsrfWebFilter.DEFAULT_CSRF_MATCHER,
    new NegatedServerWebExchangeMatcher(webhookPost)
);
~~~

Với OR, một POST webhook **vẫn** khớp default unsafe matcher, nên không được miễn; còn nhiều GET không phải webhook lại khớp nhánh NOT webhook, vô tình yêu cầu CSRF. Sai sót này rất khó phát hiện nếu chỉ thử một request không có handler.

### 4.2. Tại sao không dùng mỗi NOT webhook?

~~~java
// PHẢN VÍ DỤ: GET/OPTIONS khác webhook cũng bị yêu cầu token.
new NegatedServerWebExchangeMatcher(webhookPost);
~~~

Nếu không giữ default condition, phần lớn request **không** phải webhook đều match. GET công khai, health-check và OPTIONS preflight có thể gặp CSRF 403. Matcher ngoại lệ phải được kết hợp với chính sách theo method.

### 4.3. Tại sao không miễn mọi method tại cùng path?

~~~java
// PHẢN VÍ DỤ: path-only có thể miễn cả PUT/DELETE tại route này.
ServerWebExchangeMatchers.pathMatchers(
    "/integrations/webhook/receive");
~~~

Khi provider chỉ gửi POST, việc miễn PUT/DELETE là ngoài nhu cầu. Dù hiện tại không có controller cho PUT, endpoint mới thêm sau này có thể vô tình thừa hưởng exemption. Luôn dùng method-aware matcher nếu policy cho phép chỉ một method.

### 4.4. Tránh wildcard rộng

Matcher `/integrations/**` sẽ miễn tất cả callbacks hiện tại và tương lai, kể cả một callback chưa triển khai chữ ký HMAC. Matcher `/api/**` có thể tắt CSRF trên tất cả browser APIs dùng session cookie. Nên ưu tiên exact path và một danh sách ngoại lệ có kiểm soát.

Nếu có nhiều callback hợp lệ, xây một `OrServerWebExchangeMatcher` **giữa các exemption cụ thể**, rồi bọc bằng `NegatedServerWebExchangeMatcher` và kết hợp AND với default. OR lúc này nằm **bên trong nhóm ngoại lệ**, không OR trực tiếp với default CSRF matcher.

## 5. Truth table phải viết trước khi code

| Method | URL | Mặc định unsafe? | Đúng exemption? | Cần CSRF? |
| --- | --- | --- | --- | --- |
| GET | `/health` | Không | Không | Không |
| HEAD | `/health` | Không | Không | Không |
| OPTIONS | `/api/notes` | Không | Không | Không |
| GET | `/api/notes/count` | Không | Không | Không |
| POST | `/integrations/webhook/receive` | Có | **Có** | **Không** |
| POST | `/integrations/webhook/receive/batch` | Có | Không | **Có** |
| POST | `/integrations/other` | Có | Không | **Có** |
| PUT | `/integrations/webhook/receive` | Có | Không | **Có** |
| PATCH | `/integrations/webhook/receive` | Có | Không | **Có** |
| DELETE | `/integrations/webhook/receive` | Có | Không | **Có** |
| POST | `/api/notes` | Có | Không | **Có** |
| POST | `/login` | Có | Không | **Có** |
| POST | `/logout` | Có | Không | **Có** |

Đây là **bảng của matcher**, không phải bảng HTTP status. Một URL không có controller hoặc bị `denyAll` có thể trả 403/404/405 từ tầng khác. Test HTTP status đơn thuần không chứng minh matcher đúng.

**Lưu ý URL:** Path matching áp lên path đã được framework diễn giải, không phải toàn bộ query string. `POST /integrations/webhook/receive?delivery=123` vẫn cùng path webhook trong thiết kế này. Nếu query là một phần của giao thức bảo mật, verifier phải kiểm giá trị của nó bằng cách thích hợp; không coi query tự là bằng chứng xác thực.

## 6. Vì sao miễn CSRF không được miễn xác thực webhook?

Webhook từ server đối tác không có session cookie do browser mang. Để nhận callback, ứng dụng nên dùng một phương thức khác: HMAC, mTLS, JWT/client credentials hoặc chữ ký do provider định nghĩa.

Trong project demo ta chọn **HMAC-SHA-256**:
- Dùng secret riêng cho provider.
- Ký chính xác **raw bytes** body, không phải JSON parse rồi serialize lại.
- Header nhận có dạng `X-Hook-Signature: sha256=<64 ký tự hex>`.
- Verifier kiểm format, tính HMAC kỳ vọng và so sánh bytes bằng `MessageDigest.isEqual(...)`.
- HMAC sai/mất: **401**; HMAC đúng: chấp nhận xử lý demo **202**.
- Không có signature nhưng được miễn CSRF **không** được xem là request hợp lệ.

Cần hiểu: HMAC **không tự chống replay**. Một payload đã ký hợp lệ có thể bị gửi lại. Hệ thống production cần timestamp/delivery ID/nonce nằm trong vật liệu được ký, giới hạn độ lệch thời gian, lưu trạng thái đã xử lý và thiết kế idempotency. Nếu không, thanh toán hoặc cập nhật tài nguyên có thể thực hiện nhiều lần. Đây là vấn đề replay/TOCTOU về trạng thái nghiệp vụ, khác với việc kiểm CSRF.

**Secret trong code học chỉ dùng local.** Production phải lấy từ secret manager hoặc environment an toàn, có rotation và không ghi log. HMAC cũng không thay cho HTTPS, validation, size limit, rate limit, authorization nội bộ hoặc kiểm schema.

## 7. Dự án Java 17+ chạy được với Spring Boot WebFlux

Ví dụ cố định **Spring Boot 3.3.13** và Java 17+ để các APIs minh họa thống nhất. Không coi bản demo là cấu hình production hoàn chỉnh; khi triển khai thực nên chọn dòng Boot đang được hỗ trợ và kiểm thử lại.

### 7.1. Thư mục và Gradle

~~~text
webflux-csrf-scoped/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── CsrfScopedApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WebhookVerifier.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── CsrfScopeTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-csrf-scoped'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản Spring Security và Reactor tương thích. Không thêm `spring-boot-starter-web` của MVC Servlet vào bài WebFlux. `spring-security-test` cung cấp `csrf()` và `springSecurity()`; `reactor-test` cung cấp `StepVerifier`.

`src/main/resources/application.properties`:

~~~properties
# Demo local duy nhất: secret này KHÔNG dùng ở production.
demo.webhook.secret=development-only-change-me
~~~

### 7.2. Main class

`src/main/java/demo/CsrfScopedApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfScopedApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfScopedApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig có ngoại lệ rất hẹp

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }

    // Test có thể gọi method này để xác nhận từng ô truth table.
    static ServerWebExchangeMatcher csrfRequiredMatcher() {
        ServerWebExchangeMatcher exemptWebhook =
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST,
                "/integrations/webhook/receive"
            );

        return new AndServerWebExchangeMatcher(
            CsrfWebFilter.DEFAULT_CSRF_MATCHER,
            new NegatedServerWebExchangeMatcher(exemptWebhook)
        );
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()

                // Không yêu cầu end-user login, NHƯNG controller
                // phải kiểm HMAC hợp lệ trước khi chấp nhận.
                .pathMatchers(HttpMethod.POST,
                    "/integrations/webhook/receive")
                    .permitAll()

                .pathMatchers(HttpMethod.GET,
                    "/api/notes/count")
                    .authenticated()
                .pathMatchers(HttpMethod.POST,
                    "/api/notes")
                    .authenticated()

                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf
                .requireCsrfProtectionMatcher(csrfRequiredMatcher()))
            .build();
    }
}
~~~

**Giải thích:**

- Chỉ có **một security chain**, nên mọi URL đều đi qua chính sách đã cấu hình. `securityMatcher` không được tùy biến trong demo; việc chọn chain và CSRF matcher là hai khái niệm khác nhau.
- `exemptWebhook` match chỉ POST đúng path. PATCH/PUT/DELETE cùng path không được miễn.
- `AndServerWebExchangeMatcher` bảo toàn default safe methods và chỉ loại POST webhook.
- `requireCsrfProtectionMatcher` thiết lập predicate yêu cầu token, không phải `disable()`.
- `permitAll` cho webhook là **quyết định authentication ở mức user**, không chứng minh request từ provider. Chính verifier HMAC sẽ chứng minh điều đó.
- `/api/notes` dùng HTTP Basic để dễ thử test; Basic credentials có thể là ambient trong browser, nên POST vẫn phải có CSRF token.
- `/api/notes/count` là GET; không cần CSRF nhưng vẫn cần authentication.
- `anyExchange().denyAll()` giúp không ngầm cho phép route mới. Nếu thêm form login, cần mở các trang liên quan và test lại CSRF login/logout.
- Không dùng `HttpSecurity`/`CsrfFilter` của Servlet; code đúng stack reactive.

### 7.4. Verifier HMAC xác minh raw body

`src/main/java/demo/WebhookVerifier.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class WebhookVerifier {

    private static final String PREFIX = "sha256=";
    private final byte[] secret;

    WebhookVerifier(Environment environment) {
        secret = environment
            .getRequiredProperty("demo.webhook.secret")
            .getBytes(StandardCharsets.UTF_8);
    }

    boolean verify(byte[] raw, String header) {
        if (header == null || !header.startsWith(PREFIX)) {
            return false;
        }

        String hex = header.substring(PREFIX.length());
        if (hex.length() != 64) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(hex);
        }
        catch (IllegalArgumentException badHex) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(raw);
            return MessageDigest.isEqual(expected, supplied);
        }
        catch (GeneralSecurityException configError) {
            throw new IllegalStateException(
                "Webhook HMAC configuration failed", configError);
        }
    }
}
~~~

- `HexFormat` là Java 17 API.
- Chữ ký HMAC được tính trên **bytes nguyên gốc** từ request body. Parse rồi serialize lại JSON có thể đổi dấu cách/thứ tự key và gây sai digest.
- Header sai format, hex sai hoặc thiếu đều bị từ chối.
- `MessageDigest.isEqual(...)` so sánh digest bằng bytes, không so sánh từng ký tự theo cách ngây thơ.
- Một lỗi thuật toán/secret không được biến thành “bỏ qua xác thực”.
- Đây là verifier dành cho protocol mẫu của bài học, không tương đương mọi provider thật. Production cần versioned signatures, timestamps, nonce, size/format checks, rotation và replay protection.

### 7.5. Controller: webhook và browser API có trách nhiệm riêng

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    record NoteInput(String text) {}
    record NoteView(int count, String text) {}
    record CountView(int count) {}

    private final WebhookVerifier verifier;
    private final AtomicInteger count = new AtomicInteger();

    DemoController(WebhookVerifier verifier) {
        this.verifier = verifier;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/notes/count")
    Mono<CountView> count() {
        return Mono.fromSupplier(() -> new CountView(count.get()));
    }

    @PostMapping(
        path = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<NoteView>> create(
            @RequestBody Mono<NoteInput> body) {

        return body.map(note -> {
            if (note.text() == null
                || note.text().isBlank()
                || note.text().length() > 200) {

                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid note");
            }

            int next = count.incrementAndGet();
            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(next, note.text()));
        });
    }

    @PostMapping(
        path = "/integrations/webhook/receive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<Map<String, String>>> webhook(
            @RequestBody Mono<byte[]> rawBody,
            @RequestHeader(
                name = "X-Hook-Signature", required = false
            ) String signature) {

        return rawBody
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Empty webhook body")))
            .map(bytes -> {
                if (!verifier.verify(bytes, signature)) {
                    throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED, "Bad webhook signature");
                }
                return ResponseEntity.accepted().body(
                    Map.of("status", "accepted"));
            });
    }
}
~~~

**Chú ý về response DTO và body:**
- `@RequestBody Mono<byte[]>` là cách đọc raw bytes để xác minh HMAC. Không đọc raw signature từ query string.
- `X-Hook-Signature` không phải header mặc định của Spring Security; nó thuộc protocol demo.
- HMAC hợp lệ trả HTTP **202 Accepted**; chưa có persistence hoặc giao dịch thật.
- HMAC sai/mất trả **401 Unauthorized**, không được thực hiện side effect.
- `POST /api/notes` có side effect tăng counter. Nếu CSRF filter chặn, controller không được gọi và counter không thay đổi.
- Payload note được validate; không có chỗ để client tự thay owner/role.
- `GET /api/notes/count` dùng `Mono.fromSupplier`, không blocking; không phụ thuộc trực tiếp vào CSRF token.
- Không có lời gọi `block()` hoặc `subscribe()` bên trong reactive controller.
- Trong production, phải giới hạn body size và dùng repository/transaction idempotent thay vì counter RAM.

## 8. Kiểm chứng logic matcher độc lập với HTTP status

Một lỗi test hay gặp: `POST /integrations/other` thiếu token trả 403, rồi suy ra chắc chắn do CSRF. Nhưng `anyExchange().denyAll()` cũng có thể trả 403, hoặc controller/filter khác tự từ chối. **HTTP 403 không đủ để chứng minh CSRF matcher đúng.**

Cần kiểm trực tiếp:

~~~java
SecurityConfig.csrfRequiredMatcher()
    .matches(mockExchange)
    .map(ServerWebExchangeMatcher.MatchResult::isMatch);
~~~

Result là `Mono<Boolean>`. Trong test dùng `StepVerifier` để xác nhận:
- POST exact webhook → false.
- POST path con → true.
- PUT/PATCH/DELETE webhook → true.
- POST browser API/login/logout → true.
- GET/HEAD/OPTIONS → false.

Đây là unit test của policy predicate; nó khác integration test gửi HTTP để kiểm chứng luồng security filters + controller.

## 9. Kiểm thử hoàn chỉnh bằng WebTestClient

`src/test/java/demo/CsrfScopeTests.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfScopeTests {

    private static final String WEBHOOK =
        "/integrations/webhook/receive";
    private static final String SECRET =
        "development-only-change-me";
    private static final byte[] BODY =
        "{\"event\":\"ping\"}".getBytes(StandardCharsets.UTF_8);

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private void expectCsrfRequired(
            HttpMethod method, String path, boolean shouldMatch) {

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.method(method, path));

        StepVerifier.create(
                SecurityConfig.csrfRequiredMatcher().matches(exchange))
            .assertNext(result ->
                assertThat(result.isMatch()).isEqualTo(shouldMatch))
            .verifyComplete();
    }

    @Test
    void exactPostWebhookIsOnlyExemption() {
        expectCsrfRequired(HttpMethod.POST, WEBHOOK, false);
        expectCsrfRequired(HttpMethod.POST, WEBHOOK + "/batch", true);
        expectCsrfRequired(HttpMethod.POST, "/integrations/other", true);
    }

    @Test
    void otherMethodsAtWebhookPathStillNeedCsrf() {
        expectCsrfRequired(HttpMethod.PUT, WEBHOOK, true);
        expectCsrfRequired(HttpMethod.PATCH, WEBHOOK, true);
        expectCsrfRequired(HttpMethod.DELETE, WEBHOOK, true);
    }

    @Test
    void safeHttpMethodsRemainUnprotectedByCsrf() {
        expectCsrfRequired(HttpMethod.GET, "/health", false);
        expectCsrfRequired(HttpMethod.HEAD, "/health", false);
        expectCsrfRequired(HttpMethod.OPTIONS, "/api/notes", false);
    }

    @Test
    void browserPostLoginLogoutAndNotesStillNeedCsrf() {
        expectCsrfRequired(HttpMethod.POST, "/login", true);
        expectCsrfRequired(HttpMethod.POST, "/logout", true);
        expectCsrfRequired(HttpMethod.POST, "/api/notes", true);
    }

    private static String signature(byte[] raw) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                SECRET.getBytes(StandardCharsets.UTF_8),
                "HmacSHA256"));
            return "sha256=" +
                HexFormat.of().formatHex(mac.doFinal(raw));
        }
        catch (GeneralSecurityException error) {
            throw new AssertionError(error);
        }
    }

    @Test
    void validWebhookNeedsNoCsrfAndNoUserSession() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Hook-Signature", signature(BODY))
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void webhookWithoutSignatureFailsAtVerifier() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void webhookWithWrongSignatureFailsAtVerifier() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Hook-Signature",
                "sha256=0000000000000000000000000000000000000000000000000000000000000000")
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() {
        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "No token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithValidCsrfIsCreated() {
        client.mutateWith(csrf())
            .post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "Valid note"))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.text").isEqualTo("Valid note");
    }

    @Test
    void csrfTokenDoesNotReplaceAuthentication() {
        client.mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "Anonymous"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void getDoesNotNeedCsrfButStillNeedsAuthentication() {
        client.get().uri("/api/notes/count")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/notes/count")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.count").isNumber();
    }

    @Test
    void unrelatedPostDoesNotBecomeAnExemption() {
        client.post().uri("/integrations/other")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("event", "ping"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

### 9.1. Tại sao cần cả hai loại kiểm thử?

Các test đầu kiểm tra trực tiếp `ServerWebExchangeMatcher.MatchResult.isMatch()` bằng publisher, nên không nhầm một response 403 của `denyAll` với một response 403 do CSRF. Các test HTTP còn lại thực thi `WebFilterChain`:

- Chữ ký đúng + không có CSRF + không login trên webhook → **202**, chứng minh ngoại lệ có hiệu lực và verifier nhận request.
- Chữ ký thiếu/sai trên webhook → **401**, chứng minh exemption không vô hiệu xác minh nguồn.
- User Basic đúng + POST note thiếu CSRF → **403**, chứng minh browser API vẫn được bảo vệ.
- Basic đúng + `csrf()` hợp lệ trong test → **201**, chứng minh không có cấm nhầm mọi POST.
- CSRF đúng nhưng không auth → **401**, chứng minh CSRF token không tự cấp danh tính.
- GET note-count không CSRF nhưng thiếu auth → **401**, còn khi có auth → **200**.

`WebTestClient.mutateWith(csrf())` **không tắt CSRF trong ứng dụng**. Nó là công cụ Spring Security Test cung cấp token hợp lệ cho mock request. Với browser thật, token phải được cấp và gửi đúng `ServerCsrfTokenRepository` và request handler của Spring Security trong cùng phiên.

### 9.2. Lệnh chạy

~~~bash
gradle bootRun
gradle test
~~~

Đây là hai lệnh dùng **riêng biệt**: chạy server để thử thủ công hoặc chạy test để kiểm chứng. Nếu có Gradle Wrapper, dùng `./gradlew bootRun` và `./gradlew test` trên Unix/macOS, `gradlew.bat` trên Windows. Cần JDK 17+ và Gradle tương thích.

Trong môi trường dependency phù hợp, kỳ vọng **12** phương thức test pass. Kết quả build, stdout/log và thời gian thực tế vẫn phải được kiểm chứng khi chạy, không coi mô tả này là log của một lần đã thực thi.

### 9.3. Test chưa bao gồm gì?

Bài demo tập trung vào matcher, không tự nhận đã kiểm đầy đủ an toàn webhook production. Khi triển khai thật, thêm test:
- Replayed signed payload cùng delivery ID bị từ chối hoặc bỏ qua có kiểm soát.
- Timestamp quá hạn và nonce trùng không được thực thi lại.
- Raw JSON body thay một byte sau khi ký → HMAC sai.
- Header có hex sai/nhầm prefix → bị từ chối.
- Body quá lớn, content type sai và schema sai → 400/413/415 theo HTTP contract.
- Xử lý duplicate event phải idempotent, đặc biệt với thao tác tài chính.
- Chữ ký dùng secret đã bị thu hồi không còn hợp lệ.
- Truy cập URL qua reverse proxy có prefix/trailing slash/encoding bất thường không gây bypass.
- Multi-chain behavior được kiểm ở chain thực tế được chọn.
- Truy cập route protected từ browser có CSRF token sai/khác session bị 403.
- Trên ứng dụng có form login, login/logout POST không token vẫn bị từ chối.

## 10. Kết quả HTTP: 401 và 403 không nói hết nguyên nhân

Bảng dưới áp dụng cho demo, ngoại lệ là exact webhook POST.

| Request | Kỳ vọng | Vì sao |
| --- | --- | --- |
| POST webhook, HMAC đúng, không token CSRF | **202** | Matcher miễn CSRF; verifier đồng ý |
| POST webhook, HMAC sai/mất | **401** | Verifier từ chối |
| POST `/api/notes` Basic đúng, không CSRF | **403** | CsrfWebFilter từ chối |
| POST `/api/notes` Basic đúng, CSRF test hợp lệ | **201** | Qua auth + CSRF, controller xử lý |
| POST `/api/notes` CSRF hợp lệ, thiếu Basic | **401** | Thiếu authentication |
| GET `/api/notes/count`, không Basic | **401** | GET safe nhưng cần login |
| GET `/api/notes/count`, Basic đúng | **200** | Authentication hợp lệ |
| POST path lạ, không token | **403** | Có thể bị CSRF trước denyAll |
| POST path lạ, có token hợp lệ | **403** | `anyExchange().denyAll()` |
| PUT webhook path, không token | **403** | Matcher vẫn yêu cầu CSRF; authorization cũng không cho method |
| Path không có handler nhưng các lớp bảo mật đều cho qua | **404/405** | Routing quyết định tùy URL/method |

**Không** kết luận “403 chứng minh CSRF” khi chưa kiểm tra nơi phát sinh. Spring Security authz, CSRF filter, CORS policy, gateway hoặc app error handler đều có thể trả 403. Với form login browser, unauthenticated request có thể redirect 302 thay vì 401; test của demo đã tắt form login để quan sát rõ HTTP Basic.

### 10.1. Phân biệt “CSRF excluded” và “endpoint được phép xử lý”

Ở webhook, CSRF matcher trả false. Thế nhưng request có HMAC sai vẫn bị 401 và không được xử lý. Ở `/api/notes`, CSRF matcher trả true, nhưng token đúng vẫn không bảo đảm request được phép nếu không login.

Ta có thể hình dung:

~~~text
Có được tiếp tục xử lý?
  ├─ Security chain được chọn?
  ├─ CSRF token hợp lệ NẾU matcher yêu cầu?
  ├─ Authentication của route đúng?
  ├─ Authorization có cho phép thao tác?
  ├─ Với webhook: chữ ký HMAC và replay policy đúng?
  └─ Business validation và data permissions đúng?
      → Chỉ khi các lớp liên quan đều đạt, mới có side effect.
~~~

## 11. Những cạm bẫy khi thay đổi đường dẫn/method

### 11.1. Nới từ exact path sang wildcard

Ban đầu chỉ có `POST /integrations/webhook/receive`. Sau refactor, nếu đổi ngoại lệ thành `/integrations/**`:
- POST `/integrations/webhook/refund` tự được miễn dù chưa có signature policy.
- PUT/PATCH/DELETE under `/integrations/**` có thể miễn nếu matcher không ràng buộc method.
- Người khác dễ hiểu nhầm “mọi integrations đều không cần CSRF”.

Giữ exact path/method, hoặc liệt kê từng endpoint qua một nhóm được review. Mỗi lần thêm callback mới phải có test cả request được miễn **và** những request vẫn phải bảo vệ.

### 11.2. Proxy rewrite và URL normalization

Ingress có thể thêm prefix, thay path hoặc decode URL. Spring Security matcher xét path mà WebFlux nhận tại thời điểm filter chạy; ứng dụng phải biết path đó có giống mapping controller không.

Nếu thấy webhook POST bị 403 trong production, kiểm:
- Request thực đến app path nào?
- Có reverse proxy strip prefix hay set forwarded headers không?
- Trailing slash khác exact path?
- Percent-encoded path, case và dot-segments có được normalize nhất quán không?
- Có một filter/rewrite ở trước Spring Security không?

Đừng sửa bằng cách miễn `/**`. Hãy test chính đường đi qua proxy và cập nhật một matcher có phạm vi được phê duyệt.

### 11.3. Nhiều `SecurityWebFilterChain`

Nếu có chain webhook riêng với `securityMatcher("/integrations/**")` và chain browser cho `/**`, thứ tự chain (`@Order`) quyết định chain nào được chọn. `requireCsrfProtectionMatcher(...)` chỉ ảnh hưởng chain chứa cấu hình ấy.

Một matcher đúng trong chain **không được chọn** sẽ không có tác dụng. Một chain webhook `permitAll` mà không signature verifier cũng có thể tạo lỗ hổng. Hãy test chain selection và authentication protocol riêng cho từng nhóm URL.

**Không** dùng `securityMatcher` để “bỏ qua một CSRF check” nếu ý định chỉ miễn một POST trong cùng chain. Đó là quyết định phạm vi toàn bộ filters, không phải chỉ CsrfWebFilter.

## 12. CORS, cookie và CSRF là chính sách độc lập

Browser CORS preflight gửi OPTIONS, và default CSRF matcher không yêu cầu token đối với OPTIONS. Nếu preflight bị 401/redirect, lỗi có thể do CORS handling và authentication order, không phải do thiếu CSRF token.

- **CORS** kiểm chính sách browser cross-origin về preflight và khả năng đọc response.
- **CSRF** kiểm thao tác giả mạo khi credential được browser tự gửi.
- **Authentication** xác minh danh tính hoặc nguồn webhook.
- **Authorization** kiểm quyền và ranh giới resource.

Tắt CORS không loại bỏ CSRF, vì HTML form cross-site có thể gửi request mà attacker không cần đọc response. Cho phép một origin qua CORS cũng không đồng nghĩa cấp CSRF token hay quyền sửa dữ liệu.

Với SPA dùng session cookie, JavaScript cần cơ chế lấy CSRF token đúng repository và gửi token cùng request. Spring Security WebFlux 6.x có `ServerCsrfTokenRepository` (mặc định WebSession) và request handler; việc `XorServerCsrfTokenRequestAttributeHandler` áp dụng bảo vệ BREACH khiến representation của token cần được dùng đúng cách. Test `csrf()` không thay thế kiểm thử UI thật.

## 13. Tình huống khác: API stateless Bearer-only

Trong một API chỉ nhận Bearer token do client **chủ động** gắn header và không có ambient cookies/HTTP Basic/client certificates nào được browser tự gửi, mô hình CSRF có thể khác hẳn browser session app. Một chain riêng chỉ phục vụ Bearer-only có thể có chính sách CSRF riêng nếu threat model cho phép.

Tuy nhiên:
- Một cookie refresh token ở endpoint khác vẫn có thể cần CSRF.
- Một endpoint đồng thời chấp nhận Basic/session và Bearer có thể vẫn tồn tại CSRF risk.
- JWT cần verify issuer, signature, audience, expiration, scopes, ownership.
- XSS có thể lấy token từ client storage hoặc gửi request với quyền user.
- Endpoint webhook HMAC cần chống replay/idempotency dù không dùng CSRF token.

Không nên suy từ “API là REST” sang “tắt toàn bộ CSRF”; kiểm cách credentials hoạt động và chính sách của từng security chain.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Giải pháp |
| --- | --- | --- |
| `csrf.disable()` toàn chain cho webhook | Browser form/API không còn CSRF protection | Exemption exact POST+path |
| Dùng `NOT webhook` mà bỏ default matcher | GET/OPTIONS có thể cần CSRF | AND với `DEFAULT_CSRF_MATCHER` |
| Dùng OR trực tiếp giữa default và NOT webhook | Webhook vẫn bị bắt token, GET có thể bị bắt | Viết biểu thức logic trước, dùng AND |
| Bỏ path-only không giới hạn method | PUT/DELETE cùng path bị miễn | Path matcher kèm `HttpMethod.POST` |
| Bỏ `/integrations/**` toàn bộ | Route mới tự hưởng ngoại lệ | Chính sách route allowlist chính xác |
| Tin `permitAll()` tắt CsrfWebFilter | POST vẫn 403, dev có thể sửa sai bằng disable() | Tách CSRF matcher và authorization |
| Tin HMAC thay luôn replay protection | Một delivery hợp lệ bị gửi lại | Timestamp+nonce/delivery ID+idempotency |
| So sánh HMAC bằng chuỗi không chuẩn | Có thể tạo lỗi encoding/timing | HMAC raw bytes + `MessageDigest.isEqual` |
| Hard-code secret thật trong repo | Rò rỉ, khó rotate | Secret manager và versioned keys |
| Nhầm `HttpSecurity`/`RequestMatcher` Servlet | Code sai stack WebFlux | `ServerHttpSecurity`/`ServerWebExchangeMatcher` |
| Chỉ test HTTP 403 | Không biết filter nào trả 403 | Unit test matcher + integration tests |
| Chỉ test CSRF disabled trên webhook | Có thể không xác thực webhook | Test signature valid 202, missing/invalid 401 |
| Quên test PUT/PATCH/DELETE ở webhook path | Ngoại lệ vô tình lan qua method | Truth table method-specific |
| Tắt CSRF vì browser API bị 403 | Mất lớp chống CSRF đúng | Cấp token đúng session; dùng `csrf()` trong test |
| Tự `subscribe()` để kiểm chữ ký trước save | Dễ tách lifecycle và side effects | Compose trong `Mono`, không block |
| Coi Origin/CORS là chữ ký provider | Origin có thể bị giả ngoài browser | HMAC/mTLS/OAuth2 độc lập |
| Không test sau proxy rewrite | URL thực không trùng matcher | Kiểm route thực qua ingress/proxy |
| Không test sau bổ sung chain | Request có thể vào chain khác | Test `securityMatcher`/`@Order` |
| Coi 401, 403, 404 là nguyên nhân cố định | Không xác định được nơi từ chối | Phân loại theo security filter/entry point |

### 14.1. Khi CSRF filter đã từ chối, controller có chạy không?

Với `POST /api/notes` thiếu token, `CsrfWebFilter` từ chối trước khi request vào controller, nên counter không tăng. Trường hợp permission/user không hợp lệ cũng phải ngăn side effect. Ở production, nên có test đọc lại tài nguyên để xác nhận request bị từ chối thực sự không ghi dữ liệu.

### 14.2. Có cần test token sai bên cạnh token thiếu?

Có. Ngoài test POST không token, hệ thống thật cần:
- Token random không hợp lệ → 403.
- Token hợp lệ nhưng thuộc session khác → 403.
- Token hết hạn/invalidate → không được phép.
- Token đúng nhưng user chưa đăng nhập → không được vượt authentication.
- Token đúng nhưng thiếu role/owner → không được vượt authorization.

Test Spring Security `csrf()` đơn thuần giúp tạo token giả hợp lệ cho mock request; để kiểm toàn bộ flow session/browser cần integration/E2E test token được server render và cookie được giữ đúng.

## 15. Bài tập và đáp án

**Câu 1.** Chỉ muốn POST `/integrations/webhook/receive` không cần CSRF. Có được gọi `csrf.disable()` không?

**Đáp án:** Không khi còn browser session/cookie/Basic endpoints trong chain. Dùng matcher `DEFAULT_CSRF_MATCHER AND NOT exact POST webhook`.

**Câu 2.** Vì sao chỉ `new NegatedServerWebExchangeMatcher(webhook)` là sai?

**Đáp án:** Nó match cả GET/OPTIONS ngoài webhook, khiến safe methods có thể bị bắt CSRF.

**Câu 3.** OR giữa default matcher và NOT webhook tạo kết quả gì?

**Đáp án:** POST webhook vẫn match default và bị bắt token; nhiều GET match NOT webhook, cũng có thể bị bắt token. Phải dùng AND.

**Câu 4.** `POST /integrations/webhook/receive/batch` có được miễn không?

**Đáp án:** Không, vì exact path khác. Matcher bắt buộc CSRF.

**Câu 5.** `PUT /integrations/webhook/receive` có được miễn không?

**Đáp án:** Không, vì method phải POST để thuộc ngoại lệ.

**Câu 6.** `GET /api/notes/count` có bị yêu cầu CSRF không? Có cần authentication không?

**Đáp án:** Không CSRF theo default safe methods; vẫn cần authentication theo `authorizeExchange`.

**Câu 7.** `permitAll()` cho webhook có nghĩa bỏ HMAC verifier không?

**Đáp án:** Không. Nó chỉ cho phép route được gọi mà không yêu cầu login user; verifier phải kiểm signature trước side effect.

**Câu 8.** Có thể kết luận matcher đúng nếu POST ngoài webhook trả 403 không?

**Đáp án:** Chưa. 403 có thể đến từ `denyAll`; test `MatchResult.isMatch()` trực tiếp.

**Câu 9.** HMAC valid mà request vẫn có thể nguy hiểm khi nào?

**Đáp án:** Khi payload bị replay, signature secret bị lộ, business validation sai hoặc handler thực hiện thao tác trùng. Cần timestamp/nonce, idempotency và audit.

**Câu 10.** Khi webhook server-to-server bị 403, bước đúng đầu tiên là gì?

**Đáp án:** Xác định đúng URL/method và filter phát 403, kiểm matcher, chain routing, signature; không tắt CSRF cả chain.

**Câu 11.** Một JWT-only API không dùng ambient cookies có thể tắt CSRF không?

**Đáp án:** Có thể có cơ sở theo threat model riêng, nhưng vẫn phải xem các endpoint cookie/refresh/Basic và chống XSS, xác thực, authorization.

**Câu 12.** Vì sao phải test POST login/logout dù demo dùng Basic?

**Đáp án:** Để đảm bảo matcher exemption không lan tới các route sẽ cần CSRF khi form login được bật trong cùng chain.

**Câu 13.** `csrf()` của Spring Security Test có thật sự tắt CsrfWebFilter không?

**Đáp án:** Không. Nó cung cấp điều kiện CSRF test hợp lệ, giúp test vượt qua filter khi đúng.

**Câu 14.** Khi thêm proxy prefix và webhook không còn match, nên miễn `/**` cho nhanh?

**Đáp án:** Không. Cần kiểm URL mà WebFlux nhận, sửa mapping/matcher chính xác và test qua proxy.

**Câu 15.** CSRF token hợp lệ có tự cấp role hoặc cho phép thay đổi tài liệu người khác không?

**Đáp án:** Không. Authentication, authorization và object ownership vẫn được kiểm độc lập.

## 16. Checklist review trước khi đưa vào production

- [ ] Có threat model mô tả vì sao endpoint không dùng ambient browser credentials.
- [ ] Exemption **chỉ đúng method + exact path** đã được phê duyệt.
- [ ] CSRF matcher là `DEFAULT_CSRF_MATCHER AND NOT webhookMatcher`; safe methods vẫn không cần token.
- [ ] Không tắt CSRF toàn chain chỉ để một webhook hoạt động.
- [ ] Webhook HMAC/mTLS/auth riêng chạy **trước** mọi side effect.
- [ ] Secret được quản lý an toàn, rotate, không hard-code production.
- [ ] Replay protection, timestamps, nonce/delivery ID, idempotency được triển khai.
- [ ] Validation, request size limits, rate limit và audit phù hợp.
- [ ] Unit test matcher xác minh exact POST, path con, method khác, login/logout và GET/OPTIONS.
- [ ] Integration test webhook HMAC đúng trả 2xx không token CSRF; sai/mất HMAC bị từ chối.
- [ ] Integration test browser POST thiếu/sai CSRF bị 403 và có token hợp lệ thành công.
- [ ] CSRF token không thay thế authentication/authorization; có test riêng cho user thiếu quyền.
- [ ] Không suy diễn từ status 403 đơn lẻ, phân biệt CSRF và denyAll.
- [ ] Security chain selection, proxy rewrite và CORS preflight được kiểm khi có thay đổi.
- [ ] Không log cookie, CSRF token, HMAC secret, signature hoặc credentials.
- [ ] Test negative cases được giữ trong CI để phát hiện ngoại lệ lan quá phạm vi.

## 17. Tài liệu chính thức

- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security API — `ServerHttpSecurity.CsrfSpec` và `requireCsrfProtectionMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security API — `CsrfWebFilter.DEFAULT_CSRF_MATCHER`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security API — `AndServerWebExchangeMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/AndServerWebExchangeMatcher.html
- Spring Security API — `NegatedServerWebExchangeMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/NegatedServerWebExchangeMatcher.html
- Spring Security API — `ServerWebExchangeMatchers`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security — Testing WebFlux with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Ghi nhớ:** Bỏ CSRF an toàn là **giới hạn một ngoại lệ có lý do**, không phải tắt lớp bảo vệ. Spring Security WebFlux cho phép viết biểu thức `unsafe method AND NOT exact webhook POST` bằng `requireCsrfProtectionMatcher(...)`. Hãy kiểm **truth table trực tiếp trên matcher** và dùng **WebTestClient** để xác nhận webhook đúng chữ ký được xử lý, trong khi các POST browser vẫn phải có CSRF token và authentication hợp lệ.
