# Lấy khóa qua find, lock và truy vấn có lock mode trong JPA

Trong ứng dụng Java Persistence API (JPA), nhiều transaction có thể đồng thời truy cập một bản ghi: hai khách hàng đặt chỗ cuối cùng, hai nhân viên cùng duyệt phiếu chi, nhiều worker cùng lấy một job, hoặc nhiều request cùng trừ số lượng tồn kho. Khi **đọc, kiểm tra và cập nhật** không được phối hợp, cả hai transaction có thể đưa ra quyết định dựa trên trạng thái cũ, dẫn đến đặt vượt khả năng phục vụ, thực thi trùng hay mất cập nhật.

**Khóa bi quan (pessimistic locking)** cho phép JPA yêu cầu database giữ khóa đối với entity được chọn trong một transaction. Bài này tập trung vào ba cách lấy khóa:

~~~java
// 1. Lấy khóa ngay khi tìm entity theo primary key.
SeatInventory s1 = em.find(
    SeatInventory.class, id,
    LockModeType.PESSIMISTIC_WRITE
);

// 2. Yêu cầu khóa trên một entity đã managed.
em.lock(s1, LockModeType.PESSIMISTIC_WRITE);

// 3. Lấy khóa qua một JPQL entity query.
SeatInventory s2 = em.createQuery(
        "SELECT s FROM SeatInventory s " +
        "WHERE s.id = :id AND s.tenantId = :tenantId",
        SeatInventory.class
    )
    .setParameter("id", id)
    .setParameter("tenantId", tenantId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();
~~~

Ba cách này đều dùng `LockModeType`, nhưng không hoàn toàn tương đương về **thời điểm đọc state**, **phạm vi tìm kiếm**, **điều kiện managed entity**, **cách truyền lock hints** và **rủi ro tranh chấp**. Cả ba phải nằm trong transaction phù hợp; database quyết định chi tiết locking theo isolation level, driver, dialect và JPA provider.

Mục tiêu của bài là sử dụng khóa **đúng nơi, đúng thời điểm, đúng phạm vi**, chứ không phải thêm `PESSIMISTIC_WRITE` vào mọi câu SELECT. Nội dung gồm ba pessimistic lock modes, ví dụ đầy đủ, so sánh API, lock timeout/scope, SQL `FOR UPDATE`, transaction boundary, Spring Data `@Lock`, deadlock, retry, testing hai transaction và các anti-pattern.

## 1. Bài toán: Hai request cùng thấy một chỗ trống

Giả sử hệ thống có:

~~~text
seat_inventory
id  event_id  available  version
21  9001      1          5
~~~

Hai transaction xử lý:

~~~text
Transaction A                     Transaction B
--------------------------------  --------------------------------
Đọc available = 1
                                  Đọc available = 1
Kiểm tra còn chỗ: đúng            Kiểm tra còn chỗ: đúng
Tạo Reservation A                 Tạo Reservation B
Đặt available = 0                 Đặt available = 0
COMMIT                            COMMIT
~~~

Nếu code không có concurrency control phù hợp, có thể tạo **hai reservations cho một chỗ**, ngay cả khi giá trị `available` cuối cùng bằng 0. Đây không chỉ là lỗi một field; nó là lỗi **invariant giữa tồn kho và số booking đã được chấp nhận**.

Một cách xử lý dùng pessimistic lock:

~~~text
Transaction A                     Transaction B
--------------------------------  --------------------------------
BEGIN                             BEGIN
find(id, PESSIMISTIC_WRITE)
-> lấy row lock
                                  find(id, PESSIMISTIC_WRITE)
                                  -> chờ A nhả khóa
Kiểm tra available = 1
Tạo Reservation A
available = 0
COMMIT -> nhả lock
                                  Khi được tiếp tục:
                                  kiểm tra available mới
                                  0 -> từ chối tạo Reservation B
                                  ROLLBACK/COMMIT theo workflow
~~~

Trên nhiều database quan hệ, locking read tương ứng `SELECT ... FOR UPDATE` hoặc một cơ chế khác. JPA mô tả **semantics**, không buộc provider sinh đúng một SQL statement duy nhất.

**Điểm mấu chốt:** kiểm tra trạng thái sau khi đã có cơ chế locking thích hợp, rồi thực hiện tất cả thay đổi liên quan trong cùng transaction.

### 1.1. Vì sao chỉ dùng Java synchronized chưa đủ?

~~~java
synchronized (this) {
    inventory.reserveOne();
}
~~~

`synchronized` chỉ phối hợp các thread dùng **cùng monitor trong một JVM**. Trong hệ thống nhiều instances/pods hoặc có batch job/database client khác, Java monitor không thể bảo vệ chung database rows. Pessimistic lock do DB thực hiện có thể điều phối những transactions của nhiều connections.

### 1.2. Lock không thay business validation

Dù có lock, service vẫn phải kiểm tra `available > 0`, quyền truy cập, trạng thái Event và điều kiện booking. Khóa bảo vệ ranh giới tranh chấp; nó không tự biết nghiệp vụ nào hợp lệ.

## 2. Pessimistic locking là gì?

Một pessimistic lock yêu cầu database hạn chế những thao tác đồng thời không tương thích trên dữ liệu được khóa cho tới khi transaction nhả khóa theo quy tắc DB.

Trên DB hỗ trợ SQL tương ứng:

~~~sql
BEGIN;

SELECT id, available, version
FROM seat_inventory
WHERE id = 21
FOR UPDATE;

UPDATE seat_inventory
SET available = 0
WHERE id = 21;

COMMIT;
~~~

Câu trên là **SQL minh họa**. Một provider có thể dùng các lock hints, câu SQL khác hoặc nhiều queries tùy DB.

### 2.1. Thời gian giữ khóa

Thông thường DB giữ transaction-scoped row lock tới khi `COMMIT` hoặc `ROLLBACK`. Việc EntityManager vẫn mở hay đã đóng không thay thế cách DB transaction giữ/nhả khóa; không giữ transaction mở dài chỉ vì phải serialize JSON hoặc chờ HTTP response từ dịch vụ khác.

### 2.2. Khóa không bảo đảm mọi SELECT đều bị chặn

Trên DB có MVCC, reader thực hiện SELECT không khóa có thể đọc committed snapshot trong khi transaction khác giữ `PESSIMISTIC_WRITE`. Vì vậy không nên nói “đã khóa row thì mọi request khác đều không đọc được”. Cơ chế bảo vệ cần tập trung vào **các đường ghi và locking reads tuân thủ cùng concurrency policy**.

### 2.3. Khóa một entity không khóa toàn hệ thống

Khóa `SeatInventory#21` không tự khóa mọi `Reservation`, `Payment`, `Event` hoặc các row có thể được insert sau này. Cần chọn tài nguyên đại diện cho invariant và buộc mọi writer liên quan tuân theo quy ước khóa; thêm constraint/transaction isolation khi cần.

## 3. Ba lock modes bi quan của JPA

| Lock mode | Mục đích | Tăng version chỉ vì lấy khóa? |
|---|---|---|
| `PESSIMISTIC_READ` | Bảo vệ việc đọc theo pessimistic semantics | Không |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa phù hợp với các thay đổi/ghi tranh chấp | Không tự force increment |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa bi quan đồng thời ép tăng phiên bản entity | Có, trên versioned entity |

### 3.1. PESSIMISTIC_READ

~~~java
em.find(
    Configuration.class, configId,
    LockModeType.PESSIMISTIC_READ
);
~~~

Hữu ích khi transaction muốn giữ trạng thái đọc ổn định trong lúc ra quyết định. Một số database có shared/read locks cho phép nhiều readers đồng thời, nhưng **JPA không cam kết PESSIMISTIC_READ luôn được hiện thực bằng một shared lock vật lý**. Nếu dialect không hỗ trợ read lock tương ứng, provider có thể sử dụng khóa mạnh hơn.

### 3.2. PESSIMISTIC_WRITE

~~~java
em.find(
    SeatInventory.class, id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Thường phù hợp với resource cần trừ số lượng, duyệt trạng thái hoặc ngăn writers khác tranh cùng row. SQL có thể tương ứng `SELECT ... FOR UPDATE`. Lock có thể khiến một transaction khác **chờ**, **timeout** hoặc **bị rollback do deadlock**.

### 3.3. PESSIMISTIC_FORCE_INCREMENT

~~~java
em.lock(
    order,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
~~~

Kết hợp pessimistic locking với yêu cầu **tăng version** trên versioned entity ngay cả khi root không có scalar field dirty. Ví dụ khi sửa `OrderLine` nhưng muốn `PurchaseOrder.version` đại diện cho revision của aggregate.

`PESSIMISTIC_FORCE_INCREMENT` khác `OPTIMISTIC_FORCE_INCREMENT`: mode đầu dùng pessimistic DB locking, mode sau là optimistic version check + increment.

### 3.4. Không đồng nhất WRITE với FORCE_INCREMENT

`PESSIMISTIC_WRITE` không tự tăng `@Version` chỉ vì đã lock. Nếu entity được cập nhật qua dirty checking, provider có thể tăng version do **cập nhật entity**, nhưng đó là semantics khác với yêu cầu force increment.

### 3.5. Chọn mode theo mục đích

- Chỉ đọc và cần giữ state ổn định: cân nhắc `PESSIMISTIC_READ`.
- Đọc để cập nhật một row có contention: thường chọn `PESSIMISTIC_WRITE`.
- Cần khóa bi quan và buộc version của root tăng dù root không dirty: `PESSIMISTIC_FORCE_INCREMENT`.
- Chỉ hiển thị dữ liệu cho UI: thường **không cần explicit pessimistic lock**.

## 4. Entity ví dụ: SeatInventory

~~~java
package com.example.booking.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "seat_inventory")
public class SeatInventory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "available", nullable = false)
    private int available;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected SeatInventory() {}

    public Long getId() { return id; }

    public Long getTenantId() { return tenantId; }

    public Long getEventId() { return eventId; }

    public int getAvailable() { return available; }

    public long getVersion() { return version; }

    public void reserveOne() {
        if (available <= 0) {
            throw new IllegalStateException(
                "No seats remaining"
            );
        }
        available -= 1;
    }
}
~~~

Schema SQL minh họa:

~~~sql
CREATE TABLE seat_inventory (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    available INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uk_seat_tenant_event
        UNIQUE (tenant_id, event_id),
    CONSTRAINT ck_available_nonnegative
        CHECK (available >= 0)
);

CREATE INDEX idx_inventory_tenant_event
    ON seat_inventory(tenant_id, event_id);
~~~

Chọn ID strategy, SQL identity syntax, constraint và index theo DB production. `@Version` vẫn hữu ích khi entity có những đường ghi theo optimistic locking; pessimistic `READ`/`WRITE` không đồng nghĩa entity bắt buộc phải versioned, nhưng `FORCE_INCREMENT` liên quan versioned entity.

## 5. Cách 1 — EntityManager.find với lock mode

Một overload của EntityManager:

~~~java
SeatInventory inventory = em.find(
    SeatInventory.class,
    inventoryId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Đây là lựa chọn đơn giản nhất khi đã biết **primary key**. Provider tìm hoặc lấy managed entity tương ứng và yêu cầu lock mode cho entity trong transaction.

### 5.1. Resource-local transaction hoàn chỉnh

~~~java
public void reserveById(
        EntityManagerFactory emf,
        long inventoryId) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        SeatInventory inventory = em.find(
            SeatInventory.class,
            inventoryId,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (inventory == null) {
            throw new NoSuchElementException(
                "Inventory not found"
            );
        }

        inventory.reserveOne();

        // Ghi Reservation cùng transaction khi nghiệp vụ yêu cầu.
        // em.persist(reservation);

        tx.commit();

    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackError) {
                failure.addSuppressed(rollbackError);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
~~~

Ở đây `inventory` là managed entity. Nếu nó dirty, JPA flush thay đổi theo transaction; **không cần `em.merge(inventory)` để lưu một entity đang managed**.

### 5.2. Phải mở transaction trước find có lock

Pessimistic lock yêu cầu transaction phù hợp. Nếu gọi `find(..., PESSIMISTIC_WRITE)` ngoài transaction, JPA có thể ném `TransactionRequiredException`. Việc `find` không có lock đôi khi chạy ngoài transaction không đồng nghĩa overload với lock cũng như vậy.

### 5.3. Khi find trả null

`find` trả `null` nếu không tồn tại row/entity theo ID. Đừng coi giá trị null là lock timeout; các trường hợp “không tồn tại”, “không đủ quyền”, “không còn chỗ” và “database đang khóa” phải được xử lý riêng.

### 5.4. Rủi ro khi biết ID nhưng cần tenant check

Một pattern:

~~~java
SeatInventory inventory = em.find(
    SeatInventory.class,
    userSuppliedId,
    LockModeType.PESSIMISTIC_WRITE
);

if (!inventory.getTenantId().equals(tenantId)) {
    throw new SecurityException("Forbidden");
}
~~~

có thể đã **giành khóa trên row của tenant khác** trước khi từ chối. Khi cần kiểm soát quyền truy cập ngay từ thao tác chọn row, một query có `WHERE tenantId = :tenantId` + `setLockMode` thường phù hợp hơn.

### 5.5. Overload find với properties

~~~java
SeatInventory inventory = em.find(
    SeatInventory.class,
    inventoryId,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of(
        "jakarta.persistence.lock.timeout", 2000
    )
);
~~~

Giá trị 2000 yêu cầu timeout 2.000 ms cho lock acquisition theo hint chuẩn Jakarta Persistence. Độ chính xác và việc hint có được áp dụng phụ thuộc provider/DB, cần integration test.

### 5.6. Có thể kết hợp lock scope

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    "jakarta.persistence.lock.timeout", 2000
);

properties.put(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);

SeatInventory inventory = em.find(
    SeatInventory.class,
    inventoryId,
    LockModeType.PESSIMISTIC_WRITE,
    properties
);
~~~

`EXTENDED` không làm phép màu khóa toàn object graph; phần lock scope sẽ được giải thích riêng.

## 6. Cách 2 — EntityManager.lock với entity managed

Nếu entity đã được tải:

~~~java
SeatInventory inventory =
    em.find(SeatInventory.class, inventoryId);

em.lock(
    inventory,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

`em.lock` không phải thao tác tìm entity theo ID. Nó yêu cầu lock trên một **managed instance hiện tại**, ví dụ khi service chỉ đến một bước nhất định mới cần exclusive access.

### 6.1. Managed là điều kiện cần

~~~java
SeatInventory detached =
    loadFromPreviousClosedEntityManager();

em.lock(
    detached,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

không phải cách attach lại entity detached. JPA có thể ném `IllegalArgumentException` nếu object không managed bởi `em` hiện tại. Với transaction mới, tải lại managed entity bằng `find` hoặc JPQL entity query.

### 6.2. Lấy lock sau khi đọc có thể quá muộn

~~~text
A: em.find() -> available=1, chưa lock
B: cập nhật available=0, COMMIT
A: em.lock(entity, PESSIMISTIC_WRITE)
A: quyết định dựa vào available=1 đã đọc trước đó
~~~

Yêu cầu lock tại A **không mặc định có nghĩa mọi field Java đã được làm mới**. Với entity versioned, provider có thể phát hiện conflict do stale version; nhưng không dựa vào điều đó như một lời hứa refresh dữ liệu.

Vì vậy:

- Nếu biết ngay sẽ cần write lock, **lấy khóa khi find/query**.
- Nếu đã load trước lock, **đánh giá lại business condition sau khi có state mới hợp lệ**.
- Khi cần refresh managed entity, cân nhắc `EntityManager.refresh(entity, lockMode)`, với cảnh báo mất pending changes.

### 6.3. Refresh và lock khác nhau

~~~java
em.lock(inventory, LockModeType.PESSIMISTIC_WRITE);
~~~

áp lock mode.

~~~java
em.refresh(
    inventory,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

yêu cầu tải lại state và áp lock mode. `refresh` có thể ghi đè state chưa flush, nên không dùng sau khi đã sửa entity mà chưa quyết định giữ/hủy pending changes.

### 6.4. Overload lock có properties

~~~java
em.lock(
    inventory,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 1500)
);
~~~

Với Spring/JTA, transaction manager phải đang giữ transaction hợp lệ; `em.lock` ngoài transaction không nên được coi là cách bảo vệ một command.

### 6.5. getLockMode

~~~java
LockModeType mode =
    em.getLockMode(inventory);
~~~

cho biết lock mode gắn với managed entity theo JPA trong context phù hợp. Nó **không phải công cụ quan sát database row locks** hay số transaction đang chờ. Khi cần chẩn đoán DB, dùng các views/metrics tương ứng DB.

## 7. Cách 3 — JPQL Query.setLockMode

Khi cần tìm theo **business key** hoặc kết hợp tenant/status, dùng query:

~~~java
TypedQuery<SeatInventory> query = em.createQuery(
    """
    SELECT s
    FROM SeatInventory s
    WHERE s.tenantId = :tenantId
      AND s.eventId = :eventId
    """,
    SeatInventory.class
);

SeatInventory inventory = query
    .setParameter("tenantId", tenantId)
    .setParameter("eventId", eventId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();
~~~

### 7.1. Lợi ích của query có khóa

- Lọc tenant **trước khi yêu cầu khóa** theo query semantics.
- Có thể filter theo status, eventId, owner hoặc các thuộc tính domain.
- Không cần biết physical primary key.
- Query có thể trả một hoặc nhiều entity.
- Lock mode nằm tại repository method diễn đạt rõ operation.

### 7.2. getSingleResult vs getResultList

Nếu có unique constraint trên `(tenant_id, event_id)`, `getSingleResult()` có thể phù hợp. Nếu không tìm thấy, JPA có thể ném `NoResultException`; nếu có nhiều rows, `NonUniqueResultException`.

Khi query chọn nhiều entities, dùng `getResultList()` và giới hạn phạm vi lock. Không thực hiện `SELECT s FROM SeatInventory s` + `PESSIMISTIC_WRITE` trên hàng triệu rows chỉ để xử lý một Event.

### 7.3. Query.setHint

~~~java
SeatInventory inventory = em.createQuery(
        """
        SELECT s FROM SeatInventory s
        WHERE s.id = :id
          AND s.tenantId = :tenantId
        """,
        SeatInventory.class
    )
    .setParameter("id", inventoryId)
    .setParameter("tenantId", tenantId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setHint(
        "jakarta.persistence.lock.timeout",
        2000
    )
    .getSingleResult();
~~~

Tên hint như trên thuộc Jakarta Persistence; ở JPA 2.x dùng namespace cũ `javax.persistence.lock.timeout`. Dùng tên tương ứng stack, và không giả định provider hỗ trợ mọi hint value.

### 7.4. Không đặt lock trên scalar/DTO query một cách tùy tiện

~~~jpql
SELECT COUNT(s)
FROM SeatInventory s
WHERE s.available > 0
~~~

trả Long, không phải entity result để JPA khóa giống một SELECT entity. Tương tự, constructor DTO projection không tự đại diện cho những managed entities cần khóa.

Nếu cần lock entity để bảo vệ quyết định, query entity với lock mode riêng, rồi mới tạo DTO khi cần. Không dùng `setLockMode` với bulk UPDATE/DELETE query như một locking SELECT.

### 7.5. Query có JOIN

~~~java
PurchaseOrder order = em.createQuery(
        """
        SELECT o FROM PurchaseOrder o
        JOIN FETCH o.customer
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();
~~~

`JOIN FETCH` yêu cầu tải association; **không đồng nghĩa** JPA tự khóa mọi association target với cùng strength. Phạm vi lock và khả năng sinh SQL có thể phụ thuộc provider/dialect.

## 8. Query.setLockMode với Criteria API

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<SeatInventory> cq =
    cb.createQuery(SeatInventory.class);

Root<SeatInventory> root =
    cq.from(SeatInventory.class);

cq.select(root);
cq.where(
    cb.equal(root.get("tenantId"), tenantId),
    cb.equal(root.get("eventId"), eventId)
);

TypedQuery<SeatInventory> query =
    em.createQuery(cq);

query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

SeatInventory inventory =
    query.getSingleResult();
~~~

Criteria phù hợp khi filter được xây động hoặc muốn dùng static metamodel. Lock semantics vẫn là JPA pessimistic entity query, không phải một loại khóa mới.

## 9. Một service Spring hoàn chỉnh: Reserve chỗ

~~~java
@Service
public class BookingService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserve(
            long authenticatedTenantId,
            long eventId,
            long userId) {

        SeatInventory inventory = em.createQuery(
                """
                SELECT s FROM SeatInventory s
                WHERE s.tenantId = :tenantId
                  AND s.eventId = :eventId
                """,
                SeatInventory.class
            )
            .setParameter(
                "tenantId", authenticatedTenantId
            )
            .setParameter("eventId", eventId)
            .setLockMode(
                LockModeType.PESSIMISTIC_WRITE
            )
            .getSingleResult();

        inventory.reserveOne();

        // Tạo reservation record trong transaction.
        // Gắn userId, eventId, tenantId, idempotency key.
        // em.persist(reservation);
    }
}
~~~

### 9.1. Thứ tự đúng

~~~text
@Transactional
    |
    v
Query có PESSIMISTIC_WRITE
    |
    +-- DB cấp khóa / chờ / lỗi
    |
    v
Kiểm tra available sau khi được phục vụ
    |
    v
Giảm available + ghi Reservation
    |
    v
Flush / COMMIT
    |
    v
Nhả DB lock
~~~

### 9.2. Lock không tự tạo reservation

`reserveOne()` giảm counter nhưng phải còn thao tác ghi reservation và constraint liên quan. Nếu tạo reservation ở transaction khác, có thể làm dữ liệu không nhất quán. Invariant phải được bảo vệ trọn vẹn trong transaction hoặc workflow phù hợp với tài nguyên phân tán.

### 9.3. Lock không tự chống request trùng

Client có thể retry cùng request hai lần. Pessimistic lock chỉ serialize chúng, không tự biết cả hai là cùng một lệnh. Cần idempotency key và unique constraint hoặc chính sách tương đương.

### 9.4. Authenticated tenantId phải đáng tin cậy

Không lấy tenantId tùy ý do client gửi và coi như có quyền. Security context/service authorization phải cấp phạm vi truy cập; query `WHERE tenantId` là một phần kiểm soát, không thay thế authentication/authorization đầy đủ.

## 10. Transaction là điều kiện bắt buộc

Pessimistic lock phụ thuộc transaction để database có phạm vi giữ khóa rõ.

Với RESOURCE_LOCAL:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // find/lock/query with PESSIMISTIC_WRITE
    // validate and update

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Với Spring/JTA, không tự gọi `em.getTransaction()` trên JTA EntityManager; để framework/container quản lý.

### 10.1. @Transactional bao trùm cả use case

Một repository `@Lock` có thể lấy khóa trong một transaction ngắn, nhưng nếu service thực hiện business validation/update **sau khi transaction repository kết thúc**, lock có thể đã được nhả.

Transaction service cần bao trùm **query có khóa → kiểm tra → thay đổi → commit**.

### 10.2. @Transactional(readOnly=true) không phù hợp với write flow

Một service định giảm inventory phải chạy trong transaction cho phép ghi. Tùy DB/transaction manager/provider, read-only có thể từ chối DML hoặc làm flush behavior khác kỳ vọng.

### 10.3. Self-invocation trong Spring

Với proxy-based `@Transactional`, một method gọi method khác trong cùng bean có thể bỏ qua transaction interceptor. Nếu transaction không thực sự được mở, việc lấy lock có thể thất bại.

Tổ chức transaction boundary tại service method được gọi qua Spring proxy hoặc dùng TransactionTemplate/cơ chế thích hợp.

### 10.4. Không giữ khóa khi gọi HTTP external service

Nguy hiểm:

~~~text
BEGIN
SELECT FOR UPDATE inventory
HTTP request tới payment provider trong 10 giây
UPDATE inventory
COMMIT
~~~

Khóa bị giữ trong thời gian chờ network. Tốt hơn dùng quy trình reservation tạm, idempotency/outbox, payment state machine và transaction ngắn theo nghiệp vụ.

## 11. Lock timeout, query timeout và transaction timeout

Ba khái niệm khác nhau:

| Cấu hình | Giới hạn dự kiến |
|---|---|
| Lock timeout | Thời gian chờ giành khóa |
| Query timeout | Thời gian thực thi/trả kết quả query |
| Transaction timeout | Thời gian tồn tại của transaction |

JPA hint:

~~~java
query.setHint(
    "jakarta.persistence.lock.timeout", 1000
);
~~~

là yêu cầu chờ lock tối đa khoảng 1.000 ms nếu provider/DB hỗ trợ theo semantics tương ứng.

### 11.1. Timeout hint không phải bảo đảm chính xác

Một số provider/DB có thể bỏ qua hoặc triển khai timeout khác granularity. Không viết contract “chắc chắn trả sau đúng 1.000 ms” mà không kiểm chứng trên stack thực tế.

### 11.2. Fail fast hay chờ?

- Với một API tương tác, bounded wait hoặc fail fast có thể giữ latency dự đoán được.
- Với background job, có thể retry có backoff.
- Với booking/payment, phải phân biệt “đang bận” với “hết chỗ”.

### 11.3. NOWAIT và SKIP LOCKED

Một số database có:

~~~sql
SELECT ...
FROM job
WHERE status = 'PENDING'
FOR UPDATE NOWAIT;
~~~

hoặc:

~~~sql
SELECT ...
FROM job
WHERE status = 'PENDING'
FOR UPDATE SKIP LOCKED;
~~~

Các biến thể này hữu ích nhưng **không có LockModeType.SKIP_LOCKED portable trong JPA**. Provider extension hoặc native SQL cần tài liệu hóa, kiểm thử DB và thiết kế retry/fairness. Không mặc định `lock.timeout = 0` luôn tạo `NOWAIT` chính xác trên mọi provider.

## 12. Exceptions khi lấy khóa

JPA có một số loại exception quan trọng:

- `TransactionRequiredException`: thao tác yêu cầu transaction nhưng thiếu transaction hợp lệ.
- `IllegalArgumentException`: `em.lock` với entity không managed hoặc tham số không phù hợp.
- `LockTimeoutException`: failure do chờ khóa ở mức statement theo semantics đặc tả.
- `PessimisticLockException`: pessimistic lock failure làm transaction bị rollback theo semantics đặc tả.
- Các exception do DB/provider/Spring translation có thể bao bọc những lỗi này.

### 12.1. LockTimeoutException và PessimisticLockException

Khác biệt quan trọng là **trạng thái transaction sau lỗi**. Một statement-level lock timeout có thể không yêu cầu rollback toàn transaction theo JPA semantics; một pessimistic failure transaction-level thì phải rollback.

Nhưng behavior thực tế còn phụ thuộc DB/provider/transaction manager; không bắt exception rồi mặc định có thể tiếp tục commit mà không xác minh transaction state.

### 12.2. Ví dụ translate thành lỗi nghiệp vụ

~~~java
try {
    inventory = em.find(
        SeatInventory.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
} catch (LockTimeoutException ex) {
    throw new ResourceBusyException(
        "Inventory currently locked", ex
    );
}
~~~

`ResourceBusyException` là class minh họa. Không coi lock timeout là inventory hết hàng: hệ thống **chưa đọc được state current theo flow đã chọn**, không chứng minh available bằng 0.

### 12.3. Exception có thể lộ muộn

Một số lỗi trong transaction có thể xuất hiện khi flush hoặc commit, tùy SQL provider thực thi. Code phải xử lý lỗi tại transaction owner, không tuyên bố thành công chỉ vì `find` hoặc `lock` return.

### 12.4. Spring exception translation

Spring có thể chuyển exception JPA/provider thành loại của `DataAccessException` như pessimistic locking failure hoặc cannot acquire lock. Xây error policy theo tầng, kiểm tra root cause thay vì chỉ catch một tên class trên mọi môi trường.

## 13. Lock được nhả khi nào?

Trong transaction:

~~~text
BEGIN
  SELECT ... FOR UPDATE
  Validate
  UPDATE
COMMIT / ROLLBACK
    |
    v
DB giải phóng transaction locks
~~~

Không có API JPA `unlock(entity)` chung để nhả row lock giữa transaction theo cách portable.

### 13.1. em.clear() không phải unlock

~~~java
em.clear();
~~~

detach managed entities khỏi persistence context, nhưng không commit/rollback transaction và không phải lệnh nhả database locks.

### 13.2. em.detach() cũng không phải unlock

Detach một object không bảo đảm transaction lock được nhả. Lock lifecycle thuộc DB/transaction.

### 13.3. em.flush() không nhả khóa

Flush đồng bộ pending changes xuống DB trong transaction; lock thường còn tới transaction end. Không gọi flush với kỳ vọng giải phóng contention.

### 13.4. Query result đóng lại cũng không tự commit

Hoàn thành `getResultList()`/`getSingleResult()` không kết thúc transaction. Lập kế hoạch transaction ngắn đủ bảo vệ invariant.

## 14. SQL SELECT FOR UPDATE và MVCC

SQL minh họa trên DB hỗ trợ:

~~~sql
SELECT id, available
FROM seat_inventory
WHERE id = 21
FOR UPDATE;
~~~

### 14.1. Provider có thể dùng SQL khác

Các database có cú pháp row lock hints khác nhau, và provider có thể dùng additional query hoặc lock hints. Đừng phụ thuộc vào một log SQL của Hibernate để suy ra mọi JPA provider sẽ sinh như vậy.

### 14.2. SELECT bình thường có thể không chờ write lock

Với MVCC, reader không khóa có thể nhìn thấy committed snapshot; writer khác muốn update/lock cùng row có thể phải chờ. Không thiết kế business dựa trên giả định mọi reader đều bị khóa.

### 14.3. UPDATE bản thân cũng có DB locking

Một JPQL/SQL UPDATE có thể đụng row locks dù không gọi `setLockMode`. Pessimistic SELECT lock được dùng khi **cần giành quyền kiểm soát trước khi kiểm tra nghiệp vụ**, không phải vì SQL UPDATE vốn không có locking.

### 14.4. SELECT FOR SHARE có thể không tồn tại trên mọi DB

Với `PESSIMISTIC_READ`, một số dialect dùng shared lock, một số dùng mạnh hơn. Hãy đo tác động lên đồng thời đọc/ghi.

## 15. Lock scope: NORMAL và EXTENDED

JPA có:

~~~java
PessimisticLockScope.NORMAL
PessimisticLockScope.EXTENDED
~~~

Có thể truyền qua hint:

~~~java
query.setHint(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);
~~~

### 15.1. NORMAL

Phạm vi thường tập trung vào database rows biểu diễn entity được khóa, bao gồm những rows liên quan mapping inheritance/secondary tables theo yêu cầu JPA. Với entity đơn giản trên một bảng, dễ hình dung row lock.

### 15.2. EXTENDED

Mở rộng locking tới một số **join-table / collection-table rows** theo JPA semantics. Nó không có nghĩa:

- Mọi related entity row được khóa.
- Tất cả children trong object graph bị exclusive lock.
- Mọi phantom insert vào tập liên quan đều bị chặn.
- Transaction khác không thể tạo association mới trong mọi DB/isolation.

### 15.3. Phantom anomaly

Giả sử A khóa tập Reservation đã có, B tạo một Reservation mới cùng Event. Việc giữ khóa các entries hiện có không tự bảo đảm chặn mọi row mới thỏa điều kiện query. Nếu invariant là maximum capacity, một root inventory row và quy ước mọi reservation writers lock root, cộng constraint/conditional DML, thường rõ hơn.

### 15.4. Không nhầm FETCH với LOCK

`JOIN FETCH o.lines` tải collection, **không tự đặt cùng write lock lên mọi row con**. Nếu cần child locking, thiết kế query/lock convention cụ thể và kiểm thử SQL/DB.

## 16. Lock cùng JOIN, pagination và query phức tạp

Một số DB hạn chế `FOR UPDATE` với `DISTINCT`, `GROUP BY`, aggregate, outer joins hoặc pagination. Provider có thể dùng **follow-on locking** (lấy rows trước, thực thi lệnh khóa sau) hoặc báo lỗi nếu SQL không hỗ trợ.

### 16.1. Đừng khóa bảng lớn chỉ vì cần một row

~~~jpql
SELECT o FROM PurchaseOrder o
~~~

kèm `PESSIMISTIC_WRITE` có thể yêu cầu khóa rất nhiều orders. Thêm tenant/status/ID predicate và giới hạn phạm vi.

### 16.2. Fetch join to-many + pagination có vấn đề riêng

Một Order có nhiều Lines gây nhân SQL rows. Collection fetch join với `setMaxResults` có thể dẫn đến pagination trong memory hoặc SQL phức tạp, đặc biệt khi kết hợp locking. Nên phân trang root IDs và fetch dữ liệu theo scope phù hợp.

### 16.3. Job queue

Một worker query 10 Jobs trạng thái PENDING:

~~~java
TypedQuery<Job> query = em.createQuery(
    """
    SELECT j FROM Job j
    WHERE j.status = :pending
    ORDER BY j.createdAt, j.id
    """,
    Job.class
);

query.setParameter("pending", JobStatus.PENDING);
query.setMaxResults(10);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
~~~

Nhiều workers có thể tranh cùng các rows đầu tiên. Với DB hỗ trợ `SKIP LOCKED`, native SQL/provider-specific feature có thể là lựa chọn, nhưng phải hiểu fairness, starvation, retry và tính portable.

### 16.4. COUNT/DTO không phải locking query

Không đặt `setLockMode` lên `COUNT` rồi cho rằng mọi entity được đếm đã bị khóa. Muốn khóa, cần entity query/operation lock được hỗ trợ.

## 17. Deadlock: Khóa nhiều rows theo thứ tự ngược

Ví dụ chuyển tiền:

~~~text
Transaction A                      Transaction B
---------------------------------  --------------------------------
Lock Account #1                   Lock Account #2
Lock Account #2 -> chờ B          Lock Account #1 -> chờ A
           \                         /
            \---- deadlock cycle ---/
~~~

Database có thể phát hiện deadlock và rollback một transaction.

### 17.1. Chuẩn hóa thứ tự lấy khóa

~~~java
long firstId = Math.min(fromId, toId);
long secondId = Math.max(fromId, toId);

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
~~~

Giữ cùng thứ tự cho tất cả code paths giúp giảm nguy cơ deadlock.

### 17.2. Không bảo đảm tuyệt đối

Index locks, FK checks, triggers và các resources khác vẫn có thể tạo deadlock. Thứ tự nhất quán chỉ là biện pháp giảm rủi ro, không xóa mọi deadlock.

### 17.3. Xử lý sau deadlock

Rollback transaction thất bại; nếu retry phù hợp, mở **transaction và persistence context mới**, tải state mới và đánh giá lại business invariant. Không retry bằng cùng một EntityManager/transaction đã rollback-only.

### 17.4. Lock timeout khác deadlock

Lock timeout là chờ quá lâu theo chính sách; deadlock là chu trình phụ thuộc locks giữa nhiều transactions. Cả hai có thể làm request thất bại nhưng có nguyên nhân và cách giảm khác nhau.

## 18. Pessimistic vs optimistic locking

### 18.1. Optimistic

Entity `@Version` có thể phát hiện conflict khi flush/commit, thường không cần giữ DB read lock dài. Phù hợp khi contention thấp và retry/refresh là chấp nhận được.

### 18.2. Pessimistic

Chủ động giữ khóa để điều phối updates trên resource. Phù hợp khi transaction có quyết định đọc–ghi quan trọng, contention cao hoặc chi phí retry của bước logic lớn.

### 18.3. Bảng so sánh

| Tiêu chí | Optimistic | Pessimistic |
|---|---|---|
| Công cụ JPA | `@Version`, `OPTIMISTIC` | `PESSIMISTIC_READ/WRITE/FORCE_INCREMENT` |
| Chiến lược chính | Phát hiện xung đột | Điều phối truy cập bằng DB lock |
| Khi conflict | Version conflict/rollback | Wait/timeout/deadlock/rollback |
| Chi phí khi chỉ đọc | Thường thấp | Có thể gây lock contention |
| Form chỉnh sửa lâu | Thường phù hợp hơn | Không nên giữ DB lock xuyên user think time |
| Inventory tranh chấp mạnh | Có thể retry nhiều | Có thể phù hợp nếu transaction ngắn |
| Multi-row invariant | Cần thiết kế thêm | Cũng cần thiết kế thêm |
| Bảo đảm SERIALIZABLE toàn transaction | Không | Không tự động |

### 18.4. @Version vẫn hữu ích cùng PESSIMISTIC_WRITE

Version là concurrency token cho các đường cập nhật managed. Một entity có `@Version` có thể đồng thời hỗ trợ optimistic workflows và pessimistic workflows; không bắt buộc chọn một mode cho toàn ứng dụng.

## 19. PESSIMISTIC_FORCE_INCREMENT và aggregate root

Giả sử:

~~~text
PurchaseOrder #41 (version 12)
   |
   +-- OrderLine #7001
   +-- OrderLine #7002
~~~

Sửa `OrderLine.quantity` có thể không tự làm PurchaseOrder root dirty hoặc version root tăng, tùy ownership/mapping/provider.

Nếu business contract yêu cầu **bất kỳ thay đổi child nào cũng làm revision root tăng**, service có thể:

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);

// Sửa OrderLine trong cùng transaction.
~~~

### 19.1. Không nhầm với PESSIMISTIC_WRITE

`WRITE` không buộc version tăng chỉ vì đã lock. `FORCE_INCREMENT` biểu đạt rõ yêu cầu revision.

### 19.2. Mọi writers phải tuân theo quy ước

Nếu một native SQL job sửa child mà không tăng root.version hoặc không tuân thủ root lock, optimistic readers dựa vào version root có thể bỏ sót thay đổi. Cần phối hợp mọi đường ghi và database constraints.

### 19.3. Không dùng force increment cho read-only GET

Nếu chỉ xem Order mà vẫn tăng version, GET biến thành write workload, gây conflicts và làm cache churn. Sử dụng mode này chỉ khi domain cần revision change.

## 20. Spring Data JPA @Lock

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SeatInventoryRepository
        extends JpaRepository<SeatInventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        SELECT s FROM SeatInventory s
        WHERE s.tenantId = :tenantId
          AND s.eventId = :eventId
        """)
    Optional<SeatInventory> findForReservation(
        @Param("tenantId") Long tenantId,
        @Param("eventId") Long eventId
    );
}
~~~

Service:

~~~java
@Service
public class BookingService {

    private final SeatInventoryRepository repository;

    public BookingService(SeatInventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(long tenantId, long eventId) {

        SeatInventory inventory = repository
            .findForReservation(tenantId, eventId)
            .orElseThrow();

        inventory.reserveOne();
    }
}
~~~

### 20.1. @Lock không thay @Transactional

`@Lock` là annotation Spring Data dùng để gắn JPA lock mode vào repository query. Transaction ở service vẫn phải bao trùm query và business update để khóa không bị nhả giữa chừng.

### 20.2. Query hints trên repository

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "1000"
    )
)
@Query("""
    SELECT s FROM SeatInventory s
    WHERE s.id = :id
""")
Optional<SeatInventory> findForUpdate(
    @Param("id") Long id
);
~~~

Các imports liên quan:

~~~java
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;
~~~

Đây là Spring Data/Jakarta Persistence APIs. Provider/DB có thể không áp dụng timeout chính xác; kiểm thử lock contention trên DB target.

### 20.3. Đừng gắn @Lock lên findAll không kiểm soát

Một method trả rất nhiều entities với PESSIMISTIC_WRITE có thể khóa một tập row rộng. Đặt tên method theo use case, giới hạn filter rõ ràng, và tránh lock trên generic read endpoints.

## 21. Conditional UPDATE — Một phương án khác cho counter đơn giản

Nếu chỉ cần giảm available một đơn vị nếu lớn hơn 0:

~~~java
int changed = em.createQuery(
        """
        UPDATE SeatInventory s
        SET s.available = s.available - 1
        WHERE s.id = :id
          AND s.tenantId = :tenantId
          AND s.available > 0
        """
    )
    .setParameter("id", inventoryId)
    .setParameter("tenantId", tenantId)
    .executeUpdate();
~~~

Nếu `changed = 1`, thao tác bulk update ảnh hưởng một entity theo query semantics. Nếu bằng 0, không có row khớp (có thể sai ID/tenant hoặc hết chỗ).

### 21.1. Nó không tương đương entity lifecycle

JPQL bulk UPDATE:

- Không tự gọi callbacks của mỗi managed entity.
- Không tự đồng bộ persistence context có entity đó.
- Không tự quản lý `@Version` theo dirty checking thông thường.
- Vẫn cần transaction và constraint.
- Vẫn phải phối hợp Reservation creation trong cùng use case.

### 21.2. Conditional update vẫn chịu DB locking

Một SQL UPDATE sẽ dùng DB concurrency control. Không cho rằng “không gọi JPA lock mode” nghĩa là câu SQL có thể ghi mà không bao giờ chờ row lock.

### 21.3. Khi nào chọn phương án nào?

Với một biến đổi đơn giản, atomic conditional update có thể hiệu quả và ít round trip hơn. Khi cần đọc nhiều fields, áp domain method và ghi nhiều rows có quan hệ, pessimistic lock trên aggregate có thể dễ lý giải hơn. Đo thực tế và chọn theo invariant.

## 22. Ranh giới của khóa: Invariant liên bảng

Giả sử reservation cần:

- Event đang mở.
- Inventory.available dương.
- User chưa giữ vé trùng.
- Không vượt giới hạn theo Customer.
- Payment state hợp lệ.

Khóa `SeatInventory` bảo vệ counter, nhưng không tự bảo vệ Event/User/Payment state nếu những writers khác có thể thay chúng mà không tuân theo cùng strategy.

### 22.1. Chọn khóa đại diện cho invariant

Một aggregate root có thể là tài nguyên điều phối: mọi code path tạo Reservation phải khóa một row Inventory/Event tương ứng. Nhưng phải có policy được thực hiện đồng nhất.

### 22.2. Database constraints là lớp bảo vệ bổ sung

- `UNIQUE(user_id, event_id)` nếu mỗi user chỉ được giữ một chỗ.
- `CHECK(available >= 0)`.
- Foreign keys hợp lệ.
- Conditional state transitions.
- Idempotency key UNIQUE.

Constraint không thay service validation, nhưng giúp không có dữ liệu sai khi một writer bỏ quên lock convention.

### 22.3. Phantom inserts

Khóa những rows đang tồn tại không tự chặn mọi insert của rows mới thỏa điều kiện tương lai. Nếu phải bảo vệ một tập record, cân nhắc root counter lock, SERIALIZABLE/DB constraints hoặc cơ chế chuyên biệt.

## 23. Lock nhiều rows: Thứ tự và phạm vi

Nếu một service cần đồng thời khóa Event rồi Inventory, và service khác khóa Inventory rồi Event, có thể tạo deadlock. Thống nhất thứ tự tài nguyên trong mọi command.

### 23.1. Một transaction ngắn

Không làm các việc như render PDF, gửi email, truy vấn báo cáo lớn, HTTP payment request hoặc đợi người dùng trong khi giữ khóa.

### 23.2. Không khóa những rows không cần thiết

Một query có filter thiếu/chưa tối ưu có thể giữ nhiều locks; phân tích generated SQL, index và execution plan.

### 23.3. Nhiều transaction lồng nhau

Với Spring `REQUIRES_NEW`, outer transaction có thể vẫn giữ locks trong khi inner transaction chạy trên connection khác. Inner có thể chờ chính tài nguyên outer đang giữ. Không dùng propagation mới một cách vô thức để “giải phóng” khóa.

### 23.4. Khóa theo ID tăng dần

Với nhiều rows cùng type, sort IDs trước khi yêu cầu lock; nếu cần thứ tự xác định hơn, có thể khóa tuần tự trong service. Không giả định một JPQL `IN :ids ORDER BY id` luôn khóa row theo đúng thứ tự vật lý trên mọi DB.

## 24. Kiểm thử pessimistic locking với hai EntityManagers

Để kiểm tra thực sự có contention, dùng **hai transactions và hai EntityManagers/connections độc lập**. EntityManager không thread-safe.

### 24.1. Test scenario

Fixture:

~~~text
SeatInventory #21: available = 1
~~~

Hai transactions:

~~~text
A                                     B
------------------------------------  ---------------------------------
BEGIN
find(21, PESSIMISTIC_WRITE)
-> giữ lock
                                      BEGIN
                                      find(21, PESSIMISTIC_WRITE)
                                      -> chờ hoặc timeout
reserveOne()
COMMIT
                                      Khi được cấp lock:
                                      đọc/kiểm tra state phù hợp
                                      reserveOne() -> từ chối vì 0
                                      ROLLBACK/COMMIT thích hợp
~~~

Kết quả cần xác minh là không có hai reservations được commit khi chỉ còn một chỗ, và available không âm.

### 24.2. Dùng latches thay sleep cố định

Với JUnit/test harness, có thể dùng `CountDownLatch` để bảo đảm A đã lấy lock rồi mới cho B thử. Dùng `Future.get(timeout, ...)` hoặc framework test timeout để tránh CI treo khi lỗi DB.

~~~java
CountDownLatch aLocked = new CountDownLatch(1);
CountDownLatch releaseA = new CountDownLatch(1);

Future<?> first = executor.submit(() -> {
    EntityManager a = emf.createEntityManager();
    try {
        a.getTransaction().begin();

        SeatInventory seat = a.find(
            SeatInventory.class,
            seatId,
            LockModeType.PESSIMISTIC_WRITE
        );

        aLocked.countDown();
        releaseA.await();

        seat.reserveOne();
        a.getTransaction().commit();
    } finally {
        // Rollback active transaction khi cần.
        // Close EntityManager.
    }
});

// Trong thread điều phối:
aLocked.await();

// Khởi động transaction B độc lập:
// find(seatId, PESSIMISTIC_WRITE)
// Quan sát wait/timeout theo DB.
// releaseA.countDown();
// Verify state sau các transaction.
~~~

Đây là pseudocode minh họa đồng bộ; code chạy thật cần xử lý checked exceptions, `finally` giải phóng latch, rollback và đóng EntityManager, pool ít nhất hai connections, timeout hợp lý và assertions theo provider/DB.

### 24.3. Không dùng chung EntityManager cho hai thread

Dùng chung EM có thể tạo lỗi thread-safety hoặc identity map gây sai kết luận. Mỗi transaction phải có persistence context/connection phù hợp.

### 24.4. Dùng DB mục tiêu

H2 có thể khác PostgreSQL, MySQL, Oracle, SQL Server ở row locks, isolation, timeout, deadlocks và syntax. Các kiểm thử quan trọng nên dùng DB/dialect production hoặc môi trường tương đương.

### 24.5. Test rollback

A cập nhật inventory dưới lock rồi rollback. B tiếp tục và phải thấy trạng thái phù hợp với committed data; không chỉ nhìn object của A vì nó là state bị rollback trong transaction thất bại.

## 25. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `TransactionRequiredException` | Gọi lock ngoài transaction | Mở transaction bao trùm use case |
| `IllegalArgumentException` tại em.lock | Entity detached hoặc sai loại | Tải managed entity trong EM hiện tại |
| Lock có rồi vẫn dùng state cũ | Read trước lock, không refresh/revalidate | Lock sớm hoặc refresh + check lại |
| Hai booking cho một chỗ | Writer bỏ qua lock/idempotency | Thống nhất write policy + unique constraints |
| PESSIMISTIC_READ vẫn gây chờ lớn | Dialect/provider dùng lock mạnh | Đo DB behavior, giảm lock duration |
| GET list làm update chậm | Đặt PESSIMISTIC_WRITE trên read list | Bỏ lock không cần thiết |
| Request chờ quá lâu | Lock wait/transaction dài | Timeout bounded, transaction ngắn |
| Timeout bị coi thành hết hàng | Nhầm lỗi lock với trạng thái nghiệp vụ | Trả busy/retry riêng |
| Deadlock | Khóa nhiều rows theo thứ tự ngược | Thứ tự nhất quán, rollback/retry |
| @Lock repository không bảo vệ setter | Service xử lý ngoài transaction | Transaction boundary ở service |
| Read-only transaction không update | Transaction cấu hình không cho phép ghi | Dùng write transaction |
| COUNT query + lock bị lỗi | Không trả entity result | Query entity riêng khi cần lock |
| JOIN FETCH và lock sinh SQL lỗi | DB hạn chế FOR UPDATE trên JOIN | Điều chỉnh query và fetch/lock strategy |
| EXTENDED không chặn insert mới | Không bảo vệ phantom | Root lock/constraint/isolation |
| Lock timeout hint bị bỏ qua | DB/provider không hỗ trợ | Test và cấu hình provider-specific |
| FORCE_INCREMENT không tăng version tức thì | Provider trì hoãn SQL | Kiểm tra committed version |
| Native/bulk update phá version policy | Không đi JPA lifecycle | Đồng bộ concurrency strategy |
| Retry gây double payment | External side effect không idempotent | Outbox/idempotency key |
| Pool cạn connection | Nhiều transactions chờ khóa | Giảm critical section, đo waits |
| Test không thấy chờ | Một EM/transaction, không có contention thật | Hai connections/transactions |

## 26. Bài tập thực hành

### Bài 1. Lock theo ID

Đã có inventoryId, muốn trừ một chỗ sau khi kiểm tra.

**Đáp án:** `em.find(SeatInventory.class, inventoryId, PESSIMISTIC_WRITE)` trong transaction, sau đó check `available > 0` rồi cập nhật và commit.

### Bài 2. Entity đã managed

Entity được load trong cùng EntityManager và code muốn yêu cầu write lock.

**Đáp án:** `em.lock(entity, PESSIMISTIC_WRITE)`, nhưng phải xét state đã đọc trước khi lock có thể stale.

### Bài 3. Tìm theo tenant + business key

Chỉ biết tenantId và eventId.

**Đáp án:** JPQL entity SELECT có hai WHERE predicates, kết hợp `query.setLockMode(PESSIMISTIC_WRITE)`.

### Bài 4. Detached instance

Truyền entity từ EntityManager cũ đã close vào `em.lock` mới.

**Đáp án:** Không hợp lệ như một cách attach; tải managed entity lại trong current EM.

### Bài 5. No transaction

Gọi `find(... PESSIMISTIC_WRITE)` ngoài transaction.

**Đáp án:** Có thể nhận `TransactionRequiredException`; phải mở transaction phù hợp.

### Bài 6. Read trước lock

Đọc available=1, transaction khác giảm còn 0, sau đó mới gọi `em.lock`.

**Đáp án:** Có stale-state risk; cần giành lock trước khi kiểm tra, hoặc refresh có khóa rồi kiểm tra lại.

### Bài 7. READ có luôn là shared lock?

**Đáp án:** Không. Provider/DB có thể dùng exclusive lock để thực hiện semantics.

### Bài 8. WRITE có luôn tăng version?

**Đáp án:** Không chỉ vì lock. `PESSIMISTIC_FORCE_INCREMENT` mới yêu cầu tăng version cho versioned entity.

### Bài 9. @Lock và @Transactional

Spring repository có `@Lock` nhưng service không có transaction bao quanh xử lý.

**Đáp án:** Khóa có thể không được lấy đúng hoặc được nhả trước bước sửa; đặt transaction ở service.

### Bài 10. Timeout hint

`jakarta.persistence.lock.timeout = 1000`.

**Đáp án:** Là hint yêu cầu chờ khoảng 1 giây nếu được hỗ trợ, không bảo đảm chính xác trên mọi DB.

### Bài 11. SKIP LOCKED

Ứng dụng muốn worker khác bỏ qua jobs đang khóa.

**Đáp án:** Native SQL/provider-specific, không phải một `LockModeType.SKIP_LOCKED` portable.

### Bài 12. Deadlock

A khóa Account1 rồi Account2, B khóa Account2 rồi Account1.

**Đáp án:** Nguy cơ deadlock; thống nhất thứ tự khóa, retry có transaction mới và giới hạn.

### Bài 13. EXTENDED

**Đáp án:** Mở rộng scope tới một số join/collection rows; không tự khóa toàn graph hoặc chặn tất cả phantom inserts.

### Bài 14. SELECT không khóa trong MVCC

**Câu hỏi:** Có chắc reader bình thường bị chặn bởi PESSIMISTIC_WRITE không?

**Đáp án:** Không. DB có thể cho đọc committed snapshot cũ.

### Bài 15. Conditional UPDATE

Chỉ cần trừ counter nếu >0.

**Đáp án:** Cân nhắc atomic conditional UPDATE + affected row count; vẫn phải quản lý transaction, version, stale persistence context và Reservation.

### Bài 16. FORCE_INCREMENT cho GET

**Đáp án:** Thường không phù hợp: biến read thành write và gây version churn/lock contention.

### Bài 17. Query COUNT

Đặt PESSIMISTIC_WRITE trên `SELECT COUNT(s)`.

**Đáp án:** Không phải cơ chế khóa tập entity được đếm; cần entity query/lock operation phù hợp.

### Bài 18. Hai EntityManagers

**Câu hỏi:** Có thể dùng một EM trong hai threads để test row locks không?

**Đáp án:** Không. EntityManager không thread-safe; dùng hai transactions/contexts/connections độc lập.

### Bài 19. Rollback

A đã dùng PESSIMISTIC_WRITE, sửa available nhưng rollback.

**Đáp án:** Các thay đổi DB trong transaction có thể bị hoàn tác; locks được nhả khi transaction kết thúc theo DB semantics.

### Bài 20. Tenant scope

Service biết ID của row tenant khác và lock trước khi kiểm tra quyền.

**Đáp án:** Có thể chiếm lock ngoài quyền truy cập. Khi phù hợp, dùng query có tenant predicate trước khi yêu cầu lock.

## 27. Checklist trước khi triển khai

1. Tài nguyên tranh chấp có được xác định rõ không?
2. Có thật sự cần pessimistic locking thay vì optimistic/conditional update không?
3. Chọn `READ`, `WRITE` hay `FORCE_INCREMENT` đúng mục đích chưa?
4. Entity có version nếu dùng `FORCE_INCREMENT` không?
5. Transaction có được mở trước khi yêu cầu khóa không?
6. Transaction có bao trùm đọc, kiểm tra, sửa và commit không?
7. Nếu gọi `em.lock` sau khi đọc, đã xử lý state stale chưa?
8. Entity truyền vào `em.lock` có managed không?
9. Nếu cần refresh, có pending changes có thể bị mất không?
10. Query khóa đã lọc tenant và business key đúng chưa?
11. Có giới hạn số rows bị khóa không?
12. Có đặt lock mode lên entity SELECT thay vì scalar/DTO/bulk DML không?
13. Có phân biệt lock timeout, query timeout và transaction timeout không?
14. Timeout hint có được DB/provider áp dụng thực sự không?
15. Có hiểu rằng PESSIMISTIC_READ không chắc là shared lock vật lý không?
16. Có hiểu PESSIMISTIC_WRITE không chặn tất cả SELECT thường không?
17. Lock root có đủ bảo vệ invariant liên bảng không?
18. Nếu dùng EXTENDED, có hiểu join-table scope và phantom limitation không?
19. Có JOIN/pagination làm SQL locking phức tạp không?
20. Có external API khiến transaction giữ lock lâu không?
21. Nhiều resources được khóa theo thứ tự thống nhất không?
22. Có xử lý timeout, rollback, deadlock đúng không?
23. Retry có transaction mới, giới hạn và idempotency không?
24. Có CHECK/UNIQUE/FK để bảo vệ tính đúng cuối cùng không?
25. Spring Data `@Lock` có được gọi từ service transactional không?
26. Tất cả writers, kể cả native/bulk jobs, có tuân theo concurrency contract không?
27. Có test hai contexts/transactions độc lập không?
28. Có quan sát lock wait, P95 latency và pool pressure không?
29. Có test với DB target thay vì chỉ mock JPA không?
30. Có ghi rõ các tính năng DB-specific như NOWAIT/SKIP LOCKED không?

## 28. Tổng kết

~~~text
                  CẦN ĐIỀU PHỐI CẬP NHẬT ĐỒNG THỜI
                                 |
                                 v
                      Transaction đã mở?
                         /           \
                       Chưa          Rồi
                        |             |
                        v             v
                    Mở transaction   Chọn resource/row
                                      |
                          +-----------+-----------+
                          |           |           |
                          v           v           v
                     Biết PK      Đã managed    Cần filter
                          |           |           |
                          v           v           v
                        find       lock      query.setLockMode
                          |           |           |
                          +-----------+-----------+
                                      |
                                      v
                        DB cấp khóa/chờ/timeout
                                      |
                           +----------+----------+
                           |                     |
                         Có khóa              Thất bại
                           |                     |
                           v                     v
                   Đọc và kiểm tra         Rollback/retry policy
                   state phù hợp                 |
                           |                     |
                           v                     |
                   Sửa data trong transaction   |
                           |                     |
                           v                     |
                        COMMIT / ROLLBACK <-------+
                           |
                           v
                   Nhả locks theo DB
~~~

Các nguyên tắc cần ghi nhớ:

1. **Khóa bi quan là yêu cầu đồng bộ ở database trong transaction**, không phải Java `synchronized` và không thay thế kiểm tra nghiệp vụ.
2. **`EntityManager.find(..., lockMode)`** phù hợp khi biết primary key và muốn khóa ngay lúc tải entity.
3. **`EntityManager.lock(managed, lockMode)`** phù hợp khi entity đã managed, nhưng phải chú ý stale state nếu đã đọc trước khi lấy khóa.
4. **`Query.setLockMode(...)`** phù hợp khi cần lọc tenant, status hoặc business key và trả entity result.
5. **`PESSIMISTIC_READ` dùng cho trạng thái đọc; `PESSIMISTIC_WRITE` cho tranh chấp ghi; `PESSIMISTIC_FORCE_INCREMENT` thêm version increment trên versioned entity.**
6. **Transaction phải bao trùm lấy khóa → kiểm tra → thay đổi → commit**, không chỉ riêng repository query.
7. **Lock không phải refresh**; nếu state được tải trước lock, có thể cần refresh có khóa hoặc query lại theo cách phù hợp.
8. **SQL locking phụ thuộc DB/provider**; `FOR UPDATE`, NOWAIT, SKIP LOCKED và shared-read locks không portable tuyệt đối qua mọi dialect.
9. **Lock timeout hint cần được kiểm thử**, vì không phải mọi DB/provider đều tuân thủ chính xác.
10. **Khóa entity không tự bảo vệ mọi association hoặc phantom insert**, nên cần aggregate writer policy, constraints và isolation thích hợp.
11. **Deadlock, lock wait, rollback và retry là phần bình thường của thiết kế concurrency**; không để transaction giữ khóa quá lâu.
12. **Spring Data `@Lock` không thay `@Transactional`**, và controller không nên là nơi giữ transaction trong lúc render hoặc chờ network.
13. **Kiểm thử bằng hai EntityManagers/transactions độc lập trên DB mục tiêu** để chứng minh business invariant thực sự được bảo vệ.
14. **Không mặc định mọi use case cần PESSIMISTIC_WRITE**; optimistic version và conditional UPDATE có thể tốt hơn tùy mức độ tranh chấp.
15. **Theo dõi lock waits, throughput, timeout và lỗi contention** để đánh giá hiệu quả thực tế.

Sử dụng đúng ba API `find`, `lock` và `Query.setLockMode` không chỉ là thêm một hằng số `PESSIMISTIC_WRITE` vào code. Quan trọng hơn là xác định **entity/row đại diện cho tài nguyên tranh chấp, thời điểm cần khóa, trạng thái phải được kiểm tra sau khi có khóa và transaction sở hữu trọn vẹn thay đổi**. Khi các ranh giới đó rõ ràng, JPA pessimistic locking trở thành công cụ hữu ích để bảo vệ dữ liệu quan hệ khỏi những interleavings không phù hợp giữa nhiều request đồng thời.
