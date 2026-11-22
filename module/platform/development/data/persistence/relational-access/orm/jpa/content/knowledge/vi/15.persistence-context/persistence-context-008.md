# Đọc lại dữ liệu bằng refresh và ảnh hưởng đến thay đổi chưa đồng bộ trong JPA

Trong **Jakarta Persistence (JPA)**, một entity đã được tải vào `Persistence Context` không chỉ là một Java object bình thường. Nó thường là **managed entity**: JPA provider theo dõi trạng thái của object đó và có thể tự đồng bộ những thay đổi với cơ sở dữ liệu khi flush hoặc commit transaction.

Điều này mang lại một hành vi hữu ích nhưng cũng dễ gây nhầm lẫn: khi application gọi `entityManager.find()` lần thứ hai với cùng entity và cùng persistence context, provider có thể trả ngay object đang được quản lý mà **không đọc lại những cột mới nhất từ database**. Nếu thật sự muốn yêu cầu database cung cấp lại trạng thái cho entity managed, JPA cung cấp phương thức **`EntityManager.refresh(entity)`**.

Điểm đặc biệt quan trọng là: **`refresh()` có thể ghi đè những thay đổi trong bộ nhớ chưa được đồng bộ bằng `flush()`**. Nếu code vừa sửa một field rồi gọi `refresh()` mà chưa flush, giá trị sửa có thể biến mất vì provider lấy lại trạng thái từ database. Ngược lại, nếu đã flush thay đổi vào database trong cùng transaction, refresh thường đọc lại chính dữ liệu vừa ghi đó; **flush không đồng nghĩa commit**, nên transaction vẫn có thể rollback.

Bài học này làm rõ:

- **Persistence Context** và cơ chế theo dõi entity managed.
- Cách `refresh()` khác `find()`, `flush()`, `clear()`, `detach()`, `merge()` và rollback.
- Vì sao refresh có thể làm mất sửa đổi chưa flush, bao gồm cả trạng thái collection và quan hệ liên quan.
- Vai trò của **transaction isolation**, dữ liệu do transaction khác cập nhật, `@Version` và cascade `REFRESH`.
- Cách sử dụng refresh có chủ đích để đồng bộ lại dữ liệu sau thao tác SQL ngoài JPA, hoặc khi database tự sinh/chỉnh giá trị.

Các ví dụ dùng `jakarta.persistence.*` (Jakarta Persistence). Với một ứng dụng JPA cũ dùng namespace `javax.persistence.*`, tên import và một số chi tiết tích hợp có thể khác, nhưng ý nghĩa cơ bản của persistence context và refresh tương tự.

## 1. Persistence Context giữ trạng thái nào?

**Persistence Context** là môi trường quản lý một tập entity instance. Một `EntityManager` hoạt động gắn với persistence context; trong một persistence context, cùng một danh tính entity được biểu diễn bởi cùng một managed instance theo mô hình identity map.

Giả sử có bảng `inventory_items`:

| id | sku | quantity | unit_price | version |
| ---: | --- | ---: | ---: | ---: |
| 10 | KEYBOARD-01 | 10 | 450000.00 | 0 |

Tại thời điểm đầu, database lưu `quantity = 10`.

Ứng dụng tải entity:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);
```

Bây giờ trong persistence context có một instance `item` với `quantity = 10`.

Sau đó sửa:

```java
item.changeQuantity(15);
```

Ta có thể hình dung **hai trạng thái tạm thời khác nhau**:

```text
                  Persistence Context
                 +--------------------+
                 | InventoryItem#10   |
                 | quantity = 15      |  <-- đã thay đổi trong Java
                 | version = 0        |
                 +--------------------+
                           |
                           | chưa flush
                           v
                     Database row
                 +--------------------+
                 | inventory_items    |
                 | id = 10            |
                 | quantity = 10      |  <-- dữ liệu cũ
                 | version = 0        |
                 +--------------------+
```

Giá trị 15 có thể đang là **thay đổi chưa đồng bộ** (*unflushed change*). JPA sẽ phát hiện thay đổi bằng dirty checking và tạo SQL thích hợp khi flush/commit, miễn là transaction hợp lệ và không có thao tác nào khác ghi đè trạng thái.

### 1.1. Managed entity là gì?

Một entity thường có các trạng thái vòng đời:

| Trạng thái | Ý nghĩa | Khi gọi `refresh()` |
| --- | --- | --- |
| **New/transient** | Object vừa tạo bằng `new`, chưa managed. | Không phải đối tượng hợp lệ để refresh theo hợp đồng thông thường. |
| **Managed** | Entity đang nằm trong persistence context và được theo dõi. | Có thể refresh để lấy lại trạng thái từ database. |
| **Detached** | Entity từng được quản lý nhưng đã tách khỏi context, ví dụ sau `close()` hoặc `detach()`. | Không thể refresh trực tiếp như một managed entity thông thường. |
| **Removed** | Entity managed đã được yêu cầu xóa. | Không phải trạng thái thích hợp để refresh lại như một entity đang tồn tại. |

Cách dùng chuẩn của `refresh()` là **trên entity đang managed**, có hàng cơ sở dữ liệu tương ứng. Nếu gọi với new/detached/removed, provider có thể ném `IllegalArgumentException` hoặc một ngoại lệ theo hợp đồng JPA/phương thức. Nếu hàng tương ứng không còn tồn tại, thao tác làm mới cũng có thể thất bại.

### 1.2. Tại sao find() không mặc nhiên đọc lại?

JPA duy trì identity map trong persistence context:

```java
InventoryItem first =
    entityManager.find(InventoryItem.class, 10L);

InventoryItem second =
    entityManager.find(InventoryItem.class, 10L);

System.out.println(first == second); // true trong cùng context
```

Nếu entity đã được quản lý, JPA có thể dùng instance hiện có. Điều đó giữ tính nhất quán tham chiếu Java và giảm truy vấn không cần thiết.

Nhưng cũng đồng nghĩa:

- Lần `find()` thứ hai **không phải lời hứa** rằng database được truy vấn lại.
- Nếu một transaction khác đã sửa hàng trong database, managed entity của ta **không tự cập nhật tức thời**.
- Nếu chính ta đã thay đổi managed entity nhưng chưa flush, `find()` tiếp theo thường vẫn thấy giá trị đang có trong bộ nhớ, không phải giá trị cũ của database.

Vì vậy, “gọi find lại cho mới” và “refresh managed entity” là **hai hành động khác nhau**.

## 2. Entity và schema dùng trong bài

Chúng ta dùng ví dụ kho hàng: một sản phẩm có số lượng tồn, đơn giá và một trường version phục vụ optimistic locking.

### 2.1. Entity InventoryItem

```java
package com.example.inventory;

import java.math.BigDecimal;
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

    @Column(name = "sku", nullable = false, unique = true, length = 60)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal unitPrice;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected InventoryItem() {
        // Constructor cho JPA.
    }

    public InventoryItem(
            String sku,
            Integer quantity,
            BigDecimal unitPrice) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public Long getVersion() {
        return version;
    }

    public void changeQuantity(Integer newQuantity) {
        if (newQuantity == null || newQuantity < 0) {
            throw new IllegalArgumentException(
                "Quantity must be non-negative"
            );
        }
        this.quantity = newQuantity;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must be non-negative"
            );
        }
        this.unitPrice = newPrice;
    }
}
```

`@Version` giúp provider phát hiện xung đột optimistic locking theo quy tắc JPA. Nó **không phải điều kiện bắt buộc để dùng refresh**, nhưng giúp phân tích những tình huống dữ liệu đã thay đổi ở một transaction khác.

### 2.2. Bảng PostgreSQL minh họa

```sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price NUMERIC(15, 2) NOT NULL CHECK (unit_price >= 0),
    version BIGINT NOT NULL
);
```

Ta giả sử có hàng:

```text
id         = 10
sku        = KEYBOARD-01
quantity   = 10
unit_price = 450000.00
version    = 0
```

Schema và hàng trên dùng để **minh họa logic**. SQL provider phát ra thực tế có thể khác về thứ tự cột, bind parameter, câu lệnh lấy ID hoặc câu lệnh kiểm soát version.

## 3. EntityManager.refresh() thực hiện điều gì?

Cách gọi cơ bản:

```java
entityManager.refresh(item);
```

Ý nghĩa là yêu cầu provider **đọc lại trạng thái persistent của `item` từ database** và áp dụng trạng thái được đọc vào managed instance hiện có.

Về mô hình:

```text
Trước refresh:

Managed InventoryItem#10     Database inventory_items#10
    quantity = 15                 quantity = 10
    unitPrice = 450000            unit_price = 450000
    version = 0                   version = 0

                  refresh(item)
                        |
                        v

Sau refresh:

Managed InventoryItem#10     Database inventory_items#10
    quantity = 10  <----------    quantity = 10
    unitPrice = 450000            unit_price = 450000
    version = 0                   version = 0
```

Nếu số lượng 15 chỉ mới tồn tại trong bộ nhớ, nó **bị thay thế bằng 10**. JPA không nhất thiết phát câu `UPDATE quantity=15` trước khi refresh; điểm cốt lõi là thao tác refresh **không có mục đích bảo toàn dirty state chưa flush**.

### 3.1. refresh() làm mới cùng một object

`refresh()` khác `merge()` ở chỗ nó **không trả về một entity instance**:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

entityManager.refresh(item);

// Vẫn sử dụng chính tham chiếu "item".
System.out.println(item.getQuantity());
```

Phương thức `refresh()` trả về `void`. Managed instance hiện có được cập nhật theo database; không cần gán lại `item = ...`.

Điều này cũng có nghĩa nếu các phần code khác trong cùng persistence context giữ tham chiếu đến managed instance ấy, chúng có thể quan sát **giá trị mới sau refresh** khi truy cập field/getter.

### 3.2. refresh() không phải SELECT thuần túy

Một câu SQL `SELECT` trả về dữ liệu để ứng dụng đọc. Còn `refresh(item)` **thay đổi trạng thái của chính managed object**. Nếu trước đó code đã sửa `item`, phương thức có thể xóa công sức sửa đổi của code.

Vì vậy, dù refresh liên quan đến việc **đọc** database, tác động tới state Java có thể đáng kể không kém một thao tác ghi.

### 3.3. Cú pháp các overload của refresh

JPA có những overload cho phép chỉ định lock mode hoặc hint:

```java
entityManager.refresh(item);

entityManager.refresh(
    item,
    jakarta.persistence.LockModeType.PESSIMISTIC_READ
);

entityManager.refresh(
    item,
    java.util.Map.of(
        "jakarta.persistence.lock.timeout", 3000
    )
);

entityManager.refresh(
    item,
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE,
    java.util.Map.of(
        "jakarta.persistence.lock.timeout", 3000
    )
);
```

Hai bản có lock mode cần một transaction phù hợp và database/provider hỗ trợ cơ chế khóa được yêu cầu. Hint không được mọi provider xử lý giống nhau; timeout cũng có thể không thực thi chính xác trên mọi DBMS/driver.

**Mặc định nên hiểu `refresh(item)` trước**. Chỉ thêm locking khi nghiệp vụ thực sự cần kiểm soát tranh chấp và đã hiểu mức isolation/lock của database.

## 4. Trường hợp cốt lõi: refresh ghi đè thay đổi chưa flush

Xét đoạn mã trong một transaction:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

System.out.println(item.getQuantity()); // 10

item.changeQuantity(15);
System.out.println(item.getQuantity()); // 15

entityManager.refresh(item);

System.out.println(item.getQuantity()); // 10
```

Ta giả định:

- Database ban đầu có `quantity = 10`.
- Không có transaction khác thay đổi dữ liệu.
- Ứng dụng **chưa gọi flush** và chưa có cơ chế nào đồng bộ thay đổi `quantity = 15` trước refresh.

Khi đó, refresh đọc lại giá trị 10 từ database và ghi đè giá trị 15 đang nằm trong managed entity.

### 4.1. Bảng thời gian

| Bước | Trạng thái Java của item | Trạng thái database |
| --- | --- | --- |
| `find(item, 10)` | `quantity = 10` | `quantity = 10` |
| `changeQuantity(15)` | `quantity = 15` | `quantity = 10` |
| Chưa gọi `flush()` | `quantity = 15`, đang dirty | `quantity = 10` |
| `refresh(item)` | `quantity = 10` | `quantity = 10` |
| `commit()` sau refresh, không sửa thêm | Không còn thay đổi 15 để ghi | Thường tiếp tục là 10 |

Đây là một tình huống **mất thay đổi chưa lưu** (*discarding unflushed changes*), không phải lỗi JPA. Đó chính là ý nghĩa của việc yêu cầu đọc lại database và thay state hiện tại.

### 4.2. Không chỉ một field

Giả sử code sửa cả số lượng và đơn giá:

```java
item.changeQuantity(15);
item.changePrice(new java.math.BigDecimal("420000.00"));

entityManager.refresh(item);
```

Nếu chưa có flush, refresh không chỉ lấy lại `quantity` mà còn có thể đưa `unitPrice` về giá trị đã lưu trong database. Không nên kỳ vọng refresh chỉ tác động đến field mà một màn hình đang quan tâm.

**`refresh()` không có tham số chọn một field riêng lẻ**. Nó làm mới **trạng thái persistent của entity** theo mapping và quy tắc provider. Nếu chỉ muốn đọc một giá trị hiện tại mà không ghi đè entity managed, cân nhắc một truy vấn scalar/projection phù hợp hoặc một persistence context độc lập.

### 4.3. Vì sao có thể gây lỗi nghiệp vụ?

Giả sử service kiểm tra tồn kho:

```java
item.changeQuantity(item.getQuantity() - 1);

// Một phương thức tiện ích được gọi ở đây:
entityManager.refresh(item);

// Kết quả: thay đổi trừ một có thể biến mất.
```

Nếu service nghĩ refresh chỉ “xác nhận dữ liệu vừa cập nhật”, nó có thể trả về kết quả thành công nhưng database vẫn không giảm số lượng. Với ứng dụng kế toán, tồn kho, đặt hàng hoặc kiểm soát quota, lỗi này có thể tạo ra sai lệch lớn.

Không nên gọi refresh như bước “an toàn mặc định” sau mỗi thay đổi trên managed entity. Chỉ gọi khi **thực sự muốn bỏ hoặc đồng bộ lại trạng thái in-memory bằng dữ liệu database**.

## 5. flush() trước refresh() thay đổi điều gì?

`flush()` yêu cầu provider đồng bộ những thay đổi đang chờ của persistence context xuống database **trong transaction hiện tại**.

Ví dụ:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

item.changeQuantity(15);

entityManager.flush();

entityManager.refresh(item);

System.out.println(item.getQuantity()); // Thường là 15
```

Vì `flush()` đã phát SQL `UPDATE` làm database trong transaction hiện tại lưu `quantity = 15`, refresh thường đọc lại chính giá trị đó.

### 5.1. Minh họa luồng SQL

```text
Java: quantity = 10
       |
       | changeQuantity(15)
       v
Java: quantity = 15
DB:   quantity = 10
       |
       | flush()
       v
Java: quantity = 15
DB trong transaction hiện tại: quantity = 15
       |
       | refresh()
       v
Java: quantity = 15
DB trong transaction hiện tại: quantity = 15
       |
       | commit()
       v
Thay đổi được cam kết nếu transaction thành công
```

SQL minh họa cho entity có `@Version`:

```sql
UPDATE inventory_items
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
```

Sau đó, provider có thể thực hiện truy vấn đọc lại:

```sql
SELECT id, sku, quantity, unit_price, version
FROM inventory_items
WHERE id = ?;
```

Không nên xem số lượng câu SQL trên là bất biến: dirty checking, flush mode, locking và provider có thể tạo SQL khác. Điều quan trọng là **flush đưa thay đổi xuống database trong transaction, còn refresh đọc lại từ database và áp dụng vào entity**.

### 5.2. Flush không phải commit

Một nhầm lẫn phổ biến:

> “Nếu `flush()` đã chạy thành công, dữ liệu chắc chắn đã lưu vĩnh viễn.”

Không đúng. `flush()` có thể thực thi SQL, kiểm tra constraint và cấp ID/version, nhưng **chưa kết thúc transaction**.

Ví dụ:

```java
transaction.begin();

InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

item.changeQuantity(15);
entityManager.flush();
entityManager.refresh(item);

transaction.rollback();
```

Sau rollback, những thay đổi SQL của transaction bị hủy theo cơ chế database transaction. Dù refresh trước rollback đã nhìn thấy giá trị 15 trong chính transaction đó, hàng database sau rollback sẽ không giữ thay đổi ấy.

Sau rollback, persistence context/managed instances không nên được tái sử dụng như thể mọi state Java vẫn đồng bộ với database; ứng dụng nên kết thúc transaction/context theo quy tắc runtime đang dùng và nạp lại dữ liệu nếu cần.

### 5.3. Có nên flush chỉ để refresh không?

Không phải luôn nên. `flush()` có thể đồng bộ **nhiều thay đổi khác** trong persistence context, không chỉ một field của một entity. Điều này có thể:

- Phát sinh nhiều câu `INSERT`/`UPDATE`/`DELETE`.
- Kích hoạt kiểm tra ràng buộc database.
- Gây lỗi optimistic locking hoặc constraint sớm hơn dự kiến.
- Tăng thời gian giữ khóa trong transaction.
- Khiến những thay đổi khác chưa hoàn chỉnh bị đồng bộ.

Vì vậy, trước khi viết `flush(); refresh(entity);`, hãy xác định rõ mục tiêu:

- Nếu muốn **bỏ thay đổi chưa lưu**, dùng refresh *trước khi chúng bị flush* theo điều kiện phù hợp.
- Nếu muốn **đọc giá trị do trigger/database tạo sau SQL**, có thể cần flush trước rồi refresh.
- Nếu muốn **kiểm tra trạng thái một field** mà không ảnh hưởng managed object, đôi khi một truy vấn scalar hoặc thiết kế riêng sẽ an toàn hơn.

## 6. FlushModeType.AUTO và rủi ro flush xảy ra sớm

Không phải chỉ `entityManager.flush()` mới có thể dẫn đến đồng bộ SQL. JPA có **flush mode**, thường gặp:

- `FlushModeType.AUTO`: provider bảo đảm kết quả truy vấn phù hợp với thay đổi liên quan đang chờ; việc flush có thể xảy ra trước các truy vấn cần thiết.
- `FlushModeType.COMMIT`: flush liên quan tới commit; tác động chính xác của thay đổi chưa flush lên kết quả truy vấn trước commit có những giới hạn theo đặc tả.

Ví dụ:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

item.changeQuantity(15);

// Một truy vấn JPQL chạy ở đây:
Long count = entityManager.createQuery(
        "SELECT COUNT(i) FROM InventoryItem i " +
        "WHERE i.quantity >= 15",
        Long.class
    )
    .getSingleResult();

// Sau đó mới refresh:
entityManager.refresh(item);
```

Với `AUTO`, provider có thể cần đồng bộ thay đổi để truy vấn quan sát kết quả đúng theo ngữ nghĩa JPA. Nếu `quantity = 15` đã được flush trước khi refresh, kết quả sẽ khác ví dụ trước: refresh có thể đọc lại 15 thay vì 10.

Do đó, quy tắc **“refresh luôn hoàn tác tất cả thay đổi vừa làm”** là sai. Quy tắc đúng hơn là:

> **Refresh thay managed state bằng trạng thái database mà transaction thực sự nhìn thấy tại thời điểm refresh.** Những thay đổi chỉ nằm trong bộ nhớ có thể bị mất; những thay đổi đã được flush có thể được đọc lại từ database.

Không nên suy luận rằng provider sẽ luôn flush trước refresh hoặc sẽ không bao giờ flush trước refresh trong mọi cấu hình. Hãy kiểm soát ranh giới thao tác, truy vấn phát sinh và flush mode để tránh phụ thuộc vào một thời điểm đồng bộ ngầm.

### 6.1. Flush mode không biến refresh thành thao tác lưu

Nếu đổi sang:

```java
entityManager.setFlushMode(
    jakarta.persistence.FlushModeType.COMMIT
);
```

điều đó không biến refresh thành phương thức bảo toàn dirty state. `COMMIT` chỉ điều chỉnh một khía cạnh của việc đồng bộ; refresh vẫn có mục đích đọc lại state từ database.

Việc chọn flush mode nên xét toàn bộ transaction và truy vấn, không dùng nó như cách “chống mất dữ liệu khi refresh” khi bản thân application đang gọi sai thao tác.

## 7. refresh khác find, flush, clear, detach và merge như thế nào?

Để tránh nhầm lẫn, hãy so sánh các phương thức theo **tác động tới entity đã managed**.

| Thao tác | Mục đích | Có thể ghi SQL? | Ảnh hưởng tới thay đổi chưa flush |
| --- | --- | --- | --- |
| `find(Entity.class, id)` | Tìm entity theo ID; ưu tiên managed instance nếu đã có trong context. | Có thể SELECT nếu chưa managed; flushing còn tùy ngữ cảnh. | Thường **không ghi đè** state managed đã sửa. |
| **`refresh(entity)`** | Nạp lại state persistent của managed entity từ database. | Chủ yếu đọc; có thể phát sinh thêm tác động do flush/cascade/locking tùy môi trường. | Có thể **ghi đè/bỏ** thay đổi chưa đồng bộ. |
| `flush()` | Đồng bộ thay đổi đang chờ xuống database trong transaction. | Có, thường INSERT/UPDATE/DELETE. | Đưa thay đổi vào DB transaction; không commit. |
| `clear()` | Tách **mọi** managed entity khỏi persistence context. | Không nhằm đồng bộ. | Thay đổi chưa flush có thể không còn được ghi tự động. |
| `detach(entity)` | Tách **một** managed entity khỏi context, có thể cascade detach. | Không nhằm đồng bộ. | Thay đổi chưa flush của entity detached có thể bị bỏ khỏi quá trình đồng bộ. |
| `merge(detached)` | Sao chép state của object detached/new vào instance managed. | Có thể SELECT và sau đó INSERT/UPDATE. | Không phải thao tác đọc lại để loại bỏ sửa đổi; có thể đưa dữ liệu cũ vào bản managed. |
| `rollback()` | Hủy thay đổi database của transaction đang thực hiện. | DB thực hiện rollback. | Không tự khôi phục mọi managed object về trạng thái sạch có thể tái sử dụng. |

Từ bảng này, có thể chia mục tiêu thành ba loại:

**Muốn xem dữ liệu:** dùng `find()`, JPQL, Criteria, native query hoặc DTO phù hợp.

**Muốn lưu thay đổi:** để dirty checking xử lý tại flush/commit, hoặc gọi `flush()` khi cần đồng bộ sớm.

**Muốn thay trạng thái object managed bằng database state:** cân nhắc `refresh()` với hiểu biết rõ về hậu quả.

### 7.1. find() sau khi sửa không đảo ngược thay đổi

```java
InventoryItem first =
    entityManager.find(InventoryItem.class, 10L);

first.changeQuantity(15);

InventoryItem again =
    entityManager.find(InventoryItem.class, 10L);

System.out.println(first == again);        // true
System.out.println(again.getQuantity());   // thường là 15
```

Đây là hành vi identity map: `find()` không tự xem database là nguồn ghi đè đối với managed entity đã có.

### 7.2. clear() không giống refresh()

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

item.changeQuantity(15);

entityManager.clear();
```

Sau `clear()`, `item` trở thành detached; state Java có thể vẫn là 15, nhưng JPA không còn tự động theo dõi để flush. Một lần `find()` mới có thể lấy một instance managed khác từ database.

So sánh:

- **Refresh:** giữ entity managed và **thay giá trị của chính object đó**.
- **Clear:** **tách tất cả object** khỏi context; object Java cũ không tự bị đặt lại giá trị.

Nếu ý định chỉ làm mới một entity, `clear()` có phạm vi ảnh hưởng lớn hơn nhiều. Nó cũng có thể làm mất các sửa đổi chưa flush của những entity khác.

### 7.3. detach() không giống refresh()

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

entityManager.detach(item);
```

`item` không còn managed. `refresh(item)` trực tiếp trên instance detached không phải cách hợp lệ để đọc lại state. Nếu cần object hiện có theo database, thường nên tìm entity bằng một EntityManager phù hợp để nhận bản managed, hoặc tổ chức lại ranh giới giao dịch.

### 7.4. merge() không phải refresh của detached entity

```java
InventoryItem detached = /* object đã tách khỏi context */;

InventoryItem managed =
    entityManager.merge(detached);
```

`merge()` **sao chép dữ liệu từ object nguồn vào managed instance**, trả về managed instance và có thể dẫn tới ghi database khi flush. Nó không có ý nghĩa “bỏ dữ liệu cũ trên detached object và đọc bản mới nhất”.

Nếu client gửi một entity detached đã cũ, dùng `merge()` một cách mù quáng có thể gây ghi đè dữ liệu; `@Version` giúp phát hiện xung đột theo quy tắc locking, nhưng không thay thế thiết kế update theo các field được cho phép.

## 8. Refresh sau khi transaction khác cập nhật dữ liệu

Một mục đích hợp lý của refresh là **đọc lại state do một transaction khác sửa**.

Giả sử hai entity manager dùng hai persistence context độc lập:

```text
Transaction / Context A                  Transaction / Context B
-----------------------                 -----------------------
find InventoryItem#10
quantity = 10

                                        find InventoryItem#10
                                        changeQuantity(12)
                                        commit thành công

A vẫn có managed item
quantity = 10

A gọi refresh(item)
=> có thể đọc quantity = 12
   nếu isolation cho phép nhìn thấy
   thay đổi đã commit của B
```

**Điều kiện “nếu isolation cho phép” rất quan trọng.** Refresh không tự vượt qua quy tắc isolation của database và không bảo đảm nhìn thấy một giao dịch khác đang chưa commit.

### 8.1. READ COMMITTED và REPEATABLE READ

Đây là hai mức isolation thường gặp, nhưng cách thực thi cụ thể còn tùy DBMS:

| Isolation | Khi A đã đọc hàng, B commit thay đổi, A refresh lại |
| --- | --- |
| `READ COMMITTED` | Một câu SELECT mới thường có thể thấy dữ liệu B vừa commit, trừ khi có locking/cơ chế khác. |
| `REPEATABLE READ` hoặc snapshot-based isolation | A có thể tiếp tục thấy phiên bản dữ liệu theo snapshot của transaction A; refresh không bảo đảm thấy commit mới của B. |
| `SERIALIZABLE` | Database có thể giữ snapshot/khóa hoặc báo serialization conflict tùy engine và lịch giao dịch. |

Các dòng trên nêu **nguyên lý tổng quan**, không phải bảng kết quả cố định cho mọi database. Ví dụ, SQL Server, PostgreSQL, MySQL/InnoDB và các cấu hình MVCC/lock có thể có khác biệt đáng kể.

**Refresh không phải cơ chế đồng bộ toàn hệ thống theo thời gian thực.** Nếu yêu cầu dữ liệu mới nhất tuyệt đối kèm quyền ghi, thường cần thiết kế transaction, isolation và locking phù hợp thay vì chỉ gọi refresh.

### 8.2. Thay đổi chưa commit của B không nhất thiết đọc được

Nếu B đã sửa `quantity = 12` nhưng chưa commit, transaction A ở isolation thông thường **không được đọc thay đổi chưa commit đó**.

`refresh(item)` không có nghĩa bỏ qua isolation hay bypass transaction của DB. Trong đa số ứng dụng, refresh cần được hiểu là **đọc state đang nhìn thấy được bởi transaction hiện tại**.

### 8.3. Lưu ý về @Version

Nếu entity có `@Version` và B đã commit một phiên bản mới, A có thể gặp xung đột optimistic locking tùy tình huống. Một thao tác refresh có thể liên quan đến kiểm tra version hoặc lock mode; JPA provider có thể ném `OptimisticLockException` khi phát hiện điều kiện xung đột theo hợp đồng locking.

Không nên dựa vào refresh để “né” phiên bản cũ rồi ghi đè dữ liệu của B. Nếu A đã sửa một số field, việc refresh có thể **bỏ sửa đổi của A** để lấy state mới của B; đây là quyết định nghiệp vụ, không phải merge hai thay đổi một cách thông minh.

Nếu hệ thống cần hỗ trợ giải quyết xung đột, quy trình thường gồm báo lỗi, nạp state mới, so sánh thay đổi và yêu cầu người dùng xác nhận hoặc tính lại thao tác.

## 9. Mục đích hợp lý: đồng bộ lại sau SQL ngoài cơ chế EntityManager

Một tình huống phổ biến khác là ứng dụng dùng **native SQL**, JDBC trực tiếp, stored procedure hoặc bulk JPQL update để sửa dữ liệu.

Ví dụ, trong một transaction có managed entity:

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

// Một câu native SQL cập nhật trực tiếp bảng.
int updated = entityManager.createNativeQuery(
        "UPDATE inventory_items " +
        "SET quantity = :quantity " +
        "WHERE id = :id"
    )
    .setParameter("quantity", 20)
    .setParameter("id", 10L)
    .executeUpdate();
```

Sau lệnh SQL đó, object `item` trong persistence context **có thể vẫn giữ quantity cũ**, vì các lệnh cập nhật trực tiếp vào database không tự điều chỉnh field Java của những entity đã managed.

Có thể gọi:

```java
entityManager.refresh(item);

System.out.println(item.getQuantity()); // Có thể thấy 20.
```

Ví dụ giả định native SQL đã chạy thành công, transaction hiện tại nhìn thấy thay đổi, và không phát sinh xung đột locking. Khi có `@Version`, native SQL không tự thực hiện quy tắc tăng version của JPA như một managed entity update; các thao tác SQL trực tiếp phải cân nhắc đồng bộ version, constraint và concurrency theo thiết kế.

### 9.1. Bulk JPQL UPDATE cũng bỏ qua state managed

```java
InventoryItem item =
    entityManager.find(InventoryItem.class, 10L);

int affected = entityManager.createQuery(
        "UPDATE InventoryItem i " +
        "SET i.quantity = 20 " +
        "WHERE i.id = :id"
    )
    .setParameter("id", 10L)
    .executeUpdate();

// item có thể vẫn giữ số lượng cũ trong bộ nhớ.
entityManager.refresh(item);
```

Đối với bulk JPQL update/delete, provider thực thi tác động trên database mà không đồng bộ tự động mọi managed entity đã tải. `refresh` có thể là một cách làm mới **một entity được xác định**, còn `clear()` có thể được cân nhắc nếu muốn loại bỏ toàn bộ managed state cũ, với điều kiện đã xử lý những thay đổi chưa flush.

### 9.2. Khi gọi SQL trực tiếp, ưu tiên kiểm soát phạm vi thay đổi

Trong thực tế nên cân nhắc:

1. Flush các thay đổi cần lưu **trước** bulk/native SQL nếu tính nhất quán yêu cầu, vì bulk SQL có thể đọc trạng thái database chứ không đọc các sửa đổi chỉ nằm trong managed entities.
2. Thực thi native/bulk SQL.
3. Làm mới **những entity chịu ảnh hưởng** bằng refresh, hoặc clear/reload trong một luồng có chủ đích.
4. Tính tới `@Version`, cache, transaction isolation và lifecycle callbacks vốn không tự được bulk operation xử lý giống entity update.

Nếu có hàng nghìn entity đang managed, refresh từng entity có thể tạo rất nhiều SQL. Không phải mọi bulk update đều nên được theo sau bởi vòng lặp gọi refresh hàng nghìn lần; đôi khi một persistence context mới sẽ rõ ràng và hiệu quả hơn.

## 10. refresh và dữ liệu do database tự cập nhật

Ngoài bulk update, database có thể tự sinh hoặc điều chỉnh giá trị bằng:

- Trigger.
- Default expression.
- Generated/computed column.
- Stored procedure.
- Quy tắc chuẩn hóa dữ liệu ở tầng database.

Ví dụ database có một trigger sửa trường `last_restocked_at` khi số lượng hàng thay đổi. Nếu JPA entity có mapping cho trường đó nhưng provider không tự lấy lại giá trị mới sau update, ứng dụng có thể muốn:

```java
item.changeQuantity(25);

entityManager.flush();   // Đưa UPDATE xuống DB, trigger có thể chạy.
entityManager.refresh(item); // Đọc lại giá trị DB sinh/chỉnh.
```

Điểm quyết định: **Phải có thao tác ghi thích hợp trước khi refresh** nếu giá trị mong muốn chỉ được database tạo khi thực hiện UPDATE/INSERT. Nếu refresh trước flush, những thay đổi làm trigger chạy có thể bị loại bỏ, khiến trigger chưa từng có cơ hội xử lý chúng.

Tuy nhiên, provider như Hibernate có thể hỗ trợ những annotation/cơ chế riêng để lấy lại generated value mà không cần gọi refresh thủ công mọi lần. Khi hệ thống có yêu cầu này thường xuyên, nên nghiên cứu khả năng mapping/generated columns của provider và tránh thêm những vòng SELECT không cần thiết.

### 10.1. Giá trị default lúc INSERT

Nếu một cột database có default, việc JPA gửi giá trị `NULL` rõ ràng có thể khác với việc bỏ cột khỏi INSERT; không phải mọi database đều áp dụng default theo cùng một cách trong hai trường hợp đó.

Để dùng default/generation của database, mapping phải được thiết kế đúng. Refresh chỉ đọc trạng thái hiện có; nó không thể sửa một INSERT đã ghi giá trị không phù hợp với schema.

## 11. Refresh với entity có quan hệ

Entity thường không đứng một mình: nó có `@ManyToOne`, `@OneToMany`, `@OneToOne` hoặc `@ManyToMany`. Khi refresh một entity cha, cần phân biệt **làm mới state của cha** với **lan truyền refresh sang entity con**.

### 11.1. Ví dụ Order và OrderLine

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = CascadeType.REFRESH
    )
    private java.util.List<OrderLine> lines =
        new java.util.ArrayList<>();

    // Getter và các field khác được lược bớt.
}
```

```java
@Entity
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    private Integer quantity;

    // Getter và các field khác được lược bớt.
}
```

Hai lớp trên là **mẫu ngắn để giải thích quan hệ**, không phải một project hoàn chỉnh; ứng dụng thực tế cần constructor phù hợp, mapping khóa và validation đúng với schema.

### 11.2. CascadeType.REFRESH là gì?

Với:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REFRESH
)
private List<OrderLine> lines;
```

khi gọi:

```java
entityManager.refresh(order);
```

thao tác refresh được **lan truyền** đến các entity liên quan trong association theo quy tắc JPA. Nếu `OrderLine` đã có sửa đổi chưa flush, những sửa đổi đó **cũng có thể bị ghi đè** khi refresh cascade đến nó.

Ví dụ:

```java
OrderLine line = order.getLines().get(0);
line.changeQuantity(5); // Giả sử đây là method nghiệp vụ.

entityManager.refresh(order);

// Với cascade REFRESH, quantity của line
// có thể quay về dữ liệu lưu trong DB.
```

Đoạn trên giả định `changeQuantity` tồn tại trong entity thực tế và việc tải liên quan diễn ra trong persistence context phù hợp.

**`CascadeType.ALL` cũng bao gồm `REFRESH`.** Vì vậy, nếu một association khai báo `cascade = ALL`, refresh một entity có thể ảnh hưởng đến **nhiều entity liên quan**, không chỉ object ban đầu.

### 11.3. Nếu không có CascadeType.REFRESH?

Không nên mặc định rằng refresh entity cha sẽ thực hiện refresh đệ quy **mọi entity liên quan** trong object graph.

```java
@OneToMany(mappedBy = "order") // Không khai báo cascade.
private List<OrderLine> lines;
```

Khi gọi `refresh(order)`, thao tác không được yêu cầu cascade `REFRESH` đến tất cả child theo mapping này. Dữ liệu của các child đang managed có thể vẫn theo state riêng của chúng; kế hoạch tải và đồng bộ collection của provider còn phụ thuộc mapping và tình trạng đã khởi tạo.

Cần phân biệt:

- **Làm mới state/association của entity nguồn**: thuộc phạm vi refresh nguồn.
- **Gọi refresh lên managed entity đích**: phải có cascade REFRESH tương ứng nếu muốn lan truyền theo association.
- **Tải collection LAZY**: là chiến lược fetching, không tương đương cascade.
- **orphanRemoval**: quy tắc xóa child bị tách khỏi quan hệ, khác với refresh và cascade.

### 11.4. Refresh có thể tốn nhiều truy vấn

Nếu `Order` có 1.000 dòng và association cascade REFRESH, refresh order có thể kéo theo việc đọc lại rất nhiều entity tùy provider và fetch plan. Nó cũng có thể ghi đè 1.000 thay đổi chưa flush nếu các child bị refresh.

Không nên bật `CascadeType.ALL` chỉ để tiện khi lưu entity mới mà không cân nhắc tác động của `REFRESH` và `REMOVE`. Khi cần refresh một entity cụ thể, nên xác định phạm vi dữ liệu thật sự cần đọc lại.

## 12. Collection và @ElementCollection có thể bị ảnh hưởng thế nào?

Một value collection như:

```java
@ElementCollection
private java.util.Set<String> tags =
    new java.util.HashSet<>();
```

là **một phần trạng thái persistent của entity sở hữu**, không phải tập hợp entity độc lập để dùng `CascadeType.REFRESH` cho từng `String`.

Giả sử:

```java
Project project =
    entityManager.find(Project.class, projectId);

project.getTags().add("urgent");

// Chưa flush:
entityManager.refresh(project);
```

Provider có thể khôi phục trạng thái persistent của collection từ database theo hợp đồng refresh và mapping, khiến `"urgent"` mới thêm **không được lưu** nếu thay đổi chưa flush. Với collection có lazy loading, cách và thời điểm provider khởi tạo/tải lại có thể khác nhau.

Tương tự với embeddable:

```java
@Embedded
private Address shippingAddress;
```

Nếu ứng dụng sửa các thuộc tính persistent trong embedded value rồi refresh owner trước khi flush, trạng thái embedded có thể được thay thế bằng dữ liệu đã lưu.

**Không xem refresh như một thao tác chỉ sửa các basic scalar fields mà an toàn với mọi embedded object hoặc collection.** Phạm vi trạng thái persistent cần được hiểu từ mapping, và hành vi chi tiết của collection có thể khác giữa provider/phiên bản.

## 13. refresh với @Version và optimistic locking

`@Version` thường được dùng để kiểm soát việc hai transaction cập nhật cùng entity:

```java
@Version
private Long version;
```

Một ví dụ:

```text
Transaction A                Transaction B
-------------                -------------
Read Item#10, version=0
                             Read Item#10, version=0
                             Change quantity to 12
                             Commit, version=1
Change quantity to 15
Attempt flush/commit
=> Có thể bị optimistic lock conflict
```

### 13.1. Refresh có giải quyết optimistic conflict tự động?

Không. Refresh chỉ đọc lại state DB của managed entity. Nếu A refresh sau khi B đã commit, A có thể nhận version mới và quantity mới **nếu transaction isolation và locking cho phép**. Nhưng sửa đổi `quantity = 15` của A có thể bị mất.

Đây không phải “gộp” thay đổi hai bên. Nếu muốn kiểm tra xung đột và áp dụng lại thay đổi của A, service phải có **quy tắc nghiệp vụ rõ ràng**: đọc lại, so sánh dữ liệu, tính lại số lượng hoặc từ chối thao tác.

### 13.2. Có thể phát sinh OptimisticLockException khi refresh?

Trong những trường hợp liên quan tới optimistic locking và version, provider có thể phát hiện xung đột và ném `OptimisticLockException`. Ngoại lệ cụ thể còn phụ thuộc overload lock mode, trạng thái entity, transaction và cách provider thực thi.

Không nên đưa ra quy tắc rằng mọi lời gọi refresh khi có version khác đều luôn thành công, hoặc luôn thất bại. **Điều phải thiết kế là handling khi dữ liệu đã thay đổi đồng thời**, kể cả khi refresh trả về thành công.

### 13.3. Không dùng refresh để lén ghi đè bản mới hơn

Ví dụ nghiệp vụ trừ tồn kho:

1. A đọc quantity 10.
2. B bán 3 sản phẩm và commit quantity 7.
3. A định bán 5 sản phẩm.

Nếu A refresh thấy quantity 7, A phải kiểm tra còn đủ hàng rồi mới trừ, thay vì lấy một delta tính trên 10 và gán lại như không có thay đổi đồng thời. Nếu phải đảm bảo không bán âm kho, sử dụng optimistic locking, pessimistic locking hoặc atomic conditional update tùy thiết kế, không chỉ refresh.

## 14. Refresh với lock mode

JPA hỗ trợ làm mới entity và yêu cầu khóa trong một thao tác:

```java
entityManager.refresh(
    item,
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
);
```

Trong một transaction hợp lệ, provider có thể dùng cơ chế khóa database để ngăn hoặc điều phối các update cạnh tranh trong phạm vi câu lệnh và transaction.

Một số chế độ cần hiểu:

| LockModeType | Mục đích khái quát |
| --- | --- |
| `NONE` | Không yêu cầu lock mode đặc biệt. |
| `OPTIMISTIC` | Kiểm tra optimistic locking phù hợp với version entity. |
| `OPTIMISTIC_FORCE_INCREMENT` | Yêu cầu version tăng theo quy tắc optimistic forced increment. |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc pessimistic theo khả năng DB. |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi pessimistic. |
| `PESSIMISTIC_FORCE_INCREMENT` | Yêu cầu pessimistic lock và tăng version theo quy tắc hỗ trợ. |

Đây là những lựa chọn có điều kiện. Việc dùng lock mode có thể yêu cầu transaction hoạt động và có thể gặp `PessimisticLockException`, `LockTimeoutException` hoặc những ngoại lệ khác nếu lock thất bại.

### 14.1. Khi nào lock phù hợp hơn refresh đơn thuần?

Giả sử việc cập nhật số lượng tồn kho phải đảm bảo một request không bị request khác chèn vào giữa kiểm tra và ghi. Nếu ứng dụng chỉ:

```java
entityManager.refresh(item);
if (item.getQuantity() >= 5) {
    item.changeQuantity(item.getQuantity() - 5);
}
```

thì giữa lúc refresh và commit, transaction khác vẫn có thể sửa hàng nếu không có cơ chế kiểm soát concurrency. Refresh **không khóa hàng chỉ vì nó đọc lại dữ liệu**.

Trong những luồng cần serialization/consistency mạnh, có thể cân nhắc version check, pessimistic locking hoặc câu SQL update có điều kiện:

```sql
UPDATE inventory_items
SET quantity = quantity - 5
WHERE id = ?
  AND quantity >= 5;
```

Sau đó cần kiểm tra số hàng được update và xem xét version/cache/transaction. Đây là một thiết kế update nguyên tử khác, không phải ví dụ thay thế trực tiếp cho toàn bộ cơ chế refresh của JPA.

## 15. Những ngoại lệ thường gặp khi refresh

`refresh()` không bảo đảm luôn thành công. Một số tình huống đáng chú ý:

### 15.1. Entity không managed

```java
InventoryItem detached = /* entity từ EntityManager đã đóng */;

entityManager.refresh(detached); // Không hợp lệ theo hợp đồng managed.
```

Provider có thể ném `IllegalArgumentException`. Hãy tải entity managed trong context hiện tại rồi mới refresh nếu còn cần.

### 15.2. Hàng database đã bị xóa

Nếu entity managed còn trong context nhưng hàng tương ứng đã bị transaction khác xóa và việc xóa đó nhìn thấy được, refresh có thể không tìm thấy dữ liệu. JPA có thể báo lỗi, chẳng hạn `EntityNotFoundException` theo hợp đồng phương thức hoặc ngoại lệ provider phù hợp.

Không nên viết code bắt mọi exception rồi tiếp tục dùng object như thể việc refresh đã thành công.

### 15.3. Không có transaction phù hợp

Với transaction-scoped persistence context và môi trường JPA/container nhất định, thao tác refresh có thể yêu cầu transaction đang hoạt động. Khi cần lock mode, việc thiếu transaction càng dễ dẫn đến `TransactionRequiredException`.

Để tránh sai lệch hành vi giữa runtime, **thực hiện refresh trong ranh giới transaction phù hợp** khi thao tác thuộc luồng nghiệp vụ cần tính nhất quán.

### 15.4. Xung đột locking hoặc timeout

Nếu entity có version hoặc refresh yêu cầu pessimistic lock, có thể phát sinh `OptimisticLockException`, `PessimisticLockException` hoặc `LockTimeoutException` theo tình huống.

Ứng dụng cần phân biệt:

- Lỗi đòi hỏi rollback transaction.
- Lỗi có thể retry một đơn vị công việc nếu chính sách cho phép.
- Lỗi cần báo người dùng dữ liệu đã được cập nhật bởi người khác.

Không nên retry `refresh()` vô hạn hoặc nuốt exception rồi giả định state chắc chắn đồng bộ.

## 16. refresh trong Spring Data JPA

Spring Data JPA dùng JPA `EntityManager` ở phía dưới, nhưng `JpaRepository` **không cung cấp `refresh(entity)` như một phương thức chuẩn mặc định của repository**.

Nếu service cần refresh, có thể inject `EntityManager`:

```java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryRefreshService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Integer reloadQuantity(Long itemId) {
        InventoryItem item =
            entityManager.find(InventoryItem.class, itemId);

        if (item == null) {
            throw new IllegalArgumentException(
                "Item not found: " + itemId
            );
        }

        entityManager.refresh(item);
        return item.getQuantity();
    }
}
```

Lưu ý:

- `@PersistenceContext` inject EntityManager do container/Spring quản lý.
- `@Transactional` xác định ranh giới giao dịch khi lời gọi đi qua transaction interceptor.
- Không gọi `close()` trên EntityManager được inject.
- Entity nhận từ `find()` ở đây là managed nên có thể refresh.
- Phương thức trên có chủ đích làm mới dữ liệu; nó không nên được chèn vào một luồng vừa sửa item mà chưa flush nếu mục tiêu là giữ thay đổi.

### 16.1. Một service có thể vô tình làm mất thay đổi

Ví dụ:

```java
@Transactional
public void incorrectExample(Long itemId) {
    InventoryItem item =
        entityManager.find(InventoryItem.class, itemId);

    item.changeQuantity(15);

    entityManager.refresh(item); // Có thể bỏ quantity=15.

    // Transaction commit nhưng thay đổi 15 có thể đã bị mất.
}
```

Không nên thêm refresh sau `repository.save(...)` hoặc sau một phép sửa managed entity chỉ với mục đích “đảm bảo dữ liệu mới nhất”. Cần hiểu Spring Data đã gọi `persist` hay `merge`, entity có đang managed không, dữ liệu có cần flush không và giá trị muốn đọc đến từ nguồn nào.

### 16.2. Nếu dùng repository saveAndFlush?

`JpaRepository.saveAndFlush(entity)` được Spring Data JPA cung cấp để lưu và flush theo cơ chế repository, nhưng **không đồng nghĩa commit transaction**.

Nếu mục tiêu là đọc giá trị database mới sinh sau SQL, một quy trình có thể là:

```java
@Transactional
public InventoryItem updateThenRefresh(
        Long itemId,
        Integer quantity) {
    InventoryItem item =
        entityManager.find(InventoryItem.class, itemId);

    item.changeQuantity(quantity);

    entityManager.flush();
    entityManager.refresh(item);

    return item;
}
```

Ví dụ trên giả định item tồn tại và transaction hợp lệ. Trả entity ra khỏi transaction có thể tạo các vấn đề lazy loading/serialization; trong API thực tế thường nên map thành DTO thích hợp trước khi trả.

Nếu cần một giá trị generated by database, provider-specific annotations hoặc query projection có thể giúp giảm việc refresh lặp lại.

## 17. Khi nào refresh là lựa chọn hợp lý?

Một số tình huống thường phù hợp:

**Tình huống A — Đọc lại state sau native/bulk SQL**

Provider không tự đồng bộ managed instance sau câu SQL trực tiếp, nên refresh một số entity ảnh hưởng có thể đưa Java state về đúng dữ liệu nhìn thấy từ DB.

**Tình huống B — Đọc lại giá trị database sinh bởi trigger/default**

Sau khi insert/update đã thực sự xảy ra, refresh có thể nạp lại giá trị được database tính toán, nếu mapping/provider không tự lấy lại.

**Tình huống C — Có chủ đích hủy chỉnh sửa chưa lưu**

Trong một luồng chỉnh sửa được kiểm soát, người dùng chọn “bỏ thay đổi”. Nếu entity đang managed và trạng thái database chính là bản cần khôi phục, refresh có thể bỏ các sửa đổi chưa flush. Nhưng nếu trước đó đã flush, nó không thể thay cho rollback của transaction hoặc chức năng undo nghiệp vụ.

**Tình huống D — Entity managed đã lỗi thời so với state mà transaction nhìn thấy**

Nếu một transaction khác đã commit và isolation cho phép nhìn thấy, refresh giúp cập nhật managed entity mà không phải đóng context. Cần xử lý locking/version và đảm bảo không có dirty state muốn giữ.

### 17.1. Khi nào không nên refresh?

Không nên xem refresh là mặc định cho:

- Mọi lần đọc entity.
- Mọi lần gọi `save()` hoặc `persist()`.
- Mọi lần thay đổi một field.
- Bài toán đồng bộ thời gian thực giữa nhiều người dùng.
- Việc sửa một detached entity.
- Việc giải quyết xung đột optimistic locking một cách tự động.
- Tối ưu hiệu năng khi đang có N+1 hoặc query chậm.
- Một công cụ “flush những gì vừa sửa”.

Refresh có chi phí truy vấn, có thể gây mất thay đổi chưa flush và có thể cascade. Chỉ dùng khi lợi ích đọc lại state lớn hơn những tác động đó.

## 18. Thiết kế luồng nghiệp vụ để tránh mất dữ liệu ngoài ý muốn

Một cách tổ chức service rõ ràng là chia luồng thành hai loại.

### 18.1. Luồng ghi: dùng managed entity, tránh refresh tùy tiện

```text
BEGIN TRANSACTION
        |
        +-- Load managed entity
        |
        +-- Validate nghiệp vụ
        |
        +-- Thay đổi các field cần cập nhật
        |
        +-- (Flush khi thật sự cần)
        |
        +-- Commit
```

Luồng này dựa vào dirty checking, version và transaction. Nếu cần chống xung đột, thêm optimistic/pessimistic locking hoặc thao tác update nguyên tử phù hợp.

### 18.2. Luồng đọc lại: xử lý state cũ trước khi refresh

```text
BEGIN TRANSACTION
        |
        +-- Xác định entity nào cần reload
        |
        +-- Kiểm tra có dirty changes cần giữ không
        |       |
        |       +-- Có -> lưu/hoàn tất, hoặc hủy có chủ đích
        |       |
        |       +-- Không -> tiếp tục
        |
        +-- refresh(managedEntity)
        |
        +-- Đọc state mới theo DB/isolation
        |
        +-- Commit / kết thúc transaction
```

Điểm quan trọng không phải thêm nhiều câu lệnh bảo vệ máy móc, mà là **đặt đúng ý nghĩa cho thao tác**: refresh là “thay state hiện có bằng state từ DB”, nên luôn cần quyết định trước về các thay đổi đang chờ.

### 18.3. Nếu cần giữ cả sửa đổi local và bản database mới?

Ví dụ người dùng sửa `unitPrice` trên form, trong khi transaction khác cập nhật `quantity`. Refresh trực tiếp trên entity có thể làm mất đơn giá mới trên form.

Một lựa chọn kiến trúc là:

1. Giữ dữ liệu người dùng đang sửa trong **DTO/command** độc lập với managed entity.
2. Tải entity managed mới trong transaction.
3. Kiểm tra `@Version` hoặc quy tắc conflict.
4. Chỉ áp dụng những field người dùng được phép sửa theo ý định hiện tại.
5. Commit với kiểm soát concurrency.

Nếu cần merge tự động hai phiên bản, phải có thuật toán đối chiếu trường và quy tắc ưu tiên dữ liệu rõ ràng. `EntityManager.refresh()` **không thực hiện việc gộp này**.

## 19. Thực hành theo từng kịch bản

### Kịch bản 1 — Mất thay đổi chưa flush

Trạng thái database ban đầu:

```text
InventoryItem#10 quantity=10, unitPrice=450000.00
```

Code:

```java
InventoryItem item = em.find(InventoryItem.class, 10L);
item.changeQuantity(20);
em.refresh(item);
System.out.println(item.getQuantity());
```

**Giải thích:** Nếu chưa có flush và database chưa đổi, kết quả thường là `10`. Giá trị `20` trong bộ nhớ bị ghi đè.

### Kịch bản 2 — Flush rồi refresh

```java
InventoryItem item = em.find(InventoryItem.class, 10L);
item.changeQuantity(20);
em.flush();
em.refresh(item);
System.out.println(item.getQuantity());
```

**Giải thích:** Nếu flush thành công, transaction hiện tại đọc được thay đổi mình vừa ghi nên thường thấy `20` sau refresh. Nhưng transaction vẫn có thể rollback.

### Kịch bản 3 — Find lần thứ hai

```java
InventoryItem first = em.find(InventoryItem.class, 10L);
first.changeQuantity(20);

InventoryItem second = em.find(InventoryItem.class, 10L);
System.out.println(second.getQuantity());
```

**Giải thích:** Trong cùng context, `second` là cùng managed instance với `first`, thường thấy `20`. `find` không dùng để loại bỏ sửa đổi như refresh.

### Kịch bản 4 — Refresh sau JDBC update

```java
InventoryItem item = em.find(InventoryItem.class, 10L);

// Giả sử thao tác JDBC/native SQL phù hợp trong cùng transaction
// cập nhật quantity ở database từ 10 thành 30.

em.refresh(item);
System.out.println(item.getQuantity());
```

**Giải thích:** Nếu transaction hiện tại nhìn thấy update 30, refresh có thể nạp 30 vào managed instance. Nếu update ở transaction khác, còn phải xét commit và isolation.

### Kịch bản 5 — Refresh cascade

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REFRESH
)
private List<OrderLine> lines;
```

Service sửa một dòng rồi refresh đơn hàng trước khi flush.

**Giải thích:** Cascade REFRESH có thể đưa state của dòng về dữ liệu đã lưu. Đừng nhầm với `FetchType.LAZY`, vì fetching và cascading giải quyết hai bài toán khác nhau.

### Kịch bản 6 — Database trigger sinh giá trị

Service thay đổi một trường kích hoạt trigger khi SQL UPDATE chạy.

**Hướng xử lý:** Khi mapping không tự đọc generated value, có thể flush để trigger chạy rồi refresh để lấy lại dữ liệu. Nếu refresh trước flush, thay đổi dẫn đến trigger có thể bị ghi đè.

### Kịch bản 7 — Transaction A muốn thấy dữ liệu vừa commit của B

Transaction A đang giữ managed entity, B cập nhật và commit. A gọi refresh.

**Giải thích:** A có thể thấy dữ liệu mới nếu isolation cho phép một lần đọc mới quan sát commit của B. Dưới snapshot isolation hoặc repeatable read, không nên bảo đảm refresh thấy phiên bản mới. Locking/version có thể làm thao tác thất bại.

### Kịch bản 8 — Không có transaction

Ứng dụng gọi refresh trên entity không managed hoặc trong context/lock mode cần transaction nhưng chưa có transaction.

**Giải thích:** Có thể gặp `IllegalArgumentException` hoặc `TransactionRequiredException` theo trường hợp. Cần nắm lifecycle entity và transaction context trước khi refresh.

## 20. Các lỗi tư duy thường gặp

### “refresh là cách lưu thay đổi vào database”

Sai. Đó là vai trò của **flush/commit**. Refresh đọc lại state DB và có thể ghi đè thay đổi chưa lưu.

### “Sau khi sửa entity, gọi refresh để xác nhận đã lưu”

Sai nếu chưa flush. Chính refresh có thể hủy sửa đổi, dẫn đến không còn gì để commit.

### “Gọi find lần nữa sẽ bỏ bản cache hiện tại”

Không. Trong cùng persistence context, `find` có thể trả chính managed instance đang có.

### “Đã flush là không thể rollback”

Không. Flush thực thi SQL trong transaction, chưa cam kết vĩnh viễn.

### “refresh luôn đọc phiên bản mới nhất trên toàn hệ thống”

Không. Database isolation, transaction snapshot, locking và concurrency quyết định state được nhìn thấy. Refresh không vượt qua quy tắc transaction.

### “refresh không liên quan tới quan hệ”

Không đúng. Nó làm mới persistent state theo mapping; khi có cascade REFRESH/ALL, entity liên quan có thể bị refresh và mất dirty state.

### “refresh chỉ tác động đến field chưa thay đổi”

Không. Không có phương thức `refresh(entity, fieldName)` chuẩn để lựa chọn một field cụ thể.

### “Nếu entity đã detached thì refresh nó như thường”

Không. Refresh yêu cầu entity managed theo hợp đồng JPA. Cần lấy lại managed instance trong context thích hợp.

### “Bulk JPQL update tự sửa các managed objects đã tải”

Không. Bulk DML làm việc với database và bỏ qua cơ chế đồng bộ state entity theo kiểu dirty checking thông thường; cần refresh/clear/reload nếu muốn Java state được cập nhật.

### “refresh là cách giải quyết optimistic lock mà không mất dữ liệu”

Không. Refresh có thể đọc version mới nhưng cũng có thể loại bỏ sửa đổi local; không thực hiện merge theo quy tắc nghiệp vụ.

### “Cứ gọi refresh nhiều lần để chắc chắn an toàn”

Không. Mỗi lần refresh có thể tạo truy vấn, locking, cascade và chi phí, trong khi không bảo đảm consistency cao hơn database transaction đang cung cấp.

## 21. Bảng quyết định nhanh

| Mục tiêu | Thao tác thường phù hợp | Lưu ý |
| --- | --- | --- |
| Tải entity chưa managed trong context | `find()` | Trong context có sẵn entity thì có thể dùng bản hiện tại. |
| Tiếp tục làm việc với managed entity đã sửa | Giữ entity và commit/flush khi phù hợp | Không refresh tùy tiện. |
| Đồng bộ sửa đổi local xuống DB trước commit | `flush()` | Chưa commit; vẫn có thể rollback. |
| Bỏ sửa đổi chưa flush và lấy lại DB state | `refresh(managedEntity)` | Có thể mất dirty state; xét cascade và isolation. |
| Đọc lại sau native SQL/bulk update | `refresh()` hoặc clear/reload có chủ đích | Xử lý version, cache, trạng thái managed cũ. |
| Đồng bộ giá trị do trigger sinh sau UPDATE | Có thể `flush()` rồi `refresh()` | Kiểm tra mapping/provider generated values. |
| Ngừng theo dõi một entity | `detach()` | Object không tự được reset về DB state. |
| Bỏ tất cả managed instances khỏi context | `clear()` | Ảnh hưởng rộng, thay đổi chưa flush có thể mất. |
| Sao chép state của detached entity vào managed instance | `merge()` | Không phải reload; giá trị trả về là managed. |
| Đảm bảo không ghi đè cập nhật đồng thời | `@Version`, locking hoặc SQL có điều kiện | Refresh riêng lẻ không đủ. |
| Chỉ đọc một cột mới nhất trong phạm vi transaction | Truy vấn scalar/projection phù hợp | Cần hiểu auto-flush và isolation. |

## 22. Câu hỏi tự kiểm tra

**1. Một entity managed có `quantity = 10` trong DB. Sau `changeQuantity(15)` nhưng trước flush, gọi `refresh(item)` sẽ làm gì?**

Nó yêu cầu đọc lại state database và áp dụng lên entity. Nếu database vẫn là 10 và chưa có flush, quantity có thể quay về 10; sửa đổi 15 chưa lưu bị mất.

**2. Gọi `find()` lần thứ hai trên cùng ID trong cùng persistence context có giống `refresh()` không?**

Không. `find()` có thể trả managed instance hiện có; refresh chủ động đọc lại state DB để làm mới managed entity.

**3. Vì sao `flush()` trước `refresh()` có thể khiến thay đổi 15 vẫn còn?**

Vì flush đã cập nhật database trong transaction hiện tại; refresh đọc lại state database mà transaction nhìn thấy, bao gồm thay đổi của chính transaction.

**4. Sau `flush()`, rollback còn tác dụng không?**

Có. Flush chưa phải commit. Transaction rollback có thể hủy những câu SQL đã chạy trong transaction đó.

**5. `refresh()` có bắt buộc phải thấy commit mới nhất của một transaction khác không?**

Không. Nó vẫn chịu database isolation/snapshot và locking. Kết quả khác nhau giữa READ COMMITTED, REPEATABLE READ và những cấu hình khác.

**6. Nếu entity đã detached, có thể gọi `refresh(detached)` trực tiếp không?**

Không theo hợp đồng managed entity. Cần tải entity trở thành managed trong context phù hợp hoặc dùng quy trình khác.

**7. CascadeType.REFRESH ảnh hưởng thế nào đến quan hệ cha-con?**

Nếu refresh cha được lan truyền qua association có cascade REFRESH, child có thể được làm mới và mất các sửa đổi chưa flush của chính nó.

**8. Sau native SQL UPDATE, vì sao managed entity có thể còn giá trị cũ?**

Vì SQL trực tiếp tác động lên database mà không sửa ngay object trong persistence context. Refresh có thể nạp lại state vào managed instance.

**9. Refresh có tự giải quyết lost update khi hai transaction cùng sửa một hàng không?**

Không. Cần optimistic locking, pessimistic locking hoặc cơ chế atomic update và quy tắc nghiệp vụ phù hợp.

**10. Nếu database trigger tạo một giá trị sau UPDATE, tại sao đôi khi cần flush trước refresh?**

Vì trigger chỉ chạy khi UPDATE thật sự được thực hiện. Flush đưa SQL xuống DB, rồi refresh có thể đọc giá trị trigger đã sinh.

**11. Refresh có giống clear không?**

Không. Refresh thay state của managed entity bằng dữ liệu DB; clear tách tất cả managed instances khỏi persistence context, không tự sửa giá trị của các Java objects cũ.

**12. Có nên dùng refresh trong mọi phương thức đọc để tránh cache lỗi thời không?**

Không. Điều đó làm tăng truy vấn, có thể ghi đè dirty state và không vượt qua transaction isolation. Nên chỉ refresh khi nghiệp vụ thực sự cần đọc lại state.

## 23. Ghi nhớ cốt lõi

**`EntityManager.refresh()` làm mới trạng thái persistent của một entity đang managed bằng dữ liệu database mà transaction hiện tại nhìn thấy.** Vì entity tồn tại trong persistence context và có thể đang chứa thay đổi chưa flush, thao tác này **có thể ghi đè những thay đổi trong bộ nhớ**. Nếu chưa flush, dữ liệu mới trong Java có thể biến mất; nếu đã flush, refresh thường đọc lại chính giá trị đã được ghi trong transaction, nhưng **flush vẫn chưa phải commit**.

Refresh khác `find` (tìm và dùng identity map), `flush` (đẩy SQL xuống database), `clear`/`detach` (tách entity khỏi context) và `merge` (sao chép state vào managed instance). Khi quan hệ bật `CascadeType.REFRESH` hoặc `ALL`, thao tác làm mới còn có thể ảnh hưởng entity liên quan. Khi dữ liệu do transaction khác cập nhật, refresh vẫn chịu **transaction isolation, locking và version**.

Hãy coi refresh là một **quyết định thay thế state hiện tại bằng state database**, không phải thao tác kiểm tra hay lưu tự động. Trước khi gọi nó, cần biết: **entity có managed không, đang có dirty changes cần giữ không, có flush/auto-flush xảy ra chưa, transaction đang nhìn thấy phiên bản database nào và refresh có cascade đến đâu**. Đó là nền tảng để sử dụng Persistence Context an toàn mà không vô tình làm mất thay đổi nghiệp vụ.
