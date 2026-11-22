# Giữ logic nghiệp vụ độc lập với vòng đời tài nguyên kỹ thuật khi thiết kế Repository JPA

Một ứng dụng dùng Jakarta Persistence (JPA) không chỉ cần ghi và đọc entity đúng. Nó còn phải bảo đảm những **quy tắc nghiệp vụ** vẫn đúng khi thay đổi cấu hình transaction, JPA provider, cách quản lý `EntityManager`, cơ chế retry, chiến lược tải dữ liệu hoặc thậm chí chuyển một tác vụ sang background worker.

Ví dụ, quy tắc:

> “Chỉ có thể xác nhận một lượt đặt chỗ đang ở trạng thái DRAFT, có số lượng hợp lệ và thuộc về đúng khách hàng/tổ chức được phép.”

là một quy tắc của **nghiệp vụ**. Quy tắc ấy không nên nằm trong một chuỗi thao tác phụ thuộc vào:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();
tx.begin();

// Nghiệp vụ trộn lẫn với persistence.

em.flush();
tx.commit();
em.close();
~~~

Khi business decisions và thao tác kỹ thuật bị trộn vào cùng phương thức, mỗi lần chuyển từ `RESOURCE_LOCAL` sang JTA/Spring, thay fetch strategy, thêm audit hoặc xử lý lỗi database có thể kéo theo thay đổi những quy tắc vốn không liên quan database.

Bài học này giải thích cách thiết kế **Repository như ranh giới giữa mô hình nghiệp vụ và cơ chế lưu trữ**, để:

- Domain quyết định **điều gì được phép xảy ra**.
- Application service điều phối **một trường hợp sử dụng và ranh giới giao dịch**.
- Repository abstraction cung cấp **ngôn ngữ truy cập aggregate**.
- JPA adapter quản lý **entity state, flush, khóa, query và technical exceptions**.
- Infrastructure/container quản lý **connection, persistence context, transaction manager và cleanup**.

Điều đó **không có nghĩa phải loại bỏ JPA hoàn toàn khỏi mọi domain class** trong mọi dự án. Có nhiều mức đánh đổi. Mục tiêu thực tế là không để nghiệp vụ phụ thuộc vào **thời điểm mở/đóng tài nguyên, provider-specific API hoặc đường đi ngẫu nhiên của SQL**.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **business invariants**, **use-case orchestration**, **repository contracts** và **technical resource lifecycle**.
2. Giải thích tại sao `EntityManager`, persistence context, JDBC connection và transaction không cùng một khái niệm.
3. Xác định nơi nên đặt `@Transactional`, `flush()`, `clear()` và `close()`.
4. Viết domain model có thể kiểm thử mà không cần JPA runtime.
5. Thiết kế repository port trả về aggregate hoặc domain-oriented result thay vì rò rỉ JPA Query/EntityManager.
6. Viết JPA adapter dùng managed entities/DTO mapping theo scope transaction.
7. Xử lý optimistic locking, rollback, validation và external side effects mà không nhúng chi tiết hạ tầng vào domain.
8. Nhận diện các lỗi lazy loading, detached entities, N+1 và OSIV do boundary đặt sai.
9. Phân biệt unit test nghiệp vụ với integration test persistence/transaction.
10. Cân nhắc kiến trúc JPA entities trực tiếp trong domain so với tách persistence model.

## 2. Hai loại vòng đời không nên trộn

**Vòng đời nghiệp vụ** mô tả trạng thái có ý nghĩa với domain:

~~~text
Reservation:
  DRAFT -> CONFIRMED -> FULFILLED
      \       |
       \      v
        ---> CANCELED
~~~

**Vòng đời kỹ thuật** của một lần lưu trữ có thể là:

~~~text
Acquire EntityManager / persistence context
          |
          v
Begin transaction
          |
          v
Query / materialize / manage entities
          |
          v
Dirty checking + flush SQL
          |
          v
Commit or rollback
          |
          v
Release resources
~~~

Hai vòng đời tương tác với nhau, nhưng không đồng nhất.

Một Reservation đã **CONFIRMED về mặt Java object** không có nghĩa transaction đã commit. Ngược lại, một transaction commit thành công không tự bảo đảm domain operation đã kiểm tra đúng mọi invariant nếu code bỏ qua domain method.

### Bài học

Domain state transition là **quy tắc nghiệp vụ**; transaction commit là **đảm bảo kỹ thuật về atomicity và durability**. Thiết kế tốt kết hợp chúng, nhưng không để domain method tự quản lý tài nguyên lưu trữ.

## 3. EntityManager không phải “database connection” đơn thuần

`EntityManager` là API JPA để làm việc với persistence context, entity state và queries.

Một cách hiểu:

~~~text
Application service
       |
       v
EntityManager (JPA)
       |
       v
Persistence context
  identity map / state tracking / actions
       |
       v
JPA provider / JDBC
       |
       v
Database connection / transaction resources
~~~

Các scope có thể khác nhau:

- Một transaction-scoped persistence context có thể gắn với transaction.
- Application-managed EntityManager có lifecycle do ứng dụng quyết định.
- Trong JTA/container-managed environment, connection acquisition/release có thể lazy và do framework/provider điều phối.
- Database transaction, persistence context và JDBC connection có những mốc bắt đầu/kết thúc không nhất thiết trùng nhau trong mọi provider.

**Không dùng `EntityManager` như một global singleton hoặc truyền nó khắp domain** với giả định “chỉ là một connection”.

## 4. Vòng đời tài nguyên kỹ thuật gồm những gì?

| Tài nguyên | Trách nhiệm | Vì sao không thuộc domain rule |
| --- | --- | --- |
| `EntityManager` | Quản lý persistence context/query operations | Domain không nên biết lúc mở/đóng |
| Persistence context | Identity map, dirty tracking, lifecycle | Domain logic không nên dựa vào L1 cache |
| `EntityTransaction` | Begin/commit/rollback RESOURCE_LOCAL | Quy tắc xác nhận không đồng nghĩa commit |
| JTA/Spring transaction manager | Ranh giới giao dịch/container | Độc lập với trạng thái domain |
| JDBC Connection | Tương tác database | Domain không nên yêu cầu connection |
| PreparedStatement/ResultSet | SQL execution, result iteration | Domain không nên đóng cursor |
| Lock/timeout | Concurrency/resource protection | Policy nghiệp vụ tách implementation |
| Second-level cache | Cache shared theo provider | Tối ưu hạ tầng |
| Messaging client | Gửi sự kiện ngoài DB | Không gọi mạng trong domain method |

Domain có thể diễn đạt ý định như “xác nhận lượt đặt chỗ”, “thất bại vì đã hủy”, nhưng không nên trực tiếp gọi `commit()` hoặc đọc Hibernate `Session` để quyết định trạng thái.

## 5. Ranh giới các tầng

Một cấu trúc điển hình:

~~~text
HTTP / CLI / Scheduler
        |
        v
Application service / Use case
  - authenticated principal
  - authorization
  - transaction boundary
  - repository calls
  - domain operations
        |
        v
Domain model
  - entities / value objects
  - invariants
  - transitions
  - domain events
        ^
        |
Repository port (interface)
        ^
        |
JPA repository adapter
  - EntityManager
  - JPQL / Criteria
  - persistence mapping
  - technical exception mapping
        |
        v
JPA provider + database
~~~

Phụ thuộc theo mã nguồn thường hướng vào domain/application contracts:

~~~text
Application -> Domain
Infrastructure -> Repository port + Domain
Domain -X-> Infrastructure
~~~

Không phải mọi dự án bắt buộc có từng module JAR riêng. Sự phân tách có thể bắt đầu bằng packages và API boundaries rõ ràng.

## 6. Quy tắc đặt trách nhiệm

Hỏi một câu trước khi thêm logic:

> “Nếu ngày mai đổi Hibernate thành provider khác hoặc đổi transaction manager, quy tắc này có còn nguyên không?”

Nếu **có**, nó có khả năng là logic domain/application độc lập hạ tầng.

Nếu logic liên quan:

- JPQL syntax.
- `em.find()`.
- `flush()/clear()`.
- JDBC cursor/stream.
- Retry vì SQL state.
- Connection/transaction manager.

thì đó là chi tiết persistence/application infrastructure.

### Không đồng nghĩa mọi validation đều ở domain

- Input format/HTTP DTO validation thuộc boundary.
- User permission và tenant scope thường thuộc application/security.
- “Không thể CONFIRM một Reservation đã CANCELED” là domain invariant.
- SQL UNIQUE/FK/CHECK là database constraints và defense-in-depth.

Những tầng này bổ sung nhau, không thay thế nhau.

## 7. Anti-pattern: EntityManager nằm trong domain entity

Ví dụ không nên thiết kế:

~~~java
public class Reservation {

    public void confirm(EntityManager em) {
        if (status != Status.DRAFT) {
            throw new IllegalStateException(
                "Không thể xác nhận");
        }

        status = Status.CONFIRMED;
        em.merge(this);
        em.flush();
    }
}
~~~

Các vấn đề:

- Domain method yêu cầu JPA runtime để kiểm thử.
- Không rõ ai sở hữu transaction và rollback.
- `merge(this)` có semantics khác việc sửa managed instance.
- `flush()` có thể phát SQL trước thời điểm caller muốn.
- Domain không còn dùng được trong một batch memory-only simulation.
- Khi đổi persistence strategy, business method phải thay.

### Hướng thay thế

~~~java
public void confirm() {
    if (status != Status.DRAFT) {
        throw new InvalidReservationTransition(
            "Chỉ DRAFT mới được xác nhận");
    }

    status = Status.CONFIRMED;
}
~~~

Domain chỉ thực hiện hợp lệ hóa và transition. Application service chịu trách nhiệm load/save và transaction boundary.

## 8. Anti-pattern: Repository tự quyết định nghiệp vụ

Ví dụ:

~~~java
public void confirm(UUID reservationId) {
    em.createQuery(
        "UPDATE ReservationRecord r " +
        "SET r.status = 'CONFIRMED' " +
        "WHERE r.id = :id")
      .setParameter("id", reservationId)
      .executeUpdate();
}
~~~

Ở đây repository tự thay trạng thái mà không đảm bảo:

- Đang ở DRAFT hay đã CANCELED.
- Tenant/authorization phù hợp.
- Có đủ dữ liệu và business preconditions.
- Có domain event cần phát.
- Có optimistic version check.

### Có phải bulk update luôn sai?

Không. Nếu use case thật sự là “expire tất cả DRAFT quá hạn”, một bulk update có điều kiện, version/tenant policy và side effects được thiết kế phù hợp có thể hợp lệ. Nhưng nó phải là **quyết định kiến trúc/ứng dụng có cân nhắc**, không phải repository tự âm thầm bỏ invariants để tối ưu SQL.

## 9. Domain API nên nói bằng ngôn ngữ nghiệp vụ

So sánh:

~~~java
reservation.setStatus(Status.CONFIRMED);
~~~

và:

~~~java
reservation.confirm();
~~~

Phương thức `confirm()` có thể bảo đảm:

- Chỉ từ DRAFT.
- Số lượng > 0.
- Thời hạn chưa hết.
- Giữ nguyên identity và owner.
- Tạo domain event để application sử dụng.

Với setter public, mọi caller có thể đưa aggregate vào trạng thái bất hợp lệ.

### Không biến domain thành một tập getters/setters

Một domain model có hành vi giúp bảo vệ invariants kể cả khi code không chạy trong persistence context.

## 10. Ví dụ xuyên suốt: Reservation

Giả sử hệ thống cho đặt chỗ trước một số lượng sản phẩm.

Quy tắc:

1. Reservation được tạo với số lượng nguyên dương.
2. Mỗi Reservation thuộc một tenant/customer.
3. DRAFT có thể được xác nhận.
4. CANCELED không thể được xác nhận lại.
5. CONFIRMED không được “xác nhận thêm lần nữa” nếu API contract không idempotent.
6. Khi confirm thành công, hệ thống ghi một sự kiện để các hệ thống khác biết.

Không phải mọi quy tắc này được bảo đảm bằng `@Column(nullable=false)`. Mapping chỉ giúp database giữ một phần constraints; domain quyết định transition hợp lệ.

## 11. Domain state và domain exception

~~~java
package com.example.reservation.domain;

public enum ReservationStatus {
    DRAFT,
    CONFIRMED,
    CANCELED
}
~~~

Exception domain:

~~~java
package com.example.reservation.domain;

public final class InvalidReservationTransition
        extends RuntimeException {

    public InvalidReservationTransition(String message) {
        super(message);
    }
}
~~~

`InvalidReservationTransition` không kế thừa `PersistenceException` vì lỗi này là lỗi trạng thái nghiệp vụ, không phải vấn đề ORM.

## 12. Domain entity không phụ thuộc JPA

~~~java
package com.example.reservation.domain;

import java.time.Instant;
import java.util.UUID;

public final class Reservation {

    private final UUID id;
    private final UUID tenantId;
    private final UUID customerId;
    private final int units;
    private final Instant expiresAt;
    private ReservationStatus status;

    public Reservation(
            UUID id,
            UUID tenantId,
            UUID customerId,
            int units,
            Instant expiresAt,
            ReservationStatus status) {

        if (id == null || tenantId == null
                || customerId == null || expiresAt == null
                || status == null) {
            throw new IllegalArgumentException(
                "Các trường bắt buộc không được null");
        }

        if (units <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải dương");
        }

        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.units = units;
        this.expiresAt = expiresAt;
        this.status = status;
    }

    public void confirm(Instant now) {
        if (now == null) {
            throw new IllegalArgumentException(
                "now không được null");
        }

        if (status != ReservationStatus.DRAFT) {
            throw new InvalidReservationTransition(
                "Chỉ DRAFT mới được xác nhận");
        }

        if (!now.isBefore(expiresAt)) {
            throw new InvalidReservationTransition(
                "Reservation đã hết hạn");
        }

        status = ReservationStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != ReservationStatus.DRAFT) {
            throw new InvalidReservationTransition(
                "Chỉ DRAFT mới được hủy");
        }
        status = ReservationStatus.CANCELED;
    }

    public UUID id() { return id; }
    public UUID tenantId() { return tenantId; }
    public UUID customerId() { return customerId; }
    public int units() { return units; }
    public Instant expiresAt() { return expiresAt; }
    public ReservationStatus status() { return status; }
}
~~~

### Vì sao truyền `Instant now`?

Domain không cần tự đọc static `Instant.now()` hoặc phụ thuộc vào một infrastructure clock. Application service có thể truyền thời điểm từ `Clock` được inject.

Điều này giúp test những trường hợp “trước hạn”, “đúng hạn” và “sau hạn” một cách deterministic.

### Có nên đưa `Clock` vào domain?

Domain có thể nhận `Clock` abstraction hoặc `Instant`. Với transition đơn giản, truyền thời điểm rõ ràng giúp method thuần về mặt tài nguyên. Lựa chọn cụ thể phụ thuộc complexity.

## 13. Unit test domain không cần database

~~~java
@Test
void draftCanBeConfirmedBeforeExpiry() {
    Instant expires =
        Instant.parse("2030-01-01T00:00:00Z");

    Reservation reservation = new Reservation(
        UUID.randomUUID(),
        UUID.randomUUID(),
        UUID.randomUUID(),
        2,
        expires,
        ReservationStatus.DRAFT
    );

    reservation.confirm(
        Instant.parse("2029-12-31T23:00:00Z")
    );

    assertEquals(
        ReservationStatus.CONFIRMED,
        reservation.status()
    );
}
~~~

Không có `EntityManagerFactory`, database, `@Transactional` hoặc container start-up.

### Test trạng thái không hợp lệ

~~~java
@Test
void canceledReservationCannotBeConfirmed() {
    Reservation r = new Reservation(
        UUID.randomUUID(),
        UUID.randomUUID(),
        UUID.randomUUID(),
        1,
        Instant.parse("2030-01-01T00:00:00Z"),
        ReservationStatus.CANCELED
    );

    assertThrows(
        InvalidReservationTransition.class,
        () -> r.confirm(
            Instant.parse("2029-01-01T00:00:00Z")
        )
    );
}
~~~

Những test nhanh này kiểm tra **business invariant**, không kiểm tra transaction hoặc SQL.

## 14. Repository port diễn đạt khả năng cần thiết

Interface trong domain/application boundary:

~~~java
package com.example.reservation.domain;

import java.util.Optional;
import java.util.UUID;

public interface ReservationRepository {

    Optional<Reservation> findInTenant(
        UUID reservationId,
        UUID tenantId
    );

    void save(Reservation reservation);
}
~~~

Interface:

- Không lộ `EntityManager`.
- Không trả `TypedQuery` hoặc `Session`.
- Không yêu cầu caller quyết định `flush()`.
- Nêu phương thức nghiệp vụ cần: tìm trong tenant, lưu aggregate.

### Repository không phải generic CRUD bắt buộc

Một port với hàng chục generic methods `findAll()`, `merge()`, `detach()`, `flush()` có thể lộ chính những chi tiết muốn che. Thiết kế API theo use cases và aggregate boundaries.

## 15. Application service điều phối use case

Application service thực hiện:

~~~text
Input command
    |
    v
Get trusted tenant/user
    |
    v
Check permission
    |
    v
Repository.findInTenant
    |
    v
Domain.confirm(now)
    |
    v
Repository.save
    |
    v
Commit transaction / outbox effects
~~~

### Vai trò

- Xác định use-case transaction boundary.
- Đưa dependencies như repository, Clock, authorization vào workflow.
- Gọi domain methods, không thay domain rules bằng setter/SQL.
- Điều phối events và external effects theo consistency protocol.
- Trả kết quả DTO đơn giản, không trả JPA-managed graph tùy ý.

Domain không cần biết service dùng Spring, Jakarta Transactions hay manual resource-local transactions.

## 16. Application service với Spring @Transactional

~~~java
package com.example.reservation.application;

import com.example.reservation.domain.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

@Service
public class ConfirmReservationService {

    private final ReservationRepository reservations;
    private final AuthorizationService authorization;
    private final Clock clock;

    public ConfirmReservationService(
            ReservationRepository reservations,
            AuthorizationService authorization,
            Clock clock) {
        this.reservations = reservations;
        this.authorization = authorization;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID reservationId) {
        UUID tenantId =
            authorization.requireTenantWithPermission(
                "reservation:confirm");

        Reservation reservation = reservations
            .findInTenant(reservationId, tenantId)
            .orElseThrow(
                () -> new ReservationNotFound(reservationId)
            );

        reservation.confirm(Instant.now(clock));
        reservations.save(reservation);
    }
}
~~~

`AuthorizationService` và `ReservationNotFound` là application-level contracts/types, không phải JPA APIs. Có thể định nghĩa:

~~~java
public interface AuthorizationService {
    UUID requireTenantWithPermission(String permission);
}
~~~

### Vì sao @Transactional ở service?

Đây là ranh giới của một **use case**, gồm load, kiểm tra transition, save và các thay đổi transactional khác. Nếu mỗi repository method tự mở và commit một transaction riêng, một use case có nhiều repositories có thể không còn atomic.

### Lưu ý Spring proxy

`@Transactional` chỉ có hiệu lực khi Spring transaction infrastructure thực sự intercept invocation. Self-invocation trong cùng bean, private methods hoặc tạo service bằng `new` bên ngoài container có thể không kích hoạt transactional behavior như mong đợi.

## 17. Application service vẫn có thể dùng framework annotations

Một câu hỏi thường gặp:

> “Nếu application service có `@Transactional` thì đã vi phạm độc lập với hạ tầng chưa?”

Cần phân biệt **hai mức độ độc lập**:

1. **Domain logic thuần**: `Reservation.confirm()` không phụ thuộc framework hay database.
2. **Application orchestration**: trong một ứng dụng Spring, dùng `@Transactional` ở service boundary có thể là đánh đổi thực dụng; business rule vẫn có thể test riêng.

Nếu muốn application layer cũng framework-agnostic, có thể đặt giao dịch trong decorator/interceptor ở adapter ngoài, hoặc dùng một transaction runner port. Không có quy tắc bắt buộc mọi application service đều không được import Spring; điều quan trọng là dependency và trách nhiệm **có chủ đích**.

## 18. JPA persistence model có thể tách domain model

Để domain class không mang JPA annotations và không phụ thuộc provider, ta dùng một persistence entity:

~~~java
package com.example.reservation.persistence;

import com.example.reservation.domain.ReservationStatus;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "reservations")
public class JpaReservationEntity {

    @Id
    @Column(nullable = false, updatable = false)
    private UUID id;

    @Column(name = "tenant_id",
            nullable = false, updatable = false)
    private UUID tenantId;

    @Column(name = "customer_id",
            nullable = false, updatable = false)
    private UUID customerId;

    @Column(nullable = false)
    private int units;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ReservationStatus status;

    @Version
    private Long version;

    protected JpaReservationEntity() {
    }

    public UUID id() { return id; }
    public UUID tenantId() { return tenantId; }
    public UUID customerId() { return customerId; }
    public int units() { return units; }
    public Instant expiresAt() { return expiresAt; }
    public ReservationStatus status() { return status; }

    public void applyStatus(ReservationStatus status) {
        this.status = status;
    }
}
~~~

Đây là một *persistence representation*, không phải nơi diễn giải business invariant. Chuyển trạng thái hợp lệ phải đi qua domain method; adapter chỉ đồng bộ trạng thái đã được domain quyết định.

### @Version thuộc nhóm nào?

`@Version` là cơ chế kỹ thuật bảo vệ concurrent writes bằng optimistic locking. Khái niệm phiên bản có thể có ý nghĩa cho nghiệp vụ (ví dụ expectedVersion ở API), nhưng chi tiết annotation và SQL WHERE version thuộc adapter/persistence.

## 19. Mapper từ persistence entity sang domain

~~~java
package com.example.reservation.persistence;

import com.example.reservation.domain.Reservation;

final class ReservationMapper {

    private ReservationMapper() {
    }

    static Reservation toDomain(
            JpaReservationEntity row) {
        return new Reservation(
            row.id(),
            row.tenantId(),
            row.customerId(),
            row.units(),
            row.expiresAt(),
            row.status()
        );
    }
}
~~~

Domain không cần import `jakarta.persistence.Entity` hay `EntityManager` để được load từ database.

### Mapper có phải luôn cần?

Không. Với domain đơn giản, nhiều ứng dụng dùng cùng một JPA entity làm domain entity, giữ business methods trong class ấy. Tách model là lựa chọn phù hợp khi cần domain độc lập framework, test cực nhanh, API boundary ổn định hoặc hệ lưu trữ phức tạp.

### Giá phải trả

Hai representations cần mapping, kiểm soát stale state và tránh sao chép toàn graph không cần thiết. Đừng tách chỉ để “đủ tầng kiến trúc” nếu lợi ích không tương xứng.

## 20. JPA Repository adapter hiện thực port

~~~java
package com.example.reservation.persistence;

import com.example.reservation.domain.*;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import java.util.Optional;
import java.util.UUID;

@Repository
public class JpaReservationRepository
        implements ReservationRepository {

    @PersistenceContext
    private EntityManager em;

    @Override
    public Optional<Reservation> findInTenant(
            UUID reservationId,
            UUID tenantId) {

        return em.createQuery(
                "SELECT r FROM JpaReservationEntity r " +
                "WHERE r.id = :id " +
                "AND r.tenantId = :tenant",
                JpaReservationEntity.class)
            .setParameter("id", reservationId)
            .setParameter("tenant", tenantId)
            .getResultStream()
            .findFirst()
            .map(ReservationMapper::toDomain);
    }

    @Override
    public void save(Reservation reservation) {
        JpaReservationEntity row =
            em.find(
                JpaReservationEntity.class,
                reservation.id()
            );

        if (row == null
                || !row.tenantId().equals(
                    reservation.tenantId())) {
            throw new IllegalStateException(
                "Reservation không thuộc scope hiện tại");
        }

        row.applyStatus(reservation.status());
        // Managed row được provider dirty-check ở flush.
    }
}
~~~

### Những giả định của adapter

- `ConfirmReservationService.confirm()` được gọi trong **một active transaction**.
- Cùng transactional persistence context được dùng xuyên suốt load + save.
- `findInTenant()` load `JpaReservationEntity` managed rồi mapper tạo domain object; `em.find()` khi save thường trả lại managed instance cùng identity từ L1.
- Adapter này chỉ phục vụ **cập nhật Reservation đã tồn tại**. Create/upsert cần API và semantics riêng.
- Domain chỉ cho phép sửa status trong use case này; adapter không sao chép ID/tenant/customer/units từ client tùy ý.
- Optimistic version được provider quản lý trên `JpaReservationEntity` đã load, không phải tự do bỏ qua bằng bulk SQL.

### Cẩn trọng với stream

`getResultStream().findFirst()` ở query tối đa một row theo unique ID và tenant có thể được provider thực hiện thông thường, nhưng với streaming ResultSet/long-lived cursors cần quản lý đóng stream và resource theo provider semantics. Có thể dùng `getResultList()` trong ví dụ đơn giản nếu muốn tránh vấn đề stream lifecycle.

## 21. Vì sao adapter không tự commit?

Vì commit trong mỗi repository method sẽ phá ranh giới của use case:

~~~text
ConfirmReservationService:
  repository.load()
  domain.confirm()
  repository.save()      <-- commit tại đây?
  outbox.save()          <-- lỗi sau commit!
~~~

Nếu repository.save commit ngay, Reservation đã CONFIRMED nhưng outbox event không được ghi. Hai thao tác không còn atomic.

Đúng hơn:

~~~text
BEGIN (application use case)
  repository.load
  domain.confirm
  repository.save
  outbox.save
COMMIT
~~~

Repository có thể dùng `EntityManager` nhưng **không sở hữu commit boundary** nếu transaction owner là application service.

## 22. Dirty checking là một kỹ thuật, không phải business rule

Trong Spring/JPA transaction:

~~~java
@Transactional
public void changeStatus(UUID id) {
    JpaReservationEntity row =
        em.find(JpaReservationEntity.class, id);

    row.applyStatus(ReservationStatus.CONFIRMED);
    // Không cần em.merge(row) nếu row vẫn managed.
}
~~~

Về mặt kỹ thuật, provider có thể nhận diện thay đổi và flush ở commit.

Nhưng về mặt nghiệp vụ, trực tiếp gọi `applyStatus(CONFIRMED)` bên ngoài domain transition có thể bỏ qua invariants. Đây là lý do adapter phải được dùng thông qua use case đúng, và method thay state nên có giới hạn visibility/API phù hợp.

### Domain method không được phụ thuộc dirty checking

`Reservation.confirm()` nên xác định đúng state ngay cả khi object hoàn toàn detached, không còn trong context hoặc chưa từng được persist.

## 23. Khi dùng cùng JPA entity làm domain model

Một lựa chọn thực dụng:

~~~java
@Entity
public class Reservation {

    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private ReservationStatus status;

    @Version
    private Long version;

    protected Reservation() {
    }

    public void confirm(Instant now) {
        // Domain checks and state transition.
    }
}
~~~

Service:

~~~java
@Transactional
public void confirm(UUID id) {
    Reservation reservation = repository
        .findInTenant(id, currentTenant())
        .orElseThrow(NotFoundException::new);

    reservation.confirm(clock.instant());
    // Managed instance được dirty-check.
}
~~~

### Ưu điểm

- Ít mapping/copies.
- Dễ dùng dirty checking và associations.
- Có thể phù hợp CRUD/medium-complexity domain.

### Nhược điểm

- Domain class phải tương thích JPA constructors, field access/mapping/lazy proxies.
- Fetch boundary ảnh hưởng cách method được gọi.
- Entity relationships và persistence-specific annotations có thể tràn vào domain design.
- Domain objects bị serialize qua HTTP hoặc dùng ngoài transaction dễ dẫn đến LAZY/N+1/detached pitfalls.

**Độc lập với lifecycle tài nguyên không nhất thiết đòi không có `@Entity`**. Một JPA entity có thể chứa business methods, miễn chúng không tự mở/đóng EM, commit, gọi SQL hoặc giả định dữ liệu lazy luôn có sẵn ngoài use-case fetch plan.

## 24. Hai chiến lược mapping và lựa chọn

| Tiêu chí | Cùng entity cho domain và JPA | Tách domain model/JPA model |
| --- | --- | --- |
| Số classes/mappers | Ít hơn | Nhiều hơn |
| Dependency JPA trong domain | Có annotation/mapping | Có thể không |
| Dirty checking trên aggregate | Trực tiếp | Qua managed JPA row |
| Unit test domain | Dễ nếu methods không cần EM; vẫn có annotations | Hoàn toàn POJO |
| Lazy association | Cần quản lý fetch scope | Chuyển dữ liệu khi mapping |
| Mapping costs | Thấp | Có copy/translation |
| Portability persistence | Có giới hạn | Cao hơn |
| Rich aggregate/complex domain | Có thể được, nhưng cần kỷ luật | Thường giúp ranh giới rõ |

Không chọn bằng slogan “domain tuyệt đối không được import JPA” hoặc “mọi thứ phải là @Entity”. Cân nhắc business complexity, team, testability và nhu cầu thay đổi hạ tầng.

## 25. Repository contract nên che chi tiết của provider

Không nên phơi:

~~~java
interface ReservationRepository {
    EntityManager getEntityManager();
    Session unwrapHibernateSession();
    TypedQuery<?> createCustomQuery(String jpql);
    void flush();
    void clear();
}
~~~

Khi đó application/service bị buộc:

- Biết JPA provider API.
- Điều khiển context lifecycle.
- Viết arbitrary queries.
- Đưa decisions hạ tầng vào business flow.

Tốt hơn:

~~~java
interface ReservationRepository {
    Optional<Reservation> findInTenant(UUID id, UUID tenantId);
    void save(Reservation reservation);
    boolean existsActiveForCustomer(
        UUID customerId, UUID tenantId);
}
~~~

Những operations diễn đạt nhu cầu domain. Technical implementations có thể đổi cách query/index mà caller không cần sửa.

## 26. Repository cho aggregate, không nhất thiết cho mọi table

DDD-style Repository thường đại diện **aggregate root**:

~~~text
Reservation (aggregate root)
  |
  +-- ReservationItem (owned child)
  +-- ReservedSchedule (value object)
~~~

Thay vì để controller/service tự update từng child table qua nhiều repositories độc lập, dùng aggregate methods để bảo vệ invariants:

~~~java
reservation.changeUnits(...);
reservation.confirm(...);
repository.save(reservation);
~~~

### Tại sao hữu ích?

Một bất biến như “tổng units không vượt quota đã dành” có thể phụ thuộc nhiều child rows. Nếu mỗi bảng được sửa trong transaction riêng hoặc mỗi layer tự quyết, invariants dễ bị phá.

### Không phải mọi database row đều cần repository riêng

Với read-only reporting, projection/query service có thể truy vấn DTO trực tiếp mà không materialize aggregate, miễn quyền và data consistency được bảo đảm.

## 27. Command và Query có nhu cầu lưu trữ khác nhau

Một **command** thường:

~~~text
Load aggregate -> evaluate business rules
-> mutate aggregate -> persist within transaction
~~~

Một **query** chỉ đọc:

~~~text
Select a few scalar columns -> map to DTO -> return
~~~

Nếu list endpoint chỉ hiển thị Reservation ID, status, expiration, không nhất thiết phải load toàn aggregate và mọi child entity để tạo managed graph.

Ví dụ:

~~~java
public record ReservationSummary(
    UUID id,
    ReservationStatus status,
    Instant expiresAt
) {}
~~~

Và JPQL DTO projection trong adapter:

~~~java
List<ReservationSummary> rows = em.createQuery(
        "SELECT NEW com.example.api.ReservationSummary(" +
        "r.id, r.status, r.expiresAt) " +
        "FROM JpaReservationEntity r " +
        "WHERE r.tenantId = :tenant",
        ReservationSummary.class)
    .setParameter("tenant", tenantId)
    .setMaxResults(50)
    .getResultList();
~~~

Command/query separation ở mức **use-case contract** không yêu cầu phải áp dụng một hệ CQRS phức tạp với hai databases. Bắt đầu bằng khác biệt đơn giản giữa aggregate write port và DTO read port đã có ích.

## 28. Đừng để Query/Stream vượt khỏi vòng đời tài nguyên

Anti-pattern:

~~~java
public Stream<JpaReservationEntity> streamAll() {
    return em.createQuery(
        "SELECT r FROM JpaReservationEntity r",
        JpaReservationEntity.class)
      .getResultStream();
}
~~~

Caller có thể sử dụng stream khi EntityManager/transaction đã kết thúc:

~~~text
Repository returns Stream
  -> service transaction ends
  -> controller iterates Stream
  -> cursor/connection closed, lazy loads fail
~~~

### Thiết kế thay thế

- Repository/service **consume stream trong transaction/lifecycle scope** và trả DTOs/chunk result.
- Với export lớn, application coordinator xử lý từng page/chunk trong scope rõ.
- Dùng callback/iterator abstraction có quy định ownership, cancellation và close nếu thực sự phải stream.
- Không đưa `ResultSet` hoặc `TypedQuery` ra ngoài repository API thông thường.

Quy tắc: **đối tượng chứa tài nguyên kỹ thuật phải có owner và lifetime rõ ràng**.

## 29. Lazy loading và vòng đời persistence context

Ví dụ:

~~~java
PurchaseOrder order =
    repository.findOrder(id);

return new OrderResponse(
    order.getId(),
    order.getCustomer().getName()
);
~~~

Nếu `customer` lazy và mapping DTO xảy ra **sau khi context đóng**, Hibernate có thể ném `LazyInitializationException`.

Nếu context vẫn mở qua OSIV, mapping có thể gây N+1 secondary SELECTs.

### Kết luận kiến trúc

Đừng buộc domain method hoặc controller tự “chăm lo” mở EntityManager để chạy. Thay vào đó:

- Định nghĩa dữ liệu use case cần.
- Chọn fetch plan/DTO projection trong adapter.
- Dựng response DTO ở application boundary thích hợp.
- Chấm dứt transaction/context sau khi có kết quả đã materialize.

### Domain operation có thể cần association

Nếu `Reservation.confirm()` cần thông tin từ các items/quotas, repository phải load **đủ business state** trước khi gọi domain logic, hoặc dùng domain service phối hợp dữ liệu cần thiết. Không chuyển trách nhiệm “nếu LAZY không chạy thì mở thêm EM” vào domain.

## 30. Fetch plan thuộc adapter, không thuộc business rule

Một use case:

~~~text
Confirm Reservation:
  needs status, expiration, tenant, units
~~~

Nếu mapping chỉ cần các scalar fields, adapter có thể load một JPA entity.

Một use case khác:

~~~text
Confirm PurchaseOrder:
  needs order lines, customer credit limit,
  applied discount policy
~~~

Adapter cần bảo đảm những dữ liệu domain operation cần đã được tải đúng scope.

### Không viết domain phụ thuộc Hibernate proxy

Không nên để domain method:

~~~java
if (!Hibernate.isInitialized(lines)) {
    Hibernate.initialize(lines);
}
~~~

để “tự cứu” khi dữ liệu chưa sẵn sàng. Đó là coupling với Hibernate và resource scope.

Thay vào đó:

- Repository query với `JOIN FETCH` hoặc `EntityGraph` khi phù hợp.
- Load DTO/domain snapshot đầy đủ trước domain method.
- Dùng domain service được cấp dữ liệu đã truy xuất.
- Test cả business correctness và SQL count để tránh N+1.

## 31. Transaction boundary là một phần của application workflow

Một use case:

~~~text
BEGIN
  Verify ownership/permission
  Load Reservation
  Check domain invariants
  Update Reservation state
  Write outbox event
COMMIT
~~~

Transaction owner phải bao phủ toàn bộ những writes cần atomic.

### Sai: từng repository tự commit

~~~text
Repo A.save()  -> COMMIT
Repo B.save()  -> COMMIT
Repo C.save()  -> FAIL
~~~

Lúc đó trạng thái hệ thống có thể dở dang.

### Đúng: use case xác định atomicity

~~~text
ApplicationService @Transactional
    |
    +-- Repo A
    +-- Repo B
    +-- Repo C
    |
    v
Single transaction commit/rollback
~~~

Việc implement bằng Spring, JTA hay RESOURCE_LOCAL là chuyện adapter/infrastructure. Domain không trực tiếp gọi `begin()` hoặc `commit()`.

## 32. RESOURCE_LOCAL, JTA và Spring khác gì?

| Môi trường | Ai mở/đóng transaction? | Ai đóng EntityManager? |
| --- | --- | --- |
| Java SE RESOURCE_LOCAL | Application/infrastructure sử dụng `EntityTransaction` | Application-managed EM owner |
| Jakarta EE/JTA | Container/JTA transaction manager hoặc application boundary theo contract | Container/owner tương ứng |
| Spring với JPA | Spring transaction interceptor/manager | Framework proxy và EM lifecycle |

Trong JTA context, không dùng `em.getTransaction().begin()` như RESOURCE_LOCAL. `EntityManager.getTransaction()` cho RESOURCE_LOCAL entity managers; JTA transactions do cơ chế khác quản lý.

### Điều domain cần biết là gì?

Thông thường **không cần biết**. Domain nhận aggregate state và thực hiện transition. Application biết use case cần atomicity, còn hạ tầng chọn implementation.

## 33. RESOURCE_LOCAL: ví dụ quản lý tài nguyên ở ngoài domain

Một entrypoint Java SE có thể tổ chức:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Create a repository implementation scoped to em.
    ReservationRepository repository =
        new JpaScopedReservationRepository(em);

    UUID tenantId = authorization
        .requireTenantWithPermission(
            "reservation:confirm");

    Reservation reservation = repository
        .findInTenant(reservationId, tenantId)
        .orElseThrow(
            () -> new ReservationNotFound(reservationId)
        );

    reservation.confirm(clock.instant());
    repository.save(reservation);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
    }
    throw ex;
} finally {
    em.close();
}
~~~

Ở đây `JpaScopedReservationRepository` đại diện một adapter cùng logic như `JpaReservationRepository` nhưng nhận `EntityManager` qua constructor; không phải class thuộc JPA API. Code là minh họa **infrastructure entrypoint**; domain class vẫn không phụ thuộc EM.

### Vì sao đóng trong finally?

Để tài nguyên được giải phóng cả khi `find`, domain transition, `flush` hoặc `commit` ném exception.

### Vì sao rollback trong catch?

Một exception trước commit không nên để transaction tiếp tục mở. Khi commit outcome không rõ do kết nối lỗi, không tự kết luận thao tác chưa được ghi; với operations có thể retry, dùng idempotency/outcome verification.

## 34. Có thể trừu tượng hóa Unit of Work

Nếu application layer không muốn biết Spring annotation nhưng vẫn cần biểu đạt atomicity:

~~~java
public interface ReservationUnitOfWork
        extends AutoCloseable {

    ReservationRepository reservations();

    void commit();

    @Override
    void close();
}

public interface UnitOfWorkFactory {
    ReservationUnitOfWork begin();
}
~~~

Application:

~~~java
try (ReservationUnitOfWork uow =
        uowFactory.begin()) {

    Reservation reservation = uow.reservations()
        .findInTenant(id, tenantId)
        .orElseThrow(
            () -> new ReservationNotFound(id)
        );

    reservation.confirm(now);
    uow.reservations().save(reservation);
    uow.commit();
}
~~~

Implementation của `close()` trong resource-local adapter phải rollback nếu transaction còn active và chưa commit, rồi đóng EntityManager. Khi không có active transaction, nó chỉ cleanup tương ứng.

### Unit of Work abstraction có đáng dùng không?

Có thể hữu ích khi có nhiều entrypoints/transaction managers, hoặc muốn application framework-neutral. Nhưng với một ứng dụng Spring đơn giản, `@Transactional` trên service đã đủ rõ và bớt boilerplate. Không bọc mọi `EntityManager` operation trong lớp trừu tượng không có giá trị.

## 35. Unit of Work không phải luôn đồng nghĩa một Repository

Một transaction có thể chứa nhiều repository ports:

~~~text
UoW / Transaction
   |
   +-- ReservationRepository
   +-- InventoryReservationRepository
   +-- OutboxRepository
   |
   v
Commit atomically (nếu cùng DB/transaction resource)
~~~

### Khi có nhiều databases?

Một `@Transactional` mặc định chỉ áp dụng theo transaction manager cụ thể. Nếu các repositories dùng nhiều DB/data sources/transaction managers độc lập, không tự có distributed atomic commit.

Khi cần phối hợp nhiều systems, cân nhắc JTA/XA nếu thực sự phù hợp hoặc saga/outbox/inbox và compensations, theo yêu cầu consistency của nghiệp vụ.

## 36. @Transactional(readOnly = true) cho query use case

Ví dụ:

~~~java
@Transactional(readOnly = true)
public ReservationSummary findSummary(UUID id) {
    UUID tenantId =
        authorization.requireTenantWithPermission(
            "reservation:read");

    return queryPort.findSummaryInTenant(id, tenantId)
        .orElseThrow(
            () -> new ReservationNotFound(id)
        );
}
~~~

Read-only là policy/hint transaction và provider optimization tùy configuration, **không tự biến entity queries thành DTOs** và không thay quyền truy cập.

### Vì sao không trả managed JPA entity?

Để tránh:

- Lazy access ngoài transaction.
- Serialization kéo theo extra SQL.
- API vô tình expose persistence fields.
- Caller tiếp tục mutate managed entity ở layer không có quyền.

Với read use cases, DTO projection là cách rõ ràng để giữ output độc lập resource lifecycle.

## 37. Flush thuộc persistence, không phải business transition

`flush()` yêu cầu provider đồng bộ pending changes xuống database trong transaction thích hợp.

~~~java
Reservation reservation = ...;
reservation.confirm(now);
repository.save(reservation);
// Flush thường xảy ra do transaction manager/provider.
~~~

### Không gọi flush vô điều kiện sau từng domain operation

Nếu mỗi entity update gọi `em.flush()`, có thể:

- Phát JDBC quá thường xuyên.
- Mất lợi ích JDBC batching.
- Thay thời điểm phát hiện constraint violation.
- Làm use case khó phối hợp nhiều writes.

### Khi nào explicit flush hữu ích?

- Muốn phát hiện constraint violation trước bước tiếp theo **trong cùng transaction**.
- Cần SQL được đồng bộ trước một operation phụ thuộc DB state.
- Batch processing flush theo chunks.

Nhưng explicit flush vẫn **không phải commit**; domain method không được tự quyết định flush chỉ vì nó chuyển trạng thái.

## 38. Clear và detach là kỹ thuật có hậu quả lớn

`em.clear()` detach mọi managed entities trong persistence context.

Nếu repository tự gọi:

~~~java
em.clear();
~~~

sau một method mà caller không biết, những JPA entities khác caller đang giữ cũng có thể detached. Sửa chúng sau đó không còn tự được dirty checking.

### Trong batch

Pattern:

~~~java
em.flush();
em.clear();
~~~

có thể giúp giới hạn context growth khi xử lý hàng nghìn entities. Nhưng đó là quyết định của **batch/transaction coordinator**, không nên là side effect bí mật của generic repository method.

### Với separate domain POJO model

Domain aggregate vốn không phải managed JPA entity, nên `clear()` không trực tiếp đổi trạng thái domain object. Tuy nhiên, adapter đang giữ JPA managed rows/snapshots sẽ bị detach và phải hiểu context boundary nếu tiếp tục save.

## 39. Merge và detached state

JPA `merge(detachedEntity)` không đơn giản “đưa object gốc trở lại managed”. Nó sao chép state vào một managed instance rồi trả về managed instance đó.

Sai dễ gặp:

~~~java
Product managed = em.merge(detachedProduct);
// Code tiếp tục sửa detachedProduct và nghĩ được theo dõi:
detachedProduct.setName("New name");
~~~

Sửa object detached sau merge có thể không được flush vì managed instance là `managed` được trả về.

### Thiết kế tránh lộ merge lên domain API

Repository port nên cung cấp thao tác lưu aggregate phù hợp use case, còn JPA adapter quyết định dùng `persist`, managed dirty checking, `merge` hay query update.

### Đừng merge nguyên entity từ request JSON

Client có thể gửi stale state, tenantId khác, foreign key hoặc fields không được phép sửa. Dùng command DTO, authorization và domain transition trước khi ghi.

## 40. Không tự động lưu thay đổi nếu aggregate chưa thuộc managed context

Khi tách domain và persistence model:

~~~java
Reservation reservation = repository.findInTenant(...);
reservation.confirm(now);
~~~

Domain Reservation không phải managed JPA entity. **Không có dirty checking tự động cho domain POJO**.

Phải gọi:

~~~java
repository.save(reservation);
~~~

để adapter cập nhật một managed `JpaReservationEntity`.

### Khi dùng cùng JPA entity trong domain?

Nếu entity còn managed, thay đổi trong transactional scope có thể được dirty-checked dù không gọi `save` tường minh. Nhưng gọi repository.save có thể vẫn hữu ích để thể hiện intent theo team contract.

**Đừng pha hai mô hình mà không hiểu ownership**. Một port dùng detached domain POJO không thể dựa vào JPA dirty checking trên chính object ấy.

## 41. Exception nghiệp vụ khác lỗi hạ tầng

| Loại lỗi | Ví dụ | Layer xử lý chính |
| --- | --- | --- |
| Business invariant | CONFIRM Reservation đã CANCELED | Domain |
| Not found trong scope | ID không tồn tại hoặc không thuộc tenant | Application/repository policy |
| Authorization | User thiếu quyền confirm | Application/security |
| Optimistic conflict | @Version mismatch | JPA/infrastructure → application policy |
| Unique/FK constraint | Database từ chối write | Infrastructure/DB → application policy |
| Query timeout | SQL quá lâu | Infra/runtime → use-case error |
| Connection failure | DB unavailable | Infra/ops → retry/circuit breaker |
| Serialization failure | Response mapping sai | API/application |

Một `InvalidReservationTransition` không nên được bọc thành “database unavailable”; một `OptimisticLockException` cũng không nên mặc định biến thành business invariant lỗi.

### Đổi kỹ thuật không đổi ngôn ngữ business

Use case có thể đưa những exception hạ tầng sang application-level errors như `ConcurrencyConflict` nếu cần giữ API contract ổn định, nhưng vẫn lưu cause cho diagnostic, không giấu root cause.

## 42. Transaction rollback khi domain method thất bại

Trong Spring:

~~~java
@Transactional
public void confirm(UUID id) {
    Reservation reservation = repository
        .findInTenant(id, tenantId())
        .orElseThrow(NotFoundException::new);

    reservation.confirm(clock.instant());
    repository.save(reservation);
}
~~~

Nếu `confirm()` ném unchecked domain exception, Spring mặc định đánh dấu rollback đối với unchecked exceptions theo transaction semantics.

### Nhưng Java object vẫn có thể đã đổi state

Nếu domain method mutate một vài fields rồi ném exception ở cuối, **database rollback không tua ngược Java object state**. Domain methods nên kiểm tra các preconditions trước rồi mới mutation, hoặc bảo đảm một transition nhất quán.

### Checked exceptions

Spring mặc định khác với unchecked trong rollback rules; nếu application dùng checked business exception, cần cấu hình `rollbackFor` hoặc error strategy có chủ đích.

Không viết domain method dựa vào ý nghĩ “mọi exception đều tự rollback theo mọi transaction framework”.

## 43. Optimistic locking khi hai requests cùng confirm

Giả sử:

~~~text
DB Reservation DRAFT, version=7

TX A reads DRAFT, version=7
TX B reads DRAFT, version=7

TX A confirms -> UPDATE ... WHERE version=7
             -> version=8, commit

TX B confirms -> UPDATE ... WHERE version=7
             -> conflict
~~~

`@Version` giúp phát hiện lost updates trong các managed JPA entity writes được versioned provider processing thực thi.

### Domain không cần thấy SQL version predicate

Domain chỉ biết “transition từ DRAFT sang CONFIRMED hợp lệ trên state tôi đang xử lý”. Database/JPA báo xung đột khi state đó đã lỗi thời.

### Kết hợp hai lớp

- Domain invariant bảo đảm logic đúng trên snapshot đã tải.
- Optimistic version bảo đảm update không âm thầm ghi đè concurrent update.

Chỉ dùng một trong hai không giải quyết đủ mọi tình huống.

## 44. Retry phải mở transaction và persistence context mới

Nếu một transaction đã lỗi optimistic locking:

~~~text
Attempt 1:
  Load version 7
  Confirm
  Flush conflict -> rollback

Attempt 2:
  New transaction/context
  Reload version 8
  Re-evaluate business rule
  Commit hoặc trả conflict
~~~

Không retry bằng cách gọi `flush()` lần nữa trên cùng EntityManager bị lỗi rồi giả định trạng thái được sửa.

### Không phải xung đột nào cũng retry tự động

Nếu request B đã CONFIRM từ trước, domain rule có thể yêu cầu báo conflict hoặc idempotent success tùy API contract. Retry có thể phát hiện trạng thái đã CONFIRMED và phải quyết định theo business semantics, không do Hibernate tự chọn.

### Retry bounds

Với transient conflicts được phép retry: giới hạn attempts, backoff/jitter và kiểm tra idempotency. Với payment/order creation, không retry bừa khi outcome commit không rõ.

## 45. Khi business rule cần đồng bộ giữa nhiều aggregates

Ví dụ:

> “Mỗi ghế trong một suất chiếu chỉ được đặt cho tối đa một Reservation đang hoạt động.”

Một domain method thuần:

~~~java
reservation.confirm(now);
~~~

không thể tự ngăn hai transactions khác nhau đồng thời xác nhận cùng ghế nếu mỗi transaction chỉ thấy snapshot riêng.

### Cần nhiều tầng bảo vệ

- Domain rule kiểm tra điều kiện của aggregate.
- Application điều phối thao tác kiểm tra và ghi trong transaction.
- Repository có thể dùng pessimistic lock/optimistic concurrency khi cần.
- Database UNIQUE/EXCLUSION constraints hoặc một model giữ chỗ atomic nếu phù hợp.
- Business-specific retry/conflict handling.

### Check-then-act có race

~~~text
TX A: seatAvailable = true
TX B: seatAvailable = true
TX A: insert Reservation
TX B: insert Reservation
~~~

Nếu chỉ đọc availability rồi ghi, hai transactions có thể tranh chấp. Database constraint hoặc atomic locking/version protocol là ranh giới concurrency thực.

**Độc lập với tài nguyên không có nghĩa bỏ qua cơ chế nhất quán database**. Nó có nghĩa domain mô tả rule, còn application/infrastructure triển khai atomic enforcement.

## 46. Domain event không nên tự gửi message

Ví dụ không nên:

~~~java
public void confirm() {
    status = ReservationStatus.CONFIRMED;
    kafkaProducer.send(
        "reservations",
        "confirmed:" + id
    );
}
~~~

Rủi ro:

- Domain phụ thuộc Kafka client.
- Unit test cần mạng/broker.
- Message có thể gửi trước DB commit, trong khi transaction sau đó rollback.
- Retry domain method có thể gửi trùng.
- Broker failure có thể làm domain object thay state nhưng persistence chưa nhất quán.

### Phân biệt event

**Domain event** thể hiện sự kiện đã xảy ra trong aggregate theo mô hình nghiệp vụ.

**Integration event** là thông điệp gửi sang hệ thống ngoài, cần serialization, schema version, delivery và retry policy.

Domain có thể ghi nhận event data, nhưng không tự điều khiển producer và network lifecycle.

## 47. Tạo domain event như dữ liệu

Ví dụ:

~~~java
public record ReservationConfirmed(
    UUID reservationId,
    UUID tenantId,
    Instant occurredAt
) {}
~~~

Một aggregate có thể tập hợp pending domain events:

~~~java
private final List<ReservationConfirmed> events =
    new ArrayList<>();

public void confirm(Instant now) {
    requireDraftAndNotExpired(now);
    status = ReservationStatus.CONFIRMED;

    events.add(
        new ReservationConfirmed(id, tenantId, now)
    );
}
~~~

Đoạn thứ hai minh họa **một biến thể mở rộng** của Reservation domain model trước đó: `requireDraftAndNotExpired()` tách logic validation đã có trong `confirm()` ra helper, và `events` được quản lý bởi aggregate.

### Ai xử lý events?

Application service có thể lấy các events sau transition, ghi outbox hoặc dispatch theo workflow. Cần thiết kế lúc “đánh dấu events đã lấy” để không mất/sinh trùng khi transaction fail hoặc retry.

Không để domain tự gọi `em.persist(outboxRow)`.

## 48. Transactional outbox

Nếu confirmation phải báo cho hệ thống vận chuyển hoặc thông báo email, một outbox là giải pháp phổ biến:

~~~text
BEGIN DB TRANSACTION
  Load Reservation
  Domain confirm()
  Save Reservation status
  Save OutboxEvent(reservation-confirmed)
COMMIT DB TRANSACTION

Background Publisher
  Read unpublished outbox events
  Publish to broker
  Mark delivered/retry
~~~

Điểm quan trọng: **Reservation update và outbox insert dùng cùng DB transaction**, khi cùng resource/transaction manager. Nếu transaction rollback, cả hai bị rollback.

### Delivery semantics

Outbox publisher có thể crash sau khi publish nhưng trước khi mark delivered, vì vậy thường cần **at-least-once delivery** và idempotent consumers. Không tuyên bố outbox tự bảo đảm exactly-once end-to-end.

### Business independence

Domain chỉ phát biểu “Reservation đã được xác nhận”; application/infrastructure quyết định khi nào lưu/sent event, retry bao nhiêu lần, và quản lý broker connection.

## 49. @TransactionalEventListener và after-commit side effects

Trong Spring, một listener có thể chạy:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onReservationConfirmed(
        ReservationConfirmed event) {
    notificationSender.send(event);
}
~~~

Điều này giúp tránh gửi notification trước khi transaction commit trong một số workflows.

### Nhưng có giới hạn

Nếu process crash ngay sau DB commit và trước khi listener gửi thành công, sự kiện có thể bị mất. Listener after-commit không tự tạo durability/retry.

Khi requirement là **không được mất event**, cần outbox hoặc cơ chế durable messaging tương đương. Domain vẫn không điều khiển network connection.

## 50. Không gọi API bên ngoài trong transaction dài

Ví dụ rủi ro:

~~~java
@Transactional
public void confirm(UUID id) {
    Reservation reservation = repository.load(id);
    reservation.confirm(clock.instant());
    repository.save(reservation);

    emailGateway.sendConfirmation(id); // Network call
}
~~~

Nếu network call treo vài giây:

- Transaction/connection resources có thể bị giữ lâu.
- Locks giữ thêm thời gian.
- Timeout từ remote service ảnh hưởng DB transaction.
- Nếu email gửi thành công rồi DB rollback, side effect không thể rollback.

### Thiết kế thay thế

Trong transaction, ghi một durable intent (outbox). Sau commit, process riêng gửi email và retry idempotently.

Không phải mọi external call đều cấm tuyệt đối trong transaction; nhưng phải hiểu atomicity, timeout, resource ownership và failure modes, không viết mặc định rồi hy vọng rollback hủy được network side effect.

## 51. Domain logic trong background worker

Một command có thể được kích hoạt từ:

~~~text
HTTP controller
CLI command
Scheduled job
Message consumer
Workflow worker
~~~

Nếu domain method độc lập EM, cùng `Reservation.confirm(now)` có thể được dùng từ nhiều entrypoints.

### Nhưng transaction vẫn cần ở mỗi entrypoint

Một worker chạy trên thread khác không được giả định thừa hưởng EntityManager/transaction ThreadLocal của HTTP thread trước.

Thiết kế:

~~~text
Worker receives command
  -> application service begins its own transaction
  -> repository loads domain state
  -> domain evaluates rule
  -> repository saves
  -> commit/rollback
~~~

Không truyền managed entity/proxy qua message queue hoặc thread boundary để worker sử dụng như vẫn còn trong same persistence context.

## 52. @Async và @Transactional không tự chia sẻ context

Trong Spring:

~~~java
@Async
public void sendNotification(...) {
    // Executes in another thread.
}
~~~

Một async invocation có thể chạy với transaction/EntityManager context khác, không có active transaction nếu không được thiết lập cho method đó.

### Rủi ro

~~~text
Service loads managed Order
  -> @Async method receives Order object
  -> caller transaction ends
  -> async accesses lazy order.getLines()
  -> LazyInitializationException or unexpected behavior
~~~

### Tốt hơn

Gửi **ID hoặc immutable DTO** qua async boundary. Worker tự bắt đầu use case/transaction, load dữ liệu cần bằng repository trong scope mới.

Độc lập với lifecycle tài nguyên giúp code không dựa vào việc một entity proxy “sống mãi” giữa threads.

## 53. HTTP request và transaction không nên là một

Controller:

~~~java
@PostMapping("/reservations/{id}/confirm")
public ResponseEntity<Void> confirm(
        @PathVariable UUID id) {

    service.confirm(id);
    return ResponseEntity.noContent().build();
}
~~~

Controller xử lý HTTP input/output, còn service thực hiện use case. Không cần đặt `EntityManager` vào controller.

### Vì sao không luôn @Transactional ở controller?

Đặt transaction trùm cả HTTP serialization, network calls, upload parsing hoặc response streaming có thể giữ tài nguyên lâu và làm boundary quá rộng.

Transaction thường nên bao quanh phần application operation thực sự cần atomicity.

### HTTP status mapping

Application exception có thể map sang:

| Tình huống | Kết quả API thường phù hợp |
| --- | --- |
| Reservation không tồn tại trong tenant | 404 |
| User thiếu quyền | 403 |
| Transition không hợp lệ | 409 hoặc 422 tùy contract |
| Optimistic version conflict | 409 |
| DB tạm unavailable | 503 |
| Validation request malformed | 400 |

Đây là lựa chọn API contract, không phải mapping bắt buộc của Jakarta Persistence.

## 54. Độc lập kỹ thuật không có nghĩa bỏ authorization

Application service:

~~~java
UUID tenantId = authorization
    .requireTenantWithPermission(
        "reservation:confirm");

Reservation reservation = repository
    .findInTenant(id, tenantId)
    .orElseThrow(...);
~~~

Repository adapter bảo đảm query có:

~~~sql
WHERE id = ? AND tenant_id = ?
~~~

### Không tin tenant ID từ client

Nếu API nhận `tenantId` do người dùng tự gửi mà không kiểm tra quyền, một repository port “thuần domain” vẫn có thể bị dùng để đọc sai dữ liệu.

### Defense-in-depth

Sử dụng auth policy ở application, tenant predicates trong repository và database RLS/constraints khi phù hợp. Một business operation độc lập resource lifecycle vẫn phải có **trusted authorization context**.

## 55. Database constraints bổ sung domain invariants

Domain:

~~~java
if (units <= 0) {
    throw new IllegalArgumentException(
        "Số lượng phải dương");
}
~~~

Database có thể bảo vệ:

~~~sql
CHECK (units > 0)
UNIQUE (tenant_id, business_reference)
FOREIGN KEY (customer_id) REFERENCES customers(id)
~~~

### Vì sao cần cả hai?

- Domain cho lỗi sớm, rõ ngữ nghĩa với người dùng.
- Database constraints bảo vệ dữ liệu khi có nhiều writers, scripts, migrations hoặc concurrency.
- Provider flush/commit có thể ném constraint exceptions, application cần xử lý mà không expose SQL internals.

Domain không nên đọc vendor SQLSTATE để quyết định quy tắc “units phải dương”; nhưng hạ tầng nên nhận diện constraint violation để cung cấp lỗi ứng dụng phù hợp.

## 56. Mapping database exceptions ra application errors

Một adapter có thể bắt provider-specific exception ở boundary và chuyển sang error contract ổn định nếu giúp ích:

~~~text
SQLException / JDBC ConstraintViolation
         |
         v
JPA / Spring exception translation
         |
         v
Application conflict/unavailable error
         |
         v
Controller maps to HTTP response
~~~

### Không che mọi lỗi thành “not found”

Một query timeout không phải database không có Reservation.

Một optimistic conflict không phải quyền truy cập bị từ chối.

Một connectivity failure không phải domain validation failure.

### Giữ cause

Log lỗi kỹ thuật đúng phạm vi, có correlation ID, nhưng không trả stack trace, DB schema, raw bind parameters hoặc bí mật kết nối cho client.

## 57. Timeouts thuộc infrastructure policy

Một Repository adapter có thể đặt:

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    2000
);
~~~

Đây là JPA query timeout hint, thường theo milliseconds; hiệu lực thực tùy provider/driver/database.

Spring service:

~~~java
@Transactional(timeout = 5)
public void confirm(UUID id) {
    // Use case...
}
~~~

`timeout=5` ở đây theo seconds trong Spring transaction annotation, liên quan transaction policy chứ không tự bảo đảm hard deadline cho toàn HTTP request.

### Domain cần gì?

Nghiệp vụ có thể định nghĩa **thời hạn hiệu lực của reservation** bằng `expiresAt`, hoàn toàn khác query execution timeout.

Không nhầm:

~~~text
Reservation expires in 15 minutes
~~~

với:

~~~text
SQL query timeout = 2 seconds
~~~

Một là **quy tắc nghiệp vụ**, một là **giới hạn tài nguyên kỹ thuật**.

## 58. Không dùng JPA provider API trong domain service

Một domain service có thể cần tính quyết định từ nhiều entities hoặc value objects:

~~~java
public final class ReservationPolicy {

    public boolean canConfirm(
            Reservation reservation,
            InventoryAvailability availability) {
        return reservation.status()
                    == ReservationStatus.DRAFT
            && availability.remainingUnits()
                    >= reservation.units();
    }
}
~~~

Trong ví dụ, `InventoryAvailability` là một immutable domain value chứa số lượng có sẵn tại thời điểm đã kiểm tra.

Domain service không tự gọi:

~~~java
em.createQuery("SELECT ...");
session.lock(...);
jdbcTemplate.query(...);
~~~

Application/repository chuẩn bị dữ liệu cần cho policy, rồi bảo đảm invariant còn đúng tại commit bằng version/lock/constraint strategy.

### Quan trọng với concurrency

Một availability snapshot có thể lỗi thời ngay sau khi đọc. Domain policy cho quyết định đúng với snapshot, còn infrastructure cần atomic enforcement (inventory row version, decrement-if-available SQL có điều kiện, locking hoặc constraint) để tránh overselling.

## 59. Domain model không cần biết entity đang managed hay detached

Trong thiết kế tách domain POJO:

~~~text
JPA Entity managed in persistence context
        |
        v
Mapper -> Domain Reservation (plain Java object)
        |
        v
Domain transition
        |
        v
Repository save -> apply state to managed JPA row
~~~

Domain không hỏi `em.contains(reservation)` vì Reservation không được JPA quản lý.

### Khi dùng chung JPA entity

Vẫn nên viết business method sao cho transition đúng dù object ở trạng thái managed hoặc detached, nhưng **người gọi phải biết** thay đổi trên detached object không tự được flush.

Vì thế method:

~~~java
reservation.confirm(now);
~~~

có **business semantics** ổn định, trong khi **persistence semantics** phụ thuộc cách repository/application quản lý object.

## 60. Test domain bằng JUnit thuần

Một bảng kiểm thử state transitions:

| Initial state | Operation | Expected |
| --- | --- | --- |
| DRAFT, còn hạn | confirm | CONFIRMED |
| DRAFT, đúng hạn hết | confirm | Exception, DRAFT |
| DRAFT, quá hạn | confirm | Exception, DRAFT |
| CONFIRMED | confirm | Exception, CONFIRMED |
| CANCELED | confirm | Exception, CANCELED |
| DRAFT | cancel | CANCELED |
| CONFIRMED | cancel | Exception, CONFIRMED |
| units <= 0 | construct | Exception |

### Tính độc lập được thể hiện ở đâu?

Các test này **không cần**:

- Spring context.
- `EntityManagerFactory`.
- Hibernate Session.
- Testcontainers.
- Database fixture.
- Transaction rollback.

Chúng xác minh quy tắc nghiệp vụ một cách nhanh chóng và deterministic.

## 61. Unit test application service bằng fake repository

Fake repository có thể lưu trạng thái trong memory:

~~~java
final class InMemoryReservationRepository
        implements ReservationRepository {

    private final Map<UUID, Reservation> data =
        new HashMap<>();

    @Override
    public Optional<Reservation> findInTenant(
            UUID id, UUID tenantId) {
        Reservation r = data.get(id);
        if (r == null || !r.tenantId().equals(tenantId)) {
            return Optional.empty();
        }
        return Optional.of(copy(r));
    }

    @Override
    public void save(Reservation reservation) {
        data.put(reservation.id(), copy(reservation));
    }

    void seed(Reservation reservation) {
        data.put(reservation.id(), copy(reservation));
    }

    Reservation saved(UUID id) {
        return data.get(id);
    }

    private static Reservation copy(Reservation r) {
        return new Reservation(
            r.id(),
            r.tenantId(),
            r.customerId(),
            r.units(),
            r.expiresAt(),
            r.status()
        );
    }
}
~~~

### Vì sao fake tạo copies?

Nếu fake trả nguyên reference object trong map, application có thể đổi object đó bằng `reservation.confirm()` mà quên `repository.save()`, nhưng test vẫn pass vì map giữ cùng reference. Copy-on-read và copy-on-save làm fake gần với contract domain snapshot hơn.

### Giới hạn của fake

Nó không mô phỏng:

- DB transaction rollback.
- @Version conflicts.
- JDBC constraints.
- Isolation/locking.
- JPA lazy loading.

Những điều ấy cần integration tests riêng. Fake chỉ hỗ trợ unit test orchestration.

## 62. Unit test service orchestration

Ví dụ:

~~~java
@Test
void serviceConfirmsUsingRepositoryAndClock() {
    UUID id = UUID.randomUUID();
    UUID tenant = UUID.randomUUID();
    UUID customer = UUID.randomUUID();

    InMemoryReservationRepository repo =
        new InMemoryReservationRepository();

    repo.seed(new Reservation(
        id,
        tenant,
        customer,
        3,
        Instant.parse("2030-01-01T00:00:00Z"),
        ReservationStatus.DRAFT
    ));

    AuthorizationService auth =
        permission -> tenant;

    Clock fixedClock = Clock.fixed(
        Instant.parse("2029-01-01T00:00:00Z"),
        ZoneOffset.UTC
    );

    ConfirmReservationService service =
        new ConfirmReservationService(
            repo,
            auth,
            fixedClock
        );

    service.confirm(id);

    assertEquals(
        ReservationStatus.CONFIRMED,
        repo.saved(id).status()
    );
}
~~~

Test không cần inject EntityManager. `@Transactional` trên class sẽ không có interceptor khi khởi tạo thủ công, nhưng **mục tiêu test này là orchestration/domain**, không xác minh transactional integration. Transaction test phải chạy qua Spring-managed service.

## 63. Contract test cho Repository port

Vì domain/application chỉ biết `ReservationRepository`, một tập contract tests hữu ích:

~~~text
findInTenant(existing ID, correct tenant)
    -> returns appropriate Reservation

findInTenant(existing ID, wrong tenant)
    -> returns empty / forbidden per agreed contract

findInTenant(nonexistent ID, tenant)
    -> empty

save(valid transition within transaction)
    -> committed state updated

save(stale version)
    -> concurrency conflict, not silent overwrite
~~~

Fake repository có thể chạy phần hành vi in-memory; JPA adapter phải chạy contract tests với database thật, đặc biệt cho tenant scope, version và commit/rollback.

### Không bắt buộc fake giống mọi chi tiết hạ tầng

Fake không cần mô phỏng provider exception class, flush timing hoặc SQL count. Nó chỉ cần thực hiện contract quan trọng ở application boundary.

## 64. Integration test JPA adapter

Một test với Spring-managed transaction:

~~~text
Arrange:
  Create Reservation DRAFT
  Commit fixture

Act:
  Call managed ConfirmReservationService
  Transaction commits

Assert:
  New EntityManager reads CONFIRMED
  Version advanced if mapped/update performed
  No cross-tenant data read
~~~

### Vì sao đọc lại bằng context khác?

Nếu test đọc lại bằng cùng EntityManager đang giữ managed state, có thể chỉ thấy L1 identity map thay vì giá trị DB đã commit. Dùng transaction/EntityManager mới để xác nhận persistence thực.

### Không chỉ assert mock interactions

Kiểm thử transactional JPA path cần xác nhận **database state**, không chỉ `verify(repository).save(...)`.

## 65. Integration test rollback

Kịch bản:

~~~text
BEGIN
  Load Reservation
  Domain transitions to CONFIRMED
  Simulate failure in second write/outbox save
ROLLBACK

New transaction:
  Reservation remains DRAFT
  Outbox has no corresponding event
~~~

### Điều cần kiểm tra

- Error xảy ra **trước commit**.
- Transaction manager thật đã rollback.
- Không có partial write được commit.
- Exception không bị catch và nuốt rồi vẫn commit.

### Chú ý Spring test default rollback

Một `@Transactional` test method mặc định rollback khi kết thúc có thể che việc application service commit/rollback không như production. Nếu kiểm tra commit boundary, dùng transaction orchestration trong test phù hợp, ví dụ `TransactionTemplate`, sau đó mở read transaction/context mới.

## 66. Integration test optimistic concurrency

Sử dụng hai EntityManagers/transactions độc lập:

~~~text
TX A loads Reservation version=3, DRAFT
TX B loads Reservation version=3, DRAFT

TX A transitions -> CONFIRMED, commits
TX B transitions -> CONFIRMED, tries commit

Expect:
  TX B gets optimistic conflict
  DB state remains valid
~~~

### Test không nên dùng cùng EntityManager

Hai references trong cùng persistence context thường trỏ tới một managed instance, không tái hiện concurrent version conflict.

### Provider behavior

Exception có thể xuất hiện ở `flush()` hoặc `commit()`; Spring/JPA có thể bọc nó. Test nên assert conflict semantics/type thích hợp với stack đang chạy thay vì giả định luôn tại cùng source line.

## 67. Integration test domain + database constraint

Domain constructor từ chối units <= 0, nhưng database cũng cần constraint phù hợp nếu dữ liệu có thể được ghi qua nhiều đường.

Test:

~~~text
1. Domain unit test rejects invalid units.
2. Adapter integration test persists valid units.
3. Database test verifies CHECK/NOT NULL/UNIQUE.
4. Concurrent test verifies uniqueness/locking behavior.
~~~

Không dùng JPA `@Column(nullable=false)` như bằng chứng database thực sự đã triển khai mọi constraint; cần migration/schema verification trong test environment.

## 68. Test query boundary và lazy loading

Một service trả:

~~~java
List<ReservationSummary>
~~~

thay vì:

~~~java
List<JpaReservationEntity>
~~~

có thể được kiểm tra:

- Serialization sau service transaction không cần EM.
- Không sinh thêm SQL từ JSON serializer.
- Không lộ tenant/customer/internal fields ngoài DTO contract.
- Pagination/SQL count có giới hạn.

### Khi business cần collection

Adapter load/fetch graph hoặc projection cần thiết, rồi application tạo DTO trong đúng transaction scope. Sau đó controller chỉ serialize value objects.

Đừng chữa LazyInitializationException bằng việc cho phép controller tự mở EntityManager với ID không kiểm tra quyền.

## 69. Test outbox durability

Kịch bản:

~~~text
TX A:
  confirm Reservation + insert outbox row
  commit
Expect:
  both Reservation status and outbox event visible

TX B:
  confirm another Reservation + insert outbox row
  failure -> rollback
Expect:
  neither update nor outbox event committed
~~~

Test publisher:

- Event được publish sau commit.
- Crash/retry có thể publish trùng.
- Consumer idempotently handles duplicates.
- Outbox status/attempt counters và cleanup có giới hạn.

**Domain unit test không cần broker**; integration test messaging mới cần mô phỏng/khởi tạo broker hoặc một durable transport phù hợp.

## 70. Không dùng TransactionRequiredException để kiểm tra nghiệp vụ

`TransactionRequiredException` có nghĩa một operation cần active transaction phù hợp nhưng không có. Nó không có nghĩa Reservation đã hết hạn hoặc business rule không hợp lệ.

Ví dụ:

~~~java
em.createQuery(
    "UPDATE JpaReservationEntity r " +
    "SET r.status = :status WHERE r.id = :id")
  .setParameter("status", ReservationStatus.CONFIRMED)
  .setParameter("id", id)
  .executeUpdate();
~~~

Bulk DML yêu cầu transaction; nếu không có, đó là lỗi **application/infrastructure wiring** chứ không phải domain logic.

### Xử lý đúng

Sửa transaction boundary/manager configuration, không catch rồi chuyển thành “Reservation not found” hoặc “cannot confirm”.

## 71. Repository generic quá rộng có thể làm lộ lifecycle

Interface:

~~~java
interface GenericRepository<T> {
    void persist(T entity);
    T merge(T entity);
    void flush();
    void detach(T entity);
    void clear();
    List<T> findAll();
}
~~~

có thể hữu ích như tiện ích kỹ thuật nội bộ, nhưng không nên mặc định là **domain repository port**.

### Vì sao?

- Caller phải hiểu khi nào entity managed.
- Không rõ aggregate ownership.
- Dễ dùng `findAll()` load toàn bộ bảng.
- Merge/flush/clear điều khiển persistence context từ layer nghiệp vụ.
- Interface không diễn đạt những use cases cụ thể.

Domain-oriented port:

~~~java
interface ReservationRepository {
    Optional<Reservation> findInTenant(UUID id, UUID tenantId);
    void save(Reservation reservation);
}
~~~

giúp thực thi ranh giới rõ hơn. Không cấm generic technical repositories trong infrastructure nếu chúng thực sự có ích và không chảy lên domain API.

## 72. Các câu lệnh bulk DML cần một policy riêng

Ví dụ:

~~~java
int updated = em.createQuery(
        "UPDATE JpaReservationEntity r " +
        "SET r.status = :canceled " +
        "WHERE r.status = :draft " +
        "AND r.expiresAt < :now " +
        "AND r.tenantId = :tenant")
    .setParameter(
        "canceled", ReservationStatus.CANCELED)
    .setParameter(
        "draft", ReservationStatus.DRAFT)
    .setParameter("now", now)
    .setParameter("tenant", tenantId)
    .executeUpdate();
~~~

Đây là một cách thực hiện job expire rows hiệu quả hơn load từng aggregate, nếu nghiệp vụ cho phép.

### Nhưng bulk DML thường bypass

- Per-entity business methods.
- JPA entity lifecycle callbacks tương ứng.
- Automatic optimistic @Version handling theo managed update.
- Synchronization với managed entity state đã tồn tại trong L1.
- Một số auditing/event hooks.

### Thiết kế rõ quyết định

Application use case “Expire reservations” cần tuyên bố:

- Những rule nào có thể biểu diễn trong SQL WHERE.
- Events/audit có cần tạo cho từng reservation không.
- Concurrent CONFIRM/EXPIRE được giải quyết bằng điều kiện/version/locks nào.
- L1/L2 caches được invalidate/refresh như thế nào.

Không biến repository generic thành nơi âm thầm đổi status hàng loạt và bỏ business invariants.

## 73. Cân nhắc transaction khi xử lý batch lớn

Một job:

~~~text
For each Reservation:
  Load
  Confirm/Expire
  Save
~~~

nếu đặt trong một transaction và một EntityManager rất dài có thể giữ quá nhiều managed entities, tăng heap/dirty checking time.

### Giải pháp

- Query theo chunks/keyset khi phù hợp.
- Load đúng graph cần thiết.
- Flush/clear ở batch coordinator khi có ghi.
- Dùng transaction per chunk khi business cho phép partial commit.
- Checkpoint và idempotency cho restart.

### Không đem flush/clear vào domain method

Mọi `reservation.confirm()` phải giữ semantics như nhau dù nằm trong HTTP request, batch job hoặc simulation. Batch coordinator mới có quyền quyết định khi nào giải phóng persistence resources.

### Chia transaction thay đổi atomicity

Một job commit 1000 rows mỗi lần có thể để trạng thái nửa chừng khi lỗi; phải xác định đây có hợp lệ với nghiệp vụ không, thay vì chỉ tối ưu memory.

## 74. Transaction và thread confinement

`EntityManager` thông thường không được chia sẻ giữa threads theo cách tùy tiện. Trong Spring, injected shared EM proxy có thể route đến transaction-specific EM tương ứng, nhưng điều đó **không làm một actual persistence context trở thành thread-safe**.

### Đừng đưa managed entity vào thread pool

~~~java
executor.submit(
    () -> reservation.getItems().size()
);
~~~

Nếu `reservation` là managed JPA entity hoặc chứa lazy associations từ context thread khác, code có thể gây lỗi lifecycle/threading hoặc kết quả không được bảo đảm.

Hướng:

~~~text
Main thread:
  submit ReservationId command

Worker thread:
  start own use case/transaction
  load required state
  process/commit
~~~

Nếu chuyển một POJO detached qua threads, vẫn cần bảo đảm immutability/thread-safety của chính model và consistency của data snapshot, không chỉ vì nó không còn JPA managed.

## 75. Domain constructors và lifecycle callbacks

JPA cần một no-arg constructor có khả năng truy cập phù hợp cho entity. Lifecycle callbacks như `@PrePersist`, `@PreUpdate` có thể hỗ trợ metadata kỹ thuật:

~~~java
@PrePersist
void assignCreatedAt() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
~~~

### Không đặt toàn bộ business workflow vào callbacks

Ví dụ không phù hợp:

~~~java
@PreUpdate
void onConfirm() {
    kafkaProducer.send(...);
    chargeCreditCard(...);
}
~~~

Callbacks chạy theo JPA lifecycle/flush timing, có thể bị kích hoạt khi caller không mong đợi hoặc không chạy với bulk DML. External side effects trong callback khó bảo đảm transaction consistency, retry và testability.

### Domain rule cần được gọi tường minh

Method như `reservation.confirm(now)` truyền tải intent tốt hơn callback tự suy ra một change từ field status rồi cố thực hiện toàn workflow.

## 76. Domain events không nên phụ thuộc onFlush

Nếu event chỉ được tạo khi JPA flush:

~~~text
Domain transition
   |
   v
Wait for ORM dirty checking
   |
   v
Lifecycle listener inspects changes
   |
   v
Generate event
~~~

thì use case có thể bị phụ thuộc provider timing, @PreUpdate behavior và enhancement.

### Lựa chọn minh bạch

Domain method ghi nhận event **khi transition xảy ra**, application lưu outbox row **trong transaction**, outbox publisher gửi sau commit.

### Khi nào listener phù hợp?

Audit các metadata đơn giản hoặc integration với provider listener có thể phù hợp nếu behavior được hiểu rõ và test đầy đủ. Nhưng không nên dùng listener để che giấu business command cần authorization và domain validation.

## 77. Unit test domain không cần biết @Version

Một test:

~~~java
reservation.confirm(now);
assertEquals(
    ReservationStatus.CONFIRMED,
    reservation.status()
);
~~~

không cần assert `@Version` tăng từ 5 lên 6. Version thuộc persistence consistency test.

### Hai câu hỏi riêng

1. **Nghiệp vụ:** trạng thái chuyển có hợp lệ không?
2. **Lưu trữ:** concurrent updates có được phát hiện, commit/rollback có đúng không?

Đưa cả hai vào một test với full Spring/DB startup làm test domain chậm và khó chẩn đoán, trong khi chỉ unit test domain thì không kiểm được optimistic locking.

## 78. Observability không nên xâm nhập domain

Thông tin kỹ thuật:

~~~text
operation=reservation.confirm
transactionDurationMs=...
sqlStatements=...
dbConnectionWaitMs=...
optimisticConflicts=...
outboxPending=...
~~~

nên được ghi bởi application/infrastructure tracing, metrics và logging layers.

Domain có thể tạo business event hoặc chứa state transition reason, nhưng không nên import SQL tracer/connection-pool metrics vào `Reservation.confirm()`.

### Correlation ID

Request/command ID có thể được truyền qua application context để liên kết logs, outbox và retries, nhưng không nhất thiết phải là field bắt buộc của mọi domain entity.

### Cẩn trọng dữ liệu nhạy cảm

Không log raw customer PII, tenant secrets hoặc full SQL bind values chỉ để debug transaction timing.

## 79. Refactor từ service trộn lẫn kỹ thuật

Giả sử code ban đầu:

~~~java
public void confirm(UUID id) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();
        JpaReservationEntity row =
            em.find(JpaReservationEntity.class, id);

        if (row.status() != ReservationStatus.DRAFT) {
            throw new IllegalStateException();
        }

        row.applyStatus(ReservationStatus.CONFIRMED);
        em.flush();
        tx.commit();
    } catch (RuntimeException e) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw e;
    } finally {
        em.close();
    }
}
~~~

Code vừa quản lý EM, transaction, query và domain transition. Nó còn thiếu tenant/expiration checks.

### Lộ trình refactor từng bước

1. **Viết test domain invariant** cho DRAFT/CONFIRMED/CANCELED và expiration.
2. **Trích domain method `confirm(now)`** xử lý transition độc lập EM.
3. **Tạo Repository port** diễn đạt find trong tenant + save.
4. **Đưa JPQL/JPA mapping** vào adapter.
5. **Đưa transaction boundary** lên application service hoặc transaction decorator.
6. **Dùng trusted tenant/Clock** thay request-supplied tenant hoặc static time.
7. **Đưa external side effects** qua outbox/after-commit policy nếu cần.
8. **Viết integration tests** xác nhận commit/rollback, version và tenant scope.

### Không cần thay toàn bộ architecture cùng một lúc

Chỉ trích business transition ra khỏi class quản lý EM đã đem lại khả năng unit test độc lập. Sau đó có thể lần lượt tách repository port, DTOs, outbox và transaction policy tùy rủi ro.

## 80. Bảng quyết định: logic đặt ở đâu?

| Logic | Vị trí gợi ý | Lý do |
| --- | --- | --- |
| “DRAFT mới được confirm” | Domain entity | Business invariant |
| “Units phải > 0” | Domain/value object | Business validation |
| “Người dùng có quyền confirm” | Application/security | Trusted identity/permission |
| “Tìm Reservation trong tenant” | Repository port + adapter | Business-oriented query, enforced scope |
| “Transaction bao gồm reservation và outbox” | Application service/tx boundary | Use-case atomicity |
| “JPQL query/Criteria” | JPA adapter | Persistence implementation |
| “EntityManager.close()” | Resource owner/infrastructure | Technical lifecycle |
| “Flush theo 100 rows” | Batch infrastructure coordinator | Performance/resources |
| “ORDER BY + fetch plan” | Query adapter | SQL/data access efficiency |
| “Không để lộ customer PII” | Application API/authorization/DTO | Data protection |
| “Tăng version khi update” | JPA @Version/DB | Concurrency enforcement |
| “Outbox publish retry” | Messaging infrastructure | Delivery lifecycle |
| “Reservation đã hết hạn” | Domain rule dùng injected time | Business temporal rule |
| “Query timeout 2s” | Infrastructure policy | Operational guardrail |
| “Retry optimistic conflict” | Application orchestrator | Fresh transaction + domain re-evaluation |
| “HTTP 409 khi conflict” | API adapter/controller | Protocol mapping |
| “DB CHECK/UNIQUE” | Schema migrations | Defense-in-depth |

## 81. Sơ đồ tổng hợp: ai sở hữu vòng đời gì?

~~~text
Client/Worker
    |
    v
Application service
    | authorization, Clock, transaction policy
    |
    +------ Repository port
    |             |
    |             v
    |        JPA adapter
    |        EM/queries/mapping
    |             |
    |             v
    |           Database
    |
    +------ Domain aggregate
    |        invariants/transitions
    |
    +------ Outbox port
                  |
                  v
             Outbox DB row

Transaction commit
    |
    v
Background publisher
    |
    v
Broker / external system
~~~

Ranh giới quan trọng:

- **Domain** quyết định state transition.
- **Application service** xác định một unit of work.
- **Repository adapter** biết cách đọc/ghi bằng JPA.
- **Transaction/infrastructure** bảo đảm commit, rollback và resource cleanup.
- **Publisher** chịu trách nhiệm external delivery sau commit theo durability policy.

## 82. Bài tập thực hành

### Bài 1 — Hai vòng đời

Phân biệt “Reservation đã CONFIRMED” với “transaction đã COMMIT”. Một trong hai có tự bảo đảm điều kia không?

**Gợi ý:** Không. State in-memory và database durability là những khái niệm khác.

### Bài 2 — EntityManager trong domain

Điều gì không ổn khi định nghĩa `reservation.confirm(EntityManager em)`?

**Gợi ý:** Domain phụ thuộc JPA, flush/transaction timing, resource ownership và test runtime.

### Bài 3 — Phân tầng

Quy tắc “Chỉ DRAFT mới được confirm” thuộc domain, application service hay repository adapter?

**Gợi ý:** Domain invariant.

### Bài 4 — Transaction

Một use case cần cập nhật Reservation và Outbox. Tầng nào nên quyết định cả hai nằm cùng transaction?

**Gợi ý:** Application/use-case boundary; adapter thực hiện lưu trữ.

### Bài 5 — Repository port

Vì sao `Repository.getEntityManager()` thường là API không phù hợp để cho domain/application sử dụng?

**Gợi ý:** Rò rỉ chi tiết technical persistence lifecycle.

### Bài 6 — @Version

Domain method `confirm()` có cần biết Hibernate version predicate SQL không?

**Gợi ý:** Không; provider/adapter xử lý optimistic locking, domain xử lý transition.

### Bài 7 — Tách model

Nêu hai lợi ích và hai chi phí khi dùng `Reservation` POJO riêng với `JpaReservationEntity`.

**Gợi ý:** Independent tests/portability, nhưng cần mapper và stale-state policy.

### Bài 8 — Dùng chung model

Dùng cùng JPA entity làm domain model có bắt buộc là sai không?

**Gợi ý:** Không; giữ business methods độc lập EM/resource operations vẫn có thể hợp lý.

### Bài 9 — Managed vs detached

Sửa một detached JPA entity rồi commit một transaction không quản lý object ấy, điều gì xảy ra?

**Gợi ý:** Không tự được dirty checking; cần persistence flow đúng.

### Bài 10 — Domain POJO

Với mô hình domain tách JPA entity, vì sao service cần gọi `repository.save(reservation)` sau `reservation.confirm()`?

**Gợi ý:** Domain object không phải managed JPA entity.

### Bài 11 — Merge

`em.merge(detached)` trả về managed instance mới/hiện có. Sau đó sửa tiếp `detached` có được provider theo dõi tự động không?

**Gợi ý:** Không, phải xử lý returned managed instance hoặc use-case-specific mapping.

### Bài 12 — Flush

Tại sao không gọi `em.flush()` bên trong mỗi domain method?

**Gợi ý:** Đây là persistence timing, có thể gây DB IO quá sớm và tăng coupling.

### Bài 13 — Clear

Một generic repository gọi `em.clear()` trước khi trả kết quả. Nó có thể gây tác dụng phụ gì?

**Gợi ý:** Detach cả các managed entities khác mà caller đang dùng.

### Bài 14 — RESOURCE_LOCAL

Trong Java SE RESOURCE_LOCAL, ai nên bảo đảm `EntityManager.close()` xảy ra ở finally?

**Gợi ý:** Infrastructure/application-managed EM resource owner.

### Bài 15 — JTA

Có nên gọi `em.getTransaction().begin()` cho JTA-managed EntityManager không?

**Gợi ý:** Không; JTA/container transaction manager có cơ chế riêng.

### Bài 16 — Spring @Transactional

Nếu service dùng `@Transactional` nhưng được tạo bằng `new` rồi gọi method, annotation có chắc được Spring intercept không?

**Gợi ý:** Không; cần managed proxy/instrumentation phù hợp.

### Bài 17 — Thread

Vì sao không gửi managed `PurchaseOrder` có LAZY Lines qua `@Async` rồi mong worker tiếp tục sử dụng cùng context?

**Gợi ý:** Transaction/EM thường thread-bound và không được chia sẻ tùy tiện.

### Bài 18 — DTO

Một endpoint chỉ hiển thị ID/status/expiresAt. Vì sao Repository trả `ReservationSummary` tốt hơn trả toàn JPA entity graph?

**Gợi ý:** Bounded fields, không phụ thuộc lazy resource state và dễ kiểm soát serialization.

### Bài 19 — Lazy exception

Service trả entity rồi controller gọi `getCustomer().getName()` sau khi transaction đóng. Lỗi gì có thể xảy ra?

**Gợi ý:** LazyInitializationException hoặc provider-specific lifecycle failure.

### Bài 20 — OSIV

Bật OSIV có chắc loại bỏ vấn đề hiệu năng/lazy loading không?

**Gợi ý:** Không; có thể gây N+1 trong serialization.

### Bài 21 — Tenant

Người dùng gửi `tenantId` trong body; repository dùng giá trị đó để query dữ liệu. Đây là boundary an toàn chưa?

**Gợi ý:** Chưa; cần lấy scope từ trusted identity/authorization.

### Bài 22 — Constraint

Domain từ chối units âm. Database còn cần CHECK constraint không?

**Gợi ý:** Thường nên có defense-in-depth vì có writers/concurrency khác.

### Bài 23 — Concurrent booking

Hai transactions cùng thấy một ghế còn trống. Tại sao domain `canReserve()` không đủ?

**Gợi ý:** Snapshot race, cần atomic DB constraint/locking/version strategy.

### Bài 24 — Optimistic conflict

TX A và B cùng load version 3 rồi update. Sau khi A commit, B được phép silently overwrite không?

**Gợi ý:** Không nếu @Version được dùng đúng; cần conflict handling.

### Bài 25 — Retry

Sau `OptimisticLockException`, có nên gọi lại `flush()` trên cùng EntityManager không?

**Gợi ý:** Không; rollback rồi mở transaction/context mới, reload và re-evaluate.

### Bài 26 — Domain event

Vì sao `reservation.confirm()` không nên trực tiếp gọi Kafka producer?

**Gợi ý:** Side effect có thể xảy ra trước commit và không rollback được.

### Bài 27 — Outbox

Outbox row và Reservation status phải được ghi trong một transaction để đảm bảo điều gì?

**Gợi ý:** Atomicity của state change và durable event intent.

### Bài 28 — Exactly once

Transactional outbox có tự bảo đảm consumer xử lý event đúng một lần không?

**Gợi ý:** Không; thường có duplicate delivery, cần idempotent consumer.

### Bài 29 — After commit

Spring listener chạy sau commit nhưng process crash trước khi gửi email. Có thể mất notification không?

**Gợi ý:** Có; durable outbox/queue giải quyết yêu cầu reliability cao hơn.

### Bài 30 — Batch

Một job xử lý 2 triệu rows mà không clear context. Nên tối ưu ở domain method hay batch coordinator?

**Gợi ý:** Batch coordinator quyết định chunks, transaction boundaries và flush/clear.

### Bài 31 — Bulk DML

Bulk JPQL UPDATE trực tiếp trạng thái Reservation có chạy domain method `confirm()` và callbacks tương ứng như managed updates không?

**Gợi ý:** Không; phải xét invariants, version và events riêng.

### Bài 32 — Read-only

`@Transactional(readOnly=true)` có chắc biến entity query thành DTO query không?

**Gợi ý:** Không.

### Bài 33 — Fake repository

Vì sao fake repository nên copy-on-read khi test một model detached domain?

**Gợi ý:** Tránh test pass dù service quên save vì chia sẻ cùng Java reference.

### Bài 34 — Integration test

Vì sao cần mở EntityManager/transaction mới để kiểm tra state sau commit?

**Gợi ý:** Tránh L1 cache che giá trị thực trong DB.

### Bài 35 — Rollback

Một transaction update Reservation rồi outbox save fail. Test nên assert điều gì?

**Gợi ý:** Cả status update và outbox insert đều không commit.

### Bài 36 — Error mapping

Một database timeout có nên được chuyển thành `InvalidReservationTransition` không?

**Gợi ý:** Không; lỗi technical availability khác business invariant.

### Bài 37 — Query timeout

Reservation expiry 15 phút có phải cùng loại giới hạn với query timeout 2 giây không?

**Gợi ý:** Không; business temporal rule khác operational timeout.

### Bài 38 — Refactor

Hệ thống legacy có service trực tiếp gọi `EntityManager`, kiểm tra trạng thái rồi `em.flush()`. Nêu ba bước tách mà không cần viết lại toàn ứng dụng.

**Gợi ý:** Trích domain transition, Repository port/adapter và use-case transaction boundary.

### Bài 39 — Multiple databases

Một Spring `@Transactional` bao phủ hai repositories ở hai databases độc lập có tự atomic toàn bộ không?

**Gợi ý:** Không mặc định; xem transaction manager, XA/JTA hoặc eventual consistency/saga.

### Bài 40 — Thiết kế tổng hợp

Thiết kế use case **Confirm Reservation** cho hệ thống đa tenant, cập nhật inventory và gửi notification. Hãy chỉ rõ:

1. Domain invariants và state transitions.
2. Repository ports cần có.
3. Trusted authorization/tenant scope.
4. Transaction boundary.
5. Optimistic locking hoặc atomic inventory reservation.
6. Outbox/integration event.
7. Unit tests không cần database.
8. Integration tests cho commit, rollback và conflicts.
9. Retry/idempotency policy.
10. Resource owner và cleanup.

**Gợi ý:** Đừng cho domain gọi EntityManager hoặc broker. Application xác định unit of work, adapters quản lý JPA/DB, publisher xử lý integration delivery sau commit.

## 83. Bảng ghi nhớ nhanh

| Khái niệm | Nguyên tắc |
| --- | --- |
| Domain invariant | Đúng độc lập trạng thái JPA context |
| Domain entity | Methods biểu đạt hành vi nghiệp vụ |
| Application service | Orchestrate use case và transaction |
| Repository port | Business-oriented data access contract |
| JPA adapter | JPQL/Criteria, entity mapping, managed state |
| EntityManager | Technical persistence context API |
| Transaction manager | Begin/commit/rollback lifecycle |
| JDBC Connection | Infrastructure resource |
| `@Transactional` | Đặt ở use-case boundary phù hợp |
| RESOURCE_LOCAL | EntityTransaction do resource owner quản lý |
| JTA | Không dùng EntityTransaction theo kiểu RESOURCE_LOCAL |
| Managed JPA entity | Provider có thể dirty track |
| Detached JPA entity | Không tự flush changes |
| Detached domain POJO | Cần adapter save để persistence |
| `merge()` | Copy state vào managed instance, không “reattach” object gốc |
| `flush()` | Đồng bộ SQL, không phải commit |
| `clear()` | Detach toàn context, có thể mất unflushed state |
| Fetch plan | Quyết định trong query adapter |
| Lazy loading | Phụ thuộc context lifetime, cần xử lý ở boundary |
| DTO projection | Output độc lập managed graph |
| Aggregate root | Bảo vệ invariants của unit nghiệp vụ |
| @Version | Optimistic concurrency control |
| DB constraints | Defense-in-depth và atomic enforcement |
| Authorization | Application/security, trusted scope |
| Domain event | Sự kiện nghiệp vụ, không phải network request |
| Outbox | Durable event intent cùng DB transaction |
| Event consumer | Idempotent với at-least-once delivery |
| Retry | Transaction mới, reload/re-evaluate |
| @Async/background | Không mặc định chia sẻ EM/transaction |
| Batch processing | Flush/clear và chunk ở coordinator |
| Bulk JPQL | Có thể bypass domain lifecycle và @Version policy |
| Unit test domain | Không cần JPA/DB |
| Fake repository | Test orchestration, không thay DB tests |
| Integration test | Commit/rollback/SQL/version/tenant |
| Thiết kế tốt | Business logic ổn định dù tài nguyên thay đổi |

## Kết luận

**Giữ logic nghiệp vụ độc lập với vòng đời tài nguyên kỹ thuật là trọng tâm của một thiết kế Repository JPA bền vững.** Quy tắc “Reservation nào được xác nhận”, “trạng thái nào hợp lệ” hay “số lượng phải dương” cần được diễn đạt rõ trong domain. Chúng không nên phụ thuộc vào việc Hibernate Session còn mở, `EntityManager` đang managed hay detached, flush chạy lúc nào, hoặc JDBC connection được giải phóng ra sao.

Application service điều phối **một use case**: kiểm tra danh tính/quyền, truy cập repository, gọi domain methods, xác định atomic transaction boundary và ghi outbox khi cần. Repository port diễn đạt những thao tác có ý nghĩa với nghiệp vụ, trong khi JPA adapter quyết định JPQL/Criteria, entity mapping, loaded state và cách ghi vào database. Resource owner/framework quản lý open/close, flush, rollback, timeouts và cleanup.

Tách domain model khỏi JPA entities giúp domain độc lập hơn nhưng phát sinh mapper và state-copy costs; sử dụng chung JPA entity có thể hợp lý khi business methods vẫn không tự điều khiển persistence lifecycle. Không cần áp dụng một sơ đồ tầng phức tạp chỉ vì phong cách kiến trúc. Thước đo quan trọng là **quy tắc nghiệp vụ có thể được hiểu, thử và thay đổi mà không phải sửa logic quản lý tài nguyên**, còn persistence/transaction behavior có thể được kiểm chứng qua integration tests riêng.

Khi xử lý concurrency và external side effects, không được hiểu “domain thuần” là bỏ qua database. `@Version`, database constraints, locks và transaction boundaries vẫn cần bảo vệ correctness khi nhiều writers cùng thao tác; transactional outbox và idempotency giúp giữ nhất quán giữa dữ liệu trong DB và các thông báo ra bên ngoài. Những cơ chế kỹ thuật này **hỗ trợ domain invariants**, chứ không nên lẫn vào API của domain method.

Nguyên tắc thực hành: **Domain quyết định điều gì đúng; application quyết định một công việc cần thực hiện; repository chuyển ý định đó thành truy cập dữ liệu; infrastructure sở hữu vòng đời tài nguyên và đảm bảo nhất quán tại ranh giới kỹ thuật.** Khi các trách nhiệm ấy rõ ràng, ứng dụng có thể đổi provider, transaction model, fetch plan hoặc cách triển khai batch/async mà không phải viết lại các quy tắc nghiệp vụ cốt lõi.







