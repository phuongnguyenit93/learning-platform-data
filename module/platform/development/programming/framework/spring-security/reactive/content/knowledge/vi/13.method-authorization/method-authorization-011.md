# Tác dụng phụ đã xảy ra và giới hạn của kiểm tra sau thực thi

## 1. Mục tiêu học tập

Trong **Spring Security Reactive**, phân quyền phương thức có thể diễn ra trước hoặc sau khi một phương thức service tạo kết quả. `@PreAuthorize` thường kiểm tra quyền trước khi cho phương thức chạy; `@PostAuthorize` kiểm tra kết quả trả về, còn `@PostFilter` loại những phần tử không phù hợp khỏi kết quả. Nhưng **từ chối trả kết quả không đồng nghĩa đã ngăn tác dụng phụ**.

Ví dụ nguy hiểm: một method lưu order vào database rồi trả `Mono<Order>`. `@PostAuthorize` phát hiện order thuộc người khác và từ chối. Client nhận HTTP 403, nhưng lệnh UPDATE đã có thể commit trước đó. Nếu method đã gửi email hoặc publish Kafka event, không có cơ chế tự thu hồi tác vụ chỉ nhờ hậu kiểm.

Bài thuộc nhóm **Phân quyền phương thức** của **Spring Security - reactive**. Sau bài, bạn sẽ biết:

1. Phân biệt authentication, authorization trước và sau thực thi, phản hồi HTTP và trạng thái thực tế của tài nguyên.
2. Hiểu thứ tự cold publisher, subscription, thực hiện side effect, phát giá trị, `@PostAuthorize` kiểm tra và subscriber nhận signal.
3. Giải thích khi nào `@PostAuthorize` hữu ích, và tại sao không nên dùng nó làm chốt kiểm tra quyền đầu tiên cho write/delete/payment.
4. Nhận ra hậu quả của `@PostFilter` trên `Flux`, pagination, query chi phí cao, dữ liệu streaming và tác dụng phụ upstream.
5. Phân tích `Mono<Void>`, publisher rỗng, lỗi, cancellation, event đã phát, commit DB và HTTP response đã committed.
6. Tổ chức kiểm tra trước bằng `@PreAuthorize`, permission service, conditional SQL, transaction và transactional outbox.
7. Chạy demo WebFlux Java 17+, dùng `WebTestClient` xác minh một HTTP 403 **vẫn có side effect**, so với pre-authorization từ chối trước khi state thay đổi.
8. Tránh self-invocation bypass Spring AOP, tự `subscribe()`, blocking I/O và nhầm CSRF 403 với authorization 403.

Phần code dành cho Spring Boot 3.x, Spring Security 6.x và Java 17+. Trong ví dụ, `AtomicInteger` đóng vai trò side effect không có transaction để quan sát rõ; nó **không** là mô hình lưu trữ nghiệp vụ production. Phương thức có annotation phải là phương thức trên Spring-managed bean được gọi qua proxy phù hợp.

## 2. Side effect là gì, và nó xảy ra khi nào?

**Side effect** là ảnh hưởng quan sát được ngoài giá trị trả về. Ví dụ:

| Thao tác | Side effect | Có được undo chỉ vì hậu kiểm deny? |
|---|---|---|
| Cộng hai số trong local variable | Không có trạng thái ngoài | Không cần |
| `AtomicInteger.incrementAndGet()` | Bộ đếm thay đổi | **Không** |
| `UPDATE ...` đã commit | Database thay đổi | **Không** |
| Gửi email/SMS | Người nhận có thể thấy thông báo | **Không** |
| Gọi API thanh toán thành công | Hệ thống ngoài đã xử lý | **Không** |
| Gửi message tới broker | Consumer có thể đã nhận | **Không** |
| Ghi cache toàn cục | Cache state thay đổi | **Không** |
| Ghi logs chứa data nhạy cảm | Dữ liệu đã có thể bị lộ | **Không** |
| R2DBC write trong transaction chưa commit | State có thể rollback nếu transaction bắt lỗi đúng phạm vi | **Tùy transaction boundary** |

Đừng hiểu response `403 Forbidden` là một lệnh rollback. 403 biểu thị client không có quyền theo security flow đang chạy; nó **không chứng minh** rằng database, filesystem, cache hoặc external system không đổi.

### 2.1. Phân biệt bốn lớp kết quả

Khi debug một request bị từ chối, phải kiểm tra độc lập:

- **Quyết định phân quyền:** policy cho phép hay từ chối?
- **Tín hiệu Reactor:** publisher phát value, `onError`, `onComplete` hay bị cancel?
- **HTTP response:** 401, 403, 302, 500 hoặc response đã committed?
- **Trạng thái thực:** row đã update, event đã publish, email đã gửi, cache đã ghi chưa?

Một `WebTestClient` test chỉ có `expectStatus().isForbidden()` chưa đủ bảo vệ một endpoint mutation. Test còn phải xác minh dữ liệu **không** đổi đối với request không đủ quyền.

## 3. Thứ tự thực thi: @PreAuthorize so với @PostAuthorize

Mô hình logic với một method trả `Mono<Receipt>`:

```text
REQUEST -> Security Authentication
             |
             v
        Spring AOP proxy
             |
        @PreAuthorize
             | deny -> chặn trước method/work được bảo vệ
             v allow
        method trả Mono<Receipt>
             |
           subscribe
             |
     upstream thực thi (DB write / event / email)
             |
       emit Receipt(owner=...)
             |
        @PostAuthorize
         |          |
       allow       deny
         |          |
      trả value   AccessDeniedException / denial signal
                    |
                  HTTP layer có thể trả 403
                    |
              SIDE EFFECT không tự biến mất
```

Đây là **mô hình chức năng**, không phải thứ tự nội bộ cố định của mọi advisor. Trong reactive code, cần phân biệt **thời điểm gọi Java method** với **thời điểm publisher được subscribe và chạy**.

### 3.1. Reactor là lazy, nhưng không phải mọi Java statement đều lazy

```java
AtomicInteger writes = new AtomicInteger();

Mono<Integer> lazy = Mono.fromSupplier(
    () -> writes.incrementAndGet());

// Chỉ tạo Mono: writes.get() vẫn là 0.
// Chỉ khi subscribe, supplier mới chạy.
```

Mảnh code này cần import `java.util.concurrent.atomic.AtomicInteger` và `reactor.core.publisher.Mono`. Chạy `lazy.block()` chỉ thích hợp trong main/test minh họa, **không** trong WebFlux handler.

Cẩn thận với:

```java
Mono<Integer> eager =
    Mono.just(writes.incrementAndGet());
```

Ở đây `incrementAndGet()` được Java thực thi **ngay trước** khi `Mono.just(...)` được gọi. Tác dụng phụ đã xảy ra khi xây dựng publisher, không cần subscription. Nếu một method có side effect eager, hậu kiểm lại càng không thể được xem là “bảo vệ trước”.

Các publisher từ R2DBC/WebClient thường thực hiện I/O khi subscribe, nhưng một lời gọi Java tự viết có thể chạy eager. Không suy luận về lifecycle chỉ từ việc phương thức khai báo `Mono<T>`.

### 3.2. Check trước cần biết những gì?

`@PreAuthorize` có thể dùng principal, roles, authorities và tham số method:

```java
@PreAuthorize("#p0 == authentication.name")
public Mono<Receipt> saveFor(String owner) {
    return repository.saveFor(owner);
}
```

Đây là snippet; `repository` và `Receipt` do dự án định nghĩa. `#p0` là method argument đầu tiên, giúp tránh phụ thuộc cấu hình lưu tên tham số. Kiểm tra trước giúp chặn việc gọi method nếu owner argument không khớp người đã xác thực.

**Nhưng owner do client gửi không chứng minh quyền thực trên resource.** Với `orderId` hoặc `projectId`, phải tra owner/tenant/ACL từ nguồn authoritative, và nên đưa ràng buộc quyền vào truy vấn update. Pre-check đúng về timing vẫn có thể sai về policy nếu dữ liệu đầu vào không đáng tin.

### 3.3. Post-check cần kết quả trước khi ra quyết định

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Report> read(String reportId) {
    return repository.findById(reportId);
}
```

Snippet giả định `Report` có JavaBean property `owner` và repository trả `Mono<Report>`. Hậu kiểm có thể hữu ích như defense-in-depth cho **read-only result**: object thuộc người khác không được chuyển tiếp tới caller. Tuy nhiên:

- Database **đã có thể đọc** dữ liệu.
- Query có thể tạo audit/cache/observability side effects.
- Truy vấn không lọc tenant có thể tốn tài nguyên hoặc lộ side-channel.
- Nếu method thực hiện mutation trước khi trả `Report` thì tác dụng phụ có thể đã xảy ra.

Chọn query chỉ lấy dữ liệu mà principal được phép truy cập và giữ hậu kiểm như lớp bổ sung, không như giải pháp duy nhất.

### 3.4. @PostFilter không tương đương WHERE owner = ...

```java
@PostFilter("filterObject.owner == authentication.name")
public Flux<Report> listReports() {
    return repository.findAll();
}
```

Đây là mảnh code dùng `Flux`, `@PostFilter` và repository reactive do dự án cung cấp. `filterObject` là từng phần tử cần kiểm tra. Filter phía sau **không tự viết lại truy vấn** thành `WHERE owner_id = :principal`. Toàn bộ dữ liệu có thể đã bị fetch, ánh xạ, giải mã, log hoặc xử lý side effect ở upstream trước khi bị loại. Điều đó cũng có thể làm phân trang không đúng: DB trả một trang lớn gồm nhiều record trái quyền, sau hậu lọc chỉ còn vài record.

Với tập dữ liệu lớn/đa tenant, ưu tiên repository query scoped theo **tenant, user, membership, role và ACL**. Không giả định `@PostFilter` bảo vệ mọi trường hợp streaming/hot publisher; test behavior theo Spring Security version, loại publisher và serialization.

### 3.5. Mono.empty, Mono<Void> và error

Với `Mono.empty()` hoặc `Mono<Void>`, không có object nghiệp vụ được phát để hậu kiểm `returnObject.owner`. Chẳng hạn xóa dữ liệu trả `Mono<Void>` không được bảo vệ an toàn chỉ bằng expression về owner của *kết quả*. Phải authorize trước khi xóa và kiểm tra owner/tenant ngay trong DELETE.

Khi publisher `Mono.error(e)`, không có giá trị returnObject hợp lệ để áp rule giống luồng success. Cancellation cũng không thể đảo ngược các effect đã được commit. Với stream đã bắt đầu trả bytes, authorization error ở thời điểm muộn có thể xuất hiện khi HTTP response đã commit; server không lấy lại dữ liệu client đã nhận.

## 4. @EnableReactiveMethodSecurity và sự khác biệt với Servlet

Spring Security WebFlux dùng Reactor Context để giữ `Authentication` trong subscription. Muốn áp dụng `@PreAuthorize`, `@PostAuthorize` và `@PostFilter` trên phương thức reactive, cần bật reactive method security, ví dụ:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveAuthorizationConfig {
}
```

Đây là class cấu hình Spring, cần import `Configuration` và `EnableReactiveMethodSecurity`. Project thực hành bên dưới sẽ bật nó trong security config đầy đủ.

- Reactive method security được tích hợp qua **Spring AOP**; một phương thức trên Spring-managed bean cần được gọi qua proxy để các advisor chạy.
- Những method reactive thông thường trả `Mono<T>`/`Flux<T>`; Spring Security đọc authentication từ Reactor Context.
- `@EnableMethodSecurity`, `HttpSecurity` và `SecurityFilterChain` thuộc hướng cấu hình Servlet method/HTTP; không thay thế nguyên văn `@EnableReactiveMethodSecurity` + `ServerHttpSecurity` trong WebFlux.
- SpEL `authentication.name` là tên user đã được xác thực bởi security filter, không được tự lấy từ input client.
- Expression tham chiếu `returnObject` nên dựa trên JavaBean getter/property thật, hoặc kiểu result được phiên bản Spring Security hỗ trợ.

Nếu custom method trả `Mono<Void>` để update, hãy thiết kế **pre-authorization** thay vì thử diễn giải một return value rỗng.

## 5. Những tác dụng phụ điển hình mà hậu kiểm không undo

### 5.1. Database UPDATE/DELETE đã commit

```text
POST /orders/42/approve (Alice)
  -> repository.update(42, "APPROVED")
  -> DB thay đổi / có thể commit
  -> Mono phát Order(id=42, owner="bob")
  -> @PostAuthorize("returnObject.owner == authentication.name")
  -> Alice không phải Bob -> deny
  -> HTTP 403

Kết quả có thể xảy ra:
  HTTP client không nhận order
  NHƯNG order 42 đã ở trạng thái APPROVED
```

Từ khóa là **có thể**: nếu cùng một reactive transaction thực sự bao phủ hậu kiểm và rollback khi denial signal tới transaction boundary thì DB write chưa commit có thể bị rollback. Nhưng không được giả định điều đó chỉ vì có `@Transactional` trên source. Phải kiểm tra thời điểm commit, advisor order và transaction propagation bằng test.

### 5.2. Email, webhook, push notification

Nếu method gọi `emailSender.send(...)` rồi trả receipt, sau đó hậu kiểm deny, email đã có thể được gửi. Không có “rollback email”. Cần authorize **trước khi enqueue/send**, và nếu muốn gửi khi DB commit thành công thì dùng outbox/job xử lý có policy/idempotency rõ.

### 5.3. Kafka và message broker

Một event đã được broker ack có thể được consumer khác xử lý, dù HTTP handler cuối cùng nhận `AccessDeniedException`. Đừng để publish xảy ra trước khi xác minh quyền và quyết định transaction. Nếu có event publish sau commit, thiết kế idempotency/retry/outbox thay vì publish trước rồi hy vọng deny sẽ thu hồi event.

### 5.4. Thanh toán và hệ thống ngoài

Một `WebClient` call đã khiến payment gateway tạo charge không bị undo bởi Spring Security từ chối trả receipt. Chuyển tiền, cấp quyền, gửi hàng, đặt chỗ cần pre-check, business rules, idempotency key, audit và workflow bù trừ riêng khi thích hợp. Một `Mono.error(AccessDeniedException)` không phải lệnh refund.

### 5.5. Cache, log và observability

Một operator upstream hậu kiểm có thể `doOnNext(item -> cache.put(...))` hoặc log object nhạy cảm. Sau đó hậu kiểm deny, dữ liệu có thể còn trong cache/log. Cache key phải có user/tenant/ACL khi cần, và không bao giờ log password, bearer token, session ID hoặc payload nhạy cảm. Đừng nghĩ HTTP body không được gửi thì không có dữ liệu nào từng bị xử lý.

## 6. Thiết kế an toàn hơn: kiểm tra trước và ở nơi sửa dữ liệu

Tư duy phù hợp cho method mutation:

```text
Authentication đã được xác minh
    |
    v
Pre-authorization theo action + principal + args
    |
    v
Repository lấy quyền sở hữu/tenant/ACL từ nguồn tin cậy
    |
    v
Conditional UPDATE/DELETE hoặc transaction atomic
    |
    +-- affectedRows == 0 -> không tiếp tục effect
    |
    v
Ghi outbox event trong transaction nếu cần
    |
    v
COMMIT
    |
    v
Worker publish external effect an toàn/idempotent
```

### 6.1. SQL bảo vệ resource tại nơi cập nhật

```sql
UPDATE orders
SET status = :new_status
WHERE id = :order_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user_id
  AND status = :expected_status;
```

Đây là **SQL mẫu có bind parameters**, không phải implementation repository chạy độc lập. `trusted_tenant` và `authenticated_user_id` phải được suy ra từ identity đáng tin và policy server-side, **không** đọc thẳng từ một header `X-User` hay query do client kiểm soát. Nếu row count bằng 0, không publish event, không tự coi tác vụ thành công; phân biệt 403/404/conflict theo chính sách bảo mật và tránh resource enumeration.

### 6.2. TOCTOU: pre-check cũng chưa đủ

*Time of check / time of use*: một user có quyền ở thời điểm t0 nhưng quyền bị thu hồi trước khi update t1. Dù `@PreAuthorize` chạy đúng, nếu service chỉ dựa vào kết quả cũ, nó có thể ghi trái phép. Để giảm race:

1. Kiểm tra ACL từ dữ liệu authoritative.
2. Khi mutation, đưa điều kiện tenant/owner/version vào SQL hoặc dùng transaction/locking thích hợp.
3. Kiểm tra affected rows/optimistic version, không “success” mù.
4. Với quyền đặc biệt nhạy cảm, đánh giá chính sách revalidation gần commit.
5. Có idempotency cho retry và audit dấu vết.

### 6.3. Reactive transaction có rollback được hậu kiểm không?

Câu trả lời là **phụ thuộc cấu hình**. Spring R2DBC và `TransactionalOperator` quản lý transaction qua Reactor Context. Tính rollback phụ thuộc liệu `AccessDeniedException` có lan tới transaction boundary **trước commit** và dữ liệu có cùng transaction không.

Sai nếu kết luận:
- “`@PostAuthorize` luôn chạy sau DB commit, chắc chắn không rollback.”
- “`@Transactional` bảo đảm 100% dữ liệu sẽ rollback khi `@PostAuthorize` từ chối.”

Test phải dùng database transaction thật, kiểm tra state trước/sau, quan sát commit và advisor ordering của phiên bản đang triển khai. Một email hoặc event ngoài transaction vẫn không được rollback ngay cả khi DB quay về trạng thái ban đầu. Transaction bảo đảm atomicity theo boundary của nó, **không là công cụ phân quyền thay cho pre-check**.

### 6.4. Transactional outbox cho DB + event

```text
BEGIN DB TRANSACTION
  verify resource ACL / authorization
  UPDATE resource với tenant/owner/version condition
  INSERT outbox_event (nếu update hợp lệ)
COMMIT

Outbox dispatcher:
  đọc event đã commit -> publish -> retry/idempotency
```

Nếu transaction rollback, outbox event không được commit để phát. Dispatcher gửi sau commit và có thể retry; consumer cần idempotency. Đây là một mô hình nhất quán thực tế hơn việc publish Kafka trực tiếp rồi chờ `@PostAuthorize` phân quyền ở cuối.

## 7. Project Spring WebFlux Java 17+ minh họa side effect sau 403

Chúng ta xây dựng hai phương thức service có **cùng tác dụng phụ** nhưng thứ tự kiểm tra khác nhau:

- `risky(owner)`: tăng counter trong `Mono.fromSupplier`, tạo result, dùng `@PostAuthorize` so result.owner với principal.
- `safe(owner)`: dùng `@PreAuthorize` so argument với principal, chỉ tăng counter khi đã cho phép.

Mỗi HTTP POST yêu cầu authentication và CSRF hợp lệ. Demo dùng `AtomicInteger` để nhìn thấy effect ngay trong kiểm thử; **không dùng counter này để lưu giao dịch thật**.

### 7.1. Tạo project và dependencies

Dùng Spring Initializr với Java 17+, Spring Boot 3.x, Gradle (Groovy DSL), dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, **Spring Security Test**.

Giữ các plugins Spring Boot, repositories, dependency management và Java toolchain do Initializr sinh. Block `dependencies` tương ứng trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **block dependencies**, không phải toàn bộ `build.gradle`. Không thêm `spring-boot-starter-web`: nếu cùng có MVC và WebFlux starters, Spring Boot 3.x thường ưu tiên Servlet MVC ở inbound stack.

Cấu trúc:

```text
src/main/java/demo/sideeffects/
  SideEffectsApplication.java
  SecurityConfig.java
  OperationService.java
  OperationController.java
src/test/java/demo/sideeffects/
  SideEffectSecurityTests.java
```

### 7.2. Application entry point

File `src/main/java/demo/sideeffects/SideEffectsApplication.java`:

```java
package demo.sideeffects;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SideEffectsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SideEffectsApplication.class, args);
    }
}
```

### 7.3. WebFlux security và reactive method security

File `src/main/java/demo/sideeffects/SecurityConfig.java`:

```java
package demo.sideeffects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.POST, "/ops/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

Lý giải:
- `@EnableReactiveMethodSecurity` bật advisors phương thức trong các Spring-managed beans.
- HTTP security của `/ops/**` chỉ đòi user đã đăng nhập. Quy tắc owner là **method-level security** để minh họa thứ tự.
- `httpBasic` phục vụ credential demo. Trong ứng dụng thật phải dùng HTTPS; HTTP Basic chỉ mã hóa Base64 credential trong header, không bảo vệ đường truyền.
- `formLogin` bị tắt để test API nhận 401 thay vì HTML redirect khi chưa authenticated.
- **CSRF chưa bị tắt**; POST cần token hợp lệ trong cấu hình mặc định. Ở mục 8, `WebTestClient.mutateWith(csrf())` cung cấp token qua Spring Security test infrastructure.
- User store in-memory và password mẫu chỉ dùng để học; password được lưu dưới dạng encoded hash, không dùng dữ liệu này trong production.

### 7.4. Service chứa một tác dụng phụ được kiểm soát

File `src/main/java/demo/sideeffects/OperationService.java`:

```java
package demo.sideeffects;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OperationService {

    private final AtomicInteger effects = new AtomicInteger();

    public static final class Receipt {
        private final String owner;
        private final int sequence;

        public Receipt(String owner, int sequence) {
            this.owner = owner;
            this.sequence = sequence;
        }

        public String getOwner() {
            return owner;
        }

        public int getSequence() {
            return sequence;
        }
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Mono<Receipt> risky(String owner) {
        return Mono.fromSupplier(() -> {
            int sequence = effects.incrementAndGet();
            return new Receipt(owner, sequence);
        });
    }

    @PreAuthorize("#p0 == authentication.name")
    public Mono<Receipt> safe(String owner) {
        return Mono.fromSupplier(() -> {
            int sequence = effects.incrementAndGet();
            return new Receipt(owner, sequence);
        });
    }

    public int effectCount() {
        return effects.get();
    }

    // Dành cho JUnit test, không mở thành HTTP endpoint.
    public void resetForTests() {
        effects.set(0);
    }
}
```

Đây là một class Java hoàn chỉnh. `Receipt` có `getOwner()`, nên SpEL có thể truy cập JavaBean property `returnObject.owner`. `@PostAuthorize` kiểm tra sau khi `risky` tạo result; `@PreAuthorize` của `safe` kiểm tra argument trước khi cho method thực thi.

Với principal Alice:
- `risky("bob")`: supplier tăng counter **rồi** trả Receipt owner Bob; hậu kiểm từ chối. Side effect vẫn còn.
- `safe("bob")`: pre-check thấy owner không khớp principal, không cho method chạy; counter không đổi.
- `safe("alice")`: được phép, counter tăng và response chứa Receipt.
- `risky("alice")`: hậu kiểm cho phép; counter tăng và Receipt trả cho caller.

Đây là **minh họa lỗi thiết kế bằng side effect không transactional**, không phải bằng chứng mọi DB transaction đều không rollback. Trong production không cho client tự chỉ định owner rồi tin nó: phải kiểm tra resource ACL thật.

### 7.5. Controller trả publisher, không tự subscribe

File `src/main/java/demo/sideeffects/OperationController.java`:

```java
package demo.sideeffects;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OperationController {

    private final OperationService service;

    public OperationController(OperationService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @PostMapping("/ops/risky/{owner}")
    public Mono<OperationService.Receipt> risky(
            @PathVariable String owner) {
        return service.risky(owner);
    }

    @PostMapping("/ops/safe/{owner}")
    public Mono<OperationService.Receipt> safe(
            @PathVariable String owner) {
        return service.safe(owner);
    }
}
```

Controller gọi bean `OperationService` được inject, giúp lời gọi đi qua Spring AOP proxy. Không tự `subscribe()` ở controller hoặc service; WebFlux sẽ subscribe publisher trả về. Lời gọi trực tiếp từ method này đến method khác trong **cùng instance**, ví dụ `this.safe(...)`, có thể bypass proxy và bỏ qua annotation trong proxy-based Spring AOP.

### 7.6. HTTP dự kiến với CSRF hợp lệ

| Request | Authorization | HTTP dự kiến | Side effect |
|---|---|---:|---|
| Alice POST `/ops/risky/alice` | Post-check pass | 200 | Counter +1 |
| Alice POST `/ops/risky/bob` | Post-check deny | 403 | **Counter +1** |
| Alice POST `/ops/safe/alice` | Pre-check pass | 200 | Counter +1 |
| Alice POST `/ops/safe/bob` | Pre-check deny | 403 | **Counter không đổi** |
| Anonymous POST `/ops/safe/alice` | Chưa xác thực | 401 theo HTTP Basic | Không |
| Alice POST thiếu CSRF | Bị CSRF filter chặn | 403 | Không |

**Cùng status 403 có thể xuất phát từ hai nơi khác nhau**: thiếu CSRF hoặc method deny. Muốn kiểm thử hậu kiểm, nhất thiết phải gửi CSRF token hợp lệ để request đến service.

### 7.7. Chạy demo

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kiểm tra route công khai:

```bash
curl -i http://localhost:8080/health
```

Dự kiến HTTP 200, body:

```text
ok
```

Một lệnh POST `curl` thiếu CSRF token có thể nhận 403 trước khi method-level checks chạy. Không tắt CSRF chỉ để dựng “demo side effect”; test Spring Security ở mục 8 sẽ đính token đúng cách.

## 8. WebTestClient test: 403 không có nghĩa side effect = 0

File `src/test/java/demo/sideeffects/SideEffectSecurityTests.java`:

```java
package demo.sideeffects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SideEffectSecurityTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    OperationService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        service.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthWorks() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");

        assertEquals(0, service.effectCount());
    }

    @Test
    void postDenyDoesNotUndoSideEffect() {
        client.mutateWith(csrf())
            .post().uri("/ops/risky/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(1, service.effectCount());
    }

    @Test
    void preDenyPreventsSideEffect() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, service.effectCount());
    }

    @Test
    void allowedPreCheckRunsOnce() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.sequence").isEqualTo(1);

        assertEquals(1, service.effectCount());
    }

    @Test
    void allowedPostCheckRunsOnce() {
        client.mutateWith(csrf())
            .post().uri("/ops/risky/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice");

        assertEquals(1, service.effectCount());
    }

    @Test
    void anonymousCannotCallMutation() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/alice")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(0, service.effectCount());
    }

    @Test
    void missingCsrfPreventsPost() {
        client.post().uri("/ops/safe/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, service.effectCount());
    }
}
```

Đây là class JUnit 5, dùng test context WebFlux. `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` nối security filters vào mock server. `mutateWith(csrf())` cung cấp CSRF token thông qua Spring Security **test support**; client thật phải lấy token/session theo protocol, không tự đặt token tùy ý.

**Hai phép kiểm tra cốt lõi**:

- `postDenyDoesNotUndoSideEffect`: HTTP 403 **và** counter = 1, chứng minh hậu kiểm không hoàn tác một tác dụng phụ ngoài transaction.
- `preDenyPreventsSideEffect`: HTTP 403 **và** counter = 0, chứng minh pre-check chặn công việc ở case này.

Trong test, mỗi lần `@BeforeEach` reset counter. Nếu thiết kế test chạy song song hoặc chia sẻ ApplicationContext giữa nhiều classes, cần đảm bảo không có race giữa các phép đo; production test thực nên dùng isolated fixture, test containers hoặc fake service có kiểm soát.

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Kỳ vọng **7 test** trên cấu hình đã trình bày. Đây là **kết quả dự kiến từ mã**, chưa phải tuyên bố đã chạy Gradle. Nếu gặp khác biệt do version/test setup, kiểm tra filter chain, CSRF, AOP proxy, actual HTTP response, dữ liệu user store và việc Mono thực sự được subscribe. Không sửa expected 403 thành 200 chỉ để test xanh.

### 8.1. Test mutation production phải kiểm tra state thật

Ngoài HTTP status, test cần xác minh những điều sau theo từng endpoint:

- Database row và version chưa thay đổi khi không đủ quyền.
- Không có outbox event mới khi SQL conditional update từ chối.
- Không có Kafka event/email/webhook/payment call ngoài ý muốn.
- Cache không lưu dữ liệu trái quyền và không lộ dữ liệu tenant khác.
- Retry/idempotency không nhân đôi side effect.
- Concurrent permission revocation không tạo cửa sổ ghi trái phép.
- Stream không phát phần tử nhạy cảm trước authorization.
- Logout/session expiry/role update làm thay đổi quyền đúng kỳ vọng.

## 9. Giới hạn của rollback và cancellation

### 9.1. @Transactional không tự giải quyết thứ tự security

Với reactive transaction, các manager như `R2dbcTransactionManager`/`TransactionalOperator` dùng Reactor Context; operation nằm trong transaction khi được compose đúng vào publisher/boundary. Nếu denial signal của `@PostAuthorize` tới transaction operator trước commit thì DB write có thể rollback. Nếu transaction đã commit trước hậu kiểm, không thể suy ra rollback. `@Transactional`, advisors, order và resource boundaries quyết định hành vi.

**Không chọn một kết luận tuyệt đối**. Hãy kiểm thử trạng thái DB, transaction commit/rollback và ordering trong đúng phiên bản ứng dụng. Dù DB rollback, email, webhook, Kafka hoặc tác vụ background ngoài transaction vẫn có thể đã xảy ra.

### 9.2. Cancellation không phải phép hoàn tác

Browser đóng tab hoặc subscriber cancel không có nghĩa HTTP call đang chạy, DB commit, email hoặc message sẽ được tự rollback. Một `Mono.fromCallable` hoặc task detached có thể tiếp tục đến khi hoàn thành; một I/O reactive được hỗ trợ cancellation có thể dừng nhưng kết quả phụ thuộc thời điểm external system xử lý. Với mutation cần idempotency/compensation và xác minh trạng thái độc lập.

### 9.3. Response streaming có thể đã commit

`Flux` phát một vài phần tử trước khi phát error thì client có thể đã nhận byte dữ liệu. Header/status HTTP có thể đã committed nên server không đổi toàn bộ response thành 403 được. Bảo vệ tại source và authorize **trước lần emit đầu tiên**, không dựa vào hậu kiểm muộn để thu hồi những gì client đã đọc.

## 10. Những bẫy thường gặp

### 10.1. Self-invocation bỏ qua AOP proxy

```java
// Snippet lỗi: hai method cùng class, gọi trực tiếp qua this.
public Mono<Receipt> entry(String owner) {
    return this.secured(owner);
}

@PreAuthorize("#p0 == authentication.name")
public Mono<Receipt> secured(String owner) {
    return repository.update(owner);
}
```

Nếu không đi qua Spring AOP proxy, annotation trên `secured` có thể không chạy. Phải gọi bean được inject, tách service hoặc thiết kế proxy phù hợp rồi test. Đừng giả định annotation luôn hoạt động chỉ vì có mặt trong source.

### 10.2. Tự gọi subscribe() để fire-and-forget

```java
// Snippet lỗi: email độc lập khỏi publisher trả về.
emailSender.send(user).subscribe();
return repository.save(item);
```

Side effect chạy ở subscription tách rời, không tuân theo cùng error, cancellation, context và authorization lifecycle. Nếu hậu kiểm từ chối, email vẫn có thể gửi. Hãy compose publisher, authorize trước enqueue, và với background work thật dùng queue/outbox có quyền, retry, TTL và idempotency phù hợp.

### 10.3. Dùng blocking repository trong reactive service

`jdbcRepository.save(...)` gọi đồng bộ trong Netty event-loop gây nghẽn. Nếu chưa thay được R2DBC, chỉ bọc đoạn blocking vào `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` **kèm giới hạn concurrency**, không biến blocking thành non-blocking. Và đừng hiểu chuyển scheduler có thể đảo ngược side effect sau hậu kiểm.

### 10.4. Trông cậy vào @PostFilter cho truy vấn quá rộng

Kết quả bị lọc phía sau nhưng DB vẫn đọc mọi tenant; pagination, count, latency và side-channel có thể sai. Query tenant-scoped ngay từ DB, kiểm tra ACL ở service, rồi dùng post-filter nếu muốn defense-in-depth cho tập nhỏ.

### 10.5. Nhầm 403 do CSRF với 403 do authorization

Một POST thiếu CSRF token có thể bị chặn **trước** controller, vì vậy counter = 0 không chứng minh `@PreAuthorize`. Trong test, dùng `csrf()` đúng để đưa request qua filter, rồi test nhánh method deny độc lập.

### 10.6. Tin returnObject lấy từ client

Nếu method chỉ trả một object được dựng từ owner do client nhập, hậu kiểm `returnObject.owner == authentication.name` có thể kiểm tra sai nguồn dữ liệu. Owner trong result cần gắn với **resource authoritative**; ngay cả hậu kiểm read-only cũng phải dựa vào dữ liệu đáng tin.

## 11. Bảng lựa chọn cơ chế bảo vệ

| Loại thao tác | Kiểm tra ưu tiên | Vai trò của hậu kiểm |
|---|---|---|
| Đọc một object | Principal/tenant trước, query scoped theo ACL | Defense-in-depth trên object trả về |
| Liệt kê nhiều object | Repository WHERE owner/tenant, pagination phù hợp | PostFilter bổ sung, không thay query |
| Tạo object | PreAuthorize action/quota/tenant, transaction | Không dùng làm điều kiện cấp quyền lần đầu |
| Update/delete | PreAuthorize + conditional SQL owner/version | Không ngăn write đã commit |
| Gửi email/SMS | Authorize trước send/enqueue | Không thu hồi email |
| Thanh toán/transfer | Authentication, authorization, limits, idempotency | Không tự refund |
| Publish Kafka event | Authorize, transaction + outbox | Không xóa event đã phát |
| Streaming response | Authz trước emit, query/record-level ACL | Không thu hồi bytes đã gửi |
| Cache dữ liệu cá nhân | Pre-check + cache key theo principal/tenant | Không tự làm sạch cache upstream |

## 12. Bài tập và đáp án

**Bài 1.** Alice gọi method có `@PostAuthorize("returnObject.owner == authentication.name")`. Method đã update record của Bob và trả Receipt(owner=Bob). Client nhận 403. Database chắc chắn không đổi?

**Đáp án:** Không. Side effect có thể đã commit trước hậu kiểm. 403 chỉ báo access denied ở return boundary; cần assert state và thiết kế pre-authorization/conditional DB write.

**Bài 2.** Tại sao `@PreAuthorize("#p0 == authentication.name")` vẫn chưa đủ nếu `#p0` là owner do client tự nhập?

**Đáp án:** Chủ sở hữu thật/tenant/ACL phải được xác minh bằng nguồn tin cậy. Client có thể khai owner của chính mình cho resource thuộc người khác. Dùng lookup + conditional SQL hoặc row-level security.

**Bài 3.** `@PostFilter` trả 25 record trong khi query đã đọc 10.000 record. Server có tránh đọc 9.975 record không được phép không?

**Đáp án:** Không. Lọc kết quả sau khi truy vấn không thay điều kiện DB và có thể gây tải/pagination sai, side effects upstream.

**Bài 4.** Trong demo, Alice gọi `risky("bob")`, HTTP 403 và counter = 1. Đây là lỗi Spring Security?

**Đáp án:** Đây là hậu quả đúng của thiết kế chỉ hậu kiểm: Spring Security ngăn trả result nhưng không tự hoàn tác tác dụng phụ đã xảy ra.

**Bài 5.** Có nên dùng `@PostAuthorize` dựa trên `returnObject.owner` để bảo vệ method trả `Mono<Void>` thực hiện DELETE?

**Đáp án:** Không. `Mono<Void>` không có object owner để inspect; kiểm tra quyền trước DELETE và đưa owner/tenant condition vào câu lệnh.

**Bài 6.** Một reactive transaction rollback DB khi hậu kiểm deny nhưng email đã gửi. Email có bị rollback không?

**Đáp án:** Không. Email ở external system, ngoài transaction DB. Authorize trước khi gửi và dùng outbox/compensation nếu phù hợp.

**Bài 7.** Vì sao `this.securedMethod()` có thể bypass `@PreAuthorize`?

**Đáp án:** Lời gọi nội bộ thường không đi qua Spring AOP proxy. Cần Spring-managed bean boundary và integration test chứng minh annotation được áp dụng.

**Bài 8.** Test chỉ `expectStatus().isForbidden()` trên POST mutation còn thiếu gì?

**Đáp án:** Phải kiểm tra DB không đổi, không có event/email, cache không bị ghi, counter/side-effect phù hợp. Bảo vệ hệ thống là bảo vệ cả trạng thái, không chỉ HTTP response.

**Bài 9.** Response `Flux` đã flush 2 record rồi record thứ ba gây authorization denial. Có thể thu hồi 2 record không?

**Đáp án:** Không. HTTP bytes đã gửi không được thu hồi. Phải authorize trước streaming và query scoped từ nguồn.

**Bài 10.** Khi nào nên tạo transactional outbox event?

**Đáp án:** Chỉ sau khi permission và điều kiện resource update thành công, **trong cùng transaction DB** với update. Dispatcher publish sau commit, có retry và idempotency.

## 13. Checklist review trước production

- [ ] Side-effecting method không chỉ có `@PostAuthorize`.
- [ ] `@PreAuthorize`/policy service thực sự chạy qua Spring AOP proxy.
- [ ] Principal/tenant/owner/ACL đến từ identity và database đáng tin, không đến từ input client không xác thực.
- [ ] SQL UPDATE/DELETE có điều kiện owner/tenant/version và kiểm tra affected rows.
- [ ] Reactive transaction boundary và rollback behavior đã được **kiểm thử**, không phỏng đoán.
- [ ] External email/Kafka/payment/API không phát trước authorization; dùng outbox/idempotency/compensation đúng yêu cầu.
- [ ] Không tự `subscribe()` hoặc `block()` trong reactive handler/method.
- [ ] Không dùng `@PostFilter` thay query ACL hoặc làm hỏng pagination.
- [ ] Không dựa vào `returnObject` cho mutation trả `Mono<Void>`/empty publisher.
- [ ] HTTP response streaming được authorize trước emit đầu tiên.
- [ ] Test HTTP status **và** state trong DB/cache/event/side effects, gồm các case deny.
- [ ] Test CSRF, anonymous 401, authenticated 403, quyền hợp lệ 200.
- [ ] Kiểm tra race condition, retry, idempotency, permission revoked, error và cancellation.
- [ ] Logs không chứa token, password, session ID hay dữ liệu không được phép.
- [ ] Không biến authorization exception thành HTTP 200 bằng fallback quá rộng.

## 14. Tóm tắt kỹ thuật

```text
@PreAuthorize
   Authentication + arguments -> allow / deny
   deny -> ngăn method/work được bảo vệ chạy

@PostAuthorize
   Publisher được subscribe
   -> upstream có thể đã chạy side effect
   -> phát returnObject
   -> hậu kiểm allow / deny
   deny -> không trả result, KHÔNG tự rollback external effects

@PostFilter
   -> lọc phần tử đã được upstream fetch/emit
   -> KHÔNG thay thế query scope / resource-level ACL

An toàn cho mutation
   -> pre-check
   -> authoritative ACL/tenant tại repository
   -> conditional UPDATE/DELETE + transaction
   -> outbox/idempotency cho event và API ngoài
   -> test trạng thái thực bên cạnh HTTP status
```

**Câu quan trọng cần nhớ:** *“Không được nhận kết quả” khác hoàn toàn với “không được thực hiện hành động”.* `@PostAuthorize` bảo vệ quyền **nhận kết quả**, không thay thế quyền **thực hiện mutation**. Những hành động nhạy cảm phải được phân quyền trước khi gây side effect và được ràng buộc tại nơi thay đổi dữ liệu.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive Method Security Tests](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [Spring Security — PostAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security — PreAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security — PostFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PostFilter.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
