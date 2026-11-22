# Xử lý entity trong ngữ cảnh bị cũ sau thao tác hàng loạt

## 1. Tình huống cốt lõi: database đã đổi nhưng entity Java vẫn giữ giá trị cũ

Trong Jakarta Persistence (JPA), các thao tác cập nhật một entity đang được quản lý thường đi qua **persistence context** và cơ chế **dirty checking**. Nhưng khi dùng **truy vấn thay đổi hàng loạt** (*bulk update/bulk delete*), JPA gửi một lệnh tác động trực tiếp tới nhiều hàng trong database và **không đồng bộ lại từng instance entity đang managed** trong bộ nhớ.

Ví dụ, ứng dụng đã tải một sản phẩm:

```java
Product product = em.find(Product.class, 10L);

System.out.println(product.getStatus()); // ACTIVE
```

Sau đó cùng transaction thực thi:

```java
int changed = em.createQuery(
        "UPDATE Product p " +
        "SET p.status = :archived " +
        "WHERE p.id = :id"
    )
    .setParameter("archived", ProductStatus.ARCHIVED)
    .setParameter("id", 10L)
    .executeUpdate();
```

Dù hàng `products.id = 10` trong database có thể đã chuyển sang `ARCHIVED`, biến Java `product` **không tự đổi trạng thái**:

```java
System.out.println(changed);             // Thường là 1.
System.out.println(product.getStatus());  // Vẫn có thể là ACTIVE.
System.out.println(em.contains(product)); // true.
```

Đây là trọng tâm của bài học: **entity vẫn managed nhưng trạng thái của nó có thể đã cũ so với database**. Ta gọi đây là *stale managed entity* hoặc *persistence context không đồng bộ với thao tác hàng loạt*.

Nếu code tiếp tục sử dụng entity này để tính toán, kiểm tra điều kiện nghiệp vụ hay thực hiện update khác, ứng dụng có thể ra quyết định sai. Nếu còn thay đổi chưa được xử lý, các thao tác flush về sau thậm chí có thể xung đột hoặc ghi đè thay đổi trước đó.

Bài này tập trung vào cách:

- Hiểu vì sao bulk DML bỏ qua state của entity managed.
- Phân biệt giá trị trong bộ nhớ, giá trị đã `flush` và giá trị đã `commit`.
- Chọn đúng `flush`, `refresh`, `clear`, `detach` hoặc persistence context mới.
- Xử lý bulk `UPDATE`, `DELETE` bằng JPQL, Criteria API, native SQL.
- Không làm mất những thay đổi pending trong context.
- Bảo vệ optimistic locking và lifecycle semantics.
- Sử dụng Spring Data JPA `@Modifying` an toàn.
- Kiểm thử kết quả bằng một lượt đọc độc lập và xử lý concurrency.

## 2. Bức tranh tổng quan: hai con đường cập nhật

### 2.1. Cập nhật qua managed entity

```java
Product product = em.find(Product.class, 10L);
product.changeStatus(ProductStatus.ARCHIVED);

// Tại flush/commit, ORM xử lý state thay đổi.
em.flush();
```

Dòng thao tác:

```text
Product Java (managed)
         |
         | changeStatus(...)
         v
Persistence Context
         |
         | dirty checking
         v
SQL UPDATE do ORM tạo
         |
         v
Database
```

Provider có cơ hội xử lý theo metadata entity: thuộc tính thay đổi, version, callback, converter và những cơ chế ORM liên quan.

### 2.2. Cập nhật bằng bulk JPQL

```java
em.createQuery(
    "UPDATE Product p SET p.status = :status " +
    "WHERE p.category.id = :categoryId"
).setParameter("status", ProductStatus.ARCHIVED)
 .setParameter("categoryId", 7L)
 .executeUpdate();
```

Luồng thao tác:

```text
JPQL bulk UPDATE
         |
         | executeUpdate()
         v
SQL UPDATE nhiều hàng
         |
         v
Database
         |
         X  Không tự đi qua từng managed Product
         |
Persistence Context có thể giữ state cũ
```

Provider không cần tải từng Product rồi gọi setter. Vì vậy bulk update có thể tiết kiệm số round-trip và số entity đưa vào bộ nhớ, nhưng đổi lại caller phải chịu trách nhiệm về **sự không nhất quán với persistence context**.

### 2.3. Bảng đối chiếu

| Tiêu chí | Sửa managed entity | Bulk UPDATE/DELETE |
|---|---|---|
| Cách tác động | Sửa instance Java rồi flush | Truy vấn DML tác động trực tiếp DB |
| Có cần tải từng entity? | Thường có | Không |
| Dirty checking | Có | Không dùng để quyết định các hàng bulk thay đổi |
| Tự đồng bộ managed instances cũ? | Những instance được sửa vẫn phản ánh thay đổi | **Không bảo đảm; thường vẫn cũ** |
| `@PreUpdate`, `@PreRemove` | Theo lifecycle entity tương ứng | Không chạy trên từng hàng bulk |
| Cascade/remove/orphanRemoval | Theo thao tác entity và mapping | Không tự áp dụng trên từng hàng bulk |
| `@Version` | ORM thường thực hiện kiểm tra/cập nhật version | Bulk DML chuẩn **không tự xử lý version** |
| Khả năng xử lý rất nhiều hàng | Có thể tốn tải entity và memory | Thường hiệu quả hơn nếu phép cập nhật đồng nhất |
| Nguy cơ state stale | Thấp hơn khi chỉ thay đổi qua cùng context | **Cao khi có entity đã loaded** |

**Không có lựa chọn luôn tốt nhất.** Bulk DML phù hợp những thay đổi hàng loạt đơn giản, nhưng không phải phép thay thế cho mọi thao tác domain qua entity.

## 3. Entity và dữ liệu mẫu

Ta dùng một catalog sản phẩm. Các sản phẩm có trạng thái và giá, có timestamp tạo, có version để minh họa optimistic locking.

### 3.1. Enum

```java
package com.example.catalog.domain;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
```

### 3.2. Entity Product

```java
package com.example.catalog.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "product_name", nullable = false)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        name = value;
    }

    public void changeStatus(ProductStatus value) {
        status = Objects.requireNonNull(value);
    }

    public void changePrice(BigDecimal value) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        unitPrice = value;
    }
}
```

### 3.3. Schema SQL minh họa

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(255) NOT NULL UNIQUE,
    product_name VARCHAR(255) NOT NULL,
    unit_price NUMERIC(14,2) NOT NULL
        CHECK (unit_price >= 0),
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    row_version BIGINT NOT NULL
);

CREATE INDEX ix_products_status_created
    ON products(status, created_at);
```

Cú pháp DDL ở đây tương thích về ý tưởng với PostgreSQL; type/cú pháp thực tế có thể thay đổi theo hệ quản trị và dialect. JPQL sử dụng **tên entity `Product` và thuộc tính `status`**, không sử dụng tên cột `row_version` trong đường dẫn Java.

### 3.4. Dữ liệu giả định

| ID | SKU | Status | Price | Version |
|---:|---|---|---:|---:|
| 10 | KB-010 | ACTIVE | 890000 | 2 |
| 11 | MS-011 | ACTIVE | 390000 | 0 |
| 12 | USB-012 | DRAFT | 160000 | 1 |
| 13 | PAD-013 | ACTIVE | 120000 | 3 |

Giả sử `Product` ID 10 đang nằm trong persistence context và mang giá trị `ACTIVE`. Một bulk update đổi tất cả ACTIVE thành ARCHIVED sẽ ảnh hưởng hàng 10, 11, 13 ở database; riêng instance managed ID 10 có thể **vẫn mang ACTIVE**.

Các ví dụ sau giả định `EntityManager em` hợp lệ, có transaction phù hợp khi thực thi DML.

## 4. Persistence context lưu gì và vì sao trở nên cũ?

### 4.1. Cấp phát entity identity

Khi gọi:

```java
Product product = em.find(Product.class, 10L);
```

persistence context quản lý một entity có identity gồm **loại entity và khóa chính**. Trong cùng context, nếu tìm lại Product 10:

```java
Product again = em.find(Product.class, 10L);
System.out.println(product == again); // true.
```

Đây là **first-level cache (L1)** hoặc identity map. Nó bảo đảm một persistent identity không được biểu diễn bởi hai managed object khác nhau trong cùng context.

### 4.2. Bulk DML không cập nhật từng object Java

```java
em.createQuery(
    "UPDATE Product p " +
    "SET p.status = :newStatus " +
    "WHERE p.status = :oldStatus"
).setParameter("newStatus", ProductStatus.ARCHIVED)
 .setParameter("oldStatus", ProductStatus.ACTIVE)
 .executeUpdate();
```

Lệnh UPDATE tác động hàng database, nhưng `product` đã loaded không nhất thiết nhận được lời gọi setter hay state hydration mới.

```text
Trước bulk:
  Persistence context: Product#10.status = ACTIVE
  Database:            Product#10.status = ACTIVE

Sau bulk:
  Persistence context: Product#10.status = ACTIVE (stale)
  Database:            Product#10.status = ARCHIVED
```

### 4.3. `contains()` true không chứng minh state mới

```java
System.out.println(em.contains(product)); // true.
```

`em.contains(product)` chỉ cho biết instance còn được context quản lý. Nó không kiểm tra database và không cho biết object có đồng bộ với kết quả DML mới nhất không.

Kể cả `em.contains(product) == true`, giá trị trong object có thể khác hàng database vì:

- Bulk JPQL/Criteria UPDATE.
- Native SQL UPDATE.
- Stored procedure thay đổi bảng.
- Transaction khác đã commit thay đổi.
- Trigger hoặc tác vụ ngoài ORM.

### 4.4. `find()` ngay sau bulk có thể vẫn lấy L1

```java
Product again = em.find(Product.class, 10L);

System.out.println(again == product); // true.
```

Nếu context vẫn có Product 10 managed, `find()` có thể trả instance đó mà không bắt buộc reload toàn bộ trạng thái từ database.

**Không dùng một lần `find()` trong cùng context để chứng minh bulk UPDATE vừa thay đổi đúng giá trị.**

## 5. Bulk JPQL UPDATE: ví dụ từng bước

### 5.1. Bắt đầu transaction

Ví dụ Java SE với `RESOURCE_LOCAL`:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Product product = em.find(Product.class, 10L);

    System.out.println(product.getStatus()); // ACTIVE.

    int affected = em.createQuery(
            "UPDATE Product p " +
            "SET p.status = :archived " +
            "WHERE p.status = :active"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("active", ProductStatus.ACTIVE)
        .executeUpdate();

    System.out.println(affected);            // Ví dụ: 3.
    System.out.println(product.getStatus());  // Có thể vẫn ACTIVE.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Phải import `jakarta.persistence.EntityTransaction`. Với Spring/JTA, dùng transaction do framework/container quản lý thay vì gọi `getTransaction().begin()`.

### 5.2. `executeUpdate()` trả gì?

`Query.executeUpdate()` trả về một `int` biểu thị số entity/hàng bị tác động theo semantics của câu bulk query và provider. Đây không phải danh sách các entity đã thay đổi.

```java
int affected = query.executeUpdate();
```

Không suy ra ngay các object nào đã bị sửa chỉ từ con số 3, và không suy ra những instance Java đã được cập nhật. Đối với inheritance, mapping nhiều bảng hoặc native SQL, số lượng statement/hàng vật lý có thể khác với cách đếm entity logic mà JPA định nghĩa.

### 5.3. Bulk có thể thay nhiều thuộc tính

```jpql
UPDATE Product p
SET p.status = :archived,
    p.unitPrice = :clearancePrice
WHERE p.status = :active
```

Đây là một lệnh DML được database thực thi theo điều kiện, không phải vòng lặp `Product.changeStatus()` và `Product.changePrice()`.

Nếu domain method kiểm tra giá hoặc ghi audit event, bulk DML **không tự gọi những method đó**. Database constraint vẫn có hiệu lực nhưng không thay thế mọi validation/business invariant ở tầng Java.

### 5.4. `UPDATE` không trả entity list

```java
em.createQuery("UPDATE Product p SET ...")
  .getResultList(); // Không đúng API cho bulk UPDATE.
```

Dùng `executeUpdate()`. Nếu muốn xem entity sau cập nhật, cần truy vấn đọc riêng theo phương án xử lý stale state được thiết kế rõ.

## 6. Bulk DELETE: entity có thể đã bị xóa khỏi DB nhưng vẫn managed

### 6.1. Ví dụ

```java
Product oldProduct = em.find(Product.class, 12L);

int deleted = em.createQuery(
        "DELETE FROM Product p WHERE p.id = :id"
    )
    .setParameter("id", 12L)
    .executeUpdate();

System.out.println(deleted);                 // Ví dụ: 1.
System.out.println(em.contains(oldProduct)); // Có thể true.
```

Sau câu DELETE, hàng database có thể không còn tồn tại, nhưng `oldProduct` trong persistence context vẫn là một object Java có các field và identity cũ.

Đây là một tình trạng đặc biệt nguy hiểm vì code có thể tiếp tục xử lý entity “ma”: object vẫn truy cập được nhưng hàng backing của nó đã bị xóa.

### 6.2. `em.refresh()` trên hàng đã xóa

```java
em.refresh(oldProduct);
```

Nếu hàng không còn trong database, provider có thể ném `EntityNotFoundException` hoặc lỗi tương ứng; refresh **không phải một cách tái tạo hàng đã xóa**.

Với bulk DELETE, lựa chọn phổ biến hơn là **clear/detach các entity bị ảnh hưởng**, ngừng sử dụng instance cũ và chỉ tải lại khi cần. Đọc mới bằng `find` sẽ trả `null` nếu hàng không tồn tại theo góc nhìn của transaction/source.

### 6.3. Xóa trực tiếp không gọi cascade REMOVE

```jpql
DELETE FROM Product p WHERE p.status = :archived
```

Không tương đương:

```java
for (Product product : products) {
    em.remove(product);
}
```

Bulk DELETE bỏ qua vòng đời từng entity. Vì vậy:

- `@PreRemove`/`@PostRemove` không được gọi cho từng hàng.
- `CascadeType.REMOVE` không tự được duyệt qua object graph.
- `orphanRemoval` không tự được áp dụng như khi thao tác association.
- Các constraint foreign key của database **vẫn được kiểm tra**.
- DB `ON DELETE CASCADE` nếu đã khai báo có thể hoạt động ở tầng database, khác JPA cascade.

Nếu muốn xóa cha có con và phụ thuộc `@PreRemove` hoặc cascade ORM, phải chọn entity-level removal hoặc tự thiết kế DML/constraint phù hợp.

## 7. Vì sao trạng thái cũ gây lỗi nghiệp vụ?

### 7.1. Quyết định dựa trên status không còn đúng

```java
Product product = em.find(Product.class, 10L); // ACTIVE.

// Một bulk UPDATE vừa chuyển Product 10 thành ARCHIVED.

if (product.getStatus() == ProductStatus.ACTIVE) {
    // Quyết định có thể dựa vào trạng thái stale.
    publishToCatalog(product);
}
```

Lỗi không nhất thiết biểu hiện thành exception. Đây có thể là **bug logic**: Java tiếp tục coi Product đang ACTIVE dù DB đã archive.

### 7.2. Tính toán dựa vào giá cũ

```java
BigDecimal price = product.getUnitPrice();
```

Nếu bulk UPDATE đã giảm giá nhưng object vẫn giữ giá cũ, việc tạo đơn hàng hoặc báo giá từ field này có thể sai.

### 7.3. Flush sau có thể gây xung đột

Giả sử bulk UPDATE đã thay `unitPrice` trong DB. Sau đó code sửa `name` của cùng managed Product rồi flush:

```java
product.rename("Tên mới");
em.flush();
```

Kết quả tùy metadata/provider và SQL UPDATE được tạo:

- Provider có thể chỉ ghi field dirty, giữ giá mới của DB.
- Provider có thể gửi UPDATE chứa nhiều cột, bao gồm `unitPrice` stale, gây **ghi đè không mong muốn**.
- Nếu bulk query đã tăng version đúng cách, ORM flush với version cũ có thể phát hiện conflict và báo optimistic lock failure.
- Nếu bulk query không tăng version, ORM có thể **không biết** có cập nhật khác vừa xảy ra.

Không phụ thuộc vào một tối ưu cụ thể như “ORM luôn update đúng một cột dirty” để bảo đảm an toàn. Nguyên tắc là **không tiếp tục thao tác ghi trên managed state stale**.

### 7.4. Delete rồi flush đối tượng cũ

Nếu hàng đã bị bulk DELETE nhưng một managed instance cùng ID vẫn còn và bị thay đổi, flush sau đó có thể tạo UPDATE không ảnh hưởng hàng nào hoặc gặp optimistic locking/stale row error. Loại lỗi và thời điểm xuất hiện phụ thuộc provider, mapping và transaction.

Ngừng dùng entity stale sau bulk DELETE và đồng bộ lại persistence context bằng chiến lược phù hợp.

## 8. Chiến lược 1 — `flush()` trước khi chạy bulk DML

### 8.1. Vì sao flush trước?

Trong một persistence context có thể có nhiều thay đổi đang chờ:

```java
Product product = em.find(Product.class, 10L);
product.rename("Bàn phím cơ mới");

// Thay đổi tên chưa chắc đã được gửi bằng SQL UPDATE.
```

Nếu chạy bulk DML ngay, database có thể chưa có những thay đổi pending mà câu bulk query kỳ vọng. Đồng thời, nếu sau đó gọi `clear`, các thay đổi chưa flush có thể bị bỏ.

Một thứ tự thận trọng:

```java
em.flush();

int changed = em.createQuery(
        "UPDATE Product p SET p.status = :status " +
        "WHERE p.id IN :ids"
    )
    .setParameter("status", ProductStatus.ARCHIVED)
    .setParameter("ids", List.of(10L, 11L))
    .executeUpdate();
```

### 8.2. Flush nghĩa là gì?

`em.flush()` yêu cầu ORM đồng bộ các thay đổi pending trong persistence context với database **trong transaction hiện tại**.

Nó **không commit**. Nếu transaction rollback, những thay đổi đã flush cũng bị rollback theo quy tắc transactional của database.

### 8.3. Flush trước không sửa stale state sau bulk

```text
Entity edits pending
      |
      | em.flush()
      v
DB nhận thay đổi ORM
      |
      | bulk UPDATE
      v
DB nhận thay đổi hàng loạt
      |
      X managed entity chưa được tự refresh
```

`flush()` giải quyết **vấn đề trước bulk**: đưa thay đổi đang chờ xuống DB. Nó **không** tự kéo giá trị mới do bulk query tạo vào entity managed sau bulk.

### 8.4. Auto flush không thay thế thiết kế rõ ràng

JPA `FlushModeType.AUTO` có quy tắc bảo đảm tính nhất quán khi thực thi query trong transaction, nhưng cách provider quyết định flush cụ thể có thể phụ thuộc query spaces và loại DML. Với use case nhạy cảm, gọi `flush` tường minh trước bulk rồi chọn phương án làm mới/clear sau đó giúp mã dễ lập luận.

Không dùng `FlushModeType.COMMIT` hoặc cơ chế bỏ qua flush chỉ để làm query nhanh hơn khi procedure/bulk query cần đọc state mới từ ORM.

## 9. Chiến lược 2 — `refresh(entity)` sau bulk UPDATE

### 9.1. Làm mới một entity cụ thể

Khi chỉ một hoặc vài managed entity bị ảnh hưởng và cần tiếp tục dùng chính instance đó, có thể refresh:

```java
Product product = em.find(Product.class, 10L);

em.flush();

em.createQuery(
    "UPDATE Product p SET p.status = :status " +
    "WHERE p.id = :id"
).setParameter("status", ProductStatus.ARCHIVED)
 .setParameter("id", 10L)
 .executeUpdate();

em.refresh(product);

System.out.println(product.getStatus()); // ARCHIVED, theo DB hiện thấy.
```

`em.refresh(product)` yêu cầu tải lại state của entity managed từ database. Sau đó có thể tiếp tục dùng `product` nếu transaction và entity vẫn hợp lệ.

### 9.2. Khi nào refresh phù hợp?

- Biết chính xác những entity nào bị ảnh hưởng.
- Số lượng entity cần làm mới nhỏ.
- Entity vẫn tồn tại (bulk **UPDATE**, không phải DELETE).
- Code phía sau cần tiếp tục sử dụng **cùng Java instance**.
- Không có pending changes cần giữ trên entity tại thời điểm refresh.

### 9.3. Giới hạn và rủi ro

`refresh` có thể **ghi đè những thay đổi chưa flush** của entity đó bằng dữ liệu đọc từ database. Nó có thể kích hoạt truy vấn SELECT và chi phí riêng cho từng entity.

Nếu bulk update tác động hàng nghìn Product, refresh từng object có thể gây chi phí lớn; `clear` và truy vấn lại ở một điểm tách công việc thường thích hợp hơn.

`refresh` cũng chịu transaction isolation: nó đọc dữ liệu mà transaction hiện tại nhìn thấy, không cam kết đọc commit mới nhất của transaction khác ở mọi mức isolation.

### 9.4. Không refresh object detached

```java
em.clear();       // product trở thành detached.
em.refresh(product); // Không còn là managed entity hợp lệ.
```

Sau `clear`, muốn sử dụng tiếp thì `em.find(Product.class, id)` để lấy managed instance mới. Không nên gọi `refresh` lên object đã bị detach.

## 10. Chiến lược 3 — `clear()` sau bulk DML

### 10.1. Tách toàn bộ entity khỏi context

```java
em.flush();

int changed = em.createQuery(
        "UPDATE Product p SET p.status = :status " +
        "WHERE p.status = :active"
    )
    .setParameter("status", ProductStatus.ARCHIVED)
    .setParameter("active", ProductStatus.ACTIVE)
    .executeUpdate();

em.clear();

Product fresh = em.find(Product.class, 10L);
```

Sau `clear`:

- Các entity đang managed trước đó trở thành **detached**.
- `em.contains(oldProduct)` trả `false`.
- `find` có thể tạo/tải một managed instance khác.
- Persistence context không giữ các state cũ trước bulk ở cấp L1.
- Những biến Java cũ **không tự đổi giá trị**; chúng vẫn là detached objects mang dữ liệu đã có.

### 10.2. Sơ đồ vòng đời

```text
em.find(Product#10)     --> Object A managed, status=ACTIVE
bulk UPDATE            --> DB status=ARCHIVED
em.clear()             --> Object A detached, vẫn status=ACTIVE
em.find(Product#10)     --> Object B managed, status=ARCHIVED

Object A != Object B
```

Nếu code tiếp tục sử dụng `Object A` để quyết định nghiệp vụ, nó vẫn có dữ liệu cũ. **Clear context không “sửa” giá trị trong những biến Java mà caller đang giữ.**

### 10.3. Rủi ro lớn nhất: mất thay đổi pending

```java
Product other = em.find(Product.class, 11L);
other.rename("Tên đã sửa nhưng chưa flush");

em.clear(); // Thay đổi chưa flush có thể không được lưu.
```

`clear` không tự động gọi `flush` để bảo toàn mọi chỉnh sửa. Các thay đổi chưa đồng bộ có thể biến mất khỏi chu trình dirty checking.

Vì vậy, khi chủ đích clear sau bulk, lựa chọn thông dụng:

```java
em.flush();
executeBulkUpdate();
em.clear();
```

Tuy nhiên, flush **mọi thay đổi pending** trong context, không chỉ những object mục tiêu. Trong một service phức tạp, cần kiểm soát toàn bộ unit of work trước khi chọn cách này.

### 10.4. Clear có phạm vi rộng

`em.clear()` tác động **toàn bộ persistence context**:

```text
Managed Product#10  ---\
Managed Product#11  ----> clear() --> Detached
Managed Customer#2  ---/
Managed Order#8     --/
```

Nếu các đối tượng khác vẫn cần được sửa và commit sau đó, clear có thể làm logic thất bại âm thầm vì các object đã detached.

Không gọi `clear` chỉ vì “mọi bài viết trên mạng đều khuyên” nếu transaction còn cần các managed entities khác. Cân nhắc tách transaction, tạo context riêng hoặc dùng refresh/detach có chọn lọc.

## 11. Chiến lược 4 — `detach(entity)` có chọn lọc

### 11.1. Chỉ loại một entity khỏi context

```java
Product product = em.find(Product.class, 10L);

em.flush();
executeBulkUpdate();

em.detach(product);

Product reloaded = em.find(Product.class, 10L);
```

`detach(product)` chỉ tách instance được chỉ định (cùng các trường hợp cascade DETACH nếu được cấu hình). Nó giúp tránh `clear` tất cả entity.

### 11.2. Không tự động detach toàn bộ hàng bị ảnh hưởng

Nếu query bulk thay đổi 500 Product đã được tải, bạn cần biết những instance nào đang managed và bị ảnh hưởng để detach chính xác. JPA không cung cấp một API portable kiểu **“detach tất cả entity khớp chính xác bulk WHERE này”** mà không cần theo dõi chúng.

Nếu không biết phạm vi object, tạo một persistence context mới/clear ở ranh giới phù hợp sẽ dễ kiểm soát hơn.

### 11.3. Sau detach cần dùng bản mới

```java
Product old = product;
em.detach(old);

Product fresh = em.find(Product.class, old.getId());
```

Đừng dùng `old` như managed sau đó. Thay đổi `old.rename(...)` không tự được flush. Nếu code phải cập nhật Product tiếp, hãy làm việc trên `fresh`.

### 11.4. Detach không xử lý L2 cache

`detach` chỉ thay đổi quan hệ giữa instance và current persistence context. Cache dùng chung giữa các context vẫn là vấn đề riêng, phải xem cache policy của provider khi bulk/native DML có thể làm dữ liệu cũ.

## 12. Bảng chọn giữa refresh, clear, detach và context mới

| Tình huống | Hướng tiếp cận thường phù hợp | Cảnh báo |
|---|---|---|
| Bulk UPDATE một Product còn cần dùng ngay | `flush` trước, bulk, `refresh(product)` | Refresh có thể bỏ pending changes; hàng phải còn |
| Bulk UPDATE vài Product đã biết chính xác | Refresh từng entity hoặc detach/reload có chọn lọc | Chi phí SELECT theo số object |
| Bulk UPDATE hàng nghìn Product | Bulk trong transaction riêng, clear sau hoặc dùng context mới để đọc tiếp | Tránh quản lý số lượng lớn entity cùng lúc |
| Bulk DELETE những entity đang loaded | Không tiếp tục dùng old instances; clear/detach và truy vấn mới | Refresh có thể lỗi vì hàng đã xóa |
| Context có nhiều entity không liên quan đang pending | Không clear ngay; xem xét tách unit of work | Clear có thể làm mất thay đổi |
| Cần kiểm chứng database đã commit | Commit, reader context/transaction mới, query nguồn phù hợp | L1/L2/replica/isolation có thể ảnh hưởng |
| Cần refresh tất cả object trong một long transaction | Thiết kế lại transaction boundary hoặc clear ở điểm an toàn | Không refresh mù quáng khi pending data |
| Muốn chỉ kiểm tra giá trị DB của vài cột | Native scalar query sau flush/commit phù hợp | Scalar không sửa state của entity cũ |

**Không có một API duy nhất luôn đúng.** Hãy bắt đầu bằng câu hỏi: “Sau bulk, những object nào sẽ còn được dùng? Chúng có pending changes không? Có cần giữ cùng instance không?”.

## 13. Spring Data JPA: `@Modifying` và hai cờ quan trọng

### 13.1. Repository bulk UPDATE

Trong Spring Data JPA, truy vấn thay đổi khai báo bằng `@Query` thường kết hợp `@Modifying`:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying
    @Query("""
        UPDATE Product p
        SET p.status = :newStatus
        WHERE p.status = :oldStatus
        """)
    int bulkChangeStatus(
        @Param("oldStatus") ProductStatus oldStatus,
        @Param("newStatus") ProductStatus newStatus
    );
}
```

Các import cần thiết:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
```

Method trả `int` số entity/hàng bị ảnh hưởng theo query, **không trả tập Product đã làm mới**.

### 13.2. `clearAutomatically = true`

```java
@Modifying(clearAutomatically = true)
@Query("""
    UPDATE Product p SET p.status = :status
    WHERE p.id IN :ids
    """)
int bulkArchive(
    @Param("ids") Collection<Long> ids,
    @Param("status") ProductStatus status
);
```

Spring Data JPA có thể tự gọi `EntityManager.clear()` sau khi thực thi modifying query. Mục tiêu là tránh tiếp tục dùng managed entities stale trong persistence context.

Nhưng flag này **không thay đổi giá trị các biến Java cũ**: đối tượng cũ chỉ bị detach.

### 13.3. `flushAutomatically = true`

```java
@Modifying(flushAutomatically = true)
@Query("""
    UPDATE Product p SET p.status = :status
    WHERE p.id IN :ids
    """)
int bulkArchive(...);
```

Spring Data sẽ flush persistence context trước khi chạy modifying query. Điều này giảm rủi ro mất pending changes nếu sau đó có clear.

### 13.4. Kết hợp cả hai khi thích hợp

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    UPDATE Product p
    SET p.status = :archived
    WHERE p.id IN :ids
    """)
int archiveIds(
    @Param("ids") Collection<Long> ids,
    @Param("archived") ProductStatus archived
);
```

Luồng được mong đợi:

```text
Pending entity modifications
      |
      | flushAutomatically
      v
JPA flush
      |
      | @Query UPDATE
      v
Database bulk UPDATE
      |
      | clearAutomatically
      v
All managed entities detached
```

Đây là cách tiện lợi nhưng không nên đặt mặc định ở mọi repository method không suy nghĩ. Clear toàn context có thể ảnh hưởng các entity khác đang được service dùng trong cùng transaction.

### 13.5. Chữ ký thực tế với @Transactional

```java
@Service
public class ProductMaintenanceService {

    private final ProductRepository repository;

    public ProductMaintenanceService(
            ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int archiveProducts(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return 0;
        }

        return repository.archiveIds(
            ids, ProductStatus.ARCHIVED);
    }
}
```

Service cung cấp ranh giới transaction. Lưu ý: nếu repository tự clear context, các managed entity mà service khác đang giữ reference trong cùng transaction cũng trở thành detached.

### 13.6. `@Modifying` không tự bật version check hay lifecycle callbacks

Dù thêm `flushAutomatically` và `clearAutomatically`, bulk JPQL vẫn bỏ qua việc xử lý từng entity: `@Version` không tự tăng theo mỗi hàng, callback không được gọi cho từng bản ghi, cascade entity không chạy.

Hai cờ chỉ giúp **quản lý thời điểm flush và trạng thái persistence context**, không thay đổi bản chất bulk DML.

### 13.7. Repository method có tên delete khác với @Query bulk delete

Các phương thức repository suy ra từ tên như `deleteByStatus(...)` có thể có semantics khác với một truy vấn `DELETE` trực tiếp, tùy phương thức và cách Spring Data triển khai. Không kết luận rằng mọi method tên “delete” đều là bulk DML.

Chủ đề này tập trung vào **`@Modifying @Query("DELETE ...")`** hoặc `EntityManager.executeUpdate()`, là những đường bulk rõ ràng.

## 14. Optimistic locking: chỗ dễ bị bỏ sót nhất

### 14.1. `@Version` trong entity-level update

Entity có:

```java
@Version
private long version;
```

Khi sửa managed entity, provider thường dùng version để phát hiện một hàng đã bị thay đổi bởi transaction khác và tăng version khi cập nhật thành công.

Hình dung SQL ORM:

```sql
UPDATE products
SET product_name = ?, row_version = row_version + 1
WHERE id = ? AND row_version = ?;
```

Đây là hình minh họa; SQL thực tế phụ thuộc provider.

### 14.2. Bulk UPDATE không tự tăng version

```jpql
UPDATE Product p
SET p.status = :archived
WHERE p.status = :active
```

Đây là bulk update chuẩn. **Không mặc định nó tự tăng `@Version`**, cũng không mặc định nó so sánh version của từng entity trước khi ghi.

Hệ quả: transaction khác đang giữ Product cũ có thể không phát hiện bulk change nếu version không đổi và tiếp tục ghi từ state stale.

### 14.3. Tăng version có chủ đích trong bulk

Với numeric version, có thể thiết kế:

```jpql
UPDATE Product p
SET p.status = :archived,
    p.version = p.version + 1
WHERE p.status = :active
```

Cách này yêu cầu mapping và database hỗ trợ phép cộng numeric tương ứng. Nó giúp đánh dấu version của các hàng thay đổi, khiến managed entity cũ với version cũ không thể update thành công nếu ORM thực hiện optimistic check đúng.

Nhưng **việc tăng version một mình chưa làm mới entity managed**. Sau bulk, context vẫn phải clear/refresh/reload phù hợp.

### 14.4. Một hàng với expected version

Khi use case cần cập nhật Product cụ thể nếu version vẫn đúng:

```java
int updated = em.createQuery(
        "UPDATE Product p " +
        "SET p.status = :archived, " +
        "    p.version = p.version + 1 " +
        "WHERE p.id = :id AND p.version = :expectedVersion"
    )
    .setParameter("archived", ProductStatus.ARCHIVED)
    .setParameter("id", productId)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (updated != 1) {
    throw new OptimisticLockException(
        "Product đã đổi hoặc không còn tồn tại");
}
```

Cần import `jakarta.persistence.OptimisticLockException`. Đoạn này mô phỏng **compare-and-set** ở database.

Điều kiện `WHERE p.version = :expectedVersion` có ý nghĩa khác với chỉ “tăng version cho mọi hàng”:

- Nếu version đúng, hàng được sửa và tăng version.
- Nếu version sai, không có hàng nào khớp.
- Caller xử lý conflict theo domain và transaction policy.

### 14.5. Cần xử lý persistence context sau versioned bulk

Nếu `Product` cùng ID đã được load trước bulk, object có thể vẫn giữ `version` cũ. Flush tiếp có thể báo optimistic lock error; đó là cảnh báo tốt hơn ghi đè dữ liệu, nhưng vẫn là dấu hiệu phải quản lý lại context.

Tốt nhất là kết thúc transaction hoặc refresh/clear đúng lúc, thay vì cố dùng lại managed entity stale.

### 14.6. Không tự viết version logic cho mọi loại version

Ví dụ `p.version = p.version + 1` phù hợp một numeric version. Một số mapping dùng timestamp hoặc cơ chế version khác; cần chiến lược tương ứng, không áp dụng cộng 1 một cách máy móc.

Nếu bulk operation cần audit, vòng đời entity và concurrency phức tạp, phương án tải rồi cập nhật entity-level có thể an toàn và dễ duy trì hơn.

## 15. JPA lifecycle callbacks, cascade và auditing

### 15.1. Callback không chạy cho từng hàng bulk

Entity có:

```java
@PreUpdate
void beforeUpdate() {
    // Điều chỉnh audit hoặc invariant.
}
```

Khi một bulk query trực tiếp cập nhật hàng, JPA không tải từng entity để gọi callback. Không dựa vào `@PreUpdate` để cập nhật `updatedAt` hay phát domain event cho từng bản ghi bulk.

### 15.2. Auditing cần được xử lý trực tiếp

Nếu nghiệp vụ yêu cầu timestamp:

```jpql
UPDATE Product p
SET p.status = :archived,
    p.updatedAt = :changedAt
WHERE p.status = :active
```

Ví dụ giả định entity có field `Instant updatedAt` được mapping. Tham số `changedAt` do service tạo từ clock đáng tin cậy. Không chỉ dựa vào entity listener vốn không chạy cho bulk.

Với audit log theo từng hàng, có thể cần:

- Database trigger phù hợp.
- Câu DML có thêm audit fields.
- Bảng audit được ghi có chủ đích.
- Quy trình batch tạo event/reconciliation.
- Phương án entity-level khi callback là yêu cầu bắt buộc.

### 15.3. Cascade/`orphanRemoval` không được áp dụng

Bulk DELETE một `PurchaseOrder` không tự gọi `CascadeType.REMOVE` tới `OrderLine`, dù mapping JPA có cascade. Database FK có thể chặn DELETE nếu còn con, hoặc áp dụng `ON DELETE CASCADE` nếu schema cho phép.

Không nhầm cascade JPA với ràng buộc và trigger ở tầng database. Để xóa theo domain graph, cần chọn kỹ thuật thỏa đúng ràng buộc vòng đời.

### 15.4. Soft delete cũng có thể bị bypass

Nếu entity sử dụng một cơ chế soft delete dựa trên entity listener hoặc annotation riêng của provider, một bulk DELETE trực tiếp có thể không đi qua đường chuyển `deleted=true` như mong đợi.

Khi dùng soft-delete, nên xác định rõ query bulk là:

```jpql
UPDATE Product p SET p.deleted = TRUE
WHERE p.id IN :ids
```

hay là DELETE vật lý, và đảm bảo các query đọc tôn trọng chính sách lọc. Các thuộc tính `deleted` và provider annotations ở đây chỉ mang tính minh họa, không xuất hiện trong entity mẫu ban đầu.

## 16. Criteria API bulk UPDATE/DELETE vẫn tạo stale entity

### 16.1. CriteriaUpdate

JPA Criteria API hỗ trợ bulk update:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(
        p.<ProductStatus>get("status"),
        ProductStatus.ARCHIVED
    )
    .where(
        cb.equal(
            p.get("status"),
            ProductStatus.ACTIVE
        )
    );

int changed = em.createQuery(update).executeUpdate();
```

Cần import `jakarta.persistence.criteria.CriteriaBuilder`, `CriteriaUpdate` và `Root`.

**`CriteriaUpdate` không biến bulk operation thành entity-level update.** Nó vẫn có cùng đặc tính bỏ qua các instance managed, callbacks và việc tự xử lý version.

### 16.2. CriteriaDelete

```java
CriteriaDelete<Product> delete =
    cb.createCriteriaDelete(Product.class);

Root<Product> root = delete.from(Product.class);

delete.where(
    cb.equal(
        root.get("status"),
        ProductStatus.ARCHIVED
    )
);

int removed = em.createQuery(delete).executeUpdate();
```

Sau delete, các Product ARCHIVED đã loaded có thể vẫn tồn tại trong L1 cho tới khi detach/clear/context kết thúc.

### 16.3. Vì sao Criteria không tự sửa persistence context?

JPQL bulk DML và Criteria bulk DML chỉ khác **cách biểu diễn/trình bày query**:

```text
JPQL String UPDATE --> executeUpdate() --> DB
CriteriaUpdate    --> executeUpdate() --> DB
```

Chúng cùng có semantics bulk. Đừng nghĩ vì Criteria API là Java type-safe thì nó tự gọi setter và dirty checking cho từng entity.

### 16.4. Giới hạn cú pháp bulk Criteria

Một bulk update/delete theo Criteria có một root entity cần sửa/xóa. Các join trực tiếp kiểu SELECT không thể tùy ý dùng như trong `CriteriaQuery`. Khi cần điều kiện dựa trên bảng liên quan, có thể phải dùng subquery hoặc database-specific SQL.

Tuy nhiên, việc chọn cách diễn đạt query không thay đổi yêu cầu **đồng bộ lại state sau bulk**.

## 17. Native SQL và stored procedure cũng gây lệch context

### 17.1. Native UPDATE

```java
int changed = em.createNativeQuery(
        "UPDATE products " +
        "SET status = ?1 " +
        "WHERE id = ?2"
    )
    .setParameter(1, "ARCHIVED")
    .setParameter(2, 10L)
    .executeUpdate();
```

Ở đây SQL dùng tên bảng/cột vật lý. Vì `@Enumerated(EnumType.STRING)`, chuỗi `ARCHIVED` là giá trị lưu trữ theo mapping ví dụ.

Native UPDATE không tự cập nhật entity Product 10 đang managed trong context.

### 17.2. Stored procedure

```java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("archive_old_products");

sp.execute();
```

Giả sử procedure thực sự tồn tại và cập nhật bảng `products`. Tương tự native UPDATE, provider không tự biết tất cả thay đổi được procedure tạo và không tự refresh từng entity liên quan. Với procedure có OUT hoặc nhiều result sets cần xử lý contract riêng.

### 17.3. Thay đổi từ trigger

Database trigger có thể cập nhật cột khác khi câu bulk DML chạy. JPA có thể không đọc lại các cột do trigger thay đổi nếu không refresh/reload. Vì vậy state stale có thể liên quan cả:

- Trường được UPDATE trực tiếp.
- Trường do trigger sửa.
- Timestamp/version do database tạo.
- Các bảng liên quan thay đổi bằng trigger.

**Đừng chỉ refresh một field trong object Java**; JPA refresh entity theo mapping/state, còn nếu read model phức tạp thì nên đọc lại dữ liệu cần thiết bằng query phù hợp.

## 18. Bộ nhớ L1, L2 cache và query cache

### 18.1. L1 là vấn đề trực tiếp

`EntityManager.clear()` chỉ xóa các managed entries khỏi persistence context hiện tại; nó làm entity trở thành detached.

### 18.2. Shared L2 cache là vấn đề riêng

Một số provider bật second-level cache dùng chung giữa các context. Bulk JPQL do provider tạo có thể có cơ chế invalidation cache đặc thù, còn native SQL hoặc stored procedure có thể làm provider không biết bảng nào đã thay đổi.

Không mặc định một lần `clear()` đã loại mọi stale value trong shared cache.

### 18.3. `EntityManagerFactory.getCache()`

JPA có cache API:

```java
Cache cache = emf.getCache();

cache.evict(Product.class, 10L);
```

Hoặc khi phù hợp:

```java
cache.evict(Product.class);
```

Cần import `jakarta.persistence.Cache`. `evict(Product.class, id)` loại một entity identity khỏi shared cache nếu cache provider có entry tương ứng. `evict(Product.class)` loại các entry loại Product khỏi shared cache.

**Evict L2 không detach entity đã managed trong L1.** Nếu đang giữ `product` trong EntityManager hiện tại, vẫn cần refresh/clear/detach riêng.

### 18.4. Query result cache

Một số provider có query cache riêng ngoài L2 entity cache. Khi native SQL cập nhật dữ liệu, query cache có thể chưa được invalidated theo cách mong đợi nếu provider không biết query spaces. Cần kiểm tra provider-specific invalidation policy, không chỉ gọi một JPA Cache API rồi giả định mọi cache biến mất.

### 18.5. Read-after-write

Muốn đọc dữ liệu vừa sửa một cách chắc chắn, hãy phân biệt:

1. **Cùng context:** getter có thể đọc L1 stale.
2. **Context mới trong cùng transaction:** tránh L1 cũ nhưng có thể chịu shared cache/isolation.
3. **Transaction mới sau commit:** đọc committed state theo isolation/source.
4. **Read replica:** có thể chậm do replication lag.
5. **Native scalar/JDBC trên primary:** gần với giá trị hàng DB hơn việc lấy entity cũ, nhưng vẫn theo transaction snapshot.

Không có một lệnh JPA magic bảo đảm mọi lớp cache, replica và transaction đồng bộ tức thì.

## 19. Trường hợp nguy hiểm: flush và clear đặt sai thứ tự

### 19.1. Sai: clear trước flush làm mất pending edits

```java
Product first = em.find(Product.class, 10L);
first.rename("Tên mới chưa được flush");

int changed = executeBulkUpdate();

em.clear(); // Có thể mất rename pending.
```

Nếu query/provider không tự flush thay đổi trước đó, `clear` làm entity detached và rename có thể không được ghi.

### 19.2. Đúng về thứ tự cơ bản

```java
first.rename("Tên mới");

// Nếu muốn bảo toàn thay đổi trong context:
em.flush();

int changed = executeBulkUpdate();

em.clear();
```

Đây là một **quy trình thông dụng**, không phải bảo đảm nghiệp vụ tự động. Nếu bulk cũng ghi lên field vừa được flush, giá trị cuối ở DB tùy điều kiện và thứ tự bulk. Đó là thiết kế update semantics cần chủ đích.

### 19.3. Sai: clear sau khi đã tải đối tượng sẽ tiếp tục dùng

```java
Product product = em.find(Product.class, 10L);
executeBulkUpdate();
em.clear();

product.changeStatus(ProductStatus.ACTIVE);

// product đã detached; sửa này không tự được flush.
```

Sau clear, phải dùng managed instance mới:

```java
Product current = em.find(Product.class, 10L);
current.changeStatus(ProductStatus.ACTIVE);
```

Đừng gọi `em.merge(product)` chỉ để “cứu” một reference stale; merge object stale có thể sao chép các thuộc tính cũ trở lại DB/context và phá hỏng kết quả bulk.

### 19.4. Sai: refresh trước bulk

```java
em.refresh(product);
executeBulkUpdate();
```

Refresh trước bulk chỉ đảm bảo entity được đọc lại tại thời điểm đó. Sau bulk, chính nó lại có nguy cơ stale. Nếu cần state sau bulk, refresh **sau** bulk (và sau khi xử lý pending changes) hoặc tải lại trong context mới.

### 19.5. Sai: xem `em.flush()` sau bulk là reload

```java
executeBulkUpdate();
em.flush();
System.out.println(product.getStatus());
```

Flush đồng bộ thay đổi **từ context xuống DB**; nó không kéo state bulk từ DB lên. Ngược lại, flush sau bulk khi context đã stale có thể tạo nguy cơ ghi đè, nên phải xét thứ tự và phương án làm mới.

## 20. Chia transaction để cô lập bulk operation

### 20.1. Dùng transaction riêng cho maintenance

Thay vì tạo nhiều entity managed rồi bulk update chúng trong cùng transaction, một job maintenance có thể được thiết kế:

```text
Transaction A
   |
   +-- bulk UPDATE products
   +-- commit
   |
Transaction B mới
   |
   +-- SELECT / find Product
   +-- tiếp tục xử lý dữ liệu mới
```

Khi mỗi transaction gắn với persistence context riêng theo cách triển khai, context sau không giữ object stale từ trước.

### 20.2. Đừng dựa hoàn toàn vào transaction boundary nếu context extended

Với transaction-scoped EntityManager thường gặp, kết thúc transaction và dùng một context mới tránh L1 cũ. Nhưng một `extended persistence context` có thể tồn tại qua nhiều transaction; lúc đó **commit không tự có nghĩa clear mọi managed entity**.

Cần hiểu scope thật của EntityManager/provider, không chỉ dựa trên annotation `@Transactional`.

### 20.3. Spring propagation

Một service có thể gọi một batch operation trong transaction độc lập khi nghiệp vụ cho phép:

```java
@Service
public class MaintenanceJob {

    private final BulkArchiveService bulkService;

    public MaintenanceJob(BulkArchiveService bulkService) {
        this.bulkService = bulkService;
    }

    public void run() {
        bulkService.archiveEligibleProducts();
        // Đọc lại bằng service/context phù hợp sau commit.
    }
}
```

`BulkArchiveService` là bean khác có `@Transactional` và method thực thi bulk. Nếu cần `REQUIRES_NEW`, phải hiểu nó tạo transaction mới, ảnh hưởng commit/rollback và có thể tốn connection; không dùng chỉ để né stale context mà bỏ qua nguyên tử nghiệp vụ.

### 20.4. Không dùng transaction mới cho những thay đổi cần atomic chung

Nếu một nghiệp vụ bắt buộc tạo đơn và điều chỉnh trạng thái Product trong **cùng atomic unit**, việc tách transaction có thể phá tính nhất quán. Khi đó cần xử lý context trong cùng transaction bằng flush/refresh/clear có chủ đích hoặc chọn entity-level update.

**Ranh giới transaction phải phục vụ bất biến nghiệp vụ, không chỉ tiện xử lý cache.**

## 21. Bulk update có điều kiện và tránh tác động nhầm hàng

### 21.1. Query phải có WHERE đúng nghĩa

```jpql
UPDATE Product p
SET p.status = :archived
```

Không có `WHERE` sẽ tác động **tất cả Product**. Bulk DML có mức ảnh hưởng lớn, nên service phải kiểm tra input và review điều kiện cẩn thận.

### 21.2. Giới hạn bằng ID và trạng thái

```jpql
UPDATE Product p
SET p.status = :archived
WHERE p.id IN :ids
  AND p.status = :active
```

Giúp tránh archive lại các Product không ở trạng thái mong muốn. Cần xử lý danh sách `ids` rỗng tại Java; behavior collection rỗng trong `IN` không portable giữa provider/database.

### 21.3. Tập ID rỗng

```java
public int archive(
        EntityManager em, Collection<Long> ids) {

    if (ids == null) {
        throw new IllegalArgumentException("ids không được null");
    }

    if (ids.isEmpty()) {
        return 0;
    }

    return em.createQuery(
            "UPDATE Product p " +
            "SET p.status = :archived " +
            "WHERE p.id IN :ids " +
            "AND p.status = :active"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("ids", ids)
        .setParameter("active", ProductStatus.ACTIVE)
        .executeUpdate();
}
```

Ví dụ chỉ trình bày điều kiện query; caller vẫn cần transaction và kế hoạch xử lý state stale. Đừng truyền `null` để yêu cầu “bỏ filter” hoặc list rỗng để kỳ vọng SQL tạo `IN ()` có semantics đồng nhất.

### 21.4. Kiểm tra affected count

```java
int affected = archive(em, List.of(10L, 11L));

if (affected == 0) {
    // Có thể các ID không tồn tại hoặc đã không còn ACTIVE.
}
```

Nếu chỉ kỳ vọng cập nhật đúng một entity, số 0 hoặc lớn hơn 1 có thể là tín hiệu bất thường. Với bulk theo nhiều ID, số affected nhỏ hơn số ID không nhất thiết là lỗi: một số ID có thể không tồn tại hoặc không đáp ứng điều kiện.

## 22. Bulk DELETE và ràng buộc khóa ngoại

### 22.1. Vấn đề cha–con

Giả sử `Order` có nhiều `OrderLine`, database có FK:

```sql
FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
```

Bulk DELETE Order:

```jpql
DELETE FROM PurchaseOrder o
WHERE o.status = :cancelled
```

không đi qua từng `em.remove(order)` nên không tự thực hiện `CascadeType.REMOVE` trên các line. Nếu FK không cho xóa cha khi còn con, SQL DELETE có thể thất bại.

### 22.2. Phương án xử lý

Tùy domain:

- Dùng entity-level removal khi cần lifecycle, callbacks, cascade.
- Xóa các child bằng DML có điều kiện trước rồi xóa parent trong **cùng transaction**.
- Dựa vào database `ON DELETE CASCADE` nếu schema và quy tắc nghiệp vụ cho phép.
- Dùng soft-delete thay vì hard-delete.
- Không xóa dữ liệu đã tham chiếu nếu cần audit/giữ lịch sử.

Mỗi lựa chọn có tác động khác nhau tới persistence context và cache. Nếu đã loaded Order/OrderLine, cần xử lý stale state của cả các entity liên quan.

### 22.3. Bulk DELETE có thể va optimistic locking khác biệt

Một `DELETE` trực tiếp không tự đi qua optimistic version check của từng entity. Nếu phải bảo vệ xóa theo version, có thể đưa điều kiện version cho từng entity hoặc chọn entity-level remove với protocol ORM.

Lệnh bulk DELETE chung cho hàng nghìn ID khó xử lý version expected riêng của từng hàng; đây có thể là lý do chọn một workflow khác.

## 23. Đồng thời: bulk DML và transaction khác

### 23.1. Hai transaction cập nhật cùng hàng

```text
Transaction T1:
    load Product#10, version=2, price=890000
    sửa tên (chưa flush)

Transaction T2:
    bulk UPDATE Product#10 price=790000
    commit

Transaction T1:
    flush tên thay đổi, version vẫn=2?
```

Nếu T2 không tăng version, T1 có thể không phát hiện Product vừa bị cập nhật bên ngoài. Tùy SQL ORM, price T2 có thể được giữ hoặc bị ghi đè.

Nếu T2 tăng version, T1 thường phát hiện conflict khi flush theo optimistic locking.

### 23.2. Phát hiện conflict không tự giải quyết conflict

Một `OptimisticLockException` nói rằng state đã lệch khỏi kỳ vọng, không chỉ ra nên lấy giá của T1 hay T2. Service cần rollback và có chiến lược retry/rebase/reject theo nghiệp vụ.

Không retry vô hạn một transaction đã failed. Đọc lại state mới trong context/transaction mới rồi xây lại command nếu retry được phép.

### 23.3. Isolation ảnh hưởng những gì được đọc

Các mức `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` có hành vi snapshot/locking khác nhau theo database. `em.refresh` hay native scalar SELECT sau bulk có thể nhìn thấy các thay đổi của chính transaction, nhưng với thay đổi từ transaction khác thì còn phụ thuộc isolation.

Nếu yêu cầu là “ngay sau bulk commit, user đọc được từ nguồn chính”, cần xác định DB source, cache và transaction đọc. Nếu đọc replica hoặc cache bất đồng bộ, dữ liệu mới có thể chưa sẵn sàng.

### 23.4. Bulk không thay thế constraint

Một bulk update giảm giá cần constraint chống giá âm nếu đó là bất biến. Một bulk delete có thể bị FK cản. Query affected count không thay thế quyền truy cập/authorization hay bảo đảm rằng các trạng thái nghiệp vụ vẫn hợp lệ.

## 24. Tác động lên quan hệ và collection đã loaded

### 24.1. Association có thể stale

Giả sử `Customer.orders` đã được initialized, rồi một bulk DELETE loại nhiều Order trong DB. Collection Java trước đó có thể **vẫn chứa Order đã xóa** hoặc có số lượng khác database.

```text
Managed Customer.orders:
    [Order#1, Order#2, Order#3]

Bulk DELETE Order#2 trong DB

Java collection hiện có:
    [Order#1, Order#2, Order#3] (có thể stale)
```

Không chỉ scalar fields bị stale; **relationship state và initialized collections** cũng phải được xem xét.

### 24.2. Chọn cách làm mới

- Nếu chỉ một root và mapping/provider hỗ trợ thích hợp, cân nhắc refresh và kiểm tra collection state.
- Nếu bulk rộng và có nhiều collections đã loaded, clear/context mới thường dễ dự đoán hơn.
- Với read model, query projection trực tiếp sau commit có thể tránh dựa vào collection cũ.

Các chi tiết reload initialized collections có thể phụ thuộc provider và cascade `REFRESH`; không mặc định refresh một root luôn sửa mọi association trong mọi cấu hình.

### 24.3. Dùng collection Java để xác nhận bulk có thể sai

```java
int before = customer.getOrders().size();
executeBulkDeleteOrders();
int after = customer.getOrders().size();
```

`after` không phải cách portable xác định số Order còn lại trong DB nếu collection đã được load trước bulk. Muốn kiểm tra count mới, dùng query đếm với transaction/context phù hợp hoặc reload relationship.

## 25. Đọc lại giá trị từ DB: entity query hay scalar query?

### 25.1. Entity query trong cùng context

```java
Product product = em.find(Product.class, 10L);

executeBulkUpdate();

Product again = em.find(Product.class, 10L);
```

`again` có thể là `product` và vẫn stale vì L1 identity map.

### 25.2. Scalar query

```java
Object rawStatus = em.createNativeQuery(
        "SELECT status FROM products WHERE id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();

String statusInDb = (String) rawStatus;
```

Đây là một scalar SQL result, không phải managed Product, nên **không bị việc lấy cùng Java instance từ L1**. Tuy vậy nó vẫn đọc theo snapshot/transaction/DB source hiện tại.

### 25.3. Sau commit với EntityManager mới

```java
EntityManager reader = emf.createEntityManager();

try {
    reader.getTransaction().begin();

    Product after = reader.find(Product.class, 10L);
    ProductStatus status = after.getStatus();

    reader.getTransaction().commit();
} finally {
    reader.close();
}
```

Ví dụ giả định RESOURCE_LOCAL. Mở reader context mới tránh L1 writer cũ, nhưng nếu shared L2 cache được bật và có thể stale, nên xem cache policy/hint hoặc dùng scalar DB query để kiểm chứng hàng vật lý.

### 25.4. Không gộp “đã flush” với “đã commit”

Có ba mức cần phân biệt:

| Mức | Ý nghĩa | Điều chưa được bảo đảm |
|---|---|---|
| Entity đang managed | Java object thuộc context | Giá trị không nhất thiết mới như DB |
| Bulk `executeUpdate` / flush thành công | Database đã nhận DML trong transaction | Giao dịch chưa chắc đã commit |
| Commit thành công + reader mới đọc được | Committed state được quan sát ở nguồn đọc | Replica/cache/snapshot khác vẫn có thể lag |

## 26. Integration test: tái hiện và xử lý stale context

### 26.1. Tạo bộ fixture

Trong DB test, tạo Product ID 10 status ACTIVE và Product ID 11 status ACTIVE. Nếu ID được generate, test nên lưu lại ID sinh ra thay vì hardcode. Các đoạn tiếp theo giả định ID 10 tồn tại để ngắn gọn.

### 26.2. Test tái hiện stale

```java
@Test
void bulkUpdateDoesNotRefreshAlreadyManagedEntity() {
    Product managed = em.find(Product.class, 10L);

    assertEquals(ProductStatus.ACTIVE, managed.getStatus());

    int count = em.createQuery(
            "UPDATE Product p " +
            "SET p.status = :archived " +
            "WHERE p.id = :id"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("id", 10L)
        .executeUpdate();

    assertEquals(1, count);

    // Không dựa vào managed.getStatus() để chứng minh DB đổi.
    // Nó có thể vẫn là ACTIVE.
}
```

Test cần transaction ghi và fixture hợp lệ. Mục tiêu là cho thấy **bulk update không tự sync state vào managed instance**, không phải kiểm chứng commit.

### 26.3. Test refresh

```java
@Test
void refreshReadsBulkUpdatedValueForManagedEntity() {
    Product managed = em.find(Product.class, 10L);

    em.createQuery(
            "UPDATE Product p SET p.status = :archived " +
            "WHERE p.id = :id"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("id", 10L)
        .executeUpdate();

    em.refresh(managed);

    assertEquals(
        ProductStatus.ARCHIVED,
        managed.getStatus()
    );
}
```

Điều kiện: row vẫn tồn tại, transaction/provider và fixture thích hợp. Test cho thấy refresh làm mới managed state theo database mà transaction nhìn thấy.

### 26.4. Test clear và load lại

```java
@Test
void clearDetachesOldEntityAndReloadsFreshOne() {
    Product old = em.find(Product.class, 10L);

    em.createQuery(
            "UPDATE Product p SET p.status = :archived " +
            "WHERE p.id = :id"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("id", 10L)
        .executeUpdate();

    em.clear();

    assertFalse(em.contains(old));

    Product fresh = em.find(Product.class, 10L);
    assertNotSame(old, fresh);

    assertEquals(
        ProductStatus.ARCHIVED,
        fresh.getStatus()
    );
}
```

`old` vẫn có các field cũ; test phải dùng `fresh` cho xử lý mới.

### 26.5. Test chứng minh clear làm mất pending change nếu không flush

Ví dụ kiểm thử có kiểm soát:

1. Load Product 11, đổi `name` nhưng chưa flush.
2. Thực thi bulk query không liên quan Product 11 hoặc cấu hình flush mode/test thích hợp để đảm bảo pending edit chưa được đồng bộ.
3. Gọi `clear`.
4. Trong transaction/reader phù hợp, xác minh `name` không được ghi.

Không mặc định mọi provider đều bỏ qua flush trước bulk, bởi `FlushModeType.AUTO` có thể flush pending changes. Mục tiêu là hiểu rủi ro của **clear khi còn unflushed changes**, không ép mọi provider phải tái hiện một sequence nội bộ giống nhau.

### 26.6. Test sau commit mới chứng minh tính bền vững

```java
EntityManager writer = emf.createEntityManager();

try {
    writer.getTransaction().begin();

    writer.createQuery(
            "UPDATE Product p SET p.status = :archived " +
            "WHERE p.id = :id"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("id", 10L)
        .executeUpdate();

    writer.getTransaction().commit();
} catch (RuntimeException ex) {
    if (writer.getTransaction().isActive()) {
        writer.getTransaction().rollback();
    }
    throw ex;
} finally {
    writer.close();
}

EntityManager reader = emf.createEntityManager();

try {
    reader.getTransaction().begin();

    String status = (String) reader.createNativeQuery(
            "SELECT status FROM products WHERE id = ?1"
        )
        .setParameter(1, 10L)
        .getSingleResult();

    assertEquals("ARCHIVED", status);

    reader.getTransaction().commit();
} finally {
    reader.close();
}
```

Ví dụ giả định database nguồn chính và môi trường RESOURCE_LOCAL; thực tế cần xử lý rollback reader khi có lỗi. Đây là **một lượt đọc độc lập sau commit** nhằm phân biệt thành công của DML với state của context cũ.

### 26.7. Spring test tự rollback

Các test Spring có `@Transactional` thường rollback theo cấu hình test. Nếu assert trong cùng transaction rằng trạng thái đã đổi, điều đó chưa chứng minh dữ liệu sau commit.

Khi kiểm thử commit thực, thiết kế test theo ranh giới transaction/`TestTransaction`/hạ tầng test phù hợp, tránh nhầm dữ liệu đã flush trong test với dữ liệu đã được commit.

## 27. Hiệu năng và batching

### 27.1. Tại sao bulk nhanh?

Giả sử cần chuyển 50.000 Product ACTIVE sang ARCHIVED:

Entity-level loop:

```java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p WHERE p.status = :active",
        Product.class
    )
    .setParameter("active", ProductStatus.ACTIVE)
    .getResultList();

for (Product p : products) {
    p.changeStatus(ProductStatus.ARCHIVED);
}

em.flush();
```

Phương án này tạo/giữ rất nhiều managed Product trong context và dirty-check chúng. JDBC batching có thể giảm round-trip nhưng vẫn phải quản lý state từng entity.

Bulk:

```java
int changed = em.createQuery(
        "UPDATE Product p " +
        "SET p.status = :archived " +
        "WHERE p.status = :active"
    )
    .setParameter("archived", ProductStatus.ARCHIVED)
    .setParameter("active", ProductStatus.ACTIVE)
    .executeUpdate();
```

Database xử lý tập hàng phù hợp mà không tải từng Product vào Java. Đây là lợi thế rõ ràng khi phép cập nhật có thể diễn đạt bằng một hoặc ít câu DML.

### 27.2. Chi phí và đánh đổi

| Tiêu chí | Entity-level | Bulk DML |
|---|---|---|
| Java memory | Có thể lớn | Thường nhỏ |
| DB statements | Có thể nhiều UPDATE | Có thể ít hơn đáng kể |
| Callback/auditing JPA | Theo mapping | Không áp dụng theo từng entity |
| Optimistic version check | ORM đảm nhiệm | Caller phải thiết kế nếu cần |
| Persistence context | State được theo dõi | Dễ stale |
| Thao tác domain riêng từng entity | Tự nhiên | Phải diễn đạt bằng SQL hoặc không phù hợp |
| Xóa graph qua cascade | ORM có thể thực hiện | Không tự thực hiện |

### 27.3. Đừng xóa lợi ích bulk bằng refresh hàng chục nghìn entity

Nếu bulk xong rồi refresh từng Product đã loaded, lợi ích về số SELECT/round-trip có thể mất đi. Với job lớn, tốt hơn thường là **không tải entity trước bulk**, chạy trong unit of work tách biệt và đọc lại những gì thực sự cần hiển thị.

### 27.4. Chi phí của CLEAR

`clear` bản thân không làm database SELECT, nhưng làm toàn bộ entity detached. Nếu code sau đó cần lại nhiều object, application phải tải lại. Vì vậy nên đặt clear ở ranh giới xử lý hợp lý, không chen liên tục giữa các thao tác nhỏ.

### 27.5. Theo dõi SQL và execution plan

Khi chọn bulk, kiểm tra:

- Điều kiện WHERE có index hữu ích không.
- Số hàng ảnh hưởng.
- Lock contention và thời gian transaction.
- Chi phí version/audit cập nhật.
- Constraint FK và trigger.
- Bất đồng bộ cache/replica.
- Kế hoạch đọc lại sau bulk.

Một bulk UPDATE ảnh hưởng hàng triệu hàng có thể gây lock lâu và ảnh hưởng dịch vụ; có thể cần chia batch/chunk hoặc maintenance window. Đó là quyết định vận hành và database, không chỉ do JPA.

## 28. Một quy trình chuẩn cho service thực thi bulk

### 28.1. Các bước

Với một service chủ động xử lý nhiều Product:

1. **Xác định phạm vi:** những hàng nào được sửa/xóa? Query WHERE có được bảo vệ bằng validation/authorization?
2. **Xác định version/callback:** có yêu cầu optimistic locking, audit hay business invariant trên từng entity không?
3. **Kiểm tra pending changes:** context hiện có gì chưa flush?
4. **Flush trước bulk** nếu transaction cần bảo toàn thay đổi pending và tạo thứ tự rõ.
5. **Thực thi DML** bằng `executeUpdate`.
6. **Kiểm tra affected count** theo contract nghiệp vụ.
7. **Xử lý managed state stale:** refresh nếu ít entity, detach/clear/context mới khi phạm vi rộng.
8. **Không dùng object cũ như managed**, đặc biệt sau clear/bulk delete.
9. **Commit hoặc rollback** đúng transaction boundary.
10. **Xác minh bằng reader phù hợp** khi cần chắc chắn DB đã commit; không chỉ getter trong context cũ.

### 28.2. Ví dụ service tương đối an toàn

```java
public int archiveByIds(
        EntityManager em,
        Collection<Long> ids) {

    if (ids == null) {
        throw new IllegalArgumentException("ids là bắt buộc");
    }

    if (ids.isEmpty()) {
        return 0;
    }

    em.flush();

    int changed = em.createQuery(
            "UPDATE Product p " +
            "SET p.status = :archived, " +
            "    p.version = p.version + 1 " +
            "WHERE p.id IN :ids " +
            "AND p.status = :active"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("active", ProductStatus.ACTIVE)
        .setParameter("ids", ids)
        .executeUpdate();

    em.clear();

    return changed;
}
```

**Điều kiện sử dụng:** đoạn method này phải chạy trong transaction hợp lệ, schema dùng numeric version tương thích, và caller chấp nhận rằng clear detach **tất cả** managed entities trong context. Method không xử lý mọi yêu cầu callback/audit hoặc concurrent bulk update, nên chỉ phù hợp khi những chính sách đó đã được quyết định.

### 28.3. Một phiên bản không clear toàn context

Khi chỉ cập nhật một Product và code tiếp tục cần chính managed instance:

```java
public Product archiveOne(
        EntityManager em, long productId) {

    Product product = em.find(Product.class, productId);

    if (product == null) {
        throw new IllegalArgumentException("Không có Product");
    }

    em.flush();

    int changed = em.createQuery(
            "UPDATE Product p " +
            "SET p.status = :archived " +
            "WHERE p.id = :id"
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("id", productId)
        .executeUpdate();

    if (changed != 1) {
        throw new IllegalStateException("Không cập nhật được");
    }

    em.refresh(product);
    return product;
}
```

Cách này vẫn dùng bulk DML nhưng chỉ tác động một hàng; ở use case một entity, **gọi `product.changeStatus` rồi dirty checking** có thể đơn giản hơn và bảo toàn lifecycle tốt hơn. Đây là ví dụ để thấy phương án refresh có chọn lọc.

### 28.4. Không cố dùng cùng một chiến lược ở mọi nơi

- **One-row domain update:** thường ưu tiên managed entity.
- **Large uniform maintenance update:** thường cân nhắc bulk + transaction riêng.
- **Bulk DELETE có graph phức tạp:** xem cascade/FK/audit trước khi chọn.
- **Long-running unit of work chứa nhiều entity:** tránh clear ngoài ý muốn.
- **API read-after-write cần chính xác:** xác định cache/transaction/source và reader mới.

## 29. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| DB đã ARCHIVED nhưng `product.getStatus()` vẫn ACTIVE | Bulk UPDATE bỏ qua managed instance | Refresh, clear/reload hoặc context mới |
| `em.contains(product) == true` mà giá trị cũ | Contains chỉ kiểm tra managed status | Không coi contains là DB verification |
| `em.find` sau bulk vẫn trả giá trị cũ | Identity map/L1 trả cùng object | Refresh hoặc clear rồi find |
| Sau `clear` thay đổi entity không được lưu | Entity đã detached | Dùng instance managed mới, không tiếp tục sửa old reference |
| Sau `clear` mất một sửa đổi trước đó | Pending changes chưa flush | Flush ở ranh giới đúng trước clear |
| `flush` sau bulk không làm field mới xuất hiện | Flush đẩy từ context xuống DB, không reload | Dùng refresh/reload |
| Bulk UPDATE thay price, flush sau bị overwrite | Managed entity có field stale | Không ghi từ state stale; version/refresh/clear |
| Optimistic locking không phát hiện bulk change | Bulk không tự tăng version | Tăng version có chủ đích hoặc entity-level operation |
| Bulk DELETE rồi refresh ném lỗi | Hàng đã bị xóa | Detach/clear, đừng refresh hàng đã mất |
| Xóa cha bulk bị lỗi FK | Cascade JPA không chạy | Xử lý child, FK hoặc entity-level removal |
| `@PreUpdate` không chạy | Bulk không kích hoạt callback từng entity | Viết audit trực tiếp hoặc chọn entity-level |
| `@Modifying(clearAutomatically=true)` làm nhiều object detached | Clear toàn persistence context | Cân nhắc transaction riêng, không dùng old references |
| L2 cache vẫn cũ dù đã clear | Clear chỉ xử lý L1 | Xem cache eviction/hints/provider |
| Collection Java còn các child đã bulk delete | Collection initialized vẫn stale | Reload graph/context phù hợp |
| SELECT native scalar khác getter entity | Scalar đọc DB view, getter đọc managed state | Phân biệt các lớp trạng thái |
| Test trong `@Transactional` pass nhưng DB sau test không đổi | Test rollback | Kiểm thử commit/reader độc lập |
| Số affected là 0 | WHERE không khớp hoặc entity không tồn tại | Xác minh predicate, version, dữ liệu |
| Update hàng loạt thiếu WHERE | DML tác động mọi hàng | Giới hạn, validation, transaction safeguards |
| UPDATE chậm hoặc lock lâu | Nhiều hàng, index yếu, transaction dài | Xem plan, index, chunking |
| Entity còn cũ sau transaction khác commit | Snapshot/isolation hoặc L1/L2 | Reload theo context/isolation, xử lý cache |
| Read replica chưa thấy kết quả | Replication lag | Chọn primary khi cần read-after-write |

## 30. Bài thực hành

### Bài 1 — Tái hiện entity stale

Chuẩn bị Product ID 10 có status ACTIVE. Trong một transaction:

1. `em.find` Product 10.
2. Chạy JPQL bulk UPDATE chuyển ID 10 sang ARCHIVED.
3. In `em.contains(product)`, `product.getStatus()` và affected count.
4. Đọc native scalar `SELECT status FROM products WHERE id = ?`.

Giải thích vì sao managed object và SQL scalar có thể trả hai giá trị khác nhau.

### Bài 2 — Refresh sau bulk

Lặp bài 1 và gọi `em.refresh(product)` sau bulk UPDATE. Quan sát giá trị `product.getStatus()`. Giải thích vì sao refresh không nên dùng với Product đã bị bulk DELETE.

### Bài 3 — Clear và load lại

Load Product 10 vào biến `old`, bulk UPDATE, gọi `em.clear`, rồi `em.find` vào biến `fresh`.

Kiểm tra:

- `em.contains(old)`.
- `old == fresh`.
- `old.getStatus()`.
- `fresh.getStatus()`.

Giải thích vì sao clear không sửa field trong `old`.

### Bài 4 — Pending changes và flush

Load Product 11, đổi `name` nhưng chưa flush. Thử quy trình `flush → bulk → clear` và so sánh với một case clear khi vẫn còn pending changes.

Tại sao chỉ gọi clear mà không có kế hoạch flush có thể làm mất dữ liệu?

### Bài 5 — Detach có chọn lọc

Load Product 10 và Product 11. Bulk chỉ cập nhật Product 10. Sau bulk, detach Product 10 và load lại, giữ Product 11 managed.

Đánh giá khi nào cách này tốt hơn clear toàn context và khi nào nó không khả thi do không biết đủ các entity bị ảnh hưởng.

### Bài 6 — Versioned bulk update

Thêm `@Version` vào Product nếu chưa có. Chạy hai biến thể:

```jpql
UPDATE Product p
SET p.status = :archived
WHERE p.id = :id
```

và:

```jpql
UPDATE Product p
SET p.status = :archived,
    p.version = p.version + 1
WHERE p.id = :id AND p.version = :expectedVersion
```

Tạo concurrent transaction để quan sát tác động tới optimistic locking và phân tích vì sao version update không làm mới L1.

### Bài 7 — Bulk DELETE và FK

Tạo PurchaseOrder có các OrderLine và `CascadeType.REMOVE`. Thử bulk DELETE Order cha. So sánh với `em.remove(managedOrder)`.

Quan sát callback, SQL, FK constraint và khả năng stale ở association đã loaded. Không xóa dữ liệu thật ngoài môi trường test.

### Bài 8 — CriteriaUpdate/CriteriaDelete

Viết lại bulk UPDATE status bằng `CriteriaUpdate<Product>`, bulk DELETE bằng `CriteriaDelete<Product>`.

Chứng minh cả hai vẫn có semantics stale context giống JPQL bulk DML dạng chuỗi.

### Bài 9 — Spring Data @Modifying

Tạo repository method:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("UPDATE Product p SET p.status = :archived " +
       "WHERE p.id IN :ids")
int archiveIds(...);
```

Trong service, giữ một managed Customer hoặc Product khác trước lời gọi. Sau repository method, kiểm tra instance đó còn managed không và giải thích hậu quả của clearAutomatically.

### Bài 10 — Truy vấn read-after-write

Sau khi bulk update và commit thành công, mở EntityManager mới để truy vấn Product. So sánh query entity và native scalar, chú ý khả năng L2 cache.

Giải thích tại sao `em.find` trên cùng context cũ không đủ.

### Bài 11 — Thêm auditing

Giả sử Product có `updatedAt` và entity listener `@PreUpdate`. Chạy bulk UPDATE status và kiểm tra callback/updatedAt. Sửa bulk query để cập nhật timestamp trực tiếp.

Nếu cần audit row-by-row, thiết kế phương án thay thế hoặc database audit phù hợp.

### Bài 12 — Collection stale

Load Customer cùng collection Orders, sau đó bulk DELETE một số Order. Kiểm tra kích thước collection trong Java và query count trên database.

Đề xuất cách reload association/context an toàn mà không phụ thuộc vào collection cũ.

### Bài 13 — DML rất lớn

Tạo dữ liệu test đủ lớn để so sánh loop entity-level với một bulk UPDATE. Đo:

- SQL statements và round-trip.
- Memory persistence context.
- Thời gian transaction và lock.
- Hiệu ứng cache.
- Chi phí refresh/clear nếu có.

Không chỉ đo thời gian `executeUpdate` mà bỏ qua xử lý stale state.

### Bài 14 — Transaction độc lập

Thiết kế job bulk trong transaction A và endpoint đọc trong transaction B. Kiểm tra kết quả sau commit ở primary. Nếu dùng replica, mô phỏng/quan sát khả năng replication lag.

Giải thích tại sao transaction boundary và source DB quan trọng hơn việc gọi một API reload đơn lẻ.

### Bài 15 — Xử lý một case khó

Service đã managed 20 Product và 3 Customer, có pending edits ở 2 Customer. Cần bulk UPDATE 10.000 Product rồi tiếp tục thay đổi các Customer trong cùng một transaction.

Chọn giữa `refresh`, `detach`, `clear`, tách transaction hoặc đổi workflow. Trình bày vì sao clear ngay có thể làm các Customer detached và mất khả năng dirty-check những sửa đổi tiếp theo.

## 31. Ghi nhớ cốt lõi

**Bulk JPQL/Criteria UPDATE và DELETE tác động trực tiếp tới database nhưng không đồng bộ state của các entity đã managed trong persistence context.** Vì vậy một `Product` có thể vẫn `em.contains(product) == true` mà giữ giá trị cũ sau khi hàng trong DB đã đổi; sau bulk DELETE, instance cũ thậm chí có thể trỏ tới một hàng không còn tồn tại.

**`flush` trước bulk** giúp đưa pending ORM changes xuống database và tránh mất dữ liệu khi clear; **`refresh` sau bulk UPDATE** giúp làm mới một managed entity cụ thể; **`detach` hoặc `clear`** loại object stale khỏi context để có thể tải lại; **persistence context/transaction mới** giúp xác minh committed state độc lập. Không lẫn lộn các hướng tác động: **flush đẩy state xuống DB, refresh kéo state DB lên entity, clear/detach ngừng quản lý object**.

Bulk DML còn **bỏ qua callback, cascade, orphanRemoval và cơ chế version tự động của entity-level operation**. Nếu yêu cầu optimistic locking, cần thiết kế version check/increment phù hợp hoặc chọn entity-level update. Trong Spring Data JPA, `@Modifying(flushAutomatically=true, clearAutomatically=true)` giúp quản lý flush/clear nhưng vẫn detach **toàn context** và không sửa các biến Java cũ.

Lựa chọn an toàn bắt đầu từ **phạm vi entity bị ảnh hưởng, các thay đổi pending, vòng đời transaction và yêu cầu đọc lại**. Khi dùng bulk operation đúng cách, ứng dụng vừa tận dụng được hiệu quả DML hàng loạt vừa tránh quyết định sai hoặc ghi đè dữ liệu từ một persistence context đã cũ.
