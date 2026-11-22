# Kiểm thử hai giao dịch cập nhật cùng một entity trong JPA

**Khóa lạc quan (optimistic locking)** giải quyết một vấn đề rất thực tế trong hệ thống nhiều người dùng: hai giao dịch cùng đọc một entity, cùng thay đổi dữ liệu và cố ghi vào database. Nếu không kiểm soát xung đột, bản cập nhật sau có thể ghi đè bản cập nhật trước mà người dùng không hay biết — một dạng **lost update**.

Jakarta Persistence (JPA) hỗ trợ kiểm tra phiên bản entity bằng `@Version`. Để hiểu và sử dụng đúng cơ chế này, cần kiểm thử **hai giao dịch thật sự độc lập** cùng làm việc với một entity đã được versioned, thay vì chỉ gọi `find()` hai lần trong cùng một `EntityManager`.

Bài học thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Khóa lạc quan**, tập trung vào **“Kiểm thử hai giao dịch cập nhật cùng một entity”**. Nội dung trình bày mô hình version, cách tổ chức hai persistence contexts, một bài integration test bằng JUnit 5, vị trí phát hiện `OptimisticLockException`, rollback, kiểm chứng trạng thái cuối cùng, test đa luồng, Spring transactions và các lỗi kiểm thử thường gặp.

**Kết quả cần chứng minh:** khi T1 và T2 cùng đọc phiên bản V, T1 ghi và commit trước, thì T2 không được âm thầm ghi đè dữ liệu bằng state chứa phiên bản V đã cũ.

---

## 1. Tình huống lost update

Giả sử database có mặt hàng:

| id | sku | quantity | version |
| ---: | --- | ---: | ---: |
| 101 | SKU-A | 10 | 3 |

Hai giao dịch:

~~~text
Thời điểm     Giao dịch T1                Giao dịch T2
---------     ------------                ------------
t1            Đọc quantity=10,
              version=3

t2                                         Đọc quantity=10,
                                           version=3

t3            Đổi quantity=15

t4                                         Đổi quantity=7

t5            UPDATE thành công
              COMMIT, version -> 4

t6                                         UPDATE với version=3
                                           Không còn row phù hợp
                                           -> optimistic conflict

t7            Giá trị DB vẫn là 15
~~~

Nếu không có version check và database cho phép cả hai updates hoàn tất, T2 có thể lưu `7` sau khi T1 đã lưu `15`. Kết quả của T1 bị mất.

`@Version` làm cho thao tác stale update bị phát hiện, nhưng **không quyết định thay người dùng** liệu quantity nên là 15, 7 hay một giá trị được hợp nhất.

### 1.1. Những bằng chứng bài test phải có

Một bài test đúng nên xác nhận:

1. Entity có version field được JPA quản lý.
2. Fixture được ghi và commit **trước** hai giao dịch cạnh tranh.
3. T1 và T2 có **hai EntityManager/persistence contexts** riêng.
4. Cả hai đọc cùng entity ID và **cùng version ban đầu**.
5. Cả hai đều tạo thay đổi thật sự trên managed entity.
6. T1 flush/commit thành công.
7. T2 cố flush/commit với version cũ và bị từ chối.
8. Test nhận diện đúng lỗi optimistic locking, kể cả khi nó bị wrapper.
9. Transaction T2 được rollback/dọn dẹp.
10. Một context mới đọc lại database và thấy giá trị đã commit của T1.
11. Test không nhầm exception khóa database/connection với optimistic conflict.
12. Test không dựa vào `Thread.sleep()` hoặc lịch chạy ngẫu nhiên.

Đây là **integration test**, bởi mock `EntityManager` không thể kiểm chứng SQL UPDATE, affected-row count và hành vi transaction của một JPA provider thực.

## 2. Khai báo entity với @Version

Ví dụ dùng Java 17+, `jakarta.persistence.*`:

~~~java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                "quantity cannot be negative"
            );
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity < 0) {
            throw new IllegalArgumentException(
                "quantity cannot be negative"
            );
        }
        this.quantity = newQuantity;
    }
}
~~~

Ý nghĩa:

- `@Id` quản lý identity.
- `@Version` báo cho provider biết field nào dùng kiểm tra optimistic concurrency.
- `quantity` là trường mà hai giao dịch cùng muốn thay đổi.
- `changeQuantity(...)` thay đổi object Java managed; SQL có thể chỉ được gửi khi flush.
- `version` **không có public setter**, vì application không nên tự nâng phiên bản để vượt cơ chế kiểm tra.

Có thể dùng các kiểu version phù hợp với Jakarta Persistence/provider. Ví dụ dùng `Long` để dễ quan sát; đừng suy luận mọi provider/version type khởi tạo hoặc tăng giống hệt nhau.

### 2.1. Schema minh họa

Với PostgreSQL:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(255) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_quantity_nonnegative
        CHECK (quantity >= 0)
);
~~~

Schema ví dụ chỉ minh họa. Trong dự án thật, chạy migration phù hợp với database, provider và chiến lược sinh ID/version được sử dụng.

**Không hardcode version ban đầu bằng `0` trong assertion.** Hãy persist fixture, commit rồi đọc giá trị version thực.

## 3. Cơ chế SQL khi optimistic locking hoạt động

Giả sử T1 đã đọc:

~~~text
id=101, quantity=10, version=3
~~~

Một SQL mà JPA provider có thể phát sinh khi update:

~~~sql
UPDATE inventory_items
SET quantity = ?,
    version = ?
WHERE id = ?
  AND version = ?;
~~~

T1 bind giá trị mới, điều kiện old version:

~~~text
quantity mới = 15
version mới  = 4
id           = 101
version cũ   = 3
~~~

Sau khi T1 commit, database lưu version mới. T2 vẫn giữ version cũ nên:

~~~sql
UPDATE inventory_items
SET quantity = 7,
    version = 4
WHERE id = 101
  AND version = 3;
~~~

không khớp row nào, nếu giá trị hiện hành là version 4. Provider nhận biết stale update và báo lỗi optimistic locking.

**Đây là SQL minh họa.** Provider có thể tạo SQL khác về alias, thứ tự cột, cách binding hoặc version strategy. Điều cốt lõi là **bản cập nhật dựa trên version đã đọc không được phép ghi đè entity đã được cập nhật bởi giao dịch khác**.

### 3.1. Không được tự sửa @Version

Sai:

~~~java
item.setVersion(item.getVersion() + 1);
~~~

Một ứng dụng không nên cung cấp setter để tự chỉnh version với mục đích “chữa conflict”. JPA provider chịu trách nhiệm quản lý giá trị version của entity.

### 3.2. Version là cấp entity

Nếu cả hai transactions cùng sửa một row entity nhưng sửa **hai field khác nhau**, version check vẫn có thể báo conflict. Nó không chỉ so sánh những field có cùng tên mà hai giao dịch đã đụng tới.

Nếu T1/T2 sửa **hai entity khác nhau**, mỗi entity có version riêng; không tự phát sinh conflict chỉ vì cùng table hoặc cùng request.

---

## 4. Hai EntityManager thật sự cần thiết

Trong một persistence context:

~~~java
InventoryItem itemA = em.find(InventoryItem.class, id);
InventoryItem itemB = em.find(InventoryItem.class, id);

System.out.println(itemA == itemB); // Thường là true.
~~~

Theo identity map của JPA, hai lần tìm cùng entity identity trong một context thường trả cùng managed instance.

Nếu sửa `itemA` rồi sửa `itemB`, đó có thể chỉ là thay đổi cùng một object trước một transaction commit, **không có hai snapshots độc lập**.

Để kiểm thử conflict:

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();
~~~

Mỗi EntityManager có persistence context riêng:

~~~text
          EntityManager em1        EntityManager em2
                  |                        |
                  v                        v
           InventoryItem#101        InventoryItem#101
           quantity=10              quantity=10
           version=3                version=3
                  |                        |
                  +------- DATABASE -------+
~~~

Hai instance có cùng entity ID nhưng là **hai Java objects độc lập**. Chúng giữ version snapshot tương ứng với lần đọc ở mỗi transaction.

### 4.1. Transaction khác cũng phải rõ ràng

~~~java
em1.getTransaction().begin();
em2.getTransaction().begin();
~~~

Đây là mô hình `RESOURCE_LOCAL`. Với JTA/Spring, transaction do container/transaction manager tạo; không trộn `EntityTransaction` vào một JTA-managed EntityManager.

### 4.2. Không cần hai thread cho test đầu tiên

Hai EntityManager trên **cùng test thread** nhưng giao dịch độc lập vẫn có thể tái hiện lost-update interleaving. Điều quan trọng là **thứ tự đọc và ghi**, không phải cứ có hai Java threads mới có optimistic conflict.

Test tuần tự có điều phối giúp giảm flaky behavior và tách version conflict khỏi lock-wait test.

## 5. Kịch bản test cần điều phối

~~~text
Fixture: persist entity quantity=10, commit
                     |
        +------------+-------------+
        |                          |
        v                          v
    em1.begin()                em2.begin()
        |                          |
        v                          v
    find(id)                     find(id)
    version=V                    version=V
        |                          |
        v                          v
  quantity=15                 quantity=7
        |                          |
        v                          |
    em1.flush()                    |
    em1.commit()                   |
    version -> V'                  |
        |                          v
        +--------------------> em2.flush/commit
                                   |
                                   v
                           Optimistic conflict
                                   |
                                   v
                            rollback and close
                                   |
                                   v
                    New EntityManager reads quantity=15
~~~

**Thứ tự không thể thiếu:** cả hai đã đọc version V **trước khi** T1 commit. Nếu em2 chỉ đọc sau T1 commit, em2 có thể nhận version V' và ghi thành công như một cập nhật tuần tự hợp lệ.

---

## 6. Cấu hình JPA để kiểm thử tích hợp

Một persistence unit `RESOURCE_LOCAL` trong `META-INF/persistence.xml` có thể được cấu hình:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="optimistic-lock-test"
        transaction-type="RESOURCE_LOCAL">

        <class>
            com.example.inventory.domain.InventoryItem
        </class>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.postgresql.Driver"/>

            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:postgresql://localhost:5432/jpa_test"/>

            <property
                name="jakarta.persistence.jdbc.user"
                value="jpa_test"/>

            <property
                name="jakarta.persistence.jdbc.password"
                value="test-environment-only"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Cấu hình chỉ nhằm minh họa một **database test cô lập**. Trong hệ thống thực, đọc thông tin kết nối từ secrets/test environment và sử dụng provider/JDBC driver/migrations tương thích.

Test này cần:

- Một database đã có bảng `inventory_items`.
- EntityManagerFactory và JPA provider được khởi tạo.
- Hai EntityManager riêng.
- Hai transaction được commit/rollback rõ ràng.
- JUnit 5.
- Mỗi test nên có fixture riêng để tránh cạnh tranh giữa các test song song.

### 6.1. Vì sao không dùng mock?

Mock có thể làm cho:

~~~java
when(entityManager.find(...)).thenReturn(fakeEntity);
~~~

trả về hai objects. Nhưng mock không thực thi SQL `UPDATE ... WHERE version`, không đếm affected rows và không thực hiện transaction commit.

**Mock dùng để test business branches, không phải bằng chứng optimistic locking của ORM/database.**

---

## 7. Helper tạo fixture và dọn dẹp transaction

Ví dụ một class kiểm thử với JUnit 5:

~~~java
package com.example.inventory.test;

import com.example.inventory.domain.InventoryItem;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.OptimisticLockException;
import jakarta.persistence.Persistence;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OptimisticLockIntegrationTest {

    private static EntityManagerFactory emf;

    @BeforeAll
    static void init() {
        emf = Persistence.createEntityManagerFactory(
            "optimistic-lock-test"
        );
    }

    @AfterAll
    static void destroy() {
        if (emf != null && emf.isOpen()) {
            emf.close();
        }
    }

    private Long createFixture(int quantity) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            InventoryItem item = new InventoryItem(
                "SKU-" + java.util.UUID.randomUUID(),
                quantity
            );

            em.persist(item);
            em.flush();

            Long id = item.getId();

            em.getTransaction().commit();
            return id;
        } catch (RuntimeException ex) {
            rollbackIfActive(em);
            throw ex;
        } finally {
            em.close();
        }
    }

    private static void rollbackIfActive(EntityManager em) {
        if (em != null
                && em.isOpen()
                && em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
    }

    private static boolean hasOptimisticLockCause(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof OptimisticLockException) {
                return true;
            }
        }
        return false;
    }

    // Phương thức @Test sẽ được thêm bên dưới.
}
~~~

Những điểm quan trọng:

- Fixture **được commit trước** hai transactions đang cạnh tranh.
- ID không bị hardcode; `GenerationType.IDENTITY` có thể cần INSERT khi persist/flush.
- SKU là giá trị riêng cho từng test.
- Rollback được thực hiện nếu transaction còn active.
- `hasOptimisticLockCause` hỗ trợ wrapper ở tầng commit.
- Các helper phục vụ kiểm thử **JPA resource-local**, không dùng `em.getTransaction()` trên JTA-managed context.

## 8. Test hoàn chỉnh: T1 thành công, T2 bị conflict

Thêm vào class ở trên:

~~~java
@Test
void staleSecondTransactionCannotOverwriteFirstCommit() {

    Long id = createFixture(10);

    EntityManager em1 = emf.createEntityManager();
    EntityManager em2 = emf.createEntityManager();

    Long originalVersion;

    try {
        em1.getTransaction().begin();
        em2.getTransaction().begin();

        // Cùng đọc trước khi bên nào commit.
        InventoryItem fromT1 =
            em1.find(InventoryItem.class, id);

        InventoryItem fromT2 =
            em2.find(InventoryItem.class, id);

        assertNotNull(fromT1);
        assertNotNull(fromT2);

        assertNotSame(
            fromT1,
            fromT2,
            "Each context must hold an independent instance"
        );

        originalVersion = fromT1.getVersion();

        assertEquals(
            originalVersion,
            fromT2.getVersion(),
            "Both transactions must read version V"
        );

        assertEquals(10, fromT1.getQuantity());
        assertEquals(10, fromT2.getQuantity());

        // Hai thay đổi thật sự.
        fromT1.changeQuantity(15);
        fromT2.changeQuantity(7);

        // Giao dịch thứ nhất thắng.
        em1.flush();
        em1.getTransaction().commit();

        // Giao dịch thứ hai vẫn mang version V cũ.
        RuntimeException conflict = assertThrows(
            RuntimeException.class,
            () -> {
                em2.flush();
                em2.getTransaction().commit();
            }
        );

        assertTrue(
            hasOptimisticLockCause(conflict),
            "Expected an optimistic lock failure"
        );

    } finally {
        rollbackIfActive(em2);
        rollbackIfActive(em1);

        em2.close();
        em1.close();
    }

    // Dùng context hoàn toàn mới để xem database.
    EntityManager verify = emf.createEntityManager();

    try {
        InventoryItem persisted =
            verify.find(InventoryItem.class, id);

        assertNotNull(persisted);

        assertEquals(
            15,
            persisted.getQuantity(),
            "T2 must not overwrite T1"
        );

        assertNotEquals(
            originalVersion,
            persisted.getVersion(),
            "A committed update must change the version"
        );
    } finally {
        verify.close();
    }
}
~~~

Kịch bản này cần điều kiện:

- T1/T2 bắt đầu transactions độc lập.
- Cả hai cùng đọc version V trước khi T1 ghi.
- T1 thay quantity thành 15 và commit.
- T2 cố đưa quantity về 7 dựa trên version V.
- T2 bị từ chối.
- Data cuối là 15.

**Đây là ví dụ kiểm thử tích hợp, không phải kết quả đã thực thi trong bài.** Để chạy, cần cấu hình persistence unit, database và dependency phù hợp.

### 8.1. Vì sao assertNotSame?

~~~java
assertNotSame(fromT1, fromT2);
~~~

khẳng định đây là hai Java object độc lập được quản lý trong hai contexts. Nếu test vô tình dùng lại một EntityManager, assertion có thể làm lộ lỗi thiết kế trước khi đến bước optimistic check.

### 8.2. Vì sao assertEquals(version, version)?

~~~java
assertEquals(fromT1.getVersion(), fromT2.getVersion());
~~~

xác nhận cả hai giao dịch làm việc từ **một snapshot version**. Nếu T2 đã đọc version mới sau khi T1 commit, bài test không còn là stale update.

### 8.3. Vì sao quantity khác nhau?

~~~java
fromT1.changeQuantity(15);
fromT2.changeQuantity(7);
~~~

Hai giá trị khác với giá trị ban đầu, nên provider có cơ sở đánh dấu entity dirty và phát UPDATE. Nếu cả hai chỉ gán lại quantity=10, dirty checking có thể xem đây là no-op và không có optimistic update để kiểm thử.

### 8.4. Vì sao đọc lại bằng verify EntityManager?

`fromT2.getQuantity()` vẫn có thể là 7 sau rollback — đó chỉ là trạng thái của Java object đã được gán, **không phải dữ liệu database**.

Một context mới giúp xác minh giá trị đã commit thật sự. Nếu ứng dụng dùng second-level cache, cần biết cơ chế cache/invalidation hoặc có bước kiểm chứng trực tiếp ở database cho test đòi hỏi xác minh state vật lý.

---

## 9. Lỗi có thể xuất hiện ở flush hoặc commit

Trong JPA:

- `changeQuantity(...)` sửa managed state.
- `flush()` đồng bộ dirty changes thành SQL.
- `commit()` hoàn tất giao dịch; provider có thể flush trước commit.

Xung đột optimistic có thể được nhận diện khi SQL UPDATE được thực thi trong flush, hoặc ở giai đoạn hoàn tất transaction, tùy provider.

| Vị trí | Tình huống |
| --- | --- |
| `em2.flush()` | Provider gửi stale UPDATE và phát hiện zero-row update |
| `em2.getTransaction().commit()` | Provider flush/check trong commit, có thể bọc exception |
| JPQL query chen giữa | AUTO flush có thể xảy ra trước SELECT |
| `em.lock(entity, OPTIMISTIC)` | Kiểm tra version có thể được trì hoãn theo semantics locking |

Vì vậy test dùng:

~~~java
RuntimeException error = assertThrows(
    RuntimeException.class,
    () -> {
        em2.flush();
        em2.getTransaction().commit();
    }
);
~~~

Sau đó **kiểm tra cause chain** để không coi mọi RuntimeException là optimistic conflict.

### 9.1. OptimisticLockException và RollbackException

Các loại thường gặp:

~~~java
jakarta.persistence.OptimisticLockException
jakarta.persistence.RollbackException
~~~

Một implementation có thể ném `OptimisticLockException` trực tiếp; implementation khác có thể ném `RollbackException` ở commit, chứa optimistic cause.

Test **không nên chỉ assert một top-level class** nếu mục tiêu là portable trên nhiều providers/versions. Nhưng test cũng **không được chấp nhận lỗi bất kỳ** như SQL syntax, connection timeout, missing column hoặc constraint violation.

### 9.2. Kiểm tra helper cause chain

~~~java
private static boolean hasOptimisticLockCause(
        Throwable error) {
    for (Throwable t = error; t != null; t = t.getCause()) {
        if (t instanceof OptimisticLockException) {
            return true;
        }
    }
    return false;
}
~~~

Đây là cách nhận diện ở tầng **JPA trực tiếp**. Trong Spring, framework có thể dịch exception thành một lớp khác như `ObjectOptimisticLockingFailureException`; test qua service cần điều chỉnh assertion phù hợp contract của tầng đó.

## 10. Vì sao không cho T2 flush khi T1 chưa commit?

Một trình tự khó kiểm thử:

~~~text
T1 đọc V
T2 đọc V
T1.flush()  -> UPDATE, giữ lock row
T2.flush()  -> UPDATE cùng row khi T1 chưa commit
~~~

T2 có thể **bị chặn bởi row lock**, hoặc database trả lock timeout, deadlock hay serialization error. Điều đó chưa chắc là lỗi `@Version` mà test muốn chứng minh.

Để kiểm tra stale optimistic version một cách xác định:

1. T1 và T2 cùng đọc V.
2. T1 flush và **commit thành công**.
3. Chỉ sau đó T2 mới thử flush/commit.

Khi T1 đã commit, T2 kiểm tra version cũ trên database hiện tại, và rủi ro test bị treo do row lock của T1 được giảm đi.

### 10.1. Database isolation có thể ảnh hưởng lỗi

Nếu dùng mức isolation cao như REPEATABLE READ hoặc SERIALIZABLE, một số database có thể phát lỗi cập nhật đồng thời/serialization thay vì trình tự kiểm tra version như ở READ COMMITTED.

Đừng khẳng định mọi database luôn trả một lớp exception/SQLState giống nhau. Với bài kiểm thử tập trung `@Version`, dùng provider/database và isolation được xác định, quan sát SQL và kiểm tra exception đúng nghĩa.

---

## 11. Ba kịch bản đối chứng

Để hiểu optimistic locking, nên có cả test bị conflict lẫn test không conflict.

### 11.1. Kịch bản A — T1 thắng, T2 stale

~~~text
T1 read V
T2 read V
T1 update/commit -> V'
T2 update -> conflict
DB cuối = T1
~~~

Đây là **bài test chính**.

### 11.2. Kịch bản B — T2 thắng, T1 stale

~~~text
T1 read V
T2 read V
T2 update/commit -> V'
T1 update -> conflict
DB cuối = T2
~~~

Optimistic locking không thiên vị transaction tên T1 hay T2; **bên ghi thành công trước** theo điều kiện version có thể thắng.

### 11.3. Kịch bản C — hai updates tuần tự hợp lệ

~~~text
T1 read V
T1 update/commit -> V'
T2 read V'
T2 update/commit -> V''
~~~

Không có stale version. Cả hai giao dịch có thể thành công.

Điểm rút ra: **hai transaction cùng sửa một ID không đủ tạo conflict**. Phải có tình huống *both read the same old version*.

## 12. Thay đổi no-op có thể không tạo update

Nếu ứng dụng gọi:

~~~java
item.changeQuantity(item.getQuantity());
~~~

giá trị không đổi. Provider có thể không phát SQL UPDATE vì entity không dirty, và không có stale UPDATE để báo lỗi.

Trong test, chọn hai giá trị khác nhau và khác fixture:

~~~java
int original = 10;
int t1Value = 15;
int t2Value = 7;
~~~

Nếu muốn kiểm tra version dù entity không thay đổi, xem lock mode `OPTIMISTIC`/`OPTIMISTIC_FORCE_INCREMENT` theo semantics JPA; đó là một use case khác với dirty update conflict.

## 13. Sau exception phải rollback

Không làm:

~~~java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    // Bỏ qua, tiếp tục commit.
}

em.getTransaction().commit();
~~~

Sau optimistic failure, transaction có thể rollback-only hoặc không còn phù hợp để commit. Dữ liệu trong context có thể stale và thay đổi Java đã thực hiện vẫn tồn tại trên object.

Xử lý:

~~~java
try {
    em.flush();
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
~~~

Khi muốn retry, **không tái sử dụng transaction/context lỗi**. Mở một unit of work mới, đọc lại state mới và quyết định nghiệp vụ lại từ đầu.

### 13.1. Rollback không quay ngược object Java

Sau rollback:

~~~java
fromT2.getQuantity(); // Có thể vẫn là 7.
~~~

Nhưng DB có thể đang là 15. Đừng suy luận state database từ object đã tham gia một transaction thất bại.

## 14. Spring @Transactional: lưu ý transaction scope

Trong Spring, các phương thức service thường có:

~~~java
@Transactional
public void changeQuantity(Long id, int quantity) {
    InventoryItem item = em.find(
        InventoryItem.class,
        id
    );
    item.changeQuantity(quantity);
}
~~~

Nếu gọi hai lần trong **cùng một transaction**, đó không phải hai competing transactions. Ngoài ra, một method test gắn `@Transactional` có thể bao mọi thao tác setup/act/assert trong một context khiến test sai mục tiêu.

Cần kiểm soát transaction bằng:

- Hai calls qua service/proxies với boundaries thực sự riêng.
- `TransactionTemplate` hoặc propagation `REQUIRES_NEW`.
- Hai EntityManager `RESOURCE_LOCAL` độc lập như bài test chính.
- Test integration nhiều thread với mỗi thread có transaction manager scope riêng.

### 14.1. Spring exception translation

Khi optimistic exception đi qua Spring JPA/repository/transaction infrastructure, có thể thấy:

~~~java
org.springframework.orm.ObjectOptimisticLockingFailureException
~~~

hoặc subtype/wrapper tương ứng tùy phiên bản và provider. Vì vậy test ở tầng service nên assert theo exception contract của framework; test JPA trực tiếp ưu tiên optimistic cause của JPA.

### 14.2. Self-invocation làm REQUIRES_NEW không hiệu lực

~~~java
@Service
class InventoryService {

    @Transactional
    public void outer() {
        inner(); // Có thể bypass Spring proxy.
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void inner() {
    }
}
~~~

Với Spring proxy-based AOP, lời gọi nội bộ `this.inner()` có thể không kích hoạt transactional advice, nên **không mở transaction mới**.

Để test đúng, dùng hai beans khác nhau, gọi qua proxy hoặc `TransactionTemplate`.

## 15. Spring TransactionTemplate: interleaving trong cùng test thread

Có thể tạo một transaction ngoài T1 và transaction trong T2 với `REQUIRES_NEW`:

~~~java
TransactionTemplate outer =
    new TransactionTemplate(transactionManager);

outer.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);

TransactionTemplate inner =
    new TransactionTemplate(transactionManager);

inner.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
~~~

Ví dụ cấu trúc test:

~~~java
RuntimeException conflict = assertThrows(
    RuntimeException.class,
    () -> outer.executeWithoutResult(outerStatus -> {

        // T1 bắt đầu, đọc version V.
        InventoryItem first =
            em.find(InventoryItem.class, id);

        first.changeQuantity(15);

        // Tạm ngưng T1 và chạy T2 với context riêng.
        inner.executeWithoutResult(innerStatus -> {
            InventoryItem second =
                em.find(InventoryItem.class, id);

            second.changeQuantity(7);

            // Inner commit trước khi quay lại T1.
        });

        // T1 vẫn giữ version V, hiện đã stale.
        em.flush();
    })
);
~~~

Ở đây T2 **thắng**, T1 stale. Mẫu này chỉ đúng khi `em` là Spring-managed transaction-scoped proxy, `JpaTransactionManager` và persistence context được cấu hình thích hợp. `REQUIRES_NEW` thường cần một connection/transaction độc lập; connection pool quá nhỏ có thể gây chờ hoặc cạn tài nguyên.

Kiểm tra exception sau `assertThrows` theo Spring/JPA cause chain và đọc database ở transaction mới để xác nhận state của T2.

**Không dùng lại nguyên helper `em.getTransaction()` của RESOURCE_LOCAL test trong code đang do Spring transaction manager điều phối.**

## 16. Khi nào nên test hai thread thật?

Một bài kiểm thử đa thread bổ sung giá trị khi cần chứng minh:

- Hai request thật sự dùng hai JDBC connections.
- Transaction manager gắn context theo thread.
- Connection pool và timeout đủ cho concurrency.
- Xử lý response/metrics khi hai requests cạnh tranh.
- Blocking behavior của database.

Nhưng test đa thread **không bắt buộc** để chứng minh stale version với `@Version`.

### 16.1. Không dùng Thread.sleep làm điểm đồng bộ

Sai:

~~~java
Thread.sleep(200);
~~~

rồi hy vọng T1 đã commit trước T2. CPU, CI load, driver và database latency làm thời điểm không ổn định.

Dùng primitives:

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch firstCommitted = new CountDownLatch(1);
~~~

Luồng điều khiển:

~~~text
Thread T1                      Thread T2
---------                      ---------
Begin tx                       Begin tx
Find item/version V            Find item/version V
bothRead.countDown             bothRead.countDown
await bothRead                 await bothRead
quantity = 15                  await firstCommitted
flush/commit
firstCommitted.countDown  ---> quantity = 7
                               flush/commit -> conflict
~~~

Các bước trên là **pseudo-code** mô tả lịch chạy, chưa bao gồm toàn bộ exception handling. Một test thật cần:

- `await(timeout, TimeUnit.SECONDS)` để tránh treo.
- `Future.get(timeout)` để bắt lỗi trong worker threads.
- Mỗi thread tạo/đóng **EntityManager riêng**.
- `try/finally` đảm bảo rollback và đóng context.
- Signal ở `finally` nếu một nhánh lỗi để thread kia không chờ vô hạn.
- `ExecutorService.shutdownNow()`/await termination trong cleanup.
- Không chia sẻ EntityManager giữa các threads.

### 16.2. Đừng nhầm race scheduling với lỗi JPA

Nếu test thỉnh thoảng xanh, thỉnh thoảng đỏ, trước tiên kiểm tra:

- Cả hai có đọc trước commit không?
- Có dùng chung EntityManager không?
- Có cache/fixture khiến version khác không?
- Có flush bất ngờ trước barrier không?
- Có thực sự chờ T1 commit, hay chỉ chờ T1 gọi flush?

Kiểm thử concurrency phải **điều phối được trạng thái**, không chỉ tạo nhiều threads rồi xem chuyện gì xảy ra.

---

## 17. @Version và LockModeType.OPTIMISTIC

JPA hỗ trợ các lock modes như:

~~~java
LockModeType.OPTIMISTIC
LockModeType.OPTIMISTIC_FORCE_INCREMENT
LockModeType.PESSIMISTIC_READ
LockModeType.PESSIMISTIC_WRITE
~~~

Ví dụ:

~~~java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.OPTIMISTIC
);
~~~

`OPTIMISTIC` yêu cầu kiểm tra version theo semantics JPA. `OPTIMISTIC_FORCE_INCREMENT` còn yêu cầu version được tăng theo cơ chế phù hợp, hữu ích khi một aggregate root cần đánh dấu thay đổi dù scalar fields của root không bị dirty theo cách thông thường.

Tuy nhiên, bài test chính **không cần** gọi lock mode đặc biệt: entity có `@Version`, cả hai contexts sửa managed state và flush là đủ để kiểm tra cơ chế optimistic update thường dùng.

### 17.1. Đừng dùng PESSIMISTIC_WRITE cho test optimistic

Nếu T1 đọc với `PESSIMISTIC_WRITE`, database có thể giữ row lock và ngăn T2 đọc/ghi. Đó là một bài kiểm thử **pessimistic locking/lock timeout**, không phải một bài test thuần stale version check.

Hãy tách hai chủ đề để kết quả test có ý nghĩa rõ ràng.

## 18. Detached entity và merge cũng có thể tạo conflict

Một request đọc entity `version=3` rồi chuyển state thành detached. Request khác cập nhật entity lên `version=4`. Request đầu gửi entity đã sửa trở lại và gọi:

~~~java
em.merge(detachedItem);
~~~

Provider có thể phát hiện optimistic version stale khi merge, flush hoặc commit tùy implementation/state.

Cần test riêng khi ứng dụng thực sự dùng detached merge:

- Request DTO hoặc detached entity có mang version cũ không?
- Code có tự gán/mất version không?
- Merge có ghi đè những field không chủ đích không?
- Transaction được rollback khi conflict không?
- Exception được chuyển thành API response thế nào?

**`merge` không tự “hợp nhất ý định” hai người dùng.** Nó là cơ chế đồng bộ detached entity state, phải đi cùng chiến lược concurrency và nghiệp vụ rõ ràng.

## 19. HTTP API và expectedVersion

Một API sửa mặt hàng có thể nhận:

~~~json
{
  "itemId": 101,
  "newQuantity": 7,
  "expectedVersion": 3
}
~~~

Service có thể:

1. Xác thực caller và quyền sửa item.
2. Tải managed entity.
3. Kiểm tra expectedVersion của client so với version hiện tại.
4. Áp dụng thay đổi.
5. Flush/commit để JPA tiếp tục chống race trước thời điểm ghi.
6. Trả version mới hoặc conflict response.

Ví dụ kiểm tra ban đầu:

~~~java
if (!request.expectedVersion().equals(
        item.getVersion())) {
    throw new ConcurrentUpdateException();
}

item.changeQuantity(request.newQuantity());
~~~

**So sánh version trong Java chưa đủ**. Giao dịch khác có thể commit sau phép so sánh; `@Version` vẫn là hàng rào tại thời điểm cập nhật database.

Với REST, `409 Conflict` thường phù hợp với xung đột trạng thái. Với API dùng ETag và `If-Match`, `412 Precondition Failed` có thể phù hợp theo contract HTTP. Không chuyển mọi database RuntimeException thành 409.

## 20. Retry: chỉ khi ý định nghiệp vụ cho phép

Sau conflict:

~~~text
T2: rollback
    |
    v
Mở context + transaction mới
    |
    v
Đọc quantity/version hiện tại
    |
    v
Tính lại command nghiệp vụ
    |
    v
Thử update/commit
~~~

Nhưng **không retry mù quáng**.

Ví dụ T2 ban đầu đọc quantity=10 và muốn giảm 3:

- Nếu request là “**set quantity = 7**”, sau khi T1 đổi thành 15, tự động ghi 7 có thể bỏ qua ý định T1.
- Nếu request là “**decrease by 3 if enough stock**”, retry có thể đọc lại 15 và giảm xuống 12, nếu invariant vẫn hợp lệ.

Vì vậy retry cần:

- Transaction/persistence context mới mỗi lần.
- Giới hạn số lần thử.
- Phân biệt optimistic conflicts với lỗi khác.
- Kiểm tra điều kiện nghiệp vụ trên state mới.
- Bảo đảm idempotency hoặc tránh lặp side effects.
- Có metric theo dõi tỷ lệ conflict/retry.

Không retry trong transaction đã rollback-only.

---

## 21. Khi hai giao dịch thay đổi child entities

Giả sử `PurchaseOrder` có `@Version` nhưng hai transactions sửa hai `OrderLine` khác nhau.

`@Version` trên order root **không tự bảo đảm** version root luôn tăng nếu chỉ có các row child được sửa. Điều này tùy ownership/mapping/provider và loại thao tác.

Nếu invariant thuộc aggregate root, cần xác định chiến lược:

- Gắn version cho từng child nếu chúng được cập nhật độc lập.
- Yêu cầu optimistic lock/version increment trên root cho thao tác phải tuần tự theo aggregate.
- Sử dụng `OPTIMISTIC_FORCE_INCREMENT` nếu phù hợp.
- Áp dụng database constraint hoặc atomic DML cho invariant quan trọng.
- Viết integration test riêng cho thao tác nhiều child.

**Test của bài này chứng minh hai giao dịch cập nhật cùng một versioned entity, không tự chứng minh mọi thay đổi trong object graph đều gây conflict root.**

## 22. Bulk JPQL/native UPDATE có thể bỏ qua version check tự động

Ví dụ bulk JPQL:

~~~java
em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = :quantity
    WHERE i.id = :id
    """
)
.setParameter("quantity", 7)
.setParameter("id", id)
.executeUpdate();
~~~

Bulk DML không đồng nghĩa với việc JPA load managed entity rồi dirty-check `@Version`. Nó có thể không tự thêm version predicate hoặc increment như update qua managed entity.

Nếu cùng bảng có các đường ghi bulk/native, test optimistic locking với hai managed entities **không tự bảo vệ** những đường ghi khác.

Có thể thiết kế explicit compare-and-set cho version kiểu số:

~~~jpql
UPDATE InventoryItem i
SET i.quantity = :quantity,
    i.version = i.version + 1
WHERE i.id = :id
  AND i.version = :expectedVersion
~~~

Sau `executeUpdate()`, số rows bị ảnh hưởng bằng 0 cho biết không có row khớp; service cần phân biệt entity không tồn tại, không có quyền hoặc xung đột version theo nghiệp vụ. Đoạn này cần test theo provider/dialect và không làm thay đổi managed state tự động như sửa entity thông thường.

### 22.1. Không sửa SQL làm mất điều kiện version

Nếu provider tạo:

~~~sql
WHERE id = ? AND version = ?
~~~

thì không nên vì mục tiêu “tăng hiệu năng” mà dùng UPDATE không kiểm tra version trên cùng đường nghiệp vụ, rồi kỳ vọng optimistic locking vẫn hoạt động.

## 23. Đọc SQL log để xác nhận hành vi

Trong môi trường Hibernate 6 development/test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Hibernate 5 thường dùng namespace bind logger khác:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Một log minh họa:

~~~text
T1:
  SELECT ... FROM inventory_items WHERE id = ?
  UPDATE inventory_items
     SET quantity = ?, version = ?
   WHERE id = ? AND version = ?
  affected rows = 1

T2:
  SELECT ... FROM inventory_items WHERE id = ?
  UPDATE inventory_items
     SET quantity = ?, version = ?
   WHERE id = ? AND version = ?
  affected rows = 0
  OptimisticLockException
~~~

Đây **không phải output đã chạy**, chỉ thể hiện loại bằng chứng cần quan sát. Dạng SQL/bind/alias phụ thuộc provider và database.

Cần kết hợp SQL với assertions:

- Hai reads có cùng version ban đầu.
- Câu UPDATE sử dụng version predicate.
- T1 commit và T2 bị conflict.
- Database cuối cùng vẫn giữ thay đổi T1.

Không lưu raw bind logging chứa dữ liệu cá nhân/thông tin nhạy cảm trong môi trường production thiếu kiểm soát.

## 24. Không đánh đồng mọi lỗi cạnh tranh

| Hiện tượng | Có thể là | Cách phân biệt |
| --- | --- | --- |
| JPA báo OptimisticLockException | Stale version/entity update | Kiểm tra version, update count, cause |
| Lock timeout | Row lock bị giữ quá lâu | Kiểm tra thứ tự flush/commit và DB locks |
| Deadlock | Hai transactions lấy locks ngược thứ tự | Xem deadlock report DB |
| Serialization failure | Isolation/snapshot không cho phép lịch cập nhật | Xem SQLState/isolation/driver |
| Unique constraint violation | Hai transactions insert/update dữ liệu vi phạm unique | Không coi là optimistic locking |
| Connection timeout | Hết connection pool, DB chậm hoặc mất kết nối | Kiểm tra pool/transport |
| UnexpectedRollbackException | Transaction bị đánh dấu rollback-only | Kiểm tra cause gốc |
| Không exception, không UPDATE | Entity không dirty hoặc operation không có tác dụng | Xem state/SQL flush |

Test dùng:

~~~java
assertThrows(RuntimeException.class, operation);
~~~

mà không xem exception type/cause rất dễ **xanh giả**. Chỉ coi test thành công khi đúng cơ chế xung đột được chứng minh.

---

## 25. Test trên database đích, không chỉ H2

H2 có thể hữu ích cho một số bài kiểm tra JPA cơ bản, nhưng không thay thế hoàn toàn PostgreSQL, MySQL, Oracle hay SQL Server về:

- Isolation levels.
- Row locks và wait behavior.
- JDBC driver errors.
- Schema generation.
- Version column types.
- SQL rendering/dialect.
- Connection/transaction semantics.

Nếu production dùng PostgreSQL, test optimistic locking quan trọng nên có ít nhất một lượt trên PostgreSQL/version được hỗ trợ, chẳng hạn thông qua môi trường integration hoặc Testcontainers.

Không suy luận test H2 xanh là mọi mã SQLState và thứ tự exception sẽ giống database production.

## 26. Kiểm soát cache và fixture

First-level cache lưu managed entities trong EntityManager. Nếu fixture được tạo, rồi test tiếp tục dùng **cùng context**, có thể đọc dữ liệu từ bộ nhớ thay vì database và làm mất ý nghĩa hai independent snapshots.

Một quy trình đáng tin cậy:

1. Tạo fixture trong transaction riêng.
2. Commit fixture.
3. Đóng EntityManager tạo fixture.
4. Mở **em1** và **em2** mới.
5. Cả hai đọc cùng ID/version.
6. Để T1 commit trước, T2 stale update.
7. Dọn cả hai contexts.
8. Đọc lại bằng **verify EntityManager** mới.

Nếu second-level cache được bật, hiểu cơ chế invalidation sau commit. Khi cần xác minh database vật lý một cách chặt chẽ, có thể dùng query/JDBC ở một connection mới trong test chuyên biệt hoặc tắt/kiểm soát cache đúng phạm vi.

## 27. Các lỗi test thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Hai lần `find` trong một EntityManager | Chỉ một managed instance | Dùng hai EntityManager |
| T2 đọc sau T1 commit | T2 không stale | Hai bên đọc trước khi commit |
| T2 flush khi T1 còn giữ row lock | Blocking/timeout thay vì version conflict | T1 commit rồi T2 flush |
| Test chỉ assert RuntimeException | False positive | Kiểm tra optimistic cause |
| Test chỉ đọc `fromT2.getQuantity()` | Đọc Java object sau rollback | Dùng context verify mới |
| Test không commit fixture | Hai transactions không thấy cùng dữ liệu | Commit fixture trước |
| Fixture dùng cùng SKU giữa tests | Unique constraint/cross-test interference | Tạo fixture unique |
| Chỉ gán cùng giá trị cũ | Không dirty UPDATE | Dùng hai giá trị mới khác nhau |
| `@Version` chưa được mapping | Không có version protection | Sửa entity/schema |
| Chỉ kiểm tra version=0 | Phụ thuộc provider/init | Đọc version thực ban đầu |
| Test Spring tự `@Transactional` | Có thể chỉ một transaction | Điều phối transaction rõ |
| REQUIRES_NEW bị self-invocation | Không có T2 mới | Dùng proxy/bean/TransactionTemplate |
| Dùng sleep để tạo race | Flaky | Barrier/latch + timeout |
| Dùng cùng EntityManager ở hai threads | Không thread-safe | Context riêng mỗi thread |
| T2 thất bại rồi tiếp tục dùng context | State/transaction không đáng tin | Rollback, close, mở mới |
| Test bulk UPDATE như managed UPDATE | Bypass optimistic version | Thiết kế query/version riêng |
| T1/T2 sửa các child khác nhau | Không tự gây root conflict | Thiết kế aggregate locking |
| Test lệch database production | Exception/isolation khác | Integration test DB đích |

## 28. Bài tập thực hành có lời giải

### Bài 1. Có phải hai transaction?

~~~java
InventoryItem a = em.find(InventoryItem.class, id);
InventoryItem b = em.find(InventoryItem.class, id);
~~~

**Đáp án:** Không. Hai biến nằm trong cùng persistence context; thường là cùng managed instance. Muốn test conflict cần contexts/transactions độc lập.

### Bài 2. T2 đọc sau T1 commit

**Đáp án:** T2 có thể thấy version mới và ghi hợp lệ. Kịch bản stale update phải đảm bảo T2 đọc V trước commit của T1.

### Bài 3. UPDATE WHERE version không khớp

Database có version 4, T2 update với điều kiện version 3.

**Đáp án:** Câu UPDATE có thể ảnh hưởng 0 hàng và provider báo optimistic conflict.

### Bài 4. Exception ở flush

**Đáp án:** Hợp lệ. Flush có thể gửi SQL và kiểm tra version. Không buộc exception chỉ ném ở commit.

### Bài 5. Commit ném RollbackException

**Đáp án:** Kiểm tra cause có OptimisticLockException hoặc exception translation phù hợp. Không coi wrapper làm mất ý nghĩa optimistic conflict.

### Bài 6. Lock timeout thay vì OptimisticLockException

**Đáp án:** T2 có thể flush khi T1 chưa commit và đang giữ row lock. Phân biệt DB lock contention với stale version check.

### Bài 7. Object T2 vẫn giữ quantity=7

**Đáp án:** Java object vẫn chứa giá trị gán trước rollback. Đọc DB bằng context mới để biết persisted state.

### Bài 8. T1 sửa name, T2 sửa quantity trên cùng entity

**Đáp án:** Nếu cùng versioned row và cả hai tạo managed UPDATE, T2 stale vẫn có thể conflict dù sửa field khác nhau.

### Bài 9. Setter không đổi giá trị

**Đáp án:** Provider có thể không phát UPDATE vì không dirty. Test conflict cần sửa dữ liệu thật.

### Bài 10. Spring self-invocation

**Đáp án:** `this.innerRequiresNew()` có thể bỏ qua transaction proxy. Dùng bean/proxy khác hoặc TransactionTemplate.

### Bài 11. Multi-thread và Thread.sleep

**Đáp án:** Không ổn định. Dùng CountDownLatch/CyclicBarrier với timeout và error propagation.

### Bài 12. Retry trong cùng transaction đã lỗi

**Đáp án:** Không an toàn. Rollback, mở context/transaction mới, đọc version hiện tại và áp dụng command lại nếu hợp lệ.

### Bài 13. Retry một lệnh set quantity

**Đáp án:** Không nên tự ghi đè ý định của người khác. Có thể cần client xác nhận.

### Bài 14. Retry một lệnh giảm quantity

**Đáp án:** Có thể tính lại trên state mới nếu đủ hàng, giới hạn retry và đảm bảo idempotency của side effects.

### Bài 15. Bulk JPQL UPDATE

**Đáp án:** Không tự tương đương với dirty checking `@Version`. Nếu cần concurrency protection, dùng explicit version predicate/increment hoặc đường ghi managed entity.

### Bài 16. Hai child entities khác nhau

**Đáp án:** Root version có thể không tự tăng khi chỉ sửa child rows. Cần chiến lược root/aggregate locking riêng.

### Bài 17. H2 xanh, PostgreSQL lỗi

**Đáp án:** DB isolation/driver/dialect có khác biệt. Kiểm thử trên PostgreSQL mục tiêu để xác minh contract thực.

### Bài 18. Test chỉ kiểm tra ném exception

**Đáp án:** Chưa đủ. Phải assert precondition cùng version, lỗi optimistic đúng loại và final DB state không bị overwrite.

## 29. Checklist kiểm thử hai giao dịch

Trước khi kết luận bài test đã hoàn thành:

1. Entity dùng `@Version` đúng mapping?
2. Cột version đã có trong schema?
3. Fixture được commit trước?
4. T1 và T2 thật sự độc lập về EntityManager?
5. T1/T2 dùng transactions riêng?
6. Hai bên cùng đọc một ID và version V?
7. Hai Java instances khác nhau?
8. Hai bên tạo dirty state?
9. T1 đã commit trước T2 flush?
10. Exception được assert theo optimistic cause/wrapper?
11. Không vô tình chấp nhận lock timeout hay SQL syntax error?
12. T2 được rollback và đóng context?
13. Không tái sử dụng transaction thất bại?
14. Verify bằng một context mới?
15. Trạng thái cuối database giữ thay đổi T1?
16. Version sau T1 khác V?
17. Test không dựa vào sleep/race?
18. Nếu Spring, propagation có thực sự tạo hai contexts?
19. Connection pool/isolation đủ cho test?
20. Test có thể chạy trên database production-compatible?
21. Cache/fixture không che khuất SQL?
22. Những đường bulk/native updates có được đánh giá riêng?
23. API có chiến lược conflict/retry rõ ràng?
24. Không tự cập nhật version bằng Java setter?
25. Test parallel có dữ liệu riêng, không tranh fixture?

## 30. Tổng kết

Kiểm thử khóa lạc quan trong JPA không phải thao tác “sửa entity hai lần rồi kiểm tra exception”. Nó là một **kịch bản transaction có thứ tự được điều phối**.

~~~text
Fixture quantity=10, version=V (đã commit)
                    |
            +-------+-------+
            |               |
            v               v
          T1.begin        T2.begin
          find(id) V      find(id) V
            |               |
            v               v
          quantity=15    quantity=7
            |               |
            v               |
          flush             |
          commit            |
          version -> V'     |
            |               v
            +----------> T2 flush/commit
                            |
                            v
                    Optimistic conflict
                            |
                            v
                     rollback/close
                            |
                            v
                  New EntityManager.find(id)
                            |
                            v
                quantity=15, version=V'
~~~

Những nguyên tắc quan trọng nhất:

- **`@Version` phát hiện stale writes**, không khóa row ngay từ lúc đọc.
- Hai lần `find` trong cùng persistence context **không phải hai transactions cạnh tranh**.
- Cả T1 và T2 phải đọc **cùng version trước khi T1 commit**.
- T1 commit trước, rồi T2 flush/commit để tránh nhầm với lock blocking của database.
- Optimistic exception có thể xuất hiện ở `flush` hoặc `commit` và có thể bị bọc.
- Sau xung đột, phải rollback và không dùng lại context lỗi.
- Kiểm chứng **database từ EntityManager mới**, không chỉ giá trị còn nằm trong object đã rollback.
- Retry cần unit of work mới và phải tôn trọng **ý định nghiệp vụ**, không ghi đè mù quáng.
- Bulk SQL, child entity updates và pessimistic locks là những kịch bản cần test riêng.

**Một bài kiểm thử optimistic locking đúng phải chứng minh đủ ba điều: hai transaction đọc cùng phiên bản, transaction stale bị từ chối và thay đổi đã commit của transaction còn lại được giữ nguyên trong database.**
