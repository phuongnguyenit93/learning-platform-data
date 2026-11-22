# Khóa bi quan khi tải hoặc truy vấn thực thể trong Hibernate

Trong ứng dụng nhiều người dùng, hai transaction có thể đọc cùng một bản ghi và đồng thời muốn thay đổi nó. Chẳng hạn một kho hàng chỉ còn **một** sản phẩm, nhưng hai yêu cầu đặt hàng cùng thấy số lượng `1`. Nếu cả hai cùng kiểm tra rồi trừ tồn kho mà không có cơ chế đồng thời phù hợp, hệ thống có thể bán vượt tồn kho hoặc ghi đè thay đổi của nhau.

Hibernate hỗ trợ **khóa bi quan (pessimistic locking)**: khi tải một entity hoặc chạy một truy vấn, ứng dụng yêu cầu database đặt khóa trên những hàng dữ liệu liên quan. Các transaction cạnh tranh phải chờ, bị từ chối hoặc bỏ qua hàng đã khóa (nếu sử dụng cơ chế phù hợp), thay vì cùng thay đổi dựa trên một snapshot cũ.

Ví dụ trọng tâm:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Lời gọi này không chỉ là “tải entity có ID `itemId`”: Hibernate còn yêu cầu **database lock** theo lock mode và dialect. Một SQL điển hình trong PostgreSQL là:

~~~sql
SELECT id, sku, available_quantity, version
FROM inventory_item
WHERE id = ?
FOR UPDATE;
~~~

Tuy nhiên, khóa bi quan **không tự tạo transaction, không tự commit, không phải Java `synchronized`, không thay thế ràng buộc database và không bảo đảm mọi query đều dùng đúng cú pháp `FOR UPDATE`**. Để áp dụng đúng, cần hiểu thời điểm lấy khóa, thời gian giữ khóa, các chế độ khóa, giới hạn về SQL và cách xử lý xung đột.

> **Phạm vi:** Ví dụ sử dụng Jakarta Persistence (`jakarta.persistence`), Hibernate ORM 6.x, PostgreSQL để minh họa SQL và một số so sánh với MySQL/Oracle/SQL Server. Hibernate 5 dùng `javax.persistence`. Cú pháp và cường độ khóa thực tế do Hibernate dialect, phiên bản database, transaction isolation, mapping và query shape quyết định. Các mẫu SQL là mô hình giải thích, không phải cam kết statement chính xác trên mọi hệ thống.

## 1. Vì sao khóa bi quan cần thiết?

Xét bảng tồn kho:

~~~text
inventory_item
+----+----------+--------------------+---------+
| id | sku      | available_quantity | version |
+----+----------+--------------------+---------+
| 42 | BOOK-001 |                  1 |       0 |
+----+----------+--------------------+---------+
~~~

Hai request bắt đầu gần như đồng thời:

~~~text
Transaction A                        Transaction B
---------------------------          ---------------------------
SELECT quantity -> 1                 SELECT quantity -> 1
Kiểm tra đủ hàng                      Kiểm tra đủ hàng
quantity = 0                         quantity = 0
UPDATE quantity=0                    UPDATE quantity=0
COMMIT                               COMMIT

Kết quả: cả hai request đều được thông báo đặt hàng thành công,
nhưng chỉ có một sản phẩm thật sự tồn tại.
~~~

Đây là ví dụ **check-then-act race**: điều kiện kiểm tra và thao tác cập nhật không được bảo vệ nhất quán trong cùng transaction. Nếu chỉ dựa vào giá trị đã đọc, hai request có thể đưa ra quyết định dựa trên dữ liệu không còn phù hợp.

Một hướng giải quyết là yêu cầu transaction muốn thay đổi tồn kho phải **khóa row trước khi kiểm tra và trừ**:

~~~text
Transaction A                        Transaction B
---------------------------          ---------------------------
SELECT ... FOR UPDATE
  -> khóa item #42
                                      SELECT ... FOR UPDATE
                                      -> chờ A nhả khóa
Đọc quantity=1
Trừ còn 0
UPDATE + COMMIT
  -> nhả khóa
                                      Tiếp tục đọc item #42
                                      -> quantity=0
                                      Từ chối đặt hàng
                                      ROLLBACK/COMMIT không đổi
~~~

Với isolation và mapping phù hợp, transaction B không quyết định dựa trên quantity cũ trước khi lấy được lock. Đó là lợi ích của khóa bi quan: **chuyển tranh chấp thành sự chờ đợi/không nhận được khóa tại thời điểm xác định**, thay vì để hai bên tự quyết định từ trạng thái không được bảo vệ.

### Nhưng đây không phải giải pháp duy nhất

Một atomic SQL update có điều kiện:

~~~sql
UPDATE inventory_item
SET available_quantity = available_quantity - 1
WHERE id = 42
  AND available_quantity >= 1;
~~~

cũng có thể giải quyết bài toán trừ tồn kho nếu application kiểm tra **số row bị ảnh hưởng** và transaction thiết kế đúng. Với trường hợp này, SQL atomic có điều kiện có thể gọn hơn việc đọc entity rồi khóa. Khóa bi quan phát huy giá trị khi cần **đọc nhiều thuộc tính, kiểm tra nhiều điều kiện và thao tác theo quy tắc nghiệp vụ** trong một ranh giới transaction.

## 2. Khóa bi quan khóa gì?

Thuật ngữ “khóa entity” trong JPA/Hibernate nên được hiểu là **yêu cầu database khóa các hàng dữ liệu đại diện cho entity** theo lock mode và SQL mà dialect hỗ trợ. Nó không có nghĩa JVM đặt một mutex lên object Java.

~~~text
Java Thread A -> EntityManager A -> Hibernate SQL -> DB Transaction A
                                                     |
                                                     +-- lock row inventory_item/42
                                                     |
Java Thread B -> EntityManager B -> Hibernate SQL -> DB Transaction B
                                                     |
                                                     +-- đợi / từ chối / skip
~~~

Các hệ quả:

- Hai `Session` ở **hai tiến trình ứng dụng khác nhau** vẫn có thể tranh chấp cùng DB row.
- Java `synchronized(item)` chỉ điều phối các threads dùng **đúng một monitor JVM**; nó không bảo vệ row ở những instances khác.
- Database quyết định lock compatibility, wait queues, deadlock detection, lock timeout và thời điểm nhả khóa.
- Trên DB dùng MVCC, một transaction giữ `FOR UPDATE` thường **không ngăn các plain SELECT** đọc một phiên bản đã commit; nó chủ yếu ngăn các thao tác **xung đột về khóa/ghi**. Không diễn giải “WRITE lock” là “mọi người khác không thể đọc”.
- Khóa được giữ theo **database transaction** cho đến commit/rollback theo semantics DB, không phải tự nhả ngay khi Java method `find()` trả về.

### Khóa row khác khóa bảng

`SELECT ... FOR UPDATE` thường lấy **row-level locks** đối với những row được chọn, nhưng DB cũng có thể giữ các table-level intention/relation locks cần thiết để thực hiện statement. Không nói “Hibernate chỉ khóa đúng một row và tuyệt đối không có lock nào khác”. Với query join, điều kiện lọc, index và dialect khác nhau, tập rows bị khóa có thể rộng hơn điều code Java mong muốn.

## 3. Các lock mode bi quan của Jakarta Persistence

JPA cung cấp ba giá trị chính:

| `LockModeType` | Mục tiêu | Ý nghĩa thường thấy |
|---|---|---|
| `PESSIMISTIC_READ` | Đọc row dưới chế độ khóa phù hợp, hạn chế các writers xung đột trong thời gian transaction. | Thường hướng tới **shared/read lock** khi DB hỗ trợ; provider có thể dùng khóa mạnh hơn khi cần. |
| `PESSIMISTIC_WRITE` | Dự kiến cập nhật hoặc bảo vệ quyết định dựa trên row trước các writers cạnh tranh. | Thường tương đương **exclusive row lock** như `SELECT ... FOR UPDATE`. |
| `PESSIMISTIC_FORCE_INCREMENT` | Lấy khóa bi quan và yêu cầu tăng version của entity versioned. | Dùng khi cần ghi nhận một thay đổi logic thông qua `@Version`, kể cả không sửa field thường. |

Hai nhóm khác không được nhầm:

| `LockModeType` | Nhóm | Khác biệt |
|---|---|---|
| `NONE` | Không yêu cầu entity lock cụ thể qua API này | Không bảo đảm database không lấy bất kỳ khóa nào trong quá trình đọc/ghi. |
| `OPTIMISTIC` | Optimistic locking | Thường dựa vào version check thay vì giữ row lock từ lúc tải. |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic locking có tăng version | Không tương đương yêu cầu pessimistic database row lock ngay từ lúc tải. |

JPA định nghĩa semantics ở tầng API; dialect có thể sử dụng các cú pháp SQL khác nhau hoặc cơ chế khóa thay thế. Nếu database không có shared lock phù hợp, `PESSIMISTIC_READ` có thể được hiện thực bằng khóa tương đương write/exclusive. **Không giả định PESSIMISTIC_READ luôn đồng thời tương thích giữa hai transaction trên mọi DBMS.**

## 4. Chuẩn bị entity và schema cho ví dụ

Entity tồn kho:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_item")
@SequenceGenerator(
    name = "inventory_gen",
    sequenceName = "inventory_item_seq",
    allocationSize = 1
)
public class InventoryItem {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "inventory_gen"
    )
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 80)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected InventoryItem() {}

    public InventoryItem(String sku, int initialQuantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (initialQuantity < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }
        this.sku = sku;
        this.availableQuantity = initialQuantity;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public int getAvailableQuantity() { return availableQuantity; }

    public void reserve(int units) {
        if (units <= 0) {
            throw new IllegalArgumentException("units must be positive");
        }
        if (availableQuantity < units) {
            throw new IllegalStateException("Not enough stock");
        }
        availableQuantity -= units;
    }
}
~~~

PostgreSQL DDL tương ứng:

~~~sql
CREATE SEQUENCE inventory_item_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_inventory_quantity
        CHECK (available_quantity >= 0)
);
~~~

Giả sử item `id=42` đã tồn tại. Database `CHECK` giúp chặn quantity âm, nhưng nó **không tự ngăn hai transactions cùng thông báo reservation thành công** nếu cả hai chỉ dựa trên read-check-update thiếu điều phối. Vì vậy cần thiết kế cả **transactional decision** lẫn **DB constraints**.

### Tại sao vẫn thêm `@Version`?

Khóa bi quan và optimistic locking **có thể cùng tồn tại**. `@Version` giúp phát hiện một số cập nhật cạnh tranh đi theo đường ORM khác hoặc kiểm tra stale version khi appropriate. Nó không thay thế nhu cầu tất cả writers tuân thủ transaction protocol, và `PESSIMISTIC_WRITE` không tự yêu cầu tăng version chỉ vì lock đã được lấy mà không có update. Phần sau so sánh hai cơ chế.

## 5. Khóa ngay khi `find()` entity

API JPA thường rõ ràng nhất khi biết khóa chính:

~~~java
import jakarta.persistence.LockModeType;

InventoryItem item = entityManager.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Đoạn này cần được gọi **trong transaction đang hoạt động**. Một luồng service quản lý bằng Spring:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final EntityManager entityManager;

    public InventoryService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void reserve(long itemId, int units) {
        InventoryItem item = entityManager.find(
            InventoryItem.class,
            itemId,
            LockModeType.PESSIMISTIC_WRITE
        );
        if (item == null) {
            throw new IllegalArgumentException("Item not found");
        }

        item.reserve(units);
        // Không cần gọi update() sau setter của managed entity.
        // Hibernate dirty checking flush thay đổi khi transaction commit.
    }
}
~~~

Thứ tự logic:

1. Transaction bắt đầu khi service method được gọi qua Spring transaction proxy đúng cách.
2. Hibernate tải `InventoryItem` và yêu cầu DB lock.
3. Khi đã lấy lock, application kiểm tra tồn kho và giảm quantity.
4. Hibernate flush update khi cần; database kiểm tra constraints/version.
5. Commit nhả khóa và xác nhận dữ liệu. Nếu exception làm rollback, lock cũng được giải phóng theo DB transaction.

### Vì sao không cần `flush()` ngay sau `reserve()`?

Lock được giữ ở database trong transaction; dirty checking và flush/commit sẽ đồng bộ field thay đổi theo JPA/Hibernate. Gọi flush sớm không làm khóa “mạnh hơn” hay nhả khóa sớm. Nếu vẫn tiếp tục giữ transaction mở, lock có thể tiếp tục bị giữ dù đã flush.

### Nếu không dùng Spring?

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    InventoryItem item = entityManager.find(
        InventoryItem.class,
        42L,
        LockModeType.PESSIMISTIC_WRITE
    );
    if (item == null) {
        throw new IllegalArgumentException("Missing inventory item");
    }
    item.reserve(1);
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
~~~

Ví dụ dùng application-managed `RESOURCE_LOCAL` transaction. Với JTA/container-managed hoặc Spring, không tự gọi `getTransaction().begin()/commit()` theo cách này.

## 6. Hai transaction cạnh tranh khi sử dụng PESSIMISTIC_WRITE

Giả sử tồn kho còn `1`, hai request cùng gọi `reserve(42, 1)`. Trong PostgreSQL và isolation phổ biến `READ COMMITTED`:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: SELECT item 42 FOR UPDATE
    DB-->>A: row + lock granted (qty=1)
    B->>DB: SELECT item 42 FOR UPDATE
    Note over B,DB: B chờ row lock của A
    A->>A: reserve(1) -> qty=0
    A->>DB: UPDATE item 42
    A->>DB: COMMIT
    Note over DB: Lock A được nhả
    DB-->>B: Lock granted; đọc trạng thái phù hợp
    B->>B: Kiểm tra qty=0
    B-->>DB: ROLLBACK hoặc COMMIT không đổi
~~~

Ý nghĩa chính là **B không được đi qua bước kiểm tra tồn kho khi còn một writer khác giữ khóa xung đột trên row đó**.

Điều kiện quan trọng:

- Cả hai transaction phải thực sự dùng locking protocol tương thích. Nếu một writer bỏ qua kiểm tra và ghi trực tiếp theo logic sai, lock bi quan của transaction A không biến business rule thành universal invariant.
- Tác động đọc sau khi chờ còn phụ thuộc isolation (ví dụ `REPEATABLE READ`/`SERIALIZABLE` có thể gây serialization failure thay vì thấy phiên bản mới theo cách `READ COMMITTED`).
- Nếu A rollback, B có thể tiếp tục với trạng thái trước update của A.
- Các lệnh plain `SELECT` trong MVCC DB có thể vẫn đọc dữ liệu committed cũ khi A đang giữ `FOR UPDATE`. Không suy luận mọi người đọc đều bị block.

### Có được giữ khóa sau khi method kết thúc không?

Nếu transaction cũng kết thúc ở cuối method, lock thường được giải phóng khi commit/rollback. Nếu method tham gia một transaction **ngoài** lớn hơn, lock có thể tồn tại đến khi transaction ngoài kết thúc. Đó là lý do transaction boundary quan trọng hơn vị trí dòng `find()` trong code.

## 7. Khóa khi truy vấn bằng JPQL/HQL

Không phải lúc nào ứng dụng cũng biết ID. Có thể cần tìm một entity theo SKU hoặc các điều kiện nghiệp vụ rồi đặt lock khi truy vấn:

~~~java
InventoryItem item = entityManager.createQuery(
    """
    select i
    from InventoryItem i
    where i.sku = :sku
    """,
    InventoryItem.class
)
.setParameter("sku", "BOOK-001")
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getSingleResult();
~~~

Hibernate có thể dịch thành:

~~~sql
SELECT i.id, i.sku, i.available_quantity, i.version
FROM inventory_item i
WHERE i.sku = ?
FOR UPDATE;
~~~

`setLockMode()` gắn yêu cầu khóa với truy vấn **trả về entity**. Khi kết quả có nhiều hàng, tập những hàng bị khóa phụ thuộc query, SQL dialect và plan. Không dùng row-lock mode trên scalar-only projection rồi kỳ vọng JPA cho phép “khóa giá trị `count(*)`” như khóa entity.

### Lấy danh sách theo một điều kiện

~~~java
List<InventoryItem> items = entityManager.createQuery(
    """
    select i from InventoryItem i
    where i.availableQuantity > 0
    order by i.id
    """,
    InventoryItem.class
)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
~~~

Query có thể khóa **nhiều rows**. Với bảng hàng triệu items, thực hiện một query khóa rộng chỉ để chọn một item là chiến lược tốn kém, có thể khiến nhiều transactions chờ và tăng nguy cơ deadlock. Hãy giới hạn điều kiện và số lượng rows đúng nhu cầu.

### `setLockMode()` không phải `setMaxResults()`

`setMaxResults(1)` chỉ giới hạn số entity trả về theo query semantics và dialect; nó không tự cho biết chính xác các row DB đã kiểm tra/khóa trong mọi execution plan. Đặc biệt với join, pagination và follow-on locking, cần đọc SQL/plan thật.

## 8. Khóa một entity đã managed bằng `entityManager.lock()`

Nếu entity đã được load trước đó mà chưa yêu cầu khóa:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class, itemId
);

entityManager.lock(
    item,
    LockModeType.PESSIMISTIC_WRITE
);

item.reserve(1);
~~~

`lock(entity, mode)` yêu cầu provider áp dụng lock mode cho **entity managed** trong persistence context hiện tại. Nó có thể phát sinh SQL bổ sung, như một `SELECT ... FOR UPDATE` hoặc statement phù hợp DB.

### Lỗi nếu entity detached

~~~java
InventoryItem detached = loadInOldSession(itemId);

entityManager.lock(
    detached,
    LockModeType.PESSIMISTIC_WRITE
);
// Không hợp lệ nếu detached không managed trong context hiện tại.
~~~

JPA `lock()` yêu cầu managed entity; nếu truyền detached entity có thể nhận `IllegalArgumentException` hoặc exception tương ứng. Nên tìm managed entity trong transaction rồi lock, hoặc tổ chức lại service để tải có lock ngay từ đầu.

### Khóa sau khi đã đọc có một khoảng trống thời gian

~~~text
T1: find() không khóa -> đọc quantity=1
T2: transaction khác update quantity=0 và commit
T1: lock() rồi dùng giá trị đã đọc khi nãy
~~~

Nếu T1 không refresh/re-validate state sau khi lấy lock, quyết định nghiệp vụ có thể dựa vào dữ liệu cũ. Vì thế đối với **check-then-act**, thường rõ ràng hơn khi gọi `find(..., PESSIMISTIC_WRITE)` hoặc query có `setLockMode()` **ngay ở bước lấy dữ liệu cần kiểm tra**, thay vì đọc trần trước rồi lock sau.

Khi phải nâng cấp lock cho entity đã managed, cần hiểu Hibernate có làm SQL đọc lại, kiểm tra version hay giữ state hiện có, và cân nhắc `refresh(entity, lockMode)` hoặc thiết kế lại ranh giới tải dữ liệu theo nhu cầu.

## 9. `refresh()` đi kèm lock khi cần tái tải state

JPA hỗ trợ refresh một managed entity với lock mode:

~~~java
entityManager.refresh(
    item,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Về ý tưởng, thao tác yêu cầu provider **lấy lại state từ database** cho managed entity trong khi sử dụng khóa phù hợp. Nó khác `lock(item, mode)` đơn thuần, vì `refresh()` có semantics thay state hiện có bằng dữ liệu được tải.

### Cảnh báo quan trọng

~~~java
item.reserve(1); // pending local edit
entityManager.refresh(
    item,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

`refresh()` có thể **ghi đè các thay đổi chưa flush trên entity**. Vì vậy không dùng refresh+lock như thao tác “an toàn hơn” nếu muốn giữ nguyên local edits. Đầu tiên phải xác định bạn cần:

- **Tải và khóa ngay**: `find(..., lockMode)`.
- **Khóa object managed đã có**: `lock(entity, lockMode)`, nhưng chú ý stale state.
- **Tải lại và khóa row**: `refresh(entity, lockMode)` khi chấp nhận thay local state.

`refresh` không phải “commit” và cũng không bảo đảm nhìn thấy một transaction khác chưa commit; DB isolation vẫn áp dụng.

## 10. Hibernate native Session API

Ngoài `EntityManager` chuẩn, Hibernate native `Session` có khả năng yêu cầu lock ngay trong thao tác load:

~~~java
import org.hibernate.LockMode;
import org.hibernate.Session;

try (Session session = sessionFactory.openSession()) {
    var tx = session.beginTransaction();
    try {
        InventoryItem item = session.get(
            InventoryItem.class,
            42L,
            LockMode.PESSIMISTIC_WRITE
        );

        if (item == null) {
            throw new IllegalArgumentException("Missing item");
        }
        item.reserve(1);
        tx.commit();
    } catch (RuntimeException failure) {
        tx.rollback();
        throw failure;
    }
}
~~~

Tên phương thức/overload và các tùy chọn `LockOptions` của Hibernate native có thể thay đổi theo phiên bản. JPA `LockModeType` là lựa chọn tốt nếu dự án muốn giữ khả năng chuyển provider; dùng Hibernate-specific APIs khi cần một khả năng như timeout/skip locked chưa thể diễn đạt portable theo JPA.

### Có thể dùng HQL query với lock options của Hibernate?

Có, Hibernate cung cấp các phương thức/hints riêng trên những query types phù hợp. Tuy nhiên không cần phụ thuộc native API nếu chỉ dùng `PESSIMISTIC_READ`/`PESSIMISTIC_WRITE`: `TypedQuery.setLockMode()` của JPA đã diễn tả yêu cầu chính.

## 11. PESSIMISTIC_READ: đọc với khóa chia sẻ khi DB hỗ trợ

Ví dụ transaction muốn đọc giá bán đã được xác nhận và ngăn writer cạnh tranh thay row trong quá trình làm một bước phụ thuộc:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_READ
);
~~~

Trên PostgreSQL, một dạng SQL tương đương cho một số mapping/dialect có thể là:

~~~sql
SELECT id, sku, available_quantity, version
FROM inventory_item
WHERE id = 42
FOR SHARE;
~~~

**Semantics chung:** yêu cầu khóa đọc để bảo vệ row theo khả năng DB. Trong hệ có shared/exclusive row locks:

| Hai giao dịch cùng row | Kết quả điển hình |
|---|---|
| READ lock và READ lock | Có thể cùng giữ shared locks nếu DB hỗ trợ. |
| READ lock và WRITE lock | Thường xung đột; một bên chờ/từ chối. |
| WRITE lock và WRITE lock | Thường xung đột; một bên chờ/từ chối. |

Bảng chỉ là mô hình khái niệm. PostgreSQL có nhiều cấp row-lock (`FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`) và MySQL/Oracle/SQL Server có hệ lock riêng. Hibernate dialect có thể sử dụng cấp khóa khác, đặc biệt nếu DB không hỗ trợ shared lock theo cách JPA mong muốn.

### Khi nào nên dùng READ?

Khi nhiều readers cần cùng đọc với mức bảo vệ phù hợp nhưng không muốn giành exclusive lock nếu DB thực sự hỗ trợ shared lock. Tuy nhiên nếu thao tác **sẽ cập nhật row**, hãy cân nhắc `PESSIMISTIC_WRITE` ngay từ đầu để tránh upgrade lock và khả năng deadlock khi hai readers đồng thời muốn nâng lên writer.

## 12. PESSIMISTIC_WRITE: khóa khi sắp thực hiện check-then-update

`PESSIMISTIC_WRITE` thường được dùng khi service cần đảm bảo một quyết định cập nhật dựa vào hàng đang được khóa:

~~~java
@Transactional
public void withdraw(long accountId, BigDecimal amount) {
    Account account = entityManager.find(
        Account.class,
        accountId,
        LockModeType.PESSIMISTIC_WRITE
    );
    account.withdraw(amount);
}
~~~

Ví dụ giả định `Account.withdraw()` tự kiểm tra balance không âm, amount hợp lệ và có domain invariants. Hibernate có thể lấy row lock, tải balance, rồi dirty-check update ở flush. Cách này bảo vệ một số race giữa **những transactions cùng dùng protocol**.

### WRITE lock không đồng nghĩa khóa đọc toàn hệ thống

Trong MVCC database như PostgreSQL, transaction khác vẫn có thể `SELECT balance FROM account WHERE id=?` và nhìn bản committed trước đó, ngay cả khi A đang giữ row lock do `FOR UPDATE`. Nếu UI hiển thị số dư cũ trong vài chục milliseconds, đó có thể là behavior bình thường của isolation. Muốn ngăn quyết định giao dịch dựa trên stale data, **những operations quyết định ghi** phải dùng protocol phù hợp — không phải cố chặn mọi reader bằng row lock.

### WRITE lock bảo vệ row nào?

Nếu withdrawal còn phụ thuộc aggregate rows khác (hạn mức ngày, tổng các giao dịch, ledger…), chỉ khóa row Account có thể chưa đủ. Invariant phụ thuộc nhiều rows có thể cần atomic SQL, thêm row tổng hợp, unique/check constraints, serializable isolation hoặc khóa một “serialization point” phù hợp.

## 13. PESSIMISTIC_FORCE_INCREMENT và `@Version`

`PESSIMISTIC_FORCE_INCREMENT` kết hợp yêu cầu khóa bi quan với việc **force increment version** của entity có `@Version`:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
~~~

Ví dụ:

~~~java
@Version
private long version;
~~~

Nếu ứng dụng muốn báo hiệu một thay đổi logic ở aggregate root mà không thực sự sửa field của root, version increment có thể khiến các transactions optimistic đang sử dụng version cũ bị phát hiện xung đột. Provider có thể phát sinh SQL tăng version theo cách phù hợp với generator/DB.

### Khác gì PESSIMISTIC_WRITE?

`PESSIMISTIC_WRITE` bảo vệ row khỏi các khóa/ghi xung đột trong transaction, nhưng **không đồng nghĩa mọi lần gọi đều tăng `version`** nếu entity không dirty. `PESSIMISTIC_FORCE_INCREMENT` yêu cầu thêm tác dụng tăng version của entity versioned.

### Lưu ý

- Chế độ này chủ yếu dành cho entity có version; không sử dụng như công cụ tăng version cho một entity unversioned rồi kỳ vọng portable.
- Thời điểm thực thi version update có thể phụ thuộc Hibernate version và flush/lock semantics; quan sát SQL thực tế.
- Force increment có thể tạo thêm ghi, contention và optimistic conflict ở những transaction khác; không dùng sau mọi query chỉ vì nghĩ “version càng tăng càng an toàn”.
- Với một invariant phụ thuộc nhiều bảng, tăng version root chỉ hữu ích nếu mọi writer liên quan tuân thủ protocol versioning tương ứng.

## 14. Optimistic và pessimistic locking: chọn theo tranh chấp

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cơ chế thường dùng | `@Version`, so version khi UPDATE/flush hoặc yêu cầu optimistic lock. | Yêu cầu DB row lock trước/đang đọc hoặc xử lý. |
| Khi phát hiện xung đột | Thường ở thời điểm flush/commit khi version không khớp. | Thường lúc cố lấy lock hoặc khi khóa bị giữ bởi giao dịch khác. |
| Chờ transaction khác | Thường không giữ row lock từ lúc load để ngăn writer. | Có thể chờ, timeout, deadlock hoặc fail-fast. |
| Thích hợp | Tranh chấp thấp, thao tác thường độc lập, chấp nhận retry. | Tranh chấp cao hơn ở một số hot rows, cần serialize check-then-act. |
| Chi phí | Version check và retry khi conflict. | Lock wait, giảm concurrency, tăng nguy cơ deadlock. |
| Bảo vệ toàn bộ invariant | Không tự động; tùy rows/version protocol. | Không tự động; chỉ các rows/ranges được khóa phù hợp. |

Ví dụ optimistic:

~~~java
@Version
private long version;
~~~

SQL update có thể:

~~~sql
UPDATE inventory_item
SET available_quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Hai transactions cùng load version 0, transaction thắng cập nhật thành version 1; transaction còn lại bị từ chối khi cố update version 0. Đây là cách **phát hiện** conflict thay vì chờ khóa ngay khi đọc.

### Có thể kết hợp cả hai?

Có. Một entity versioned vẫn có thể được tải bằng `PESSIMISTIC_WRITE`. Khóa bi quan giúp điều phối những transactions đang dùng row-lock protocol; version giúp phát hiện một số stale updates ở các luồng khác. Không phải cứ có cả hai là mọi race biến mất. Cần thiết kế dữ liệu và domain invariant phù hợp.

### Nếu transaction dài, chọn pessimistic luôn tốt hơn?

Không. Transaction dài khiến lock tồn tại lâu hơn, tăng wait time/deadlock và giảm throughput. Với yêu cầu UI người dùng nhập liệu trong nhiều phút, thường không nên giữ row lock suốt thời gian nhập; có thể dùng optimistic version khi lưu.

## 15. Transaction là điều kiện bắt buộc để khóa bi quan có ý nghĩa

JPA `PESSIMISTIC_*` locks yêu cầu transaction đang hoạt động cho các thao tác lock tương ứng. Khi gọi `find(..., PESSIMISTIC_WRITE)` hoặc `query.setLockMode(...)` ngoài transaction, provider có thể ném `TransactionRequiredException` hoặc exception phù hợp.

~~~java
// Thiếu transaction:
InventoryItem item = entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE
);
// Có thể ném TransactionRequiredException.
~~~

Phạm vi khóa thường là database transaction, nên cần tránh:

~~~text
BEGIN
  SELECT ... FOR UPDATE   -- đã giữ lock
  gọi HTTP API ngoài
  sleep / chờ người dùng
  xử lý file lớn
  gửi email chậm
  UPDATE
COMMIT                    -- lock cuối cùng mới nhả
~~~

Vì các thao tác I/O không liên quan DB kéo dài transaction, hàng bị khóa có thể khiến nhiều request khác chờ. Một thiết kế tốt thường chia quá trình:

1. Chuẩn bị dữ liệu/validation không cần DB lock ở ngoài.
2. Mở transaction **ngắn**.
3. Lấy row lock khi cần.
4. Đọc/kiểm tra dữ liệu có thể thay đổi, ghi những mutation bắt buộc.
5. Commit/rollback sớm.
6. Thực hiện external notifications sau commit thông qua cơ chế đáng tin cậy như outbox nếu nghiệp vụ yêu cầu.

### Flush không giải phóng lock

~~~java
entityManager.flush();
// Transaction vẫn mở; lock thường vẫn được giữ.
~~~

Đừng dùng `flush()` như thay thế `commit()` để cho transaction khác tiếp tục. Nếu cần thả lock, phải kết thúc transaction theo semantics DB. `clear()` cũng không nhả lock database; nó chỉ detach managed objects trong Java.

## 16. Timeout: không nên chờ khóa mãi

Khi transaction khác giữ row lock, lời gọi `find()`/query có thể đợi. Một service có SLA rõ ràng nên định nghĩa cách xử lý khi quá thời gian.

JPA hỗ trợ query hint tiêu chuẩn:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE,
    java.util.Map.of(
        "jakarta.persistence.lock.timeout", 1_000
    )
);
~~~

Giá trị `1_000` là **millisecond hint** yêu cầu thời gian chờ lock khoảng 1 giây. Có thể đặt trên query:

~~~java
InventoryItem item = entityManager.createQuery(
    "select i from InventoryItem i where i.id = :id",
    InventoryItem.class
)
.setParameter("id", 42L)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.setHint("jakarta.persistence.lock.timeout", 1_000)
.getSingleResult();
~~~

**Quan trọng:** Đây là *hint*, không phải bảo đảm mọi provider/dialect sẽ thực thi chính xác 1.000 ms. Một số database áp dụng timeout ở cấp transaction/session, một số không có `FOR UPDATE WAIT n` portable, và Hibernate có thể bỏ qua hoặc ánh xạ hint theo khả năng dialect. Cần kiểm tra SQL, exception và thời gian thực tế trên DBMS đang dùng.

### Query timeout khác lock timeout

| Hint/tham số | Mục tiêu |
|---|---|
| `jakarta.persistence.lock.timeout` | Thời gian mong muốn để chờ lấy pessimistic lock. |
| `jakarta.persistence.query.timeout` | Thời gian mong muốn để query thực thi nói chung, không chỉ lock wait. |
| Spring `@Transactional(timeout = ...)` | Giới hạn transaction theo cơ chế transaction manager, thường tính bằng giây; không đồng nghĩa một lệnh `FOR UPDATE NOWAIT`. |
| DB statement/lock timeout | Điều khiển riêng của database; có hiệu lực theo scope SQL/session/transaction tương ứng. |

Chúng có thể tương tác nhưng không nên thay thế tên này cho tên kia tùy tiện.

## 17. NOWAIT và SKIP LOCKED

Ngoài việc chờ lock mặc định, nhiều database hỗ trợ hai hành vi đặc biệt:

**NOWAIT:** Nếu không lấy được lock ngay, trả lỗi thay vì chờ lâu.

~~~sql
-- PostgreSQL minh họa:
SELECT *
FROM inventory_item
WHERE id = 42
FOR UPDATE NOWAIT;
~~~

**SKIP LOCKED:** Bỏ qua những rows đang bị transaction khác khóa xung đột; thường dùng để nhiều workers chọn các công việc chưa bị worker khác xử lý.

~~~sql
-- PostgreSQL minh họa:
SELECT id, status
FROM job_queue
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 10;
~~~

### Những khác biệt

| Hành vi | Khi row đang có lock xung đột | Thích hợp |
|---|---|---|
| Chờ (mặc định thông thường) | Đợi đến khi lấy được hoặc timeout/deadlock | Cần xử lý chính row đã chỉ định. |
| NOWAIT | Trả lỗi ngay | Request latency thấp, ứng dụng biết trả “đang bận” hoặc retry sau. |
| SKIP LOCKED | Không đưa row đang bị khóa vào tập kết quả | Worker queue, tìm công việc khả dụng khác. |

**Không dùng SKIP LOCKED cho dữ liệu nghiệp vụ mà “không thấy row” đồng nghĩa “row không tồn tại”.** Bị skip vì lock không giống row không có trong DB. Một query `SKIP LOCKED` cố ý trả tập kết quả **không nhất quán đầy đủ** so với mọi rows thỏa điều kiện tại một thời điểm; đó là trade-off được chấp nhận ở workload phân phối công việc.

### Hibernate API hỗ trợ đến đâu?

Hibernate có các lock options và timeout constants riêng cho `NOWAIT`/`SKIP_LOCKED` ở những phiên bản/dialect hỗ trợ. Chúng không hoàn toàn portable dưới dạng một `LockModeType` JPA riêng; cú pháp native SQL hoặc provider-specific hints/options có thể cần thiết. Cách gọi cụ thể thay đổi theo Hibernate release, vì thế chỉ dùng trên phiên bản dự án đã kiểm chứng và có integration test trên DB thực.

## 18. Xử lý lỗi lấy khóa

Không thể lấy lock vì timeout, deadlock hoặc serialization conflict là **kết quả bình thường có thể xảy ra trong hệ concurrent**, không nhất thiết lỗi logic Hibernate.

Trong JPA, hai loại exception cần biết:

| Exception | Ngữ nghĩa tiêu chuẩn chính |
|---|---|
| `LockTimeoutException` | Lock không được cấp và chỉ statement bị rollback (theo khả năng báo lỗi của provider/DB), transaction không nhất thiết bị đánh dấu rollback. |
| `PessimisticLockException` | Lấy lock thất bại khiến transaction bị rollback hoặc được đánh dấu rollback-only theo semantics JPA. |

Trên thực tế còn có:

- `PersistenceException`/Hibernate exceptions bọc SQLException từ DB.
- Deadlock victim, serialization failure hoặc lock wait timeout với SQLSTATE/mã lỗi riêng.
- Spring DataAccessException được dịch từ persistence exception, ví dụ lock acquisition/optimistic locking exceptions tương ứng.

Không viết code chỉ catch đúng một exception rồi khẳng định mọi lock conflict được xử lý. Quan sát SQLSTATE, transaction manager rollback status và dialect để phân loại retryable vs non-retryable.

### Nếu đã gặp lỗi, có thể gọi clear rồi tiếp tục không?

Không nên. `entityManager.clear()` chỉ detach managed entities; nó **không giải phóng một database transaction đang bị rollback-only** và không sửa row conflict. Sau những lỗi SQL/flush nghiêm trọng, thông thường cần rollback, kết thúc unit of work rồi retry trong transaction/context mới.

### Retry có giới hạn

Với NOWAIT/lock timeout/deadlock, application có thể retry có giới hạn:

~~~text
attempt #1 -> lock timeout
  rollback transaction
  backoff + jitter
attempt #2 -> retry toàn nghiệp vụ trong transaction mới
  lấy lock
  check trạng thái mới
  cập nhật
  commit
~~~

**Không retry mù quáng** nếu operation có side effects bên ngoài (gửi email, gọi payment provider, gửi sự kiện) mà chưa có idempotency/outbox. Retry toàn transaction phải **đọc lại dữ liệu** vì state giữa các lần có thể đã đổi.

## 19. Deadlock: khi nhiều transaction khóa rows theo thứ tự khác

Giả sử chuyển tiền giữa hai accounts:

~~~text
Transaction A                       Transaction B
------------------------------      ------------------------------
LOCK account #1                    LOCK account #2
LOCK account #2 (chờ B)            LOCK account #1 (chờ A)
           \                       /
            +---- DEADLOCK -------+
~~~

Database thường có cơ chế phát hiện deadlock và chọn một transaction làm victim để rollback, nhưng tốc độ phát hiện và exception tùy DBMS.

### Thứ tự khóa nhất quán

Khi cần khóa nhiều entities, một cách đơn giản là khóa theo thứ tự định danh:

~~~java
long firstId = Math.min(fromAccountId, toAccountId);
long secondId = Math.max(fromAccountId, toAccountId);

Account first = entityManager.find(
    Account.class, firstId, LockModeType.PESSIMISTIC_WRITE
);

Account second = entityManager.find(
    Account.class, secondId, LockModeType.PESSIMISTIC_WRITE
);
~~~

Sau khi đã khóa, code dùng `fromAccountId`/`toAccountId` để xác định bên ghi nợ/ghi có và thực hiện domain operation. Đoạn minh họa cần xử lý cả trường hợp hai ID bằng nhau, hai account không tồn tại và validate amount trước khi chuyển tiền.

**Khóa theo thứ tự thống nhất** giúp giảm khả năng hai transactions hình thành vòng chờ, nhưng không loại bỏ mọi deadlock nếu còn bảng/row/trigger/unique index/foreign-key checks khác tham gia.

### Đừng tự tin `ORDER BY` luôn khóa theo đúng thứ tự mong muốn

Một query `WHERE id IN (...) ORDER BY id FOR UPDATE` có thể được database optimizer thực thi theo kế hoạch riêng, nhất là khi joins/CTEs/limits. Khi cần thứ tự lock deterministic cho một tập rất nhỏ, lấy lần lượt từng ID đã sort trong application thường rõ ràng hơn. Với tập lớn, cần đo concurrency và thiết kế câu SQL/db-specific locking cẩn thận.

## 20. Không khóa được row chưa tồn tại

Một hiểu nhầm phổ biến:

~~~java
List<Coupon> coupons = entityManager.createQuery(
    "select c from Coupon c where c.code = :code",
    Coupon.class
)
.setParameter("code", "PROMO-NEW")
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
~~~

Nếu không có coupon nào mang code đó, query có thể trả danh sách rỗng. **Không có row để khóa** theo row-lock thông thường.

Sau đó hai transactions có thể cùng quyết định “chưa có coupon, vậy tạo mới”:

~~~text
T1: SELECT FOR UPDATE WHERE code='PROMO-NEW' -> empty
T2: SELECT FOR UPDATE WHERE code='PROMO-NEW' -> empty
T1: INSERT coupon('PROMO-NEW')
T2: INSERT coupon('PROMO-NEW')
~~~

Giải pháp bắt buộc thường gồm **UNIQUE constraint trên code**, sau đó xử lý conflict tại insert/commit, hoặc sử dụng một serialization row/range/isolation strategy tương ứng nghiệp vụ. Một số DB/isolation dùng gap/next-key locks trong những truy vấn nhất định, nhưng đó **không phải bảo đảm portable của JPA `PESSIMISTIC_WRITE`**.

### Bảo vệ invariant trên tập rows

Nếu quy tắc là “một người chỉ có tối đa 3 vé đang giữ”, khóa một vé hiện có chưa chắc bảo vệ điều kiện `count(tickets) < 3` khỏi transaction khác insert thêm vé mới. Cần:

- Khóa một row owner/aggregate làm serialization point và bắt buộc mọi writers dùng nó.
- Unique/partial unique constraint hoặc một bảng quota với atomic conditional update.
- Serializable isolation với retry khi phù hợp.
- Một quy trình khác bảo vệ invariant ở DB.

**Row lock bảo vệ các rows đã khóa**, không tự bảo vệ mọi predicate, gap hoặc phép đếm trên tập dữ liệu.

## 21. Phạm vi khóa khi query có JOIN

Query HQL:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    """
    select o
    from PurchaseOrder o
    join o.customer c
    where c.id = :customerId
    """,
    PurchaseOrder.class
)
.setParameter("customerId", customerId)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.getResultList();
~~~

Trong SQL, Hibernate có thể dùng join `purchase_order -> customer`, rồi đưa lock clause tương ứng. Nhưng **tập rows thật sự bị khóa** phụ thuộc dialect, join semantics, alias/lock scope và database SQL.

Không nên mặc định:

- Chỉ entity root `PurchaseOrder` chắc chắn bị khóa và không có bảng join nào khác bị khóa.
- Mọi `Customer` và mọi collection con chắc chắn cũng bị khóa.
- Tập rows theo Java object graph trùng chính xác tập rows bị DB khóa.

Đặc biệt PostgreSQL có giới hạn khi áp dụng `FOR UPDATE` lên phía nullable của outer join trong một số cấu trúc; Hibernate có thể thay đổi SQL hoặc dùng **follow-on locking**.

### Join để lọc khác join fetch

`join o.customer c` cho phép lọc theo Customer, còn `join fetch o.lines` yêu cầu nạp collection. Nếu fetch join collection làm nhân số rows SQL, kết hợp với locking có thể trở nên rất đắt hoặc cần SQL phụ theo dialect. Đừng thêm `join fetch` vào locking query chỉ vì muốn “tránh lazy loading”; phải hiểu tập dữ liệu và khóa thực sự cần.

## 22. PessimisticLockScope.NORMAL và EXTENDED

Jakarta Persistence còn có khái niệm **pessimistic lock scope**, điều khiển phạm vi lock trong những mapping phù hợp:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.scope",
    jakarta.persistence.PessimisticLockScope.EXTENDED
);

InventoryItem item = entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Hai ý tưởng:

- `PessimisticLockScope.NORMAL`: scope mặc định về entity và những bảng thuộc chính entity theo inheritance/secondary-table mapping phù hợp.
- `PessimisticLockScope.EXTENDED`: yêu cầu provider mở rộng phạm vi khóa tới các rows thuộc một số collection/join tables hoặc quan hệ không có owner row riêng theo ngữ nghĩa JPA. Đây **không phải lệnh khóa đệ quy toàn bộ các entity liên quan**.

Nếu entity có `@ElementCollection`, join table hoặc unidirectional `@OneToMany` dùng join table, EXTENDED có thể tác động thêm những bảng chứa association rows. Hành vi thực tế phụ thuộc JPA provider và DBMS, có thể không có khác biệt nếu dialect không hỗ trợ/không thể triển khai theo mong muốn.

**Không lạm dụng EXTENDED** để bảo vệ mọi business invariant. Nếu muốn khóa một child entity cụ thể, hãy lock child trong transaction theo mapping thực sự, rồi kiểm tra những rows DB nào được khóa.

## 23. JOINED inheritance và @SecondaryTable

Không phải mọi entity ánh xạ đúng một bảng. Ví dụ một `Payment` dùng inheritance strategy `JOINED` có bảng root và bảng subtype; hoặc entity có `@SecondaryTable` cho thông tin bổ sung.

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
abstract class Payment {
    @Id
    Long id;
}
~~~

Một concrete `CardPayment` có thể có:

~~~text
payment(id=100)
card_payment(payment_id=100)
~~~

Khi Hibernate khóa `CardPayment#100` bằng `PESSIMISTIC_WRITE`, nhà phát triển phải hiểu SQL có thể liên quan **nhiều bảng vật lý** của cùng entity. Lock scope NORMAL không đơn giản là “chỉ khóa row root rồi bỏ hết subtype tables”. Cách Hibernate tạo lock SQL, các lock clauses trên joined tables hoặc follow-on locks phụ thuộc dialect và mapping.

### Tại sao cần xem SQL?

Nếu một transaction chỉ khóa bảng root còn đường cập nhật khác trực tiếp sửa bảng subtype, business protocol không nhất thiết ngăn mọi xung đột như bạn nghĩ. Nên kiểm tra actual locks và bảo đảm mọi writers đi theo transaction/mapping phù hợp, đặc biệt khi có native SQL hoặc ứng dụng khác cập nhật schema.

## 24. Pagination với locking queries

Ví dụ worker muốn chọn 10 items đủ điều kiện:

~~~java
List<InventoryItem> candidates = entityManager.createQuery(
    """
    select i
    from InventoryItem i
    where i.availableQuantity > 0
    order by i.id
    """,
    InventoryItem.class
)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.setMaxResults(10)
.getResultList();
~~~

Tùy dialect, Hibernate có thể tạo SQL chứa `LIMIT/FETCH FIRST` và `FOR UPDATE`, hoặc phải dùng **follow-on locking**: lấy IDs/entities rồi phát khóa trong statement bổ sung để đáp ứng giới hạn SQL của database.

### Follow-on locking là gì?

Một mô hình:

~~~text
Query chính:
  SELECT ... FROM inventory_item
  WHERE ... ORDER BY ... FETCH FIRST 10 ROWS ONLY

Query khóa theo kết quả:
  SELECT ... FROM inventory_item
  WHERE id IN (...)
  FOR UPDATE
~~~

Đây chỉ là **hình thức minh họa**. Hibernate có thể áp dụng cơ chế khác tùy phiên bản/dialect, hoặc báo lỗi nếu query shape không hỗ trợ khóa như yêu cầu. Giữa query chính và query lấy lock có một khoảng thời gian; cần hiểu semantics isolation/row recheck nếu ứng dụng phụ thuộc tính nhất quán tuyệt đối.

### Phân trang không tự bảo đảm fairness

Nếu mọi worker đều lấy `ORDER BY id LIMIT 10 FOR UPDATE`, các rows có ID nhỏ có thể trở thành hotspot. `SKIP LOCKED` giúp các workers chọn công việc khác, nhưng có thể bỏ qua các rows đang bị giữ lock rất lâu, gây starvation. Thiết kế cần lease/retry/monitoring thay vì giả định query phân trang tự là một scheduler hoàn chỉnh.

## 25. Locking queries với aggregate, DISTINCT và GROUP BY

JPA query:

~~~java
Long count = entityManager.createQuery(
    "select count(i) from InventoryItem i where i.availableQuantity > 0",
    Long.class
).getSingleResult();
~~~

Kết quả là **scalar**, không phải managed entity. Không thể chỉ thêm `setLockMode(PESSIMISTIC_WRITE)` rồi nghĩ database sẽ “khóa giá trị COUNT”. Một số DB còn cấm `FOR UPDATE` kết hợp aggregate/`GROUP BY`/`DISTINCT` trong những hình dạng SQL nhất định.

Nếu nghiệp vụ dựa trên kết quả `COUNT` để quyết định có insert/update, cần thiết kế **serialization point, atomic conditional SQL, constraints hoặc isolation** phù hợp với predicate. Khóa một tập entities và sau đó đếm bằng một query khác chưa chắc bảo vệ mọi phantom rows.

### DTO projection cũng không phải managed entity lock

~~~java
List<InventorySummary> summaries = entityManager.createQuery(
    """
    select new com.example.InventorySummary(
        i.id, i.availableQuantity
    )
    from InventoryItem i
    """,
    InventorySummary.class
).getResultList();
~~~

Đây là projection DTO (giả sử constructor đúng) chứ không phải danh sách managed `InventoryItem` entities. Nếu yêu cầu khóa entity, hãy viết một entity-select query phù hợp hoặc dùng native SQL có khóa được kiểm chứng, thay vì suy luận DTO mặc nhiên nắm pessimistic lock.

## 26. Ví dụ hàng đợi công việc với SKIP LOCKED

Một use case điển hình là nhiều workers cùng lấy công việc chưa được xử lý:

~~~sql
CREATE TABLE job_queue (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ
);

CREATE INDEX ix_job_ready
    ON job_queue(status, created_at, id);
~~~

Trong PostgreSQL:

~~~sql
BEGIN;

SELECT id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 1;

-- Trong cùng transaction, đánh dấu row vừa được chọn:
UPDATE job_queue
SET status = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP
WHERE id = :selected_id;

COMMIT;
~~~

Hai workers có thể thực hiện query cùng lúc mà không phải chờ trên đúng một row đã được worker khác khóa; worker sau sẽ bỏ qua row đang có lock và nhận row khác.

### Claim và xử lý dài nên tách thế nào?

Không nên giữ transaction `FOR UPDATE SKIP LOCKED` mở trong suốt 20 phút chạy external job. Một pattern:

1. Transaction ngắn: chọn row chưa claim, lấy lock, đánh dấu `CLAIMED`/owner/lease expiry rồi commit.
2. Thực hiện công việc dài ngoài lock transaction.
3. Transaction khác: xác nhận kết quả và chuyển `DONE` hoặc `FAILED`, kiểm tra lease/owner/version.

**Điều kiện phục hồi:** nếu worker chết sau khi claim, cần lease timeout/retry logic; nếu job có side effect, cần idempotency. `SKIP LOCKED` không tự đảm bảo exactly-once processing, fairness hoặc tự phục hồi các job bị kẹt.

### So sánh với inventory reservation

Với inventory item cụ thể, bỏ qua row đang bị lock thường **không phải** kết quả đúng: người dùng cần biết tình trạng chính item đó. Với queue có nhiều công việc thay thế nhau, bỏ qua một row đang bận lại là cơ chế hữu ích. Chọn NOWAIT/WAIT/SKIP LOCKED phải dựa trên semantics nghiệp vụ.

## 27. Khi nào không nên dùng khóa bi quan?

Khóa bi quan có chi phí:

- Transaction khác có thể phải chờ và chiếm connection trong pool.
- Thời gian phản hồi biến thiên theo contention.
- Lock wait timeout/deadlock có thể làm retry và rollback nhiều hơn.
- Hot row trở thành điểm tuần tự hóa, hạn chế throughput.
- Query khóa nhiều rows có thể làm giảm concurrency đáng kể.
- Holding locks lâu do HTTP calls hoặc thao tác xử lý nặng làm vấn đề nghiêm trọng hơn.

Những workload cần cân nhắc giải pháp khác:

| Nhu cầu | Ứng viên |
|---|---|
| Update một counter đơn giản nếu đủ hàng | Atomic conditional `UPDATE ... WHERE available_quantity >= ?` và kiểm tra row count. |
| Edit form lâu trên UI | Optimistic `@Version`, retry/merge conflict có chủ đích khi save. |
| Ngăn duplicate email/code | Unique constraint ở DB; xử lý collision, không chỉ row lock. |
| Đếm điều kiện trên nhiều rows | Serializable isolation, lock serialization row, aggregate counter hoặc constraint phù hợp. |
| Phân phối jobs cho nhiều workers | Transaction claim ngắn + `SKIP LOCKED`/lease/idempotency khi DB hỗ trợ. |
| Đọc danh mục/report | Thường không cần pessimistic lock; cân nhắc read consistency/isolation và caching. |
| Hotspot rất lớn | Thiết kế giảm contention, partition/shard counter, queueing hoặc data model phù hợp. |

Khóa bi quan không phải “mức an toàn cao nhất áp dụng càng nhiều càng tốt”. Nó là một công cụ có **chi phí trên throughput và latency**.

## 28. Isolation level vẫn quan trọng

Ngay cả khi có row lock, **transaction isolation** ảnh hưởng dữ liệu transaction nhìn thấy:

| Isolation (mô tả khái niệm) | Điều cần lưu ý khi dùng row locking |
|---|---|
| `READ COMMITTED` | Mỗi statement thường thấy committed state phù hợp DB; transaction đợi lock rồi tiếp tục có thể thấy row đã cập nhật. |
| `REPEATABLE READ` | Có snapshot/locking semantics DB-specific; một số hệ thống có thể báo serialization/concurrent update error khi đụng row đã đổi. |
| `SERIALIZABLE` | Bảo vệ nhiều anomaly hơn theo DB implementation, nhưng có thể tạo serialization failure cần retry. |

Đừng chỉ nhìn tên isolation rồi suy luận tất cả DB giống nhau. PostgreSQL, MySQL InnoDB, Oracle và SQL Server có chi tiết MVCC, range locks, snapshot isolation và deadlock behaviors khác nhau.

### Pessimistic lock không tự chống phantom

Ví dụ transaction kiểm tra:

~~~sql
SELECT COUNT(*) FROM reservation WHERE resource_id = 10;
~~~

Sau đó khóa một `Resource#10` nhưng **một writer khác không khóa resource row** vẫn có thể insert reservation mới. Muốn serializable business decision cần mọi writers tuân thủ shared protocol, hoặc dùng DB constraint/isolation/atomic update phù hợp.

## 29. So sánh SQL giữa các database

| Hệ DB | Cơ chế điển hình | Lưu ý |
|---|---|---|
| PostgreSQL | `SELECT ... FOR UPDATE`; `FOR SHARE`; `NOWAIT`; `SKIP LOCKED` | Có nhiều mức row-lock, MVCC readers thường không bị chặn bởi row lock writer. |
| MySQL (InnoDB) | `SELECT ... FOR UPDATE`; shared-lock syntax tùy phiên bản; NOWAIT/SKIP LOCKED ở các phiên bản hỗ trợ | Isolation/index/range scans có thể tạo next-key/gap locks; autocommit/transaction scope rất quan trọng. |
| Oracle | `SELECT ... FOR UPDATE`; NOWAIT/WAIT/SKIP LOCKED với cú pháp và giới hạn riêng | Không có cùng một shared row lock syntax/semantics như PostgreSQL ở mọi trường hợp. |
| SQL Server | Lock hints như `UPDLOCK`, `HOLDLOCK`, `ROWLOCK` hoặc cơ chế tương đương | Không dùng `FOR UPDATE` PostgreSQL như cú pháp portable; isolation và row-versioning configuration ảnh hưởng behavior. |

Các cú pháp và capability thay đổi theo version/edition. Hibernate dialect dịch `LockModeType` thành cơ chế phù hợp nơi có hỗ trợ, có thể dùng follow-on locking, nhưng **không thể biến một DB không hỗ trợ requested semantics thành behavior giống tuyệt đối DB khác**.

### Chú ý MySQL autocommit

Một raw `SELECT ... FOR UPDATE` ngoài transaction được giữ mở đúng cách có thể không đem lại bảo vệ như mong đợi vì statement kết thúc và lock được nhả ngay sau đó trong autocommit mode. Trong JPA, yêu cầu transaction cho pessimistic lock giúp tránh lạm dụng này; nhưng khi viết native SQL/JDBC, phải kiểm tra connection autocommit và transaction boundary.

## 30. Entity manager cache và dữ liệu stale

Giả sử `InventoryItem#42` đã managed trước khi code yêu cầu lock:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class, 42L
);
// Lúc này state đã được đưa vào persistence context.
~~~

Nếu transaction khác cập nhật DB rồi commit, và context hiện tại tiếp tục dùng object cũ, một lần gọi `lock(item, PESSIMISTIC_WRITE)` không được hiểu là **bảo đảm Java fields đã được refresh theo một cách giống `refresh()`** trong mọi provider path.

Lý do: persistence context có **identity map và loaded-state metadata**. Hibernate thường giữ managed instance cùng ID và không tự thay mọi field chỉ vì SQL query mới chạy. Cần xác định:

- Đã load entity trước đó chưa?
- Transaction khác có thể thay đổi row sau lần load?
- Có yêu cầu nhìn state mới nhất trong isolation đang dùng?
- Cần lock từ lần load đầu, hay refresh kèm lock?

Trong một quy trình check-then-update, cách dễ hiểu nhất vẫn là **tải với lock ở thời điểm bắt đầu bước ra quyết định** trong transaction ngắn, tránh giữ một object stale từ transaction cũ.

### Second-level cache có bảo vệ concurrency không?

Không thay thế row locks. Cache cấp hai có các chiến lược concurrency riêng nhưng không tự tạo bảo vệ cho một nghiệp vụ check-then-act xuyên nhiều writers/database clients. Khi cần DB lock, phải yêu cầu lock phù hợp và giữ transaction đúng ranh giới; việc load từ cache/identity map không chứng minh khóa DB đã có.

## 31. Lock và transaction propagation trong Spring

Ví dụ:

~~~java
@Transactional
public void reserve(long itemId) {
    InventoryItem item = entityManager.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );
    item.reserve(1);
}
~~~

Nếu method này được gọi từ một transaction ngoài với propagation mặc định `REQUIRED`, nó thường **tham gia transaction ngoài**, nên lock có thể được giữ lâu hơn thời gian method con chạy.

~~~java
@Transactional
public void placeOrder(long itemId) {
    inventoryService.reserve(itemId);
    callSlowExternalApi(); // lock có thể còn giữ đến khi placeOrder commit!
}
~~~

Không tự động thêm `REQUIRES_NEW` để rút ngắn lock duration mà không hiểu business atomicity: commit reservation ở transaction con rồi external API thất bại có thể để lại tồn kho đã trừ. Cân nhắc state machine, outbox/saga, idempotency hoặc transaction boundary khác để đáp ứng yêu cầu hệ thống.

### Self-invocation

Với Spring proxy-based transaction management, gọi method `@Transactional` từ method khác **trong cùng instance** bằng `this.method()` có thể không đi qua transaction proxy. Nếu `PESSIMISTIC_WRITE` được gọi khi transaction không được mở như bạn nghĩ, nó có thể thất bại. Kiểm tra transaction configuration và call path thực tế, không coi annotation luôn tự tạo transaction trong mọi trường hợp.

## 32. Quan sát SQL, lock waits và deadlocks

Trong môi trường thử nghiệm Spring Boot + Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
hibernate.generate_statistics=true
~~~

Những gì cần quan sát:

- SQL thực tế có `FOR UPDATE`, `FOR SHARE`, lock hint hay follow-on `SELECT` không?
- Lock có được yêu cầu **trước** khi business code kiểm tra state không?
- Transaction bắt đầu/kết thúc ở đâu? Có I/O lâu khi đang giữ lock không?
- Lock wait duration, số deadlocks, timeout và transaction rollbacks là bao nhiêu?
- Query khóa bao nhiêu rows (tập khóa thực tế có rộng hơn kết quả nghiệp vụ không)?
- Với NOWAIT/SKIP LOCKED, dialect có sinh đúng cú pháp được hỗ trợ không?
- Sau exception, transaction còn hợp lệ hay phải rollback?

Log bind values có thể chứa thông tin nhạy cảm; chỉ bật TRACE trong môi trường phù hợp. Hibernate statistics không luôn cho biết đầy đủ wait graph/row lock owner; cần kết hợp **database monitoring**, ví dụ PostgreSQL `pg_stat_activity` và `pg_locks` hoặc công cụ tương ứng của DBMS.

### PostgreSQL: quan sát wait khi thử nghiệm

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Đây là truy vấn giám sát khái quát; permissions và thông tin hiển thị tùy role/version. Không chạy truy vấn mạnh hoặc thu thập toàn bộ SQL chứa dữ liệu nhạy cảm ở production nếu chưa có quy định.

## 33. Thực hành A: hai transaction khóa cùng một row

Mở **hai sessions/transactions độc lập** trên cùng database; không chia sẻ một Hibernate `Session` giữa threads.

**Transaction A:**

~~~sql
BEGIN;
SELECT * FROM inventory_item WHERE id = 42 FOR UPDATE;
-- Giữ transaction mở vài giây để quan sát (chỉ ở DB thử nghiệm).
UPDATE inventory_item
SET available_quantity = 0
WHERE id = 42;
COMMIT;
~~~

**Transaction B (bắt đầu sau khi A đã khóa, trước khi A commit):**

~~~sql
BEGIN;
SELECT * FROM inventory_item WHERE id = 42 FOR UPDATE;
-- Thường phải chờ A kết thúc, hoặc lỗi nếu có timeout/NOWAIT.
ROLLBACK;
~~~

Quan sát thời gian B chờ, DB monitoring và state B nhìn thấy sau khi tiếp tục. Lặp lại với B dùng plain `SELECT` trong PostgreSQL MVCC để thấy reader thường không bị block như writer; ghi chú isolation.

### Kiểm chứng ứng dụng JPA

Ở service A và B, gọi cùng:

~~~java
entityManager.find(
    InventoryItem.class, 42L,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Đừng dùng một `EntityManager` chung cho hai threads để mô phỏng concurrent transactions: `EntityManager/Session` không thread-safe. Mỗi worker phải có transaction/context riêng được transaction manager tạo đúng cách.

## 34. Thực hành B: NOWAIT và lock timeout

Giữ row `42` đang bị A khóa. Ở B:

~~~sql
BEGIN;
SELECT * FROM inventory_item
WHERE id = 42
FOR UPDATE NOWAIT;
-- PostgreSQL trả lỗi không lấy được lock ngay.
ROLLBACK;
~~~

So với:

~~~java
entityManager.find(
    InventoryItem.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 500)
);
~~~

Xem timeout hint có được dialect hỗ trợ và được thực thi như mong muốn hay không. Không đoán mọi trường hợp đều ném đúng cùng exception class; ghi nhận SQLSTATE và transaction state.

## 35. Thực hành C: cùng READ lock rồi nâng cấp lên WRITE

Trong DB hỗ trợ shared row locks:

~~~text
T1: PESSIMISTIC_READ item/42
T2: PESSIMISTIC_READ item/42
T1: muốn PESSIMISTIC_WRITE item/42
T2: muốn PESSIMISTIC_WRITE item/42
~~~

Hai transactions có thể hình thành một tình huống upgrade conflict/deadlock, tùy DB lock compatibility. Quan sát DB behavior và giải thích vì sao **nếu biết chắc sẽ sửa row**, thường nên lấy `PESSIMISTIC_WRITE` ngay thay vì cả hai cùng shared lock rồi tranh nhau nâng cấp.

Không thực hiện thử nghiệm trên bảng production có hot rows; nên dùng DB test với transaction timeout rõ để không giữ lock vô hạn.

## 36. Thực hành D: khóa và kiểm tra stock trong service

Giả sử item#42 còn `1`, chạy hai requests độc lập cùng gọi:

~~~java
@Transactional
public boolean tryReserve(long itemId) {
    InventoryItem item = entityManager.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );
    if (item == null) return false;
    if (item.getAvailableQuantity() < 1) return false;

    item.reserve(1);
    return true;
}
~~~

Lưu ý phương thức trả `true` trước khi transaction interceptor commit. Nếu commit sau đó lỗi, service caller phải nhận failure (exception) và không thông báo success vĩnh viễn cho client. Trong thiết kế API thực tế, cần đảm bảo chỉ xác nhận hoàn thành nghiệp vụ sau khi transaction commit thành công.

Kỳ vọng khi cả hai transaction dùng protocol và isolation phù hợp: chỉ một request thành công trừ tồn kho, request còn lại thấy không đủ hàng hoặc gặp lỗi concurrency được xử lý. Kiểm tra DB constraint `available_quantity >= 0` và số row reservation được tạo, không chỉ xem thông báo từ Java.

## 37. Thực hành E: deadlock do khóa ngược thứ tự

Tạo hai account rows `1` và `2`, hai transactions:

~~~text
T1:
  lock account 1
  lock account 2

T2:
  lock account 2
  lock account 1
~~~

Quan sát deadlock detector/timeout của DB. Sau đó sửa cả hai code paths để luôn lock theo `min(id)` rồi `max(id)`. Lặp lại và xem khả năng deadlock giảm. Ghi nhận nó **không loại trừ** deadlocks từ các bảng/locks khác, nhưng là một biện pháp thiết kế quan trọng.

## 38. Thực hành F: predicate không có row

Tạo bảng `coupon(code UNIQUE)`, mở hai transactions:

~~~sql
BEGIN;
SELECT * FROM coupon
WHERE code = 'NEW-2026'
FOR UPDATE;
-- trả 0 row nếu code chưa tồn tại
~~~

Trong transaction khác, làm tương tự. Sau đó cả hai cố insert cùng code. Quan sát unique constraint xử lý tranh chấp: row-lock query rỗng không bảo vệ sự tồn tại của code. Thí nghiệm này minh họa vì sao locking query không thay được **unique DB constraint**.

## 39. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `TransactionRequiredException` khi lock | Gọi pessimistic lock ngoài active transaction. | Đặt transaction boundary đúng, kiểm tra Spring proxy/self-invocation. |
| Query khóa chờ quá lâu | Row hot, transaction holder dài, external I/O trong transaction. | Rút ngắn transaction, kiểm tra waits, timeout/NOWAIT phù hợp. |
| Nhiều deadlocks | Khóa nhiều rows theo thứ tự khác hoặc tham gia trigger/FK/index locks. | Thứ tự lock thống nhất, giảm phạm vi, retry có giới hạn. |
| PESSIMISTIC_READ cũng chặn readers khác | Dialect fallback sang lock mạnh hơn hoặc DB lock semantics khác kỳ vọng. | Xem SQL/DB docs, không giả định READ luôn shared. |
| `SKIP LOCKED` trả thiếu row | Row đang khóa bị bỏ qua theo thiết kế. | Chỉ dùng cho use case chấp nhận bỏ qua; tránh dùng như query đầy đủ. |
| Khóa một row nhưng vẫn bị oversell | Invariant phụ thuộc rows khác hoặc writers không tuân thủ protocol. | Serialization row, atomic conditional SQL, constraints/isolation. |
| `lock()` trên detached ném lỗi | `EntityManager.lock` yêu cầu managed entity. | Tải managed trong transaction trước khi khóa. |
| Row đã load trước, lấy lock sau nhưng state cũ | Identity map giữ managed snapshot; lock không giống refresh. | Tải có lock ngay từ đầu hoặc refresh+lock có chủ đích. |
| `flush()` rồi request khác vẫn chờ | Lock giữ tới commit/rollback. | Kết thúc transaction sớm, không coi flush là unlock. |
| `clear()` rồi tưởng lock đã nhả | Clear chỉ detach managed objects. | Commit/rollback DB transaction. |
| Lock query JOIN khóa quá nhiều rows | Tập row/joins, lock scope/follow-on locking rộng. | Giới hạn query, chỉ lock target rows, xem SQL/plan. |
| `PESSIMISTIC_FORCE_INCREMENT` làm version tăng | Đúng semantics force increment. | Chỉ dùng khi thật sự cần invalidate optimistic readers/writers. |
| Timeout hint bị bỏ qua | Dialect/provider không hỗ trợ đúng yêu cầu. | Kiểm chứng DB-specific behavior hoặc cấu hình timeout ở DB. |
| Không query được lock mode với DTO/aggregate | Query không trả managed entity hoặc SQL shape không lockable. | Entity-select query hoặc native SQL/mô hình invariant khác. |
| Gặp lock exception rồi clear và retry trong cùng tx | Transaction đã rollback-only/aborted. | Rollback và retry trong transaction/context mới. |

### Hai quy tắc để tránh lỗi khó thấy

**Quy tắc thứ nhất:** Quyết định nghiệp vụ phải được thực hiện **sau khi bảo vệ dữ liệu nền**, không phải đọc giá trị cũ rồi “khóa để hợp thức hóa” quyết định đã đưa ra.

**Quy tắc thứ hai:** Khóa bảo vệ **những rows/ranges mà DB thật sự khóa và những writers tuân thủ protocol**. Nó không tự bảo vệ tất cả điều kiện nghiệp vụ, đối tượng Java hay hệ thống bên ngoài database.

## 40. Quy trình ra quyết định dùng khóa bi quan

Trước khi thêm `PESSIMISTIC_WRITE` vào repository, trả lời:

1. **Đang bảo vệ invariant nào?** Số lượng tồn kho, số dư, trạng thái job, hạn mức hay uniqueness?
2. **Invariant phụ thuộc row nào?** Một row có đủ để serialize decision hay cần nhiều rows/ranges?
3. **Các writers khác có tuân thủ cùng protocol không?** Có native SQL, batch jobs hoặc app khác ghi trực tiếp không?
4. **Có thể dùng atomic conditional UPDATE hoặc unique constraint đơn giản hơn không?**
5. **Transaction có ngắn và kết thúc rõ không?** Có gọi external APIs/sleep/đợi người dùng trong khi giữ lock không?
6. **Lock mode nào đúng?** READ nếu cần shared read protection và DB hỗ trợ; WRITE khi check-then-update; FORCE_INCREMENT khi có ý đồ version cụ thể.
7. **Nếu lock không lấy được, ứng dụng làm gì?** Chờ, fail-fast, retry có giới hạn hay chọn công việc khác?
8. **Query có JOIN/fetch/pagination/aggregate không?** Tập khóa và SQL có như bạn nghĩ không?
9. **DB isolation/dialect có khác các giả định trên localhost không?**
10. **Đã có integration test với hai transactions thật chưa?** Một unit test chỉ mock repository không chứng minh DB locking hoạt động.

### Bảng gợi ý lựa chọn

| Tình huống | Gợi ý |
|---|---|
| Đặt hàng từ inventory item cụ thể, nhiều writers cạnh tranh | `find(..., PESSIMISTIC_WRITE)` trong transaction ngắn hoặc atomic conditional update. |
| Xem danh mục sản phẩm | Thường không cần pessimistic lock; dùng read-only/projection phù hợp. |
| Nhập liệu form dài rồi lưu | Optimistic `@Version` thường phù hợp hơn giữ lock trong thời gian người dùng nhập. |
| Chọn một job READY bất kỳ giữa nhiều workers | `SKIP LOCKED`/claim transaction ngắn và lease/idempotency nếu DB hỗ trợ. |
| Truy vấn nhiều accounts để chuyển tiền | Khóa các accounts theo thứ tự ID nhất quán; kiểm tra toàn transaction. |
| Cần nhận lỗi ngay nếu row đang bị khóa | NOWAIT hoặc lock timeout phù hợp dialect, retry/fallback có chủ đích. |
| Cần ngăn hai transactions tạo cùng một code chưa tồn tại | Unique constraint/atomic insert conflict handling, không chỉ `SELECT FOR UPDATE` rỗng. |
| Thay đổi aggregate con cần tăng version root có chủ đích | Xem xét `PESSIMISTIC_FORCE_INCREMENT` trên versioned root và bảo đảm writers cùng protocol. |

## 41. Mô hình ghi nhớ cuối bài

~~~mermaid
flowchart TD
    A["Cần xử lý dữ liệu có thể bị sửa đồng thời"] --> B{"Có cần ngăn writer khác ngay lúc đọc?"}
    B -- "Không, chấp nhận conflict/retry" --> C["Optimistic @Version hoặc atomic SQL"]
    B -- "Có" --> D["Mở transaction ngắn"]
    D --> E{"Biết entity ID?"}
    E -- "Có" --> F["find(Entity, id, PESSIMISTIC_WRITE)"]
    E -- "Không" --> G["JPQL entity query + setLockMode"]
    F --> H["Database cấp row lock hoặc wait/fail"]
    G --> H
    H --> I{"Lấy được khóa?"}
    I -- "Không" --> J["Rollback / timeout policy / bounded retry"]
    I -- "Có" --> K["Đọc và kiểm tra lại state/invariant"]
    K --> L["Sửa managed entity"]
    L --> M["Flush khi cần, commit để xác nhận và nhả lock"]
    M --> N["Theo dõi latency, waits, deadlocks"]
~~~

**Khóa bi quan khi tải hoặc truy vấn thực thể** là yêu cầu Hibernate gửi database một thao tác đọc kèm lock semantics, thường qua `find(..., LockModeType.PESSIMISTIC_WRITE)`, `entityManager.lock()` hoặc JPQL `setLockMode()`. Khóa giúp điều phối các transactions tranh chấp trên những hàng dữ liệu liên quan, nhưng **nó chỉ có hiệu lực đúng như transaction, SQL và DBMS thực thi**.

Một thiết kế tốt bắt đầu từ **invariant nghiệp vụ**, lựa chọn rows cần bảo vệ, giữ transaction ngắn, dùng lock mode phù hợp và định nghĩa hành vi khi chờ/timeout/deadlock. Không dùng `PESSIMISTIC_WRITE` như annotation “bật an toàn toàn hệ thống”, không nhầm `flush()` với unlock/commit, và không mong query khóa một row bảo vệ mọi dòng mới chưa tồn tại. Khi biết chính xác **lúc nào khóa được lấy, hàng nào bị khóa, khi nào khóa được nhả và conflict được xử lý ra sao**, Hibernate pessimistic locking trở thành công cụ đáng tin cậy để xây dựng các thao tác đồng thời có tính nhất quán cao.
