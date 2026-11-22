# 4.3. Dependency OAuth2 Client cho ứng dụng WebFlux

## 1. Mục tiêu của bước thiết lập

Khi xây dựng ứng dụng **Spring Boot WebFlux** cho người dùng đăng nhập qua OAuth 2.0/OpenID Connect (OIDC), cần đưa đúng các thư viện vào classpath để Spring Security có thể:

1. Khởi tạo và quản lý một **OAuth 2.0 Client** (các thông tin client ID, client secret, authorization endpoint, token endpoint, scopes).
2. Chuyển hướng trình duyệt đến Authorization Server/OpenID Provider để đăng nhập.
3. Nhận callback chứa **authorization code**, đổi code lấy token và tạo phiên đăng nhập ở ứng dụng reactive.
4. Xác minh **ID Token** khi yêu cầu có scope `openid`.
5. Nếu cần, gắn access token vào các yêu cầu HTTP gửi ra ngoài bằng `WebClient`.

Việc chọn đúng dependency rất quan trọng vì **WebFlux sử dụng mô hình lập trình reactive**, với các thành phần như `ServerHttpSecurity`, `SecurityWebFilterChain`, `Mono`, `Flux` và `WebClient`. Ví dụ cấu hình bảo mật kiểu Servlet dùng `HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest` hoặc `OAuth2AuthorizedClientManager` bản Servlet không thể bê nguyên sang ứng dụng WebFlux.

Bài này tập trung vào **dependency và phần cấu hình tối thiểu để khởi động một OAuth2/OIDC Client trên WebFlux**. Các máy chủ bên ngoài — Authorization Server và API/Resource Server — là những hệ thống khác, không cần được triển khai trong cùng ứng dụng.

## 2. Ba nhóm dependency cốt lõi

Với ứng dụng Spring Boot WebFlux đóng vai trò OAuth2/OIDC Client, ta thường cần:

| Nhóm | Dependency Spring Boot | Mục đích |
|---|---|---|
| Reactive web stack | `spring-boot-starter-webflux` | Cung cấp Spring WebFlux, Reactor và web runtime reactive (thường là Reactor Netty). |
| Spring Security | `spring-boot-starter-security` | Cung cấp hạ tầng xác thực, bảo vệ HTTP và tích hợp Spring Security. |
| OAuth 2.0 / OIDC Client | Starter OAuth2 Client tương ứng phiên bản Boot | Cung cấp các thành phần OAuth2 Client và OIDC login, registration, xử lý token. |

**Tên starter OAuth2 Client thay đổi theo dòng Spring Boot:**

- **Spring Boot 3.x:** `org.springframework.boot:spring-boot-starter-oauth2-client`.
- **Spring Boot 4.x:** `org.springframework.boot:spring-boot-starter-security-oauth2-client` là tên được khuyến nghị. Tên cũ `spring-boot-starter-oauth2-client` vẫn được giữ ở Boot 4.0 nhưng đã được đánh dấu **deprecated**.

Điểm thay đổi này liên quan đến tên artifact starter của **Spring Boot**, không có nghĩa chuẩn OAuth 2.0 hoặc cách đăng nhập OIDC thay đổi. Hãy dùng **một** starter OAuth2 Client đúng với dòng Boot dự án sử dụng; không cần khai báo đồng thời starter cũ và mới.

**Có cần khai báo tường minh `spring-boot-starter-security` không?** Starter OAuth2 Client thường mang các thành phần Security liên quan theo phụ thuộc bắc cầu; trong một dự án dạy học hoặc một ứng dụng thực tế, khai báo Security starter tường minh làm rõ rằng ứng dụng chủ động sử dụng lớp bảo vệ HTTP. Khi tối ưu dependency thực tế, kiểm tra dependency graph để tránh diễn giải sai về các dependency bắc cầu.

## 3. Cấu hình Gradle cho Spring Boot 3.x

### 3.1. Gradle Groovy DSL — `build.gradle`

Khi dự án đã được tạo với Spring Boot Gradle plugin và dependency management tương ứng, phần dependencies cơ bản có thể là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Từng dòng có ý nghĩa như sau:

- `spring-boot-starter-webflux` thiết lập HTTP server/reactive controller và các loại phản hồi `Mono`/`Flux`.
- `spring-boot-starter-security` giúp ứng dụng đăng ký chuỗi bảo vệ HTTP reactive, xử lý authentication và authorization.
- `spring-boot-starter-oauth2-client` bổ sung hỗ trợ OAuth2 login, token exchange, client registration, OIDC.
- `spring-boot-starter-test` phục vụ kiểm thử ứng dụng Spring Boot (không phải điều kiện để OAuth2 login hoạt động ở runtime).
- `reactor-test` dùng các tiện ích kiểm thử reactive như `StepVerifier`.
- `spring-security-test` phục vụ kiểm thử bảo mật, principal và security context.

**Không thêm phiên bản riêng** cho từng Spring starter khi dự án dùng cơ chế quản lý phiên bản dependency của Spring Boot plugin/BOM. Việc khai báo các phiên bản Spring Security không tương thích với Spring Boot có thể gây lỗi classpath và bean creation.

Nếu dự án chỉ cần chạy ứng dụng và chưa viết test, ba dependency `implementation` đầu tiên mới là phần cốt lõi của bài này. Test dependencies là phần bổ trợ phù hợp cho phát triển.

### 3.2. Gradle Kotlin DSL — `build.gradle.kts`

Nếu dự án dùng Kotlin DSL thay cho Groovy DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Đây là cùng bộ dependency, chỉ khác cú pháp Gradle. Chọn DSL trùng với file build đang dùng; không tạo cả `build.gradle` lẫn `build.gradle.kts` để khai báo trùng một dự án.

## 4. Cấu hình Gradle cho Spring Boot 4.x

Spring Boot 4 sắp xếp lại tên một số starter theo tính năng. Đối với OAuth2 Client, dùng artifact **`spring-boot-starter-security-oauth2-client`** thay cho tên đã deprecated.

### 4.1. Gradle Groovy DSL — Boot 4.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-webflux-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Các starter test theo tính năng là một phần cách tổ chức dependency mới ở Spring Boot 4; tùy phạm vi kiểm thử có thể cần thêm `spring-security-test`. Chúng **không bắt buộc** để chạy ứng dụng web OAuth2 Client.

### 4.2. Gradle Kotlin DSL — Boot 4.x

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-oauth2-client-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Không cần vừa thêm `spring-boot-starter-security-oauth2-client` vừa thêm `spring-boot-starter-oauth2-client`. Nếu nâng cấp từ Boot 3 lên Boot 4, thay tên dependency là bước đơn giản và rõ ràng; cần tuân theo hướng dẫn nâng cấp Spring Boot cho các thay đổi khác trong dự án.

> **Phạm vi phiên bản:** Các ví dụ Boot 3.x và Boot 4.x đại diện cho hai dòng dependency. Không trộn version plugin/BOM của Boot 3 với starter Boot 4, hoặc ngược lại. Chọn một dòng Spring Boot mà ứng dụng đang sử dụng và để BOM/plugin của dòng đó quản lý phiên bản thư viện.

## 5. Cấu hình Maven tương ứng

Khi ứng dụng được tạo bằng Maven, các dependency tương tự nằm trong `pom.xml`.

### 5.1. Maven — Spring Boot 3.x

~~~xml
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
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ giả định dự án dùng `spring-boot-starter-parent` hoặc import BOM của Spring Boot tương ứng, vì vậy không ghi thủ công `<version>` ở từng dependency.

### 5.2. Maven — Spring Boot 4.x

Khi dự án sử dụng Boot 4.x, hai dependency ứng dụng `webflux` và `security` giữ nguyên; đổi starter OAuth2 Client như sau:

~~~xml
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
        <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-oauth2-client-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Maven không yêu cầu thêm một “OAuth2 OIDC Client starter” riêng nữa: thư viện OAuth2 Client của Spring Security hỗ trợ cả OAuth 2.0 và OpenID Connect login. Việc yêu cầu OIDC hay OAuth2 thuần được quyết định bởi **client registration, scope và cấu hình provider**, không phải bởi một dependency OIDC thứ hai.

## 6. Dependency nào nằm dưới các starter?

Starter là tập hợp dependency đã được thiết kế để làm việc cùng nhau. Trong một ứng dụng WebFlux + OAuth2 Client, các module quan trọng có thể xuất hiện trong dependency tree gồm:

| Module | Vai trò |
|---|---|
| `spring-webflux` | HTTP server/reactive web framework, handler, router, `WebClient`. |
| `reactor-core` | Kiểu reactive `Mono` và `Flux`, các toán tử lập trình bất đồng bộ. |
| `reactor-netty` | Runtime mạng non-blocking thường được WebFlux starter mang vào mặc định. |
| `spring-security-config` | API cấu hình Spring Security, bao gồm phần reactive security. |
| `spring-security-web` | Web security infrastructure; các lớp reactive và tích hợp web. |
| `spring-security-oauth2-core` | Các model/kiểu dữ liệu cơ bản của OAuth 2.0. |
| `spring-security-oauth2-client` | Client registration, OAuth2 Login và các client/token workflows. |
| `spring-security-oauth2-jose` | Hỗ trợ JWT/JWS/JWK sử dụng trong các tình huống OAuth2/OIDC, gồm xử lý ID Token. |

Không cần khai báo lại từng module trực tiếp nếu starter đã quản lý chúng. Nếu bỏ starter để tự lắp ghép module, nhà phát triển phải quản lý tương thích phiên bản và các thành phần còn thiếu; đó là lựa chọn nâng cao, thường không cần ở bước thiết lập dự án.

### 6.1. Nếu không dùng Spring Boot

Một ứng dụng Spring WebFlux thuần (không dùng Boot) có thể khai báo trực tiếp các module, chẳng hạn `spring-webflux`, `spring-security-config`, `spring-security-web`, `spring-security-oauth2-client` và các module/token dependencies cần thiết. Tuy nhiên, **không có Spring Boot auto-configuration và property binding mặc định**, nên phải chủ động định nghĩa những bean như `ReactiveClientRegistrationRepository`, security filter chain và cơ chế lưu authorized client.

Tại bước khởi tạo một dự án học Spring Security, dùng Spring Boot starter thường dễ hiểu và ít cấu hình hơn.

## 7. Dependency không tự biến ứng dụng thành OAuth2 Client hoàn chỉnh

Thêm starter OAuth2 Client chỉ đưa **khả năng xử lý** vào classpath. Để thực sự đăng nhập, ứng dụng cần ít nhất:

- Một **client registration** xác định provider, client ID, secret hoặc phương thức xác thực client, scope và redirect URI.
- Một **Authorization Server/OpenID Provider** thật để cấp code và token.
- Cấu hình **reactive security chain** phù hợp với WebFlux, nếu ứng dụng tùy chỉnh đường dẫn/phân quyền.

Với Spring Boot, registration thường được khai báo trong `application.yml` hoặc `application.properties`. Boot có thể tạo `ReactiveClientRegistrationRepository` từ các thuộc tính đó, giúp Spring Security kết nối client và provider.

## 8. Ví dụ `application.yml` cho ứng dụng WebFlux OIDC Client

Giả sử ứng dụng chạy tại `https://app.example.com`, đăng nhập qua provider có issuer `https://id.example.com`. Client registration ID là `demo`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-provider:
            issuer-uri: https://id.example.com
~~~

Các giá trị `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` cần được cung cấp qua biến môi trường hoặc cơ chế quản lý bí mật phù hợp. Không ghi secret thật vào repository.

### 8.1. Ý nghĩa từng nhóm cấu hình

| Thuộc tính | Vai trò |
|---|---|
| `registration.demo` | Đặt tên registration; dùng `demo` trong URL khởi tạo và callback mặc định. |
| `provider: demo-provider` | Nối client registration với thông tin OpenID Provider được khai báo. |
| `client-id` | Định danh client mà provider đã cấp. |
| `client-secret` | Bí mật của confidential client, được lưu ở server. |
| `client-authentication-method` | Cách client xác thực tại token endpoint trong ví dụ này. |
| `authorization-grant-type` | Chọn `authorization_code`, phù hợp đăng nhập người dùng qua trình duyệt. |
| `redirect-uri` | Callback mà provider sẽ chuyển trình duyệt về sau khi cấp code. |
| `scope` | `openid` kích hoạt OIDC, còn `profile`/`email` yêu cầu thêm thông tin theo hỗ trợ của provider. |
| `issuer-uri` | Định danh OP và điểm khởi đầu khám phá OIDC metadata. |

Khi issuer hỗ trợ OIDC Discovery, Spring Security có thể xác định authorization endpoint, token endpoint, JWK Set URI, UserInfo endpoint và các metadata liên quan từ `issuer-uri`. Nếu provider chỉ hỗ trợ OAuth2 không có discovery tương ứng, cần khai báo thủ công các endpoint phù hợp.

### 8.2. Redirect URI phải khớp với provider

Với registration `demo`, callback mặc định là:

~~~text
https://app.example.com/login/oauth2/code/demo
~~~

Đường dẫn này phải được cấu hình cho client tại provider. Khi chạy local ở `localhost:8080`, callback có thể là:

~~~text
http://localhost:8080/login/oauth2/code/demo
~~~

Provider có thể cho phép callback HTTP localhost phục vụ phát triển; khi triển khai thật, dùng HTTPS và host public. Nếu ứng dụng chạy sau reverse proxy, cần cấu hình forwarded headers đáng tin cậy để `{baseUrl}` được tính đúng scheme/host/port bên ngoài.

### 8.3. OAuth2 Client khác OIDC Client ở scope

Một registration chỉ yêu cầu scope của API như `read:orders` có thể là OAuth2 Client thuần. Khi yêu cầu có `openid`, Spring Security xử lý theo **OIDC Login**, trong đó ID Token được dùng để xác thực danh tính người dùng.

**Không cần cài thêm dependency mang tên “OIDC starter”** chỉ để nhận ID Token. OAuth2 Client starter đã cung cấp khả năng OIDC; provider phải thực sự hỗ trợ OIDC và trả ID Token đúng chuẩn.

## 9. Cấu hình Spring Security reactive tối thiểu

Trong WebFlux, bean trung tâm là **`SecurityWebFilterChain`**, cấu hình qua **`ServerHttpSecurity`**. Đây là mô hình reactive, không dùng `SecurityFilterChain` và `HttpSecurity` của ứng dụng Servlet.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Giải thích:

- `@EnableWebFluxSecurity` bật hỗ trợ web security cho WebFlux; ứng dụng có cấu hình security rõ ràng và kiểm soát chuỗi filter.
- `SecurityWebFilterChain` thay cho servlet `SecurityFilterChain`.
- `authorizeExchange(...)` xác định URL nào cần xác thực.
- `oauth2Login(...)` kích hoạt đăng nhập người dùng bằng OAuth2/OIDC qua trình duyệt.
- `oauth2Client(...)` bật hỗ trợ dùng OAuth2 authorized client khi ứng dụng cần lấy/gắn access token để gọi API bên ngoài.
- `build()` tạo chain để WebFlux sử dụng.

Nếu ứng dụng chỉ yêu cầu OIDC Login mà chưa có outbound API call, có thể chỉ cần cấu hình `oauth2Login(...)`. `oauth2Client(...)` bổ sung khả năng làm việc với authorized client; hai API có vai trò khác nhau và có thể được kết hợp.

**Vì sao không dùng ví dụ Servlet?**

| WebFlux/reactive | Servlet/MVC |
|---|---|
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `authorizeExchange` | `authorizeHttpRequests` |
| `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| `WebFilter` / reactive security chain | Servlet Filter / servlet security chain |
| `WebClient` với reactive authorized-client filter | `RestClient` hoặc client tích hợp thích hợp cho Servlet |

Nhầm kiểu ở bảng này dễ dẫn đến lỗi compile, bean không được đăng ký hoặc ứng dụng thực chất chạy ở servlet stack.

## 10. Khi các dependency đã có, luồng đăng nhập đi qua đâu?

Với Spring Security WebFlux cấu hình như trên, một luồng đăng nhập OIDC điển hình như sau:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Trình duyệt
    participant W as Spring Boot WebFlux
    participant OP as OIDC Provider
    participant API as Resource Server

    U->>W: GET /private
    W-->>U: Chuyển hướng khởi tạo login
    U->>W: GET /oauth2/authorization/demo
    W-->>U: 302 đến authorization endpoint
    U->>OP: Authorization request
    OP->>U: Đăng nhập / consent
    OP-->>U: 302 callback?code=...&state=...
    U->>W: GET /login/oauth2/code/demo?code=...&state=...
    W->>OP: POST token endpoint (đổi code)
    OP-->>W: Access token + ID Token
    Note over W: Kiểm tra token, tạo reactive Authentication
    W-->>U: Phiên đăng nhập ứng dụng
    W->>API: WebClient + Bearer access token
    API-->>W: Dữ liệu
    W-->>U: Nội dung trang / response
~~~

Các endpoint thường gặp:

| Đường dẫn/endpoint | Bên sở hữu | Chức năng |
|---|---|---|
| `/oauth2/authorization/demo` | Ứng dụng Spring WebFlux | Khởi tạo authorization request qua provider có registration ID `demo`. |
| Authorization endpoint, ví dụ `https://id.example.com/authorize` | OP/Authorization Server | Nhận yêu cầu cấp quyền/đăng nhập. |
| `/login/oauth2/code/demo` | Ứng dụng Spring WebFlux | Nhận authorization code và tiếp tục xác thực. |
| Token endpoint, ví dụ `https://id.example.com/token` | OP/Authorization Server | Đổi code lấy token, xác thực client và kiểm tra điều kiện giao thức. |
| `https://api.example.com/...` | Resource Server | Kiểm tra access token do WebClient gửi. |

**Dependency chỉ giúp Spring Security có khả năng thực thi luồng**, không thay thế bước đăng ký client với provider, đăng ký callback, cấp secret hoặc cấu hình scope.

## 11. Đọc người dùng đã đăng nhập bằng kiểu reactive

Khi OIDC Login hoàn tất, Spring Security gắn principal vào reactive security context. Ví dụ controller đơn giản đọc `OidcUser`:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "subject", user.getSubject(),
            "issuer", user.getIssuer().toString()
        );
    }
}
~~~

Ví dụ này chỉ phù hợp khi `/me` được bảo vệ và người dùng đăng nhập bằng OIDC. Nếu scope `openid` không có hoặc principal là một kiểu OAuth2 khác, không được ép kiểu tùy ý sang `OidcUser`.

Method của WebFlux controller có thể trả `Mono<T>`, `Flux<T>` hoặc giá trị đơn giản khi xử lý là tác vụ tức thời. Đọc vài claim có sẵn không cần ép vào `Mono` một cách hình thức. Khi truy cập database, gọi API hoặc thực hiện thao tác I/O, nên dùng driver/reactive API phù hợp và tránh chặn event-loop.

Nếu muốn giảm nguy cơ lộ dữ liệu, chỉ trả các claim cần thiết; không trả nguyên ID Token, access token hoặc refresh token cho trình duyệt chỉ để chứng minh đăng nhập thành công.

## 12. Vì sao cần `WebClient` và liên quan gì đến OAuth2 Client?

Spring WebFlux đi kèm **`WebClient`**, HTTP client dựa trên reactive stream. Khi ứng dụng cần gọi API đã bảo vệ bằng Bearer token, Spring Security cung cấp `ServerOAuth2AuthorizedClientExchangeFilterFunction` để gắn token của authorized client vào yêu cầu gửi đi.

Ví dụ cấu hình `WebClient`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient apiWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager
        );

        return WebClient.builder()
            .baseUrl("https://api.example.com")
            .filter(oauth2)
            .build();
    }
}
~~~

Một service dùng `WebClient` đã cấu hình:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
public class ProfileApiClient {

    private final WebClient apiWebClient;

    public ProfileApiClient(WebClient apiWebClient) {
        this.apiWebClient = apiWebClient;
    }

    public Mono<String> fetchProfile() {
        return apiWebClient.get()
            .uri("/v1/profile")
            .attributes(clientRegistrationId("demo"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

`clientRegistrationId("demo")` chọn cấu hình client mà Spring Security dùng để tìm authorized client/token trong ngữ cảnh hiện tại. Ví dụ giả định người dùng đã đăng nhập và authorized client tương ứng có thể được truy xuất. Với grant `authorization_code`, cần luồng ủy quyền tương tác ban đầu; không thể lấy token thay mặt người dùng từ một tác vụ nền không có principal/authorization context một cách tự động.

Đối với trường hợp gọi API bằng **client credentials** (không đại diện người dùng), cơ chế authorized client manager, principal và registration cần được cấu hình phù hợp với service-to-service; không dùng cấu hình OIDC login của người dùng như một giải pháp thay thế.

### 12.1. Nhớ sự phân chia trách nhiệm

- `spring-boot-starter-webflux` mang vào `WebClient`, nhưng không tự biết client ID hay token OAuth2.
- Starter OAuth2 Client cung cấp authorized-client infrastructure, nhưng không tự chọn API nào cần access token.
- `ServerOAuth2AuthorizedClientExchangeFilterFunction` là cầu nối giữa `WebClient` và quản lý OAuth2 authorized clients.
- Resource server/API tiếp tục phải xác minh access token và kiểm tra quyền; việc user đăng nhập thành công ở client không bỏ qua bước kiểm tra của API.

## 13. Không nhầm OAuth2 Client với Resource Server hoặc Authorization Server

Đây là lỗi lựa chọn dependency phổ biến khi mới làm Spring Security OAuth2.

| Ứng dụng muốn làm gì? | Nhóm tính năng cần | Starter Boot 3.x | Starter Boot 4.x |
|---|---|---|---|
| Đăng nhập người dùng qua OP; đổi code lấy token; gọi API thay mặt người dùng | **OAuth2/OIDC Client** | `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| Nhận Bearer access token từ caller và bảo vệ API của chính mình | **OAuth2 Resource Server** | `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| Tự phát hành authorization codes, access tokens và vận hành authorization endpoints | **Authorization Server** | Starter hoặc module Spring Authorization Server phù hợp phiên bản | `spring-boot-starter-security-oauth2-authorization-server` |

Một ứng dụng có thể đóng nhiều vai trò khi thực sự có yêu cầu, nhưng **bài này chỉ cần OAuth2 Client** để đăng nhập OIDC qua nhà cung cấp bên ngoài.

Ví dụ: ứng dụng WebFlux A cho người dùng đăng nhập với IdP B và sau đó gọi API C.

~~~text
[Trình duyệt]
      |
      v
[WebFlux A] ------- OAuth2 authorization code --------> [IdP B]
  OAuth2 Client <------- ID / access tokens ------------
      |
      | Bearer access token
      v
[API C: Resource Server]
~~~

WebFlux A không cần phụ thuộc `oauth2-resource-server` chỉ vì nó **gửi** access token đến API C. Nó chỉ cần resource-server capability nếu chính A phải **nhận và xác minh** Bearer token của các caller đến A.

Tương tự, WebFlux A không cần triển khai Authorization Server riêng chỉ vì nó chuyển trình duyệt đến IdP B.

## 14. Reactive WebFlux và Servlet MVC: chọn đúng web stack

### 14.1. Không thêm Servlet web starter nếu mục tiêu là WebFlux reactive

Với Spring Boot 3.x, starter MVC truyền thống là `spring-boot-starter-web`; Spring Boot 4.x khuyến nghị `spring-boot-starter-webmvc`. Nếu đưa đồng thời MVC và WebFlux starter vào dự án, Spring Boot có thể chọn **Servlet web application** theo cơ chế ưu tiên/autoconfiguration thông thường, khiến cấu hình WebFlux security không được áp dụng như mong đợi.

Vì vậy, khi thiết kế ứng dụng là WebFlux end-to-end, dependency nền tảng nên là:

~~~text
spring-boot-starter-webflux
spring-boot-starter-security
starter OAuth2 Client của phiên bản Spring Boot đang dùng
~~~

Chỉ thêm MVC starter khi dự án thật sự có mục tiêu chạy theo Servlet stack. Một ứng dụng MVC **có thể** dùng `WebClient` để gọi HTTP non-blocking mà không nhất thiết trở thành ứng dụng WebFlux server. Việc có class `WebClient` trên classpath không chứng minh server đang chạy kiểu reactive.

### 14.2. So sánh nhanh

| Đặc điểm | Spring WebFlux | Spring MVC |
|---|---|---|
| Web server programming model | Reactive/non-blocking ở API và pipeline phù hợp | Servlet request/response |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Cấu hình bảo mật | `ServerHttpSecurity` | `HttpSecurity` |
| HTTP client thường dùng | `WebClient` | `RestClient`, `WebClient` hoặc client khác |
| Authorization request repository | Bản reactive/server-web-exchange | Bản Servlet/HTTP session |
| Authorized client manager | `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Principal trong controller | Có thể nhận từ reactive security context | Có thể nhận từ servlet security context |

**OAuth2 Client starter dùng cho cả hai mô hình web**; việc Spring Security chọn các lớp reactive hay Servlet phụ thuộc loại ứng dụng và configuration chain.

## 15. Các lỗi dependency và cấu hình thường gặp

### 15.1. Chỉ thêm WebFlux starter, thiếu OAuth2 Client starter

**Dấu hiệu:** không có API cấu hình OAuth2 login phù hợp, không có client registration bean, hoặc endpoint `/oauth2/authorization/demo` không hoạt động như kỳ vọng.

**Nguyên nhân:** `spring-boot-starter-webflux` không tự cung cấp OAuth2 Client infrastructure.

**Cách xử lý:** thêm starter OAuth2 Client đúng phiên bản Spring Boot. Kiểm tra ứng dụng có client registration và security config.

### 15.2. Chỉ thêm Resource Server starter

**Dấu hiệu:** ứng dụng được cấu hình để kiểm tra Bearer JWT từ request đến, nhưng không có luồng redirect đăng nhập OIDC client.

**Nguyên nhân:** Resource Server và OAuth2 Client là hai vai trò khác nhau.

**Cách xử lý:** ứng dụng muốn làm login client thì thêm OAuth2 Client starter và `oauth2Login()` tương ứng, không thay bằng `oauth2ResourceServer()`.

### 15.3. Đang dùng Spring Boot 4 mà vẫn sao chép starter Boot 3

**Dấu hiệu:** build vẫn có thể chạy nhờ tên cũ còn tồn tại, nhưng phụ thuộc `spring-boot-starter-oauth2-client` đã deprecated trong Boot 4.

**Cách xử lý:** với Boot 4, chuyển sang `spring-boot-starter-security-oauth2-client`; không khai báo cả hai.

### 15.4. Khai báo `HttpSecurity` trong dự án WebFlux

**Dấu hiệu:** cấu hình security không khớp, lỗi thiếu bean hoặc chức năng bảo vệ không hoạt động theo cách dự kiến.

**Nguyên nhân:** code đang dùng API Servlet thay vì reactive.

**Cách xử lý:** dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `authorizeExchange`.

### 15.5. Dùng `OAuth2AuthorizedClientManager` sai loại

**Dấu hiệu:** code cấu hình `WebClient` không tương thích constructor/filter function hoặc Spring không tìm thấy bean phù hợp.

**Nguyên nhân:** import bản Servlet `OAuth2AuthorizedClientManager` thay vì `ReactiveOAuth2AuthorizedClientManager`.

**Cách xử lý:** dùng manager reactive và `ServerOAuth2AuthorizedClientExchangeFilterFunction`.

### 15.6. Thiếu registration hoặc sai `issuer-uri`

**Dấu hiệu:** ứng dụng không tạo được `ReactiveClientRegistrationRepository` phù hợp, đăng nhập không khởi chạy, hoặc discovery metadata thất bại khi startup/request.

**Nguyên nhân:** chưa khai báo `spring.security.oauth2.client.registration.*`, issuer sai hoặc provider không hỗ trợ OIDC Discovery.

**Cách xử lý:** kiểm tra `client-id`, `scope`, `provider` và `issuer-uri`; nếu provider không hỗ trợ discovery, khai báo endpoint trực tiếp theo tài liệu provider.

### 15.7. Sai redirect URI

**Dấu hiệu:** OP báo `invalid_redirect_uri` hoặc redirect quay về host/protocol không đúng.

**Nguyên nhân:** callback trong provider và `{baseUrl}` không khớp, proxy gửi sai scheme/host, hoặc registration ID khác tên URL.

**Cách xử lý:** đăng ký đúng `/login/oauth2/code/demo`, cấu hình proxy/header đáng tin cậy và dùng HTTPS ở production.

### 15.8. Có OAuth2 login nhưng không có ID Token

**Dấu hiệu:** chỉ nhận OAuth2 principal hoặc không có OIDC-specific user.

**Nguyên nhân:** thiếu scope `openid` hoặc provider không hỗ trợ OIDC.

**Cách xử lý:** chọn provider OIDC hợp lệ và yêu cầu `openid`, rồi sử dụng OIDC Login.

### 15.9. Thêm thư viện HTTP blocking vào event-loop

**Dấu hiệu:** ứng dụng chậm hoặc tăng độ trễ khi tải cao, dù dùng WebFlux.

**Nguyên nhân:** gọi `RestTemplate`, JDBC blocking hoặc `.block()` tùy tiện trong đường xử lý reactive.

**Cách xử lý:** dùng các API/reactive driver phù hợp. Nếu buộc phải gọi thư viện blocking, cần tách khỏi event-loop theo chiến lược scheduling thích hợp; dependency OAuth2 Client không tự làm mọi thao tác I/O của ứng dụng trở thành non-blocking.

### 15.10. Quên cấu hình secret và scope theo môi trường

**Dấu hiệu:** startup hoặc token exchange báo `invalid_client`; OIDC Login không tạo được principal như mong đợi.

**Nguyên nhân:** placeholder biến môi trường không có giá trị, secret sai, client auth method sai hoặc scopes không được provider cấp.

**Cách xử lý:** cung cấp secret bằng cơ chế được phép, đối chiếu client registration với IdP, đảm bảo scope `openid` cho đăng nhập OIDC.

## 16. Quan sát classpath và phát hiện dependency trùng

Để hiểu những gì starter đã mang vào, dùng công cụ dependency của build system.

### Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Để tìm một dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

### Maven

~~~bash
mvn dependency:tree
~~~

Những lệnh này giúp biết có module `spring-security-oauth2-client` hay không, phiên bản nào được chọn, và liệu nhiều starter kéo các phần khác nhau vào classpath. Chúng đặc biệt hữu ích khi nâng cấp Boot hoặc khi một thư viện khác đưa thêm Servlet/MVC dependencies ngoài ý muốn.

Về mặt kiến trúc, cần xác định ba thứ riêng biệt: **có OAuth2 Client module**, **ứng dụng chạy trên WebFlux**, và **đã đăng ký provider/client để thực hiện login**. Đủ dependency chưa đồng nghĩa với đủ cấu hình đăng nhập.

## 17. Ví dụ cấu trúc dự án WebFlux OAuth2/OIDC Client

Một dự án tối thiểu có thể tổ chức:

~~~text
spring-webflux-oidc-client/
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/oidc/
        │   ├── OidcClientApplication.java
        │   ├── SecurityConfig.java
        │   ├── MeController.java
        │   └── WebClientConfig.java
        └── resources/
            └── application.yml
~~~

- `OidcClientApplication` chứa `@SpringBootApplication` và phương thức `main`.
- `SecurityConfig` chứa `SecurityWebFilterChain` kiểu WebFlux.
- `MeController` minh họa principal OIDC trong route đã đăng nhập.
- `WebClientConfig` chỉ cần khi ứng dụng gọi API ngoài bằng token.
- `application.yml` định nghĩa OAuth2 client registration, provider và các thuộc tính cần thiết.

Ví dụ main class:

~~~java
package com.example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcClientApplication.class, args);
    }
}
~~~

Có thể bắt đầu từ Spring Initializr bằng cách chọn các khả năng **Spring Reactive Web**, **Spring Security** và **OAuth2 Client**. Sau khi tạo dự án, đối chiếu tên artifact với phiên bản Boot đang dùng, đặc biệt sự thay đổi của starter OAuth2 Client trong Boot 4.

## 18. Khi dự án chạy, mong đợi thấy gì?

Với provider đã cấu hình hợp lệ, ứng dụng cho phép khởi tạo đăng nhập qua:

~~~http
GET /oauth2/authorization/demo HTTP/1.1
Host: localhost:8080
~~~

Spring Security chuyển hướng đến authorization endpoint của OP. Sau khi người dùng xác thực và chấp thuận, OP chuyển trình duyệt về:

~~~text
/login/oauth2/code/demo?code=...&state=...
~~~

Spring Security dùng thông tin authorization request đã lưu để xác minh callback và trao đổi code với token endpoint. Với OIDC, client còn xác thực ID Token rồi tạo principal và lưu ngữ cảnh đăng nhập phù hợp. Khi quay lại route đã bảo vệ, người dùng sử dụng phiên được ứng dụng quản lý.

Trong trình duyệt thường nhìn thấy **redirect** và callback; token endpoint request của backend không phải một lệnh `fetch()` do trình duyệt gọi trong mô hình confidential web client.

Nếu chưa có IdP hoặc chưa khai báo đúng client ID/secret/redirect URI, ứng dụng có thể build thành công mà đăng nhập vẫn thất bại. Đó là khác biệt giữa **dependency readiness** và **OAuth2/OIDC integration readiness**.

## 19. Ghi nhớ khi lựa chọn dependency

| Nếu mục tiêu là… | Cần chuẩn bị |
|---|---|
| Dựng reactive HTTP server | `spring-boot-starter-webflux`. |
| Bảo vệ route ứng dụng theo reactive model | `spring-boot-starter-security` và `SecurityWebFilterChain`. |
| Cho user đăng nhập bằng OAuth 2.0/OIDC qua provider ngoài | OAuth2 Client starter đúng dòng Spring Boot, registration và `oauth2Login()`. |
| Gọi API bằng access token | `WebClient` và các thành phần quản lý authorized client phù hợp, chẳng hạn `ReactiveOAuth2AuthorizedClientManager`. |
| Bảo vệ chính API bằng Bearer token inbound | Thêm Resource Server capability theo yêu cầu riêng. |
| Tự vận hành IdP/Authorization Server | Thêm Authorization Server capability cho một dịch vụ chuyên biệt, không phải yêu cầu mặc định của client. |

Với một **Spring Boot WebFlux OAuth2/OIDC Client**, ba nhóm dependency quan trọng nhất là **WebFlux + Spring Security + OAuth2 Client**. Điểm cần ghi nhớ theo phiên bản là:

- **Boot 3.x:** `spring-boot-starter-oauth2-client`.
- **Boot 4.x:** `spring-boot-starter-security-oauth2-client`.

Sau đó, sử dụng **`ServerHttpSecurity` và `SecurityWebFilterChain`** cho ứng dụng reactive, khai báo **`spring.security.oauth2.client.registration`** với provider thật, và dùng scope **`openid`** nếu mục tiêu là OIDC Login. Khi gọi API downstream, tích hợp **`WebClient`** với OAuth2 authorized-client infrastructure.

## Tài liệu tham khảo chính thức

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/) — phạm vi OAuth2 Login và OAuth2 Client trong WebFlux.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — danh sách starter theo các dòng Spring Boot hiện đại.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) — thay đổi tên các starter trong Spring Boot 4.
- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html) — cấu hình bảo mật reactive và các thành phần liên quan.
