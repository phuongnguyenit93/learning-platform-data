# Đồng bộ context trước hoặc sau thao tác SQL ngoài cơ chế theo dõi thực thể

## 1. Vấn đề: database đã đổi nhưng entity trong Java chưa đổi

Trong Hibernate ORM/Jakarta Persistence (JPA), phần lớn thao tác thông thường được thực hiện trên **managed entity**:

~~~java
InventoryItem item = entityManager.find(InventoryItem.class, itemId);
item.reserve(3);
~~~

Khi entity được quản lý trong **persistence context**, Hibernate theo dõi trạng thái và phát sinh SQL UPDATE lúc `flush`. Người viết code không nhất thiết gọi SQL UPDATE trực tiếp.

Tuy nhiên, ứng dụng còn có thể thay đổi database bằng những con đường **ngoài cơ chế dirty checking từng entity**:

- `EntityManager.createNativeQuery(...).executeUpdate()`: native SQL UPDATE/DELETE/INSERT.
- `Session.createNativeMutationQuery(...)` hoặc native-query API tương ứng trong Hibernate version.
- `Session.doWork(...)` hoặc JDBC thuần.
- `JdbcTemplate`/jOOQ/MyBatis chạy SQL trong ứng dụng.
- Stored procedure, database trigger, FK `ON DELETE CASCADE`.
- JPQL/HQL **bulk** UPDATE/DELETE.
- Một transaction khác hoặc hệ thống khác sửa cùng bản ghi.

Sau những thao tác này, hai thế giới có thể khác nhau:

~~~text
Java / Hibernate Session
    +------------------------------+
    | Persistence context (L1)     |
    | InventoryItem#42.quantity=8  |
    | InventoryItem#42.version=5   |
    +------------------------------+
                   |
                   | native UPDATE trực tiếp,
                   | không cập nhật managed object
                   v
Database transaction
    +------------------------------+
    | inventory_items#42           |
    | quantity=5, version=6        |
    +------------------------------+
~~~

Hibernate không thể suy luận tùy ý mọi thay đổi dữ liệu do SQL ngoại lai gây ra rồi tự sửa tất cả Java objects đang managed. Vì vậy phải phân biệt hai hướng đồng bộ:

1. **Trước khi chạy SQL ngoài cơ chế theo dõi thực thể:** cân nhắc `flush()` để đẩy những thay đổi pending trong persistence context xuống database, bảo đảm SQL kế tiếp đọc/ghi dựa trên trạng thái đã được ghi vào transaction.
2. **Sau khi SQL đã thay đổi database:** cân nhắc `refresh()`, `clear()`, `detach()` hoặc context/transaction mới để không tiếp tục dùng trạng thái managed đã lỗi thời.

**Nguyên tắc nhớ nhanh: `flush` là Java → database; `refresh` là database → một entity managed; `clear` làm persistence context ngừng quản lý tất cả entity hiện tại.** Ba thao tác không thay thế cho nhau.

Bài này nằm trong chương **SQL gốc** của module **Data Persistence Relational Access ORM Hibernate**, tập trung vào ranh giới giữa native/JDBC SQL và persistence context.

## 2. Ba tầng trạng thái cần phân biệt

### 2.1. Persistence context: first-level cache và identity map

Persistence context nằm trong `EntityManager` hoặc Hibernate `Session`. Với cùng một entity type và identifier, thông thường nó giữ một managed instance trong context:

~~~java
InventoryItem first = entityManager.find(InventoryItem.class, 42L);
InventoryItem second = entityManager.find(InventoryItem.class, 42L);

System.out.println(first == second); // true trong cùng persistence context
~~~

Lần `find` thứ hai có thể lấy lại object đã quản lý mà không truy vấn database lần nữa. Đây là hành vi hữu ích cho identity, dirty checking và nhất quán graph nội bộ; nó cũng giải thích tại sao database đổi nhưng một entity đã nạp vẫn có thể giữ giá trị cũ.

Persistence context không phải một cơ chế tự động nhận mọi thay đổi database. Nó chỉ biết những thay đổi đi qua entity lifecycle hoặc những thao tác đồng bộ mà ứng dụng/provider thực hiện.

### 2.2. Database transaction và SQL thực thi

Database quản lý các hàng, foreign keys, locks, isolation level, triggers và commit/rollback.

Khi Hibernate gọi `flush()`, SQL pending được gửi đi trong transaction, nhưng **chưa có nghĩa đã commit**. Transaction khác có nhìn thấy thay đổi hay không còn phụ thuộc isolation/commit.

Ngược lại, khi native SQL UPDATE chạy trong **cùng transaction**, database đã thay đổi hàng theo câu SQL đó, nhưng persistence context có thể vẫn chứa entity state cũ.

### 2.3. Second-level cache và query cache

Ngoài first-level context, dự án có thể bật:

- **Second-level cache (L2):** cache dữ liệu entity/collection giữa các Session.
- **Query cache:** cache kết quả/truy vấn theo cơ chế Hibernate.

`entityManager.clear()` chỉ dọn **first-level persistence context hiện tại**, không mặc định xóa tất cả entry trong L2 hay query cache. Khi dữ liệu bị thay đổi bằng một JDBC client độc lập, stored procedure hoặc hệ thống ngoài ORM, cache dùng chung có thể cần chính sách invalidation riêng.

### 2.4. Cùng một row có thể có nhiều “giá trị hiện tại”

| Nơi quan sát | Giá trị có thể thấy | Lý do |
|---|---|---|
| Getter của managed entity | Snapshot/biến Java hiện tại | Entity đã được nạp trước native UPDATE |
| `EntityManager.find` trong cùng context | Chính managed instance cũ | Identity map/L1 |
| Native scalar SELECT trên cùng connection/transaction | Giá trị database sau SQL đã thực thi | SQL đọc trực tiếp DB |
| `refresh(managedEntity)` | State DB phù hợp với transaction visibility | ORM nạp lại entity |
| EntityManager/Session mới | State được DB/cache trả về theo transaction | Context mới, nhưng L2/cache policy vẫn quan trọng |

Không tự kết luận “getter của entity là sự thật cuối cùng trong database” sau khi vừa thực hiện một câu native SQL.

## 3. Ví dụ xuyên suốt: tồn kho và SQL cập nhật trực tiếp

Giả sử một bảng lưu tồn kho:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_nonnegative_quantity CHECK (available_quantity >= 0)
);
~~~

Entity:

~~~java
package com.example.inventory;

import jakarta.persistence.*;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    private long version;

    protected InventoryItem() {}

    public Long getId() {
        return id;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public long getVersion() {
        return version;
    }

    public void restock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        this.availableQuantity = Math.addExact(
            this.availableQuantity, amount
        );
    }
}
~~~

Trong ví dụ, hãy giả định ID `42` đã tồn tại và `available_quantity = 10`, `version = 3`.

### 3.1. Cập nhật bằng managed entity

~~~java
InventoryItem item = entityManager.find(InventoryItem.class, 42L);
item.restock(5);

// Hibernate chưa bắt buộc gửi UPDATE ngay tại lời gọi restock().
entityManager.flush();
~~~

SQL minh họa:

~~~sql
UPDATE inventory_items
SET available_quantity = 15,
    version = 4
WHERE id = 42
  AND version = 3;
~~~

SQL chính xác phụ thuộc mapping/version/dialect. Với `@Version`, Hibernate thường dùng version trong điều kiện optimistic locking của entity-level update.

### 3.2. Cập nhật bằng native SQL

~~~java
int count = entityManager.createNativeQuery(
    """
    UPDATE inventory_items
       SET available_quantity = available_quantity - ?,
           version = version + 1
     WHERE id = ?
       AND available_quantity >= ?
    """
)
.setParameter(1, 2)
.setParameter(2, 42L)
.setParameter(3, 2)
.executeUpdate();
~~~

Câu SQL được database thực thi trực tiếp. Nó không gọi `item.restock()` và không tự sửa fields của một `InventoryItem` đang managed.

SQL ví dụ có tăng version **tường minh** để những giao dịch optimistic locking khác không lặng lẽ ghi đè. Nhưng việc có tăng version hay không phải được thiết kế theo nghiệp vụ, không phải quy tắc tự động cho mọi native UPDATE.

Nếu `count == 0`, có thể không tìm thấy bản ghi hoặc tồn kho không đủ; ứng dụng cần trả kết quả nghiệp vụ đúng và không giả định chắc chắn row đã được đổi.

## 4. Vấn đề A: chưa flush mà SQL cần đọc các thay đổi pending

Xét một transaction thực hiện:

~~~java
@Transactional
public BigDecimal updateAndReadTotal(Long itemId) {
    InventoryItem item = entityManager.find(
        InventoryItem.class, itemId
    );

    item.restock(5);

    Object value = entityManager.createNativeQuery(
        "select available_quantity from inventory_items where id = ?"
    ).setParameter(1, itemId)
     .getSingleResult();

    return new BigDecimal(value.toString());
}
~~~

Chỗ cần lưu ý: `item.restock(5)` thay đổi Java object. Việc Hibernate có flush tự động trước native SELECT hay không **phụ thuộc API, flush mode, synchronization information và phiên bản**. Không thể suy luận một câu native SELECT chắc chắn thấy state mới chỉ từ việc setter vừa chạy.

### 4.1. Flush tường minh khi cần thứ tự chắc chắn

~~~java
@Transactional
public int restockAndReadFromSql(Long itemId, int amount) {
    InventoryItem item = entityManager.find(
        InventoryItem.class, itemId
    );

    item.restock(amount);

    // Đưa các thay đổi pending xuống DB trong transaction hiện tại.
    entityManager.flush();

    Number quantity = (Number) entityManager.createNativeQuery(
        "select available_quantity from inventory_items where id = ?"
    ).setParameter(1, itemId)
     .getSingleResult();

    return quantity.intValue();
}
~~~

Đây là cách **diễn đạt rõ thứ tự**: thay đổi entity → flush → native SELECT.

Lưu ý:
- `flush()` không commit.
- `flush()` cần transaction phù hợp khi gửi thay đổi dữ liệu.
- Nếu entity có constraint/optimistic-locking error, lỗi có thể xuất hiện ngay ở flush.
- `flush()` có thể gửi **nhiều** SQL pending trong context, không chỉ SQL cho `item`.
- Nếu native SQL sử dụng **connection/transaction khác**, flush trên context hiện tại không đảm bảo transaction khác nhìn thấy thay đổi chưa commit.

### 4.2. Timeline khi SQL cần phụ thuộc pending entity changes

~~~text
T0: DB quantity = 10
T1: em.find(Item#42)                Java quantity = 10
T2: item.restock(5)                Java quantity = 15; DB vẫn có thể = 10
T3: em.flush()                     UPDATE thực thi; DB trong transaction = 15
T4: native SELECT quantity         thấy 15 trên cùng transaction/connection
T5: transaction commit             dữ liệu được xác nhận bền vững
~~~

Nếu bỏ T3, auto-flush có thể xảy ra hoặc không tùy cơ chế. Khi correctness phụ thuộc SQL thấy dữ liệu mới, yêu cầu explicit flush hoặc cấu hình synchronization được xác nhận qua test.

### 4.3. Auto-flush qua EntityManager và Hibernate Session khác nhau thế nào?

Với `FlushModeType.AUTO`, JPA yêu cầu các thay đổi ảnh hưởng kết quả query được phản ánh phù hợp trước khi query thực thi, nhưng provider được chọn cách đảm bảo.

Hibernate có sự khác biệt theo API/version:
- Native SQL chạy qua **JPA EntityManager** trong chế độ AUTO thường kích hoạt flush trước query theo cách tích hợp của Hibernate.
- Native SQL chạy qua **Hibernate Session** có thể không tự flush nếu Hibernate chưa biết query phụ thuộc vào bảng nào và chưa có synchronization information.
- `COMMIT`, `MANUAL` hoặc các flush modes khác làm thay đổi thời điểm flush và có thể dẫn đến kết quả query cũ nếu lập trình viên giả định AUTO.
- Hibernate cung cấp native-query synchronization APIs để khai báo query spaces/entities cho một số đường thực thi.

Vì vậy, thay vì học thuộc “native SQL luôn auto-flush” hoặc “native SQL không bao giờ auto-flush”, hãy **kiểm tra đúng phiên bản/API/flush mode** và dùng `flush()` tường minh khi thứ tự là điều kiện correctness.

## 5. Vấn đề B: native UPDATE xong nhưng entity vẫn stale

Xét đoạn sau trong cùng persistence context:

~~~java
InventoryItem item = entityManager.find(
    InventoryItem.class, 42L
);

int before = item.getAvailableQuantity();  // Ví dụ: 10

entityManager.createNativeQuery(
    """
    update inventory_items
       set available_quantity = available_quantity - 2,
           version = version + 1
     where id = ?
       and available_quantity >= 2
    """
).setParameter(1, 42L)
 .executeUpdate();

int after = item.getAvailableQuantity();
~~~

**Không được mặc định `after == 8`.** Getter có thể vẫn trả `10` vì native UPDATE không đi qua setter/dirty checking của Java object đã nạp. Kể cả một `find(InventoryItem.class, 42L)` nữa trong cùng context có thể trả chính instance ấy.

### 5.1. refresh đúng một managed entity

~~~java
entityManager.refresh(item);

int quantity = item.getAvailableQuantity(); // Dựa trên state được nạp lại.
long version = item.getVersion();
~~~

`refresh` yêu cầu entity còn managed và row vẫn tồn tại/được nhìn thấy theo transaction isolation. Nó tải lại state từ database và cập nhật object. Nhưng chú ý:

- Những thay đổi Java **chưa flush** trên entity được refresh có thể bị **ghi đè**.
- Nếu row đã bị xóa ngoài ORM, refresh có thể ném exception.
- Nếu một transaction khác sửa dữ liệu nhưng isolation hiện tại giữ snapshot cũ, refresh **không bảo đảm** thấy mọi thay đổi vừa được transaction khác commit.
- Refresh một entity không mặc định cập nhật mọi DTO, mọi object khác hoặc mọi collection cache độc lập.

### 5.2. Timeline khi SQL thay đổi DB sau khi entity đã load

~~~text
T0: DB quantity = 10, version = 3
T1: em.find(Item#42)              managed Item quantity=10, version=3
T2: native UPDATE -2, version+1   DB quantity=8, version=4
T3: item.getAvailableQuantity()   có thể vẫn =10 (stale)
T4: em.refresh(item)              managed Item quantity=8, version=4
T5: item.getAvailableQuantity()   8
T6: commit                        chấp nhận thay đổi DB trong transaction
~~~

### 5.3. clear toàn context khi có nhiều entity bị ảnh hưởng

Nếu native SQL sửa hàng nghìn rows, refresh từng entity không thực tế. Có thể chọn context boundary:

~~~java
entityManager.flush(); // Nếu có các thay đổi managed cần giữ.
int affected = entityManager.createNativeQuery(
    "update inventory_items set available_quantity = 0 where id in (?,?,?)"
)
.setParameter(1, 101L)
.setParameter(2, 102L)
.setParameter(3, 103L)
.executeUpdate();

entityManager.clear();

InventoryItem reloaded =
    entityManager.find(InventoryItem.class, 101L);
~~~

Sau `clear()`, tất cả managed entities trước đó trở thành **detached**. Bất kỳ reference Java đang giữ tới object cũ không tự cập nhật; cần dùng object được load lại.

`clear()` có phạm vi rất rộng: không chỉ detach những item vừa cập nhật. Nếu có thay đổi chưa flush cần giữ, clear có thể khiến thay đổi không được persisted. Thiết kế service nên tách ranh giới transaction/context thay vì gọi clear tùy tiện trong một nghiệp vụ dài.

### 5.4. detach một entity riêng lẻ

~~~java
entityManager.detach(item);

InventoryItem fresh =
    entityManager.find(InventoryItem.class, item.getId());
~~~

`detach()` chỉ đưa entity cụ thể ra khỏi persistence context (với các tác động cascade detach nếu mapping có). Nó **không** tự cập nhật object cũ. Trong một context khác hoặc dưới cache configuration cụ thể, `find` có thể đi qua L2 cache; nếu cập nhật ngoài Hibernate, cần cân nhắc invalidation của L2.

## 6. Bộ công cụ đồng bộ: flush, refresh, clear, detach

| Công cụ | Hướng tác động | Khi nào nên dùng | Điều KHÔNG làm |
|---|---|---|---|
| `entityManager.flush()` | Managed changes → DB trong transaction | Trước SQL cần đọc/ghi dựa trên pending changes | Không commit, không reload managed objects |
| `entityManager.refresh(entity)` | DB → entity managed | Sau native update/trigger, cần state mới của một entity | Không refresh toàn context, có thể mất local pending changes |
| `entityManager.clear()` | Detach mọi managed entity khỏi L1 | Sau bulk/native SQL ảnh hưởng nhiều row, muốn bắt đầu đọc lại | Không commit, không xóa L2; có thể bỏ pending changes |
| `entityManager.detach(entity)` | Detach một object | Muốn ngừng quản lý một entity và load lại sau | Không sửa database, không reload object cũ |
| Đóng context và mở context mới | Chấm dứt identity map cũ | Ranh giới use case/transaction rõ ràng | Không tự làm L2 cache luôn mới |
| L2/query cache eviction | Xóa cache dùng chung có chọn lọc | Dữ liệu bị sửa bên ngoài Hibernate cache tracking | Không thay state managed trong L1 đang mở |

**Không dùng `refresh` khi muốn “flush”. Không dùng `flush` khi muốn “reload”. Không dùng `clear` như một lệnh commit.**

### 6.1. Quy tắc thứ tự phổ biến

Khi kết hợp entity update và native SQL trong **cùng transaction**:

~~~text
[Managed changes cần giữ]
           |
           v
       em.flush()
           |
           v
   [Native SQL/JDBC DML]
           |
           v
     +-----------------+
     | Cần entity mới? |
     +-----------------+
         |         |
    một entity     nhiều entity / bulk
         |         |
         v         v
   em.refresh(x)  em.clear()
         |         |
         v         v
    dùng x mới   load lại khi cần
           |
           v
  Commit/rollback theo transaction manager
~~~

Không phải mọi query cần cả ba thao tác. Nếu code chỉ chạy native SELECT trên database chưa có pending changes, không cần `clear`. Nếu sau native UPDATE không tiếp tục dùng entity trong context cũ, có thể kết thúc transaction/context ngay thay vì refresh dư thừa.

## 7. Một service thực tế: kiểm tra lượng cập nhật và nạp lại

Ví dụ method Spring-managed, với một SQL giảm tồn kho có điều kiện:

~~~java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int reserveWithNativeSql(Long itemId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }

        // Nếu context có pending changes mà native SQL phụ thuộc,
        // đảm bảo DB trong transaction hiện tại thấy chúng trước.
        em.flush();

        int affected = em.createNativeQuery(
            """
            UPDATE inventory_items
               SET available_quantity = available_quantity - ?,
                   version = version + 1
             WHERE id = ?
               AND available_quantity >= ?
            """
        )
        .setParameter(1, quantity)
        .setParameter(2, itemId)
        .setParameter(3, quantity)
        .executeUpdate();

        if (affected != 1) {
            // Có thể không tồn tại item hoặc không đủ tồn kho.
            // Service phải chọn exception/result đúng contract nghiệp vụ.
            throw new IllegalStateException(
                "Item not found or insufficient inventory"
            );
        }

        // Đã cập nhật DB nhưng có thể có InventoryItem managed stale.
        // Nếu service này không cần giữ bất kỳ managed state hiện có,
        // có thể chọn clear. Trong service khác có nhiều state pending,
        // không nên clear mù quáng.
        em.clear();

        return affected;
    }
}
~~~

Ví dụ làm rõ **semantics**, không phải nguyên tắc rằng service nào cũng nên `flush() + clear()`. `flush()` có thể là overhead dư thừa nếu transaction chỉ thực hiện đúng một native UPDATE. `clear()` có thể làm hỏng một unit of work lớn nếu caller đã tạo/sửa nhiều managed entities còn dùng sau đó.

Đặc biệt, trong Spring, transaction `@Transactional` có thể tham gia transaction bên ngoài. Một repository/service gọi `clear()` ảnh hưởng cả persistence context được chia sẻ trong transaction ấy. Vì vậy cần **quyết định phạm vi giao dịch và ownership context**, không chỉ lắp hai lệnh vào tất cả method.

### 7.1. Chỉ refresh một Item đã load

Nếu caller cần tiếp tục dùng object cụ thể:

~~~java
@Transactional
public InventoryItem reserveAndRead(Long itemId, int quantity) {
    InventoryItem item = em.find(InventoryItem.class, itemId);
    if (item == null) {
        throw new IllegalArgumentException("Item not found");
    }

    em.flush();  // Nếu có pending entity changes cần đồng bộ.

    int affected = em.createNativeQuery(
        """
        UPDATE inventory_items
           SET available_quantity = available_quantity - ?,
               version = version + 1
         WHERE id = ? AND available_quantity >= ?
        """
    )
    .setParameter(1, quantity)
    .setParameter(2, itemId)
    .setParameter(3, quantity)
    .executeUpdate();

    if (affected != 1) {
        throw new IllegalStateException("Insufficient inventory");
    }

    em.refresh(item);  // Nạp lại quantity và version.
    return item;
}
~~~

Nếu entity có local changes chưa flush **sau** khi native UPDATE mà `refresh` được gọi, những thay đổi đó có thể bị mất. Quy trình an toàn là không trộn sửa entity và SQL trực tiếp lên cùng row nếu chưa định nghĩa rõ thứ tự và conflict behavior.

### 7.2. Read response sau khi kết thúc transaction

Không nên trả một managed entity trực tiếp ra ngoài chỉ để biến thành JSON nếu có lazy associations, graph quá lớn hoặc trạng thái entity không phải contract API. Có thể chuyển thành DTO ngay trong transaction:

~~~java
public record InventoryView(
    Long id,
    int availableQuantity,
    long version
) {}

@Transactional
public InventoryView reserveAndView(Long itemId, int quantity) {
    // Giả định reserveAndRead đã được triển khai trong cùng transaction.
    InventoryItem item = reserveAndRead(itemId, quantity);

    return new InventoryView(
        item.getId(),
        item.getAvailableQuantity(),
        item.getVersion()
    );
}
~~~

Nếu các method ở cùng một Spring bean và dùng self-invocation, `@Transactional` trên method được gọi nội bộ có thể không được proxy intercept; trong ví dụ, method gọi ngoài phải thực sự mở transaction. Không nhân đôi SQL chỉ để đưa dữ liệu về response; chọn boundary phù hợp.
+## 8. Native SELECT: khi dữ liệu SQL khác trạng thái pending hoặc L1

Native SQL không chỉ là UPDATE/DELETE. Ngay cả một SELECT cũng có thể làm lộ sự khác nhau giữa persistence context và database.

### 8.1. SELECT scalar đi thẳng đến database

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);
item.restock(5);

Number dbQuantity = (Number) em.createNativeQuery(
    "select available_quantity from inventory_items where id = ?"
).setParameter(1, itemId)
 .getSingleResult();
~~~

`dbQuantity` được lấy từ SQL query, còn `item.getAvailableQuantity()` được lấy từ Java object. Nếu không có flush trước SELECT và API không auto-flush theo điều kiện, kết quả hai bên có thể khác.

Giải pháp nếu SELECT phải dựa trên entity changes:

~~~java
em.flush();

Number dbQuantity = (Number) em.createNativeQuery(
    "select available_quantity from inventory_items where id = ?"
).setParameter(1, itemId)
 .getSingleResult();
~~~

Không nên ép `clear()` trước SELECT để “cho chắc”: nếu context còn changes chưa flush, clear có thể làm mất chúng. Trình tự flush trước, và chỉ clear khi thực sự cần loại bỏ state managed cũ.

### 8.2. Native query trả entity cũng có thể dùng instance đã managed

Ví dụ:

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);

em.createNativeQuery(
    "update inventory_items set available_quantity = 99 where id = ?"
).setParameter(1, itemId)
 .executeUpdate();

InventoryItem queried = (InventoryItem) em.createNativeQuery(
    "select * from inventory_items where id = ?",
    InventoryItem.class
).setParameter(1, itemId)
 .getSingleResult();
~~~

Khi query result được map thành entity và persistence context đã có entity cùng identity, Hibernate có thể trả chính managed instance hiện hữu:

~~~java
System.out.println(queried == item); // Có thể là true.
~~~

Đừng cho rằng việc native SELECT trả `InventoryItem.class` chắc chắn cập nhật fields cũ của `item`. Đó vẫn là entity result, chịu identity map và state handling của ORM.

Nếu muốn dữ liệu mới từ DB:
- `em.refresh(item)` khi entity còn tồn tại và cần tiếp tục dùng chính instance.
- `em.clear()` và query/find lại khi chấp nhận detach tất cả.
- Scalar/DTO projection riêng nếu chỉ cần giá trị đọc, không cần entity managed.

### 8.3. DTO/scalar đọc trực tiếp không tự đồng bộ managed object

Giả sử native scalar SELECT đã trả 99, còn `item.getAvailableQuantity()` vẫn 10. Điều này không mâu thuẫn: một bên đến từ database, bên kia là managed Java state. Việc convert kết quả scalar thành DTO không tác động lên `item`.

Không dùng “cùng transaction” làm lý do khẳng định hai object view phải tự cập nhật; transaction chỉ xác định phạm vi atomicity/isolation ở DB, không đồng bộ state trong bộ nhớ Java.

## 9. Hibernate Session và NativeQuery synchronization

Hibernate có cơ chế **query spaces** (bảng hoặc vùng dữ liệu query phụ thuộc) để xác định sự liên quan giữa pending entity updates và native SQL query. Khi biết query liên quan tới entity/bảng nào, Hibernate có thể quyết định auto-flush và xử lý một số khía cạnh cache synchronization phù hợp.

### 9.1. Native SELECT qua Hibernate Session

~~~java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery(
    "select count(*) from inventory_items"
);

Object count = query.getSingleResult();
~~~

Đây là API Hibernate native; kết quả scalar có thể là Number/Long/BigInteger tùy driver/provider/mapping. Không cast cứng khi chưa biết kiểu thực tế.

Với Hibernate Session, việc native query có tự flush pending changes dưới AUTO hay không liên quan tới synchronization metadata và hành vi của version. Không suy luận giống hệt đường thực thi qua EntityManager.

### 9.2. addSynchronizedEntityClass()

Khi query tham chiếu bảng của entity cụ thể:

~~~java
NativeQuery<?> query = session.createNativeQuery(
    "select count(*) from inventory_items"
);

query.addSynchronizedEntityClass(InventoryItem.class);

Number count = (Number) query.getSingleResult();
~~~

`addSynchronizedEntityClass(InventoryItem.class)` thông báo dependency của native query tới entity mapping tương ứng. Hibernate có thể dùng thông tin này cho auto-flush checking và query-cache synchronization/invalidation theo contract phiên bản.

Nếu query phụ thuộc nhiều bảng/entity, khai báo đầy đủ những vùng dữ liệu có liên quan; chỉ khai báo một entity không thể mô tả một query đọc join sang nhiều bảng khác.

### 9.3. addSynchronizedQuerySpace()

Khi cần khai báo tên query space/bảng:

~~~java
NativeQuery<?> query = session.createNativeQuery(
    "select count(*) from inventory_items"
);

query.addSynchronizedQuerySpace("inventory_items");

Number count = (Number) query.getSingleResult();
~~~

Tên query space liên quan mapping và bảng thực tế; phải kiểm tra đúng version và cách naming/schema được sử dụng. Đừng ghép một tên không tồn tại rồi nghĩ Hibernate tự hiểu tất cả câu SQL.

### 9.4. Cơ chế này KHÔNG làm gì?

Dù query có được khai báo synchronized query spaces, **nó không có nghĩa Hibernate tự phân tích từng giá trị đã bị native UPDATE thay đổi và cập nhật managed InventoryItem objects**.

Cần phân biệt:

- **Trước native query:** synchronization metadata có thể làm Hibernate flush pending changes liên quan.
- **Sau native DML:** persistence context vẫn có thể giữ state cũ; phải refresh/clear/context boundary tùy tình huống.

Query-space registration không thay thế `refresh`, `clear` hoặc chính sách cache khi thay đổi dữ liệu từ hệ thống bên ngoài không đi qua ORM.

### 9.5. Explicit flush vẫn hữu ích ở ranh giới cần tính đúng đắn

Nếu một nghiệp vụ kết hợp entity update và SQL có dependency phức tạp, explicit `em.flush()` trước native SQL thường dễ hiểu, rõ contract và ít phụ thuộc chi tiết AUTO flush. Đổi lại, nó có thể gửi nhiều SQL sớm hơn và ảnh hưởng batching. Không lạm dụng flush trên từng entity/iteration nếu không cần.

### 9.6. @Synchronize và entity ánh xạ tới view/subselect

Hibernate có extension `@Synchronize` cho một số entity mapping (ví dụ entity đọc từ `@Subselect`) để khai báo các bảng cơ sở mà entity phụ thuộc nhằm hỗ trợ flush synchronization. Đây là cơ chế ở mức mapping, không đồng nghĩa `NativeQuery.addSynchronizedEntityClass` ở từng câu query.

Nếu đã có một entity ánh xạ tới subselect/view, cần đối chiếu Hibernate documentation và xác nhận bảng được đồng bộ phù hợp. Đừng thêm annotation mà không xác định chính xác những bảng mà view/subselect đọc.

## 10. JDBC thuần, JdbcTemplate và Session.doWork

Khi SQL chạy ngoài `EntityManager.createNativeQuery`, các vấn đề về connection và transaction còn quan trọng hơn.

### 10.1. Thực thi JDBC bằng connection của Session

Hibernate hỗ trợ `Session.doWork` để thực hiện JDBC work trên connection liên quan đến Session:

~~~java
import java.sql.PreparedStatement;
import org.hibernate.Session;

Session session = em.unwrap(Session.class);

em.flush(); // Nếu JDBC SQL phụ thuộc pending entity state.

session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
        """
        UPDATE inventory_items
           SET available_quantity = available_quantity + 5,
               version = version + 1
         WHERE id = ?
        """
    )) {
        ps.setLong(1, itemId);
        ps.executeUpdate();
    }
});

em.refresh(item); // Nếu item là managed entity cần state mới.
~~~

Ví dụ giả định `item` đã được load và vẫn là managed entity cùng row, còn connection tham gia đúng transaction của Session.

**Đừng gọi `connection.commit()`, `rollback()` hoặc `close()` bên trong `doWork` khi connection thuộc lifecycle do Hibernate/transaction manager quản lý.** Để transaction manager xử lý ranh giới commit/rollback; chỉ đóng JDBC resources mà code tự tạo như PreparedStatement/ResultSet.

### 10.2. Dùng JdbcTemplate trong Spring

Một Spring service có thể đồng thời dùng JPA EntityManager và JdbcTemplate:

~~~java
@Service
public class InventoryAdjustmentService {

    private final JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager em;

    public InventoryAdjustmentService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void adjust(Long id, int delta) {
        InventoryItem item = em.find(InventoryItem.class, id);

        em.flush(); // Nếu có pending JPA changes cần JDBC thấy.

        int updated = jdbcTemplate.update(
            """
            UPDATE inventory_items
               SET available_quantity = available_quantity + ?,
                   version = version + 1
             WHERE id = ?
            """,
            delta, id
        );

        if (updated != 1) {
            throw new IllegalStateException("Inventory item missing");
        }

        em.refresh(item);
    }
}
~~~

Code minh họa giả định `JdbcTemplate` và JPA tham gia **cùng** transaction/connection resource theo cấu hình Spring của ứng dụng. Điều đó không tự được bảo đảm chỉ vì method có `@Transactional`: cần kiểm tra transaction manager, DataSource, routing, XA/JTA hay resource-local setup thực tế.

Nếu JdbcTemplate dùng một DataSource khác/connection độc lập, flush của EntityManager có thể không hiển thị với JDBC transaction đó trước commit. Và hai thao tác có thể không commit/rollback cùng nhau.

### 10.3. Connection khác đồng nghĩa có thể là transaction khác

~~~text
EntityManager / Session       JDBC connection khác
       |                              |
  update entity (pending)              |
       |                              |
     flush()                           |
       |  (chưa commit)                |
       |--------------?--------------> SELECT
       |                              |
  DB isolation có thể                 không thấy change
  che giá trị chưa commit             của transaction kia
       |
     commit()
~~~

Giữ mọi thao tác thuộc cùng một unit of work trong transaction resource đúng; đừng cố chữa thiếu transaction sharing bằng `refresh()` hoặc `clear()`. Hai thao tác context này không làm transaction khác thấy dữ liệu chưa commit.

### 10.4. PreparedStatement thay vì nối SQL string

SQL ngoài ORM vẫn phải parameterized:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
    "update inventory_items set available_quantity = ? where id = ?"
)) {
    ps.setInt(1, newQuantity);
    ps.setLong(2, itemId);
    ps.executeUpdate();
}
~~~

Không nối input từ người dùng vào câu SQL; đồng bộ context không giải quyết nguy cơ SQL injection.

## 11. Bulk JPQL/HQL cũng bỏ qua dirty checking theo entity

Người học thường cho rằng chỉ **native SQL** mới có nguy cơ stale. Thực tế, JPQL/HQL bulk UPDATE/DELETE cũng là một dạng **set-based DML** thực thi tại DB, không qua cơ chế cập nhật từng managed entity.

### 11.1. JPQL bulk UPDATE

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);

int count = em.createQuery(
    """
    update InventoryItem i
       set i.availableQuantity = 0
     where i.id = :id
    """
)
.setParameter("id", itemId)
.executeUpdate();

int quantity = item.getAvailableQuantity();
// Có thể vẫn là giá trị đã load trước bulk update.
~~~

Sau bulk DML, nếu cần dùng entity hiện tại:

~~~java
em.refresh(item);
~~~

Nếu cập nhật số lượng lớn và không còn cần object graph cũ:

~~~java
em.clear();
// Sau đó query hoặc find lại.
~~~

### 11.2. Bulk DELETE và entity đã bị xóa

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);

int deleted = em.createQuery(
    "delete from InventoryItem i where i.id = :id"
).setParameter("id", itemId)
 .executeUpdate();
~~~

Entity `item` có thể vẫn tồn tại dưới dạng managed reference trong Java dù row đã bị DB xóa. Sau DELETE, `refresh(item)` không phải một cách đáng tin để “làm entity biến mất”; có thể ném exception vì row không còn. Nếu không cần giữ state, clear/detach và không sử dụng lại reference cũ là cách rõ ràng.

### 11.3. Bulk DML không gọi lifecycle/cascade như remove từng entity

Không nhầm:

~~~java
for (InventoryItem item : items) {
    em.remove(item);
}
~~~

với:

~~~java
em.createQuery(
    "delete from InventoryItem i where i.sku like :prefix"
)
.setParameter("prefix", "OLD-%")
.executeUpdate();
~~~

Bulk DELETE:
- Không tự gọi entity lifecycle callback (ví dụ `@PreRemove`) cho từng row theo cách `remove(entity)`.
- Không tự cascade REMOVE/orphanRemoval qua Java graph.
- Có thể bị foreign key constraints của DB chặn.
- Không tự đồng bộ các managed entity/collection đang có.
- Không bảo đảm cơ chế `@Version` trên từng entity như entity-level update.

Những vấn đề này gần với native SQL, dù câu lệnh được viết bằng JPQL/HQL.

### 11.4. Hibernate MutationQuery

Hibernate 6 có `MutationQuery` cho bulk HQL mutation:

~~~java
import org.hibernate.Session;
import org.hibernate.query.MutationQuery;

Session session = em.unwrap(Session.class);

MutationQuery query = session.createMutationQuery(
    """
    update InventoryItem i
       set i.availableQuantity = i.availableQuantity + :delta
     where i.id = :id
    """
);

int count = query
    .setParameter("delta", 10)
    .setParameter("id", itemId)
    .executeUpdate();
~~~

`MutationQuery` thể hiện rõ ý định sửa dữ liệu nhưng vẫn là **bulk mutation**: không tự refresh managed object sau khi thực thi.

Đối với các entity cần domain invariants, entity callbacks, optimistic locking theo từng row hoặc cascade, có thể phải load entity và gọi domain methods thay vì bulk DML.

## 12. Spring Data JPA @Modifying: hai cờ flushAutomatically và clearAutomatically

Spring Data JPA hỗ trợ annotation `@Modifying` cho repository query thay đổi dữ liệu.

Ví dụ:

~~~java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query(
        value = """
            UPDATE inventory_items
               SET available_quantity = available_quantity + :delta,
                   version = version + 1
             WHERE id = :id
            """,
        nativeQuery = true
    )
    int adjustQuantity(
        @Param("id") Long id,
        @Param("delta") int delta
    );
}
~~~

Ý nghĩa theo Spring Data JPA:
- `flushAutomatically = true`: flush EntityManager **trước** khi chạy modifying query.
- `clearAutomatically = true`: clear EntityManager **sau** khi chạy modifying query.

Đây là hai lựa chọn độc lập, không mặc định bật trong mọi phiên bản; phải xem đúng Spring Data JPA version.

### 12.1. Vì sao clearAutomatically không luôn an toàn?

Nếu trong transaction có nhiều entity được caller sửa mà chưa flush, clear có thể làm mất pending changes. Bật `flushAutomatically` trước `clearAutomatically` giúp bảo vệ những thay đổi đang chờ ghi trong cùng context, nhưng cũng có thể flush **nhiều** entity khác sớm hơn mong muốn.

Ngoài ra, clear ảnh hưởng toàn EntityManager trong transaction, không chỉ InventoryItem liên quan tới một query. Một repository method nhỏ có thể khiến caller bất ngờ nhận các detached entities.

### 12.2. Một lựa chọn khác: chỉ refresh entity cần dùng

Nếu chỉ cập nhật một row và caller cần một managed instance được nạp lại, có thể chạy `@Modifying(flushAutomatically = true)` rồi để service `em.refresh(item)` sau query. Điều này giữ các entity khác trong context. Tuy nhiên, refresh sẽ ghi đè local modifications chưa flush trên chính entity được refresh, nên thứ tự vẫn quan trọng.

### 12.3. Spring Data @Modifying không phải transaction boundary

`@Modifying` phân loại modifying query của repository; nó không thay thế `@Transactional` khi cần transaction ghi. Đặt transaction boundary ở service hoặc repository theo thiết kế.

Một transaction rollback thì những database writes trong cùng transaction cũng rollback; flush/clear không làm commit độc lập.

## 13. Optimistic locking: native SQL không tự thực hiện @Version

Một entity có:

~~~java
@Version
private long version;
~~~

Khi Hibernate thực hiện **entity-level update** thông thường, version có thể được đưa vào điều kiện WHERE và tăng theo mapping để phát hiện cập nhật cạnh tranh.

Native SQL hoặc JDBC UPDATE **không tự áp dụng** logic đó.

### 13.1. Nguy cơ: SQL thay dữ liệu nhưng giữ nguyên version

Giả sử DB ban đầu:

~~~text
id=42, quantity=10, version=7
~~~

Transaction A load entity:

~~~java
InventoryItem item = em.find(InventoryItem.class, 42L);
// quantity=10, version=7
~~~

Trong khi đó, một native SQL/JDBC operation (cùng hoặc khác transaction) thực hiện:

~~~sql
UPDATE inventory_items
SET available_quantity = 2
WHERE id = 42;
-- version vẫn 7
~~~

Sau đó entity cũ được sửa bằng dirty checking và flush. Vì version chưa đổi, một optimistic update dựa trên version=7 có thể vẫn thành công và ghi đè dữ liệu native SQL, tùy state/entity mapping và thứ tự transaction.

**Không kết luận `@Version` bảo vệ được mọi thay đổi khi một nguồn ghi bỏ qua version.**

### 13.2. Tăng version tường minh cùng native UPDATE

Một phương án là nâng version trong SQL:

~~~sql
UPDATE inventory_items
   SET available_quantity = available_quantity - ?,
       version = version + 1
 WHERE id = ?
   AND available_quantity >= ?;
~~~

Khi một managed entity cũ đang giữ version trước đó, entity-level update về sau có thể bị optimistic-lock failure thay vì lặng lẽ ghi đè.

Nhưng đây chưa hẳn là đầy đủ: nếu muốn native operation cũng phát hiện conflict dựa trên phiên bản mà application đã đọc, cần version predicate:

~~~sql
UPDATE inventory_items
   SET available_quantity = available_quantity - ?,
       version = version + 1
 WHERE id = ?
   AND version = ?
   AND available_quantity >= ?;
~~~

Đọc số affected rows để biết thao tác có thành công. Với một số database/statement, affected-row semantics cần được kiểm tra, nhưng khi UPDATE theo primary key và predicate cụ thể, 0 thường có nghĩa row không thỏa điều kiện.

### 13.3. Không trộn hai cơ chế tăng version không kiểm soát

Nếu một use case vừa thay managed entity vừa chạy native UPDATE trên cùng row và mỗi bên tăng version, có thể gặp:

- Optimistic lock failure hợp lệ vì state đã khác.
- Local entity giữ version cũ nên getter stale.
- Flush order không mong muốn.
- Dữ liệu “last writer wins” nếu native SQL không dùng version predicate.
- Số version tăng nhiều lần trong một transaction nếu có nhiều cập nhật riêng.

Cần thiết kế chính sách rõ: native SQL là con đường cập nhật chính cho row đó, hay entity-level update là con đường chính? Nếu phải kết hợp, flush trước để đảm bảo thứ tự, thực thi SQL có conflict check, sau đó refresh hoặc kết thúc context phù hợp.

### 13.4. SQL tăng version không thay thế refresh

Sau:

~~~sql
UPDATE inventory_items
SET version = version + 1, available_quantity = 8
WHERE id = 42;
~~~

Java object đang managed vẫn có thể giữ `version = 7` và quantity cũ. `@Version` không phải một kênh thông báo đẩy dữ liệu từ DB vào object. Dùng `refresh` hoặc context mới khi cần state mới.

## 14. Stored procedure, trigger và side effects của database

Một câu SQL nhìn có vẻ chỉ sửa một cột, nhưng database có thể làm nhiều hơn:

- Trigger tự cập nhật `updated_at`.
- Trigger thêm một audit row.
- Stored procedure cập nhật bảng liên quan.
- FK `ON DELETE CASCADE` xóa hàng ở bảng con.
- DB computed/generated column thay đổi.
- Một job ngoài ứng dụng cập nhật trạng thái theo lịch.

### 14.1. Trigger thay đổi field của managed entity

Giả sử trigger luôn gán `updated_at = CURRENT_TIMESTAMP` sau UPDATE.

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);

em.createNativeQuery(
    "update inventory_items set available_quantity = ? where id = ?"
).setParameter(1, 30)
 .setParameter(2, itemId)
 .executeUpdate();

// updatedAt và availableQuantity trong item có thể chưa phản ánh DB.
em.refresh(item);
~~~

Nếu Hibernate mapping một cột generated/on-update có metadata provider-specific, Hibernate có thể nạp lại một số giá trị sau SQL **do chính Hibernate quản lý**, tùy annotation/version. Nhưng không suy luận provider tự biết mọi trigger trong một SQL tùy ý hoặc stored procedure.

### 14.2. Stored procedure cập nhật nhiều bảng

Ví dụ một stored procedure xử lý quyết toán đơn:

~~~java
StoredProcedureQuery procedure = em.createStoredProcedureQuery(
    "close_monthly_accounts"
);

procedure.registerStoredProcedureParameter(
    1, LocalDate.class, ParameterMode.IN
);
procedure.setParameter(1, cutoffDate);
procedure.execute();
~~~

Nếu procedure thay đổi bảng `purchase_orders`, `invoices` và `account_balances`, những entity đã managed tương ứng có thể stale.

Sau procedure:
- Nếu chỉ cần một entity cụ thể, refresh entity đó.
- Nếu nhiều loại entity bị ảnh hưởng, cân nhắc clear/context boundary.
- Nếu L2 cache liên quan dữ liệu có thể stale, dùng invalidation policy thích hợp.
- Kiểm tra procedure tham gia đúng transaction và quyền commit/rollback do ai quản lý.
- Đừng cho rằng flush tự động xảy ra trước mọi stored procedure invocation trong mọi API/version.

### 14.3. ON DELETE CASCADE không gọi entity callbacks

Nếu SQL DELETE parent khiến database cascade xóa child:

~~~sql
DELETE FROM purchase_orders WHERE id = 42;
~~~

Hibernate không tự gọi `@PreRemove` trên từng child chỉ vì database FK đã xóa child. Những child entity đã được load trong context có thể còn tồn tại trong memory; refresh một child đã bị xóa có thể gây exception.

Nên dùng entity-level remove/cascade khi lifecycle callbacks/domain semantics là yêu cầu thiết yếu; khi dùng DB cascade, thiết kế cache/context invalidation và audit theo database.

### 14.4. Một DB trigger không thay thế sự đồng bộ application state

Trigger có thể bảo đảm ràng buộc dữ liệu dưới database, nhưng nếu application tiếp tục trả JSON từ managed object đã cũ, người dùng vẫn nhìn thấy giá trị chưa cập nhật. Quyết định read model phải dựa trên snapshot mới/refresh, không chỉ tin rằng “trigger đã chạy”.

## 15. Second-level cache và query cache: clear không đủ

Giả sử ứng dụng bật L2 cache cho InventoryItem. A mở Session và load Item#42; B dùng JDBC độc lập để UPDATE row mà Hibernate không biết; C mở Session mới và gọi find.

Khả năng cần xem xét:

~~~text
External JDBC / Script
       |
       v
  DB row changed
       |
       | (Không tự gửi invalidation tới Hibernate cache)
       v
L2 cache có thể giữ entry cũ
       |
       v
Session mới vẫn có nguy cơ nhận stale data
~~~

### 15.1. Vì sao em.clear() chỉ xử lý L1?

`em.clear()` detach các managed entities của **một** persistence context. Nó không tự bảo đảm evict entries trong shared L2 cache/query cache của `EntityManagerFactory` hoặc `SessionFactory`.

Nếu dữ liệu bị sửa ngoài đường đi có cache integration, application cần:
- Xác định các entities, collections và query results liên quan.
- Sử dụng cơ chế cache invalidation/eviction phù hợp.
- Hoặc không bật L2/query cache cho dữ liệu được nhiều hệ thống chỉnh sửa mà không có protocol invalidation.
- Thiết kế TTL/event-driven invalidation hoặc cache ownership rõ ràng khi nhiều ứng dụng cùng ghi.

### 15.2. JPA Cache API

Jakarta Persistence có Cache API ở mức EntityManagerFactory:

~~~java
Cache cache = entityManagerFactory.getCache();

// Evict cache entry cho InventoryItem#42 (khi provider/cache hỗ trợ).
cache.evict(InventoryItem.class, 42L);

// Hoặc toàn bộ InventoryItem cache entries.
cache.evict(InventoryItem.class);
~~~

`Cache.evictAll()` có phạm vi lớn và chi phí rõ ràng; không dùng như phản xạ mặc định sau mọi native UPDATE.

Evict L2 **không** làm managed Item#42 trong context hiện tại tự đổi giá trị. Nếu vẫn giữ reference đó, phải refresh/clear/detach theo mục tiêu.

### 15.3. Hibernate cache và query synchronization

Hibernate có các API cache riêng của `SessionFactory` và native query synchronization (ví dụ `addSynchronizedEntityClass`/`addSynchronizedQuerySpace`) tùy version. Những cơ chế này giúp Hibernate quản lý invalidation khi mutation/query đi qua đường tích hợp thích hợp và các query spaces được khai báo.

Đừng nhầm với một JDBC connection/ETL bên ngoài: nếu Hibernate **không nhận được thông tin thay đổi**, nó không thể tự invalidation cache đúng lúc.

### 15.4. Không có một lệnh duy nhất giải quyết tất cả

| Vấn đề | Lệnh/cơ chế có thể phù hợp |
|---|---|
| Managed entity trong L1 stale | `refresh` hoặc `clear`/context mới |
| L2 entity entry stale | Cache eviction/invalidation |
| Cached query result stale | Query cache synchronization/invalidation theo provider |
| DB khác transaction chưa commit | Transaction visibility/isolation; không phải clear |
| Entity pending changes chưa ghi DB | `flush` |
| UI giữ DTO cũ sau commit | Fetch lại hoặc update client/read-model cache |

Mỗi tầng có lifecycle riêng; đồng bộ một tầng không có nghĩa các tầng khác tự đồng bộ.

## 16. Transaction và isolation: refresh không phá luật MVCC

### 16.1. Cùng transaction nhưng object vẫn stale

Giả sử JPA và native SQL dùng cùng transaction:

~~~text
T1: em.find(Item#42)       -> Java quantity=10
T2: native UPDATE          -> DB quantity=5, cùng transaction
T3: item.getQuantity()     -> Java có thể vẫn =10
T4: em.refresh(item)       -> Java quantity=5
T5: commit                 -> DB commit quantity=5
~~~

Ở đây refresh đọc state DB trong transaction hiện tại (giả định row tồn tại). Không có mâu thuẫn với ACID: database state và Java state là hai lớp khác nhau.

### 16.2. Khác transaction và isolation level

Transaction A đã load Item#42; B cập nhật và commit row.

Trong A:
- Getter của managed entity vẫn có thể trả state cũ do L1.
- Nếu A gọi refresh, nó chỉ nhận dữ liệu DB mà isolation/snapshot của transaction A cho phép nhìn thấy.
- Dưới một số implementation của `REPEATABLE READ`/snapshot isolation, A có thể tiếp tục thấy snapshot cũ dù B đã commit.
- Dưới `READ COMMITTED`, câu đọc mới thường có thể thấy bản commit mới, nhưng phải xét locks, DB version và concurrency.
- Không chắc mỗi database đặt tên isolation giống nhau có hành vi giống hệt ở mọi trường hợp.

Đừng cố “ép thấy bản mới” bằng vòng lặp `clear()`/`refresh()` vô hạn trong cùng snapshot transaction. Nếu nghiệp vụ cần trạng thái sau commit mới, hãy dùng transaction boundary phù hợp.

### 16.3. Refresh có thể xóa local state

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.restock(5);           // Thay đổi chưa flush.

em.refresh(item);          // Có thể ghi đè thay đổi restock().
~~~

Nếu mục tiêu là ghi `restock` xuống DB rồi đọc thêm field do trigger tạo, thường phải flush trước refresh (và sau đó refresh theo mapping/DB behavior). Nếu đang cần loại bỏ thay đổi không hợp lệ, refresh có thể là thao tác chủ ý. **Không dùng refresh theo phản xạ mà không biết local modifications nào sẽ bị ghi đè.**

### 16.4. Clear bỏ pending state không tự rollback DB SQL đã chạy

Giả sử native UPDATE đã thực thi, sau đó `em.clear()`:
- Native UPDATE đã gửi DB và vẫn nằm trong transaction; clear không rollback SQL ấy.
- Managed changes chưa được flush có thể bị bỏ.
- Khi transaction commit, SQL đã thực thi có thể commit bình thường.
- Khi transaction rollback, cả SQL đã thực thi và flush trong cùng transaction sẽ rollback theo DB transaction semantics.

`clear()` là quản lý object graph, không phải transaction control.

## 17. Trình tự đặc biệt khi trộn entity changes và SQL trên cùng row

Đây là trường hợp rủi ro nhất vì cả ORM và native SQL đều muốn ghi một row.

### 17.1. Sai hướng: native UPDATE rồi để entity cũ flush sau

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.restock(5); // pending entity update

em.createNativeQuery(
    "update inventory_items set available_quantity = 1 where id = ?"
).setParameter(1, id)
 .executeUpdate();

// Nếu managed update được flush sau native SQL,
// giá trị cuối có thể không còn như ứng dụng kỳ vọng.
~~~

Với `@Version`, việc native SQL có/không cập nhật version còn làm kết quả khác (success/stale exception). Không thể coi thứ tự source code luôn tương đương thứ tự SQL được thực thi.

### 17.2. Một thứ tự có kiểm soát

~~~java
InventoryItem item = em.find(InventoryItem.class, id);

item.restock(5);
em.flush();  // SQL của entity-level update chạy trước.

int affected = em.createNativeQuery(
    """
    update inventory_items
       set available_quantity = available_quantity - ?,
           version = version + 1
     where id = ?
       and available_quantity >= ?
    """
)
.setParameter(1, 2)
.setParameter(2, id)
.setParameter(3, 2)
.executeUpdate();

if (affected != 1) {
    throw new IllegalStateException("Cannot reserve inventory");
}

em.refresh(item); // Đồng bộ quantity/version cho object còn managed.
~~~

Đây là một mô hình có thể hiểu được:
1. Managed changes được flush.
2. Native mutation chạy trên DB state đã được ghi trong transaction.
3. Refresh đọc lại DB state.
4. Commit bởi transaction manager.

Nó không chứng minh rằng nên chia nghiệp vụ thành hai kiểu update. Nếu có thể viết toàn bộ theo entity domain method hoặc một SQL atomic update duy nhất, giải pháp đó thường dễ reasoning hơn.

### 17.3. SQL atomic update trong concurrency

Bài toán giữ quantity không âm thường có thể xử lý bằng một SQL:

~~~sql
UPDATE inventory_items
   SET available_quantity = available_quantity - :delta,
       version = version + 1
 WHERE id = :id
   AND available_quantity >= :delta;
~~~

Điều kiện `available_quantity >= :delta` được database kiểm tra khi thực thi UPDATE theo locking/isolation semantics, thay vì:
1. Query quantity từ Java.
2. Kiểm tra trong Java.
3. UPDATE không có predicate.

Cách hai bước không có lock/optimistic check có thể race khi nhiều request đồng thời. Tuy vậy, SQL atomic UPDATE vẫn phải kết hợp đúng transaction, affected-row handling và context invalidation sau đó.

### 17.4. Nếu có trigger/constraint, cần kiểm tra DB thực tế

SQL UPDATE có thể:
- Bị CHECK constraint từ chối.
- Kích hoạt trigger làm thay đổi field khác.
- Bị optimistic version predicate từ chối.
- Bị deadlock/lock timeout và cần retry có kiểm soát.
- Cập nhật row nhưng application chưa thấy do L1 stale.

Đồng bộ context chỉ là một phần trong thiết kế concurrency/data integrity.


## 18. Native INSERT và DELETE: context không tự biết row đã sinh ra hoặc biến mất

### 18.1. Native INSERT

Giả sử SQL insert một inventory item mới:

~~~java
int inserted = em.createNativeQuery(
    """
    INSERT INTO inventory_items(id, sku, available_quantity, version)
    VALUES (?, ?, ?, 0)
    """
)
.setParameter(1, 501L)
.setParameter(2, "SKU-501")
.setParameter(3, 20)
.executeUpdate();
~~~

`INSERT` đi thẳng tới database. Hibernate không tự tạo `InventoryItem` managed cho ID 501 chỉ vì SQL được thực thi qua EntityManager. Nếu cần entity mới:

~~~java
InventoryItem loaded = em.find(InventoryItem.class, 501L);
~~~

Lệnh find có thể tải row mới (theo transaction/isolation/cache phù hợp), nhưng nếu trước đó context đã quản lý một entity với ID này trong một trạng thái không nhất quán, phải giải quyết xung đột identity/state trước.

Native insert cũng không tự áp dụng `@PrePersist` hoặc `CascadeType.PERSIST` trên Java graph. Các default/generated values của DB phải được đọc lại nếu cần đưa vào response.

### 18.2. Native DELETE

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);

int deleted = em.createNativeQuery(
    "delete from inventory_items where id = ?"
).setParameter(1, itemId)
 .executeUpdate();
~~~

Row ở DB có thể đã bị xóa, nhưng `item` vẫn là Java object đã được tạo và nạp trước đó. Đừng tiếp tục sửa `item` rồi mong Hibernate biết nó không còn trong DB.

Cách xử lý:
- Nếu xóa entity theo domain workflow, ưu tiên `em.remove(item)` khi cần callbacks/cascade.
- Nếu bulk/native DELETE đã được chọn, dùng `em.clear()` hoặc `em.detach(item)` và bỏ reference cũ.
- Không dựa vào `refresh(item)` sau khi row đã bị delete; refresh có thể thất bại vì row không còn.
- Nếu DB cascade xóa thêm child, cân nhắc invalidate những entity/collection/cache khác bị ảnh hưởng.

### 18.3. Entity lifecycle và SQL trực tiếp không thay thế nhau

| Hành động | Đi qua managed entity lifecycle? | Có thể làm L1 stale? |
|---|---|---|
| `em.persist(newEntity)` | Có | ORM quản lý graph theo mapping |
| `em.remove(managedEntity)` | Có | ORM quản lý remove; reference Java vẫn cần dùng cẩn thận |
| `em.createNativeQuery("insert ...")` | Không tạo entity instance | Có, nếu ID/graph đã được load |
| `em.createNativeQuery("delete ...")` | Không remove entity objects theo lifecycle | Có |
| `em.createQuery("delete from Entity ...")` bulk | Không remove từng managed instance | Có |
| JDBC/Procedure/Trigger | Ngoài managed entity lifecycle | Có |

## 19. Quy trình chọn cách đồng bộ theo nhu cầu thực tế

Không có một công thức bắt buộc luôn `flush(); nativeSql(); clear();`. Hãy đặt câu hỏi để chọn đúng phạm vi và giảm chi phí.

### 19.1. Sơ đồ quyết định

~~~text
Bắt đầu: sắp chạy SQL ngoài entity lifecycle
                     |
                     v
       SQL có cần thấy thay đổi
       pending trong persistence context?
                /             \
              CÓ              KHÔNG
              |                 |
       flush trước SQL      Không flush thừa
              |                 |
              +--------+--------+
                       |
                       v
            Thực thi SQL trong
           transaction/connection đúng
                       |
                       v
           SQL có thay đổi row được
           managed trong context?
                 /           \
               CÓ            KHÔNG
               |               |
        Cần dùng state mới?  Không cần reset
          /           \        context
        CÓ            KHÔNG
        |               |
   Một entity?     Có thể kết thúc
     /    \        context bình thường
   CÓ     NHIỀU
   |        |
 refresh  clear / context mới
  hoặc    nếu không làm mất pending state
 detach
                       |
                       v
         Kiểm tra L2/query cache nếu
         thay đổi ngoài Hibernate tracking
                       |
                       v
       Commit / rollback bởi transaction manager
~~~

Trong một số trường hợp, cần refresh nhiều entity riêng lẻ để tránh clear toàn context; hoặc cần tách transaction thành các pha đọc/ghi để giảm risk.

### 19.2. Bảng quyết định nhanh

| Tình huống | Thao tác phù hợp | Vì sao |
|---|---|---|
| Có entity pending changes; native SELECT phải đọc chúng | `flush()` trước SELECT | Đẩy update vào DB cùng transaction |
| SQL UPDATE một row đã load và cần dùng entity ngay | `refresh(item)` sau UPDATE | Cập nhật state Java từ DB |
| Bulk UPDATE nhiều rows; không cần giữ managed entities hiện tại | `flush()` nếu cần, rồi DML, sau đó `clear()` | Tránh stale graph, bảo vệ pending changes |
| Bulk DELETE các rows đã load | Detach/clear, ngừng dùng object cũ | Deleted row không thể refresh như row còn tồn tại |
| Native SQL update qua Session và muốn auto-flush đúng query space | `addSynchronizedEntityClass` / `addSynchronizedQuerySpace` | Khai báo dependency, tùy Hibernate version |
| JdbcTemplate/JPA không cùng transaction | Sửa transaction management | Flush/refresh không làm hai transactions gắn kết |
| SQL ngoài hệ thống sửa entity có L2 cache | Cache eviction/invalidation policy | L2 không tự biết external write |
| Trigger cập nhật timestamp của một entity | `refresh` hoặc mapping generated phù hợp | Giá trị DB có thể khác state Java |
| Chỉ SELECT scalar và không pending changes | Không cần clear | Tránh detach/flush thừa |
| Cần cập nhật business invariant theo entity lifecycle | Dùng managed entity operations | Native SQL bỏ qua callbacks/domain rules |
| Muốn SQL UPDATE atomic chống overselling | Predicate UPDATE/row count/version & transaction | Context synchronization không thay concurrency control |

### 19.3. Chọn giữa refresh và clear

**Ưu tiên refresh** khi:
- Chỉ một vài managed entities liên quan.
- Các object khác trong transaction vẫn cần tiếp tục managed.
- Những entities được refresh còn tồn tại.
- Không có local changes cần giữ trên entities đó, hoặc đã flush có chủ đích.

**Ưu tiên clear/context mới** khi:
- Bulk SQL sửa rất nhiều entity.
- Không cần tiếp tục sử dụng managed graph cũ.
- Đã flush những pending changes cần giữ.
- Cần ranh giới rõ cho một phase xử lý dữ liệu lớn.

**Không dùng clear** khi:
- Caller còn unflushed changes quan trọng.
- Caller trông đợi các reference hiện tại vẫn managed để tiếp tục dirty checking.
- Chưa rõ transaction/context là shared với những service/repository nào.

## 20. Thiết kế transaction để giảm nhu cầu “sửa context”

Một cách hiệu quả để tránh stale state là **đặt SQL ngoại lai ở một transaction/use-case có context ngắn**, thay vì xen kẽ entity changes và native DML liên tục.

### 20.1. Cách khó reasoning

~~~text
Transaction dài:
  load A, B, C
  sửa A
  native SQL sửa A, B
  sửa B
  procedure sửa B, C
  query DTO
  refresh A
  native DELETE C
  sửa A lần nữa
  commit
~~~

Rất khó xác định state nào là nguồn sự thật, flush/refresh xảy ra lúc nào và entity nào stale. Optimistic locking/callbacks cũng trở nên khó kiểm soát.

### 20.2. Cách rõ ràng hơn

~~~text
Use case 1:
  transaction -> load entity -> domain changes -> commit

Use case 2:
  transaction -> native bulk DML -> commit
  (không giữ entity graph cũ)

Use case 3:
  transaction -> đọc DTO mới -> return
~~~

Tách transaction giúp giảm trạng thái cần đồng bộ, nhưng phải cân nhắc atomicity nghiệp vụ. Không tách một thao tác cần atomic thành nhiều transaction độc lập chỉ để code đơn giản nếu điều đó tạo rủi ro dữ liệu không nhất quán.

### 20.3. Nếu bắt buộc phối hợp trong một transaction

Ví dụ vừa cập nhật entity, vừa gọi stored procedure:

~~~java
@Transactional
public void performWorkflow(Long id) {
    InventoryItem item = em.find(InventoryItem.class, id);
    item.restock(10);

    em.flush();

    StoredProcedureQuery procedure = em.createStoredProcedureQuery(
        "recalculate_inventory_totals"
    );
    procedure.execute();

    em.refresh(item);

    // Nếu procedure còn sửa nhiều entity khác đã managed,
    // cần xử lý chúng hoặc dùng context boundary.
}
~~~

Ví dụ chỉ minh họa thứ tự. Stored procedure có thể có parameter, result sets hoặc transaction semantics cần được đăng ký đúng API. Không giả định mọi DB/procedure đều hoạt động giống nhau.

## 21. Cách kiểm chứng bằng integration test

Vì flush mode, native query synchronization và transaction behavior phụ thuộc provider/version/configuration, cần kiểm chứng trên database mục tiêu khi logic dựa vào chúng.

Các thử nghiệm nên dùng **transaction rõ ràng** và **hai quan sát**: managed getter vs DB scalar query.

### 21.1. Test stale managed entity sau native UPDATE

Ý tưởng:

~~~java
@Transactional
void nativeUpdateDoesNotMagicallyChangeManagedObject() {
    InventoryItem item = em.find(InventoryItem.class, 42L);
    int original = item.getAvailableQuantity();

    em.createNativeQuery(
        """
        UPDATE inventory_items
           SET available_quantity = ?,
               version = version + 1
         WHERE id = ?
        """
    )
    .setParameter(1, 73)
    .setParameter(2, 42L)
    .executeUpdate();

    // Không dựa vào getter item như nguồn dữ liệu DB mới.

    em.refresh(item);

    assertEquals(73, item.getAvailableQuantity());
}
~~~

`assertEquals` thuộc JUnit; ví dụ giả định fixture Item#42 tồn tại và transaction/test setup đúng. Không gọi `refresh` trên entity đã bị xóa.

### 21.2. Test flush trước native SELECT

Để kiểm tra thứ tự:
1. Load managed Item.
2. Thay đổi quantity bằng domain method.
3. Gọi explicit flush.
4. Native scalar SELECT lại quantity trên cùng transaction/connection.
5. Assert giá trị đúng.

Điều này kiểm chứng đường xử lý có explicit ordering. Để khảo sát auto-flush, dùng test riêng theo EntityManager/Session và flush mode/version, không trộn vào contract chính của service.

### 21.3. Test clear và detach

- Load Item trước DML.
- Gọi native UPDATE rồi clear.
- Kiểm tra `em.contains(oldItem) == false`.
- Load lại Item và kiểm tra giá trị DB.
- Kiểm tra object cũ không trở thành managed lại chỉ vì một find mới.

Ví dụ:

~~~java
InventoryItem oldItem = em.find(InventoryItem.class, 42L);

// Native SQL update here...

em.clear();

assertFalse(em.contains(oldItem));

InventoryItem fresh = em.find(InventoryItem.class, 42L);
assertNotSame(oldItem, fresh);
~~~

Những assertions này cần fixture và cache configuration phù hợp; test không được giữ một context ngoài ý muốn qua setup steps.

### 21.4. Test shared transaction với JDBC

Khi cùng workflow dùng JdbcTemplate và JPA:

- Xác nhận cả hai đi vào cùng DataSource/transaction resources.
- Thực hiện pending entity change → flush → JDBC SELECT và kiểm chứng dữ liệu.
- Thực hiện JDBC UPDATE → refresh entity → kiểm chứng giá trị.
- Ném exception để xác nhận cả các thay đổi JDBC và JPA rollback cùng nhau.
- Nếu test dùng hai DataSources, không giả định một local transaction manager bao quát cả hai.

### 21.5. Test version conflict

Nếu native SQL cần optimistic locking:
- Load entity version V ở transaction A.
- Native SQL cập nhật row và tăng version ở B theo strategy.
- Cho A thử flush entity update trên version V.
- Xác nhận conflict được phát hiện theo DB/provider semantics.

Đừng mock EntityManager rồi kết luận optimistic locking hoạt động; cần DB constraint/SQL thật.

### 21.6. Query logging và thống kê

Có thể bật logging phù hợp Hibernate/Spring test configuration để xem:
- Khi nào UPDATE xuất hiện trước native SELECT.
- Native DML có xảy ra trước hay sau flush.
- Có query mới sau refresh không.
- Có L1 cache hit hay SQL mới khi find lại không.
- Version predicate/tăng version có được đưa vào SQL entity update không.

Không để logging bind parameters chứa dữ liệu nhạy cảm bật ở production mà không có cơ chế bảo vệ.

## 22. Bảng lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
|---|---|---|
| Native SELECT trả số cũ sau setter | Entity change chưa flush, auto-flush không xảy ra | Flush trước SQL khi cần |
| `find()` trả entity cũ sau native UPDATE | Entity đã có trong L1 identity map | Refresh/clear/context mới |
| Native SELECT scalar thấy mới, getter thấy cũ | Hai lớp state khác nhau | Refresh managed entity nếu cần |
| `clear()` khiến cập nhật entity không được lưu | Pending changes chưa flush | Flush trước clear hoặc thay đổi transaction design |
| `refresh()` làm mất thay đổi Java vừa sửa | Refresh ghi đè local pending state | Flush/đổi thứ tự hoặc tránh refresh |
| Refresh sau native DELETE ném exception | Row đã bị xóa | Không refresh row đã mất; detach/clear |
| Version vẫn cũ sau native UPDATE | SQL bỏ qua `@Version` | Tăng version/predicate tường minh, refresh |
| Entity stale update đè dữ liệu SQL | Native update không làm optimistic check | Thiết kế locking/version strategy |
| Native UPDATE khác transaction không thấy JPA flush | Không cùng connection/resource hoặc isolation | Sửa transaction sharing/commit boundaries |
| `JdbcTemplate` commit nhưng JPA rollback | Transaction managers/resources không phối hợp | Kiểm tra DataSource/JTA/XA/config |
| Trigger đổi timestamp nhưng entity vẫn cũ | Hibernate không tự reread external SQL effects | Refresh hoặc mapping generated phù hợp |
| Native DELETE làm child managed còn trong graph | DB cascade không sync Java context | Clear/detach, reload graph |
| Bulk JPQL không gọi `@PreRemove` | Bulk DML bypass lifecycle callbacks | Dùng entity operations nếu cần |
| `@Modifying(clearAutomatically=true)` gây detached objects | Clear toàn persistence context | Cân nhắc refresh/call boundary và flushAutomatically |
| Session native query không auto-flush như kỳ vọng | Thiếu synchronization info hoặc flush mode | Explicit flush/query spaces theo version |
| EntityManager native query flush sớm | FlushMode.AUTO và provider behavior | Hiểu contract, sắp transaction/SQL |
| L2 cache vẫn stale sau clear | Clear chỉ xóa L1 | L2/query cache invalidation |
| Refresh không thấy transaction B đã commit | Isolation/snapshot vẫn giữ dữ liệu cũ | Dùng transaction mới hoặc isolation đúng |
| SQL UPDATE fail FK/CHECK constraint | DB bảo vệ referential/integrity | Sửa dữ liệu/schema/logic, không chỉ flush |
| Native UPDATE affectedRows = 0 | Predicate không thỏa hoặc thiếu row | Kiểm tra logic và trả lỗi nghiệp vụ đúng |
| SQL chạy sai thứ tự giữa pending changes và DML | Flush timing chưa được kiểm soát | Flush rõ ràng và tránh cùng-row dual writes |
| Session dùng sau khi close | Entity references detached/Session unavailable | Lifecycle/context boundary đúng |

## 23. Bài tập tự luyện

### Bài 1 — Nhận biết hai chiều đồng bộ

Một entity đã sửa trong Java nhưng SQL SELECT cần nhìn trạng thái mới.

**Câu hỏi:** dùng `flush()`, `refresh()` hay `clear()`?

**Đáp án:** thường cần `flush()` trước SQL (cùng transaction phù hợp), vì đó là chiều managed state → database.

### Bài 2 — Native UPDATE và stale entity

Code đã load Item#42, sau đó native SQL đổi quantity từ 10 thành 8, getter vẫn 10.

**Câu hỏi:** đây là lỗi database hay L1 state?

**Đáp án:** có thể là persistence context giữ managed state cũ. Dùng refresh hoặc clear/load lại tùy phạm vi.

### Bài 3 — Refresh mất pending changes

~~~java
item.restock(10);
em.refresh(item);
~~~

**Câu hỏi:** `restock(10)` có được bảo toàn không?

**Định hướng:** không chắc; refresh có thể ghi đè local changes chưa flush. Đổi thứ tự theo mục tiêu nghiệp vụ.

### Bài 4 — Clear sau bulk SQL

Bulk SQL sửa 10.000 Items; service không cần dùng các entity managed cũ.

**Câu hỏi:** refresh 10.000 entities hay clear?

**Định hướng:** clear/context mới thường hợp lý hơn, nhưng phải xử lý pending changes trước khi clear và hiểu tác động lên toàn context.

### Bài 5 — Truy vấn EntityManager vs Session

Native SELECT chạy sau managed changes ở chế độ AUTO, behavior khác giữa EntityManager và Session.

**Câu hỏi:** có thể khẳng định mọi native query luôn auto-flush không?

**Đáp án:** không. Kiểm tra API/version/flush mode/query synchronization; dùng explicit flush nếu correctness phụ thuộc thứ tự.

### Bài 6 — Version không được tăng

Native SQL cập nhật quantity nhưng giữ nguyên version. Một managed entity cũ sau đó ghi lại row.

**Câu hỏi:** `@Version` chắc chắn ngăn lost update không?

**Đáp án:** không. Native write phải tham gia chiến lược version/locking phù hợp.

### Bài 7 — JDBC không cùng connection

JPA transaction A đã flush nhưng JdbcTemplate dùng connection/transaction B chưa nhìn thấy dữ liệu mới.

**Câu hỏi:** có nên gọi thêm `refresh` hoặc `clear` không?

**Đáp án:** không giải quyết transaction visibility. Cần kiểm tra DataSource/transaction manager/isolation và commit boundaries.

### Bài 8 — Stored procedure cập nhật bảng khác

Procedure sửa Orders, Invoices và Balances. Service trước đó load một Invoice và một Balance.

**Câu hỏi:** entity getters có tự phản ánh dữ liệu mới không?

**Đáp án:** không được mặc định. Refresh từng entity cần dùng hoặc clear/context mới; xử lý cache ngoài L1 nếu có.

### Bài 9 — SQL DELETE

Native SQL xóa Item#42, còn managed Item#42 nằm trong context.

**Câu hỏi:** refresh entity này có phải giải pháp chuẩn không?

**Đáp án:** không. Row đã bị xóa; refresh có thể ném exception. Detach/clear và không dùng reference cũ.

### Bài 10 — Spring Data @Modifying

~~~java
@Modifying(clearAutomatically = true)
@Query("update InventoryItem i set i.availableQuantity = 0")
int resetAll();
~~~

**Câu hỏi:** có rủi ro nào khi caller còn entity changes pending?

**Định hướng:** clear có thể bỏ pending changes. Cân nhắc `flushAutomatically = true`, explicit flush hoặc transaction design; không bật cờ mù quáng.

### Bài 11 — Caches

External ETL sửa DB trong khi L2 cache bật. Service mở EntityManager mới, `find()` có thể nhận dữ liệu cũ.

**Câu hỏi:** vì sao `clear()` ở EntityManager cũ chưa đủ?

**Đáp án:** clear chỉ xử lý L1. Cần invalidation L2/query cache hoặc chính sách ownership phù hợp.

### Bài 12 — READ COMMITTED vs snapshot

Transaction A refresh entity nhưng vẫn thấy giá trị cũ sau khi B commit.

**Câu hỏi:** có thể là do Hibernate lỗi không?

**Định hướng:** chưa đủ kết luận; phải kiểm tra DB isolation/snapshot semantics và context state. Transaction A có thể không nhìn thấy commit mới theo isolation level.

### Bài 13 — Atomic UPDATE

Hai request cùng muốn trừ 7 đơn vị từ tồn kho 10.

**Câu hỏi:** phương án SELECT quantity trong Java rồi UPDATE không predicate có an toàn không?

**Đáp án:** không mặc định. Dùng SQL atomic UPDATE với `available_quantity >= :delta`, affected rows và version/locking strategy phù hợp.

### Bài 14 — Query spaces

Hibernate Session native query đọc bảng inventory_items, nhưng code vừa sửa entity InventoryItem chưa flush.

**Câu hỏi:** `addSynchronizedEntityClass(InventoryItem.class)` giúp gì?

**Định hướng:** cung cấp dependency metadata để Hibernate xét auto-flush và query cache synchronization theo version. Nó không tự refresh managed entity sau SQL DML.

### Bài 15 — Chọn thao tác tối thiểu

Service chỉ chạy native SELECT scalar, không có entity changes pending và không giữ managed graph cần làm mới.

**Câu hỏi:** có cần `flush(); clear();` không?

**Đáp án:** không cần như một công thức bắt buộc. Chỉ thực hiện đồng bộ khi có dependency hay stale state cần xử lý.

### Bài 16 — Native INSERT

JDBC INSERT một row mới, code gọi `em.find` sau đó.

**Câu hỏi:** Hibernate có tự gọi `@PrePersist` cho row này không?

**Đáp án:** không. SQL INSERT trực tiếp bypass Java entity persist lifecycle. Find chỉ nạp row theo mapping/transaction visibility.

### Bài 17 — Hai nguồn ghi một row

Trong transaction, managed Item được sửa, rồi native SQL cũng sửa quantity. Không có explicit flush order.

**Câu hỏi:** rủi ro lớn nhất?

**Định hướng:** SQL execution order có thể khác giả định; stale entity/optimistic conflicts/ghi đè. Thiết kế một nguồn ghi chính hoặc explicit flush → SQL → refresh và version checking.

## 24. Tổng kết

Khi SQL chạy ngoài cơ chế quản lý từng entity của Hibernate, hãy tách hai vấn đề:

**Trước SQL:** có pending entity changes mà SQL cần thấy không? Nếu có, `flush()` trong transaction phù hợp để đưa thay đổi xuống database.

**Sau SQL:** câu SQL có thay đổi row mà Hibernate đang quản lý không? Nếu có, state Java có thể stale. Dùng `refresh(entity)` khi cần làm mới một entity còn tồn tại; dùng `clear()` hoặc context mới khi bulk SQL ảnh hưởng nhiều entity và không cần giữ managed graph cũ. `detach(entity)` là lựa chọn phạm vi nhỏ khi muốn loại một entity khỏi context.

Những ghi nhớ quan trọng:

1. Persistence context là **identity map/first-level cache**, không phải database snapshot tự đồng bộ mọi thay đổi ngoài ORM.
2. `flush` khác `commit`: SQL đã thực thi không có nghĩa transaction đã commit.
3. `refresh` có thể ghi đè thay đổi Java chưa flush.
4. `clear` detach toàn bộ managed objects và có thể làm mất pending changes; không dùng tùy tiện trong shared transaction.
5. Native SQL, JDBC, stored procedures, DB triggers, FK cascades và JPQL/HQL bulk DML đều có thể tạo stale state.
6. `@Version` không tự bảo vệ những câu native UPDATE bỏ qua version strategy.
7. Hibernate NativeQuery query-space synchronization hỗ trợ auto-flush/cache coordination, **không** là lệnh reload Java objects.
8. `EntityManager.clear()` không mặc định evict second-level cache/query cache.
9. Transaction isolation có thể ngăn refresh nhìn thấy cập nhật từ transaction khác; context refresh không phá quy tắc MVCC.
10. Đặt rõ transaction/connection boundary và ưu tiên thiết kế ít nguồn ghi vào cùng row trong một unit of work.

Một cách nhớ cuối cùng:

~~~text
              FLUSH
Managed entity -------> Database
       ^                   |
       |                   |
       +------ REFRESH ----+
            một entity

CLEAR:     ngừng quản lý tất cả entity hiện có trong context.
DETACH:    ngừng quản lý một entity.
COMMIT:    xác nhận transaction, KHÔNG thay thế refresh/clear.
EVICT L2:  giải quyết cache dùng chung, KHÔNG thay thế refresh L1.
~~~

### Tài liệu tham khảo chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — persistence context, flush mode, refresh, clear, detach, native queries và bulk DML.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/) — `EntityManager`, `FlushModeType`, `Cache` và lifecycle contracts.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — Session, persistence context, flushing, native SQL, synchronizations và cache theo phiên bản.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — phần flushing, native SQL queries, synchronization và bulk update/delete.
- [Hibernate ORM 6.6 NativeQuery Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/NativeQuery.html) — `addSynchronizedEntityClass`, `addSynchronizedQuerySpace` và native query APIs.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repository modifying queries và transaction.
- [Spring Data JPA @Modifying Javadoc](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html) — `flushAutomatically`, `clearAutomatically`.

> Những đoạn code minh họa giả định API/driver/schema tương ứng. Hành vi auto-flush của native query, query-space synchronization, result type và cache invalidation có thể khác giữa Hibernate 5/6/7, EntityManager/Session và flush modes. Khi triển khai thực tế, xác nhận bằng integration test trên đúng database, Hibernate version, Spring transaction manager và cache configuration của dự án.
