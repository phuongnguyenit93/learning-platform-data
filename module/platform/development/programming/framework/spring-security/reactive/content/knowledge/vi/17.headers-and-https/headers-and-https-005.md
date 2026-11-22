# Content-Security-Policy, nonce và giới hạn bảo vệ trước XSS

## 1. Bối cảnh và mục tiêu

Trong phần **Header và HTTPS** của **Spring Security reactive / WebFlux**, Content-Security-Policy (**CSP**) là một response header quan trọng để giảm nguy cơ **Cross-Site Scripting (XSS)**. CSP cho browser biết những nguồn script, style, hình ảnh, iframe, kết nối API... được phép trong tài liệu HTML. Một kiểu CSP mạnh sử dụng **nonce**, tức giá trị ngẫu nhiên mới cho từng response, để cho phép một số script đáng tin cậy chạy mà không phải mở `'unsafe-inline'`.

Tuy nhiên, **CSP không chữa được mọi XSS**. Ứng dụng vẫn phải escape dữ liệu khi dựng HTML, dùng DOM API an toàn, sanitize rich HTML khi cần, bảo vệ session và xác minh người dùng. Nếu một đoạn script hợp lệ được cấp nonce nhưng tự dùng `innerHTML` với dữ liệu không tin cậy, nó vẫn có thể trở thành XSS gadget.

Mục tiêu bài học:

1. Hiểu CSP là chính sách **do browser thực thi**, không phải server-side HTML sanitizer hay authentication mechanism.
2. Đọc `Content-Security-Policy` và phân biệt với `Content-Security-Policy-Report-Only`.
3. Dùng đúng các directive `default-src`, `script-src`, `script-src-attr`, `style-src`, `connect-src`, `object-src`, `base-uri`, `form-action`, `frame-ancestors`.
4. Giải thích nonce là gì, vì sao cần ít nhất 128 bit entropy từ `SecureRandom`, tại sao phải tạo mới **mỗi HTML response**, và vì sao header/HTML phải khớp.
5. Cấu hình CSP **tĩnh** bằng DSL `ServerHttpSecurity.headers().contentSecurityPolicy(...)`; phân biệt với CSP **động có nonce**.
6. Chạy ví dụ **Java 17+, Spring Boot 3.3.5, Spring Security reactive**, có HTML động và một script tin cậy mang nonce.
7. Kiểm thử `WebTestClient`: nonce ngẫu nhiên giữa các response, nonce trong HTML khớp header, dữ liệu user được escape, response không cache và authentication vẫn riêng biệt.
8. Hiểu giới hạn bảo vệ trước XSS, hoạt động của `'strict-dynamic'`, Trusted Types, cache/CDN, reverse proxy, CSP reports và HTTPS.
9. Có checklist review bảo mật và cách gỡ lỗi khi browser chặn chính script hợp lệ.

**Phạm vi:** CSP response header và HTML trong ứng dụng WebFlux. Các SPA static/SSR, CDN, template engine hoặc hệ thống dùng nhiều security chains có thể cần triển khai khác, nhưng nguyên lý nonce/CSP vẫn tương tự.

## 2. Nhắc lại XSS và biện pháp phòng thủ chính

### 2.1. XSS bắt đầu từ việc nhầm dữ liệu thành code

Đoạn Java sau **không an toàn** nếu `name` đến từ người dùng:

```java
// ANTI-PATTERN: chỉ dùng để minh họa lỗi injection.
String html = "<p>Xin chào " + name + "</p>";
```

Nếu `name` chứa:

```html
<img src=x onerror="alert('XSS demo')">
```

trình duyệt có thể hiểu nó như HTML thực, và inline event handler `onerror` có thể chạy JavaScript. Đây là payload học tập để nhận diện rủi ro, không dùng trên hệ thống chưa được phép kiểm thử.

Trong HTML **text context**, cần encode trước khi đưa dữ liệu vào:

```java
String escaped = HtmlUtils.htmlEscape(name);
String html = "<p>Xin chào " + escaped + "</p>";
```

`HtmlUtils` thuộc `org.springframework.web.util`. Với dữ liệu có `<`, `>` và các ký tự đặc biệt, output là HTML entities để browser hiển thị **văn bản**. Nhưng quy tắc escape còn phụ thuộc context: HTML attribute, URL, CSS và JavaScript string phải dùng encoding tương ứng; **không dùng chung một HTML escaping function cho mọi trường hợp**.

### 2.2. CSP bổ sung lớp hạn chế thực thi

Nếu một điểm render khác vẫn để lọt `<script>` hoặc `onclick`, CSP chặt có thể ngăn browser thực thi nội dung không nằm trong tập được phép. Đây là **defense-in-depth**.

Bảo vệ có nhiều lớp:

```text
Dữ liệu không tin cậy
        |
        v
Input validation phù hợp nghiệp vụ
        |
        v
Template / DOM safe API / context-aware output encoding
        |
        v
HTML response + CSP response header
        |
        v
Browser kiểm tra các nguồn/hành vi được phép
        |
        v
User interface
```

Không loại bỏ bước output encoding với lý do “đã có CSP”. CSP không phải bộ lọc sửa source HTML trên server và không đảm bảo mọi browser/WebView sẽ thực thi giống nhau.

## 3. CSP là response header gì?

CSP được truyền chủ yếu qua HTTP response:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'none'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
```

Policy gồm các **directive**, phân tách bằng dấu `;`:

- `'self'`: nguồn phù hợp cùng origin với tài liệu trong ngữ nghĩa CSP.
- `'none'`: không cho phép nguồn nào trong source list đó.
- `https://cdn.example.test`: một host source cụ thể, không đặt dấu quote quanh URL.
- `'nonce-abc...'`: cho phép script/style elements mang thuộc tính nonce tương ứng.
- `'sha256-...'`: cho phép nội dung script/style có hash khớp.
- `'strict-dynamic'`: cơ chế ủy thác trust qua scripts được nonce/hash cho phép, cần cân nhắc kỹ.

### Bảng directive cần nắm

| Directive | Hành vi | Gợi ý |
| --- | --- | --- |
| `default-src` | Fallback cho nhiều resource fetch directives | Bắt đầu bằng `'none'` rồi mở từng nhu cầu |
| `script-src` | Script execution và một số JS behaviors | Ưu tiên nonce/hash; hạn chế unsafe-inline/eval |
| `script-src-elem` | Nguồn cho script elements | Tùy biến khi cần phân biệt nguồn `<script>` |
| `script-src-attr` | Inline event-handler attributes | `'none'` chặn rõ `onclick`, `onerror` |
| `style-src` | CSS sources, inline styles theo policy | Chọn stylesheets hợp lệ; nonce/hash nếu cần |
| `img-src` | Image sources | Cho phép chính xác origin/data schemes cần thiết |
| `font-src` | Web fonts | Giới hạn CDN/host theo ứng dụng |
| `connect-src` | Fetch/XHR/WebSocket/EventSource... | Chỉ những API/WSS endpoints cần dùng |
| `object-src` | Object/embed plugins | Thường `'none'` |
| `base-uri` | `<base>` thay đổi base URL | Thường `'none'` |
| `form-action` | Đích HTML form submit | Chỉ các origins cần thiết, ví dụ `'self'` |
| `frame-ancestors` | Ai được phép nhúng document này | `'none'` nếu cấm nhúng |
| `frame-src` | Iframes mà document được phép nhúng | Khác `frame-ancestors` |
| `upgrade-insecure-requests` | Yêu cầu browser nâng subresource HTTP lên HTTPS | Chỉ khi backend/site đã sẵn sàng HTTPS |
| `report-uri` / `report-to` | Gửi báo cáo vi phạm CSP | Cần endpoint, privacy và rate limit |

**Lưu ý quan trọng:** `base-uri`, `form-action` và `frame-ancestors` **không tự lấy fallback từ `default-src`**. Một policy “default-src none” chưa mô tả đầy đủ các ranh giới này.

### `'unsafe-inline'` và `'unsafe-eval'`

`'unsafe-inline'` có thể cho phép inline script/event handlers rộng hơn dự kiến; `'unsafe-eval'` mở các hành vi eval-like. Không thêm chúng chỉ để một frontend cũ chạy được. Nên chuyển inline event handler thành `addEventListener` từ một script đáng tin, chuyển JavaScript thành external files hoặc cho script được kiểm soát một nonce/hash.

Khi browser hỗ trợ nonce/hash trong `script-src`, việc kết hợp `'unsafe-inline'` có quy tắc tương thích riêng; đừng dựa vào những fallback hỗn hợp khi chưa hiểu CSP của browser mục tiêu.

## 4. Enforce và Report-Only

### CSP enforce

```http
Content-Security-Policy: default-src 'none'; script-src 'self'; object-src 'none'
```

Browser thực thi chính sách, chặn nội dung không đáp ứng directive được hỗ trợ và có thể ghi vi phạm trong DevTools.

### CSP Report-Only

```http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'
```

Policy này dùng để **quan sát**, không chặn nội dung chỉ vì vi phạm report-only. Nếu muốn nhận reports ở server, cần cấu hình report endpoint tương ứng và chính sách xử lý dữ liệu gửi tới đó.

### Triển khai theo giai đoạn

1. Kiểm kê HTML documents, inline scripts, stylesheets, CDN, analytics, API connections, WebSocket, iframes.
2. Xây policy thử nghiệm với sources rõ, tránh `*` hoặc `'unsafe-inline'`.
3. Dùng Report-Only để phát hiện trang/chức năng bị ảnh hưởng; kiểm soát report volume và privacy.
4. Sửa frontend code, thêm nonce/hash cho những script do app kiểm soát, loại bỏ inline event handlers/eval.
5. Enforce policy đã test trên các browser mục tiêu.
6. Giữ monitoring và regression tests khi thay libraries/front-end build pipeline.
7. Nếu thêm CSP thứ hai ở gateway, **kiểm tra hiệu ứng giao nhau** với policy đang có.

Nhiều CSP enforced headers thường phải được thỏa **đồng thời**. Chúng không tạo một allowlist OR. Nếu Spring Security áp CSP tĩnh `script-src 'self'` và controller thêm CSP nonce, script inline có nonce có thể vẫn bị policy tĩnh chặn.

## 5. CSP tĩnh trong Spring Security reactive

Theo tài liệu Spring Security, framework **không tự thêm CSP mặc định**, vì CSP phải phản ánh nhu cầu cụ thể của ứng dụng. Ví dụ cấu hình **tĩnh** trên WebFlux:

```java
// FRAGMENT bên trong một @Bean SecurityWebFilterChain.
return http
        .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated())
        .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                        .policyDirectives(
                                "default-src 'none'; "
                              + "script-src 'self'; "
                              + "style-src 'self'; "
                              + "img-src 'self'; "
                              + "connect-src 'self'; "
                              + "object-src 'none'; "
                              + "base-uri 'none'; "
                              + "frame-ancestors 'none'")))
        .build();
```

Trong cấu hình đầy đủ, `http` là `ServerHttpSecurity` và bean trả `SecurityWebFilterChain`. Đây là API **reactive**, không phải `HttpSecurity` / `SecurityFilterChain` Servlet.

Nếu muốn **Report-Only**:

```java
// FRAGMENT THAY THẾ, không bật đè lên policy dynamic trong demo.
.headers(headers -> headers
        .contentSecurityPolicy(policy -> policy
                .policyDirectives(
                        "default-src 'none'; "
                      + "script-src 'self'; "
                      + "object-src 'none'; "
                      + "base-uri 'none'")
                .reportOnly()))
```

Cả hai fragments mang ý nghĩa phương án độc lập. Nếu app không dùng inline scripts, CSP tĩnh có thể phù hợp. Nhưng **nonce phải đổi theo từng response**; một `policyDirectives(...)` tĩnh, chạy khi khởi tạo filter chain, không có nonce tương ứng với HTML sinh động.

**Ví dụ chạy đầy đủ dưới đây sẽ không bật CSP writer tĩnh**, vì controller tạo CSP nonce động trên response `/page`. Không ghép hai snippet này vào cùng chain mà không thiết kế chính sách chung.

## 6. Nonce là gì và phải sinh như thế nào?

**Nonce** là giá trị ngẫu nhiên cho phép một script/style element cụ thể. Server gửi nonce trong **CSP header**, đồng thời đặt nó trong thuộc tính `nonce` của **thẻ do ứng dụng tin cậy tạo ra**:

```http
Content-Security-Policy: default-src 'none'; script-src 'nonce-ExampleRandomValueOnly'; object-src 'none'; base-uri 'none'
```

```html
<script nonce="ExampleRandomValueOnly">
  document.getElementById("message").textContent = "Script tin cậy";
</script>
```

Chuỗi trên chỉ dùng để giải thích cú pháp, **không đủ entropy và không nên sao chép vào production**. Với nonce thật, dùng CSPRNG và giá trị mới từng response.

### Yêu cầu kỹ thuật

- **Ít nhất 128 bit entropy**. Ví dụ dùng 24 random bytes = **192 bit**, rồi Base64 encode.
- Sinh bằng `java.security.SecureRandom`, không dùng `Math.random()`, timestamp hoặc incrementing counter.
- Mỗi **HTML response** có nonce mới, không giữ trong `application.properties`, static constant hoặc session để dùng lại.
- Trong **cùng response**, header và HTML dùng **chính xác một nonce chung**.
- Nonce chỉ cấp cho script/style **do server/template kiểm soát**. Không tự động gắn nonce lên mọi `<script>` sau khi ghép user-supplied HTML.
- Không cần nonce là bí mật vĩnh viễn: nó xuất hiện trong response và DOM. Thuộc tính quan trọng là **không thể dự đoán trước một response mới**.
- Khi HTML được cache hoặc proxy rewrite, phải giữ **header và HTML khớp**; không ghép cached body nonce A với header nonce B.
- Không đặt nonce thành token authentication, password hoặc CSRF token.

### Nonce, hash và SRI

| Cơ chế | Mục đích | Phù hợp khi |
| --- | --- | --- |
| CSP nonce | Cho phép script/style elements tin cậy trong response | HTML render động |
| CSP hash `'sha256-...'` | Cho phép đoạn inline script/style có nội dung khớp hash | Nội dung tĩnh, ít đổi |
| SRI `integrity="sha384-..."` | Xác thực nội dung resource được tải theo hash | External scripts/styles từ CDN |
| CSP host allowlist | Cho phép nguồn theo origin/host | Cần cân nhắc XSS có thể dùng nguồn cùng origin |
| `'strict-dynamic'` | Tin scripts được nonce/hash và scripts chúng load động | Loader đã được rà soát tránh script gadgets |

Không coi nonce như “chữ ký xác minh nội dung”: nonce cho phép **thẻ script** và không chứng minh rằng logic bên trong thẻ an toàn. Với external resources, SRI có mục tiêu khác và nên được cân nhắc thêm.

## 7. Ví dụ hoàn chỉnh: Spring Boot WebFlux sinh nonce cho từng HTML response

Demo dùng **Java 17+**, **Spring Boot 3.3.5**, Spring Security do Boot BOM quản lý và Gradle tương thích (ví dụ 8.5).

Hành vi:

- `GET /page?name=An`: server sinh nonce mới, đặt CSP header và HTML có script nonce phù hợp.
- Dữ liệu `name` được **HTML escape** trước khi đưa vào text node.
- Script đáng tin đăng ký event bằng `addEventListener`, không dùng `onclick`.
- `Cache-Control: no-store` cho trang có nonce; không bật CSP tĩnh mâu thuẫn.
- `GET /health` công khai.
- `GET /api/profile` yêu cầu HTTP Basic, để chứng minh CSP không thay authentication.

### 7.1. Cấu trúc project

```text
reactive-csp-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/csp/
    │   ├── CspApplication.java
    │   ├── SecurityConfig.java
    │   ├── CspNonceGenerator.java
    │   └── CspController.java
    └── test/java/dev/example/csp/
        └── CspSecurityTests.java
```

### 7.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-csp-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không đồng thời thêm `spring-boot-starter-web` vào demo WebFlux thuần: Spring Boot thường ưu tiên Servlet/MVC khi có cả hai web starters.

### 7.3. Application entry point

`src/main/java/dev/example/csp/CspApplication.java`:

```java
package dev.example.csp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CspApplication {
    public static void main(String[] args) {
        SpringApplication.run(CspApplication.class, args);
    }
}
```

### 7.4. Security config

`src/main/java/dev/example/csp/SecurityConfig.java`:

```java
package dev.example.csp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/page", "/health")
                            .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Giải thích:
- `@EnableWebFluxSecurity` và `ServerHttpSecurity` là stack reactive.
- Trang HTML công khai để demo; `/api/profile` yêu cầu principal đã xác thực.
- User mẫu `reader` và password `reader-pass` chỉ dùng localhost, được BCrypt encode trong memory.
- Không có `.contentSecurityPolicy(...)` writer tĩnh trong chain; header nonce sẽ do controller `/page` tạo, tránh hai CSP policies trùng nhau.
- Spring Security vẫn có các default headers khác, ví dụ `X-Content-Type-Options: nosniff`.
- `formLogin` được tắt để quan sát HTTP Basic 401 rõ hơn.
- Production phải dùng HTTPS/TLS nếu truyền HTTP Basic, không hardcode credentials demo.

### 7.5. Nonce generator dùng SecureRandom

`src/main/java/dev/example/csp/CspNonceGenerator.java`:

```java
package dev.example.csp;

import java.security.SecureRandom;
import java.util.Base64;

import org.springframework.stereotype.Component;

@Component
public class CspNonceGenerator {

    private final SecureRandom random = new SecureRandom();

    public String nextNonce() {
        byte[] bytes = new byte[24]; // 24 bytes = 192 bits
        random.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
```

Mỗi lời gọi `nextNonce()` tạo mảng bytes mới rồi điền bằng CSPRNG. Một bean generator dùng chung là được; **không được lưu nonce đã sinh trong một field rồi reuse**. 24 bytes đủ 192 bit entropy, Base64 output dài khoảng 32 ký tự. Base64 không phải encryption; ở đây chỉ giúp biểu diễn nonce bằng các ký tự hợp lệ trong CSP.

### 7.6. WebFlux controller tạo CSP và HTML đồng bộ

`src/main/java/dev/example/csp/CspController.java`:

```java
package dev.example.csp;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

import reactor.core.publisher.Mono;

@RestController
public class CspController {

    private final CspNonceGenerator nonceGenerator;

    public CspController(CspNonceGenerator nonceGenerator) {
        this.nonceGenerator = nonceGenerator;
    }

    @GetMapping(value = "/page", produces = MediaType.TEXT_HTML_VALUE)
    public Mono<ResponseEntity<String>> page(
            @RequestParam(defaultValue = "khách") String name) {

        return Mono.fromSupplier(() -> {
            String nonce = nonceGenerator.nextNonce();
            String safeName = HtmlUtils.htmlEscape(name);

            String policy = "default-src 'none'; "
                    + "script-src 'nonce-" + nonce + "'; "
                    + "script-src-attr 'none'; "
                    + "style-src 'none'; "
                    + "img-src 'self'; "
                    + "connect-src 'self'; "
                    + "object-src 'none'; "
                    + "base-uri 'none'; "
                    + "form-action 'self'; "
                    + "frame-ancestors 'none'";

            String html = """
                    <!doctype html>
                    <html lang="vi">
                    <head>
                      <meta charset="utf-8">
                      <title>Spring WebFlux CSP demo</title>
                    </head>
                    <body>
                      <h1>Nonce CSP demo</h1>
                      <p id="message">Xin chào %s</p>
                      <button id="change" type="button">Đổi lời chào</button>
                      <script nonce="%s">
                        document.getElementById("change")
                          .addEventListener("click", () => {
                            document.getElementById("message")
                              .textContent = "Script tin cậy đã chạy";
                          });
                      </script>
                    </body>
                    </html>
                    """.formatted(safeName, nonce);

            return ResponseEntity.ok()
                    .contentType(new MediaType(
                            MediaType.TEXT_HTML, StandardCharsets.UTF_8))
                    .cacheControl(CacheControl.noStore())
                    .header("Content-Security-Policy", policy)
                    .body(html);
        });
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(Principal principal) {
        return Mono.just(Map.of("user", principal.getName()));
    }
}
```

#### Vì sao cách này đáp ứng chính sách?

1. `Mono.fromSupplier(...)` thực hiện logic khi subscriber xử lý request. Mỗi response `/page` có một lần tạo nonce mới.
2. Nonce từ `SecureRandom` có đủ entropy; **cùng biến `nonce`** được dùng để dựng `script-src` và HTML `<script nonce="...">`.
3. `script-src 'nonce-...'` cho phép thẻ script do server sở hữu, không cho phép mọi inline scripts.
4. `script-src-attr 'none'` và không có `'unsafe-inline'` giúp chặn inline event handler attributes.
5. Script dùng `addEventListener` thay vì `onclick="..."`.
6. `HtmlUtils.htmlEscape(name)` xử lý user input **trước khi chèn vào HTML text context**. Không chèn user input vào script source, HTML attribute không được escape hoặc URL javascript.
7. `object-src 'none'`, `base-uri 'none'` và `frame-ancestors 'none'` giảm một số attack surfaces khác.
8. `CacheControl.noStore()` nhằm tránh tái dùng document có nonce; CDN/proxy vẫn phải được cấu hình phù hợp.
9. `ResponseEntity` đặt đúng `Content-Type: text/html; charset=UTF-8` và CSP header.
10. Dù `/page` public, `/api/profile` vẫn cần auth. CSP không thay authorization.
11. Không thêm global CSP writer thứ hai. Nếu dùng gateway cũng thêm CSP, phải kiểm tra giao nhau của policies.
12. `Mono<ResponseEntity<String>>` là kiểu trả phù hợp cho controller reactive; không gọi `block()` hay `subscribe()`.

Đây là demo **server-rendered HTML** nhỏ không cần template engine. Với Thymeleaf/SSR thật, cách tương đương là tạo một nonce duy nhất cho request, truyền vào model/template và dùng để render cả header lẫn thẻ script do template tạo. **Không tự động gắn nonce vào mọi script tag sau khi ghép dữ liệu người dùng**.

## 8. Chạy và quan sát header

Từ thư mục `reactive-csp-demo`:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Server mặc định ở `http://localhost:8080`.

### 8.1. Dùng curl xem response

```bash
curl -i "http://localhost:8080/page?name=An"
```

Bạn sẽ thấy các phần như:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
Cache-Control: no-store
Content-Security-Policy: default-src 'none'; script-src 'nonce-<NONCE_MOI>'; script-src-attr 'none'; style-src 'none'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

`<NONCE_MOI>` chỉ là **ký hiệu minh họa output**, không phải giá trị thật. HTML body có:

```html
<p id="message">Xin chào An</p>
<script nonce="<CHINH_GIA_TRI_NONCE_TRONG_HEADER>">
  // Script có addEventListener do ứng dụng tạo.
</script>
```

Đây là **output rút gọn**, không phải nguyên response chính xác từng byte. Điều phải kiểm tra là **header và script attribute khớp trong cùng response**, còn **nonce thay đổi giữa hai response**.

`curl` không thực thi CSP như browser. Dùng nó để kiểm tra header/body, không để kết luận XSS đã bị chặn trong browser.

### 8.2. Thử input HTML nguy hiểm trong môi trường học

```bash
curl -i "http://localhost:8080/page?name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E"
```

Sau HTML escaping, trang chứa text dạng:

```html
<p id="message">Xin chào &lt;img src=x onerror=alert(1)&gt;</p>
```

Browser hiển thị ký tự như văn bản, không tự tạo một `<img>` từ input đó. Đây là lợi ích trực tiếp của **output encoding**. Nếu một context render khác không encode, CSP có thể chặn event handler thiếu nonce, nhưng cần sửa origin of injection chứ không chỉ trông cậy CSP.

### 8.3. Dùng DevTools

1. Mở `http://localhost:8080/page?name=An`.
2. Vào **Network → Document /page**, xem `Content-Security-Policy`, `Content-Type` và `Cache-Control`.
3. Kiểm tra trong DOM có `<script nonce="...">` của ứng dụng.
4. Bấm nút “Đổi lời chào”; script có nonce hợp lệ hoạt động.
5. Reload và xem nonce mới. Nếu giống hệt nhau trên nhiều responses, kiểm tra generator/cache.
6. Thử URL-encoded input HTML; xác nhận hiển thị như text.
7. Xem **Console** để phát hiện CSP violations.
8. Nếu DevTools `getAttribute("nonce")` trả chuỗi rỗng, đó có thể là cơ chế **nonce hiding** của browser; `element.nonce` property vẫn có thể đọc được. Không xem nonce như bí mật vĩnh viễn.

**Không dùng kết quả gõ trực tiếp JavaScript trong DevTools Console như bằng chứng duy nhất về CSP**: DevTools có quyền đặc biệt và hành vi khác với script được phân phối qua HTML. Dùng test page/E2E và quan sát script elements/violation thực.

### 8.4. Authentication vẫn độc lập

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/profile

# Curl hỏi mật khẩu demo khi chỉ đưa username.
curl -i --user reader http://localhost:8080/api/profile
```

Dự kiến:
- `GET /health` → 200, body `ok`.
- `GET /api/profile` không credentials → 401.
- `GET /api/profile` với reader đúng password → 200, JSON chứa `user=reader`.

Trong production phải dùng HTTPS/TLS có xác thực server; không gửi HTTP Basic credential rõ trên đường truyền HTTP.

## 9. Test bằng WebTestClient

`WebTestClient` giúp kiểm chứng response headers/body của WebFlux. Nó **không phải browser JavaScript engine**: test đạt không chứng minh browser chặn mọi XSS. Cần có browser E2E khi triển khai chính sách bảo mật.

Tệp `src/test/java/dev/example/csp/CspSecurityTests.java`:

```java
package dev.example.csp;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CspSecurityTests {

    private static final Pattern NONCE_PATTERN =
            Pattern.compile("script-src 'nonce-([^']+)'");

    @Autowired
    WebTestClient client;

    private EntityExchangeResult<String> page(String url) {
        return client.get().uri(url)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .returnResult();
    }

    private String nonceInHeader(EntityExchangeResult<String> result) {
        String policy = result.getResponseHeaders()
                .getFirst("Content-Security-Policy");
        assertNotNull(policy);

        Matcher matcher = NONCE_PATTERN.matcher(policy);
        assertTrue(matcher.find());
        return matcher.group(1);
    }

    @Test
    void trustedScriptHasTheNonceDeclaredInCsp() {
        EntityExchangeResult<String> result = page("/page?name=An");
        String nonce = nonceInHeader(result);
        String html = result.getResponseBody();

        assertNotNull(html);
        assertTrue(nonce.length() >= 22);
        assertTrue(html.contains("<script nonce=\"" + nonce + "\">"));
    }

    @Test
    void twoResponsesHaveDifferentNonces() {
        String first = nonceInHeader(page("/page"));
        String second = nonceInHeader(page("/page"));

        assertNotEquals(first, second);
    }

    @Test
    void scriptPolicyDoesNotUseUnsafeInlineOrUnsafeEval() {
        EntityExchangeResult<String> result = page("/page");
        String policy = result.getResponseHeaders()
                .getFirst("Content-Security-Policy");

        assertNotNull(policy);
        assertFalse(policy.contains("'unsafe-inline'"));
        assertFalse(policy.contains("'unsafe-eval'"));
        assertTrue(policy.contains("object-src 'none'"));
        assertTrue(policy.contains("base-uri 'none'"));
        assertTrue(policy.contains("frame-ancestors 'none'"));
        assertTrue(policy.contains("script-src-attr 'none'"));
    }

    @Test
    void userInputIsHtmlEscaped() {
        EntityExchangeResult<String> result = page(
                "/page?name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E");
        String html = result.getResponseBody();

        assertNotNull(html);
        assertTrue(html.contains("&lt;img"));
        assertTrue(html.contains("&gt;"));
        assertFalse(html.contains("<img src=x"));
    }

    @Test
    void dynamicHtmlIsMarkedNoStore() {
        EntityExchangeResult<String> result = page("/page");
        String header = result.getResponseHeaders()
                .getFirst(HttpHeaders.CACHE_CONTROL);

        assertNotNull(header);
        assertTrue(header.contains("no-store"));
    }

    @Test
    void springSecurityStillSetsNosniff() {
        EntityExchangeResult<String> result = page("/page");
        assertEquals("nosniff", result.getResponseHeaders()
                .getFirst("X-Content-Type-Options"));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void profileNeedsAuthentication() {
        client.get().uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCanViewProfile() {
        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.user").isEqualTo("reader");
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả dự kiến:** 9 test thành công nếu các file và dependency đồng nhất với ví dụ. Đây là **kết quả dự kiến theo code**, không phải tuyên bố đã thực thi Gradle trong môi trường của bạn.

### Phạm vi các test

| Test | Xác nhận | Chưa chứng minh |
| --- | --- | --- |
| CSP nonce khớp thẻ script | Header và HTML được tạo đồng bộ | Browser không còn XSS |
| Nonce mới ở 2 response | Không reuse nonce giữa 2 requests | Mọi node CDN/proxy được cấu hình đúng |
| Không unsafe-inline/eval | Script policy chặt ở các directive được test | Không có script gadget nào |
| HTML escape | Input trong **text context** không thành tag | Mọi HTML/JS/CSS context an toàn |
| Cache-Control no-store | Trang demo yêu cầu không cache | Mọi cache tầng proxy tuân thủ |
| Nosniff tồn tại | Default header của Spring Security có hiệu lực | HTTPS/HSTS đã được cấu hình |
| 401/200 profile | Authentication độc lập với CSP | Mọi endpoint có authorization đầy đủ |

**Điểm cần test thật kỹ:** Nếu filter A tạo nonce A trong header nhưng view B tạo nonce B trong script, cả hai có thể trông như “đã có nonce” mà browser vẫn chặn. Test phải so **giá trị cùng response**, không chỉ assert chuỗi `nonce-` xuất hiện.

## 10. Thiết kế nonce trong ứng dụng nhiều trang

### 10.1. WebFilter và template engine

Với nhiều HTML controllers, đặt một **request-scoped nonce** là lựa chọn dễ quản lý:

```text
HTTP request
     |
     v
WebFilter / request context tạo nonce một lần
     |
     +--> Lưu nonce vào ServerWebExchange attribute
     |
     +--> Xây CSP response header theo nonce đó
     |
     +--> Truyền nonce tới view/template
     |
     v
Render HTML: chỉ thẻ script/style tin cậy có nonce
     |
     v
Response header + body đồng bộ
```

Đây là sơ đồ thiết kế, **không phải code filter độc lập**. Nếu dùng `ServerHttpResponse.beforeCommit(...)`, nhớ phải ghi header **trước khi response commit**. Đừng `block()` để lấy nonce từ `Mono` và đừng tạo nhiều nonce khác nhau trong các components của cùng document.

### 10.2. Template engine và user-provided HTML

Template chỉ gắn nonce vào thẻ `<script>`/`<style>` mà team kiểm soát. **Không** chạy regex thay mọi `<script>` trong HTML kết quả để thêm nonce: attacker có thể gửi một HTML fragment chứa script, rồi cơ chế đó vô tình cấp nonce cho nó.

Nếu template engine tự escape text thì giữ behavior đó; đừng dùng HTML raw/unescaped directive trừ khi giá trị đã được sanitize theo policy của ứng dụng.

### 10.3. Static SPA, SSR và hash-based policy

Với HTML tĩnh qua CDN, nonce mới **cho mỗi response** không dễ áp dụng nếu CDN phục vụ nguyên bytes đã cache. Lựa chọn:
- Chuyển inline scripts sang files và dùng CSP phù hợp.
- Dùng hash-based CSP cho những inline snippets tĩnh.
- Có server/edge render động nonce trong header và HTML trước khi trả.
- Không reuse một nonce sinh lúc build cho toàn bộ người dùng.
- Kiểm tra scripts do framework build inject vào document, hydration, third-party SDK và CSS runtime.

Nếu CDN chỉ thay CSP header mà không thay script nonce trong cached body, browser chặn script tin cậy. Nếu CDN thay body mà không cập nhật header, cũng sai. Cần chiến lược caching nhất quán và test tại response cuối cùng đến browser.

### 10.4. Nhiều Spring Security filter chains

Với `@Order`/`securityMatcher` có thể có chain riêng cho HTML, API, admin... Một CSP writer của chain A không tự áp dụng cho document đi chain B. Kiểm tra từng đường dẫn, redirect và error page. Có thể đặt policy HTML ở tầng controller/renderer và policy tĩnh ở tầng security header writer cho những response khác, nhưng phải tránh header duplicate/mismatch.

### 10.5. Proxy, gateway và nhiều CSP headers

Nếu proxy đặt CSP cố định còn app đặt CSP nonce, browser phải thỏa **mọi enforced policies**. Ví dụ:
- Policy A: `script-src 'self'`.
- Policy B: `script-src 'nonce-abc'`.

Một inline script mang nonce abc thỏa B nhưng có thể vẫn vi phạm A, vì `'self'` không cho phép inline script tương ứng. Không giải quyết bằng cách chuyển cả hai về `'unsafe-inline'`. Hãy thống nhất ownership và test CSP response cuối cùng.

## 11. Giới hạn bảo vệ trước XSS

### 11.1. CSP không thay output encoding

OWASP coi context-aware output encoding và sanitization khi cần là biện pháp phòng thủ chính. Script injected có thể bị CSP chặn, nhưng markup không tin cậy vẫn có thể làm đổi giao diện, tạo phishing form hoặc khai thác những browser/libraries có hành vi khác. Đừng cho raw user input vào:
- HTML text mà chưa HTML escape.
- HTML attributes mà chưa encode đúng context.
- JS string/source code.
- CSS string/URL.
- `href=javascript:...` hay các dangerous URLs.
- DOM `innerHTML` và các sink nguy hiểm.

Khi muốn hiển thị text, dùng `textContent` trong JavaScript, không dùng `innerHTML`. Khi cần rich HTML, dùng sanitizer đáng tin (ví dụ DOMPurify trong bối cảnh phù hợp), cập nhật thường xuyên và tránh sửa đổi sau sanitize theo cách làm mất bảo vệ.

### 11.2. Một script có nonce vẫn có thể là XSS gadget

Fragment JavaScript sau **không an toàn dù nằm trong script đã được nonce cho phép**:

```javascript
// ANTI-PATTERN: mã tin cậy vẫn xử lý input theo cách nguy hiểm.
const query = new URLSearchParams(location.search).get("html");
document.getElementById("target").innerHTML = query;
```

Script hợp lệ có quyền truy cập DOM. CSP có thể chặn một số bước thực thi script chèn tiếp theo nhưng không bảo đảm vô hiệu mọi cách khai thác. Sửa bằng `textContent` hoặc sanitizer cho rich HTML, và loại bỏ đường vào nguy hiểm.

### 11.3. `'strict-dynamic'` có cả lợi ích và rủi ro

Khi CSP có nonce/hash cùng `'strict-dynamic'`, browser hỗ trợ có thể tin scripts được script đã tin cậy tạo/load động. Điều này giúp script loader hoạt động, nhưng nếu loader tạo `<script src=...>` dựa trên query parameter hay dữ liệu không đáng tin, attacker có thể điều khiển nguồn script theo chính sách cho phép.

Ở các browser hỗ trợ `'strict-dynamic'`, những host source/scheme source hoặc `'self'` trong `script-src` có thể bị bỏ qua cho mô hình đó. Không hiểu `'strict-dynamic'` như “thêm một origin vào allowlist” một cách đơn giản.

### 11.4. Nonce không phải access token

Nonce xuất hiện trong document và có thể được truy cập bằng DOM APIs. Nó không thay CSRF token hay session identifier. Nếu attacker đã có khả năng thực thi JavaScript đáng tin cậy trong origin, nonce không tự ngăn việc đọc những dữ liệu mà script hợp pháp có thể truy cập. Nonce chủ yếu ngăn **một script chưa được tin cậy trở thành script được chạy**.

### 11.5. CSP không sửa các lỗ hổng backend

IDOR/BOLA, sai phân quyền, SSRF, SQL injection, insecure deserialization, leaked JWT, lộ dữ liệu do thiếu tenant isolation, CSRF và các lỗi nghiệp vụ không được chữa chỉ bằng CSP. Server vẫn phải xác thực/ủy quyền và validate request.

CSP cũng không mã hóa HTTP, không thu hồi token và không ngăn bot/curl gửi request: **HTTPS, HSTS, security filters, authn/authz, CSRF và rate limit** là các kiểm soát khác.

### 11.6. Browser compatibility

CSP được thực thi bởi browser hỗ trợ, không phải mọi HTTP client. Những directive mới như `script-src-attr`, `'strict-dynamic'` hoặc Trusted Types có mức hỗ trợ và hành vi khác nhau. Cần kiểm thử browser trong danh sách sản phẩm hỗ trợ, đồng thời duy trì output encoding kể cả khi policy không được thực thi.

## 12. Trusted Types và các lớp bảo vệ bổ sung

**Trusted Types** (nơi browser hỗ trợ) có thể yêu cầu một số DOM injection sinks nhận loại dữ liệu được tạo qua policy phù hợp, thay vì arbitrary string. Directive `require-trusted-types-for 'script'` có thể giúp giảm DOM XSS trong hệ thống dùng nhiều DOM APIs.

Nhưng:
- Trusted Types **không tự sanitize dữ liệu**. Policy tạo TrustedHTML/TrustedScriptURL vẫn phải validate/sanitize đúng.
- Browser hỗ trợ khác nhau; cần feature detection và fallback phù hợp.
- Nếu policy rất rộng, ví dụ trả nguyên input chưa kiểm tra, hiệu lực bảo vệ giảm.
- Nên dùng safe DOM APIs từ đầu, rồi bổ sung Trusted Types trong ứng dụng phức tạp.
- Không bật một directive mới trong production mà chưa rà libraries vốn dùng `innerHTML` hoặc các sinks bị kiểm soát.

Một hệ thống an toàn theo lớp:
- Context-aware encoding + safe rendering.
- HTML sanitization khi cho phép user tạo markup.
- Nonce/hash-based CSP.
- Trusted Types nếu browser/framework hỗ trợ.
- Dependencies/third-party script auditing và SRI khi phù hợp.
- HTTPS/HSTS, cookie attributes và authentication/authorization riêng.

## 13. CSP Report-Only và violation reports

Một policy Report-Only ví dụ:

```http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; object-src 'none'; report-uri /csp-report
```

Nó không tự chặn script, chỉ hướng browser ghi nhận/report vi phạm. `report-uri`/`report-to` và `Reporting-Endpoints` phụ thuộc browser support/config, nên phải kiểm tra các browser mục tiêu.

**Đừng chỉ khai báo `report-uri` rồi nghĩ server tự nhận báo cáo.** Cần endpoint tương ứng, xử lý nội dung đầu vào không tin cậy và bảo vệ khỏi flood.

Violation report có thể chứa:
- URL tài liệu hoặc URL resource bị chặn.
- Directive vi phạm, file/line info.
- Mẫu nội dung bị chặn nếu bật `'report-sample'` ở browser phù hợp.

Những dữ liệu đó có thể lộ PII hoặc token nếu hệ thống từng cho dữ liệu nhạy cảm trong URL/source. Vì vậy cần:
1. Không đặt secret vào query/path.
2. Loại thông tin nhạy cảm ở report receiver và log collector.
3. Giới hạn kích thước, rate limit/sampling.
4. RBAC/audit, retention và privacy policy.
5. Không bật `'report-sample'` mặc định cho mọi tình huống.
6. Phân biệt violations từ browser extensions với regression thật của ứng dụng.

Một ứng dụng có thể giữ **enforce policy đang chạy** và dùng một **report-only policy mới** để thử việc siết chặt tiếp, nhưng phải biết policy nào chặn và policy nào chỉ quan sát.

## 14. CSP cùng các HTTP security headers khác

| Cơ chế | Mục đích | Không thay thế |
| --- | --- | --- |
| CSP | Giới hạn nguồn/hành vi nội dung trong document | Output encoding, authn/authz, CSRF |
| HTTPS/TLS | Bảo vệ dữ liệu HTTP trên kết nối | CSP, server authorization |
| HSTS | Giúp browser ưu tiên HTTPS sau khi học policy | Certificate validation, CSP |
| `X-Content-Type-Options: nosniff` | Hạn chế MIME sniffing | CSP script policy |
| `X-Frame-Options` | Giảm clickjacking trong browser cũ | Mọi khả năng CSP |
| `frame-ancestors` | Chọn origin nào được nhúng trang | `frame-src` chiều ngược lại |
| `Referrer-Policy` | Giảm dữ liệu gửi qua Referer | Authentication |
| Cookie `Secure`/`HttpOnly`/`SameSite` | Giảm một số rủi ro cookie | CSP và CSRF mọi trường hợp |
| CSRF token | Bảo vệ thao tác state-changing với browser credentials | CSP và CORS |
| SRI | Kiểm chứng bytes resource tải ngoài | Nonce freshness |
| Trusted Types | Hạn chế DOM injection sinks được hỗ trợ | Sanitization/validation |

Spring Security thường cung cấp một số headers mặc định, nhưng **không tự phát sinh CSP phù hợp**. HSTS phải áp dụng trên HTTPS; không bật `upgrade-insecure-requests` trong demo HTTP localhost rồi coi đó là thay thế TLS configuration.

## 15. Các lỗi cấu hình CSP thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Script có nonce vẫn không chạy | Header nonce khác HTML | Tạo một nonce và dùng lại trong một response |
| Nonce luôn giống nhau | Sinh lúc startup hoặc cache một giá trị | CSPRNG mỗi HTML response |
| Script bất kỳ chạy dù thiếu nonce | Policy có `'unsafe-inline'` hoặc nguồn rộng | Siết `script-src`, bỏ unsafe-inline |
| Mọi inline script đều bị chặn | `default-src 'none'` nhưng thiếu `script-src` | Cho phép nonce/hash của script tin cậy |
| Styles bị mất | `style-src 'none'` chặn CSS | Cho phép đúng stylesheet/nonce style |
| External JS cùng origin không tải | Nonce policy không tự cho `'self'` | Gắn nonce vào script tin cậy hoặc chọn policy khác |
| Report-only mà không thấy chặn | Đúng thiết kế: chỉ ghi nhận | Chuyển sang enforce sau QA |
| CSP có hai giá trị khác nhau | Proxy và app cùng thêm header | Tổ chức ownership hoặc kiểm tra giao nhau |
| JS có nonce vẫn DOM-XSS | Trusted script dùng `innerHTML` | Sửa dangerous sink bằng safe DOM APIs |
| CDN gây mismatch | Body nonce A, header nonce B | Cache/render đồng bộ |
| Một trang không có CSP | Đi filter chain/route khác | Kiểm tra toàn bộ HTML docs |
| Browser nhìn thấy CSP violation | Policy chặn tài nguyên chưa cho phép | Phân loại script hợp lệ/không hợp lệ trước khi sửa |
| `frame-ancestors 'none'` ngăn iframe cần thiết | Chưa xác định embed requirements | Mở origin cần thiết một cách có chủ đích |
| AJAX/WebSocket bị chặn | `connect-src` thiếu URL hợp lệ | Liệt kê API/WSS thật |
| CSP report spam | Không rate limit/report filtering | Sampling và kiểm soát endpoint |
| CSP trên Servlet API trong app WebFlux | Nhầm `HttpSecurity` với `ServerHttpSecurity` | Dùng reactive DSL |
| Test HTTP PASS nhưng browser fail | Test không chạy JS | Thêm browser E2E và DevTools checks |

## 16. Checklist review và tự kiểm tra

### Checklist trước khi production

- [ ] Application dùng đúng **WebFlux** và security chain phù hợp.
- [ ] CSP được thiết kế rõ; không giả định Spring Security tự thêm.
- [ ] Có một owner cho CSP header của mỗi document, không trùng policies ngoài ý định.
- [ ] `script-src` không rộng tùy tiện; hạn chế `'unsafe-inline'` và `'unsafe-eval'`.
- [ ] Nonce từ CSPRNG có **≥128 bit entropy**, tạo mới cho mỗi HTML response.
- [ ] Header nonce và thuộc tính nonce trong HTML khớp trong cùng response.
- [ ] Nonce không được tự gắn cho script do user control.
- [ ] HTML text/attribute/JS/URL/CSS có output encoding đúng context.
- [ ] Không dùng `innerHTML` với input không tin cậy; nếu rich HTML thì sanitize.
- [ ] `object-src`, `base-uri`, `frame-ancestors`, `form-action`, `connect-src` được kiểm tra.
- [ ] Các scripts có nonce được review để tránh dynamic-loader gadget.
- [ ] HTML caches/CDN/proxy không gây mismatch.
- [ ] CSP Report-Only migration và endpoint reports có quyền truy cập/retention/rate limit.
- [ ] HTTPS/TLS, HSTS, nosniff, cookies, CSRF, CORS và authentication vẫn được rà soát riêng.
- [ ] Test response header/body và browser E2E (trong browsers được hỗ trợ).
- [ ] Login/error pages, multiple chains, SSR và SPA documents đều được kiểm thử CSP.

### Câu hỏi ôn tập

**1. CSP do ai thực thi?**  
Browser thực thi policy do server gửi bằng response header; CSP không tự kiểm tra quyền API server-side.

**2. Spring Security reactive có CSP mặc định không?**  
Không. Ứng dụng tự cung cấp policy phù hợp.

**3. Enforce khác Report-Only thế nào?**  
Enforce chặn vi phạm; Report-Only ghi nhận/report mà không chặn vì policy đó.

**4. Nonce cần có entropy tối thiểu bao nhiêu?**  
Ít nhất 128 bit; ví dụ demo dùng 192 bit từ `SecureRandom`.

**5. Một nonce có được dùng cho mọi response không?**  
Không. Sinh mới mỗi HTML response, nhưng dùng cùng nonce cho header và các trusted scripts thuộc chính response đó.

**6. `script-src 'nonce-abc'` cần HTML gì?**  
Một thẻ script có thuộc tính `nonce="abc"`, và không bị policy khác chặn.

**7. Tại sao nonce không phải password?**  
Nó có mặt trong HTML/DOM, được thiết kế để khó đoán **trước khi response được dựng**, không phải secret vĩnh viễn.

**8. Vì sao không tự thêm nonce vào mọi script tag?**  
Có thể cấp nonce cho script attacker inject sau khi HTML bị ghép từ input không tin cậy.

**9. CSP có thay `HtmlUtils.htmlEscape` không?**  
Không. Output encoding đúng context là tuyến phòng thủ chính.

**10. `innerHTML=userInput` có an toàn nếu nằm trong script có nonce?**  
Không. Trusted script vẫn có thể tạo DOM XSS; dùng `textContent` hoặc sanitize.

**11. `'strict-dynamic'` làm gì?**  
Có thể cho scripts được nonce/hash cấp trust load scripts tiếp theo; nguy hiểm nếu loader dùng URL từ input không tin cậy.

**12. `frame-ancestors` và `frame-src` giống nhau không?**  
Không. Một cái kiểm soát ai được nhúng trang, một cái kiểm soát trang được nhúng tài nguyên nào.

**13. Vì sao WebTestClient test CSP chưa đủ?**  
WebTestClient không thực thi JavaScript/CSP browser semantics; cần browser E2E.

**14. CSP có ngăn user không đăng nhập gọi API không?**  
Không. Cần Spring Security authentication/authorization.

**15. Có nên bật `'unsafe-inline'` khi một script hợp lệ bị chặn không?**  
Không như sửa nhanh mặc định. Kiểm tra nonce/header mismatch hoặc refactor script.

**16. Một CSP của proxy và một CSP của app có thể mâu thuẫn không?**  
Có. Enforced policies phải đều được thỏa; một policy có thể chặn nguồn policy kia cho phép.

**17. Report CSP vi phạm có chứa thông tin nhạy cảm không?**  
Có thể có URLs, resource info, sample source; cần redact và giới hạn nơi nhận.

**18. CSP có thay HTTPS không?**  
Không. TLS bảo vệ đường truyền; CSP kiểm soát một số hành vi nội dung trong browser.

### Bài tập thực hành

1. Chạy demo, lấy hai response `/page`; xác nhận nonce mới mỗi lần và header/body khớp trong từng response.
2. Thay thuộc tính nonce trong HTML bằng giá trị sai **chỉ trên bản sao môi trường học**, xác nhận browser chặn script.
3. Thử query `name` chứa HTML, quan sát `&lt;`/`&gt;` và giải thích output encoding.
4. Đổi CSP sang `script-src 'self'` và quan sát inline trusted script không tự được chạy.
5. Thêm stylesheet local; thiết kế `style-src` cụ thể để trang hoạt động mà không dùng wildcard.
6. Viết test bảo đảm policy không có `'unsafe-inline'`/`'unsafe-eval'`.
7. Dùng browser E2E xác nhận script hợp lệ chạy, inline event handler không được phép.
8. So sánh hash CSP cho inline bootstrap tĩnh với nonce CSP cho HTML động qua CDN.
9. Thiết kế Report-Only policy, endpoint nhận reports và cơ chế rate limit/redaction.
10. Vẽ sơ đồ request-scoped nonce qua WebFilter → template → header và chỉ ra nơi có thể sinh nonce trùng.
11. Review một script loader `'strict-dynamic'` lấy URL từ query param; chỉ ra rủi ro và cách sửa.
12. Thêm API giới hạn theo role, chứng minh CSP không thay method security.
13. Kiểm tra proxy có thêm CSP khác gây chặn script không.
14. Xây checklist cho login/error pages, không chỉ trang chính.

## 17. Tài liệu tham khảo

- [Spring Security — WebFlux HTTP response headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): CSP không có mặc định; cách cấu hình `contentSecurityPolicy` và Report-Only.
- [Spring Security — WebFlux configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, security filters.
- [Spring Security 6.3 API — ServerHttpSecurity.HeaderSpec](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html): API CSP header DSL.
- [MDN — CSP guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): nonce/hash, strict CSP, `'strict-dynamic'`, Report-Only.
- [MDN — HTML nonce attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/nonce): nonce ít nhất 128 bit, dùng một lần và khớp header/script.
- [MDN — Content-Security-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): directive và source expressions.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): context-aware encoding, sanitization, dangerous sinks và CSP defense-in-depth.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): chiến lược CSP trong thực tế.
- [W3C — CSP Level 3](https://www.w3.org/TR/CSP3/): tiêu chuẩn CSP.
- [Spring Framework — HtmlUtils](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/util/HtmlUtils.html): HTML text escaping.

**Ghi nhớ:** Với **Content-Security-Policy** trong Spring Security reactive, dùng CSP để **giảm nguy cơ XSS**, không để thay **output encoding/sanitization**. Nếu dùng nonce, server phải sinh nonce mới bằng **CSPRNG cho mỗi HTML response** và dùng đúng giá trị đó trong **CSP header + những script được tin cậy**; tránh `'unsafe-inline'`, tránh cấp nonce cho dữ liệu người dùng và kiểm soát cache/CDN. Vẫn phải bảo vệ bằng **HTTPS, authentication, authorization, CSRF và safe DOM APIs**.