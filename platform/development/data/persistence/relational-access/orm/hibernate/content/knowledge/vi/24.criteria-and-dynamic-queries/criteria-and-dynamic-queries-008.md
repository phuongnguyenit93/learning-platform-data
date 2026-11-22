# CriteriaUpdate, CriteriaDelete và quy tắc đồng bộ context trong Hibernate ORM

Trong Jakarta Persistence, **Criteria API** không chỉ dùng để tạo câu `SELECT` động. API còn cung cấp hai kiểu truy vấn ghi:

- **`CriteriaUpdate<T>`**: xây dựng một lệnh bulk `UPDATE` trên entity `T`.
- **`CriteriaDelete<T>`**: xây dựng một lệnh bulk `DELETE` trên entity `T`.

Nhờ đó, ứng dụng có thể tạo các điều kiện cập nhật hoặc xóa theo thời điểm chạy mà không phải nối chuỗi JPQL/HQL. Chẳng hạn, một tác vụ bảo trì catalog có thể vô hiệu hóa sản phẩm ngừng kinh doanh theo tenant và ngày cắt; một công việc dọn dẹp có thể xóa token hết hạn.

Điểm quan trọng nhất: **CriteriaUpdate và CriteriaDelete thực thi bulk DML trực tiếp trên database; chúng không cập nhật các object Java đang managed trong Persistence Context và không đi qua vòng đời entity như setter + dirty checking hoặc `EntityManager.remove()`.**

Điều này tác động đến:

1. **First-level cache/Persistence Context**: entity đã tải có thể giữ dữ liệu cũ sau bulk DML.
2. **`@Version` và optimistic locking**: version không tự được kiểm tra/tăng như khi Hibernate flush managed entity.
3. **Lifecycle callbacks**: `@PreUpdate`, `@PreRemove`, listener audit không được gọi lần lượt cho từng entity bị tác động.
4. **Cascade và orphan removal**: bulk delete không tương đương gọi `remove()` trên từng root.
5. **Ràng buộc database và cache**: FK, trigger, transaction vẫn hoạt động, nhưng chiến lược đồng bộ với Hibernate cần được hiểu rõ.

Bài học tập trung vào **cách tạo CriteriaUpdate/CriteriaDelete đúng và quy tắc xử lý Persistence Context trước, trong và sau bulk DML**. Các ví dụ dùng Java, Jakarta Persistence và Hibernate; phần Spring Data JPA là một tích hợp thường gặp, không phải yêu cầu bắt buộc của Criteria API.

---

## 1. Vị trí của CriteriaUpdate và CriteriaDelete trong Criteria API

Một query đọc thông thường dùng `CriteriaQuery<T>`:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Product> query =
    cb.createQuery(Product.class);

Root<Product> product = query.from(Product.class);

query.select(product)
     .where(cb.isTrue(product.get("active")));

List<Product> results =
    entityManager.createQuery(query).getResultList();
```

Ở đây, query lấy các `Product` và Hibernate đưa những entity phù hợp vào persistence context khi cần.

Bulk update dùng `CriteriaUpdate<Product>`:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> product = update.from(Product.class);

update.set(product.<Boolean>get("active"), false);
update.where(cb.equal(product.get("id"), productId));

int affected = entityManager
    .createQuery(update)
    .executeUpdate();
```

Bulk delete dùng `CriteriaDelete<Product>`:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaDelete<Product> delete =
    cb.createCriteriaDelete(Product.class);

Root<Product> product = delete.from(Product.class);

delete.where(cb.equal(product.get("id"), productId));

int affected = entityManager
    .createQuery(delete)
    .executeUpdate();
```

### 1.1. Bảng so sánh ba loại Criteria

| Tiêu chí | `CriteriaQuery<T>` | `CriteriaUpdate<T>` | `CriteriaDelete<T>` |
|---|---|---|---|
| Mục đích | Đọc dữ liệu | Cập nhật tập hàng | Xóa tập hàng |
| Tạo bằng | `cb.createQuery(...)` | `cb.createCriteriaUpdate(...)` | `cb.createCriteriaDelete(...)` |
| Chỉ định entity root | `from(...)` | `from(...)` | `from(...)` |
| Chỉ định dữ liệu | `select`/`multiselect` | `set` | Không có `set` |
| Điều kiện | `where` | `where` | `where` |
| Thực thi | `getResultList()`/`getSingleResult()` | `executeUpdate()` | `executeUpdate()` |
| Kết quả thường gặp | Entity/DTO/scalar | Số lượng tác động | Số lượng tác động |
| Đồng bộ managed objects | Entity được load theo cơ chế context | Không tự đồng bộ object đã load | Không tự remove object đã load |

`CriteriaUpdate` và `CriteriaDelete` đại diện cho **bulk mutation**, không phải một tập entity đang chờ dirty checking.

### 1.2. Vì sao gọi là bulk ngay cả khi WHERE chỉ khớp một hàng?

“Bulk” mô tả **đường thực thi**, không phải điều kiện phải sửa nhiều row. Ví dụ:

```java
delete.where(cb.equal(root.get("id"), 42L));
```

Nếu chỉ có một row được xóa, nó vẫn là bulk CriteriaDelete: Hibernate không tải entity rồi gọi `remove(entity)`. Vì thế các giới hạn về context, version và callback vẫn áp dụng.

## 2. Mô hình entity dùng trong bài

Giả sử có bảng `products` trong ứng dụng đa tenant:

```java
import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Column(name = "discontinued_at")
    private Instant discontinuedAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public boolean isActive() {
        return active;
    }

    public long getVersion() {
        return version;
    }

    public void deactivate() {
        active = false;
    }

    public void changePrice(BigDecimal newPrice) {
        price = newPrice;
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = Instant.now();
    }
}
```

Có ba đặc điểm quan trọng:

- `tenantId` giúp giới hạn dữ liệu được cập nhật theo tenant.
- `@Version` dùng cho optimistic locking ở đường managed-entity update.
- `@PreUpdate` cập nhật thời gian sửa khi entity trải qua lifecycle update tương ứng.

Sau đây, ta sẽ thấy bulk CriteriaUpdate **không tự gọi `updateTimestamp()`**, cũng **không tự tăng version** nếu không có xử lý tường minh.

Ví dụ giả định dự án có EntityManager, Spring transaction nếu dùng service và các migration/schema tương ứng. Các đoạn code độc lập minh họa từng API; khi ghép vào ứng dụng cần thêm imports, DTO, exception và dependency injection phù hợp.

## 3. CriteriaUpdate: tạo lệnh UPDATE theo cấu trúc typed API

Quy trình cơ bản:

1. Lấy `CriteriaBuilder`.
2. Tạo `CriteriaUpdate<Product>`.
3. Tạo root bằng `update.from(Product.class)`.
4. Gọi `set(...)` cho một hoặc nhiều thuộc tính.
5. Xây dựng `Predicate` trong `where(...)`.
6. Thực thi `entityManager.createQuery(update).executeUpdate()`.

### 3.1. Ví dụ vô hiệu hóa sản phẩm ngừng bán

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.*;

import java.time.Instant;
import java.util.UUID;

public int deactivateProducts(
        EntityManager em,
        UUID tenantId,
        Instant cutoff,
        Instant now) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaUpdate<Product> update =
        cb.createCriteriaUpdate(Product.class);

    Root<Product> product = update.from(Product.class);

    update.set(product.<Boolean>get("active"), false);
    update.set(product.<Instant>get("updatedAt"), now);

    Predicate sameTenant = cb.equal(
        product.get("tenantId"),
        tenantId
    );

    Predicate currentlyActive = cb.isTrue(
        product.<Boolean>get("active")
    );

    Predicate discontinuedBefore = cb.lessThan(
        product.<Instant>get("discontinuedAt"),
        cutoff
    );

    update.where(
        cb.and(
            sameTenant,
            currentlyActive,
            discontinuedBefore
        )
    );

    return em.createQuery(update).executeUpdate();
}
```

Câu HQL tương đương về ý định:

```sql
update Product p
set p.active = false,
    p.updatedAt = :now
where p.tenantId = :tenantId
  and p.active = true
  and p.discontinuedAt < :cutoff
```

Hibernate chuyển mô hình Criteria sang câu SQL update trên bảng và cột vật lý tương ứng.

### 3.2. `Root<Product>` không phải object Product

`Root<Product> product` là một **node mô tả entity trong câu query**, không phải instance Product lấy từ database.

Vì thế:

```java
update.set(product.<Boolean>get("active"), false);
```

không gọi `Product.deactivate()` trên từng row. Nó thêm một phép gán vào cấu trúc UPDATE.

### 3.3. Thêm nhiều phép SET

Có thể gọi `set` nhiều lần:

```java
update.set(product.<Boolean>get("active"), false);
update.set(product.<Instant>get("updatedAt"), now);
update.set(product.<String>get("name"), "ARCHIVED");
```

Tuy nhiên, các phép gán phải hợp lệ theo mapping, kiểu thuộc tính và quy tắc update của provider. Không nên cập nhật hàng loạt những trường đóng vai trò định danh hoặc khóa ngoại quan trọng nếu domain không cho phép.

## 4. Dùng biểu thức trong CriteriaUpdate.set

`set` không chỉ nhận literal; nó còn có thể nhận `Expression`.

Ví dụ tăng giá theo tỷ lệ:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

Expression<BigDecimal> newPrice = cb.prod(
    p.<BigDecimal>get("price"),
    new BigDecimal("1.05")
);

update.set(p.<BigDecimal>get("price"), newPrice);
update.where(
    cb.equal(p.get("tenantId"), tenantId),
    cb.isTrue(p.<Boolean>get("active"))
);

int changed = em.createQuery(update).executeUpdate();
```

Đây là phép tính trực tiếp trong database theo kiểu numeric mapping. Với tiền tệ, vẫn cần chính sách làm tròn, scale và constraint rõ ràng; không giả định phép nhân sẽ cho kết quả nghiệp vụ mong muốn ở mọi dialect.

### 4.1. SET expression khác cập nhật Java

Không có chuyện Hibernate tải từng Price, nhân trong Java rồi gọi setter. Database đánh giá expression, với semantics về `NULL` và kiểu số của chính DB/SQL được sinh ra.

### 4.2. Thao tác cộng dồn

Một ví dụ khác là tăng bộ đếm:

```java
CriteriaUpdate<InventoryCounter> update =
    cb.createCriteriaUpdate(InventoryCounter.class);

Root<InventoryCounter> c =
    update.from(InventoryCounter.class);

update.set(
    c.<Long>get("totalRequests"),
    cb.sum(c.<Long>get("totalRequests"), 1L)
);

update.where(cb.equal(c.get("id"), counterId));
```

Cách này có thể tránh race condition kiểu đọc giá trị, tăng trong Java rồi ghi lại. Tuy nhiên nó vẫn là bulk path, không gọi callbacks và cần version/transaction rule phù hợp nếu có các cập nhật khác.

## 5. Tạo điều kiện động mà không nối chuỗi JPQL

Điểm mạnh lớn nhất của Criteria API là điều kiện có thể được cấu thành từ dữ liệu optional.

Ví dụ bộ lọc bảo trì:

```java
public record DeactivationFilter(
    UUID tenantId,
    Instant discontinuedBefore,
    BigDecimal minimumPrice,
    boolean onlyCurrentlyActive
) {}
```

Xây predicate:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);
update.set(p.<Instant>get("updatedAt"), now);

List<Predicate> predicates = new ArrayList<>();

// Giới hạn tenant luôn bắt buộc, không tùy chọn.
predicates.add(
    cb.equal(p.get("tenantId"), filter.tenantId())
);

if (filter.discontinuedBefore() != null) {
    predicates.add(
        cb.lessThan(
            p.<Instant>get("discontinuedAt"),
            filter.discontinuedBefore()
        )
    );
}

if (filter.minimumPrice() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            p.<BigDecimal>get("price"),
            filter.minimumPrice()
        )
    );
}

if (filter.onlyCurrentlyActive()) {
    predicates.add(cb.isTrue(p.<Boolean>get("active")));
}

update.where(
    cb.and(predicates.toArray(new Predicate[0]))
);

int changed = em.createQuery(update).executeUpdate();
```

Các điểm cần lưu ý:

- Các điều kiện được thêm có chủ đích, không phải nối input tùy ý thành cú pháp SQL.
- `tenantId` được giữ bắt buộc để tránh cập nhật dữ liệu tenant khác.
- Predicate rỗng có thể dẫn tới lệnh UPDATE tác động toàn bộ tập hàng. Với mutation, cần đặt **rào chắn an toàn** khi thiếu điều kiện quan trọng.
- `NULL` trong SQL có logic riêng: `discontinuedAt < :cutoff` không chọn các hàng có `discontinuedAt IS NULL`.

### 5.1. Sử dụng ParameterExpression

Để tách query structure khỏi giá trị:

```java
ParameterExpression<Instant> cutoffParam =
    cb.parameter(Instant.class, "cutoff");

update.where(
    cb.equal(p.get("tenantId"), tenantId),
    cb.lessThan(
        p.<Instant>get("discontinuedAt"),
        cutoffParam
    )
);

jakarta.persistence.Query query =
    em.createQuery(update);

int changed = query
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

`ParameterExpression` hữu ích khi tái sử dụng cách dựng query, cần kiểu rõ và muốn dùng named parameters giống JPQL/HQL.

### 5.2. Criteria API không tự giải quyết authorization

Predicate động an toàn về cấu trúc không có nghĩa truy vấn có đúng scope nghiệp vụ. Nếu quên điều kiện tenant, project hoặc permission, lệnh có thể sửa nhiều row ngoài dự kiến.

Với mutation, nên mô hình hóa ràng buộc phạm vi như một phần bắt buộc của repository/application service contract.

## 6. CriteriaDelete: xóa dữ liệu theo predicate

Quy trình tương tự CriteriaUpdate nhưng không có `set`.

Ví dụ xóa token hết hạn:

```java
@Entity
@Table(name = "reset_tokens")
public class ResetToken {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private Instant expiresAt;

    @Column(nullable = false)
    private boolean used;
}
```

Code dọn dẹp:

```java
public int deleteExpiredTokens(
        EntityManager em,
        UUID tenantId,
        Instant cutoff) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaDelete<ResetToken> delete =
        cb.createCriteriaDelete(ResetToken.class);

    Root<ResetToken> token =
        delete.from(ResetToken.class);

    delete.where(
        cb.equal(token.get("tenantId"), tenantId),
        cb.lessThan(
            token.<Instant>get("expiresAt"),
            cutoff
        )
    );

    return em.createQuery(delete).executeUpdate();
}
```

Tương đương ý định:

```sql
delete from ResetToken t
where t.tenantId = :tenantId
  and t.expiresAt < :cutoff
```

Không có `List<ResetToken>` được trả về. Database xóa các hàng khớp điều kiện; các token object đã managed trong EntityManager vẫn có thể giữ state cũ.

### 6.1. Delete và deactivate không giống nhau

Nếu muốn giữ lịch sử, đừng dùng CriteriaDelete chỉ vì API có sẵn. Soft delete thường là CriteriaUpdate:

```java
CriteriaUpdate<Product> softDelete =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = softDelete.from(Product.class);

softDelete.set(p.<Boolean>get("active"), false);
softDelete.where(cb.equal(p.get("id"), productId));
```

Đây là bulk UPDATE, không phải lời gọi entity `remove()`. Những mapping soft delete đặc thù Hibernate phải được kiểm tra theo version và đường DML thật; không giả định CriteriaDelete tự chuyển thành cùng workflow xóa mềm của entity.

## 7. Giới hạn mô hình FROM và JOIN trong bulk Criteria

Một `CriteriaQuery` cho SELECT có thể định nghĩa nhiều root, join, select expression và order.

Với `CriteriaUpdate` / `CriteriaDelete`, nguồn DML được tập trung vào **một entity root mục tiêu**. Bulk DML chuẩn có giới hạn về join tại update/delete root; không thể bê nguyên một Criteria SELECT có nhiều root/join sang mutation.

Ví dụ không nên suy luận:

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

// Không xem việc join tùy ý ở UPDATE root
// là cú pháp portable trên mọi provider:
Join<Product, Category> category = p.join("category");
```

Quy tắc portable là không dùng JOIN tùy tiện trên target root của bulk UPDATE/DELETE. Khi cần điều kiện dựa vào entity khác, hãy xem xét **subquery** hoặc association path hợp lệ trong giới hạn grammar/provider.

### 7.1. Subquery cho điều kiện liên quan

Ví dụ xóa token có ID nằm trong danh sách token đã bị thu hồi. Giả định entity `RevokedToken` có thuộc tính `tokenId` cùng kiểu UUID:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<ResetToken> delete =
    cb.createCriteriaDelete(ResetToken.class);

Root<ResetToken> token =
    delete.from(ResetToken.class);

Subquery<UUID> revokedIds =
    delete.subquery(UUID.class);

Root<RevokedToken> revoked =
    revokedIds.from(RevokedToken.class);

revokedIds.select(revoked.<UUID>get("tokenId"));

delete.where(
    cb.equal(token.get("tenantId"), tenantId),
    token.<UUID>get("id").in(revokedIds)
);

int affected = em.createQuery(delete).executeUpdate();
```

Subquery nằm trong điều kiện và tham chiếu entity `RevokedToken` qua chính root của subquery. Database chịu trách nhiệm chọn tập token phù hợp.

Tùy database và Hibernate version, cách render `IN (subquery)` hoặc các biểu thức correlated subquery có thể khác; cần xác nhận SQL sinh ra nếu dùng cấu trúc nâng cao.

### 7.2. Không dùng fetch join cho bulk mutation

`JOIN FETCH` nhằm nạp association của entity được SELECT. Bulk UPDATE/DELETE không trả object graph để fetch, vì vậy fetch join không có vai trò tương ứng.

Nếu cần xử lý từng child và lifecycle callback, hãy chọn entity operation path hoặc chia workflow theo từng aggregate thay vì tìm cách fetch join trong CriteriaDelete.

### 7.3. Không có ORDER BY/LIMIT portable trên CriteriaDelete

Bulk CriteriaDelete chuẩn mô tả điều kiện xóa chứ không cung cấp API phân trang root như CriteriaQuery.

Muốn xóa từng chunk:

- Chọn ID theo `CriteriaQuery`/SELECT với thứ tự ổn định và giới hạn phù hợp.
- Dùng CriteriaDelete với `id IN :ids` cho chunk đã chọn.
- Lặp và xác định transaction boundary/retry.
- Chấp nhận rằng thay đổi dữ liệu đồng thời có thể làm tập ID khác đi, trừ khi thiết kế locking/snapshot thích hợp.

Không nối “limit 100” vào CriteriaDelete rồi mặc định mọi DB/dialect đều hỗ trợ.

## 8. Quy tắc đồng bộ context: vấn đề trung tâm

**Persistence Context** là tập managed entities và trạng thái theo dõi của một `EntityManager`/`Session`.

Ví dụ:

```java
Product first = em.find(Product.class, 10L);
Product again = em.find(Product.class, 10L);

System.out.println(first == again); // Thường true.
```

Trong cùng context, Hibernate thường trả cùng một managed instance cho cùng entity type + ID. Context lưu snapshot, state và thông tin phục vụ dirty checking.

### 8.1. Điều gì xảy ra sau CriteriaUpdate?

Giả sử Product#10 ở database:

```text
id = 10
active = true
version = 3
```

Code:

```java
Product managed = em.find(Product.class, 10L);

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);
update.where(cb.equal(p.get("id"), 10L));

em.createQuery(update).executeUpdate();

System.out.println(managed.isActive());
```

Kết quả **có thể vẫn là `true`** dù row trong database đã được set `active=false`.

Sơ đồ:

```text
Trước bulk:
    Persistence Context              Database
    Product#10.active = true    <--> Product#10.active = true

Bulk CriteriaUpdate:
    UPDATE products SET active = false WHERE id = 10

Sau bulk:
    Persistence Context              Database
    Product#10.active = true         Product#10.active = false
             ^
             |
       managed object stale
```

Hibernate không duyệt tất cả managed `Product` để thay field theo CriteriaUpdate, vì mutation được thực thi ở database dựa trên predicate.

### 8.2. CriteriaDelete còn nguy hiểm hơn nếu tiếp tục dùng object cũ

```java
Product managed = em.find(Product.class, 10L);

CriteriaDelete<Product> delete =
    cb.createCriteriaDelete(Product.class);

Root<Product> p = delete.from(Product.class);

delete.where(cb.equal(p.get("id"), 10L));

em.createQuery(delete).executeUpdate();

// managed vẫn là tham chiếu Java đã tồn tại;
// nó không được tự chuyển thành Removed bởi bulk delete.
```

Nếu tiếp tục đọc getter, code có thể thấy dữ liệu cũ; nếu sửa entity rồi flush, có thể gặp stale-state/optimistic-locking exception hoặc lỗi vì row đã bị xóa.

### 8.3. `find()` lại trong cùng context chưa chắc tải dữ liệu mới

```java
Product a = em.find(Product.class, 10L);

executeBulkCriteriaUpdate();

Product b = em.find(Product.class, 10L);
```

`b` thường chính là object `a` từ identity map. Việc gọi `find()` không bảo đảm tạo SELECT mới hay đồng bộ state.

**Giải pháp phải tác động đến trạng thái context**, không chỉ gọi lại API tìm entity.

## 9. Pattern flush → bulk DML → clear

Một quy trình phổ biến khi muốn trộn thay đổi managed với bulk mutation là:

```text
1. FLUSH các thay đổi managed phải được giữ
            |
            v
2. EXECUTE UPDATE/DELETE trực tiếp trong DB
            |
            v
3. CLEAR context nếu cần tránh object stale
            |
            v
4. RELOAD entity trong context mới/đã clear khi cần
```

Ví dụ:

```java
@Transactional
public int deactivateAndReloadContext(Instant cutoff) {
    // Các thay đổi managed đã chuẩn bị từ trước:
    em.flush();

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaUpdate<Product> update =
        cb.createCriteriaUpdate(Product.class);

    Root<Product> p = update.from(Product.class);

    update.set(p.<Boolean>get("active"), false);
    update.where(
        cb.lessThan(
            p.<Instant>get("discontinuedAt"),
            cutoff
        )
    );

    int affected = em.createQuery(update).executeUpdate();

    em.clear();

    return affected;
}
```

Đây là **một pattern có chủ đích**, không phải yêu cầu phải gọi đủ ba thao tác sau mọi CriteriaUpdate/CriteriaDelete.

### 9.1. Khi nào cần flush trước?

Khi context có những thay đổi managed chưa được gửi xuống database và:

- Bulk predicate phải thấy các thay đổi ấy.
- Bulk DML phụ thuộc thứ tự ghi trước đó.
- Code định `clear()` nhưng muốn giữ các thay đổi pending.

Ví dụ:

```java
Product product = em.find(Product.class, id);
product.changePrice(new BigDecimal("90.00"));

// Nếu bulk predicate dựa trên price, DB cần thấy giá mới.
em.flush();

executeBulkUpdateForExpensiveProducts();
```

Hibernate có các cơ chế auto-flush theo flush mode và query spaces, nhưng khi correctness phụ thuộc thứ tự, explicit flush giúp ý định rõ ràng.

### 9.2. Flush không phải commit

`em.flush()` gửi các DML pending xuống DB trong transaction; **nó không tự commit**. Nếu cuối transaction rollback, những thay đổi đã flush cũng có thể rollback cùng bulk SQL.

### 9.3. Clear sau DML giải quyết điều gì?

`em.clear()` detach toàn bộ entity trong persistence context. Sau đó, `em.find(Product.class, id)` có thể tải lại state mới từ database thay vì trả entity managed cũ.

Nhưng:

- `clear()` không sửa các object Java đã giữ trong biến.
- Những object cũ trở thành detached, có thể vẫn mang giá trị stale.
- `clear()` tác động **toàn context**, không chỉ loại entity Product.
- Các thay đổi chưa flush có thể bị mất cơ hội đồng bộ tự động.

### 9.4. Đừng dùng clear khi chưa hiểu pending state

```java
Order order = em.find(Order.class, orderId);
order.changeStatus("APPROVED");

executeProductBulkUpdate();

em.clear(); // Có thể detach order trước khi update được flush.
```

Nếu thay đổi `order` chưa flush, transaction commit sau `clear()` không nhất thiết ghi nó. Mất thay đổi có thể xảy ra âm thầm.

Khi transaction đang quản lý nhiều aggregate khác nhau, thường tốt hơn là **tách bulk mutation thành transaction chuyên biệt**, thay vì clear toàn bộ context trong một workflow đang dang dở.

## 10. Refresh, detach và transaction mới

`clear()` không phải lựa chọn duy nhất.

### 10.1. Refresh một managed entity

Nếu chỉ vài entity cần được đồng bộ lại:

```java
Product product = em.find(Product.class, productId);

int affected = executeBulkCriteriaUpdate(productId);

if (affected == 1) {
    em.refresh(product);
}
```

`refresh(product)` nạp lại state của managed entity từ database (subject to provider semantics, locks, filters và transaction). Nó có thể thay giá trị stale.

Cảnh báo:

- Refresh có thể ghi đè thay đổi chưa flush trên entity đó.
- Có thể chạy thêm SQL.
- Cascade REFRESH có thể ảnh hưởng association nếu mapping cấu hình.
- Refresh entity đã bị bulk DELETE có thể thất bại vì row không tồn tại.
- Refresh hàng nghìn entity mất đi lợi ích hiệu năng của bulk DML.

### 10.2. Detach một entity

`em.detach(product)` tách riêng object, không xóa toàn context. Tuy nhiên Java object cũ vẫn stale; để đọc mới cần load một managed instance phù hợp sau detach.

### 10.3. Transaction mới sau bulk

Một thiết kế đơn giản:

```text
Transaction A:
    bulk CriteriaUpdate
    COMMIT
    EntityManager/context kết thúc

Transaction B:
    query dữ liệu mới cần dùng
    map DTO hoặc thực hiện bước tiếp
```

Điều này giúp code không vô tình tiếp tục dùng managed state cũ. Tuy nhiên, khi chia thành nhiều transaction, **không còn tính nguyên tử** cho các bước thuộc hai transaction. Chỉ tách nếu nghiệp vụ cho phép.

### 10.4. Bảng lựa chọn đồng bộ

| Nhu cầu | Hành động có thể phù hợp | Cảnh báo |
|---|---|---|
| Có pending changes phải ghi trước bulk | `flush()` | Flush toàn bộ managed state đang dirty |
| Cần loại mọi managed state stale | `clear()` | Detach toàn context; mất pending changes chưa flush |
| Chỉ cần cập nhật một managed entity còn tồn tại | `refresh(entity)` | Ghi đè unflushed state của entity |
| Chỉ muốn tách một entity stale | `detach(entity)` | Object cũ vẫn giữ field cũ |
| Không cần đọc thêm sau bulk | Kết thúc transaction/context | Thường đơn giản nhất |
| Cần đọc mới trong request kế tiếp | Context mới | Tính nhất quán tùy commit/isolation/cache |

## 11. CriteriaUpdate không tự gọi dirty checking hoặc domain methods

Với managed entity:

```java
Product product = em.find(Product.class, productId);
product.deactivate();
```

Hibernate theo dõi state, rồi flush và sinh UPDATE nếu cần. Domain method có thể kiểm tra invariant.

Với CriteriaUpdate:

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);
update.where(cb.equal(p.get("id"), productId));

em.createQuery(update).executeUpdate();
```

Không có lời gọi `product.deactivate()` cho từng row, không kiểm tra quy tắc domain trong method đó, không chạy dirty checking trên các instance của tập bị cập nhật.

Nếu `deactivate()` có logic:

```java
public void deactivate() {
    if (hasUnfulfilledOrders()) {
        throw new IllegalStateException("Cannot deactivate");
    }
    this.active = false;
}
```

thì CriteriaUpdate sẽ **không tự gọi** logic ấy. Nếu rule quan trọng, phải:

- Biểu đạt nó trong WHERE/constraints/locking/transaction phù hợp; hoặc
- Không dùng bulk path, mà tải aggregate và gọi domain method cho từng entity.

### 11.1. Bulk không có nghĩa tự động vi phạm invariant

Một bulk mutation vẫn có thể đúng nếu nghiệp vụ là phép biến đổi tập hàng đơn giản, predicate đầy đủ và database bảo vệ các ràng buộc cần thiết.

Ví dụ “xóa token hết hạn” thường dễ mô hình hóa bằng CriteriaDelete hơn “hủy mọi đơn hàng đã đặt” có nhiều liên kết thanh toán/giao hàng.

## 12. @Version: bulk CriteriaUpdate không tự tăng version

`@Version` giúp Hibernate phát hiện optimistic locking conflict khi thao tác theo lifecycle managed entity.

Ví dụ managed update có thể tạo SQL tương đương:

```sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu row version đã khác, Hibernate phát hiện xung đột khi kiểm tra số row cập nhật.

Với CriteriaUpdate mặc định:

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);
update.where(cb.equal(p.get("id"), productId));

em.createQuery(update).executeUpdate();
```

bulk DML **không tự tăng `Product.version` và không tự kiểm tra version của từng entity giống managed update**.

### 12.1. Hệ quả khi concurrent update

Giả sử:

```text
Database: Product#10
    active = true
    price = 20.00
    version = 5

Transaction A: tải Product#10 version 5

Transaction B: bulk CriteriaUpdate active=false
    version vẫn 5
    commit

Transaction A: sửa price
    flush managed update WHERE version=5
```

Nếu version không đổi, transaction A có thể cập nhật thành công dù B đã thay đổi state. Tùy SQL/`@DynamicUpdate`, A có thể ghi lại giá trị `active` cũ hoặc không phát hiện xung đột nghiệp vụ.

**Đừng coi `@Version` là tấm khiên tự động cho mọi câu bulk update.**

## 13. Tăng numeric version tường minh trong CriteriaUpdate

Với numeric `@Version`, có thể mô tả phép tăng version ngay trong SET.

Giả sử entity dùng `Long version` hoặc `long version`, biểu thức:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);

update.set(
    p.<Long>get("version"),
    cb.sum(p.<Long>get("version"), 1L)
);

update.where(
    cb.equal(p.get("tenantId"), tenantId),
    cb.isTrue(p.<Boolean>get("active"))
);

int affected = em.createQuery(update).executeUpdate();
```

Đây là **manual version increment**. Cần kiểm tra tính tương thích kiểu số giữa `@Version` mapping, `CriteriaBuilder.sum`, Hibernate version và database dialect.

Nếu dùng custom hoặc temporal version, không thể áp dụng phép cộng số này một cách tùy tiện.

### 13.1. Tăng version không đồng nghĩa kiểm tra expected version

Nếu lệnh chỉ có:

```text
WHERE active = true
SET active = false, version = version + 1
```

nó tăng version cho những row phù hợp nhưng không kiểm tra rằng người dùng từng đọc mỗi row tại version nào.

Đối với cập nhật một entity dựa trên snapshot mà client biết, hãy bổ sung `WHERE version = :expectedVersion`.

### 13.2. Conditional update có expected version

```java
public boolean changePriceIfUnmodified(
        EntityManager em,
        Long productId,
        long expectedVersion,
        BigDecimal newPrice,
        Instant now) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaUpdate<Product> update =
        cb.createCriteriaUpdate(Product.class);

    Root<Product> p = update.from(Product.class);

    update.set(
        p.<BigDecimal>get("price"),
        newPrice
    );

    update.set(
        p.<Instant>get("updatedAt"),
        now
    );

    update.set(
        p.<Long>get("version"),
        cb.sum(p.<Long>get("version"), 1L)
    );

    update.where(
        cb.equal(p.get("id"), productId),
        cb.equal(p.get("version"), expectedVersion)
    );

    int affected = em.createQuery(update).executeUpdate();
    return affected == 1;
}
```

Ý nghĩa:

- Trả `true` nếu một row thỏa ID + expected version được cập nhật.
- Trả `false` nếu không có row khớp; có thể do ID không tồn tại hoặc version đã thay đổi.
- Version tăng trong database cùng update row khi thành công.
- Entity object đang managed trước đó vẫn stale; vẫn cần đồng bộ context.
- Callback không chạy vì đây là bulk DML.

### 13.3. Nên dùng entity-managed path khi nào?

Nếu cập nhật giá có nhiều invariant trên aggregate, callback và event quan trọng, dùng:

```java
Product product = em.find(Product.class, productId);
product.changePrice(newPrice);
```

với `@Version` thường dễ duy trì hơn manual CriteriaUpdate. Conditional bulk update phù hợp khi quy tắc cập nhật đơn giản, cần hiệu năng và đã kiểm soát đầy đủ tác động phụ.

## 14. HQL "update versioned" khác CriteriaUpdate

Hibernate HQL có extension `update versioned` ở các phiên bản hỗ trợ:

```java
em.createQuery("""
    update versioned Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Đây là **HQL-specific**, không thuộc CriteriaUpdate chuẩn của Jakarta Persistence.

Với CriteriaUpdate, không có một phương thức portable `setVersioned(true)` trong API JPA. Nếu cần tăng version, hãy dùng cách biểu đạt tường minh bằng `set` với version thích hợp hoặc chọn HQL extension khi ứng dụng chấp nhận phụ thuộc Hibernate.

Không nên cố ép một API riêng chưa có trong Criteria chuẩn rồi mặc định nó portable.

## 15. CriteriaDelete và optimistic locking

`EntityManager.remove(managedProduct)` có thể dùng version check cho entity versioned theo semantics managed removal.

`CriteriaDelete` không tải từng Product, nên không có chuyện tự so sánh version snapshot của mỗi Product trước khi delete.

Nếu muốn xóa Product#10 **chỉ khi version vẫn bằng 5**:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<Product> delete =
    cb.createCriteriaDelete(Product.class);

Root<Product> p = delete.from(Product.class);

delete.where(
    cb.equal(p.get("id"), productId),
    cb.equal(p.get("version"), expectedVersion)
);

int affected = em.createQuery(delete).executeUpdate();

if (affected == 0) {
    // Không có hàng khớp: có thể không tồn tại hoặc đã thay đổi.
}
```

Đây là conditional delete. Nó kiểm tra điều kiện được nêu trong WHERE, nhưng:

- Không gọi `@PreRemove` hoặc `@PostRemove`.
- Không cascade entity remove xuống child như `em.remove(root)`.
- Có thể gặp FK violation nếu child rows còn tham chiếu.
- Managed Product trong context có thể vẫn tồn tại/stale nếu không clear/detach.

## 16. Lifecycle callbacks bị bỏ qua khi bulk Criteria DML

Entity có thể có:

```java
@PreUpdate
void onUpdate() {
    updatedAt = Instant.now();
}

@PreRemove
void onRemove() {
    // Ghi một thông tin audit local hợp lệ.
}
```

Khi sửa/xóa từng managed entity, callback được thực thi theo quy tắc JPA lifecycle tương ứng.

Nhưng `CriteriaUpdate` và `CriteriaDelete` là bulk operations và **không gọi các callback đó lần lượt cho từng row bị tác động**.

### 16.1. @PreUpdate không tự cập nhật updatedAt

Nếu entity có callback cập nhật `updatedAt`, CriteriaUpdate này:

```java
update.set(p.<Boolean>get("active"), false);
```

sẽ không gọi `@PreUpdate` để sửa timestamp.

Nếu cần timestamp, ghi rõ:

```java
update.set(p.<Instant>get("updatedAt"), now);
```

### 16.2. @PreRemove không được gọi khi CriteriaDelete

Nếu code dùng:

```java
em.remove(managedProduct);
```

thì `@PreRemove` có thể chạy theo lifecycle.

Nếu dùng:

```java
em.createQuery(criteriaDelete).executeUpdate();
```

không có một callback Java cho từng Product bị xóa.

### 16.3. Entity listener và Hibernate Envers

Các cơ chế audit dựa trên entity lifecycle events, như một số cấu hình Hibernate Envers/listener, có thể không ghi revision per-entity cho bulk DML.

Nếu ứng dụng cần lịch sử thay đổi bắt buộc:

- Dùng managed-entity update/remove khi số lượng hợp lý.
- Dùng database trigger/audit table.
- Thiết kế bulk audit SQL/CDC/outbox phù hợp.
- Hoặc ghi một audit record mô tả cả tác vụ nếu business chỉ yêu cầu mức batch.

Không thay entity loop bằng CriteriaUpdate rồi mặc định mọi audit listener vẫn hoạt động.

### 16.4. Database triggers là cơ chế khác

Một trigger SQL `BEFORE UPDATE` ở database vẫn có thể chạy khi bulk DML thực thi. Nó không phải `@PreUpdate` của JPA.

Nếu trigger tự cập nhật timestamp hoặc cột tính toán, managed entity trong context vẫn không tự thấy thay đổi đó. Cần refresh/reload nếu code còn sử dụng giá trị mới.

## 17. Cascade REMOVE và orphanRemoval không tự chạy với CriteriaDelete

Mô hình đơn hàng:

```java
@Entity
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.REMOVE,
        orphanRemoval = true
    )
    private List<OrderLine> lines;
}
```

Đường entity lifecycle:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
em.remove(order);
```

Hibernate có thể cascade remove đến các `OrderLine` theo mapping.

Đường bulk CriteriaDelete:

```java
CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> o =
    delete.from(PurchaseOrder.class);

delete.where(cb.equal(o.get("status"), "DRAFT"));

em.createQuery(delete).executeUpdate();
```

**Không** diễn ra một vòng lặp gọi `remove(order)` và `remove(line)` cho từng entity.

### 17.1. Foreign key vẫn được database kiểm tra

Nếu `order_lines.order_id` tham chiếu `purchase_orders.id` với `ON DELETE RESTRICT`/`NO ACTION`, database có thể từ chối lệnh xóa cha trong khi child còn tồn tại.

Nếu FK có `ON DELETE CASCADE`, database có thể tự xóa child rows, nhưng:

- Java callbacks không chạy.
- Persistence context không tự đồng bộ child entities đã load.
- Audit hoặc event qua entity listener không được phát.
- Chính sách soft delete và lịch sử cần được xử lý riêng.

### 17.2. Xóa theo nghiệp vụ hay xóa theo dữ liệu?

Đối với token hết hạn không có child và không có callback bắt buộc, CriteriaDelete thường thích hợp.

Đối với order đã thanh toán, việc “xóa” có thể cần giữ audit, hoàn tiền, hủy shipment và phát domain event. Không nên chọn CriteriaDelete chỉ vì một câu SQL nhanh hơn.

## 18. Bulk DML và optimistic concurrency là hai bài toán song song

Một transaction chứa CriteriaUpdate vẫn có tính nguyên tử của database trong phạm vi resource/transaction manager tương ứng. Nhưng **atomicity không tự cung cấp optimistic locking semantics cho từng entity**.

Có ba tình huống:

1. **Bulk maintenance**: thay đổi hàng loạt state mà không dựa vào version client; có thể tăng version cho mọi row để các transaction khác nhận biết.
2. **Single-row conditional mutation**: WHERE ID + expectedVersion, SET version+1; kiểm tra affected count.
3. **Domain aggregate update**: tải managed entity, gọi domain method, để Hibernate kiểm tra `@Version` khi flush.

Lựa chọn tùy invariant, số row và yêu cầu phát hiện xung đột.

### 18.1. Không dựa vào affected count làm cơ chế optimistic lock toàn cục

`executeUpdate()` trả về số affected theo semantics của query/provider. Nếu update 5.000 row nhưng một vài row đã bị transaction khác đổi field, affected count không tự cho biết version kỳ vọng của từng row trừ khi query và dữ liệu đầu vào đã mã hóa điều kiện kiểm tra rõ ràng.

### 18.2. Retry phải mở transaction/context mới

Nếu câu mutation thất bại vì deadlock, serialization conflict hoặc exception persistence làm transaction rollback-only, không tiếp tục chạy lại cùng bulk mutation trong EntityManager/transaction đã lỗi. Thiết kế retry cả unit of work trong transaction mới và dùng idempotency nếu có side effect ngoài DB.

## 19. Semantics của executeUpdate() và affected count

`int affected = em.createQuery(update).executeUpdate();` thường cho biết số entity/hàng logic mà bulk statement tác động theo semantics của provider.

Nhưng cần thận trọng:

- Một SQL UPDATE có thể chọn row dù giá trị mới bằng giá trị cũ.
- Database/driver có khác biệt về affected-row count cho một số thao tác.
- Với inheritance nhiều bảng, Hibernate có thể sinh nhiều SQL statement cho một bulk operation.
- Kết quả trả về không nhất thiết bằng tổng physical rows trên mọi bảng trong hierarchy.

Nếu nghiệp vụ cần đếm số sản phẩm **chuyển từ active sang inactive**, hãy đưa trạng thái cũ vào WHERE:

```java
update.where(
    cb.isTrue(p.<Boolean>get("active")),
    cb.equal(p.get("tenantId"), tenantId)
);
```

Khi đó query chỉ chọn row đang active tại thời điểm mutation phù hợp.

### 19.1. Không có danh sách ID được trả về

CriteriaUpdate/CriteriaDelete chuẩn trả affected count, không trả list ID hay old/new values. Nếu cần biết chính xác những row nào đổi:

- Chọn ID trước với transaction/isolation thích hợp.
- Dùng native SQL có `RETURNING` nếu DB hỗ trợ.
- Ghi audit ở database hoặc thiết kế outbox/CDC.
- Dùng entity path khi cần per-entity lifecycle.

Chọn IDs trước và mutate sau là hai bước có thể bị cạnh tranh, trừ khi đã thiết kế locking/transaction phù hợp.

## 20. Trộn Criteria DML với Criteria SELECT

Một workflow dễ gặp:

```java
CriteriaQuery<Product> select = cb.createQuery(Product.class);
Root<Product> p1 = select.from(Product.class);

select.select(p1).where(cb.isTrue(p1.get("active")));

List<Product> products =
    em.createQuery(select).getResultList();

// Sau đó chạy CriteriaUpdate trên cùng Product.
executeBulkDeactivate();
```

Sau mutation, list `products` vẫn chứa các managed Java objects đã load. Một CriteriaQuery SELECT sau đó có thể trả lại các object đã có trong identity map, dẫn đến confusion khi xem state.

### 20.1. SELECT count và getter có thể nhìn khác nhau

Ví dụ:

```java
Product managed = em.find(Product.class, productId);

executeBulkDeactivate(productId);

Long stillActiveCount = em.createQuery("""
    select count(p)
    from Product p
    where p.id = :id and p.active = true
    """, Long.class)
    .setParameter("id", productId)
    .getSingleResult();

boolean managedValue = managed.isActive();
```

`stillActiveCount` là kết quả query dựa trên database; `managedValue` có thể là state stale của object. Hai kết quả có thể khác nhau trong cùng transaction.

Đây không phải lỗi ngẫu nhiên của Criteria; đó là hai lớp trạng thái chưa đồng bộ.

### 20.2. Khi nào nên chia transaction?

Nếu một tác vụ gồm giai đoạn bulk maintenance rồi giai đoạn đọc báo cáo, có thể tách hai unit of work để mỗi context rõ ràng. Nhưng đừng tách nếu nghiệp vụ cần tất cả bước commit nguyên tử.

## 21. Query cache, second-level cache và first-level cache

Hibernate có:

- **First-level cache**: persistence context của Session/EntityManager.
- **Second-level cache**: cache giữa các Session nếu bật và cấu hình.
- **Query cache**: cache kết quả query/metadata nếu bật.

Bulk CriteriaUpdate/CriteriaDelete đi qua mutation engine của Hibernate. Provider có thể thực hiện những bước invalidation cache tương ứng với query spaces/entity mapping, tùy version.

Nhưng một nguyên tắc luôn phải nhớ:

**Evict L2/query cache không làm mới object Java đang managed trong first-level cache.**

### 21.1. Vì sao `EntityManagerFactory.getCache().evict(...)` chưa đủ?

Ví dụ:

```java
Product managed = em.find(Product.class, id);

executeBulkDeactivate();

em.getEntityManagerFactory()
  .getCache()
  .evict(Product.class);
```

Dù L2 cache entry bị evict, `managed` vẫn là object cũ trong context hiện hành. Muốn cập nhật object, cần `refresh`, `clear` + reload hoặc kết thúc context.

### 21.2. Native SQL và external writers

Nếu một job JDBC hoặc hệ thống khác sửa cùng bảng ngoài Hibernate, Hibernate không nhất thiết biết để đồng bộ caches. Với native SQL, các synchronized query spaces/entity mapping có thể cần cấu hình theo API Hibernate/version.

Đừng áp chính sách cache của CriteriaUpdate một cách máy móc cho mọi stored procedure hoặc external database writer.

## 22. Transaction boundary cho CriteriaUpdate/CriteriaDelete

Bulk mutation thông thường cần thực thi trong transaction phù hợp.

Ví dụ service Spring:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.*;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductMaintenanceService {

    private final EntityManager em;

    public ProductMaintenanceService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public int deactivateBefore(
            UUID tenantId,
            Instant cutoff,
            Instant now) {

        CriteriaBuilder cb = em.getCriteriaBuilder();

        CriteriaUpdate<Product> update =
            cb.createCriteriaUpdate(Product.class);

        Root<Product> p = update.from(Product.class);

        update.set(p.<Boolean>get("active"), false);
        update.set(p.<Instant>get("updatedAt"), now);

        update.where(
            cb.equal(p.get("tenantId"), tenantId),
            cb.isTrue(p.<Boolean>get("active")),
            cb.lessThan(
                p.<Instant>get("discontinuedAt"),
                cutoff
            )
        );

        return em.createQuery(update).executeUpdate();
    }
}
```

Đây là một **bulk-only unit of work**: service không cần tải danh sách Product trước. Do đó, thường không có managed Product state cũ phải refresh/clear. Transaction commit hoặc rollback theo cấu hình transaction manager.

### 22.1. executeUpdate không phải commit

`executeUpdate()` thực thi DML và trả affected count, nhưng transaction có thể chưa commit. Nếu bước khác trong cùng transaction gặp lỗi và toàn transaction rollback, thay đổi bulk cũng rollback theo đảm bảo DB.

### 22.2. @Transactional(readOnly = true) không phù hợp

Một số integration có thể cấu hình flush mode/connection theo hướng read-only. Bulk mutation là write operation, nên đặt transaction ghi rõ ràng.

### 22.3. Self-invocation trong Spring

Với Spring proxy-based transaction management phổ biến, method nội bộ gọi trực tiếp một method `@Transactional` trong cùng object có thể bỏ qua interceptor.

Đừng giả định annotation đã tạo transaction nếu call không đi qua Spring-managed proxy. Đặt transaction ở application service entry point hoặc gọi qua bean phù hợp.

## 23. Criteria API không thay đổi nguyên tắc transaction của JPA

Dùng CriteriaUpdate không làm transaction “an toàn hơn” hay “nhiều atomicity hơn” so với HQL bulk query tương đương.

So sánh:

```java
// HQL:
em.createQuery("""
    update Product p
    set p.active = false
    where p.tenantId = :tenant
    """)
    .setParameter("tenant", tenantId)
    .executeUpdate();
```

và:

```java
// CriteriaUpdate:
CriteriaUpdate<Product> u =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = u.from(Product.class);

u.set(p.<Boolean>get("active"), false);
u.where(cb.equal(p.get("tenantId"), tenantId));

em.createQuery(u).executeUpdate();
```

Hai cách khác về **cú pháp dựng query** nhưng cùng thuộc bulk mutation path, nên cùng phải cân nhắc:

- Pending managed changes trước DML.
- Managed state stale sau DML.
- Version/callback/cascade.
- Transaction, isolation và locks.
- Database constraints và cache.

Criteria API không khắc phục các giới hạn bulk mutation chỉ vì query được xây bằng Java object.

## 24. So sánh CriteriaUpdate với HQL update và managed entity

| Nhu cầu | CriteriaUpdate | HQL update | Managed entity |
|---|---|---|---|
| Điều kiện tùy chọn/phức tạp | Thuận tiện với Predicate builders | Phải ghép query có kiểm soát hoặc nhiều biến thể | Thường tải tập entity rồi kiểm tra Java |
| Type safety với static metamodel | Có thể cao | Chủ yếu query string | Java entity fields/methods |
| Tự đồng bộ context sau ghi | Không | Không | Có vì sửa chính object managed |
| Callback `@PreUpdate` | Không per-entity | Không per-entity | Có theo lifecycle |
| `@Version` mặc định | Không như entity update | Không như entity update | Có |
| DML nhiều hàng | Có | Có | Có thể nhiều statement/batch |
| Cần trả managed entity đã thay đổi | Không | Không | Có |
| Phù hợp dynamic filters | Có | Có nhưng dễ phức tạp string | Tùy use case |
| Khả năng đọc của query đơn giản | Có thể nhiều dòng | Thường ngắn | Đơn giản cho một aggregate |

**Lựa chọn nên dựa trên nghiệp vụ và lifecycle**, không chỉ dựa vào số dòng code hoặc độ “hiện đại” của API.

## 25. Static metamodel: tăng an toàn kiểu và tránh lỗi tên thuộc tính

Criteria API có thể dùng chuỗi thuộc tính:

```java
p.<Instant>get("discontinuedAt")
```

Nếu đổi tên field thành `retiredAt` mà quên sửa chuỗi, lỗi có thể chỉ xuất hiện khi chạy query hoặc khi provider kiểm tra mapping.

Jakarta Persistence có static metamodel, thường được sinh qua annotation processor:

```java
// Ví dụ sau khi annotation processor đã tạo Product_:
Path<Instant> discontinued =
    p.get(Product_.discontinuedAt);

Path<Boolean> active =
    p.get(Product_.active);

update.set(active, false);
update.where(
    cb.lessThan(discontinued, cutoff)
);
```

`Product_` là class metamodel được sinh theo cấu hình build; nó không tự tồn tại nếu project chưa bật annotation processing tương ứng.

### 25.1. Tác dụng thực tế

- Compiler hỗ trợ phát hiện lỗi rename.
- Kiểu thuộc tính được thể hiện rõ hơn.
- Refactor trong IDE an toàn hơn.
- Ít nhầm tên field với tên cột SQL.

Tuy nhiên, metamodel **không thay đổi semantics bulk DML**: vẫn không tự cập nhật managed objects, vẫn không gọi callbacks.

## 26. Dynamic conditions cần giới hạn an toàn

Một helper có thể nhận các option tùy ý:

```java
public record DeleteTokenFilter(
    UUID tenantId,
    Instant expiresBefore,
    Boolean onlyUsed
) {}
```

Nếu cả `tenantId` và `expiresBefore` đều null mà code tạo `CriteriaDelete` không có WHERE, query có thể xóa **toàn bộ** token. Đây là rủi ro lớn nhất của mutation theo filter.

Một thiết kế an toàn:

```java
if (filter.tenantId() == null) {
    throw new IllegalArgumentException(
        "tenantId is required for bulk mutation"
    );
}

if (filter.expiresBefore() == null) {
    throw new IllegalArgumentException(
        "expiresBefore is required for cleanup"
    );
}
```

Sau đó mới xây CriteriaDelete.

### 26.1. Không nhận attribute name tùy ý từ client

Criteria API không tự ngăn người dùng truyền tên thuộc tính nguy hiểm nếu backend nhận chuỗi field và làm:

```java
root.get(clientSuppliedField)
```

Cấu trúc dynamic field phải được whitelist:

```java
switch (sortField) {
    case "name" -> root.get("name");
    case "price" -> root.get("price");
    default -> throw new IllegalArgumentException(
        "Unsupported field"
    );
}
```

Đối với UPDATE/DELETE, cần kiểm soát còn nghiêm hơn: ứng dụng nên quyết định cố định những cột được phép sửa/xóa.

### 26.2. Không xây SET từ JSON tùy ý

Một endpoint “bulk patch mọi cột theo tên do client gửi” có thể tạo thay đổi trái invariant hoặc bypass authorization. Hãy tạo từng use case rõ nghĩa như `deactivateExpired`, `markTokensUsed`, `expireSessions`.

## 27. Null semantics và điều kiện thời gian

SQL có ba giá trị logic: true, false, unknown. Với cột nullable:

```java
cb.lessThan(
    root.<Instant>get("discontinuedAt"),
    cutoff
)
```

hàng có `discontinuedAt = NULL` thường không thỏa điều kiện.

Nếu muốn xóa cả bản ghi có ngày hết hạn null, phải thể hiện rõ:

```java
Predicate expired = cb.lessThan(
    root.<Instant>get("expiresAt"),
    cutoff
);

Predicate missingExpiry = cb.isNull(
    root.get("expiresAt")
);

delete.where(cb.or(expired, missingExpiry));
```

Nhưng việc xóa token không có ngày hết hạn có thể là lỗi nghiệp vụ. Không thêm `isNull` chỉ vì muốn kết quả nhiều hơn; xác định ý nghĩa NULL trước.

### 27.1. Dùng Instant và clock ổn định

Trong một bulk job, truyền cùng một `Instant now`/`cutoff` vào query giúp các row được đánh giá theo một mốc thời gian nhất quán.

`Instant.now()` gọi nhiều lần ở nhiều bước có thể tạo ranh giới thời gian hơi khác nhau. Với những quy tắc expiration/retention quan trọng, lấy mốc từ `Clock` hoặc chính sách thời gian hệ thống rõ ràng.

## 28. Soft delete, tenant filter và chính sách visibility

Một entity có thể được soft delete qua cột `deletedAt`:

```java
@Column(name = "deleted_at")
private Instant deletedAt;
```

Một thao tác xóa mềm bằng CriteriaUpdate:

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Instant>get("deletedAt"), now);

update.where(
    cb.equal(p.get("tenantId"), tenantId),
    cb.isNull(p.get("deletedAt"))
);
```

Đây là bulk UPDATE. Vì không có entity callbacks per-row, nếu hệ thống cũng cần `updatedAt` hoặc version bump, phải xử lý tường minh.

### 28.1. Hibernate @SoftDelete không thay thế thiết kế mutation

Hibernate có cơ chế soft delete riêng ở các phiên bản hỗ trợ, cùng một số annotation/custom SQL của những cách triển khai cũ.

Không mặc định một `CriteriaDelete` luôn tôn trọng logic soft delete giống `EntityManager.remove()`. Cần kiểm tra version, mapping, SQL thực tế và thử nghiệm đường bulk.

Nếu yêu cầu là “không bao giờ hard-delete Order”, hãy bảo vệ cả tầng service, permission và database strategy thay vì chỉ dựa vào annotation entity.

### 28.2. Tenant filter không phải lý do bỏ tenant predicate

Các cơ chế multi-tenancy và filter ở Hibernate phụ thuộc kiểu mapping, cấu hình session và phiên bản. Không giả định mọi filter tự áp vào mọi bulk DML đúng như SELECT.

Đối với mutation nhạy cảm, thường nên đưa phạm vi tenant/owner vào predicate hoặc dựa vào cơ chế database RLS đã kiểm chứng, cùng integration test cho đúng đường CriteriaUpdate/CriteriaDelete.

## 29. CriteriaDelete và foreign key

Giả sử `OrderLine` tham chiếu `PurchaseOrder`.

Nếu dùng:

```java
CriteriaDelete<PurchaseOrder> delete =
    cb.createCriteriaDelete(PurchaseOrder.class);

Root<PurchaseOrder> o =
    delete.from(PurchaseOrder.class);

delete.where(cb.equal(o.get("status"), "DRAFT"));

em.createQuery(delete).executeUpdate();
```

database có thể từ chối vì child rows trong `order_lines` còn tham chiếu.

### 29.1. Khi nào xóa child trước?

Nếu domain thực sự cho phép xóa vật lý draft order và các line, có thể tạo workflow xóa child trước rồi xóa parent bằng SQL/bulk Criteria. Nhưng:

- Phải đảm bảo cùng transaction.
- Xóa child trước không được vô tình xóa data shared.
- Không có callback per-entity, nên audit/event phải riêng.
- Điều kiện chọn child phải khớp chính xác tập order cần xóa.
- Cần kiểm soát concurrent insert child hoặc locking phù hợp.

### 29.2. Khi nào database ON DELETE CASCADE phù hợp?

Nếu child chỉ thuộc vòng đời parent và schema có FK `ON DELETE CASCADE`, database có thể tự dọn child khi xóa parent. Nhưng điều đó không tạo Java callback hoặc domain lifecycle events cho child.

Nếu cần xử lý từng child domain logic, dùng `em.remove(root)` theo mapping hoặc một workflow đã mô hình hóa rõ.

### 29.3. Đừng dùng cascade chỉ để làm SQL khỏi lỗi

Quyết định xóa phải dựa trên ownership và retention policy. Một product được nhiều order line tham chiếu không nên được hard-delete bằng CriteriaDelete chỉ vì đã ngừng kinh doanh.

## 30. Giới hạn với inheritance và nhiều bảng

Với `@Inheritance(strategy = JOINED)`, một entity logic có thể trải qua nhiều bảng.

Bulk mutation trên hierarchy không nhất thiết tương ứng một physical SQL statement. Hibernate có thể dùng chiến lược multi-table mutation (ví dụ temporary tables hoặc cách khác tùy dialect/version) để thực hiện đúng mapping.

Hệ quả:

- `executeUpdate()` không nhất thiết bằng tổng các row được sửa/xóa trên mọi bảng vật lý.
- SQL generated có thể phức tạp hơn HQL/Criteria source.
- Query performance phụ thuộc dialect và index.
- Vẫn không gọi entity callbacks per-row.

Nếu dữ liệu dùng inheritance, đừng kết luận “CriteriaDelete chỉ xóa bảng gốc” hay “luôn có đúng một DELETE” mà không kiểm tra mapping và SQL được sinh ra.

## 31. Số lượng lớn: chunking và transaction

CriteriaDelete có thể xóa hàng trăm nghìn row chỉ với một query logic, nhưng transaction có thể giữ lock lâu, sinh undo/WAL lớn và làm replication chậm.

Nếu nghiệp vụ cho phép dọn theo chunk:

```text
Vòng 1:
    SELECT một nhóm ID theo thứ tự ổn định
    DELETE WHERE id IN :ids
    COMMIT

Vòng 2:
    SELECT nhóm ID tiếp theo
    DELETE WHERE id IN :ids
    COMMIT

...
```

Điều quan trọng:

- **Chunk boundary là transaction boundary**, không phải `flush()/clear()`.
- Nếu mỗi chunk commit riêng, thao tác tổng thể có thể hoàn tất một phần.
- Retry phải idempotent và có checkpoint/monitoring.
- Giữa các chunk dữ liệu có thể thay đổi do transaction khác.
- Nếu cần atomicity toàn bộ tập, chia commit theo chunk không tương đương một transaction.

### 31.1. Xóa theo danh sách ID

```java
CriteriaDelete<ResetToken> delete =
    cb.createCriteriaDelete(ResetToken.class);

Root<ResetToken> token =
    delete.from(ResetToken.class);

delete.where(token.<UUID>get("id").in(ids));

int changed = em.createQuery(delete).executeUpdate();
```

Danh sách `ids` cần được giới hạn kích thước phù hợp với giới hạn bind parameters/dialect. Nếu `ids` rỗng, xử lý trả 0 trước khi dựng query thay vì phụ thuộc vào SQL `IN ()` không portable.

### 31.2. Chọn ID theo keyset pagination

Với bảng lớn đang thay đổi, keyset pagination theo ID hoặc thời điểm/ID có thể ổn định hơn offset pagination. Nhưng cần xác định rõ điều kiện “chỉ những row đủ tiêu chí tại thời điểm nào” và cách xử lý concurrent changes.

## 32. Spring Data JPA: @Modifying và CriteriaUpdate

Spring Data JPA thường có:

```java
@Modifying
@Query("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
int deactivateExpired(@Param("cutoff") Instant cutoff);
```

`@Modifying` chủ yếu áp dụng cho repository query method khai báo `@Query` dùng DML. Nó không phải annotation cần gắn vào mọi method tự gọi `EntityManager.createQuery(criteriaUpdate).executeUpdate()`.

Nếu repository custom implementation tự dùng CriteriaUpdate:

```java
@Repository
public class ProductBulkRepository {

    @PersistenceContext
    private EntityManager em;

    public int deactivateExpired(
            UUID tenantId,
            Instant cutoff,
            Instant now) {

        CriteriaBuilder cb = em.getCriteriaBuilder();

        CriteriaUpdate<Product> update =
            cb.createCriteriaUpdate(Product.class);

        Root<Product> p = update.from(Product.class);

        update.set(p.<Boolean>get("active"), false);
        update.set(p.<Instant>get("updatedAt"), now);

        update.where(
            cb.equal(p.get("tenantId"), tenantId),
            cb.lessThan(
                p.<Instant>get("discontinuedAt"),
                cutoff
            )
        );

        return em.createQuery(update).executeUpdate();
    }
}
```

Application service nên mở transaction ghi phù hợp. Nếu context cần được làm mới, service/repository phải chọn flush/clear/refresh theo hợp đồng của use case.

### 32.1. flushAutomatically và clearAutomatically

Spring Data `@Modifying` có các tùy chọn:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

Chúng giúp flush EntityManager trước và clear sau query method được đánh dấu. Nhưng chúng không làm bulk DML gọi callbacks/versioning per-entity. `clearAutomatically` còn có thể detach những entity không liên quan; cần hiểu pending changes trước khi bật.

Với custom CriteriaUpdate, pattern tương ứng có thể được gọi tường minh bằng EntityManager.

### 32.2. Derived delete và bulk delete có semantics khác nhau

Một method tên `deleteByStatus` được Spring Data derive có thể tải/xóa entity theo lifecycle tùy cơ chế và version. Một repository `@Modifying @Query("delete ...")` là bulk DML.

**Không suy diễn semantics chỉ từ tên method**. Xem implementation và SQL thực tế.

## 33. Query Criteria động và tính portable

CriteriaUpdate/CriteriaDelete là một phần của Jakarta Persistence Criteria API. Dùng chúng thường portable hơn cách ghép cú pháp HQL-specific nếu các expression và mapping tuân theo đặc tả.

Nhưng portability không tuyệt đối:

- DB có kiểu dữ liệu, function và collation khác nhau.
- Hibernate có extension Criteria riêng.
- Một số biểu thức/association path có giới hạn khi dùng trong bulk DML.
- Multi-table mutation phụ thuộc dialect.
- Timestamp, numeric calculation và NULL semantics có thể khác.
- Hibernate-specific mapping như custom type/filter/soft delete cần được kiểm tra.

**Typed API không có nghĩa query sẽ chạy giống hệt trên mọi database.**

### 33.1. Khi nào dùng HQL thay Criteria?

Nếu điều kiện cố định và query ngắn:

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

có thể dễ đọc hơn nhiều dòng Criteria.

Khi query có nhiều điều kiện optional, static metamodel hoặc reusable predicate builder, Criteria thường hữu ích hơn.

### 33.2. Khi nào dùng native SQL?

- Cần `RETURNING` các row đã đổi theo DB cụ thể.
- Cần `UPDATE ... FROM` hoặc `DELETE ... USING` theo dialect.
- Cần lock/hint hay database-specific operator.
- Cần bulk mutation CTE hoặc window-driven update phức tạp ngoài API.
- Muốn kiểm soát chính xác execution plan sau khi đo đạc.

Native SQL còn yêu cầu chính sách cache invalidation, tenant scoping và mapping rõ.

## 34. Audit và outbox khi bulk mutation

Giả sử deactivation cần phát event cho từng Product. Nếu event đang được phát từ `Product.deactivate()` hoặc `@PostUpdate`, CriteriaUpdate sẽ không tạo event đó.

Có vài thiết kế khả thi:

1. **Entity-based path**: tải từng entity, gọi domain method, ghi event/outbox, dùng batching nếu cần.
2. **Audit ở database**: trigger hoặc cơ chế capture affected rows để ghi event/audit record.
3. **Bulk job event**: phát một event tổng hợp “N sản phẩm của tenant đã bị vô hiệu hóa” nếu downstream chấp nhận.
4. **Tách tập ID**: chọn IDs có locking/snapshot thích hợp, thực hiện bulk mutation và ghi outbox rows tương ứng trong cùng transaction nếu correctness được thiết kế rõ.

### 34.1. Outbox record phải được ghi trong cùng transaction nếu cần atomicity

```text
BEGIN TRANSACTION
    bulk update products
    insert outbox/audit records
COMMIT
```

Nếu database rollback, cả business change lẫn outbox rows trong cùng transaction rollback.

Nhưng code không nên gửi message trực tiếp ra broker trước khi commit rồi kỳ vọng rollback thu hồi nó. Outbox và consumer idempotency là cơ chế cần thiết khi workflow có delivery ngoài DB.

### 34.2. Không giả định “after commit callback” là delivery bền vững

Nếu DB commit rồi process crash trước lúc callback gửi message, downstream có thể không nhận event. Outbox persistent sẽ bền vững hơn cho các yêu cầu cần retry.

## 35. Isolation, locks và concurrent Criteria mutation

Bulk update trực tiếp xuống DB vẫn chịu transaction isolation/locking.

Ví dụ cùng một Product:

```text
Transaction A:
    SELECT Product#10 version=4

Transaction B:
    CriteriaUpdate Product#10 active=false
    (không tăng version)
    COMMIT

Transaction A:
    update managed Product#10
    có thể không phát hiện B nếu version không đổi
```

Để bảo vệ invariant:

- Dùng expected version condition + version increment.
- Dùng database atomic predicate/state transition.
- Hoặc tải managed aggregate và locking phù hợp.
- Xác định isolation level và retry khi deadlock/serialization failure.

### 35.1. Atomic conditional state transition

Ví dụ chỉ chuyển sản phẩm từ ACTIVE sang INACTIVE nếu đang active:

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<Boolean>get("active"), false);

update.where(
    cb.equal(p.get("id"), id),
    cb.isTrue(p.<Boolean>get("active"))
);

int affected = em.createQuery(update).executeUpdate();

if (affected != 1) {
    // Không thỏa trạng thái kỳ vọng.
}
```

Đây là kiểm tra trạng thái ngay trong SQL mutation, giảm khoảng trống giữa SELECT và UPDATE. Nhưng nếu rule phụ thuộc nhiều hàng hoặc nhiều aggregate, cần locking/isolation/constraint phù hợp chứ không thể chỉ thêm một Predicate đơn giản.

### 35.2. Không kéo transaction dài không cần thiết

Bulk DML lớn có thể giữ row locks lâu. Nên đo số row, index, query plan, thời gian và lock waits; không giả định một CriteriaUpdate luôn nhanh hơn mọi cách batch entity trong mọi database.

## 36. Kiểm thử hành vi CriteriaUpdate và CriteriaDelete

Một test có giá trị cần nhìn cả database **và** persistence context.

### 36.1. Kiểm thử CriteriaUpdate thay đổi DB

- Chuẩn bị Product active=true, version=3.
- Thực thi CriteriaUpdate active=false.
- Flush/commit theo transaction.
- Mở EntityManager mới.
- Xác nhận database lưu active=false.

### 36.2. Kiểm thử managed state stale

- Tải Product vào context A.
- Thực thi CriteriaUpdate trong cùng context/transaction.
- Kiểm tra getter có thể vẫn giữ giá trị cũ.
- `refresh()` hoặc `clear()` + reload.
- Xác nhận giá trị đã được cập nhật.

### 36.3. Kiểm thử callback không chạy

- Đặt `@PreUpdate` để tăng một counter test hoặc cập nhật một trường quan sát.
- So sánh managed setter + flush với CriteriaUpdate.
- Xác nhận bulk path không gọi callback per-entity; nếu cần timestamp, phải đưa vào SET.

### 36.4. Kiểm thử version

- Managed update tăng version theo mapping.
- CriteriaUpdate mặc định không tự tăng version.
- CriteriaUpdate explicit version increment tăng version.
- Conditional query với expectedVersion cũ trả affected=0 hoặc hành vi phù hợp.

### 36.5. Kiểm thử xóa và FK

- Tạo parent/child có FK.
- Thử `em.remove(parent)` với cascade mapping.
- Thử CriteriaDelete(parent) và quan sát constraint/DB cascade.
- Xác nhận callbacks không bị gọi trong bulk path.

### 36.6. Kiểm thử flush/clear

- Thay đổi một entity khác trong cùng context.
- Chạy CriteriaUpdate rồi clear.
- Xác nhận điều gì xảy ra với pending changes.
- Kiểm tra pattern explicit flush trước clear khi cần giữ thay đổi.

### 36.7. Kiểm thử tenant và soft delete

- Tạo dữ liệu của hai tenant.
- Chạy CriteriaUpdate/Delete cho tenant A.
- Xác nhận không row nào của B bị thay đổi.
- Kiểm tra filter/soft-delete mapping ở đường bulk thực tế.

### 36.8. Không dùng test mặc định rollback để kết luận commit production

Một số integration test Spring có transaction của chính test và tự rollback. Để xác minh transaction boundary, hãy đảm bảo test mô phỏng được cách service được gọi qua proxy và cách commit/rollback xảy ra ở runtime thật.

Không biến STEP 4 viết bài thành một lượt chạy project; các gợi ý kiểm thử này là nội dung học tập.

## 37. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Coi CriteriaUpdate là gọi setter trên từng entity | Domain method và callback không chạy | Xem CriteriaUpdate là bulk DML |
| Coi CriteriaDelete là gọi `remove(entity)` | Không có cascade/callback per-entity | Dùng entity removal nếu lifecycle cần thiết |
| Đọc entity managed cũ sau bulk | Thấy giá trị stale | Refresh hoặc clear + reload |
| Gọi `find()` lại ngay mà không clear/refresh | Identity map trả cùng object | Quản lý context có chủ đích |
| `clear()` trước khi flush các thay đổi cần giữ | Unflushed state bị bỏ qua | Flush có chủ đích hoặc tách transaction |
| Không tăng version | Transaction khác có thể không phát hiện bulk change | Explicit version policy |
| Tăng version nhưng không kiểm tra expectedVersion khi cần | Vẫn ghi đè thay đổi không mong muốn | WHERE ID + version |
| Trông chờ `@PreUpdate` cập nhật timestamp | `updatedAt` không đổi | SET timestamp tường minh hoặc audit DB |
| Bulk DELETE parent có child FK | Constraint violation hoặc DB cascade ngoài ý muốn | Thiết kế FK và ownership đúng |
| Thiếu tenant predicate | Sửa/xóa dữ liệu tenant khác | Bắt buộc tenant scope + tests |
| Bộ lọc rỗng | UPDATE/DELETE quá rộng | Validate các điều kiện bắt buộc |
| Dùng JOIN FETCH trong CriteriaDelete | Không có fetch trong DML | Subquery hoặc đổi workflow |
| Dùng affected count như danh sách ID bị đổi | Không biết row cụ thể | Audit/RETURNING/ID selection phù hợp |
| Dùng L2 eviction để sửa first-level cache | Managed instance vẫn stale | Clear/refresh |
| Dùng `@Modifying` cho mọi custom Criteria method | Không đúng cơ chế | Custom EntityManager Criteria + transaction |
| Giữ transaction quá dài khi mutate hàng triệu row | Lock contention, timeout | Index/chunk/retry policy |
| Dùng bulk DML cho domain invariant phức tạp | Bỏ qua logic per-entity | Managed aggregate path |
| Retry trong EntityManager đã lỗi | Transaction/context có thể hỏng | Rollback và mở unit mới |

## 38. Bài tập thực hành

### Bài 1 — Dựng CriteriaUpdate

Yêu cầu: với tenant `tenantId`, đặt `active=false` cho Product có `discontinuedAt < cutoff` và `active=true`.

Gợi ý:

```java
CriteriaUpdate<Product> u =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = u.from(Product.class);

u.set(p.<Boolean>get("active"), false);
u.where(
    cb.equal(p.get("tenantId"), tenantId),
    cb.isTrue(p.<Boolean>get("active")),
    cb.lessThan(p.<Instant>get("discontinuedAt"), cutoff)
);
```

**Câu hỏi:** nếu thiếu `tenantId` trong WHERE, lỗi nghiệp vụ nào có thể xảy ra?

**Trả lời:** query có thể vô hiệu hóa sản phẩm của tất cả tenant phù hợp ngày cắt thay vì chỉ tenant hiện tại.

### Bài 2 — Context sau mutation

```java
Product p = em.find(Product.class, 10L);

executeCriteriaUpdateActiveFalse(10L);

System.out.println(p.isActive());
```

**Câu hỏi:** có chắc in `false`?

**Trả lời:** Không. Object `p` được quản lý trước bulk có thể stale; CriteriaUpdate không tự đặt field của object ấy.

### Bài 3 — Chọn clear hay refresh

Bạn chỉ cần đọc lại Product#10 sau bulk update, nhưng context đang có một Order được sửa chưa flush.

**Câu hỏi:** gọi `em.clear()` ngay có an toàn?

**Trả lời:** Có thể không. Clear detach cả Order, có thể mất pending changes. Nếu chỉ cần Product#10 và nó còn managed/tồn tại, cân nhắc refresh riêng; hoặc flush các thay đổi cần giữ trước khi clear theo boundary có chủ đích.

### Bài 4 — Version

```java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

update.set(p.<BigDecimal>get("price"), newPrice);

update.where(cb.equal(p.get("id"), id));
```

**Câu hỏi:** `@Version` có tự tăng?

**Trả lời:** Không như managed update. Nếu versioning cần bảo vệ, thêm version increment và expected version condition phù hợp hoặc dùng entity lifecycle path.

### Bài 5 — Callback

Entity có `@PreUpdate` cập nhật `updatedAt`. CriteriaUpdate chỉ set `active=false`.

**Câu hỏi:** `updatedAt` có chắc đổi?

**Trả lời:** Không nhờ callback JPA. Nếu cần, bulk query phải set `updatedAt` hoặc có database trigger/audit mechanism phù hợp.

### Bài 6 — Delete parent

PurchaseOrder có OrderLines và `cascade = REMOVE`. Bạn dùng CriteriaDelete trên PurchaseOrder.

**Câu hỏi:** Hibernate có gọi `@PreRemove` của từng OrderLine không?

**Trả lời:** Không. Bulk CriteriaDelete không dùng entity removal path. Database FK/ON DELETE policy quyết định SQL deletion, và audit cần cơ chế riêng.

### Bài 7 — Chọn công cụ

Nhiệm vụ A: xóa 100.000 token hết hạn, không có callback/audit per-token bắt buộc.

Nhiệm vụ B: hủy 500 đơn hàng đã thanh toán, mỗi đơn cần hoàn tiền và kiểm tra shipment.

**Gợi ý:** A có thể dùng CriteriaDelete theo batch/transaction policy phù hợp. B nên dùng workflow/domain operations có trạng thái và side-effect coordination; CriteriaDelete trực tiếp thường không phù hợp.

## 39. Checklist thiết kế trước khi dùng bulk Criteria DML

1. **Mục tiêu mutation:** Cập nhật hay xóa những entity nào, theo predicate nào?
2. **Scope bắt buộc:** Tenant, owner, project, trạng thái và ngày cắt đã được giới hạn?
3. **Điều kiện rỗng:** Nếu input thiếu, có nguy cơ update/delete toàn bảng?
4. **Số row:** Kích thước mutation, index và lock duration có chấp nhận?
5. **Domain logic:** Có setter/method phải chạy để bảo vệ invariant?
6. **Version:** Có cần tăng version, kiểm tra expectedVersion hoặc retry?
7. **Callbacks:** `@PreUpdate`/`@PreRemove` có logic cần giữ?
8. **Audit:** Có Envers/listener/outbox/trigger cần điều chỉnh?
9. **Cascade/FK:** Nếu DELETE, child rows và shared references được xử lý thế nào?
10. **Soft delete:** Mutation phải hard delete hay chỉ đổi trạng thái?
11. **Persistence context:** Có entity đã load hoặc pending changes?
12. **Flush:** Có cần gửi pending managed changes trước mutation?
13. **Clear/refresh:** Code sau mutation có còn dùng stale objects?
14. **Cache:** Có L2/query/custom cache hoặc external writers?
15. **Transaction:** Boundary commit/rollback bao phủ đúng nghiệp vụ?
16. **Concurrency:** Atomic predicates, optimistic locking, deadlocks, isolation đã rõ?
17. **Dữ liệu trả về:** Affected count có đủ hay cần danh sách ID/old-new state?
18. **Kiểm thử:** Đã so sánh database state với managed state và đường entity lifecycle?
19. **Portability:** Query dùng JPA Criteria chuẩn hay extension Hibernate/database?
20. **Vận hành:** Có log/metrics cho affected count, duration, retry và lỗi constraint?

Checklist này giúp quyết định **có nên dùng** CriteriaUpdate/CriteriaDelete và phải bổ sung những bảo đảm nào để chúng an toàn cho use case.

## 40. Ghi nhớ

- **`CriteriaUpdate<T>` và `CriteriaDelete<T>`** là API bulk mutation của Jakarta Persistence; chúng khác `CriteriaQuery<T>` dùng SELECT.
- Trình tự chung: lấy `CriteriaBuilder` → tạo CriteriaUpdate/Delete → `from(...)` → `set` (chỉ update) và `where` → `executeUpdate()`.
- Bulk DML **tác động trực tiếp lên database** theo predicate, không duyệt và gọi setter/remove trên từng managed entity.
- **Persistence Context có thể stale** sau bulk: object Java đã load không tự đổi field hoặc chuyển trạng thái removed.
- `find()` trong cùng context thường trả entity đã managed, không bảo đảm tải state mới.
- Khi có pending changes cần lưu, dùng **`flush()` trước bulk** theo nhu cầu thứ tự/đồng bộ; flush không commit.
- Nếu không được tiếp tục dùng managed state cũ, dùng **`clear()` và reload**, hoặc `refresh()` những entity còn tồn tại.
- **Clear có thể làm mất pending changes chưa flush**; nó tác động toàn context, không chỉ các entity thuộc bulk query.
- **`@Version` không tự được kiểm tra/tăng** trong bulk CriteriaUpdate như managed update. Dùng explicit version increment/expectedVersion hoặc entity path nếu cần.
- **Lifecycle callbacks** như `@PreUpdate` và `@PreRemove` không chạy per-entity qua CriteriaUpdate/CriteriaDelete.
- **Cascade REMOVE/orphanRemoval** không tự chạy như `EntityManager.remove(root)` khi bulk delete; FK và DB `ON DELETE CASCADE` vẫn có hiệu lực riêng.
- `executeUpdate()` trả affected count, không trả danh sách entity/ID bị thay đổi; với inheritance nhiều bảng, số physical SQL rows có thể khác.
- Criteria bulk mutation có **một root mục tiêu** và giới hạn join; dùng subquery khi cần điều kiện liên quan, theo grammar/provider hỗ trợ.
- **Transaction boundary** vẫn bắt buộc; executeUpdate không phải commit. Concurrent updates cần locking/conditional predicates/versioning phù hợp.
- **`@Modifying`** trong Spring Data áp dụng cho repository DML query methods; custom CriteriaUpdate bằng EntityManager không tự cần annotation đó.
- Criteria API giúp xây predicate động và dùng static metamodel, nhưng **không tự bảo vệ authorization, tenant scope, audit hoặc domain invariants**.
- Chọn Criteria DML cho biến đổi tập hàng đơn giản, có thể diễn đạt bằng SQL; chọn managed entity path khi cần lifecycle/callback/cascade/domain logic từng entity.

**Kết luận:** CriteriaUpdate và CriteriaDelete rất hữu ích khi cần update/delete động trên nhiều bản ghi mà không tải từng entity. Nhưng chúng là **đường bulk DML**, không phải cách viết khác của dirty checking hay `remove(entity)`. Một triển khai đúng phải quyết định rõ đồng bộ persistence context bằng flush, refresh, clear hoặc context mới; xử lý optimistic versioning, callbacks, cascade và audit bằng chính sách riêng; đồng thời giữ mutation trong transaction và phạm vi dữ liệu được phép. Khi hiểu đúng những khác biệt ấy, Criteria API vừa giúp truy vấn động dễ bảo trì vừa tránh các lỗi dữ liệu stale và thay đổi ngầm không mong muốn.
