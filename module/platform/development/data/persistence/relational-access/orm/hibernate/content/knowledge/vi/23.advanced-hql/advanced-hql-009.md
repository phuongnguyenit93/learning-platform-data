# Ảnh hưởng của bulk DML đến Persistence Context, phiên bản và callback trong Hibernate ORM

Khi cần cập nhật hoặc xóa hàng nghìn, hàng triệu bản ghi, cách thông thường là tải từng entity, sửa trạng thái, rồi để Hibernate dirty checking phát sinh SQL khi flush. Cách ấy thuận tiện vì đi qua vòng đời entity, nhưng có thể tốn bộ nhớ, tạo nhiều statement và kéo dài transaction.

**Bulk DML** (*bulk Data Manipulation Language*) cho phép thực hiện một thao tác ghi trực tiếp dựa trên điều kiện: thay vì gọi setter hoặc `EntityManager.remove()` cho từng object, ứng dụng gửi một lệnh dạng `update ... where ...` hoặc `delete ... where ...` viết bằng HQL/JPQL. Hibernate chuyển truy vấn sang SQL và thực thi tại database.

Ví dụ:

```java
int affected = em.createQuery("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Nhìn qua, thao tác này có vẻ giống việc lặp trên từng `Product` rồi gọi `setActive(false)`. Nhưng **semantics khác nhau đáng kể**:

1. Persistence context đang giữ các `Product` đã load **không tự cập nhật field tương ứng** sau bulk DML.
2. Cơ chế `@Version`/optimistic locking **không tự chạy giống update từng managed entity**.
3. Những callback entity như `@PreUpdate`, `@PreRemove` và cascade/remove/orphan removal **không được gọi theo quy trình vòng đời từng entity**.
4. Database constraints, trigger, foreign key và transaction vẫn có hiệu lực theo SQL thực tế.
5. Cache, soft delete, multi-tenancy và các cơ chế lọc cần được kiểm tra theo mapping, Hibernate version và đường thực thi.

Đây là lý do một bulk query có thể rất nhanh nhưng nguy hiểm nếu gọi nó giữa một transaction đang chứa managed entities hoặc trong workflow vốn phụ thuộc vào callback và versioning.

Bài học đi từ phân biệt bulk DML với entity lifecycle, đến cách nhận diện dữ liệu stale, xử lý `@Version`, callbacks, cache, batching, Spring Data JPA và quy trình sử dụng an toàn.

---

## 1. Bulk DML là gì?

DML là nhóm thao tác thay đổi dữ liệu, thường gồm `INSERT`, `UPDATE` và `DELETE`.

Trong HQL/JPQL, các thao tác phổ biến là:

- Bulk `UPDATE`: cập nhật nhiều entity phù hợp điều kiện.
- Bulk `DELETE`: xóa các entity phù hợp điều kiện.
- Hibernate HQL còn hỗ trợ một số dạng bulk `INSERT`, như `insert ... select`, và một số cú pháp mở rộng tùy phiên bản.

Ví dụ bulk update:

```java
int updated = em.createQuery("""
    update Product p
    set p.active = false
    where p.category.id = :categoryId
    """)
    .setParameter("categoryId", categoryId)
    .executeUpdate();
```

Ví dụ bulk delete:

```java
int deleted = em.createQuery("""
    delete from ExpiredToken t
    where t.expiresAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Trong hai ví dụ, Hibernate không có nghĩa vụ tải toàn bộ `Product` hoặc `ExpiredToken` thành object Java trước khi thực thi SQL.

### 1.1. Truy vấn SELECT và bulk DML dùng API khác nhau ở điểm nào?

SELECT:

```java
List<Product> products = em.createQuery("""
    select p from Product p where p.active = true
    """, Product.class)
    .getResultList();
```

DML:

```java
int affected = em.createQuery("""
    update Product p set p.active = false
    """)
    .executeUpdate();
```

- `getResultList()` trả dữ liệu từ truy vấn SELECT.
- `executeUpdate()` thực hiện bulk UPDATE/DELETE và trả một số đếm theo semantics của provider.
- Bulk DML thường yêu cầu transaction đang hoạt động trong mô hình JPA thông thường.
- Không có danh sách managed entities được trả về để ứng dụng sửa từng object.

### 1.2. Bulk operation khác vòng lặp entity update

Hai đoạn này **không tương đương về hành vi**.

**Cách A — cập nhật từng managed entity:**

```java
List<Product> products = em.createQuery("""
    select p
    from Product p
    where p.discontinuedAt < :cutoff
    """, Product.class)
    .setParameter("cutoff", cutoff)
    .getResultList();

for (Product product : products) {
    product.deactivate();
}

// Hibernate dirty checking khi flush.
```

**Cách B — bulk update:**

```java
int affected = em.createQuery("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Cách A đi qua method domain, managed state, dirty checking, version check, callback phù hợp và lifecycle mapping. Cách B chạy trực tiếp bằng DML; callback/lifecycle từng entity không chạy theo cách A.

## 2. Ví dụ entity xuyên suốt bài

Giả sử hệ thống quản lý sản phẩm:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    private Instant discontinuedAt;

    @Version
    private long version;

    @Column(nullable = false)
    private Instant updatedAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public void deactivate() {
        this.active = false;
    }

    @PreUpdate
    void beforeUpdate() {
        this.updatedAt = Instant.now();
    }

    @PreRemove
    void beforeRemove() {
        // Ví dụ điểm callback; không nên gọi mạng ở đây.
    }
}
```

Các trường và callback giúp quan sát ba nhóm hành vi:

- State trong memory (`active`, `price`).
- Optimistic version (`version`).
- Lifecycle callback (`@PreUpdate`, `@PreRemove`).

Giả sử database có các row:

| id | name | active | price | version |
|---:|---|---|---:|---:|
| 10 | Bút | true | 20.00 | 3 |
| 11 | Sổ | true | 50.00 | 8 |
| 12 | Thước | true | 30.00 | 2 |

Với entity managed thông thường, Hibernate theo dõi state và version. Với bulk DML, database có thể đổi row ngay mà các object trong persistence context chưa biết gì về thay đổi đó.

## 3. Persistence Context và identity map

**Persistence context** là tập entity mà `EntityManager`/Hibernate `Session` đang quản lý trong một đơn vị làm việc.

Trong context, Hibernate thường đảm bảo với cùng entity type và ID có một managed instance đại diện:

```java
Product a = em.find(Product.class, 10L);
Product b = em.find(Product.class, 10L);

System.out.println(a == b); // Thường true trong cùng context.
```

Hibernate lưu thông tin để thực hiện dirty checking và quản lý identity:

```text
Persistence Context
+--------------------------------------+
| Product#10                            |
|   managed Java object                 |
|   active = true                       |
|   price = 20.00                       |
|   version = 3                         |
|   loaded state / dirty tracking       |
+--------------------------------------+
                 |
                 | SQL SELECT/UPDATE qua JDBC
                 v
Database row products.id = 10
```

Đối với update managed thông thường, Hibernate biết object nào thay đổi và có thể kiểm tra version khi flush.

### 3.1. Bulk DML bỏ qua việc cập nhật object Java trong context

Giả sử:

```java
Product product = em.find(Product.class, 10L);

em.createQuery("""
    update Product p
    set p.active = false
    where p.id = :id
    """)
    .setParameter("id", 10L)
    .executeUpdate();
```

Ngay sau câu bulk query, một trạng thái thường gặp:

```text
Managed Product#10 trong Java: active = true
Database products.id=10:        active = false
```

Hibernate không duyệt từng managed `Product` khớp điều kiện để gọi `deactivate()` hoặc đặt `active=false` trong object Java. Do đó, `product.isActive()` có thể vẫn trả `true`.

### 3.2. SELECT lại chưa chắc sửa được state stale

```java
Product product = em.find(Product.class, 10L);

em.createQuery("""
    update Product p set p.active = false where p.id = 10
    """).executeUpdate();

Product again = em.find(Product.class, 10L);
```

Trong cùng persistence context, `again` thường là **cùng managed instance** với `product`. `find` lần hai có thể trả identity-map entry và không thực hiện SQL SELECT. Vì thế:

```java
System.out.println(product == again); // Thường true.
System.out.println(again.isActive());  // Có thể vẫn true.
```

Đừng dùng `find` lại trong cùng context như cách đảm bảo vừa đọc dữ liệu mới nhất sau bulk DML.

## 4. Bulk DML không đồng bộ Persistence Context: hệ quả chính

Khi database đã đổi nhưng managed object vẫn giữ state trước đó, persistence context trở nên **stale** (cũ, không đồng bộ).

Các hệ quả có thể gặp:

1. **Đọc sai trong cùng transaction**: logic Java dựa vào field managed cũ.
2. **Ghi đè thay đổi mới**: một flush sau đó cập nhật row bằng state không còn đồng nhất với database.
3. **Sai kiểm tra nghiệp vụ**: object vẫn active dù bulk query đã deactivate.
4. **Sai version trong memory**: bulk update đã thay đổi dữ liệu nhưng version không tăng theo entity lifecycle.
5. **Khó debug**: native SQL hoặc tool database thấy giá trị mới, nhưng Java getter thấy giá trị cũ.
6. **Không có callback**: logic cập nhật audit timestamp, domain event hoặc snapshot trong callback bị bỏ qua.
7. **Cache cần xem xét**: Hibernate có cơ chế invalidation riêng, nhưng không tự thay đổi các entity managed đang giữ trong context.

### 4.1. Ví dụ sai dữ liệu ngay sau bulk update

```java
@Transactional
public boolean disableAndCheck(Long id) {
    Product product = em.find(Product.class, id);

    em.createQuery("""
        update Product p
        set p.active = false
        where p.id = :id
        """)
        .setParameter("id", id)
        .executeUpdate();

    return product.isActive();
}
```

Một kết quả có thể là `true`, mặc dù database row đã bị cập nhật thành false trong transaction.

Vấn đề không phải SQL bulk query thất bại. Vấn đề là Java object `product` không được tự đồng bộ sau câu SQL ấy.

### 4.2. Khi context kết thúc

Sau commit và đóng context, entity trở thành detached. Nếu mở context mới và load lại row, truy vấn thông thường sẽ đọc giá trị mới đã commit (trừ những yếu tố transaction isolation/cache cấu hình riêng).

Đây là lý do một số lỗi chỉ xuất hiện trong **cùng request/transaction** ngay sau bulk DML, nhưng không còn xuất hiện ở request kế tiếp.

## 5. Dirty checking và bulk DML là hai con đường ghi khác nhau

Với entity managed:

```java
Product product = em.find(Product.class, id);
product.deactivate();

// Khi flush:
// Hibernate phát hiện thay đổi và sinh UPDATE tương ứng.
```

Hibernate có thể phát SQL tương đương:

```sql
UPDATE products
SET active = ?, updated_at = ?, version = ?
WHERE id = ? AND version = ?;
```

Đây là SQL minh họa: danh sách cột thực tế phụ thuộc mapping, Hibernate version, `@DynamicUpdate` và các cấu hình khác.

Với HQL bulk update:

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
```

Hibernate tạo SQL update theo điều kiện nhưng **không áp dụng từng entity setter/dirty checking như con đường trước**.

### So sánh nhanh

| Thuộc tính | Managed entity + dirty checking | Bulk HQL/JPQL DML |
|---|---|---|
| Tải từng entity | Thường có | Không bắt buộc |
| Gọi domain method/setter | Có thể | Không |
| Tự đồng bộ managed object | Có, vì object được sửa trực tiếp | Không |
| Dirty checking từng managed entity | Có | Không theo bulk operation |
| Optimistic version mặc định | Thường có qua `@Version` | Không tự tăng/kiểm tra như entity update |
| `@PreUpdate` / `@PreRemove` | Áp dụng khi phù hợp | Không gọi per-entity |
| Cascade entity remove | Có nếu mapping phù hợp | Không theo đường `remove(entity)` |
| Orphan removal | Có theo lifecycle association | Không tự chạy như sửa collection managed |
| SQL count | Có thể nhiều statement/batch | Thường ít statement; inheritance có thể cần nhiều |
| Mục đích | Domain mutation có invariant/lifecycle | Thay đổi tập hàng theo điều kiện một cách trực tiếp |

## 6. Flush trước bulk DML: vì sao quan trọng?

Trong một transaction, có thể đã tồn tại những thay đổi chưa flush:

```java
Product product = em.find(Product.class, id);
product.changePrice(new BigDecimal("80.00"));

// Pending managed state chưa chắc đã được gửi xuống DB.
```

Nếu sau đó chạy bulk update với điều kiện dựa vào `price`:

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.price >= :threshold
    """)
    .setParameter("threshold", new BigDecimal("70.00"))
    .executeUpdate();
```

Vấn đề: bulk SQL quyết định các row phù hợp dựa trên **giá trị trong database** tại thời điểm câu SQL thực thi, không dựa trực tiếp vào setter trong Java.

Nếu price mới chưa được flush, bulk condition có thể dùng price cũ.

Ở `AUTO`, Hibernate có các quy tắc auto-flush đối với query spaces liên quan. Tuy nhiên, nếu correctness của workflow phụ thuộc **thứ tự rõ ràng giữa dirty checking và bulk DML**, code nên làm cho boundary ấy tường minh:

```java
product.changePrice(new BigDecimal("80.00"));

em.flush();  // Đồng bộ các thay đổi managed còn chờ.

em.createQuery("""
    update Product p
    set p.active = false
    where p.price >= :threshold
    """)
    .setParameter("threshold", new BigDecimal("70.00"))
    .executeUpdate();
```

**Flush không commit.** Nếu transaction rollback, cả SQL do flush và bulk SQL đều bị rollback khi chúng cùng nằm trong transaction database phù hợp.

### 6.1. Không gọi flush sau mỗi setter

`em.flush()` ở đây có mục đích **thiết lập thứ tự phụ thuộc giữa hai kiểu cập nhật**. Không cần gọi sau mỗi setter khi chỉ thực hiện cập nhật managed thông thường.

Flush quá thường xuyên có thể làm tăng round-trip, dirty checking và giảm hiệu quả batching.

### 6.2. Nếu flush thất bại

Một exception persistence/constraint trong flush có thể khiến transaction không còn an toàn để tiếp tục. Không nên bắt lỗi rồi thực hiện bulk SQL tiếp và cố commit. Thường cần rollback toàn bộ unit of work và mở context/transaction mới cho retry phù hợp.

## 7. Clear sau bulk DML: tránh đọc entity stale

Cách phổ biến để tránh sử dụng lại managed state cũ là `clear()`:

```java
@Transactional
public void deactivateDiscontinued(Instant cutoff) {
    em.flush();

    em.createQuery("""
        update Product p
        set p.active = false
        where p.discontinuedAt < :cutoff
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    em.clear();
}
```

`clear()` tách tất cả entity managed khỏi persistence context. Lần `find` tiếp theo thường phải tải lại entity, thay vì trả managed instance stale.

### 7.1. Clear không phải refresh

- `clear()`: detach **toàn bộ** managed entities; context không còn quản lý object cũ.
- `detach(entity)`: detach một entity (cascade DETACH có thể áp dụng).
- `refresh(entity)`: tải lại state của một managed entity cụ thể từ database.
- Đóng EntityManager: kết thúc context.

### 7.2. Cẩn thận: clear có thể làm mất pending changes

Giả sử:

```java
Product other = em.find(Product.class, otherId);
other.changePrice(new BigDecimal("100.00"));

em.createQuery("""
    update Product p set p.active = false where p.id = :id
    """)
    .setParameter("id", targetId)
    .executeUpdate();

em.clear();
```

Nếu `other.changePrice` chưa được flush, `em.clear()` có thể detach `other` và làm thay đổi giá chưa đồng bộ **không còn được ghi tự động** khi commit.

Vì vậy, khi định clear toàn bộ context, thông thường cần:

1. Xác định những thay đổi managed phải được giữ.
2. `flush()` các thay đổi ấy.
3. Chạy bulk DML.
4. `clear()` để tránh tiếp tục dùng managed objects stale.

Đây là pattern thường dùng, không phải một thao tác copy-paste an toàn cho mọi hệ thống: nếu một phần context có state không muốn ghi, gọi flush sẽ ghi cả phần ấy. Thiết kế transaction nên tránh trộn nhiều workflow chưa hoàn chỉnh.

### 7.3. Clear không tự thay dữ liệu trong biến Java

```java
Product product = em.find(Product.class, id);

executeBulkUpdate();

em.clear();

System.out.println(product.isActive());
```

`product` vẫn là Java object cũ, giờ đã detached. `clear()` không ghi đè field của object đó. Muốn đọc mới, cần tải lại trong context:

```java
Product fresh = em.find(Product.class, id);
```

## 8. Refresh thay vì clear khi chỉ có vài entity cần cập nhật

Nếu chỉ cần đồng bộ một managed entity sau bulk update và không muốn detach toàn bộ context:

```java
Product product = em.find(Product.class, id);

int count = em.createQuery("""
    update Product p
    set p.active = false
    where p.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();

if (count > 0) {
    em.refresh(product);
}
```

`refresh` yêu cầu entity còn managed. Nếu row còn tồn tại, Hibernate có thể lấy state mới, cập nhật field và version từ database.

### 8.1. Nhược điểm của refresh

- Làm mất những thay đổi chưa flush của entity được refresh.
- Có thể phát SELECT bổ sung.
- Cascade REFRESH có thể ảnh hưởng association tùy mapping.
- Nếu bulk DELETE đã xóa row, `refresh` có thể thất bại vì entity không còn.
- Nếu bulk update tác động hàng chục nghìn entity, refresh từng cái thường không phải chiến lược hiệu quả.

### 8.2. Khi nào nên tải lại bằng context mới?

Với thao tác bulk quy mô lớn, cách đơn giản thường là coi bulk DML như **ranh giới kết thúc giai đoạn ghi dữ liệu**: commit và mở một unit of work mới khi cần đọc tiếp.

Cách đó giảm nguy cơ trộn entity state cũ với kết quả bulk và dễ kiểm soát hơn một context chứa quá nhiều object đã được load trước đó.

## 9. @Version và optimistic locking trong cập nhật managed

Ví dụ:

```java
@Version
private long version;
```

Với managed entity, Hibernate thường dùng version để phát hiện optimistic locking conflict.

Giả sử Product#10 có version 3:

```sql
UPDATE products
SET price = 90.00, version = 4
WHERE id = 10 AND version = 3;
```

Nếu transaction khác đã tăng version lên 4, câu update với điều kiện version 3 có thể không khớp hàng; Hibernate phát hiện stale state khi statement/row count được kiểm tra và báo exception phù hợp.

Các chi tiết SQL và thời điểm exception có thể phụ thuộc version, mapping, batching và Hibernate runtime, nhưng **khái niệm** là version được kiểm tra và tăng khi entity update theo lifecycle tương ứng.

### 9.1. Bulk UPDATE mặc định không tự xử lý @Version như managed update

Ví dụ:

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
```

Ở dạng thông thường, bulk update **không tự động tăng version của từng Product** theo cơ chế entity update.

Hệ quả:

- Row trong database có thể đổi `active`.
- `version` vẫn giữ giá trị cũ.
- Một transaction khác đang giữ Product với version cũ có thể không phát hiện bulk modification chỉ nhờ `@Version`.
- Sau đó một cập nhật managed có thể ghi đè một phần giá trị bulk tùy SQL sinh ra và các field thay đổi.

Điểm cuối đặc biệt quan trọng: bulk update không tự gia nhập quy tắc optimistic locking của mọi entity đang được quản lý ở nơi khác.

## 10. Ví dụ lost update do bulk không tăng version

Giả sử database:

```text
Product#10:
    active  = true
    price   = 20.00
    version = 3
```

Transaction A tải entity:

```text
T-A:
    SELECT Product#10
    managed.active = true
    managed.price = 20.00
    managed.version = 3
```

Transaction B thực hiện bulk update:

```sql
UPDATE products
SET active = false
WHERE id = 10;
```

Giả sử B commit nhưng **không tăng version**.

Sau đó A đổi price:

```java
product.changePrice(new BigDecimal("25.00"));
```

Khi A flush, Hibernate có thể phát UPDATE với điều kiện `version = 3`, vẫn khớp vì bulk B không tăng version. Tùy mapping và `@DynamicUpdate`, SQL của A có thể ghi lại cả giá trị `active = true` từ managed state cũ hoặc ít nhất không phát hiện bulk change qua version.

Đây là một trong những nguy cơ lớn nhất khi dùng bulk update cạnh các transaction dựa vào optimistic locking.

### 10.1. Không phải mọi bulk update đều gây lost update

Nếu A chỉ thay đổi price và SQL update chỉ ghi price, active có thể vẫn false. Nhưng version không tăng vẫn có thể làm **business invariant hoặc cơ chế phát hiện xung đột không hoạt động như dự kiến**.

Không nên dựa vào việc SQL hiện tại “tình cờ chỉ cập nhật một cột” để kết luận bulk update an toàn trong mọi trường hợp.

### 10.2. @DynamicUpdate không thay thế optimistic locking

`@DynamicUpdate` có thể giúp Hibernate chỉ ghi các cột dirty của entity managed. Điều đó đôi khi giảm khả năng ghi đè cột khác, nhưng nó không tự bổ sung version check/increment cho bulk DML.

Nếu một rule yêu cầu phát hiện **bất kỳ** thay đổi đồng thời nào tới Product, versioning phải được xử lý nhất quán ở mọi con đường ghi.

## 11. Hibernate HQL "update versioned" là gì?

Hibernate HQL có extension `update versioned` dành cho bulk update, yêu cầu cập nhật optimistic version/timestamp cho entity được tác động theo khả năng phiên bản Hibernate hỗ trợ.

Ví dụ:

```java
int affected = em.createQuery("""
    update versioned Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Từ khóa `versioned` là **extension HQL của Hibernate**, không phải cú pháp JPQL portable. Với Hibernate ORM phù hợp, nó yêu cầu cập nhật version của các entity bị tác động thay vì giữ nguyên version như bulk update mặc định.

### 11.1. Lợi ích

- Các transaction đang giữ version cũ có thể phát hiện xung đột khi cố update sau đó.
- Version tăng giúp đồng bộ chính sách optimistic locking giữa bulk update và managed entity update trong nhiều workflow.
- Không phải tự viết biểu thức tăng version cho từng query.

### 11.2. Giới hạn cần hiểu

- `update versioned` vẫn là **bulk DML**, nên không tự đồng bộ object trong persistence context.
- Không gọi `@PreUpdate`/`@PostUpdate` cho từng entity.
- Không thực hiện các domain method cho từng row.
- Không tự cập nhật toàn bộ cache/object graph đã được load.
- Không tự bảo đảm người gọi bulk update đã kiểm tra đúng invariant nghiệp vụ hoặc version của từng row.
- Hibernate có giới hạn với một số kiểu version tùy chỉnh, ví dụ custom `UserVersionType`; cần xem tài liệu đúng version.

**Tăng version của row bị bulk update không giống việc so sánh version expected của một request riêng lẻ.** Nếu bulk query phải bảo đảm chỉ cập nhật những row có version kỳ vọng, vẫn cần điều kiện WHERE thích hợp.

### 11.3. Nhận diện một query phụ thuộc HQL

```sql
update versioned Product p set p.active = false
```

Đây là ví dụ Hibernate-specific. Nếu chuyển sang JPA provider khác, query có thể bị từ chối. Dự án nên đánh dấu query này trong tài liệu/repository và có integration test với Hibernate version đang sử dụng.

## 12. Tăng version tường minh bằng bulk UPDATE

Một cách khác cho entity có **numeric version** là đưa phép tăng version vào SET:

```java
int affected = em.createQuery("""
    update Product p
    set p.active = false,
        p.version = p.version + 1
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Cách này thể hiện rõ version column được thay đổi. Tuy nhiên, cần xét:

- Version field có kiểu số phù hợp hay không.
- Mapping, dialect và query provider có chấp nhận biểu thức update version ấy không.
- Timestamp/temporal version không thể áp dụng phép cộng 1 như numeric version.
- Mọi con đường ghi khác có đang sử dụng cùng quy tắc versioning không.
- Update nhiều row có thể phát sinh xung đột nghiệp vụ dù chỉ một SQL thành công.

Không nên tự viết `version = version + 1` một cách máy móc cho mọi entity. Với Hibernate, `update versioned` thường rõ ý định hơn nếu project chấp nhận HQL-specific behavior và cấu hình hỗ trợ.

### 12.1. Thêm điều kiện version kỳ vọng cho một row

Nếu request muốn cập nhật Product#10 **chỉ khi version là 3**:

```java
int affected = em.createQuery("""
    update Product p
    set p.price = :price,
        p.version = p.version + 1
    where p.id = :id
      and p.version = :expectedVersion
    """)
    .setParameter("price", new BigDecimal("99.00"))
    .setParameter("id", 10L)
    .setParameter("expectedVersion", 3L)
    .executeUpdate();

if (affected == 0) {
    throw new OptimisticLockingFailureException(
        "Product changed concurrently"
    );
}
```

Đây là **optimistic conditional update** được viết rõ bằng DML. `OptimisticLockingFailureException` trong ví dụ là tên minh họa; dùng exception thích hợp của ứng dụng/framework.

Ưu điểm là điều kiện WHERE kiểm tra expected version và SET tăng version nguyên tử ở database. Nhưng:

- Đây vẫn là bulk path, không gọi entity callbacks.
- Persistence context vẫn có thể stale.
- Các invariant gắn với setter/domain method vẫn phải được bảo vệ bằng logic phù hợp.
- Không dùng số affected như một bảo đảm mọi rule khác đều đúng.

## 13. Bulk DELETE và optimistic locking

Với `EntityManager.remove(managedEntity)`, Hibernate có thể dùng optimistic locking khi xóa entity versioned; SQL có thể bao gồm điều kiện version.

Với bulk delete:

```java
int deleted = em.createQuery("""
    delete from Product p
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Query xóa theo điều kiện tập hàng, không tự kiểm tra version kỳ vọng của từng managed entity tương ứng như `remove(entity)`.

### 13.1. Xóa theo version nếu cần

Nếu muốn xóa một Product theo expected version cụ thể:

```java
int deleted = em.createQuery("""
    delete from Product p
    where p.id = :id
      and p.version = :expectedVersion
    """)
    .setParameter("id", id)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (deleted == 0) {
    // Không tìm thấy row phù hợp hoặc version đã thay đổi.
}
```

Cách này bảo vệ điều kiện version của hàng đó, nhưng không gọi `@PreRemove` hoặc cascade entity REMOVE. Cần cân nhắc foreign key và các yêu cầu audit.

### 13.2. Nếu entity vẫn managed sau bulk delete

```java
Product product = em.find(Product.class, id);

em.createQuery("""
    delete from Product p where p.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();

// product vẫn là Java object trong persistence context
// nếu chưa clear/detach.
```

Entity đã bị xóa trong DB nhưng `product` trong context có thể vẫn được xem là managed với state cũ. Đọc getter có thể trả dữ liệu stale; cập nhật tiếp rồi flush có thể gây lỗi vì row không còn tồn tại.

Đây là tình huống đặc biệt nguy hiểm nếu sau bulk delete, code tiếp tục sử dụng entity vừa xóa như một phần workflow khác.

## 14. Lifecycle callbacks: @PreUpdate, @PostUpdate, @PreRemove, @PostRemove

JPA hỗ trợ entity callbacks và entity listeners:

```java
@PrePersist
void onCreate() { ... }

@PreUpdate
void onUpdate() { ... }

@PreRemove
void onRemove() { ... }

@PostUpdate
void afterUpdate() { ... }

@PostRemove
void afterRemove() { ... }
```

Với thao tác từng managed entity, callbacks được áp dụng theo những điều kiện lifecycle tương ứng.

Ví dụ:

```java
Product product = em.find(Product.class, id);
product.changePrice(new BigDecimal("100.00"));

// @PreUpdate / @PostUpdate có thể được kích hoạt
// trong quá trình Hibernate cập nhật entity.
```

Nhưng với:

```java
em.createQuery("""
    update Product p
    set p.price = :price
    where p.id = :id
    """)
    .setParameter("price", new BigDecimal("100.00"))
    .setParameter("id", id)
    .executeUpdate();
```

Hibernate **không gọi `@PreUpdate` / `@PostUpdate` trên mỗi Product khớp điều kiện**. Tương tự, bulk delete không gọi `@PreRemove`/`@PostRemove` cho từng entity như `em.remove(entity)`.

### 14.1. Hệ quả với updatedAt

Entity có:

```java
@PreUpdate
void onUpdate() {
    this.updatedAt = Instant.now();
}
```

Với managed update, callback có thể cập nhật `updatedAt`. Với bulk update, callback **không chạy**, nên nếu câu bulk không set `updatedAt`, cột có thể giữ thời điểm cũ.

Có thể viết tường minh:

```java
Instant now = clock.instant();

em.createQuery("""
    update Product p
    set p.active = false,
        p.updatedAt = :now
    where p.discontinuedAt < :cutoff
    """)
    .setParameter("now", now)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Ở đây ứng dụng chủ động đưa audit timestamp vào bulk update, không dựa vào callback.

### 14.2. Hệ quả với domain event

Nếu `@PreUpdate` hoặc `@PostUpdate` đang gọi logic ghi sự kiện nghiệp vụ, bulk update sẽ **bỏ qua** đường đó. Hệ thống downstream có thể không nhận event dù database đã đổi.

Một thiết kế bền vững hơn là use case bulk tạo các bản ghi outbox/audit cần thiết bằng một đường tường minh trong transaction hoặc thiết kế event theo tập thay đổi.

Không nên đưa HTTP call, message publish hoặc email vào callback rồi kỳ vọng mọi con đường SQL đều gọi callback. Database transaction cũng không tự rollback những side effect đã gửi ra ngoài.

### 14.3. Hibernate Envers hoặc listener hạ tầng

Một số hệ thống dùng Hibernate Envers, listener hoặc interceptor để tạo audit history từ entity lifecycle events. Bulk HQL DML thường **không phát các entity lifecycle events như việc update/remove từng entity**, nên không nên kỳ vọng audit revision cho từng row tự được tạo theo đường ấy.

Nếu audit là yêu cầu bắt buộc, kiểm tra chính xác cơ chế audit đang dùng. Có thể phải ghi audit bằng SQL/outbox riêng hoặc tránh bulk path cho nghiệp vụ đó.

### 14.4. Database trigger vẫn có thể chạy

Phân biệt **entity callbacks** với **database triggers**:

- `@PreUpdate` là callback phía Java/JPA.
- Trigger `BEFORE UPDATE` / `AFTER UPDATE` là logic phía database.

Bulk SQL đi trực tiếp xuống database nên trigger database vẫn có thể được thực thi theo quy tắc của DB. Nhưng trigger không làm persistence context tự cập nhật object Java.

Nếu trigger thay đổi `updated_at` hoặc cột tính toán, entity đã load vẫn có thể stale và cần refresh/reload.

## 15. Cascade và orphanRemoval khi bulk DELETE

Giả sử:

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

Khi dùng:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
em.remove(order);
```

Hibernate đi theo entity removal path: cascade REMOVE tới line theo mapping, thực hiện callbacks liên quan và xử lý thứ tự xóa sao cho hợp FK.

Nhưng với:

```java
em.createQuery("""
    delete from PurchaseOrder o
    where o.status = 'DRAFT'
    """).executeUpdate();
```

Bulk delete **không đồng nghĩa gọi `em.remove()` trên từng PurchaseOrder**, nên cascade REMOVE và orphan removal không được áp dụng như đường entity lifecycle.

### 15.1. Có thể gặp lỗi foreign key

Nếu `order_lines.order_id` tham chiếu `purchase_orders.id` bằng FK không có ON DELETE CASCADE và các line vẫn tồn tại, database có thể từ chối xóa order.

Ví dụ:

```text
DELETE purchase_orders WHERE status = 'DRAFT'
    |
    +--> FK từ order_lines tới purchase_orders
    |
    +--> constraint violation
```

Hibernate HQL bulk delete trên một entity có inheritance/secondary tables có thể phải tổ chức nhiều SQL để xóa dữ liệu thuộc mapping của **chính entity đích**. Điều đó không có nghĩa mọi association child độc lập đều tự được cascade như `remove(entity)`.

### 15.2. DB-level ON DELETE CASCADE khác JPA cascade

Nếu schema có:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

database có thể tự xóa order lines khi hàng order bị xóa bằng bulk SQL.

Nhưng:

- DB cascade không gọi `@PreRemove` của Java entity.
- Hibernate persistence context không tự thấy mọi row child đã bị DB xóa.
- Child/audit domain events không tự được phát.
- Soft-delete policy cần được xem xét riêng.

### 15.3. Bulk DELETE có bảo vệ invariant domain không?

Không. Một câu:

```sql
delete from PurchaseOrder o where o.status = 'DRAFT'
```

không tự gọi method `order.canBeDeleted()` cho từng order. Nếu deletion rule còn phụ thuộc payment, shipment, retention period, audit hoặc trạng thái khác, cần biểu đạt điều kiện đó bằng query và constraint thích hợp hoặc dùng entity lifecycle path.

**Bulk DELETE là quyết định nghiệp vụ và dữ liệu**, không chỉ là tối ưu câu SQL.

## 16. Inheritance mapping và số SQL thực tế

Hibernate có các chiến lược inheritance như:

- `SINGLE_TABLE`: nhiều subtype chung một bảng.
- `JOINED`: base class và subtype có bảng riêng.
- `TABLE_PER_CLASS`: mỗi concrete class có bảng riêng theo mapping.

Bulk update/delete với hierarchy có thể cần SQL khác nhau:

- Với SINGLE_TABLE, có thể tác động một bảng.
- Với JOINED, thao tác xóa entity có thể phải đụng nhiều bảng hoặc dùng chiến lược multi-table mutation.
- Với TABLE_PER_CLASS, query polymorphic có thể liên quan nhiều bảng.

Hibernate có cơ chế hỗ trợ bulk mutation nhiều bảng, đôi khi dùng temporary table hoặc chiến lược khác tùy dialect/version.

### 16.1. executeUpdate() trả về số gì?

`int affected = query.executeUpdate();` không nên được hiểu máy móc là tổng số **physical rows** bị tác động trên mọi bảng trong tất cả statement Hibernate thực thi.

Đặc biệt với inheritance mapping nhiều bảng, Hibernate có thể báo số **entity instances** bị tác động theo semantics của bulk operation, trong khi số SQL statements/rows vật lý khác.

Ví dụ nếu xóa 10 entity thuộc JOINED hierarchy, database có thể xóa hàng ở bảng base và bảng subtype. Không nên cộng các statement row counts để suy ra số entity theo cách tự phát.

### 16.2. Mức độ chính xác của số affected

Ngay cả với một bảng, “số hàng phù hợp điều kiện” và “số giá trị thực sự thay đổi” có thể khác theo database/driver. Một UPDATE đặt cùng giá trị cũ vẫn có thể được tính là hàng bị tác động.

Nếu nghiệp vụ cần số chính xác theo định nghĩa riêng (ví dụ chỉ đếm các sản phẩm chuyển từ active sang inactive), hãy đưa điều kiện trạng thái cũ vào WHERE:

```java
int affected = em.createQuery("""
    update Product p
    set p.active = false
    where p.active = true
      and p.discontinuedAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Như vậy query giới hạn tập row được xem là đã chuyển trạng thái theo điều kiện yêu cầu.

## 17. Bulk INSERT trong HQL

JPQL chuẩn truyền thống không có một cú pháp portable tổng quát như `INSERT INTO Entity ... SELECT ...`. Hibernate HQL hỗ trợ một số dạng bulk insert, chẳng hạn insert-select, theo phiên bản và dialect.

Ví dụ khái niệm:

```sql
insert into ProductArchive (id, name, archivedAt)
select p.id, p.name, current_timestamp
from Product p
where p.active = false
```

Cần đảm bảo entity `ProductArchive` và thuộc tính tương ứng tồn tại, kiểu dữ liệu tương thích, ID policy hợp lệ và HQL version hỗ trợ cú pháp.

### 17.1. Bulk INSERT không giống persist()

```java
ProductArchive archive = new ProductArchive(...);
em.persist(archive);
```

`persist` đưa một entity vào persistence context và tham gia lifecycle callbacks như `@PrePersist` theo semantics tương ứng.

Bulk INSERT tạo hàng trực tiếp bằng DML, không tạo managed Java object cho từng row insert và không gọi `@PrePersist` của từng object mới.

Nếu archive row cần ID generated, audit fields hay business invariant, phải mô hình hóa trực tiếp trong query/schema hoặc chọn entity-based path.

### 17.2. Không phải mọi generator đều tương đương

Identifier allocation trong entity persist có thể dùng sequence, pooled optimizer, identity hoặc custom generator. Bulk insert-select có giới hạn riêng với sinh ID; không mặc định mọi chiến lược ID dùng cho `persist` đều chạy như nhau trong bulk DML.

Hãy kiểm tra tài liệu Hibernate version, mapping ID và database dialect trước khi đưa HQL bulk insert vào production.

## 18. FlushMode và auto-flush đối với bulk DML

Hibernate có flush modes như `AUTO`, `COMMIT` và các mode native khác.

Trong mode `AUTO`, Hibernate có thể auto-flush những thay đổi pending liên quan trước khi thực thi query để đảm bảo kết quả cần thiết. Nhưng khi trộn nhiều bước ghi, cách ít mơ hồ nhất là làm rõ ranh giới:

```java
em.flush();
int count = em.createQuery(bulkHql).executeUpdate();
em.clear();
```

Đây là một pattern có chủ đích, không phải quy tắc “mọi bulk query đều phải gọi flush và clear” bất kể context.

### 18.1. Khi không có managed changes

Nếu transaction chỉ chạy một bulk update và không giữ entity nào đã load trước đó:

```java
@Transactional
public int deactivateBefore(Instant cutoff) {
    return em.createQuery("""
        update Product p
        set p.active = false
        where p.discontinuedAt < :cutoff
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();
}
```

Không có pending state trong context thì explicit flush/clear có thể không mang thêm giá trị. Một use case bulk-only với context riêng thường là thiết kế đơn giản nhất.

### 18.2. Manual flush mode dễ gây mất pending updates

Nếu Hibernate Session bị đặt `FlushMode.MANUAL`, không được giả định commit tự đồng bộ mọi entity changes pending. Khi trộn managed operations với bulk DML dưới MANUAL, cần nắm chắc thời điểm explicit flush; nếu không, kết quả rất khó dự đoán.

Không đổi flush mode chỉ để làm bulk update “nhanh hơn” khi chưa hiểu transaction và query semantics.

## 19. Hãy dùng transaction boundary rõ ràng

Bulk DML thay đổi database trực tiếp, nhưng **không phải transaction độc lập mặc định**.

Ví dụ:

```java
@Transactional
public int archiveExpired(Instant cutoff) {
    int changed = em.createQuery("""
        update Product p
        set p.active = false,
            p.updatedAt = :now
        where p.active = true
          and p.discontinuedAt < :cutoff
        """)
        .setParameter("now", Instant.now())
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    saveAuditBatchSummary(changed);

    return changed;
}
```

Nếu `saveAuditBatchSummary` ghi dữ liệu vào cùng database transaction và có lỗi khiến transaction rollback, bulk update cũng rollback. Bulk DML không vượt ra khỏi ACID boundary của transaction đang chứa nó.

### 19.1. Flush không phải commit

Ngay cả khi bulk SQL đã được thực thi và `executeUpdate()` trả số affected, transaction có thể chưa commit. Exception/rollback sau đó có thể hủy những cập nhật đó.

### 19.2. Transaction dài và lock

Một câu bulk UPDATE ảnh hưởng hàng trăm nghìn row có thể giữ lock, gây WAL/undo lớn, chặn transaction khác hoặc phát sinh deadlock. Nó ít statement hơn không đồng nghĩa “tức thời và vô hại”.

Cần xem xét:

- Điều kiện WHERE có index phù hợp không?
- Có cập nhật toàn bộ bảng không cần thiết không?
- Transaction sẽ giữ lock bao lâu?
- Có thể chia chunk nếu business cho phép partial commit không?
- Có cần retry khi deadlock/serialization conflict không?
- Hệ thống replication/cdc/audit có bị ảnh hưởng không?

## 20. Bulk DML và cache: first-level khác second-level

Hibernate có nhiều lớp lưu trạng thái:

1. **Persistence context / first-level cache**: luôn gắn với Session/EntityManager, giữ managed objects và identity map.
2. **Second-level cache (L2)**: tùy cấu hình, lưu dữ liệu giữa các Session.
3. **Query cache**: tùy cấu hình, lưu kết quả query và metadata liên quan.

Bulk HQL/JPQL tác động trực tiếp tới DB. Điều quan trọng nhất:

**First-level cache không tự được cập nhật theo bulk query.** Nó có thể tiếp tục chứa managed entities stale cho tới khi refresh/clear/detach/context kết thúc.

### 20.1. Hibernate có cơ chế invalidation cache cho HQL mutation

Hibernate có cơ chế dọn/invalidate cache region và query timestamps khi thực thi bulk HQL/JPQL mutation để giảm nguy cơ cache liên phiên giữ dữ liệu đã bị sửa, tùy mapping và version.

Tuy nhiên, không nên suy ra:

- Mọi loại cache custom đều được invalidated.
- Một native SQL update ngoài Hibernate sẽ tự cập nhật cache.
- Invalidation L2 sẽ refresh object đang managed trong Session hiện hành.
- Mọi query cache entry đều có hành vi giống nhau khi dùng custom cache region/filter/tenant.

### 20.2. Native SQL cần chú ý synchronized query spaces

Với native SQL, Hibernate có thể thiếu thông tin bảng/entity bị tác động để invalidation cache chính xác, đặc biệt khi query truy cập view, procedure hoặc bảng không được mapping.

Các API native Hibernate có thể khai báo synchronized entity/query spaces cho query tương ứng, ví dụ trên `NativeQuery` khi version hỗ trợ. Cần đối chiếu API/dialect cụ thể.

Nếu ứng dụng cập nhật database bằng JDBC trực tiếp hoặc job ngoài Hibernate, hãy thiết kế chính sách cache eviction/invalidation riêng; không mặc định Hibernate tự phát hiện mọi external writer.

### 20.3. Cache không phải giải pháp làm mới persistence context

`em.getEntityManagerFactory().getCache().evict(Product.class);` có thể ảnh hưởng L2 cache, nhưng **không tự đồng bộ managed Product** đã nằm trong một EntityManager.

Nếu vấn đề là Java object stale sau bulk update, phải xử lý context bằng refresh/clear/reload phù hợp.

## 21. Soft delete và bulk DELETE/UPDATE

Nhiều ứng dụng không xóa vật lý mà đánh dấu:

```java
private boolean deleted;
private Instant deletedAt;
```

Một lệnh bulk update để soft delete:

```java
em.createQuery("""
    update Product p
    set p.deleted = true,
        p.deletedAt = :now
    where p.id in :ids
    """)
    .setParameter("now", now)
    .setParameter("ids", ids)
    .executeUpdate();
```

Ở đây ứng dụng chủ động cập nhật cột soft-delete. Điều cần nhớ:

- Callback `@PreRemove` không được gọi, vì đây là bulk UPDATE.
- Callback `@PreUpdate` cũng không gọi per-entity.
- Version không tự tăng trừ khi query/extension xử lý rõ.
- Managed Product đã load vẫn có thể báo `deleted=false`.
- Mọi query về sau phải áp dụng chính sách lọc deleted rows phù hợp.

### 21.1. Hibernate @SoftDelete và custom @SQLDelete

Các phiên bản Hibernate có thể hỗ trợ cơ chế mapping soft delete như `@SoftDelete` hoặc custom SQL delete như `@SQLDelete`. Những annotation này có semantics riêng với đường remove entity, HQL mutation và SQL sinh ra.

**Không nên giả định một bulk HQL DELETE sẽ gọi cùng logic Java/custom SQL như xóa từng entity**. Hãy kiểm tra Hibernate version, mapping thực tế và SQL của bulk DELETE.

Nếu hệ thống yêu cầu tuyệt đối không xóa vật lý, hãy kiểm soát cả service permissions, query paths, native SQL, schema và tests. Đừng chỉ dựa vào một annotation rồi cho phép bulk delete tùy ý.

### 21.2. Filter, tenant và soft delete predicate

Ứng dụng multi-tenant hoặc có data visibility rule có thể dùng filter, discriminator, tenant mapping hoặc SQL restriction riêng.

Một bulk DML thiếu giới hạn tenant có thể gây hậu quả nghiêm trọng nếu query không được framework tự bổ sung predicate như mong muốn.

Ví dụ thao tác được thiết kế rõ điều kiện tenant:

```java
int changed = em.createQuery("""
    update Product p
    set p.active = false
    where p.tenantId = :tenantId
      and p.discontinuedAt < :cutoff
    """)
    .setParameter("tenantId", tenantId)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Ví dụ giả định Product có thuộc tính `tenantId`. Cần kiểm thử đúng mapping tenant của dự án; không suy luận rằng mọi filter áp dụng đồng nhất cho SELECT, bulk HQL và native SQL ở mọi phiên bản.

## 22. Spring Data JPA @Modifying và bulk DML

Spring Data JPA hỗ trợ DML query qua `@Query` kết hợp `@Modifying`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying
    @Query("""
        update Product p
        set p.active = false
        where p.active = true
          and p.discontinuedAt < :cutoff
        """)
    int deactivateExpired(@Param("cutoff") Instant cutoff);
}
```

`@Modifying` cho Spring Data biết method chạy một DML query thay vì một query SELECT bình thường.

### 22.1. @Modifying không tự đồng bộ entity đang managed

`@Modifying` không biến bulk update thành `save(entity)`, không gọi callback per-entity và không đảm bảo optimistic version được tăng tự động.

Một service gọi repository method trong transaction vẫn cần quan tâm state của các Product đã load trước đó.

### 22.2. flushAutomatically và clearAutomatically

Spring Data JPA cung cấp các thuộc tính:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
    """)
int deactivateExpired(@Param("cutoff") Instant cutoff);
```

Ý nghĩa thông thường:

- `flushAutomatically = true`: flush EntityManager trước khi chạy modifying query.
- `clearAutomatically = true`: clear EntityManager sau khi chạy modifying query.

Đây là cơ chế hỗ trợ thao tác tương đương pattern flush–bulk–clear.

### 22.3. Vì sao clearAutomatically mặc định không nên tùy tiện bật?

Clear sau DML có thể detach tất cả entity đang managed trong transaction, bao gồm entity **không liên quan** đến query. Nếu một service lớn đang cập nhật các object khác và chờ commit bằng dirty checking, việc clear có thể làm mất các thay đổi chưa flush.

Vì vậy:

- Dùng cả flush/clear khi use case và boundary thực sự yêu cầu.
- Không thêm `clearAutomatically = true` vào mọi repository method một cách máy móc.
- Tốt nhất để bulk method được gọi từ một transaction chuyên biệt và tránh quản lý một graph lớn cùng lúc.
- Khi service cần trả dữ liệu mới, reload trong context phù hợp sau bulk.

### 22.4. Transaction ở service

Ví dụ:

```java
@Service
public class CatalogMaintenanceService {

    private final ProductRepository repository;

    public CatalogMaintenanceService(
            ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateExpired(Instant cutoff) {
        return repository.deactivateExpired(cutoff);
    }
}
```

Transaction manager đóng vai trò đảm bảo DML chạy trong transaction phù hợp. Không dựa vào việc mọi repository method tự tạo boundary theo ý định business. Nếu có nhiều bước DB cần atomicity, đặt transaction ở application service/use case.

`@Transactional(readOnly = true)` không phù hợp cho method cần bulk update; integration với Hibernate có thể điều chỉnh flush mode hoặc database connection theo hướng read-only.

## 23. Spring Data delete methods: derived delete và @Modifying bulk delete

Cần phân biệt **derived delete method** với **@Modifying bulk delete query**.

Ví dụ:

```java
long deleteByStatus(String status);
```

Tùy Spring Data JPA version, dạng derived delete query có thể thực hiện quy trình tìm entity rồi xóa từng entity, nhằm giữ lifecycle callbacks/cascade phù hợp.

Trong khi đó:

```java
@Modifying
@Query("""
    delete from PurchaseOrder o
    where o.status = :status
    """)
int bulkDeleteByStatus(@Param("status") String status);
```

là bulk DML qua `executeUpdate()`, nên không đi qua per-entity removal callbacks.

**Tên method cùng có chữ delete không đủ để kết luận semantics.** Phải xem Spring Data query derivation, annotation và SQL thực tế.

Nếu nghiệp vụ phụ thuộc `@PreRemove` hoặc cascade, chọn đường entity removal. Nếu chủ đích bulk delete trực tiếp, cần thiết kế FK/audit/cache/context phù hợp.

## 24. Khi nào nên dùng entity update thay vì bulk update?

Bulk update thích hợp khi:

- Quy tắc thay đổi có thể biểu đạt bằng một điều kiện WHERE và các biểu thức SET.
- Không cần gọi domain method cho từng entity.
- Không cần callback/listener per-entity.
- Không cần cascade/orphan removal theo entity lifecycle.
- Đã thiết kế version, audit, cache và transaction tương ứng.
- Số row lớn khiến tải từng entity trở nên lãng phí.
- Có thể xác định rõ affected set và chấp nhận semantics của SQL trực tiếp.

Ngược lại, nên cân nhắc managed entity path khi:

- Mỗi entity có invariant phức tạp.
- Cần gọi method domain để quyết định trạng thái mới.
- Cần `@PreUpdate` / `@PreRemove` hoặc event trên từng entity.
- Cần cascade removal đúng mapping.
- Optimistic locking theo entity là phần bắt buộc và không muốn tự mô hình hóa trong DML.
- Cần xử lý khác nhau theo từng entity.
- Số entity không quá lớn và JDBC batching có thể đáp ứng.

### 24.1. JDBC batching là một phương án trung gian

Nếu cần giữ callbacks/version nhưng phải cập nhật nhiều entity, có thể dùng entity loop kết hợp JDBC batching:

```java
for (int i = 0; i < products.size(); i++) {
    products.get(i).deactivate();

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}
```

Đây chỉ là minh họa; khi clear, các Product còn lại trong danh sách có thể trở thành detached nếu đã loaded toàn bộ, nên vòng lặp như trên **không phải thiết kế batch hoàn chỉnh**.

Một thiết kế batch an toàn thường tải từng chunk trong context hiện hành, sửa các entity thuộc chunk, flush/clear rồi tải chunk tiếp theo, hoặc dùng stateless/bulk path theo yêu cầu.

### 24.2. StatelessSession khác bulk DML

Hibernate `StatelessSession` là API riêng có semantics persistence context/lifecycle khác Session stateful và hỗ trợ thao tác hàng loạt; nó không phải cách “tắt dirty checking nhưng vẫn giữ mọi callback/cascade như bình thường”.

Nếu cần dùng, hãy kiểm tra API và các hạn chế theo Hibernate version. Đừng coi StatelesSession là phương án tự động tương đương với managed entity path.

## 25. Ví dụ batch managed đúng ranh giới hơn

Một hướng xử lý theo chunk:

```java
@Transactional
public void deactivateIds(List<Long> ids) {
    int chunkSize = 50;

    for (int from = 0; from < ids.size(); from += chunkSize) {
        List<Long> chunkIds = ids.subList(
            from,
            Math.min(from + chunkSize, ids.size())
        );

        List<Product> chunk = em.createQuery("""
            select p
            from Product p
            where p.id in :ids
            """, Product.class)
            .setParameter("ids", chunkIds)
            .getResultList();

        for (Product product : chunk) {
            product.deactivate();
        }

        em.flush();
        em.clear();
    }
}
```

Ưu điểm:

- Entity trong chunk được managed khi cập nhật.
- Callback/version hoạt động theo đường entity update thông thường.
- Persistence context được giải phóng sau mỗi chunk.
- Không giữ tất cả entity của toàn bộ batch trong memory.

Giới hạn:

- Đây vẫn là một transaction duy nhất nếu annotation bao toàn bộ method; mỗi flush/clear **không phải commit riêng**.
- Nếu transaction cuối rollback, các SQL đã flush trước đó vẫn có thể bị rollback.
- Với nhiều row, transaction vẫn có thể rất dài.
- Cần xử lý version conflict, retry và thứ tự xử lý.
- Các association/constraint cần kiểm tra theo domain cụ thể.

Nếu cho phép commit mỗi chunk, phải đặt transaction boundary **thực sự** cho từng chunk, chấp nhận partial progress và thiết kế idempotency/checkpoint phù hợp.

## 26. Bulk DELETE và dữ liệu dùng chung

Giả sử `Product` được nhiều `OrderLine` tham chiếu. Một bulk delete Product:

```java
em.createQuery("""
    delete from Product p
    where p.active = false
    """).executeUpdate();
```

có thể vi phạm FK từ `order_lines.product_id` tới `products.id`. Điều đó là đúng nếu domain không cho phép xóa sản phẩm đã từng xuất hiện trong đơn hàng.

Không nên giải quyết bằng cách bật ON DELETE CASCADE lên order lines nếu làm thế sẽ xóa lịch sử đơn hàng. Có thể:

- Chỉ đánh dấu Product inactive/archived.
- Tách product catalog với snapshot thông tin sản phẩm trong order line.
- Thực hiện retention/purge policy riêng.
- Xóa chỉ những product thật sự không được tham chiếu theo query/constraint.

Bulk DELETE **không tự biết** entity nào có vòng đời độc lập hoặc được nhiều aggregate dùng chung.

## 27. Audit strategy khi cần bulk update

Nếu hệ thống có yêu cầu ghi nhật ký thay đổi, hãy quyết định mức granularity:

### 27.1. Audit theo từng row

Cần biết mỗi Product trước/sau như thế nào. Bulk update đơn giản sẽ không tạo callback audit per-entity. Các giải pháp có thể gồm:

- Entity lifecycle path khi số row vừa phải.
- Database trigger ghi audit rows.
- SQL đặc thù DB có `RETURNING`/CTE để capture affected rows.
- Snapshot/temporary table trước thay đổi, nếu được thiết kế transaction chính xác.
- CDC/outbox architecture với semantics rõ.

### 27.2. Audit theo tác vụ

Nếu chỉ cần ghi “job 123 đã vô hiệu hóa N sản phẩm trước ngày X”, có thể ghi một batch audit record trong cùng transaction:

```java
int affected = em.createQuery("""
    update Product p
    set p.active = false
    where p.discontinuedAt < :cutoff
      and p.active = true
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();

em.persist(new MaintenanceAudit(
    jobId,
    "DEACTIVATE_DISCONTINUED",
    affected,
    clock.instant()
));
```

`MaintenanceAudit` là entity ứng dụng cần định nghĩa. Cách này không cung cấp lịch sử từng Product; nó chỉ ghi lại thao tác bulk theo mức job.

**Phải quyết định audit contract trước khi thay entity loop bằng bulk DML**, không xem sự mất callback là chi tiết nhỏ.

## 28. DML và query visibility trong cùng transaction

Sau bulk update, một JPQL query aggregate đi xuống database có thể thấy kết quả SQL mới trong cùng transaction:

```java
em.createQuery("""
    update Product p
    set p.active = false
    where p.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();

Long activeCount = em.createQuery("""
    select count(p)
    from Product p
    where p.active = true
    """, Long.class)
    .getSingleResult();
```

Nhưng một managed Product đã load trước đó vẫn có thể báo `active=true`.

Đây là điểm cần phân biệt:

- **Query aggregate dựa vào database:** thường phản ánh state đã được bulk SQL đồng bộ trong transaction hiện tại.
- **Getter trên managed object cũ:** có thể đọc first-level cache stale.
- **Giao dịch khác:** có nhìn thấy bulk change hay không phụ thuộc commit/isolation.
- **Second-level/query cache:** có cơ chế invalidation riêng, không thay thế context refresh.

Không dùng một phép đọc trong Java để suy ra database chưa nhận SQL, cũng không dùng một aggregate query đúng để kết luận mọi managed entity đã đồng bộ.

## 29. Bulk DML và optimistic conflict khi nhiều transaction

Hai transaction có thể cùng chạy bulk update. Nếu cả hai chỉ dùng điều kiện thông thường:

```sql
UPDATE products SET active = false WHERE id = 10;
UPDATE products SET price = 90 WHERE id = 10;
```

database thực thi theo locking/isolation riêng. Nhưng **optimistic locking ở mức @Version không tự áp** nếu query không kiểm tra/increment version phù hợp.

### 29.1. Khi nào dùng điều kiện expected state?

Ví dụ chỉ chuyển từ trạng thái ACTIVE sang ARCHIVED:

```java
int count = em.createQuery("""
    update Product p
    set p.status = 'ARCHIVED'
    where p.id = :id
      and p.status = 'ACTIVE'
    """)
    .setParameter("id", id)
    .executeUpdate();

if (count != 1) {
    // Không có row đủ điều kiện để chuyển trạng thái.
}
```

Ví dụ giả định Product có thuộc tính `status`. Đây là **conditional update** giúp bảo vệ state transition đơn giản ở database, nhưng không thay thế version nếu các thay đổi khác cũng cần được coi là conflict.

### 29.2. Deadlock/serialization failure

Một bulk update nhiều row có thể tranh lock với transaction khác. Nếu DB phát hiện deadlock hoặc serialization failure, cần rollback và cân nhắc retry **toàn bộ transaction** trong một context mới.

Không nên catch exception rồi tiếp tục dùng EntityManager/Session đã lỗi để chạy lại một bulk query khác và cố commit.

## 30. HQL bulk UPDATE với association: giới hạn query và subquery

Bulk HQL/JPQL update/delete có grammar khác SELECT. Đừng viết join tùy ý trong phần UPDATE/DELETE rồi mặc định mọi SELECT join đều hợp lệ ở DML root.

Ví dụ muốn cập nhật Product thuộc Category có mã:

```java
int changed = em.createQuery("""
    update Product p
    set p.active = false
    where p.category.id in (
        select c.id
        from Category c
        where c.code = :code
    )
    """)
    .setParameter("code", code)
    .executeUpdate();
```

Subquery là cách biểu đạt quan hệ điều kiện mà không cần tải entity từng hàng, nhưng cú pháp JPQL/HQL cụ thể và hỗ trợ của database/dialect phải được kiểm tra theo version.

### 30.1. Đừng nhầm association traversal với lifecycle

Bulk DML có thể tham chiếu relation trong điều kiện WHERE, nhưng không có nghĩa Hibernate sẽ cascade update tới entity liên quan hoặc gọi các callback của chúng.

### 30.2. SQL thực tế có thể gồm nhiều statement

Khi update/delete trên inheritance hierarchy hoặc mapping nhiều bảng, Hibernate có thể dùng nhiều SQL statement dù HQL chỉ có một câu. Việc này không biến thao tác thành entity-by-entity lifecycle processing.

## 31. Khi nào nên chọn bulk-only unit of work?

Một mô hình an toàn cho maintenance job:

```text
BEGIN TRANSACTION
    |
    +-- HQL bulk UPDATE/DELETE
    |
    +-- INSERT maintenance audit/outbox summary
    |
    +-- COMMIT
    |
    v
Kết thúc context; các request khác tải dữ liệu mới
```

Nếu không cần managed entities trong cùng transaction, không tạo ra state stale trong context để rồi phải clear.

Ví dụ:

```java
@Service
public class ProductMaintenanceService {

    private final EntityManager em;
    private final Clock clock;

    public ProductMaintenanceService(
            EntityManager em,
            Clock clock) {
        this.em = em;
        this.clock = clock;
    }

    @Transactional
    public int deactivate(Instant cutoff) {
        Instant now = clock.instant();

        return em.createQuery("""
            update Product p
            set p.active = false,
                p.updatedAt = :now
            where p.active = true
              and p.discontinuedAt < :cutoff
            """)
            .setParameter("now", now)
            .setParameter("cutoff", cutoff)
            .executeUpdate();
    }
}
```

Điều kiện ở ví dụ:

- Không có callback per-entity cần thiết.
- Versioning/concurrency policy đã được xem xét (ví dụ thêm HQL versioned hoặc set version phù hợp nếu yêu cầu).
- Query scope (tenant/visibility) đúng.
- Database constraints phù hợp.
- Không dùng managed Product state cũ sau thao tác.
- Kết quả audit/event được ghi tường minh nếu nghiệp vụ cần.

## 32. Thiết kế một migration chuyển từ entity loop sang bulk DML

Giả sử code hiện tại:

```java
for (Product product : products) {
    product.deactivate();
}
```

Trước khi thay bằng:

```java
update Product p set p.active = false where ...
```

hãy điều tra các khác biệt hành vi:

1. `deactivate()` có kiểm tra invariant nào không?
2. `@PreUpdate` có sửa audit fields không?
3. Entity listeners có phát domain events hoặc ghi audit không?
4. `@Version` có được dùng để phát hiện conflict không?
5. Có association cascade hoặc collection lifecycle liên quan không?
6. Có cache cần invalidation ngoài Hibernate không?
7. Có rule tenant/soft delete/filter không?
8. Có row nào cần được loại khỏi update theo trạng thái hiện tại không?
9. Có yêu cầu trả danh sách ID row đã đổi không?
10. Có thể rollback toàn bộ nếu chỉ một row vi phạm constraint không?
11. Có cần giữ khả năng partial success/chunk processing không?
12. Hibernate version/dialect sẽ sinh SQL gì?

Sau khi xác định các semantics cần giữ, có thể thiết kế query bulk tương đương về **nghiệp vụ**, không chỉ tương tự về cú pháp.

## 33. Kiểm thử bulk DML: không chỉ kiểm tra affected count

Một test đúng nên kiểm tra **state trong database, context và concurrency**.

### 33.1. Kiểm tra state stale

1. Mở transaction và tải Product#10.
2. Bulk update `active=false`.
3. Xác nhận `product.isActive()` có thể còn true trước refresh/clear.
4. Refresh hoặc clear + reload.
5. Xác nhận state mới được đọc từ database.

### 33.2. Kiểm tra version

1. Tải Product version 3.
2. Chạy bulk update thông thường.
3. Xem version có tăng hay không.
4. Thực hiện cùng kịch bản với `update versioned` hoặc explicit version increment.
5. Kiểm tra transaction giữ stale version có gặp optimistic conflict như kỳ vọng không.

### 33.3. Kiểm tra callback

Một listener đếm số lần `@PreUpdate` / `@PreRemove` được gọi trong môi trường test. So sánh:

- Managed update/remove entity.
- Bulk update/delete cùng số row.

Kỳ vọng bulk path không tạo callback per-entity theo lifecycle tương ứng.

### 33.4. Kiểm tra FK/cascade

Tạo Order có OrderLines. So sánh `em.remove(order)` với bulk `delete PurchaseOrder`, xác nhận hành vi FK/ON DELETE CASCADE và callback theo schema thực tế.

### 33.5. Kiểm tra Spring @Modifying

Với `flushAutomatically` và `clearAutomatically`:

- Có managed changes pending trước query.
- Sau query, context có còn chứa entity cũ không?
- Những thay đổi dự định giữ đã được flush chưa?
- Có lost changes do clear không?
- Có dirty state nào bị ghi ngoài ý định do flush trước query không?

### 33.6. Kiểm tra audit/cache

Dùng integration test với database/cache configuration thực tế để xác minh audit row, L2/query cache invalidation và trạng thái read-after-bulk.

### 33.7. Kiểm tra trên database tương ứng production

H2 hoặc in-memory DB có thể có FK/locking/SQL semantics khác PostgreSQL, MySQL hay Oracle. Đặc biệt với multi-table bulk mutation, versioned updates, temp tables và transaction locks, nên có test chạy trên dialect/database phù hợp.

## 34. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Bulk UPDATE thành công nhưng getter vẫn trả giá trị cũ | Managed object trong first-level cache stale | Refresh, clear + reload, hoặc transaction riêng |
| `find()` lại vẫn thấy giá trị cũ | Identity map trả cùng object | Clear/refresh hoặc dùng context mới |
| Cập nhật sau bulk ghi đè cột đã đổi | Snapshot managed cũ, version bulk không tăng | Version policy rõ và tránh trộn state stale |
| Version không tăng sau bulk | Bulk update bỏ qua per-entity versioning mặc định | HQL `update versioned` hoặc explicit version increment phù hợp |
| `@PreUpdate` không chạy | Bulk không qua entity lifecycle | Set audit fields trong DML, audit strategy riêng |
| `@PreRemove` không chạy | Bulk DELETE không gọi `remove(entity)` từng row | Dùng entity removal path nếu callback bắt buộc |
| Bulk DELETE bị FK violation | Child rows còn tham chiếu root | Thiết kế cleanup/ON DELETE policy đúng domain |
| Xóa order làm mất dữ liệu không dự kiến | DB ON DELETE CASCADE quá rộng | Kiểm tra FK và ownership trước bulk |
| `clear()` làm mất thay đổi chưa lưu | Pending managed changes chưa flush | Flush có chủ đích trước clear; tách workflow |
| `refresh()` làm mất setter vừa gọi | Refresh ghi đè state trong memory | Không refresh khi còn thay đổi cần giữ |
| Job update nhưng không có audit revision | Audit dựa trên entity listeners | Audit SQL/outbox/trigger hoặc entity path |
| Cache L2 được evict nhưng object vẫn stale | First-level cache độc lập với L2 | Xử lý EntityManager context |
| Affected count khác số physical rows | Multi-table inheritance/DB semantics | Hiểu số đếm logic và SQL thực tế |
| Query chạy quá lâu/lock nhiều row | Bulk update tập lớn trong transaction dài | Index, chunk, scheduling, monitoring |
| Native SQL làm cache lệch | Thiếu synchronized spaces/invalidation | Khai báo synchronization hoặc cache eviction |
| Bulk query chạy nhầm tenant | WHERE/filter không giới hạn đúng | Tenant predicate và integration test |
| Spring @Modifying trong readOnly transaction | Transaction manager/provider tối ưu đường đọc | Đặt transaction ghi phù hợp |
| Không phát event khi bulk update | Event chỉ phát từ domain method/callback | Explicit outbox/batch event policy |

## 35. Bảng quyết định: dùng cách nào?

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Cập nhật một aggregate có invariant phức tạp | Load managed root, gọi domain methods, flush/commit |
| Vô hiệu hóa nhiều row theo điều kiện đơn giản | HQL bulk UPDATE với audit/version policy rõ |
| Xóa root cần cascade/callback của child | EntityManager.remove(root) theo mapping |
| Dọn dữ liệu lớn, FK xử lý được, không cần callbacks | Bulk DELETE có transaction và schema policy |
| Nâng version cho các row bị bulk update | HQL `update versioned` hoặc explicit version increment có kiểm chứng |
| Chỉ cập nhật khi version kỳ vọng còn đúng | Conditional DML WHERE id + expectedVersion và xử lý count |
| Cần audit per-entity | Entity lifecycle hoặc DB audit/CDC/SQL riêng |
| Cần audit theo job | Bulk DML + một audit summary record |
| Context đã chứa nhiều entity trước bulk | Flush có chủ đích; bulk; clear/refresh/reload |
| Dự án dùng Spring Data JPA | `@Modifying` và transaction boundary rõ |
| Muốn tối ưu nhưng vẫn giữ callback/version của từng entity | Managed entity batching theo chunk |
| Cần DB-specific RETURNING/advanced mutation | Native SQL khi rõ provider/dialect và kiểm soát cache |

## 36. Bài tập thực hành

### Bài 1: State stale

Có Product#10 đang `active=true`. Trong cùng EntityManager:

```java
Product p = em.find(Product.class, 10L);

em.createQuery("""
    update Product x set x.active = false where x.id = 10
    """).executeUpdate();

System.out.println(p.isActive());
```

**Câu hỏi:** Lệnh in có chắc chắn là `false`?

**Giải thích:** Không. `p` là managed instance đã load; bulk query không tự cập nhật field trong object. Có thể vẫn in `true`. Dùng `refresh(p)` hoặc clear + reload để lấy state mới từ database.

### Bài 2: Version không tăng

Product#10 có version 3. Bulk query:

```sql
update Product p set p.price = 100 where p.id = 10
```

**Câu hỏi:** Có thể mặc định version thành 4 không?

**Giải thích:** Không. Bulk UPDATE mặc định không áp per-entity version increment. Cần dùng HQL `update versioned` hoặc set version có chủ đích nếu yêu cầu.

### Bài 3: Callback

Entity có:

```java
@PreUpdate
void audit() { updatedAt = Instant.now(); }
```

Bulk query:

```sql
update Product p set p.active = false where p.active = true
```

**Câu hỏi:** updatedAt có chắc được cập nhật cho từng row không?

**Giải thích:** Không qua callback JPA. Nếu cần, query phải set field rõ ràng, hoặc database trigger/audit mechanism khác đảm nhận.

### Bài 4: Cascade REMOVE

Order chứa OrderLine, association có `cascade = REMOVE`. Chạy bulk:

```sql
delete from PurchaseOrder o where o.status = 'DRAFT'
```

**Câu hỏi:** Hibernate có tự gọi `remove(line)` và `@PreRemove` cho từng line không?

**Giải thích:** Không. Bulk delete không đi qua entity lifecycle removal. FK hoặc DB cascade quyết định khả năng xóa vật lý, còn callbacks không tự chạy.

### Bài 5: Flush–bulk–clear

Trong transaction:

```java
Product p = em.find(Product.class, 10L);
p.changePrice(new BigDecimal("200.00"));

em.createQuery("""
    update Product x set x.active = false where x.id = 11
    """).executeUpdate();

em.clear();
```

**Câu hỏi:** Price của Product#10 có được ghi không?

**Giải thích:** Phụ thuộc việc thay đổi đã được flush trước clear hay chưa. Nếu còn pending, clear detach entity và thay đổi có thể bị mất. Nếu cần đảm bảo, explicit `flush()` trước bulk/clear ở boundary phù hợp.

### Bài 6: Optimistic conditional update

```java
int n = em.createQuery("""
    update Product p
    set p.price = :price,
        p.version = p.version + 1
    where p.id = :id
      and p.version = :expectedVersion
    """)
    .setParameter("price", price)
    .setParameter("id", id)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();
```

**Câu hỏi:** Nếu `n == 0` thì có thể kết luận điều gì?

**Giải thích:** Không có row được cập nhật theo điều kiện. Có thể ID không tồn tại hoặc version đã khác. Ứng dụng cần xử lý theo policy không tìm thấy/xung đột; query không tự gọi `@PreUpdate`.

## 37. Quy trình thiết kế bulk DML an toàn

Trước khi đưa bulk DML vào một use case, làm rõ các vấn đề:

1. **Mục tiêu:** thay đổi những row nào, theo tiêu chí nào?
2. **Quy tắc nghiệp vụ:** có cần domain method hoặc validation từng entity?
3. **Versioning:** có cần tăng version hoặc kiểm tra expected version không?
4. **Callbacks:** có listener cập nhật timestamp, audit, domain events hay cleanup không?
5. **Cascade:** nếu xóa, child có cần được remove theo lifecycle entity không?
6. **Database constraints:** FK, unique, check và trigger ảnh hưởng gì?
7. **Soft delete/tenant/filter:** query có giới hạn đúng phạm vi?
8. **Persistence context:** trong transaction có entity nào đã load hoặc pending changes không?
9. **Flush trước:** có thay đổi managed cần được gửi xuống DB trước khi bulk query chạy không?
10. **Clear/refresh sau:** code có còn sử dụng managed entity có thể stale không?
11. **Cache:** có L2/query/custom cache hay external writers cần invalidation?
12. **Audit/event:** sẽ ghi thông tin thay đổi ở mức row hay job bằng cách nào?
13. **Transaction:** một bulk statement có nằm trong atomic unit of work đúng không?
14. **Concurrency:** row locks, optimistic conflicts, deadlocks và retry được xử lý thế nào?
15. **Performance:** có index cho WHERE, SQL plan tốt và giới hạn batch size hợp lý không?
16. **Tests:** đã xác minh state DB, managed state, version, callback, FK và rollback trong database thực tế chưa?

Một query ngắn có thể làm thay đổi hàng triệu row. Độ ngắn của code không phải thước đo rủi ro thấp.

## 38. Ghi nhớ

- **Bulk HQL/JPQL UPDATE và DELETE thao tác trực tiếp trên database**, không phải vòng lặp tự động qua từng managed entity.
- **Persistence context không tự đồng bộ** sau bulk DML: managed object đã load có thể chứa state stale dù database đã thay đổi.
- `find()` cùng ID trong cùng context thường trả managed instance hiện có; muốn state mới cần refresh, clear + reload hoặc context mới.
- **Flush trước bulk** khi điều kiện DML phụ thuộc các managed changes chưa được gửi xuống database.
- **Clear sau bulk** khi không được tiếp tục dùng state managed cũ; nhớ clear có thể làm mất pending changes chưa flush.
- **`@Version` không tự tăng trong bulk update mặc định** như với managed entity update; cần chính sách version tường minh.
- Hibernate HQL có extension **`update versioned`**, nhưng vẫn không gọi entity callbacks hoặc đồng bộ first-level cache.
- Có thể dùng **numeric version increment** và `WHERE version = :expectedVersion` cho conditional bulk update khi query/dialect hỗ trợ.
- **`@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` không chạy per-entity** qua bulk DML.
- Hibernate Envers/listener audit dựa trên lifecycle có thể không ghi revision per-entity cho bulk mutation; phải thiết kế audit riêng.
- **Database triggers/constraints vẫn hoạt động** theo SQL thực tế; chúng khác JPA callbacks.
- **Cascade REMOVE, orphanRemoval và domain methods không tự chạy** như `remove(entity)` khi dùng bulk DELETE.
- **ON DELETE CASCADE** ở database có thể xóa child rows, nhưng không phát callback Java.
- **Bulk DML có thể cần nhiều SQL** với inheritance mapping nhiều bảng; affected count không nhất thiết bằng tổng physical row counts.
- **Second-level cache invalidation không sửa first-level cache**. Native SQL/external writers cần thêm chính sách synchronization.
- **Spring Data `@Modifying`** biểu diễn bulk query; `flushAutomatically`/`clearAutomatically` hỗ trợ pattern flush–bulk–clear nhưng có side effect với context.
- **Soft delete, tenant filters và authorization** phải được kiểm tra ở mọi con đường DML, không chỉ SELECT thông thường.
- Bulk DML phù hợp thay đổi tập hàng đơn giản; **managed entity path** phù hợp khi cần invariant, version/callback/cascade per-entity.
- Mọi thao tác phải nằm trong **transaction boundary** đúng; bulk SQL thành công không đồng nghĩa commit.

**Kết luận:** Bulk DML là công cụ mạnh cho truy vấn ghi quy mô lớn, nhưng đổi lại nó bỏ qua nhiều hành vi vốn được Hibernate cung cấp khi thao tác trên managed entity. Cần xem bulk update/delete như **một con đường thay đổi dữ liệu riêng**, với chính sách rõ ràng về persistence context, versioning, callbacks, cascade, audit, cache và transaction. Một thiết kế an toàn không chỉ hỏi “câu UPDATE có chạy nhanh không?”, mà còn hỏi “những bảo đảm nào từ entity lifecycle đã bị bỏ qua và ai chịu trách nhiệm thay thế chúng?”.
