# `orphanRemoval` khi phần tử không còn thuộc quan hệ

Trong Jakarta Persistence và Hibernate, `orphanRemoval = true` mô tả một quy tắc vòng đời rất cụ thể: **khi một entity con không còn thuộc quan hệ `@OneToOne` hoặc `@OneToMany` được đánh dấu orphan removal, thao tác xóa entity con sẽ được áp dụng khi flush**.

Ví dụ một `PurchaseOrder` sở hữu các `OrderLine`. Nếu người dùng xóa một dòng hàng khỏi đơn, dòng đó không còn ý nghĩa độc lập và phải bị xóa khỏi database:

```java
order.removeLine(line);
```

Với `orphanRemoval = true`, thao tác này có thể khiến Hibernate phát `DELETE` cho chính hàng `order_lines`, không chỉ gỡ khóa ngoại hay xóa một hàng liên kết.

Điều quan trọng là `orphanRemoval` diễn đạt **quyền sở hữu vòng đời** (*private ownership*): entity con phụ thuộc vào entity cha và không được dùng chung hoặc chuyển tùy ý sang quan hệ khác. Nó khác `CascadeType.REMOVE`, khác việc xóa một hàng trong join table, và khác `ON DELETE CASCADE` của database.

Bài học tập trung vào thời điểm một phần tử trở thành orphan, cách giữ hai phía quan hệ nhất quán, hành vi khi xóa cha, các giới hạn với entity mới/detached/được chuyển owner, và cách kiểm thử để tránh xóa nhầm dữ liệu.

## 1. Orphan là gì trong mô hình entity?

Giả sử một đơn hàng có ba dòng:

```text
PurchaseOrder #500
  ├─ OrderLine #1: SKU-A, quantity=2
  ├─ OrderLine #2: SKU-B, quantity=1
  └─ OrderLine #3: SKU-C, quantity=4
```

Mỗi `OrderLine` là một entity có định danh riêng trong database. Tuy nhiên, trong domain này, một dòng hàng chỉ có ý nghĩa như một phần của đơn hàng chứa nó.

Nếu người dùng bỏ `OrderLine #2`, trạng thái nghiệp vụ mong muốn là:

```text
PurchaseOrder #500
  ├─ OrderLine #1
  └─ OrderLine #3

OrderLine #2: bị xóa khỏi database
```

Đây là trường hợp **orphan removal**. Entity con đã bị loại khỏi quan hệ sở hữu và không được giữ lại như một bản ghi độc lập.

Nếu chỉ xóa liên kết mà vẫn giữ entity con, trạng thái có thể là:

```text
PurchaseOrder #500
  ├─ OrderLine #1
  └─ OrderLine #3

OrderLine #2: vẫn tồn tại, không còn order_id
```

Hai kết quả này khác nhau về lifecycle. `orphanRemoval` chọn kết quả đầu tiên.

### 1.1. Không phải mọi phần tử bị bỏ khỏi collection đều là orphan

Hãy hỏi: **sau khi bị gỡ khỏi quan hệ, entity đó có còn ý nghĩa và có thể được quản lý độc lập không?**

| Phần tử | Có nên orphan removal? | Lý do |
| --- | --- | --- |
| `OrderLine` riêng của một đơn hàng | Thường có | Dòng hàng phụ thuộc vòng đời đơn |
| `Address` riêng của một `Customer` | Có thể | Địa chỉ có thể là thành phần riêng tư của customer |
| `User` trong danh sách thành viên của `Team` | Thường không | User tồn tại độc lập và có thể tham gia team khác |
| `Product` được tham chiếu từ `OrderLine` | Không | Product là dữ liệu dùng chung |
| `Tag` dùng chung bởi nhiều bài viết | Không | Gỡ tag khỏi một bài không có nghĩa xóa tag |
| `InvoiceAttachment` chỉ thuộc một invoice | Có thể | Tệp đính kèm có lifecycle phụ thuộc invoice |

Đừng chọn `orphanRemoval = true` chỉ vì muốn tự động dọn dữ liệu. Trước tiên phải xác định quyền sở hữu và lifecycle của entity con.

## 2. Khai báo `orphanRemoval`

Jakarta Persistence cho phép thuộc tính này trên:

- `@OneToOne`
- `@OneToMany`

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Hoặc:

```java
@OneToOne(
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
@JoinColumn(name = "profile_id")
private CustomerProfile profile;
```

`orphanRemoval` là thuộc tính của association mapping. Không có thuộc tính `orphanRemoval` trên `@ManyToMany` hoặc `@ElementCollection`.

### 2.1. Phạm vi ý nghĩa

| Annotation | Có thể khai báo `orphanRemoval`? | Đối tượng bị tác động |
| --- | --- | --- |
| `@OneToMany` | Có | Entity đích bị loại khỏi quan hệ |
| `@OneToOne` | Có | Entity đích bị thay thế hoặc tách khỏi quan hệ |
| `@ManyToMany` | Không | Chỉ gỡ liên kết; entity ở đầu kia thường được dùng chung |
| `@ElementCollection` | Không | Giá trị trong collection table được thêm/xóa theo collection mapping |

`@ElementCollection` không cần orphan removal vì phần tử là basic value hoặc embeddable, không phải entity có lifecycle độc lập. Khi bỏ một giá trị, Hibernate đồng bộ hàng tương ứng trong collection table.

## 3. Ví dụ `@OneToMany` hai chiều với `Order` và `OrderLine`

Trong ví dụ này, mỗi `OrderLine` thuộc riêng một `PurchaseOrder`. Entity con không được chuyển sang đơn hàng khác sau khi đã trở thành orphan.

### 3.1. Entity cha

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException(
                "OrderLine already belongs to another order"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
        }

        line.assignTo(this);
    }

    public boolean removeLine(OrderLine line) {
        if (!lines.remove(line)) {
            return false;
        }

        line.detachFromOrder();
        return true;
    }
}
```

### 3.2. Entity con

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 18, scale = 2)
    private BigDecimal unitPrice;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        this.sku = Objects.requireNonNull(sku);

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    void assignTo(PurchaseOrder order) {
        this.order = Objects.requireNonNull(order);
    }

    void detachFromOrder() {
        this.order = null;
    }
}
```

Các class trên minh họa mapping Jakarta Persistence hiện đại. `PurchaseOrder.lines` là inverse side vì có `mappedBy = "order"`; `OrderLine.order` là owning side của khóa ngoại `order_id`.

### 3.3. Vì sao helper method cập nhật cả hai phía?

Trong quan hệ hai chiều, có hai biểu diễn trong bộ nhớ:

```text
PurchaseOrder.lines  ↔  OrderLine.order
```

Khi thêm:

```java
order.addLine(line);
```

helper phải:

1. Thêm `line` vào `order.lines`.
2. Gán `line.order = order`.

Khi gỡ:

```java
order.removeLine(line);
```

helper phải:

1. Xóa `line` khỏi `order.lines`.
2. Xóa tham chiếu `line.order` trong object graph.
3. Để orphan removal xử lý lifecycle xóa entity khi flush.

**Owning side quyết định cập nhật FK trong quan hệ hai chiều.** Chỉ thay đổi collection inverse mà không đồng bộ `OrderLine.order` có thể làm object graph mâu thuẫn với mapping và khiến SQL không như dự kiến. Hãy giữ hai phía nhất quán qua helper method.

`detachFromOrder()` trong ví dụ đặt field về `null` trong bộ nhớ. Vì entity đã trở thành orphan, Hibernate cần xóa nó theo `orphanRemoval`; không thiết kế thao tác này như cách giữ một hàng con với FK `NULL`. Schema `order_id NOT NULL` thể hiện rằng một `OrderLine` đã lưu luôn phải thuộc một order.

## 4. Khi gỡ một phần tử khỏi collection managed

Giả sử order đã được load và managed:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = em.find(PurchaseOrder.class, 500L);
    OrderLine line = findLine(order, 2L);

    order.removeLine(line);

    em.flush();
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

`findLine()` là helper tìm phần tử trong collection theo ID, ví dụ:

```java
private static OrderLine findLine(PurchaseOrder order, Long lineId) {
    return order.getLines().stream()
        .filter(line -> line.getId().equals(lineId))
        .findFirst()
        .orElseThrow();
}
```

Khi `order.removeLine(line)` được gọi, Hibernate ghi nhận thay đổi membership của collection. Đến flush, entity con bị orphan được đưa vào quy trình remove theo semantics của `orphanRemoval`.

Kết quả nghiệp vụ mong muốn:

```text
Trước:
  purchase_orders: 500
  order_lines:     1, 2, 3

Sau commit:
  purchase_orders: 500
  order_lines:     1, 3
```

Với mapping FK trực tiếp, SQL cuối cùng có thể bao gồm:

```sql
DELETE FROM order_lines
WHERE id = 2;
```

Không nên dựa vào **chính xác một câu SQL hoặc thứ tự statement cụ thể**. Hibernate có thể phát thêm SQL cho association, collection, callbacks hoặc batching tùy mapping và phiên bản. Điều cần kiểm chứng là hàng `order_lines` đã bị xóa sau commit và các constraint vẫn hợp lệ.

### 4.1. Thời điểm xóa là flush

`removeLine()` chỉ thay đổi object graph và collection managed. Theo semantics JPA, thao tác remove do orphan removal được áp dụng **tại thời điểm flush**.

Các thời điểm flush thường gặp:

- Gọi `em.flush()` tường minh.
- Trước commit theo flush mode.
- Trước query trong một số trường hợp `FlushModeType.AUTO`.
- Một số thao tác cần SQL sớm do chiến lược sinh ID hoặc mapping.

Vì vậy, ngay sau:

```java
order.removeLine(line);
```

không nên suy luận rằng SQL `DELETE` đã chạy. Database chỉ được đồng bộ khi flush thích hợp.

### 4.2. Flush không phải commit

```text
BEGIN
  order.removeLine(line)
  FLUSH   → DELETE có thể đã chạy trong transaction
  ROLLBACK
```

Nếu transaction rollback, database khôi phục hàng đã xóa theo transaction semantics. `orphanRemoval` không biến thao tác xóa thành một hành động ngoài transaction.

## 5. Nếu không bật `orphanRemoval` thì sao?

Thay mapping bằng:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
```

Giả sử helper vẫn gỡ phần tử và đặt `line.order = null`. Khi flush, với FK nullable, Hibernate có thể phát:

```sql
UPDATE order_lines
SET order_id = NULL
WHERE id = 2;
```

Hàng `order_lines` vẫn còn trong database, chỉ không còn thuộc order cũ.

Nếu `order_id NOT NULL`, thao tác unlink như vậy không hợp lệ: database sẽ từ chối việc đặt FK thành `NULL`. Khi entity con cần được giữ độc lập, schema và domain phải cho phép trạng thái không có parent hoặc phải chuyển nó tới owner khác theo một quy trình hợp lệ.

Với mapping unidirectional `@OneToMany` dùng join table, gỡ phần tử thường xóa hàng trong join table; entity con có thể vẫn tồn tại trong bảng entity.

| Hành vi khi gỡ phần tử | `orphanRemoval = true` | `orphanRemoval = false` |
| --- | --- | --- |
| Gỡ khỏi collection | Có | Có |
| Xóa entity con | Có, khi orphan semantics áp dụng và flush | Không tự động |
| Giữ hàng con trong DB | Không, sau khi remove được thực thi | Có thể |
| FK nullable có thể được đặt `NULL` | Không phải mục tiêu; con bị xóa | Có thể, tùy mapping |
| Dùng khi con có lifecycle độc lập | Thường không phù hợp | Có thể phù hợp |
| Dùng khi con chỉ tồn tại trong owner | Phù hợp | Cần xóa con bằng cách khác nếu không muốn giữ orphan |

Đừng nhầm “không có `orphanRemoval`” với “entity con không thể bị xóa”. Ứng dụng vẫn có thể gọi `em.remove(line)` trực tiếp hoặc cấu hình cascade remove khi xóa cha.

## 6. `orphanRemoval` khác `CascadeType.REMOVE`

Đây là khác biệt quan trọng nhất khi học cascade và delete.

- `CascadeType.REMOVE` lan truyền thao tác xóa **từ cha sang con khi cha bị remove**.
- `orphanRemoval = true` xóa entity con **khi con bị loại khỏi quan hệ**, ngoài hành vi xóa con khi cha bị remove.

Bảng so sánh:

| Tình huống | `cascade = REMOVE` | `orphanRemoval = true` |
| --- | --- | --- |
| Xóa parent | Remove được cascade tới target entity | Remove được cascade tới target entity |
| Gỡ một child khỏi collection | Không tự xóa child | Xóa child khi flush |
| Thay child trong OneToOne | Không tự xóa child cũ chỉ vì thay tham chiếu | Child cũ trở thành orphan và bị xóa |
| Child cần tồn tại độc lập | Có thể phù hợp | Không phù hợp với private ownership |
| Ý nghĩa | Propagate remove operation | Lifecycle của child gắn với association |

Theo Jakarta Persistence, khi `orphanRemoval = true` được khai báo trên `@OneToOne` hoặc `@OneToMany`, việc cascade remove khi xóa source entity đã được bao hàm; khai báo thêm `CascadeType.REMOVE` là dư thừa cho riêng hành vi đó.

Tuy nhiên, orphan removal **không tự bật mọi cascade khác**. Nếu muốn persist child mới cùng parent, vẫn cần `CascadeType.PERSIST` hoặc gọi `persist(child)` riêng. Nếu muốn merge graph theo cascade, cần cân nhắc `CascadeType.MERGE`.

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Mapping này chọn PERSIST/MERGE tường minh và dùng orphan removal cho lifecycle xóa khi gỡ con. Không cần thêm REMOVE chỉ để xóa con khi parent bị xóa, vì orphanRemoval đã bao hàm semantics đó theo đặc tả.

## 7. Xóa parent cũng xóa các child thuộc quan hệ orphan removal

Khi xóa toàn bộ đơn:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 500L);
em.remove(order);
```

Với `orphanRemoval = true`, thao tác remove được cascade tới các entity đích của quan hệ. Các `OrderLine` thuộc order sẽ được remove theo lifecycle của chúng.

Về mặt dữ liệu:

```text
Trước:
  purchase_orders: 500
  order_lines:     1, 2, 3

Sau commit:
  purchase_orders: không còn 500
  order_lines:     không còn 1, 2, 3
```

Hibernate phải thực thi DML tương thích với FK. Một trình tự SQL minh họa:

```sql
DELETE FROM order_lines WHERE id = 1;
DELETE FROM order_lines WHERE id = 2;
DELETE FROM order_lines WHERE id = 3;
DELETE FROM purchase_orders WHERE id = 500;
```

SQL thực tế có thể batch các DELETE hoặc sử dụng chiến lược khác. Điều quan trọng là database không bị để lại FK tham chiếu tới parent đã xóa.

### 7.1. `orphanRemoval` không đồng nghĩa xóa mọi thứ được tham chiếu gián tiếp

Nếu `OrderLine` tham chiếu `Product`:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Product product;
```

xóa `OrderLine` không có nghĩa xóa `Product`. Quan hệ từ line tới product có lifecycle riêng. `Product` là dữ liệu dùng chung và thường không nên nhận cascade REMOVE từ order line.

Cẩn trọng với `CascadeType.ALL` trên những quan hệ hướng tới entity dùng chung. Cascade REMOVE có thể xóa nhầm product, customer hoặc user mà các aggregate khác đang sử dụng.

## 8. `orphanRemoval` trong `@OneToOne`

Một hồ sơ có thể sở hữu một cấu hình riêng:

```java
@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {

    @Id
    private Long id;

    @OneToOne(
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    @JoinColumn(name = "profile_id", unique = true)
    private CustomerProfile profile;

    protected CustomerAccount() {
    }

    public CustomerProfile getProfile() {
        return profile;
    }

    public void replaceProfile(CustomerProfile replacement) {
        this.profile = replacement;
    }

    public void removeProfile() {
        this.profile = null;
    }
}
```

Nếu account đang có `CustomerProfile #10` và gán profile mới:

```java
account.replaceProfile(new CustomerProfile(...));
```

profile cũ bị loại khỏi association và trở thành orphan. Khi flush, Hibernate áp dụng remove semantics cho profile cũ.

Nếu đặt:

```java
account.removeProfile();
```

profile hiện tại cũng trở thành orphan và sẽ bị xóa khi flush.

### 8.1. Không thay thế một profile đang được dùng chung

Nếu `CustomerProfile` là một entity có thể được nhiều account tham chiếu, nó không phải private-owned target thích hợp cho orphan removal. Với quan hệ dùng chung, việc thay tham chiếu của một account chỉ nên gỡ association; không nên xóa entity mà account khác cần.

Đối với `@OneToOne`, unique FK thường bảo đảm một profile chỉ được liên kết với tối đa một account qua cột đó. Nhưng constraint schema **không thay thế quyết định lifecycle**: cần xác định profile có thật sự thuộc riêng account hay không.

## 9. Vì sao `@ManyToMany` không có orphan removal?

Giả sử một `Article` có nhiều `Tag`, và một `Tag` được dùng trong nhiều article:

```text
Article A ──┬── Tag: java
            └── Tag: hibernate

Article B ────── Tag: java
```

Khi bỏ tag `java` khỏi Article A, chỉ association A–java cần bị gỡ. `Tag: java` vẫn được Article B sử dụng.

Mapping:

```java
@ManyToMany
@JoinTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Khi gọi:

```java
article.removeTag(javaTag);
```

Hibernate xóa hàng tương ứng khỏi `article_tags`; entity `Tag` vẫn tồn tại.

Không có `orphanRemoval` trên `@ManyToMany`, bởi target entity thường có thể được chia sẻ. Nếu bật cascade REMOVE tùy tiện, việc xóa một article có thể xóa tag còn được các article khác sử dụng.

### 9.1. Nếu quan hệ cần thuộc tính riêng thì dùng association entity

Nếu bảng liên kết có `addedAt`, `addedBy`, `position` hoặc trạng thái riêng, có thể ánh xạ bảng đó thành entity, ví dụ `ArticleTagAssignment`:

```java
@Entity
@Table(name = "article_tag_assignments")
public class ArticleTagAssignment {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Article article;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Tag tag;

    @Column(name = "added_at", nullable = false)
    private Instant addedAt;
}
```

Sau đó Article sở hữu các assignment:

```java
@OneToMany(
    mappedBy = "article",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<ArticleTagAssignment> tagAssignments = new ArrayList<>();
```

Khi gỡ assignment, entity `ArticleTagAssignment` bị xóa, còn `Tag` vẫn tồn tại. Đây là cách mô hình hóa đúng khi **bản thân liên kết** có lifecycle riêng.

## 10. `@ElementCollection` đã có semantics xóa giá trị riêng

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "order_labels",
    joinColumns = @JoinColumn(name = "order_id")
)
@Column(name = "label")
private Set<String> labels = new HashSet<>();
```

Khi gọi:

```java
order.getLabels().remove("priority");
```

Hibernate đồng bộ việc xóa giá trị khỏi collection table. `String` không phải entity đích, không có `@Id` và không có entity lifecycle để gọi remove.

Do đó:

- Không khai báo `orphanRemoval` trên `@ElementCollection`.
- Không dùng `CascadeType.REMOVE` cho value.
- Xóa một value không có nghĩa xóa entity owner.
- Xóa owner có thể kéo theo dữ liệu collection theo mapping/database behavior.

## 11. Private ownership: quy tắc quan trọng nhất

Jakarta Persistence mô tả orphan removal dành cho entity **được sở hữu riêng bởi parent entity**. Điều này dẫn tới các quy tắc thiết kế:

1. Child không được dùng chung bởi nhiều parent.
2. Khi child rời parent, nghiệp vụ muốn xóa child.
3. Child không được chuyển sang association khác sau khi đã trở thành orphan.
4. Không phụ thuộc vào một thứ tự xóa cụ thể ngoài những semantics được đặc tả.
5. Nếu child cần tồn tại độc lập, không nên dùng orphan removal.

Ví dụ hợp lý:

```text
PurchaseOrder
  └── OrderLine

OrderLine không có ý nghĩa độc lập sau khi bị bỏ khỏi order.
```

Ví dụ không hợp lý:

```text
Team A ── User #10
Team B ── User #10

Bỏ User #10 khỏi Team A không được xóa User #10.
```

Nếu một entity có thể chuyển owner, hãy thiết kế nó như entity có lifecycle độc lập và thay đổi FK/association theo transaction. Không dùng orphan removal như một cách “tự dọn” rồi cố gán lại cùng entity sang parent mới.

## 12. Không reassign entity đã trở thành orphan

Đặc tả Jakarta Persistence nêu rõ ứng dụng portable **không được phụ thuộc vào một thứ tự remove cụ thể** và **không được gán lại một entity đã trở thành orphan sang quan hệ khác**.

Ví dụ không nên làm:

```java
PurchaseOrder oldOrder = em.find(PurchaseOrder.class, 1L);
PurchaseOrder newOrder = em.find(PurchaseOrder.class, 2L);

OrderLine line = findLine(oldOrder, 10L);

oldOrder.removeLine(line); // line trở thành orphan.
newOrder.addLine(line);    // Không nên tái sử dụng orphan này.
```

Với `orphanRemoval = true`, Hibernate có thể lên lịch xóa `line` khi flush. Việc thêm lại nó vào parent khác trong cùng unit of work tạo ra xung đột giữa ý định remove và reassignment; kết quả có thể phụ thuộc provider, thứ tự action hoặc mapping.

### 12.1. Nếu nghiệp vụ là chuyển child từ A sang B

Nếu `OrderLine` thật sự được phép chuyển, hãy bỏ orphan removal cho association đó và thiết kế một thao tác transfer có chủ đích:

```java
public void transferLineTo(
        PurchaseOrder target,
        OrderLine line) {

    if (!lines.remove(line)) {
        throw new IllegalArgumentException("Line is not in this order");
    }

    line.assignTo(target);
    target.addExistingLine(line);
}
```

Đây chỉ là phác thảo domain method; implementation thực tế phải tránh thêm trùng, đồng bộ hai collection và owning side, kiểm tra quyền/điều kiện nghiệp vụ và chạy trong một transaction.

Schema cần cho phép FK chuyển từ order A sang order B. Nếu `OrderLine` có ID, lịch sử hoặc tham chiếu riêng, nó là entity có lifecycle độc lập; orphan removal thường không phải mapping phù hợp.

Nếu dòng hàng chỉ thuộc riêng một order, khi cần “chuyển” có thể tạo một `OrderLine` mới trong order đích và xóa line cũ, đồng thời ghi nhận lịch sử nghiệp vụ nếu cần.

## 13. Entity mới, detached và removed: các giới hạn của orphan semantics

Đây là chi tiết dễ bị bỏ qua trong Jakarta Persistence: nếu entity bị orphan là **new, detached hoặc removed**, semantics của `orphanRemoval` không áp dụng theo cùng cách như entity managed đã tồn tại.

### 13.1. Entity mới chưa từng persist

```java
OrderLine line = new OrderLine(
    "SKU-X", 1, new BigDecimal("10.00")
);

order.addLine(line);
order.removeLine(line);
```

Nếu `line` chưa từng được persist và chưa có hàng trong database, không có hàng entity cũ để xóa. Không dựa vào orphan removal như cơ chế thay thế việc quản lý object mới trong Java.

### 13.2. Entity detached

```java
em.detach(line);
order.removeLine(line);
```

Một object detached không còn được dirty-check như managed entity trong context đó. Đừng kỳ vọng chỉ thay đổi collection bằng một object detached sẽ tạo ra hành động xóa portable.

Hãy tải entity managed trong transaction rồi thực hiện thao tác remove theo đúng aggregate; hoặc thiết kế merge flow rõ ràng và kiểm thử provider cụ thể.

### 13.3. Entity đã removed

Nếu entity đã được gọi `em.remove(line)`, việc tiếp tục gỡ hoặc tái sử dụng nó trong collection không phải cách quản lý lifecycle hợp lệ. Không thêm một entity đã removed trở lại association rồi mong ORM tự khôi phục trạng thái.

### 13.4. Vì sao đặc tả giới hạn các trường hợp này?

Orphan removal được thiết kế để quản lý entity con **đang được quản lý và thuộc riêng parent**. Nó không phải cơ chế tổng quát quét mọi object graph detached/new và suy luận rằng mọi phần tử vắng mặt đều phải DELETE.

## 14. Unidirectional và bidirectional: vị trí FK không làm đổi ý nghĩa orphan

`orphanRemoval` có thể được dùng với `@OneToMany` một chiều hoặc hai chiều. Vị trí FK và SQL chi tiết phụ thuộc mapping.

### 14.1. Hai chiều với FK trong bảng con

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

`OrderLine.order` sở hữu `order_id`. Gỡ một line làm nó thành orphan và Hibernate xóa entity con khi flush.

### 14.2. Một chiều với `@JoinColumn`

```java
@OneToMany(
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
@JoinColumn(name = "order_id")
private List<OrderLine> lines = new ArrayList<>();
```

Quan hệ được khai báo ở parent nhưng FK nằm trong bảng entity đích `order_lines`. Khi gỡ phần tử, target entity vẫn là orphan và phải bị xóa theo semantics. Không được hiểu rằng `@JoinColumn` biến thao tác thành “chỉ đặt FK null” khi orphan removal được bật.

### 14.3. Một chiều với join table

```java
@OneToMany(
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
@JoinTable(
    name = "purchase_order_lines",
    joinColumns = @JoinColumn(name = "order_id"),
    inverseJoinColumns = @JoinColumn(name = "line_id")
)
private List<OrderLine> lines = new ArrayList<>();
```

Ở đây có bảng liên kết. Khi orphan removal được kích hoạt, Hibernate phải xử lý cả association rows lẫn entity target theo mapping. Cần quan sát SQL thật vì việc đồng bộ collection một chiều qua join table có thể phát nhiều câu DELETE/INSERT hơn số phần tử thực sự đổi.

Dù dùng kiểu mapping nào, **orphan removal là lifecycle rule của entity đích**. Vị trí FK chỉ quyết định cách quan hệ được lưu và cập nhật.

## 15. Orphan removal và thứ tự SQL

Một thao tác gỡ line có thể tạo nhiều việc:

1. Đánh dấu thay đổi collection.
2. Xác định entity con bị orphan.
3. Lập kế hoạch remove entity.
4. Xử lý FK/association cần thiết.
5. Thực thi DELETE khi flush.

Hibernate có action riêng cho orphan removal trong ActionQueue. Nhưng không nên lấy một thứ tự nội bộ cụ thể làm cam kết portable cho mọi provider/version.

Ví dụ SQL minh họa với FK trực tiếp:

```sql
DELETE FROM order_lines
WHERE id = 2;
```

Với join table, có thể thấy thêm:

```sql
DELETE FROM purchase_order_lines
WHERE order_id = 500 AND line_id = 2;
```

Tùy mapping, Hibernate có thể batch hoặc đồng bộ collection theo chiến lược riêng. Nếu có FK, unique constraint, trigger hay association phức tạp, database kiểm tra từng statement theo semantics của nó.

### 15.1. Không phải DELETE nào cũng là orphan delete

Phân biệt:

| SQL DELETE tác động vào | Ý nghĩa |
| --- | --- |
| Bảng entity `order_lines` | Xóa entity con |
| Bảng join `purchase_order_lines` | Gỡ association row |
| Bảng collection `order_labels` | Xóa value row |
| Bảng entity `purchase_orders` | Xóa parent |
| Bảng con qua database `ON DELETE CASCADE` | Database tự xóa do FK rule |

Nhìn thấy một câu `DELETE` trong log chưa đủ để kết luận orphan removal đã xóa entity. Hãy xem **tên bảng, khóa điều kiện và trạng thái cuối**.

## 16. `orphanRemoval` không phải `ON DELETE CASCADE`

Hai cơ chế có phạm vi khác nhau:

- `orphanRemoval = true` là lifecycle behavior ở ORM khi association bị loại bỏ hoặc source entity bị remove.
- `ON DELETE CASCADE` là constraint/action của database khi hàng được tham chiếu bị xóa.

Ví dụ:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

Nếu xóa parent bằng SQL trực tiếp, database có thể xóa các hàng con mà không cần Hibernate quản lý entity graph.

Ngược lại, nếu chỉ gỡ một child khỏi collection mà không xóa parent, `ON DELETE CASCADE` **không được kích hoạt**, vì không có thao tác xóa parent.

Một hệ thống có thể kết hợp ORM orphan removal và database cascade có chủ đích, nhưng phải hiểu provider có phát DELETE từng child hay dựa vào DB. Không mặc định hai cơ chế tự động đồng bộ trạng thái cache hoặc lifecycle callbacks giống nhau.

## 17. Cascade REMOVE, orphan removal và soft delete

Orphan removal diễn đạt thao tác remove của entity đích. Nếu ứng dụng dùng soft delete, cần biết cách soft delete được triển khai:

- Nếu Hibernate map thao tác remove thành câu SQL cập nhật cờ/xóa logic theo extension phù hợp, orphan removal có thể đi qua remove path đó.
- Nếu soft delete chỉ được thực hiện bằng service method tùy chỉnh, orphan removal không tự gọi method nghiệp vụ đó.
- Nếu database trigger thay DELETE thành một hành động khác, Hibernate vẫn có semantics remove ở ORM nhưng dữ liệu vật lý có thể được giữ lại.

Vì vậy, đừng mặc định `orphanRemoval = true` luôn có nghĩa **hard delete vật lý** trong mọi hệ thống. Nó yêu cầu remove lifecycle; SQL cuối cùng chịu ảnh hưởng mapping, Hibernate extension và database.

Nếu cần audit ai đã bỏ một order line, phải ghi nhận actor/reason/time bằng lifecycle callback, entity listener, service/domain event hoặc audit system thích hợp. Orphan removal tự nó không cung cấp đầy đủ business audit context.

## 18. Cascade PERSIST/MERGE và orphan removal là các lựa chọn riêng

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Ý nghĩa:

- `PERSIST`: khi persist order, persist các line mới được cascade.
- `MERGE`: khi merge order, merge các target theo cascade và semantics merge.
- `orphanRemoval`: xóa entity con khi nó không còn thuộc quan hệ.
- Không cần `REMOVE` chỉ để có hành vi remove khi xóa parent, vì orphanRemoval đã bao hàm remove cascade cho association đó.

Nếu viết:

```java
@OneToMany(orphanRemoval = true)
private List<OrderLine> lines;
```

điều đó **không tự động đồng nghĩa cascade PERSIST/MERGE**. Khi tạo parent với child mới, ứng dụng vẫn phải persist child theo cách hợp lệ hoặc khai báo cascade persist.

### 18.1. Không lạm dụng `CascadeType.ALL`

`CascadeType.ALL` gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH. Nó có thể phù hợp khi child thực sự hoàn toàn phụ thuộc parent. Nhưng nếu quan hệ chỉ cần persist/merge và orphan deletion, khai báo rõ từng cascade giúp người đọc hiểu lifecycle.

Quan trọng hơn, không dùng `ALL` trên quan hệ tới entity dùng chung như `Product`, `User` hoặc `Tag` nếu điều đó có thể lan truyền REMOVE ngoài ý muốn.

## 19. Detached graph, `merge()` và nguy cơ xóa nhầm orphan

Một lỗi thực tế thường xuất hiện khi API nhận DTO hoặc detached entity có collection.

Giả sử:

```text
Thời điểm A tải order:
  lines = [1, 2]

Transaction B thêm line 3 và commit:
  database lines = [1, 2, 3]

A gửi lại object/DTO cũ:
  lines = [1, 2]
```

Nếu ứng dụng merge một detached graph cũ với cascade MERGE và orphan removal, provider có thể xem những phần tử vắng mặt trong trạng thái được merge là đã bị loại khỏi association, dẫn tới xóa orphan. Chi tiết merge collection và trạng thái loaded/unloaded phụ thuộc mapping/provider; **không coi payload cũ là bản cập nhật an toàn**.

### 19.1. Không biến field bị thiếu trong PATCH thành collection rỗng

Một API có thể nhận:

```json
{
  "id": 500,
  "status": "CONFIRMED"
}
```

Nếu mapper khởi tạo `lines = []` cho field không được gửi, rồi merge toàn bộ object, ứng dụng có thể vô tình diễn giải “không gửi danh sách” thành “xóa hết dòng hàng”.

Cần phân biệt:

- Field không xuất hiện trong request: không yêu cầu thay đổi collection.
- Collection rỗng rõ ràng: người dùng muốn xóa hết hay chỉ không gửi phần tử?
- Một command xóa cụ thể: người dùng muốn loại đúng child ID nào?

### 19.2. Tải managed aggregate và áp dụng command tường minh

Một cách an toàn hơn cho API cập nhật từng phần:

```java
@Transactional
public void removeOrderLine(long orderId, long lineId) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

    OrderLine line = order.getLines().stream()
        .filter(candidate -> candidate.getId().equals(lineId))
        .findFirst()
        .orElseThrow();

    order.removeLine(line);
}
```

Đây là ví dụ Spring-style; repository và exception là thành phần ứng dụng. Service tải aggregate managed trong transaction, xác định đúng child, rồi gọi hành động domain cụ thể. Hibernate phát orphan removal khi flush/commit.

Nếu dữ liệu có thể được cập nhật đồng thời, thêm version/locking phù hợp cho aggregate hoặc child và xử lý stale request. Đừng dùng một detached collection snapshot cũ làm nguồn chân lý cho mọi thay đổi.

## 20. `@Version` và concurrent orphan removal

Giả sử hai request cùng thao tác trên một order:

```text
A: load Order#500, lines=[1,2]
B: load Order#500, lines=[1,2]

A: remove line 1
B: sửa quantity của line 1
```

Một transaction muốn xóa entity, transaction còn lại muốn cập nhật nó. Kết quả phụ thuộc mapping, versioning, transaction isolation và thứ tự flush. Nếu line có `@Version`, thao tác UPDATE/DELETE phù hợp có thể phát hiện stale version; nếu không, các race có thể dẫn tới update/delete conflict hoặc outcome không như nghiệp vụ mong muốn.

### 20.1. Version ở child và version ở parent có scope khác nhau

- `@Version` trên `OrderLine` bảo vệ optimistic update/delete của **hàng line** khi provider áp dụng version check.
- `@Version` trên `PurchaseOrder` bảo vệ state/version của **hàng order**.
- Không mặc định mọi thay đổi trên collection inverse tự động tăng version của parent trong mọi mapping/provider.
- Nếu aggregate invariant yêu cầu mọi thay đổi line phải xung đột qua root version, có thể thiết kế force increment/lock trên root hoặc một cơ chế cập nhật version tường minh.

Ví dụ yêu cầu: “Hai request không được đồng thời thay đổi cấu trúc dòng hàng của cùng một order mà không phát hiện conflict.” Cần kiểm thử trên mapping thực tế và chọn version/lock scope phù hợp; chỉ thêm `@Version` vào một entity bất kỳ chưa chắc bảo vệ toàn bộ aggregate.

### 20.2. Không retry mù quáng sau delete conflict

Nếu transaction bị optimistic lock hoặc deadlock khi xóa orphan:

1. Rollback transaction lỗi.
2. Bỏ persistence context không còn phù hợp.
3. Đọc lại aggregate trong transaction mới.
4. Kiểm tra child còn tồn tại và còn thuộc parent không.
5. Quyết định hành động nghiệp vụ: đã bị xóa, đã chuyển trạng thái hay cần báo conflict.
6. Retry có giới hạn chỉ khi command idempotent và vẫn hợp lệ.

Nếu child đã bị người khác xóa, retry cùng lệnh có thể được coi là thành công idempotent hoặc trả 404/409 tùy API contract. Đây là quyết định nghiệp vụ, không phải annotation tự chọn thay ứng dụng.

## 21. Orphan removal và database constraints

Mapping JPA không thay thế schema constraints.

Với quan hệ `Order`–`OrderLine`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_order_lines_quantity
        CHECK (quantity > 0)
);
```

Các constraint bảo vệ:

- FK: không cho `order_lines.order_id` tham chiếu order không tồn tại.
- NOT NULL: mỗi line đã lưu phải có order.
- CHECK: quantity phải dương.
- UNIQUE nếu domain yêu cầu không trùng SKU trong cùng order, ví dụ `(order_id, sku)`.

Orphan removal xử lý lifecycle qua ORM. FK/NOT NULL/CHECK/UNIQUE bảo vệ dữ liệu ở database, kể cả khi có SQL ngoài Hibernate.

### 21.1. Vì sao FK không tự xóa orphan khi gỡ collection?

FK chỉ biểu diễn tham chiếu. Nếu gọi unlink và đặt FK thành NULL, database không biết đó là “orphan phải xóa” hay “entity được phép tồn tại độc lập”. `orphanRemoval` là quy tắc ORM cung cấp ngữ nghĩa đó.

Nếu muốn database tự xóa child khi parent bị xóa, dùng `ON DELETE CASCADE` phù hợp. Nó không tương đương với việc gỡ child khỏi collection.

## 22. Tương tác với `@OnDelete`

Hibernate có extension `@OnDelete` để khai báo hành vi cascade delete ở database cho FK trong những mapping phù hợp:

```java
@OnDelete(action = OnDeleteAction.CASCADE)
```

Đây là Hibernate-specific, không phải thuộc tính thay thế trực tiếp cho `orphanRemoval`.

| Cơ chế | Kích hoạt khi | Nơi thực thi |
| --- | --- | --- |
| `orphanRemoval = true` | Entity con bị loại khỏi OneToOne/OneToMany sở hữu riêng | ORM lifecycle |
| `CascadeType.REMOVE` | Source entity bị remove | ORM cascade |
| `@OnDelete(CASCADE)` | DDL/FK được cấu hình và hàng được tham chiếu bị xóa | Database |
| `ON DELETE CASCADE` | DELETE parent row | Database |

Database cascade có thể hữu ích khi xóa lượng lớn child, nhưng nếu database tự xóa mà Hibernate không xử lý từng entity, persistence context hoặc second-level cache có thể cần chiến lược đồng bộ/invalidation phù hợp.

Đặc biệt, `@OnDelete` không tự biến việc bỏ một phần tử khỏi collection thành orphan removal. Khi cần xóa child vì nó bị gỡ khỏi association, phải dùng lifecycle mapping phù hợp.

## 23. Kiểm thử orphan removal bằng integration test

Unit test chỉ gọi `removeLine()` có thể xác nhận collection trong Java thay đổi, nhưng **chưa chứng minh hàng con bị xóa khỏi database**. Cần test với Hibernate và database test có mapping thật.

### 23.1. Test gỡ child và kiểm tra sau commit

Giả định `EntityManagerFactory emf` đã được tạo, order có ID `500`, line `2` đã được seed:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrphanRemovalTest {

    private final EntityManagerFactory emf;

    OrphanRemovalTest(EntityManagerFactory emf) {
        this.emf = emf;
    }

    @Test
    void removingLineDeletesChildRow() {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order = em.find(PurchaseOrder.class, 500L);
            assertNotNull(order);

            OrderLine line = order.getLines().stream()
                .filter(item -> item.getId().equals(2L))
                .findFirst()
                .orElseThrow();

            assertTrue(order.removeLine(line));

            em.flush();
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }

        try (EntityManager verifyEm = emf.createEntityManager()) {
            assertNull(verifyEm.find(OrderLine.class, 2L));
        }
    }
}
```

Đây là test body minh họa; cần fixture JUnit tạo `emf`, seed data, cleanup và import đầy đủ. JUnit 5 không tự inject `EntityManagerFactory` vào constructor nếu không cấu hình extension phù hợp.

Điểm đáng chú ý: kiểm tra bằng **EntityManager mới** sau commit, tránh đọc lại một managed instance cũ trong first-level cache.

### 23.2. Test không orphan removal thì child vẫn tồn tại

Dùng một mapping test riêng không bật orphan removal và schema cho phép unlink:

```java
// Mapping minh họa: FK nullable và orphanRemoval=false.
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

Sau khi gỡ child và đồng bộ owning side, kiểm tra:

```java
assertNotNull(verifyEm.find(OrderLine.class, lineId));
```

Hàng entity vẫn tồn tại, dù association với parent đã bị gỡ. Không dùng cùng một class mapping rồi thay annotation giữa lúc chạy; hãy tạo fixture/entity test riêng hoặc persistence unit riêng.

### 23.3. Test rollback

```java
tx.begin();

PurchaseOrder order = em.find(PurchaseOrder.class, 500L);
OrderLine line = findLine(order, 2L);

order.removeLine(line);
em.flush();

tx.rollback();
```

Sau rollback, dùng `EntityManager` mới để kiểm tra `OrderLine#2` vẫn tồn tại và association vẫn đúng. Test này chứng minh orphan delete tham gia transaction, không phải xóa vật lý ngoài transaction.

### 23.4. Test xóa parent

Xóa `PurchaseOrder#500`, commit, rồi kiểm tra:

```java
assertNull(verifyEm.find(PurchaseOrder.class, 500L));
assertNull(verifyEm.find(OrderLine.class, 1L));
assertNull(verifyEm.find(OrderLine.class, 2L));
assertNull(verifyEm.find(OrderLine.class, 3L));
```

Đây là kiểm thử semantics parent remove cascade qua orphanRemoval. Nếu có FK từ bảng khác tới order line, phải seed và xử lý đúng các dependency đó.

### 23.5. Test shared target của ManyToMany

Tạo hai article cùng tham chiếu một tag. Gỡ tag khỏi article A, commit, rồi xác nhận:

- Hàng association A–tag đã biến mất.
- Article B vẫn tham chiếu tag.
- Hàng entity `Tag` vẫn tồn tại.

Test này bảo vệ ứng dụng khỏi lỗi cấu hình cascade REMOVE trên target dùng chung.

## 24. Kiểm tra SQL và trạng thái entity

Bật SQL logging trong môi trường test:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

Hoặc dùng logger phù hợp với Hibernate version:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Khi gỡ child với orphan removal, hãy quan sát:

1. SQL nào tác động tới bảng liên kết/collection table?
2. Có DELETE tới bảng entity con không?
3. Khi xóa parent, child rows có được xử lý trước khi parent row bị xóa không?
4. Có FK/NOT NULL/UNIQUE violation không?
5. Rollback có phục hồi trạng thái database không?

Không bật bind-parameter logging ở production nếu giá trị có thể chứa dữ liệu nhạy cảm.

### 24.1. Không assert số SQL cố định một cách portable

Một integration test có thể assert **trạng thái database cuối** và các invariant. Không nên yêu cầu mọi provider luôn phát đúng một câu DELETE, vì:

- Join table có thể cần xóa association row.
- Collection mapping có thể tạo nhiều statement.
- JDBC batching thay đổi cách gửi statement.
- Hibernate version/dialect có thể thay đổi SQL.
- Callback, audit, soft-delete hoặc trigger có thể bổ sung thao tác.

Nếu dự án phụ thuộc vào SQL shape để đạt hiệu năng, viết test/benchmark riêng trên đúng Hibernate version và DBMS production.

## 25. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Gỡ child khỏi collection nhưng hàng con vẫn còn | `orphanRemoval=false` | Bật orphan removal nếu child thực sự private-owned, hoặc gọi remove tường minh |
| Gỡ child làm lỗi FK NOT NULL | Mapping không orphan-delete nhưng cố đặt FK NULL | Xác định unlink hay delete; chọn lifecycle/schema phù hợp |
| Xóa parent làm mất entity dùng chung | Cascade REMOVE/ALL trên association không thuộc quyền sở hữu | Bỏ cascade remove và mô hình hóa shared reference |
| Thêm lại child đã bị gỡ gây lỗi khó đoán | Đã orphan rồi lại reassign trong cùng unit of work | Không tái sử dụng orphan; thiết kế transfer không dùng orphanRemoval |
| `removeLine()` không tìm thấy child | `equals()`/`hashCode()` sai hoặc object khác persistence context | Tìm theo ID trong managed collection; kiểm tra equality |
| Gỡ ở parent nhưng FK không đổi | Chỉ sửa inverse collection, không đồng bộ owning side | Helper cập nhật cả `parent.children` và `child.parent` |
| DTO PATCH làm xóa tất cả child | Mapper biến field thiếu thành collection rỗng rồi merge graph | Phân biệt absent/null/empty và áp dụng command tường minh |
| `merge()` của graph cũ gây mất child | Detached collection snapshot stale | Load managed aggregate, áp dụng delta và concurrency check |
| Entity mới add rồi remove gây kỳ vọng DELETE | Orphan semantics không áp dụng cho new entity | Quản lý transient object trong Java; không giả định có row để xóa |
| Child detached bị gỡ nhưng không có DELETE | Orphan tracking cần managed lifecycle | Load managed child/aggregate trong transaction |
| Gỡ ManyToMany xóa target entity | Cascade REMOVE trên entity dùng chung | Chỉ gỡ association; không cascade delete target |
| `@ElementCollection` không nhận `orphanRemoval` | Annotation không áp dụng cho value collection | Dùng collection mapping semantics |
| SQL DELETE xuất hiện nhưng target vẫn còn | DELETE chỉ tác động join/collection table | Kiểm tra bảng entity và trạng thái sau commit |
| Rollback xong object Java vẫn thay đổi | Persistence context/object graph không tự phục hồi mọi field như database | Bỏ context sau rollback, đọc lại bằng context mới |
| Concurrent update và orphan delete xung đột | Hai transaction sửa/xóa cùng child | Dùng version/lock, rollback và xử lý conflict |

## 26. Quy trình quyết định có dùng `orphanRemoval` không

Trước khi bật annotation, trả lời các câu hỏi sau:

**1. Child có thuộc riêng parent không?** Nếu child có thể được nhiều parent dùng chung hoặc có lifecycle độc lập, không dùng orphan removal.

**2. Gỡ khỏi quan hệ có nghĩa xóa entity không?** Nếu chỉ muốn unlink, chọn `orphanRemoval=false` và thiết kế FK nullable/association table phù hợp.

**3. Có cần chuyển child sang owner khác không?** Nếu có, không orphan child rồi reassign; thiết kế transfer với lifecycle độc lập.

**4. Quan hệ là OneToOne hay OneToMany?** Đây là hai association hỗ trợ orphanRemoval trong Jakarta Persistence. ManyToMany và ElementCollection không có thuộc tính này.

**5. Cascade PERSIST/MERGE có cần riêng không?** Orphan removal không tự thay thế những cascade đó.

**6. Hai phía association có được cập nhật đồng bộ không?** Với mapping hai chiều, helper method phải duy trì owning side.

**7. Có detached graph hoặc PATCH request không?** Không để một collection snapshot thiếu dữ liệu vô tình bị hiểu là lệnh xóa hàng loạt.

**8. Có concurrency không?** Kiểm tra version/locking và xử lý stale request khi nhiều transaction cùng sửa cấu trúc collection.

**9. Database constraints đã đúng chưa?** PK/FK/UNIQUE/NOT NULL/CHECK phải phản ánh lifecycle mong muốn.

**10. Có cần audit/soft delete không?** `orphanRemoval` yêu cầu remove semantics; nó không tự ghi lý do xóa hoặc quyết định retention.

## 27. Bài tập tình huống

### Bài 1 — Bỏ một dòng đơn hàng

`PurchaseOrder.lines` có `orphanRemoval=true`. Gọi `order.removeLine(line)` trên aggregate managed rồi commit. Kết quả mong muốn ở database là gì?

**Đáp án:** Entity `OrderLine` bị remove và hàng trong `order_lines` bị xóa khi flush/commit thành công.

### Bài 2 — Chỉ có Cascade REMOVE

Mapping có `cascade=REMOVE` nhưng `orphanRemoval=false`. Gỡ một line khỏi collection, còn giữ parent. Line có tự bị xóa không?

**Đáp án:** Không. Cascade REMOVE lan khi source parent bị remove; nó không tự xóa child chỉ vì association bị gỡ.

### Bài 3 — Xóa parent

Parent có `orphanRemoval=true`, rồi gọi `em.remove(parent)`. Có cần thêm `CascadeType.REMOVE` chỉ để xóa child không?

**Đáp án:** Không cần cho riêng semantics remove cascade đó; orphanRemoval trên OneToOne/OneToMany đã bao hàm việc remove target khi source bị remove. Các cascade PERSIST/MERGE vẫn là lựa chọn riêng.

### Bài 4 — Chuyển child sang parent mới

Một `OrderLine` bị remove khỏi order A rồi add vào order B trong cùng transaction, trong khi A dùng orphanRemoval. Có nên dựa vào provider để xử lý?

**Đáp án:** Không. Đặc tả yêu cầu ứng dụng portable không phụ thuộc thứ tự remove cụ thể và không reassign entity đã trở thành orphan. Nếu cần transfer, dùng mapping/lifecycle không có orphanRemoval và thao tác owning-side FK tường minh.

### Bài 5 — User trong nhiều Team

Một `User` tham gia Team A và Team B. Gỡ User khỏi Team A có nên xóa entity User?

**Đáp án:** Không. User có lifecycle độc lập và được dùng chung. Gỡ association, không orphan-delete target.

### Bài 6 — Tag của Article

`Article.tags` là ManyToMany. Có thể thêm `orphanRemoval=true` không?

**Đáp án:** Không. ManyToMany không hỗ trợ thuộc tính này; gỡ tag chỉ xóa join row. Nếu cần lifecycle cho quan hệ, tạo association entity và orphan-remove association entity.

### Bài 7 — Child mới chưa persist

Tạo line mới, add vào order, rồi remove ngay trước lần persist/flush đầu tiên. Có nên kỳ vọng orphan removal phát DELETE?

**Đáp án:** Không. Orphan semantics không áp dụng cho entity mới; chưa có row persistent để xóa.

### Bài 8 — DTO không gửi collection

API PATCH chỉ gửi status nhưng mapper biến `lines` thành danh sách rỗng rồi merge. Điều gì có thể xảy ra?

**Đáp án:** Ứng dụng có thể vô tình diễn giải trạng thái collection là đã gỡ các line, dẫn tới orphan deletion. Cần phân biệt field absent và collection empty, tải managed aggregate và áp dụng field/command được gửi.

### Bài 9 — FK NOT NULL

Mapping không có orphanRemoval nhưng helper đặt `line.order = null`. Database báo NOT NULL. Vì sao?

**Đáp án:** Ứng dụng đang yêu cầu unlink và giữ entity, nhưng schema không cho phép line tồn tại mà không có order. Phải quyết định delete, transfer hoặc đổi schema.

### Bài 10 — Rollback

Sau khi gỡ line và `flush()`, transaction rollback. Hàng database có còn không?

**Đáp án:** Có, nếu database transaction rollback thành công. Flush không phải commit. Nên xác nhận bằng EntityManager mới vì object trong context đã dùng có thể vẫn phản ánh thao tác Java trước rollback.

### Bài 11 — Soft delete

Entity dùng soft delete qua custom SQL. `orphanRemoval=true` có tự ghi actor và lý do xóa không?

**Đáp án:** Không. Orphan removal yêu cầu remove lifecycle; audit context và reason phải do domain/service/listener/audit system thiết kế riêng.

### Bài 12 — Cạnh tranh update/delete

Transaction A xóa line, transaction B cập nhật quantity cùng line. Cần xem gì?

**Đáp án:** Version của child, lock/isolation, thứ tự commit và cách provider phát hiện stale delete/update. Rollback transaction xung đột và xử lý lại nghiệp vụ trong context mới.

## 28. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): mục relationship mappings và orphan removal; phạm vi OneToOne/OneToMany, private ownership, thời điểm flush và giới hạn reassign.
- [Jakarta Persistence 3.2 — `@OneToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToMany.html): thuộc tính `orphanRemoval`, `cascade`, `mappedBy` và association semantics.
- [Jakarta Persistence 3.2 — `@OneToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToOne.html): orphan removal trong quan hệ một-một.
- [Jakarta Persistence 3.2 — `CascadeType`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CascadeType.html): ý nghĩa các thao tác cascade PERSIST, MERGE, REMOVE, REFRESH và DETACH.
- [Hibernate ORM User Guide — One-to-many associations](https://docs.hibernate.org/stable/orm/userguide/html_single/#associations-one-to-many): mapping hai chiều/một chiều, collection lifecycle, orphan removal và SQL.
- [Hibernate ORM User Guide — One-to-one associations](https://docs.hibernate.org/stable/orm/userguide/html_single/#associations-one-to-one): mapping một-một và lifecycle association.
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing): thời điểm ORM đồng bộ entity/collection changes và transaction.
- [Hibernate ORM User Guide — Database-level cascade](https://docs.hibernate.org/stable/orm/userguide/html_single/#associations-on-delete): phân biệt database `ON DELETE CASCADE` với ORM lifecycle.
- [PostgreSQL Documentation — Foreign Key Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): FK, NOT NULL, UNIQUE và hành vi cascade ở database.

Các ví dụ dùng namespace `jakarta.persistence.*`. Dự án Hibernate cũ dùng `javax.persistence.*` cần đối chiếu đúng version API/provider. SQL trong bài là minh họa; thứ tự statement, batching, soft-delete SQL và cách xử lý collection phụ thuộc mapping, Hibernate version và DBMS.

## Kết luận

`orphanRemoval = true` dành cho quan hệ `@OneToOne` hoặc `@OneToMany` trong đó entity đích **thuộc riêng parent**. Khi entity con không còn thuộc quan hệ được quản lý, Hibernate/JPA áp dụng remove semantics tại flush; khi parent bị xóa, thao tác remove cũng được cascade tới target. Vì thế `orphanRemoval` khác `CascadeType.REMOVE`: một bên xử lý việc **gỡ con**, bên kia mô tả việc **xóa cha** lan xuống con.

Không bật orphan removal cho entity dùng chung hoặc cần chuyển owner. Với quan hệ hai chiều, giữ collection và owning side đồng bộ; với detached graph, tránh biến field thiếu thành collection rỗng; với entity mới/detached/removed, không giả định orphan semantics giống một child managed đã tồn tại. Kết hợp lifecycle mapping với FK/constraint, transaction, version/locking và integration tests để bảo đảm **một thao tác gỡ phần tử chỉ xóa đúng entity được domain xác định là orphan**.
