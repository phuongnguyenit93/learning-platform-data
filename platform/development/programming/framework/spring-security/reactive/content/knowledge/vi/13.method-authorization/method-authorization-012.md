# Kiểm soát thứ tự thực thi giữa bảo mật, giao dịch và chuỗi reactive

> **Chủ đề:** Spring Security - reactive · **Nhóm:** Phân quyền phương thức

## 1. Mục tiêu

Bài này giải thích cách phối hợp `@PreAuthorize`, `@PostAuthorize`, Spring AOP, `ReactiveSecurityContextHolder`, `@Transactional`, `TransactionalOperator` và các publisher Reactor để tránh thay đổi dữ liệu trước khi kiểm tra quyền, tránh commit khi một bước trong nghiệp vụ thất bại và tránh mất ngữ cảnh bảo mật khi chuyển luồng.

Sau khi học, bạn phải giải thích được **ba thời điểm khác nhau**: lúc Java method được gọi qua proxy; lúc publisher được subscribe; và lúc giao dịch R2DBC commit/rollback. Bạn cũng phải kiểm thử được yêu cầu bị từ chối không sửa database, yêu cầu hợp lệ commit cả UPDATE và audit, lỗi giữa hai thao tác SQL làm rollback.

## 2. Quy tắc duyệt đơn minh họa

Nghiệp vụ phê duyệt đơn yêu cầu:
- Actor đã xác thực, có cả `ROLE_APPROVER` và `SCOPE_orders.approve`.
- Đơn thuộc tenant mà actor được phép thao tác.
- Đơn đang `PENDING`.
- Người duyệt khác người tạo đơn (four-eyes rule).
- Khi hợp lệ, UPDATE trạng thái đơn và INSERT audit **trong cùng một transaction**.

Dữ liệu test: `o-100` thuộc tenant acme, người tạo alice; `o-200` thuộc beta; `o-300` thuộc acme, người tạo reviewer. Actor reviewer có `TENANT_acme`, role và scope cần thiết. Reviewer duyệt o-100 được nhưng không được vượt tenant sang o-200 hay tự duyệt o-300.

~~~mermaid
flowchart TD
  A["Subscriber / HTTP request"] --> B["Method security proxy"]
  B --> C{"@PreAuthorize role + scope?"}
  C -->|"Không"| D["AccessDenied; không có write"]
  C -->|"Có"| E["Transactional reactive publisher"]
  E --> F["SELECT order + kiểm tra tenant/status/creator"]
  F -->|"Không đủ quyền"| G["onError → rollback"]
  F -->|"Hợp lệ"| H["UPDATE order có điều kiện"]
  H --> I["INSERT approval_audit"]
  I -->|"Thành công"| J["onComplete → commit"]
  I -->|"Lỗi"| G
~~~

## 3. Phân biệt ba lớp thứ tự

| Lớp | Công cụ | Điều cần nhớ |
| --- | --- | --- |
| Spring AOP | `@PreAuthorize`, `@PostAuthorize`, `@Transactional` | Advisor chạy trước/sau method; method thường chỉ trả publisher |
| Reactor | `Mono.defer`, `flatMap`, `then`, `contextWrite` | Publisher cold thực thi khi subscribe, không phải khi được tạo |
| R2DBC transaction | `ReactiveTransactionManager`, `TransactionalOperator` | Bao những SQL được subscribe trong cùng context; commit khi work thành công, rollback khi lỗi |

Ví dụ `Mono<String> task = service.approve("o-100")` chưa đồng nghĩa SQL đã chạy. Tuy nhiên Java code đồng bộ đặt **ngoài** Mono (ví dụ `sendEmailImmediately()` trước `return Mono.just(...)`) vẫn chạy lúc method được gọi. Vì thế **trả Mono không tự biến mọi side effect thành lazy**.

## 4. Bảo mật phương thức trước và sau thao tác

Bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` trên một Spring configuration. `@PreAuthorize` kiểm tra trước khi cho method được thực thi; `@PostAuthorize` kiểm tra dựa trên kết quả đã tạo ra, thích hợp cho read-only data authorization. Khi method đã UPDATE hoặc gọi external API, một `AccessDeniedException` do post-authorization **không chứng minh side effect đã được rollback**.

Chính sách đúng cho write là: kiểm tra role/scope **trước use case**, kiểm tra tenant/creator/status **trước UPDATE và ngay gần dữ liệu**, bao UPDATE/audit trong cùng transaction. Không dựa vào hai annotations trên cùng method để suy luận ngầm định commit order.

Spring reactive method security dùng AOP và Reactor Context. Gọi method qua `this.securedMethod()` hoặc tự `new Service()` có thể bypass proxy. Các method cần được gọi qua Spring bean proxy và test qua `@Autowired`.

## 5. Ngữ cảnh reactive và transaction

`ReactiveSecurityContextHolder.getContext()` lấy Authentication từ Reactor Context của subscription. Reactive transaction dùng Reactor Context để gắn connection và transaction synchronization. Cùng dùng cơ chế propagation nhưng **hai loại context không thay thế nhau**.

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Trong test có thể dùng `publisher.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`. Đừng phụ thuộc vào Servlet `SecurityContextHolder.getContext()` ThreadLocal trong WebFlux; đừng tự `subscribe()` ở service hoặc tạo thread/callback detached rồi mong cùng SecurityContext/transaction.

Imperative transaction dùng `PlatformTransactionManager` và JDBC/JPA blocking; reactive transaction dùng `ReactiveTransactionManager` với R2DBC. Với `@Transactional` reactive, method phải trả Publisher, giao dịch thực thi theo subscription và phải đi qua proxy. Với `TransactionalOperator`, phần publisher được bao rõ ràng bằng `work.as(tx::transactional)`.

## 6. Advisor order khác commit order

Trong Spring AOP, advisor precedence cao chạy **sớm khi đi vào** method và **muộn khi đi ra**. Spring Security có `AuthorizationManagerBeforeReactiveMethodInterceptor`, `AuthorizationManagerAfterReactiveMethodInterceptor`, cùng `AuthorizationInterceptorsOrder`. Transaction advice có thể cấu hình `@EnableTransactionManagement(order=...)`; mặc định proxy mode thường là `Ordered.LOWEST_PRECEDENCE`.

~~~text
Advisor A: vào
  Advisor B: vào
    target method → trả Mono
  Advisor B: ra
Advisor A: ra

Subscription sau đó:
  Reactor Context → R2DBC → transaction terminal signal
~~~

**Không suy luận thời điểm COMMIT từ thứ tự annotations trên source.** Một method có cả `@PreAuthorize`, `@Transactional`, `@PostAuthorize` cần test đúng Spring version và advisor/publisher composition. Một cách dễ kiểm chứng là tách facade bảo mật và writer giao dịch, như project dưới đây.

## 7. Dự án Maven Java 17+ runnable

Bài dùng Spring Boot `3.3.13` (Spring Security 6.x) cho lab; nhánh 3.3 không còn hỗ trợ OSS, sản phẩm mới phải chọn version đang được hỗ trợ. Test trực tiếp Spring beans và R2DBC H2, không cần HTTP endpoint.

~~~text
reactive-secure-tx/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/securetx/
    │   │   ├── SecureTxApplication.java
    │   │   ├── TxConfig.java
    │   │   ├── ApprovalFacade.java
    │   │   └── ApprovalWriter.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/securetx/
        └── ApprovalFlowTest.java
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>reactive-secure-tx</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
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
      <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
      <groupId>io.r2dbc</groupId>
      <artifactId>r2dbc-h2</artifactId>
      <scope>runtime</scope>
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
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

### SecureTxApplication.java

~~~java
package demo.securetx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@SpringBootApplication
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecureTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureTxApplication.class, args);
    }
}
~~~

### application.yml

~~~yaml
spring:
  r2dbc:
    url: "r2dbc:h2:mem:///securetx163?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
~~~

### schema.sql

~~~sql
CREATE TABLE purchase_orders (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  created_by VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL
);

CREATE TABLE approval_audit (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL,
  actor VARCHAR(64) NOT NULL
);
~~~

### data.sql

~~~sql
INSERT INTO purchase_orders (id, tenant_id, created_by, status) VALUES
  ('o-100', 'acme', 'alice', 'PENDING'),
  ('o-200', 'beta', 'bob', 'PENDING'),
  ('o-300', 'acme', 'reviewer', 'PENDING');
~~~

Các file YAML/SQL nằm trong `src/main/resources`. `DB_CLOSE_DELAY=-1` giữ H2 in-memory database sau khi connection đóng. Spring Boot SQL initializer nạp schema/data cho lab. Không dùng SQL scripts này để thay migrations production.

## 8. TxConfig: ReactiveTransactionManager → TransactionalOperator

File `src/main/java/demo/securetx/TxConfig.java`:

~~~java
package demo.securetx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TxConfig {
    @Bean
    TransactionalOperator tx(ReactiveTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Spring Boot cấu hình `R2dbcTransactionManager` khi có ConnectionFactory phù hợp. TransactionalOperator không tự tạo dữ liệu hay phân quyền; nó bao một publisher được chọn trong transaction với tài nguyên Reactor Context.

## 9. ApprovalFacade: chặn sớm role và scope

File `src/main/java/demo/securetx/ApprovalFacade.java`:

~~~java
package demo.securetx;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ApprovalFacade {
    private final ApprovalWriter writer;

    public ApprovalFacade(ApprovalWriter writer) {
        this.writer = writer;
    }

    @PreAuthorize(
        "hasRole('APPROVER') and hasAuthority('SCOPE_orders.approve')")
    public Mono<String> approve(String id) {
        return writer.approveInsideTransaction(id, false);
    }
}
~~~

Facade chỉ chặn quyền tổng quát, chưa biết owner/tenant/status của record. Writer vẫn kiểm tra quyền thêm lần nữa để bảo vệ nếu adapter khác vô tình gọi thẳng, và làm tất cả data-level checks trong transactional publisher.

## 10. ApprovalWriter: kiểm tra domain rồi UPDATE + audit atomically

File `src/main/java/demo/securetx/ApprovalWriter.java`:

~~~java
package demo.securetx;

import org.springframework.http.HttpStatus;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

record OrderRow(String id, String tenant, String creator, String status) {}

@Service
public class ApprovalWriter {
    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public ApprovalWriter(DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    public Mono<String> approveInsideTransaction(
            String id, boolean failAfterUpdate) {
        Mono<String> work = Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .switchIfEmpty(Mono.error(
                    new AccessDeniedException("No security context")))
                .map(ctx -> ctx.getAuthentication())
                .flatMap(auth -> approveForActor(id, failAfterUpdate, auth))
        );
        return work.as(tx::transactional);
    }

    private Mono<String> approveForActor(
            String id, boolean failAfterUpdate, Authentication auth) {
        if (!auth.isAuthenticated()
                || !has(auth, "ROLE_APPROVER")
                || !has(auth, "SCOPE_orders.approve")) {
            return Mono.error(new AccessDeniedException("Denied"));
        }

        return db.sql(
            "SELECT id, tenant_id, created_by, status " +
            "FROM purchase_orders WHERE id = :id")
            .bind("id", id)
            .map((r, m) -> new OrderRow(
                r.get(0, String.class), r.get(1, String.class),
                r.get(2, String.class), r.get(3, String.class)))
            .one()
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)))
            .flatMap(order -> {
                boolean tenantOk = has(auth, "TENANT_" + order.tenant());
                boolean notCreator =
                    !order.creator().equals(auth.getName());
                boolean pending = "PENDING".equals(order.status());

                if (!tenantOk || !notCreator || !pending) {
                    return Mono.error(new AccessDeniedException("Denied"));
                }

                return db.sql(
                    "UPDATE purchase_orders SET status = 'APPROVED' " +
                    "WHERE id = :id AND status = 'PENDING'")
                    .bind("id", id).fetch().rowsUpdated()
                    .flatMap(updated -> {
                        if (updated != 1L) {
                            return Mono.error(new IllegalStateException(
                                "Concurrent modification"));
                        }
                        if (failAfterUpdate) {
                            return Mono.error(new IllegalStateException(
                                "Simulated audit failure"));
                        }
                        return db.sql(
                            "INSERT INTO approval_audit " +
                            "(order_id, actor) VALUES (:id, :actor)")
                            .bind("id", id)
                            .bind("actor", auth.getName())
                            .fetch().rowsUpdated()
                            .flatMap(inserted -> inserted == 1L
                                ? Mono.just("APPROVED")
                                : Mono.error(new IllegalStateException(
                                    "Audit failure")));
                    });
            });
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }
}
~~~

Khi subscribe, transaction bao toàn bộ `work`: lấy Authentication, SELECT, domain checks, UPDATE và INSERT audit. Nếu lỗi giữa UPDATE và audit, `onError` đi tới operator và rollback. Nếu thành công, `onComplete` mới commit.

Điểm tinh tế: UPDATE có `WHERE status='PENDING'` và `rowsUpdated()==1` để phát hiện một số races khi trạng thái bị đổi. Trong hệ thống thật cần transaction isolation, optimistic locking/version và xử lý idempotency theo nghiệp vụ.

## 11. Integration test với StepVerifier và database

File `src/test/java/demo/securetx/ApprovalFlowTest.java`:

~~~java
package demo.securetx;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ApprovalFlowTest {
    @Autowired ApprovalFacade facade;
    @Autowired ApprovalWriter writer;
    @Autowired DatabaseClient db;

    private Authentication actor(String name, String... permissions) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, AuthorityUtils.createAuthorityList(permissions));
    }

    private Authentication reviewer() {
        return actor("reviewer",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_acme");
    }

    private Mono<String> as(Mono<String> mono, Authentication auth) {
        return mono.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private String status() {
        return db.sql(
            "SELECT status FROM purchase_orders WHERE id = 'o-100'")
            .map((r, m) -> r.get(0, String.class))
            .one().block();
    }

    private long auditCount() {
        return db.sql(
            "SELECT COUNT(*) FROM approval_audit WHERE order_id = 'o-100'")
            .map((r, m) -> ((Number) r.get(0)).longValue())
            .one().block();
    }

    @BeforeEach
    void reset() {
        db.sql(
            "UPDATE purchase_orders SET status = 'PENDING' " +
            "WHERE id = 'o-100'")
            .fetch().rowsUpdated().block();
        db.sql("DELETE FROM approval_audit")
            .fetch().rowsUpdated().block();
    }

    @Test
    void missingScopeDoesNotWrite() {
        Authentication noScope =
            actor("reviewer", "ROLE_APPROVER", "TENANT_acme");
        StepVerifier.create(as(facade.approve("o-100"), noScope))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void permittedActorCommitsBothWrites() {
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectNext("APPROVED").verifyComplete();
        assertEquals("APPROVED", status());
        assertEquals(1L, auditCount());
    }

    @Test
    void wrongTenantCannotWrite() {
        Authentication beta = actor("reviewer",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_beta");
        StepVerifier.create(as(facade.approve("o-100"), beta))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void creatorCannotApproveOwnOrder() {
        Authentication alice = actor("alice",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_acme");
        StepVerifier.create(as(facade.approve("o-100"), alice))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
    }

    @Test
    void auditFailureRollsBackUpdate() {
        StepVerifier.create(as(
            writer.approveInsideTransaction("o-100", true), reviewer()))
            .expectError(IllegalStateException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void missingContextIsDenied() {
        StepVerifier.create(facade.approve("o-100"))
            .expectError().verify();
        assertEquals("PENDING", status());
    }

    @Test
    void coldMonoDoesNotWriteBeforeSubscribe() {
        Mono<String> operation =
            as(facade.approve("o-100"), reviewer());
        assertEquals("PENDING", status());
        StepVerifier.create(operation)
            .expectNext("APPROVED").verifyComplete();
        assertEquals("APPROVED", status());
    }

    @Test
    void secondApprovalIsRejected() {
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectNext("APPROVED").verifyComplete();
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectError(AccessDeniedException.class).verify();
        assertEquals(1L, auditCount());
    }
}
~~~

Test được thực thi qua Spring bean `@Autowired`, không phải object tự `new`. `contextWrite` cung cấp SecurityContext của subscriber. `block()` chỉ ở JUnit test thread để quan sát trạng thái DB, không nằm trong WebFlux service.

| Test | Publisher | DB cuối cùng |
| --- | --- | --- |
| Thiếu scope | AccessDeniedException | PENDING, 0 audit |
| Đủ role/scope/tenant | APPROVED rồi complete | APPROVED, 1 audit |
| Sai tenant | AccessDeniedException | PENDING, 0 audit |
| Người tạo tự duyệt | AccessDeniedException | PENDING |
| Lỗi giữa UPDATE và audit | IllegalStateException | PENDING, 0 audit |
| Thiếu Authentication | onError | PENDING |
| Chưa subscribe Mono | Chưa ghi | PENDING |
| Duyệt hai lần | Lần 2 denied | Chỉ 1 audit |

Chạy `mvn clean test`. Kỳ vọng **8 JUnit tests PASS**. Đây là test method security/transaction; chưa chứng minh HTTP status, JWT signature hay CSRF của một endpoint thực.

## 12. @Transactional và TransactionalOperator khác nhau thế nào?

Reactive `@Transactional` có thể bảo vệ publisher trả về bởi một method bean nếu có `ReactiveTransactionManager`. Ví dụ cú pháp độc lập (chưa có authorization, không được expose như API):

~~~java
package demo.securetx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
class TransactionalExample {
    private final DatabaseClient db;
    TransactionalExample(DatabaseClient db) { this.db = db; }

    @Transactional
    public Mono<Long> markApproved(String id) {
        return db.sql(
            "UPDATE purchase_orders SET status='APPROVED' " +
            "WHERE id=:id AND status='PENDING'")
            .bind("id", id).fetch().rowsUpdated();
    }
}
~~~

Annotation phụ thuộc Spring AOP proxy, rất dễ bị self-invocation; operator không cần proxy để tạo transaction nhưng có thể bị đặt scope sai. **Không trộn hai cơ chế cho cùng workflow** nếu chưa xác định rõ propagation. Với method transaction thật, giữ mọi SQL và domain checks trong publisher return, không tự subscribe và không dùng manager JDBC blocking.

## 13. Sai lầm về AOP, publisher và rollback

### Self-invocation

~~~java
@Service
class WrongService {
    public Mono<String> process(String id) {
        return this.protectedMethod(id);
    }

    @PreAuthorize("hasRole('APPROVER')")
    @Transactional
    public Mono<String> protectedMethod(String id) {
        return Mono.just("ok");
    }
}
~~~

Code minh họa lỗi: lời gọi qua `this` thường bypass proxy method security/transaction. Tách facade và writer như project runnable; test qua Spring bean.

### Subscribe lồng nhau

~~~java
public Mono<String> wrong(String id) {
    repository.update(id).subscribe();
    return Mono.just("APPROVED");
}
~~~

Đây là pseudocode với repository giả định. UPDATE chạy trong subscription khác, có thể mất SecurityContext, transaction, error propagation và thứ tự. Thay bằng publisher được trả về, nối `flatMap`/`then` rồi subscribe ở tầng sở hữu vòng đời.

### Chỉ bao UPDATE, bỏ audit

~~~java
Mono<Long> update = repository.update(id).as(tx::transactional);
return update.then(repository.insertAudit(id));
~~~

Sai vì audit nằm ngoài transaction đã commit. Đúng về vị trí scope:

~~~java
Mono<String> work = repository.update(id)
    .then(repository.insertAudit(id))
    .thenReturn("APPROVED");
return work.as(tx::transactional);
~~~

Các đoạn trên là **mô hình operator**, không phải class runnable. Project thật ở mục 10 bao domain check và cả hai SQL.

### Nuốt lỗi trong transaction

~~~java
Mono<String> risky = repository.update(id)
    .then(repository.insertAudit(id))
    .onErrorResume(ex -> Mono.just("ignored"))
    .as(tx::transactional);
~~~

Nếu audit error bị chuyển thành complete **trước ranh giới transaction**, transaction có thể commit UPDATE. Hãy để error tới transaction operator để rollback, rồi ánh xạ lỗi thành response bên ngoài tx. Đừng dùng `Mono.empty()` cho deny nếu downstream `then(otherWrite)` sẽ coi đó là thành công.

## 14. Retry, cancellation và tác dụng phụ ngoài DB

- `onError` đi qua transaction: rollback. `onComplete`: commit khi các điều kiện được thỏa.
- `cancel` (ví dụ `take(1)` trên Flux) có thể làm reactive transaction rollback theo Spring Framework hiện đại; không mặc định consumer chỉ đọc một phần đồng nghĩa commit.
- `retryWhen` resubscribe publisher, có thể lặp lại SQL và side effects. Cần idempotency/optimistic locking/unique event ID.
- `timeout` và upstream cancellation có thể dừng workflow, phải test theo DB/driver thật.
- `flatMap` có thể chạy concurrent; nếu cần tuần tự, cân nhắc `concatMap` và transaction scope phù hợp.
- `publishOn` trong cùng Reactor pipeline không tự làm mất context; thread hoặc subscribe tách rời mới đáng nghi.

Database transaction không thể thu hồi email hay HTTP call đã gửi trước rollback. Dùng **transactional outbox**: UPDATE order, INSERT audit, INSERT outbox event trong cùng DB transaction; sau commit worker publish, receiver xử lý event ID idempotently. Không coi `send().subscribe()` là after-commit event.

## 15. HTTP và phân quyền dữ liệu trong production

Một HTTP request thực có thêm `SecurityWebFilterChain` để xác thực và lập Reactor SecurityContext. Controller gọi facade qua Spring bean, facade áp dụng `@PreAuthorize`, writer kiểm tra tenant/status/owner và mutation atomically. Thiếu credentials thường 401; authenticated nhưng thiếu quyền là 403; bản ghi không tồn tại có thể 404; conflict do concurrency có thể 409 theo API contract. Test trực tiếp Spring bean chỉ thấy exceptions, không tự có HTTP status.

Khi dùng JWT, token cần xác minh chữ ký, issuer, expiry, audience, và claim-to-authority mapping. Không tin tenant do client gửi trong header hay query. Khi dùng browser session/Basic, phải xem CSRF vì credentials có thể được trình duyệt gửi tự động; không tắt CSRF chỉ để POST chạy.

Người dùng đã có role/scope vẫn có thể bị từ chối nếu tenant hoặc trạng thái record thay đổi. Authorization theo domain phải kiểm tra gần dữ liệu, không chỉ tin claims cũ của session/token. Với tác vụ viết quan trọng, thêm optimistic locking/isolation, kiểm soát retries và idempotency.

## 16. Ma trận lỗi cần chẩn đoán

| Hiện tượng | Khả năng | Hướng xử lý |
| --- | --- | --- |
| Denied nhưng DB đổi | Side effect eager / @PostAuthorize sau commit | Pre-check, transactional domain policy, DB test |
| Annotation không chạy | Không enable method security, self-invocation | Test qua @Autowired proxy |
| Context rỗng | ThreadLocal, nested subscribe, thiếu contextWrite | Reactor SecurityContext đúng subscription |
| DB không rollback | Transaction bao sai publisher, lỗi bị nuốt | TransactionalOperator scope, onError |
| Audit thiếu nhưng order APPROVED | UPDATE đã commit trước audit | Bao cả hai trong cùng transaction |
| Đơn duyệt lặp | Không có status/version condition | Conditional update, rowsUpdated |
| Email gửi dù DB rollback | External side effect không atomic với DB | Outbox/idempotency |
| Test lẫn trạng thái | Không reset fixture | @BeforeEach và DB readback |
| Timeout/policy store lỗi rồi allow | Fail-open | Fail closed, giám sát |

**Thứ tự điều tra:** gọi qua proxy chưa → Authentication có trong Reactor Context chưa → pre-check đã chặn chưa → publisher nào được subscribe → tx bao đúng thao tác chưa → lỗi/cancel có truyền tới operator chưa → DB thực sự lưu gì.

## 17. Bài tập và checklist

**Bài A:** tạo `Mono` nhưng chưa subscribe; chứng minh DB PENDING. Sau StepVerifier thành công, DB APPROVED.

**Bài B:** đưa audit ra ngoài `work.as(tx)` trong bản lab, giả lập lỗi và quan sát sai khác rollback; khôi phục.

**Bài C:** thêm `onErrorResume` trước operator để nuốt lỗi; test và giải thích khi nào commit sai.

**Bài D:** gọi protected method qua `this`, chứng minh proxy bypass, sửa lại hai bean.

**Bài E:** thử actor đúng role/scope nhưng sai tenant và actor tự duyệt đơn của mình. Đều phải không có write.

**Bài F:** thử hai approval đồng thời, thêm version column hoặc conditional update và test idempotency.

**Bài G:** tạo Flux transactional bị cancel bằng `take(1)`; xem rollback/commit bằng DB test.

**Bài H:** thêm outbox table cho event OrderApproved và worker publish sau commit.

**Checklist:**
- [ ] Phân biệt method invocation, subscription và transaction terminal signals.
- [ ] Không dùng @PostAuthorize làm rollback guarantee.
- [ ] Gọi qua Spring bean proxy, tránh self-invocation.
- [ ] Không tự subscribe hoặc chạy side effect đồng bộ trước authorization.
- [ ] Dùng đúng ReactiveTransactionManager và publisher cold.
- [ ] Domain checks, UPDATE và audit nằm trong một transaction.
- [ ] Có negative tests và xác minh DB rollback khi audit fail.
- [ ] Hiểu onErrorResume, retry, cancel, timeout và outbox.
- [ ] Không nhầm quyền HTTP với quyền thực tế theo tenant/object.

## 18. Tài liệu tham khảo

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): method-security advisors, Reactor Context.
- [Spring Security — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html): thứ tự interceptors.
- [Spring Framework — Transaction Management Explained](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): reactive vs imperative transactions.
- [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, advisor order.
- [Spring Framework — TransactionalOperator](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): transaction scope và cancel semantics.
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): R2DBC connections.
- [Spring Boot — SQL Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql/data.sql.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, quyền object.

**Kết luận:** Quy tắc an toàn là chặn quyền tổng quát bằng `@PreAuthorize` trước use case; lấy và kiểm tra trạng thái nghiệp vụ đúng lúc trong transaction; nối mọi SQL cần nguyên tử thành một publisher không có nested subscription; cho lỗi đến TransactionalOperator để rollback; và dùng DB readback xác minh chứ không chỉ tin vào HTTP status.