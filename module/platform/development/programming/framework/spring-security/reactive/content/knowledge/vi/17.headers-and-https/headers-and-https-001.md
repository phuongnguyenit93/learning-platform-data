# Các header bảo mật mặc định trong Spring Security reactive

> **Bối cảnh:** Spring Security 6.x trên Spring WebFlux, Java 17+, Spring Boot 3.3.x. Bài tập trung vào **HTTP response security headers được Spring Security WebFlux tự thêm**, ý nghĩa, điều kiện xuất hiện, cách giữ/tùy chỉnh từng header, và cách kiểm thử trên ứng dụng reactive. Cú pháp ví dụ sử dụng Spring Boot 3.3.13 để minh họa API; khi triển khai thật cần nâng cấp lên bản Spring Security/Spring Framework còn được hỗ trợ và đã vá bảo mật.

## 1. Header bảo mật là gì?

Mỗi HTTP response có một nhóm header cho biết trình duyệt và client phải xử lý nội dung thế nào. Một số header tạo ra **ràng buộc bảo vệ ở phía trình duyệt**:

- Không lưu bản sao nhạy cảm vào cache.
- Không suy đoán loại nội dung không đúng với `Content-Type`.
- Hạn chế trang bị nhúng trong `iframe`.
- Khuyến khích trình duyệt chỉ dùng HTTPS với host đã thiết lập HSTS.
- Hạn chế hoặc chỉ rõ nguồn script, style, ảnh, frame, camera, geolocation... **khi ứng dụng tự cấu hình thêm** các policy tương ứng.

Trong Spring Security WebFlux, các header này được cấu hình qua `ServerHttpSecurity.headers(...)` và ghi bởi các `ServerHttpHeadersWriter` trong hệ thống `SecurityWebFilterChain`.

```text
HTTP request
    |
    v
WebFlux / WebFilterChainProxy
    |
    +--> SecurityWebFilterChain (được chọn theo securityMatcher)
             |
             +--> Header writers của Spring Security
             |       +-- Cache-Control / Pragma / Expires
             |       +-- X-Content-Type-Options
             |       +-- X-Frame-Options
             |       +-- X-XSS-Protection
             |       +-- HSTS (chỉ khi request được xem là secure)
             |
             +--> Authentication / Authorization / CSRF ...
             |
             v
         Controller hoặc lỗi 401/403
             |
             v
         HTTP response + headers nếu chain/response cho phép
```

Điều quan trọng: **security headers không phải cơ chế xác thực hay phân quyền**. `X-Frame-Options: DENY` không tự chặn `GET /admin` đối với người thiếu quyền. `Strict-Transport-Security` cũng không tự bật TLS cho Netty hoặc buộc Spring Security redirect mọi request HTTP sang HTTPS. Phải cấu hình các lớp đó riêng.

### Thuật ngữ dễ nhầm

| Thuật ngữ | Vai trò | Ví dụ |
|---|---|---|
| **Response header** | Server trả về, client đọc | `X-Content-Type-Options: nosniff` |
| **Request header** | Client gửi vào server | `Accept: application/json`, `Authorization: Bearer ...` |
| **SecurityWebFilterChain** | Tập filter áp dụng cho request WebFlux | Bean trả `SecurityWebFilterChain` |
| **Header writer** | Thành phần tạo/thêm response header | `XFrameOptionsServerHttpHeadersWriter` |
| **Security policy HTTP** | Rule cấp phép route, user, method | `authorizeExchange(...).hasRole("ADMIN")` |
| **HTTPS redirect** | Phản hồi redirect từ HTTP đến HTTPS | `redirectToHttps(Customizer.withDefaults())` |
| **HSTS** | Browser ghi nhớ host nên dùng HTTPS về sau | `Strict-Transport-Security` |

Một header xuất hiện trong response không chứng minh ứng dụng an toàn toàn diện. Header chỉ là một lớp phòng vệ trong mô hình gồm HTTPS, authorization, CSRF, XSS prevention, quản lý cookie, input validation và patching.

## 2. Danh sách header mặc định của Spring Security WebFlux

Theo danh sách mặc định trong Javadoc `ServerHttpSecurity.headers(...)` của Spring Security 6.x, response đi qua Security chain thường nhận:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

**Lưu ý quyết định:** header `Strict-Transport-Security` **chỉ được thêm khi request được nhận diện là HTTPS/secure**. Vì vậy response trên `http://localhost:8080` thường có sáu header còn lại, **không** có HSTS. Đây không phải lỗi cấu hình mặc định.

Bảng chi tiết:

| Header | Giá trị mặc định theo danh sách Spring Security 6.x | Mục đích | Điều kiện/lưu ý |
|---|---|---|---|
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` | Ngăn cache vô tình lưu response nhạy cảm | Có thể được application ghi giá trị riêng cho resource công khai |
| `Pragma` | `no-cache` | Tương thích client/cache cũ | Đi kèm chính sách cache mặc định |
| `Expires` | `0` | Nêu response đã hết hạn dùng cache | Không phải thời gian hết hạn token/session |
| `X-Content-Type-Options` | `nosniff` | Hạn chế MIME/content sniffing | Cần gửi `Content-Type` đúng cho resource |
| `X-Frame-Options` | `DENY` | Hạn chế clickjacking bằng iframe | Đổi `SAMEORIGIN` khi có yêu cầu nhúng cùng origin được đánh giá |
| `X-XSS-Protection` | `0` | Tắt XSS Auditor cũ không đáng tin | **Không** đồng nghĩa đã chống XSS |
| `Strict-Transport-Security` | `max-age=31536000 ; includeSubDomains` | HSTS: browser dùng HTTPS sau khi đã nhận policy | **Chỉ trên secure request**; `preload` không mặc định |

**Không kết luận rằng mọi response HTTP ngoài thế giới thực luôn có y hệt bảng trên.** Cấu hình `SecurityWebFilterChain`, proxy/CDN, version Spring Security, resource riêng, filter bổ sung hoặc ứng dụng tự đặt header có thể thay đổi kết quả. Đối chiếu **dependency đang chạy** với integration test và HTTP response thật.

### Trường hợp đặc biệt: Referrer-Policy theo phiên bản và tài liệu

Có điểm dễ bị hiểu sai khi chỉ nhìn tài liệu:

- Danh sách default headers trong Javadoc `ServerHttpSecurity.headers(...)` Spring Security 6.x gồm các header ở trên, **không liệt kê `Referrer-Policy`**.
- Trang hướng dẫn **WebFlux Spring Security 6.5** có mô tả `Referrer-Policy: no-referrer` như một hành vi mặc định của nhánh reactive.
- Tài liệu **Servlet** ở các phiên bản tương tự lại nói `Referrer-Policy` không được tự thêm.

Vì vậy, **không tự suy** chỉ từ bảng tổng quát rằng có/không có `Referrer-Policy` ở mọi version. Muốn một chính sách được đảm bảo ở deployment, hãy **cấu hình `referrerPolicy(...)` tường minh** và kiểm thử HTTP response thực tế. Không dùng khác biệt tài liệu làm cớ tắt các header bảo vệ khác.

### Không phải mọi security-related header đều mặc định

Spring Security có API cấu hình thêm, nhưng **không mặc định phát mọi policy sau**:

- `Content-Security-Policy` (CSP), `Content-Security-Policy-Report-Only`.
- `Permissions-Policy`.
- `Cross-Origin-Opener-Policy` (COOP).
- `Cross-Origin-Embedder-Policy` (COEP).
- `Cross-Origin-Resource-Policy` (CORP).
- `Feature-Policy` (legacy, được Permissions-Policy thay thế trong nhiều ngữ cảnh).
- `Access-Control-Allow-Origin`/`Access-Control-Allow-Methods`: là CORS response headers **phụ thuộc request và CORS policy**, không thuộc danh sách security default kể trên.
- `Set-Cookie: ...; Secure; HttpOnly; SameSite=...`: được quản lý bởi session/cookie/authentication/các framework liên quan, không tự có chỉ vì gọi `headers(...)`.

Trong cấu hình chính xác của bạn, một header bổ sung có thể do framework khác hoặc reverse proxy thêm; hãy phân biệt **ai là chủ sở hữu policy**, tránh một nơi ghi đè nơi khác.

## 3. Cache-Control, Pragma, Expires: tránh cache dữ liệu riêng tư

### 3.1 Vì sao mặc định không cho cache?

Giả sử một người dùng đăng nhập, tải trang sao kê, rồi logout. Nếu browser/proxy lưu bản sao trang đó như public cache, một người khác dùng lại máy hoặc một client khác có thể xem được dữ liệu đáng ra đã được bảo vệ.

Spring Security mặc định dùng:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

- `no-store`: yêu cầu cache không lưu bản sao response.
- `no-cache`: cho phép một số cache lưu nhưng cần revalidate trước khi dùng (theo HTTP semantics). **Không đồng nghĩa tuyệt đối với “không lưu”**; `no-store` là thành phần quan trọng trong chính sách này.
- `max-age=0`: response cũ ngay lập tức cần được xem là stale.
- `must-revalidate`: khi stale, cache phải tái xác nhận theo cơ chế hợp lệ.
- `Pragma` và `Expires` bổ trợ cho các client/proxy đời cũ.

Các directive này áp dụng cho **response**, không tự xóa cookie, kết thúc session, thu hồi JWT hoặc ngăn mọi hình thức lưu trữ phía client. Sau logout, backend vẫn phải vô hiệu hóa session/token đúng chính sách.

### 3.2 Resource công khai có thể cache được

Một file JavaScript versioned, ảnh công khai hoặc trang cacheable thực sự có thể dùng:

```http
Cache-Control: public, max-age=300
```

Spring Security có thể để ứng dụng **ghi Cache-Control riêng** cho response đó thay cho default. Ví dụ trong WebFlux:

```java
@GetMapping("/api/public-cache")
public Mono<ResponseEntity<String>> cacheablePublic() {
    return Mono.just(
        ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .body("public-cache"));
}
```

Đây là **method minh họa**, cần import `GetMapping`, `Mono`, `ResponseEntity` và `HttpHeaders`. Trong demo đầy đủ ở mục 8 có method tương ứng.

**Đừng** trả `public` cache cho tài nguyên có chứa dữ liệu theo user, cookie/session, kết quả permission hoặc token. Với nội dung không công khai, ưu tiên giữ `no-store`. Nếu một reverse proxy cache theo route, cần thêm chính sách `Vary` và cache key phù hợp; đừng trông chờ header Spring Security tự sửa cấu hình cache CDN sai.

### 3.3 Khi nào có thể tắt cache header writer?

Spring Security cho phép:

```java
.headers(headers -> headers
    .cache(cache -> cache.disable()))
```

Đây là **mảnh DSL**, không nên copy vào production chỉ vì muốn cache một file static. Tắt `cache` writer có thể ảnh hưởng **toàn bộ response thuộc chain đó**. Thường ưu tiên đặt `Cache-Control` riêng cho đúng những endpoint/resource công khai hoặc cấu hình resource chain chuyên biệt.

## 4. X-Content-Type-Options: nosniff

`X-Content-Type-Options: nosniff` hướng trình duyệt không “đoán” content type trong các ngữ cảnh được hỗ trợ. Trước đây một server có thể gửi file do user upload với loại MIME sai, browser suy diễn nó thành JavaScript/HTML và khiến code không đáng tin bị thực thi.

```http
Content-Type: application/json
X-Content-Type-Options: nosniff
```

Hai header phục vụ hai việc:

1. `Content-Type`: server tuyên bố dữ liệu là JSON.
2. `X-Content-Type-Options`: hạn chế browser tự sniff sang loại nội dung khác.

**Không được hiểu `nosniff` tự gán Content-Type đúng.** Hãy gửi MIME type chuẩn cho JavaScript/CSS, không phục vụ upload nhạy cảm cùng origin mà browser có thể coi là script/HTML; cân nhắc domain riêng cho file người dùng tải lên và `Content-Disposition: attachment` khi thích hợp.

Nếu cần vô hiệu hóa:

```java
.headers(headers -> headers
    .contentTypeOptions(options -> options.disable()))
```

Chỉ dùng khi đã xác định một ràng buộc tương thích thật sự và hiểu rủi ro. Bài học **không khuyến nghị** tắt `nosniff` để chữa lỗi MIME: sửa MIME sẽ an toàn hơn.

## 5. X-Frame-Options: DENY

### 5.1 Clickjacking

Một attacker có thể nhúng trang quan trọng của bạn trong `iframe`, đặt lớp phủ giao diện khiến người dùng tưởng bấm nút vô hại trong khi thực chất tương tác với trang nhạy cảm.

Mặc định:

```http
X-Frame-Options: DENY
```

Nghĩa là browser hỗ trợ header này không cho render response trong frame. Chính sách này hữu ích cho trang đăng nhập, trang quản lý tài khoản, console admin, giao dịch...

Khi ứng dụng **cần** nhúng một số trang trong iframe **cùng origin**, có thể chọn:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN)))
```

Import:

```java
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
```

**SAMEORIGIN không có nghĩa “cho phép mọi iframe trong tổ chức”.** Nó bị giới hạn bởi quy tắc same-origin (scheme + host + port). Một website khác subdomain hoặc khác scheme có thể không được xem là cùng origin.

### 5.2 CSP frame-ancestors linh hoạt hơn

Khi cần cho phép một domain khác nhúng trang, `X-Frame-Options` không có cú pháp hiện đại tương đương allowlist nhiều origin. Dùng **Content-Security-Policy: frame-ancestors ...** để khai báo chính sách theo các origin được tin cậy:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
```

Lưu ý:

- CSP không được tự sinh chỉ vì có `X-Frame-Options`.
- Browser cũ và mới có mức hỗ trợ khác nhau; kiểm chứng kết hợp CSP/`X-Frame-Options` khi cần nhúng khác origin.
- Đừng bỏ `DENY` toàn cục chỉ để sửa một trường hợp embed; cân nhắc route-specific policy/chain và threat model.
- `frame-ancestors` kiểm **ai được nhúng trang của bạn**, khác với `frame-src` hoặc `child-src` quy định trang của bạn được nhúng nội dung ở đâu.

## 6. Strict-Transport-Security: HSTS chỉ trên HTTPS

### 6.1 HSTS làm gì?

Header:

```http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

yêu cầu browser hỗ trợ HSTS ghi nhớ rằng host này chỉ nên được kết nối qua HTTPS trong thời gian quy định. `31536000` giây xấp xỉ **một năm**; `includeSubDomains` mở chính sách xuống các subdomain.

**Điều kiện quan trọng:**

- Spring Security mặc định chỉ thêm HSTS **khi request được đánh giá là secure/HTTPS**.
- Browser chỉ học HSTS từ một **HTTPS response được tin cậy**, không học header từ HTTP plain text.
- HSTS không mở một HTTPS listener. Ứng dụng hoặc reverse proxy phải thật sự phục vụ TLS và certificate hợp lệ.
- HSTS không thể sửa một request HTTP đầu tiên nếu browser chưa biết host; preload có thể giải quyết một số tình huống nhưng cần điều kiện và cam kết vận hành riêng.

```text
Lần đầu chưa biết HSTS:
  browser -> https://shop.example.com
       -> TLS OK -> response HSTS -> browser ghi nhớ host

Lần sau:
  user gõ http://shop.example.com
       -> browser nhớ HSTS -> tự dùng HTTPS trước khi gửi dữ liệu
```

### 6.2 HSTS không thay redirectToHttps

`ServerHttpSecurity.redirectToHttps(...)` có thể cấu hình redirect request HTTP sang HTTPS. **Đây không phải header HSTS**. Một cấu hình có redirect nhưng không có HTTPS/TLS đúng vẫn lỗi; HSTS chỉ có ý nghĩa khi response truyền qua HTTPS an toàn.

Mảnh cấu hình:

```java
// Chỉ bật khi hệ thống TLS/proxy thực sự sẵn sàng.
http.redirectToHttps(Customizer.withDefaults());
```

Không bật redirect này trong ví dụ localhost HTTP nếu chưa chuẩn bị endpoint HTTPS: dễ tạo redirect đến port không có dịch vụ.

### 6.3 Tùy chỉnh max-age, subdomain và preload

DSL Spring Security WebFlux:

```java
.headers(headers -> headers
    .hsts(hsts -> hsts
        .maxAge(Duration.ofDays(180))
        .includeSubdomains(false)
        .preload(false)))
```

Cần import `java.time.Duration` và đặt trong `ServerHttpSecurity` chain.

- `maxAge(Duration.ofDays(180))`: policy thử nghiệm/vận hành với thời hạn đã chọn; **không** phải giá trị mặc định.
- `includeSubdomains(false)`: không buộc các subdomain cùng áp dụng theo HSTS policy; điều này khác default minh họa.
- `preload(false)`: không yêu cầu header có directive preload.

**Mặc định trong Javadoc HstsSpec:** một năm, bao gồm subdomain, `preload=false`. Vì vậy **không khẳng định Spring Security mặc định gửi `preload`** mặc dù một số snippet tài liệu tổng quát minh họa `; preload`.

### 6.4 Cẩn trọng với includeSubDomains và preload

HSTS có thể kéo dài sau khi bạn deploy/ngắt dịch vụ. Nếu một subdomain phụ thuộc HTTP (legacy, nội bộ, service cũ), bật `includeSubDomains` trên domain cha có thể khiến người dùng không truy cập được nó bằng HTTP.

Nếu đăng ký **HSTS preload**, còn có quy trình/chính sách browser vendor riêng và việc gỡ khỏi preload list khó hoặc mất thời gian. Không bật `preload(true)` chỉ để “tăng điểm” security scanner. Trước đó cần bảo đảm HTTPS với certificate hợp lệ cho tất cả subdomain liên quan và có vận hành dài hạn.

### 6.5 Reverse proxy và TLS termination

Mô hình thường gặp:

```text
Browser --HTTPS--> Reverse Proxy/Load Balancer --HTTP--> Spring WebFlux
                       |
                  TLS kết thúc ở đây
```

Nếu Spring WebFlux chỉ thấy request từ proxy là `http://...`, header writer HSTS có thể **không nhận ra request bên ngoài là HTTPS** và không phát HSTS. Ngược lại, tự tin vào `X-Forwarded-Proto: https` do người dùng Internet gửi có thể tạo vấn đề spoofing/redirect/scheme.

Một chiến lược Spring Boot khi **đứng sau proxy đáng tin**:

```yaml
server:
  forward-headers-strategy: framework
```

Bật và cấu hình forwarding headers chỉ khi reverse proxy **loại bỏ/ghi đè các header forwarding do client gửi**, xác định các hop đáng tin. Xem tài liệu WebFlux `ForwardedHeaderTransformer` và Spring Boot. Cũng có thể cấu hình HSTS ở **proxy** thay vì app; nếu vậy phải thống nhất người chịu trách nhiệm và test HTTPS response từ Internet thật.

**Test quan trọng:** kiểm HTTPS production và HTTP localhost/staging riêng; `X-Forwarded-Proto` không phải cơ chế cấp quyền và không thay TLS.

## 7. X-XSS-Protection: 0 không có nghĩa vô hiệu hóa an toàn XSS

Mặc định được liệt kê:

```http
X-XSS-Protection: 0
```

Header này liên quan đến XSS Auditor/filter cũ của browser. Các cơ chế đó có lịch sử gây lỗi hoặc hành vi không đáng tin; browser hiện đại đã loại bỏ/hạn chế hỗ trợ. Giá trị `0` hướng browser cũ **tắt** filter, không có nghĩa Spring Security đang bật lớp chống XSS “cấp cao”.

**Cần làm để chống XSS thật sự:**

- Escape output theo ngữ cảnh HTML/attribute/URL/JavaScript.
- Dùng template engine an toàn và tránh dựng HTML từ user input chưa encode.
- Không dùng `innerHTML` hoặc HTML injection không kiểm soát.
- Đặt CSP phù hợp ứng dụng và giảm `unsafe-inline`.
- Quản lý script dependencies, integrity, trusted code, upload boundaries.
- Kiểm tra các route có JSON/HTML đúng `Content-Type` và `nosniff`.

Có thể điều chỉnh header writer (ít khi cần):

```java
.headers(headers -> headers
    .xssProtection(xss -> xss.disable()))
```

Đừng đổi thành `X-XSS-Protection: 1; mode=block` chỉ vì nghe “1 là bật nên an toàn hơn”; hãy xem browser support và khuyến nghị hiện hành. Trong đa số dự án hiện đại, chính sách CSP/output encoding có giá trị hơn XSS Auditor legacy.

## 8. Dự án Java 17+ chạy được: nhìn đúng header mặc định

Dự án nhỏ dùng Spring WebFlux và Spring Security, có ba endpoint: public, public cache có chủ đích và private/admin. **Không tùy chỉnh `headers(...)`** để test đúng **mặc định** của Spring Security 6.3.x.

### 8.1 Cấu trúc

```text
webflux-security-headers/
  settings.gradle
  build.gradle
  src/main/java/demo/headers/HeadersApplication.java
  src/main/java/demo/headers/SecurityConfiguration.java
  src/main/java/demo/headers/ApiController.java
  src/test/java/demo/headers/DefaultHeadersTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-security-headers'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.headers'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-webflux` tạo reactive HTTP server; không khai báo `spring-boot-starter-web` của Servlet.
- `spring-boot-starter-security` áp dụng WebFlux Security, default header writers, Basic authentication.
- Test dùng Spring Boot Test và WebTestClient.
- Gradle/JDK cần tương thích với Spring Boot 3.3.13. Bản 3.3.x chỉ để học API; không chọn làm production release chưa được vá năm 2026.

### 8.2 Spring Boot application

**src/main/java/demo/headers/HeadersApplication.java**

```java
package demo.headers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeadersApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeadersApplication.class, args);
    }
}
```

### 8.3 SecurityConfiguration: giữ nguyên header defaults

**src/main/java/demo/headers/SecurityConfiguration.java**

```java
package demo.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-only-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/public-cache")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // Chỉ diễn đạt rõ việc giữ cấu hình header mặc định:
            .headers(Customizer.withDefaults())
            .build();
    }
}
```

Điểm cần hiểu:

1. `@EnableWebFluxSecurity` áp dụng Security WebFilter cho WebFlux, không dùng `@EnableWebSecurity` kiểu Servlet.
2. `headers(Customizer.withDefaults())` giữ chính sách header mặc định, **không tự chọn custom CSP**. Có thể bỏ dòng này trong cấu hình minimal nếu không cần diễn đạt tường minh.
3. `/api/public` và `/api/public-cache` không yêu cầu login. **`permitAll()` không vô hiệu hóa header writers**; response public vẫn nhận header security phù hợp.
4. `/api/private` cần authentication, `/api/admin` cần `ROLE_ADMIN`.
5. HTTP Basic dùng để kiểm thử response 401/200/403. Password chỉ là credential demo, được hash bằng BCrypt.
6. `formLogin(disable)` tránh redirect login HTML trong demo API; không liên quan đến header default.
7. Mặc định của Spring Security WebFlux còn có **CSRF protection**. Demo chỉ dùng GET; khi thêm POST/PUT/PATCH/DELETE trong browser/cookie-based app, phải xem xét CSRF thay vì tắt để “sửa lỗi 403”.

### 8.4 Controller

**src/main/java/demo/headers/ApiController.java**

```java
package demo.headers;

import java.security.Principal;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/public-cache")
    public Mono<ResponseEntity<String>> publicCache() {
        return Mono.just(ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .body("public-cache"));
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo(Principal principal) {
        return Mono.just("hello " + principal.getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin");
    }
}
```

Bản demo chủ động viết Cache-Control cho route **công khai và không chứa dữ liệu người dùng**. Vì Spring Security tránh ghi đè response đã có Cache-Control do ứng dụng đặt, nó minh họa cách cho cache có chọn lọc mà không tắt toàn bộ header writers.

### 8.5 Chạy thử bằng curl

Tại thư mục dự án (JDK 17+ và Gradle tương thích):

```bash
gradle bootRun
```

Nếu có Gradle Wrapper phù hợp, dùng `./gradlew bootRun`; trên Windows dùng `gradlew.bat bootRun`.

Mở terminal khác:

```bash
# Public, response 200 với các header mặc định:
curl -i http://localhost:8080/api/public

# Resource công khai có Cache-Control riêng:
curl -i http://localhost:8080/api/public-cache

# Chưa xác thực: response 401 + challenge HTTP Basic:
curl -i http://localhost:8080/api/private

# Curl yêu cầu password khi -u chỉ có username;
# nhập dev-only-password tại prompt:
curl -i -u alice http://localhost:8080/api/private

# Alice không có ROLE_ADMIN: 403:
curl -i -u alice http://localhost:8080/api/admin

# Admin hợp lệ: nhập dev-admin-password tại prompt:
curl -i -u admin http://localhost:8080/api/admin
```

Windows PowerShell có thể cần `curl.exe` khi `curl` là alias. Không gắn password vào URL hay lưu credential thật trong shell history.

**Quan sát trên `http://localhost`:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0` và nhóm no-cache sẽ được mong đợi; **không yêu cầu thấy `Strict-Transport-Security` vì request chưa phải HTTPS**. Một số response có thể có header khác do Netty, Spring WebFlux hoặc thư viện khác.

### 8.6 Kiểm thử tự động WebTestClient

**src/test/java/demo/headers/DefaultHeadersTest.java**

```java
package demo.headers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DefaultHeadersTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicResponseHasDefaultHeaders() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .expectHeader().valueEquals("Pragma", "no-cache")
            .expectHeader().valueEquals("Expires", "0")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueEquals(
                "X-XSS-Protection", "0");
    }

    @Test
    void hstsIsNotAddedOnPlainHttp() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Strict-Transport-Security");
    }

    @Test
    void cspIsNotAutomicallyAdded() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Content-Security-Policy")
            .expectHeader().doesNotExist(
                "Permissions-Policy");
    }

    @Test
    void applicationCanOverrideCacheForPublicResource() {
        client.get().uri("/api/public-cache")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }

    @Test
    void missingCredentialIsUnauthorized() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");
    }

    @Test
    void privateDataHasCacheProtection() {
        client.get().uri("/api/private")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .expectBody(String.class).isEqualTo("hello alice");
    }

    @Test
    void unauthorizedRoleStillCannotSeeAdmin() {
        client.get().uri("/api/admin")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessProtectedRoute() {
        client.get().uri("/api/admin")
            .headers(h ->
                h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }
}
```

Đây là **8 phương thức test** nhằm chứng minh:

- Mặc định header no-cache/nosniff/frame/XSS header được sinh cho resource public.
- HSTS **không xuất hiện** trên HTTP thật của test server.
- CSP/Permissions-Policy **không tự được thêm** vào response bởi cấu hình mặc định.
- `Cache-Control` riêng của resource public có thể được giữ, trong khi `nosniff` vẫn còn.
- Authentication/authorization hoạt động **độc lập** với header, cả 401, 403 và 200.
- Dữ liệu private vẫn nhận chính sách chống cache mặc định.

Chạy:

```bash
gradle test
```

**Lưu ý:** đây là kết quả dự kiến sau khi rà soát code và Javadoc, **không phải log build/test đã thực thi**. Nếu dùng phiên bản Spring Security/Netty khác, hãy xác minh giá trị từng header. Test `Referrer-Policy` không được ép mặc định vì có khác biệt tài liệu như mục 2; nếu ứng dụng cần chính sách đó, cấu hình tường minh và thêm test.

### 8.7 Test HSTS trên HTTPS thật

Test ở mục 8.6 chỉ chạy HTTP. Để kiểm HSTS:

1. Dựng TLS trên Netty hoặc reverse proxy với chứng chỉ hợp lệ trên môi trường staging.
2. Truy cập endpoint **qua HTTPS** thực tế từ client/browser.
3. Quan sát header và xác nhận không có proxy đang xóa/ghi đè sai.
4. Nếu dùng HTTPS termination ở proxy, xác nhận forwarded headers/scheme được nhận diện đúng hoặc proxy chịu trách nhiệm HSTS.

Ví dụ:

```bash
curl -i https://staging.example.com/api/public
```

Kỳ vọng response qua HTTPS có `Strict-Transport-Security` nếu chính sách mặc định/đã cấu hình còn hiệu lực. **Không dùng `curl -k` làm bằng chứng TLS production an toàn**: bỏ xác minh certificate sẽ che sự cố TLS dù vẫn đọc được header.

## 9. Tùy chỉnh header trong WebFlux DSL

Khi không muốn thay toàn bộ defaults, nên điều chỉnh **chỉ những header cần thiết**:

```java
// Mảnh cấu hình: dùng thay cho .headers(withDefaults())
// trong SecurityWebFilterChain, không lắp cả hai song song.
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .hsts(hsts -> hsts
        .maxAge(Duration.ofDays(180))
        .includeSubdomains(false)
        .preload(false))
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicyServerHttpHeadersWriter
            .ReferrerPolicy.NO_REFERRER))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; "
                + "base-uri 'self'; frame-ancestors 'self'")))
```

Cần imports phù hợp:

```java
import java.time.Duration;
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter;
```

Đây là **đoạn cấu hình tùy chọn**, không phải class hoàn chỉnh. Khi áp dụng:

- `X-Frame-Options` thành `SAMEORIGIN`; cần cho phép nhúng cùng origin thực sự hay không?
- HSTS thành 180 ngày và không mở rộng subdomain; phải xét policy domain.
- `Referrer-Policy: no-referrer` được thêm tường minh bất kể khác biệt default.
- CSP là policy **minh họa**, không chắc phù hợp app SPA đang dùng CDN/inline script/WebSocket. Nếu áp dụng không kiểm thử, CSP có thể chặn chức năng hợp lệ.
- Các default headers khác vẫn được giữ, vì ta **không disable cả `headers`**.

### CSP phải thiết kế theo tài nguyên thực

`Content-Security-Policy` là header bổ sung **không có default policy dùng chung**. Ví dụ:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'
```

Nó hạn chế nguồn resource và cách trang được nhúng. Nhưng một ứng dụng có CDN, font, ảnh hoặc kết nối API khác origin có thể cần các directive riêng như `script-src`, `style-src`, `img-src`, `connect-src`, `font-src`. Không bỏ `default-src` và mở `*` vô hạn để “hết lỗi”. Với deployment lớn, thử `Content-Security-Policy-Report-Only` trước rồi thắt chặt policy.

`frame-ancestors` có thể tương tác với `X-Frame-Options` trên các browser khác nhau; cần test phiên bản browser mục tiêu.

### Permissions-Policy, COOP, COEP, CORP

Những header này được thêm khi app muốn kiểm soát quyền browser features và ranh giới cross-origin. Ví dụ policy riêng:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-site
```

Các dòng trên **chỉ minh họa** một chính sách, **không mặc định** trong demo. Một ứng dụng nhúng SSO/payment iframe hoặc cần tích hợp bên thứ ba phải đánh giá cẩn thận COOP/COEP/CORP để không làm hỏng flow hợp lệ. Chúng không thay thế CORS hay authentication.

### Thay đổi frame policy nhưng giữ default khác

Nếu chỉ cần dùng H2 console hoặc một trang nhúng cùng origin trong môi trường học, có thể cấu hình riêng:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN)))
```

Không dùng `headers(headers -> headers.disable())` chỉ vì một trang cần iframe. Cách đó loại bỏ **toàn bộ** nhóm header bảo vệ của chain.

### Khi muốn tắt toàn bộ header writers

```java
// PHẢN VÍ DỤ: mất toàn bộ header bảo mật của chain.
.headers(headers -> headers.disable())
```

Cấu hình này tắt header writer Spring Security trên chain; chỉ cân nhắc khi một lớp khác đã có responsibility rõ, đã kiểm thử end-to-end và bạn biết chính xác tác động. Với app thông thường, đây là cách sửa quá rộng và nguy hiểm.

## 10. Sự khác biệt giữa WebFlux và Servlet/MVC

| Chủ đề | Reactive/WebFlux | Servlet/MVC |
|---|---|---|
| Builder bảo mật | `ServerHttpSecurity` | `HttpSecurity` |
| Filter chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Bật cấu hình | `@EnableWebFluxSecurity` | `@EnableWebSecurity` |
| Header DSL | `.headers(headers -> ...)` | Có DSL tên tương tự nhưng class/overload khác |
| Header writer API | `ServerHttpHeadersWriter`, reactive response | `HeaderWriter`, Servlet response |
| Request/response | `ServerWebExchange`/`ServerHttpResponse` | `HttpServletRequest`/`HttpServletResponse` |
| HSTS | Dựa trên việc WebFlux request được coi secure | Dựa trên Servlet request secure |
| Proxy forwarding | `ForwardedHeaderTransformer` hoặc tích hợp Boot | `ForwardedHeaderFilter` hoặc container native |
| Header mặc định | Tương đồng danh sách cốt lõi, có thể khác chi tiết/version | Tương đồng cốt lõi; không sao chép class imports |

**Không** copy:

```java
// Chỉ dành cho Servlet; không dùng trong WebFlux:
HttpSecurity http;
SecurityFilterChain chain;
```

rồi mong class này xuất hiện trong reactive configuration. Với cùng tên DSL `headers`, class writer và enum import có thể khác nhau. Ví dụ `XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN` ở WebFlux không phải enum header writer Servlet.

## 11. Lỗi thực tế và phương pháp chẩn đoán

### 11.1 Không thấy bất kỳ header nào

Kiểm tra:

1. Request có đi qua `SecurityWebFilterChain` thực sự không?
2. Có nhiều chain với `securityMatcher`/`@Order`? URL có khớp chain khác, hoặc rơi ngoài tất cả chain?
3. Có ai gọi `headers(headers -> headers.disable())` không?
4. Spring Boot có chọn **WebFlux** đúng không, hay có Spring MVC trên classpath?
5. Reverse proxy/CDN/WebFilter có xóa hoặc ghi đè headers không?
6. Response thuộc luồng error/redirect đặc biệt có đi qua filter writer không?
7. Kiểm lại phiên bản Spring Security và các thay đổi cấu hình sau upgrade.

**Header thiếu không đồng nghĩa route không được bảo vệ**; nhưng là dấu hiệu cần điều tra vì browser protection và cache policy có thể bị mất. Thêm test phát hiện regression.

### 11.2 Thấy đủ header trừ HSTS trên localhost

Đây thường là **đúng mặc định**: localhost dùng HTTP, nên HSTS không được thêm. Dùng HTTPS thật hoặc giả lập request secure trong test được thiết kế đúng. Không sửa bằng cách buộc HSTS gửi trên HTTP; browser sẽ không tin policy HSTS từ HTTP response.

### 11.3 HSTS thiếu sau khi deploy sau reverse proxy

Có thể ứng dụng chỉ thấy HTTP nội bộ do TLS terminate ở proxy. Giải pháp:

- Cấu hình forwarding headers đúng phía proxy và Boot.
- Hoặc cấu hình HSTS ở proxy có trách nhiệm.
- Test từ phía browser qua **HTTPS public endpoint**, không chỉ test nội bộ pod.
- Không tin `X-Forwarded-Proto` từ Internet chưa được proxy xử lý.

### 11.4 Tắt X-Frame-Options để render iframe

Cân nhắc `SAMEORIGIN` nếu đúng nhu cầu. Nếu cần embed từ origin khác, đánh giá `Content-Security-Policy: frame-ancestors ...`, session/cookie SameSite và clickjacking threat model. Đừng tắt tất cả headers.

### 11.5 Static CSS/JS bị “no-cache”

Cache-Control mặc định ưu tiên an toàn. Chọn policy riêng cho các resource công khai, versioned, hoặc cấu hình static resource caching; không disable cache writer toàn cục nếu các API có dữ liệu theo user.

### 11.6 Có nosniff nhưng tải script/style lỗi

Cần sửa server trả đúng `Content-Type` (JavaScript/CSS). `nosniff` đang giúp browser tránh chạy nội dung có MIME sai; tắt nó có thể che bug và mở đường XSS.

### 11.7 Header mới nhưng browser không đổi hành vi

- Browser không hỗ trợ policy tương ứng.
- Policy không có trên **đúng response** mà browser tải.
- Browser có cache/HSTS state cũ hoặc proxy trả response khác.
- Header CSP sai syntax/duplicate; console cho biết directive nào bị chặn.
- `Permissions-Policy`/cross-origin policy không đúng feature hoặc browsing context.
- HSTS chỉ có tác dụng với HTTPS host được browser tin cậy.

### 11.8 Header được phát hai lần

Nếu cả CDN, reverse proxy và ứng dụng cùng thêm CSP/HSTS/X-Frame-Options, có thể xuất hiện duplicate hoặc policy chồng chéo ngoài ý muốn. Nên xác định **single ownership** hoặc hợp đồng hợp nhất rõ: app phụ trách CSP theo route; edge phụ trách HSTS trên public TLS; cả hai được integration test. Không đoán thứ tự browser xử lý khi duplicate.

### 11.9 Lỗi 401/403 không có header đúng

Spring Security filter thường có thể thêm security headers vào các response đi qua chain, bao gồm response error, nhưng filter/commit path và proxy có thể khác. Test trực tiếp cả 200, 401, 403, redirect và lỗi server. Một `@RestControllerAdvice` không phải nơi duy nhất có thể tạo 401/403 vì nhiều lỗi Security đến từ WebFilter trước controller.

### 11.10 Header không giải quyết CSRF, CORS, XSS hay upload một mình

- `X-Content-Type-Options` không thay XSS output encoding.
- `X-Frame-Options` không tự phòng CSRF.
- HSTS không sửa certificate sai/HTTP listener chưa có.
- Cache-Control không tự xóa session/token.
- CSP không được tự tạo và không thay permission check server-side.
- CORS chỉ kiểm cơ chế trình duyệt chia sẻ response, không phải authorization.
- X-XSS-Protection=0 không phải bộ lọc chống XSS.

## 12. Test matrix nên có ở dự án thật

| Kiểu response | Header cần xác minh | Điều kiện |
|---|---|---|
| Public GET 200 | no-cache/nosniff/frame/XSS header mặc định | Nếu không có cache override |
| Private GET 200 | Cache-Control bảo vệ dữ liệu user | Có credentials hợp lệ |
| 401 Basic/Bearer | Security headers + `WWW-Authenticate` đúng scheme | Thiếu/sai credential |
| 403 role/CSRF | Security headers và status 403 thật | Không đủ quyền hoặc CSRF sai |
| 302 login redirect | Cache/security headers khi chain xử lý | Form login/browser |
| Public static asset | Cache-Control công khai đúng resource | Không chứa dữ liệu user |
| HTTPS 200 | HSTS đúng theo policy domain | TLS thật hoặc request được nhận diện secure |
| HTTP 200 | Không suy ra phải có HSTS | Chạy plain HTTP |
| Page dùng iframe | X-Frame-Options/CSP frame-ancestors | Đúng origin được cho phép |
| CSP-enabled page | CSP policy và console violation | Đã định nghĩa source allowlist |
| Multi-chain routes | Header viết trên đúng chain | `securityMatcher` và thứ tự `@Order` |
| Nhiều proxy/CDN | Header đến browser không bị ghi đè sai | Test end-to-end |

**Lời khuyên kiểm thử:** test dựa trên **hợp đồng security của ứng dụng**, không hardcode mọi header ngẫu nhiên mà server gửi. Mặc định cốt lõi có thể assert như demo; header tự cấu hình nên có assert riêng. Với browser behavior, cần thử trên các browser và môi trường TLS mục tiêu.

## 13. Checklist triển khai và bảo trì

1. Xác định app dùng WebFlux và bean `SecurityWebFilterChain` thực sự áp dụng.
2. Biết chính xác nhóm header default của phiên bản đang chạy, không nhầm với trang docs “current” của version khác.
3. Giữ `Cache-Control: no-store` trên tài nguyên riêng tư; chỉ cho cache những resource công khai.
4. Giữ `X-Content-Type-Options: nosniff`, đồng thời sửa MIME type/Content-Disposition của upload/resource.
5. Giữ `X-Frame-Options: DENY` trừ khi cần nhúng trang; nếu cần, thiết kế CSP `frame-ancestors` theo origin đáng tin.
6. Nhớ `X-XSS-Protection: 0` là tắt legacy XSS Auditor; có output encoding và CSP riêng.
7. Bảo đảm HTTPS/TLS ở public edge và kiểm tra HSTS chỉ xuất hiện trên HTTPS. Đánh giá includeSubDomains/preload cẩn thận.
8. Đặt forwarding header trust boundary, tránh scheme/host spoofing từ Internet.
9. Không tùy tiện gọi `headers(...disable())` hoặc tắt cache/security writers toàn cục.
10. Nếu app cần CSP, Referrer-Policy, Permissions-Policy hoặc COOP/COEP/CORP, cấu hình tường minh và test.
11. Xác định ai phụ trách security headers khi có cả app + Nginx/Ingress/CDN.
12. Kiểm 200/401/403/302, static assets, HTTPS, fallback chain và sau nâng cấp dependency.
13. Quan sát browser devtools/CSP reports, integration test HTTP response, và security scanners như tín hiệu bổ trợ — không coi “điểm A” là bằng chứng đủ.
14. Không lộ password, session cookie, Authorization header hoặc token trong log/debug để kiểm tra header.
15. Duy trì phiên bản Spring Security được hỗ trợ; xem cả các advisory liên quan header. Ví dụ **CVE-2026-22732** (công bố 19/03/2026) mô tả một tình huống header không được ghi trên **nhánh Servlet** ở một số phiên bản; **không suy rộng tự động rằng cùng CVE này áp dụng WebFlux**. Đây là lời nhắc kiểm tra scope và patch theo advisory chính thức.

## 14. Bài tập tự luyện

1. Chạy demo và đọc tất cả response header của `GET /api/public`. Đối chiếu danh sách mặc định; vì sao `Strict-Transport-Security` có thể vắng mặt?
2. Gọi `GET /api/private` chưa đăng nhập. Xác nhận 401 Basic challenge và nhóm header bảo vệ, phân biệt chúng với authentication/authorization.
3. Đăng nhập bằng Alice, xem `Cache-Control` của `GET /api/private`. Vì sao không thể thay `no-store` bằng `public,max-age=3600`?
4. So sánh `GET /api/public` và `GET /api/public-cache`. Vì sao cache override chỉ phù hợp resource công khai?
5. Đổi frameOptions từ `DENY` sang `SAMEORIGIN`, viết test header và thử trang được nhúng cùng origin. Với third-party portal, cần thêm cơ chế nào?
6. Triển khai HTTPS staging và kiểm HSTS trên response qua proxy. Nếu thấy mất HSTS, hãy kiểm scheme, forwarding headers, ownership policy và TLS termination.
7. Thử cấu hình HSTS maxAge 180 ngày, không includeSubdomains. Phân tích vì sao bật preload không chỉ là thay đổi nhỏ.
8. Thêm CSP chỉ cho phép script cùng origin và test trang dùng script CDN. Hãy đề xuất cách báo cáo violation/rollout an toàn.
9. Bật `Referrer-Policy: no-referrer` tường minh. Kiểm tra trên version Spring Security thực tế thay vì đoán từ tài liệu tổng quát.
10. Thêm `Permissions-Policy: geolocation=()` và test browser không cho trang gọi geolocation trong bối cảnh bị cấm.
11. Tạo hai `SecurityWebFilterChain` với matcher `/api/**` và fallback; kiểm default headers trên mỗi nhóm. Lỗi nào xảy ra nếu một URL không match bất cứ chain nào?
12. Giải thích vì sao `X-XSS-Protection: 0` không làm ứng dụng “không có XSS” và vì sao `nosniff` không tự sửa content type.
13. Mô tả quy trình test header sau deploy bằng WebTestClient, curl và browser devtools, bao gồm 200/401/403/HTTPS.
14. Kiểm soát proxy/CDN để không xóa header do app phát hoặc nhân đôi HSTS/CSP theo cách bất ngờ.

## Tóm tắt

**Spring Security WebFlux mặc định cung cấp một nhóm HTTP response security headers** nhằm bảo vệ cache, MIME handling, iframe embedding, legacy XSS browser behavior và HTTPS. Bộ mặc định được liệt kê trong Javadoc Spring Security 6.x gồm **`Cache-Control`, `Pragma`, `Expires`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0` và `Strict-Transport-Security` chỉ trên secure request**. HSTS không có nghĩa Spring Boot tự mở HTTPS; CSP/Permissions-Policy và các cross-origin isolation policy cần cấu hình theo ứng dụng. Nếu chỉ muốn đổi một header, dùng `ServerHttpSecurity.headers(...)` để tùy chỉnh **riêng header đó**, không tắt toàn bộ bảo vệ. Bảo đảm các điều kiện cache, HTTPS/proxy, security chain, role/CSRF và browser test luôn được kiểm tra cùng nhau.

## Tài liệu tham khảo chính thức

1. Spring Security 6.5 — WebFlux Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
2. Spring Security 6.5 — `ServerHttpSecurity.headers(Customizer)` và default header list: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
3. Spring Security — General HTTP Response Headers list: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
4. Spring Security 6.3.10 — `ServerHttpSecurity.HeaderSpec` (lambda API): https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html
5. Spring Security 6.3.x — `XFrameOptionsServerHttpHeadersWriter.Mode`: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/header/XFrameOptionsServerHttpHeadersWriter.Mode.html
6. Spring Security 6.5 — `ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/header/ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy.html
7. Spring Security — HTTP, redirect HTTPS, TLS và proxy forwarding: https://docs.spring.io/spring-security/reference/6.5/features/exploits/http.html
8. Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
9. Spring Framework — ForwardedHeaderTransformer (WebFlux): https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
10. OWASP Cheat Sheet — HTTP Security Response Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
11. MDN — Strict-Transport-Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
12. Spring Security advisory CVE-2026-22732, Servlet-specific scope: https://spring.io/security/cve-2026-22732/
