# Không lưu đệm công khai phản hồi chứa thông tin cá nhân trong Spring Boot

## 1. Vì sao cache có thể trở thành lỗ hổng rò rỉ dữ liệu?

Một ứng dụng Spring Boot có endpoint `GET /api/me`. Khi Alice đăng nhập, endpoint trả tên, email, quyền hoặc dữ liệu đơn hàng của Alice. Khi Bob đăng nhập, **cùng URL** trả body khác. Nếu CDN, reverse proxy hoặc gateway lưu bản của Alice theo URL rồi gửi lại cho Bob thì việc xác thực ở Spring Boot không còn tác dụng: request của Bob thậm chí không đi tới origin.

~~~text
Alice -- GET /api/me, Cookie A --> CDN -- MISS --> Spring Boot
                                 |               |
                                 |<-- Alice -----|
                                 |  cache URL sai
                                 |
Bob -- GET /api/me, Cookie B ----> CDN -- HIT --> dữ liệu Alice
                                           (RÒ RỈ DỮ LIỆU)
~~~

Đây không phải chỉ là lỗi cache stale, mà là **vi phạm cô lập dữ liệu giữa người dùng**. Hậu quả tương tự với thông tin thanh toán, địa chỉ, báo cáo tài chính, session-bearing HTML hoặc JSON chứa thông tin xác thực.

**Nguyên tắc:** một response phụ thuộc user/tenant/authorization **không được lưu trong shared HTTP cache**. Với nội dung nhạy cảm, lựa chọn mặc định tốt là `Cache-Control: no-store`: yêu cầu **cả shared cache lẫn private cache không lưu**. Với nội dung cá nhân được phép browser tự giữ, `private` ngăn shared cache nhưng vẫn có thể cho phép browser lưu.

“GET là idempotent”, “URL là duy nhất”, “request có cookie” và “đã cài Spring Security” **không phải bằng chứng** phản hồi an toàn để public-cache. Phải xét **toàn bộ body và headers**, nguồn tạo response, các lớp cache trên đường đi và việc đổi account/logout.

## 2. Phân biệt các loại cache trước khi sửa

| Loại | Ví dụ | Có chia sẻ cho nhiều user? | `Cache-Control` response quản lý? |
| --- | --- | --- | --- |
| Private HTTP cache | Browser memory/disk, HTTP client riêng | Thông thường chỉ trong phạm vi client/profile | Có |
| Shared HTTP cache | CDN edge, proxy cache, API gateway response cache | Có, theo cache key và rule | Có nếu cache tuân chuẩn và không override |
| Application data cache | Spring `@Cacheable`, Redis object cache, in-memory map | Tùy code/key | **Không** |
| Service worker/browser app storage | Cache Storage, IndexedDB, localStorage | Trong client app, có lifecycle riêng | **Không bảo đảm** |
| Session store | Redis session/`HttpSession` | Các app node dùng chung server state | **Không**; đây không phải HTTP response cache |
| Log/archive/analytics | Access logs, APM traces, downloaded files | Tùy hạ tầng/quyền | **Không** |

**Không nhầm HTTP caching với Spring Cache.** Một response được gắn `no-store` vẫn có thể lấy từ một `@Cacheable` có key sai ở backend. Ngược lại, một backend không dùng Redis cache vẫn có thể bị CDN lưu nhầm HTTP response.

HTTPS bảo vệ đường truyền, nhưng một CDN kết thúc TLS và thực thi policy cache vẫn có khả năng lưu response; không có bảo đảm private caching chỉ vì URL bắt đầu bằng `https://`.

## 3. So sánh những chỉ thị Cache-Control quan trọng

| Directive trong **response** | Hệ quả ở shared cache | Hệ quả ở private cache | Nên dùng cho thông tin cá nhân? |
| --- | --- | --- | --- |
| `public, max-age=300` | Cho phép lưu và dùng khi fresh 300 giây | Cho phép | **Không** cho response cá nhân |
| `private` | **Cấm shared cache lưu toàn response** | Có thể lưu | Chỉ khi cho phép browser giữ bản sao |
| `private, max-age=60` | Cấm shared storage | Có thể lưu tối đa 60 giây | Chỉ với dữ liệu được phép lưu tại client |
| `no-cache` | Có thể lưu; phải revalidate trước khi reuse | Có thể lưu và revalidate | **Không đủ** nếu yêu cầu không lưu |
| `no-store` | **Không được cố ý lưu request/response** | **Không được cố ý lưu** | **Ưu tiên cho nội dung nhạy cảm** |
| `private, no-store` | Không lưu | Không lưu | Hợp lệ; `no-store` đã nghiêm hơn |
| `max-age=0` | Có thể lưu nhưng stale ngay | Có thể lưu | Không thay được `no-store` |
| `must-revalidate` | Khi stale, phải revalidate trước khi dùng | Tương tự | Không phải lệnh cấm lưu |
| `s-maxage=600` | Shared cache có TTL 600 giây, ưu tiên hơn `max-age` | Không phải TTL của private cache | **Không** cho personalized response |
| `no-transform` | Cấm intermediary biến đổi representation | Không cấm cache | Không thay `private/no-store` |

### 3.1. `no-cache` không có nghĩa “không lưu”

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
Content-Type: application/json

{"email":"alice@example.test"}
~~~

Cache tuân chuẩn vẫn **có thể giữ body** rồi revalidate với origin trước khi tái sử dụng. Nếu yêu cầu thực sự không có bản sao của PII trong browser/CDN, chỉ thị thích hợp hơn là:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"email":"alice@example.test"}
~~~

Theo RFC 9111, `no-store` yêu cầu cache không **cố ý** lưu request/response, nhưng không bảo đảm loại bỏ dữ liệu đã nằm trong log, extension, screenshot hay cache độc hại. Phải có TLS, authorization và kiểm soát retention bổ sung.

### 3.2. `private` cấm **shared** caching, không cấm browser caching

~~~http
Cache-Control: private, max-age=120
~~~

Browser có thể lưu một bản riêng đến hai phút nếu điều kiện cache khác thỏa. Đây là khác biệt với `no-store`. `private` không mã hóa dữ liệu và không bảo vệ khi user khác dùng cùng profile máy tính sau logout.

RFC 9111 có cú pháp `private="Set-Cookie"` để hạn chế **chỉ field được nêu**; nó không cấm shared cache giữ **body**. Vì vậy dùng `private` không có tham số hoặc `no-store` nếu body chứa PII.

### 3.3. `max-age=0, must-revalidate` cũng không cấm lưu

~~~http
Cache-Control: max-age=0, must-revalidate
~~~

Cache có thể chứa một bản stale và kiểm tra lại trước khi dùng. Nó không thỏa yêu cầu “không lưu response”. Nếu cần ngăn storage, phải có `no-store`.

### 3.4. Cache-Control ở request và response khác nhau

Client gửi `Cache-Control: no-cache` trên **request** là một yêu cầu về cách cache xử lý request đó; nó **không thay** response directive mà Spring Boot phải gửi. Đừng chỉ cấu hình frontend `fetch(..., {cache: "no-store"})` rồi bỏ header ở origin. Đường đi qua CDN/reverse proxy vẫn cần policy đúng.

## 4. Authorization, Cookie và Set-Cookie không tự bảo đảm riêng tư

### 4.1. Request có `Authorization`

RFC 9111 `3.5 giới hạn shared cache reuse đối với response của request có `Authorization`, **nhưng có ngoại lệ** khi response mang directive cho phép, đáng chú ý gồm `public`, `s-maxage` và `must-revalidate`.

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <token-cua-Alice>
~~~

Nếu response vô tình có:

~~~http
Cache-Control: public, s-maxage=1800
~~~

thì không thể dựa vào việc có bearer token để khẳng định sẽ không được shared-cache sử dụng. `must-revalidate` cũng **không** thay cho `private` hay `no-store` với personalized responses.

**Khuyến nghị:** response chứa dữ liệu riêng luôn đặt chính sách rõ, tối thiểu `private`, với dữ liệu nhạy cảm đặt `no-store`, đồng thời bypass ở CDN/gateway.

### 4.2. Request có `Cookie`

~~~http
Cookie: SESSION=<session-id>
~~~

Cookie không có cùng quy tắc đặc biệt về shared caches như `Authorization` ở mục trên. Một response xác thực bằng session vẫn có thể bị cache sai nếu gateway rule và Cache-Control cho phép. Các trang HTML server-rendered chứa “Xin chào, Alice” đặc biệt dễ bị bỏ sót khi một rule “cache HTML” được bật toàn website.

### 4.3. Response có `Set-Cookie`

Header `Set-Cookie` **không tự động biến response thành non-cacheable** theo HTTP caching standard. Nếu một response cacheable lại mang session cookie hoặc body user-specific, proxy có thể tạo rủi ro khi lưu/forward không đúng cách.

Không để một response được đánh dấu `public` chứa session ID của từng người dùng. Tách static page/asset chung khỏi API set session và API lấy dữ liệu cá nhân, hoặc thiết kế edge behavior có kiểm chứng.

## 5. Vì sao `Vary: Cookie` không thay được `private/no-store`?

`Vary` yêu cầu cache xét các request header được nêu khi chọn bản lưu. `Vary: Accept-Encoding` thường có ích cho gzip và uncompressed representations.

~~~http
Vary: Cookie
~~~

có thể làm variant key phụ thuộc Cookie, nhưng **không đủ làm biện pháp bảo mật**:

1. Nó **không cấm lưu** phản hồi trong shared infrastructure.
2. CDN có thể strip, normalize hoặc không đưa Cookie vào key theo config.
3. Cookie nhiều thành phần (session, analytics, thử nghiệm) tạo vô số biến thể; tăng memory, cache miss và nguy cơ lộ qua logs.
4. Logout, session rotation, quyền thay đổi không tự xóa entries cũ.
5. Một lỗi matching, bypass hoặc override rule có thể dùng bản của Alice cho Bob.
6. Với nội dung nhạy cảm, chính việc giữ bản sao ở CDN đã trái yêu cầu không public-cache.

Đừng dùng `Vary: Authorization` hoặc query parameter `userId` như một lý do để phát `Cache-Control: public` trên profile. Dữ liệu nào không thật sự public phải được bảo vệ ở origin và edge.

## 6. Chính sách theo loại endpoint

| URL hoặc loại response | Phụ thuộc người dùng? | Header gợi ý |
| --- | --- | --- |
| `/assets/app.abcd1234.js`, CSS fingerprint | Không | `public, max-age=31536000, immutable` nếu URL thay khi bytes thay |
| `/assets/logo.svg` | Không | `public, max-age=86400` tùy update |
| `/api/catalog` thuần công khai | Không | `public, max-age=300` |
| `/api/catalog` có member-specific price | Có | Tách giá user hoặc `private/no-store` |
| `/api/me`, `/account` | Có, PII | `no-store` |
| `/api/orders`, `/checkout` | Có, nhạy cảm | `no-store` |
| `/payment-methods` | Có | `no-store` |
| `/login` có CSRF token hoặc state phiên | Có thể | `no-store` |
| 401/403/404 có nội dung gắn user | Có thể | `no-store` |
| 3xx redirect có token/state riêng | Có thể | `no-store`, tránh secret trong URL |
| Download file chỉ owner được xem | Có | `no-store` và auth từng request |
| Avatar thật sự public | Không | Có thể cache theo versioned URL |

**Public HTML shell + private API** là mô hình hữu ích: CSS, JS, HTML khung chung có thể cache; dữ liệu profile và giao dịch lấy riêng với `no-store`. Nếu thêm câu `"Welcome back, Alice"` trực tiếp vào cached HTML, toàn bộ response đã thành personalized.

## 7. Cấu hình Cache-Control trên Spring MVC ResponseEntity

Spring Framework cung cấp `org.springframework.http.CacheControl` và `ResponseEntity.cacheControl(...)`.

Đối với dữ liệu riêng:

~~~java
// Snippet bên trong một @RestController:
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(personalProfile);
~~~

Có thể dùng `CacheControl.noStore().cachePrivate()` nếu muốn diễn đạt cả ý định cấm shared storage, nhưng `no-store` một mình đã là lựa chọn nghiêm hơn.

Đối với nội dung **thực sự công khai**:

~~~java
return ResponseEntity.ok()
        .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic())
        .body(commonCatalog);
~~~

Nó phát directive `max-age=300` và `public`. Không dùng global annotation hoặc filter tự gắn public cho tất cả GET.

Ngoài `Cache-Control`, có thể thêm:

~~~http
Pragma: no-cache
Expires: 0
~~~

để hỗ trợ client cũ. Đây là **header bổ sung**, không thay thế `no-store`. Đặc biệt tránh nhiều middleware ghi các giá trị Cache-Control trái ngược mà không test header cuối cùng.

## 8. Dự án chạy được: Java 17 + Spring Boot MVC + Security

Ví dụ có hai user lab Alice/Bob và hai endpoint:

- `GET /api/catalog` công khai, giống nhau cho mọi user, có thể cache.
- `GET /api/me` yêu cầu HTTP Basic, trả username theo principal, **no-store**.

**HTTP Basic trên localhost chỉ phục vụ lab.** Production phải dùng HTTPS và hệ thống identity/password/secret được quản lý an toàn; không đưa mật khẩu demo vào hệ thống thật.

### 8.1. Cấu trúc và Gradle

~~~text
cache-privacy-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/cache/CachePrivacyApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/cache/CachePrivacyTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cache-privacy-lab'
~~~

`build.gradle` (Spring Boot 3.3.13 là ví dụ một phiên bản 3.x; dự án thật theo phiên bản được hỗ trợ):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 8.2. Java source

`src/main/java/demo/cache/CachePrivacyApplication.java`:

~~~java
package demo.cache;

import java.security.Principal;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CachePrivacyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CachePrivacyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-password"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-password"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/catalog").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }
}

@RestController
class CachePrivacyController {
    @GetMapping("/api/catalog")
    ResponseEntity<Map<String, Object>> catalog() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofMinutes(5))
                        .cachePublic())
                .body(Map.of(
                        "product", "Java Handbook",
                        "price", 100));
    }

    @GetMapping("/api/me")
    ResponseEntity<Map<String, String>> profile(Principal principal) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header(HttpHeaders.PRAGMA, "no-cache")
                .header(HttpHeaders.EXPIRES, "0")
                .body(Map.of(
                        "viewer", principal.getName(),
                        "kind", "personal"));
    }
}
~~~

Giải thích:

1. `Principal` do Spring Security xác thực, không nhận user ID tùy ý từ request header của client.
2. `SessionCreationPolicy.STATELESS` chỉ liên quan cách auth demo lưu session, **không** miễn trừ nhu cầu no-store với dữ liệu cá nhân.
3. `/api/me` trả policy `no-store`; `Pragma` và `Expires` thêm cho tương thích.
4. `/api/catalog` công khai và không phụ thuộc username, nên được phép cache có kiểm soát.
5. Nếu sau này catalog chứa giá theo user, cookie experiment hoặc "Hello Alice", chính sách `public` phải được bỏ/thay đổi.
6. `Map.of` không bảo đảm thứ tự trường JSON; test kiểm tra theo key.
7. Các user/password trong bộ nhớ dùng riêng cho lab. Không log credential, không đưa phiên thật/PII thật vào example.

### 8.3. Chạy và quan sát

Khi đã tạo Gradle wrapper cho dự án:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra public:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Các dòng mang ý nghĩa kỳ vọng (thứ tự header/JSON có thể khác):

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=300, public
Content-Type: application/json

{"product":"Java Handbook","price":100}
~~~

Kiểm tra Alice:

~~~bash
curl -i -u alice:alice-password http://localhost:8080/api/me
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Expires: 0
Content-Type: application/json

{"viewer":"alice","kind":"personal"}
~~~

Kiểm tra Bob trên **cùng URL**:

~~~bash
curl -i -u bob:bob-password http://localhost:8080/api/me
~~~

Kỳ vọng body có `"viewer":"bob"`, vẫn `Cache-Control: no-store`. Gọi không xác thực:

~~~bash
curl -i http://localhost:8080/api/me
~~~

Spring Security thông thường trả **401 Unauthorized**, không phải profile của một user bất kỳ. Cần kiểm tra cache policy cả ở đường 401/error trong môi trường thật.

## 9. Kiểm thử tự động Spring MVC với MockMvc

Để ngăn regression do developer sửa nhầm headers, thêm test. Tệp `src/test/java/demo/cache/CachePrivacyTest.java`:

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CachePrivacyTest {
    @Autowired
    MockMvc mvc;

    @Test
    void aliceHasNoStore() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(jsonPath("$.viewer").value("alice"));
    }

    @Test
    void bobHasNoStoreAndHisOwnBody() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("bob", "bob-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(jsonPath("$.viewer").value("bob"));
    }

    @Test
    void unauthenticatedCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void catalogIsExplicitlyPublic() throws Exception {
        mvc.perform(get("/api/catalog"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("public")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("max-age=300")));
    }
}
~~~

Lệnh chạy:

~~~bash
./gradlew test --tests demo.cache.CachePrivacyTest
~~~

Test kiểm tra cả **body theo user** và **policy `no-store`**. Nếu chỉ kiểm tra response 200, lỗi cache có thể lọt. Tuy nhiên `MockMvc` chạy tại origin, **không mô phỏng CDN/proxy**, nên phải có thêm staging integration test qua đường truy cập thật.

## 10. Spring Security default headers không thay việc phân loại response

Spring Security thường thêm response headers bảo vệ caching:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Điều này hữu ích mặc định. Nhưng nếu ứng dụng đã đặt Cache-Control, security header writer thường **tôn trọng policy ứng dụng** để cho phép asset public được cache. Vì vậy:

- Một developer có thể vô tình gắn `Cache-Control: public` vào trang profile.
- Một `SecurityFilterChain` có thể không bao phủ endpoint bạn nghĩ nó bao phủ.
- Tắt cache-control headers **toàn cục** vì muốn cache CSS/JS có thể làm mất chính sách bảo vệ.
- API error page, redirect, static handler và template engine có thể có header khác controller thành công.
- CDN có thể rewrite header sau khi Spring Boot đã phát no-store.

**Kiểm tra final response**, không dựa vào việc có dependency `spring-boot-starter-security` rồi coi mọi route an toàn.

## 11. Giữ `no-store` cho response lỗi, redirect và HTML riêng tư

Không chỉ `200 OK` mới chứa PII. Ví dụ:

- `401/403` body có email hoặc thông tin người dùng.
- `404` hiển thị mã hồ sơ/đơn hàng không thuộc quyền.
- `500` bị trả stack trace, SQL/debug data.
- `302` redirect chứa state/session/one-time token trong URL.
- Trang HTML server-rendered có tên/account của người đang đăng nhập.
- File download có private name hoặc nội dung nhạy cảm.
- Response `304` hoặc cache metadata được tính sai theo identity.

Một **policy ở route/boundary** nên ngăn public caching cho tất cả response thuộc nhánh riêng. Controller dùng `ResponseEntity.cacheControl(CacheControl.noStore())` cho response thành công, và có thể thêm filter phòng vệ trước khi headers commit.

Snippet dành cho **Spring MVC Servlet**, nằm trong class kế thừa `OncePerRequestFilter` và được đăng ký phù hợp:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    String path = request.getServletPath();
    if (path.equals("/api/me")
            || path.startsWith("/api/account/")
            || path.startsWith("/api/orders/")) {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.setHeader("Expires", "0");
    }

    chain.doFilter(request, response);
}
~~~

**Không phải một class chạy độc lập:** snippet cần imports Jakarta Servlet, Spring Web và class/filter registration. Thử với Spring Security chain, error dispatch và context path.

Nếu controller/proxy sau đó **ghi đè** Cache-Control thành `public`, filter đặt sớm không đủ. Phải có test final response và cơ chế policy enforcement rõ ràng tại boundary. Không để exception handler lộ PII chỉ vì đã có `no-store`.

## 12. WebFlux: cùng Cache-Control, API xử lý khác

WebFlux dùng `Mono`/`Flux` và `ServerWebExchange`; header HTTP có cùng semantics. Đoạn minh họa bên trong một `@RestController` WebFlux đã xác thực:

~~~java
@GetMapping("/api/reactive-me")
Mono<ResponseEntity<Map<String, String>>> me(
        Mono<Principal> principal) {

    return principal.map(p ->
            ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(Map.of("viewer", p.getName())));
}
~~~

Đây là snippet method, không phải Java class độc lập. `Principal` phải được cung cấp bởi security configuration thật; nếu user không xác thực, xử lý 401/403 đúng policy.

Snippet `WebFilter` để gắn no-store **trước response commit**:

~~~java
// Thêm vào cấu hình WebFlux thực tế:
return (exchange, chain) -> {
    String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

    if (path.equals("/api/reactive-me")
            || path.startsWith("/api/private/")) {
        exchange.getResponse().getHeaders()
                .setCacheControl("no-store");
    }
    return chain.filter(exchange);
};
~~~

Không dùng `HttpServletResponse`/`OncePerRequestFilter` để điều khiển Netty WebFlux thuần. Kiểm tra Spring Security reactive headers và final response cùng nguyên tắc Servlet.

**Reactor `Mono.cache()` và Spring `@Cacheable` là caches ở tầng ứng dụng.** Chúng có thể trả dữ liệu user A cho B nếu dùng shared Publisher/cache key sai, bất kể response có no-store. Không cache một `Mono<UserProfile>` toàn cục cho mọi user.

## 13. CDN và reverse proxy: chỉ whitelist tài nguyên public

Đường đi thường gặp:

~~~text
Browser
   |
   v
CDN edge cache
   |
   v
API gateway / reverse proxy / ingress
   |
   v
Spring Boot origin
   |
   v
Database / Session store
~~~

Origin `Cache-Control: no-store` là hợp đồng với cache tuân chuẩn, nhưng một số CDN có cấu hình “cache everything”, force TTL, cache key không có Cookie/Authorization, edge worker tự rewrite hoặc rule bỏ qua origin headers. **Phải audit cấu hình sản phẩm đang dùng**.

Chính sách triển khai gợi ý:

1. **Bypass lookup và storage** trên `/api/me`, `/api/account/**`, `/api/orders/**`, checkout, payment, auth, private downloads và admin.
2. Cho phép caching ở `/assets/**` đã fingerprint, ảnh/logo public và API có body được kiểm chứng **giống nhau với mọi user**.
3. Với request có Authorization/cookie session, mặc định bypass trừ những endpoint đã được review là công khai.
4. Tránh cache một response có Set-Cookie hoặc thông tin user-specific, dù Set-Cookie không tự cấm HTTP caching.
5. Không dùng `Vary: Cookie` như biện pháp duy nhất và không lưu raw session cookie trong CDN cache key logs.
6. Đọc response headers **sau CDN** để phát hiện origin header bị override; kiểm tra `Age`, `Cache-Status`, `Via` hoặc vendor `X-Cache` nếu có.
7. Cần biết một số CDN không gửi hit headers, vì vậy “không có Age” không chứng minh chắc chắn cache bị bypass.

### NGINX snippet: không đọc cache cũ và không ghi cache mới

Ví dụ này chỉ dành cho cấu hình có upstream `spring_backend` và `proxy_cache` đã được định nghĩa ở nơi khác, **không phải toàn bộ cấu hình NGINX standalone**:

~~~nginx
location /api/me {
    proxy_pass http://spring_backend;
    proxy_cache_bypass 1;
    proxy_no_cache 1;
}

location /api/orders/ {
    proxy_pass http://spring_backend;
    proxy_cache_bypass 1;
    proxy_no_cache 1;
}
~~~

- `proxy_cache_bypass 1` bỏ qua cache entry đã có.
- `proxy_no_cache 1` ngăn lưu response mới.
- Cần xác minh chính xác path matching (bao gồm trailing slash, query, routing) và xem CDN **phía trước** NGINX có policy tương ứng không.
- Không lấy ví dụ này áp thẳng cho nền tảng cloud/CDN dùng cơ chế rule khác.

Cách an toàn là **public caching theo allowlist**, không phải “cache all GET” rồi vá từng endpoint có PII khi phát sinh sự cố.

## 14. ETag, If-None-Match và 304: revalidation không bảo đảm cô lập user

Cache có thể giữ một representation rồi gửi conditional request:

~~~http
GET /api/report HTTP/1.1
If-None-Match: "v5"
~~~

Nếu origin trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "v5"
Cache-Control: private, max-age=0, must-revalidate
~~~

thì client/cache có thể tái sử dụng bản lưu theo quy tắc. Với dữ liệu riêng:

- Nếu yêu cầu **không lưu**, dùng `no-store` và tránh tạo đường reuse trên shared cache.
- Nếu **cho phép browser private cache**, ETag phải phản ánh representation của **đúng user và đúng quyền**, không dùng `"v5"` chung cho các body khác nhau.
- Khi đổi account trong cùng browser, một validator/cache key không scope theo identity có thể gây 304 sai dẫn đến hiển thị data cũ.
- `Vary: Accept-Encoding` phân biệt encoding; `Vary: Cookie` không thay `private/no-store`.
- Nếu dữ liệu từng bị cache public, sửa header mới **không xóa** cache entry cũ. Phải purge CDN.

Spring MVC hỗ trợ ETag/Last-Modified và resource caching, nhưng đừng bật một cơ chế ETag toàn cục cho mọi personalized response mà không xét representation key và security policy.

## 15. HTTP compression khác caching; có rủi ro side-channel riêng

**Compression** (`Content-Encoding: gzip`, `br`, v.v.) giảm bytes truyền. **Caching** quyết định có lưu response hay không. Một HTTP response có thể vừa nén vừa không được lưu:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Encoding: gzip
Vary: Accept-Encoding
Content-Type: application/json
~~~

`Vary: Accept-Encoding` chỉ phân biệt nén/không nén, **không** cô lập user. `no-transform` ngăn intermediary biến đổi representation, **không** cấm cache.

Spring Boot có cấu hình compression:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
~~~

Đây không phải cấu hình cache. Khi nội dung có secret và dữ liệu mà attacker có thể ảnh hưởng nằm chung trong response được nén, thay đổi kích thước nén có thể tạo side-channel kiểu **BREACH**. `no-store` không ngăn rủi ro side-channel này. Đánh giá việc tắt compression cho tài nguyên nhạy cảm, tách secret khỏi nội dung reflected, áp dụng CSRF/security controls.

Không suy ra “response có gzip ⇒ CDN cache” hoặc “no-store ⇒ gzip bị tắt”.

## 16. Logout, browser history, service worker và dữ liệu đã lưu

`no-store` giúp ngăn private/shared HTTP caches lưu response, **không** bảo đảm xóa mọi nội dung đã hiển thị:

1. Logout phải vô hiệu phiên/token tại server theo policy; xóa cookie ở browser không đủ nếu token cũ còn hiệu lực.
2. `localStorage`, IndexedDB, service worker Cache Storage hoặc state manager của SPA có thể chứa PII; phải có policy riêng và xóa khi logout/đổi account.
3. Browser history, back-forward cache (bfcache), snapshot UI/extension có lifecycle phụ thuộc browser; không cam kết no-store xóa tất cả dấu vết. Khi restore UI nên kiểm tra lại authentication/identity.
4. `Clear-Site-Data: "cache"` có thể hữu ích khi logout trên browser hỗ trợ nhưng có phạm vi/giới hạn và **không purge CDN**.
5. Đối với máy dùng chung, đặt policy cache bảo thủ, dùng HTTPS, cookie `Secure`/`HttpOnly`/`SameSite`, session revocation và CSRF/authorization phù hợp.

No-store không thay đổi quyền truy cập trên API hay tính hợp lệ của bearer token; cần cả caching policy lẫn security controls.

## 17. Spring `@Cacheable` có thể làm lộ dữ liệu ngay tại origin

Một ví dụ **sai**:

~~~java
// Anti-pattern: method không tham số có thể dùng cache key chung.
@Cacheable("profiles")
public Profile currentProfile() {
    return repository.findById(currentUserId());
}
~~~

User Alice gọi trước, profile Alice có thể được lưu dưới key chung; Bob gọi sau nhận lại object Alice. HTTP response dù mang `Cache-Control: no-store` vẫn bị sai **trước khi tới CDN**.

Ví dụ ý tưởng có key rõ hơn (snippet, không phải class hoàn chỉnh):

~~~java
@Cacheable(cacheNames = "profiles", key = "#userId")
public Profile loadProfile(String userId) {
    return repository.findById(userId).orElseThrow();
}
~~~

Nhưng `userId` đơn lẻ cũng có thể chưa đủ nếu dữ liệu phân vùng theo tenant/role/permission. Authorization phải được kiểm tra **trước khi trả cache hit**, cache key phản ánh tất cả dimensions tác động response, có invalidation khi quyền/profile đổi. Với dữ liệu đặc biệt nhạy cảm có thể không nên cache ở application layer.

**`spring.cache.*` không phải cấu hình HTTP Cache-Control.** Xem Spring Cache/Redis/CDN/browsers là các tầng riêng có mô hình bảo mật khác nhau.

## 18. Kiểm thử end-to-end với hai user và proxy/CDN

Test origin `MockMvc` đã có; tiếp theo cần staging route **qua CDN và load balancer thật** với hai tài khoản giả, khác PII marker.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Alice gọi `/api/me` qua origin | no-store và body Alice |
| Bob gọi cùng URL qua origin | no-store và body Bob |
| Alice/Bob gọi qua CDN | Không trả chéo body, private response không shared-cache HIT |
| 401/403 route private | Không lộ PII và không public-cache |
| Error 500 route private | Không public-cache hoặc lộ debug data |
| Profile đổi quyền/session | Bản cũ không được shared-cache reuse |
| Thêm compression | Cache-Control vẫn no-store |
| Conditional 304 | Không dùng sai representation của user cũ |
| Catalog public | Có thể cache nếu body thật sự giống nhau |
| Catalog có member discount | Phải thay policy/chia endpoint |
| Logout, đổi account cùng browser | Không hiển thị dữ liệu user trước |
| CDN bật force cache thử trên staging | Test phải báo sai policy |

Quan sát headers qua staging (placeholder token, không dán credential thật vào tài liệu/ticket):

~~~bash
curl -sD - -o /dev/null \
  -H "Authorization: Bearer <staging-token-A>" \
  https://staging.example.test/api/me
~~~

Cần nhìn response body của hai account bằng công cụ an toàn và quan sát `Cache-Control` trên **response cuối cùng tới client**. `Age`, `Cache-Status`, `Via`, `X-Cache` có thể giúp chẩn đoán nhưng không phải mọi CDN đều phát cùng header; thiếu `Age` không chứng minh bypass. Tốt nhất đối chiếu edge caching rule và cache-hit metrics.

Không thử bằng dữ liệu khách hàng thật và không lưu raw Authorization/session ID vào log cURL công khai.

## 19. Dấu hiệu sai và cách xử lý

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Bob thấy profile Alice | CDN/shared cache key bỏ auth/cookie hoặc policy public | Bypass, purge, incident investigation |
| Response chỉ có `no-cache` nhưng browser vẫn lưu | `no-cache` cho phép storage | Dùng no-store nếu phải cấm lưu |
| Có `max-age=0` nhưng proxy có cache entry | max-age=0 không cấm lưu | Dùng private/no-store đúng mức |
| Có `Vary: Cookie` nhưng CDN vẫn giữ PII | Vary không cấm storage | Bypass shared cache và no-store |
| Response có bearer Authorization bị public-cache | Có directive cho phép hoặc CDN override | Audit response Cache-Control, edge config |
| Có Set-Cookie nhưng bị lưu ở proxy | Set-Cookie tự nó không cấm cache | Tách response, no-store/bypass |
| Spring Security mặc định bảo vệ nhưng controller ghi public | App override Cache-Control | Test final headers ở origin/edge |
| 401/500 không có no-store | Header chỉ ở success controller | Áp route-level policy và test error paths |
| Logout nhưng màn hình vẫn hiện data cũ | bfcache, service worker, state/client storage | Reset UI, invalidate session, no-store |
| Spring `@Cacheable` trả nhầm data | Key thiếu user/tenant/authorization | Sửa application caching, auth, invalidation |
| `304` dùng bản của user khác | ETag/cache key không scope identity | Sửa validator hoặc không cache PII |
| `Content-Encoding: gzip` xuất hiện | Đang bật compression | Đánh giá compression riêng và side-channel |
| CDN báo HIT cho PII endpoint | Force cache rule hoặc bypass sai | Điều tra/purge và chặn cache |

## 20. Khi đã lỡ cache công khai thông tin cá nhân

Đừng chỉ sửa origin header thành no-store rồi dừng: **entry cũ có thể tồn tại tới TTL**, một số edge còn có stale serving, và bản đã gửi tới user khác không thể tự thu hồi.

1. **Chặn phát tán:** tắt cache rule/bypass trên private route ngay, sửa origin `no-store` và kiểm tra final response.
2. **Purge/invalidate** entry đã cache tại CDN/proxy bằng URL/key/tag hoặc phạm vi phù hợp; không mặc định header mới xóa được entry cũ.
3. **Đánh giá phạm vi:** endpoint, thời gian, các edge, cache-hit logs, account bị ảnh hưởng; giảm việc sao chép PII vào hệ thống ghi chép điều tra.
4. **Đánh giá credential exposure:** nếu session token/OTP/bearer có thể lộ, xử lý revoke/rotate theo security incident plan.
5. **Escalate** cho security/privacy/operations và áp dụng chính sách/pháp luật liên quan dựa trên đánh giá thực tế.
6. **Regression test** 200/304/401/403/500, hai users cùng URL, CDN hit/miss, logout, rolling deploy và proxy rule.
7. **Kiểm tra cache khác** (`@Cacheable`, service worker, app state), vì sửa HTTP header không bảo vệ chúng.

Sử dụng dữ liệu giả có dấu hiệu nhận biết để tái hiện; không cần công bố nội dung PII thật cho cả team để chứng minh lỗi.

## 21. Checklist review trước release

- Response có PII, token, số giao dịch, email, tên, địa chỉ, nội dung nhạy cảm hoặc redirect riêng không?
- Nội dung phụ thuộc identity, cookie, bearer, tenant, tier, experiment, permission hay session không?
- Cache-Control trên route private là no-store/private đúng mức chưa, có `public`/`s-maxage` mâu thuẫn không?
- CDN và reverse proxy có bypass cả **cache lookup** lẫn **store** cho path riêng không?
- Có dựa sai vào `Vary: Cookie`, Set-Cookie hoặc Authorization để cho rằng public caching an toàn không?
- ETag, 304, cache keys có đúng representation theo user không?
- Spring Security default có bị middleware/controller override không; response lỗi/login/logout được bảo vệ không?
- Compression và caching đã được xét riêng; có nguy cơ side-channel trên response chứa secret không?
- Service worker, localStorage, IndexedDB và client app state có giữ dữ liệu sau logout không?
- `@Cacheable`/Redis internal cache có key đúng user/tenant và authorization không?
- Có unit/MockMvc test tại origin **và** staging test hai users qua CDN không?
- Có kế hoạch purge/incident handling và audit rule khi deploy không?

## 22. Câu hỏi tự kiểm tra

**1.** `GET /api/me` trả hai body theo Alice/Bob, có thể public-cache nếu thêm `Vary: Cookie` không?

**Đáp án:** Không. Vary không cấm storage, CDN có thể xử lý sai và shared cache vẫn chứa PII. Dùng no-store (hoặc private nếu chấp nhận browser cache) và bypass shared cache.

**2.** `no-cache` có cấm ghi dữ liệu lên disk cache không?

**Đáp án:** Không. Nó cho phép lưu, chỉ yêu cầu revalidate trước khi reuse. `no-store` mới là directive cấm cố ý lưu.

**3.** Có Spring Security, vì sao vẫn cần test Cache-Control trên `/api/me`?

**Đáp án:** Security default có thể không override header do ứng dụng ghi, hoặc CDN có rule riêng. Phải kiểm tra final response, không chỉ dependency.

**4.** Một response chứa `Set-Cookie` có tự bị RFC ngăn cache không?

**Đáp án:** Không. Cần policy `Cache-Control` và CDN bypass; Set-Cookie không tự là lệnh no-store.

**5.** Profile có `no-store` và `Content-Encoding: gzip`, có mâu thuẫn không?

**Đáp án:** Không: compression và caching khác nhau. Nhưng vẫn phải xem nguy cơ side-channel của nén với secret.

**6.** Origin đã sửa no-store nhưng trước đó CDN từng cache nhầm, có cần purge không?

**Đáp án:** Có, vì header mới không xóa retroactively entry cũ. Cần xử lý sự cố, kiểm tra phạm vi và regression test.

**7.** Controller no-store nhưng `@Cacheable` có key chung, có an toàn không?

**Đáp án:** Không. Dữ liệu có thể bị lẫn ngay tại origin; HTTP no-store không sửa cache key backend.

**8.** `must-revalidate` có thay `private` cho personalized response không?

**Đáp án:** Không. Nó không cấm storage, và RFC 9111 cho phép một số shared caching của authenticated responses với directive này theo điều kiện.

## 23. Nguồn tham khảo chính thức

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): `3.5` authenticated requests, `5.2` Cache-Control directives, `4.1` Vary, `4.3` revalidation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): request methods, status, representations và validators.
- [Spring Framework 6.1 — CacheControl API](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/http/CacheControl.html): `noStore()`, `cachePrivate()`, `cachePublic()`, `maxAge()`.
- [Spring Security — Default HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): các response headers mặc định và khi app override.
- [Spring Security — Servlet HTTP Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache control trong Servlet.
- [Spring Security — Reactive HTTP Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): cache control trong WebFlux.
- [Spring Framework — Web MVC HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ETag, Last-Modified và conditional requests.
- [Spring Boot — Web Servlet](https://docs.spring.io/spring-boot/reference/web/servlet.html): cấu hình web runtime, tài nguyên static và compression.

**Ghi nhớ:** `private` cấm shared cache nhưng vẫn cho phép cache riêng, `no-cache` cho phép lưu và revalidate, còn **`no-store` yêu cầu không lưu trong cả shared/private HTTP caches tuân chuẩn**. Với response có thông tin cá nhân, không dùng `public`/`s-maxage`; kiểm tra cả Spring Boot, CDN/proxy và application caches.
