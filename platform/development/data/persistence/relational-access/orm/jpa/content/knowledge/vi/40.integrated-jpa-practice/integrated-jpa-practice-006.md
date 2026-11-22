# Quản lý đối tượng con bằng cascade và orphanRemoval đúng phạm vi

Trong JPA, thao tác với một thực thể thường kéo theo thay đổi ở những thực thể có quan hệ với nó. Ví dụ, một đơn hàng có nhiều dòng hàng: khi tạo đơn hàng, hệ thống cần lưu các dòng; khi bỏ một dòng khỏi đơn, hệ thống phải quyết định xóa bản ghi dòng hàng, giữ lại nó, hay gán nó sang đơn khác. Hai cơ chế thường được sử dụng là **cascade** và **`orphanRemoval`**.

Sử dụng sai hai cơ chế này có thể gây mất dữ liệu ngoài ý muốn, đặc biệt khi các entity cùng tham chiếu đến một đối tượng dùng chung. Vì vậy, câu hỏi đầu tiên không phải “cần thêm annotation nào?”, mà là **thực thể nào thật sự sở hữu vòng đời của thực thể con?**

Bài thực hành này xây dựng aggregate **`PurchaseOrder` – `OrderLine`** với JPA/Hibernate, áp dụng cascade và `orphanRemoval` đúng phạm vi, xử lý cập nhật qua Service có transaction và chỉ ra những thiết kế cần tránh.

## 1. Xác định ranh giới sở hữu trước khi ánh xạ

Xét một hệ thống bán hàng có:

- `PurchaseOrder`: đơn hàng, có ID, trạng thái và phiên bản.
- `OrderLine`: dòng hàng, có mã SKU tại thời điểm đặt, số lượng, đơn giá; chỉ tồn tại trong một đơn hàng.
- `Product`: sản phẩm trong danh mục, có thể được nhiều đơn hàng sử dụng.
- `Customer`: khách hàng có thể sở hữu nhiều đơn hàng.

Quan hệ vòng đời phù hợp là:

```text
Customer (tồn tại độc lập)
   |
   +-------> PurchaseOrder (aggregate root)
               |
               +-------> OrderLine A (thuộc riêng một đơn)
               |
               +-------> OrderLine B (thuộc riêng một đơn)

Product (dữ liệu dùng chung, không thuộc vòng đời PurchaseOrder)
```

**`OrderLine` là đối tượng con thuộc quyền quản lý độc quyền của `PurchaseOrder`.** Khi đơn hàng mất đi, các dòng hàng của nó cũng mất đi. Khi một dòng không còn thuộc đơn hàng nào, thường không có lý do nghiệp vụ để giữ bản ghi dòng đó.

Ngược lại, `Product` hay `Customer` không được xóa chỉ vì một đơn hàng bị xóa. Đây là ranh giới quan trọng để quyết định nơi đặt `cascade`.

| Quan hệ | Ai quản lý vòng đời? | Cascade xóa? | `orphanRemoval`? |
|---|---|---|---|
| `PurchaseOrder → OrderLine` | `PurchaseOrder` quản lý riêng từng `OrderLine` | Có thể dùng, phù hợp quan hệ sở hữu độc quyền | Có thể dùng |
| `OrderLine → Product` | `Product` tồn tại độc lập | **Không** | Không |
| `PurchaseOrder → Customer` | `Customer` tồn tại độc lập | **Không** | Không |
| `Student ↔ Course` (nhiều-nhiều) | Mỗi bên tồn tại độc lập | Không cascade xóa entity bên kia | Không dùng |

Một tiêu chí thực tế: **Nếu bỏ liên kết với đối tượng cha thì đối tượng con có còn ý nghĩa và có thể được thực thể khác sử dụng hay không?** Nếu có, thường không nên dùng `orphanRemoval=true` và không nên cascade thao tác xóa từ cha sang con.

## 2. Phân biệt cascade và orphanRemoval

### 2.1. Cascade lan truyền thao tác của EntityManager

`cascade` chỉ định những thao tác JPA thực hiện trên entity cha cần được lan truyền đến entity liên quan.

| `CascadeType` | Thao tác được lan truyền | Tình huống sử dụng |
|---|---|---|
| `PERSIST` | `persist(parent)` lan tới đối tượng con mới | Tạo đơn và các dòng trong một lần lưu |
| `MERGE` | `merge(parent)` lan tới đối tượng con | Gộp trạng thái detached; phải kiểm soát nguồn dữ liệu |
| `REMOVE` | `remove(parent)` lan tới đối tượng con | Xóa cha thì xóa con thuộc sở hữu riêng |
| `REFRESH` | `refresh(parent)` lan tới con | Làm mới trạng thái đã quản lý |
| `DETACH` | `detach(parent)` lan tới con | Tách cả đồ thị entity khỏi persistence context |
| `ALL` | Tất cả các thao tác trên | Chỉ nên dùng khi con thật sự thuộc vòng đời của cha |

Ví dụ:

```java
@OneToMany(mappedBy = "purchaseOrder", cascade = CascadeType.PERSIST)
private List<OrderLine> lines = new ArrayList<>();
```

Khi `entityManager.persist(order)`, các `OrderLine` mới được liên kết sẽ được persist theo. Tuy nhiên, **`PERSIST` không có nghĩa là “xóa một phần tử khỏi danh sách thì xóa dòng trong database”**.

### 2.2. orphanRemoval xử lý đối tượng con bị tách khỏi quan hệ sở hữu

`orphanRemoval=true` dành cho quan hệ `@OneToOne` hoặc `@OneToMany` có sở hữu vòng đời. Khi một entity con đã được lưu bị loại khỏi quan hệ với cha, provider sẽ lập lịch xóa entity con tại thời điểm đồng bộ persistence context với database.

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Ví dụ hành vi:

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 10L);
OrderLine oldLine = order.getLines().get(0);
order.removeLine(oldLine.getId());
// Khi flush/commit: dòng đã bị tách khỏi order được DELETE.
```

So sánh hai cơ chế:

| Tình huống | Chỉ có `cascade=REMOVE` | Có `orphanRemoval=true` |
|---|---|---|
| Xóa entity cha bằng `EntityManager.remove(parent)` | Lan truyền xóa tới con | Con phụ thuộc cũng được xóa |
| Xóa một phần tử khỏi collection nhưng giữ cha | Không tự động có nghĩa là xóa entity con | Con bị tách được xóa |
| Tạo cha mới cùng các con mới | Cần `PERSIST` hoặc `ALL` | `orphanRemoval` tự nó không persist con |
| Tham chiếu đến entity dùng chung | Có nguy cơ xóa nhầm dữ liệu dùng chung | Không phù hợp với quan hệ chia sẻ |

Đối với một aggregate mà các con hoàn toàn thuộc quyền sở hữu cha, kết hợp `cascade=ALL` và `orphanRemoval=true` thường thuận tiện. Với vòng đời phức tạp, hãy liệt kê chính xác `CascadeType` cần thiết thay vì mặc định `ALL`.

> `orphanRemoval` **không phải** cơ chế garbage collection cho mọi entity không còn được Java tham chiếu. Nó hoạt động trên thay đổi quan hệ JPA đã được quản lý, theo các quy tắc của mapping và persistence context.

## 3. Thực hành: Thiết kế entity PurchaseOrder – OrderLine

Ví dụ dùng API `jakarta.persistence` (Spring Boot 3+, Jakarta Persistence 3). Các getter đặt theo JavaBean thông thường; mẫu tập trung vào quản lý vòng đời và có thể bổ sung validation/domain rules theo ứng dụng.

### 3.1. Aggregate root PurchaseOrder

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 30)
    private String status = "DRAFT";

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA
    }

    public static PurchaseOrder draft() {
        return new PurchaseOrder();
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(String sku, int quantity, BigDecimal unitPrice) {
        requireDraft();
        OrderLine line = new OrderLine(sku, quantity, unitPrice);
        line.attachTo(this);
        lines.add(line);
    }

    public void changeQuantity(Long lineId, int quantity) {
        requireDraft();
        findLine(lineId).changeQuantity(quantity);
    }

    public void removeLine(Long lineId) {
        requireDraft();
        Iterator<OrderLine> iterator = lines.iterator();
        while (iterator.hasNext()) {
            OrderLine line = iterator.next();
            if (Objects.equals(line.getId(), lineId)) {
                iterator.remove();
                line.detachFromOrder();
                return;
            }
        }
        throw new OrderLineNotFoundException(id, lineId);
    }

    private OrderLine findLine(Long lineId) {
        return lines.stream()
            .filter(line -> Objects.equals(line.getId(), lineId))
            .findFirst()
            .orElseThrow(() -> new OrderLineNotFoundException(id, lineId));
    }

    private void requireDraft() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Only a DRAFT order can change its lines");
        }
    }
}
```

Các đặc điểm đáng chú ý:

1. **`PurchaseOrder` là cổng chỉnh sửa collection.** Caller không lấy `getLines()` rồi tự `clear()` hoặc `add()`.
2. Các thao tác `addLine`, `removeLine` và `changeQuantity` thực thi quy tắc trạng thái đơn hàng ở cùng một nơi.
3. `removeLine` chỉ tìm trong collection **của chính đơn hàng hiện tại**. Không thể dùng một `lineId` thuộc đơn khác để xóa ngang phạm vi.
4. Với entity mới chưa được persist, `id` của `OrderLine` có thể là `null`. Ví dụ `removeLine(id)` hướng tới dòng đã có ID; muốn xóa một dòng vừa thêm trong bộ nhớ thì có thể bổ sung lệnh riêng dựa trên một định danh nghiệp vụ ổn định.
5. Collection dùng `List`, tránh việc đưa một entity transient vào `Set` với `equals/hashCode` dựa trên ID chưa được cấp.

### 3.2. Entity con OrderLine và owning side

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

@Entity
@Table(name = "purchase_order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    @Column(nullable = false, length = 64)
    private String productSku;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {
        // JPA
    }

    OrderLine(String productSku, int quantity, BigDecimal unitPrice) {
        if (productSku == null || productSku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Unit price must be non-negative");
        }
        this.productSku = productSku;
        this.unitPrice = unitPrice;
        changeQuantity(quantity);
    }

    void attachTo(PurchaseOrder order) {
        if (purchaseOrder != null && purchaseOrder != order) {
            throw new IllegalStateException("Line already belongs to another order");
        }
        purchaseOrder = order;
    }

    void detachFromOrder() {
        purchaseOrder = null;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        quantity = newQuantity;
    }

    public Long getId() {
        return id;
    }

    public String getProductSku() {
        return productSku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
```

Với ánh xạ hai chiều:

- `OrderLine.purchaseOrder`, được khai báo bằng `@ManyToOne` và `@JoinColumn`, là **owning side** trực tiếp quản lý khóa ngoại `purchase_order_id`.
- `PurchaseOrder.lines` có `mappedBy="purchaseOrder"` là **inverse side**, biểu diễn collection con.
- Mỗi thao tác phải giữ hai phía nhất quán **trong bộ nhớ**, vì chỉ thay đổi một bên khiến code nghiệp vụ thấy dữ liệu sai và SQL có thể không đúng ý định.
- `nullable=false` thể hiện quy tắc dòng hàng còn tồn tại phải thuộc một đơn hàng. Khi `removeLine` tách quan hệ, `orphanRemoval` sẽ xóa hàng con ở flush/commit; không kỳ vọng giữ một hàng với `purchase_order_id=NULL`.

Ví dụ cố ý lưu `productSku` và `unitPrice` như **snapshot** thay vì cascade tới entity `Product`. Nếu thay bằng:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

thì **không thêm `cascade=REMOVE` hoặc `cascade=ALL`** vào quan hệ tới `Product`: một dòng đơn hàng bị xóa không được làm mất sản phẩm trong danh mục.

## 4. Repository và Service: Chỉnh sửa thông qua aggregate root

Repository của aggregate root là điểm truy cập chính:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Trong nghiệp vụ cơ bản, không nhất thiết phải cung cấp endpoint xóa `OrderLineRepository.deleteById(lineId)`. Làm vậy có thể bỏ qua kiểm tra trạng thái đơn, quyền sở hữu và đồng bộ collection của root.

### 4.1. Tạo đơn mới cùng các dòng hàng

```java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createDraft() {
        PurchaseOrder order = PurchaseOrder.draft();
        order.addLine("BOOK-JPA", 2, new BigDecimal("199.00"));
        order.addLine("PEN-BLUE", 3, new BigDecimal("12.50"));

        return orders.save(order).getId();
    }

    @Transactional
    public void addLine(Long orderId, String sku,
                        int quantity, BigDecimal unitPrice) {
        PurchaseOrder order = requiredOrder(orderId);
        order.addLine(sku, quantity, unitPrice);
        // Entity managed: JPA theo dõi collection mới và PERSIST con.
    }

    @Transactional
    public void changeQuantity(Long orderId, Long lineId, int quantity) {
        PurchaseOrder order = requiredOrder(orderId);
        order.changeQuantity(lineId, quantity);
        // Dirty checking UPDATE OrderLine tương ứng.
    }

    @Transactional
    public void removeLine(Long orderId, Long lineId) {
        PurchaseOrder order = requiredOrder(orderId);
        order.removeLine(lineId);
        // orphanRemoval lập lịch DELETE OrderLine tương ứng.
    }

    private PurchaseOrder requiredOrder(Long orderId) {
        return orders.findById(orderId)
            .orElseThrow(() -> new PurchaseOrderNotFoundException(orderId));
    }
}
```

Các exception `PurchaseOrderNotFoundException` và `OrderLineNotFoundException` là lỗi nghiệp vụ tùy hệ thống; chúng có thể được ánh xạ thành HTTP `404`. Khi API thao tác dòng theo `/orders/{orderId}/lines/{lineId}`, cần kiểm tra rằng dòng đó thật sự thuộc đơn hàng được chỉ định.

**Không cần gọi `orders.save(order)` sau mỗi thay đổi của một entity managed** đang ở trong transaction; JPA sẽ dùng dirty checking khi flush/commit. Ngược lại, khi tạo aggregate mới bằng `save(order)`, cascade persist sẽ lưu các dòng mới cùng đơn hàng.

Với `FetchType.LAZY` mặc định của `@OneToMany`, truy cập `getLines()` trong transaction sẽ khởi tạo collection khi cần. Với đường đọc có nhiều đơn hàng, có thể dùng DTO projection, `@EntityGraph` hoặc fetch join phù hợp để tránh N+1; không chuyển toàn bộ collection thành `EAGER` chỉ để tiện cập nhật.

### 4.2. Kỳ vọng các câu lệnh SQL

Khi tạo đơn có hai dòng hàng:

```sql
INSERT INTO purchase_orders (status, version) VALUES ('DRAFT', 0);
INSERT INTO purchase_order_lines
    (purchase_order_id, product_sku, quantity, unit_price)
VALUES (?, 'BOOK-JPA', 2, 199.00);
INSERT INTO purchase_order_lines
    (purchase_order_id, product_sku, quantity, unit_price)
VALUES (?, 'PEN-BLUE', 3, 12.50);
```

Khi xóa một dòng khỏi collection bằng `removeLine`:

```sql
DELETE FROM purchase_order_lines
WHERE id = ?;
```

Đây là minh họa ý nghĩa của câu lệnh, **không phải cam kết SQL nguyên văn** của mọi JPA provider: thứ tự flush, câu lệnh cụ thể và điều kiện khóa phiên bản phụ thuộc mapping, chiến lược sinh ID và Hibernate/provider đang dùng.

## 5. Thao tác thêm, sửa, bỏ con: Khác nhau thế nào?

| Ý định từ người dùng | Thao tác trên root | Kỳ vọng |
|---|---|---|
| Thêm dòng mới | `order.addLine(...)` | `INSERT` dòng mới khi flush, nhờ `PERSIST` |
| Đổi số lượng dòng hiện có | `order.changeQuantity(lineId, ...)` | `UPDATE` chính dòng đó |
| Bỏ dòng khỏi đơn | `order.removeLine(lineId)` | `DELETE` dòng bị loại, nhờ `orphanRemoval` |
| Xóa toàn bộ đơn | `repository.delete(order)` | Xóa đơn cùng các dòng thuộc sở hữu riêng |
| Chuyển dòng sang đơn khác | Không hỗ trợ như thao tác thông thường | Xác định nghiệp vụ và chiến lược chuyển riêng |

Với dữ liệu mới chưa persist, đừng dựa vào việc xóa orphan để “dọn” đối tượng chưa được lưu. JPA định nghĩa `orphanRemoval` chủ yếu cho entity con đã được quản lý; xử lý object mới, detached hoặc đã bị remove có những giới hạn khác. Nếu tạo rồi bỏ một dòng ngay trong bộ nhớ trước lần persist đầu tiên, việc không thêm nó vào collection cuối cùng đã đủ để không tạo bản ghi.

### 5.1. Vì sao không thay toàn bộ danh sách từ request?

Một anti-pattern rất phổ biến:

```java
// KHÔNG NÊN làm trực tiếp với request JSON từ client.
order.setLines(request.getLines());
orders.save(order);
```

Nếu request chỉ gửi một phần danh sách, các dòng không được gửi có thể bị hiểu là đã bị bỏ, gây xóa hàng loạt khi `orphanRemoval=true`. Thay thế collection do Hibernate đang theo dõi bằng một collection mới còn có thể làm phát sinh lỗi quản lý orphan hoặc trạng thái không nhất quán, tùy mapping/provider.

Nên thiết kế **lệnh có ý nghĩa nghiệp vụ rõ ràng**:

```text
POST   /orders/{orderId}/lines           thêm dòng
PATCH  /orders/{orderId}/lines/{lineId}  đổi số lượng
DELETE /orders/{orderId}/lines/{lineId}  bỏ một dòng
```

Nếu thật sự cần endpoint **thay thế toàn bộ danh sách**, hãy nêu rõ đó là *full replacement*, xác minh quyền sở hữu tất cả ID, so sánh danh sách ID cũ–mới trong một transaction và quyết định rõ dòng nào **update**, dòng nào **insert**, dòng nào **delete**. Đừng coi sự thiếu vắng một phần tử trong payload dạng PATCH là lệnh xóa.

### 5.2. Vì sao không trực tiếp xóa child qua bulk query?

```java
@Modifying
@Query("delete from OrderLine l where l.purchaseOrder.id = :orderId")
int deleteAllLinesByOrderId(Long orderId);
```

JPQL bulk delete và nhiều phương thức như `deleteAllInBatch` tác động trực tiếp lên database, **bỏ qua hành vi vòng đời của từng entity managed**, các callback và cascade ở mức entity. Persistence context có thể vẫn chứa dữ liệu cũ nếu query được gọi sau khi entity đã được tải. Với aggregate đang quản lý, ưu tiên sửa collection có kiểm soát trong transaction; chỉ dùng bulk query khi đã chấp nhận và thiết kế riêng tác động lên entity state, callbacks và cache.

## 6. Ranh giới an toàn khi con là dữ liệu dùng chung

Giả sử bổ sung quan hệ `OrderLine → Product`. Một sản phẩm được dùng trong nhiều đơn. Mapping sau rất nguy hiểm:

```java
// SAI với Product là entity dùng chung.
@ManyToOne(cascade = CascadeType.ALL)
private Product product;
```

Khi xóa một `OrderLine`, cascade remove có thể cố xóa `Product`; kết quả là lỗi ràng buộc khóa ngoại hoặc mất dữ liệu nếu schema không bảo vệ.

Mapping phù hợp:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

Các lưu ý bổ sung:

- Với `@ManyToMany`, xóa một phần tử khỏi quan hệ thường chỉ phải xóa **bản ghi liên kết** trong join table. Không cascade `REMOVE` sang entity bên kia nếu nó được chia sẻ.
- Nếu một dòng hàng được chuyển từ đơn A sang B, `orphanRemoval` trên A có thể đánh dấu xóa dòng đó. Chuyển quyền sở hữu ngay trong một flush có thể tạo ra hành vi khó đoán; hãy định nghĩa lệnh chuyển rõ ràng (ví dụ tạo dòng mới ở B và bỏ dòng ở A) hoặc chọn mô hình mà child có vòng đời độc lập nếu nghiệp vụ thật sự cho phép chuyển.
- Với một entity chia sẻ có thể được “gỡ liên kết” nhưng vẫn phải tồn tại, hãy dùng quan hệ bình thường **không `orphanRemoval`**. Quyết định xóa entity chia sẻ phải nằm trong nghiệp vụ riêng của entity đó.
- `@OneToOne(orphanRemoval=true)` phù hợp với đối tượng phụ thuộc độc quyền như một bản cấu hình riêng cho đúng một aggregate; vẫn cần kiểm tra yêu cầu vòng đời trước khi dùng.

## 7. Quan hệ hai chiều: luôn cập nhật cả hai phía

Trong mô hình JPA hai chiều, `mappedBy` không có nghĩa là collection bên cha không quan trọng. Ngược lại, collection quyết định orphan nào bị loại khỏi aggregate, còn field bên con giữ khóa ngoại.

Những cách viết dễ gây sai:

```java
// Chỉ thêm bên cha, không set owning side:
order.getMutableLines().add(line);

// Chỉ đặt FK bên con về null, không cập nhật collection:
line.setPurchaseOrder(null);

// Chỉ xóa bằng repository con, collection managed của cha còn tham chiếu:
orderLineRepository.delete(line);
```

Với ví dụ đã xây dựng, các helper của `PurchaseOrder` thao tác theo cặp:

```java
// Khi thêm:
line.attachTo(order);
lines.add(line);

// Khi bỏ:
lines.remove(line);
line.detachFromOrder();
```

Đừng đưa public setter cho `purchaseOrder` hoặc collection mutable ra ngoài aggregate nếu nghiệp vụ yêu cầu đi qua root. Điều này cũng giúp kiểm tra quyền sở hữu, trạng thái đơn và các bất biến như “không cho sửa đơn đã CONFIRMED” ở một nơi.

Một vấn đề khác là `equals/hashCode`: nếu chúng chỉ dựa trên ID phát sinh từ database, hai entity mới đều có `id=null` có thể bị xem là bằng nhau, hoặc hash code thay đổi sau khi persist. Với tập `Set`, đây là nguồn gây thiếu phần tử và hành vi orphan khó hiểu. Mẫu sử dụng `List` và xác định phần tử cần xóa bằng ID đã tồn tại giúp giảm lỗi này.

## 8. Transaction, phiên bản và cập nhật đồng thời

`@Transactional` phải bao trùm quá trình tải aggregate, kiểm tra nghiệp vụ, thay đổi collection và flush/commit. Nếu thao tác trên collection lazy ngoài transaction, bạn có thể gặp lỗi `LazyInitializationException` trong Hibernate.

### 8.1. @Version trên root có đủ bảo vệ mọi thay đổi child?

`PurchaseOrder` có `@Version`, nhưng khi chỉ đổi các trường của `OrderLine`, **không thể giả định mọi JPA provider đều tăng version của `PurchaseOrder`**. Đặc biệt, thay đổi trường scalar của child không nhất thiết làm thay đổi row của root. Ngay cả cập nhật collection, việc root là phía `mappedBy` cũng ảnh hưởng thời điểm/provider tăng version.

Nếu quy tắc nghiệp vụ là **mọi thao tác với dòng hàng đều phải làm tăng version của toàn đơn**, có thể khóa optimistic theo root trong Service:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;
import java.util.Objects;

@PersistenceContext
private EntityManager entityManager;

private void requireExpectedVersion(
        PurchaseOrder order, Long expectedVersion) {
    if (!Objects.equals(order.getVersion(), expectedVersion)) {
        throw new OrderVersionConflictException(order.getId());
    }
    entityManager.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
}
```

Gọi `requireExpectedVersion(order, request.expectedVersion())` **trong transaction trước khi sửa child**. `OPTIMISTIC_FORCE_INCREMENT` yêu cầu provider kiểm tra và tăng phiên bản của entity root; nếu một transaction khác ghi root trước, transaction hiện tại phải thất bại thay vì âm thầm chấp nhận thay đổi. Mức khóa này làm giảm khả năng hai người sửa hai dòng khác nhau của cùng đơn cùng thành công, nên chỉ dùng khi cần quy tắc “phiên bản toàn đơn”.

Nếu nghiệp vụ cho phép cập nhật từng dòng độc lập, có thể dùng `@Version` riêng trên `OrderLine` và hợp đồng version riêng cho từng dòng. Khi đó phải xác định những bất biến cấp đơn nào vẫn cần đồng bộ bằng khóa hoặc điều kiện khác (ví dụ tổng giá trị, tồn kho, trạng thái CONFIRMED).

### 8.2. Phân biệt không tồn tại và xung đột

Với `DELETE /orders/10/lines/99`, phải kiểm tra trong phạm vi `Order 10`. Nếu dòng 99 không thuộc Order 10, phản hồi có thể là `404` theo hợp đồng API. Nếu client gửi phiên bản đơn đã cũ, hợp đồng có thể trả `409 Conflict` hoặc `412 Precondition Failed` khi sử dụng HTTP `If-Match`.

Lỗi optimistic locking cũng có thể xuất hiện tại flush/commit sau khi Service đã tìm thấy entity. Không nên bắt toàn bộ lỗi rồi tự động tải lại aggregate và ghi tiếp: điều đó có thể làm mất chỉnh sửa của transaction khác. Với conflict, caller cần xem bản hiện tại và quyết định có áp dụng lại lệnh hay không.

## 9. Cân nhắc giữa orphanRemoval và ràng buộc khóa ngoại DB

Một schema minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE purchase_order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    product_sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    CONSTRAINT fk_line_order
      FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_quantity_positive CHECK (quantity > 0)
);
```

Kiểu DDL/syntax chính xác thay đổi theo hệ quản trị DB; mục đích là biểu diễn FK bắt buộc và ràng buộc dữ liệu.

**`orphanRemoval` hoạt động ở tầng ORM:** khi một dòng bị loại khỏi collection của entity cha đang được quản lý, JPA phát lệnh xóa dòng.

**`ON DELETE CASCADE` hoạt động ở database:** khi bản ghi cha bị xóa trực tiếp, DB tự xóa các dòng con theo FK. Nó không thay thế `orphanRemoval` cho tình huống “giữ cha, xóa một dòng”. Hai cơ chế có thể cùng tồn tại nhưng cần thiết kế phù hợp để tránh xung đột giữa trạng thái persistence context và xóa ngoài ORM.

Nếu cho phép trực tiếp xóa record bằng SQL/bulk delete hoặc qua các dịch vụ khác, những đường đó không tự áp dụng lifecycle/callback của JPA. Cần thống nhất đâu là đường ghi chính và liệu có cần cơ chế bảo vệ tại database cho mọi đường ghi không.

## 10. Những lỗi phổ biến và cách sửa

### Lỗi 1: Cascade ALL tới mọi quan hệ

**Sai:** thêm `cascade=ALL` cho `@ManyToOne Product`, `Customer` hoặc `@ManyToMany Tag` vì muốn gọi một lệnh `save()` duy nhất.

**Sửa:** cascade theo **quyền sở hữu vòng đời**. Entity chia sẻ được tải/tham chiếu riêng; chỉ con thuộc độc quyền root mới nhận cascade remove.

### Lỗi 2: Bật orphanRemoval cho collection được chia sẻ

**Sai:** xóa một association phải chỉ xóa row liên kết, nhưng `orphanRemoval` lại có ý nghĩa xóa chính entity con.

**Sửa:** dùng join table hoặc cập nhật FK thích hợp khi tách association; chỉ xóa entity qua nghiệp vụ riêng.

### Lỗi 3: Chỉ sửa một phía của quan hệ hai chiều

**Sai:** `order.lines.add(line)` mà `line.purchaseOrder` vẫn null, hoặc xóa collection mà tham chiếu ngược không thay đổi.

**Sửa:** dùng `addLine` / `removeLine` của aggregate root để duy trì hai phía nhất quán.

### Lỗi 4: Bind trực tiếp request JSON vào entity rồi merge

**Sai:** nhận request chứa danh sách con chưa đầy đủ và thay thế luôn collection entity managed. Với `orphanRemoval`, các dòng “không hiện diện” có thể bị xóa.

**Sửa:** dùng DTO và lệnh cụ thể `add`, `changeQuantity`, `remove`. Nếu replace toàn bộ, thực hiện diff theo ID và xác nhận semantics của replace.

### Lỗi 5: Dùng bulk delete mà kỳ vọng cascade JPA

**Sai:** gọi bulk JPQL query hoặc `deleteAllInBatch` nhưng trông đợi `@PreRemove`, orphan removal hay cascade cho từng object.

**Sửa:** chọn đường xóa qua EntityManager đối với aggregate có lifecycle; dùng bulk delete khi đã quản lý tác động của nó lên callbacks, version và persistence context.

### Lỗi 6: Tách child khỏi cha rồi “gắn lại” cha khác trong cùng flush

**Sai:** coi child orphan như entity độc lập có thể chuyển tự do. Orphan removal có thể đã lập lịch xóa.

**Sửa:** làm rõ có cho phép chuyển quyền sở hữu hay không. Nếu không, tạo dòng mới cho cha mới và xóa dòng cũ theo một lệnh nghiệp vụ; nếu có, cân nhắc mô hình không dùng orphan removal.

### Lỗi 7: Tin rằng chỉ @Version của cha bảo vệ mọi trường của con

**Sai:** hai transaction sửa những child khác nhau mà chỉ nhìn version của cha, trong khi provider không tăng version cha cho các sửa đổi đó.

**Sửa:** định nghĩa mức xung đột mong muốn: khóa optimistic cưỡng bức trên root cho toàn aggregate, hoặc version/điều kiện ghi riêng cho từng child.

## 11. Gợi ý kiểm chứng bằng integration test

Với JPA, các tình huống quan trọng cần chạy trên database thật hoặc môi trường test có mapping và transaction tương đương sản phẩm. Những trường hợp mang tính hành vi gồm:

| Kịch bản | Dữ liệu đầu | Kỳ vọng sau commit |
|---|---|---|
| Tạo đơn có 2 dòng | Đơn chưa tồn tại | 1 đơn, 2 dòng cùng FK tới đơn |
| Thêm dòng | Đơn DRAFT có 2 dòng | 3 dòng; không sửa dòng cũ |
| Đổi số lượng | Đơn DRAFT có dòng ID 5 | Dòng 5 được `UPDATE`, không bị delete/insert lại |
| Bỏ một dòng | Đơn DRAFT có ID 5 và 6 | ID 5 bị xóa; ID 6 còn, FK không đổi |
| Xóa đơn | Đơn có các dòng riêng | Đơn và toàn bộ dòng thuộc đơn bị xóa; Product/Customer còn |
| Bỏ dòng thuộc đơn khác | Order 10 không sở hữu line 99 | Từ chối; line 99 và đơn sở hữu không đổi |
| Đơn đã CONFIRMED | Collection có dữ liệu | Không thêm/sửa/bỏ dòng; transaction không ghi thay đổi |
| Hai transaction sửa cùng aggregate | Hai transaction độc lập đọc một version | Theo chính sách optimistic lock, không chấp nhận ghi đè lặng lẽ |

Để quan sát hành vi `orphanRemoval`, cần **flush và clear persistence context** rồi truy vấn lại, thay vì chỉ xem collection trong bộ nhớ:

```java
// Minh họa trong một transaction kiểm thử.
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
Long lineToRemove = order.getLines().get(0).getId();

order.removeLine(lineToRemove);
entityManager.flush();
entityManager.clear();

OrderLine removed = entityManager.find(OrderLine.class, lineToRemove);
assert removed == null;
```

Trong kiểm thử thực tế, dùng assertion của JUnit/AssertJ thay cho Java `assert` nếu runtime có thể tắt assertion. Đừng chỉ kiểm tra rằng dòng biến mất khỏi `getLines()`: điều đó chưa chứng minh database đã xóa nó.

Đối với test song song, phải tạo hai transaction và persistence context độc lập, phối hợp thứ tự đọc/ghi để mô phỏng race. Gọi hai lần update tuần tự trong cùng một transaction không chứng minh được optimistic locking.

## 12. Quy trình ra quyết định cho dự án thật

Khi chuẩn bị thêm cascade hoặc `orphanRemoval` cho một quan hệ, thực hiện theo thứ tự:

1. Xác định **aggregate root** và đối tượng con có vòng đời phụ thuộc thật sự.
2. Phân biệt entity **được sở hữu độc quyền** với entity **được chia sẻ**; đặt cascade remove/orphan removal chỉ trong phạm vi phù hợp.
3. Chọn ánh xạ `@OneToMany`/`@ManyToOne` và owning side quản lý FK; viết helper đồng bộ cả hai phía.
4. Khóa thay đổi collection sau các method nghiệp vụ của root; Service tải root và thay đổi trong `@Transactional`.
5. Xác định API đang thực hiện **thêm**, **sửa**, **bỏ** hay **thay thế toàn bộ**; không suy ra lệnh xóa từ payload thiếu trường.
6. Chọn chính sách concurrency: version cho từng child hay version toàn aggregate, sau đó bảo vệ đường ghi tương ứng.
7. Kiểm chứng sau flush/commit rằng chỉ đúng các dòng con cần thay đổi đã bị tác động và dữ liệu dùng chung vẫn nguyên vẹn.

Trong thực hành JPA, **cascade điều khiển sự lan truyền của thao tác persistence; `orphanRemoval` điều khiển việc xóa con bị tách khỏi quan hệ sở hữu**. Cả hai chỉ an toàn khi mô hình quan hệ phản ánh đúng quyền quản lý vòng đời, các thao tác đi qua aggregate root và mỗi thay đổi có phạm vi rõ ràng. Khi đó việc lưu một đơn hàng cùng các dòng hay bỏ riêng một dòng sẽ trở thành hành vi có thể dự đoán, bảo trì và kiểm soát dữ liệu.
