# Xử lý EntityExistsException và định danh bị trùng trong JPA

Khi lưu entity mới bằng Jakarta Persistence (JPA), có những trường hợp ứng dụng nhận lỗi liên quan **định danh đã tồn tại**: `EntityExistsException`, lỗi vi phạm khóa chính của database, lỗi trùng UNIQUE business key hoặc exception do JPA provider chuyển tiếp. Những lỗi này trông giống nhau ở tầng API — “không thể tạo thêm bản ghi” — nhưng **nguyên nhân, thời điểm phát hiện và cách phục hồi không hoàn toàn giống nhau**.

Ví dụ:

```java
Product first = new Product(42L, "BOOK-JPA");
Product second = new Product(42L, "BOOK-SPRING");

em.persist(first);
em.persist(second); // Có thể bị phát hiện xung đột identity trong context.
```

Trường hợp khác:

```text
Database đã có:
  product(id=42, sku='BOOK-JPA')

Persistence context mới, chưa load Product#42:
  em.persist(new Product(42, 'BOOK-OTHER'))

Khi INSERT/flush/commit:
  DB từ chối vì PRIMARY KEY(id=42) đã tồn tại.
```

Và một trường hợp khác nữa:

```text
Product#42: sku='BOOK-JPA'
Request tạo Product#43: sku='BOOK-JPA'

PRIMARY KEY khác nhau.
Nhưng UNIQUE(tenant_id, sku) vẫn bị vi phạm.
```

Không nên áp dụng cùng một “mẹo” như `em.merge(...)`, `em.clear()` hoặc retry ngay lập tức cho cả ba tình huống.

> **Nguyên tắc cốt lõi:** Khi thấy lỗi “đã tồn tại”, phải xác định **trùng loại định danh nào**, **lỗi được phát hiện ở đâu**, và **transaction còn sử dụng được hay không**. Chỉ khi phân loại đúng mới chọn được phản hồi nghiệp vụ, rollback, idempotency, retry hay sửa cấu hình phát sinh ID.

Bài này thuộc chương **Lỗi và phục hồi** của module *Data Persistence Relational Access ORM JPA*. Nội dung đi từ JPA entity identity, `persist`/`merge`, đến lỗi database, Spring Data JPA, transaction rollback, idempotency và kiểm thử song song.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích nghĩa của **persistent identity** và vì sao hai Java objects cùng ID chưa chắc là cùng managed instance.
2. Hiểu contract và giới hạn của `jakarta.persistence.EntityExistsException`.
3. Phân biệt **identity collision trong persistence context**, **duplicate primary key ở DB**, và **duplicate unique business key**.
4. Biết ngoại lệ có thể xuất hiện tại `persist`, `flush` hoặc `commit` tùy tình huống/provider.
5. Tránh dùng `merge` làm “cách sửa” thiếu kiểm soát cho mọi lỗi INSERT trùng.
6. Hiểu sự khác nhau giữa assigned ID, `IDENTITY`, `SEQUENCE` và UUID ID.
7. Phân tích lỗi khi sequence database bị lệch so với dữ liệu.
8. Kiểm tra cascading persist, detached entity, composite IDs và shared primary keys.
9. Xử lý lỗi transaction theo nguyên tắc **rollback attempt thất bại, dùng transaction mới khi cần tiếp tục**.
10. Phân loại lỗi JPA, Bean Validation, Hibernate ORM, JDBC và Spring exception translation.
11. Dùng database constraints để bảo vệ uniqueness khi hai requests tạo đồng thời.
12. Thiết kế idempotency key, upsert có điều kiện và conflict response hợp lệ.
13. Viết integration tests với cùng persistence context và hai transactions độc lập.
14. Tạo checklist chẩn đoán lỗi từ API tới schema/database.

## 2. Định danh entity là gì?

Trong JPA, một entity có **persistent identity** được xác định bởi entity type và primary key value trong phạm vi persistence unit tương ứng.

```java
@Entity
@Table(name = "product")
public class Product {

    @Id
    private Long id;

    private String name;
}
```

`Product.class + id=42` là một identity trong entity model này.

### 2.1. Ba điều không nên nhầm

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Java object identity | `a == b` | Có phải cùng instance trong JVM? |
| JPA persistent identity | `Product#42` | Có đại diện cho cùng entity row theo mapping? |
| Database/business uniqueness | `PRIMARY KEY(id)` hoặc `UNIQUE(tenant_id,sku)` | DB ngăn những bộ giá trị trùng theo constraint |

Hai Java objects có thể mang cùng ID nhưng `a != b`:

```java
Product a = new Product(42L, "A");
Product b = new Product(42L, "B");

System.out.println(a == b); // false
```

Chúng vẫn có **cùng persistent identity** nếu đều được xem là `Product#42` trong cùng entity model.

### 2.2. Persistence context là identity map

Trong một persistence context, JPA quản lý **một managed instance cho một persistent entity identity**.

```java
Product a = em.find(Product.class, 42L);
Product b = em.find(Product.class, 42L);

System.out.println(a == b); // true nếu entity còn managed
```

Đó là identity map của persistence context, thường gọi là cache cấp một (L1).

### 2.3. Định danh database có thể có phạm vi tenant

Nếu hệ thống multi-tenant dùng database/schema riêng, ID `42` ở tenant A và ID `42` ở tenant B có thể đại diện hai bản ghi khác nhau tùy kiến trúc. Không tự dùng một ID trần làm cache key/authorization proof xuyên tenant.

Nếu dùng shared table có `tenant_id`, thiết kế khóa chính có thể là globally unique ID hoặc composite `(tenant_id,id)`. Phải phân biệt **JPA primary key model** với **UNIQUE business key**.

---

## 3. EntityExistsException là gì?

`jakarta.persistence.EntityExistsException` là exception thuộc API Jakarta Persistence, thường được dùng khi một thao tác persist cố tạo entity có persistent identity đã tồn tại.

```java
import jakarta.persistence.EntityExistsException;
```

Theo contract JPA, khi persist một entity đã có identity trùng với entity tồn tại, `EntityExistsException` **có thể** được ném tại lời gọi `persist`. Trong một số tình huống, lỗi chỉ xuất hiện khi provider đồng bộ SQL với database, tức tại `flush` hoặc `commit`, và có thể được biểu diễn bởi `EntityExistsException` hoặc một `PersistenceException` khác phù hợp.

### 3.1. Không suy luận exception class chỉ từ chữ “duplicate”

Một duplicate PK bị database báo lỗi không có nghĩa JPA provider bắt buộc biến nó thành đúng `EntityExistsException`. Provider có thể ném/wrap exception về SQL constraint.

### 3.2. Không suy luận timing từ lời gọi persist

```java
em.persist(product);
System.out.println("After persist");
```

Việc chạy tới dòng `After persist` **không chứng minh INSERT thành công**. SQL INSERT có thể chưa được gửi hoặc transaction chưa commit.

### 3.3. EntityExistsException không chứng minh record đã commit ở DB

Một provider có thể phát hiện identity collision trong persistence context trước khi database kiểm tra. Một object cùng ID đang managed chưa chắc là row đã commit — có thể là entity mới được schedule INSERT trong chính transaction.

### 3.4. EntityExistsException không phải optimistic locking exception

`OptimisticLockException` là loại xung đột stale version trong optimistic concurrency. Một INSERT trùng PK và một UPDATE entity có version cũ là hai nghiệp vụ khác nhau.

---

## 4. Vòng đời entity liên quan đến lỗi trùng định danh

```text
Transient / New
      |
      | em.persist(...)
      v
Managed new ---- flush/INSERT ----> Managed persisted
      |
      | em.remove(...)
      v
Removed
      |
      | flush/DELETE
      v
Row deleted

Managed -- detach/clear/close --> Detached
Detached -- em.merge(...) ------> Managed COPY returned
```

### 4.1. New entity

Chưa được persistence context quản lý. Nó có thể có:

- ID chưa được gán vì dùng `@GeneratedValue`.
- Assigned ID đã có sẵn.
- Composite ID được tạo từ nhiều thuộc tính.

**Có ID không tự chứng minh object là persisted entity.**

### 4.2. Managed entity

Đã được persistence context quản lý. Với cùng identity, gọi `find` trả managed instance hiện tại.

### 4.3. Detached entity

Từng được quản lý nhưng đã tách khỏi context, ví dụ sau `em.detach`, `em.clear` hoặc `em.close`. Nó vẫn có ID và các field values, nhưng không còn được context theo dõi.

### 4.4. Removed entity

Được đánh dấu để xóa. Nếu `persist` được gọi với removed entity, JPA có rules chuyển trạng thái riêng; không nên mặc định mọi removed instance phải được xử lý như một new entity.

### 4.5. Persist không phải “save bất kể state”

`em.persist` có mục đích biến một **new entity** thành managed và schedule INSERT. Với detached instance, cách dùng `persist` không phù hợp và có thể dẫn đến `EntityExistsException` hoặc `PersistenceException` theo provider/timing.

---

## 5. Tình huống A: hai objects cùng ID trong một persistence context

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product first = new Product(42L, "First");
Product second = new Product(42L, "Second");

em.persist(first);
em.persist(second); // Identity conflict có thể bị phát hiện.

tx.commit();
```

Hai objects có cùng JPA identity `Product#42` nhưng là hai instances. Persistence context không thể quản lý chúng độc lập như hai entity khác nhau với cùng identity.

### 5.1. Khi nào phát hiện?

Provider có thể phát hiện ngay tại lần persist thứ hai, hoặc muộn hơn khi xử lý persistence operation. Không viết logic correctness dựa trên một thời điểm cố định.

### 5.2. Nguyên nhân phổ biến

- DTO mapper tạo lại entity instance với ID đã có.
- Hai lần mapping cùng request tạo hai `Product` objects mang cùng assigned ID.
- Child cascades cùng reference entity được tạo hai object với cùng ID.
- Ghép hai object graphs từ nhiều requests vào một context mà không resolve identity.
- Code dùng `new Product(existingId,...)` thay vì lấy managed reference phù hợp.

### 5.3. Đừng dùng em.clear như “chữa” identity conflict

`em.clear()` detach tất cả managed entities, có thể làm mất pending changes chưa flush, nhưng **không làm database cho phép hai rows cùng PRIMARY KEY**. Nếu tiếp tục INSERT cùng key, database vẫn từ chối.

### 5.4. Cách làm đúng khi entity đã hiện diện

Nếu intent là **chỉnh sửa entity hiện có**, truy xuất instance đang managed:

```java
Product managed = em.find(Product.class, 42L);

if (managed == null) {
    throw new ProductNotFoundException(42L);
}

managed.rename("Updated name");
```

Không tạo thêm new Product với ID 42 rồi `persist`.

### 5.5. Khi intent là tạo mới

Không dùng lại ID đã cấp. Nếu ID do application tạo, cần thuật toán tạo ID đúng; nếu ID do DB/JPA tạo, để generator đảm nhiệm.

---

## 6. Tình huống B: trùng primary key với row đã có trong database

Giả sử table:

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL
);

INSERT INTO product(id, sku, name)
VALUES (42, 'BOOK-JPA', 'Learn JPA');
```

Một persistence context hoàn toàn mới:

```java
em.persist(new Product(42L, "Another title"));
em.flush();
```

Nếu provider cố INSERT ID 42, database sẽ từ chối do PRIMARY KEY đã tồn tại.

### 6.1. Trùng DB PK có thể khác identity collision trong L1

Trong context mới, JPA có thể chưa load `Product#42`. Không có “hai managed objects cùng ID trong L1”, nhưng **database đã có row**.

### 6.2. Chọn exception theo actual cause, không theo giả định

Lỗi có thể đi qua:

```text
Database unique/PK violation
    |
    v
JDBC SQLException / SQLIntegrityConstraintViolationException
    |
    v
Hibernate ORM constraint exception (nếu dùng Hibernate)
    |
    v
JPA PersistenceException / RollbackException
    |
    v
Spring translated DataIntegrityViolationException
    (tùy boundary và framework)
```

Không phải stack nào cũng có đầy đủ các lớp trên hoặc cùng thứ tự nesting.

### 6.3. Không nên catch mọi PersistenceException và trả “đã tồn tại”

`PersistenceException` cũng có thể chứa lỗi connection, SQL syntax, mapping hoặc transaction. Chỉ kết luận duplicate khi **constraint/SQLState/vendor code được xác nhận** hoặc đã có dữ kiện nghiệp vụ đáng tin.

### 6.4. Database constraint là hàng rào đáng tin cậy

`PRIMARY KEY` được DB thực thi khi INSERT và xử lý xung đột đồng thời. Một check `existsById` trước INSERT không thay thế nó.

---

## 7. Tình huống C: trùng UNIQUE business key chứ không trùng ID

Entity:

```java
@Entity
@Table(
    name = "product",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "sku", nullable = false)
    private String sku;

    // ...
}
```

Rows:

| id | tenant_id | sku |
|---:|---|---|
| 42 | shop-a | BOOK-JPA |
| 43 | shop-b | BOOK-JPA |

Cả hai hợp lệ nếu uniqueness theo `(tenant_id, sku)`.

Nhưng thêm `Product#44` với `tenant_id=shop-a, sku=BOOK-JPA` sẽ vi phạm `uk_product_tenant_sku` dù **ID mới là 44**.

### 7.1. Không gọi mọi UNIQUE conflict là EntityExistsException

Một UNIQUE business key conflict có thể được báo như database constraint violation; nó không đồng nghĩa JPA identity đã tồn tại.

### 7.2. Tại sao phân biệt này quan trọng?

Nếu handler nhận conflict ở `sku` mà tự gọi `merge` theo ID mới, nó không giải quyết gì. Cần lựa chọn nghiệp vụ:

- Trả lỗi SKU đã được sử dụng.
- Trả lại existing resource nếu đây là retry idempotent được xác nhận.
- Cập nhật resource hiện có nếu API contract rõ là upsert theo SKU.
- Tạo SKU khác nếu quy trình tự động cấp mã cho phép.

### 7.3. Database migration mới là nơi xác nhận UNIQUE thực

`@UniqueConstraint` mô tả schema metadata. Production thường quản lý bảng bằng migration; annotation **không tự bổ sung constraint** nếu schema generation đã tắt.

### 7.4. UNIQUE và null semantics khác nhau giữa databases

Nhiều DB cho phép nhiều NULL values trong một UNIQUE constraint theo semantics riêng. Nếu business key phải luôn hiện diện, kết hợp `NOT NULL` với `UNIQUE` và application validation.

---

## 8. Entity mẫu: assigned ID và business uniqueness

Để kiểm soát bài toán định danh rõ nhất, dùng entity có **assigned ID**:

```java
package com.example.catalog.persistence;

import jakarta.persistence.*;

@Entity
@Table(
    name = "catalog_product",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_product_tenant_sku",
            columnNames = {"tenant_id", "sku"}
        )
    }
)
public class CatalogProduct {

    @Id
    @Column(name = "product_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "product_name", nullable = false, length = 200)
    private String name;

    @Version
    @Column(name = "row_version")
    private Long version;

    protected CatalogProduct() {
    }

    public CatalogProduct(
            Long id,
            String tenantId,
            String sku,
            String name
    ) {
        if (id == null || id <= 0) {
            throw new IllegalArgumentException("Invalid ID");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }

        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public Long getVersion() { return version; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = newName;
    }
}
```

SQL schema minh họa:

```sql
CREATE TABLE catalog_product (
    product_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT uk_product_tenant_sku
        UNIQUE (tenant_id, sku)
);
```

Trong ví dụ assigned ID, **caller hoặc ID allocation service** phải cấp ID mới. `@Version` do JPA provider quản lý, không để request tự gán.

### 8.1. Constructor kiểm tra cơ bản không thay UNIQUE

Constructor biết SKU không blank, nhưng không thể tự chứng minh toàn database không có SKU đó. Database UNIQUE vẫn cần.

### 8.2. @Version không giúp tránh hai INSERT cùng PK

Optimistic versioning tập trung vào stale updates của cùng persisted entity. Hai INSERT cạnh tranh cùng primary key sẽ được database giải quyết bởi PK uniqueness, không phải `@Version` thay thế.

### 8.3. Chỉ dùng entity fields thuộc authorized tenant

Không tin `tenantId` từ payload client. Service lấy tenant từ security context/server-side contract và áp vào entity/query.

---

## 9. Persist đúng ý nghĩa “tạo mới”

Một service dạng Java SE:

```java
public void createProduct(
        EntityManager em,
        long id,
        String authorizedTenant,
        String sku,
        String name
) {
    CatalogProduct product = new CatalogProduct(
        id,
        authorizedTenant,
        sku,
        name
    );

    em.persist(product);
}
```

Hàm trên giả định **caller đã mở transaction** và sẽ flush/commit. Nó không tự xác nhận tạo mới thành công chỉ vì `em.persist` return.

### 9.1. Không đặt transaction trong entity

Entity không nên gọi `EntityManager` để tự xác định có thể persist hay không. Service/repository điều phối persistence; entity giữ domain invariants cục bộ.

### 9.2. Không dùng EntityExistsException để tự chọn update

Sai về semantics nếu API được định nghĩa “POST create new”:

```java
try {
    em.persist(newProduct);
} catch (EntityExistsException ex) {
    em.merge(newProduct);
}
```

Nếu user chỉ có quyền tạo mà không có quyền sửa, chuyển conflict thành update có thể vượt authorization.

### 9.3. Idempotent create là một API contract riêng

Nếu request lặp lại với cùng `requestKey` thì trả outcome cũ, cần hệ idempotency rõ. Không dùng “trùng ID thì chắc là retry” làm tiêu chuẩn.

---

## 10. Tại sao gọi persist hai lần cùng một managed instance thường không tạo hai INSERT?

```java
CatalogProduct product = new CatalogProduct(
    100L, "shop-a", "BOOK-100", "Persistence"
);

em.persist(product);
em.persist(product);
```

Với **cùng instance đã managed**, `persist` thứ hai không có ý nghĩa tạo thêm row mới. Đây khác với:

```java
em.persist(new CatalogProduct(
    100L, "shop-a", "BOOK-100", "Persistence"
));
em.persist(new CatalogProduct(
    100L, "shop-a", "BOOK-101", "Different object"
));
```

Hai objects khác nhau cố dùng cùng persistent identity. Provider có thể báo identity collision.

### 10.1. Object reference quan trọng

`a == b` là dấu hiệu hai biến trỏ cùng object. `a.getId().equals(b.getId())` chỉ nói ID values trùng, không nói chúng là cùng managed instance.

### 10.2. equals/hashCode không quyết định DB identity correctness

Định nghĩa `equals`/`hashCode` đúng giúp collections hoạt động hợp lý, nhưng không sửa PK/UNIQUE constraints. Hai objects bằng nhau theo Java equality có thể vẫn là hai instances trong persistence context.

### 10.3. Đừng hack equals để tránh EntityExistsException

Xóa `equals` hay đổi nó sang so sánh object reference không làm database cho phép duplicate PK.

---

## 11. Định danh do application cấp và bẫy tái sử dụng ID

Assigned IDs phù hợp nếu:

- ID đến từ một hệ thống có authority rõ.
- Có thuật toán phân bổ không trùng giữa instances.
- Legacy data yêu cầu giữ ID.
- ID là composite natural key theo domain.

Nhưng các sai lầm dễ gây duplicate:

```java
long id = 1L; // hard-code cho mọi request
CatalogProduct p = new CatalogProduct(
    id, tenant, sku, name
);
em.persist(p);
```

Hoặc:

```java
long nextId = repository.findMaxId() + 1;
em.persist(new CatalogProduct(nextId, ...));
```

### 11.1. MAX(id)+1 không an toàn dưới concurrency

Hai transactions cùng đọc `MAX(id)=100` rồi cùng tạo ID=101. Một bên sẽ bị PK conflict. Không giải quyết bằng cách “ngủ vài milliseconds”.

### 11.2. Dùng ID generator có uniqueness contract rõ

- Database sequence/identity.
- UUID được sinh theo quy trình và kiểm tra constraint.
- Distributed ID service/algorithm với node configuration chính xác.
- Composite key có authority/ràng buộc rõ.

### 11.3. ID trùng sau restore/import

Dữ liệu được import với IDs lớn nhưng sequence chưa đồng bộ có thể khiến generated IDs đụng rows cũ. Đây là lỗi vận hành/migration, không phải lý do đổi tất cả writes thành merge.

---

## 12. @GeneratedValue và lựa chọn chiến lược

Entity:

```java
@Entity
public class GeneratedProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected GeneratedProduct() {
    }

    public GeneratedProduct(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

### 12.1. IDENTITY

Database thường cấp ID trong quá trình INSERT. Provider có thể phải gửi INSERT sớm để có generated ID. Do đó exception timing của constraint cũng có thể xảy ra ngay gần `persist`, nhưng **không có bảo đảm giống nhau trên mọi provider/dialect/transaction flow**.

### 12.2. SEQUENCE

Provider có thể lấy số từ sequence trước INSERT; generated ID được cấp trước khi row tồn tại trong DB. `id != null` không chứng minh INSERT/commit đã thành công.

### 12.3. TABLE/AUTO

`TABLE` có chi phí và concurrency semantics riêng; `AUTO` để provider chọn strategy theo database và configuration. Không suy luận AUTO luôn tương đương IDENTITY.

### 12.4. Đừng tự set ID khi provider sở hữu ID

Nếu mapping dùng `@GeneratedValue`, application nên để generator cấp ID theo contract. Tự set ID bằng reflection/setter có thể khiến provider hiểu entity state sai hoặc gây duplicate.

### 12.5. Trùng generated ID thường là tín hiệu cần điều tra

Nếu một generator bình thường mà liên tục tạo ID trùng, kiểm tra:

- Database sequence/identity counter sau import.
- Migrations.
- Multiple nodes/generator allocation configuration.
- Hibernate pooling/optimizer strategy.
- Database restore hoặc manual inserts.
- Sequence increment/allocation mismatch.

Chỉ retry mù quáng có thể làm che lỗi hạ tầng.

---

## 13. Sequence bị lệch sau import dữ liệu

Giả sử PostgreSQL table:

```text
catalog_product:
  product_id = 1 .. 5000

sequence hiện phát giá trị tiếp theo = 100
```

Nếu generator dùng sequence này, INSERT mới có thể bị PK conflict khi ID được cấp đã tồn tại.

### 13.1. Chẩn đoán

Đối chiếu:

1. Current maximum primary key trong table.
2. Sequence mapping JPA XML/annotations.
3. Sequence object và trạng thái thực.
4. Allocation size/optimizer strategy của provider.
5. Các nodes có đang dùng pooled ID ranges không.
6. Các manual imports có chèn explicit IDs không.

### 13.2. Không “set sequence = MAX(id)+1” khi hệ thống đang ghi

Nếu điều chỉnh sequence trong lúc nhiều application nodes vẫn cấp IDs, có race với in-memory allocated ranges. Cần maintenance plan, xác định provider allocation strategy, chặn hoặc phối hợp writers và test staging.

### 13.3. Không giả định sequence luôn tăng đúng 1

`@SequenceGenerator(allocationSize=50)` và provider optimizers có thể cấp theo block. Database sequence step và application allocation phải tương thích.

### 13.4. Kết quả phục hồi

Sau sửa generator, request thất bại trước đó cần được đánh giá lại: đã commit hay chưa, có idempotency key hay không, có external side effects không. Không chỉ phát lại INSERT vô điều kiện.

---

## 14. UUID có loại bỏ hoàn toàn rủi ro duplicate không?

UUID giảm xác suất trùng khi được tạo đúng, nhưng:

- Database PRIMARY KEY/UNIQUE vẫn phải tồn tại.
- Bug có thể tái sử dụng cùng UUID.
- Client có thể gửi lại ID từ request cũ.
- Copy dữ liệu giữa environments có thể tạo duplicates.
- Một service có thể cố tạo cùng business key dù UUID khác nhau.

### 14.1. UUID là identity, không phải idempotency key mặc định

Hai requests tạo cùng một sản phẩm nghiệp vụ nhưng sinh hai UUID khác nhau vẫn có thể tạo hai rows, nếu không có UNIQUE business key hoặc idempotency contract.

### 14.2. ID do server sinh hay client sinh?

Cần quy định rõ. Nếu server cấp ID, client không nên tự override. Nếu client-supplied ID được cho phép, authorization và duplicate handling phải nêu rõ semantics (ví dụ PUT idempotent ở URL xác định).

### 14.3. Kiểm tra serialization

UUID Java ↔ database UUID/BINARY/CHAR representation có mapping và index considerations; không nên chuyển strategy chỉ để né một lỗi duplicate PK mà chưa điều tra nguyên nhân.

---

## 15. Composite primary key và @EmbeddedId

Ví dụ bảng line item có khóa chính `(order_id, line_no)`:

```java
@Embeddable
public class OrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_no")
    private Integer lineNo;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = orderId;
        this.lineNo = lineNo;
    }

    // equals/hashCode theo tất cả thành phần key.
}
```

Entity:

```java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @Column(nullable = false)
    private String sku;

    protected OrderLine() {
    }

    public OrderLine(OrderLineId id, String sku) {
        this.id = id;
        this.sku = sku;
    }
}
```

### 15.1. Trùng composite identity

`(orderId=10, lineNo=1)` và `(orderId=10, lineNo=1)` là cùng PK dù Java objects có thể khác instance.

### 15.2. Line number allocation race

Nếu hai transactions cùng `COUNT(lines)+1` để cấp `lineNo`, cả hai có thể chọn cùng số. PK sẽ chặn một bên, nhưng cần thiết kế cấp line number an toàn hoặc serializing đúng parent Order.

### 15.3. equals/hashCode của embedded key

Composite key class cần equality/hash semantics phù hợp JPA identity, nhất quán với DB. Mutating key fields sau khi entity đã managed là hành vi rủi ro, không phải cách sửa duplicate.

### 15.4. Thay khóa không giống đổi thuộc tính thường

Nếu cần di chuyển OrderLine sang Order khác, thường nên thiết kế thao tác domain tạo entity/new identity hoặc một migration riêng, không tự set key của managed entity.

---

## 16. @MapsId và shared primary key

Một `OrderDetails` có cùng PK với `Order`:

```java
@Entity
public class OrderDetails {

    @Id
    private Long id;

    @MapsId
    @OneToOne(optional = false)
    private SalesOrder order;

    private String notes;
}
```

`@MapsId` liên kết identity của dependent entity với parent entity. Nếu code tạo **hai OrderDetails** cho cùng Order, cả hai có cùng PK dù tạo từ hai new Java instances.

### 16.1. Không tạo dependent entity hai lần

Nếu một Order chỉ có một Details row, trước khi create cần biết business operation là:

- Tạo lần đầu.
- Update Details đã có.
- Bỏ qua vì request lặp.
- Trả conflict vì đã tồn tại.

### 16.2. Cascade không “hợp nhất” hai dependents

`CascadeType.PERSIST` chỉ truyền persistence operation theo graph. Nó không chọn một trong hai objects cùng ID làm source of truth.

### 16.3. FK và PK uniqueness vẫn cần

Shared key được DB bảo vệ bởi PRIMARY KEY và foreign key. JPA mapping giúp diễn đạt quan hệ, nhưng không thay constraint vật lý.

---

## 17. Cascading persist có thể làm lộ entity trùng identity

Ví dụ `Order` tham chiếu một `Customer` đã tồn tại:

```java
@ManyToOne(cascade = CascadeType.PERSIST)
private Customer customer;
```

Nếu code:

```java
Customer customer = new Customer(existingCustomerId);
Order order = new Order(customer);

em.persist(order); // cascade persist có thể đi tới customer.
```

Trong khi DB đã có Customer cùng ID, cascade persist có thể cố tạo thêm Customer thay vì chỉ link existing Customer.

### 17.1. Không cascade persist reference entity mặc định

Với `@ManyToOne` trỏ tới Customer, Product, Country, Currency hoặc shared master data, thường không nên tự động cascade PERSIST nếu referenced entity có lifecycle độc lập.

### 17.2. Dùng managed reference đúng mục đích

```java
Customer customer =
    em.getReference(Customer.class, customerId);

Order order = new Order(customer);
em.persist(order);
```

`getReference` cho phép tạo managed reference theo ID mà không nhất thiết SELECT ngay. **Nó không xác nhận row tồn tại hoặc user có quyền sử dụng ID**; DB FK hoặc truy cập proxy sau này có thể phát hiện vấn đề.

### 17.3. Nếu cần xác minh ownership/tenant

Query Customer trong authorized scope thay vì chỉ `getReference`. Khóa tham chiếu là vấn đề khác; một reference object không tự chứng minh authorization.

### 17.4. CascadeType.ALL không phải lựa chọn an toàn mặc định

`ALL` bao gồm cả remove; trên shared master-data association có thể dẫn đến operations ngoài ý muốn. Thiết kế cascade theo aggregate ownership.

---

## 18. persist hay merge khi có ID?

Một quy tắc sai phổ biến:

> “Nếu object có ID thì dùng merge, không có ID thì persist.”

Điều này **không phải luật JPA**.

### 18.1. Assigned ID mới hoàn toàn có ID

```java
CatalogProduct newProduct = new CatalogProduct(
    9001L, "shop-a", "BOOK-9001", "New item"
);

em.persist(newProduct);
```

Nó là new entity dù ID không null.

### 18.2. Detached entity có thể có ID

```java
CatalogProduct detached = ...; // loaded từ EM trước
CatalogProduct managed = em.merge(detached);
```

Đây là một workflow update/reattach state khác.

### 18.3. merge không làm detached instance managed

```java
CatalogProduct managed = em.merge(detached);
System.out.println(managed == detached); // Không mặc định true.
```

JPA trả một managed instance chứa state được merge. Caller nên tiếp tục làm việc với **managed return value**.

### 18.4. Merge có thể INSERT khi entity không tồn tại

Tùy state/ID/version/provider, `merge` một object không tìm được existing row có thể dẫn tới INSERT. Vì vậy không coi `merge` là "update-only" hoặc "safe if duplicate".

### 18.5. Merge không giải quyết UNIQUE business key

Nếu source object có ID khác nhưng SKU trùng, merge vẫn có thể làm DB báo UNIQUE violation.

---

## 19. Vì sao dùng merge để “chữa” EntityExistsException là nguy hiểm?

Xét API:

```text
POST /products
body: { "id": 42, "name": "Attacker-controlled" }
```

Nếu Product#42 đã tồn tại, yêu cầu tạo mới cần trả conflict hoặc áp idempotency contract. Nhưng code:

```java
try {
    em.persist(product);
} catch (EntityExistsException ex) {
    em.merge(product);
}
```

có thể biến yêu cầu create thành **ghi đè bản ghi hiện hữu**, thậm chí vượt quyền.

### 19.1. Lỗi transaction trước đó chưa được giải quyết

Khi persist/flush thất bại, transaction có thể đã rollback-only. Cố gọi merge trong cùng transaction không bảo đảm có thể commit.

### 19.2. Mất dữ liệu do detached fields

Merge có thể copy null/default fields từ payload vào managed entity, ghi đè fields client không được phép sửa.

### 19.3. Chưa xử lý optimistic version

Nếu entity versioned, detached state có thể stale; merge có thể phát sinh `OptimisticLockException` thay vì xử lý duplicate.

### 19.4. Hướng đúng theo intent

- **Create-only:** persist entity mới; nếu duplicate trả conflict hoặc reconcile idempotency.
- **Update-only:** load managed entity theo authorized scope, apply changes, kiểm tra version.
- **Upsert:** định nghĩa rõ key, trường được phép update, database atomicity và conflict policy.
- **Idempotent replay:** tìm operation outcome theo request key, không tự ghi lại.

---

## 20. Spring Data JPA save không đồng nghĩa SQL INSERT

Spring Data JPA thường có:

```java
Product saved = repository.save(product);
```

Nhưng `save` có thể chọn `persist` hoặc `merge` tùy cơ chế nhận diện entity có phải new hay không.

### 20.1. Nhận diện isNew

Spring Data JPA thường dùng version attribute (nếu có version không phải primitive phù hợp), ID hoặc custom `Persistable.isNew()` để xác định state. Với assigned ID, nếu không cấu hình đúng, object mới nhưng `id != null` có thể bị coi là existing và đi qua `merge`.

### 20.2. Vì sao quan trọng?

Bạn muốn API **create-only**, nhưng repository `save` có thể dùng merge và không biểu diễn điều kiện “không được update nếu ID tồn tại”.

### 20.3. Khi cần create-only mạnh

Có thể dùng service với EntityManager `persist` rõ ràng, cùng database PK/UNIQUE. Khi dùng Spring Data repository, cần hiểu `isNew` strategy và không xem `save` là bằng chứng uniqueness đã được kiểm tra.

### 20.4. saveAndFlush không phải commit

`saveAndFlush` yêu cầu flush, giúp phát hiện một số lỗi sớm, nhưng transaction vẫn chưa chắc đã commit. Không phát event “created” trước commit chỉ vì saveAndFlush return.

### 20.5. Entity new detection không thay DB uniqueness

Dù Spring quyết định đúng persist, hai requests đồng thời vẫn có thể tạo cùng SKU/assigned ID. Constraints ở DB là hàng rào cuối.

---

## 21. Thời điểm phát hiện lỗi: persist, flush, commit

Timeline:

```text
BEGIN TRANSACTION
    |
    v
em.persist(newProduct)
    |   có thể phát hiện identity collision
    |   hoặc có thể chỉ schedule INSERT
    v
em.flush()
    |   có thể chạy INSERT
    |   có thể phát hiện DB duplicate PK / UNIQUE
    v
tx.commit()
    |   có thể flush pending changes
    |   có thể phát hiện constraints deferred/commit failure
    v
COMMITTED (chỉ nếu commit thực sự thành công)
```

### 21.1. Lỗi ngay ở persist

Thường liên quan provider phát hiện state/identity conflict trong persistence context, hoặc SQL sớm vì IDENTITY generation/flush behavior.

### 21.2. Lỗi khi flush

Database có thể từ chối INSERT hoặc provider phát hiện entity conflicts khi đồng bộ.

### 21.3. Lỗi khi commit

Nếu chưa flush hoặc database constraint được kiểm tra ở commit (ví dụ một số deferred constraints), exception có thể xuất hiện ở ranh giới commit.

### 21.4. Exception có thể được wrap

Ví dụ resource-local `tx.commit` có thể bọc lỗi trong `RollbackException` hoặc loại `PersistenceException` khác; Spring transaction interceptor cũng có thể translate/wrap.

### 21.5. Đừng dựa vào "persist return" để phát HTTP 201

Chỉ xác nhận created sau khi transaction commit thành công. Với `@Transactional` proxy, commit diễn ra ngoài method body và trước khi lời gọi transactional trả quyền điều khiển hoàn toàn cho caller.

---

## 22. Flush có giúp bắt lỗi sớm không?

```java
em.persist(product);
em.flush();
```

Có. Với một số DB constraints không deferred và SQL được gửi ở flush, bạn có thể quan sát duplicate trước khi phần còn lại của method xử lý.

Nhưng:

- `flush` không commit.
- Một transaction khác có thể gây xung đột/commit outcome ảnh hưởng đến thao tác sau.
- DB có deferred constraints.
- Flush có thể đồng bộ **nhiều managed entities** khác đang dirty, không chỉ Product.
- Lỗi ở commit vẫn có thể xảy ra.
- Sau flush failure, transaction có thể không thể tiếp tục.

### 22.1. Flush đúng lý do

Hữu ích khi:

- Cần phát hiện lỗi DB trước khi chạy các bước trong **cùng DB transaction**.
- Cần kiểm tra FK/UNIQUE ngay khi có SQL.
- Muốn test persistence behavior cụ thể.

Không nên:

- Flush rồi gửi email/payment trước commit.
- Flush và coi như chắc chắn đã tạo resource.
- Catch duplicate rồi tiếp tục INSERT hàng khác trong transaction bị lỗi.

### 22.2. Constraint deferrability

Một số database hỗ trợ constraints được kiểm tra cuối transaction. Với constraints như vậy, flush có thể pass và commit mới fail. Do đó **không có flush nào thay commit confirmation**.

---

## 23. Exception taxonomy: cùng lỗi business, nhiều lớp Java

| Exception | Namespace | Ý nghĩa điển hình |
|---|---|---|
| `EntityExistsException` | `jakarta.persistence` | JPA entity identity đã tồn tại trong ngữ cảnh persist |
| `PersistenceException` | `jakarta.persistence` | Lỗi persistence tổng quát |
| `RollbackException` | `jakarta.persistence` | Transaction commit không thể thành công |
| `OptimisticLockException` | `jakarta.persistence` | Xung đột optimistic version |
| `EntityNotFoundException` | `jakarta.persistence` | Referenced entity không tồn tại theo semantics |
| `ConstraintViolationException` | `jakarta.validation` | Bean Validation vi phạm constraint trên Java bean |
| `ConstraintViolationException` | `org.hibernate.exception` | Hibernate ORM báo database constraint violation |
| `DataIntegrityViolationException` | `org.springframework.dao` | Spring data access translation cho lỗi integrity |
| `DuplicateKeyException` | `org.springframework.dao` | Spring subtype khi duplicate key được phân loại phù hợp |
| `SQLIntegrityConstraintViolationException` | `java.sql` | JDBC-level integrity error |
| `SQLException` | `java.sql` | Cơ sở chung của JDBC errors |

### 23.1. Hai ConstraintViolationException là hai loại hoàn toàn khác

```java
jakarta.validation.ConstraintViolationException
org.hibernate.exception.ConstraintViolationException
```

Cái đầu chứa tập `ConstraintViolation<?>` cho bean fields; cái sau có thể chứa constraint name/SQL exception khi DB từ chối.

### 23.2. Không phải mọi database duplicate đều là EntityExistsException

Provider có thể giữ underlying SQL constraint exception và bọc nó. Ứng dụng nên dựa vào cause/constraint semantics thay vì yêu cầu đúng một class.

### 23.3. Spring exception translation còn phụ thuộc boundary

Một repository bean có `@Repository`/Spring exception translation có thể xuất `DataIntegrityViolationException`. Nhưng exception ở commit phase qua transaction interceptor có thể có wrapper khác tùy stack. API handler cần hiểu đường đi thật.

### 23.4. Không catch Throwable hoặc mọi RuntimeException để trả 409

Lỗi database outage, null dereference hoặc mapping bug không phải duplicate conflict. Việc phân loại sai vừa làm mất khả năng quan sát vừa khiến client retry không đúng.

---

## 24. Đọc nguyên nhân SQL: SQLState, vendor code, constraint name

Một SQL constraint violation thường có các thông tin:

- SQLState.
- Vendor-specific numeric error code.
- Constraint name.
- Table/index name.
- Message của driver.
- Original SQL exception trong cause chain.

Ví dụ phổ biến (phải đối chiếu driver/DB/version mục tiêu):

| Database | Dấu hiệu thường gặp của UNIQUE violation |
|---|---|
| PostgreSQL | SQLSTATE `23505` |
| MySQL/MariaDB | Duplicate entry vendor error `1062`, SQLSTATE thường `23000` |
| SQL Server | Vendor errors như `2601`/`2627` |
| Oracle | `ORA-00001` |
| H2 | Có thể dùng `23505` trong nhiều trường hợp |

### 24.1. Không dựa vào SQLState class 23 một mình để khẳng định duplicate

`23xxx` liên quan integrity constraints, có thể gồm FK, NOT NULL, CHECK, UNIQUE. Muốn phân biệt chính xác cần code/constraint name theo driver.

### 24.2. Tên constraint rất hữu ích

`uk_product_tenant_sku` giúp trả lỗi business “SKU đã được dùng trong shop này”; `catalog_product_pkey` chỉ ra primary key conflict. Nhưng cách lấy constraint name là provider-specific và có thể khác theo dialect/driver.

### 24.3. Không parse tự do một error message thành business logic

Message text có thể thay theo locale, database version hoặc driver. Nếu không có stable code/constraint metadata, cần một cơ chế điều tra/lookup đáng tin sau rollback, không dựa vào `contains("duplicate")`.

### 24.4. Không lộ raw SQL/constraint details ra API

Log có thể lưu metadata an toàn để debug, nhưng response gửi client nên dùng mã lỗi ổn định như `PRODUCT_ID_ALREADY_EXISTS` hoặc `SKU_ALREADY_EXISTS`, không gửi SQL text có thể chứa PII.

---

## 25. Transaction sau EntityExistsException: rollback là lựa chọn mặc định an toàn

Đây là nguyên tắc quan trọng trong chương **Lỗi và phục hồi**.

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    em.persist(product);
    em.flush();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }

    throw ex;
}
```

### 25.1. Vì sao phải rollback?

Lỗi persistence trong transaction có thể đánh dấu transaction rollback-only hoặc làm persistence context không còn trạng thái tin cậy. Ngay cả khi provider/DB cho phép một số statement errors được xử lý đặc biệt, không nên mặc định có thể tiếp tục cùng transaction.

### 25.2. Với PostgreSQL, statement error thường làm transaction không dùng tiếp được

Trong transaction thông thường, sau một SQL error, các statements tiếp theo có thể báo “current transaction is aborted” cho tới rollback. Đây là một ví dụ cụ thể cho thấy catch exception **không phục hồi database transaction**.

### 25.3. Không tiếp tục dùng EntityManager sau failed flush như chưa có lỗi

Sau rollback/failed persistence operation, nên kết thúc attempt và sử dụng transaction/persistence context mới khi cần retry hoặc đọc outcome. Đừng dựa vào managed objects đã tham gia attempt thất bại để suy luận state committed.

### 25.4. Đừng chỉ gọi em.clear sau lỗi

`em.clear()` detach entities; nó **không tự rollback** database transaction, không xóa duplicate row và không sửa sequence/cascade logic.

### 25.5. Exception do business precheck khác SQL failure

Nếu service phát hiện SKU đã tồn tại **trước khi gửi INSERT**, nó có thể từ chối theo transaction policy. Nhưng nếu lỗi đã xảy ra ở flush/DB, luôn xử lý transaction state thực tế, không gộp chung với một business exception thuần.

---

## 26. Transaction resource-local với EntityManager mới cho mỗi attempt

Một skeleton an toàn:

```java
public long createOnce(
        EntityManagerFactory emf,
        CreateProductCommand command
) {
    EntityManager em = emf.createEntityManager();

    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        try {
            CatalogProduct product =
                new CatalogProduct(
                    command.id(),
                    command.tenantId(),
                    command.sku(),
                    command.name()
                );

            em.persist(product);
            em.flush();

            tx.commit();
            return product.getId();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    } finally {
        em.close();
    }
}
```

`CreateProductCommand` là DTO do ứng dụng định nghĩa.

### 26.1. Không dùng EntityTransaction khi EM được JTA quản lý

Ví dụ trên là **resource-local JPA**. Với Spring/JTA container-managed EntityManager, transaction manager quản lý begin/commit/rollback.

### 26.2. Mở context mới khi phân loại kết quả

Nếu sau duplicate cần kiểm tra existing record, hãy để original transaction rollback trước rồi dùng một **new transaction/context** hoặc repository call thích hợp. Đừng query ngay bằng một session đang lỗi.

### 26.3. Không biến exception thành success trước khi biết outcome

Nếu lỗi là duplicate PK, không có nghĩa request này đã được xử lý trước đó thành công. Có thể một user khác đã chiếm ID hoặc một data migration làm lệch generator.

---

## 27. Spring @Transactional: commit thường xảy ra sau method body

```java
@Service
public class ProductCreationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public long create(CreateProductCommand command) {
        CatalogProduct product = new CatalogProduct(
            command.id(),
            command.tenantId(),
            command.sku(),
            command.name()
        );

        em.persist(product);

        return product.getId();
    }
}
```

Method body có thể return ID trước khi transaction interceptor flush/commit. Caller chỉ có thể coi operation thành công sau khi lời gọi transactional hoàn tất không lỗi.

### 27.1. try/catch trong method có thể không bắt được commit failure

```java
@Transactional
public long create(...) {
    try {
        em.persist(product);
        return product.getId();
    } catch (EntityExistsException ex) {
        // Có thể không chạy vì lỗi xuất hiện sau method body.
    }
}
```

### 27.2. Đặt transaction boundary và classification ở hai tầng

Một kiến trúc:

```text
Controller / Coordinator
    |
    +-- gọi ProductCreationService.createOnce(...)
           | @Transactional
           | persist -> flush/commit
           v
         success / failure
    |
    +-- phân loại failure ở bên ngoài transaction
    +-- nếu cần, mở transaction mới đọc existing outcome
    +-- trả HTTP response
```

### 27.3. Self-invocation

Nếu method `@Transactional` được gọi qua `this.createOnce()` trong cùng Spring proxy-based bean, transaction advice có thể bị bypass. Cần phân tách service hoặc dùng transaction orchestration phù hợp.

### 27.4. Checked exceptions và rollback rules

Spring mặc định rollback với unchecked exceptions/errors trong nhiều cấu hình, nhưng checked exceptions và custom rollback policy cần kiểm tra. Khi persistence failure xảy ra, không “cố commit” chỉ vì một exception đã được catch.

---

## 28. Khi nào trả 409 Conflict?

Một POST create-only có thể trả `409 Conflict` nếu resource identifier/business key đã tồn tại và request không có quyền update.

| Tình huống | Hướng outcome |
|---|---|
| Client tự cấp ID, ID đã được người khác dùng | 409 hoặc domain conflict code |
| SKU đã tồn tại trong tenant | 409 hoặc mã `SKU_ALREADY_EXISTS` |
| Retry idempotent, cùng key và cùng payload đã xử lý | Trả lại outcome ban đầu theo contract |
| Cùng idempotency key nhưng payload khác | 409/validation conflict |
| Trùng ID do sequence hỏng | Lỗi hệ thống, điều tra generator; không đổ cho client |
| DB unavailable | Server error/retry policy; không giả là duplicate |
| Optimistic version stale khi update | 409/412 tùy API precondition |
| Duplicate create do two requests | Một thành công, một conflict/idempotent result |

### 28.1. 409 không phải quy tắc duy nhất

Tùy API contract, create với client-chosen URI có thể dùng `PUT` idempotent, hoặc `POST` với idempotency key; một số conflicts có thể biểu diễn bằng `422` hay các mã khác. Điều quan trọng là **semantics nhất quán**.

### 28.2. Không trả “tồn tại” nếu làm lộ tài nguyên tenant khác

Với multitenancy, một ID không thuộc authorized scope có thể được trả 404 theo security policy, thay vì “ID này thuộc tenant B”.

### 28.3. Không cần lộ constraint name trong response

`uk_product_tenant_sku` là metadata nội bộ. Response có thể là:

```json
{
  "code": "SKU_ALREADY_EXISTS",
  "message": "SKU is already used in this shop"
}
```

---

## 29. Rủi ro race của existsById và existsBySku

Sai lầm quen thuộc:

```java
if (!repository.existsById(id)) {
    repository.save(newProduct);
}
```

Hai requests đồng thời:

```text
Time      Transaction A               Transaction B
-------------------------------------------------------
T1        SELECT id=42 -> absent
T2                                    SELECT id=42 -> absent
T3        INSERT id=42
T4                                    INSERT id=42
T5        COMMIT
T6                                    PK violation / rollback
-------------------------------------------------------
```

### 29.1. Precheck chỉ cải thiện UX

Nó có thể giúp trả lỗi sớm trong phần lớn requests, nhưng không đóng race window giữa SELECT và INSERT.

### 29.2. Khóa row không tồn tại không portable

Nếu SELECT không tìm thấy row, không có existing row thông thường để áp `PESSIMISTIC_WRITE`. Một số databases có gap/key-range locking đặc thù; không suy luận JPA locking một query rỗng sẽ bảo vệ mọi concurrent inserts.

### 29.3. Database UNIQUE/PRIMARY KEY là nguồn quyết định cuối

Ngay cả khi precheck pass, INSERT có thể fail do conflict concurrent. Service phải chuẩn bị xử lý lỗi đó.

### 29.4. Precheck và authorization

Nếu `existsBySku` query không giới hạn tenant, nó có thể tiết lộ SKU của tenant khác. Hãy xây query theo authorized scope.

---

## 30. Idempotency: duplicate request khác duplicate entity

Client gửi request tạo Product:

```json
{
  "sku": "BOOK-JPA",
  "name": "Learn Persistence"
}
```

Server commit Product nhưng HTTP response mất. Client retry. Nếu server tạo Product ID mới mỗi lần, duplicate request có thể vi phạm UNIQUE SKU hoặc tạo hai records khi không có constraint.

### 30.1. Idempotency key

Client cung cấp một operation key:

```text
Idempotency-Key: create-product-req-abc123
```

Server lưu kết quả operation theo namespace phù hợp, ví dụ `(tenant_id, idempotency_key)`.

### 30.2. Một bảng operation outcome

```sql
CREATE TABLE idempotent_operation (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    operation_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    operation_status VARCHAR(32) NOT NULL,
    resource_id BIGINT,
    CONSTRAINT uk_operation_tenant_key
        UNIQUE (tenant_id, operation_key)
);
```

Tên/bộ fields là ví dụ. Một hệ thống thực cần transaction strategy, status lifecycle và expiration policy phù hợp.

### 30.3. Lần đầu

```text
BEGIN
  Claim operation key atomically
  Validate authorized request
  INSERT Product
  Store resource_id/outcome
COMMIT
```

### 30.4. Lần retry

```text
Lookup operation key
  |
  +-- Đã hoàn tất + same payload:
  |      Return stored outcome
  |
  +-- Đã tồn tại + different payload:
  |      Conflict: idempotency key reused
  |
  +-- Đang xử lý:
  |      Wait/poll/retry according to contract
  |
  +-- Chưa tồn tại:
         Claim key atomically, process
```

### 30.5. Phải bảo vệ cuộc đua hai requests cùng key

Chỉ `SELECT` check-then-insert cũng có race. UNIQUE key/atomic claim/locking cần bảo vệ operation row. Trong nhiều databases, khi gặp duplicate-key error, transaction hiện tại phải rollback trước khi đọc lại outcome ở transaction mới.

### 30.6. Unique business key không phải luôn idempotency key

Hai khách hàng có thể gửi hai requests khác nhau cùng SKU; đó là conflict, không phải hai lần của cùng operation. Không trả lại success cũ chỉ vì SKU trùng.

---

## 31. Upsert là một hợp đồng, không phải phương án cứu lỗi mặc định

Upsert nghĩa là:

> Nếu key chưa tồn tại thì INSERT; nếu đã tồn tại thì UPDATE hoặc DO NOTHING theo quy tắc định nghĩa trước.

Có thể dùng database-specific SQL, ví dụ PostgreSQL:

```sql
INSERT INTO catalog_product (
    product_id, tenant_id, sku, product_name, row_version
)
VALUES (
    :id, :tenant, :sku, :name, 0
)
ON CONFLICT (product_id)
DO NOTHING;
```

Đây là **SQL của PostgreSQL**, không phải JPQL portable.

### 31.1. Conflict target phải đúng business key

`ON CONFLICT(product_id)` xử lý PK conflict. Nếu business muốn upsert theo `(tenant_id, sku)`, phải dùng conflict target phù hợp và unique index/constraint tương ứng.

### 31.2. DO NOTHING không nghĩa “đã tạo”

Nếu row đã tồn tại, `DO NOTHING` không INSERT. Service cần kiểm tra affected rows/returning và trả outcome đúng — không báo Created mới một cách máy móc.

### 31.3. DO UPDATE có thể ghi đè dữ liệu

`ON CONFLICT ... DO UPDATE` là một **update thật**, cần authorization, expected version/merge policy, audit và concurrency contract. Không dùng chỉ để triệt duplicate-key exception.

### 31.4. Upsert bypass entity callbacks nếu dùng native SQL

Raw upsert không tự chạy JPA entity lifecycle callbacks, Bean Validation, dirty checking hay entity-level version management. Cần xử lý thêm và tránh stale persistence context/L2.

### 31.5. Portability

MySQL/MariaDB, SQL Server và Oracle có cú pháp/cơ chế khác như `ON DUPLICATE KEY` hoặc `MERGE`, với các điều kiện concurrency riêng. Không copy PostgreSQL SQL vào JPQL và kỳ vọng chạy mọi database.

---

## 32. Race giữa hai transactions và database isolation

Giả sử hai transactions muốn tạo cùng `sku=BOOK-JPA`.

```text
A: BEGIN
A: SELECT sku=BOOK-JPA -> no rows

B: BEGIN
B: SELECT sku=BOOK-JPA -> no rows

A: INSERT sku=BOOK-JPA
B: INSERT sku=BOOK-JPA  [wait/conflict tùy DB]

A: COMMIT
B: UNIQUE violation / rollback
```

### 32.1. READ COMMITTED không ngăn check-then-insert race

Mỗi SELECT có thể hợp lệ ở thời điểm nó chạy nhưng thiếu atomicity với INSERT sau.

### 32.2. REPEATABLE READ không tự bảo đảm uniqueness toàn bảng

Snapshot isolation có thể làm cả hai thấy row chưa tồn tại, nhưng UNIQUE constraint vẫn phải quyết định concurrent INSERT. Không dùng isolation label thay database index constraint.

### 32.3. SERIALIZABLE có thể yêu cầu retry

Database có thể abort một transaction vì serialization conflict. Retry phải chạy **toàn transaction** trong context mới; không dùng kết luận “SKU absent” từ snapshot cũ.

### 32.4. Unique constraint vẫn cần dù transaction isolation mạnh

Đặt UNIQUE business key là cách diễn đạt invariant trực tiếp, bảo vệ cả JDBC writers, migrations và các ứng dụng khác.

### 32.5. Khi không có natural unique key rõ

Domain phải xác định thế nào là “cùng một resource”. Không dựa vào tên/title gần giống hoặc request timestamp để tự suy ra duplicate tuyệt đối.

---

## 33. Retry: khi nào nên, khi nào không?

| Nguyên nhân | Retry nguyên request? | Ghi chú |
|---|---|---|
| ID generator tạm xung đột do triển khai lỗi | Không retry mù | Sửa generator/configuration, xác minh outcome |
| Assigned ID do client đã dùng | Thường không | Trả conflict |
| SKU trùng business key | Không tự retry | Cần user chọn SKU khác hoặc contract upsert |
| Duplicate idempotency key, cùng payload | Không làm lại side effects | Trả stored outcome |
| Duplicate idempotency key, payload khác | Không | Báo key reuse conflict |
| Deadlock/serialization failure | Có thể, giới hạn | Transaction mới + backoff + re-evaluate |
| Connection lost trước khi biết commit outcome | Cần reconciliation | Không tự giả commit thất bại |
| Validation name blank | Không | Input invalid, sửa dữ liệu |
| FK missing | Không tự | Kiểm tra reference/authorization |
| DB maintenance lock timeout | Có thể theo policy | Đừng bỏ concurrency protection |

### 33.1. Retry toàn unit of work

Không bắt một `EntityExistsException` rồi chỉ gọi `em.persist` lần nữa trên cùng entity/context bị lỗi. Nếu có retry hợp lệ, rollback attempt cũ và xây attempt mới.

### 33.2. Retry duplicate PK với ID mới có thể gây duplicate business operation

Nếu request đầu tiên đã commit nhưng response mất, retry với ID mới có thể tạo bản ghi thứ hai. Phải xác định outcome bằng idempotency key/business uniqueness trước khi sinh ID mới.

### 33.3. Backoff không thay correctness

Đợi 500ms rồi thử INSERT cùng ID/UNIQUE key vẫn sẽ fail nếu record vẫn tồn tại. Retry phải dựa trên nguyên nhân transient, không phải mọi constraint violation.

---

## 34. Phân biệt duplicate PK với optimistic lock conflict

Một UPDATE entity stale:

```text
A: load Product#42 version=5
B: load Product#42 version=5
B: update name, commit version=6
A: update name dựa trên version=5
   -> OptimisticLockException
```

Đây không phải create duplicate. A đang cố ghi thay đổi dựa vào snapshot cũ.

### 34.1. Không catch OptimisticLockException và merge mù quáng

Merge lại detached state cũ có thể overwrite update của B hoặc tiếp tục conflict. Cần reload và áp business merge policy, hoặc báo client version conflict.

### 34.2. Duplicate create xử lý khác stale update

| Operation | Lỗi đúng bản chất |
|---|---|
| INSERT id=42 khi id=42 đã tồn tại | Duplicate primary key / identity |
| INSERT id=43 nhưng SKU đã dùng | Unique business key |
| UPDATE id=42 với version cũ | Optimistic concurrency |
| DELETE id=42 đang được FK tham chiếu | Referential integrity |
| INSERT order_line tham chiếu customer không tồn tại | Foreign key violation |

### 34.3. @Version không thay UNIQUE

Hai entities mới mỗi cái có version 0 vẫn có thể cùng SKU; DB UNIQUE mới chặn conflict đó.

---

## 35. save DTO: tránh copy primary key không chủ đích

Một mapper nguy hiểm:

```java
public CatalogProduct toEntity(CreateProductRequest dto) {
    return new CatalogProduct(
        dto.id(),
        dto.tenantId(),
        dto.sku(),
        dto.name()
    );
}
```

Nếu create endpoint đáng lẽ do server cấp ID, client có thể gửi ID cũ và gây duplicate hoặc thử ghi đè.

### 35.1. Tách request DTO create và update

```java
public record CreateProductRequest(
    String sku,
    String name
) { }

public record RenameProductRequest(
    String name,
    Long expectedVersion
) { }
```

Create request không có ID nếu ID do server sở hữu.

### 35.2. Tenant được xác định server-side

```java
String tenantId = currentUser.authorizedTenantId();
```

Không tin vào client-supplied tenantId cho primary/scoped business key.

### 35.3. Update luôn load authorized entity trước

```java
CatalogProduct product = em.createQuery(
    """
    select p
    from CatalogProduct p
    where p.id = :id
      and p.tenantId = :tenant
    """,
    CatalogProduct.class
)
.setParameter("id", id)
.setParameter("tenant", tenantId)
.getSingleResult();

product.rename(request.name());
```

### 35.4. Không dùng merge của toàn object từ JSON để giải quyết ID

API layer nên kiểm soát fields được phép sửa, authorization và optimistic concurrency; `merge` không phải mass assignment guard.

---

## 36. Nhiều entities trong cùng transaction: rollback toàn bộ

Một checkout transaction:

```text
BEGIN
  INSERT SalesOrder
  INSERT OrderLine 1
  INSERT OrderLine 2  <-- PK collision
  INSERT OutboxEvent
COMMIT
```

Nếu OrderLine 2 gây duplicate PK và transaction rollback, **SalesOrder, OrderLine 1 và OutboxEvent** trong cùng database transaction cũng không được commit.

### 36.1. Không cố “giữ phần thành công” trong transaction đã hỏng

Nếu business cần partial success (ví dụ import rows độc lập), phải thiết kế transactions riêng/batch boundaries/validation policy từ đầu, không catch exception rồi commit phần còn lại tùy ý.

### 36.2. External side effects không rollback

Nếu email đã gửi ngay sau INSERT OrderLine 1, DB rollback không xóa email. Dùng outbox/after-commit theo durability requirements.

### 36.3. Idempotent rerun sau failure

Nếu transaction chắc chắn rollback, có thể xây attempt mới. Nếu commit outcome **không rõ** do connection loss, cần reconcile trước khi retry.

---

## 37. Commit outcome không rõ: tình huống khó nhất

Giả sử:

```text
Application:
  send COMMIT to DB
  network connection dies
  application cannot receive acknowledgment

Database:
  COMMIT may already have succeeded
  OR transaction may not have committed
```

Ứng dụng không thể suy từ connection error rằng transaction chắc chắn rollback.

### 37.1. Retry bằng key mới có nguy cơ duplicate

Nếu lần đầu đã commit, lần hai tạo resource mới có thể nhân đôi side effects.

### 37.2. Thiết kế để điều tra outcome

- Client-supplied idempotency key có unique constraint.
- Server-generated operation ID có persisted outcome.
- Business key/ledger entry có uniqueness.
- Reconciliation query trong **transaction/context mới**, theo authorized scope.
- Outbox/event IDs để ngăn xử lý trùng ở consumers.

### 37.3. Không khẳng định exactly once chỉ vì có @Transactional

Database transaction bảo vệ atomic writes **trong database**. HTTP delivery, external payment và message delivery không tự nằm trong transaction JPA.

### 37.4. Thiết kế response cho trạng thái chưa biết

Có thể dùng accepted/pending/reconcile outcome tùy API; tránh tự động trả Created nếu chưa có authoritative confirmation.

---

## 38. Database constraint với soft delete

Một bảng Product có `deleted_at`. Business muốn SKU chỉ unique trong các rows đang active.

Nếu constraint là:

```sql
UNIQUE (tenant_id, sku)
```

thì một Product đã soft-delete vẫn có thể chiếm SKU, ngăn tạo lại.

### 38.1. Cần định nghĩa business rule thật

- SKU unique vĩnh viễn trong tenant?
- Hay chỉ unique giữa active products?
- Có cho phép revive một deleted Product?
- Audit có yêu cầu không tái sử dụng SKU?

### 38.2. Partial unique index là database-specific

Ví dụ PostgreSQL:

```sql
CREATE UNIQUE INDEX uk_product_active_tenant_sku
ON catalog_product(tenant_id, sku)
WHERE deleted_at IS NULL;
```

Đây không phải mapping portable của `@UniqueConstraint` và không chạy y hệt mọi DB. Quản lý bằng migration/vendor-specific schema.

### 38.3. Soft delete và JPA identity

Soft-delete có thể giữ row ID; tạo Product mới cùng **ID** vẫn vi phạm PK dù active uniqueness được thiết kế cho SKU khác.

### 38.4. Filter mặc định không thay DB uniqueness

Một ORM filter chỉ query active rows không biến PK/unique index tự động thành partial uniqueness. Nếu `existsBySku` bỏ qua deleted rows nhưng database unique vẫn chặn, ứng dụng sẽ gặp lỗi sau precheck.

---

## 39. Multi-tenant và duplicate key classification

Cần phân biệt:

- Global primary key.
- Tenant-scoped natural key.
- Tenant-scoped idempotency key.
- Composite primary key có tenant.
- Resource visibility/authorization.

### 39.1. Đừng query toàn bảng sau duplicate để lộ resource của tenant khác

Nếu conflict ở global ID, handler không nên trả owner tenant/email từ bản ghi đang tồn tại trừ khi policy cho phép.

### 39.2. Dùng unique key đúng scope

`UNIQUE(tenant_id, sku)` khác `UNIQUE(sku)`. Nếu business cho mỗi shop dùng cùng SKU, global unique sẽ gây conflicts không cần thiết.

### 39.3. TenantId trong entity không tự bảo vệ quyền

`@Column(nullable=false) tenantId` chỉ nói field phải có giá trị, không xác minh người dùng có quyền ghi row đó.

### 39.4. Nếu database-per-tenant

Hai rows cùng ID ở hai databases có thể hợp lệ. Cache key/EntityManagerFactory/connection routing cần đảm bảo tenant isolation.

---

## 40. Bulk/native INSERT và JPA identity map

Native SQL:

```java
em.createNativeQuery(
    """
    INSERT INTO catalog_product(
        product_id, tenant_id, sku, product_name, row_version
    ) VALUES (:id, :tenant, :sku, :name, 0)
    """
)
.setParameter("id", 42L)
.setParameter("tenant", "shop-a")
.setParameter("sku", "BOOK-JPA")
.setParameter("name", "Persistence")
.executeUpdate();
```

Đây là SQL INSERT trong database transaction, nhưng **không tự tạo managed CatalogProduct instance** tương ứng trong L1.

### 40.1. Cùng transaction có thể tự gây duplicate

Nếu đã `em.persist(new CatalogProduct(42...))` rồi chạy native INSERT id=42, một hoặc cả hai statements có thể conflict khi flush/order SQL execution. Đừng trộn entity persistence và native writes cùng table/ID mà không có kế hoạch.

### 40.2. Native DML bypass entity lifecycle

Không tự chạy `@PrePersist`, entity Bean Validation, entity cascade hoặc managed versioning theo object lifecycle.

### 40.3. Persistence context có thể stale

Nếu native SQL cập nhật tồn tại row, managed entity trong L1 không tự refresh. Dùng context/refresh/clear có chủ đích, không lạm dụng clear khi còn unflushed changes.

### 40.4. Database constraint vẫn chặn duplicate

Native INSERT không thể vượt PRIMARY KEY/UNIQUE constraints hợp lệ chỉ vì nó bypass JPA.

---

## 41. Quan sát lỗi trên production: log gì?

Khi duplicate exception xảy ra, nên có structured logs/metrics:

- Operation type: CREATE_PRODUCT, CREATE_ORDER, IMPORT_LINE.
- Request correlation ID.
- Idempotency key fingerprint, không log secrets thô.
- Tenant identifier theo policy bảo mật.
- Entity type và key category (PK vs business unique).
- Constraint name nếu driver/provider cung cấp.
- SQLState và vendor error code.
- Exception class/cause chain rút gọn.
- Transaction attempt ID.
- Database instance/region (theo security policy).
- Provider/framework version.
- Tỷ lệ lỗi theo thời gian.

### 41.1. Không log raw JDBC SQL parameters vô tội vạ

SKU có thể không nhạy cảm, nhưng payload chứa PII, token, payment reference có thể bị lộ qua exception messages hoặc bind logs. Redact/mask theo policy.

### 41.2. Metrics cần phân loại

`product_create_duplicate_sku_total` và `product_create_duplicate_pk_total` nên là hai nhóm khác nhau; một bên có thể phản ánh expected user conflict, một bên có thể báo generator issue.

### 41.3. Alert theo bất thường

- PK collisions bất ngờ tăng trên generated IDs.
- Duplicate SKU rate tăng đột biến sau bulk import.
- Transaction rollbacks do constraints tăng sau rollout.
- Sequence cache/allocator mismatch.
- API 409 spike kèm retry storm.

### 41.4. Không coi exception count bằng số duplicate rows được tạo

Database constraints ngăn duplicate rows; metrics đo attempts thất bại, không phải duplicated committed rows.

---

## 42. Quy trình chẩn đoán theo nhánh

```text
Lỗi lúc create?
       |
       v
Có thật là EntityExistsException?
       |
       +-- Có:
       |    kiểm tra identity trong L1,
       |    state new/managed/detached,
       |    cascading persist và assigned ID.
       |
       +-- Không / provider wrapper:
            kiểm tra nested cause:
            PK / UNIQUE / FK / CHECK / network?
                  |
                  +-- PK:
                  |    assigned ID?
                  |    generator/sequence drift?
                  |    repeated persist/cascade?
                  |
                  +-- UNIQUE business key:
                  |    tenant/scope đúng?
                  |    idempotent retry hay new conflict?
                  |
                  +-- FK:
                  |    referenced entity có tồn tại?
                  |    relationship mapping đúng?
                  |
                  +-- Optimistic version:
                  |    đây là update stale, không phải INSERT duplicate
                  |
                  +-- Unknown:
                       giữ nguyên lỗi kỹ thuật,
                       điều tra thay vì gán 409.
       |
       v
Rollback attempt lỗi
       |
       v
Mở context/transaction mới nếu cần reconcile
       |
       v
Trả conflict / idempotent outcome / retryable failure
```

### 42.1. Câu hỏi chẩn đoán cụ thể

1. Operation đang là `persist` hay `merge`?
2. Entity có `@GeneratedValue` không?
3. Đối tượng là new, detached hay managed?
4. Có hai Java objects cùng ID được cascade vào context?
5. DB đã có PK đó trước request chưa?
6. Constraint nào thực sự bị vi phạm?
7. Lỗi xuất hiện ở persist, flush hay commit?
8. Transaction có rollback-only không?
9. ID từ sequence có lệch vì import/manual insert?
10. Đây có phải retry idempotent cùng operation không?
11. SKU/business key có tenant scope đúng không?
12. Một bước external đã xảy ra trước commit chưa?

---

## 43. Test 1: identity collision trong cùng persistence context

Ví dụ JUnit style:

```java
@Test
void rejectsTwoDifferentEntitiesWithSameAssignedId() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        assertThrows(
            RuntimeException.class,
            () -> {
                em.persist(new CatalogProduct(
                    42L, "shop-a", "BOOK-1", "First"
                ));

                em.persist(new CatalogProduct(
                    42L, "shop-a", "BOOK-2", "Second"
                ));

                em.flush();
            }
        );
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }
}
```

### 43.1. Vì sao assert RuntimeException thay vì luôn EntityExistsException?

Tùy JPA provider và timing, có thể là `EntityExistsException`, provider persistence exception hoặc database constraint exception. Với test contract riêng của stack, có thể assert chính xác class sau khi kiểm chứng provider.

### 43.2. Test phải bảo đảm DB fixture không vô tình trùng trước đó

Dùng isolated test database và ID dành riêng; nếu row 42 đã tồn tại từ fixture, test sẽ kiểm tra DB duplicate chứ không thuần L1 conflict.

### 43.3. Không chỉ check exception class

Sau rollback, xác nhận không có row commit từ attempt này.

### 43.4. Bản chất test

Cần dùng **hai distinct Java object instances** cùng assigned ID trong **một EntityManager**. Nếu dùng cùng instance gọi persist hai lần, đó là test khác.

---

## 44. Test 2: duplicate primary key từ database

Chuẩn bị:

```text
Tx setup:
  INSERT Product#42
  COMMIT
```

Sau đó mở EM mới:

```java
@Test
void databaseRejectsExistingPrimaryKey() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        assertThrows(
            RuntimeException.class,
            () -> {
                em.persist(new CatalogProduct(
                    42L,
                    "shop-a",
                    "BOOK-OTHER",
                    "Duplicate PK"
                ));

                em.flush();
            }
        );
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }
}
```

### 44.1. L1 chưa có Product#42 ở đầu test

Vì thế test mô phỏng DB PK conflict thay vì một instance đang managed.

### 44.2. Provider có thể SELECT/kiểm tra sớm

Một số providers/strategies có thể phát hiện tồn tại trước SQL INSERT. Dù vậy, test xác minh expected outcome là không có hai committed rows cùng primary key.

### 44.3. Không giả định lỗi chỉ ở em.flush

Đặt `persist + flush` cùng lambda để bắt các timing khác nhau. Nếu database có deferred constraint chỉ báo ở commit, test cần mở rộng tới commit/catch phù hợp.

---

## 45. Test 3: UNIQUE natural key

Setup:

```text
Product#42 tenant=shop-a sku=BOOK-JPA
```

Test thêm:

```text
Product#43 tenant=shop-a sku=BOOK-JPA
```

Expected: DB UNIQUE `uk_product_tenant_sku` từ chối. Sau rollback, số rows cùng tenant/sku vẫn bằng 1.

### 45.1. Test cùng SKU khác tenant

```text
Product#44 tenant=shop-b sku=BOOK-JPA
```

Expected: thành công nếu UNIQUE business key thật sự là `(tenant_id, sku)` và không có constraint khác cấm.

### 45.2. Test trên schema thật

Annotation `@UniqueConstraint` không tự chứng minh migration production có constraint; inspect schema/migration hoặc dùng DB integration test.

### 45.3. Test soft-delete nếu có

Nếu business cho phép tái sử dụng SKU của deleted row, kiểm tra partial unique index semantics trên target database.

---

## 46. Test 4: hai transactions cùng tạo một SKU

Kịch bản:

```text
Initial database:
  no row with (shop-a, BOOK-JPA)

Thread A / EM_A                    Thread B / EM_B
---------------------------------------------------------
BEGIN                              BEGIN
query sku absent                   query sku absent
INSERT sku=BOOK-JPA                INSERT sku=BOOK-JPA
COMMIT                              COMMIT/constraint failure
---------------------------------------------------------
Expected DB outcome:
  exactly one committed row
```

### 46.1. Hai EntityManagers độc lập

Không chia sẻ cùng `EntityManager` giữa threads. Mỗi thread có context và transaction riêng.

### 46.2. Synchronization

Dùng `CountDownLatch`/`CyclicBarrier` để cả hai readers hoàn thành precheck trước khi INSERT, tránh timing hên xui. Dùng timeouts để test không treo vô hạn.

### 46.3. Không dựa vào Thread.sleep

`Thread.sleep(100)` không xác nhận hai transactions chạy đúng interleaving. CI có scheduling khác local.

### 46.4. Kết quả test không bắt buộc “B luôn thua”

Thứ tự commit không cố định; có thể A hoặc B thành công. Assert **đúng một success** và **đúng một duplicate/conflict outcome**, không assert cố định thread thắng.

### 46.5. Kiểm tra transaction mới sau khi cả hai kết thúc

Dùng EM_C đọc row count và business values từ committed DB, không dùng detached objects của transactions thất bại.

---

## 47. Test 5: idempotent replay sau response mất

Chuẩn bị một request key `REQ-123`.

1. Request 1 dùng key này, tạo Product và commit.
2. Giả lập HTTP response không tới client.
3. Request 2 gửi lại cùng key và cùng payload.
4. Service phải trả cùng resource ID/outcome đã lưu.
5. DB chỉ có một Product tương ứng.
6. Không có duplicate outbox event/payment effect từ replay.

### 47.1. Same key, different payload

Request 3 dùng `REQ-123` nhưng name hoặc SKU khác. Expected: idempotency conflict, không silently update Product lần đầu.

### 47.2. Hai threads cùng key

Test unique operation key/atomic claim để tránh hai requests chạy đồng thời và xử lý hai side effects trước khi một bên fail.

### 47.3. Transaction outcome chưa rõ

Mô phỏng lỗi kết nối ngay lúc commit nếu framework hỗ trợ test. Phục hồi phải tra outcome bằng key, không tự create resource mới ngay lập tức.

---

## 48. Test 6: duplicate trong cascade

Setup Customer đã có ID 42.

Tạo Order chứa **new Customer(42)** và có cascade persist trên `@ManyToOne`.

Expected: có thể gặp detached/identity/PK collision. Sau khi sửa mapping và dùng managed Customer reference, Order insert thành công mà không tạo Customer mới.

### 48.1. Test cả hai phía

Kiểm tra Order.customer FK trỏ Customer#42 thực, không chỉ kiểm tra Java object reference.

### 48.2. Test không cascade REMOVE reference entity

Xóa Order không được xóa shared Customer nếu domain không cho phép.

### 48.3. Test @MapsId

Tạo hai dependent entities cùng parent ID và xác minh duplicate primary key được ngăn.

---

## 49. Debugging checklist cho một incident thực tế

Khi production log xuất hiện “EntityExistsException”:

- [ ] Giữ correlation ID và stack trace có thể truy nguyên.
- [ ] Xác định exception class chính xác, không chỉ tên rút gọn.
- [ ] Xem nested cause/SQLState/vendor code nếu có.
- [ ] Ghi nhận constraint name và entity/table nếu an toàn.
- [ ] Xác định JPA provider và version.
- [ ] Xác định điểm lỗi: persist, flush hay commit.
- [ ] Xác định method được gọi qua transaction proxy thật.
- [ ] Xác định transaction đã rollback/rollback-only.
- [ ] Không tiếp tục dùng failed EntityManager như một context sạch.
- [ ] Đối chiếu assigned ID/generated ID.
- [ ] Kiểm tra DB PK row có tồn tại trước attempt không.
- [ ] Kiểm tra natural key uniqueness và tenant scope.
- [ ] Kiểm tra cascade graph tạo object trùng ID.
- [ ] Kiểm tra DTO mapper/merge/save isNew behavior.
- [ ] Kiểm tra sequence/identity sau import và migrations.
- [ ] Kiểm tra có external JDBC/native writer không.
- [ ] Kiểm tra idempotency key, request hash và previous outcome.
- [ ] Kiểm tra có network commit ambiguity hay không.
- [ ] Không gọi raw SQL/PII details vào API response.
- [ ] Viết regression test nhỏ nhất có thể tái hiện trên DB mục tiêu.

---

## 50. Anti-pattern thường gặp

### 50.1. Catch EntityExistsException rồi tiếp tục commit

Transaction có thể đã rollback-only; cần kết thúc attempt theo trạng thái thật.

### 50.2. Dùng em.clear để “xóa conflict”

Clear chỉ detach managed objects; DB PK vẫn tồn tại.

### 50.3. Retry INSERT cùng ID vô hạn

Nếu ID đã commit, retry sẽ không sửa được gì và gây tải.

### 50.4. Dùng merge như “insert if absent” mà không định nghĩa update policy

Có thể update row người khác thay vì báo conflict.

### 50.5. Dùng Spring Data save như create-only guarantee

`save` có thể chọn persist/merge; phải biết new-detection.

### 50.6. Tự tính MAX(id)+1 trong nhiều nodes

Race tạo duplicate IDs.

### 50.7. Dùng @Version để thay DB UNIQUE

Optimistic locking không bảo vệ concurrent INSERT cùng business key.

### 50.8. Chỉ dùng existsBySku trước insert

Check-then-insert có race.

### 50.9. Không tạo UNIQUE constraint trong migration

`@UniqueConstraint` annotations có thể không làm gì khi schema production được quản lý độc lập.

### 50.10. Nhầm jakarta.validation.ConstraintViolationException với Hibernate SQL exception

Chúng giải quyết hai loại constraints khác nhau.

### 50.11. Bắt mọi PersistenceException thành 409

Có thể che database outage và programming errors.

### 50.12. Cho rằng mọi PK conflict là retry HTTP của cùng user

Có thể là ID generator hỏng, import hay một operation khác.

### 50.13. Cho rằng UUID loại bỏ nhu cầu UNIQUE

Business key vẫn có thể trùng; UUID có thể bị tái sử dụng do bug.

### 50.14. Dùng getReference như cách xác minh tồn tại và quyền

Reference không nhất thiết SELECT/authorize trước.

### 50.15. Cascade PERSIST trên shared reference entities

Có thể cố INSERT lại Customer/Country/Product.

### 50.16. Gửi notification trước commit

Transaction rollback không thu hồi email/push message.

### 50.17. Retry sau connection loss mà không reconcile

Commit có thể đã thành công; nguy cơ double create.

### 50.18. Để client tự gán tenant và ID mà không kiểm soát

Có thể lộ dữ liệu hoặc tạo xung đột xuyên tenant.

### 50.19. Trả toàn bộ SQL error cho client

Có thể lộ table names, values hoặc PII.

### 50.20. Test duplicate chỉ với một object gọi persist hai lần

Không mô phỏng hai distinct objects hoặc database collision.

### 50.21. Test trong H2 rồi coi behavior exceptions giống mọi DB

SQLState, constraint timing và provider translation khác nhau.

### 50.22. Không kiểm tra DB outcome sau test exception

Nếu test chỉ assert exception, có thể bỏ qua việc partial transaction đã commit hay dữ liệu fixture sai.

### 50.23. Dùng native UPSERT mà không quan tâm entity state/cache

Bypass callbacks và có thể làm managed entity stale.

### 50.24. Coi generated ID có giá trị là bằng chứng commit

Sequence có thể cấp ID trước INSERT; IDENTITY insert có thể vẫn rollback.

### 50.25. Bỏ qua sequence allocation khi sửa generator

Có thể phát ID trùng giữa nodes/pooled ranges.

### 50.26. Dùng FK violation như duplicate entity error

Missing referenced row là integrity issue khác, cần xử lý khác.

### 50.27. Không phân biệt hard delete và soft-delete uniqueness

Deleted row có thể vẫn chiếm natural key theo constraint.

### 50.28. Dùng cùng EntityManager giữa threads

JPA EntityManager không có contract thread-safe cho concurrent use.

### 50.29. Không rollback sau failed flush

Có thể để transaction ở trạng thái aborted và làm nhiều lỗi tiếp theo.

### 50.30. Không xử lý idempotency key reused với payload khác

Có thể trả outcome cũ cho operation không tương đương.

---

## 51. Bảng quyết định nhanh

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Hai distinct new objects cùng ID trong một EM | L1 identity collision | Không persist trùng; resolve instance/ID |
| Một new object ID đã tồn tại ở DB | PK duplicate | Rollback; create conflict hoặc sửa ID source |
| ID generated trùng liên tục sau import | Sequence/identity drift | Điều tra sequence, migration, pooling |
| Hai IDs khác nhau nhưng cùng SKU | UNIQUE business key | Rollback; trả conflict/idempotency policy |
| Customer detached được cascade persist | Cascade/reference modeling sai | Load/reference existing Customer, sửa cascade |
| Merge old entity nhận optimistic conflict | Stale update | Reload/re-evaluate hoặc conflict response |
| Retry HTTP sau response mất | Commit outcome chưa rõ | Reconcile qua idempotency key |
| SQLState 23505 PostgreSQL | UNIQUE/PK conflict | Xác định constraint nào |
| Spring Data save “mysterious update” | save dùng merge | Xem isNew policy, create/update intent |
| JPQL bulk/native write gây state khác | Bypass entity lifecycle | Context/cache/version strategy |
| Duplicate FK/shared PK child | @MapsId/composite identity collision | Xác định child lifecycle/upsert semantics |
| Business cần upsert | Explicit insert-or-update semantics | Native atomic upsert/service policy |
| Lock timeout/deadlock | Contention, không phải duplicate | Retry giới hạn transaction mới nếu phù hợp |

---

## 52. Bài tập thực hành có gợi ý

### Bài 1 — Hai Java objects

Hai `Product` objects có ID 42 nhưng `a != b`. Chúng có cùng persistent identity không?

**Gợi ý:** Có, khi cùng JPA entity type và PK trong cùng model.

### Bài 2 — find hai lần

`em.find(Product.class, 42L)` gọi hai lần trong một context.

**Đáp án:** Có thể trả cùng managed instance từ L1.

### Bài 3 — persist cùng instance

Gọi `em.persist(p)` hai lần trên cùng object đã managed.

**Gợi ý:** Không đồng nghĩa hai INSERT.

### Bài 4 — persist hai instances

`p1.id=42` và `p2.id=42`, cả hai new objects trong cùng EM.

**Gợi ý:** Identity collision, có thể bị phát hiện ở persist/flush.

### Bài 5 — database PK

DB đã có Product#42; EM mới persist Product#42.

**Gợi ý:** DB PK từ chối nếu INSERT được thực hiện, exception có thể được wrap.

### Bài 6 — natural key

Product#42 và Product#43 có cùng SKU trong tenant.

**Gợi ý:** Không phải PK conflict, nhưng UNIQUE(tenant_id,sku) có thể vi phạm.

### Bài 7 — Exception timing

`persist` return bình thường, `commit` ném lỗi.

**Gợi ý:** Persist không cam kết INSERT/commit đã hoàn tất.

### Bài 8 — EntityExistsException vs PersistenceException

Một duplicate PK có bắt buộc luôn ném `EntityExistsException` không?

**Đáp án:** Không; có thể là provider/JDBC/other PersistenceException.

### Bài 9 — SQLState

PostgreSQL báo `23505`.

**Gợi ý:** Xác định PK hay UNIQUE business key bằng constraint name; không chỉ dựa SQLState.

### Bài 10 — Bean Validation exception

`jakarta.validation.ConstraintViolationException` có phải SQL duplicate exception không?

**Đáp án:** Không; đó là bean constraint violation.

### Bài 11 — Assigned ID

Một new Product có `id=9001`, chưa tồn tại DB.

**Gợi ý:** Có ID không có nghĩa entity detached; `persist` có thể là intent đúng.

### Bài 12 — Generated ID

Entity dùng `@GeneratedValue` nhưng controller tự set ID 42.

**Gợi ý:** Không cho client can thiệp generator; sửa request mapping.

### Bài 13 — MAX(id)+1

Hai requests cùng đọc max=100.

**Gợi ý:** Cả hai có thể chọn 101; dùng sequence/generator an toàn.

### Bài 14 — Sequence drift

DB có max ID 5000 nhưng sequence còn ở 100.

**Gợi ý:** Điều tra mapping/sequence/pooling, sửa bằng maintenance plan.

### Bài 15 — UUID

Hai requests cùng SKU nhưng có UUID khác nhau.

**Gợi ý:** Vẫn là duplicate business key; UUID không thay UNIQUE.

### Bài 16 — Composite PK

OrderLine có ID (orderId=10,lineNo=1). Có thể tạo hai rows cùng key không?

**Đáp án:** Không nếu DB PK được tạo đúng.

### Bài 17 — @MapsId

Hai OrderDetails cho cùng Order.

**Gợi ý:** Shared primary key collision; xác định one-to-one lifecycle.

### Bài 18 — Cascade persist Customer

Order mới tham chiếu `new Customer(existingId)` và bật cascade PERSIST.

**Gợi ý:** Có thể cố INSERT lại Customer; nên reference managed Customer thay vì persist shared entity.

### Bài 19 — getReference

`em.getReference(Customer.class,id)` có xác minh DB row tồn tại không?

**Gợi ý:** Không nhất thiết; FK/proxy access có thể phát hiện sau.

### Bài 20 — persist vs merge

DTO create-only gặp ID trùng; có nên tự merge?

**Đáp án:** Không, có thể biến create thành update không được phép.

### Bài 21 — Spring Data save

Assigned ID mới khác null, repository.save dùng persist hay merge?

**Gợi ý:** Phụ thuộc isNew detection và mapping/version/`Persistable`, không đoán.

### Bài 22 — saveAndFlush

`saveAndFlush` return có chắc transaction đã commit không?

**Đáp án:** Không.

### Bài 23 — Flush

`em.flush` phát hiện duplicate; có thể catch rồi tiếp tục trong cùng transaction không?

**Gợi ý:** Không mặc định; rollback attempt.

### Bài 24 — PostgreSQL aborted transaction

Một INSERT gây UNIQUE error trong transaction.

**Gợi ý:** Transaction thường ở trạng thái lỗi cho tới rollback, không chỉ sửa Java object là đủ.

### Bài 25 — @Transactional commit timing

Method body return trước khi transaction manager commit.

**Gợi ý:** Exception có thể xuất hiện ngoài try/catch trong method.

### Bài 26 — Self-invocation

Spring `this.createOnce` gọi method `@Transactional`.

**Gợi ý:** Proxy advice có thể bị bypass.

### Bài 27 — Race existsBySku

A/B đều thấy SKU chưa tồn tại và cùng INSERT.

**Gợi ý:** UNIQUE constraint quyết định, một operation fail hoặc đợi.

### Bài 28 — Lock row chưa tồn tại

Có thể dùng JPA PESSIMISTIC_WRITE trên query rỗng để bảo vệ mọi concurrent inserts portable không?

**Đáp án:** Không.

### Bài 29 — Isolation

READ COMMITTED có tự làm check-then-insert atomic không?

**Đáp án:** Không.

### Bài 30 — Retry PK conflict

ID=42 đã tồn tại, retry ID=42 liên tục có ích không?

**Đáp án:** Không nếu row vẫn tồn tại.

### Bài 31 — Idempotent replay

Request key giống và payload giống đã commit.

**Gợi ý:** Trả lại stored outcome, không tạo row mới.

### Bài 32 — Key reuse khác payload

Cùng idempotency key nhưng SKU khác.

**Gợi ý:** Conflict, không xem là replay tương đương.

### Bài 33 — Response mất

Connection lỗi ngay lúc commit, có chắc rollback không?

**Đáp án:** Không, cần reconcile.

### Bài 34 — UPSERT

`ON CONFLICT DO NOTHING` có nghĩa resource mới chắc chắn được tạo không?

**Đáp án:** Không; cần affected count/returning.

### Bài 35 — Native upsert

Native SQL có tự chạy `@PrePersist` và Bean Validation không?

**Gợi ý:** Không theo entity lifecycle.

### Bài 36 — @Version

Hai transactions update cùng entity version cũ.

**Gợi ý:** Optimistic conflict khác duplicate INSERT.

### Bài 37 — Soft delete

SKU đang ở deleted row nhưng global UNIQUE vẫn cấm tái sử dụng.

**Gợi ý:** Business phải chọn uniqueness semantics; DB partial unique index có thể phù hợp nếu vendor hỗ trợ.

### Bài 38 — Multi-tenant

Tenant B gửi ID của Product thuộc tenant A.

**Gợi ý:** Không trả metadata sở hữu ngoài scope; authorization trước khi update/return.

### Bài 39 — Log errors

Có nên trả SQL duplicate message chứa constraint/value cho client?

**Gợi ý:** Không; trả domain code/message an toàn.

### Bài 40 — Test L1 collision

Tạo hai distinct Java objects với cùng assigned ID trong một EM.

**Gợi ý:** Bắt exception trong persist+flush scope, rollback, kiểm tra DB.

### Bài 41 — Test DB PK

Persist Product#42 trong Tx1 và commit; Tx2 EM mới persist Product#42.

**Gợi ý:** Kiểm tra DB constraint outcome, không nhầm L1.

### Bài 42 — Test business UNIQUE

Hai Products có IDs khác nhau nhưng cùng (tenant,sku).

**Gợi ý:** Assert không có hai committed rows, phân loại constraint.

### Bài 43 — Concurrency integration

Hai threads cùng create SKU, barrier trước INSERT.

**Gợi ý:** Không giả định A luôn thắng; assert exactly one committed row.

### Bài 44 — Cascade test

Tạo Order với Customer đã tồn tại bằng `new Customer(id)` và cascade PERSIST.

**Gợi ý:** Reproduce lỗi, sau đó sửa bằng managed reference/ownership design.

### Bài 45 — Rollback side effects

OrderLine 2 trùng PK sau khi OrderLine 1 đã insert trong cùng transaction.

**Gợi ý:** Cả transaction rollback, không còn partial rows.

### Bài 46 — Version/sequence sau import

Một migration nhập explicit IDs và đổi sequence allocation.

**Gợi ý:** Test generated IDs trên target DB, tránh collision trước production deploy.

### Bài 47 — API create vs update

Client gửi POST create với ID đã tồn tại.

**Gợi ý:** Trả conflict hoặc idempotent outcome theo contract, không tự update.

### Bài 48 — DuplicateKeyException trong Spring

Repository ném `DataIntegrityViolationException`.

**Gợi ý:** Xem nested cause/constraint, không mặc định mọi integrity error là duplicate PK.

### Bài 49 — Deferred constraint

Flush pass nhưng commit fail vì constraint.

**Gợi ý:** Chỉ coi operation thành công sau commit, không gửi external event sớm.

### Bài 50 — Thiết kế incident runbook

Lập một danh sách 10 dữ kiện cần thu thập khi generated ID trùng liên tục.

**Gợi ý:** Entity, PK, constraint name, SQLState, generator type, sequence state, max DB ID, provider version, import history, allocation strategy và transaction outcome.

---

## 53. Checklist triển khai

Trước khi merge luồng tạo entity, kiểm tra:

- [ ] Đã xác định rõ API là create-only, update-only, upsert hay idempotent create.
- [ ] Entity có primary key mapping và generator strategy đúng.
- [ ] Client không được tự đặt ID khi ID do server/DB sở hữu.
- [ ] Không dùng `MAX(id)+1` trong môi trường concurrent.
- [ ] Khi dùng assigned ID có allocator/authority rõ.
- [ ] Khi dùng sequence đã kiểm tra imports, increments và allocation size.
- [ ] Khi dùng `@EmbeddedId` có equality và key allocation đúng.
- [ ] Khi dùng `@MapsId` hiểu shared primary key lifecycle.
- [ ] Không cascade persist shared reference entities vô ý.
- [ ] Không dùng merge để chữa duplicate create một cách mù quáng.
- [ ] Spring Data `isNew` policy được hiểu và kiểm thử.
- [ ] Database PRIMARY KEY và UNIQUE business constraints được migrate.
- [ ] Uniqueness có đúng tenant/soft-delete scope.
- [ ] Precheck `exists` chỉ là UX optimization, không thay DB constraints.
- [ ] Exception handler phân biệt PK, UNIQUE, FK, Bean Validation và optimistic conflicts.
- [ ] Bắt lỗi ở boundary bao trùm flush/commit timing.
- [ ] Rollback transaction sau persistence failure.
- [ ] Không tiếp tục dùng failed persistence context.
- [ ] Khi retry phải dùng transaction mới và re-evaluate state.
- [ ] Không retry mù duplicate PK/UNIQUE violations.
- [ ] Có idempotency key cho những operations cần chống replay.
- [ ] Cùng idempotency key nhưng payload khác phải bị xử lý rõ.
- [ ] Có reconciliation khi commit outcome không rõ.
- [ ] Không gửi email/payment/event trước commit nếu không có compensation strategy.
- [ ] Có structured logs/metrics nhưng không leak SQL parameters/PII.
- [ ] Có integration tests cho same-context collision và database PK conflict.
- [ ] Có concurrency test hai EMs/transactions cùng UNIQUE key.
- [ ] Có test generated IDs sau data import/restore.
- [ ] Có test rollback atomicity khi transaction ghi nhiều entities.
- [ ] Có test tenant authorization và soft-delete uniqueness.
- [ ] Có plan xử lý duplicate spikes và sequence drift production.

## 54. Bảng tra cứu nhanh

| Câu hỏi | Câu trả lời |
|---|---|
| JPA identity-exists exception? | `jakarta.persistence.EntityExistsException` |
| Gọi persist entity đã managed? | Không tạo entity mới lần hai |
| Hai objects cùng PK trong L1? | Identity collision, provider có thể báo lỗi |
| PK đã tồn tại ở database? | DB từ chối INSERT, exception có thể được wrap |
| SKU trùng nhưng PK khác? | UNIQUE business key violation |
| Lỗi có chắc ở persist? | Không; có thể flush/commit |
| Flush đã commit chưa? | Chưa |
| Có thể catch rồi tiếp tục transaction? | Không nên; rollback attempt lỗi |
| em.clear có xóa PK conflict? | Không |
| persist và merge giống nhau? | Không |
| merge là upsert an toàn? | Không, cần contract rõ |
| Spring Data save luôn INSERT? | Không; có thể persist hoặc merge |
| @GeneratedValue ID đã có nghĩa commit? | Không |
| MAX(id)+1 dùng cho concurrent writes? | Không an toàn |
| Sequence bị lệch sau import? | Điều tra DB sequence + provider allocation |
| UUID có thay UNIQUE SKU? | Không |
| @Version ngăn duplicate INSERT? | Không |
| @EmbeddedId bị trùng? | Composite PK conflict |
| @MapsId shared key? | Child dùng PK liên quan parent |
| Cascade persist reference entity đã có? | Có thể gây detached/duplicate error |
| getReference xác minh tồn tại? | Không nhất thiết |
| existsBySku tránh race? | Không |
| DB constraint quan trọng nhất? | PRIMARY KEY / UNIQUE |
| PostgreSQL duplicate SQLSTATE? | Thường `23505` |
| Bean Validation exception? | `jakarta.validation.ConstraintViolationException` |
| Hibernate DB constraint exception? | `org.hibernate.exception.ConstraintViolationException` |
| Spring integrity translation? | `DataIntegrityViolationException` hoặc subtype |
| Upsert chuẩn JPQL portable? | Không có cùng cú pháp native `ON CONFLICT` |
| UPSERT DO NOTHING có tạo mới? | Không khi conflict |
| HTTP duplicate create response? | 409 hoặc idempotent outcome theo contract |
| Retry duplicate key? | Không retry mù |
| Retry deadlock/serialization? | Có thể trong transaction mới, có giới hạn |
| Commit response mất? | Reconcile bằng idempotency/business key |
| Soft-delete uniqueness? | Thiết kế DB constraint theo business scope |
| Multi-tenant duplicate? | Bảo vệ tenant scope và authorization |
| Test L1 collision? | Hai distinct objects cùng PK trong một EM |
| Test DB collision? | Row commit trước, EM mới INSERT cùng PK |
| Test concurrent creates? | Hai EM/transactions, UNIQUE final count |
| Log constraint details? | Có kiểm soát, không lộ PII/API internals |

## 55. Tổng kết

1. **`EntityExistsException` liên quan việc cố persist một entity có persistent identity đã tồn tại**, nhưng không phải mọi duplicate PK/UNIQUE đều bắt buộc được biểu diễn bằng đúng exception này.
2. **Persistence context identity collision** và **database primary-key conflict** là hai tình huống khác nhau: một có thể được phát hiện trong L1, một được DB xử lý khi ghi.
3. **UNIQUE business key conflict không đồng nghĩa primary key conflict**. Hai entities có IDs khác nhau vẫn có thể trùng SKU trong cùng tenant.
4. **`persist` dành cho new entity**, `merge` copy detached/new state vào managed instance theo contract khác; không chuyển create conflict thành update tùy tiện.
5. **Exception có thể xuất hiện tại persist, flush hoặc commit**. Chỉ coi create thành công sau khi commit thành công.
6. **Rollback attempt sau persistence failure** và dùng transaction/context mới khi cần reconcile hoặc retry; `em.clear()` không sửa database conflict.
7. **Database PRIMARY KEY/UNIQUE constraints là hàng rào cuối**, bảo vệ cả concurrent requests, native SQL, batch jobs và external writers.
8. **Không dùng `MAX(id)+1` hoặc retry mù** để khắc phục duplicate; generated ID collisions cần điều tra sequence/identity/import/allocator.
9. **Cascading persist, @MapsId, composite keys và Spring Data save state detection** là những nguồn duplicate không hiển nhiên.
10. **@Version xử lý stale updates, không thay uniqueness constraints**.
11. **Idempotency key giải quyết replay của cùng một business operation**, khác với việc SKU/ID tình cờ đã tồn tại.
12. **Commit outcome không rõ do lỗi kết nối phải được reconcile** trước khi tạo lại resource hoặc phát side effects.
13. **Phân loại exception dựa trên cause/constraint**, không catch mọi persistence error rồi trả 409.
14. **Kiểm thử cả same-context và cross-transaction scenarios** trên database/provider mục tiêu, xác minh database state sau rollback/commit.

**Kết luận:** Xử lý `EntityExistsException` đúng không đơn giản là đặt một khối `try/catch` quanh `em.persist`. Cần phân biệt **identity đang được quản lý**, **khóa chính đã tồn tại trong database**, **khóa nghiệp vụ bị trùng**, và **request được gửi lại**. Khi mô hình hóa rõ create/update/idempotency contracts, giữ PRIMARY KEY/UNIQUE constraints trong database, kiểm soát transaction rollback và phục hồi bằng attempt mới có reconciliation, hệ thống có thể từ chối duplicate một cách chính xác mà không vô tình ghi đè dữ liệu hoặc thực hiện nghiệp vụ hai lần.
