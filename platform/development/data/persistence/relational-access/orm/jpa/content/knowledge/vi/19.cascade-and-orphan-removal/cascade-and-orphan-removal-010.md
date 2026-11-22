# Phối hợp orphanRemoval với phía sở hữu và ràng buộc khóa ngoại trong JPA

Trong JPA, một entity cha thường chứa collection các entity con. Ví dụ `PurchaseOrder` có nhiều `OrderLine`, hoặc một `CustomerAccount` có một `AccountSettings`. Nếu entity con **không còn ý nghĩa nghiệp vụ khi rời khỏi cha**, ứng dụng có thể dùng `orphanRemoval = true` để yêu cầu JPA xóa bản ghi con khi quan hệ bao chứa bị loại bỏ.

Tuy nhiên, chỉ thêm `orphanRemoval = true` vào annotation chưa đủ để tạo ra một mô hình dữ liệu đúng. Với cơ sở dữ liệu quan hệ, ứng dụng cần phối hợp đồng thời:

1. **Quan hệ sở hữu vòng đời về nghiệp vụ**: entity nào được xem là thành phần phụ thuộc?
2. **Owning side của JPA association**: thuộc tính nào thực sự điều khiển khóa ngoại hoặc bảng nối?
3. **Ràng buộc vật lý của database**: `FOREIGN KEY`, `NOT NULL`, `UNIQUE` và chính sách xóa.
4. **Trạng thái trong persistence context**: entity managed, collection được theo dõi, dirty checking và thời điểm flush.
5. **Ranh giới transaction**: `DELETE` có thể chạy trước khi commit nhưng vẫn có khả năng rollback.

Bài học này sử dụng mô hình đơn hàng–dòng hàng để giải thích `@OneToMany` hai chiều, tiếp tục với quan hệ một-một và shared primary key, rồi đi vào các tình huống dễ sai: chỉ cập nhật inverse side, tách entity con rồi chuyển sang cha khác, thay phần mở rộng trong cùng transaction, xóa qua bulk JPQL, và dùng `ON DELETE CASCADE` song song với orphan removal.

> **Tư tưởng chính:** `orphanRemoval` diễn đạt **xóa entity phụ thuộc khi mất quan hệ bao chứa**; owning side diễn đạt **ai ghi liên kết vào DB**; FK constraint diễn đạt **trạng thái dữ liệu nào được DB chấp nhận**. Ba cơ chế bổ sung cho nhau, không thay thế nhau.

## 1. Phân tích quy tắc nghiệp vụ trước khi bật orphanRemoval

Giả sử có ba yêu cầu:

- Một đơn hàng gồm nhiều dòng hàng; một dòng hàng chỉ tồn tại trong một đơn hàng.
- Mỗi dòng hàng trỏ tới một sản phẩm trong danh mục.
- Danh mục sản phẩm vẫn tồn tại dù một dòng hàng hoặc cả đơn hàng bị xóa.

Từ đây có hai loại quan hệ khác nhau:

~~~text
PurchaseOrder (1) ---- (N) OrderLine (N) ---- (1) Product
      |                       |                       |
      |                       |                       |
   Aggregate              Thành phần                Entity
      root                phụ thuộc               dùng chung
~~~

Với `PurchaseOrder → OrderLine`:

- Xóa một dòng khỏi đơn có thể đồng nghĩa **xóa dòng đó khỏi database**.
- Xóa đơn có thể kéo theo xóa những dòng thuộc đơn, nếu nghiệp vụ cho phép xóa vật lý.
- Dòng hàng không được giữ lại như entity độc lập sau khi mất đơn cha.
- `orphanRemoval = true` là một lựa chọn hợp lý.

Với `OrderLine → Product`:

- Xóa dòng hàng **không được xóa Product**.
- Một Product có thể được hàng nghìn dòng khác tham chiếu.
- Đây là liên kết tham chiếu entity độc lập, **không nên dùng cascade REMOVE** cho Product.
- `orphanRemoval` không áp dụng cho `@ManyToOne`.

### 1.1. Orphan là gì?

*Orphan* trong ngữ cảnh này là một entity con bị tách khỏi quan hệ phụ thuộc mà ứng dụng muốn duy trì với entity cha.

Ví dụ:

~~~text
Trước:
Order #10
   +-- Line #101
   +-- Line #102

Sau khi loại Line #102:
Order #10
   +-- Line #101

Line #102 không còn được phép tồn tại độc lập
=> JPA cần xóa Line #102 theo orphanRemoval.
~~~

Orphan removal **không** có nghĩa mọi entity không có foreign key đều bị JPA tự tìm và xóa định kỳ. Nó là thao tác vòng đời được kích hoạt bởi thay đổi quan hệ được JPA theo dõi trong persistence context, khi mapping phù hợp.

### 1.2. Có phải mọi One-to-Many đều cần orphanRemoval?

Không. So sánh:

| Quan hệ | Con rời cha sẽ ra sao? | `orphanRemoval` thường phù hợp? |
|---|---|---|
| Order → OrderLine | Dòng không còn ý nghĩa, cần xóa | Có |
| ShoppingCart → CartItem | Item bị bỏ khỏi giỏ cần xóa | Có, tùy chính sách |
| Invoice → InvoiceLine | Thường không được xóa lịch sử hóa đơn đã phát hành | Chỉ theo chính sách, thường hạn chế sửa/xóa |
| Department → Employee | Nhân viên có thể chuyển phòng hoặc tạm chưa có phòng | Thường không |
| Customer → AddressBookEntry | Entry có thể bị xóa khi khách xóa khỏi sổ địa chỉ | Có thể |
| Project → Task | Task có thể chuyển dự án hoặc cần lưu audit | Cần phân tích |
| OrderLine → Product | Product tồn tại độc lập | Không dùng orphanRemoval ở Many-to-One |

Từ khóa quyết định là **quyền sở hữu vòng đời**, không phải việc Java có `List`, `Set` hoặc annotation `@OneToMany`.

## 2. Hai nghĩa khác nhau của chữ “sở hữu”

Đây là nguồn gốc của nhiều lỗi JPA.

### 2.1. Sở hữu nghiệp vụ: Ai kiểm soát vòng đời?

`PurchaseOrder` được xem là aggregate root. `OrderLine` phụ thuộc vào đơn và không tồn tại độc lập. Đây là **business ownership** hoặc *lifecycle ownership*.

Nó trả lời: “Nếu một dòng hàng bị gỡ khỏi đơn, ta nên giữ nó, chuyển sang đơn khác, hay xóa nó?”

### 2.2. Owning side JPA: Ai điều khiển FK?

Trong quan hệ hai chiều:

~~~java
// PurchaseOrder
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;

// OrderLine
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
~~~

`OrderLine.order` là **owning side** của liên kết theo JPA, vì cột FK `order_line.order_id` nằm ở bảng con và được ánh xạ bởi field đó.

`PurchaseOrder.lines` là **inverse side**, vì dùng `mappedBy = "order"`.

### 2.3. Điều này không mâu thuẫn

~~~text
VÒNG ĐỜI NGHIỆP VỤ                    LIÊN KẾT DATABASE

PurchaseOrder                       OrderLine.order
  sở hữu các OrderLine                là JPA owning side
         |                                   |
         v                                   v
orphanRemoval=true                 order_line.order_id
trên Order.lines                   FK trỏ purchase_order.id
~~~

**Entity cha sở hữu vòng đời không có nghĩa collection của cha phải là owning side của JPA association.**

Trong một quan hệ hai chiều thông thường, collection phía cha có thể khai báo `orphanRemoval = true` và `mappedBy`, trong khi thuộc tính phía con vẫn là owning side điều khiển FK.

### 2.4. Ba câu hỏi phải tách riêng

1. Entity con có được phép tồn tại khi mất cha không? → Quyết định `orphanRemoval`.
2. Cột FK nằm ở bảng nào và field nào ánh xạ nó? → Quyết định `@JoinColumn` / `mappedBy`.
3. DB có được phép chứa FK null hoặc trỏ tới record không tồn tại không? → Quyết định `NOT NULL`, `FOREIGN KEY` và chính sách xóa.

## 3. Thiết kế schema Order–OrderLine trước khi viết JPA

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14, 2) NOT NULL,

    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id),

    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id)
        REFERENCES product(id),

    CONSTRAINT ck_line_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_line_unit_price
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_order_line_order_id
    ON order_line(order_id);
~~~

Ở đây:

- `order_line.order_id` là FK bắt buộc và không null.
- `order_line.product_id` là FK bắt buộc đến Product.
- Không có yêu cầu `UNIQUE(order_id)`, vì một Order có thể có nhiều dòng.
- `PRIMARY KEY(id)` định danh riêng từng OrderLine.
- Index trên FK có thể giúp tải dòng theo đơn hoặc xử lý xóa; index không phải điều kiện bắt buộc của annotation nhưng quan trọng khi có dữ liệu lớn.
- Không đặt `ON DELETE CASCADE` trong ví dụ gốc, để chính sách xóa qua JPA được minh họa rõ ràng. Có thể thêm ở một thiết kế khác, nhưng phải hiểu tương tác.

### 3.1. `nullable = false` và `optional = false` ở đâu?

Ở entity con:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
~~~

- `optional = false` mô tả liên kết bắt buộc trong metadata JPA.
- `nullable = false` mô tả cột join không được null trong schema do JPA tạo.
- `FOREIGN KEY (order_id)` ở database ngăn con trỏ đến cha không tồn tại.
- `NOT NULL` ở database ngăn một bản ghi con còn sống nhưng không có cha.

Hai annotation Java **không thay thế việc kiểm tra migration/DDL thực tế**. Nếu DB đã tồn tại, sửa annotation không tự đảm bảo migration đã thêm constraint.

### 3.2. Tại sao FK không null không cấm orphanRemoval?

Nếu dòng hàng bị gỡ khỏi đơn và `orphanRemoval = true`, mục tiêu cuối cùng là **xóa cả row OrderLine**, không phải để row tồn tại với `order_id = NULL`.

Kết quả mong muốn:

~~~sql
DELETE FROM order_line WHERE id = 102;
~~~

chứ không phải trạng thái cuối:

~~~sql
UPDATE order_line SET order_id = NULL WHERE id = 102;
~~~

vì lệnh UPDATE đó sẽ vi phạm `NOT NULL`.

JPA provider thường triển khai orphan removal bằng thao tác xóa entity con tại flush. Nhưng **thứ tự và hình dạng SQL cụ thể không phải hợp đồng portable cho mọi provider/mapping**; phải kiểm thử trên cấu hình thực tế, đặc biệt khi có constraint chặt hoặc nhiều thao tác thay thế liên tiếp.

## 4. Mapping entity Product: Một tham chiếu độc lập

Ví dụ tối giản:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

`Product` tồn tại độc lập với đơn hàng. Các OrderLine chỉ tham chiếu Product qua FK. Không đặt `CascadeType.REMOVE` trên `OrderLine.product` chỉ vì muốn xóa OrderLine theo Order.

## 5. Mapping đầy đủ: PurchaseOrder là chủ vòng đời

~~~java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(
        name = "order_number",
        nullable = false,
        unique = true,
        length = 40
    )
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status = OrderStatus.DRAFT;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public OrderLine addLine(
            Product product,
            int quantity,
            BigDecimal unitPrice) {

        requireDraft();

        OrderLine line =
            new OrderLine(this, product, quantity, unitPrice);

        lines.add(line);
        return line;
    }

    public void removeLine(OrderLine line) {
        requireDraft();

        if (line == null || !lines.contains(line)) {
            throw new IllegalArgumentException(
                "Line does not belong to this order"
            );
        }

        lines.remove(line);
        line.detachFromOrder();
    }

    public void confirm() {
        requireDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot confirm an empty order"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only DRAFT orders can be modified"
            );
        }
    }
}
~~~

Enum minh họa:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Những quyết định chính trong `PurchaseOrder`:

1. `@OneToMany(mappedBy = "order")` khai báo inverse side và trỏ tới **tên field Java** `OrderLine.order`.
2. `cascade = ALL` cho phép các thao tác persistence từ cha lan tới thành phần con trong mô hình vòng đời phụ thuộc.
3. `orphanRemoval = true` yêu cầu xóa dòng hàng được tách khỏi quan hệ bao chứa, thay vì giữ dòng mồ côi.
4. `lines` được khởi tạo rỗng; trong giai đoạn DRAFT, đơn có thể chưa có dòng. Quy tắc “ít nhất một dòng” được kiểm tra ở `confirm()`.
5. `addLine` và `removeLine` là API nghiệp vụ, không để caller tùy ý mutate list.
6. `@Version` trên PurchaseOrder hỗ trợ optimistic locking khi chính entity Order được cập nhật; nếu cần bảo vệ thêm xung đột trên collection ở nhiều transaction, phải kiểm chứng chiến lược lock thực tế.
7. Không cấu hình cascade từ PurchaseOrder sang Product: Product chỉ được tham chiếu gián tiếp qua OrderLine.

### 5.1. Không công khai setter cho toàn bộ collection

Đây là kiểu API dễ gây lỗi:

~~~java
public void setLines(List<OrderLine> newLines) {
    this.lines = newLines;
}
~~~

Khi entity đang managed, collection có thể được provider thay bằng một wrapper để theo dõi thay đổi. Việc thay hẳn reference có thể gây khó khăn với orphanRemoval hoặc hành vi collection tracking, nhất là trong một số provider như Hibernate.

Thay vì thay collection, hãy cung cấp thao tác thay đổi **trên instance collection đang được quản lý** qua helper:

~~~java
order.addLine(product, 2, price);
order.removeLine(existingLine);
~~~

Nếu cần đồng bộ list từ request DTO, hãy tính những dòng cần thêm, sửa và xóa; không gán nguyên một `new ArrayList<>(dtoLines)` vào field persistence.

## 6. Mapping entity OrderLine: Phía sở hữu khóa ngoại

~~~java
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

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_line")
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

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    OrderLine(
            PurchaseOrder order,
            Product product,
            int quantity,
            BigDecimal unitPrice) {

        this.order = Objects.requireNonNull(order, "order");
        this.product = Objects.requireNonNull(product, "product");

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Invalid unit price"
            );
        }

        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }

    void detachFromOrder() {
        // Chỉ gọi qua PurchaseOrder.removeLine().
        // Entity bị tách được dự kiến xóa bởi orphanRemoval.
        this.order = null;
    }
}
~~~

Cấu hình `OrderLine.order` điều khiển FK:

~~~text
PurchaseOrder.lines
  @OneToMany(mappedBy="order", orphanRemoval=true)
          |
          | inverse side
          v
OrderLine.order
  @ManyToOne(optional=false)
  @JoinColumn(name="order_id", nullable=false)
          |
          | owning side
          v
order_line.order_id
  NOT NULL + FOREIGN KEY
~~~

Cả `OrderLine.order` và `OrderLine.product` đều là `@ManyToOne`, nhưng chúng có **ý nghĩa vòng đời khác nhau**. `order` là liên kết đến cha bao chứa; `product` là tham chiếu entity dùng chung.

### 6.1. Field order được gán null khi tách thì có mâu thuẫn optional=false không?

Trong helper `removeLine`, sau khi xóa khỏi collection, `line.detachFromOrder()` đặt field `order` thành null để biểu diễn trong bộ nhớ rằng line không còn thuộc order nào.

Đây là **trạng thái trung gian của entity chuẩn bị bị xóa**, không phải trạng thái cuối cùng mà ứng dụng muốn persist thành row với FK null. Khi xử lý orphan, provider được kỳ vọng thực hiện xóa entity con lúc flush theo mapping.

Tuy vậy:

- Không gọi `detachFromOrder()` trực tiếp trên một OrderLine vẫn còn nằm trong `order.lines`.
- Không giữ một entity bị tách làm object còn được quản lý để tiếp tục lưu hoặc chuyển sang cha khác.
- Không cố flush một thay đổi FK thành null rồi mới quyết định xóa nếu mapping không xử lý orphan như dự kiến.
- Kiểm tra SQL của provider trên schema có `NOT NULL`; thứ tự SQL cụ thể không phải phần ứng dụng nên tùy tiện dựa vào.

Nếu mapping/provider cụ thể có vấn đề với trình tự xóa, có thể chọn một operation xóa rõ ràng, đồng bộ quan hệ trong bộ nhớ và gọi `entityManager.remove(managedLine)` theo thiết kế; không giải quyết bằng cách bỏ FK constraint để che lỗi.

## 7. Helper hai chiều: Thêm và xóa phải đồng bộ

Một nguyên tắc JPA quan trọng: với quan hệ hai chiều, **ứng dụng có trách nhiệm giữ hai phía nhất quán trong bộ nhớ**.

### 7.1. Thêm đúng

~~~java
public OrderLine addLine(
        Product product, int quantity, BigDecimal price) {

    OrderLine line = new OrderLine(this, product, quantity, price);
    lines.add(line);
    return line;
}
~~~

Kết quả:

~~~text
order.lines.contains(line) == true
line.getOrder() == order
~~~

Provider sẽ dùng `line.order` để xác định FK `order_id`.

### 7.2. Thêm sai: Chỉ cập nhật inverse collection

~~~java
OrderLine line = ...;

order.getMutableLines().add(line);
// line.order vẫn null hoặc trỏ tới order khác.
~~~

Nếu phía owning side chưa được cập nhật, JPA có thể không ghi đúng FK, gây vi phạm NOT NULL hoặc làm liên kết không khớp mong đợi.

Chỉ vì entity xuất hiện trong collection Java không có nghĩa DB biết nó thuộc order nào.

### 7.3. Xóa đúng

~~~java
public void removeLine(OrderLine line) {
    if (!lines.remove(line)) {
        throw new IllegalArgumentException("Line not found");
    }

    line.detachFromOrder();
}
~~~

Kết quả cuối mong đợi:

~~~text
order.lines không còn line
line.order == null (trong bộ nhớ, chuẩn bị xóa)
row order_line tương ứng được DELETE ở flush
~~~

### 7.4. Xóa sai: Chỉ sửa owning side

~~~java
line.detachFromOrder();
// order.lines vẫn chứa line.
~~~

Đây là trạng thái object graph không nhất quán. Với FK NOT NULL, một thao tác cố đồng bộ association thành null có thể gây lỗi, và provider không có nghĩa vụ hiểu chính xác ý định xóa khỏi collection của cha khi collection vẫn giữ phần tử.

Để khai báo việc orphan của `@OneToMany`, hãy thay đổi quan hệ bao chứa theo cách JPA theo dõi được, đồng thời đồng bộ owning side.

### 7.5. Một phương thức domain tốt không cần public mutable collection

Ví dụ expose read-only view:

~~~java
public List<OrderLine> getLines() {
    return Collections.unmodifiableList(lines);
}
~~~

Code bên ngoài có thể duyệt các dòng nhưng không thể tùy tiện gọi `clear()`, `remove()` hoặc `add()` làm phá invariant. Việc sửa nội dung OrderLine cần thực hiện qua method có quy tắc trạng thái DRAFT/CONFIRMED.

Nếu UI gửi list mới, service nên **đối chiếu ID và thao tác từng phần tử**, thay vì dùng setter thay toàn bộ collection.

## 8. `orphanRemoval` và `CascadeType.REMOVE` không giống nhau

Đây là hai cơ chế thường cùng xuất hiện nhưng kích hoạt trong những hoàn cảnh khác nhau.

### 8.1. `CascadeType.REMOVE` khi xóa cha

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
~~~

Nếu ứng dụng gọi:

~~~java
entityManager.remove(order);
~~~

`CascadeType.REMOVE` yêu cầu thao tác remove lan sang những OrderLine thuộc association theo quy tắc cascade.

Nhưng nếu chỉ gỡ một line khỏi collection mà **không remove Order**, riêng `CascadeType.REMOVE` không diễn đạt việc xóa entity con bị tách.

### 8.2. `orphanRemoval = true` khi tách con

~~~java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Nếu một OrderLine đang tồn tại bị gỡ khỏi quan hệ bao chứa, JPA áp dụng remove cho entity orphan ở thời điểm flush theo ngữ nghĩa orphanRemoval.

Với `@OneToOne` hoặc `@OneToMany` có orphanRemoval, thao tác remove trên nguồn cũng dẫn đến remove target theo quy tắc của đặc tả; không nhất thiết phải khai báo thêm `CascadeType.REMOVE` chỉ để xóa target khi xóa cha. Tuy nhiên, các cascade khác như PERSIST/MERGE vẫn là các quyết định riêng.

### 8.3. Bảng so sánh

| Hành động | Chỉ `cascade=REMOVE` | Chỉ `orphanRemoval=true` |
|---|---|---|
| `entityManager.remove(parent)` | Lan remove sang child | Child được remove theo ngữ nghĩa orphan removal |
| Loại child khỏi collection mà parent còn tồn tại | Không tự có nghĩa xóa child | **Child orphan được remove** |
| Gán `parent.profile=null` với one-to-one | Không đủ để xóa chỉ nhờ cascade REMOVE | Có thể xóa profile bị tách |
| Persist parent cùng child mới | Không, nếu không có PERSIST cascade | Orphan removal tự nó không thay thế cascade PERSIST |
| Thay đổi child sang parent khác | Không giải quyết lifecycle | Không được giả định là move an toàn của orphan |
| Xóa Product dùng chung | Có thể nguy hiểm nếu cascade REMOVE sai | Không áp dụng orphanRemoval trên Many-to-One |

### 8.4. Vì sao hay dùng `cascade = ALL` cùng orphanRemoval?

Trong mô hình OrderLine hoàn toàn phụ thuộc PurchaseOrder, thường muốn:

- Persist Order cùng các line mới.
- Merge phù hợp nếu có use case làm việc với detached graph.
- Remove các line khi remove Order.
- Remove từng line khi gỡ khỏi Order.

Do đó:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

là lựa chọn phổ biến. Nhưng `ALL` không phải câu thần chú; cần quyết định xem mọi thao tác cascade có đúng với vòng đời thực hay không. Nếu chỉ muốn một tập con, có thể chọn `PERSIST` và `MERGE` hoặc các lựa chọn phù hợp thay vì `ALL`.

## 9. Phối hợp orphanRemoval với FK NOT NULL

### 9.1. Không để orphan tồn tại ở trạng thái cuối

Với schema:

~~~sql
order_id BIGINT NOT NULL REFERENCES purchase_order(id)
~~~

một dòng hàng còn tồn tại mà `order_id` null là không hợp lệ.

Có hai nghiệp vụ khác nhau:

**Nghiệp vụ A: xóa dòng hàng khỏi đơn.**

~~~text
Trước: OrderLine #102, order_id=10
Sau:   Không còn OrderLine #102
~~~

Đây là mục tiêu phù hợp với orphanRemoval.

**Nghiệp vụ B: tách dòng hàng khỏi đơn nhưng giữ lại làm bản nháp độc lập.**

~~~text
Trước: OrderLine #102, order_id=10
Sau:   OrderLine #102, order_id=NULL
~~~

Nghiệp vụ B **không tương thích** với FK NOT NULL; nếu thật sự cần, phải thay đổi domain model và schema. Không bật orphanRemoval cho B vì nó sẽ xóa thay vì giữ con.

### 9.2. Có cần FK `ON DELETE CASCADE` không?

Không bắt buộc. Có thể giữ FK mặc định `NO ACTION`/`RESTRICT` theo DB, rồi cho ORM xóa child trước parent.

Ví dụ SQL kỳ vọng:

~~~sql
BEGIN;

DELETE FROM order_line WHERE id = 101;
DELETE FROM order_line WHERE id = 102;
DELETE FROM purchase_order WHERE id = 10;

COMMIT;
~~~

Provider có thể dùng batching, một SQL khác hoặc thứ tự tương đương. Khi schema từ chối xóa cha trước khi con được xóa, ORM phải có mapping/operation đúng để thỏa ràng buộc.

### 9.3. FK constraint là lớp bảo vệ cuối

Khi có code JDBC khác xóa trực tiếp Order:

~~~sql
DELETE FROM purchase_order WHERE id = 10;
~~~

nếu FK không có `ON DELETE CASCADE` và còn dòng con, database thường từ chối lệnh này. `orphanRemoval` trên Java **không tự chạy** khi có đường ghi trực tiếp ngoài EntityManager.

Đó có thể là hành vi mong muốn: chỉ cho xóa qua quy trình nghiệp vụ đã thiết kế. Nếu nhiều hệ thống được phép xóa vật lý bằng SQL, cần thống nhất chính sách DB-level deletion.

## 10. `ON DELETE CASCADE` khác orphanRemoval ra sao?

Database có thể khai báo:

~~~sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES purchase_order(id)
        ON DELETE CASCADE
);
~~~

Khi trực tiếp xóa row parent, DB xóa các row con tham chiếu theo hành vi FK.

Nhưng:

- **`orphanRemoval`:** JPA phát hiện một entity con rời khỏi association được theo dõi và áp dụng thao tác remove.
- **`CascadeType.REMOVE`:** JPA lan truyền remove từ entity nguồn đến entity đích.
- **`ON DELETE CASCADE`:** Database xóa row con khi FK parent bị xóa, kể cả nếu thao tác delete được phát ra ngoài JPA.

### 10.1. DB cascade không tự kích hoạt orphan removal khi chỉ thay collection

Nếu cha còn tồn tại nhưng chỉ loại một line ra khỏi `order.lines`, `ON DELETE CASCADE` trên FK không có điều kiện kích hoạt; parent row vẫn tồn tại.

Cần thao tác xóa child qua JPA orphanRemoval hoặc một lệnh xóa tường minh.

### 10.2. JPA callback và persistence context

Khi DB tự xóa row qua `ON DELETE CASCADE`, JPA provider không nhất thiết biết từng entity con đã bị xóa nếu các row biến mất ngoài đường remove do ORM điều phối. Các lifecycle callbacks, cache và managed state có thể không được đồng bộ như khi gọi `entityManager.remove(child)`.

Vì vậy, không nên bật cả hai cơ chế mà không có chính sách rõ về:

- Ai chịu trách nhiệm xóa trong đường đi bình thường?
- Có entity listener/callback quan trọng không?
- Cache cấp hai có cần invalidation không?
- Các system khác có ghi/xóa trực tiếp DB không?
- Schema migration đã mô tả đúng hành vi chưa?

Nếu provider có extension tích hợp DB cascade, phải xem tài liệu của provider/phiên bản cụ thể, không coi đó là tính năng portable của `orphanRemoval`.

## 11. Thời điểm orphan được xóa: Flush, không phải ngay khi gọi `remove`

Giả sử:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

order.removeLine(line);
~~~

Sau câu gọi `removeLine`:

- Java collection không còn line.
- Provider có thể ghi nhận thay đổi quan hệ.
- SQL `DELETE` **có thể chưa được thực thi**.
- Transaction chưa chắc đã commit.

Đến:

~~~java
em.flush();
~~~

JPA đồng bộ các thay đổi pending trong transaction, bao gồm việc xóa orphan theo mapping.

Sau:

~~~java
tx.commit();
~~~

nếu commit thành công, deletion mới được xác nhận. Nếu rollback, database có thể giữ lại row OrderLine như trước transaction.

### 11.1. Sơ đồ trạng thái

~~~text
OrderLine đang persistent
          |
          v
Loại khỏi Order.lines
          |
          v
Trong bộ nhớ: đã tách
Trong DB: có thể vẫn còn row
          |
          v
FLUSH
          |
          v
DELETE order_line ...
          |
      +---+---+
      |       |
   COMMIT   ROLLBACK
      |       |
      v       v
   Row bị   Row có thể
   xóa      vẫn tồn tại
   lâu dài  như trước
~~~

SQL gửi tại flush chưa phải dữ liệu committed cho transaction khác.

### 11.2. `FlushModeType.AUTO` và `COMMIT`

Nếu đang ở `AUTO`, một JPQL query có thể bị ảnh hưởng bởi việc xóa orphan; JPA phải bảo đảm semantics của query theo quy tắc flush mode, có thể flush trước query.

Nếu ở `COMMIT` mà chưa flush, ảnh hưởng của các thay đổi pending tới kết quả query trước commit **không được đặc tả bảo đảm**. Nếu query cần dựa trên kết quả xóa, flush tường minh trong transaction phù hợp.

Không dùng `FlushModeType.COMMIT` để suy ra orphan “chưa bị xóa” hay “chắc chắn đã bị xóa”.

## 12. Cẩn trọng với việc chuyển một orphan sang cha khác

Giả sử Line #102 thuộc Order #10. Người dùng muốn chuyển dòng sang Order #20.

Một ý tưởng:

~~~java
order10.removeLine(line);
order20.addExistingLine(line);
~~~

Nhưng `order10.lines` có `orphanRemoval = true`. Khi line bị tách, nó có thể được lên lịch remove. **Đặc tả JPA không cho phép ứng dụng dựa vào việc reassign một entity orphan sang association khác rồi mong nó tự được “cứu” một cách portable.**

Với orphanRemoval, ứng dụng **không nên reassociate entity đã bị orphan** hoặc cố persist lại nó như một phần của thao tác thay cha.

### 12.1. Khi nào không nên dùng orphanRemoval?

Nếu nghiệp vụ yêu cầu:

- OrderLine có thể chuyển sang đơn khác mà giữ nguyên identity.
- Employee có thể chuyển Department.
- Task có thể chuyển Project.
- Address có thể được dùng chung và đổi owner.

thì **quan hệ đó không còn là quan hệ sở hữu vòng đời độc quyền** theo cách orphanRemoval thường được dùng. Cân nhắc:

- Không bật orphanRemoval.
- Có một operation chuyển cha cập nhật owning FK và hai collection trong cùng transaction.
- Xác định FK nullable hay mandatory theo nghiệp vụ.
- Bảo vệ tính nhất quán và concurrency tại DB.

### 12.2. Nếu nghiệp vụ cho phép “chuyển” thông tin nhưng không chuyển identity

Với OrderLine, có thể thiết kế “sao chép dòng sang đơn khác”:

1. Tạo OrderLine **mới** ở Order #20 với Product, quantity, unitPrice tương ứng.
2. Xóa OrderLine cũ khỏi Order #10 để orphanRemoval xóa bản ghi cũ.
3. Xem đây là **một dòng mới có ID mới**, không phải reparent cùng entity.
4. Nếu có lịch sử/audit, lưu quan hệ nguồn–đích bằng metadata nghiệp vụ phù hợp.

Đây là một nghiệp vụ khác với việc chuyển FK của cùng row; cần xác nhận yêu cầu trước khi chọn.

## 13. Một-nhiều một chiều và join table: Đừng đoán nơi lưu FK

Không phải mọi `@OneToMany` đều có cùng cách ghi FK.

### 13.1. Một chiều với join table

Một `@OneToMany` một chiều không có `mappedBy` có thể sử dụng join table theo mapping mặc định hoặc theo cấu hình rõ ràng.

Ví dụ:

~~~java
@Entity
public class Team {

    @Id
    private Long id;

    @OneToMany(orphanRemoval = true)
    @JoinTable(
        name = "team_member",
        joinColumns = @JoinColumn(name = "team_id"),
        inverseJoinColumns = @JoinColumn(name = "member_id")
    )
    private List<TeamMember> members = new ArrayList<>();
}
~~~

Sơ đồ:

~~~text
team
   id
    |
    v
team_member
   team_id (FK)
   member_id (FK)
    |
    v
team_member_entity
   id
~~~

Trong thiết kế này, liên kết được lưu qua **join table**. Việc xóa khỏi collection có thể tác động row join table; nếu orphanRemoval bật và TeamMember thực sự là entity phụ thuộc, còn có yêu cầu xóa entity TeamMember orphan.

Cần ràng buộc unique thích hợp để bảo vệ rằng mỗi TeamMember chỉ có một Team nếu đó là quan hệ một-nhiều, không phải nhiều-nhiều được ngụy trang.

### 13.2. Một chiều dùng FK ở bảng con

Có thể cấu hình một `@OneToMany` một chiều với `@JoinColumn` đặt trên collection:

~~~java
@OneToMany(orphanRemoval = true)
@JoinColumn(name = "team_id", nullable = false)
private List<TeamMember> members;
~~~

Trong trường hợp này, có thể JPA quản lý FK ở bảng child thông qua mapping collection, thay vì field `TeamMember.team` ở child (vì không có chiều ngược).

Khác biệt so với ví dụ hai chiều Order–OrderLine:

- Không có `mappedBy`.
- Không có `@ManyToOne Team` trên entity child trong cách ánh xạ này.
- Phía collection điều khiển liên kết theo cấu trúc mapping.
- SQL để persist/remove có thể khác, cần kiểm thử với NOT NULL và generator phù hợp.

### 13.3. Khi child cần biết parent, quan hệ hai chiều thường rõ hơn

Nếu nghiệp vụ cần `line.getOrder()` và DB có cột `order_line.order_id`, cấu hình:

~~~java
// Parent
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;

// Child
@ManyToOne(optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
~~~

thường diễn đạt rõ owning FK, điều hướng hai chiều và lifecycle.

Đừng thêm `mappedBy` cùng với `@JoinColumn` trên phía inverse như thể cả hai phía cùng sở hữu FK; hãy chọn **một cơ chế ownership nhất quán**.

## 14. Quan hệ một-một: Orphan removal và UNIQUE foreign key

Một yêu cầu khác:

> Một tài khoản có tối đa một bộ cài đặt bảo mật nâng cao. Bộ cài đặt chỉ tồn tại cùng tài khoản và phải bị xóa khi tài khoản gỡ nó.

Schema có FK riêng và UNIQUE:

~~~sql
CREATE TABLE customer_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE
);

CREATE TABLE account_settings (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE,
    two_factor_enabled BOOLEAN NOT NULL,

    CONSTRAINT fk_settings_account
        FOREIGN KEY (account_id)
        REFERENCES customer_account(id)
);
~~~

`account_id` vừa là FK vừa có UNIQUE, bảo đảm mỗi Account có **tối đa một** Settings.

### 14.1. Parent side

~~~java
@Entity
@Table(name = "customer_account")
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private AccountSettings settings;

    protected CustomerAccount() {
    }

    public void addSettings() {
        if (settings != null) {
            throw new IllegalStateException(
                "Settings already exist"
            );
        }
        settings = new AccountSettings(this);
    }

    public void removeSettings() {
        if (settings != null) {
            settings.detachFromAccount();
            settings = null;
        }
    }
}
~~~

### 14.2. Child owning side

~~~java
@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true
    )
    private CustomerAccount account;

    @Column(name = "two_factor_enabled", nullable = false)
    private boolean twoFactorEnabled;

    protected AccountSettings() {
    }

    AccountSettings(CustomerAccount account) {
        this.account = Objects.requireNonNull(account);
    }

    void detachFromAccount() {
        this.account = null;
    }
}
~~~

Ở đây:

- `CustomerAccount.settings` là inverse side nhưng có `orphanRemoval=true`.
- `AccountSettings.account` giữ FK và là owning side.
- Khi Settings bị gỡ khỏi Account, entity Settings được dự kiến xóa.
- `UNIQUE(account_id)` bảo vệ cardinality 1:1 ở DB.
- `NOT NULL` bảo vệ Settings không tồn tại độc lập.
- Cần đồng bộ cả hai phía và giữ operation trong transaction.

### 14.3. Thay một Settings bằng instance mới trong cùng transaction

Trường hợp có thể gây lỗi:

~~~java
account.removeSettings();
account.addSettings();

em.flush();
~~~

Ngay trong một transaction, provider có thể phải xóa Settings cũ rồi insert Settings mới có **cùng giá trị `account_id`**. Nếu SQL INSERT xảy ra trước DELETE hoặc entity identity/constraint còn xung đột, `UNIQUE(account_id)` có thể báo lỗi.

Không được giả định mọi provider đều sắp xếp thao tác thay thế theo cách ứng dụng mong muốn.

**Nếu chỉ đổi cấu hình**, cách tốt nhất thường là **cập nhật entity Settings đang tồn tại**, thay vì xóa và tạo mới để giữ cùng một quan hệ one-to-one.

Nếu nghiệp vụ thực sự cần thay instance:

1. Thiết kế phương thức replacement riêng.
2. Xem xét thứ tự DELETE và INSERT cùng FK duy nhất.
3. Có thể cần flush sau xóa trước khi thêm mới, nếu mô hình và provider hỗ trợ.
4. Không sử dụng một object đã được đánh dấu remove như entity mới.
5. Kiểm tra việc xử lý persistence context, unique constraint và transaction.

## 15. One-to-One dùng chung khóa chính với `@MapsId`

Một biến thể khác không có cột ID độc lập của Settings:

~~~sql
CREATE TABLE account_settings (
    account_id BIGINT PRIMARY KEY
        REFERENCES customer_account(id),
    two_factor_enabled BOOLEAN NOT NULL
);
~~~

Ở đây `account_settings.account_id` vừa là PK vừa là FK.

Mapping con:

~~~java
@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private CustomerAccount account;

    protected AccountSettings() {
    }

    AccountSettings(CustomerAccount account) {
        this.account = account;
    }
}
~~~

Mapping cha:

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountSettings settings;
~~~

`@MapsId` giúp Settings nhận identity từ Account. `orphanRemoval` vẫn mô tả việc xóa thành phần bị gỡ khỏi quan hệ.

### 15.1. Vì sao thay thế càng phải cẩn trọng?

Nếu Settings cũ có `id = 20` và Account có ID 20, một Settings mới được tạo cho Account ấy cũng phải mang ID 20. Xóa entity cũ và persist entity mới cùng identity trong **cùng persistence context** có thể gây xung đột trạng thái entity hoặc SQL ordering.

Do đó, khi dùng shared PK:

- Ưu tiên cập nhật Settings hiện có.
- Xóa hẳn Settings khi nghiệp vụ thật sự yêu cầu.
- Nếu cần xóa rồi tạo lại cùng identity, phải thiết kế rõ ranh giới transaction/persistence context và kiểm thử trên provider.
- Đừng nhầm `@MapsId` với cơ chế giúp tự động “thay entity cũ bằng entity mới”.

## 16. Trường hợp `@ManyToMany`: Không dùng orphanRemoval

`orphanRemoval` là thuộc tính của `@OneToOne` và `@OneToMany`, **không phải một tùy chọn của `@ManyToMany`**.

Ví dụ:

~~~java
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
~~~

Khi một Student hủy đăng ký Course, mục tiêu thường là xóa **row liên kết** ở `student_course`, không xóa entity Course đang được nhiều Student khác sử dụng.

Dùng cascade REMOVE từ Student sang Course trong `@ManyToMany` thường nguy hiểm, vì có thể yêu cầu xóa Course dùng chung.

### 16.1. Nếu liên kết có vòng đời riêng, dùng entity trung gian

Ví dụ học viên đăng ký khóa học có thời gian đăng ký và điểm số:

~~~text
Student (1) --- (N) Enrollment (N) --- (1) Course
                        |
                        +-- enrolledAt
                        +-- status
                        +-- finalGrade
~~~

`Enrollment` có thể là entity phụ thuộc vào Student hoặc có vòng đời riêng tùy quy tắc. Nếu “hủy đăng ký” nghĩa là xóa hẳn Enrollment, `@OneToMany(orphanRemoval=true)` từ Student tới Enrollment có thể phù hợp, **nếu Enrollment không được chuyển/chia sẻ độc lập**.

Còn Course vẫn là entity tham chiếu dùng chung, không được xóa theo Enrollment.

### 16.2. Đừng biến quan hệ N:N thành xóa entity dùng chung

Ngay cả khi hai collection dùng Set và helper remove ở cả hai phía, điều đó chỉ biểu diễn việc **ngừng liên kết** giữa hai entity độc lập. Nó không đồng nghĩa một entity trở thành orphan cần xóa.

## 17. OrphanRemoval không áp dụng tùy tiện cho entity mới, detached hoặc đã remove

Đặc tả JPA quy định ý nghĩa orphanRemoval trong ngữ cảnh entity được quản lý phù hợp. Đối với target entity ở trạng thái **new**, **detached** hoặc **removed**, không được dựa vào orphanRemoval như một cơ chế xóa portable tương tự một managed child đã tồn tại.

### 17.1. Entity mới chưa persist

~~~java
PurchaseOrder order = new PurchaseOrder("ORD-001");

OrderLine newLine = order.addLine(
    product, 2, new BigDecimal("100000.00")
);

order.removeLine(newLine);

// Sau đó mới persist Order.
em.persist(order);
~~~

Nếu dòng chưa từng được persist và đã bị gỡ trước khi Order được persist, ta không cần kỳ vọng có SQL DELETE cho dòng chưa từng có row trong DB. `orphanRemoval` không phải một “undo persisted insert” tổng quát cho mọi trạng thái transient.

### 17.2. Entity detached

~~~java
PurchaseOrder order = ...; // Đã detached.
order.removeLine(existingDetachedLine);
~~~

Việc sửa detached graph không tương đương tự động thay đổi DB ngay. Sau đó gọi `merge(order)` có những quy tắc phức tạp về cascade, identity và collection reconciliation; không nên mặc định một graph detached bị cắt bớt sẽ luôn xóa đúng các orphan trên mọi provider và mọi trạng thái.

Đối với API sửa danh sách con, một hướng dễ kiểm soát hơn:

1. Mở transaction.
2. Load Order managed theo ID.
3. Tìm các OrderLine managed thuộc Order.
4. Dựa trên DTO để thêm/sửa/xóa qua helper.
5. Commit transaction.

Không nhận graph entity do client gửi rồi `merge()` toàn bộ mà không kiểm tra ownership và quyền sửa.

### 17.3. Entity đã bị remove

Nếu child đã được gọi `em.remove(child)` hoặc đã bị đánh dấu removed, không tiếp tục coi nó là một entity “đổi cha” hoặc persist lại tùy tiện. Đây là một vòng đời khác, và `orphanRemoval` không làm entity trở lại managed/persistent như một object mới.

## 18. Xóa rõ ràng bằng EntityManager.remove khi nào?

Không phải lúc nào orphanRemoval cũng là lựa chọn duy nhất.

Ví dụ một use case xóa một OrderLine theo ID:

~~~java
@Transactional
public void deleteLine(Long orderId, Long lineId) {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    if (order == null) {
        throw new IllegalArgumentException("Order not found");
    }

    OrderLine line = order.getLines()
        .stream()
        .filter(candidate -> lineId.equals(candidate.getId()))
        .findFirst()
        .orElseThrow(() ->
            new IllegalArgumentException("Line not in order")
        );

    order.removeLine(line);
}
~~~

Với association orphanRemoval, chỉ việc remove qua helper là đủ thể hiện ý định xóa entity con theo mô hình.

Trong một mô hình **không dùng orphanRemoval**, muốn xóa child thì service có thể cần:

~~~java
order.detachLineWithoutOrphanRemoval(line);
em.remove(line);
~~~

Nhưng phải bảo đảm:

- Child là managed.
- Hai phía quan hệ được đồng bộ theo thiết kế.
- Entity không còn được giữ trong collection cha.
- Transaction hợp lệ.
- Provider thực hiện DELETE với FK/constraint phù hợp.

Không cần gọi `em.remove(line)` **thêm lần nữa** sau khi orphanRemoval đã xử lý đúng chỉ để “chắc chắn”, trừ khi đã có lý do kỹ thuật được xác minh. Việc trộn hai cơ chế không cần thiết có thể làm logic khó hiểu.

## 19. Thao tác xóa nhiều dòng và hiệu năng

Nếu một Order có 10.000 dòng và xóa toàn bộ order, cascade/orphanRemoval có thể khiến provider cần quản lý nhiều child entity. SQL có thể là nhiều DELETE statement hoặc được batch tùy provider/cấu hình.

### 19.1. Tránh tải toàn bộ collection chỉ để xóa một dòng khi không cần

Nếu user muốn xóa duy nhất `lineId`, việc load toàn bộ `order.lines` có thể tốn bộ nhớ. Có thể dùng một truy vấn entity con có điều kiện:

~~~java
OrderLine line = em.createQuery(
        "SELECT l FROM OrderLine l " +
        "WHERE l.id = :lineId " +
        "AND l.order.id = :orderId",
        OrderLine.class
    )
    .setParameter("lineId", lineId)
    .setParameter("orderId", orderId)
    .getResultStream()
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException("Line not found")
    );
~~~

Sau đó cần chọn chiến lược xóa **giữ nhất quán object graph**:

- Nếu Order đã managed và collection đã load, dùng helper trên Order để remove khỏi collection.
- Nếu sử dụng `em.remove(line)` trực tiếp, đảm bảo collection đang managed không giữ reference cũ theo cách nghiệp vụ sử dụng lại trong cùng context.
- Nếu không tải Order collection, có thể tổ chức service thao tác theo managed child/owner và làm rõ cách đồng bộ context trước khi dùng lại.
- Với số lượng lớn, cân nhắc batch/chunk, nhưng phải giữ đúng yêu cầu transaction atomicity.

### 19.2. Bulk JPQL DELETE không kích hoạt lifecycle thông thường

Ví dụ:

~~~java
int deleted = em.createQuery(
    "DELETE FROM OrderLine l WHERE l.order.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
~~~

Bulk delete thực thi trực tiếp đối với database và **không chạy quy trình remove từng managed entity theo cách orphanRemoval/cascade entity bình thường**. Nó cũng không tự cập nhật `order.lines` trong persistence context đã load.

Vì vậy, nếu chọn bulk delete, cần hiểu rõ:

- Entity callbacks và cascading entity-level có thể bị bỏ qua.
- Persistence context có thể giữ các OrderLine đã bị DB xóa.
- Các FK từ bảng khác tới OrderLine vẫn áp dụng và có thể làm bulk delete lỗi.
- Có thể cần `flush()` trước bulk DML và `clear()`/refresh/reload sau đó.
- `clear()` detach entities; pending changes chưa flush có thể bị mất.

Đừng dùng bulk DELETE như một tối ưu vô điều kiện cho mô hình có lifecycle/audit phức tạp.

## 20. OrphanRemoval và cập nhật collection từ DTO

Một API nhận payload:

~~~json
{
  "orderId": 10,
  "lines": [
    {"id": 101, "quantity": 3},
    {"productId": 202, "quantity": 1}
  ]
}
~~~

Giả sử DB hiện có Line #101 và #102. Ý định của payload:

- Giữ Line #101, cập nhật quantity.
- Xóa Line #102 khỏi đơn.
- Thêm một dòng mới tham chiếu Product #202.

Một triển khai không nên làm:

~~~java
order.setLines(mapDtoToNewEntities(request.lines()));
~~~

vì nó có thể:

- Mất identity của Line #101.
- Thay wrapper persistent collection.
- Tạo duplicate PK hoặc entity detached.
- Gây xóa và thêm lại không cần thiết.
- Làm mất kiểm tra quyền sở hữu/order state.

Một workflow tốt hơn:

~~~text
Transaction bắt đầu
        |
        v
Load managed PurchaseOrder
        |
        v
Xác thực order thuộc người dùng và ở trạng thái DRAFT
        |
        v
Đọc danh sách OrderLine managed hiện có
        |
        +-- ID còn trong DTO: sửa field cho phép
        |
        +-- ID vắng khỏi DTO: order.removeLine(line)
        |
        +-- Item mới: order.addLine(product, qty, price)
        |
        v
Flush/commit theo transaction boundary
~~~

### 20.1. Phân biệt “không gửi danh sách” và “gửi danh sách rỗng”

Trong API PATCH:

- Field `lines` không xuất hiện có thể mang ý nghĩa “không sửa các dòng”.
- Field `lines: []` có thể mang ý nghĩa “xóa toàn bộ các dòng”.
- Field `lines: null` cần được định nghĩa rõ là hợp lệ hay không.

Không để framework mapping DTO tự chuyển cả ba trạng thái thành một collection rỗng rồi vô tình orphan-delete toàn bộ dữ liệu.

### 20.2. Không tin ID con do client gửi

Khi request cung cấp `lineId`, service phải xác nhận dòng thực sự thuộc Order đang được sửa. Không chỉ gọi:

~~~java
OrderLine line = em.find(OrderLine.class, lineId);
em.remove(line);
~~~

rồi bỏ qua kiểm tra `line.order.id == orderId` và quyền của caller. Nếu không, API có thể xóa dòng thuộc đơn khác.

## 21. OrphanRemoval trong quan hệ có khóa tổng hợp

Một OrderLine có thể dùng khóa tổng hợp, ví dụ:

~~~text
(order_id, line_number)
~~~

Trong trường hợp này, `order_id` là một phần của primary key của child, không chỉ là FK bình thường.

Một mapping nâng cao có thể sử dụng `@EmbeddedId` và `@MapsId("orderId")`. Khi đó:

- Identity của line chứa ID của Order.
- Chuyển line sang Order khác đồng nghĩa đổi **primary key**.
- Việc reparent managed entity càng không phù hợp.
- Orphan removal diễn đạt xóa dòng đã không còn thuộc order, không diễn đạt chuyển PK.
- Nếu cần “chuyển dòng”, thường phải xem đó là tạo record mới với identity mới rồi xóa record cũ.

Không nên mặc định dùng composite key chỉ vì line có số thứ tự. Nếu line number thường được sắp xếp lại, việc đưa nó vào PK có thể tạo thêm chi phí cập nhật identity. Có thể dùng PK kỹ thuật riêng và constraint `UNIQUE(order_id, line_number)` nếu nghiệp vụ cho phép.

## 22. Concurrency: OrphanRemoval không thay thế locking

Giả sử hai request đồng thời sửa cùng một đơn DRAFT:

~~~text
Transaction A                        Transaction B
----------------------------------   ----------------------------------
Load Order #10 có Line #101,#102     Load Order #10 có Line #101,#102
A xóa Line #102                      B sửa quantity của Line #102
A flush DELETE                       B flush UPDATE
A commit                             B có thể lỗi lock/stale row
~~~

Kết quả phụ thuộc isolation, versioning và thời điểm commit. `orphanRemoval` tự nó **không giải quyết xung đột đồng thời** giữa thao tác xóa và sửa.

### 22.1. Optimistic locking

Có thể khai báo `@Version` trên OrderLine:

~~~java
@Version
@Column(name = "version", nullable = false)
private long version;
~~~

Khi provider thực thi UPDATE/DELETE với optimistic locking, xung đột có thể được phát hiện thông qua version hoặc số row bị ảnh hưởng. Nếu Order là aggregate root và mọi chỉnh sửa collection cần được tuần tự hóa theo một version chung, hãy thiết kế rõ optimistic locking ở mức Order và xác minh cách provider đánh version khi collection thay đổi.

Không mặc định việc remove một child trên inverse collection luôn tăng version của parent trong mọi mapping/provider. Nếu yêu cầu tranh chấp nghiêm ngặt, có thể lock parent có chủ đích bằng `LockModeType.OPTIMISTIC_FORCE_INCREMENT` hoặc cách phù hợp, rồi kiểm thử.

### 22.2. Xóa và thêm cùng một khóa nghiệp vụ

Giả sử order có ràng buộc:

~~~sql
UNIQUE (order_id, product_id)
~~~

nghĩa là một Product chỉ được xuất hiện một lần trong một Order.

Trong cùng transaction:

~~~java
order.removeLine(oldLineForProduct);
order.addLine(product, 1, price);
~~~

Nếu provider thực thi INSERT mới trước khi DELETE oldLine, `UNIQUE(order_id, product_id)` có thể báo lỗi.

Cách xử lý phụ thuộc nghiệp vụ:

- Nếu chỉ thay quantity/price, **update existing line**.
- Nếu cần thay instance, quản lý rõ thứ tự xóa rồi thêm; có thể cần flush trung gian.
- Không bỏ unique constraint để tránh lỗi ordering mà làm mất invariant.
- Không tái sử dụng managed entity đã bị orphan như thể nó là entity mới.

### 22.3. Soft delete và unique constraint

Nếu hệ thống lưu lịch sử bằng soft delete, ràng buộc UNIQUE của bản ghi active có thể cần được thiết kế đặc biệt (ví dụ partial unique index ở DB hỗ trợ). OrphanRemoval vật lý không tự trở thành soft-delete; phải chọn một mô hình nghiệp vụ khác hoặc extension được hỗ trợ rõ ràng.

## 23. OrphanRemoval không tự hỗ trợ soft delete

Có những hệ thống không được xóa vật lý OrderLine vì yêu cầu audit, kế toán hoặc pháp lý.

Thay vì:

~~~java
@OneToMany(orphanRemoval = true)
private List<OrderLine> lines;
~~~

có thể cần giữ row và đánh dấu:

~~~java
public void cancelLine() {
    this.status = LineStatus.CANCELLED;
}
~~~

Một ứng dụng có thể lưu sự kiện điều chỉnh hoặc phiên bản hóa dòng hàng, thay vì xóa record.

Nếu dùng Hibernate-specific soft-delete mapping hoặc interceptor SQL, cần hiểu tác động tới:

- Orphan removal.
- Entity callbacks.
- Unique constraint.
- Query lọc record active.
- Quan hệ FK.
- Audit/versioning.
- Khả năng khôi phục.

**JPA orphanRemoval portable thể hiện thao tác remove entity**, không có nghĩa “chuyển `deleted=true`” theo mặc định. Khi nghiệp vụ cần lưu lịch sử, đừng bật orphanRemoval rồi kỳ vọng Hibernate/JPA tự giữ đủ dữ liệu.

## 24. Không dùng orphanRemoval cho dữ liệu lịch sử cần bất biến

Một hóa đơn đã phát hành thường phải được lưu giữ đầy đủ:

~~~text
Invoice #2026-001
  +-- InvoiceLine #1
  +-- InvoiceLine #2
~~~

Nếu người dùng “sửa hóa đơn” bằng cách gỡ một line và orphanRemoval tự xóa row lịch sử, ứng dụng có thể phá quy tắc kế toán.

Những mô hình thay thế:

- Không cho sửa Invoice đã issued.
- Lập credit note hoặc adjustment record.
- Phiên bản hóa hóa đơn.
- Soft-cancel một line và giữ audit theo yêu cầu.
- Dùng trạng thái DRAFT cho phép sửa, nhưng chuyển sang ISSUED thì các thao tác remove bị chặn ở domain.

Điểm mấu chốt: **orphanRemoval là chính sách xóa**, không chỉ là tiện ích tự dọn collection. Nó phải phản ánh điều gì được phép mất khỏi lịch sử.

## 25. Theo dõi SQL và transaction khi debug orphanRemoval

Nếu gọi `order.removeLine(line)` nhưng không thấy row bị xóa, hãy xem từng lớp:

### 25.1. Entity có đang managed không?

Nếu Order detached hoặc được tạo ngoài transaction rồi không được merge/persist phù hợp, sửa collection có thể chỉ là thay đổi Java thuần, không được JPA đồng bộ.

### 25.2. Transaction có hoạt động không?

Gọi flush với thay đổi cần DB transaction mà transaction không phù hợp có thể gây `TransactionRequiredException`. Với Spring, đảm bảo method `@Transactional` được gọi qua proxy/interceptor theo cấu hình.

### 25.3. Mapping có đúng association không?

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
~~~

thì child phải có:

~~~java
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

`mappedBy = "order"` là **tên property Java**, không phải tên cột `order_id`.

### 25.4. Code có thay đổi collection đang managed không?

Nếu gán list mới hoặc sửa field child mà không sửa collection cha, provider có thể không thấy tín hiệu orphan đúng mong đợi.

### 25.5. Có flush hoặc commit thực tế chưa?

Không có SQL DELETE trước flush chưa phải bug. Nếu flush/commit đã chạy nhưng row vẫn còn, kiểm tra log transaction/rollback và SQL.

### 25.6. Có DB constraint chặn xóa không?

Ví dụ một bảng `shipment_line` còn FK trỏ tới `order_line.id` với quy tắc restrict. Xóa OrderLine có thể bị DB từ chối cho tới khi dữ liệu phụ thuộc sâu hơn được xử lý phù hợp.

Orphan removal ở một tầng không tự xóa toàn bộ các entity tham chiếu tới child từ mọi nơi.

### 25.7. Có bulk SQL hoặc native SQL can thiệp không?

Một lệnh bulk DELETE có thể xóa row nhưng persistence context vẫn giữ entity cũ. Ngược lại, một cache hoặc query ở transaction snapshot cũ có thể khiến người quan sát nghĩ row chưa bị xóa.

Cần kiểm tra ở transaction/persistence context mới khi muốn xác nhận dữ liệu đã committed.

## 26. Integration test: Kiểm tra xóa orphan trong DB

Để kiểm chứng mapping trên database thực, tổ chức test theo hai transaction hoặc hai persistence context độc lập.

### 26.1. Test thêm rồi xóa một dòng

Ý tưởng test:

~~~java
@Test
void removingLineDeletesRowAfterCommit() {
    Long orderId;
    Long lineId;

    // Transaction 1: tạo dữ liệu và commit.
    {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Product product =
                em.find(Product.class, existingProductId);

            PurchaseOrder order =
                new PurchaseOrder("ORD-TEST-001");

            OrderLine line = order.addLine(
                product, 2, new BigDecimal("99000.00")
            );

            em.persist(order);
            em.flush();

            orderId = order.getId();
            lineId = line.getId();

            tx.commit();
        } finally {
            em.close();
        }
    }

    // Transaction 2: xóa line bằng helper rồi commit.
    {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order =
                em.find(PurchaseOrder.class, orderId);

            OrderLine line =
                order.getLines().stream()
                    .filter(l -> lineId.equals(l.getId()))
                    .findFirst()
                    .orElseThrow();

            order.removeLine(line);
            tx.commit();
        } finally {
            em.close();
        }
    }

    // Context mới để xác minh trạng thái committed.
    {
        EntityManager em = emf.createEntityManager();
        try {
            assertNull(em.find(OrderLine.class, lineId));
            assertNotNull(em.find(PurchaseOrder.class, orderId));
        } finally {
            em.close();
        }
    }
}
~~~

Đây là ví dụ về cấu trúc integration test, giả định `existingProductId` thuộc fixture đã tồn tại và các dependency/JUnit assertions được cấu hình. Mẫu production nên xử lý rollback trong catch trước khi close; nội dung test tập trung vào hai mốc commit và đọc lại độc lập.

### 26.2. Test FK NOT NULL

Tạo OrderLine cố tồn tại mà không có Order phải bị từ chối theo policy của entity và constraint DB. Không chỉ kiểm tra exception từ constructor; còn cần xác nhận DB có `order_id NOT NULL` và FK thực tế.

### 26.3. Test xóa cha

Tạo Order cùng hai OrderLine, commit, rồi `em.remove(order)` trong transaction mới. Kiểm tra:

- Order bị xóa nếu nghiệp vụ cho phép.
- Các line phụ thuộc bị xóa theo cascade/orphanRemoval mapping.
- Product vẫn tồn tại.
- Không có FK violation.
- Không có row orphan còn lại.

### 26.4. Test rollback sau flush

~~~java
tx.begin();

order.removeLine(line);
em.flush();     // Có thể đã thực thi DELETE.

tx.rollback();  // Hủy DELETE trong transaction.

EntityManager verify = emf.createEntityManager();
// Đọc ở context mới, transaction thích hợp:
// Row vẫn còn nếu việc xóa chỉ xảy ra trong transaction bị rollback.
~~~

Đừng xác nhận rollback bằng `em.find()` ngay trong một context đã chịu nhiều thao tác remove rồi rollback; hãy mở context mới để tránh hiểu sai trạng thái managed.

### 26.5. Test ràng buộc one-to-one

Với AccountSettings:

- Không được có hai Settings cho cùng Account.
- Gỡ Settings phải xóa entity phụ thuộc.
- Xóa Account phải tuân theo policy xóa Settings.
- Thay Settings trong cùng transaction cần xử lý xung đột UNIQUE nếu có.
- Với `@MapsId`, ID của Settings phải bằng ID Account khi persist đúng.

### 26.6. Test với provider và DB thật

Một H2 test đơn giản có thể không phản ánh toàn bộ khác biệt về SQL ordering, deferred constraint, FK action và isolation của PostgreSQL/MySQL/Oracle. Nếu logic phụ thuộc hành vi xóa và UNIQUE constraint, integration test nên chạy với DB/dialect tương ứng triển khai thực.

## 27. Bảng tổng hợp các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Xóa khỏi collection nhưng FK không đổi | Quan hệ hai chiều chưa đồng bộ owning side; hoặc entity không managed | Dùng helper đồng bộ cả hai phía trong transaction |
| Đặt `mappedBy = "order_id"` bị lỗi | Dùng tên cột SQL thay vì tên field Java | Đổi thành `mappedBy = "order"` |
| DB báo `NOT NULL violation` khi tách child | Provider đang cố lưu FK null, child chưa được xử lý là orphan hoặc mapping sai | Kiểm tra association và cách gỡ, không bỏ constraint tùy tiện |
| Child vẫn còn sau khi remove khỏi collection | Thiếu orphanRemoval, chưa flush/commit, hoặc thao tác trên detached object | Kiểm tra lifecycle và transaction |
| Xóa Order kéo theo xóa Product | Cascade REMOVE đặt sai trên `OrderLine.product` | Giữ Product là entity độc lập, không cascade xóa |
| Dùng `CascadeType.REMOVE` nhưng gỡ child không xóa row | Cascade REMOVE kích hoạt khi remove parent, không tự thay orphanRemoval | Thêm orphanRemoval khi đúng nghiệp vụ |
| Muốn chuyển Employee sang Department khác nhưng row bị xóa | Dùng orphanRemoval cho quan hệ không độc quyền vòng đời | Không dùng orphanRemoval, cập nhật FK để chuyển |
| Insert Settings mới lỗi UNIQUE khi thay Settings cũ | INSERT trước DELETE hoặc entity identity còn xung đột | Update instance cũ hoặc thiết kế replacement rõ |
| Xóa Order bị FK violation từ bảng khác | Child khác còn tham chiếu OrderLine/Order | Thiết kế chính sách các FK liên quan và thứ tự xóa |
| Bulk DELETE xong Java collection vẫn có item | Bulk DML bỏ qua đồng bộ managed entities | Flush trước/clear hoặc reload có kiểm soát |
| `ON DELETE CASCADE` đã cấu hình nhưng remove khỏi collection không xóa child | DB cascade chỉ kích hoạt khi xóa parent row | Orphan removal/JPA remove child riêng |
| SQL DELETE xuất hiện nhưng dữ liệu vẫn còn sau test | Transaction test đã rollback hoặc chưa commit | Xác nhận ở context/transaction mới |
| Entity mới bị thêm rồi gỡ không tạo DELETE | Entity new chưa được lưu thành row | Không kỳ vọng DELETE một row chưa tồn tại |
| Thay collection bằng list mới gây lỗi ORM | Mất persistent collection wrapper/tracking | Giữ instance collection và sửa qua helper |
| Xóa một dòng rồi thêm cùng Product gây UNIQUE violation | Constraint theo `(order_id, product_id)` gặp SQL ordering | Update dòng cũ hoặc chia rõ trình tự xóa/thêm |
| Cùng một child được gắn hai cha | Mô hình trái lifecycle ownership, collection và FK thiếu nhất quán | Cấm reparent, hoặc đổi mô hình nếu cần chuyển |
| Entity con đã removed nhưng vẫn được persist lại | Vi phạm vòng đời entity | Tạo entity mới, không tái sử dụng removed orphan |
| Xóa làm mất dữ liệu lịch sử | OrphanRemoval bật trái quy tắc audit/soft delete | Thiết kế trạng thái/phiên bản/sự kiện điều chỉnh |
| Concurrent update và delete gây lỗi | Thiếu hoặc chưa thiết kế locking/concurrency | `@Version`, lock parent, constraint và retry đúng cách |
| Lazy collection không tải ngoài transaction | EntityManager/session đã đóng | Truy vấn hoặc tạo DTO trong transaction phù hợp |

## 28. Quy trình quyết định cho một quan hệ cha–con mới

### Bước 1: Xác định vòng đời của con

Hỏi: “Nếu con không còn thuộc cha, con được phép tồn tại không?”

- Nếu **không**: cân nhắc `orphanRemoval = true`.
- Nếu **có**: thường không dùng orphanRemoval; thiết kế unlink, chuyển cha hoặc giữ entity độc lập.
- Nếu **không được xóa vì lịch sử**: dùng quy tắc trạng thái/phiên bản thay vì xóa vật lý.

### Bước 2: Xác định cardinality

- Một cha có nhiều con, mỗi con thuộc một cha → One-to-Many/Many-to-One.
- Một cha có tối đa một con phụ thuộc → One-to-One.
- Nhiều bên cùng dùng chung một entity → xem lại vì orphanRemoval thường không phù hợp với đối tượng dùng chung.

### Bước 3: Vẽ khóa ngoại vật lý

Xác định:

- FK nằm ở bảng nào?
- FK có được null?
- Có cần UNIQUE cho One-to-One?
- FK có liên kết tới dữ liệu được dùng chung?
- DB có cần `ON DELETE CASCADE` hoặc `RESTRICT`?
- Còn bảng nào tham chiếu child không?

### Bước 4: Chọn owning side JPA

Với FK ở bảng child và quan hệ hai chiều:

~~~java
// Child owning side:
@ManyToOne
@JoinColumn(name = "parent_id")
private Parent parent;

// Parent inverse side:
@OneToMany(mappedBy = "parent")
private List<Child> children;
~~~

Đừng nhầm owning side association với lifecycle ownership.

### Bước 5: Chọn cascade và orphanRemoval riêng rẽ

Quyết định:

- Parent persist có persist child mới không?
- Parent remove có remove child không?
- Gỡ child khỏi parent có nghĩa DELETE child không?
- Child có cần merge/refresh/detach cùng parent không?
- Có entity dùng chung không được xóa liên đới không?

Không bật `cascade = ALL` chỉ để tránh một lỗi transient entity mà không hiểu vòng đời.

### Bước 6: Viết helper đồng bộ hai phía

Cấm caller tự ý mutate collection. Helper thêm phải gán FK owning side; helper xóa phải phản ánh việc tách khỏi collection và không tạo ra một entity con sống sót trái với orphanRemoval.

### Bước 7: Chọn ranh giới transaction

Tất cả thao tác sửa Order và Line nên xảy ra trong transaction ứng dụng. Không nhầm `flush()` với `commit()`.

### Bước 8: Tính đến concurrency

Nếu xóa/thêm entity trùng khóa nghiệp vụ, xem constraint và SQL ordering. Nếu nhiều request sửa cùng aggregate, xem `@Version`, lock và chính sách retry.

### Bước 9: Kiểm tra đối với đường ghi ngoài JPA

Nếu có bulk JPQL, native SQL, JDBC, migration hoặc microservice khác ghi DB, hiểu rõ rằng orphanRemoval không tự chạy cho mọi đường đó. Chọn constraint và chính sách xóa DB phù hợp.

### Bước 10: Integration test ở context mới

Test persist, remove, flush, commit, rollback; kiểm tra con bị xóa và các entity tham chiếu độc lập được giữ lại. Đối với One-to-One, test UNIQUE; đối với One-to-Many, test FK NOT NULL; với DB cascade, test tương tác đúng theo hệ thống thực.

## 29. Bài tập thực hành

### Bài 1: Đọc đúng phía sở hữu

Cho:

~~~java
// Order
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;

// OrderLine
@ManyToOne(optional = false)
@JoinColumn(name = "order_id", nullable = false)
private Order order;
~~~

**Câu hỏi:** Ai là JPA owning side? Ai sở hữu vòng đời nghiệp vụ? `mappedBy` có tham chiếu tên cột SQL không?

**Đáp án:** `OrderLine.order` là JPA owning side vì ánh xạ FK. `Order` có thể sở hữu vòng đời các OrderLine nhờ quy tắc nghiệp vụ/orphanRemoval. `mappedBy = "order"` là tên field Java, không phải `order_id`.

### Bài 2: FK NOT NULL và orphan removal

Bảng `order_line` có `order_id NOT NULL`. Khi gỡ OrderLine khỏi collection có `orphanRemoval=true`, mục tiêu cuối cùng của persistence là gì?

**Đáp án:** Xóa row OrderLine orphan, không giữ một row có `order_id=NULL`. Trình tự SQL phải thỏa FK; cần dùng helper và kiểm thử provider, không bỏ NOT NULL chỉ để hợp thức hóa lỗi mapping.

### Bài 3: Cascade REMOVE có đủ không?

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.REMOVE)
private List<OrderLine> lines;
~~~

Service gọi `order.getLines().remove(line)` nhưng không remove Order.

**Câu hỏi:** Có chắc Line bị DELETE không?

**Đáp án:** Không. Chỉ `CascadeType.REMOVE` áp dụng khi remove parent; nó không tự biến việc xóa phần tử collection thành remove entity con. Cân nhắc `orphanRemoval=true` nếu đúng vòng đời.

### Bài 4: Employee chuyển phòng

Department có `@OneToMany(mappedBy="department", orphanRemoval=true)`. Employee phải được phép chuyển Department mà giữ nguyên ID.

**Câu hỏi:** Annotation đó có phù hợp không?

**Đáp án:** Thường không. Employee có vòng đời độc lập; gỡ khỏi department cũ không được hiểu là xóa Employee. Cần thay đổi mapping/lifecycle, cập nhật owning FK và cả hai collections theo operation chuyển phòng.

### Bài 5: Many-to-Many giữa Student và Course

Student bỏ một Course khỏi `student.courses`.

**Câu hỏi:** Có nên xóa entity Course không? Có `orphanRemoval` cho `@ManyToMany` không?

**Đáp án:** Không. Course được nhiều Student dùng chung. JPA `@ManyToMany` không có thuộc tính orphanRemoval; bỏ liên kết thường chỉ xóa row join table.

### Bài 6: Thay One-to-One

Account có Settings cũ và FK `account_id UNIQUE`. Service gỡ Settings cũ rồi tạo Settings mới ngay trong cùng transaction.

**Câu hỏi:** Rủi ro là gì?

**Đáp án:** Nếu INSERT mới xảy ra trước DELETE cũ, có thể vi phạm UNIQUE. Với shared PK còn có xung đột identity trong persistence context. Ưu tiên cập nhật Settings hiện có hoặc tổ chức replacement với ranh giới rõ và test provider.

### Bài 7: Gỡ orphan rồi gắn sang parent khác

~~~java
orderA.removeLine(line);
orderB.attachExistingLine(line);
~~~

OrderA có `orphanRemoval=true`.

**Câu hỏi:** Có được coi là move an toàn theo chuẩn JPA không?

**Đáp án:** Không. Entity đã orphan có thể bị xử lý remove; JPA không bảo đảm “cứu lại” qua reassociation. Nếu nghiệp vụ cho phép move cùng identity, thường không dùng orphanRemoval; nếu chỉ chuyển dữ liệu, tạo child mới và xóa child cũ.

### Bài 8: Bulk DELETE

~~~java
em.createQuery(
    "DELETE FROM OrderLine l WHERE l.order.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
~~~

**Câu hỏi:** `order.lines` đã load có tự mất hết phần tử không?

**Đáp án:** Không được bảo đảm. Bulk DML bỏ qua đồng bộ từng managed entity; cần xử lý context/reload phù hợp và hiểu các FK/callback bị tác động.

### Bài 9: DB cascade và ORM orphan removal

DB có `ON DELETE CASCADE` trên `order_line.order_id`, nhưng service chỉ gỡ một line khỏi collection mà không xóa Order.

**Câu hỏi:** DB cascade có tự xóa line không?

**Đáp án:** Không. ON DELETE CASCADE kích hoạt khi parent row bị xóa. Muốn xóa riêng line phải dùng ORM orphanRemoval hoặc DELETE line rõ ràng.

### Bài 10: Flush và rollback

~~~java
tx.begin();
order.removeLine(line);
em.flush();
tx.rollback();
~~~

**Câu hỏi:** Nếu log xuất hiện `DELETE FROM order_line`, row có chắc biến mất sau rollback không?

**Đáp án:** Không. DELETE thuộc transaction chưa commit; rollback hủy tác động của transaction theo quy tắc DB.

### Bài 11: Soft delete lịch sử hóa đơn

Invoice đã phát hành bắt buộc lưu mọi dòng để audit; UI muốn “xóa” một dòng.

**Câu hỏi:** Có nên dùng `orphanRemoval=true` cho InvoiceLine không?

**Đáp án:** Thường không nếu yêu cầu là giữ lịch sử bất biến. Cần nghiệp vụ điều chỉnh, credit note hoặc trạng thái hủy/phiên bản hóa thay vì xóa vật lý.

### Bài 12: Chỉnh sửa DTO không xóa nhầm

Client gửi orderId=10 và chỉ một line trong danh sách, trong khi DB có ba line.

**Câu hỏi:** Nếu request là PATCH, có nên mặc định xóa hai line còn lại?

**Đáp án:** Không cho tới khi API định nghĩa rõ semantics của field list. Có thể “không gửi list” là không thay đổi và “gửi list đầy đủ” là đồng bộ toàn bộ. Cần phân biệt field vắng mặt, null, list rỗng; kiểm tra quyền sở hữu của các line ID trước khi xóa.

## 30. Tóm tắt trọng tâm

~~~text
                 PurchaseOrder
             (chủ vòng đời nghiệp vụ)
                          |
             @OneToMany(mappedBy="order")
                 orphanRemoval=true
                          |
                          | inverse side
                          v
                     OrderLine
                          |
              @ManyToOne(optional=false)
              @JoinColumn(name="order_id")
                          |
                          | JPA owning side
                          v
                order_line.order_id
                   FK + NOT NULL
                          |
                          v
               purchase_order.id

Thao tác gỡ line:
    Order.removeLine(line)
             |
             +-- xóa khỏi Order.lines
             +-- đồng bộ line.order
             |
             v
    JPA nhận biết orphan ở flush
             |
             v
    DELETE child (theo mapping)
             |
             v
    COMMIT thành công: row biến mất
    ROLLBACK: tác động bị hủy
~~~

Những nguyên tắc cần ghi nhớ:

1. **`orphanRemoval = true` dành cho thành phần phụ thuộc vòng đời**, không dành cho entity tham chiếu dùng chung hoặc đối tượng thường xuyên đổi cha.
2. **Business ownership và JPA owning side là hai khái niệm khác nhau.** Parent có thể sở hữu vòng đời, nhưng `@ManyToOne` phía child mới là owning side của FK.
3. **`mappedBy` trỏ tới thuộc tính Java ở owning side**, không phải tên cột foreign key.
4. **Quan hệ hai chiều phải được đồng bộ bằng helper.** Chỉ sửa inverse collection hoặc chỉ sửa owning field đều có thể để object graph bất nhất.
5. **FK `NOT NULL` phù hợp với orphanRemoval khi mục tiêu là DELETE child**, không phải cập nhật FK thành null rồi giữ row còn sống.
6. **`CascadeType.REMOVE` và orphanRemoval khác nhau:** một cái lan thao tác remove từ parent, cái kia xử lý child khi rời association.
7. **`@OneToOne` cần UNIQUE FK hoặc shared PK để bảo vệ cardinality**, đồng thời replacement trong cùng transaction có thể vướng SQL ordering và identity.
8. **`ON DELETE CASCADE` của DB không thay thế orphanRemoval của JPA**; cơ chế, callbacks và persistence context khác nhau.
9. **Không reassociate một entity orphan như một thao tác move portable.** Nếu cần chuyển ownership mà giữ identity, phải chọn mô hình khác.
10. **Flush là thời điểm đồng bộ thao tác xóa; commit mới xác nhận giao dịch.** SQL DELETE xuất hiện không chứng minh dữ liệu đã biến mất vĩnh viễn.
11. **Bulk DML, native SQL và đường ghi ngoài JPA có thể bỏ qua lifecycle thông thường**, nên constraint DB vẫn phải đủ chặt.
12. **OrphanRemoval không phải soft delete.** Nếu phải giữ lịch sử, dùng cơ chế domain/audit thích hợp thay vì xóa vật lý.
13. **Concurrency, unique constraint và DTO reconciliation cần được thiết kế rõ.** Một annotation không tự giải quyết race condition hoặc ý nghĩa cập nhật list.
14. **Kiểm chứng trên database/provider thật**, ở persistence context/transaction mới sau commit hoặc rollback, để phân biệt trạng thái managed với dữ liệu được xác nhận.

Khi phối hợp đúng ba lớp **vòng đời nghiệp vụ – owning side JPA – ràng buộc khóa ngoại**, `orphanRemoval` giúp loại bỏ thành phần phụ thuộc một cách tự nhiên, nhất quán và dễ bảo trì. Nếu bỏ qua một trong ba lớp, một thao tác tưởng như đơn giản là “xóa một phần tử khỏi collection” có thể dẫn tới FK violation, xóa nhầm entity dùng chung, dữ liệu mồ côi hoặc mất lịch sử nghiệp vụ.
