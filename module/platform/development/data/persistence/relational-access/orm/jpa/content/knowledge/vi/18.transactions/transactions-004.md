# Kiểm tra trạng thái giao dịch và cờ rollback-only trong JPA

## 1. Vì sao phải kiểm tra trạng thái transaction?

Khi thao tác với cơ sở dữ liệu qua **Jakarta Persistence (JPA)**, việc gọi `persist()`, sửa một entity managed hoặc `flush()` chưa có nghĩa dữ liệu chắc chắn đã được commit. Các thao tác ghi cần nằm trong một **transaction** và transaction đó phải kết thúc thành công.

Một transaction có thể:

- Chưa bắt đầu.
- Đang hoạt động và vẫn có khả năng commit.
- Đang hoạt động nhưng **đã được đánh dấu rollback-only**.
- Đang commit hoặc rollback.
- Đã kết thúc bằng commit hoặc rollback.

Giả sử một use case chuyển tiền có hai bước:

```text
BEGIN TRANSACTION
   |
   +-- Trừ 500.000 khỏi tài khoản A
   |
   +-- Cộng 500.000 vào tài khoản B
   |
   +-- Phát hiện một điều kiện nghiệp vụ không được đáp ứng
   |
   +-- Không được commit chỉ bước đã thực hiện
   |
   v
ROLLBACK
```

Nếu quy tắc nghiệp vụ phát hiện lỗi nhưng code vẫn gọi `commit()`, một phần thay đổi đang chờ có thể được ghi xuống database. **Cờ rollback-only** là tín hiệu để transaction manager biết rằng **transaction hiện tại không được phép kết thúc bằng commit thành công**.

Trong JPA, hai câu hỏi rất quan trọng nhưng khác nhau:

1. **Transaction có đang hoạt động không?** — Ví dụ với resource-local: `EntityTransaction.isActive()`.
2. **Transaction đã bị đánh dấu chỉ được rollback chưa?** — Ví dụ: `EntityTransaction.getRollbackOnly()`.

Cần hiểu cả hai để thiết kế nhánh thành công, nhánh lỗi và xử lý cleanup đúng cách.

## 2. Phân biệt transaction, persistence context và trạng thái entity

Trong JPA có ba lớp khái niệm:

| Khái niệm | Chức năng | API/biểu hiện tiêu biểu |
|---|---|---|
| **Transaction** | Đơn vị công việc được commit hoặc rollback. | `EntityTransaction` hoặc transaction manager/JTA. |
| **Persistence context** | Quản lý identity và trạng thái các entity Java. | `EntityManager`, `find`, `persist`, `flush`, `clear`. |
| **Entity lifecycle** | Entity là new, managed, detached, removed. | `em.contains(entity)` kiểm tra entity có thuộc context hiện tại không. |

Một entity đang **managed** không chứng minh transaction đang hoạt động. Ví dụ, application-managed `EntityManager` có thể tiếp tục tồn tại giữa các transaction; entity còn trong context nhưng transaction trước đã kết thúc.

Ngược lại, transaction đang active không có nghĩa tất cả object Java có ID đều managed.

**Cờ rollback-only thuộc về transaction**, không phải một field của entity và không phải thuộc tính của `@Version`.

### 2.1. `flush()` không phải `commit()`

```java
tx.begin();

Product product = em.find(Product.class, productId);
product.changePrice(new BigDecimal("250000.00"));

em.flush();  // Có thể gửi SQL UPDATE, chưa commit.
tx.rollback();
```

Nếu transaction rollback thành công, các thay đổi chưa commit trong transaction sẽ bị hủy theo semantics của database. Việc `flush()` không lỗi **không bảo đảm** transaction sau đó sẽ commit.

Đặc biệt, rollback không tự sửa các biến Java đã thay đổi:

```text
Java object: product.price = 250000
Database sau rollback: product.price vẫn là giá trị đã commit trước đó
```

Sau rollback, không nên tiếp tục sử dụng state của persistence context cũ để ra quyết định như thể nó đã được đồng bộ lại. Đóng context của đơn vị công việc thất bại và tải lại trong context mới thường là cách an toàn.

## 3. Transaction resource-local và JTA là hai mô hình khác nhau

JPA hỗ trợ các mô hình điều phối transaction khác nhau. Trước khi kiểm tra rollback-only, phải xác định đang chạy trong môi trường nào.

### 3.1. Resource-local transaction

Trong Java SE hoặc ứng dụng chủ động quản lý transaction theo `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
// Thao tác JPA.
tx.commit();
```

API cần dùng là **`jakarta.persistence.EntityTransaction`**. Nó cung cấp:

- `begin()`
- `commit()`
- `rollback()`
- `setRollbackOnly()`
- `getRollbackOnly()`
- `isActive()`

Đây là trọng tâm kỹ thuật cho các ví dụ Java SE trong bài.

### 3.2. JTA / container-managed transaction

Trong Jakarta EE hoặc môi trường framework quản lý transaction, application code thường **không gọi `em.getTransaction().begin()`**.

Ví dụ container-managed JPA:

```java
@PersistenceContext
private EntityManager em;
```

Transaction có thể do EJB container hoặc Jakarta Transactions `@Transactional` quản lý. Để quan sát/đánh dấu rollback-only, dùng API của môi trường đó, chẳng hạn:

- `jakarta.transaction.TransactionSynchronizationRegistry`.
- `jakarta.transaction.UserTransaction` đối với kiểu quản lý transaction phù hợp.
- `jakarta.ejb.SessionContext` trong EJB container-managed transaction.
- `TransactionStatus` của Spring khi ứng dụng dùng Spring transaction manager.

**Không trộn** `EntityTransaction` resource-local với transaction JTA trong cùng đoạn code chỉ vì cả hai đều có khái niệm rollback.

## 4. Các phương thức quan trọng của `EntityTransaction`

### 4.1. `isActive()`

```java
boolean active = tx.isActive();
```

Trả về `true` khi transaction resource-local đang active, và `false` khi không có transaction active theo semantics của API.

Ví dụ:

```java
EntityTransaction tx = em.getTransaction();

System.out.println(tx.isActive()); // false, nếu chưa begin.

tx.begin();
System.out.println(tx.isActive()); // true.

tx.rollback();
System.out.println(tx.isActive()); // false.
```

Điểm dễ nhầm: `isActive() == true` **không đồng nghĩa** transaction chắc chắn còn được commit. Một transaction đã bị đánh dấu rollback-only thường **vẫn đang active** cho tới khi rollback hoặc kết thúc bằng quy trình transaction.

### 4.2. `setRollbackOnly()`

```java
tx.setRollbackOnly();
```

Đánh dấu rằng transaction hiện tại phải rollback, không được kết thúc thành công bằng commit. Việc đánh dấu **không đồng nghĩa đã rollback ngay lập tức**.

```text
ACTIVE
  |
  | tx.setRollbackOnly()
  v
ACTIVE + ROLLBACK-ONLY
  |
  | tx.rollback()
  v
ROLLED BACK
```

Transaction có thể vẫn còn trong phạm vi xử lý của đoạn code sau khi đặt cờ; nên dừng những bước ghi không cần thiết và chuyển tới cleanup/rollback.

### 4.3. `getRollbackOnly()`

```java
boolean marked = tx.getRollbackOnly();
```

Trong **resource-local transaction đang active**, phương thức trả về cờ rollback-only theo trạng thái hiện tại.

Ví dụ:

```java
tx.begin();

System.out.println(tx.getRollbackOnly()); // Thường false ban đầu.

tx.setRollbackOnly();

System.out.println(tx.getRollbackOnly()); // true.

tx.rollback();
```

**Quan trọng:** `getRollbackOnly()` yêu cầu có transaction active; nếu gọi lúc không có transaction active, API có thể ném `IllegalStateException` theo hợp đồng của `EntityTransaction`. Vì vậy phải kiểm tra `isActive()` trước khi gọi.

### 4.4. `commit()`

```java
tx.commit();
```

Yêu cầu transaction được commit. Nếu transaction đã được đánh dấu rollback-only, provider phải xử lý rollback thay vì commit thành công và có thể báo **`RollbackException`** theo JPA contract. Các lỗi khác trong quá trình flush/commit cũng có thể khiến transaction không commit.

Không nên viết business logic coi `commit()` là phép gán đơn giản “`committed = true`”; nó là thao tác có thể thất bại.

### 4.5. `rollback()`

```java
tx.rollback();
```

Yêu cầu rollback một transaction đang active. Đây là thao tác kết thúc transaction, không phải chỉ đặt cờ.

Sự khác biệt rất quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `setRollbackOnly()` | Đánh dấu transaction **phải rollback** khi kết thúc. |
| `getRollbackOnly()` | Xem transaction **đã bị đánh dấu** rollback-only chưa. |
| `rollback()` | **Thực hiện rollback** transaction. |
| `commit()` | Yêu cầu commit; không thể commit thành công nếu rollback-only. |
| `isActive()` | Kiểm tra transaction **còn đang hoạt động** hay không. |

## 5. Sơ đồ trạng thái transaction resource-local

Hình dung chu trình:

```text
                    +------------------+
                    |  KHÔNG ACTIVE    |
                    +------------------+
                             |
                             | begin()
                             v
                    +------------------+
                    |      ACTIVE      |
                    | rollbackOnly=no  |
                    +------------------+
                       |            |
             commit()  |            | setRollbackOnly()
               thành   |            v
               công    |      +----------------------+
                       |      | ACTIVE               |
                       |      | rollbackOnly=yes     |
                       |      +----------------------+
                       |            |
                       |            | rollback()
                       |            | hoặc commit() bị từ chối
                       |            v
                       |        ROLLED BACK
                       v
                    COMMITTED

ACTIVE -- rollback() --> ROLLED BACK
ACTIVE -- lỗi khi ghi/commit --> có thể rollback/failure
```

Đây là sơ đồ khái niệm. Lỗi kết nối, lỗi database hoặc implementation provider có thể tạo những trạng thái trung gian phức tạp hơn. **`EntityTransaction` không có API tiêu chuẩn để lấy mọi trạng thái chi tiết của JTA như `STATUS_PREPARING`**.

Một bảng quyết định đơn giản:

| `isActive()` | `getRollbackOnly()` | Hành động thông thường |
|---|---|---|
| `false` | **Không gọi** | Transaction đã không active; kiểm tra xem use case đã kết thúc chưa. |
| `true` | `false` | Có thể tiếp tục quy trình, nhưng commit vẫn có thể lỗi do lý do khác. |
| `true` | `true` | Dừng việc ghi mới và rollback theo luồng xử lý. |

**Không phải cứ `getRollbackOnly() == false` là commit chắc chắn thành công.** Giữa thời điểm kiểm tra và commit có thể phát sinh lỗi ràng buộc, deadlock, timeout, optimistic lock conflict hoặc lỗi hệ thống.

## 6. Kiểm tra cờ đúng thời điểm: guard trước `getRollbackOnly()`

Sai:

```java
EntityTransaction tx = em.getTransaction();

// Chưa begin:
if (tx.getRollbackOnly()) {
    // Có thể ném IllegalStateException.
}
```

Đúng khi cần quan sát:

```java
EntityTransaction tx = em.getTransaction();

if (!tx.isActive()) {
    System.out.println("Không có transaction đang hoạt động");
} else if (tx.getRollbackOnly()) {
    System.out.println("Transaction đã được đánh dấu rollback-only");
} else {
    System.out.println("Transaction đang hoạt động, chưa rollback-only");
}
```

Có thể đóng gói một helper chẩn đoán chỉ dùng với resource-local transaction:

```java
public static String describe(EntityTransaction tx) {
    if (!tx.isActive()) {
        return "NO_ACTIVE_TRANSACTION";
    }
    return tx.getRollbackOnly()
            ? "ACTIVE_ROLLBACK_ONLY"
            : "ACTIVE_NOT_MARKED_ROLLBACK_ONLY";
}
```

Helper không chứng minh transaction đã commit thành công. Nó chỉ đọc một **snapshot trạng thái tại thời điểm gọi**. Nếu transaction được quản lý bởi một framework khác, helper này không thay thế API/framework quản lý transaction.

### 6.1. Không dùng `getRollbackOnly()` trong `finally` sau `commit()`

Ví dụ nguy hiểm:

```java
try {
    tx.begin();
    // ...
    tx.commit();
} finally {
    // Sai khi transaction đã kết thúc:
    System.out.println(tx.getRollbackOnly());
}
```

Sau commit, transaction không còn active. Nếu muốn ghi log trạng thái, lưu kết quả của operation thành công/thất bại và kiểm tra cờ **khi transaction còn active**.

## 7. Mẫu transaction an toàn trong Java SE

Ví dụ với `EntityManagerFactory` đã được khởi tạo, một service thay đổi một entity:

```java
public void renameCustomer(
        EntityManagerFactory emf,
        Long customerId,
        String newName
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer =
                em.find(Customer.class, customerId);

        if (customer == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy khách hàng"
            );
        }

        customer.rename(newName);

        // Managed entity được dirty checking.
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
}
```

Giả định `Customer` là entity đã được mapping với `@Id` và phương thức `rename` bảo vệ dữ liệu đầu vào; import gồm `jakarta.persistence.EntityManager`, `EntityManagerFactory`, `EntityTransaction`.

Các ý chính:

1. `tx.begin()` tạo ranh giới transaction rõ ràng.
2. `em.find()` tải entity trong context.
3. Business method chỉ thay đổi state; provider ghi khi flush/commit.
4. Nếu có exception, kiểm tra `tx.isActive()` trước khi cố rollback.
5. Nếu rollback cũng lỗi, giữ lại exception gốc và thêm lỗi rollback bằng `addSuppressed`.
6. `em.close()` giải phóng application-managed EntityManager bất kể thành công hay thất bại.

Trong code production, nếu `em.close()` cũng có khả năng ném exception, cần một chính sách ghi log/bảo toàn lỗi phù hợp. Mục tiêu của ví dụ là thể hiện luồng transaction chính.

**Lưu ý:** Catch exception rồi rollback là cách xử lý thông thường đối với lỗi. `setRollbackOnly()` đặc biệt hữu ích khi không thể hoặc không muốn rollback ngay tại vị trí phát hiện điều kiện thất bại, nhưng vẫn cần buộc outer scope không được commit.

## 8. Khi nào dùng rollback-only thay vì rollback ngay?

Một tình huống: service đã thực hiện nhiều thao tác trong transaction, một bước kiểm tra bổ sung phát hiện yêu cầu không hợp lệ nhưng API nội bộ trả **kết quả từ chối** thay vì ném exception ngay.

Ví dụ:

```text
BEGIN
  |
  +-- cập nhật state tạm thời của một aggregate managed
  |
  +-- kiểm tra chính sách liên quan
  |     |
  |     +-- Nếu không được phép:
  |            đánh dấu rollback-only
  |
  +-- outer service xem cờ
  |     |
  |     +-- rollback-only -> ROLLBACK
  |     +-- không -> COMMIT
  v
Kết thúc request
```

### 8.1. Entity minh họa: quản lý tồn kho

```java
package com.example.stock;

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

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    protected InventoryItem() {}

    public InventoryItem(String sku, int availableQuantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (availableQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho âm");
        }
        this.sku = sku;
        this.availableQuantity = availableQuantity;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0"
            );
        }
        if (quantity > availableQuantity) {
            throw new IllegalStateException(
                "Không đủ tồn kho"
            );
        }
        availableQuantity -= quantity;
    }
}
```

Ở đây, `reserve()` kiểm tra invariant cục bộ; `@Version` giúp phát hiện cập nhật đồng thời lên cùng một item. Nó không tự quyết định transaction nên commit hay rollback vì các bước ở use case có thể còn nhiều điều kiện bên ngoài entity.

### 8.2. Service đánh dấu rollback-only khi policy từ chối

Giả sử ngoài kiểm tra tồn kho còn có một chính sách nội bộ: yêu cầu trên `maximumUnitsPerRequest` phải bị từ chối. Ví dụ đặt policy sau thao tác dự trữ chỉ để làm rõ rollback của pending changes:

```java
public boolean tryReserve(
        EntityManagerFactory emf,
        Long itemId,
        int quantity,
        int maximumUnitsPerRequest
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        InventoryItem item = em.find(
            InventoryItem.class,
            itemId
        );

        if (item == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy hàng tồn kho"
            );
        }

        item.reserve(quantity);

        // Một policy khác của use case được kiểm tra
        // sau khi đã thay state managed.
        if (quantity > maximumUnitsPerRequest) {
            tx.setRollbackOnly();
        }

        if (tx.getRollbackOnly()) {
            tx.rollback();
            return false;
        }

        tx.commit();
        return true;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Ví dụ này chứng minh sự khác nhau giữa:

- **Thay đổi object managed:** `item.reserve(quantity)` làm giảm `availableQuantity` trong bộ nhớ.
- **Đánh dấu transaction không được commit:** `tx.setRollbackOnly()`.
- **Kiểm tra cờ trước khi kết thúc:** `tx.getRollbackOnly()`.
- **Thực thi rollback:** `tx.rollback()`.

Sau rollback, object `item` đã thay đổi ở Java không được coi là state database hiện tại. Đóng `em` và đọc lại trong context mới khi cần.

Trong code production, **nên kiểm tra những policy có thể kiểm tra sớm trước khi thay state**, để tránh công việc thừa. Ví dụ chỉ đặt policy sau thay đổi nhằm minh họa rằng rollback-only bảo vệ toàn bộ transaction, kể cả khi state managed đã bị chỉnh sửa.

### 8.3. Tại sao không gọi `commit()` sau khi đã đánh dấu?

Code sau sai về ý định:

```java
tx.begin();
// ...
tx.setRollbackOnly();
tx.commit();  // Không thể commit thành công theo ý định.
```

Khi rollback-only, transaction không được commit. Provider có thể rollback và ném `jakarta.persistence.RollbackException`. Nếu business logic đã biết cần hủy, **gọi `rollback()` rõ ràng** thường dễ hiểu hơn là cố tình gọi commit rồi đợi exception.

## 9. Cờ rollback-only là tín hiệu không thể “gỡ bỏ” bằng API chuẩn

Các API transaction phổ biến cho phép **đánh dấu** rollback-only nhưng không có phương thức đối xứng kiểu:

```java
tx.setRollbackOnly(false); // Không có trong EntityTransaction.
```

Sau khi transaction đã bị đánh dấu rollback-only, code không thể làm nó trở lại một transaction commit bình thường bằng một lệnh `unsetRollbackOnly()`.

Nếu application cần thử lại, cách đúng là:

1. Rollback transaction hiện tại.
2. Kết thúc/giải phóng context bị lỗi theo semantics provider.
3. Mở transaction mới.
4. Đọc lại state phù hợp.
5. Thực hiện lại thao tác nếu nghiệp vụ cho phép và nguyên nhân lỗi có thể khắc phục.

Không nên lưu lại tham chiếu entity đã thay đổi trong transaction rollback rồi tiếp tục ghi như thể nó đang ở trạng thái database mới nhất.

### 9.1. Vì sao cờ không được phép xóa?

Một thành phần trong transaction có thể phát hiện invariant vi phạm hoặc lỗi ràng buộc khiến commit không còn an toàn. Nếu thành phần khác có thể xóa cờ một cách tùy tiện, transaction có thể commit những thay đổi chưa đúng.

Rollback-only cho phép các tầng sâu hơn của use case đưa ra **yêu cầu tối thiểu về an toàn**: transaction phải kết thúc bằng rollback.

Tuy nhiên, đặt cờ không giúp tự động sửa mọi side effect ở ngoài database như gọi HTTP, gửi email hay ghi file.

## 10. Phân biệt rollback-only do ứng dụng đặt và do lỗi persistence

Cờ có thể do ứng dụng đặt tường minh:

```java
if (!businessRuleSatisfied) {
    tx.setRollbackOnly();
}
```

Hoặc transaction có thể bị đánh dấu rollback-only sau một lỗi trong quá trình thực thi, tùy loại lỗi và hợp đồng API/provider:

- Vi phạm ràng buộc database.
- `OptimisticLockException` khi version không khớp.
- Lỗi lock/timeout.
- Lỗi SQL hoặc lỗi flush có ảnh hưởng tới transaction.
- Runtime exception trong một transactional method được framework/container áp dụng quy tắc rollback.

Điều quan trọng là **không phải mọi exception đều có hậu quả transaction giống nhau**. Một số lỗi truy vấn/timeout hoặc lỗi API có thể có semantics riêng, và việc provider/container đánh dấu rollback-only phụ thuộc loại exception cùng đặc tả áp dụng.

Đừng viết:

```java
catch (Exception ex) {
    // Giả định mọi exception đều đã tự set rollback-only.
}
```

Thay vào đó, xác định transaction manager đang dùng, hiểu quy tắc rollback cho loại exception cụ thể, và để outer scope xử lý rollback hoặc propagate exception đúng cách.

### 10.1. Nếu đã bắt exception rồi tiếp tục

Ví dụ:

```java
tx.begin();

try {
    operationThatCanFail(em);
} catch (RuntimeException ex) {
    log.warn("Bước phụ đã lỗi", ex);
}

// Nếu transaction đã bị đánh dấu rollback-only,
// bước commit vẫn không thể thành công.
tx.commit();
```

Bắt exception **không xóa cờ rollback-only**. Việc log rồi tiếp tục không có nghĩa transaction đã trở lại trạng thái sạch.

Nếu một lỗi có thể bỏ qua về mặt nghiệp vụ, nên thiết kế bước đó tách transaction hoặc cấu trúc ngoại lệ rõ ràng từ đầu. Với một lỗi persistence nghiêm trọng, thường nên rollback đơn vị công việc hiện tại thay vì tiếp tục nhiều câu SQL trên transaction đã lỗi.

## 11. Điều gì xảy ra khi `commit()` gặp rollback-only?

Một luồng thường gặp:

```text
tx.begin()
  |
  +-- cập nhật entity A
  |
  +-- bước B phát hiện lỗi
  |
  +-- tx.setRollbackOnly()
  |
  +-- code ở tầng ngoài vẫn gọi tx.commit()
                  |
                  v
       Provider không được commit transaction
                  |
                  v
           Rollback / RollbackException
```

Trong resource-local JPA, `commit()` có thể ném **`RollbackException`** nếu commit không thành công và transaction được rollback.

Một đoạn code phòng lỗi:

```java
try {
    tx.begin();

    doWork(em);

    if (tx.getRollbackOnly()) {
        tx.rollback();
        throw new IllegalStateException(
            "Đã hủy transaction do điều kiện nghiệp vụ"
        );
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Nếu `doWork` đánh dấu rollback-only nhưng không ném exception, outer scope có thể chủ động rollback và trả kết quả lỗi nghiệp vụ phù hợp.

**Không dùng `getRollbackOnly() == false` làm tiêu chí duy nhất để kết luận an toàn:** trạng thái có thể thay đổi và commit có thể phát hiện lỗi mới.

### 11.1. Sau lỗi commit, không tự động gọi lại `commit()`

Nếu commit lỗi, không nên retry ngay trên **cùng EntityTransaction/EntityManager**. Transaction có thể đã rollback hoặc ở trạng thái không sử dụng tiếp an toàn, và state của entity trong context có thể không còn phù hợp.

Nếu muốn retry với lỗi mang tính tạm thời, cần một đơn vị công việc **mới**, đọc lại dữ liệu cần thiết, rồi thực hiện lại hành động theo chính sách idempotency/concurrency của nghiệp vụ.

## 12. JTA: trạng thái transaction được quản lý ở tầng khác

Trong môi trường **JTA**, không nên dùng `em.getTransaction()` trên một JTA EntityManager để điều khiển transaction:

```java
@PersistenceContext
private EntityManager em;

// Không phải cách điều phối transaction JTA:
EntityTransaction tx = em.getTransaction();
```

Việc gọi `getTransaction()` trên JTA entity manager có thể ném `IllegalStateException` theo API JPA. Transaction lúc này thuộc quyền điều phối của container/transaction manager.

### 12.1. `UserTransaction`

Với **bean-managed transaction** hoặc vị trí được cho phép dùng `UserTransaction`:

```java
import jakarta.annotation.Resource;
import jakarta.transaction.UserTransaction;

@Resource
private UserTransaction userTransaction;
```

Các thao tác chính:

```java
userTransaction.begin();
userTransaction.setRollbackOnly();
int status = userTransaction.getStatus();
userTransaction.rollback();
```

**`UserTransaction` không cung cấp `getRollbackOnly()` như `EntityTransaction`.** Để kiểm tra trạng thái, dùng `getStatus()` và so sánh với các hằng trong `jakarta.transaction.Status`.

Ví dụ:

```java
int status = userTransaction.getStatus();

if (status == Status.STATUS_MARKED_ROLLBACK) {
    // Transaction đã được đánh dấu rollback-only.
}
```

Trong source thật, cần import `jakarta.transaction.Status` và xử lý các checked exceptions JTA phù hợp. Không dùng `UserTransaction` để tự begin/commit trong những vị trí đang được container-managed transaction điều phối mà đặc tả/container không cho phép.

### 12.2. Các mã trạng thái JTA tiêu biểu

JTA cung cấp các hằng trạng thái:

| Hằng của `jakarta.transaction.Status` | Diễn giải |
|---|---|
| `STATUS_ACTIVE` | Transaction đang hoạt động. |
| `STATUS_MARKED_ROLLBACK` | Transaction được đánh dấu phải rollback. |
| `STATUS_PREPARING` | Đang chuẩn bị cho commit theo quy trình transaction manager. |
| `STATUS_PREPARED` | Đã chuẩn bị xong trong quy trình liên quan. |
| `STATUS_COMMITTING` | Đang commit. |
| `STATUS_COMMITTED` | Đã commit. |
| `STATUS_ROLLING_BACK` | Đang rollback. |
| `STATUS_ROLLEDBACK` | Đã rollback. |
| `STATUS_NO_TRANSACTION` | Không có transaction gắn với ngữ cảnh được hỏi. |
| `STATUS_UNKNOWN` | Không xác định được trạng thái. |

Các trạng thái trung gian có thể không thường xuyên xuất hiện trong code nghiệp vụ vì transaction manager điều phối chúng. Không cần tự tạo state machine JTA trong ứng dụng; dùng API manager tương ứng và để nó xử lý commit/rollback.

### 12.3. Ví dụ bean-managed transaction

Minh họa với `UserTransaction` và JTA `EntityManager`:

```java
public void updateWithinUserTransaction(
        UserTransaction utx,
        EntityManager em,
        Long customerId
) throws Exception {

    utx.begin();

    try {
        Customer customer = em.find(
            Customer.class,
            customerId
        );

        if (customer == null) {
            utx.setRollbackOnly();
        } else {
            customer.rename("Tên mới");
        }

        int status = utx.getStatus();

        if (status == Status.STATUS_MARKED_ROLLBACK) {
            utx.rollback();
            return;
        }

        utx.commit();
    } catch (Exception ex) {
        try {
            int status = utx.getStatus();
            if (status != Status.STATUS_NO_TRANSACTION
                    && status != Status.STATUS_COMMITTED
                    && status != Status.STATUS_ROLLEDBACK) {
                utx.rollback();
            }
        } catch (Exception rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }

        throw ex;
    }
}
```

Đây là ví dụ cấu trúc; cần chạy trong môi trường cho phép **bean-managed UserTransaction**, có JTA persistence context phù hợp, các import tương ứng, và xử lý cụ thể các ngoại lệ `NotSupportedException`, `SystemException`, `RollbackException`, `HeuristicMixedException`... khi xây dựng production code.

Ở transaction JTA đã kết thúc hoặc bị lỗi, thao tác rollback có thể bị từ chối; code cần tránh giả định mọi trạng thái đều cho phép rollback và phải có chính sách ghi log/cleanup phù hợp với container.

## 13. `TransactionSynchronizationRegistry`: kiểm tra rollback-only trong JTA

Trong Jakarta EE, `TransactionSynchronizationRegistry` cho phép truy cập thông tin transaction hiện tại theo cách phù hợp với JTA mà không cần cầm một `EntityTransaction`.

```java
import jakarta.annotation.Resource;
import jakarta.transaction.TransactionSynchronizationRegistry;

@Resource
private TransactionSynchronizationRegistry registry;
```

Các phương thức liên quan:

```java
int status = registry.getTransactionStatus();

boolean rollbackOnly = registry.getRollbackOnly();

registry.setRollbackOnly();
```

`getTransactionStatus()` trả trạng thái JTA dưới dạng số nguyên trong `Status`. `getRollbackOnly()` biểu diễn việc transaction hiện tại đã được đánh dấu rollback-only hay chưa; phải dùng trong ngữ cảnh có transaction tương ứng. Nếu không có transaction phù hợp, thao tác truy cập rollback-only có thể ném exception theo hợp đồng API.

Ví dụ trong một service container-managed:

```java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class BillingService {

    @Resource
    private TransactionSynchronizationRegistry registry;

    @Transactional
    public void charge() {
        // Thao tác JPA trong transaction hiện tại.

        if (!businessConditionSatisfied()) {
            registry.setRollbackOnly();
            return;
        }

        // Các bước còn lại...
    }

    private boolean businessConditionSatisfied() {
        // Minh họa: một quy tắc nội bộ.
        return false;
    }
}
```

Nếu thực thi trong một container hỗ trợ Jakarta Transactions `@Transactional` với JTA transaction, transaction bị đánh dấu rollback-only sẽ không thể commit thành công ở boundary. **Không nên dùng `registry.setRollbackOnly()` như cách trả lỗi nghiệp vụ im lặng** khi caller cần biết tác vụ đã bị từ chối; hãy trả kết quả hoặc ném domain exception rõ ràng theo contract.

### 13.1. Cẩn thận với các ngữ cảnh không có transaction

Một helper an toàn về mặt ý định:

```java
int status = registry.getTransactionStatus();

if (status == Status.STATUS_NO_TRANSACTION) {
    throw new IllegalStateException(
        "Thao tác yêu cầu transaction JTA"
    );
}

if (status == Status.STATUS_MARKED_ROLLBACK) {
    throw new IllegalStateException(
        "Transaction không thể commit"
    );
}
```

Các trường hợp `STATUS_UNKNOWN` hoặc trạng thái đang kết thúc cũng cần được coi là không phù hợp để bắt đầu một thao tác ghi mới. Tránh viết điều kiện chỉ cần `status != STATUS_NO_TRANSACTION` rồi kết luận transaction luôn có thể commit.

## 14. EJB container-managed transaction và `SessionContext`

Trong EJB dùng **container-managed transactions (CMT)**, `SessionContext` cung cấp:

- `setRollbackOnly()`
- `getRollbackOnly()`

Ví dụ:

```java
import jakarta.annotation.Resource;
import jakarta.ejb.SessionContext;
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class OrderBean {

    @Resource
    private SessionContext sessionContext;

    @PersistenceContext
    private EntityManager em;

    public void process(Long orderId) {
        Order order = em.find(Order.class, orderId);

        if (order == null) {
            sessionContext.setRollbackOnly();
            return;
        }

        order.process();

        if (sessionContext.getRollbackOnly()) {
            // Caller phải biết kết quả xử lý không thành công.
        }
    }
}
```

Giả định `Order` là entity hợp lệ và `process()` là domain method. Đoạn code dùng môi trường EJB container-managed transaction hỗ trợ các API trên.

Với **bean-managed transaction (BMT)**, không dùng `SessionContext.setRollbackOnly()` theo cùng giả định; dùng `UserTransaction` và lifecycle BMT thích hợp.

**Khi transaction được quản lý bởi container, không gọi thủ công `em.getTransaction().rollback()`** để xử lý những thao tác CMT. Đánh dấu rollback hoặc ném exception theo quy tắc container là cách đúng phạm vi.

## 15. Spring `@Transactional`: rollback-only và `UnexpectedRollbackException`

Nếu dự án dùng **Spring Framework/Spring Data JPA**, transaction thường được quản lý bởi Spring `PlatformTransactionManager`. API kiểm tra rollback-only là **Spring `TransactionStatus`**, không phải `EntityTransaction` của JPA trong một `@Transactional` service thông thường.

### 15.1. Kiểm tra/đánh dấu rollback-only trong Spring

Trong một method thực sự đang được Spring transactional advice quản lý:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.TransactionStatus;

@Transactional
public void executeBusinessCommand() {
    TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

    if (someConditionIsInvalid()) {
        status.setRollbackOnly();
        return;
    }

    // Xử lý tiếp khi hợp lệ.
}
```

`status.isRollbackOnly()` có thể được dùng để quan sát cờ theo semantics của Spring.

Lưu ý:

- Đây là API **Spring**, không phải Jakarta Persistence chuẩn.
- `currentTransactionStatus()` đòi hỏi method đang nằm trong transaction interceptor đúng cách; gọi ở nơi không có transaction status thích hợp có thể lỗi.
- `setRollbackOnly()` là lệnh đánh dấu transaction để rollback; caller cần contract rõ về kết quả.
- Cách một trạng thái rollback-only được truyền giữa các scope phụ thuộc propagation và loại transaction manager.

### 15.2. Đã catch exception nhưng transaction vẫn rollback-only

Một tình huống dễ gây hiểu lầm:

```java
@Service
public class OuterService {

    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        saveFirstRecord();

        try {
            inner.doWorkThatFails();
        } catch (RuntimeException ex) {
            // Chỉ ghi log, vẫn muốn outer commit.
            log.warn("Bước phụ lỗi nhưng tiếp tục", ex);
        }

        saveSecondRecord();
        // Khi outer commit có thể nhận UnexpectedRollbackException.
    }
}

@Service
public class InnerService {

    @Transactional  // Mặc định propagation REQUIRED.
    public void doWorkThatFails() {
        throw new IllegalStateException("Lỗi bước phụ");
    }
}
```

Mã chỉ minh họa các service; `saveFirstRecord`, `saveSecondRecord` và logger là những thành phần ứng dụng giả định.

Luồng:

```text
OuterService.outer() mở transaction T
           |
           +-- saveFirstRecord()
           |
           +-- InnerService.doWorkThatFails()
           |      dùng chung T (REQUIRED)
           |      RuntimeException thoát khỏi inner advice
           |      Spring đánh dấu T rollback-only
           |
           +-- outer catch exception
           |      nhưng cờ rollback-only vẫn còn
           |
           +-- saveSecondRecord()
           |
           +-- outer kết thúc, thử commit T
                  |
                  +-- T rollback
                  +-- có thể ném UnexpectedRollbackException
```

Spring dùng `UnexpectedRollbackException` để báo rằng tầng gọi tưởng transaction đã commit nhưng transaction thực chất phải rollback. Đây không phải một thông báo “database đã commit rồi”; nó cho biết kỳ vọng commit không được đáp ứng.

**Quan trọng:** ví dụ giả định `InnerService` được gọi qua Spring proxy/transaction advice, không phải self-invocation trong cùng bean. Nếu một method `@Transactional` tự gọi method khác qua `this.method()` trong cấu hình proxy điển hình, advice có thể không chạy như người viết tưởng.

### 15.3. Không dùng rollback-only để ép outer transaction commit được

Không có API chuẩn an toàn kiểu “clear rollback-only” để sửa transaction đã bị đánh dấu. Nếu một bước thực sự được phép thất bại mà không làm hỏng transaction chính, cần thiết kế **ranh giới transaction** phù hợp từ đầu:

- Nếu lỗi là trạng thái nghiệp vụ bình thường, có thể biểu diễn bằng kết quả không ném unchecked exception qua transactional boundary.
- Nếu bước phụ độc lập, cân nhắc `Propagation.REQUIRES_NEW` cho transaction riêng, hiểu rõ semantics và kết quả riêng của nó.
- Nếu cần savepoint, cân nhắc `Propagation.NESTED` chỉ khi transaction manager/tài nguyên thực sự hỗ trợ; JPA persistence context không tự trở thành nhiều transaction độc lập.
- Hoặc thực hiện bước phụ sau commit bằng outbox/event phù hợp.

Không tự ý đổi propagation chỉ để “chặn exception”, vì điều đó thay đổi tính nguyên tử của use case.

## 16. Quy tắc rollback khi exception được ném ra ngoài boundary

Tùy framework và annotation, **loại exception ảnh hưởng việc transaction có tự đánh dấu rollback không**.

### 16.1. Spring `@Transactional`

Trong cấu hình Spring phổ biến, mặc định:

- `RuntimeException` và `Error` → rollback.
- Checked exception (`Exception` không phải runtime) → không tự rollback, trừ khi cấu hình rule khác.

Ví dụ:

```java
@Transactional(rollbackFor = BusinessRuleException.class)
public void process() throws BusinessRuleException {
    // Nếu checked BusinessRuleException được ném ra,
    // Spring sẽ áp dụng rule rollback đã cấu hình.
}
```

Đây là annotation `org.springframework.transaction.annotation.Transactional`.

### 16.2. Jakarta Transactions `@Transactional`

Annotation **`jakarta.transaction.Transactional`** có thuộc tính `rollbackOn` và `dontRollbackOn` để khai báo rule exception:

```java
@Transactional(rollbackOn = BusinessRuleException.class)
public void process() throws BusinessRuleException {
    // ...
}
```

Cấu hình checked/unchecked exceptions phải theo đúng Jakarta Transactions `@Transactional`, không nhầm thuộc tính `rollbackFor` của Spring.

### 16.3. Business rule thất bại nhưng không ném exception

Nếu method trả về `false` hoặc một result object thay vì throw, transaction framework **không thể tự biết** business operation bị từ chối chỉ từ việc method return bình thường. Khi đã có pending database changes cần bỏ, code phải:

- Chủ động đánh dấu rollback-only theo API transaction manager, **hoặc**
- Ném exception phù hợp để boundary áp dụng rollback, **hoặc**
- Thiết kế sao cho điều kiện được kiểm tra trước khi có side effect rồi kết thúc transaction theo logic rõ ràng.

Chọn phương án dựa trên contract service và mong muốn của caller; không dựa vào kỳ vọng “trả `false` thì framework tự rollback”.

## 17. Rollback-only và propagation: `REQUIRED`, `REQUIRES_NEW`, `NESTED`

### 17.1. `REQUIRED`: thường tham gia transaction hiện có

Với Spring:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void serviceA() {
    serviceB.doSomething();
}
```

`serviceB` cũng dùng `REQUIRED` và được gọi qua advice phù hợp thì thường cùng tham gia transaction. Nếu B đánh dấu rollback-only, A không thể giả định vẫn commit transaction chung thành công.

### 17.2. `REQUIRES_NEW`: transaction độc lập

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentAudit() {
    // Transaction mới, độc lập với transaction đang bị suspend.
}
```

Điều này có thể thích hợp khi tác vụ audit cần commit độc lập. Nhưng nó thay đổi tính nguyên tử:

- Outer transaction rollback **không tự rollback** một transaction `REQUIRES_NEW` đã commit.
- Ghi dữ liệu thành công ở transaction mới không chứng minh outer transaction thành công.
- Nếu nhiều resources tham gia, cần đánh giá connection pool và lock contention.

Đừng đặt `REQUIRES_NEW` cho mọi repository method chỉ để tránh rollback-only; làm vậy dễ khiến use case không còn atomic.

### 17.3. `NESTED` và savepoint

`Propagation.NESTED` có thể dùng **savepoint** khi Spring transaction manager và tài nguyên hỗ trợ. Nhưng JPA chuẩn **không có API `EntityTransaction.beginNested()`**. Việc database rollback về savepoint cũng không tự làm cho mọi managed entity state trong JPA persistence context khớp lại.

Vì vậy phải xác nhận cụ thể mức hỗ trợ của transaction manager, JDBC driver, JPA provider và cách xử lý persistence context trước khi dùng nested transaction cho JPA entities.

## 18. Kiểm tra trạng thái giao dịch không thay thế kiểm soát đồng thời

Giả sử hai transaction đều đọc tồn kho:

```text
Database: availableQuantity = 10

T1 đọc 10
T2 đọc 10

T1 reserve 7
T2 reserve 7
```

Cả hai transaction có thể cùng đang **active, rollbackOnly=false** tại thời điểm gọi method. Điều đó **không có nghĩa cả hai cùng đủ tồn kho để commit**.

Cần cơ chế bảo vệ concurrent updates, chẳng hạn:

- `@Version` để kiểm tra optimistic locking.
- `PESSIMISTIC_WRITE` trong transaction ngắn khi cần.
- Atomic database update có điều kiện và kiểm tra row count khi use case phù hợp.
- Unique/foreign key/check constraints.
- Isolation phù hợp với invariant.

### 18.1. `@Version` và rollback-only

Một entity:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Khi transaction A commit thay đổi làm version tăng, transaction B vẫn giữ version cũ có thể gặp `OptimisticLockException` lúc flush/commit. Tùy hợp đồng JPA, exception có thể khiến transaction được đánh dấu rollback-only.

Ví dụ:

```text
T1: version 3 -> UPDATE -> version 4 -> COMMIT
T2: vẫn giữ version 3
    -> thử UPDATE
    -> conflict
    -> rollback transaction
```

**Rollback-only là tín hiệu cần hủy transaction, không phải cơ chế phát hiện lost update.** `@Version` và các cơ chế khóa chịu trách nhiệm phát hiện xung đột; rollback-only giúp điều phối hậu quả của tình huống không thể commit.

## 19. Transaction timeout, SQL error và trạng thái không đáng tin cậy

Khi transaction bị timeout hoặc database trả lỗi:

- Transaction manager có thể đánh dấu rollback-only hoặc bắt đầu rollback.
- Những câu SQL tiếp theo có thể lỗi.
- `isActive()` hoặc trạng thái JTA có thể thay đổi theo thời điểm hỏi.
- Một rollback có thể gặp lỗi nếu kết nối đã bị hỏng hoặc context không còn hợp lệ.

Đừng viết logic như:

```java
if (tx.isActive() && !tx.getRollbackOnly()) {
    // Kết luận chắc chắn commit sẽ thành công.
    tx.commit();
}
```

Câu điều kiện chỉ nói rằng **ngay lúc hỏi** transaction đang active và chưa có cờ rollback-only. Nó không phải bảo đảm commit thành công.

Nếu commit hoặc rollback trả lỗi trong tình huống kết nối bất ổn, cần ghi nhận rằng **kết quả transaction có thể chưa xác định hoàn toàn ở tầng ứng dụng** cho tới khi đối soát với database/hệ thống. Đặc biệt với giao dịch bên ngoài như thanh toán, không gửi lại operation không idempotent chỉ vì kết nối trả timeout.

## 20. Logging và quan sát trạng thái transaction

Khi debug một use case, nên log:

- ID request hoặc correlation ID.
- Mã use case/nghiệp vụ.
- Điểm bắt đầu và kết thúc transaction.
- Cờ rollback-only **khi transaction còn active**.
- Exception gốc và exception từ commit/rollback.
- Kết quả nghiệp vụ: đã commit, rollback do rule, rollback do lỗi, hoặc chưa xác định.

Không nên log password, token hay toàn bộ thông tin nhạy cảm của entity.

Ví dụ utility cho resource-local:

```java
private static String transactionSnapshot(EntityTransaction tx) {
    if (!tx.isActive()) {
        return "inactive";
    }

    return tx.getRollbackOnly()
            ? "active/rollback-only"
            : "active/not-marked";
}
```

Dùng:

```java
log.debug("Before commit, tx={}", transactionSnapshot(tx));
```

Nếu không thể lấy trạng thái do transaction manager/provider đã lỗi, ghi nhận exception kiểm tra thay vì tiếp tục thao tác mạnh để “cố kiểm tra cho ra”.

### 20.1. Trạng thái transaction và business status khác nhau

Một đơn hàng có:

```java
order.getStatus() == OrderStatus.PAID
```

nhưng transaction đang `rollback-only`. Khi đó trạng thái `PAID` trong object Java **chưa chắc đã được commit xuống database**.

Ngược lại, transaction có thể commit thành công trong khi đơn hàng vẫn `PENDING` theo nghiệp vụ. Không dùng transaction status để kết luận doanh nghiệp đã thanh toán/thành công khi chưa kiểm tra trạng thái domain và tính bền vững cần thiết.

## 21. Rollback không hoàn tác side effect bên ngoài database

Một transaction database có thể rollback các SQL changes trong phạm vi tài nguyên được quản lý, nhưng **không tự hủy** email đã gửi, HTTP request đã gọi, thông báo Kafka đã phát hoặc file đã ghi ngoài transaction.

Anti-pattern:

```java
tx.begin();

order.markPaid();
emailClient.sendReceipt(order); // Side effect ra ngoài DB.

tx.setRollbackOnly();
tx.rollback();
```

Sau rollback, email đã gửi vẫn có thể tồn tại, dù database không ghi nhận đơn đã thanh toán.

Thiết kế thực tế nên dùng cơ chế đồng bộ side effects đáng tin cậy, ví dụ:

- Transactional outbox: lưu event trong cùng DB transaction, worker phát sau commit.
- Idempotency key khi gọi API ngoài.
- Chia hành động có thể bù trừ (*compensation*) cho workflow phân tán.
- Gửi email/thông báo từ hệ thống sau khi biết DB commit thành công, với xử lý retry phù hợp.

Không nên suy ra từ `tx.getRollbackOnly() == false` rằng gửi thông báo ngay sẽ luôn đúng; commit có thể thất bại sau bước kiểm tra.

## 22. Batch update JPQL và cờ rollback-only

JPQL bulk update/delete thường thao tác trực tiếp lên database, không đồng bộ lại mọi managed entity đang nằm trong persistence context.

Ví dụ:

```java
tx.begin();

int rows = em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.availableQuantity = 0
    WHERE i.availableQuantity < 0
    """
).executeUpdate();

if (rows > unexpectedLimit) {
    tx.setRollbackOnly();
}

if (tx.getRollbackOnly()) {
    tx.rollback();
} else {
    tx.commit();
}
```

Trong ví dụ này, `unexpectedLimit` là một ngưỡng nghiệp vụ do application cung cấp. Nếu số hàng bị tác động quá mức dự kiến, rollback giúp hủy toàn bộ bulk update trong transaction.

Điểm cần chú ý:

1. Bulk update có thể bỏ qua lifecycle callback/dirty checking thông thường.
2. Managed entities có thể giữ state cũ sau bulk statement.
3. Nếu cuối cùng **commit**, cần quản lý context, chẳng hạn dùng context riêng hoặc `clear()` sau khi xử lý pending changes.
4. Nếu rollback, không tiếp tục dùng state managed như snapshot DB mới.
5. `@Version` của từng managed entity không tự được xử lý giống update entity thông thường trong JPQL bulk update; cần concurrency policy riêng.

`setRollbackOnly()` giải quyết việc **commit hay không**, chứ không giải quyết mọi vấn đề đồng bộ persistence context sau bulk operation.

## 23. Integration test: kiểm tra rollback-only thật sự ngăn commit

Một bài thực hành hữu ích là tạo một entity đơn giản:

```java
@Entity
@Table(name = "audit_records")
public class AuditRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String message;

    protected AuditRecord() {}

    public AuditRecord(String message) {
        this.message = message;
    }
}
```

Giả sử `emf` là `EntityManagerFactory` cho persistence unit `RESOURCE_LOCAL` có entity này.

### 23.1. Test đánh dấu và rollback rõ ràng

```java
@Test
void rollbackOnlyPreventsPersistedRow() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    Long newId = null;

    try {
        assertFalse(tx.isActive());

        tx.begin();
        assertTrue(tx.isActive());
        assertFalse(tx.getRollbackOnly());

        AuditRecord record = new AuditRecord("should rollback");
        em.persist(record);
        em.flush();
        newId = record.getId();

        tx.setRollbackOnly();
        assertTrue(tx.isActive());
        assertTrue(tx.getRollbackOnly());

        tx.rollback();
        assertFalse(tx.isActive());
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    // Dùng context mới để tránh managed state còn trong bộ nhớ.
    EntityManager verification = emf.createEntityManager();
    try {
        assertNull(verification.find(AuditRecord.class, newId));
    } finally {
        verification.close();
    }
}
```

Các import gồm `jakarta.persistence.*` và JUnit 5 (`@Test` cùng `assertTrue`, `assertFalse`, `assertNull`). Entity `AuditRecord` cần đặt trong package/file Java hợp lệ và đăng ký với persistence unit.

Điều được kiểm tra:

- Trước `begin()`, transaction không active.
- Sau `begin()`, transaction active.
- Sau `setRollbackOnly()`, transaction vẫn có thể active nhưng đã có cờ.
- `rollback()` kết thúc transaction.
- Row đã được `flush()` nhưng rollback không tồn tại trong database sau transaction.

Với khóa sinh bằng IDENTITY/sequence, số ID đã cấp có thể bị bỏ qua sau rollback; không nên giả định database sẽ tái sử dụng ID đó.

### 23.2. Test gọi `getRollbackOnly()` khi chưa begin

```java
@Test
void getRollbackOnlyRequiresActiveTransaction() {
    EntityManager em = emf.createEntityManager();

    try {
        EntityTransaction tx = em.getTransaction();

        assertFalse(tx.isActive());

        assertThrows(
            IllegalStateException.class,
            tx::getRollbackOnly
        );
    } finally {
        em.close();
    }
}
```

Test minh họa API contract resource-local: không được gọi `getRollbackOnly()` như một cách “khởi tạo trạng thái cờ” trước transaction.

### 23.3. Test commit trên transaction rollback-only

```java
@Test
void commitDoesNotSucceedWhenMarkedRollbackOnly() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();
        em.persist(new AuditRecord("not committed"));

        tx.setRollbackOnly();

        assertThrows(
            RollbackException.class,
            tx::commit
        );
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }
}
```

Ví dụ bám theo contract JPA về `RollbackException` khi transaction được rollback trong lúc commit. Một framework có thể bọc lỗi ở tầng khác; nếu viết integration test qua Spring/JTA, cần assert đúng exception của **transaction boundary thực tế**, không áp đặt exception resource-local cho mọi môi trường.

### 23.4. Các test bổ sung nên thực hiện

- Lỗi domain exception trước commit → toàn bộ thay đổi phải rollback.
- Optimistic locking conflict của hai transaction → không có lost update.
- Spring outer service catch exception từ inner REQUIRED → xác nhận rollback toàn bộ và `UnexpectedRollbackException` theo cấu hình thực tế.
- BMT/JTA `getStatus()` trước/sau `setRollbackOnly()` → trạng thái phù hợp.
- Timeout/fault injection → xác minh cleanup và outcome logging.
- HTTP command lặp → kiểm tra idempotency thay vì giả định rollback sẽ đảo side effect ngoài DB.

Các test này cần database/transaction manager tương ứng với môi trường deployment vì đặc tính rollback, isolation và exception wrapping có thể khác H2/in-memory demo.

## 24. Những lỗi thường gặp

| Triệu chứng hoặc anti-pattern | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getRollbackOnly()` ném `IllegalStateException` trước `begin()` | Không có resource-local transaction active. | Kiểm tra `isActive()` trước. |
| `isActive() == true` nhưng commit vẫn rollback | Transaction đã có cờ rollback-only hoặc lỗi khi commit. | Kiểm tra cờ, exception và transaction outcome. |
| Gọi `setRollbackOnly()` rồi tiếp tục ghi và gọi `commit()` | Nhầm “đánh dấu” với một transaction có thể phục hồi. | Dừng xử lý, rollback rõ ràng, trả kết quả lỗi. |
| Gọi `getRollbackOnly()` sau commit | Transaction đã kết thúc. | Đọc trạng thái trong transaction; ghi log outcome riêng. |
| Dùng `EntityTransaction` với JTA EntityManager | Nhầm loại transaction. | Dùng JTA/container transaction APIs. |
| Dùng `UserTransaction.getRollbackOnly()` | `UserTransaction` không có method này. | Dùng `getStatus()`/`Status` hoặc `TransactionSynchronizationRegistry`. |
| Dùng `SessionContext.setRollbackOnly()` trong BMT như CMT | Nhầm quyền điều phối EJB. | Dùng `UserTransaction` cho BMT. |
| Spring outer catch exception rồi vẫn gặp `UnexpectedRollbackException` | Inner REQUIRED đã đánh dấu transaction chung rollback-only. | Thiết kế ranh giới exception/propagation; không “xóa cờ”. |
| Method `@Transactional` tự gọi qua `this` mà không có transaction như dự kiến | Self-invocation bỏ qua proxy advice trong cấu hình Spring thông dụng. | Tổ chức gọi qua bean được proxy hoặc dùng cơ chế transaction phù hợp. |
| Checked exception trong Spring nhưng transaction vẫn commit | Quy tắc rollback mặc định thường áp dụng unchecked exception. | Cấu hình `rollbackFor` hoặc quản lý transaction theo contract. |
| Jakarta Transactions dùng thuộc tính `rollbackFor` | Nhầm Spring với Jakarta `@Transactional`. | Dùng `rollbackOn`/`dontRollbackOn` theo API Jakarta. |
| Return `false` mà transaction vẫn commit | Framework không tự hiểu kết quả business là lỗi. | Mark rollback-only hoặc ném exception phù hợp. |
| `flush()` thành công rồi transaction rollback | Flush không phải commit. | Chỉ xác nhận thành công sau commit; kiểm tra outcome. |
| Rollback rồi entity Java vẫn hiển thị giá trị đã sửa | Rollback không tự khôi phục object state trong bộ nhớ. | Kết thúc context lỗi và tải lại state khi cần. |
| Đã đánh dấu rollback-only mà muốn “clear flag” | API không hỗ trợ phục hồi transaction đã bị đánh dấu. | Rollback và tạo transaction mới khi phù hợp. |
| `getRollbackOnly()==false` nhưng vẫn có duplicate key | Cờ không dự đoán mọi lỗi DB tương lai. | Giữ PK/UNIQUE/FK, bắt lỗi commit/flush. |
| Cập nhật hai row cạnh tranh vẫn mất dữ liệu | Rollback-only không tự phát hiện lost update. | `@Version`, locks và transaction isolation đúng invariant. |
| Rollback nhưng email đã gửi | Side effect ngoài DB không tự bị rollback. | Outbox, idempotency, workflow bù trừ. |
| Dùng `REQUIRES_NEW` khắp nơi để tránh rollback chung | Phá tính atomic của use case. | Chỉ tách transaction khi nghiệp vụ cho phép kết quả độc lập. |
| Dùng `NESTED` mặc định với JPA entity | Savepoint và state của persistence context không đồng bộ tự động. | Xác minh hỗ trợ cụ thể hoặc thiết kế transaction boundary khác. |
| Dùng `em.clear()` khi đang có pending changes | Clear detach state và có thể bỏ thay đổi chưa flush. | Chọn flush/clear có chủ đích, tốt nhất dùng context riêng. |
| Giữ EntityManager từ transaction lỗi sang request mới | Context có thể chứa stale/inconsistent state. | Đóng và tạo context/transaction mới. |

## 25. Quy trình chẩn đoán khi transaction bất ngờ rollback

Giả sử service ghi log:

```text
Business logic đã chạy xong,
nhưng database không thấy dữ liệu.
```

Hãy kiểm tra theo thứ tự:

**Bước 1 — Xác định transaction manager.** Đây là resource-local `EntityTransaction`, JTA/container hay Spring `PlatformTransactionManager`? Không thể dùng một API thống nhất tùy tiện cho cả ba.

**Bước 2 — Xác định transaction boundary.** Transaction bắt đầu ở đâu, commit được gọi ở đâu, một interceptor có tự động bao quanh method không?

**Bước 3 — Kiểm tra rollback-only trước khi kết thúc nếu có thể.** Với resource-local dùng `isActive()` rồi `getRollbackOnly()`; với JTA dùng `getStatus()` hoặc registry; với Spring quan sát `TransactionStatus` tại nơi thích hợp.

**Bước 4 — Tìm exception đầu tiên.** Một lỗi inner service có thể đã được catch rồi chỉ log; chính lỗi đó có thể đã đánh dấu transaction rollback-only.

**Bước 5 — Kiểm tra propagation.** Inner service dùng REQUIRED, REQUIRES_NEW hay NESTED? Nó có thật sự được gọi qua transactional advice không?

**Bước 6 — Kiểm tra lỗi ở flush/commit.** SQL constraint, deadlock, version conflict, timeout có thể chỉ xuất hiện khi flush/commit, không xuất hiện ở setter/domain method.

**Bước 7 — Kiểm tra dữ liệu sau rollback trong context mới.** Đừng dùng object managed/detached từ transaction lỗi để kết luận database đã thay đổi.

**Bước 8 — Kiểm tra side effects.** Nếu có email, message hoặc external payment call xảy ra trước rollback, cần đối soát chúng theo cơ chế riêng.

**Bước 9 — Thiết kế sửa lỗi theo semantics nghiệp vụ.** Nếu bước phụ được phép thất bại độc lập thì xác định transaction riêng hoặc outbox; nếu mọi bước phải atomic thì propagate exception và rollback toàn bộ.

### 25.1. Cây quyết định nhanh cho resource-local

```text
Có transaction active không? -- Không --> Không gọi getRollbackOnly()
          |
          Có
          |
          v
getRollbackOnly() == true? -- Có --> rollback(), báo lỗi/return rejected
          |
          Không
          |
          v
Có exception hoặc invariant bị vi phạm? -- Có --> rollback()
          |
          Không
          |
          v
Yêu cầu commit()
          |
          +-- Thành công --> báo success
          |
          +-- Thất bại --> xử lý lỗi, cleanup,
                            không coi dữ liệu đã commit
```

Dù có thể kiểm tra cờ, hãy thiết kế luồng **exception-safe** và để `commit()` quyết định outcome cuối cùng của transaction database.

## 26. Thiết kế API nghiệp vụ khi transaction phải rollback

Không nên để transaction status là thứ duy nhất giải thích kết quả cho caller.

Ví dụ nếu việc dự trữ tồn kho bị từ chối vì chính sách:

```java
public record ReservationResult(
    boolean accepted,
    String reason
) {}
```

Application service có thể trả:

```java
return new ReservationResult(
    false,
    "Vượt quá giới hạn số lượng mỗi lần yêu cầu"
);
```

nhưng phải bảo đảm transaction đã rollback hoặc chưa thực hiện bất kỳ thay đổi cần rollback nào. **Result object diễn đạt quyết định nghiệp vụ; rollback-only diễn đạt yêu cầu kết thúc transaction.**

Trong ứng dụng HTTP, không nên trả `200 OK` với dữ liệu “thành công” chỉ vì không có exception ở domain method trong khi transaction manager sẽ rollback ở cuối request.

Với Spring, một transaction có thể rollback tại **interceptor sau khi method return**. Caller phải nhận được semantics đúng qua exception hoặc result được thiết kế cùng transaction boundary, không quyết định outcome từ một biến `success=true` đặt trước commit.

### 26.1. Không tự động retry vô điều kiện

Rollback có thể do:

- **Business rejection**: retry cùng input thường không giúp gì.
- **Optimistic locking conflict**: có thể tải lại và yêu cầu người dùng quyết định.
- **Deadlock/timeout tạm thời**: có thể retry có giới hạn nếu operation idempotent.
- **Lỗi schema/configuration**: retry vô hạn sẽ gây tải và che lỗi.

Đừng coi mọi rollback-only là lỗi tạm thời. Muốn retry, cần phân loại nguyên nhân, tạo **transaction mới** và bảo đảm external side effects không bị nhân đôi.

## 27. Câu hỏi tự kiểm tra

**1. `isActive()` và `getRollbackOnly()` khác nhau thế nào?**

`isActive()` cho biết transaction resource-local còn đang hoạt động; `getRollbackOnly()` cho biết transaction active đã bị đánh dấu bắt buộc rollback chưa.

**2. `isActive() == true` có bảo đảm commit thành công không?**

Không. Transaction có thể rollback-only hoặc gặp lỗi ở flush/commit.

**3. Khi chưa gọi `begin()`, có nên gọi `getRollbackOnly()` không?**

Không. `EntityTransaction.getRollbackOnly()` yêu cầu transaction active; nên kiểm tra `isActive()` trước.

**4. `setRollbackOnly()` có làm dữ liệu bị rollback ngay không?**

Không. Nó đánh dấu transaction không được commit; `rollback()` hoặc cơ chế kết thúc của transaction manager mới thực hiện rollback.

**5. Có thể “unset rollback-only” để commit lại transaction không?**

Không có API tiêu chuẩn để xóa cờ sau khi đã đánh dấu. Cần rollback rồi bắt đầu transaction mới nếu nghiệp vụ cho phép.

**6. Nếu `commit()` được gọi trên transaction rollback-only, chuyện gì xảy ra?**

Nó không thể commit thành công; resource-local JPA có thể rollback và ném `RollbackException`.

**7. `flush()` thành công có nghĩa transaction đã commit chưa?**

Chưa. Flush gửi SQL đang chờ theo context; commit vẫn có thể thất bại, rollback vẫn có thể hủy SQL chưa commit.

**8. Trong JTA, `UserTransaction` có `getRollbackOnly()` không?**

Không. Dùng `getStatus()` với hằng `Status`, hoặc `TransactionSynchronizationRegistry` khi phù hợp.

**9. `STATUS_MARKED_ROLLBACK` trong JTA có nghĩa gì?**

Transaction đã được đánh dấu phải rollback, nhưng không có nghĩa rollback đã hoàn tất ngay.

**10. Trong Spring, tại sao outer service catch exception rồi vẫn gặp `UnexpectedRollbackException`?**

Vì inner transactional method tham gia cùng transaction có thể đã đánh dấu rollback-only; việc catch không xóa cờ, outer commit thất bại.

**11. Checked exception có luôn khiến Spring `@Transactional` rollback không?**

Không theo cấu hình mặc định thông dụng; cần khai báo rule như `rollbackFor` khi yêu cầu nghiệp vụ.

**12. `@Version` và rollback-only có cùng nhiệm vụ không?**

Không. `@Version` hỗ trợ phát hiện cập nhật đồng thời; rollback-only cho biết transaction không được commit.

**13. Rollback transaction có hủy email đã gửi không?**

Không. Email là side effect ngoài DB transaction. Cần cơ chế outbox/idempotency/compensation.

**14. `EntityTransaction` có dùng để điều phối transaction của JTA EntityManager không?**

Không. Dùng API transaction manager/JTA/container phù hợp; `getTransaction()` trên JTA EM không hợp lệ.

**15. Sau rollback có nên đọc lại dữ liệu bằng chính managed entity cũ không?**

Không nên dựa vào state cũ. Mở context mới và tải lại khi cần, vì rollback không tự đảo mọi thay đổi trên object Java.

**16. Khi bước con được phép thất bại độc lập, có nên luôn dùng `REQUIRES_NEW` không?**

Không. Chỉ dùng khi nghiệp vụ cho phép commit độc lập; nếu không, nó có thể phá tính nguyên tử của use case.

**17. Tại sao không dùng cờ rollback-only làm kết quả trả cho UI?**

Vì cờ là trạng thái kỹ thuật của transaction; UI cần kết quả nghiệp vụ, và commit còn có thể thất bại ở thời điểm sau đó.

## 28. Ghi nhớ trọng tâm

Trong giao dịch JPA, **kiểm tra trạng thái transaction** và **cờ rollback-only** giúp ứng dụng tránh một giả định nguy hiểm: “đang chạy trong transaction thì chắc chắn sẽ commit”.

Với **resource-local transaction**, mẫu quan trọng nhất là:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();

try {
    // Thao tác nghiệp vụ...

    if (mustAbort) {
        tx.setRollbackOnly();
    }

    if (tx.getRollbackOnly()) {
        tx.rollback();
    } else {
        tx.commit();
    }
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Mẫu này giả định `mustAbort` đã được xác định từ nghiệp vụ và không cố thay thế phần cleanup của application production.

Với **JTA**, sử dụng đúng `UserTransaction.getStatus()`, `TransactionSynchronizationRegistry` hoặc `SessionContext` theo kiểu quản lý giao dịch. Với **Spring**, sử dụng `TransactionStatus` và hiểu `@Transactional`, propagation cùng nguyên nhân của `UnexpectedRollbackException`.

Bốn quy tắc cần thuộc:

1. **`isActive()` chỉ nói transaction còn hoạt động**, không chứng minh nó có thể commit.
2. **`setRollbackOnly()` chỉ đánh dấu phải rollback**, không tự hoàn tác dữ liệu ngay.
3. **`getRollbackOnly()` được hỏi khi transaction đang active**; không gọi sau khi transaction kết thúc.
4. **Kết quả commit/rollback do transaction manager quyết định**, còn invariant nghiệp vụ, concurrency, cache và side effects cần được xử lý ở tầng tương ứng.

Khi phân biệt rõ **trạng thái giao dịch**, **trạng thái entity** và **trạng thái nghiệp vụ**, code JPA sẽ dễ chẩn đoán lỗi hơn, tránh commit ngoài ý muốn và bảo đảm các nhánh thất bại được xử lý an toàn.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `EntityTransaction`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitytransaction)
- [Jakarta Transactions — đặc tả chính thức](https://jakarta.ee/specifications/transactions/)
- [Jakarta Transactions API — `UserTransaction`](https://jakarta.ee/specifications/transactions/2.0/apidocs/jakarta.transaction/jakarta/transaction/usertransaction)
- [Jakarta Transactions API — `TransactionSynchronizationRegistry`](https://jakarta.ee/specifications/transactions/2.0/apidocs/jakarta.transaction/jakarta/transaction/transactionsynchronizationregistry)
- [Spring — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
