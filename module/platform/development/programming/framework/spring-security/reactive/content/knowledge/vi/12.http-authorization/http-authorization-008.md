# Tra cứu quyền bằng dữ liệu reactive mà không chặn luồng trong Spring Security WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication** (ai đang gọi), **authorization** (có được phép hay không) và **kiểm tra quyền trên từng tài nguyên** (ABAC/ACL) trong HTTP request.
2. Hiểu vai trò của `ReactiveAuthorizationManager<AuthorizationContext>` và cách gắn vào `ServerHttpSecurity.authorizeExchange(...).access(...)`.
3. Đọc principal và path variable từ ngữ cảnh request, truy vấn ACL bằng R2DBC/`DatabaseClient` để trả `Mono<AuthorizationDecision>` mà **không gọi `block()`**.
4. Thực thi quy tắc **deny by default**, phân biệt quyền không tồn tại với lỗi database; không vô tình cấp quyền do `Mono.empty()`, timeout hay SQL injection.
5. Xây dựng ứng dụng Spring Boot WebFlux Java 17+ có hai người dùng, cơ sở dữ liệu H2 R2DBC, API đọc tài liệu và các bài kiểm thử `WebTestClient`.
6. Đánh giá hiệu năng, TOCTOU, caching, audit và phân quyền tầng service để áp dụng khi triển khai PostgreSQL.

> Phiên bản minh họa: **Spring Boot 3.x với Spring Security 6.5.x**, Java 17+. API reactive dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveAuthorizationManager`, `Mono` và `Flux`. Spring Security 6.5 đã đánh dấu phương thức `check(...)` là deprecated để hướng tới `authorize(...)`; ví dụ dành cho 6.5 dùng `check(...)` vì đó vẫn là phương thức abstract của interface trong phiên bản này. Nếu nâng lên Spring Security 7.x, đối chiếu lại contract của interface trước khi chuyển mã.

## 1. Bài toán thực tế: role chung không đủ

Giả sử hệ thống có API:

```text
GET /documents/100
GET /documents/200
```

Hai người dùng `alice` và `bob` đều có role `ROLE_READER`. Nếu chỉ viết:

```java
.pathMatchers("/documents/**").hasRole("READER")
```

thì **cả hai** đều có thể đọc mọi document, trừ khi nghiệp vụ ở tầng sau còn kiểm tra. Thực tế, Alice chỉ được đọc document 100, Bob chỉ được đọc document 200. Quy tắc cần xem cả **principal** lẫn **document ID**:

```text
CanRead(username, documentId) =
  user đã được xác thực
  AND có ROLE_READER
  AND database có quyền READ cho username + documentId
```

Đây là **object-level authorization**, có thể triển khai qua ACL (Access Control List) hoặc thuộc tính (ABAC). Kiểm tra URL không thay thế việc áp dụng cùng nguyên tắc ở service/repository, nơi dữ liệu thật được lấy.

| Loại quyết định | Ví dụ | Cách phổ biến |
| --- | --- | --- |
| Chỉ xác thực | Mọi user đăng nhập được xem `/profile` | `authenticated()` |
| Role/authority tĩnh | Chỉ ADMIN vào `/admin/**` | `hasRole("ADMIN")` |
| Quyền tùy tài nguyên | Alice đọc document 100 nhưng không đọc 200 | `.access(customReactiveManager)` truy vấn ACL |
| Quyền theo thuộc tính | Người xử lý đơn hàng cùng phòng ban và đơn còn trạng thái OPEN | Rule nghiệp vụ + truy vấn dữ liệu có điều kiện |
| Quyền tại service | Lấy đúng bản ghi được phép theo owner/tenant | Query đã lọc theo principal, method security hoặc cả hai |

**Nguyên tắc:** dữ liệu từ client (ID, tenant header, query param) không phải bằng chứng người đó có quyền. Phải so với danh tính đã xác thực và chính sách server-side.

## 2. Tại sao bắt buộc non-blocking trong WebFlux?

Spring WebFlux dựa trên Reactor để biểu diễn chuỗi bất đồng bộ. Khi HTTP request chạy qua authorization WebFilter, Spring Security có thể chờ **publisher** trả quyết định. Nếu bạn gọi JDBC blocking hoặc `.block()` ngay tại event loop Reactor Netty, thread bị giữ để chờ database, làm tăng độ trễ và giới hạn số request concurrent.

| Cách | Vấn đề / lợi ích |
| --- | --- |
| `jdbcRepository.find(...);` bên trong HTTP filter | I/O đồng bộ có thể chặn event loop |
| `Mono.just(jdbcRepository.find(...))` | Vẫn gọi JDBC **ngay khi tạo Mono**, không biến thành non-blocking |
| `databaseClient.sql(...).fetch().first()` từ R2DBC | Trả `Mono` và thực thi khi được subscribe |
| `permissionMono.block()` | Chờ đồng bộ, có thể gây lỗi trên non-blocking thread |
| `permissionMono.flatMap(...)` hoặc `map(...)` | Nối logic authorization vào cùng pipeline |
| `permissionMono.subscribe()` thủ công trong manager | Tách khỏi request lifecycle, có thể trả quyết định trước khi DB xong |
| `Mono.fromCallable(blockingIo).subscribeOn(boundedElastic())` | Cách **cô lập blocking** khi buộc dùng thư viện blocking, không biến driver thành reactive |

R2DBC (Reactive Relational Database Connectivity) giúp truy vấn cơ sở dữ liệu quan hệ qua driver reactive. Với Spring Boot, `ConnectionFactory` được cấu hình qua `spring.r2dbc.*`; `DatabaseClient` tạo câu SQL và trả các publisher. Khi query thất bại, publisher phát `onError`, không nên biến mọi lỗi thành `true` hoặc fallback tự động mở quyền.

### Sơ đồ chuỗi authorization

```text
Client GET /documents/100 + HTTP Basic
           |
           v
Spring Security WebFilter chain
           |
           +--> Authentication filters:
           |      xác thực username/password -> Authentication
           |
           +--> AuthorizationWebFilter
                  |
                  +--> Path matcher /documents/{id}
                  |        -> AuthorizationContext:
                  |           {id = "100"}
                  |
                  +--> ReactiveAuthorizationManager.check(
                  |        Mono<Authentication>, context)
                  |              |
                  |              +--> username = alice
                  |              +--> verify ROLE_READER
                  |              +--> database check (R2DBC)
                  |                       |
                  |                       +--> ACL row exists -> true
                  |                       +--> no ACL row     -> false
                  |
                  +--> Mono<AuthorizationDecision>
                          |
                          +--> granted=true  -> controller
                          +--> granted=false -> 403 (authenticated)
                          +--> no identity   -> 401 (Basic entry point)
```

Cùng một manager cũng có thể được áp dụng cho nhiều URL, nhưng phải xác nhận path variables và semantics của từng matcher; đừng tạo một manager đọc sai biến rồi trả `permit` theo mặc định.

## 3. Hợp đồng ReactiveAuthorizationManager

Spring Security 6.5 định nghĩa interface `org.springframework.security.authorization.ReactiveAuthorizationManager<T>`. Đối với HTTP WebFlux, thường dùng `T = AuthorizationContext`.

Chữ ký tương ứng ở 6.5:

```java
// Chữ ký interface để giải thích, không phải chương trình độc lập:
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context);

// Từ 6.4 có thêm default method mới:
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        AuthorizationContext context);
```

Ở Spring Security 6.5, `check` đã được đánh dấu deprecated, nhưng nó vẫn là abstract method mà nhiều implementation hiện tại sử dụng; `authorize` mặc định có thể gọi `check`. Khi code theo đúng baseline 6.5, việc implement `check` vẫn hợp lệ. Ở phiên bản mới hơn, hãy kiểm tra tài liệu API trước khi chuyển sang `authorize`; không đổi kiểu trả về máy móc từ `Mono<AuthorizationDecision>` sang `Mono<AuthorizationResult>` khi compiler chưa khớp.

Trong rule HTTP:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/documents/{id}")
            .access(documentAuthorizationManager)
        .anyExchange().denyAll()
)
```

- `pathMatchers(...)` lựa chọn request bằng HTTP method và path pattern; thứ tự rule quan trọng.
- `AuthorizationContext.getVariables()` cung cấp biến template, ví dụ `id`.
- `AuthorizationContext.getExchange()` cung cấp request/headers/remote address và những dữ liệu khác nếu cần; không tin header caller tự đặt là quyền.
- `authentication` là publisher, có thể rỗng; không được gọi `authentication.block()` hoặc `authentication.get()` kiểu Servlet.
- `AuthorizationDecision(true)` cấp quyền, `AuthorizationDecision(false)` từ chối. `Mono.empty()` có thể được diễn giải là **abstain/no decision**, không nên dùng nó làm đường xử lý thiếu user hoặc thiếu ACL nếu policy muốn deny rõ ràng.

### Fail closed khác "giấu mọi lỗi"

Hai tình huống phải được phân biệt:

1. Không có ACL row: đây là **quyết định không được phép**, trả `AuthorizationDecision(false)`.
2. Database timeout/connection failure: đây là **lỗi hạ tầng**; request không được cấp quyền, nhưng lỗi nên được ghi nhận là lỗi hệ thống, không tự ép thành "không có ACL" và làm mất tín hiệu giám sát.

Đừng viết `onErrorReturn(new AuthorizationDecision(true))` hoặc `onErrorResume(ex -> Mono.just(new AuthorizationDecision(true)))`. Trong demo, lỗi R2DBC được **propagate** lên pipeline để xử lý theo error handling/server policy; như vậy không cấp quyền khi hệ thống không biết kết quả. Nếu hệ thống muốn chuyển mọi lỗi kiểm tra quyền thành 503 thay vì 500, đặt exception mapping/telemetry phù hợp, tuyệt đối không fallback sang permit.

## 4. Xây dựng demo hoàn chỉnh: dữ liệu ACL reactive với H2 R2DBC

Ta dùng ba bảng minh họa:

- `documents`: tài liệu có ID và nội dung.
- `document_permissions`: username nào có quyền READ document nào.
- Người dùng được xác thực bằng `MapReactiveUserDetailsService` **chỉ để demo HTTP Basic**. Quyền trên từng document được tra riêng từ database qua R2DBC.

Thiết kế tách **đăng nhập** và **tra cứu quyền**. Trong sản phẩm, username nên được thay bằng **principal ID bất biến** từ identity provider/database, có ràng buộc tenant phù hợp; không dựa vào tên hiển thị có thể đổi.

### 4.1. Gradle dependencies

Project Spring Boot 3.x Java 17 có plugin Spring Boot/Dependency Management đã thiết lập cần:

**`build.gradle`** (phần dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Không thêm `spring-boot-starter-web` trong demo thuần WebFlux vì Spring Boot thường ưu tiên Servlet nếu cả starter MVC và WebFlux cùng tồn tại.

### 4.2. Cấu hình R2DBC và dữ liệu test

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: reactive-document-authorization
  r2dbc:
    url: "r2dbc:h2:mem:///permissiondb?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
      schema-locations: "classpath:schema.sql"
      data-locations: "classpath:data.sql"

server:
  port: 8080
```

URL `r2dbc:h2:...` là cho R2DBC, không phải `jdbc:h2:...`. H2 in-memory được dùng để học và test; `spring.sql.init.mode=always` chỉ phù hợp khi bạn chủ động muốn dựng schema/dữ liệu demo. Production nên dùng migrations có version và secret/DB riêng.

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT PRIMARY KEY,
    body VARCHAR(2000) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_permissions (
    document_id BIGINT NOT NULL,
    username VARCHAR(120) NOT NULL,
    permission VARCHAR(30) NOT NULL,
    PRIMARY KEY (document_id, username, permission),
    CONSTRAINT fk_document_permissions_doc
        FOREIGN KEY (document_id) REFERENCES documents(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_permissions_username
    ON document_permissions(username);
```

**`src/main/resources/data.sql`** — chỉ là dữ liệu **không nhạy cảm** cho demo:

```sql
INSERT INTO documents(id, body)
VALUES (100, 'Plan A: internal'), (200, 'Plan B: private');

INSERT INTO document_permissions(document_id, username, permission)
VALUES (100, 'alice', 'READ'), (200, 'bob', 'READ');
```

Mỗi document có thể được cấp nhiều quyền qua nhiều hàng. Primary key ghép ngăn bản ghi quyền trùng; khóa ngoại bảo đảm ACL không trỏ tới document không tồn tại. Với thực tế, cần phân loại tenant, owner, action (READ/EDIT/DELETE), audit cấp quyền và kiểm soát ai được ghi bảng này.

**Hành vi được kiểm tra trong bài:**

| User | Role | Document 100 | Document 200 |
| --- | --- | --- | --- |
| `alice` | `ROLE_READER` | READ | Không được cấp |
| `bob` | `ROLE_READER` | Không được cấp | READ |
| anonymous | Không có login | Không | Không |

Lưu ý không suy quyền từ role `ROLE_READER` đơn thuần; role này là điều kiện cần, ACL mới chỉ ra **tài liệu cụ thể**.

### 4.3. Main class

**`src/main/java/example/reactiveauthz/ReactiveAuthzApplication.java`**:

```java
package example.reactiveauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthzApplication.class, args);
    }
}
```

Cấu trúc project:

```text
src/
  main/
    java/example/reactiveauthz/
      ReactiveAuthzApplication.java
      DocumentPermissionRepository.java
      DocumentReadAuthorizationManager.java
      SecurityConfiguration.java
      DocumentController.java
    resources/
      application.yml
      schema.sql
      data.sql
  test/
    java/example/reactiveauthz/
      DocumentAuthorizationTest.java
```

### 4.4. Repository query ACL bằng DatabaseClient

**`src/main/java/example/reactiveauthz/DocumentPermissionRepository.java`**:

```java
package example.reactiveauthz;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentPermissionRepository {

    private final DatabaseClient client;

    public DocumentPermissionRepository(DatabaseClient client) {
        this.client = client;
    }

    public Mono<Boolean> hasReadPermission(
            String username, long documentId) {
        return client.sql("""
                    SELECT 1 AS allowed
                      FROM document_permissions
                     WHERE username = :username
                       AND document_id = :documentId
                       AND permission = 'READ'
                    """)
                .bind("username", username)
                .bind("documentId", documentId)
                .fetch()
                .first()
                .hasElement();
    }

    public Mono<String> readVisibleDocument(
            String username, long documentId) {
        return client.sql("""
                    SELECT d.body
                      FROM documents d
                      JOIN document_permissions p
                        ON p.document_id = d.id
                     WHERE d.id = :documentId
                       AND p.username = :username
                       AND p.permission = 'READ'
                    """)
                .bind("username", username)
                .bind("documentId", documentId)
                .map((row, metadata) -> row.get("body", String.class))
                .one();
    }
}
```

**Giải thích chi tiết:**

- `DatabaseClient` dùng `ConnectionFactory` R2DBC mà Spring Boot đã cấu hình, trả publisher thay vì kết quả blocking.
- `:username` và `:documentId` được bind qua `.bind(...)`. Không nối username hoặc path variable trực tiếp vào SQL vì có nguy cơ SQL injection.
- `.fetch().first()` tạo `Mono<Map<String,Object>>` chứa hàng đầu tiên; `.hasElement()` biến thành `Mono<Boolean>`: có hàng thì `true`, không có hàng thì `false`. Lỗi SQL vẫn phát `onError`, không bị chuyển thành `false` một cách mù quáng.
- `readVisibleDocument` dùng **JOIN với ACL trong chính query đọc body**. Đây là *defense in depth*: kể cả khi HTTP authorization trước đó đã cho phép, truy vấn dữ liệu nghiệp vụ vẫn kiểm soát user đang đọc. Tránh dựa hoàn toàn vào filter khi có các entry point khác gọi thẳng service/repository.
- `.one()` trả `Mono<String>` cho đúng một document. Schema primary key/ACL ngăn nhiều hàng trùng trong ví dụ.
- Repository không có `.block()`, `.subscribe()` hoặc `ExecutorService` tự chế; framework subscribe publisher khi xử lý request.

**Lưu ý consistency:** Authorization filter và controller làm hai query, nên ACL có thể bị thay đổi giữa chúng (TOCTOU). Query thứ hai vẫn bao gồm ACL để ngăn đọc sau khi quyền bị thu hồi. Nếu quy tắc bảo mật đòi một snapshot atomic hoặc consistency mạnh, cần transaction/isolation theo nghiệp vụ và thiết kế nhất quán hơn, không dựa vào kiểm tra đầu request là đủ.

### 4.5. ReactiveAuthorizationManager của HTTP

**`src/main/java/example/reactiveauthz/DocumentReadAuthorizationManager.java`**:

```java
package example.reactiveauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DocumentReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final DocumentPermissionRepository permissions;

    public DocumentReadAuthorizationManager(
            DocumentPermissionRepository permissions) {
        this.permissions = permissions;
    }

    @Override
    @SuppressWarnings("deprecation") // check() vẫn là hợp đồng abstract của 6.5
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object rawId = context.getVariables().get("id");
        if (rawId == null) {
            return denied();
        }

        final long documentId;
        try {
            documentId = Long.parseLong(String.valueOf(rawId));
        } catch (NumberFormatException invalidId) {
            return denied();
        }

        if (documentId <= 0) {
            return denied();
        }

        return authentication
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .filter(auth -> auth.getAuthorities().stream()
                        .anyMatch(authority ->
                                "ROLE_READER".equals(authority.getAuthority())))
                .map(Authentication::getName)
                .flatMap(username ->
                        permissions.hasReadPermission(username, documentId))
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private Mono<AuthorizationDecision> denied() {
        return Mono.just(new AuthorizationDecision(false));
    }
}
```

**Điểm quan trọng trong manager:**

1. `context.getVariables().get("id")` nhận path variable của rule `/documents/{id}`. Nếu thiếu hoặc ID không phải số dương, **trả deny**; không ném `NumberFormatException` thành 500 chỉ vì client gửi `/documents/abc`.
2. `authentication` là `Mono<Authentication>`. Ta dùng `filter` để loại principal chưa xác thực và `AnonymousAuthenticationToken`. Không dựa vào `isAuthenticated()` một mình: anonymous token cũng có thể được đánh dấu authenticated theo semantics của token.
3. Kiểm tra `ROLE_READER` là lớp quyền ở mức chức năng; sau đó `flatMap` nối truy vấn ACL ở database.
4. `permissions.hasReadPermission(...)` trả `Mono<Boolean>`, được chuyển thành `AuthorizationDecision`. Không `block()`.
5. `defaultIfEmpty(new AuthorizationDecision(false))` đảm bảo không có authentication hoặc không qua bộ lọc role thì **quyết định từ chối rõ ràng**, không để `Mono.empty()` thành abstain rồi vô tình dựa vào policy khác.
6. Nếu R2DBC phát `onError`, pipeline **không cấp quyền**; lỗi đi vào error handling của hệ thống. Không dùng `onErrorReturn(true)`, và không giả mạo đây là "ACL không tồn tại".
7. `@SuppressWarnings("deprecation")` chỉ che cảnh báo compile cho ví dụ **đúng baseline 6.5**. Khi nâng Spring Security 7.x, xem API `authorize(...)`/`AuthorizationResult` mới và cập nhật test; không copy interface signature cũ sang bản đã thay đổi contract.

### Vì sao không tự `subscribe()`?

Sai:

```java
// Anti-pattern: callback thay đổi biến sau khi quyết định đã trả.
AtomicBoolean allowed = new AtomicBoolean(false);
permissions.hasReadPermission(username, id)
        .subscribe(allowed::set);
return Mono.just(new AuthorizationDecision(allowed.get()));
```

Kết quả ở thời điểm `allowed.get()` thường vẫn là false; nếu callback đến sau còn có data race/rủi ro mất context. Có thể một test nhỏ "trông như hoạt động" do timing, nhưng không đúng về kiến trúc. Đúng là **trả một `Mono` được compose**, để Spring Security chờ quyết định của publisher.

### Vì sao không dùng `block()`?

Sai:

```java
// Anti-pattern: blocking trong authorization của WebFlux
boolean granted = permissions.hasReadPermission(username, id).block();
return Mono.just(new AuthorizationDecision(granted));
```

Trên Reactor Netty event loop, `block()` có thể bị Reactor cấm hoặc làm nghẽn thread. Nếu dữ liệu nằm trong JDBC/LDAP SDK chỉ hỗ trợ blocking, hãy đánh giá chuyển driver hoặc cô lập blocking có giới hạn trên `Schedulers.boundedElastic()`; đừng bao `Mono.just(blockingCall())` rồi gọi đó là reactive.

## 5. Gắn manager vào SecurityWebFilterChain

**`src/main/java/example/reactiveauthz/SecurityConfiguration.java`**:

```java
package example.reactiveauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            DocumentReadAuthorizationManager documentAuthorizationManager) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/documents/{id}")
                            .access(documentAuthorizationManager)
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

- `GET /public/ping` cho anonymous.
- `GET /documents/{id}` được chuyển cho custom reactive authorization manager.
- `anyExchange().denyAll()` từ chối các đường/method khác **chứ không tự mở mọi request**.
- HTTP Basic dùng để minh họa authentication; production phải bật TLS/HTTPS. Basic truyền credential mỗi request, Base64 không phải mã hóa bảo mật.
- `formLogin` được tắt để client API nhận HTTP Basic challenge ổn định, thay vì redirect tới HTML login.
- CSRF **không bị tắt**, nhưng demo chỉ định nghĩa GET. Nếu thêm POST/PUT/DELETE với browser cookies, phải đánh giá CSRF, không lấy việc dùng R2DBC làm lý do vô hiệu hóa bảo vệ.
- Danh tính `alice` và `bob` là **fixture local**, không được giữ credential demo trong production. UserDetails chứa `ROLE_READER` nhưng quyền đọc từng document vẫn do bảng ACL quyết định.

### Rule order và HTTP status

Matcher được xét theo thứ tự khai báo trong chain. Rule catch-all `anyExchange().denyAll()` phải đứng **cuối cùng**. Nếu thêm `pathMatchers("/documents/**").permitAll()` **trước** rule ACL, mọi document có thể bị mở công khai và custom manager không được gọi cho request đó.

Với HTTP Basic:

| Tình huống | Kỳ vọng | Lý do |
| --- | --- | --- |
| `GET /public/ping` anonymous | 200 | Public |
| `GET /documents/100` anonymous | Thường 401 | Chưa xác thực; Basic entry point |
| `GET /documents/100` Alice | 200 | Đúng role và có ACL |
| `GET /documents/200` Alice | 403 | Đã login, không có ACL |
| `GET /documents/200` Bob | 200 | Có ACL |
| `GET /documents/abc` Alice | 403 theo policy mẫu | ID invalid được manager deny |
| `GET /documents/999` Alice | 403 | Không có ACL cho ID |
| `POST /documents/100` Alice | Không được truy cập (thường 403; CSRF có thể chặn trước) | Catch-all deny; method không được mở |

Lưu ý status chính xác cho anonymous tùy authentication entry point/configuration. Với Basic đơn thuần trong demo, phản hồi 401 là hợp lý. Nếu chuyển sang form login hoặc custom entry point, anonymous có thể nhận redirect 302 thay vì 401.

## 6. Controller: chỉ lấy dữ liệu mà principal có quyền

Một lỗi phổ biến là filter cho phép xong thì controller query document **chỉ bằng ID**, bỏ qua điều kiện owner/tenant. Nếu ACL bị thay đổi giữa hai thao tác, hoặc controller được gọi từ một đường nghiệp vụ khác, điều này có thể gây IDOR (Insecure Direct Object Reference).

**`src/main/java/example/reactiveauthz/DocumentController.java`**:

```java
package example.reactiveauthz;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentPermissionRepository documents;

    public DocumentController(DocumentPermissionRepository documents) {
        this.documents = documents;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/documents/{id}")
    public Mono<ResponseEntity<String>> read(@PathVariable long id) {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .flatMap(username ->
                        documents.readVisibleDocument(username, id))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Ở đây, `ReactiveSecurityContextHolder.getContext()` đọc context từ **Reactor Context của subscription hiện tại**, không dùng `SecurityContextHolder.getContext()` kiểu thread-local của Servlet. Repository chỉ trả nội dung nếu query `JOIN document_permissions` có row tương ứng username + document ID. Nếu quyền vừa bị thu hồi trước query thứ hai, API không trả body.

`.defaultIfEmpty(ResponseEntity.notFound().build())` thể hiện việc controller không tìm thấy bản ghi **còn nhìn thấy được**. Tuy nhiên, với rule ACL ở filter, caller không có quyền thường bị chặn trước và nhận **403**, không đi tới controller. Nếu sản phẩm muốn luôn trả 404 để che sự tồn tại của tài nguyên, cần thiết kế exception mapping/policy có kiểm chứng; không mặc định 404 trên mọi ACL miss.

### Vì sao kiểm tra hai lần vẫn có ý nghĩa?

- **HTTP filter**: chặn request không có quyền trước khi vào controller.
- **Repository/service**: chỉ lấy data người dùng thực sự được phép xem; phòng thủ nếu gọi từ luồng khác, hoặc quyền thay đổi sau kiểm tra filter.

Nếu dữ liệu nhạy cảm hơn, nên tập trung authorization ở service được tái sử dụng và đồng thời bảo đảm mọi truy vấn có điều kiện tenant/owner; cân nhắc reactive method security hoặc policy engine riêng. Không chỉ dựa vào URL regex để bảo vệ object-level data.

## 7. Kiểm thử tích hợp qua WebTestClient

Demo dùng H2 in-memory; `schema.sql` và `data.sql` được Spring Boot khởi tạo ở startup. Test gọi HTTP Basic, kiểm tra status và body. Vì test sử dụng R2DBC thực (H2 trong RAM), đây không chỉ là mock manager trả true/false.

**`src/test/java/example/reactiveauthz/DocumentAuthorizationTest.java`**:

```java
package example.reactiveauthz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DocumentAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentPermissionRepository permissions;

    @Test
    void repositoryReturnsTrueWhenAclExists() {
        StepVerifier.create(permissions.hasReadPermission("alice", 100L))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void repositoryReturnsFalseWhenAclIsMissing() {
        StepVerifier.create(permissions.hasReadPermission("alice", 200L))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentRequestIsUnauthorized() {
        client.get().uri("/documents/100")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceReadsDocument100() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Plan A: internal");
    }

    @Test
    void aliceCannotReadDocument200() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobReadsDocument200() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth("bob", "demo-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Plan B: private");
    }

    @Test
    void invalidIdIsDenied() {
        client.get().uri("/documents/not-a-number")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void missingAclIsDenied() {
        client.get().uri("/documents/999")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth("alice", "incorrect"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy từ thư mục dự án có Gradle Wrapper:

```bash
./gradlew test --tests example.reactiveauthz.DocumentAuthorizationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.reactiveauthz.DocumentAuthorizationTest
```

**Kỳ vọng:** mười bài test PASS với project/demo và phiên bản tương thích. Kết quả trên là **kỳ vọng** khi chạy code, không phải log của một lần chạy test đã được thực hiện trong workspace. Test dùng password fixture local; không dùng lại ở production.

**Cần test bổ sung cho production**:

- ACL bị thu hồi trong khi request đang xử lý.
- Database timeout/unavailable: request **không được cấp quyền**, telemetry có lỗi DB (không cố giả mạo là account không tồn tại).
- Nhiều request đồng thời, giới hạn connection pool và p95/p99 latency.
- User có role nhưng không có ACL, có ACL nhưng thiếu role.
- Multi-tenant: username giống nhau ở tenant khác không được đọc nhầm data.
- Retry, connection exhaustion, cache invalidation và audit khi policy thay đổi.

## 8. Cân nhắc hiệu năng và không chặn luồng

### 8.1. Một request có thể tạo nhiều I/O

Trong demo, khi GET `/documents/{id}` thành công:

1. HTTP Basic xác thực user in-memory (trong ứng dụng thật có thể gọi IdP hoặc database).
2. `DocumentReadAuthorizationManager` truy vấn ACL qua R2DBC.
3. Controller truy vấn body kèm ACL điều kiện lần nữa.

Vậy một request đọc document ở demo thường có **hai SQL queries** sau khi xác thực. Điều này giúp dễ quan sát và defense-in-depth, nhưng production cần đo chi phí. Có thể tối ưu thành một query nghiệp vụ kiểm tra ACL và trả dữ liệu, rồi chỉ sử dụng manager ở các endpoint nơi filter check thật sự cần thiết; hoặc chia sẻ một kết quả đã được xác minh qua context exchange có kiểm soát. Mọi tối ưu phải bảo đảm không tạo lỗ hổng TOCTOU/IDOR.

### 8.2. Non-blocking không có nghĩa vô hạn năng lực

Dù R2DBC không chặn event loop, database vẫn có số connection và CPU hữu hạn. Nếu 10.000 requests đồng thời mỗi request mở 1-2 queries, pool/DB có thể bị quá tải.

Cần quan tâm:

- **Connection pool**: giới hạn số connection, acquisition timeout, idle timeout; dùng R2DBC pool phù hợp với driver.
- **Timeout**: giới hạn thời gian truy vấn/authorization; khi timeout, không cấp quyền.
- **Backpressure và concurrency**: giới hạn số request hay công việc query đồng thời, không tạo `flatMap` vô hạn trên tập lớn.
- **Index**: query ACL theo `username`, `document_id`, `permission` phải có index phù hợp dựa trên query plan; primary key ở demo là `(document_id, username, permission)`, index riêng theo username có thể hữu ích tùy tải.
- **Metrics**: authz decision counts theo kết quả và reason *không có dữ liệu nhạy cảm*; query duration, connection wait time, timeout/error.
- **Retry**: không retry mù quáng mọi lỗi DB; có thể tăng áp lực lên database khi đang mất kết nối.
- **Caching**: cân nhắc TTL và invalidation khi quyền bị thu hồi; quyết định quyền cũ có thể gây lộ dữ liệu nếu cache stale.
- **Tenant isolation**: thêm tenant_id vào ràng buộc ACL và query (lấy tenant từ nguồn đã xác thực), không tin `X-Tenant-Id` caller gửi mà không xác minh.
- **Phân quyền tầng service**: không để endpoint gRPC, message consumer, batch job hoặc background process bỏ qua HTTP filter rồi lấy dữ liệu không kiểm tra ACL.

### 8.3. Không trộn blocking library vào reactive pipeline

Đoạn anti-pattern:

```java
return authentication.map(auth -> {
    // JDBC/JPA: blocking và thực thi ngay trong map.
    boolean allowed = jdbcPermissions.canRead(auth.getName(), documentId);
    return new AuthorizationDecision(allowed);
});
```

Nếu bạn chưa thể thay JDBC bằng R2DBC, giải pháp chuyển tiếp có thể là:

```java
return authentication.flatMap(auth ->
        Mono.fromCallable(() ->
                jdbcPermissions.canRead(auth.getName(), documentId))
            .subscribeOn(Schedulers.boundedElastic())
            .map(AuthorizationDecision::new));
```

Đây là **đoạn minh họa**: cần import `Mono`, `Schedulers`, `AuthorizationDecision` và đảm bảo thiếu principal vẫn deny, timeout/error handling đúng. `boundedElastic` cho phép cách ly **blocking code** khỏi event loop với tài nguyên hữu hạn, chứ không biến JDBC thành non-blocking R2DBC. Khi có thể, ưu tiên driver R2DBC và giữ query không chặn end-to-end.

### 8.4. Không đưa I/O nặng vào `map`

Khi tác vụ trả `Mono<Boolean>`, dùng `flatMap` để nối publisher:

```java
// Đúng: trả Mono<AuthorizationDecision>.
return authentication
        .map(Authentication::getName)
        .flatMap(name -> permissions.hasReadPermission(name, documentId))
        .map(AuthorizationDecision::new);
```

Nếu dùng `map(name -> permissions.hasReadPermission(...))`, bạn có `Mono<Mono<Boolean>>` và filter không thể tự nhận được `AuthorizationDecision` như mong muốn. Đồng thời phải bảo vệ trường hợp anonymous/thiếu role/thiếu ACL bằng `defaultIfEmpty(deny)` như manager đầy đủ phía trên.

## 9. Các quyết định authorization khó và cách xử lý

### 9.1. Missing resource: 403 hay 404?

Ở demo, manager tra ACL trước khi controller đọc document. Nếu document 999 không tồn tại **hoặc tồn tại nhưng Alice không có ACL**, cả hai có thể nhận 403. Cách này giảm việc tiết lộ tài nguyên tồn tại hay không, nhưng không phải API contract của mọi sản phẩm.

Một số hệ thống muốn 404 cho cả "không tồn tại" lẫn "không được xem" để chống enumeration. Khi đó cần thiết kế behavior tại service/exception handler và kiểm thử rõ ràng; không chỉ đổi `AuthorizationDecision(false)` thành true rồi để controller 404 mà vô tình mở dữ liệu.

### 9.2. Ai là chủ thể của quyết định?

`authentication.getName()` trong demo là username. Trong production, username có thể đổi và có thể trùng theo tenant; nên dùng ID bất biến và tenant đã được xác minh, ví dụ một claim đã validate bởi JWT decoder hoặc ID từ identity provider. Không dùng `?user=bob` hay `X-User: bob` từ client làm principal.

### 9.3. Quyết định thiếu dữ liệu khác lỗi hạ tầng

| Kết quả từ repository | Mono | Ý nghĩa | Xử lý đúng |
| --- | --- | --- | --- |
| ACL match | `Mono.just(true)` | Có quyền | `AuthorizationDecision(true)` |
| ACL miss | `Mono.just(false)` | Không có quyền | `AuthorizationDecision(false)` |
| Principal không có | `Mono.empty()` ở auth source | Chưa xác thực | Manager explicit deny hoặc entry point 401 |
| Database unreachable | `Mono.error(...)` | Không biết kết quả | **Không cấp quyền**, ghi nhận lỗi vận hành |
| Authenticated user thiếu role | Bị `filter` loại | Role không đủ | Explicit deny và status 403 |

Không log toàn bộ Authentication/token/authorization header hoặc body document trong log lỗi. Audit chỉ cần principal ID đã được xử lý theo chính sách, resource ID, decision, elapsed time, correlation ID và error class an toàn.

### 9.4. "Permit nếu database lỗi" là lỗi nghiêm trọng

Sai:

```java
permissions.hasReadPermission(username, documentId)
    .onErrorReturn(true) // KHÔNG được dùng cho kiểm tra quyền!
```

Khi database mất kết nối, câu lệnh trên cấp quyền cho mọi user vượt qua kiểm tra role. Tương tự, đừng gán `Mono.empty()` hoặc exception thành `AuthorizationDecision(true)` để "ứng dụng vẫn hoạt động". Tính sẵn sàng quan trọng nhưng **không được đánh đổi bằng tiết lộ dữ liệu**.

### 9.5. Reactive HTTP authorization và method security

Nếu mọi đường vào dữ liệu đều qua HTTP filter có custom manager thì việc kiểm tra ở URL là lớp đầu. Nhưng service có thể được gọi từ scheduled job, WebSocket, message consumer hoặc RPC; cần policy ở tầng service/data.

Spring Security cũng hỗ trợ `@EnableReactiveMethodSecurity` với `@PreAuthorize` trên phương thức trả `Mono`/`Flux`. Một custom bean trong expression có thể trả `Mono<Boolean>` cho rule. Tuy nhiên method security là phạm vi khác; nếu chọn dùng, phải đảm bảo context reactor được truyền đúng, không tách subscription hoặc gọi `block()`.

Bài học này tập trung **quyền HTTP với `ReactiveAuthorizationManager<AuthorizationContext>`**, không ép mọi hệ thống chuyển sang method security.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Chỉ viết `hasRole("READER")` cho mọi document | User đọc được tài nguyên không thuộc quyền | Tra ACL theo principal + resource ID |
| Dùng JDBC/JPA trực tiếp trong WebFilter | Chặn event loop | R2DBC hoặc cô lập blocking có kiểm soát |
| Gọi `.block()` trong manager | Chặn luồng hoặc bị Reactor cấm | Trả pipeline `Mono` hoàn chỉnh |
| Gọi `.subscribe()` rồi đọc biến được set sau | Race condition, mất context, kết quả sai | Compose qua `flatMap`/`map` |
| Dùng `Mono.just(blockingCall())` | Blocking đã xảy ra trước khi tạo publisher | Chuyển nguồn dữ liệu hoặc `fromCallable + boundedElastic` khi bắt buộc |
| Sử dụng `map` cho hàm trả `Mono` | Tạo `Mono<Mono<T>>` | Dùng `flatMap` |
| Auth Mono rỗng trở thành abstain | Có thể bị hiểu khác deny rõ ràng | `defaultIfEmpty(new AuthorizationDecision(false))` |
| Tin `Authentication.isAuthenticated()` với anonymous | Anonymous token có thể mang cờ authenticated | Loại `AnonymousAuthenticationToken` / dùng trust resolver |
| Không validate path ID | Lỗi NumberFormatException -> 500 | Parse có kiểm tra, deny hoặc 400 theo API contract |
| Nối id/username vào SQL | SQL injection | Dùng `DatabaseClient.bind(...)` |
| Không dùng tenant trong ACL | Có thể đọc chéo tenant | Thêm tenant verified vào query/index |
| Lỗi DB fallback permit | Mở quyền khi mất DB | Fail closed, telemetry/error handling rõ ràng |
| Nuốt mọi lỗi DB thành ACL miss | Che sự cố, khó vận hành | Phân loại lỗi không có quyền và lỗi hạ tầng |
| Cache quyền vĩnh viễn | User vẫn xem được sau khi bị thu hồi quyền | TTL, invalidation, policy version hoặc query live |
| Controller đọc bằng ID sau khi filter cho phép | TOCTOU/IDOR nếu gọi từ đường khác hoặc quyền bị đổi | Query data có điều kiện ACL/tenant |
| Đặt `anyExchange().permitAll()` quá sớm | Bỏ qua mọi rule phía sau | Rule cụ thể trước, deny/authenticated cuối |
| Test chỉ dùng `mockUser`, không gọi DB | Không phát hiện lỗi mapping/ACL query | Integration test WebTestClient + R2DBC thật |
| Dùng HTTP Basic không có TLS | Credential bị lộ | Luôn HTTPS trên mạng thật |
| Dùng API Spring Security 7.x trong project 6.5 | Signature không khớp compiler | Pin phiên bản, đọc Javadoc và migration guide |

## 11. Bài tập thực hành

1. Thêm cột `tenant_id` vào `documents` và `document_permissions`. Viết test hai user có cùng username nhưng khác tenant **không** truy cập được tài liệu của nhau.
2. Tạo permission `EDIT` riêng cho `PUT /documents/{id}`, giữ CSRF nếu client dùng cookie; không dùng GET để cập nhật dữ liệu.
3. Bổ sung user `charlie` có `ROLE_READER` nhưng không có ACL. Kiểm tra login thành công, GET document bị 403.
4. Bổ sung user có ACL ở database nhưng không có `ROLE_READER`: phân quyền vẫn deny. Đừng lấy ACL làm cách vượt qua role bắt buộc.
5. Đo thời gian của hai SQL queries mỗi request, thử tối ưu để chỉ đọc body bằng query có ACL và so sánh bảo đảm security.
6. Giả lập database timeout trong `DocumentPermissionRepository`; chứng minh kết quả không trở thành 200 và hệ thống ghi nhận lỗi đúng.
7. Thu hồi ACL của Alice khi service đang xử lý; kiểm tra query body có ACL vẫn không trả dữ liệu nếu quyền đã bị xóa.
8. Nâng bản demo từ Spring Security 6.5 lên 7.x, đối chiếu `ReactiveAuthorizationManager.authorize(...)` và `AuthorizationResult` rồi cập nhật manager và các test theo Javadoc bản đang dùng.
9. Nếu application cũng có WebSocket hoặc message consumer, xác định nơi đặt rule ở tầng service để các đường không đi qua HTTP filter vẫn được kiểm tra.

**Kết luận:** Phân quyền HTTP theo dữ liệu trong WebFlux không cần chặn luồng. Hãy nhận `Mono<Authentication>` từ Spring Security, lấy biến URL bằng `AuthorizationContext`, tra ACL qua R2DBC, rồi trả `Mono<AuthorizationDecision>` được compose đầy đủ. Thiếu user/role/ACL phải **deny**, lỗi database không bao giờ biến thành permit; với dữ liệu nhạy cảm, áp dụng kiểm soát thêm tại service/repository và kiểm thử thật.

## Tài liệu chính thức

- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — AuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security 6.5 — AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Boot 3.x — SQL Databases và R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework — R2DBC và DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
