# Cascade từ gốc aggregate theo quyền sở hữu nghiệp vụ trong Hibernate ORM

Trong một mô hình domain, một đối tượng thường bao gồm nhiều thực thể có liên quan. Ví dụ, một đơn hàng gồm các dòng hàng; một hóa đơn gồm các dòng chi tiết; một bài viết gồm các đoạn nội dung thuộc quyền quản lý của bài viết. Khi lưu hoặc xóa đối tượng chính, ứng dụng có thể muốn thao tác persistence được lan truyền đến các thành phần bên trong.

Hibernate/Jakarta Persistence hỗ trợ cơ chế **cascade** để truyền một số thao tác vòng đời từ entity này sang entity liên quan. Tuy nhiên, việc chọn cascade không nên dựa trên suy nghĩ “hai entity có quan hệ thì cứ dùng `CascadeType.ALL`”. Cần xác định **entity nào sở hữu vòng đời của entity nào trong nghiệp vụ**.

Một `Order` có thể sở hữu vòng đời của `OrderLine`: tạo order thì tạo các line, xóa order thì xóa các line. Nhưng `Order` không sở hữu vòng đời của `Customer` hay `Product`: khách hàng và sản phẩm tồn tại độc lập, được nhiều đơn hàng cùng tham chiếu. Nếu cascade xóa từ order sang customer hoặc product, xóa một đơn có thể vô tình xóa dữ liệu dùng chung.

Bài học giải thích cách đặt cascade từ **aggregate root** theo quyền sở hữu nghiệp vụ, phân biệt nó với phía sở hữu quan hệ trong ORM, lựa chọn từng loại cascade, sử dụng `orphanRemoval`, và phối hợp với khóa ngoại database khi xóa.

## 1. Aggregate root và quyền sở hữu vòng đời

Trong Domain-Driven Design (DDD), **aggregate** là một nhóm đối tượng được quản lý như một đơn vị nhất quán. **Aggregate root** là điểm vào chính để bên ngoài thay đổi aggregate; root chịu trách nhiệm bảo vệ các invariant của nhóm.

Ví dụ đơn hàng:

```text
PurchaseOrder (aggregate root)
    |
    +-- OrderLine
    |      |
    |      +-- product reference
    |
    +-- OrderLine
           |
           +-- product reference

PurchaseOrder tham chiếu Customer
```

Trong mô hình này:

- `PurchaseOrder` là aggregate root.
- `OrderLine` là thành phần thuộc vòng đời của order.
- `Customer` là aggregate/entity độc lập.
- `Product` là entity/catalog độc lập được line tham chiếu.

Quy tắc nghiệp vụ có thể là:

- Không có `OrderLine` nếu không có order chứa nó.
- Mỗi `OrderLine` chỉ thuộc một order.
- Xóa order đồng nghĩa xóa các line của order.
- Xóa order không xóa customer hoặc product.
- Việc thay đổi số lượng line phải đi qua thao tác của order để kiểm tra trạng thái, giá và các invariant.

Đó là **quyền sở hữu nghiệp vụ**. Hibernate không tự suy ra khái niệm aggregate root từ entity graph. Lập trình viên thể hiện nó qua API domain, repository boundary, mapping cascade và quy tắc transaction.

### 1.1. Aggregate không chỉ là một sơ đồ quan hệ

Một entity có association tới entity khác không có nghĩa nó sở hữu entity kia.

Ví dụ:

```java
class PurchaseOrder {
    private Customer customer;
    private List<OrderLine> lines;
}
```

Cả `customer` và `lines` đều là association trong Java. Nhưng semantics khác nhau:

- Customer là tham chiếu tới đối tượng có vòng đời riêng.
- Lines là tập thành phần được order quản lý.

Cascade cần phản ánh khác biệt này.

### 1.2. Aggregate root kiểm soát thay đổi

Một cách thiết kế:

```java
order.addLine(product, quantity);
order.changeLineQuantity(lineId, newQuantity);
order.removeLine(lineId);
```

Các method của root có thể kiểm tra:

- Order còn ở trạng thái cho phép sửa không?
- Product có hợp lệ không?
- Quantity có dương không?
- Có vượt hạn mức hoặc chính sách đặt hàng không?
- Xóa line có cần cập nhật tổng tiền không?

Nếu tầng controller hoặc service bên ngoài tự sửa trực tiếp mọi `OrderLine` mà bỏ qua root, các invariant có thể bị phá vỡ dù cascade mapping hoàn toàn đúng.

**Cascade là cơ chế lan truyền thao tác persistence; aggregate root là ranh giới bảo vệ nghiệp vụ.** Hai khái niệm bổ trợ nhau nhưng không thay thế nhau.

## 2. Phân biệt aggregate ownership với owning side của JPA

Đây là điểm dễ nhầm nhất khi thiết kế cascade.

Trong JPA, **owning side** của association là phía quyết định cập nhật quan hệ trong database, thường là phía chứa khóa ngoại. Trong DDD, **aggregate root** là entity có trách nhiệm kiểm soát vòng đời và invariant của nhóm.

Hai vai trò có thể nằm ở hai phía khác nhau.

Ví dụ:

```java
@Entity
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
public class OrderLine {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;
}
```

Ở đây:

- `PurchaseOrder` là aggregate root theo nghiệp vụ.
- `OrderLine.order` là owning side của association vì cột `order_id` nằm trong bảng `order_lines`.
- `PurchaseOrder.lines` là inverse side vì dùng `mappedBy = "order"`.
- Cascade được khai báo từ root xuống các line để thao tác persistence lan theo quyền sở hữu.

Sơ đồ:

```text
Nghiệp vụ:
PurchaseOrder (root) ----owns lifecycle----> OrderLine

JPA mapping:
PurchaseOrder.lines (inverse side)
OrderLine.order      (owning side)
                              |
                              v
                       order_lines.order_id
```

**Cascade có thể được khai báo ở association từ root, dù root không phải owning side của khóa ngoại.** Khi thêm hoặc gỡ line, code vẫn phải cập nhật owning side để Hibernate ghi đúng FK.

### 2.1. Vì sao phải cập nhật cả hai phía?

Với mapping hai chiều, nếu chỉ làm:

```java
order.getLines().add(line);
```

nhưng không đặt `line.order`, object graph không nhất quán. Vì `OrderLine.order` sở hữu khóa ngoại, Hibernate có thể không ghi `order_id` như mong muốn.

Helper domain nên cập nhật cả hai:

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.assignTo(this);
}
```

Và khi bỏ line:

```java
public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.assignTo(null);
    }
}
```

Ví dụ này giả định line được phép tách khỏi order trong bộ nhớ trước khi orphan removal được áp dụng; với FK NOT NULL và orphanRemoval, thao tác xóa line cần được thực hiện theo lifecycle phù hợp. Không nên flush một trạng thái line còn tồn tại nhưng `order_id` đã null nếu schema cấm null.

## 3. Các loại CascadeType trong Jakarta Persistence

Jakarta Persistence định nghĩa các thao tác cascade sau:

| Cascade type | Thao tác được lan truyền | Ý nghĩa |
|---|---|---|
| `PERSIST` | `EntityManager.persist` | Khi persist root, persist các entity liên quan có cấu hình cascade |
| `MERGE` | `EntityManager.merge` | Khi merge root, merge các entity liên quan |
| `REMOVE` | `EntityManager.remove` | Khi remove root, remove các entity liên quan |
| `REFRESH` | `EntityManager.refresh` | Khi refresh root, refresh các entity liên quan |
| `DETACH` | `EntityManager.detach` | Khi detach root, detach các entity liên quan |
| `ALL` | Tất cả các thao tác trên | Tương đương khai báo tất cả cascade type |

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<OrderLine> lines = new ArrayList<>();
```

`CascadeType.ALL` là cách viết gọn:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines = new ArrayList<>();
```

Không có một loại cascade riêng tên “SAVE”. Trong Spring Data, `save` thường chọn persist hoặc merge theo cơ chế nhận diện entity mới; cascade thực tế vẫn phụ thuộc các thao tác JPA tương ứng.

### 3.1. PERSIST: tạo mới cả aggregate

Khi root mới được persist:

```java
PurchaseOrder order = new PurchaseOrder(customer);

order.addLine(new OrderLine(productA, 2));
order.addLine(new OrderLine(productB, 1));

entityManager.persist(order);
```

Nếu association root-to-lines có `cascade = PERSIST`, Hibernate lan thao tác persist đến các line mới.

Điều này hợp lý khi line chỉ có ý nghĩa như thành phần của order. Ứng dụng không cần gọi `persist(line)` riêng cho từng phần tử.

Nhưng nếu `customer` là entity đã tồn tại, không nên đặt cascade PERSIST từ order sang customer. Khi đó, persist order có thể cố persist customer detached và gây lỗi `detached entity passed to persist`.

### 3.2. MERGE: hợp nhất trạng thái của aggregate

`CascadeType.MERGE` cho phép thao tác merge từ root lan đến các entity liên quan.

Ví dụ:

```java
PurchaseOrder managed = entityManager.merge(detachedOrder);
```

Nếu lines có cascade MERGE, Hibernate có thể merge các line thuộc graph đầu vào. Kết quả trả về là managed instance; object detached truyền vào không tự biến thành managed.

MERGE hữu ích khi ứng dụng thực sự cần hợp nhất detached graph. Tuy nhiên, một graph từ request không đầy đủ có thể ghi đè trường hoặc association không được gửi lên. Với API cập nhật từng phần, thường an toàn hơn khi tải root managed rồi áp dụng command có chủ đích.

### 3.3. REMOVE: xóa thành phần thuộc vòng đời root

Nếu order sở hữu line:

```java
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class,
    orderId
);

entityManager.remove(order);
```

Với cascade REMOVE từ order xuống lines, thao tác remove lan đến các line. Điều này phù hợp nếu không có line nào được chia sẻ hoặc tồn tại độc lập ngoài order.

Không cascade REMOVE tới `Customer` hoặc `Product` dùng chung. Nếu xóa một order mà xóa luôn customer, những order khác có thể mất tham chiếu hoặc dữ liệu dùng chung bị phá hủy.

### 3.4. REFRESH: nạp lại state từ database

`CascadeType.REFRESH` có thể phù hợp khi entity con là một phần của cùng aggregate và cần refresh đồng bộ với root.

Tuy nhiên, refresh sẽ thay state trong bộ nhớ bằng dữ liệu database hiện có, nên có thể làm mất những thay đổi chưa flush. Không dùng REFRESH như cách “đồng bộ nhẹ” sau khi sửa entity.

Với association tới entity độc lập/shared, cascade REFRESH cũng cần cân nhắc: refresh một order không nhất thiết nên làm mới mọi customer/product liên quan.

### 3.5. DETACH: tách cả graph

`CascadeType.DETACH` lan thao tác detach đến entity liên quan. Nó có thể hữu ích khi muốn tách một aggregate được quản lý cùng nhau, nhưng cũng có thể làm entity shared reference bị detach khỏi persistence context hiện tại.

Detach không xóa dữ liệu. Nó chỉ ngừng quản lý các entity liên quan trong persistence context.

### 3.6. ALL không có nghĩa “mọi thứ”

`CascadeType.ALL` chỉ là tất cả **các thao tác cascade JPA** nêu trên. Nó không có nghĩa:

- Fetch eager toàn bộ graph.
- Tự tạo khóa ngoại hoặc ràng buộc database.
- Bảo vệ mọi invariant nghiệp vụ.
- Tự động xóa theo một chính sách soft-delete.
- Cascade mọi bulk JPQL/native SQL.
- Gửi sự kiện, email hoặc gọi service ngoài.
- Làm cho entity liên quan trở thành thành phần aggregate chỉ vì annotation.

## 4. Mô hình Order, OrderLine, Customer và Product

Hãy xác định quyền sở hữu trước khi viết annotation.

| Entity | Vai trò nghiệp vụ | Vòng đời do ai quản lý? | Cascade từ Order? |
|---|---|---|---|
| `PurchaseOrder` | Aggregate root | Tự quản lý | Không áp dụng |
| `OrderLine` | Thành phần riêng của order | PurchaseOrder | Có thể PERSIST/MERGE/REMOVE |
| `Customer` | Khách hàng độc lập | Customer aggregate/service | Thường không |
| `Product` | Sản phẩm/catalog độc lập | Product/catalog service | Thường không |
| `Payment` | Có thể là aggregate riêng hoặc thành phần phụ thuộc, tùy domain | Theo chính sách payment | Không mặc định |
| `Shipment` | Thường có vòng đời và quy trình riêng | Fulfillment workflow | Không mặc định |

Cấu trúc quan hệ:

```text
Customer 1 <------ * PurchaseOrder
                         |
                         | 1
                         v
                         * OrderLine * ------> 1 Product
```

- Một customer có nhiều order.
- Một order có nhiều line.
- Mỗi line tham chiếu một product.
- Order sở hữu các line; customer và product không thuộc vòng đời của order.

### 4.1. Vì sao không cascade REMOVE tới Customer?

Giả sử:

```text
Customer 42
   |
   +-- Order 100
   +-- Order 101
   +-- Order 102
```

Nếu mapping `PurchaseOrder.customer` có cascade REMOVE, xóa Order 100 có thể lan xóa Customer 42, ảnh hưởng Order 101 và 102. Điều đó vi phạm ownership: order chỉ **tham chiếu** customer.

### 4.2. Vì sao không cascade PERSIST tới Product?

Một Product đã có thể được tạo trong catalog trước khi khách đặt hàng. Khi tạo OrderLine mới, line chỉ cần tham chiếu product managed/reference. Cascade PERSIST có thể khiến Hibernate cố persist lại product detached hoặc tạo lỗi lifecycle.

Nếu nghiệp vụ thực sự cho phép tạo Product mới đồng thời tạo Order, đó thường là một use case/aggregate khác; không nên dùng cascade từ OrderLine như cơ chế tạo catalog một cách ngẫu nhiên.

## 5. Mapping khuyến nghị cho aggregate order

Ví dụ entity root:

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REMOVE
        },
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Column(nullable = false, length = 30)
    private String status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.id = UUID.randomUUID();
        this.customer = Objects.requireNonNull(customer);
        this.status = "DRAFT";
    }

    public UUID getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(Product product, int quantity) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Only a draft order can be edited"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        OrderLine line = new OrderLine(product, quantity);
        line.assignTo(this);
        lines.add(line);
    }

    public void removeLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Only a draft order can be edited"
            );
        }

        if (lines.remove(line)) {
            line.assignTo(null);
        }
    }

    public void submit() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An order must contain at least one line"
            );
        }

        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Only a draft order can be submitted"
            );
        }

        status = "SUBMITTED";
    }
}
```

Entity line:

```java
import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    OrderLine(Product product, int quantity) {
        this.product = Objects.requireNonNull(product);
        this.quantity = quantity;
    }

    void assignTo(PurchaseOrder order) {
        this.order = order;
    }

    public void changeQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        this.quantity = quantity;
    }
}
```

Các điểm thiết kế:

- Cascade đi từ `PurchaseOrder.lines` xuống các line.
- `OrderLine.order` là owning side của FK.
- `OrderLine.product` không cascade; Product là entity dùng chung.
- `PurchaseOrder.customer` không cascade; Customer có lifecycle riêng.
- `orphanRemoval = true` thể hiện line bị bỏ khỏi order thì không còn tồn tại độc lập.
- API trả collection chỉ đọc, giúp thay đổi line đi qua root.
- Method `submit` bảo vệ invariant tối thiểu của order; nghiệp vụ thực tế có thể cần kiểm tra giá, tồn kho, quyền, thuế và trạng thái thanh toán.

Ví dụ sử dụng UUID được cấp trong constructor để đơn giản hóa việc tạo root. Nếu dùng generator database, thời điểm ID có thể xuất hiện khác nhau; cascade không thay đổi nguyên tắc ownership.

### 5.1. Tại sao cascade chỉ ở một phía?

Một entity graph hai chiều thường có đường tham chiếu vòng:

```text
PurchaseOrder -> lines -> OrderLine -> order -> lines -> ...
```

Cascade từ root xuống child đã diễn đạt ownership. Không cần cấu hình cascade ngược từ `OrderLine.order` trở lại `PurchaseOrder`, vì điều đó làm thao tác từ child có thể lan ngược lên root ngoài ý định.

Cascade có thể đi qua graph; tránh tạo những chuỗi cascade vòng không cần thiết.

## 6. Tạo mới aggregate bằng PERSIST

Với order mới và các line mới:

```java
@Transactional
public UUID createDraft(Long customerId, List<LineCommand> commands) {
    Customer customer = em.find(Customer.class, customerId);

    if (customer == null) {
        throw new IllegalArgumentException("Customer not found");
    }

    PurchaseOrder order = new PurchaseOrder(customer);

    for (LineCommand command : commands) {
        Product product = em.find(
            Product.class,
            command.productId()
        );

        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        order.addLine(product, command.quantity());
    }

    em.persist(order);
    return order.getId();
}
```

`LineCommand` là DTO/record do ứng dụng định nghĩa. Ví dụ giả định method chạy qua Spring transaction proxy và `EntityManager` dùng cùng transaction manager.

Do `PurchaseOrder.lines` có cascade PERSIST, persist root có thể persist các line mới. Customer và Product đã được tải trong persistence context hiện tại, không cần cascade persist sang chúng.

### 6.1. Điều gì xảy ra nếu bỏ cascade PERSIST?

Nếu không có cascade PERSIST, code phải persist từng line mới một cách tường minh hoặc qua một API repository phù hợp. Điều đó không sai, nhưng có thể làm lộ chi tiết persistence ra ngoài root và tăng khả năng thao tác thiếu nhất quán.

Chọn cascade khi child thực sự thuộc vòng đời root và việc tạo child luôn nằm trong cùng use case/transaction.

### 6.2. Cascade PERSIST không phải cơ chế “lưu mọi object trong graph”

Giả sử order có một customer detached do lấy từ request hoặc một EntityManager cũ. Nếu cascade PERSIST được đặt trên customer, thao tác persist order có thể lan đến customer và gây:

```text
PersistentObjectException:
    detached entity passed to persist
```

Giải pháp không phải thêm `CascadeType.ALL` ở mọi quan hệ. Hãy tải Customer managed bằng ID trong transaction hiện tại, hoặc dùng reference phù hợp; bỏ cascade PERSIST ở quan hệ shared.

## 7. MERGE: dùng khi nào và vì sao phải thận trọng?

Nếu root và các line đã detached, `merge` có thể sao chép trạng thái của graph vào managed instance nếu cascade MERGE được cấu hình.

```java
PurchaseOrder managed = em.merge(detachedOrder);
```

Luôn sử dụng object trả về:

```java
PurchaseOrder managed = em.merge(detachedOrder);
managed.submit();
```

Object `detachedOrder` ban đầu vẫn detached. Những thay đổi tiếp theo trên nó không tự động được Hibernate theo dõi.

### 7.1. Rủi ro graph không đầy đủ

Giả sử database có order với ba line:

```text
Order 100:
  Line 1
  Line 2
  Line 3
```

Một request PATCH chỉ gửi Line 1. Nếu mapper tạo một detached graph mới với collection chỉ có Line 1 rồi merge, trạng thái collection có thể không phản ánh ý định của client. Khi có orphan removal, các line bị thiếu có thể bị xem là đã bị loại khỏi quan hệ và bị xóa theo semantics mapping.

Không nên diễn giải “không có trong JSON” thành “hãy xóa khỏi aggregate” nếu API chỉ là cập nhật từng phần.

### 7.2. Tải root managed rồi áp dụng command

Một cách an toàn hơn:

```java
@Transactional
public void changeLineQuantity(
        UUID orderId,
        Long lineId,
        int newQuantity) {

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        throw new IllegalArgumentException("Order not found");
    }

    OrderLine line = order.findLine(lineId);
    if (line == null) {
        throw new IllegalArgumentException("Line not found");
    }

    order.changeLineQuantity(line, newQuantity);
}
```

Các method `findLine` và `changeLineQuantity` cần được triển khai trong root theo domain. Ví dụ chỉ mô tả cách làm: tải aggregate managed, xác định đúng child, áp dụng thay đổi hợp lệ; dirty checking ghi state khi flush.

Không cần merge một graph được dựng lại từ request.

## 8. REMOVE: xóa aggregate theo quyền sở hữu

Nếu `OrderLine` chỉ tồn tại bên trong order, xóa root có thể xóa tất cả line:

```java
@Transactional
public void cancelAndDeleteDraft(UUID orderId) {
    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        return;
    }

    if (!"DRAFT".equals(order.getStatus())) {
        throw new IllegalStateException(
            "Only draft orders can be deleted"
        );
    }

    em.remove(order);
}
```

Với cascade REMOVE từ root xuống lines, Hibernate xử lý xóa line theo mapping. `orphanRemoval` cũng biểu thị vòng đời phụ thuộc khi child bị loại khỏi association.

Nhưng trong hệ thống thương mại thực tế, order đã submitted/paid có thể **không được xóa vật lý**. Nó có thể chuyển sang trạng thái cancelled/refunded để giữ lịch sử. Chính sách xóa phụ thuộc domain, pháp lý và audit; cascade REMOVE chỉ là công cụ persistence khi quyết định xóa đã hợp lệ.

### 8.1. Vì sao không gọi remove trên từng shared reference?

```java
em.remove(order.getCustomer()); // Không nên và thường không hợp lệ nếu customer detached.
```

Customer là đối tượng độc lập; xóa order không có nghĩa xóa customer. Việc xóa customer cần use case riêng với kiểm tra các order/quan hệ đang tham chiếu.

### 8.2. Cascade REMOVE không phải ON DELETE CASCADE

Cascade REMOVE là thao tác của ORM: khi ứng dụng gọi remove trên root managed, Hibernate lan remove theo mapping.

`ON DELETE CASCADE` là hành vi của database foreign key: khi một hàng cha bị xóa ở DB, DB tự xóa hàng con tham chiếu theo ràng buộc.

Hai cơ chế khác nhau về nơi thực thi, lifecycle callback và cách persistence context biết các hàng đã bị xóa. Phần so sánh chi tiết ở dưới.

## 9. orphanRemoval: khi child bị tách khỏi root

`orphanRemoval = true` áp dụng cho association `@OneToOne` hoặc `@OneToMany` theo Jakarta Persistence. Khi một entity con bị loại khỏi quan hệ được đánh dấu orphan removal, provider áp dụng thao tác remove cho child theo lifecycle rule, thường tại flush.

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi:

```java
order.removeLine(line);
```

và helper loại line khỏi collection, Hibernate sẽ lên lịch xóa child theo orphan removal.

### 9.1. REMOVE và orphanRemoval khác nhau

| Cơ chế | Kích hoạt bởi | Ý nghĩa |
|---|---|---|
| `CascadeType.REMOVE` | Gọi `remove(root)` | Lan thao tác xóa root tới các entity liên quan |
| `orphanRemoval = true` | Child bị loại khỏi association được quản lý | Child mất quan hệ sở hữu và bị xóa |
| `ON DELETE CASCADE` | Database xóa hàng cha | Database tự xóa hàng con theo FK |
| Soft delete | Domain đổi trạng thái/cột | Hàng vẫn tồn tại, được đánh dấu không còn hoạt động |

Một mapping có thể dùng cả cascade REMOVE và orphanRemoval nếu child thực sự phụ thuộc root. Chúng giải quyết hai sự kiện khác nhau: xóa cả root và bỏ một child riêng lẻ.

### 9.2. Khi nào không dùng orphanRemoval?

Không dùng nếu child có thể:

- Chuyển sang parent khác.
- Tồn tại độc lập sau khi tách.
- Được nhiều parent cùng tham chiếu.
- Cần lưu lịch sử hoặc audit sau khi association bị gỡ.
- Được tái sử dụng trong workflow khác.

Ví dụ `Tag` được nhiều bài viết dùng không phải orphan của một bài viết. Gỡ tag khỏi một bài chỉ nên xóa **hàng liên kết**, không xóa entity Tag.

### 9.3. Không dùng orphanRemoval cho thao tác di chuyển child

Giả sử cần chuyển một line sang một order khác. Nếu association cũ có orphanRemoval, việc gỡ child khỏi root cũ có thể khiến nó được lên lịch xóa. Jakarta Persistence yêu cầu ứng dụng portable không dựa vào việc tái gắn một entity đã bị orphan để hủy bỏ thao tác remove đã áp dụng.

Với entity có thể di chuyển, cần thiết kế lifecycle khác: không dùng orphanRemoval, hoặc mô hình hóa thao tác di chuyển theo quy tắc phù hợp mà không đưa entity vào trạng thái orphan bị xóa.

Đối với `OrderLine`, thường nghiệp vụ không cho phép chuyển một line cũ giữa hai order; nếu cần tạo dòng ở order mới, tạo một line mới với dữ liệu cần thiết.

## 10. Cascade và quan hệ dùng chung: Customer, Product, Tag

Một quy tắc quan trọng:

> **Chỉ cascade thao tác vòng đời từ root tới entity mà root thực sự sở hữu.** Entity được tham chiếu hoặc chia sẻ thường không nên nhận cascade REMOVE.

### 10.1. Many-to-one tới Customer

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Không cascade REMOVE. Order có thể tham chiếu customer; customer không phải thành phần được order sở hữu.

Cascade PERSIST cũng thường không cần vì customer đã tồn tại. Khi tạo order, service tải customer managed hoặc dùng reference thích hợp.

### 10.2. Many-to-one tới Product

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

Không cascade REMOVE hoặc PERSIST. Product thuộc catalog và có thể được nhiều order line tham chiếu.

### 10.3. Many-to-many tới Tag

Một bài viết có thể gắn nhiều tag và một tag có thể được nhiều bài viết dùng:

```java
@ManyToMany
@JoinTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Khi gỡ tag khỏi article, điều cần xóa thường là hàng trong bảng `article_tags`, không phải entity Tag. Cascade REMOVE từ Article sang Tag có thể xóa tag được nhiều article khác dùng.

Với many-to-many, thường chỉ thay đổi association/join table. Nếu mỗi liên kết có dữ liệu riêng (thứ tự, người thêm, thời điểm), cân nhắc mô hình hóa join entity riêng thay vì một association many-to-many đơn giản.

### 10.4. Một câu hỏi kiểm tra ownership

Trước khi thêm cascade, hãy hỏi:

- Nếu root bị xóa, entity đích có phải biến mất theo nghiệp vụ không?
- Nếu entity đích được dùng bởi một aggregate khác, thao tác này có phá dữ liệu không?
- Entity đích có thể được tạo/cập nhật độc lập không?
- Có một repository/use case riêng quản lý vòng đời nó không?
- Việc tách khỏi association có nghĩa là xóa thật hay chỉ bỏ liên kết?

Nếu câu trả lời cho thấy entity có vòng đời riêng, cascade REMOVE thường không phù hợp.

## 11. Cascade là hướng truyền thao tác, không phải tự động hai chiều

Giả sử mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Cascade từ `PurchaseOrder` tới `OrderLine`. Nếu gọi `persist(order)`, thao tác persist lan xuống line.

Điều này không có nghĩa gọi `persist(line)` sẽ tự động cascade ngược lên `PurchaseOrder`. Cascade được khai báo trên association nào thì thao tác được truyền theo hướng đó.

Không nên khai báo cascade PERSIST ở cả hai phía một cách máy móc. Quan hệ hai chiều không có nghĩa lifecycle operation phải truyền qua lại.

### 11.1. Chu trình association không nhất thiết là chu trình cascade nguy hiểm

Hai phía có thể tham chiếu nhau:

```text
Order -> lines -> Order
```

Hibernate quản lý identity và persistence graph; nhưng việc cấu hình cascade hai chiều không cần thiết làm thao tác khó dự đoán, đặc biệt khi có nhiều association khác nối sang entity dùng chung.

Chọn một hướng từ root xuống các thành phần sở hữu và giữ association ngược chủ yếu để điều hướng/mapping.

### 11.2. Cascade không phải fetch

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.LAZY,
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

- `fetch = LAZY` quyết định thời điểm tải collection theo khả năng provider.
- `cascade = ALL` quyết định thao tác persistence nào lan đến child.

Không có nghĩa khi tải order, Hibernate tự tải hết lines. Và cũng không có nghĩa chỉ vì collection chưa loaded thì cascade persist/remove sẽ không hoạt động theo semantics cần thiết.

## 12. Database foreign key và thứ tự xóa

Giả sử schema:

```sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

FK từ `order_lines.order_id` tới `purchase_orders.id` ngăn database xóa order khi vẫn còn line tham chiếu, trừ khi ràng buộc được cấu hình cascade delete hoặc các line đã được xóa trước.

Khi Hibernate thực hiện cascade REMOVE, nó cần xóa child/root theo thứ tự phù hợp để thỏa FK. Hibernate có action queue và quy tắc thứ tự DML riêng; không nên dựa vào thứ tự method Java gọi để suy luận SQL.

### 12.1. Nếu FK dùng RESTRICT/NO ACTION

Hibernate cascade REMOVE có thể lên lịch xóa các line và order trong cùng transaction. Khi SQL được thực hiện theo thứ tự hợp lệ, DB chấp nhận.

Nếu code không cascade và chỉ remove order trong khi line vẫn tồn tại, database có thể báo FK violation. Đây là tín hiệu schema đang bảo vệ một quan hệ chưa được xử lý, không nên giải quyết bằng cách bỏ FK.

### 12.2. Nếu FK dùng ON DELETE CASCADE

Database có thể tự xóa các hàng order_lines khi purchase_orders bị xóa. Đây là hành vi ở DB, có thể giảm số lệnh DELETE ORM cần gửi trong một số mô hình.

Nhưng nếu Hibernate vẫn quản lý child trong persistence context, state Java có thể không tự phản ánh mọi hàng bị DB xóa. Cần hiểu cách ORM mapping và cơ chế database cascade được tích hợp, tránh dùng các entity child đã bị xóa vật lý như thể chúng còn tồn tại.

### 12.3. Hibernate-specific @OnDelete

Hibernate có annotation riêng `@OnDelete` để mô tả hành vi database-level delete action cho một số association/collection mapping, ví dụ:

```java
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@OneToMany(mappedBy = "order")
@OnDelete(action = OnDeleteAction.CASCADE)
private List<OrderLine> lines;
```

Đây là tính năng riêng Hibernate và có thể ảnh hưởng DDL/schema generation hoặc cách Hibernate phối hợp delete. Nó không phải cascade REMOVE JPA theo nghĩa giống nhau.

Phải kiểm tra tài liệu đúng Hibernate version và schema migration thực tế. Nếu schema được quản lý bằng Flyway/Liquibase, annotation không nhất thiết tự sửa constraint production. Cần xác nhận FK thật trong database có `ON DELETE CASCADE`.

### 12.4. Không xóa FK để làm cascade “chạy được”

Nếu gặp lỗi constraint khi xóa root, giải pháp đúng là quyết định ownership và xử lý child/reference phù hợp. Bỏ FK có thể làm mất lớp bảo vệ dữ liệu và tạo orphan khó phát hiện.

## 13. Xóa vật lý và soft delete là hai nghiệp vụ khác nhau

**Hard delete** xóa hàng khỏi database. **Soft delete** giữ hàng nhưng đánh dấu không còn hoạt động.

Ví dụ:

```java
@Column(name = "deleted_at")
private Instant deletedAt;

public void archive() {
    if (deletedAt == null) {
        deletedAt = Instant.now();
    }
}
```

Nếu order được soft delete, cascade REMOVE không tự động được kích hoạt chỉ vì gọi `archive()`. Đây là một method domain đổi trạng thái; ứng dụng cần quyết định:

- Các line có được soft delete cùng không?
- Có giữ line để audit không?
- Product/Customer có bị ảnh hưởng không? Thông thường không.
- Query nào bỏ qua order đã archive?
- Có thể khôi phục order và lines không?

Có thể triển khai một method root:

```java
public void archive() {
    if (isAlreadyArchived()) {
        return;
    }

    this.deletedAt = Instant.now();
    for (OrderLine line : lines) {
        line.archive();
    }
}
```

Nhưng đây là **quy tắc domain được code rõ ràng**, không phải semantics tự động của CascadeType.REMOVE. Nếu có nhiều child, cần kiểm soát fetch, transaction và kích thước aggregate.

### 13.1. Soft delete không xóa được tham chiếu

Vì hàng vẫn tồn tại, FK vẫn hợp lệ. Tuy nhiên entity có thể không còn được hiển thị trong query mặc định. Một order line trỏ tới product soft-deleted vẫn có FK hợp lệ, nhưng nghiệp vụ có thể cấm bán product ấy.

Referential integrity và business availability là hai kiểm tra khác nhau.

### 13.2. Restore cần đồng bộ toàn aggregate

Nếu order được khôi phục, không nhất thiết mọi line đều được khôi phục theo cùng quy tắc. Có thể product đã ngừng kinh doanh hoặc một line đã bị hủy riêng. Xác định trạng thái hợp lệ thay vì đảo ngược mọi cột một cách máy móc.

## 14. Bulk JPQL DELETE không chạy cascade entity như remove

Một bẫy quan trọng:

```java
int deleted = em.createQuery("""
    delete from PurchaseOrder o
    where o.status = :status
    """)
    .setParameter("status", "DRAFT")
    .executeUpdate();
```

JPQL bulk delete được thực thi trực tiếp trên database. Nó **không tải từng PurchaseOrder rồi gọi EntityManager.remove()**. Vì vậy:

- Cascade REMOVE của entity graph không được thực hiện như khi remove từng entity.
- Orphan removal không chạy như thao tác thay đổi collection managed.
- Lifecycle callbacks của từng entity không được gọi theo quy trình remove thông thường.
- Persistence context có thể chứa entity cũ, trở nên stale sau bulk DML.
- FK có thể chặn lệnh hoặc DB cascade có thể xử lý tùy schema.

Nếu cần áp dụng quy tắc aggregate và lifecycle, dùng load root + remove managed entity hoặc thiết kế một bulk workflow có chủ đích ở database, xử lý child/FK/audit riêng.

### 14.1. Xóa theo lô bằng SQL không tương đương cascade ORM

Ví dụ native SQL:

```sql
DELETE FROM purchase_orders
WHERE status = 'DRAFT';
```

Không nên giả định Hibernate sẽ tìm mọi line, gọi callback và xóa chúng theo mapping. Nếu FK không có ON DELETE CASCADE, database có thể từ chối. Nếu có ON DELETE CASCADE, DB xóa child nhưng Hibernate persistence context có thể chưa biết.

Sau bulk/native DML, thường cần quản lý persistence context (flush trước nếu có pending changes, clear/refresh khi phù hợp) và chạy trong transaction có chính sách rõ ràng.

### 14.2. Khi nào bulk delete phù hợp?

- Dữ liệu rất lớn, xóa từng entity qua ORM không khả thi.
- Quy tắc xóa được mô hình hóa trực tiếp trong SQL/DB.
- Không cần per-entity callbacks hoặc domain behavior.
- Có kế hoạch xử lý audit, cache, FK, outbox và persistence context.

Bulk DML là một con đường hạ tầng riêng, không phải cách viết ngắn hơn cho aggregate operation.

## 15. Cascade và lifecycle callbacks

JPA/Hibernate có các callback như `@PrePersist`, `@PostPersist`, `@PreRemove`, `@PostRemove` và listener tương ứng.

Ví dụ:

```java
@PreRemove
void beforeRemove() {
    // Logic local phù hợp trước khi entity bị xóa.
}
```

Khi thao tác remove được cascade tới child, callback lifecycle phù hợp của child có thể được áp dụng theo quy trình entity removal. Nhưng không nên dùng callback như nơi gọi API ngoài hoặc triển khai workflow phức tạp:

- Callback chạy trong lifecycle persistence và có thể được gọi ở thời điểm flush/operation tương ứng.
- Gọi mạng trong callback có thể giữ transaction/lock lâu.
- Nếu transaction rollback, side effect bên ngoài không tự rollback.
- Thứ tự callback giữa một graph không nên bị dùng làm giao thức nghiệp vụ xuyên nhiều aggregate.

Nếu cần ghi audit/outbox, nên lưu bản ghi cần thiết trong transaction hoặc dùng cơ chế domain/application event có boundary rõ ràng.

## 16. Cascade REFRESH và DETACH: ít dùng nhưng vẫn có tác động

Nhiều dự án chỉ dùng PERSIST, MERGE, REMOVE nhưng `ALL` còn bao gồm REFRESH và DETACH.

### 16.1. REFRESH có thể ghi đè state trong bộ nhớ

```java
entityManager.refresh(order);
```

Refresh tải lại state từ database. Nếu cascade REFRESH xuống lines, các thay đổi chưa flush của lines có thể bị thay thế bằng dữ liệu database. Không dùng refresh như thao tác “cập nhật cache” vô hại khi người dùng đang chỉnh aggregate.

### 16.2. DETACH có thể làm root và child ngừng được theo dõi

```java
entityManager.detach(order);
```

Nếu cascade DETACH được cấu hình, các child liên quan có thể cũng bị detach. Sau đó sửa line không còn được dirty checking của persistence context cũ ghi tự động.

Điều này có thể hữu ích khi muốn giải phóng graph khỏi context hoặc ngăn tracking tiếp tục, nhưng thường không cần khai báo chỉ vì muốn “dọn bộ nhớ”. `clear()` detach toàn bộ context và có tác động rộng hơn.

### 16.3. ALL mang theo những thao tác này

Khi dùng `CascadeType.ALL`, hãy nhớ nó bao gồm cả REFRESH và DETACH. Nếu domain chỉ cần persist/remove child, khai báo rõ những loại cần thiết giúp ý định dễ hiểu và giảm tác dụng phụ không mong muốn.

## 17. Cascade với many-to-many và join entity

Một `@ManyToMany` thường biểu diễn hai entity cùng tồn tại độc lập, liên kết qua bảng nối:

```text
Article <---- article_tags ----> Tag
```

Khi xóa một Article, điều thường muốn là xóa các hàng `article_tags` của Article đó, nhưng giữ các Tag còn được Article khác sử dụng.

Do đó không nên cấu hình `CascadeType.REMOVE` hoặc `ALL` một cách mặc định trên many-to-many.

### 17.1. Nếu liên kết có lifecycle riêng, dùng join entity

Giả sử một article-tag relation lưu thêm:

- Thời điểm gắn tag.
- Người thêm tag.
- Thứ tự hiển thị.
- Trạng thái phê duyệt.

Khi đó, association không còn là một hàng nối vô danh. Có thể mô hình hóa:

```text
Article (root)
   |
   +-- ArticleTag (link entity)
            |
            +-- Tag (shared reference)
```

`ArticleTag` có thể thuộc vòng đời Article, nên cascade PERSIST/REMOVE từ Article xuống ArticleTag hợp lý; nhưng `Tag` vẫn là entity dùng chung, không cascade REMOVE.

Ví dụ:

```java
@OneToMany(
    mappedBy = "article",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<ArticleTag> tagLinks = new ArrayList<>();
```

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "tag_id", nullable = false)
private Tag tag;
```

Khi gỡ tag khỏi article, xóa `ArticleTag` link entity; giữ `Tag`.

### 17.2. Cascade không phải quyền sở hữu database

Ngay cả khi Article sở hữu vòng đời của ArticleTag, database vẫn cần FK từ ArticleTag tới Article và Tag. Cascade ORM không thay thế constraint bảo vệ dữ liệu khi có SQL writer khác.

## 18. Aggregate lớn và chi phí cascade

Một aggregate có hàng chục nghìn child có thể làm cascade REMOVE/PERSIST/merge tốn tài nguyên:

- Hibernate phải quản lý nhiều entity trong persistence context.
- Dirty checking có thể tốn bộ nhớ/CPU.
- Cascade traversal có thể đi qua graph lớn.
- Xóa từng entity có thể tạo nhiều DML và callback.
- Lock/transaction kéo dài.
- JDBC batching có thể giúp giảm round-trip nhưng không làm biến mất chi phí quản lý graph.

### 18.1. Aggregate boundary cũng là giới hạn kích thước

Nếu một `PurchaseOrder` có hàng triệu line, có thể aggregate boundary đang quá rộng hoặc workflow xử lý cần một mô hình batch chuyên biệt.

DDD không yêu cầu mọi entity có quan hệ phải nằm trong cùng aggregate. Một aggregate root nên gom các đối tượng cần được bảo vệ cùng nhau trong một transaction ngắn theo invariant thực tế.

### 18.2. Xóa subtree lớn

Với dữ liệu rất lớn, có thể cần:

- Bulk delete có thứ tự.
- DB-level ON DELETE CASCADE.
- Stored procedure.
- Batch job chia lô.
- Soft delete + purge bất đồng bộ.
- Outbox/audit cho thao tác xóa.

Những lựa chọn này phải xử lý lifecycle/callback/cache/audit riêng. Không thể kỳ vọng cascade ORM thông thường luôn phù hợp với hàng triệu entity.

### 18.3. Chia nhỏ transaction có thay đổi semantics

Nếu xóa aggregate theo từng chunk và commit mỗi chunk, thao tác không còn atomic toàn bộ. Nếu chunk thứ ba thất bại, hai chunk trước có thể đã commit.

Điều đó có thể chấp nhận với một quy trình purge có trạng thái và retry; không phù hợp nếu invariant đòi hỏi mọi child và root phải biến mất cùng lúc.

## 19. Cascade và optimistic locking

Root có `@Version` không có nghĩa mọi thao tác trên child đều tự động bảo vệ invariant aggregate theo cùng cách.

Ví dụ:

```java
@Version
private long version;
```

Một line thay đổi quantity có thể chỉ update row `order_lines`. Tùy mapping và thao tác, version của root không nhất thiết tăng nếu root không được sửa. Nếu invariant yêu cầu mọi thay đổi child phải được tuần tự hóa qua root, có thể cần:

- Thay đổi state/version của root qua domain operation.
- Khóa root bằng optimistic/pessimistic lock trước khi sửa child.
- Thiết kế version/constraint ở mức database phù hợp.
- Giới hạn thao tác cập nhật child chỉ qua aggregate root.

Cascade chỉ truyền lifecycle operation; **không tự tạo một cơ chế aggregate-wide lock**.

## 20. Cascade và event/outbox khi xóa

Nếu xóa một aggregate cần phát sự kiện:

```text
BEGIN
  DELETE/mark PurchaseOrder
  DELETE/mark owned OrderLines
  INSERT outbox event OrderDeleted
COMMIT
```

Ghi outbox trong cùng transaction giúp sự kiện chỉ tồn tại khi thao tác xóa đã commit. Publisher gửi sau commit theo cơ chế retry.

Không gửi event trước khi database commit rồi kỳ vọng rollback sẽ thu hồi message. Cũng không dùng callback `@PostRemove` để gửi trực tiếp broker mà không có cơ chế đảm bảo.

Nếu thao tác xóa diễn ra bằng bulk SQL/DB cascade, outbox cần được tạo bằng một đường riêng (service/procedure/trigger phù hợp) vì ORM callbacks không nhất thiết chạy cho từng child.

## 21. Những lỗi cấu hình thường gặp

| Cấu hình/lỗi | Hậu quả | Cách suy nghĩ đúng |
|---|---|---|
| `CascadeType.ALL` từ Order tới Customer | Xóa order có thể xóa customer; persist có thể cascade tới customer detached | Customer có lifecycle riêng, không cascade REMOVE/PERSIST |
| `CascadeType.REMOVE` từ OrderLine tới Product | Xóa line có thể xóa product dùng chung | Product là shared reference |
| Không cascade PERSIST từ root tới private child | Cần persist child tường minh hoặc gặp transient reference | Chọn PERSIST nếu root sở hữu child mới |
| Chỉ sửa collection inverse side | FK owning side không được cập nhật đúng | Đồng bộ cả hai phía qua helper |
| Dùng orphanRemoval cho entity có thể chuyển parent | Child bị lên lịch xóa khi bị tách | Không orphan-remove entity có lifecycle độc lập/di chuyển |
| Dùng ALL nhưng không hiểu REFRESH/DETACH | State child có thể bị refresh hoặc detach ngoài ý muốn | Khai báo cascade cần thiết một cách rõ ràng |
| Dùng bulk DELETE rồi mong cascade ORM | Child/callback không được xử lý như remove entity | Dùng entity remove hoặc thiết kế SQL/DB lifecycle riêng |
| Dùng cascade thay cho FK | SQL writer ngoài Hibernate tạo orphan | Bảo vệ schema bằng FK/check/unique |
| Cascade qua graph vòng không cần thiết | Lifecycle lan khó dự đoán, có thể đụng shared entity | Đặt hướng từ aggregate root xuống private parts |
| Aggregate quá lớn | Flush/delete tốn bộ nhớ, lock lâu | Xem lại aggregate boundary và batch workflow |

## 22. Quy trình chọn cascade cho một association

Trước khi thêm cascade vào mapping, có thể trả lời lần lượt:

1. **Entity đích có tồn tại độc lập không?** Nếu có, đừng mặc định cascade REMOVE.
2. **Ai quyết định tạo entity đích?** Nếu root luôn tạo child mới cùng lúc, PERSIST có thể phù hợp.
3. **Ai quyết định xóa entity đích?** Nếu chỉ root có quyền xóa private child, REMOVE/orphanRemoval có thể phù hợp.
4. **Entity có được chia sẻ bởi aggregate khác không?** Nếu có, cascade REMOVE thường sai.
5. **Entity có thể di chuyển khỏi association không?** Nếu có, cân nhắc không dùng orphanRemoval.
6. **Cập nhật detached graph có thực sự cần không?** Nếu không, có thể bỏ MERGE và dùng managed aggregate + command.
7. **Có cần cascade REFRESH/DETACH không?** Chỉ thêm nếu có use case cụ thể.
8. **Association là owning hay inverse side?** Cập nhật đúng phía sở hữu FK.
9. **Database có FK/ON DELETE policy nào?** Đảm bảo ORM và schema không mâu thuẫn.
10. **Có bulk/native SQL hoặc external writer không?** Cascade ORM không bảo vệ các đường ghi đó.
11. **Aggregate có quá lớn không?** Cân nhắc transaction và persistence context.
12. **Test xóa và tạo mới đã xác nhận đúng ownership chưa?** Kiểm tra shared entity vẫn tồn tại.

### Bảng quyết định nhanh

| Association | Cascade thường cân nhắc | Lý do |
|---|---|---|
| Order → OrderLine (private child) | PERSIST, REMOVE; MERGE nếu có detached merge; orphanRemoval nếu tách là xóa | Line thuộc lifecycle order |
| OrderLine → Product (shared) | Thường không cascade | Product sống độc lập |
| Order → Customer (shared) | Thường không cascade | Customer dùng chung nhiều order |
| Article → ArticleTag (link entity riêng) | PERSIST/REMOVE, orphanRemoval có thể phù hợp | Link thuộc Article |
| ArticleTag → Tag (shared) | Thường không cascade REMOVE | Tag dùng chung |
| User → Profile (private one-to-one) | Có thể PERSIST/REMOVE + orphanRemoval | Profile có thể phụ thuộc User nếu domain xác định |
| Department → Employee | Không mặc định REMOVE | Employee có thể chuyển phòng ban hoặc có vòng đời riêng |
| Parent → Child có thể chuyển nhánh | PERSIST tùy ownership; tránh orphanRemoval nếu detach chỉ là di chuyển | Gỡ quan hệ không có nghĩa xóa entity |

Đây là gợi ý thiết kế, không phải quy tắc cứng cho mọi domain. Phải xác nhận lifecycle thật.

## 23. Ví dụ service tạo và xóa aggregate

Service tạo order:

```java
@Service
public class OrderApplicationService {

    private final EntityManager em;

    public OrderApplicationService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public UUID create(CreateOrderCommand command) {
        Customer customer = em.find(
            Customer.class,
            command.customerId()
        );

        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        PurchaseOrder order = new PurchaseOrder(customer);

        for (CreateOrderLineCommand lineCommand : command.lines()) {
            Product product = em.find(
                Product.class,
                lineCommand.productId()
            );

            if (product == null) {
                throw new IllegalArgumentException("Product not found");
            }

            order.addLine(product, lineCommand.quantity());
        }

        em.persist(order); // Cascade PERSIST xuống private lines.
        return order.getId();
    }

    @Transactional
    public void deleteDraft(UUID orderId) {
        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            orderId
        );

        if (order == null) {
            return;
        }

        if (!order.isDraft()) {
            throw new IllegalStateException(
                "Only draft orders can be deleted"
            );
        }

        em.remove(order); // Cascade REMOVE tới lines.
    }
}
```

Các command record và method `isDraft` là thành phần ứng dụng cần định nghĩa. Ví dụ giả định Spring quản lý service, transaction manager và EntityManager đúng cách.

Service chỉ persist/remove root; cascade xử lý private children theo mapping. Customer/Product được tải như managed reference, không bị cascade vòng đời.

### 23.1. Xóa root không phải lúc nào cũng hợp lệ

Ví dụ service chỉ cho xóa draft order. Với order đã submitted hoặc paid, nghiệp vụ có thể yêu cầu cancellation/refund và giữ lịch sử. Không nên để một API delete vật lý bỏ qua trạng thái domain chỉ vì ORM có cascade REMOVE.

### 23.2. Dùng repository root

Trong DDD, thường chỉ expose repository cho aggregate root:

```java
interface PurchaseOrderRepository {
    Optional<PurchaseOrder> findById(UUID id);
    void add(PurchaseOrder order);
    void remove(PurchaseOrder order);
}
```

Không nhất thiết tạo repository công khai cho `OrderLine` nếu line chỉ được thay đổi thông qua root. Đây là quy ước kiến trúc giúp tránh thao tác child ngoài boundary.

## 24. Kiểm thử cascade và quyền sở hữu

Một test hữu ích cần xác nhận **dữ liệu thực tế sau flush/commit**, không chỉ kiểm tra annotation tồn tại.

### 24.1. Persist root tạo private children

- Tạo customer/product đã tồn tại.
- Tạo order mới và hai line mới.
- Persist root.
- Flush/commit rồi kiểm tra order và line tồn tại.
- Kiểm tra customer/product vẫn là các hàng cũ, không bị tạo lại.

### 24.2. Remove root xóa children nhưng giữ shared entities

- Tạo order có line.
- Remove order managed.
- Commit.
- Xác nhận order và lines đã bị xóa theo policy.
- Xác nhận customer/product vẫn tồn tại.

### 24.3. Orphan removal xóa child khi gỡ khỏi collection

- Load order managed.
- Gọi root.removeLine(line).
- Flush/commit.
- Kiểm tra line bị xóa vật lý theo mapping.
- Kiểm tra các line khác còn nguyên.

### 24.4. Cascade PERSIST không đi vào shared entity

- Tạo một customer đã tồn tại và detached.
- Gắn customer reference được tải managed trong transaction mới vào order.
- Persist order.
- Xác nhận không có cascade persist/remove sang customer.

### 24.5. Merge graph và dữ liệu không đầy đủ

Nếu hệ thống dùng cascade MERGE:

- Thử graph đầy đủ.
- Thử request thiếu một line.
- Xác nhận semantics xóa/thêm được định nghĩa rõ.
- Kiểm tra optimistic locking và các trường không được gửi lên không bị ghi đè ngoài ý muốn.

### 24.6. Bulk delete không chạy cascade entity

- Tạo order và line.
- Chạy bulk JPQL delete.
- Quan sát FK/DB cascade và persistence context.
- Không kỳ vọng callback/orphan removal của từng entity chạy như remove managed root.

### 24.7. Transaction rollback

- Tạo root/child.
- Cố tình gây lỗi sau một số thao tác persist/remove.
- Rollback.
- Xác nhận không có partial commit.
- Nếu có outbox/audit, xác nhận record cùng transaction cũng rollback theo.

Nên dùng integration test với database/dialect phù hợp, vì thứ tự DML, FK và ON DELETE CASCADE phụ thuộc schema thực tế.

## 25. Ghi nhớ

- **Aggregate root** là điểm vào bảo vệ invariant và quyền sở hữu vòng đời nghiệp vụ của nhóm entity.
- **Owning side JPA** quyết định phía nào cập nhật FK; nó không đồng nghĩa với aggregate root.
- Cascade nên được cấu hình từ root tới **private child** mà root thực sự quản lý.
- `PERSIST` phù hợp khi tạo mới aggregate và các child mới thuộc root.
- `MERGE` lan hợp nhất state của detached graph; dùng object trả về và thận trọng với graph không đầy đủ.
- `REMOVE` lan xóa root tới các child có vòng đời phụ thuộc; không cascade REMOVE tới customer/product/tag dùng chung.
- `orphanRemoval = true` xóa child khi bị tách khỏi association; chỉ phù hợp nếu tách nghĩa là xóa, không phải chuyển sang parent khác.
- `CascadeType.ALL` bao gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH; nó không có nghĩa fetch tất cả hoặc bảo vệ database.
- Trong association hai chiều, helper của root cần cập nhật **cả collection và owning side** để FK đúng.
- `ON DELETE CASCADE` là hành vi database, khác với cascade REMOVE của ORM; bulk DML cũng không chạy lifecycle cascade như thao tác entity.
- Soft delete là thay đổi trạng thái domain, không tự động được kích hoạt bởi CascadeType.REMOVE.
- Cascade không thay thế foreign key, unique/check constraint, transaction, locking hay concurrency control.
- Aggregate quá lớn có thể gây chi phí cascade/flush/delete cao; cần xem lại boundary hoặc dùng batch workflow có semantics rõ.
- Test phải chứng minh root, private children và shared references được tạo/xóa đúng, kể cả rollback và bulk DML.

**Kết luận:** hãy chọn cascade dựa trên câu hỏi **“entity này có thuộc vòng đời do aggregate root kiểm soát không?”**. Với private child, cascade PERSIST/REMOVE và orphan removal có thể giúp biểu diễn lifecycle tự nhiên. Với entity được tham chiếu hoặc dùng chung, giữ vòng đời độc lập và chỉ thiết lập association. Khi ranh giới nghiệp vụ, owning side JPA và foreign key database được thiết kế nhất quán, Hibernate có thể thực hiện các thao tác aggregate mà không vô tình xóa hoặc lưu lại những entity ngoài quyền sở hữu của root.
