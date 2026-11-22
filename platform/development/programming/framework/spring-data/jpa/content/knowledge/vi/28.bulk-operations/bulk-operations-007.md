# Đếm số dòng tác động và xác nhận điều kiện cập nhật

## 1. Mục tiêu

Trong Spring Data JPA, một truy vấn bulk `UPDATE` hoặc `DELETE` có thể tác động tới nhiều Entity bằng một câu lệnh. Phương thức Repository có thể trả về số lượng Entity bị tác động để Service biết thao tác đã khớp bao nhiêu bản ghi. Kết hợp số lượng này với điều kiện `WHERE` rõ ràng giúp xác nhận trạng thái trước khi thay đổi dữ liệu.

Sau bài học, bạn có thể:
- Nhận số lượng bản ghi bị tác động từ JPQL bulk update/delete.
- Dùng `@Modifying` và transaction đúng cách trong Spring Data JPA.
- Thiết kế điều kiện `WHERE` để chỉ cập nhật các bản ghi đang ở trạng thái mong đợi.
- Phân biệt số lượng tác động với truy vấn đếm trước khi cập nhật.
- Dùng `@Version` và điều kiện version để phát hiện cập nhật cạnh tranh trong bulk DML.
- Xử lý persistence context sau bulk update/delete.
- Xác định khi nào cần rollback nếu số lượng thực tế khác số lượng mong đợi.
- Kiểm thử affected count và điều kiện cập nhật trên database.

## 2. Bulk update/delete và số lượng tác động

Bulk DML là một câu lệnh JPQL `UPDATE` hoặc `DELETE` áp dụng trực tiếp lên tập Entity thỏa điều kiện. Spring Data JPA đánh dấu phương thức Repository bằng `@Modifying` để thực thi câu lệnh thay đổi dữ liệu thay vì truy vấn đọc thông thường.

Ví dụ:

```java
@Modifying
@Query("update PurchaseOrder o set o.status = :newStatus where o.status = :oldStatus")
int changeStatus(OrderStatus oldStatus, OrderStatus newStatus);
```

Kiểu trả về `int` nhận số Entity bị tác động theo kết quả thực thi bulk query. `0` nghĩa là không có Entity nào khớp toàn bộ điều kiện `WHERE`; số dương cho biết có Entity được cập nhật.

Với bulk delete, cách nhận số lượng tương tự:

```java
@Modifying
@Query("delete from PurchaseOrder o where o.status = :status")
int deleteByStatus(OrderStatus status);
```

Không cần tải từng Entity vào bộ nhớ rồi gọi `save()` hoặc `delete()` trong vòng lặp nếu nghiệp vụ thực sự là một phép cập nhật hàng loạt đơn giản. Bulk DML thường giảm số lần round-trip và tránh dirty checking cho từng Entity.

## 3. Ý nghĩa và giới hạn của affected count

Với JPQL, thao tác `executeUpdate()` trả về số Entity được cập nhật hoặc xóa. Spring Data chuyển kết quả đó về kiểu số nguyên của phương thức `@Modifying`.

| Kết quả | Cách hiểu thường dùng |
| ---: | --- |
| `0` | Không có Entity nào thỏa tất cả điều kiện `WHERE` tại thời điểm câu lệnh chạy. |
| `1` | Một Entity được tác động. |
| `n > 1` | Có `n` Entity được tác động bởi câu lệnh bulk. |

Đối với cập nhật theo khóa chính, kết quả mong đợi thường là `1`. Nếu nhận `0`, có thể bản ghi không tồn tại, trạng thái hiện tại đã thay đổi, version không còn khớp hoặc điều kiện khác không còn đúng. Chỉ riêng con số `0` không cho biết chính xác nguyên nhân nào.

Đối với bulk update theo điều kiện, affected count là số lượng Entity mà câu lệnh đã tác động. Không diễn giải con số này thành số lượng giá trị field chắc chắn thay đổi theo cách nghiệp vụ mong muốn. Với native SQL, update count còn phụ thuộc quy tắc báo cáo của JDBC driver và database; hãy xác nhận semantics trên engine đang dùng.

Không dùng affected count để suy ra các side effect đã chạy trên từng Entity. Bulk DML bỏ qua lifecycle callback của Entity và không gọi logic trong setter hoặc Service cho từng bản ghi.

## 4. Xác nhận điều kiện cập nhật bằng WHERE

Để tránh ghi đè trạng thái mới hơn, đưa điều kiện nghiệp vụ vào chính câu lệnh `UPDATE`. Ví dụ chỉ chuyển đơn hàng từ `PENDING` sang `EXPIRED` nếu thời hạn đã qua:

```jpql
update PurchaseOrder o
set o.status = :expiredStatus
where o.status = :pendingStatus
  and o.expiresAt < :cutoff
```

Điều kiện `o.status = :pendingStatus` xác nhận trạng thái trước khi cập nhật. Điều kiện `o.expiresAt < :cutoff` xác nhận thời hạn. Database kiểm tra điều kiện và cập nhật trong cùng một statement.

Đây là cách an toàn hơn việc đọc trạng thái trước ở Java rồi chạy một câu update không có điều kiện trạng thái. Giữa lần đọc và lần ghi, một transaction khác có thể thay đổi dữ liệu.

### 4.1. Không dựa vào count trước để xác nhận update

Có thể viết một truy vấn `count` trước thao tác để xem hiện có bao nhiêu đơn phù hợp. Tuy nhiên, count và update là hai statement riêng biệt:

1. Transaction A đếm được 10 đơn `PENDING` đã hết hạn.
2. Transaction B thay đổi trạng thái của 3 đơn.
3. Transaction A chạy update và chỉ còn 7 đơn thỏa điều kiện.

Vì vậy, count trước chỉ phù hợp cho preview hoặc báo cáo tại thời điểm đọc. Nó không bảo đảm số dòng sẽ được cập nhật sau đó. **Affected count trả về từ chính câu lệnh UPDATE là kết quả cần dùng để xác nhận thao tác đã tác động bao nhiêu Entity.**

Nếu nghiệp vụ yêu cầu đúng một số lượng cụ thể hoặc phải cập nhật tất cả/không cập nhật gì, hãy so sánh affected count trong cùng transaction và rollback khi không đạt điều kiện.

### 4.2. Điều kiện nên đủ chặt

Điều kiện `WHERE` nên chứa mọi tiền đề cần đúng tại thời điểm ghi, ví dụ:

- ID của bản ghi.
- Tenant hoặc phạm vi dữ liệu mà người gọi được phép thay đổi.
- Trạng thái hiện tại được phép chuyển.
- Version mong đợi nếu dùng optimistic concurrency.
- Điều kiện thời gian hoặc điều kiện nghiệp vụ khác.

Không chỉ kiểm tra điều kiện ở Controller hoặc Service rồi bỏ chúng khỏi câu lệnh update. Kiểm tra tại thời điểm ghi giúp giảm race condition.

## 5. Mô hình ví dụ

Ví dụ dùng Java 17+, Spring Boot 3.5.x, Spring Data JPA và Hibernate do Spring Boot quản lý phiên bản. Một đơn hàng có trạng thái, thời điểm hết hạn và version.

### 5.1. Enum OrderStatus

`src/main/java/com/example/orders/OrderStatus.java`:

```java
package com.example.orders;

public enum OrderStatus {
    PENDING,
    PAID,
    EXPIRED,
    CANCELLED
}
```

### 5.2. Entity PurchaseOrder

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    public PurchaseOrder(OrderStatus status, Instant expiresAt) {
        if (status == null || expiresAt == null) {
            throw new IllegalArgumentException("Status and expiresAt are required");
        }
        this.status = status;
        this.expiresAt = expiresAt;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getExpiresAt() {
        return expiresAt;
    }

    public long getVersion() {
        return version;
    }
}
```

`@Version` cho phép JPA kiểm soát optimistic locking khi cập nhật Entity theo cách thông thường. Tuy nhiên, bulk JPQL update không tự động thực hiện kiểm tra version hoặc tăng version như dirty checking của một Entity managed. Bài học sẽ xử lý điều này tường minh.

## 6. Repository trả về affected count

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update PurchaseOrder o
           set o.status = :expiredStatus,
               o.version = o.version + 1
           where o.status = :pendingStatus
             and o.expiresAt < :cutoff
           """)
    int expirePendingOrders(
            @Param("pendingStatus") OrderStatus pendingStatus,
            @Param("expiredStatus") OrderStatus expiredStatus,
            @Param("cutoff") Instant cutoff);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update PurchaseOrder o
           set o.status = :newStatus,
               o.version = o.version + 1
           where o.id = :id
             and o.status = :expectedStatus
             and o.version = :expectedVersion
           """)
    int updateStatusIfCurrent(
            @Param("id") Long id,
            @Param("expectedStatus") OrderStatus expectedStatus,
            @Param("expectedVersion") long expectedVersion,
            @Param("newStatus") OrderStatus newStatus);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           delete from PurchaseOrder o
           where o.status = :status
             and o.expiresAt < :cutoff
           """)
    int deleteExpiredOrders(
            @Param("status") OrderStatus status,
            @Param("cutoff") Instant cutoff);

    long countByStatusAndExpiresAtBefore(OrderStatus status, Instant cutoff);
}
```

Điểm cần chú ý:

- `@Modifying` báo cho Spring Data đây là câu lệnh thay đổi dữ liệu.
- Kiểu trả về `int` nhận số Entity được cập nhật hoặc xóa.
- `flushAutomatically = true` yêu cầu flush các thay đổi đang chờ trước khi chạy bulk query.
- `clearAutomatically = true` yêu cầu clear persistence context sau khi query chạy để tránh tiếp tục đọc các Entity managed có trạng thái cũ.
- `version = version + 1` được ghi rõ vì bulk DML không tự tăng version.

Phương thức `countByStatusAndExpiresAtBefore` chỉ phục vụ việc đếm/preview. Không dùng kết quả count đó thay cho affected count của update.

## 7. Gọi Repository trong transaction

Phương thức bulk DML nên được thực thi bên trong transaction. Có thể đặt transaction boundary ở Service để bao trọn thao tác và bước xác nhận:

`src/main/java/com/example/orders/OrderMaintenanceService.java`:

```java
package com.example.orders;

import java.time.Instant;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMaintenanceService {
    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int expirePendingOrders(Instant cutoff) {
        Objects.requireNonNull(cutoff, "cutoff is required");
        return repository.expirePendingOrders(
                OrderStatus.PENDING, OrderStatus.EXPIRED, cutoff);
    }

    @Transactional
    public void markPaid(Long id, long expectedVersion) {
        int affected = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, expectedVersion, OrderStatus.PAID);

        if (affected == 0) {
            throw new IllegalStateException(
                    "Order is missing or no longer matches the expected state");
        }
        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected to update one order but affected " + affected);
        }
    }
}
```

Trong `markPaid`, điều kiện theo ID và version phải khớp đúng một Entity. Nếu kết quả là `0`, bản ghi có thể không tồn tại, trạng thái đã thay đổi hoặc version đã cũ. Nếu kết quả khác `1`, Service báo lỗi vì giả định khóa chính duy nhất không còn đúng.

Exception runtime được ném ra trong transaction mặc định khiến Spring rollback transaction. Có thể thay `IllegalStateException` bằng exception nghiệp vụ riêng và ánh xạ thành HTTP 404 hoặc 409 theo hợp đồng API. Không thể xác định chắc chắn lý do `0` chỉ từ affected count; nếu cần phân biệt missing với stale state, phải thiết kế thêm bước đọc hoặc kết quả nghiệp vụ phù hợp.

## 8. Xác nhận một cập nhật có điều kiện

Giả sử client đọc một đơn hàng và nhận được:

```text
id = 42
status = PENDING
version = 3
```

Khi client gửi yêu cầu thanh toán, câu lệnh update dùng ba điều kiện:

```jpql
update PurchaseOrder o
set o.status = PAID,
    o.version = o.version + 1
where o.id = 42
  and o.status = PENDING
  and o.version = 3
```

Nếu không có transaction nào thay đổi đơn sau lần đọc, câu lệnh tác động một Entity và version tăng từ 3 lên 4. Nếu một transaction khác đã cập nhật đơn và version thành 4, điều kiện `o.version = 3` không còn đúng; câu lệnh tác động 0 Entity.

Đây là mẫu compare-and-set: cập nhật chỉ thành công khi trạng thái hiện tại vẫn bằng giá trị mà caller đã đọc. Nó phù hợp cho chuyển trạng thái, xác nhận đơn, giữ chỗ hoặc các thao tác cần phát hiện dữ liệu đã thay đổi.

**Lưu ý:** vì đây là bulk update, Hibernate không tự ném optimistic locking exception khi version không khớp. Service phải kiểm tra affected count và xử lý kết quả `0`.

## 9. Khi cần đúng số lượng hoặc all-or-nothing

Với một thao tác hàng loạt, có thể nghiệp vụ yêu cầu cập nhật đúng `expectedCount` bản ghi. Ví dụ một đợt xử lý phải cập nhật đủ 50 đơn:

```java
@Transactional
public int expireExactly(
        Instant cutoff, int expectedCount) {
    int affected = repository.expirePendingOrders(
            OrderStatus.PENDING, OrderStatus.EXPIRED, cutoff);

    if (affected != expectedCount) {
        throw new IllegalStateException(
                "Expected " + expectedCount + " updates but affected " + affected);
    }

    return affected;
}
```

Nếu exception là unchecked và không bị bắt nuốt bên trong transaction, transaction sẽ rollback toàn bộ thao tác. Cần bảo đảm Service method thực sự chạy qua Spring transaction proxy; gọi method `@Transactional` từ một method khác trong cùng instance (self-invocation) không kích hoạt proxy theo cách thông thường.

Nếu nghiệp vụ chấp nhận cập nhật một phần, không rollback chỉ vì count thấp hơn dự kiến. Hãy trả số lượng thực tế và để caller quyết định bước tiếp theo.

Không lấy `countBy...()` trước rồi giả định update sẽ có cùng số lượng. Nếu cần kiểm tra all-or-nothing dựa trên điều kiện cạnh tranh, hãy dùng một câu lệnh có điều kiện, affected count, transaction và cơ chế khóa/isolation phù hợp với yêu cầu.

## 10. Bulk DML và @Version

Với thao tác cập nhật Entity thông thường:

```java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.markPaid();
```

JPA/Hibernate theo dõi Entity managed. Khi flush, provider thường tạo UPDATE có điều kiện version hiện tại, tăng version và phát hiện xung đột optimistic locking.

Bulk JPQL hoạt động khác:

- Không tải từng Entity để dirty checking.
- Không tự kiểm tra `@Version` như thao tác update Entity thông thường.
- Không tự tăng version attribute nếu câu lệnh không yêu cầu.
- Không gọi `@PreUpdate`, `@PostUpdate` hoặc callback tương ứng cho từng Entity.

Nếu bulk update tác động Entity có `@Version`, hãy quyết định rõ chính sách version. Khi cần phát hiện cập nhật cạnh tranh, thêm version mong đợi vào `WHERE` và tăng version trong `SET`, như phương thức `updateStatusIfCurrent` ở trên.

Với bulk update nhiều dòng, có thể tăng version từng dòng bằng `o.version = o.version + 1`. Tuy nhiên, câu lệnh vẫn không thực hiện kiểm tra version đầu vào cho từng Entity. Nó chỉ tăng version để các transaction khác đang giữ version cũ phát hiện xung đột ở lần update Entity thông thường tiếp theo.

## 11. Persistence context sau bulk update/delete

Bulk DML chạy trực tiếp trên database, nên các Entity đã được load trong persistence context có thể giữ giá trị cũ.

Ví dụ:

1. Service tải `PurchaseOrder` với status `PENDING` vào persistence context.
2. Repository chạy bulk update đổi status trong database thành `EXPIRED`.
3. Service tiếp tục đọc object đã tải trước đó và vẫn thấy `PENDING` vì object managed chưa được đồng bộ tự động với bulk statement.

Có ba cách xử lý thường dùng:

- `clearAutomatically = true`: Spring Data clear toàn bộ persistence context sau khi modifying query chạy.
- Gọi `EntityManager.clear()` sau bulk query khi muốn tự kiểm soát thời điểm clear.
- Gọi `EntityManager.refresh(entity)` cho Entity cụ thể cần đồng bộ lại, nếu Entity vẫn managed và cách dùng phù hợp.

Clear toàn bộ persistence context làm tất cả Entity managed hiện tại trở thành detached, kể cả những Entity không liên quan tới bulk query. Vì vậy, cân nhắc phạm vi transaction và thứ tự thao tác.

`flushAutomatically = true` giúp đồng bộ các thay đổi đang chờ trước bulk query. Kết hợp flush trước và clear sau giúp tránh vừa bỏ qua thay đổi chưa flush, vừa đọc lại state cũ từ persistence context.

## 12. Bulk delete và số lượng bị xóa

Bulk delete cũng trả về số Entity bị xóa:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("delete from PurchaseOrder o where o.status = :status and o.expiresAt < :cutoff")
int deleteExpiredOrders(
        @Param("status") OrderStatus status,
        @Param("cutoff") Instant cutoff);
```

Nếu method trả về `int`, Service có thể ghi nhận số đơn đã bị xóa và kiểm tra giới hạn nghiệp vụ. Tuy nhiên, bulk delete bỏ qua lifecycle callback của từng Entity và không áp dụng cascade remove theo vòng đời Entity như khi gọi `EntityManager.remove()` cho từng object.

Nếu database có foreign key, thao tác xóa có thể bị từ chối khi còn bản ghi con tham chiếu, trừ khi schema có `ON DELETE CASCADE` phù hợp. Quy tắc cascade của database là một cơ chế riêng, không phải cascade remove của JPA.

Không dùng bulk delete nếu nghiệp vụ yêu cầu chạy logic xóa từng Entity, phát sự kiện domain cho từng bản ghi hoặc thực hiện cascade JPA. Khi đó, tải và xóa Entity theo batch hoặc thiết kế quy trình xử lý riêng.

## 13. Phân biệt JPQL bulk count với JDBC batch

Hai khái niệm có thể cùng xuất hiện trong một ứng dụng nhưng có ý nghĩa khác nhau:

| Cơ chế | Cách hoạt động | Kết quả đếm |
| --- | --- | --- |
| JPQL bulk update/delete | Một câu lệnh tác động trực tiếp lên tập Entity thỏa `WHERE`. | `executeUpdate()`/phương thức `@Modifying` trả số Entity bị tác động. |
| JDBC batching | Gom nhiều câu INSERT/UPDATE/DELETE riêng lẻ để gửi theo batch. | JDBC driver trả update count theo từng lệnh hoặc batch result; semantics phụ thuộc driver. |
| Entity-by-Entity update | Tải từng Entity, thay đổi object và để dirty checking ghi lại. | Không có một affected count tổng tự động từ method update; Service tự đếm số Entity đã xử lý nếu cần. |

Không nhầm `hibernate.jdbc.batch_size` với số dòng được tác động bởi một câu JPQL bulk update. JDBC batching tối ưu việc gửi nhiều câu lệnh ghi; bulk DML dùng một câu lệnh điều kiện cho nhiều Entity.

## 14. Kiểm thử affected count với H2

Ví dụ dùng `spring-boot-starter-data-jpa`, H2 và `spring-boot-starter-test`. `@DataJpaTest` tạo test slice và transaction cho từng test.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:bulkdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/orders/PurchaseOrderBulkDmlTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderBulkDmlTest {
    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    private PurchaseOrder order(OrderStatus status, String expiresAt) {
        return new PurchaseOrder(status, Instant.parse(expiresAt));
    }

    @Test
    void returnsNumberOfOrdersUpdatedByBulkQuery() {
        PurchaseOrder first = entityManager.persist(order(
                OrderStatus.PENDING, "2026-01-01T00:00:00Z"));
        PurchaseOrder second = entityManager.persist(order(
                OrderStatus.PENDING, "2026-01-02T00:00:00Z"));
        PurchaseOrder future = entityManager.persist(order(
                OrderStatus.PENDING, "2026-02-01T00:00:00Z"));
        PurchaseOrder paid = entityManager.persist(order(
                OrderStatus.PAID, "2026-01-01T00:00:00Z"));
        entityManager.flush();

        Long firstId = first.getId();
        Long secondId = second.getId();
        Long futureId = future.getId();
        Long paidId = paid.getId();

        int affected = repository.expirePendingOrders(
                OrderStatus.PENDING,
                OrderStatus.EXPIRED,
                Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(affected).isEqualTo(2);
        assertThat(entityManager.find(PurchaseOrder.class, firstId).getStatus())
                .isEqualTo(OrderStatus.EXPIRED);
        assertThat(entityManager.find(PurchaseOrder.class, secondId).getStatus())
                .isEqualTo(OrderStatus.EXPIRED);
        assertThat(entityManager.find(PurchaseOrder.class, futureId).getStatus())
                .isEqualTo(OrderStatus.PENDING);
        assertThat(entityManager.find(PurchaseOrder.class, paidId).getStatus())
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void conditionalUpdateUsesExpectedStatusAndVersion() {
        PurchaseOrder order = entityManager.persist(order(
                OrderStatus.PENDING, "2026-02-01T00:00:00Z"));
        entityManager.flush();
        Long id = order.getId();
        long initialVersion = order.getVersion();
        entityManager.clear();

        int firstUpdate = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, initialVersion, OrderStatus.PAID);
        int staleUpdate = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, initialVersion, OrderStatus.CANCELLED);

        assertThat(firstUpdate).isEqualTo(1);
        assertThat(staleUpdate).isZero();

        PurchaseOrder reloaded = entityManager.find(PurchaseOrder.class, id);
        assertThat(reloaded.getStatus()).isEqualTo(OrderStatus.PAID);
        assertThat(reloaded.getVersion()).isEqualTo(initialVersion + 1);
    }

    @Test
    void returnsZeroWhenNoOrderMatchesTheUpdateCondition() {
        int affected = repository.expirePendingOrders(
                OrderStatus.PENDING,
                OrderStatus.EXPIRED,
                Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(affected).isZero();
    }

    @Test
    void returnsNumberOfOrdersDeletedByBulkQuery() {
        PurchaseOrder expiredOne = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-01-01T00:00:00Z"));
        PurchaseOrder expiredTwo = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-01-02T00:00:00Z"));
        PurchaseOrder stillValid = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-02-01T00:00:00Z"));
        entityManager.flush();

        Long firstId = expiredOne.getId();
        Long secondId = expiredTwo.getId();
        Long validId = stillValid.getId();

        int deleted = repository.deleteExpiredOrders(
                OrderStatus.EXPIRED, Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(deleted).isEqualTo(2);
        assertThat(entityManager.find(PurchaseOrder.class, firstId)).isNull();
        assertThat(entityManager.find(PurchaseOrder.class, secondId)).isNull();
        assertThat(entityManager.find(PurchaseOrder.class, validId)).isNotNull();
    }
}
```

Test đầu xác nhận update trả về `2` và chỉ đổi các đơn thỏa cả trạng thái lẫn cutoff. Test thứ hai xác nhận lần update đầu tác động đúng một Entity, version tăng một đơn vị và lần update dùng version cũ trả về `0`. Test thứ ba xác nhận không có dòng phù hợp thì count bằng `0`. Test cuối kiểm tra số Entity bị bulk delete.

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và cả bốn test đều thành công. Đây là kết quả kỳ vọng từ ví dụ, không phải log build đã chạy trong môi trường này.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Method `@Query` báo lỗi khi chạy update | Thiếu `@Modifying` hoặc query vẫn là SELECT. | Thêm `@Modifying` cho JPQL UPDATE/DELETE. |
| Affected count bằng 0 | Không có Entity nào khớp mọi điều kiện `WHERE`. | Kiểm tra ID, trạng thái, cutoff, version và tenant scope; không suy đoán một nguyên nhân duy nhất. |
| Đếm trước 5 nhưng update chỉ tác động 4 | Dữ liệu thay đổi giữa hai statement hoặc transaction khác cập nhật trước. | Dùng affected count của UPDATE; đặt điều kiện bảo vệ ngay trong câu lệnh. |
| Entity đã load vẫn hiển thị trạng thái cũ | Bulk DML không đồng bộ object đang managed. | Flush trước nếu cần và clear/refresh persistence context sau query. |
| Version không tăng sau bulk update | Bulk DML không tự áp dụng version management như dirty checking. | Tăng version tường minh trong `SET` khi chính sách yêu cầu. |
| Không phát hiện stale update bằng `@Version` | Bulk DML bỏ qua optimistic locking tự động. | Đưa version mong đợi vào `WHERE`, tăng version và kiểm tra affected count. |
| Callback hoặc cascade không chạy | Bulk DML bỏ qua lifecycle của từng Entity. | Dùng thao tác Entity-by-Entity nếu cần callback hoặc cascade JPA. |
| Transaction không rollback khi count sai | Exception bị bắt và không ném lại, hoặc code chạy ngoài transaction boundary mong muốn. | Ném unchecked exception trong transaction hoặc cấu hình rollback rõ ràng. |
| Bulk delete bị foreign key từ chối | Bản ghi con vẫn tham chiếu Entity cha. | Xóa dữ liệu con theo quy trình nghiệp vụ hoặc thiết kế FK cascade có chủ đích. |
| Native SQL trả affected count khác kỳ vọng | JDBC driver/database có quy tắc báo update count riêng. | Kiểm thử trên engine/driver thật và ghi rõ semantics của hệ thống. |

## 16. Nguyên tắc triển khai

1. Dùng kiểu trả về `int` cho phương thức JPQL bulk update/delete để nhận số Entity bị tác động.
2. Đưa các tiền đề nghiệp vụ quan trọng vào `WHERE`, ví dụ ID, tenant, trạng thái và version.
3. Dùng affected count từ chính statement để xác nhận kết quả; count trước chỉ là preview vì có thể bị race condition.
4. Với cập nhật một Entity, coi `1` là thành công; `0` là không khớp điều kiện; số lớn hơn `1` là vi phạm giả định về khóa duy nhất.
5. Nếu cần đúng số lượng hoặc all-or-nothing, so sánh count trong transaction và rollback khi sai.
6. Nhớ rằng bulk DML bỏ qua dirty checking, callback, cascade Entity và optimistic locking tự động.
7. Nếu dùng `@Version`, thêm điều kiện version vào `WHERE` và tăng version trong `SET` khi cần compare-and-set.
8. Dùng `flushAutomatically` và `clearAutomatically` có chủ đích; clear sẽ detach mọi Entity managed trong persistence context.
9. Không dùng bulk DML khi nghiệp vụ cần xử lý từng Entity hoặc phát side effect riêng cho từng bản ghi.
10. Kiểm thử cả trường hợp count bằng 0, count bằng 1, nhiều bản ghi, version cũ và delete.
11. Kiểm tra SQL và affected count trên database thực tế nếu ứng dụng dùng native query hoặc phụ thuộc driver.

## 17. Checklist hoàn thành

- [ ] Giải thích được bulk JPQL UPDATE/DELETE và vai trò của `@Modifying`.
- [ ] Nhận số Entity bị tác động bằng kiểu trả về `int`.
- [ ] Giải thích được ý nghĩa của count bằng 0, 1 hoặc lớn hơn 1.
- [ ] Đưa điều kiện trạng thái/thời gian/phạm vi vào chính câu lệnh `WHERE`.
- [ ] Hiểu vì sao count trước update không bảo đảm affected count sau update.
- [ ] Dùng transaction và rollback khi số lượng thực tế không đạt yêu cầu.
- [ ] Phân biệt bulk DML với cập nhật Entity thông thường.
- [ ] Xử lý `@Version` tường minh trong bulk update khi cần optimistic concurrency.
- [ ] Đồng bộ persistence context bằng flush, clear hoặc refresh.
- [ ] Hiểu bulk delete không chạy cascade và callback Entity.
- [ ] Kiểm thử affected count và điều kiện cập nhật bằng `@DataJpaTest`.

Khi hoàn thành, bạn có thể dùng affected count để xác nhận bulk operation, bảo vệ điều kiện cập nhật ngay tại database và xử lý an toàn các trường hợp không có bản ghi phù hợp hoặc dữ liệu đã bị thay đổi đồng thời.