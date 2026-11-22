# Xử lý OptimisticLockException và trạng thái giao dịch trong JPA

Trong **Jakarta Persistence (JPA)**, khóa lạc quan (*optimistic locking*) giúp phát hiện một entity đã bị giao dịch khác thay đổi kể từ khi ứng dụng đọc nó. Cơ chế phổ biến nhất là đánh dấu một thuộc tính bằng `@Version` và để JPA provider kiểm tra phiên bản khi đồng bộ thay đổi xuống cơ sở dữ liệu.

Khi hai giao dịch cùng cập nhật dữ liệu dựa trên một phiên bản cũ, một giao dịch có thể nhận **`OptimisticLockException`**. Điểm quan trọng không chỉ là nhận diện ngoại lệ mà còn là **xử lý trạng thái giao dịch** sau lỗi:

> **OptimisticLockException làm transaction liên quan bị đánh dấu rollback-only. Không được catch lỗi rồi cố ghi tiếp hoặc commit chính transaction ấy. Hãy rollback, kết thúc persistence context đã lỗi và chỉ retry toàn bộ nghiệp vụ trong transaction mới nếu nghiệp vụ thực sự cho phép.**

Lỗi không nhất thiết xuất hiện ngay khi gọi setter. JPA provider có thể phát hiện nó ở `merge()`, `lock()`, `flush()` hoặc `commit()`; khi commit, ngoại lệ có thể được bọc bởi `RollbackException` hoặc một exception của framework.

Bài học này tập trung vào: ý nghĩa của `@Version`, cơ chế phát hiện lost update, trạng thái rollback-only, vòng đời `EntityManager`, code Java SE và Spring để rollback/retry, conflict từ form HTTP cũ, tương tác với bulk update, side effects, chiến lược thay thế và kiểm thử hai transaction.

## 1. Vì sao cần optimistic locking?

Giả sử hệ thống kho có bản ghi:

| Thuộc tính | Giá trị ban đầu |
| --- | ---: |
| `id` | 101 |
| `available` | 10 |
| `reserved` | 0 |
| `version` | 7 |

Hai người cùng đặt giữ hàng:

- Transaction A muốn giữ 4 đơn vị.
- Transaction B muốn giữ 3 đơn vị.

Nếu không có kiểm tra phiên bản:

```text
A: đọc available=10
B: đọc available=10
A: tính available=6
B: tính available=7
A: UPDATE available=6
B: UPDATE available=7
A/B: commit
```

Kết quả cuối có thể là 7 thay vì 3. Một lần đặt giữ có nguy cơ bị ghi đè: **lost update**.

Khi entity có `@Version`, một SQL UPDATE minh họa là:

```sql
UPDATE inventory_items
SET available = 6,
    reserved = 4,
    version = 8
WHERE id = 101
  AND version = 7;
```

Nếu A cập nhật thành công, version mới là 8. B vẫn giữ snapshot với version 7, nên lần UPDATE tương ứng có thể không tác động hàng nào:

```sql
UPDATE inventory_items
SET available = 7,
    reserved = 3,
    version = 8
WHERE id = 101
  AND version = 7;
```

Provider nhận biết bản ghi/phiên bản không còn khớp và báo optimistic conflict. Transaction B cần rollback. Nếu nghiệp vụ cho phép retry, B phải đọc lại `available=6, version=8` rồi **kiểm tra lại đủ tồn** trước khi giữ tiếp 3 đơn vị.

### 1.1. Timeline có khóa lạc quan

```text
Thời gian       Transaction A                  Transaction B
-----------     -------------------------      -------------------------
t1              BEGIN
t2                                                BEGIN
t3              SELECT Item#101 v=7
t4                                                SELECT Item#101 v=7
t5              reserve(4) -> available=6
t6                                                reserve(3) -> available=7
t7              UPDATE ... WHERE version=7
t8              COMMIT -> version=8
t9                                                UPDATE ... WHERE version=7
t10                                               0 rows / stale version
t11                                               OptimisticLockException
t12                                               ROLLBACK
```

Thứ tự thắng/thua có thể đảo ngược. Quy tắc cần giữ là **không để cả hai commit các thay đổi dựa trên cùng snapshot cũ mà không được phát hiện**.

### 1.2. Optimistic locking khác khóa bi quan

- **Optimistic locking:** chủ yếu kiểm tra tính mới của version, không giữ trước một khóa ghi dài hạn chỉ để chờ sửa.
- **Pessimistic locking:** yêu cầu DBMS khóa tương ứng, ví dụ `PESSIMISTIC_WRITE`, để kiểm soát cạnh tranh trước hoặc trong quá trình thao tác.

Optimistic không đồng nghĩa DBMS hoàn toàn không lấy lock: khi thực thi SQL UPDATE, database vẫn sử dụng cơ chế ghi và khóa phù hợp với isolation của nó.

## 2. Mapping @Version trong entity

Ví dụ Java sử dụng namespace `jakarta.persistence`:

```java
package com.example.inventory;

import jakarta.persistence.*;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Column(nullable = false)
    private int available;

    @Column(nullable = false)
    private int reserved;

    @Version
    @Column(nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public int getReserved() {
        return reserved;
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

        if (available < quantity) {
            throw new InsufficientStockException(
                "Not enough available stock"
            );
        }

        available -= quantity;
        reserved += quantity;
    }

    public static final class InsufficientStockException
            extends RuntimeException {

        public InsufficientStockException(String message) {
            super(message);
        }
    }
}
```

Trong ví dụ:

- `id` là định danh entity.
- `available` và `reserved` là dữ liệu nghiệp vụ.
- `version` là thuộc tính version do provider quản lý.
- `reserve()` kiểm tra invariant tại thời điểm đang sử dụng entity và thay đổi managed state.

**Không tự viết `item.setVersion(item.getVersion()+1)` trong business method.** Với managed entity, việc kiểm tra và thay đổi version là trách nhiệm của JPA provider theo `@Version`.

### 2.1. DDL minh họa

Ví dụ PostgreSQL:

```sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_available_nonnegative
        CHECK (available >= 0),
    CONSTRAINT ck_reserved_nonnegative
        CHECK (reserved >= 0)
);
```

Cột `version` là numeric; kiểu Java ví dụ là `Long`. Cách khởi tạo version và SQL cụ thể khi persist/update phụ thuộc provider và mapping.

### 2.2. SQL kiểm tra phiên bản không phải một template bắt buộc

Provider có thể sinh SQL có dạng:

```sql
UPDATE inventory_items
SET available = ?,
    reserved = ?,
    version = ?
WHERE id = ?
  AND version = ?;
```

Nhưng thứ tự cột, JDBC statement batching, câu SELECT bổ sung và cách báo lỗi có thể khác nhau. Điều quan trọng là semantics **kiểm tra version cũ khi ghi**.

### 2.3. Có @Version không đủ nếu writer khác bỏ qua version

Nếu có code JDBC hoặc stored procedure:

```sql
UPDATE inventory_items
SET available = available - 1
WHERE id = 101;
```

mà không cập nhật version theo chính sách chung, một giao dịch JPA khác có thể không nhận biết thay đổi đó qua version như dự kiến. Mọi đường ghi vào cùng dữ liệu quan trọng phải có chiến lược đồng bộ và versioning tương thích.

## 3. OptimisticLockException là gì?

`jakarta.persistence.OptimisticLockException` là runtime exception báo lỗi kiểm tra optimistic version hoặc optimistic lock.

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    // Transaction không còn là đơn vị công việc
    // có thể tiếp tục commit.
}
```

Ngoại lệ có thể cung cấp entity liên quan:

```java
Object conflicting = ex.getEntity();
```

Tuy nhiên, `getEntity()` **có thể trả null**. Không nên viết business logic phụ thuộc tuyệt đối vào việc provider luôn đính kèm entity cụ thể, nhất là khi SQL được batch hoặc ngoại lệ đến từ commit.

### 3.1. Phân biệt các loại lỗi

| Loại tình huống | Ý nghĩa | Hướng xử lý chính |
| --- | --- | --- |
| `quantity <= 0` | Input không hợp lệ | Validation error |
| Không đủ hàng sau khi đọc state mới | Business rejection | Trả kết quả nghiệp vụ |
| Không tìm thấy ID | Entity không tồn tại | Not found / lỗi domain |
| Version đã đổi trong lúc ghi | Optimistic conflict | Rollback, reload và retry/409 tùy nghiệp vụ |
| Unique/FK constraint violation | Vi phạm ràng buộc DB | Rollback và sửa nghiệp vụ/dữ liệu |
| Mất kết nối, timeout | Lỗi hạ tầng | Chính sách retry riêng có xét outcome |
| Deadlock | Cạnh tranh ở DBMS | Rollback, có thể retry nếu an toàn |

Không xem mọi lỗi lúc commit đều là optimistic conflict.

## 4. OptimisticLockException có thể xuất hiện lúc nào?

Một setter thay đổi đối tượng Java; nó không tự cần phải gửi SQL ngay.

| Thao tác | Khi nào có thể phát hiện conflict? |
| --- | --- |
| `item.reserve(qty)` | Thường chưa kiểm tra database |
| `em.merge(detached)` | Có thể lúc merge hoặc muộn hơn |
| `em.lock(item, OPTIMISTIC)` | Có thể lúc lock, flush hoặc commit |
| `em.flush()` | Có thể thực thi SQL version-aware UPDATE |
| `tx.commit()` | Có thể kích hoạt flush rồi phát hiện lỗi |
| Kết thúc method `@Transactional` | Framework commit sau invocation nên có thể báo conflict lúc này |

### 4.1. Xung đột lộ ở flush

```java
InventoryItem item = em.find(
    InventoryItem.class, 101L
);

item.reserve(4);

// Lỗi có thể xuất hiện ở đây:
em.flush();
```

### 4.2. Xung đột lộ ở commit

```java
InventoryItem item = em.find(
    InventoryItem.class, 101L
);

item.reserve(4);

// Provider có thể flush ngầm trước commit:
tx.commit();
```

`commit()` có thể ném `RollbackException` chứa `OptimisticLockException` ở cause chain. Nếu chỉ catch `OptimisticLockException` quanh `em.flush()`, ứng dụng có thể bỏ lỡ lỗi xảy ra ở transaction boundary.

### 4.3. Tại sao flush sớm đôi khi hữu ích?

Trong một nghiệp vụ có nhiều bước, `em.flush()` có thể giúp phát hiện lỗi ghi trước khi tiếp tục làm việc tốn chi phí. Nhưng:

- Flush **không phải commit**.
- Flush có thể thành công còn commit lỗi.
- Một optimistic conflict khác có thể xảy ra ở bước tiếp theo.
- Không được làm side effects bên ngoài dựa trên kết quả flush như thể transaction đã hoàn tất.

## 5. Trạng thái transaction sau optimistic conflict

Quy tắc trung tâm của đặc tả: **`OptimisticLockException` đánh dấu transaction liên quan để rollback**.

Sơ đồ:

```text
         begin()
            |
            v
     +--------------+
     | ACTIVE       |
     +--------------+
            |
            | version mismatch
            v
     +--------------+
     | ROLLBACK-ONLY|
     +--------------+
            |
         rollback()
            v
     +--------------+
     | ENDED        |
     +--------------+
```

Sơ đồ mô tả hành vi, không phải một enum trạng thái mà `EntityTransaction` trả nguyên văn.

### 5.1. Active không đồng nghĩa có thể commit

```java
EntityTransaction tx = em.getTransaction();

if (tx.isActive()) {
    // Transaction có thể vẫn đã rollback-only.
}
```

Trong resource-local JPA, `tx.getRollbackOnly()` giúp kiểm tra rollback-only khi việc gọi hợp lệ và transaction còn active. Nhưng sau optimistic failure, không cần cố thăm dò từng chi tiết để tìm cách commit lại: **hãy rollback**.

### 5.2. Catch không làm mất rollback-only

Sai:

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    System.out.println("Ignore conflict");
}

tx.commit(); // Không phải cách phục hồi.
```

Nếu transaction đã rollback-only, việc catch lỗi không thay đổi trạng thái. Commit có thể thất bại, và các bước ghi khác trong cùng transaction không được phép coi là đã thành công.

### 5.3. Nếu exception xảy ra trong commit

Sau khi `tx.commit()` ném exception, transaction có thể đã kết thúc; `tx.isActive()` có thể là false. Vì vậy:

```java
catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

hợp lý hơn việc gọi `rollback()` bất kể trạng thái. Trong trường hợp mất kết nối đúng lúc commit, kết quả thực tế có thể cần cơ chế đối soát/idempotency riêng; đừng suy mọi loại commit exception đều có cùng semantics.

## 6. Trạng thái EntityManager và persistence context sau lỗi

Persistence context quản lý entity identity, snapshots, dirty state và collections.

Giả sử:

```java
InventoryItem item =
    em.find(InventoryItem.class, 101L);

item.reserve(4); // Field Java thay đổi.

em.flush(); // OptimisticLockException.
```

Sau lỗi:

- `item.getAvailable()` có thể vẫn chứa giá trị vừa tính trên Java object.
- Điều đó **không chứng minh** database đã commit thay đổi.
- Transaction phải rollback.
- EntityManager/context đang gắn với lượt xử lý lỗi **không nên được tiếp tục dùng để sửa và commit**.
- `em.refresh(item)` hoặc `em.clear()` không biến transaction rollback-only thành giao dịch khỏe mạnh.

### 6.1. Quy trình phục hồi hợp lý

Với application-managed EntityManager:

```text
OptimisticLockException
        |
        v
Rollback transaction
        |
        v
Close EntityManager cũ
        |
        v
Nếu retry được:
  Create EntityManager mới
  Begin transaction mới
  Find entity mới nhất
  Tính lại nghiệp vụ
  Flush / commit
```

Với container-managed/Spring, để transaction manager rollback và bắt đầu một invocation **thực sự có transaction mới**, không dùng tiếp managed state của lượt thất bại.

### 6.2. Vì sao refresh() không phải chiến lược retry?

Sai:

```java
catch (OptimisticLockException ex) {
    em.refresh(item);
    item.reserve(4);
    em.flush();
}
```

Đoạn này cố thao tác trong transaction đã lỗi. Refresh có thể thất bại hoặc cho state mới nhưng transaction vẫn rollback-only; nó không khôi phục khả năng commit.

### 6.3. Vì sao clear() cũng không đủ?

`em.clear()` detach entities, có thể làm mất các thay đổi chưa flush, nhưng không điều khiển transaction status. Giải pháp đúng là kết thúc lượt transaction lỗi, không chỉ xóa nội dung persistence context.

## 7. Resource-local JPA: một giao dịch có rollback đúng

Ví dụ hoàn chỉnh:

```java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class InventoryReservationService {

    private final EntityManagerFactory emf;

    public InventoryReservationService(
            EntityManagerFactory emf) {
        this.emf = emf;
    }

    public int reserveOnce(long id, int quantity) {
        if (id <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                "Invalid product or quantity"
            );
        }

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                InventoryItem item =
                    em.find(InventoryItem.class, id);

                if (item == null) {
                    throw new IllegalArgumentException(
                        "Inventory item not found"
                    );
                }

                item.reserve(quantity);

                // Một số conflict có thể xuất hiện ở đây.
                em.flush();

                int remaining = item.getAvailable();

                // Conflict hoặc lỗi khác vẫn có thể lộ
                // tại commit.
                tx.commit();

                return remaining;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackEx) {
                        ex.addSuppressed(rollbackEx);
                    }
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

### 7.1. Điều ví dụ bảo đảm về cấu trúc

- Mỗi lời gọi sử dụng một EntityManager riêng.
- Transaction bắt đầu trước thao tác thay đổi.
- Lỗi ở `flush()` **và** `commit()` đều rơi vào catch.
- Transaction còn active sẽ được rollback.
- EntityManager luôn được đóng.
- Method chỉ trả remaining sau khi `commit()` hoàn tất.

### 7.2. Vì sao catch RuntimeException?

Không chỉ `OptimisticLockException` mới yêu cầu rollback. Việc quản lý transaction nên coi **mọi lỗi runtime của đơn vị công việc** là lý do không commit tiếp.

Phân loại xem lỗi **có được retry không** là một bước khác, thường thực hiện ở tầng gọi nằm ngoài transaction.

### 7.3. Tại sao không trả phần việc đã hoàn thành?

Nếu giao dịch còn cập nhật Order, Reservation, Audit trong cùng transaction, xung đột ở InventoryItem khiến **toàn bộ transaction rollback**, không phải riêng SQL của InventoryItem. Trả kết quả “một nửa thành công” có thể phá invariant nghiệp vụ.

## 8. Nhận diện optimistic conflict bị bọc

Một cause chain có thể trông như:

```text
RollbackException
    |
    +-- OptimisticLockException
            |
            +-- Provider-specific stale state exception
```

Helper nhận diện:

```java
package com.example.inventory;

import jakarta.persistence.OptimisticLockException;

public final class PersistenceFailureClassifier {

    private PersistenceFailureClassifier() {
    }

    public static boolean isOptimisticConflict(
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
}
```

Đây là một cách phân loại hữu ích nhưng không phải cam kết mọi provider trả đúng cause chain. Khi dùng Spring, còn có exception translation thuộc Spring DAO.

### 8.1. Không retry mọi RollbackException

`RollbackException` có thể do constraint, timeout, transaction bị đánh dấu rollback-only vì một lỗi trước đó, hoặc lỗi commit khác. Retry bừa bãi có thể lặp một lỗi không bao giờ tự hết.

### 8.2. Không dựa tuyệt đối vào getEntity()

`OptimisticLockException.getEntity()` có thể trả null hoặc entity không đủ thông tin để giải quyết conflict. Hãy lưu ID/command của nghiệp vụ và đọc lại state trong transaction mới.

## 9. Retry phải diễn ra trong transaction mới

Khi nghiệp vụ cho phép, một retry đúng có dạng:

```text
Attempt #1
  New EntityManager A
  New transaction A
  Read version 7
  Apply reserve(4)
  Conflict
  Rollback A
  Close A

Attempt #2
  New EntityManager B
  New transaction B
  Read version 8
  Re-check stock
  Apply reserve(4) only if still valid
  Flush and commit B
  Close B
```

Sai:

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    item.reserve(4);
    em.flush(); // Cùng transaction lỗi.
}
```

### 9.1. Retry loop trong Java SE

```java
package com.example.inventory;

import jakarta.persistence.*;
import java.util.Objects;

public final class RetryingInventoryService {

    private final EntityManagerFactory emf;
    private final int maxAttempts;

    public RetryingInventoryService(
            EntityManagerFactory emf,
            int maxAttempts) {

        this.emf = Objects.requireNonNull(emf);

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be at least one"
            );
        }

        this.maxAttempts = maxAttempts;
    }

    public int reserve(long itemId, int quantity) {
        if (itemId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                "Invalid input"
            );
        }

        for (int attempt = 1;
                attempt <= maxAttempts;
                attempt++) {

            EntityManager em = emf.createEntityManager();
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                InventoryItem item =
                    em.find(InventoryItem.class, itemId);

                if (item == null) {
                    throw new IllegalArgumentException(
                        "Item not found"
                    );
                }

                // Luôn tính lại theo state của attempt mới.
                item.reserve(quantity);

                em.flush();

                int remaining = item.getAvailable();

                tx.commit();

                return remaining;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackEx) {
                        ex.addSuppressed(rollbackEx);
                    }
                }

                boolean retryable =
                    PersistenceFailureClassifier
                        .isOptimisticConflict(ex);

                if (!retryable || attempt == maxAttempts) {
                    throw ex;
                }
            } finally {
                em.close();
            }
        }

        throw new IllegalStateException(
            "Unreachable retry state"
        );
    }
}
```

Mỗi attempt tạo EntityManager và transaction **mới**. Nếu attempt hai đọc còn 2 sản phẩm mà yêu cầu giữ 4, `reserve(4)` sẽ từ chối theo nghiệp vụ — không tiếp tục retry mù quáng.

### 9.2. Retry số lần hữu hạn

Không retry vô hạn. Số lượt phù hợp phụ thuộc:

- Mức độ tranh chấp.
- Độ trễ giới hạn của request.
- Chi phí query và transaction.
- Tính an toàn khi chạy lại domain logic.
- Tỷ lệ thành công khi retry thực tế.

Với hot row liên tục có conflict, thêm retry có thể tăng tải database. Có thể cân nhắc backoff có jitter, nhưng phải chờ **sau khi transaction lỗi đã kết thúc**, không giữ connection/lock trong lúc chờ.

### 9.3. Retry business command, không phải stale entity

Giữ một command đơn giản:

```java
record ReserveCommand(long itemId, int quantity) {}
```

Mỗi attempt tải entity mới nhất rồi áp lại command. Không lấy object entity đã bị thay đổi trong transaction lỗi đem merge vào context mới như một cách “tiếp tục”.

## 10. Những trường hợp không nên tự động retry

Một số thao tác thích hợp để tính lại theo dữ liệu mới:

- Tăng bộ đếm với rule cộng dồn rõ.
- Đặt giữ hàng sau khi kiểm tra lại số lượng.
- Tính lại tổng theo những dòng còn hiện hành.

Một số thao tác cần hỏi người dùng hoặc từ chối:

- Chỉnh sửa một văn bản có nội dung bị người khác sửa giữa chừng.
- Đặt giá thành một giá trị tuyệt đối trong khi người khác vừa đặt giá khác.
- Phê duyệt một đơn hàng dựa trên các điều kiện đã thay đổi.
- Thực thi thanh toán, gửi email hoặc gọi hệ thống bên ngoài không có idempotency.

### 10.1. Phép cộng khác phép gán

Lệnh:

```text
counter = latestCounter + 5
```

có thể an toàn khi tính lại nếu domain cho phép.

Lệnh:

```text
price = 100
```

không nên tự động ghi đè một giá trị mới khác mà người dùng chưa được nhìn thấy.

### 10.2. Một bảng quyết định

| Use case | Sau optimistic conflict |
| --- | --- |
| Giữ kho | Rollback, đọc lại và thử lại có giới hạn nếu đủ hàng |
| Tăng bộ đếm | Có thể retry, xét idempotency |
| Chỉnh sửa form người dùng | Báo conflict, đọc bản mới, để người dùng quyết định |
| Thanh toán | Cần workflow/idempotency riêng, không retry tùy tiện |
| Cập nhật trạng thái theo điều kiện | Phải kiểm tra lại điều kiện ở mỗi attempt |
| Bulk xử lý nhiều entities | Retry toàn bộ phần atomic, tránh partial commit |

## 11. Spring @Transactional và thời điểm exception

Với Spring Data JPA:

```java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(
            InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(long id, int quantity) {
        InventoryItem item = repository.findById(id)
            .orElseThrow();

        item.reserve(quantity);
    }
}
```

Spring transaction interceptor có thể flush/commit **sau khi method body trả về**. Vì vậy một catch chỉ nằm quanh `item.reserve(...)` thường không bắt được lỗi xảy ra ở commit.

### 11.1. Explicit flush

```java
@Transactional
public void reserve(long id, int quantity) {
    InventoryItem item = repository.findById(id)
        .orElseThrow();

    item.reserve(quantity);

    repository.flush();
}
```

`flush()` có thể làm xung đột lộ sớm, nhưng **không bảo đảm commit luôn thành công**.

### 11.2. Không catch và trả success trong transaction rollback-only

Sai:

```java
@Transactional
public Result reserve(...) {
    try {
        updateAndFlush();
    } catch (OptimisticLockException ex) {
        return Result.SUCCESS;
    }

    return Result.SUCCESS;
}
```

Catch không phục hồi rollback-only. Commit vẫn có thể bị từ chối, và báo thành công là sai.

### 11.3. Exception translation của Spring

Khi đi qua repository hoặc exception translator, lỗi có thể xuất hiện dưới dạng:

```java
org.springframework.orm.ObjectOptimisticLockingFailureException
```

hoặc subtype của:

```java
org.springframework.dao.OptimisticLockingFailureException
```

và có thể bọc một ngoại lệ JPA/provider. Tầng điều phối retry phải biết cách phân loại exception thực tế trong cấu hình của dự án, không chỉ một lớp exception duy nhất.

### 11.4. noRollbackFor không cứu transaction JPA đã rollback-only

Một cấu hình `@Transactional(noRollbackFor = OptimisticLockException.class)` không biến transaction đã được JPA đánh dấu rollback-only thành giao dịch có thể commit. Quy tắc rollback của Spring và trạng thái do provider áp vào transaction là hai lớp cơ chế khác nhau.

## 12. Spring retry: tách coordinator khỏi transaction worker

Sai:

```java
@Transactional
public void reserveWithRetry(long id, int qty) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            reserveOnce(id, qty);
            return;
        } catch (OptimisticLockException ex) {
            // Vòng for vẫn trong cùng transaction.
        }
    }
}
```

Cách tốt hơn là một **coordinator không có transaction bao vòng retry**, gọi một bean worker tạo transaction riêng cho từng attempt.

Worker:

```java
@Service
public class InventoryTransactionalWorker {

    private final InventoryRepository repository;

    public InventoryTransactionalWorker(
            InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int reserveOnce(long id, int quantity) {
        InventoryItem item = repository.findById(id)
            .orElseThrow();

        item.reserve(quantity);

        repository.flush();

        return item.getAvailable();
    }
}
```

Coordinator:

```java
@Service
public class InventoryRetryCoordinator {

    private final InventoryTransactionalWorker worker;

    public InventoryRetryCoordinator(
            InventoryTransactionalWorker worker) {
        this.worker = worker;
    }

    public int reserve(long id, int quantity) {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return worker.reserveOnce(id, quantity);
            } catch (RuntimeException ex) {
                if (!isOptimistic(ex) || attempt == 3) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }

    private static boolean isOptimistic(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof jakarta.persistence.OptimisticLockException
                    || t instanceof
                        org.springframework.dao.OptimisticLockingFailureException) {
                return true;
            }
        }
        return false;
    }
}
```

Giả định: coordinator được gọi **không nằm trong một transaction bên ngoài**, và lời gọi worker đi qua **Spring transactional proxy**. Nếu có outer transaction, `Propagation.REQUIRED` mặc định có thể khiến worker tham gia transaction ấy, làm sai ý tưởng mỗi attempt có transaction độc lập.

### 12.1. Self-invocation

Gọi `this.reserveOnce(...)` trong cùng bean có thể bỏ qua Spring proxy trong cấu hình transaction proxy-based thông thường. Vì vậy tách worker thành bean khác hoặc dùng transaction API trực tiếp.

### 12.2. REQUIRES_NEW không phải giải pháp mặc định

`REQUIRES_NEW` có thể cho mỗi attempt transaction độc lập ngay cả khi có outer transaction, nhưng nó cũng có thể:

- Tạo commit riêng không rollback cùng outer transaction.
- Tăng nhu cầu connection.
- Gây hiểu nhầm về atomicity giữa nhiều bước.

Phải thiết kế transaction boundary theo domain thay vì thêm propagation tùy tiện.

## 13. TransactionTemplate để điều phối retry

`TransactionTemplate` của Spring có thể bao một attempt:

```java
@Service
public class InventoryTemplateService {

    private final TransactionTemplate template;

    @PersistenceContext
    private EntityManager em;

    public InventoryTemplateService(
            PlatformTransactionManager manager) {
        this.template = new TransactionTemplate(manager);
        this.template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public int reserve(long id, int quantity) {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                Integer value = template.execute(status -> {
                    InventoryItem item =
                        em.find(InventoryItem.class, id);

                    if (item == null) {
                        throw new IllegalArgumentException(
                            "Item not found"
                        );
                    }

                    item.reserve(quantity);
                    em.flush();
                    return item.getAvailable();
                });

                return java.util.Objects.requireNonNull(value);
            } catch (RuntimeException ex) {
                if (!isOptimisticConflict(ex)
                        || attempt == 3) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }

    private boolean isOptimisticConflict(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof OptimisticLockException
                    || t instanceof OptimisticLockingFailureException) {
                return true;
            }
        }
        return false;
    }
}
```

Đoạn ví dụ cần imports từ `jakarta.persistence`, `org.springframework.transaction`, `org.springframework.transaction.support` và `org.springframework.dao`. Các transaction/callback phải dùng cùng JPA transaction manager với EntityManager được inject.

Ưu điểm quan trọng: catch nằm **ngoài `template.execute(...)`**, bao gồm cả lỗi phát sinh lúc commit khi transaction callback đã chạy xong.

Lưu ý: `REQUIRES_NEW` ở đây được dùng để minh họa boundary riêng; trong kiến trúc thật cần đánh giá outer transaction và rủi ro commit một phần.

## 14. Container/JTA-managed EntityManager

Với Jakarta EE hoặc hệ thống JTA, EntityManager thường do container quản lý:

```java
@PersistenceContext
private EntityManager em;
```

Không sử dụng:

```java
em.getTransaction().begin();
```

trên JTA-managed EntityManager. Transaction được điều phối bởi container/transaction manager.

Khi optimistic conflict:

1. Để transaction manager rollback transaction hiện tại.
2. Không tiếp tục ghi trong invocation đã rollback-only.
3. Nếu cần retry, gọi lại nghiệp vụ trong transaction mới đúng cách.
4. Không tái sử dụng entity graph chứa state của lượt lỗi.

### 14.1. Một lỗi entity làm rollback toàn bộ transaction

Nếu transaction làm:

```text
Update inventory
Insert reservation
Update purchase order
```

và inventory gặp optimistic conflict, không được commit hai bước còn lại như thể chúng thành công. Transaction là một đơn vị atomic.

## 15. Form HTTP mở lâu: @Version vẫn có thể chưa đủ

Đây là tình huống **khác** với hai transactions cùng đọc version ngay trong database.

```text
10:00 User A GET Product#101, version=7, price=100
10:01 User B GET Product#101, version=7, price=100
10:02 User B PUT price=120 -> version=8
10:05 User A PUT price=110 từ form version=7
```

Nếu server xử lý A bằng:

```java
@Transactional
public void updatePrice(long id, BigDecimal price) {
    Product p = em.find(Product.class, id); // Đọc version=8
    p.changePrice(price);                   // Ghi price=110
}
```

thì **JPA có thể không phát sinh optimistic conflict**: transaction của A mới đọc version 8 rồi cập nhật version 8 hợp lệ. Nhưng nó đã vô tình ghi đè ý định của B từ form cũ.

### 15.1. Giữ expectedVersion trong request

Response GET:

```json
{
  "id": 101,
  "price": "100.00",
  "version": 7
}
```

Request PUT:

```json
{
  "price": "110.00",
  "expectedVersion": 7
}
```

Service:

```java
@Transactional
public void updatePrice(UpdatePriceCommand command) {
    Product product = em.find(
        Product.class,
        command.id()
    );

    if (product == null) {
        throw new EntityNotFoundException();
    }

    if (!Objects.equals(
            product.getVersion(),
            command.expectedVersion())) {
        throw new StaleClientStateException(
            "Product was changed by another request"
        );
    }

    product.changePrice(command.price());

    // @Version vẫn bảo vệ khoảng thời gian
    // giữa phép đọc hiện tại và flush/commit.
}
```

Ví dụ này giả định `Product`, `UpdatePriceCommand` và `StaleClientStateException` là các kiểu domain có sẵn. Nó minh họa logic, không phải toàn bộ compilation unit.

### 15.2. Hai khoảng thời gian được bảo vệ

**Expected version của client**:

```text
GET -> user chỉnh sửa nhiều phút -> PUT
```

giúp phát hiện thay đổi xảy ra **giữa các HTTP requests**.

**Optimistic version check của JPA**:

```text
BEGIN -> em.find version N -> UPDATE WHERE version N
```

giúp phát hiện thay đổi **trong transaction đang ghi**.

Hai cơ chế bổ sung nhau.

### 15.3. 409 Conflict và 412 Precondition Failed

Tầng API có thể:

- Trả **409 Conflict** cho trạng thái tài nguyên xung đột.
- Trả **412 Precondition Failed** khi yêu cầu dùng HTTP `If-Match`/ETag và precondition không thỏa.

JPA không tự quyết định HTTP status. Nếu dùng ETag, cần thiết kế cách xây validator và kiểm tra version theo contract API.

### 15.4. Khi nào phải hỏi người dùng?

Với biểu mẫu chỉnh sửa tài liệu/giá trị tuyệt đối, ứng dụng có thể hiển thị hai phiên bản, cho người dùng so sánh và merge. Không tự động retry bằng cách ghi toàn bộ dữ liệu từ form cũ lên bản mới.

## 16. Detached entity và merge()

Một detached entity có thể giữ version cũ:

```java
InventoryItem detached = loadAndDetach(101L);
// Trong DB đã có transaction khác cập nhật version mới.

InventoryItem managed = em.merge(detached);
```

Provider có thể phát hiện version mismatch ở `merge()` hoặc khi flush/commit.

`merge()` **không** có nghĩa ép ghi đè state mới nhất bất chấp version.

Ngoài ra, `merge()` trả về một managed instance; object `detached` ban đầu vẫn là detached. Sau lỗi, không được dùng lại cả hai như nguồn state mới đáng tin cho một retry.

### 16.1. DTO + find + apply changes

Với web API, thường rõ ràng hơn khi:

```text
DTO(id, expectedVersion, fields)
     |
     v
Transaction
     |
     +-- find managed entity
     +-- compare expectedVersion
     +-- validate allowed fields
     +-- apply updates
     +-- flush/commit with @Version
```

Cách này giúp kiểm soát field được phép sửa và không phụ thuộc vào client gửi nguyên trạng một entity JPA.

## 17. Optimistic lock modes

JPA cung cấp:

```java
LockModeType.OPTIMISTIC
LockModeType.OPTIMISTIC_FORCE_INCREMENT
```

### 17.1. OPTIMISTIC

```java
InventoryItem item = em.find(
    InventoryItem.class,
    101L,
    LockModeType.OPTIMISTIC
);
```

hoặc:

```java
em.lock(item, LockModeType.OPTIMISTIC);
```

Mode này yêu cầu kiểm tra optimistic version theo semantics JPA, kể cả trong use case đọc cần xác minh phiên bản nhưng không nhất thiết thay đổi field.

Provider có thể thực hiện kiểm tra vào cuối transaction; đừng giả định mọi xung đột sẽ bị ném ngay tại `em.lock()`.

### 17.2. OPTIMISTIC_FORCE_INCREMENT

```java
em.lock(
    item,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
```

Mode này yêu cầu increment version theo hợp đồng thích hợp, có thể dùng khi thay đổi ở một phần của aggregate mà muốn biểu diễn bằng version của entity owner.

Nhưng việc increment có thể diễn ra muộn; không tự sửa version bằng tay hoặc dự đoán SQL cụ thể.

### 17.3. Không lạm dụng FORCE_INCREMENT

Nếu mỗi request chỉ đọc cũng làm tăng version, hệ thống có thể tạo write contention và false conflicts không cần thiết. Chỉ sử dụng khi cần semantics đó.

## 18. Bulk JPQL UPDATE/DELETE có thể bỏ qua @Version

Một bulk query:

```jpql
UPDATE InventoryItem i
SET i.available = i.available - :qty
WHERE i.id = :id
```

thực thi trực tiếp ở database. Nó không đi qua managed-entity dirty checking/optimistic checking cho từng entity như cập nhật thông thường.

### 18.1. Vì sao nguy hiểm?

Nếu bulk update đổi `available` nhưng không kiểm tra/tăng `version`, các transactions JPA khác có thể tiếp tục làm việc với version không phản ánh thay đổi này.

### 18.2. Một conditional bulk update có chủ đích

```jpql
UPDATE InventoryItem i
SET i.available = i.available - :qty,
    i.reserved = i.reserved + :qty,
    i.version = i.version + 1
WHERE i.id = :id
  AND i.version = :expectedVersion
  AND i.available >= :qty
```

Nếu chủ động chọn cách này, ứng dụng phải:

1. Bind params chính xác.
2. Kiểm tra `executeUpdate()` trả bao nhiêu hàng.
3. Phân biệt 0 do version mismatch, hết hàng hoặc ID không tồn tại.
4. Quản lý persistence context đã stale sau bulk DML.
5. Xác nhận domain invariants, transaction và version numbering.
6. Không xem đây là cơ chế managed-entity optimistic locking tự động.

Với CRUD bình thường, managed entity có `@Version` dễ dùng và bảo trì hơn.

### 18.3. Native SQL và procedure

JDBC/native DML/stored procedures cũng phải tuân thủ version contract nếu cùng cập nhật bảng. Một entity có `@Version` không có nghĩa mọi câu SQL bên ngoài JPA đều tự động kiểm tra cột ấy.

## 19. Optimistic locking không bảo vệ mọi invariant đa hàng

Ví dụ quy tắc:

> Không được có quá 10 booking cho cùng một khung giờ.

Hai transactions có thể cùng:

```text
SELECT COUNT(bookings) -> 9
INSERT booking khác nhau
COMMIT
```

Nếu chúng không cập nhật chung một versioned row, `@Version` trên từng Booking riêng lẻ có thể không ngăn việc tổng vượt 10. Đây có thể là **write skew/phantom**.

Các lựa chọn:

- Một aggregate root/version row chung.
- Unique/check constraint hoặc cấu trúc DB thích hợp.
- Atomic conditional update.
- Pessimistic lock ở đúng hàng/nguồn tài nguyên.
- Isolation phù hợp.
- Serialize công việc qua queue theo khóa nghiệp vụ.

Không coi một optimistic version field là bằng chứng hệ thống đã serializable cho mọi loại invariant.

## 20. Retry và side effects bên ngoài database

Một workflow sai:

```text
Update inventory
Send email "Đã đặt hàng"
Call payment gateway
Commit -> OptimisticLockException
```

Database rollback nhưng email/thanh toán có thể đã xảy ra. Retry có thể tạo side effect trùng.

### 20.1. Transactional outbox

Một giải pháp:

```text
Trong transaction:
    Update inventory
    Create reservation
    Insert outbox_event
    COMMIT

Sau commit:
    Dispatcher đọc outbox_event
    Gửi thông báo/idempotent external call
```

Nếu optimistic conflict dẫn tới rollback, cả reservation và outbox event không được commit.

### 20.2. Outbox không tự bảo đảm exactly once

Dispatcher có thể gửi xong rồi crash trước khi đánh dấu đã gửi. Cần deduplication hoặc idempotency key cho hệ thống nhận.

### 20.3. Thanh toán cần workflow riêng

Với payment, phải phân biệt transaction DB và giao dịch gateway. Có thể cần idempotency key, trạng thái pending/confirmed hoặc saga. Đừng retry toàn bộ hành vi ngoài DB chỉ vì bắt một exception khóa lạc quan.

## 21. Khi nào cân nhắc khóa bi quan?

Nếu một row tồn kho bị cập nhật liên tục bởi rất nhiều transaction, tỷ lệ optimistic conflicts có thể rất cao.

Ví dụ:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

Điều này yêu cầu database locking theo provider/DBMS. Nó có thể giảm optimistic retries nhưng tăng thời gian chờ, timeout hoặc deadlock.

Chọn chiến lược dựa trên số liệu thực tế:

- Conflict rate.
- Retry attempts và thời gian chờ.
- Tần suất update hot keys.
- Throughput/latency p95, p99.
- Deadlock và lock duration.
- Khả năng dùng atomic conditional update.

Không đổi toàn bộ hệ thống sang pessimistic locking chỉ vì nhìn thấy một conflict hiếm gặp.

## 22. Kiểm thử với hai transactions thật

Mock `EntityManager` có thể xác nhận code gọi `flush()`, nhưng không chứng minh DB phát hiện stale version. Cần integration test với hai persistence contexts độc lập.

### 22.1. Kịch bản

```text
Seed Item#101:
  available=10
  reserved=0
  version=7

Transaction A: begin, find Item#101 (v=7)
Transaction B: begin, find Item#101 (v=7)
A.reserve(4)
B.reserve(3)
A.flush / commit -> success, v=8
B.flush / commit -> optimistic conflict
B.rollback
Read new context -> available=6, reserved=4
```

### 22.2. Mã test minh họa

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

EntityTransaction txA = emA.getTransaction();
EntityTransaction txB = emB.getTransaction();

try {
    txA.begin();
    txB.begin();

    InventoryItem a =
        emA.find(InventoryItem.class, 101L);

    InventoryItem b =
        emB.find(InventoryItem.class, 101L);

    a.reserve(4);
    b.reserve(3);

    txA.commit();

    try {
        emB.flush();
        txB.commit();

        throw new AssertionError(
            "Expected optimistic conflict"
        );
    } catch (OptimisticLockException
            | RollbackException ex) {

        if (!PersistenceFailureClassifier
                .isOptimisticConflict(ex)) {
            throw ex;
        }

        if (txB.isActive()) {
            txB.rollback();
        }
    }
} finally {
    if (txA.isActive()) {
        txA.rollback();
    }
    if (txB.isActive()) {
        txB.rollback();
    }

    emA.close();
    emB.close();
}
```

Đây là kịch bản minh họa cho resource-local JPA; phải quản lý test fixture, isolation, thứ tự flush/commit và database thật để tránh test treo hoặc bắt nhầm lỗi. Khi điều chỉnh để thành test tự động, nên bảo đảm rollback dọn tài nguyên ngay cả khi gặp assertion failure.

### 22.3. Vì sao cần hai EntityManager?

Một EntityManager có first-level cache/identity map. Hai lần `find` cùng ID trong một persistence context thường trả cùng managed instance, **không tạo hai snapshots độc lập**.

### 22.4. Hậu điều kiện quan trọng hơn tên exception

Sau xung đột:

- Chỉ A commit.
- B không để lại partial updates.
- Version đã thay đổi.
- Đọc bằng EntityManager mới cho state đúng.
- Retry (nếu có) dùng context mới và xác minh lại invariant.

## 23. Kiểm thử trường hợp form đã cũ

Một test riêng:

1. GET entity trả version 4.
2. Request khác cập nhật thành version 5.
3. PUT sử dụng expectedVersion 4.
4. Server phải nhận diện stale form theo hợp đồng.

Test này phát hiện thiếu sót mà test hai transactions trong cùng thời điểm không thấy: nếu server luôn `find` version mới nhất rồi ghi, `@Version` có thể không chặn việc ghi đè form cũ.

## 24. Logging và quan sát production

Có thể theo dõi:

- Tỷ lệ optimistic conflicts theo operation.
- Số attempt và thành công sau retry.
- Entity type/hot keys theo chính sách bảo mật.
- Latency và số rollback.
- Conflict phát sinh ở flush hay commit nếu xác định được.
- Số request phải trả conflict cho người dùng.

Không log toàn bộ detached/managed object vì có thể chứa dữ liệu cá nhân và kích hoạt lazy loading trong `toString()`.

Một số conflict là hành vi bình thường của ứng dụng đồng thời. Nếu chúng tăng mạnh ở vài rows, xem xét lại aggregation, mô hình versioning hoặc locking strategy.

## 25. Những lỗi thường gặp

### 25.1. Catch optimistic conflict rồi commit tiếp

**Sai:** catch không xóa rollback-only.

**Đúng:** rollback và kết thúc lượt transaction lỗi.

### 25.2. Retry trong cùng EntityManager

**Sai:** vẫn giữ state cũ và transaction có thể rollback-only.

**Đúng:** transaction và persistence context mới.

### 25.3. Chỉ catch quanh setter

**Sai:** SQL check có thể xảy ra ở flush/commit.

**Đúng:** bao cả transaction boundary trong cơ chế rollback/error handling.

### 25.4. Coi isActive là có thể commit

**Sai:** active transaction có thể rollback-only.

### 25.5. Bắt mọi RollbackException rồi retry

**Sai:** rollback có thể do nhiều nguyên nhân khác.

### 25.6. Tự chỉnh version field

**Sai:** version của managed entity thuộc trách nhiệm provider.

### 25.7. Merge detached entity cũ như cách retry

**Sai:** stale state vẫn được mang sang transaction mới.

### 25.8. Tự retry form chỉnh sửa

**Sai:** có thể làm mất thay đổi của người khác.

### 25.9. Tin @Version phát hiện form cũ nếu server đọc state mới trước khi ghi

**Sai:** cần expectedVersion từ request.

### 25.10. Dùng một @Transactional bao cả vòng retry

**Sai:** các attempt có thể vẫn chung một transaction lỗi.

### 25.11. Gọi @Transactional qua this.method()

**Sai:** Spring proxy-based interceptor có thể bị bỏ qua.

### 25.12. Dùng REQUIRES_NEW khắp nơi

**Sai:** có thể tạo commit độc lập phá workflow atomic.

### 25.13. Không quản lý side effects trước commit

**Sai:** notification/payment không rollback cùng database.

### 25.14. Cho rằng bulk update tự tăng @Version

**Sai:** bulk JPQL DML không được quản lý như update của từng entity.

### 25.15. Cho rằng @Version đảm bảo mọi constraint đa hàng

**Sai:** cần bảo vệ đúng phạm vi dữ liệu/invariant.

### 25.16. Chỉ test optimistic locking với một EntityManager

**Sai:** không tạo hai snapshots độc lập.

### 25.17. Cho rằng flush thành công nghĩa commit chắc chắn thành công

**Sai:** flush không phải transaction commit.

### 25.18. Nhận được OptimisticLockException nghĩa có thể retry vô hạn

**Sai:** phải đánh giá tính an toàn, giới hạn và trạng thái nghiệp vụ mới.

## 26. Bài tập thực hành

### Bài 1 — Version conflict

Hai transactions đọc version 4. A ghi lên version 5. B thử UPDATE theo version 4.

**Đáp án:** B không khớp phiên bản; có thể nhận `OptimisticLockException`, transaction B phải rollback.

### Bài 2 — Catch rồi commit

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    logger.warn("Ignored");
}
tx.commit();
```

**Đáp án:** Sai. Transaction đã rollback-only, cần rollback.

### Bài 3 — isActive trả true

`tx.isActive()` là true ngay sau optimistic conflict.

**Đáp án:** Không thể kết luận transaction có thể commit. Active không đồng nghĩa không rollback-only.

### Bài 4 — Lỗi xuất hiện ở commit

`tx.commit()` ném `RollbackException` chứa `OptimisticLockException`.

**Đáp án:** Phân loại cause chain; không chỉ catch lỗi ở `flush()`.

### Bài 5 — Tồn kho sau retry

Ban đầu còn 10; yêu cầu giữ 4. Transaction khác giữ 7 trước, làm attempt đầu conflict.

**Đáp án:** Reload còn 3 rồi từ chối giữ 4, không tự ép ghi.

### Bài 6 — Form HTTP cũ

A mở form version 5, B lưu version 6, A gửi PUT sau đó.

**Đáp án:** Dùng expectedVersion hoặc If-Match, báo conflict hoặc precondition failed, không âm thầm ghi đè.

### Bài 7 — @Transactional và retry

Một method có `@Transactional` bao vòng for 3 attempts.

**Đáp án:** Có thể vẫn một transaction. Đặt transaction boundary **bên trong từng attempt** bằng worker proxied hoặc TransactionTemplate.

### Bài 8 — Side effect trước commit

Transaction gửi email rồi xảy ra optimistic conflict.

**Đáp án:** Email không rollback. Dùng transactional outbox và idempotency.

### Bài 9 — Bulk UPDATE

Query bulk cập nhật available mà không đổi version.

**Đáp án:** Có thể làm mất hiệu lực optimistic version check của writer JPA khác; cần conditional update/version contract.

### Bài 10 — Nhiều entities

Transaction cập nhật Order, Inventory và tạo Reservation; Inventory bị conflict.

**Đáp án:** Rollback toàn bộ transaction, không chỉ Inventory.

### Bài 11 — Merge detached

Entity detached v=3, DB v=4, gọi `em.merge(detached)`.

**Đáp án:** Có thể phát hiện conflict tại merge/flush/commit; không dùng merge như cơ chế ép ghi đè.

### Bài 12 — Optimistic vs pessimistic

Một hot row có xung đột liên tục và retry nhiều lần.

**Đáp án:** Đo latency/conflict, cân nhắc pessimistic lock hoặc atomic conditional update phù hợp; không đổi strategy không có số liệu.

### Bài 13 — Vi phạm invariant đa hàng

Hai transactions cùng thấy 9 bookings, cùng insert booking thứ 10/11 vào hai rows khác nhau.

**Đáp án:** `@Version` từng Booking không tự bảo vệ quota; cần cơ chế chung ở mức invariant.

### Bài 14 — Test hai transactions

Vì sao cần hai EntityManager?

**Đáp án:** Để có hai persistence contexts và snapshots độc lập.

### Bài 15 — Khi nào báo thành công?

`em.flush()` chạy xong và đã đọc remaining.

**Đáp án:** Chưa đủ; transaction còn phải commit thành công trước khi xác nhận persistence bền vững.

## 27. Câu hỏi tự kiểm tra

**1. `@Version` có vai trò gì?**

Cho JPA provider quản lý phiên bản entity và kiểm tra stale updates.

**2. Optimistic conflict có thể xuất hiện ở những thời điểm nào?**

Có thể ở merge, lock, flush hoặc commit tùy cách provider thực thi.

**3. Setter có bắt buộc ném OptimisticLockException ngay không?**

Không. Setter thường chỉ thay đổi field Java.

**4. Transaction bị optimistic conflict có thể tiếp tục commit không?**

Không nên; nó bị đánh dấu rollback-only.

**5. Catch exception có tự phục hồi transaction không?**

Không.

**6. `tx.isActive()` có chứng minh transaction có thể commit không?**

Không.

**7. `em.clear()` có xóa rollback-only không?**

Không.

**8. Sau rollback nên làm gì nếu retry?**

Tạo transaction/persistence context mới, đọc lại dữ liệu và tính lại nghiệp vụ.

**9. Có nên mang entity cũ sang transaction mới để merge ngay không?**

Không như một cách retry mặc định; state cũ có thể stale.

**10. Tại sao cần bắt exception ở ranh giới transaction?**

Vì conflict có thể chỉ lộ khi commit, sau khi thân method hoàn thành.

**11. RollbackException có luôn nghĩa optimistic conflict không?**

Không.

**12. Spring có thể dịch optimistic exception sang nhóm nào?**

`OptimisticLockingFailureException` và các subtype, tùy nơi phát sinh.

**13. Vì sao một vòng retry trong @Transactional có thể sai?**

Vì mọi attempt có thể cùng dùng một transaction rollback-only.

**14. Vì sao self-invocation gây vấn đề?**

Trong proxy-based Spring, gọi cùng bean có thể không đi qua transaction interceptor.

**15. Version trong request HTTP cần để làm gì?**

Phát hiện stale form giữa các requests.

**16. `@Version` của JPA có tự chặn stale form nếu server luôn đọc current version rồi ghi không?**

Không nhất thiết.

**17. Có nên tự retry mọi chỉnh sửa của người dùng không?**

Không; có thể ghi đè thay đổi hợp lệ của người khác.

**18. Bulk JPQL UPDATE có tự động kiểm tra @Version như entity update không?**

Không.

**19. Có nên gửi email trước commit trong workflow retryable không?**

Không nếu thiếu cơ chế đảm bảo/idempotency.

**20. Khóa lạc quan có bảo vệ mọi invariant đa hàng không?**

Không.

**21. Một optimistic conflict có làm rollback các bước khác cùng transaction không?**

Có, giao dịch phải rollback như một đơn vị.

**22. Nếu retry đọc lại và phát hiện không đủ hàng, nên xử lý sao?**

Trả business rejection, không lặp vô hạn.

**23. Khi nào cân nhắc pessimistic locking?**

Khi tranh chấp cao và các retry quá tốn kém, sau khi đánh giá DB lock contention.

**24. Kiểm thử thực tế optimistic conflict cần gì?**

Hai transaction và persistence contexts độc lập trên database thực.

## 28. Tình huống tổng hợp: xác nhận đơn hàng

Một lệnh xác nhận đơn hàng có thể mang:

```java
record ConfirmOrderCommand(
    long orderId,
    long productId,
    int quantity,
    long expectedOrderVersion
) {}
```

Yêu cầu:

- Order vẫn ở trạng thái DRAFT.
- Client không dùng một phiên bản Order đã cũ.
- Inventory còn đủ hàng.
- Giữ hàng, chuyển trạng thái Order và ghi outbox phải cùng transaction.
- Không gửi thông báo khi transaction rollback.

### 28.1. Luồng đề xuất

```text
HTTP command
    |
    v
Authorization / Validation
    |
    v
Transaction attempt
    |
    +-- Find current Order
    +-- Compare expectedOrderVersion
    +-- Verify Order is DRAFT
    +-- Find current Inventory
    +-- Re-check available stock
    +-- Reserve stock
    +-- Confirm Order
    +-- Insert outbox event
    |
    v
Flush / Commit
    |
    +-- Success -> respond confirmed
    |
    +-- Optimistic conflict
             |
             v
          Rollback
             |
             v
       New transaction if
       domain-safe to retry
             |
             v
       Re-evaluate rules
```

### 28.2. Xung đột version của Order khác với xung đột tồn kho

- Nếu `expectedOrderVersion` của client không khớp, người dùng đã dựa trên bản đơn cũ. Cần từ chối/giải quyết conflict theo contract.
- Nếu Order hợp lệ nhưng Inventory xung đột lúc flush, có thể thử lại số lần hữu hạn nếu quy tắc giữ kho cho phép.
- Nếu sau reload không đủ hàng, trả lỗi nghiệp vụ; không cần gọi đó là optimistic conflict mãi.

### 28.3. Hậu điều kiện cần kiểm thử

Khi thành công:

- Order chuyển trạng thái đúng một lần.
- Không âm tồn kho.
- Reservation được ghi đầy đủ.
- Outbox event chỉ được commit cùng transaction.
- API trả thành công sau commit.

Khi thất bại:

- Không có partial commit.
- Không gửi thông báo sai.
- EntityManager của lượt lỗi không được dùng tiếp.
- Client nhận lỗi phù hợp để quyết định tải lại/retry.

## 29. Kết luận

`OptimisticLockException` báo rằng một transaction đã cố xử lý dữ liệu không còn phù hợp với phiên bản mà nó dựa vào. Xử lý đúng không dừng ở `catch`: **trạng thái transaction và persistence context phải được xử lý như phần của lỗi**.

Các quy tắc cần nhớ:

1. **`@Version` giúp phát hiện stale updates** khi ghi managed entities, nhưng không tự bảo vệ mọi writer và mọi invariant đa hàng.
2. **Lỗi có thể xuất hiện ở flush hoặc commit**, không chỉ ở setter/merge.
3. **Giao dịch gặp optimistic conflict bị rollback-only**. Catch không cho phép commit tiếp.
4. **Rollback và kết thúc context lỗi**. Không dùng clear/refresh để cố chữa transaction.
5. **Retry phải dùng transaction/context mới**, đọc state mới và tính lại toàn bộ nghiệp vụ; luôn có giới hạn và phân loại lỗi.
6. **Không tự retry chỉnh sửa dựa trên form cũ**. Dùng expectedVersion/ETag để giữ ý định người dùng.
7. **Bulk JPQL/native SQL phải phối hợp versioning**, nếu không có thể bỏ qua bảo vệ của JPA.
8. **Side effects bên ngoài database cần outbox/idempotency**, không được thực hiện tùy tiện trước commit.
9. **Kiểm thử bằng hai transactions thật** để xác nhận rollback và kết quả cuối đúng.

Nắm được các nguyên tắc này giúp ứng dụng JPA không chỉ phát hiện **lost update** mà còn **phục hồi an toàn sau xung đột**, không làm hỏng transaction boundaries, dữ liệu nghiệp vụ hoặc trải nghiệm của người dùng.
