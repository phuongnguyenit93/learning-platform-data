# Tránh gọi flush hoặc clear theo thói quen khi chưa rõ mục đích

Trong Hibernate, một lỗi thiết kế phổ biến là thêm `entityManager.flush()` ngay sau mỗi lệnh `persist()`, `merge()` hoặc setter; hoặc gọi `entityManager.clear()` sau mọi truy vấn vì cho rằng như vậy “dọn cache cho sạch”. Hai thao tác này **không sai tự thân**. Chúng chỉ trở nên có hại khi người lập trình không xác định được **mục đích, ranh giới transaction, trạng thái của entity và hậu quả đối với những thay đổi đang chờ**.

**`flush()`** yêu cầu Hibernate đồng bộ các thay đổi từ persistence context xuống database bằng các câu SQL cần thiết, nhưng **không commit transaction**. **`clear()`** làm tất cả entities trong persistence context trở thành **detached** và giải phóng thông tin quản lý tương ứng; nó **không tự flush trước** và có thể khiến các thay đổi chưa được đồng bộ không còn được ghi. Cả hai can thiệp vào cơ chế **dirty checking** và **transactional write-behind** mà Hibernate vốn đã tự điều phối.

Một đoạn code đúng thường ngắn hơn:

~~~java
@Transactional
public void changePrice(long productId, BigDecimal newPrice) {
    Product product = entityManager.find(Product.class, productId);
    if (product == null) {
        throw new IllegalArgumentException("Product not found");
    }
    product.changePrice(newPrice); // managed entity được dirty checking
    // Không cần flush() hoặc clear() theo thói quen.
}
~~~

Ở cuối transaction, transaction manager/Hibernate thực hiện việc flush thích hợp và commit. Đó là cách dùng cơ bản nên hiểu trước khi tối ưu hoặc thêm explicit flush/clear.

> **Phạm vi:** Ví dụ dùng `jakarta.persistence` và Hibernate ORM 6.x; với Hibernate 5, import thường là `javax.persistence`. Các trường hợp Spring được ghi rõ là Spring-managed, không phải JPA bắt buộc. Chi tiết Hibernate flush trước query, SQL batch và thời điểm cấp khóa sinh tự động phụ thuộc provider version, generator, flush mode, query API và DB dialect. Câu SQL trong bài chỉ minh họa semantics, không phải dạng SQL duy nhất.

## 1. Năm thuật ngữ cần tách bạch

| Khái niệm | Ý nghĩa | Không có nghĩa |
|---|---|---|
| **Persistence context** | Tập entity managed, identity map, loaded state và metadata dirty/collection. | Không phải kho cache dùng chung vĩnh viễn giữa mọi session. |
| **Dirty checking** | Xác định state managed đã thay đổi so với trạng thái nền hoặc metadata dirty. | Không đồng nghĩa gửi UPDATE ngay sau mỗi setter. |
| **Flush** | Đồng bộ những thay đổi chờ của context thành SQL phù hợp trong transaction. | Không xác nhận commit, không đóng session, không detach entities. |
| **Clear** | Bỏ quản lý **tất cả** entity trong context; những object được giữ ở Java trở thành detached. | Không flush, không rollback, không xóa row DB, không xóa cache cấp hai. |
| **Commit** | Xác nhận transaction database theo semantics của DB/transaction manager. | Không nhất thiết chỉ thực hiện một SQL hoặc tự biến Java object thành detached ngay lúc đó. |

Một cách đọc nhanh:

~~~text
find() / persist() / changePrice()
               |
               v
       Persistence Context
      (managed entity state)
               |
         Dirty Checking
               |
           flush()
               |
               v
       JDBC INSERT/UPDATE/DELETE
               |
          commit()
               |
               v
      DB transaction confirmed

clear()  --X--> managed state
           (detach, không tự lưu)
~~~

Nếu entity vẫn managed, Hibernate có đủ thông tin để theo dõi nó. Gọi `clear()` là chủ động phá bỏ quan hệ quản lý này. Gọi `flush()` là chủ động đặt một điểm đồng bộ SQL. Cả hai đều nên xuất phát từ yêu cầu cụ thể.

## 2. Mô hình ví dụ dùng xuyên suốt

Giả sử hệ thống quản lý hàng hóa có bảng:

~~~sql
CREATE SEQUENCE product_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(15,2) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
~~~

Entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "product")
@SequenceGenerator(
    name = "product_gen",
    sequenceName = "product_seq",
    allocationSize = 1
)
public class Product {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_gen"
    )
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 80)
    private String sku;

    @Column(name = "display_name", nullable = false, length = 200)
    private String displayName;

    @Column(name = "unit_price", nullable = false, precision = 15, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "active", nullable = false)
    private boolean active = true;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Product() {}

    public Product(String sku, String displayName, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.displayName = Objects.requireNonNull(displayName);
        changePrice(price);
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public BigDecimal getUnitPrice() { return unitPrice; }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice);
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }
        unitPrice = newPrice;
    }

    public void rename(String name) {
        displayName = Objects.requireNonNull(name);
    }

    public void deactivate() { active = false; }
}
~~~

`@Version` cung cấp optimistic locking: ở lần update entity thích hợp, Hibernate có thể sử dụng version đã load để phát hiện có transaction khác ghi đè. Trong bài, việc có `@Version` giúp giải thích vì sao một lỗi constraint hoặc optimistic locking có thể xuất hiện tại flush/commit, nhưng nó không thay đổi ý nghĩa của `flush()` và `clear()`.

## 3. Kịch bản cơ bản: chỉ sửa managed entity, không gọi thêm gì

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product product = entityManager.find(Product.class, 42L);
if (product == null) {
    tx.rollback();
    throw new IllegalArgumentException("Product not found");
}

product.changePrice(new BigDecimal("120.00"));
tx.commit();
~~~

Giả định `EntityManager` được ứng dụng quản lý và dùng transaction `RESOURCE_LOCAL`. Với managed object, chuỗi logic thường là:

1. `find()` trả entity managed (từ persistence context, cache thích hợp hoặc SQL).
2. `changePrice()` thay đổi giá trị Java; Hibernate có thể giữ loaded-state snapshot và thông tin dirty.
3. Khi transaction commit, Hibernate flush nếu cần, phát hiện price đã thay đổi và gửi SQL update.
4. DB commit transaction.

SQL minh họa:

~~~sql
SELECT id, sku, display_name, unit_price, active, version
FROM product
WHERE id = 42;

UPDATE product
SET unit_price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Lệnh update có thể chứa thêm các cột tùy `@DynamicUpdate`, metadata và SQL shape. Điểm cần nhớ: **không có lời gọi `update()` hoặc `flush()` của ứng dụng vẫn có thể ghi thay đổi đúng**.

### Vì sao không cần flush ngay sau setter?

Vì Hibernate không thiết kế để mọi setter = một SQL update. Nó gom state cuối trong context rồi đồng bộ ở flush boundary. Nếu cùng entity bị đổi 3 lần trong transaction:

~~~java
product.changePrice(new BigDecimal("110.00"));
product.rename("New Product Name");
product.changePrice(new BigDecimal("120.00"));
~~~

Hibernate thường chỉ cần cập nhật **state cuối cùng** ở flush, không phải ba lần update tương ứng từng dòng Java. Gọi flush sau từng setter có thể làm mất cơ hội gộp thay đổi và tăng overhead.

## 4. `flush()` thực sự làm gì?

`entityManager.flush()` yêu cầu đồng bộ trạng thái persistence context với database. Theo mapping và pending operations, Hibernate có thể:

- Lấy loaded/current state và xác định dirty fields của managed entities.
- Lập/xử lý các insert/update/delete actions trong Hibernate ActionQueue.
- Ghi thay đổi association/collection/join table khi cần.
- Thực hiện optimistic-locking checks và để database kiểm tra một số constraint ngay lúc SQL chạy.
- Phát JDBC statements, có thể theo batch nếu thích hợp.
- Cập nhật thông tin quản lý nội bộ sau khi flush thành công.

Ví dụ:

~~~java
tx.begin();
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("120.00"));

entityManager.flush();   // Có thể phát UPDATE tại đây.

// Entity vẫn managed; transaction vẫn đang mở.
product.rename("Updated Name");

tx.commit();             // Có thể cần flush thêm cho tên mới rồi commit.
~~~

Một explicit flush **không đóng cửa** khả năng phát sinh SQL tiếp theo. Nếu code tiếp tục thay đổi managed entities sau flush, một flush khác có thể cần diễn ra trước commit.

### Flush không phải “đồng bộ hết mọi thứ về phiên bản mới nhất”

Flush chủ yếu có hướng **Java persistence context → database**. Nó không tự kéo dữ liệu mới nhất từ database vào tất cả objects. Để lấy lại state DB cho entity managed khi phù hợp, dùng `refresh()`; để bỏ state managed, dùng `clear()`/`detach()`; mỗi API có hậu quả khác.

### Flush có bắt buộc chạy SQL?

Không. Nếu không có pending changes cần đồng bộ, explicit flush có thể không gửi update/insert/delete nào. Dù vậy, nó vẫn có thể đi qua công việc kiểm tra và lifecycle hooks cần thiết; không nên thêm nó như một “câu thần chú an toàn” rồi mặc định không có chi phí.

## 5. Flush khác commit: ví dụ rollback sau flush

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("999.00"));

entityManager.flush(); // SQL UPDATE có thể đã chạy.
tx.rollback();          // UPDATE bị hủy theo transaction DB.
~~~

Sau rollback, Java object `product` có thể vẫn đang giữ giá `999.00`, nhưng row trong database không được commit giá đó. Không được lấy state của object sau rollback làm bằng chứng DB đã lưu dữ liệu.

~~~text
Java state:  999.00
       |
     FLUSH
       |
DB transaction: UPDATE price=999.00 (chưa commit)
       |
    ROLLBACK
       |
Committed DB state: giữ giá cũ
~~~

Do đó, nếu cần đảm bảo transaction đã hoàn tất, điều kiện phải dựa vào **commit outcome**, không phải “flush không ném exception”. Lỗi vẫn có thể xuất hiện khi commit, ví dụ deferred constraint, deadlock hoặc mất kết nối khiến kết quả commit không chắc chắn.

### Transaction atomicity không biến flush thành savepoint

Gọi `flush()` rồi sau đó tiếp tục thực hiện các thao tác khác không có nghĩa phần trước đã được commit “riêng”. Muốn tách giao dịch phải thiết kế transaction boundary phù hợp. Flush không tự tạo một đơn vị commit con, cũng không bảo đảm có thể phục hồi riêng phần sau bằng cách “undo flush”.

## 6. `clear()` thực sự làm gì?

`entityManager.clear()` làm persistence context không còn quản lý những entities trước đó. Các Java references vẫn có thể tồn tại, nhưng những objects ấy trở thành detached đối với context hiện tại.

~~~java
Product product = entityManager.find(Product.class, 42L);
System.out.println(entityManager.contains(product)); // true

entityManager.clear();

System.out.println(entityManager.contains(product)); // false
~~~

Những thông tin quản lý liên quan entity/collection được giải phóng hoặc tách khỏi context. Nếu sau clear bạn gọi `find(Product.class, 42L)`, Hibernate có thể trả một Java instance khác được load lại từ DB/cache, chứ không tự biến `product` trước đó thành managed.

### Clear không phải thao tác “xóa dữ liệu”

~~~java
entityManager.clear();
~~~

không dịch thành:

~~~sql
DELETE FROM product;
~~~

Nó cũng không mặc định xóa second-level cache hay query cache. Nó chỉ tác động đến **persistence context hiện tại**. Vì vậy tên `clear()` dễ gây hiểu nhầm nếu không nắm rõ nó “clear cái gì”.

### Clear khác close

`clear()` giữ EntityManager/Session có thể tiếp tục dùng; `close()` kết thúc EntityManager/Session application-managed theo semantics tương ứng. Trong Spring/JTA, không tự gọi close trên một context do framework sở hữu.

## 7. Rủi ro lớn nhất: `clear()` trước `flush()` làm mất thay đổi

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("130.00"));

entityManager.clear(); // Tách entity; thay đổi chưa flush có thể bị bỏ.
tx.commit();
~~~

Giả định không có flush tự động trước clear. `product` đã đổi giá trong Java, nhưng vì entity bị detached và context không còn quản lý pending dirty state ấy, commit có thể không phát `UPDATE`. Người dùng sẽ thấy “setter chạy thành công, transaction commit không lỗi, nhưng DB không thay đổi”.

~~~text
Before:
  managed Product/42, DB price=100, Java price=100

Set price:
  managed Product/42, DB price=100, Java price=130

clear():
  detached Product/42, DB price=100, Java price=130

commit:
  không còn pending dirty update của Product/42 để flush
~~~

### Quy tắc thực tế

**Nếu cần giữ những thay đổi managed đang chờ trước khi clear, phải có một ranh giới đồng bộ phù hợp** — thường là `flush()` thành công trong transaction rồi mới `clear()`. Nhưng đừng biến nguyên tắc ấy thành “luôn gọi flush + clear sau mọi thao tác”: ở luồng CRUD bình thường, **không cần clear** nên cũng không cần cặp thao tác này.

### Cẩn thận với entity mới đã `persist()`

~~~java
tx.begin();
Product newProduct = new Product(
    "SKU-NEW", "New Product", new BigDecimal("10.00")
);
entityManager.persist(newProduct);
entityManager.clear();
tx.commit();
~~~

Với generator `SEQUENCE`, Hibernate có thể đã cấp ID trước khi INSERT. Nhưng nếu insert còn nằm trong pending actions chưa flush, clear có thể bỏ thao tác pending. **`newProduct.getId() != null` không bảo đảm row đã insert hoặc commit**. Với `IDENTITY`, insert có thể diễn ra sớm hơn để nhận generated key, nên outcome quan sát có thể khác; đừng dựa vào một trường hợp mà suy ra clear là an toàn.

## 8. Một bảng so sánh các API dễ nhầm

| API | Gửi SQL pending? | Entity còn managed sau lời gọi? | Mục tiêu |
|---|---|---|---|
| `flush()` | Có thể, nếu có thay đổi | **Có** | Đồng bộ pending changes với DB trong transaction. |
| `clear()` | **Không tự động** | **Không**, toàn bộ bị detach | Bỏ mọi managed state của context. |
| `detach(entity)` | Không tự động | Entity chỉ định không còn managed | Tách một entity; có thể cascade DETACH theo mapping. |
| `refresh(entity)` | Đọc lại state DB theo semantics provider | **Có** | Thay state managed bằng dữ liệu được tải lại. |
| `merge(detached)` | Có thể dẫn đến SQL khi flush | **Managed instance được trả về** | Copy state detached vào managed instance. |
| `remove(managed)` | Lập pending deletion, SQL khi flush thích hợp | Entity bị đánh dấu removed | Xóa entity theo lifecycle/transaction. |
| `commit()` | Thường liên quan flush trước/tại commit | Tùy scope/context ownership | Xác nhận transaction. |
| `close()` | Không thay thế commit | Context kết thúc | Giải phóng tài nguyên/đóng application-managed context. |

**Thường gặp nhất:** gọi `flush()` thay cho `commit()`, hoặc gọi `clear()` thay cho `refresh()`. Hai nhầm lẫn này có thể dẫn đến dữ liệu chưa commit hoặc thay đổi chưa flush bị bỏ qua.

## 9. Hibernate có thể flush tự động: hiểu `AUTO` trước

JPA có `FlushModeType.AUTO` và `FlushModeType.COMMIT`; Hibernate native còn các flush modes khác theo API/phiên bản. Với `AUTO`, provider phải bảo đảm những query cần nhìn các thay đổi đang chờ được xử lý nhất quán theo semantics JPA. Hibernate thường đánh giá sự chồng lấn giữa **tables/query spaces** liên quan query và pending entity actions để quyết định có flush trước query hay không.

~~~java
tx.begin();

Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("140.00"));

Long count = entityManager.createQuery(
    """
    select count(x)
    from Product x
    where x.unitPrice >= :minimum
    """,
    Long.class
).setParameter("minimum", new BigDecimal("120.00"))
 .getSingleResult();

tx.commit();
~~~

Query đọc `Product`, nơi có pending update. Trong chế độ thích hợp, Hibernate có thể flush trước SELECT count để kết quả phản ánh state cần thiết trong transaction.

### Không phải mọi query đều flush

Giả sử trong một mapping khác, pending update chỉ ảnh hưởng `product` còn query chỉ đọc `country_reference`:

~~~java
entityManager.createQuery(
    "select c from CountryReference c",
    CountryReference.class
).getResultList();
~~~

Hibernate có thể không cần flush pending Product changes trước query này nếu không có overlap. Với native SQL qua JPA `EntityManager`, quy tắc flush có thể khác Hibernate `Session` native; không sao chép kết luận từ một API sang mọi API.

### COMMIT flush mode là gì?

`FlushModeType.COMMIT` có thể trì hoãn flush đến commit; theo đặc tả JPA, ảnh hưởng của pending changes lên kết quả query trước khi flush có thể không xác định trong các trường hợp. Đừng đổi sang COMMIT chỉ để che lỗi “quá nhiều SQL”: cần chứng minh query semantics vẫn đúng.

### Có cần tự flush ngay trước mọi truy vấn không?

Không. Nếu dùng flush mode chuẩn và transaction đúng, Hibernate thường biết khi nào cần đồng bộ cho query. Explicit flush có thể tạo round trip không cần thiết trước query chỉ đọc bảng không liên quan hoặc trước khi unit of work hoàn tất.

## 10. Vì sao “flush sau mọi persist()” thường không cần thiết?

Ví dụ code với 100 entity mới:

~~~java
tx.begin();
for (int i = 0; i < 100; i++) {
    Product p = new Product(
        "SKU-" + i,
        "Product " + i,
        new BigDecimal("10.00")
    );
    entityManager.persist(p);
}
tx.commit();
~~~

Với generator cho phép cấp ID trước insert, Hibernate có thể đưa insert vào ActionQueue và thực hiện những statement phù hợp tại flush/commit. Nếu bật batching, các insert cùng SQL shape có cơ hội được gửi theo JDBC batch.

Nếu thêm:

~~~java
for (int i = 0; i < 100; i++) {
    entityManager.persist(new Product(...));
    entityManager.flush(); // 100 điểm đồng bộ thay vì một/lô.
}
~~~

thì khả năng gom các inserts thành một batch lớn bị phá vỡ, số lần dirty checking/flush overhead tăng và các constraint/callbacks xảy ra sớm hơn. Đây có thể là thay đổi hiệu năng đáng kể khi nhiều thao tác cùng nằm trong một transaction.

**Ngoại lệ có chủ đích:** khi cần phát hiện constraint vi phạm tại một mốc cụ thể hoặc cần SQL đã chạy trước một thao tác database phụ thuộc nó, explicit flush có thể đúng. Không nhầm tình huống đó với thói quen gọi flush trong mọi repository method.

## 11. Gọi flush quá sớm có thể đổi thời điểm lỗi xuất hiện

Giả sử có unique constraint trên `product.sku`. Hai entity mới dùng cùng SKU:

~~~java
tx.begin();
entityManager.persist(
    new Product("DUP-001", "First", new BigDecimal("10.00"))
);
entityManager.persist(
    new Product("DUP-001", "Second", new BigDecimal("20.00"))
);

entityManager.flush(); // Có thể phát sinh unique constraint violation.
tx.commit();
~~~

Nếu không flush tường minh, exception có thể xảy ra khi commit-triggered flush. Gọi flush sớm giúp biết lỗi sớm hơn, nhưng **không chứng minh lỗi chỉ có thể xảy ra ở flush**: deferred constraints và các điều kiện DB khác vẫn có thể bị từ chối khi commit.

### Sau lỗi flush có thể tiếp tục được không?

Thông thường **không nên tiếp tục dùng persistence context/transaction đã gặp Hibernate/JDBC exception trong quá trình flush**. Transaction có thể bị đánh dấu rollback-only hoặc DB có thể đang ở trạng thái aborted. Hãy rollback, kết thúc unit of work và bắt đầu lại với một persistence context/transaction phù hợp.

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    // ghi nhiều entity...
    entityManager.flush();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
    }
    throw failure;
}
~~~

Đoạn code áp dụng cho `RESOURCE_LOCAL`. Với Spring/JTA, framework xử lý transaction; đừng tự gọi `entityManager.getTransaction()` và rollback khi context do container sở hữu.

### Đừng flush để “thử xem dữ liệu hợp lệ” rồi tiếp tục trên Session hỏng

Nếu constraint violation xảy ra, bắt exception rồi `clear()` để “xóa lỗi” không làm transaction hợp lệ trở lại. `clear()` chỉ tách objects; nó không sửa constraint, không rollback DB transaction và không xóa rollback-only flag.

## 12. `clear()` sau mọi query có thể phá lợi ích identity map

~~~java
Product a = entityManager.find(Product.class, 42L);
entityManager.clear();
Product b = entityManager.find(Product.class, 42L);
~~~

Ở hai lần find, Hibernate không còn first-level managed object từ lần đầu khi lần thứ hai chạy. Nó có thể cần load lại từ DB hoặc second-level cache, gây công việc dư thừa. Đồng thời:

~~~java
System.out.println(a == b); // thường false
System.out.println(entityManager.contains(a)); // false
System.out.println(entityManager.contains(b)); // true
~~~

Trong cùng transaction, nếu code đang giữ reference `a` và tiếp tục sửa `a`, dirty checking không theo dõi nó nữa. Từ đây dễ phát sinh bug mà người viết code quy cho “Hibernate không update”.

### Lợi ích identity map bị mất

Persistence context đảm bảo một managed instance theo entity key trong context. Nó cũng giúp:

- Tránh hydrate lại entity cùng ID ở nhiều điểm của unit of work.
- Duy trì tính nhất quán của object graph khi code truy cập association từ nhiều đường.
- Theo dõi loaded state để lập update khi cần.
- Giữ relationship changes/cascade trong cùng unit of work.

Gọi clear theo thói quen phá các lợi ích đó mà không chắc tiết kiệm được chi phí đáng kể.

## 13. Đừng dùng clear để “đọc lại dữ liệu mới nhất” khi còn pending writes

Giả sử transaction đang sửa hai sản phẩm:

~~~java
Product p1 = entityManager.find(Product.class, 1L);
Product p2 = entityManager.find(Product.class, 2L);
p1.changePrice(new BigDecimal("100.00"));
p2.changePrice(new BigDecimal("200.00"));

entityManager.clear();
Product reloaded = entityManager.find(Product.class, 1L);
~~~

Nếu chưa flush, thay đổi trên cả hai có thể không được ghi. Lập trình viên chỉ muốn reload product 1 nhưng lại làm **mọi managed entities** bị detach.

### Dùng refresh khi muốn đồng bộ một entity từ DB

~~~java
Product p = entityManager.find(Product.class, 42L);
entityManager.refresh(p);
~~~

`refresh()` lấy lại state từ DB cho entity managed; nó có thể **ghi đè pending edits trên chính entity đó**. Cần xác định ý định rõ ràng: cập nhật từ DB và chấp nhận mất local changes, hay giữ pending edits rồi commit?

### Dùng detach khi chỉ muốn tách một entity

~~~java
entityManager.detach(p);
~~~

`detach(p)` tác động đến entity được chỉ định (và những entity thuộc cascade DETACH nếu mapping yêu cầu), nhỏ hơn phạm vi `clear()`. Tuy nhiên, những thay đổi chưa flush trên entity bị detach cũng có thể không được lưu. Việc chọn detach thay clear không tự giải quyết vấn đề mất pending changes; nó chỉ làm **phạm vi tác động hẹp hơn**.

## 14. Clear không thay thế “reset transaction”

Nếu một transaction gặp lỗi hoặc bị đánh dấu rollback-only:

~~~java
entityManager.clear();
~~~

không chuyển transaction từ rollback-only thành có thể commit. Tương tự, clear không tự:

- Rollback SQL đã flush.
- Mở một transaction mới.
- Xóa lock DB đang nắm giữ.
- Xác nhận hay hủy commit.
- Khôi phục constraint đã vi phạm.

Muốn xử lý transaction lỗi, cần **rollback theo ownership** và kết thúc context không còn an toàn rồi tạo unit of work mới. Sau rollback, cả entity state trong Java và trạng thái DB đã commit cần được hiểu riêng; object có thể vẫn mang field/ID đã thay đổi dù DB không lưu chúng.

## 15. Khi nào explicit flush thực sự hữu ích?

Một số trường hợp hợp lý:

| Nhu cầu cụ thể | Vì sao flush có ích? | Điều kiện/cảnh báo |
|---|---|---|
| **Kiểm tra constraint tại một điểm xác định** | Buộc pending insert/update được gửi để DB kiểm tra những constraint áp dụng khi statement chạy. | Constraint trì hoãn có thể chờ đến commit; lỗi phải rollback. |
| **SQL đã chạy trước một thao tác JDBC/native riêng** | Native code/trigger cần thấy dữ liệu đã được DB nhận trong cùng transaction. | Kiểm tra cùng connection/transaction; flush không đồng nghĩa commit. |
| **Chia batch lớn thành các đợt ghi** | Sau mỗi lô, gửi SQL và có thể tiếp theo clear để giảm kích thước context. | Chỉ clear sau flush thành công, xử lý detached refs/cascade. |
| **Đo/test SQL tại ranh giới chủ động** | Test muốn quan sát constraint hoặc SQL ngay, không chờ commit. | Không rải trong production chỉ để log đẹp. |
| **Đảm bảo SQL pending đã chạy trước một thao tác phụ thuộc DB** | Ví dụ thủ tục trong cùng transaction cần đọc row mới. | Cần xác nhận flush/order/trigger semantics. |

Ví dụ một thao tác sử dụng cùng transaction database sau khi tạo entity:

~~~java
tx.begin();
Product p = new Product(
    "EXT-001", "External product", new BigDecimal("10.00")
);
entityManager.persist(p);
entityManager.flush(); // Cần row đã INSERT trước khi native SQL phụ thuộc nó.

Object result = entityManager.createNativeQuery(
    "select count(*) from product where id = :id"
).setParameter("id", p.getId())
 .getSingleResult();

tx.commit();
~~~

Với JPA AUTO flush, query native có thể tự kích hoạt flush trong một số cấu hình; explicit flush ở ví dụ là **ranh giới có chủ đích** nếu ứng dụng cần bảo đảm thứ tự ghi trước một thao tác khác. Không lấy nó làm quy tắc mọi native query đều phải có flush đi kèm.

## 16. Khi nào explicit clear thực sự hữu ích?

Các trường hợp có lý do:

1. **Batch lớn:** sau khi flush thành công một phần công việc, tách managed entities để hạn chế memory/dirty-check overhead.
2. **Bulk HQL/JPQL/native DML:** một thao tác bên ngoài entity state tracking đã cập nhật DB và context có thể giữ các objects stale; sau khi xử lý pending writes, clear/refresh theo yêu cầu.
3. **Yêu cầu loại bỏ state cũ của toàn context:** ứng dụng thực sự muốn reload toàn bộ graph trong unit of work hoặc chuyển sang một giai đoạn dữ liệu khác.
4. **Một số quy trình import/ETL có lifecycle được kiểm soát:** khi các objects đã xử lý không còn cần được giữ managed.

Đặc biệt, **không clear chỉ vì số lần gọi find lớn** nếu chưa biết memory profile, transaction size, cách Hibernate quản lý context, và ứng dụng còn cần managed references hay không.

### Có thể dùng transaction mới thay clear không?

Nhiều khi **đúng**. Thiết kế các unit of work ngắn, rõ ràng và để framework quản lý EntityManager theo transaction giúp lifecycle sạch hơn so với một context rất dài rồi chủ động clear ở những thời điểm tùy ý. Tuy nhiên, chia transaction thay đổi tính atomicity của nghiệp vụ; không tự tách một giao dịch nguyên tử chỉ vì muốn tiết kiệm RAM.

## 17. Batch processing: trường hợp thường cần cả flush và clear

Khi import hoặc cập nhật hàng chục nghìn row, persistence context có thể giữ quá nhiều managed objects và loaded-state snapshots nếu không có ranh giới lô.

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

final int batchSize = 50;
for (int i = 0; i < rows.size(); i++) {
    ImportRow row = rows.get(i);
    Product product = new Product(
        row.sku(), row.name(), row.price()
    );
    entityManager.persist(product);

    if ((i + 1) % batchSize == 0) {
        entityManager.flush(); // Gửi pending INSERT theo lô.
        entityManager.clear(); // Bỏ managed state đã xử lý.
    }
}

entityManager.flush(); // Đảm bảo phần dư cuối cùng được đồng bộ.
tx.commit();
~~~

Mẫu này phù hợp nhất khi các entities đã được xử lý **không còn cần managed state** ở những vòng lặp sau, và domain không có quan hệ/cascade đang phụ thuộc các references bị detach.

### Không nhầm kích thước batch với transaction boundary

Trong code trên, mọi lô vẫn nằm trong **một transaction**. Nếu vòng lặp ghi 10.000 row rồi lỗi ở cuối, rollback có thể hủy toàn bộ dữ liệu trong transaction (giả sử các bảng tham gia cùng database transaction), dù đã gọi flush nhiều lần.

Muốn commit từng lô là thiết kế **nhiều transactions**, với trade-off rằng các lô trước có thể đã commit khi lô sau thất bại. Điều đó đòi hỏi idempotency, restart/resume, error tracking và nghiệp vụ chấp nhận partial progress.

### Với Spring

Trong Spring service dùng `@Transactional`, tránh tự gọi transaction begin/commit như ví dụ `RESOURCE_LOCAL`. Có thể gọi `entityManager.flush()/clear()` trong transaction được Spring quản lý khi batch thật sự cần, hoặc dùng framework batch orchestration phù hợp.

### Với relationships

Nếu một parent managed giữ `List<Child>`, gọi clear giữa lúc đang xây graph có thể detach parent; các child được thêm sau đó không được cascade như khi parent còn managed. Hãy sắp xếp batch theo các aggregate độc lập, hoặc dùng chiến lược khác để không làm rời một graph đang cần ghi nguyên tử.

## 18. Vì sao dùng IDENTITY có thể làm SQL insert sớm dù không flush?

Với:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

database sinh khóa khi `INSERT`. Hibernate thường phải thực hiện insert sớm để lấy ID, mặc dù còn chưa gọi `flush()` rõ ràng; trong một số tình huống có thể trì hoãn theo context/API. Với `SEQUENCE`, ID thường được lấy trước và INSERT có thể chờ flush.

Vì vậy:

~~~java
entityManager.persist(product);
System.out.println(product.getId());
~~~

không cho biết toàn bộ SQL đã chạy hay database đã commit. Khi nghiên cứu hiệu năng hoặc giải thích tại sao flush không tạo thêm insert, cần xem **ID generation strategy** và SQL log.

Một lưu ý khác: IDENTITY thường hạn chế JDBC batching của Hibernate đối với entity inserts do mỗi insert cần generated key. Do đó thêm explicit flush/clear không “kích hoạt” batching vốn bị giới hạn bởi generator.

## 19. Bulk HQL UPDATE: vì sao đôi khi phải clear sau đó?

Bulk JPQL/HQL DML không đồng bộ từng managed entity như việc gọi setter:

~~~java
tx.begin();
Product product = entityManager.find(Product.class, 42L);
// product.active trong Java vẫn là true.

int changed = entityManager.createQuery(
    "update Product p set p.active = false where p.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

// Managed product có thể vẫn giữ active=true.
tx.commit();
~~~

SQL bulk update đã tác động database nhưng entity object có thể vẫn cũ trong context. Đó là **stale managed state**.

### Luồng có chủ đích khi bulk update

~~~java
tx.begin();

entityManager.flush(); // Chỉ nếu còn pending changes cần ghi trước bulk DML.

int changed = entityManager.createQuery(
    "update Product p set p.active = false where p.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

entityManager.clear(); // Chấp nhận detach toàn context để tránh dùng state cũ.

Product refreshedByReload =
    entityManager.find(Product.class, 42L);

tx.commit();
~~~

Ở đây cặp flush/clear **có lý do cụ thể**: flush bảo vệ pending writes trước bulk DML, clear tránh dùng stale objects sau bulk DML. Nhưng nó vẫn có chi phí và phạm vi tác động toàn context; nếu chỉ một entity bị ảnh hưởng và không muốn detach toàn bộ, `refresh(entity)` có thể phù hợp hơn.

### Bulk update và @Version

JPQL bulk update thông thường không tự áp dụng optimistic version checks/increments theo cách Hibernate thực hiện khi dirty-check từng managed entity. Nếu ứng dụng cần concurrency control, phải thiết kế bulk update với điều kiện/version handling phù hợp. Không gọi clear rồi mặc định optimistic locking đã được giải quyết.

### Bulk DELETE còn khó hơn

Nếu bulk delete xóa row DB nhưng context còn managed entity đại diện row đó, getter trên object có thể tiếp tục trả state cũ; commit hoặc những thao tác sau có thể thất bại nếu ORM cố update/delete cùng row. Ranh giới context sau bulk DML phải được quyết định rõ.

## 20. Native SQL, stored procedure và JDBC trong cùng transaction

Một service có thể trộn ORM với SQL trực tiếp:

~~~java
Product p = new Product(
    "MIX-001", "Mixed access", new BigDecimal("20.00")
);
entityManager.persist(p);

// Ở một bước sau, code muốn gọi stored procedure hoặc native SQL
// cần row mới đã có trên DB trong cùng transaction.
~~~

Nếu stored procedure dùng đúng transaction/connection và cần thấy row Hibernate chưa insert, explicit flush có thể là ranh giới hợp lý:

~~~java
entityManager.flush();
entityManager.createNativeQuery(
    "select process_product(:id)"
).setParameter("id", p.getId())
 .getSingleResult();
~~~

**Nhưng không đảm bảo một kết nối DB khác cũng nhìn thấy row**: với transaction chưa commit và isolation thông thường, connection khác không thấy uncommitted changes. Flush không “publish dữ liệu” ra ngoài transaction.

### Điều phối transaction là điều kiện quan trọng

Nếu ứng dụng vô tình dùng một JDBC connection khác không cùng transaction khi gọi thủ tục, `flush()` không sửa được vấn đề visibility/atomicity. Cần đảm bảo các thao tác có cùng transaction boundary và connection enlistment phù hợp.

### Native DML và state stale

Native `UPDATE`/`DELETE` không tự cập nhật mọi managed fields trong context. Sau native DML, lựa chọn `refresh` hoặc `clear` phải căn cứ phạm vi entity bị tác động và liệu còn pending writes hay không.

## 21. Spring Data JPA: save(), saveAndFlush() và flush()

Trong Spring Data JPA, người mới học thường thay mọi `repository.save(entity)` bằng `repository.saveAndFlush(entity)` vì nghĩ “save chưa lưu”. Thực tế:

- `save(entity)` thường gọi JPA `persist()` hoặc `merge()` tùy trạng thái entity, đăng ký/thực hiện thao tác trong persistence context.
- `saveAndFlush(entity)` gọi save rồi yêu cầu flush; điều này có thể đưa SQL đến DB sớm **nhưng không tự commit transaction đang mở**.
- `repository.flush()` đồng bộ pending changes trong persistence context theo semantics JPA.
- `saveAllAndFlush(entities)` có thể flush sau khi xử lý danh sách; không nên dùng nếu yêu cầu chỉ là đăng ký nhiều entities để commit một lần.

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void updatePrice(long id, BigDecimal newPrice) {
        Product product = repository.findById(id)
            .orElseThrow();
        product.changePrice(newPrice);
        // Không cần saveAndFlush() vì product đã managed.
    }
}
~~~

Trong một transaction, Hibernate dirty checking xử lý thay đổi ở cuối. `saveAndFlush()` có thể hợp lý khi thực sự cần constraint/SQL side effect được áp dụng trước một bước khác. Không dùng nó như phương pháp mặc định cho mọi update.

### `@Modifying(clearAutomatically, flushAutomatically)`

Spring Data JPA hỗ trợ:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(
    "update Product p set p.active = false where p.id = :id"
)
int deactivateBulk(@Param("id") Long id);
~~~

Đây là một cấu hình có thể hữu ích với bulk DML vì nó giải quyết hai vấn đề có chủ đích: flush pending changes trước bulk update và clear context sau bulk update để tránh stale objects.

**Đổi lại**, `clearAutomatically = true` làm **mọi managed entities trong context** bị detach, không chỉ Product được update. Cần hiểu service workflow trước khi bật, và không đặt annotation này trên mọi method theo thói quen. Nó là extension của Spring Data, không phải annotation JPA chung.

## 22. Cấu hình read-only và thay thế bằng projection

Nếu endpoint chỉ cần xem thông tin sản phẩm, không phải mọi lần đọc đều cần giữ hàng nghìn managed entities và dirty-checking metadata:

~~~java
public record ProductView(
    Long id, String sku, BigDecimal unitPrice
) {}
~~~

~~~java
List<ProductView> views = entityManager.createQuery(
    """
    select new com.example.dto.ProductView(
        p.id, p.sku, p.unitPrice
    )
    from Product p
    where p.active = true
    """,
    ProductView.class
).getResultList();
~~~

Giả định record có package đúng `com.example.dto`. DTO projection trả các giá trị cần cho API mà không cần tạo managed Product entity cho từng row. Điều này thường phù hợp hơn việc load entity rồi `clear()` ngay sau query.

### Read-only mode

Hibernate native có khả năng `Session.setDefaultReadOnly(true)` và read-only hints. Với entity read-only, Hibernate có thể giảm loaded-state snapshot/dirty checking đối với simple properties theo semantics hỗ trợ.

~~~java
try (Session session = sessionFactory.openSession()) {
    session.setDefaultReadOnly(true);
    Product p = session.find(Product.class, 42L);
    // Chỉ đọc, không dự kiến ghi state của p.
}
~~~

Spring `@Transactional(readOnly = true)` là hint/transaction setting có thể tối ưu một số cơ chế, nhưng không tự bảo đảm mọi ghi DB bị chặn trong mọi cấu hình. Không thay permission/DB access rules bằng readOnly flag.

**Kết luận:** nếu mục tiêu là giảm overhead của một read path, cân nhắc projection hoặc read-only mode phù hợp trước, thay vì gọi clear sau từng entity.

## 23. `flush()` không sửa được vấn đề N+1 hoặc lazy loading

Ví dụ:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
~~~

Nếu `lines` là lazy collection, code có thể gây thêm query trên từng order (N+1). Gọi `entityManager.flush()` trước vòng lặp không làm Hibernate tự fetch tất cả `lines` hiệu quả hơn.

Các lựa chọn liên quan đến N+1 là:

- JPQL `join fetch` khi cần cả collection và hiểu giới hạn pagination.
- Hibernate batch fetching qua `@BatchSize` hoặc default batch fetch size.
- DTO/projection/aggregate query nếu chỉ cần `count` hoặc field chọn lọc.
- Fetch plan phù hợp với use case.

Tương tự, gọi `clear()` trước khi truy cập lazy collection có thể gây `LazyInitializationException` hoặc khiến data không còn được tải qua context ban đầu; nó không phải cách “refresh lazy”.

### Lazy loading sau clear

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
entityManager.clear();

int count = order.getLines().size();
// Nếu lines chưa initialized, có thể gây LazyInitializationException.
~~~

Đây là hậu quả trực tiếp của detach, không phải lỗi `@OneToMany`. Nếu code cần collection, hãy fetch nó đúng lúc context còn quản lý entity, hoặc trả DTO đã chứa dữ liệu cần thiết.

## 24. Clear có thể phá graph và cascade giữa chừng

Giả sử:

~~~java
@Entity
class PurchaseOrder {
    @Id @GeneratedValue Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    List<OrderLine> lines = new ArrayList<>();
}
~~~

Service:

~~~java
tx.begin();
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class, orderId
);

// Thao tác A: thêm hoặc chỉnh con, cần cascade/dirty tracking.
entityManager.clear();

// Thao tác B: tiếp tục sửa order đang được giữ trong biến Java.
// Nhưng order giờ detached!
tx.commit();
~~~

Nếu chưa flush trước clear, thao tác A có thể không được ghi. Thao tác B sau clear không tự được dirty-checked. Với lazy collections chưa initialized, truy cập cũng có thể lỗi.

### `orphanRemoval` không phải bảo vệ trước clear

Nếu loại một child khỏi collection managed và định xóa orphan, nhưng `clear()` trước khi Hibernate đồng bộ hành động, việc xóa có thể không diễn ra. `orphanRemoval = true` không tự biến mọi `List.remove` thành SQL DELETE đã commit ngay lập tức.

### Gọi clear sau flush có an toàn tuyệt đối?

Không. Flush rồi clear có thể giữ những SQL đã gửi trong transaction, nhưng các references đã detached. Nếu code sau đó thay đổi parent/child, sử dụng cascade, truy cập lazy field hoặc gọi remove trên detached object, semantics không còn giống lúc managed. Hãy thiết kế **điểm kết thúc công việc với graph** trước khi clear.

## 25. Clear và optimistic locking

`@Version` giúp Hibernate phát hiện xung đột khi update managed entity. Nhưng:

~~~java
Product p = entityManager.find(Product.class, 42L);
entityManager.clear();
p.changePrice(new BigDecimal("155.00"));
~~~

không có dirty checking trên `p` sau clear. Không có SQL update thì cũng không có optimistic-locking check gắn với thay đổi đó.

Ngược lại, nếu application merge một detached object có version cũ vào context mới, Hibernate có thể phát hiện stale state ở merge/flush/commit tùy mapping và phiên bản. Điều đó là một quy trình khác — **clear không phải công tắc reset version**.

### Bẫy “flush để tránh lost update”

Flush sớm không thay thế optimistic locking hoặc transaction isolation. Transaction A flush price 120 nhưng chưa commit; transaction B có thể đọc/cập nhật theo isolation và locking rules. Sử dụng `@Version`, DB constraints, locking hoặc atomic SQL thích hợp để bảo vệ invariant, không phụ thuộc việc flush sớm để “thắng” các giao dịch khác.

## 26. Sự khác nhau giữa clear và evict/detach

Hibernate native API có `Session.evict(entity)`, JPA dùng `EntityManager.detach(entity)`. Cả hai biểu diễn việc tách entity cụ thể khỏi context, với các quy tắc cascade/tình huống tương ứng. `clear()` tác động toàn context.

~~~java
Product p1 = entityManager.find(Product.class, 1L);
Product p2 = entityManager.find(Product.class, 2L);

entityManager.detach(p1);
System.out.println(entityManager.contains(p1)); // false
System.out.println(entityManager.contains(p2)); // true
~~~

Nếu chỉ muốn bỏ quản lý Product#1, `detach` hẹp hơn `clear`. Nhưng cũng phải đảm bảo đã flush những thay đổi ở p1 cần được giữ. Trong Hibernate, việc tách parent có collections/cascade cần hiểu ảnh hưởng tới graph.

### Evict second-level cache không phải clear first-level cache

Hibernate có APIs làm mất hiệu lực cache cấp hai như `SessionFactory.getCache().evictEntityData(...)`. Đây là vấn đề khác `Session.clear()`. Nếu một external system sửa DB, làm mới dữ liệu có thể đòi phối hợp first-level context, second-level cache và transaction isolation; gọi clear alone không chắc đảm bảo freshness khi cache cấp hai chứa stale state.

## 27. Thời điểm gọi flush ảnh hưởng trigger, generated value và constraint

Database có thể có trigger hoặc generated columns:

~~~sql
-- Ý tưởng schema:
-- Product INSERT làm DB trigger cập nhật thống kê hoặc audit row.
~~~

Khi `persist()` chỉ đăng ký insert chưa gửi SQL, trigger chưa chạy. Một `flush()` có thể khiến INSERT chạy và trigger có thể thực thi trong transaction. Nhưng:

1. Dữ liệu do trigger tạo cũng có thể chưa commit.
2. Hibernate entity trong Java chưa chắc tự có mọi giá trị do trigger cập nhật nếu mapping không khai báo generated/readback thích hợp.
3. SQL ở kết nối khác có thể chưa thấy những thay đổi chưa commit.
4. Một constraint hoãn đến commit vẫn có thể phát hiện lỗi sau flush.

Nếu nghiệp vụ cần giá trị generated từ DB, xem mapping của các generated attributes, `refresh`/returning support hoặc API thích hợp thay vì thêm flush rồi tin mọi field Java tự đổi.

### Thời điểm SQL có thể chạy sớm vì ID generator

Với IDENTITY, INSERT thường cần chạy để có generated key ngay; sequence có thể cấp ID trước INSERT; table generator có hoạt động SQL riêng. Vì vậy “không gọi flush” không đồng nghĩa “chắc chắn không có SQL nào trước commit”.

## 28. Đo hiệu năng trước khi tối ưu flush/clear

Những chỉ số nên quan sát:

| Triệu chứng | Giả thuyết | Kiểm chứng |
|---|---|---|
| Nhiều SQL UPDATE cho một entity | Gọi flush nhiều lần giữa các setter hoặc callback/query triggers | SQL log theo transaction, Hibernate statistics. |
| Nhiều câu INSERT đơn lẻ | IDENTITY hạn chế batching, SQL shape khác nhau, explicit flush per item | JDBC batch metrics, ID generator, driver log. |
| Memory tăng theo số row import | Persistence context giữ nhiều managed entities/snapshots | Heap profile và số entities managed, batch flush/clear. |
| CPU cao lúc commit | Dirty checking nhiều managed objects hoặc collection graph lớn | Profiling, transaction size, read-only/projection. |
| SQL select lặp lại cùng ID | Gọi clear hoặc tạo nhiều contexts vô ích | Cache hit logs, Session lifecycle. |
| LazyInitializationException sau clear | Entity/collection trở thành detached trước khi truy cập | Fetch plan và vị trí clear. |
| DB không update dù setter chạy | Entity detached sau clear/detach, read-only/immutable | `contains()`, SQL logs, transaction boundaries. |

Có thể bật:

~~~properties
# Ví dụ Spring Boot / Hibernate 6 trong môi trường thử nghiệm:
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
hibernate.generate_statistics=true
~~~

Tên logger và cách cấu hình statistics có thể khác theo phiên bản/framework. Log bind values có thể lộ dữ liệu nhạy cảm; không bật TRACE không kiểm soát ở production.

### Một lưu ý quan trọng

Số dòng SQL logger in ra **không luôn bằng số network round trips**; JDBC batching, driver rewriting và database protocol có thể khác. Nếu tối ưu batch, cần quan sát statistics, throughput và JDBC/DB metrics thay vì chỉ đếm dòng log.

## 29. Anti-pattern: repository luôn `flush()` sau mỗi phương thức

Ví dụ không nên dùng mặc định:

~~~java
@Repository
class ProductRepositoryCustom {
    @PersistenceContext
    private EntityManager em;

    public void changePrice(long id, BigDecimal price) {
        Product p = em.find(Product.class, id);
        p.changePrice(price);
        em.flush(); // Bắt buộc caller chịu một ranh giới SQL không cần thiết.
    }
}
~~~

Nếu caller dùng:

~~~java
@Transactional
public void updateManyProducts(List<PriceChange> changes) {
    for (PriceChange change : changes) {
        repository.changePrice(change.id(), change.price());
    }
}
~~~

thì flush xảy ra mỗi lần gọi repository, làm mất cơ hội Hibernate gom nhiều thay đổi trong transaction. Repository cũng vô tình quyết định thời điểm constraint được kiểm tra và SQL side effects xảy ra, dù transaction thuộc service.

Một thiết kế thường rõ hơn:

~~~java
public void changePrice(long id, BigDecimal price) {
    Product p = em.find(Product.class, id);
    if (p == null) throw new IllegalArgumentException("Missing product");
    p.changePrice(price);
    // Caller/transaction manager kiểm soát flush boundary.
}
~~~

Nếu một phương thức thực sự cần SQL đã chạy trước khi trả kết quả, hãy biểu đạt yêu cầu đó rõ ràng trong tên/API và giải thích tại sao; đừng rải flush ở mọi write method.

## 30. Anti-pattern: `flush(); clear();` sau mỗi lần save

~~~java
@Transactional
public void saveProduct(Product product) {
    entityManager.persist(product);
    entityManager.flush();
    entityManager.clear();
}
~~~

Thoạt nhìn giống “save rồi giải phóng bộ nhớ”. Nhưng:

- Mất khả năng gom SQL cùng transaction của caller.
- Tất cả managed entities khác, không chỉ `product`, đều bị detached.
- Caller có thể giữ references và tiếp tục sửa nhưng không được dirty checking.
- Lazy associations có thể không còn tải được.
- Một giao dịch lớn có thể cần nhiều vòng load lại cùng entity.
- Flush không phải commit, nên `product` chưa chắc đã được lưu vĩnh viễn dù method trả về.

Trong một service transaction bình thường, thường chỉ cần `persist()` hoặc thay đổi managed state rồi để transaction manager flush/commit. Cặp flush/clear thuộc **batch processing hoặc quy trình state management cụ thể**, không phải chuẩn CRUD.

## 31. Anti-pattern: `clear()` để né optimistic-locking exception

Giả sử transaction A load Product#42 với version 2, transaction B commit update version 3. A sửa và flush, gặp optimistic-locking exception.

Sai:

~~~java
try {
    entityManager.flush();
} catch (OptimisticLockException ex) {
    entityManager.clear();
    // tiếp tục commit transaction cũ - KHÔNG NÊN
}
~~~

`clear()` không thay đổi row version trong DB, không sửa transaction rollback-only và không quyết định chiến lược giải quyết conflict. Sau lỗi:

1. Rollback/kết thúc unit of work hiện tại theo framework.
2. Chọn retry có giới hạn và idempotency nếu nghiệp vụ cho phép.
3. Trong transaction mới, load state mới.
4. Kiểm tra quy tắc merge/xung đột và thực hiện lại thao tác khi hợp lệ.

Không “nuốt” optimistic-locking error rồi giả định mọi thứ đã commit.

## 32. Anti-pattern: ép flush để lấy ID mà không hiểu generator

~~~java
entityManager.persist(product);
entityManager.flush();
Long id = product.getId();
~~~

Với `SEQUENCE`, Hibernate thường có thể cấp ID ngay trong `persist()`, nên flush chỉ để lấy ID có thể không cần. Với `IDENTITY`, Hibernate thường insert để lấy key và ID có thể xuất hiện trước explicit flush theo bối cảnh. Với assigned ID/UUID, ID có thể đã được cấp khi tạo object.

Điều quan trọng là hiểu **chiến lược sinh ID của entity** và yêu cầu thật:

- Muốn có ID để tạo association trong cùng persistence context? ORM thường có thể quản lý thứ tự insert và FK.
- Muốn row thật sự đã tồn tại để native SQL trong cùng transaction tham chiếu? Có thể cần flush.
- Muốn row chắc chắn đã commit để service khác đọc? Flush **không đủ**, cần commit và isolation/communication phù hợp.

Gọi flush theo thói quen để lấy ID có thể khiến code trông đúng trong một generator nhưng gây overhead và rối transaction boundary.

## 33. Phân biệt flush với `savepoint` và retry

Một số hệ quản trị hỗ trợ transaction savepoint. Hibernate flush **không tạo savepoint**; nó chỉ gửi SQL.

~~~text
BEGIN TX
  persist(A)
  flush()          <-- SQL INSERT(A) đã chạy trong transaction
  persist(B)
  flush()          <-- SQL INSERT(B) có thể lỗi
ROLLBACK
~~~

Nếu rollback toàn transaction, cả A và B không được commit. Muốn rollback một phần sau savepoint đòi hỏi một chiến lược transaction/JDBC riêng và phải xử lý sự lệch giữa persistence context với DB khi thực hiện savepoint rollback. Không coi việc rollback SQL ở savepoint là Hibernate tự hoàn nguyên tất cả Java managed state/snapshots.

### Retry sau exception

Nếu transaction gặp lỗi SQL, cách an toàn thường là kết thúc context lỗi và chạy lại nghiệp vụ trong transaction mới; không gọi `clear()` rồi retry vài câu SQL trên context/transaction đang ở trạng thái không xác định.

## 34. Tài nguyên và thời gian sống của persistence context

Trong ứng dụng request/transaction-scoped EntityManager, một transaction thường có thời gian sống ngắn:

~~~text
HTTP request
  |
  +-- service @Transactional
        |
        +-- find / persist / mutate
        +-- lazy loading khi còn transaction
        +-- flush at needed boundary / commit
        |
      transaction ends
~~~

Nếu context kết thúc đúng lúc, ít cần gọi clear thủ công. Ngược lại, extended persistence contexts hoặc các batch jobs giữ Session rất lâu có thể khiến managed state tăng, vì thế cần kế hoạch flush/clear/detach hoặc chia transaction có chủ đích.

### Không nhầm OSIV với nhu cầu clear

Open Session in View có thể giữ persistence context mở trong lúc render response, cho phép lazy loading trong view nhưng cũng có những trade-off như phát SQL ngoài service transaction và khó dự đoán query count. Gọi clear ở cuối controller không giải quyết thiết kế fetch/transaction; thường rõ hơn là tạo DTO đầy đủ trong service và đóng transaction ở ranh giới phù hợp.

## 35. Cách viết service có ranh giới rõ, không rải flush/clear

Ví dụ một nghiệp vụ đổi giá nhiều sản phẩm, yêu cầu **atomicity**:

~~~java
@Service
public class PriceService {
    private final EntityManager entityManager;

    public PriceService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void applyChanges(List<PriceChange> changes) {
        for (PriceChange change : changes) {
            Product product = entityManager.find(
                Product.class, change.productId()
            );
            if (product == null) {
                throw new IllegalArgumentException(
                    "Unknown product: " + change.productId()
                );
            }
            product.changePrice(change.newPrice());
        }

        // Không cần explicit flush hay clear.
        // Transaction manager xử lý commit/rollback.
    }
}

public record PriceChange(long productId, BigDecimal newPrice) {}
~~~

Lợi ích:

- Business transaction bao trùm mọi thay đổi.
- Nếu validation thất bại trước flush, không cần “undo từng update”.
- Hibernate có thể lập các SQL updates theo unit of work.
- Mọi entity được quản lý xuyên suốt method.
- Không cần caller biết chi tiết flush mode hoặc detached state.

Nếu yêu cầu đổi sang **mỗi 100 row commit một transaction**, đây là **một nghiệp vụ/processing contract khác** và phải được thiết kế rõ (kết quả từng lô, retry, idempotency), không chỉ thêm `flush(); clear()` vào vòng lặp.

## 36. Kiểm thử tác động của flush có chủ đích

### Test A — Managed update không cần explicit flush

Trong transaction test:

~~~java
tx.begin();
Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("125.00"));
tx.commit();

entityManager.clear();
Product reloaded = entityManager.find(Product.class, 42L);
assert reloaded.getUnitPrice()
    .compareTo(new BigDecimal("125.00")) == 0;
~~~

Với test thực tế, dùng JUnit/AssertJ thay vì Java `assert` nếu runtime chưa bật `-ea`, và chuẩn bị dữ liệu/transaction teardown rõ. Mục tiêu là chứng minh commit-triggered flush có thể ghi state mà application không cần gọi flush sau setter.

### Test B — Flush rồi rollback không lưu lâu dài

~~~java
tx.begin();
Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("500.00"));
entityManager.flush();
tx.rollback();
~~~

Trong transaction/context mới, query DB và xác nhận giá chưa commit. Đừng dùng chính object `p` sau rollback làm nguồn kết quả DB.

### Test C — Clear trước flush bỏ thay đổi

~~~java
tx.begin();
Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("550.00"));
entityManager.clear();
tx.commit();
~~~

Reload trong context mới; với mapping thông thường, không có UPDATE cho thay đổi đang bị detach. Test này làm rõ clear không phải commit hoặc flush.

### Test D — Flush sớm làm lỗi constraint xuất hiện sớm

~~~java
tx.begin();
entityManager.persist(
    new Product("DUP-SKU", "A", new BigDecimal("10.00"))
);
entityManager.persist(
    new Product("DUP-SKU", "B", new BigDecimal("20.00"))
);
entityManager.flush(); // Dự kiến unique violation ở flush hoặc DB.
~~~

Sau exception, rollback/kết thúc context. Không nuốt exception rồi tiếp tục chạy test khác trên Session đó.

## 37. Kiểm thử tác động của clear có chủ đích

### Test E — Clear tách mọi entities

~~~java
tx.begin();
Product first = entityManager.find(Product.class, 1L);
Product second = entityManager.find(Product.class, 2L);

entityManager.clear();

assert !entityManager.contains(first);
assert !entityManager.contains(second);

tx.rollback();
~~~

Nếu muốn chỉ tách một entity, thử `detach(first)` để so sánh; `second` vẫn managed nếu không bị cascade/detach theo mapping.

### Test F — Bulk UPDATE tạo managed state cũ

~~~java
tx.begin();
Product p = entityManager.find(Product.class, 42L);

entityManager.createQuery(
    "update Product p set p.active = false where p.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

// p có thể còn giữ field active cũ.
entityManager.refresh(p); // Tải lại DB state theo mapping/isolation.

tx.commit();
~~~

Lặp lại với `clear()` rồi `find()` mới trong một transaction được kiểm soát. Mục tiêu là quan sát lý do thật sự cần refresh/clear sau bulk DML chứ không coi clear là bước bắt buộc của mọi query.

### Test G — Batch và managed count

Import vài nghìn entities theo hai cách:

1. `persist()` toàn bộ trong một transaction, chỉ commit cuối.
2. `persist()` theo nhóm 50, `flush()` rồi `clear()` ở điểm kết thúc mỗi nhóm.

Theo dõi heap memory, SQL statements, JDBC batching và total duration. Dữ liệu test phải phù hợp schema; thử cùng generator/dialect/connection pool để so sánh có ý nghĩa. Bài thử không nhằm khẳng định cách 2 luôn nhanh hơn; nó thể hiện trade-off memory, flush overhead và batch execution.

## 38. Checklist tự hỏi trước khi gọi

**Trước khi viết `flush()`**, hãy trả lời:

1. Có cần **SQL đã được gửi xuống database ngay tại dòng này** không? Vì sao?
2. ORM/transaction manager có tự flush trước query/commit đủ cho nhu cầu chưa?
3. Đây có phải một unit of work mà việc flush sớm sẽ chia nhỏ cơ hội batching?
4. Nếu flush ném exception, đã có rollback/error boundary phù hợp chưa?
5. Có đang nhầm “SQL đã chạy” với “transaction đã commit” không?

**Trước khi viết `clear()`**, hãy trả lời:

1. Có thật sự muốn **detach toàn bộ managed entities** trong context này không?
2. Mọi pending changes cần giữ đã được flush/commit ở boundary phù hợp chưa?
3. Code sau có còn dùng những entity references ấy để sửa field, cascade, lazy load hoặc remove không?
4. Có thể dùng `detach(entity)` hay `refresh(entity)` với phạm vi hẹp hơn không?
5. Nếu mục tiêu là giảm RAM, đã đo context size/heap và chọn batch size phù hợp chưa?
6. Nếu mục tiêu là tránh stale state sau bulk DML, đã xác định đúng tập entities bị tác động và transaction semantics chưa?

Nếu không trả lời được lý do trực tiếp, **bỏ lời gọi tường minh và để Hibernate/transaction manager quản lý** thường là điểm bắt đầu an toàn hơn.

## 39. Bảng quyết định nhanh cho các tình huống phổ biến

| Tình huống | Có cần explicit flush? | Có cần explicit clear? | Cách ưu tiên |
|---|---|---|---|
| Sửa một field của managed entity trong `@Transactional` | **Thường không** | **Không** | Để dirty checking và commit xử lý. |
| `persist()` một entity mới | Thường không | Không | Để flush/commit theo transaction; hiểu ID generator. |
| `persist()` nhiều entities nhỏ trong một transaction | Thường không | Không | Gom unit of work, cân nhắc batching khi cần. |
| Import hàng trăm nghìn row, context tăng quá lớn | **Có thể có**, theo lô | **Có thể có**, sau flush | Batch boundary rõ ràng; xử lý detached state. |
| Cần native SQL trong **cùng transaction** thấy INSERT pending | **Có thể cần** | Thường không | Flush trước dependency, kiểm tra connection. |
| Muốn DB constraint được kiểm tra trước bước tiếp theo | **Có thể cần** | Không | Explicit flush rồi xử lý lỗi/rollback. |
| HQL/JPQL SELECT bình thường với AUTO flush | Thường không | Không | Để provider quyết định flush phù hợp. |
| Bulk HQL UPDATE/DELETE làm stale managed entities | Có thể cần **trước** bulk | Có thể cần **sau** bulk | Flush pending writes; clear/refresh theo phạm vi. |
| Muốn tải lại **một** managed entity | Không vì mục tiêu reload | Không bắt buộc | `refresh(entity)` nếu phù hợp. |
| Muốn bỏ quản lý **một** entity | Không tự động | Không | `detach(entity)`; nhớ pending changes. |
| Muốn “giảm số SQL SELECT” | Không | **Không** | Fetch plan, projections, batch fetching, identity map. |
| Gặp Hibernate/JDBC exception khi flush | Không gọi lại một cách mù quáng | Clear không sửa lỗi | Rollback và tạo unit of work mới. |
| Đã flush nhưng chưa commit | Đã thực hiện | Không phải bước commit | Commit/rollback theo transaction. |

Đây là gợi ý về ý định nghiệp vụ, không phải danh sách lệnh phải chạy. Một project có extended persistence context, flush mode MANUAL hoặc infrastructure khác cần quy tắc riêng, nhưng nguyên tắc **tường minh về mục đích** vẫn giữ nguyên.

## 40. Mô hình tư duy cuối cùng

~~~mermaid
flowchart TD
    A["Muốn gọi flush() hoặc clear()?"] --> B{"Mục tiêu là gì?"}
    B -- "Chỉ sửa managed entity bình thường" --> C["Không gọi theo thói quen; để transaction/dirty checking xử lý"]
    B -- "Cần SQL chạy ngay trong transaction" --> D["flush() có chủ đích; nhớ chưa commit"]
    B -- "Muốn giải phóng managed state theo lô" --> E["flush() thành công rồi clear() khi không còn cần refs managed"]
    B -- "Muốn bỏ quản lý một entity" --> F["detach(entity) thay vì clear() toàn context"]
    B -- "Muốn đọc lại DB state" --> G["refresh(entity) hoặc transaction/context mới"]
    B -- "Bulk DML gây stale context" --> H["Xử lý pending writes, rồi refresh/clear theo phạm vi"]
    B -- "Gặp flush exception" --> I["Rollback, kết thúc unit of work; clear không chữa transaction"]
    C --> J["Kiểm tra SQL/transaction behavior theo workload"]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
~~~

**Quy tắc thực hành quan trọng nhất:** `flush()` và `clear()` không phải cặp lệnh “lưu và dọn” cần gọi sau mọi thao tác Hibernate. Với managed entities trong một transaction bình thường, Hibernate đã có **persistence context, dirty checking, write-behind và flush tại các ranh giới cần thiết**. Explicit flush chỉ nên đặt khi cần bảo đảm SQL pending được gửi tại một thời điểm xác định; explicit clear chỉ nên dùng khi thật sự muốn bỏ managed state của context, hiểu rõ dữ liệu chưa flush và hậu quả detached.

Nếu mục tiêu là tối ưu hiệu năng, hãy đo SQL, batching, context memory và transaction duration. Nếu mục tiêu là giải quyết dữ liệu stale, hãy phân biệt refresh, detach, clear và transaction mới. Nếu mục tiêu là xử lý lỗi, rollback đúng boundary — **không dùng clear như công cụ xóa exception**. Khi mỗi lời gọi `flush()` hay `clear()` đều có lý do cụ thể, code vừa đơn giản hơn vừa tránh được các lỗi tinh vi về mất thay đổi, cập nhật trễ, lazy loading và tính nguyên tử giao dịch.
