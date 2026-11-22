# Kiểm tra chủ sở hữu bằng dữ liệu reactive ở tầng dịch vụ

## Mục tiêu học tập

Bài học thuộc nhóm **Phân quyền phương thức** của **Spring Security - reactive**. Một ứng dụng có thể đã xác thực người dùng và yêu cầu `ROLE_USER`, nhưng **vẫn phải kiểm tra người đó có sở hữu tài nguyên cụ thể hay không**. Nếu chỉ kiểm tra "đã đăng nhập" ở HTTP route rồi đọc dữ liệu bằng ID bất kỳ, hệ thống có thể mắc lỗi **IDOR/BOLA** (Insecure Direct Object Reference / Broken Object Level Authorization).

Mục tiêu:

1. Phân biệt **xác thực**, **quyền vai trò**, **quyền sở hữu tài nguyên** và **phạm vi tenant**.
2. Đọc principal từ `ReactiveSecurityContextHolder` thay vì tin `ownerId` do client gửi.
3. Thực hiện **lookup dữ liệu reactive** qua Spring Data R2DBC/`Mono` trong phép kiểm tra quyền, không gọi `block()`.
4. Kích hoạt `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` và đặt `@PreAuthorize` trên **service bean**.
5. Sử dụng bean kiểm tra quyền trả `Mono<Boolean>` trong SpEL method security, xử lý đúng thiếu user, không tìm thấy record và lỗi database.
6. Tránh TOCTOU bằng truy vấn **được giới hạn ngay trong điều kiện WHERE theo chủ sở hữu**, đặc biệt khi thực hiện update/delete.
7. Dựng ví dụ chạy được với **Java 17+, Spring Boot 3.3.13, Spring WebFlux, Spring Security, Spring Data R2DBC và H2**.
8. Kiểm thử cả truy cập từ HTTP và **gọi trực tiếp phương thức service** bằng `WebTestClient`/`StepVerifier`.
9. Nhận diện vấn đề Spring AOP self-invocation, scheduler, Reactor Context, cross-tenant, cache quyền, ghi audit và response 401/403/404.

**Trọng tâm:** Quyền sở hữu phải được xác minh bằng dữ liệu **do server kiểm soát**, không phải bằng URL, header, cookie hoặc thông tin JSON mà client có thể sửa.

## 1. Bài toán: user hợp lệ không có nghĩa được xem mọi record

Giả sử hệ thống lưu hai tài liệu:

| ID | owner_id trong database | Tiêu đề |
| --- | --- | --- |
| 101 | alice | Tài liệu riêng của Alice |
| 202 | bob | Tài liệu riêng của Bob |

API có route `GET /api/documents/{id}`. HTTP security viết:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/documents/**").authenticated()
    .anyExchange().denyAll());
```

Rule này chỉ đảm bảo request có Authentication hợp lệ. Nếu controller gọi thẳng:

```java
// SAI: chỉ dựa vào id mà client nhập.
@GetMapping("/api/documents/{id}")
public Mono<Document> getDocument(@PathVariable Long id) {
    return documentRepository.findById(id);
}
```

thì Alice (đã đăng nhập) có thể thử `/api/documents/202` và nhìn thấy tài liệu của Bob. Đây là lỗi object-level authorization dù endpoint yêu cầu xác thực.

Cần thêm một điều kiện:

```text
ALLOW = authenticated(actor)
    AND actor has permission "document:read"
    AND resource exists
    AND resource.ownerId == trustedActorId
    AND resource.tenantId == trustedTenantId (nếu đa tenant)
```

Trong ví dụ đơn tenant, `trustedActorId` là username lấy từ Authentication đã được Spring Security xác minh. Trong sản phẩm thực, ưu tiên **immutable user ID** và **tenant ID** từ token/identity provider đã kiểm tra chữ ký hoặc dữ liệu server-side; không nên dùng username thay cho stable identity nếu username có thể đổi.

## 2. Vì sao phải kiểm tra ở tầng dịch vụ?

Nếu chỉ kiểm tra owner ở HTTP filter/controller, một phương thức business service có thể được gọi từ:

- WebFlux REST controller;
- RSocket handler hoặc GraphQL resolver;
- message consumer;
- scheduled job/batch;
- test hoặc một luồng tích hợp nội bộ;
- một service khác trong ứng dụng.

Không phải đường gọi nào cũng đi qua `AuthorizationWebFilter` của HTTP. **Method security** giúp policy được áp dụng **tại boundary của service bean**, nơi tài nguyên được truy cập.

```text
HTTP request
   |
   +-- WebFlux SecurityWebFilterChain
   |     +-- Authentication (Basic/Form/Bearer)
   |     +-- HTTP authorization: authenticated()
   |
   v
DocumentController
   |
   v
Spring AOP proxy của DocumentService
   |
   +-- @PreAuthorize("@documentPermission.canRead(#p0)")
   |      |
   |      +-- ReactiveSecurityContextHolder -> Authentication
   |      +-- Reactive DocumentRepository
   |              -> SELECT theo id và owner đã xác minh
   |      +-- Mono<Boolean> -> ALLOW / DENY
   |
   v
DocumentService.read(id)
   |
   +-- SELECT theo id và owner một lần nữa
   |
   v
DocumentView -> response
```

Đường `@PreAuthorize` là **bảo vệ trước khi chạy thân phương thức**. Ở ví dụ này, service vẫn truy vấn có điều kiện owner sau khi qua AOP để tránh phụ thuộc vào kết quả lookup trước đó nếu dữ liệu thay đổi trong khoảng giữa (time-of-check to time-of-use).

**Đổi lại, ví dụ thực hiện hai truy vấn SELECT.** Điều đó có chủ ý cho mục tiêu dạy hai lớp bảo vệ. Ứng dụng cần tối ưu có thể chọn mô hình **@PreAuthorize chỉ kiểm tra vai trò** + **truy vấn dữ liệu scope theo owner trực tiếp trong service** để giảm một round trip; xem mục 9.

## 3. Reactor Context: lấy danh tính tin cậy trong service

Trong WebFlux, SecurityContext được truyền theo **Reactor Context**. Một pipeline có thể chuyển thread; vì vậy đừng dựa vào Servlet-style `SecurityContextHolder.getContext()`/`ThreadLocal` trong service reactive.

```java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Điều trên lấy username từ Authentication của subscriber hiện hành, do Spring Security tạo sau khi xác thực. Nó không gọi database hoặc tạo phiên đăng nhập mới.

**Phân biệt các giá trị:**

| Giá trị | Nguồn | Dùng để cấp quyền? |
| --- | --- | --- |
| `authentication.getName()` | Cơ chế authentication đã xác thực | Có thể dùng như actor ID trong demo |
| `authentication.getAuthorities()` | Roles/scopes đã được xác minh/ánh xạ | Có, theo policy |
| `@PathVariable Long id` | Client chọn resource | Chỉ xác định đối tượng cần kiểm tra |
| `?ownerId=alice` | Client tự gửi | Không phải bằng chứng ownership |
| `X-User-ID: alice` | Header client tự gửi | Không dùng làm principal |
| `document.ownerId()` trong DB | Dữ liệu server lưu | Nguồn đối chiếu owner |
| `document.tenantId()` trong DB | Dữ liệu server lưu | Nguồn đối chiếu tenant khi có xác minh membership |

Nếu request không có SecurityContext, `ReactiveSecurityContextHolder.getContext()` có thể trả `Mono.empty()`. Trong policy của bài, trường hợp này phải **DENY**, không được “không có context tức là public”.

Cần loại bỏ anonymous authentication. `AnonymousAuthenticationToken` có thể báo `isAuthenticated()==true` theo contract của đối tượng, nhưng không đại diện user đã đăng nhập. Vì vậy không kiểm tra flag này **một mình**.

## 4. Method security trong WebFlux: annotation và bean reactive

### 4.1. Bật method security

Với Spring Security 6.x, cách rõ ràng là:

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Annotation nằm trong package `org.springframework.security.config.annotation.method.configuration`. Nó bật các interceptor method security dựa trên Spring AOP, gồm `@PreAuthorize` và `@PostAuthorize`.

**Ràng buộc cần nhớ:** Trong ứng dụng reactive, phương thức được bảo vệ nên trả `Mono<T>` hoặc `Flux<T>` (một `Publisher`). Spring Security dùng Reactor Context để lấy Authentication. Phương thức đồng bộ trả `T` và cố đọc ThreadLocal là một mô hình khác; đừng ghép nhầm với flow này.

### 4.2. Quy tắc đơn giản

```java
@PreAuthorize("hasRole('READER')")
public Mono<Document> read(Long id) {
    return documents.findById(id);
}
```

Rule trên chỉ kiểm tra role. Người dùng có `ROLE_READER` vẫn có thể đọc tài liệu người khác nếu thân service dùng `findById` không scope.

### 4.3. Kết hợp phép kiểm tra trả Mono<Boolean>

Spring Security reactive hỗ trợ tham chiếu một bean trong SpEL:

```java
@PreAuthorize("@documentPermission.canRead(#p0)")
public Mono<DocumentView> read(Long documentId) {
    // chỉ chạy khi phép kiểm tra canRead cho phép
}
```

- `@documentPermission` là bean có tên `documentPermission`.
- `#p0` là **tham số đầu tiên** của phương thức đang được bảo vệ, ở đây là documentId. Cú pháp này tránh phụ thuộc vào việc build có lưu tên tham số `-parameters` hay không.
- `canRead` có thể trả `Mono<Boolean>`, cho phép gọi repository reactive.
- Manager/interceptor của Spring Security chờ publisher đưa ra kết quả trước khi cho phương thức được thực thi.
- Nếu trả `false`, method security từ chối và phát lỗi phân quyền; trong HTTP pipeline Spring Security thường biến thành 403 đối với user đã xác thực.

**Lưu ý tương thích Spring Security 6.3:** Không nên tùy tiện gộp một biểu thức trả `Mono<Boolean>` và các toán tử SpEL boolean đồng bộ như `hasAuthority(...) && @bean.canRead(...)` trong cùng `@PreAuthorize`, vì có phiên bản gặp vấn đề chuyển đổi kiểu biểu thức. Trong ví dụ, **toàn bộ quyết định role + ownership** nằm trong một bean `Mono<Boolean>`. Khi nâng cấp framework, hãy chạy lại integration tests trên đúng phiên bản, không chỉ dựa vào kiểu code trông hợp lý.

### 4.4. Dùng bean riêng thay vì code quyền trong controller

Đặt phép kiểm tra quyền trong một `@Component`, để:

- Có thể kiểm thử riêng;
- Không phải sao chép logic vào mọi controller;
- Có thể tái sử dụng giữa các service;
- Dễ thay repository và chính sách tenant;
- Có thể đo latency của quyết định, audit và bổ sung rule mới;
- Tránh việc controller đọc dữ liệu trước rồi tự quyết định sau khi dữ liệu đã có nguy cơ bị lộ.

Không biến bean này thành một helper tĩnh sử dụng `.block()`, vì nó sẽ chặn event loop và có nguy cơ mất Reactor Context.

## 5. Thiết kế phép kiểm tra chủ sở hữu bằng Mono

Giả sử `DocumentRepository` có truy vấn:

```java
Mono<Document> findByIdAndOwnerId(Long id, String ownerId);
```

Khi repo trả `Mono<Document>`, dùng `hasElement()` để đổi thành `Mono<Boolean>`:

```java
Mono<Boolean> owned =
    documents.findByIdAndOwnerId(documentId, actorId)
             .hasElement();
```

Đây là một truy vấn reactive: adapter R2DBC lấy dữ liệu bất đồng bộ, không cần `block()`. Trong production, nếu chỉ kiểm tra tồn tại, có thể tối ưu query chỉ trả Boolean hoặc dùng `SELECT EXISTS(...)` / repository derived exists query tùy database.

### Dữ liệu đầu vào nào được kiểm tra?

1. `documentId` hợp lệ theo kiểu/format và có giá trị trong miền tài nguyên.
2. Có Authentication đã xác thực, không phải anonymous.
3. Authentication có authority phù hợp, ví dụ `ROLE_READER`.
4. Server dùng actor ID **từ Authentication**, không lấy từ query/header.
5. Repository kiểm tra record với **cả document ID và owner ID**.
6. Nếu record không tồn tại hoặc không thuộc owner, kết quả là **false**.
7. Nếu DB lỗi, không trả `true`; lỗi phải được xử lý fail-closed và quan sát vận hành.

### Mono<Boolean> khác Mono.empty()

| Tín hiệu từ phép kiểm tra | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `Mono.just(true)` | Có đủ điều kiện cấp quyền | ALLOW |
| `Mono.just(false)` | Không đủ điều kiện | DENY |
| `Mono.empty()` | Không phát kết quả kiểm tra | Tránh abstain ngoài ý muốn; biến trường hợp thiếu context thành false |
| `Mono.error(ex)` | Lỗi lookup/đánh giá policy | Không phát ALLOW; phản hồi lỗi có kiểm soát |

`defaultIfEmpty(false)` chỉ biến **empty** thành false, không nuốt **error**. Đây là lựa chọn phù hợp với fail-closed: DB mất kết nối không được coi là "không có thông tin nên cho qua".

**Không viết:**

```java
// SAI: database lỗi lại cấp quyền truy cập.
return documents.findByIdAndOwnerId(id, userId)
    .hasElement()
    .onErrorReturn(true);
```

Khi policy phụ thuộc vào DB, timeout và circuit-breaker (nếu có) chỉ dùng để bảo vệ tài nguyên và báo lỗi rõ, không tự cấp quyền khi không thể xác minh ownership.

## 6. Ví dụ hoàn chỉnh: Spring Boot WebFlux + Spring Data R2DBC H2

Mẫu sử dụng **Java 17+, Spring Boot 3.3.13**, HTTP Basic để thử nhanh quyền và **database H2 qua R2DBC** cho lookup bất đồng bộ. Method security chặn Alice khi yêu cầu tài liệu của Bob ngay cả nếu controller đã được phép gọi service.

### 6.1. Cấu trúc dự án

```text
reactive-ownership-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/
        OwnershipApplication.java
        Document.java
        DocumentView.java
        DocumentRepository.java
        DocumentPermission.java
        DocumentService.java
        DocumentController.java
      resources/
        application.yml
        schema.sql
        data.sql
    test/
      java/example/
        OwnershipApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'reactive-ownership-demo'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` (MVC/Servlet). `spring-boot-starter-data-r2dbc` cung cấp repository reactive, `r2dbc-h2` là driver R2DBC dùng cho dữ liệu mẫu. Spring Boot BOM chọn phiên bản framework, driver và Reactor tương thích.

### 6.4. application.yml

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  r2dbc:
    url: "r2dbc:h2:mem:///ownerlab?options=DB_CLOSE_DELAY=-1"
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
```

`spring.sql.init` hỗ trợ khởi tạo cả `ConnectionFactory` R2DBC trong Spring Boot. Chế độ `always` và dữ liệu mẫu ở đây **chỉ dành cho demo**; production dùng migration tool/DB thật theo chính sách, không tự chèn user/tài liệu mỗi lần khởi động.

Đối với H2 memory, `DB_CLOSE_DELAY=-1` giúp giữ cơ sở dữ liệu khi không còn connection đang mở trong quá trình lab. Cú pháp R2DBC H2 chứa `?options=...`, không dùng JDBC URL `jdbc:h2:...`.

### 6.5. SQL schema và dữ liệu mẫu

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL
);

CREATE INDEX idx_documents_owner ON documents(owner_id);
```

Tạo `src/main/resources/data.sql`:

```sql
INSERT INTO documents (id, owner_id, title)
VALUES (101, 'alice', 'Alice private');

INSERT INTO documents (id, owner_id, title)
VALUES (202, 'bob', 'Bob private');

INSERT INTO documents (id, owner_id, title)
VALUES (303, 'alice', 'Alice notes');
```

Dữ liệu này là **nguồn được server lưu**. Client không thể trở thành chủ sở hữu chỉ bằng việc thay `owner_id` trong URL. Query ở service phải đối chiếu với identity đã xác thực.

### 6.6. OwnershipApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}read")
                .roles("READER")
                .build();

        UserDetails visitor = User.withUsername("visitor")
                .password("{noop}visit")
                .roles("GUEST")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, visitor);
    }
}
```

Các import phía trên cố ý xuống dòng tại dấu `.` để trình bày dễ đọc; Java cho phép ngắt dòng giữa token theo cú pháp import. Nếu trình định dạng của IDE gộp chúng thành một dòng, ý nghĩa không thay đổi.

**Tại sao chỉ có `authenticated()` ở HTTP?** Để minh họa rõ hai lớp:

- HTTP filter kiểm tra identity phù hợp để vào route.
- Method security tại `DocumentService` mới kiểm tra **ROLE_READER và ownership thực trong DB**.

Tài khoản `visitor` đã authenticated nhưng không có `ROLE_READER` nên bị phương thức service từ chối. Điều này giúp phân biệt "đã đăng nhập" với "có quyền đọc tài liệu".

`{noop}` chỉ phục vụ demo local; production dùng password encoder mạnh, HTTPS và quản lý người dùng phù hợp. HTTP Basic có thể gửi username/password theo từng request; đó là công cụ quan sát nhanh, không phải gợi ý mặc định cho mọi API production.

### 6.7. Document.java

```java
package example;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("documents")
public record Document(
        @Id Long id,
        String ownerId,
        String title) {
}
```

Spring Data R2DBC mapping chuyển `ownerId` sang cột `owner_id` theo quy tắc naming mặc định; nếu dự án có `NamingStrategy` tùy biến, cần giữ mapping/annotation `@Column` nhất quán.

**Không coi record này là DTO công khai.** `ownerId` là metadata phục vụ bảo mật/domain. Ví dụ trả về một `DocumentView` riêng để tránh vô tình lộ field không cần thiết.

### 6.8. DocumentView.java

```java
package example;

public record DocumentView(Long id, String title) {
}
```

Việc tách DTO giúp hạn chế dữ liệu được serialize. Nếu tài liệu có nội dung nhạy cảm, service phải tải **đúng phần dữ liệu đã được cấp quyền** trước khi trả ra.

### 6.9. DocumentRepository.java

```java
package example;

import org.springframework.data.repository.reactive
        .ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndOwnerId(
            Long id, String ownerId);
}
```

Spring Data suy diễn truy vấn theo tên method. Quan trọng nhất: điều kiện WHERE theo **cả id và ownerId**. Nếu không có bản ghi nào thỏa, `Mono` hoàn thành rỗng. Query dùng R2DBC, không gọi `block()` trên Netty event loop.

Với CSDL thật có hàng triệu tài liệu, cần index thích hợp cho truy vấn owner/id và phân tích query plan. Với primary key ID riêng, cơ sở dữ liệu có thể dùng index ID trước rồi kiểm tra owner; lựa chọn index phụ thuộc workload, không tự thêm hàng loạt index theo tên cột mà không đo.

### 6.10. DocumentPermission.java — bean kiểm tra quyền reactive

```java
package example;

import org.springframework.security.authentication
        .AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentPermission")
public class DocumentPermission {

    private final DocumentRepository documents;

    public DocumentPermission(DocumentRepository documents) {
        this.documents = documents;
    }

    public Mono<Boolean> canRead(Long documentId) {
        if (documentId == null || documentId <= 0L) {
            return Mono.just(false);
        }

        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(this::isReader)
            .flatMap(authentication ->
                documents.findByIdAndOwnerId(
                        documentId, authentication.getName())
                    .hasElement())
            .defaultIfEmpty(false);
    }

    private boolean isReader(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return auth.getAuthorities().stream()
                .anyMatch(granted ->
                    "ROLE_READER".equals(
                        granted.getAuthority()));
    }
}
```

**Phân tích từng bước:**

1. Input `documentId` sai/rỗng → `Mono.just(false)`, không truy vấn DB.
2. Lấy Authentication từ **Reactor Context**, không tin `ownerId` client tự gửi.
3. `filter(this::isReader)` từ chối anonymous, token chưa authenticated hoặc người thiếu `ROLE_READER`.
4. Query `findByIdAndOwnerId(id, authentication.getName())` yêu cầu record vừa có ID đúng vừa thuộc actor đã xác thực.
5. `hasElement()` phát true khi tìm được record, false khi repository trả empty.
6. `defaultIfEmpty(false)` xử lý không có context/không có authenticated reader một cách tường minh.
7. Lỗi R2DBC không bị biến thành true. Mặc định nó đi theo error pipeline; request không được cấp quyền trên cơ sở một query lỗi.
8. Không có `subscribe()` tự gọi và không có `block()`: mọi phép đánh giá diễn ra khi có subscriber của chain method security.

Đoạn này minh họa quyền **chỉ đọc tài liệu của mình**. Với quyền supervisor/auditor, hãy thiết kế policy rõ ràng, kiểm tra loại quyền và tenant, rồi viết negative tests cho các ngoại lệ; không tự thêm `|| roleAdmin` ở nhiều nơi thiếu nhất quán.

### 6.11. DocumentService.java — bảo vệ ở boundary dịch vụ

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPermission.canRead(#p0)")
    public Mono<DocumentView> read(Long documentId) {
        // Bảo vệ lớp thứ hai bằng truy vấn scoped,
        // không chuyển sang findById(documentId) toàn cục.
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(auth -> documents.findByIdAndOwnerId(
                        documentId, auth.getName()))
                .map(doc -> new DocumentView(
                        doc.id(), doc.title()))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND)));
    }
}
```

**Vì sao vẫn query theo owner dù @PreAuthorize đã kiểm tra?** Vì owner có thể thay đổi giữa hai bước, hoặc service sau này được sửa để lấy dữ liệu theo cách khác. Truy vấn scoped giúp không trả record nếu owner đã khác khi bước đọc thực tế xảy ra. Nó cũng tránh phụ thuộc chỉ vào một phép kiểm tra trước method.

Đối với hệ thống có business update/delete, **chỉ kiểm tra trước rồi UPDATE WHERE id=?** không đủ chống TOCTOU. Tốt nhất đưa owner/tenant vào điều kiện UPDATE/DELETE ở cùng câu lệnh nguyên tử; xem mục 10.

**Phương thức phải được gọi qua Spring bean proxy** để annotation có hiệu lực. Ở demo, controller inject `DocumentService` nên Spring AOP có cơ hội intercept. Nếu tự gọi `this.read(id)` từ một method khác **trong cùng class**, Spring proxy-based method security có thể bị bypass; đừng coi annotation là bảo vệ mọi lệnh gọi Java nội bộ một cách tự động.

### 6.12. DocumentController.java — controller mỏng

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/api/documents/{id}")
    public Mono<DocumentView> document(
            @PathVariable("id") Long id) {
        return service.read(id);
    }
}
```

Controller chỉ chuyển `id` của client tới service. Nó **không** tự khẳng định người gọi sở hữu ID ấy. Method security ở service sẽ thực hiện lookup thực tế.

### 6.13. Khởi chạy

Yêu cầu **JDK 17+**, Gradle 8.x tương thích Spring Boot 3.3.13 và không cần cài Redis/PostgreSQL vì demo dùng R2DBC H2 memory.

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Boot tải `schema.sql` và `data.sql` khi khởi động. Nếu DB initializer lỗi, cần kiểm tra R2DBC URL/driver và scripts; không bỏ initialization rồi cho rằng dữ liệu mẫu đã sẵn sàng.

### 6.14. Thử HTTP bằng curl

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/202

curl -i -u bob:read \
  http://localhost:8080/api/documents/202

curl -i -u visitor:visit \
  http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/999
```

**Kết quả dự kiến với đúng cấu hình demo:**

| Request | Status | Giải thích |
| --- | --- | --- |
| `GET /public/ping`, guest | 200, `PONG` | Public |
| `GET /api/documents/101`, guest | 401 + Basic challenge | Chưa xác thực, chặn ở HTTP layer |
| Alice đọc 101 | 200 | Alice là owner và có ROLE_READER |
| Alice đọc 202 | 403 | Bob là owner, method security DENY |
| Bob đọc 202 | 200 | Bob là owner và có ROLE_READER |
| Visitor đọc 101 | 403 | Đã đăng nhập nhưng không có ROLE_READER |
| Alice đọc 999 | 403 trong demo | Resource không tìm thấy nên permission check trả false |

Body JSON dự kiến khi Alice đọc 101:

```json
{
  "id": 101,
  "title": "Alice private"
}
```

Thứ tự key và whitespace JSON do serializer quyết định. Không dựa vào format byte-for-byte, mà kiểm tra status, id và title.

**Vì sao 999 trả 403 thay vì 404?** Trong thiết kế demo, `@PreAuthorize` chạy **trước** khi thân service đọc record và không thể xác minh ownership cho ID không tồn tại, nên trả DENY. Chính sách che giấu existence có thể cố tình dùng cùng một response cho "không tồn tại" và "không có quyền" để hạn chế enumeration. Nếu sản phẩm muốn 404 cho cả trường hợp này, hãy thiết kế error mapping/lookup scoped có chủ đích, không mặc nhiên thay toàn bộ 403 bằng 404 mà bỏ mất phân biệt lỗi vận hành.

## 7. Kiểm thử với WebTestClient và StepVerifier

### 7.1. Tạo lớp test

Tạo `src/test/java/example/OwnershipApplicationTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority
        .SimpleGrantedAuthority;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.boot.test.context.SpringBootTest
        .WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class OwnershipApplicationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentService service;

    @Test
    void publicPing() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/documents/101")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceMayReadOwnDocument() {
        client.get().uri("/api/documents/101")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(101)
                .jsonPath("$.title").isEqualTo("Alice private");
    }

    @Test
    void aliceCannotReadBobDocument() {
        client.get().uri("/api/documents/202")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobMayReadBobDocument() {
        client.get().uri("/api/documents/202")
                .headers(h -> h.setBasicAuth("bob", "read"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(202);
    }

    @Test
    void authenticatedGuestWithoutRoleIsDenied() {
        client.get().uri("/api/documents/101")
                .headers(h -> h.setBasicAuth("visitor", "visit"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void nonExistingDocumentDeniedBeforeServiceBody() {
        client.get().uri("/api/documents/999")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void directServiceCallStillEnforcesOwnership() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(
                service.read(202L).contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void directServiceCallWithOwnerIsAllowed() {
        Authentication bob =
                UsernamePasswordAuthenticationToken.authenticated(
                    "bob", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(
                service.read(202L).contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)))
            .assertNext(view -> {
                assertEquals(202L, view.id());
                assertEquals("Bob private", view.title());
            })
            .verifyComplete();
    }
}
```

Chạy:

```bash
gradle test
```

Test dùng dữ liệu H2 qua R2DBC được khởi tạo từ `schema.sql`/`data.sql` khi Spring context khởi động. Test trực tiếp dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` để mô phỏng danh tính đã xác thực trong một pipeline **không có HTTP**; điều cần chứng minh là Spring AOP method security **vẫn chặn service.read(202)** khi actor không phải owner.

**Không lấy `mockUser` hoặc HTTP Basic làm bằng chứng duy nhất cho method security.** HTTP Basic test tốt cho toàn pipeline; test gọi service trực tiếp cho thấy bảo vệ không chỉ đến từ route `authenticated()`. Khi method được gọi qua proxy, `AccessDeniedException` là tín hiệu phản ánh quyền bị từ chối.

### 7.2. Test dữ liệu reactive và fail-closed

Nên bổ sung các ca:

- Permission bean nhận ID không hợp lệ → `Mono.just(false)`, không truy vấn.
- Actor không có `ROLE_READER` → false.
- Không có Reactor SecurityContext → false.
- ID tồn tại nhưng owner khác → false.
- Repository trả `Mono.empty()` → `hasElement()` phát false.
- Repository phát `Mono.error(new RuntimeException("DB down"))` → permission **không phát true**, request không vào service body; test ghi nhận error path phù hợp.
- Khi owner trong DB đổi hoặc bị revoke, request mới phải bị từ chối; không dùng cache allow vô hạn.

Có thể dùng `StepVerifier` với permission bean đơn lẻ trong unit test được mock repository. Nhưng khi kiểm thử tích hợp ownership thật, không được mock dữ liệu owner theo đúng user mong muốn rồi kết luận DB query đã an toàn; dùng R2DBC test database hoặc container PostgreSQL với dữ liệu thực.

### 7.3. Ma trận quyền quan trọng

| Actor | Role | Resource | Kỳ vọng |
| --- | --- | --- | --- |
| Guest | không | 101 | 401 ở HTTP |
| Alice | READER | 101 | ALLOW |
| Alice | READER | 202 | DENY |
| Bob | READER | 202 | ALLOW |
| Bob | READER | 101 | DENY |
| Visitor | GUEST | 101 | DENY |
| Alice | READER | 999 | DENY vì không xác minh owner |
| Alice | READER | id âm/sai format | Không cho vào dữ liệu; mã HTTP có thể 400/403 tùy layer |
| Alice | READER | 101 sau khi chuyển owner sang Bob | DENY trên request mới |
| Service gọi trực tiếp | Alice trong Reactor Context | 202 | AccessDeniedException |
| Service gọi trực tiếp | Bob trong Reactor Context | 202 | DocumentView |

## 8. Lựa chọn chiến lược tại tầng service

Có nhiều cách thực hiện object-level authorization. Nên chọn theo yêu cầu bảo mật và hiệu năng thay vì viết nhiều lớp truy vấn ngẫu nhiên.

| Cách | Cơ chế | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| `@PreAuthorize("hasRole('READER')")` + `findById(id)` | Chỉ RBAC, lookup unscoped | Dễ viết | **Không đủ** bảo vệ ownership |
| Custom bean `Mono<Boolean>` trong `@PreAuthorize` | Kiểm tra owner trước method | Policy tập trung, bảo vệ boundary service | Có thể cần thêm query để tải nội dung |
| `@PreAuthorize("isAuthenticated()")` + `findByIdAndOwnerId(id, actor)` | Scope ngay trong câu SELECT | Một round trip, tránh đọc record người khác | Logic quyền nằm ở thân service, cần giữ nhất quán giữa các method |
| Reactive repository query theo tenant + owner + ID | DB thực hiện điều kiện scope | Chống cross-tenant, dễ mở rộng | Cần thiết kế index/schema và identity mapping đúng |
| `@PostAuthorize` trên kết quả | Kiểm tra sau khi method đã tạo dữ liệu | Hữu ích khi cần xét object trả về | Dữ liệu đã được load; không thay thế kiểm tra trước side effects |
| DB Row-Level Security (PostgreSQL RLS) | Enforce trong database | Defense in depth mạnh | Cần truyền tenant/actor vào DB session/transaction đúng cách và test pool reuse |

### Khi nào bỏ một trong hai SELECT của ví dụ?

Nếu mục tiêu là tối ưu READ:

```java
// Mảnh code: service có sẵn documents.
@PreAuthorize("isAuthenticated()")
public Mono<DocumentView> read(Long id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> hasReaderAuthority(auth))
        .flatMap(auth -> documents.findByIdAndOwnerId(
                id, auth.getName()))
        .map(doc -> new DocumentView(
                doc.id(), doc.title()))
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
```

`hasReaderAuthority` là helper phải được định nghĩa; đoạn trên **minh họa riêng**, không phải source file độc lập. Điều kiện owner nằm **ngay trong SELECT**, nên DB không trả document ngoài owner của người gọi; nếu thiếu quyền, publisher empty dẫn tới response theo policy.

Đổi lại, cách này không đặt ownership dưới `@PreAuthorize`. Nó vẫn là kiểm tra quyền ở service nhưng phải được áp dụng nhất quán ở mọi method/service dùng tài nguyên. Một lớp policy service chung có thể tập trung quy tắc thay vì sao chép ở nhiều nơi.

## 9. Tại sao @PostAuthorize không thay thế mọi @PreAuthorize?

`@PostAuthorize` chạy sau khi method thực hiện để xét object trả về trước khi giao cho caller. Nó hữu ích khi việc xác định quyền cần nội dung object (ví dụ `ownerId` nằm trong document trả về). Nhưng:

1. Nếu method đã cập nhật database, gửi email hoặc publish event, kiểm tra sau **không đảo ngược side effects**.
2. Object có thể đã được tải vào memory dù cuối cùng bị từ chối; không nên log hoặc cache nhầm trước khi check.
3. Đối với `Flux<T>`, cần xem chính xác semantics của annotation và từng phần tử ở phiên bản Spring Security; không suy rằng kiểm tra một lần sẽ lọc an toàn mọi row.
4. Policy owner phức tạp đôi khi cần nhiều field từ DB; nên giới hạn query trước khi trả dữ liệu để giảm cơ hội lộ dữ liệu.

Ví dụ ý tưởng hậu kiểm:

```java
// Mảnh minh họa: cần xác nhận semantics @PostAuthorize
// với reactive return type và bản Spring Security sử dụng.
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<Document> readForPostAuthorization(Long id) {
    return documents.findById(id);
}
```

**Không sao chép đoạn này vào demo chạy đầy đủ** mà chưa kiểm chứng annotation/returnObject behavior theo phiên bản cụ thể và test negative; quyền sở hữu đáng tin cậy nhất vẫn được kiểm soát bằng scoped lookup hoặc policy service. Nếu truy vấn đã lọc theo owner và tenant, hậu kiểm chỉ là lớp bổ sung có điều kiện rõ ràng.

### Đối với Flux nhiều tài liệu

Một API liệt kê `Flux<Document>` nên dùng repository query kiểu:

```java
Flux<Document> findAllByOwnerId(String ownerId);
```

hoặc kết hợp tenant khi có multi-tenancy. Đừng chạy `findAll()` rồi `filter(doc -> owner.equals(...))` sau khi đã tải toàn bộ tài liệu của người khác. Filter tại application không thay thế tối ưu và bảo vệ phạm vi truy cập từ database, đặc biệt khi pagination, sorting, total counts hoặc cache có thể làm lộ metadata.

## 10. Khi update/delete: kiểm tra owner và sửa dữ liệu một cách nguyên tử

Đối với READ, kiểm tra hai lần (trước method và trong SELECT) là defense in depth. Đối với WRITE, nguy cơ TOCTOU lớn hơn:

```text
T0: SELECT document WHERE id=101 -> owner alice -> ALLOW
T1: Quyền sở hữu bị chuyển từ alice sang bob
T2: UPDATE documents SET title='...' WHERE id=101
    -> Alice vẫn sửa được record đã thuộc Bob nếu thiếu owner trong WHERE
```

**Không** chỉ dùng `@PreAuthorize("@documentPermission.canWrite(#p0)")` rồi update không giới hạn. Cần conditional mutation:

```sql
UPDATE documents
SET title = :title
WHERE id = :documentId
  AND owner_id = :trustedActorId;
```

Ví dụ mảnh code dùng Spring `DatabaseClient` và ReactiveSecurityContextHolder, **không phải file độc lập**:

```java
Mono<Long> updatedRows =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(this::isValidWriter)
        .flatMap(auth ->
            databaseClient.sql(
                "UPDATE documents SET title = :title "
              + "WHERE id = :id AND owner_id = :owner")
                .bind("title", newTitle)
                .bind("id", documentId)
                .bind("owner", auth.getName())
                .fetch()
                .rowsUpdated())
        .defaultIfEmpty(0L);
```

Phần này cần định nghĩa `databaseClient`, `isValidWriter`, `newTitle` và `documentId` cùng validation, vì là mảnh hướng dẫn. **Điểm an toàn nằm ở một lệnh UPDATE có điều kiện**: nếu owner không còn khớp tại thời điểm update, số dòng cập nhật là 0. Không dùng kết quả `updatedRows > 0` một cách đơn giản khi chính sách cho phép update nhiều dòng; demo chỉ nhắm một record theo khóa chính.

Với tenant-aware records, WHERE phải có **cả** `tenant_id = :trustedTenantId`. Nếu dùng ACL phức tạp, cần transaction hoặc lệnh SQL có điều kiện permission phù hợp để không có khoảng hở giữa kiểm tra và ghi.

### Trường hợp thay đổi quyền giữa check và write

Ngay cả khi `@PreAuthorize` đã kiểm tra membership, membership có thể bị revoke trước lúc ghi. Đối với thao tác nhạy cảm, cần thực thi quyền ở **cùng transaction/mutation** hoặc có khóa/phiên bản dữ liệu phù hợp. Reactive transaction nên dùng `TransactionalOperator` hoặc `@Transactional` trên publisher được Spring AOP quản lý với `ReactiveTransactionManager`; không chuyển sang JDBC transaction ThreadLocal của Servlet.

**Lưu ý:** Transaction không tự làm mọi check-then-act an toàn nếu isolation/câu lệnh không phù hợp. Thiết kế predicate nguyên tử và test race vẫn quan trọng.

## 11. Đa tenant: owner không đồng nghĩa tenant

Trong SaaS, hai người dùng có thể có username giống nhau ở hai tenant khác nhau, hoặc một principal được phép tham gia nhiều tenant. Query `WHERE owner_id = :username` đơn độc có thể gây lộ dữ liệu chéo tenant.

Một mô hình mạnh hơn:

```text
Document:
  id
  tenant_id
  owner_user_id
  title

Authenticated principal:
  immutable user_id
  allowed_tenants (đã xác minh)
  authorities/scopes

Authorized READ:
  requested document id
  AND document.tenant_id thuộc tập tenant được phép
  AND (
       document.owner_user_id == principal.user_id
       OR có permission đọc hợp lệ trong tenant đó
  )
```

**Không tin header `X-Tenant-ID` hoặc query `tenant=...` như bằng chứng membership.** Client chỉ chọn tenant mục tiêu; service vẫn xác minh token/DB/identity provider xác thực user có quyền trong tenant ấy. Nếu token chứa tenant claim, phải xác minh chữ ký, issuer, audience, thời hạn và quy tắc mapping claim.

Trong truy vấn, ưu tiên:

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_user_id = :trustedUserId;
```

Đối với tài khoản admin/cross-tenant support, thiết kế rule riêng với audit, scope và cơ chế phê duyệt khi cần; không cho role `ADMIN` của một tenant truy cập mọi tenant bằng một điều kiện OR toàn cục.

### Role và ownership là hai trục khác nhau

- `ROLE_READER` cho biết người gọi có khả năng đọc theo chức năng.
- `owner_user_id` cho biết người đó có quyền với **record cụ thể**.
- `tenant_id` giới hạn không gian dữ liệu.
- ACL/sharing grants có thể cấp quyền cho người không phải owner trong cùng tenant.
- Trạng thái tài nguyên (locked, archived, legal hold) có thể giới hạn thao tác thêm.

Trong sản phẩm thật, phép kiểm tra quyền không nên chỉ so sánh chuỗi; cần mô hình permission phù hợp vòng đời dữ liệu.

## 12. Những lỗi kiến trúc thường gặp

### 12.1. Self-invocation làm annotation không chạy

```java
@Service
class DangerousService {
    public Mono<Document> outer(Long id) {
        return this.securedRead(id); // cùng instance, có thể bỏ qua AOP proxy
    }

    @PreAuthorize("@documentPermission.canRead(#p0)")
    public Mono<Document> securedRead(Long id) {
        // ...
        return Mono.empty();
    }
}
```

Đây là bẫy của Spring AOP proxy-based method security. **Sửa:** đưa phương thức bảo vệ vào bean riêng được inject; gọi qua proxy; hoặc đảm bảo policy owner được thực hiện ở query/service domain không phụ thuộc proxy.

Không đặt annotation trên `private` helper rồi nghĩ Spring AOP sẽ intercept. Các lớp/phương thức final cũng cần lưu ý proxy strategy; trong demo Java classes không final và method được gọi qua Spring bean.

### 12.2. Dùng ThreadLocal security context trong pipeline reactive

```java
// SAI cho logic reactive phụ thuộc Reactor Context:
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

Code trên có thể trả context sai/mất khi pipeline chuyển thread. Trong Spring WebFlux, dùng `ReactiveSecurityContextHolder.getContext()` trong publisher, không tự `block()` hoặc `subscribe()` tách nhánh.

### 12.3. Dùng ownerId do client truyền

```java
// SAI: client tự khai ownerId và service tin luôn.
Mono<Document> read(Long id, String ownerId) {
    return documents.findByIdAndOwnerId(id, ownerId);
}
```

Dù query có `owner_id`, nó vẫn sai nếu `ownerId` lấy trực tiếp từ query/header/request body mà không đối chiếu với principal. Lấy actor ID từ Authentication đã xác minh, hoặc xác thực membership từ DB.

### 12.4. Chỉ kiểm tra role

`@PreAuthorize("hasRole('READER')")` không biết tài liệu 101 thuộc Alice hay Bob. Dùng ownership lookup hoặc scoped query.

### 12.5. Kiểm tra quyền rồi đọc theo ID không scope

`@PreAuthorize(...)` kiểm tra tại thời điểm T0, nhưng `findById(id)` tại T1 có thể trả tài nguyên đổi owner. Với dữ liệu nhạy cảm, read/write nên scope theo chủ sở hữu/tenant ngay trong truy vấn thực thi.

### 12.6. Query database bằng block()

```java
// SAI: có thể làm nghẽn event loop, mất lợi ích reactive.
boolean allowed =
    documents.findByIdAndOwnerId(id, actor).block() != null;
```

Dùng `Mono<Boolean>` và return publisher; Spring Security reactive method interceptor hỗ trợ nó. Nếu thư viện thực sự blocking, dùng executor riêng có giới hạn và chiến lược chuyển thread, không gọi block trên Netty event loop.

### 12.7. Mono.empty được hiểu là ALLOW

Một permission bean trả `Mono.empty()` khi không tìm thấy user/record có thể dẫn đến abstain semantics ngoài ý định ở một số layer. Chính sách owner nên trả **false tường minh** khi thiếu dữ liệu và không tự động bỏ qua bảo vệ.

### 12.8. Nuốt lỗi database rồi cấp quyền

`onErrorReturn(true)` hoặc `onErrorResume(e -> Mono.just(true))` làm outage trở thành security bypass. Fail-closed và ghi metric lỗi hạ tầng là yêu cầu bắt buộc.

### 12.9. Dùng @PostAuthorize sau side effect

Không để method gửi thông báo, ghi tiền hoặc cập nhật tài liệu rồi mới từ chối ở `@PostAuthorize`. Phải xác minh quyền **trước/đồng thời với mutation** và dùng DB predicate nguyên tử.

### 12.10. Chỉ test controller

Khi HTTP rule đã `authenticated()`, controller có thể trả 403 vì lý do khác, không chứng minh AOP method owner check hoạt động. Viết test **gọi trực tiếp service bean** với Reactor Context và negative case.

### 12.11. Cache permission không có invalidation

Nếu user từng là owner và cache `canRead=true` theo `documentId` mà không gắn user/tenant, sau khi chuyển owner người cũ vẫn có quyền. Cache authorization (nếu cần) phải có key chính xác, TTL ngắn/eviction phù hợp và invalidation theo biến động quyền; không để `ALLOW` tồn tại vô thời hạn.

### 12.12. Existence leak qua khác biệt 403/404

Trả 403 khi record có thật nhưng không thuộc owner, trả 404 khi record không có có thể giúp đoán ID. Quyết định error mapping theo threat model, tránh lộ nội dung/metadata, audit denied access. Demo trả 403 cho cả absent và wrong-owner do gate kiểm tra trước service.

### 12.13. Mặc định cho phép khi service được gọi từ job

Scheduled job và message consumer có thể không có ReactiveSecurityContextHolder. Khi method đã bảo vệ cần actor, thiếu context phải DENY; job có nhu cầu thật nên có **system actor** và permission rõ, không dùng hardcoded `ROLE_ADMIN` toàn quyền hoặc bypass annotation bí mật.

## 13. Hiệu năng và quan sát khi ownership lookup là reactive

Kiểm tra owner trước mỗi method có thể tạo thêm database round trip:

```text
Request
  -> authentication
  -> permission SELECT EXISTS/SELECT scoped
  -> service SELECT scoped
  -> response
```

Tối ưu có kiểm soát:

- **Đếm truy vấn:** trong demo hai SELECT là chủ ý; production có thể đổi sang một SELECT scoped trong service nếu kiểm tra chức năng/actor vẫn chặt.
- **Không đọc cả document chỉ để kiểm tra Boolean** nếu backend hỗ trợ `EXISTS` hoặc `SELECT 1 ... LIMIT 1` hiệu quả.
- **Index theo ID, tenant, owner** dựa trên explain plan và workload; không tự động tạo index thừa.
- **Reactive driver thật:** R2DBC cho phép nonblocking I/O; không biến JDBC blocking thành reactive chỉ nhờ bọc `Mono.just(...)`.
- **Giới hạn lưu lượng:** tránh login/client gọi hàng nghìn ID ngẫu nhiên làm quá tải permission DB; dùng rate limit, pagination và backpressure theo thiết kế.
- **Timeout:** timeout DB theo SLO, phản hồi fail-closed khi không xác minh được quyền; đừng chờ vô hạn.
- **N+1 với Flux:** không gọi một truy vấn owner cho mỗi phần tử khi có thể scope danh sách bằng query server-side.
- **Cache:** có thể cache metadata ít thay đổi, nhưng phải theo actor/tenant/permission version và invalidation; không cache "allow" toàn cục theo document ID.
- **Audit:** ghi actor ID, resource ID, decision và policy version với mức cần thiết; không log JWT raw, password, cookie/session ID hoặc nội dung document riêng.
- **Metrics:** đo permission lookup p50/p95/p99, allow/deny/error, DB pool wait, query latency, retry rate, không chỉ HTTP total latency.
- **Chống TOCTOU:** mutation cần điều kiện owner/tenant trong SQL; cache/read-before-write không thể thay thế predicate nguyên tử.

Một số hệ thống dùng DB Row-Level Security (RLS) của PostgreSQL để bảo vệ thêm; khi dùng connection pool reactive, cần đặt session/transaction variables theo actor **đúng connection và vòng đời transaction**, tránh để thông tin tenant của request trước tràn sang request sau.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `authenticated()` trên `/api/documents/**` chưa đủ?  
**Đáp:** Nó chỉ xác thực identity cho route; không kiểm tra tài liệu cụ thể thuộc ai. Alice vẫn có thể truy cập ID của Bob nếu service dùng `findById(id)` không giới hạn.

**Câu 2.** Một service reactive lấy user từ đâu cho đáng tin?  
**Đáp:** `ReactiveSecurityContextHolder.getContext()` trong publisher, sau đó lấy Authentication/immutable user ID do hệ thống đã xác thực.

**Câu 3.** `@PreAuthorize("@documentPermission.canRead(#p0)")` có ý nghĩa gì?  
**Đáp:** Gọi bean `documentPermission` với tham số thứ nhất của method; bean trả `Mono<Boolean>` thực hiện lookup bất đồng bộ trước khi cho method chạy.

**Câu 4.** Có nên viết `@PreAuthorize("hasRole('READER') && @documentPermission.canRead(#p0)")` mà không kiểm thử không?  
**Đáp:** Không nên. Với một số phiên bản Spring Security 6.3 có vấn đề kết hợp Boolean expression và Mono<Boolean>. Đưa cả role và owner vào bean reactive, test trên phiên bản thật.

**Câu 5.** `findByIdAndOwnerId(id, auth.getName())` trả Mono.empty thì kết luận gì?  
**Đáp:** Không có tài liệu thuộc actor với ID đó; permission dùng `hasElement()` thành false. Không phân biệt record không tồn tại hay tồn tại nhưng khác owner khi chưa được phép.

**Câu 6.** Vì sao `defaultIfEmpty(false)` tốt hơn để `Mono.empty()` từ permission bean thoát ra?  
**Đáp:** Nó biểu đạt rõ DENY khi thiếu context/record, tránh trường hợp abstain hoặc hành vi mặc định khác ý định.

**Câu 7.** DB timeout có được `onErrorReturn(true)` để không làm gián đoạn user không?  
**Đáp:** Không. Không xác minh được quyền thì không có cơ sở ALLOW; cần phản hồi lỗi có kiểm soát và audit/alert.

**Câu 8.** Self-invocation `this.read(id)` có thể bỏ qua annotation không?  
**Đáp:** Có, trong mô hình Spring AOP proxy-based. Phải gọi qua proxy/bean phù hợp hoặc giữ predicate quyền trong query/domain.

**Câu 9.** Vì sao READ có thể dùng scoped SELECT, còn WRITE cần đặc biệt cẩn trọng?  
**Đáp:** Vì owner/quyền có thể đổi giữa kiểm tra và mutation. UPDATE/DELETE nên chứa owner/tenant predicate ngay trong một câu lệnh hoặc transaction/isolation phù hợp.

**Câu 10.** Khi nào @PostAuthorize hữu ích?  
**Đáp:** Khi cần xét object trả về để quyết định trước khi trao cho caller. Nhưng nó không thể hoàn tác các side effects đã xảy ra trong method.

**Câu 11.** Vì sao `ownerId` trong URL/header không đủ?  
**Đáp:** Client có thể giả. Cần dùng actor ID đã xác minh và đối chiếu owner thật trong DB.

**Câu 12.** Hai tenant có username `alice`; so sánh `owner_id='alice'` có đủ không?  
**Đáp:** Không. Cần immutable user ID và tenant ID đã xác minh, kết hợp membership/ACL đúng phạm vi.

**Câu 13.** Làm sao test service không chỉ dựa vào HTTP?  
**Đáp:** Gọi Spring-injected service bean qua proxy trong `StepVerifier`, gắn Authentication vào Reactor Context, thử allowed/denied; sai owner phải phát `AccessDeniedException`.

**Câu 14.** Vì sao sử dụng `Flux.findAll().filter(...)` theo owner dễ nguy hiểm?  
**Đáp:** Nó đọc quá nhiều dữ liệu trước khi lọc, gây nguy cơ lộ qua logs/cache/count và hiệu năng kém; nên scope ở truy vấn DB.

**Câu 15.** Một quyền quản trị ở tenant A có tự cho phép đọc tài liệu tenant B không?  
**Đáp:** Không, trừ khi policy cho phép cross-tenant một cách tường minh. Scope tenant phải được kiểm tra bằng claim/DB đáng tin, không chỉ dựa vào role chung.

**Kết luận:** Trong Spring Security WebFlux, **method security kết hợp lookup dữ liệu reactive** giúp chặn truy cập sai chủ sở hữu ngay ở service boundary. Đặt policy vào bean trả `Mono<Boolean>` khi cần `@PreAuthorize`, lấy actor từ Reactor SecurityContext, để repository đối chiếu **ID + owner (+ tenant)** và đảm bảo fail-closed. Với thao tác thay đổi dữ liệu, đặt điều kiện quyền trong chính mutation để chống TOCTOU; kiểm thử cả đường HTTP lẫn service trực tiếp.

## Tài liệu tham khảo

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`/`@PostAuthorize`, bean trả `Mono<Boolean>` và reactive interceptors.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): đọc và truyền SecurityContext trong Reactor.
- [Spring Security — PreAuthorize API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html): khai báo expression bảo vệ phương thức.
- [Spring Security — Reactive Method Security Spring AOP](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): behavior khi gọi method qua proxy và biểu thức tùy biến.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): request thay đổi trạng thái và CSRF bên cạnh authorization.
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): `ReactiveCrudRepository`, các derived queries và publisher reactive.
- [Spring Boot — R2DBC SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình `spring.r2dbc.url` và embedded H2.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`, `data.sql` và `spring.sql.init.mode`.
- [R2DBC H2 — ConnectionFactory URI](https://github.com/r2dbc/r2dbc-h2): cú pháp `r2dbc:h2:mem:///...` và cấu hình memory H2.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` và Reactor Context trong test.
