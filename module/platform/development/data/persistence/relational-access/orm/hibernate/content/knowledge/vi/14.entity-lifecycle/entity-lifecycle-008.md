# refresh để đọc lại dữ liệu từ cơ sở dữ liệu

Trong Hibernate/JPA, một entity đang được quản lý (**managed entity**) không phải lúc nào cũng phản ánh tức thời mọi thay đổi trong database. Persistence context giữ một đối tượng Java cho mỗi identity đã nạp; khi truy vấn lại cùng identity, Hibernate thường sử dụng đối tượng đó thay vì tự động tải lại tất cả giá trị từ database. Nếu một transaction khác, trigger, stored procedure hoặc native SQL đã thay đổi hàng, trạng thái của managed object có thể cũ.

**`EntityManager.refresh(entity)`** yêu cầu JPA provider **đọc lại trạng thái persistent của entity từ database và ghi đè trạng thái đang có trên chính managed object**. Nó hữu ích để đồng bộ giá trị mới nhưng có thể **làm mất sửa đổi chưa flush**. Refresh cũng không tự vượt qua transaction isolation, không “reattach” entity detached và không phải cách bắt buộc để đọc dữ liệu sau mỗi lần gọi `save()`.

Bài học giải thích vòng đời entity liên quan tới `refresh()`, cách sử dụng, điểm khác với `find()`/`flush()`/`clear()`/`merge()`, vấn đề transaction và cache, cascade REFRESH, ví dụ Hibernate/Spring Data JPA và các tình huống cần tránh.

## 1. Vì sao object Java và database có thể khác nhau?

Giả sử entity kiểm kê:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Version
    private long version;

    protected InventoryItem() {}

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
~~~

Khi gọi:

~~~java
InventoryItem item = em.find(InventoryItem.class, 10L);
~~~

Hibernate nạp hàng từ database nếu chưa có managed instance tương ứng. Tại thời điểm đầu:

~~~text
Database: id=10, name="Bút chì", stock_quantity=100, version=1
Java:     item.name="Bút chì", item.stockQuantity=100
~~~

Một transaction khác cập nhật stock xuống 80 và commit. Trạng thái có thể trở thành:

~~~text
Database: id=10, name="Bút chì", stock_quantity=80, version=2
Java:     item.name="Bút chì", item.stockQuantity=100
~~~

Cùng persistence context, gọi lại:

~~~java
InventoryItem again = em.find(InventoryItem.class, 10L);
System.out.println(again == item); // Thường là true.
~~~

`find()` thường trả chính managed instance đang có, nên không bảo đảm stock được đọc lại. Khi muốn cập nhật đối tượng đó từ database:

~~~java
em.refresh(item);
System.out.println(item.getStockQuantity());
~~~

Nếu transaction isolation cho phép quan sát bản commit mới nhất tương ứng, giá trị có thể là 80. **Đối tượng `item` vẫn là cùng Java reference**, không phải một object khác được thay vào.

### 1.1. First-level cache của persistence context

Mỗi `EntityManager` hoặc Hibernate `Session` có một persistence context giữ entity đang managed. Một hệ quả là trong một context, một entity identity thông thường được biểu diễn bằng một managed instance.

Điều này giúp Hibernate:

- Bảo đảm identity nhất quán trong một đơn vị công việc.
- Theo dõi thay đổi qua dirty checking.
- Tránh tải lại cùng hàng từ DB ở mọi lệnh `find()`.
- Điều phối quan hệ giữa các managed entity.

Nhưng first-level cache không tự biết mọi thay đổi ngoài transaction của Hibernate. `refresh()` là một công cụ để đồng bộ một đối tượng cụ thể theo yêu cầu.

## 2. refresh() làm gì?

API JPA:

~~~java
void EntityManager.refresh(Object entity);
~~~

Yêu cầu cơ bản: `entity` phải là **entity đang managed bởi chính EntityManager hiện tại**; ngữ cảnh và transaction phải hợp lệ theo quy tắc JPA.

Hành vi chính:

1. Provider xác định persistent identity và mapping của object.
2. Provider đọc lại trạng thái persistent từ database.
3. Các field được ánh xạ phù hợp được cập nhật trên managed object.
4. Object vẫn managed trong persistence context.
5. Những thay đổi local trước refresh trên các thuộc tính được nạp lại có thể bị ghi đè.
6. Những association có cascade REFRESH có thể được refresh theo quy tắc mapping.
7. Phương thức trả về `void`, không trả một instance mới.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant Service as Java service
    participant PC as Persistence context
    participant DB as Database
    Service->>PC: find(Item, 10)
    PC->>DB: SELECT item
    DB-->>PC: stock=100
    PC-->>Service: managed item
    Note over DB: Transaction khác cập nhật stock=80
    Service->>PC: refresh(item)
    PC->>DB: SELECT lại dữ liệu
    DB-->>PC: stock=80 (nếu isolation cho phép)
    PC->>PC: Ghi đè state managed
    PC-->>Service: Vẫn chính object item
~~~

Sơ đồ mô tả nguyên tắc. SQL, số lần truy cập DB, cách xử lý thuộc tính lazy và association phụ thuộc Hibernate, mapping, driver, dialect và transaction isolation.

### 2.1. refresh không tự lưu hay commit

`refresh()` là thao tác đọc lại state; nó không đồng nghĩa với `commit()`. Nếu có sửa đổi đã được flush trong một transaction chưa commit, refresh có thể đọc lại trạng thái tương ứng của transaction đó, nhưng dữ liệu vẫn có thể rollback.

Vì thế:

- **Flush** đẩy SQL ghi đang chờ tới DB.
- **Refresh** nạp lại persistent state từ DB.
- **Commit** hoàn tất transaction và xác nhận các thay đổi.

Ba thao tác giải quyết ba nhiệm vụ khác nhau.

### 2.2. refresh không tạo object mới

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
InventoryItem alias = item;

em.refresh(item);

System.out.println(alias == item); // true
~~~

Mọi biến trỏ tới cùng object quan sát state đã nạp lại. Điều này rất khác `clear()` + `find()`, vì cách sau có thể tạo một managed instance khác, trong khi reference cũ trở thành detached.

## 3. Ví dụ cơ bản: native SQL thay đổi hàng đang managed

Giả sử entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private int quantity;

    protected Product() {}

    public Product(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getQuantity() {
        return quantity;
    }

    public void rename(String value) {
        this.name = value;
    }
}
~~~

Ví dụ giả định `EntityManager em` đang tham gia một transaction hợp lệ và hàng `products` đã tồn tại:

~~~java
Product product = em.find(Product.class, productId);

// Giả sử quantity ban đầu là 10.
System.out.println(product.getQuantity()); // 10

em.createNativeQuery("""
    UPDATE products
    SET quantity = :newQuantity
    WHERE id = :id
    """)
    .setParameter("newQuantity", 25)
    .setParameter("id", productId)
    .executeUpdate();

// Object trong context có thể vẫn giữ giá trị cũ.
System.out.println(product.getQuantity()); // Có thể là 10.

em.refresh(product);

System.out.println(product.getQuantity()); // 25
~~~

Native SQL đã thay hàng database trực tiếp, không gọi setter `Product` và không dựa vào dirty checking cho field `quantity`. Refresh yêu cầu Hibernate đọc lại giá trị vào managed entity.

**Không phải lần nào chạy native SQL cũng cần refresh.** Nếu chỉ cần số hàng ảnh hưởng của bulk UPDATE và sẽ kết thúc transaction mà không dùng lại object, refresh có thể là round-trip thừa. Chỉ dùng nó khi cần managed state mới.

### 3.1. Đối tượng có còn được quản lý sau refresh?

~~~java
Product product = em.find(Product.class, id);

System.out.println(em.contains(product)); // true

em.refresh(product);

System.out.println(em.contains(product)); // true
~~~

Trong ngữ cảnh thông thường, refresh duy trì trạng thái managed. Do đó những thay đổi persistent hợp lệ **sau refresh** vẫn có thể được Hibernate theo dõi khi transaction flush/commit.

## 4. Cảnh báo quan trọng: refresh có thể làm mất thay đổi chưa flush

Giả sử database lưu:

~~~text
Product(id=5, name="Bàn học", quantity=7)
~~~

Transaction hiện tại:

~~~java
Product product = em.find(Product.class, 5L);

product.rename("Bàn học gỗ tự nhiên");
// Thay đổi mới chỉ nằm trong object managed, chưa flush.

em.refresh(product);

// Hibernate nạp lại name từ database.
System.out.println(product.getName()); // "Bàn học" trong ví dụ.
~~~

`refresh()` **không phải một phương thức merge thông minh** biết giữ field người dùng vừa sửa và chỉ làm mới field khác. Nó ghi đè persistent state theo dữ liệu được tải lại.

### 4.1. Nếu muốn giữ sửa đổi local thì làm gì?

Tùy nghiệp vụ:

- **Muốn bỏ thay đổi local và chấp nhận state từ database**: refresh phù hợp.
- **Muốn lưu thay đổi local trước**: có thể cần `flush()` trước refresh, biết rằng flush gửi SQL và có thể phát hiện lỗi/lock/conflict.
- **Chỉ muốn lấy giá trị một field từ DB**: dùng truy vấn projection riêng thay vì refresh toàn entity, rồi xử lý theo quy tắc domain.
- **Muốn giải quyết thay đổi đồng thời**: dùng `@Version`, transaction, lock hoặc giao diện giải quyết xung đột; không dùng refresh như cách tự động chọn bên thắng.

### 4.2. Flush trước refresh

~~~java
Product product = em.find(Product.class, id);
product.rename("Tên muốn lưu");

em.flush();          // Gửi thay đổi persistent đang chờ.
em.refresh(product); // Đọc lại state từ DB.
~~~

Trình tự này có thể hữu ích với trigger/generated column sau UPDATE. Tuy nhiên:

1. `flush()` **không phải commit**.
2. Hibernate có thể flush **nhiều entity managed khác** trong context, không chỉ Product.
3. Nếu có lỗi constraint hoặc optimistic locking, flush có thể phát sinh exception.
4. Không nên tự ý flush nếu không muốn ghi thay đổi đang chờ.
5. Dữ liệu được đọc lại vẫn chịu transaction isolation.

Bởi vậy, hãy xác định rõ vì sao cần dữ liệu mới ngay, thay vì thêm `flush()` và `refresh()` sau mỗi setter.

## 5. Phân biệt refresh, find, flush, clear, detach và merge

| API | Mục đích | Hệ quả đối với instance Java |
| --- | --- | --- |
| `find(Entity.class, id)` | Tìm entity theo identity | Có thể trả object managed đang có mà không query lại |
| `refresh(entity)` | Nạp lại state persistent từ DB | **Cập nhật chính object managed**, giữ reference |
| `flush()` | Đồng bộ thay đổi persistent đang chờ xuống DB | Không tự đọc lại mọi giá trị DB mới |
| `clear()` | Detach tất cả managed entities của context | Các object cũ vẫn trong RAM nhưng không còn managed |
| `detach(entity)` | Detach một entity cụ thể | Object ngừng được context theo dõi |
| `merge(entity)` | Sao chép source state sang managed counterpart | Nguồn detached vẫn detached; dùng instance trả về |
| `remove(entity)` | Đánh dấu entity để xóa | Thực thi vòng đời remove, không phải reload |
| `lock(entity, mode)` | Áp dụng lock mode theo quy tắc JPA | Không mặc nhiên đọc lại toàn entity như refresh |

### 5.1. find hai lần không bảo đảm SELECT hai lần

~~~java
Product a = em.find(Product.class, id);
Product b = em.find(Product.class, id);

System.out.println(a == b); // Thường là true.
~~~

Trong một persistence context, Hibernate thường duy trì một managed instance duy nhất cho identity đó. Gọi lại find thường không đủ để làm mới các field.

### 5.2. clear rồi find khác refresh

~~~java
Product oldRef = em.find(Product.class, id);

em.clear();

Product freshRef = em.find(Product.class, id);
~~~

`oldRef` vẫn tồn tại trong RAM nhưng đã detached. `freshRef` là managed instance phù hợp trong context hiện tại.

Với:

~~~java
Product ref = em.find(Product.class, id);
em.refresh(ref);
~~~

`ref` vẫn là cùng object managed, chỉ có state persistent được nạp lại.

**Cẩn trọng:** `clear()` detach *mọi* entity và có thể khiến những thay đổi chưa flush không còn được đồng bộ. Refresh thường có phạm vi đối tượng nhỏ hơn, trừ khi khai báo cascade REFRESH tới association.

### 5.3. merge và refresh đi ngược hướng

~~~text
merge(detached):
    Java source detached  →  Java managed target
                              (sau đó flush tới DB)

refresh(managed):
    Database row          →  chính Java managed entity đó
~~~

`merge()` giúp đưa trạng thái từ object nguồn detached vào context; `refresh()` đưa trạng thái từ database về một object đã managed. Đừng dùng refresh để reattach.

## 6. Điều kiện: phải là entity managed trong đúng EntityManager

~~~java
Product product = em.find(Product.class, id);

System.out.println(em.contains(product)); // true
em.refresh(product);
~~~

Đối tượng truyền vào phải được quản lý **bởi EntityManager đó**, không chỉ có ID khớp.

### 6.1. Detached entity không được refresh như managed

~~~java
Product product = em.find(Product.class, id);
em.detach(product);

// Không dùng như một thao tác reattach:
em.refresh(product);
~~~

Theo hợp đồng JPA, refresh một entity không managed có thể ném `IllegalArgumentException`. Nó không tự gắn lại object detached.

Để lấy phiên bản hiện hành có thể:

~~~java
Product managed = em.find(Product.class, id);

if (managed == null) {
    throw new IllegalArgumentException("Không tìm thấy sản phẩm");
}

em.refresh(managed);
~~~

Trong thực tế, nếu `find()` vừa nạp object từ DB trong context mới thì refresh ngay lập tức có thể không cần; ví dụ chủ yếu cho thấy cần dùng managed reference.

### 6.2. Đối tượng dựng từ request JSON không tự managed

~~~java
Product fromRequest = ...; // Object Java do JSON mapper tạo.
// em.refresh(fromRequest); // Không bảo đảm hợp lệ.
~~~

Có ID không đồng nghĩa được JPA quản lý. Đối với API cập nhật, thường nên nhận DTO, lấy entity managed bằng repository/`find()` và áp dụng các field được phép sửa.

### 6.3. Không dùng refresh để hoàn tác remove

~~~java
Product product = em.find(Product.class, id);
em.remove(product);
// em.refresh(product); // Không phải cơ chế undo remove.
~~~

Entity đã chuyển sang trạng thái removed. Nếu muốn bỏ một thao tác xóa chưa commit, hãy thiết kế rollback/transaction thích hợp; nếu khôi phục bản ghi soft-deleted, dùng thao tác nghiệp vụ restore riêng.

### 6.4. Hàng không còn tồn tại

Nếu row bị transaction khác xóa và phép refresh nhìn thấy việc xóa, provider có thể ném `EntityNotFoundException` hoặc persistence exception tương ứng. Refresh không biến một hàng đã xóa thành entity mới.

## 7. Transaction isolation: refresh có thật sự thấy dữ liệu mới?

“Đọc từ DB” không bảo đảm bạn nhìn thấy bản cập nhật mới nhất của mọi transaction. Câu SELECT mà Hibernate thực hiện vẫn chịu isolation, MVCC, lock và phạm vi transaction.

### 7.1. READ COMMITTED

Ở nhiều database với `READ COMMITTED`, một SELECT mới có thể thấy dữ liệu đã commit trước khi câu lệnh bắt đầu:

~~~text
Transaction A: đọc stock=100
Transaction B: UPDATE stock=80; COMMIT
Transaction A: refresh(item)
Transaction A: có thể đọc stock=80
~~~

Cần chú ý: nếu B chưa commit, A thường không thấy giá trị chưa commit dưới READ COMMITTED. Kết quả còn phụ thuộc DB và việc transaction A có lock/xử lý khác hay không.

### 7.2. REPEATABLE READ và snapshot isolation

Ở nhiều hệ thống dùng snapshot hoặc isolation cao hơn:

~~~text
A: BEGIN, snapshot chứa stock=100
A: SELECT stock=100
B: UPDATE stock=80; COMMIT
A: refresh(item)
A: có thể vẫn thấy stock=100 trong snapshot cũ
~~~

Do đó gọi refresh nhiều lần **không tự phá vỡ snapshot**. PostgreSQL và MySQL/InnoDB có chi tiết MVCC/locking khác nhau, nên phải hiểu isolation của database đang vận hành.

### 7.3. Khi nào cần transaction mới?

Nếu mục tiêu là đọc dữ liệu mà transaction khác đã commit nhưng transaction hiện tại giữ snapshot cũ, có thể cần kết thúc transaction A và đọc ở transaction mới, nếu nghiệp vụ cho phép. Không được tự ý commit một transaction đang thực hiện nhiều thay đổi cần tính nguyên tử chỉ để “làm refresh hoạt động”.

### 7.4. Refresh không giải quyết race condition

Ngay sau khi refresh đọc stock=80, transaction khác vẫn có thể cập nhật stock=70. Nếu dùng stock để quyết định xuất kho, chuyển tiền hoặc thay đổi tồn kho, cần concurrency control, không chỉ refresh.

Các biện pháp có thể gồm `@Version`, pessimistic lock khi phù hợp, SQL UPDATE có điều kiện, ràng buộc database, transaction isolation và retry theo nghiệp vụ.

## 8. refresh và optimistic locking với @Version

Một entity versioned:

~~~java
@Version
private long version;
~~~

Hibernate dùng version trong SQL cập nhật để phát hiện xung đột. Khi refresh đọc lại trạng thái persistent, giá trị version của managed entity cũng có thể được cập nhật theo DB.

Giả sử:

1. Request A tải version 3.
2. Request B cập nhật hàng và commit version 4.
3. Request A có sửa đổi local chưa flush.
4. A gọi refresh và thấy version 4, đồng thời sửa đổi local của A có thể bị ghi đè.

Nếu A muốn phát hiện xung đột của thao tác sửa version 3, việc refresh để “né lỗi” là sai ngữ nghĩa. Hành vi đúng thường là để optimistic locking báo `OptimisticLockException` hoặc lỗi tương ứng khi flush/commit, rollback transaction và quyết định cách xử lý conflict.

### 8.1. Không dùng refresh thay cho retry/merge nghiệp vụ

`@Version` phát hiện một số lost updates, nhưng không tự hòa giải dữ liệu. Refresh cũng không biết field nào là nguồn chân lý. Nếu người dùng đã sửa form dựa trên state cũ, cần giải quyết conflict bằng UI/service, thay vì refresh rồi tự động ghi đè hoặc bỏ sửa đổi.

### 8.2. Refresh với lock mode

JPA có overload:

~~~java
em.refresh(product, LockModeType.PESSIMISTIC_WRITE);
~~~

Nó yêu cầu refresh cùng một lock mode cụ thể, nếu transaction/database hỗ trợ. Các overload khác nhận map hints, ví dụ lock timeout của JPA/Jakarta:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 1000
);

em.refresh(product, LockModeType.PESSIMISTIC_WRITE, hints);
~~~

Không phải mọi driver/database đều tôn trọng mọi hint hoặc timeout. Pessimistic locking có thể tăng lock wait, deadlock và giảm throughput; chỉ dùng khi business cần.

## 9. refresh và quan hệ entity: cascade REFRESH

Giả sử `Order` tham chiếu `Customer` và có các dòng hàng:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Khi gọi:

~~~java
Order order = em.find(Order.class, orderId);
em.refresh(order);
~~~

ta đang refresh state của **Order**. Không nên mặc định mọi Customer, OrderLine, Product hoặc các entity liên quan đều được refresh đệ quy chỉ vì có tham chiếu Java.

### 9.1. CascadeType.REFRESH

JPA hỗ trợ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REFRESH
)
private List<OrderLine> lines;
~~~

Hoặc:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
~~~

`CascadeType.ALL` cũng bao gồm REFRESH. Khi refresh Order, JPA/Hibernate có thể lan truyền refresh sang các entity đích theo cấu hình cascade và trạng thái association.

### 9.2. Cascade có thể làm mất thay đổi local của child

~~~java
Order managedOrder = em.find(Order.class, orderId);
OrderLine line = managedOrder.getLines().get(0);

line.setQuantity(3); // Chưa flush.

em.refresh(managedOrder);
~~~

Nếu association cấu hình cascade REFRESH và child phù hợp để refresh, sửa đổi `quantity = 3` có thể bị ghi đè bằng dữ liệu DB. Điều này thường ngoài mong đợi.

Không gắn `CascadeType.ALL` lên mọi relation chỉ vì tiện. Với `@ManyToOne` tham chiếu aggregate độc lập, cascade PERSIST/REMOVE có thể còn nguy hiểm hơn, vì xóa entity hiện tại có thể lan sang entity dùng chung.

### 9.3. Không đảm bảo một SELECT duy nhất

Refresh một graph lớn có thể dẫn tới nhiều SQL và khởi tạo/tải những thành phần liên quan theo mapping/provider. Nó không nhất thiết là một SELECT duy nhất hoặc “refresh tất cả liên kết sâu vô hạn”. Khi cần cập nhật một phần graph, nên chủ động chọn entity hoặc query cụ thể.

## 10. Trường hợp nên dùng: trigger và cột database-generated

Một trong các use case có ích nhất của refresh là khi database tạo hoặc điều chỉnh giá trị qua trigger/default/generated column.

Giả sử:

~~~sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    tax_amount NUMERIC(19, 2),
    updated_at TIMESTAMP
);
~~~

Database có trigger tính `tax_amount` khi `amount` thay đổi. Entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(
        name = "tax_amount",
        precision = 19,
        scale = 2,
        insertable = false,
        updatable = false
    )
    private BigDecimal taxAmount;

    protected Invoice() {}

    public void updateAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getTaxAmount() {
        return taxAmount;
    }
}
~~~

Trong transaction:

~~~java
Invoice invoice = em.find(Invoice.class, invoiceId);

invoice.updateAmount(new BigDecimal("250000.00"));

em.flush();          // UPDATE tới DB; trigger tính tax_amount.
em.refresh(invoice); // Nạp lại tax_amount.

System.out.println(invoice.getTaxAmount());
~~~

`insertable = false, updatable = false` chỉ nói Hibernate không gửi giá trị `taxAmount` trong INSERT/UPDATE cho mapping đó; field vẫn là persistent và có thể được đọc từ DB.

### 10.1. @Generated có thể phù hợp hơn

Nếu cột luôn do DB tạo ra, Hibernate có cơ chế mapping generated value như `@Generated` theo các event/phiên bản phù hợp. Với mapping đúng, provider có thể chủ động lấy giá trị mới mà không cần viết refresh trong mọi service.

Cần đánh giá:

- Cột được tạo ở INSERT, UPDATE hay cả hai?
- Giá trị có cần ngay trước commit không?
- Hibernate version và dialect có hỗ trợ đọc giá trị generated hiệu quả không?
- Nếu không cần giá trị ngay, có thể chỉ đọc ở transaction khác sau commit không?

Refresh là công cụ, không phải bắt buộc mỗi khi database có trigger.

## 11. Native SQL và JPQL bulk DML có thể làm context bị cũ

### 11.1. Native SQL

~~~java
Product product = em.find(Product.class, productId);

em.createNativeQuery("""
    UPDATE products
    SET quantity = quantity + 5
    WHERE id = :id
    """)
    .setParameter("id", productId)
    .executeUpdate();

em.refresh(product);
~~~

Nếu native UPDATE thay đổi row nhưng managed object chưa biết, refresh đọc lại state. Tuy nhiên, nếu có những thay đổi local khác chưa flush, refresh có thể ghi đè chúng.

### 11.2. JPQL bulk UPDATE

~~~java
Product product = em.find(Product.class, productId);

em.createQuery("""
    UPDATE Product p
    SET p.quantity = p.quantity + 5
    WHERE p.id = :id
    """)
    .setParameter("id", productId)
    .executeUpdate();

em.refresh(product);
~~~

JPQL bulk DML thao tác trực tiếp trên tập hàng và không cập nhật mọi managed object tương ứng như khi sửa Java field. Với một entity cần tiếp tục dùng ngay, refresh có thể hợp lý. Với hàng nghìn entity, refresh từng object có thể quá tốn SQL; cân nhắc `flush()`/`clear()` và tổ chức transaction phù hợp.

### 11.3. Bulk DELETE hoặc native DELETE

Nếu SQL đã xóa hàng mà entity managed đang đại diện, `refresh()` không phải cách biến object thành detached/removed hợp lệ. Nó có thể báo lỗi vì hàng không tồn tại. Hãy thiết kế chiến lược đồng bộ context, transaction và xử lý xóa tương ứng.

## 12. refresh và các tầng cache

Hibernate có nhiều tầng dữ liệu có thể giữ state:

1. **Persistence context (first-level cache)**: mỗi `Session`/`EntityManager` quản lý các object trong scope của nó.
2. **Second-level cache**: tùy cấu hình, chia sẻ cache entity/collection giữa các context.
3. **Query cache**: tùy cấu hình, cache kết quả truy vấn.
4. **Cache ngoài Hibernate**: Redis, response cache, CDN, cache trong các service khác.

`refresh()` được dùng để lấy lại state của một managed entity từ database thay vì chấp nhận snapshot sẵn có trong first-level cache. Nhưng **không phải lệnh vô hiệu hóa toàn bộ các tầng cache**.

### 12.1. Thay đổi bởi hệ thống ngoài Hibernate

Nếu một batch job sửa dữ liệu bằng SQL trực tiếp, second-level cache của ứng dụng có thể vẫn giữ state cũ nếu không có cách invalidation phù hợp. Refresh một entity cụ thể có thể đọc lại nó, nhưng không giải quyết toàn bộ consistency của những cached result khác.

Hãy hỏi:

- Entity nào bị nhiều hệ thống cùng sửa?
- Có nên cache entity đó không?
- Có cơ chế event, eviction hay TTL phù hợp không?
- Transaction hiện tại có nhìn thấy dữ liệu mới không?
- Có query cache/API cache cần cập nhật không?

Không nên gọi refresh tràn lan để vá vấn đề cache invalidation ở cấp hệ thống.

### 12.2. clear cache và refresh khác nhau

Evict second-level cache không tự xóa object managed đang tồn tại trong first-level cache. Ngược lại, refresh một object không mặc nhiên xóa mọi kết quả query/HTTP cache. Phải chọn biện pháp đúng với tầng state thực sự bị cũ.

## 13. Dùng refresh trong Spring Boot và Spring Data JPA

`JpaRepository` cung cấp `findById()`, `save()`, `saveAndFlush()` và `flush()`, nhưng không mặc định có một method `refresh(entity)` chuẩn cho mọi repository.

Cách thường gặp là inject `EntityManager` trong service hoặc custom repository.

### 13.1. Service với @Transactional

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int reloadQuantity(Long productId) {
        Product product = em.find(Product.class, productId);

        if (product == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy sản phẩm");
        }

        em.refresh(product);
        return product.getQuantity();
    }
}
~~~

`@PersistenceContext` cho phép Spring cung cấp EntityManager proxy gắn với context/transaction phù hợp. `@Transactional` xác định ranh giới giao dịch theo cấu hình Spring.

`EntityManager` tự nó không thread-safe; không tự tạo một instance rồi chia sẻ đồng thời giữa nhiều request.

### 13.2. saveAndFlush() không phải refresh()

~~~java
Product saved = repository.saveAndFlush(product);
~~~

`saveAndFlush()` yêu cầu thao tác lưu và flush theo semantics của Spring Data JPA. Nó **không đồng nghĩa** với đọc lại mọi giá trị persistent từ database vào object đã nạp.

Đặc biệt, nếu `saveAndFlush()` chọn nhánh `merge()` vì nguồn detached, giá trị trả về có thể là managed counterpart khác object đầu vào. Khi muốn refresh, hãy bảo đảm **đối tượng truyền vào refresh đang managed trong context hiện tại**, không đơn giản gọi refresh lên input từ client.

### 13.3. Custom refresher

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRefresher {

    @PersistenceContext
    private EntityManager em;

    public void refresh(Product product) {
        em.refresh(product);
    }
}
~~~

Service gọi refresher phải bảo đảm product là managed **trong chính persistence context đang được sử dụng** và có transaction phù hợp. Một entity lấy ở request trước thường đã detached.

## 14. Cần một SELECT mới hay cần refresh cùng instance?

Trường hợp giao diện chỉ cần đọc số lượng tồn kho mới nhất trong một request mới, có thể dùng projection:

~~~java
Integer quantity = em.createQuery("""
    SELECT p.quantity
    FROM Product p
    WHERE p.id = :id
    """, Integer.class)
    .setParameter("id", productId)
    .getSingleResult();
~~~

Không phải lúc nào cũng cần load Product entity rồi refresh. Projection có thể hiệu quả hơn khi chỉ cần một vài cột.

Tuy nhiên, projection **không cập nhật field** trong một managed Product đã có sẵn. Nếu trong cùng context bạn muốn tiếp tục tính toán trên chính object Product với state DB mới, refresh phù hợp hơn, sau khi bảo đảm không bỏ mất sửa đổi cần giữ.

### 14.1. Refresh sau mỗi lần tìm kiếm là lãng phí

Ví dụ:

~~~java
List<Product> products = em.createQuery("""
    SELECT p FROM Product p
    """, Product.class).getResultList();

for (Product p : products) {
    em.refresh(p);
}
~~~

Điều này có thể tạo thêm rất nhiều SELECT, một dạng N+1 reads do chính ứng dụng tạo ra. Nếu có cascade REFRESH, chi phí có thể cao hơn.

Nếu chỉ cần tập dữ liệu mới cho màn hình, hãy chọn transaction/context và query phù hợp ngay từ đầu; đừng refresh từng entity trong một danh sách lớn theo thói quen.

## 15. Những ngoại lệ cần xử lý

| Tình huống | Lỗi hoặc hành vi có thể gặp |
| --- | --- |
| Object không phải managed entity của EntityManager hiện tại | `IllegalArgumentException` |
| Ngữ cảnh cần transaction nhưng không có transaction hợp lệ | `TransactionRequiredException` |
| Hàng database đã biến mất | `EntityNotFoundException` hoặc lỗi persistence tương ứng |
| Không lấy được lock khi dùng lock mode | `PessimisticLockException` hoặc `LockTimeoutException` |
| Lỗi JDBC/driver/database khi đọc lại | Exception persistence/provider tương ứng |
| Version/locking không phù hợp | Có thể gặp optimistic locking exception trong điều kiện liên quan |

Không nên bắt mọi exception rồi tiếp tục dùng dữ liệu cũ nếu nghiệp vụ yêu cầu state mới. Nếu refresh thất bại, transaction có thể cần rollback và service phải quyết định thông báo lỗi rõ ràng.

### 15.1. TransactionRequiredException

Với transaction-scoped persistence context, refresh thường yêu cầu transaction đang hoạt động theo hợp đồng JPA. Trong Spring, dễ kiểm soát nhất là thực hiện thao tác trong service `@Transactional` phù hợp.

### 15.2. EntityNotFoundException

Nếu hàng đã bị xóa và không còn đọc được, refresh không thể tạo lại entity đó. Cần báo not-found/conflict hoặc thiết kế xử lý phù hợp; không dùng refresh như phép tạo lại.

### 15.3. Lock timeout

Các overload refresh với pessimistic lock có thể chờ lock và gặp timeout. Đây không phải connection pool timeout hoặc query timeout giống hệt trong mọi hệ thống. Cần hiểu cơ chế cụ thể của database và transaction manager.

## 16. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Gọi find thêm một lần chắc chắn đọc DB mới.” | Persistence context có thể trả managed instance hiện tại. |
| “Refresh giữ mọi sửa đổi local và chỉ bổ sung field mới.” | Refresh có thể ghi đè persistent state chưa flush. |
| “Refresh biến detached entity thành managed.” | Refresh yêu cầu entity đã managed. |
| “Refresh là commit.” | Refresh đọc state; commit xác nhận transaction. |
| “Flush và refresh giống nhau.” | Flush ghi từ context xuống DB; refresh đọc từ DB vào context. |
| “Clear và refresh như nhau.” | Clear detach toàn context; refresh cập nhật state trên cùng managed object. |
| “Refresh luôn thấy transaction khác vừa commit.” | Isolation/snapshot có thể khiến nó vẫn thấy dữ liệu cũ. |
| “Refresh sửa optimistic locking conflict.” | Nó có thể làm mất ý định sửa local; conflict cần xử lý theo nghiệp vụ. |
| “Refresh parent làm mới mọi child.” | Còn phụ thuộc cascade REFRESH, mapping và provider. |
| “Refresh xóa mọi loại cache.” | Không tự invalidated query cache, API cache hoặc cache hệ thống khác. |
| “saveAndFlush() của repository là refresh.” | Save/flush đồng bộ ghi, không tự đọc lại toàn state. |
| “Refresh miễn phí vì entity đã có trong RAM.” | Refresh thường cần đọc DB và có thể phát sinh nhiều SQL. |

## 17. Quy trình chọn refresh trong một use case thực tế

Trước khi gọi `refresh()`, xác định rõ:

1. **Entity đã managed chưa?** Kiểm tra scope, transaction, hoặc `em.contains()` khi cần.
2. **Vì sao nó có thể cũ?** Thay đổi từ trigger, native SQL, bulk JPQL, transaction khác hay một tầng cache khác?
3. **Có sửa đổi local chưa flush không?** Nếu có, refresh có thể ghi đè; cần quyết định giữ hay bỏ.
4. **Cần toàn bộ state hay chỉ một vài cột?** Projection hoặc query mới có thể rẻ và rõ hơn.
5. **Transaction isolation có cho đọc phiên bản mới không?** Snapshot cũ không thể được chữa bằng cách gọi refresh lặp.
6. **Có cascade REFRESH không?** Xem nguy cơ ghi đè child và chi phí truy vấn.
7. **Có optimistic locking/concurrency requirement không?** Refresh không thay cơ chế xử lý conflict.
8. **Có generated mapping phù hợp hơn không?** Nếu DB tự tính một trường, cân nhắc Hibernate generated value support.
9. **Có cache ngoài Hibernate không?** Refresh một object không giải quyết cache toàn hệ thống.
10. **Sau refresh, dùng object thế nào?** Tiếp tục dùng cùng managed instance trong context/transaction hiện tại.

### Ví dụ: đọc lại thuế sau trigger

~~~java
@Transactional
public BigDecimal updateAndReadTax(Long invoiceId) {
    Invoice invoice = em.find(Invoice.class, invoiceId);

    if (invoice == null) {
        throw new IllegalArgumentException("Không tìm thấy hóa đơn");
    }

    invoice.updateAmount(new BigDecimal("250000.00"));

    em.flush();
    em.refresh(invoice);

    return invoice.getTaxAmount();
}
~~~

Đoạn này giả định trigger DB tính tax khi UPDATE và mapping `Invoice` tương thích. Refresh được sử dụng đúng một chỗ sau flush vì service cần giá trị tax mới ngay, không phải dùng theo thói quen ở mọi câu lệnh.

## 18. Bài tập thực hành

### Bài 1 — Có mất thay đổi local không?

~~~java
Product p = em.find(Product.class, id);
p.rename("Tên mới");

em.refresh(p);
em.flush();
~~~

Giả sử DB vẫn có tên cũ và không có thay đổi khác. Giá trị tên sau refresh là gì? Vì sao có thể không xuất hiện SQL UPDATE cho `"Tên mới"`?

### Bài 2 — refresh hay clear + find?

~~~java
Product old = em.find(Product.class, id);
em.clear();
Product fresh = em.find(Product.class, id);
~~~

So sánh Java object identity, trạng thái managed/detached và các sửa đổi chưa flush với trường hợp gọi `em.refresh(old)` khi old vẫn managed.

### Bài 3 — Thay đổi từ transaction khác

A đọc stock=100. B cập nhật stock=80 và commit. Sau đó A gọi refresh. Hãy giải thích kết quả có thể khác nhau dưới READ COMMITTED và snapshot isolation. Nếu A cần ghi dựa trên stock, còn cần cơ chế gì để xử lý concurrency?

### Bài 4 — Cascade REFRESH

`Order.lines` được cấu hình cascade REFRESH. Một OrderLine đã được đổi quantity trong RAM nhưng chưa flush. Refresh Order có thể tác động gì đến quantity của child? Tại sao không nên bật cascade REFRESH trên mọi association?

### Bài 5 — Trigger và generated value

Trigger tự đặt `tax_amount` khi `amount` đổi. Service cần trả về taxAmount vừa tính. Vì sao `flush()` rồi `refresh()` có thể hữu ích? Khi nào nên xem xét mapping generated value?

### Bài 6 — Spring Data JPA

~~~java
Product saved = repository.saveAndFlush(incoming);
entityManager.refresh(incoming);
~~~

Giả sử `incoming` là detached, repository gọi merge và trả managed counterpart. Vì sao refresh trên `incoming` có thể lỗi? Cần dùng instance nào và transaction/context phải như thế nào?

### Bài 7 — Refresh hàng loạt

Một trang danh sách đã query 500 Product, sau đó lặp gọi refresh trên cả 500 entity. Nêu vấn đề hiệu năng và đề xuất phương án thay thế nếu API chỉ cần ID và quantity.

### Định hướng trả lời

- **Bài 1:** Refresh có thể khôi phục tên cũ từ DB và bỏ local edit chưa flush; Hibernate không còn thay đổi đó để UPDATE.
- **Bài 2:** Clear detach old và find trả managed instance mới; refresh giữ cùng object managed, nạp lại state persistent.
- **Bài 3:** READ COMMITTED có thể thấy stock=80; snapshot có thể vẫn thấy 100; cần `@Version`, lock, điều kiện UPDATE hoặc transaction design phù hợp.
- **Bài 4:** Cascade refresh có thể ghi đè thay đổi quantity chưa flush; cần giới hạn cascade theo use case.
- **Bài 5:** Flush để SQL/trigger chạy rồi refresh lấy kết quả; mapping generated value có thể giúp provider tự đọc khi được hỗ trợ.
- **Bài 6:** Incoming vẫn detached; cần managed result trong cùng EntityManager/transaction nếu muốn refresh.
- **Bài 7:** Có nguy cơ 500 SELECT bổ sung hoặc nhiều hơn; dùng projection/query thích hợp trong context mới theo nhu cầu.

---

**Ghi nhớ:** `EntityManager.refresh(entity)` **đọc lại dữ liệu persistent từ database vào chính managed entity hiện tại**. Nó không phải `flush()`, `merge()`, `clear()` hay `commit()`. Hãy dùng refresh khi cần đồng bộ state sau thay đổi từ database, đồng thời bảo vệ những sửa đổi chưa flush và hiểu giới hạn transaction isolation, cascade, optimistic locking, cache và chi phí SQL.
