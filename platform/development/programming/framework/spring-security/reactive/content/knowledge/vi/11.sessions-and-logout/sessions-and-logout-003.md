# Phân biệt ứng dụng có trạng thái và ứng dụng không lưu trạng thái xác thực trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm kiến thức:** Phiên và đăng xuất  
> **Mục tiêu:** Phân biệt cơ chế giữ đăng nhập bằng session với cơ chế xác thực độc lập ở từng request; hiểu tác động của WebSession, cookie, SecurityContext, Bearer token và logout; thực hành hai cấu hình WebFlux tách biệt và kiểm chứng hành vi bằng WebTestClient.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích “**stateful authentication**” là server hoặc session store giữ thông tin xác thực qua nhiều HTTP requests; “**stateless authentication**” là mỗi request mang đủ credential để server xác thực lại mà không cần đọc một session đăng nhập trước đó.
2. Phân biệt `WebSession`, cookie `SESSION`, `SecurityContext`, `Reactor Context`, HTTP Basic, Bearer access token và refresh token.
3. Cấu hình WebFlux dùng `WebSessionServerSecurityContextRepository` cho form login và `NoOpServerSecurityContextRepository` cho API xác thực mỗi request.
4. Dự đoán điều gì xảy ra với request kế tiếp khi bỏ cookie, bỏ header Authorization, token hết hạn hoặc logout.
5. Giải thích vì sao **logout có thể vô hiệu hóa server session ngay** nhưng không tự thu hồi mọi JWT đã phát hành.
6. Phân tích trade-off giữa server-side session và token-based API về CSRF, XSS, lưu trữ credential, mở rộng nhiều instance, thu hồi quyền và bảo vệ data-level.
7. Kiểm tra hành vi thực tế bằng các phép thử âm tính, thay vì chỉ thấy một response 200 rồi kết luận “đã đăng nhập”.

**Điểm cốt lõi:** “Không lưu trạng thái xác thực” nghĩa là **không dựa vào session xác thực đã lưu từ request trước**. Nó không hứa ứng dụng không có bất kỳ state nào: database, cache, rate limiter, audit, CSRF token repository, refresh-token store hoặc request cache vẫn có thể có trạng thái.

## 2. HTTP vốn độc lập; cơ chế xác thực mới quyết định tính stateful

HTTP request không tự mang object Java của request trước. Khi người dùng mở `GET /api/me` sau khi đã login, server cần biết tại sao request mới thuộc cùng người dùng.

**Stateful session:** sau khi xác thực, server lưu `SecurityContext` hoặc dữ liệu liên quan vào session store. Browser nhận cookie chứa **session ID**; request tiếp theo gửi cookie, server dùng ID để tra lại session rồi khôi phục Authentication.

**Stateless per-request:** mỗi request mang credential được kiểm chứng cho chính request đó, ví dụ `Authorization: Bearer <access-token>`. Resource Server xác thực token, tạo Authentication trong scope của request, rồi bỏ kết quả local sau khi xử lý. Không cần lưu “user X đã đăng nhập từ request trước” trong một session xác thực.

~~~mermaid
flowchart TD
    U["Client gửi request #1"] --> S{"Chọn kiểu xác thực"}
    S -->|"Stateful: POST /login"| A["Kiểm tra credentials"]
    A --> B["Lưu SecurityContext trong WebSession"]
    B --> C["Set-Cookie: SESSION=<session-id>"]
    C --> D["Request #2 có Cookie: SESSION"]
    D --> E["Server tra WebSession và khôi phục Authentication"]
    S -->|"Stateless: Bearer"| F["Request #1 có Authorization: Bearer token"]
    F --> G["Kiểm chứng token → Authentication cục bộ"]
    G --> H["Request #2 phải có Bearer token phù hợp riêng"]
    H --> I["Kiểm chứng lại token cho request #2"]
~~~

### So sánh nhanh

| Khía cạnh | Có trạng thái xác thực (session) | Không lưu trạng thái xác thực (per-request) |
| --- | --- | --- |
| Thông tin client gửi thường thấy | Cookie chứa session ID | Authorization Bearer/JWT; HTTP Basic cũng kiểm chứng mỗi request |
| Server giữ “đăng nhập trước đó” | Có, trong `WebSession`/session store | Không cần server-side login session |
| Danh tính request mới | Nạp từ server session được tra bằng ID | Xác thực credential của request mới |
| Khi client bỏ credential | Không có cookie → không tìm được session | Không có token/header → không xác thực |
| Vô hiệu hóa/logout | Invalidate session ở server; cookie cũ không dùng được | Xóa token phía client **không tự thu hồi** token còn hiệu lực |
| Thu hồi tập trung | Xóa session hoặc đổi trạng thái trong store | JWT offline: cần expiry ngắn/denylist/introspection/token version hoặc chiến lược phù hợp |
| Quy mô nhiều instance | Cần session stickiness hoặc shared session store như Redis | Thường không cần shared authentication session; vẫn có hạ tầng/secret/keys/validation state |
| CSRF | Đặc biệt quan trọng khi browser tự gửi session cookie | Phụ thuộc credential được tự gửi hay chủ động đính kèm, **không chỉ phụ thuộc “JWT”** |
| XSS/token theft | Session cookie vẫn có rủi ro hijack; HttpOnly giảm JS đọc cookie | Token trong JS-accessible storage rất nhạy cảm với XSS; token ở cookie lại có CSRF risk |
| Server-side authorization | Luôn phải kiểm tra route, role và quyền dữ liệu | Luôn phải kiểm tra route, scope, role và quyền dữ liệu |

**Không nhầm “stateless” với “dùng JWT”:** HTTP Basic không lưu login session nếu cấu hình không lưu SecurityContext, nhưng phải gửi username/password mỗi request và không phải phương án lý tưởng cho nhiều API production. Một JWT hoàn toàn có thể được đặt trong **cookie** và bị browser tự gửi; việc đó vẫn tạo CSRF risk. Ngược lại, server-side session không tự ngụ ý hệ thống không mở rộng được: shared session store có thể giúp scale.

## 3. Những thứ thường bị nhầm với nhau trong WebFlux

### 3.1. WebSession

`WebSession` là abstraction session của **Spring WebFlux**. Server có thể lưu session data trong bộ nhớ hoặc store bên ngoài. Session ID thường gửi cho browser qua cookie tên `SESSION`, nhưng tên/cơ chế cookie có thể cấu hình hoặc thay bằng session resolver khác. Cookie chứa **ID để tham chiếu**; trong ví dụ session mặc định, nó **không phải JWT** và không chứa nguyên object `SecurityContext`.

`WebSession` là khái niệm rộng hơn authentication: app có thể lưu dữ liệu phiên khác, CSRF token và saved request. Vì vậy tắt persistence của SecurityContext **không đủ** để chứng minh không còn WebSession nào trong toàn ứng dụng.

### 3.2. SecurityContext và Reactor Context

`SecurityContext` chứa `Authentication` (principal, authorities, thông tin xác thực liên quan). `ReactiveSecurityContextHolder` giúp code trong `Mono`/`Flux` đọc SecurityContext từ **Reactor Context của subscription đang chạy**.

- **Với session:** Spring Security có thể tải SecurityContext đã lưu từ WebSession vào Reactor Context của **request mới**.
- **Với stateless:** Spring Security có thể tạo SecurityContext từ token của **request hiện tại**, đưa vào Reactor Context rồi không ghi nó vào WebSession cho request tiếp theo.
- Vì vậy **có SecurityContext trong một request không đồng nghĩa ứng dụng stateful**.

Không dùng `SecurityContextHolder` của kiểu Servlet ThreadLocal và giả định một request WebFlux luôn chạy trên một thread.

### 3.3. ServerSecurityContextRepository

`ServerSecurityContextRepository` định nghĩa cách `load(ServerWebExchange)` và `save(ServerWebExchange, SecurityContext)` trạng thái xác thực giữa requests.

- `WebSessionServerSecurityContextRepository`: lưu/đọc SecurityContext trong `WebSession`. Theo API chính thức, khi lưu SecurityContext, session ID được thay đổi để giảm session fixation risk.
- `NoOpServerSecurityContextRepository`: implementation không lưu/tải SecurityContext; thích hợp khi xác thực lại từ credential ở từng request.
- `ReactorContextWebFilter` có thể dùng repository để nạp SecurityContext cho request hiện tại.
- Khi cấu hình cơ chế login/custom authentication, cần xét **repository của AuthenticationWebFilter tương ứng**, không chỉ repository ở cấp `ServerHttpSecurity`. Một cơ chế login vẫn có thể lưu session nếu filter riêng được cấu hình để làm vậy.

**Đừng mang code Servlet sang WebFlux:** `HttpSessionSecurityContextRepository`, `HttpSecurity` và `SessionCreationPolicy.STATELESS` là các ví dụ quen thuộc thuộc nhánh Servlet; trong bài này dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerSecurityContextRepository`.

## 4. Luồng Stateful: login một lần, request sau dùng cookie

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as App WebFlux
    participant S as WebSession store
    B->>A: GET /login
    A-->>B: Login page + CSRF token
    B->>A: POST /login + credentials + CSRF
    A->>A: Kiểm chứng username/password
    A->>S: Lưu SecurityContext vào WebSession
    A-->>B: Set-Cookie SESSION + redirect
    B->>A: GET /api/me + Cookie SESSION
    A->>S: Tải SecurityContext theo session ID
    S-->>A: Authentication đã lưu
    A-->>B: 200 JSON user
    B->>A: POST /logout + Cookie + CSRF
    A->>S: Xóa context/invalidate session
    A-->>B: Redirect / login
    B->>A: GET /api/me + cookie cũ
    A-->>B: Yêu cầu login lại
~~~

**Điều browser lưu thường chỉ là session ID.** Dữ liệu server-side có thể nằm trong bộ nhớ của một instance hoặc shared store. Với Spring Session + Redis, nhiều instance có thể truy cập cùng session. Nếu chỉ lưu in-memory mỗi instance, load balancer cần chiến lược sticky session hoặc user dễ bị mất trạng thái khi request đến instance khác.

### 4.1. Session lifecycle

1. **Anonymous:** có thể chưa có session hoặc session chỉ chứa dữ liệu như CSRF/saved request; chưa có Authentication của user.
2. **Login thành công:** Spring Security tạo Authentication và lưu vào repository dùng WebSession; session ID được đổi khi lưu để giảm session fixation.
3. **Request kế:** client gửi session cookie; server tìm session và khôi phục danh tính. Nếu session hết hạn/bị xóa/ID giả, phải yêu cầu login lại.
4. **Idle/absolute expiration:** phải xác định timeout và chính sách gia hạn theo ứng dụng. WebSession có khả năng timeout theo thời gian không hoạt động; absolute lifetime/giới hạn đăng nhập đồng thời có thể cần cơ chế bổ sung.
5. **Logout:** xóa SecurityContext và thường invalidate WebSession; xóa cookie phía browser hỗ trợ UX nhưng **server invalidation** mới là điều khiến ID cũ không còn dùng được.
6. **Quyền thay đổi:** nếu session lưu authorities cũ, việc đổi role/disable account có thể không có hiệu lực ngay nếu không refresh/revoke session hoặc kiểm tra quyền tại tầng dữ liệu.

### 4.2. Cookie security và CSRF

Đối với browser session, cần xem `Secure` (chỉ gửi qua HTTPS), `HttpOnly` (giảm việc script đọc cookie), `SameSite`, domain/path và expiration. Không đặt session ID vào URL, log hoặc third-party analytics. Cookie đánh cắp có thể cho phép session hijack dù không biết password.

Vì browser tự gửi cookie theo domain/policy, request thay đổi trạng thái có thể bị **Cross-Site Request Forgery (CSRF)**. Spring Security WebFlux bật CSRF protection theo mặc định. Form login và logout cần CSRF token; logout mặc định được kích hoạt qua **POST**, không phải GET link tùy ý. `HttpOnly` không thay thế CSRF token và `SameSite` không phải một hàng rào đủ cho mọi threat model.

## 5. Luồng Stateless: xác thực lại dựa trên credential từng request

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API client
    participant A as Resource Server A
    C->>A: GET /api/me + Bearer token
    A->>A: Kiểm tra signature/issuer/exp/aud/scope
    A->>A: Tạo Authentication cho request hiện tại
    A-->>C: 200 JSON user
    C->>A: GET /api/me không có token
    A-->>C: 401
    C->>A: GET /api/me + token hợp lệ
    A->>A: Xác thực cho request mới
    A-->>C: 200
~~~

Với Bearer JWT, resource server thường kiểm tra chữ ký dựa trên khóa công khai/JWKS, `iss`, `exp`, `nbf` và **audience theo policy**. Scope có thể ánh xạ thành `SCOPE_...` để cấp quyền. JWT ở request thứ hai không phải “phiên” server đã nhớ từ request đầu tiên: server cần xác thực credential mới mỗi lần.

Với opaque access token, server có thể gọi **introspection** tới hệ thống quản lý token; khi đó xác thực vẫn **không nhất thiết dùng một WebSession đăng nhập**, nhưng có dependency/state ở authorization server và cache introspection. Như vậy “không lưu trạng thái xác thực ở resource server” **không** đồng nghĩa “không có state ở toàn hệ thống”.

### 5.1. Stateless không có nghĩa không có local SecurityContext

Trong từng request, filter vẫn tạo `Authentication` và code service vẫn đọc qua `ReactiveSecurityContextHolder.getContext()`. Context này cần cho authorization trong request hiện tại. Điều bị loại bỏ là **tính phụ thuộc vào SecurityContext đã lưu giữa hai HTTP requests**.

### 5.2. Không tự phát JWT ở một Resource Server

Ứng dụng đóng vai **Resource Server** xác minh access token do Authorization Server/IdP cấp. Đừng tự tạo một endpoint demo ký JWT bằng secret hardcode rồi coi đó là phương pháp sản xuất. Cấp token, xoay khóa, revocation, refresh token, OIDC login và quản trị user là các trách nhiệm phải được thiết kế riêng.

Trong mục thực hành, để hai biến thể **chạy được độc lập không cần IdP**, ta minh họa stateless bằng HTTP Basic trên WebFlux với repository NoOp. Sau đó mục 10 chỉ ra cấu hình JWT Resource Server thực tế. Basic gửi password mỗi request nên **chỉ dùng cho lab localhost** và không phải khuyến nghị thay JWT/OAuth2.

## 6. Dự án Maven chạy hai chế độ tách biệt

Ta tạo **một project** với hai Spring profiles:

- `session`: form login và WebSession, endpoint `/api/me` dùng cookie session đã được xác thực.
- `basic`: HTTP Basic kiểm tra username/password mỗi lần, `NoOpServerSecurityContextRepository` không giữ SecurityContext giữa requests.
- Ở cả hai: `GET /api/public` công khai và `GET /api/me` chỉ dành cho authenticated user.
- Mỗi lần khởi động chọn **đúng một** profile; đây là hai cách cấu hình thay thế nhau, không bật đồng thời.

Ví dụ dùng **JDK 17+**, Maven, Spring Boot `3.3.13` tương ứng Spring Security 6.x; nhánh Spring Boot 3.3 đã hết hỗ trợ OSS, do vậy production mới phải chọn phiên bản hiện được hỗ trợ và kiểm tra API theo phiên bản. Mã account/password ở lab không dùng trong môi trường thật.

Cấu trúc:

~~~text
webflux-auth-state/
├── pom.xml
└── src/
    ├── main/java/example/state/
    │   ├── StateApplication.java
    │   ├── UserConfig.java
    │   ├── SessionSecurityConfig.java
    │   ├── BasicStatelessSecurityConfig.java
    │   └── ApiController.java
    └── test/java/example/state/
        ├── SessionModeTest.java
        └── BasicStatelessModeTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-auth-state</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao không có Resource Server dependency?** Hai profile đầu cố ý không cần issuer/token thật để thử ngay. Cấu hình JWT ở mục 10 là biến thể bổ sung có dependency riêng. Không thêm `spring-boot-starter-web` vì lab dùng reactive WebFlux, không dùng Servlet MVC.

### 6.2. Class khởi động

File `src/main/java/example/state/StateApplication.java`:

~~~java
package example.state;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@SpringBootApplication
@EnableWebFluxSecurity
public class StateApplication {
    public static void main(String[] args) {
        SpringApplication.run(StateApplication.class, args);
    }
}
~~~

### 6.3. Một user store chung cho hai profile

File `src/main/java/example/state/UserConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class UserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
            .password(encoder.encode("demo-pass"))
            .roles("STUDENT")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
~~~

`MapReactiveUserDetailsService` cung cấp một user demo. Password được encode bằng `PasswordEncoder` trước khi đưa vào in-memory user store; tuy nhiên chuỗi plaintext `demo-pass` xuất hiện trong **mã nguồn lab**, nên không dùng cách này cho production. User store thật cần database/IdP an toàn, quản lý mật khẩu và rotation thích hợp.

## 7. Cấu hình stateful: form login + WebSession

File `src/main/java/example/state/SessionSecurityConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@Profile("session")
public class SessionSecurityConfig {

    @Bean
    SecurityWebFilterChain sessionChain(ServerHttpSecurity http) {
        var repository = new WebSessionServerSecurityContextRepository();

        var logoutHandler = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler()
        );

        return http
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public", "/login", "/logout")
                    .permitAll()
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form.securityContextRepository(repository))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .logout(logout -> logout.logoutHandler(logoutHandler))
            .build();
    }
}
~~~

**Các quyết định quan trọng:**

1. `@Profile("session")` bảo đảm bean chain này chỉ hoạt động khi khởi động profile session.
2. `WebSessionServerSecurityContextRepository` dùng để đọc/lưu trạng thái xác thực qua các HTTP requests. Cả phần tải context của HTTP security và form login đều dùng repo phù hợp.
3. `formLogin(...)` cung cấp cơ chế nhập credentials và lưu context sau login; Spring Security có trang login mặc định trong môi trường mẫu.
4. `httpBasic(...disable)` tránh HTTP Basic trở thành cơ chế thay thế, giúp test chỉ quan sát session. Không có nghĩa HTTP Basic vốn “stateless” luôn kém bảo mật; hai cơ chế có mục đích khác nhau.
5. Logout dùng `DelegatingServerLogoutHandler`: xóa context theo `SecurityContextServerLogoutHandler` và invalidate `WebSession` theo `WebSessionServerLogoutHandler`. Lưu ý Spring Security có logout mặc định, nhưng **muốn invalidation toàn bộ WebSession rõ ràng** thì nên cấu hình handler tương ứng.
6. CSRF **không bị tắt**. POST login và POST logout cần CSRF token theo chính sách Spring Security Reactive. Không biến logout thành GET để né CSRF.
7. `anyExchange().denyAll()` ở cuối tránh tự mở các URL khác. Các endpoint login/logout đi qua filter đặc thù của Spring Security.

**Cẩn trọng khi mở rộng:** phiên đăng nhập còn có timeout, cookie flags, session fixation, concurrency, quyền thay đổi và session-store resilience. Ở WebFlux, repository lưu SecurityContext vào WebSession; phần lưu thực tế của session có thể dùng default session manager hoặc được thay bởi Spring Session/shared store. `SESSION` là tên cookie mặc định thường thấy, không phải bảo đảm vĩnh viễn ở mọi cấu hình.

## 8. Cấu hình stateless đơn giản: HTTP Basic mỗi request

File `src/main/java/example/state/BasicStatelessSecurityConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@Profile("basic")
public class BasicStatelessSecurityConfig {

    @Bean
    SecurityWebFilterChain basicChain(ServerHttpSecurity http) {
        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.securityContextRepository(noOp))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .build();
    }
}
~~~

**Giải thích:**

- `@Profile("basic")` chọn phương án thay thế, không chạy đồng thời với chain session.
- `NoOpServerSecurityContextRepository.getInstance()` làm repository lưu/đọc SecurityContext giữa requests thành no-op. Cấu hình **cả repository ở cấp ServerHttpSecurity và trên filter HTTP Basic** để ý định không persist credentials rõ ràng.
- `httpBasic(...)` kiểm tra `Authorization: Basic ...` tại **mỗi request**. Nếu request kế tiếp bỏ header, user sẽ không còn được xác thực. Đây là ví dụ stateless về mặt **authentication persistence**.
- Tắt `formLogin`, `requestCache` và endpoint logout mặc định vì không dùng browser login session. Không có session đăng nhập để invalidate; gọi lại API bằng Basic credentials hợp lệ vẫn đăng nhập được cho request mới.
- **Cố ý giữ CSRF mặc định** trong lab, vì HTTP Basic **cũng có thể được trình duyệt cache rồi tự gửi**. Chỉ thử các GET nên không cần CSRF token. Đừng suy luận `NoOpServerSecurityContextRepository` nghĩa là có thể tắt CSRF cho mọi loại credentials.
- NoOp chỉ giải quyết SecurityContext persistence; một phần khác của app vẫn có thể tạo WebSession cho CSRF, flash data hoặc chức năng riêng. Muốn xác nhận kiến trúc “no session cookie” phải kiểm thử toàn bộ flow, không chỉ đọc một thuộc tính cấu hình.
- Basic không phù hợp cho nhiều hệ thống web hiện đại vì password gửi lại trên mỗi request (Base64 không phải mã hóa bí mật), logout phía browser không đáng tin và khả năng thu hồi liên quan đến mật khẩu. **Dùng HTTPS ngoài localhost** và ưu tiên OAuth2/Bearer cho API thực.

Nếu ứng dụng cần user đã đăng nhập với credential trong một request, `ReactiveSecurityContextHolder.getContext()` vẫn có thể chứa Authentication **cho request hiện tại**; NoOp không ngăn tạo local SecurityContext sau khi xác thực thành công.

## 9. Controller dùng chung cả hai chế độ

File `src/main/java/example/state/ApiController.java`:

~~~java
package example.state;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }
}
~~~

Cùng endpoint `GET /api/me` có thể cho ra JSON `{"username":"student"}` trong **cả hai mode**. **Điểm khác biệt không nằm ở controller** mà nằm ở chứng cứ danh tính của request: stateful dùng cookie session đã tạo từ trước; stateless Basic yêu cầu credentials lại cho request đó.

Không tự gọi `block()` để lấy Authentication và không sử dụng Servlet `SecurityContextHolder` để suy luận security của WebFlux.

## 10. Chạy và quan sát hai mode

Tại thư mục chứa `pom.xml`, chạy test:

~~~bash
mvn clean test
~~~

Để khởi động chế độ session:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=session
~~~

Mở `http://localhost:8080/login` bằng browser; nhập username `student` và password `demo-pass`. Spring Security render form login; nếu browser hỗ trợ cookies, bạn được redirect sau login và có session. Sau đó truy cập `http://localhost:8080/api/me` trong **cùng browser**: kỳ vọng 200 và JSON student. Dùng private window **không có cookie** để gọi `/api/me`: sẽ được yêu cầu login (thường redirect tới `/login` với form login).

Đăng xuất theo flow browser bằng **POST /logout có CSRF token** (trang/biểu mẫu logout của Spring Security xử lý yêu cầu). Sau logout, cookie session cũ không còn đại diện cho Authentication hợp lệ; tải lại `/api/me` phải yêu cầu xác thực lại. Nếu chỉ xóa cookie phía client mà server chưa invalidate session, session có thể vẫn tồn tại tới khi timeout; nên logout chuẩn phải xử lý **server-side invalidation**.

Dừng server rồi khởi động chế độ Basic:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=basic
~~~

Gửi request:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u student http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
~~~

Với lệnh `curl -u student`, công cụ sẽ hỏi password; nhập `demo-pass`. Kỳ vọng theo thứ tự **200, 401, 200, 401**. Lệnh GET thứ ba thành công vì có Basic credentials; lệnh thứ tư là request **mới** không gửi credentials, không được “thừa hưởng đăng nhập” từ request thứ ba.

Trong môi trường local, cách dễ nhất để quan sát là dùng tab Network của browser hoặc `curl -i` và kiểm tra cookie/header. **Không gửi password thật trong command history**, không log Authorization. Cổng mặc định 8080 có thể đổi bằng cấu hình nếu đang có ứng dụng khác chiếm cổng.

### 10.1. Ma trận expected behavior

| Hành động | Session mode | Basic stateless mode |
| --- | --- | --- |
| `GET /api/public` không credential | 200 | 200 |
| `GET /api/me` không credential | Thường redirect tới login (form flow) | 401 với Basic challenge |
| Đăng nhập thành công | Server lưu SecurityContext vào WebSession | Xác thực trên từng request có Authorization |
| Request sau **chỉ có cookie** đã cấp | Có thể 200 nếu session còn hợp lệ | Không được xác thực bởi cookie session |
| Request sau **không cookie/header** | Chưa đăng nhập → login lại | 401 |
| Đăng xuất | Xóa context/invalidate WebSession | Không thể vô hiệu hóa password đã biết chỉ bằng “logout” |
| Gửi lại Basic credentials sau thời điểm vừa “logout” ở client | Basic bị tắt trong mode này | Request mới vẫn có thể 200 |
| Server restart và session store in-memory | Session có thể mất | Không có session xác thực cần phục hồi |

**Không so sánh chỉ mỗi HTTP status giữa hai chế độ rồi kết luận sai chính sách.** Một form-login site có thể redirect 302 với anonymous, trong khi REST API trả 401. Điều cần chứng minh là request anonymous **không tới endpoint protected** và trạng thái xác thực giữa requests khác nhau như thiết kế.

## 11. Kiểm thử tự động bằng WebTestClient

Ta dùng hai test classes, mỗi class bật một Spring profile. `spring-security-test` cung cấp helper `csrf()` trong môi trường WebTestClient mock. Trong project Spring Boot 3.3, `@SpringBootTest` không chỉ định `RANDOM_PORT` kết hợp `@AutoConfigureWebTestClient` cho phép kiểm thử WebFlux trong ApplicationContext; không dùng CSRF mock helper với một HTTP client ngoài thực tế mà cho rằng token sẽ tự xuất hiện trên server khác.

### 11.1. SessionModeTest.java

File `src/test/java/example/state/SessionModeTest.java`:

~~~java
package example.state;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@ActiveProfiles("session")
@AutoConfigureWebTestClient
class SessionModeTest {

    @Autowired
    WebTestClient client;

    @Test
    void loginPersistsAcrossRequestsAndLogoutInvalidatesSession() {
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "demo-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody()
            .returnResult();

        ResponseCookie session = login.getResponseCookies()
            .getFirst("SESSION");
        assertNotNull(session);

        client.get()
            .uri("/api/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");

        client.mutateWith(csrf())
            .post()
            .uri("/logout")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();

        // Cookie cũ sau khi WebSession bị invalidate
        // không được dùng để xem endpoint riêng tư.
        client.get()
            .uri("/api/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

Ở form flow mặc định, user anonymous thường được redirect tới login; test kiểm tra redirect thay vì cưỡng ép phải là 401. Cookie thực tế có thể có tên khác nếu ứng dụng thay cookie resolver, nên đoạn test này cố ý áp dụng **default lab**. `csrf()` là mutator của Spring Security Test, không đại diện việc production client được miễn CSRF.

Nếu dự án dùng custom login page, success handler, API JSON entry point hoặc logout-success handler trả 200, phải sửa assertion theo giao thức đã chọn. Test quan trọng là **request cầm cookie cũ không thể xem /api/me sau logout**.

### 11.2. BasicStatelessModeTest.java

File `src/test/java/example/state/BasicStatelessModeTest.java`:

~~~java
package example.state;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("basic")
@AutoConfigureWebTestClient
class BasicStatelessModeTest {

    @Autowired
    WebTestClient client;

    @Test
    void eachRequestMustPresentCredentialsAgain() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");

        // Request khác không có Basic header: 401.
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();

        // Fake session cookie không thay Basic credentials.
        client.get().uri("/api/me")
            .cookie("SESSION", "not-a-valid-session-id")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void publicEndpointIsStillAccessible() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }
}
~~~

Test Basic chứng minh **một request có credentials đúng không đăng nhập cho request tiếp theo**. Nó không chứng minh toàn bộ ứng dụng “không bao giờ có session cookie”: để xác nhận điều đó phải kiểm tra response headers và các flow khác như CSRF, request cache, OAuth2 login hoặc code ứng dụng tự dùng WebSession.

Đây là test mức web security cho **thực hành**, không phải benchmark. Không dùng các password demo trong môi trường thật; không đưa mật khẩu production vào log hoặc test fixtures công khai.

## 12. Cấu hình stateless JWT Resource Server trong ứng dụng thật

JWT Bearer là một ví dụ phổ biến hơn của API xác thực **từng request**. Mã sau là **cấu hình thay thế** cho profile Basic, **không gắn cùng lúc trong project lab** nếu chưa tạo profile/bean routing rõ ràng.

Thêm dependency (trong `pom.xml`, khi chuyển project sang Resource Server):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ bean cho JWT API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Bean
SecurityWebFilterChain jwtApiChain(ServerHttpSecurity http) {
    var noOp = NoOpServerSecurityContextRepository.getInstance();

    return http
        .securityContextRepository(noOp)
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
        // Chỉ dành cho API Bearer không dựa vào cookie
        // tự động gửi để xác thực; phải đánh giá CSRF trước.
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
}
~~~

Đây là **đoạn bean minh họa**, cần đặt trong `@Configuration`, cung cấp issuer/decoder hợp lệ và xóa các chain demo đang trùng phạm vi. Ví dụ không tự ký JWT, không cấp refresh token và không chứng minh rằng tắt CSRF luôn an toàn.

Cấu hình issuer ở nơi cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/issuer
~~~

Tên miền `example.invalid` không có issuer thật; phải thay bằng IdP hoạt động với metadata/JWKS và access token được cấp đúng audience/scope của ứng dụng. Với cấu hình cơ bản, Resource Server kiểm chứng chữ ký, `iss`, `exp`/`nbf`. **Đừng mặc định issuer-uri tự kiểm tra đúng audience của API**; bổ sung audience validation theo hợp đồng bảo mật. Nếu dùng opaque token, thay decoder JWT bằng introspection theo mô hình phù hợp.

Một request JWT không có token → thường **401**; token hợp lệ và đủ quyền → controller chạy; token hợp lệ nhưng thiếu scope/authority của endpoint → **403**. Một `JwtAuthenticationToken` vẫn được tạo trong local Reactor Context **cho request đó**, dù server không giữ WebSession authentication.

### 12.1. Stateless chỉ khi credential **không dựa vào auto-sent cookie**

Nếu access token JWT được đặt trong cookie và browser tự gửi ở mọi request, threat model CSRF tương tự cơ chế cookie khác vẫn cần được đánh giá. **Không tắt CSRF chỉ vì dùng JWT.** Việc disable CSRF trong snippet chỉ phù hợp với API dùng Authorization Bearer header do client chủ động gắn, không có cookie/basic/session tự động được dùng để xác thực và đã có đánh giá threat model.

### 12.2. Authentication state và token state khác nhau

Một service không giữ session xác thực vẫn có thể sử dụng:

- Cache JWKS/kết quả introspection, connection pools và database.
- Refresh token store tại Authorization Server.
- Denylist/allowlist, token version, audit, risk engine và rate limiter.
- Thông tin quyền/tenant trong DB hoặc service authorization.
- `WebSession` cho một phần giao diện khác nếu kiến trúc kết hợp session + API.

Vì vậy khái niệm chính xác là **stateless authentication at resource server boundary**, không phải “100% không có state ở bất kỳ service nào”.

## 13. Đăng xuất: khác biệt quan trọng nhất

### 13.1. Logout trong session-based application

Một POST logout hợp lệ với CSRF token làm server xóa SecurityContext và/hoặc invalidate WebSession. Cookie cũ được client gửi lại **không còn tham chiếu tới phiên xác thực còn hiệu lực**. Muốn logout từ tất cả thiết bị, phải có khả năng tìm/xóa tất cả session tương ứng với user, không phải chỉ invalidate session trên thiết bị hiện tại.

Cookie client có thể bị xóa cùng lúc, nhưng chỉ xóa cookie trong browser là **chưa đủ** để thu hồi session bị đánh cắp — bản copy session ID ở nơi khác có thể vẫn dùng được cho đến khi server xóa hoặc hết hạn.

### 13.2. Logout với Bearer JWT stateless

Xóa access token khỏi bộ nhớ an toàn của client và dừng refresh có thể kết thúc “phiên” của client. Nhưng **một bản copy access token tự chứa còn hợp lệ có thể tiếp tục được resource server chấp nhận đến khi hết hạn**, trừ khi có cơ chế thu hồi/token version/denylist/introspection được áp dụng.

Mức độ cần thu hồi phụ thuộc rủi ro:

- **Access token ngắn hạn:** giới hạn cửa sổ rủi ro; không tạo khả năng thu hồi tức thì.
- **Refresh token rotation và revocation:** chặn cấp **access token mới**, không nhất thiết làm access token đã phát lập tức vô hiệu.
- **Denylist theo `jti` hoặc token fingerprint:** resource server kiểm tra mỗi request; tăng state/latency và cần vận hành store/TTL.
- **Opaque token + introspection:** có thể thu hồi ở hệ thống trung tâm, nhưng caching introspection làm chậm hiệu lực thu hồi nếu TTL không phù hợp.
- **Token version / session version:** kiểm tra dữ liệu hiện hành của tài khoản hoặc session server-side để từ chối token cũ; từ chối hoàn toàn không tra cứu state sẽ khó có hiệu lực tức thời.
- **Xoay khóa ký:** ảnh hưởng diện rộng, không phải biện pháp logout một user thông thường.
- **OIDC front-/back-channel logout:** giải quyết ngữ cảnh phiên SSO/RP theo protocol và khả năng của IdP; không đồng nhất với thu hồi mọi OAuth2 access token.

**HTTP Basic cũng không có “logout” server-side phiên xác thực** trong mode NoOp: nếu client tiếp tục gửi username/password hợp lệ, server sẽ xác thực lại. Xóa credentials khỏi client hoặc đổi password/disable account có thể thay đổi hành vi về sau, nhưng không có cookie session để invalidate.

### 13.3. Bảng so sánh thao tác logout

| Hành động | Stateful WebSession | Stateless JWT/Bearer | Stateless HTTP Basic |
| --- | --- | --- | --- |
| Xóa credential ở client | Browser ngừng gửi session ID, nhưng session có thể còn ở server | Client ngừng gửi token, bản copy khác vẫn có thể dùng | Client ngừng gửi Basic; browser cache có thể khó xóa chắc chắn |
| Server invalidate ngay một phiên | Có, nếu store hỗ trợ và logout handler phù hợp | Không tự có; cần denylist/validation online/session version | Không có phiên đã lưu, chỉ kiểm tra password request kế |
| Hết hạn | Server session TTL/timeout | `exp` JWT/TTL/token policy | Phụ thuộc hiệu lực password/account |
| Logout tất cả thiết bị | Cần registry/store tìm toàn bộ sessions | Cần revocation policy/token family/refresh sessions phù hợp | Có thể vô hiệu hóa credentials (ảnh hưởng cả user) |
| Đánh cắp credential | Session ID có thể bị dùng tới khi invalidate/expire | Bearer token có thể bị dùng tới khi expire/revoke | Password bị lộ có rủi ro lớn tới khi đổi/disable |

## 14. CSRF, XSS và vị trí lưu credential

Không có công thức “stateful nguy hiểm, stateless an toàn hơn” hay ngược lại. Rủi ro dựa vào **credential được mang bằng cách nào**.

| Lưu credential | Browser có tự gửi theo request? | Rủi ro chính | Biện pháp |
| --- | --- | --- | --- |
| Session ID trong cookie | Có, theo cookie policy | CSRF, session hijack | CSRF token, Secure/HttpOnly/SameSite, session timeout/invalidation |
| JWT trong cookie | Có | CSRF **vẫn tồn tại**, token theft | CSRF policy, cookie flags, token expiry/revocation |
| Bearer token ở JS memory | Chỉ khi JS tự gắn header | XSS có thể lấy token; refresh sau reload | CSP/XSS mitigation, short-lived token, tránh log |
| Bearer token ở localStorage | JS tự gắn header | XSS đánh cắp token tồn tại lâu | Hạn chế lưu token trong JS-readable persistent storage |
| HTTP Basic browser cache | Browser có thể tự gửi sau challenge | CSRF/credential exposure tùy client, khó logout | HTTPS, CSRF theo threat model, ưu tiên cơ chế khác |

**CORS không phải authentication.** Cho origin khác đọc response không tự cấp quyền, và chặn CORS trong browser không có nghĩa API đã được bảo vệ khỏi curl/server-to-server calls. CSRF dựa trên việc browser tự gắn credentials cho cross-site requests; JWT nằm ở đâu và gửi thế nào mới là điểm quyết định.

Session cookie `HttpOnly` giúp JavaScript không đọc trực tiếp cookie, nhưng XSS vẫn có thể thực hiện hành động qua trình duyệt đã đăng nhập. Vì vậy phải đồng thời có input/output encoding, CSP phù hợp, CSRF và authorization dữ liệu.

## 15. Vận hành và scale: chọn kiến trúc theo yêu cầu

### 15.1. Stateful có thật sự khó scale?

Không nhất thiết. Nếu server lưu session trong bộ nhớ của một instance, mất pod/redeploy hoặc load-balancing sang instance khác có thể làm mất login; giải pháp là sticky session **hoặc** dùng shared session store như Spring Session + Redis. Shared store tăng tính liên tục giữa các instance nhưng thêm network IO, TTL, consistency, bảo mật session store và khả năng phục hồi. Phải quản lý session fixation, session hijack, timeout, logout và invalidation khi role đổi.

### 15.2. Stateless có thật sự không cần hạ tầng chung?

JWT offline verification có thể giảm đọc session store từng request; nhưng API vẫn cần JWKS/key rotation, đồng bộ clock, audience validation, rate limits và dữ liệu nghiệp vụ. Nếu muốn revoke ngay, bạn thường phải tra denylist/introspection hoặc trạng thái tài khoản, làm tăng phụ thuộc state. Không nên đánh đổi bảo mật thu hồi vì một khẩu hiệu “stateless tuyệt đối”.

### 15.3. So sánh quyết định

| Nhu cầu | Session-based thường phù hợp | Bearer-based thường phù hợp |
| --- | --- | --- |
| Website server-rendered có login/logout browser | Dễ quản lý qua session và cookie, CSRF | Có thể dùng OIDC + backend-for-frontend, nhưng không nhất thiết lưu token trong JS |
| Mobile/API với Authorization header | Có thể dùng session nếu protocol phù hợp | Thường phù hợp OAuth2/OIDC access token |
| Logout ngay một thiết bị | Invalidate session | Cần cơ chế thu hồi nếu không chờ expiry |
| Dịch vụ nhiều instance | Cần shared store hoặc session affinity | Dễ phân phối validation JWT, nhưng còn key/authorization state |
| Chính sách quyền thay đổi tức thời | Revoke/revalidate session | Cần DB/claims version/denylist, tránh tin claim cũ quá lâu |
| Tích hợp nhiều resource servers | Session cookie của một app không tự dùng được ở B | Token đúng audience/scope có thể dùng theo hợp đồng; không relay token sai audience |
| Stateless bắt buộc vì latency | Cần đo store latency thực tế | Cần đo JWT verify, introspection, cache; không giả định luôn nhanh hơn |

Không kết luận từ tên công nghệ. Hãy bắt đầu từ **client loại gì, lifetime của credential, yêu cầu logout/revocation, data authorization, scaling, risk và trải nghiệm**.

## 16. Giữ quyền dữ liệu đúng trong cả hai mô hình

Ở cả stateful lẫn stateless, `authenticated()` chỉ xác định người gọi có danh tính hợp lệ. Nó **không** đồng nghĩa user được phép đọc mọi tài nguyên.

Ví dụ `GET /api/orders/42`:

- Stateful: session có user ID A; service phải kiểm tra order 42 có thuộc A hoặc tenant được phép không.
- Stateless: JWT có `sub=A`, scope `orders.read`; service vẫn phải kiểm tra order 42 thuộc A/tenant hợp lệ.
- Nếu role/tenant đổi, session authorities và JWT claims có thể đã cũ. Bên cạnh expiry/logout, cần policy để quyền thu hồi có hiệu lực đúng thời hạn.
- Nếu service A gọi B, context của A **không tự đi qua HTTP**. B xác thực credential outbound riêng và quyết định quyền tài nguyên ở B.

Không dùng “token đã ký” như một lý do bỏ kiểm tra owner/tenant. Signature chứng minh token do nguồn được tin cấp và chưa bị sửa, **không** chứng minh được người gọi có quyền trên mọi object.

## 17. Những lỗi cấu hình thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đăng nhập form xong, GET /api/me vẫn yêu cầu login | Cookie SESSION không được gửi, repo sai, session mất hoặc login không lưu context | Kiểm tra Set-Cookie/Cookie (không log giá trị), session store, repo của formLogin |
| Basic stateless trả 200 ở request thiếu header | Có session/auth filter khác, test client tự gửi credentials hoặc matcher sai | Đọc đúng security chain, kiểm tra request outbound thực |
| Thay `securityContextRepository(NoOp)` nhưng vẫn thấy SESSION cookie | CSRF/request cache/feature khác tạo WebSession hoặc auth filter riêng lưu context | Kiểm tra tất cả thành phần có session state, không chỉ repo |
| POST /logout trả 403 | Thiếu/không đúng CSRF token, session expired | Giữ POST và token CSRF; kiểm tra flow login/logout |
| Logout rồi request cũ vẫn 200 | Server chưa invalidate session hoặc browser còn gửi Basic/Bearer | Phân biệt credential thực trên request mới, token revocation vs session |
| User đăng nhập ở node A nhưng sang B mất phiên | Session in-memory không chia sẻ giữa nodes | Shared session store/affinity/TTL theo kiến trúc |
| JWT vẫn chạy sau khi click Logout | Access token vẫn còn hiệu lực và không có revocation check | Thiết kế TTL/denylist/introspection/revoke refresh |
| Token hợp lệ nhưng B trả 401 | Sai issuer/audience, token expired hoặc B không nhận token | Kiểm tra validation tại B và header outbound |
| GET chạy, POST trả 403 | CSRF bảo vệ unsafe method hoặc thiếu authority | Phân biệt CSRF với authorization |
| Cookie JWT và tắt CSRF vì “stateless” | Browser vẫn tự gửi cookie, tạo CSRF risk | Dùng threat model dựa trên credential transport |
| SecurityContextHolder ThreadLocal rỗng | Đang dùng WebFlux Reactor Context | Dùng ReactiveSecurityContextHolder bên trong Mono/Flux |
| Revoke role nhưng request vẫn có quyền cũ | Session/token claims cache đã cũ | Session invalidation hoặc revalidation/versioning |

**Thứ tự điều tra nên cố định:** request có cookie/header gì (không log secret) → security chain nào chọn → authentication mechanism → SecurityContextRepository → CSRF/authorization → controller → session/token lifetime/revocation.

## 18. Bài tập vận dụng

### Bài A — mô tả hai request liên tiếp

Vẽ sequence cho login bằng form, server phát session cookie rồi hai GET /api/me: GET có cookie phải có danh tính; GET không cookie phải bị chặn. Vẽ sequence thứ hai cho Bearer: hai GET đều phải tự mang token được chấp nhận. Chỉ ra lúc nào Authentication được tạo/tải.

### Bài B — thay repository trong lab

Ở profile Basic, đọc code `NoOpServerSecurityContextRepository` rồi giải thích vì sao `ReactiveSecurityContextHolder` vẫn có Authentication khi một request Basic thành công. Thử bỏ Basic header ở request tiếp theo: dự đoán status. Không tự thay NoOp bằng một repository session chỉ để “làm test pass”.

### Bài C — quan sát logout session

Chạy test session: login, lấy cookie, GET /api/me, POST /logout với CSRF, gửi lại cookie cũ. Giải thích vì sao invalidation tại server quan trọng hơn chỉ xóa cookie ở browser.

### Bài D — phân biệt token access và refresh

Giả định JWT access token sống 10 phút, refresh token sống 7 ngày. User logout ở phút thứ 2: thu hồi refresh token ngăn điều gì? Token access đã phát có còn dùng được không khi Resource Server chỉ verify offline? Đề xuất một cơ chế revoke với SLA tức thời nếu nghiệp vụ yêu cầu.

### Bài E — CSRF với JWT trong cookie

Thiết kế API dùng JWT lưu trong HttpOnly cookie. Dù server không lưu session Authentication, browser vẫn tự gửi cookie. Giải thích vì sao phải đánh giá CSRF, và viết test POST có/không CSRF token theo policy đã chọn.

### Bài F — scale multi-instance

Giả định hai replicas WebFlux và load balancer round-robin. Vẽ điều xảy ra nếu session chỉ nằm trong memory của replica A; đề xuất Spring Session/Redis hoặc sticky sessions. So sánh với JWT offline verify, xét thêm JWKS rotation, revoke và authorization dữ liệu.

### Bài G — phân quyền sau khi thay role

User đang có role ADMIN rồi bị thu hồi quyền. Với session và JWT ngắn hạn, thay đổi có thể hiệu lực khi nào? Thiết kế policy đáp ứng yêu cầu thu hồi trong 1 phút mà không dựa vào giả định token tự cập nhật.

### Checklist tự đánh giá

- [ ] Giải thích được “stateful” là giữ authentication giữa requests, không phải chỉ là có cookie.
- [ ] Biết `WebSession` khác `SecurityContext` và `Reactor Context`.
- [ ] Biết `WebSessionServerSecurityContextRepository` lưu SecurityContext qua requests.
- [ ] Biết `NoOpServerSecurityContextRepository` không lưu SecurityContext, nhưng không xóa mọi state của ứng dụng.
- [ ] Phân biệt form login/session với per-request Basic và JWT.
- [ ] Chạy được hai Spring profiles và kiểm thử âm tính qua WebTestClient.
- [ ] Giải thích được session logout vs JWT access token revocation.
- [ ] Biết CSRF phụ thuộc vào credential có được browser tự gửi hay không.
- [ ] Không nhầm Spring WebFlux ServerHttpSecurity với Servlet HttpSecurity/SessionCreationPolicy.
- [ ] Đề xuất được giải pháp session store và token revocation khi scale.
- [ ] Biết auth thành công không tự cấp quyền trên mọi order/tenant.

## 19. Câu hỏi tự kiểm tra

1. Một request mới chỉ mang `Cookie: SESSION=...`: phần nào của server khôi phục Authentication?
2. Vì sao `ReactiveSecurityContextHolder.getContext()` vẫn có thể trả context trong mode NoOp?
3. `NoOpServerSecurityContextRepository` có cấm mọi WebSession trong app không?
4. Tại sao POST logout của form-based WebFlux nên có CSRF token?
5. Vì sao chỉ xóa cookie client chưa chắc vô hiệu hóa session ID bị đánh cắp?
6. Nếu gửi lại HTTP Basic credentials sau “logout”, server có thể xác thực lại không?
7. JWT trong cookie có miễn CSRF vì server không lưu session Authentication không?
8. Khi click logout ở client nhưng JWT chưa hết hạn, resource server offline verifier có chấp nhận lại nó không?
9. Opaque token introspection có nghĩa resource server stateful session không? Vì sao?
10. Nếu app có 4 replicas, session state lưu ở đâu để người dùng không mất login?
11. Tại sao một user `authenticated()` vẫn không mặc nhiên được xem order của user khác?
12. Khi thay đổi role lập tức, các chiến lược nào giúp session/JWT cũ không giữ quyền quá thời hạn được chấp nhận?

## 20. Tài liệu chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình `SecurityWebFilterChain`, formLogin, httpBasic.
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html): lưu SecurityContext vào WebSession, session-id rotation.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): chiến lược load/save giữa requests.
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html): không lưu/tải context giữa requests.
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): mặc định logout và `WebSessionServerLogoutHandler`.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): cơ chế CSRF, form login/logout, cookie token repository.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Bearer JWT validation và authorities.
- [Spring Security — WebTestClient CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): mutator `csrf()`.
- [Spring Framework — WebFlux WebSession](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattributes.html): cách dùng dữ liệu phiên trong WebFlux; xem thêm API `WebSession`.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, cookie flags, fixation, timeout và logout.
- [OWASP — JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT storage, logout/revocation, key/claim validation.

**Kết luận:** Ở ứng dụng **stateful**, server duy trì thông tin đăng nhập trong `WebSession` và client đưa session ID để tìm lại Authentication; POST logout có thể invalidate phiên tại server. Ở ứng dụng **stateless authentication**, mỗi HTTP request phải mang credential được kiểm chứng cho chính nó; local SecurityContext vẫn có trong request, nhưng không được nạp từ session đã lưu. Đặc biệt với JWT, “xóa token trên client” không tương đương “thu hồi token ở server”; và “stateless” không miễn các yêu cầu về CSRF, quyền dữ liệu, rate limiting hoặc quản lý credential.