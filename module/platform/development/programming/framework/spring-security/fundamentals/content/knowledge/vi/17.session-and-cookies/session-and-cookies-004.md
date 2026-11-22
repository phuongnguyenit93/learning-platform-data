# Stateful và stateless là lựa chọn về nơi giữ trạng thái xác thực

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích **stateful** và **stateless** trong bối cảnh *xác thực HTTP* bằng câu hỏi: **sau khi xác thực, trạng thái nhận diện người dùng được giữ ở đâu để request tiếp theo được công nhận?**
2. Mô tả luồng đăng nhập bằng `HttpSession` + session cookie và luồng xác thực lại mỗi request bằng HTTP Basic hoặc bearer access token.
3. Phân biệt **cookie, session ID, SecurityContext, Authentication, access token, refresh token** và khái niệm HTTP vốn stateless.
4. Hiểu `SessionCreationPolicy` của Spring Security, đặc biệt khác biệt `IF_REQUIRED`, `NEVER`, `STATELESS`; biết rằng chọn stateless **không tự bật JWT**.
5. Thấy một ứng dụng có thể dùng **stateful cho giao diện browser**, **stateless cho API**, với hai `SecurityFilterChain` có thứ tự rõ ràng.
6. Kiểm tra bằng Java 17+/Spring Boot, `MockMvc` và `curl`: session đăng nhập được tái sử dụng, trong khi API yêu cầu credentials cho từng request.
7. Đánh giá ưu/nhược về mở rộng hệ thống, revoke/logout, CSRF, XSS, vòng đời token, tải hệ thống và trải nghiệm người dùng.

**Phạm vi:** nền tảng Spring Security và HTTP session/cookie. Ví dụ chính sử dụng **Servlet/MVC** (`HttpSecurity`, `HttpSession`, `SecurityFilterChain`). WebFlux có cách quản lý session/security context khác; không dùng trực tiếp Servlet API trong reactive handler.

## 2. Ý chính: trạng thái xác thực tồn tại ở đâu giữa các request?

HTTP là giao thức *stateless* theo nghĩa mỗi request độc lập, không tự giữ “ai đã đăng nhập ở request trước”. Nhưng **ứng dụng** có thể xây dựng phiên đăng nhập bằng session hoặc yêu cầu bằng chứng xác thực mỗi lần.

Hai mô hình:

**Stateful authentication (dựa trên phiên phía server):**

```text
Browser                                  Server
  │ POST /login + credentials + CSRF       │
  ├───────────────────────────────────────>│ kiểm tra credentials
  │                                        │ tạo/lưu SecurityContext
  │                                        │ trong HttpSession
  │<────────────── Set-Cookie: JSESSIONID=... ─┤
  │                                        │
  │ GET /account                          │
  │ Cookie: JSESSIONID=...                │
  ├───────────────────────────────────────>│ tra session bằng session ID
  │                                        │ đọc Authentication đã lưu
  │<────────────── 200 OK ────────────────┤
```

**Stateless authentication (không dựa vào phiên bảo mật giữa các request):**

```text
Client                                     Resource Server
  │ GET /api/account                         │
  │ Authorization: Bearer <access-token>     │
  ├─────────────────────────────────────────>│ kiểm tra token cho request
  │                                          │ tạo Authentication cho request
  │<──────────────── 200 OK ─────────────────┤
  │                                          │ không lưu SecurityContext
  │ GET /api/account                         │ qua HttpSession cho lần sau
  │ Authorization: Bearer <access-token>     │
  ├─────────────────────────────────────────>│ kiểm tra lại bằng chứng
  │<──────────────── 200 OK ─────────────────┤
```

Trong sơ đồ stateless, chữ `<access-token>` chỉ là ký hiệu minh họa luồng, không phải token thật. Có nhiều cơ chế credentials, chẳng hạn HTTP Basic hay mTLS, không nhất thiết phải là JWT.

**Định nghĩa cẩn thận:**

- **Stateful:** server hoặc kho trạng thái phía server lưu thông tin phiên đăng nhập giữa nhiều request; client thường giữ một **định danh phiên** trỏ tới trạng thái đó.
- **Stateless (với security context):** server xử lý request dựa vào bằng chứng kèm request, không cần lấy phiên xác thực của cùng user đã lưu từ một request trước. Nó vẫn tạo `Authentication`/`SecurityContext` **cho request hiện tại**.
- **Không có trạng thái nào trong cả hệ thống** không phải mục tiêu hay cam kết của “stateless”. Server vẫn có cấu hình, kho người dùng, khóa ký, cache, rate limits, audit, và đôi khi phải hỏi hệ thống ngoài để xác minh token.

Sự khác biệt **không nằm ở việc frontend là SPA hay web truyền thống**. SPA có thể dùng cookie session; web server cũng có thể dùng bearer token; quan trọng là **ai giữ và tra cứu trạng thái xác thực giữa các request**.

## 3. Stateful: session ID nằm ở client, SecurityContext thường ở server

Với Spring Security Servlet, một luồng form login điển hình:

1. Client gửi username/password qua HTTPS cùng CSRF token nếu áp dụng CSRF protection.
2. Server xác thực và tạo `Authentication` chứa principal, authorities và các thông tin cần thiết.
3. Cơ chế security context persistence lưu `SecurityContext` để có thể khôi phục ở request sau, thường vào `HttpSession`.
4. Server gửi session cookie (thường tên `JSESSIONID` trong Servlet container) chứa **session ID**, chứ thông thường không phải cả `Authentication`/password.
5. Browser tự động gửi cookie phù hợp domain/path/các thuộc tính cookie ở request tiếp theo.
6. Server dùng ID để tìm session, khôi phục `SecurityContext` và tiếp tục kiểm tra authorization.
7. Logout/session hết hạn/vô hiệu hóa session làm server không còn công nhận ID tương ứng.

### Phân biệt các đối tượng

| Khái niệm | Vị trí/thời gian điển hình | Chứa gì? |
| --- | --- | --- |
| `HttpSession` | Server-side session store, có thể nằm trong RAM hoặc Redis | Dữ liệu phiên qua nhiều request; có thể gồm Spring Security context |
| `JSESSIONID` cookie | Browser; gửi kèm request phù hợp | Thường chỉ là định danh session mờ, không phải token JWT |
| `SecurityContext` | Ngữ cảnh security ở request và có thể được lưu trong session | `Authentication` và trạng thái security liên quan |
| `Authentication` | Tạo khi xác thực hoặc khôi phục từ context | Principal, credentials/authorities, trạng thái xác thực |
| CSRF token | Một giá trị bảo vệ request thay đổi trạng thái | Giúp chống giả mạo request; không phải session ID |
| Access token | Client mang tới resource server | Bằng chứng quyền truy cập, có thể tự chứa claims hoặc là chuỗi mờ |

**Cookie không đồng nghĩa stateful.** Một cookie có thể chứa session ID, cũng có thể chứa một signed token; ngược lại, server có thể nhận session ID qua cơ chế khác. Khi so sánh mô hình, cần xem **giá trị cookie biểu diễn điều gì** và server có cần tra session phía mình không.

### Khi có nhiều instance

Nếu server A giữ session trong RAM riêng còn request sau vào server B, B có thể không tìm thấy session đó. Các cách xử lý gồm:

- Dùng một **session store chia sẻ** (ví dụ Spring Session + Redis) để nhiều instance truy cập cùng trạng thái.
- Dùng sticky sessions tại load balancer nếu chấp nhận coupling vào instance và giới hạn failover.
- Thiết kế logout, expiration, session serialization/consistency, bảo vệ kho session và xử lý lúc Redis/database không sẵn sàng.

**Session store dùng Redis vẫn là stateful.** Nó chỉ chuyển vị trí lưu từ bộ nhớ của từng instance sang kho chia sẻ, không làm ứng dụng tự động thành stateless.

### Ưu điểm và giới hạn

- Dễ làm **logout/revoke gần tức thời** bằng cách vô hiệu session tương ứng (với điều kiện các instance cùng kiểm tra kho session).
- Có thể quản lý concurrent sessions và timeout tập trung.
- Browser UX thuận tiện vì cookie được tự gửi, không phải gắn Authorization header bằng code ở mỗi call.
- Cần bảo vệ kho session, session ID, session fixation, CSRF và cấu hình cookie.
- Hạ tầng có thể cần store phân tán khi scale; mỗi request có thể cần lookup tới store hoặc cache.

## 4. Stateless: bằng chứng xác thực đến cùng từng request

Trong mô hình API stateless, client mang credentials/bằng chứng mỗi request; server tạo security context để xử lý request đó nhưng không dựa vào một `HttpSession` chứa security context từ request trước.

Ví dụ:

**HTTP Basic:** mỗi request gửi header `Authorization: Basic ...` chứa username/password được Base64-encode, **không mã hóa**. Server kiểm tra thông tin cho mỗi request. Đây là cách đơn giản để minh họa stateless nhưng không phải lựa chọn UX/bảo mật phù hợp cho đa số API công khai; cần HTTPS và chiến lược credentials phù hợp.

**Bearer token (ví dụ JWT):** mỗi request gửi `Authorization: Bearer ...`. Resource server kiểm tra token theo cấu hình: chữ ký/thuật toán/khoá, issuer, thời hạn, audience và các claim/authority cần thiết. Không cần session lưu login ở chính resource server nếu token và chính sách được xác minh từ request.

**Opaque reference token:** resource server có thể hỏi authorization server bằng introspection để biết token còn hợp lệ, phạm vi/quyền và user nào. Resource server vẫn có thể **không giữ phiên của user**, nhưng toàn hệ thống vẫn phụ thuộc trạng thái ở authorization server và có thể thêm cache introspection.

Vì vậy, “stateless” thường là phát biểu **về service/resource server cụ thể** và cơ chế persistence của security context, không phải khẳng định mọi thành phần đều không cần state.

### JWT không phải điều kiện bắt buộc của stateless

Có thể xây dựng API stateless bằng HTTP Basic, mTLS hoặc bearer access token. Ngược lại, một hệ thống dùng JWT vẫn có state nếu nó lưu token/session phía server, dùng denylist, refresh-token store hoặc tra quyền từ cơ sở dữ liệu. Không nên kết luận “có JWT = hoàn toàn stateless”, hoặc “có cookie = chắc chắn stateful”.

**JWT chỉ là một định dạng token**, không phải protocol đăng nhập, không tự bảo vệ XSS/CSRF, không tự cho phép refresh/revoke. Việc chọn JWT/opaque token nằm sau quyết định kiến trúc identity, trust và lifecycle.

### Revocation và logout trong stateless token

Nếu resource server tin một JWT tự chứa claims còn hạn, việc người dùng bấm “Logout” ở client có thể chỉ xóa token trên thiết bị; một bản sao token bị đánh cắp vẫn có thể dùng tới khi hết hạn. Các cách giảm rủi ro:

- Access token sống ngắn; refresh token có quy trình kiểm tra/rotate/revoke rõ ràng.
- Introspection hoặc denylist/revocation state cho use case đòi thu hồi ngay.
- Giới hạn scope/audience, kiểm tra issuer, chữ ký, expiry, clock skew và key rotation.
- Giám sát replay, bảo vệ token trên client và TLS.

**Đánh đổi:** muốn thu hồi ngay thường phải thêm một nguồn trạng thái/tra cứu; khi đó resource server có thể không còn hoàn toàn self-contained dù API vẫn không dùng HttpSession.

## 5. So sánh theo tiêu chí kiến trúc

| Tiêu chí | Stateful session | Stateless security context |
| --- | --- | --- |
| Bằng chứng client mang theo | Thường cookie chứa session ID mờ | Credentials/token kèm từng request (Basic/Bearer/mTLS...) |
| Thông tin xác thực giữa requests | Server/session store nắm trạng thái phiên | Không dựa vào phiên login trước ở resource server |
| Xác nhận request kế tiếp | Tra session và khôi phục context | Kiểm tra bằng chứng kèm request |
| Quyền thay đổi/revoke | Có thể vô hiệu session trên server | Tùy loại token; tự chứa JWT có thể cần expiry/denylist/introspection |
| Mở rộng nhiều instance | Cần chia sẻ/sticky session nếu state cục bộ | Dễ scale stateless resource server hơn, nhưng vẫn có dependencies |
| Chi phí mỗi request | Có thể phải tra session/store | Có thể phải xác minh chữ ký/token hoặc gọi introspection/identity |
| CSRF | Quan trọng khi cookie tự gửi để xác thực | Vẫn quan trọng nếu cookies hoặc browser tự gửi credentials; header bearer có tính chất khác |
| XSS | Cookie HttpOnly có thể giảm khả năng đọc session ID bằng JS | Token lưu trong JS-accessible storage có nguy cơ bị lấy qua XSS |
| Logout | Invalidating session có thể chặn các request tiếp theo | Xóa phía client không nhất thiết vô hiệu token đã phát |
| Session fixation | Cần rotation/bảo vệ session ID | Không dựa vào session ID cho API; vẫn phải bảo vệ token replay |
| Client phổ biến | Browser/server-rendered, admin UI | Service-to-service, mobile/SPA/API với IdP tùy yêu cầu |
| Bản chất quyết định | **Nơi giữ state qua request** | **Không khôi phục login từ server session qua request** |

Không có mô hình nào “nhanh hơn tuyệt đối” hay “an toàn hơn tuyệt đối”. Với số lượng request, token verification, session store latency, requirements về revoke và client/browser, kết quả thực tế có thể khác nhau.

## 6. Spring Security: SessionCreationPolicy điều khiển điều gì?

Trong Spring Security Servlet, `SessionCreationPolicy` có các giá trị thường gặp:

| Policy | Ý nghĩa |
| --- | --- |
| `ALWAYS` | Spring Security luôn tạo `HttpSession` theo policy này |
| `IF_REQUIRED` | Chỉ tạo session khi Spring Security cần |
| `NEVER` | Spring Security không tự tạo session nhưng **có thể dùng session đã tồn tại** |
| `STATELESS` | Spring Security không tạo session và **không dùng session để lấy `SecurityContext`** |

Điểm quan trọng nhất của bài:

```java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

Đây là **fragment cấu hình**, không phải chương trình độc lập; cần import `org.springframework.security.config.http.SessionCreationPolicy` và đặt trong `SecurityFilterChain`.

Theo hành vi Spring Security được tài liệu mô tả, dùng `STATELESS` khiến SecurityContextRepository sử dụng `NullSecurityContextRepository` trong flow stateless thích hợp và tránh lưu request phục vụ login vào HttpSession. Nó **không có nghĩa không một thành phần nào trong toàn ứng dụng có thể tạo HttpSession**; code ứng dụng, servlet/framework khác hoặc cơ chế CSRF/session tùy cấu hình vẫn cần được xem xét.

### STATELESS không tự xác thực request

Nếu chỉ cấu hình `STATELESS` mà không bật `httpBasic`, resource server JWT, OAuth2, mTLS hoặc cơ chế AuthenticationFilter phù hợp, server không có cách tự suy ra người gọi là ai. Session policy quyết định cách persistence, **không phải** cơ chế kiểm chứng credentials.

Cũng không nên dùng `NEVER` như từ đồng nghĩa với stateless: `NEVER` vẫn có thể đọc một session có sẵn và khôi phục security context.

### SecurityContext vẫn tồn tại trong request stateless

Ngay cả khi không lưu qua session, Spring Security vẫn xử lý `Authentication`/`SecurityContext` **trong phạm vi request hiện tại** để thực hiện authorization. “Stateless” ở đây không có nghĩa framework không có `Authentication` trong memory.

Với Spring Security 6, các lớp như `SecurityContextHolderFilter`/`SecurityContextRepository` chịu trách nhiệm tải/lưu context theo cơ chế cấu hình. Nếu bạn tự triển khai filter xác thực, phải theo đúng API và semantics của version đang dùng, bao gồm việc có cần lưu context tường minh vào repository hay không. Không áp dụng nguyên trạng ví dụ Spring Security 5 cũ cho Spring Security 6 mà chưa kiểm tra.

## 7. Ví dụ runnable Java 17: một ứng dụng có cả stateful và stateless

Ta tạo ứng dụng Spring Boot **3.3.13**, Java 17+, Gradle 8.x. Ứng dụng cố ý có **hai `SecurityFilterChain`**:

- **API:** tất cả `/api/**` dùng HTTP Basic mỗi request và `SessionCreationPolicy.STATELESS`; không lấy thông tin đăng nhập từ session của browser.
- **Browser:** `/browser/**` dùng form login mặc định và `HttpSession` để giữ đăng nhập qua nhiều request; `/public` công khai.
- Chuỗi API ở `@Order(1)` được xét **trước** chuỗi tổng quát ở `@Order(2)` để tránh chain browser che chain API.

Đây là một ứng dụng có **hai chính sách cho hai nhóm request**; không có mâu thuẫn khi một backend sử dụng cả hai.

### 7.1. Cấu trúc và build

```text
session-state-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/sessionstate/
    │   ├── SessionStateApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/sessionstate/
        └── SessionStateTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'session-state-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
```

### 7.2. Main class

**`src/main/java/com/example/sessionstate/SessionStateApplication.java`**

```java
package com.example.sessionstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionStateApplication.class, args);
    }
}
```

### 7.3. SecurityConfiguration: hai chains, hai nơi giữ authentication state

**`src/main/java/com/example/sessionstate/SecurityConfiguration.java`**

```java
package com.example.sessionstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain statelessApiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSessionChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

Giải thích từng quyết định:

1. `@Order(1)` và `securityMatcher("/api/**")` đặt API chain lên trước, chỉ áp dụng cho nhóm API.
2. `SessionCreationPolicy.STATELESS` chỉ đạo Spring Security không dựa vào `HttpSession` lưu login để xác thực API. HTTP Basic gửi credentials ở **mỗi request**.
3. `httpBasic(withDefaults())` kích hoạt xử lý header `Authorization: Basic ...`; `formLogin(...disable())` tránh redirect sang login form trên API. Một request API không có Basic credentials sẽ thường nhận 401.
4. `@Order(2)` là chain tổng quát cho phần còn lại. `formLogin(withDefaults())` tạo/trình bày trang login và dùng session để duy trì login trình duyệt. `/public` không cần đăng nhập.
5. User store dùng `{noop}` chỉ để demo cục bộ. Không dùng mật khẩu rõ, HTTP không TLS hoặc tài khoản cứng trong production.
6. CSRF protection **giữ mặc định trên cả hai chain**. Các endpoint demo dùng GET; browser form login POST sử dụng CSRF token được form và test helper hỗ trợ. Không tắt CSRF một cách máy móc chỉ vì API mang nhãn stateless, nhất là khi browser có thể tự gửi Basic/cookie credentials.

**Lưu ý production:** vì chain API dùng HTTP Basic, browser có thể tự gửi lại Basic credentials trong một số tình huống. Đánh giá CSRF theo cách credentials được trình duyệt gửi thực tế; nếu chuyển sang bearer token truyền tường minh trong Authorization header và không dùng ambient cookies, CSRF threat model sẽ khác. Trong ví dụ này giữ mặc định bảo vệ các HTTP method không an toàn.

### 7.4. Controller chung

**`src/main/java/com/example/sessionstate/DemoController.java`**

```java
package com.example.sessionstate;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/browser/me")
    public String browserMe(Principal principal) {
        return "browser " + principal.getName();
    }

    @GetMapping("/api/me")
    public String apiMe(Principal principal) {
        return "api " + principal.getName();
    }
}
```

`Principal` được cung cấp sau khi request đã xác thực thành công qua chain tương ứng. Đây là ví dụ đọc tên hiện tại, không dùng principal name làm bằng chứng quyền sở hữu tài nguyên khác.

### 7.5. Chạy và quan sát

Cài JDK 17+, Gradle 8.x phù hợp, rồi tại thư mục `session-state-demo` chạy:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper đúng version, có thể dùng `./gradlew test`, `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat test`, `gradlew.bat bootRun` (Windows). Các class cần dependency Spring nên lệnh `javac`/`java` đơn lẻ không đủ nếu thiếu classpath.

**Quan sát browser stateful:**

1. Trên trình duyệt mở `http://localhost:8080/browser/me`.
2. Khi chưa có session đăng nhập, Spring Security thường chuyển đến `/login`.
3. Nhập `alice` / `alice123` trong form login demo.
4. Sau khi đăng nhập, mở lại `/browser/me`. Server khôi phục Authentication từ `HttpSession` thông qua session ID cookie, nên response có body `browser alice`.
5. Mở tab mới trong cùng browser profile với cùng cookie vẫn có thể dùng session; sau logout/session hết hạn, request lại cần đăng nhập.

**Quan sát API stateless bằng curl:**

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
```

Kỳ vọng theo thứ tự:

1. `401 Unauthorized`, vì không có credentials.
2. `200 OK`, body `api alice`, vì có HTTP Basic hợp lệ trong request.
3. `401 Unauthorized` lần nữa, vì lần gọi trước **không tạo phiên đăng nhập cho API** và curl cuối không gửi Basic credentials.

**Quan sát ranh giới hai chains:** sau khi đăng nhập browser, chỉ gửi cookie session đến `/api/me` (không có Basic credentials) không làm chain API công nhận login; chain API được cấu hình stateless và sẽ yêu cầu xác thực riêng. Trên thực tế, browser có thể gửi một số headers/cookies khác, nên dùng `MockMvc` bên dưới để thử ranh giới có kiểm soát.

Bảng tóm tắt kết quả:

| Kịch bản | Endpoint | Bằng chứng gửi kèm | Dự kiến |
| --- | --- | --- | --- |
| Chưa đăng nhập | `GET /public` | Không | 200, `public` |
| Browser chưa đăng nhập | `GET /browser/me` | Không | 302 chuyển đến login (với form login mặc định) |
| Browser đã login | `GET /browser/me` | Session cookie hợp lệ | 200, `browser alice` |
| API thiếu Basic | `GET /api/me` | Không | 401 |
| API có Basic | `GET /api/me` | Username/password đúng | 200, `api alice` |
| API sau request thành công | `GET /api/me` | Không gửi Basic | 401 |
| API nhận session browser nhưng không Basic | `GET /api/me` | Chỉ session cookie | 401 |

Các status có thể thay đổi nếu bạn thêm custom entry point, thay đổi đường login hoặc bật cơ chế identity khác; bảng này phản ánh đúng cấu hình demo.

### 7.6. Kiểm thử sự khác biệt bằng MockMvc

**`src/test/java/com/example/sessionstate/SessionStateTests.java`**

```java
package com.example.sessionstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStateTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void browserEndpointRedirectsBeforeLogin() throws Exception {
        mvc.perform(get("/browser/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void browserLoginCreatesReusableSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/browser/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("browser alice"));
    }

    @Test
    void apiRequiresCredentialsOnEveryRequest() throws Exception {
        MvcResult success = mvc.perform(
                get("/api/me").with(httpBasic("alice", "alice123"))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("api alice"))
            .andReturn();

        assertNull(success.getRequest().getSession(false));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void browserSessionDoesNotAuthenticateStatelessApi() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }
}
```

Trong Spring Security Test, helper `formLogin()` xây dựng request POST login có CSRF token hợp lệ; vì vậy ta có thể giữ CSRF protection và vẫn kiểm thử được login.

Những ý nghĩa quan trọng của bộ test:

- Test browser chứng minh login thành công có `HttpSession` và cùng session được sử dụng để truy cập request tiếp theo.
- Test API chứng minh chỉ request có `Authorization: Basic` hợp lệ thành công; không có bằng chứng ở request kế tiếp sẽ không được công nhận.
- Test cross-chain chứng minh việc browser có session **không phải nguồn xác thực cho stateless API chain**.
- `MockHttpSession` trong test thay cho session/cookie transport của servlet environment, **không** phải phép đo thực tế về cookie `Set-Cookie` trên mạng hoặc TLS/browser flags. Cần kiểm tra browser và hạ tầng thực tế riêng nếu triển khai.

## 8. Cookie/session security: stateful cần những bảo vệ nào?

Khi browser giữ một session ID, kẻ khác có ID đó có thể cố sử dụng phiên. Vì vậy:

1. **HTTPS và cookie `Secure`:** browser chỉ gửi cookie qua kết nối bảo mật khi được cấu hình đúng; production không truyền session ID qua HTTP không mã hóa.
2. **`HttpOnly`:** giảm nguy cơ JavaScript đọc session cookie khi có XSS (không ngăn hoàn toàn mọi tác động của XSS).
3. **`SameSite`:** giảm một số tình huống gửi cookie cross-site, nhưng không thay thiết kế CSRF protection.
4. **Path/Domain:** giới hạn nơi cookie được gửi, tránh scope rộng không cần thiết.
5. **Session fixation protection:** đổi session identifier sau khi login/đổi mức quyền. Spring Security có cơ chế bảo vệ session fixation; kiểm tra theo version/config.
6. **Timeout, logout và invalidation:** giới hạn thời hạn phiên, vô hiệu session khi người dùng logout và theo dõi quyền bị thu hồi.
7. **CSRF token:** bảo vệ các request thay đổi trạng thái khi browser tự gửi cookie; cả request login/logout cũng có thể cần CSRF protection.
8. **XSS, CSP và audit:** không để user content tùy ý thực thi script; bảo vệ dữ liệu ứng dụng ngay cả khi cookie HttpOnly.

**Một điểm cần nhớ:** người dùng bấm logout thường làm session không còn hiệu lực ở server. Xóa cookie riêng ở client không thay thế việc vô hiệu hóa server session. Trong Spring Security, logout thường xử lý POST với CSRF token mặc định; dùng GET logout tùy tiện dễ mở rủi ro logout CSRF.

### CSRF khi dùng JWT/Bearer thì sao?

Nếu bearer token được JavaScript chủ động đính kèm vào `Authorization` header và browser không tự phát kèm credentials tương đương cho cross-site request, CSRF threat model khác với cookie session. Nhưng nếu token được đặt trong cookie và tự gửi, **rủi ro CSRF có thể quay trở lại dù token là JWT**.

Đừng dùng quy tắc “stateless thì tắt CSRF”. Hãy xác định browser có thể **tự gửi bằng chứng xác thực** trong request do trang khác khởi tạo hay không, endpoints nào thay đổi trạng thái và cơ chế bảo vệ nào đang dùng. Ví dụ runnable giữ CSRF mặc định.

### XSS và token storage

Lưu access token trong `localStorage` khiến JavaScript có thể đọc token, nên khi có XSS, token có thể bị đánh cắp. Cookie `HttpOnly` giảm khả năng script đọc cookie nhưng vẫn có thể bị trình duyệt gửi trong request khi có XSS/CSRF nếu bảo vệ không đủ. Chọn cách lưu token cần xét cả XSS, CSRF, thời hạn token, refresh flow, SameSite, CORS và kiến trúc client.

## 9. Khi dùng OAuth2 Resource Server / JWT thật

HTTP Basic trong demo chỉ dùng để **quan sát request stateless** vì có thể chạy ngay mà không cần Identity Provider. Một API production thường chọn OAuth2 Resource Server với access token do Authorization Server/IdP phát hành.

Ví dụ **fragment cấu hình khái niệm**:

```java
@Bean
@Order(1)
SecurityFilterChain jwtApiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
```

Đây là **fragment, không phải chương trình runnable độc lập**; cần dependency `spring-boot-starter-oauth2-resource-server`, các import và cấu hình issuer/JWK source thực tế từ IdP được tin cậy. Không chèn thêm bean này vào ứng dụng demo mục 7 nếu chưa bỏ/thay API chain cũ. Với JWT thật:

- Xác thực token signature, algorithm, issuer, expiration và audience theo chính sách; Spring Security có một số validator mặc định nhưng audience thường cần cấu hình xác minh phù hợp.
- Mapping claims như scopes, roles, groups thành authorities phải rõ ràng; không tự suy ra mọi claim `roles` đều là `ROLE_ADMIN`.
- Giới hạn scopes/audience; access token chỉ cấp đúng tài nguyên và hành động.
- Thiết kế refresh, revoke, key rotation, xử lý token hết hạn và clock skew.
- Bảo vệ token khi truyền/lưu và chống lộ thông tin qua log.

Với **opaque token**, có thể dùng token introspection thay vì JWT self-validation; một API có thể không giữ session nhưng vẫn gọi authorization server hoặc cache kết quả introspection. Nơi giữ và tra cứu trạng thái **vẫn phải được mô tả ở cấp hệ thống**, không chỉ nhìn kiểu token.

## 10. Chọn mô hình theo yêu cầu thay vì theo trào lưu

### Trường hợp A: ứng dụng quản trị browser

Người dùng đăng nhập qua form, muốn logout ngay, có nhiều thao tác nhạy cảm, cần timeout phiên, có thể dùng session store chia sẻ. Stateful session là lựa chọn dễ quản trị nếu triển khai cookie và CSRF đúng cách. Nên cân nhắc session fixation, session hijacking, quản lý nhiều phiên, sự sẵn sàng của session store và chính sách re-authentication cho thao tác nhạy cảm.

### Trường hợp B: API phục vụ mobile/service

Client gửi bearer access token mỗi request, resource server xác thực token và không giữ session login; dễ scale các instance, dễ có ranh giới API, nhưng phải giải quyết thời hạn, refresh/revoke, scopes/audience, key rotation và bảo vệ token. Nếu phải thu hồi lập tức hoặc quyền thay đổi liên tục, token tự chứa dài hạn gây khó khăn.

### Trường hợp C: một backend phục vụ browser và API

Có thể áp dụng hai chains như demo:

```text
Request /api/**         → SecurityFilterChain #1 → STATELESS + Basic/Bearer
Request /browser/**     → SecurityFilterChain #2 → FormLogin + HttpSession
Request /public         → SecurityFilterChain #2 → permitAll
```

**Thứ tự chain rất quan trọng.** Nếu chain tổng quát đứng trước, API chain có thể không được chọn. `securityMatcher` xác định chain phù hợp; `requestMatchers` bên trong chain chỉ chọn authorization rule. Một chain ở cuối bao phủ còn lại giúp tránh request nằm ngoài mọi Spring Security chain.

### Trường hợp D: scale stateful bằng Redis

Cần nhiều server và giữ trải nghiệm login/session truyền thống? Dùng Spring Session với Redis có thể cho các instance cùng truy cập phiên, giúp giảm phụ thuộc sticky sessions. Nhưng Redis/cluster, TTL, failover và security của store trở thành một phần kiến trúc. Đây vẫn là **stateful**, vì request cần tra trạng thái login được lưu phía server.

## 11. Hiểu đúng những tuyên bố thường gặp

| Tuyên bố | Đánh giá đúng |
| --- | --- |
| “HTTP stateless nên không thể dùng session” | Sai: ứng dụng xây dựng session bên trên HTTP |
| “Có cookie nghĩa là stateful” | Sai: cookie có thể mang ID phiên hoặc token tự chứa |
| “Stateless nghĩa là không có SecurityContext” | Sai: mỗi request vẫn có thể tạo Authentication/SecurityContext |
| “`STATELESS` tự xác thực JWT” | Sai: cần cấu hình mechanism JWT/OAuth2 Resource Server riêng |
| “`NEVER` và `STATELESS` giống nhau” | Sai: NEVER có thể dùng session đã tồn tại |
| “Có JWT thì logout sẽ vô hiệu token ngay” | Sai: còn phụ thuộc expiry/revocation/introspection |
| “Stateless đồng nghĩa tắt CSRF” | Sai: tùy cách browser tự gửi credentials |
| “Dùng Redis cho session là stateless” | Sai: state chuyển vị trí, vẫn được tra qua ID |
| “Dùng HTTP Basic thì request sau tự đăng nhập” | Sai trong cấu hình STATELESS: phải gửi Basic credentials mỗi lần |
| “Server không giữ session nên chẳng có dữ liệu trạng thái nào” | Sai: vẫn có keys, user store, policy, cache, audit, token/refresh state ở hệ thống |
| “JWT luôn tốt hơn session” | Không có kết luận chung: chọn theo client, vận hành, revoke, quy mô và mối đe dọa |
| “Dùng form login là đủ, không cần CSRF” | Sai: form login/cookie flow cần đánh giá CSRF nghiêm túc |

### Cách chẩn đoán một request bất ngờ bị 401

1. Client có gửi cookie `JSESSIONID` hoặc `Authorization` header phù hợp với chain được chọn không?
2. Request khớp `SecurityFilterChain` nào? `@Order` và `securityMatcher` có như mong đợi không?
3. Chain đó dùng `STATELESS`, `NEVER` hay `IF_REQUIRED`? Có dùng `HttpSessionSecurityContextRepository` hay `NullSecurityContextRepository`?
4. Session ID có tồn tại, hết hạn, bị invalidate, mất khi chuyển instance hoặc không có trong session store không?
5. Token có hết hạn, sai issuer/audience, sai chữ ký, bị revoke hoặc không map được authorities không?
6. Nếu dùng browser cookie, có request bị CSRF chặn và trả **403** thay vì 401 không?
7. Có proxy/load balancer đổi domain/path/scheme, làm browser không gửi cookie đúng phạm vi không?

Không log session ID, Authorization header, password, refresh token hoặc JWT đầy đủ trong log sản xuất. Chỉ lưu những thông tin cần thiết đã được lược bỏ hoặc hash phù hợp để điều tra.

## 12. Bài tập tự kiểm tra

**1. Nếu browser giữ cookie `JSESSIONID`, người dùng đã đăng nhập có thể dùng lại session bằng cách nào?**

Server nhận session ID từ cookie, tra `HttpSession` đã lưu `SecurityContext`, khôi phục `Authentication` rồi đánh giá authorization. Browser chỉ lưu ID, không cần gửi lại password trên mỗi request.

**2. Nếu server dùng Redis làm session store, hệ thống có trở thành stateless không?**

Không. Redis là nơi chứa state phía server cho các request kế tiếp. Nó hỗ trợ chia sẻ trạng thái giữa nhiều instance nhưng mô hình vẫn stateful.

**3. Vì sao `SessionCreationPolicy.NEVER` chưa đủ để cam kết không dùng session?**

Vì nó không tạo HttpSession cho Spring Security nhưng vẫn có thể sử dụng session đã tồn tại. `STATELESS` mới diễn đạt chính sách không dùng HttpSession để lấy security context.

**4. Một API dùng JWT trong `Authorization` header có nhất thiết không lưu trạng thái nào không?**

Không. Resource server có thể kiểm tra JWT tự chứa không cần phiên, nhưng hệ thống vẫn có keys, permissions, refresh token store, revocation/denylist, cache hoặc introspection tùy thiết kế.

**5. Vì sao API stateless trong demo trả 401 sau một request Basic thành công?**

Vì request sau không gửi Basic credentials và Spring Security không lấy phiên đăng nhập từ request trước. Authentication của request thành công không được lưu để cấp quyền cho request tiếp theo.

**6. Vì sao một cookie có thể gây rủi ro CSRF?**

Browser có thể tự gửi cookie khi tạo request thỏa thuộc tính cookie, kể cả request được kích hoạt từ nguồn không tin cậy. CSRF token và chính sách SameSite/Origin phù hợp giúp giảm nguy cơ; không chỉ dựa vào chữ “stateful/stateless”.

**7. JWT có thể bị dùng tiếp sau khi người dùng bấm logout không?**

Có thể nếu token còn hiệu lực và resource server tiếp tục chấp nhận nó. Cần expiry ngắn, revocation/introspection hoặc cơ chế khác nếu yêu cầu chặn ngay.

**8. Trong demo, tại sao login ở `/browser/me` không tự cho phép `/api/me`?**

Vì request `/api/**` được chain riêng `@Order(1)` xử lý với `STATELESS` và HTTP Basic. Security context trong HttpSession của browser không được API chain dùng làm nguồn xác thực.

**9. Có nên tắt CSRF bất cứ khi nào cấu hình `STATELESS`?**

Không. Cần xem bằng chứng xác thực có tự động được browser gửi trong request cross-site không. Basic authentication hoặc bearer token trong cookie vẫn có thể cần CSRF mitigation.

**10. Một hệ thống yêu cầu thu hồi quyền gần tức thì cho mọi API request có phù hợp JWT self-contained dài hạn không?**

Thường không thuận tiện: một JWT tự chứa chưa hết hạn có thể còn được chấp nhận. Nên xét access token ngắn hạn, introspection hoặc cơ chế revoke/denylist phù hợp với yêu cầu.

## 13. Ghi nhớ

- **Stateful / stateless là quyết định về nơi giữ trạng thái xác thực giữa các request**, không phải nhãn “có/không có cookie” hay “JWT/không JWT”.
- **Stateful:** client thường giữ session ID, server giữ session và Authentication; request sau tra lại state bằng ID.
- **Stateless:** mỗi request mang bằng chứng xác thực, server kiểm tra trong request đó và không cần khôi phục security context từ phiên login trước.
- `SessionCreationPolicy.STATELESS` không tự bật JWT, không có nghĩa toàn ứng dụng không bao giờ tạo HttpSession, và không tự quyết định CSRF threat model.
- HTTP Basic là minh họa stateless đơn giản nhưng gửi lại credentials mỗi request; API production thường dùng token/mTLS phù hợp hơn.
- **Cookie session cần CSRF, XSS, session fixation và cookie flags được cấu hình đúng.** Token tự chứa cũng cần expiry, scope, issuer/audience và chiến lược revoke.
- Stateful session chia sẻ qua Redis **vẫn stateful**. Stateless resource server dựa vào introspection/denylist vẫn phụ thuộc state ở thành phần khác.
- Một ứng dụng có thể dùng **stateful cho browser, stateless cho API** nếu định nghĩa rõ security chains, phạm vi và thứ tự.
- Quyết định cuối cùng dựa trên yêu cầu về client, trải nghiệm, kiểm soát phiên, vận hành, scaling, logout, bảo mật và chi phí.

### Tài liệu chính thức

- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Session Management và cấu hình HttpSession: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Java Configuration, multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing Form Based Authentication với MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Session — Spring Session và session sharing: https://docs.spring.io/spring-session/reference/
