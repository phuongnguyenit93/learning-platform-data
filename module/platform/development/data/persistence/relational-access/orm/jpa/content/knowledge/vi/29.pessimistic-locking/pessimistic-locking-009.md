# Kết hợp khóa bi quan với kiểm tra điều kiện nghiệp vụ trong JPA

Trong các hệ thống dùng Jakarta Persistence (JPA), một thao tác cập nhật quan trọng thường gồm nhiều bước: **đọc trạng thái hiện tại → kiểm tra một quy tắc nghiệp vụ → thay đổi dữ liệu → commit**. Khi chỉ có một request, chuỗi thao tác này trông rất đơn giản. Nhưng khi hai transaction cùng xử lý một đối tượng, chúng có thể cùng kiểm tra trên dữ liệu cũ rồi đưa ra những quyết định không còn hợp lệ.

**Khóa bi quan (pessimistic locking)** giúp điều phối những transaction có khả năng xung đột. Tuy nhiên, khóa chỉ là **cơ chế đồng bộ truy cập dữ liệu**. Nó không hiểu những quy tắc như “không được bán quá tồn kho”, “đơn đã hủy không được xuất hàng” hay “không được chuyển tiền khi số dư không đủ”.

Để có một workflow đúng, ta phải **kết hợp khóa với kiểm tra điều kiện nghiệp vụ** theo đúng trình tự:

```text
BEGIN TRANSACTION
        |
        v
Xác định đúng bản ghi cần bảo vệ
        |
        v
Lấy khóa phù hợp (thường PESSIMISTIC_WRITE)
        |
        v
Đọc trạng thái hiện hành dưới cơ chế bảo vệ
        |
        v
Kiểm tra lại toàn bộ điều kiện nghiệp vụ
        |
        +---- Không hợp lệ ---> Không cập nhật, kết thúc/rollback
        |
        v
Thay đổi state trong cùng transaction
        |
        v
Ghi các bản ghi DB liên quan (nếu có)
        |
        v
COMMIT
        |
        v
Thực hiện các bước sau commit theo workflow
```

Với JPA, ví dụ:

```java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);

if (item == null) {
    throw new ItemNotFoundException(itemId);
}

item.reserve(requestedQuantity);
```

Điểm quan trọng không phải chỉ có `PESSIMISTIC_WRITE`. Phương thức `reserve` phải kiểm tra số lượng **sau khi transaction lấy được khóa**, và toàn bộ phần kiểm tra/cập nhật phải nằm trong **cùng transaction**. Nếu một transaction khác đã xử lý trước, request tới sau cần nhìn trạng thái mới và xử lý lại cho đúng.

Bài học thuộc chương **Khóa bi quan** của module *Data Persistence Relational Access ORM JPA*. Nội dung tập trung vào việc phối hợp **pessimistic locks**, **domain validation**, **transaction boundaries**, **database constraints**, **idempotency**, **retry** và **kiểm thử concurrency** để bảo vệ nghiệp vụ thực tế.

> **Nguyên tắc trung tâm:** *Khóa đúng tài nguyên trước, đọc lại và đánh giá điều kiện trên state được bảo vệ, rồi mới thay đổi và commit*. Khóa không thay thế kiểm tra nghiệp vụ; kiểm tra nghiệp vụ bên ngoài khóa không thay thế khóa.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác vấn đề **time-of-check to time-of-use (TOCTOU)** trong các truy vấn đọc–kiểm tra–ghi.
2. Giải thích vì sao lấy `PESSIMISTIC_WRITE` phải đi cùng một lần kiểm tra điều kiện **bên trong transaction**.
3. Viết service JPA an toàn để giữ chỗ tồn kho, chuyển trạng thái đơn, kiểm soát quota và điều phối hai tài khoản.
4. Phân biệt **điều kiện có thể kiểm tra trước khóa** với **điều kiện bắt buộc kiểm tra sau khi khóa**.
5. Thiết kế rõ **phạm vi khóa** khi invariant phụ thuộc nhiều rows hoặc entity associations.
6. So sánh cách kết hợp lock+validation với `@Version`, atomic conditional UPDATE và database constraints.
7. Xử lý lock timeout, deadlock, rollback và retry mà không bỏ qua business validation.
8. Giải thích vì sao một transaction giữ khóa không đồng nghĩa external API/email/payment cũng được bảo vệ.
9. Thiết kế idempotency cho requests lặp và trạng thái nghiệp vụ bền vững sau commit.
10. Kiểm thử song song bằng hai transaction/persistence contexts và quan sát state database cuối cùng.

## 2. Khóa và điều kiện nghiệp vụ làm hai việc khác nhau

Hãy tách hai câu hỏi:

- **Khóa:** *Ai có quyền tiếp tục truy cập/thay đổi tài nguyên theo cơ chế đồng thời tại thời điểm này?*
- **Điều kiện nghiệp vụ:** *Với trạng thái hiện tại, thao tác này có được phép thực hiện không?*

Ví dụ với tồn kho:

```text
InventoryItem#42
  availableQuantity = 3
  status = ACTIVE
  version = 11
```

Một request muốn giữ chỗ năm sản phẩm. Nó có thể lấy được khóa một cách hoàn toàn hợp lệ; nhưng **không được giữ chỗ**, vì 3 < 5.

Ngược lại, request có thể kiểm tra “tồn kho = 10, đủ 5” trước khóa, nhưng một transaction khác đã mua 7 trong thời gian chờ. Khi tới lượt, điều kiện trước đó **không còn đúng**.

### 2.1. Bốn trường hợp phân biệt

| Lấy được khóa? | Điều kiện hiện tại hợp lệ? | Hành động đúng |
|---|---|---|
| Có | Có | Thực hiện cập nhật trong transaction |
| Có | Không | Từ chối nghiệp vụ, không cập nhật |
| Không, đang chờ/timeout | Chưa xác định | Xử lý lock failure; **không** suy ra “hết hàng” |
| Không tìm thấy row cần khóa | Không có target hợp lệ | Xử lý không tồn tại/không thuộc scope, theo authorization policy |

`PESSIMISTIC_WRITE` **không tự kiểm tra giá, số lượng, trạng thái, tenant, quota hay điều kiện thời gian**. Đó là trách nhiệm của code nghiệp vụ và database constraints.

### 2.2. Khóa không phải điều kiện WHERE

Câu query:

```jpql
select i
from InventoryItem i
where i.id = :id
```

với `setLockMode(PESSIMISTIC_WRITE)` có mục tiêu lấy entity và lock. Nó không tự bảo đảm:

```text
status == ACTIVE
availableQuantity >= requestedQuantity
reservedQuantity + requestedQuantity <= dailyLimit
tenantId == authorizedTenantId
```

Nếu các điều kiện đó quan trọng, phải viết trong WHERE, domain method hoặc bước validation phù hợp.

### 2.3. Điều kiện hợp lệ không đảm bảo được giữ nguyên nếu kiểm tra ngoài khóa

Một câu:

```java
if (inventory.getAvailableQuantity() >= requestedQuantity) {
    // Chưa chắc còn hợp lệ khi ghi.
}
```

chỉ có ý nghĩa tại thời điểm đọc. Nó không tự khóa database row hoặc tạo một hợp đồng atomic giữa read và write.

---

## 3. Race condition: kiểm tra trước, dùng sau

Giả sử bảng `inventory_item` có:

| id | tenant_id | status | available_quantity | reserved_quantity |
|---:|---|---|---:|---:|
| 42 | shop-a | ACTIVE | 7 | 0 |

Hai request đồng thời, mỗi request muốn giữ chỗ 5 đơn vị.

### 3.1. Workflow không có concurrency protection

```text
Thời gian      Transaction A                  Transaction B
----------------------------------------------------------------
T1             READ available = 7
T2                                            READ available = 7
T3             7 >= 5 -> hợp lệ
T4                                            7 >= 5 -> hợp lệ
T5             reserved = 5, available = 2
T6                                            reserved = 5, available = 2
T7             COMMIT
T8                                            COMMIT
----------------------------------------------------------------
Cả hai request đều nhận "đã giữ chỗ 5".
DB cuối chỉ ghi nhận 5 đã giữ, không phải 10.
```

Đây là dạng **lost update** hoặc quyết định nghiệp vụ sai vì nhiều transactions cùng dựa trên snapshot cũ. Tùy database/isolation/ORM, thứ tự thực tế có thể sinh thêm lỗi lock/optimistic conflict, nhưng rủi ro cốt lõi vẫn là việc **kiểm tra và sử dụng dữ liệu không được phối hợp đúng**.

### 3.2. Có khóa nhưng kiểm tra trước khóa: vẫn sai

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId
);

int quantityBeforeLock = item.getAvailableQuantity();

if (quantityBeforeLock < requestedQuantity) {
    throw new InsufficientStockException();
}

em.lock(item, LockModeType.PESSIMISTIC_WRITE);

// Dựa vào kết luận cũ mà không đọc/đánh giá lại.
item.reserveWithoutChecking(requestedQuantity);
```

Khóa đến **sau** quyết định. Trong khoảng đó, transaction khác có thể đã thay đổi row. Một managed entity còn có thể giữ state cũ trong persistence context.

Nếu cần lấy lock sau khi entity đã loaded, phải xác định liệu state có cần `refresh` dưới lock hay không, rồi **chạy lại business validation**. Cách rõ ràng hơn cho nhiều use case là lấy entity cùng lock ngay từ đầu.

### 3.3. Đúng thứ tự: khóa trước, kiểm tra sau

```text
Transaction A                    Transaction B
------------------------------------------------------
BEGIN                            BEGIN
LOCK Item#42
đọc available=7                  yêu cầu LOCK Item#42
                                 chờ A
kiểm tra 7 >= 5 -> đúng
reserve(5), available=2
COMMIT, release lock             nhận lock
                                 đọc available=2
                                 kiểm tra 2 >= 5 -> sai
                                 từ chối, không reserve
                                 ROLLBACK/COMMIT no-op
------------------------------------------------------
Chỉ một reservation được chấp nhận.
```

**B không dùng lại kết quả kiểm tra đã tính trước khi chờ**. Nó phải ra quyết định dựa trên trạng thái nhận được khi được phép tiếp tục dưới lock.

### 3.4. Khi nào có thể kiểm tra trước khóa?

Các điều kiện **độc lập với dữ liệu mutable được bảo vệ** có thể kiểm tra sớm để giảm thời gian giữ lock:

- `requestedQuantity > 0`.
- Định dạng request.
- Cú pháp mã sản phẩm.
- Giá trị enum có hợp lệ về kiểu hay không.
- Giới hạn kích thước payload.
- Xác thực identity/role cơ bản không phụ thuộc state DB đang thay đổi.

Nhưng phải **kiểm tra lại sau lock** các điều kiện phụ thuộc state cạnh tranh:

- `availableQuantity >= requestedQuantity`.
- `status == ACTIVE`.
- `order.status == PAID`.
- `account.balance >= amount`.
- `remainingSeats >= requestedSeats`.
- `job.status == READY`.

Với permission phụ thuộc vào trạng thái mutable trong DB, cần xác định nó có phải điều kiện phải kiểm tra lại dưới cùng concurrency strategy hay không.

## 4. Mô hình dữ liệu ví dụ

Ta xây mô hình kho hàng và reservation đơn giản.

### 4.1. Entity InventoryItem

```java
package com.example.shop.persistence;

import jakarta.persistence.*;

@Entity
@Table(
    name = "inventory_item",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_inventory_tenant_sku",
            columnNames = {"tenant_id", "sku"}
        )
    }
)
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Enumerated(EnumType.STRING)
    @Column(name = "item_status", nullable = false)
    private ItemStatus status;

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

    public String getSku() {
        return sku;
    }

    public ItemStatus getStatus() {
        return status;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public int getReservedQuantity() {
        return reservedQuantity;
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
        if (status != ItemStatus.ACTIVE) {
            throw new ItemNotAvailableException(
                "Item is not active"
            );
        }
        if (availableQuantity < quantity) {
            throw new InsufficientStockException(
                "Not enough inventory"
            );
        }

        availableQuantity -= quantity;
        reservedQuantity += quantity;
    }
}
```

Enum:

```java
public enum ItemStatus {
    ACTIVE,
    SUSPENDED,
    DISCONTINUED
}
```

Các exception `ItemNotAvailableException` và `InsufficientStockException` là **domain exceptions do dự án định nghĩa**, không phải built-in exception của JPA. Ví dụ code có thể dùng các runtime exceptions này để kích hoạt rollback theo cấu hình transaction.

### 4.2. Entity StockReservation

```java
package com.example.shop.persistence;

import jakarta.persistence.*;

@Entity
@Table(
    name = "stock_reservation",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_reservation_tenant_request",
            columnNames = {"tenant_id", "request_key"}
        )
    }
)
public class StockReservation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "request_key", nullable = false)
    private String requestKey;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "inventory_item_id", nullable = false)
    private InventoryItem item;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Enumerated(EnumType.STRING)
    @Column(name = "reservation_status", nullable = false)
    private ReservationStatus status;

    protected StockReservation() {
    }

    public static StockReservation pending(
            String tenantId,
            String requestKey,
            InventoryItem item,
            int quantity
    ) {
        StockReservation reservation =
            new StockReservation();

        reservation.tenantId = tenantId;
        reservation.requestKey = requestKey;
        reservation.item = item;
        reservation.quantity = quantity;
        reservation.status = ReservationStatus.PENDING;

        return reservation;
    }

    public Long getId() {
        return id;
    }

    public String getRequestKey() {
        return requestKey;
    }
}
```

Enum:

```java
public enum ReservationStatus {
    PENDING,
    CONFIRMED,
    RELEASED,
    EXPIRED
}
```

### 4.3. Schema minh họa

```sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(128) NOT NULL,
    item_status VARCHAR(24) NOT NULL,
    available_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT uk_inventory_tenant_sku
      UNIQUE (tenant_id, sku),
    CONSTRAINT ck_available_nonnegative
      CHECK (available_quantity >= 0),
    CONSTRAINT ck_reserved_nonnegative
      CHECK (reserved_quantity >= 0)
);

CREATE TABLE stock_reservation (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    request_key VARCHAR(128) NOT NULL,
    inventory_item_id BIGINT NOT NULL
      REFERENCES inventory_item(id),
    quantity INTEGER NOT NULL,
    reservation_status VARCHAR(24) NOT NULL,
    CONSTRAINT uk_reservation_tenant_request
      UNIQUE (tenant_id, request_key),
    CONSTRAINT ck_reservation_positive
      CHECK (quantity > 0)
);
```

DDL chỉ minh họa cấu trúc và constraints; `BIGINT PRIMARY KEY` không đồng nhất generator DDL trên mọi database với `GenerationType.IDENTITY`. Dự án thực cần migration, identity/sequence strategy và dialect phù hợp.

### 4.4. Ba lớp bảo vệ khác nhau trong ví dụ

| Lớp | Mục đích |
|---|---|
| `PESSIMISTIC_WRITE` trên InventoryItem | Tuần tự hóa những workflow tranh cùng bản ghi |
| `reserve` domain method | Xác nhận ACTIVE, quantity hợp lệ và còn đủ hàng |
| Database CHECK/UNIQUE/FK | Chặn một số trạng thái dữ liệu bất hợp lệ ngay tại DB |

Ngoài ra, `requestKey` unique giúp giới hạn duplicate reservations theo business operation. **Không lớp nào có thể thay thế hoàn toàn tất cả các lớp còn lại**.

---

## 5. Service chuẩn: khóa, kiểm tra, cập nhật và ghi reservation trong cùng transaction

Ví dụ dùng Spring để quản lý transaction:

```java
package com.example.shop.application;

import com.example.shop.persistence.*;
import jakarta.persistence.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class StockReservationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long reserveStock(
            long itemId,
            String authorizedTenantId,
            int quantity,
            String requestKey
    ) {
        // Validation không phụ thuộc state cạnh tranh.
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (requestKey == null || requestKey.isBlank()) {
            throw new IllegalArgumentException(
                "Request key is required"
            );
        }

        // Chọn đúng item được phép và lấy lock.
        List<InventoryItem> matches = em.createQuery(
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

        if (matches.isEmpty()) {
            throw new ItemNotFoundException(itemId);
        }

        InventoryItem item = matches.get(0);

        // Validation dựa trên state hiện tại, dưới lock.
        item.reserve(quantity);

        // Ghi reservation trong CHÍNH transaction.
        StockReservation reservation =
            StockReservation.pending(
                authorizedTenantId,
                requestKey,
                item,
                quantity
            );

        em.persist(reservation);

        return reservation.getId();
    }
}
```

**Lưu ý:** Với `GenerationType.IDENTITY`, ID của reservation có thể chưa sẵn có ở mọi thời điểm nếu chưa thực hiện INSERT. Tùy provider/strategy, `reservation.getId()` có thể được gán khi persist hoặc khi flush. Để làm ví dụ API độc lập provider hơn, có thể trả `void`, dùng business-generated reservation ID, hoặc lấy kết quả sau khi entity được persist/flush theo chiến lược đã kiểm chứng. Không nên coi việc có ID trước commit là bằng chứng INSERT đã commit.

Các annotation `@Service` và `@Transactional` thuộc Spring, không phải Jakarta Persistence chuẩn. Phương thức phải được gọi qua transaction boundary có hiệu lực (ví dụ Spring proxy) và sử dụng transaction manager đúng với EntityManager.

### 5.1. Điều gì đã được đảm bảo ở cấp DB transaction?

Nếu chỉ có một transaction cập nhật `InventoryItem#42` theo quy tắc này:

1. Transaction yêu cầu lock trên item.
2. Khi lock thành công, service kiểm tra số lượng/trạng thái.
3. Service cập nhật available/reserved.
4. Service tạo Reservation.
5. Commit thành công ghi các thay đổi DB cùng nhau.

Nếu INSERT reservation vi phạm unique constraint và transaction rollback, phần thay đổi tồn kho trong cùng transaction cũng phải rollback. Điều kiện này phụ thuộc transaction được cấu hình và lỗi được xử lý đúng, không commit dù đã có failure.

### 5.2. Lock không tự đảm bảo requestKey idempotency

Một request có `requestKey="R-123"` chạy hai lần liên tiếp:

- Lần một có thể reserve(3), commit.
- Lần hai cũng có thể lấy lock khi lần một đã hoàn tất.
- Nếu code reserve(3) **trước** khi thử INSERT cùng requestKey, lần hai sẽ gặp UNIQUE conflict ở INSERT và rollback toàn transaction.

Database cuối sẽ không trừ thêm nếu rollback đúng, nhưng lần hai vẫn gây lock/DB work và API cần phân biệt duplicate operation với lỗi hệ thống. **Không nên lấy constraint exception rồi tự coi tất cả tình huống là “đã xử lý thành công” mà không đối chiếu request payload**.

Một thiết kế idempotency trưởng thành hơn có thể kiểm tra requestKey sớm để trả kết quả lần đầu và **vẫn giữ unique constraint** làm hàng rào chống race; có thể cần transaction riêng để đọc lại outcome sau duplicate-key rollback.

### 5.3. Không trả dữ liệu nhạy cảm qua exception

Query theo `authorizedTenantId` chỉ nhìn thấy item trong scope. Nếu ID thuộc tenant khác, không nên tự query ngoài scope rồi trả “ID tồn tại nhưng thuộc shop-b”, trừ khi security policy cho phép.

### 5.4. Cần validate những gì trước lock?

- quantity phải dương.
- requestKey hợp lệ.
- thao tác có permission loại “reserve inventory” theo identity.
- giới hạn kích thước request.

Cần validate dưới lock:

- Item còn ACTIVE.
- availableQuantity đủ.
- hạn mức per-item còn hiệu lực.
- trạng thái nghiệp vụ chưa bị hủy/khóa.
- các invariant phụ thuộc state mutable của item.

Nếu authorization phụ thuộc **ownership/role đang lưu trong một row có thể thay đổi**, cần xác định cách bảo vệ thêm state authorization đó, không chỉ kiểm tra role cũ.

## 6. Trình tự chuẩn cho một transaction nghiệp vụ

Mẫu tư duy tổng quát:

```java
@Transactional
public Outcome execute(Command command) {

    validateCommandShape(command);

    Target target = loadWithPessimisticWriteLock(command.targetId());

    requireAuthorizedScope(target, command.actor());

    validateCurrentBusinessState(target, command);

    applyStateChange(target, command);

    persistDependentRecords(command, target);

    return buildProvisionalOutcome(target);
}
```

Các methods là tên khái niệm. `Outcome` được trả từ method body **không tự chứng nhận commit thành công** nếu framework còn thực hiện commit sau đó.

### 6.1. Bảo vệ “đọc → kiểm tra → ghi” là một khối

Không được:

```text
Transaction A:
    đọc trạng thái
    commit

Transaction B:
    lấy lock
    dùng kết luận từ transaction A
    cập nhật
    commit
```

Mặc dù transaction B có lock, nó vẫn đưa ra quyết định dựa trên state không còn được bảo đảm.

### 6.2. Không chia lock và write thành hai transaction

```text
Tx 1: SELECT ... FOR UPDATE; COMMIT;
Tx 2: UPDATE sau đó
```

Lock từ Tx 1 đã được giải phóng trước khi Tx 2 bắt đầu. Nếu cần tính atomic của business decision, giữ **lock, validation và writes** trong cùng transaction.

### 6.3. Phân biệt lỗi trước và sau khi lấy lock

- **Input invalid:** từ chối trước khi truy cập database.
- **Target không tồn tại trong scope:** không có row để thao tác.
- **Lock timeout:** không thể bảo đảm quyền tiếp tục, thường là lỗi tạm thời.
- **Business precondition false:** đã đánh giá state hiện tại và từ chối hợp lệ.
- **DB constraint error:** một invariant database bị vi phạm; transaction có thể rollback.
- **Commit error:** toàn bộ outcome DB chưa được xác nhận thành công.

Thiết kế các outcome khác nhau giúp retry an toàn và thông báo rõ ràng.

## 7. Phải kiểm tra lại khi transaction vừa chờ lock

Một timeline thực tế:

```text
Database: Order#55 status=PAID

A: BEGIN
A: khóa Order#55
A: chuyển PAID -> CANCELLED
A: COMMIT

B: đã gửi yêu cầu "ship order" từ trước khi A commit
B: BEGIN
B: cố lấy khóa Order#55, phải chờ A
B: được cấp lock sau khi A commit
B: thấy status=CANCELLED
B: KHÔNG được chuyển sang SHIPPED
```

Điểm mấu chốt: Request B có thể được nhận khi order còn PAID ở một màn hình hoặc cache, nhưng **state được phép quyết định ở thời điểm thực thi là state nằm trong transaction sau khi lấy lock**.

### 7.1. Không dùng trạng thái do client gửi làm sự thật

Client gửi:

```json
{
  "orderId": 55,
  "currentStatus": "PAID",
  "action": "SHIP"
}
```

`currentStatus` trong payload không thể thay cho `order.getStatus()` được kiểm tra trong DB transaction.

Dữ liệu client có thể hữu ích như **expected state/If-Match precondition**, nhưng server phải tự xác nhận và không tin client quyết định final current state.

### 7.2. Nếu state từ first-level cache có thể stale

Giả sử EntityManager đã load Order trước khi lấy lock. Gọi `em.lock(order, PESSIMISTIC_WRITE)` **không được mặc định là refresh toàn bộ persistent attributes**. Với workflow cần quan sát DB mới, có thể cân nhắc:

```java
em.refresh(
    order,
    LockModeType.PESSIMISTIC_WRITE
);
```

nhưng phải hiểu `refresh` có thể ghi đè các thay đổi local chưa flush. Cách sạch hơn thường là thiết kế để entity được load lần đầu **cùng với lock** trong một persistence context/transaction ngắn.

### 7.3. Isolation vẫn có ý nghĩa

Ngay cả với explicit lock, database snapshot/isolation có thể ảnh hưởng trạng thái quan sát được, deadlock/serialization failures và phạm vi predicate. Đừng giả định mọi DB trả “latest committed state” theo cùng một cách trong mọi isolation level. Test target database và chọn chiến lược transaction phù hợp.

---

## 8. Điều kiện nghiệp vụ nên nằm ở domain method

Mẫu không tốt:

```java
if (item.getAvailableQuantity() >= quantity) {
    item.setAvailableQuantity(
        item.getAvailableQuantity() - quantity
    );
}
```

Nếu một nơi khác quên kiểm tra, invariant bị vi phạm. Nếu gọi setter trực tiếp tùy ý, logic xử lý trạng thái ACTIVE và số lượng âm có thể bị bỏ sót.

Đưa quy tắc vào entity/domain method:

```java
public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Invalid quantity");
    }

    if (status != ItemStatus.ACTIVE) {
        throw new ItemNotAvailableException();
    }

    if (availableQuantity < quantity) {
        throw new InsufficientStockException();
    }

    availableQuantity -= quantity;
    reservedQuantity += quantity;
}
```

Sau đó service chịu trách nhiệm **điều phối khóa và transaction**, còn domain object chịu trách nhiệm **quy tắc thay đổi trạng thái của chính nó**.

### 8.1. Vì sao không đặt lock trong entity?

Entity thường không nên trực tiếp gọi `EntityManager` hoặc quản lý transaction:

```java
public void reserve(int quantity) {
    em.lock(this, PESSIMISTIC_WRITE); // Không nên.
}
```

Đưa persistence infrastructure vào domain entity làm trộn trách nhiệm, khiến unit tests và lifecycle khó dự đoán.

Service/repository lấy lock; entity kiểm tra invariant và thay đổi state.

### 8.2. Điều kiện phụ thuộc entity khác thì sao?

Nếu reserve phụ thuộc `Customer.creditLimit`, chỉ lock InventoryItem là chưa đủ để đảm bảo credit limit không đổi. Service phải phối hợp trạng thái của Customer hoặc resource đại diện hạn mức bằng transaction/locking/atomic strategy riêng.

Domain methods giúp local invariants rõ hơn, **không tự mở rộng lock scope**.

### 8.3. Không coi validation là side effect-free trong mọi trường hợp

Một số validation có thể đọc DB hoặc gọi external API. Nếu validation chạy chậm khi đang giữ lock, transaction bị kéo dài. Hãy phân loại:

- Pure validation: chạy nhanh trước/sau lock đều được nếu không phụ thuộc state.
- DB-dependent validation: chạy trong transaction, có scope concurrency rõ.
- External validation: cố gắng tách khỏi khoảng giữ lock, hoặc thiết kế workflow hai giai đoạn với reconciliation khi external state có thể đổi.

## 9. Có thể đặt một số điều kiện ngay trong query khóa không?

Ví dụ:

```jpql
select i
from InventoryItem i
where i.id = :id
  and i.tenantId = :tenant
  and i.status = :active
```

kèm:

```java
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
```

Cách này chỉ lấy và khóa item đang ACTIVE theo predicate truy vấn. Có thể giảm số entity không đủ điều kiện phải hydrate, nhưng cũng có một vấn đề diễn giải:

- **Không có kết quả**: item không tồn tại?
- Thuộc tenant khác?
- Đã SUSPENDED?
- Đã DISCONTINUED?
- Predicate khác không khớp?

Nếu API cần phân biệt “không tồn tại trong phạm vi” với “không đủ điều kiện”, có thể tốt hơn là query theo ID+tenant để lấy lock, **sau đó** đánh giá status trong domain.

### 9.1. Khi nào đưa điều kiện vào WHERE?

- Những điều kiện dùng để giới hạn chính xác scope và hiệu quả query.
- Tenant/authorization filtering.
- Claim tasks READY bằng một chiến lược atomic/locking đã thiết kế.
- Preconditions mà ứng dụng chấp nhận cùng một response khi không match.

### 9.2. Khi nào kiểm tra trong domain?

- Cần trả business error khác nhau.
- Nhiều điều kiện liên quan nhau.
- Quy tắc thay đổi theo trạng thái entity.
- Cần domain event/audit cho lý do từ chối.
- Cần bảo toàn logic tại nhiều điểm gọi.

### 9.3. Có thể kết hợp cả hai

Một service có thể:

1. Dùng WHERE tenant + ID để xác định scope.
2. Lock root.
3. Gọi domain method đánh giá status, availability, limit.
4. Ghi thay đổi.

Đây thường là điểm cân bằng giữa rõ ngữ nghĩa, bảo mật và kiểm soát concurrency.

## 10. Order state machine: khóa rồi kiểm tra transition

Giả sử:

```text
NEW
 |
 v
PAID -----+--------------+
 |        |              |
 v        v              v
PICKING  CANCELLED     REFUND_PENDING
 |
 v
SHIPPED
```

Chỉ các transition hợp lệ được phép. Hai workers có thể cạnh tranh cùng Order ở trạng thái PAID:

- Worker A bắt đầu PICKING.
- Worker B bắt đầu REFUND_PENDING.

### 10.1. Entity tự bảo vệ transition

```java
@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Version
    private Long version;

    protected SalesOrder() {
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void startPicking() {
        if (status != OrderStatus.PAID) {
            throw new InvalidOrderTransitionException(
                "Only PAID orders may start picking"
            );
        }

        status = OrderStatus.PICKING;
    }

    public void startRefund() {
        if (status != OrderStatus.PAID) {
            throw new InvalidOrderTransitionException(
                "Only PAID orders may start refund"
            );
        }

        status = OrderStatus.REFUND_PENDING;
    }
}
```

`InvalidOrderTransitionException` là exception miền nghiệp vụ. Các enum values và mapping khác của Order được đơn giản hóa để tập trung vào transition.

### 10.2. Service khóa trước khi gọi domain method

```java
@Transactional
public void startPicking(
        long orderId,
        String authorizedTenantId
) {
    SalesOrder order = em.createQuery(
        """
        select o
        from SalesOrder o
        where o.id = :id
          and o.tenantId = :tenant
        """,
        SalesOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenantId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();

    order.startPicking();

    // Có thể ghi audit/outbox DB record trong cùng transaction.
}
```

Từ sau khi lock được cấp, code phải kiểm tra `status == PAID` ở domain method. Worker đến sau không thể đi qua branch cũ nếu transaction trước đã commit status khác và cơ chế transaction/isolation đúng.

### 10.3. Ghi event trong transaction

Nếu cần phát sự kiện `OrderPickingStarted`, một lựa chọn bền là ghi **outbox row** trong cùng transaction sau khi transition hợp lệ:

```text
BEGIN
  lock Order
  validate transition
  update Order status
  insert OutboxEvent(ORDER_PICKING_STARTED, orderId)
COMMIT
```

Một outbox relay sẽ publish sau commit và retry. Không gửi message trực tiếp rồi giả định nếu DB rollback thì message cũng rollback.

### 10.4. Trường hợp transition đơn giản có thể dùng atomic UPDATE

Nếu việc chuyển PAID→PICKING chỉ đổi một field:

```jpql
update SalesOrder o
set o.status = :picking,
    o.version = o.version + 1
where o.id = :id
  and o.tenantId = :tenant
  and o.status = :paid
```

với numeric version, đây có thể là giải pháp gọn hơn lock + load + dirty checking. Tuy nhiên bulk JPQL không tự chạy entity callbacks/domain method/version management như entity-level update; cần tự quản lý những việc đó và diễn giải affected count đúng.

**Lựa chọn phụ thuộc yêu cầu nghiệp vụ**, không phải mục tiêu thêm càng nhiều locks càng tốt.

## 11. Transfer tiền: kiểm tra số dư dưới lock

Chuyển tiền giữa hai tài khoản đòi hỏi:

1. Nguồn và đích tồn tại/được phép.
2. Hai tài khoản cùng đơn vị tiền hoặc có quy tắc quy đổi rõ.
3. Nguồn ACTIVE.
4. Nguồn có đủ available balance.
5. Ghi debit và credit nguyên tử.
6. Có ledger để kiểm toán và request ID để chống lặp.

### 11.1. Khóa cả hai tài khoản theo một thứ tự

```java
@Transactional
public void transfer(
        long sourceId,
        long targetId,
        String authorizedTenantId,
        BigDecimal amount,
        String transferKey
) {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException(
            "Amount must be positive"
        );
    }
    if (sourceId == targetId) {
        throw new IllegalArgumentException(
            "Accounts must differ"
        );
    }

    long firstId = Math.min(sourceId, targetId);
    long secondId = Math.max(sourceId, targetId);

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
        throw new AccountNotFoundException();
    }

    Account source =
        sourceId == firstId ? first : second;

    Account target =
        targetId == firstId ? first : second;

    requireSameAuthorizedTenant(
        source, target, authorizedTenantId
    );

    source.debit(amount);
    target.credit(amount);

    // Ghi ledger/transfer record có unique transferKey
    // trong transaction này.
}
```

`Account`, `debit`, `credit` và các exception là domain types minh họa; không dùng code này làm hệ thống ngân hàng production khi chưa bổ sung đầy đủ kiểm soát bảo mật, ledger, currency, fee, fraud, idempotency và reconciliation.

### 11.2. Vì sao khóa theo ID tăng dần?

Nếu transaction A khóa Account#10 rồi chờ #20, còn B khóa #20 rồi chờ #10, cả hai có thể deadlock. Khi mọi workflows khóa theo cùng thứ tự, xác suất vòng chờ giảm.

```text
Sai thứ tự:
  A: lock #10 -> đợi #20
  B: lock #20 -> đợi #10

Đúng quy ước:
  A: lock #10 -> lock #20
  B: lock #10 -> lock #20
```

Thứ tự nhất quán **giảm** deadlock, không bảo đảm loại bỏ mọi deadlock do triggers, FK/indexes hoặc resources khác.

### 11.3. Kiểm tra quyền sau khóa có quá muộn?

Có thể kiểm tra authorization sơ bộ theo request trước khi chạm DB. Nhưng khi kiểm tra ownership/status thực tế của Account, nên bảo đảm state dùng để ra quyết định không bị thay đổi theo race condition.

Trong hệ thống đa tenant, `find(id, lockMode)` có thể load account của tenant khác trước khi check. Nếu policy yêu cầu không truy cập entity ngoài scope, dùng query có `WHERE tenantId = :authorizedTenantId` cho cả hai IDs, đồng thời giữ thứ tự khóa rõ và kiểm soát trường hợp không match.

### 11.4. Lock không tự tránh duplicate transfer

Hai lệnh cùng `transferKey` có thể chạy lần lượt. Nếu không có unique/idempotency, cả hai vẫn chuyển tiền. Cần kiểm tra operation ID và database uniqueness trong cùng business workflow.

### 11.5. Không gọi payment gateway trong lúc giữ locks

Transfer nội bộ giữa hai accounts cùng database có thể atomic trong một transaction. Gọi ngân hàng bên ngoài/payment provider là bài toán khác: DB lock không bao trùm hệ thống ngoài. Sử dụng state machine/idempotency/outbox/saga hoặc integration strategy thích hợp.

---

## 12. Quota và giới hạn số chỗ: phải khóa đúng “nguồn sự thật”

Giả sử sự kiện chỉ có 100 chỗ. Có hai mô hình dữ liệu.

### 12.1. Mô hình một row counter

```text
EventCapacity#900:
    availableSeats = 2
```

Service:

```java
@Transactional
public void reserveSeats(
        long eventId,
        int requestedSeats
) {
    EventCapacity capacity = em.find(
        EventCapacity.class,
        eventId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (capacity == null) {
        throw new EventNotFoundException();
    }

    capacity.reserve(requestedSeats);

    // persist TicketReservation(s) trong transaction này.
}
```

Domain method kiểm tra `requestedSeats > 0` và `availableSeats >= requestedSeats` dưới lock.

Vì mọi writers thao tác quota trên cùng row, lock giúp serialize những quyết định cạnh tranh.

### 12.2. Mô hình đếm nhiều row reservations

Một cách khác:

```sql
SELECT COUNT(*)
FROM ticket_reservation
WHERE event_id = 900
  AND status = 'CONFIRMED';
```

Sau đó INSERT nếu count < 100. Hai transactions có thể cùng đọc count=99 rồi cùng INSERT, dù mỗi transaction có lock trên một reservation row **khác nhau**.

Khóa một row có sẵn không mặc nhiên ngăn **future inserts** hoặc **phantoms** trong toàn bộ predicate.

Giải pháp có thể là:

- Counter row đại diện quota và được mọi writer khóa/cập nhật.
- Seat-specific unique constraint (mỗi ghế chỉ một reservation hợp lệ).
- Atomic conditional UPDATE.
- SERIALIZABLE isolation và retry.
- Một cơ chế claim/cấp phát có invariant rõ.

**Khi invariant nằm trên một tập hợp nhiều rows, phải chọn resource và loại concurrency control đúng cho toàn tập**.

### 12.3. Tại sao business validation cũng phải kiểm tra status reservation?

Một seat có thể ở trạng thái HELD, CONFIRMED, CANCELLED hoặc EXPIRED. Quy tắc “còn chỗ” phải định nghĩa những trạng thái nào chiếm quota và khi nào lease hết hạn. Lock chỉ điều phối truy cập; nó không tự định nghĩa chính sách này.

## 13. State khi nào hết hạn? Kiểm tra thời gian dưới lock

Một reservation có thể hết hạn lúc `expiresAt`. Service nhận lệnh xác nhận lúc 11:59:59, nhưng phải chờ khóa đến 12:00:02.

Nếu quy tắc là **chỉ được xác nhận khi chưa quá hạn tại thời điểm quyết định DB**, kiểm tra ở lúc client gửi yêu cầu không đủ.

```java
@Transactional
public void confirm(long reservationId, Instant now) {
    StockReservation reservation = em.find(
        StockReservation.class,
        reservationId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (reservation == null) {
        throw new ReservationNotFoundException();
    }

    reservation.confirmIfNotExpired(now);
}
```

### 13.1. Đồng hồ nào là nguồn sự thật?

Nếu quy tắc phụ thuộc chính xác timestamp, cần xác định:

- Application clock hay database clock?
- Có nhiều app instances khác timezone/clock drift không?
- `Instant.now()` được lấy trước hay sau khi chờ lock?
- Chấp nhận sai lệch thời gian tới mức nào?
- Database có cung cấp timestamp nhất quán trong transaction không?

Nếu muốn đánh giá “ngay sau khi lock được cấp”, hãy lấy **clock time phù hợp ở thời điểm đó**, không dùng timestamp được ghi trước một khoảng lock wait dài.

### 13.2. Không giữ khóa để đợi đến khi hết hạn

Không được giữ row lock suốt 15 phút “chờ khách thanh toán”. Dùng trạng thái RESERVED + `expiresAt` bền vững và scheduled expiration/reconciliation.

### 13.3. Nhiều workers expire cùng reservation

Worker expire và user confirm có thể cạnh tranh cùng row. Cả hai cần dùng cùng concurrency strategy, kiểm tra status và expiry dưới lock hoặc atomic predicates, để chỉ transition hợp lệ được commit.

## 14. Thế nào là một điều kiện nghiệp vụ “được bảo vệ”?

Một điều kiện chỉ được coi là bảo vệ tốt khi:

1. Những dữ liệu quyết định điều kiện được xác định đầy đủ.
2. Các concurrent writers có thể làm thay đổi dữ liệu đó được phối hợp theo chiến lược đã chọn.
3. Điều kiện được đánh giá ở thời điểm thích hợp trong transaction.
4. Việc ghi dựa trên điều kiện diễn ra trước transaction hoàn tất.
5. Transaction có chính sách rollback khi validation/DB operation thất bại.
6. Không có writer khác bypass chiến lược qua native SQL, batch script hoặc service khác.
7. Có database constraints bảo vệ các invariant có thể biểu diễn ở DB.

### 14.1. Khóa một row không tự bảo vệ biến bên ngoài row

Ví dụ muốn xác định đủ điểm thưởng:

```text
Customer.loyaltyTier = GOLD
Promotion.remainingUses = 1
Order.totalAmount = 300
```

Khóa Order nhưng không khóa Promotion vẫn cho phép hai Orders khác nhau cùng sử dụng lượt khuyến mãi cuối. Cần khóa hoặc atomic decrement **Promotion.remainingUses** hoặc resource bảo vệ đúng quota.

### 14.2. Khóa entity root không tự khóa children

```text
SalesOrder#55
  ├── OrderLine#1
  ├── OrderLine#2
  └── Shipment#8
```

`PESSIMISTIC_WRITE` trên Order không phải “recursive graph lock”. Nếu domain invariant còn dựa vào các Lines/Shipments có thể được writers khác sửa độc lập, phải bảo đảm chúng tham gia cùng strategy hoặc phải dùng một aggregate guard được **mọi writer** tuân thủ.

### 14.3. Bộ nhớ local không phải database lock

Synchronized block, `ReentrantLock` hoặc cache lock trong một JVM không tự điều phối instance ứng dụng khác. Nếu nhiều pods/servers cùng dùng một relational DB, khóa ở DB transaction có thể là điểm điều phối chung, nhưng chỉ bảo vệ state và writers nằm trong phạm vi cùng hệ DB.

## 15. JPA API: ba cách lấy khóa phổ biến

### 15.1. Khi find theo primary key

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Hữu ích khi ID được xác định rõ, nhưng nếu multi-tenant cần filter quyền ngay tại SELECT, có thể dùng JPQL entity query thay cho find đơn thuần.

### 15.2. Khi query có nhiều predicates

```java
List<InventoryItem> results = em.createQuery(
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

Đây là cách làm rõ target và scope. Kết quả query có thể rỗng; không mặc định rỗng nghĩa “hết hàng”.

### 15.3. Khi entity đã managed

```java
em.lock(item, LockModeType.PESSIMISTIC_WRITE);
```

Nhưng **không nên tự cho rằng state Java của entity đã được refresh**. Nếu entity được load trước khi thay đổi concurrent xảy ra, cần đánh giá tính mới của state trước khi ra quyết định.

### 15.4. Khi cần refresh dưới lock

```java
em.refresh(item, LockModeType.PESSIMISTIC_WRITE);
```

Có thể phù hợp nếu chủ động muốn nạp lại state. Cảnh báo: refresh có thể loại bỏ local changes chưa flush. Cần ranh giới rõ giữa “load để đọc fresh” và “đang sửa managed entity”.

### 15.5. Không dùng lock mode như một replacement cho transaction

Các pessimistic lock operations cần transaction hợp lệ. Một method không được chạy trong transaction đúng có thể ném `TransactionRequiredException` hoặc không có lock lifetime đáp ứng workflow.

## 16. PESSIMISTIC_WRITE, READ và FORCE_INCREMENT: chọn đúng ý định

| JPA lock mode | Mục tiêu | Phù hợp với kiểm tra nghiệp vụ nào? |
|---|---|---|
| `PESSIMISTIC_WRITE` | Lấy khóa bi quan cho transaction sẽ đọc và ghi | Inventory reserve, debit, state transition |
| `PESSIMISTIC_READ` | Yêu cầu bảo vệ đọc có khóa theo contract | Đọc trạng thái làm điều kiện của một thay đổi khác |
| `PESSIMISTIC_FORCE_INCREMENT` | Lấy khóa bi quan và yêu cầu tăng version | Quản lý aggregate root có optimistic version token |
| `OPTIMISTIC` | Kiểm tra version lạc quan, không giữ DB write lock dài | Kiểm tra state ổn định khi conflict hiếm |
| `OPTIMISTIC_FORCE_INCREMENT` | Kiểm tra version và yêu cầu tăng version | Buộc root revision tiến lên, không phải khóa ghi bi quan |

### 16.1. Tại sao PESSIMISTIC_WRITE thường rõ nhất khi sửa cùng row?

Workflow reserve thay đổi chính InventoryItem, nên ý định là read-modify-write. `PESSIMISTIC_WRITE` thể hiện rõ việc cần ngăn những ghi cạnh tranh không được phép xen vào.

`PESSIMISTIC_READ` có thể dùng shared/read lock theo DB/provider, nhưng không nên mặc định nó có cùng tác động với write lock. Nếu transaction sẽ cập nhật row, chọn mode được thiết kế cho ghi.

### 16.2. Có nên FORCE_INCREMENT khi entity có @Version?

`PESSIMISTIC_WRITE` không có nghĩa luôn force-increment version nếu không có persistent state change. `PESSIMISTIC_FORCE_INCREMENT` được dùng khi workflow cần **yêu cầu tăng version** của versioned entity.

Ví dụ một parent Order cần ghi dấu optimistic revision khi thay đổi child. Nhưng force increment root không tự khóa hoặc version-check mọi child nếu các writers khác bỏ qua aggregate discipline.

### 16.3. Không dùng FORCE_INCREMENT để “nhận quyền sở hữu mãi mãi”

Version là concurrency token; một transaction khác có thể tiếp tục sau khi transaction hiện tại commit theo policy mới. Nó không thay lease/lock bền vững sau commit.

## 17. Transaction boundary là điều kiện bắt buộc

Một service chỉ đúng khi lock, validation và mutation thuộc cùng transaction.

Ví dụ resource-local JPA:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (item == null) {
        throw new ItemNotFoundException(itemId);
    }

    item.reserve(requestedQuantity);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đây là mẫu **resource-local transaction**. Với JTA/container-managed EntityManager hoặc Spring `@Transactional`, transaction lifecycle được transaction manager điều phối; không được trộn `em.getTransaction()` vào môi trường mà EntityManager do JTA quản lý.

### 17.1. Spring self-invocation

Với Spring proxy-based transactions, nếu method `@Transactional` được gọi từ một method khác **trong chính class** qua `this.`, transaction advice có thể không chạy.

```java
public void handle(Command command) {
    this.reserveWithLock(command); // Có thể bypass Spring proxy.
}

@Transactional
public void reserveWithLock(Command command) {
    // ...
}
```

Không tin rằng chỉ có annotation thì chắc chắn transaction đã active. Đặt transaction boundary tại public service method được gọi qua proxy hoặc dùng TransactionTemplate/AOP strategy đã xác định.

### 17.2. Rollback khi domain validation fail

Nếu domain method ném unchecked exception và Spring dùng rollback rules mặc định, transaction thường rollback. Với checked exceptions hoặc configuration tùy chỉnh, cần xác nhận rollback policy.

Nếu service catch lỗi nghiệp vụ rồi tiếp tục commit, hãy chắc rằng **không có mutation nào đã xảy ra trước exception** hoặc transaction đã được reset phù hợp. Không để trạng thái cập nhật dở được commit vì đã che mất exception.

### 17.3. Kết quả từ method không phải commit cuối cùng

Một Spring `@Transactional` method có thể return khỏi body, sau đó interceptor mới commit. Commit có thể thất bại vì constraint/deadlock/connection issue. Caller chỉ nên coi operation hoàn tất khi transaction manager thực sự thông báo thành công.

### 17.4. Flush không phải commit

`em.flush()` có thể phát hiện SQL/constraint/optimistic conflict sớm, nhưng transaction còn có thể rollback. Không gửi email/charge payment ngay sau flush rồi nghĩ đã chắc chắn commit.

---

## 18. Tối ưu: kiểm tra điều kiện nào trước, trong và sau transaction?

Một request có nhiều điều kiện:

| Điều kiện | Giai đoạn thường phù hợp | Vì sao |
|---|---|---|
| `quantity > 0` | Trước transaction/lock | Không phụ thuộc state thay đổi |
| Request key có định dạng hợp lệ | Trước lock | Tránh chiếm DB lock cho input lỗi |
| Xác thực người dùng | Trước lock | Không cần chờ khóa để biết identity |
| Item thuộc tenant được phép | Trong scoped query hoặc dưới lock | Từ database/security scope đáng tin |
| Item ACTIVE | Sau lock | Trạng thái mutable |
| availableQuantity đủ | Sau lock | Giá trị cạnh tranh cao |
| Order chưa CANCELLED | Sau lock | State transition mutable |
| Quota còn đủ | Sau lock trên quota resource, hoặc atomic predicate | Cần đúng nguồn sự thật |
| Foreign key/uniqueness | Database constraint | Bảo vệ ngay khi ghi trong DB |
| External payment success | Ngoài DB transaction dài, workflow state | Không thể khóa remote system bằng row lock |
| Gửi notification | Sau commit/outbox relay | Tránh side effect của transaction rollback |

### 18.1. Đừng cố chuyển mọi kiểm tra ra trước để giảm lock duration

Giảm thời gian giữ lock là tốt, nhưng nếu chuyển một validation phụ thuộc state ra trước lock, correctness có thể mất.

### 18.2. Có thể kiểm tra “sớm” để trả lỗi nhanh nhưng vẫn kiểm tra lại

Ví dụ service đọc cache thấy item DISCONTINUED, có thể trả lỗi sớm nếu business policy chấp nhận. Nhưng nếu cache hiện ACTIVE và request tiếp tục, **validation thật** vẫn phải xảy ra trong transaction dưới concurrency control phù hợp.

### 18.3. Authorization có thể cần kiểm tra hai lần

Nếu quyền người dùng phụ thuộc vào thông tin mutable (ví dụ Account bị FROZEN), việc authenticated user có vai trò giao dịch không có nghĩa account vẫn cho phép debit khi transaction lấy lock. Khi đó:

- Xác thực user trước.
- Kiểm tra quyền hành động cơ bản.
- Lấy lock đúng Account.
- Kiểm tra trạng thái FROZEN và ownership theo DB policy.
- Chỉ sau đó mới mutate.

---

## 19. Kết hợp khóa với @Version: có mâu thuẫn không?

**Không.** Có thể giữ `@Version` trên entity và dùng `PESSIMISTIC_WRITE` cho use case đặc biệt.

```java
@Version
@Column(name = "row_version")
private Long version;
```

Khi service sửa entity managed, provider vẫn có thể dùng cơ chế versioning cho cập nhật. Pessimistic lock giúp serialize access trong transaction hiện tại; versioning còn hữu ích cho những workflows dùng optimistic locking hoặc detached forms.

### 19.1. Hai chiến lược phục vụ hai thời điểm

- **Optimistic locking:** nhiều transactions được đọc cùng state, xung đột phát hiện khi ghi/check version.
- **Pessimistic locking:** transaction yêu cầu một lock trước khi quyết định/giai đoạn ghi, các giao dịch xung đột có thể chờ.

Nếu nghiệp vụ phải giữ xung đột tới commit và conflict hiếm, `@Version` thường đủ. Nếu retry rất đắt hoặc phải serialize nhiều quyết định DB cùng một resource, pessimistic lock có thể phù hợp.

### 19.2. Khi client gửi expectedVersion, vẫn có thể kiểm tra dưới lock

```java
if (!Objects.equals(
        item.getVersion(),
        request.expectedVersion())) {
    throw new StaleRequestException();
}
```

Dưới lock, điều này có thể giúp phân biệt client đang dựa trên một bản cũ ngay cả khi item vẫn đủ số lượng.

Tuy nhiên, khi use case là **reserve(2) trên stock mới**, business contract có thể cho phép xử lý theo state mới mà không cần client version cố định. Không bắt client gửi version nếu nó không phù hợp semantics.

### 19.3. Khóa không thay authorization/idempotency

Version và lock giải quyết concurrency trong DB, không định nghĩa ai được phép sử dụng item, cũng không nhận biết hai HTTP requests có cùng idempotency key.

## 20. Atomic UPDATE hay lock + domain validation?

Nếu logic đơn giản:

```java
if (item.getAvailableQuantity() >= q) {
    item.setAvailableQuantity(item.getAvailableQuantity() - q);
}
```

thì atomic conditional UPDATE có thể tốt hơn:

```jpql
update InventoryItem i
set i.availableQuantity = i.availableQuantity - :q,
    i.reservedQuantity = i.reservedQuantity + :q,
    i.version = i.version + 1
where i.id = :id
  and i.tenantId = :tenant
  and i.status = :active
  and i.availableQuantity >= :q
```

Thực thi trong transaction:

```java
int affected = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = i.availableQuantity - :q,
        i.reservedQuantity = i.reservedQuantity + :q,
        i.version = i.version + 1
    where i.id = :id
      and i.tenantId = :tenant
      and i.status = :active
      and i.availableQuantity >= :q
    """
)
.setParameter("q", quantity)
.setParameter("id", itemId)
.setParameter("tenant", authorizedTenantId)
.setParameter("active", ItemStatus.ACTIVE)
.executeUpdate();
```

Với numeric `@Version`, câu trên **tự biểu diễn** phép tăng version cho bulk DML; JPQL bulk update không tự triển khai entity-level versioning.

### 20.1. Ưu điểm của atomic UPDATE

- Một câu DML chứa check+mutation.
- Không cần load entity.
- Database xử lý predicate và update atomically.
- Ít Java-side state hơn.
- Có affected-row count để diễn giải outcome.
- Có thể giảm lock duration so với chuỗi nhiều SELECT.

### 20.2. Hạn chế

- Không gọi domain method `reserve`.
- Không tự kích hoạt per-entity lifecycle callbacks và cascades.
- Có thể làm managed entities trong persistence context stale.
- `affected == 0` không nói rõ nguyên nhân: status, tenant, stock hay không tồn tại.
- Dễ phức tạp khi validation nhiều bảng, nhiều quy tắc.
- Cần tự quản lý version increments, outbox và audit khi phải đồng bộ với entity workflows.

### 20.3. Khi nào lock + domain method tốt hơn?

- Có nhiều business conditions khó diễn đạt bằng một SQL.
- Cần cập nhật nhiều entities trong cùng DB transaction.
- Cần domain methods duy trì invariants.
- Có callbacks/validation entity-level cần chạy.
- Cần thể hiện rõ state transition với những lỗi riêng.
- Mỗi resource có kích thước hợp lý và contention chấp nhận được.

### 20.4. Đừng dùng “cả hai” theo cách thừa

`SELECT ... FOR UPDATE` rồi ngay sau đó làm một atomic UPDATE có đầy đủ predicates trên cùng row đôi khi là lock thừa. Nếu cần giữ read state cho các bước khác thì có lý do; nếu chỉ thực hiện một DML, hãy đo tác động và đơn giản hóa.

## 21. Kiểm tra điều kiện trên nhiều rows: khóa một row có đủ không?

Giả sử quy tắc:

> Tổng giá trị đơn đang chờ của Customer không được vượt credit limit.

Các dữ liệu liên quan:

```text
Customer#7 creditLimit = 10.000
    |
    +-- Order#101 pending = 5.000
    +-- Order#102 pending = 4.000
```

Hai transactions cùng thêm Order mới 1.000. Mỗi bên đọc tổng pending=9.000 và cho phép, kết quả tổng=11.000.

### 21.1. Khóa mỗi Order mới không giúp

Hai Orders mới khác nhau, nên không tranh một existing row. Cả hai có thể commit.

### 21.2. Dùng Customer như aggregate guard

Một thiết kế là:

1. Mọi workflow thêm/sửa pending order có ảnh hưởng credit limit phải lock `Customer#7`.
2. Sau khi lock, đọc trạng thái quota/aggregate nhất quán theo transaction/isolation.
3. Kiểm tra credit limit.
4. Ghi Order/counter.
5. Commit.

Điều kiện rất quan trọng: **mọi writers phải tuân thủ khóa guard Customer**. Một ETL job INSERT Order trực tiếp mà không lock Customer có thể phá invariant.

### 21.3. Đếm nhiều rows và phantom inserts

Nếu chỉ chạy `SELECT SUM(pending_amount)` sau khi lock Customer, nhưng một writer khác không lock Customer, nó vẫn có thể INSERT vào bảng Order. Lock Customer không vật lý chặn mọi insert Order ở tất cả DB.

Có thể cần:

- Counter/materialized aggregate trên Customer được cập nhật atomically.
- Transaction SERIALIZABLE với retry.
- Database constraints/triggers được thiết kế đúng.
- Quy trình ghi bắt buộc qua aggregate root guard.

### 21.4. Viết rõ bất biến tổng

```text
customer.pendingAmount + newOrderAmount <= customer.creditLimit
```

Nếu lưu `pendingAmount` trên Customer và mọi writer cập nhật field này dưới lock Customer trong cùng transaction với Order, invariant dễ bảo vệ hơn việc SUM toàn bảng mỗi lần. Nhưng khi counter bị lệch do bug/legacy writer, cần reconciliation.

## 22. Dữ liệu “không có row” là một trường hợp đặc biệt

Một request:

```text
Nếu chưa có coupon redemption của customer này:
    tạo redemption mới
```

Nếu query tìm redemption không có kết quả thì **không có existing redemption row để khóa** theo trực giác thông thường.

### 22.1. Row lock không tự bảo vệ việc INSERT duy nhất

Hai transactions có thể đều thấy “chưa tồn tại” và cùng INSERT. Thông thường nên dùng:

```sql
UNIQUE (tenant_id, customer_id, coupon_id)
```

theo đúng business uniqueness contract.

### 22.2. Nếu cần quota cho coupon tổng?

Ngoài unique redemption per customer, quota `remainingUses` có thể cần một row CouponCapacity để lock/atomic decrement. Như vậy một workflow có thể cần **hai constraints**:

- Unique key chặn một customer dùng coupon hai lần.
- Counter lock/atomic update chặn vượt số lượt toàn coupon.

### 22.3. Gap/range locks không portable

Một vài database/isolation hỗ trợ key-range/gap locks ngăn phantom inserts trong phạm vi nhất định. Nhưng đừng mặc định `PESSIMISTIC_WRITE` trên một query rỗng có cùng tác dụng trên mọi PostgreSQL/MySQL/Oracle/SQL Server. Khi invariant là uniqueness, database UNIQUE constraint thường rõ ràng hơn.

## 23. Transaction isolation và dữ liệu được kiểm tra

Khóa là một phần của concurrency control; **isolation level** quyết định một phần trạng thái transaction có thể nhìn thấy.

| Isolation | Điều cần nhớ |
|---|---|
| READ COMMITTED | Thường mỗi statement thấy dữ liệu đã commit theo semantics DB |
| REPEATABLE READ | Giữ tính ổn định của một số quan sát; chi tiết MVCC/snapshot/locking khác nhau giữa DB |
| SERIALIZABLE | Mục tiêu tương đương lịch trình tuần tự, có thể ném serialization failure và cần retry |
| DB-specific modes | Có cơ chế riêng; cần tài liệu/version cụ thể |

### 23.1. PESSIMISTIC_WRITE không thay SERIALIZABLE

Lock một InventoryItem row có thể bảo vệ số lượng của item ấy, nhưng không tự bảo vệ:

- Tổng số Orders trong ngày.
- Predicate “không có appointment trùng”.
- Tổng hạn mức trên nhiều accounts.
- Không có duplicate SKU được INSERT.
- Tham chiếu dữ liệu ở database khác.

### 23.2. SERIALIZABLE không có nghĩa không thể rollback

Một transaction serializable có thể bị DB buộc rollback khi phát hiện serialization anomaly. Nếu nghiệp vụ cần, service phải retry toàn transaction **trong context mới** và chạy lại validation.

### 23.3. Không suy ra locking semantics từ tên isolation duy nhất

MySQL/InnoDB, PostgreSQL và SQL Server có khác biệt lớn về snapshot, locking reads, predicates và phantom protection. Khi một invariant quan trọng, integration test trên database mục tiêu là bắt buộc.

### 23.4. Việc B chờ A không bảo đảm tất cả dữ liệu của B đều fresh

Nếu B đã load nhiều entities trước khi chờ row lock, các managed instances khác vẫn có thể stale. Hãy xác định phạm vi trạng thái cần refresh/reload sau lock, hoặc tránh preload trước phần critical section.

---

## 24. Lấy khóa nhiều entities: thứ tự là một phần thiết kế

Một transaction cần khóa:

- Order#200.
- InventoryItem#42.
- Coupon#9.

Transaction khác lại khóa Coupon trước rồi Order sau; có thể hình thành vòng chờ.

### 24.1. Đặt quy ước lock ordering

Ví dụ:

```text
Rule A:
  Account: order by account ID ascending.

Rule B:
  Checkout workflow:
    1. Order
    2. Inventory items sorted by (tenant, ID)
    3. Coupon capacity
```

Mọi workflows liên quan cần tuân theo cùng thứ tự, không chỉ một method.

### 24.2. Khóa danh sách item theo thứ tự ID

```java
List<Long> itemIds = requestedLines.stream()
    .map(RequestLine::itemId)
    .distinct()
    .sorted()
    .toList();

for (Long id : itemIds) {
    InventoryItem item = em.find(
        InventoryItem.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (item == null) {
        throw new ItemNotFoundException(id);
    }

    // Không validate trước khi đã bảo vệ đúng tập state cần dùng.
}
```

Sau khi lấy toàn bộ locks, có thể kiểm tra tất cả số lượng và apply changes. Nếu có nhiều lần xuất hiện cùng một item trong request, cần **gộp tổng quantity theo ID** trước khi validate để tránh over-reservation do xử lý từng dòng không nhất quán.

### 24.3. Nhưng lock tất cả trước có thể tốn kém

Với cart 1.000 mặt hàng, khóa 1.000 rows để rồi phát hiện một item hết hàng cuối danh sách rất tốn. Có thể cần:

- Validate không cần lock sơ bộ để loại lỗi rõ.
- Đặt giới hạn số items/cart.
- Thiết kế atomic batch cập nhật có điều kiện.
- Tách reservation workflows.
- Giảm hot-item contention.
- Chấp nhận rollback nguyên batch nếu invariant đòi all-or-nothing.

Không có một chiến lược duy nhất đúng cho mọi khối lượng.

### 24.4. Deadlock có thể vẫn xảy ra

FK checks, triggers, indexes và các bảng phụ có thể tạo vòng chờ ngoài các locks tường minh. Lock ordering giảm nguy cơ, không loại bỏ mọi deadlock.

## 25. Lock scope trên association: không khóa toàn graph

Giả sử:

```text
SalesOrder
  ├── Customer
  ├── Lines
  └── ShippingRequest
```

Khi gọi:

```java
em.lock(
    order,
    LockModeType.PESSIMISTIC_WRITE
);
```

không được suy ra Customer, mọi Line và ShippingRequest cũng đã khóa để business validation an toàn.

### 25.1. Đặc điểm JPA

JPA có `PessimisticLockScope` và lock scope hint:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);
```

Nhưng `EXTENDED` không phải cơ chế đệ quy khóa toàn bộ object graph. Scope theo spec chủ yếu đề cập những mapping liên quan như owned join/collection tables; hành vi cụ thể còn phụ thuộc provider/database.

### 25.2. Khi kiểm tra quan hệ phụ thuộc

Nếu `Order.ship()` kiểm tra tất cả Lines chưa bị cancel, nhưng Lines có thể được một service khác sửa độc lập, cần một quy ước:

- Lock Order root cho mọi thay đổi Lines; hoặc
- Lock các Line rows cần thiết; hoặc
- Dùng optimistic version/aggregate revision; hoặc
- Dùng database-level constraint/isolation phù hợp.

**Không chỉ viết JOIN FETCH rồi nghĩ đã khóa mọi entity được fetch.**

### 25.3. Fetch plan và locking plan không giống nhau

`JOIN FETCH` quyết định association nào được tải. `PESSIMISTIC_WRITE` quyết định locking semantics cho query/entity roots theo JPA/provider. SQL join và locking có tương tác với nhau, nhưng fetch không đồng nghĩa “khóa mọi row trong join”.

## 26. Khi validation cần đọc aggregate COUNT/SUM

Một service kiểm tra:

```jpql
select count(r)
from StockReservation r
where r.item.id = :itemId
  and r.status = :pending
```

rồi quyết định nếu count < limit.

Chỉ khóa InventoryItem có thể là một **guard row** nếu toàn bộ writers tạo reservation đều khóa InventoryItem trước. Nhưng nếu một writer khác không lock guard, nó vẫn có thể INSERT.

### 26.1. Không dựa vào `setLockMode` trên scalar COUNT

Một count query trả `Long`, không trả entity root để JPA áp lock theo contract entity locking thông thường. Không coi:

```java
em.createQuery(
    "select count(r) from StockReservation r",
    Long.class
).setLockMode(LockModeType.PESSIMISTIC_WRITE);
```

là cách portable khóa mọi row r khi đếm.

### 26.2. Chọn một tài nguyên đại diện invariant

Ví dụ `ReservationQuota` entity chứa `remaining`. Tất cả operations tiêu thụ quota cập nhật cùng row dưới khóa/atomic DML. Đó là một mô hình có điểm đồng bộ rõ hơn.

### 26.3. Khi không có guard row khả thi

SERIALIZABLE isolation, DB exclusion constraints, unique per slot hoặc các giải pháp domain-specific có thể phù hợp hơn. Hãy thiết kế từ invariant, không từ syntax JPA.

## 27. Khóa và duplicate requests: cần idempotency

Giả sử client gửi request reserve(2) với `requestKey=ABC`, server xử lý thành công nhưng HTTP response bị mất. Client retry.

Không có idempotency:

```text
Request ABC #1:
  lock Item
  reserve(2)
  commit

Request ABC #2:
  lock Item
  reserve(2) lần nữa
  commit
```

Hai requests được xử lý tuần tự — **khóa hoạt động đúng** — nhưng workflow vẫn giữ chỗ bốn đơn vị thay vì hai.

### 27.1. Unique request key

Một bảng có:

```sql
UNIQUE (tenant_id, request_key)
```

giúp bảo vệ tính duy nhất ở database.

### 27.2. Flow idempotency mẫu

```text
Nhận requestKey
      |
      v
Kiểm tra đã có outcome cho key này trong authorized tenant?
   /             \
 Có               Chưa
 |                  |
 v                  v
Trả lại outcome    Bắt đầu transaction
đã lưu              |
                    v
               Lock item/quota
                    |
                    v
               Validate state
                    |
                    v
               Update + INSERT record có UNIQUE key
                    |
                    v
                  Commit
```

Nếu hai requests cùng key xuất hiện đồng thời, cả hai có thể “chưa thấy” record ở bước đầu. UNIQUE constraint và transaction handling vẫn phải xử lý race. Sau duplicate-key error, đọc lại outcome bằng transaction mới (khi rollback đã hoàn tất) và xác minh payload/tenant phù hợp trước khi trả kết quả idempotent.

### 27.3. Không coi mọi duplicate key là retry hợp lệ

Nếu cùng requestKey nhưng khác item/quantity, đó có thể là conflict nghiệp vụ hoặc tấn công lạm dụng. Cần lưu payload fingerprint/metadata phù hợp và từ chối key bị dùng lại với nội dung khác.

### 27.4. Lock không làm remote payment exactly once

Payment provider không tham gia row lock DB, vì vậy cần idempotency key ở payment API hoặc workflow reconciliation riêng.

## 28. Khóa và external side effects: không giữ transaction quá lâu

Không nên:

```java
@Transactional
public void payAndReserve(...) {
    InventoryItem item = lockItem(...);

    paymentGateway.charge(...); // HTTP chậm, không rollback theo DB.

    item.reserve(...);

    emailClient.send(...);      // Email cũng không rollback.
}
```

Vấn đề:

- Database row lock và connection bị giữ khi chờ network.
- Payment có thể thành công nhưng transaction DB rollback.
- Email có thể được gửi trong khi reservation không được commit.
- Retry transaction có thể charge lần nữa nếu thiếu idempotency.
- Lock contention và deadlock/timeout có thể tăng mạnh.

### 28.1. Tách workflow thành các transaction ngắn

Một hướng:

```text
Transaction 1:
  lock item/quota
  validate
  tạo PENDING reservation
  giảm available / tăng reserved
  ghi outbox event
  COMMIT

Bên ngoài transaction:
  xử lý payment qua idempotent API

Transaction 2:
  lock reservation/order liên quan
  kiểm tra payment outcome & status hiện tại
  CONFIRM hoặc RELEASE/CANCEL
  COMMIT
```

Các bước có thể cần saga/compensation, expiration, reconciliation và idempotency. Thiết kế này có nhiều trạng thái hơn nhưng phản ánh ranh giới giữa database transaction và external services.

### 28.2. Không “chỉ cần after-commit là đủ” cho mọi use case

Một callback sau commit có thể giúp không gửi trước khi DB commit, nhưng nếu process crash giữa commit và callback, notification có thể không được phát. Khi cần delivery durable, transactional outbox + relay/retry thường phù hợp hơn.

### 28.3. Ghi outbox event sau validation trong cùng transaction

Không tạo outbox event “OrderShipped” nếu validation state transition thất bại. Event phải phản ánh **đúng thay đổi sẽ được commit**, và vẫn cần consumer idempotency.

---

## 29. Lock duration, connection pool và contention

Một transaction có khóa càng lâu, các transactions cần resource tương tự càng dễ phải chờ.

```text
Thread A: lock Item#42 --- validate --- update --- external call --- commit
Thread B:                   chờ Item#42 -----------------------> ...
Thread C:                   chờ Item#42 -----------------------> ...
```

Nếu external call mất vài giây, một hot item có thể làm nhiều requests tắc nghẽn.

### 29.1. Rút ngắn critical section

- Validate request format/identity trước.
- Chuẩn bị các tính toán không phụ thuộc mutable DB state trước.
- Không gọi network khi giữ lock.
- Không serialize response lớn trong transaction.
- Không gọi `Thread.sleep` trong transaction như cách thử xử lý race.
- Không lấy lock quá nhiều rows.
- Cập nhật và commit ngay sau khi các DB operations thiết yếu đã hoàn tất.

### 29.2. Những metrics quan trọng

| Metric | Câu hỏi |
|---|---|
| Lock wait p95/p99 | Request chờ khóa bao lâu? |
| Transaction duration | Critical section kéo dài bao lâu? |
| Deadlock count | Có vòng chờ resource không? |
| Lock timeout rate | Bao nhiêu request thất bại khi lấy khóa? |
| DB connection pool wait | Threads đang chiếm/đợi connection thế nào? |
| Business rejection count | Bao nhiêu request bị từ chối vì state thực sự không hợp lệ? |
| Retry count | Có retry storm không? |
| Successful reservations/sec | Throughput hữu ích có tăng không? |
| Hot item IDs | Có một resource chịu cạnh tranh quá cao không? |
| SQL rows examined | Query tìm lock có scan rộng không? |

### 29.3. Đừng chỉ đếm số SQL

Một workflow với một `SELECT FOR UPDATE` và một `UPDATE` có thể bị chậm hàng giây do lock wait. SQL count thấp không chứng minh performance tốt.

## 30. Index: phải tìm đúng row trước khi khóa

Query:

```jpql
select i
from InventoryItem i
where i.tenantId = :tenant
  and i.sku = :sku
```

cần index phù hợp trên business key. Nếu DB phải quét nhiều rows để xác định target, chi phí và phạm vi lock có thể tăng theo engine/isolation.

Schema ví dụ có:

```sql
UNIQUE (tenant_id, sku)
```

vừa bảo vệ uniqueness, vừa cung cấp một access path có thể hiệu quả cho query theo tenant+SKU.

Nhưng:

- Index có chi phí duy trì khi ghi.
- Composite index order/selectivity quan trọng.
- Query plan còn tùy statistics và DB optimizer.
- Index không tự bảo đảm phạm vi physical locks chỉ đúng một row trong mọi database/isolation.

Quan sát execution plan và lock diagnostics trong môi trường mục tiêu.

## 31. Lock timeout: không lấy được khóa thì chưa đánh giá được nghiệp vụ

Ví dụ thêm hint:

```java
TypedQuery<InventoryItem> q = em.createQuery(
    """
    select i
    from InventoryItem i
    where i.id = :id
      and i.tenantId = :tenant
    """,
    InventoryItem.class
);

q.setParameter("id", itemId);
q.setParameter("tenant", authorizedTenantId);
q.setLockMode(LockModeType.PESSIMISTIC_WRITE);
q.setHint("jakarta.persistence.lock.timeout", 1000);

InventoryItem item = q.getSingleResult();
```

Giá trị thường diễn đạt thời gian chờ lock ở đơn vị milliseconds. **Khả năng hỗ trợ hint phụ thuộc database/provider/dialect**; nó không phải cam kết SLA chính xác 1.000 ms trên mọi stack.

### 31.1. Timeout khác “hết hàng”

Nếu không lấy được lock:

- Không có state được kiểm tra thành công dưới lock.
- Không thể kết luận hết hàng.
- Không thể coi request đã reserve thành công.
- Có thể trả lỗi retryable/tạm thời theo API contract.

Nếu sau khi lấy được lock mà availableQuantity không đủ, đó là **business rejection** khác hẳn.

### 31.2. PessimisticLockException và LockTimeoutException

JPA có:

```java
jakarta.persistence.PessimisticLockException
jakarta.persistence.LockTimeoutException
```

Theo contract JPA:

- `PessimisticLockException` thường biểu thị lock failure dẫn đến rollback ở mức transaction.
- `LockTimeoutException` mô tả trường hợp lock failure chỉ rollback statement thay vì tự động toàn transaction.

Trong môi trường thực, database/provider/Spring exception translation và transaction status có thể thêm wrappers; phải kiểm tra nguyên nhân và rollback state thay vì catch một class rồi tiếp tục mù quáng.

### 31.3. Không fallback sang không khóa

Sai:

```java
try {
    return findWithLock(id);
} catch (RuntimeException ex) {
    return em.find(InventoryItem.class, id);
}
```

Nếu lock là điều kiện để bảo vệ business invariant, bỏ lock sau timeout là làm mất bảo vệ. Hãy rollback/retry/queue/thông báo tạm thời theo policy.

## 32. Deadlock và thứ tự khóa

Hai transfers:

```text
A giữ Account#1, muốn Account#2
B giữ Account#2, muốn Account#1
```

gây deadlock. Khi database phát hiện, thường chọn một transaction làm nạn nhân để rollback. Application phải dự đoán điều này.

### 32.1. Lock ordering giảm deadlock

Chọn một thứ tự nhất quán:

```java
long firstId = Math.min(accountA, accountB);
long secondId = Math.max(accountA, accountB);
```

và luôn khóa theo thứ tự đó.

### 32.2. Không phải toàn bộ deadlocks có thể tránh chỉ bằng ordering

Indexes, foreign keys, triggers, background jobs và transaction khác có thể tạo thứ tự khóa ngoài dự đoán. Vì vậy cần log, metrics, retry policies và kiểm thử ở database thật.

### 32.3. Khi retry, chạy lại validation

Sau deadlock/lock timeout, không tiếp tục transaction bị lỗi. Với retry hợp lệ:

1. Rollback attempt hiện tại.
2. Bắt đầu transaction/persistence context mới.
3. Lấy lại các locks.
4. Đọc current state.
5. Kiểm tra **lại** các business conditions.
6. Mutate và commit nếu còn hợp lệ.

Không replay một snapshot balance/quantity đã tính trước khi fail.

## 33. Retry policy: không retry mọi lỗi theo cùng cách

| Outcome | Retry? | Cần làm gì trước retry |
|---|---|---|
| Lock timeout tạm thời | Có thể, giới hạn | Transaction mới, backoff/jitter, reload/revalidate |
| Deadlock victim | Thường có thể, giới hạn | Rollback, transaction mới |
| Serialization failure | Có thể | Rerun toàn unit of work |
| Optimistic conflict | Tùy nghiệp vụ | Reload state, re-evaluate |
| Không đủ tồn kho | Không tự retry vô hạn | Chờ restock/event hoặc trả business rejection |
| Order đã CANCELLED | Thường không | Trả transition conflict |
| Duplicate idempotency key | Không xử lý operation hai lần | Đọc outcome cũ, verify payload |
| UNIQUE/FK violation | Không mặc định | Phân loại constraint/business error |
| SQL syntax/configuration error | Không | Sửa code/config |
| Payment provider timeout | Chưa biết outcome | Reconciliation/idempotency, không double charge |

### 33.1. Retry coordinator bên ngoài @Transactional

Một cấu trúc Spring:

```text
API Controller
     |
     v
ReservationCoordinator (quản lý retry attempts)
     |
     v
ReservationAttemptService.reserveOnce(...)
     |   @Transactional
     v
Lock -> revalidate -> mutate -> commit
```

Mỗi attempt phải có transaction mới. Với Spring proxy, tránh đặt `@Transactional` ở một method bị gọi nội bộ qua `this.` dẫn tới annotation không có hiệu lực.

### 33.2. Backoff không thay đúng đắn

Một retry sau 200 ms vẫn phải **đọc lại** state. Chờ lâu hơn không tự bảo đảm request được phép thực hiện.

### 33.3. Giới hạn retry để tránh thảm họa tải

Nhiều workers cùng tranh item nóng có thể tạo retry storm. Đặt số attempts tối đa, jitter hoặc queue theo chiến lược phù hợp. Đo throughput hữu ích, không chỉ số retries.

## 34. Lỗi dễ gặp: đợi lock lâu rồi dùng trạng thái request cũ

Ví dụ client gửi:

```json
{
  "orderId": 55,
  "expectedStatus": "PAID",
  "action": "SHIP"
}
```

Khi service lấy lock, Order có thể đã `REFUND_PENDING`. Business validation phải dựa trên **Order hiện tại**, không chỉ `expectedStatus` từ client.

Một cách xử lý:

```java
if (order.getStatus() != OrderStatus.PAID) {
    throw new InvalidOrderTransitionException(
        "Order is no longer PAID"
    );
}
```

Nếu API có optimistic precondition, có thể kiểm tra cả expected status/version dưới lock, nhưng những giá trị từ client là **preconditions**, không phải source of truth.

## 35. Lỗi dễ gặp: lấy lock sau khi đã gọi callback bên ngoài

Sai:

```java
if (inventoryLooksAvailable()) {
    paymentClient.charge();
    lockInventory();
    reserve();
}
```

Nếu sau charge mới phát hiện không đủ stock, cần hoàn tiền/compensation.

Khóa trước charge cũng có vấn đề vì giữ DB transaction qua network I/O. Cần workflow hai giai đoạn:

- Reserve tồn kho bằng transaction ngắn.
- Commit reservation pending.
- Gọi payment idempotent ngoài lock.
- Xác nhận/hoàn trả reservation ở transaction mới.
- Xử lý timeout/reconciliation.

Đừng cố giải tất cả bằng một transaction DB.

## 36. Lỗi dễ gặp: entity đã nằm trong persistence context

Giả sử:

```java
InventoryItem item = em.find(InventoryItem.class, id);

// Một khoảng thời gian sau:
em.lock(item, LockModeType.PESSIMISTIC_WRITE);

item.reserve(q);
```

Lấy lock không mặc nhiên làm state managed Java được reload. Nếu row bị transaction khác thay đổi giữa hai mốc, validation có thể đọc snapshot stale. Cần:

- Load lần đầu với lock, hoặc
- Refresh dưới lock khi phù hợp, hoặc
- Dùng fresh context/transaction với isolation rõ.

Cẩn thận: `em.refresh` có thể ghi đè local unflushed changes, còn `em.clear` detach toàn bộ managed entities.

## 37. Lỗi dễ gặp: khóa chỉ một resource trong invariant nhiều resource

Ví dụ:

```text
Order#55: status=PAID
InventoryItem#42: available=1
ShippingCapacity#7: remaining=1
```

Hai Orders khác nhau có thể cùng muốn reserve ShippingCapacity#7. Chỉ khóa Orders khác nhau không chặn cạnh tranh quota.

Thiết kế đúng phải xác định những resources tham gia:

```text
Order
  + Inventory
  + ShippingCapacity
```

Có thể cần khóa/atomic update trên từng resource, cùng transaction và thứ tự khóa được thống nhất giữa workflows.

### 37.1. Không lock toàn graph một cách mù quáng

Khóa mọi association chỉ vì chúng có liên kết ORM có thể tạo contention và performance kém. Bảo vệ những trạng thái **thật sự ảnh hưởng invariant**, không phải tất cả dữ liệu liên quan về mặt object graph.

## 38. Lỗi dễ gặp: kiểm tra “trống” rồi INSERT

Ví dụ:

```java
boolean noBooking = checkNoBookingForSlot(slot);

if (noBooking) {
    insertBooking(slot);
}
```

Nếu hai transactions cùng thấy trống, cả hai có thể INSERT. Khóa một row Booking hiện có không bảo vệ slot chưa có Booking.

Giải pháp có thể là:

- UNIQUE (slot_id) nếu một slot chỉ có một booking hợp lệ.
- Atomic claim trên Slot row.
- Exclusion constraints cho khoảng thời gian (DB-specific).
- SERIALIZABLE isolation với retry.
- Row guard có sẵn và mọi writers tuân thủ.

**Đừng dùng pessimistic lock như một phép thay thế tổng quát cho uniqueness.**

## 39. Lỗi dễ gặp: chỉ test happy path

Một unit test gọi service với một EntityManager và một request:

```java
service.reserve(42, 2);
assertEquals(8, loadAvailable(42));
```

kiểm tra logic trừ tồn kho nhưng **chưa kiểm tra concurrency**.

Cần test hai transactions thật tranh cùng row, data state ở cuối và các failure modes.

---

## 40. Kiểm thử concurrency: thiết kế kịch bản hai transactions

### 40.1. Fixture

```text
Item#42
  tenant = shop-a
  status = ACTIVE
  available = 5
  reserved = 0
```

Hai requests cùng muốn reserve(4).

Outcome đúng mong đợi:

- Một request thành công.
- Request còn lại thấy available=1 và bị từ chối vì không đủ.
- available cuối = 1.
- reserved cuối = 4.
- Chỉ một StockReservation được commit cho hai business operations cạnh tranh.
- Không có hai notifications “đã giữ chỗ thành công”.

### 40.2. Dùng hai EntityManagers độc lập

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();
```

Không dùng cùng một `EntityManager` đồng thời ở nhiều threads; nó không có thread-safe contract cho cách sử dụng đó.

### 40.3. Điều phối transaction A và B

```text
Thread A                              Thread B
-----------------------------------------------------------------
begin txA
find Item#42 PESSIMISTIC_WRITE
signal A_HAS_LOCK

                                      begin txB
                                      cố find Item#42
                                      PESSIMISTIC_WRITE
                                      chờ A (hoặc timeout)

A reserve(4)
commit txA

                                      sau khi A commit:
                                      B được cấp lock
                                      B nhìn available=1
                                      B reserve(4) -> reject
                                      rollback/no state change
-----------------------------------------------------------------
Mở emC để verify available=1, reserved=4
```

### 40.4. Ví dụ test skeleton với latch

```java
CountDownLatch aHasLock = new CountDownLatch(1);
CountDownLatch releaseA = new CountDownLatch(1);
CountDownLatch bAboutToLock = new CountDownLatch(1);

ExecutorService pool = Executors.newFixedThreadPool(2);

Future<?> aFuture = pool.submit(() -> {
    try (EntityManager a = emf.createEntityManager()) {
        EntityTransaction tx = a.getTransaction();
        tx.begin();
        try {
            InventoryItem item = a.find(
                InventoryItem.class,
                42L,
                LockModeType.PESSIMISTIC_WRITE
            );
            aHasLock.countDown();

            if (!releaseA.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Test synchronization timeout"
                );
            }

            item.reserve(4);
            tx.commit();
        } catch (Exception e) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw new RuntimeException(e);
        }
    }
});

Future<?> bFuture = pool.submit(() -> {
    try (EntityManager b = emf.createEntityManager()) {
        if (!aHasLock.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "A never acquired lock"
            );
        }

        EntityTransaction tx = b.getTransaction();
        tx.begin();
        try {
            bAboutToLock.countDown();

            InventoryItem item = b.find(
                InventoryItem.class,
                42L,
                LockModeType.PESSIMISTIC_WRITE
            );

            // Nếu A đã commit, B phải đánh giá state mới.
            item.reserve(4);

            tx.commit();
        } catch (InsufficientStockException expected) {
            if (tx.isActive()) {
                tx.rollback();
            }
        } catch (Exception e) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw new RuntimeException(e);
        }
    }
});

try {
    if (!bAboutToLock.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException(
            "B did not start lock attempt"
        );
    }

    // Không lấy bAboutToLock làm bằng chứng B đã bị
    // database chặn: nó chỉ báo B chuẩn bị gọi find().
    // Test thật cần instrumentation/timeout xác định.
} finally {
    releaseA.countDown();
}

aFuture.get(15, TimeUnit.SECONDS);
bFuture.get(15, TimeUnit.SECONDS);
pool.shutdown();
```

Mã minh họa cần các imports `java.util.concurrent.*`, setup JUnit/`EntityManagerFactory`, domain exception và transaction provider tương ứng. Mục đích của skeleton là thể hiện **hai contexts, hai transactions và các mốc điều phối**. Nó **không** tự chứng minh B đã đợi lock: latch `bAboutToLock` được gửi trước lời gọi DB. Với test nghiêm ngặt, cần thêm probe đo lock wait hoặc dùng bounded `Future.get(timeout)` cùng barrier/instrumentation thật để xác nhận B chưa đi qua lock trước khi A nhả.

### 40.5. Tránh test bằng Thread.sleep đơn thuần

`Thread.sleep(100)` không bảo đảm scheduling: trên CI chậm, thread B có thể chưa kịp chạy; trên local nhanh, event đã xảy ra. Dùng latch/barrier/DB instrumentation và timeouts rõ, cùng database lock diagnostics khi cần.

### 40.6. Dùng database phù hợp production

H2/in-memory DB có thể khác PostgreSQL/MySQL/Oracle/SQL Server về `FOR UPDATE`, lock timeout, MVCC và deadlock. Với correctness quan trọng, integration test trên target database/provider/dialect; Testcontainers có thể hữu ích nếu stack hỗ trợ.

### 40.7. Kiểm tra final state bằng context mới

`emC.find(...)` trong transaction/context mới sau A/B hoàn tất mới phản ánh DB commit phù hợp. Đừng dùng object từ transaction vừa rollback để đánh giá trạng thái cuối.

---

## 41. Kiểm thử business validation trong trường hợp lock contention

Bên cạnh scenario hai requests cùng đủ hàng ở thời điểm ban đầu, thêm:

### 41.1. Item đã SUSPENDED khi lấy lock

A thay ACTIVE→SUSPENDED và commit. B đang chờ, sau đó được cấp lock. B phải từ chối reservation vì status hiện tại không ACTIVE.

### 41.2. Item vừa được restock

A tăng available từ 1→10. B chờ lock rồi muốn reserve(5). Nếu business policy cho phép, B có thể thành công sau khi thấy state mới.

Điều này chứng minh **điều kiện phải được tái đánh giá**, không phải luôn trả lỗi cho request đã phải chờ.

### 41.3. Hai customers cùng tiêu thụ quota

A và B muốn cùng một suất ShippingCapacity cuối. Hai Orders khác nhau. Test phải phát hiện rằng khóa Orders không đủ, còn lock/atomic update Capacity mới bảo vệ invariant.

### 41.4. Validation exception xảy ra sau mutation phụ

Giả sử service đã cập nhật Customer counter rồi mới phát hiện Item không đủ. Cần rollback toàn transaction, và final state phải không chứa counter update nửa vời.

### 41.5. Unique requestKey race

Hai transactions gửi cùng requestKey. Assert chỉ một StockReservation commit, số lượng chỉ trừ một lần và response/reconciliation xử lý đúng duplicate key. Dùng constraint DB, không chỉ kiểm tra `existsByRequestKey`.

### 41.6. Lock timeout

A giữ lock lâu; B cấu hình timeout ngắn và không lấy được lock. Assert B **không** mutate item và không trả lỗi “hết hàng”. Kiểm tra exception/cause chain theo target provider.

### 41.7. Deadlock

Hai operations khóa hai Accounts theo thứ tự ngược. Test mô phỏng deadlock hoặc timeout có giới hạn; thay code theo một lock order thống nhất và quan sát hành vi dưới concurrency.

### 41.8. Side effect ngoài DB

Cho transaction reserve rollback sau khi viết outbox pending (chưa commit). Assert không có event committed, và worker relay không gửi sự kiện cho reservation thất bại.

### 41.9. Retry phải reload

A reserve(4) trước. B retry sau conflict; assert B đọc lại available=1 và từ chối chứ không replay phép tính từ available=5.

### 41.10. Multi-tenant isolation

Item#42 thuộc shop-a. Request từ shop-b không được đọc/cập nhật row đó; lỗi trả về không tiết lộ ownership trái policy.

## 42. Thiết kế response API theo outcome

| Outcome | Ví dụ response | Lưu ý |
|---|---|---|
| Reservation commit thành công | 200/201 theo API contract | Có reservation ID/outcome ổn định |
| Request giống hệt key đã xử lý | Trả lại outcome cũ | Không double-reserve |
| Không đủ stock | 409 hoặc domain-specific code | Business rejection |
| Item không ACTIVE | 409/422 tùy API contract | Trạng thái không hợp lệ |
| Không tìm thấy trong authorized scope | 404 theo policy | Không lộ tenant khác |
| Lock timeout | 409/423/503 hoặc retryable code theo contract | Không đánh đồng hết hàng |
| Deadlock/serialization failure | Retry nội bộ hoặc trả lỗi phù hợp | Không để exception kỹ thuật lộ thông tin nhạy cảm |
| Validation input fail | 400/422 theo API contract | Có thể xử lý trước DB lock |
| Commit thất bại | Không trả success | Transaction outcome chưa thành công |

HTTP codes trong bảng là **gợi ý thiết kế**, không phải một mapping bắt buộc do JPA quy định. `423 Locked` có ý nghĩa riêng trong HTTP/WebDAV context; không mặc định mọi lock timeout phải trả 423. API nên phân biệt business conflict với infrastructure contention và không lộ thông tin của tài nguyên không được phép.

### 42.1. Không khẳng định thành công quá sớm

Nếu Spring `@Transactional` commit ngoài method body, response success phải phụ thuộc việc transaction invocation thực sự hoàn tất thành công, không chỉ return từ một method nội bộ.

### 42.2. External workflow có thể ở trạng thái pending

Nếu reservation đã commit nhưng payment chưa xác nhận, API nên có trạng thái `PENDING_PAYMENT` hoặc tương tự thay vì nói toàn bộ checkout đã hoàn tất.

## 43. Anti-pattern tổng hợp

### 43.1. Kiểm tra trước khóa

```java
boolean enough = item.getAvailableQuantity() >= q;
em.lock(item, PESSIMISTIC_WRITE);
if (enough) item.reserveUnchecked(q);
```

Sai vì quyết định dựa trên dữ liệu trước lock.

### 43.2. Lock một transaction, save transaction khác

```text
tx1: SELECT ... FOR UPDATE; COMMIT
tx2: validate/write
```

Lock không còn tồn tại ở tx2.

### 43.3. Bỏ qua domain validation vì đã có lock

Lock không bảo đảm quantity > 0, status ACTIVE hoặc tenant đúng.

### 43.4. Tự xem managed entity đã fresh sau em.lock

`lock` không phải lời hứa refresh toàn bộ state. Có thể cần load với lock ngay từ đầu hoặc refresh có chủ đích.

### 43.5. Lock root nhưng invariant nằm ở child/counter khác

Sai phạm vi; cần guard resource đúng.

### 43.6. Không có unique constraint cho idempotency

Hai requests trùng key chạy tuần tự dưới lock vẫn có thể tạo hai side effects.

### 43.7. Đưa payment/email vào critical section

Kéo dài lock; external system không tham gia DB rollback.

### 43.8. Catch lock timeout và tiếp tục không khóa

Phá concurrency contract, dễ oversell/lost update.

### 43.9. Retry bằng dữ liệu cũ

Một attempt mới phải reload và revalidate, không replay computed new balance cũ.

### 43.10. Dùng `PESSIMISTIC_WRITE` với mọi SELECT

Tăng contention vô ích cho read-only use cases.

### 43.11. Dùng COUNT scalar + lock mode để khóa mọi row được đếm

Không portable; query result scalar không có semantics entity locking như mong muốn.

### 43.12. Dùng `JOIN FETCH` rồi nghĩ toàn graph đã được khóa

Fetch plan và lock scope khác nhau.

### 43.13. Không có index cho lookup khóa

Có thể tăng scan/lock footprint và thời gian chờ.

### 43.14. Khóa rows theo thứ tự khác nhau giữa workflows

Dễ deadlock.

### 43.15. Nhầm khóa với lease sau commit

DB row lock biến mất khi transaction hoàn tất; job kéo dài cần lease/fencing.

### 43.16. Dùng một EntityManager ở nhiều threads

Vi phạm cách dùng an toàn; persistence context không phải shared thread-safe object.

### 43.17. Không phân biệt business rejection và hạ tầng thất bại

Lock timeout không chứng minh điều kiện nghiệp vụ sai.

### 43.18. Đo SQL count nhưng bỏ qua lock waits

Một query chờ vài giây có thể phá SLA dù chỉ có một statement.

### 43.19. Chỉ test tuần tự

Không kiểm chứng state sau contention.

### 43.20. Xem @Version như thay thế mọi row lock

Optimistic và pessimistic giải quyết xung đột theo thời điểm khác nhau. Cần chọn theo invariant và workload.

### 43.21. Dùng atomic UPDATE nhưng quên version/cache implications

Bulk DML không tự đồng bộ managed entity và versioning như entity-level update.

### 43.22. Kiểm tra quota bằng COUNT rồi chỉ lock một row không liên quan

Không bảo vệ phantom inserts/invariant tổng.

### 43.23. Gửi event trước commit

Transaction có thể rollback; dùng outbox/after-commit theo độ bền yêu cầu.

### 43.24. Luôn retry khi hết hàng

“Không đủ stock” là trạng thái nghiệp vụ, không phải deadlock transient.

### 43.25. Quên tenant trong khóa/validation

Lock không cung cấp authorization; phải lọc và xác nhận scope.

## 44. Bảng quyết định nhanh

| Bài toán | Cách cân nhắc trước tiên | Vì sao |
|---|---|---|
| Chỉ đọc danh sách sản phẩm | Read-only query/DTO, không pessimistic lock | Không cần serialize writes |
| Hai requests trừ tồn kho đơn giản | Atomic conditional UPDATE | Check và mutate trong một statement |
| Reserve tồn kho kèm nhiều domain rules | PESSIMISTIC_WRITE + validation dưới lock | Giữ state ổn định trong transaction |
| Chuyển trạng thái Order phức tạp | Lock Order + domain state machine | Chỉ một transition hợp lệ tiến hành |
| Transition một field, một predicate | Conditional UPDATE + count | Có thể đơn giản hơn fetch+lock |
| Chỉnh sửa form dài, ít conflict | @Version + expectedVersion/If-Match | Không giữ transaction qua user think time |
| Chuyển tiền hai accounts | Lock đúng accounts, order cố định, transaction + ledger | Bảo vệ read-modify-write đa row |
| Quota từ counter row | Lock/atomic update counter | Guard đúng nguồn sự thật |
| Quota từ COUNT nhiều rows | Counter/constraint/SERIALIZABLE | Một row lock tùy ý không đủ |
| Unique email/coupon redemption | UNIQUE constraint | Chặn concurrent INSERT |
| Claim job ngắn | Atomic claim hoặc lock + status check | Không để hai workers claim cùng job |
| Xử lý job dài | Lease/fencing/idempotency | Không giữ DB lock qua phút/giờ |
| Payment/email | Outbox/idempotency/saga | DB lock không rollback external effects |
| High contention hot row | Benchmark atomic DML/partition/lock strategy | Pessimistic wait có thể bottleneck |
| Report/analytics | Snapshot/isolation/reporting DB | Lock rows để đọc thường không cần |
| Client retry sau timeout | Idempotency key + stored outcome | Lock không tự nhận biết request lặp |

## 45. Bài tập thực hành có gợi ý

### Bài 1 — Khóa có làm quantity hợp lệ?

Item còn 2, request muốn reserve(5), transaction đã lấy `PESSIMISTIC_WRITE` thành công.

**Đáp án:** Không. Lock không thay domain validation; từ chối vì 2 < 5.

### Bài 2 — Kiểm tra trước lock

Code đọc available=10, thấy đủ 6, rồi chờ khóa. Transaction khác đã reserve 7 và commit.

**Gợi ý:** Sau khi lấy lock phải đọc lại current state (hoặc dùng loaded-with-lock/fresh context) và kiểm tra lại; lúc này chỉ còn 3.

### Bài 3 — Validation được phép làm trước

Trong các điều kiện `quantity > 0`, `item.status == ACTIVE`, `item.available >= quantity`, điều kiện nào nên kiểm tra trước lock?

**Đáp án:** `quantity > 0`; hai điều kiện kia phụ thuộc mutable DB state nên kiểm tra dưới concurrency control.

### Bài 4 — Gọi find với lock

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

**Câu hỏi:** Có cần transaction không?

**Đáp án:** Có transaction phù hợp cho pessimistic locking.

### Bài 5 — Tenant query

Viết JPQL lấy item theo ID và tenant được phép, kèm lock.

**Gợi ý:** `select i from InventoryItem i where i.id=:id and i.tenantId=:tenant`, `setLockMode(PESSIMISTIC_WRITE)`.

### Bài 6 — Vi phạm status

Transaction khóa Item và thấy `SUSPENDED`.

**Gợi ý:** Từ chối reserve, không cố sửa status để lách điều kiện trừ khi workflow có quyền transition riêng.

### Bài 7 — Domain method

Viết `reserve(int q)` kiểm tra q dương, status ACTIVE và đủ stock.

**Gợi ý:** Đặt invariant trong entity/domain object; service phụ trách lock và transaction.

### Bài 8 — Rollback khi reservation INSERT lỗi

Stock đã giảm trong managed entity, nhưng INSERT Reservation vi phạm UNIQUE constraint.

**Đáp án:** Phải rollback cả transaction, stock không được commit bị trừ.

### Bài 9 — Lock ở repository nhưng cập nhật ngoài transaction

**Câu hỏi:** Có đúng không?

**Gợi ý:** Không; phần lock→validate→write cần cùng transaction boundary.

### Bài 10 — Spring self-invocation

Method `@Transactional` được gọi bằng `this.reserve()` từ cùng bean.

**Gợi ý:** Với Spring proxy strategy, advice có thể không được áp dụng; điều chỉnh service boundary.

### Bài 11 — Order picking

Hai workers cùng muốn chuyển Order PAID thành PICKING và REFUND_PENDING.

**Gợi ý:** Lock Order, đọc status dưới lock, chỉ thực hiện transition hợp lệ.

### Bài 12 — Chỉ một field

Đổi status PAID→PICKING và không có domain logic bổ sung.

**Gợi ý:** Atomic conditional UPDATE có thể đủ, không nhất thiết SELECT FOR UPDATE trước.

### Bài 13 — Hai accounts

A chuyển Account#10→#20, B chuyển #20→#10.

**Gợi ý:** Khóa theo thứ tự ID tăng dần để giảm deadlock.

### Bài 14 — Quota counter

Sự kiện còn 1 chỗ, hai requests đặt 1 chỗ.

**Gợi ý:** Lock hoặc atomic update đúng EventCapacity row, validate remaining dưới lock.

### Bài 15 — Quota count nhiều rows

Tính COUNT(reservations)=99 rồi hai transactions cùng INSERT.

**Gợi ý:** Khóa một reservation row không bảo vệ predicate; cần guard counter/constraint/SERIALIZABLE.

### Bài 16 — Booking chưa tồn tại

Hai requests cùng tạo booking cho một slot.

**Đáp án:** UNIQUE/constraint đúng business key thường là bảo vệ tự nhiên; lock trên row chưa tồn tại không portable.

### Bài 17 — State do client gửi

Client báo Order đang PAID, DB dưới lock hiện CANCELLED.

**Gợi ý:** Tin DB state đã được kiểm tra; từ chối ship.

### Bài 18 — em.lock và state cũ

Entity đã managed trước khi lấy lock.

**Gợi ý:** Không mặc định em.lock refresh state; cân nhắc load-with-lock hoặc refresh đúng chỗ.

### Bài 19 — PESSIMISTIC_READ

Đang chuẩn bị sửa chính row InventoryItem.

**Gợi ý:** `PESSIMISTIC_WRITE` thể hiện ý định read-modify-write rõ hơn.

### Bài 20 — FORCE_INCREMENT

Muốn khóa root và yêu cầu version tiến lên dù không đổi root fields.

**Gợi ý:** `PESSIMISTIC_FORCE_INCREMENT` với versioned entity, hiểu phạm vi lock.

### Bài 21 — Nested associations

Lock Order, Customer thay đổi credit limit đồng thời.

**Gợi ý:** Order lock không tự bảo vệ Customer; xác định strategy cho Customer/credit resource.

### Bài 22 — Idempotency

Hai requests cùng requestKey, chạy tuần tự dưới lock.

**Gợi ý:** Lock không nhận diện duplicates; dùng unique key và stored outcome.

### Bài 23 — Trùng key khác payload

Cùng requestKey nhưng một request reserve(2), một reserve(5).

**Gợi ý:** Không trả idempotent success mù quáng; kiểm tra payload fingerprint/conflict.

### Bài 24 — Payment API

Service định gọi payment provider trong lúc giữ InventoryItem lock.

**Gợi ý:** Tách transaction ngắn, pending reservation/outbox, payment idempotent ngoài lock.

### Bài 25 — Lock timeout

Không lấy được lock, có kết luận “item hết hàng” không?

**Đáp án:** Không; chưa kiểm tra thành công current stock. Xử lý error transient.

### Bài 26 — Fallback không khóa

Nếu `PessimisticLockException`, service chuyển sang `find` thường.

**Gợi ý:** Sai; bỏ concurrency guarantee.

### Bài 27 — Retry

Một attempt gặp deadlock; nên chạy lại phép tính đã thực hiện từ balance cũ?

**Gợi ý:** Không. Transaction mới, reload/recheck và tính toán lại.

### Bài 28 — Database CHECK

Có lock và domain check nhưng database không có `CHECK available>=0`.

**Gợi ý:** Constraint là defense-in-depth chống writers ngoài workflow; cân nhắc thêm.

### Bài 29 — Bulk UPDATE

JPQL giảm số lượng trực tiếp, entity có `@Version`.

**Gợi ý:** Bulk DML không tự dùng entity-level version handling; thiết kế manual increment/check và tránh stale context.

### Bài 30 — Lock nhiều IDs

Cart gồm item 42, 10, 99.

**Gợi ý:** Sắp xếp IDs rồi khóa theo thứ tự nhất quán; gộp quantities của IDs trùng.

### Bài 31 — Hot row

Một sản phẩm được hàng nghìn requests cùng reserve.

**Gợi ý:** Đo lock waits, throughput, atomic UPDATE/partitioning; không mặc định lock lâu là tối ưu.

### Bài 32 — Lock scope

`JOIN FETCH o.lines` và `setLockMode(PESSIMISTIC_WRITE)`.

**Câu hỏi:** Có chắc mọi Line đã được write-lock không?

**Đáp án:** Không nên mặc định; fetch và lock scope khác nhau, phụ thuộc JPA/provider/database.

### Bài 33 — Test concurrency

Item còn 5, A/B cùng reserve(4).

**Gợi ý:** Dùng hai EntityManager/transactions, latches và verify kết quả cuối trong context mới.

### Bài 34 — Đọc dưới lock sau khi chờ

A chuyển ACTIVE→SUSPENDED, B chờ lock rồi reserve.

**Gợi ý:** B phải từ chối vì status hiện hành SUSPENDED.

### Bài 35 — Trạng thái vừa đổi theo hướng có lợi

A restock từ 1→10, B chờ lock muốn reserve(5).

**Gợi ý:** Nếu semantics cho phép, B có thể thành công sau revalidation; “đã chờ” không tự là lỗi nghiệp vụ.

### Bài 36 — Permission mutable

User đã có role hợp lệ, nhưng Account bị FROZEN trong thời gian chờ lock.

**Gợi ý:** Authentication có thể làm trước; state Account/FROZEN phải kiểm tra theo đúng concurrency strategy.

### Bài 37 — External notification

Transaction cập nhật stock rồi gửi email trước commit, sau đó rollback.

**Gợi ý:** Email không rollback; dùng outbox/after-commit có độ bền phù hợp.

### Bài 38 — Lock wait metrics

Sau deploy, lỗi oversell giảm nhưng latency p99 tăng.

**Gợi ý:** Đo thời gian giữ khóa, lock waits, hot keys, connection pool; tối ưu transaction hoặc đổi sang atomic UPDATE.

### Bài 39 — Serializable

Có thể dùng SERIALIZABLE để bảo vệ invariant nhiều rows?

**Gợi ý:** Có thể phù hợp với thiết kế và retry serialization failures; không coi nó là cơ chế không bao giờ rollback.

### Bài 40 — API outcome

Lock timeout và InsufficientStockException nên được trả giống nhau?

**Gợi ý:** Không mặc định; một bên là concurrency infrastructure/transient, bên kia là business rejection.

## 46. Checklist thiết kế thực tế

Trước khi merge một service sử dụng pessimistic locking, hãy xác định:

- [ ] Business invariant được phát biểu rõ.
- [ ] Resource/row được khóa thật sự đại diện state mà invariant phụ thuộc.
- [ ] Input validation độc lập với DB được thực hiện trước khi lấy lock.
- [ ] Lock được lấy **trước** khi đọc/ra quyết định trên state cạnh tranh.
- [ ] Business validation được thực hiện lại dưới lock/current state.
- [ ] Mutation và các DB records liên quan thuộc cùng transaction.
- [ ] Transaction boundary có hiệu lực, không bị Spring self-invocation bypass.
- [ ] Domain methods bảo vệ state transitions và invariants cục bộ.
- [ ] Không có thao tác external I/O dài trong critical section.
- [ ] Khi cần nhiều locks, có thứ tự nhất quán giữa workflows.
- [ ] Tenant/authorization scope được áp đúng và không làm lộ thông tin.
- [ ] Có UNIQUE/FK/CHECK constraints phù hợp để bảo vệ ở DB.
- [ ] Những writers qua native SQL/batch jobs cũng tuân thủ concurrency contract.
- [ ] Pessimistic lock scope không bị nhầm với fetch graph.
- [ ] Không dùng state managed stale đã đọc trước khi lấy lock.
- [ ] Có timeout/deadlock/rollback policy; không fallback sang không khóa.
- [ ] Retry tạo transaction mới, reload và revalidate.
- [ ] Duplicate requests được xử lý bằng idempotency key/unique outcome.
- [ ] Notification/payment được thiết kế sau commit/outbox/reconciliation.
- [ ] Có integration tests hai transactions trên target database.
- [ ] Tests xác nhận final DB state, không chỉ số exception.
- [ ] Đo lock wait, transaction duration, hot rows và throughput hữu ích.
- [ ] Đã so sánh phương án atomic conditional DML và optimistic `@Version`.

## 47. Tổng kết

Những điểm cần ghi nhớ nhất:

1. **Khóa bi quan và kiểm tra điều kiện nghiệp vụ là hai trách nhiệm bổ sung cho nhau.** Khóa điều phối concurrency; domain validation quyết định thao tác có hợp lệ không.
2. **Thứ tự đúng là lấy khóa → đọc state được bảo vệ → kiểm tra lại → cập nhật → commit.**
3. **Không kiểm tra mutable DB state trước lock rồi dùng kết quả cũ** sau khi phải chờ một transaction khác.
4. **`PESSIMISTIC_WRITE` phù hợp cho read-modify-write nhiều bước**; dùng trong transaction ngắn với EntityManager/Query API phù hợp.
5. **Không phải mọi thao tác cần SELECT FOR UPDATE.** Một atomic conditional UPDATE có thể đơn giản và hiệu quả hơn khi invariant biểu diễn được trong một statement.
6. **`@Version` phát hiện stale writes khi conflict hiếm**; pessimistic lock có thể tốt hơn khi cần serialize quyết định hoặc retries quá tốn.
7. **Khóa phải đúng phạm vi invariant.** Khóa Order không tự bảo vệ CreditLimit, Inventory, ShippingCapacity hoặc các inserts chưa tồn tại.
8. **Đối với invariant nhiều rows**, có thể cần guard row, constraints, SERIALIZABLE isolation hoặc thiết kế aggregate rõ.
9. **UNIQUE constraints và idempotency vẫn cần thiết**, vì lock không tự nhận diện duplicate requests hoặc bảo vệ uniqueness khi chưa có row.
10. **Không giữ DB lock khi chờ user/payment/email**, và không nghĩ row lock có hiệu lực trên hệ thống ngoài database.
11. **Timeout/deadlock khác business rejection**; xử lý rollback, retry và thông báo theo nguyên nhân thực.
12. **Khi retry, phải bắt đầu transaction mới và đánh giá lại state**, không replay quyết định từ snapshot cũ.
13. **Kiểm thử concurrency bằng hai persistence contexts/transactions thật**, với fixture tranh chấp và kiểm tra state sau commit.
14. **Theo dõi lock waits, deadlocks và latency**, vì đúng dữ liệu nhưng giữ khóa quá lâu vẫn có thể làm hệ thống khó vận hành.

**Kết luận:** Kết hợp khóa bi quan với kiểm tra điều kiện nghiệp vụ trong JPA không đơn thuần là thêm `setLockMode(PESSIMISTIC_WRITE)` vào một truy vấn. Điều cốt lõi là xác định đúng **dữ liệu nào quyết định tính hợp lệ**, lấy lock trước khi dựa vào dữ liệu đó, **kiểm tra lại các điều kiện sau khi khóa được cấp**, rồi hoàn tất các thay đổi DB trong một transaction ngắn. Khi phối hợp thêm domain methods, database constraints, idempotency, retry và kiểm thử song song, ứng dụng có thể tránh các race condition gây oversell, state transition sai hoặc cập nhật thiếu nhất quán — mà không phải khóa mọi truy vấn một cách máy móc.
