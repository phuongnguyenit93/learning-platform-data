# Xác thực ẩn danh bằng AnonymousAuthenticationWebFilter

> **Phạm vi:** Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux (reactive) và Java 17+. Bài này giải thích **anonymous authentication** trong luồng reactive, vai trò của `AnonymousAuthenticationWebFilter`, cách cấu hình `ServerHttpSecurity.anonymous(...)`, cách đọc danh tính ẩn danh từ Reactor Context và cách phân biệt người truy cập công khai với người dùng đã đăng nhập.

## 1. “Ẩn danh” có phải là “đã xác thực” không?

Một API thường phục vụ đồng thời hai loại người gọi:

- **Khách chưa đăng nhập:** chưa cung cấp credential hợp lệ; có thể được phép xem trang công khai, danh mục sản phẩm hoặc tài liệu.
- **Người dùng đã đăng nhập:** danh tính được xác minh bằng HTTP Basic, form login, JWT hay cơ chế khác; có thể truy cập dữ liệu hoặc thao tác cần cấp quyền.

Spring Security cung cấp một cơ chế gọi là **anonymous authentication**: khi chưa có `Authentication` thật trong security context, framework *có thể* tạo một đối tượng `AnonymousAuthenticationToken` đại diện cho khách. Mục đích là cho một số phần của hệ thống cùng nhìn thấy một `Authentication` với danh tính/authority thống nhất, thay vì mỗi chỗ phải tự chọn một chuỗi như `"guest"`.

**Cảnh báo quan trọng:** có một `AnonymousAuthenticationToken` trong context **không** có nghĩa khách đã chứng minh danh tính. Nó không tạo tài khoản, không xác minh mật khẩu, không gán danh tính cá nhân và không cấp quyền cho vùng bảo vệ.

### Điểm đặc thù của WebFlux

Trong WebFlux, thành phần thực hiện việc này là:

```java
org.springframework.security.web.server.authentication.AnonymousAuthenticationWebFilter
```

Đây là một `org.springframework.web.server.WebFilter`, khác với `AnonymousAuthenticationFilter` của Servlet/MVC. Nó kiểm tra liệu `ReactiveSecurityContextHolder` đã có `Authentication` hay chưa; nếu chưa, nó có thể cung cấp một `AnonymousAuthenticationToken` cho phần xử lý phía sau.

**Đừng mặc định WebFlux luôn bật anonymous authentication.** Javadoc `ServerHttpSecurity.anonymous(Customizer)` của Spring Security 6.x mô tả anonymous authentication **bị tắt theo mặc định** trong reactive DSL; muốn dùng hãy khai báo tường minh `.anonymous(Customizer.withDefaults())` hoặc một cấu hình `anonymous(...)` cụ thể. Từ việc một endpoint `permitAll()` trả 200 **không suy ra** rằng context đang có anonymous token.

## 2. AnonymousAuthenticationWebFilter vận hành ra sao?

Bộ lọc thuộc security web chain và hoạt động trong bối cảnh reactive:

```text
HTTP request
   |
   v
SecurityWebFilterChain
   |
   +--> Filter xác thực (Basic/form/JWT, nếu cấu hình)
   |         |
   |         +--> credential hợp lệ: Authentication người dùng thật
   |         +--> không có credential: có thể chưa có Authentication
   |
   +--> AnonymousAuthenticationWebFilter (khi BẬT)
   |         |
   |         +--> đã có Authentication: giữ nguyên
   |         +--> chưa có Authentication: tạo AnonymousAuthenticationToken
   |                  principal = "anonymousUser" (mặc định)
   |                  authorities = ["ROLE_ANONYMOUS"] (mặc định)
   |
   +--> Authorization / authorizeExchange(...)
   |         |
   |         +--> permitAll()       : không yêu cầu đăng nhập
   |         +--> authenticated()   : cần danh tính thực được xác thực
   |         +--> hasAuthority(...) : so sánh authority theo policy
   v
Controller -> Mono / Flux -> HTTP response
```

Sơ đồ trên mô tả **trường hợp anonymous đã được bật** trong chain. Nếu tắt, request thiếu credential có thể tiếp tục với security context rỗng tại một endpoint công khai.

Những thuộc tính mặc định của anonymous token khi sử dụng constructor `AnonymousAuthenticationWebFilter(String key)`:

| Thuộc tính | Giá trị/ý nghĩa |
|---|---|
| Loại token | `AnonymousAuthenticationToken` |
| Principal | Chuỗi `"anonymousUser"` |
| Authority | Một authority `"ROLE_ANONYMOUS"` |
| Key | Khóa nội bộ dùng tạo/xác định token anonymous, không phải mật khẩu của khách |
| Credentials | Không đại diện thông tin đăng nhập được người dùng cung cấp |
| Mức tin cậy | Khách ẩn danh; không phải xác thực danh tính người dùng |

Bạn có thể cấu hình principal, authority, key hoặc thay filter thông qua `ServerHttpSecurity.AnonymousSpec`. Nếu đã có `Authentication` do xác thực thành công, bộ lọc không được phép thay nó bằng khách ẩn danh.

### SecurityContext sống ở đâu?

Trong WebFlux, Spring Security dùng **Reactor Context** để đưa security context vào chuỗi reactive. Vì request có thể chuyển thread, không nên sử dụng `SecurityContextHolder` dựa trên ThreadLocal như một cách mặc định để đọc user trong service reactive. Khi cần, dùng:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
```

Đoạn này là **một mảnh code**, cần đặt trong method trả `Mono` cùng các import phù hợp. Nếu security context rỗng, nó có thể trả `Mono.empty()`. Khi `AnonymousAuthenticationWebFilter` được cấu hình và hoạt động trong chuỗi phù hợp, phần xử lý sau bộ lọc có thể nhận được anonymous authentication.

## 3. “Token có isAuthenticated() = true” có phải lỗ hổng không?

`AnonymousAuthenticationToken` kế thừa cơ chế token của Spring Security và thường có `Authentication.isAuthenticated() == true`. Cờ kỹ thuật này khiến nhiều người đọc nhầm rằng khách ẩn danh là “người đã đăng nhập”.

**Không được tự viết:**

```java
// Sai nếu dùng làm kiểm tra đã đăng nhập:
boolean isRealUser = authentication != null
    && authentication.isAuthenticated();
```

Vì một anonymous token cũng có thể làm biểu thức trên thành `true`.

Trong Spring Security 6.x, `AuthenticationTrustResolver` phân biệt anonymous với authentication thực. Cách minh họa:

```java
AuthenticationTrustResolver trust =
    new AuthenticationTrustResolverImpl();

boolean anonymous = trust.isAnonymous(authentication);
boolean authenticatedUser = trust.isAuthenticated(authentication);
```

Đây là code minh họa cần imports và một `Authentication` cụ thể. `isAuthenticated` của trust resolver kiểm tra không null, cờ authenticated và **không phải anonymous**. Spring Security sử dụng logic nhận biết mức tin cậy tương tự trong các quy tắc xác thực tiêu chuẩn; vì vậy không nên suy ra `authenticated()` cấp quyền cho anonymous chỉ từ cờ raw của token.

**Nguyên tắc:** dùng `.authenticated()`, `.hasRole(...)`, `.hasAuthority(...)` và các cơ chế authorization của Spring Security khi bảo vệ route. Đừng tự so sánh chuỗi `"anonymousUser"` hoặc chỉ dựa vào raw `isAuthenticated()` để đưa ra quyết định bảo mật.

## 4. Bốn khái niệm rất dễ nhầm

| Khái niệm | Điều nó thực hiện | Điều nó không bảo đảm |
|---|---|---|
| `permitAll()` | Cho phép request khớp rule đi tiếp mà không cần đăng nhập | Không tự tạo `AnonymousAuthenticationToken` |
| `anonymous(Customizer.withDefaults())` | Bật cơ chế tạo anonymous authentication khi chưa có auth thật | Không tự mở route hoặc thay thế `authorizeExchange` |
| `authenticated()` | Yêu cầu người gọi đã thực sự được xác thực theo policy | Không coi một anonymous token là đăng nhập thật |
| `hasAuthority("ROLE_ANONYMOUS")` | Yêu cầu đối tượng Authentication có authority đúng tên | Không tuyệt đối chứng minh khách *chưa* đăng nhập nếu hệ thống tùy chỉnh authority cho user thật |

Điểm cuối cần chú ý: `ROLE_ANONYMOUS` là một **authority**, không phải một phép kiểm “duy nhất khách không đăng nhập”. Ví dụ một user thật bị gán authority đó trong cấu hình sai thì điều kiện `hasAuthority("ROLE_ANONYMOUS")` cũng có thể khớp. Khi yêu cầu nghiệp vụ *chỉ khách chưa đăng nhập* được truy cập, hãy thiết kế một `ReactiveAuthorizationManager` xét mức tin cậy với `AuthenticationTrustResolver`, thay vì dựa vào tên role.

**Không có auth** và **anonymous auth** là hai trạng thái kỹ thuật khác nhau; cả hai đều không đủ để vào route `authenticated()`.

## 5. Bật anonymous authentication trong ServerHttpSecurity

Phần cấu hình trọng tâm:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated())
        .anonymous(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đoạn trên cần đặt vào lớp `@Configuration` của WebFlux, với các imports cần thiết. `.anonymous(Customizer.withDefaults())` chính là bước bật filter cho chain. `.httpBasic(...)` bật một cơ chế xác thực thực; `.authorizeExchange(...)` định nghĩa chính sách đường dẫn.

Không phải cứ dùng Spring Boot security starter thì cần anonymous token. Chỉ bật khi có nhu cầu cụ thể như đồng nhất context của khách hoặc kiểm thử các trạng thái danh tính; cấu hình thừa có thể làm người đọc nhầm kiểu principal và cách kiểm quyền.

### Tùy chỉnh danh tính anonymous

Có thể thay principal và authority theo nhu cầu kỹ thuật:

```java
.anonymous(anonymous -> anonymous
    .principal("guest")
    .authorities("ROLE_GUEST"))
```

Đây là mảnh DSL **thay thế** `anonymous(Customizer.withDefaults())`. Khi thay như trên, đừng tiếp tục kỳ vọng `principalName = "anonymousUser"` hoặc `ROLE_ANONYMOUS` xuất hiện. Đừng cấu hình `ROLE_ADMIN`/`ROLE_USER` cho khách ẩn danh; khi đó các rule dựa vào authority có thể cho khách quyền ngoài ý muốn.

`AnonymousSpec` còn hỗ trợ `key(String)` và `authenticationFilter(AnonymousAuthenticationWebFilter)`. Trong cấu hình thông thường, key mặc định được tạo nội bộ; **không chia key này cho browser như một credential**, và không cần tự tạo filter thứ hai khi builder đã thêm anonymous filter. Nếu thay filter, hãy hiểu rõ phạm vi và trách nhiệm của filter tùy chỉnh.

## 6. Demo hoàn chỉnh: so sánh anonymous và user đã đăng nhập

Ứng dụng dưới đây dùng **Spring Boot 3.3.13, Java 17+, Spring WebFlux và HTTP Basic**. Mục tiêu là quan sát security context bằng JSON mà không ghi token/cookie/mật khẩu. Chỉ chạy credential phát triển trên localhost hoặc HTTPS.

Cấu trúc dự án:

```text
anonymous-webflux-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/anonymous/AnonymousDemoApplication.java
  src/main/java/demo/anonymous/SecurityConfiguration.java
  src/test/java/demo/anonymous/AnonymousDemoTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'anonymous-webflux-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.anonymous'
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

**src/main/java/demo/anonymous/SecurityConfiguration.java**

```java
package demo.anonymous;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/api/public", "/api/whoami").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/guest-role").hasAuthority("ROLE_ANONYMOUS")
                .pathMatchers(HttpMethod.GET,
                    "/api/member").authenticated()
                .anyExchange().denyAll())
            .anonymous(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Giải thích: `/api/public` và `/api/whoami` cho phép khách, `/api/guest-role` minh họa rule dựa trên authority `ROLE_ANONYMOUS`, còn `/api/member` yêu cầu đăng nhập thật. Các HTTP method khác không được khai báo sẽ bị chặn bởi `denyAll()`. `formLogin` được tắt để quan sát HTTP Basic challenge trực tiếp bằng curl; đây là cấu hình demo API, không phải mẫu áp dụng cho mọi trang web.

**src/main/java/demo/anonymous/AnonymousDemoApplication.java**

```java
package demo.anonymous;

import java.security.Principal;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class AnonymousDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnonymousDemoApplication.class, args);
    }

    public record IdentityView(
            String principalName,
            String tokenType,
            boolean tokenAuthenticatedFlag,
            boolean anonymous,
            boolean authenticatedUser,
            List<String> authorities) {
    }

    @RestController
    static class Api {

        private static final AuthenticationTrustResolver TRUST =
            new AuthenticationTrustResolverImpl();

        @GetMapping("/api/public")
        Mono<String> publicMessage() {
            return Mono.just("public");
        }

        @GetMapping("/api/guest-role")
        Mono<String> guestRole() {
            return Mono.just("anonymous role");
        }

        @GetMapping("/api/member")
        Mono<String> member(Principal principal) {
            return Mono.just("member: " + principal.getName());
        }

        @GetMapping("/api/whoami")
        Mono<IdentityView> whoami() {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Api::asView)
                .switchIfEmpty(Mono.just(
                    new IdentityView("none", "none",
                        false, false, false, List.of())));
        }

        private static IdentityView asView(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
            return new IdentityView(
                auth.getName(),
                auth.getClass().getSimpleName(),
                auth.isAuthenticated(),
                TRUST.isAnonymous(auth),
                TRUST.isAuthenticated(auth),
                authorities);
        }
    }
}
```

**Vì sao ví dụ dùng `AuthenticationTrustResolver`?** Một anonymous token có thể trả `true` từ `auth.isAuthenticated()` nhưng `TRUST.isAnonymous(auth)` là `true` và `TRUST.isAuthenticated(auth)` là `false`. Các trường này cho phép bạn nhìn thấy khác biệt ngay trong JSON; ứng dụng không dùng response đó làm nơi xác thực hoặc phân quyền.

### 6.1 Chạy ứng dụng

Cần JDK 17+ và Gradle tương thích với Boot 3.3. Từ thư mục dự án:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper tương thích, dùng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Vì demo không cung cấp `ReactiveUserDetailsService` hay `ReactiveAuthenticationManager` riêng, Spring Boot có thể tạo tài khoản thử nghiệm `user` với password ngẫu nhiên. Đọc dòng `Using generated security password: ...` trong startup log; đây là mật khẩu của lần chạy hiện tại, chỉ dùng cho local.

### 6.2 Thử request không mang credential

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/whoami
curl -i http://localhost:8080/api/guest-role
curl -i -H "Accept: application/json" http://localhost:8080/api/member
```

Kết quả kỳ vọng:

| Endpoint | HTTP kỳ vọng | Ý nghĩa |
|---|---|---|
| `GET /api/public` | 200, body `public` | `permitAll()` |
| `GET /api/whoami` | 200, JSON báo anonymous | Có anonymous filter, context được điền cho guest |
| `GET /api/guest-role` | 200, body `anonymous role` | Guest mang authority `ROLE_ANONYMOUS` |
| `GET /api/member` | 401 | Guest không đáp ứng `authenticated()`, Basic challenge |

Phần JSON quan trọng của `/api/whoami` khi chưa có credential:

```json
{
  "principalName": "anonymousUser",
  "tokenType": "AnonymousAuthenticationToken",
  "tokenAuthenticatedFlag": true,
  "anonymous": true,
  "authenticatedUser": false,
  "authorities": ["ROLE_ANONYMOUS"]
}
```

Tùy server và HTTP headers, phần header khác nhau; JSON minh họa các giá trị được tạo từ chính code demo.

### 6.3 Thử request mang credential hợp lệ

Sử dụng curl CLI với `-u user` để công cụ hỏi password thay vì gõ vào history:

```bash
curl -i -u user http://localhost:8080/api/whoami
curl -i -u user http://localhost:8080/api/member
curl -i -u user http://localhost:8080/api/guest-role
```

Trong PowerShell có thể dùng `curl.exe` thay cho alias `curl`.

Kỳ vọng:

- `/api/whoami` trả HTTP 200 với `principalName = "user"`, `anonymous = false` và `authenticatedUser = true`.
- `/api/member` trả HTTP 200 với body `member: user`.
- `/api/guest-role` trả HTTP 403 vì user phát triển mặc định có `ROLE_USER`, **không** có `ROLE_ANONYMOUS`.

Ở đây `/api/guest-role` là **demo so khớp authority**, không phải bộ kiểm bảo đảm “chỉ guest” trong mọi hệ thống có tùy chỉnh authorities. Nếu business rule thực sự đòi hỏi khách chưa đăng nhập, cần kiểm theo trust resolver bằng policy phù hợp.

**Lưu ý khi gửi credential sai:** Một request có header HTTP Basic không hợp lệ có thể bị cơ chế authentication từ chối với HTTP 401 **ngay cả khi đường dẫn được đánh dấu `permitAll()`**. `permitAll()` quyết định authorization; nó không biến một lần xác thực thất bại thành login ẩn danh thành công.

## 7. Kiểm thử tự động bằng WebTestClient

Khi chạy test, sử dụng tài khoản test cố định từ Boot property, không phụ thuộc password ngẫu nhiên trong log. Không dùng password này trong production.

**src/test/java/demo/anonymous/AnonymousDemoTest.java**

```java
package demo.anonymous;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.security.user.name=alice",
        "spring.security.user.password=test-only-secret",
        "spring.security.user.roles=USER"
    }
)
@AutoConfigureWebTestClient
class AnonymousDemoTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsGuest() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void guestHasAnonymousAuthenticationToken() {
        client.get().uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("anonymousUser")
            .jsonPath("$.tokenType").isEqualTo("AnonymousAuthenticationToken")
            .jsonPath("$.tokenAuthenticatedFlag").isEqualTo(true)
            .jsonPath("$.anonymous").isEqualTo(true)
            .jsonPath("$.authenticatedUser").isEqualTo(false)
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_ANONYMOUS");
    }

    @Test
    void guestRoleMatchesAnonymousAuthority() {
        client.get().uri("/api/guest-role")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("anonymous role");
    }

    @Test
    void memberEndpointRequiresRealAuthentication() {
        client.get().uri("/api/member")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserReplacesAnonymousPrincipal() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("alice")
            .jsonPath("$.anonymous").isEqualTo(false)
            .jsonPath("$.authenticatedUser").isEqualTo(true);
    }

    @Test
    void memberCanEnterButLacksAnonymousAuthority() {
        client.get().uri("/api/member")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("member: alice");

        client.get().uri("/api/guest-role")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

Khi dependency đã tải, Gradle/JDK phù hợp và dự án giữ nguyên cấu hình demo, **6 phương thức test** được kỳ vọng pass. Test không phụ thuộc một database hay token server ngoài. Không khẳng định build đã chạy chỉ dựa vào nội dung bài; nếu build lỗi, cần đọc log cụ thể rồi xử lý phiên bản/dependency hoặc điểm sai trong source thực tế.

### 7.1 Thử tắt anonymous để quan sát khác biệt

Để so sánh, trong `SecurityConfiguration` hãy **thay duy nhất**:

```java
.anonymous(Customizer.withDefaults())
```

bằng:

```java
.anonymous(anonymous -> anonymous.disable())
```

Sau đó chạy test riêng: `/api/public` vẫn có thể trả 200 bởi `permitAll()`; `/api/whoami` không còn được bảo đảm có anonymous token để trả JSON như lúc bật; quy tắc `hasAuthority("ROLE_ANONYMOUS")` không thể trông cậy vào token do filter tạo. **Đừng áp nguyên bộ 6 test với kỳ vọng cũ rồi coi tất cả đều vẫn phải pass**; mục tiêu là chứng minh việc bật/tắt token ẩn danh độc lập với việc cho phép URL công khai.

### 7.2 Thử thay principal và authority

Thay dòng bật anonymous bằng:

```java
.anonymous(anonymous -> anonymous
    .principal("guest")
    .authorities("ROLE_GUEST"))
```

Kỳ vọng `/api/whoami` ở guest thể hiện `principalName = "guest"` và authority `ROLE_GUEST`. Nếu vẫn giữ matcher `hasAuthority("ROLE_ANONYMOUS")`, `/api/guest-role` **không còn khớp**; cần sửa matcher nếu chủ đích đổi policy. Cách thử này làm rõ constructor/config của filter ảnh hưởng giá trị ngữ cảnh, trong khi `permitAll` vẫn độc lập.

## 8. Nếu muốn đọc anonymous trong controller hoặc service

### 8.1 ReactiveSecurityContextHolder là cách trực tiếp

Trong controller/service được gọi từ một reactive request có security chain tương ứng:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("no-security-context");
}
```

Đây là **method minh họa**, không tự biên dịch nếu thiếu imports/class. Khi đã bật anonymous và request không có auth thật, kết quả thường là `anonymousUser` theo default. Khi anonymous chưa bật, publisher có thể rỗng; hãy xử lý một cách có chủ đích.

### 8.2 Vì sao `Principal` và `@AuthenticationPrincipal` có thể khác?

Trong Spring Security, `Authentication` cũng thực hiện giao diện `Principal` và có phương thức `getPrincipal()`. Khi anonymous filter tạo token mặc định:

- `Authentication` có thể là `AnonymousAuthenticationToken`.
- `Authentication.getPrincipal()` mặc định là chuỗi `"anonymousUser"`.
- Một handler dùng `@AuthenticationPrincipal UserDetails` không nên mặc định nhận được `UserDetails`: ở guest principal chỉ là `String`, nên không phù hợp kiểu.
- `ServerWebExchange.getPrincipal()` và `ReactiveSecurityContextHolder.getContext()` có thể phản ánh danh tính request dưới dạng reactive khi chain đã thiết lập context.

Ví dụ `@AuthenticationPrincipal Object user` có thể nhận principal kiểu String hoặc kiểu khác theo authentication đã cấu hình, nhưng code nghiệp vụ không nên tự ép kiểu tùy ý. Khi chỉ cần hiển thị “khách” hoặc “user”, tốt hơn ánh xạ từ `Authentication` đã được xác minh sang DTO nội bộ rồi xét `AuthenticationTrustResolver`.

### 8.3 Reactor Context không phải ThreadLocal

`publishOn` hay `subscribeOn` có thể làm đổi thread nhưng không mặc nhiên xóa Reactor Context; lỗi thường nảy sinh khi code tự `subscribe()`, tạo subscription không liên kết hoặc chuyển việc sang hệ thống không truyền Context. Không gọi `block()` trên event loop chỉ để lấy user. Truyền publisher hoặc identity đã xác minh qua API/service, và kiểm quyền lại khi gửi message/job bất đồng bộ.

## 9. So sánh WebFlux và Servlet

| Vấn đề | Spring WebFlux/reactive | Spring MVC/Servlet |
|---|---|---|
| Anonymous filter | `AnonymousAuthenticationWebFilter` | `AnonymousAuthenticationFilter` |
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Security context trong luồng | `ReactiveSecurityContextHolder` / Reactor Context | Thường qua `SecurityContextHolder`/ThreadLocal |
| Cấu hình minh họa | `.anonymous(Customizer.withDefaults())` | `.anonymous(Customizer.withDefaults())` trên builder Servlet tương ứng |
| Loại HTTP filter | `WebFilter` | Servlet `Filter` |

Đừng lấy ví dụ `HttpSecurity` hoặc `OncePerRequestFilter` rồi đưa thẳng vào WebFlux. Các kiểu, vòng đời request và cách truyền security context khác nhau. Đặc biệt **không suy luận trạng thái bật anonymous ở WebFlux từ hành vi mặc định của Servlet**.

## 10. Rủi ro và nhầm lẫn phổ biến

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| “Có `AnonymousAuthenticationToken` nghĩa là người dùng đã login” | Có thể cấp quyền sai nếu chỉ kiểm `isAuthenticated()` | Dùng `AuthenticationTrustResolver` hoặc authorization framework |
| “`permitAll()` luôn tạo anonymous principal” | Code controller tin vào principal giả không có thật | `permitAll` và `anonymous` là hai cấu hình độc lập |
| “Reactive anonymous tự bật mặc định như MVC” | Test mong chờ `anonymousUser` không có | Bật tường minh trên chain cần anonymous |
| “`ROLE_ANONYMOUS` tương đương xác thực danh tính” | Dữ liệu riêng lộ cho khách | Role này chỉ thể hiện danh nghĩa guest |
| “Đặt `hasAuthority("ROLE_ANONYMOUS")` là phép kiểm chỉ guest tuyệt đối” | User thật có cùng authority có thể khớp | Với chính sách chỉ guest, kiểm trust level |
| “Không mang Basic header thì mọi route là public” | Bị 401/403 trên route protected | Mặc định cần rule `permitAll` có chủ đích |
| “Gửi Basic sai lên public vẫn phải 200” | Nhầm lỗi xác thực với lỗi phân quyền | Authentication failure có thể chặn request trước authorization |
| “Tắt `anonymous()` sẽ xóa `permitAll()`” | Sửa policy sai mục tiêu | Hai cấu hình độc lập; kiểm thử từng điều kiện |
| “Guest phải có `UserDetails`” | Null/ClassCastException trong handler | Anonymous principal thường chỉ là String |
| “Anonymous context tồn tại trong job nền” | Logic audit/authorization sai bối cảnh | Không tự mang Reactor Context sang queue/background job |
| “Bật anonymous thay cho JWT/Basic” | Nhầm danh tính giả với danh tính xác minh | Anonymous chỉ lấp chỗ trống khi chưa có authentication thật |
| “Có thể trả nguyên Authentication ra JSON” | Có nguy cơ lộ credential/details nội bộ | Chỉ trả DTO thông tin tối thiểu, không log token |
| “Một custom chain bảo vệ mọi request khác” | URL ngoài `securityMatcher` có thể không qua chain | Có fallback chain và test route nằm ngoài matcher |

**Chú ý bảo mật:** sử dụng `ROLE_ANONYMOUS` để phân quyền đọc tài liệu công khai có thể hữu ích, nhưng `permitAll()` đơn giản hơn khi *mọi người* đều được xem. Không gán cho anonymous authorities tương đương quyền ghi dữ liệu, quản trị, xem hồ sơ hoặc truy cập các tenant. Không đưa key nội bộ của anonymous filter vào client.

## 11. Checklist để rà soát một ứng dụng WebFlux

1. Xác định ứng dụng đang dùng `ServerHttpSecurity`/`SecurityWebFilterChain` của WebFlux, không trộn với cấu hình MVC.
2. Kiểm tra trong chain cần thiết **đã gọi `anonymous(...)` hay chưa**. Không dựa vào dự đoán mặc định.
3. Xác định rõ các route `permitAll`, `authenticated` và các authority yêu cầu; đặt matcher cụ thể trước fallback.
4. Với `permitAll`, không giả định Reactor Context có user thật hoặc thậm chí anonymous token nếu filter chưa bật.
5. Nếu thực sự muốn “đã đăng nhập”, sử dụng authorization của framework/`AuthenticationTrustResolver`; không kiểm raw `isAuthenticated()` đơn lẻ.
6. Kiểm thử cả khách, credential sai và user được xác thực, bao gồm các HTTP status 200/401/403 phù hợp.
7. Kiểm tra filter không thay `Authentication` hợp lệ, không cấp nhầm role nhạy cảm cho guest.
8. Không trả nguyên `SecurityContext`/`Authentication` hay log credentials.
9. Với nhiều security chain, cấu hình anonymous và rule theo đúng phạm vi của từng chain, đồng thời có fallback.
10. Với ứng dụng gọi async message/queue, không giả định danh tính anonymous của request tiếp tục tồn tại trong một subscription/job độc lập.

## 12. Bài tập tự luyện

1. Chạy demo rồi gọi `/api/whoami` không Basic và có Basic hợp lệ. So sánh `tokenType`, `principalName`, `tokenAuthenticatedFlag`, `anonymous` và `authenticatedUser`.
2. Tại sao `AnonymousAuthenticationToken.isAuthenticated()` có thể là `true` nhưng `.authenticated()` vẫn không cho phép guest vào `/api/member`?
3. Tắt anonymous bằng `.anonymous(anonymous -> anonymous.disable())`, thử lại `/api/public` và `/api/whoami`. Phân biệt public access với anonymous context.
4. Đổi principal sang `guest` và authority sang `ROLE_GUEST`; sửa test `/api/guest-role` tương ứng.
5. Tạo một policy thật sự chỉ cho guest *chưa xác thực* truy cập bằng trust resolver thay vì chỉ dựa vào authority; viết test cho trường hợp user có thêm `ROLE_ANONYMOUS`.
6. Thử gửi header Basic sai đến một route `permitAll` để hiểu sự khác nhau giữa authentication failure và authorization.
7. Giải thích vì sao không nên coi `anonymousUser` là ID của một người dùng trong database hay làm khóa cache của dữ liệu riêng.

## Ghi nhớ

`AnonymousAuthenticationWebFilter` là một **WebFilter của Spring Security reactive** có thể cung cấp `AnonymousAuthenticationToken` trong `ReactiveSecurityContextHolder` khi chưa có authentication khác. Trên `ServerHttpSecurity`, hãy **bật anonymous tường minh** khi thực sự cần và kiểm tra chính sách request riêng qua `authorizeExchange`. Token anonymous mang principal/authority phục vụ cơ chế biểu diễn khách; nó **không phải bằng chứng đăng nhập**. Kiểm quyền thực bằng Spring Security authorization và nhận diện mức tin cậy qua `AuthenticationTrustResolver`.

## Tài liệu kỹ thuật

- Javadoc `AnonymousAuthenticationWebFilter` — package, constructors và hành vi: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AnonymousAuthenticationWebFilter.html
- Javadoc `ServerHttpSecurity.anonymous(Customizer)` — cách bật và chính sách mặc định: https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Javadoc `ServerHttpSecurity.AnonymousSpec` — principal, authorities, key, disable: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/config/web/server/ServerHttpSecurity.AnonymousSpec.html
- Javadoc `AuthenticationTrustResolver` — nhận diện anonymous và user đã xác thực: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security WebFlux configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
