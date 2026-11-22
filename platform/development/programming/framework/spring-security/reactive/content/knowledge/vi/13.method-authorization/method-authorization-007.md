# Sử dụng bean trả về Mono<Boolean> cho điều kiện phân quyền

> **Phạm vi:** Phân quyền phương thức trong **Spring Security reactive / Spring WebFlux**, cụ thể là dùng một **Spring bean chứa logic phân quyền bất đồng bộ trả về `Mono<Boolean>`** từ biểu thức `@PreAuthorize`. Ví dụ theo **Spring Boot 3.x, Spring Security 6.x (hướng AuthorizationManager) và Java 17+**. Mục tiêu là kiểm tra quyền người dùng dựa trên chủ sở hữu tài liệu trong repository reactive, không chặn luồng bằng `block()` và không nhầm `Mono.empty()` với kết quả từ chối rõ ràng.

## 1. Kết quả cần đạt

Sau bài này bạn sẽ:

1. Giải thích tại sao `@PreAuthorize("hasRole('READER')")` đôi khi không đủ để kiểm tra **ownership**, tenant hoặc điều kiện cần gọi database.
2. Bật đúng `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` cho Spring Security reactive hỗ trợ điều kiện `Mono<Boolean>`.
3. Tạo Spring bean `@Component("documentAccess")` có method `canRead(Authentication, String)` trả `Mono<Boolean>` rồi tham chiếu bằng `@PreAuthorize("@documentAccess.canRead(authentication, #p0)")`.
4. Kết hợp một reactive repository vào policy bằng `map` / `flatMap` / `defaultIfEmpty(false)`, tuyệt đối không `block()` trong WebFlux request.
5. Phân biệt tín hiệu `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()` và `Mono.error(...)` về quyết định và xử lý lỗi.
6. Hiểu Spring AOP proxy, thời điểm subscription, Reactor Context và cách HTTP authorization kết hợp method authorization.
7. Viết unit tests bằng `StepVerifier` và integration tests bằng `WebTestClient` với các trường hợp 200 / 401 / 403.
8. Tránh sai lầm về self-invocation, SpEL root, tham số method, lỗi repository, leakage dữ liệu và cơ chế fail closed.

## 2. Tại sao phải sử dụng bean phân quyền reactive?

Hãy tưởng tượng API:

```http
GET /documents/doc-a
Authorization: Basic ...
```

HTTP security đã xác minh danh tính và biết user thuộc role `READER`. Nhưng tài liệu `doc-a` thuộc về **alice**. Nếu **bob** cũng có `ROLE_READER`, một rule chỉ yêu cầu đăng nhập/role chưa ngăn bob đọc tài liệu của alice.

Các trường hợp này cần **quyền theo dữ liệu**:

- Người dùng chỉ được đọc tài liệu mình sở hữu; quản trị viên được phép đọc các tài liệu có tồn tại.
- Nhân viên chỉ xem đơn hàng thuộc tenant được cấp.
- Một lệnh chuyển tiền chỉ được phép nếu người thực hiện có quyền ở tài khoản nguồn.
- Chỉ tài khoản được phân công mới có thể chỉnh sửa một tác vụ.
- Policy cần đọc quyền từ database hoặc cache reactive trước khi đưa ra quyết định.

Bạn có thể dùng Java bean để mô tả chính sách này rõ ràng, tách khỏi controller và service. Nếu việc tra cứu dữ liệu trả `Mono<Document>`, bean có thể trả **`Mono<Boolean>`** mà không cần chặn thread.

### 2.1 So sánh với các phương án khác

| Cách | Khi nào hợp lý | Giới hạn |
| --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Điều kiện tĩnh theo authorities | Không đủ cho ownership của từng document |
| `@PreAuthorize("#p0 == authentication.name")` | So sánh trực tiếp tham số với principal | Chỉ phù hợp khi owner đã nằm trong tham số đáng tin cậy; không tra DB |
| `@PreAuthorize("@documentAccess.canRead(authentication, #p0)")` | Logic domain phức tạp, DB/cache reactive, tái sử dụng | Cần bật reactive method security đúng cách và kiểm thử |
| `ServerHttpSecurity.authorizeExchange` | Chặn request HTTP ở lớp WebFilter | Thường chưa có tài nguyên/domain object để quyết định |
| Gọi policy bằng tay trong service | Một số workflow đặc thù muốn xử lý result thay vì exception | Dễ quên ở call path khác nếu không có convention |
| Custom `ReactiveAuthorizationManager` | Cần kết quả chi tiết, interceptor tùy chỉnh | Phức tạp hơn, không cần thiết cho bài cơ bản |

**Lựa chọn của bài:** Giữ HTTP-level authorization để yêu cầu đăng nhập, đồng thời đặt `@PreAuthorize` trên **service bean** để áp dụng quyền đối với document. Hai lớp bảo vệ có nhiệm vụ bổ sung, không thay thế nhau.

## 3. Phiên bản API: điểm cần xác định trước khi viết

Đối với ví dụ Spring Security 6.x, bật method security theo hướng **AuthorizationManager** một cách tường minh:

```java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
```

Spring Security 6.5 mô tả chính thức rằng biểu thức `@PreAuthorize` có thể tham chiếu một bean/function trả **`Boolean` hoặc `Mono<Boolean>`** khi sử dụng hạ tầng reactive AuthorizationManager. Nó cho phép một rule chờ publisher quyết định trước khi chạy method được bảo vệ.

Ví dụ contract:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public Mono<String> readText(String documentId) {
    // ... logic truy cập tài liệu
}
```

Đây là **một method snippet** (chưa có class/bean), chỉ đúng khi `documentAccess` là Spring bean có method phù hợp và reactive method security đang được bật. Các file chạy được trình bày ở phần 5.

**Điểm dễ nhầm giữa tài liệu các thế hệ:** Các ví dụ method security reactive kiểu cũ `@EnableReactiveMethodSecurity` có những giới hạn về biểu thức Boolean đồng bộ. Để sử dụng **`Mono<Boolean>` trong SpEL**, dùng đúng đường đi `useAuthorizationManager = true` trên Spring Security 6.x và giữ method được bảo vệ trả về reactive publisher như `Mono<T>` / `Flux<T>`.

Không áp dụng `@EnableMethodSecurity` của Servlet thay cho `@EnableReactiveMethodSecurity`. Có thể có những API tương tự ở Spring Security 7.x nhưng bài này nhất quán với baseline Spring Security 6.x.

### 3.1 Bean, SpEL và reactive publisher

Với annotation:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
```

các thành phần có nghĩa:

- `@PreAuthorize`: Spring Security đánh giá **trước khi thực thi method được bảo vệ**.
- `@documentAccess`: tham chiếu bean có tên `documentAccess` trong Spring application context.
- `canRead(...)`: gọi method của bean chính sách; kết quả là `Mono<Boolean>`.
- `authentication`: đối tượng `Authentication` đã được đưa vào security expression root theo context của method invocation.
- `#p0`: tham số thứ nhất của method đang được bảo vệ, ví dụ `documentId`; tránh phụ thuộc tên biến Java khi build không giữ `-parameters`.
- `true`: policy cho phép; `false`: policy từ chối.
- `Mono.empty()`: ngữ nghĩa **không ra quyết định (abstain)** theo tài liệu hiện hành, không nên dùng làm câu trả lời “không có document”.
- `Mono.error(...)`: lỗi khi thực thi policy; không phải kết quả đồng ý.

**Không tự gọi `subscribe()` và không lấy kết quả bằng `block()`**. Hạ tầng reactive method security sẽ subscribe vào decision publisher theo cơ chế của nó và truyền tín hiệu từ chối đến caller khi cần.

## 4. Luồng bảo mật từ HTTP đến điều kiện phân quyền

```text
Client GET /documents/doc-a, Basic credentials của alice
       |
       v
SecurityWebFilterChain (WebFlux)
       |
       +-- Authentication manager kiểm chứng username/password
       |
       +-- authorizeExchange("/documents/**").authenticated()
       |
       v
DocumentController -> gọi DocumentService.readText("doc-a")
                               |
                               v
                  Spring AOP method security proxy
                               |
                      @PreAuthorize expression
                               |
                      @documentAccess.canRead(
                          authentication, "doc-a")
                               |
                      DocumentRepository.findById
                               |
                         Mono<Document>
                               |
                        map owner/role
                               |
                      Mono<Boolean> decision
                       /              \
                  true               false
                   |                   |
                   v                   v
             Gọi service         Access denied
             readText()          (HTTP thường 403)
                   |
                   v
             Mono<String>
                   |
                   v
             HTTP 200 body
```

Đường đi này cho thấy **HTTP WebFilter** xử lý xác thực và rule path, sau đó **method security** bảo vệ service method qua Spring AOP. Nếu controller khác, scheduled/reactive entry point khác hoặc một service khác gọi cùng bean qua Spring proxy và có SecurityContext hợp lệ, method security vẫn có cơ hội áp dụng policy. Điều này giúp phòng lỗi “HTTP route mới quên gọi authorization check”.

### 4.1 Khi nào đánh giá?

Publisher Reactor thường **lười**: `Mono` được tạo khi assembly nhưng nhiều phần logic chạy khi subscription. Hạ tầng reactive method security tương tác với Reactor Context để lấy danh tính tại subscription. Đây là lý do method được bảo vệ nên có **reactive return type**.

Ví dụ `Mono<Boolean>` từ repository không chạy I/O cho đến khi được subscribe. Không biến bất đồng bộ thành đồng bộ chỉ để đưa vào `@PreAuthorize`:

```java
// Không dùng trong WebFlux:
boolean allowed = documentRepository.findById(id)
    .map(doc -> doc.owner().equals(username))
    .block(); // Có thể chặn event-loop hoặc tạo subscription sai context.
```

Dòng trên là **snippet minh họa lỗi**, không phải code độc lập. Viết policy trả `Mono<Boolean>` cho Spring Security dùng thay vì chờ bằng `block()`.

## 5. Dự án mẫu Spring Boot 3 / Java 17+

Ta xây một API nhỏ với dữ liệu bất biến trong bộ nhớ, nhưng truy xuất thông qua interface reactive `Mono`. Phần repository được cố ý giữ đơn giản; khi thay bằng Spring Data R2DBC/MongoDB reactive, API policy không cần chuyển sang blocking.

Yêu cầu: JDK 17+, project Spring Boot 3.x với Spring Reactive Web và Spring Security.

Trong `build.gradle` của project đã cấu hình Spring Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng **`spring-boot-starter-webflux`** làm server. Nếu cùng thêm `spring-boot-starter-web` (MVC), Spring Boot thường chọn MVC/Servlet mặc định; có `Mono` trên classpath **chưa đủ** chứng minh request dùng `SecurityWebFilterChain`.

Cấu trúc đầy đủ:

```text
src/
  main/java/com/example/reactivepolicy/
    ReactivePolicyApplication.java
    SecurityConfig.java
    DocumentRepository.java
    DocumentAccessPolicy.java
    DocumentService.java
    DocumentController.java
  test/java/com/example/reactivepolicy/
    DocumentAccessPolicyTest.java
    DocumentMethodSecurityTest.java
    DocumentHttpTest.java
```

Các class `public` được đặt ở **file riêng đúng tên**, cùng package `com.example.reactivepolicy`. Ví dụ dùng repository demo và password giả; **không dùng user/secret cố định trong production**.

### 5.1 ReactivePolicyApplication.java

`src/main/java/com/example/reactivepolicy/ReactivePolicyApplication.java`:

```java
package com.example.reactivepolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactivePolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactivePolicyApplication.class, args);
    }
}
```

### 5.2 SecurityConfig.java: HTTP và method security

`src/main/java/com/example/reactivepolicy/SecurityConfig.java`:

```java
package com.example.reactivepolicy;

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
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/documents/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo-password"))
            .roles("READER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }
}
```

**Giải thích:**

- `@EnableWebFluxSecurity` bật HTTP security ở WebFlux; `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` bật reactive method security theo cách hỗ trợ decision publisher.
- `/documents/**.authenticated()` **chỉ yêu cầu đã đăng nhập**. Kiểm tra owner/role ADMIN của từng tài liệu được giao cho policy bean ở service.
- `.httpBasic(...)` dùng authentication để có principal trong Reactor Context. `.formLogin(...disable)` tắt form redirect trong bài test API. HTTP Basic yêu cầu **HTTPS** khi truyền credential thật; dùng HTTP localhost chỉ với dữ liệu giả.
- `User.roles("ADMIN")` thêm authority `ROLE_ADMIN`. Username/password demo được mã hóa một chiều bằng encoder trước khi đưa vào user store.
- `anyExchange().denyAll()` là fallback an toàn. Đừng thay bằng `permitAll()` cho tiện.

### 5.3 DocumentRepository.java: dữ liệu sở hữu tài liệu

`src/main/java/com/example/reactivepolicy/DocumentRepository.java`:

```java
package com.example.reactivepolicy;

import java.util.Map;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentRepository {

    private final Map<String, DocumentRecord> records = Map.of(
        "doc-a", new DocumentRecord(
            "doc-a", "alice", "Alice private document"),
        "doc-b", new DocumentRecord(
            "doc-b", "bob", "Bob private document")
    );

    public Mono<DocumentRecord> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(records.get(id)));
    }
}

// Package-private record, cùng file Java với DocumentRepository.
record DocumentRecord(String id, String owner, String content) {}
```

**Tại sao dùng `Mono.defer(...)`?** Để việc tra cứu được thực hiện khi có subscription, tương tự semantics của reactive repository. Đối với Map nhỏ, bản thân `Map.get` không phải I/O chặn. Trong production, có thể thay bằng database client reactive. Không gói một JDBC call blocking vào `Mono.just(jdbcCall())` rồi cho rằng nó non-blocking.

`DocumentRecord` là record **package-private** ở cuối file, không cần tạo thêm `DocumentRecord.java`. Vì toàn bộ ví dụ nằm cùng package, `DocumentService` và `DocumentAccessPolicy` có thể gọi các accessor `owner()` / `content()`.

### 5.4 DocumentAccessPolicy.java: bean trả về Mono<Boolean>

`src/main/java/com/example/reactivepolicy/DocumentAccessPolicy.java`:

```java
package com.example.reactivepolicy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentAccess")
public class DocumentAccessPolicy {

    private final DocumentRepository repository;

    public DocumentAccessPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(Authentication authentication, String id) {
        // Không chấp nhận danh tính null/anonymous ở tầng policy.
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Mono.just(false);
        }

        return repository.findById(id)
            .map(document -> {
                boolean owner =
                    document.owner().equals(authentication.getName());

                boolean admin = authentication.getAuthorities().stream()
                    .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));

                return owner || admin;
            })
            // Document không tồn tại: trả một quyết định từ chối rõ ràng.
            .defaultIfEmpty(false);
    }
}
```

Đây là **Spring bean đầy đủ**, không phải pseudocode. `canRead` trả **`Mono<Boolean>`**, chứ không trả Boolean đồng bộ.

Ý nghĩa từng thành phần:

1. Kiểm `Authentication` null, `isAuthenticated` và anonymous trước khi xét dữ liệu. `AnonymousAuthenticationToken` có thể được đánh dấu authenticated theo nghĩa kỹ thuật nhưng vẫn **không phải** danh tính người dùng đã xác minh.
2. `repository.findById(id)` trả `Mono<DocumentRecord>`, là nguồn async decision.
3. `map(document -> ...)` kết hợp hai điều kiện: người gọi là **owner** hoặc có `ROLE_ADMIN` đáng tin cậy.
4. `defaultIfEmpty(false)` bắt **không tìm được tài liệu** thành một quyết định từ chối tường minh. Không coi `Mono.empty()` đồng nghĩa với `Mono.just(false)` trong method security.
5. Code **không tự subscribe, không block**, nên tương thích với Reactive Method Security AOP và WebFlux runtime.
6. `Authentication` phải được cấp bởi manager/provider đã kiểm chứng credential. Đừng tạo token authenticated/role từ query param, request body hoặc header mà chưa kiểm chứng.

Một policy phù hợp dự án thật còn phải kiểm tra **tenant, trạng thái tài liệu, version, quyền chia sẻ, phân cấp tổ chức hoặc trạng thái khóa**. Kiểm tra owner đơn giản chỉ minh họa cách ghép truy vấn dữ liệu và quyết định bất đồng bộ.

### 5.5 DocumentService.java: tham chiếu bean từ @PreAuthorize

`src/main/java/com/example/reactivepolicy/DocumentService.java`:

```java
package com.example.reactivepolicy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentAccess.canRead(authentication, #p0)")
    public Mono<String> readText(String id) {
        return repository.findById(id)
            .map(DocumentRecord::content)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                )
            ));
    }
}
```

**Đọc annotation:**

- `@documentAccess` tham chiếu đúng bean name trong `@Component("documentAccess")`.
- `authentication` trong SpEL là identity của method-security evaluation context, **không phải tham số mà client tự gửi**.
- `#p0` là tham số method thứ nhất (`String id`), dùng được kể cả khi build không giữ tên tham số cho reflection. Nếu muốn `#id`, cần đảm bảo cơ chế discover parameter names được cấu hình/biên dịch đúng.
- Policy trả `Mono<Boolean>`; hạ tầng `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` đánh giá nó **trước khi cho đọc nội dung tài liệu**.
- `readText` trả `Mono<String>` và nằm trong Spring bean `@Service`. Controller phải gọi bean thông qua Spring proxy; không dùng `new DocumentService(...)` tự tạo trong application rồi kỳ vọng AOP chạy.

**Vì sao service vẫn có `switchIfEmpty(404)`?** Nếu dữ liệu bị xóa giữa lần check của policy và lần đọc service, service có thể nhận empty và trả 404. Trong ví dụ này, khi `id` không tồn tại **ngay từ lúc kiểm policy**, `defaultIfEmpty(false)` từ chối trước nên thường là 403 đối với caller đã login. Đây là quyết định demo theo hướng không tiết lộ sự tồn tại tài liệu; sản phẩm thật phải chọn chính sách 403/404 có chủ đích.

### 5.6 DocumentController.java: HTTP endpoint

`src/main/java/com/example/reactivepolicy/DocumentController.java`:

```java
package com.example.reactivepolicy;

import org.springframework.http.MediaType;
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

    @GetMapping(
        value = "/documents/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> getDocument(@PathVariable String id) {
        return documents.readText(id);
    }
}
```

Ở controller **không viết lại** `if (doc.owner().equals(...))`. Controller gọi `DocumentService` do Spring quản lý; method-security proxy áp dụng cùng policy dù sau này còn có controller/functional route khác gọi service qua bean.

Dùng `Mono<String>` xuyên suốt giúp Spring Security duy trì Reactor Context của request đã xác thực. Không gọi `block()`, `subscribe()`, `toFuture()` hoặc tạo thread thủ công để tìm username/role trong handler.

## 6. Kết quả kỳ vọng của ứng dụng

| HTTP request | Credential | Document | Quyết định của bean | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| GET `/documents/doc-a` | Không có | Có | HTTP chain chặn trước policy | **401** với HTTP Basic |
| GET `/documents/doc-a` | alice, đúng password | Alice sở hữu | `Mono.just(true)` | **200**, body `Alice private document` |
| GET `/documents/doc-a` | bob, đúng password | Alice sở hữu | `Mono.just(false)` | **403 Forbidden** |
| GET `/documents/doc-b` | bob, đúng password | Bob sở hữu | `Mono.just(true)` | **200**, body `Bob private document` |
| GET `/documents/doc-b` | alice, đúng password | Bob sở hữu | `Mono.just(false)` | **403** |
| GET `/documents/doc-a` | admin, đúng password | Có | `Mono.just(true)` do `ROLE_ADMIN` | **200**, body `Alice private document` |
| GET `/documents/unknown` | admin, đúng password | Không có | `defaultIfEmpty(false)` | **403** trong chính sách demo |
| POST `/documents/doc-a` | alice, đúng password | Không có POST route | HTTP rule cuối/CSRF có thể chặn | Không được suy ra quyền từ GET |

Sự khác nhau giữa 401 và 403:

- **401**: request chưa xác thực hợp lệ ở HTTP security, hoặc không có credential phù hợp theo Basic challenge.
- **403**: người dùng đã xác thực nhưng **method policy** từ chối, hoặc CSRF/HTTP policy từ chối request khác.
- **200**: HTTP authentication/authorization và method authorization đều cấp quyền, rồi handler trả dữ liệu thành công.

Vì `DocumentAccessPolicy` trả Boolean khi có document nhưng không tự sinh HTTP status, **Spring Security method interceptor** mới chuyển quyết định từ chối sang exception để WebFlux security infrastructure xử lý.

## 7. Test đơn vị bean bằng StepVerifier

Lớp policy là bean độc lập, nên có thể test các nhánh business logic mà **không cần HTTP server**. Với project đã có `reactor-test` và `spring-boot-starter-test`, file:

`src/test/java/com/example/reactivepolicy/DocumentAccessPolicyTest.java`:

```java
package com.example.reactivepolicy;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.test.StepVerifier;

class DocumentAccessPolicyTest {

    private DocumentAccessPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new DocumentAccessPolicy(new DocumentRepository());
    }

    private Authentication user(String name, String role) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_" + role))
        );
    }

    @Test
    void ownerIsAllowed() {
        StepVerifier.create(policy.canRead(user("alice", "READER"), "doc-a"))
            .expectNext(true)
            .verifyComplete();
    }

    @Test
    void otherUserIsDeniedEvenWithSameRole() {
        StepVerifier.create(policy.canRead(user("bob", "READER"), "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void adminIsAllowedForExistingDocument() {
        StepVerifier.create(policy.canRead(user("admin", "ADMIN"), "doc-a"))
            .expectNext(true)
            .verifyComplete();
    }

    @Test
    void missingDocumentIsDeniedEvenForAdmin() {
        StepVerifier.create(policy.canRead(user("admin", "ADMIN"), "missing"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(policy.canRead(null, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void unauthenticatedTokenIsDenied() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "not-verified"
        );
        StepVerifier.create(policy.canRead(request, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void anonymousAuthenticationIsDenied() {
        var anonymous = new AnonymousAuthenticationToken(
            "test-key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );
        StepVerifier.create(policy.canRead(anonymous, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*DocumentAccessPolicyTest'
```

Kỳ vọng là 7 test hoàn tất. Đây là **kỳ vọng của mã nguồn bài học**, chưa phải kết quả thực thi build trong môi trường này.

**Bảo mật của unit test:** `UsernamePasswordAuthenticationToken.authenticated(...)` tạo một đối tượng đã đánh dấu xác thực **để giả lập trường hợp thành công**. Trong production, không được coi một đối tượng tự tạo từ input client là credential đã được chứng minh. Test policy không thay thế test lớp authentication/WebFilter.

### 7.1 Tại sao không chỉ assert bằng blocking code?

`StepVerifier` subscribe tới publisher, kiểm tra cả giá trị lẫn tín hiệu hoàn tất:

```java
StepVerifier.create(policy.canRead(user, "doc-a"))
    .expectNext(true)
    .verifyComplete();
```

Đây là **method snippet trong một test có biến `user`**, không phải code độc lập. Nó có lợi hơn `policy.canRead(...).block()` trong test vì kiểm tra được `onNext`/`onComplete` và có thể mở rộng để assert `onError`. Không đặt `block()` trong WebFlux event-loop; unit test `StepVerifier` không cần phá reactive pipeline.

## 8. Test Spring AOP method security bằng Reactor Context

Unit test bean riêng chưa chứng minh annotation `@PreAuthorize` **đã được Spring Security thực thi**. Cần thêm một test gọi **service do Spring container cấp**, trong khi có `Authentication` trong Reactor Context.

`src/test/java/com/example/reactivepolicy/DocumentMethodSecurityTest.java`:

```java
package com.example.reactivepolicy;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents;

    private Authentication authentication(String name, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Test
    void methodProxyGrantsAccessToOwner() {
        Mono<String> result = documents.readText("doc-a")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("alice", "ROLE_READER")
            ));

        StepVerifier.create(result)
            .expectNext("Alice private document")
            .verifyComplete();
    }

    @Test
    void methodProxyDeniesAccessToOtherOwner() {
        Mono<String> result = documents.readText("doc-a")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("bob", "ROLE_READER")
            ));

        StepVerifier.create(result)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void methodProxyGrantsAccessToAdmin() {
        Mono<String> result = documents.readText("doc-b")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("admin", "ROLE_ADMIN")
            ));

        StepVerifier.create(result)
            .expectNext("Bob private document")
            .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*DocumentMethodSecurityTest'
```

Giải thích quan trọng:

- `@SpringBootTest` dựng context và AOP method-security interceptors. `documents` là **bean được inject**, không phải `new DocumentService(...)`.
- `ReactiveSecurityContextHolder.withAuthentication(...)` tạo context **trong test**, cung cấp Authentication giả lập có kiểm soát.
- `contextWrite(...)` ở phía **downstream** của `documents.readText(...)` làm cho upstream publisher và authorization logic đọc được reactive SecurityContext trong subscription.
- Test thiếu quyền kỳ vọng `AccessDeniedException` (hoặc subtype) do method security tạo khi `Mono<Boolean>` phát `false`.
- Khi production phục vụ HTTP, Spring Security WebFlux đưa Authentication từ quá trình login/token verification vào Reactor Context; controller **không tự đặt authentication** để vượt quyền.

**Lưu ý về AOP proxy:** Nếu test chỉ `new DocumentService(new DocumentRepository())` rồi gọi `readText`, annotation `@PreAuthorize` **không được Spring AOP áp dụng**. Đó là lỗi test quan trọng. Đừng kết luận method security hỏng khi bạn không gọi qua Spring bean/proxy.

## 9. Integration test HTTP với WebTestClient

Kiểm tra cả authentication, HTTP rule và bean method policy bằng HTTP server khởi động trong test.

`src/test/java/com/example/reactivepolicy/DocumentHttpTest.java`:

```java
package com.example.reactivepolicy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DocumentHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void withoutCredentialReturns401() {
        client.get()
            .uri("/documents/doc-a")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadHerOwnDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "alice", "alice-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Alice private document");
    }

    @Test
    void bobCannotReadAlicesDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "bob", "bob-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bobCanReadHisOwnDocument() {
        client.get()
            .uri("/documents/doc-b")
            .headers(h -> h.setBasicAuth(
                "bob", "bob-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Bob private document");
    }

    @Test
    void adminCanReadExistingDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Alice private document");
    }

    @Test
    void unknownDocumentIsDeniedByPolicy() {
        client.get()
            .uri("/documents/not-found")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordDoesNotReachMethodPolicy() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*DocumentHttpTest'
```

Với Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*DocumentHttpTest'
```

Đây là 7 kiểm thử HTTP theo **kết quả dự kiến từ cấu hình mẫu**. Chúng chưa được chạy trong môi trường biên soạn bài. Nếu một dự án thêm authentication entry point khác, nhiều `SecurityWebFilterChain`, custom method exception handling hoặc khác Spring Security version, HTTP status cần đối chiếu với cấu hình thực tế.

**Điểm khác biệt của 3 tầng test:**

| Test | Kiểm tra | Không chứng minh |
| --- | --- | --- |
| `DocumentAccessPolicyTest` | Logic bean `Mono<Boolean>` độc lập | AOP/SpEL có chạy không |
| `DocumentMethodSecurityTest` | `@PreAuthorize` gọi bean thông qua Spring proxy và Reactor Context | HTTP authentication filter có chạy không |
| `DocumentHttpTest` | Basic authentication, HTTP authorization, method security và routing tích hợp | Bảo mật production với IdP/database/proxy thật |

Ba tầng này bổ sung nhau; chỉ test principal do mock tạo ra không đủ chứng minh HTTP credentials đã được kiểm chứng trong thực tế.

## 10. Bảng tín hiệu: true, false, empty và error

`Mono<Boolean>` có thể phát những tín hiệu sau:

| Publisher | Ý nghĩa khi dùng làm authorization expression | Có nên dùng trong policy kiểm ownership? |
| --- | --- | --- |
| `Mono.just(true)` | Cấp quyền theo policy | Có, khi đã xác minh đủ điều kiện |
| `Mono.just(false)` | Từ chối rõ ràng | **Có**, với không đủ quyền hoặc thiếu tài nguyên theo chính sách fail closed |
| `Mono.empty()` | Không phát Boolean, theo tài liệu method security có thể được xem là **abstain** | **Không nên** cho “không tìm thấy tài liệu” nếu yêu cầu từ chối mặc định |
| `Mono.error(exception)` | Policy thực thi thất bại hoặc gặp lỗi hạ tầng | Không cấp quyền; xử lý lỗi quan sát được, không đổi thành true |

Nếu repository trả empty cho tài liệu không tồn tại, ví dụ:

```java
return repository.findById(id)
    .map(document -> document.owner().equals(authentication.getName()))
    .defaultIfEmpty(false);
```

`defaultIfEmpty(false)` biến **absence** thành một quyết định deny rõ ràng. Ngược lại, nếu bỏ `defaultIfEmpty(false)`, bean có thể trả `Mono.empty()`; đó không đồng nghĩa với một Boolean `false`, nên tránh dựa vào cách interceptor xử lý abstention để thiết kế bảo mật tài nguyên.

### 10.1 Không biến lỗi database thành quyền cho phép

**Sai nguy hiểm:**

```java
return repository.findById(id)
    .map(document -> document.owner().equals(authentication.getName()))
    .onErrorReturn(true);
```

Đây là snippet cảnh báo **không nên dùng**. Nếu DB mất kết nối, một policy dạng này có thể cấp quyền cho người dùng **không được xác minh ownership**.

**Tốt hơn:** Giữ error được phát ra để request không trả nội dung, log và quan sát ở lớp hạ tầng; hoặc ánh xạ lỗi cụ thể sang quyết định từ chối **sau khi** đánh giá tác động của việc che lỗi. Không coi `onErrorReturn(false)` luôn là hoàn hảo: nó cũng có thể che sự cố đáng được trả 5xx và alert. Điểm bắt buộc là **không cấp quyền khi không xác minh được điều kiện**.

### 10.2 Không gộp Mono với SpEL boolean operator tùy tiện

Ví dụ **cần tránh vì semantics không rõ/không phù hợp**:

```java
@PreAuthorize("hasRole('READER') and @documentAccess.canRead(authentication, #p0)")
```

`hasRole` trả Boolean đồng bộ còn bean trả `Mono<Boolean>`. Không giả định SpEL sẽ tự chờ một publisher ở **bên trong** toán tử `and` như logic Java thông thường; một phép chuyển kiểu sang Boolean có thể thất bại tùy expression handling và phiên bản. Hãy để **kết quả reactive là kết quả cuối của expression** và kết hợp các điều kiện **bên trong bean** bằng reactive operators.

Ví dụ bean có thể kiểm role trước rồi tra repository:

```java
public Mono<Boolean> canRead(Authentication auth, String id) {
    if (auth == null || !auth.isAuthenticated()) {
        return Mono.just(false);
    }

    boolean reader = auth.getAuthorities().stream()
        .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
    boolean admin = auth.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    if (!reader && !admin) {
        return Mono.just(false);
    }

    return repository.findById(id)
        .map(doc -> admin || doc.owner().equals(auth.getName()))
        .defaultIfEmpty(false);
}
```

Đây là **đoạn method thay thế trong `DocumentAccessPolicy`**, không phải class độc lập. Nó minh họa việc trả `Mono.just(false)` sớm cho role không phù hợp, sau đó tra DB reactive. Logic cụ thể phụ thuộc chính sách: trong cấu hình demo gốc, owner được phép dù role nào, còn bản biến thể này yêu cầu READER hoặc ADMIN.

### 10.3 Mono<Boolean> có được dùng để kiểm tra điều kiện có I/O?

Có. Đây chính là trường hợp phù hợp cho reactive method security: `documentRepository.findById(id)` có thể là async database call, hoặc lời gọi dịch vụ quyền truy cập qua `WebClient` trả publisher. Điều kiện là **thực sự non-blocking**, có timeout/retry/circuit breaker phù hợp và không tạo side effects trong phép kiểm tra quyền.

Nếu I/O là **blocking** (JDBC legacy), đừng viết `Mono.just(blockingPermissionCheck())`; hàm blocking đã chạy **trước khi** Mono được tạo. Dùng reactive driver/client hoặc cô lập blocking vào scheduler thích hợp theo kiến trúc có kiểm soát.

## 11. Thay thế bean bằng Function<String, Mono<Boolean>>

Ngoài bean class `DocumentAccessPolicy`, Spring Security 6.5 minh họa `@Bean Function<T, Mono<Boolean>>` được gọi bằng `@functionName.apply(...)` trong `@PreAuthorize`.

Ví dụ cấu hình riêng sau cho phép đọc **document thuộc chính principal**, dùng `ReactiveSecurityContextHolder` để lấy Authentication từ Reactor Context:

```java
package com.example.reactivepolicy;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class FunctionPolicyExample {

    @Bean("ownsDocument")
    Function<String, Mono<Boolean>> ownsDocument(DocumentRepository repository) {
        return id -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth ->
                repository.findById(id)
                    .map(doc -> doc.owner().equals(auth.getName()))
            )
            .defaultIfEmpty(false);
    }
}
```

Sau đó trong method thuộc một Spring bean:

```java
@PreAuthorize("@ownsDocument.apply(#p0)")
public Mono<String> readOwnText(String id) {
    return repository.findById(id)
        .map(DocumentRecord::content);
}
```

Đây là **method snippet**, cần đặt trong service có field `repository` và import `@PreAuthorize`. Hai đoạn là phương án **minh họa thay thế**, không cần dùng đồng thời với `DocumentService.readText` chính. Điểm mạnh của kiểu function là chữ ký gọn và bám theo tài liệu chính thức; điểm khác là `FunctionPolicyExample` tự đọc security context thay vì nhận `Authentication` từ SpEL.

**Khi nào nên chọn cách nào?**

- `@documentAccess.canRead(authentication, #p0)`: thuận tiện để **unit test thuần Java** với Authentication cụ thể, dễ truyền principal và document ID.
- `@ownsDocument.apply(#p0)`: hữu ích nếu function chủ động dùng `ReactiveSecurityContextHolder`, nhưng unit test phải cấp Reactor Context; không có authentication thì publisher cần fail closed.
- `@authz.decide(#root)`: biến thể dùng `MethodSecurityExpressionOperations` theo hướng dẫn Spring Security, có thể giữ logic trong bean và truy cập security expression root. Phải import đúng type từ Spring Security và tránh phụ thuộc request state ngoài thiết kế.

Đừng lẫn lộn `@documentAccess` với annotation `@Component`. Dấu `@` bên trong SpEL **chỉ cách truy cập bean theo tên**, không tự biến một class bất kỳ thành bean.

## 12. Spring AOP: vì sao annotation có thể không chạy?

Một trong những lỗi khó phát hiện nhất là **self-invocation**: code trong một class gọi `this.readText(id)` nội bộ. Khi gọi nội bộ không qua Spring proxy, interceptor bảo vệ method có thể bị bỏ qua. Ví dụ:

```java
@Service
public class RiskyService {

    public Mono<String> outer(String id) {
        return this.inner(id); // self-invocation: bỏ qua proxy method security
    }

    @PreAuthorize("@documentAccess.canRead(authentication, #p0)")
    public Mono<String> inner(String id) {
        return Mono.just("sensitive");
    }
}
```

**Đây là class minh họa rủi ro**, cần import `Service`, `PreAuthorize`, `Mono`. Khi `outer` được gọi qua proxy, `outer` không có annotation; lệnh `this.inner(...)` có thể bypass interceptor của `inner`. Không sử dụng mẫu này để bảo vệ dữ liệu nhạy cảm.

**Cách sửa:** Đưa method có `@PreAuthorize` sang một `@Service` khác và inject bean đó vào caller, hoặc thiết kế interface/layer sao cho mọi external access đến dữ liệu đi qua **Spring-managed proxy**. Đảm bảo method public, bean được component scan, không tạo thủ công bằng `new`, và không dựa vào proxying private/final methods.

### 12.1 Reactive return type

Với Spring Security reactive method authorization, dùng `Mono<T>` / `Flux<T>` hoặc Publisher phù hợp ở method được bảo vệ; hạ tầng cần Reactor Context trong subscription.

Ví dụ đúng:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public Mono<DocumentRecord> findById(String id) {
    return repository.findById(id);
}
```

Đây là method snippet trong service. Đừng đổi thành:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public DocumentRecord findById(String id) {
    return repository.findById(id).block();
}
```

Mẫu thứ hai vừa chặn luồng vừa mất hợp đồng Publisher dự kiến; nó **không phải** cách áp dụng an toàn cho Spring Security reactive.

### 12.2 Reactor Context khác ThreadLocal

`ReactiveSecurityContextHolder` dùng **Reactor Context** gắn với subscription, không dựa vào `ThreadLocal` của `SecurityContextHolder` theo kiểu Servlet. Reactor operators như `map`, `flatMap` và `publishOn` trong cùng reactive chain được thiết kế để giữ context đúng phạm vi. Ngược lại, gọi `subscribe()` thủ công, tách sang callback bất kỳ hoặc `CompletableFuture` mà không có cơ chế context propagation rõ ràng có thể làm mất authentication.

Trong HTTP request WebFlux bình thường, Spring Security tạo/khôi phục context cho request. Trong unit test dùng `StepVerifier`, ta chủ động cấp context với `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` để mô phỏng một user đã được xác thực.

## 13. Phân biệt pre-authorization và post-authorization

`@PreAuthorize` quyết định **trước khi method được thực hiện**: phù hợp khi bạn có thể quyết định từ tham số và lookup quyền trước khi đọc/ghi dữ liệu.

`@PostAuthorize` đánh giá sau khi method đã trả kết quả, hữu ích nếu policy cần chính object result, nhưng với reactive stream cần hiểu chính xác cách method-security interceptor xử lý publisher/result và phiên bản hỗ trợ. Một dữ liệu đã được tính toán/truy vấn trước lúc quyết định có thể tạo side effect hoặc tốn tài nguyên; đừng mặc định rằng “chặn trả dữ liệu sau” sẽ hoàn tác side effect trong method.

**Trong ví dụ tài liệu, `@PreAuthorize` tốt hơn** vì có thể xác minh owner/role bằng repo trước khi cho phép `readText`. Với thao tác **ghi dữ liệu**, chỉ pre-check có thể chưa đủ do race condition (TOCTOU): quyền có thể thay đổi giữa lần kiểm và lần update. Cân nhắc transaction, row-level security, câu lệnh update có điều kiện owner/tenant, optimistic locking hoặc kiểm tra policy ngay ở lệnh ghi.

### 13.1 Không đặt kiểm quyền ở mỗi Controller rồi quên service

Nếu một service đọc dữ liệu nhạy cảm được gọi từ cả REST controller, GraphQL resolver, message consumer hoặc job xử lý batch, chỉ dùng HTTP route matcher sẽ không bảo vệ các đường gọi khác. Đặt policy tại **service boundary** giúp tạo defense in depth. Nhưng vẫn phải cấp một **Authentication đáng tin cậy trong context** cho các workflow ngoài HTTP nếu chúng được phép thực hiện tác vụ; không “đóng giả admin” từ input tự do.

## 14. Xử lý lỗi, latency và quan sát

### 14.1 Fail closed nhưng phân biệt lỗi thật

Khi repository không tìm thấy document, demo chọn `Mono.just(false)` bằng `defaultIfEmpty(false)`, để policy từ chối. Khi repository **bị lỗi thực sự** (mất DB, timeout), nên để error lan ra và được xử lý ở lớp phù hợp mà **không cấp quyền**; không biến lỗi thành `true` để “tránh gián đoạn”.

Trong production có thể chọn HTTP 503 thay vì 403 khi không thể kiểm chứng quyền vì hạ tầng unavailable, miễn là **không trả dữ liệu**. Xác định policy của hệ thống: tách “user không có quyền” với “không thể đánh giá quyền”, nhưng cả hai phải **không phát tán tài nguyên nhạy cảm**.

### 14.2 Timeout, retry và cache

Nếu policy cần query DB hoặc external policy service:

- Đặt timeout hữu hạn và instrumentation cho thời gian đánh giá quyền.
- Retry chỉ lỗi có thể phục hồi và giới hạn số lần; không retry invalid authentication/denied decision.
- Cache quyết định quyền cần key theo **principal, tenant, resource ID, action và phiên bản policy**; đừng cache một Boolean theo document ID rồi tái sử dụng cho user khác.
- Có chính sách invalidation khi owner/roles/tenant membership thay đổi.
- Không log password, token, chi tiết bí mật hoặc toàn bộ document content.
- Với danh sách tài liệu, cân nhắc batch authorization thay vì N lần lookup dẫn đến N+1 queries.

### 14.3 Tránh leak dữ liệu qua status hoặc timing

Một request không được phép xem document cũng có thể vô tình tiết lộ sự tồn tại tài liệu qua phân biệt 403 và 404, hoặc thời gian phản hồi. Demo trả 403 cho tài liệu không tồn tại nhằm đơn giản hóa fail-closed; đây là lựa chọn **có chủ đích**, không phải quy tắc bắt buộc của mọi API. Với API thật, cần quyết định cách phản hồi 404/403 nhất quán với privacy policy và threat model.

## 15. Bảng lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `@EnableMethodSecurity` của Servlet thay cho reactive | Bean trả `Mono<Boolean>` không được xử lý như kỳ vọng | Bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` trong WebFlux |
| Dùng cấu hình reactive method security kiểu cũ chỉ hỗ trợ Boolean | SpEL trả publisher không được diễn giải đúng | Dùng hạ tầng AuthorizationManager của Spring Security 6.x |
| `@PreAuthorize("@documentAccess.canRead(...)")` nhưng bean tên khác | SpEL không tìm bean | Đặt `@Component("documentAccess")` hoặc `@Bean("documentAccess")` |
| SpEL `#id` nhưng build không giữ tên tham số | `id` null/không resolve | Dùng `#p0` hoặc cấu hình parameter name discovery |
| Bean trả `Mono.empty()` khi không có document | Abstain khác deny rõ ràng | `defaultIfEmpty(false)` |
| Policy gọi `block()` | Chặn event-loop, context bị sai | Trả `Mono<Boolean>` và dùng reactive operators |
| Gọi `subscribe()` trong bean | Spring Security không nhận decision đúng lifecycle | Trả publisher để framework subscribe |
| Gọi method nội bộ bằng `this.method()` | Bỏ qua Spring AOP interceptor | Đi qua bean/proxy hoặc tách service |
| Tự `new DocumentService(...)` | Không có Spring proxy | Inject bean qua constructor |
| Dùng user/role từ query/header chưa xác minh | Bypass authentication/privilege escalation | Chỉ dùng Authentication đã được provider xác minh |
| `onErrorReturn(true)` trong policy | DB lỗi trở thành quyền cho phép | Fail closed, propagate/handle errors an toàn |
| Test bean trực tiếp rồi suy ra annotation hoạt động | Bỏ qua AOP/SpEL | Thêm `@SpringBootTest` gọi injected service |
| Chỉ test user được phép | Không phát hiện được cross-owner leak | Thêm negative tests cho user khác |
| HTTP layer `permitAll` và không bật method security | Controller có thể trả dữ liệu trực tiếp | Kiểm tra HTTP policy và method security đều active |
| Có quyền theo document ID nhưng thiếu tenant ID | Cross-tenant access | Kiểm tra composite ownership/tenant trên dữ liệu thật |
| Cache Boolean policy theo resource ID בד | Kết quả của Alice áp dụng sai cho Bob | Cache theo principal/tenant/action/policy version |
| Chỉ pre-check rồi ghi dữ liệu không kiểm tra lại | TOCTOU/race condition | Dùng update có điều kiện/transaction/DB constraints |
| Tưởng Spring AOP proxy bảo vệ private/final/self-call | Interceptor không chạy | Thiết kế public service boundary và test proxy |

## 16. Bài tập tự kiểm tra

**Câu 1.** Vì sao `@PreAuthorize("hasRole('READER')")` chưa đủ để bảo vệ `GET /documents/{id}`?

**Đáp:** Role chỉ nói người dùng có quyền READER tổng quát, không chứng minh họ sở hữu **document ID cụ thể**. Bean policy tra dữ liệu reactive có thể so owner/tenant với principal trước khi cho phép.

**Câu 2.** `@documentAccess` trong SpEL là Java annotation?

**Đáp:** Không. Đây là cú pháp **Spring bean reference** trong biểu thức SpEL. Bean phải có tên `documentAccess` được Spring quản lý.

**Câu 3.** Nếu repository trả `Mono.empty()` cho ID không tồn tại, phương án an toàn cho ownership check là gì?

**Đáp:** `defaultIfEmpty(false)` để trả **`Mono.just(false)`**. Đừng dựa vào semantics abstain của empty để xử lý quyền nhạy cảm.

**Câu 4.** Tại sao `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` được nêu rõ?

**Đáp:** Cơ chế AuthorizationManager-based reactive method security hỗ trợ kết quả biểu thức Boolean hoặc `Mono<Boolean>`; đường đi cũ có những giới hạn biểu thức đồng bộ. Cần bật và test tương thích với phiên bản Spring Security dự án.

**Câu 5.** Nếu `DocumentAccessPolicy.canRead` trả `Mono.just(false)`, Spring Security có gọi tiếp `DocumentService.readText` không?

**Đáp:** Không khi method security hoạt động đúng; before-method authorization từ chối bằng exception. HTTP caller đã xác thực thường nhận 403.

**Câu 6.** Lệnh `this.readText("doc-a")` trong cùng một class có chắc đi qua method-security proxy không?

**Đáp:** Không. Self-invocation có thể bỏ qua proxy. Gọi qua Spring-managed bean/proxy hoặc tách method được bảo vệ sang service khác.

**Câu 7.** Unit test `policy.canRead(...)` bằng StepVerifier đều pass, có đủ chứng minh bảo mật HTTP chưa?

**Đáp:** Chưa. Cần test Spring proxy `@PreAuthorize` và HTTP filter/credential bằng WebTestClient để xác minh cả ba lớp.

**Câu 8.** Có nên ghép `hasRole('READER') and @policy.check(...)` khi `check` trả `Mono<Boolean>` không?

**Đáp:** Tránh phụ thuộc khả năng SpEL tự giải quyết nested publisher; nên kết hợp điều kiện trong bean, để kết quả reactive là **kết quả cuối** của authorization expression.

**Câu 9.** Một user có `ROLE_ADMIN` truy cập ID không tồn tại, policy demo có cho phép không?

**Đáp:** Không, do `findById` empty và `defaultIfEmpty(false)`. Policy này yêu cầu tài liệu tồn tại **trước** khi xét owner/admin.

**Câu 10.** Nếu database bị outage, có nên `onErrorReturn(true)` để hệ thống vẫn chạy không?

**Đáp:** Tuyệt đối không. Khi chưa kiểm chứng quyền không được cho phép truy cập. Có thể trả lỗi server/503 và cảnh báo vận hành, nhưng không cấp quyền cho dữ liệu nhạy cảm.

## 17. Checklist triển khai

- [ ] Dùng Spring WebFlux reactive thật sự, không vô tình chạy MVC/Servlet.
- [ ] Bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` cho mẫu Spring Security 6.x.
- [ ] Method được bảo vệ nằm trong **Spring-managed public service bean**, trả `Mono<T>`/`Flux<T>`.
- [ ] Annotation tham chiếu đúng bean name và method signature: `@documentAccess.canRead(authentication, #p0)`.
- [ ] Policy bean trả **`Mono<Boolean>`**, không `block()` hoặc tự `subscribe()`.
- [ ] Dữ liệu người dùng/role trong `Authentication` đã được authentication provider xác thực.
- [ ] Không có resource hoặc thiếu quyền → quyết định `false` rõ ràng, không vô tình trả empty.
- [ ] Database error không được ánh xạ thành `true`.
- [ ] HTTP `authorizeExchange` vẫn yêu cầu authentication/role phù hợp như lớp phòng vệ thứ nhất.
- [ ] Có test bean đơn vị, test AOP method security qua Spring proxy và test HTTP end-to-end.
- [ ] Negative tests bao gồm cross-owner, anonymous, ID không tồn tại, role thiếu quyền và credential sai.
- [ ] Kiểm tra self-invocation, parameter name lookup, async context propagation, cache và timeout.
- [ ] Với nghiệp vụ ghi, kiểm tra lại quyền tại transaction/update để tránh TOCTOU.
- [ ] Bảo vệ secrets, TLS, audit logs và không rò rỉ thông tin tài liệu qua status hoặc exception.

**Ghi nhớ:** Spring Security reactive cho phép bean được gọi từ `@PreAuthorize` trả **`Mono<Boolean>`** khi dùng **AuthorizationManager-based reactive method security**. Điều đó giúp thực hiện permission check cần database/network một cách **bất đồng bộ, không chặn thread**. Hãy trả `true` khi đủ quyền, `false` khi thiếu quyền/tài nguyên không tồn tại, xử lý `empty` và `error` có chủ đích, và **kiểm thử qua Spring proxy** để chắc annotation thật sự có hiệu lực.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — EnableReactiveMethodSecurity, Method Security Reactive Boolean Expression, Using a Custom Bean in SpEL](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity annotation Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 — ReactiveSecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Framework — Spring AOP proxy semantics](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
