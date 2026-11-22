# Xử lý quan hệ và tham chiếu sau khi context đã được làm rỗng trong ghi hàng loạt với Hibernate ORM

Khi ghi hàng chục nghìn hoặc hàng triệu entity bằng Hibernate ORM, một kỹ thuật quan trọng là **xử lý theo từng lô (*chunk*)**, định kỳ gọi `flush()` để đẩy thay đổi xuống database và `clear()` để giải phóng những managed entities đang được persistence context theo dõi. Cách này tránh việc first-level cache phình to, giảm chi phí dirty checking và giúp một tiến trình import dài không giữ toàn bộ object graph trong bộ nhớ.

Tuy nhiên, lời gọi `clear()` không chỉ “dọn bộ nhớ”. Nó **tách (detach) tất cả entity và persistent collection khỏi persistence context hiện tại**. Nếu một chunk tiếp theo cần tạo con của parent đã lưu, liên kết thêm entity vào quan hệ nhiều-nhiều, cập nhật một association hoặc xóa một child, việc tiếp tục dùng các Java object được giữ lại từ trước `clear()` có thể gây lỗi hoặc âm thầm không được ghi xuống database.

Ví dụ:

```java
Order order = new Order();
em.persist(order);

em.flush();
em.clear();

OrderLine line = new OrderLine();
line.setOrder(order); // order là object detached từ chunk trước.
em.persist(line);
```

Tình huống này cần được phân tích theo mapping cascade, ID, bên sở hữu quan hệ và trạng thái tham chiếu. Với một số mapping, Hibernate có thể lấy khóa ngoại từ ID của parent detached; với mapping khác, cascade persist có thể gây `PersistentObjectException` hoặc lỗi tương đương “detached entity passed to persist”. Dù không có exception, việc sửa `order.getLines()` sau `clear()` không làm Hibernate tự theo dõi thay đổi ấy.

**Nguyên tắc cốt lõi:** *Sau khi clear, ưu tiên giữ identifier/immutable command data, rồi lấy managed entity hoặc managed reference trong persistence context hiện tại trước khi thực hiện thay đổi quan hệ. Đừng xem object cũ là managed chỉ vì nó từng được persist.*

Bài học này giải thích sâu hành vi `flush/clear`, cơ chế định danh và reference, phía sở hữu quan hệ, cascade, collection, `merge`, `orphanRemoval`, quan hệ khóa chính chia sẻ, hiệu năng JDBC batching, transaction/concurrency, và cách tổ chức import nhiều lô an toàn.

---

## 1. Vì sao quy trình ghi hàng loạt thường cần clear?

Giả sử import 300.000 sản phẩm từ file CSV:

```java
@Transactional
public void importProducts(List<ProductRow> rows) {
    for (ProductRow row : rows) {
        Product product = new Product(
            row.code(),
            row.name()
        );
        em.persist(product);
    }
}
```

Trong một persistence context stateful, Hibernate có thể phải giữ thông tin của rất nhiều entity:

- Entity instances trong identity map.
- Loaded state hoặc dữ liệu phục vụ dirty checking.
- Action queue chờ SQL INSERT/UPDATE/DELETE.
- Collection snapshots và liên kết với các entity khác.
- Thông tin version, cascade, lifecycle.

Vì thế số object managed tăng theo số dòng import; memory và thời gian flush có thể tăng mạnh.

Một cách phổ biến là chia thành chunks:

```java
@Transactional
public void importProducts(List<ProductRow> rows) {
    int chunkSize = 50;
    int processed = 0;

    for (ProductRow row : rows) {
        em.persist(new Product(
            row.code(),
            row.name()
        ));

        processed++;

        if (processed % chunkSize == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
    em.clear();
}
```

Sau mỗi chunk, context không còn quản lý các Product của chunk trước. Đây là lợi ích cho bộ nhớ, đồng thời là **ranh giới vòng đời object** mà mọi xử lý quan hệ phải tôn trọng.

### 1.1. Flush và clear khác nhau

| Thao tác | Tác dụng chính | Không có nghĩa |
|---|---|---|
| `em.flush()` | Đồng bộ các thay đổi pending với database trong transaction | Không commit; không detach entity |
| `em.clear()` | Detach mọi managed entity trong persistence context | Không commit; không tự flush; không thay field trong object Java |
| `em.detach(entity)` | Detach một entity cụ thể theo semantics JPA | Không detach mọi entity; không xóa row |
| `em.refresh(entity)` | Nạp lại state của một entity managed từ database | Không dùng cho entity detached như một cách reattach đơn giản |
| `em.close()` | Đóng EntityManager và kết thúc persistence context | Không đồng nghĩa commit transaction trong mọi mô hình |

**Thứ tự `flush()` rồi `clear()` rất quan trọng** nếu đang có thay đổi cần lưu. Gọi `clear()` khi chưa flush có thể làm mất các insert/update/delete đang chờ của những entity bị detach.

### 1.2. Một transaction có thể gồm nhiều flush/clear

```text
BEGIN TRANSACTION
    |
    +-- persist 50 entities
    +-- flush()  -> SQL được gửi
    +-- clear()  -> entity trở thành detached
    |
    +-- persist 50 entities
    +-- flush()
    +-- clear()
    |
    +-- persist 50 entities
    +-- flush()
    +-- clear()
    |
COMMIT
```

Ba lần flush **không phải ba lần commit**. Nếu transaction cuối rollback, những câu SQL trước đó vẫn có thể bị rollback, miễn chúng nằm trong cùng transaction database phù hợp.

Nếu mỗi chunk phải commit riêng, cần transaction boundary độc lập cho từng chunk; `clear()` không tạo boundary ấy.

## 2. Managed, detached, transient và removed trong một batch

JPA mô tả các trạng thái entity thường gặp:

| Trạng thái | Ý nghĩa | Hibernate xử lý thay đổi field như thế nào? |
|---|---|---|
| **Transient** | Object mới, chưa được đưa vào persistence context | Không tự lưu |
| **Managed** | Object đang được EntityManager quản lý | Dirty checking và lifecycle áp dụng khi flush |
| **Detached** | Object từng được quản lý nhưng không còn gắn context hiện tại | Setter không tự sinh SQL |
| **Removed** | Entity managed được đánh dấu xóa | DELETE được lên lịch theo lifecycle khi flush |

Ví dụ:

```java
Product product = new Product("P-1", "Bút");
// transient

em.persist(product);
// managed

em.flush();
// managed, SQL INSERT đã được đồng bộ

em.clear();
// detached

product.rename("Bút xanh");
// chỉ đổi object Java detached; không tự UPDATE
```

### 2.1. Clear không xóa Java object

Biến `product` vẫn chứa:

- Giá trị ID đã được gán.
- Trường scalar đã có.
- Tham chiếu tới entity/collection khác.
- Dữ liệu business đã tải trong bộ nhớ.

Nhưng Hibernate **không còn theo dõi** biến này qua context vừa được clear. Cần phân biệt “đối tượng còn sống trong heap” với “đối tượng managed”.

### 2.2. Identity trong một context khác identity giữa các chunk

Trong cùng context:

```java
Product a = em.find(Product.class, id);
Product b = em.find(Product.class, id);

// Thông thường a == b.
```

Sau `clear()`:

```java
Product old = em.find(Product.class, id);

em.clear();

Product fresh = em.find(Product.class, id);

// old và fresh có thể là hai Java objects khác nhau
// nhưng cùng đại diện một database identity.
```

`old == fresh` không phải phép so sánh identity database đáng tin giữa các persistence contexts. Khi thiết kế map/set/equals/hashCode, không lấy object reference equality làm khóa định danh nghiệp vụ xuyên chunk.

## 3. Vấn đề điển hình: parent được tạo ở chunk trước

Giả sử import bảng Order và OrderLine:

```text
orders
+---------+-------------+
| id      | order_code  |
+---------+-------------+
| 100     | O-001       |
+---------+-------------+

order_lines
+---------+----------+---------+
| id      | order_id | qty     |
+---------+----------+---------+
| 200     | 100      | 2       |
+---------+----------+---------+
```

Quan hệ:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderCode;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {}

    public Order(String orderCode) {
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }
}
```

Child:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(int quantity) {
        this.quantity = quantity;
    }

    public void setOrder(Order order) {
        this.order = order;
    }
}
```

Ở mapping này **`OrderLine.order` là owning side** vì nó chứa `@JoinColumn(name="order_id")`. Collection `Order.lines` là inverse side qua `mappedBy`.

### 3.1. Khi parent và child cùng chunk

```java
Order order = new Order("O-001");
OrderLine line = new OrderLine(2);

order.addLine(line);

em.persist(order);
em.persist(line);

em.flush();
em.clear();
```

Các entity vẫn managed trong lúc mapping và persist; Hibernate có thể sắp thứ tự INSERT phù hợp ràng buộc FK. `OrderLine.order` trỏ vào một managed Order đã được persist.

Nếu cấu hình cascade persist từ Order sang lines:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
```

thì có thể chỉ cần `em.persist(order)` cho aggregate mới đã gắn child đúng, thay vì persist child riêng. Cascade có tác dụng theo mapping **khi nguồn đang trong lifecycle operation phù hợp**, không phải bất kỳ lúc nào có object reference.

### 3.2. Khi parent đã bị detach trước khi tạo child

```java
Order order = new Order("O-001");
em.persist(order);

em.flush();
em.clear(); // order bây giờ detached.

OrderLine line = new OrderLine(2);
line.setOrder(order);

em.persist(line);
```

Đây là pattern nên tránh như một quy ước chung vì:

- `order` không còn managed.
- Nếu child-to-parent có `cascade=PERSIST` hoặc `ALL`, Hibernate có thể cố persist một parent detached và báo lỗi.
- Nếu không cascade, một số mapping/version có thể ghi FK bằng ID của detached parent, nhưng không được coi là cách portable và dễ bảo trì để thao tác quan hệ sau clear.
- Nếu code tiếp tục gọi `order.addLine(line)`, thay đổi collection detached không được Hibernate tự phát hiện.

**Cách rõ ràng hơn: giữ `orderId` và lấy reference trong context hiện tại.**

## 4. Giữ ID, lấy managed reference trong chunk mới

Ví dụ:

```java
Order order = new Order("O-001");
em.persist(order);

em.flush();

Long orderId = order.getId();

em.clear();

// Chunk sau.
Order managedOrderRef = em.getReference(
    Order.class,
    orderId
);

OrderLine line = new OrderLine(2);
line.setOrder(managedOrderRef);

em.persist(line);

em.flush();
em.clear();
```

Ý nghĩa:

1. `orderId` là giá trị định danh thuần Java, không phụ thuộc managed state.
2. `getReference(Order.class, orderId)` trả một reference liên kết với **EntityManager hiện tại**, thường có thể là proxy lazy.
3. `line.order` trỏ tới reference thuộc context đang thực thi.
4. Khi persist line, Hibernate có thể dùng identifier của order để ghi `order_id`.
5. Không cần tải toàn bộ Order và lines chỉ để gán FK.

### 4.1. Sơ đồ vòng đời

```text
Chunk A
    Order Java object A (managed)
               |
               +-- persist
               +-- flush -> orders.id = 100
               |
            clear()
               |
               v
    Order object A (detached)       giữ Long orderId = 100
                                            |
                                            v
Chunk B
                                    getReference(Order, 100)
                                            |
                                            v
                                    Order reference B (managed)
                                            |
                                            v
                                    line.setOrder(reference B)
                                            |
                                            v
                                    persist(line)
                                            |
                                            v
                                    SQL INSERT order_id = 100
```

**Thứ nên chuyển giữa chunks là ID/DTO/command data**, không phải proxy cũ như thể nó còn managed mãi.

### 4.2. getReference không nhất thiết chạy SELECT

`EntityManager.getReference()` có mục đích lấy một entity reference theo identifier; trong nhiều tình huống Hibernate tạo proxy hoặc trả entity đã managed mà không truy vấn ngay.

```java
Order ref = em.getReference(Order.class, orderId);

OrderLine line = new OrderLine(2);
line.setOrder(ref);
em.persist(line);
```

Khi chỉ cần FK, Hibernate thường không cần đọc các trường của Order. Điều này đặc biệt hữu ích khi import hàng triệu child.

Tuy nhiên, **không được hứa rằng mọi provider/version/mapping luôn zero-SELECT**. Nếu Hibernate cần initialize reference (ví dụ code gọi một property khác ID hoặc yêu cầu proxy không được đáp ứng), có thể chạy SELECT.

### 4.3. getReference không phải kiểm tra tồn tại

`getReference(Order.class, 999999L)` có thể trả proxy mà chưa xác nhận database có row ấy. Lỗi có thể đến sau:

- Khi truy cập thuộc tính khiến proxy initialize.
- Khi INSERT child và FK constraint bị từ chối.
- Khi flush/commit, tùy mapping/driver.
- Hoặc sớm hơn nếu provider chọn cách kiểm tra tồn tại.

Vì vậy:

- Dùng `getReference` khi **ID đáng tin cậy và chỉ cần tham chiếu**.
- Dùng `find` hoặc query có điều kiện khi **nghiệp vụ cần xác minh thực thể tồn tại, thuộc tenant đúng và có trạng thái hợp lệ**.

Không sử dụng `getReference` như một API authorization.

## 5. getReference, find, merge, persist: chọn đúng mục đích

| API | Tác dụng | Dùng tốt khi | Cảnh báo |
|---|---|---|---|
| `em.getReference(T.class, id)` | Lấy reference quản lý bởi context hiện tại; có thể lazy | Cần gán FK tới entity đã biết ID | Không mặc định xác minh tồn tại/tenant |
| `em.find(T.class, id)` | Tìm và trả entity managed hoặc null | Cần đọc/kiểm tra trạng thái parent | Có thể SELECT và tải dữ liệu dư |
| `em.persist(newEntity)` | Đưa entity mới vào managed lifecycle | Tạo row mới | Cascade PERSIST tới detached association có thể lỗi |
| `em.merge(detached)` | Copy state từ detached sang managed instance mới/đang có | Hợp nhất detached state có chủ đích | Không reattach chính object đầu vào; có rủi ro overwrite |
| `em.refresh(managed)` | Tải lại state của managed instance | Cần cập nhật state cũ trong context | Không phải giải pháp refresh detached trực tiếp |
| `em.clear()` | Detach tất cả managed entities | Giảm kích thước context theo chunk | Không flush, không commit |

### 5.1. Quy tắc thực dụng

- **Chỉ cần liên kết foreign key**: `getReference`.
- **Cần kiểm tra hoặc đọc parent**: `find` hoặc query projection có điều kiện.
- **Cần sửa một entity đã tồn tại**: tải managed entity rồi sửa; không sửa object detached cũ.
- **Thực sự cần merge state detached**: `merge` và dùng **đối tượng kết quả trả về** để làm tiếp.
- **Tạo child mới**: persist child, không gọi persist lại parent cũ chỉ để “gắn lại”.

## 6. Vì sao sửa object detached sau clear không tạo UPDATE?

Ví dụ:

```java
Order order = em.find(Order.class, orderId);

em.flush();
em.clear();

order.changeStatus("CLOSED");

// Không có SQL UPDATE tự động cho order detached.
```

`clear()` đã chấm dứt việc theo dõi object `order`. Một lần `em.flush()` sau đó không “quét heap Java” để tìm thay đổi của nó.

Cách đúng nếu cần cập nhật:

```java
em.clear();

Order managed = em.find(Order.class, orderId);

if (managed == null) {
    throw new OrderNotFoundException(orderId);
}

managed.changeStatus("CLOSED");

em.flush();
```

`Order.changeStatus` và `OrderNotFoundException` là API ứng dụng minh họa.

### 6.1. Đặc biệt nguy hiểm khi sửa collection detached

```java
Order order = em.find(Order.class, orderId);

em.flush();
em.clear();

order.getLines().add(new OrderLine(2));

// Không có lý do để Hibernate tự phát hiện thay đổi này.
```

Nếu collection chưa initialized, lời gọi `getLines()`/`add()` có thể còn gặp `LazyInitializationException`. Nếu collection đã initialized thì Java list có thể đổi, nhưng nó không trở thành managed collection của context mới.

Đừng dùng hành vi “thêm thành công vào List” làm bằng chứng association đã được persist.

## 7. Owning side là điều quyết định foreign key

Với bidirectional one-to-many/many-to-one:

```java
@Entity
public class Order {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
public class OrderLine {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private Order order;
}
```

**Owning side là `OrderLine.order`**; update FK dựa trên bên này.

### 7.1. Chỉ thêm vào inverse collection là chưa đủ

```java
Order managedOrder = em.find(Order.class, orderId);
OrderLine newLine = new OrderLine(2);

managedOrder.getLines().add(newLine);

em.persist(newLine);
```

Nếu không gọi `newLine.setOrder(managedOrder)`, FK `order_id` có thể null hoặc không đúng, vì association owning side chưa được thiết lập.

### 7.2. Helper đồng bộ hai chiều

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this);
}

public void removeLine(OrderLine line) {
    lines.remove(line);
    line.setOrder(null);
}
```

Helper có ích **khi các entity và collection tham gia đang managed**, nhất là trong một aggregate operation.

Nhưng khi chỉ chèn hàng triệu child sau clear, không nhất thiết phải tải collection inverse rồi gọi helper trên từng dòng. Có thể tạo child và gán managed parent reference trên owning side, vì mục tiêu chính là ghi FK:

```java
Order parentRef = em.getReference(Order.class, orderId);

OrderLine child = new OrderLine(2);
child.setOrder(parentRef);

em.persist(child);
```

Trong context hiện tại, inverse collection `Order.lines` có thể chưa được tải hoặc chưa phản ánh element mới cho đến khi được đồng bộ/refresh/reload thích hợp. Vì vậy, đừng lập tức dựa vào `parentRef.getLines().size()` như một kết quả chắc chắn nếu bạn không chủ động duy trì hai phía trong memory.

### 7.3. Chọn mô hình theo mục đích

- **Domain aggregate update trong một transaction**: helper hai chiều giữ object graph nhất quán.
- **Import dữ liệu khối lượng lớn**: gán owning-side reference bằng ID, tránh tải/giữ inverse collection khổng lồ.
- **Tầng đọc**: query/DTO riêng để đọc quan hệ sau khi ghi; không trông đợi collection detached tự được làm mới.

## 8. Cascade PERSIST và lỗi "detached entity passed to persist"

Một lỗi phổ biến xuất hiện khi code thêm cascade tùy tiện:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.PERSIST
)
private Order order;
```

Sau đó:

```java
Order oldOrder = previouslySavedAndClearedOrder;

OrderLine line = new OrderLine(2);
line.setOrder(oldOrder);

em.persist(line);
```

Vì `persist(line)` có thể cascade PERSIST lên `oldOrder`, Hibernate gặp một entity mang identity đã tồn tại và đang detached. Nó có thể báo:

```text
org.hibernate.PersistentObjectException:
    detached entity passed to persist: ...Order
```

hoặc một `PersistenceException` liên quan tùy API và version.

### 8.1. Không dùng CascadeType.ALL theo phản xạ trên @ManyToOne

`CascadeType.ALL` bao gồm `PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH`. Nếu child là OrderLine và parent là Order:

- Persist child không nhất thiết nên persist Order lần nữa.
- Remove child gần như chắc chắn **không nên tự remove Order** có nhiều lines.
- Merge child không nhất thiết nên copy toàn bộ detached parent state.

Với quan hệ từ child tới parent/reference data, nhiều ứng dụng **không cấu hình cascade** hoặc cấu hình rất chọn lọc.

### 8.2. Cascade không đồng nghĩa FK

Gán:

```java
line.setOrder(parentRef);
```

đã tạo association từ child tới parent theo mapping. Cascade chỉ điều khiển **lan truyền lifecycle operation**, không phải điều kiện bắt buộc để Hibernate biết FK.

### 8.3. Phân biệt parent mới và parent có sẵn

- Nếu parent và child đều mới, có thể persist parent trước rồi child; hoặc cấu hình cascade từ aggregate root phù hợp.
- Nếu parent đã tồn tại, chunk sau nên tham chiếu bằng managed `getReference`/`find`, không cascade persist từ child lên parent detached.

## 9. Merge không phải "gắn lại object cũ"

`merge` thường gây hiểu nhầm khi dùng để xử lý detached parent:

```java
Order detached = savedInPreviousChunk;

Order managed = em.merge(detached);
```

Với JPA, `merge` **copy state** từ detached object vào một managed instance; **đối tượng truyền vào vẫn detached**.

```java
Order merged = em.merge(detached);

System.out.println(detached == merged);
// Không được giả định true.
```

### 9.1. Vì sao merge chỉ để lấy FK thường là lựa chọn kém?

Nếu bạn chỉ cần `order_id` cho một child mới, `merge(detachedOrder)` có thể:

- Đòi hỏi SELECT hoặc kiểm tra state.
- Copy field cũ, có thể ghi đè thay đổi mới hơn.
- Lan cascade MERGE qua graph lớn.
- Làm tốn memory và phát sinh SQL ngoài ý định.
- Khó phân biệt dữ liệu nhập cũ và dữ liệu cập nhật hợp lệ.

`getReference(Order.class, orderId)` thể hiện ý định “chỉ cần reference” tốt hơn.

### 9.2. Khi nào merge có thể hợp lý?

Khi use case **thật sự cần hợp nhất state detached** do client/batch lưu lại, đã xác định rõ:

- Những field nào được phép đổi.
- Optimistic locking và version check.
- Các association nào cascade MERGE.
- Cách xử lý object graph cũ hoặc stale.
- Quy tắc không overwrite state mới hơn.

Với application update thông thường, pattern **load managed aggregate → áp command** thường rõ hơn merge một graph lớn.

### 9.3. Nếu đã merge, tiếp tục dùng kết quả

```java
Order managed = em.merge(detachedOrder);

managed.changeStatus("CONFIRMED");

OrderLine child = new OrderLine(2);
child.setOrder(managed);
em.persist(child);
```

Không tiếp tục sửa `detachedOrder` rồi kỳ vọng dirty checking đồng bộ các sửa đổi ấy.

## 10. Tạo quan hệ child → parent qua ID trong nhiều chunks

Một import lớn thường có hai tập dữ liệu:

```text
orders.csv
    external_order_key, order_code

order_lines.csv
    external_order_key, product_code, quantity
```

Parent và child có thể đến ở những chunk khác nhau. Nên có cấu trúc map từ business key bên ngoài sang persisted ID:

```java
Map<String, Long> orderIdByExternalKey =
    new HashMap<>();
```

Khi import parent:

```java
Order order = new Order(row.orderCode());

em.persist(order);

// ID sẵn có khi generator cấp; cần xét strategy.
em.flush();

orderIdByExternalKey.put(
    row.externalOrderKey(),
    order.getId()
);

em.clear();
```

Khi import child:

```java
Long orderId =
    orderIdByExternalKey.get(row.externalOrderKey());

if (orderId == null) {
    throw new IllegalStateException(
        "Unknown external order key"
    );
}

Order parentRef =
    em.getReference(Order.class, orderId);

OrderLine line = new OrderLine(row.quantity());
line.setOrder(parentRef);
em.persist(line);
```

### 10.1. Lưu map ID có thể cũng quá lớn

Nếu hàng triệu parent, map trong heap cũng có thể quá lớn dù context đã clear. Có thể:

- Lưu mapping external key → generated ID vào staging table.
- Dùng natural/business key có unique constraint và query theo chunk.
- Sắp xếp input để parent và child cùng nhóm.
- Dùng external ID làm identifier nếu domain và schema cho phép.
- Persist mapping ở một kho trung gian bền vững để resume job.

**Clear chỉ giải phóng persistence context; nó không tự giải phóng mọi collection/map do ứng dụng giữ.**

### 10.2. Đừng lưu entity trong map thay cho ID

Sai về quản lý state:

```java
Map<String, Order> parentByKey = new HashMap<>();

parentByKey.put(externalKey, persistedOrder);

em.clear();

// Các Order trong map đã detached.
```

Map đó giữ object graph cũ trong memory và tạo rủi ro sử dụng detached reference ở chunk tiếp theo.

Thay bằng:

```java
Map<String, Long> parentIdByKey = new HashMap<>();
```

hoặc cấu trúc staging bền vững.

## 11. Ví dụ đầy đủ: import parent trước, child sau

Một service minh họa dùng JPA và Spring transaction. Giả định các record import đã được validate; `Order` dùng ID được cấp qua sequence và `OrderLine` có constructor/setter như ở phần trước.

```java
@Service
public class OrderImportService {

    private static final int CHUNK_SIZE = 100;

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void importData(
            List<OrderInput> orders,
            List<OrderLineInput> lines) {

        Map<String, Long> orderIds = new HashMap<>();

        int count = 0;

        // Pha 1: tạo parent.
        for (OrderInput input : orders) {
            Order order = new Order(input.orderCode());
            em.persist(order);

            // Với generator phù hợp, ID thường sẵn ở đây.
            // Nếu không, phải flush trước khi dùng ID.
            Long id = order.getId();

            if (id == null) {
                em.flush();
                id = order.getId();
            }

            orderIds.put(input.externalKey(), id);

            count++;

            if (count % CHUNK_SIZE == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        em.clear();

        // Pha 2: tạo child bằng ID, không dùng Order cũ.
        count = 0;

        for (OrderLineInput input : lines) {
            Long parentId =
                orderIds.get(input.externalOrderKey());

            if (parentId == null) {
                throw new IllegalArgumentException(
                    "Missing parent: "
                        + input.externalOrderKey()
                );
            }

            Order parentRef =
                em.getReference(Order.class, parentId);

            OrderLine line = new OrderLine(input.quantity());
            line.setOrder(parentRef);

            em.persist(line);

            count++;

            if (count % CHUNK_SIZE == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        em.clear();
    }
}
```

Các record ứng dụng:

```java
public record OrderInput(
    String externalKey,
    String orderCode
) {}

public record OrderLineInput(
    String externalOrderKey,
    int quantity
) {}
```

### 11.1. Ví dụ này minh họa nguyên tắc, không phải import engine hoàn chỉnh

Trong production, cần thêm:

- Kiểm tra dữ liệu trùng external key và order code.
- Chính sách retry/idempotency.
- Staging cho tập dữ liệu rất lớn.
- Giới hạn memory và input stream.
- Chính sách transaction theo chunk hoặc toàn bộ.
- Kiểm tra tenant/authorization.
- Error reporting theo row.
- FK/unique constraint và cleanup khi lỗi.
- Identifier strategy của entity.

Nếu import toàn bộ trong một transaction, số lượng lock và undo/WAL có thể lớn dù memory context đã được kiểm soát.

### 11.2. Vì sao giai đoạn parent phải flush trước clear?

Để đảm bảo các INSERT parent pending đã được gửi xuống DB trước khi dùng context mới cho child, đồng thời giữ ID đã được cấp. `flush()` không commit, nhưng parent và child có thể tham chiếu nhau trong cùng database transaction qua FK đúng.

### 11.3. Vì sao không gọi parent.getLines().add(line)?

Nếu mục tiêu của import là ghi FK trên `order_lines.order_id`, chỉ cần gán owning side. Gọi `parentRef.getLines()` có thể initialize một collection rất lớn, làm mất lợi ích của batch.

Nếu yêu cầu nghiệp vụ cần kiểm tra aggregate invariant dựa trên toàn bộ lines, không được bỏ qua bằng thủ thuật FK; cần một thiết kế tổng hợp khác (ví dụ staging/aggregate validation trước persist).

## 12. Gán quan hệ trên phía sở hữu trong chunk mới

Sau `clear()`, nếu cập nhật association của **entity đang tồn tại**, không thể chỉ sửa object detached.

Sai:

```java
OrderLine detachedLine = savedEarlier;

em.clear();

Order other = em.getReference(Order.class, otherOrderId);
detachedLine.setOrder(other);

// Không có managed dirty checking cho detachedLine.
```

Đúng:

```java
OrderLine managedLine = em.find(
    OrderLine.class,
    lineId
);

Order newParentRef = em.getReference(
    Order.class,
    otherOrderId
);

managedLine.setOrder(newParentRef);

em.flush();
```

Trong context hiện tại, `managedLine` là entity được theo dõi. Khi flush, thay đổi FK có thể được chuyển thành UPDATE với điều kiện và version semantics phù hợp.

### 12.1. Cẩn thận với object graph hai chiều

Nếu trong context hiện tại đã có cả `oldOrder` và `newOrder` managed, đổi `line.order` mà không cập nhật collections tương ứng có thể khiến object graph Java tạm thời không nhất quán.

Với aggregate manipulation cần business method đồng bộ hai phía. Với import bulk update chỉ cần cập nhật FK, có thể tổ chức query chuyên biệt và không dựa vào các inverse collections đang loaded.

### 12.2. Không sửa primary key để đổi quan hệ

Khóa chính của entity không được dùng như một field mutable tùy ý sau persist. Nếu association ánh xạ qua `@MapsId` hoặc composite key, đổi parent có thể đụng identity của child; thường phải thiết kế lại thao tác dưới dạng xóa/tạo entity mới theo domain và constraint thay vì đổi khóa chính của managed entity.

## 13. Persistent collection sau clear: initialized hay chưa?

Hibernate thường dùng persistent collection wrapper cho `@OneToMany`, `@ManyToMany`, `@ElementCollection`.

Ví dụ:

```java
Order order = em.find(Order.class, orderId);

List<OrderLine> lines = order.getLines();

em.clear();
```

Có hai tình huống:

### 13.1. Collection chưa được initialized

Nếu code sau clear thực hiện:

```java
lines.size();
```

Hibernate có thể cần query để tải collection, nhưng wrapper không còn Session phù hợp. Kết quả có thể là:

```text
org.hibernate.LazyInitializationException:
    failed to lazily initialize a collection
    - no Session
```

`clear()` không làm association lazy tự được tải.

### 13.2. Collection đã initialized

Nếu trước clear:

```java
order.getLines().size(); // Giả sử thao tác này initialize.

em.clear();

order.getLines().add(new OrderLine(5));
```

List Java có thể đổi, nhưng vì wrapper và owner đã detached, thay đổi **không tự được ghi xuống database**.

### 13.3. Đừng giữ collection wrapper xuyên chunks

Không nên dùng:

```java
List<OrderLine> cachedLines = order.getLines();

em.flush();
em.clear();

// Chunk khác:
cachedLines.add(newChild);
```

thay cho thao tác vào managed aggregate trong context mới.

Cần giữ dữ liệu nào giữa các chunks thì giữ DTO, IDs hoặc các giá trị đơn giản. Đừng giữ persistent collection wrapper như một danh sách có khả năng tự lưu.

## 14. orphanRemoval sau clear: nguy cơ bỏ sót việc xóa

Giả sử Order:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Trong context managed, remove một child khỏi collection theo mapping có thể khiến Hibernate lên lịch DELETE khi flush:

```java
Order managedOrder = em.find(Order.class, orderId);

OrderLine line = findLineInOrder(managedOrder, lineId);
managedOrder.removeLine(line);

em.flush();
```

Sau clear:

```java
Order detachedOrder = loadedEarlier;

em.clear();

detachedOrder.getLines().removeIf(
    line -> Objects.equals(line.getId(), lineId)
);

// Không có lý do để Hibernate tự phát hiện orphanRemoval.
```

### 14.1. Tải lại managed owner nếu cần orphan removal lifecycle

```java
Order managedOrder = em.find(Order.class, orderId);

OrderLine target = managedOrder.getLines().stream()
    .filter(line -> Objects.equals(line.getId(), lineId))
    .findFirst()
    .orElseThrow();

managedOrder.removeLine(target);

em.flush();
```

Cách này có thể tải toàn bộ collection để tìm một child, không phù hợp với collection khổng lồ.

### 14.2. Xóa child trực tiếp có khác orphanRemoval?

Có thể load child theo ID rồi:

```java
OrderLine managedLine = em.find(OrderLine.class, lineId);
em.remove(managedLine);
```

Cách này đi qua entity removal lifecycle cho child, nhưng nếu owner collection đã loaded trong context thì cần giữ graph nhất quán trong memory. Đồng thời, deletion rule phải được domain cho phép.

Bulk HQL/Criteria DELETE theo ID có thể tiết kiệm hơn nhưng **bỏ qua callback/cascade entity lifecycle**; đó là quyết định khác cần hiểu trước khi áp dụng.

## 15. Many-to-many: chỉnh collection owning side sau clear

Giả sử Product và Tag:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "product_tags",
        joinColumns = @JoinColumn(name = "product_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();

    public Set<Tag> getTags() {
        return tags;
    }
}
```

`Product.tags` là owning side của join table.

Sai sau clear:

```java
Product product = em.find(Product.class, productId);

em.clear();

product.getTags().add(tag);

// product detached; không tự INSERT product_tags.
```

Cách theo entity lifecycle:

```java
Product managedProduct = em.find(Product.class, productId);
Tag tagRef = em.getReference(Tag.class, tagId);

managedProduct.getTags().add(tagRef);

em.flush();
```

Ở đây cả owner và tag reference thuộc context hiện tại. Hibernate có thể ghi join-table row khi flush, nhưng có thể phải initialize collection để quản lý snapshot/duplicates tùy mapping.

### 15.1. Ghi rất nhiều liên kết vào join table

Nếu mỗi Product có hàng chục nghìn tags và cần import hàng triệu quan hệ, tải một `Set<Tag>` lớn cho từng product có thể tốn kém.

Một phương án là **mô hình hóa join table thành entity liên kết**:

```java
@Entity
@Table(
    name = "product_tags",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"product_id", "tag_id"}
    )
)
public class ProductTag {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id")
    private Product product;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "tag_id")
    private Tag tag;

    protected ProductTag() {}

    public ProductTag(Product product, Tag tag) {
        this.product = product;
        this.tag = tag;
    }
}
```

Như vậy, mỗi row join được insert như một entity:

```java
Product productRef =
    em.getReference(Product.class, productId);

Tag tagRef =
    em.getReference(Tag.class, tagId);

ProductTag link = new ProductTag(productRef, tagRef);

em.persist(link);
```

Không cần tải `product.getTags()` để chỉ thêm row liên kết.

### 15.2. Database unique constraint cho link

Với entity liên kết, dùng unique constraint trên `(product_id, tag_id)` để bảo vệ không có duplicate dưới concurrent imports.

Nếu join table thực sự có thuộc tính riêng như `createdAt` hoặc `source`, entity liên kết còn giúp mô hình hóa dữ liệu ấy rõ ràng hơn.

### 15.3. Many-to-many không nên cascade REMOVE sang reference data

Nếu Product và Tag là hai aggregate/entity độc lập, xóa một Product không nên xóa Tag đang được Product khác dùng. Không gán `cascade=REMOVE` hoặc `ALL` cho ManyToMany nếu semantics domain không yêu cầu.

## 16. Quan hệ @OneToOne và shared primary key

Một mô hình khác là Order và OrderDetail có quan hệ một-một. Với `@MapsId`, child có thể dùng ID của parent làm chính ID:

```java
@Entity
public class OrderDetail {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Order order;

    @Column(nullable = false)
    private String deliveryNote;
}
```

Sau khi đã persist Order và clear:

```java
Order orderRef = em.getReference(
    Order.class,
    orderId
);

OrderDetail detail = new OrderDetail();
detail.setOrder(orderRef);
detail.setDeliveryNote("Giao giờ hành chính");

em.persist(detail);

em.flush();
em.clear();
```

`@MapsId` cho biết identifier của child được dẫn xuất từ parent association theo mapping. Nhưng cần kiểm tra:

- Parent row đã tồn tại hoặc đã được flush trong transaction.
- Child chưa tồn tại với cùng ID.
- Quan hệ không cố gắng đổi parent/ID sau persist.
- Constructor/setter và mapping chính xác trong entity thực tế.

Không cần merge cả Order detached chỉ để tạo OrderDetail.

## 17. Composite key và @EmbeddedId: giữ key value, không giữ object graph

Một association dùng khóa ghép có thể cần một giá trị key gồm tenant ID và order number:

```java
@Embeddable
public class OrderKey implements Serializable {

    private UUID tenantId;
    private String orderNumber;

    protected OrderKey() {}

    // Constructor, equals, hashCode.
}
```

Với entity:

```java
@Entity
public class Order {

    @EmbeddedId
    private OrderKey id;
}
```

Sau clear, lưu một **immutable/copy-safe identifier value** rồi lấy reference:

```java
OrderKey key = savedOrder.getId();

em.flush();
em.clear();

Order parentRef = em.getReference(
    Order.class,
    key
);
```

### 17.1. Tránh sửa mutable key sau persist

Một `@EmbeddedId` mutable, nhất là khi dùng làm key trong `HashMap`, có thể gây lỗi lookup nếu thay field sau khi hashCode đã được tính.

Thiết kế key nhất quán, có equals/hashCode đúng, và không thay identifier của entity đã tồn tại.

### 17.2. Composite FK cần đủ thành phần

Nếu child tham chiếu parent qua nhiều cột, schema/`@JoinColumns` phải phản ánh đầy đủ khóa. Không nên chỉ giữ một cột mã hiển thị rồi dùng nó như identity toàn cục khi domain thực tế còn tenant/shard.

## 18. @ManyToOne từ child sang parent có nullable hay không?

Khi child bắt buộc có parent:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private Order order;
```

Mapping thể hiện ý định:

- Association không được null theo JPA.
- FK column không được null theo schema mong muốn.
- Insert child thiếu parent có thể thất bại ở validation/SQL constraint.

Nhưng `optional=false` **không chứng minh ID được truyền vào `getReference` có row tồn tại**. Muốn bảo đảm referential integrity cần FK trong database, và nếu cần thông báo nghiệp vụ trước khi insert thì phải validate.

### 18.1. Nếu parent thực sự optional

Có thể:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "referrer_id", nullable = true)
private Customer referrer;
```

Nếu không có referrer, gán `null`. Đừng tạo một proxy với ID giả như 0 hoặc -1 để mô tả “không có”, trừ khi schema/domain thực sự dùng sentinel row có nghĩa.

## 19. Identifier generation và thời điểm ID có sẵn

Trong batch import, có một vấn đề thực tế: khi nào `parent.getId()` có giá trị?

### 19.1. SEQUENCE

Với `GenerationType.SEQUENCE`, Hibernate thường có thể lấy ID từ sequence trước khi thực thi INSERT; tùy generator/optimizer, ID thường có sau `persist()`.

```java
em.persist(order);
Long id = order.getId(); // Thường đã có với SEQUENCE phù hợp.
```

Pooled optimizers có thể giảm số lần lấy sequence và tăng hiệu quả batching. ID được cấp không có nghĩa row đã commit.

### 19.2. IDENTITY

Với `GenerationType.IDENTITY`, database thường tạo ID khi INSERT xảy ra. Hibernate có thể phải thực hiện INSERT sớm để lấy generated key, đặc biệt trong transaction và cách dùng persist thông thường.

Điều này có thể làm giảm hoặc hạn chế JDBC INSERT batching so với sequence. Không giả định mọi entity IDENTITY sẽ đợi đủ chunk rồi mới có ID.

### 19.3. UUID/assigned ID

Với UUID được tạo phía ứng dụng hoặc assigned ID, giá trị có thể biết trước khi INSERT:

```java
UUID id = UUID.randomUUID();
Order order = new Order(id, code);
em.persist(order);
```

Nhưng vẫn cần flush/commit và FK constraints phù hợp trước khi child ở transaction khác có thể tham chiếu parent một cách đáng tin.

### 19.4. Không dùng ID null trong reference

Sai:

```java
em.persist(order);

Long id = order.getId(); // Có thể null tùy strategy/timing.

em.clear();

em.getReference(Order.class, id);
```

Nếu ID cần được chuyển sang chunk khác, hãy xác minh nó đã được cấp, flush khi cần, rồi lưu vào cấu trúc dữ liệu phù hợp.

Không tự gán ID tùy tiện cho entity dùng generator mà không hiểu mapping, vì có thể tạo duplicate hoặc lỗi lifecycle.

## 20. Thứ tự INSERT và ràng buộc foreign key

Với FK không deferrable:

```text
INSERT orders(id = 100)
          |
          v
INSERT order_lines(order_id = 100)
```

Parent phải tồn tại theo transaction/database constraint khi child được insert. Nếu code lưu child trước parent và không có cascade/ordering phù hợp, có thể gặp:

```text
ConstraintViolationException
foreign key constraint fails
```

Trong một Session, Hibernate có action queue và có thể sắp xếp INSERT dựa trên mapping hoặc cấu hình `hibernate.order_inserts`. Nhưng không nên giao toàn bộ dependency phức tạp cho thứ tự tình cờ của action queue.

### 20.1. Flush parent trước rồi clear

Với mô hình hai pha:

```java
em.persist(parent);
em.flush(); // INSERT parent đã gửi.
Long id = parent.getId();
em.clear();

Child child = new Child();
child.setParent(em.getReference(Parent.class, id));
em.persist(child);
```

Đường này giúp trạng thái parent rõ ràng trong transaction hiện tại.

### 20.2. Nếu parent và child ở hai transaction khác nhau

Cần commit transaction chứa parent trước khi transaction khác dựa vào parent, hoặc một cơ chế coordination phù hợp với isolation.

Một ID đã được cấp nhưng transaction parent rollback **không bảo đảm row tồn tại**. Child insert ở transaction khác có thể bị FK violation.

## 21. Flush có thể tốn chi phí, clear có thể phá logic aggregate

Một batch loop theo mỗi 50 rows:

```java
if (++count % 50 == 0) {
    em.flush();
    em.clear();
}
```

giúp giới hạn managed state, nhưng nếu chunk kết thúc **giữa lúc aggregate đang được xây dựng**, clear có thể làm parent hoặc các child cần xử lý tiếp trở thành detached.

### 21.1. Không clear giữa lúc vẫn trông chờ cascade

Ví dụ:

```java
Order order = new Order("O-001");
em.persist(order);

em.flush();
em.clear();

order.addLine(new OrderLine(2));

// Không thể kỳ vọng cascade PERSIST từ order detached
// tự thực thi cho line mới này.
```

Với aggregate nhỏ, có thể xử lý trọn aggregate trong cùng chunk trước khi flush/clear.

### 21.2. Chunk theo ranh giới nghiệp vụ thay vì số row tuyệt đối

Nếu Order có 7 lines, nên cân nhắc coi **Order là một đơn vị**; hoàn tất quan hệ của nó trong một context, rồi mới clear.

Nếu một Order có 200.000 lines, không thể giữ toàn bộ aggregate trong context chỉ vì muốn helper hai chiều. Cần chuyển sang mô hình staged import qua ID/managed references và một cơ chế kiểm tra invariant ở mức DB/staging hoặc tổng hợp theo chunk.

**Chunk size và aggregate boundary là hai quyết định khác nhau.**

## 22. Khi cần đọc parent state: find hoặc projection thay cho getReference

`getReference` thích hợp nếu chỉ cần FK. Nhưng nhiều bài toán yêu cầu xác minh:

- Parent thuộc tenant hiện tại.
- Parent chưa bị khóa hoặc xóa mềm.
- Parent ở trạng thái cho phép thêm child.
- Tổng số child chưa vượt giới hạn.
- Người dùng có quyền thêm quan hệ.

Trong trường hợp này:

```java
Order order = em.createQuery("""
    select o
    from Order o
    where o.id = :id
      and o.tenantId = :tenantId
      and o.status = 'OPEN'
    """, Order.class)
    .setParameter("id", orderId)
    .setParameter("tenantId", tenantId)
    .getResultStream()
    .findFirst()
    .orElseThrow(() -> new OrderUnavailableException(orderId));
```

Query minh họa giả định entity `Order` có `tenantId` và `status`.

Sau khi xác minh và nhận managed Order, có thể gán nó cho child. Nhưng nếu invariant cần chống concurrent changes, chỉ kiểm tra state rồi ghi FK trong cùng transaction **chưa chắc đủ**; cần version/locking/constraint phù hợp.

### 22.1. getReference không phải công cụ xác thực tenant

Nếu code nhận `orderId` từ client rồi gọi:

```java
em.getReference(Order.class, orderId);
```

nó chưa xác minh Order thuộc tenant của user. Nếu schema cho phép FK cross-tenant, có nguy cơ liên kết dữ liệu sai phạm vi.

Có thể giải quyết bằng:

- Scoped SELECT/authorization trước khi liên kết.
- Composite tenant-aware FK/unique constraints.
- Database row-level security nếu được triển khai đúng.
- Service boundary và tenant isolation được kiểm thử.

### 22.2. Không tin ID do import file cung cấp mà không kiểm tra

File CSV bên ngoài có thể chứa parent ID không tồn tại hoặc thuộc dataset khác. Với dữ liệu không tin cậy, staging/lookup/validation theo business key có thể tốt hơn nhận trực tiếp internal primary key.

## 23. Persistence Context và @Version khi cập nhật quan hệ sau clear

Một managed Order có `@Version` có thể phát hiện optimistic locking conflict khi update state của chính Order theo lifecycle.

Sau clear:

```java
Order detached = previouslyLoadedOrder;

em.clear();

// Một transaction khác có thể đã thay đổi Order.

detached.changeStatus("CONFIRMED");
```

Sửa detached object không tự tạo version check. Nếu sau đó `merge(detached)`, Hibernate có thể gặp stale version hoặc áp state cũ tùy mapping/concurrency. Đường này phức tạp và có rủi ro.

Tốt hơn:

```java
Order managed = em.find(Order.class, orderId);

managed.changeStatus("CONFIRMED");

em.flush();
```

Việc load managed entity mới cho phép đọc version hiện tại và dùng optimistic locking theo Hibernate entity update path.

### 23.1. Thêm child có làm tăng version parent không?

Không có quy tắc đơn giản “cứ INSERT child là version parent tăng”. Điều này phụ thuộc:

- Bên sở hữu quan hệ.
- Mapping collection.
- Thao tác trên collection managed.
- Hibernate version và chính sách versioning collection.
- Có UPDATE parent được phát hay không.

Nếu nghiệp vụ cần khóa aggregate-level để ngăn hai transaction cùng thêm child vượt giới hạn, hãy thiết kế version/locking trên parent rõ ràng. Có thể dùng `LockModeType.OPTIMISTIC_FORCE_INCREMENT` hoặc `PESSIMISTIC_WRITE` trong ngữ cảnh phù hợp, thay vì trông chờ INSERT child tự tăng version parent.

### 23.2. Detached reference và stale data

Nếu `Order` đã đóng trước khi thêm line, giữ tham chiếu Order cũ có thể bỏ qua việc parent vừa đổi sang CANCELLED bởi transaction khác. Lấy managed reference giúp association mapping sạch hơn, nhưng **không tự bảo đảm đọc lại status**. Muốn kiểm tra status phải query/lock theo rule nghiệp vụ.

## 24. equals/hashCode và identity giữa các chunks

Nếu entity được dùng trong `Set`/`Map` hoặc trong collection association, triển khai equals/hashCode không đúng có thể gây duplicate/mất phần tử hoặc exception khi Hibernate dùng proxy.

### 24.1. Tránh equals/hashCode dựa vào object identity duy nhất

`==` so sánh Java object, không phải database identity. Sau clear rồi find lại, hai instances có thể cùng ID nhưng khác reference.

### 24.2. Tránh hashCode đổi sau persist

Nếu equals/hashCode dựa trên generated ID, ID có thể từ null chuyển thành non-null sau persist. Nếu object đã được thêm vào HashSet trước khi ID có giá trị, hash code thay đổi có thể khiến không còn tìm được phần tử.

Một chiến lược phù hợp tùy domain là dùng immutable natural/business key có unique constraint hoặc cách triển khai identity equality xử lý transient entity/proxy cẩn thận. Không có một công thức phù hợp mọi mapping và generator.

### 24.3. Không đưa association lazy vào equals/hashCode

Ví dụ dùng Lombok `@Data` trên entity có `@OneToMany` có thể sinh equals/hashCode và toString duyệt collection. Sau clear, điều đó có thể kích hoạt `LazyInitializationException` hoặc recursion/nhiều SELECT.

Đối với batch imports, map bằng ID hoặc external key của DTO thường an toàn và ít tốn memory hơn lưu cả entity trong HashSet.

## 25. Session.getReference và EntityManager.getReference

Trong Hibernate native API có `Session`:

```java
Session session = em.unwrap(Session.class);

Order ref = session.getReference(
    Order.class,
    orderId
);
```

Đây là phương án native Hibernate cho mục đích tương tự.

Nếu ứng dụng viết theo Jakarta Persistence, `EntityManager.getReference` có tính portable cao hơn. Dù dùng API nào, **reference thuộc Session/EntityManager hiện tại**, không phải một proxy “có thể tái sử dụng ở bất kỳ context nào”.

Sau lần `clear()` tiếp theo, cả reference vừa lấy cũng có thể trở thành detached; hãy lấy lại khi bước mới cần managed reference.

## 26. Không gắn một persistent collection wrapper từ context cũ sang entity mới

Một lỗi đặc biệt khó debug:

```java
Order old = em.find(Order.class, oldId);

List<OrderLine> oldLines = old.getLines();

em.clear();

Order managedNew = em.find(Order.class, newId);

managedNew.setLines(oldLines); // Cực kỳ nguy hiểm.
```

Ngoài việc quan hệ domain có thể sai, `oldLines` có thể là collection wrapper gắn owner/session/snapshot từ context cũ. Việc gán lại wrapper có thể gây lỗi collection ownership, shared reference hoặc mutation không đúng.

Đối với entity quan hệ, không “chuyển” Hibernate collection wrapper như một `ArrayList` tùy ý. Hãy thao tác trên managed associations qua helper đúng, gán owning side cho child hoặc dùng một domain-specific migration process.

### 26.1. Không dùng EntityManager cũ như factory cho reference mới

Nếu context đã `close()`, `em.getReference` trên EntityManager đó không hợp lệ. Cần lấy EntityManager/Session mới do transaction manager quản lý. Nếu chỉ `clear()` mà EntityManager vẫn mở, có thể dùng `getReference` trên cùng EntityManager để lấy reference mới cho context đã rỗng.

## 27. Flush/clear không thay thế xử lý lỗi transaction

Nếu `flush()` ném lỗi constraint:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    em.clear();
    // Tiếp tục import???
}
```

Cách tiếp tục vô điều kiện như trên không an toàn. Một persistence exception có thể khiến transaction rollback-only hoặc Session/action queue không còn trạng thái sử dụng tiếp đáng tin cậy.

Thông thường:

1. Ghi nhận lỗi của chunk với ngữ cảnh an toàn.
2. Rollback transaction.
3. Đóng/loại bỏ persistence context lỗi.
4. Mở transaction/context mới cho retry được thiết kế.
5. Không tái sử dụng entity managed/proxy/collection từ transaction đã thất bại.

**Clear không phải “reset” một transaction lỗi để có thể commit tiếp như chưa có chuyện gì.**

### 27.1. Lỗi FK có thể xuất hiện muộn

`em.persist(child)` không nhất thiết chạy INSERT ngay. FK violation có thể xuất hiện lúc `flush()` hoặc commit. Do đó, không xem “persist không throw” là bằng chứng parent ID hợp lệ.

### 27.2. Lỗi unique link xảy ra khi flush

Khi import join entities, hai child cùng product/tag có thể vi phạm unique constraint tại flush. Nếu muốn idempotent, cần thiết kế lookup/upsert/native SQL phù hợp, không chỉ catch exception rồi dùng lại context cũ.

## 28. Quy mô batch, JDBC batching và thứ tự SQL

Ba yếu tố độc lập:

1. **Chunk size**: số row ứng dụng xử lý trước `flush/clear`.
2. **JDBC batch size**: số statement có thể gom lại trong một lần gửi JDBC batch.
3. **Transaction size**: số row thuộc một lần commit/rollback.

Ví dụ cấu hình Hibernate (cần đối chiếu version và môi trường):

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Với 500 rows và chunk size 100, mỗi chunk có thể chứa các nhóm JDBC batches nhỏ hơn theo statement type/entity mapping. Nhưng:

- Hibernate chỉ gom SQL khi statement đủ tương thích và driver/dialect cho phép.
- IDENTITY identifier generation thường hạn chế insert batching cho entity đó.
- Interleaving nhiều entity types có thể chia batch.
- Quan hệ và FK có thể yêu cầu thứ tự INSERT/UPDATE cụ thể.
- `flush()` kết thúc một nhóm các actions đang pending; `clear()` không tự tối ưu JDBC.

### 28.1. Đừng chọn chunkSize bằng JDBC batch size một cách máy móc

Chunk size 1.000 với JDBC batch size 50 đôi khi phù hợp hơn 50/50; tùy memory, number of associations, dirty checking cost, database latency và transaction size.

Không có con số luôn tối ưu. Hãy đo:

- Rows/s.
- Heap usage.
- SQL statement count.
- JDBC batch executions.
- Flush duration.
- Transaction duration.
- Lock waits.
- Retry rate.

### 28.2. Parent-child dependency ảnh hưởng batch grouping

Nếu input xen kẽ Order, OrderLine, Order, OrderLine, Hibernate có thể khó gom một loại INSERT thành batch lớn. Một import **hai pha** (parents trước, children sau) có thể giúp batching, đồng thời làm FK/order rõ ràng.

Nhưng hai pha chỉ hợp lý khi dữ liệu đầu vào và domain cho phép; với aggregate cần xử lý atomically từng Order, có thể chunk theo aggregate.

## 29. Cách tổ chức transaction: toàn bộ job hay từng chunk?

### 29.1. Một transaction cho toàn bộ job

```text
BEGIN
  chunk A: flush/clear
  chunk B: flush/clear
  chunk C: flush/clear
COMMIT
```

Ưu điểm:

- Atomicity toàn bộ job.
- Parent-child cùng transaction, có thể tham chiếu row đã flush.
- Rollback toàn bộ khi có lỗi.

Nhược điểm:

- Transaction dài, lock/undo/WAL lớn.
- Một lỗi cuối job có thể làm rollback lượng công việc lớn.
- Connection và DB resources bị giữ lâu.

### 29.2. Một transaction mỗi chunk

```text
BEGIN chunk A -> COMMIT
BEGIN chunk B -> COMMIT
BEGIN chunk C -> COMMIT
```

Ưu điểm:

- Transaction ngắn hơn.
- Retry riêng chunk phù hợp.
- Giảm phạm vi rollback.

Nhược điểm:

- Partial progress khi chunk sau thất bại.
- Parent phải commit trước child ở transaction khác.
- Cần checkpoint/idempotency/reconciliation.
- Không thể coi toàn bộ import là một atomic unit.

### 29.3. Spring proxy và transaction per chunk

Đặt `@Transactional` trên method private rồi gọi nội bộ trong cùng class thường không tạo transaction mới khi dùng Spring proxy-based transaction management.

Nếu cần transaction mỗi chunk, dùng một Spring-managed service riêng hoặc `TransactionTemplate`/cơ chế phù hợp để đảm bảo call thực sự qua transaction boundary. `REQUIRES_NEW` có semantics riêng và cần kiểm tra ảnh hưởng lên resource/persistence context.

Không dùng `em.clear()` rồi tuyên bố “chunk đã commit”.

## 30. Tham chiếu sang entity thuộc chunk chưa commit

Nếu Job A tạo Order trong transaction A nhưng chưa commit, Job B ở transaction B gọi:

```java
em.getReference(Order.class, orderId);
em.persist(new OrderLine(..., parentRef));
```

ID có thể đã được cấp nhưng row không visible với transaction B, tùy isolation. Child có thể bị block, FK violation hoặc kết quả khác theo DB.

### 30.1. Xử lý dependency bằng commit boundary

Nếu child phụ thuộc parent từ một transaction khác:

- Commit parent trước.
- Lưu checkpoint/mapping external key → parent ID bền vững.
- Chỉ bắt đầu child chunk khi parent batch đã commit thành công.
- Có retry/idempotency nếu job bị ngắt.
- Kiểm tra parent status/tenant khi dependency có thể thay đổi.

### 30.2. Một ID được cấp không bảo đảm entity tồn tại vĩnh viễn

Sequence/identity có thể để lại khoảng trống khi rollback hoặc delete. Không dùng khoảng liên tục của ID để xác định số lượng rows hay trạng thái commit.

## 31. Thiết kế staging table khi dữ liệu có quan hệ phức tạp

Nếu import có nhiều cấp:

```text
Customer
   |
   +-- Order
           |
           +-- OrderLine
                   |
                   +-- Product
```

và nguồn dữ liệu không được sắp theo dependency, staged import thường an toàn hơn giữ toàn bộ object graph:

1. Đọc raw rows vào staging table có job ID.
2. Validate external keys, tenant và dữ liệu trùng.
3. Tạo/lookup Customer, ghi mapping external → internal ID.
4. Tạo Order với Customer IDs đã có.
5. Tạo OrderLine với Order/Product IDs đã có.
6. Kiểm tra tổng số, orphan references, constraints.
7. Mark job complete và cleanup staging theo retention policy.

### 31.1. Lợi ích

- Không giữ hàng triệu detached entities trong heap.
- Có thể resume từ checkpoint.
- Dễ tìm parent chưa có hoặc duplicate key.
- Tách ingestion khỏi normalization và persistence.
- Có đường audit và reconciliation rõ.

### 31.2. Giới hạn

- Cần schema/tables và quy trình cleanup.
- Cần thiết kế transaction/visibility giữa các bước.
- Cần cân nhắc khả năng concurrent imports cùng external key.
- Có thể chậm hơn đường tối giản nếu tập dữ liệu nhỏ.

Không cần staging cho mọi import, nhưng đáng cân nhắc khi object graph xuyên nhiều chunks.

## 32. Khi parent là reference data dùng chung

Ví dụ Category, Currency, Country, TaxRate, ProductCatalog: nhiều child cùng trỏ đến một parent/reference entity.

Nhiều người cố load tất cả references thành entity map trước batch:

```java
Map<String, Category> categories = loadAllCategories();

for (Row row : rows) {
    Product p = new Product();
    p.setCategory(categories.get(row.categoryCode()));
    em.persist(p);
    // flush/clear định kỳ
}
```

Sau lần clear đầu tiên, các Category trong map đã detached. Chúng có thể cũng chiếm memory và khiến cascade/hành vi association khó dự đoán.

Tốt hơn:

```java
Map<String, Long> categoryIds = loadCategoryIds();

for (Row row : rows) {
    Long categoryId = categoryIds.get(row.categoryCode());

    Category categoryRef = em.getReference(
        Category.class,
        categoryId
    );

    Product product = new Product();
    product.setCategory(categoryRef);

    em.persist(product);
}
```

`loadCategoryIds` là query projection/lookup ứng dụng, không nhất thiết phải tải Category entity. Với domain cần xác minh giá trị category hợp lệ, nên validate khi xây ID mapping và bảo vệ FK/tenant constraints.

## 33. Quan hệ nhiều cấp và cascade theo từng tầng

Ví dụ Customer → Order → OrderLine, cả ba entity đều mới.

Có hai chiến lược:

### 33.1. Cùng aggregate, persist bằng cascade

Khi toàn bộ aggregate nhỏ và hoàn chỉnh:

```java
Customer customer = new Customer(...);
Order order = new Order(...);
OrderLine line = new OrderLine(...);

customer.addOrder(order);
order.addLine(line);

em.persist(customer); // Nếu cascade PERSIST được cấu hình đúng.
em.flush();
em.clear();
```

Không nên giả định mọi class đã được cấu hình cascade; đây là thiết kế mapping cụ thể. Quan hệ từ aggregate root xuống owned children thường phù hợp hơn cascade từ child ngược lên shared parent.

### 33.2. Nhiều pha, giữ IDs và lấy references

Với tập lớn:

```text
Phase A:
    persist Customers
    flush/clear
    retain customerId by external key

Phase B:
    getReference(Customer, id)
    persist Orders
    flush/clear
    retain orderId by external key

Phase C:
    getReference(Order, id)
    getReference(Product, id)
    persist OrderLines
    flush/clear
```

Khi chuyển pha, không cần merge cả graph Customer/Order cũ. Mỗi pha tạo entity mới với owning-side associations ở context hiện tại.

### 33.3. Business invariants ở đâu?

Nếu invariant “một Order phải có ít nhất một line” hoặc “tổng line amount phải bằng order total”, hai pha có thể tạm thời tạo trạng thái chưa hoàn chỉnh.

Giải pháp tùy domain:

- Staging + validation trước commit.
- Một transaction bao toàn bộ creation, và SQL constraints cho state cuối.
- Trạng thái `IMPORTING`/`PENDING` chỉ publish Order khi hoàn tất.
- Aggregate summary/checksum và reconciliation.
- Một chunk theo aggregate nếu kích thước cho phép.

Không được hy sinh invariant chỉ để đạt JDBC batching.

## 34. Sửa quan hệ sau clear bằng UPDATE bulk HQL/Criteria có được không?

Nếu mục tiêu chỉ là gán FK cho nhiều OrderLine đã tồn tại, có thể cân nhắc bulk UPDATE trên mapped entity:

```java
int affected = em.createQuery("""
    update OrderLine l
    set l.order = :newOrder
    where l.id in :lineIds
    """)
    .setParameter(
        "newOrder",
        em.getReference(Order.class, newOrderId)
    )
    .setParameter("lineIds", lineIds)
    .executeUpdate();
```

Tính hợp lệ của assignment association và SQL được sinh ra phụ thuộc mapping/provider/version. Một phương án portable có thể là tải managed lines theo chunk rồi gọi setter, hoặc dùng native SQL nếu cần thay đổi FK hàng loạt với cú pháp DB cụ thể.

**Điểm khác biệt:** bulk HQL/Criteria UPDATE là mutation trực tiếp ở DB; nó không gọi setter, callback per-entity hoặc đồng bộ managed entities đang nằm trong context.

### 34.1. Không nhầm batch entity writes với bulk DML

- **Batch entity writes**: nhiều `persist`/dirty-check updates được gom thành JDBC batches, vẫn qua entity lifecycle.
- **Bulk HQL/Criteria DML**: một query logic UPDATE/DELETE cho nhiều rows, bỏ qua per-entity dirty checking/callback.

Nếu bài toán có cascade/orphanRemoval/version phải xử lý theo từng entity, không thay đổi sang bulk DML mà chưa thiết kế lại semantics.

## 35. Kiểm tra tính đúng sau clear: dữ liệu nào nên giữ?

Một bảng lựa chọn:

| Dữ liệu muốn dùng ở chunk tiếp | Có nên giữ? | Vì sao? |
|---|---|---|
| `Long orderId` / `UUID orderId` | Có | Identifier value, độc lập context |
| DTO immutable từ input | Có | Không mang trạng thái Hibernate |
| External key → internal ID | Có, nếu vừa memory | Hữu ích tra FK; có thể đưa vào staging |
| Managed entity từ chunk trước | Tránh | Trở thành detached sau clear |
| Hibernate lazy proxy cũ | Tránh | Không còn Session phù hợp để initialize |
| Persistent collection wrapper cũ | Tránh | Snapshot/owner/session cũ |
| `EntityManager` của transaction đã đóng | Không | Không thể tiếp tục quản lý entity |
| Error list theo row | Có, giới hạn memory | Dùng report/checkpoint phù hợp |
| Cache of Category entities | Tránh xuyên clear | Chuyển sang ID map hoặc scoped lookup |
| Business aggregate đang xây dở | Cân nhắc lại chunk boundary | Clear giữa chừng có thể bỏ mất lifecycle/cascade |

Một rule hữu ích: **Giữ values để tái dựng tham chiếu; không giữ managed object graph để tái sử dụng như trước khi clear.**

## 36. Kiểm thử liên kết giữa chunks

Integration tests cần tái hiện rõ ranh giới `flush/clear`, không chỉ persist toàn bộ entity trong một context.

### 36.1. Parent ở chunk trước, child ở chunk sau

1. Persist Order.
2. Flush và lấy ID.
3. Clear.
4. `getReference(Order, id)`.
5. Persist OrderLine gán parent ref.
6. Flush/commit.
7. Mở context mới và xác nhận `order_lines.order_id` đúng.

### 36.2. Detached reference với cascade PERSIST

Tạo một mapping test có `cascade=PERSIST` từ child đến parent, tạo parent, clear, rồi persist child tham chiếu parent detached. Xác nhận exception/behavior theo Hibernate version; sau đó dùng managed reference và kiểm chứng trường hợp được hỗ trợ.

Mục tiêu test là **phát hiện giả định sai về state**, không cổ vũ cascade từ child tới parent không cần thiết.

### 36.3. Sửa detached owner không tự được lưu

1. Load OrderLine.
2. Flush/clear.
3. Gán parent khác lên detached line.
4. Flush mà không merge/reload.
5. Xác nhận FK không tự thay đổi.
6. Reload managed line, gán managed parent ref, flush.
7. Xác nhận FK được cập nhật.

### 36.4. Inverse collection

1. Persist Order và OrderLine.
2. Clear.
3. Lấy detached Order từ biến cũ và thêm line vào collection.
4. Kiểm tra database không có row mới nếu không có persist/managed lifecycle tương ứng.
5. Lặp lại với owning side được gán trong context mới.

### 36.5. Many-to-many join entity

1. Tạo Product/Tag ở chunk khác, giữ IDs.
2. Clear.
3. Lấy references trong context hiện tại.
4. Persist ProductTag.
5. Kiểm tra join-table FK, unique constraints và retry behavior.

### 36.6. @MapsId

1. Tạo parent, flush, clear.
2. Lấy reference theo ID.
3. Persist child shared-key.
4. Xác nhận child PK/FK bằng parent ID.
5. Thử duplicate child và kiểm tra constraint.

### 36.7. LazyInitializationException

1. Load parent với lazy collection chưa initialized.
2. Clear.
3. Truy cập collection cũ, quan sát exception.
4. Load lại parent trong context mới và truy vấn dữ liệu cần thiết.

### 36.8. Transaction per chunk

Kiểm tra:
- Parent chunk commit thành công.
- Child chunk fail và rollback.
- Job có thể resume mà không duplicate parent.
- Parent ID mapping được lưu bền vững và không trỏ tới transaction đã rollback.
- Concurrency/tenant scopes được bảo vệ.

## 37. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `clear()` trước `flush()` | Pending changes có thể mất | Flush những thay đổi cần giữ trước clear |
| Giữ `Map<Key, Entity>` qua nhiều chunks | Entity trở thành detached, memory vẫn lớn | Giữ `Map<Key, ID>` hoặc staging |
| Persist child kèm parent detached có cascade PERSIST | Có thể “detached entity passed to persist” | Managed `getReference`/`find`, cascade phù hợp |
| Gọi `persist(parent)` lại sau clear | Nhầm detached thành transient | Không persist lại; dùng reference/find/merge đúng mục đích |
| Dùng `merge` chỉ để gán FK | Có thể SELECT/copy stale state/cascade rộng | `getReference` |
| Sửa detached child rồi flush | Không có dirty checking | Reload managed child rồi sửa |
| Thêm child vào detached collection | Không tự persist | Gán owning side và persist child trong context mới |
| Chỉ sửa inverse side `@OneToMany(mappedBy)` | FK có thể không đổi | Sửa owning side `@ManyToOne` |
| Truy cập lazy collection sau clear | `LazyInitializationException` | Fetch trong context phù hợp |
| Dùng old Hibernate collection wrapper trong owner mới | Lỗi owner/snapshot, graph sai | Thao tác managed association, không copy wrapper |
| Cho rằng `getReference` chứng minh row tồn tại | FK/EntityNotFoundException xuất hiện muộn | Validate nếu cần và dùng FK constraint |
| Cho rằng `getReference` xác minh tenant | Có thể liên kết cross-tenant | Scoped query/authorization/schema |
| Gọi `em.clear()` để reset transaction lỗi | Transaction có thể rollback-only | Rollback, mở context/transaction mới |
| Gọi `clear()` sau mỗi row | Nhiều SQL, chi phí cao | Chunk theo memory/performance |
| Dùng IDENTITY rồi kỳ vọng INSERT batching tối ưu | INSERT có thể chạy sớm lấy ID | Hiểu generator, cân nhắc SEQUENCE/UUID khi hợp |
| Clear giữa aggregate chưa hoàn chỉnh | Mất cascade/dirty tracking | Chunk theo aggregate hoặc staged phases |
| Copy relation update sang bulk HQL tùy tiện | Bỏ qua callbacks/versioning | Chọn lifecycle hoặc bulk policy rõ |
| Giữ transaction quá dài | Lock/WAL/rollback lớn | Chọn transaction boundary theo job |
| Dùng entity equality dựa trên mutable ID trong HashSet | HashCode thay đổi, lookup lỗi | Thiết kế equality/identity đúng |
| Không có unique constraint ở link table | Duplicate link dưới concurrency | Constraint + idempotency |

## 38. Bài tập thực hành

### Bài 1: Parent detached

```java
Order order = new Order("O-1");
em.persist(order);
em.flush();
em.clear();

OrderLine line = new OrderLine(3);
line.setOrder(order);
em.persist(line);
```

**Câu hỏi:** Có nên coi đoạn này là cách chuẩn xử lý association xuyên chunks?

**Giải thích:** Không. `order` detached. Một số mapping có thể ghi FK từ ID, nhưng cascade PERSIST từ child lên parent có thể lỗi; object graph cũ không còn managed. Giữ `orderId` và lấy `em.getReference(Order.class, orderId)` trong context hiện tại là cách diễn đạt ý định an toàn, rõ hơn.

### Bài 2: Sửa inverse collection

```java
Order order = em.find(Order.class, id);
em.clear();
order.getLines().add(new OrderLine(5));
em.flush();
```

**Câu hỏi:** Child có chắc được insert?

**Giải thích:** Không. `order` và collection đã detached. Thậm chí nếu collection còn lazy chưa initialized, có thể ném exception. Cần persist child trong context mới và gán owning `line.order` đúng.

### Bài 3: Merge

```java
Order managed = em.merge(oldOrder);
oldOrder.changeStatus("SHIPPED");
em.flush();
```

**Câu hỏi:** Có chắc UPDATE status không?

**Giải thích:** Không. `oldOrder` vẫn detached, `merge` trả managed instance có thể khác. Nếu muốn cập nhật sau merge thì sửa `managed`, nhưng với workflow batch thường nên load managed và áp command thay vì merge detached graph.

### Bài 4: getReference chưa có row

```java
Order ref = em.getReference(Order.class, 999L);
OrderLine line = new OrderLine(2);
line.setOrder(ref);
em.persist(line);
```

**Câu hỏi:** Có chắc Order#999 tồn tại?

**Giải thích:** Không. getReference có thể trả proxy chưa SELECT; lỗi có thể xuất hiện lúc initialize hoặc khi database kiểm tra FK. Kiểm tra tồn tại/tenant nếu nghiệp vụ yêu cầu.

### Bài 5: Many-to-many lớn

Cần import hai triệu ProductTag links. Mỗi Product có vài nghìn tags.

**Câu hỏi:** Có nên load `Product.tags` rồi thêm từng Tag vào managed Set?

**Gợi ý:** Cách ấy có thể tải collection rất lớn. Nếu domain cho phép, mô hình hóa join table bằng entity `ProductTag`, persist từng link với Product/Tag managed references và unique constraint; xử lý theo chunk.

### Bài 6: Transaction

Trong một transaction dài, batch chạy 10 lần `flush/clear`, lần thứ 10 lỗi và transaction rollback.

**Câu hỏi:** 9 chunk đầu đã commit chưa?

**Giải thích:** Chưa. Flush gửi SQL nhưng không commit. Nếu tất cả ở cùng transaction và rollback, các thay đổi trước đó cũng rollback. Muốn commit riêng phải tạo transaction boundary thực sự.

### Bài 7: Invariant aggregate

Order yêu cầu tổng quantity tối đa 1.000. Import 20.000 OrderLines qua nhiều chunks.

**Câu hỏi:** Chỉ dựa vào `order.getLines().size()` trong một detached object có đủ an toàn?

**Giải thích:** Không. Collection có thể chưa initialized, stale và không phản ánh lines đã ghi từ những chunks/transactions khác. Cần validation/tổng hợp theo staging, query và locking/constraint phù hợp.

## 39. Quy trình thiết kế import có quan hệ

Trước khi triển khai, trả lời các câu hỏi:

1. **Đối tượng nào là parent, child, shared reference?**
2. **Owning side** của từng association nằm ở đâu?
3. Parent và child được tạo cùng chunk hay khác chunk?
4. Parent ID được cấp ở thời điểm nào với generator hiện tại?
5. Có thể giữ ID/DTO thay vì entity trong bộ nhớ không?
6. Có cần `getReference` hay phải `find` và xác minh parent state?
7. Có tenant/authorization constraint khi gán FK?
8. Cascade PERSIST/MERGE/REMOVE có phù hợp ownership?
9. Có persistent collections hoặc aggregate đang xây dở lúc clear?
10. Có dùng `@MapsId`/composite key khiến association quyết định identity?
11. Có orphanRemoval cần lifecycle processing không?
12. Có many-to-many quá lớn nên dùng link entity?
13. Có cần parent version lock/invariant khi thêm child đồng thời?
14. Dữ liệu có staging external key → internal ID để resume?
15. Flush/clear xảy ra sau bao nhiêu entity và ở boundary nào?
16. Transaction commit toàn job hay từng chunk?
17. Parent chunk đã commit trước khi child transaction khác chạy chưa?
18. Khi flush lỗi, workflow rollback và retry thế nào?
19. JDBC batch size/ID generator/inserts ordering đã được đo?
20. Tests có thực sự clear context giữa các giai đoạn liên kết?

Không có một công thức chung cho mọi graph. Với mỗi association, cần biết **ai sở hữu FK, object đang managed ở context nào, và boundary giao dịch ở đâu**.

## 40. Ghi nhớ

- **`flush()` và `clear()` phục vụ hai mục đích khác nhau**: flush gửi SQL pending, clear detach toàn bộ managed entities.
- **Clear không commit**, không đổi ID đã cấp, nhưng làm entity và persistent collection cũ không còn managed.
- **Đừng giữ entity/proxy/collection cũ làm state xuyên chunks**. Giữ IDs/immutable DTO/external-key mappings; dùng staging nếu tập quá lớn.
- Sau clear, khi cần gán FK đến parent đã tồn tại, thường dùng **`EntityManager.getReference(Parent.class, parentId)`** trong context hiện tại.
- `getReference` có thể không chạy SELECT ngay nhưng **không tự chứng minh row tồn tại hoặc thuộc tenant đúng**. Nếu cần kiểm tra nghiệp vụ, dùng scoped query/`find`, locks và DB constraints.
- **Owning side quyết định FK**: trong bidirectional one-to-many, thường là `child.parent` ở `@ManyToOne`.
- Thêm vào inverse collection detached không tự persist child; sửa field detached không tạo dirty checking.
- Không dùng `CascadeType.ALL` trên child-to-parent một cách máy móc; cascade PERSIST có thể gây **“detached entity passed to persist”** với parent cũ.
- **Merge copy state vào managed instance được trả về**, không reattach chính object đầu vào. Không merge cả graph chỉ để lấy FK.
- Persistent collections có thể ném `LazyInitializationException` sau clear nếu chưa initialized; collection đã initialized nhưng detached cũng không tự đồng bộ mutation.
- **orphanRemoval** và xóa entity theo lifecycle cần managed graph; bulk delete là semantics khác.
- Many-to-many khối lượng lớn có thể phù hợp **link entity + getReference** hơn là tải toàn bộ collection.
- Với `@MapsId` và composite keys, identifier/association mapping cần được giữ nhất quán; không tùy tiện đổi khóa chính.
- `SEQUENCE`, `IDENTITY` và assigned/UUID ID có thời điểm cấp và hiệu quả JDBC batching khác nhau.
- Chunk size, JDBC batch size và transaction size là **ba tham số khác nhau**; flush/clear không tạo transaction mới.
- Nếu parent và child ở **các transaction riêng**, parent phải được commit thành công hoặc có coordination phù hợp trước khi child dựa vào row đó.
- Không dùng `clear()` để tiếp tục sau một transaction đã thất bại; rollback và mở unit of work mới.
- Đánh giá performance cùng các yếu tố memory, SQL count, batch count, locks, duration và retry — không chỉ số row xử lý mỗi chunk.
- **Thiết kế theo ownership, identifier, context lifecycle và transaction boundary** là nền tảng để ghi nhiều entity có quan hệ một cách đúng đắn.

**Kết luận:** Trong ghi hàng loạt Hibernate, `clear()` giúp kiểm soát bộ nhớ bằng cách tách entity khỏi persistence context, nhưng chính hành vi ấy làm những tham chiếu Java từ chunk trước không còn là đối tượng managed. Cách làm bền vững là **flush đúng lúc, lưu identifier, tái lấy managed reference trong context hiện tại và cập nhật owning side của quan hệ**. Chỉ dùng merge khi thật sự cần hợp nhất detached state; không dựa vào cascade hoặc collection detached để tự tạo SQL. Khi quan hệ phức tạp, có nhiều child hoặc chạy qua các transaction, hãy tổ chức theo aggregate boundaries hoặc staging/ID-based phases với constraints, versioning, retry và kiểm thử rõ ràng.
