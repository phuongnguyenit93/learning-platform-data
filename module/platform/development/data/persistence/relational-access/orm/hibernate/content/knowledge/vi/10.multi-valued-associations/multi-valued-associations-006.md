# Thêm, xóa và thay thế phần tử trên tập hợp đang được quản lý

## 1. Đặt vấn đề: sửa một collection Java có nghĩa gì với Hibernate?

Trong Java thuần, các thao tác `list.add(element)`, `list.remove(element)` và `list.set(index, newElement)` chỉ thay đổi cấu trúc dữ liệu trong bộ nhớ. Khi collection là thuộc tính của một **entity đang được quản lý** (*managed entity*) bởi Hibernate, cùng những lời gọi ấy có thể được Hibernate theo dõi để ghi thay đổi vào các bảng quan hệ ở lần `flush` tiếp theo.

Ví dụ một đơn hàng có ba dòng:

```text
Order(id=100)
   │
   └── lines (managed collection)
       ├── OrderLine(id=201, sku="JAVA", quantity=1)
       ├── OrderLine(id=202, sku="ORM", quantity=2)
       └── OrderLine(id=203, sku="SQL", quantity=1)

Trong transaction:
   add(new OrderLine("JPA", 1))
   remove(OrderLine #202)
   changeQuantity(OrderLine #203, 4)

Khi flush/commit:
   INSERT dòng mới
   DELETE dòng đã bị loại nếu orphanRemoval phù hợp
   UPDATE số lượng dòng #203
```

Sơ đồ trên mô tả **kết quả dự kiến của một mapping cụ thể**, không phải quy tắc “mỗi thao tác Java luôn tương ứng đúng một câu SQL”. SQL thực tế phụ thuộc loại quan hệ, bên sở hữu khóa ngoại, loại collection, cascade, orphan removal, collection snapshot, phiên bản Hibernate và trạng thái các phần tử.

**Trọng tâm bài học:** thao tác với collection được quản lý phải nhất quán ở cả ba tầng:

1. **Đối tượng Java:** thêm, xóa, thay và cập nhật phần tử trong `List`/`Set`/`Map`.
2. **Đồ thị entity:** phía sở hữu quan hệ, các reference hai chiều, trạng thái managed/transient/detached/removed và cascade.
3. **Cơ sở dữ liệu:** bảng collection, foreign key, join table, order column, SQL phát ra khi flush và tính nguyên tử của transaction.

Nếu chỉ chú ý tầng Java, code có thể “trông đúng” trong debugger nhưng không lưu quan hệ xuống database, hoặc vô tình xóa một entity mà các nghiệp vụ khác vẫn cần.

## 2. Collection “đang được quản lý” là gì?

Entity được tải qua một `Session` hoặc `EntityManager` đang mở thường ở trạng thái **managed**. Collection được ánh xạ trong entity có thể được Hibernate đại diện bằng một wrapper nội bộ, chẳng hạn các dạng `PersistentBag`, `PersistentList` hoặc `PersistentSet`. Wrapper giúp quản lý khởi tạo lazy, trạng thái collection và thay đổi cần đồng bộ.

Ví dụ:

```java
Order order = entityManager.find(Order.class, orderId);
List<OrderLine> lines = order.getLines();

// lines có thể là wrapper của Hibernate, không phải ArrayList thuần.
lines.add(newLine);
```

Không nên viết logic phụ thuộc vào tên class cụ thể của wrapper. Mapping khai báo `List<OrderLine>`, `Set<String>` hoặc `Map<String, Value>`, còn Hibernate có quyền chọn implementation tại runtime.

### Ba trạng thái cần phân biệt

| Tình huống | Ví dụ | Hệ quả |
|---|---|---|
| Collection thuộc entity **managed** | `Order order = em.find(...); order.addLine(...)` trong transaction | Hibernate có thể phát hiện thay đổi và đồng bộ theo mapping |
| Collection thuộc entity **transient** | `Order order = new Order(...); order.addLine(...)` chưa persist | Java object thay đổi, chưa có SQL cho tới khi persist/flush |
| Collection thuộc entity **detached** | Sửa `order.getLines()` sau khi session đóng | Không tự đồng bộ vào DB; dữ liệu chưa tải lazy còn có thể gây `LazyInitializationException` |

Một collection chưa khởi tạo lazy vẫn có thể là collection được quản lý trong session. Nhưng không phải thao tác nào cũng chỉ gây một SQL nhỏ: chẳng hạn `clear()` hoặc `remove()` có thể làm Hibernate tải collection để xác định trạng thái, tùy mapping.

### Thời điểm Hibernate ghi dữ liệu

```text
begin transaction
     │
     ├── load Order → managed
     ├── add/remove/set/clear trên collection
     ├── sửa field của managed OrderLine
     │
     ▼
flush
     ├── dirty checking entity
     ├── đồng bộ collection state / quan hệ
     └── thực thi SQL INSERT / UPDATE / DELETE cần thiết
     │
     ▼
commit → xác nhận ở database
     │
     ▼
close Session → các entity còn tham chiếu trở thành detached
```

`flush()` **không đồng nghĩa** `commit()`. SQL có thể đã chạy trong transaction rồi vẫn bị rollback. Khi transaction rollback, Java object trong bộ nhớ cũng không tự trở về trạng thái trước khi sửa, nên thường cần bỏ session bị lỗi và tải lại dữ liệu trong session mới.

## 3. Phân biệt ba kiểu tập hợp quan trọng nhất

| Mapping | Phần tử là gì? | Thêm | Xóa | Thay thế |
|---|---|---|---|---|
| `@ElementCollection` | Giá trị cơ bản/embeddable, không có entity ID riêng | Thêm một giá trị thuộc owner | Bỏ giá trị khỏi collection table | Thay giá trị; SQL phụ thuộc Set/List/bag/index |
| `@OneToMany` | Entity con có `@Id` | Cần gán đúng phía sở hữu FK và cascade/persist | Có thể chỉ gỡ liên kết, hoặc xóa entity con nếu `orphanRemoval=true` | Có thể đổi association, xóa orphan và tạo con mới |
| `@ManyToMany` | Entity có ID tồn tại độc lập | Thêm liên kết trong join table | Xóa **liên kết**, không xóa entity đích | Gỡ liên kết cũ và thêm liên kết mới |

Quyết định “một dòng bị xóa khỏi collection” **không đủ** để kết luận Hibernate sẽ `DELETE` hàng entity con. Ví dụ xóa một `Role` khỏi `User.roles` thường chỉ xóa hàng ở bảng `user_roles`, còn role vẫn tồn tại. Nhưng loại một `OrderLine` ra khỏi `Order.lines` với `orphanRemoval=true` là yêu cầu xóa entity con ở database.

Các phần sau lần lượt làm rõ cách thao tác đúng cho từng loại.

## 4. Mô hình @OneToMany hai chiều: Order và OrderLine

Giả sử một dòng đơn hàng chỉ thuộc một Order. Đây là mô hình phù hợp để học thêm, xóa, thay thế phần tử:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(120) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);
```

Java entity cha:

```java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String customerName;

    @Version
    private Long version;

    @OneToMany(
            mappedBy = "order",
            cascade = CascadeType.ALL,
            orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {}

    public Order(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên khách hàng không được rỗng");
        }
        this.customerName = customerName;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        if (line == null) {
            throw new IllegalArgumentException("Thiếu dòng hàng");
        }
        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalArgumentException(
                    "Dòng hàng đã thuộc một đơn khác");
        }
        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }
}
```

Entity con:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public Order getOrder() { return order; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }

    void attachTo(Order newOrder) {
        this.order = newOrder;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0");
        }
        quantity = newQuantity;
    }
}
```

Trong mapping trên:

- `Order.lines` là **phía nghịch** (*inverse side*) vì có `mappedBy = "order"`.
- `OrderLine.order` là **phía sở hữu FK**, tương ứng cột `order_lines.order_id`.
- `cascade = ALL` cho phép một số thao tác lifecycle của Order truyền sang các OrderLine liên quan, gồm persist/merge/remove theo semantics của JPA.
- `orphanRemoval = true` yêu cầu xóa OrderLine khỏi database khi bị loại khỏi quan hệ sở hữu theo vòng đời ORM và điều kiện thích hợp.
- `getLines()` trả một view không cho sửa để code bên ngoài phải dùng `addLine()`/`removeLine()`, qua đó đồng bộ hai phía.

Các method `attachTo()`/`detachFromOrder()` có phạm vi package nhằm ngăn tầng ngoài sửa một phía quan hệ tùy ý. Trong lúc xử lý `removeLine()`, object con tạm có `order=null`, dù FK database khai báo `NOT NULL`; khi `orphanRemoval=true`, Hibernate sẽ lên lịch xóa orphan thay vì giữ một dòng con có FK null. Không nên coi đoạn helper này là mẫu để “gỡ liên kết nhưng giữ dòng” với mapping FK `NOT NULL`.

**Lưu ý:** `List` trong ví dụ không khai báo `@OrderColumn`. Trật tự phần tử trong Java chưa được bảo đảm là thứ tự lưu bền vững trong database. Nếu nghiệp vụ cần vị trí có ý nghĩa, phải thiết kế mapping thứ tự hoặc một cột thứ tự của OrderLine.

## 5. Thêm phần tử vào @OneToMany managed

Giả sử Order đã tồn tại, được tải trong transaction:

```java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final EntityManager em;

    public OrderService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void addBookLine(Long orderId, String sku, int quantity) {
        Order order = em.find(Order.class, orderId);
        if (order == null) {
            throw new IllegalArgumentException("Không tìm thấy đơn hàng");
        }

        OrderLine newLine = new OrderLine(sku, quantity);
        order.addLine(newLine);
        // Transaction manager sẽ flush và commit khi method kết thúc.
    }
}
```

Luồng trạng thái:

```text
Order: managed
new OrderLine(...): transient
        │
        ▼
order.addLine(newLine)
        ├── lines.add(newLine)
        └── newLine.order = order (phía sở hữu FK)
        │
        ▼
CascadeType.PERSIST / ALL phù hợp
        │
        ▼
flush → INSERT order_lines(..., order_id, ...)
        │
        ▼
commit → bản ghi mới được xác nhận
```

Với `cascade = PERSIST` hoặc `ALL` từ parent được quản lý, phần tử mới có thể được Hibernate persist theo cascade tại flush/thao tác cascade thích hợp. Nếu mapping không có cascade persist, cần `em.persist(newLine)` một cách tường minh trong transaction. Không nên giả định mọi phần tử transient được thêm vào collection sẽ tự có ID và tự được insert nếu thiếu cascade phù hợp.

### 5.1. Chỉ thêm vào phía inverse là chưa đủ

Một lỗi kinh điển:

```java
// Sai khi đây là quan hệ hai chiều mappedBy="order":
order.getInternalLines().add(newLine);
// newLine.order vẫn null.
```

Giả sử `getInternalLines()` là phương thức truy cập trực tiếp collection bên trong (không có trong thiết kế encapsulated ở trên). Nếu chỉ sửa phía `Order.lines` mà không gán `OrderLine.order`, phía sở hữu FK không có quan hệ đúng. Lúc flush có thể xuất hiện constraint violation, insert thiếu FK hoặc trạng thái quan hệ không như mong đợi.

Ngược lại, nếu chỉ gọi:

```java
newLine.attachTo(order);
```

thì FK có thể được ghi nếu `newLine` được persist, nhưng collection `order.lines` đang nằm trong memory lại không chứa phần tử mới. Trong cùng transaction, code có thể nhìn thấy đồ thị đối tượng không nhất quán. Helper method sửa **cả hai phía** là cách tổ chức đáng tin cậy.

### 5.2. Thêm phần tử đã tồn tại

Nếu `OrderLine` là một entity managed đã thuộc Order khác, không nên dùng `order.addLine(existingLine)` để “chuyển” nó khi mapping `orphanRemoval=true`. Orphan removal hàm ý con thuộc vòng đời của cha; việc loại nó khỏi parent cũ có thể đánh dấu entity để xóa, rồi gắn sang parent mới trong cùng flush dễ vi phạm semantics của orphan.

Nếu nghiệp vụ thực sự cho phép chuyển phần tử giữa các parent, hãy cân nhắc quan hệ không có orphan removal, cung cấp operation chuyển ownership riêng, và cập nhật hai phía trong một transaction. Nếu dòng đơn hàng vốn phải bất biến theo Order, nên tạo dòng mới thay vì “chuyển dòng”.

## 6. Xóa phần tử: gỡ liên kết hay xóa entity?

Trong mapping Order → OrderLine với `orphanRemoval=true`:

```java
@Transactional
public void removeLine(Long orderId, Long lineId) {
    Order order = em.find(Order.class, orderId);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }

    OrderLine target = order.getLines().stream()
            .filter(line -> lineId.equals(line.getId()))
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Không tìm thấy dòng"));

    order.removeLine(target);
}
```

Ở đây `order.getLines()` có thể phải khởi tạo collection trước khi tìm phần tử. Mẫu thích hợp cho đơn có ít dòng; với tập hợp lớn, nên query trực tiếp `OrderLine` theo `id` và `order.id` rồi áp dụng quy tắc delete một cách có kiểm soát.

Khi xóa:

```text
order.lines.remove(line)
        │
        ├── Java collection không còn line
        ├── line.order = null trong memory
        └── orphanRemoval = true
                      │
                      ▼
             flush → DELETE order_lines WHERE id = ...
                      │
                      ▼
                    commit
```

Nếu bỏ `orphanRemoval=true` nhưng vẫn có `@ManyToOne(optional=false)` và FK `NOT NULL`, “gỡ liên kết” không còn hợp lệ ở database trừ khi thay bằng quan hệ khác hoặc xóa con một cách tường minh. Hibernate có thể cố cập nhật FK thành null, gây lỗi constraint, hoặc không tạo thay đổi ở FK nếu chỉ sửa phía inverse. Không nên áp dụng cùng helper cho mọi chính sách lifecycle mà không kiểm tra mapping.

### 6.1. Ba khái niệm dễ nhầm

| Cơ chế | Ý nghĩa | Ví dụ |
|---|---|---|
| `collection.remove(child)` | Thao tác Java lên association/collection | Bỏ phần tử ra khỏi `Order.lines` |
| `orphanRemoval=true` | Khi con bị loại khỏi quan hệ sở hữu theo mapping, ORM xử lý xóa orphan | `DELETE FROM order_lines ...` |
| `CascadeType.REMOVE` | Khi gọi remove trên **parent**, thao tác remove có thể truyền sang các con | `em.remove(order)` dẫn tới xóa các dòng |

`orphanRemoval` và `CascadeType.REMOVE` không tương đương. Thường không cần gọi `em.remove(child)` sau khi đã loại child khỏi collection với orphan removal đúng; làm cả hai có thể gây trạng thái khó đọc và tăng coupling.

### 6.2. Cẩn thận khi dùng remove(Object)

`List.remove(Object)` và `Set.remove(Object)` dựa vào `equals()` của phần tử, không tự chọn bằng primary key của Hibernate. Nếu entity không override `equals()`, một detached object có cùng ID nhưng khác reference thường **không** xóa được phần tử managed:

```java
// lineFromRequest là detached và có cùng ID với một line managed.
order.removeLine(lineFromRequest); // Có thể không xóa phần tử nào.
```

Nếu chỉ có `lineId` từ request, hãy tìm managed element theo ID trong collection rồi truyền chính instance đó cho helper, hoặc query entity managed theo ID và kiểm tra quyền sở hữu. Không dựa vào việc tạo “entity rỗng chỉ gắn ID” rồi `remove()` một cách tùy tiện.

Với `Set<Entity>`, `equals()/hashCode()` phải có hợp đồng ổn định theo lifecycle và tương thích proxy. Hash code phụ thuộc trực tiếp vào generated ID có thể đổi sau khi persist, khiến `Set.contains()` hoặc `remove()` thất bại dù phần tử đang ở trong Set.

## 7. Thay thế một phần tử là thao tác nào?

“Thay thế” có thể mang ít nhất bốn ý nghĩa khác nhau:

1. **Sửa thuộc tính của cùng entity:** dòng #201 vẫn là dòng #201, chỉ thay số lượng.
2. **Xóa entity cũ và tạo entity mới:** dòng #201 bị loại, dòng mới nhận ID khác.
3. **Đổi liên kết tới entity khác:** ví dụ người dùng bỏ role A và gắn role B, nhưng cả hai role vẫn tồn tại.
4. **Thay một value object:** giá trị địa chỉ cũ được thay bằng địa chỉ mới, không có entity ID riêng.

Chọn đúng ý nghĩa trước khi gọi `list.set()`, `remove()` + `add()` hoặc `clear()` + `addAll()`.

### 7.1. Nếu vẫn là cùng entity, sửa thuộc tính

Để đổi số lượng của dòng #201:

```java
@Transactional
public void changeLineQuantity(Long orderId, Long lineId, int quantity) {
    OrderLine line = em.createQuery(
            "select l from OrderLine l " +
            "where l.id = :lineId and l.order.id = :orderId",
            OrderLine.class)
            .setParameter("lineId", lineId)
            .setParameter("orderId", orderId)
            .getResultStream()
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Dòng không thuộc đơn"));

    line.changeQuantity(quantity);
    // line vẫn có cùng ID; dirty checking UPDATE khi flush.
}
```

Phần tử là entity đã managed, nên thường không cần `remove(oldLine)` rồi `add(newLine)`. Làm vậy có thể gây `DELETE` và `INSERT`, đổi ID, phá FK đang tham chiếu dòng cũ, và kích hoạt audit/lifecycle không mong muốn. Khi identity không thay đổi, **sửa field** là lựa chọn phù hợp.

### 7.2. Nếu thực sự cần một entity mới

Trong collection nhỏ có orphan removal:

```java
@Transactional
public void replaceLineEntity(
        Long orderId, Long oldLineId, String newSku, int newQuantity) {
    Order order = em.find(Order.class, orderId);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }

    OrderLine oldLine = order.getLines().stream()
            .filter(line -> oldLineId.equals(line.getId()))
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Không có dòng cũ"));

    order.removeLine(oldLine);                  // orphan
    order.addLine(new OrderLine(newSku, newQuantity)); // transient mới
}
```

Ở flush, Hibernate có thể xóa row của oldLine và insert row mới. Không nên giả định hai câu SQL luôn xuất hiện đúng thứ tự lập trình hoặc khi `remove()` được gọi. Nếu có unique constraint (ví dụ `UNIQUE(order_id, sku)`), việc thay entity với cùng business key có thể gặp xung đột do **thứ tự thực thi SQL**. Thường nên cập nhật entity cũ thay vì xóa rồi insert lại khi cần giữ cùng business identity; nếu việc thay ID thực sự bắt buộc, cần thiết kế flush/constraint/transaction phù hợp.

### 7.3. List.set(index, newElement) không giống sửa field

Về Java, `List.set(2, replacement)` thay object tại vị trí 2 và trả về object cũ. Trong managed collection, tùy mapping, Hibernate có thể coi đó là **loại entity cũ khỏi association và gắn entity mới**. Với orphan removal, entity cũ có thể bị xóa. Với `@OrderColumn`, còn có thể phát sinh thay đổi vị trí của những phần tử khác.

Ví dụ helper có ý nghĩa “thay entity” đối với collection nhỏ:

```java
public void replaceLineAt(int index, OrderLine replacement) {
    if (replacement.getOrder() != null
            && replacement.getOrder() != this) {
        throw new IllegalArgumentException(
                "Dòng mới thuộc một đơn khác");
    }
    OrderLine old = lines.get(index);
    if (old == replacement) {
        return;
    }
    lines.set(index, replacement);
    old.detachFromOrder();
    replacement.attachTo(this);
}
```

Đây là method **bổ sung vào Order** để minh họa semantics và giả định các phần tử không bị trùng reference ở vị trí khác. Với list có thể chứa duplicate reference, cần có chính sách riêng. Vì mapping Order phía trên không có `@OrderColumn`, vị trí `index` chỉ mang ý nghĩa trong danh sách hiện tại, không bảo đảm giữ nguyên sau khi nạp lại từ database. Nên thiết kế thứ tự rõ ràng nếu API thực sự thao tác bằng index.

**Khi đang sửa quantity, đừng gọi `set(index, new OrderLine(...))`.** Đó là thay thực thể, có thể xóa hàng cũ và tạo hàng mới.

## 8. Vì sao không nên thay cả object collection một cách tùy tiện?

Hibernate có thể thay field collection bằng một wrapper để theo dõi trạng thái. Mẫu code sau tiềm ẩn rủi ro trên entity managed:

```java
// MẪU NGUY HIỂM với managed persistent collection:
public void setLines(List<OrderLine> incoming) {
    this.lines = new ArrayList<>(incoming);
}
```

Việc thay reference khiến wrapper Hibernate cũ bị bỏ khỏi field entity. Với mapping có `orphanRemoval=true`, lúc flush có thể xảy ra lỗi kiểu “collection with cascade=all-delete-orphan was no longer referenced by the owning entity instance”, hoặc Hibernate hiểu sự thay đổi khác với điều nghiệp vụ mong muốn. Những mapping khác có thể thực thi DELETE/INSERT diện rộng.

Một cách an toàn hơn khi cần sửa trạng thái một collection **đang được quản lý** là giữ reference của collection cũ và thao tác trên chính collection đó thông qua các helper:

```java
// Ví dụ thay toàn bộ tập hợp giá trị (không phải entity con có identity):
public void replaceLabels(Set<String> newLabels) {
    Set<String> copy = new HashSet<>(newLabels);
    labels.clear();
    labels.addAll(copy);
}
```

Tuy nhiên, với `@OneToMany` entity con, `clear()` + `addAll()` đơn thuần chưa đủ vì còn phải cập nhật **phía sở hữu**, cascade/orphan lifecycle, ID của con và những con có thể đã bị đánh dấu removed. Đối với entity collection, dùng quy trình đồng bộ phần tử theo ID ở phần 13.

Các trường hợp áp dụng khác nhau:

| Tình huống | Hướng xử lý |
|---|---|
| Entity **transient**, chưa được Hibernate quản lý | Có thể khởi tạo field collection bằng `new ArrayList<>()` trước persist |
| Entity **managed**, chỉ thêm/xóa vài phần tử | Giữ wrapper; gọi method thay đổi collection/association |
| Entity **managed**, thay toàn bộ value collection nhỏ | `clear()`/`addAll()` trên collection hiện tại, có defensive copy |
| Entity **managed**, đồng bộ child entities | So sánh theo ID, update phần tử hiện tại, remove phần tử mất đi, add phần tử mới |
| Collection **detached** | Không trông đợi tự flush; tải managed entity rồi áp dụng command/DTO trong transaction |

**Điểm dễ bỏ sót:** trong Hibernate, không nên gán `new ArrayList<>(...)` vào field collection chỉ vì muốn “đổi list”. Nếu áp dụng thuật toán thay toàn bộ, nên chọn thao tác phù hợp trên collection được quản lý thay vì phá vòng đời wrapper.

## 9. @ElementCollection: thêm, xóa, thay một giá trị

Khác với `OrderLine` có `@Id`, một tập hợp nhãn hoặc số điện thoại thường là value collection. Ví dụ:

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "article_tags",
            joinColumns = @JoinColumn(name = "article_id"))
    @Column(name = "tag", nullable = false, length = 50)
    private Set<String> tags = new HashSet<>();

    protected Article() {}

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Tag rỗng");
        }
        tags.add(tag.trim());
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }

    public void replaceTags(Set<String> incoming) {
        Set<String> copy = new HashSet<>(incoming);
        tags.clear();
        for (String tag : copy) {
            addTag(tag);
        }
    }
}
```

Ví dụ DDL:

```sql
CREATE TABLE articles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE article_tags (
    article_id BIGINT NOT NULL REFERENCES articles(id),
    tag VARCHAR(50) NOT NULL,
    PRIMARY KEY (article_id, tag)
);
```

Khi Article managed, `addTag()` và `removeTag()` đổi collection đang được Hibernate theo dõi. Khi flush, Hibernate có thể phát INSERT/DELETE trên `article_tags`. Không cần `@Entity` hay `em.persist("java")` cho từng `String`. Hibernate quản lý vòng đời value collection thông qua Article.

### Thay một giá trị bằng giá trị khác

Với `Set<String>`, có thể dùng:

```java
public void renameTag(String oldTag, String newTag) {
    if (newTag == null || newTag.isBlank()) {
        throw new IllegalArgumentException("Tag mới không hợp lệ");
    }
    if (tags.remove(oldTag)) {
        tags.add(newTag.trim());
    }
}
```

Ý nghĩa là bỏ giá trị cũ rồi thêm giá trị mới. Đây không phải SQL `UPDATE` trên một entity có ID; Hibernate có thể tạo DELETE/INSERT đối với collection table. Nếu giá trị mới trùng với phần tử đã có, `Set` tự loại duplicate theo `equals()`; database unique constraint giúp bảo vệ khi có nhiều transaction cạnh tranh.

### Không có cascade persist/remove riêng cho từng element

`@ElementCollection` không dùng `cascade = ...` như quan hệ entity vì phần tử không phải entity có lifecycle độc lập. Khi entity owner bị xóa theo ORM, collection rows cần được xử lý theo mapping và constraint; khi xóa tag khỏi collection, ta bỏ **một giá trị**, không thực hiện `EntityManager.remove()` trên một object Tag.

Khi số lượng tag cực lớn và cần ID/audit/status riêng, xem xét chuyển thành entity liên kết thay vì bắt mọi thao tác thông qua value collection của Article.

## 10. List, bag, Set và thứ tự trong database

Java API có nhiều loại collection, nhưng mapping SQL ảnh hưởng mạnh đến cách Hibernate đồng bộ khi thêm/xóa/thay:

| Cấu trúc | Đặc điểm | Điều cần chú ý khi sửa |
|---|---|---|
| `Set<T>` | Không có duplicate theo Java equality; không có index | `equals()/hashCode()` phải ổn định, phần tử phải phân biệt được |
| `List<T>` không có `@OrderColumn` | Với nhiều mapping được xử lý như bag (không lưu vị trí) | `list.set(i, ...)`/reorder trong Java không bảo đảm thứ tự bền vững |
| `List<T>` có `@OrderColumn` | Có cột số thứ tự lưu trong database | Insert/remove ở giữa có thể làm UPDATE nhiều vị trí |
| `List<T>` với `@OrderBy` | Kết quả đọc được sắp theo cột/thuộc tính | Sắp xếp lúc query, không tự lưu vị trí do Java `Collections.swap()` |
| `Map<K,V>` | Phần tử truy cập theo key | Phải hiểu cách key/value được ánh xạ; key mutable gây khó |

Trong mapping dạng bag, Hibernate đôi khi không có khóa hàng rõ ràng để xóa chính xác một giá trị khi có duplicate. Tùy mapping và Hibernate version, sửa một bag có thể khiến SQL **xóa nhiều row rồi insert lại** những row còn lại. Không nên khẳng định `remove()` lúc nào cũng đúng một `DELETE` theo PK.

### 10.1. Ví dụ @OrderColumn

```java
@ElementCollection
@CollectionTable(
        name = "playlist_items",
        joinColumns = @JoinColumn(name = "playlist_id"))
@Column(name = "track_name", nullable = false)
@OrderColumn(name = "position_index")
private List<String> trackNames = new ArrayList<>();
```

Ví dụ DDL tương ứng:

```sql
CREATE TABLE playlist_items (
    playlist_id BIGINT NOT NULL REFERENCES playlists(id),
    position_index INTEGER NOT NULL,
    track_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (playlist_id, position_index)
);
```

Giả sử danh sách là:

```text
index 0 = "A"
index 1 = "B"
index 2 = "C"
```

Sau `trackNames.remove(0)`, Hibernate phải bảo đảm dữ liệu có thứ tự mới `B, C`. Trong một mapping có order column, việc xóa đầu danh sách có thể kéo theo chỉnh lại giá trị `position_index` cho các phần tử sau. Với hàng chục nghìn phần tử, thao tác giữa danh sách có thể rất tốn kém.

Nếu phần tử cần ID riêng và thao tác reorder liên tục, hãy cân nhắc entity `PlaylistEntry` chứa `id`, `playlistId`, `sortKey` và domain operation reorder. Điều đó giúp thiết kế thứ tự theo nhu cầu thực tế, dù phải tự quản lý collision và concurrency.

### 10.2. @OrderBy không đồng nghĩa @OrderColumn

`@OrderBy("createdAt ASC")` yêu cầu Hibernate sắp kết quả theo một thuộc tính khi tải collection, trong khi `@OrderColumn(name="position_index")` lưu **vị trí** theo cấu trúc List. Nếu chỉ khai báo `@OrderBy`, việc đổi thứ tự các object trong Java List nhưng không đổi `createdAt` sẽ không làm database lưu một thứ tự mới.

Muốn cho phép người dùng kéo thả và giữ thứ tự tùy ý, cần dữ liệu vị trí/sort key được lưu rõ ràng. Chỉ dựa vào thứ tự của `ArrayList` lúc commit là chưa đủ.

## 11. @ManyToMany: xóa liên kết, không xóa entity đích

Một user có thể có nhiều role; một role cũng được sử dụng bởi nhiều user:

```text
users            user_roles            roles
id=1  ────────── (1, 10) ──────────── id=10 ("EDITOR")
  │
  └───────────── (1, 20) ──────────── id=20 ("READER")
```

Mapping ở phía sở hữu:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import java.util.HashSet;
import java.util.Set;

@Entity
public class AppUser {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
            name = "user_roles",
            joinColumns = @JoinColumn(name = "user_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id"))
    private Set<Role> roles = new HashSet<>();

    protected AppUser() {}

    public void grantRole(Role role) {
        roles.add(role);
    }

    public void revokeRole(Role role) {
        roles.remove(role);
    }
}
```

Role là entity độc lập:

```java
@Entity
public class Role {
    @Id
    private Long id;

    private String name;

    protected Role() {}
}
```

Khi AppUser managed:

```java
AppUser user = em.find(AppUser.class, userId);
Role role = em.find(Role.class, roleId);

user.grantRole(role);  // Thêm liên kết vào user_roles
user.revokeRole(role); // Gỡ liên kết khỏi user_roles
```

`role` vẫn tồn tại trong bảng `roles` sau `revokeRole()` vì role có thể được nhiều user sử dụng. **Không đặt `CascadeType.REMOVE` hoặc `CascadeType.ALL` một cách máy móc trên quan hệ many-to-many dùng chung.** Cascade remove có thể cố xóa Role được user khác tham chiếu, dẫn đến vi phạm FK hoặc mất dữ liệu dùng chung.

### 11.1. Bên sở hữu quan hệ quyết định join table

Nếu ánh xạ hai chiều `Role.users` với `@ManyToMany(mappedBy="roles")`, collection inverse đó không phải phía quyết định thay đổi bảng `user_roles`. Khi thêm/xóa association, cập nhật `AppUser.roles` là cần thiết; có thể đồng bộ cả `Role.users` trong memory để graph nhất quán.

Nếu chỉ sửa `role.getUsers().remove(user)` trên phía inverse, Hibernate không có bảo đảm sẽ xóa đúng hàng join table. Thiết kế helper method ở phía sở hữu và hạn chế setter trực tiếp giúp tránh lỗi này.

### 11.2. Nếu liên kết có metadata riêng

Một role assignment có thể có `grantedBy`, `grantedAt`, `expiresAt` và trạng thái phê duyệt. Lúc đó liên kết là một domain entity như `UserRoleAssignment` với ID/FK riêng, thường được ánh xạ bằng hai `@ManyToOne`.

Khi đó “xóa role” có thể có nghĩa thu hồi một assignment hoặc soft delete assignment, khác với xóa Role. Mô hình association entity giúp thao tác theo ID và ghi audit chi tiết.

## 12. Xử lý dữ liệu nhận từ API: không merge graph tùy tiện

Giả sử client gửi yêu cầu:

```json
{
  "orderId": 100,
  "lines": [
    {"id": 201, "sku": "JAVA", "quantity": 3},
    {"id": null, "sku": "JPA", "quantity": 2}
  ]
}
```

Có thể client muốn **trạng thái cuối cùng** là hai dòng: cập nhật #201, tạo dòng JPA, xóa mọi dòng cũ không còn được gửi. Nhưng nếu API của client chỉ gửi một phần trang, việc diễn giải “ID không xuất hiện tức là phải xóa” sẽ gây mất dữ liệu. Trước khi đồng bộ phải định nghĩa rõ:

- Request là **patch** (chỉ thay những phần tử được chỉ định), hay **replace** (danh sách đầy đủ)?
- Field `id=null` là tạo mới hay lỗi?
- Có được phép cập nhật `sku` của một dòng hay SKU bất biến?
- Client có được phép xóa hàng không có trong danh sách?
- Có cần version/ETag để tránh xóa thay đổi từ một request khác?

Không nên ánh xạ request JSON thành một graph detached có `Order.lines` rồi gọi `em.merge(detachedOrder)` một cách vô điều kiện. Với cascade merge và orphan removal, graph thiếu phần tử có thể bị hiểu là yêu cầu xóa hoặc không phản ánh đúng ownership/lifecycle. Cũng dễ phát sinh overposting: client sửa những field không được phép.

**Hướng an toàn hơn:** tải managed Order trong transaction, kiểm tra quyền và state, sau đó áp dụng command/DTO vào managed entities. Quy trình đồng bộ đầy đủ được minh họa tiếp theo.

## 13. Đồng bộ danh sách child entity theo ID

Với collection **có kích thước nhỏ hoặc vừa, bounded**, một API thay toàn bộ có thể dùng thuật toán:

1. Tải Order managed và collection hiện tại trong transaction.
2. Tạo map phần tử hiện có theo ID.
3. Với mỗi DTO: có ID thì tìm đúng child thuộc Order và cập nhật field cho phép; không có ID thì thêm entity mới.
4. Những child cũ còn lại mà request không đề cập sẽ bị xóa **chỉ khi endpoint có semantics replace toàn bộ**.
5. Flush/commit; nếu lỗi database/validation thì rollback.

DTO đầu vào:

```java
public record LineInput(Long id, String sku, int quantity) {}

public record ReplaceOrderLinesRequest(
        Long expectedOrderVersion,
        List<LineInput> lines) {}
```

Giả sử Order bổ sung helper `findLineById()` và cho phép cập nhật quantity của child. Một implementation tập trung vào việc giữ managed instances:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void replaceOrderLines(
        Long orderId, ReplaceOrderLinesRequest request) {
    if (request == null || request.lines() == null) {
        throw new IllegalArgumentException("Thiếu danh sách");
    }

    Order order = em.find(Order.class, orderId);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }

    // Kiểm tra trạng thái, quyền thao tác, invariant tại đây.
    if (!Objects.equals(order.getVersion(),
                        request.expectedOrderVersion())) {
        throw new IllegalStateException(
                "Dữ liệu đã thay đổi; cần tải lại đơn");
    }

    Map<Long, OrderLine> currentById = new HashMap<>();
    for (OrderLine line : order.getLines()) {
        if (line.getId() != null) {
            currentById.put(line.getId(), line);
        }
    }

    Set<Long> submittedIds = new HashSet<>();

    for (LineInput input : request.lines()) {
        if (input == null || input.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "Dòng hàng không hợp lệ");
        }

        if (input.id() == null) {
            order.addLine(
                    new OrderLine(input.sku(), input.quantity()));
            continue;
        }

        if (!submittedIds.add(input.id())) {
            throw new IllegalArgumentException(
                    "ID dòng bị lặp trong request");
        }

        OrderLine existing = currentById.remove(input.id());
        if (existing == null) {
            throw new IllegalArgumentException(
                    "Dòng không thuộc đơn hàng");
        }

        // SKU được coi là bất biến trong ví dụ này.
        if (!existing.getSku().equals(input.sku())) {
            throw new IllegalArgumentException(
                    "Không được đổi SKU của dòng có ID");
        }
        existing.changeQuantity(input.quantity());
    }

    // Chỉ trong endpoint REPLACE toàn bộ.
    for (OrderLine omitted : currentById.values()) {
        order.removeLine(omitted);
    }
}
```

Đoạn code dùng map để phân biệt những dòng hiện có, những dòng mới và những dòng bị bỏ. Nó **giữ nguyên instance managed/ID** cho các dòng đang tồn tại và chỉ tạo entity mới khi yêu cầu không có ID. `order.removeLine(...)` bảo đảm orphan removal qua helper quan hệ hai chiều.

### 13.1. Version check ở đây có giới hạn gì?

`Order.version` được kiểm tra trước khi thay danh sách. Nhưng với quan hệ `@OneToMany(mappedBy="order")`, việc sửa dữ liệu con không phải lúc nào cũng làm version của parent tăng. Nếu hệ thống dùng version của Order để bảo vệ **toàn bộ tập hợp**, phải thiết kế một protocol đảm bảo mọi đường ghi child cũng tham gia kiểm soát version của Order, ví dụ khóa cha hoặc yêu cầu tăng version theo quy tắc nghiệp vụ.

Không thể giả định mọi Hibernate mapping tự tăng `Order.version` mỗi lần thêm/xóa/sửa child. Nếu yêu cầu replace danh sách phải có tính nguyên tử với các request đồng thời, cần xem xét:

- Khóa `Order` theo `PESSIMISTIC_WRITE` khi đọc/thay collection.
- Dùng `OPTIMISTIC_FORCE_INCREMENT` ở đường ghi thích hợp.
- Khai báo `@Version` trên child cho xung đột cập nhật riêng từng dòng.
- Quy ước mọi command tác động cùng aggregate kiểm tra một version thống nhất.

Cách chọn phụ thuộc đặc tính truy cập và transaction isolation. Việc chỉ kiểm tra một Long version từ client chưa đủ nếu có đường ghi khác không cập nhật version đó.

### 13.2. Khi tập hợp rất lớn

Thuật toán trên đọc **toàn bộ collection**, phù hợp với tập con nhỏ và bounded. Nếu một Order có hàng trăm nghìn OrderLine, không nên gửi tất cả trong một request rồi bắt Hibernate load hết để so sánh.

Thay vào đó, thiết kế endpoint theo từng thao tác:

- `POST /orders/{id}/lines` để thêm một dòng.
- `PATCH /orders/{id}/lines/{lineId}` để sửa một dòng.
- `DELETE /orders/{id}/lines/{lineId}` để xóa một dòng.
- API bulk theo chunk có giới hạn rõ và idempotency key nếu nghiệp vụ cần.

Repository truy vấn trực tiếp OrderLine theo `id` và `order.id`, dùng index FK và kiểm soát transaction phù hợp. **Tách thao tác theo child không loại bỏ invariant ở parent**: cùng một protocol xác thực/trạng thái/locking phải được áp dụng.

## 14. Trạng thái managed, detached và merge ảnh hưởng thế nào?

### Managed collection

```java
Order managed = em.find(Order.class, orderId);
managed.addLine(new OrderLine("ORM", 2));
// Flush trong transaction: quan hệ được đồng bộ theo cascade/mapping.
```

### Detached collection

```java
Order detached = loadOrderAndCloseSession(orderId);
// Sau khi session đóng:
detached.addLine(new OrderLine("ORM", 2));
// Java object có thay đổi nhưng không có transaction theo dõi để ghi SQL.
```

Đoạn `loadOrderAndCloseSession()` là ví dụ khái niệm. Nếu collection chưa được khởi tạo trước khi session đóng, việc gọi `addLine()` hoặc `getLines()` trên lazy persistent collection có thể dẫn tới `LazyInitializationException`, tùy thao tác và cách Hibernate quản lý proxy. Không nên coi detached collection như một ArrayList độc lập.

### Merge không có nghĩa “đưa nguyên object này trở lại managed”

```java
Order managedCopy = em.merge(detached);
// managedCopy được quản lý; detached vẫn detached.
```

Với cascade merge, Hibernate có thể sao chép state của graph detached sang graph managed. Nhưng khi client gửi partial graph hoặc có orphan removal, kết quả có thể gây xóa/thêm không mong đợi. Tránh dùng `merge()` như một phương thức thay thế toàn bộ collection từ payload API nếu không hiểu rõ semantics.

Nếu nghiệp vụ cần cập nhật có kiểm soát, nhận DTO, tải entity managed, rồi gọi helper thêm/xóa/thay đúng ID như ở phần trước.

## 15. Lỗi thường gặp khi thao tác với tập hợp có quản lý

| Mẫu code hoặc hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `parent.getChildren().add(child)` nhưng FK không đúng | Chỉ sửa phía inverse của quan hệ hai chiều | Helper đồng bộ collection và `child.parent` |
| Thêm entity mới nhưng không INSERT | Thiếu cascade persist hoặc chưa gọi persist con | Cấu hình cascade phù hợp hoặc persist child |
| `remove()` trả false dù ID giống nhau | Object khác reference; entity equality không phù hợp | Tìm managed child theo ID rồi remove |
| `Set.remove()` không tìm thấy sau persist | Hash code đổi khi generated ID xuất hiện | Dùng hash/equality ổn định với lifecycle |
| Xóa con khiến constraint FK null lỗi | Muốn gỡ association nhưng FK `NOT NULL`, không có orphan removal/xóa con | Xác định rõ “unlink” hay “delete”, sửa mapping/command |
| Xóa role làm ảnh hưởng user khác | Đặt cascade REMOVE/ALL ở many-to-many dùng chung | Gỡ join row, không xóa entity đích |
| Thay `this.children = new ArrayList<>(...)` rồi flush lỗi | Bỏ persistent wrapper, đặc biệt với orphan removal | Giữ collection managed, sửa phần tử trên chính wrapper |
| `list.set(i, newEntity)` làm mất ID cũ | Thay entity thay vì sửa field của entity | Cập nhật managed child nếu identity không đổi |
| `clear()` gây hàng loạt DELETE | Thay toàn bộ tập hợp không kiểm soát | Dùng diff theo ID, hoặc lệnh theo từng phần tử |
| Mất thứ tự sau khi nạp lại | List không có order mapping | `@OrderColumn` hoặc cột sort key rõ ràng |
| Đổi vị trí khiến nhiều UPDATE | `@OrderColumn` phải duy trì index của List | Cân nhắc sort key/entity riêng nếu reorder lớn |
| `LazyInitializationException` | Sửa/truy cập collection chưa load sau khi session đóng | Đặt thao tác trong transaction, query đúng dữ liệu |
| Merge payload thiếu phần tử làm mất dữ liệu | Nhầm PATCH với REPLACE và cascade orphan | DTO commands và semantics API rõ |
| Bulk delete xong collection vẫn có phần tử | Bulk DML bỏ qua state managed trong persistence context | `clear()/refresh()` hoặc session riêng, tránh trộn đường ghi |
| Hai request thay collection đè lên nhau | Thiếu protocol version/locking cho aggregate | Optimistic/pessimistic locking hoặc conditional SQL |
| OOM khi `clear()` collection hàng triệu con | Lazy collection bị materialize | Query từng child, phân trang và thao tác bounded |

## 16. Bulk DML, SQL trực tiếp và persistence context

Khi collection quá lớn, đôi khi cần xóa hàng loạt trong database:

```java
int deleted = em.createQuery(
        "delete from OrderLine l " +
        "where l.order.id = :orderId")
        .setParameter("orderId", orderId)
        .executeUpdate();
```

Đây là **JPQL bulk delete** theo điều kiện, không phải lần lượt gọi `order.removeLine(child)` trên từng child managed. Bulk DML có những khác biệt:

- Không chạy entity lifecycle callbacks và cascade/orphan removal theo cùng đường đi của thao tác entity bình thường.
- Không tự đồng bộ trạng thái các entity và collection đã được load trong persistence context.
- Có thể bỏ qua optimistic locking hoặc domain methods theo cách thông thường; phải thiết kế điều kiện/version nếu nghiệp vụ yêu cầu.
- Foreign key tới bảng khác vẫn được database kiểm tra; việc “xóa hết” có thể fail nếu còn phụ thuộc.

Nếu trước đó trong cùng session đã tải `order.lines`, bulk delete có thể để collection Java chứa những child không còn hàng trong database. Sau bulk DML, hãy quyết định rõ việc `clear()` persistence context, `refresh()` dữ liệu cần thiết hoặc tách sang transaction/session phù hợp. Không tiếp tục flush một graph stale một cách mù quáng.

### Bulk update một trường

```java
int updated = em.createQuery(
        "update OrderLine l " +
        "set l.quantity = :newQuantity " +
        "where l.order.id = :orderId " +
        "and l.sku = :sku")
        .setParameter("newQuantity", 5)
        .setParameter("orderId", orderId)
        .setParameter("sku", "JAVA")
        .executeUpdate();
```

Câu lệnh trên không gọi `OrderLine.changeQuantity()`, nên validation trong method Java bị bỏ qua. Nếu quantity phải dương, database `CHECK(quantity > 0)` là lớp bảo vệ bổ sung quan trọng. Với bulk update, cần xác định có cần audit, version và đồng bộ cache hay không.

## 17. Xóa entity cha và vòng đời của các phần tử

Với `@OneToMany(cascade=ALL, orphanRemoval=true)` ở Order, việc xóa Order có thể kéo theo xóa các OrderLine trước khi database cho phép xóa parent:

```java
Order order = em.find(Order.class, orderId);
em.remove(order);
```

Khi số child lớn, cascade remove trên cả object graph có thể nặng: Hibernate phải xử lý trạng thái entity, callback, SQL và ràng buộc theo mapping. Nếu một parent có 500.000 child, cân nhắc chiến lược xóa theo chunk, archive/soft-delete, hoặc `ON DELETE CASCADE` ở database khi phù hợp.

Ví dụ database:

```sql
ALTER TABLE order_lines
    DROP CONSTRAINT order_lines_order_id_fkey;

ALTER TABLE order_lines
    ADD CONSTRAINT fk_order_lines_orders
    FOREIGN KEY (order_id)
    REFERENCES orders(id)
    ON DELETE CASCADE;
```

Đoạn DDL trên **chỉ minh họa cú pháp PostgreSQL**. Tên constraint thật khác nhau tùy migration. Không chạy thao tác DROP constraint chưa xác định trong môi trường có dữ liệu. Database cascade khác ORM cascade: xóa child do database thực thi có thể không chạy callback entity của Hibernate; persistence context và cache cần chính sách nhất quán.

Nếu OrderLine có lịch sử/audit hoặc được entity khác tham chiếu, có thể không được xóa vật lý; chuyển trạng thái `CANCELLED` hoặc lưu bản ghi archive sẽ phù hợp hơn. Quy tắc này thuộc domain, không thể suy ra chỉ từ `orphanRemoval`.

## 18. Đồng thời và tính toàn vẹn của collection

Hai transaction có thể cùng thay một collection:

```text
Transaction A                        Transaction B
─────────────                        ─────────────
load Order #100                      load Order #100
load lines: [201, 202]               load lines: [201, 202]
add line 203                         remove line 202
             ...                 ...
commit                               commit
```

Kết quả cuối cùng phụ thuộc SQL, isolation, version và constraint. Không thể suy ra Hibernate tự phát hiện mọi xung đột chỉ vì Order có `@Version`. Với `mappedBy`, thao tác child có thể không tăng parent version; version riêng trên child cũng không bảo vệ việc hai transaction cùng thêm các phần tử trùng business key.

Một số công cụ bảo vệ:

- **Unique constraint:** ví dụ `UNIQUE(order_id, sku)` nếu mỗi SKU chỉ được có một lần trong Order. Chặn duplicate dù hai request cùng kiểm tra “chưa có”.
- **Optimistic locking:** `@Version` cho entity cần bảo vệ, kết hợp policy rõ ràng với các thao tác thêm/xóa child.
- **Pessimistic lock trên cha:** mọi command cập nhật tập dòng đều khóa cùng Order khi cần serialize thay đổi.
- **Conditional DML:** chỉ cập nhật/xóa nếu trạng thái/phiên bản điều kiện còn đúng.
- **Idempotency:** nếu API retry sau timeout, bảo đảm không tạo hai dòng vì cùng một yêu cầu.

Ví dụ khóa Order khi thực hiện nghiệp vụ cần độc quyền trên tập dòng:

```java
import jakarta.persistence.LockModeType;

@Transactional
public void addLineWithOrderLock(Long orderId,
                                 String sku,
                                 int quantity) {
    Order order = em.find(
            Order.class, orderId, LockModeType.PESSIMISTIC_WRITE);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }

    // Kiểm tra state và uniqueness theo nghiệp vụ.
    order.addLine(new OrderLine(sku, quantity));
}
```

Nếu tất cả transaction sửa tập dòng đều khóa Order theo cùng protocol, mức độ cạnh tranh sẽ được kiểm soát tốt hơn nhưng có thể tăng thời gian chờ/khả năng deadlock. Cần đặt transaction ngắn, tránh gọi dịch vụ mạng trong lúc giữ lock và xử lý lỗi lock timeout.

## 19. Các bài toán dùng List, Set và Map trong thực tế

### A. Danh sách thành viên được phân vai

Một `Project.members` là `Set<User>` qua many-to-many. “Thêm thành viên” thêm một join row. “Xóa thành viên” gỡ join row; User vẫn tồn tại. Nếu cần `joinedAt`, `inviteStatus` hoặc `roleInProject` riêng, entity `ProjectMembership` rõ hơn một Set many-to-many thuần.

### B. Danh sách dòng giỏ hàng

Mỗi dòng có quantity, unit price, coupon, mã hàng. Nếu các dòng được quản lý theo ID và cần audit, dùng child entity. Cập nhật số lượng trên dòng đang managed giữ nguyên identity; xóa dòng với orphan removal có thể xóa row tương ứng. Đồng bộ cả giỏ hàng từ client cần version/semantics replace đầy đủ.

### C. Nhãn bài viết

Vài nhãn string, không có metadata: `@ElementCollection Set<String>`. Đổi nhãn dùng remove + add. Khi nhãn có state duyệt hoặc tác giả gắn nhãn, xem xét entity `ArticleTagAssignment` với ID hoặc composite key, tránh coi toàn bộ association là một String.

### D. Thứ tự bài hát trong danh sách phát

Nếu chỉ cần một playlist ngắn chứa tên bài hát, `List<String>` với `@OrderColumn` có thể đủ. Khi mỗi entry có ID, thời điểm thêm, ghi chú, số lượt phát và rất nhiều thao tác reorder, entity `PlaylistEntry` với sort key riêng thường dễ kiểm soát hơn. `List.set(index, track)` phải được diễn giải rõ là đổi bài ở một vị trí hay tạo một entry mới.

### E. Tập các địa chỉ giao hàng

Nếu address là value object và được thay trọn, collection embeddable có thể phù hợp. Nếu mỗi địa chỉ có ID, xác minh, người quản lý, thời gian hết hạn hoặc được nhiều đơn hàng tham chiếu, entity riêng hợp lý hơn. Không sử dụng `equals()` của entity để giải thích equality theo giá trị của địa chỉ.

## 20. Một quy trình thực hành cho mọi thao tác collection

Khi chuẩn bị viết `add()`, `remove()` hoặc `set()` trên entity, hãy xác định lần lượt:

**1. Entity cha có managed trong transaction không?** Nếu detached, thay đổi Java không tự ghi SQL. Nếu lazy collection chưa được tải, tránh truy cập sau khi session đóng.

**2. Collection thuộc mapping gì?** `@ElementCollection`, `@OneToMany` hay `@ManyToMany` quyết định phần tử là value/entity và việc xóa ảnh hưởng đến hàng nào.

**3. Ai là owning side?** Với `@OneToMany(mappedBy="parent")`, FK thuộc child `@ManyToOne`. Khi sửa association hai chiều, cập nhật cả hai phía trong memory.

**4. Phần tử có identity riêng không?** Nếu sửa cùng một entity, cập nhật field. Nếu thay entity, xác định orphan removal và FK. Nếu chỉ đổi value, chọn thao tác value collection phù hợp.

**5. Cascade nào được cấp?** Thêm transient child có cần `persist()` riêng? Xóa parent có tự cascade remove không? Many-to-many dùng chung không được vô tình cascade xóa entity đích.

**6. Collection có lưu thứ tự không?** `@OrderColumn`, `@OrderBy` hay không có cả hai? Đừng giả định vị trí trong Java List đồng nhất với vị trí SQL.

**7. Kích thước bao nhiêu?** Với tập hợp lớn, tránh load tất cả để xóa một phần tử. Query child theo ID và FK, phân trang, bulk theo chiến lược phù hợp.

**8. Có cạnh tranh không?** Xác định version/lock/unique constraint và semantics khi hai request cùng thêm, xóa hoặc thay danh sách.

**9. Có cần giữ Hibernate wrapper không?** Đối với managed collection, ưu tiên sửa trên collection hiện tại và helper domain; không gán list mới tùy tiện.

**10. Flush, commit và lỗi được xử lý ra sao?** Lỗi SQL có thể xuất hiện muộn ở flush/commit. Rollback transaction, đóng/bỏ session bị lỗi và giữ nguyên nguyên nhân để chẩn đoán.

## 21. Tổng hợp bằng sơ đồ

```text
                        ENTITY MANAGED
                              │
                   Collection bị thay đổi?
                              │
                ┌─────────────┴──────────────┐
                │                            │
        @ElementCollection                Quan hệ entity
                │                            │
       Thêm/xóa/thay value          ┌─────────┴─────────┐
                │                   │                   │
       Collection table         @OneToMany         @ManyToMany
       INSERT/DELETE/...            │                   │
                                    │                   │
                          Ai sở hữu FK?          Ai sở hữu join table?
                          Có cascade?            Gỡ liên kết, giữ Role/
                          Có orphanRemoval?      Tag/User dùng chung
                                    │                   │
                                    ├── thêm child       └── INSERT/DELETE
                                    ├── sửa child            join row
                                    ├── gỡ association
                                    └── xóa orphan
                                    │
                            Flush SQL phù hợp
                                    │
                                    ▼
                             COMMIT / ROLLBACK
```

Thêm, xóa và thay thế phần tử trên một collection Hibernate được quản lý cần được hiểu là **thay đổi mô hình quan hệ và vòng đời entity**, không chỉ thay đổi `List`/`Set` trong Java. Với value collection, Hibernate đồng bộ các giá trị thuộc owner; với one-to-many, owning side, cascade và orphan removal quyết định sự tồn tại của child; với many-to-many, thao tác thường chỉ thêm/xóa liên kết giữa hai entity độc lập. Khi giữ collection wrapper được quản lý, dùng helper đồng bộ hai phía và đặt thao tác trong transaction có chính sách concurrency rõ ràng, các thay đổi Java sẽ biểu đạt đúng nghiệp vụ và được Hibernate đồng bộ xuống database theo mapping đã chọn.
