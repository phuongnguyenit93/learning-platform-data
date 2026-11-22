# Phối hợp phân quyền HTTP với phân quyền phương thức trong Spring Security WebFlux

## Mục tiêu bài học

Sau bài học này, bạn có thể:

1. Phân biệt **phân quyền tại HTTP/WebFilter** và **phân quyền trên lời gọi phương thức của Spring bean**; hiểu tại sao cùng một thao tác nghiệp vụ có thể cần hai lớp bảo vệ.
2. Cấu hình `ServerHttpSecurity.authorizeExchange(...)` cùng `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` và `@PreAuthorize` cho các phương thức trả `Mono`/`Flux`.
3. Mô tả cách `Authentication` được truyền qua Reactor Context và tác dụng của `ReactiveSecurityContextHolder` đối với các lời gọi trong và ngoài HTTP request.
4. Kết hợp role, authority và quyền theo từng document bằng hàm kiểm tra `Mono<Boolean>` sử dụng R2DBC, tuyệt đối không gọi `block()` trong WebFlux.
5. Thiết kế chính sách **hai lớp đều phải cho phép** (logical AND), từ chối theo mặc định, tránh tự gọi phương thức (self-invocation) làm bypass AOP.
6. Viết và kiểm thử ví dụ Java 17+ có Spring Boot WebFlux, method security, database H2 R2DBC, `WebTestClient`, `StepVerifier` và phân biệt 401/403/404.
7. Nhận diện rủi ro multi-tenant, TOCTOU, cache quyền, thiếu context và giới hạn của riêng HTTP authorization.

> **Phiên bản tham chiếu:** Spring Boot 3.x, Spring Security 6.5.x, Java 17+. Mã sử dụng API **reactive**: `SecurityWebFilterChain`, `ServerHttpSecurity`, `@EnableReactiveMethodSecurity`, `Mono` và `ReactiveSecurityContextHolder`. Không thay bằng các API Servlet/MVC như `HttpSecurity`, `SecurityFilterChain` hoặc tự dùng `ThreadLocal` khi xử lý luồng Reactor.

## 1. Hai lớp bảo vệ giải quyết hai loại rủi ro

Một ứng dụng có thể áp dụng chính sách ngay khi HTTP request vừa vào hệ thống:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated()
)
```

Quy tắc này xác định URL nào được mở. Nhưng cùng nghiệp vụ đọc dữ liệu còn có thể được gọi từ HTTP endpoint khác, job nội bộ, message consumer hoặc code service khác. Nếu bạn chỉ bảo vệ URL mà quên bảo vệ service, đường gọi khác có thể bỏ qua kiểm tra quyền.

Ngược lại, nếu bạn đặt `@PreAuthorize` ở một service nhưng để HTTP `anyExchange().permitAll()` không có chủ đích, các tài nguyên và endpoint không gọi service đó có thể bị mở. Bảo mật tốt cần xác định **ranh giới riêng** của hai lớp.

| Lớp | Vị trí | Điều kiện điển hình | Chịu trách nhiệm chính |
| --- | --- | --- | --- |
| HTTP authorization | Security WebFilter trước controller | HTTP method, path, có đăng nhập, role phạm vi chức năng | Chặn request không hợp lệ từ biên |
| Method authorization | Spring AOP quanh public method của bean | Role, authority, tham số phương thức, object/tenant, trạng thái nghiệp vụ | Chặn thao tác nghiệp vụ dù được gọi từ đâu |
| Data access guard | Query/service truy cập dữ liệu | Owner/tenant/ACL/row-level policy | Chỉ lấy hoặc sửa bản ghi thực sự được phép |
| Authentication | Trước việc quyết định quyền | HTTP Basic, session, OAuth2/JWT | Xác lập danh tính đáng tin cậy |

**Nếu một HTTP request phải vượt qua cả HTTP rule và method rule, nó chỉ được thực hiện khi cả hai đều cấp quyền.** Lớp này không có tác dụng "mở khóa" lớp kia. Một `permitAll()` ở HTTP không tự bỏ qua `@PreAuthorize`; một phương thức cho phép cũng không vượt qua HTTP `denyAll()`.

### Ví dụ dễ thấy

Giả sử có API:

- `GET /documents/100`: user đã đăng nhập có thể **đến được controller**, nhưng service chỉ cho đọc document nếu có role READER và ACL cho document 100.
- `GET /documents/100/audit`: HTTP yêu cầu `ROLE_AUDITOR`; service còn đòi authority `AUDIT_VIEW`.
- `GET /public/ping`: HTTP công khai và controller không thực hiện nghiệp vụ nhạy cảm.

Một user có `ROLE_AUDITOR` nhưng thiếu `AUDIT_VIEW` sẽ vượt qua lớp HTTP và bị service từ chối. Một user chỉ có `ROLE_READER` sẽ bị HTTP chặn ngay khi gọi URL audit, bất kể có thử gọi URL nào khác.

### Ma trận quyết định

| HTTP rule | Method rule | Kết quả khi endpoint gọi method đó |
| --- | --- | --- |
| Cho phép | Cho phép | Controller/service tiếp tục, còn các điều kiện dữ liệu/kinh doanh khác |
| Cho phép | Từ chối | Method không thực hiện công việc bảo vệ; HTTP thường trả 403 nếu đã xác thực |
| Từ chối | Cho phép theo giả định | HTTP chặn trước; method không được gọi từ request này |
| Từ chối | Từ chối | HTTP chặn trước; không dựa vào lần kiểm tra thứ hai |
| Không yêu cầu xác thực | Method yêu cầu identity | Method vẫn chặn nếu không có context hợp lệ |
| Request không qua HTTP (job/message) | Method cho phép hoặc từ chối | Chỉ method/data guard còn cơ hội kiểm soát; context phải được cấp có chủ đích |

Không gọi đây là hai bước luôn xảy ra tuần tự đối với **mọi request**: nếu HTTP chặn sớm, method không được gọi; endpoint không có method security sẽ không có bước kiểm tra thứ hai.

## 2. Cơ chế reactive method security và Reactor Context

Để bật phân quyền phương thức, thêm vào Spring configuration:

```java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
```

Spring Security đăng ký các **AOP interceptors** cho annotation, ví dụ `@PreAuthorize`, `@PostAuthorize`. Khi một bean được gọi qua Spring proxy, interceptor có thể kiểm tra quyền trước hoặc sau thao tác, dùng authentication từ **Reactor Context**.

Điểm mấu chốt:

- Phương thức được bảo vệ trong chương trình reactive thường phải trả `org.reactivestreams.Publisher`, ví dụ `Mono<T>` hoặc `Flux<T>`. Điều này giúp authorization dùng đúng context trong subscription.
- `ReactiveSecurityContextHolder` đọc SecurityContext trong Reactor Context, không dựa vào `SecurityContextHolder.getContext()` kiểu Servlet thread-local.
- `@PreAuthorize` kiểm tra **trước** công việc bảo vệ; khi từ chối, Spring Security phát lỗi `AccessDeniedException` trong publisher, method không được thực thi theo hợp đồng.
- `@PostAuthorize` kiểm tra **sau** khi có kết quả, trước khi trả kết quả cho caller. Với thao tác ghi side effect, nó **không** thay thế pre-authorization vì side effect có thể đã xảy ra.
- `@EnableWebFluxSecurity` không đồng nghĩa tự bật method security. Phải bật `@EnableReactiveMethodSecurity` cho phương thức mong muốn.
- Đừng dùng `@EnableMethodSecurity` theo ví dụ Servlet một cách máy móc khi app chủ đích dùng reactive method support.

### Đường truyền Authentication

```text
HTTP request
  |
  +--> Authentication WebFilter (Basic/Session/JWT)
  |       |
  |       v
  |   Reactor Context chứa SecurityContext/Authentication
  |
  +--> AuthorizationWebFilter
  |       |
  |       +--> HTTP matcher / role rule -> pass / deny
  |
  +--> Controller gọi Spring bean service (qua proxy)
          |
          +--> Reactive method security interceptor
          |       |
          |       +--> @PreAuthorize lấy Authentication từ Reactor Context
          |       +--> Kiểm tra role/permission/ACL
          |       +--> Deny -> AccessDeniedException
          |
          +--> Dịch vụ thực thi logic Mono/Flux
                  |
                  +--> Data access có ràng buộc owner/tenant
                  +--> Trả kết quả, có thể có @PostAuthorize bổ sung
```

Khi chuyển thread qua `publishOn(...)` hoặc `subscribeOn(...)` mà vẫn **giữ nguyên chuỗi Reactor**, Reactor Context thường được truyền theo subscription. Ngược lại, tự gọi `subscribe()`, tạo publisher ngoài request không có context, hoặc chuyển sang executor không quản lý context có thể khiến method security thấy anonymous/no authentication. Không nên "sửa" bằng cách nhét một Authentication giả vào global variable.

### Dùng @PreAuthorize như thế nào?

```java
// Các method trong Spring bean, minh họa cách khai báo:
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() {
    return Mono.just("restricted");
}

@PreAuthorize("hasAuthority('AUDIT_VIEW')")
public Flux<String> auditItems() {
    return Flux.just("entry-1", "entry-2");
}
```

`hasRole("ADMIN")` trong SpEL tương ứng authority `ROLE_ADMIN` (prefix mặc định), còn `hasAuthority("AUDIT_VIEW")` đối chiếu chuỗi chính xác, không tự thêm prefix. Quy ước lưu role/permission cần thống nhất giữa identity provider, user database, JWT authorities mapping và policy.

## 3. Chính sách mẫu: HTTP route + quyền document ở service

Ta xây dựng project demo:

- Dùng HTTP Basic để test dễ, không cần giao diện HTML hoặc form login.
- HTTP `GET /documents/{id}` yêu cầu **authenticated** nhưng không tự quyết định mọi ACL.
- Service `readDocument(id)` có `@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")`. Bean `documentPolicy` trả `Mono<Boolean>` sau khi kiểm tra role và truy vấn quyền trong H2 R2DBC.
- Truy vấn lấy nội dung vẫn có điều kiện ACL để tránh lỗi khi quyền thay đổi sau bước method check.
- URL `GET /documents/{id}/audit` yêu cầu `ROLE_AUDITOR` ở HTTP; method `auditDocument(id)` lại yêu cầu `AUDIT_VIEW`.
- Mọi URL/method khác bị `denyAll()`, chỉ `GET /public/ping` được mở công khai.

### Dữ liệu mong đợi

| Tài khoản | Authorities | ACL đọc document | Kết quả |
| --- | --- | --- | --- |
| `alice` | `ROLE_READER` | READ document 100 | Đọc 100 được; 200 bị từ chối |
| `bob` | `ROLE_READER` | READ document 200 | Đọc 200 được; 100 bị từ chối |
| `charlie` | `ROLE_VIEWER` | Có hàng READ document 100 | Vẫn bị từ chối vì thiếu `ROLE_READER` |
| `auditor` | `ROLE_AUDITOR` | Không cần ACL của demo | Vượt HTTP audit nhưng bị method từ chối do thiếu `AUDIT_VIEW` |
| `chief` | `ROLE_AUDITOR`, `AUDIT_VIEW` | Không cần ACL của demo | Vào được endpoint audit |
| Anonymous | Không có Authentication hợp lệ | Không | 401 với HTTP Basic ở URL được bảo vệ |

Đây là các **fixture local**, không phải role và mật khẩu có thể đem dùng ở production. Chính sách cụ thể tùy tổ chức; bài học minh họa cách ghép **điều kiện AND qua nhiều lớp**.

## 4. Chuẩn bị project Spring Boot WebFlux + R2DBC

### 4.1. Dependencies

Trong project Gradle đã có Spring Boot plugin, dependency management và cấu hình Java 17+, cần các dependency sau:

**`build.gradle`** (phần `dependencies`):

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

Không thêm `spring-boot-starter-web` cho ví dụ này: khi MVC và WebFlux có cùng classpath, Spring Boot thường chọn Servlet, khiến các API security/config không còn đúng kiểu runtime.

Cấu trúc source:

```text
src/main/
  java/example/layered/
    LayeredSecurityApplication.java
    ReactiveSecurityConfiguration.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  resources/
    application.yml
    schema.sql
    data.sql
src/test/
  java/example/layered/
    LayeredSecurityIntegrationTest.java
```

### 4.2. Cấu hình H2 R2DBC

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: layered-webflux-security
  r2dbc:
    url: "r2dbc:h2:mem:///layereddb?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
      schema-locations: "classpath:schema.sql"
      data-locations: "classpath:data.sql"

server:
  port: 8080
```

- `r2dbc:h2:...` là URL cho driver R2DBC, **khác** `jdbc:h2:...`.
- `spring.sql.init.mode=always` yêu cầu chạy schema/data fixture khi app khởi động. Chỉ dùng cho bài thực hành hoặc môi trường test kiểm soát.
- H2 in-memory không thay thế migration và backup của PostgreSQL production.
- `DB_CLOSE_DELAY=-1` giúp giữ DB in-memory khi connection tạm thời được đóng.

### 4.3. Schema và dữ liệu mẫu

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT PRIMARY KEY,
    body VARCHAR(1000) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_permissions (
    document_id BIGINT NOT NULL,
    username VARCHAR(120) NOT NULL,
    permission VARCHAR(20) NOT NULL,
    PRIMARY KEY (document_id, username, permission),
    CONSTRAINT fk_doc_permission
        FOREIGN KEY (document_id) REFERENCES documents(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_doc_permission_username
    ON document_permissions(username);
```

**`src/main/resources/data.sql`**:

```sql
INSERT INTO documents(id, body)
VALUES
    (100, 'Internal plan A'),
    (200, 'Private plan B');

INSERT INTO document_permissions(document_id, username, permission)
VALUES
    (100, 'alice', 'READ'),
    (200, 'bob', 'READ'),
    (100, 'charlie', 'READ');
```

Vai trò `ROLE_READER` được khai báo trong nguồn người dùng của Security Configuration; **không** nằm trong bảng ACL demo. Lý do: role trả lời user có được phép sử dụng chức năng đọc nói chung hay không; ACL trả lời user đó có được phép đọc **bản ghi cụ thể** hay không.

Schema production cần user ID bất biến, tenant ID, index phù hợp, foreign key tới user/tenant và migration versioned. Username trong bảng demo chỉ để dễ đọc; không phải lựa chọn tốt nhất khi người dùng có thể đổi tên.

### 4.4. Main class

**`src/main/java/example/layered/LayeredSecurityApplication.java`**:

```java
package example.layered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayeredSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayeredSecurityApplication.class, args);
    }
}
```

## 5. Cấu hình cùng lúc HTTP và reactive method security

**`src/main/java/example/layered/ReactiveSecurityConfiguration.java`**:

```java
package example.layered;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
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
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails charlie = User.withUsername("charlie")
                .password(encoder.encode("local-test-password"))
                .roles("VIEWER")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("local-test-password"))
                .roles("AUDITOR")
                .build();

        UserDetails chief = User.withUsername("chief")
                .password(encoder.encode("local-test-password"))
                .authorities("ROLE_AUDITOR", "AUDIT_VIEW")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, charlie, auditor, chief);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/documents/{id}/audit")
                            .hasRole("AUDITOR")
                        .pathMatchers(HttpMethod.GET, "/documents/{id}")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Đây là nơi hai lớp security được kích hoạt:**

1. `@EnableWebFluxSecurity` tạo hệ thống security filter cho HTTP.
2. `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` đăng ký Spring AOP method interceptors, bao gồm `@PreAuthorize`. Spring Boot Security starter không tự đảm bảo method annotations sẽ chạy nếu thiếu annotation này.
3. HTTP Basic kiểm tra username/password; các tài khoản mẫu dùng `PasswordEncoder` sinh hash BCrypt có prefix thuật toán, không dùng `{noop}`.
4. Path matcher cho `/documents/{id}/audit` đứng trước matcher đọc document để rõ ràng về mức độ đặc biệt; `anyExchange().denyAll()` là rule cuối.
5. Trên `GET /documents/{id}`, HTTP chỉ đòi đã xác thực; **kiểm tra role và ACL nằm ở service**. Đây là một lựa chọn có chủ ý, không phải lỗ hổng, vì mọi đường lấy document phải gọi service đã được bảo vệ và repository còn lọc dữ liệu.
6. Trên URL audit, HTTP yêu cầu `ROLE_AUDITOR`, method còn yêu cầu `AUDIT_VIEW`. Không có cơ chế "một trong hai" ở đây.
7. Các mẫu username/password chỉ phục vụ localhost và integration test; production dùng nguồn user được quản lý riêng.
8. CSRF mặc định không bị tắt. Ví dụ chỉ cho GET; với POST/PUT/DELETE và cookie-based auth, thiết kế CSRF phải được kiểm tra riêng.

### Cảnh báo khi bổ sung rule

Nếu bạn đặt `.anyExchange().permitAll()` trước các matcher cần bảo vệ, rule sau có thể không còn được thực hiện. Nếu bạn khai báo nhiều `SecurityWebFilterChain`, Spring Security chọn **một** chain theo matcher và thứ tự, nên phải kiểm tra chain nào nhận URL. Method security độc lập với HTTP matcher nhưng không tự bảo vệ endpoint không gọi method có annotation.

## 6. Repository reactive đọc ACL và dữ liệu có điều kiện

**`src/main/java/example/layered/DocumentRepository.java`**:

```java
package example.layered;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentRepository {

    private final DatabaseClient database;

    public DocumentRepository(DatabaseClient database) {
        this.database = database;
    }

    public Mono<Boolean> hasReadPermission(String username, long id) {
        return database.sql("""
                    SELECT 1 AS allowed
                      FROM document_permissions
                     WHERE document_id = :documentId
                       AND username = :username
                       AND permission = 'READ'
                    """)
                .bind("documentId", id)
                .bind("username", username)
                .fetch()
                .first()
                .hasElement();
    }

    public Mono<String> findVisibleBody(String username, long id) {
        return database.sql("""
                    SELECT d.body
                      FROM documents d
                     WHERE d.id = :documentId
                       AND EXISTS (
                           SELECT 1
                             FROM document_permissions p
                            WHERE p.document_id = d.id
                              AND p.username = :username
                              AND p.permission = 'READ'
                       )
                    """)
                .bind("documentId", id)
                .bind("username", username)
                .map((row, metadata) -> row.get("body", String.class))
                .one();
    }
}
```

**Vì sao có hai query?**

- `hasReadPermission` kiểm tra ACL ở **method authorization**. `.fetch().first().hasElement()` trả `Mono<Boolean>` luôn phát `true/false` khi query thành công. Nếu không có hàng thì `false`; nếu DB bị lỗi thì publisher báo `onError`.
- `findVisibleBody` chỉ trả nội dung document nếu truy vấn dữ liệu **vẫn** thỏa ACL. Lớp kiểm soát bổ sung tránh việc controller hoặc các caller khác đọc nhầm body khi quyền thay đổi hoặc không qua đúng code path.
- Query sử dụng `.bind(...)` để gắn tham số, không nối username/id vào SQL; phòng tránh SQL injection.
- Không có `block()` hoặc `subscribe()`. Spring WebFlux và method interceptor sẽ subscribe các publisher cần thiết trong request.
- Khi performance quan trọng, có thể tối ưu số query, nhưng không được bỏ điều kiện owner/tenant/ACL trong data access chỉ vì HTTP đã kiểm tra một lần.

**TOCTOU:** quyền có thể bị thu hồi trong khoảng thời gian giữa query authorization và query trả body. Query `findVisibleBody` bảo đảm mỗi lần đọc dữ liệu lại có điều kiện ACL tại thời điểm query đó. Nếu nghiệp vụ đòi snapshot hoặc atomicity mạnh hơn, cần transaction isolation và kiểm thử concurrency, không chỉ trông chờ hai lần đọc thông thường.

## 7. Bean kiểm tra quyền trả Mono<Boolean>

Spring Security 6.5 hỗ trợ một expression gọi bean, trong đó bean method có thể trả **Boolean hoặc Mono<Boolean>** cho `@PreAuthorize`. Cách này giúp tách SQL/logic phức tạp khỏi SpEL và vẫn không chặn luồng.

**`src/main/java/example/layered/DocumentPolicy.java`**:

```java
package example.layered;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(Authentication authentication, Long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || id == null || id <= 0) {
            return Mono.just(false);
        }

        boolean readerRole = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_READER".equals(authority.getAuthority()));
        if (!readerRole) {
            return Mono.just(false);
        }

        return repository.hasReadPermission(authentication.getName(), id);
    }
}
```

**Cách đọc logic:**

1. `Authentication` phải tồn tại, hợp lệ và không phải `AnonymousAuthenticationToken`. Không chỉ tin `isAuthenticated()`: anonymous token trong Spring Security có thể được đánh dấu authenticated theo cách xây dựng đối tượng.
2. ID phải có ý nghĩa; ID rỗng/không dương bị từ chối.
3. Tầng chức năng yêu cầu authority `ROLE_READER`.
4. Tầng dữ liệu tra ACL theo username + id, trả `Mono<Boolean>`. Spring Security method authorization có thể chờ quyết định này mà không blocking event loop.
5. Không có ACL -> `Mono.just(false)` thông qua `hasElement()`, bảo đảm **deny rõ ràng**.
6. SQL timeout/lỗi connection -> `Mono.error(...)` được propagate, **không** biến thành `true` hoặc âm thầm cấp quyền.

### Không được làm thế này

```java
// Anti-pattern: chặn luồng xử lý WebFlux
boolean allowed = repository
        .hasReadPermission(authentication.getName(), id)
        .block();

// Anti-pattern: database lỗi thì cấp quyền
return repository.hasReadPermission(authentication.getName(), id)
        .onErrorReturn(true);

// Anti-pattern: thay đổi biến async rồi trả kết quả ngay
AtomicBoolean allowed = new AtomicBoolean(false);
repository.hasReadPermission(authentication.getName(), id)
        .subscribe(allowed::set);
return Mono.just(allowed.get());
```

Đoạn trên chỉ minh họa **các lỗi**, không phải chương trình độc lập. Dùng `Mono.just(blockingCall())` cũng không khiến thư viện blocking trở thành non-blocking: lời gọi đã thực thi trước khi tạo `Mono`.

Nếu ứng dụng chưa thể thay JDBC, có thể cô lập blocking I/O qua `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` với giới hạn tài nguyên, timeout và kiểm thử tải; đây là giải pháp chuyển tiếp, **không tương đương** driver R2DBC.

### Mono.empty() có nghĩa gì trong method authorization?

Theo tài liệu Spring Security reactive method security, bean authorization có thể trả `Mono.empty()` để **abstain** (không đưa ra quyết định). Đối với ACL "không thấy quyền", chúng ta muốn **deny** nên trả `Mono.just(false)`. Đừng vô tình trả `Mono.empty()` trên đường nhánh người dùng không có ACL rồi tưởng rằng đó luôn là "từ chối".

## 8. Service được bảo vệ bằng @PreAuthorize

**`src/main/java/example/layered/DocumentService.java`**:

```java
package example.layered;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public Mono<String> readDocument(Long id) {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName())
                .flatMap(username ->
                        repository.findVisibleBody(username, id));
    }

    @PreAuthorize("hasAuthority('AUDIT_VIEW')")
    public Mono<String> auditDocument(Long id) {
        return Mono.just("Audit document " + id);
    }
}
```

### Vì sao dùng #p0?

`#p0` là **tham số thứ nhất** trong biểu thức Spring Method Security; tránh phụ thuộc việc compiler có giữ tên tham số Java bằng `-parameters` hay không. Bạn cũng có thể dùng `#id` khi parameter names được phát hiện, chẳng hạn dùng `@P("id")` hoặc build đã cấu hình parameter metadata. Nếu đổi tên tham số mà expression bị lệch, policy có thể trả sai hoặc không hoạt động; đặt test cho biến dùng trong authorization.

### Tại sao readDocument có hai lần kiểm tra ACL?

Ở service, `@PreAuthorize` gọi `DocumentPolicy.canRead(authentication,id)` trước khi thực thi nội dung method. Nếu pass, `readDocument` đọc username bằng `ReactiveSecurityContextHolder` và truy vấn repository kèm ACL. Hai truy vấn là tradeoff giữa **defense-in-depth** và hiệu năng; với hệ thống thật, có thể hợp nhất kiểm tra + dữ liệu trong một truy vấn kiểm soát ở service, đồng thời vẫn giữ role/entry checks rõ ràng.

### Vì sao auditDocument chỉ có một annotation?

HTTP rule `hasRole("AUDITOR")` và method rule `hasAuthority("AUDIT_VIEW")` là hai lớp AND. Không cần nhét cả hai điều kiện vào một annotation khi bạn muốn minh họa ranh giới. Tuy nhiên, nếu `auditDocument` cũng được gọi từ batch/message nơi **không có HTTP filter**, role `ROLE_AUDITOR` không được kiểm tra bởi method hiện tại. Với một policy nghiệp vụ bắt buộc cả hai quyền dù caller tới từ đâu, nên viết ngay tại method:

```java
// Phương án chặt hơn cho service có nhiều entry points:
@PreAuthorize("hasRole('AUDITOR') and hasAuthority('AUDIT_VIEW')")
public Mono<String> auditDocument(Long id) {
    return Mono.just("Audit document " + id);
}
```

Đây là **biến thể thay thế** method `auditDocument` ở file trên, không đặt hai method cùng chữ ký. Với bài học, đoạn cấu hình chính cố ý chỉ yêu cầu `AUDIT_VIEW` ở service để thể hiện hai lớp có nhiệm vụ khác nhau; khi production, **đặt điều kiện nghiệp vụ bắt buộc ở lớp service** và dùng HTTP filter như lớp sàng lọc trước.

### Về @PostAuthorize

`@PostAuthorize` kiểm tra quyền trên **kết quả**. Ví dụ khái niệm:

```java
// Mẫu minh họa khi dùng kiểu Document có thuộc tính owner:
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Document> findDocument(Long id) {
    return repository.findById(id);
}
```

Đây là đoạn **minh họa**; class `Document` và repository method `findById` chưa được định nghĩa trong app demo. Trong reactive method security, `@PostAuthorize` có thể kiểm tra phần tử được phát từ publisher trước khi caller nhận; nhưng thao tác đọc đã diễn ra, và side effect trước đó có thể đã xảy ra. Với lệnh chuyển tiền/xóa tài liệu/cập nhật database, **không dùng chỉ @PostAuthorize để ngăn hành động nguy hiểm**. Ưu tiên `@PreAuthorize` + điều kiện trong query/transaction.

## 9. Controller WebFlux gọi service qua Spring proxy

**`src/main/java/example/layered/DocumentController.java`**:

```java
package example.layered;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/documents/{id}")
    public Mono<ResponseEntity<String>> read(@PathVariable Long id) {
        return documents.readDocument(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping("/documents/{id}/audit")
    public Mono<String> audit(@PathVariable Long id) {
        return documents.auditDocument(id);
    }
}
```

Constructor nhận `DocumentService` do Spring quản lý, tức lời gọi `documents.readDocument(id)` đi **qua proxy method security**. Tránh viết `new DocumentService(...)` trong controller vì sẽ bỏ qua bean lifecycle và interceptor. `read` không tự so sánh authority ở controller, cũng không nhận username từ query string để tự tin dùng làm principal.

Nếu `readDocument` phát `AccessDeniedException`, WebFlux security exception translation có thể trả 403 cho người dùng **đã xác thực**. Nếu anonymous vào URL yêu cầu authentication, HTTP Basic entry point thường trả 401. Nếu query trả `Mono.empty()` vì dữ liệu đã biến mất sau khi pre-check pass, controller có thể trả 404. Đừng viết `onErrorResume(AccessDeniedException.class, ... return ResponseEntity.ok(...))` vì đó là cấp dữ liệu khi bị từ chối.

### Quy tắc của một request điển hình

```text
GET /documents/100 - Basic alice/password
    -> HTTP authenticated()                  PASS
    -> method @PreAuthorize
          ROLE_READER                       PASS
          ACL Alice đọc document 100        PASS
    -> repository query kèm ACL             PASS
    -> 200 "Internal plan A"

GET /documents/200 - Basic alice/password
    -> HTTP authenticated()                  PASS
    -> method @PreAuthorize
          ROLE_READER                       PASS
          ACL Alice đọc document 200        DENY
    -> controller không nhận body
    -> 403

GET /documents/100/audit - Basic auditor/password
    -> HTTP hasRole("AUDITOR")               PASS
    -> method hasAuthority("AUDIT_VIEW")     DENY
    -> 403

GET /documents/100/audit - Basic alice/password
    -> HTTP hasRole("AUDITOR")               DENY
    -> method không chạy
    -> 403
```

Thứ tự HTTP trước method là **thứ tự trên request HTTP này**. Khi service được gọi ngoài HTTP, nó không có bước HTTP gate và phải áp dụng quy tắc phù hợp ngay trên method/data.

## 10. Kiểm thử HTTP và phương thức độc lập

Dự án thêm `spring-security-test` và `reactor-test` để kiểm tra từng lớp. Một test chỉ mock role ở HTTP có thể bỏ qua bug trong SQL ACL. Bài này dùng H2 R2DBC thật trong test để kiểm chứng cả chính sách và dữ liệu.

**`src/test/java/example/layered/LayeredSecurityIntegrationTest.java`**:

```java
package example.layered;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LayeredSecurityIntegrationTest {

    @Autowired WebTestClient client;
    @Autowired DocumentService documents;
    @Autowired DocumentRepository repository;

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadDocument() {
        client.get().uri("/documents/100").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadHerDocument() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Internal plan A");
    }

    @Test
    void aliceCannotReadBobsDocument() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobCanReadHisDocument() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth(
                        "bob", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Private plan B");
    }

    @Test
    void aclWithoutReaderRoleIsNotEnough() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "charlie", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void httpAuditorWithoutMethodPermissionIsDenied() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "auditor", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerIsDeniedAuditAtHttpLayer() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorWithAdditionalAuthorityCanReadAudit() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "chief", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Audit document 100");
    }

    @Test
    void wrongPasswordCannotReadDocument() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "alice", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void repositoryReturnsExplicitAclDecision() {
        StepVerifier.create(repository.hasReadPermission("alice", 100))
                .expectNext(true).verifyComplete();
        StepVerifier.create(repository.hasReadPermission("alice", 200))
                .expectNext(false).verifyComplete();
    }

    @Test
    void serviceDirectCallSucceedsWithMatchingReactorContext() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(documents.readDocument(100L)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectNext("Internal plan A")
                .verifyComplete();
    }

    @Test
    void serviceDirectCallIsDeniedWithoutAcl() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(documents.readDocument(200L)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void serviceDirectCallWithoutPrincipalIsDenied() {
        StepVerifier.create(documents.readDocument(100L))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

Lệnh chạy từ project có Gradle Wrapper:

```bash
./gradlew test --tests example.layered.LayeredSecurityIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.layered.LayeredSecurityIntegrationTest
```

**Kết quả kỳ vọng:** 14 test PASS trên một project được cấu hình đúng các file và dependency tương thích với Spring Boot 3.x/Spring Security 6.5. Đây là **kết quả dự kiến**, không phải nhật ký một lần chạy test thực tế trong môi trường của bạn.

### Kiểm thử đã chứng minh điều gì?

| Nhóm test | Điều được kiểm chứng |
| --- | --- |
| Public và anonymous | HTTP filter cho phép public; yêu cầu authenticated chặn anonymous |
| Alice/Bob/Charlie | HTTP authenticated chưa đủ; method còn kiểm tra ROLE_READER và ACL thật |
| Auditor/chief | HTTP role gate + method authority gate là hai điều kiện độc lập |
| Sai mật khẩu | Authentication thất bại trước khi vào service |
| `repositoryReturnsExplicitAclDecision` | R2DBC query trả `true/false` với dữ liệu có hoặc không có quyền |
| Direct service call có Reactor Context | Spring proxy method security áp dụng cả khi không qua controller |
| Direct service call thiếu quyền | Method từ chối bằng `AccessDeniedException`, không cần HTTP status |
| Direct service call không context | Không tự tạo danh tính, từ chối |

**Không kết luận rằng chỉ test WebTestClient là đủ.** Test service trực tiếp quan trọng vì nó có thể phát hiện annotation không hoạt động do thiếu `@EnableReactiveMethodSecurity`, gọi không qua proxy, hoặc mất Reactor Context.

### Về HTTP status khi không được phép

Trong demo dùng HTTP Basic:

- Request anonymous vào URL authenticated thường nhận **401** với challenge HTTP Basic.
- Request đã xác thực nhưng bị HTTP hoặc method deny thường nhận **403**.
- Khi service/controller chủ ý trả `Mono.empty()` sau khi đã được cho phép, controller có thể trả **404**.
- Khi database lỗi, phải có response lỗi hệ thống phù hợp (thường 5xx), **không tự biến lỗi SQL thành 200 hoặc "không có quyền" mà mất telemetry**.

Nếu đổi sang form login, anonymous thường được **redirect đến trang đăng nhập** thay vì 401. Nếu dùng JWT resource server, token invalid/expired có thể nhận 401 tùy entry point. Không hardcode một bảng status làm API contract bất biến khi thay authentication mechanism.

## 11. Lỗi AOP hay khiến @PreAuthorize bị bỏ qua

Reactive method security sử dụng Spring AOP proxy. Vì vậy phải hiểu **lời gọi qua proxy**.

### 11.1. Self-invocation

```java
@Service
public class BadExampleService {

    public Mono<String> outer() {
        // Anti-pattern: gọi nội bộ qua this, có thể bypass proxy.
        return this.sensitive();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> sensitive() {
        return Mono.just("secret");
    }
}
```

Đây là lớp **anti-pattern độc lập để giải thích**, không được thêm vào demo chính. Khi `outer()` gọi `this.sensitive()` trong cùng instance, lời gọi thường không đi qua proxy, nên interceptor của `sensitive()` không chạy. Nếu `outer()` được mở, đây là lỗ hổng. Giải pháp: tách `sensitive()` sang bean riêng rồi gọi bean đã được inject, hoặc đặt bảo vệ đúng trên entry method; viết test gọi chính đường code đó.

### 11.2. Khởi tạo service bằng new

```java
// Anti-pattern: bean không đi qua Spring context/proxy.
DocumentService service = new DocumentService(repository);
service.readDocument(100L);
```

Đoạn code minh họa này có thể **bỏ qua AOP**, khác với `@Autowired DocumentService` hoặc constructor injection của Spring. Không tự tạo bean được bảo vệ bằng `new` rồi kỳ vọng annotation thực thi.

### 11.3. Private, final và annotation ở sai chỗ

Một proxy Spring AOP không thể chặn mọi lời gọi tùy ý:

- Private methods không thể được gọi từ bên ngoài qua proxy thông thường.
- Final class/method có thể cản trở proxy kiểu subclass (CGLIB) intercept; với JDK interface proxy có các điều kiện khác.
- Annotation ở method không phải điểm vào thực tế có thể không được chạy.
- Khi thay đổi class/interface proxies, phải test đường bean wiring thật.
- Gọi method từ code chạy **trong constructor/@PostConstruct** trước khi proxy được hoàn thiện không phù hợp để dựa vào method security.

**Nguyên tắc:** đặt annotation trên public service method, gọi qua bean Spring, bảo vệ mọi entry point có thể truy cập business operation và kiểm thử direct service call.

### 11.4. @PreAuthorize chưa tự bật

Bạn có thể viết `@PreAuthorize` đúng mà ứng dụng vẫn không có interceptor vì quên `@EnableReactiveMethodSecurity`. Bật annotation trên một `@Configuration` và dùng test fail-case để xác nhận. Đừng suy ra "chạy được HTTP Basic" nghĩa là method security cũng đã bật.

## 12. Context của non-HTTP caller: scheduler, message và WebSocket

HTTP Basic/session/JWT filter thường tạo Authentication trong Reactor Context khi request qua WebFlux. Nhưng scheduled task hay message consumer không tự có danh tính user HTTP.

Ví dụ gọi service trong test bằng một Authentication giả lập **có chủ đích**:

```java
Authentication principal =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_READER")));

Mono<String> result = documents.readDocument(100L)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(principal));
```

Đây là fragment cần các import đã có trong test, **không phải cách client được phép tự chọn danh tính**. Chỉ test infrastructure hoặc một trusted component mới có quyền cấp Authentication như vậy. Trong production, background worker nên dùng service identity hoặc một policy riêng đã được audit; không gán ROLE_ADMIN giả để "cho job chạy".

Nếu bạn gọi `documents.readDocument(100L)` trong job mà không có context:

- Method security có thể từ chối (là điều mong muốn nếu policy đòi end-user).
- Hoặc bạn phải thiết kế API/service riêng với policy dành cho hệ thống, không bỏ annotation vô điều kiện.
- Không gọi `subscribe()` trong service rồi mong Reactor Context của HTTP tự được truyền sang một subscription hoàn toàn độc lập.

Nếu mở WebSocket, RSocket hay consumer, kiểm soát thêm entry point, mapping identity, cross-tenant permissions và method security; HTTP authorization chỉ áp dụng cho HTTP request mà nó thực sự xử lý.

## 13. Hiệu năng, transaction và tính nhất quán

### 13.1. Có thể tốn nhiều truy vấn mỗi request

Ví dụ GET document hợp lệ thường thực hiện:

1. HTTP Basic xác thực user in-memory (production có thể thêm IO).
2. Method `DocumentPolicy.canRead` truy vấn ACL bằng R2DBC.
3. Repository `findVisibleBody` truy vấn document kèm điều kiện ACL.

Hai query dữ liệu bảo vệ tốt nhưng có chi phí. Nếu lưu lượng lớn:

- Đo p50/p95/p99 của authorization + DB, đồng thời đo pool acquisition wait.
- Thiết kế query có index đúng cho `document_id, username, permission`; dùng query plan trên PostgreSQL thực.
- Có thể gộp ACL và đọc body thành một query ở service nếu policy vẫn rõ ràng và có kiểm soát object-level.
- Với dữ liệu nhạy cảm, không loại bỏ rào chắn owner/tenant ở SQL chỉ để giảm một query.
- Nếu cache ACL, cần TTL/invalidation khi thu hồi quyền; cache stale có thể tiếp tục cấp quyền sai.
- Giới hạn connection pool, query timeout, concurrency và retry. Reactive non-blocking **không tạo ra vô hạn DB capacity**.

### 13.2. Database failure phải fail closed

Khi quyền do database quyết định:

- Không có ACL row là **deny**.
- SQL timeout, mất kết nối, pool hết connection là **không thể xác minh quyền**. Request không được cấp phép; lỗi phải được log/monitor theo cách an toàn.
- Không dùng `onErrorReturn(true)`, `onErrorResume(ex -> Mono.just(true))` hoặc bất kỳ fallback nào cấp quyền vì hệ thống "cần sẵn sàng".
- Nếu muốn trả 503 thay vì 500 khi authorization DB unavailable, map exception hạ tầng sang lỗi service unavailable **mà không trả nội dung bảo vệ**. Tránh coi tất cả lỗi là một 403 rồi mất khả năng vận hành.
- Không log raw password, Authorization header, JWT, password hash, cookie/session hoặc toàn bộ nội dung document trong error trace.

### 13.3. TOCTOU: quyền đổi giữa hai thời điểm

*Time-of-check to time-of-use* xảy ra khi ACL còn hợp lệ trong method check nhưng bị thu hồi trước query body. Query thứ hai có ACL là một cách giảm nguy cơ. Với thao tác ghi, ví dụ chuyển tiền/xóa document, cần kiểm soát quyền cùng transaction hoặc dùng SQL `UPDATE ... WHERE id=:id AND tenant_id=:tenantId AND EXISTS (...)` để điều kiện được kiểm tra tại thời điểm ghi.

Không giả định transaction reactive được tạo bằng `@Transactional` trên phương thức không trả publisher rồi tự `subscribe()`. Khi dùng R2DBC, cần reactive transaction manager và giữ nguyên subscription context; thiết kế isolation theo nghiệp vụ và test race conditions thực.

### 13.4. Thay đổi role giữa request và service

HTTP authorization lấy Authentication của request; role trong Authentication có thể được nạp từ token/session trước đó. Nếu admin vừa thu hồi một role, session/JWT cũ có thể giữ authorities đã cũ. Method security dùng **cùng Authentication** sẽ không tự phát hiện role vừa đổi trừ khi được thiết kế tra lại hoặc token/session bị thu hồi.

Do đó:

- Định nghĩa độ trễ thu hồi quyền chấp nhận được.
- Cân nhắc short-lived tokens, forced re-authentication, cache invalidation, query live hoặc version-based permission model.
- Tách static role vào Authentication và dynamic resource ACL vào database; kiểm thử chính sách revoke.
- Không tin header `X-User`/`X-Tenant` do client tự đặt làm principal, và không lấy tenant ID chưa xác minh để query ACL.

## 14. Chiến lược kiểm thử để tránh bảo vệ "giả"

Một bộ test đầy đủ nên kiểm tra **cả hai chiều**:

| Kịch bản | HTTP test | Service test |
| --- | --- | --- |
| Anonymous vào URL protected | 401/redirect login | Thiếu Reactor Context phải từ chối |
| Đăng nhập nhưng thiếu role HTTP | 403 trước controller | Không có kết luận gì về method trừ khi gọi riêng |
| Qua HTTP nhưng thiếu authority method | 403 | Direct call từ role tương ứng bị `AccessDeniedException` |
| Role đủ nhưng thiếu ACL | 403 | Direct call bị từ chối |
| Có ACL nhưng thiếu role | 403 | Policy từ chối |
| Có role và ACL | 200, body đúng | Publisher phát đúng dữ liệu |
| Sai ID/tenant | 400/403/404 theo policy | Không trả dữ liệu ngoài quyền |
| Database lỗi | Không trả dữ liệu được bảo vệ | Publisher báo lỗi; không cấp quyền |
| Self-invocation | Có thể không phát hiện bằng controller test đơn lẻ | Viết test cho đúng đường gọi nội bộ |
| Cache đã stale sau revoke | Đo hành vi qua nhiều request | Kiểm tra thời gian/invalidation của policy |

`@WithMockUser`/`mockUser()` rất hữu ích khi kiểm tra role và method authorization, nhưng **không kiểm chứng quá trình nhận password/token thật**. Với các chức năng nhạy cảm, cần thêm integration test xác thực thực, các trường hợp expired/invalid token và role mapping.

### 401, 403 và 404 không thay nhau được

- **401 Unauthorized:** authentication thất bại/chưa được cung cấp khi dùng Basic hoặc Bearer entry point phù hợp.
- **403 Forbidden:** đã được xác thực nhưng authorization không đạt ở HTTP hoặc method layer. CSRF filter cũng có thể tạo 403 trên unsafe method thiếu token — cần phân biệt nguyên nhân.
- **404 Not Found:** resource không tồn tại hoặc policy chủ ý ẩn sự tồn tại. Không tự chuyển 403 thành 404 mà không có thiết kế nhất quán.

Trong WebFlux reactive, lỗi `AccessDeniedException` được Web Security exception handling chuyển thành HTTP response khi phát sinh trong HTTP pipeline. Nếu gọi service trực tiếp không qua HTTP, caller nhận lỗi từ publisher và **không có HTTP status** để kiểm tra.

## 15. Các lỗi thường gặp

| Lỗi triển khai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ có `authorizeExchange`, bỏ method security | Service có thể bị gọi qua job/endpoint khác mà không kiểm tra quyền | Bật `@EnableReactiveMethodSecurity`, bảo vệ public service methods |
| Chỉ có `@PreAuthorize` nhưng mở quá rộng HTTP | Endpoint khác không gọi service vẫn lộ | Dùng rule cụ thể và `anyExchange().denyAll()` |
| Dùng nhầm `@EnableMethodSecurity` kiểu Servlet | Configuration/semantics không khớp reactive method flow | Dùng `@EnableReactiveMethodSecurity` |
| Service trả plain object, tự block Mono | Có thể làm mất reactive context hoặc chặn event loop | Trả `Mono`/`Flux` trong method được bảo vệ |
| `this.protectedMethod()` | Lời gọi không qua proxy nên annotation không chạy | Tách bean, gọi qua Spring proxy |
| `new DocumentService(...)` | Không có AOP proxy của Spring | Inject bean Spring-managed |
| Phương thức private/final hoặc proxy sai | Interceptor không chạy như dự kiến | Public method, kiểm tra proxy và test |
| Truyền username từ request param vào ACL | Người dùng có thể giả mạo principal | Lấy từ Authentication đáng tin cậy |
| Chỉ `hasRole("READER")` cho mọi tài liệu | User đọc nhầm tài liệu không thuộc quyền | Thêm kiểm tra object-level ACL |
| Có ACL nhưng không role / có role nhưng không ACL | Logic OR vô tình cấp quyền | Thiết kế điều kiện AND, test mọi tổ hợp |
| `Mono.empty()` khi muốn deny | Có thể được hiểu là abstain trong method-security expression | Trả `Mono.just(false)` |
| `onErrorReturn(true)` khi DB lỗi | Data leak khi mất kết nối | Fail closed và telemetry rõ |
| `block()` hay `subscribe()` thủ công | Event loop blocking, race/mất Reactor Context | Compose publisher đúng |
| Dùng `map` với hàm trả `Mono` | Tạo `Mono<Mono<T>>` | Dùng `flatMap` |
| `anyExchange().permitAll()` đặt sai vị trí | Bỏ qua HTTP restriction | Đặt rule cụ thể trước, catch-all cuối |
| Caching quyền không invalidation | Người bị thu hồi quyền vẫn truy cập | TTL/invalidation/live check |
| Bỏ tenant predicate ở SQL | Cross-tenant data leakage | Verified tenant context + constraint trong query |
| Test chỉ assert 200 | Không phát hiện lỗ hổng | Test deny 401/403, direct service, revoke, missing context |
| Dùng `@PostAuthorize` bảo vệ lệnh ghi | Side effect có thể đã xảy ra trước deny | Kiểm tra trước và enforce ở transaction/query |

## 16. Bài tập mở rộng

1. Thêm user `dave` có `ROLE_READER` nhưng chưa có ACL; chứng minh HTTP cho qua, method từ chối. Sau đó thêm một ACL và kiểm tra kết quả chuyển thành 200.
2. Đặt `@PreAuthorize("hasRole('AUDITOR') and hasAuthority('AUDIT_VIEW')")` ở service audit; viết test direct service chứng minh thiếu từng điều kiện đều bị từ chối ngay cả khi không qua HTTP.
3. Tạo một `DocumentAdminService` riêng có method `@PreAuthorize("hasRole('ADMIN')")`; viết một `public` method trong service khác gọi nó qua bean proxy và một anti-pattern tự gọi nội bộ. So sánh kết quả.
4. Thử bỏ `@EnableReactiveMethodSecurity` trong một nhánh test: xác nhận các direct service tests thất bại, chứng minh kiểm thử phát hiện thiếu interceptor.
5. Đổi principal từ username sang ID/tenant verified; thêm `tenant_id` vào ACL và document table, ngăn Alice của tenant A đọc document tenant B.
6. Dùng R2DBC PostgreSQL và migration có version; đo latency của method ACL, connection pool acquisition, timeout và so sánh hai query với một query có predicate.
7. Thêm test database unavailable và chứng minh endpoint không trả 200 dù role trong Authentication hợp lệ.
8. Thêm `Flux<Document>` liệt kê nhiều tài liệu: áp policy bằng điều kiện ngay trong SQL thay vì tải tất cả rồi `filter` quá muộn trên stream.
9. Thiết kế đường message consumer gọi document service: xác định service identity/đối tượng được phép, gắn Reactor Context chỉ từ nguồn tin cậy và test deny nếu không có context.
10. Nâng phiên bản Spring Security; đối chiếu tài liệu `@EnableReactiveMethodSecurity`, `@PreAuthorize`, reactive `Mono<Boolean>` bean, request matchers và các thay đổi deprecation trước khi chỉnh source.

## Tổng kết

- **HTTP authorization** quyết định request nào được tới controller: path, method, authenticated, role/authority.
- **Reactive method authorization** bảo vệ lời gọi nghiệp vụ dù được khởi tạo từ controller, service khác hoặc message/job; nó dựa trên Spring AOP và Reactor Context.
- Với cùng một HTTP request, **HTTP phải cho phép và method phải cho phép**; không có cơ chế layer này tự mở quyền của layer kia.
- `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` bật proxy/interceptors; `@PreAuthorize` có thể gọi bean trả `Mono<Boolean>` để kiểm tra ACL không blocking.
- **Không dùng** `block()`, manual `subscribe()`, fallback permit trên lỗi DB, tự gọi protected method qua `this`, hay tin username/tenant do client tự khai.
- Dữ liệu nhạy cảm nên có thêm điều kiện kiểm soát trong query/transaction, bởi HTTP và method check không thay thế toàn bộ data-access security.
- Test cả HTTP và direct service bằng `WebTestClient`/`StepVerifier`; sau khi quyền bị thu hồi, xác nhận dữ liệu cũ không còn truy cập được.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Framework — R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Boot — SQL Databases and R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Security — Reactive Method Security migration/latest](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
