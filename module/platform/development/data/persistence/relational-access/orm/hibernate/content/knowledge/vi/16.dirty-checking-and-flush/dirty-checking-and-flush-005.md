# Thời điểm flush trước truy vấn hoặc khi kết thúc giao dịch trong Hibernate ORM

Khi một entity đang được Hibernate quản lý thay đổi, Hibernate không nhất thiết chạy câu lệnh `UPDATE` ngay tại thời điểm setter được gọi. ORM thường giữ các thay đổi trong **persistence context**, sau đó đồng bộ chúng với cơ sở dữ liệu ở một thời điểm thích hợp bằng thao tác **flush**.

Điều này dẫn đến hai câu hỏi quan trọng:

1. **Tại sao vừa thay đổi một entity, chưa gọi `commit()`, nhưng một truy vấn ngay sau đó đã khiến Hibernate chạy `INSERT`/`UPDATE`/`DELETE`?**
2. **Nếu không chạy truy vấn, khi nào các thay đổi được gửi xuống database?**

Câu trả lời nằm ở cơ chế **dirty checking**, **flush mode**, **phạm vi bảng mà truy vấn sử dụng** và **vòng đời transaction**. Trong Hibernate, ở chế độ thông dụng `AUTO`, flush thường được cân nhắc **trước truy vấn có thể bị ảnh hưởng bởi thay đổi chưa đồng bộ** và **khi transaction kết thúc bằng commit**.

Bài học tập trung giải thích chính xác các thời điểm ấy, vì sao Hibernate đôi khi bỏ qua flush trước một truy vấn, sự khác biệt giữa JPQL/HQL với native SQL, và cách kiểm soát flush mà không làm mất tính đúng đắn của dữ liệu.

## 1. Tư duy nền tảng: thay đổi trong bộ nhớ và dữ liệu ở database

Xét entity `Product`:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
```

Nếu gọi:

```java
Product product = entityManager.find(Product.class, productId);

product.changePrice(new BigDecimal("199.00"));
```

thì giá trị `product.price` trong Java đã đổi. Nhưng chưa chắc Hibernate đã gửi:

```sql
UPDATE products SET price = 199.00 WHERE id = ...;
```

Hibernate có thể đợi đến lúc flush để phát hiện entity đã thay đổi và lên lịch SQL. Việc chưa có SQL ngay sau setter **không có nghĩa** thay đổi bị bỏ qua: đối tượng đang ở trạng thái **managed**, nên persistence context chịu trách nhiệm đồng bộ theo hợp đồng transaction và flush mode.

### Sơ đồ các lớp trạng thái

```text
Java application
    |
    | product.changePrice(...)
    v
Managed entity trong persistence context
    |
    | trạng thái đã thay đổi (dirty)
    | Hibernate kiểm tra / ghi nhận thay đổi
    v
Flush / auto-flush khi cần
    |
    | INSERT / UPDATE / DELETE qua JDBC
    v
Database transaction (chưa chắc commit)
    |
    | COMMIT thành công
    v
Dữ liệu được xác nhận theo giao dịch
```

Không được gộp ba mốc **thay đổi object**, **flush SQL** và **commit transaction** thành một.

## 2. Dirty checking hoạt động như thế nào?

**Dirty checking** là khả năng Hibernate phát hiện thay đổi của entity đang được quản lý để sinh SQL cập nhật khi cần.

Khi một entity được tải vào persistence context, Hibernate có thể giữ thông tin trạng thái ban đầu (*loaded state/snapshot*) của các thuộc tính cần theo dõi. Khi flush, ORM so sánh hoặc dùng thông tin theo dõi thay đổi để xác định entity nào cần `UPDATE`.

Ví dụ:

```java
Product product = entityManager.find(Product.class, 10L);
// Trạng thái đã tải: price = 100.00

product.changePrice(new BigDecimal("120.00"));
// Trạng thái hiện tại: price = 120.00

// Chưa gọi SQL UPDATE chỉ bởi changePrice().
entityManager.flush();
// Hibernate đồng bộ thay đổi khi flush nếu entity còn managed
// và thao tác update là cần thiết.
```

Cơ chế thực hiện có thể dựa trên snapshot hoặc **bytecode enhancement** với khả năng tracking thay đổi. Tùy mapping, Hibernate còn xét thuộc tính updatable, entity read-only, `@Immutable`, interceptor và các chi tiết versioning.

Điểm quan trọng là **dirty checking gắn với managed entity**:

- **Transient**: object mới tạo, chưa được quản lý; thay đổi nó không tự tạo SQL.
- **Managed**: được persistence context theo dõi; thay đổi có thể được flush.
- **Detached**: không còn được context hiện tại theo dõi; sửa object không tự tạo SQL.
- **Removed**: entity đã được yêu cầu xóa; thao tác xóa sẽ được xử lý theo vòng đời persistence.

### Không cần `save()` sau mỗi setter

Đối với entity đã managed:

```java
Product product = entityManager.find(Product.class, id);
product.changePrice(new BigDecimal("120.00"));

// Trong transaction, không cần persist(product) lần nữa.
```

Nếu transaction commit bình thường với flush mode phù hợp, Hibernate đồng bộ thay đổi. Trong ứng dụng Spring dùng `@Transactional`, một service thường chỉ cần tải entity, gọi method domain rồi kết thúc transaction.

Ngược lại, đối với detached entity, dirty checking của EntityManager mới không tự áp dụng. Cần dùng managed instance hoặc một quy trình `merge` có chủ đích.

## 3. Flush là gì và không phải là gì?

**Flush** là quá trình đồng bộ các thay đổi persistence đang được quản lý với cơ sở dữ liệu, bằng các thao tác SQL cần thiết trong **transaction đang hoạt động**.

Thông thường nó có thể liên quan:

- `INSERT` entity mới đã được persist.
- `UPDATE` entity managed có các thuộc tính cần ghi.
- `DELETE` entity được đánh dấu removed.
- Thao tác trên collection/join table hoặc khóa ngoại khi quan hệ thay đổi.
- Đồng bộ version, các ràng buộc và một số hành vi lifecycle/callback tương ứng.

Các thao tác ấy được Hibernate tổ chức và thực thi theo cơ chế internal action queue và dependency; **thứ tự SQL không nhất thiết giống thứ tự setter/persist/remove trong Java**.

### Flush không đồng nghĩa commit

| Khái niệm | Làm gì? | Transaction đã kết thúc chưa? |
|---|---|---|
| **Thay đổi managed entity** | Đổi state trong persistence context | Chưa |
| **`flush()`** | Đưa những thay đổi đang chờ xuống database bằng SQL | Chưa, nếu chưa commit |
| **`commit()`** | Yêu cầu database xác nhận transaction | Có, nếu commit thành công |
| **`rollback()`** | Hủy những thay đổi database thuộc transaction theo semantics giao dịch | Có, theo hướng rollback |

Ví dụ:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product product = em.find(Product.class, 10L);
product.changePrice(new BigDecimal("120.00"));

em.flush(); // SQL UPDATE có thể đã chạy.

tx.rollback(); // UPDATE không trở thành dữ liệu đã commit.
```

Sau `flush()`, SQL đã được gửi và có thể đã thỏa/vi phạm các ràng buộc do database kiểm tra ở thời điểm ấy. Nhưng các transaction khác có nhìn thấy giá trị mới hay không phụ thuộc **transaction isolation**, trạng thái commit và cơ chế database.

**Một entity có ID hoặc một câu UPDATE đã xuất hiện trong log không chứng minh transaction đã commit.**

### Tránh gọi `flush()` ngoài transaction

Trong ứng dụng JPA thông thường, việc gọi `EntityManager.flush()` yêu cầu transaction thích hợp; nếu không có transaction đang hoạt động, có thể nhận `TransactionRequiredException`. Một số đường native Hibernate và cấu hình legacy có đặc điểm khác, nhưng không nên xây dựng logic ứng dụng dựa trên flush ngoài transaction.

## 4. Hibernate flush khi nào?

Trong một ứng dụng transaction thông thường, các điểm kích hoạt flush đáng chú ý gồm:

1. **Explicit flush:** code gọi `entityManager.flush()` hoặc `session.flush()`.
2. **Auto-flush trước truy vấn:** ở chế độ `AUTO`, truy vấn có thể cần thấy các thay đổi chưa gửi xuống database.
3. **Flush khi commit:** trước khi transaction được commit, Hibernate thường đồng bộ những thay đổi đang chờ.
4. **Một số đường thực thi đặc biệt:** việc lấy ID `IDENTITY`, một số thao tác native SQL, lifecycle hoặc cấu hình riêng có thể khiến SQL xảy ra sớm; **không phải mọi SQL sớm đều là một đợt flush toàn bộ persistence context**.

Sơ đồ:

```text
begin transaction
       |
       v
persist / edit / remove
       |
       +----> flush() do ứng dụng gọi
       |
       +----> query có thể cần state vừa thay đổi
       |              |
       |              v
       |          AUTO flush khi thích hợp
       |
       +----> commit transaction
                      |
                      v
             đồng bộ thay đổi còn chờ
                      |
                      v
                   COMMIT
```

Điểm 2 cần được giải thích kỹ: **`AUTO` không có nghĩa Hibernate luôn flush trước tất cả truy vấn JPQL/HQL**.

## 5. Flush mode: chính sách quyết định thời điểm đồng bộ

Jakarta Persistence định nghĩa hai giá trị `FlushModeType` công khai:

- **`AUTO`**: mặc định trong mô hình JPA thông dụng; provider phải bảo đảm thay đổi trong persistence context có thể ảnh hưởng kết quả query được phản ánh khi xử lý query theo hợp đồng.
- **`COMMIT`**: cho phép trì hoãn flush chủ yếu đến commit; ảnh hưởng của các thay đổi chưa flush lên query được đặc tả để không thể kỳ vọng nhất quán tuyệt đối trước commit.

Hibernate native còn hỗ trợ `FlushMode` với những mức chi tiết hơn, điển hình gồm `ALWAYS`, `AUTO`, `COMMIT` và `MANUAL`. Ý nghĩa và tích hợp có thể phụ thuộc phiên bản/framework.

| Chế độ | Ý nghĩa thực tế thường gặp | Điểm cần lưu ý |
|---|---|---|
| **JPA `AUTO` / Hibernate `AUTO`** | Flush trước query nếu thay đổi có thể ảnh hưởng query; flush lúc commit | Không mặc định mọi query đều bắt buộc có SQL flush |
| **JPA `COMMIT` / Hibernate `COMMIT`** | Trì hoãn flush cho đến commit trong trường hợp thông thường | Query trước commit có thể không thấy các thay đổi đang chờ ở DB |
| **Hibernate `ALWAYS`** | Flush trước mỗi lần chạy query theo chính sách Hibernate native | Có thể tốn kém nếu thực hiện nhiều query liên tiếp |
| **Hibernate `MANUAL`** | Chỉ flush khi được gọi rõ ràng theo chính sách này | Commit có thể không tự đồng bộ những thay đổi còn chờ; dễ mất update ngoài ý định |

**Quan trọng:** JPA `FlushModeType` chỉ có `AUTO` và `COMMIT`; `ALWAYS`/`MANUAL` là khái niệm native Hibernate. Không đưa các giá trị riêng Hibernate vào `FlushModeType` của Jakarta Persistence.

### Đặt chế độ ở EntityManager

```java
import jakarta.persistence.FlushModeType;

em.setFlushMode(FlushModeType.AUTO);
```

Đặt cho một query:

```java
List<Product> products = em.createQuery("""
    select p from Product p
    where p.price >= :minPrice
    """, Product.class)
    .setParameter("minPrice", new BigDecimal("100.00"))
    .setFlushMode(FlushModeType.AUTO)
    .getResultList();
```

Flush mode của query có thể điều chỉnh cách query được đồng bộ so với lựa chọn mặc định của persistence context. Khi dùng `COMMIT`, không nên kỳ vọng query nhất thiết phản ánh đầy đủ mọi state chưa flush.

### Đặt chế độ ở Hibernate Session

Ví dụ API native:

```java
import org.hibernate.FlushMode;
import org.hibernate.Session;

Session session = em.unwrap(Session.class);
session.setHibernateFlushMode(FlushMode.AUTO);
```

Các cấu hình native này nên được dùng ở ranh giới infrastructure; tránh đổi flush mode ở nhiều lớp business rồi quên khôi phục. Framework transaction manager có thể điều chỉnh chế độ phù hợp với read-only transaction hoặc chính sách của chính nó.

## 6. Vì sao Hibernate có thể flush **trước** một truy vấn?

Giả sử bảng `products` hiện có:

| id | name | price |
|---:|---|---:|
| 10 | Bút | 10.00 |
| 11 | Sổ | 50.00 |

Trong transaction, ứng dụng đổi giá bút thành `120.00`:

```java
Product pen = em.find(Product.class, 10L);
pen.changePrice(new BigDecimal("120.00"));
```

Sau đó truy vấn:

```java
Long count = em.createQuery("""
    select count(p)
    from Product p
    where p.price >= :minimum
    """, Long.class)
    .setParameter("minimum", new BigDecimal("100.00"))
    .getSingleResult();
```

Nếu truy vấn đi thẳng xuống database **trước khi các thay đổi có liên quan được đồng bộ**, database có thể vẫn thấy `price = 10.00` cho row 10 và trả kết quả không phản ánh thay đổi đang managed.

Ở `AUTO`, Hibernate thường phát hiện truy vấn cần đọc bảng `products` và có pending update trên bảng đó, nên flush `UPDATE` trước khi thực hiện `SELECT count(...)`:

```text
Java: pen.price = 120.00 (managed, chưa UPDATE)
       |
       v
JPQL: count(Product where price >= 100)
       |
       v
Hibernate thấy thay đổi đang chờ liên quan bảng products
       |
       +--> UPDATE products SET price = 120.00 WHERE id = 10
       |
       +--> SELECT COUNT(*) FROM products WHERE price >= 100
       |
       v
Query phản ánh thay đổi đã flush trong transaction
```

Điều này làm kết quả query tuân theo ngữ nghĩa JPA `AUTO` ở mức cần thiết.

### Quy định của JPA và cách Hibernate hiện thực

JPA mô tả kết quả cần thấy các thay đổi có khả năng ảnh hưởng query; provider **có thể flush hoặc dùng cơ chế khác** để đáp ứng hợp đồng. Hibernate ORM thường dùng việc kiểm tra **query spaces** (các bảng liên quan đến query) và các thao tác đang chờ để quyết định có cần auto-flush hay không.

Vì vậy, có hai mức cần phân biệt:

- **Hợp đồng truy vấn:** query phải phản ánh các thay đổi liên quan theo flush mode `AUTO`.
- **Chiến lược thực hiện:** Hibernate có thể chọn flush dựa trên các bảng liên quan, không nhất thiết flush ngay khi có bất kỳ managed entity nào bị sửa.

Hibernate không bắt buộc chạy SQL `UPDATE` cho một entity không bị thay đổi thực sự chỉ vì có một truy vấn. Dirty checking có thể xác định không có gì cần ghi.

## 7. Bảng trùng nhau và query spaces: khi nào AUTO flush, khi nào không?

Một cơ chế tối ưu quan trọng là **so sánh các bảng mà query đọc với các bảng mà pending actions có thể ghi**.

### Tình huống A: query và pending change cùng bảng

```java
Product product = em.find(Product.class, productId);
product.changePrice(new BigDecimal("900.00"));

List<Product> expensive = em.createQuery("""
    select p
    from Product p
    where p.price > :limit
    """, Product.class)
    .setParameter("limit", new BigDecimal("500.00"))
    .getResultList();
```

Thay đổi và query đều liên quan `products`, nên AUTO flush thường xảy ra trước query nếu có SQL cần đồng bộ.

Đây là cách bảo đảm kết quả truy vấn không bỏ sót hàng vừa đổi giá.

### Tình huống B: query đọc bảng khác, không liên quan pending change

Giả sử có thêm entity `AuditEvent` mapping tới bảng `audit_events`. Code:

```java
Product product = em.find(Product.class, productId);
product.changePrice(new BigDecimal("900.00"));

Long totalEvents = em.createQuery("""
    select count(a)
    from AuditEvent a
    """, Long.class)
    .getSingleResult();
```

Nếu Hibernate xác định query chỉ đọc `audit_events` và pending change chỉ liên quan `products`, query `AuditEvent` **thường không cần flush** update của Product trước khi chạy.

```text
Pending update: products
Query reads:    audit_events
               |
               v
       không có bảng giao nhau
               |
               v
       AUTO có thể bỏ qua flush
```

Cơ chế này tránh SQL không cần thiết trước mọi truy vấn.

### Tình huống C: query có join hoặc subquery đến bảng liên quan

```java
List<AuditEvent> events = em.createQuery("""
    select a
    from AuditEvent a
    where exists (
        select p.id
        from Product p
        where p.id = a.productId
          and p.price > :min
    )
    """, AuditEvent.class)
    .setParameter("min", new BigDecimal("500.00"))
    .getResultList();
```

Dù entity kết quả là `AuditEvent`, query còn dùng bảng `products`. Nếu đang có pending change trên `products`, việc xét query spaces có thể cho thấy cần flush trước query.

**Không nên chỉ xem kiểu entity được trả về** để kết luận auto-flush có xảy ra hay không. Cần xét toàn bộ bảng/thực thể tham gia join, subquery và mapping.

### Tình huống D: pending action nằm trên bảng liên kết

Nếu ứng dụng thay đổi một collection many-to-many, Hibernate có thể cần cập nhật join table thay vì chỉ bảng entity gốc. Một query liên quan join table đó cũng có thể làm AUTO flush trở nên cần thiết.

Query spaces được xác định từ SQL/mapping, không đơn giản là tên class đã gọi setter.

### Có thể có flush nhưng không có UPDATE

Ngay cả khi truy vấn được đánh giá cần auto-flush, sau dirty checking Hibernate có thể nhận ra state không thay đổi đáng kể, hoặc không có pending SQL đối với bảng ấy. Quan sát “có/không có câu `UPDATE`” trong log không phải lúc nào cũng chứng minh toàn bộ hoạt động nội bộ của lần auto-flush.

## 8. Ví dụ hoàn chỉnh: flush do query trước commit

Ví dụ sau sử dụng `EntityManager` với **resource-local transaction**, không phải JTA:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

public void changePriceAndQuery(
        EntityManagerFactory emf,
        Long productId) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Product product = em.find(Product.class, productId);
        if (product == null) {
            throw new IllegalArgumentException("Unknown product");
        }

        product.changePrice(new BigDecimal("150.00"));

        // Chưa gọi em.flush().

        Long count = em.createQuery("""
            select count(p)
            from Product p
            where p.price >= :min
            """, Long.class)
            .setParameter("min", new BigDecimal("100.00"))
            .getSingleResult();

        System.out.println("Matching products: " + count);

        tx.commit();
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

Trong cấu hình `AUTO` thường gặp, Hibernate có thể thực hiện:

```sql
-- Trước SELECT count, khi pending update liên quan products:
UPDATE products SET price = ? WHERE id = ? AND version = ?;

-- Sau đó:
SELECT COUNT(*)
FROM products
WHERE price >= ?;

-- Cuối cùng:
COMMIT;
```

SQL chỉ là minh họa: Hibernate có thể cập nhật cả cột `version`, dùng alias/cú pháp khác và chọn thời điểm đồng bộ phụ thuộc mapping/version.

**Điểm chính:** câu `UPDATE` có thể xuất hiện **trước câu `SELECT`**, dù code chưa gọi explicit `flush()` và transaction vẫn chưa commit.

## 9. Chỉ có thay đổi trong bộ nhớ thì sao `EntityManager.find()`?

Một nguồn nhầm lẫn khác là:

```java
Product product = em.find(Product.class, 10L);
product.changePrice(new BigDecimal("120.00"));

Product same = em.find(Product.class, 10L);
System.out.println(same.getPrice()); // 120.00
```

Trong cùng persistence context, Hibernate thường trả về **chính managed instance đã có** theo identity map, không cần SELECT mới. Vì vậy, việc `same.getPrice()` thấy giá trị `120.00` **không chứng minh SQL UPDATE đã được gửi tới database**.

`EntityManager.find` trên entity đã managed, query JPQL dựa vào DB và native SQL là những đường truy xuất khác nhau. Khi kiểm tra thời điểm flush, không nên dùng `find` lần hai như bằng chứng duy nhất rằng DB đã nhận thay đổi.

Một phép thử sát hơn là theo dõi SQL hoặc chạy JPQL aggregate/filter có thể bị ảnh hưởng bởi pending changes trong một transaction.

## 10. Flush khi commit: con đường đồng bộ thông thường

Nếu ứng dụng chỉ tải và sửa entity, sau đó kết thúc transaction mà không gọi query:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();

Product product = em.find(Product.class, id);
product.changePrice(new BigDecimal("1000.00"));

// Không gọi query, không explicit flush.

tx.commit();
```

Ở `AUTO` hoặc `COMMIT` trong môi trường Hibernate/JPA thông thường, Hibernate đồng bộ thay đổi còn chờ như một phần của việc hoàn tất transaction trước khi commit được database xác nhận.

```text
begin transaction
    |
    v
find(Product)
    |
    v
changePrice(...)
    |
    | chưa cần UPDATE ngay
    v
commit()
    |
    +--> flush pending changes
    |       |
    |       +--> dirty checking
    |       +--> UPDATE products ...
    |
    +--> database COMMIT
    |
    v
transaction kết thúc
```

Không nên nói “Hibernate chỉ flush đúng lúc gọi commit”, vì **AUTO flush trước query** hoặc explicit flush có thể xảy ra từ trước. Nhưng **commit là một điểm đồng bộ tự nhiên** đối với những thay đổi managed còn chờ.

### Nếu không có thay đổi thực sự?

```java
Product product = em.find(Product.class, id);
String name = product.getName();

tx.commit();
```

Hibernate có thể đi qua bước flush/check nhưng không sinh `UPDATE` nào, vì không có thay đổi cần ghi. `commit` không đồng nghĩa luôn có SQL DML.

### Khi phiên transaction được quản lý bởi Spring

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PriceService {

    private final EntityManager em;

    public PriceService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        Product product = em.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Not found");
        }

        product.changePrice(price);
        // Không cần em.persist(product) hoặc em.flush() thủ công.
    }
}
```

Giả định đây là bean được Spring quản lý, lời gọi đi qua cơ chế transaction interception và cấu hình JPA/Hibernate phù hợp. Transaction manager sẽ quản lý việc commit; Hibernate đồng bộ những thay đổi managed theo chính sách flush đang có.

Nếu gọi phương thức từ chính object mà không đi qua proxy (self-invocation ở mô hình Spring AOP proxy thông thường), annotation `@Transactional` có thể không được áp dụng như mong đợi. Khi đó không thể suy luận về thời điểm flush/commit chỉ từ sự có mặt của annotation.

## 11. `FlushModeType.COMMIT`: query trước commit có thể thấy gì?

Với chế độ `COMMIT`:

```java
em.setFlushMode(FlushModeType.COMMIT);

Product product = em.find(Product.class, productId);
product.changePrice(new BigDecimal("999.00"));

Long count = em.createQuery("""
    select count(p)
    from Product p
    where p.price > :threshold
    """, Long.class)
    .setParameter("threshold", new BigDecimal("500.00"))
    .getSingleResult();
```

Hibernate thông thường có thể trì hoãn `UPDATE products` cho đến commit; query aggregate có thể đọc giá trị **chưa được cập nhật** ở database và trả kết quả không phản ánh thay đổi managed trong bộ nhớ.

Theo JPA, ảnh hưởng của các cập nhật chưa flush lên các query khi flush mode là `COMMIT` **không được bảo đảm theo cùng cách với `AUTO`**. Do đó, không nên viết logic nghiệp vụ giả định:

> “Dù đã chuyển sang COMMIT, mọi JPQL query trong transaction vẫn luôn thấy tất cả setter vừa gọi.”

### Khi nào cân nhắc COMMIT?

- Một workflow cần giảm các đợt flush giữa nhiều query, và **đã thiết kế rõ** việc query trung gian không phụ thuộc pending changes.
- Một tác vụ xử lý theo lô có kiểm soát thời điểm đồng bộ.
- Một cấu hình tích hợp đặc biệt mà transaction manager chịu trách nhiệm chính.

Không nên đổi `AUTO` sang `COMMIT` chỉ để giảm số SQL trong log khi chưa xét ý nghĩa query. Một phép kiểm tra tồn kho, số lượng đơn hàng, hạn mức hoặc ràng buộc nghiệp vụ có thể phụ thuộc pending changes và cho kết quả sai nếu chưa flush.

### Explicit flush khi query cần state mới nhất

Trong một giao dịch dùng `COMMIT` nhưng có query bắt buộc thấy thay đổi đã gửi xuống DB:

```java
product.changePrice(new BigDecimal("999.00"));

em.flush(); // Chủ động đồng bộ SQL.

Long count = em.createQuery("""
    select count(p)
    from Product p
    where p.price > :threshold
    """, Long.class)
    .setParameter("threshold", new BigDecimal("500.00"))
    .getSingleResult();
```

Lời gọi explicit flush làm rõ dependency, nhưng có chi phí. Hãy cân nhắc có thực sự cần query database ngay lúc đó hay có thể tính trong bộ nhớ một cách đúng đắn.

## 12. `FlushMode.MANUAL`: kiểm soát tối đa, trách nhiệm cao

Hibernate native hỗ trợ `FlushMode.MANUAL`:

```java
import org.hibernate.FlushMode;
import org.hibernate.Session;

Session session = em.unwrap(Session.class);
session.setHibernateFlushMode(FlushMode.MANUAL);
```

Với chế độ này, Hibernate thông thường chỉ đồng bộ các thay đổi khi code gọi `flush()` rõ ràng. **Không được giả định commit tự flush mọi managed changes**.

Ví dụ nguy hiểm:

```java
session.setHibernateFlushMode(FlushMode.MANUAL);

Product product = session.find(Product.class, id);
product.changePrice(new BigDecimal("777.00"));

transaction.commit();
// Nếu không có explicit flush phù hợp,
// UPDATE có thể không được thực thi.
```

Lỗi ở đây không nhất thiết làm exception xuất hiện: transaction có thể commit mà **không ghi cập nhật** đang nằm trong persistence context.

### Dùng MANUAL trong tình huống nào?

Nó có thể hữu ích khi infrastructure hiểu và kiểm soát vòng đời Session, ví dụ một số transaction read-only hoặc một quy trình xử lý đặc thù. Nhưng dùng ở tầng business thông thường có nhiều bẫy:

- Quên explicit `flush` trước commit.
- Query đọc dữ liệu cũ vì pending changes chưa được đồng bộ.
- Một đoạn code thứ ba thay đổi Session flush mode mà không trả lại.
- Các helper hoặc framework giả định chế độ `AUTO`.

Nếu phải thay đổi flush mode tạm thời, lưu chế độ cũ và khôi phục trong `finally` theo logic phù hợp:

```java
FlushMode previous = session.getHibernateFlushMode();

try {
    session.setHibernateFlushMode(FlushMode.MANUAL);
    // Thực hiện công việc được kiểm soát chặt.
} finally {
    session.setHibernateFlushMode(previous);
}
```

Trong ứng dụng dùng transaction manager, cân nhắc để framework quản lý flush mode thay vì tự thay đổi từ repository.

## 13. `FlushMode.ALWAYS`: vì sao không phải lựa chọn mặc định?

Ở Hibernate native, `ALWAYS` yêu cầu flush trước mỗi query theo chính sách của Hibernate. Nó có thể đơn giản hóa một số giả định về dữ liệu đã đồng bộ trước truy vấn nhưng thường tăng chi phí:

```text
set A
SELECT ...
set B
SELECT ...
set C
SELECT ...
```

Mỗi `SELECT` có thể trở thành điểm phải cân nhắc dirty checking và đồng bộ, làm giảm khả năng gom SQL và tăng round-trip.

Với phần lớn ứng dụng, `AUTO` là điểm cân bằng tốt hơn: Hibernate chỉ flush trước query khi cần thiết theo thông tin mà ORM có.

Không nên chọn `ALWAYS` chỉ để đảm bảo mọi native query luôn nhìn thấy thay đổi nếu có thể kiểm soát query spaces hoặc explicit flush ở đúng nơi.

## 14. JPQL/HQL và native SQL có hành vi auto-flush khác nhau

Hibernate hiểu cấu trúc entity và bảng của JPQL/HQL, nên thường xác định được các **query spaces** liên quan.

Ví dụ JPQL:

```java
List<Product> products = em.createQuery("""
    select p
    from Product p
    where p.price > :min
    """, Product.class)
    .setParameter("min", new BigDecimal("100.00"))
    .getResultList();
```

Hibernate biết truy vấn tham gia mapping `Product` và những bảng liên quan; nó có thể so sánh với pending actions.

Native SQL lại là chuỗi SQL do ứng dụng đưa vào. Hibernate có thể không xác định đầy đủ mọi bảng ảnh hưởng, đặc biệt với stored procedure, view, CTE hoặc hàm database.

### 14.1. Native query qua `EntityManager`

Ví dụ:

```java
Object total = em.createNativeQuery("""
    SELECT COUNT(*) FROM products
    """).getSingleResult();
```

Trong các phiên bản Hibernate phổ biến, native query chạy qua `EntityManager` ở `AUTO` thường kích hoạt flush để bảo đảm các cập nhật liên quan được phản ánh, ngay cả khi Hibernate không phân tích chính xác toàn bộ SQL. **Hành vi chi tiết phải được đối chiếu với phiên bản Hibernate và API đang dùng**.

Không nên suy ra: “Vì query native không phải JPQL nên chắc chắn không flush”.

### 14.2. Native query qua Hibernate `Session`

API native `Session` có những khác biệt lịch sử và theo phiên bản về auto-flush đối với native SQL khi chưa khai báo bảng liên quan. Trong các cấu hình mà `Session` không auto-flush native query chưa được đồng bộ hóa, query có thể đọc trạng thái database cũ cho dù có pending updates.

Một cách diễn đạt rõ dependency là đăng ký entity/table mà native query liên quan với `NativeQuery`:

```java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = em.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery("""
    SELECT COUNT(*) FROM products
    """);

query.addSynchronizedEntityClass(Product.class);

Object count = query.getSingleResult();
```

Thông tin synchronization giúp Hibernate biết query native có liên quan đến bảng mapped bởi `Product`. Cơ chế và kết quả flush chính xác phụ thuộc native API và version đang dùng.

Khi query liên quan một bảng không map bởi entity, Hibernate còn có các API khai báo query space trực tiếp, ví dụ `addSynchronizedQuerySpace(...)` trong các phiên bản hỗ trợ. Cần đối chiếu tài liệu phiên bản trước khi sử dụng.

### 14.3. Tự flush trước native SQL khi cần chắc chắn

Nếu workflow bắt buộc native SQL đọc kết quả **sau khi tất cả pending changes liên quan đã được gửi xuống database**, có thể explicit flush:

```java
Product product = em.find(Product.class, id);
product.changePrice(new BigDecimal("300.00"));

em.flush();

Object count = em.createNativeQuery(
    "SELECT COUNT(*) FROM products WHERE price >= 300"
).getSingleResult();
```

Ở đây chủ ý được thể hiện rõ: cập nhật entity được đồng bộ trong transaction **trước** câu SQL native. Nhưng explicit flush có chi phí và không thay thế việc hiểu isolation, trigger, các transaction khác hoặc hành vi của DB.

**Tóm lại:** với native SQL, hãy phân biệt `EntityManager` và `Session`, API query cụ thể và khả năng khai báo synchronized query spaces. Không dùng một quy tắc tuyệt đối cho mọi Hibernate version.

## 15. Bulk JPQL update/delete và persistence context

JPQL bulk DML như `UPDATE Product p SET p.price = ...` là một trường hợp đặc biệt.

Ví dụ:

```java
int affected = em.createQuery("""
    update Product p
    set p.price = :newPrice
    where p.id = :id
    """)
    .setParameter("newPrice", new BigDecimal("500.00"))
    .setParameter("id", id)
    .executeUpdate();
```

Bulk DML được thực thi trực tiếp ở tầng database và **không đồng bộ từng entity managed trong persistence context như setter + dirty checking thông thường**.

Giả sử trước bulk update, `Product(id)` đã được load:

```java
Product managed = em.find(Product.class, id);
BigDecimal before = managed.getPrice();

em.createQuery("""
    update Product p set p.price = :price where p.id = :id
    """)
    .setParameter("price", new BigDecimal("500.00"))
    .setParameter("id", id)
    .executeUpdate();

// managed.getPrice() có thể vẫn giữ giá trị cũ.
```

Ở đây, cần phân biệt:

1. **Auto-flush trước khi thực thi bulk query:** Hibernate có thể cần đồng bộ pending changes có liên quan.
2. **Bulk update tự nó:** chạy trực tiếp trong DB, không sửa field của mọi managed entity đã được tải.
3. **State trong persistence context sau bulk update:** có thể stale và cần `clear()`/`refresh()`/thiết kế lại workflow.

Ví dụ nếu cần đọc lại:

```java
em.flush(); // Đồng bộ pending managed changes khi cần.
int affected = em.createQuery("""
    update Product p set p.price = :price where p.id = :id
    """)
    .setParameter("price", new BigDecimal("500.00"))
    .setParameter("id", id)
    .executeUpdate();

em.clear(); // Detach toàn bộ managed entities.

Product fresh = em.find(Product.class, id);
```

**Cảnh báo:** `clear()` có thể làm mất những thay đổi chưa flush ở các entity khác. Chỉ dùng khi đã xác định đúng boundary và những thay đổi cần thiết đã được đồng bộ.

Bulk update còn có semantics riêng với `@Version` và lifecycle callbacks; không tự thay thế toàn bộ dirty checking/optimistic locking của các update thông thường.

## 16. Flush với entity mới: `persist`, `SEQUENCE` và `IDENTITY`

Thời điểm SQL `INSERT` không phải lúc nào cũng giống nhau, bởi cách sinh identifier ảnh hưởng đến việc Hibernate có cần gửi SQL sớm hay không.

### 16.1. `SEQUENCE`: ID có thể có trước INSERT

```java
Product product = new Product(
    "Chuột không dây",
    new BigDecimal("350.00")
);

em.persist(product);

Long id = product.getId(); // Thường đã có khi dùng SEQUENCE.
```

Hibernate có thể lấy ID từ sequence hoặc một pool đã cấp phát, gán vào entity và **để INSERT chờ đến flush**.

```text
persist(Product)
    |
    +--> sinh ID từ sequence / pool
    |
    +--> lên lịch INSERT
                  |
                  v
             flush sau đó
                  |
                  v
           INSERT products
```

Nhờ biết ID trước, các INSERT có thể được gom vào JDBC batch khi điều kiện khác cho phép.

### 16.2. `IDENTITY`: có thể phải INSERT sớm để lấy ID

Nếu:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

database thường sinh ID trong quá trình INSERT. Hibernate thường cần thực thi `INSERT` để nhận generated key, thậm chí trước một đợt flush/commit thông thường.

Đây là **SQL xuất hiện sớm do chiến lược sinh ID**, không có nghĩa mọi pending update trong persistence context đều đã được flush hoặc transaction đã commit. Một số trường hợp Hibernate có delayed identity insertion, phụ thuộc version và trạng thái transaction.

Vì vậy, không nên kết luận “Hibernate luôn trì hoãn tất cả INSERT đến flush” hoặc “persist không bao giờ chạy SQL”.

### 16.3. Flush không phải JDBC batching

`hibernate.jdbc.batch_size` quyết định khả năng gom các statement JDBC tương thích; `flush` quyết định lúc ORM đồng bộ pending actions. Hai cơ chế liên quan nhưng không đồng nhất.

Flush quá thường xuyên, ví dụ sau mỗi `persist`, thường hạn chế cơ hội gom batch:

```java
for (Product product : products) {
    em.persist(product);
    em.flush(); // Không nên làm mặc định cho từng hàng.
}
```

Một cách thường dùng trong batch processing là flush/clear theo nhóm; xem phần tiếp theo.

## 17. Ảnh hưởng của auto-flush đến hiệu năng

Giả sử transaction tạo hàng trăm sản phẩm, nhưng sau mỗi vài lần persist lại chạy query liên quan bảng `products`.

```java
for (int i = 0; i < products.size(); i++) {
    em.persist(products.get(i));

    if (i % 10 == 0) {
        em.createQuery("""
            select count(p) from Product p
            """, Long.class).getSingleResult();
    }
}
```

Nếu query đụng bảng `products` và Hibernate phải flush pending inserts trước nó, transaction có thể bị chia thành nhiều đợt đồng bộ sớm. Điều này làm tăng số lần dirty checking/SQL execution và có thể làm batch nhỏ hơn.

### 17.1. Chỉ query khi thật sự cần

Nếu query chỉ để hiển thị số object vừa tạo trong vòng lặp, ứng dụng có thể tự đếm trong Java mà không cần truy vấn database liên tục.

Tuy nhiên, nếu query nhằm kiểm tra constraint trên DB, tính số lượng của toàn hệ thống hoặc thông tin phụ thuộc các transaction khác, không thể mặc định thay bằng một biến đếm local. Phải phân biệt **mục đích nghiệp vụ** trước khi tối ưu.

### 17.2. Flush/clear theo lô

Ví dụ:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    int batch = 50;

    for (int i = 0; i < products.size(); i++) {
        em.persist(products.get(i));

        if ((i + 1) % batch == 0) {
            em.flush();
            em.clear();
        }
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Ý nghĩa:

- `flush()` gửi SQL của các entity đang chờ.
- `clear()` tách entity khỏi persistence context để giới hạn bộ nhớ.
- `commit()` đồng bộ nốt nhóm cuối còn chờ rồi xác nhận **cùng một transaction**.
- Việc flush các nhóm trước đó **không tạo commit riêng**. Nếu transaction rollback, các SQL đã flush thường vẫn bị rollback theo semantics của DB.

Cần để ý quan hệ cascade, foreign key và entity bị detach sau `clear`: code không còn được dựa vào dirty checking của các instance cũ nếu chưa đưa chúng vào context phù hợp.

### 17.3. Auto-flush có thể tốn chi phí ngay cả khi query chỉ đọc

Một query `SELECT` có thể buộc ORM quét/kiểm tra dirty state và sinh DML trước khi đọc. Vì vậy, nếu một request xen kẽ cập nhật nhiều entity và truy vấn aggregate, tổng SQL/round-trip có thể lớn hơn số lệnh xuất hiện trực tiếp trong business code.

Nhưng giải pháp **không phải tắt flush toàn cục**. Hãy xem lại ranh giới transaction, thời điểm query, cách gom batch và những thay đổi query thực sự cần nhìn thấy.

## 18. Flush và kiểm tra ràng buộc database

Khi Hibernate flush, database có thể kiểm tra các ràng buộc:

- `NOT NULL`;
- khóa ngoại `FOREIGN KEY`;
- `UNIQUE`;
- `CHECK`;
- ràng buộc version hoặc row count trong optimistic locking;
- trigger và một số logic database.

Ví dụ:

```java
Product product = new Product(null, new BigDecimal("100.00"));
em.persist(product);

em.flush(); // Có thể báo lỗi NOT NULL ngay ở đây.
```

Nếu không có explicit flush và không có query bắt buộc đồng bộ, lỗi có thể chỉ xuất hiện khi commit. Điều này dẫn tới nhầm lẫn:

> “Lỗi xảy ra ở commit, nên commit làm sai dữ liệu.”

Thực tế, nguồn lỗi có thể là một entity invalid đã được persist từ trước; commit chỉ là thời điểm Hibernate buộc phải gửi SQL.

### Khi cần kiểm tra lỗi sớm

Một service có thể explicit flush để buộc DB kiểm tra các ràng buộc chưa kiểm tra ở thời điểm persist:

```java
@Transactional
public Long createProduct(String name, BigDecimal price) {
    Product product = new Product(name, price);
    em.persist(product);

    em.flush(); // Có thể phát hiện lỗi SQL sớm hơn commit.

    return product.getId();
}
```

Nhưng `flush()` **không thay thế commit**; một số constraint được database thiết kế để kiểm tra **trì hoãn đến commit** (*deferrable constraints*), và transaction vẫn có thể rollback sau flush vì một lỗi khác.

Vì vậy, không được nói “flush thành công tức dữ liệu chắc chắn hợp lệ và sẽ commit”. Nó chỉ xác nhận các thao tác đã được đồng bộ đến bước đó mà không gặp lỗi không thể tiếp tục trong hoàn cảnh ấy.

### Vi phạm `UNIQUE` do thứ tự thao tác

Giả sử code xóa một hàng đang giữ unique value rồi insert hàng mới dùng cùng unique value trong cùng transaction. Hibernate Action Queue không bắt buộc phát SQL theo thứ tự lời gọi Java. Nếu `INSERT` chạy trước `DELETE`, database có thể báo unique constraint dù chương trình “đã remove hàng cũ trước”.

Trong trường hợp đặc biệt, một explicit flush sau thao tác xóa có thể giúp đảm bảo SQL delete xảy ra trước insert:

```java
em.remove(oldEntity);
em.flush(); // Đảm bảo delete đã được đồng bộ.

em.persist(newEntity);
```

Tuy nhiên, đây là một quyết định giao dịch có ảnh hưởng rõ rệt, không phải quy tắc cần áp cho mọi thao tác thay thế dữ liệu. Có thể tốt hơn nếu cập nhật entity hiện hữu hoặc thiết kế unique key/migration đúng nghiệp vụ.

## 19. Flush và optimistic locking

Entity có `@Version`:

```java
@Version
private Long version;
```

Khi dirty entity được flush, Hibernate có thể phát SQL tương đương:

```sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu một transaction khác đã thay đổi version khiến câu UPDATE không còn khớp hàng, Hibernate có thể phát hiện optimistic locking conflict ở **flush** hoặc cuối transaction — tùy thời điểm SQL thực thi.

Ví dụ:

```java
Product product = em.find(Product.class, id);

product.changePrice(new BigDecimal("120.00"));

// Không thấy exception ngay tại setter.
em.flush(); // Có thể phát hiện stale version ở đây.
```

Đừng nhầm rằng `@Version` chỉ có hiệu lực lúc commit. Lỗi thường bộc lộ khi SQL update/row count được kiểm tra; flush có thể khiến thời điểm ấy đến sớm hơn.

### Flush không tránh được mọi xung đột đồng thời

Flush là cơ chế đồng bộ SQL, **không phải khóa toàn bộ dữ liệu nghiệp vụ**. Nếu cần bảo vệ invariant xuyên nhiều hàng hoặc chống race condition, vẫn phải thiết kế transaction isolation, pessimistic/optimistic locking hoặc constraint database thích hợp.

## 20. Flush và trạng thái transaction sau khi lỗi

Nếu `flush()` thất bại vì một lỗi JDBC, constraint hoặc persistence nghiêm trọng, **không nên tiếp tục sử dụng cùng Session/EntityManager như thể nó vẫn còn sạch**.

Ví dụ không nên làm:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    // Sai ý tưởng: sửa một field rồi tiếp tục commit như bình thường,
    // không xét trạng thái transaction / persistence context.
    product.changePrice(new BigDecimal("1.00"));
}
```

Hướng thông thường trong transaction nghiệp vụ:

1. Ghi nhận exception để trả thông tin lỗi phù hợp.
2. Đánh dấu rollback hoặc rollback transaction theo mô hình quản lý hiện tại.
3. Không giả định Action Queue và managed state còn ở một trạng thái đáng tin cậy để thử lại.
4. Khi cần retry, thực hiện lại trong một unit of work và persistence context mới.

Trong môi trường Spring, exception từ JPA/Hibernate có thể được dịch sang lớp exception của Spring. Một transaction đã bị đánh dấu rollback-only có thể khiến commit thất bại dù code tầng trên đã catch một exception và tiếp tục.

Không nên tự retry một câu flush trên context vừa gặp lỗi mà không hiểu trạng thái session/transaction.

## 21. Transaction isolation: ai nhìn thấy dữ liệu sau flush?

Giả sử T1 cập nhật giá sản phẩm rồi flush, nhưng chưa commit:

```text
Transaction T1                       Transaction T2
---------------------------------    -----------------------------
BEGIN
UPDATE products SET price = 120
-- do Hibernate flush
                                     SELECT price FROM products
-- Chưa COMMIT                      -- Giá trị thấy được phụ thuộc
                                     -- isolation và lock behavior
COMMIT
```

Thông thường, với isolation như `READ COMMITTED`, T2 chưa thấy thay đổi chưa commit của T1. Nhưng query trong **chính transaction T1** thường có thể đọc lại các thay đổi do nó đã ghi.

Vì vậy:

- **Flush** giúp SQL của transaction hiện tại được gửi tới database.
- **Commit** xác nhận transaction; từ đó các transaction khác có thể quan sát thay đổi theo isolation.
- **Isolation** quyết định cách các transaction nhìn nhau, không được thay bằng flush mode.
- **Flush mode** quyết định khi nào ORM đồng bộ thay đổi managed để phục vụ query/commit.

Chỉ thay flush mode không thể giải quyết dirty read, phantom read hoặc mọi vấn đề concurrency.

## 22. Read-only transaction và flush mode

Trong Spring/Hibernate, một transaction được đánh dấu:

```java
@Transactional(readOnly = true)
public List<Product> listProducts() {
    return em.createQuery(
        "select p from Product p",
        Product.class
    ).getResultList();
}
```

có thể được framework tối ưu bằng cấu hình read-only và/hoặc flush mode của Hibernate. Nhưng **`readOnly = true` không phải một bảo đảm an ninh rằng không SQL UPDATE nào có thể chạy trong mọi database và mọi cấu hình**.

Điều cần hiểu:

- Đây thường là **gợi ý cho transaction manager/provider** để tối ưu đường đọc.
- Một số integration với Hibernate có thể dùng `MANUAL` hoặc cơ chế read-only session.
- Nếu code vẫn sửa managed entity trong read-only transaction, thay đổi ấy **có thể không được flush** như một transaction ghi thông thường.
- Hành vi chính xác phải xét Spring version, transaction manager và cách EntityManager/Session được quản lý.

Không dùng read-only transaction cho workflow cần ghi dữ liệu rồi mong Hibernate tự đồng bộ lúc commit.

### `@Immutable` và managed entity read-only

Nếu một entity được đánh dấu bất biến bằng cơ chế Hibernate như `@Immutable`, Hibernate có thể không dirty-check/sinh update cho trạng thái entity theo cách thông thường. Đây là đặc điểm của mapping, **không phải lỗi do `AUTO` không flush**.

Khi thấy setter không tạo `UPDATE`, hãy xem cả lifecycle và mapping read-only/immutable chứ không chỉ flush mode.

## 23. Truy vấn bên ngoài ORM và việc đồng bộ trạng thái

Một hệ thống có thể đồng thời dùng Hibernate và JDBC trực tiếp:

```text
EntityManager / Hibernate Session
    |
    | pending UPDATE products
    |
    +--> JDBC query trực tiếp trên cùng/different connection
```

Nếu JDBC code chạy trước khi Hibernate flush, SQL của JDBC có thể không thấy state mới chỉ nằm trong persistence context Java. Nếu JDBC dùng connection/transaction khác, ngay cả sau flush còn có vấn đề isolation và commit.

Không nên giả định:

> “Hibernate đã đổi object nên mọi SQL JDBC trong ứng dụng đều lập tức đọc được giá trị mới.”

Khi pha trộn ORM với JDBC, cần xác định:

- JDBC có tham gia **cùng transaction** không?
- Có dùng cùng connection do transaction manager quản lý không?
- ORM đã flush các thay đổi cần thiết chưa?
- Query có đọc table/state phù hợp không?
- Thao tác JDBC trực tiếp có làm persistence context của Hibernate trở nên stale không?

Nếu trực tiếp sửa dữ liệu bằng JDBC, Hibernate không tự cập nhật mọi managed entity đã load. Có thể cần `refresh`/`clear` hoặc tách workflow để tránh cache bẩn.

## 24. Một số câu hỏi hiểu nhầm thường gặp

### “AUTO nghĩa là flush trước mọi SELECT?”

Không. Với JPQL/HQL, Hibernate thường kiểm tra **query spaces** và pending actions. Query đọc bảng không liên quan có thể chạy mà không cần flush cập nhật khác đang chờ. Native SQL có những quy tắc riêng theo API/version.

### “Không gọi flush thì Hibernate sẽ không bao giờ chạy UPDATE?”

Không. Commit thường flush thay đổi đang chờ ở chế độ thông dụng. AUTO query có liên quan cũng có thể kích hoạt flush.

### “Flush rồi thì dữ liệu đã commit?”

Không. SQL có thể được thực thi trong transaction vẫn còn mở. Rollback có thể hủy thay đổi đã flush.

### “Vừa đổi entity và query thấy giá trị mới tức database đã UPDATE?”

Chưa chắc. Nếu query được đáp ứng qua persistence context, hoặc cách JPA bảo đảm query visibility khác, quan sát giá trị Java không tự chứng minh một SQL UPDATE đã chạy. Cần phân biệt identity map, JPQL/HQL và native SQL.

### “COMMIT flush mode cấm query thấy pending changes?”

Không phải cách diễn đạt chính xác. JPA không bảo đảm tác động của pending changes lên query ở chế độ COMMIT theo cùng cách với AUTO; một số query vẫn có thể thấy thay đổi tùy đường truy cập và implementation. Đừng dựa vào một kết quả ngẫu nhiên để xây invariant.

### “MANUAL cũng tự flush khi commit vì tên commit?”

Không nên giả định. Với Hibernate `MANUAL`, người dùng/infrastructure phải gọi explicit flush ở nơi cần thiết; pending changes có thể không được ghi.

### “Gọi flush sau mỗi persist sẽ an toàn và nhanh hơn?”

Không. Nó có thể làm batch nhỏ, tăng SQL/round-trip và tiêu tốn dirty checking; hơn nữa flush không phải commit hoặc validation nghiệp vụ đầy đủ.

### “Native SQL của Session và EntityManager có cùng auto-flush?”

Không nên khẳng định tuyệt đối. Cách xử lý native SQL và synchronization metadata có thể khác nhau theo API và phiên bản Hibernate.

### “Tắt auto-flush sẽ hết N+1?”

Không. N+1 liên quan cách fetch entity/association. Flush là cơ chế đồng bộ các thay đổi ghi; thay flush mode không phải giải pháp cho N+1.

### “Nếu flush lỗi, chỉ catch rồi thử commit tiếp?”

Nguy hiểm. Persistence context và transaction có thể ở trạng thái thất bại hoặc rollback-only. Thường nên rollback và tạo unit of work mới.

### “Hibernate chạy SQL đúng thứ tự code gọi persist/remove?”

Không có bảo đảm chung. Hibernate tổ chức actions theo dependency và quy tắc riêng, nên thứ tự statement khi flush có thể khác thứ tự lời gọi Java.

## 25. Bảng quyết định khi quan sát thời điểm flush

| Tình huống | Hành vi thường gặp với Hibernate ở AUTO | Lý do |
|---|---|---|
| Sửa managed Product, chưa query, chưa commit | Chưa cần `UPDATE` ngay | Trạng thái chờ dirty checking/flush |
| Sửa Product rồi JPQL query bảng `products` | Có thể flush trước query | Pending change có thể ảnh hưởng kết quả |
| Sửa Product rồi JPQL query bảng không liên quan | Có thể không flush trước query | Query spaces không giao nhau |
| Persist Product với SEQUENCE | Có thể cấp ID ngay, INSERT chờ flush | Generator biết ID trước insert |
| Persist Product với IDENTITY | Có thể INSERT sớm để lấy ID | Database sinh khóa trong insert |
| Gọi `em.flush()` trong transaction | Đồng bộ pending operations thích hợp | Explicit flush |
| Gọi commit ở AUTO/COMMIT | Đồng bộ pending changes còn chờ rồi commit | Transaction completion |
| Chạy JPQL ở COMMIT | Có thể không flush trước query | Chế độ trì hoãn query auto-flush |
| Chạy query ở Hibernate ALWAYS | Flush trước query theo chính sách | Flush mode native |
| Commit trong Hibernate MANUAL mà quên flush | Có thể không ghi pending changes | Chính sách chỉ flush thủ công |
| Native SQL qua EntityManager | Thường flush ở AUTO theo hành vi provider | Query không thể suy ra đầy đủ query spaces |
| Native SQL qua Session | Phụ thuộc version và đăng ký query spaces | Cần xem API và synchronization |
| Bulk JPQL UPDATE | Có thể auto-flush trước, sau đó database update trực tiếp | Bulk DML không cập nhật managed fields tự động |
| Transaction rollback sau flush | SQL đã gửi nhưng thay đổi chưa commit bị hủy | Flush khác commit |

Bảng mô tả hướng xử lý thường gặp. Với ứng dụng production, phải đối chiếu phiên bản Hibernate, transaction manager, dialect và SQL thực tế.

## 26. Ví dụ tổng hợp: update, query liên quan, query không liên quan, commit

Giả sử ứng dụng có hai entity:

- `Product` mapped vào bảng `products`.
- `AuditEvent` mapped vào bảng `audit_events`.

Workflow:

```java
@Transactional
public ProductReport updateAndReport(Long productId) {
    Product product = em.find(Product.class, productId);
    if (product == null) {
        throw new IllegalArgumentException("Product not found");
    }

    product.changePrice(new BigDecimal("250.00"));

    // Query chỉ đọc audit_events.
    Long auditCount = em.createQuery("""
        select count(a) from AuditEvent a
        """, Long.class)
        .getSingleResult();

    // Query đọc products, có thể buộc AUTO flush pending Product update.
    Long expensiveCount = em.createQuery("""
        select count(p)
        from Product p
        where p.price >= :minPrice
        """, Long.class)
        .setParameter("minPrice", new BigDecimal("200.00"))
        .getSingleResult();

    return new ProductReport(auditCount, expensiveCount);
    // Transaction manager commit sau khi method hoàn tất.
}
```

Ví dụ giả định `ProductReport` là DTO/record có constructor tương ứng, Spring thực sự quản lý transaction và flush mode là AUTO. Minh họa trình tự dự kiến:

```text
find Product
    |
changePrice(250.00)
    |
query AuditEvent count
    |  không overlap products; thường không cần flush Product
    v
query Product count
    |  overlap products
    +--> dirty checking / UPDATE Product nếu cần
    +--> SELECT count(Product)
    |
return DTO
    |
transaction commit
    |  flush những thay đổi còn chờ (nếu có)
    +--> COMMIT
```

Chính sự xuất hiện của **query Product sau khi sửa Product** làm `UPDATE` có thể xảy ra trước transaction commit. Nếu bỏ query ấy, `UPDATE` có thể được trì hoãn tới commit trong mô hình AUTO thông thường.

## 27. Cách quan sát hành vi thực tế khi học và debug

Để hiểu thời điểm flush, có thể thực hành trong một **database thử nghiệm**, dùng một transaction resource-local hoặc một service Spring `@Transactional` đã cấu hình đúng.

### Thử nghiệm 1: chỉ setter rồi commit

- Tải `Product`.
- Đổi giá.
- Không gọi query và không explicit flush.
- Quan sát SQL `UPDATE` xuất hiện khi transaction kết thúc.

### Thử nghiệm 2: setter rồi JPQL query cùng bảng

- Đổi giá một managed Product.
- Gọi query aggregate/filter trên `Product`.
- Quan sát SQL `UPDATE` có thể xuất hiện trước `SELECT`.

### Thử nghiệm 3: setter rồi JPQL query bảng khác

- Đổi Product.
- Query `AuditEvent` không tham gia bảng products.
- So sánh với thử nghiệm 2: Hibernate có thể chưa phải flush thay đổi Product trước query.

### Thử nghiệm 4: COMMIT flush mode

- Đặt `FlushModeType.COMMIT` trong transaction.
- Sửa Product rồi query aggregate.
- Phân biệt kết quả query với trạng thái managed Product trong bộ nhớ.
- Commit và quan sát SQL cập nhật.

### Thử nghiệm 5: explicit flush rồi rollback

- Sửa Product.
- Gọi `em.flush()`.
- Sau đó rollback.
- Tải lại Product bằng transaction/context mới và quan sát dữ liệu đã commit vẫn như cũ.

### Thử nghiệm 6: native query

- Thực hiện native query qua `EntityManager`.
- Thực hiện query tương đương qua `Session` hoặc `NativeQuery` đã khai báo synchronized entity.
- Quan sát khác biệt theo Hibernate version hiện tại, tránh suy luận từ một hướng gọi.

### Đọc SQL log đúng cách

- `SELECT`, `UPDATE` và `INSERT` có thể xuất hiện theo thứ tự không giống thứ tự câu lệnh Java.
- Với JDBC batching, log ở mức Hibernate SQL không luôn cho biết rõ số lần gửi batch vật lý.
- Nếu bật second-level cache hoặc entity đã được managed, số SQL có thể giảm.
- Không gọi `nextval` chỉ để “xem” sequence trong production; nó tiêu thụ giá trị sequence.
- Nếu flush đã được thực thi một lần, commit sau đó có thể không còn SQL DML để chạy; điều đó bình thường.
- Quan sát ngoại lệ constraint/optimistic lock ở flush hoặc commit để hiểu thời điểm SQL thực sự diễn ra.

## 28. Quy trình lựa chọn flush mode và explicit flush

Một cách tiếp cận thực tế:

1. **Bắt đầu với `AUTO`.** Đây là chế độ thông dụng và giữ hành vi query trong transaction dễ dự đoán.
2. **Đặt boundary transaction rõ ràng.** Service/Unit of Work nên sở hữu commit/rollback.
3. **Cho phép dirty checking làm việc với managed entities.** Không gọi `persist` hoặc `flush` sau mỗi setter.
4. **Nhận diện query cần thấy pending changes.** Nếu một query phụ thuộc state vừa sửa, giữ `AUTO` hoặc explicit flush trong tình huống đặc biệt.
5. **Đo chi phí nếu transaction có nhiều query xen kẽ write.** Cân nhắc gom thao tác hoặc đổi cấu trúc workflow trước khi thay flush mode.
6. **Phân biệt JPQL/HQL với native SQL.** Khi dùng native Query, xác định synchronization API và version.
7. **Chỉ dùng `COMMIT`/`MANUAL` khi hiểu rõ hệ quả.** Đặc biệt với MANUAL, thiết kế explicit flush trước những mốc cần ghi.
8. **Không dùng flush làm transaction/locking substitute.** Flush chưa commit, không bảo vệ mọi race condition.
9. **Xem xét bulk DML và JDBC trực tiếp.** Những thao tác ấy có thể khiến state trong persistence context stale.
10. **Khi flush thất bại, xử lý transaction thất bại đúng cách.** Không tiếp tục như thể persistence context vẫn nguyên vẹn.

## 29. Ghi nhớ

- **Dirty checking** theo dõi entity managed; Hibernate thường chỉ phát `UPDATE` khi flush và phát hiện thay đổi cần đồng bộ.
- **Flush** gửi SQL tới database trong transaction; **commit** xác nhận transaction; hai việc này không đồng nghĩa.
- Ở chế độ **`AUTO`**, Hibernate thường auto-flush **trước truy vấn có thể bị ảnh hưởng bởi pending changes**, không nhất thiết trước mọi JPQL/HQL query.
- Hibernate có thể xác định sự liên quan bằng **query spaces**: bảng mà query đọc so với bảng mà các thay đổi chưa flush cần ghi.
- Query bảng không liên quan có thể không flush; join/subquery liên quan bảng đã thay đổi vẫn có thể kích hoạt flush.
- **Khi commit**, Hibernate thông thường flush những thay đổi còn chờ; commit không bắt buộc tạo DML nếu đã flush từ trước.
- JPA có **`FlushModeType.AUTO`** và **`COMMIT`**; Hibernate native bổ sung các mức như **`ALWAYS`** và **`MANUAL`**.
- Với **`COMMIT`**, query trước commit không được bảo đảm thấy mọi pending changes như AUTO; với **`MANUAL`**, không nên chờ commit tự flush.
- Native SQL qua **`EntityManager`** và **`Session`** có thể khác hành vi auto-flush; cần xem API/version và synchronized query spaces.
- IDENTITY có thể làm `INSERT` xảy ra sớm để lấy generated key; SQL sớm không có nghĩa toàn bộ context đã flush hoặc transaction commit.
- Bulk JPQL DML và JDBC trực tiếp có thể làm **managed entities stale**, cần quản lý persistence context có chủ đích.
- Flush quá thường xuyên ảnh hưởng batching và hiệu năng; flush/clear theo lô phù hợp hơn cho nhiều tác vụ batch.
- Lỗi constraint hoặc optimistic locking có thể xuất hiện **ở flush**, không nhất thiết chỉ ở commit.
- Nếu flush thất bại, thường phải rollback và bắt đầu một unit of work mới.

**Kết luận:** Hibernate cho phép ứng dụng làm việc với một đồ thị entity nhất quán trong bộ nhớ và trì hoãn SQL cho đến khi cần thiết. Thời điểm flush trước query hoặc lúc commit là cơ chế cân bằng giữa **đúng kết quả truy vấn, hiệu năng và vòng đời transaction**. Muốn sử dụng nó chính xác, hãy luôn phân biệt **state managed trong persistence context**, **SQL đã đồng bộ nhưng chưa commit**, và **dữ liệu đã được database xác nhận sau commit**.
