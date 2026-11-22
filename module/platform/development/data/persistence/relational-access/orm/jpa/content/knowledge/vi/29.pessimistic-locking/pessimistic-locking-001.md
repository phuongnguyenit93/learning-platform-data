# Khi nào cần khóa bản ghi ở cơ sở dữ liệu trong JPA?

Trong ứng dụng JPA, nhiều giao dịch thường truy cập cùng một bản ghi. Đọc cùng dữ liệu không phải vấn đề; rủi ro xuất hiện khi **quyết định nghiệp vụ dựa trên trạng thái vừa đọc** nhưng trạng thái đó bị một giao dịch khác thay đổi trước khi giao dịch hiện tại hoàn tất. Khi ấy, hai yêu cầu riêng lẻ đều có vẻ hợp lệ nhưng kết quả cuối cùng có thể vi phạm quy tắc của hệ thống.

Một phương án là **khóa bi quan (pessimistic locking)**: yêu cầu cơ sở dữ liệu giữ khóa phù hợp trên bản ghi trong một transaction, để những giao dịch xung đột không thể đồng thời thay đổi bản ghi đó theo cách phá vỡ quy tắc đã thiết kế.

Trong JPA, ví dụ:

```java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Hoặc:

```java
List<InventoryItem> items = entityManager.createQuery(
    """
    select i
    from InventoryItem i
    where i.id = :id
      and i.tenantId = :tenant
    """,
    InventoryItem.class
)
.setParameter("id", itemId)
.setParameter("tenant", authorizedTenantId)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
```

Hai cách trên biểu diễn ý định yêu cầu **khóa ghi bi quan** ở cấp JPA. Provider sẽ sử dụng cơ chế tương ứng của database/dialect, thường liên quan `SELECT ... FOR UPDATE` hoặc những câu lệnh khóa tương đương.

Nhưng **khóa bản ghi không phải một “nút tăng tính an toàn” nên bật cho mọi truy vấn**. Nó có chi phí: chờ đợi, tắc nghẽn, deadlock, timeout, transaction kéo dài và giảm throughput. Rất nhiều trường hợp chỉ cần `@Version`, một câu `UPDATE ... WHERE ...` có điều kiện hoặc UNIQUE constraint là đủ — đôi khi còn tốt hơn khóa trước rồi mới cập nhật.

Bài học thuộc chương **Khóa bi quan** trong module *Data Persistence Relational Access ORM JPA*. Trọng tâm là **nhận biết khi nào cần khóa bản ghi ở cơ sở dữ liệu**, cách thực hiện an toàn bằng JPA, và cách phân biệt tình huống nên/không nên khóa.

> **Nguyên tắc chính:** Chỉ giữ khóa khi bạn có một **invariant nghiệp vụ cụ thể** cần được bảo vệ trong một transaction, đã xác định **đúng bản ghi cần khóa**, và không có giải pháp đồng thời đơn giản hơn thỏa cùng yêu cầu.

---

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích thế nào là database row lock và tại sao JPA có pessimistic lock modes.
2. Nhận diện race condition trong các thao tác **đọc → kiểm tra → cập nhật**.
3. Đánh giá khi nào phải khóa để bảo vệ state transition, số dư, tồn kho, quota hoặc công việc được nhiều worker tranh nhận.
4. Phân biệt **khóa ghi bi quan** với optimistic locking bằng `@Version` và atomic conditional UPDATE.
5. Dùng `EntityManager.find`, `lock` và `Query.setLockMode` đúng bối cảnh transaction.
6. Hiểu các mode `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` và `PESSIMISTIC_FORCE_INCREMENT`.
7. Nhận biết những điều khóa một row **không** bảo vệ: row chưa tồn tại, phantom inserts, invariant nhiều rows hoặc side effect bên ngoài DB.
8. Giảm lock contention bằng index, thời gian transaction ngắn, thứ tự khóa nhất quán và timeout có kiểm soát.
9. Xử lý deadlock, lock timeout, rollback/retry và kiểm thử bằng nhiều transaction thật.
10. Thiết kế phương án concurrency có chủ đích, không khóa “cho chắc” trên mọi SELECT.

---

## 2. Một bản ghi bị khóa nghĩa là gì?

Trong relational database, transaction có thể lấy lock trên một hoặc nhiều tài nguyên để phối hợp truy cập đồng thời. Khi một transaction nắm giữ khóa không tương thích với thao tác của transaction khác, giao dịch đến sau có thể:

- **Chờ** cho đến khi khóa được giải phóng.
- **Bị từ chối ngay**, nếu dùng chiến lược không chờ.
- **Timeout** sau một khoảng thời gian.
- **Bị database chọn rollback** để giải quyết deadlock.
- **Bỏ qua những bản ghi đang bị khóa**, nếu database hỗ trợ và query yêu cầu một cơ chế như `SKIP LOCKED`.

Những lựa chọn và chi tiết thực thi phụ thuộc vào database, isolation level, driver, provider và lock mode.

### 2.1. “Row lock” là cách gọi hữu ích nhưng không phải bảo đảm vật lý tuyệt đối

Khi nói “khóa bản ghi”, ta thường muốn khóa một row tương ứng với entity, chẳng hạn `InventoryItem#42`. Tuy nhiên:

- Database có thể khóa **row, key, index entry, range** hoặc tài nguyên khác.
- Optimizer và chỉ số có thể làm phạm vi khóa khác mong đợi.
- Một vài database/engine có cơ chế khóa không hoàn toàn giống nhau.
- Với association, inheritance và secondary tables, một entity có thể liên quan nhiều physical rows.
- Cơ chế lock cụ thể do database quyết định; JPA biểu diễn **ý định khóa entity**.

Không tuyên bố `PESSIMISTIC_WRITE` luôn tạo chính xác một physical row lock trên một physical table trong mọi trường hợp.

### 2.2. Khóa gắn với transaction, không gắn với Java object mãi mãi

Một transaction:

```text
BEGIN
  |
  +-- Tải InventoryItem#42 với PESSIMISTIC_WRITE
  |       |
  |       v
  |    Giữ lock phù hợp
  |
  +-- Kiểm tra số lượng
  |
  +-- Cập nhật entity
  |
  +-- COMMIT / ROLLBACK
          |
          v
     Database giải phóng lock
```

Thông thường, lock được giữ tới khi transaction hoàn tất theo semantics database. **Không có ý nghĩa** rằng entity Java đã được trả khỏi repository thì lock tự biến mất, hoặc người dùng giữ một Entity instance trong browser sẽ giữ được khóa cho đến lần lưu tiếp theo.

### 2.3. Khóa bi quan không có nghĩa chỉ một người được đọc

Tùy lock mode/database/MVCC, một giao dịch nắm write lock có thể vẫn cho phép những giao dịch khác thực hiện **đọc không khóa** và thấy phiên bản đã commit trước đó. Mục tiêu chính là ngăn những **hoạt động ghi/khóa xung đột** diễn ra song song không an toàn.

Do đó, “đã khóa row” **không đồng nghĩa** “mọi SELECT từ mọi transaction đều bị chặn”.

## 3. Vấn đề điển hình: đọc rồi cập nhật không nguyên tử

Giả sử bảng:

```sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT ck_inventory_nonnegative
      CHECK (available_quantity >= 0)
);
```

Dữ liệu:

| id | tenant_id | sku | available_quantity | reserved_quantity |
|---:|---|---|---:|---:|
| 42 | shop-a | BOOK-JPA | 5 | 0 |

Hai khách cùng đặt mua bốn quyển sách.

Không có concurrency control:

```text
Thời điểm      Transaction A                 Transaction B
------------------------------------------------------------------
T1             SELECT qty = 5
T2                                           SELECT qty = 5
T3             Kiểm tra 5 >= 4 → hợp lệ
T4                                           Kiểm tra 5 >= 4 → hợp lệ
T5             Gán qty = 1, reserved = 4
T6                                           Gán qty = 1, reserved = 4
T7             UPDATE và commit
T8                                           UPDATE và commit
------------------------------------------------------------------
Hai yêu cầu cùng được báo thành công.
Nhưng DB chỉ ghi nhận tổng cộng 4 quyển đã giữ, không phải 8.
```

Kết quả là **lost update/overselling ở cấp workflow**. Database có thể không cho số âm nhờ CHECK constraint, nhưng **CHECK không phát hiện việc hai request đã được xác nhận thành công chỉ dựa trên cùng một lượng tồn kho ban đầu**.

### 3.1. Khóa trước khi đọc và ra quyết định

Với write lock:

```text
A: BEGIN
A: SELECT item#42 FOR UPDATE   ───┐
A: đọc qty=5                     │ A giữ lock
A: reserve(4), qty=1             │
A: COMMIT                        └── giải phóng lock

B: BEGIN
B: SELECT item#42 FOR UPDATE   ... chờ A
B: đọc qty=1
B: reserve(4) -> không đủ hàng
B: ROLLBACK hoặc kết thúc không cập nhật
```

Điểm quyết định: **B chỉ kiểm tra số lượng sau khi đã lấy được khóa và nhìn thấy dữ liệu theo transaction semantics phù hợp**. Đó là cách bảo vệ một chuỗi thao tác **đọc → kiểm tra → ghi** khi tất cả writers tuân thủ cùng chiến lược.

### 3.2. Nhưng có thể không cần SELECT FOR UPDATE

Nếu nghiệp vụ chỉ là **giảm số lượng khi đủ hàng**, một câu lệnh nguyên tử có điều kiện có thể đơn giản hơn:

```sql
UPDATE inventory_item
SET
    available_quantity = available_quantity - ?,
    reserved_quantity = reserved_quantity + ?
WHERE
    id = ?
    AND tenant_id = ?
    AND available_quantity >= ?;
```

Một UPDATE như thế vẫn sử dụng locking nội bộ của database để thực hiện thao tác ghi an toàn, nhưng ứng dụng **không cần giữ khóa từ lúc SELECT tới lúc UPDATE**.

Nếu update count = 1, một row thỏa điều kiện đã được cập nhật; = 0 có thể là không đủ hàng, không tồn tại hoặc sai tenant. Nếu entity dùng `@Version` và có writers đi qua JPA, phải bổ sung chiến lược versioning nhất quán cho bulk/native DML.

**Từ đây có nguyên tắc lựa chọn:** Khóa pessimistic tường minh thường hữu ích khi cần nhiều bước quyết định/ghi dựa trên cùng snapshot; một thao tác có thể diễn tả hoàn toàn trong một atomic DML thì nên cân nhắc DML trước.

---

## 4. Bốn câu hỏi trước khi quyết định khóa

Trước khi gọi `PESSIMISTIC_WRITE`, hãy trả lời:

**Câu hỏi 1 — Invariant nào cần bảo vệ?**

Ví dụ:

- Số dư tài khoản không âm.
- Một đơn không được chuyển hai lần từ `PAID` sang `SHIPPED`.
- Chỉ một worker được nhận một job cụ thể.
- Một mã khuyến mãi chỉ được sử dụng tối đa N lần.
- Chỉ một nhân viên được sửa trạng thái khóa sổ tài chính tại một thời điểm.

Nếu không phát biểu được invariant, rất có thể khóa đang được thêm như một hành động “phòng xa” không được đo lường.

**Câu hỏi 2 — Có đọc trạng thái rồi mới quyết định ghi không?**

Một thao tác `UPDATE status='SHIPPED' WHERE status='PAID'` có thể atomic. Nhưng một workflow phải đọc tồn kho, mức ưu tiên, đơn hàng, hạn mức tín dụng và thay đổi nhiều fields có thể cần serialization phức tạp hơn.

**Câu hỏi 3 — Tranh chấp xảy ra thường xuyên đến mức nào?**

- Xung đột hiếm: `@Version` và retry/conflict handling có thể giảm thời gian chờ.
- Tranh chấp cao, mỗi lần retry rất tốn: pessimistic locking hoặc atomic update có thể hợp lý hơn.
- Hàng nghìn writers lên một row: cần xem lại data model/partitioning, không chỉ tăng lock timeout.

**Câu hỏi 4 — Có giải pháp hẹp hơn không?**

- UNIQUE/FK/CHECK constraint.
- Atomic conditional UPDATE/DELETE.
- `@Version` optimistic locking.
- SERIALIZABLE isolation có retry.
- Idempotency key.
- Queue/partition/claim mechanism.
- Database-native upsert.

Chỉ khóa khi nó bảo vệ invariant rõ hơn hoặc phù hợp hơn so với các giải pháp đó.

## 5. Những tình huống thường **nên cân nhắc** khóa

| Tình huống | Vì sao khóa có thể hữu ích | Điều kiện để đúng |
|---|---|---|
| Giữ chỗ tồn kho có nhiều bước | Tránh hai transaction cùng quyết định trên số lượng cũ | Lock trước khi kiểm tra, mọi writer tuân thủ |
| Chuyển tiền giữa tài khoản | Cần đọc số dư và cập nhật nhất quán nhiều rows | Lock tất cả rows liên quan, theo thứ tự cố định |
| Đổi trạng thái workflow quan trọng | Không cho hai request cùng chạy transition xung đột | Lock đúng aggregate/state, validate trong transaction |
| Claim một công việc trong DB queue | Giảm trùng worker nhận cùng job | Atomic claim, recheck status, recovery/lease |
| Kiểm soát hạn mức gắn với một row counter | Cần serialize quyết định cấp quota | Counter row đại diện đúng invariant |
| Đóng kỳ kế toán/quyết toán | Nhiều bước không được xen ngang trên cùng aggregate | Lock root và bảo vệ các phụ thuộc liên quan |
| Cập nhật record “nóng” thường xuyên | Retry optimistic quá nhiều | Đo contention; khóa có thể đơn giản hơn |
| Đọc bản ghi rồi gọi nhiều thay đổi DB liên quan | Cần giữ state ổn định trong transaction | Không chứa network I/O dài, scope đủ hẹp |

Bảng này **không có nghĩa mọi trường hợp trong đó bắt buộc dùng pessimistic lock**. Ví dụ tồn kho đơn giản có thể giải bằng atomic UPDATE, hạn mức đăng ký có thể giải bằng uniqueness/constraint, queue có thể dùng broker chuyên dụng.

## 6. Những trường hợp **thường không nên** khóa

| Tình huống | Vì sao chưa cần khóa tường minh |
|---|---|
| Trang danh sách sản phẩm chỉ đọc | Không có thao tác ghi dựa trên dữ liệu được đọc |
| Báo cáo/analytics | Khóa có thể tăng contention; isolation/snapshot/replica phù hợp hơn |
| Người dùng mở form rồi vài phút sau mới bấm Save | Không nên giữ transaction/lock qua thời gian tương tác người dùng |
| Hai người hiếm khi sửa cùng document | `@Version` và thông báo conflict thường phù hợp |
| INSERT một SKU duy nhất | UNIQUE constraint bảo vệ tốt hơn “SELECT trước rồi khóa row chưa tồn tại” |
| UPDATE một field bằng một predicate đủ điều kiện | Atomic conditional UPDATE có thể gọn và hiệu quả hơn |
| Read-only lookup có cache | Lock gây thêm round trip/transaction requirements |
| Gọi HTTP/payment provider trong transaction | Giữ lock qua external I/O là nguy cơ latency/timeout/deadlock |
| Một invariant trải nhiều rows nhưng chỉ khóa một row không liên quan | Khóa không bảo vệ đúng phạm vi |
| Mong ngăn transaction khác đọc dữ liệu cũ | MVCC/transaction isolation có semantics riêng; write lock không đồng nghĩa chặn mọi SELECT |

**Không có “khóa cho chắc” miễn phí.** Một lock thừa trên hot path có thể làm latency tăng mạnh khi số request tăng.

## 7. Entity ví dụ: InventoryItem

Để sử dụng các ví dụ Java, giả sử có entity:

```java
package com.example.shop.persistence;

import jakarta.persistence.*;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Column(name = "reserved_quantity", nullable = false)
    private int reservedQuantity;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public Long getVersion() {
        return version;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (availableQuantity < quantity) {
            throw new IllegalStateException(
                "Insufficient inventory"
            );
        }
        availableQuantity -= quantity;
        reservedQuantity += quantity;
    }
}
```

Tại đây:

- `@Id` biểu diễn entity identity.
- `tenantId` dùng giới hạn phạm vi dữ liệu được phép.
- `availableQuantity` và `reservedQuantity` là state nghiệp vụ.
- `@Version` là optimistic concurrency token; nó **không thay thế** pessimistic lock khi service chủ động dùng `PESSIMISTIC_WRITE`.
- `reserve` là domain method thực hiện validation và state change.

**Kết hợp `@Version` với pessimistic locking là hợp lệ.** Có một version field không khiến mọi query tự lấy pessimistic lock. Ngược lại, dùng pessimistic lock không có nghĩa phải xóa `@Version`.

## 8. JPA PESSIMISTIC_WRITE: ví dụ giữ chỗ tồn kho

Một service Spring JPA:

```java
package com.example.shop.application;

import jakarta.persistence.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserve(
            long itemId,
            String authorizedTenantId,
            int quantity
    ) {
        List<InventoryItem> found = em.createQuery(
            """
            select i
            from InventoryItem i
            where i.id = :id
              and i.tenantId = :tenant
            """,
            InventoryItem.class
        )
        .setParameter("id", itemId)
        .setParameter("tenant", authorizedTenantId)
        .setLockMode(LockModeType.PESSIMISTIC_WRITE)
        .getResultList();

        if (found.isEmpty()) {
            throw new IllegalArgumentException(
                "Inventory item not found in authorized scope"
            );
        }

        InventoryItem item = found.get(0);

        // Quyết định nghiệp vụ diễn ra SAU KHI lấy lock.
        item.reserve(quantity);

        // item vẫn managed; dirty checking đồng bộ ở flush/commit.
        // Không tự set version hay gọi merge(item).
    }
}
```

Đoạn mã là **mô hình minh họa**, cần cấu hình persistence unit, transaction manager, entity imports và domain exceptions phù hợp. `@Service` và `@Transactional` là annotation của Spring, không phải Jakarta Persistence chuẩn.

### 8.1. Vì sao query có tenantId?

Nếu làm:

```java
em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

thì đã lấy entity theo ID trước khi kiểm tra tenant. Trong hệ thống nhiều tenant, một query giới hạn tenant ngay trong WHERE có thể làm rõ **scope được phép** khi tìm và khóa. Tuy nhiên vẫn phải thiết kế security policy đúng; truyền `authorizedTenantId` từ request chưa được xác thực không đủ an toàn.

### 8.2. Vì sao kiểm tra số lượng sau khi lấy lock?

Nếu đọc `availableQuantity` trước khi khóa, một transaction khác có thể thay đổi số lượng trong khoảng giữa. Quy tắc thiết kế là:

```text
BEGIN
  -> Lấy lock đúng record
  -> Đọc trạng thái được bảo vệ
  -> Kiểm tra điều kiện nghiệp vụ
  -> Cập nhật state
  -> COMMIT hoặc ROLLBACK
```

Không đảo thành:

```text
Đọc (không khóa)
  -> Kiểm tra
  -> Lấy lock
  -> Ghi dựa trên giá trị đọc trước đó
```

nếu không có bước đọc/đánh giá lại trạng thái sau khi lấy lock.

### 8.3. Có cần flush ngay?

Không bắt buộc trong mọi use case. Managed entity được dirty-check khi transaction flush/commit. Có thể gọi `em.flush()` khi cần phát hiện lỗi DB/optimistic check ở một mốc rõ ràng, nhưng **flush không phải commit**.

### 8.4. Có cần transaction?

**Có.** Locking API bi quan đòi hỏi transaction context hợp lệ. Nếu transaction không active hoặc EntityManager không tham gia transaction đúng, provider có thể ném `TransactionRequiredException`.

### 8.5. Lock có được giải phóng khi method return?

Trong một transaction được quản lý bằng `@Transactional`, transaction manager thường commit/rollback khi method invocation kết thúc theo proxy/interceptor contract. Database giải phóng locks theo transaction completion. Không nên tách phần `getResultList()` lấy lock ra ngoài một transaction rồi tin rằng phần xử lý phía sau vẫn được bảo vệ.

---

## 9. EntityManager.find với lock mode

Với một entity có ID và không cần filter phức tạp, có thể yêu cầu khóa ngay khi tìm:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

JPA overload này kết hợp thao tác find với lock mode. Nó phù hợp khi:

- ID đã được xác định và được phép truy cập.
- Muốn khóa một entity cụ thể.
- Không cần thêm predicate tenant/soft-delete/trạng thái trong chính query.
- Transaction ghi đã được thiết lập.

### 9.1. Trả về null

Nếu entity không tồn tại theo identity, `find` trả `null` theo semantics thông thường. **Không có một existing row nào được khóa** nếu không tìm thấy entity đó. Điều này quan trọng khi tính tới kiểm tra rồi INSERT, phần sau.

### 9.2. Nếu entity đã có trong persistence context?

`EntityManager` có first-level cache/identity map. Khi entity đã managed, gọi `find(..., lockMode)` hoặc `lock(entity, lockMode)` có thể yêu cầu lock, nhưng **không nên mặc định** nó refresh tất cả persistent fields từ database.

Nếu cần đọc lại trạng thái mới dưới lock, có thể cân nhắc:

```java
em.refresh(
    item,
    LockModeType.PESSIMISTIC_WRITE
);
```

trong transaction và mapping phù hợp. `refresh` có thể ghi đè local unflushed changes; chỉ dùng khi hiểu rõ trạng thái hiện có.

### 9.3. Không xem EntityManager là thread-safe lock manager

`EntityManager` không được sử dụng đồng thời tùy ý bởi nhiều threads. Hai requests nên có persistence contexts/transactions phù hợp, còn database mới là nơi điều phối khóa giữa các tiến trình.

## 10. Query.setLockMode với JPQL/Criteria

Khi chọn entity theo điều kiện:

```java
TypedQuery<InventoryItem> query = em.createQuery(
    """
    select i
    from InventoryItem i
    where i.tenantId = :tenant
      and i.sku = :sku
    """,
    InventoryItem.class
);

query.setParameter("tenant", authorizedTenantId);
query.setParameter("sku", sku);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

InventoryItem item = query.getSingleResult();
```

Đây là **entity-result JPQL**. `setLockMode` được dùng để yêu cầu lock theo semantics JPA.

### 10.1. Không mặc định lock mode áp dụng như nhau lên mọi result shape

Đừng kỳ vọng:

```java
em.createQuery(
    "select count(i) from InventoryItem i"
).setLockMode(LockModeType.PESSIMISTIC_WRITE);
```

sẽ khóa toàn bộ các row được đếm theo cách portable. Scalar/aggregate query không có entity result owner để áp lock theo semantics tương ứng, và provider có thể từ chối lock mode hoặc SQL không có ý nghĩa mong muốn.

Với native SQL, `setLockMode` cũng không nên được coi là cách portable để ép khóa cho mọi câu SQL tùy ý. Native locking syntax/driver/provider có thể cần adapter riêng.

### 10.2. Query có nhiều JOIN

Nếu query:

```jpql
select o
from SalesOrder o
join o.customer c
where o.id = :id
```

rồi đặt `PESSIMISTIC_WRITE`, không mặc định rằng **mọi row Customer và mọi association sâu** đều đã bị khóa đủ cho mọi invariant nghiệp vụ. Phạm vi JPA lock và cách SQL lock các bảng JOIN phụ thuộc lock scope, provider và database.

Nếu cần khóa cả Order và Customer vì một invariant cụ thể, hãy xác định và lấy lock tường minh trên các entities cần bảo vệ, hoặc sử dụng database concurrency design phù hợp.

## 11. SQL thường gặp: SELECT ... FOR UPDATE

Trong nhiều relational databases, một cơ chế để lấy exclusive row lock là:

```sql
BEGIN;

SELECT
    id,
    available_quantity,
    reserved_quantity
FROM inventory_item
WHERE id = 42
FOR UPDATE;

-- Kiểm tra available_quantity.
-- Cập nhật nếu đủ hàng.

UPDATE inventory_item
SET
    available_quantity = available_quantity - 4,
    reserved_quantity = reserved_quantity + 4
WHERE id = 42;

COMMIT;
```

Đây là **SQL minh họa cho các dialect hỗ trợ `FOR UPDATE`**, không phải SQL chạy nguyên trên tất cả DB.

Ví dụ cách tiếp cận theo database:

| Database | Cách khóa thường gặp | Lưu ý |
|---|---|---|
| PostgreSQL | `SELECT ... FOR UPDATE` và các biến thể | MVCC/row locks, nhiều lock strengths |
| MySQL/InnoDB | `SELECT ... FOR UPDATE` | Index/range/next-key locking tùy isolation và query |
| Oracle Database | `SELECT ... FOR UPDATE` | Syntax và wait/nowait/skip locked riêng |
| SQL Server | Có thể dùng hints như `UPDLOCK`/`HOLDLOCK` theo mục tiêu | Không giả định syntax `FOR UPDATE` của DB khác |
| Các RDBMS khác | Cơ chế riêng | Phải đọc tài liệu phiên bản cụ thể |

**JPA `PESSIMISTIC_WRITE` biểu diễn ý định khóa**, để provider chọn cách thực thi dựa trên dialect. Nhưng tính tương thích và hiệu lực cần kiểm tra trên provider/database thực tế, nhất là khi dùng JOIN, pagination, lock scope và timeout.

### 11.1. Vì sao phải có index?

Nếu câu:

```sql
SELECT *
FROM inventory_item
WHERE sku = ?
FOR UPDATE;
```

quét quá nhiều rows vì không có index phù hợp, database có thể:

- Đọc và khóa nhiều tài nguyên hơn cần thiết.
- Giữ transaction lâu hơn.
- Tăng contention.
- Làm query chậm trước cả khi lấy được target lock.

Khi khóa theo `id` primary key, index khóa chính thường giúp tìm đúng row hiệu quả. Nếu khóa theo `tenant_id + sku`, cân nhắc composite unique/index phù hợp:

```sql
CREATE UNIQUE INDEX uq_inventory_tenant_sku
ON inventory_item(tenant_id, sku);
```

Index và uniqueness phải dựa trên schema/queries thực tế; không áp chỉ số máy móc mà không đo chi phí ghi và execution plan.

### 11.2. Không khẳng định có đúng một SQL

Provider có thể dùng một hoặc nhiều statements để lấy lock, nhất là query phức tạp, inheritance, outer join hoặc database có giới hạn cú pháp. Điều quan trọng là contract khóa JPA được thực hiện phù hợp, không phải khớp một SQL string cứng.

## 12. PESSIMISTIC_READ, PESSIMISTIC_WRITE và PESSIMISTIC_FORCE_INCREMENT

JPA định nghĩa các lock modes trong `jakarta.persistence.LockModeType`.

| Mode | Ý định chính | Tình huống |
|---|---|---|
| `PESSIMISTIC_READ` | Yêu cầu khóa bi quan tương thích với việc đọc và ngăn thay đổi xung đột theo contract | Cần đọc trạng thái ổn định trong transaction, không nhất thiết sửa row |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi bi quan, bảo vệ read-modify-write | Tồn kho, số dư, state transition |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa ghi bi quan đồng thời yêu cầu tăng version | Khi cần đánh dấu aggregate/root version thay đổi theo workflow |
| `OPTIMISTIC` | Kiểm tra phiên bản lạc quan, không phải giữ write lock dài hạn | Xung đột hiếm |
| `OPTIMISTIC_FORCE_INCREMENT` | Kiểm tra phiên bản và yêu cầu tăng version, không phải pessimistic write lock | Đánh dấu version thay đổi khi dùng chiến lược lạc quan |

### 12.1. PESSIMISTIC_READ không đồng nghĩa “không bao giờ chặn writers”

`PESSIMISTIC_READ` có thể được thực hiện bằng shared lock hoặc chiến lược đủ mạnh tùy DB/provider. Một số database/provider có thể dùng khóa mạnh hơn nếu shared lock không có tương đương thích hợp.

Không nên suy luận chính xác những thao tác nào bị chặn chỉ từ tên mode, mà không kiểm thử trên database mục tiêu.

### 12.2. Khi nào dùng PESSIMISTIC_READ?

Một transaction cần:

1. Đọc cấu hình/hạn mức từ một entity.
2. Thực hiện các thay đổi trên entity khác.
3. Muốn ngăn entity được đọc bị thay đổi trong thời gian transaction kiểm tra/gắn kết kết quả.

`PESSIMISTIC_READ` có thể là một lựa chọn nếu thực sự cần bảo vệ đối tượng đọc. Nhưng nếu invariant cần khóa ghi hoặc có khả năng nâng cấp lock, `PESSIMISTIC_WRITE` có thể phù hợp hơn.

### 12.3. Khi nào dùng PESSIMISTIC_WRITE?

Khi transaction sẽ:

- Đọc state.
- Kiểm tra điều kiện.
- Sửa **cùng row hoặc aggregate được bảo vệ**.
- Muốn tránh xung đột trước khi ra quyết định.

Ví dụ giữ chỗ tồn kho hoặc cập nhật số dư theo nhiều bước.

### 12.4. Khi nào dùng PESSIMISTIC_FORCE_INCREMENT?

Khi entity có version và transaction muốn **vừa giữ khóa ghi vừa buộc version tăng** theo lock mode:

```java
em.lock(
    order,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Tùy spec/provider và version mapping, mode này yêu cầu versioned entity. Nó hữu ích khi cần phối hợp concurrency ở aggregate root dù thay đổi trực tiếp trên root ít hoặc không có.

Không sử dụng nó để “đảm bảo mọi child entity đã khóa” hoặc mặc định version đã tăng ngay khi lệnh `lock` trả về; thời điểm increment có thể gắn với flush/commit.

## 13. Khi nào khóa vì state transition?

Giả sử một đơn hàng có trạng thái:

```text
NEW -> PAID -> PICKING -> SHIPPED
        |
        +-> REFUND_PENDING
```

Hai workflow cùng lúc:

- Worker A chuyển `PAID` → `PICKING`.
- Worker B chuyển `PAID` → `REFUND_PENDING`.

Nếu cả hai đọc `PAID` và cùng chạy business logic, hệ thống có thể vừa chuẩn bị giao hàng vừa bắt đầu hoàn tiền.

### 13.1. Dùng khóa trong transaction

```java
@Transactional
public void startPicking(long orderId, String tenantId) {
    SalesOrder order = em.createQuery(
        """
        select o
        from SalesOrder o
        where o.id = :id and o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", tenantId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();

    if (order.getStatus() != OrderStatus.PAID) {
        throw new IllegalStateException(
            "Order is not eligible for picking"
        );
    }

    order.startPicking();
}
```

Ví dụ giả định `SalesOrder` có `getStatus()`, `startPicking()` và các giá trị enum phù hợp. Đây là phần minh họa domain model, không phải bộ entity code đầy đủ.

### 13.2. Nhưng một UPDATE có điều kiện có thể đủ

```jpql
update SalesOrder o
set o.status = :picking
where o.id = :id
  and o.tenantId = :tenant
  and o.status = :paid
```

Nếu chỉ là một state transition đơn giản và không cần thêm entity-level callbacks/validation, atomic conditional UPDATE + `executeUpdate()` có thể xử lý race gọn hơn.

Nhưng bulk JPQL không tự có toàn bộ entity-level `@Version`, callbacks hoặc dirty checking; cần version strategy khi business contract yêu cầu.

### 13.3. Lúc nào khóa là hợp lý hơn?

Khi transition phải phối hợp nhiều bước trong cùng DB transaction:

- Validate nhiều fields.
- Ghi một số bảng liên quan.
- Kiểm tra quyền/điều kiện aggregate.
- Tạo outbox event.
- Cập nhật quota/counter.
- Đảm bảo không workflow khác đi qua trạng thái trung gian.

**Nếu chỉ cần một UPDATE đúng predicate, khóa trước có thể là bước thừa.**

## 14. Khi nào khóa nhiều bản ghi: chuyển tiền giữa tài khoản

Giả sử chuyển 100 đơn vị từ Account#10 sang Account#20:

1. Kiểm tra Account#10 có đủ số dư.
2. Trừ Account#10.
3. Cộng Account#20.
4. Ghi ledger/transfer record.
5. Commit tất cả cùng nhau.

Nếu hai giao dịch chuyển tiền ngược chiều hoặc cùng rút một tài khoản, cần bảo vệ tính nhất quán.

### 14.1. Khóa cả hai tài khoản

Một hướng:

```java
@Transactional
public void transfer(
        long sourceAccountId,
        long targetAccountId,
        BigDecimal amount
) {
    if (sourceAccountId == targetAccountId) {
        throw new IllegalArgumentException(
            "Source and target must differ"
        );
    }

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException(
            "Amount must be positive"
        );
    }

    long firstId = Math.min(sourceAccountId, targetAccountId);
    long secondId = Math.max(sourceAccountId, targetAccountId);

    Account first = em.find(
        Account.class,
        firstId,
        LockModeType.PESSIMISTIC_WRITE
    );

    Account second = em.find(
        Account.class,
        secondId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (first == null || second == null) {
        throw new IllegalArgumentException(
            "Account not found"
        );
    }

    Account source =
        sourceAccountId == firstId ? first : second;

    Account target =
        targetAccountId == firstId ? first : second;

    source.debit(amount);
    target.credit(amount);

    // Tạo ledger/transfer row trong cùng transaction.
}
```

`Account` ở đây là entity giả định có `debit(BigDecimal)` và `credit(BigDecimal)`. Dự án thực cần kiểm tra currency, ownership, tenant/authorization, trạng thái tài khoản, hạn mức, ledger và idempotency.

### 14.2. Vì sao khóa theo ID tăng dần?

Nếu giao dịch A khóa Account#10 rồi #20, còn B khóa #20 rồi #10, có thể tạo deadlock:

```text
A giữ lock #10 -> đợi #20
B giữ lock #20 -> đợi #10
             DEADLOCK
```

Sắp xếp IDs và luôn khóa **theo thứ tự tăng dần** giảm nguy cơ vòng chờ:

```text
A: khóa #10 -> #20
B: khóa #10 -> #20
             |
             v
B chờ ngay từ #10, không giữ #20 để chặn A
```

Đây là một biện pháp giảm deadlock rất quan trọng. Nó **không bảo đảm không có deadlock trong mọi hệ thống**, vì triggers, FK, indexes và các tài nguyên khác vẫn có thể gây vòng chờ.

### 14.3. Transaction phải bao cả hai thay đổi

Nếu trừ tiền đã commit rồi mới cộng tiền trong transaction khác, khóa không tự đảm bảo atomic transfer. Các thao tác DB liên quan phải thuộc cùng transaction phù hợp.

### 14.4. Khóa tài khoản không thay thế ledger/idempotency

Hai lần nhận cùng request transfer có thể hoàn tất tuần tự dưới lock và chuyển tiền hai lần. Cần idempotency key hoặc unique business operation ID. Lock chỉ điều phối concurrency, không tự phân biệt request mới và request retry.

## 15. Khi nào khóa một row đại diện cho quota?

Ví dụ hệ thống giới hạn số lượt đăng ký một sự kiện. Nếu quota chỉ là một thuộc tính ở row `EventCapacity`:

```text
event_id = 900
remaining_seats = 2
```

Hai request cùng muốn 2 chỗ. Lock row chứa remainingSeats, kiểm tra rồi giảm trong transaction có thể bảo vệ quyết định.

```text
BEGIN
LOCK EventCapacity#900
READ remainingSeats
IF remainingSeats >= requested:
    remainingSeats -= requested
    INSERT reservations
COMMIT
```

Điều kiện để đúng:

- Mọi writer làm thay đổi quota đi qua cùng row/quy tắc.
- Ghi reservation và giảm quota cùng transaction.
- Không có script/batch bypass quota update.
- Có unique/idempotency constraint để tránh ghi trùng request.
- Nếu còn pending payments, quota lease/expiration được thiết kế.

### 15.1. Quota đếm từ nhiều rows thì khác

Nếu quota được suy từ:

```sql
SELECT COUNT(*) FROM reservation WHERE event_id = ?;
```

rồi mới INSERT một row, việc khóa một reservation hiện có **không tự khóa được toàn bộ tập và những rows chưa tồn tại**.

Giải pháp có thể là:

- Một row counter/quota làm điểm khóa được mọi writers tuân thủ.
- Unique/constraint phù hợp với từng seat.
- SERIALIZABLE isolation và retry.
- Atomic insert/upsert/claim.
- Pessimistic lock trên một aggregate root thực sự đại diện invariant.

**Khóa đúng một row chỉ có ích nếu row đó thật sự đại diện trạng thái cần bảo vệ.**

## 16. Trường hợp “kiểm tra không tồn tại rồi tạo mới”

Một lỗi phổ biến:

```text
T1: SELECT WHERE email = 'a@example.com' -> không có
T2: SELECT WHERE email = 'a@example.com' -> không có
T1: INSERT email
T2: INSERT email
```

Nhiều người muốn “khóa row email này” trước khi INSERT. Nhưng **row chưa tồn tại thì không có row cụ thể để khóa** theo trực giác thông thường.

### 16.1. Giải pháp đúng thường là UNIQUE constraint

```sql
CREATE UNIQUE INDEX uq_customer_email
ON crm_customer(email_address);
```

Database đảm bảo không có hai rows vi phạm uniqueness theo semantics/collation đã định nghĩa. Ứng dụng xử lý unique conflict, và có thể dùng database-specific upsert hoặc transaction retry nếu nghiệp vụ yêu cầu.

### 16.2. SELECT FOR UPDATE không có match không bảo đảm khóa “khoảng trống”

Một số DB/isolation có key-range/gap locks, nhưng khác nhau rất nhiều. Không mặc định query không trả row mà dùng `FOR UPDATE` sẽ bảo vệ mọi future INSERT phù hợp predicate.

Đây là ví dụ quan trọng về **giới hạn của row locking**. Khi invariant là “một giá trị chỉ xuất hiện một lần”, UNIQUE constraint phù hợp hơn.

### 16.3. Nếu cần singleton row lock?

Đôi khi có thể khóa một **row điều phối đã tồn tại** (ví dụ một tenant settings/counter row) rồi thực hiện check/insert trong transaction. Cách này chỉ đúng nếu mọi writers tuân thủ quy tắc và phạm vi khóa đủ hẹp. Nhưng thường database UNIQUE/atomic DML vẫn là giải pháp tự nhiên hơn.

## 17. Claim công việc: nhiều workers cùng lấy job

Một bảng công việc:

```text
background_job
  id
  status: READY | RUNNING | DONE | FAILED
  scheduled_at
  lease_owner
  lease_until
```

Hai worker có thể cùng query “job READY đầu tiên”. Nếu cả hai đọc cùng row trước khi đổi status, chúng có nguy cơ xử lý trùng.

### 17.1. Chỉ SELECT job READY là chưa đủ

```jpql
select j from BackgroundJob j
where j.status = :ready
order by j.scheduledAt, j.id
```

Nếu code tiếp theo đặt `RUNNING` mà không có concurrency policy, hai transactions có thể đều dựa vào state READY cũ.

### 17.2. Khóa job rồi claim trong cùng transaction

Một hướng JPA:

```java
@Transactional
public Long claimOneJob() {
    List<BackgroundJob> jobs = em.createQuery(
        """
        select j
        from BackgroundJob j
        where j.status = :ready
        order by j.scheduledAt, j.id
        """,
        BackgroundJob.class
    )
    .setParameter("ready", JobStatus.READY)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setMaxResults(1)
    .getResultList();

    if (jobs.isEmpty()) {
        return null;
    }

    BackgroundJob job = jobs.get(0);

    if (job.getStatus() != JobStatus.READY) {
        return null;
    }

    job.markRunning();

    return job.getId();
}
```

`BackgroundJob`, `JobStatus` và methods là mô hình minh họa. Cần bổ sung owner/lease/attempts/transaction commit và khả năng recovery.

**Lưu ý quan trọng:** Query có `ORDER BY`, `setMaxResults(1)` và pessimistic lock **không được bảo đảm trên mọi database/provider sẽ hoạt động như hàng đợi tối ưu**, đặc biệt dưới contention. Có thể nhiều workers cùng chờ row đầu tiên, bị timeout hoặc trả kết quả khác khi lock được nhả.

### 17.3. SKIP LOCKED có thể giúp nhưng thường phụ thuộc DB

Database có thể hỗ trợ:

```sql
SELECT id
FROM background_job
WHERE status = 'READY'
ORDER BY scheduled_at, id
FOR UPDATE SKIP LOCKED;
```

Một worker bỏ qua row đang bị khóa để lấy row READY khác, tăng throughput. Nhưng:

- Cú pháp/hỗ trợ khác theo DB/version.
- JPA chuẩn không yêu cầu mọi provider biến `PESSIMISTIC_WRITE` thành `SKIP LOCKED`.
- Hint/provider extension có thể khác nhau.
- `SKIP LOCKED` có thể làm một số jobs bị đói tài nguyên (*starvation*).
- Cần atomic status transition và lease.
- Job xử lý bên ngoài transaction có thể chạy rất lâu.

Cô lập `SKIP LOCKED` trong adapter theo DB/provider, không coi đó là portability mặc định của JPA.

### 17.4. Không giữ DB lock khi chạy toàn bộ job dài

Một workflow tốt thường:

```text
Transaction claim rất ngắn:
  lock hoặc atomic claim
  READY -> RUNNING
  ghi lease_owner / lease_until
  COMMIT
        |
        v
Xử lý job bên ngoài transaction claim
        |
        v
Transaction hoàn tất:
  kiểm tra lease/fencing/idempotency
  RUNNING -> DONE hoặc retry/FAILED
```

Không giữ lock qua một tác vụ 20 phút gồm HTTP calls, đọc file, xử lý ảnh, gửi email. Lock không phải lease bền vững sau commit.

### 17.5. “Chỉ một worker claim” không đồng nghĩa exactly-once effects

Worker có thể claim và gọi external API thành công rồi crash trước khi đánh dấu DONE. Job sẽ được retry. Cần idempotency/fencing và workflow recovery riêng.

## 18. Khi nào chọn optimistic locking thay vì giữ lock?

JPA có `@Version`:

```java
@Version
@Column(name = "row_version")
private Long version;
```

Managed entity update có thể được provider kiểm tra bằng điều kiện ID+version tương đương:

```sql
UPDATE inventory_item
SET available_quantity = ?,
    row_version = ?
WHERE id = ?
  AND row_version = ?;
```

Nếu transaction khác đã cập nhật row, provider phát hiện stale version và có thể ném `OptimisticLockException` tại flush/commit.

### 18.1. So sánh

| Đặc điểm | Optimistic `@Version` | Pessimistic row lock |
|---|---|---|
| Thời điểm phát hiện va chạm | Thường khi flush/commit hoặc optimistic check | Khi lấy khóa/giao dịch xung đột có thể chờ |
| Tác động tới writer cạnh tranh | Không chủ động giữ write lock dài trong giai đoạn đọc | Có thể chặn/chờ hoặc timeout |
| Phù hợp | Conflict hiếm, đọc nhiều | Contention cao hoặc cần serialize quyết định |
| Tính đơn giản khi user sửa form lâu | Tốt: đọc rồi gửi expected version lúc save | Không phù hợp giữ lock suốt thời gian user sửa |
| Failure | Optimistic conflict, rollback/retry | Deadlock/timeout/lock failure, chờ đợi |
| Throughput khi conflict hiếm | Thường cao | Có thể tốn khóa không cần |
| Khi conflict cao | Nhiều retry phí công | Có thể hiệu quả hơn nhưng phải đo |
| Giới hạn | Không tự bảo vệ cross-row invariant | Khóa sai rows vẫn không bảo vệ invariant |

### 18.2. Khi người dùng đang chỉnh sửa biểu mẫu

Người dùng mở Product vào 9:00, sửa đến 9:05 rồi Save. **Không giữ DB lock năm phút**; transaction dài dễ gây contention, timeout và tài nguyên bị chiếm.

Thiết kế thường hợp lý hơn:

1. GET trả data + version.
2. Client chỉnh sửa ngoài transaction.
3. PATCH/PUT gửi expected version hoặc HTTP If-Match.
4. Transaction save kiểm tra phiên bản.
5. Nếu stale, trả conflict để user quyết định.

### 18.3. Optimistic conflict quá thường xuyên?

Nếu cùng một inventory row có hàng nghìn requests cùng cập nhật, optimistic retries có thể trở thành chi phí lớn. Khi ấy nên đo:

- Conflict rate.
- Số attempts/retry.
- Latency p95/p99.
- Lock waits/deadlocks.
- Database CPU.
- Throughput hữu ích (successful operations/s).

Sau đó so sánh với atomic UPDATE hoặc pessimistic locking; không đổi chiến lược chỉ dựa vào cảm giác.

## 19. Atomic conditional UPDATE: lựa chọn thay thế rất quan trọng

Nếu chỉ cần cập nhật một row khi đủ điều kiện:

```jpql
update InventoryItem i
set i.availableQuantity = i.availableQuantity - :quantity,
    i.reservedQuantity = i.reservedQuantity + :quantity,
    i.version = i.version + 1
where i.id = :id
  and i.tenantId = :tenant
  and i.availableQuantity >= :quantity
```

Đây là bulk JPQL update với **manual version increment** cho numeric version. Dùng:

```java
int updated = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity =
            i.availableQuantity - :quantity,
        i.reservedQuantity =
            i.reservedQuantity + :quantity,
        i.version = i.version + 1
    where i.id = :id
      and i.tenantId = :tenant
      and i.availableQuantity >= :quantity
    """
)
.setParameter("quantity", quantity)
.setParameter("id", itemId)
.setParameter("tenant", authorizedTenantId)
.executeUpdate();
```

Trước khi chạy cần validate `quantity > 0` và thực hiện trong transaction ghi phù hợp.

### 19.1. Vì sao atomic?

Câu UPDATE kiểm tra `availableQuantity >= quantity` và giảm số lượng **trong cùng statement**. Nhiều transactions cạnh tranh sẽ được database điều phối qua concurrency control của chính UPDATE; không cần hai câu SELECT→UPDATE tách rời.

### 19.2. Count = 0 không nói rõ nguyên nhân

Nếu `updated == 0`, có thể:

- Item không tồn tại.
- Item thuộc tenant khác.
- Không đủ số lượng.
- Trạng thái/ngày hiệu lực khác, nếu query có thêm predicates.

Đừng tự kết luận “không đủ hàng” rồi để lộ rằng item thuộc tenant khác nếu chưa có authorization policy rõ.

### 19.3. Bulk JPQL bỏ qua entity-level lifecycle

Cách này không tự gọi domain method `reserve`, entity callbacks hoặc version management tự động như một managed entity update. Nó cũng có thể làm first-level persistence context stale.

Khi sử dụng manual bulk DML, bạn chịu trách nhiệm cho:

- Validation.
- Version increment theo chiến lược phù hợp.
- Entity cache/context synchronization.
- Audit/outbox nếu cần.
- Những invariants không biểu diễn được trong một statement.

### 19.4. Khi nào khóa vẫn hữu ích hơn?

Nếu quyết định reserve phụ thuộc:

- Hạn mức tín dụng khách hàng.
- Trạng thái sản phẩm.
- Nhiều cấu hình phức tạp.
- Phân bổ hàng từ nhiều lô.
- Một loạt cập nhật liên quan phải đồng bộ.

lúc ấy mô hình explicit transaction + locks có thể rõ ràng và dễ bảo trì hơn một SQL phức tạp khó kiểm chứng.

## 20. Lock và transaction isolation không thay thế nhau hoàn toàn

Isolation level ảnh hưởng những gì transaction có thể quan sát và mức xen kẽ của các thao tác. Các mức thường gặp:

- READ COMMITTED.
- REPEATABLE READ.
- SERIALIZABLE.
- Các chế độ/biến thể khác theo DB.

### 20.1. READ COMMITTED và lock

Ở nhiều DB, READ COMMITTED cho phép query thứ hai trong một transaction thấy những rows mới được commit kể từ query thứ nhất. Một `SELECT ... FOR UPDATE` có thể giúp bảo vệ row được chọn khỏi concurrent writers trong transaction, nhưng không phải mọi predicate/phạm vi đều được đóng băng.

### 20.2. REPEATABLE READ không tự giải quyết mọi invariant

Một database có MVCC/snapshot-based REPEATABLE READ có thể giữ read snapshot ổn định, nhưng đó không nhất thiết ngăn hai transactions cùng chèn rows mới hoặc vi phạm invariant tổng thể.

Hành vi phụ thuộc database; không được khẳng định REPEATABLE READ giống nhau trên PostgreSQL, MySQL và SQL Server.

### 20.3. SERIALIZABLE có thể thay đổi bài toán

SERIALIZABLE nhằm ngăn một số lịch trình không thể tương đương serial execution, nhưng có thể phát hiện lỗi serialization và yêu cầu retry. Nó không có nghĩa mọi transaction tự chạy nhanh hoặc không thể fail.

Trong một số hệ thống, SERIALIZABLE + retry có thể dễ đúng hơn việc tự khóa nhiều predicates/rows phức tạp. Chi phí và semantics phải được test theo DB.

### 20.4. Khóa một row không tự khóa những rows “sẽ xuất hiện”

Các query như:

```sql
SELECT COUNT(*)
FROM reservation
WHERE event_id = 900;
```

có thể bị transaction khác chèn thêm Reservation sau khi bạn đếm. Khóa một row Reservation hiện có không mặc nhiên ngăn mọi phantom insert thỏa predicate đó.

Đây là khác biệt giữa **row conflict** và **predicate/range consistency**.

## 21. Lock duration: transaction càng dài, rủi ro càng lớn

Giả sử service:

```java
@Transactional
public void checkout(...) {
    InventoryItem item = lockInventory(...);

    paymentGateway.charge(...);  // Network call, có thể mất nhiều giây.

    item.reserve(...);
    emailClient.send(...);
}
```

Đây là một thiết kế đáng lo:

- Lock giữ qua network call.
- Nếu payment chậm, nhiều requests khác phải chờ.
- Payment có thể thành công nhưng DB transaction rollback.
- Email không thể rollback cùng DB.
- Deadlock/timeout tăng khi nhiều resources tham gia.
- Transaction giữ database connection và resources lâu.

### 21.1. Giữ phần cần khóa thật ngắn

Một phương án theo workflow:

```text
1. Validate request không cần DB lock:
   - format
   - quyền truy cập
   - thông tin đã có sẵn
2. Transaction ngắn:
   - lock/atomic reserve tồn kho
   - ghi reservation + outbox
   - commit
3. Bên ngoài transaction:
   - gọi payment/notification với idempotency
4. Transaction tiếp theo:
   - hoàn tất hoặc bù trừ reservation theo trạng thái payment
```

Mô hình này phức tạp hơn một method đơn lẻ nhưng phản ánh đúng giới hạn giữa database atomicity và external side effects.

### 21.2. “Khóa ít rows” và “khóa ngắn” đều quan trọng

Một transaction khóa một row trong 30 giây có thể gây nghẽn hơn transaction khóa 10 rows trong vài mili giây, tùy workload. Không chỉ đếm số row locks; hãy đo **thời gian giữ khóa** và số request cùng cần resource đó.

### 21.3. Không chờ người dùng khi đang giữ lock

Không dùng transaction mở sẵn qua thao tác “click xác nhận”, màn hình nhập OTP hoặc chờ quản trị viên phê duyệt. Với các workflow kéo dài, dùng state machine/optimistic tokens/leases thay vì DB lock dài hạn.

## 22. Deadlock: khi hai transaction chờ nhau

Một deadlock cơ bản:

```text
Transaction A                         Transaction B
-----------------------------------------------------
Lock Account#10                       Lock Account#20
Cần Lock Account#20                   Cần Lock Account#10
        |                                      |
        +--------------- chờ nhau -------------+
```

Database thường có cơ chế phát hiện deadlock và rollback một transaction nạn nhân. Khi dùng JPA, lỗi có thể xuất hiện dưới dạng exception provider/JPA/Spring được bọc theo môi trường.

### 22.1. Biện pháp giảm deadlock

1. Khóa các rows theo **một thứ tự nhất quán**.
2. Giữ transaction ngắn.
3. Dùng indexes để tránh truy vấn/lock quá nhiều rows.
4. Không trộn thứ tự update bảng tùy tiện giữa workflows.
5. Tránh vừa giữ lock vừa gọi external I/O.
6. Đưa phần validate không cần lock ra trước transaction khi an toàn.
7. Đặt timeout và retry policy có giới hạn.
8. Quan sát lock waits/deadlock logs theo database.

### 22.2. Deadlock vẫn có thể xảy ra dù đã sắp theo ID

Index modifications, foreign keys, triggers và nhiều statement khác trong transaction có thể tạo vòng chờ ngoài hai rows bạn nhìn thấy. Lock ordering **giảm rủi ro**, không biến deadlock thành bất khả thi.

### 22.3. Retry deadlock có giống retry optimistic conflict?

Cả hai thường yêu cầu transaction mới. Nhưng nguyên nhân, quy tắc retry và độ an toàn side effects khác nhau. Không catch mọi DB exception rồi tự động retry toàn bộ workflow, đặc biệt khi có thanh toán/email.

## 23. Lock timeout và no-wait

Nếu một transaction giữ lock quá lâu, giao dịch khác không nên chờ vô hạn theo mọi use case.

JPA có lock timeout hint:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE,
    java.util.Map.of(
        "jakarta.persistence.lock.timeout", 1500
    )
);
```

Ví dụ thể hiện yêu cầu thời gian chờ lock khoảng 1.500 milliseconds. Nhưng:

- Hỗ trợ hint có thể phụ thuộc DB/provider/driver.
- Provider có thể bỏ qua hoặc diễn giải khác nếu database không hỗ trợ.
- Không được coi đây là SLA chấm dứt query tuyệt đối đúng mili giây.
- Transaction manager hoặc JDBC statement timeout có thể tác động độc lập.
- Database có thể báo lock timeout/deadlock theo exception khác.

### 23.1. Giá trị 0: ý định không chờ

Trong các stack hỗ trợ, có thể dùng:

```java
query.setHint(
    "jakarta.persistence.lock.timeout",
    0
);
```

để yêu cầu no-wait lock acquisition. Cần **kiểm chứng trên provider/database** vì hint support không thống nhất mọi nơi.

### 23.2. Không tự fallback bằng cách bỏ khóa

Một lỗi thiết kế:

```java
try {
    return loadWithPessimisticLock();
} catch (Exception ex) {
    return loadWithoutLock();
}
```

Nếu invariant đòi lock, fallback sang đọc không khóa có thể làm mất chính sự bảo vệ bạn định thêm. Khi khóa không lấy được, hãy fail/retry/queue theo policy, không âm thầm bỏ concurrency control.

### 23.3. Timeout cần phân biệt

- **Lock wait timeout**: đợi khóa quá thời gian mong muốn.
- **Query/statement timeout**: SQL mất quá thời gian.
- **Transaction timeout**: toàn transaction quá hạn.
- **Request timeout**: HTTP/gRPC client ngừng chờ.

Chúng không đồng nghĩa và có thể xảy ra ở các lớp khác nhau.

## 24. PessimisticLockException và LockTimeoutException

JPA có các exception liên quan pessimistic lock:

```java
import jakarta.persistence.PessimisticLockException;
import jakarta.persistence.LockTimeoutException;
```

Về nguyên tắc:

- `PessimisticLockException` liên quan thất bại khóa dẫn tới rollback ở mức transaction theo contract JPA.
- `LockTimeoutException` dùng cho thất bại khóa mà chỉ statement bị rollback, không bắt buộc rollback toàn transaction theo contract tương ứng.

Tuy nhiên, cách báo từ database/provider/framework có thể có wrapper và cause chain. Trong thực tế, ứng dụng cần xem **trạng thái transaction** và exception translation trước khi quyết định tiếp tục hay retry.

### 24.1. Không tiếp tục transaction vô điều kiện

Không nên:

```java
try {
    em.lock(item, LockModeType.PESSIMISTIC_WRITE);
} catch (PessimisticLockException ex) {
    // Ignore và tiếp tục chuyển tiền.
}
```

Nếu transaction đã rollback-only hoặc invariant không còn được khóa, tiếp tục công việc sẽ không đúng. Hãy để transaction rollback và trả lỗi/retry theo policy.

### 24.2. Spring có thể dịch exception

Với Spring ORM/Spring Data, một số JPA/provider exceptions được translate sang `DataAccessException` subclasses. Không chỉ catch một class cụ thể mà bỏ qua tầng transaction manager đang dùng.

### 24.3. Không trả “không đủ hàng” khi thực chất lock timeout

Một lock timeout nói rằng thao tác **chưa lấy được khóa**; nó không chứng minh database thiếu tồn kho. Hệ thống có thể trả trạng thái tạm thời không xử lý được/retryable theo API contract, khác với từ chối nghiệp vụ do số lượng thật sự không đủ.

### 24.4. Không lạm dụng catch RuntimeException

`PersistenceException` có thể báo SQL syntax, FK, constraint, connection failure hoặc deadlock. Chỉ retry những lỗi được chính sách và trạng thái transaction cho phép.

## 25. Phạm vi khóa qua quan hệ và PessimisticLockScope

Nếu một entity có `@OneToMany`, `@ElementCollection` hoặc các quan hệ JOIN, câu hỏi là: **khóa root có khóa mọi row liên quan không?**

Không thể mặc định.

JPA có hint về pessimistic lock scope, ví dụ:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);

InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
```

`EXTENDED` biểu thị một yêu cầu mở rộng phạm vi khóa theo contract JPA cho các trường hợp phù hợp như owned join table/collection table mappings. Nhưng **nó không đồng nghĩa khóa đệ quy tất cả associated entities của cả object graph**.

### 25.1. Không tin rằng khóa Order tự khóa Customer/Lines

```text
SalesOrder (root)
  +-- Customer
  +-- OrderLine #1
  +-- OrderLine #2
```

Nếu business invariant cần bảo vệ đồng thời:

- Order status.
- Tổng số lượng ở Lines.
- Customer credit balance.

thì phải xác định **những records thực sự tham gia invariant** và thiết kế lock/atomic DML/transaction isolation tương ứng. `PESSIMISTIC_WRITE` trên SalesOrder không phải một “global object graph mutex”.

### 25.2. Khi nào cần aggregate root guard row?

Một cách thiết kế là mọi workflow chỉnh Lines đều phải lock hoặc force-increment Order root trước, giúp serialize thay đổi theo aggregate. Điều này chỉ an toàn nếu **mọi writers** tuân thủ convention và transaction bao trọn cập nhật; bản thân mapping `mappedBy` không ép mọi child writer khóa root.

### 25.3. Đừng phụ thuộc provider extension ngoài ý muốn

Một số provider có API locks cho associations, hints, follow-on locking hoặc SQL dialect-specific behavior. Nếu cần tính năng đó, cô lập trong adapter hạ tầng, ghi rõ phiên bản và test đúng target DB.

## 26. Khóa sau khi đã đọc entity có thể là quá muộn

Đây là anti-pattern:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId
);

// Đọc từ state có thể đã cũ.
int qty = item.getAvailableQuantity();

em.lock(
    item,
    LockModeType.PESSIMISTIC_WRITE
);

// Dùng qty cũ để quyết định.
if (qty >= requestedQuantity) {
    item.reserve(requestedQuantity);
}
```

Vấn đề: `qty` là giá trị đọc **trước khi lấy lock**. Một transaction khác có thể đã commit giữa hai thao tác. Ngay cả khi lock được lấy thành công, biến `qty` không tự đổi.

### 26.1. Tốt hơn: lấy lock trước rồi đọc

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);

item.reserve(requestedQuantity);
```

### 26.2. Nếu entity đã managed và có khả năng stale?

Cân nhắc `em.refresh(item, LockModeType.PESSIMISTIC_WRITE)` với transaction phù hợp, rồi mới đưa ra quyết định. Nhưng refresh có thể ghi đè local changes, nên không dùng vô điều kiện.

### 26.3. @Version không sửa mọi lựa chọn dữ liệu cũ

Nếu entity có `@Version`, một stale write có thể được phát hiện ở flush/commit, nhưng nếu bạn đã dùng state cũ để thực hiện **side effect ngoài database** trước đó, exception không thể đảo ngược side effect ấy.

Do vậy cần thiết kế transaction boundary và outbox/idempotency đúng.

## 27. Khóa một row không ngăn tất cả lost updates khi có writers khác

Giả sử service A lock InventoryItem và cập nhật. Nhưng service B dùng một hệ thống khác hoặc raw SQL:

```sql
UPDATE inventory_item
SET available_quantity = 100
WHERE id = 42;
```

Database write lock của A có thể khiến B đợi khi hai transactions xung đột về cùng row, nhưng khi A commit và B tiếp tục, B có thể ghi đè state bằng giá trị không dựa trên quyết định mới.

**Locking chỉ bảo đảm thứ tự xung đột, không bảo đảm writer B có business logic đúng.**

Để bảo vệ invariant, mọi writers phải:

- Tuân thủ transaction/concurrency policy.
- Dùng expected predicates/version khi cần.
- Không gán stale absolute values một cách mù quáng.
- Có database constraints phù hợp.
- Không bypass authorization/validation.

### 27.1. Khi thêm @Version có ích

Nếu B dùng managed entity với version stale, `@Version` có thể phát hiện conflict khi nó cố ghi. Pessimistic locking và optimistic versioning có thể bổ trợ nhau theo use case, không phải hai chế độ buộc chọn một cho toàn bộ entity.

### 27.2. Khi database CHECK có ích

`CHECK (available_quantity >= 0)` ngăn một số trạng thái sai ngay cả khi writer lỗi. Nhưng nó không bảo đảm hai giao dịch không cùng gửi notification “đã đặt thành công” hoặc tổng số lần giữ chỗ được ghi nhận đúng nếu transaction/workflow không chuẩn.

## 28. Khóa và batching: cẩn thận khi xử lý danh sách lớn

Một job chọn 50.000 rows rồi lock tất cả:

```java
List<InventoryItem> items = em.createQuery(
    "select i from InventoryItem i",
    InventoryItem.class
)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
```

có thể:

- Giữ rất nhiều locks.
- Gây nghẽn writers khác.
- Tốn persistence context memory.
- Kéo dài transaction.
- Tăng nguy cơ deadlock.
- Kích hoạt lock escalation/giới hạn DB trong một số engine.

### 28.1. Chia nhỏ transaction theo batch

Nếu nghiệp vụ cho phép, xử lý 100–500 rows mỗi transaction, commit rồi chuyển batch khác. Giới hạn kích thước batch dựa trên đo đạc thực tế, không có một con số đúng cho mọi hệ thống.

### 28.2. Dùng keyset pagination và deterministic order

Nếu job duyệt nhiều rows, có thể lấy theo ID tăng dần, không truy vấn lại cùng tập đã thay đổi một cách mơ hồ. Nhưng khi kết hợp lock và pagination/offset, cần kiểm chứng semantics của DB/provider; một `LIMIT` trên joined query và lock không tự là scheduler an toàn.

### 28.3. Không giữ entity graph quá lớn

Nếu cần chỉ IDs/status để chọn batch, một projection có thể giảm chi phí đọc. Tuy nhiên, muốn khóa entities qua JPA, cần sử dụng API/query result và lock semantics phù hợp; không mặc định đặt lock mode trên scalar query sẽ khóa rows như mong muốn.

### 28.4. Với queue, tránh xử lý tất cả trong một transaction

Claim ngắn, commit, xử lý, ack/retry ở transaction riêng thường hợp lý hơn. Điều đó giảm thời gian giữ khóa và hạn chế một worker chậm chặn toàn hàng đợi.

## 29. Có nên dùng PESSIMISTIC_READ cho báo cáo?

Thông thường, **không** nếu chỉ cần thống kê.

Một báo cáo doanh thu:

```jpql
select sum(o.totalAmount)
from SalesOrder o
where o.tenantId = :tenant
  and o.createdAt >= :start
  and o.createdAt < :end
```

không nên mặc định cố khóa mọi Order được tổng hợp chỉ để “ổn định kết quả”. Những vấn đề như consistent snapshot hoặc reconciliation cần chiến lược database isolation/snapshot/materialized views/event log riêng.

### 29.1. Report chính xác theo thời điểm

Nếu báo cáo tài chính yêu cầu snapshot không đổi, có thể cần:

- Giao dịch đọc với isolation phù hợp.
- Snapshot read/replica hoặc reporting database.
- Cutoff timestamp và trạng thái “đã khóa sổ”.
- Bảng ledger immutable/append-only.
- Quy trình finalize period có khóa hoặc state transition rõ.

**Khóa từng Order của toàn bộ kỳ không phải mặc định tốt nhất.**

### 29.2. Không nhầm “khóa sổ nghiệp vụ” với row lock

Một kỳ kế toán được đánh dấu `CLOSED` là business state lưu trong database. Một DB lock chỉ tồn tại trong transaction. Để ngăn thay đổi sau khi kỳ đã đóng, mọi writer phải kiểm tra/được ràng buộc theo **business state**, không dựa trên row lock đã được giải phóng từ hôm qua.

## 30. Khóa khi có nhiều trạng thái liên quan: phải chọn phạm vi thật rõ

Giả sử order fulfillment yêu cầu:

- Order vẫn PAID.
- InventoryItem còn hàng.
- Customer chưa bị chặn.
- ShippingCapacity còn chỗ.

Khóa chỉ Order không tự bảo vệ các rows khác. Một workflow có thể cần:

```text
Transaction:
  lock Order#123
  lock InventoryItem#42
  lock ShippingCapacity#2026-11-15
  validate all invariants
  apply changes
  write outbox
  commit
```

Nhưng càng khóa nhiều rows, càng tăng contention và nguy cơ deadlock.

### 30.1. Quy tắc chọn phạm vi

- Chỉ khóa những state **có thể bị cạnh tranh và ảnh hưởng quyết định**.
- Dùng database constraints/atomic DML cho invariant biểu diễn được bằng SQL.
- Định nghĩa thứ tự khóa nhất quán giữa workflows.
- Tách external calls khỏi transaction.
- Không khóa associations không liên quan chỉ vì được JOIN FETCH.
- Phân tích ảnh hưởng của triggers, FK và indexes.

### 30.2. Luôn thiết kế đường thất bại

Nếu khóa Order thành công nhưng khóa InventoryItem timeout:

- Transaction hiện tại có còn hợp lệ không?
- Những thay đổi nào đã pending?
- Có phải rollback không?
- Client sẽ retry hay nhận thông báo tạm thời?
- Có external side effect nào đã xảy ra trước đó không?

Thiết kế khóa đúng không chỉ là happy path mà còn là **rollback path**.

## 31. Performance: đo cả thời gian chờ và chi phí giữ khóa

Một service có thể nhanh khi chạy một request nhưng chậm khi có 100 requests đồng thời. Khóa có thể tạo **queueing effect**: mỗi request chờ request trước trên cùng row.

Ví dụ mỗi transaction giữ lock 100 ms. Nếu 50 requests cùng tranh một row, **thời gian chờ tổng thể có thể tăng mạnh** ngay cả khi CPU DB còn dư. Không thể tính chính xác chỉ từ một phép nhân vì scheduling, concurrency và DB execution thay đổi, nhưng đây là dấu hiệu hot-row contention.

### 31.1. Các chỉ số nên theo dõi

| Metric | Dùng để phát hiện |
|---|---|
| Lock wait time p50/p95/p99 | Request đang chờ khóa bao lâu |
| Lock timeout count | Bao nhiêu request không lấy được lock |
| Deadlock count | Có vòng chờ giữa transactions không |
| Transaction duration | Locks bị giữ lâu bao nhiêu |
| DB connection pool wait | Giao dịch chờ lock có chiếm connections không |
| Retry attempts | Optimistic/pessimistic retry gây tải bao nhiêu |
| Successful operations/sec | Throughput hữu ích, không chỉ requests |
| SQL execution time | Query tìm và khóa row có chậm không |
| Rows examined / execution plan | Có quét quá nhiều dữ liệu không |
| Hot keys/IDs | Có một item/account/job bị tranh chấp quá mức không |

### 31.2. Đọc database diagnostics

Các DB có những công cụ xem locks, active transactions, wait graphs, slow queries và deadlock logs. Dùng công cụ đúng theo PostgreSQL, MySQL, Oracle hoặc SQL Server và kiểm tra phiên bản. Không giả định cùng một DMV/system view trên mọi database.

### 31.3. Đo theo workload thực

Test ít nhất:

- Một request đơn lẻ.
- Nhiều requests lên **cùng ID**.
- Nhiều requests lên **các IDs khác nhau**.
- Tranh chấp hai accounts theo thứ tự ngược.
- Transaction bị delay bất thường.
- Timeout/deadlock/failure.
- Peak load gần production.

Cách này giúp phân biệt **lỗi concurrency** với **bottleneck hiệu năng**.

## 32. Lưu ý về database indexes và lock footprint

Query:

```sql
SELECT *
FROM inventory_item
WHERE tenant_id = ?
  AND sku = ?
FOR UPDATE;
```

nên có chiến lược index phù hợp nếu đây là hot path. Khi không có index:

- Database có thể scan nhiều rows.
- Lock acquisition lâu.
- Trong một số engine/isolation, phạm vi khóa vật lý có thể rộng hơn dự kiến.
- Mức contention không tương xứng với một “lookup một item”.

### 32.1. Unique index theo business key

Nếu mỗi tenant có một SKU duy nhất:

```sql
CREATE UNIQUE INDEX uq_item_tenant_sku
ON inventory_item(tenant_id, sku);
```

Unique index vừa bảo vệ uniqueness, vừa tạo lookup path hiệu quả. Nhưng cần đo ảnh hưởng tới INSERT/UPDATE và phù hợp schema.

### 32.2. Không đọc nhầm EXPLAIN là danh sách locks chính xác

Execution plan cho thấy cách DB dự kiến truy cập dữ liệu; việc liệt kê chính xác locks còn phụ thuộc engine/isolation/runtime. Khi nghi có lock contention, kết hợp plan với lock diagnostics thay vì chỉ nhìn số rows ước lượng.

## 33. Khi nào row lock không giải quyết distributed concurrency?

Trong hệ thống nhiều services, một database row lock chỉ điều phối các giao dịch **cùng hệ database và tương thích cơ chế khóa**. Nó không đồng thời khóa:

- Request ở payment provider.
- Message đang chạy trong Kafka/RabbitMQ.
- File trên object storage.
- API của nhà vận chuyển.
- Một database khác.
- Một cache Redis hoặc hệ thống search.

### 33.1. External side effects cần giao thức riêng

Một transaction giữ Order row lock không thể rollback một khoản charge đã được payment provider chấp nhận. Cần:

- Idempotency keys.
- Transactional outbox/inbox.
- State machine.
- Compensation/saga khi cần.
- Retry policies và reconciliation.

### 33.2. Row lock không tồn tại sau commit

Không thể lấy DB lock lúc gửi message, commit, rồi mong row vẫn khóa trong lúc worker nhận và xử lý message. Với công việc kéo dài, dùng lease/fencing token hoặc state claim bền vững.

### 33.3. Nhiều databases không chia sẻ row locks

Nếu Order ở database A, Inventory ở database B, khóa Order#123 không bảo vệ Inventory#42 trên B. Cross-database consistency cần distributed transaction hoặc thiết kế eventual consistency có compensation/idempotency tùy nhu cầu.

## 34. Kiểm thử concurrency với nhiều EntityManager

Kiểm thử một repository gọi `setLockMode` và không ném exception **chưa chứng minh** row lock bảo vệ invariant trong môi trường concurrent. Cần ít nhất hai transactions/persistence contexts độc lập.

### 34.1. Mục tiêu test

Fixture:

```text
InventoryItem#42
available = 5
reserved = 0
```

Hai operations đồng thời đều muốn reserve(4).

Outcome chấp nhận:

- Một operation thành công.
- Operation còn lại thất bại vì không đủ số lượng hoặc nhận lỗi retryable theo policy.
- Database cuối cùng không âm tồn kho.
- Tổng reservation được commit đúng.
- Không có hai “success” nếu chỉ đủ hàng cho một.

### 34.2. Tổ chức hai transactions

Một test kịch bản:

```text
Thread A                          Thread B
----------------------------------------------------------------
create EntityManager A           create EntityManager B
txA.begin()                      txB.begin()

A lock Item#42
A đọc quantity=5

                                 B thử lock Item#42
                                 -> chờ hoặc timeout

A reserve(4)
A commit()

                                 B lấy lock sau A (nếu còn chờ)
                                 B đọc quantity=1
                                 B reserve(4) -> insufficient
                                 B rollback/commit no-op
----------------------------------------------------------------
Verify với EntityManager C:
quantity=1; reserved=4
```

### 34.3. Pseudocode JUnit với executor

```java
ExecutorService pool =
    Executors.newFixedThreadPool(2);

CountDownLatch aHasLock =
    new CountDownLatch(1);

CountDownLatch releaseA =
    new CountDownLatch(1);

Future<?> first = pool.submit(() -> {
    EntityManager a = emf.createEntityManager();
    EntityTransaction tx = a.getTransaction();

    try {
        tx.begin();

        InventoryItem item = a.find(
            InventoryItem.class,
            42L,
            LockModeType.PESSIMISTIC_WRITE
        );

        aHasLock.countDown();

        if (!releaseA.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test gate timeout");
        }

        item.reserve(4);
        tx.commit();
    } catch (Exception ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw new RuntimeException(ex);
    } finally {
        a.close();
    }
});

Future<?> second = pool.submit(() -> {
    EntityManager b = emf.createEntityManager();
    EntityTransaction tx = b.getTransaction();

    try {
        if (!aHasLock.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("A did not lock");
        }

        tx.begin();

        InventoryItem item = b.find(
            InventoryItem.class,
            42L,
            LockModeType.PESSIMISTIC_WRITE
        );

        // Nếu không timeout, B chỉ đọc sau khi A nhả lock.
        // Kỳ vọng theo test setup: availableQuantity = 1.
        assertEquals(1, item.getAvailableQuantity());

        tx.commit();
    } catch (Exception ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw new RuntimeException(ex);
    } finally {
        b.close();
    }
});

// Cho B cơ hội tiến tới thao tác lock trong môi trường test.
// Test nghiêm ngặt cần barrier/instrumentation riêng ở DB,
// không dựa vào Thread.sleep như bằng chứng tuyệt đối.
releaseA.countDown();

first.get();
second.get();

pool.shutdown();
```

Đây là **pseudocode kiểm thử hướng dẫn**, không phải test đồng bộ hoàn chỉnh: việc `releaseA.countDown()` ngay sau submit không bảo đảm B đã thực sự chờ trên DB lock. Một integration test xác định cần additional synchronization/instrumentation, timeout có giới hạn và assertions về lock wait/serialization phù hợp target database. Đừng dùng đoạn này để khẳng định đã chứng minh B bị block trong mọi lịch trình.

### 34.4. Kiểm thử hành vi timeout/no-wait

Để kiểm tra lock timeout:

1. A lấy lock và giữ transaction.
2. B cố lấy lock với timeout ngắn/no-wait đã được cấu hình.
3. Xác nhận B không đọc/cập nhật trái phép.
4. Ghi nhận exception/cause chain của target provider.
5. Rollback/commit A đúng cách, đảm bảo test không treo.

Nếu provider bỏ qua hint, test phải phát hiện và ghi nhận thay vì âm thầm pass.

### 34.5. Kiểm thử deadlock

Với hai Accounts, cho A khóa #10 rồi #20, B khóa #20 rồi #10 để mô phỏng deadlock (mỗi worker/EntityManager độc lập), đặt timeouts để test không treo. Sau đó đổi code dùng ordering theo ID và so sánh tỷ lệ deadlock trong test workload.

### 34.6. Đọc state sau commit bằng context mới

Không dùng managed instance còn nằm trong transaction thất bại để xác minh DB cuối. Dùng EntityManager/transaction mới và assertions sau khi threads hoàn tất.

### 34.7. Không chỉ chạy test trên in-memory DB

H2 hoặc một database in-memory có thể khác production về lock modes, timeout, isolation, range locks và deadlock. Các test quan trọng nên chạy trên database/provider/version mục tiêu, chẳng hạn sử dụng Testcontainers nếu hạ tầng cho phép.

**Các ví dụ kiểm thử trong tài liệu là hướng dẫn học tập; không có test/Gradle/Content QA nào được thực thi trong bước soạn Markdown này.**

## 35. Anti-pattern: giữ lock nhưng không có ranh giới transaction

Sai:

```java
public InventoryItem getForUpdate(long id) {
    return em.find(
        InventoryItem.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
}
```

và service gọi:

```java
InventoryItem item = repository.getForUpdate(id);
// Tưởng lock vẫn tồn tại qua nhiều bước bất kỳ.
callRemoteService();
item.reserve(4);
```

Nếu `getForUpdate` không nằm trong transaction ghi chung, lock có thể thất bại ngay hoặc bị giải phóng sau một transaction ngắn. Chỉ trả Java object ra ngoài không giữ database lock.

**Giải pháp:** Đặt toàn bộ phần **lấy lock → đọc quyết định → ghi DB** trong transaction boundary rõ ràng, ngắn và có rollback policy.

## 36. Anti-pattern: khóa một row nhưng cập nhật nhiều row không được bảo vệ

Giả sử service khóa Order để quyết định có đủ quota, nhưng quota nằm ở `ShippingCapacity` row khác.

```text
lock Order#123
read ShippingCapacity#7 (không khóa)
if remaining > 0:
    insert shipping allocation
```

Hai transaction khóa **hai Orders khác nhau** nên không tranh chấp, nhưng cùng đọc `ShippingCapacity#7` và cùng cấp suất vượt quota.

Khóa Order ở đây **không bảo vệ invariant quota**. Cần khóa/atomic update trên chính resource đại diện capacity hoặc dùng constraint/isolation khác.

## 37. Anti-pattern: dùng PESSIMISTIC_WRITE cho mọi SELECT

Nếu repository tự động khóa tất cả entity reads:

```java
em.createQuery("select p from Product p", Product.class)
  .setLockMode(LockModeType.PESSIMISTIC_WRITE)
  .getResultList();
```

thì cả trang danh sách sản phẩm chỉ xem cũng tạo lock pressure. Với hàng nghìn users, có thể dẫn tới tắc nghẽn không cần thiết.

Chỉ thêm lock vào **use case cụ thể có invariant cần bảo vệ**, không vào base repository method chỉ vì muốn “chắc ăn”.

## 38. Anti-pattern: cho rằng khóa giải quyết duplicate request

Hai lần nhận cùng lệnh chuyển tiền:

```text
Request 1: chuyển 100 từ A sang B
Request 2: chuyển 100 từ A sang B (retry của request 1)
```

Nếu cả hai đi qua cùng row lock:

- Request 1 có thể hoàn tất.
- Request 2 chờ, rồi vẫn nhìn thấy số dư đủ và tiếp tục chuyển thêm 100.

Khóa bảo đảm thứ tự thực thi, không định nghĩa “cùng business operation”. Cần **idempotency key**, unique operation ID hoặc ledger state để nhận biết request lặp.

## 39. Anti-pattern: dùng timeout như bảo đảm nhất quán

Một request không lấy được lock trong 100 ms. Thay vì báo retryable error, code bỏ khóa và chạy UPDATE không có predicate.

Đó là cách phá concurrency contract. Timeout chỉ là **chính sách chờ**, không phải phép miễn kiểm tra invariant. Nếu lock cần thiết mà không lấy được, transaction phải fail/retry theo policy.

## 40. Các lỗi phổ biến khi quyết định khóa

### 40.1. Khóa trước khi xác định invariant
Không biết đang bảo vệ điều gì; có thể thêm lock thừa và tăng latency.

### 40.2. Khóa sau khi đã quyết định từ dữ liệu cũ
Giá trị được đọc trước khi lock có thể stale; phải kiểm tra dưới lock hoặc có version/atomic predicate.

### 40.3. Giữ lock qua HTTP/payment/email
Kéo dài transaction và tạo side effects không rollback được.

### 40.4. Khóa root rồi nghĩ mọi association đã an toàn
Không có bảo đảm cả graph được khóa; xác định scope rõ.

### 40.5. Khóa row không tồn tại để ngăn INSERT
Không portable; UNIQUE/atomic insert thường đúng hơn.

### 40.6. Bỏ qua concurrency của raw SQL writers
Một writer không tuân thủ business/version rules vẫn có thể ghi đè state sau khi đợi lock.

### 40.7. Dùng PESSIMISTIC_READ như PESSIMISTIC_WRITE
Lock strengths khác nhau tùy DB. Khi sẽ sửa row, chọn mode theo mục tiêu ghi.

### 40.8. Nghĩ PESSIMISTIC_WRITE chặn mọi SELECT
MVCC/read isolation có thể cho phép non-locking readers đọc snapshot cũ.

### 40.9. Query kết quả scalar + lock mode
Không giả định `COUNT`/DTO/native query tùy ý khóa rows theo JPA entity semantics.

### 40.10. Không có transaction hợp lệ
Có thể `TransactionRequiredException`, hoặc lock không sống qua business workflow.

### 40.11. Dùng một EntityManager cho nhiều threads
Không có thread-safety contract; mỗi worker/transaction cần persistence context phù hợp.

### 40.12. Đặt lock timeout nhưng không test provider
Hint có thể bị bỏ qua, khiến request chờ lâu hơn dự kiến.

### 40.13. Catch PessimisticLockException rồi tiếp tục
Transaction có thể rollback-only; invariant không còn được bảo vệ.

### 40.14. Catch mọi exception rồi coi là “không đủ hàng”
Che deadlock/timeout/SQL error thành business outcome sai.

### 40.15. Không sắp thứ tự khóa multi-row
Dễ tạo deadlock khi workflows khóa các resources ngược chiều.

### 40.16. Phân trang/ORDER BY lock query không được kiểm chứng
Query có thể bị hạn chế bởi DB/provider, hoặc nhiều workers cùng tranh row đầu tiên.

### 40.17. Dùng SKIP LOCKED như tính năng JPA chuẩn mặc định
Nó phụ thuộc DB/provider/version; phải cô lập và test.

### 40.18. Nghĩ SKIP LOCKED bảo đảm công bằng
Jobs đang khóa có thể liên tục bị bỏ qua; cần lease/retry/monitoring.

### 40.19. Giữ lock hàng triệu rows trong một batch
Có thể gây bão hòa kết nối, memory, lock escalation và timeout.

### 40.20. Không dùng index cho predicate khóa
Scan rộng có thể tăng thời gian và phạm vi khóa vật lý.

### 40.21. Dựa vào một SELECT COUNT đã khóa một row
Count trên tập rows khác có phantom/concurrency riêng; row guard phải đại diện invariant.

### 40.22. Dùng @Version thay toàn bộ pessimistic policy hoặc ngược lại
Hai cơ chế giải quyết xung đột theo cách khác; chọn đúng theo workload.

### 40.23. Nghĩ PESSIMISTIC_FORCE_INCREMENT khóa mọi child
Force increment ảnh hưởng version của entity được yêu cầu, không đệ quy bảo vệ mọi quan hệ.

### 40.24. Retry trong transaction đã bị rollback-only
Phải bắt đầu transaction/context mới và re-evaluate business state.

### 40.25. Retry toàn bộ payment workflow vô hạn
Có nguy cơ double-charge, retry storm; cần idempotency và giới hạn.

### 40.26. Chỉ đo số SQL statements
Một SELECT có lock có thể ít SQL nhưng chờ rất lâu; đo lock waits/p99 latency.

### 40.27. Test chỉ một request hoặc một EntityManager
Không chứng minh correctness dưới concurrency.

### 40.28. Chỉ test H2 rồi suy ra production locking giống nhau
Isolation và lock semantics khác giữa DB/driver/provider.

### 40.29. Khóa theo ID nhưng quên tenant
Không tự có authorization; cần scope bảo mật.

### 40.30. Xem lock như business state lâu dài
Lock mất khi transaction kết thúc; cần trạng thái bền vững như RESERVED/RUNNING/CLOSED.

---

## 41. Bảng so sánh các phương án bảo vệ dữ liệu

| Bài toán | Thường ưu tiên xem xét | Vì sao |
|---|---|---|
| Tạo customer với email duy nhất | UNIQUE constraint | Bảo vệ concurrent inserts ngay tại DB |
| Sửa một product qua form, conflict hiếm | `@Version`/If-Match | Không giữ lock qua thời gian user chỉnh sửa |
| Trừ tồn kho đơn giản khi đủ số lượng | Atomic conditional UPDATE | Một statement thực hiện check và update |
| Reserve tồn kho có nhiều bước validation/DB writes | `PESSIMISTIC_WRITE` hoặc thiết kế atomic hơn | Giữ state ổn định trong transaction |
| Chuyển tiền hai accounts | Khóa đúng các accounts theo thứ tự + transaction/ledger | Giảm race/lost update và bảo vệ atomic transfer |
| Claim nhiều jobs | Atomic claim/DB-specific SKIP LOCKED + lease | Tối ưu worker contention, recovery |
| Đếm registrations để enforce quota | Counter row/constraint/SERIALIZABLE | Khóa row ngẫu nhiên không bảo vệ predicate |
| Đọc báo cáo | Snapshot/isolation/projection | Tránh chặn writers không cần |
| Bảo đảm một external payment chỉ charge một lần | Idempotency key + workflow state | DB row lock không giữ được ở payment provider |
| Cần nhiều transactions hợp tác theo aggregate root | Root lock/version strategy | Chỉ đúng khi mọi writers tuân thủ |
| Hot counter được cập nhật rất thường xuyên | Atomic update/partitioning; đo lại | Một lock dài có thể thành bottleneck |
| Đóng kỳ kế toán | Business state + transaction/constraint | Lock chỉ tồn tại trong transaction, trạng thái CLOSED phải bền |

## 42. Bài tập thực hành có hướng dẫn

### Bài 1 — Có cần khóa khi đọc danh sách?
Một endpoint chỉ trả 20 tên sản phẩm, không ghi DB.

**Gợi ý:** Thường không cần pessimistic lock; dùng query/DTO projection và isolation đọc phù hợp.

### Bài 2 — Hai người cùng reserve tồn kho
Item còn 5, hai request muốn reserve 4.

**Gợi ý:** Cần concurrency control. Có thể dùng `PESSIMISTIC_WRITE` trước check/modify hoặc atomic conditional UPDATE.

### Bài 3 — Khóa trước hay sau?
Code đọc quantity=5 rồi mới lấy lock và quyết định reserve(4).

**Gợi ý:** Quyết định dựa trên state cũ. Lock trước và đọc lại dưới lock, hoặc dùng atomic predicate/version strategy.

### Bài 4 — Dùng EntityManager.find
Viết lệnh tìm Item#42 và yêu cầu write lock.

```java
InventoryItem item = em.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE
);
```

### Bài 5 — Dùng JPQL setLockMode
Khóa InventoryItem theo id và authorized tenant.

```java
InventoryItem item = em.createQuery(
    """
    select i from InventoryItem i
    where i.id = :id and i.tenantId = :tenant
    """,
    InventoryItem.class
)
.setParameter("id", id)
.setParameter("tenant", authorizedTenantId)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getSingleResult();
```

### Bài 6 — Transaction
Một repository method có lock nhưng phần kiểm tra/ghi xảy ra trong transaction khác.

**Gợi ý:** Không bảo đảm. Lock và thao tác ghi phải trong transaction boundary phù hợp.

### Bài 7 — Chọn mode
Cần read-modify-write một Account.

**Gợi ý:** `PESSIMISTIC_WRITE` thường rõ ý định hơn `PESSIMISTIC_READ`.

### Bài 8 — Shared vs exclusive
`PESSIMISTIC_READ` có luôn sinh một shared SQL lock giống nhau trên mọi DB?

**Đáp án:** Không. Provider có thể dùng cơ chế khác/khóa mạnh hơn theo khả năng DB.

### Bài 9 — Force increment
Muốn khóa Order root và buộc tăng phiên bản.

**Gợi ý:** `PESSIMISTIC_FORCE_INCREMENT` khi có version mapping phù hợp.

### Bài 10 — Khóa nhiều accounts
A chuyển từ #10 sang #20, B từ #20 sang #10.

**Gợi ý:** Khóa theo thứ tự ID tăng dần để giảm nguy cơ deadlock.

### Bài 11 — Deadlock
Hai giao dịch mỗi bên giữ một lock và đợi lock còn lại.

**Gợi ý:** Database có thể rollback một transaction; retry qua transaction mới, kiểm tra side effects.

### Bài 12 — UNIQUE email
Hai transactions cùng INSERT email mới giống nhau.

**Gợi ý:** UNIQUE constraint, không “khóa row chưa tồn tại” bằng một SELECT tùy ý.

### Bài 13 — Quota
Hệ thống kiểm tra `COUNT(reservation) < 100` rồi INSERT.

**Gợi ý:** Cần bảo vệ tập/quota bằng counter row, constraint hoặc isolation phù hợp; lock một reservation row không đủ.

### Bài 14 — Atomic conditional update
Viết SQL giảm tồn kho khi qty đủ.

```sql
UPDATE inventory_item
SET available_quantity = available_quantity - :q
WHERE id = :id
  AND available_quantity >= :q;
```

**Gợi ý:** Đây là ý tưởng SQL; thực tế cú pháp named params và cách bind phụ thuộc JPA/provider nếu chạy như native SQL. Dùng positional binds hoặc JPQL theo contract được hỗ trợ.

### Bài 15 — Có nên khóa trước câu UPDATE ở bài 14?
**Gợi ý:** Thường không cần explicit SELECT lock nếu một UPDATE atomic giải quyết đầy đủ invariant.

### Bài 16 — Transaction dài
Service giữ lock rồi chờ payment gateway 10 giây.

**Gợi ý:** Thiết kế lại: transaction ngắn, outbox/idempotency và workflow trạng thái.

### Bài 17 — Lock timeout
Một transaction không lấy được lock trong thời gian mong đợi.

**Gợi ý:** Báo retryable/timeout theo policy, không biến thành “hết hàng” hoặc bỏ lock.

### Bài 18 — LockTimeoutException
**Câu hỏi:** Có chắc transaction đã rollback toàn bộ?

**Gợi ý:** Phân biệt `LockTimeoutException` và `PessimisticLockException` theo JPA contract; xem trạng thái transaction/framework.

### Bài 19 — No-wait
Muốn nhận lỗi nhanh nếu row đang bị khóa.

**Gợi ý:** Có thể thử `jakarta.persistence.lock.timeout` bằng 0 trên stack hỗ trợ; phải test provider/DB.

### Bài 20 — SKIP LOCKED
Muốn nhiều worker lấy các job READY khác nhau.

**Gợi ý:** Dùng DB/provider adapter hỗ trợ SKIP LOCKED hoặc atomic claim; không mặc định đây là khả năng portable của JPA.

### Bài 21 — Job lâu
Worker cần xử lý video 20 phút.

**Gợi ý:** Không giữ DB lock suốt 20 phút; claim ngắn, lease/fencing, xử lý, ack/retry.

### Bài 22 — Exactly once
Một job được lock và claim một lần, nhưng worker crash sau khi gọi external API.

**Gợi ý:** Lock không giải quyết duplicate effects; cần idempotency/recovery.

### Bài 23 — Parent và children
Khóa SalesOrder, nhưng InventoryItem là row khác.

**Gợi ý:** Không được mặc định Inventory đã khóa. Chọn đúng resource cần bảo vệ.

### Bài 24 — First-level cache
Đã load Item cũ, rồi mới gọi `em.lock(item, PESSIMISTIC_WRITE)`.

**Gợi ý:** Lock không nhất thiết refresh object; cân nhắc `refresh(item, lockMode)` khi cần và hiểu tác động tới local changes.

### Bài 25 — MVCC
A giữ write lock Item#42. B chạy non-locking SELECT cùng Item.

**Câu hỏi:** Có luôn bị chặn?

**Đáp án:** Không; nhiều DB MVCC có thể cho đọc phiên bản đã commit.

### Bài 26 — Index
Query khóa theo tenant_id, sku nhưng không có index.

**Gợi ý:** Xem execution plan và composite index, có thể giảm scan/lock contention.

### Bài 27 — Batch 100.000 rows
Một transaction khóa và cập nhật toàn bộ.

**Gợi ý:** Cân nhắc chunking/partitioning và transaction ngắn nếu nghiệp vụ cho phép.

### Bài 28 — Kiểm thử hai EntityManager
**Yêu cầu:** Thiết kế một test A giữ PESSIMISTIC_WRITE, B cố lấy lock.

**Gợi ý:** Hai EntityManagers, hai transactions/threads, synchronization có timeout, verify DB state sau commit.

### Bài 29 — Tenant
Một account ID thuộc tenant khác; query `find(id, lockMode)` trả entity.

**Gợi ý:** Lock không thay authorization. Giới hạn tenant và kiểm tra quyền theo security policy.

### Bài 30 — Isolation
READ COMMITTED và SERIALIZABLE khác nhau thế nào với một quota/count predicate?

**Gợi ý:** SERIALIZABLE có thể phát hiện serialization anomaly và cần retry; row locking một item không tự ngăn phantom inserts.

### Bài 31 — PESSIMISTIC_FORCE_INCREMENT
**Câu hỏi:** Nó có tự khóa mọi OrderLine không?

**Gợi ý:** Không. Nó yêu cầu lock/version theo entity được chỉ định; scope graph phải được thiết kế riêng.

### Bài 32 — Retry
Một transaction timeout vì lock contention.

**Gợi ý:** Nếu retry, transaction mới, reload/re-evaluate state, giới hạn attempts; không retry external payment tùy ý.

### Bài 33 — Đọc state mới
A reserve thành công, B sau khi lấy lock vẫn dùng biến qty đọc trước khi chờ.

**Gợi ý:** Sai; B phải dựa trên state sau khi lock được lấy, qua query/refresh/context phù hợp.

### Bài 34 — Khóa có đúng phạm vi?
Hai Orders khác nhau cùng tiêu thụ một ShippingCapacity row.

**Gợi ý:** Lock Orders riêng không serialize capacity. Lock/atomic update đúng capacity resource.

### Bài 35 — Metric
Sau deploy PESSIMISTIC_WRITE, request throughput giảm nhưng số errors ít.

**Gợi ý:** Đo lock wait p95/p99, hot IDs, transaction duration, connection pool, successful operations/s; đánh giá atomic DML/optimistic alternative.

### Bài 36 — API response
Lock timeout và “không đủ hàng” có nên đều trả cùng business code?

**Gợi ý:** Không mặc định. Một bên là hạ tầng/concurrency tạm thời; một bên là business state, cần error policy riêng.

## 43. Quy trình quyết định dùng row lock

```text
                 Cần ghi dữ liệu?
                    /       \
                  Không       Có
                   |          |
                   v          v
             Đọc/snapshot   Có invariant cạnh tranh?
             phù hợp           /          \
                             Không        Có
                               |           |
                               v           v
                         Không cần lock   Atomic DML/UNIQUE/
                                         CHECK đủ không?
                                            /        \
                                          Có         Không
                                           |           |
                                           v           v
                                      Dùng DML/     Conflict hiếm?
                                      constraint      /       \
                                                    Có        Không
                                                     |           |
                                                     v           v
                                                 @Version   Cân nhắc
                                                 + retry    PESSIMISTIC_WRITE
                                                               |
                                                               v
                                                     Xác định đúng rows
                                                     và thứ tự khóa
                                                               |
                                                               v
                                                     Transaction ngắn:
                                                     lock -> validate
                                                     -> update -> commit
                                                               |
                                                               v
                                                     Test concurrency,
                                                     timeout, deadlock,
                                                     performance
```

Một checklist quyết định thực tế:

- [ ] Đã phát biểu invariant cụ thể cần bảo vệ.
- [ ] Đã xác định tất cả rows/tables có thể làm thay đổi invariant.
- [ ] Đã xem UNIQUE, FK, CHECK, atomic UPDATE/DELETE hoặc upsert.
- [ ] Đã đánh giá optimistic `@Version` và tỷ lệ conflict thực tế.
- [ ] Nếu dùng lock, lock **trước** khi quyết định dựa trên state.
- [ ] Có transaction boundary rõ và ngắn.
- [ ] Không giữ lock qua user interaction/external API.
- [ ] Có thứ tự khóa cố định khi nhiều resources.
- [ ] Có index phù hợp cho lookup khóa.
- [ ] Có policy timeout/deadlock/rollback/retry.
- [ ] Có bảo mật tenant và authorization phù hợp.
- [ ] Mọi writers quan trọng tuân thủ cùng concurrency contract.
- [ ] Có test với nhiều EntityManagers/transactions trên target database.
- [ ] Có quan sát lock waits, deadlocks, hot rows và transaction duration.
- [ ] Không dùng DB lock làm idempotency key hoặc lease dài hạn.
- [ ] Có giải pháp cho các invariants nhiều rows/phạm vi chưa tồn tại.

## 44. Tổng kết

Các nguyên tắc cần ghi nhớ:

1. **Pessimistic locking phù hợp khi một transaction phải bảo vệ quyết định đọc–kiểm tra–ghi trước concurrent writers**, đặc biệt khi nhiều bước cùng phụ thuộc một trạng thái có thể thay đổi.
2. **Không phải mọi race condition đều cần SELECT FOR UPDATE.** Atomic conditional UPDATE hoặc database constraint thường đơn giản và đủ mạnh hơn cho một số bài toán.
3. **`PESSIMISTIC_WRITE` là lựa chọn JPA rõ ràng cho read-modify-write**, trong transaction ghi và trên entity được xác định đúng.
4. **`PESSIMISTIC_READ` và `PESSIMISTIC_FORCE_INCREMENT` có mục đích khác**, không nên dùng tùy tiện chỉ vì tên giống nhau.
5. **Lấy lock trước khi dựa vào state**, không ra quyết định từ snapshot cũ rồi mới khóa.
6. **Row lock chỉ sống trong transaction**; không giữ được qua thời gian user nhập form, sau commit hoặc trên external systems.
7. **Phạm vi khóa phải đúng invariant.** Khóa Order không tự khóa Inventory hay mọi OrderLine; khóa row có sẵn không tự bảo vệ các inserts tương lai.
8. **Tránh transaction dài, có index phù hợp và khóa nhiều rows theo thứ tự ổn định** để giảm contention và deadlocks.
9. **Timeout/deadlock là failure modes cần xử lý**, không phải lý do bỏ lock hoặc ghi tiếp trong transaction rollback-only.
10. **`@Version` thường tốt hơn khi xung đột hiếm**, còn pessimistic locks có thể phù hợp khi nhiều writers tranh một resource và retry quá tốn.
11. **Việc một job được claim dưới lock không bảo đảm exactly-once side effects**; cần lease/fencing/idempotency và workflow recovery.
12. **Khóa không thay thế security, transaction isolation, UNIQUE/FK/CHECK, audit hoặc business state dài hạn**.
13. **Đánh giá locking phải có integration tests đồng thời trên DB/provider thật** và số liệu lock waits, latency, throughput dưới tải.

**Kết luận:** Cần khóa bản ghi ở cơ sở dữ liệu khi việc **cho phép hai giao dịch cùng tiến hành trên một trạng thái có thể tạo ra quyết định không hợp lệ**, và khi việc tuần tự hóa truy cập bằng khóa trong một transaction ngắn là cách rõ ràng, kiểm chứng được để bảo vệ quy tắc đó. Với JPA, `PESSIMISTIC_WRITE` cung cấp một API chuẩn để thể hiện ý định; nhưng lựa chọn đúng vẫn cần hiểu database isolation, phạm vi rows, transaction boundaries và chi phí chờ khóa. Khóa **đúng lúc, đúng bản ghi, trong thời gian ngắn**, đồng thời ưu tiên atomic DML, versioning và database constraints khi chúng giải quyết bài toán đơn giản hơn.
