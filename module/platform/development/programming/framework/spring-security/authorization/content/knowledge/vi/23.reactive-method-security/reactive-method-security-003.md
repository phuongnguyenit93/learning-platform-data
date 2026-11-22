# @PreAuthorize, @PostAuthorize và giới hạn hỗ trợ từng annotation trong Reactive Method Security

## 1. Vấn đề: quyền phải được kiểm tra ở thời điểm nào?

Một ứng dụng Spring WebFlux có các nghiệp vụ:

- Đọc tài liệu thuộc một tenant.
- Đọc một tài liệu có owner hoặc được chia sẻ.
- Liệt kê tài liệu mà người dùng thực sự được xem.
- Đổi tiêu đề tài liệu nếu có quyền EDIT.
- Xuất dữ liệu, gửi thông báo hoặc ghi database.

Trên controller, route `GET /api/tenants/t1/docs/101` có thể được bảo vệ bằng `authenticated()`. Điều đó **chưa** chứng minh Alice được xem Document#101. Bản ghi có thể thuộc tenant khác, chủ sở hữu khác hoặc đang bị khóa.

**Reactive Method Security** cho phép Spring kiểm tra tại **method của Spring-managed bean**:

```java
@PreAuthorize("@docGuard.canEnter(authentication, #tenant, #id)")
@PostAuthorize("@docGuard.canReadReturned(authentication, returnObject)")
public Mono<Doc> read(
        @P("tenant") String tenant, @P("id") Long id) {
    return repository.findById(id);
}
```

Đoạn trên **minh họa chính sách**, chưa phải file Java độc lập. Nó có hai câu hỏi khác nhau:

1. **Trước khi cho phép xử lý**: người gọi có quyền vào tenant, document ID và trạng thái phù hợp không? `@PreAuthorize`.
2. **Sau khi có giá trị kết quả**: tài liệu thực sự được trả về có phù hợp owner/share hay không? `@PostAuthorize`.

Cách thứ hai hữu ích để phòng lộ dữ liệu trong **read-only method**, nhưng nguy hiểm nếu dùng để “bảo vệ” một mutation vốn đã ghi DB, gửi email hoặc gọi API ngoài trước khi bị từ chối.

### Mục tiêu học tập

Sau bài này, bạn có thể:
- Kích hoạt `@EnableReactiveMethodSecurity` đúng với Spring Security 6.5.x.
- Giải thích **Reactor Context, subscription và proxy** trong kiểm tra quyền reactive.
- Phân biệt thời điểm và ngữ nghĩa `@PreAuthorize` với `@PostAuthorize`.
- Nhận biết ranh giới hỗ trợ của `@PreFilter`, `@PostFilter`, `@Secured`, JSR-250 và kiểu return values.
- Dùng biểu thức SpEL với `Boolean` hoặc `Mono<Boolean>` đúng khả năng của `AuthorizationManager`.
- Chặn mutation **trước tác dụng phụ**, không dùng post-check như một cơ chế rollback.
- Viết tests bằng `WebTestClient` và `StepVerifier`; kiểm tra 401/403, tenant/owner/share và không ghi khi pre-check deny.
- Tránh đồng nhất method authorization với HTTP authorization hoặc filtering dữ liệu trước phân trang.

## 2. Method Security trong hệ Reactive khác Servlet thế nào?

Spring Security có hai nhánh cấu hình mà người học không nên trộn lẫn.

| WebFlux/Reactive | Servlet/MVC | Ý nghĩa |
|---|---|---|
| `@EnableReactiveMethodSecurity` | `@EnableMethodSecurity` | Kích hoạt các method interceptors tương ứng |
| `ServerHttpSecurity` | `HttpSecurity` | Cấu hình HTTP security |
| `SecurityWebFilterChain` | `SecurityFilterChain` | HTTP filter chain |
| `ReactiveSecurityContextHolder` | `SecurityContextHolder` | Lấy context an toàn trên reactive pipeline |
| `Mono<T>` và `Flux<T>` | Thường là giá trị đồng bộ `T`, `List<T>` | Phương thức/giá trị phù hợp reactive API |
| `AuthorizationManagerBeforeReactiveMethodInterceptor` | Before-method interceptor servlet | Authorization trước method |
| `AuthorizationManagerAfterReactiveMethodInterceptor` | After-method interceptor servlet | Authorization theo kết quả |

Trên **Reactor**, một publisher là mô tả xử lý có thể được subscribe sau, có thể chạy bất đồng bộ. Không được giả định `ThreadLocal SecurityContextHolder` luôn giữ đúng principal khi pipeline chuyển scheduler/thread.

Spring Security tích hợp security context trong **Reactor Context** qua `ReactiveSecurityContextHolder`. HTTP WebFlux security thiết lập context của user đã xác thực cho request; trong kiểm thử service trực tiếp, `@WithMockUser` với reactive testing support hoặc `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` cung cấp context phù hợp.

### 2.1. Tại sao nên trả Mono/Flux?

Tài liệu Spring Security 6.5 nêu với thiết lập reactive thông dụng, method bảo vệ phải trả `org.reactivestreams.Publisher` như `Mono` hoặc `Flux` để có thể phối hợp với Reactor Context. Nhánh `AuthorizationManager` hỗ trợ các return types reactive khác, bao gồm Kotlin coroutines trong cấu hình thích hợp, nhưng **không thể tự suy luận** rằng mọi method trả giá trị đồng bộ `Doc`, `void`, `CompletableFuture` hoặc `suspend` đều có cùng hành vi.

Đối với Java 17 WebFlux, **mẫu đáng tin để bắt đầu** là:
- `Mono<Doc>` cho read một tài liệu.
- `Flux<Doc>` cho danh sách.
- `Mono<Void>`, `Mono<Doc>` hoặc `Mono<Result>` cho mutation đã được pre-check và được bảo vệ trong reactive pipeline.

Không khai báo một method đồng bộ `void delete(...)` rồi kỳ vọng `@PostAuthorize` kiểm tra lại sau một reactive operation không chờ kết quả.

### 2.2. Kích hoạt annotation nào?

Với Spring Security 6.5:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {
}
```

Đây là đoạn cấu hình minh họa; ví dụ đầy đủ nằm ở phần 7.

Từ Spring Security 6.0, `@EnableReactiveMethodSecurity` mặc định sử dụng `useAuthorizationManager=true`. Vì vậy không cần tự viết `useAuthorizationManager=true` để “bật” chế độ này ở 6.5. Cơ chế mới dùng Spring AOP và các interceptors cho pre/post authorization và filtering.

**Chỉ thêm `spring-boot-starter-security` chưa bật Method Security**. Phải bật bằng annotation/config và kiểm tra bean thực sự do Spring quản lý.

## 3. @PreAuthorize: kiểm tra quyền trước khi target method được thực thi

`@PreAuthorize` sử dụng **SpEL** để ra quyết định dựa trên principal, method arguments, authorities và logic bean. Ví dụ:

```java
@PreAuthorize("hasAuthority('docs:edit')")
public Mono<Doc> rename(Long id, String newTitle) {
    return repository.rename(id, newTitle);
}
```

Đây là ví dụ minh họa. Nó kiểm tra một authority chung nhưng **chưa** kiểm tra object owner/tenant, nên chưa đủ bảo vệ production.

Một rule đầy đủ hơn:

```java
@PreAuthorize(
    "@docGuard.canEdit(authentication, #tenant, #id)"
)
public Mono<Doc> rename(
        @P("tenant") String tenant,
        @P("id") Long id,
        String title) {
    // ...
}
```

`@P` giúp Spring Security lấy đúng `#tenant`, `#id` ngay cả khi compiler không lưu tên parameter. `authentication` là Authentication đã được Spring Security xác thực; không tự tạo từ `X-User` hay `X-Role` của client.

### 3.1. Pre-check an toàn với mutation

Mục tiêu là người không có quyền **không thể đi tới logic ghi**:
 
```text
Subscriber bắt đầu request
  ├── Reactive Method Security: @PreAuthorize
  │      ├── false/error -> AccessDeniedException
  │      └── true
  └── Target publisher
         └── Kiểm tra điều kiện DML và mutation
```

Phía dưới, `DocGuard.canEdit(...)` trả `Mono<Boolean>` từ một `Mono.fromSupplier(...)` (giản lược dữ liệu demo). Điều này cho thấy Spring Security 6.5 hỗ trợ reactive boolean decision từ một bean SpEL trong cơ chế `AuthorizationManager`.

Ví dụ độc lập trong ý nghĩa biểu thức:

```java
@PreAuthorize("@reactivePolicy.allowed(authentication, #id)")
Mono<Doc> update(@P("id") Long id) {
    return repository.update(id);
}
```

Nếu bean trả `Mono<Boolean>` thì authorization có thể kết hợp vào pipeline. Không gọi `block()` trong bean policy để đợi JDBC/HTTP vì điều đó chặn event-loop và có thể gây deadlock hoặc giảm throughput.

### 3.2. Pre-check chưa giải quyết hoàn toàn TOCTOU

Nếu quyền owner/tenant thay đổi sau khi được check mà trước lúc UPDATE, một request có thể chạy với quyết định cũ. Spring Security annotation **không tạo transaction nguyên tử** với storage. Giải pháp phù hợp phụ thuộc nghiệp vụ:
- Dùng SQL `UPDATE ... WHERE id=? AND tenant_id=? AND owner_id=?` hoặc permission predicate.
- Kiểm tra affected row count và optimistic version.
- Row locks/transaction isolation nếu cần.
- Tái đánh giá quyền tại thời điểm ghi trong transaction.
- Với external effects, dùng transactional outbox hoặc workflow có bù trừ.

Kiểm tra ở method và guard tại data layer là **hai lớp bảo vệ**, không thay thế nhau.

## 4. @PostAuthorize: kiểm tra giá trị đầu ra, nhưng quá muộn cho side effects

`@PostAuthorize` kiểm tra kết quả của method, thường dùng biến SpEL `returnObject`. Ví dụ:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Doc> readOwned(Long id) {
    return repository.findById(id);
}
```

Đây là mẫu minh họa. Với `Doc` có getter/property `owner`, expression có thể quyết định liệu principal có là owner của object trả về hay không. Trong ví dụ runnable, thay bằng bean policy `@docGuard.canReadReturned(authentication, returnObject)` để hỗ trợ cả owner, share và tenant binding.

### 4.1. Khi nào hữu ích?

- Method chỉ đọc bản ghi và trả `Mono<Doc>`.
- Không có external side effect khi làm read.
- Cần kiểm tra thuộc tính **thực tế của kết quả trả về**: owner, visibility, state, tenant.
- Tránh dựa duy nhất vào tài nguyên ID người dùng cung cấp.

Kết quả denied **không được trả ra caller**, thông thường subscriber nhận `AccessDeniedException`; ở WebFlux HTTP, exception translation có thể trả 403 nếu user đã xác thực.

### 4.2. Nguy hiểm trên mutation

```java
// PHẢN VÍ DỤ: không dùng post-check để bảo vệ thao tác ghi.
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Doc> transferOwner(Long id, String newOwner) {
    return repository.changeOwner(id, newOwner);
}
```

Dù post-check từ chối kết quả, DB update có thể **đã thực hiện**. Reactive sequencing không tự rollback network call, message publish hoặc database transaction chỉ vì response bị deny sau đó. Do đó:
- Dùng `@PreAuthorize` trên write/delete/export/approve.
- Dùng tenant-/owner-qualified transaction và update.
- Không cho rằng một HTTP 403 tương đương “không có gì đã xảy ra”.
- Với GET cũng tránh đọc external secrets hoặc phát events nhạy cảm **trước** post-check.

### 4.3. @PostAuthorize không phải bộ lọc cho Flux

`@PostAuthorize` trả lời câu hỏi “giá trị/method result này có được trả ra không?”. Nó không phải một mô hình pagination hay row-level filtering cho mọi record trong một `Flux` lớn. Nếu API trả danh sách nhiều tài liệu với owners khác nhau, sử dụng:
- Authorization trong repository/query trước phân trang.
- Trong demo nhỏ, `Flux.filter(...)` dựa trên principal từ Reactor Context.
- Nếu chọn `@PostFilter`, phải xác minh loại kết quả và khả năng hỗ trợ của version đang dùng, kiểm thử đầy đủ semantics.

Không dùng `@PostAuthorize("true")` để che lỗi policy trên một method đã ghi rồi.

## 5. Giới hạn hỗ trợ từng annotation trong Reactive Method Security 6.5

**Không đúng** nếu nói WebFlux “chỉ có `@PreAuthorize`, không có `@PostAuthorize` hoặc filtering”. Trong chế độ `AuthorizationManager`, Spring Security 6.5 công bố các reactive interceptors cho cả bốn loại. Tuy nhiên, **được cung cấp interceptor** không đồng nghĩa mọi shape dữ liệu, collection, stream hay method signature đều hoạt động giống Servlet.

| Annotation | Thời điểm | Hỗ trợ/cách dùng ở Spring Security 6.5 | Giới hạn cần nhớ |
|---|---|---|---|
| `@PreAuthorize` | Trước target method | Có, SpEL với role/authority/params/bean; bean có thể trả `Boolean` hoặc `Mono<Boolean>` khi dùng AuthorizationManager | Phải được Spring AOP intercept; không `block()`; không thay guarded write |
| `@PostAuthorize` | Sau khi có kết quả | Có, diễn giải `returnObject`, phù hợp với `Mono<T>` read-only | Không ngăn tác dụng phụ đã thực hiện; không phải per-item paging |
| `@PreFilter` | Trước khi đưa arguments vào method | Có reactive filtering interceptor ở chế độ AuthorizationManager | Phụ thuộc kiểu tham số; tham số Collection cần hỗ trợ remove, không tự là arbitrary `Flux`; tránh immutable collection |
| `@PostFilter` | Trên kết quả sau invocation | Có reactive filtering interceptor ở chế độ AuthorizationManager | Không nên lọc dữ liệu lớn **sau** khi query/paging; xác minh kiểu trả về và semantics bằng integration tests |
| `@Secured` | Kiểm tra role theo annotation cũ | Có trong hệ method security nhưng là cơ chế/kiểu cấu hình riêng, không phải lựa chọn chính trong bài này | Không coi tự tương đương `@PreAuthorize` hoặc assume bật mặc định; thử khi dùng legacy |
| `@RolesAllowed`/`@PermitAll`/`@DenyAll` | JSR-250 style | Reactive AuthorizationManager docs nêu tích hợp JSR-250 | Phải bảo đảm đúng config/dependency/vùng đặt annotation và test actual advisor |
| `@EnableMethodSecurity` | Kích hoạt Servlet-style method interceptors | **Không phải annotation chọn cho demo reactive này** | Dùng `@EnableReactiveMethodSecurity` và context reactive |
| `@EnableReactiveMethodSecurity` | Cấu hình | Bật reactive interceptors; `useAuthorizationManager` mặc định true trong 6.x | Phải có Spring-managed proxy; cần method/return shape phù hợp |

### 5.1. PreFilter có những ràng buộc khác PostFilter

Theo API của `@PreFilter`, tham số được lọc thường là một **Java Collection có khả năng remove**. Một `List.of(...)` immutable có thể gây lỗi khi lọc; mảng không được hỗ trợ bởi contract classic `@PreFilter`. Nếu method có nhiều collection arguments, cần chỉ định `filterTarget` và dùng tên tham số có thể được resolve.

Mẫu kiến trúc (cần test trên phiên bản cụ thể):

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public Mono<Integer> importOwned(
        @P("documents") java.util.List<Doc> documents) {
    return Mono.just(documents.size());
}
```

**Chỉ là ví dụ annotation**, không thuộc demo runnable vì cần imports và `Doc`. Nó có thể loại phần tử không được phép trước khi method xử lý, nhưng **lọc silently** có khi không phù hợp với batch update nghiệp vụ: an toàn hơn là validate tất cả IDs, báo chính xác record bị từ chối và thực hiện transaction theo policy rõ.

### 5.2. PostFilter khác PostAuthorize

`@PostFilter` dùng `filterObject` để đánh giá từng phần tử khi shape được hỗ trợ, còn `@PostAuthorize` dùng `returnObject` để đánh giá method result. Ví dụ minh họa:

```java
@PostFilter("filterObject.owner == authentication.name")
public Flux<Doc> listOwned() {
    return repository.findAll();
}
```

Đây là **mẫu khái niệm**, không mặc định coi nó là giải pháp sản xuất cho mọi reactive repository. Để chạy, cần kiểm chứng behavior với chính Spring Security version, return type và test case. Kể cả có lọc được, query `findAll()` vẫn đọc mọi tenant và có thể rò total count/timing, gây N+1 và phân trang sai. Với dữ liệu lớn, **lọc bằng tenant/permission predicates tại database trước paging** vẫn là hướng an toàn hơn.

### 5.3. Legacy và version-specific configuration

Tài liệu chính thức mô tả `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` từ Spring Security 5.8 và ghi rằng 6.0+ mặc định true. Nếu dự án còn 5.x legacy, kiểm tra riêng cấu hình, interceptor và khả năng expression kết quả reactive.

`@Secured` và JSR-250 không thay thế mọi tính năng của `@PreAuthorize`; biểu thức owner/tenant/resource-based thường nên dùng policy bean với `@PreAuthorize`. Không tự suy luận chỉ cần thêm annotation lên interface là Spring AOP luôn intercept trong mọi cấu hình; nhất là khi class final, self-invocation, proxy mode và Kotlin final classes.

## 6. Ngữ nghĩa reactive: subscribe, Reactor Context và ngoại lệ

### 6.1. Thời điểm thực thi

`Mono.defer(...)` mô tả một đơn vị công việc được thực hiện khi subscriber subscribe. Với reactive method interceptor, Spring Security có thể điều phối authorization trong publisher thay vì một check blocking bên ngoài.

```text
HTTP request ─> WebFlux Authentication
                │
                └── Reactor Context
                      │
Subscriber ───────────┤
                      v
               @PreAuthorize
                   │
               ALLOW/DENY
                   │ allow
                   v
             Mono.defer(...) / service logic
                   │
               value Doc
                   │
               @PostAuthorize
                   │
              ALLOW/DENY
                   │ allow
                   v
              HTTP body to client
```

Đây là **mô hình hành vi**. Đừng coi thời điểm gọi Java method và thời điểm subscribe là cùng một việc. Đặc biệt không làm side effect eager trước khi tạo publisher:

```java
// PHẢN VÍ DỤ: ghi đồng bộ/eager trước khi trả Mono.
@PreAuthorize("hasAuthority('docs:edit')")
public Mono<Void> unsafe(Long id) {
    someBlockingRepository.deleteById(id);
    return Mono.empty();
}
```

Dùng `Mono.defer` và reactive repository/transaction guard phù hợp. Một annotation không tạo phép màu rollback khi code có hành vi eager không tương thích.

### 6.2. SecurityContextHolder vs ReactiveSecurityContextHolder

Trong imperative servlet code, `SecurityContextHolder` thường hoạt động nhờ ThreadLocal. WebFlux có thể chuyển thread trong một pipeline, nên ưu tiên:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMapMany(authentication ->
        repository.findVisibleTo(authentication.getName()));
```

Đây là đoạn minh họa (cần bean repository và imports). Spring Security quản lý Reactor Context trong HTTP pipeline. Khi gọi method từ job, reactive tests hoặc non-HTTP entry point, cần chủ động tạo/propagate security context đã xác thực; không tự giả mạo principal từ request body.

### 6.3. Ngữ nghĩa empty và null

- `Mono.empty()` là không emit giá trị; nhiều `@PostAuthorize` expressions kiểm tra `returnObject` chỉ thực sự có ý nghĩa khi publisher có value. Không dùng empty để “bypass deny” vì bảo vệ resource thuộc trách nhiệm của pre-check và service policy.
- `Mono.error(...)` lan lỗi về subscriber; không biến error thành allow bằng `onErrorResume(e -> Mono.just(secret))`.
- Bean authorization trả `Mono.empty()` có thể mang ý nghĩa **abstain** tùy manager/combiner. Với tài nguyên nhạy cảm, thiết kế **deny khi không có quyết định cho phép rõ**.
- Nếu expression bean gọi HTTP/DB, response null, timeout hoặc invalid data phải có policy fail-closed và bounded timeout.
- Đừng dùng `block()` trong WebFlux event-loop để lấy quyết định cho một reactive annotation.

## 7. Dự án Java 17/Spring Boot 3.5.6 kiểm chứng @PreAuthorize và @PostAuthorize

Dự án độc lập dùng Spring WebFlux, Spring Security 6.5.x do Spring Boot 3.5.6 quản lý, một kho document trong RAM, policy bean, service trả `Mono`/`Flux` và tests bằng WebTestClient/StepVerifier. Không dùng JPA/blocking DB để tránh đánh tráo reactive semantics. Phần production sẽ nêu cách chuyển sang R2DBC.

### 7.1. Cây thư mục

```text
reactive-method-security-demo/
  pom.xml
  src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    SecurityConfig.java
    Doc.java
    DocCatalog.java
    DocGuard.java
    DocService.java
    DocController.java
  src/test/java/com/example/reactiveauth/
    ReactiveMethodSecurityTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-method-security-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

**Quan trọng:** demo không thêm `spring-boot-starter-web` (Servlet/MVC). Khi có cả hai starters, Spring Boot có thể chọn stack không như dự định. `spring-security-test` cung cấp `mockUser`/`csrf`; `reactor-test` cung cấp `StepVerifier`.

### 7.3. Main application

**`src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java`**

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
```

### 7.4. SecurityConfig

**`src/main/java/com/example/reactiveauth/SecurityConfig.java`**

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain webFluxChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/tenants/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityWebFilterChain` chỉ bảo đảm người dùng đã đăng nhập trên `/api/tenants/**` và deny những route HTTP còn lại. **Object-level checks** do `DocService` thực hiện. Đặt cả hai để minh họa defense-in-depth, không suy luận rằng request authenticated được quyền đọc mọi document.

Demo không cần khai báo user/password thật vì các integration tests tạo principal thông qua `mockUser(...)`. Nếu chạy ứng dụng độc lập với `mvn spring-boot:run`, Spring Boot có thể phát một password development do auto-configuration; đó không phải cơ chế cấp quyền production.

### 7.5. Doc model

**`src/main/java/com/example/reactiveauth/Doc.java`**

```java
package com.example.reactiveauth;

public record Doc(
        Long id,
        String tenant,
        String owner,
        String state,
        String title) {}
```

Đây là record Java 17. Ví dụ dùng bean `@docGuard` để xét `returnObject` nên không phụ thuộc vào việc SpEL diễn giải getter của record ra sao.

### 7.6. DocCatalog — dữ liệu canonical trong RAM

**`src/main/java/com/example/reactiveauth/DocCatalog.java`**

```java
package com.example.reactiveauth;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class DocCatalog {

    private final ConcurrentMap<Long, Doc> docs =
        new ConcurrentHashMap<>();

    private final Map<String, Set<String>> memberships = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> admins = Set.of(
        "t1:manager"
    );

    private final Set<String> viewers = Set.of(
        "101:bob"
    );

    private final AtomicInteger reads = new AtomicInteger();
    private final AtomicInteger writes = new AtomicInteger();

    public DocCatalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        docs.put(101L, new Doc(
            101L, "t1", "alice", "ACTIVE", "Owner memo"));
        docs.put(102L, new Doc(
            102L, "t1", "alice", "ACTIVE", "Project notes"));
        docs.put(103L, new Doc(
            103L, "t1", "manager", "ACTIVE", "Manager secret"));
        docs.put(104L, new Doc(
            104L, "t1", "alice", "ARCHIVED", "Old draft"));
        docs.put(201L, new Doc(
            201L, "t2", "carol", "ACTIVE", "Other tenant"));
        reads.set(0);
        writes.set(0);
    }

    public Doc find(Long id) {
        return id == null ? null : docs.get(id);
    }

    public boolean member(String tenant, String username) {
        Set<String> users = memberships.get(tenant);
        return users != null && username != null
            && users.contains(username);
    }

    public boolean adminBinding(String tenant, String username) {
        return tenant != null && username != null
            && admins.contains(tenant + ":" + username);
    }

    public boolean viewer(Long id, String username) {
        return id != null && username != null
            && viewers.contains(id + ":" + username);
    }

    public List<Doc> docsInTenant(String tenant) {
        return docs.values().stream()
            .filter(doc -> doc.tenant().equals(tenant))
            .sorted(Comparator.comparing(Doc::id))
            .toList();
    }

    public void recordRead() {
        reads.incrementAndGet();
    }

    public int readCount() {
        return reads.get();
    }

    public int writeCount() {
        return writes.get();
    }

    public synchronized Doc rename(
            Long id, String expectedTenant, String title) {
        Doc old = find(id);
        if (old == null
                || !expectedTenant.equals(old.tenant())
                || !"ACTIVE".equals(old.state())) {
            return null;
        }
        Doc updated = new Doc(
            old.id(), old.tenant(),
            old.owner(), old.state(), title);
        docs.put(id, updated);
        writes.incrementAndGet();
        return updated;
    }
}
```

Các record được seed phía server. Các counters `readCount` và `writeCount` phục vụ minh họa **sự khác nhau giữa pre-deny và post-deny**:
- Pre-deny không subscribe vào `Mono.defer` đọc body method, kỳ vọng `readCount=0`.
- Post-deny có thể đã đọc result rồi mới chặn trả response, kỳ vọng `readCount=1`, còn client không nhận document.
- Mutation bị pre-deny không gọi `rename`, `writeCount=0`.

**Cảnh báo:** Đây là repository RAM không có transaction/isolation như database thật; production cần transaction, optimistic locking và WHERE tenant/action đủ chặt.

### 7.7. DocGuard — membership, owner, viewer và admin binding

**`src/main/java/com/example/reactiveauth/DocGuard.java`**

```java
package com.example.reactiveauth;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("docGuard")
public class DocGuard {

    private final DocCatalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocGuard(DocCatalog catalog) {
        this.catalog = catalog;
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean authenticated(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !trust.isAnonymous(auth);
    }

    private boolean scopedAdmin(Authentication auth, String tenant) {
        return hasAuthority(auth, "ROLE_TENANT_ADMIN")
            && catalog.adminBinding(tenant, auth.getName());
    }

    // Pre-check: đúng tenant, trạng thái và membership.
    public boolean canEnter(
            Authentication auth, String tenant, Long id) {
        if (!authenticated(auth) || tenant == null) {
            return false;
        }
        Doc doc = catalog.find(id);
        return doc != null
            && tenant.equals(doc.tenant())
            && "ACTIVE".equals(doc.state())
            && catalog.member(tenant, auth.getName());
    }

    // Post-check: quyền đọc trên kết quả thực.
    public boolean canReadReturned(
            Authentication auth, Doc doc) {
        if (!authenticated(auth) || doc == null
                || !"ACTIVE".equals(doc.state())
                || !catalog.member(doc.tenant(), auth.getName())) {
            return false;
        }
        return auth.getName().equals(doc.owner())
            || catalog.viewer(doc.id(), auth.getName())
            || scopedAdmin(auth, doc.tenant());
    }

    public boolean canList(Authentication auth, String tenant) {
        return authenticated(auth)
            && tenant != null
            && catalog.member(tenant, auth.getName())
            && hasAuthority(auth, "docs:list");
    }

    // Async-compatible SpEL result cho @PreAuthorize.
    public Mono<Boolean> canEdit(
            Authentication auth, String tenant, Long id) {
        return Mono.fromSupplier(() -> {
            if (!canEnter(auth, tenant, id)) {
                return false;
            }

            Doc doc = catalog.find(id);
            if (doc == null) {
                return false;
            }

            boolean ownerWithEditAuthority =
                auth.getName().equals(doc.owner())
                && hasAuthority(auth, "docs:edit");

            return ownerWithEditAuthority
                || scopedAdmin(auth, tenant);
        });
    }
}
```

Các kiểm soát quan trọng:
- Header `X-Tenant-Id`, path và body **không tự cấp authority**. Tenant trên route là selector; kiểm tra với canonical document tenant và server membership.
- `ROLE_TENANT_ADMIN` chỉ có hiệu lực trong tenant mà user có binding (`t1:manager`).
- Bob được viewer grant cho Document#101 nhưng **không** tự được quyền edit.
- `canEdit` trả `Mono<Boolean>` để phù hợp đường reactive, không gọi `block()`.
- Rule không thấy document, sai tenant, thiếu membership, archived, role/grant sai → deny.

### 7.8. DocService — pre + post cho READ, pre cho mutation

**`src/main/java/com/example/reactiveauth/DocService.java`**

```java
package com.example.reactiveauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocService {

    private final DocCatalog catalog;
    private final DocGuard guard;

    public DocService(DocCatalog catalog, DocGuard guard) {
        this.catalog = catalog;
        this.guard = guard;
    }

    // Hai lớp: pre-check tenant/state; post-check owner/share.
    @PreAuthorize(
        "@docGuard.canEnter(authentication, #tenant, #id)"
    )
    @PostAuthorize(
        "@docGuard.canReadReturned(authentication, returnObject)"
    )
    public Mono<Doc> read(
            @P("tenant") String tenant,
            @P("id") Long id) {

        return Mono.defer(() -> {
            catalog.recordRead();
            return Mono.justOrEmpty(catalog.find(id));
        });
    }

    // List có quyền riêng và lọc từng document theo caller.
    @PreAuthorize(
        "@docGuard.canList(authentication, #tenant)"
    )
    public Flux<Doc> list(@P("tenant") String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMapMany(auth -> Flux.fromIterable(
                    catalog.docsInTenant(tenant)
                )
                .filter(doc -> guard.canReadReturned(auth, doc)));
    }

    // Không dùng @PostAuthorize để bảo vệ mutation!
    @PreAuthorize(
        "@docGuard.canEdit(authentication, #tenant, #id)"
    )
    public Mono<Doc> rename(
            @P("tenant") String tenant,
            @P("id") Long id,
            String title) {

        return Mono.defer(() -> {
            if (title == null || title.isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title required"));
            }

            Doc updated = catalog.rename(id, tenant, title);
            if (updated == null) {
                return Mono.error(new AccessDeniedException(
                    "Resource changed"));
            }
            return Mono.just(updated);
        });
    }
}
```

**Tại sao cách này đúng với chủ đề?**

- `read` dùng cả hai annotations: `@PreAuthorize` không cho query khác tenant hoặc archived, `@PostAuthorize` kiểm tra owner/share trên object thực sự được emit.
- Bob thuộc t1 nhưng không được share Document#102: **pre-pass**, document được đọc, **post-deny**. Một kết quả bị post-deny không được trả cho client, nhưng đọc bên trong **đã xảy ra**.
- Alice thuộc t1 cố đọc Document#201 t2 qua route t1: **pre-deny**, nên method body không cần thực thi.
- `list` có quyền `docs:list` riêng và lọc trên records trong tenant. Đây là demo RAM; dữ liệu lớn phải lọc trong query trước pagination.
- `rename` chỉ dùng **pre-check**, không có post-check sau khi ghi. Quyền edit được quyết định bằng một `Mono<Boolean>`.
- `Mono.defer` giúp logic trong method thực thi khi được subscribe, không có side effect eager trước reactive authorization.

Trong production, `catalog.rename` phải được thay bằng conditional UPDATE tenant/owner/permission + optimistic locking hoặc transaction. Demo không bảo đảm hai thay đổi membership đồng thời luôn atomic.

### 7.9. REST controller — các path/ID của client chỉ là selectors

**`src/main/java/com/example/reactiveauth/DocController.java`**

```java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants")
public class DocController {

    public record RenameBody(String title) {}

    private final DocService service;

    public DocController(DocService service) {
        this.service = service;
    }

    @GetMapping("/{tenant}/docs/{id}")
    public Mono<Doc> read(
            @PathVariable("tenant") String tenant,
            @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @GetMapping("/{tenant}/docs")
    public Flux<Doc> list(
            @PathVariable("tenant") String tenant) {
        return service.list(tenant);
    }

    @PutMapping("/{tenant}/docs/{id}")
    public Mono<Doc> rename(
            @PathVariable("tenant") String tenant,
            @PathVariable("id") Long id,
            @RequestBody RenameBody body) {
        return service.rename(
            tenant, id, body.title());
    }
}
```

Controller không tự kết luận rằng `/api/tenants/t1` chứng minh user thuộc t1; đó chỉ là input cho `DocGuard`. `@RequestBody` ở endpoint rename chỉ nhận title, không cung cấp thao tác thay owner hoặc tenant.

## 8. Integration tests: chứng minh pre/post khác nhau

**`src/test/java/com/example/reactiveauth/ReactiveMethodSecurityTest.java`**

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveMethodSecurityTest {

    @Autowired ApplicationContext context;
    @Autowired DocCatalog catalog;
    @Autowired DocService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        catalog.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private static String docPath(String tenant, long id) {
        return "/api/tenants/" + tenant + "/docs/" + id;
    }

    private WebTestClient as(String username, String... authorities) {
        return client.mutateWith(
            mockUser(username).authorities(authorities)
        );
    }

    private WebTestClient asWithCsrf(
            String username, String... authorities) {
        return as(username, authorities).mutateWith(csrf());
    }

    @Test
    void anonymousReadNeedsAuthentication() {
        client.get().uri(docPath("t1", 101))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnDocument() {
        as("alice").get().uri(docPath("t1", 101))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.title").isEqualTo("Owner memo");
    }

    @Test
    void viewerCanReadSharedDocument() {
        as("bob").get().uri(docPath("t1", 101))
            .exchange().expectStatus().isOk();
    }

    @Test
    void preAuthorizeDeniesOtherTenantBeforeRead() {
        as("alice").get().uri(docPath("t2", 201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesForgedPathTenant() {
        as("alice").get().uri(docPath("t1", 201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesArchivedDocument() {
        as("alice").get().uri(docPath("t1", 104))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesUnknownDocument() {
        as("alice").get().uri(docPath("t1", 999))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void postAuthorizeDeniesUnsharedDocumentAfterFetch() {
        as("bob").get().uri(docPath("t1", 102))
            .exchange().expectStatus().isForbidden();

        // Method đã tạo/subscribe kết quả trước post-check.
        assertEquals(1, catalog.readCount());
    }

    @Test
    void postAuthorizeDeniedContentIsNotReturned() {
        as("bob").get().uri(docPath("t1", 103))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void scopedTenantAdminMayReadPrivateDocument() {
        as("manager", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t1", 103))
            .exchange().expectStatus().isOk();
    }

    @Test
    void adminRoleWithoutServerBindingDoesNotGrantRead() {
        as("bob", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t1", 103))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void scopedAdminCannotReadAnotherTenant() {
        as("manager", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t2", 201))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listRequiresDistinctAuthority() {
        as("bob").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listFiltersDocumentsUsingResultPermission() {
        as("bob", "docs:list")
            .get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void ownerListOmitsArchivedAndUnsharedOthers() {
        as("alice", "docs:list")
            .get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1].id").isEqualTo(102)
            .jsonPath("$[2]").doesNotExist();
    }

    @Test
    void listCannotCrossTenantEvenWithAuthority() {
        as("bob", "docs:list")
            .get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void editRequiresDocsEditAuthority() {
        asWithCsrf("alice")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"No grant\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void ownerWithEditAuthorityCanRename() {
        asWithCsrf("alice", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Revised\"}")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Revised");

        assertEquals(1, catalog.writeCount());
        assertEquals("Revised", catalog.find(101L).title());
    }

    @Test
    void viewerWithEditStringCannotEditUnownedObject() {
        asWithCsrf("bob", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Forbidden\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void editChecksCanonicalTenantBeforeMutation() {
        asWithCsrf("alice", "docs:edit")
            .put().uri(docPath("t1", 201))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Wrong tenant\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void boundAdminMayEditOwnTenant() {
        asWithCsrf("manager", "ROLE_TENANT_ADMIN")
            .put().uri(docPath("t1", 102))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Managed\"}")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.writeCount());
    }

    @Test
    void adminRoleCannotEditAnotherTenant() {
        asWithCsrf("manager", "ROLE_TENANT_ADMIN")
            .put().uri(docPath("t2", 201))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Forbidden\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void missingCsrfBlocksOtherwiseAllowedEdit() {
        as("alice", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"No CSRF\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void unknownRouteDeniedByHttpFilter() {
        as("alice").get().uri("/internal/diagnostics")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceReadUsesReactiveSecurityContext() {
        StepVerifier.create(service.read("t1", 101L))
            .expectNextMatches(doc ->
                doc.id().equals(101L)
                    && doc.owner().equals("alice"))
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "bob")
    void directServiceCallGetsPostAuthorizationError() {
        StepVerifier.create(service.read("t1", 102L))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceCallGetsPreAuthorizationError() {
        StepVerifier.create(service.read("t2", 201L))
            .expectError(AccessDeniedException.class)
            .verify();
        assertEquals(0, catalog.readCount());
    }
}
```

Vì sao test này kiểm tra **đúng Reactive Method Security**?
1. `WebTestClient.bindToApplicationContext(...)` dựng WebFlux handlers và security WebFilters thực của context.
2. `apply(springSecurity())` bật reactive security testing support.
3. `mockUser(...)` thêm principal/authorities test vào request; không phải password authentication hay JWT signature thật.
4. `csrf()` giúp PUT đi qua CSRF filter để kết quả 403/200 phản ánh **method-level quyền sửa**.
5. `@WithMockUser` + `StepVerifier` kiểm thử **Spring-managed service bean** không đi qua HTTP controller. Tài liệu Spring Security có hướng dẫn chính thức cho reactive method-security testing với `StepVerifier`.
6. `readCount` và `writeCount` phân biệt **thời điểm của pre-check và post-check**: pre-deny không fetch, post-deny có fetch nhưng kết quả không được trả, pre-deny trên mutation không có write.

### 8.1. Chạy test

Tại thư mục có `pom.xml`:

```bash
mvn test
```

**Kết quả kỳ vọng:** các test JUnit trên pass nếu chạy đúng dependencies/versions của bài. Đây là **kỳ vọng từ việc biên soạn/kiểm tra mã**, không phải khẳng định đã thực thi Maven. Cần chạy thực tế trên máy phát triển/CI để phát hiện sai khác version, thứ tự reactive interceptors hoặc test configuration.

`@WithMockUser` và `mockUser(...)` kiểm tra **authorization**, không kiểm thử JWT issuer, audience, signature, password strength hoặc production IdP.

### 8.2. Đọc những kết quả quan trọng

| Tình huống | Pre | Post | Dữ liệu bên trong | HTTP/test |
|---|---|---|---|---|
| Alice đọc Document#101 | Allow | Allow | Đọc một bản ghi | 200 |
| Bob đọc Document#101 được share | Allow | Allow | Đọc một bản ghi | 200 |
| Bob đọc Document#102 không share | Allow | Deny | Đã đọc nhưng không emit ra client | 403 |
| Alice dùng path t1 để đọc Doc#201 t2 | Deny | Không thực hiện | Không fetch | 403 |
| Alice đọc Doc#104 archived | Deny | Không thực hiện | Không fetch | 403 |
| Bob sửa Doc#101 không owner | Deny | Không dùng | Không ghi | 403 |
| Alice có docs:edit sửa Doc#101 | Allow | Không dùng | Ghi một lần | 200 |
| Alice không có docs:edit sửa Doc#101 | Deny | Không dùng | Không ghi | 403 |
| Alice PUT không CSRF token | Bị WebFilter chặn | Không chạy service | Không ghi | 403 |
| Bob list với docs:list | Allow | Không dùng | Chỉ trả Doc#101 được đọc | 200 |
| Anonymous đọc bất kỳ API protected | Bị HTTP authentication chặn | Không chạy service | Không đọc | 401 |

**Đặc biệt lưu ý:** Bảng mô tả post-check deny *sau khi đọc* là lý do `@PostAuthorize` không phải lựa chọn bảo vệ side effects. Không dùng HTTP status làm bằng chứng duy nhất về transaction rollback hoặc dữ liệu không bị tác động.

## 9. Các tình huống vượt ngoài demo: cần làm đúng trong sản phẩm

### 9.1. R2DBC và repository có tenant predicate

Với database thật, đừng làm:

```java
return repository.findById(documentId);
```

nếu API multi-tenant có thể lấy record thuộc tenant khác chỉ qua ID. Dùng query ràng buộc tenant và permission:

```sql
SELECT id, tenant_id, owner_id, state, title
FROM document
WHERE id = :documentId
  AND tenant_id = :verifiedTenant;
```

Ở list:

```sql
SELECT d.id, d.tenant_id, d.owner_id, d.state, d.title
FROM document d
WHERE d.tenant_id = :verifiedTenant
  AND d.state = 'ACTIVE'
  AND (
       d.owner_id = :authenticatedUser
       OR EXISTS (
            SELECT 1 FROM document_share s
            WHERE s.document_id = d.id
              AND s.user_id = :authenticatedUser
              AND s.permission = 'READ'
       )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

Những đoạn SQL là **mẫu logic** (không có schema/connection config). Cần thêm admin binding được xác minh nếu nghiệp vụ cho phép admin đọc. `:verifiedTenant` phải là tenant đã đối chiếu Authentication và membership, không phải raw header.

Không query mọi tenant rồi `Flux.filter(...)` sau khi phân trang; cách đó vừa tốn băng thông vừa làm sai tổng số/trang và dễ rò metadata.

### 9.2. @Transactional trong reactive

Spring Framework có reactive transaction với `ReactiveTransactionManager`, hoạt động qua Reactor Context. Đừng trộn imperative `PlatformTransactionManager` và reactive pipeline rồi tin rollback được thực hiện như mong muốn.

Với write:

```java
@PreAuthorize("@docGuard.canEdit(authentication, #tenant, #id)")
@Transactional
public Mono<Integer> update(
        @P("tenant") String tenant,
        @P("id") Long id) {
    return databaseClient.sql(
        """
        UPDATE document
        SET title = :title
        WHERE id = :id AND tenant_id = :tenant
        """
    ).bind("title", "Revised")
     .bind("id", id)
     .bind("tenant", tenant)
     .fetch().rowsUpdated();
}
```

Đây là **mẫu kiến trúc**, cần injected `DatabaseClient`, reactive transaction manager, imports, tên tham số và permission guard đủ điều kiện mới chạy. Với production, thêm owner/role/ACL predicates, expected version và rows-updated == 1.

**Không** chuyển annotation thành `@PostAuthorize("returnObject > 0")` để bảo vệ mutation: việc UPDATE có thể đã chạy, không nên làm sau-check là ranh giới duy nhất. Thay vào đó luôn có pre-check, guarded update và transaction.

### 9.3. Không thực hiện blocking work trong biểu thức

Bean SpEL có thể trả `Boolean` cho rule tính toán nhanh; nhưng nếu phải truy vấn database hoặc HTTP, nên đưa dữ liệu qua non-blocking pipeline và trả `Mono<Boolean>`. Không viết:

```java
@PreAuthorize("@policy.remoteCheck(authentication, #id).block()")
```

Đó là **phản ví dụ**: .block() trong event-loop là bẫy performance. Tạo một bean `@policy.remoteCheck(...)` trả `Mono<Boolean>` trong phiên bản hỗ trợ, đặt timeout và fail-closed khi service không khả dụng.

### 9.4. Subscription và side effects ngoài transaction

Reactive publisher có thể:
- Không được subscribe: không có dữ liệu, không có DML.
- Được subscribe nhiều lần: có thể thực thi lại side effect nếu publisher là cold publisher.
- Bị cancel giữa chừng: có thể chưa hoàn tất hoặc đã gửi external request.
- Chuyển scheduler: Reactor Context thường propagate theo cách Reactor hỗ trợ, nhưng ThreadLocal tùy biến không tự truyền giống vậy.

Cần idempotency keys, quản lý retries, cancellation và transaction boundary. `@PreAuthorize` không tự bảo vệ khỏi “retry hai lần gửi email” nếu logic nghiệp vụ không có idempotency. Với database + broker, xem xét transactional outbox.

### 9.5. @PreFilter / @PostFilter và collection shape

Nếu sử dụng filtering annotations, viết một **compatibility test** cho:
- `List` mutable vs immutable.
- `Mono<List<T>>`, `Flux<T>`, collection thường: loại nào thực sự được intercept và cách filter chạy trong version pinned.
- Collection rỗng, null, array.
- Nested/group/tenant denies.
- Kết quả paging, counts, sort và timing.

Không giả định hành vi giống Servlet trong tất cả các trường hợp. Một annotation hỗ trợ ở mức API nhưng chưa qua test của loại return/argument thực tế có thể dẫn tới lỗi runtime hoặc chính sách lọc sai.

### 9.6. Annotation trên interface, class và self-invocation

Method Security mặc định dùng Spring AOP. Các trường hợp cần test:
- Gọi service qua bean được inject: có thể qua proxy.
- Gọi `this.read(...)` trong cùng class: self-invocation có thể bypass advice.
- Tự `new DocService(...)`: không có Spring proxy.
- Method `private` hoặc `final`, Kotlin class final, interface default method: phụ thuộc proxy configuration, không mặc nhiên được intercept.
- Annotate interface và implementation trùng/mâu thuẫn: cơ chế AuthorizationManager có kiểm tra conflicting annotations; review để policy không ambiguous.
- Class-level annotation với method-level: kiểm tra thứ tự/kế thừa; không tự suy luận hai rule được OR.

Nếu cần AspectJ weaving hoặc custom advisors, đó là cấu hình chuyên sâu phải test theo phiên bản, không lấy demo này làm cam kết hỗ trợ mọi trường hợp.

### 9.7. Cache và principal-specific results

Nếu cache `Doc` theo `docId` mà không phân tenant, hoặc cache quyết định authorization theo username mà không phân action/permissions/version, có thể dùng quyền cũ sau revoke. Mỗi cached authorization decision cần xác định principal, tenant, resource, action, version và TTL; với dữ liệu nhạy cảm cần thiết kế invalidation/revocation SLA.

### 9.8. Security ngoài HTTP

Message consumer, scheduler và asynchronous job không tự có HTTP SecurityContext. Nếu gọi Spring service qua proxy mà chưa thiết lập Authentication/Reactor Context đáng tin, method-level guard sẽ không có cơ sở cấp quyền (thường deny). Nếu công việc do hệ thống thực hiện, tạo service identity/capability rõ ràng, không tự dùng `System.setProperty("admin",true)` hoặc bypass annotation.

## 10. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách sửa |
|---|---|---|
| Dùng `@EnableMethodSecurity` thay `@EnableReactiveMethodSecurity` mà không hiểu stack | Advisor/context không khớp mong muốn | Reactive config đúng version, integration test |
| Chỉ thêm starter-security rồi cho rằng method annotations hoạt động | Annotation không kích hoạt | Bật `@EnableReactiveMethodSecurity` |
| Method trả `void` hoặc giá trị sync và dựa vào Reactor Context | Hành vi không giống publisher | Mono/Flux hoặc return type được version hỗ trợ/test |
| Dùng `@PostAuthorize` duy nhất trên DELETE/UPDATE | DML xảy ra trước deny | `@PreAuthorize` + guarded DML |
| Dùng `@PostAuthorize` như bộ lọc mọi record trong Flux lớn | Sai phân trang/semantics | Lọc tại repository trước paging |
| Cho rằng `@PreFilter` áp dụng tùy ý cho array/List.of/Flux | Runtime errors hoặc sai dữ liệu | Kiểm tra contract, mutable collection và integration test |
| Dùng `hasRole('ADMIN')` như quyền mọi tenant | Cross-tenant escalation | Scope tenant membership và admin binding |
| Bean policy lấy owner từ request body | Client tự khai owner | Canonical resource lookup |
| `block()` trong reactive SpEL | Event-loop bị chặn | Non-blocking Mono<Boolean> |
| Bắt exception rồi default allow | Bypass khi PDP lỗi | Fail-closed, timeout và observability |
| Gọi method bằng `this.method()` | Bỏ qua proxy | Spring-managed service bean |
| Tự `new` một service có annotations | Không có method interceptor | Inject Spring bean |
| Chỉ kiểm tra HTTP route, bỏ resource ID | BOLA/IDOR | Object-level policy trong service và DB |
| 403 từ post-check được hiểu là không có side effect | DB/email có thể đã thay đổi | Pre-check, transaction, outbox |
| Đọc `SecurityContextHolder` bất kỳ trong Reactor | Sai principal khi đổi thread | `ReactiveSecurityContextHolder` |
| Không test negative path, multi-tenant, cancellation | Lỗi khó phát hiện | WebTestClient, StepVerifier, concurrency/revocation tests |
| “Admin luôn có mọi role” | Sai authority mapping | Explicit role hierarchy và scope |
| Không pin/test Spring Security version | Khác biệt annotation behavior | Version matrix và contract tests |

## 11. Checklist code review

- [ ] Spring Boot đang chạy thực WebFlux, không vô tình dùng Servlet auto-configuration.
- [ ] `@EnableReactiveMethodSecurity` được bật, default AuthorizationManager mode đã xác minh.
- [ ] Những method được bảo vệ là Spring-managed bean và đi qua AOP proxy.
- [ ] Java reactive methods trả `Mono`/`Flux` hoặc kiểu được version thực hỗ trợ.
- [ ] Authentication lấy từ Reactor Context, không tự phong qua header/body.
- [ ] `@PreAuthorize` nằm trước mọi mutation có tác dụng phụ.
- [ ] `@PostAuthorize` chỉ dùng ở nơi cho phép đọc result trước kiểm tra, không tự suy luận rollback.
- [ ] Bean SpEL không blocking event-loop, lỗi/empty decision được xử lý an toàn.
- [ ] `@PreFilter`/`@PostFilter` được test trên đúng collection/publisher type, không dùng để thay DB filtering khi dữ liệu lớn.
- [ ] Tenant membership và record tenant canonical được đối chiếu trước khi cấp quyền.
- [ ] Owner/share/role/admin binding theo action; không cấp mọi record chỉ từ membership.
- [ ] Reactive transaction manager và guarded UPDATE/DELETE với affected-row checks.
- [ ] `@PreAuthorize` và `@PostAuthorize` cùng method có tests để chứng minh thứ tự/semantics.
- [ ] CSRF, CORS, JWT authentication và route-level security không bị nhầm với method authorization.
- [ ] Có WebTestClient tests 401/403/200, StepVerifier tests trực tiếp, positive/negative tenant/object.
- [ ] Cache invalidation/revoke, retries, subscriptions và async context được rà soát.
- [ ] Annotation class/interface/meta-annotation được review về quyền kế thừa và xung đột.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Trong reactive app, vì sao dùng `@EnableReactiveMethodSecurity` thay vì chỉ `@EnableMethodSecurity`?

**Trả lời:** Reactive method security cần tích hợp với Reactor Context và reactive method interceptors; `@EnableMethodSecurity` chủ yếu cấu hình nhánh Servlet/imperative method security. Sự khác nhau phải được xác minh theo stack/version.

**Câu 2.** Bob ở tenant t1 đọc một document không được share nhưng tồn tại và active. `@PreAuthorize` tenant check pass; `@PostAuthorize` owner/share check deny. Có nên giả định DB chưa được đọc không?

**Trả lời:** Không. Post-check được áp sau khi đã có result để đánh giá, nên một phần xử lý đọc có thể đã xảy ra. Nội dung bị ngăn không trả cho client, nhưng đây không phải pre-check.

**Câu 3.** Có thể dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho `DELETE` không?

**Trả lời:** Không nên. Delete hoặc side effects có thể đã thực hiện trước khi post-check trả deny. Dùng `@PreAuthorize`, transaction và guarded delete.

**Câu 4.** Spring Security 6.5 Reactive Method Security có hoàn toàn không hỗ trợ `@PreFilter`/`@PostFilter`?

**Trả lời:** Không. Chế độ AuthorizationManager có các reactive filtering interceptors. Tuy nhiên kiểu argument/return value và filter semantics cần được kiểm thử theo chính phiên bản và contract.

**Câu 5.** Tại sao một `List.of(...)` có thể là input không phù hợp cho `@PreFilter`?

**Trả lời:** Contract classic `@PreFilter` yêu cầu Java Collection có thể remove phần tử. `List.of(...)` immutable nên lọc trực tiếp có thể thất bại.

**Câu 6.** Bean được gọi từ `@PreAuthorize` có thể trả `Mono<Boolean>` không?

**Trả lời:** Có trong cơ chế reactive AuthorizationManager của Spring Security 6.5; đây là cách phù hợp cho asynchronous/non-blocking policy logic. Không gọi `block()` để ép chuyển thành boolean.

**Câu 7.** Vì sao `@PostFilter` sau `findAll()` không phải chiến lược tốt cho report phân trang hàng triệu dòng?

**Trả lời:** Repository đã đọc dữ liệu lớn hoặc sai tenant, permission được lọc quá muộn, total count/pagination có thể sai và gây N+1. Đưa tenant/permission predicates vào DB trước paging.

## 13. Nguồn tài liệu chính thức

- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`, bean trả `Boolean`/`Mono<Boolean>`, bốn reactive pre/post interceptors và AuthorizationManager mode.
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html): `@WithMockUser` và `StepVerifier` cho method của Spring bean.
- [Spring Security 6.5 — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `bindToApplicationContext` và `springSecurity()`.
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, roles, authorities.
- [Spring Security 6.5 — Reactive Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()` khi kiểm thử POST/PUT/DELETE.
- [Spring Security 6.5 — PostAuthorizeReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): kiểm tra giá trị trả về của reactive method.
- [Spring Security 6.5 — PreFilterAuthorizationReactiveMethodInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html): interceptor lọc arguments.
- [Spring Security 6.5 — PostFilterAuthorizationReactiveMethodInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html): interceptor lọc returned object.
- [Spring Security 6.5 — EnableReactiveMethodSecurity annotation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html): `useAuthorizationManager` mặc định `true` ở 6.5.
- [Spring Framework — Declarative Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction context và reactive transaction semantics.

**Ghi nhớ:** Với Reactive Method Security, **`@PreAuthorize` chặn trước phần xử lý**, trong khi **`@PostAuthorize` kiểm tra trên kết quả đã được tạo, không thể bảo đảm rollback tác dụng phụ**. Spring Security 6.5 hỗ trợ pre/post authorization và reactive filtering interceptors, nhưng **kiểu return, collection shape, Reactor Context và proxy** quyết định việc dùng đúng hay sai. Hãy dùng `Mono`/`Flux`, policy theo tenant và object canonical, `Mono<Boolean>` non-blocking khi cần, guarded database queries, và kiểm thử cả pre-deny, post-deny lẫn thay đổi dữ liệu.